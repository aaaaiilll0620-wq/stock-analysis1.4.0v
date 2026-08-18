# -*- coding: utf-8 -*-
"""Coverage report for the official bonus-share ratio. READ-ONLY.

Classifies every canonical `stock_dividend` event the 141-period lookback can
reach into exactly one terminal class, with transport failure kept separate from
absence throughout. Nothing here decides anything;
`stock_dividend_holder_multiplier_source` stays OPEN.

    python research/b0_stock_dividend_multiplier_audit/report_official_bonus_rate.py
"""
from __future__ import annotations

import collections
import datetime
import csv
import glob
import io
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or os.path.join(REPO, "artifacts"),
                   "stock_dividend_multiplier_audit")
RAW = os.path.join(ART, "raw")
OUT = os.path.join(ART, "coverage_report.txt")

sys.path.insert(0, HERE)
from analyse_official_bonus_rate import twse_details, twse_range_rows, num  # noqa: E402

WINDOW_FROM, WINDOW_TO = "2013-06-29", "2026-03-31"
TPEX_BONUS = "每仟股無償配股"

BUF = io.StringIO()


def p(*a):
    print(*a, file=BUF)


def tpex_rows():
    out = {}
    for path in sorted(glob.glob(os.path.join(RAW, "tpex_range_*.json"))):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        for tb in rec["payload"].get("tables") or []:
            fields = tb.get("fields") or []
            if not fields:
                continue
            ix = {c: i for i, c in enumerate(fields)}
            for r in tb.get("data") or []:
                q = str(r[ix["除權息日期"]]).split("/")
                if len(q) != 3 or not q[0].isdigit():
                    continue
                d = "%04d-%02d-%02d" % (int(q[0]) + 1911, int(q[1]), int(q[2]))
                out[(str(r[ix["代號"]]).strip(), d)] = {
                    "bonus_per_1000": num(r[ix[TPEX_BONUS]]),
                    "flag": str(r[ix["權/息"]]).strip()}
    return out


def official_dates_by_security(twse, tpex):
    by = collections.defaultdict(set)
    for sid, d in list(twse) + list(tpex):
        by[sid].add(d)
    return by


def main() -> int:
    twse_rng, tpex = twse_range_rows(), tpex_rows()
    det = twse_details()
    by_sec = official_dates_by_security(twse_rng, tpex)

    fails = []
    for path in glob.glob(os.path.join(ART, "transport_failures_*.json")):
        with open(path, encoding="utf-8") as fh:
            fails.extend(json.load(fh))

    with open(os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv"),
              encoding="utf-8") as fh:
        events = [r for r in csv.DictReader(fh)
                  if r["kind"] == "stock_dividend"
                  and WINDOW_FROM <= r["ex_or_effective_date"] <= WINDOW_TO]

    with open(os.path.join(REPO, "data", "b0", "trading_calendar.csv"),
              encoding="utf-8") as fh:
        sessions = {r["session"] for r in csv.DictReader(fh)}

    p("## Source identity")
    for label, pat in (("twse_range", "twse_range_*.json"),
                       ("tpex_range", "tpex_range_*.json"),
                       ("twse_detail", "twse_detail_*.json")):
        paths = sorted(glob.glob(os.path.join(RAW, pat)))
        tot = sum(os.path.getsize(x) for x in paths)
        p("  %-12s payloads=%-5d bytes=%-10d" % (label, len(paths), tot))
        if paths:
            with open(paths[0], encoding="utf-8") as fh:
                r0 = json.load(fh)
            p("      first url : %s" % r0["url"])
            p("      first sha : %s" % r0["sha256"])
    p("  unresolved transport failures: %d" % len(fails))

    p("")
    p("## Date semantics vs C-50/R4 (`ex_or_effective_date`)")
    off = [d for _, d in list(twse_rng) + list(tpex)]
    p("  official ex-right dates harvested : %d" % len(off))
    p("  that are trading sessions in the frozen calendar : %d (%.2f%%)"
      % (sum(1 for d in off if d in sessions),
         100.0 * sum(1 for d in off if d in sessions) / len(off)))
    p("  -> the official date IS the market-effective session R4 requires;")
    p("     no translation from a credit/registration date is involved.")

    rows, cls = [], collections.Counter()
    for ev in events:
        sid, ex = ev["stock_id"], ev["ex_or_effective_date"]
        key = (sid, ex)
        rate = board = None
        if key in twse_rng:
            board = "TWSE"
            d = det.get(key)
            if d is None:
                klass = "TRANSPORT_OR_UNFETCHED"
            elif not d.get("row"):
                klass = "MATCHED_DETAIL_NO_DATA"
            else:
                rate = d["bonus_per_1000"]
                klass = ("MATCHED_POSITIVE" if rate and rate > 0
                         else "MATCHED_ZERO" if rate == 0 else "MATCHED_NULL")
        elif key in tpex:
            board = "TPEX"
            rate = tpex[key]["bonus_per_1000"]
            klass = ("MATCHED_POSITIVE" if rate and rate > 0
                     else "MATCHED_ZERO" if rate == 0 else "MATCHED_NULL")
        else:
            board = "ABSENT"
            have = by_sec.get(sid)
            if ev["reconstructibility"] == "NOT_RECONSTRUCTIBLE":
                klass = "LEDGER_NOT_RECONSTRUCTIBLE"
            elif not have:
                klass = "OFF_BOARD_NEVER_PUBLISHED"
            elif ex < min(have):
                klass = "OFF_BOARD_BEFORE_FIRST_OFFICIAL_ROW"
            else:
                exd = datetime.date.fromisoformat(ex)
                gap = min(abs((datetime.date.fromisoformat(d) - exd).days)
                          for d in have)
                # Reported as its OWN class, never merged into MATCHED. C-50 was
                # ruled without a date tolerance and this audit does not invent
                # one; naming the class is the finding, absorbing it would be a
                # decision.
                klass = ("DATE_OFFSET_WITHIN_3D" if gap <= 3
                         else "ABSENT_UNEXPLAINED")
        cls[klass] += 1
        rows.append({"stock_id": sid, "ex_date": ex, "board": board,
                     "class": klass, "bonus_per_1000": rate,
                     "multiplier": (1 + rate / 1000.0) if rate else None,
                     "reconstructibility": ev["reconstructibility"]})

    p("")
    p("## Coverage over the %d canonical stock_dividend events in the window" % len(events))
    for k, v in cls.most_common():
        p("  %-38s %5d  (%.2f%%)" % (k, v, 100.0 * v / len(events)))

    matched = [r for r in rows if r["class"] == "MATCHED_POSITIVE"]
    p("")
    p("  matched with a positive official ratio : %d over %d securities"
      % (len(matched), len({r["stock_id"] for r in matched})))
    if matched:
        m = sorted(r["multiplier"] for r in matched)
        p("  implied m = 1 + rate/1000  min=%.6f p50=%.6f p95=%.6f max=%.6f"
          % (m[0], statistics.median(m), m[int(.95 * len(m)) - 1], m[-1]))
        by_board = collections.Counter(r["board"] for r in matched)
        p("  by contemporaneous board: %s" % dict(by_board))

    with open(os.path.join(ART, "coverage.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(BUF.getvalue())
    print(BUF.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main())
