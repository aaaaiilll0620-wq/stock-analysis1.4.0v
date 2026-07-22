# -*- coding: utf-8 -*-
"""single_stock_dca_test.py — 單押龍頭 DCA vs 0050:台積電/聯發科的真實代價。
================================================================================
使用者問:定存龍頭(2330台積/2454聯發)這種「倒不了」的公司如何?
測各起始年 DCA 每月5000 的 MWRR / 最大回撤 / 最長套牢月數,對比 0050。
凸顯單股「沒自癒」的風險:聯發科 2011 起的失落七年會很明顯。

個股總報酬 = 月價格報酬 + 殖利率/12(近似補息,同誠實引擎);0050 用還原序列(exact)。
誠實邊界:近似補息、未含個股零股價差、倖存者(這兩檔是活下來的)。回測≠未來,非投資建議。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from beat_0050.honest_backtest import TEJ_CACHE
from core.dca_calc import simulate_dca, mwrr_annual

BENCH_TR = Path(__file__).resolve().parents[2] / "data" / "research_base" / "benchmark" / "0050_tr.parquet"
# 0050_tr 在 beat_0050/data;修正路徑
BENCH_TR = Path(__file__).resolve().parents[1] / "data" / "benchmark" / "0050_tr.parquet"
STOCKS = {"2330": "台積電", "2454": "聯發科"}


def stock_monthly_tr(sid: str) -> pd.Series:
    d = pd.read_parquet(TEJ_CACHE / "price_valuation" / f"{sid}.parquet",
                        columns=["date", "close", "dividend_yield_TSE"])
    d["date"] = pd.to_datetime(d["date"]); d = d.sort_values("date").set_index("date")
    mc = d["close"].resample("ME").last()
    dy = pd.to_numeric(d["dividend_yield_TSE"], errors="coerce").resample("ME").last().fillna(0)
    pr = mc.pct_change()
    pr[pr.abs() > 0.6] = np.nan                       # 濾分割/異常
    tr = pr + dy / 100.0 / 12.0                        # 補息近似
    tr.index = tr.index.strftime("%Y-%m")
    return tr.dropna()


def bench_monthly_tr() -> pd.Series:
    b = pd.read_parquet(BENCH_TR)
    b["date"] = pd.to_datetime(b["date"]); b = b.sort_values("date").set_index("date")
    mc = b["adj_close"].resample("ME").last()
    tr = mc.pct_change().dropna()
    tr.index = tr.index.strftime("%Y-%m")
    return tr


def max_underwater(rets):
    r = np.asarray(rets, float) / 100.0
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(eq)
    uw = eq < peak * (1 - 1e-9)
    L = c = 0
    for u in uw:
        c = c + 1 if u else 0; L = max(L, c)
    return L


if __name__ == "__main__":
    series = {name: stock_monthly_tr(sid) for sid, name in STOCKS.items()}
    series["0050"] = bench_monthly_tr()
    # 對齊共同月份
    idx = sorted(set.intersection(*[set(s.index) for s in series.values()]))
    for k in series:
        series[k] = series[k].reindex(idx)

    print("每月 5000 DCA:MWRR / 過程最大回撤 / 最長套牢(月)")
    print("(個股近似補息;0050還原exact;2330/2454為倖存者)\n")
    for yr in ["2005", "2010", "2015", "2020"]:
        sub_idx = [d for d in idx if d >= f"{yr}-01"]
        print(f"── {yr} 起 ({len(sub_idx)} 月) ──")
        print(f"  {'標的':<8}{'MWRR':>8}{'最大回撤':>9}{'最長套牢':>9}{'期末/投入':>10}")
        for name in ["台積電", "聯發科", "0050"]:
            v = series[name].reindex(sub_idx).values
            v = v[~np.isnan(v)]
            r = simulate_dca(list(v * 100), 5000)   # v 是小數,轉%給 simulate
            mw = mwrr_annual(list(v * 100), 5000, r["final"])
            uw = max_underwater(v * 100)
            print(f"  {name:<8}{mw:>7.1f}%{r['mdd']:>8.0f}%{uw:>8}月{r['final']/r['invested']:>9.2f}倍")
        print()
