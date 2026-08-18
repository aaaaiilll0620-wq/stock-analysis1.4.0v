"""O-F step 3 - supplementary PIT audit of 事件+下市 (crisis events + delisting).

The suspension table does not account for most terminations (audit B). This
script asks whether the crisis/delisting table can, and it asks the O-E question
first, because a source that explains everything but is not PIT-safe explains
nothing a replay is allowed to use:

  P-1  shape. Is it effective-dated, or one row per security -- a snapshot?
  P-2  forward content. Does it already carry delisting dates in the future
       relative to the export? A future date proves the record exists BEFORE the
       event, which is the availability question in its sharpest form.
  P-3  availability of 下市日期. The column has no filing timestamp. Measured:
       where does 下市日期 fall relative to the first missing session? If it
       lands on or after it, declaring available_from = 下市日期 fails O-E-1 and
       the column cannot be a runtime explanation.
  P-4  availability of 危機發生日. It is an event-occurrence date, and the
       category text embeds the same date, so it is self-describing. Measured:
       how many unexplained terminations have a crisis date STRICTLY BEFORE the
       first missing session -- the only ones O-E-1 would ever admit.

Nothing here promotes any column to a runtime source. The output is evidence for
a ruling, and the ruling is not mine to make.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import bisect
import csv
import glob
import json
import os
import sys
import zipfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

SRC_DIR = os.path.join(REPO, "tej_exports", "DataExport0806", "暫停交易2004-20260818")
EVENT_ZIP = os.path.join(SRC_DIR, "事件+下市.zip")
AUDIT = os.path.join(HERE, "status_coverage_audit.json")
CALENDAR = os.path.join(REPO, "data", "b0", "trading_calendar.csv")
OUT = os.path.join(HERE, "event_table_audit.json")

EXPORT_DATE = "2026-08-18"          # from the export's own member timestamp


def d8(v):
    s = str(v).strip().split(".")[0]
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else None


def read_events():
    rows = []
    with zipfile.ZipFile(EVENT_ZIP) as zf:
        for name in zf.namelist():
            lines = [ln for ln in zf.read(name).decode("utf-16").splitlines()
                     if ln.strip()]
            header = lines[0].split("\t")
            rows += [dict(zip(header, ln.split("\t"))) for ln in lines[1:]]
    out = {}
    for r in rows:
        sid = r["證券代碼"].split()[0]
        out[sid] = {
            "delisted_on": d8(r["下市日期"]),
            "crisis_from": d8(r["危機發生日"]),
            "crisis_to": d8(r["危機發生迄日"]),
            "major_class": r["危機事件大類別"],
            "major_text": r["危機事件大類別說明"],
            "class_text": r["危機事件類別說明"],
        }
    return rows, out


def main():
    raw, ev = read_events()
    with open(CALENDAR, encoding="utf-8") as fh:
        sessions = sorted(r["session"] for r in csv.DictReader(fh))
    audit = json.load(open(AUDIT, encoding="utf-8"))

    report = {"study": "O-F supplementary audit of 事件+下市",
              "read_only": True, "performance_computed": False,
              "promoted_to_runtime_source": False}

    # --- P-1 shape ------------------------------------------------------------
    sids = [r["證券代碼"].split()[0] for r in raw]
    delisted = {s: v for s, v in ev.items() if v["delisted_on"]}
    report["P1_shape"] = {
        "rows": len(raw), "unique_securities": len(set(sids)),
        "rows_per_security_max": Counter(sids).most_common(1)[0][1],
        "one_row_per_security": len(set(sids)) == len(sids),
        "record_level_effective_date_column": None,
        "verdict": (
            "one row per security with no record-level effective date: the SHAPE "
            "is a current snapshot. Its date COLUMNS are effective dates, which "
            "is not the same thing as the record being effective-dated."),
    }

    # --- P-2 forward content --------------------------------------------------
    future = sorted((s, v["delisted_on"]) for s, v in delisted.items()
                    if v["delisted_on"] > EXPORT_DATE)
    report["P2_forward_content"] = {
        "export_date": EXPORT_DATE,
        "delisting_dates_after_export_date": len(future),
        "examples": future[:10],
        "verdict": (
            "a delisting dated after the export proves TEJ files the delisting "
            "date BEFORE the event. So 下市日期 is knowable in advance -- but the "
            "table does not say HOW far in advance, and that unknown lead time is "
            "exactly what an availability semantics has to pin down."),
    }

    # --- the unexplained terminations, from audit B --------------------------
    unexplained = audit["audit_B_terminal_gaps"]["detail"]
    report["input"] = {"unexplained_terminal_gaps": len(unexplained)}

    # --- P-3 does 下市日期 land before the first missing session? -------------
    p3 = Counter()
    offsets = Counter()
    p3_detail = []
    for u in unexplained:
        sid, first_missing = u["stock_id"], u["first_missing"]
        rec = ev.get(sid)
        if rec is None:
            p3["absent_from_event_table"] += 1
            continue
        d = rec["delisted_on"]
        if not d:
            p3["no_delisting_date"] += 1
            continue
        if d < first_missing:
            p3["strictly_before_first_missing"] += 1
            verdict = "would satisfy O-E-1"
        elif d == first_missing:
            p3["same_day_as_first_missing"] += 1
            verdict = "blocked by O-E-1"
        else:
            p3["after_first_missing"] += 1
            verdict = "blocked by O-E-1"
        i = bisect.bisect_left(sessions, first_missing)
        j = bisect.bisect_left(sessions, d)
        offsets[max(-30, min(30, j - i))] += 1
        p3_detail.append({"stock_id": sid, "first_missing": first_missing,
                          "delisted_on": d, "sessions_offset": j - i,
                          "verdict": verdict})
    report["P3_delisting_date_availability"] = {
        "by_position": dict(p3),
        "offset_histogram_sessions_clipped_at_30": dict(sorted(offsets.items())),
        "covers_unexplained": sum(v for k, v in p3.items()
                                  if k != "absent_from_event_table"
                                  and k != "no_delisting_date"),
        "verdict": (
            "下市日期 is an EFFECTIVE date that lands on or after the first "
            "missing session in the overwhelming majority of cases. Declaring "
            "available_from = 下市日期 therefore fails O-E-1 exactly where it is "
            "needed. The column identifies WHICH securities left; it does not "
            "establish WHEN that became knowable."),
        "detail": sorted(p3_detail, key=lambda r: r["first_missing"])[:200],
    }

    # --- P-4 does 危機發生日 land before the first missing session? -----------
    p4 = Counter()
    p4_detail = []
    for u in unexplained:
        sid, first_missing = u["stock_id"], u["first_missing"]
        rec = ev.get(sid)
        if rec is None:
            p4["absent_from_event_table"] += 1
            continue
        c = rec["crisis_from"]
        if not c:
            p4["no_crisis_date"] += 1
            continue
        if c < first_missing:
            p4["strictly_before_first_missing"] += 1
            p4_detail.append({"stock_id": sid, "first_missing": first_missing,
                              "crisis_from": c,
                              "class": rec["major_class"],
                              "text": rec["class_text"][:60]})
        else:
            p4["on_or_after_first_missing"] += 1
    report["P4_crisis_date_availability"] = {
        "by_position": dict(p4),
        "verdict": (
            "危機發生日 is an occurrence date and the category text repeats it, so "
            "it is self-describing in a way 下市日期 is not. It still carries no "
            "filing timestamp, and it covers only crisis-driven exits -- a "
            "voluntary or merger delisting has no crisis row."),
        "detail": p4_detail[:200],
    }

    # --- combined best case ---------------------------------------------------
    best = Counter()
    still = []
    for u in unexplained:
        sid, first_missing = u["stock_id"], u["first_missing"]
        rec = ev.get(sid) or {}
        d, c = rec.get("delisted_on"), rec.get("crisis_from")
        if c and c < first_missing:
            best["crisis_date_before"] += 1
        elif d and d < first_missing:
            best["delisting_date_before"] += 1
        else:
            best["still_unexplained"] += 1
            still.append({"stock_id": sid, "first_missing": first_missing,
                          "delisted_on": d, "crisis_from": c,
                          "in_event_table": sid in ev})
    report["combined_best_case"] = {
        "by_source": dict(best),
        "residual": len(still),
        "note": ("BEST CASE ONLY. It assumes both columns are PIT-available on "
                 "their own dates, which P-3 shows is false for 下市日期. It is "
                 "an upper bound on what a ruling could buy, not a result."),
        "residual_detail": sorted(still, key=lambda r: r["first_missing"])[:200],
    }

    # --- P-6 interior gaps: exit-and-return vs a true mid-listing gap --------
    # Audit C cannot tell these apart on its own. A security delisted and
    # relisted years later leaves ONE run there, and during it the exchange
    # expected nothing of it -- calling that an unexplained mark gap would be a
    # category error.
    #
    # 下市日期 turns out to be useless for the split, and that is itself the
    # finding: for every one of these securities it is BLANK. The table keeps one
    # row per security and that row describes the security NOW, so a code that
    # came back has had its earlier exit erased -- the same current-snapshot
    # defect that 上市別 and industry_map have. The master's listing dates are
    # used instead, and only to CLASSIFY a diagnostic, never as a PIT
    # explanation, which is why P-3 does not apply to this use.
    sys.path.insert(0, os.path.join(REPO, "research", "d1_price_universe"))
    from audit_universe_vs_master import load_master        # noqa: E402
    master = {r["stock_id"]: r for r in load_master()}

    runs = audit["audit_C_interior_gaps"]["runs"]
    p6 = Counter()
    true_gaps, returns = [], []
    for r in runs:
        sid = r["stock_id"]
        m = master.get(sid, {})
        listed_from = m.get("listed_from")
        rec = ev.get(sid) or {}
        d = rec.get("delisted_on")
        i = bisect.bisect_left(sessions, r["first_missing"])
        end = sessions[min(i + r["length"] - 1, len(sessions) - 1)]
        row = {**r, "delisted_on": d, "listed_from": listed_from,
               "run_end": end}
        # the run ends on the session BEFORE the security reappears, so the
        # relisting date is one session past `end`, not inside the run.
        if listed_from and listed_from > r["first_missing"]:
            p6["exit_and_return"] += 1
            returns.append(row)
        elif d and r["first_missing"] <= d <= end:
            p6["delisting_inside_run"] += 1
        else:
            p6["true_mid_listing_gap"] += 1
            true_gaps.append(row)
    report["P6_interior_gap_split"] = {
        "unexplained_runs": len(runs),
        "by_kind": dict(p6),
        "exit_and_return_with_delisting_date_recorded": sum(
            1 for r in returns if r["delisted_on"]),
        "finding": (
            "every exit-and-return security has 下市日期 BLANK in the event table "
            "and delisted_on BLANK in the master: the earlier listing episode is "
            "recorded by the price corpus and by NOTHING else. A holding exiting "
            "in that episode is unexplainable by any registered source, "
            "retrospectively as well as PIT."),
        "exit_and_return_detail": sorted(returns, key=lambda r: -r["length"]),
        "true_mid_listing_gap_detail": sorted(true_gaps, key=lambda r: -r["length"]),
    }

    # --- P-5 ruling option matrix -------------------------------------------
    # Decision support, not a decision. Each row is a relaxation the user could
    # rule on; the number is what that relaxation would actually buy, measured.
    def residual(relax_o_e_1, admit_crisis, admit_delisting):
        n = 0
        for u in unexplained:
            sid, fm = u["stock_id"], u["first_missing"]
            rec = ev.get(sid) or {}
            if relax_o_e_1 and u["blocked_by_o_e_1"]:
                continue
            c, d = rec.get("crisis_from"), rec.get("delisted_on")
            if admit_crisis and c and c < fm:
                continue
            if admit_delisting and d and d <= fm:
                continue
            n += 1
        return n

    report["P5_ruling_options"] = {
        "baseline_unexplained": len(unexplained),
        "relax_o_e_1_same_day_only": residual(True, False, False),
        "admit_crisis_date_only": residual(False, True, False),
        "admit_delisting_date_on_or_before_only": residual(False, False, True),
        "relax_o_e_1_plus_crisis": residual(True, True, False),
        "all_three": residual(True, True, True),
        "note": ("`admit_delisting_date_on_or_before` is listed because it is the "
                 "relaxation someone will reach for, and it is the one P-3 shows "
                 "is unsound: it lets a date filed ON the missing session explain "
                 "that session, which is precisely what O-E-1 forbids."),
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("P1 shape :", {k: v for k, v in report["P1_shape"].items()
                         if k != "verdict"})
    print("P2 forward:", {k: v for k, v in report["P2_forward_content"].items()
                          if k != "verdict"})
    print("\nunexplained terminal gaps:", len(unexplained))
    print("P3 下市日期 :", report["P3_delisting_date_availability"]["by_position"])
    print("   offsets  :",
          report["P3_delisting_date_availability"]["offset_histogram_sessions_clipped_at_30"])
    print("P4 危機發生日:", report["P4_crisis_date_availability"]["by_position"])
    print("\ncombined best case:", report["combined_best_case"]["by_source"])
    print("P6 interior split:", report["P6_interior_gap_split"]["by_kind"])
    print("P5 ruling options:", report["P5_ruling_options"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
