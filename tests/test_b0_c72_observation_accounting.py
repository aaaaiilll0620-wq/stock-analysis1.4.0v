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
    REGISTERED_L2_LINEAGES,
    DataRepair,
    ImplementationConformanceRepair,
    L2Opening,
    L2ReopeningUnreachable,
    L2_NOT_EVALUABLE_CA_BLOCK,
    L2_RUN_INVALID_CONFORMANCE,
    MasterPreregViolation,
    UnregisteredLineage,
    assert_l2_reopening_reachable,
    assert_reopening_admissible,
    assert_reopening_claim_wellformed,
    effective_observation_count,
    effective_observations,
    l2_replay_permitted,
    spec,
)

THE_CONSUMING_RUN = "L2-af1b4d90c29b3b5f"

# Names that are NOT registered lineages. Every one of them must fail loudly.
# `FROZEN_BO` is the important one: an O for a zero, and under a fail-open
# register it walks straight past the gate.
# Names nobody has ruled on. "B1" was here until 2026-09-03, when B1 was
# registered; a registered name in this tuple is a probe of nothing, and the
# test below would have kept passing while silently testing one case fewer.
# `test_the_unregistered_probes_are_actually_unregistered` now makes that
# impossible to miss.
UNREGISTERED = ("FROZEN_BO", "B2", "B1_LINEAGE_NOT_YET_OPENED", "frozen_b0",
                "b1", "")

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


@pytest.mark.parametrize("name", UNREGISTERED)
def test_an_unregistered_lineage_fails_loudly_rather_than_being_admitted(name):
    """Fail-open here would make the whole ruling bypassable by a typo.

    "C-72 does not govern a new lineage" is not "any unknown string is
    admitted". A lineage nobody has ruled on has no replay disposition to read.
    """
    with pytest.raises(UnregisteredLineage):
        l2_replay_permitted(name)
    with pytest.raises(UnregisteredLineage):
        assert_l2_reopening_reachable(name)


def test_the_register_is_exhaustive_and_says_which_budgets_are_spent():
    """The register is a statement about BUDGETS, not about permissions.

    Frozen B0 is False because its one effective observation is spent. B1,
    registered 2026-09-03 under authority `aaaai`, is True because it has opened
    nothing, run nothing and scored nothing. Pinned exhaustively: a lineage that
    appears here without a ruling is exactly what the register exists to
    prevent.
    """
    assert dict(REGISTERED_L2_LINEAGES) == {FROZEN_B0_LINEAGE: False,
                                            "B1": True}


def test_the_unregistered_probes_are_actually_unregistered():
    """Registering a lineage must BREAK this, loudly, at the line to edit.

    "B1" sat in UNREGISTERED after B1 was registered and turned a refusal probe
    into a no-op. The failure mode is not that a test goes red; it is that a
    test stays green while checking less than it says.
    """
    overlap = set(REGISTERED_L2_LINEAGES) & set(UNREGISTERED)
    assert not overlap, (
        "%s is registered and can no longer probe the unregistered-lineage "
        "refusal. Replace it with a name nobody has ruled on - do not just "
        "delete it, or the refusal loses a case." % sorted(overlap))


def test_the_c56_mechanism_is_reached_by_calling_it_not_by_naming_a_lineage():
    """C-72 closes a door; it must not delete C-56 on the way past.

    The mechanism is exercised on a terminal outside the non-consuming set, so
    the seal comparison, the repair-kind dispatch and the named authorization
    are all live without depending on a real run's artefacts.
    """
    assert_reopening_claim_wellformed(
        L2Opening(opened_at="2026-08-19T10:03:02.603852+00:00",
                  spec_sha256="a" * 64, code_commit="3256270b",
                  data_manifest_sha256="b" * 64,
                  outcome=L2_NOT_EVALUABLE_CA_BLOCK),
        DataRepair(description="an independent source closes a real gap",
                   independent_source="an exchange export nobody has read yet",
                   scope="event_class", performance_consulted=False,
                   selected_by_portfolio_exposure=False),
        previous_baseline_seal_sha256=OLD_SEAL,
        new_baseline_seal_sha256=NEW_SEAL,
        authorization_reference="a fresh explicit authorization")

    # And it is still a gate, not a rubber stamp: same call, same seal twice.
    with pytest.raises(MasterPreregViolation, match="requires a NEW Baseline Seal"):
        assert_reopening_claim_wellformed(
            L2Opening(opened_at="2026-08-19T10:03:02.603852+00:00",
                      spec_sha256="a" * 64, code_commit="3256270b",
                      data_manifest_sha256="b" * 64,
                      outcome=L2_NOT_EVALUABLE_CA_BLOCK),
            DataRepair(description="an independent source closes a real gap",
                       independent_source="an exchange export nobody has read yet",
                       scope="event_class", performance_consulted=False,
                       selected_by_portfolio_exposure=False),
            previous_baseline_seal_sha256=OLD_SEAL,
            new_baseline_seal_sha256=OLD_SEAL,
            authorization_reference="a fresh explicit authorization")


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

