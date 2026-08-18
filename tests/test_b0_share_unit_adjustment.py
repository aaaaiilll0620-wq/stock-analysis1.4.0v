"""C-50 · share-unit price adjustment, pinned by the ruling's own test list.

The twelve required cases, in the ruling's order. The load-bearing ones are the
negative controls: an adjustment rule is defined as much by what it refuses as by
what it does, and every refusal here is an event that DOES move shares
outstanding and must still not touch a holder's price history.

`SESSIONS` is a small synthetic calendar. Synthetic on purpose — these tests are
about the transformation, and a real ledger row would make the arithmetic depend
on data that can change underneath them.
"""

import pytest

from core.b0_features import compute_momentum_12_1
from core.b0_share_unit_adjustment import (
    ADJUSTED_CONSUMERS,
    ADJUSTMENT_BASIS,
    ELIGIBLE_KINDS,
    EXCLUDED_FROM_FACTOR,
    IDENTITY_CHANGE_KINDS,
    INELIGIBLE_KINDS,
    NOT_BOUNDARY_FIELD,
    RAW_CONSUMERS,
    ShareUnitAdjustmentError,
    ShareUnitEvent,
    UnreconstructibleAdjustment,
    adjusted_series,
    assert_consumer_reads_adjusted,
    assert_consumer_reads_raw,
    assert_no_identity_splice,
    assert_no_total_return_component,
    boundary_session,
    factors_for,
    holder_multiplier,
)
from core.b0_state import compute_sigma20d

SESSIONS = tuple("2020-%02d-%02d" % (m, d)
                 for m in (1, 2) for d in (3, 6, 9, 12, 15, 18, 21, 24, 27))
BOUNDARY = "2020-02-03"          # the 10th session


def _record(kind, mult, recon="RECONSTRUCTIBLE", sid="1234"):
    return {"stock_id": sid, "kind": kind, "share_multiplier": mult,
            "reconstructibility": recon, "ex_or_effective_date": BOUNDARY}


def _flat_then_flat(pre: float, post: float):
    """A series that is flat at `pre` before the boundary and `post` after."""
    return [pre if s < BOUNDARY else post for s in SESSIONS]


# --- 1-3 · eligible transformations remove the mechanical discontinuity -------

@pytest.mark.parametrize("m,pre,post,label", [
    (2.0, 100.0, 50.0, "1-for-2 split"),
    (0.5, 50.0, 100.0, "reverse split"),
    (1.1, 110.0, 100.0, "10% stock dividend"),
])
def test_an_eligible_transformation_leaves_no_artificial_jump(m, pre, post, label):
    ev = ShareUnitEvent("1234", "par_value_change" if m != 1.1 else "stock_dividend",
                        BOUNDARY, m)
    adj = adjusted_series(SESSIONS, _flat_then_flat(pre, post), factors_for([ev]))
    assert len(set(round(x, 9) for x in adj)) == 1, (
        f"{label}: the adjusted series should be flat, got {adj}")
    assert round(adj[-1], 9) == post, "the most recent price stays the raw quote"


def test_a_split_produces_no_artificial_momentum_discontinuity():
    """Case 1, through the frozen feature rather than through the helper."""
    raw = _flat_then_flat(100.0, 50.0)[:14]
    assert compute_momentum_12_1(raw) == pytest.approx(-50.0, abs=1e-9)
    ev = ShareUnitEvent("1234", "par_value_change", BOUNDARY, 2.0)
    adj = adjusted_series(SESSIONS[:14], raw, factors_for([ev]))
    assert compute_momentum_12_1(adj) == pytest.approx(0.0, abs=1e-9)


def test_a_reverse_split_produces_no_artificial_momentum_discontinuity():
    raw = _flat_then_flat(50.0, 100.0)[:14]
    assert compute_momentum_12_1(raw) == pytest.approx(100.0, abs=1e-9)
    ev = ShareUnitEvent("1234", "par_value_change", BOUNDARY, 0.5)
    adj = adjusted_series(SESSIONS[:14], raw, factors_for([ev]))
    assert compute_momentum_12_1(adj) == pytest.approx(0.0, abs=1e-9)


