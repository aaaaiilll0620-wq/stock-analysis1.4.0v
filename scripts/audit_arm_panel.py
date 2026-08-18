# -*- coding: utf-8 -*-
"""audit_arm_panel.py — **arm 面板完整性稽核**(第二批 B4 / B5 / C2)
================================================================================
`build_arm_panel.py` 自己的驗收閘門只看「覆蓋率 + real_composite vs V0」。
本檔是**建置之後的獨立複核**,問的是不同的問題:

  1. 鍵集合是否與 V0 **完全相同**(duplicate / missing / extra 三者都要 0);
  2. 有沒有靜默的缺值(`score_error` 非空、`real_composite` / `composite_indep` NaN);
  3. 面板內存的 `composite_indep` 與 `real_composite` 是否逐列一致;
  4. **再做一次獨立的算術重算** —— 本檔的實作是**向量化 numpy**,
     從 `core/advisor.py:advise()` 的規格重寫,與 `build_arm_panel._indep_composite`
     的「逐列 python dict」路徑無共用程式碼。兩條路徑對得起來才算數。
  5. **arm-specific 足跡**:預註冊說這個 arm 只改一個面,就必須**只有那一個面**變動。
     其餘四面必須與 V0 **逐列 bit-identical**(容差 0,不是 0.01)。

⚠ 本檔**不 join 報酬線、不算 IC / CAGR / Sharpe / MDD / 任何績效**。
   它只讀分數面板與 V0 面板,做算術與集合比對。

用法:
    python -m scripts.audit_arm_panel --arm B4
    python -m scripts.audit_arm_panel --arm C2 --ref-arm B3
================================================================================
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[1]
ARM_DIR = PROJ / "data" / "research_base" / "arms"
KEY = ["as_of", "stock_id"]
FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
FACE2KEY = {"f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
            "f_mom": "momentum", "f_whale": "whale"}
TOL = 0.01

# 預註冊寫死:每個 arm **唯一**允許變動的面(其餘四面必須與 V0 逐列相同)
#
# 第一批(`docs/預註冊_FaceRedesignV2_草案.md`)的宣告來源逐條註明。
# 這些值只能抄自預註冊,**不得**從面板實際變了哪一面回推 —— 那是結果相依。
ARM_MUTABLE_FACE = {
    "A1": "f_mom",      # 第一批 §4 表:只補 2005-2018 的 RS(f_mom 的 A2 ±8),regime 維持 V0
    "A2": None,         # 第一批 §4 表:只補 2005-2018 的 regime;RS 值逐月同 V0 → regime 只動權重
    "A3": "f_fund",     # 第一批 §4-1:缺財報列的 f_fund 由人造 32.5 → 中性 50.0
    "A4": "f_val",      # 第一批 §4-2:f_val 配方統一,不做權重重分配
    "B1": "f_tech",     # §1  分桶 → 連續
    "B2": "f_whale",    # §2  解除飽和
    "B3": "f_mom",      # §3  移除營收腿
    "B4": "f_fund",     # §4  移除估值組
    "B5": "f_mom",      # §4-B5 分桶 → 連續
    "C1": None,         # 第一批 §4 表:拿掉 regime_multipliers,只動權重
    "C2": None,         # §5  只動合成,五個面都不准變
    "C3": None,         # 第一批 §4-2b:百分位化的對象是 b_* buckets,f_* 原封不動
}

# 後處理 arm(由 `scripts/build_face_postprocess_arms.py` 從診斷面板產生)。
# 這兩個 arm 的 `composite_indep` 是**從診斷面板繼承的 V0 欄位**,不是該 arm 自己的
# 第二路徑重算值 —— 拿它對 arm 的 `real_composite` 會產生整表假失敗(實測 C1 89,619 列 /
# C3 263,727 列)。改驗它必須逐列等於面板自帶的 `v0_real_composite`,
# 那才是這個欄位真正的不變量(= 來源面板沒被動過)。
POSTPROCESS_ARMS = {"C1", "C3"}

# 預註冊第一批 §4 表 :298-300 寫死:A1/A2 的補值只在 2005-2018 生效,
# **2019-08-31 起與 V0 逐月完全相同**(2019-01~07 是刻意排除的邊界污染窗,不進任何判定)。
# 這是 A1/A2 專屬的硬條件,A3/A4 是全期定義修正,不適用。
OOS_ZERO_ARMS = {"A1", "A2"}
OOS_START = "2019-08-31"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ==============================================================================
# 第二條獨立實作:向量化的合成算術
#   規格來源 = core/advisor.py:advise() 第 89-122 行 + _dynamic_weights() 第 490-509 行。
#   刻意**不** import build_arm_panel._indep_composite —— 兩條路徑要各自寫一次才有對帳意義。
# ==============================================================================
def recompute_composite_vectorized(df: pd.DataFrame, base_w: dict, *,
                                   use_regime: bool = True,
                                   bucket_values: dict | None = None) -> pd.DataFrame:
    """從 `f_*` + regime + override 旗標,向量化重算 b_* 與 composite。

    回傳與 `df` 同 index 的 DataFrame,欄位 `rc_b_*` / `rc_composite`。

    `use_regime=False`  → 不套 regime 乘數(**C1** 的定義,第一批 §4 表)。
    `bucket_values`     → 加權時改用這組值取代 b_*(**C3** 的定義,第一批 §4-2b:
                          百分位化的是 advisor 實際加權的 buckets)。
                          `rc_b_*` 仍回傳原始 bucket 語意,供 b_* 複核使用。
    """
    from core.regime import REGIME_MULTIPLIERS

    n = len(df)
    # --- 第一段:f_* → b_*(advise() 第 91-104 行的兩個 override)---
    val_override = df["val_override"].to_numpy(dtype=bool)
    washout = df["washout_override"].to_numpy(dtype=bool)
    f = {c: df[c].to_numpy(dtype=float) for c in FACES}
    b = {
        "fundamental": f["f_fund"],
        "valuation": np.where(val_override, 50.0, f["f_val"]),
        "technical": f["f_tech"],
        "momentum": f["f_mom"],
        # washout:min(100, max(chip, 60) + 5)
        "whale": np.where(washout, np.minimum(100.0, np.maximum(f["f_whale"], 60.0) + 5.0),
                          f["f_whale"]),
    }

    # --- 第二段:regime 乘數(advise() 第 108-111 行)---
    regime = df["regime"].fillna("neutral").to_numpy()
    mw = {k: np.full(n, float(base_w[k])) for k in base_w}
    if use_regime:
        for reg, mult in REGIME_MULTIPLIERS.items():
            sel = (regime == reg)
            if not sel.any():
                continue
            for k in mw:
                mw[k][sel] = float(base_w[k]) * float(mult.get(k, 1.0))
        # 面板裡若出現 REGIME_MULTIPLIERS 沒有的標籤 → 生產碼會落到 neutral(全 1.0)
        unknown = ~np.isin(regime, list(REGIME_MULTIPLIERS.keys()))
        if unknown.any():
            for k in mw:
                mw[k][unknown] = float(base_w[k])

    # --- 第三段:個股動態權重(_dynamic_weights 第 504-508 行)---
    dyn = df["dyn_weight"].to_numpy(dtype=bool)
    cut = mw["valuation"] * 0.6
    mw["valuation"] = np.where(dyn, mw["valuation"] - cut, mw["valuation"])
    mw["momentum"] = np.where(dyn, mw["momentum"] + cut * 0.6, mw["momentum"])
    mw["whale"] = np.where(dyn, mw["whale"] + cut * 0.4, mw["whale"])

    # --- 第四段:加權平均 + round(2)(advise() 第 117-122 行)---
    wsum = np.zeros(n)
    for k in b:
        wsum = wsum + np.maximum(0.0, mw[k])
    if float(np.nanmin(wsum)) <= 0:
        raise SystemExit("❌ 有列的權重和 <= 0 —— 生產碼會走 DEFAULT_MODE_WEIGHTS 回退,"
                         "本重算未涵蓋該分支,不得以 0 差異蒙混過去。")
    # C3:加權的對象換成百分位化的 buckets;權重、override、regime、dyn 全部照舊
    bw = bucket_values if bucket_values is not None else b
    num = np.zeros(n)
    for k in b:
        num = num + bw[k] * mw[k]
    comp = np.round(num / wsum, 2)

    out = pd.DataFrame({f"rc_b_{k}": v for k, v in b.items()}, index=df.index)
    out["rc_composite_raw"] = num / wsum      # 未四捨五入 —— 主比對用這個(見下方說明)
    out["rc_composite"] = comp
    return out


def percentile_desc_by_asof(df: pd.DataFrame, col: str) -> pd.Series:
    """第二條獨立實作:逐 `as_of` 母體內的降冪百分位。

    規格來源 = 第一批預註冊 §4-2b 第 2 點:每個 `as_of` 在該 as_of 的母體
    (`listed_ok & adv20≥1e6`,即本面板的全部列)內轉成 0-100,映射公式與
    `high52_lab.dual_confirm_mask` 的 `pct()` 完全相同 ——
    stable 降冪 rank、`100·(1 − (rank−1)/n_valid)`、NaN 不參與也不補中性值。

    刻意**不** import `build_face_postprocess_arms._percentile_desc`:
    生產路徑用 `np.argsort(-x, kind="stable")`,本檔用 pandas
    `rank(method="first", ascending=False)`(並列依原始順序決勝,與 stable argsort 等價)。
    兩條路徑各自寫一次,對帳才有意義。
    """
    x = pd.to_numeric(df[col], errors="coerce")
    g = x.groupby(df["as_of"], sort=False)
    rk = g.rank(method="first", ascending=False)
    nv = g.transform("count").astype(float)
    return 100.0 * (1.0 - (rk - 1.0) / nv.where(nv > 0, 1.0))


# ==============================================================================
def audit(arm: str, ref_arm: str | None) -> dict:
    from scripts.lab_paths import resolve_realbody
    from core.scoring_manager import ScoringManager

    rep: dict = {"arm": arm, "failures": [], "warnings": []}

    v0_path = resolve_realbody(1e6)
    arm_path = ARM_DIR / f"arm_{arm}_scores_adv100w_arm.parquet"
    if not arm_path.exists():
        raise SystemExit(f"❌ arm 面板不存在:{arm_path}")

    v0 = pd.read_parquet(v0_path)
    got = pd.read_parquet(arm_path)
    for d in (v0, got):
        d["as_of"] = d["as_of"].astype(str)
        d["stock_id"] = d["stock_id"].astype(str)

    rep["v0_panel"] = v0_path.name
    rep["v0_sha256"] = sha256(v0_path)          # V0 不得被動過 —— 三次稽核應印出同一個值
    rep["arm_panel"] = str(arm_path)
    rep["arm_report"] = str(arm_path.with_name(arm_path.stem + "_report.json"))
    rep["v0_rows"] = int(len(v0))
    rep["rows"] = int(len(got))

    # ---------- 1. 鍵完整性 ----------
    rep["duplicate_keys"] = int(got.duplicated(subset=KEY).sum())
    v0_keys = set(map(tuple, v0[KEY].to_numpy()))
    got_keys = set(map(tuple, got[KEY].to_numpy()))
    rep["missing_keys"] = len(v0_keys - got_keys)     # V0 有、arm 沒有
    rep["extra_keys"] = len(got_keys - v0_keys)       # arm 有、V0 沒有
    rep["coverage"] = float(len(got) / len(v0)) if len(v0) else 0.0
    if rep["duplicate_keys"]:
        rep["failures"].append(f"duplicate keys = {rep['duplicate_keys']}(不得去重掩蓋)")
    if rep["missing_keys"]:
        rep["failures"].append(f"missing keys = {rep['missing_keys']}")
    if rep["extra_keys"]:
        rep["failures"].append(f"extra keys = {rep['extra_keys']}")
    if abs(rep["coverage"] - 1.0) > 1e-12:
        rep["failures"].append(f"coverage = {rep['coverage']:.6f} != 1.0")

    # 以下所有逐列比對都在「同一組鍵、同一個順序」上做
    m = got.merge(v0, on=KEY, how="inner", suffixes=("", "_v0"))
    rep["compared_rows"] = int(len(m))
    if len(m) != len(got):
        rep["failures"].append(f"merge 後只剩 {len(m)} / {len(got)} 列")

    # ---------- 2. 缺值 / 例外 ----------
    se = got["score_error"].fillna("").astype(str)
    rep["score_error_count"] = int((se.str.strip() != "").sum())
    if rep["score_error_count"]:
        rep["failures"].append(f"score_error 非空 = {rep['score_error_count']}")
        rep["score_error_sample"] = se[se.str.strip() != ""].head(5).tolist()

    nan_cols = {}
    for c in ["real_composite", "composite_indep"] + FACES + \
             ["b_fund", "b_val", "b_tech", "b_mom", "b_whale"]:
        if c in got.columns:
            k = int(got[c].isna().sum())
            if k:
                nan_cols[c] = k
    rep["nan_counts"] = nan_cols
    for c in ("real_composite", "composite_indep"):
        if nan_cols.get(c):
            rep["failures"].append(f"{c} 有 {nan_cols[c]} 個 NaN")
    if nan_cols:
        rep["warnings"].append(f"其他欄位有 NaN:{nan_cols}")

    # ---------- 3. 面板內存的 composite_indep ----------
    rep["postprocess_arm"] = arm in POSTPROCESS_ARMS
    if arm in POSTPROCESS_ARMS:
        # C1/C3 的 composite_indep 是從診斷面板繼承的 **V0** 欄位,不是該 arm 的重算值。
        # 正確的不變量是「它必須逐列等於面板自帶的 v0_real_composite」= 來源面板沒被動過。
        if "v0_real_composite" not in got.columns:
            rep["failures"].append(
                f"{arm} 是後處理 arm 卻沒有 v0_real_composite 欄 —— 無法驗證來源面板")
            rep["stored_indep_max_abs_diff"] = float("nan")
            rep["stored_indep_mismatch"] = -1
        else:
            d_stored = (got["composite_indep"] - got["v0_real_composite"]).abs()
            rep["stored_indep_max_abs_diff"] = float(d_stored.max())
            rep["stored_indep_mismatch"] = int((d_stored > TOL).sum())
            rep["stored_indep_checked_against"] = "v0_real_composite(繼承欄,非本 arm 重算)"
            if rep["stored_indep_mismatch"]:
                rep["failures"].append(
                    f"{arm} 的 composite_indep 與 v0_real_composite 有 "
                    f"{rep['stored_indep_mismatch']} 列 |Δ| > {TOL} —— 來源 V0 面板被動過")
            # 繼承欄同時必須等於現行 V0 面板的 real_composite
            d_src = (m["v0_real_composite"] - m["real_composite_v0"]).abs()
            rep["postprocess_source_vs_v0_mismatch"] = int((d_src > TOL).sum())
            if rep["postprocess_source_vs_v0_mismatch"]:
                rep["failures"].append(
                    f"{arm} 繼承的 v0_real_composite 與現行 V0 面板有 "
                    f"{rep['postprocess_source_vs_v0_mismatch']} 列不同")
    else:
        d_stored = (got["real_composite"] - got["composite_indep"]).abs()
        rep["stored_indep_max_abs_diff"] = float(d_stored.max())
        rep["stored_indep_mismatch"] = int((d_stored > TOL).sum())
        rep["stored_indep_checked_against"] = "real_composite"
        if rep["stored_indep_mismatch"]:
            rep["failures"].append(
                f"stored composite_indep 與 real_composite 有 {rep['stored_indep_mismatch']} 列 "
                f"|Δ| > {TOL}(max {rep['stored_indep_max_abs_diff']:.4f})")

    # ---------- 4. 獨立算術重算(本檔的向量化第二路徑)----------
    base_w = dict(ScoringManager.MODES["balanced"]["composite_weights"])
    rep["base_weights"] = base_w

    # C1 的定義就是不套 regime 乘數(第一批 §4 表);用通用路徑會整表假失敗。
    use_regime = arm != "C1"
    rep["recompute_use_regime"] = use_regime

    # C3:先獨立重算 b_*_pct,驗過之後才拿它去合成(第一批 §4-2b)
    bucket_values = None
    if arm == "C3":
        pct_bad, na_bad, bucket_values = {}, {}, {}
        for face, key in FACE2KEY.items():
            bcol = "b_" + face[2:]
            pcol = bcol + "_pct"
            mine = percentile_desc_by_asof(got, bcol)
            bucket_values[key] = mine.to_numpy(dtype=float)
            if pcol not in got.columns:
                rep["failures"].append(f"C3 缺 {pcol} 欄 —— 無法驗證百分位量尺")
                continue
            na_k = int((got[pcol].isna() != mine.isna()).sum())
            if na_k:
                na_bad[pcol] = na_k
            dd = (got[pcol] - mine).abs()
            k = int((dd > 1e-9).sum())
            if k:
                pct_bad[pcol] = {"mismatch": k, "max_abs_diff": float(dd.max())}
        rep["c3_pct_mismatch"] = pct_bad
        rep["c3_pct_nan_misalign"] = na_bad
        if pct_bad:
            rep["failures"].append(
                f"C3 的 b_*_pct 與獨立百分位重算不符:{pct_bad} —— "
                "量尺不是按凍結公式逐 as_of 算的")
        if na_bad:
            rep["failures"].append(
                f"C3 的 b_*_pct NaN 位置與獨立重算不一致:{na_bad}(NaN 必須維持 NaN、不補中性值)")

    rc = recompute_composite_vectorized(got, base_w, use_regime=use_regime,
                                        bucket_values=bucket_values)

    # 主比對用**未四捨五入**的重算值。理由(必須講清楚,不是放寬門檻):
    # 生產 advisor 與本檔的差別只在浮點加總順序,量級是 1 ULP(~4e-15 相對誤差);
    # 但 `round(x, 2)` 在 x 恰好落在 .xx5 的列上會把這 1 ULP 放大成整整 0.01。
    # 拿「未捨入值 vs 已捨入值」比、容差 0.01,才是在比**算術**;
    # 拿「捨入 vs 捨入」比則是在比**捨入方向**,那不是本稽核要驗的東西。
    # 為了不讓這條掩護真正的錯誤,下面對每一個捨入分歧列額外要求
    # |real − raw| <= 0.005 + eps —— 也就是它**必須**是真正的半值僵局,而不是別的差異。
    d_rc = (got["real_composite"] - rc["rc_composite_raw"]).abs()
    rep["recompute_vs_real_max_abs_diff"] = float(d_rc.max())
    rep["recompute_vs_real_mismatch"] = int((d_rc > TOL).sum())
    if rep["recompute_vs_real_mismatch"]:
        rep["failures"].append(
            f"獨立重算(未捨入)vs real_composite 有 {rep['recompute_vs_real_mismatch']} 列 "
            f"|Δ| > {TOL}(max {rep['recompute_vs_real_max_abs_diff']:.6f})")

    if arm in POSTPROCESS_ARMS:
        # composite_indep 在這兩個 arm 是 V0 的值,不是本 arm 的第二路徑重算值。
        # 它的正確性已由第 3 節(vs v0_real_composite / vs 現行 V0 面板)驗過。
        rep["recompute_vs_stored_indep_max_abs_diff"] = None
        rep["recompute_vs_stored_indep_mismatch"] = None
        rep["warnings"].append(
            f"{arm} 是後處理 arm:composite_indep 為繼承的 V0 欄,"
            "已改在第 3 節對 v0_real_composite 驗證,不與本 arm 的重算值比對")
    else:
        d_rc2 = (got["composite_indep"] - rc["rc_composite_raw"]).abs()
        rep["recompute_vs_stored_indep_max_abs_diff"] = float(d_rc2.max())
        rep["recompute_vs_stored_indep_mismatch"] = int((d_rc2 > TOL).sum())
        if rep["recompute_vs_stored_indep_mismatch"]:
            rep["failures"].append(
                f"獨立重算(未捨入)vs stored composite_indep 有 "
                f"{rep['recompute_vs_stored_indep_mismatch']} 列不合")

    # 捨入分歧的列:逐列證明它確實只是 .xx5 的半值僵局
    tie = (got["real_composite"] - rc["rc_composite"]).abs() > TOL
    rep["rounding_tie_rows"] = int(tie.sum())
    if tie.any():
        worst = float(d_rc[tie].max())
        rep["rounding_tie_max_unrounded_diff"] = worst
        if worst > 0.005 + 1e-9:
            rep["failures"].append(
                f"有捨入分歧列的未捨入差達 {worst:.6f} > 0.005 —— 那不是半值僵局,是真差異")
        else:
            rep["warnings"].append(
                f"{int(tie.sum())} 列的 round(x,2) 方向不同(未捨入最大差 {worst:.6f} "
                "≤ 0.005)—— 純浮點加總順序造成的半值僵局,非算術分歧")

    # b_* 也對一次(override 語意的獨立複核)
    b_bad = {}
    for face, key in FACE2KEY.items():
        col = "b_" + face[2:]
        if col in got.columns:
            dd = (got[col] - rc["rc_b_" + key]).abs()
            k = int((dd > 1e-9).sum())
            if k:
                b_bad[col] = {"mismatch": k, "max_abs_diff": float(dd.max())}
    rep["b_face_mismatch"] = b_bad
    if b_bad:
        rep["failures"].append(f"b_* 欄位與獨立重算不符:{b_bad}")

    # ---------- 5. arm-specific 足跡 ----------
    mutable = ARM_MUTABLE_FACE.get(arm, "__unknown__")
    if mutable == "__unknown__":
        rep["failures"].append(f"未知 arm {arm!r} —— 沒有預註冊的允許變動面")
    face_stats = {}
    for c in FACES:
        dd = (m[c] - m[c + "_v0"]).abs()
        face_stats[c] = {"changed_rows": int((dd > 0).sum()),
                         "max_abs_diff": float(dd.max())}
    rep["face_changes"] = face_stats
    rep["mutable_face"] = mutable
    for c in FACES:
        if c == mutable:
            continue
        st = face_stats[c]
        if st["changed_rows"] != 0:
            rep["failures"].append(
                f"{arm} 不該動 {c},卻有 {st['changed_rows']} 列不同"
                f"(max|Δ|={st['max_abs_diff']:.6f})—— 洩漏到別的面,是 bug 不是研究結果")
    if mutable is not None and face_stats[mutable]["changed_rows"] == 0:
        rep["failures"].append(f"{arm} 的 {mutable} 一列都沒改到 —— arm 旗標沒生效")
    rep["arm_specific_changed_rows"] = (face_stats[mutable]["changed_rows"]
                                        if mutable else 0)

    d_comp = (m["real_composite"] - m["real_composite_v0"]).abs()
    rep["composite_changed_rows"] = int((d_comp > TOL).sum())
    rep["composite_same_rate"] = float((d_comp <= TOL).mean())
    rep["composite_max_abs_diff"] = float(d_comp.max())

    # `mutable is None` 的 arm(A2 / C1 / C2 / C3)五個面都不准變 —— 那道檢查是**否定式**的,
    # 旗標完全沒生效也會過。補一道正向檢查:composite 必須真的動過。
    if mutable is None and rep["composite_changed_rows"] == 0:
        rep["failures"].append(
            f"{arm} 不動任何面,而 composite 也一列都沒變 —— arm 旗標沒生效")

    # ---------- 5-b. A1/A2 的 OOS 邊界(第一批預註冊 §4 表 :298-300)----------
    if arm in OOS_ZERO_ARMS:
        oos = m["as_of"] >= OOS_START
        d_oos = (m.loc[oos, "real_composite"] - m.loc[oos, "real_composite_v0"]).abs()
        rep["oos_start"] = OOS_START
        rep["oos_rows"] = int(oos.sum())
        rep["oos_changed_rows"] = int((d_oos > TOL).sum())
        rep["oos_max_abs_diff"] = float(d_oos.max()) if len(d_oos) else 0.0
        if rep["oos_changed_rows"]:
            rep["failures"].append(
                f"{arm} 在 {OOS_START} 起有 {rep['oos_changed_rows']} / {rep['oos_rows']} 列 "
                f"composite 與 V0 不同 —— 預註冊要求逐月完全相同,補值外溢到 OOS 了")
        pre = m["as_of"] < "2019-01-01"
        d_pre = (m.loc[pre, "real_composite"] - m.loc[pre, "real_composite_v0"]).abs()
        rep["pre2019_rows"] = int(pre.sum())
        rep["pre2019_changed_rows"] = int((d_pre > TOL).sum())
        if rep["pre2019_changed_rows"] == 0:
            rep["failures"].append(
                f"{arm} 在 2005-2018 一列都沒變 —— 補值根本沒生效")

    # ---------- 6. 值域 ----------
    rng = {}
    for c in FACES + ["real_composite", "composite_indep"]:
        rng[c] = {"min": float(got[c].min()), "max": float(got[c].max())}
    rep["ranges"] = rng
    if arm in ("B5", "B4", "C2"):     # 這三個 arm 都沒有解除 clip,五面必須留在 [0,100]
        for c in FACES + ["real_composite", "composite_indep"]:
            if rng[c]["min"] < -1e-9 or rng[c]["max"] > 100.0 + 1e-9:
                rep["failures"].append(
                    f"{c} 超出 [0,100]:[{rng[c]['min']:.4f}, {rng[c]['max']:.4f}]")

    # ---------- 7. C2 專屬:資料狀態不得無故改變 ----------
    if arm == "C2":
        rep["dyn_weight_true"] = int(got["dyn_weight"].sum())
        if rep["dyn_weight_true"] != 0:
            rep["failures"].append(
                f"C2 的 dyn_weight 有 {rep['dyn_weight_true']} 列為 True —— "
                "預註冊 §5 要求全 False")
        ref_path = ARM_DIR / f"arm_{ref_arm}_scores_adv100w_arm.parquet"
        if ref_arm and ref_path.exists():
            ref = pd.read_parquet(ref_path)
            ref["as_of"] = ref["as_of"].astype(str)
            ref["stock_id"] = ref["stock_id"].astype(str)
            cmp_cols = ["regime", "val_override", "washout_override", "valuation_basis"]
            mm = got.merge(ref[KEY + cmp_cols + ["dyn_weight"]], on=KEY, how="inner",
                           suffixes=("", "_ref"))
            rep["c2_ref_arm"] = ref_arm
            rep["c2_ref_compared_rows"] = int(len(mm))
            state_diff = {}
            for c in cmp_cols:
                k = int((mm[c].astype(str) != mm[c + "_ref"].astype(str)).sum())
                state_diff[c] = k
                if k:
                    rep["failures"].append(
                        f"C2 的 {c} 與 {ref_arm} 有 {k} 列不同 —— C2 只該動權重,"
                        "資料狀態不得改變")
            rep["c2_state_diff_vs_ref"] = state_diff
            # C2 的 composite 只應在「原本 dyn_weight=True」的列上改變
            ref_dyn = mm["dyn_weight_ref"].to_numpy(dtype=bool)
            mm2 = mm.merge(v0[KEY + ["real_composite"]], on=KEY, how="inner",
                           suffixes=("", "_v0base"))
            chg = (mm2["real_composite"] - mm2["real_composite_v0base"]).abs() > TOL
            rep["c2_ref_dyn_true_rows"] = int(ref_dyn.sum())
            leaked = int((chg.to_numpy() & ~ref_dyn).sum())
            rep["c2_changed_outside_dyn_rows"] = leaked
            if leaked:
                rep["failures"].append(
                    f"C2 有 {leaked} 列在 dyn_weight=False 的地方也變了 composite —— "
                    "不該發生")
        else:
            rep["warnings"].append(f"找不到參考 arm 面板 {ref_path.name},"
                                   "跳過 regime/override 狀態比對")

    rep["passed"] = not rep["failures"]
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--ref-arm", default="B3",
                    help="C2 的資料狀態比對基準(任一不動 regime/override 的 B arm)")
    a = ap.parse_args()

    rep = audit(a.arm, a.ref_arm)

    print("=" * 96)
    print(f"arm 面板完整性稽核 — **{a.arm}**")
    print("=" * 96)
    print(f"panel        : {rep['arm_panel']}")
    print(f"report       : {rep['arm_report']}")
    print(f"V0           : {rep['v0_panel']}  sha256={rep['v0_sha256'][:16]}…  "
          f"{rep['v0_rows']:,} 列")
    print(f"rows         : {rep['rows']:,}   coverage {rep['coverage']:.6f}")
    print(f"keys         : duplicate={rep['duplicate_keys']}  "
          f"missing={rep['missing_keys']}  extra={rep['extra_keys']}")
    print(f"score_error  : {rep['score_error_count']}")
    print(f"NaN          : {rep['nan_counts'] or '無'}")
    print(f"stored indep : mismatch={rep['stored_indep_mismatch']}  "
          f"max|Δ|={rep['stored_indep_max_abs_diff']:.6f}  "
          f"[比對對象 {rep.get('stored_indep_checked_against', 'real_composite')}]")
    vs_stored = rep["recompute_vs_stored_indep_mismatch"]
    print(f"獨立重算     : vs real mismatch={rep['recompute_vs_real_mismatch']} "
          f"(max|Δ|={rep['recompute_vs_real_max_abs_diff']:.6f}) / "
          f"vs stored mismatch={'不適用(後處理 arm)' if vs_stored is None else vs_stored}"
          f"   regime乘數={'套用' if rep.get('recompute_use_regime', True) else '不套用(C1 定義)'}")
    print(f"捨入僵局列   : {rep['rounding_tie_rows']}  "
          f"(未捨入最大差 {rep.get('rounding_tie_max_unrounded_diff', 0.0):.6f} ≤ 0.005)")
    print(f"b_* 複核     : {rep['b_face_mismatch'] or '全部相符'}")
    print(f"允許變動的面 : {rep['mutable_face']}")
    for c, st in rep["face_changes"].items():
        mark = "←允許" if c == rep["mutable_face"] else ("✅" if st["changed_rows"] == 0 else "❌")
        print(f"   {c:<9} changed={st['changed_rows']:>7,}  "
              f"max|Δ|={st['max_abs_diff']:.6f}  {mark}")
    print(f"composite    : changed={rep['composite_changed_rows']:,}  "
          f"same_rate={rep['composite_same_rate']:.4%}  "
          f"max|Δ|={rep['composite_max_abs_diff']:.4f}")
    if a.arm == "C3":
        print(f"C3 b_*_pct 獨立重算 : {rep.get('c3_pct_mismatch') or '全部相符'}  "
              f"NaN 位置 : {rep.get('c3_pct_nan_misalign') or '全部對齊'}")
        print(f"C3 來源 V0 欄複核  : composite_indep vs v0_real_composite "
              f"mismatch={rep.get('stored_indep_mismatch')} / "
              f"vs 現行 V0 面板 mismatch={rep.get('postprocess_source_vs_v0_mismatch')}")
    if a.arm == "C1":
        print(f"C1 來源 V0 欄複核  : composite_indep vs v0_real_composite "
              f"mismatch={rep.get('stored_indep_mismatch')} / "
              f"vs 現行 V0 面板 mismatch={rep.get('postprocess_source_vs_v0_mismatch')}")
    if a.arm in OOS_ZERO_ARMS:
        print(f"OOS 邊界({rep.get('oos_start')} 起) : "
              f"changed={rep.get('oos_changed_rows')} / {rep.get('oos_rows')}   ← 必須 0")
        print(f"2005-2018 變動列    : {rep.get('pre2019_changed_rows')} / "
              f"{rep.get('pre2019_rows')}   ← 必須 > 0")
    if a.arm == "C2":
        print(f"C2 dyn_weight True 列 : {rep.get('dyn_weight_true')}   ← 必須 0")
        print(f"C2 狀態 vs {rep.get('c2_ref_arm')} : {rep.get('c2_state_diff_vs_ref')}")
        print(f"C2 參考 dyn=True 列 : {rep.get('c2_ref_dyn_true_rows')}  / "
              f"在 dyn=False 處變動的列 : {rep.get('c2_changed_outside_dyn_rows')}")
    for w in rep["warnings"]:
        print(f"⚠ {w}")

    out = ARM_DIR / f"arm_{a.arm}_integrity_audit.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n稽核報告 → {out}")

    if rep["passed"]:
        print("\n✅ 完整性稽核通過")
    else:
        print("\n" + "=" * 96)
        for msg in rep["failures"]:
            print(f"❌ {msg}")
        print("=" * 96)
        raise SystemExit(f"❌ {a.arm} 完整性稽核未過 —— 保留原始錯誤,不放寬門檻。")


if __name__ == "__main__":
    main()