def test_the_four_c72_declarations_are_bound_and_conform():
    keys = {b.key for b in DECLARATION_BINDINGS}
    assert {"frozen_b0_l2_replay_permitted",
            "frozen_b0_l2_reopening_is_unreachable",
            "l2_opening_entry_points_ask_the_gate",
            "l2_reclassification_does_not_reopen_accounting"} <= keys
    assert verify_declaration_bindings() == []


# --- the boundary, not the API · entry-layer integration ----------------------
#
# The first attempt at C-72 wired the guard into `assert_reopening_admissible`
# and stopped there. `scripts/b0_open_l2.py` — which claims the run directory
# and writes the opening claim, and is therefore where an opening ACTUALLY
# happens — never called it, and `scripts/b0_baseline_seal.py` recorded
# `effective_observations_to_date` into its manifest without refusing to seal.
# Testing the core function proved nothing about the boundary, so these tests
# run the real scripts as subprocesses and then check the filesystem.

import os                                                       # noqa: E402
import subprocess                                               # noqa: E402
import sys                                                      # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L2_RUN_ROOT = os.path.join(REPO, "artifacts", "l2_run")


def _tree(root):
    """Every path under `root`, so 'nothing was created' is a measurement."""
    if not os.path.isdir(root):
        return frozenset()
    return frozenset(
        os.path.join(dirpath, name)
        for dirpath, dirnames, filenames in os.walk(root)
        for name in list(dirnames) + list(filenames))


def _run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join("scripts", script), *args],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace")


@pytest.mark.parametrize("extra", [(), ("--dry-run",)])
def test_the_opener_refuses_and_creates_nothing(extra):
    """--dry-run is not exempt: it would print that an opening is available."""
    before = _tree(L2_RUN_ROOT)
    proc = _run("b0_open_l2.py",
                "--seal", "7faad84ab88c972474780d406cb3504e039d26d416c21c62a1cd1ed7ae1c3289",
                "--authorization", "a fresh explicit authorization", *extra)
    assert proc.returncode != 0, proc.stdout
    assert "9.6e-R5" in proc.stdout + proc.stderr
    assert _tree(L2_RUN_ROOT) == before, "the opener created something"


def test_the_opener_refuses_before_it_looks_at_the_seal_at_all():
    """Order again. A bogus seal must not be what stops it.

    If the seal lookup spoke first, the refusal would be about a missing file,
    and someone holding a real seal would find the boundary open behind it.
    """
    proc = _run("b0_open_l2.py", "--seal", "not-a-seal",
                "--authorization", "x", "--dry-run")
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "9.6e-R5" in out
    assert "no archived seal" not in out


BASELINE_SEAL_DIR = os.path.join(REPO, "artifacts", "baseline_seal")


def test_the_baseline_sealer_refuses_to_take_a_new_seal():
    """R2 condition 6 is not an entrance. A seal taken is already a fact."""
    before = _tree(BASELINE_SEAL_DIR)
    proc = _run("b0_baseline_seal.py")
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "abort: Master 9.6e-R5" in out
    assert _tree(BASELINE_SEAL_DIR) == before, "the sealer wrote something"


