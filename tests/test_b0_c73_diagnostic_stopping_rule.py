# -*- coding: utf-8 -*-
"""C-73 · the diagnostic replay iteration contract.

The negative controls matter more than the positive ones here. A blinding rule
that cannot be shown to reject a leak, and a stop condition that cannot be shown
to refuse an incomplete run, are decoration.
"""
import json
import os

import pytest

from core.b0_diagnostic_iteration import (
    DIAGNOSTIC_OUTCOME_ROW_KEYS, HOLDINGS_KEY, OUTCOME_STREAM, POSITIONS_KEY,
    OutcomeLeak, RepairClaimExists, RepairNotAdmissible, StopConditionNotMet,
    assert_outcome_release_permitted, assert_repair_admissible,
    assert_run_blinded, assert_stop_condition, assert_stream_blinded,
    changed_files, compute_trajectory_divergence, create_repair_claim,
    holdings_fingerprint, read_outcome_series, read_repair_claim,
    resolve_cited_failure,
)

import core.b0_diagnostic_iteration as di  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two historical artefacts this contract was derived from. Both are frozen
# provenance: C-57 forbids rewriting them, so pinning facts about them is safe.
B06_PROGRESS = os.path.join(
    REPO, "artifacts", "b0_6_diagnostic", "runs",
    "B06DIAG-055dbf317d3f67ac", "period_progress.jsonl")
B07_PROGRESS = os.path.join(
    REPO, "research", "b0_7_diagnostic", "terminal_provenance",
    "period_progress.jsonl")


def _jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def _json(path, payload):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, sort_keys=True, indent=1)
    return path


def _progress_row(seq, positions=20, post="h%d", book=None, **extra):
    row = {"run_id": "R", "seq": seq, "period": "2014-%02d" % (seq % 12 + 1),
           "as_of": "2014-07-30", "positions": positions,
           "ca_applied": [], "claim_only_securities": [],
           "state_hash": "s%d" % seq, "post_state_hash": post % seq}
    if book is not None:
        row[HOLDINGS_KEY] = holdings_fingerprint(book)
    row.update(extra)
    return row


def _failure_row(seq=67, **extra):
    row = {"run_id": "R", "seq": seq, "period": "2020-01",
           "classification": "F-CA-C-or-core",
           "blocker_kind": "implementation_conformance_or_invariant",
           "error_type": "PriceObservabilityError", "error": "O-B: ...",
           "traceback": "Traceback ... core/b0_pit_observability.py line 247"}
    row.update(extra)
    return row


def _claim(**extra):
    claim = {
        "cites": {"error_type": "PriceObservabilityError", "seq": 67},
        "hypothesized_root_cause": "applicability state-domain split between "
                                   "held_securities and holding_spells",
        "falsifier": {"file": "tests/test_b0_claim_side_ca_applicability.py",
                      "test": "test_a_sub_share_claim_is_visible_to_the_ca_layer"},
        "declared_scope": ["core/b0_corporate_actions.py", "core/b0_state.py"],
        "parent_commit": "271b1106",
        "declared_at": "2026-08-29T00:00:00+00:00",
    }
    claim.update(extra)
    return claim


# --- R1 · blinding -------------------------------------------------------------

def test_a_progress_row_carrying_port_value_is_refused(tmp_path):
    path = _jsonl(str(tmp_path / "period_progress.jsonl"),
                  [_progress_row(1, port_value=2_000_000.0)])
    with pytest.raises(OutcomeLeak, match="port_value"):
        assert_stream_blinded(path)


def test_a_blinded_progress_row_passes(tmp_path):
    path = _jsonl(str(tmp_path / "period_progress.jsonl"),
                  [_progress_row(1), _progress_row(2)])
    assert assert_stream_blinded(path)["rows_checked"] == 2


