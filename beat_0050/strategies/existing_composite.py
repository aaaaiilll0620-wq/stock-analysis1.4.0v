# -*- coding: utf-8 -*-
"""existing_composite.py — 救專案:把原策略(綜合分/c2/雙確認)餵進含息0050引擎跑全循環。
================================================================================
問題:原策略當初判「輸0050」,是在 2019-26 窗測的——那正是0050夏普1.3~2.0的怪物年代。
現在有全循環含息0050(整體夏普~0.7,早年僅0.26~0.54)。本腳本用**誠實引擎+全循環**重判,
看原策略是不是本來就贏、只是被0050最猛的7年冤枉。

策略定義完全沿用 scripts/equity_curve_lab.py (app 的 proxy composite):
  composite = 0.31 營收 + 0.08 價值 + 0.19 技術 + 0.27 動能 + 0.15 籌碼 (百分位)
  c2        = (價值 + 營收 + 距52週高 + 反動能) / 4
  dual      = composite 前20% ∩ c2 前20% (雙確認)
差別:基準從「等權母體均值」換成「含息0050買進持有」,個股報酬含息(引擎內建)。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from beat_0050.honest_backtest import Engine, OBS_ALPHA, ERAS

TOP_PCT = 20


def build_factors() -> pd.DataFrame:
    obs = pd.read_parquet(OBS_ALPHA)
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= 2e7)].copy().reset_index(drop=True)  # noqa: E712
    g = obs.groupby("as_of")
    def pct(s):
        return s.rank(pct=True) * 100
    obs["_f"] = g["revenue_yoy"].transform(pct)
    obs["_v"] = g["value_ind"].transform(pct)
    obs["_t"] = (g["high52_prox"].transform(pct) + g["bbp20"].transform(pct)) / 2
    obs["_m"] = g["momentum"].transform(pct)
    obs["_w"] = g["chip"].transform(pct)
    obs["composite"] = 0.31*obs["_f"] + 0.08*obs["_v"] + 0.19*obs["_t"] + 0.27*obs["_m"] + 0.15*obs["_w"]
    obs["c2"] = (obs["_v"] + obs["_f"] + g["high52_prox"].transform(pct) + (100 - obs["_m"])) / 4
    return obs


def holdings_for(obs: pd.DataFrame, which: str) -> dict:
    """which ∈ {composite, c2, dual} → {as_of: [stock_id]}"""
    out = {}
    for a, x in obs.groupby("as_of"):
        k = max(1, int(len(x) * TOP_PCT / 100))
        ca = set(x.nlargest(k, "c2").index)
        co = set(x.nlargest(k, "composite").index)
        idx = {"composite": co, "c2": ca, "dual": ca & co}[which]
        if idx:
            out[a] = x.loc[list(idx), "stock_id"].tolist()
    return out


def era_metrics(m: pd.DataFrame, col: str) -> dict:
    """m: run() 月度表; col ∈ {ret, bench}. 回各時代 + 全期指標。"""
    def calc(r):
        r = np.asarray(r, float) / 100.0
        r = r[~np.isnan(r)]
        if len(r) < 6:
            return None
        eq = np.cumprod(1 + r); n = len(r)
        cagr = (eq[-1] ** (12 / n) - 1) * 100
        vol = r.std(ddof=1) * np.sqrt(12) * 100
        sharpe = (cagr - 1.0) / vol if vol else np.nan
        dd = eq / np.maximum.accumulate(eq) - 1
        return {"cagr": cagr, "sharpe": sharpe, "mdd": dd.min() * 100}
    res = {}
    for name, s, e in ERAS:
        sub = m[(m["as_of"].astype(str) >= s) & (m["as_of"].astype(str) <= e)]
        res[name] = calc(sub[col].values)
    res["全期"] = calc(m[col].values)
    return res


if __name__ == "__main__":
    eng = Engine()
    obs = build_factors()
    print("策略對照:含息0050 · 全循環 · 元大6折+滑價 (來回0.57%)\n")

    strat_runs = {}
    for name in ["composite", "c2", "dual"]:
        h = holdings_for(obs, name)
        r = eng.run(h)
        strat_runs[name] = r["monthly"]

    # 0050 基準(任一 run 的 bench 欄都一樣)
    base = strat_runs["dual"]
    bench_m = era_metrics(base, "bench")

    labels = {"composite": "綜合分", "c2": "純c2價值", "dual": "雙確認"}
    header = f"{'時代':<16}" + "".join(f"{labels[n]:>10}" for n in ['composite','c2','dual']) + f"{'0050含息':>10}"
    for metric, tag in [("sharpe", "夏普"), ("cagr", "CAGR%"), ("mdd", "MDD%")]:
        print(f"\n===== {tag} =====")
        print(header)
        eras_all = [e[0] for e in ERAS] + ["全期"]
        strat_m = {n: era_metrics(strat_runs[n], "ret") for n in strat_runs}
        for era in eras_all:
            row = f"{era:<16}"
            for n in ['composite', 'c2', 'dual']:
                v = strat_m[n].get(era)
                row += f"{(v[metric] if v else float('nan')):>10.2f}"
            bv = bench_m.get(era)
            row += f"{(bv[metric] if bv else float('nan')):>10.2f}"
            print(row)

    # 全期淨贏判定 (夏普)
    print("\n" + "=" * 60)
    b = bench_m["全期"]["sharpe"]
    for n in ['composite', 'c2', 'dual']:
        sm = era_metrics(strat_runs[n], "ret")["全期"]["sharpe"]
        print(f"{labels[n]:<10} 全期夏普 {sm:.2f}  vs 0050 {b:.2f}  → {'✅贏' if sm > b else '❌輸'}")
