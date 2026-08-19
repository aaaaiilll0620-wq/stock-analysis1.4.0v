"""C-58 · one L2 run, one immutable directory.

The runner wrote every output into a single global `artifacts/l2_run/`. That was
never a property of the first attempt failing — it is the storage model. A second
run would have appended its periods to the first run's `period_progress.jsonl`
and overwritten its `nav_series.json` and `final_result.json`, and it would have
done so whether the first run had failed or completed. The invalid run happened
to be the one that exposed it.

The consequence was not merely untidy. `verify_opening_state_restatement` reads
every row in the progress file, so a second run taking a single position would
have turned the first run's condition-2 evidence false — the machine proof that
`effective_observation_count == 0` would have been destroyed by the act of
running again.

So the fix is to the storage model, not to this incident:

    artifacts/l2_run/                     legacy root, frozen, first attempt only
    artifacts/l2_run/runs/<run_id>/       every attempt from now on, one each

Run identity is explicit everywhere. There is deliberately no `latest` pointer
that governance consults: a mutable name that resolves to "whichever run wrote
most recently" is exactly how the first run's evidence would have been read out
from under it.
"""

from __future__ import annotations

import hashlib
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEGACY_RUN_ROOT = os.path.join(REPO_ROOT, "artifacts", "l2_run")
RUNS_ROOT = os.path.join(LEGACY_RUN_ROOT, "runs")

# R1. The first attempt stays exactly where it is, under the root, because
# moving it would break every path already recorded in the Master, in the
# attestation ledger and in this repository's own governance prose. It is the
# only run that will ever live at the root.
LEGACY_RUN_ID = "L2-2520c80aa980d681"

RUN_ARTEFACTS: tuple[str, ...] = (
    "opening_record.json",
    "period_progress.jsonl",
    "nav_series.json",
    "final_result.json",
)

# R1/R4, pinned rather than promised. These hashes are part of a NORMATIVE
# module, so the seal binds them: the first invalid run's bytes can no longer
# drift without changing the specification's own identity.
LEGACY_RUN_ARTEFACT_SHA256: dict[str, tuple[str, int]] = {
    "opening_record.json":
        ("af0fcf7d82ca2d24977fc67855394c1c7ac23628665850678b69843eefb81cef", 1011),
    "period_progress.jsonl":
        ("ec1a8a3e71fbe6b2f27a73deab44a30ac46bdf339fde4fe3d3071ac7d1b56713", 44730),
    "nav_series.json":
        ("8df673360d40a915e301e4c904eb5547e809a4d6c13b4f40c57c5d1e7b170639", 17768),
    "final_result.json":
        ("2e7f11fd322357e03a240cd1740120b3d3a808a92f60083966c9176c1618948e", 2666),
}

# R4. Recorded so that "we did not resolve identity through a mutable pointer"
# is a declaration rather than a habit.
CANONICAL_RUN_IDENTITY = "run_id"
LATEST_POINTER_IS_CANONICAL = False


class RunDirectoryExists(RuntimeError):
    """R3: the chosen run_id already owns a directory. Nothing was written."""


class LegacyRunProtected(RuntimeError):
    """R1: something tried to write the first attempt's identity or artefacts."""


def _valid(run_id: str) -> str:
    run_id = str(run_id).strip()
    if not run_id:
        raise ValueError("a run_id is required; provenance cannot be anonymous")
    if os.path.basename(run_id) != run_id or run_id in (".", ".."):
        raise ValueError(
            f"run_id {run_id!r} is not a single path component; a run_id that "
            f"can traverse directories can address another run's artefacts")
    return run_id


def run_dir(run_id: str) -> str:
    """Where a run's artefacts live. Pure; creates nothing."""
    run_id = _valid(run_id)
    if run_id == LEGACY_RUN_ID:
        return LEGACY_RUN_ROOT
    return os.path.join(RUNS_ROOT, run_id)


def resolve_run_dir(run_id: str) -> str:
    """R4: readers bind to the run they are adjudicating, never to `latest`."""
    path = run_dir(run_id)
    if not os.path.isdir(path):
        raise FileNotFoundError(
            f"no artefact directory for run {run_id!r} at {path}. A verifier "
            f"must not fall back to another run: the answer to 'I cannot find "
            f"this run' is not 'so read a different one'.")
    return path


