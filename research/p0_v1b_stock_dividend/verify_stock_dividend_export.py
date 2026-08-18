"""V-1b verification of the 配股相關 export (READ-ONLY, non-performance only).

Answers exactly the questions the V-1b ruling requires and nothing else:
  schema consistency / date semantics / coverage / can it support
  receivable -> tradable shares. No return, IC, Sharpe, ranking or selection
  quantity is computed anywhere in this file.

Also resolves, from the data itself, the two open questions from the export
design conversation:
  1. what unit 盈餘配股率 % is expressed in — decided by reconciling it against
     the absolute new-share counts, never by assuming a par value;
  2. whether 股票股利上市日 or 股票股利發放日 is the binding tradable date.
"""

import glob
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, "tej_exports", "DataExport0806", "配股相關2004-20260817")
OUT = os.path.join(HERE, "v1b_verification.json")

WIN_START, WIN_END = "2014-07-31", "2026-03-31"      # frozen B0 window
_D8 = re.compile(r"^\d{8}$")


def norm_date(v):
    s = str(v).strip()
    if not s or s == ".":
        return None
    if _D8.match(s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    s = s.replace("/", "-")
    p = s.split("-")
    if len(p) == 3 and all(x.isdigit() for x in p):
        return "%04d-%02d-%02d" % (int(p[0]), int(p[1]), int(p[2]))
    return None


def num(v):
    s = str(v).strip()
    if not s or s == ".":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_rows():
    rows, files = [], []
    for z in sorted(glob.glob(os.path.join(SRC, "*.zip"))):
        zf = zipfile.ZipFile(z)
        for name in zf.namelist():
            txt = zf.read(name).decode("utf-16")
            lines = txt.split("\n")
            hdr = lines[0].rstrip("\r").split("\t")
            for line in lines[1:]:
                if not line.strip():
                    continue
                f = line.rstrip("\r").split("\t")
                if len(f) < len(hdr):
                    continue
                rows.append(dict(zip(hdr, f)))
        files.append((os.path.basename(z), len(rows)))
    return rows, hdr, files


def main():
    rows, hdr, files = load_rows()
    print(f"loaded {len(rows):,} rows from {len(files)} zips, {len(hdr)} columns")

    # --- what counts as a stock-dividend event ------------------------------
    def new_shares(r):
        a = num(r.get("盈餘增資(仟股)")) or 0.0
        b = num(r.get("公積增資(仟股)")) or 0.0
        return a + b

    flag_y = [r for r in rows if str(r.get("配股(Y/N)", "")).strip() == "Y"]
    shares_pos = [r for r in rows if new_shares(r) > 0]
    both = [r for r in flag_y if new_shares(r) > 0]
    print(f"配股(Y/N)=='Y': {len(flag_y):,} | new_shares>0: {len(shares_pos):,} | both: {len(both):,}")

    events = both or shares_pos
    stocks = {str(r["證券代碼"]).split()[0] for r in events}
    print(f"stock-dividend events: {len(events):,} across {len(stocks):,} securities")

    # --- coverage by year ----------------------------------------------------
    by_year = Counter()
    for r in events:
        d = norm_date(r.get("年月日"))
        if d:
            by_year[d[:4]] += 1

    # --- date semantics: 上市日 vs 發放日 -----------------------------------
    lag = {"listed_only": 0, "paid_only": 0, "both": 0, "neither": 0}
    diff_hist = Counter()
    ex_to_tradable = []
    in_window, in_window_missing = 0, 0
    not_ordered = 0
    for r in events:
        ex = norm_date(r.get("年月日"))
        li = norm_date(r.get("股票股利上市日"))
        pa = norm_date(r.get("股票股利發放日"))
        if li and pa:
            lag["both"] += 1
            diff_hist[(1 if li > pa else (-1 if li < pa else 0))] += 1
        elif li:
            lag["listed_only"] += 1
        elif pa:
            lag["paid_only"] += 1
        else:
            lag["neither"] += 1
        tradable = max([d for d in (li, pa) if d], default=None)
        if ex and WIN_START <= ex <= WIN_END:
            in_window += 1
            if not tradable:
                in_window_missing += 1
            elif tradable <= ex:
                not_ordered += 1
        if ex and tradable and tradable > ex:
            y, m, d = (int(x) for x in ex.split("-"))
            y2, m2, d2 = (int(x) for x in tradable.split("-"))
            ex_to_tradable.append((y2 - y) * 365 + (m2 - m) * 30 + (d2 - d))

    # --- unit resolution: reconcile 配股率 % against absolute new shares -----
    unit_tests = []
    for r in events:
        ns = new_shares(r)
        tot = num(r.get("總股數(仟股)"))
        rate = (num(r.get("盈餘配股率 %")) or 0.0) + (num(r.get("公積配股率 %")) or 0.0)
        if ns > 0 and tot and tot > ns and rate > 0:
            pre = tot - ns
            unit_tests.append({
                "vs_pre_pct": ns / pre * 100.0,      # % of pre-event shares
                "vs_pre_per10": ns / pre * 10.0,     # NT$ per share at par 10
                "rate": rate,
            })
    def ratio_stats(key):
        vals = sorted(t[key] / t["rate"] for t in unit_tests if t["rate"])
        if not vals:
            return None
        n = len(vals)
        return {"n": n, "p10": vals[n // 10], "median": vals[n // 2],
                "p90": vals[min(n - 1, 9 * n // 10)]}

    as_pct, as_per10 = ratio_stats("vs_pre_pct"), ratio_stats("vs_pre_per10")

    # --- other share-count events (scope question, counts only) -------------
    other_cols = ["減資(仟股)", "現金增資(仟股)", "員工分紅(仟股)", "合併(仟股)",
                  "受讓(仟股)", "庫藏股註銷(仟股)", "証券轉換_可轉債(仟股)",
                  "股份轉換(仟股", "變更股票面額股數(仟股)", "其它(仟股)"]
    other = {}
    for c in other_cols:
        ev = [r for r in rows if (num(r.get(c)) or 0.0) != 0.0]
        win = [r for r in ev if (lambda d: d and WIN_START <= d <= WIN_END)(norm_date(r.get("年月日")))]
        other[c] = {"events_all": len(ev), "events_in_window": len(win),
                    "securities_in_window": len({str(r["證券代碼"]).split()[0] for r in win})}

    payload = {
        "study": "V-1b stock-dividend source verification",
        "read_only": True,
        "performance_computed": False,
        "source": os.path.relpath(SRC, REPO).replace("\\", "/"),
        "files": files,
        "columns": hdr,
        "rows_total": len(rows),
        "event_definition": {
            "flag_Y": len(flag_y), "new_shares_gt_0": len(shares_pos),
            "both": len(both), "used": len(events),
        },
        "securities_with_events": len(stocks),
        "events_by_year": dict(sorted(by_year.items())),
        "tradable_date_presence": lag,
        "listed_vs_paid": {"listed_later": diff_hist[1], "paid_later": diff_hist[-1],
                           "same_day": diff_hist[0]},
        "window": {"start": WIN_START, "end": WIN_END,
                   "events_in_window": in_window,
                   "missing_tradable_date": in_window_missing,
                   "tradable_not_after_ex": not_ordered},
        "ex_to_tradable_days_approx": {
            "n": len(ex_to_tradable),
            "median": sorted(ex_to_tradable)[len(ex_to_tradable) // 2] if ex_to_tradable else None,
            "min": min(ex_to_tradable) if ex_to_tradable else None,
            "max": max(ex_to_tradable) if ex_to_tradable else None,
        },
        "rate_unit_resolution": {
            "method": "reconcile (盈餘增資+公積增資) / pre-event shares against (盈餘+公積)配股率 %",
            "if_rate_is_percent_of_shares": as_pct,
            "if_rate_is_NTD_per_share_at_par_10": as_per10,
        },
        "other_share_count_events": other,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print()
    print("events by year:", dict(sorted(by_year.items())))
    print("tradable date presence:", lag)
    print("listed vs paid:", dict(diff_hist))
    print(f"IN WINDOW {WIN_START}..{WIN_END}: events={in_window} "
          f"missing_tradable={in_window_missing} not_after_ex={not_ordered}")
    print("ex->tradable days (approx): ", payload["ex_to_tradable_days_approx"])
    print("rate as % of shares  :", as_pct)
    print("rate as NTD/share@par10:", as_per10)
    print()
    print("other share-count events in window:")
    for c, v in other.items():
        if v["events_in_window"]:
            print("   %-26s %5d events / %4d securities"
                  % (c, v["events_in_window"], v["securities_in_window"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
