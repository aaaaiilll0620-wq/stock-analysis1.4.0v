"""§6.1 · corporate-action state transition conformance (Master v1.20).

The §6.1.18 list, plus I-CA-01 … I-CA-15. The load-bearing cases are the ones
that distinguish OWNED from TRADABLE from SPENDABLE: every silent NAV error this
clause exists to stop looks like a correct number until one of those three is
asked for separately.
"""

from fractions import Fraction

import pytest

from core.b0_corporate_actions import (
    IDENTITY_CHANGING_KINDS,
    NOT_RECONSTRUCTIBLE,
    RECONSTRUCTIBLE,
    CorporateActionEvent,
    CorporateActionReconstructionBlock,
    CorporateActionTransitionError,
    assert_no_adjusted_price_double_count,
    assert_transition_applied,
    assert_transition_fields_present,
    redate,
    transition_portfolio,
)
from core.b0_state import CoreStateError, PortfolioState, SecurityReceivable

S = tuple("2020-%02d-%02d" % (m, d) for m in (1, 2, 3) for d in range(1, 29))


def _p(**over):
    base = dict(as_of="2020-01-05", cash=10_000.0, shares={"1101": 1000})
    base.update(over)
    return PortfolioState(**base)


def _ev(kind, date, **kw):
    kw.setdefault("knowledge_ts", "2019-12-01")
    return CorporateActionEvent("1101", kind, date, RECONSTRUCTIBLE, **kw)


def _run(state, events, as_of):
    return transition_portfolio(redate(state, as_of), events, as_of=as_of,
                                sessions=S, period=as_of[:7])


# --- stock dividend -----------------------------------------------------------

def test_stock_dividend_normal_credit_is_owned_before_it_is_tradable():
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-09")
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 1000}, "not tradable yet"
    assert len(r.state.security_receivables) == 1
    assert r.state.security_receivables[0].shares == Fraction(100)
    assert "1101" in r.state.held_securities, "owned, so it must reach the mark"
    r2 = _run(r.state, [ev], "2020-01-09")
    assert dict(r2.state.shares) == {"1101": 1100}
    assert r2.state.security_receivables == ()


def test_stock_dividend_zero_day_credit_still_passes_through_a_receivable():
    """§6.1.7A: same-day credit is a release, never a skipped ledger step."""
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-06", zero_day_receivable=True)
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 1100}
    rec = r.ledger[0]
    assert rec.created_security_receivables, "the claim must be recorded"
    assert rec.released_security_receivables, "and its same-day release too"


# --- capital reduction --------------------------------------------------------

def test_capital_reduction_shares_only():
    ev = _ev("capital_reduction", "2020-01-06", share_multiplier=0.6)
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 600}
    assert r.state.cash == 10_000.0


def test_capital_reduction_refund_is_owned_before_it_is_spendable():
    ev = _ev("capital_reduction", "2020-01-06", share_multiplier=0.5,
             cash_per_share=2.0, cash_payment_date="2020-01-20")
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 500}
    assert r.state.cash == 10_000.0, "the refund is not spendable yet"
    assert [x.amount for x in r.state.cash_receivables] == [2000.0]
    assert r.state.spendable_cash() == 10_000.0
    r2 = _run(r.state, [], "2020-01-20")
    assert r2.state.cash == 12_000.0
    assert r2.state.cash_receivables == ()


def test_a_refund_with_no_payment_date_blocks_rather_than_being_spent_now():
    ev = _ev("capital_reduction", "2020-01-06", share_multiplier=0.5,
             cash_per_share=2.0)
    with pytest.raises(CorporateActionReconstructionBlock, match="cash_available_date"):
        _run(_p(), [ev], "2020-01-06")


# --- identity changes ---------------------------------------------------------

@pytest.mark.parametrize("kind", IDENTITY_CHANGING_KINDS)
def test_identity_change_ends_the_old_identity_and_never_splices(kind):
    ev = _ev(kind, "2020-01-06", successor_security_id="9999",
             stock_ratio=Fraction(3, 2), credit_tradable_date="2020-01-09")
    r = _run(_p(), [ev], "2020-01-06")
    assert "1101" not in r.state.shares, "I-CA-07"
    claim = r.state.security_receivables[0]
    assert (claim.security_id, claim.shares, claim.source_security_id) == (
        "9999", Fraction(1500), "1101")
    r2 = _run(r.state, [ev], "2020-01-09")
    assert dict(r2.state.shares) == {"9999": 1500}


def test_merger_cash_only():
    ev = _ev("merger", "2020-01-06", successor_security_id="9999",
             stock_ratio=Fraction(0), credit_tradable_date="2020-01-09",
             cash_per_share=15.0, cash_payment_date="2020-01-15")
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {}
    assert r.state.security_receivables == ()
    assert [x.amount for x in r.state.cash_receivables] == [15_000.0]
    assert r.state.cash == 10_000.0


