"""Tests for the frozen B0 rulings O-1, V-1b, V-5, V-6.

These are not behavioural tests of a computation — they pin decisions, so that
re-opening one requires changing a test rather than editing a default.
"""

import pytest

from core.b0_frozen_spec import (
    BLOCKING_DATA_REQUIREMENTS,
    CASH_EARNS_INTEREST,
    CHIP_GROSS_ROLE,
    CHIP_SEMANTICS,
    CHIP_SEMANTICS_FORBIDDEN,
    L3_CHECKPOINT_INTERVAL_MONTHS,
    L3_FIRST_CHECKPOINT_MONTHS,
    RISK_FREE_RATE,
    SHARPE_METRIC_NAME,
    FrozenSpecViolation,
    assert_chip_semantics,
    assert_l3_assessment_allowed,
    assert_no_blocking_requirements,
    assert_sharpe_named_explicitly,
    is_l3_assessment_month,
    l3_checkpoints,
    next_l3_checkpoint,
    unmet_blocking_requirements,
    verify_stock_dividend_rows,
)


# --- O-1 ---------------------------------------------------------------------

def test_O1_chip_semantics_is_net():
    assert CHIP_SEMANTICS == "net"
    assert "gross" in CHIP_SEMANTICS_FORBIDDEN
    assert CHIP_GROSS_ROLE == "diagnostic_only"


def test_O1_gross_is_not_a_fallback():
    assert_chip_semantics("net")
    for bad in ("gross", "auto", "", "NET"):
        with pytest.raises(FrozenSpecViolation, match="O-1"):
            assert_chip_semantics(bad)


# --- V-6 ---------------------------------------------------------------------

def test_V6_sharpe_convention_frozen():
    assert SHARPE_METRIC_NAME == "Sharpe_0rf"
    assert RISK_FREE_RATE == 0.0
    assert CASH_EARNS_INTEREST is False


def test_V6_bare_sharpe_name_is_rejected():
    assert_sharpe_named_explicitly("Sharpe_0rf")
    for bad in ("Sharpe", "sharpe", "Sharpe Ratio"):
        with pytest.raises(FrozenSpecViolation, match="V-6"):
            assert_sharpe_named_explicitly(bad)


# --- V-5 ---------------------------------------------------------------------

def test_V5_checkpoint_schedule():
    assert L3_FIRST_CHECKPOINT_MONTHS == 36
    assert L3_CHECKPOINT_INTERVAL_MONTHS == 24
    assert l3_checkpoints(5) == (36, 60, 84, 108, 132)


@pytest.mark.parametrize("m", [0, 1, 12, 24, 35])
def test_V5_no_early_graduation(m):
    assert not is_l3_assessment_month(m)
    assert next_l3_checkpoint(m) == 36
    with pytest.raises(FrozenSpecViolation, match="optional stopping"):
        assert_l3_assessment_allowed(m)


@pytest.mark.parametrize("m", [36, 60, 84, 108, 132])
def test_V5_checkpoints_are_assessable(m):
    assert is_l3_assessment_month(m)
    assert_l3_assessment_allowed(m)


@pytest.mark.parametrize("m,expected_next", [
    (37, 60), (38, 60), (59, 60), (61, 84), (85, 108),
])
def test_V5_off_checkpoint_months_are_peeks_not_tests(m, expected_next):
    """The 37/38/39-then-pick-a-good-month failure mode is closed."""
    assert not is_l3_assessment_month(m)
    assert next_l3_checkpoint(m) == expected_next
    with pytest.raises(FrozenSpecViolation):
        assert_l3_assessment_allowed(m)


def test_V5_interval_is_permanent_not_just_the_second_checkpoint():
    assert l3_checkpoints(8)[-1] == 36 + 24 * 7


# --- V-1b (as amended by W-1 / W-2) ------------------------------------------
# The requirement is now MET: the 配股相關 export landed and carries absolute
# new-share counts, 除權日 and 上市日/發放日. What changed under W-1 is what
# "met" means — the source must be semantically sufficient and self-classifying,
# not gap-free. A gap fails at exposure time (tests/test_b0_corporate_actions.py),
# which is why the verifier no longer rejects a source for having one.


def _req():
    return {r.key: r for r in BLOCKING_DATA_REQUIREMENTS}["stock_dividend_pit_source"]