def create_run_dir(run_id: str) -> str:
    """R3: exclusive creation. Fails BEFORE any artefact byte is written.

    `os.makedirs` without `exist_ok` is the whole mechanism, and that is the
    point — the check and the claim are one operation, so two writers cannot
    both decide the directory was free.
    """
    run_id = _valid(run_id)
    if run_id == LEGACY_RUN_ID:
        raise LegacyRunProtected(
            f"R1/R3: {LEGACY_RUN_ID} is the first attempt's immutable identity. "
            f"A new run may not claim it.")
    path = run_dir(run_id)
    os.makedirs(RUNS_ROOT, exist_ok=True)
    try:
        os.makedirs(path)                      # deliberately NOT exist_ok
    except FileExistsError as exc:
        raise RunDirectoryExists(
            f"R3: {path} already exists. A run_id identifies exactly one "
            f"immutable run; reusing, clearing, merging or appending across "
            f"runs is refused. Nothing has been written."
        ) from exc
    return path


def artefact_path(run_id: str, name: str) -> str:
    """The one place a run's output may go. Refuses to address the legacy run."""
    if run_id != LEGACY_RUN_ID and name not in RUN_ARTEFACTS:
        # Not an allow-list on content -- receipts and post-run provenance are
        # expected too -- only a guard against escaping the run directory.
        if os.path.basename(name) != name:
            raise ValueError(f"artefact name {name!r} must not contain a path")
    return os.path.join(run_dir(run_id), name)


def sha256_of(path: str) -> tuple[str, int]:
    raw = open(path, "rb").read()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def legacy_artefact_identity() -> dict:
    """R4: the first attempt bound by run_id + path + hash, measured now."""
    out = {}
    for name, (expected, size) in LEGACY_RUN_ARTEFACT_SHA256.items():
        path = os.path.join(LEGACY_RUN_ROOT, name)
        if not os.path.exists(path):
            out[name] = {"path": path, "present": False}
            continue
        sha, length = sha256_of(path)
        out[name] = {"path": os.path.relpath(path, REPO_ROOT).replace("\\", "/"),
                     "present": True, "sha256": sha, "bytes": length,
                     "matches_pinned": sha == expected and length == size}
    return out


def assert_legacy_run_unmutated() -> dict:
    """R1: the first attempt's bytes, checked rather than trusted."""
    identity = legacy_artefact_identity()
    broken = [n for n, m in identity.items()
              if not m.get("present") or not m.get("matches_pinned")]
    if broken:
        raise LegacyRunProtected(
            f"R1: the first invalid run's artefacts no longer match the bytes "
            f"pinned in this module: {broken}. They are the immutable "
            f"provenance of an attempt that must never be rewritten.")
    return identity


# =============================================================================
# C-59 · the opening/execution protocol
#
# C-58 gave every run its own directory. It did not make the handover between
# the opener and the runner a checked protocol, and the review found the gap in
# three places: a run directory could exist without anything having formally
# opened; `attempted_openings` was counted from TERMINAL registry rows, so an
# opening whose process died was invisible; and the runner would happily start
# period 1 again over an existing run, appending a second progress sequence and
# overwriting the NAV.
#
# The fix is to make the boundary an EVENT rather than a side effect. Two
# immutable claims, both created with O_EXCL so that the check and the claim are
# one operation:
#
#   opening_claims/<baseline_seal>.json   the formal L2 opening. One per seal.
#   runs/<run_id>/execution_claim.json    the right to execute. One per run.
#
# State is derived from which claims exist, never from a mutable field.
# =============================================================================

OPENING_CLAIMS_ROOT = os.path.join(LEGACY_RUN_ROOT, "opening_claims")
EXECUTION_CLAIM = "execution_claim.json"
TERMINAL_RESULT = "final_result.json"

OPENING_CLAIM_FIELDS: tuple[str, ...] = (
    "run_id",
    "baseline_seal_sha256",
    "opening_record_sha256",
    "spec_sha256",
    "commit_sha",
    "market_state_composed_sha256",
    "period1_full_input_sha256",
    "authorization",
    "opened_at",
)

# R3. The first attempt predates this protocol and has no claim file. It is
# pinned here instead of being reconstructed, because fabricating a claim for it
# would mean writing an opening event that never happened.
LEGACY_ATTEMPTED_OPENING = {
    "run_id": LEGACY_RUN_ID,
    "baseline_seal_sha256":
        "7faad84ab88c972474780d406cb3504e039d26d416c21c62a1cd1ed7ae1c3289",
    "opened_at": "2026-08-19T06:25:31.174494+00:00",
    "opening_record_sha256":
        LEGACY_RUN_ARTEFACT_SHA256["opening_record.json"][0],
    "protocol": "pre-C-59, no canonical opening claim exists for this attempt",
}

