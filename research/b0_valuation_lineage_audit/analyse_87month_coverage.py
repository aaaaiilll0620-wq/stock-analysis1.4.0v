# -*- coding: utf-8 -*-
"""Per-month coverage of the official exchange PBR harvest — READ-ONLY.

For each of the 87 frozen decision months 2019-01 .. 2026-03 this reports the
eight quantities the audit was asked for, and it keeps the NA classes apart,
because they are different facts about the same missing number:

    required               securities with an observed price on the as-of
                           session, from the ADMISSIBLE 2019+ corpus only
    twse_rows / tpex_rows  rows the exchange published that session
    covered                required securities with a usable official PBR
    explicit_na            required, published on a board, ratio shown as `-`
    off_board_unpublished  required, on neither board's report that session
    transport_unresolved   sessions where a host never answered
    coverage_rate          covered / required

Board membership is point-in-time BY CONSTRUCTION: a security counts as 上市 on
session s because TWSE published it on s, and 上櫃 because TPEx did. The current
`上市別` label is never read — §2.3 shows it is rewritten on delisting, so
back-filling history from it is look-ahead.

The bar is not 100%: the frozen pre-2019 lineage carries its own NA rate, and
§4.1 complete-case already absorbs one of that size. Decides nothing.

    python research/b0_valuation_lineage_audit/analyse_87month_coverage.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from harvest_official_pbr import decision_sessions  # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
NORM_DIR = os.path.join(ART, "norm")
NEEDED = os.path.join(ART, "needed_per_session.json")
OUT = os.path.join(HERE, "official_pbr_87month_report.json")
OUT_CSV = os.path.join(HERE, "official_pbr_87month_table.csv")

# Measured on the admissible pre-2019 lineage (2018 month-ends, yearly export).
PRE2019_BASELINE = {
    "sessions": 12, "priced_min": 1781, "priced_max": 1796,
    "with_pbr_tse_min": 1657, "with_pbr_tse_max": 1692,
    "coverage_min": round(1657 / 1781, 4), "coverage_max": round(1692 / 1796, 4),
}


def load_norm(src: str, sess: str) -> dict | None:
    p = os.path.join(NORM_DIR, "%s_%s.json" % (src, sess))
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def classify_gap(uncovered_by_session: dict, first_seen: dict, last_seen: dict,
                 sessions: list[str]) -> dict:
    """What KIND of absence each uncovered security-month is.

    Every label is derived from the exchanges' own reports across the harvested
    span — never from a current-snapshot label. `later_on_board` says the report
    first lists that security after this session, `earlier_on_board` that it
    stopped being listed, `never_on_board` that no session in the whole harvest
    ever carried it (ETFs, TDRs and emerging-board securities have no official
    PE/PBR report at all).
    """
    out = Counter()
    per_security = Counter()
    for sess, ids in uncovered_by_session.items():
        for sid in ids:
            fs, ls = first_seen.get(sid), last_seen.get(sid)
            if fs is None:
                label = "never_on_board"
            elif sess < fs:
                label = "later_on_board"
            elif sess > ls:
                label = "earlier_on_board"
            else:
                label = "gap_while_on_board"
            out[label] += 1
            per_security[(sid, label)] += 1
    shapes = Counter()
    for sid, label in per_security:
        if label != "never_on_board":
            continue
        shapes["etf_or_fund_00xx" if sid.startswith("00")
               else "five_digit_or_longer" if len(sid) > 4
               else "four_digit"] += 1
    return {"security_months_by_kind": dict(out),
            "never_on_board_security_shapes": dict(shapes)}


def main() -> None:
    needed = json.load(open(NEEDED, encoding="utf-8"))
    months = decision_sessions("2019-01", "2026-03")

    rows, unresolved, never_covered = [], [], Counter()
    board_only_counts = Counter()
    uncovered_by_session: dict[str, set] = {}
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    for _ym, _dd, sess in months:
        for src in ("twse", "tpex"):
            rec = load_norm(src, sess)
            for sid in (rec or {}).get("raw", {}):
                first_seen.setdefault(sid, sess)
                last_seen[sid] = sess
    for ym, ddate, sess in months:
        req = set(needed.get(sess, []))
        t = load_norm("twse", sess)
        p = load_norm("tpex", sess)

        miss_src = [s for s, rec in (("twse", t), ("tpex", p)) if rec is None]
        if miss_src:
            unresolved.append({"decision_month": ym, "as_of_session": sess,
                               "sources_without_an_answer": miss_src})

        t_ids = set((t or {}).get("raw", {}))
        p_ids = set((p or {}).get("raw", {}))
        t_val = set((t or {}).get("values", {}))
        p_val = set((p or {}).get("values", {}))

        published = t_ids | p_ids
        with_value = t_val | p_val
        covered = req & with_value
        na_explicit = (req & published) - with_value
        off_board = req - published

        uncovered_by_session[sess] = req - with_value
        board_only_counts["twse_only"] += len(req & t_ids - p_ids)
        board_only_counts["tpex_only"] += len(req & p_ids - t_ids)
        board_only_counts["both_boards"] += len(req & t_ids & p_ids)
        never_covered.update(req - with_value)

        rows.append({
            "decision_month": ym,
            "decision_date": ddate,
            "as_of_session": sess,
            "required": len(req),
            "twse_state": (t or {}).get("state", "NOT_HARVESTED"),
            "tpex_state": (p or {}).get("state", "NOT_HARVESTED"),
            "twse_rows": (t or {}).get("rows", 0),
            "tpex_rows": (p or {}).get("rows", 0),
            "twse_values": (t or {}).get("n_values", 0),
            "tpex_values": (p or {}).get("n_values", 0),
            "covered": len(covered),
            "covered_via_twse": len(req & t_val),
            "covered_via_tpex": len(req & p_val),
            # PIT board membership, from the exchanges' own reports for THIS
            # session — never from the current 上市別 label.
            "pit_on_twse_board": len(req & t_ids),
            "pit_on_tpex_board": len(req & p_ids),
            "pit_on_both_boards": len(req & t_ids & p_ids),
            "explicit_na": len(na_explicit),
            "off_board_unpublished": len(off_board),
            "transport_unresolved": len(miss_src),
            "coverage_rate": round(len(covered) / len(req), 4) if req else None,
            "twse_discloses_vintage": bool((t or {}).get("has_vintage_field")),
            "tpex_discloses_vintage": bool((p or {}).get("has_vintage_field")),
        })

    complete = [r for r in rows if r["transport_unresolved"] == 0]
    cov = [r["coverage_rate"] for r in complete if r["coverage_rate"] is not None]

    report = {
        "audit": "official_exchange_pbr_full_87_month_harvest",
        "window": {"first": months[0][0], "last": months[-1][0],
                   "months": len(months)},
        "definitions": {
            "required": ("securities with an observed price on the as-of session "
                         "in the admissible 2019+ corpus"),
            "covered": "required securities with a numeric official PBR on either board",
            "explicit_na": ("required, listed in a board's report for that session, "
                            "ratio published as `-` / `N/A`"),
            "off_board_unpublished": ("required, absent from both boards' reports "
                                      "for that session"),
            "transport_unresolved": ("sources with no cached answer at report time — "
                                     "a transport failure that never resolved, or a "
                                     "session never attempted. It is NOT evidence "
                                     "that the exchange lacks the data"),
        },
        "months_fully_harvested": len(complete),
        "months_with_unresolved_transport": len(unresolved),
        "unresolved": unresolved,
        "coverage_rate_min": min(cov) if cov else None,
        "coverage_rate_median": round(statistics.median(cov), 4) if cov else None,
        "coverage_rate_max": max(cov) if cov else None,
        "required_min": min(r["required"] for r in rows),
        "required_max": max(r["required"] for r in rows),
        "explicit_na_min": min(r["explicit_na"] for r in complete) if complete else None,
        "explicit_na_max": max(r["explicit_na"] for r in complete) if complete else None,
        "off_board_min": min(r["off_board_unpublished"] for r in complete) if complete else None,
        "off_board_max": max(r["off_board_unpublished"] for r in complete) if complete else None,
        "pit_board_membership_security_months": dict(board_only_counts),
        "board_membership_source": (
            "presence in the exchange's own report for that session; the current "
            "上市別 label is never read"),
        "pre2019_lineage_baseline": PRE2019_BASELINE,
        "gap_taxonomy": classify_gap(uncovered_by_session, first_seen, last_seen,
                                     [s for _, _, s in months]),
        "securities_ever_uncovered": len(never_covered),
        "uncovered_top20": [{"stock_id": s, "months": n}
                            for s, n in never_covered.most_common(20)],
        "needed_per_session_sha256": hashlib.sha256(
            open(NEEDED, "rb").read()).hexdigest(),
        "used_pbr_tej": False,
        "used_quarantined_corpus": False,
        "b0_modified": False,
        "decision_or_performance_computed": False,
        "months": rows,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    cols = ["decision_month", "as_of_session", "required", "twse_rows", "tpex_rows",
            "covered", "explicit_na", "off_board_unpublished",
            "transport_unresolved", "coverage_rate", "twse_state", "tpex_state"]
    # lineterminator is explicit: csv defaults to CRLF, and the repo is `* text
    # eol=lf` with a CRLF->LF migration ledger, so the default would dirty it.
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("months                : %d (%s .. %s)" % (
        len(months), months[0][0], months[-1][0]))
    print("fully harvested       : %d" % len(complete))
    print("unresolved transport  : %d" % len(unresolved))
    print("coverage min/med/max  : %s / %s / %s" % (
        report["coverage_rate_min"], report["coverage_rate_median"],
        report["coverage_rate_max"]))
    print("explicit NA range     : %s .. %s" % (
        report["explicit_na_min"], report["explicit_na_max"]))
    print("off-board range       : %s .. %s" % (
        report["off_board_min"], report["off_board_max"]))
    print("wrote", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
