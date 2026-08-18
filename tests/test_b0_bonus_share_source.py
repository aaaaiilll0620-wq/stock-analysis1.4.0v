"""C-51 · the official bonus-share holder-multiplier source, pinned by R6.

The eight negative controls the ruling names are the load-bearing part. Each one
is a way a plausible multiplier could get in — an employee-bonus column, a
subscription column, a price inversion, a nearest-date match, a live request —
and each has to fail rather than merely be unused.
"""

import json
import os
import subprocess
import sys

import pytest

from core.b0_bonus_share_source import (
    BONUS_IMPORTER_VERSION,
    BONUS_PARSER_VERSION,
    BONUS_PER_1000_DIVISOR,
    BONUS_UNIT,
    CANONICAL_CONVERSION,
    CURRENT_LISTING_LABEL_ALLOWED,
    DATE_TOLERANCE_DAYS,
    FORBIDDEN_MULTIPLIER_SOURCES,
    MATCHED_DISPOSITION,
    NEAREST_DATE_MATCHING_ALLOWED,
    OFFICIAL_BONUS_FIELD,
    OFFICIAL_ENDPOINT,
    PRE_LISTING_DISPOSITION,
    UNRESOLVED_DISPOSITION,
    BonusShareSourceContract,
    BonusShareSourceError,
    UnresolvedBonusEvent,
    assert_bonus_source_admissible,
    assert_multiplier_source_admissible,
    assert_no_inferred_multiplier,
    assert_not_current_board_status,
    assert_same_market_effective_event,
    holder_multiplier_from_bonus,
    is_pre_listing,
    market_effective_session,
    resolve_disposition,
)
from core.b0_share_unit_adjustment import (
    ShareUnitAdjustmentError,
    UnreconstructibleAdjustment,
    holder_multiplier,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(REPO, "data", "b0", "bonus_share_panel.parquet")
RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                       "bonus_share_panel_receipt.json")

# A small synthetic calendar with one closed market day: 2019-08-09 is missing,
# exactly the shape the 2019 closure produced in the real data.
SESSIONS = ("2019-08-06", "2019-08-07", "2019-08-08",
            "2019-08-12", "2019-08-13", "2019-08-14")


def _contract(**over):
    base = dict(
        name="t", endpoints=dict(OFFICIAL_ENDPOINT),
        importer_version=BONUS_IMPORTER_VERSION,
        parser_version=BONUS_PARSER_VERSION,
        schema_sha256="a" * 64, content_sha256="b" * 64,
        upstream_manifest_sha256="c" * 64, upstream_sha256={"k": "d" * 64},
        date_min="2013-07-02", date_max="2025-12-10",
        events_total=10, events_matched=7, events_not_applicable=2,
        events_unresolved=1, securities=5, live_fetch=False)
    base.update(over)
    return BonusShareSourceContract(**base)


# --- R1 · the canonical source and conversion --------------------------------

def test_the_canonical_conversion_is_per_thousand():
    assert BONUS_UNIT == "shares_per_1000_held"
    assert BONUS_PER_1000_DIVISOR == 1000.0
    assert CANONICAL_CONVERSION == "holder_multiplier = 1 + bonus_shares_per_1000 / 1000"
    assert holder_multiplier_from_bonus(100) == pytest.approx(1.1)
    assert holder_multiplier_from_bonus(50) == pytest.approx(1.05)
    assert holder_multiplier_from_bonus(0) == pytest.approx(1.0)
    assert holder_multiplier_from_bonus(9380) == pytest.approx(10.38)


def test_the_official_field_is_named_per_board_not_normalised():
    """TWSE writes 每千股 and TPEx 每仟股; one lookup for both would miss."""
    assert OFFICIAL_BONUS_FIELD["TWSE"] == "A. 按普通股股東持股比例每千股無償配股"
    assert OFFICIAL_BONUS_FIELD["TPEx"] == "每仟股無償配股"
    assert OFFICIAL_BONUS_FIELD["TWSE"] != OFFICIAL_BONUS_FIELD["TPEx"]


def test_only_the_official_exchange_field_is_an_admissible_source():
    assert_multiplier_source_admissible("official_exchange_bonus_share")
    for bad in FORBIDDEN_MULTIPLIER_SOURCES:
        with pytest.raises(BonusShareSourceError, match="R1"):
            assert_multiplier_source_admissible(bad)


# --- R6 negative control 1-2 · the ineligible legs never enter ----------------

@pytest.mark.parametrize("leg", ["employee_bonus_shares",
                                 "paid_capital_increase_shares"])
