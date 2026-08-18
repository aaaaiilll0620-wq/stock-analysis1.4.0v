# -*- coding: utf-8 -*-
"""C-51/R5 · seal the official bonus-share panel. READ-ONLY with respect to A.

The pipeline the ruling requires, end to end:

    official TWSE/TPEx payloads
      -> pinned parser/importer            (BONUS_PARSER_VERSION)
      -> canonical bonus-rate event panel  (data/b0/bonus_share_panel.parquet)
      -> content/schema/source hashes      (receipt + BonusShareSourceContract)
      -> share-unit adjustment producer    (core.b0_share_unit_adjustment)

Every canonical `stock_dividend` event the 141-period lookback can reach gets
exactly one disposition — OFFICIAL_BONUS_RATE / NOT_APPLICABLE_TO_B0_MARKET_HISTORY
/ UNRESOLVED — and an UNRESOLVED one never carries a number.

No performance quantity is computed and no live request is made: the builder
reads the harvested payloads and aborts if one it needs is not on disk.

    python research/b0_materializer/build_bonus_share_panel.py
"""
from __future__ import annotations

import collections
import csv
import glob
import hashlib
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_bonus_share_source import (              # noqa: E402
    BONUS_IMPORTER_VERSION, BONUS_PARSER_VERSION, BONUS_UNIT,
    CANONICAL_CONVERSION, MATCHED_DISPOSITION, OFFICIAL_BONUS_FIELD,
    OFFICIAL_ENDPOINT, PRE_LISTING_DISPOSITION, UNRESOLVED_DISPOSITION,
    BonusShareSourceContract, assert_bonus_source_admissible,
    assert_no_inferred_multiplier, assert_same_market_effective_event,
    coverage_record, holder_multiplier_from_bonus, is_pre_listing,
    market_effective_session, resolve_disposition,
)
from core.b0_provenance import file_sha256             # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or os.path.join(REPO, "artifacts"),
                   "stock_dividend_multiplier_audit")
RAW = os.path.join(ART, "raw")
OUT = os.path.join(REPO, "data", "b0", "bonus_share_panel.parquet")
RECEIPT = os.path.join(HERE, "bonus_share_panel_receipt.json")
LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")
TODO = os.path.join(ART, "twse_detail_todo.json")

# The union window every 141-period momentum_12_1 / sigma20d lookback reaches.
# P_{t-13} for the first decision month 2014-07 is the 2013-06 month-end session
# (2013-06-28); an event on or before it divides both momentum anchors alike.
WINDOW_FROM, WINDOW_TO = "2013-06-29", "2026-03-31"

TWSE_A = OFFICIAL_BONUS_FIELD["TWSE"]
TPEX_B = OFFICIAL_BONUS_FIELD["TPEx"]