def _require_clean_tree(why):
    """Fail loudly on a dirty tree rather than quietly dropping an assertion.

    A skip here would be the same defect in a politer form: the one situation
    in which this precondition fails — someone mid-edit — is the situation in
    which the success assertion would stop running, so "the audit still works"
    would be untested exactly when it is most likely to have broken.

    An isolated `git worktree` would remove the precondition entirely and was
    considered. It does not work here: `data/b0/` is UNTRACKED (`git ls-files
    data/b0` is empty), so a fresh worktree has no sealed corpus to assemble and
    the audit would fail for a reason that has nothing to do with C-72. Pinned
    here so the next reader does not rediscover it as a mystery.
    """
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0:
        pytest.fail("git is unavailable, so the precondition cannot be "
                    "established: %s" % proc.stderr.strip())
    if proc.stdout.strip():
        pytest.fail(
            "%s, and the working tree is dirty. The sealer's own clean-tree "
            "rule (C-47) would abort the audit for that reason, so the "
            "assertion below could not mean what it says. Commit or stash "
            "first - this is a precondition, not a failure of the code under "
            "test.\nDirty:\n%s"
            % (why, "\n".join(proc.stdout.strip().splitlines()[:10])))


def test_the_read_only_seal_audit_survives_the_closure():
    """Closing the reopening path does not license deleting an audit.

    `--dry-run` assembles and validates and writes nothing, which is useful
    precisely BECAUSE the window is closed. Three things are asserted, and the
    exit code is one of them: §9.6e promises this mode still ASSEMBLES AND
    VALIDATES, and without that assertion the audit could start aborting for
    some unrelated reason and this test would stay green.
    """
    _require_clean_tree("this test asserts the read-only seal audit SUCCEEDS")

    before = _tree(BASELINE_SEAL_DIR)
    proc = _run("b0_baseline_seal.py", "--dry-run")
    out = proc.stdout + proc.stderr
    assert "abort: Master 9.6e-R5" not in out, (
        "the read-only audit was refused as if it were taking a seal")
    assert "UNREACHABLE" in out and "READ-ONLY audit" in out, out[:2000]
    assert proc.returncode == 0, out
    assert "record NOT written" in out, out[-2000:]
    assert _tree(BASELINE_SEAL_DIR) == before, "the audit wrote something"


def test_the_two_dry_runs_are_treated_differently_on_purpose():
    """The opener's dry run is refused; the sealer's is not.

    Same flag, opposite answers, because they do different things: one prints a
    record asserting an opening is available (wrong), the other validates a
    corpus and writes nothing (still true).
    """
    opener = _run("b0_open_l2.py", "--seal", "0" * 64,
                  "--authorization", "x", "--dry-run")
    sealer = _run("b0_baseline_seal.py", "--dry-run")
    assert "abort: Master 9.6e-R5" in opener.stdout + opener.stderr
    assert "abort: Master 9.6e-R5" not in sealer.stdout + sealer.stderr


def test_the_entry_point_binding_actually_bites(monkeypatch):
    """A check that cannot fail is not a check.

    Pointed at a real script that does NOT call the guard — the adjudication
    tool, which has no business opening anything — the binding must raise. No
    file is created and no source is edited: the negative control is a path
    substitution.
    """
    from core import b0_declaration_conformance as conform

    monkeypatch.setattr(conform, "L2_OPENING_ENTRY_POINTS",
                        ("scripts/b0_adjudicate_l2_run.py",))
    with pytest.raises(conform.DeclarationConformanceError, match="does not"):
        conform._conform_l2_opening_entry_points_ask_the_gate()

    monkeypatch.setattr(conform, "L2_OPENING_ENTRY_POINTS",
                        ("scripts/there_is_no_such_script.py",))
    with pytest.raises(conform.DeclarationConformanceError, match="does not exist"):
        conform._conform_l2_opening_entry_points_ask_the_gate()


def test_both_entry_points_are_bound_by_a_declaration():
    """So that deleting the call is a conformance failure, not a silent regress."""
    from core.b0_declaration_conformance import L2_OPENING_ENTRY_POINTS

    assert set(L2_OPENING_ENTRY_POINTS) == {
        "scripts/b0_open_l2.py", "scripts/b0_baseline_seal.py"}
    assert spec("l2_opening_entry_points_ask_the_gate") is True
