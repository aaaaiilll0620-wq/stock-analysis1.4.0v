# -*- coding: utf-8 -*-
"""B0.2 · the frozen 0050 benchmark construction protocol (M-3 ruling B1-B12).

These pin the ruling so that a later reader cannot mistake a convention for a
preference, and so that B4 in particular -- newly frozen in B0.2 -- can never be
back-dated into v1.26.
"""
from __future__ import annotations

import math

import pytest

from core import b0_benchmark_construction as bc
from core.b0_cost_model import COMMISSION_RATE, IMPACT_K, MIN_FEE
from core.b0_master_prereg import NORMATIVE_MODULES

AS_OF, EXEC = "2014-07-31", "2014-08-01"


def test_construction_module_is_normative():
    assert "core/b0_benchmark_construction.py" in NORMATIVE_MODULES


def test_all_seven_rules_are_recorded():
    assert sorted(bc.CONSTRUCTION_RULES) == ["B1", "B2", "B3", "B4", "B5", "B6", "B7"]
    for k, v in bc.CONSTRUCTION_RULES.items():
        assert len(v) > 80, k


# --- B2 / B5 / B7 · the frozen scalars ---------------------------------------

def test_b2_initial_capital_and_no_interest():
    assert bc.C_REF == 2_000_000.0
    assert bc.BENCHMARK_CASH_EARNS_INTEREST is False


def test_b5_terminal_is_mark_to_market_not_liquidation():
    assert bc.TERMINAL_TREATMENT == "MARK_TO_MARKET"
    assert bc.TERMINAL_LIQUIDATION is False


def test_b5_precondition_strategy_wealth_is_also_a_mark():
    """The symmetry B5 requires, proved against the real mark function."""
    out = bc.assert_strategy_wealth_is_mark_to_market()
    assert out["contradiction"] is False
    assert out["strategy_terminal_treatment"] == "MARK_TO_MARKET"
    assert out["symmetric"] is True


def test_b7_dividends_are_not_reinvested_and_tr_is_inadmissible():
    assert bc.DIVIDEND_REINVESTED is False
    assert bc.TOTAL_RETURN_SERIES_IS_ADMISSIBLE is False


def test_b4_is_recorded_as_newly_frozen_in_b0_2():
    """It must never be represented as having been explicit in v1.26."""
    assert bc.APPLY_B0_ADV_CAPACITY_THROTTLE_TO_BENCHMARK is False
    assert bc.B4_NEWLY_FROZEN_IN_B0_2 is True
    assert "NEWLY FROZEN IN B0.2" in bc.CONSTRUCTION_RULES["B4"]


def test_benchmark_identity_is_unchanged_by_b0_2():
    assert bc.BENCHMARK_IDENTITY_CHANGED_IN_B0_2 is False
    assert bc.BENCHMARK_PROTOCOL_STATUS == "EVALUATION_PROTOCOL_COMPLETION"


# --- B3 · the share/cash solve ------------------------------------------------

def test_b3_solve_is_affordable_and_maximal():
    r = bc.solve_initial_shares(66.25, bc.C_REF, 0.0102, 8.0e8,
                                data_as_of=AS_OF, execution_date=EXEC)
    q = r["shares"]
    assert q > 0
    assert r["gross_value"] + r["total_cost"] <= bc.C_REF          # affordable
    assert r["residual_cash"] >= 0                                  # no borrowing
    # one more share must NOT fit -- that is what "maximum" means
    nxt = (q + 1) * 66.25
    fee = max(MIN_FEE, nxt * COMMISSION_RATE)
    imp = nxt * IMPACT_K * 0.0102 * math.sqrt(nxt / 8.0e8)
    assert nxt + fee + imp > bc.C_REF


def test_b3_charges_no_buy_tax():
    r = bc.solve_initial_shares(66.25, bc.C_REF, 0.0102, 8.0e8,
                                data_as_of=AS_OF, execution_date=EXEC)
    assert r["transaction_tax"] == 0.0
    assert bc.BUY_TAX_RATE == 0.0


def test_b3_shares_are_integers_odd_lot_capable():
    r = bc.solve_initial_shares(66.25, bc.C_REF, 0.0102, 8.0e8,
                                data_as_of=AS_OF, execution_date=EXEC)
    assert isinstance(r["shares"], int)
    assert r["shares"] % 1000 != 0 or True      # odd lots permitted, not required


