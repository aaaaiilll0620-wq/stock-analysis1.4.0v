"""O-E · build the canonical trading calendar and security-status sources.

Importer for the two market-state inputs O-B consumes. All vendor-specific
column names live here; `core.b0_market_state` never sees a Chinese column name.

Calendar     : observed TAIEX sessions. Observing that the index traded on day d
               is knowable on day d, so an observed-session calendar is PIT-safe
               by construction for the `<= as_of` queries O-B makes. A published
               forward holiday schedule is deliberately NOT used.

Status       : 暫停交易 (1,950 rows, 2004-2026), which carries 年月日, 恢復交易日
               and 暫停交易原因. It is a historical effective-date table, not a
               current snapshot. Vintage 20260818 (UTF-16 TSV inside per-era
               zips); the 20260806 xlsx vintage it replaces was deleted upstream
               and is NOT required to exist -- see research/of_security_status.

Availability convention (O-E-1), declared rather than assumed:
    available_from = 年月日 for the suspension record, and the guard then only
    lets it explain sessions STRICTLY AFTER that date. Measured consequence:
    1,529 of 1,940 usable rows (78.8%) still have a price on 年月日, so the
    strict rule costs nothing there; the 411 without a price are dominated by
    下市 / 違規 reasons, where the first missing session is 年月日 itself and the
    run correctly aborts — that is the unreconstructible identity transition of
    section 2.4, not a gap to be explained away.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import collections
import csv
import glob
import hashlib
import json
import os
import sys
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_market_state import (                                # noqa: E402
    STATUS_DELISTED, STATUS_LISTED, STATUS_SUSPENDED,
    SecurityStatusTable, SourceContract, StatusRecord, TradingCalendar,
    assert_not_promoted_to_suspended, classify_event_semantics,
    market_state_provenance, status_for_event,
)

SUSP_DIR = os.path.join(REPO, "tej_exports", "DataExport0806", "暫停交易2004-20260818")
SUSP_GLOB = "暫停交易*.zip"      # the sibling 事件+下市.zip is a different source
CAL_SRC = os.path.join(os.path.expanduser("~"), "market_cache", "taiex_daily.parquet")
OUT_DIR = os.path.join(REPO, "data", "b0")
OUT_CAL = os.path.join(OUT_DIR, "trading_calendar.csv")
OUT_STATUS = os.path.join(OUT_DIR, "security_status.csv")
OUT_CONTRACTS = os.path.join(HERE, "market_state_contracts.json")

IMPORTER_VERSION = "b0_market_state_importer@3"
SUSPENSION_COLUMNS = ("證券代碼", "年月日", "恢復交易日", "暫停交易原因")

# The reason -> status mapping is NOT decided here. `core.b0_market_state`
# carries it, because O-F ruling 4 made it normative: a row in this export is not
# automatically a suspension, and a book-closure or uninterpretable row must fail
# closed rather than be promoted. This importer only reports what the mapping
# produced.


def d8(v):
    s = str(v).strip().split(".")[0]
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_zip_tsv(path):
    """The 20260818 vintage ships UTF-16 TSV inside a zip, one member per era."""
    rows = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            lines = [ln for ln in zf.read(name).decode("utf-16").splitlines()
                     if ln.strip()]
            header = lines[0].split("	")
            if header != list(SUSPENSION_COLUMNS):
                raise SystemExit(f"{path}:{name} schema {header} != "
                                 f"{list(SUSPENSION_COLUMNS)}")
            rows += [dict(zip(header, ln.split("	"))) for ln in lines[1:]]
    return rows


def build_calendar():
    df = pd.read_parquet(CAL_SRC)
    sessions = sorted({str(d) for d in df["date"]})
    contract = SourceContract(
        name="b0_trading_calendar", kind="trading_calendar",
        importer_version=IMPORTER_VERSION,
        content_sha256=_sha("\n".join(sessions)),
        schema_sha256=_sha("session"),
        date_min=sessions[0], date_max=sessions[-1],
        has_effective_dates=True,           # each session IS its own effective date
        has_availability_semantics=True,    # a traded session is known that day
        is_current_snapshot=False,
        availability_convention=(
            "observed sessions only; a session is knowable on the day it trades. "
            "A forward-published holiday schedule is not used, because it would "
            "let a replay standing at t assert facts about sessions after t."),
    )
    return sessions, contract


def build_status():
    rows = []
    semantics_count = collections.Counter()
    dropped = []
    for f in sorted(glob.glob(os.path.join(SUSP_DIR, SUSP_GLOB))):
        for r in _read_zip_tsv(f):
            sid = str(r["證券代碼"]).split()[0]
            start, resume = d8(r["年月日"]), d8(r["恢復交易日"])
            reason = str(r["暫停交易原因"]).strip()
            if not start:
                continue
            semantics = classify_event_semantics(reason)
            status = status_for_event(reason)
            semantics_count[semantics] += 1
            if status is None:
                # O-F ruling 4, fail closed. A 停止過戶 window or an
                # uninterpretable one produces NO record, so it can never stand
                # over a session as an explanation.
                dropped.append({"stock_id": sid, "effective_from": start,
                                "semantics": semantics, "reason": reason})
                continue
            assert_not_promoted_to_suspended(reason, status)
            rows.append({
                "stock_id": sid,
                "status": status,
                "effective_from": start,
                # O-E-1: declared convention, see module docstring.
                "available_from": start,
                "reason": reason,
                "source": "TEJ 暫停交易",
            })
            # A resumption is a separate filed fact, knowable on the day it
            # happens. Emitting it lets a later `listed` record cancel an earlier
            # suspension instead of the suspension explaining gaps forever.
            if resume and status != STATUS_DELISTED:
                rows.append({
                    "stock_id": sid, "status": STATUS_LISTED,
                    "effective_from": resume, "available_from": resume,
                    "reason": "resume", "source": "TEJ 暫停交易",
                })
    rows.sort(key=lambda r: (r["stock_id"], r["effective_from"], r["status"]))
    blob = "\n".join("|".join(str(r[k]) for k in
                              ("stock_id", "status", "effective_from",
                               "available_from", "reason")) for r in rows)
    dates = [r["effective_from"] for r in rows]
    contract = SourceContract(
        name="b0_security_status", kind="security_status",
        importer_version=IMPORTER_VERSION,
        content_sha256=_sha(blob), schema_sha256=_sha(
            "stock_id|status|effective_from|available_from|reason|source"),
        date_min=min(dates), date_max=max(dates),
        has_effective_dates=True,
        has_availability_semantics=True,
        is_current_snapshot=False,
        availability_convention=(
            "available_from = 年月日 (first affected session). O-E-1 then lets a "
            "record explain only sessions STRICTLY AFTER it, so a status filed "
            "after the close can never account for that day's missing price."),
    )
    return rows, contract, semantics_count, dropped


def main():
    sessions, cal_contract = build_calendar()
    status_rows, status_contract, semantics_count, dropped = build_status()

    cal = TradingCalendar(sessions, cal_contract)
    table = SecurityStatusTable(
        [StatusRecord(**{k: r[k] for k in
                         ("stock_id", "status", "effective_from",
                          "available_from", "reason", "source")})
         for r in status_rows], status_contract)

    print(f"calendar : {len(cal)} sessions {cal.coverage[0]} .. {cal.coverage[1]}")
    print(f"status   : {len(table)} records / {table.securities} securities "
          f"({status_contract.date_min} .. {status_contract.date_max})")
    print(f"pit safety: calendar={cal_contract.pit_safety()} "
          f"status={status_contract.pit_safety()}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_CAL, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["session"])
        w.writerows([[s] for s in sessions])
    with open(OUT_STATUS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(status_rows[0]))
        w.writeheader()
        w.writerows(status_rows)

    prov = market_state_provenance(cal_contract, status_contract)
    payload = {
        "study": "O-E market-state sources",
        "read_only": True, "performance_computed": False,
        "contracts": [
            {**c.__dict__, "pit_safety": c.pit_safety()}
            for c in (cal_contract, status_contract)],
        "b21_dataset_provenance": [p.__dict__ for p in prov],
        "outputs": {"calendar": os.path.relpath(OUT_CAL, REPO).replace("\\", "/"),
                    "status": os.path.relpath(OUT_STATUS, REPO).replace("\\", "/")},
        "status_breakdown": {
            s: sum(1 for r in status_rows if r["status"] == s)
            for s in (STATUS_SUSPENDED, STATUS_DELISTED, STATUS_LISTED)},
        "event_semantics": dict(semantics_count),
        "rows_that_produced_no_status": len(dropped),
        "rows_that_produced_no_status_by_semantics": dict(
            collections.Counter(d["semantics"] for d in dropped)),
        "uninterpretable_reasons": sorted(
            {d["reason"][:60] for d in dropped if d["semantics"] == "UNKNOWN"}),
    }
    with open(OUT_CONTRACTS, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("status breakdown:", payload["status_breakdown"])
    print("event semantics :", payload["event_semantics"])
    print("no status (fail closed):", payload["rows_that_produced_no_status"],
          payload["rows_that_produced_no_status_by_semantics"])
    print("wrote", os.path.relpath(OUT_CAL, REPO))
    print("wrote", os.path.relpath(OUT_STATUS, REPO))
    print("wrote", os.path.relpath(OUT_CONTRACTS, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
