# -*- coding: utf-8 -*-
"""Official Exchange Valuation Lineage Audit — analysis step (READ-ONLY).

Compares, per decision month 2019-01 .. 2026-03:

    NEEDED    securities with an observed price on the as-of session, taken ONLY
              from the admissible 2019+ corpus (股價 2019-2022.zip /
              股價2023-20260817.zip). The quarantined corpus is never opened.
    COVERED   securities for which an OFFICIAL exchange published a usable
              股價淨值比 on that session — TWSE for 上市, TPEx for 上櫃.

Board membership is not inferred from a current snapshot: a security is 上市 on
session s because TWSE published it on s, and 上櫃 because TPEx did. That is
point-in-time by construction, which is the property §2.3 shows a current-snapshot
classification does not have.

The comparison bar is NOT 100%. The existing pre-2019 PBR_TSE lineage carries a
real NA rate of its own — measured at ~6-7% of priced securities across the 2018
month-ends — because a security with non-positive book value has no meaningful
PBR. §4.1 complete-case already absorbs that. So the question this answers is
whether official coverage is COMPARABLE to the frozen lineage, not whether it is
total.

Decides nothing. `value_pbr_lineage_2019plus` stays open until a ruling.

    python research/b0_valuation_lineage_audit/analyse_coverage.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

RAW_DIR = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                       os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
NEEDED = r"C:\tmp\b0audit\needed_per_session.json"
COVERAGE_RAW = os.path.join(HERE, "official_pbr_coverage_raw.json")
OUT = os.path.join(HERE, "official_pbr_coverage_report.json")

# Measured on the admissible pre-2019 lineage (2018 month-ends, yearly export).
PRE2019_BASELINE = {
    "sessions": 12,
    "priced_min": 1781, "priced_max": 1796,
    "with_pbr_tse_min": 1657, "with_pbr_tse_max": 1692,
    "coverage_min": round(1657 / 1781, 4), "coverage_max": round(1692 / 1796, 4),
}


def _ids(prefix: str, sess: str) -> set[str]:
    p = os.path.join(RAW_DIR, f"{prefix}_ids_{sess}.json")
    if not os.path.exists(p):
        return set()
    return set(json.load(open(p)))


def main() -> None:
    needed = json.load(open(NEEDED))
    raw = json.load(open(COVERAGE_RAW, encoding="utf-8"))

    rows, fetch_failures = [], []
    for m in raw["months"]:
        sess = m["as_of_session"]
        need = set(needed.get(sess, []))
        twse, tpex = _ids("twse", sess), _ids("tpex", sess)
        if m.get("twse_stat") != "OK" or m.get("tpex_stat") != "OK":
            fetch_failures.append({"decision_month": m["decision_month"],
                                   "session": sess,
                                   "twse_stat": m.get("twse_stat"),
                                   "tpex_stat": m.get("tpex_stat")})
        union = twse | tpex
        covered = need & union
        gap = sorted(need - union)
        rows.append({
            "decision_month": m["decision_month"],
            "decision_date": m["decision_date"],
            "as_of_session": sess,
            "needed": len(need),
            "covered_total": len(covered),
            "covered_twse_listed": len(need & twse),
            "covered_tpex_otc": len(need & tpex),
            "in_both_boards": len(need & twse & tpex),
            "gap": len(gap),
            "coverage_rate": round(len(covered) / len(need), 4) if need else None,
            "gap_sample": gap[:10],
        })

    cov = [r["coverage_rate"] for r in rows if r["coverage_rate"] is not None]
    gaps = [r["gap"] for r in rows]
    # Which securities are persistently missing, and how often.
    from collections import Counter
    miss = Counter()
    for m in raw["months"]:
        sess = m["as_of_session"]
        need = set(needed.get(sess, []))
        miss.update(need - (_ids("twse", sess) | _ids("tpex", sess)))

    report = {
        "audit": "official_exchange_valuation_lineage",
        "question": ("can TWSE (上市) + TPEx (上櫃) official 股價淨值比 cover every "
                     "B0 decision month 2019-01..2026-03?"),
        "sources_are_official_exchanges": True,
        "used_pbr_tej": False,
        "used_quarantined_corpus": False,
        "b0_modified": False,
        "decision_or_performance_computed": False,
        "months_audited": len(rows),
        "fetch_failures": fetch_failures,
        "coverage_rate_min": min(cov) if cov else None,
        "coverage_rate_max": max(cov) if cov else None,
        "coverage_rate_median": round(statistics.median(cov), 4) if cov else None,
        "gap_min": min(gaps) if gaps else None,
        "gap_max": max(gaps) if gaps else None,
        "gap_median": statistics.median(gaps) if gaps else None,
        "pre2019_lineage_baseline": PRE2019_BASELINE,
        "persistently_missing_top20": [
            {"stock_id": s, "months_missing": n} for s, n in miss.most_common(20)],
        "securities_ever_missing": len(miss),
        "months": rows,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"months audited        : {report['months_audited']}")
    print(f"fetch failures        : {len(fetch_failures)}")
    print(f"coverage rate min/med/max : {report['coverage_rate_min']} / "
          f"{report['coverage_rate_median']} / {report['coverage_rate_max']}")
    print(f"gap min/med/max       : {report['gap_min']} / {report['gap_median']} / "
          f"{report['gap_max']}")
    print(f"pre-2019 lineage cov  : {PRE2019_BASELINE['coverage_min']} .. "
          f"{PRE2019_BASELINE['coverage_max']}")
    print(f"securities ever missing: {report['securities_ever_missing']}")
    print("wrote", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