def test_positions_stays_visible_by_a_named_decision():
    """R7. It is weakly outcome-bearing -- B0.6 -> B0.7 moved it 23 -> 22 at
    seq 49 -- and it is kept anyway, because it is the only divergence witness
    that survives a state-hash scope change. The trade is named, not hidden."""
    assert POSITIONS_KEY not in DIAGNOSTIC_OUTCOME_ROW_KEYS


def test_a_nested_outcome_key_is_caught(tmp_path):
    """Ledger rows come from a dataclass __dict__; nothing keeps them flat."""
    path = _jsonl(str(tmp_path / "ca_transition_ledger.jsonl"),
                  [{"run_id": "R", "detail": {"inner": [{"nav": 1.0}]}}])
    with pytest.raises(OutcomeLeak, match="nav"):
        assert_stream_blinded(path)


def test_the_real_b07_artefact_still_holds_the_leak_this_contract_exists_for():
    """Pins the defect. B0.7 recorded performance_displayed=false while its
    progress file carried port_value on all 66 rows."""
    with pytest.raises(OutcomeLeak, match="port_value"):
        assert_stream_blinded(B07_PROGRESS)


def test_the_condition_two_key_set_was_not_widened():
    """The landmine in §4(e). `verify_opening_state_restatement` raises on any
    key in STRATEGY_OUTCOME_ROW_KEYS BEFORE reaching the branch that permits
    port_value when it equals the sealed opening cash. Adding the key there
    would flip the legacy L2 run's condition 2 from PASS to FAIL and silently
    rewrite C-57's recorded evidence. C-73 owns a separate constant."""
    from core.b0_master_prereg import STRATEGY_OUTCOME_ROW_KEYS
    for key in ("port_value", "cash_after", "nav"):
        assert key not in STRATEGY_OUTCOME_ROW_KEYS, key
        assert key in DIAGNOSTIC_OUTCOME_ROW_KEYS, key


def test_condition_two_still_passes_on_the_legacy_run():
    """The other half of the same guard, measured rather than asserted."""
    from core.b0_master_prereg import verify_opening_state_restatement
    from core.b0_l2_run_layout import LEGACY_RUN_ID, run_dir
    evidence = verify_opening_state_restatement(
        run_dir=run_dir(LEGACY_RUN_ID), run_id=LEGACY_RUN_ID)
    assert evidence["rows_checked"] > 0
    assert evidence["distinct_position_counts_observed"] in ([], [0])


# --- R2/R3 · the repair claim --------------------------------------------------

def test_a_claim_is_frozen_once(tmp_path):
    run = str(tmp_path / "run"); os.makedirs(run)
    create_repair_claim(run, _claim())
    with pytest.raises(RepairClaimExists):
        create_repair_claim(run, _claim(declared_scope=["core/anything.py"]))
    assert read_repair_claim(run)["declared_scope"] == [
        "core/b0_corporate_actions.py", "core/b0_state.py"]


def test_a_repair_without_a_falsifier_is_not_a_repair(tmp_path):
    run = str(tmp_path / "run"); os.makedirs(run)
    with pytest.raises(RepairNotAdmissible, match="FAILS before"):
        create_repair_claim(run, _claim(falsifier={"file": "tests/x.py"}))


def test_a_claim_may_not_carry_an_outcome(tmp_path):
    run = str(tmp_path / "run"); os.makedirs(run)
    with pytest.raises(OutcomeLeak):
        create_repair_claim(run, _claim(port_value=2_000_000.0))


def test_a_claim_must_bind_every_field(tmp_path):
    run = str(tmp_path / "run"); os.makedirs(run)
    with pytest.raises(RepairNotAdmissible, match="hypothesized_root_cause"):
        create_repair_claim(run, _claim(hypothesized_root_cause=""))


def test_a_citation_must_resolve_to_exactly_one_row(tmp_path):
    parent = str(tmp_path / "parent"); os.makedirs(parent)
    _jsonl(os.path.join(parent, "failure_record.jsonl"),
           [_failure_row(67), _failure_row(67)])
    with pytest.raises(RepairNotAdmissible, match="resolved to 2 rows"):
        resolve_cited_failure(parent, {"error_type": "PriceObservabilityError",
                                       "seq": 67})


