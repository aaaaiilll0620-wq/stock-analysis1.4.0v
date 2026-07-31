"""Gate 1 主判定(paired ΔIC + 12-arm joint max-t)的**回歸測試**。

為什麼要有這個測試(Codex 第九輪 §3):`scripts/gate1_delta_ic_maxt.py` 的
`delta_ic_t()` / `joint_maxt_null()` 是預註冊 `FaceRedesignV2` §5-2 **凍結**的判定演算法。
它有四個**結構性**性質,任何一個被改壞都會讓 Gate 1 的判定悄悄失效:

  1. **退化守衛**:arm 與 V0 數值上無差異時,`sd(ΔIC)` 是機器誤差級(實測 4e-17),
     `mean/sd` 會把浮點殘渣放大成**假 t≈0.56、虛無 max-t≈2.76** ——
     一個「什麼都沒改」的 arm 憑空拿到 t 值。`EPS_SD` 守衛必須把它壓成 t=0。
  2. **固定 seed 可重現**:凍結的門檻若不可重現,就不是凍結。
  3. **同一置換索引必須同時套用到全部 arm**:這是 paired + joint 的關鍵。
     若每個 arm 各自抽一組置換,arm 之間的相關結構就消失,max-t 退化成 Bonferroni。
  4. **退化族系不得噴 RuntimeWarning**:相關係數在退化時無定義,必須**明確回報**
     「無法估計」,不能靠 `nanmean` 把全 NaN 矩陣吞掉(那會噴
     `Mean of empty slice / All-NaN slice`)。

**刻意不測的東西**(Codex 第九輪 §3 明確指示):T2 的 FWER 區間與 T3 的檢定力
**不當成嚴格單元測試門檻** —— 小樣本置換的拒絕率本身有抽樣誤差,拿它當固定數字
斷言會變成脆弱測試。那兩項留在較慢的 synthetic validation
(`python scripts/gate1_delta_ic_maxt.py`)。

本測試用**自己造的小面板**(12 月 × 50 檔),不依賴研究面板存在,毫秒級跑完。
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

G = pytest.importorskip("gate1_delta_ic_maxt")

N_MONTHS = 12
N_STOCKS = 50
K = 12                      # arm 數(與凍結的 N_ARMS 同義,但測試用小 n_perm)
ARMS = [f"arm{j}" for j in range(K)]


def _panel(seed: int = 7) -> pd.DataFrame:
    """小面板:V0 分數與報酬有一點正相關,產業欄 5 類。"""
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(N_MONTHS):
        v0 = rng.standard_normal(N_STOCKS)
        ret = 0.15 * v0 + rng.standard_normal(N_STOCKS)      # 微弱正 IC
        rows.append(pd.DataFrame({
            "as_of": f"2020-{m + 1:02d}-28",
            "stock_id": [f"{1000 + i}" for i in range(N_STOCKS)],
            G.REAL_COMP_COL: v0,
            G.RET_COL: ret,
            "_ind": [f"ind{i % 5}" for i in range(N_STOCKS)],
        }))
    return pd.concat(rows, ignore_index=True)


def _with_arms(d: pd.DataFrame, deviations) -> pd.DataFrame:
    """deviations: list 長度 K,每個是 (n,) 的偏離或 None(= 完全等於 V0)。"""
    out = d.copy()
    for j, dev in enumerate(deviations):
        out[ARMS[j]] = out[G.REAL_COMP_COL] if dev is None else out[G.REAL_COMP_COL] + dev
    return out


# ---------------------------------------------------------------------------
# 1. 退化守衛
# ---------------------------------------------------------------------------
def test_degenerate_arms_give_zero_t_and_zero_threshold():
    """12 個 arm 全等於 V0 → 觀測 t 全 0、虛無 max-t 全 0 → `T*` = 0。

    沒有 EPS_SD 守衛時這裡會拿到 t≈0.56 / T*≈2.76(實測),
    等於「什麼都沒改」也能參加判定。
    """
    d = _with_arms(_panel(), [None] * K)
    blocks, info = G.build_month_blocks(d, ARMS)
    assert info["n_months"] == N_MONTHS

    t = G.delta_ic_t(blocks)
    assert t.shape == (K,)
    assert np.all(t == 0.0), f"退化 arm 的 t 必須恰為 0,實得 {t}"

    null = G.joint_maxt_null(blocks, n_perm=50, seed=G.SEED)
    assert null["degenerate"] is True
    assert null["T_star"] == 0.0
    assert np.all(null["maxt"] == 0.0)


def test_degenerate_rho_is_reported_not_nan():
    """退化族系的相關係數**無定義** → 必須回 None 並附狀態字串,不得回 NaN。"""
    d = _with_arms(_panel(), [None] * K)
    blocks, _ = G.build_month_blocks(d, ARMS)
    null = G.joint_maxt_null(blocks, n_perm=30, seed=G.SEED)
    assert null["rho_hat"] is None
    assert null["rho_min"] is None and null["rho_max"] is None
    assert "degenerate" in null["rho_status"]


def test_degenerate_emits_no_runtime_warning():
    """退化路徑不得噴 RuntimeWarning(`Mean of empty slice` / `All-NaN slice`)。"""
    d = _with_arms(_panel(), [None] * K)
    blocks, _ = G.build_month_blocks(d, ARMS)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        G.delta_ic_t(blocks)
        G.joint_maxt_null(blocks, n_perm=30, seed=G.SEED)


def test_partial_degenerate_excludes_constant_arms_from_rho():
    """一部分 arm 退化時:ρ̂ 仍可估計,但必須標記 `partial` 並排除恆定的 arm。"""
    rng = np.random.default_rng(11)
    n = N_MONTHS * N_STOCKS
    devs = [None] * (K - 3) + [rng.standard_normal(n) for _ in range(3)]
    d = _with_arms(_panel(), devs)
    blocks, _ = G.build_month_blocks(d, ARMS)
    null = G.joint_maxt_null(blocks, n_perm=60, seed=G.SEED)
    assert null["degenerate"] is False
    assert null["rho_hat"] is not None
    assert null["rho_status"].startswith("partial")


# ---------------------------------------------------------------------------
# 2. 固定 seed 可重現
# ---------------------------------------------------------------------------
def test_same_seed_reproduces_threshold():
    rng = np.random.default_rng(3)
    n = N_MONTHS * N_STOCKS
    d = _with_arms(_panel(), [rng.standard_normal(n) for _ in range(K)])
    blocks, _ = G.build_month_blocks(d, ARMS)
    a = G.joint_maxt_null(blocks, n_perm=80, seed=12345)
    b = G.joint_maxt_null(blocks, n_perm=80, seed=12345)
    assert a["T_star"] == b["T_star"]
    assert np.array_equal(a["maxt"], b["maxt"])

    c = G.joint_maxt_null(blocks, n_perm=80, seed=54321)
    assert c["T_star"] != a["T_star"], "不同 seed 應給出不同的虛無抽樣"


# ---------------------------------------------------------------------------
# 3. 同一置換索引必須同時套用到全部 arm
# ---------------------------------------------------------------------------
def test_identical_arms_get_identical_null_t_per_permutation():
    """12 個 arm **內容完全相同(但不等於 V0)** 時,每一次置換下 12 個 t 必須逐位相同。

    這是「同一組置換索引同時套用到全族」的**決定性**檢查:
    若每個 arm 各自抽一組置換,同一列的 12 個 t 就會彼此不同。
    """
    rng = np.random.default_rng(5)
    dev = rng.standard_normal(N_MONTHS * N_STOCKS)
    d = _with_arms(_panel(), [dev] * K)          # K 個一模一樣的 arm
    blocks, _ = G.build_month_blocks(d, ARMS)

    null = G.joint_maxt_null(blocks, n_perm=60, seed=G.SEED)
    spread = null["allt"].max(axis=1) - null["allt"].min(axis=1)
    assert np.allclose(spread, 0.0, atol=1e-12), (
        "同一次置換下,內容相同的 arm 必須得到相同的 t —— "
        f"實測最大跨 arm 差異 {spread.max():.3e},代表置換索引沒有共用")

    # 全族相同 → max-t 分布 == 單 arm t 分布 → ρ̂ 必須是 1
    assert null["rho_hat"] == pytest.approx(1.0, abs=1e-9)
    assert np.allclose(null["maxt"], null["allt"][:, 0], atol=1e-12)


def test_v0_leg_shares_the_same_permutation_as_arms():
    """V0 那一腿也必須吃同一組置換 —— 否則 ΔIC 的配對結構就斷了。

    測法:arm = V0 的**單調變換**(乘正數)→ rank 完全相同 → ΔIC 恆為 0。
    若 V0 與 arm 吃到不同的置換,ΔIC 就不會是 0。
    """
    d = _panel()
    d2 = d.copy()
    for c in ARMS:
        d2[c] = d2[G.REAL_COMP_COL] * 3.0 + 7.0     # 單調變換,rank 不變
    blocks, _ = G.build_month_blocks(d2, ARMS)
    null = G.joint_maxt_null(blocks, n_perm=40, seed=G.SEED)
    assert null["degenerate"] is True, "單調變換後 rank 相同 → 必須判為與 V0 無差異"
    assert np.all(null["maxt"] == 0.0)


# ---------------------------------------------------------------------------
# 4. 共同月份 / 共同股票集 / 缺值規則
# ---------------------------------------------------------------------------
def test_month_below_min_n_is_dropped_entirely():
    rng = np.random.default_rng(9)
    n = N_MONTHS * N_STOCKS
    d = _with_arms(_panel(), [rng.standard_normal(n) for _ in range(K)])
    bad = d["as_of"] == "2020-03-28"
    keep = bad & (d.groupby("as_of").cumcount() < G.MIN_N - 1)
    d.loc[bad & ~keep, G.RET_COL] = np.nan          # 該月只剩 29 檔
    blocks, info = G.build_month_blocks(d, ARMS)
    assert info["n_months"] == N_MONTHS - 1
    assert "2020-03-28" not in info["months"]
    assert info["dropped"] and info["dropped"][0][0] == "2020-03-28"


def test_one_arm_missing_removes_stock_from_common_set_for_all():
    """`I(t)` 是**交集**:任一 arm 缺值 → 該股在該月對**所有** arm 與 V0 一起被剔除。"""
    rng = np.random.default_rng(13)
    n = N_MONTHS * N_STOCKS
    d = _with_arms(_panel(), [rng.standard_normal(n) for _ in range(K)])
    d.loc[:4, ARMS[0]] = np.nan                      # 只讓 arm0 缺 5 檔
    blocks, info = G.build_month_blocks(d, ARMS)
    assert info["n_months"] == N_MONTHS
    assert blocks[0][0].shape[0] == N_STOCKS - 5      # 第一個月共同股票集少 5 檔
    assert blocks[0][1].shape[0] == N_STOCKS - 5      # V0 腿用同一組股票


# ---------------------------------------------------------------------------
# 5. G1-c(產業內中性化)必須與 G1-a 跑在同一組 M*
# ---------------------------------------------------------------------------
def test_industry_neutral_uses_same_months_as_raw():
    rng = np.random.default_rng(17)
    n = N_MONTHS * N_STOCKS
    d = _with_arms(_panel(), [rng.standard_normal(n) for _ in range(K)])
    b_raw, i_raw = G.build_month_blocks(d, ARMS)
    b_ind, i_ind = G.build_month_blocks(d, ARMS, neutral_by="_ind")
    G.assert_same_months(i_raw, i_ind)               # 不得 raise
    assert i_ind["neutral_by"] == "_ind"
    assert len(b_raw) == len(b_ind)
    # 中性化確實改變了分數(否則 G1-c 等於 G1-a)
    assert not np.allclose(b_raw[0][1], b_ind[0][1])


def test_assert_same_months_raises_on_mismatch():
    with pytest.raises(SystemExit):
        G.assert_same_months({"months": ["a", "b"]}, {"months": ["a"]})
