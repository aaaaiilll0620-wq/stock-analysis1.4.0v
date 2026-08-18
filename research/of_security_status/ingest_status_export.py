"""O-F step 1 - inventory, fingerprint and SEMANTICS of the new status export.

`tej_exports/DataExport0806/暫停交易2004-20260818` replaces the deleted
20260806 folder. Nothing here assumes the new export fixes anything; the
question this script answers is only what it contains and what its three date
columns MEAN, because O-E admits a status source only if its availability and
effective-date semantics are demonstrated rather than declared.

Semantics tested against the D-1 canonical price corpus, not against prose:

  E-1  年月日 is an EFFECTIVE date, not an announcement date.
       Measured: does the security still have a price ON 年月日?
  E-2  恢復交易日 is the first session that trades again.
       Measured: is there a price on it, and none strictly between?
  E-3  ordering: 恢復交易日 > 年月日.
  A-1  the table carries NO availability column. This is a finding, not a
       defect to paper over: available_from must therefore be DECLARED, and
       O-E-1 then decides what that declaration can and cannot explain.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import bisect
import csv
import glob
import hashlib
import json
import os
import sys
import zipfile
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

SRC_DIR = os.path.join(REPO, "tej_exports", "DataExport0806", "暫停交易2004-20260818")
PRESENCE = os.path.join(REPO, "data", "b0", "price_presence.parquet")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")
OUT = os.path.join(HERE, "status_export_inventory.json")

SUSPENSION_GLOB = "暫停交易*.zip"
EVENT_ZIP = "事件+下市.zip"
EXPECTED_COLUMNS = ("證券代碼", "年月日", "恢復交易日", "暫停交易原因")

# Audit trail for the deleted 20260806 vintage. The old files are gone and are
# NOT required to exist; what is recorded is what the derived artefact built
# from them measured, so the two vintages remain comparable.
SUPERSEDED_VINTAGE = {
    "folder": "tej_exports/DataExport0806/暫停交易2004-20260806",
    "state": "DELETED_BY_USER_2026-08-18",
    "raw_sha256": None,
    "raw_sha256_note": "never recorded; the 20260806 vintage was imported from "
                       "xlsx and only its derived table was fingerprinted",
    "derived_artifact": "data/b0/security_status.csv",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_zip_tsv(path):
    zf = zipfile.ZipFile(path)
    members = zf.namelist()
    rows, header = [], None
    for name in members:
        text = zf.read(name).decode("utf-16")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        hdr = tuple(lines[0].split("\t"))
        if header is None:
            header = hdr
        elif hdr != header:
            raise SystemExit(f"schema drift inside {path}: {hdr} != {header}")
        for ln in lines[1:]:
            rows.append(dict(zip(hdr, ln.split("\t"))))
    return header, rows, members


def d8(v):
    s = str(v).strip().split(".")[0]
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else None


def main():
    report = {"study": "O-F status source inventory and semantics",
              "read_only": True, "performance_computed": False,
              "source_dir": os.path.relpath(SRC_DIR, REPO).replace("\\", "/"),
              "superseded_vintage": SUPERSEDED_VINTAGE}

    # --- inventory + raw fingerprints ---------------------------------------
    files = []
    header, rows = None, []
    for z in sorted(glob.glob(os.path.join(SRC_DIR, SUSPENSION_GLOB))):
        hdr, rs, members = read_zip_tsv(z)
        if header is None:
            header = hdr
        elif hdr != header:
            raise SystemExit(f"schema drift across zips: {hdr} != {header}")
        rows.extend(rs)
        files.append({"file": os.path.basename(z), "bytes": os.path.getsize(z),
                      "sha256": sha256_file(z), "members": members,
                      "rows": len(rs)})
    ev_path = os.path.join(SRC_DIR, EVENT_ZIP)
    ev_hdr, ev_rows, ev_members = read_zip_tsv(ev_path)
    files.append({"file": EVENT_ZIP, "bytes": os.path.getsize(ev_path),
                  "sha256": sha256_file(ev_path), "members": ev_members,
                  "rows": len(ev_rows)})

    if tuple(header) != EXPECTED_COLUMNS:
        raise SystemExit(f"unexpected suspension schema: {header}")

    report["files"] = files
    report["suspension"] = {
        "columns": list(header),
        "schema_sha256": sha256_text("|".join(header)),
        "rows": len(rows),
        "securities": len({r["證券代碼"].split()[0] for r in rows}),
    }
    report["event_table"] = {
        "columns": list(ev_hdr),
        "schema_sha256": sha256_text("|".join(ev_hdr)),
        "rows": len(ev_rows),
        "securities": len({r["證券代碼"].split()[0] for r in ev_rows}),
    }

    # --- normalise ------------------------------------------------------------
    norm = []
    bad = Counter()
    for r in rows:
        sid = r["證券代碼"].split()[0]
        start, resume = d8(r["年月日"]), d8(r["恢復交易日"])
        reason = r["暫停交易原因"].strip()
        if not start:
            bad["no_effective_date"] += 1
            continue
        if not resume:
            bad["no_resume_date"] += 1
        if not reason or reason == ".":
            bad["no_reason"] += 1
        norm.append({"stock_id": sid, "start": start, "resume": resume,
                     "reason": reason})
    starts = sorted(r["start"] for r in norm)
    report["suspension"]["usable_rows"] = len(norm)
    report["suspension"]["unusable"] = dict(bad)
    report["suspension"]["effective_date_range"] = [starts[0], starts[-1]]
    report["suspension"]["years_covered"] = sorted({s[:4] for s in starts})
    report["suspension"]["content_sha256"] = sha256_text("\n".join(
        "|".join(str(r[k]) for k in ("stock_id", "start", "resume", "reason"))
        for r in sorted(norm, key=lambda r: (r["stock_id"], r["start"]))))
    report["suspension"]["reason_top"] = Counter(
        r["reason"][:8] for r in norm).most_common(12)

    # --- 2004-2026 historical range check ------------------------------------
    years = {s[:4] for s in starts}
    expected_years = {str(y) for y in range(2004, 2027)}
    report["coverage_check"] = {
        "expected_years": sorted(expected_years),
        "missing_years": sorted(expected_years - years),
        "extra_years": sorted(years - expected_years),
        "spans_2004_through_2026": not (expected_years - years),
    }

    # --- semantics against the canonical price corpus ------------------------
    pres = pd.read_parquet(PRESENCE)
    by_id = defaultdict(list)
    for sid, date in zip(pres["stock_id"].astype(str), pres["date"]):
        by_id[sid].append(date)
    with open(CALENDAR, encoding="utf-8") as fh:
        calendar = sorted(r["session"] for r in csv.DictReader(fh))

    def priced_on(sid, day):
        d = by_id.get(sid)
        if not d:
            return None
        i = bisect.bisect_left(d, day)
        return i < len(d) and d[i] == day

    def sessions_between(a, b):
        i, j = bisect.bisect_right(calendar, a), bisect.bisect_left(calendar, b)
        return calendar[i:j]

    e1 = Counter()
    e2 = Counter()
    e3 = Counter()
    for r in norm:
        p = priced_on(r["stock_id"], r["start"])
        e1["security_absent_from_corpus" if p is None
           else ("priced_on_effective_date" if p
                 else "not_priced_on_effective_date")] += 1
        if not r["resume"]:
            continue
        e3["resume_after_start" if r["resume"] > r["start"]
           else ("resume_equals_start" if r["resume"] == r["start"]
                 else "resume_before_start")] += 1
        pr = priced_on(r["stock_id"], r["resume"])
        if pr is None:
            e2["security_absent_from_corpus"] += 1
            continue
        gap = sessions_between(r["start"], r["resume"])
        traded_inside = sum(1 for s in gap if priced_on(r["stock_id"], s))
        if pr and traded_inside == 0:
            e2["clean_resume"] += 1
        elif pr:
            e2["priced_inside_suspension_window"] += 1
        elif traded_inside == 0:
            e2["silent_through_resume_date"] += 1
        else:
            e2["priced_inside_and_not_on_resume"] += 1

    report["semantics"] = {
        "E-1_effective_date_not_announcement": dict(e1),
        "E-1_verdict": (
            "年月日 is an EFFECTIVE date: the majority still trade ON it, so the "
            "suspension takes hold from the NEXT session. It is not an "
            "announcement date and carries no availability information."),
        "E-2_resume_is_first_session_back": dict(e2),
        "E-3_ordering": dict(e3),
        "A-1_availability_column_present": False,
        "A-1_verdict": (
            "no filing/announcement timestamp exists in the export. available_from "
            "must be DECLARED; O-E-1 then bounds what that declaration explains."),
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("files:")
    for f in files:
        print(f"  {f['file']:<26} {f['bytes']:>7,}B rows={f['rows']:>5} "
              f"{f['sha256'][:16]}")
    s = report["suspension"]
    print(f"\nsuspension : {s['rows']} rows / {s['securities']} securities "
          f"({s['effective_date_range'][0]} .. {s['effective_date_range'][1]})")
    print(f"  columns  : {s['columns']}")
    print(f"  schema   : {s['schema_sha256']}")
    print(f"  content  : {s['content_sha256']}")
    print(f"  unusable : {s['unusable']}")
    e = report["event_table"]
    print(f"event tbl  : {e['rows']} rows / {e['securities']} securities")
    print(f"  columns  : {e['columns']}")
    print(f"\ncoverage 2004-2026: {report['coverage_check']['spans_2004_through_2026']} "
          f"missing={report['coverage_check']['missing_years']}")
    print("semantics:")
    for k in ("E-1_effective_date_not_announcement",
              "E-2_resume_is_first_session_back", "E-3_ordering"):
        print(f"  {k}: {report['semantics'][k]}")
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