def test_a_completed_run_affords_no_next_iteration(tmp_path):
    """R2.1. The stop condition is not only 'you may stop' -- it is 'there is
    nothing further you may admissibly do'."""
    parent = str(tmp_path / "parent"); os.makedirs(parent)
    _jsonl(os.path.join(parent, "failure_record.jsonl"), [])
    with pytest.raises(RepairNotAdmissible, match="no failure record"):
        resolve_cited_failure(parent, {"seq": 67})


def test_an_out_of_scope_edit_is_refused(tmp_path):
    parent = str(tmp_path / "parent"); os.makedirs(parent)
    _jsonl(os.path.join(parent, "failure_record.jsonl"), [_failure_row(67)])
    run = str(tmp_path / "run"); os.makedirs(run)
    create_repair_claim(run, _claim())
    with pytest.raises(RepairNotAdmissible, match="outside the frozen"):
        assert_repair_admissible(run, parent,
                                 changed=["core/b0_decision.py"])


def test_an_in_scope_edit_with_tests_and_docs_is_admissible(tmp_path):
    parent = str(tmp_path / "parent"); os.makedirs(parent)
    _jsonl(os.path.join(parent, "failure_record.jsonl"), [_failure_row(67)])
    run = str(tmp_path / "run"); os.makedirs(run)
    create_repair_claim(run, _claim())
    out = assert_repair_admissible(run, parent, changed=[
        "core/b0_corporate_actions.py", "core/b0_state.py",
        "tests/test_b0_claim_side_ca_applicability.py",
        "docs/FrozenB0_MasterPreregistration.md"])
    assert out["admissible"] and out["cited_failure_seq"] == 67


def test_the_traceback_scope_rule_would_have_rejected_c66(tmp_path):
    """§4(d), as an executable statement rather than a claim in prose.

    B0.6 raised from core/b0_pit_observability.py; C-66 repaired
    core/b0_corporate_actions.py and core/b0_state.py and left the raising
    module untouched. A contract scoped to the traceback's files would have
    refused the most substantive repair in the lineage -- which is why C-73
    scopes on a claim frozen in advance instead.
    """
    traceback_files = {"research/b0_6_diagnostic/run_b0_6_diagnostic.py",
                       "core/b0_route.py", "core/b0_pit_observability.py"}
    c66_actually_changed = {"core/b0_corporate_actions.py", "core/b0_state.py"}
    assert not (c66_actually_changed & traceback_files)

    parent = str(tmp_path / "parent"); os.makedirs(parent)
    _jsonl(os.path.join(parent, "failure_record.jsonl"), [_failure_row(67)])
    run = str(tmp_path / "run"); os.makedirs(run)
    create_repair_claim(run, _claim())
    assert assert_repair_admissible(
        run, parent, changed=sorted(c66_actually_changed))["admissible"]


def test_changed_files_unions_the_working_tree(monkeypatch):
    """A scope rule that only reads commits is one `git stash` from meaning
    nothing."""
    import core.b0_diagnostic_iteration as di

    def fake_git(*args):
        if args[0] == "diff":
            return "core/b0_state.py\n"
        return " M core/b0_decision.py\n?? core/b0_new.py\n"

    monkeypatch.setattr(di, "_git", fake_git)
    assert di.changed_files("abc") == [
        "core/b0_decision.py", "core/b0_new.py", "core/b0_state.py"]


# --- R4 · the stop condition ---------------------------------------------------

