# -*- coding: utf-8 -*-
"""face_lineage_audit.py — 五維度「血緣 / 定義 / 資料完整性」靜態稽核(不調權重、不跑 OOS)

`face_audit.py` 問的是**效力**(IC/t/分時代);本檔問的是**這五個數字到底是什麼**:

  §1 量尺       —— 相異值、Top-20% 並列率、邊界堆積(0 / 100)、逐月標準差
  §2 有效權重   —— 名目權重 vs 排序變異佔比(未標準化的加權平均,名目≠有效)
  §3 合成層殘差 —— real_composite 是否等於 Σw·face?差在哪(regime / dyn / bucket 替換)
  §4 缺值語意   —— 缺值進到分數是 0(最差)、50(中性),還是 100(最好)
  §5 資訊重疊   —— c2 的四條腿 vs 五個面(尤其 c2 的 100−momentum% 與 f_mom)
  §6 排序穩定度 —— 逐月 rank 自相關(換手率的上游)

用法:python scripts/face_lineage_audit.py --adv 1e6
      python scripts/face_lineage_audit.py --adv 2e7 --part 3
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))      # repo root:part3 要 import core.regime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from lab_paths import RET_COL, REAL_COMP_COL, REAL_FACES, load_real_panel   # noqa: E402

# advisor 實際使用的五維名目權重(ScoringManager.MODES['balanced']['composite_weights'])
W = {"f_fund": 0.31, "f_val": 0.08, "f_tech": 0.19, "f_mom": 0.27, "f_whale": 0.15}
FACE2KEY = {"f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
            "f_mom": "momentum", "f_whale": "whale"}
LABEL = {"f_fund": "基本面", "f_val": "估值", "f_tech": "技術", "f_mom": "動能", "f_whale": "籌碼"}


def hr(t=""):
    print("\n" + "=" * 92)
    if t:
        print(t)
        print("=" * 92)


def part1(d: pd.DataFrame):
    hr("§1 量尺 —— 這五個數字分得開嗎")
    n = len(d)
    print(f"母體 {n:,} stock-months × {d['as_of'].nunique()} 月 × {d['stock_id'].nunique()} 檔\n")
    print(f"{'面':<8}{'相異值':>8}{'=0 %':>8}{'=100 %':>8}{'中位':>8}{'月內std':>9}"
          f"{'Top20並列%':>12}{'缺值%':>8}")
    for c in REAL_FACES + [REAL_COMP_COL]:
        s = d[c]
        nuniq = s.nunique()
        p0 = (s == 0).mean() * 100
        p100 = (s == 100).mean() * 100
        med = s.median()
        std_m = d.groupby("as_of")[c].std().mean()
        # Top-20% 並列率:每月取第 80 百分位為門檻,計算「剛好等於門檻值」的比例
        def tie(v):
            v = v.dropna()
            if len(v) < 20:
                return np.nan
            thr = v.quantile(0.80)
            top = v[v >= thr]
            return (top == thr).mean() * 100 if len(top) else np.nan
        tie_pct = d.groupby("as_of")[c].apply(tie).mean()
        nan_pct = s.isna().mean() * 100
        print(f"{LABEL.get(c, c):<8}{nuniq:>8,}{p0:>8.2f}{p100:>8.2f}{med:>8.1f}"
              f"{std_m:>9.2f}{tie_pct:>12.1f}{nan_pct:>8.2f}")
    print("\n讀法:相異值少 + 並列率高 = 該面在排序上其實只有少數幾格,誰入選由後續排序規則(股號序)決定。")
    print("      =0 / =100 的堆積量 = clipping 邊界被壓扁的觀測數。")


def part2(d: pd.DataFrame):
    hr("§2 名目權重 vs 有效權重(五面**未標準化**就直接加權平均)")
    print("advisor.advise():composite = Σ w·bucket / Σw,bucket 是原始 0–100 分,")
    print("沒有先做 z-score 或百分位化 → 分得越開的面,實際主導排序的力道越大。\n")
    tot_std = d.groupby("as_of")[REAL_COMP_COL].std().mean()
    print(f"{'面':<8}{'名目w':>8}{'月內std':>9}{'w×std':>9}{'有效權重':>10}{'與綜合分corr':>14}")
    contrib = {}
    for c in REAL_FACES:
        s_std = d.groupby("as_of")[c].std().mean()
        contrib[c] = W[c] * s_std
    tot = sum(contrib.values())
    for c in REAL_FACES:
        s_std = d.groupby("as_of")[c].std().mean()
        corr = d.groupby("as_of")[[c, REAL_COMP_COL]].apply(
            lambda g: g[c].rank().corr(g[REAL_COMP_COL].rank())).mean()
        print(f"{LABEL[c]:<8}{W[c]:>8.2f}{s_std:>9.2f}{contrib[c]:>9.3f}"
              f"{contrib[c]/tot:>10.2f}{corr:>14.3f}")
    print(f"\n綜合分本身月內 std = {tot_std:.2f}")


def part3(d: pd.DataFrame):
    hr("§3 合成層殘差 —— real_composite 真的等於 Σw·face 嗎")
    faces = d[REAL_FACES].to_numpy(float)
    w = np.array([W[c] for c in REAL_FACES])
    static = faces @ w / w.sum()
    resid = d[REAL_COMP_COL].to_numpy(float) - static
    a = np.abs(resid)
    print(f"殘差 = real_composite − Σw·face(靜態 balanced 權重、直接用面板存的五面分)")
    print(f"  |殘差| ≤0.01 : {(a <= 0.01).mean()*100:6.2f}%   ← 完全對得起來的比例")
    print(f"  |殘差| >0.5  : {(a > 0.5).mean()*100:6.2f}%")
    print(f"  |殘差| >2.0  : {(a > 2.0).mean()*100:6.2f}%")
    print(f"  |殘差| >5.0  : {(a > 5.0).mean()*100:6.2f}%")
    print(f"  殘差 中位 {np.median(resid):+.3f} / 平均 {resid.mean():+.3f} / "
          f"max {resid.max():+.2f} / min {resid.min():+.2f}")

    print("\n殘差有三個已知來源(都在 advisor.advise / score_store 裡,面板未存旗標):")
    print("  (a) regime_multipliers  —— 市場層級乘數(bear:動能1.5×、技術/籌碼0.3×、估值0.6×)")
    print("  (b) _dynamic_weights    —— 個股層級:強勢多頭排列 → 估值權重砍 60% 轉給動能/籌碼")
    print("  (c) bucket ≠ 存下來的面 —— 估值『資料不足』時 composite 用 50 但面板存原始分;")
    print("      洗盤(washout)時 composite 用 max(whale,60)+5 但面板存原始 whale")

    # (a) 用三組 regime 權重各自重算,看哪一組最貼近 → 反推該月實際用的是哪組
    from core.regime import REGIME_MULTIPLIERS
    cand = {}
    for reg, mult in REGIME_MULTIPLIERS.items():
        wr = np.array([W[c] * mult[FACE2KEY[c]] for c in REAL_FACES])
        cand[reg] = np.abs(d[REAL_COMP_COL].to_numpy(float) - faces @ wr / wr.sum())
    best = pd.DataFrame(cand).idxmin(axis=1)
    print("\n逐列最貼近的 regime 權重組(反推,非面板紀錄):")
    print("   " + str(best.value_counts(normalize=True).round(4).to_dict()))
    by_year = pd.DataFrame({"y": d["as_of"].str[:4], "reg": best}).groupby("y")["reg"] \
        .apply(lambda s: s.value_counts(normalize=True).round(2).to_dict())
    print("\n逐年分布(bear 乘數命中率高的年份 = 該年 regime 進了選股):")
    for y, v in by_year.items():
        print(f"   {y}  {v}")

    print("\n※ 結論寫法注意:面板只存了五面與 composite,**沒有存 dyn_weight / regime 欄**")
    print("   (score_store.COLUMNS 有這兩欄,build_realbody_scores._score_stock 沒有取)。")
    print("   所以殘差歸因只能反推,不能對帳 —— 這本身就是要修的血緣缺口。")


def part4(d: pd.DataFrame):
    hr("§4 缺值語意 —— 缺資料進到分數是 0(最差)、50(中性)還是 100(最好)")
    print("靜態追溯(core/backtest.build_pit_stockdata → core/fundamentals / valuation):\n")
    rows = [
        ("pe_vs_industry", "缺 PE → 填 10.0", "bounds lower=30 upper=10 → **100 分(最便宜)**",
         "❌ 缺值 = 最好分,佔 f_fund 的 0.20"),
        ("eps_cagr", "缺 EPS 成長 → 填 0.0", "bounds lower=0 upper=20 → **0 分(最差)**",
         "❌ 缺值 = 最差分,且因『有值』而計入 growth 平均"),
        ("net_income_growth", "缺 → 填 0.0", "只進獲利品質判斷,不直接計分", "⚠ 影響 quality_flag"),
        ("roe/net_margin/gross_margin/rev_cagr/debt/current_ratio", "None 保留",
         "_avg_present() 只對有值的取平均;整組皆缺 → 50", "✅ 中性"),
        ("valuation(整支)", "三條路徑皆無資料 → valuation_score=0.0、status='估值資料不足'",
         "advisor 用 **50** 當 bucket,但面板存的 f_val 是 **0.0**",
         "❌ 面板值 ≠ 合成用值"),
        ("whale washout", "洗盤尾聲 → bucket=min(100,max(whale,60)+5)",
         "面板存的 f_whale 是**未加成**的原始分", "❌ 面板值 ≠ 合成用值"),
    ]
    print(f"{'欄位':<52}{'缺值處置':<40}{'進到分數':<46}判定")
    for a, b, c, e in rows:
        print(f"{a:<52}{b:<40}{c:<46}{e}")

    print("\n實測(本面板):")
    v0 = (d["f_val"] == 0).mean() * 100
    print(f"  f_val == 0 的比例 {v0:.2f}%  ← 其中『估值資料不足』那部分,合成時其實是用 50 分")
    for c in REAL_FACES:
        s = d[c]
        print(f"  {LABEL[c]:<6} =0 {(s==0).mean()*100:6.2f}%   =100 {(s==100).mean()*100:6.2f}%   "
              f"=50 {(s==50).mean()*100:6.2f}%")


def part5(d: pd.DataFrame):
    hr("§5 資訊重疊 —— c2 的四條腿 vs 五個面")
    print("c2 = mean(value_ind%, revenue_yoy%, high52_prox%, 100 − momentum%)(層內百分位)\n")
    g = d.groupby("as_of")
    legs = {}
    for col in ["value_ind", "revenue_yoy", "high52_prox", "momentum"]:
        if col in d.columns:
            legs[col] = g[col].transform(lambda s: s.rank(pct=True) * 100)
    legs["100−momentum%"] = 100 - legs.pop("momentum") if "momentum" in legs else None
    legs = {k: v for k, v in legs.items() if v is not None}
    d2 = d.copy()
    for k, v in legs.items():
        d2["_leg_" + k] = v
    print(f"{'c2 腿':<16}" + "".join(f"{LABEL[c]:>10}" for c in REAL_FACES) + f"{'c2':>10}")
    for k in legs:
        row = []
        for c in REAL_FACES + ["c2"]:
            r = d2.groupby("as_of")[["_leg_" + k, c]].apply(
                lambda gg: gg.iloc[:, 0].rank().corr(gg.iloc[:, 1].rank())).mean()
            row.append(r)
        print(f"{k:<16}" + "".join(f"{x:>10.3f}" for x in row))
    print("\n讀法:|ρ| 高 = 兩邊在用同一份資訊。特別看:")
    print("  · 100−momentum% vs 動能面 —— 一個是 20 日**短線反轉**,一個是 3~6 月**中期動能**;")
    print("    若 ρ 接近 0 或為負,代表兩者不是同一件事(不是重複計,而是方向相反)。")
    print("  · revenue_yoy% vs 動能面 —— f_mom 的 (B) 營收動能佔 30 分,這一段是**真的重疊**。")


def part6(d: pd.DataFrame):
    hr("§6 排序穩定度 —— 逐月 rank 自相關(換手率的上游)")
    print(f"{'面':<8}{'月間rank自相關':>16}{'Top20%留存率':>16}")
    for c in REAL_FACES + [REAL_COMP_COL, "c2"]:
        if c not in d.columns:
            continue
        months = sorted(d["as_of"].unique())
        ac, keep = [], []
        prev = None
        for m in months:
            g = d[d["as_of"] == m][["stock_id", c]].dropna()
            cur = g.set_index("stock_id")[c].rank(pct=True)
            if prev is not None:
                common = cur.index.intersection(prev.index)
                if len(common) > 30:
                    ac.append(cur[common].rank().corr(prev[common].rank()))
                    a = set(cur[cur >= 0.8].index); b = set(prev[prev >= 0.8].index)
                    if b:
                        keep.append(len(a & b) / len(b))
            prev = cur
        print(f"{LABEL.get(c, c):<8}{np.nanmean(ac):>16.3f}{np.nanmean(keep)*100:>15.1f}%")


def part7(d: pd.DataFrame):
    hr("§7 定義斷裂點 —— 同一個欄名,2019 前後不是同一個因子")
    print("三個開關的資料相依,全部在 2019 落地(靜態追溯 + 實測):")
    print("  · f_val   : core/industry_value.py 的 industry_value_ref.parquet 起 **2019-04-10**")
    print("              → 之前退回 PEG(0.85)+歷史位階(0.15);之後是『產業內估值位階』。兩個不同因子。")
    print("  · f_mom   : RS 疊加(±8)要 0050 快取,core.backtest._RS_BENCHMARK 讀 TaiwanStockPrice/0050,")
    print("              該快取只有 **2019-01-02 起** → 2019 年中之前 rs_6m=None,A2 那一段整段不計分。")
    print("  · composite: regime 乘數要 load_benchmark('0050'),同樣只有 2019 起 →")
    print("              2019 之前 classify_regime() 一律回 'neutral',**regime 層從未生效**。\n")
    d = d.copy()
    d["y"] = d["as_of"].str[:4]
    print(f"{'年':<6}" + "".join(f"{LABEL[c]+'中位':>12}{LABEL[c]+'std':>11}" for c in ["f_val", "f_mom"]))
    for y, g in d.groupby("y"):
        print(f"{y:<6}" + "".join(f"{g[c].median():>12.1f}{g.groupby('as_of')[c].std().mean():>11.2f}"
                                  for c in ["f_val", "f_mom"]))
    print("\n含意:H5『六時代穩健』的前三段(05-09/10-14/15-18)量到的分數,與後三段不是同一個定義。")
    print("      任何跨 2019 的全期 IC / 時代比較都混了兩個因子,必須在新預註冊裡明確處置。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adv", type=float, default=1e6)
    ap.add_argument("--part", type=int, default=None)
    args = ap.parse_args()

    d = load_real_panel(adv_floor=args.adv)
    d["as_of"] = d["as_of"].astype(str)
    print(f"面板:{d.attrs.get('realbody_path')}  ADV≥{args.adv:,.0f}  {len(d):,} 列")
    parts = {1: part1, 2: part2, 3: part3, 4: part4, 5: part5, 6: part6, 7: part7}
    for k in sorted(parts):
        if args.part in (None, k):
            parts[k](d)


if __name__ == "__main__":
    main()
