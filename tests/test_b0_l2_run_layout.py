"""C-58 · cross-run isolation. One run, one immutable directory.

The runner wrote everything into a single global `artifacts/l2_run/`. It would
have appended a second run's periods to the first run's `period_progress.jsonl`
and overwritten its NAV and final result — and it would have done that whether
the first run had failed or completed. The invalid run is the one that exposed
it, not the reason it existed.

That is why the isolation tests below run against BOTH kinds of prior run: an
invalid prior run that produced nothing, and a generic completed prior run
holding positions and returns. A fix that only protects the invalid run would
pass the first and fail the second, which is the difference between repairing
the storage model and patching this incident.
"""

import hashlib
import io
import json
import os

import pytest

import core.b0_l2_run_layout as layout
from core.b0_l2_run_layout import (
    LEGACY_RUN_ARTEFACT_SHA256,
    LEGACY_RUN_ID,
    RUN_ARTEFACTS,
    LegacyRunProtected,
    RunDirectoryExists,
    assert_legacy_run_unmutated,
    create_run_dir,
    resolve_run_dir,
    run_dir,
)
from core.b0_master_prereg import (
    ConditionTwoContradicted,
    append_provenance_record,
    spec,
    verify_opening_state_restatement,
    write_provenance_json,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASH = 2000000.0


def _sha(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def _snapshot(directory):
    return {name: _sha(os.path.join(directory, name))
            for name in sorted(os.listdir(directory))
            if os.path.isfile(os.path.join(directory, name))}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A private artefact root, so no test can touch the real provenance."""
    root = tmp_path / "l2_run"
    root.mkdir()
    monkeypatch.setattr(layout, "LEGACY_RUN_ROOT", str(root))
    monkeypatch.setattr(layout, "RUNS_ROOT", str(root / "runs"))
    return str(root)


def _write_run(directory, *, positions, port_values):
    """A prior run's four artefacts, at whatever economic state is asked for."""
    os.makedirs(directory, exist_ok=True)
    nav = [{"period": "2014-%02d" % (i % 12 + 1), "as_of": "2014-%02d-28" % (i % 12 + 1),
            "port_value": port_values[i], "cash_after": port_values[i],
            "positions": positions[i]} for i in range(len(positions))]
    write_provenance_json(os.path.join(directory, "nav_series.json"), nav)
    for i, p in enumerate(positions):
        append_provenance_record(
            os.path.join(directory, "period_progress.jsonl"),
            {"seq": i + 1, "period": nav[i]["period"], "as_of": nav[i]["as_of"],
             "port_value": port_values[i], "positions": p})
    write_provenance_json(os.path.join(directory, "opening_record.json"),
                          {"run_id": os.path.basename(directory)})
    write_provenance_json(os.path.join(directory, "final_result.json"),
                          {"performance_computed": False, "evidence": {},
                           "run_id": os.path.basename(directory)})


def _invalid_prior_run(directory, n=141):
    """What actually happened: 141 restatements of the opening state."""
    _write_run(directory, positions=[0] * n, port_values=[CASH] * n)


def _completed_prior_run(directory, n=141):
    """The case the fix must also cover: a run that held things and moved."""
    _write_run(directory, positions=[20] * n,
               port_values=[CASH * (1.0 + 0.004 * i) for i in range(n)])


PRIOR_RUNS = {"invalid": _invalid_prior_run, "completed": _completed_prior_run}


# --- R5 · run B must not disturb one byte of run A ---------------------------

@pytest.mark.parametrize("kind", sorted(PRIOR_RUNS))
def test_writing_run_b_leaves_every_byte_of_run_a_identical(sandbox, kind):
    a = create_run_dir("L2-aaaaaaaaaaaaaaaa")
    PRIOR_RUNS[kind](a)
    before = _snapshot(a)
    assert len(before) == len(RUN_ARTEFACTS)

    b = create_run_dir("L2-bbbbbbbbbbbbbbbb")
    _completed_prior_run(b)

    assert _snapshot(a) == before, (
        "run B changed run A's bytes; this is the defect, not a symptom of it")


@pytest.mark.parametrize("kind", sorted(PRIOR_RUNS))
def test_run_b_progress_does_not_append_to_run_a(sandbox, kind):
    a = create_run_dir("L2-aaaaaaaaaaaaaaaa")
    PRIOR_RUNS[kind](a, n=141)
    rows_a = io.open(os.path.join(a, "period_progress.jsonl"),
                     encoding="utf-8").read().count("\n")

    b = create_run_dir("L2-bbbbbbbbbbbbbbbb")
    _completed_prior_run(b, n=7)

    assert io.open(os.path.join(a, "period_progress.jsonl"),
                   encoding="utf-8").read().count("\n") == rows_a == 141
    assert io.open(os.path.join(b, "period_progress.jsonl"),
                   encoding="utf-8").read().count("\n") == 7


@pytest.mark.parametrize("artefact", ["nav_series.json", "final_result.json"])
@pytest.mark.parametrize("kind", sorted(PRIOR_RUNS))
def test_run_b_does_not_replace_run_a_artefacts(sandbox, kind, artefact):
    a = create_run_dir("L2-aaaaaaaaaaaaaaaa")
    PRIOR_RUNS[kind](a)
    before = _sha(os.path.join(a, artefact))

    b = create_run_dir("L2-bbbbbbbbbbbbbbbb")
    _completed_prior_run(b, n=3)

    assert _sha(os.path.join(a, artefact)) == before, "run A was replaced"
    assert _sha(os.path.join(b, artefact)) != before, (
        "run B wrote content indistinguishable from run A's, so this test "
        "would pass even if B had written into A's directory")


def test_two_runs_have_independent_files(sandbox):
    a = create_run_dir("L2-aaaaaaaaaaaaaaaa")
    b = create_run_dir("L2-bbbbbbbbbbbbbbbb")
    assert os.path.realpath(a) != os.path.realpath(b)
    _invalid_prior_run(a)
    _completed_prior_run(b)
    for name in RUN_ARTEFACTS:
        assert os.path.exists(os.path.join(a, name))
        assert os.path.exists(os.path.join(b, name))


# --- R3 · reuse fails BEFORE anything is written -----------------------------

@pytest.mark.parametrize("kind", sorted(PRIOR_RUNS))
def test_reusing_a_run_id_fails_before_any_artefact_mutation(sandbox, kind):
    a = create_run_dir("L2-aaaaaaaaaaaaaaaa")
    PRIOR_RUNS[kind](a)
    before = _snapshot(a)

    with pytest.raises(RunDirectoryExists, match="Nothing has been written"):
        create_run_dir("L2-aaaaaaaaaaaaaaaa")

    assert _snapshot(a) == before


def test_a_new_run_may_not_claim_the_legacy_identity(sandbox):
    with pytest.raises(LegacyRunProtected, match="immutable identity"):
        create_run_dir(LEGACY_RUN_ID)


def test_a_run_id_may_not_traverse_out_of_its_directory(sandbox):
    for bad in ("../elsewhere", "a/b", "..", ""):
        with pytest.raises(ValueError):
            create_run_dir(bad)


# --- R4 · readers bind to the run they are adjudicating ----------------------

def test_a_verifier_never_substitutes_another_run(sandbox):
    """The legacy run's condition 2 must survive a later run that held positions."""
    legacy = sandbox
    _invalid_prior_run(legacy)
    later = create_run_dir("L2-bbbbbbbbbbbbbbbb")
    _completed_prior_run(later)

    evidence = verify_opening_state_restatement(run_id=LEGACY_RUN_ID,
                                                opening_cash=CASH)
    assert evidence["run_id"] == LEGACY_RUN_ID
    assert evidence["distinct_position_counts_observed"] == [0]

    with pytest.raises(ConditionTwoContradicted):
        verify_opening_state_restatement(run_id="L2-bbbbbbbbbbbbbbbb",
                                         opening_cash=CASH)


def test_verification_without_a_named_run_is_refused():
    from core.b0_master_prereg import UnspecifiedBehaviour

    with pytest.raises(UnspecifiedBehaviour, match="NAMED run"):
        verify_opening_state_restatement()


def test_a_missing_run_does_not_fall_back(sandbox):
    with pytest.raises(FileNotFoundError, match="must not fall back"):
        resolve_run_dir("L2-nonexistent")


def test_the_latest_pointer_is_declared_non_canonical():
    assert spec("l2_canonical_run_identity") == "run_id"
    assert spec("l2_latest_pointer_is_canonical") is False


# --- R1 · the first attempt, pinned rather than promised ---------------------

def test_the_legacy_run_artefacts_still_match_the_pinned_bytes():
    identity = assert_legacy_run_unmutated()
    for name, (sha, size) in LEGACY_RUN_ARTEFACT_SHA256.items():
        assert identity[name]["sha256"] == sha
        assert identity[name]["bytes"] == size


def test_the_legacy_run_stays_at_the_root(sandbox):
    """R1: preserved IN PLACE. Moving it would break every recorded path."""
    assert run_dir(LEGACY_RUN_ID) == layout.LEGACY_RUN_ROOT
    assert run_dir("L2-other").startswith(layout.RUNS_ROOT)


def test_a_mutated_legacy_artefact_is_detected(sandbox, monkeypatch):
    """Negative control: the pin is a check, not a comment."""
    _invalid_prior_run(sandbox)          # right shape, wrong bytes
    with pytest.raises(LegacyRunProtected, match="no longer match"):
        assert_legacy_run_unmutated()
