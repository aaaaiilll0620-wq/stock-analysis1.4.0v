"""C-48 · the `pbr_tse` lineage ruling, pinned.

The ruling's whole content is a set of things that must be IMPOSSIBLE, so the
load-bearing tests here are the negative controls: each one takes a source
contract that is well-formed in every other respect and changes exactly the one
field the ruling forbids. A ruling whose prohibitions are only prose is a
prohibition until someone is in a hurry.

The positive test is deliberately thin. That an admissible contract passes says
almost nothing — every wrong contract passes a check that does not exist.
"""

import dataclasses

import pytest

from core.b0_master_prereg import spec
from core.b0_valuation_source import (
    BOARD_ATTRIBUTION_SOURCE,
    CURRENT_LISTING_LABEL_ALLOWED,
    FORBIDDEN_GAP_REPAIRS,
    LINEAGE_BOUNDARY,
    MISSING_VALUE_POLICY,
    OFFICIAL_BOARDS,
    RUNTIME_FETCH_ALLOWED,
    TEJ_SUBSTITUTION_ALLOWED,
    TPEX_VINTAGE_MAY_BE_INFERRED,
    VALUATION_PARSER_VERSION,
    ValuationSourceContract,
    ValuationSourceError,
    assert_valuation_source_admissible,
    known_lineages,
    limitation_record,
    lineage_for,
)


def _admissible(**over) -> ValuationSourceContract:
    base = dict(
        name="official_exchange_pbr_panel",
        era=">= 2019-01-01",
        lineage="official_exchange_pbr",
        importer_version="official_pbr_importer_v1",
        parser_version=VALUATION_PARSER_VERSION,
        content_sha256="a" * 64,
        schema_sha256="b" * 64,
        date_min="2019-01-30",
        date_max="2026-03-31",
        sessions=87,
        securities=1961,
        coverage_rate_min=0.9369,
        coverage_rate_max=0.9842,
        na_policy=MISSING_VALUE_POLICY,
        live_fetch=False,
        upstream_sha256={"twse_2019-01-30": "c" * 64},
    )
    base.update(over)
    return ValuationSourceContract(**base)


def test_an_admissible_contract_passes():
    assert_valuation_source_admissible(_admissible())


# --- the prohibitions, one field at a time -----------------------------------

def test_tej_is_not_a_selectable_lineage():
    """R1: PBR_TEJ is not a fallback, a gap-filler or a tie-break."""
    with pytest.raises(ValuationSourceError, match="PBR_TEJ"):
        assert_valuation_source_admissible(_admissible(lineage="pbr_tej"))
    assert "pbr_tej" not in known_lineages()
    assert TEJ_SUBSTITUTION_ALLOWED is False


def test_a_live_endpoint_is_not_a_source():
    """R5: L2 must consume harvested, hashed, provenance-bound data."""
    with pytest.raises(ValuationSourceError, match="live_fetch"):
        assert_valuation_source_admissible(_admissible(live_fetch=True))
    assert RUNTIME_FETCH_ALLOWED is False


def test_a_gap_repair_cannot_be_declared_as_the_na_policy():
    """R3: NA propagates to complete-case; the four repairs stay forbidden."""
    for repair in FORBIDDEN_GAP_REPAIRS:
        with pytest.raises(ValuationSourceError, match="R3"):
            assert_valuation_source_admissible(_admissible(na_policy=repair))
    assert MISSING_VALUE_POLICY == "NA -> §4.1 complete-case"


def test_current_listing_label_cannot_attribute_a_board():
    """R4: the current 上市別 is rewritten on delisting (§2.3)."""
    with pytest.raises(ValuationSourceError, match="R4"):
        assert_valuation_source_admissible(
            _admissible(board_attribution_source="current_上市別"))
    assert CURRENT_LISTING_LABEL_ALLOWED is False
    assert BOARD_ATTRIBUTION_SOURCE == "contemporaneous_exchange_payload"


def test_a_parser_change_changes_the_source_identity():
    """A parser fix can move a number, so it may not be invisible."""
    with pytest.raises(ValuationSourceError, match="parser"):
        assert_valuation_source_admissible(
            _admissible(parser_version="official_pbr_parser_v0"))


