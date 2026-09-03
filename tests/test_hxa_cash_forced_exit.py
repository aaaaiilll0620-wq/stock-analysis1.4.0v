# -*- coding: utf-8 -*-
"""HX-A/CASH: a NOT_RECONSTRUCTIBLE cash exit becomes cash instead of blocking.

Frozen for lineage B1 only. Every test here is about the boundary of the rule,
because the rule's whole defence is that its scope is narrow and its bias was
measured on that scope (cash n=21, UNDERSTATES 21 / FLATTERS 0).
"""
from fractions import Fraction

import pytest

from core.b0_corporate_actions import (
    HXA_CASH_SCOPE, HXA_CASH_STALENESS_CAP_SESSIONS, NOT_RECONSTRUCTIBLE,
    CorporateActionEvent, CorporateActionReconstructionBlock,
    HxaCashAnchorUnavailable, hxa_cash_applies, hxa_cash_quantity,
    transition_portfolio,
)
from core.b0_state import PortfolioState, SecurityReceivable

SESSIONS = ["2020-01-%02d" % d for d in range(6, 15)]
BOUNDARY = "2020-01-14"


def _event(sid="8913", kind="holder_side_reorganization_exit"):
    return CorporateActionEvent(
        sid, kind, BOUNDARY, NOT_RECONSTRUCTIBLE,
        "authoritative status reason establishes a reorganization exit; the "
        "holder outcome is not reconstructible from it",
        event_id="%s|%s|%s" % (sid, kind, BOUNDARY),
        knowledge_ts=BOUNDARY)


def _state(shares=0, claim=None, cash=1000.0, sid="8913"):
    recv = ()
    if claim is not None:
        recv = (SecurityReceivable(
            security_id=sid, shares=Fraction(claim),
            credit_tradable_date="2017-07-28", event_id="seed",
            origin_effective_date="2017-07-28"),)
    return PortfolioState(as_of=BOUNDARY, cash=cash, shares={sid: shares} if shares else {},
                          security_receivables=recv,
                          holding_spells=(("2017-03-01", "2099-01-01"),) if shares else ())


def _anchor(price=13.30, session="2020-01-13"):
    return lambda sid, boundary: (price, session)


# --- scope ------------------------------------------------------------------

def test_the_scope_excludes_4152_because_two_b0_8_artefacts_disagree():
    """d8_1 says MIXED, the pass-2 extraction says C_CASH_ONE_DATE_AWAY.

    A rule may not rest on a contested classification, so the event stays out
    until it is adjudicated - failing closed, not being waved through.
    """
    assert "4152" not in HXA_CASH_SCOPE


def test_6514_is_in_scope_only_as_a_pending_adjudication():
    """WAS: "the scope excludes events whose semantics were never established".

    6514 carried a cash amount in the extraction while d8_1 called it UNKNOWN, so
    it was held out as a FALSE NEGATIVE - the safe direction, since a false
    POSITIVE (cash treatment on a share exchange) is the dangerous one.

    2026-09-03: it was added, and this test records WHY rather than being
    deleted. The user attested the consideration (NT$53.80, 昇達科/UMT reverse
    triangular merger) from their own research; the corpus independently
    corroborates the STRUCTURE (a 2024-03-13 「董事會通過反式三角合併案」 and a
    2024-10-16 「合併對價發放通知」 classed CASH_CONSIDERATION_PAYMENT) but not
    the AMOUNT - that document's body was never cached.

    Two facts travel with it, and this test is where they are checked rather
    than trusted:
      - the addition is a SEMANTIC change to a scope B1 §2.3(3) froze at 22, so
        it is not an erratum and its lineage is not yet adjudicated;
      - HX-A/CASH prices this exit at the pre-boundary close (50.80), 5.91%
        below the attested consideration - 7.9x the worst of the 19 measured
        cash legs (max 1.0075).
    """
    assert "8913" in HXA_CASH_SCOPE
    assert "6514" in HXA_CASH_SCOPE
    assert len(HXA_CASH_SCOPE) == 23, (
        "B1 §2.3(3) froze 22; 6514 is the 23rd and is PENDING. A further change "
        "to this scope must be adjudicated, not absorbed into this count.")


@pytest.mark.parametrize("kind", ["stock_dividend", "capital_reduction",
                                  "par_value_change"])
def test_only_holder_side_exits_are_in_scope(kind):
    assert not hxa_cash_applies(_event(kind=kind))


def test_a_reconstructible_event_is_not_in_scope():
    ev = CorporateActionEvent("8913", "holder_side_reorganization_exit",
                              BOUNDARY, "RECONSTRUCTIBLE")
    assert not hxa_cash_applies(ev)


# --- Q_total ----------------------------------------------------------------

def test_q_total_is_exact_and_keeps_the_sub_share_claim():
    """B0.7 stopped on a 1.076-share claim int() could never credit. Rounding
    here would leave that wall exactly where it was."""
    st = _state(shares=0, claim=Fraction("1.076"))
    assert hxa_cash_quantity(st, "8913") == Fraction("1.076")