# --- 4 · a cash dividend is a real return and must survive -------------------

def test_a_cash_dividend_remains_visible_in_price_momentum():
    """§3.1 froze a PRICE relative, so the ex-dividend drop is signal, not noise."""
    raw = _flat_then_flat(100.0, 95.0)[:14]
    adj = adjusted_series(SESSIONS[:14], raw, factors_for([]))
    assert adj == pytest.approx(raw)
    assert compute_momentum_12_1(adj) == pytest.approx(-5.0, abs=1e-9)
    for component in EXCLUDED_FROM_FACTOR:
        with pytest.raises(ShareUnitAdjustmentError, match="R3"):
            assert_no_total_return_component(component)
    assert ADJUSTMENT_BASIS == "SHARE_UNIT_ADJUSTED"


# --- 5-6 · shares outstanding moving is not sufficient -----------------------

@pytest.mark.parametrize("kind", INELIGIBLE_KINDS)
def test_an_outstanding_only_change_never_adjusts_holder_history(kind):
    """Case 5 and 6: dilution and cancellation are not transformations."""
    with pytest.raises(ShareUnitAdjustmentError, match="R2"):
        holder_multiplier(_record(kind, "1.05"))
    with pytest.raises(ShareUnitAdjustmentError, match="R2"):
        ShareUnitEvent("1234", kind, BOUNDARY, 1.05)


def test_a_cash_capital_increase_is_ineligible_even_with_a_multiplier():
    assert "cash_capital_increase" in INELIGIBLE_KINDS
    assert "cash_capital_increase" not in ELIGIBLE_KINDS


# --- 7 · the boundary is the market-effective session ------------------------

def test_capital_reduction_uses_the_market_effective_boundary_not_credit_date():
    m = holder_multiplier(_record("capital_reduction", "0.53626"))
    assert m == pytest.approx(0.53626)
    assert boundary_session(BOUNDARY, SESSIONS) == BOUNDARY
    # a non-session effective date resolves forward to the first quoted session
    assert boundary_session("2020-02-01", SESSIONS) == "2020-02-03"
    assert NOT_BOUNDARY_FIELD == "credit_tradable_date"


def test_an_unreconstructible_boundary_fails_rather_than_guessing():
    with pytest.raises(UnreconstructibleAdjustment, match="R4"):
        boundary_session("", SESSIONS)
    with pytest.raises(UnreconstructibleAdjustment, match="R4"):
        boundary_session("2099-01-01", SESSIONS)


# --- 8 · identity changes are not spliced ------------------------------------

@pytest.mark.parametrize("kind", IDENTITY_CHANGE_KINDS)
def test_a_cross_security_event_does_not_splice_price_history(kind):
    with pytest.raises(ShareUnitAdjustmentError, match="R5"):
        assert_no_identity_splice(kind, "1234", "5678")
    assert_no_identity_splice(kind, "1234", "1234")          # same id is fine
    with pytest.raises(ShareUnitAdjustmentError, match="R2"):
        ShareUnitEvent("1234", kind, BOUNDARY, 1.5)


# --- 9-11 · who reads which series ------------------------------------------

def test_sigma20d_does_not_receive_a_synthetic_split_shock():
    """Case 9: one -50% day inside the window is a fabricated volatility spike."""
    closes = [100.0] * 21
    closes[10:] = [50.0] * 11
    raw_sigma = compute_sigma20d(closes)
    ev = ShareUnitEvent("1234", "par_value_change", "B", 2.0)
    sessions = ["A"] * 10 + ["B"] * 11
    adj = adjusted_series(sessions, closes, factors_for([ev]))
    adj_sigma = compute_sigma20d(adj)
    assert raw_sigma > 0.1, "the raw series should show the fabricated shock"
    assert adj_sigma == pytest.approx(0.0, abs=1e-12)
    assert "sigma20d" in ADJUSTED_CONSUMERS