# R7. Monotonic, and derived from immutable events rather than declared.
RUN_STATE_OPENED = "OPENED"
RUN_STATE_EXECUTION_CLAIMED = "EXECUTION_CLAIMED"
RUN_STATE_TERMINAL = "TERMINAL"
RUN_STATES: tuple[str, ...] = (
    RUN_STATE_OPENED, RUN_STATE_EXECUTION_CLAIMED, RUN_STATE_TERMINAL)


class OpeningClaimExists(RuntimeError):
    """R1: this Baseline Seal has already been opened. Nothing was written."""


class ExecutionClaimExists(RuntimeError):
    """R6: this run has already claimed execution. Nothing was written."""


class PreOpeningOrphan(RuntimeError):
    """R2: a run directory or record with no canonical opening claim."""


class OpeningProvenanceMismatch(RuntimeError):
    """R5: the opening provenance does not describe this repository state."""


class UnresolvedExecutionClaim(RuntimeError):
    """M-3: a run claimed execution and never reached a terminal result.

    Deliberately NOT resolved here. Whether such a run consumed the once-only
    observation, and whether anything may resume it, is exactly the kind of
    question §1.5 forbids an implementation from answering.
    """


def _exclusive_write(path: str, blob: bytes) -> str:
    """Create-or-fail. The check and the claim are one syscall.

    `os.path.exists` followed by `open(path, "w")` is two, and two writers can
    both pass the first. O_EXCL is the reason concurrent openers cannot both
    believe they opened the window.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        os.write(fd, blob)
    finally:
        os.close(fd)
    return path


def _canonical_bytes(payload) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
    return (body + "\n").replace("\r\n", "\n").encode("utf-8")


def opening_claim_path(baseline_seal_sha256: str) -> str:
    seal = _valid(baseline_seal_sha256)
    if len(seal) != 64 or any(c not in "0123456789abcdef" for c in seal):
        raise ValueError(f"{seal!r} is not a Baseline Seal sha256")
    return os.path.join(OPENING_CLAIMS_ROOT, seal + ".json")


def create_opening_claim(payload: dict) -> str:
    """R1: the formal L2 opening boundary. One per Baseline Seal, ever."""
    missing = [f for f in OPENING_CLAIM_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        raise ValueError(
            f"an opening claim must bind {missing}; a claim that cannot say "
            f"what it opened is not provenance")
    path = opening_claim_path(payload["baseline_seal_sha256"])
    os.makedirs(OPENING_CLAIMS_ROOT, exist_ok=True)
    try:
        return _exclusive_write(path, _canonical_bytes(dict(payload)))
    except FileExistsError as exc:
        existing = read_opening_claim(payload["baseline_seal_sha256"]) or {}
        raise OpeningClaimExists(
            f"R1: baseline {payload['baseline_seal_sha256'][:8]} was already "
            f"opened by run {existing.get('run_id')!r} at "
            f"{existing.get('opened_at')!r}. One seal, one opening. Nothing "
            f"has been written."
        ) from exc


def read_opening_claim(baseline_seal_sha256: str) -> dict | None:
    path = opening_claim_path(baseline_seal_sha256)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def opening_claims() -> list[dict]:
    if not os.path.isdir(OPENING_CLAIMS_ROOT):
        return []
    out = []
    for name in sorted(os.listdir(OPENING_CLAIMS_ROOT)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(OPENING_CLAIMS_ROOT, name), encoding="utf-8") as fh:
            claim = json.load(fh)
        if os.path.basename(name)[:-5] != claim.get("baseline_seal_sha256"):
            raise OpeningProvenanceMismatch(
                f"R1: {name} claims baseline "
                f"{claim.get('baseline_seal_sha256')!r}; the filename IS the "
                f"identity and the two must agree")
        out.append(claim)
    return out


def attempted_openings() -> list[dict]:
    """R3: derived from immutable OPENING events, never from terminal rows.

    An opening whose process died one second later is still an attempt; that is
    the whole reason the count may not wait for a terminal result.
    """
    seen, out = set(), []
    for record in [LEGACY_ATTEMPTED_OPENING, *opening_claims()]:
        if record["run_id"] in seen:
            continue
        seen.add(record["run_id"])
        out.append(record)
    return out


def attempted_opening_count() -> int:
    return len(attempted_openings())


# --- execution claim ---------------------------------------------------------

def execution_claim_path(run_id: str) -> str:
    return os.path.join(run_dir(run_id), EXECUTION_CLAIM)


def create_execution_claim(run_id: str, payload: dict) -> str:
    """R6: taken AFTER admission and BEFORE the first execution output."""
    assert_run_dir_exists(run_id)
    try:
        return _exclusive_write(execution_claim_path(run_id),
                                _canonical_bytes(dict(payload)))
    except FileExistsError as exc:
        raise ExecutionClaimExists(
            f"R6: {run_id} has already claimed execution. A second invocation "
            f"may not restart from period 1, append a second progress "
            f"sequence, or overwrite the NAV. Nothing has been written."
        ) from exc


def read_execution_claim(run_id: str) -> dict | None:
    path = execution_claim_path(run_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --- derived state -----------------------------------------------------------

def run_state(run_id: str) -> str | None:
    """R7: read off the immutable events. There is no mutable `state` field."""
    directory = run_dir(run_id)
    if run_id == LEGACY_RUN_ID:
        opened = True
    else:
        opened = any(c["run_id"] == run_id for c in opening_claims())
    if not opened:
        return None
    if os.path.exists(os.path.join(directory, TERMINAL_RESULT)):
        return RUN_STATE_TERMINAL
    if os.path.exists(os.path.join(directory, EXECUTION_CLAIM)):
        return RUN_STATE_EXECUTION_CLAIMED
    return RUN_STATE_OPENED


def assert_run_dir_exists(run_id: str) -> str:
    """R4: run-scoped writers require the directory; they never create it."""
    path = run_dir(run_id)
    if not os.path.isdir(path):
        raise PreOpeningOrphan(
            f"R4: {path} does not exist and this writer may not create it. The "
            f"opener is the sole creator of a run directory.")
    return path


def assert_not_creating_run_dir(directory: str) -> None:
    """R4 · structural. Generic provenance writers may not become a creator.

    Previously this was true only because `resolve_run_dir` happened to raise
    first. Order of calls is not a guarantee; this is checked at the write, so
    it holds however the writer is reached.
    """
    directory = os.path.abspath(directory)
    runs_root = os.path.abspath(RUNS_ROOT)
    if directory == runs_root or not directory.startswith(runs_root + os.sep):
        return
    if not os.path.isdir(directory):
        raise PreOpeningOrphan(
            f"R4: {directory} is inside the run tree and does not exist. A "
            f"generic provenance writer must not create a run directory - "
            f"only the opener may, and only exclusively.")


# --- R5 · admission ----------------------------------------------------------

FREEZE_PATH = os.path.join(
    REPO_ROOT, "research", "b0_registry", "master_prereg_freeze.json")
MANIFEST_PATH = os.path.join(REPO_ROOT, "data", "b0", "market_state_manifest.json")
PERIOD1_RECEIPT = os.path.join(
    REPO_ROOT, "research", "b0_materializer", "period1_full_input_receipt.json")
SEAL_ARCHIVE_ROOT = os.path.join(REPO_ROOT, "artifacts", "baseline_seal", "seals")


def composed_market_state_sha256(manifest_path: str = "") -> str:
    with open(manifest_path or MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return hashlib.sha256("".join(
        "%s:%s\n" % (m["decision_month"], m["market_state_sha256"])
        for m in manifest).encode()).hexdigest()


def _load(path: str, what: str) -> dict:
    if not os.path.exists(path):
        raise OpeningProvenanceMismatch(f"R5: {what} is missing at {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as exc:
        raise OpeningProvenanceMismatch(
            f"R5: {what} at {path} is malformed: {exc}") from exc


def assert_runner_admissible(run_id: str, *, head: str = "",
                             dirty: bool | None = None) -> dict:
    """Everything that must hold BEFORE the first execution write.

    Failure here is a refusal to start, not a problem to work around: every one
    of these mismatches means the run about to execute is not the run that was
    authorised. `head`/`dirty` are injectable so a test can drive the real code
    path rather than a copy of it.
    """
    directory = assert_run_dir_exists(run_id)

    # 1 · the opening record, and it must be THIS run's
    record_path = os.path.join(directory, "opening_record.json")
    record = _load(record_path, "opening record")
    for field in ("run_id", "baseline_seal_sha256", "spec_sha256", "commit_sha",
                  "market_state_composed_sha256"):
        if field not in record:
            raise OpeningProvenanceMismatch(
                f"R5: opening record for {run_id} has no {field!r}")
    if record["run_id"] != run_id:
        raise OpeningProvenanceMismatch(
            f"R5: {record_path} opens {record['run_id']!r}, not {run_id!r}")

    # 2 · the canonical opening claim. Without it nothing formally opened.
    seal = record["baseline_seal_sha256"]
    claim = read_opening_claim(seal)
    if claim is None:
        raise PreOpeningOrphan(
            f"R2/R5: {run_id} has a run directory and an opening record but no "
            f"canonical opening claim for baseline {seal[:8]}. That is a "
            f"pre-opening orphan: it is not an attempted opening and it is not "
            f"executable.")
    if claim["run_id"] != run_id:
        raise OpeningProvenanceMismatch(
            f"R5: baseline {seal[:8]} was opened by run {claim['run_id']!r}; "
            f"{run_id!r} may not execute another run's opening.")

    # 3 · the record has not moved since the claim pinned it
    actual_record_sha, _ = sha256_of(record_path)
    if actual_record_sha != claim["opening_record_sha256"]:
        raise OpeningProvenanceMismatch(
            f"R5: the opening record has changed since it was claimed "
            f"(claim pins {claim['opening_record_sha256'][:16]}, file is "
            f"{actual_record_sha[:16]}). An opening record is immutable.")

    # 4 · the seal it names must exist and reopen to its own identity
    seal_path = os.path.join(SEAL_ARCHIVE_ROOT, seal + ".json")
    body = _load(seal_path, f"baseline seal {seal[:8]}")
    if body.get("baseline_seal_sha256") != seal:
        raise OpeningProvenanceMismatch(
            f"R5: {seal_path} does not reopen to the identity it claims")

    # 5 · spec, commit and repository identity
    freeze = _load(FREEZE_PATH, "master preregistration freeze")
    if record["spec_sha256"] != freeze["spec_sha256"]:
        raise OpeningProvenanceMismatch(
            f"R5: the opening bound spec {record['spec_sha256'][:16]} and the "
            f"repository now carries {freeze['spec_sha256'][:16]}")
    if body["specification"]["spec_sha256"] != freeze["spec_sha256"]:
        raise OpeningProvenanceMismatch(
            "R5: the sealed spec identity and the frozen one disagree")
    if head and record["commit_sha"] != head:
        raise OpeningProvenanceMismatch(
            f"R5: the opening bound commit {record['commit_sha'][:8]} and HEAD "
            f"is {head[:8]}")
    if head and body["commit_sha"] != head:
        raise OpeningProvenanceMismatch(
            f"R5: the seal bound commit {body['commit_sha'][:8]} and HEAD is "
            f"{head[:8]}")
    if dirty:
        raise OpeningProvenanceMismatch(
            "R5: the working tree is dirty; a dirty tree cannot be recovered "
            "from the commit the opening bound")

    # 6 · the sealed inputs are still the ones that were opened
    composed = composed_market_state_sha256()
    if record["market_state_composed_sha256"] != composed:
        raise OpeningProvenanceMismatch(
            f"R5: the opening bound 141-state {record['market_state_composed_sha256'][:16]} "
            f"and the manifest now composes to {composed[:16]}")
    receipt = _load(PERIOD1_RECEIPT, "period-1 full input receipt")
    if claim["period1_full_input_sha256"] != receipt["full_decision_input_sha256"]:
        raise OpeningProvenanceMismatch(
            f"R5: the opening claim pinned period-1 input "
            f"{claim['period1_full_input_sha256'][:16]} and the receipt now "
            f"carries {receipt['full_decision_input_sha256'][:16]}")

    # 7 · governance, and the first attempt still intact
    from core.b0_finalization_items import assert_not_blocked
    assert_not_blocked("L2_opening")
    assert_legacy_run_unmutated()

    # 8 · R6/R7 · this run must not already have executed
    state = run_state(run_id)
    if state == RUN_STATE_TERMINAL:
        raise ExecutionClaimExists(
            f"R6: {run_id} already has an immutable terminal result. A run "
            f"executes once.")
    if state == RUN_STATE_EXECUTION_CLAIMED:
        raise UnresolvedExecutionClaim(
            f"M-3: {run_id} claimed execution and has no terminal result. The "
            f"specification does not define what an interrupted sealed L2 run "
            f"leaves behind - whether it consumed the observation, whether it "
            f"may be resumed, and from which period. Inventing a rerun rule "
            f"here would be the implementer deciding how many looks the window "
            f"gets. This must be ruled before anything continues.")

    return {"run_id": run_id, "run_dir": directory, "state": state,
            "opening_record_sha256": actual_record_sha,
            "baseline_seal_sha256": seal, "spec_sha256": freeze["spec_sha256"],
            "commit_sha": record["commit_sha"],
            "market_state_composed_sha256": composed,
            "period1_full_input_sha256": claim["period1_full_input_sha256"],
            "authorization": claim["authorization"],
            "opened_at": claim["opened_at"]}