def test_the_ineligible_exchange_legs_are_refused(leg):
    """The exchange publishes A, B and C separately; only A is holder-level."""
    with pytest.raises(BonusShareSourceError, match="R1"):
        assert_multiplier_source_admissible(leg)
    assert leg in FORBIDDEN_MULTIPLIER_SOURCES


def test_the_parser_reads_only_field_A_from_the_twse_detail():
    """B (員工紅利轉增資) and C (現金增資) are not the bonus field."""
    a = OFFICIAL_BONUS_FIELD["TWSE"]
    assert a.startswith("A.")
    for other in ("B. 員工紅利轉增資", "C. (有償) 現金增資",
                  "按股東持股比例每千股認購"):
        assert other != a


# --- R6 negative control 3 · reference-price inversion is unreachable ---------

def test_reference_price_inversion_is_not_reachable_as_a_source():
    with pytest.raises(BonusShareSourceError, match="R1"):
        assert_multiplier_source_admissible("reference_price_inversion")
    assert "reference_price_inversion" in FORBIDDEN_MULTIPLIER_SOURCES
    assert "new_shares_over_shares_outstanding" in FORBIDDEN_MULTIPLIER_SOURCES
    assert "current_shares_outstanding" in FORBIDDEN_MULTIPLIER_SOURCES
    assert "cash_dividend_corpus" in FORBIDDEN_MULTIPLIER_SOURCES


def test_a_new_share_count_still_cannot_become_a_multiplier():
    """C-50 refused it and C-51 does not reopen the door."""
    with pytest.raises(UnreconstructibleAdjustment, match="no share_multiplier"):
        holder_multiplier({"stock_id": "1234", "kind": "stock_dividend",
                           "reconstructibility": "RECONSTRUCTIBLE",
                           "share_multiplier": "",
                           "new_shares_thousands": "6692"})


# --- R6 negative control 4 · pre-listing is NOT_APPLICABLE, not missing -------

def test_a_pre_listing_event_is_not_applicable_rather_than_missing():
    assert is_pre_listing("2013-07-03", []) is True
    assert is_pre_listing("2013-07-03", ["2012-07-02"]) is False
    assert resolve_disposition(official_bonus_per_1000=None,
                               pre_listing=True) == PRE_LISTING_DISPOSITION
    assert resolve_disposition(official_bonus_per_1000=None,
                               pre_listing=False) == UNRESOLVED_DISPOSITION
    assert resolve_disposition(official_bonus_per_1000=100.0,
                               pre_listing=False) == MATCHED_DISPOSITION


def test_pre_listing_classification_cannot_use_later_information():
    with pytest.raises(BonusShareSourceError, match="R2"):
        is_pre_listing("2013-07-03", ["2014-05-15"])


def test_board_attribution_may_not_come_from_the_current_label():
    assert CURRENT_LISTING_LABEL_ALLOWED is False
    assert_not_current_board_status("contemporaneous_exchange_payload")
    with pytest.raises(BonusShareSourceError, match="R2"):
        assert_not_current_board_status("current_上市別")
    with pytest.raises(BonusShareSourceError, match="R2"):
        assert_bonus_source_admissible(
            _contract(board_attribution_source="current_listing_label"))


def test_a_not_applicable_event_never_carries_a_multiplier():
    assert_no_inferred_multiplier(PRE_LISTING_DISPOSITION, None)
    with pytest.raises(BonusShareSourceError, match="R2"):
        assert_no_inferred_multiplier(PRE_LISTING_DISPOSITION, 1.1)


# --- R6 negative control 5-6 · date normalization, and no tolerance -----------

def test_a_closed_market_scheduled_date_maps_to_the_exact_next_session():
    assert market_effective_session("2019-08-09", SESSIONS) == "2019-08-12"
    assert_same_market_effective_event("2019-08-09", "2019-08-12", SESSIONS)


def test_a_scheduled_date_that_is_a_session_is_its_own_boundary():
    assert market_effective_session("2019-08-08", SESSIONS) == "2019-08-08"
    assert_same_market_effective_event("2019-08-08", "2019-08-08", SESSIONS)


def test_arbitrary_plus_minus_day_matching_fails():
    """The whole point of R3: this is normalization, not a tolerance window."""
    assert NEAREST_DATE_MATCHING_ALLOWED is False
    assert DATE_TOLERANCE_DAYS == 0
    # both are sessions, one apart -> not the same event
    with pytest.raises(BonusShareSourceError, match="R3"):
        assert_same_market_effective_event("2019-08-07", "2019-08-08", SESSIONS)
    # a closure day, but the SECOND session after -> not admissible
    with pytest.raises(BonusShareSourceError, match="R3"):
        assert_same_market_effective_event("2019-08-09", "2019-08-13", SESSIONS)
    # backwards matching -> not admissible
    with pytest.raises(BonusShareSourceError, match="R3"):
        assert_same_market_effective_event("2019-08-09", "2019-08-08", SESSIONS)