def test_q_total_adds_shares_and_claims_but_not_pending_exit():
    """pending_exit counts shares that are ALREADY in `shares`; adding it would
    double the position."""
    st = PortfolioState(as_of=BOUNDARY, cash=0.0, shares={"8913": 100},
                        pending_exit={"8913": 100},
                        security_receivables=(SecurityReceivable(
                            security_id="8913", shares=Fraction("0.5"),
                            credit_tradable_date="2017-07-28", event_id="s",
                            origin_effective_date="2017-07-28"),),
                        holding_spells=(("2017-03-01", "2099-01-01"),))
    assert hxa_cash_quantity(st, "8913") == Fraction("100.5")


# --- the transition ---------------------------------------------------------

def test_a_claim_only_exposure_becomes_cash_instead_of_blocking():
    st = _state(claim=Fraction("1.076"), cash=1000.0)
    res = transition_portfolio(st, [_event()], as_of=BOUNDARY,
                               sessions=SESSIONS, period="2020-01",
                               hxa_anchor=_anchor())
    assert not res.state.security_receivables
    assert res.state.cash == pytest.approx(1000.0 + float(Fraction("1.076")) * 13.30)
    rec = [r for r in res.ledger if r.security_id == "8913"][0]
    assert rec.hxa_applied is True
    assert rec.hxa_note.startswith("HX-A:")
    assert rec.hxa_anchor_session == "2020-01-13"
    assert rec.hxa_q_total == "269/250"          # 1.076 kept exact, not rounded
    assert rec.blocking_reason is None           # disposed of, not blocked
    assert not any("actual" in f for f in rec.__dataclass_fields__)


def test_without_a_resolver_the_block_is_unchanged():
    """No anchor resolver is not a licence to guess."""
    st = _state(claim=Fraction("1.076"))
    with pytest.raises(CorporateActionReconstructionBlock):
        transition_portfolio(st, [_event()], as_of=BOUNDARY, sessions=SESSIONS,
                             period="2020-01")


def test_a_resolver_that_returns_none_still_blocks():
    st = _state(claim=Fraction("1.076"))
    with pytest.raises(CorporateActionReconstructionBlock):
        transition_portfolio(st, [_event()], as_of=BOUNDARY, sessions=SESSIONS,
                             period="2020-01",
                             hxa_anchor=lambda sid, b: None)


def test_an_out_of_scope_security_still_blocks_even_with_an_anchor():
    """The probe id is asserted out-of-scope, not assumed to be.

    This test used 6514 as its example of "out of scope". When 6514 was added to
    the scope the test went red -- which was correct, but only by luck: had it
    used an id that was later added SILENTLY the test would have kept passing
    while checking nothing. So the id is checked first, and the assertion names
    the file to fix.
    """
    probe = "1101"          # never a holder_side_reorganization_exit in B0/B1
    assert probe not in HXA_CASH_SCOPE, (
        "%s is now in HXA_CASH_SCOPE, so this test no longer proves that an "
        "out-of-scope security blocks. Pick an id that is still out of scope."
        % probe)
    # a SUB-share claim: a whole-share claim would be released by
    # `_release_matured` before the gate and there would be no exposure left
    st = _state(claim=Fraction("0.4"), sid=probe)
    with pytest.raises(CorporateActionReconstructionBlock):
        transition_portfolio(st, [_event(sid=probe)], as_of=BOUNDARY,
                             sessions=SESSIONS, period="2020-01",
                             hxa_anchor=_anchor())


def test_a_stale_anchor_fails_closed_rather_than_being_tolerated():
    stale = ["2019-11-%02d" % d for d in range(1, 30)] + SESSIONS
    st = _state(claim=Fraction("1.076"))
    with pytest.raises(HxaCashAnchorUnavailable):
        transition_portfolio(st, [_event()], as_of=BOUNDARY, sessions=stale,
                             period="2020-01",
                             hxa_anchor=_anchor(session="2019-11-01"))


def test_the_staleness_cap_is_the_frozen_ten():
    assert HXA_CASH_STALENESS_CAP_SESSIONS == 10


def test_an_anchor_at_or_after_the_boundary_is_refused_as_post_event_data():
    """The staleness gap counts sessions BETWEEN anchor and boundary, so an
    anchor at or after the boundary scores 0 and would sail through. This branch
    also `continue`s before `assert_no_look_ahead`, so nothing downstream would
    catch it either. Rule §2.3 says strictly before; R8 says post-event prices
    are inadmissible.
    """
    st = _state(claim=Fraction("1.076"))
    for bad_session in (BOUNDARY, "2020-01-20"):
        with pytest.raises(HxaCashAnchorUnavailable):
            transition_portfolio(
                st, [_event()], as_of=BOUNDARY,
                sessions=SESSIONS + ["2020-01-20"], period="2020-01",
                hxa_anchor=_anchor(session=bad_session))
