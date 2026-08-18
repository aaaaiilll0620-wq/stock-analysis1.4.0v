"""O-G · listing spells: what breaks one, what does not, and what resets.

The case these tests are written against is real. `8102` is priced through
2005-08-30, absent for 4,474 sessions, and priced again from 2023-10-27 under
the same name — and the security master records `listed_from=2023-10-27` with no
delisting at all. Concatenated, those two runs make a 20-session ADV window
anchored in 2023 reach back into 2005.

No performance quantity appears here. Every session list is invented.
"""

import pytest

from core.b0_listing_spell import (
    PRICE_LOOKBACK_SESSIONS,
    SPELL_BRIDGING_SESSION_TOLERANCE,
    ListingSpell,
    ListingSpellError,
    assert_disappearance_not_explained_by_return,
    assert_no_bridging_tolerance,
    assert_price_lookbacks_reset,
    assert_spells_declared,
    assert_window_within_spell,
    derive_current_spell,
    lookback_is_available,
    price_lookback_or_na,
    spell_sessions,
)
from core.b0_pit_observability import LookAheadError

SESSIONS = tuple(f"2020-01-{d:02d}" for d in range(1, 22))
AS_OF = SESSIONS[-1]

NOTHING_EXPLAINS = lambda session: False        # noqa: E731
EVERYTHING_EXPLAINS = lambda session: True      # noqa: E731


def spell(start, opened_by="reappearance", as_of=AS_OF):
    return ListingSpell(stock_id="8102", start=start, opened_by=opened_by,
                        as_of=as_of)


# --- deriving the spell -------------------------------------------------------

def test_an_uninterrupted_series_is_one_spell_opened_by_first_observation():
    s = derive_current_spell(AS_OF, "8102", SESSIONS, SESSIONS, NOTHING_EXPLAINS)
    assert s.start == SESSIONS[0]
    assert s.opened_by == "first_observation"


def test_an_explained_gap_does_not_break_the_spell():
    """A suspension interrupts a listing; it does not end one."""
    priced = [x for x in SESSIONS if x not in SESSIONS[5:9]]
    s = derive_current_spell(AS_OF, "8102", SESSIONS, priced, EVERYTHING_EXPLAINS)
    assert s.start == SESSIONS[0]
    assert s.opened_by == "first_observation"


def test_an_unexplained_gap_then_reappearance_opens_a_new_spell():
    priced = [x for x in SESSIONS if x not in SESSIONS[5:9]]
    s = derive_current_spell(AS_OF, "8102", SESSIONS, priced, NOTHING_EXPLAINS)
    assert s.start == SESSIONS[9]
    assert s.opened_by == "reappearance"


def test_the_new_spell_starts_at_the_first_REOBSERVED_session():
    """Not at the disappearance, and not at any date derived from the return."""
    priced = [x for x in SESSIONS if x not in SESSIONS[3:12]]
    s = derive_current_spell(AS_OF, "8102", SESSIONS, priced, NOTHING_EXPLAINS)
    assert s.start == SESSIONS[12]
    assert s.start != SESSIONS[3]


def test_only_the_latest_break_survives_when_a_code_returns_twice():
    priced = [x for x in SESSIONS
              if x not in SESSIONS[3:6] and x not in SESSIONS[10:14]]
    s = derive_current_spell(AS_OF, "8102", SESSIONS, priced, NOTHING_EXPLAINS)
    assert s.start == SESSIONS[14]


def test_a_security_never_priced_through_as_of_has_no_spell():
    assert derive_current_spell(AS_OF, "8102", SESSIONS, (), NOTHING_EXPLAINS) is None


def test_a_gap_still_open_at_as_of_leaves_the_old_spell_in_force():
    """Standing at t there is no reappearance yet, so nothing has reopened."""
    priced = SESSIONS[:10]
    s = derive_current_spell(AS_OF, "8102", SESSIONS, priced, NOTHING_EXPLAINS)
    assert s.start == SESSIONS[0]
    assert s.opened_by == "first_observation"


# --- look-ahead ---------------------------------------------------------------

def test_a_session_after_as_of_cannot_enter_the_derivation():
    with pytest.raises(LookAheadError):
        derive_current_spell(SESSIONS[5], "8102", SESSIONS, SESSIONS[:6],
                             NOTHING_EXPLAINS)


def test_a_price_dated_after_as_of_cannot_enter_the_derivation():
    with pytest.raises(LookAheadError):
        derive_current_spell(SESSIONS[5], "8102", SESSIONS[:6], SESSIONS,
                             NOTHING_EXPLAINS)


def test_a_spell_cannot_start_after_its_own_as_of():
    with pytest.raises(LookAheadError):
        ListingSpell(stock_id="8102", start=SESSIONS[10],
                     opened_by="reappearance", as_of=SESSIONS[2])


