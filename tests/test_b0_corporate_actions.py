"""W-1..W-4 corporate-action closure tests.

The claim under test is the completion condition: every corporate action that
changes B0 holdings / cash / security identity has a canonical handler, and a
gap fails loudly at the moment the portfolio is exposed to it — never silently.

Each guard is tested with a negative control, because a guard that cannot be
made to fire has not been shown to work.
"""

import pytest

from core.b0_corporate_actions import (
    CASH_CAPITAL_INCREASE_SUBSCRIBE,
    EVENT_KINDS,
    INTERPOLATION_ALLOWED,
    MISSING_DATA_RATE_THRESHOLD,
    NOT_APPLICABLE,
    NOT_RECONSTRUCTIBLE,
    RECONSTRUCTIBILITY_STATES,
    RECONSTRUCTIBLE,
    CorporateActionError,
    CorporateActionEvent,
    Exposure,
    assert_every_holder_affecting_kind_has_a_handler,
    assert_exposure_reconstructible,
    assert_never_subscribes,
    assert_no_threshold_policy,
    classify,
    classify_receivable_ordering,
    exposed_unreconstructible_events,
    holder_affecting_kinds,
    registered_handlers,
)


# --- three states, not two ---------------------------------------------------

def test_three_states_exist_and_are_distinct():
    assert RECONSTRUCTIBILITY_STATES == (
        RECONSTRUCTIBLE, NOT_RECONSTRUCTIBLE, NOT_APPLICABLE)
    assert len(set(RECONSTRUCTIBILITY_STATES)) == 3


def test_a_two_state_collapse_is_rejected():
    with pytest.raises(CorporateActionError):
        CorporateActionEvent("1101", "merger", "2020-01-01", "FAIL")


def test_not_reconstructible_requires_a_reason():
    """Without one, a known gap and an unnoticed event look identical."""
    with pytest.raises(CorporateActionError, match="reason"):
        CorporateActionEvent("1101", "merger", "2020-01-01", NOT_RECONSTRUCTIBLE)
    CorporateActionEvent("1101", "merger", "2020-01-01", NOT_RECONSTRUCTIBLE, "why")


# --- W-3: every holder-affecting kind has a handler --------------------------

def test_every_holder_affecting_kind_has_a_canonical_handler():
    assert_every_holder_affecting_kind_has_a_handler()
    for k in holder_affecting_kinds():
        assert k in registered_handlers()


def test_the_registry_would_notice_a_missing_handler(monkeypatch):
    """Negative control: drop a handler and the check must abort."""
    import core.b0_corporate_actions as ca
    monkeypatch.setattr(ca, "_HANDLERS",
                        {k: v for k, v in registered_handlers().items()
                         if k != "capital_reduction"})
    with pytest.raises(CorporateActionError, match="capital_reduction"):
        ca.assert_every_holder_affecting_kind_has_a_handler()


def test_dilution_only_kinds_are_declared_not_forgotten():
    """The largest event class in the corpus changes none of our quantities.
    It must be classified NOT_APPLICABLE explicitly, not omitted."""
    kinds = {e.key: e for e in EVENT_KINDS}
    for k in ("convertible_bond_conversion", "treasury_cancellation",
              "employee_bonus", "transfer_in", "other_share_change"):
        e = kinds[k]
        assert not (e.changes_our_shares or e.changes_our_cash
                    or e.changes_security_identity)
        assert classify(k, {"stock_id": "2330", "effective_date": "2020-01-01"}
                        ).reconstructibility == NOT_APPLICABLE


def test_an_unknown_kind_aborts_rather_than_defaulting():
    with pytest.raises(CorporateActionError, match="unknown"):
        classify("spin_off", {"stock_id": "2330"})


# --- W-2: zero-day receivable ------------------------------------------------

@pytest.mark.parametrize("ex,credit,expect", [
    ("2020-08-06", "2020-09-04", "ok"),
    ("2020-08-06", "2020-08-06", "zero_day"),
    ("2020-08-06", None, "missing"),
    ("2020-08-06", "2020-08-05", "before_ex"),
])
def test_receivable_ordering(ex, credit, expect):
    assert classify_receivable_ordering(ex, credit) == expect


