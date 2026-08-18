# -*- coding: utf-8 -*-
"""Two-stage provenance: the pre-L2 Baseline Seal and the L2 run record.

M-3 ruling of 2026-08-18 (master preregistration v1.14). Before the ruling,
`seal(final_seal=True)` was unreachable: it rejects an empty section, and the
only way to fill `execution.decision_date` / `output.artifacts` is to run the B0
route — the step the seal exists to authorise.

What these tests pin down is that the fix did NOT become "allow blanks":

  * a baseline states `NOT_EXECUTED_PRE_L2` / `NOT_PRODUCED_PRE_L2` explicitly,
  * a baseline carrying output hashes is REJECTED, not tolerated,
  * a run record must name the baseline it descends from,
  * a run record may add outputs but may not restate the baseline's bindings,
  * every pre-existing abort (spec / module / data provenance) still fires.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.b0_provenance import (
    CodeProvenance,
    ConfigProvenance,
    DatasetProvenance,
    DerivedArtifactProvenance,
    EXECUTED,
    ExecutionProvenance,
    NOT_EXECUTED_PRE_L2,
    NOT_PRODUCED_PRE_L2,
    OutputProvenance,
    PRODUCED,
    ProvenanceError,
    ProvenanceManifest,
    RepoIdentityGuard,
    SEAL_STAGE_BASELINE,
    SEAL_STAGE_L2_RUN,
    SealRaceError,
    SpecificationProvenance,
    assert_baseline_not_mutated,
    seal,
)

CLEAN_ENV: dict[str, str] = {}


@pytest.fixture
def no_finalization_block(monkeypatch):
    """Isolate the STAGE contract from environment-dependent gates.

    These tests measure whether the two-stage rules hold, not whether this
    particular machine currently has every dataset on disk. The data gate and
    the finalization register have their own tests, which do NOT clear them.
    """
    import core.b0_finalization_items as fin
    import core.b0_frozen_spec as spec

    monkeypatch.setattr(fin, "FINALIZATION_ITEMS", ())
    monkeypatch.setattr(spec, "BLOCKING_DATA_REQUIREMENTS", ())

L2_PROTOCOL = {
    "window": "2014-07-31..2026-03-31",
    "months": 141,
    "gate": "net cumulative wealth > frozen market benchmark AND net CAGR > 0 "
            "AND Sharpe_0rf > 0",
    "verdict_vocabulary": ["Supported", "Not Supported"],
    "openings_permitted": 1,
}


def _baseline(**over) -> ProvenanceManifest:
    from core.b0_master_prereg import normative_module_hashes

    m = ProvenanceManifest(
        specification=SpecificationProvenance(
            "docs/FrozenB0_MasterPreregistration.md", "s" * 64, "1.14"),
        code=CodeProvenance("a" * 40, False, None, "lock#1", normative_module_hashes()),
        config=ConfigProvenance({"N_target": 20, "w_target": 0.05}, {}),
        data=(DatasetProvenance("price_valuation", "d1", "s1",
                                "2004-01-02", "2026-08-17", "tej_importer@1"),),
        derived=(DerivedArtifactProvenance("b_value_reference", "v1", ("d1",)),),
        execution=ExecutionProvenance.pre_l2_baseline(
            initial_state_sha256="opening_state#1",
            market_data_as_of={"price_valuation": "2026-08-17"},
            route_module="core.b0_route", route_version="1.0.0"),
        output=OutputProvenance.pre_l2_baseline(),
        l2_opening_protocol=L2_PROTOCOL,
    )
    return dataclasses.replace(m, **over) if over else m


def _run_from(baseline: ProvenanceManifest, **over) -> ProvenanceManifest:
    m = dataclasses.replace(
        baseline,
        execution=dataclasses.replace(
            baseline.execution, decision_date="2026-03-31", status=EXECUTED),
        output=OutputProvenance({"target_list": "o1", "intent": "o2",
                                 "receipt": "o3", "nav": "o4"}),
        baseline_seal_sha256=baseline.manifest_sha256,
    )
    return dataclasses.replace(m, **over) if over else m


# --- the baseline seal is reachable ------------------------------------------

def test_baseline_seal_succeeds_with_explicit_not_executed_states(no_finalization_block):
    """The whole point of the ruling: this call used to be impossible."""
    m = _baseline()
    assert m.stage == SEAL_STAGE_BASELINE
    assert m.execution.status == NOT_EXECUTED_PRE_L2
    assert m.output.status == NOT_PRODUCED_PRE_L2
    assert len(seal(m, final_seal=True, env=CLEAN_ENV)) == 64


def test_absence_of_a_run_is_stated_not_blank():
    """A blank field says nothing; these states are an assertion about the world."""
    m = _baseline()
    assert m.execution.decision_date == ""
    assert dict(m.output.artifacts) == {}
    # ...and the statement is part of the sealed identity, so a baseline and a
    # run over identical inputs cannot collapse to the same hash.
    assert "execution_status" in m.sealed_input_sha256_payload_sections()
    assert "output_status" in m.sealed_input_sha256_payload_sections()


def test_baseline_binds_the_l2_opening_protocol(no_finalization_block):
    """The gate has to be fixed before the run, not after seeing the numbers."""
    with pytest.raises(ProvenanceError, match="l2_opening_protocol"):
        seal(_baseline(l2_opening_protocol={}), final_seal=True, env=CLEAN_ENV)


def test_baseline_still_binds_route_and_opening_state():
    """Knowable without running anything — so omitting them lets them drift."""
    with pytest.raises(ProvenanceError, match="route_module"):
        _baseline(execution=ExecutionProvenance(
            "", "state#1", {"d": "1"}, "", "1.0.0",
            NOT_EXECUTED_PRE_L2)).execution.validate()
    with pytest.raises(ProvenanceError, match="initial_state_sha256"):
        _baseline(execution=ExecutionProvenance(
            "", "", {"d": "1"}, "core.b0_route", "1.0.0",
            NOT_EXECUTED_PRE_L2)).execution.validate()


# --- a baseline may not fabricate a run --------------------------------------

def test_baseline_rejects_a_fabricated_decision_date(no_finalization_block):
    bad = ExecutionProvenance("2026-03-31", "state#1", {"d": "1"},
                              "core.b0_route", "1.0.0", NOT_EXECUTED_PRE_L2)
    with pytest.raises(ProvenanceError, match="fabricates a run"):
        seal(_baseline(execution=bad), final_seal=True, env=CLEAN_ENV)


def test_baseline_rejects_fabricated_output_hashes(no_finalization_block):
    bad = OutputProvenance({"nav": "o1"}, NOT_PRODUCED_PRE_L2)
    with pytest.raises(ProvenanceError, match="did not happen"):
        seal(_baseline(output=bad), final_seal=True, env=CLEAN_ENV)


def test_a_baseline_with_real_outputs_is_a_run_and_needs_a_baseline_ref(no_finalization_block):
    """Flipping output to PRODUCED without a baseline reference must not seal."""
    m = _baseline(output=OutputProvenance({"nav": "o1"}, PRODUCED))
    with pytest.raises(ProvenanceError, match="cannot carry outputs"):
        seal(m, final_seal=True, env=CLEAN_ENV)


def test_baseline_may_not_reference_another_baseline(no_finalization_block):
    with pytest.raises(ProvenanceError, match="belongs on an L2 run record"):
        seal(_baseline(baseline_seal_sha256="c" * 64), final_seal=True, env=CLEAN_ENV)


# --- every pre-existing abort still fires ------------------------------------

def test_missing_spec_still_aborts_at_baseline(no_finalization_block):
    bad = SpecificationProvenance("docs/x.md", "", "1.14")
    with pytest.raises(ProvenanceError, match="spec_sha256"):
        seal(_baseline(specification=bad), final_seal=True, env=CLEAN_ENV)


def test_missing_normative_module_hashes_still_abort_at_baseline(no_finalization_block):
    bad = CodeProvenance("a" * 40, False, None, "lock#1", {})
    with pytest.raises(ProvenanceError, match="normative module"):
        seal(_baseline(code=bad), final_seal=True, env=CLEAN_ENV)


def test_missing_data_provenance_still_aborts_at_baseline(no_finalization_block):
    with pytest.raises(ProvenanceError, match="missing sections"):
        seal(_baseline(data=()), final_seal=True, env=CLEAN_ENV)


def test_incomplete_dataset_identity_still_aborts_at_baseline(no_finalization_block):
    bad = (DatasetProvenance("price_valuation", "d1", "", "2004-01-02",
                             "2026-08-17", "tej_importer@1"),)
    with pytest.raises(ProvenanceError, match="schema_sha256"):
        seal(_baseline(data=bad), final_seal=True, env=CLEAN_ENV)


def test_dirty_tree_still_forbidden_at_baseline(no_finalization_block):
    dirty = CodeProvenance("a" * 40, True, "diff#1", "lock#1",
                           _baseline().code.normative_module_sha256)
    with pytest.raises(ProvenanceError, match="dirty working tree"):
        seal(_baseline(code=dirty), final_seal=True, env=CLEAN_ENV)


# --- the L2 run record --------------------------------------------------------

def test_run_record_requires_the_baseline_seal_hash(no_finalization_block):
    run = _run_from(_baseline(), baseline_seal_sha256=None)
    assert run.stage == SEAL_STAGE_L2_RUN
    with pytest.raises(ProvenanceError, match="baseline_seal_sha256"):
        seal(run, final_seal=True, env=CLEAN_ENV)


def test_run_record_seals_once_it_names_its_baseline(no_finalization_block):
    b = _baseline()
    assert len(seal(_run_from(b), final_seal=True, env=CLEAN_ENV)) == 64


def test_run_record_may_not_mutate_the_baseline():
    b = _baseline()
    good = _run_from(b)
    assert_baseline_not_mutated(b, good)          # adding outputs is allowed

    moved = dataclasses.replace(
        good, config=ConfigProvenance({"N_target": 19}, {}))
    with pytest.raises(ProvenanceError, match="may not replace the baseline"):
        assert_baseline_not_mutated(b, moved)


def test_run_record_pointing_at_the_wrong_baseline_is_rejected():
    b = _baseline()
    wrong = dataclasses.replace(_run_from(b), baseline_seal_sha256="d" * 64)
    with pytest.raises(ProvenanceError, match="names baseline"):
        assert_baseline_not_mutated(b, wrong)


def test_a_baseline_and_a_run_over_identical_inputs_hash_differently():
    b = _baseline()
    assert _run_from(b).sealed_input_sha256 != b.sealed_input_sha256


# --- the seal critical section ------------------------------------------------

def test_head_moving_during_the_critical_section_aborts(no_finalization_block):
    """A scheduled task commits to this repository without human action."""
    guard = RepoIdentityGuard.snapshot()
    moved = dataclasses.replace(guard, expected_head="0" * 40)
    with pytest.raises(SealRaceError, match="HEAD moved"):
        seal(_baseline(), final_seal=True, env=CLEAN_ENV, guard=moved)


def test_tree_going_dirty_during_the_critical_section_aborts(no_finalization_block):
    guard = RepoIdentityGuard.snapshot()
    flipped = dataclasses.replace(guard, expected_clean=not guard.expected_clean)
    with pytest.raises(SealRaceError, match="cleanliness changed"):
        seal(_baseline(), final_seal=True, env=CLEAN_ENV, guard=flipped)


def test_normative_modules_moving_during_the_critical_section_aborts(no_finalization_block):
    guard = RepoIdentityGuard.snapshot()
    tampered = dataclasses.replace(
        guard, expected_normative_module_sha256={
            **guard.expected_normative_module_sha256,
            "core/b0_route.py": "0" * 64})
    with pytest.raises(SealRaceError, match="normative module hashes changed"):
        seal(_baseline(), final_seal=True, env=CLEAN_ENV, guard=tampered)


def test_an_unmoved_guard_permits_the_seal(no_finalization_block):
    guard = RepoIdentityGuard.snapshot()
    assert len(seal(_baseline(), final_seal=True, env=CLEAN_ENV, guard=guard)) == 64
