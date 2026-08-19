"""R1–R4 · what a RUN INVALID leaves behind, and what it does not.

Run `L2-2520c80aa980d681` executed all 141 periods and formed nothing: no
non-empty SelectionScore cross-section, no target or executed portfolio, no NAV
that was anything but the opening cash restated, no performance quantity. The
ruling of 2026-08-19 says that is not an effective observation — and says it
NARROWLY, because "a crashed run never counts" would be an open invitation to
crash on purpose.

The narrowness is the part worth testing. Any one of the five attested
conditions failing spends the observation; any outcome other than the single
conformance-failure outcome can never be attested at all; and the two remaining
conditions are enforced at the reopening call site, where comparing seal
identities beats a boolean promising a seal was taken.
"""

import pytest

from core.b0_finalization_items import assert_not_blocked, open_keys, summary
from core.b0_master_prereg import (
    ATTESTED_CONDITIONS,
    DataRepair,
    ImplementationConformanceRepair,
    L2_NON_EVIDENTIAL_OUTCOMES,
    L2_NOT_EVALUABLE,
    L2_NOT_EVALUABLE_CA_BLOCK,
    L2_NOT_SUPPORTED,
    L2_OUTCOMES,
    L2_RUN_INVALID_CONFORMANCE,
    L2_SUPPORTED,
    MasterPreregViolation,
    NON_CONSUMING_OUTCOMES,
    NON_CONSUMPTION_CONDITIONS,
    NON_CONSUMPTION_ENFORCEMENT,
    L2Opening,
    NonConsumptionAttestation,
    assert_conformance_repair_admissible,
    assert_non_consumption_admissible,
    assert_reopening_admissible,
    assert_rerun_admissible,
    effective_observation_count,
    read_non_consumption,
    record_non_consumption,
    record_opening,
)

OLD_SEAL = "7faad84ab88c972474780d406cb3504e039d26d416c21c62a1cd1ed7ae1c3289"
NEW_SEAL = "aea938248ef8bdee4fdb3b6fb5cade7bd58e0219a7c9dab2dda51c076dc52cee"


def _opening(**kw):
    base = dict(opened_at="2026-08-19T06:25:31.174494+00:00",
                spec_sha256="a" * 64, code_commit="d49222b1",
                data_manifest_sha256="b" * 64,
                outcome=L2_RUN_INVALID_CONFORMANCE)
    base.update(kw)
    return L2Opening(**base)


def _att(**kw):
    base = dict(opened_at="2026-08-19T06:25:31.174494+00:00",
                run_id="L2-2520c80aa980d681",
                outcome=L2_RUN_INVALID_CONFORMANCE,
                ruling="RULING of 2026-08-19 R1/R2",
                evidence="141/141 periods, eligible=0 everywhere, receipts=0")
    base.update({c: True for c in ATTESTED_CONDITIONS})
    base.update(kw)
    return NonConsumptionAttestation(**base)


def _conformance_repair(**kw):
    base = dict(description="monthly_revenue supplied 13 against a required 18",
                frozen_semantics_reference="lookback_L_months = 18 (revenue_accel)",
                semantics_frozen_before_run=True,
                changes_strategy_semantics=False,
                performance_consulted=False,
                selected_by_portfolio_exposure=False)
    base.update(kw)
    return ImplementationConformanceRepair(**base)


def _data_repair(**kw):
    base = dict(description="65 stock dividends lack a credit date",
                independent_source="TWSE public filings, whole event class",
                scope="whole_source", performance_consulted=False,
                selected_by_portfolio_exposure=False)
    base.update(kw)
    return DataRepair(**base)


# --- R2 · the rule is narrow --------------------------------------------------

def test_only_the_conformance_failure_outcome_can_ever_be_non_consuming():
    assert NON_CONSUMING_OUTCOMES == (L2_RUN_INVALID_CONFORMANCE,)


@pytest.mark.parametrize(
    "outcome", [o for o in L2_OUTCOMES if o != L2_RUN_INVALID_CONFORMANCE])