def _sd(**kw):
    base = {"stock_id": "1101", "ex_right_date": "2020-08-06",
            "new_shares_thousands": 1000.0, "distribution_ratio_pct": 10.0,
            "credit_tradable_date": "2020-09-04", "is_ex_right_event": True}
    base.update(kw)
    return base


def test_W2_same_day_credit_is_reconstructible_and_flagged():
    e = classify("stock_dividend", _sd(credit_tradable_date="2020-08-06"))
    assert e.reconstructibility == RECONSTRUCTIBLE
    assert e.zero_day_receivable is True


def test_W2_credit_before_ex_right_is_not_reconstructible():
    e = classify("stock_dividend", _sd(credit_tradable_date="2020-08-05"))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "precedes" in e.reason


# --- W-1: missing credit date ------------------------------------------------

def test_W1_missing_credit_date_is_per_event_not_a_source_failure():
    e = classify("stock_dividend", _sd(credit_tradable_date=None))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert e.new_shares_thousands == 1000.0        # what IS known is preserved


def test_W1_no_threshold_and_no_interpolation_exist():
    assert MISSING_DATA_RATE_THRESHOLD is None
    assert INTERPOLATION_ALLOWED is False
    assert_no_threshold_policy()


def test_W1_a_threshold_would_be_rejected_if_reintroduced(monkeypatch):
    import core.b0_corporate_actions as ca
    monkeypatch.setattr(ca, "MISSING_DATA_RATE_THRESHOLD", 0.03)
    with pytest.raises(CorporateActionError, match="threshold"):
        ca.assert_no_threshold_policy()


def test_unflagged_capitalisation_is_not_treated_as_an_ex_right_event():
    """312 in-window rows carry new shares with no 配股率 and no credit date;
    their 年月日 is a registration stamp. Calling them ex-right stock dividends
    would invent an event date."""
    e = classify("stock_dividend", _sd(is_ex_right_event=False,
                                       distribution_ratio_pct=None,
                                       credit_tradable_date=None))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "registration stamp" in e.reason


# --- exposure gate: existence does not abort, exposure does ------------------

_GAP = CorporateActionEvent("2317", "stock_dividend", "2020-07-15",
                            NOT_RECONSTRUCTIBLE, "no credit date")
_OK = CorporateActionEvent("2330", "stock_dividend", "2020-07-15", RECONSTRUCTIBLE)


def test_an_event_we_never_held_does_not_abort():
    assert_exposure_reconstructible([_GAP], [Exposure("2330", "2020-01-01", "2021-01-01")])
    assert exposed_unreconstructible_events([_GAP], []) == []


def test_holding_through_an_unreconstructible_event_aborts():
    with pytest.raises(CorporateActionError, match="2317"):
        assert_exposure_reconstructible(
            [_GAP], [Exposure("2317", "2020-01-01", "2021-01-01")])


def test_exposure_is_date_bounded_not_merely_by_ticker():
    held_before = [Exposure("2317", "2019-01-01", "2020-07-14")]
    assert_exposure_reconstructible([_GAP], held_before)
    held_through = [Exposure("2317", "2019-01-01", "2020-07-15")]
    with pytest.raises(CorporateActionError):
        assert_exposure_reconstructible([_GAP], held_through)


def test_reconstructible_events_never_abort():
    assert_exposure_reconstructible([_OK], [Exposure("2330", "2020-01-01", "2021-01-01")])


# --- identity changes: unobservable on the holder side -----------------------

@pytest.mark.parametrize("kind", ["merger", "share_conversion"])
def test_identity_changes_are_never_silently_reconstructible(kind):
    e = classify(kind, {"stock_id": "3710", "effective_date": "2017-12-29"})
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "counterparty" in e.reason


def test_the_holder_side_detector_lives_outside_this_module():
    """O-B: the earlier guard took a global last_price_date lookup, i.e. it asked
    a question only the future can answer. It was removed, not repaired."""
    import core.b0_corporate_actions as ca
    assert not hasattr(ca, "assert_no_unexplained_disappearance")
    assert ca.HOLDER_SIDE_DETECTOR == (
        "core.b0_pit_observability.assert_no_unexplained_price_gap")


