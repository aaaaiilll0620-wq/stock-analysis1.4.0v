# -*- coding: utf-8 -*-
"""B0.2 · R2/R3/R4 — active-vs-historical exposure projection.

The B0.1 diagnostic replay died at period 3 because a CURRENT caller declaration
was required to equal the COMPLETE historical spell ledger. These tests fix the
three concepts in place so the domains cannot silently merge again:

    holding_spells / exposure_spells()      complete history, open + closed
    active_exposure_projection(as_of)       what is current at as_of
    exposure_applies(sid, event, as_of)     the frozen CA predicate

R3 is a NON-change: the interval rule `H.start < E.effective_date <= H.end` and
the same-spell event/application requirement are re-asserted here, so a future
edit to the projection cannot quietly drag the economics along with it.
"""
from __future__ import annotations

import pytest

from core.b0_corporate_actions import (
    CorporateActionError, assert_caller_exposures_conform,
)
from core.b0_corporate_actions import Exposure
from core.b0_state import HoldingSpell, PortfolioState


def _state(spells, as_of="2014-09-30", shares=None):
    return PortfolioState(as_of=as_of, cash=0.0, shares=shares or {},
                          pending_exit={}, holding_spells=tuple(spells))


# --- the three concepts are distinct ------------------------------------------

def test_historical_ledger_keeps_closed_spells():
    closed = HoldingSpell("3032", "2014-08-01", "2014-09-01")
    open_ = HoldingSpell("2330", "2014-08-01")
    st = _state([closed, open_])
    assert set(st.exposure_spells()) == {closed, open_}


def test_active_projection_excludes_closed_spells():
    closed = HoldingSpell("3032", "2014-08-01", "2014-09-01")
    open_ = HoldingSpell("2330", "2014-08-01")
    st = _state([closed, open_], as_of="2014-09-30")
    assert st.active_exposure_projection("2014-09-30") == (open_,)


def test_active_projection_includes_a_spell_opened_on_as_of():
    """Current is has-begun-and-has-not-ended, not `covers()`.

    `covers` is the CA predicate and is asymmetric by derivation; a position
    bought today is not exposed to an event dated today but is certainly held.
    """
    sp = HoldingSpell("2330", "2014-09-30")
    st = _state([sp], as_of="2014-09-30")
    assert st.active_exposure_projection("2014-09-30") == (sp,)
    assert sp.covers("2014-09-30") is False


def test_active_projection_excludes_a_spell_not_yet_started():
    sp = HoldingSpell("2330", "2014-10-01")
    st = _state([sp], as_of="2014-09-30")
    assert st.active_exposure_projection("2014-09-30") == ()


# --- R4, the four required conformance cases ----------------------------------

def test_r4_historical_closed_spell_omitted_by_caller_passes():
    """The exact shape that ended B01DIAG-0121b3261805b826 at period 3."""
    st = _state([HoldingSpell("3032", "2014-08-01", "2014-09-01"),
                 HoldingSpell("3218", "2014-08-01", "2014-09-01"),
                 HoldingSpell("2330", "2014-08-01")], as_of="2014-09-30")
    declared = [Exposure(stock_id="2330", held_from="2014-08-01",
                         held_until="2014-09-30")]
    assert_caller_exposures_conform(declared, st, as_of="2014-09-30")


def test_r4_active_spell_omitted_by_caller_fails():
    st = _state([HoldingSpell("2330", "2014-08-01"),
                 HoldingSpell("2317", "2014-08-01")], as_of="2014-09-30")
    declared = [Exposure(stock_id="2330", held_from="2014-08-01",
                         held_until="2014-09-30")]
    with pytest.raises(CorporateActionError) as exc:
        assert_caller_exposures_conform(declared, st, as_of="2014-09-30")
    assert "2317" in str(exc.value)


def test_r4_closed_spell_declared_as_current_fails():
    st = _state([HoldingSpell("3032", "2014-08-01", "2014-09-01"),
                 HoldingSpell("2330", "2014-08-01")], as_of="2014-09-30")
    declared = [Exposure(stock_id="2330", held_from="2014-08-01",
                         held_until="2014-09-30"),
                Exposure(stock_id="3032", held_from="2014-08-01",
                         held_until="2014-09-30")]
    with pytest.raises(CorporateActionError) as exc:
        assert_caller_exposures_conform(declared, st, as_of="2014-09-30")
    assert "3032" in str(exc.value)


def test_r4_exit_then_reentry_caller_declares_the_active_spell_only():
    """Closed A + active re-entry B: declare B only -> PASS, ledger keeps A+B."""
    a = HoldingSpell("3032", "2014-08-01", "2014-09-01")
    b = HoldingSpell("3032", "2014-11-03")
    st = _state([a, b], as_of="2014-11-28")
    declared = [Exposure(stock_id="3032", held_from="2014-11-03",
                         held_until="2014-11-28")]
    assert_caller_exposures_conform(declared, st, as_of="2014-11-28")
    assert set(st.exposure_spells()) == {a, b}
    assert st.active_exposure_projection("2014-11-28") == (b,)


def test_r4_exit_then_reentry_declaring_the_closed_spell_too_fails():
    a = HoldingSpell("3032", "2014-08-01", "2014-09-01")
    b = HoldingSpell("3032", "2014-11-03")
    st = _state([a, b], as_of="2014-11-28")
    declared = [Exposure(stock_id="3032", held_from="2014-08-01",
                         held_until="2014-09-01"),
                Exposure(stock_id="3032", held_from="2014-11-03",
                         held_until="2014-11-28")]
    with pytest.raises(CorporateActionError):
        assert_caller_exposures_conform(declared, st, as_of="2014-11-28")


# --- R3, the economics that must NOT have moved -------------------------------

def test_r3_interval_rule_is_unchanged():
    """`H.start < E.effective_date <= H.end`, both boundaries."""
    sp = HoldingSpell("3032", "2014-08-01", "2014-09-01")
    assert sp.covers("2014-08-01") is False      # bought on the event date
    assert sp.covers("2014-09-01") is True       # sold on the event date
    assert sp.covers("2014-08-15") is True
    assert sp.covers("2014-09-02") is False


def test_r3_closed_spells_remain_available_for_historical_adjudication():
    st = _state([HoldingSpell("3032", "2014-08-01", "2014-09-01")],
                as_of="2014-09-30")
    # the event fell inside the closed spell, and application is asked as of a
    # moment that same spell also covers
    assert st.exposure_applies("3032", "2014-08-15", "2014-09-01") is True
    # ...but the spell is not a CURRENT exposure
    assert st.active_exposure_projection("2014-09-30") == ()


def test_r3_same_spell_requirement_blocks_replay_onto_a_reentry_position():
    """An event earned by spell A must never apply to the later spell B."""
    st = _state([HoldingSpell("3032", "2014-08-01", "2014-09-01"),
                 HoldingSpell("3032", "2014-11-03")], as_of="2014-11-28")
    # event dated inside A, application asked while only B is open
    assert st.exposure_applies("3032", "2014-08-15", "2014-11-28") is False
    # and B's own window still works
    assert st.exposure_applies("3032", "2014-11-10", "2014-11-28") is True


def test_r3_caller_may_still_decline_to_declare_anything():
    """An empty declaration stays a no-op, as B0.1 had it."""
    st = _state([HoldingSpell("2330", "2014-08-01")], as_of="2014-09-30")
    assert_caller_exposures_conform([], st, as_of="2014-09-30")
    assert_caller_exposures_conform(None, st, as_of="2014-09-30")
