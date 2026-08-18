"""O-B · PIT price-observability semantics.

The claim under test is that B0 cannot express the rejected question. It is not
enough that the guard behaves well when called correctly — the signature must
make a look-ahead call fail, because the previous design's defect was that its
signature invited one.
"""

import pytest

from core.b0_pit_observability import (
    CURRENT,
    EXPLAINED_CORPORATE_ACTION,
    EXPLAINED_SUSPENSION,
    GAP_CLASSIFICATIONS,
    STALE_MARK_SESSION_TOLERANCE,
    UNEXPLAINED_GAP,
    LookAheadError,
    PitPriceObservation,
    PriceObservabilityError,
    assert_no_tolerance_policy,
    assert_no_unexplained_price_gap,
    assert_not_after,
    classify_price_gap,
    stale_mark_report,
)

SESSIONS = ("2019-04-25", "2019-04-26", "2019-04-29", "2019-04-30", "2019-05-01")
AS_OF = "2019-05-01"


def _obs(**kw):
    base = dict(as_of=AS_OF, stock_id="1234",
                price_observed_through="2019-05-01",
                expected_sessions=SESSIONS)
    base.update(kw)
    return PitPriceObservation(**base)


# --- the rejected design is not expressible ----------------------------------

def test_permanence_is_not_a_concept_here():
    """'Is this security gone forever?' has no PIT answer, so it has no field."""
    fields = set(PitPriceObservation.__dataclass_fields__)
    for banned in ("last_price_date", "final_trading_day", "delisting_date",
                   "permanently_gone"):
        assert banned not in fields
    import core.b0_pit_observability as pit
    assert not hasattr(pit, "last_price_date")


def test_a_price_date_after_as_of_is_rejected():
    with pytest.raises(LookAheadError, match="after as_of"):
        _obs(price_observed_through="2019-06-01")


def test_a_calendar_extending_past_as_of_is_rejected():
    """The trading calendar is future-knowable, which makes it the easiest way
    to smuggle look-ahead into an otherwise PIT computation."""
    with pytest.raises(LookAheadError, match="expected_sessions"):
        _obs(expected_sessions=SESSIONS + ("2019-05-02",))


def test_a_status_dated_after_as_of_is_rejected():
    with pytest.raises(LookAheadError, match="status_available_from"):
        _obs(known_status="suspended", status_available_from="2019-05-20")


def test_a_corporate_action_dated_after_as_of_is_rejected():
    with pytest.raises(LookAheadError, match="corporate_action_available_from"):
        _obs(price_observed_through="2019-04-25",
             explaining_corporate_action="merger",
             corporate_action_available_from="2019-05-15")


def test_an_explanation_without_an_availability_date_is_rejected():
    """O-E-1 is unanswerable without it, so the explanation is inadmissible."""
    with pytest.raises(PriceObservabilityError, match="O-E-1"):
        _obs(price_observed_through="2019-04-25",
             explaining_corporate_action="merger")


def test_assert_not_after_is_usable_standalone():
    assert_not_after("2019-05-01", a="2019-04-01", b=None)
    with pytest.raises(LookAheadError):
        assert_not_after("2019-05-01", a="2019-05-02")


def test_as_of_is_required():
    with pytest.raises(LookAheadError):
        assert_not_after("", a="2019-01-01")


# --- classification -----------------------------------------------------------

def test_a_currently_priced_position_is_current():
    v = classify_price_gap(_obs())
    assert v.classification == CURRENT
    assert v.sessions_stale == 0 and not v.stale_mark and v.markable


def test_staleness_counts_expected_sessions_not_calendar_days():
    """A weekend is not a missing session; the exchange calendar decides."""
    v = classify_price_gap(_obs(price_observed_through="2019-04-26"))
    assert v.sessions_stale == 3          # 04-29, 04-30, 05-01


def test_an_unexplained_gap_is_not_markable():
    v = classify_price_gap(_obs(price_observed_through="2019-04-25"))
    assert v.classification == UNEXPLAINED_GAP
    assert not v.markable and not v.stale_mark


def test_a_known_suspension_explains_the_gap_and_flags_a_stale_mark():
    v = classify_price_gap(_obs(price_observed_through="2019-04-25",
                                known_status="suspended",
                                status_available_from="2019-04-25"))
    assert v.classification == EXPLAINED_SUSPENSION
    assert v.stale_mark and v.markable and v.sessions_stale == 4