def test_a_spell_has_no_end_field():
    """'When does this listing end' is not answerable standing inside it."""
    assert not hasattr(spell(SESSIONS[0]), "end")
    assert not hasattr(spell(SESSIONS[0]), "final_session")


# --- windows ------------------------------------------------------------------

def test_a_window_reaching_before_the_spell_start_aborts():
    with pytest.raises(ListingSpellError, match="before the current listing"):
        assert_window_within_spell(spell(SESSIONS[10]), SESSIONS[5:15])


def test_a_window_inside_the_spell_passes():
    assert_window_within_spell(spell(SESSIONS[10]), SESSIONS[10:15]) is None


def test_spell_sessions_are_bounded_at_both_ends():
    s = spell(SESSIONS[5], as_of=SESSIONS[15])
    got = spell_sessions(s, SESSIONS)
    assert got[0] == SESSIONS[5] and got[-1] == SESSIONS[15]


def test_lookback_availability_counts_only_the_current_spell():
    s = spell(SESSIONS[18])
    assert not lookback_is_available(s, SESSIONS, 20)
    assert lookback_is_available(spell(SESSIONS[0], "first_observation"),
                                 SESSIONS, 20)


# --- the reset ----------------------------------------------------------------

def test_a_short_new_spell_yields_NA_rather_than_a_number():
    assert price_lookback_or_na("adv20", spell(SESSIONS[18]), SESSIONS, 5e8) is None


def test_a_long_enough_spell_passes_the_value_through():
    s = spell(SESSIONS[0], "first_observation")
    assert price_lookback_or_na("adv20", s, SESSIONS, 5e8) == 5e8


def test_no_spell_at_all_is_NA_not_a_value():
    assert price_lookback_or_na("adv20", None, SESSIONS, 5e8) is None


def test_an_unregistered_lookback_key_aborts_rather_than_guessing():
    from core.b0_open_items import UnspecifiedCoreBehaviour

    with pytest.raises((UnspecifiedCoreBehaviour, KeyError)):
        price_lookback_or_na("turnover60", spell(SESSIONS[0]), SESSIONS, 1.0)


def test_the_route_guard_fires_on_a_bridged_window():
    with pytest.raises(ListingSpellError, match="listing-spell boundary"):
        assert_price_lookbacks_reset(
            AS_OF, {"8102": spell(SESSIONS[18])}, SESSIONS,
            {"adv20": {"8102": 5e8}, "sigma20d": {"8102": 0.02}})


def test_the_route_guard_ignores_a_short_first_observation_spell():
    """A calendar that does not reach back far enough is not a bridged window."""
    assert assert_price_lookbacks_reset(
        AS_OF, {"8102": spell(SESSIONS[18], "first_observation")}, SESSIONS,
        {"adv20": {"8102": 5e8}}) == []


def test_a_quantity_with_no_declared_window_is_not_policed_here():
    assert "marks" not in PRICE_LOOKBACK_SESSIONS
    assert assert_price_lookbacks_reset(
        AS_OF, {}, SESSIONS, {"marks": {"8102": 20.0}}) == []


# --- the source obligation ----------------------------------------------------

def test_a_window_quantity_with_no_declared_spell_aborts():
    with pytest.raises(ListingSpellError, match="no listing spell declared"):
        assert_spells_declared({}, {"adv20": {"8102": 5e8}})


def test_declaring_every_supplied_security_satisfies_the_obligation():
    assert assert_spells_declared(
        {"8102": spell(SESSIONS[0])}, {"adv20": {"8102": 5e8}}) is None


# --- O-G must not become a repair of O-F --------------------------------------

def test_a_reappearance_never_explains_the_original_disappearance():
    """The return is information from after the gap. It may not run backwards."""
    s = spell(SESSIONS[12])
    with pytest.raises(ListingSpellError, match="not before the spell opened"):
        assert_disappearance_not_explained_by_return(s, SESSIONS[14],
                                                     NOTHING_EXPLAINS)


def test_a_disappearance_before_the_new_spell_is_the_expected_ordering():
    s = spell(SESSIONS[12])
    assert assert_disappearance_not_explained_by_return(
        s, SESSIONS[3], NOTHING_EXPLAINS) is None


def test_a_first_observation_spell_has_no_earlier_disappearance_to_account_for():
    s = spell(SESSIONS[0], "first_observation")
    assert assert_disappearance_not_explained_by_return(
        s, SESSIONS[14], NOTHING_EXPLAINS) is None


# --- no tolerance -------------------------------------------------------------

def test_there_is_no_bridging_tolerance():
    assert SPELL_BRIDGING_SESSION_TOLERANCE is None
    assert assert_no_bridging_tolerance() is None


def test_opened_by_must_be_one_of_the_two_defined_values():
    with pytest.raises(ListingSpellError, match="not defined"):
        ListingSpell(stock_id="8102", start=SESSIONS[0],
                     opened_by="probably_fine", as_of=AS_OF)
