# -*- coding: utf-8 -*-
"""existing_composite.py — 把**生產在跑的**選股層(綜合分/c2/雙確認)餵進含息0050引擎跑全循環。
================================================================================
問題:原策略當初判「輸0050」,是在 2019-26 窗測的——那正是0050夏普1.3~2.0的怪物年代。
現在有全循環含息0050(整體夏普~0.7,早年僅0.26~0.54)。本腳本用**誠實引擎+全循環**重判,
看原策略是不是本來就贏、只是被0050最猛的7年冤枉。

2026-07-29 (L3) 換身:綜合分這一腿改吃**真身分數**。
--------------------------------------------------------------------------------
以前:composite = 0.31 營收% + 0.08 估值% + 0.19 技術% + 0.27 動能% + 0.15 籌碼%
      —— 用 obs_alpha 的原始因子、套生產的權重「重建」的替身。
現在:real_composite = `core/scoring_manager` 實際算出來的五面加權分
      (realbody_scores.parquet,257 月 × 135,972 列,ADV≥2000萬,與 obs 母體 1:1 對齊)。

為什麼非換不可(2026-07-29 實測,同母體 134,125 stock-months):
  · 逐月橫斷面 Spearman(真身 vs 替身)僅 **0.632**,Top-20% 名單 Jaccard 僅 **0.35**
    —— 三分之二的選股不一樣。
  · 逐面更糟:基本面 **0.140**、動能面 **0.376**、估值面 0.391(技術 0.715、籌碼 0.701)。
  · 排序力方向相反:真身 IC **+0.0093**,替身 IC **−0.0036**。
生產的動能面早就重建過(近3~6月價格動能 + 營收動能 + 短線只作確認),替身還停在
`pct_change(20)` 的舊定義;基本面替身只用 revenue_yoy 一條腿代理整個面。
用替身測出來的「雙確認 vs 0050」測的不是生產在跑的東西。詳見 `docs/現況盤點_2026-07-29.md` §L3。

策略定義:
  real_composite = 生產真身綜合分 (五面加權,scoring_manager)
  c2             = mean(產業內估值%, 營收YoY%, 距52週高%, 100 − 動能%)
                   —— 對齊 `universe_screen_daily.c2_score`;這一腿生產與研究本來就同定義
  dual           = real_composite 前20% ∩ c2 前20% (雙確認,即 app「✨雙確認精選」)

替身仍留在 `build_proxy_factors()`,**只給 compare_realbody 做真身/替身相似度對照用**,
不得再拿去下任何生產判斷。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from beat_0050.honest_backtest import Engine, OBS_ALPHA, EXEC_RET, RET_COL, ERAS
from lab_paths import load_real_panel, add_c2, REAL_COMP_COL, REAL_FACES  # noqa: E402

TOP_PCT = 20


def build_factors(adv_floor: float = 2e7) -> pd.DataFrame:
    """**真身**面板:real_composite(生產五面分數)+ c2 + 可執行報酬線。

    回傳的欄位裡**沒有 `composite`** —— 漏改的呼叫端會直接 KeyError,
    不會靜默拿替身當真身跑(同 `lab_paths.load_panel` 丟掉 `fwd` 的理由)。
    adv_floor 低於 2000萬會 raise:realbody_scores 沒建到那麼低。
    """
    return load_real_panel(adv_floor=adv_floor, with_c2=True)


def build_proxy_factors(adv_floor: float = 2e7) -> pd.DataFrame:
    """⚠️ **替身**面板(舊版 proxy composite),只保留給真身/替身相似度對照。

    與真身逐月橫斷面 Spearman 0.632、Top-20% 名單 Jaccard 0.35、IC 方向相反
    → **不得用於任何生產判斷**。要跑策略請用 `build_factors()`。
    """
    obs = pd.read_parquet(OBS_ALPHA).drop(columns=["fwd"], errors="ignore")
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= adv_floor)]  # noqa: E712
    # 可執行報酬線;obs_alpha.fwd 有執行偏誤與漏日偏誤,見 honest_backtest 檔頭
    ex = pd.read_parquet(EXEC_RET, columns=["as_of", "stock_id", RET_COL])
    obs = obs.merge(ex, on=["as_of", "stock_id"], how="left").dropna(subset=[RET_COL])
    obs = obs.reset_index(drop=True)
    g = obs.groupby("as_of")
    def pct(s):
        return s.rank(pct=True) * 100
    obs["_f"] = g["revenue_yoy"].transform(pct)
    obs["_v"] = g["value_ind"].transform(pct)
    obs["_t"] = (g["high52_prox"].transform(pct) + g["bbp20"].transform(pct)) / 2
    obs["_m"] = g["momentum"].transform(pct)
    obs["_w"] = g["chip"].transform(pct)
    obs["composite"] = 0.31*obs["_f"] + 0.08*obs["_v"] + 0.19*obs["_t"] + 0.27*obs["_m"] + 0.15*obs["_w"]
    return add_c2(obs)


def holdings_for(obs: pd.DataFrame, which: str, comp_col: str = REAL_COMP_COL) -> dict:
    """which ∈ {composite, c2, dual} → {as_of: [stock_id]}

    comp_col 預設 `real_composite`(真身)。替身面板要明寫 `comp_col="composite"` ——
    不做自動 fallback,拿錯面板會直接 KeyError。
    """
    if comp_col not in obs.columns:
        raise KeyError(
            f"面板沒有 `{comp_col}` 欄(有的是:{sorted(c for c in obs.columns if 'compos' in c)})。\n"
            "真身面板用 build_factors() → real_composite;替身面板要明寫 comp_col='composite'。")
    out = {}
    for a, x in obs.groupby("as_of"):
        k = max(1, int(len(x) * TOP_PCT / 100))
        ca = set(x.nlargest(k, "c2").index)
        co = set(x.nlargest(k, comp_col).index)
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
    print(f"真身面板 {len(obs)} 列 / {obs['as_of'].nunique()} 月 (綜合分 = 生產 scoring_manager 五面分數)")
    print("策略對照:含息0050 · 全循環 · 元大6折+滑價 (來回0.72%)\n")

    strat_runs = {}
    for name in ["composite", "c2", "dual"]:
        h = holdings_for(obs, name)
        r = eng.run(h)
        strat_runs[name] = r["monthly"]

    # 0050 基準(任一 run 的 bench 欄都一樣)
    base = strat_runs["dual"]
    bench_m = era_metrics(base, "bench")

    labels = {"composite": "真身綜合分", "c2": "純c2價值", "dual": "雙確認"}
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
