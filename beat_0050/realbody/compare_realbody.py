# -*- coding: utf-8 -*-
"""compare_realbody.py — B核心對照:真身綜合分 vs proxy vs 0050 (全循環,含息)。
================================================================================
回答兩個問題:
  (1) 我們一路用的 proxy composite,跟 App 真身綜合分**像不像**?(逐月排序相關 + 選股重疊)
  (2) 換成真身綜合分,救專案結論(淨贏0050)**還成立嗎**?(真身 top20% ± 風控 vs 0050)

真身分數來自 realbody_scores.parquet(build_realbody_scores 產);proxy 來自 existing_composite;
含息報酬/0050/風控疊加沿用 beat_0050 既有引擎。蘋果對蘋果(同母體 stock-months)。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

from beat_0050.honest_backtest import Engine, ERAS, RF_ANNUAL
from existing_composite import build_factors, holdings_for
from regime_signal_lab import build_regime_features
from regime_hysteresis_lab import ladder_expo_daily, apply_daily_expo, metrics

RB = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"
TOP_PCT = 20


def era_sharpe(as_ofs, rets):
    df = pd.DataFrame({"a": [str(x) for x in as_ofs], "r": rets})
    out = {}
    for name, s, e in ERAS:
        sub = df[(df["a"] >= s) & (df["a"] <= e)]
        out[name] = metrics(sub["r"].values).get("夏普", np.nan)
    out["全期"] = metrics(df["r"].values).get("夏普", np.nan)
    return out


def real_holdings(rb: pd.DataFrame, by="real_composite") -> dict:
    out = {}
    for a, x in rb.groupby("as_of"):
        x = x.dropna(subset=[by])
        k = max(1, int(len(x) * TOP_PCT / 100))
        out[a] = x.nlargest(k, by)["stock_id"].tolist()
    return out


if __name__ == "__main__":
    rb = pd.read_parquet(RB)
    rb["as_of"] = rb["as_of"].astype(str)
    rb["stock_id"] = rb["stock_id"].astype(str)
    obs = build_factors()
    obs["as_of"] = obs["as_of"].astype(str); obs["stock_id"] = obs["stock_id"].astype(str)

    # ---- (1) 真身 vs proxy 相似度 ----
    m = rb.merge(obs[["as_of", "stock_id", "composite", "c2", "fwd"]], on=["as_of", "stock_id"], how="inner")
    print("=" * 68)
    print("(1) 真身綜合分 vs proxy — 像不像?")
    print("=" * 68)
    corrs, ic_real, ic_proxy = [], [], []
    for a, g in m.groupby("as_of"):
        if len(g) < 30:
            continue
        corrs.append(g["real_composite"].rank().corr(g["composite"].rank()))
        fwdp = g["fwd"].rank(pct=True)
        ic_real.append(g["real_composite"].rank(pct=True).corr(fwdp))
        ic_proxy.append(g["composite"].rank(pct=True).corr(fwdp))
    print(f"逐月排序相關 (真身 vs proxy): 平均 {np.nanmean(corrs):.3f} (中位 {np.nanmedian(corrs):.3f})")
    print(f"  → 1=完全一致, 0=無關。越高表 proxy 越接近真身。")
    print(f"排序力 IC vs 未來報酬:  真身 {np.nanmean(ic_real):+.4f}   proxy {np.nanmean(ic_proxy):+.4f}")

    # 選股重疊 (各自 top20%)
    jac = []
    for a, g in m.groupby("as_of"):
        if len(g) < 30:
            continue
        k = max(1, int(len(g) * TOP_PCT / 100))
        R = set(g.nlargest(k, "real_composite")["stock_id"])
        P = set(g.nlargest(k, "composite")["stock_id"])
        jac.append(len(R & P) / len(R | P))
    print(f"Top-20% 選股重疊 (Jaccard): 平均 {np.nanmean(jac):.2f}  (0=完全不同, 1=完全相同)")

    # ---- (2) 真身綜合分還贏不贏 0050 ----
    eng = Engine()
    feat = build_regime_features(); dates = feat["date"].tolist()

    h_real = real_holdings(rb)
    h_proxy_dual = holdings_for(obs, "dual")
    runs = {"真身top20%": eng.run(h_real)["monthly"].reset_index(drop=True),
            "proxy雙確認": eng.run(h_proxy_dual)["monthly"].reset_index(drop=True)}
    bench = runs["proxy雙確認"]["bench"].values

    # 真身 + 定案風控 (多軸階梯+確認3d)
    rr = runs["真身top20%"]
    real_over = apply_daily_expo(rr, dates, ladder_expo_daily(feat, 3, 3))

    print("\n" + "=" * 68)
    print("(2) 全循環績效 (含息+成本) vs 0050 — 真身還贏不贏?")
    print("=" * 68)
    cols = ["CAGR", "波動", "夏普", "Sortino", "Calmar", "MDD"]
    print(f"{'策略':<22}" + "".join(f"{c:>9}" for c in cols))
    print("-" * 76)
    series = {"proxy雙確認(原始)": runs["proxy雙確認"]["ret"].values,
              "真身top20%(原始)": rr["ret"].values,
              "真身top20%+階梯確認3d": real_over}
    for name, s in series.items():
        mt = metrics(s)
        print(f"{name:<22}" + "".join(f"{mt.get(c, float('nan')):>9.2f}" for c in cols))
    mb = metrics(bench)
    print(f"{'0050買進持有':<22}" + "".join(f"{mb.get(c, float('nan')):>9.2f}" for c in cols))

    # ---- 逐時代 (真身+風控 vs 0050) ----
    print("\n" + "=" * 68)
    print("(3) 逐時代夏普 — 真身top20%+風控 vs 0050")
    print("=" * 68)
    es_real = era_sharpe(rr["as_of"], real_over)
    es_b = era_sharpe(rr["as_of"], bench)
    print(f"{'時代':<16}{'真身+風控':>10}{'0050':>9}{'勝?':>6}")
    for name, _, _ in ERAS:
        win = "✅" if es_real[name] > es_b[name] else "❌"
        print(f"{name:<16}{es_real[name]:>10.2f}{es_b[name]:>9.2f}{win:>6}")
    win = "✅" if es_real['全期'] > es_b['全期'] else "❌"
    print(f"{'全期':<16}{es_real['全期']:>10.2f}{es_b['全期']:>9.2f}{win:>6}")
