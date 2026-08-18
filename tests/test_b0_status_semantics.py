"""O-F · event semantics, the exposure-scoped abort, and the S-3b criterion.

Three rulings are tested here, and each of them overturned something this repo
previously did:

  ruling 2  the abort is scoped to EXPOSURE. The route used to hand the guard
            every observation it had, so an incomplete status source looked like
            a route failure.
  ruling 4  a row in the vendor suspension export is not automatically a
            suspension. 1,135 of the 1,148 capital-reduction rows have a price
            on every session of their own declared window — they describe a
            book-closure period, and reading them as `suspended` puts a standing
            explanation over a window where a real gap could hide.
  ruling 5  S-3b is enforcement, not source completeness. 293 of 352 corpus
            terminations have no PIT-available explanation and no re-export will
            change that, so the criterion is what the route DOES.

No performance quantity appears here.
"""

import pytest

from core.b0_market_state import (
    BOOK_CLOSURE,
    LISTING_TERMINATION,
    STATUS_DELISTED,
    STATUS_SUSPENDED,
    TRADING_SUSPENSION,
    UNKNOWN_EVENT_SEMANTICS,
    MarketStateError,
    assert_not_promoted_to_suspended,
    classify_event_semantics,
    status_for_event,
)
from core.b0_pit_observability import (
    EXPLAINED_SUSPENSION,
    UNEXPLAINED_GAP,
    PitPriceObservation,
    PriceObservabilityError,
    assert_no_unexplained_gap_in_holdings,
    classify_price_gap,
    universe_gap_diagnostic,
)

SESSIONS = ("2020-06-24", "2020-06-25", "2020-06-26", "2020-06-29")
AS_OF = SESSIONS[-1]


def observation(sid, observed_through=SESSIONS[0], status="listed",
                available_from=None):
    return PitPriceObservation(
        as_of=AS_OF, stock_id=sid, price_observed_through=observed_through,
        expected_sessions=SESSIONS, known_status=status,
        status_available_from=available_from)


# --- ruling 4 · the export is not a suspension table --------------------------

@pytest.mark.parametrize("reason,expected", [
    ("減資", BOOK_CLOSURE),
    ("現金減資", BOOK_CLOSURE),
    ("分割減資", BOOK_CLOSURE),
    ("面額變更，10元換1元", BOOK_CLOSURE),
    ("合併下市", LISTING_TERMINATION),
    ("併入控股公司下市", LISTING_TERMINATION),
    ("重大訊息之查證: 某某公司將成為子公司", TRADING_SUSPENSION),
    ("違規財報", TRADING_SUSPENSION),
    ("盤中暫停", TRADING_SUSPENSION),
    ("執行董事離世", UNKNOWN_EVENT_SEMANTICS),
    (".", UNKNOWN_EVENT_SEMANTICS),
    ("", UNKNOWN_EVENT_SEMANTICS),
])
def test_the_reason_decides_the_semantics(reason, expected):
    assert classify_event_semantics(reason) == expected


def test_a_capital_reduction_row_produces_no_status_at_all():
    """Measured: 1,135 of 1,148 such windows are fully priced. Nothing to explain."""
    assert status_for_event("現金減資") is None


def test_an_uninterpretable_row_fails_closed_rather_than_becoming_suspended():
    assert status_for_event("執行董事離世") is None


def test_a_halt_becomes_suspended_and_a_termination_becomes_delisted():
    assert status_for_event("違規財報") == STATUS_SUSPENDED
    assert status_for_event("合併下市") == STATUS_DELISTED


def test_termination_wins_over_book_closure_when_a_row_says_both():
    assert classify_event_semantics("減資後合併下市") == LISTING_TERMINATION


def test_promoting_a_book_closure_row_to_suspended_aborts():
    with pytest.raises(MarketStateError, match="fail closed"):
        assert_not_promoted_to_suspended("現金減資", STATUS_SUSPENDED)


def test_promoting_an_unknown_row_to_suspended_aborts():
    with pytest.raises(MarketStateError, match="fail closed"):
        assert_not_promoted_to_suspended("執行董事離世", STATUS_SUSPENDED)


def test_the_correct_assignment_passes():
    assert assert_not_promoted_to_suspended("違規財報", STATUS_SUSPENDED) is None
    assert assert_not_promoted_to_suspended("現金減資", None) is None


def test_every_semantics_has_an_explicit_status_mapping():
    from core.b0_market_state import EVENT_SEMANTICS, STATUS_BY_EVENT_SEMANTICS

    assert set(EVENT_SEMANTICS) == set(STATUS_BY_EVENT_SEMANTICS)


# --- ruling 2 · the abort is scoped to exposure -------------------------------

def test_an_unexplained_gap_in_a_held_name_aborts():
    obs = observation("1107")
    with pytest.raises(PriceObservabilityError, match="price gap"):
        assert_no_unexplained_gap_in_holdings(AS_OF, [obs], {"1107": 1000})


def test_the_same_gap_in_a_name_b0_does_not_hold_does_not_abort():
    obs = observation("1107")
    assert assert_no_unexplained_gap_in_holdings(AS_OF, [obs], {}) == []


