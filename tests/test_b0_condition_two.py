"""R1–R5 · condition 2 is a definition with a verifier behind it.

The word `information` was doing all the work and was never defined. Two readings
survived it, and they disagreed about the run in hand: `nav_series.json` exists
and holds 141 rows, so under a literal reading condition 2 was false; every one
of those rows is the sealed opening cash with no position, so under a
strategy-dependent reading it carries nothing that could only be known after a
B0 decision. Ruled in favour of the second, with the carve-out written down
instead of inferred.

The negative controls are the load-bearing part. "Constant NAV means
non-consuming" would be the wrong rule — a NAV that is flat at some value the
strategy traded its way to is strategy-outcome information — so the test is
equality with the SEALED OPENING cash, and each control below breaks exactly one
requirement.
"""

import json
import os

import pytest

from core.b0_master_prereg import (
    ARTEFACT_VERIFIED_CONDITIONS,
    CONDITION_2_DEFINITION,
    CONDITION_2_NEGATIVE_BOUNDARY,
    L2_RUN_INVALID_CONFORMANCE,
    MasterPreregViolation,
    NON_CONSUMPTION_ENFORCEMENT,
    OPENING_STATE_RESTATEMENT_REQUIREMENTS,
    STRATEGY_OUTCOME_ROW_KEYS,
    ConditionTwoContradicted,
    L2Opening,
    NonConsumptionAttestation,
    assert_non_consumption_admissible,
    assert_reopening_claim_wellformed,
    effective_observation_count,
    read_non_consumption,
    record_non_consumption,
    record_opening,
    spec,
    verify_opening_state_restatement,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_RUN = os.path.join(REPO, "artifacts", "l2_run")
OPENING_CASH = 2000000.0

OLD_SEAL = "7faad84ab88c972474780d406cb3504e039d26d416c21c62a1cd1ed7ae1c3289"
NEW_SEAL = "ab8dcbc3d87b3647bf280c9af9ac66ccd7a3d13ff7f04f7160105ea3ab5149f4"

# C-72 / Master 9.6e-R5. Frozen B0's reopening path is closed by ruling, so the
# PRODUCTION gate `assert_reopening_admissible` now refuses it before it looks
# at anything else. The tests below are about C-56's MECHANISM — R2 conditions 6
# and 7 — which the ruling leaves intact, so they call the mechanism directly:
# `assert_reopening_claim_wellformed`. They deliberately do NOT reach it by
# naming some other lineage; an unregistered lineage fails loudly, and routing a
# test around a production guard is how the guard stops meaning anything.
# The refusal itself is pinned in tests/test_b0_c72_observation_accounting.py.


def _run_dir(tmp_path, nav_rows, final=None):
    """A synthetic run directory holding exactly the rows under test."""
    d = tmp_path / "l2_run"
    d.mkdir()
    (d / "nav_series.json").write_text(
        json.dumps(nav_rows, ensure_ascii=False), encoding="utf-8")
    if final is not None:
        (d / "final_result.json").write_text(
            json.dumps(final, ensure_ascii=False), encoding="utf-8")
    return str(d)


def _restatement_rows(n=141, **overrides):
    rows = []
    for i in range(n):
        row = {"period": "2014-%02d" % (i % 12 + 1),
               "as_of": "2014-%02d-28" % (i % 12 + 1),
               "port_value": OPENING_CASH, "cash_after": OPENING_CASH,
               "positions": 0}
        rows.append(row)
    if overrides:
        rows[-1].update(overrides)
    return rows


def _att(**kw):
    base = dict(opened_at="2026-08-19T06:25:31.174494+00:00",
                run_id="L2-2520c80aa980d681",
                outcome=L2_RUN_INVALID_CONFORMANCE,
                ruling="RULING of 2026-08-19 R1/R2 + condition-2 ruling",
                evidence="141/141 periods, eligible=0 everywhere",
                zero_effective_decision_observations=True,
                no_portfolio_nav_or_performance_produced_or_viewed=True,
                defect_is_implementation_or_input_conformance=True,
                repair_independent_of_observed_performance=True,
                invalid_run_immutable=True)
    base.update(kw)
    return NonConsumptionAttestation(**base)


# --- R1 · the definition exists and says what was ruled ----------------------

def test_the_definition_is_strategy_dependent_not_file_literal():
    d = CONDITION_2_DEFINITION
    assert "strategy-dependent" in d
    assert "benchmark comparison" in d and "performance metric" in d
    assert "deterministic restatement of the sealed opening economic state" in d
    assert "is not strategy-outcome information" in d
    assert "nav_series.json" not in d, (
        "the definition must not turn on a filename; it turns on whether the "
        "content could only be known after an effective B0 decision")


def test_the_definition_is_a_registered_declaration():
    assert spec("l2_condition_2_definition") == CONDITION_2_DEFINITION
    assert spec("l2_condition_2_negative_boundary") == CONDITION_2_NEGATIVE_BOUNDARY


# --- R2 · an opening-state restatement is admissible -------------------------

def test_an_opening_state_only_restatement_is_non_consuming(tmp_path):
    """Negative control 1: 141 rows of the sealed opening state, and nothing else."""
    evidence = verify_opening_state_restatement(
        _run_dir(tmp_path, _restatement_rows()), opening_cash=OPENING_CASH)
    assert evidence["rows_checked"] == 141
    assert evidence["distinct_value_fields_observed"] == [OPENING_CASH]
    assert evidence["distinct_position_counts_observed"] == [0]
    assert evidence["requirements_verified"] == list(
        OPENING_STATE_RESTATEMENT_REQUIREMENTS)


def test_date_progression_alone_is_not_strategy_dependent(tmp_path):
    """R2: the dates advance across all 141 rows and that changes nothing."""
    rows = _restatement_rows()
    assert len({r["as_of"] for r in rows}) > 1
    verify_opening_state_restatement(_run_dir(tmp_path, rows),
                                     opening_cash=OPENING_CASH)


# --- R3 · the negative boundary ----------------------------------------------

def test_one_non_zero_position_is_consuming(tmp_path):
    """Negative control 2."""
    run = _run_dir(tmp_path, _restatement_rows(positions=1))
    with pytest.raises(ConditionTwoContradicted, match="non-empty strategy portfolio"):
        verify_opening_state_restatement(run, opening_cash=OPENING_CASH)


def test_one_strategy_dependent_nav_change_is_consuming(tmp_path):
    """Negative control 3. One row out of 141 is enough."""
    run = _run_dir(tmp_path, _restatement_rows(port_value=2000001.0))
    with pytest.raises(ConditionTwoContradicted, match="NAV that moved"):
        verify_opening_state_restatement(run, opening_cash=OPENING_CASH)


@pytest.mark.parametrize("key,value", [("period_return", 0.013),
                                       ("sharpe", 0.9),
                                       ("benchmark", "0050"),
                                       ("target_portfolio", ["2330"])])
def test_one_strategy_outcome_quantity_is_consuming(tmp_path, key, value):
    """Negative control 4: return, performance metric, benchmark, target."""
    run = _run_dir(tmp_path, _restatement_rows(**{key: value}))
    with pytest.raises(ConditionTwoContradicted, match="effective B0 decision"):
        verify_opening_state_restatement(run, opening_cash=OPENING_CASH)


def test_presence_disqualifies_even_when_the_value_is_empty(tmp_path):
    """A `sharpe` field set to null is still a record shaped by having looked."""
    run = _run_dir(tmp_path, _restatement_rows(sharpe=None))
    with pytest.raises(ConditionTwoContradicted):
        verify_opening_state_restatement(run, opening_cash=OPENING_CASH)


def test_a_constant_nav_at_the_wrong_level_is_still_consuming(tmp_path):
    """R3: do NOT generalize this into 'constant NAV means non-consumption'.

    Every row here is identical, so a constancy test would pass it. The strategy
    traded its way to this level, which is exactly what condition 2 excludes.
    """
    rows = [dict(r, port_value=2143000.0, cash_after=2143000.0)
            for r in _restatement_rows()]
    with pytest.raises(ConditionTwoContradicted, match="constancy at some other value"):
        verify_opening_state_restatement(_run_dir(tmp_path, rows),
                                         opening_cash=OPENING_CASH)


def test_a_computed_performance_flag_is_consuming(tmp_path):
    run = _run_dir(tmp_path, _restatement_rows(),
                   final={"performance_computed": True, "evidence": {}})
    with pytest.raises(ConditionTwoContradicted, match="performance_computed"):
        verify_opening_state_restatement(run, opening_cash=OPENING_CASH)


def test_a_receipt_in_the_final_record_is_consuming(tmp_path):
    run = _run_dir(tmp_path, _restatement_rows(),
                   final={"performance_computed": False,
                          "evidence": {"receipts_total": 3}})
    with pytest.raises(ConditionTwoContradicted, match="receipts_total"):
        verify_opening_state_restatement(run, opening_cash=OPENING_CASH)


# --- R5 · the attestation may not stand alone --------------------------------

def test_condition_2_is_verified_not_merely_attested():
    assert NON_CONSUMPTION_ENFORCEMENT[
        "no_portfolio_nav_or_performance_produced_or_viewed"] == \
        "attested_and_verified"
    assert ARTEFACT_VERIFIED_CONDITIONS == (
        "no_portfolio_nav_or_performance_produced_or_viewed",)


def test_the_artefacts_outvote_the_boolean(tmp_path):
    """A true attestation over contradicting rows must fail, not be believed."""
    run = _run_dir(tmp_path, _restatement_rows(positions=4))
    with pytest.raises(ConditionTwoContradicted):
        assert_non_consumption_admissible(_att(), run_dir=run)


def test_a_contradicted_run_is_not_excused_in_the_count(tmp_path):
    reg, led = str(tmp_path / "r.jsonl"), str(tmp_path / "a.jsonl")
    record_opening(L2Opening(opened_at="2026-08-19T06:25:31.174494+00:00",
                             spec_sha256="a" * 64, code_commit="c",
                             data_manifest_sha256="b" * 64,
                             outcome=L2_RUN_INVALID_CONFORMANCE), reg)
    record_non_consumption(_att(), led)
    run = _run_dir(tmp_path, _restatement_rows(port_value=2500000.0))
    with pytest.raises(ConditionTwoContradicted):
        effective_observation_count(reg, led, run_dir=run)


def test_the_reopening_gate_refuses_when_the_artefacts_are_missing(tmp_path):
    """At the gate, 'I cannot check' is not 'it checks out'."""
    from core.b0_master_prereg import ImplementationConformanceRepair

    repair = ImplementationConformanceRepair(
        description="monthly_revenue supplied 13 against a required 18",
        frozen_semantics_reference="lookback_L_months = 18",
        semantics_frozen_before_run=True, changes_strategy_semantics=False,
        performance_consulted=False, selected_by_portfolio_exposure=False)
    previous = L2Opening(opened_at="2026-08-19T06:25:31.174494+00:00",
                         spec_sha256="a" * 64, code_commit="c",
                         data_manifest_sha256="b" * 64,
                         outcome=L2_RUN_INVALID_CONFORMANCE)
    with pytest.raises(ConditionTwoContradicted, match="cannot be verified"):
        assert_reopening_claim_wellformed(
            previous, repair,
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=NEW_SEAL,
            authorization_reference="a fresh explicit authorization",
            attestation=_att(), run_dir=str(tmp_path / "absent"))


# --- R4 · the preserved run, verified rather than described -------------------

@pytest.mark.skipif(not os.path.exists(REAL_RUN), reason="run artefacts absent")
def test_the_preserved_invalid_run_satisfies_condition_2():
    evidence = verify_opening_state_restatement(REAL_RUN)
    assert evidence["sealed_opening_cash"] == OPENING_CASH
    assert evidence["distinct_value_fields_observed"] == [OPENING_CASH]
    assert evidence["distinct_position_counts_observed"] == [0]
    assert evidence["final_result_performance_computed"] is False
    assert evidence["final_result_receipts_total"] == 0
    assert evidence["final_result_positions_held_any_period"] == 0
    assert evidence["rows_checked"] == 282        # 141 nav + 141 progress


@pytest.mark.skipif(not os.path.exists(REAL_RUN), reason="run artefacts absent")
def test_the_governed_observation_is_attributable_to_exactly_one_named_run():
    """Migrated to the post-L2 governance truth, not relaxed.

    `== 1` on its own is satisfied by any run whatsoever, so the invariant that
    carries the meaning is the IDENTITY: the single effective observation of the
    Frozen B0 window belongs to the official run and to nothing else. The first,
    invalid run is excused by its attestation and must not appear.
    """
    from core.b0_l2_run_layout import attempted_opening_count
    from core.b0_master_prereg import effective_observations, read_registry

    assert len(read_registry()) == 2          # both attempts are on record
    assert len(read_non_consumption()) == 1   # one of them is excused
    assert attempted_opening_count() == 2
    assert effective_observation_count() == 1
    assert set(effective_observations()) == {"L2-af1b4d90c29b3b5f"}
    assert "L2-2520c80aa980d681" not in effective_observations()


@pytest.mark.skipif(not os.path.exists(REAL_RUN), reason="run artefacts absent")
def test_the_original_run_artefacts_were_not_rewritten():
    """R6: the runner's conservative verdict is superseded, not edited."""
    with open(os.path.join(REAL_RUN, "final_result.json"), encoding="utf-8") as fh:
        final = json.load(fh)
    assert final["l2_opening_consumed"] is True, (
        "the original record must keep the value the runner wrote; the ruling "
        "supersedes it through the attestation lineage, not by editing history")
    assert final["performance_computed"] is False