def test_V1b_requirement_is_registered_and_now_met_by_a_real_source():
    req = _req()
    assert set(req.required_fields) >= {
        "ex_right_date", "distribution_ratio_or_new_shares",
        "actual_credit_tradable_date", "reconstructibility", "reason"}
    assert "S-3" in req.blocks and "final_provenance_seal" in req.blocks
    res = req.verify()
    assert res.satisfied, res.detail
    assert res.diagnostics["rows"] > 0
    assert res.diagnostics["bad_ex_right_date"] == 0


def test_V1b_satisfaction_is_not_a_settable_flag():
    """A boolean someone can flip is how a blocking requirement gets closed
    without the data ever arriving. Satisfaction must come from a verifier."""
    req = _req()
    assert not hasattr(req, "satisfied")
    assert req.verifier in ("stock_dividend_source",)


def test_V1b_verifier_still_blocks_when_the_source_goes_missing():
    """Negative control: the guard passes because of the data, not because it
    was disarmed. Repoint it at a non-existent file and it must block again."""
    import dataclasses
    broken = dataclasses.replace(_req(), source_path="does/not/exist.csv")
    assert not broken.verify().satisfied
    assert "not present" in broken.verify().detail


def test_V1b_verifier_rejects_absent_empty_and_incomplete_sources():
    assert not verify_stock_dividend_rows([]).satisfied
    incomplete = [{"stock_id": "1101", "ex_right_date": "20260806"}]
    r = verify_stock_dividend_rows(incomplete)
    assert not r.satisfied and "missing required columns" in r.detail


def _row(**kw):
    base = {"stock_id": "1101", "ex_right_date": "20260806",
            "distribution_ratio_or_new_shares": 100.0,
            "actual_credit_tradable_date": "20260904",
            "reconstructibility": "RECONSTRUCTIBLE", "reason": ""}
    base.update(kw)
    return base


def test_V1b_verifier_accepts_a_well_formed_source():
    r = verify_stock_dividend_rows([_row(), _row(stock_id="2330")])
    assert r.satisfied
    assert r.diagnostics["rows"] == 2
    assert r.diagnostics["rows_by_ex_right_year"] == {"2026": 2}
    assert r.diagnostics["reconstructibility"] == {"RECONSTRUCTIBLE": 2}


def test_V1b_verifier_catches_unparseable_ex_right_date():
    """An unrecoverable schema defect, distinct from a data gap."""
    r = verify_stock_dividend_rows([_row(ex_right_date=".")])
    assert not r.satisfied and "unparseable ex_right_date" in r.detail


def test_W1_missing_credit_date_is_classified_not_rejected():
    """W-1: per event, no interpolation, no missing-rate threshold. The row is
    kept and labelled; it aborts only when the portfolio is exposed to it."""
    r = verify_stock_dividend_rows([
        _row(),
        _row(stock_id="2330", actual_credit_tradable_date="",
             reconstructibility="NOT_RECONSTRUCTIBLE",
             reason="no 股票股利上市日/發放日"),
    ])
    assert r.satisfied
    assert r.diagnostics["reconstructibility"] == {
        "NOT_RECONSTRUCTIBLE": 1, "RECONSTRUCTIBLE": 1}
    assert r.diagnostics["receivable_ordering"]["missing"] == 1


def test_W1_a_gap_without_a_reason_is_still_rejected():
    """'NOT_RECONSTRUCTIBLE' with no reason is indistinguishable from an event
    the system never noticed — the exact confusion three states exist to remove."""
    r = verify_stock_dividend_rows([_row(reconstructibility="NOT_RECONSTRUCTIBLE",
                                         reason="")])
    assert not r.satisfied and "reconstructibility" in r.detail


def test_W1_an_unclassified_row_is_rejected():
    for bad in ("", "MAYBE", "reconstructible"):
        r = verify_stock_dividend_rows([_row(reconstructibility=bad)])
        assert not r.satisfied, bad


def test_W2_zero_day_receivable_is_legal():
    """Ruled legal: credit == ex-right. Only credit < ex-right is impossible."""
    r = verify_stock_dividend_rows([_row(actual_credit_tradable_date="20260806")])
    assert r.satisfied
    assert r.diagnostics["receivable_ordering"] == {"zero_day": 1}


