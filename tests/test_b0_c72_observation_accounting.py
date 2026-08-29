"""C-72 / §9.6e · accounting under a re-classified terminal, and reachability.

The governance ruling of 2026-08-29 did two things that pull in opposite
directions and must not be allowed to blur into each other:

  * it re-classified the DEFECT CLASS of `L2-af1b4d90c29b3b5f` from F-CA-B to
    F-CA-C — the terminal was mis-classified, and
  * it left the ACCOUNTING alone: the run had already formed one effective
    decision and built a 20-name portfolio, so conditions 1 and 2 of §9.6a-R2
    fail and the once-only observation is spent.

The second half is the load-bearing one. Any reconstruction block can be
narrated afterwards as "that question should never have been asked" — this case
is the proof, since C-60 alone cleared seq 2 on identical data — so an
accounting rule keyed on the LABEL would let every future block re-label its
way out and once-only would be decorative.

§9.6e-R5 then closes the third consumer of that label: the repair-kind dispatch.
It is moot for Frozen B0 for two independent reasons, the second of which has
held since v1.26 — and until this version it held only in prose, which is what
these tests exist to stop happening again.
"""

import pytest

from core.b0_declaration_conformance import (
    DECLARATION_BINDINGS,
    verify_declaration_bindings,
)
from core.b0_master_prereg import (
    FROZEN_B0_LINEAGE,
    FROZEN_B0_REOPENING_UNREACHABLE_REASONS,
    ImplementationConformanceRepair,
    L2Opening,
    L2ReopeningUnreachable,
    L2_NOT_EVALUABLE_CA_BLOCK,
    L2_RUN_INVALID_CONFORMANCE,
    MasterPreregViolation,
    assert_l2_reopening_reachable,
    assert_reopening_admissible,
    effective_observation_count,
    effective_observations,
    l2_replay_permitted,
    spec,
)

THE_CONSUMING_RUN = "L2-af1b4d90c29b3b5f"

# Deliberately not a real lineage. C-72 is scoped to Frozen B0; naming a lineage
# nobody has opened is how a test reaches the mechanism without pretending the
# ruling reaches further than it does.
OTHER_LINEAGE = "B1_LINEAGE_NOT_YET_OPENED"

OLD_SEAL = "7faad84ab88c972474780d406cb3504e039d26d416c21c62a1cd1ed7ae1c3289"
NEW_SEAL = "aea938248ef8bdee4fdb3b6fb5cade7bd58e0219a7c9dab2dda51c076dc52cee"


def _previous(outcome=L2_RUN_INVALID_CONFORMANCE):
    return L2Opening(opened_at="2026-08-19T10:03:02.603852+00:00",
                     spec_sha256="a" * 64, code_commit="3256270b",
                     data_manifest_sha256="b" * 64, outcome=outcome)


def _good_repair(**kw):
    base = dict(description="a repair that is well formed in every respect",
                frozen_semantics_reference="§6.1.7 exposure interval rule",
                semantics_frozen_before_run=True,
                changes_strategy_semantics=False,
                performance_consulted=False,
                selected_by_portfolio_exposure=False)
    base.update(kw)
    return ImplementationConformanceRepair(**base)


# --- §9.6e-R2 · the fact this whole ruling is about ---------------------------

def test_the_frozen_b0_window_was_observed_exactly_once_and_by_a_named_run():
    """A count alone is satisfied by any run at all; the identity is the claim.

    This is a regression test on a historical fact, not on a computation. If it
    ever fails, either the registry moved or something learned to retire a row
    it may not retire.
    """
    assert effective_observations() == (THE_CONSUMING_RUN,)
    assert effective_observation_count() == 1


def test_the_consuming_row_is_still_recorded_under_its_original_label():
    """C-57 keeps provenance; C-56 keeps accounting. Both, not either."""
    from core.b0_master_prereg import read_registry

    rows = {r["opened_at"]: r["outcome"] for r in read_registry()}
    assert rows["2026-08-19T10:03:02.603852+00:00"] == L2_NOT_EVALUABLE_CA_BLOCK


# --- §9.6e-R5 · unreachable, and unreachable FIRST ----------------------------

def test_the_default_lineage_is_frozen_b0_and_it_is_refused():
    """Silence is the closed case. Reaching the mechanism costs an explicit name."""
    assert l2_replay_permitted() is False
    assert l2_replay_permitted(FROZEN_B0_LINEAGE) is False
    with pytest.raises(L2ReopeningUnreachable):
        assert_l2_reopening_reachable()


def test_a_lineage_this_ruling_does_not_reach_is_unaffected():
    assert l2_replay_permitted(OTHER_LINEAGE) is True
    assert_l2_reopening_reachable(OTHER_LINEAGE)