def num(v):
    s = str(v).replace(",", "").strip()
    for tail in ("元／股", "元/股", "股", "元"):
        if s.endswith(tail):
            s = s[: -len(tail)].strip()
    if s in ("", "-", "--", ".", "N/A", "nan", "None"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return None if f != f else f


def _payloads(pattern):
    for path in sorted(glob.glob(os.path.join(RAW, pattern))):
        with open(path, encoding="utf-8") as fh:
            yield json.load(fh)


def official_index():
    """(stock_id, scheduled_date) -> row, from the two range reports.

    The range reports establish contemporaneous BOARD membership: a security is
    on TWSE for a date because the TWSE report for that date carries it. TPEx
    carries the bonus allotment in the range table itself; TWSE needs the
    per-event detail, joined below.
    """
    idx, upstream = {}, {}
    for rec in _payloads("twse_range_*.json"):
        upstream[rec["key"]] = rec["sha256"]
        pay = rec["payload"]
        fields = pay.get("fields") or []
        if not fields:
            continue
        ix = {c: i for i, c in enumerate(fields)}
        for r in pay.get("data") or []:
            s = str(r[ix["資料日期"]])
            d = "%04d-%02d-%02d" % (int(s.split("年")[0]) + 1911,
                                    int(s.split("年")[1].split("月")[0]),
                                    int(s.split("月")[1].split("日")[0]))
            idx[(str(r[ix["股票代號"]]).strip(), d)] = {
                "board": "TWSE", "bonus_per_1000": None,
                "payload_key": rec["key"], "payload_sha256": rec["sha256"]}
    for rec in _payloads("tpex_range_*.json"):
        upstream[rec["key"]] = rec["sha256"]
        for tb in rec["payload"].get("tables") or []:
            fields = tb.get("fields") or []
            if not fields:
                continue
            if TPEX_B not in fields:
                raise SystemExit(
                    "C-51/R5: TPEx schema in %s has no %r column. The disclosure "
                    "changed; the parser version must change with it rather than "
                    "this builder guessing a replacement." % (rec["key"], TPEX_B))
            ix = {c: i for i, c in enumerate(fields)}
            for r in tb.get("data") or []:
                q = str(r[ix["除權息日期"]]).split("/")
                if len(q) != 3 or not q[0].isdigit():
                    continue
                d = "%04d-%02d-%02d" % (int(q[0]) + 1911, int(q[1]), int(q[2]))
                idx[(str(r[ix["代號"]]).strip(), d)] = {
                    "board": "TPEx", "bonus_per_1000": num(r[ix[TPEX_B]]),
                    "payload_key": rec["key"], "payload_sha256": rec["sha256"]}
    return idx, upstream


def twse_detail_index():
    out, upstream = {}, {}
    for rec in _payloads("twse_detail_*.json"):
        upstream[rec["key"]] = rec["sha256"]
        stk, ymd = rec["key"].split("twse_detail_")[1].rsplit("_", 1)
        iso = "%s-%s-%s" % (ymd[:4], ymd[4:6], ymd[6:8])
        pay = rec["payload"]
        fields, data = pay.get("fields") or [], pay.get("data") or []
        if not fields or not data:
            out[(stk, iso)] = {"bonus_per_1000": None,
                               "payload_key": rec["key"],
                               "payload_sha256": rec["sha256"]}
            continue
        hits = [i for i, c in enumerate(fields) if c.strip() == TWSE_A.strip()]
        if len(hits) != 1:
            raise SystemExit(
                "C-51/R5: TWSE detail schema in %s resolves %r to %d columns. "
                "The report changed; the parser version must change with it."
                % (rec["key"], TWSE_A, len(hits)))
        out[(stk, iso)] = {"bonus_per_1000": num(data[0][hits[0]]),
                           "payload_key": rec["key"],
                           "payload_sha256": rec["sha256"]}
    return out, upstream


def main() -> int:
    with open(CALENDAR, encoding="utf-8") as fh:
        sessions = sorted(r["session"] for r in csv.DictReader(fh))
    sset = set(sessions)
    with open(LEDGER, encoding="utf-8") as fh:
        events = [r for r in csv.DictReader(fh)
                  if r["kind"] == "stock_dividend"
                  and WINDOW_FROM <= r["ex_or_effective_date"] <= WINDOW_TO]

    idx, up_range = official_index()
    det, up_det = twse_detail_index()
    by_sec = collections.defaultdict(set)
    for sid, d in idx:
        by_sec[sid].add(d)

    # R3 · which official row, if any, describes this ledger event. Exact key
    # first; then the closed-market normalisation, which is checked by the
    # normative module rather than re-implemented here.
    def official_for(sid, ex):
        if (sid, ex) in idx:
            return ex
        for sched in sorted(by_sec.get(sid, ())):
            if sched in sset or sched >= ex:
                continue
            try:
                assert_same_market_effective_event(sched, ex, sessions)
            except Exception:
                continue
            if market_effective_session(sched, sessions) == ex:
                return sched
        return None

    missing_detail, rows = [], []
    for ev in events:
        sid, ex = ev["stock_id"], ev["ex_or_effective_date"]
        sched = official_for(sid, ex)
        if sched is not None and idx[(sid, sched)]["board"] == "TWSE" \
                and (sid, sched.replace("-", "")) not in {
                    (a, b) for a, b in ((k[0], k[1].replace("-", ""))
                                        for k in det)}:
            missing_detail.append([sid, sched.replace("-", "")])
    if missing_detail:
        with open(TODO, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(missing_detail, fh, ensure_ascii=False)
        raise SystemExit(
            "C-51/R5: %d TWSE detail payloads this panel needs are not on disk. "
            "They were written to %s; run the harvester "
            "(B0_SDM_LAYER=twse_detail) and re-run this builder. Nothing was "
            "sealed." % (len(missing_detail), os.path.relpath(TODO, REPO)))

    for ev in events:
        sid, ex = ev["stock_id"], ev["ex_or_effective_date"]
        sched = official_for(sid, ex)
        board = bonus = pkey = psha = None
        if sched is not None:
            row = idx[(sid, sched)]
            board, pkey, psha = row["board"], row["payload_key"], row["payload_sha256"]
            if board == "TWSE":
                d = det[(sid, sched)]
                bonus, pkey, psha = d["bonus_per_1000"], d["payload_key"], d["payload_sha256"]
            else:
                bonus = row["bonus_per_1000"]
            if bonus is not None and bonus <= 0:
                # An official row that says "no bonus" is not a multiplier of 1
                # waiting to be applied; it contradicts the ledger's classification
                # of the event and must not be silently turned into one.
                bonus = None
        prior = [d for d in by_sec.get(sid, ()) if d < ex]
        pre = is_pre_listing(ex, prior)
        disp = resolve_disposition(official_bonus_per_1000=bonus, pre_listing=pre)
        mult = holder_multiplier_from_bonus(bonus) if disp == MATCHED_DISPOSITION else None
        assert_no_inferred_multiplier(disp, mult)
        rows.append({
            "stock_id": sid,
            "official_scheduled_ex_right_date": sched,
            "market_effective_session": ex,
            "board": board,
            "source_endpoint": OFFICIAL_ENDPOINT[board] if board else None,
            "payload_key": pkey,
            "payload_sha256": psha,
            "bonus_shares_per_1000": bonus,
            "holder_multiplier": mult,
            "disposition": disp,
            # Carried, not folded into the disposition. R2's NOT_APPLICABLE is
            # about B0 having no market history to adjust; the ledger's own
            # NOT_RECONSTRUCTIBLE verdict ("年月日 is a registration stamp") is a
            # different reason for arriving there, and collapsing the two would
            # make the panel claim more than it knows.
            "ledger_reconstructibility": ev["reconstructibility"],
            "parser_version": BONUS_PARSER_VERSION,
        })

    df = pd.DataFrame(rows).sort_values(
        ["stock_id", "market_effective_session"]).reset_index(drop=True)
    df.to_parquet(OUT, index=False)

    upstream = {**up_range, **up_det}
    manifest = "".join("%s:%s\n" % (k, upstream[k]) for k in sorted(upstream))
    schema = "|".join("%s:%s" % (c, df[c].dtype) for c in df.columns)
    counts = collections.Counter(df.disposition)
    contract = BonusShareSourceContract(
        name="b0_bonus_share_20260819",
        endpoints=OFFICIAL_ENDPOINT,
        importer_version=BONUS_IMPORTER_VERSION,
        parser_version=BONUS_PARSER_VERSION,
        schema_sha256=hashlib.sha256(schema.encode()).hexdigest(),
        content_sha256=file_sha256(OUT),
        upstream_manifest_sha256=hashlib.sha256(manifest.encode()).hexdigest(),
        upstream_sha256=upstream,
        date_min=str(df.market_effective_session.min()),
        date_max=str(df.market_effective_session.max()),
        events_total=len(df),
        events_matched=counts[MATCHED_DISPOSITION],
        events_not_applicable=counts[PRE_LISTING_DISPOSITION],
        events_unresolved=counts[UNRESOLVED_DISPOSITION],
        securities=int(df.stock_id.nunique()),
        live_fetch=False,
    )
    assert_bonus_source_admissible(contract)

    receipt = {
        "artefact": "data/b0/bonus_share_panel.parquet",
        "builder": "research/b0_materializer/build_bonus_share_panel.py",
        "clause": "C-51 R1-R5 · official exchange bonus-share holder multiplier",
        "bytes": os.path.getsize(OUT),
        "content_sha256": contract.content_sha256,
        "schema_sha256": contract.schema_sha256,
        "schema": schema,
        "importer_version": BONUS_IMPORTER_VERSION,
        "parser_version": BONUS_PARSER_VERSION,
        "bonus_unit": BONUS_UNIT,
        "conversion": CANONICAL_CONVERSION,
        "live_fetch": False,
        "endpoints": dict(OFFICIAL_ENDPOINT),
        "upstream_manifest_sha256": contract.upstream_manifest_sha256,
        "upstream_payloads": len(upstream),
        "upstream_sha256": upstream,
        "coverage": coverage_record(contract),
        "by_board": {k: int(v) for k, v in
                     collections.Counter(df[df.disposition == MATCHED_DISPOSITION]
                                         .board.dropna()).items()},
        "date_normalized_events": int(
            (df.official_scheduled_ex_right_date.notna() &
             (df.official_scheduled_ex_right_date != df.market_effective_session)
             ).sum()),
        # What the two non-matched dispositions are actually made of, so that a
        # reader does not have to take "not applicable" on trust.
        "disposition_by_ledger_reconstructibility": {
            "%s|%s" % (d, r): int(n) for (d, r), n in
            collections.Counter(zip(df.disposition,
                                    df.ledger_reconstructibility)).items()},
        "performance_computed": False,
    }
    with open(RECEIPT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=1, sort_keys=True)

    print("rows            :", len(df))
    print("securities      :", contract.securities)
    print("coverage        :", coverage_record(contract))
    print("by board        :", receipt["by_board"])
    print("date-normalized :", receipt["date_normalized_events"])
    print("content sha256  :", contract.content_sha256)
    print("upstream manifest sha256:", contract.upstream_manifest_sha256)
    print("wrote", os.path.relpath(OUT, REPO), "and", os.path.relpath(RECEIPT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
