"""B0.7 · claim-side corporate-action applicability.

The B0.6 diagnostic replay stopped at 2020-01 with a held position that had no
observable price. The audit found the price gap was the SECOND thing wrong. The
first was that the portfolio held an uncreditable fractional claim in that
security — 0.199... shares left over from a 2017 capital reduction, which
`int()` can never turn into a tradable share and §6.1.9 forbids rounding away —
while every holding spell in that security had been closed since 2017-08-01.

So the state said two incompatible things at once:

    held_securities   contains it, and I-CA-08 requires it to be marked
    holding_spells    contains no covering spell, so no event could reach it

§6.1.12 had already settled which one is right for corporate actions:

    affected economic exposure 包含 tradable position、security receivable、
    entitlement-bearing claim、unresolved pending-exit claim

and every transition in §6.1.7 takes `Q` = entitlement-bearing shares, which
`_apply_one` has always read as `pre_shares + same_claims`. The code asked the
holding-spell ledger alone. Twenty-seven such claims had accumulated by 2020-01,
each one a marked NAV asset no corporate action could reach; the first security
to disappear surfaced as an unexplained gap instead of as the reorganization it
was.

B0.7 adds the second domain and combines the ANSWERS. It does not rename a claim
into underlying exposure: no spell opens, reopens or extends, and B0.1/R1 stands
exactly as frozen.

Nothing here names security 8913 or its event id.
"""

from fractions import Fraction

import pytest

from core.b0_corporate_actions import (
    CLAIM_BEARING_EVENT_KINDS,
    NOT_RECONSTRUCTIBLE,
    RECONSTRUCTIBLE,
    CorporateActionError,
    CorporateActionEvent,
    CorporateActionReconstructionBlock,
    CorporateActionTransitionError,
    assert_ca_event_delivery_conforms,
    assert_claim_bearing_registry_conforms,
    ca_economic_interest_applies,
    deliver_ca_events,
    economic_interest_securities,
    holder_affecting_kinds,
    is_exposed,
    redate,
    transition_portfolio,
)
from core.b0_state import CoreStateError, HoldingSpell, PortfolioState, SecurityReceivable

SESSIONS = tuple("%d-%02d-%02d" % (y, m, d)
                 for y in (2017, 2018, 2019, 2020)
                 for m in range(1, 13) for d in (1, 5, 9, 13, 15, 20, 28))
AS_OF = "2019-06-13"


def _claim(sid, shares, origin, credit="2030-01-01", source=""):
    return SecurityReceivable(
        security_id=sid, shares=Fraction(shares), credit_tradable_date=credit,
        event_id="seed|stock_dividend|%s" % origin,
        origin_effective_date=origin, source_security_id=source)


def _state(*, shares=None, claims=(), spells=(), as_of=AS_OF, **kw):
    # I-CA-03: a claim in an opening state has to trace to an event that was
    # already applied, or the invariant correctly refuses it as a free share.
    kw.setdefault("applied_ca_event_ids",
                  frozenset(c.event_id for c in claims))
    return PortfolioState(as_of=as_of, cash=1_000_000.0, shares=dict(shares or {}),
                          security_receivables=tuple(claims),
                          holding_spells=tuple(spells), **kw)


def _ev(sid, date, kind="stock_dividend", recon=RECONSTRUCTIBLE, **kw):
    kw.setdefault("knowledge_ts", "2010-01-01")
    if kind == "stock_dividend":
        kw.setdefault("stock_ratio", Fraction(1, 10))
        kw.setdefault("credit_tradable_date", "2020-12-28")
    if recon == NOT_RECONSTRUCTIBLE:
        return CorporateActionEvent(sid, kind, date, recon,
                                    kw.pop("reason", "terms not observable"), **kw)
    return CorporateActionEvent(sid, kind, date, recon, **kw)


def _run(state, events, as_of):
    return transition_portfolio(redate(state, as_of), events, as_of=as_of,
                                sessions=SESSIONS, period=as_of[:7])


# --- R4 · which events may reach a claim, derived rather than declared --------

def test_r4_the_claim_bearing_registry_is_derived_from_the_transitions():
    """A list of "kinds that consume same_claims" is a sentence that goes stale.

    So it is not trusted: every holder-affecting kind is probed with a state
    that has zero shares and one claim, and the set is read off what the frozen
    transition actually does with it.
    """
    assert_claim_bearing_registry_conforms()


