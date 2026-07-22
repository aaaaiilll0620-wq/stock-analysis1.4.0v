# -*- coding: utf-8 -*-
"""regime_hysteresis_lab.py — 攻 2022 破口:多軸階梯 + 遲滯(不對稱確認),專治 whipsaw。
================================================================================
發現(regime_signal_lab):多軸階梯全期夏普1.01最強,但**2022空頭-1.13比0050(-0.49)還慘**——
碎波陰跌把 MA50 whipsaw(賣低→追反彈→反彈失敗→再賣)。本腳本加**遲滯**:

  不對稱確認 = 偵測危險快退(down_confirm小)、加碼回來要連續確認(up_confirm大),
  濾掉假反彈,避免鋸齒裡賣低買高。目標:2022 從 -1.13 拉到不輸 0050,其他時代不被拖累。

這不是「預測方向」,是「判斷當下該承受多少風險」的反應式曝險函式。無未來函數。
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
from beat_0050.honest_backtest import Engine, RF_ANNUAL, ERAS
from existing_composite import build_factors, holdings_for
from regime_signal_lab import build_regime_features, metrics, era_sharpe

DERISK_COST = 0.285


def debounce(cond: np.ndarray, up_confirm: int, down_confirm: int) -> np.ndarray:
    """cond=True 表『站上MA(risk-on)』。翻到 True 需連續 up_confirm 天;翻到 False 需連續 down_confirm 天。"""
    state = np.empty(len(cond), bool)
    s = bool(cond[0]); up = dn = 0
    for i, c in enumerate(cond):
        if c:
            up += 1; dn = 0
        else:
            dn += 1; up = 0
        if not s and up >= up_confirm:
            s = True
        elif s and dn >= down_confirm:
            s = False
        state[i] = s
    return state


def ladder_expo_daily(feat: pd.DataFrame, up_confirm: int, down_confirm: int) -> np.ndarray:
    """多軸階梯 + 遲滯:三條 MA 各自去抖動後的 above 狀態,平均成曝險∈{0,1/3,2/3,1}。"""
    s50 = debounce((feat["ew"] >= feat["ma50"]).values, up_confirm, down_confirm)
    s100 = debounce((feat["ew"] >= feat["ma100"]).values, up_confirm, down_confirm)
    s200 = debounce((feat["ew"] >= feat["ma200"]).values, up_confirm, down_confirm)
    return (s50.astype(float) + s100 + s200) / 3.0


def apply_daily_expo(dual: pd.DataFrame, dates, expo_daily) -> np.ndarray:
    cash = RF_ANNUAL / 12.0
    out, prev = [], 1.0
    for _, row in dual.iterrows():
        i = bisect.bisect_right(dates, str(row["as_of"])) - 1
        e = float(expo_daily[i]) if i >= 0 else 1.0
        out.append(e * row["ret"] + (1 - e) * cash - abs(e - prev) * DERISK_COST)
        prev = e
    return np.array(out, float)


if __name__ == "__main__":
    eng = Engine()
    obs = build_factors()
    dual = eng.run(holdings_for(obs, "dual"))["monthly"].reset_index(drop=True)
    feat = build_regime_features()
    dates = feat["date"].tolist()
    bench = dual["bench"].values

    # (up_confirm 加碼確認天, down_confirm 減碼確認天)
    configs = [
        ("多軸階梯(原始)",      1, 1),
        ("+對稱確認3d",        3, 3),
        ("+慢回補5d/降1",      5, 1),
        ("+慢回補10d/降1",     10, 1),
        ("+慢回補10d/降2",     10, 2),
        ("+慢回補15d/降2",     15, 2),
    ]
    series = {}
    for name, up, dn in configs:
        series[name] = apply_daily_expo(dual, dates, ladder_expo_daily(feat, up, dn))

    cols = ["CAGR", "波動", "夏普", "Sortino", "Calmar", "MDD", "水下"]
    print("=" * 82)
    print("全循環頭對頭 — 多軸階梯 + 遲滯 (目標:全期不掉、2022 補起來)")
    print("=" * 82)
    print(f"{'配置':<18}" + "".join(f"{c:>9}" for c in cols))
    print("-" * 81)
    for name, _, _ in configs:
        m = metrics(series[name])
        print(f"{name:<18}" + "".join(f"{m.get(c, float('nan')):>9.2f}" for c in cols))
    mb = metrics(bench)
    print(f"{'0050買進持有':<18}" + "".join(f"{mb.get(c, float('nan')):>9.2f}" for c in cols))

    print("\n" + "=" * 82)
    print("逐時代夏普 — 重點看 2022 那格能不能從 -1.13 拉起來,其他時代別掉")
    print("=" * 82)
    es_b = era_sharpe(dual["as_of"], bench)
    names = [c[0] for c in configs]
    print(f"{'時代':<16}" + "".join(f"{n:>16}" for n in names) + f"{'0050':>8}")
    for ename, _, _ in ERAS:
        row = f"{ename:<16}"
        for n in names:
            row += f"{era_sharpe(dual['as_of'], series[n])[ename]:>16.2f}"
        row += f"{es_b[ename]:>8.2f}"
        print(row)
    row = f"{'全期':<16}"
    for n in names:
        row += f"{era_sharpe(dual['as_of'], series[n])['全期']:>16.2f}"
    print(row + f"{es_b['全期']:>8.2f}")
