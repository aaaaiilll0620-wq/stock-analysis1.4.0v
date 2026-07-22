# -*- coding: utf-8 -*-
"""build_dca_series.py — 產 DCA 計算機用的月報酬序列 (策略 + 0050,含息)。
================================================================================
策略 = 真身綜合分 top20% + 定案風控(多軸階梯+確認3d);0050 = 含息買進持有。
輸出 data/research_base/dca_series.parquet 欄位:as_of / strat_ret / bench_ret (%)。
App 的 DCA 分頁讀它做定期定額模擬 + MWRR,不必重跑重引擎。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

from beat_0050.honest_backtest import Engine
from regime_signal_lab import build_regime_features
from regime_hysteresis_lab import ladder_expo_daily, apply_daily_expo

RB = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"
OUT = Path(__file__).resolve().parents[2] / "data" / "research_base" / "dca_series.parquet"
TOP_PCT = 20


def real_holdings(rb):
    out = {}
    for a, x in rb.groupby("as_of"):
        k = max(1, int(len(x) * TOP_PCT / 100))
        out[a] = x.nlargest(k, "real_composite")["stock_id"].tolist()
    return out


if __name__ == "__main__":
    rb = pd.read_parquet(RB)
    rb["as_of"] = rb["as_of"].astype(str); rb["stock_id"] = rb["stock_id"].astype(str)
    rb["real_composite"] = pd.to_numeric(rb["real_composite"], errors="coerce")
    rb = rb.dropna(subset=["real_composite"])

    eng = Engine()
    run = eng.run(real_holdings(rb))["monthly"].reset_index(drop=True)
    feat = build_regime_features(); dates = feat["date"].tolist()
    strat = apply_daily_expo(run, dates, ladder_expo_daily(feat, 3, 3))   # 真身+定案風控

    out = pd.DataFrame({"as_of": run["as_of"].astype(str),
                        "strat_ret": strat,
                        "bench_ret": run["bench"].values})
    out = out.dropna(subset=["bench_ret"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)
    print(f"✅ {len(out)} 月 ({out['as_of'].min()} ~ {out['as_of'].max()}) → {OUT}")
    # 快速對照:一次投入複利倍數
    import numpy as np
    for c, lab in [("strat_ret", "策略"), ("bench_ret", "0050")]:
        g = np.prod(1 + out[c].values / 100)
        print(f"  {lab}: 一次投入 {g:.1f} 倍")