def test_the_era_boundary_is_not_a_per_run_choice():
    """The 2019 boundary is §2.8.3's, reused — not re-decidable per source."""
    with pytest.raises(ValuationSourceError, match="frozen to lineage"):
        assert_valuation_source_admissible(
            _admissible(era="<= 2018-12-31", lineage="official_exchange_pbr"))
    with pytest.raises(ValuationSourceError, match="frozen eras"):
        assert_valuation_source_admissible(_admissible(era="2019-2022"))


def test_a_source_without_upstream_hashes_is_not_sealed():
    with pytest.raises(ValuationSourceError, match="upstream"):
        _admissible(upstream_sha256={})


@pytest.mark.parametrize("field", ["content_sha256", "schema_sha256",
                                   "importer_version", "parser_version"])
def test_every_identity_field_is_mandatory(field):
    with pytest.raises(ValuationSourceError, match="must declare"):
        _admissible(**{field: "  "})


def test_the_contract_is_frozen_against_mutation():
    c = _admissible()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.lineage = "pbr_tej"          # type: ignore[misc]


# --- the boundary itself ------------------------------------------------------

def test_every_session_resolves_to_exactly_one_lineage():
    assert lineage_for("2018-12-28") == "yearly_export_pbr_tse"
    assert lineage_for("2018-12-31") == "yearly_export_pbr_tse"
    assert lineage_for(LINEAGE_BOUNDARY) == "official_exchange_pbr"
    assert lineage_for("2019-01-30") == "official_exchange_pbr"
    assert lineage_for("2026-03-31") == "official_exchange_pbr"


def test_a_non_session_string_aborts_rather_than_guessing():
    with pytest.raises(ValuationSourceError):
        lineage_for("2019")


# --- the disclosures that must travel with the series ------------------------

def test_the_tpex_limitation_keeps_the_two_claims_apart():
    """R2: 'official daily value' is admissible; 'which vintage' is not."""
    rec = limitation_record()["tpex_pre_vintage"]
    assert rec["admissible"] == "Official historical daily PBR is admissible."
    assert "must not be claimed" in rec["inadmissible"]
    assert rec["vintage_disclosure_first_session"] == "2025-01-02"
    assert rec["may_be_inferred"] is False
    assert TPEX_VINTAGE_MAY_BE_INFERRED is False


def test_the_2025_coverage_shift_cannot_move_strategy_semantics():
    """R6: recorded as an observation, load-bearing for nothing."""
    rec = limitation_record()["coverage_regime_2025"]
    assert rec["may_modify_selection_semantics"] is False
    assert rec["may_modify_historical_eligibility"] is False
    assert rec["reopens_b09"] is False


# --- the ruling is reachable through the frozen registry ---------------------

def test_the_ruling_is_in_the_frozen_spec_not_only_in_a_document():
    assert spec("value_pbr_lineage_boundary") == LINEAGE_BOUNDARY
    assert spec("value_pbr_official_boards") == OFFICIAL_BOARDS == ("TWSE", "TPEx")
    assert spec("value_pbr_tej_substitution_allowed") is False
    assert spec("value_pbr_runtime_fetch_allowed") is False
    assert spec("value_pbr_current_listing_label_allowed") is False
    assert spec("value_pbr_tpex_vintage_may_be_inferred") is False
    assert spec("value_pbr_missing_value_policy") == MISSING_VALUE_POLICY


def test_the_open_item_is_closed_and_the_module_is_normative():
    """Scoped to C-48's own item on purpose.

    Whether the register is globally empty is a different claim, pinned by
    `test_the_register_is_empty_and_that_is_the_goal_state`. Asserting it here
    too would make this test go red when some LATER behaviour is registered —
    which is the mechanism working, not C-48 coming undone.
    """
    from core.b0_master_prereg import NORMATIVE_MODULES
    from core.b0_open_items import OPEN_ITEMS

    assert "core/b0_valuation_source.py" in NORMATIVE_MODULES
    assert "value_pbr_lineage_2019plus" not in [i.key for i in OPEN_ITEMS]
