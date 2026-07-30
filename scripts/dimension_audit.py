# -*- coding: utf-8 -*-
"""dimension_audit.py — 五個維度的成分因子逐一量 Rank IC(可執行線)。
目的不是「挑最好的因子」(那是過擬合機器),是回答每個維度**該不該存在、該怎麼定義**:
  · 這個維度裡有沒有任何成分是顯著的?
  · 現行定義有沒有把有效成分跟反向成分混在一起(技術腿的病)?
多重檢定:30 個因子 → Bonferroni 0.05/30 對應 |t| ≈ 3.0。標 ★ 者才算通過。
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\dev\Project 1")

DIMS = {
    "基本面 (權重 0.31)": ["revenue_yoy", "rev_yoy_3m", "rev_accel", "eps", "roe",
                           "op_income", "net_income", "eps_pos_q4"],
    "估值 (權重 0.08)": ["value", "value_ind"],
    "技術 (權重 0.19)": ["high52_prox", "bbp20", "rsi14", "ma_gap60", "vol60"],
    "動能 (權重 0.27)": ["momentum", "mom60", "mom120"],
    "籌碼 (權重 0.15)": ["chip", "chip5", "chip10", "chip60", "chip_accel",
                         "ratio_1000up", "big_d4w", "big_d12w", "holders_chg12w"],
    "(未納入) 股權結構": ["pledge_pct", "pledge_d3m", "director_holding_pct"],
}
IN_USE = {"revenue_yoy": "基本面腿本體", "value_ind": "估值腿本體",
          "high52_prox": "技術腿 1/2", "bbp20": "技術腿 1/2",
          "momentum": "動能腿本體", "chip": "籌碼腿本體"}
TCRIT = 3.0   # Bonferroni 0.05/30

obs = pd.read_parquet(ROOT / "data" / "research_base" / "obs_alpha.parquet")
ex = pd.read_parquet(ROOT / "data" / "research_base" / "exec_ret.parquet")
d = obs[obs["listed_ok"] == True].merge(ex, on=["as_of", "stock_id"], how="left")  # noqa: E712
d["as_of_s"] = d["as_of"].astype(str).str[:10]


def ic(sub, col):
    out = {}
    for a, g in sub.groupby("as_of_s"):
        m = g[col].notna() & g["fwd_x"].notna()
        if m.sum() >= 30:
            out[a] = g.loc[m, col].rank().corr(g.loc[m, "fwd_x"].rank())
    return pd.Series(out).dropna()


def t_of(s):
    return s.mean() / s.std(ddof=1) * np.sqrt(len(s)) if len(s) > 2 else np.nan


for tier, floor in [("ADV≥2000萬(生產設定)", 2e7), ("ADV≥100萬", 1e6)]:
    sub = d[d["adv20"] >= floor]
    print("=" * 104)
    print(f"五維度成分稽核 — {tier}   (★ = |t| ≥ {TCRIT},通過 30 因子的 Bonferroni)")
    print("=" * 104)
    for dim, cols in DIMS.items():
        print(f"\n■ {dim}")
        print(f"  {'因子':<22}{'現行用途':<14}{'IC':>9}{'t':>7}{'月勝率%':>9}"
              f"{'2010後IC':>10}{'t':>7}{'覆蓋率%':>9}")
        rows = []
        for c in cols:
            if c not in sub.columns:
                continue
            s = ic(sub, c)
            if len(s) < 60:
                continue
            s2 = s[s.index >= "2010"]
            rows.append((c, s.mean(), t_of(s), (s > 0).mean() * 100,
                         s2.mean(), t_of(s2), sub[c].notna().mean() * 100))
        for c, m, t, w, m2, t2, cov in sorted(rows, key=lambda r: -abs(r[2])):
            star = "★" if abs(t) >= TCRIT else " "
            print(f" {star}{c:<22}{IN_USE.get(c, ''):<14}{m:>9.4f}{t:>7.2f}{w:>9.1f}"
                  f"{m2:>10.4f}{t2:>7.2f}{cov:>9.1f}")
    print()