def test_O_E_1_a_status_available_only_on_the_first_missing_session_cannot_explain_it():
    """A suspension filed after the close still carries that day's date. Using
    it to account for that day's missing price is look-ahead with a valid date."""
    v = classify_price_gap(_obs(price_observed_through="2019-04-25",
                                known_status="suspended",
                                status_available_from="2019-04-26"))
    assert v.classification == UNEXPLAINED_GAP
    assert "O-E-1" in v.reason and not v.markable


def test_a_known_corporate_action_explains_the_gap():
    v = classify_price_gap(_obs(price_observed_through="2019-04-25",
                                explaining_corporate_action="merger",
                                corporate_action_available_from="2019-04-25"))
    assert v.classification == EXPLAINED_CORPORATE_ACTION
    assert v.stale_mark


def test_O_E_1_applies_to_corporate_actions_too():
    v = classify_price_gap(_obs(price_observed_through="2019-04-25",
                                explaining_corporate_action="merger",
                                corporate_action_available_from="2019-04-29"))
    assert v.classification == UNEXPLAINED_GAP and "O-E-1" in v.reason


def test_a_position_never_priced_is_unexplained_even_when_suspended():
    """No explanation supplies a number that was never observed."""
    v = classify_price_gap(_obs(price_observed_through=None,
                                known_status="suspended",
                                status_available_from="2019-04-26"))
    assert v.classification == UNEXPLAINED_GAP and not v.markable


def test_an_undated_non_listed_status_is_rejected():
    with pytest.raises(PriceObservabilityError, match="date it became known"):
        _obs(known_status="delisted")


def test_an_undefined_status_aborts():
    with pytest.raises(PriceObservabilityError, match="not defined"):
        _obs(known_status="probably_fine")


def test_listed_does_not_explain_a_gap():
    """The default status must not be an escape hatch."""
    v = classify_price_gap(_obs(price_observed_through="2019-04-25",
                                known_status="listed"))
    assert v.classification == UNEXPLAINED_GAP


# --- the guard ---------------------------------------------------------------

def test_the_guard_passes_a_clean_book():
    verdicts = assert_no_unexplained_price_gap(AS_OF, [_obs(), _obs(stock_id="2330")])
    assert [v.classification for v in verdicts] == [CURRENT, CURRENT]


def test_the_guard_aborts_on_an_unexplained_gap():
    with pytest.raises(PriceObservabilityError, match="1234"):
        assert_no_unexplained_price_gap(
            AS_OF, [_obs(price_observed_through="2019-04-25")])


def test_the_guard_message_names_the_failure_mode_it_prevents():
    with pytest.raises(PriceObservabilityError, match="missing price as zero"):
        assert_no_unexplained_price_gap(
            AS_OF, [_obs(price_observed_through="2019-04-25")])


def test_explained_gaps_survive_the_guard_and_are_reported():
    verdicts = assert_no_unexplained_price_gap(AS_OF, [
        _obs(),
        _obs(stock_id="2330", price_observed_through="2019-04-25",
             known_status="suspended", status_available_from="2019-04-25"),
    ])
    rep = stale_mark_report(verdicts)
    assert rep["positions"] == 2 and rep["stale_marks"] == 1
    assert rep["max_sessions_stale"] == 4
    assert rep["by_classification"][CURRENT] == 1
    assert rep["detail"][0]["stock_id"] == "2330"


def test_report_covers_every_classification_key():
    rep = stale_mark_report([classify_price_gap(_obs())])
    assert set(rep["by_classification"]) == set(GAP_CLASSIFICATIONS)


# --- no tolerance knob -------------------------------------------------------

def test_there_is_no_stale_session_tolerance():
    assert STALE_MARK_SESSION_TOLERANCE is None
    assert_no_tolerance_policy()


def test_a_tolerance_would_be_rejected_if_reintroduced(monkeypatch):
    import core.b0_pit_observability as pit
    monkeypatch.setattr(pit, "STALE_MARK_SESSION_TOLERANCE", 5)
    with pytest.raises(PriceObservabilityError, match="never tolerated"):
        pit.assert_no_tolerance_policy()


def test_one_missing_session_is_already_enough_to_abort():
    """No grace period: the first unexplained session fails."""
    v = classify_price_gap(_obs(price_observed_through="2019-04-30"))
    assert v.sessions_stale == 1 and v.classification == UNEXPLAINED_GAP