def test_no_other_outcome_may_be_attested_non_consuming(outcome):
    with pytest.raises(MasterPreregViolation, match="can never be non-consuming"):
        _att(outcome=outcome)


def test_non_evidential_is_not_the_same_property_as_non_consuming():
    """A data block proves nothing about the strategy AND still spends a look."""
    assert L2_NOT_EVALUABLE in L2_NON_EVIDENTIAL_OUTCOMES
    assert L2_NOT_EVALUABLE not in NON_CONSUMING_OUTCOMES
    assert L2_NOT_EVALUABLE_CA_BLOCK not in NON_CONSUMING_OUTCOMES


@pytest.mark.parametrize("condition", sorted(ATTESTED_CONDITIONS))
def test_every_attested_condition_is_load_bearing(condition):
    assert_non_consumption_admissible(_att())          # all true -> admissible
    with pytest.raises(MasterPreregViolation, match=condition):
        assert_non_consumption_admissible(_att(**{condition: False}))


def test_all_seven_conditions_have_exactly_one_enforcement_site():
    assert set(NON_CONSUMPTION_ENFORCEMENT) == set(NON_CONSUMPTION_CONDITIONS)
    assert len(NON_CONSUMPTION_CONDITIONS) == 7
    deferred = [c for c in NON_CONSUMPTION_CONDITIONS
                if c not in ATTESTED_CONDITIONS]
    assert deferred == ["new_baseline_seal_taken",
                        "fresh_explicit_authorization_required"]


# --- R1 · effective observation accounting ------------------------------------

def test_an_attested_invalid_run_does_not_count(tmp_path):
    reg, led = str(tmp_path / "r.jsonl"), str(tmp_path / "a.jsonl")
    record_opening(_opening(), reg)
    assert effective_observation_count(reg, led) == 1      # unattested: it counts
    record_non_consumption(_att(), led)
    assert effective_observation_count(reg, led) == 0


def test_an_attestation_cannot_retire_a_decided_window(tmp_path):
    """A mis-filed attestation must not excuse a row that produced a verdict."""
    reg, led = str(tmp_path / "r.jsonl"), str(tmp_path / "a.jsonl")
    record_opening(_opening(outcome=L2_SUPPORTED), reg)
    record_non_consumption(_att(), led)                    # same opened_at
    assert effective_observation_count(reg, led) == 1


def test_the_invalid_run_is_still_recorded(tmp_path):
    """R1: preserve it permanently. Non-consuming is not the same as deleted."""
    reg, led = str(tmp_path / "r.jsonl"), str(tmp_path / "a.jsonl")
    record_opening(_opening(), reg)
    record_non_consumption(_att(), led)
    from core.b0_master_prereg import read_registry
    rows = read_registry(reg)
    assert len(rows) == 1
    assert rows[0]["outcome"] == L2_RUN_INVALID_CONFORMANCE


def test_the_repository_records_zero_effective_observations():
    """The claim about THIS project, bound to the files it actually has."""
    ledger = read_non_consumption()
    assert len(ledger) == 1
    att = NonConsumptionAttestation(**ledger[0])
    assert att.run_id == "L2-2520c80aa980d681"
    assert_non_consumption_admissible(att)
    assert effective_observation_count() == 0


# --- R3 · the two repair kinds are not interchangeable ------------------------

def test_a_conformance_failure_requires_a_conformance_repair():
    assert_rerun_admissible(_opening(), _conformance_repair())


def test_a_data_repair_may_not_stand_in_for_a_conformance_failure():
    with pytest.raises(MasterPreregViolation, match="requires a ImplementationConformanceRepair"):
        assert_rerun_admissible(_opening(), _data_repair())


@pytest.mark.parametrize("outcome", [L2_NOT_EVALUABLE, L2_NOT_EVALUABLE_CA_BLOCK])
def test_a_conformance_repair_may_not_close_a_data_block(outcome):
    with pytest.raises(MasterPreregViolation, match="requires a DataRepair"):
        assert_rerun_admissible(_opening(outcome=outcome), _conformance_repair())


