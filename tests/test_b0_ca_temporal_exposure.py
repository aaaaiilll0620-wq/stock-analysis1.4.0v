"""B0.1 · T1–T13 · corporate-action exposure has a time dimension.

The official Frozen B0 L2 run aborted in period 2 because the engine asked "is
this security in the portfolio now?" and then applied a 2012 event to a position
opened in 2014. Three different exposure notions existed in the canonical core —
one date-bounded, two membership-only — and the two membership-only ones were on
the production path.

The interval rule below is derived, not chosen. `INTRADAY_SEQUENCE` applies
corporate actions before the same day's execution and §6.1.7 A takes `Q` before
the conversion, so:

    H.start < E.effective_date <= H.end

Bought on the event date: the shares did not exist when `Q` was taken.
Sold on the event date: they still did.

Nothing here names security 1589 or its event id. A fix that recognised the
incident rather than the rule would be a fix that fails the next time.
"""

from fractions import Fraction

import pytest

from core.b0_corporate_actions import (
    NOT_RECONSTRUCTIBLE,
    RECONSTRUCTIBLE,
    CorporateActionError,
    CorporateActionEvent,
    CorporateActionReconstructionBlock,
    assert_exposure_reconstructible,
    assert_transition_applied,
    exposed_unreconstructible_events,
    is_exposed,
    redate,
    transition_portfolio,
)
from core.b0_state import HoldingSpell, PortfolioState

SESSIONS = tuple("%d-%02d-%02d" % (y, m, d)
                 for y in (2012, 2013, 2014, 2015, 2016, 2017)
                 for m in range(1, 13) for d in (1, 5, 9, 13, 15, 20, 28))


def _state(spells, shares, as_of, **kw):
    return PortfolioState(as_of=as_of, cash=1_000_000.0, shares=dict(shares),
                          holding_spells=tuple(spells), **kw)


def _ev(sid, date, kind="stock_dividend", recon=RECONSTRUCTIBLE, **kw):
    kw.setdefault("knowledge_ts", "2010-01-01")
    if recon == NOT_RECONSTRUCTIBLE:
        return CorporateActionEvent(sid, kind, date, recon,
                                    kw.pop("reason", "no official ratio"), **kw)
    return CorporateActionEvent(sid, kind, date, recon, **kw)


def _run(state, events, as_of):
    return transition_portfolio(redate(state, as_of), events, as_of=as_of,
                                sessions=SESSIONS, period=as_of[:7])


# --- T1 · the exact L2 defect, expressed as the general rule -----------------

def test_t1_an_event_predating_the_first_holding_is_not_applied():
    """The shape that ended the official L2 run, with no stock-specific escape."""
    st = _state([HoldingSpell("AAAA", "2014-08-01")], {"AAAA": 722}, "2014-08-29")
    ev = _ev("AAAA", "2012-09-13", recon=NOT_RECONSTRUCTIBLE)

    assert st.holding_spells[0].start > ev.ex_or_effective_date
    assert not st.exposure_applies("AAAA", "2012-09-13", "2014-08-29")
    assert not is_exposed(st, ev, as_of="2014-08-29")
    assert exposed_unreconstructible_events([ev], st, as_of="2014-08-29") == []

    r = _run(st, [ev], "2014-08-29")               # no abort
    assert dict(r.state.shares) == {"AAAA": 722}, "no back-applied transformation"
    assert r.state.security_receivables == (), "no claim from a pre-holding event"
    assert ev.canonical_event_id() in r.skipped_unexposed


def test_t1b_the_same_case_passes_the_mark_gate():
    st = _state([HoldingSpell("AAAA", "2014-08-01")], {"AAAA": 722}, "2014-08-29")
    ev = _ev("AAAA", "2012-09-13", recon=NOT_RECONSTRUCTIBLE)
    assert_transition_applied(st, [ev], as_of="2014-08-29")
    assert_exposure_reconstructible([ev], st, as_of="2014-08-29")


# --- T2 · a genuinely exposed unresolved event still fails loud --------------

