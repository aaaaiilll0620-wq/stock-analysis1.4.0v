# -*- coding: utf-8 -*-
"""technical_mean_reversion_lab.py — 技術指標負 IC 機制檢驗
================================================================================
預註冊:`docs/預註冊_技術指標負IC機制檢驗.md`(2026-08-10 凍結)。本腳本只**執行**
該文件寫死的協定,不重新決定門檻/視野/因子。任何要改動的念頭,先回去讀
`docs/研究紀律_ResearchDiscipline.md` §2。

研究問題:法人賣轉買、RSI14、布林%B、MA偏離在本專案為何呈負 IC?
是短期均值回歸(H1)、universe 條件(H4:dual100 品質池是否翻正)、訊號本身滯後(H2,
本輪不執行)、還是單純無 alpha?

範圍(凍結,見預註冊 §5 / §3):
  · 視野:T+1(`fwd_t1`,主) / T+20(`fwd_x`,主) / T+60(`fwd_x60`,主);
    T+2(`fwd_t2`)僅供敏感度,不進判定。不用 `obs_alpha.fwd` / `exec_ret.fwd_cc`。
  · 技術因子:`rsi14` / `bbp20` / `ma_gap60`(obs_alpha 既有欄,零新計算)。KD 不測。
  · 法人賣轉買:沿用 `inst_reversal_lab` 既有 4 態分類(chip 20日 vs chip5),
    連續版用 `rev_score = chip5 - chip`(同 `inst_reversal_lab.by_era` 既有作法)。
  · 母體:Wide = ADV≥2000萬(與 `inst_reversal_lab` 預設 / `REALBODY_ADV_FLOOR` 同慣例);
    dual100 primary = `high52_lab.dual_confirm_mask` 產出的 ~48 檔實際持股遮罩
    (real_composite Top20% ∩ c2 Top20%,ADV≥100萬)。
  · H2(event study,需日頻資料)、H3 新分態(7 態 lifecycle)本輪不執行。
  · H6 分桶規則:同月橫斷面中位數分高/低(median split,零自由參數)。
  · H8 regime:`alpha_gate_lab.regime()` 的「Wide 池 mom60 橫斷面均值正負」規則,
    套用到全樣本(規則不變,只是延伸應用範圍)。

用法:
    python scripts/technical_mean_reversion_lab.py              # 全部(H1/H4/H5/H6/H7/H8)
    python scripts/technical_mean_reversion_lab.py --part h1
================================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))            # lab_paths, inst_reversal_lab
sys.path.insert(0, str(PROJ / "beat_0050" / "strategies"))           # high52_lab, dual100_lab

from lab_paths import (OBS_ALPHA, EXEC_RET, ensure_base,             # noqa: E402
                       assert_unique, assert_no_row_growth)
from inst_reversal_lab import ERAS, classify as chip_classify, tstat  # noqa: E402
from high52_lab import Panel, dual_confirm_mask                      # noqa: E402
from dual100_lab import mask_to_holdings                             # noqa: E402

OUTDIR = PROJ / "research" / "technical_mean_reversion_lab"

# ---- 預註冊 §3 凍結參數 ----
WIDE_ADV_FLOOR = 2e7            # Wide 池門檻,與 inst_reversal_lab 預設 / REALBODY_ADV_FLOOR 同慣例
DUAL100_TIER = "100萬"          # dual_confirm_mask 的 tier key
HORIZONS = [("T+1", "fwd_t1"), ("T+20", "fwd_x"), ("T+60", "fwd_x60")]   # 主判定三點
PRIMARY_HORIZON = "T+20"        # H6/H7/H8/pool_comparison headline 用這個視野
SENSITIVITY_HORIZONS = [("T+2", "fwd_t2")]                               # 僅敏感度,不進判定
TECH_FACTORS = [("RSI14", "rsi14"), ("布林%B", "bbp20"), ("MA偏離", "ma_gap60")]
MIN_STOCKS_PER_MONTH = 20       # 與 inst_reversal_lab.ic_series 同門檻
MIN_MONTHS_FOR_T = 12           # 與 inst_reversal_lab --min-n 同門檻


# ==============================================================================
# 資料載入(唯一入口的延伸:同一份 obs_alpha ⋈ exec_ret,一次取多個視野欄)
# ==============================================================================
def load_multi_horizon_panel(adv_floor: float | None = None, listed_only: bool = True) -> pd.DataFrame:
    """等同 `lab_paths.load_panel()` 的合併邏輯(同樣的 assert_unique / assert_no_row_growth),
    只是一次取 fwd_t1/fwd_t2/fwd_x/fwd_x60 四個視野欄,避免對 obs_alpha 重複 IO三次。
    不使用 `obs_alpha.fwd`(反向偏誤,研究紀律 §1 規則1)、不使用 `exec_ret.fwd_cc`(對帳用)。
    """
    ensure_base()
    obs = pd.read_parquet(OBS_ALPHA)
    if listed_only and "listed_ok" in obs.columns:
        obs = obs[obs["listed_ok"] == True]                     # noqa: E712
    if adv_floor is not None:
        obs = obs[obs["adv20"] >= adv_floor]
    obs = obs.drop(columns=["fwd"], errors="ignore")
    obs["as_of"] = obs["as_of"].astype(str)
    obs["stock_id"] = obs["stock_id"].astype(str)
    assert_unique(obs, name="obs_alpha(過濾後)")

    ex = pd.read_parquet(EXEC_RET, columns=["as_of", "stock_id", "fwd_x", "fwd_x60", "fwd_t1", "fwd_t2"])
    ex["as_of"] = ex["as_of"].astype(str)
    ex["stock_id"] = ex["stock_id"].astype(str)
    assert_unique(ex, name="exec_ret")

    n0 = len(obs)
    out = obs.merge(ex, on=["as_of", "stock_id"], how="left")
    assert_no_row_growth(n0, len(out), "load_multi_horizon_panel")
    out["_inst_revscore"] = out["chip5"] - out["chip"]   # 同 inst_reversal_lab.by_era 既有連續版定義
    return out.reset_index(drop=True)


def build_dual100_pairs() -> tuple[set, dict]:
    """Primary dual100 池(預註冊 §3-D):`high52_lab.dual_confirm_mask` 的月度 ~48 檔實際
    持股遮罩,經 `dual100_lab.mask_to_holdings()` 轉成 {as_of: [stock_id]}。"""
    print("[dual100] 建 Panel(realbody_floor=1e6) ...")
    P = Panel(realbody_floor=1e6)
    mask = dual_confirm_mask(P, tier=DUAL100_TIER, top_pct=20, source="real")
    holdings = mask_to_holdings(P, mask)
    pairs = {(as_of, str(sid)) for as_of, sids in holdings.items() for sid in sids}
    sizes = {as_of: len(sids) for as_of, sids in holdings.items()}
    avg_n = np.mean(list(sizes.values())) if sizes else float("nan")
    print(f"[dual100] {len(sizes)} 月,平均每月 {avg_n:.1f} 檔(預期 ≈48)")
    return pairs, sizes


def attach_dual100_flag(df: pd.DataFrame, pairs: set) -> pd.DataFrame:
    df = df.copy()
    keys = list(zip(df["as_of"], df["stock_id"]))
    df["in_dual100"] = [k in pairs for k in keys]
    return df


def assign_era(as_of_series: pd.Series) -> pd.Series:
    out = pd.Series(index=as_of_series.index, dtype=object)
    for name, s, e in ERAS:
        m = (as_of_series >= s) & (as_of_series <= e)
        out[m] = name
    return out


def assign_regime(df: pd.DataFrame) -> pd.Series:
    """`alpha_gate_lab.regime()` 規則逐字重現:逐月對 Wide 池 mom60 取橫斷面均值,
    >0 → bull,否則 bear。用整個 df(呼叫端應傳入 Wide 池)算月均值,再映到每列。"""
    mkt = df.groupby("as_of")["mom60"].mean()
    bull_dates = set(mkt[mkt > 0].index)
    return np.where(df["as_of"].isin(bull_dates), "bull", "bear")


# ==============================================================================
# 通用統計:rank IC(月度)、t 檢定、十分位多空 LS10(同 26 因子掃描既有量尺)
# ==============================================================================
def ic_series(df: pd.DataFrame, factor_col: str, ret_col: str, min_n: int = MIN_STOCKS_PER_MONTH) -> pd.Series:
    def _ic(g):
        m = g[factor_col].notna() & g[ret_col].notna()
        if m.sum() < min_n:
            return np.nan
        return g.loc[m, factor_col].rank().corr(g.loc[m, ret_col].rank())
    sub = df[["as_of", factor_col, ret_col]]
    return sub.groupby("as_of").apply(_ic, include_groups=False).dropna()


def ic_stats(df: pd.DataFrame, factor_col: str, ret_col: str, min_n: int = MIN_STOCKS_PER_MONTH) -> dict:
    ic = ic_series(df, factor_col, ret_col, min_n)
    n = len(ic)
    return {"ic_mean": float(ic.mean()) if n else float("nan"),
            "ic_t": tstat(ic.to_numpy()) if n else float("nan"),
            "n_months": n}


def ls10_series(df: pd.DataFrame, factor_col: str, ret_col: str, min_n: int = MIN_STOCKS_PER_MONTH) -> pd.Series:
    def _spread(g):
        m = g[factor_col].notna() & g[ret_col].notna()
        gg = g.loc[m]
        if len(gg) < min_n:
            return np.nan
        try:
            q = pd.qcut(gg[factor_col], 10, labels=False, duplicates="drop")
        except ValueError:
            return np.nan
        if q.nunique() < 2:
            return np.nan
        top = gg.loc[q == q.max(), ret_col].mean()
        bot = gg.loc[q == q.min(), ret_col].mean()
        return top - bot
    sub = df[["as_of", factor_col, ret_col]]
    return sub.groupby("as_of").apply(_spread, include_groups=False).dropna()


def ls10_stats(df: pd.DataFrame, factor_col: str, ret_col: str, min_n: int = MIN_STOCKS_PER_MONTH) -> dict:
    s = ls10_series(df, factor_col, ret_col, min_n)
    n = len(s)
    return {"ls10_mean": float(s.mean()) if n else float("nan"),
            "ls10_t": tstat(s.to_numpy()) if n else float("nan"),
            "n_months": n}


# ==============================================================================
# H1 + H4 — horizon curve × (Wide, dual100_primary)
# ==============================================================================
def run_horizon_curve(wide: pd.DataFrame, dual: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 88 + "\nH1+H4 — horizon curve (Wide vs dual100_primary)\n" + "=" * 88)
    rows = []
    signals = TECH_FACTORS + [("法人賣轉買(rev_score=chip5-chip)", "_inst_revscore")]
    pools = [("wide", wide), ("dual100_primary", dual)]
    all_horizons = HORIZONS + SENSITIVITY_HORIZONS
    for label, ret_col in all_horizons:
        for sig_name, sig_col in signals:
            for pool_name, df in pools:
                n_valid = df[[sig_col, ret_col]].dropna().shape[0]
                if n_valid < MIN_STOCKS_PER_MONTH:
                    continue
                ic = ic_stats(df, sig_col, ret_col)
                l10 = ls10_stats(df, sig_col, ret_col)
                rows.append({"signal": sig_name, "factor_col": sig_col, "horizon": label,
                            "horizon_col": ret_col, "pool": pool_name,
                            "sensitivity_only": label not in [h for h, _ in HORIZONS],
                            "n_months": ic["n_months"], "ic_mean": round(ic["ic_mean"], 4),
                            "ic_t": round(ic["ic_t"], 2), "ls10_mean": round(l10["ls10_mean"], 3),
                            "ls10_t": round(l10["ls10_t"], 2)})
                print(f"{sig_name:<30}{label:<6}{pool_name:<16}n={ic['n_months']:>4}"
                      f"  IC={ic['ic_mean']:+.4f}(t={ic['ic_t']:+.2f})"
                      f"  LS10={l10['ls10_mean']:+.3f}(t={l10['ls10_t']:+.2f})")
    return pd.DataFrame(rows)


def build_pool_comparison(horizon_curve: pd.DataFrame) -> pd.DataFrame:
    """GPT 原規格 §四的 paired table:Factor | Wide IC | dual100 IC | ΔIC | Wide t | dual100 t,
    跨 §0 三個凍結主視野(T+1/T+20/T+60)。"""
    rows = []
    for label, _ in HORIZONS:
        sub = horizon_curve[horizon_curve["horizon"] == label]
        for sig in sub["signal"].unique():
            w = sub[(sub["signal"] == sig) & (sub["pool"] == "wide")]
            d = sub[(sub["signal"] == sig) & (sub["pool"] == "dual100_primary")]
            if w.empty or d.empty:
                continue
            w, d = w.iloc[0], d.iloc[0]
            rows.append({"signal": sig, "horizon": label,
                        "wide_ic": w["ic_mean"], "wide_t": w["ic_t"], "wide_n": w["n_months"],
                        "dual100_ic": d["ic_mean"], "dual100_t": d["ic_t"], "dual100_n": d["n_months"],
                        "delta_ic": round(d["ic_mean"] - w["ic_mean"], 4)})
    return pd.DataFrame(rows)


# ==============================================================================
# H6 — interaction(median split,零自由參數;僅 Wide pool,見預註冊理由)
# ==============================================================================
def run_interaction(wide: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 88 + "\nH6 — interaction (median split, Wide pool only)\n" + "=" * 88)
    rows = []
    combos = [("RSI14", "rsi14", "布林%B", "bbp20"),
             ("RSI14", "rsi14", "MA偏離", "ma_gap60"),
             ("布林%B", "bbp20", "MA偏離", "ma_gap60")]
    for label, ret_col in HORIZONS:
        df = wide[["as_of", "rsi14", "bbp20", "ma_gap60", ret_col]].dropna(
            subset=["rsi14", "bbp20", "ma_gap60", ret_col]).copy()
        med = df.groupby("as_of")[["rsi14", "bbp20", "ma_gap60"]].transform("median")
        hi = {"rsi14": df["rsi14"] >= med["rsi14"], "bbp20": df["bbp20"] >= med["bbp20"],
              "ma_gap60": df["ma_gap60"] >= med["ma_gap60"]}
        for na, ca, nb, cb in combos:
            for bhi, la in [(True, "高"), (False, "低")]:
                for bhi2, lb in [(True, "高"), (False, "低")]:
                    m = (hi[ca] == bhi) & (hi[cb] == bhi2)
                    g = df.loc[m]
                    n_months = g["as_of"].nunique()
                    if n_months < MIN_MONTHS_FOR_T:
                        continue
                    cell = g.groupby("as_of")[ret_col].mean()
                    rows.append({"combo": f"{na}×{nb}", "bucket": f"{na}{la}×{nb}{lb}",
                                "horizon": label, "n_months": n_months,
                                "avg_n_per_month": round(g.groupby("as_of").size().mean(), 1),
                                "mean_fwd": round(float(cell.mean()), 3), "t": round(tstat(cell.to_numpy()), 2)})
        # 三因子共振
        for r_hi, r_l in [(True, "高"), (False, "低")]:
            for b_hi, b_l in [(True, "高"), (False, "低")]:
                for m_hi, m_l in [(True, "高"), (False, "低")]:
                    mask = (hi["rsi14"] == r_hi) & (hi["bbp20"] == b_hi) & (hi["ma_gap60"] == m_hi)
                    g = df.loc[mask]
                    n_months = g["as_of"].nunique()
                    if n_months < MIN_MONTHS_FOR_T:
                        continue
                    cell = g.groupby("as_of")[ret_col].mean()
                    rows.append({"combo": "RSI14×布林%B×MA偏離",
                                "bucket": f"RSI14{r_l}×布林%B{b_l}×MA偏離{m_l}",
                                "horizon": label, "n_months": n_months,
                                "avg_n_per_month": round(g.groupby("as_of").size().mean(), 1),
                                "mean_fwd": round(float(cell.mean()), 3), "t": round(tstat(cell.to_numpy()), 2)})
    out = pd.DataFrame(rows)
    print(out.to_string(index=False) if len(out) else "(無足夠樣本的 bucket)")
    return out


# ==============================================================================
# H7 + H8 — era stability + regime(exploratory),限主視野 T+20,合併輸出
# ==============================================================================
def run_era_and_regime(wide: pd.DataFrame, dual: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 88 + "\nH7 era stability + H8 regime (exploratory) — 主視野 T+20\n" + "=" * 88)
    ret_col = dict(HORIZONS)[PRIMARY_HORIZON]
    rows = []
    signals = TECH_FACTORS + [("法人賣轉買(rev_score)", "_inst_revscore")]
    for pool_name, df0 in [("wide", wide), ("dual100_primary", dual)]:
        df = df0.copy()
        df["_era"] = assign_era(df["as_of"])
        df["_regime"] = assign_regime(wide) if pool_name == "wide" else np.nan
        # dual100 的 regime 標籤沿用 Wide 池同月份算出的 bull/bear(regime 是市場層級,非池層級)
        if pool_name != "wide":
            wide_regime = pd.Series(assign_regime(wide), index=wide.index)
            m = wide[["as_of"]].assign(_regime=wide_regime).drop_duplicates("as_of")
            df = df.merge(m, on="as_of", how="left", suffixes=("", "_dup"))
        for sig_name, sig_col in signals:
            for era_name, _, _ in ERAS:
                g = df[df["_era"] == era_name]
                if g.empty:
                    continue
                ic = ic_stats(g, sig_col, ret_col)
                if ic["n_months"] == 0:
                    continue
                rows.append({"signal": sig_name, "pool": pool_name, "split_type": "era",
                            "segment": era_name, "n_months": ic["n_months"],
                            "ic_mean": round(ic["ic_mean"], 4), "ic_t": round(ic["ic_t"], 2)})
            for regime_name in ["bull", "bear"]:
                g = df[df["_regime"] == regime_name]
                if g.empty:
                    continue
                ic = ic_stats(g, sig_col, ret_col)
                if ic["n_months"] == 0:
                    continue
                rows.append({"signal": sig_name, "pool": pool_name, "split_type": "regime",
                            "segment": regime_name, "n_months": ic["n_months"],
                            "ic_mean": round(ic["ic_mean"], 4), "ic_t": round(ic["ic_t"], 2)})
    out = pd.DataFrame(rows)
    print(out.to_string(index=False) if len(out) else "(無資料)")
    return out


# ==============================================================================
# main
# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="技術指標負 IC 機制檢驗(預註冊_技術指標負IC機制檢驗.md)")
    ap.add_argument("--part", choices=["all", "h1h4", "h6", "h7h8"], default="all")
    args = ap.parse_args()

    t0 = time.time()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print(f"[load] Wide 池(ADV≥{WIDE_ADV_FLOOR:,.0f}) ...")
    wide = load_multi_horizon_panel(adv_floor=WIDE_ADV_FLOOR)
    print(f"[load] Wide {len(wide):,} 列 / {wide['as_of'].nunique()} 月 "
          f"({wide['as_of'].min()} ~ {wide['as_of'].max()})")

    pairs, sizes = build_dual100_pairs()
    wide_flagged = attach_dual100_flag(wide, pairs)
    dual = wide_flagged[wide_flagged["in_dual100"]].copy()
    print(f"[load] dual100_primary(在 Wide 池內可辨識的列) {len(dual):,} 列 / "
          f"{dual['as_of'].nunique()} 月")

    horizon_curve = pd.DataFrame()
    pool_comparison = pd.DataFrame()
    interaction = pd.DataFrame()
    era_regime = pd.DataFrame()

    if args.part in ("all", "h1h4"):
        horizon_curve = run_horizon_curve(wide, dual)
        horizon_curve.to_csv(OUTDIR / "horizon_curve.csv", index=False, encoding="utf-8-sig")
        pool_comparison = build_pool_comparison(horizon_curve)
        pool_comparison.to_csv(OUTDIR / "pool_comparison.csv", index=False, encoding="utf-8-sig")
        print(f"\n→ horizon_curve.csv({len(horizon_curve)} 列)、"
              f"pool_comparison.csv({len(pool_comparison)} 列) 已寫")

    if args.part in ("all", "h6"):
        interaction = run_interaction(wide)
        interaction.to_csv(OUTDIR / "interaction_results.csv", index=False, encoding="utf-8-sig")
        print(f"\n→ interaction_results.csv({len(interaction)} 列) 已寫")

    if args.part in ("all", "h7h8"):
        era_regime = run_era_and_regime(wide, dual)
        era_regime.to_csv(OUTDIR / "era_results.csv", index=False, encoding="utf-8-sig")
        print(f"\n→ era_results.csv({len(era_regime)} 列) 已寫")

    print(f"\n完成,共 {time.time()-t0:.0f}s。結果目錄:{OUTDIR}")
    print("下一步:跑 scripts/technical_mean_reversion_lab_summary.py 產生 summary.csv + README.md"
          "(依 §4 判定門檻逐項讀 CSV 判讀,不在本腳本內混入判讀邏輯)。")


if __name__ == "__main__":
    main()