def _completed_run(tmp_path, periods=141, failures=(), leak=False,
                   progress_rows=None):
    """The conformance stream carries `periods` rows, not three.

    It used to write three regardless, beside `{"periods_executed": 141}` --
    which is precisely the state R4 now refuses, and the reason it did not
    refuse it before was that nothing counted the stream. `progress_rows`
    overrides the count so that disagreement can still be constructed on
    purpose.
    """
    run = str(tmp_path / "run"); os.makedirs(run, exist_ok=True)
    n = periods if progress_rows is None else progress_rows
    _jsonl(os.path.join(run, "period_progress.jsonl"),
           [_progress_row(i, **({"port_value": 1.0} if leak else {}))
            for i in range(1, n + 1)])
    _jsonl(os.path.join(run, "failure_record.jsonl"), list(failures))
    _jsonl(os.path.join(run, OUTCOME_STREAM),
           [{"seq": 1, "port_value": 2_000_000.0, "cash_after": 0.0}])
    _json(os.path.join(run, "final_result.json"), {"periods_executed": periods})
    return run


def test_an_incomplete_run_has_not_stopped(tmp_path):
    with pytest.raises(StopConditionNotMet, match="periods_executed=66"):
        assert_stop_condition(_completed_run(tmp_path, periods=66))


def test_a_completed_run_with_a_recorded_failure_has_not_stopped(tmp_path):
    with pytest.raises(StopConditionNotMet, match="failure record row"):
        assert_stop_condition(_completed_run(tmp_path, failures=[_failure_row()]))


def test_a_run_that_never_terminated_has_not_stopped(tmp_path):
    run = str(tmp_path / "run"); os.makedirs(run)
    with pytest.raises(StopConditionNotMet, match="has not terminated"):
        assert_stop_condition(run)


def test_a_completed_run_that_still_leaks_has_not_stopped(tmp_path):
    """R1 is a precondition of R4, not a parallel rule."""
    with pytest.raises(OutcomeLeak):
        assert_stop_condition(_completed_run(tmp_path, leak=True))


def test_the_outcome_seal_opens_only_after_the_stop_condition(tmp_path):
    blocked = _completed_run(tmp_path / "a", periods=66)
    with pytest.raises(StopConditionNotMet):
        assert_outcome_release_permitted(blocked)
    done = _completed_run(tmp_path / "b")
    assert assert_stop_condition(done)["stop_condition_met"]
    assert read_outcome_series(done)[0]["port_value"] == 2_000_000.0


def test_the_run_blinding_sweep_covers_every_visible_artefact(tmp_path):
    """Every artefact is named, present or not.

    Reporting only what was found is what let an absent stream read as blinded:
    a run with no streams at all returned `{}` and passed R1.
    """
    run = _completed_run(tmp_path)
    result = assert_run_blinded(run)
    assert set(result) == set(di.BLINDED_ARTEFACTS)
    assert result["period_progress.jsonl"]["blinded"] is True
    assert result["failure_record.jsonl"]["blinded"] is True
    # Absent on a first iteration, and SAID to be absent rather than dropped.
    assert result["repair_claim.json"] == {
        "path": result["repair_claim.json"]["path"],
        "present": False, "checked": False}


def test_a_run_claiming_more_periods_than_its_stream_holds_has_not_stopped(
        tmp_path):
    """R4's one gated quantity may not be the one nothing counts.

    This is the exact shape the old fixture wrote: 141 claimed, three recorded.
    """
    run = _completed_run(tmp_path, progress_rows=3)
    with pytest.raises(StopConditionNotMet, match="holds 3 row"):
        assert_stop_condition(run)


def test_a_run_with_no_conformance_stream_has_not_stopped(tmp_path):
    """Deleting the stream must not make a run MORE compliant."""
    run = _completed_run(tmp_path)
    os.remove(os.path.join(run, "period_progress.jsonl"))
    with pytest.raises(StopConditionNotMet, match="does not exist"):
        assert_stop_condition(run)


# --- R5 · trajectory divergence ------------------------------------------------

def test_divergence_refuses_un_blinded_input():
    with pytest.raises(OutcomeLeak):
        compute_trajectory_divergence(B06_PROGRESS, B07_PROGRESS)


