# -*- coding: utf-8 -*-
"""per-arm baseline(勘誤 E1-E3)的測試。

背景:第一批預註冊 §5-2 把 `ΔIC(t) = IC_arm(t) − IC_V0(t)` 凍結成全族單一 baseline,
第二批 §0-1 卻要求 B1-B5/C2 的對照組是 `V0-C3`,而 §7 又要求 12 個 arm 同族算 `T*`。
凍結的 `delta_ic_t()` 只支援單一 `v0_col`,三條無法並存 —— Codex 2026-08-02 裁決採
per-arm baseline 擴充。

本檔驗證擴充**沒有動到既有語意**,以及新語意本身正確。
既有的 `tests/test_gate1_delta_ic.py`(11 項)一字未改,必須照樣全過。

⚠ 全部使用合成資料。**本檔不讀任何 candidate 面板、不產生任何 candidate 的
ΔIC / t / T* / p-value。**
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

G = pytest.importorskip("gate1_delta_ic_maxt")

N_MONTHS = 12
N_STOCKS = 50
K = 12
ARMS = [f"arm{j}" for j in range(K)]

# 真實宣告的形狀:族內第 5 個(index 5)扮演 C3,後 6 個以它為 baseline。
IDX_C3 = 5
REAL_SHAPE = [G.V0_BASELINE] * 6 + [IDX_C3] * 6


def _panel(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(N_MONTHS):
        v0 = rng.standard_normal(N_STOCKS)
        ret = 0.15 * v0 + rng.standard_normal(N_STOCKS)
        rows.append(pd.DataFrame({
            "as_of": f"2020-{m + 1:02d}-28",
            "stock_id": [f"{1000 + i}" for i in range(N_STOCKS)],
            G.REAL_COMP_COL: v0,
            G.RET_COL: ret,
            "_ind": [f"ind{i % 5}" for i in range(N_STOCKS)],
        }))
    return pd.concat(rows, ignore_index=True)


def _with_arms(d: pd.DataFrame, deviations) -> pd.DataFrame:
    out = d.copy()
    for j, dev in enumerate(deviations):
        out[ARMS[j]] = out[G.REAL_COMP_COL] if dev is None else out[G.REAL_COMP_COL] + dev
    return out


def _distinct_panel(seed: int = 11) -> pd.DataFrame:
    """12 個彼此不同的 arm(避免退化守衛把訊號吃掉)。"""
    rng = np.random.default_rng(seed)
    d = _panel(seed)
    n = len(d)
    return _with_arms(d, [rng.standard_normal(n) * 0.5 for _ in range(K)])


# ---------------------------------------------------------------------------
# 1. 回溯相容:省略參數必須與勘誤前**逐位元**相同
# ---------------------------------------------------------------------------
def test_default_is_bitwise_identical_to_all_v0():
    """`baseline_idx=None` 與「顯式宣告全族對 V0」必須逐位元相同。"""
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)

    t_default = G.delta_ic_t(blocks)
    t_explicit = G.delta_ic_t(blocks, baseline_idx=[G.V0_BASELINE] * K)
    assert np.array_equal(t_default, t_explicit), "顯式全 V0 與預設不一致"

    n1 = G.joint_maxt_null(blocks, n_perm=40, seed=G.SEED)
    n2 = G.joint_maxt_null(blocks, n_perm=40, seed=G.SEED,
                           baseline_idx=[G.V0_BASELINE] * K)
    assert n1["T_star"] == n2["T_star"]
    assert np.array_equal(n1["maxt"], n2["maxt"])
    assert np.array_equal(n1["allt"], n2["allt"])


# ---------------------------------------------------------------------------
# 2. 新語意正確性
# ---------------------------------------------------------------------------
def test_per_arm_baseline_matches_manual_pairing():
    """per-arm ΔIC 必須等於「手算的逐月配對相減」。

    這是勘誤的核心:B arm 的 ΔIC = IC_B − IC_C3(族內欄),
    第一批的 ΔIC = IC_arm − IC_V0。兩者在同一組 M*/I(t) 上。
    """
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    ica, ic0 = G._ic_row(blocks)

    expect = np.empty_like(ica)
    for k, b in enumerate(REAL_SHAPE):
        expect[:, k] = ica[:, k] - (ic0 if b == G.V0_BASELINE else ica[:, b])

    got = G.delta_ic_t(blocks, baseline_idx=REAL_SHAPE)
    assert np.allclose(got, G._t_of(expect), rtol=0, atol=0), "per-arm ΔIC 與手算不符"


def test_c3_itself_still_paired_against_v0():
    """扮演 C3 的那個 arm 自己仍對 V0 配對 —— 它是第一批成員,不對自己配對。"""
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    ica, ic0 = G._ic_row(blocks)

    t = G.delta_ic_t(blocks, baseline_idx=REAL_SHAPE)
    t_c3_expect = G._t_of((ica[:, IDX_C3] - ic0)[:, None])[0]
    assert t[IDX_C3] == pytest.approx(t_c3_expect, rel=0, abs=1e-12)


def test_arm_equal_to_its_baseline_arm_gives_zero_t():
    """B arm 與它的 baseline arm 完全相同 → sd(ΔIC)<EPS_SD → t 必須恰為 0。

    退化守衛的語意在 per-arm baseline 下必須延續:
    「與**自己宣告的** baseline 無數值差異」= 不得產生 t 值。
    """
    rng = np.random.default_rng(3)
    d = _panel(3)
    n = len(d)
    devs = [rng.standard_normal(n) * 0.5 for _ in range(K)]
    devs[7] = devs[IDX_C3]                       # arm7 與 C3 逐列相同
    d = _with_arms(d, devs)

    blocks, _ = G.build_month_blocks(d, ARMS)
    t = G.delta_ic_t(blocks, baseline_idx=REAL_SHAPE)
    assert t[7] == 0.0, f"與自己 baseline 相同的 arm 必須記 t=0,實得 {t[7]}"
    assert t[8] != 0.0, "其他 arm 不該被連帶歸零"


def test_maxt_is_taken_across_the_whole_family():
    """max 一律跨全部 12 個 arm 取,不因 baseline 不同而分組(勘誤 E3)。"""
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    null = G.joint_maxt_null(blocks, n_perm=50, seed=G.SEED, baseline_idx=REAL_SHAPE)
    assert null["allt"].shape == (50, K), "allt 必須含全部 12 個 arm"
    assert np.allclose(null["maxt"], null["allt"].max(axis=1)), \
        "maxt 必須是全族逐列 max"


def test_shared_permutation_across_mixed_baselines():
    """同一次置換的同一組打散順序,必須同時餵給 arm、它的 baseline arm 與 V0。

    做法:兩個 arm 設成完全相同,且都以 C3 為 baseline →
    它們每一次置換的 t 必須逐位元相同。若 baseline 那一腿各自重抽,這裡會不同。
    """
    rng = np.random.default_rng(5)
    d = _panel(5)
    n = len(d)
    devs = [rng.standard_normal(n) * 0.5 for _ in range(K)]
    devs[9] = devs[8]                            # arm8 ≡ arm9,兩者 baseline 都是 C3
    d = _with_arms(d, devs)

    blocks, _ = G.build_month_blocks(d, ARMS)
    null = G.joint_maxt_null(blocks, n_perm=40, seed=G.SEED, baseline_idx=REAL_SHAPE)
    assert np.array_equal(null["allt"][:, 8], null["allt"][:, 9]), \
        "相同 arm、相同 baseline 的每次置換 t 必須相同 → baseline 腿沒共用置換"


def test_same_seed_reproduces_with_per_arm_baseline():
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    a = G.joint_maxt_null(blocks, n_perm=60, seed=G.SEED, baseline_idx=REAL_SHAPE)
    b = G.joint_maxt_null(blocks, n_perm=60, seed=G.SEED, baseline_idx=REAL_SHAPE)
    assert a["T_star"] == b["T_star"]
    assert np.array_equal(a["allt"], b["allt"])


# ---------------------------------------------------------------------------
# 3. 宣告本身的 fail-closed
# ---------------------------------------------------------------------------
def test_self_referential_baseline_is_rejected():
    """arm 以自己為 baseline → ΔIC 恆為 0,那是恆等式不是檢定,必須 raise。"""
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    bad = list(REAL_SHAPE)
    bad[3] = 3
    with pytest.raises(ValueError, match="以自己為 baseline"):
        G.delta_ic_t(blocks, baseline_idx=bad)


def test_out_of_range_baseline_is_rejected():
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    with pytest.raises(ValueError, match="越界"):
        G.delta_ic_t(blocks, baseline_idx=[G.V0_BASELINE] * (K - 1) + [K])


def test_wrong_length_baseline_is_rejected():
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    with pytest.raises(ValueError, match="長度"):
        G.delta_ic_t(blocks, baseline_idx=[G.V0_BASELINE] * (K - 1))


@pytest.mark.parametrize("bad, exc, match", [
    ([-1.0] * 6 + [5.0] * 6, TypeError, "不是整數"),            # 全浮點
    ([-1] * 11 + [5.0], TypeError, "不是整數"),                 # 混一個浮點
    ([False] * 6 + [True] * 6, TypeError, "是 bool"),           # bool list
    ([-1] * 11 + [True], TypeError, "是 bool"),                 # 混一個 bool
    (np.zeros((2, 12), dtype=int), ValueError, "一維"),          # 二維
    (np.array([-1.0] * 6 + [5.0] * 6), TypeError, "整數 dtype"),  # 浮點 ndarray
    (np.array([True] * 12), TypeError, "bool 陣列"),             # bool ndarray
    (5, TypeError, "純量"),                                      # 純量
    ("-1" * 12, TypeError, "純量"),                              # 字串
    ([[-1]] * 12, ValueError, "一維"),                           # 巢狀
])
def test_declaration_rejects_silent_coercion(bad, exc, match):
    """宣告表是凍結研究設定 —— 型別出錯必須 raise,不得靜默轉型(Codex §3)。

    `np.asarray(x, dtype=int)` 會把 `2.0`→`2`、`True`→`1`、二維壓平。
    這些都會讓「宣告表寫錯」變成「跑出一組看起來正常的數字」。
    """
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    with pytest.raises(exc, match=match):
        G.delta_ic_t(blocks, baseline_idx=bad)


def test_numpy_int_array_is_accepted():
    """正確型別(整數 ndarray / list)必須照常接受,不可過度嚴格。"""
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    t_list = G.delta_ic_t(blocks, baseline_idx=REAL_SHAPE)
    t_np32 = G.delta_ic_t(blocks, baseline_idx=np.array(REAL_SHAPE, dtype=np.int32))
    t_np64 = G.delta_ic_t(blocks, baseline_idx=np.array(REAL_SHAPE, dtype=np.int64))
    assert np.array_equal(t_list, t_np32)
    assert np.array_equal(t_list, t_np64)


def test_null_validates_declaration_before_permuting():
    """宣告錯誤必須在跑 2000 次置換**之前**就 raise。"""
    d = _distinct_panel()
    blocks, _ = G.build_month_blocks(d, ARMS)
    bad = list(REAL_SHAPE)
    bad[0] = 0
    with pytest.raises(ValueError, match="以自己為 baseline"):
        G.joint_maxt_null(blocks, n_perm=2000, seed=G.SEED, baseline_idx=bad)
