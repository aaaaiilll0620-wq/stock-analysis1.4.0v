# -*- coding: utf-8 -*-
"""gate1_delta_ic_maxt.py — Gate 1 主判定的**凍結實作**:對 V0 的 paired ΔIC 檢定
+ **12-arm joint max-t** 校正,附**完整 synthetic test**。

Codex 第八輪 §1 選 (b):Gate 1 改成 `IC_arm − IC_V0` 的配對檢定,並要求先凍結
「共同月份 / 缺值規則 / 置換方式 / 12-arm max-t」;§4 另要求補上**實際 runner 的
12-arm 實作與 synthetic test** —— 舊的 `gate1_maxt_power_check.py` 只有單 arm +
等相關模擬,不算完成的驗證。

本檔提供:
  1. `delta_ic_t()`      —— 凍結的統計量(共同月份、共同股票集、缺值規則);
  2. `joint_maxt_null()` —— 凍結的 12-arm joint max-t 虛無分布(同一置換索引套用全族);
  3. `synthetic_suite()` —— 四項驗證:
       (T1) 退化:12 個 arm 全部等於 V0 → ΔIC ≡ 0,必須不拒絕;
       (T2) FWER:用**另一組 seed** 的虛無重抽檢查族系型一誤差 ≈ α;
       (T3) 檢定力:注入已知大小的 IC 改善,量偵測率;
       (T4) MDI:最小可偵測改善量(`T* · sd(ΔIC) / √|M*|`)。

⚠ **synthetic arm 不是 candidate arm。** 它們是用 V0 分數 + 雜訊(T1/T2)或
V0 分數 + 一小部分**未來報酬**(T3/T4)人工合成的,**刻意含有前視**,
唯一目的是校準這個檢定程序的操作特性。**它們不是策略、不會被採用、不建任何面板。**
本檔**不執行任何 candidate OOS**。

用法:python scripts/gate1_delta_ic_maxt.py
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

# ============================================================================
# 凍結參數(Codex 第八輪 §1/§4:必須事前寫死)
# ============================================================================
OOS_LO, OOS_HI = "2019-08-01", "2026-03-31"   # 主時鐘 80 月
MIN_N = 30            # 每月最少共同檔數;不足 → 該月不計入 M*
N_PERM = 2000         # 置換次數
SEED = 20260731
ALPHA = 0.05          # 單尾
N_ARMS = 12           # N_total
EPS_SD = 1e-12        # sd(ΔIC) 低於此值 → 視為「與 V0 數值上無差異」,t 記 0(見 T1)


# ============================================================================
# 1. 凍結的統計量
# ============================================================================
def build_month_blocks(d: pd.DataFrame, arm_cols: list, v0_col: str = REAL_COMP_COL,
                       ret_col: str = RET_COL, min_n: int = MIN_N,
                       neutral_by: str | None = None) -> tuple:
    """把面板整理成逐月的 (V0 rank, 各 arm rank, 報酬 rank),並套用凍結的缺值規則。

    **凍結的共同月份 / 共同股票集規則**:
      · 每個 as_of 的**共同股票集** `I(t)` = 該 as_of 母體中,
        `fwd_x` **與** V0 分數 **與全部 arm 分數**都非缺的交集;
      · `|I(t)| < min_n` → 該 as_of **整個** 不計入;
      · **族系共同月份集** `M*` = 通過上述檢查的 as_of。
        全部 12 個 arm 與 V0 **一律用同一組 `M*` 與同一組 `I(t)`**
        —— 否則各 arm 的 t 跑在不同月份/不同母體上,joint max-t 沒有意義。
      · 缺值**不補中性值、不補 0**,一律以剔除處理。

    **`neutral_by`(G1-c 用,凍結定義)**:給定產業欄位名時,
    把 V0 與各 arm 的**全體 rank 減掉「該股所屬產業的全體 rank 平均」**,再標準化。
      · **報酬那一腿不做中性化** —— 中性化的對象是分數,不是報酬。
        這與 `scripts/gate1_maxt_power_check._demean_by` 的定義**逐字相同**,
        所以 §5-2b 那張表的 V0 產業內中性化數字(IC 0.0020 / t 0.26)可以直接對照。
      · **`I(t)` 與 raw 版完全相同** —— 產業欄位已 `fillna('未分類')`,不會造成額外缺失。
        呼叫端應以 `assert_same_months()` 複核兩版的 `M*` 一致。

    回 (blocks, info):blocks = [(R_arms(n×K), r_v0(n), y(n)), …];
    info 含 M* 的月份數與被剔除的月份。
    """
    blocks, kept, dropped = [], [], []
    for a, g in d.groupby("as_of"):
        ok = g[ret_col].notna() & g[v0_col].notna()
        for c in arm_cols:
            ok &= g[c].notna()
        n = int(ok.sum())
        if n < min_n:
            dropped.append((str(a), n))
            continue
        gg = g.loc[ok]
        y = gg[ret_col].rank().to_numpy(float)
        r0s = gg[v0_col].rank()
        Rs = [gg[c].rank() for c in arm_cols]
        if neutral_by is not None:
            grp = gg[neutral_by]
            r0s = r0s - r0s.groupby(grp).transform("mean")
            Rs = [r - r.groupby(grp).transform("mean") for r in Rs]
        r0 = r0s.to_numpy(float)
        R = np.column_stack([r.to_numpy(float) for r in Rs])
        blocks.append((_z(R), _z(r0[:, None])[:, 0], _z(y[:, None])[:, 0]))
        kept.append(str(a))
    return blocks, {"n_months": len(kept), "months": kept, "dropped": dropped,
                    "neutral_by": neutral_by}


def assert_same_months(info_a: dict, info_b: dict) -> None:
    """G1-a 與 G1-c 必須跑在同一組 `M*` 上(Codex 第九輪 §1:同一共同股票集)。"""
    if info_a["months"] != info_b["months"]:
        raise SystemExit(
            f"G1-a 與 G1-c 的 M* 不一致:{len(info_a['months'])} vs {len(info_b['months'])}"
            " —— 兩者必須用同一組共同月份與共同股票集,否則 AND 判定沒有意義。")


def _z(X: np.ndarray) -> np.ndarray:
    """逐欄標準化(z-score)。rank 之後標準化 → Pearson 等於 Spearman。"""
    mu = X.mean(axis=0, keepdims=True)
    sd = X.std(axis=0, ddof=0, keepdims=True)
    sd = np.where(sd > 0, sd, 1.0)
    return (X - mu) / sd


def _ic_row(blocks, y_list=None) -> tuple:
    """回 (IC_arms 陣列 T×K, IC_v0 陣列 T)。y_list 給定時用它取代原始報酬(置換用)。"""
    T, K = len(blocks), blocks[0][0].shape[1]
    ica = np.empty((T, K))
    ic0 = np.empty(T)
    for i, (R, r0, y) in enumerate(blocks):
        yy = y if y_list is None else y_list[i]
        n = len(yy)
        ica[i] = (R.T @ yy) / n
        ic0[i] = float(r0 @ yy) / n
    return ica, ic0


def _t_of(x: np.ndarray, axis: int = 0) -> np.ndarray:
    """t = mean/sd·√n,**附退化守衛**(凍結規格的一部分)。

    `sd(ΔIC) < EPS_SD` 代表該 arm 與 V0 在數值上無差異(例如變更實際命中 0 列)。
    此時 mean 也是機器誤差級,`mean/sd` 會把浮點殘渣放大成有限的假 t
    (實測:全等於 V0 時會放大成 t≈0.56、虛無 max-t≈2.76)。
    → 一律記 **t = 0**,並由呼叫端報告成「與 V0 無差異」,不得產生 t 值。
    """
    n = x.shape[axis]
    sd = x.std(axis=axis, ddof=1)
    mean = x.mean(axis=axis)
    degenerate = sd < EPS_SD
    safe = np.where(degenerate, 1.0, sd)
    out = mean / safe * np.sqrt(n)
    return np.where(degenerate, 0.0, out)


V0_BASELINE = -1   # baseline_idx 中代表「對 V0(即 build_month_blocks 的 v0_col)」


def _check_baseline_idx(baseline_idx, K: int) -> np.ndarray:
    """驗證 per-arm baseline 宣告(勘誤 E1)。回正規化後的 int64 陣列。

    **一律拒絕靜默轉型**(Codex 2026-08-02 §3):`np.asarray(x, dtype=int)` 會把
    `2.0` 變 `2`、把 `True` 變 `1`、把 `[[...]]` 壓平 —— 宣告表是凍結研究設定,
    型別出錯時必須 raise 讓人看見,不得默默改成某個「看起來合理」的值。
    """
    if isinstance(baseline_idx, (str, bytes, bool, int, float, np.generic)):
        raise TypeError(
            f"baseline_idx 必須是長度 {K} 的一維整數序列,"
            f"收到純量/字串 {type(baseline_idx).__name__}")

    if isinstance(baseline_idx, np.ndarray):
        if baseline_idx.ndim != 1:
            raise ValueError(f"baseline_idx 必須是一維,收到 ndim={baseline_idx.ndim}")
        if baseline_idx.dtype == np.bool_:
            raise TypeError("baseline_idx 不得為 bool 陣列 —— True/False 不是 arm 索引")
        if baseline_idx.dtype.kind not in ("i", "u"):
            raise TypeError(
                f"baseline_idx 必須是整數 dtype,收到 {baseline_idx.dtype} —— 不做靜默轉型")
        b = baseline_idx.astype(np.int64, copy=True)
    else:
        try:
            seq = list(baseline_idx)
        except TypeError as exc:
            raise TypeError(f"baseline_idx 不可迭代:{exc}") from None
        for k, v in enumerate(seq):
            if isinstance(v, bool):          # 必須先於 int 檢查:Python 的 bool 是 int 子類
                raise TypeError(f"baseline_idx[{k}] 是 bool {v!r} —— 不是 arm 索引")
            if isinstance(v, (list, tuple, np.ndarray)):
                raise ValueError(f"baseline_idx 必須是一維,baseline_idx[{k}] 是序列")
            if not isinstance(v, (int, np.integer)):
                raise TypeError(
                    f"baseline_idx[{k}] = {v!r}({type(v).__name__})不是整數 —— 不做靜默轉型")
        b = np.asarray(seq, dtype=np.int64)

    if b.shape != (K,):
        raise ValueError(f"baseline_idx 長度須為 K={K},收到 {b.shape}")
    bad = [(k, int(v)) for k, v in enumerate(b)
           if not (v == V0_BASELINE or 0 <= v < K)]
    if bad:
        raise ValueError(f"baseline_idx 含越界值(須為 -1 或 0..{K-1}):{bad}")
    self_ref = [k for k, v in enumerate(b) if v == k]
    if self_ref:
        raise ValueError(
            f"baseline_idx 讓 arm {self_ref} 以自己為 baseline → ΔIC 恆為 0,"
            "那不是檢定而是恆等式;宣告寫錯了。")
    return b


def _delta_ic_matrix(ica: np.ndarray, ic0: np.ndarray,
                     baseline_idx=None) -> np.ndarray:
    """逐月配對的 ΔIC 矩陣 (T×K)。

    `baseline_idx=None` → 全族對 V0,`ica - ic0[:, None]`,**與勘誤前逐位元相同**。
    給定時 → 每個 arm 用自己宣告的 baseline:`-1` 代表 V0,`j` 代表族內第 j 個 arm。
    兩種情形都在**同一組 `M*` / `I(t)` / 同一組(置換後的)報酬**上相減,
    所以 paired 與 joint 的性質都保住(勘誤 E2)。
    """
    if baseline_idx is None:
        return ica - ic0[:, None]
    b = _check_baseline_idx(baseline_idx, ica.shape[1])
    base = np.where(b[None, :] == V0_BASELINE, ic0[:, None], ica[:, np.clip(b, 0, None)])
    return ica - base


def delta_ic_t(blocks, baseline_idx=None) -> np.ndarray:
    """**凍結的統計量**:每個 arm 的 `t(ΔIC)`,ΔIC(t) = IC_arm(t) − IC_baseline(t)
    在**同一組 `M*` 與同一組 `I(t)`** 上逐月配對相減。回長度 K 的陣列。

    `baseline_idx`(勘誤 E1,2026-08-02 加入):per-arm 的配對基準。
    省略 → 全族對 V0,行為與勘誤前完全相同(既有 11 項測試不受影響)。
    """
    ica, ic0 = _ic_row(blocks)
    return _t_of(_delta_ic_matrix(ica, ic0, baseline_idx))


# ============================================================================
# 2. 凍結的 12-arm joint max-t 虛無
# ============================================================================
def joint_maxt_null(blocks, n_perm: int = N_PERM, seed: int = SEED,
                    alpha: float = ALPHA, baseline_idx=None) -> dict:
    """**凍結的虛無**:逐 as_of 打散報酬 rank,**同一次置換的同一組打散順序
    同時套用到全部 12 個 arm 與 V0**(這是 paired + joint 的關鍵:
    保留 arm 之間的相關結構,否則 max-t 會退化成 Bonferroni)。

    每次置換 → 12 個 `t(ΔIC)` → 取 max → n_perm 次形成虛無分布 → 取 p(1−alpha)。

    `baseline_idx`(勘誤 E1):per-arm 的配對基準,語意見 `_delta_ic_matrix`。
    **max 一律跨全族 12 個 arm 取**,不因 baseline 不同而分組 —— 分組取 max 就是
    分批降低多重比較懲罰,第二批 §7 明文禁止(勘誤 E3)。
    當某個 arm 的 baseline 是族內另一個 arm 時,兩者的 IC 在**同一次置換的同一組
    打散順序**下算出,配對結構與「對 V0」的情形完全一致。
    """
    rng = np.random.default_rng(seed)
    K = blocks[0][0].shape[1]
    if baseline_idx is not None:
        _check_baseline_idx(baseline_idx, K)     # fail fast:不要跑完 2000 次才發現宣告錯
    maxt = np.empty(n_perm)
    allt = np.empty((n_perm, K))
    for b in range(n_perm):
        yp = [rng.permutation(y) for (_, _, y) in blocks]   # 同一組順序餵給所有 arm 與 V0
        ica, ic0 = _ic_row(blocks, yp)
        t = _t_of(_delta_ic_matrix(ica, ic0, baseline_idx))
        allt[b] = t
        maxt[b] = np.nanmax(t)
    thr = float(np.percentile(maxt[np.isfinite(maxt)], 100 * (1 - alpha)))
    # ---- arm 間相關 ρ̂ ----
    # **退化族系必須明確回報「無法估計」,不得靠 nanmean 吞掉**(Codex 第九輪必修點 1)。
    # 例:12 個 arm 全等於 V0 → 每個 arm 的 t 恆為 0 → 各欄變異數為 0 →
    # np.corrcoef 會 0/0 產生全 NaN 矩陣,再用 nanmean 會噴
    # 「Mean of empty slice / All-NaN slice」的 RuntimeWarning。
    out = {"T_star": thr, "maxt": maxt, "allt": allt,
           "rho_hat": None, "rho_min": None, "rho_max": None,
           "rho_status": "ok", "degenerate": False}
    colvar = allt.var(axis=0)
    if np.all(colvar < EPS_SD ** 2):
        out.update(rho_status="degenerate:所有 arm 的 t 恆定(與 V0 無差異)→ 相關係數無定義",
                   degenerate=True)
        return out
    live = np.where(colvar >= EPS_SD ** 2)[0]
    if len(live) < 2:
        out.update(rho_status=f"degenerate:只有 {len(live)} 個 arm 的 t 有變異 → 相關係數無定義",
                   degenerate=True)
        return out
    rho = np.corrcoef(allt[:, live], rowvar=False)
    iu = np.triu_indices(len(live), 1)
    vals = rho[iu]
    if len(live) < K:
        out["rho_status"] = f"partial:{K - len(live)} 個 arm 的 t 恆定,已排除後估計"
    out.update(rho_hat=float(vals.mean()), rho_min=float(vals.min()),
               rho_max=float(vals.max()))
    return out


# ============================================================================
# 3. synthetic arms(**不是 candidate**,只為校準檢定程序)
# ============================================================================
def make_synth(d: pd.DataFrame, n_arms: int, noise: float, signal: float,
               seed: int, shared: float = 0.0, signal_arms=(0,)) -> pd.DataFrame:
    """人工 arm(**不是 candidate**):

        e_j    = √shared·e_common + √(1−shared)·e_j          (逐 stock-month)
        score_j = z(rank(V0)) + noise·e_j + signal·z(rank(fwd_x))   [僅 signal_arms]

    · `noise` 模擬「單點定義變更造成的擾動」;
    · `shared` 控制 arm 之間**偏離方向的共同成分** —— 真實的 12 個 arm 都是 V0 的
      單點變體,偏離會高度相關,`shared` 就是用來重現這個結構的旋鈕;
    · `signal > 0` **刻意注入未來報酬**,只為把 ΔIC 推到已知大小以量偵測率。
      **這不是策略,不會被採用。**
    """
    rng = np.random.default_rng(seed)
    cols = {f"synth{j}": np.full(len(d), np.nan) for j in range(n_arms)}
    for _, g in d.groupby("as_of"):
        ok = g[RET_COL].notna() & g[REAL_COMP_COL].notna()
        gg = g.loc[ok]
        if len(gg) < MIN_N:
            continue
        pos = gg.index.to_numpy()               # d 已 reset_index → index 即位置
        n = len(gg)
        r0 = _z(gg[REAL_COMP_COL].rank().to_numpy(float)[:, None])[:, 0]
        yz = _z(gg[RET_COL].rank().to_numpy(float)[:, None])[:, 0]
        e_common = rng.standard_normal(n)
        for j in range(n_arms):
            e = (np.sqrt(shared) * e_common
                 + np.sqrt(1.0 - shared) * rng.standard_normal(n)) if shared > 0                 else rng.standard_normal(n)
            s = r0 + noise * e
            if j in signal_arms and signal > 0:
                s = s + signal * yz
            cols[f"synth{j}"][pos] = s
    out = d[["as_of", "stock_id"]].copy()
    for k, v in cols.items():
        out[k] = v
    return out


def _sd_dic(blocks) -> float:
    """各 arm 的 sd(ΔIC) 平均(供 MDI 換算)。"""
    ica, ic0 = _ic_row(blocks)
    return float(np.nanmean((ica - ic0[:, None]).std(axis=0, ddof=1)))


def hr(t):
    print("\n" + "=" * 92)
    print(t)
    print("=" * 92)



def _fam(d, arm_cols, noise, signal, seed, shared, neutral_by=None):
    sy = make_synth(d, N_ARMS, noise=noise, signal=signal, seed=seed, shared=shared)
    dd = d.merge(sy, on=["as_of", "stock_id"], how="left")
    return build_month_blocks(dd, arm_cols, neutral_by=neutral_by)


def _rho_str(nn: dict) -> str:
    """ρ̂ 的顯示 —— 退化族系明確回報「無法估計」,不用 NaN、也不吞警告。"""
    if nn["rho_hat"] is None:
        return "無法估計"
    return f"{nn['rho_hat']:.3f}"


def synthetic_suite(d: pd.DataFrame, neutral_by=None, tag="G1-a(raw ΔIC)",
                    v0_ic_ref: float = 0.0092) -> dict:
    """T1–T4。`neutral_by` 給定時就是 G1-c(產業內中性化 ΔIC),產生獨立的 `T*_ind`。"""
    arm_cols = [f"synth{j}" for j in range(N_ARMS)]
    verdict, star = {}, "_ind" if neutral_by else ""
    stat = "ΔIC_ind(產業內中性化)" if neutral_by else "ΔIC(raw)"
    hr(f"█████  {tag}  —— 統計量 {stat},門檻 T*{star}")
    if neutral_by:
        print(f"  中性化欄位:`{neutral_by}`;定義 = 全體 rank − 該股所屬產業的全體 rank 平均")
        print("  **報酬那一腿不中性化**;`I(t)` 與 raw 版相同(產業欄已 fillna)")

    # ---------------- T1 退化 ----------------
    hr(f"T1  [{tag}] 退化檢查:12 個 arm 全 = V0 → 必須判為「與 V0 無差異」,不得產生 t 值")
    d1 = d.copy()
    for c in arm_cols:
        d1[c] = d1[REAL_COMP_COL]
    b1, i1 = build_month_blocks(d1, arm_cols, neutral_by=neutral_by)
    t1 = delta_ic_t(b1)
    n1 = joint_maxt_null(b1, n_perm=200, seed=SEED)
    ok_t1 = bool(np.nanmax(np.abs(t1)) == 0.0 and np.nanmax(np.abs(n1["maxt"])) == 0.0
                 and n1["degenerate"] and n1["rho_hat"] is None)
    print(f"  M* = {i1['n_months']} 月;實測 sd(ΔIC) = {_sd_dic(b1):.3e}(機器誤差級)")
    print(f"  觀測 max|t| = {np.nanmax(np.abs(t1)):.3e}   虛無 max-t 的 max = "
          f"{np.nanmax(np.abs(n1['maxt'])):.3e}")
    print(f"  ρ̂ = {_rho_str(n1)}   狀態:{n1['rho_status']}")
    print(f"  → {'✅ 通過' if ok_t1 else '❌ 未通過'}"
          "(t=0、T*=0、相關係數明確回報無法估計、無 RuntimeWarning)")
    print("  ⚠ 兩件事都是實測逼出來的凍結規格:")
    print("     (a) 加 EPS_SD 守衛前,mean/sd 把 4e-17 級殘渣放大成假 t≈0.56、虛無 max-t≈2.76;")
    print("     (b) ρ̂ 原本用 nanmean 吞掉全 NaN 矩陣 → 噴 RuntimeWarning。現在明確回報。")
    verdict[f"T1{star}"] = ok_t1

    # ---------------- T2 FWER × 兩種 arm 相關結構 ----------------
    hr(f"T2  [{tag}] FWER 校準 × 兩種 arm 相關結構(驗證 joint max-t 真的在用相關結構)")
    print(f"  {'族系':<28}{'ρ̂':>10}{'T*' + star:>10}{'獨立虛無拒絕率':>16}{'判定':>8}")
    fams = [("A 偏離互相獨立(shared=0)", 0.0), ("B 偏離高度相關(shared=0.9)", 0.9)]
    res = {}
    for label, sh in fams:
        bb, ii = _fam(d, arm_cols, noise=0.30, signal=0.0, seed=101, shared=sh,
                      neutral_by=neutral_by)
        nn = joint_maxt_null(bb, n_perm=N_PERM, seed=SEED)
        nb = joint_maxt_null(bb, n_perm=N_PERM, seed=SEED + 777)
        fwer = float((nb["maxt"] > nn["T_star"]).mean())
        ok = 0.02 <= fwer <= 0.08
        res[label] = dict(blocks=bb, info=ii, null=nn, fwer=fwer)
        print(f"  {label:<28}{_rho_str(nn):>10}{nn['T_star']:>10.3f}"
              f"{fwer * 100:>15.2f}%{'✅' if ok else '⚠':>8}")
        verdict[f"T2-{label[0]}{star}"] = ok
    print("\n  對照:單 arm 單尾 95% ≈ 1.645;Bonferroni(0.05/12)≈ 2.638")
    print(f"  ⇒ ρ̂ 上升 → T*{star} 下降 → **joint max-t 確實在使用相關結構**,"
          "不是退化成 Bonferroni。")

    famA = res["A 偏離互相獨立(shared=0)"]
    T_star = famA["null"]["T_star"]        # 用最保守的族系當校準門檻
    M = famA["info"]["n_months"]
    sd_dic = _sd_dic(famA["blocks"])
    tA = delta_ic_t(famA["blocks"])
    print(f"\n  族系 A 的 12 個純雜訊 arm 觀測 t:min {np.nanmin(tA):+.2f} / "
          f"max {np.nanmax(tA):+.2f} → 超過 T*{star} 的 {int((tA > T_star).sum())} 個"
          "(期望 0:雜訊只會讓 IC 變差)")

    # ---------------- T4 MDI ----------------
    hr(f"T4  [{tag}] 最小可偵測改善量 MDI")
    mdi = T_star * sd_dic / np.sqrt(M)
    print(f"  MDI = T*{star} · sd(ΔIC) / √M* = {T_star:.3f} × {sd_dic:.5f} / √{M} = "
          f"**{mdi:+.5f} IC**")
    ref_label = "產業內中性化 " if neutral_by else ""
    print(f"  對照:V0 在同窗的 {ref_label}rank IC = **{v0_ic_ref:.4f}** → 需要約 "
          f"**+{mdi / v0_ic_ref * 100:.0f}%** 的相對改善才可能被此 Gate 偵測。")

    # ---------------- T3 檢定力 ----------------
    hr(f"T3  [{tag}] 檢定力:12 個 arm 中**只有 1 個**注入已知改善"
       f"(門檻固定為族系 A 的 T*{star})")
    print(f"  {'signal':>8}{'實測 ΔIC':>11}{'相對 V0':>10}{'平均 t':>9}{'偵測率':>9}"
          "   (每格 12 次重抽)")
    for sg in (0.001, 0.002, 0.003, 0.005, 0.010):
        hits, dics, ts = 0, [], []
        for rep in range(12):
            bb, ii = _fam(d, arm_cols, noise=0.30, signal=sg, seed=2000 + rep,
                          shared=0.0, neutral_by=neutral_by)
            ica, ic0 = _ic_row(bb)
            dics.append(float(np.nanmean(ica[:, 0] - ic0)))
            tt = float(delta_ic_t(bb)[0])
            ts.append(tt)
            hits += int(tt > T_star)
        print(f"  {sg:>8.3f}{np.mean(dics):>11.5f}{np.mean(dics) / v0_ic_ref:>9.0%}"
              f"{np.mean(ts):>9.2f}{hits / 12 * 100:>8.0f}%")

    hr(f"[{tag}] 小結")
    all_ok = all(verdict.values())
    for k, v in verdict.items():
        print(f"  {k}: {'✅ 通過' if v else '❌ 未通過'}")
    print(f"\n  → {tag} 的 12-arm 實作{'**可以**' if all_ok else '**還不能**'}當凍結 runner。")
    print(f"  → synthetic 校準值:T*{star} = **{T_star:.3f}**、MDI ≈ **{mdi:+.5f} IC**。")
    print("  → **這是校準值,不是真實門檻。** 真實值必須由同一凍結演算法在")
    print("     12 個真 arm 的共同資料上產生(Codex 第八輪 §4)。")
    return {"verdict": verdict, "T_star": T_star, "mdi": mdi, "M": M,
            "sd_dic": sd_dic, "rho_A": famA["null"]["rho_hat"],
            "rho_B": res["B 偏離高度相關(shared=0.9)"]["null"]["rho_hat"],
            "info": famA["info"]}


def main():
    d = load_real_panel(adv_floor=1e6)
    d["as_of"] = d["as_of"].astype(str)
    d = d[(d["as_of"] >= OOS_LO) & (d["as_of"] <= OOS_HI)].reset_index(drop=True)
    d["_ind"] = d["tej_ind_name"].fillna("未分類")
    print("=" * 92)
    print("Gate 1 主判定 —— paired ΔIC + 12-arm joint max-t 的**凍結實作 + synthetic test**")
    print("=" * 92)
    print(f"主時鐘 {OOS_LO} ~ {OOS_HI};面板 ADV≥100萬,{len(d):,} 列,"
          f"{d['as_of'].nunique()} 個 as_of;產業欄 `tej_ind_name` {d['_ind'].nunique()} 類")
    print(f"凍結參數:min_n={MIN_N} / n_perm={N_PERM} / seed={SEED} / "
          f"α={ALPHA}(單尾) / K={N_ARMS} / EPS_SD={EPS_SD:g}")
    print("\n⚠ synthetic arm **不是 candidate arm** —— T3 的 arm 刻意含前視,")
    print("   只為校準檢定程序的操作特性。本檔不執行任何 candidate OOS、不建任何面板。")

    ra = synthetic_suite(d, neutral_by=None, tag="G1-a(raw ΔIC)", v0_ic_ref=0.0092)
    rc = synthetic_suite(d, neutral_by="_ind", tag="G1-c(產業內中性化 ΔIC)",
                         v0_ic_ref=0.0020)

    assert_same_months(ra["info"], rc["info"])
    hr("G1-a 與 G1-c 併陳(通過條件是 **AND**,Codex 第九輪 §2)")
    print(f"  {'':<8}{'T*':>9}{'sd(ΔIC)':>11}{'MDI':>11}{'V0 同窗 IC':>12}"
          f"{'需要相對改善':>14}{'ρ̂ A/B':>16}")
    for name, r, ref in (("G1-a", ra, 0.0092), ("G1-c", rc, 0.0020)):
        print(f"  {name:<8}{r['T_star']:>9.3f}{r['sd_dic']:>11.5f}{r['mdi']:>+11.5f}"
              f"{ref:>12.4f}{r['mdi'] / ref * 100:>13.0f}%"
              f"{r['rho_A']:>9.3f}/{r['rho_B']:.3f}")
    print(f"\n  M* 一致:{ra['info']['n_months']} 月 = {rc['info']['n_months']} 月 ✅")
    ok = all(ra["verdict"].values()) and all(rc["verdict"].values())
    print(f"  兩套驗證全部通過:{'✅' if ok else '❌'}")
    print("\n  ⚠ **AND 的必然後果**:arm 必須同時在 raw 與產業內中性化兩個尺度上超過各自門檻。")
    print("     §5-2b 實測 V0 的產業內中性化 IC 只有 0.0020(t 0.26),所以 G1-c 需要的")
    print("     **絕對**改善量比 G1-a 小,但**相對**幅度大得多。這是「排序改善且不是單純")
    print("     產業暴露」的代價,已事前揭露。")
    return ok


if __name__ == "__main__":
    main()
