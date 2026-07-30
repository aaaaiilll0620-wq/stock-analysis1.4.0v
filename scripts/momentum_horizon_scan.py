# -*- coding: utf-8 -*-
"""momentum_horizon.py — 「動能是負的」是因子無效,還是形成期選錯?
面板裡有三個形成期:momentum=20日、mom60=60日、mom120=120日。若負號只出現在 20 日、
而 60/120 日轉正,那就是**短期反轉窗**,不是動能失效。
另對照 high52_prox(路徑型,非報酬型)與 c2 用的反動能。
報酬線:exec_ret.fwd_x(可執行)。
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\dev\Project 1")

obs = pd.read_parquet(ROOT / "data" / "research_base" / "obs_alpha.parquet")
ex = pd.read_parquet(ROOT / "data" / "research_base" / "exec_ret.parquet")
d = obs[obs["listed_ok"] == True].merge(ex, on=["as_of", "stock_id"], how="left")  # noqa: E712
d["as_of_s"] = d["as_of"].astype(str).str[:10]

COLS = [("momentum", "過去 20 日報酬 (生產用的『動能』)"),
        ("mom60", "過去 60 日報酬 (≈3 個月)"),
        ("mom120", "過去 120 日報酬 (≈6 個月)"),
        ("high52_prox", "距 240 日最高收盤 (路徑型)"),
        ("rsi14", "RSI14"),
        ("bbp20", "布林帶位置 20"),
        ("ma_gap60", "距 MA60 乖離")]

ERAS = [("2005-2009", "2005", "2009-12"), ("2010-2014", "2010", "2014-12"),
        ("2015-2018", "2015", "2018-12"), ("2019-2021", "2019", "2021-12"),
        ("2022", "2022", "2022-12"), ("2023-2026", "2023", "2026-12")]


def ic(sub, col, retcol="fwd_x"):
    out = {}
    for a, g in sub.groupby("as_of_s"):
        m = g[col].notna() & g[retcol].notna()
        if m.sum() >= 30:
            out[a] = g.loc[m, col].rank().corr(g.loc[m, retcol].rank())
    return pd.Series(out).dropna()


def t_of(s):
    return s.mean() / s.std(ddof=1) * np.sqrt(len(s)) if len(s) > 2 else np.nan


for tier, floor in [("ADV≥2000萬(生產設定)", 2e7), ("ADV≥100萬", 1e6)]:
    sub = d[d["adv20"] >= floor]
    print("=" * 108)
    print(f"Rank IC vs 未來 20 日可執行報酬 — {tier}")
    print("=" * 108)
    print(f"{'因子':<34}{'IC':>9}{'t':>7}{'月勝率%':>9}   " + "".join(f"{e[0]:>10}" for e in ERAS))
    for col, label in COLS:
        if col not in sub.columns:
            continue
        s = ic(sub, col)
        row = f"{label:<34}{s.mean():>9.4f}{t_of(s):>7.2f}{(s > 0).mean()*100:>9.1f}   "
        for _, lo, hi in ERAS:
            e = s[(s.index >= lo) & (s.index <= hi + "-31")]
            row += f"{(e.mean() if len(e) else np.nan):>10.4f}"
        print(row)
    print()

print("=" * 108)
print("形成期掃描:過去 N 日報酬 → 未來 20 日報酬 (ADV≥2000萬,由日價格線現算)")
print("=" * 108)
import duckdb  # noqa: E402
TEJ = Path.home() / "tej_cache"
con = duckdb.connect()
con.execute("PRAGMA threads=8")
base = d[d["adv20"] >= 2e7][["as_of", "stock_id", "fwd_x"]].dropna()
con.register("base", base)
con.execute(f"""CREATE TEMP TABLE px AS
    SELECT stock_id, date, close, row_number() OVER (PARTITION BY stock_id ORDER BY date) i
    FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true) WHERE close>0""")
LAGS = [5, 10, 20, 40, 60, 120, 240]
sel = ", ".join(f"p{n}.close AS c{n}" for n in LAGS)
joins = " ".join(f"LEFT JOIN px p{n} ON p{n}.stock_id=b.stock_id AND p{n}.i=b0.i-{n}" for n in LAGS)
q = con.execute(f"""
    WITH b0 AS (SELECT b.as_of, b.stock_id, b.fwd_x, p.i, p.close c0
                FROM base b ASOF JOIN px p ON b.stock_id=p.stock_id AND p.date<=b.as_of)
    SELECT b.as_of, b.stock_id, b.fwd_x, b0.c0, {sel}
    FROM base b JOIN b0 ON b.as_of=b0.as_of AND b.stock_id=b0.stock_id {joins}
""").df()
q["as_of_s"] = q["as_of"].astype(str).str[:10]
print(f"{'形成期':<22}{'IC':>9}{'t':>7}{'月勝率%':>9}")
for n in LAGS:
    q[f"m{n}"] = q["c0"] / q[f"c{n}"] - 1
    s = ic(q, f"m{n}")
    lab = f"過去 {n} 日報酬" + ("  ← 生產用的" if n == 20 else "")
    print(f"{lab:<22}{s.mean():>9.4f}{t_of(s):>7.2f}{(s > 0).mean()*100:>9.1f}")
# 跳過最近一個月的版本 (Jegadeesh-Titman 標準做法)
print()
for n in [120, 240]:
    q[f"skip{n}"] = q[f"c20"] / q[f"c{n}"] - 1
    s = ic(q, f"skip{n}")
    print(f"{'過去 '+str(n)+' 日、跳過最近 20 日':<22}{s.mean():>9.4f}{t_of(s):>7.2f}{(s > 0).mean()*100:>9.1f}")
