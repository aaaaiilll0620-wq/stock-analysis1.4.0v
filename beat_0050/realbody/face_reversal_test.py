# -*- coding: utf-8 -*-
"""face_reversal_test.py — 驗證「技術面=短期反轉、動能面=中期趨勢」。
================================================================================
每月按各面分數分五等分(Q1最低~Q5最高),看各組未來20日報酬(fwd)。
  · 技術面若=短期反轉 → Q5(最強)報酬<Q1,單調遞減,Q5−Q1價差負。
  · 動能面若=中期趨勢 → Q5>Q1,單調遞增,價差正。
Q5−Q1 逐月價差算 t 值(|t|>2 顯著)。resolve「猜測」→「數據」。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from beat_0050.honest_backtest import OBS_ALPHA

RB = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"
FACES = {"f_tech": "技術面", "f_mom": "動能面", "f_val": "估值面", "f_fund": "基本面", "f_whale": "籌碼面"}


def quintile_profile(df, face):
    """回 (各Q平均fwd陣列 Q1..Q5, Q5-Q1逐月價差)。"""
    q_means = {q: [] for q in range(1, 6)}
    spreads = []
    for a, g in df.groupby("as_of"):
        g = g.dropna(subset=[face, "fwd"])
        if len(g) < 50:
            continue
        try:
            g = g.assign(_q=pd.qcut(g[face].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]))
        except Exception:
            continue
        mq = g.groupby("_q", observed=True)["fwd"].mean()
        for q in range(1, 6):
            if q in mq.index:
                q_means[q].append(mq[q])
        if 5 in mq.index and 1 in mq.index:
            spreads.append(mq[5] - mq[1])
    prof = [np.nanmean(q_means[q]) for q in range(1, 6)]
    spreads = np.array(spreads, float)
    t = spreads.mean() / spreads.std(ddof=1) * np.sqrt(len(spreads)) if len(spreads) > 1 else np.nan
    return prof, spreads.mean(), t


if __name__ == "__main__":
    rb = pd.read_parquet(RB)
    rb["as_of"] = rb["as_of"].astype(str); rb["stock_id"] = rb["stock_id"].astype(str)
    obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "fwd"])
    obs["as_of"] = obs["as_of"].astype(str); obs["stock_id"] = obs["stock_id"].astype(str)
    rb = rb.merge(obs, on=["as_of", "stock_id"], how="left")
    for f in FACES:
        rb[f] = pd.to_numeric(rb[f], errors="coerce")

    print("=" * 72)
    print("各面五等分的未來20日報酬(%) — Q1最低分 → Q5最高分")
    print("=" * 72)
    print(f"{'面':<8}{'Q1':>8}{'Q2':>8}{'Q3':>8}{'Q4':>8}{'Q5':>8}{'Q5−Q1':>9}{'t值':>7}  型態")
    for f, lab in FACES.items():
        prof, sp, t = quintile_profile(rb, f)
        shape = ("↗遞增(趨勢)" if prof[4] > prof[0] and prof[4] > prof[2]
                 else "↘遞減(反轉)" if prof[4] < prof[0] and prof[4] < prof[2]
                 else "─平/雜訊")
        print(f"{lab:<8}" + "".join(f"{p:>8.2f}" for p in prof) +
              f"{sp:>9.2f}{t:>7.1f}  {shape}")
    print("\n→ 技術面若 Q5<Q1、價差負 = 買最強者反而跌 = 短期反轉,假設成立。")
    print("  動能面若 Q5>Q1、價差正 = 中期趨勢延續,兩者對比即答案。")
