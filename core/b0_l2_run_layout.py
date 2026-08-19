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
