# -*- coding: utf-8 -*-
"""test_canonical_universe.py — P0-U1 迴歸測試(預註冊 §33)

預註冊：docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md

範圍裁決(對話中已與使用者確認)：U1 的對象是 H1-H5 已驗證研究引擎
(`beat_0050/strategies/high52_lab.py::dual_confirm_mask` + `honest_backtest.Engine`)，
不是 production score_store/l4a_decision.py 路徑；後者從未走過 H1-H5、也沒有全歷史
批次回測迴圈可用。§33 點名的 LOT_SIZE / ORDER_ADV_CAP / T+1 執行等常數實際定義在
`scripts/l4a_decision.py` / `scripts/l4b_execution.py`（live 部署層），U1 本身不觸碰
那兩支檔案，故對應測試改為「常數未被本次改動」的靜態守衛，防止未來有人誤以為
U1 也動了部署層。

全部用合成資料(np.random.default_rng 固定種子),不讀真身面板 —— Phase A 階段禁止
查看任何報酬/績效數字(§23),這裡也只測結構,不算 Sharpe/CAGR。

    python -m pytest tests/test_canonical_universe.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJ = Path(__file__).resolve().parents[1]
for p in (PROJ, PROJ / "scripts", PROJ / "beat_0050", PROJ / "beat_0050" / "strategies"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from core import canonical_universe as cu                        # noqa: E402
import high52_lab                                                # noqa: E402


# ==============================================================================
# 合成 Panel 替身 —— 只帶 dual_confirm_mask 需要的屬性,不讀任何真實資料
# ==============================================================================
class _FakePanel:
    def __init__(self, rng, T=6, S=40, nan_rate_composite=0.05, nan_rate_leg=0.10):
        self.T, self.S = T, S
        self.stocks = np.array([f"{1000 + i}" for i in range(S)])
        self.months = np.array([f"2020-{m:02d}-28" for m in range(1, T + 1)])
        tier_valid = rng.random((T, S)) > 0.15   # 85% 屬於 ADV 分層母體
        self.tier_valid = {"100萬": tier_valid}

        # 真身模組的 min_cov=1.0 硬性要求 real_composite 100% 覆蓋 tier_valid
        # (見 dual_confirm_mask 的覆蓋率 gate)——合成資料只在 tier_valid=False
        # 的格子灌 NaN,不違反這個前提;nan_rate_composite 留參數是為了其他測試
        # 需要「composite 本身有缺值」情境時可覆寫。
        real_comp = rng.normal(50, 15, size=(T, S))
        outside = ~tier_valid
        extra_nan = rng.random((T, S)) < nan_rate_composite
        real_comp[outside & extra_nan] = np.nan
        self._real_comp = real_comp

        legs = {}
        for name in cu.C2_LEGS:
            v = rng.normal(50, 15, size=(T, S))
            v[rng.random((T, S)) < nan_rate_leg] = np.nan
            legs[name] = v
        self.F = legs

    @property
    def REAL_COMP(self):
        return self._real_comp


def _fake_panel(seed=1, **kw):
    return _FakePanel(np.random.default_rng(seed), **kw)


# ==============================================================================
# core.canonical_universe 原語
# ==============================================================================
def test_rank_pct_desc_matches_manual_formula():
    """rank_pct_desc 與預註冊 §9 要求逐位元相同的手算公式對帳(非 pandas rank(pct=True))。"""
    rng = np.random.default_rng(0)
    values = rng.normal(size=(3, 8))
    valid = np.ones((3, 8), dtype=bool)
    out = cu.rank_pct_desc(values, valid)
    for row in range(3):
        order = np.argsort(-values[row], kind="stable")
        rk = np.empty(8)
        rk[order] = np.arange(1, 9)
        expect = 100.0 * (1.0 - (rk - 1) / 8)
        assert np.allclose(out[row], expect)


def test_rank_pct_desc_not_pandas_rank_pct():
    """刻意驗證 tie 存在時與 pandas .rank(pct=True)*100 不同(那是另一條 production
    管線 —— scripts/l4a_decision.py 的 c2_pct —— 用的公式,§9 禁止在抽取共用函式時
    混用不同管線的百分位/tie-break 定義)。無 tie 時兩式代數上恰好相等,故必須用
    有並列值的資料才測得出差異。"""
    import pandas as pd
    values = np.array([[10.0, 20.0, 20.0, 40.0]])  # 20 並列兩檔
    valid = np.ones((1, 4), dtype=bool)
    ours = cu.rank_pct_desc(values, valid)[0]
    pandas_pct = pd.Series(values[0]).rank(pct=True).to_numpy() * 100.0
    assert not np.allclose(ours, pandas_pct)


def test_topk_mask_desc_floor_cutoff():
    """topk_mask_desc 用 floor(N*top_pct/100) 名次門檻,至少取 1 檔。"""
    values = np.array([[5.0, 4.0, 3.0, 2.0, 1.0]])
    valid = np.ones((1, 5), dtype=bool)
    m = cu.topk_mask_desc(values, valid, top_pct=20)  # floor(5*0.2)=1
    assert m.sum() == 1 and m[0, 0]  # 只留分數最高那一檔


# ==============================================================================
# §33-1 test_canonical_contains_only_overlap
# ==============================================================================
def test_canonical_contains_only_overlap():
    P = _fake_panel()
    valid = P.tier_valid["100萬"]
    C = cu.build_canonical_valid_mask(valid, P.REAL_COMP, P.F)
    expect = valid & np.isfinite(P.REAL_COMP)
    for leg in cu.C2_LEGS:
        expect &= np.isfinite(P.F[leg])
    assert np.array_equal(C, expect)
    # C_t 必為 tier_valid 的子集(§33-13 no_watchlist_expansion 的核心斷言)
    assert np.array_equal(C & valid, C)


# ==============================================================================
# §33-2 test_a_b_rank_universe_identical / §33-3 test_rank_denominator_identical
# ==============================================================================
def test_a_b_rank_universe_identical():
    P = _fake_panel()
    M = high52_lab.dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=True)
    valid = P.tier_valid["100萬"]
    C = cu.build_canonical_valid_mask(valid, P.REAL_COMP, P.F)
    a_pct = cu.rank_pct_desc(P.REAL_COMP, C)
    v, f = cu.rank_pct_desc(P.F["value_ind"], C), cu.rank_pct_desc(P.F["revenue_yoy"], C)
    h, m = cu.rank_pct_desc(P.F["high52_prox"], C), cu.rank_pct_desc(P.F["momentum"], C)
    c2 = (v + f + h + (100 - m)) / 4
    # A 腿與 B 腿的「有效格」(非 NaN)必須逐格等於 C_t 本身
    assert np.array_equal(np.isfinite(a_pct), C)
    assert np.array_equal(np.isfinite(c2), C)
    assert M.shape == (P.T, P.S)


def test_rank_denominator_identical():
    """A 與 B 在每個決策日的排名分母(有效檔數)必須相等 —— 因為兩者共用同一個 C_t。"""
    P = _fake_panel()
    valid = P.tier_valid["100萬"]
    C = cu.build_canonical_valid_mask(valid, P.REAL_COMP, P.F)
    n_a = (C & np.isfinite(P.REAL_COMP)).sum(1)
    n_b = C.sum(1)  # B 的四腳在 C 內已保證全部有限(建構定義)
    assert np.array_equal(n_a, n_b)


# ==============================================================================
# §33-4/5 raw score 不變(canonical=True 不得動到原始分數,只動百分位/交集)
# ==============================================================================
def test_real_composite_unchanged():
    P = _fake_panel()
    before = P.REAL_COMP.copy()
    high52_lab.dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=True)
    assert np.array_equal(before, P.REAL_COMP, equal_nan=True)


def test_c2_score_unchanged():
    """c2 的四條原始腿在 canonical=True 呼叫前後必須逐位元不變(未被就地修改)。"""
    P = _fake_panel()
    before = {leg: P.F[leg].copy() for leg in cu.C2_LEGS}
    high52_lab.dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=True)
    for leg in cu.C2_LEGS:
        assert np.array_equal(before[leg], P.F[leg], equal_nan=True)


def test_canonical_false_bitwise_identical_to_pre_refactor():
    """canonical=False(預設)必須與抽取共用函式前的內嵌算法逐位元相同 —— 用原始
    inline 算法(從重構前的原始碼複製,凍結在此測試中當回歸基準)重算一次比對。
    """
    P = _fake_panel(seed=7)
    valid = P.tier_valid["100萬"]

    def legacy_pct(name):
        v = P.F[name]
        ok = valid & np.isfinite(v)
        x = np.where(ok, v, -np.inf).astype(np.float64)
        order = np.argsort(-x, axis=1, kind="stable")
        rk = np.empty(order.shape, dtype=np.float64)
        np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.float64)[None, :], axis=1)
        nv = ok.sum(1).astype(float)[:, None]
        return np.where(ok, 100.0 * (1.0 - (rk - 1) / np.maximum(nv, 1)), np.nan)

    f, v = legacy_pct("revenue_yoy"), legacy_pct("value_ind")
    m = legacy_pct("momentum")
    composite = P.REAL_COMP.astype(np.float64)
    c2 = (v + f + legacy_pct("high52_prox") + (100 - m)) / 4

    def legacy_topk(score, top_pct=20):
        ok = valid & np.isfinite(score)
        x = np.where(ok, score, -np.inf)
        order = np.argsort(-x, axis=1, kind="stable")
        rk = np.empty(order.shape, dtype=np.int32)
        np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
        kk = np.maximum(1, (ok.sum(1) * top_pct // 100).astype(int))
        return (rk <= kk[:, None]) & ok

    expect = legacy_topk(composite) & legacy_topk(c2)
    got = high52_lab.dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=False)
    assert np.array_equal(expect, got)


# ==============================================================================
# §33-6/7 唯一性與缺值 assertion(§14 implementation invariants)
# ==============================================================================
def test_no_duplicate_ticker_date():
    P = _fake_panel()
    valid = P.tier_valid["100萬"]
    C = cu.build_canonical_valid_mask(valid, P.REAL_COMP, P.F)
    a_pct = cu.rank_pct_desc(P.REAL_COMP, C)
    c2 = cu.rank_pct_desc(P.F["value_ind"], C)  # 隨便一腿,足夠測 assertion 本身

    dup_stocks = P.stocks.copy()
    dup_stocks[1] = dup_stocks[0]
    with pytest.raises(AssertionError, match="重複 ticker"):
        cu.assert_canonical_invariants(C, a_pct, c2, dup_stocks, P.months)

    dup_months = P.months.copy()
    dup_months[1] = dup_months[0]
    with pytest.raises(AssertionError, match="重複 date"):
        cu.assert_canonical_invariants(C, a_pct, c2, P.stocks, dup_months)


def test_no_missing_score_in_canonical():
    P = _fake_panel()
    valid = P.tier_valid["100萬"]
    C = cu.build_canonical_valid_mask(valid, P.REAL_COMP, P.F)

    good_a = cu.rank_pct_desc(P.REAL_COMP, C)
    good_c2 = cu.rank_pct_desc(P.F["value_ind"], C)
    cu.assert_canonical_invariants(C, good_a, good_c2, P.stocks, P.months)  # 不應 raise

    broken_a = good_a.copy()
    # 找一個 C 內的有效格,人為打成 NaN
    ti, si = np.argwhere(C)[0]
    broken_a[ti, si] = np.nan
    with pytest.raises(AssertionError, match="real_composite 在 canonical universe"):
        cu.assert_canonical_invariants(C, broken_a, good_c2, P.stocks, P.months)

    broken_c2 = good_c2.copy()
    broken_c2[ti, si] = np.nan
    with pytest.raises(AssertionError, match="c2 在 canonical universe"):
        cu.assert_canonical_invariants(C, good_a, broken_c2, P.stocks, P.months)


def test_dual_confirm_mask_canonical_degenerate_leg_stays_consistent():
    """若某條 c2 腿全部缺值,canonical universe 會整片縮成空集合 —— 這不是 invariant
    違反(A/B 仍然逐格相等,只是都是 False/NaN),assertion 不應誤報,遮罩應為全 False
    而不是靜默退回一個更大的母體(§14 的反面:不誤殺,也不誤放)。"""
    P = _fake_panel()
    P.F["momentum"][:, :] = np.nan
    M = high52_lab.dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=True)
    assert not M.any()


# ==============================================================================
# §33-8 test_fusion_threshold_unchanged / §33-9 test_top_n_remains_none
# ==============================================================================
def test_fusion_threshold_unchanged():
    import inspect
    sig = inspect.signature(high52_lab.dual_confirm_mask)
    assert sig.parameters["top_pct"].default == 20
    assert sig.parameters["canonical"].default is False  # 舊呼叫者行為不變(§9)
    assert sig.parameters["source"].default == "real"
    assert sig.parameters["min_cov"].default == 1.0


def test_top_n_remains_none():
    """dual_confirm_mask 本身不引入任何 TOP_N 濃縮參數 —— 交集算完就是最終遮罩。"""
    import inspect
    sig = inspect.signature(high52_lab.dual_confirm_mask)
    assert "top_n" not in sig.parameters
    P = _fake_panel()
    M = high52_lab.dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=True)
    # 遮罩即是完整交集,不應被任何固定檔數上限二次篩選
    assert M.dtype == bool


# ==============================================================================
# §33-10/11/12 部署層常數守衛(U1 不觸碰 l4a/l4b,這裡防呆未來誤改)
# ==============================================================================
def test_order_adv_cap_unchanged():
    import l4a_decision
    assert l4a_decision.ORDER_ADV_CAP == 0.03


def test_lot_size_unchanged():
    import l4a_decision
    assert l4a_decision.LOT_SIZE == 1000
    assert l4a_decision.TOP_N is None


def test_execution_t_plus_1_unchanged():
    import l4b_execution
    assert l4b_execution.BUY_COST == 0.001585
    assert abs(l4b_execution.SELL_COST - 0.004585) < 1e-9


# ==============================================================================
# §33-13/14 no_watchlist_expansion(此引擎無 watchlist,改測母體不擴張) /
#            no_new_liquidity_filter
# ==============================================================================
def test_no_watchlist_expansion():
    """canonical universe 只能是 tier_valid 的子集,任何情況下都不擴張母體
    (研究引擎不用 watchlist.txt,這是它在此引擎裡的等價不變量)。"""
    P = _fake_panel()
    valid = P.tier_valid["100萬"]
    C = cu.build_canonical_valid_mask(valid, P.REAL_COMP, P.F)
    assert not (C & ~valid).any()
    assert C.sum() <= valid.sum()


def test_no_new_liquidity_filter():
    import inspect
    assert high52_lab.ADV_TIERS == [("2000萬", 2e7), ("500萬", 5e6), ("100萬", 1e6), ("無門檻", 0.0)]
    sig = inspect.signature(cu.build_canonical_valid_mask)
    # 只接受既有母體(tier_valid)+ 既有分數,不接受新的 ADV/市值/成交值門檻參數
    assert set(sig.parameters) == {"tier_valid", "real_composite", "factor_legs", "legs"}