@pytest.mark.parametrize("outcome", [L2_SUPPORTED, L2_NOT_SUPPORTED])
def test_a_decided_window_is_still_never_re_run(outcome):
    with pytest.raises(MasterPreregViolation, match="no-post-hoc-rescue"):
        assert_rerun_admissible(_opening(outcome=outcome), _conformance_repair())


def test_a_conformance_repair_must_cite_the_clause_it_conforms_to():
    with pytest.raises(MasterPreregViolation, match="cite the frozen clause"):
        assert_conformance_repair_admissible(
            _conformance_repair(frozen_semantics_reference="  "))


def test_semantics_written_after_the_run_are_not_a_repair():
    with pytest.raises(MasterPreregViolation, match="frozen before"):
        assert_conformance_repair_admissible(
            _conformance_repair(semantics_frozen_before_run=False))


def test_a_conformance_repair_may_not_change_the_strategy():
    with pytest.raises(MasterPreregViolation, match="changes strategy semantics"):
        assert_conformance_repair_admissible(
            _conformance_repair(changes_strategy_semantics=True))
    for subject in ("factor_definition", "factor_weight", "threshold",
                    "portfolio_construction", "execution", "cost",
                    "universe_rule", "corporate_action_semantics",
                    "performance_driven_data_policy"):
        assert subject in ImplementationConformanceRepair.FORBIDDEN_SUBJECTS


def test_a_conformance_repair_chosen_after_seeing_performance_is_a_rescue():
    with pytest.raises(MasterPreregViolation, match="post-hoc rescue"):
        assert_conformance_repair_admissible(
            _conformance_repair(performance_consulted=True))


def test_a_conformance_repair_scoped_to_the_portfolio_is_refused():
    with pytest.raises(MasterPreregViolation, match="selects the fix"):
        assert_conformance_repair_admissible(
            _conformance_repair(selected_by_portfolio_exposure=True))


# --- R2 conditions 6 and 7 · enforced, not attested ---------------------------

def test_reopening_requires_a_genuinely_new_baseline_seal():
    with pytest.raises(MasterPreregViolation, match="requires a NEW Baseline Seal"):
        assert_reopening_admissible(
            _opening(), _conformance_repair(),
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=OLD_SEAL,
            authorization_reference="ruling of 2026-08-19")


def test_reopening_requires_a_named_authorization():
    with pytest.raises(MasterPreregViolation, match="authorization_reference"):
        assert_reopening_admissible(
            _opening(), _conformance_repair(),
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=NEW_SEAL,
            authorization_reference="   ")


def test_reopening_still_requires_the_right_repair_kind():
    with pytest.raises(MasterPreregViolation, match="requires a ImplementationConformanceRepair"):
        assert_reopening_admissible(
            _opening(), _data_repair(),
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=NEW_SEAL,
            authorization_reference="a fresh explicit authorization")


def test_a_complete_reopening_claim_is_admissible():
    assert_reopening_admissible(
        _opening(), _conformance_repair(),
        previous_baseline_seal_sha256=OLD_SEAL,
        new_baseline_seal_sha256=NEW_SEAL,
        authorization_reference="a fresh explicit authorization")


# --- R4 · the M-3 item is closed, and closing it authorises nothing -----------

def test_the_finalization_register_no_longer_blocks_l2_opening():
    assert "l2_reopening_after_run_invalid" not in open_keys()
    assert summary()["by_stage"]["L2_opening"] == 0
    assert_not_blocked("L2_opening")
    assert_not_blocked("final_provenance_seal")


def test_closing_the_item_did_not_grant_a_retry():
    """Mechanically unblocked is not the same as authorised.

    Nothing in the register can satisfy 6.1.14: an opening still has to present a
    conformance repair, a different Baseline Seal, and a named authorization.
    """
    with pytest.raises(MasterPreregViolation):
        assert_reopening_admissible(
            _opening(), None,
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=NEW_SEAL,
            authorization_reference="a fresh explicit authorization")