def test_W2_credit_before_ex_right_still_fails():
    r = verify_stock_dividend_rows([_row(actual_credit_tradable_date="20260805")])
    assert not r.satisfied and "precedes ex-right" in r.detail


def test_V1b_itself_no_longer_blocks():
    """V-1b is met. The seal is still blocked, but by D-1, not by this."""
    unmet = {r.key for r in unmet_blocking_requirements()}
    assert "stock_dividend_pit_source" not in unmet


def test_the_gate_still_discriminates_by_stage():
    assert_no_blocking_requirements("some_unrelated_stage")


def test_V1b_reason_rejects_both_escape_hatches():
    """Neither inference from the ex-reference price nor omission is allowed."""
    req = _req()
    assert "ex-reference price" in req.reason
    assert "Ignoring stock" in req.reason


# --- integration: the gate is wired into the seal, and still fires -----------

def _clean_manifest():
    from core.b0_master_prereg import normative_module_hashes
    from core.b0_provenance import (
        CodeProvenance, ConfigProvenance, DatasetProvenance,
        DerivedArtifactProvenance, ExecutionProvenance, OutputProvenance,
        ProvenanceManifest, SpecificationProvenance,
    )
    return ProvenanceManifest(
        specification=SpecificationProvenance(
            "docs/FrozenB0_MasterPreregistration.md", "s" * 64, "1.13"),
        code=CodeProvenance("a" * 40, False, None, "lock#1",
                            normative_module_hashes()),
        config=ConfigProvenance({"N_target": 20}, {}),
        data=(DatasetProvenance("price_valuation", "d1", "s1",
                                "2004-01-02", "2026-07-14", "tej_importer@1"),),
        derived=(DerivedArtifactProvenance("b_value_reference", "v1", ("d1",)),),
        execution=ExecutionProvenance("2026-03-31", "state#1",
                                      {"price_valuation": "2026-03-30"},
                                      "core.b0_route", "1.0.0"),
        output=OutputProvenance({"nav": "o1"}),
        baseline_seal_sha256="b" * 64,
    )


def _without_finalization_items(monkeypatch):
    """F-0 blocks every final seal until the hash scope is ruled on.

    A test aimed at the data-requirement layer clears the finalization register
    on an isolated copy, so that what it measures is still the data gate. The
    F-0 block itself is measured by `test_final_seal_is_blocked_by_the_open_hash_
    scope_item`, which does NOT clear it.
    """
    import core.b0_finalization_items as fin

    monkeypatch.setattr(fin, "FINALIZATION_ITEMS", ())


def test_the_finalization_register_is_empty_after_the_f0_ruling():
    """F-0 was ruled on (F0-R1 ~ F0-R7), so nothing blocks finalization here.

    The register itself stays: the next finalization-blocking gap has to land in
    it rather than in somebody's judgement about whether a seal is safe.
    """
    from core.b0_finalization_items import summary

    assert summary()["total"] == 0


def test_the_finalization_block_still_fires_when_an_item_is_open(monkeypatch):
    """Negative control: the mechanism was not retired along with the item."""
    import core.b0_finalization_items as fin
    from core.b0_finalization_items import FinalizationBlocked, FinalizationItem
    from core.b0_provenance import seal

    item = FinalizationItem(
        key="synthetic_scope_gap", question="q?", why_it_matters="w",
        measured="m", options=("a", "b"), blocks=("final_provenance_seal",),
        opened_by="test")
    monkeypatch.setattr(fin, "FINALIZATION_ITEMS", (item,))
    with pytest.raises(FinalizationBlocked, match="synthetic_scope_gap"):
        seal(_clean_manifest(), final_seal=True, env={})


def test_a_non_final_seal_is_not_blocked_by_the_hash_scope_item(monkeypatch):
    """The block is scoped to finalization; mechanics stay testable meanwhile."""
    from core.b0_provenance import seal
    import core.b0_frozen_spec as spec

    monkeypatch.setattr(spec, "BLOCKING_DATA_REQUIREMENTS", (_req(),))
    assert len(seal(_clean_manifest(), final_seal=False, env={})) == 64


def test_final_seal_passes_when_no_requirement_is_unmet(monkeypatch):
    """V-1b's own requirement is met; with D-1 out of the way the seal closes,
    which shows the block is D-1's doing and not a permanently stuck gate."""
    from core.b0_provenance import seal
    import core.b0_frozen_spec as spec

    _without_finalization_items(monkeypatch)
    v1b = _req()
    monkeypatch.setattr(spec, "BLOCKING_DATA_REQUIREMENTS", (v1b,))
    assert v1b.verify().satisfied
    assert len(seal(_clean_manifest(), final_seal=True, env={})) == 64


