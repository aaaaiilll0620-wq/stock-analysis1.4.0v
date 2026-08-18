"""O-E · availability + coverage probe for calendar and security-status sources.

Answers, from the data rather than from reasoning about market microstructure:

  1. Is 暫停交易.年月日 the first NON-TRADING session, or a session that still has
     a price? This decides whether the row can explain a missing price on its own
     start date without violating O-E-1.
  2. Does the price series actually resume at/after 恢復交易日?
  3. Coverage: of the price gaps that really occur in the window, how many can
     this status source explain at all?

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import glob
import json
import os
import sys
from collections import Counter

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SUSP = os.path.join(REPO, "tej_exports", "DataExport0806", "暫停交易2004-20260806")
CAL = os.path.join(os.path.expanduser("~"), "market_cache", "taiex_daily.parquet")
PRICE = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
OUT = os.path.join(HERE, "market_state_probe.json")

WIN_START, WIN_END = "2014-07-31", "2026-03-31"


def d8(v):
    s = str(v).strip().split(".")[0]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return None


def load_suspensions():
    rows = []
    for f in sorted(glob.glob(os.path.join(SUSP, "**", "*.xlsx"), recursive=True)):
        df = pd.read_excel(f)
        for r in df.to_dict("records"):
            rows.append({
                "stock_id": str(r["證券代碼"]).split()[0],
                "start": d8(r["年月日"]),
                "resume": d8(r["恢復交易日"]),
                "reason": str(r["暫停交易原因"]).strip(),
            })
    return rows


def load_calendar():
    cal = pd.read_parquet(CAL)
    return sorted(cal["date"].astype(str).unique())


def load_prices():
    files = sorted(glob.glob(os.path.join(PRICE, "*.parquet")))
    if not files:
        files = [PRICE]
    frames = []
    for f in files:
        df = pd.read_parquet(f, columns=["stock_id", "date", "close"])
        frames.append(df)
    px = pd.concat(frames, ignore_index=True)
    px["date"] = px["date"].astype(str)
    px["stock_id"] = px["stock_id"].astype(str)
    return px


def main():
    susp = load_suspensions()
    cal = load_calendar()
    cal_set = set(cal)
    print(f"suspensions: {len(susp)}   calendar sessions: {len(cal)} "
          f"({cal[0]} .. {cal[-1]})")

    px = load_prices()
    print(f"price rows: {len(px):,}  securities: {px.stock_id.nunique():,}")
    priced = set(zip(px.stock_id, px.date))
    by_stock = px.groupby("stock_id")["date"]
    last_price = by_stock.max().to_dict()
    first_price = by_stock.min().to_dict()
    px_max = px.date.max()

    # --- Q1: is the suspension start date itself priced? --------------------
    q1 = Counter()
    q1_by_reason = {}
    for s in susp:
        if not s["start"]:
            continue
        if s["start"] not in cal_set:
            q1["start_not_a_session"] += 1
            continue
        if s["stock_id"] not in first_price:
            q1["stock_not_in_price_data"] += 1
            continue
        hit = (s["stock_id"], s["start"]) in priced
        q1["start_has_price" if hit else "start_has_no_price"] += 1
        key = s["reason"][:12]
        d = q1_by_reason.setdefault(key, Counter())
        d["priced" if hit else "unpriced"] += 1

    # --- Q2: does the series resume at/after 恢復交易日? ---------------------
    q2 = Counter()
    for s in susp:
        if not (s["start"] and s["resume"]) or s["stock_id"] not in last_price:
            continue
        after = [d for d in cal if s["resume"] <= d <= px_max][:10]
        got = any((s["stock_id"], d) in priced for d in after)
        q2["resumes_within_10_sessions" if got else "no_resume_observed"] += 1
        if s["resume"] > px_max:
            q2["resume_beyond_price_data"] += 1

    # --- Q3: coverage of real gaps in the window ----------------------------
    # A "terminal gap": the security has prices in the window but stops before
    # the end of the price data. Can a suspension row explain it?
    susp_by_stock = {}
    for s in susp:
        susp_by_stock.setdefault(s["stock_id"], []).append(s)

    q3 = Counter()
    unexplained_examples = []
    for sid, last in last_price.items():
        if last >= px_max:
            continue                     # still priced through the data end
        if not (WIN_START <= last <= WIN_END):
            continue                     # terminal event outside the window
        q3["terminal_gaps_in_window"] += 1
        rows = susp_by_stock.get(sid, [])
        near = [r for r in rows if r["start"] and abs_days(r["start"], last) <= 40]
        if near:
            q3["explained_by_suspension_row"] += 1
        else:
            q3["unexplained_by_this_source"] += 1
            if len(unexplained_examples) < 15:
                unexplained_examples.append({"stock_id": sid, "last_price": last,
                                             "suspension_rows": len(rows)})

    # --- calendar sanity ----------------------------------------------------
    cal_win = [d for d in cal if WIN_START <= d <= WIN_END]
    payload = {
        "study": "O-E market-state source probe",
        "read_only": True, "performance_computed": False,
        "window": {"start": WIN_START, "end": WIN_END},
        "calendar": {
            "source": "market_cache/taiex_daily.parquet",
            "sessions_total": len(cal), "first": cal[0], "last": cal[-1],
            "sessions_in_window": len(cal_win),
            "duplicate_dates": len(cal) - len(set(cal)),
        },
        "suspensions": {
            "rows": len(susp),
            "securities": len({s["stock_id"] for s in susp}),
            "reasons_top": dict(Counter(s["reason"][:16] for s in susp).most_common(12)),
        },
        "q1_start_date_priced": dict(q1),
        "q1_by_reason": {k: dict(v) for k, v in sorted(
            q1_by_reason.items(), key=lambda kv: -sum(kv[1].values()))[:12]},
        "q2_resume": dict(q2),
        "q3_gap_coverage": dict(q3),
        "q3_unexplained_examples": unexplained_examples,
        "price_data_max": px_max,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print("\nQ1 suspension start date priced?", dict(q1))
    print("   by reason:")
    for k, v in list(payload["q1_by_reason"].items()):
        print("      %-14s %s" % (k, dict(v)))
    print("\nQ2 resume observed?", dict(q2))
    print("\nQ3 terminal gap coverage in window:", dict(q3))
    for e in unexplained_examples[:8]:
        print("      unexplained:", e)
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


def abs_days(a, b):
    from datetime import date
    ya, ma, da = (int(x) for x in a.split("-"))
    yb, mb, db = (int(x) for x in b.split("-"))
    return abs((date(ya, ma, da) - date(yb, mb, db)).days)


if __name__ == "__main__":
    sys.exit(main())