@pytest.mark.parametrize("consumer", ["marks", "execution_prices", "nav",
                                      "portfolio_market_value", "order_notional",
                                      "fees_tax"])
def test_money_quantities_stay_raw(consumer):
    """Case 10: these are amounts actually paid or actually traded."""
    assert_consumer_reads_raw(consumer)
    with pytest.raises(ShareUnitAdjustmentError, match="R6"):
        assert_consumer_reads_adjusted(consumer)


def test_adv20_stays_on_actual_dollar_liquidity():
    """Case 11: §4.2 is an absolute NTD threshold on liquidity that existed."""
    assert "adv20" in RAW_CONSUMERS
    assert_consumer_reads_raw("adv20")
    with pytest.raises(ShareUnitAdjustmentError, match="R6"):
        assert_consumer_reads_adjusted("adv20")


def test_only_momentum_and_sigma_read_the_adjusted_series():
    assert ADJUSTED_CONSUMERS == ("momentum_12_1", "sigma20d")
    for name in ADJUSTED_CONSUMERS:
        assert_consumer_reads_adjusted(name)
    with pytest.raises(ShareUnitAdjustmentError, match="not a declared consumer"):
        assert_consumer_reads_adjusted("value_ind_pct_b")


# --- 12 · determinism -------------------------------------------------------

def test_two_rebuilds_produce_identical_factors_and_series():
    from core.b0_canonical_hash import canonical_sha256

    events = [ShareUnitEvent("1234", "stock_dividend", "2020-01-12", 1.1),
              ShareUnitEvent("1234", "par_value_change", BOUNDARY, 2.0)]
    a, b = factors_for(events), factors_for(list(reversed(events)))
    assert a == b, "factor order must not depend on input order"
    prices = [100.0 + i for i in range(len(SESSIONS))]
    s1 = adjusted_series(SESSIONS, prices, a)
    s2 = adjusted_series(SESSIONS, prices, b)
    assert canonical_sha256(s1) == canonical_sha256(s2)
    # compounding is multiplicative across boundaries, not additive
    assert s1[0] == pytest.approx(100.0 / (1.1 * 2.0))


# --- R8 · the fail-loud paths, which are the whole safety property -----------

def test_an_eligible_event_without_a_multiplier_fails_loudly():
    """A stock dividend carrying only a new-share COUNT is not reconstructible."""
    with pytest.raises(UnreconstructibleAdjustment, match="no share_multiplier"):
        holder_multiplier(_record("stock_dividend", ""))


def test_a_non_reconstructible_event_fails_loudly():
    with pytest.raises(UnreconstructibleAdjustment, match="not RECONSTRUCTIBLE"):
        holder_multiplier(_record("capital_reduction", "0.5",
                                  recon="NOT_RECONSTRUCTIBLE"))


def test_an_unclassified_kind_is_not_silently_ineligible():
    with pytest.raises(UnreconstructibleAdjustment, match="not classified"):
        holder_multiplier(_record("some_new_event_kind", "1.5"))


def test_a_multiplier_of_one_does_not_create_a_boundary():
    with pytest.raises(ShareUnitAdjustmentError, match="transforms nothing"):
        ShareUnitEvent("1234", "stock_dividend", BOUNDARY, 1.0)


def test_every_ledger_kind_is_classified_by_the_ruling():
    """The real ledger's kinds, so a new one in the data cannot pass unnoticed."""
    import csv
    import os

    from core.b0_share_unit_adjustment import assert_kind_classified

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "b0", "corporate_actions_ledger.csv")
    if not os.path.exists(path):
        pytest.skip("ledger not materialized")
    kinds = {r["kind"] for r in csv.DictReader(open(path, encoding="utf-8"))}
    for kind in sorted(kinds):
        assert assert_kind_classified(kind) in (
            "eligible", "ineligible", "identity_change")