def test_r4_a_claim_is_not_eligible_for_every_corporate_action():
    """The restriction is real: 5 of the 13 kinds, and structurally so."""
    from core.b0_corporate_actions import EVENT_KINDS

    assert set(CLAIM_BEARING_EVENT_KINDS) == set(holder_affecting_kinds())
    assert len(CLAIM_BEARING_EVENT_KINDS) == 5
    assert len(EVENT_KINDS) > len(CLAIM_BEARING_EVENT_KINDS)
    outside = [e.key for e in EVENT_KINDS
               if e.key not in CLAIM_BEARING_EVENT_KINDS]
    assert len(outside) == 8
    state = _state(claims=[_claim("AAAA", "1/5", "2018-01-05")])
    for kind in outside:
        ev = CorporateActionEvent("AAAA", kind, "2019-01-05", RECONSTRUCTIBLE,
                                  knowledge_ts="2010-01-01")
        assert not ca_economic_interest_applies(state, ev, as_of=AS_OF), kind


# --- R12 · the eight required cases ------------------------------------------

def test_c1_open_underlying_shares_no_claim_behaves_exactly_as_before():
    """B0.1's spell rule, untouched: interval in, interval out."""
    st = _state(shares={"AAAA": 1000},
                spells=[HoldingSpell("AAAA", "2018-01-05")])
    inside = _ev("AAAA", "2019-01-05")
    before = _ev("AAAA", "2017-09-09")           # earlier than the spell start

    assert ca_economic_interest_applies(st, inside, as_of=AS_OF)
    assert not ca_economic_interest_applies(st, before, as_of=AS_OF)
    assert st.underlying_exposure_applies("AAAA", "2019-01-05", AS_OF)
    assert not st.claim_interest_applies("AAAA", "2019-01-05")

    r = _run(st, [inside, before], AS_OF)
    assert list(r.applied_event_ids) == [inside.canonical_event_id()]


def test_c2_a_claim_with_no_open_spell_can_be_reached():
    """The B0.6 shape: every spell closed, one outstanding claim, event later."""
    st = _state(claims=[_claim("AAAA", "1/5", "2017-07-28")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])

    ev = _ev("AAAA", "2019-01-05")
    assert not st.underlying_exposure_applies("AAAA", "2019-01-05", AS_OF)
    assert st.claim_interest_applies("AAAA", "2019-01-05")
    assert ca_economic_interest_applies(st, ev, as_of=AS_OF)
    assert is_exposed(st, ev, as_of=AS_OF)

    r = _run(st, [ev], AS_OF)
    assert list(r.applied_event_ids) == [ev.canonical_event_id()]


def test_c2b_reaching_a_claim_opens_no_underlying_spell():
    """R2/R3. Applicability is combined; the spell ledger is not."""
    spells = (HoldingSpell("AAAA", "2017-05-02", "2017-08-01"),)
    st = _state(claims=[_claim("AAAA", "1/5", "2017-07-28")], spells=spells)
    r = _run(st, [_ev("AAAA", "2019-01-05")], AS_OF)

    assert r.state.holding_spells == spells, "no spell opened, closed or moved"
    assert all(not sp.open for sp in r.state.holding_spells)
    assert not r.state.underlying_exposure_applies("AAAA", "2019-01-05", AS_OF)