# --- W-4: never subscribe ----------------------------------------------------

def test_W4_subscription_is_frozen_off():
    assert CASH_CAPITAL_INCREASE_SUBSCRIBE is False
    assert_never_subscribes(False)


def test_W4_subscribing_aborts_and_is_not_strategy_selectable():
    with pytest.raises(CorporateActionError, match="W-4"):
        assert_never_subscribes(True)
    with pytest.raises(CorporateActionError, match="W-4"):
        classify("cash_capital_increase", {"stock_id": "2330", "subscribe": True})


def test_W4_unsubscribed_increase_is_not_applicable_to_our_shares():
    e = classify("cash_capital_increase",
                 {"stock_id": "2330", "effective_date": "2020-01-01"})
    assert e.reconstructibility == NOT_APPLICABLE


# --- capital reduction -------------------------------------------------------

def _cr(**kw):
    base = {"stock_id": "5383", "effective_date": "2017-12-21",
            "reduction_rate_pct": 29.84, "cash_per_share": 0.0,
            "cash_payment_date": None}
    base.update(kw)
    return base


def test_capital_reduction_yields_a_share_multiplier():
    e = classify("capital_reduction", _cr())
    assert e.reconstructibility == RECONSTRUCTIBLE
    assert e.share_multiplier == pytest.approx(1.0 - 0.2984)


def test_capital_reduction_with_cash_but_no_payment_date_is_not_reconstructible():
    """Cash without a date cannot be placed in the NAV series at all."""
    e = classify("capital_reduction", _cr(cash_per_share=1.429))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "退款日" in e.reason


def test_capital_reduction_with_cash_and_a_date_is_reconstructible():
    e = classify("capital_reduction",
                 _cr(cash_per_share=1.429, cash_payment_date="2018-02-01"))
    assert e.reconstructibility == RECONSTRUCTIBLE
    assert e.cash_per_share == 1.429


def test_capital_reduction_without_a_rate_is_not_reconstructible():
    e = classify("capital_reduction", _cr(reduction_rate_pct=None))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE


# --- par value change: the ratio must reconcile ------------------------------

def _pv(**kw):
    base = {"stock_id": "6531", "effective_date": "2021-10-07",
            "old_par": 10.0, "new_par": 5.0,
            "changed_shares_thousands": 74341.0,
            "total_shares_thousands": 148681.0}
    base.update(kw)
    return base


def test_par_change_reconciles_against_share_counts():
    e = classify("par_value_change", _pv())
    assert e.reconstructibility == RECONSTRUCTIBLE
    assert e.share_multiplier == pytest.approx(2.0)


def test_par_change_with_a_bad_par_does_not_silently_rescale():
    """Accepting the ratio without reconciliation would let one bad par value
    rescale a position by 100x."""
    e = classify("par_value_change", _pv(old_par=1000.0))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "reconcile" in e.reason


def test_par_change_with_non_positive_pre_event_shares_is_rejected():
    e = classify("par_value_change", _pv(changed_shares_thousands=148681.0))
    assert e.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "not positive" in e.reason


# --- the built ledger is the one the verifier reads --------------------------

def test_ledger_and_stock_dividend_view_agree_on_classification():
    import csv
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ledger = os.path.join(repo, "data", "b0", "corporate_actions_ledger.csv")
    view = os.path.join(repo, "data", "b0", "stock_dividend_pit.csv")
    if not (os.path.exists(ledger) and os.path.exists(view)):
        pytest.skip("ledger not built in this checkout")

    with open(ledger, encoding="utf-8") as fh:
        sd = [r for r in csv.DictReader(fh) if r["kind"] == "stock_dividend"]
    with open(view, encoding="utf-8") as fh:
        v = list(csv.DictReader(fh))
    assert len(sd) == len(v)
    assert ({(r["stock_id"], r["ex_or_effective_date"], r["reconstructibility"]) for r in sd}
            == {(r["stock_id"], r["ex_right_date"], r["reconstructibility"]) for r in v})
    assert {r["reconstructibility"] for r in v} <= set(RECONSTRUCTIBILITY_STATES)