def test_t2_holding_across_an_unresolved_event_still_aborts():
    """The repair must not become 'unresolved corporate actions never block'."""
    st = _state([HoldingSpell("AAAA", "2012-01-05")], {"AAAA": 1000}, "2014-08-29")
    ev = _ev("AAAA", "2012-09-13", recon=NOT_RECONSTRUCTIBLE)

    assert st.exposure_applies("AAAA", "2012-09-13", "2014-08-29")
    assert exposed_unreconstructible_events([ev], st, as_of="2014-08-29") == [ev]
    with pytest.raises(CorporateActionError, match="W-1/W-3"):
        assert_exposure_reconstructible([ev], st, as_of="2014-08-29")
    with pytest.raises(CorporateActionReconstructionBlock):
        _run(st, [ev], "2014-08-29")


# --- T3 · a reconstructible event inside the spell applies exactly once ------

def test_t3_a_reconstructible_event_during_holding_applies_once():
    st = _state([HoldingSpell("AAAA", "2014-01-05")], {"AAAA": 1000}, "2014-09-13")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-13")
    r = _run(st, [ev], "2014-09-13")
    assert dict(r.state.shares) == {"AAAA": 1100}
    r2 = _run(r.state, [ev], "2014-09-20")
    assert dict(r2.state.shares) == {"AAAA": 1100}, "applied twice"


# --- T4 · buying after the event earns nothing from it -----------------------

def test_t4_a_purchase_after_the_event_receives_no_entitlement():
    st = _state([HoldingSpell("AAAA", "2014-09-20")], {"AAAA": 500}, "2014-09-28")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-20")
    r = _run(st, [ev], "2014-09-28")
    assert dict(r.state.shares) == {"AAAA": 500}
    assert r.state.security_receivables == ()


# --- T5 · exit then re-entry: the event belongs to the first spell -----------

def test_t5_an_event_from_a_closed_spell_never_replays_onto_a_new_one():
    """The hazard a boundary-only test would miss.

    Testing `H.covers(event_date)` alone passes here — spell A really did cover
    2014 — and the event would then be applied to the 2017 position. The claim
    belongs to the exposure that earned it, so ONE spell must cover both the
    event and the moment of application.
    """
    spells = [HoldingSpell("AAAA", "2014-01-05", "2015-03-13"),
              HoldingSpell("AAAA", "2017-01-05")]
    st = _state(spells, {"AAAA": 800}, "2017-06-01")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-20")

    assert st.is_exposed_at("AAAA", "2014-09-13"), "spell A did cover it"
    assert not st.exposure_applies("AAAA", "2014-09-13", "2017-06-01")
    r = _run(st, [ev], "2017-06-01")
    assert dict(r.state.shares) == {"AAAA": 800}, "replayed onto the new spell"


def test_t5b_the_same_event_applies_while_its_own_spell_is_open():
    st = _state([HoldingSpell("AAAA", "2014-01-05")], {"AAAA": 800}, "2014-09-13")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-13")
    r = _run(st, [ev], "2014-09-13")
    assert dict(r.state.shares) == {"AAAA": 880}


# --- T6 · entitled, then sold before the credit date -------------------------

def test_t6_closing_the_spell_does_not_destroy_an_established_claim():
    """R5/T6: the claim lifecycle is untouched by the exposure repair.

    The entitlement forms at the boundary while B0 is still a holder. Selling the
    underlying afterwards ends the SPELL; it does not reach into the claim, which
    keeps running on its own frozen credit/tradable rules.
    """
    st = _state([HoldingSpell("AAAA", "2014-01-05")], {"AAAA": 1000}, "2014-09-13")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-28")
    r = _run(st, [ev], "2014-09-13")
    assert len(r.state.security_receivables) == 1
    assert r.state.security_receivables[0].shares == Fraction(100)

    # the underlying is fully sold the next session; the spell closes
    sold = r.state.with_underlying_exposure_recorded("2014-09-20")
    sold = PortfolioState(
        as_of="2014-09-20", cash=sold.cash, shares={},
        security_receivables=sold.security_receivables,
        applied_ca_event_ids=sold.applied_ca_event_ids,
        holding_spells=sold.holding_spells).with_underlying_exposure_recorded(
            "2014-09-20")

    assert [sp.end for sp in sold.holding_spells] == ["2014-09-20"]
    assert len(sold.security_receivables) == 1, "the claim survived the exit"
    assert "AAAA" in sold.held_securities, "still owned, so it still reaches NAV"

    r2 = _run(sold, [ev], "2014-09-28")
    assert dict(r2.state.shares) == {"AAAA": 100}, "credited on its own date"
    assert r2.state.security_receivables == ()