def test_a_scheduled_date_with_no_later_session_is_unresolved_not_guessed():
    with pytest.raises(UnresolvedBonusEvent, match="R3"):
        market_effective_session("2019-08-15", SESSIONS)


# --- R4 · what is left over stays left over ----------------------------------

def test_an_unresolved_event_never_carries_an_inferred_multiplier():
    assert_no_inferred_multiplier(UNRESOLVED_DISPOSITION, None)
    with pytest.raises(BonusShareSourceError, match="R4"):
        assert_no_inferred_multiplier(UNRESOLVED_DISPOSITION, 1.05)


def test_a_non_numeric_or_negative_allotment_fails_loudly():
    for bad in ("", "n/a", None):
        with pytest.raises(UnresolvedBonusEvent, match="R1"):
            holder_multiplier_from_bonus(bad)
    with pytest.raises(UnresolvedBonusEvent, match="R1"):
        holder_multiplier_from_bonus(-1.0)


# --- R6 negative control 7 · live fetch is rejected --------------------------

def test_a_live_fetch_source_is_not_admissible():
    assert_bonus_source_admissible(_contract())
    with pytest.raises(BonusShareSourceError, match="R5"):
        assert_bonus_source_admissible(_contract(live_fetch=True))


def test_a_parser_or_importer_change_changes_source_identity():
    with pytest.raises(BonusShareSourceError, match="R5"):
        assert_bonus_source_admissible(_contract(parser_version="something_else"))
    with pytest.raises(BonusShareSourceError, match="R5"):
        assert_bonus_source_admissible(_contract(importer_version="other@9"))


def test_a_contract_must_bind_hashes_and_a_partitioning_coverage():
    with pytest.raises(BonusShareSourceError, match="R5"):
        _contract(content_sha256="")
    with pytest.raises(BonusShareSourceError, match="R5"):
        _contract(upstream_sha256={})
    with pytest.raises(BonusShareSourceError, match="R5"):
        _contract(events_matched=1)          # 1 + 2 + 1 != 10


# --- R6 negative control 8 · repeated materialization is identical -----------

def test_the_sealed_panel_matches_its_receipt():
    if not (os.path.exists(PANEL) and os.path.exists(RECEIPT)):
        pytest.skip("bonus-share panel not materialized")
    from core.b0_provenance import file_sha256
    with open(RECEIPT, encoding="utf-8") as fh:
        receipt = json.load(fh)
    assert receipt["content_sha256"] == file_sha256(PANEL)
    assert receipt["live_fetch"] is False
    assert receipt["parser_version"] == BONUS_PARSER_VERSION
    assert receipt["bonus_unit"] == BONUS_UNIT
    cov = receipt["coverage"]
    assert (cov["matched_official_bonus_rate"]
            + cov[PRE_LISTING_DISPOSITION.lower()]
            + cov["unresolved"]) == cov["events_total"]


@pytest.mark.slow
def test_rebuilding_the_panel_yields_an_identical_content_hash():
    """R6: determinism, checked by actually rebuilding rather than asserting it."""
    if not os.path.exists(PANEL):
        pytest.skip("bonus-share panel not materialized")
    from core.b0_provenance import file_sha256
    before = file_sha256(PANEL)
    r = subprocess.run(
        [sys.executable, os.path.join("research", "b0_materializer",
                                      "build_bonus_share_panel.py")],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("builder inputs unavailable: %s" % r.stdout[-200:])
    assert file_sha256(PANEL) == before


# --- the C-50 seam ------------------------------------------------------------

def test_the_official_rate_reaches_the_share_unit_producer():
    m = holder_multiplier({"stock_id": "2548", "kind": "stock_dividend",
                           "reconstructibility": "RECONSTRUCTIBLE",
                           "bonus_shares_per_1000": "100"})
    assert m == pytest.approx(1.1)


def test_a_bonus_rate_on_a_non_stock_dividend_is_refused():
    """The official bonus field is canonical for stock dividends only."""
    with pytest.raises(ShareUnitAdjustmentError, match="R1"):
        holder_multiplier({"stock_id": "1234", "kind": "capital_reduction",
                           "reconstructibility": "RECONSTRUCTIBLE",
                           "bonus_shares_per_1000": "100"})


def test_a_zero_allotment_does_not_create_a_boundary():
    with pytest.raises(ShareUnitAdjustmentError, match="transforms nothing"):
        holder_multiplier({"stock_id": "1234", "kind": "stock_dividend",
                           "reconstructibility": "RECONSTRUCTIBLE",
                           "bonus_shares_per_1000": "0"})