def test_merger_mixed_consideration():
    ev = _ev("merger", "2020-01-06", successor_security_id="9999",
             stock_ratio=Fraction(1, 2), credit_tradable_date="2020-01-09",
             cash_per_share=5.0, cash_payment_date="2020-01-15")
    r = _run(_p(), [ev], "2020-01-06")
    assert r.state.security_receivables[0].shares == Fraction(500)
    assert [x.amount for x in r.state.cash_receivables] == [5_000.0]


# --- par value ----------------------------------------------------------------

@pytest.mark.parametrize("mult,expect", [(2.0, 2000), (0.5, 500)])
def test_par_value_change_scales_the_share_count(mult, expect):
    ev = _ev("par_value_change", "2020-01-06", share_multiplier=mult)
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {"1101": expect}


# --- §6.1.10 · pending exits --------------------------------------------------

@pytest.mark.parametrize("kind,kw", [
    ("capital_reduction", {"share_multiplier": 0.5}),
    ("par_value_change", {"share_multiplier": 0.5}),
])
def test_a_full_exit_obligation_scales_with_the_shares(kind, kw):
    p = _p(pending_exit={"1101": 1000})
    r = _run(p, [_ev(kind, "2020-01-06", **kw)], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 500}
    assert dict(r.state.pending_exit) == {"1101": 500}, "still a full exit"


def test_a_stock_dividend_does_not_resurrect_an_exited_position():
    """§6.1.10: a credit delay must not turn a zero target into a holding."""
    p = _p(pending_exit={"1101": 1000})
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-09")
    r = _run(p, [ev], "2020-01-06")
    assert "1101" in r.state.pending_exit_on_receivable
    r2 = _run(r.state, [ev], "2020-01-09")
    assert dict(r2.state.shares) == {"1101": 1100}
    assert dict(r2.state.pending_exit) == {"1101": 1100}, "the whole lot exits"


@pytest.mark.parametrize("kind", IDENTITY_CHANGING_KINDS)
def test_a_pending_exit_follows_the_economic_claim_across_an_identity_change(kind):
    p = _p(pending_exit={"1101": 1000})
    ev = _ev(kind, "2020-01-06", successor_security_id="9999",
             stock_ratio=Fraction(1), credit_tradable_date="2020-01-09")
    r = _run(p, [ev], "2020-01-06")
    assert "9999" in r.state.pending_exit_on_receivable, "I-CA-10"
    r2 = _run(r.state, [ev], "2020-01-09")
    assert dict(r2.state.pending_exit) == {"9999": 1000}


# --- §6.1.9 · fractional entitlement ------------------------------------------

def test_a_fractional_entitlement_is_kept_not_rounded_away():
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 3),
             credit_tradable_date="2020-01-09")
    p = _p(shares={"1101": 100})
    r = _run(p, [ev], "2020-01-06")
    assert r.state.security_receivables[0].shares == Fraction(100, 3)
    r2 = _run(r.state, [ev], "2020-01-09")
    assert dict(r2.state.shares) == {"1101": 133}
    left = r2.state.security_receivables[0].shares
    assert left == Fraction(1, 3), "the remainder is retained, not discarded"


def test_a_float_entitlement_is_refused_outright():
    with pytest.raises(CoreStateError, match="exact Fraction"):
        SecurityReceivable("1101", 33.33, "2020-01-09", "e1")


# --- §6.1.11/§6.1.12 · ordering, exposure, exactly-once ----------------------

def test_an_event_is_applied_exactly_once():
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-06")
    r = _run(_p(), [ev], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 1100}
    again = _run(r.state, [ev], "2020-01-07")
    assert dict(again.state.shares) == {"1101": 1100}, "I-CA-01"
    assert again.applied_event_ids == ()


def test_same_day_non_commuting_events_without_a_sequence_block():
    a = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
            credit_tradable_date="2020-01-09")
    b = _ev("merger", "2020-01-06", successor_security_id="9999",
            stock_ratio=Fraction(1), credit_tradable_date="2020-01-09")
    with pytest.raises(CorporateActionReconstructionBlock, match="causal sequence"):
        _run(_p(), [a, b], "2020-01-06")


def test_same_day_events_with_a_source_sequence_apply_in_that_order():
    a = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
            credit_tradable_date="2020-01-06",
            diagnostics={"event_sequence": 1})
    b = _ev("capital_reduction", "2020-01-06", share_multiplier=0.5,
            diagnostics={"event_sequence": 2})
    r = _run(_p(), [a, b], "2020-01-06")
    assert dict(r.state.shares) == {"1101": 550}


def test_an_unheld_not_reconstructible_event_is_irrelevant():
    ev = CorporateActionEvent("2330", "stock_dividend", "2020-01-06",
                              NOT_RECONSTRUCTIBLE, "no distribution rate")
    r = _run(_p(), [ev], "2020-01-06")
    assert r.skipped_unexposed == ("2330|stock_dividend|2020-01-06",)
    assert dict(r.state.shares) == {"1101": 1000}


def test_a_held_not_reconstructible_event_fails_closed_with_a_full_record():
    ev = CorporateActionEvent("1101", "stock_dividend", "2020-01-06",
                              NOT_RECONSTRUCTIBLE, "no distribution rate")
    with pytest.raises(CorporateActionReconstructionBlock) as exc:
        _run(_p(), [ev], "2020-01-06")
    d = exc.value.detail
    for k in ("security_id", "event_kind", "event_id", "effective_date",
              "exposure", "missing_fields", "pre_state_hash",
              "last_valid_state_hash"):
        assert k in d, "§6.1.14 F-CA-B requires %s in the record" % k


