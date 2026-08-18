"""Tests for the Frozen B0 cost model (docs/B14_CostModel_Closure_Phase2_Spec_2026-08-17.md §4).

Does not touch Frozen A: scripts/l4b_execution.py and portfolio_simulator_lab.py
are untouched, and their legacy constants remain pinned by
tests/test_canonical_universe.py.
"""

import math

import pytest

from core.b0_cost_model import (
    COMMISSION_RATE,
    IMPACT_K,
    MIN_FEE,
    TAX_RATE,
    CostModelError,
    aggregate_fills,
    child_order_cost,
    child_order_cost_from_fills,
    min_fee_breakeven_value,
)

D0, D1 = "2026-03-30", "2026-03-31"      # data_as_of strictly before execution


def _cost(value, side="buy", sigma=0.02, adv=1e8):
    return child_order_cost(value, side, sigma, adv, D0, D1, execution_confirmed=True)


# --- Frozen constants --------------------------------------------------------

def test_frozen_constants():
    assert COMMISSION_RATE == 0.001425
    assert MIN_FEE == 20.0
    assert TAX_RATE == 0.003
    assert IMPACT_K == 1.0


# --- T1 / T2 / T3: explicit fee, including the MIN_FEE non-linearity ----------

def test_T1_full_position_uses_proportional_leg():
    assert _cost(100_000).explicit_fee == pytest.approx(142.5)


def test_T2_small_order_hits_min_fee():
    c = _cost(2_000)
    assert c.explicit_fee == pytest.approx(20.0)
    assert c.explicit_fee / 2_000 == pytest.approx(0.01)


def test_T3_breakeven_point_and_both_sides():
    v_star = min_fee_breakeven_value()
    assert v_star == pytest.approx(20.0 / 0.001425)
    assert v_star == pytest.approx(14_035.0877, abs=1e-3)
    assert _cost(v_star * 1.01).explicit_fee == pytest.approx(v_star * 1.01 * COMMISSION_RATE)
    assert _cost(v_star * 0.99).explicit_fee == pytest.approx(MIN_FEE)
    assert _cost(v_star).explicit_fee == pytest.approx(MIN_FEE)


@pytest.mark.parametrize("value,expected_rate", [
    (100_000, 0.001425),
    (14_035.0877, 0.001425),
    (5_000, 0.004),
    (2_000, 0.010),
    (1_000, 0.020),
])
def test_T2b_effective_rate_curve(value, expected_rate):
    assert _cost(value).explicit_fee / value == pytest.approx(expected_rate, rel=1e-4)


# --- T4: tax is sell-side only ----------------------------------------------

def test_T4_tax_sell_side_only():
    assert _cost(100_000, side="buy").transaction_tax == 0.0
    assert _cost(100_000, side="sell").transaction_tax == pytest.approx(300.0)


# --- T5 / T6: impact ---------------------------------------------------------

def test_T5_impact_matches_formula_bitwise():
    v, sig, adv = 100_000.0, 0.0217, 5.0e8
    expected = v * IMPACT_K * sig * math.sqrt(v / adv)
    assert _cost(v, sigma=sig, adv=adv).impact == expected


def test_T6_impact_rate_capped_at_participation_limit():
    """Q/ADV = 1% (the B-06 policy cap) => impact rate == 0.1 * sigma."""
    sig = 0.0217
    v = 100_000.0
    adv = v / 0.01
    assert _cost(v, sigma=sig, adv=adv).impact / v == pytest.approx(0.1 * sig)


# --- T7: G14-2, MIN_FEE per child order, not per fill ------------------------

def test_T7_min_fee_charged_once_per_child_order():
    fills = [1_000.0, 1_000.0]
    agg = child_order_cost_from_fills(fills, "buy", 0.02, 1e8, D0, D1,
                                      execution_confirmed=True)
    assert agg.explicit_fee == pytest.approx(MIN_FEE)
    per_fill = sum(_cost(f).explicit_fee for f in fills)
    assert per_fill == pytest.approx(2 * MIN_FEE)
    assert agg.explicit_fee < per_fill