# --- T7 · bought after the entitlement but before the credit -----------------

def test_t7_a_buyer_after_the_boundary_receives_no_prior_entitlement():
    st = _state([HoldingSpell("AAAA", "2014-09-15")], {"AAAA": 400}, "2014-09-20")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-28")
    r = _run(st, [ev], "2014-09-28")
    assert dict(r.state.shares) == {"AAAA": 400}
    assert r.state.security_receivables == ()


# --- T8 · idempotence ---------------------------------------------------------

def test_t8_repeated_evaluation_has_the_economic_effect_exactly_once():
    st = _state([HoldingSpell("AAAA", "2014-01-05")], {"AAAA": 1000}, "2014-09-13")
    ev = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
             credit_tradable_date="2014-09-13")
    state = st
    for as_of in ("2014-09-13", "2014-09-15", "2014-09-20", "2014-09-28"):
        state = _run(state, [ev], as_of).state
    assert dict(state.shares) == {"AAAA": 1100}


# --- T9 · no future leakage ---------------------------------------------------

def test_t9_a_future_event_cannot_affect_an_earlier_state():
    st = _state([HoldingSpell("AAAA", "2014-01-05")], {"AAAA": 1000}, "2014-09-13")
    future = _ev("AAAA", "2015-01-05", stock_ratio=Fraction(1, 10),
                 credit_tradable_date="2015-01-09")
    r = _run(st, [future], "2014-09-13")
    assert dict(r.state.shares) == {"AAAA": 1000}
    assert r.state.security_receivables == ()
    assert_transition_applied(r.state, [future], as_of="2014-09-13")


# --- T10 · property: buy → event → sell → buy → event → sell -----------------

def test_t10_every_event_touches_exactly_the_spell_that_owned_it():
    spells = [HoldingSpell("AAAA", "2014-01-05", "2014-09-20"),
              HoldingSpell("AAAA", "2015-01-05", "2015-09-20")]
    st = _state(spells, {}, "2016-01-05")
    cases = {
        "2013-12-01": False,   # before spell A
        "2014-01-05": False,   # bought that day
        "2014-05-01": True,    # inside A
        "2014-09-20": True,    # sold that day
        "2014-11-01": False,   # between spells
        "2015-01-05": False,   # bought that day (B)
        "2015-05-01": True,    # inside B
        "2015-09-20": True,    # sold that day (B)
        "2015-12-01": False,   # after B
    }
    for date, expected in cases.items():
        assert st.is_exposed_at("AAAA", date) is expected, date


def test_t10b_application_is_scoped_to_the_still_open_spell():
    spells = [HoldingSpell("AAAA", "2014-01-05", "2014-09-20"),
              HoldingSpell("AAAA", "2015-01-05")]
    st = _state(spells, {"AAAA": 100}, "2015-06-01")
    assert st.exposure_applies("AAAA", "2015-05-01", "2015-06-01")
    assert not st.exposure_applies("AAAA", "2014-05-01", "2015-06-01")


# --- T11 · one predicate, so every path agrees -------------------------------