def test_a_pending_exit_alone_counts_as_exposure():
    """§6.1.12: an unresolved exit obligation is affected economic exposure."""
    p = _p(shares={"1101": 1000}, pending_exit={"1101": 1000})
    ev = CorporateActionEvent("1101", "capital_reduction", "2020-01-06",
                              NOT_RECONSTRUCTIBLE, "no surviving ratio")
    with pytest.raises(CorporateActionReconstructionBlock):
        _run(p, [ev], "2020-01-06")


# --- §6.1.5 · PIT -------------------------------------------------------------

def test_information_that_was_not_knowable_yet_cannot_be_applied():
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-09", knowledge_ts="2020-02-01")
    with pytest.raises(CorporateActionTransitionError, match="I-CA-06"):
        _run(_p(), [ev], "2020-01-06")


def test_a_partially_specified_event_blocks_rather_than_transitioning():
    ev = _ev("stock_dividend", "2020-01-06", credit_tradable_date="2020-01-09")
    with pytest.raises(CorporateActionReconstructionBlock, match="stock_ratio"):
        assert_transition_fields_present(ev)


# --- I-CA-13 atomicity, I-CA-15, and the stage guard --------------------------

def test_a_failed_transition_commits_nothing():
    good = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
               credit_tradable_date="2020-01-09")
    bad = CorporateActionEvent("1101", "capital_reduction", "2020-01-06",
                               NOT_RECONSTRUCTIBLE, "no surviving ratio",
                               diagnostics={"event_sequence": 2})
    good = CorporateActionEvent(**{**good.__dict__,
                                   "diagnostics": {"event_sequence": 1}})
    before = _p()
    with pytest.raises(CorporateActionReconstructionBlock):
        _run(before, [good, bad], "2020-01-06")
    assert dict(before.shares) == {"1101": 1000}
    assert before.security_receivables == ()
    assert before.applied_ca_event_ids == frozenset()


def test_adjusted_prices_may_not_be_used_after_an_explicit_share_transition():
    assert_no_adjusted_price_double_count("RAW_OBSERVED")
    with pytest.raises(CorporateActionTransitionError, match="I-CA-15"):
        assert_no_adjusted_price_double_count("SHARE_UNIT_ADJUSTED")


def test_marking_before_the_transition_ran_is_refused():
    """The defect that stopped the first authorized L2 run, as a test."""
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-09")
    with pytest.raises(CorporateActionTransitionError, match="never applied"):
        assert_transition_applied(_p(), [ev], as_of="2020-01-06")
    r = _run(_p(), [ev], "2020-01-06")
    assert_transition_applied(r.state, [ev], as_of="2020-01-06")


def test_an_unheld_event_does_not_require_a_transition():
    ev = CorporateActionEvent("2330", "stock_dividend", "2020-01-06",
                              RECONSTRUCTIBLE, stock_ratio=Fraction(1, 10),
                              credit_tradable_date="2020-01-09")
    assert_transition_applied(_p(), [ev], as_of="2020-01-06")


# --- I-CA-12 determinism ------------------------------------------------------

def test_the_same_inputs_produce_the_same_state_hash():
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-09")
    a = _run(_p(), [ev], "2020-01-06")
    b = _run(_p(), [ev], "2020-01-06")
    assert a.ledger[0].post_state_hash == b.ledger[0].post_state_hash
    assert a.ledger[0].pre_state_hash != a.ledger[0].post_state_hash


def test_every_transition_writes_a_complete_audit_row():
    ev = _ev("stock_dividend", "2020-01-06", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2020-01-09")
    rec = _run(_p(), [ev], "2020-01-06").ledger[0]
    for f in ("period", "event_id", "event_kind", "security_id", "knowledge_ts",
              "effective_date", "credit_tradable_date", "pre_tradable_shares",
              "post_tradable_shares", "created_security_receivables",
              "pending_exit_before", "pending_exit_after", "reconstructibility",
              "pre_state_hash", "post_state_hash", "event_source_hash"):
        assert getattr(rec, f) is not None or f in ("blocking_reason",)


# --- I-CA-08 · an unmarkable successor stops the NAV --------------------------

def test_an_unmarkable_successor_receivable_fails_closed():
    from core.b0_state import MarketSnapshot, SourceAttestation, mark_portfolio

    ev = _ev("merger", "2020-01-06", successor_security_id="9999",
             stock_ratio=Fraction(1), credit_tradable_date="2020-01-09")
    st = _run(_p(), [ev], "2020-01-06").state
    att = SourceAttestation("t", "x" * 64, True, True, (), True)
    snap = MarketSnapshot(as_of=st.as_of, attestation=att,
                          marks={"1101": 10.0}, adv20={}, sigma20d={})
    with pytest.raises(Exception):
        mark_portfolio(st, snap, ())