def test_T7b_aggregate_fills_sums_and_validates():
    assert aggregate_fills([1.5, 2.5]) == pytest.approx(4.0)
    for bad in ([], [-1.0], [float("nan")], [0.0]):
        with pytest.raises(CostModelError):
            aggregate_fills(bad)


# --- T8: G14-1, no execution-day look-ahead ----------------------------------

@pytest.mark.parametrize("data_as_of,execution_date", [
    ("2026-03-31", "2026-03-31"),
    ("2026-04-01", "2026-03-31"),
])
def test_T8_lookahead_is_rejected(data_as_of, execution_date):
    with pytest.raises(CostModelError, match="look-ahead"):
        child_order_cost(100_000, "buy", 0.02, 1e8, data_as_of, execution_date,
                         execution_confirmed=True)


def test_T8b_strictly_prior_data_is_accepted():
    child_order_cost(100_000, "buy", 0.02, 1e8, "2026-03-30", "2026-03-31",
                     execution_confirmed=True)


def test_T8c_missing_dates_rejected():
    with pytest.raises(CostModelError):
        child_order_cost(100_000, "buy", 0.02, 1e8, "", "2026-03-31",
                         execution_confirmed=True)


# --- T9: three-way separation ------------------------------------------------

def test_T9_components_separate_and_sum_to_total():
    c = _cost(100_000, side="sell", sigma=0.0217, adv=5.0e8)
    assert c.explicit_fee > 0 and c.transaction_tax > 0 and c.impact > 0
    assert c.total == pytest.approx(c.explicit_fee + c.transaction_tax + c.impact)


def test_T9b_no_single_blended_rate_exposed():
    with pytest.raises(AttributeError):
        _ = _cost(100_000).effective_rate


# --- T10: fail-loud inputs ---------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"value": 0}, {"value": -1}, {"value": float("inf")},
    {"adv": 0}, {"adv": -1},
    {"sigma": -0.01}, {"sigma": float("nan")},
])
def test_T10_invalid_inputs_raise(kwargs):
    with pytest.raises(CostModelError):
        _cost(**{"value": 100_000, **kwargs})


def test_T10b_unknown_side_raises():
    with pytest.raises(CostModelError):
        child_order_cost(100_000, "short", 0.02, 1e8, D0, D1, execution_confirmed=True)


# --- T11: G14-3, the cost model never decides tradability --------------------

def test_T11_execution_confirmed_is_required_and_keyword_only():
    with pytest.raises(TypeError):
        child_order_cost(100_000, "buy", 0.02, 1e8, D0, D1)          # no default
    with pytest.raises(TypeError):
        child_order_cost(100_000, "buy", 0.02, 1e8, D0, D1, True)    # positional blocked


@pytest.mark.parametrize("flag", [False, None, 0, 1, "yes"])
def test_T11b_unconfirmed_execution_is_rejected(flag):
    with pytest.raises(CostModelError, match="G14-3"):
        child_order_cost(100_000, "buy", 0.02, 1e8, D0, D1, execution_confirmed=flag)


def test_T11c_zero_sigma_is_flagged_not_silent():
    """sigma == 0 gives zero impact by definition, but must stay auditable."""
    c = _cost(100_000, sigma=0.0)
    assert c.impact == 0.0
    assert c.zero_sigma_fill is True
    assert _cost(100_000, sigma=0.02).zero_sigma_fill is False


def test_T11d_from_fills_also_requires_confirmation():
    with pytest.raises(CostModelError, match="G14-3"):
        child_order_cost_from_fills([1_000.0], "buy", 0.02, 1e8, D0, D1,
                                    execution_confirmed=False)


# --- G14-4 lives in tests/test_b0_regime_invariant.py, which shares the same
#     reachability machinery in core/b0_invariants.py.

# --- Frozen A must remain untouched -----------------------------------------

def test_frozen_A_constants_untouched():
    import scripts.l4b_execution as l4b
    assert l4b.BUY_COST == 0.001585
    assert abs(l4b.SELL_COST - 0.004585) < 1e-9
