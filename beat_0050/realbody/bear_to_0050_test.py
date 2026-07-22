# -*- coding: utf-8 -*-
"""bear_to_0050_test.py — 空頭時「轉現金」vs「轉0050」:一次投入 & DCA 兩情境。
================================================================================
使用者提問:空頭別抱現金、改抱 0050(有自癒、會反彈)如何?
測 真身top20% + 階梯確認3d 曝險,非曝險部位分別放 [現金 / 0050],對比純0050。
一次投入看夏普/MDD;DCA 看 MWRR/MDD(新錢空頭去向的差別)。
================================================================================
"""
from __future__ import annotations
import sys
import bisect
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

from beat_0050.honest_backtest import Engine, RF_ANNUAL
from beat_0050.realbody.build_dca_series import real_holdings
from regime_signal_lab import build_regime_features
from regime_hysteresis_lab import ladder_expo_daily, metrics
from core.dca_calc import simulate_dca, mwrr_annual

RB = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"


def blend(run, dates, expo_daily, alt):
    """非曝險部位放 alt('cash'|'bench')。回月報酬%序列。"""
    cash = RF_ANNUAL / 12.0
    out = []
    for _, row in run.iterrows():
        i = bisect.bisect_right(dates, str(row["as_of"])) - 1
        e = float(expo_daily[i]) if i >= 0 else 1.0
        a = (row["bench"] if alt == "bench" and not np.isnan(row["bench"]) else cash)
        out.append(e * row["ret"] + (1 - e) * a)
    return np.array(out, float)


if __name__ == "__main__":
    rb = pd.read_parquet(RB)
    rb["as_of"] = rb["as_of"].astype(str); rb["stock_id"] = rb["stock_id"].astype(str)
    rb["real_composite"] = pd.to_numeric(rb["real_composite"], errors="coerce")
    rb = rb.dropna(subset=["real_composite"])
    eng = Engine()
    run = eng.run(real_holdings(rb))["monthly"].reset_index(drop=True)
    feat = build_regime_features(); dates = feat["date"].tolist()
    expo = ladder_expo_daily(feat, 3, 3)

    series = {
        "空頭轉現金": blend(run, dates, expo, "cash"),
        "空頭轉0050": blend(run, dates, expo, "bench"),
        "純0050": run["bench"].values,
    }
    asof = run["as_of"].astype(str).values

    print("=" * 60)
    print("(1) 一次投入(含息全循環):夏普 / MDD / CAGR")
    print("=" * 60)
    print(f"{'配置':<14}{'夏普':>8}{'MDD':>8}{'CAGR':>8}")
    for name, s in series.items():
        m = metrics(s)
        print(f"{name:<14}{m.get('夏普',float('nan')):>8.2f}{m.get('MDD',float('nan')):>8.0f}{m.get('CAGR',float('nan')):>8.1f}")

    print("\n" + "=" * 60)
    print("(2) DCA 每月5000:MWRR / 過程最大回撤")
    print("=" * 60)
    for yr in ["2005", "2015"]:
        print(f"-- {yr} 起 --")
        mask = asof >= f"{yr}-01-01"
        for name, s in series.items():
            vals = np.array(s)[mask]
            vals = list(vals[~np.isnan(vals)])          # 濾末月 NaN
            r = simulate_dca(vals, 5000)
            mw = mwrr_annual(vals, 5000, r["final"])
            print(f"  {name:<12} MWRR {mw:>5.1f}%   回撤 {r['mdd']:>4.0f}%   期末 {r['final']:>12,.0f}")
