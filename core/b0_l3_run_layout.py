"""W7B5 · one L3 run, one immutable directory.

L3 is prospective, but its provenance has the same storage hazard C-58 fixed
for L2: a global output directory lets a later run append to or overwrite an
earlier run.  The storage invariant is therefore identical, without importing
L2's once-only opening protocol:

    artifacts/l3_run/runs/<run_id>/

The run directory is claimed with one exclusive directory creation.  Readers
must name the run they are adjudicating; there is no canonical ``latest``
pointer and a missing run never falls back to another one.

This module defines layout only.  Opening claims, source receipts, checkpoints
and terminal-result schemas are separate contracts, but every one of them must
write inside the directory claimed here.
"""

from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

L3_RUN_ROOT = os.path.join(REPO_ROOT, "artifacts", "l3_run")
RUNS_ROOT = os.path.join(L3_RUN_ROOT, "runs")

CANONICAL_RUN_IDENTITY = "run_id"
LATEST_POINTER_IS_CANONICAL = False


class RunDirectoryExists(RuntimeError):
    """The run identity is already claimed.  Nothing was written."""


class RunDirectoryMissing(RuntimeError):
    """A run-scoped writer or reader named a directory no opener claimed."""


def _valid_component(value: str, what: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"a {what} is required; provenance cannot be anonymous")
    if os.path.basename(value) != value or value in (".", ".."):
        raise ValueError(
            f"{what} {value!r} is not a single path component; it could "
            f"address another run's artefacts")
    return value


def run_dir(run_id: str) -> str:
    """Return one run's path without creating or resolving anything."""
    return os.path.join(RUNS_ROOT, _valid_component(run_id, "run_id"))


def create_run_dir(run_id: str) -> str:
    """Claim a new run identity before any run artefact byte is written."""
    path = run_dir(run_id)
    os.makedirs(RUNS_ROOT, exist_ok=True)
    try:
        os.makedirs(path)  # deliberately not exist_ok: this is the claim
    except FileExistsError as exc:
        raise RunDirectoryExists(
            f"W7B5: {path} already exists. A run_id identifies exactly one "
            f"immutable L3 run; reuse, clearing, merging and cross-run append "
            f"are refused. Nothing has been written."
        ) from exc
    return path


def resolve_run_dir(run_id: str) -> str:
    """Resolve exactly the named run; never substitute ``latest`` or a peer."""
    path = run_dir(run_id)
    if not os.path.isdir(path):
        raise FileNotFoundError(
            f"no L3 run directory for {run_id!r} at {path}. A verifier must "
            f"not fall back to another run.")
    return path


def assert_run_dir_exists(run_id: str) -> str:
    """Require the opener's directory; generic writers may not create it."""
    path = run_dir(run_id)
    if not os.path.isdir(path):
        raise RunDirectoryMissing(
            f"W7B5: {path} does not exist. A run-scoped writer may not create "
            f"a run directory; only create_run_dir may claim one.")
    return path


def artefact_path(run_id: str, name: str) -> str:
    """Address one direct child of a run directory; paths cannot escape it."""
    name = _valid_component(name, "artefact name")
    return os.path.join(run_dir(run_id), name)


def assert_not_creating_run_dir(directory: str) -> None:
    """Fail if a generic writer would implicitly create an L3 run directory."""
    directory = os.path.abspath(directory)
    runs_root = os.path.abspath(RUNS_ROOT)
    if directory == runs_root or not directory.startswith(runs_root + os.sep):
        return
    if not os.path.isdir(directory):
        raise RunDirectoryMissing(
            f"W7B5: {directory} is inside the L3 run tree and does not exist. "
            f"Only create_run_dir may create a run directory.")
