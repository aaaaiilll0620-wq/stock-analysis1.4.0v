# -*- coding: utf-8 -*-
"""bull_attribution_lab.py — 多頭診斷:雙確認在多頭賺多少 + 獲利因子是誰。
================================================================================
兩個問題:
  (1) 報酬率:regime 切多頭月/空頭月,雙確認(含息)在多頭月的年化報酬 + 對 0050 多頭時贏不贏。
  (2) 獲利因子:綜合分5因子(營收/動能/技術/籌碼/價值)各自的排序力 IC,分多頭/空頭。
      IC = 當月因子百分位 vs 未來報酬百分位 的相關(Spearman);正=高分股後續漲多。
      t = mean(IC)/std × √月數;|t|>2 才算穩定。

誠實邊界:fwd=20日價格報酬(未含息,IC看排序不受影響);proxy composite;回測≠未來。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import bisect
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from beat_0050.honest_backtest import Engine, RF_ANNUAL
from existing_composite import build_factors, holdings_for
from regime_switch_lab import build_regime

FACTORS = {"_f": "營收成長(0.31)", "_m": "動能(0.27)", "_t": "技術(0.19)",
           "_w": "籌碼(0.15)", "_v": "價值(0.08)", "composite": "綜合分(合成)", "c2": "c2價值"}


def ann(monthly_ret_pct: np.ndarray) -> tuple:
    """回 (年化報酬%, 月勝率%, 平均月報酬%)。"""
    r = np.asarray(monthly_ret_pct, float) / 100.0
    r = r[~np.isnan(r)]
    if len(r) == 0:
        return (np.nan, np.nan, np.nan)
    eq = np.prod(1 + r)
    cagr = (eq ** (12 / len(r)) - 1) * 100
    return (cagr, (r > 0).mean() * 100, r.mean() * 100)


if __name__ == "__main__":
    eng = Engine()
    obs = build_factors()

    # regime bear 旗 → 每月多空
    reg = build_regime(); rm = dict(zip(reg["date"], reg["bear"])); rd = sorted(rm)
    def is_bear(a):
        i = bisect.bisect_right(rd, str(a)) - 1
        return bool(rm[rd[i]]) if i >= 0 else False

    # ===== (1) 報酬率:雙確認 含息 分多空 =====
    dual = eng.run(holdings_for(obs, "dual"))["monthly"].reset_index(drop=True)
    dual["bear"] = dual["as_of"].map(is_bear)
    print("=" * 66)
    print("(1) 雙確認報酬率(含息+成本) — 多頭月 vs 空頭月 vs 0050")
    print("=" * 66)
    print(f"{'':<10}{'月數':>5}{'年化%':>9}{'月勝率%':>9}{'平均月%':>9}")
    for lab, sub in [("多頭月", dual[~dual["bear"]]), ("空頭月", dual[dual["bear"]]), ("全部", dual)]:
        s = ann(sub["ret"].values); b = ann(sub["bench"].values)
        print(f"{'雙確認·'+lab:<10}{len(sub):>5}{s[0]:>9.1f}{s[1]:>9.0f}{s[2]:>9.2f}")
        print(f"{'  0050·'+lab:<10}{len(sub):>5}{b[0]:>9.1f}{b[1]:>9.0f}{b[2]:>9.2f}")
    print("\n→ 看『多頭月』那組:你的系統多頭時年化多少、對 0050 是否有超額。")

    # ===== (2) 獲利因子:各因子 IC 分多空 =====
    print("\n" + "=" * 66)
    print("(2) 獲利因子 — 各因子排序力 IC(多頭 vs 空頭);正且|t|>2=穩定賺")
    print("=" * 66)
    recs = {k: {"bull": [], "bear": []} for k in FACTORS}
    for a, x in obs.groupby("as_of"):
        if len(x) < 30 or x["fwd"].isna().all():
            continue
        fwd_pct = x["fwd"].rank(pct=True)
        tag = "bear" if is_bear(a) else "bull"
        for k in FACTORS:
            ic = np.corrcoef(x[k].values, fwd_pct.values)[0, 1]
            if not np.isnan(ic):
                recs[k][tag].append(ic)
    print(f"{'因子':<16}{'多頭IC':>9}{'多頭t':>8}{'空頭IC':>9}{'空頭t':>8}")
    def tstat(v):
        v = np.array(v, float)
        return v.mean() / v.std(ddof=1) * np.sqrt(len(v)) if len(v) > 1 and v.std() else np.nan
    for k, name in FACTORS.items():
        bull, bear = recs[k]["bull"], recs[k]["bear"]
        print(f"{name:<16}{np.mean(bull):>9.3f}{tstat(bull):>8.1f}"
              f"{np.mean(bear):>9.3f}{tstat(bear):>8.1f}")
    print("\n→ 多頭IC 最高且 t 顯著者 = 你多頭時的獲利引擎。負值=多頭時反而扣分。")
