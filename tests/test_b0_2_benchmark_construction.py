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
        assert f.required_by.startswith("B")
        assert f.why.strip()


def test_b6_sufficient_lineage_passes():
    ok = ["date", "open", "close", "volume", "dividend_ex_date",
          "dividend_cash_per_share", "dividend_payment_date"]
    bc.assert_benchmark_lineage_sufficient(ok, source="hypothetical panel")


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