@pytest.mark.parametrize("start,end,event,expected", [
    ("2014-01-05", "", "2013-01-05", False),
    ("2014-01-05", "", "2014-01-05", False),
    ("2014-01-05", "", "2014-05-01", True),
    ("2014-01-05", "2014-09-20", "2014-09-20", True),
    ("2014-01-05", "2014-09-20", "2014-09-28", False),
])
def test_t11_the_gate_the_engine_and_the_mark_check_agree(start, end, event,
                                                          expected):
    """R3: three call sites, one predicate. Disagreement is how this began."""
    as_of = end or "2014-05-15"
    as_of = max(as_of, event)
    st = _state([HoldingSpell("AAAA", start, end)], {"AAAA": 100}, as_of)
    ev = _ev("AAAA", event, recon=NOT_RECONSTRUCTIBLE)

    gate = bool(exposed_unreconstructible_events([ev], st, as_of=as_of))
    engine = is_exposed(st, ev, as_of=as_of)
    predicate = st.exposure_applies("AAAA", event, as_of)
    assert gate == engine == predicate == expected


# --- T12 · membership alone must never be sufficient -------------------------

def test_t12_membership_without_date_exposure_is_not_exposure():
    """The exact negative boundary. This is the bug, stated as a test."""
    st = _state([HoldingSpell("AAAA", "2014-08-01")], {"AAAA": 722}, "2014-08-29")
    ev = _ev("AAAA", "2012-09-13", recon=NOT_RECONSTRUCTIBLE)

    assert "AAAA" in st.entitlement_securities, "membership is TRUE"
    assert "AAAA" in st.held_securities
    assert not st.exposure_applies("AAAA", "2012-09-13", "2014-08-29"), (
        "membership-only exposure must never be sufficient")
    assert not is_exposed(st, ev, as_of="2014-08-29")


def test_t12b_only_one_exposure_predicate_is_defined():
    """R4: a duplicate definition shadowed the first one for two versions."""
    import ast
    import io
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "core", "b0_corporate_actions.py")
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, (
        "duplicate top-level definitions in the normative CA module: %s. The "
        "later one silently shadows the earlier, so editing the wrong copy "
        "changes nothing." % duplicates)
    assert names.count("is_exposed") == 1


# --- T13 · a claim is not underlying exposure --------------------------------

def test_t13_a_claim_only_state_creates_no_underlying_exposure():
    """R1: event A's claim survives; event B sees no shareholder."""
    st = _state([HoldingSpell("AAAA", "2014-01-05")], {"AAAA": 1000}, "2014-09-13")
    ev_a = _ev("AAAA", "2014-09-13", stock_ratio=Fraction(1, 10),
               credit_tradable_date="2015-01-05")
    r = _run(st, [ev_a], "2014-09-13")
    assert len(r.state.security_receivables) == 1

    # underlying fully sold; only the claim remains
    claim_only = PortfolioState(
        as_of="2014-09-20", cash=r.state.cash, shares={},
        security_receivables=r.state.security_receivables,
        applied_ca_event_ids=r.state.applied_ca_event_ids,
        holding_spells=r.state.holding_spells).with_underlying_exposure_recorded(
            "2014-09-20")

    assert len(claim_only.security_receivables) == 1, "claim A survives"
    assert "AAAA" in claim_only.entitlement_securities, "membership is still TRUE"
    assert all(not sp.open for sp in claim_only.holding_spells), (
        "a surviving claim must not keep the underlying spell open")

    ev_b = _ev("AAAA", "2014-09-28", stock_ratio=Fraction(1, 5),
               credit_tradable_date="2014-09-28")
    assert not claim_only.exposure_applies("AAAA", "2014-09-28", "2014-09-28")
    r2 = _run(claim_only, [ev_b], "2014-09-28")
    assert dict(r2.state.shares) == {}, "event B found no shareholder"
    assert len(r2.state.security_receivables) == 1, "and did not disturb claim A"


def test_t13b_an_unresolved_event_during_a_claim_only_window_does_not_block():
    st = _state([HoldingSpell("AAAA", "2014-01-05", "2014-09-20")], {},
                "2014-09-28")
    ev = _ev("AAAA", "2014-09-28", recon=NOT_RECONSTRUCTIBLE)
    assert exposed_unreconstructible_events([ev], st, as_of="2014-09-28") == []
    assert_exposure_reconstructible([ev], st, as_of="2014-09-28")