def test_only_held_names_come_back_as_verdicts():
    """The mark stage needs a verdict per holding and has no use for the rest."""
    held = observation("1101", observed_through=AS_OF)
    other = observation("1107")
    verdicts = assert_no_unexplained_gap_in_holdings(
        AS_OF, [held, other], {"1101": 500})
    assert [v.stock_id for v in verdicts] == ["1101"]


def test_a_pit_available_status_explains_the_gap_for_a_held_name():
    obs = observation("2496", status="suspended",
                      available_from=SESSIONS[0])
    verdicts = assert_no_unexplained_gap_in_holdings(AS_OF, [obs], {"2496": 1})
    assert verdicts[0].classification == EXPLAINED_SUSPENSION
    assert verdicts[0].stale_mark is True


def test_o_e_1_stays_strict_a_same_day_status_still_does_not_explain():
    """The status is dated the first missing session itself, so it is not before it."""
    obs = observation("2496", status="suspended", available_from=SESSIONS[1])
    verdict = classify_price_gap(obs)
    assert verdict.classification == UNEXPLAINED_GAP
    assert "O-E-1" in verdict.reason
    with pytest.raises(PriceObservabilityError):
        assert_no_unexplained_gap_in_holdings(AS_OF, [obs], {"2496": 1})


# --- the diagnostic that O-F closure permits to be non-zero -------------------

def test_the_universe_diagnostic_counts_without_aborting():
    report = universe_gap_diagnostic(
        AS_OF, [observation("1107"), observation("1101", observed_through=AS_OF)],
        holdings={})
    assert report["unexplained_total"] == 1
    assert report["unexplained_held"] == 0
    assert report["aborts"] is False
    assert report["enforced"] is False


def test_the_diagnostic_reports_when_an_unexplained_name_IS_held():
    report = universe_gap_diagnostic(AS_OF, [observation("1107")],
                                     holdings={"1107": 1000})
    assert report["unexplained_held"] == 1
    assert report["aborts"] is True


# --- ruling 5 · S-3b is enforcement -------------------------------------------

def test_s3b_is_registered_as_a_blocking_requirement_with_a_real_verifier():
    from core.b0_frozen_spec import BLOCKING_DATA_REQUIREMENTS

    req = next(r for r in BLOCKING_DATA_REQUIREMENTS
               if r.key == "security_status_guard_enforcement")
    assert req.blocks == ("S-3b",)
    assert not hasattr(req, "satisfied")


def test_s3b_proves_all_four_properties_on_the_real_fixture():
    from core.b0_frozen_spec import BLOCKING_DATA_REQUIREMENTS, S3B_ENFORCEMENT_PROPERTIES

    req = next(r for r in BLOCKING_DATA_REQUIREMENTS
               if r.key == "security_status_guard_enforcement")
    result = req.verify()
    assert result.satisfied, result.detail
    assert set(result.diagnostics["properties_proved"]) == set(
        S3B_ENFORCEMENT_PROPERTIES)


def test_s3b_fails_when_the_held_case_does_not_abort():
    """A fixture whose 'unexplained' case is actually explained proves nothing."""
    from core.b0_frozen_spec import verify_status_guard_enforcement

    rows = [{"property": "held_unexplained_gap_aborts", "stock_id": "1107",
             "as_of": AS_OF, "price_observed_through": AS_OF,
             "expected_sessions": ";".join(SESSIONS), "known_status": "listed",
             "status_available_from": "", "held": "1",
             "expected_outcome": "ABORT"}]
    result = verify_status_guard_enforcement(rows)
    assert not result.satisfied
    assert "did not abort" in result.detail


def test_s3b_fails_when_the_fixture_is_absent():
    from core.b0_frozen_spec import verify_status_guard_enforcement

    assert not verify_status_guard_enforcement([]).satisfied


def test_s3b_requires_the_route_to_reach_the_exposure_scoped_guard():
    from core.b0_frozen_spec import (
        S3B_FORBIDDEN_DIRECT_GUARD, S3B_GUARD_SYMBOL, _verify_routes_invoke_guard,
    )

    problems, diag = _verify_routes_invoke_guard()
    assert problems == []
    assert diag["core.b0_route"]["calls_exposure_scoped_guard"]
    assert not any(d["calls_unscoped_guard"] for d in diag.values())
    assert S3B_GUARD_SYMBOL != S3B_FORBIDDEN_DIRECT_GUARD


def test_s3b_closure_does_not_require_zero_unexplained_gaps():
    """The whole point of the ruling: the source is incomplete and stays so."""
    from core.b0_frozen_spec import BLOCKING_DATA_REQUIREMENTS

    req = next(r for r in BLOCKING_DATA_REQUIREMENTS
               if r.key == "security_status_guard_enforcement")
    assert "enforcement" in req.reason
    assert req.verify().satisfied


# --- the snapshot delisting fields stay audit-only ---------------------------

def test_no_route_module_can_reach_the_current_snapshot_delisting_fields():
    from core.b0_invariants import (
        AUDIT_ONLY_MODULES, AUDIT_ONLY_SYMBOLS, B0_ENTRY_MODULES, find_violations,
    )

    assert find_violations(B0_ENTRY_MODULES, AUDIT_ONLY_MODULES,
                           AUDIT_ONLY_SYMBOLS) == []
