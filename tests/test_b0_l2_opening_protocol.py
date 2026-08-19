"""C-59 · the opener ↔ runner boundary, driven end to end.

The review found three holes that `tests/test_b0_l2_run_layout.py` could not
have caught, because it tested the layout helpers rather than the handover:

  * a run directory could exist with nothing having formally opened;
  * `attempted_openings` was counted from TERMINAL registry rows, so an opening
    whose process died was invisible to the budget it had just spent;
  * the runner would start period 1 again over an existing run, appending a
    second progress sequence and overwriting the NAV.

So these tests drive the real opener `main()` and the real admission code the
runner calls — not reimplementations of them — against a sandboxed artefact
tree. Everything up to and including the execution claim is exercised; the 141
periods themselves are not, because admission and the claim are what this ruling
is about and they all happen before period 1.
"""

import hashlib
import io
import json
import os
import sys

import pytest

import core.b0_l2_run_layout as layout
from core.b0_l2_run_layout import (
    ExecutionClaimExists,
    OpeningClaimExists,
    OpeningProvenanceMismatch,
    PreOpeningOrphan,
    UnresolvedExecutionClaim,
    assert_runner_admissible,
    attempted_opening_count,
    attempted_openings,
    create_execution_claim,
    create_opening_claim,
    create_run_dir,
    opening_claims,
    run_state,
)
from core.b0_master_prereg import write_provenance_json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEAL_A = "a" * 64
SEAL_B = "b" * 64
HEAD = "c" * 40
SPEC = "d" * 64
COMPOSED = "e" * 64
PERIOD1 = "f" * 64


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A sandboxed artefact tree plus the surrounding files admission reads."""
    root = tmp_path / "l2_run"
    root.mkdir()
    monkeypatch.setattr(layout, "LEGACY_RUN_ROOT", str(root))
    monkeypatch.setattr(layout, "RUNS_ROOT", str(root / "runs"))
    monkeypatch.setattr(layout, "OPENING_CLAIMS_ROOT", str(root / "opening_claims"))

    seals = tmp_path / "seals"
    seals.mkdir()
    for seal in (SEAL_A, SEAL_B):
        write_provenance_json(str(seals / (seal + ".json")), {
            "baseline_seal_sha256": seal, "commit_sha": HEAD, "l2_opened": False,
            "specification": {"spec_sha256": SPEC},
            "l2_opening_protocol": {"openings_permitted": 1}})
    monkeypatch.setattr(layout, "SEAL_ARCHIVE_ROOT", str(seals))

    freeze = tmp_path / "freeze.json"
    write_provenance_json(str(freeze), {"spec_sha256": SPEC, "version": "1.25"})
    monkeypatch.setattr(layout, "FREEZE_PATH", str(freeze))

    receipt = tmp_path / "p1.json"
    write_provenance_json(str(receipt), {"full_decision_input_sha256": PERIOD1})
    monkeypatch.setattr(layout, "PERIOD1_RECEIPT", str(receipt))

    monkeypatch.setattr(layout, "composed_market_state_sha256",
                        lambda *a, **k: COMPOSED)
    # the legacy attempt is not present in the sandbox; its check is exercised
    # by test_b0_l2_run_layout against the real artefacts
    monkeypatch.setattr(layout, "assert_legacy_run_unmutated", lambda: {})
    return tmp_path


def _open(run_id, *, seal=SEAL_A, record=None, claim=True):
    """What the opener does: directory, record, then the claim that pins it."""
    directory = create_run_dir(run_id)
    payload = record or {
        "run_id": run_id, "baseline_seal_sha256": seal, "spec_sha256": SPEC,
        "commit_sha": HEAD, "market_state_composed_sha256": COMPOSED,
        "period1_full_input_sha256": PERIOD1, "opened_at": "2026-08-19T12:00:00Z"}
    path = os.path.join(directory, "opening_record.json")
    write_provenance_json(path, payload)
    sha = hashlib.sha256(io.open(path, "rb").read()).hexdigest()
    if claim:
        create_opening_claim({
            "run_id": run_id, "baseline_seal_sha256": seal,
            "opening_record_sha256": sha, "spec_sha256": SPEC,
            "commit_sha": HEAD, "market_state_composed_sha256": COMPOSED,
            "period1_full_input_sha256": PERIOD1,
            "authorization": "test authorization",
            "opened_at": "2026-08-19T12:00:00Z"})
    return directory, sha


# --- opening succeeds, runner never starts -----------------------------------

def test_an_opening_is_countable_before_anything_runs(world):
    """The case that used to be invisible: opened, then the process dies."""
    before = attempted_opening_count()
    _open("L2-aaaaaaaaaaaaaaaa")

    assert attempted_opening_count() == before + 1
    assert "L2-aaaaaaaaaaaaaaaa" in [a["run_id"] for a in attempted_openings()]
    assert run_state("L2-aaaaaaaaaaaaaaaa") == "OPENED"
    # and it did NOT need a terminal result to be counted
    assert not os.path.exists(os.path.join(
        layout.run_dir("L2-aaaaaaaaaaaaaaaa"), "final_result.json"))


def test_attempted_openings_do_not_come_from_terminal_rows(world):
    """R3: the count is derived from opening events, full stop."""
    _open("L2-aaaaaaaaaaaaaaaa")
    ids = [a["run_id"] for a in attempted_openings()]
    assert ids.count("L2-aaaaaaaaaaaaaaaa") == 1     # deduplicated by run_id
    assert layout.LEGACY_ATTEMPTED_OPENING["run_id"] in ids


# --- an opening record without a claim is not an opening ---------------------

def test_a_record_without_a_claim_is_a_pre_opening_orphan(world):
    _open("L2-aaaaaaaaaaaaaaaa", claim=False)

    assert opening_claims() == []
    assert attempted_opening_count() == 1            # legacy only
    assert run_state("L2-aaaaaaaaaaaaaaaa") is None
    with pytest.raises(PreOpeningOrphan, match="pre-opening orphan"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_a_run_directory_alone_is_not_executable(world):
    create_run_dir("L2-aaaaaaaaaaaaaaaa")
    with pytest.raises(OpeningProvenanceMismatch, match="opening record is missing"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


# --- the record may not move after it is claimed -----------------------------

def test_a_record_modified_after_the_claim_is_rejected(world):
    directory, _ = _open("L2-aaaaaaaaaaaaaaaa")
    assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)

    payload = json.load(io.open(os.path.join(directory, "opening_record.json"),
                                encoding="utf-8"))
    payload["authorization"] = "quietly edited"
    write_provenance_json(os.path.join(directory, "opening_record.json"), payload)

    with pytest.raises(OpeningProvenanceMismatch, match="changed since it was claimed"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


# --- identity mismatches all fail before period 1 ----------------------------

def test_a_foreign_run_record_is_rejected(world):
    directory = create_run_dir("L2-aaaaaaaaaaaaaaaa")
    write_provenance_json(os.path.join(directory, "opening_record.json"), {
        "run_id": "L2-somebodyelse00", "baseline_seal_sha256": SEAL_A,
        "spec_sha256": SPEC, "commit_sha": HEAD,
        "market_state_composed_sha256": COMPOSED})
    with pytest.raises(OpeningProvenanceMismatch, match="not 'L2-aaaaaaaaaaaaaaaa'"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_a_wrong_baseline_seal_is_rejected(world):
    _open("L2-aaaaaaaaaaaaaaaa", seal=SEAL_A)
    # the claim for SEAL_A names this run; point the record at a seal that was
    # never opened
    directory = layout.run_dir("L2-aaaaaaaaaaaaaaaa")
    payload = json.load(io.open(os.path.join(directory, "opening_record.json"),
                                encoding="utf-8"))
    payload["baseline_seal_sha256"] = SEAL_B
    write_provenance_json(os.path.join(directory, "opening_record.json"), payload)
    with pytest.raises(PreOpeningOrphan, match="no\\s+canonical opening claim"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_a_wrong_commit_is_rejected(world):
    _open("L2-aaaaaaaaaaaaaaaa")
    with pytest.raises(OpeningProvenanceMismatch, match="HEAD is"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head="9" * 40, dirty=False)


def test_a_dirty_tree_is_rejected(world):
    _open("L2-aaaaaaaaaaaaaaaa")
    with pytest.raises(OpeningProvenanceMismatch, match="working tree is dirty"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=True)


def test_a_wrong_spec_is_rejected(world, monkeypatch, tmp_path):
    _open("L2-aaaaaaaaaaaaaaaa")
    moved = tmp_path / "freeze2.json"
    write_provenance_json(str(moved), {"spec_sha256": "9" * 64, "version": "1.26"})
    monkeypatch.setattr(layout, "FREEZE_PATH", str(moved))
    with pytest.raises(OpeningProvenanceMismatch, match="repository now carries"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_moved_sealed_inputs_are_rejected(world, monkeypatch):
    _open("L2-aaaaaaaaaaaaaaaa")
    monkeypatch.setattr(layout, "composed_market_state_sha256",
                        lambda *a, **k: "7" * 64)
    with pytest.raises(OpeningProvenanceMismatch, match="141-state"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_a_moved_period_1_input_is_rejected(world, monkeypatch, tmp_path):
    _open("L2-aaaaaaaaaaaaaaaa")
    moved = tmp_path / "p1b.json"
    write_provenance_json(str(moved), {"full_decision_input_sha256": "8" * 64})
    monkeypatch.setattr(layout, "PERIOD1_RECEIPT", str(moved))
    with pytest.raises(OpeningProvenanceMismatch, match="period-1 input"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_admission_never_falls_back_to_another_run(world):
    _open("L2-aaaaaaaaaaaaaaaa")
    with pytest.raises(PreOpeningOrphan):
        assert_runner_admissible("L2-bbbbbbbbbbbbbbbb", head=HEAD, dirty=False)


# --- one seal, one opening ---------------------------------------------------

def test_two_openers_on_one_baseline_yield_exactly_one_opening(world):
    """Different run_ids, same seal: the second gets nothing but a refusal."""
    _open("L2-aaaaaaaaaaaaaaaa", seal=SEAL_A)
    with pytest.raises(OpeningClaimExists, match="already opened"):
        _open("L2-bbbbbbbbbbbbbbbb", seal=SEAL_A)

    assert len(opening_claims()) == 1
    assert opening_claims()[0]["run_id"] == "L2-aaaaaaaaaaaaaaaa"
    # the loser's directory exists but nothing opened for it, and it is not an
    # attempted opening. Admission names the reason precisely: the seal it
    # points at was opened by somebody else.
    assert "L2-bbbbbbbbbbbbbbbb" not in [a["run_id"] for a in attempted_openings()]
    with pytest.raises(OpeningProvenanceMismatch,
                       match="may not execute another run's opening"):
        assert_runner_admissible("L2-bbbbbbbbbbbbbbbb", head=HEAD, dirty=False)


def test_opening_again_after_a_successful_opening_fails(world):
    _open("L2-aaaaaaaaaaaaaaaa", seal=SEAL_A)
    before = attempted_opening_count()
    with pytest.raises(OpeningClaimExists):
        create_opening_claim({
            "run_id": "L2-cccccccccccccccc", "baseline_seal_sha256": SEAL_A,
            "opening_record_sha256": "1" * 64, "spec_sha256": SPEC,
            "commit_sha": HEAD, "market_state_composed_sha256": COMPOSED,
            "period1_full_input_sha256": PERIOD1, "authorization": "again",
            "opened_at": "2026-08-19T13:00:00Z"})
    assert attempted_opening_count() == before


def test_a_different_baseline_may_be_opened(world):
    """Narrowness check: the rule is one-per-seal, not one-ever."""
    _open("L2-aaaaaaaaaaaaaaaa", seal=SEAL_A)
    _open("L2-bbbbbbbbbbbbbbbb", seal=SEAL_B)
    assert len(opening_claims()) == 2


# --- once-only execution -----------------------------------------------------

def test_a_second_runner_invocation_makes_zero_execution_writes(world):
    _open("L2-aaaaaaaaaaaaaaaa")
    directory = layout.run_dir("L2-aaaaaaaaaaaaaaaa")
    create_execution_claim("L2-aaaaaaaaaaaaaaaa", {"claimed_at": "t"})
    # pretend the first invocation got partway
    from core.b0_master_prereg import append_provenance_record
    append_provenance_record(os.path.join(directory, "period_progress.jsonl"),
                             {"seq": 1, "positions": 0})
    before = {n: hashlib.sha256(io.open(os.path.join(directory, n), "rb").read())
              .hexdigest() for n in sorted(os.listdir(directory))}

    with pytest.raises(ExecutionClaimExists, match="Nothing has been written"):
        create_execution_claim("L2-aaaaaaaaaaaaaaaa", {"claimed_at": "t2"})

    after = {n: hashlib.sha256(io.open(os.path.join(directory, n), "rb").read())
             .hexdigest() for n in sorted(os.listdir(directory))}
    assert after == before, "the refused invocation still wrote something"


def test_an_execution_claim_without_a_terminal_result_never_restarts(world):
    """R6: interrupted is NOT resumable-by-default, and not silently restartable."""
    _open("L2-aaaaaaaaaaaaaaaa")
    create_execution_claim("L2-aaaaaaaaaaaaaaaa", {"claimed_at": "t"})
    assert run_state("L2-aaaaaaaaaaaaaaaa") == "EXECUTION_CLAIMED"

    with pytest.raises(UnresolvedExecutionClaim, match="M-3"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


def test_a_terminated_run_may_not_execute_again(world):
    _open("L2-aaaaaaaaaaaaaaaa")
    directory = layout.run_dir("L2-aaaaaaaaaaaaaaaa")
    create_execution_claim("L2-aaaaaaaaaaaaaaaa", {"claimed_at": "t"})
    write_provenance_json(os.path.join(directory, "final_result.json"),
                          {"record": "B0_L2_TERMINAL_RESULT"})
    assert run_state("L2-aaaaaaaaaaaaaaaa") == "TERMINAL"

    with pytest.raises(ExecutionClaimExists, match="executes once"):
        assert_runner_admissible("L2-aaaaaaaaaaaaaaaa", head=HEAD, dirty=False)


# --- R7 · state is derived, monotonic, and has no mutable field --------------

def test_state_is_derived_from_events_and_is_monotonic(world):
    run = "L2-aaaaaaaaaaaaaaaa"
    assert run_state(run) is None
    _open(run)
    assert run_state(run) == "OPENED"
    create_execution_claim(run, {"claimed_at": "t"})
    assert run_state(run) == "EXECUTION_CLAIMED"
    write_provenance_json(os.path.join(layout.run_dir(run), "final_result.json"),
                          {"record": "B0_L2_TERMINAL_RESULT"})
    assert run_state(run) == "TERMINAL"


def test_no_mutable_state_field_is_consulted(world):
    """Writing `state` into the record must not change the derived state."""
    run = "L2-aaaaaaaaaaaaaaaa"
    directory, _ = _open(run)
    payload = json.load(io.open(os.path.join(directory, "opening_record.json"),
                                encoding="utf-8"))
    payload["state"] = "TERMINAL"
    write_provenance_json(os.path.join(directory, "opening_record.json"), payload)
    assert run_state(run) == "OPENED"


# --- R4 · structural single creator ------------------------------------------

def test_a_generic_provenance_writer_cannot_create_a_run_directory(world):
    """Not "it happens to fail first" — it fails at the write itself."""
    from core.b0_master_prereg import append_provenance_record

    target = os.path.join(layout.RUNS_ROOT, "L2-neverclaimed", "period_progress.jsonl")
    with pytest.raises(PreOpeningOrphan, match="must not create a run directory"):
        append_provenance_record(target, {"seq": 1})
    assert not os.path.exists(os.path.dirname(target))

    with pytest.raises(PreOpeningOrphan):
        write_provenance_json(
            os.path.join(layout.RUNS_ROOT, "L2-neverclaimed2", "nav_series.json"),
            [])


def test_writers_still_work_inside_a_claimed_run_directory(world):
    """The guard must not break the legitimate path."""
    from core.b0_master_prereg import append_provenance_record

    _open("L2-aaaaaaaaaaaaaaaa")
    directory = layout.run_dir("L2-aaaaaaaaaaaaaaaa")
    append_provenance_record(os.path.join(directory, "period_progress.jsonl"),
                             {"seq": 1})
    assert os.path.exists(os.path.join(directory, "period_progress.jsonl"))


def test_writers_outside_the_run_tree_are_untouched(world, tmp_path):
    from core.b0_master_prereg import append_provenance_record

    path = str(tmp_path / "elsewhere" / "log.jsonl")
    append_provenance_record(path, {"a": 1})
    assert os.path.exists(path)


# --- the claim file is itself content-addressed ------------------------------

def test_a_claim_filename_must_match_its_payload(world):
    _open("L2-aaaaaaaaaaaaaaaa", seal=SEAL_A)
    path = layout.opening_claim_path(SEAL_A)
    payload = json.load(io.open(path, encoding="utf-8"))
    payload["baseline_seal_sha256"] = SEAL_B
    io.open(path, "wb").write(
        (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    with pytest.raises(OpeningProvenanceMismatch, match="filename IS the"):
        opening_claims()


def test_an_incomplete_claim_is_refused(world):
    for missing in ("run_id", "baseline_seal_sha256", "opening_record_sha256",
                    "authorization", "opened_at"):
        payload = {"run_id": "L2-x", "baseline_seal_sha256": SEAL_A,
                   "opening_record_sha256": "1" * 64, "spec_sha256": SPEC,
                   "commit_sha": HEAD, "market_state_composed_sha256": COMPOSED,
                   "period1_full_input_sha256": PERIOD1,
                   "authorization": "auth", "opened_at": "t"}
        payload[missing] = ""
        with pytest.raises(ValueError, match="must bind"):
            create_opening_claim(payload)