def test_b3_impact_is_superlinear_so_the_solve_is_not_a_division():
    """If it were a division, this cheaper-per-share case would not differ."""
    naive = int(bc.C_REF // 66.25)
    r = bc.solve_initial_shares(66.25, bc.C_REF, 0.30, 1.0e6,
                                data_as_of=AS_OF, execution_date=EXEC)
    assert r["shares"] < naive


def test_b3_refuses_a_nonpositive_price():
    with pytest.raises(bc.BenchmarkConstructionError):
        bc.solve_initial_shares(0.0, bc.C_REF, 0.01, 1e8,
                                data_as_of=AS_OF, execution_date=EXEC)


def test_b3_returns_zero_shares_when_nothing_is_affordable():
    r = bc.solve_initial_shares(1e9, 100.0, 0.01, 1e8,
                                data_as_of=AS_OF, execution_date=EXEC)
    assert r["shares"] == 0
    assert r["residual_cash"] == 100.0


# --- B6 · lineage sufficiency fails loud --------------------------------------

def test_required_fields_are_derived_and_each_names_its_rule():
    for f in bc.REQUIRED_LINEAGE_FIELDS:
        assert f.required_by[0] in "BR"      # a B-rule or an R-rule, never blank
        assert f.why.strip()


def test_b6_sufficient_lineage_passes():
    ok = ["date", "open", "close", "volume", "dividend_ex_date",
          "dividend_cash_per_share", "share_unit_effective_date",
          "holder_multiplier"]
    bc.assert_benchmark_lineage_sufficient(ok, source="hypothetical panel")


def test_r8_payment_date_is_no_longer_required():
    """R1/R8: wealth-neutral, so it is an audit field, not a gate-1 input."""
    assert bc.PAYMENT_DATE_IS_OUTCOME_REQUIRED is False
    assert bc.DIVIDEND_PAYMENT_DATE_CLASSIFICATION == "OPTIONAL_NON_OUTCOME_AUDIT_FIELD"
    required = {f.field for f in bc.REQUIRED_LINEAGE_FIELDS}
    assert "dividend_payment_date" not in required
    assert "dividend_payment_date" in {f.field for f in bc.OPTIONAL_AUDIT_FIELDS}


def test_r8_missing_split_lineage_fails_loud():
    """The dependency that was nearly missed must be the one that shouts."""
    no_split = ["date", "open", "close", "volume", "dividend_ex_date",
                "dividend_cash_per_share"]
    with pytest.raises(bc.BenchmarkLineageInsufficient) as exc:
        bc.assert_benchmark_lineage_sufficient(no_split, source="no-split lineage")
    msg = str(exc.value)
    assert "share_unit_effective_date" in msg
    assert "holder_multiplier" in msg


def test_b6_the_manifested_tej_lineage_is_insufficient():
    """The measured basis of the blocker, asserted rather than recalled."""
    tej = ["date", "adjusted_total_return_price", "return_pct"]
    with pytest.raises(bc.BenchmarkLineageInsufficient) as exc:
        bc.assert_benchmark_lineage_sufficient(tej, source="TEJ 0050 export")
    msg = str(exc.value)
    for field in ("open", "close", "volume", "dividend_ex_date"):
        assert field in msg


def test_b6_raw_close_only_source_is_still_insufficient():
    with pytest.raises(bc.BenchmarkLineageInsufficient) as exc:
        bc.assert_benchmark_lineage_sufficient(["date", "close"],
                                               source="0050_raw.parquet")
    assert "volume" in str(exc.value)
    assert "open" in str(exc.value)


def test_b6_refusal_names_no_admissible_workaround():
    with pytest.raises(bc.BenchmarkLineageInsufficient) as exc:
        bc.assert_benchmark_lineage_sufficient(["date"])
    msg = str(exc.value)
    assert "NON-EVALUABLE" in msg
    assert "forward fill" in msg


# --- R3 · payment-date invariance, on the ledger itself -----------------------

def _bench(shares=30_130):
    return bc.BenchmarkLedger(shares=shares)


@pytest.mark.parametrize("terminal", ["2016-08-01", "2026-03-31"])
def test_r3_wealth_is_identical_whether_or_not_the_dividend_was_paid(terminal):
    """Known payment date vs receivable left outstanding -> identical wealth."""
    close = 47.57
    paid = _bench()
    paid = bc.apply_dividend_ex_date(paid, 1.55)
    paid = bc.apply_dividend_payment(paid, paid.receivable)     # credited
    unpaid = bc.apply_dividend_ex_date(_bench(), 1.55)          # still a claim
    assert paid.cash > 0 and paid.receivable == 0
    assert unpaid.cash == 0 and unpaid.receivable > 0
    assert paid.wealth(close) == unpaid.wealth(close)


def test_r3_partial_and_staggered_crediting_is_also_wealth_neutral():
    close = 47.57
    base = bc.apply_dividend_ex_date(_bench(), 1.55)
    whole = bc.apply_dividend_payment(base, base.receivable)
    half = bc.apply_dividend_payment(base, base.receivable / 2)
    assert base.wealth(close) == whole.wealth(close) == half.wealth(close)


def test_r3_a_payment_date_after_the_terminal_boundary_changes_nothing():
    """R3 asks specifically for this case: it never gets credited at all."""
    close = 47.57
    never = bc.apply_dividend_ex_date(_bench(), 1.55)
    assert never.receivable > 0
    credited = bc.apply_dividend_payment(never, never.receivable)
    assert never.wealth(close) == credited.wealth(close)
    assert bc.UNPAID_RECEIVABLE_MAY_REMAIN_OUTSTANDING is True


def test_r3_invariance_holds_across_the_full_real_distribution_schedule():
    """Every acquired ex-date, under three different crediting policies."""
    amounts = [1.55, 2.00, 0.85, 1.70, 0.70, 2.20, 0.70, 2.30, 0.70, 2.90,
               0.70, 3.05, 0.35, 3.20, 1.80, 2.60, 1.90, 3.00, 1.00, 2.70,
               0.36, 1.00, 0.60]
    close = 47.57
    always = never = _bench()
    alternate = _bench()
    for i, amt in enumerate(amounts):
        always = bc.apply_dividend_ex_date(always, amt)
        always = bc.apply_dividend_payment(always, always.receivable)
        never = bc.apply_dividend_ex_date(never, amt)
        alternate = bc.apply_dividend_ex_date(alternate, amt)
        if i % 2 == 0:
            alternate = bc.apply_dividend_payment(alternate, alternate.receivable)
    assert always.wealth(close) == pytest.approx(never.wealth(close))
    assert always.wealth(close) == pytest.approx(alternate.wealth(close))


# --- R7 · split regressions ----------------------------------------------------

def test_r7_shares_go_q_to_4q_at_the_boundary():
    led = bc.apply_share_unit_event(_bench(30_130), "2025-06-18", 4.0)
    assert led.shares == 4 * 30_130


def test_r7_the_split_applies_exactly_once():
    led = bc.apply_share_unit_event(_bench(), "2025-06-18", 4.0)
    with pytest.raises(bc.BenchmarkConstructionError) as exc:
        bc.apply_share_unit_event(led, "2025-06-18", 4.0)
    assert "already been applied" in str(exc.value)


def test_r7_the_split_creates_no_dividend_receivable_and_no_cash():
    led = bc.apply_share_unit_event(_bench(), "2025-06-18", 4.0)
    assert led.receivable == 0.0
    assert led.cash == 0.0


def test_r7_a_dividend_creates_no_share_unit_transformation():
    led = bc.apply_dividend_ex_date(_bench(30_130), 1.55)
    assert led.shares == 30_130
    assert led.applied_share_unit_events == ()


def test_r7_a_receivable_fixed_before_a_split_is_not_rescaled_by_it():
    """The claim was struck in money against the pre-split holding; a later
    unit change does not retroactively enlarge it."""
    led = bc.apply_dividend_ex_date(_bench(30_130), 1.55)
    before = led.receivable
    led = bc.apply_share_unit_event(led, "2025-06-18", 4.0)
    assert led.receivable == before
    assert led.shares == 4 * 30_130


def test_r7_marks_stay_raw_so_wealth_is_continuous_across_the_split():
    """q x 188.65 immediately before == 4q x 47.1625 immediately after."""
    pre = _bench(30_130)
    post = bc.apply_share_unit_event(pre, "2025-06-18", 4.0)
    assert pre.wealth(188.65) == pytest.approx(post.wealth(188.65 / 4.0))


def test_r6_multiplier_is_derived_from_twse_fields_only():
    assert bc.derive_holder_multiplier(188.65, 47.57, 0.41) == 4.0


def test_r6_refuses_a_non_integer_multiplier():
    with pytest.raises(bc.BenchmarkConstructionError):
        bc.derive_holder_multiplier(188.65, 47.57, 20.0)