@pytest.mark.parametrize("repair", [None, _good_repair()])
def test_no_input_combination_reopens_frozen_b0(repair):
    """Including the well-formed one.

    A gate that only fired on malformed input would leave the path open to
    anyone who filled the form in correctly, which is the reading §9.6e-R5
    forbids in as many words.
    """
    with pytest.raises(L2ReopeningUnreachable):
        assert_reopening_admissible(
            _previous(), repair,
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=NEW_SEAL,
            authorization_reference="a fresh explicit authorization")


def test_the_lineage_question_is_asked_before_every_lesser_one():
    """Order is the point, not merely the refusal.

    Here the seals are identical and the repair is the wrong kind — two lesser
    complaints that would each refuse on their own. If either spoke first, a
    caller could fix it and find the mechanism waiting behind it.
    """
    from core.b0_master_prereg import DataRepair

    with pytest.raises(L2ReopeningUnreachable):
        assert_reopening_admissible(
            _previous(), DataRepair(
                description="an independent source for a gap that does not exist",
                independent_source="TWSE bonus-share rates extended to 2012",
                scope="event_class", performance_consulted=False,
                selected_by_portfolio_exposure=False),
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=OLD_SEAL,
            authorization_reference="   ")


def test_the_two_reasons_are_recorded_and_independent():
    """Either alone closes the path; the record says so rather than implying it."""
    assert len(FROZEN_B0_REOPENING_UNREACHABLE_REASONS) == 2
    assert any("consumed" in r for r in FROZEN_B0_REOPENING_UNREACHABLE_REASONS)
    assert any("v1_26" in r for r in FROZEN_B0_REOPENING_UNREACHABLE_REASONS)


def test_the_prohibition_is_now_a_constant_and_not_only_a_header_sentence():
    """§5.1 measured that it was prose. This is the measurement, inverted."""
    assert spec("frozen_b0_l2_replay_permitted") is False
    assert spec("frozen_b0_l2_reopening_is_unreachable") is True


# --- §9.6e-R4 · re-classification is not a resurrection ritual ----------------

def _rows(tmp_path, recorded_outcome, **att_kw):
    from core.b0_master_prereg import (
        ATTESTED_CONDITIONS, NonConsumptionAttestation, record_non_consumption,
        record_opening,
    )

    opened_at, run_id = "2026-08-19T10:03:02.603852+00:00", "L2-0000000000000001"
    reg = str(tmp_path / "registry.jsonl")
    led = str(tmp_path / "nonconsumption.jsonl")
    record_opening(L2Opening(
        opened_at=opened_at, spec_sha256="a" * 64, code_commit="3256270b",
        data_manifest_sha256="b" * 64, outcome=recorded_outcome,
        detail='{"run_id": "%s"}' % run_id), reg)
    att = dict(opened_at=opened_at, run_id=run_id,
               outcome=L2_RUN_INVALID_CONFORMANCE,
               ruling="§9.6e-R1 re-classified the defect class",
               evidence="injected fixture, not a real run")
    att.update({c: True for c in ATTESTED_CONDITIONS})
    att.update(att_kw)
    record_non_consumption(NonConsumptionAttestation(**att), led)
    return reg, led, run_id


def test_an_attestation_naming_a_reclassified_class_does_not_retire_the_row(tmp_path):
    """The row is recorded F-CA-B. Re-classifying the defect does not move it."""
    reg, led, run_id = _rows(tmp_path, L2_NOT_EVALUABLE_CA_BLOCK)
    assert effective_observations(reg, led) == (run_id,)


def test_the_narrow_exemption_itself_still_works(tmp_path):
    """The other side. C-72 must not quietly delete C-56 while closing a door."""
    reg, led, _ = _rows(tmp_path, L2_RUN_INVALID_CONFORMANCE)
    assert effective_observations(reg, led) == ()


def test_denying_any_one_condition_is_refused_outright(tmp_path):
    """Seven conditions are a conjunction — and this run fails exactly this one."""
    with pytest.raises(MasterPreregViolation, match="zero_effective_decision"):
        reg, led, _ = _rows(tmp_path, L2_RUN_INVALID_CONFORMANCE,
                            zero_effective_decision_observations=False)
        effective_observations(reg, led)


# --- the bindings are registered, not merely written --------------------------

def test_the_three_c72_declarations_are_bound_and_conform():
    keys = {b.key for b in DECLARATION_BINDINGS}
    assert {"frozen_b0_l2_replay_permitted",
            "frozen_b0_l2_reopening_is_unreachable",
            "l2_reclassification_does_not_reopen_accounting"} <= keys
    assert verify_declaration_bindings() == []
