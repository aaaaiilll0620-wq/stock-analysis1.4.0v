# -*- coding: utf-8 -*-
"""phase2_diag_analysis.py — Phase 2 診斷分析(**只讀診斷面板,不改任何策略**)

回應 Codex 第三輪授權的 Phase 2 前五項:

  §1 regime / dynamic weight 的**實際有效權重**分布
  §2 缺值與 data_gaps 對五面分數的影響(基本面通過率見 phase2_is_passed_sample.py)
  §3 washout 在 live 與研究路徑的差異(含影響上界)
  §4 原始五面分數 vs 實際合成 bucket 的差異
  §5 2019 前後與 H5 六時代的**有效評分定義**

**本階段禁止且未做**:改五維公式 / 改權重 / 改 c2 / 改缺值填法 / 補 0050 重建 V0 /
跑 OOS 或 H1–H5 / 把診斷數字當策略結論。

**本檔完全不碰報酬線** —— 沒有 join `exec_ret`,沒有任何 IC / 績效計算。
所有輸出都是「分數與狀態的分布」,不是「這樣做會賺多少」。

用法:python scripts/phase2_diag_analysis.py [--part N]
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIAG = os.path.join(_ROOT, "data", "research_base", "diag", "diag_scores_adv100w_diag.parquet")

FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
BUCKETS = ["b_fund", "b_val", "b_tech", "b_mom", "b_whale"]
KEY = {"f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
       "f_mom": "momentum", "f_whale": "whale"}
LAB = {"f_fund": "基本面", "f_val": "估值", "f_tech": "技術", "f_mom": "動能", "f_whale": "籌碼"}
ERAS = [("05-09", "2005", "2009"), ("10-14", "2010", "2014"), ("15-18", "2015", "2018"),
        ("19-21", "2019", "2021"), ("2022", "2022", "2022"), ("23-26", "2023", "2026")]


def hr(t):
    print("\n" + "=" * 96 + f"\n{t}\n" + "=" * 96)


def load():
    d = pd.read_parquet(DIAG)
    d["as_of"] = d["as_of"].astype(str)
    d["y"] = d["as_of"].str[:4]
    d["era"] = "?"
    for name, y0, y1 in ERAS:
        d.loc[(d["y"] >= y0) & (d["y"] <= y1), "era"] = name
    d["all3_missing"] = d["income_missing"] & d["balance_missing"] & d["cashflow_missing"]
    d["has_gaps"] = d["data_gaps"] != ""
    return d


def eff_weights(d: pd.DataFrame) -> pd.DataFrame:
    """逐列算出**正規化後的實際有效權重**(名目 × regime 乘數 → dynamic weights → 除以總和)。

    這是 `advisor.advise()` 第 106–119 行的算術;`composite_reconcile` 與 `build_diag_panel`
    已各自逐列驗過它能完全重現 `real_composite`,所以這裡的權重就是**當時真的用的那一組**。
    """
    from core.regime import REGIME_MULTIPLIERS
    from core.scoring_manager import ScoringManager
    W = ScoringManager.MODES["balanced"]["composite_weights"]
    out = np.zeros((len(d), 5))
    regs = d["regime"].to_numpy()
    dyns = d["dyn_weight"].to_numpy()
    cache = {}
    for i, (r, dy) in enumerate(zip(regs, dyns)):
        k = (r, bool(dy))
        if k not in cache:
            mult = REGIME_MULTIPLIERS.get(r or "neutral", REGIME_MULTIPLIERS["neutral"])
            w = {kk: W[kk] * mult[kk] for kk in W}
            if dy:
                cut = w["valuation"] * 0.6
                w["valuation"] -= cut
                w["momentum"] += cut * 0.6
                w["whale"] += cut * 0.4
            s = sum(w.values())
            cache[k] = np.array([w[KEY[c]] / s for c in FACES])
        out[i] = cache[k]
    return pd.DataFrame(out, columns=["w_" + c[2:] for c in FACES], index=d.index)


def part1(d, W):
    hr("§1 regime / dynamic weight 的**實際有效權重**分布(名目權重從來不是實際權重)")
    from core.scoring_manager import ScoringManager
    nom = ScoringManager.MODES["balanced"]["composite_weights"]
    print("名目(MODES['balanced']['composite_weights']):"
          + "  ".join(f"{LAB[c]} {nom[KEY[c]]:.2f}" for c in FACES))

    print("\n六種 (regime × dyn) 組合的實際有效權重,以及各佔多少列:")
    g = d.assign(**W).groupby(["regime", "dyn_weight"])
    print(f"{'regime':<9}{'dyn':<6}{'列數':>10}{'佔比':>8}"
          + "".join(f"{LAB[c]:>9}" for c in FACES))
    rows = []
    for (r, dy), gg in g:
        w = [gg["w_" + c[2:]].iloc[0] for c in FACES]
        rows.append((r, dy, len(gg), len(gg) / len(d), w))
    for r, dy, n, p, w in sorted(rows, key=lambda x: -x[2]):
        print(f"{r:<9}{str(dy):<6}{n:>10,}{p*100:>7.2f}%" + "".join(f"{x:>9.3f}" for x in w))

    print("\n全 panel 的有效權重分布(逐列):")
    print(f"{'面':<8}{'名目':>8}{'平均':>9}{'p5':>9}{'p50':>9}{'p95':>9}{'≠名目的列%':>12}")
    for c in FACES:
        s = W["w_" + c[2:]]
        print(f"{LAB[c]:<8}{nom[KEY[c]]:>8.2f}{s.mean():>9.3f}{s.quantile(.05):>9.3f}"
              f"{s.quantile(.50):>9.3f}{s.quantile(.95):>9.3f}"
              f"{(np.abs(s - nom[KEY[c]]) > 1e-9).mean()*100:>11.2f}%")
    same = np.ones(len(d), bool)
    for c in FACES:
        same &= np.abs(W["w_" + c[2:]] - nom[KEY[c]]) < 1e-9
    print(f"\n**五面全部等於名目權重的列:{same.mean()*100:.2f}%** "
          f"→ 其餘 {100-same.mean()*100:.2f}% 的列用的是別組權重。")


def part2(d):
    hr("§2 缺值與 data_gaps 對五面分數的影響(全 panel;通過率見 phase2_is_passed_sample.py)")
    print(f"{'分組':<26}{'列數':>10}{'佔比':>8}"
          + "".join(f"{LAB[c]+'中位':>11}" for c in FACES))
    groups = [("全體", pd.Series(True, index=d.index)),
              ("無任何缺口", ~d["has_gaps"] & ~d["pe_missing"] & ~d["all3_missing"]),
              ("有 data_gaps", d["has_gaps"]),
              ("PE 缺失", d["pe_missing"]),
              ("三大財報全缺", d["all3_missing"]),
              ("僅損益表缺", d["income_missing"] & ~d["all3_missing"]),
              ("val_override(估值資料不足)", d["val_override"])]
    for name, m in groups:
        if m.sum() == 0:
            continue
        g = d[m]
        print(f"{name:<26}{len(g):>10,}{m.mean()*100:>7.2f}%"
              + "".join(f"{g[c].median():>11.1f}" for c in FACES))

    print("\nPE 缺失對基本面的位移(pe_vs_industry 缺 → 填 10.0 → 估值腿拿 100 分,佔 f_fund 的 0.20):")
    a, b = d[d["pe_missing"]]["f_fund"], d[~d["pe_missing"]]["f_fund"]
    print(f"  PE 缺失   n={len(a):,}  f_fund 中位 {a.median():.1f}  p25 {a.quantile(.25):.1f}  p75 {a.quantile(.75):.1f}")
    print(f"  PE 有值   n={len(b):,}  f_fund 中位 {b.median():.1f}  p25 {b.quantile(.25):.1f}  p75 {b.quantile(.75):.1f}")
    print(f"  中位差 {a.median()-b.median():+.1f} 分")

    print("\ndata_gaps 的實際成分(前 12 種):")
    vc = d[d["has_gaps"]]["data_gaps"].value_counts().head(12)
    for k, v in vc.items():
        print(f"  {v:>9,}  ({v/len(d)*100:5.2f}%)  {k}")

    print("\n逐年:PE 缺失% / 三大財報全缺% / 有 data_gaps%")
    t = d.groupby("y")[["pe_missing", "all3_missing", "has_gaps"]].mean() * 100
    t["n"] = d.groupby("y").size()
    print(t.round(2).to_string())


def part3(d):
    hr("§3 washout:live 與研究路徑的差異")
    print("機制(core/advisor.py:84-91):washout 命中 → chip_bucket = min(100, max(whale,60)+5)")
    print("觸發條件之一(:361):`stock.margin_change_pct <= -8.0`\n")
    print("  live      :`data_provider._fetch_full_stock_data():1827` 會填 margin_change_pct")
    print("  研究/PIT  :`core/backtest.build_pit_stockdata()` **從未設定該欄** → 恆為 dataclass 預設 0.0")
    print(f"             → `retail_exit = (0.0 <= -8.0)` 恆為 False\n")
    print(f"全 panel washout_override 觸發:**{int(d['washout_override'].sum())} / {len(d):,} 列**"
          f"({d['washout_override'].mean()*100:.4f}%)")

    # 影響上界:若 washout 曾觸發,能被墊高的是 f_whale < 65 的列
    elig = d["f_whale"] < 65.0
    lift = np.where(elig, np.minimum(100.0, np.maximum(d["f_whale"], 60.0) + 5.0) - d["f_whale"], 0.0)
    print(f"\n**影響上界估計**(不是策略結論,只是量這個落差有多大):")
    print(f"  f_whale < 65 的列(墊高會真的動到分數):{elig.mean()*100:.2f}%")
    print(f"  若對這些列全部套用 washout,籌碼分平均墊高 {lift[elig].mean():.1f} 分"
          f"(中位 {np.median(lift[elig]):.1f},最大 {lift.max():.1f})")
    print(f"  換算到 composite(籌碼名目權重 0.15):平均 {lift[elig].mean()*0.15:.2f} 分")
    print("  ⚠ 這是**上界**:live 實際觸發率遠低於 100%(需要融資10日大減 + 法人賣超 + 股價回檔同時成立),")
    print("     但研究端的觸發率是**確定的 0%**。真實落差落在 0 與上界之間,**無法從研究面板回推**。")


def part4(d):
    hr("§4 原始五面分數 vs 實際合成 bucket")
    print("設計上只有兩個面可能不同(advise:84-95):估值(資料不足→50)、籌碼(washout→墊高)。")
    print("其餘三面應**逐列相同**。實測:\n")
    print(f"{'面':<8}{'b≠f 的列':>12}{'佔比':>9}{'平均 b−f':>11}{'max|b−f|':>11}")
    for f, b in zip(FACES, BUCKETS):
        diff = d[b] - d[f]
        ne = np.abs(diff) > 1e-9
        print(f"{LAB[f]:<8}{int(ne.sum()):>12,}{ne.mean()*100:>8.2f}%"
              f"{diff.mean():>11.4f}{np.abs(diff).max():>11.2f}")

    m = d["val_override"]
    print(f"\n估值覆寫的細節({int(m.sum()):,} 列):")
    print(f"  這些列的 f_val(面板存的原始分):中位 {d[m]['f_val'].median():.1f}  "
          f"max {d[m]['f_val'].max():.1f}  (=0 的比例 {(d[m]['f_val']==0).mean()*100:.1f}%)")
    print(f"  合成時實際用的 b_val:一律 {d[m]['b_val'].unique()}")
    print(f"  → 面板值與合成用值的差:平均 {(d[m]['b_val']-d[m]['f_val']).mean():+.1f} 分")
    print(f"  換算到 composite(估值名目權重 0.08):平均 {(d[m]['b_val']-d[m]['f_val']).mean()*0.08:+.2f} 分")
    print("\n**含意**:任何直接拿面板 f_* 重建 composite 的分析,在這些列上會系統性偏低;")
    print("  這正是先前『殘差 40% 對不上』的一部分。診斷面板現在把 b_* 存下來了,不必再反推。")

    print(f"\nvaluation_basis(估值走哪一條路徑)全 panel 分布:")
    for k, v in d["valuation_basis"].value_counts().items():
        print(f"  {v:>9,}  ({v/len(d)*100:5.2f}%)  {k or '(空)'}")


def part5(d, W):
    hr("§5 2019 前後與 H5 六時代的**有效評分定義**")
    dd = d.assign(**W)
    print(f"{'時代':<7}{'月':>4}{'列數':>9}"
          f"{'bear%':>7}{'bull%':>7}{'dyn%':>7}{'valOv%':>8}{'產業位階%':>10}"
          f"{'PE缺%':>7}{'三表缺%':>8}" + "".join(f"{'w_'+c[2:]:>8}" for c in FACES))
    for name, y0, y1 in ERAS:
        g = dd[dd["era"] == name]
        if g.empty:
            continue
        ind = (g["valuation_basis"] == "產業內位階").mean() * 100
        print(f"{name:<7}{g['as_of'].nunique():>4}{len(g):>9,}"
              f"{(g['regime']=='bear').mean()*100:>7.2f}{(g['regime']=='bull').mean()*100:>7.2f}"
              f"{g['dyn_weight'].mean()*100:>7.2f}{g['val_override'].mean()*100:>8.2f}{ind:>10.2f}"
              f"{g['pe_missing'].mean()*100:>7.2f}{g['all3_missing'].mean()*100:>8.2f}"
              + "".join(f"{g['w_'+c[2:]].mean():>8.3f}" for c in FACES))

    print("\n2019 分界(以 2019-01 為切點):")
    for lab, m in [("2019 前", dd["as_of"] < "2019"), ("2019 起", dd["as_of"] >= "2019")]:
        g = dd[m]
        ind = (g["valuation_basis"] == "產業內位階").mean() * 100
        print(f"  {lab}:{len(g):>7,} 列  bear {(g['regime']=='bear').mean()*100:5.2f}%  "
              f"bull {(g['regime']=='bull').mean()*100:5.2f}%  產業位階 {ind:5.2f}%  "
              f"有效 w_mom 平均 {g['w_mom'].mean():.3f}  w_tech 平均 {g['w_tech'].mean():.3f}")

    print("\n**RS(f_mom 的 A2 ±8)不在面板欄位裡**,由 breakpoint_2019_audit.py 量到的閘值是:")
    print("  rs_3m 首見 2019-04-30、rs_6m 首見 2019-07-31 → 05-09 / 10-14 / 15-18 三段整段不計分。")
    print("\n結論(語意,不是策略判定):六個時代**不是同一套評分定義**在跑。")
    print("  前三段:regime 恆 neutral(有效權重 = 名目)、RS 不計分、估值走 PEG 路徑。")
    print("  後三段:regime 逐月切換、RS 生效、估值走產業內位階。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, default=None)
    args = ap.parse_args()
    d = load()
    print(f"診斷面板:{DIAG}")
    print(f"{len(d):,} 列 × {len(d.columns)} 欄 / {d['as_of'].nunique()} 月 / {d['stock_id'].nunique()} 檔")
    print(f"builder={d['builder_version'].iloc[0]}  commit={d['code_commit'].iloc[0]}  "
          f"weights_version={d['weights_version'].iloc[0]}  source={d['panel_source'].iloc[0]}")
    W = eff_weights(d)
    parts = {1: lambda: part1(d, W), 2: lambda: part2(d), 3: lambda: part3(d),
             4: lambda: part4(d), 5: lambda: part5(d, W)}
    for k in sorted(parts):
        if args.part in (None, k):
            parts[k]()


if __name__ == "__main__":
    main()
