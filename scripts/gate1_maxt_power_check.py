# -*- coding: utf-8 -*-
"""gate1_maxt_power_check.py — Codex 第七輪選 (c):**Gate 1 升為主判定**。
本檔在凍結前把三件事量清楚:

  1. **V0 自己的 rank IC 與 t** 在主時鐘(2019-08~2026-03,80 月)上是多少
     —— 若連 V0 都遠低於門檻,那 Gate 1 會重演上一輪 Gate 2 的問題;
  2. **單 arm 的置換虛無分布** —— 逐月打散 `fwd_x` 後 t 的分布,確認 t 的參考尺度;
  3. **12-arm max-t 校正的門檻**隨「arm 之間相關係數 ρ」如何變化
     —— 12 個 arm 都是 V0 的單點變體,ρ 會很高,max-t 的懲罰因此遠小於 Bonferroni。
     這一步用模擬(多變量常態的 max)算出門檻區間,**不需要 arm 存在**。

**這不是 candidate OOS**:量的是 V0 與純虛無分布,此刻不存在任何 candidate。

================================================================================
⚠ 2026-08-01 已降級 —— **第 3 節的等相關模擬不是 12-arm 驗證,不可引用為 `T*`**
================================================================================
Codex 第八輪 §4 判定:本檔「仍只是單 arm + 等相關模擬,不能算完成的 12-arm 驗證」。
而且第八輪 §1 已把 Gate 1 的主統計量從**絕對 IC** 改成**對 V0 的配對 ΔIC**,
所以本檔第 3 節印的 `ρ 0→1 對應 max-t 2.628→1.654` 只是**理論預測範圍**,
**不是** `T*` 的實測值,**不得**寫成已知事實。

**Gate 1 的凍結實作與 12-arm synthetic 驗證 → `scripts/gate1_delta_ic_maxt.py`。**

本檔仍然有用、也仍然是文件引用的來源,但**只限於一件事**:
量 **V0 自己的絕對 rank IC 水準**(主窗 t=0.88、產業內中性化 t=0.26,
即預註冊 §5-2b 那張表)。那個量測是把主統計量改成 ΔIC 的直接理由。
================================================================================

用法:python scripts/gate1_maxt_power_check.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_HERE, _ROOT):
    sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from lab_paths import load_real_panel, RET_COL, REAL_COMP_COL   # noqa: E402

# ---- 凍結參數(Gate 1 的 max-t 置換校正)----
N_PERM = 2000           # 置換次數
SEED = 20260731
ALPHA = 0.05            # 單尾;門檻 = 虛無 max-t 分布的 p95
N_ARMS = 12             # N_total(第一批 6 + 第二批 6)
MIN_N = 30              # 每月最少檔數(與 scripts/face_audit.ic_series 相同)

WINDOWS = [
    ("Train      2005-01~2014-12", "2005-01-01", "2014-12-31"),
    ("Validation 2015-01~2018-12", "2015-01-01", "2018-12-31"),
    ("**OOS(主)** 2019-08~2026-03", "2019-08-01", "2026-03-31"),
    ("OOS(robust) 2019-01~2026-03", "2019-01-01", "2026-03-31"),
    ("全期        2005-01~2026-03", "2005-01-01", "2026-03-31"),
]
OOS_ERAS = [
    ("19-21(截短)2019-08~2021-12", "2019-08-01", "2021-12-31"),
    ("2022       2022-01~2022-12", "2022-01-01", "2022-12-31"),
    ("23-26      2023-01~2026-03", "2023-01-01", "2026-03-31"),
]


def tstat(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def _demean_by(g: pd.DataFrame, col: str, by: str) -> pd.Series:
    """產業內中性化:同一 as_of 內,把**全體 rank** 減掉「該股所屬產業的全體 rank 平均」。
    → 剩下的是「在自己產業裡相對強弱」,產業層級的整體偏移被移除。"""
    r = g[col].rank()
    return r - r.groupby(g[by]).transform("mean")


def ic_series(d: pd.DataFrame, col: str, neutral_by: str | None = None) -> pd.Series:
    out = {}
    for a, g in d.groupby("as_of"):
        m = g[col].notna() & g[RET_COL].notna()
        if m.sum() < MIN_N:
            continue
        gg = g.loc[m]
        x = _demean_by(gg, col, neutral_by) if neutral_by else gg[col].rank()
        out[a] = x.corr(gg[RET_COL].rank())
    return pd.Series(out).dropna()


def perm_null_t(d: pd.DataFrame, col: str, n_perm: int, seed: int) -> np.ndarray:
    """單 arm 置換虛無:**逐月**打散 `fwd_x`(打斷分數↔報酬的連結,保留橫斷面分布
    與每月檔數),重算 IC 序列的 t。這是 max-t 校正的基礎單元。"""
    rng = np.random.default_rng(seed)
    months, xs, ys = [], [], []
    for a, g in d.groupby("as_of"):
        m = g[col].notna() & g[RET_COL].notna()
        if m.sum() < MIN_N:
            continue
        gg = g.loc[m]
        months.append(a)
        xs.append(gg[col].rank().to_numpy())
        ys.append(gg[RET_COL].rank().to_numpy())
    out = np.empty(n_perm)
    for i in range(n_perm):
        ics = []
        for x, y in zip(xs, ys):
            yp = rng.permutation(y)
            ics.append(np.corrcoef(x, yp)[0, 1])
        out[i] = tstat(ics)
    return out


def maxt_threshold(rho: float, n_arms: int, n_sim: int, seed: int) -> float:
    """12 個相關係數為 ρ 的 arm,其 max-t 虛無分布的 p95。
    模型:t_j = sqrt(ρ)·Z0 + sqrt(1−ρ)·Z_j(等相關的多變量常態)。
    ρ→1 → 門檻 = 單 arm 的 1.645;ρ→0 → 接近 12 個獨立檢定的 Bonferroni 尺度。"""
    rng = np.random.default_rng(seed)
    z0 = rng.standard_normal((n_sim, 1))
    zj = rng.standard_normal((n_sim, n_arms))
    t = np.sqrt(rho) * z0 + np.sqrt(1.0 - rho) * zj
    return float(np.percentile(t.max(axis=1), 100 * (1 - ALPHA)))


def main():
    d = load_real_panel(adv_floor=1e6)
    d["as_of"] = d["as_of"].astype(str)
    d["_ind"] = d["tej_ind_name"].fillna("未分類")
    print("=" * 96)
    print("Gate 1 升為主判定(Codex 第七輪 §1)—— 凍結前的檢定力與 max-t 門檻量測")
    print("=" * 96)
    print(f"面板:ADV≥100萬,{len(d):,} 列;報酬線 {RET_COL};綜合分 {REAL_COMP_COL}")
    print("\n⚠ 這**不是 candidate OOS** —— 量的是 V0 與純虛無分布,此刻不存在任何 candidate。\n")

    # ---- 1. V0 的 rank IC / t ----
    print(f"{'區間':<30}{'月數':>6}{'rank IC':>10}{'t':>8}{'產業內 IC':>11}{'t':>8}{'月勝率%':>9}")
    res = {}
    for label, lo, hi in WINDOWS + OOS_ERAS:
        if label == OOS_ERAS[0][0]:
            print("-" * 82 + "  ← Gate 3 的三段")
        sub = d[(d["as_of"] >= lo) & (d["as_of"] <= hi)]
        s = ic_series(sub, REAL_COMP_COL)
        sn = ic_series(sub, REAL_COMP_COL, neutral_by="_ind")
        res[label] = (s, sn)
        print(f"{label:<30}{len(s):>6}{s.mean():>10.4f}{tstat(s):>8.2f}"
              f"{sn.mean():>11.4f}{tstat(sn):>8.2f}{(s > 0).mean()*100:>9.1f}")

    s_oos, sn_oos = res["**OOS(主)** 2019-08~2026-03"]

    # ---- 2. 單 arm 置換虛無 ----
    sub = d[(d["as_of"] >= "2019-08-01") & (d["as_of"] <= "2026-03-31")]
    print(f"\n單 arm 置換虛無(逐月打散 {RET_COL},{N_PERM} 次,seed={SEED})…")
    null_t = perm_null_t(sub, REAL_COMP_COL, N_PERM, SEED)
    print(f"  虛無 t:mean {null_t.mean():+.3f}  sd {null_t.std(ddof=1):.3f}  "
          f"p95 **{np.percentile(null_t, 95):.3f}**  p99 {np.percentile(null_t, 99):.3f}")
    print(f"  → V0 觀測 t = **{tstat(s_oos):.2f}**;"
          f"置換 p 值 = {(null_t >= tstat(s_oos)).mean():.4f}")

    # ---- 3. 12-arm max-t 門檻隨 ρ 變化 ----
    print(f"\n12-arm max-t 校正門檻(單尾 α={ALPHA},{200_000} 次模擬):")
    print(f"  {'ρ':>6}{'max-t p95':>12}   判讀")
    for rho in (0.0, 0.5, 0.8, 0.9, 0.95, 0.99, 1.0):
        thr = maxt_threshold(rho, N_ARMS, 200_000, SEED + int(rho * 100))
        note = ""
        if rho == 0.0:
            note = "12 個獨立檢定(≈Bonferroni 尺度)"
        elif rho == 1.0:
            note = "12 個完全相同的 arm = 單一檢定"
        print(f"  {rho:>6.2f}{thr:>12.3f}   {note}")
    print("  對照:單 arm 單尾 95% = 1.645;Bonferroni(0.05/12)單尾 = 2.638")

    print("\n" + "=" * 96)
    print("判讀(寫進預註冊 §5 Gate 1):")
    print(f"  · V0 在主時鐘的 rank IC t = {tstat(s_oos):.2f}、產業內中性化後 t = {tstat(sn_oos):.2f}。")
    print("  · 12 個 arm 都是 V0 的**單點變體**,彼此相關係數會很高(ρ≳0.9)")
    print("    → max-t 門檻約 1.7–1.9,**遠低於** Bonferroni 的 2.64。")
    print("    所以『用 max-t 而不是 Bonferroni』不是為了放寬,而是因為 Bonferroni 對")
    print("    高度相關的族系是錯的校正(過度保守)。實際 ρ 必須在跑完 12 個 arm 後**實測**,")
    print("    不得事前假設。")
    print("=" * 96)


if __name__ == "__main__":
    main()