def test_c3_neither_shares_nor_claim_is_not_applicable():
    """§6.1.12's other half, preserved: zero exposure stays a no-op."""
    st = _state(spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    ev = _ev("AAAA", "2019-01-05")

    assert not ca_economic_interest_applies(st, ev, as_of=AS_OF)
    r = _run(st, [ev], AS_OF)
    assert r.applied_event_ids == ()
    assert ev.canonical_event_id() in r.skipped_unexposed


def test_c3b_an_unresolved_event_with_no_interest_still_does_not_abort():
    st = _state(spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    r = _run(st, [_ev("AAAA", "2019-01-05", kind="holder_side_reorganization_exit",
                      recon=NOT_RECONSTRUCTIBLE)], AS_OF)
    assert r.applied_event_ids == ()


def test_c4_shares_and_claim_are_counted_once_together_not_twice():
    """§6.1.7 A: `Q` is one quantity — pre_shares + same_claims — not two."""
    st = _state(shares={"AAAA": 1000},
                claims=[_claim("AAAA", 100, "2018-01-05")],
                spells=[HoldingSpell("AAAA", "2017-01-05")])
    ev = _ev("AAAA", "2019-01-05", stock_ratio=Fraction(1, 10))
    r = _run(st, [ev], AS_OF)

    assert list(r.applied_event_ids) == [ev.canonical_event_id()], "exactly once"
    created = [c for c in r.state.security_receivables
               if c.event_id == ev.canonical_event_id()]
    assert len(created) == 1, "one claim created, not one per domain"
    assert created[0].shares == Fraction(1100, 10), "Q = 1000 + 100, counted once"
    assert dict(r.state.shares) == {"AAAA": 1000}, "nothing credited early"


def test_c4b_a_second_evaluation_applies_nothing(monkeypatch):
    """I-CA-01 survives the new domain: the applied ledger still ends it."""
    st = _state(shares={"AAAA": 1000},
                claims=[_claim("AAAA", 100, "2018-01-05")],
                spells=[HoldingSpell("AAAA", "2017-01-05")])
    ev = _ev("AAAA", "2019-01-05")
    once = _run(st, [ev], AS_OF)
    twice = _run(once.state, [ev], AS_OF)

    assert twice.applied_event_ids == ()
    assert len(twice.state.security_receivables) == len(once.state.security_receivables)


def test_c5_claim_only_reconstructible_identity_change_transforms_exactly_once():
    """§6.1.7 C/D on a claim: old identity ends, successor claim is created."""
    st = _state(claims=[_claim("AAAA", 100, "2018-01-05")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    ev = _ev("AAAA", "2019-01-05", kind="holder_side_security_conversion",
             successor_security_id="BBBB", stock_ratio=Fraction(1, 2),
             credit_tradable_date="2020-12-28")

    r = _run(st, [ev], AS_OF)
    assert list(r.applied_event_ids) == [ev.canonical_event_id()]
    assert [c.security_id for c in r.state.security_receivables] == ["BBBB"], (
        "I-CA-07: the old identity ends here, no splice and no alias")
    assert r.state.security_receivables[0].shares == Fraction(50)
    assert r.state.security_receivables[0].source_security_id == "AAAA"

    again = _run(r.state, [ev], AS_OF)
    assert again.applied_event_ids == (), "exactly once, across evaluations"


def test_c6_claim_only_unresolved_reorganization_blocks_on_reconstruction():
    """R5/R6, generically. This is the B0.6 shape with fictional identifiers."""
    st = _state(claims=[_claim("AAAA", "1/5", "2017-07-28")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    ev = _ev("AAAA", "2019-01-05", kind="holder_side_reorganization_exit",
             recon=NOT_RECONSTRUCTIBLE)

    with pytest.raises(CorporateActionReconstructionBlock) as exc:
        _run(st, [ev], AS_OF)
    detail = exc.value.detail
    assert detail["security_id"] == "AAAA"
    assert detail["event_kind"] == "holder_side_reorganization_exit"
    assert detail["effective_date"] == "2019-01-05"
    assert detail["reconstructibility"] if "reconstructibility" in detail else True
    assert detail["exposure"]["tradable_shares"] == 0, (
        "the interest is the claim, and the record says so")
    assert detail["exposure"]["claims"] == ["1/5"]
    assert detail["as_of"] == AS_OF


def test_c7_a_non_claim_bearing_event_invents_no_applicability():
    """R4's boundary. A claim does not make every event reach the portfolio."""
    st = _state(claims=[_claim("AAAA", "1/5", "2017-07-28")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    for kind in ("cash_capital_increase", "treasury_cancellation",
                 "issuer_side_merger_share_issuance", "employee_bonus"):
        ev = CorporateActionEvent("AAAA", kind, "2019-01-05", RECONSTRUCTIBLE,
                                  knowledge_ts="2010-01-01")
        assert not ca_economic_interest_applies(st, ev, as_of=AS_OF), kind
        assert _run(st, [ev], AS_OF).applied_event_ids == ()


def test_c8_a_fractional_claim_stays_fractional():
    """§6.1.9 and R8. `int(0.2) == 0` is the whole 2017 mechanism, unchanged."""
    st = _state(claims=[_claim("AAAA", "1/5", "2017-07-28",
                               credit="2017-07-28")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])

    quiet = _run(st, [], AS_OF)
    assert dict(quiet.state.shares) == {}, "no forced credit of under one share"
    assert [c.shares for c in quiet.state.security_receivables] == [Fraction(1, 5)]
    assert quiet.state.cash == st.cash, "and no fabricated cash settlement"

    # a legitimate frozen transition may transform it, and only then
    r = _run(st, [_ev("AAAA", "2019-01-05", kind="capital_reduction",
                      share_multiplier=0.5)], AS_OF)
    assert [c.shares for c in r.state.security_receivables] == [Fraction(1, 10)], (
        "scaled by the same multiplier as the shares would have been")


# --- R3 · the claim domain has a time dimension too ---------------------------

def test_a_claim_is_not_reached_by_an_event_older_than_the_claim():
    """The B0.1 lesson, applied to the second domain.

    Without this the OR would reintroduce retroactive application on the claim
    side: an unapplied 2017 event would reach a claim created in 2018 and hand
    the portfolio an entitlement it never earned.
    """
    st = _state(claims=[_claim("AAAA", 100, "2018-01-05")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    older = _ev("AAAA", "2017-09-09")
    newer = _ev("AAAA", "2018-05-05")

    assert not st.claim_interest_applies("AAAA", "2017-09-09")
    assert st.claim_interest_applies("AAAA", "2018-05-05")
    r = _run(st, [older, newer], AS_OF)
    assert list(r.applied_event_ids) == [newer.canonical_event_id()]


def test_a_claim_that_cannot_date_itself_is_refused_at_construction():
    """No silent default. Either answer would be a decision nobody authorised."""
    with pytest.raises(CoreStateError, match="origin_effective_date"):
        SecurityReceivable(security_id="AAAA", shares=Fraction(1, 5),
                           credit_tradable_date="2030-01-01",
                           event_id="seed|x|2018-01-05")


def test_a_partially_released_remainder_keeps_its_original_origin():
    """R8: a remainder is the same claim, not a new one born today."""
    st = _state(claims=[_claim("AAAA", "7/2", "2018-01-05", credit="2018-02-01")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    r = _run(st, [], AS_OF)

    assert dict(r.state.shares) == {"AAAA": 3}, "the integral part is credited"
    rest = r.state.security_receivables
    assert [c.shares for c in rest] == [Fraction(1, 2)]
    assert rest[0].origin_effective_date == "2018-01-05", (
        "restamping it today would hide it from its own event's successors")


# --- R10 · the economic-interest delivery invariant ---------------------------

def test_r10_delivery_does_not_depend_on_a_market_row():
    """`deliver_ca_events` takes the portfolio and the ledger. Nothing else.

    Not a claim about behaviour under one fixture: there is no parameter through
    which a price row, a universe or an eligibility result could reach it.
    """
    st = _state(claims=[_claim("AAAA", "1/5", "2017-07-28")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    ev = _ev("AAAA", "2019-01-05", kind="holder_side_reorganization_exit",
             recon=NOT_RECONSTRUCTIBLE)
    delivered = deliver_ca_events({"AAAA": [ev]}, st, as_of=AS_OF)

    assert [e.canonical_event_id() for e in delivered] == [ev.canonical_event_id()]
    assert "AAAA" in economic_interest_securities(st)


def test_r10_an_event_not_yet_pit_available_is_not_delivered():
    st = _state(shares={"AAAA": 1000}, spells=[HoldingSpell("AAAA", "2017-01-05")])
    past, future = _ev("AAAA", "2019-01-05"), _ev("AAAA", "2019-09-09")
    delivered = deliver_ca_events({"AAAA": [past, future]}, st, as_of=AS_OF)

    assert [e.ex_or_effective_date for e in delivered] == ["2019-01-05"]
    with pytest.raises(CorporateActionTransitionError, match="PIT-available"):
        assert_ca_event_delivery_conforms([past, future], st, as_of=AS_OF)


def test_r10_one_event_reachable_through_two_interests_is_delivered_once():
    """A claim names its own security AND the source it came from."""
    st = _state(claims=[_claim("BBBB", 50, "2018-01-05", source="AAAA")],
                spells=[HoldingSpell("AAAA", "2017-05-02", "2017-08-01")])
    ev = _ev("AAAA", "2019-01-05")
    delivered = deliver_ca_events({"AAAA": [ev], "BBBB": []}, st, as_of=AS_OF)

    assert {"AAAA", "BBBB"} <= set(economic_interest_securities(st))
    assert len(delivered) == 1
    assert_ca_event_delivery_conforms(delivered, st, as_of=AS_OF)


def test_r10_a_duplicated_delivery_is_a_defect():
    st = _state(shares={"AAAA": 1000}, spells=[HoldingSpell("AAAA", "2017-01-05")])
    ev = _ev("AAAA", "2019-01-05")
    with pytest.raises(CorporateActionTransitionError, match="more than once"):
        assert_ca_event_delivery_conforms([ev, ev], st, as_of=AS_OF)


def test_r10_an_irrelevant_event_is_still_allowed_to_arrive():
    """Delivery scope is a floor, never a ceiling.

    §6.1.12: `NOT_RECONSTRUCTIBLE + zero exposure -> log as irrelevant ->
    continue`. An earlier draft of the gate rejected these and the existing
    route suite caught it in the same minute.
    """
    st = _state(shares={"AAAA": 1000}, spells=[HoldingSpell("AAAA", "2017-01-05")])
    stray = _ev("ZZZZ", "2019-01-05", recon=NOT_RECONSTRUCTIBLE)
    assert_ca_event_delivery_conforms([stray], st, as_of=AS_OF)


# --- R11 · the reconstruction gate wins before the mark gate ------------------

def test_r11_a_claim_only_reorganization_beats_the_price_gap_gate():
    """The whole point, at route level.

    Both guards would fire on this input. B0.6 reached the price-gap one first
    and reported an unexplained gap; §6.1 puts the corporate-action stage before
    `portfolio_mark`, so the answer has to be the reorganization.
    """
    from core.b0_pit_observability import PitPriceObservation, PriceObservabilityError
    from tests.test_b0_adapter_parity import AS_OF as R_AS_OF, SESSIONS as R_SESSIONS
    from tests.test_b0_route import canonical_input

    sid = "1101"
    claim_only = PortfolioState(
        R_AS_OF, 5_000_000.0, {},
        security_receivables=(SecurityReceivable(
            security_id=sid, shares=Fraction(1, 5),
            credit_tradable_date="2017-07-28",
            event_id="%s|capital_reduction|2017-07-28" % sid,
            origin_effective_date="2017-07-28"),),
        holding_spells=(HoldingSpell(sid, "2017-05-02", "2017-08-01"),))
    gapped = tuple(
        PitPriceObservation(
            as_of=R_AS_OF, stock_id=o.stock_id,
            price_observed_through=(None if o.stock_id == sid
                                    else o.price_observed_through),
            expected_sessions=tuple(s for s in R_SESSIONS if s <= R_AS_OF))
        for o in __import__("tests.test_b0_adapter_parity", fromlist=["x"]).observations())
    event = CorporateActionEvent(
        stock_id=sid, kind="holder_side_reorganization_exit",
        ex_or_effective_date="2020-06-15", reconstructibility=NOT_RECONSTRUCTIBLE,
        reason="successor, ratio and credit date are not established",
        knowledge_ts="2020-06-15")

    # the price-gap guard really would fire on this state
    with pytest.raises(PriceObservabilityError):
        run = canonical_input(portfolio=claim_only, price_observations=gapped,
                              corporate_action_events=(), exposures=())
        __import__("core.b0_route", fromlist=["x"]).run_decision(
            run, for_sealed_run=False)

    # but the corporate-action gate is upstream of it, and answers first
    with pytest.raises(CorporateActionError, match="cannot reconstruct"):
        run = canonical_input(portfolio=claim_only, price_observations=gapped,
                              corporate_action_events=(event,), exposures=())
        __import__("core.b0_route", fromlist=["x"]).run_decision(
            run, for_sealed_run=False)
