# -*- coding: utf-8 -*-
"""dual_riskoverlay.py — 救專案 A:雙確認 + 空頭 regime 減碼,壓 MDD 讓夏普淨贏 0050。
================================================================================
發現(existing_composite):雙確認全循環 CAGR 16.1%>0050 14.7%,但夏普 0.64<0.69,
病灶 100% 是回撤(MDD -69% vs -54%)。本腳本加一層**空頭減碼**風控,測能否把 MDD 壓到
0050 附近、同時保住報酬 → 夏普過 0.69 = 淨贏。

風控邏輯(無未來函數):regime bear 旗在 as_of 當下已知(等權市場 vs MA200),
bear 期把曝險降到 expo,其餘轉現金(RF)或轉 0050。曝險變動收單邊成本(近似)。
報表:CAGR / 波動 / 夏普 / Sortino / **Calmar(CAGR÷|MDD|)** / MDD / 水下 vs 0050。
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

DERISK_COST = 0.285   # 曝險變動單邊成本近似 (%),元大6折半程+滑價半程


def metrics(ret_pct: np.ndarray) -> dict:
    r = np.asarray(ret_pct, float) / 100.0
    r = r[~np.isnan(r)]
    if len(r) < 6:
        return {}
    eq = np.cumprod(1 + r); n = len(r)
    cagr = (eq[-1] ** (12 / n) - 1) * 100
    vol = r.std(ddof=1) * np.sqrt(12) * 100
    downside = r[r < 0].std(ddof=1) * np.sqrt(12) * 100 if (r < 0).any() else np.nan
    sharpe = (cagr - RF_ANNUAL) / vol if vol else np.nan
    sortino = (cagr - RF_ANNUAL) / downside if downside and downside > 0 else np.nan
    dd = eq / np.maximum.accumulate(eq) - 1; mdd = dd.min() * 100
    calmar = cagr / abs(mdd) if mdd else np.nan
    uw = dd < -1e-9; L = c = 0
    for u in uw:
        c = c + 1 if u else 0; L = max(L, c)
    return {"CAGR": cagr, "波動": vol, "夏普": sharpe, "Sortino": sortino,
            "Calmar": calmar, "MDD": mdd, "水下": L}


def apply_overlay(m: pd.DataFrame, bear_of, expo: float, bear_asset: str) -> np.ndarray:
    """bear 期曝險降到 expo,其餘 → cash(RF) 或 b0050(該期0050報酬)。回月報酬%序列。"""
    cash = RF_ANNUAL / 12.0
    out, prev_e = [], 1.0
    for _, row in m.iterrows():
        bear = bear_of(str(row["as_of"]))
        e = expo if bear else 1.0
        alt = row["bench"] if (bear_asset == "0050" and not np.isnan(row["bench"])) else cash
        r = e * row["ret"] + (1 - e) * alt
        r -= abs(e - prev_e) * DERISK_COST          # 曝險變動成本
        prev_e = e
        out.append(r)
    return np.array(out, float)


if __name__ == "__main__":
    from regime_switch_lab import build_regime
    eng = Engine()
    obs = build_factors()
    dual = eng.run(holdings_for(obs, "dual"))["monthly"].reset_index(drop=True)

    reg = build_regime(); rm = dict(zip(reg["date"], reg["bear"])); rd = sorted(rm)
    def bear_of(a):
        i = bisect.bisect_right(rd, a) - 1
        return bool(rm[rd[i]]) if i >= 0 else False

    nb = sum(bear_of(str(x)) for x in dual["as_of"])
    print(f"雙確認 {len(dual)} 月,其中 bear 月 {nb} ({nb/len(dual)*100:.0f}%)  來回成本已含\n")

    base = metrics(dual["ret"].values)
    bench = metrics(dual["bench"].dropna().values)
    # 注意:0050 指標用有 bench 的月;策略用全月。同窗比較看夏普即可。

    configs = [
        ("雙確認(原始)", None, None),
        ("bear→現金30%曝險", 0.30, "cash"),
        ("bear→現金0%(空手)", 0.00, "cash"),
        ("bear→轉0050", 0.00, "0050"),
        ("bear→半0050(50%)", 0.50, "0050"),
    ]
    cols = ["CAGR", "波動", "夏普", "Sortino", "Calmar", "MDD", "水下"]
    print(f"{'配置':<20}" + "".join(f"{c:>9}" for c in cols))
    print("-" * 83)
    for name, expo, asset in configs:
        r = dual["ret"].values if expo is None else apply_overlay(dual, bear_of, expo, asset)
        mt = metrics(r)
        print(f"{name:<20}" + "".join(f"{mt.get(c, float('nan')):>9.2f}" for c in cols))
    print(f"{'0050 買進持有':<20}" + "".join(f"{bench.get(c, float('nan')):>9.2f}" for c in cols))
    print("\n門檻:夏普 > 0050 且 MDD 不差於 0050 → 淨贏。Calmar 越高=每單位回撤換到越多報酬。")