def test_divergence_finds_the_first_moved_period(tmp_path):
    a = _jsonl(str(tmp_path / "a.jsonl"), [_progress_row(i) for i in range(1, 6)])
    b = _jsonl(str(tmp_path / "b.jsonl"),
               [_progress_row(i, positions=19 if i >= 4 else 20)
                for i in range(1, 6)])
    out = compute_trajectory_divergence(a, b)
    assert out["first_positions_divergence_seq"] == 4
    assert out["state_hash_scope_changed"] is False
    assert out["post_state_hash_divergence_interpretable"] is True


def test_a_truncated_parent_does_not_read_as_no_divergence(tmp_path):
    """Only the common prefix is compared, so a null there means "the prefix
    agreed", not "the repair moved nothing"."""
    a = _jsonl(str(tmp_path / "a.jsonl"), [_progress_row(i) for i in range(1, 4)])
    b = _jsonl(str(tmp_path / "b.jsonl"), [_progress_row(i) for i in range(1, 9)])
    out = compute_trajectory_divergence(a, b)
    assert out["first_positions_divergence_seq"] is None      # prefix agrees
    assert out["compared_full_length"] is False               # and says so
    assert (out["parent_rows"], out["child_rows"]) == (3, 8)


def test_the_holdings_witness_needs_every_row_not_just_the_first(tmp_path):
    """Row 0 CARRIES it and a later row does not.

    That direction is what discriminates: deciding from `(a[0], b[0])` answers
    True and then `first_divergence` compares None against a hash at the row the
    key drops out, reporting a divergence that is an artefact of schema rather
    than of the repair. Checking every row answers False and names the fallback.
    (The mirror case -- row 0 lacking it -- is NOT a witness for this fix: both
    the old and the new rule answer False there.)
    """
    rows = [_progress_row(i, book=None if i == 3 else {"1101": 1.0})
            for i in range(1, 4)]
    a = _jsonl(str(tmp_path / "a.jsonl"), rows)
    b = _jsonl(str(tmp_path / "b.jsonl"), rows)
    out = compute_trajectory_divergence(a, b)
    assert out["holdings_hash_available"] is False
    assert out["divergence_witness"].startswith("positions")
    assert out["first_holdings_divergence_seq"] is None

    whole_a = _jsonl(str(tmp_path / "wa.jsonl"),
                     [_progress_row(i, book={"1101": 1.0}) for i in range(1, 4)])
    whole_b = _jsonl(str(tmp_path / "wb.jsonl"),
                     [_progress_row(i, book={"1101": 1.0}) for i in range(1, 4)])
    assert compute_trajectory_divergence(
        whole_a, whole_b)["holdings_hash_available"] is True


def test_an_untracked_directory_is_expanded_not_judged_as_a_path(monkeypatch):
    """`git status --porcelain` collapses an untracked directory into one entry
    and `_in_scope` compares exactly, so a correctly-declared file inside it
    would be refused as out-of-scope for a path that names no file."""
    seen = {}

    def fake_git(*args):
        if args[0] == "diff":
            return ""
        seen["status_args"] = args
        return "?? research/b0_l3_runner/\n"

    monkeypatch.setattr(di, "_git", fake_git)
    with pytest.raises(RepairNotAdmissible, match="rather than"):
        changed_files("abc")
    assert "-uall" in seen["status_args"]


def test_a_widened_state_domain_makes_hash_divergence_uninterpretable(tmp_path):
    """§1.5. B0.6 and B0.7 differ in state_hash at seq 1 while that period's
    economics are identical, because B0.7 widened what the state covers."""
    a = _jsonl(str(tmp_path / "a.jsonl"),
               [{"seq": 1, "positions": 20, "post_state_hash": "x"}])
    b = _jsonl(str(tmp_path / "b.jsonl"),
               [{"seq": 1, "positions": 20, "post_state_hash": "y",
                 "claim_only_securities": []}])
    out = compute_trajectory_divergence(a, b)
    assert out["state_hash_scope_changed"] is True
    assert out["post_state_hash_divergence_interpretable"] is False
    assert out["first_positions_divergence_seq"] is None