# --- D-1 · price-universe survivorship ---------------------------------------

def test_D1_is_registered_and_now_met_by_the_repaired_source():
    req = {r.key: r for r in BLOCKING_DATA_REQUIREMENTS}["price_universe_survivorship"]
    assert set(req.blocks) >= {"S-3", "final_provenance_seal", "L2_opening"}
    res = req.verify()
    assert res.satisfied, res.detail
    assert res.diagnostics["source_only_backstop"]["satisfied"] is True


def test_D1_blocks_again_if_the_audit_goes_missing(monkeypatch):
    """Negative control on the integration: the gate still fires."""
    import dataclasses

    from core.b0_provenance import ProvenanceError, seal
    import core.b0_frozen_spec as spec

    _without_finalization_items(monkeypatch)
    req = {r.key: r for r in BLOCKING_DATA_REQUIREMENTS}["price_universe_survivorship"]
    broken = dataclasses.replace(req, source_path="does/not/exist.csv")
    monkeypatch.setattr(spec, "BLOCKING_DATA_REQUIREMENTS", (broken,))
    with pytest.raises(FrozenSpecViolation, match="price_universe_survivorship"):
        assert_no_blocking_requirements("L2_opening")
    with pytest.raises(ProvenanceError, match="price_universe_survivorship"):
        seal(_clean_manifest(), final_seal=True, env={})


def test_D1_verifier_flags_zero_departure_years():
    """Zero delistings across a year is a universe filter, not a market fact."""
    from core.b0_frozen_spec import verify_price_universe_churn

    rows = [{"year": "2019", "securities": 1734, "dropped_next_year": 0,
             "dropped_but_traded_to_year_end": 0}]
    r = verify_price_universe_churn(rows)
    assert not r.satisfied and "zero departures" in r.detail


def test_D1_year_end_vanishers_are_reported_not_gated():
    """This signal has a legitimate baseline: a security trading to the final
    session of a year and delisting in early January vanishes exactly like a
    filtered-out one, and it happens every year. Gating on it would block every
    real corpus. The contradiction it reached for is C2's job, measured with the
    `explained` instrument."""
    from core.b0_frozen_spec import verify_price_universe_churn

    rows = [{"year": "2018", "securities": 1817, "dropped_next_year": 110,
             "dropped_but_traded_to_year_end": 90}]
    r = verify_price_universe_churn(rows)
    assert r.satisfied
    assert r.diagnostics["vanished_after_trading_to_year_end"] == {"2018": 90}
    assert r.diagnostics["vanished_at_year_end_is_reported_not_gated"] is True


def test_D1_verifier_accepts_ordinary_churn():
    from core.b0_frozen_spec import verify_price_universe_churn

    rows = [{"year": str(y), "securities": 1700 + y - 2012,
             "dropped_next_year": 14, "dropped_but_traded_to_year_end": 0}
            for y in range(2012, 2018)]
    r = verify_price_universe_churn(rows)
    assert r.satisfied, r.detail


def test_D1_reason_states_the_remedy_and_refuses_reconstruction():
    req = {r.key: r for r in BLOCKING_DATA_REQUIREMENTS}["price_universe_survivorship"]
    assert "re-export" in req.reason
    assert "impossible" in req.reason


def test_V1b_final_seal_blocks_again_if_the_source_disappears(monkeypatch):
    """Negative control on the integration, not just on the verifier: the seal
    must fail loudly when a blocking requirement is unmet."""
    import dataclasses

    from core.b0_provenance import ProvenanceError, seal
    import core.b0_frozen_spec as spec

    _without_finalization_items(monkeypatch)
    broken = dataclasses.replace(_req(), source_path="does/not/exist.csv")
    monkeypatch.setattr(spec, "BLOCKING_DATA_REQUIREMENTS", (broken,))
    with pytest.raises(ProvenanceError, match="stock_dividend_pit_source"):
        seal(_clean_manifest(), final_seal=True, env={})
    # intermediate audits remain possible even while blocked
    assert len(seal(_clean_manifest(), final_seal=False, env={})) == 64
