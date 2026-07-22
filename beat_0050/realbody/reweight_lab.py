# -*- coding: utf-8 -*-
"""reweight_lab.py — 真身五面綜合分「重配權重」實驗 (B+多頭歸因共同指向的上修槓桿)。
================================================================================
發現:App綜合分把0.27權重押在動能(多頭IC負、有害)、0.15在籌碼(雜訊),真引擎價值/基本面被低配。
本實驗把 realbody_scores 的五面分數用不同權重**線性重組**(不重跑PIT),測「重配能否把真身推回1.0+」。

紀律(避免grid-search過擬合):
  · IC加權方案的權重**只從 train窗(2005-2018)導出**,在 test窗(2019-2026)是真OOS。
  · 其餘方案為**預註冊**的原則性配置(依歸因邏輯先定,非事後挑)。
  · 全部方案 full/train/test 三窗都報,不藏。含息+成本+定案風控(多軸階梯+確認3d)+對0050。
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

from beat_0050.honest_backtest import Engine, OBS_ALPHA
from regime_signal_lab import build_regime_features
from regime_hysteresis_lab import ladder_expo_daily, apply_daily_expo, metrics

RB = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"
FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
FLAB = {"f_fund": "基本面", "f_val": "估值", "f_tech": "技術", "f_mom": "動能", "f_whale": "籌碼"}
TRAIN_END = "2018-12-31"
TOP_PCT = 20


def win_sharpe(as_ofs, rets, lo, hi):
    a = np.array([str(x) for x in as_ofs]); r = np.asarray(rets, float)
    mask = (a >= lo) & (a <= hi)
    return metrics(r[mask]).get("夏普", np.nan)


def holdings_from(rb, wcol):
    out = {}
    for a, x in rb.groupby("as_of"):
        k = max(1, int(len(x) * TOP_PCT / 100))
        out[a] = x.nlargest(k, wcol)["stock_id"].tolist()
    return out


if __name__ == "__main__":
    rb = pd.read_parquet(RB)
    rb["as_of"] = rb["as_of"].astype(str); rb["stock_id"] = rb["stock_id"].astype(str)
    for c in FACES:
        rb[c] = pd.to_numeric(rb[c], errors="coerce").fillna(rb[c].median())
    obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "fwd"])
    obs["as_of"] = obs["as_of"].astype(str); obs["stock_id"] = obs["stock_id"].astype(str)
    rb = rb.merge(obs, on=["as_of", "stock_id"], how="left")

    # ---- 各面 IC(train窗導出) ----
    print("=" * 64)
    print("各面排序力 IC (train 2005-2018 導出;負=多頭有害)")
    print("=" * 64)
    ic_train = {}
    tr = rb[rb["as_of"] <= TRAIN_END]
    for f in FACES:
        ics = [g[f].rank(pct=True).corr(g["fwd"].rank(pct=True))
               for _, g in tr.groupby("as_of") if len(g) >= 30 and g["fwd"].notna().any()]
        ic_train[f] = float(np.nanmean(ics))
        print(f"  {FLAB[f]:<6}{ic_train[f]:+.4f}")

    # IC加權(train):負IC歸零,正規化
    pos = {f: max(0.0, ic_train[f]) for f in FACES}
    tot = sum(pos.values()) or 1.0
    w_ic = {f: pos[f] / tot for f in FACES}

    # ---- 預註冊權重方案 (f_fund,f_val,f_tech,f_mom,f_whale) ----
    SCHEMES = {
        "現行balanced": {"f_fund": .31, "f_val": .08, "f_tech": .19, "f_mom": .27, "f_whale": .15},
        "去動能雜訊":    {"f_fund": .40, "f_val": .25, "f_tech": .25, "f_mom": .00, "f_whale": .10},
        "價值基本面重":  {"f_fund": .45, "f_val": .35, "f_tech": .15, "f_mom": .00, "f_whale": .05},
        "IC加權(train)": w_ic,
    }

    eng = Engine()
    feat = build_regime_features(); dates = feat["date"].tolist()
    bench = eng.run(holdings_from(rb.assign(_w=rb["f_fund"]), "_w"))["monthly"]  # 只為取 bench 欄
    bench = bench.reset_index(drop=True)

    print("\n" + "=" * 76)
    print("重配權重 → 真身top20% + 定案風控(階梯確認3d) 全循環 vs 0050")
    print("=" * 76)
    print(f"{'方案':<16}{'權重(基/估/技/動/籌)':<24}{'全期夏普':>9}{'train':>8}{'test':>8}{'MDD':>8}")
    print("-" * 76)
    # 0050 benchmark 三窗
    b_full = metrics(bench["bench"].values).get("夏普", np.nan)
    b_tr = win_sharpe(bench["as_of"], bench["bench"].values, "2005-01-01", TRAIN_END)
    b_te = win_sharpe(bench["as_of"], bench["bench"].values, "2019-01-01", "2026-12-31")

    for name, w in SCHEMES.items():
        rb["_c"] = sum(w.get(f, 0) * rb[f] for f in FACES)
        run = eng.run(holdings_from(rb, "_c"))["monthly"].reset_index(drop=True)
        ov = apply_daily_expo(run, dates, ladder_expo_daily(feat, 3, 3))
        full = metrics(ov).get("夏普", np.nan)
        trs = win_sharpe(run["as_of"], ov, "2005-01-01", TRAIN_END)
        tes = win_sharpe(run["as_of"], ov, "2019-01-01", "2026-12-31")
        mdd = metrics(ov).get("MDD", np.nan)
        wstr = "/".join(f"{w.get(f,0)*100:.0f}" for f in FACES)
        print(f"{name:<16}{wstr:<24}{full:>9.2f}{trs:>8.2f}{tes:>8.2f}{mdd:>8.0f}")
    print(f"{'0050買進持有':<16}{'':<24}{b_full:>9.2f}{b_tr:>8.2f}{b_te:>8.2f}{'-54':>8}")
    print("\n→ IC加權(train)的 test欄=真OOS(權重只用2005-2018導出)。全期夏普>0.69=淨贏0050。")