def test_the_b06_to_b07_divergence_is_what_c66_never_recorded(tmp_path):
    """The measurement R5 exists to produce, pinned against the real lineage.

    C-66 is described as repairing a 2020-01 block. It moved `positions` at
    seq 49. Nothing in B0.7's artefacts says so.
    """
    def blind(src, dst):
        rows = []
        for line in open(src, encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                rows.append({k: v for k, v in row.items()
                             if k.lower() not in DIAGNOSTIC_OUTCOME_ROW_KEYS})
        return _jsonl(dst, rows)

    out = compute_trajectory_divergence(
        blind(B06_PROGRESS, str(tmp_path / "b6.jsonl")),
        blind(B07_PROGRESS, str(tmp_path / "b7.jsonl")))
    assert out["compared_prefix_length"] == 66
    assert out["state_hash_scope_changed"] is True
    assert out["first_positions_divergence_seq"] == 49
    assert out["first_post_state_hash_divergence_seq"] == 2
    assert out["post_state_hash_divergence_interpretable"] is False
    # And the reason R5 gained a third witness: on these two runs it has only
    # the lagging one. The economics moved at seq 12; `positions` said 49 and
    # the state hash was unreadable. Runs predating C-73 cannot be re-measured.
    assert out["holdings_hash_available"] is False
    assert out["first_holdings_divergence_seq"] is None
    assert "lagging" in out["divergence_witness"]


# --- R5 · the scope-stable witness ---------------------------------------------

def test_the_holdings_fingerprint_ignores_order_and_empty_lots():
    """A security that left the book and one that was never in it are the same
    portfolio; a fingerprint that disagreed would report a phantom divergence."""
    assert holdings_fingerprint({"2330": 10, "1101": 5}) == \
        holdings_fingerprint({"1101": 5, "2330": 10})
    assert holdings_fingerprint({"2330": 10, "1101": 0}) == \
        holdings_fingerprint({"2330": 10})
    assert holdings_fingerprint({"2330": 10}) != holdings_fingerprint({"2330": 11})


def test_the_holdings_hash_is_not_an_outcome_key():
    """It is strictly more blind than the count it supplements: one bit, and no
    selection can be read back out of it."""
    assert HOLDINGS_KEY not in DIAGNOSTIC_OUTCOME_ROW_KEYS


def test_a_swap_that_leaves_the_count_flat_still_moves_the_hash(tmp_path):
    """The exact gap `positions` cannot see: 20 names become 20 other names."""
    a = _jsonl(str(tmp_path / "a.jsonl"),
               [_progress_row(i, book={"2330": 10, "1101": 5})
                for i in range(1, 6)])
    b = _jsonl(str(tmp_path / "b.jsonl"),
               [_progress_row(i, book=({"2330": 10, "2454": 5} if i >= 3
                                       else {"2330": 10, "1101": 5}))
                for i in range(1, 6)])
    out = compute_trajectory_divergence(a, b)
    assert out["holdings_hash_available"] is True
    assert out["first_holdings_divergence_seq"] == 3
    assert out["first_positions_divergence_seq"] is None
    assert out["divergence_witness"] == "holdings_hash"


def test_the_witness_says_which_one_it_used(tmp_path):
    """A null from a witness the run never carried is not 'no divergence'."""
    a = _jsonl(str(tmp_path / "a.jsonl"), [_progress_row(1)])
    b = _jsonl(str(tmp_path / "b.jsonl"), [_progress_row(1)])
    out = compute_trajectory_divergence(a, b)
    assert out["holdings_hash_available"] is False
    assert out["first_holdings_divergence_seq"] is None
    assert "lagging" in out["divergence_witness"]
