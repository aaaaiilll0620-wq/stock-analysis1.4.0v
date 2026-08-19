# -*- coding: utf-8 -*-
"""Frozen B0.1 diagnostic-run closure. R1 of the B0.2 authorization.

The B0.1 RETROSPECTIVE DIAGNOSTIC REPLAY (`B01DIAG-0121b3261805b826`) terminated
at 2/141 with `DIAGNOSTIC_RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE`. That
terminal state is ACCEPTED AND IMMUTABLE: it is the evidence that motivates B0.2,
and B0.2 must not be able to quietly rewrite the record that justifies it.

Its live artefacts live under `artifacts/b0_1_diagnostic/`, which is gitignored --
the same situation as the first invalid L2 run, and the reason
`b0_l2_run_layout.LEGACY_RUN_ARTEFACT_SHA256` exists. This module applies that
precedent to B0.1 and adds one thing the L2 case did not have: a byte-identical
VERSIONED copy under `research/b0_1_diagnostic/terminal_provenance/`, so the
provenance survives a machine, not only a working directory.

Both copies are pinned. `assert_b0_1_diagnostic_unmutated()` checks the versioned
copy unconditionally and the live copy when it is present, so a developer without
the original `artifacts/` tree still gets the guarantee.

THE HISTORICAL B0.1 BASELINE IS NOT THIS COMMIT. B0.1 is `e708fdb7` /
`4d17505d...`; the closure commit that adds this file comes AFTER the diagnostic
run and must never be presented as the B0.1 baseline.
"""
from __future__ import annotations

import hashlib
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- the historical B0.1 identity, which a later closure commit does not move ---
B0_1_BASELINE_SEAL_SHA256 = (
    "4d17505d3800b04c2f7cb867492038bd2d260b50b3b8fb9f99413a6da812c037")
B0_1_BOUND_COMMIT = "e708fdb7cb03718dc4179243ff2c7c502c72ea36"
B0_1_SPEC_SHA256 = (
    "6f452ea23406ac52a5547c32bb1285f4284dd07a83503ee865e88eb9b1145a15")
B0_1_MASTER_VERSION = "1.26"

# --- the diagnostic run itself ------------------------------------------------
B0_1_DIAGNOSTIC_RUN_ID = "B01DIAG-0121b3261805b826"
B0_1_DIAGNOSTIC_RUN_KIND = "B0_1_RETROSPECTIVE_DIAGNOSTIC"
B0_1_DIAGNOSTIC_EVIDENCE_CLASS = "RETROSPECTIVE_SUPPORTING_ONLY"
B0_1_DIAGNOSTIC_TERMINAL_STATUS = (
    "DIAGNOSTIC_RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE")
B0_1_DIAGNOSTIC_PERIODS_EXECUTED = 2
B0_1_DIAGNOSTIC_PERIODS_REQUIRED = 141
B0_1_DIAGNOSTIC_PERFORMANCE_COMPUTED = False

# The harness bytes that produced the run. Preserved exactly; B0.2 gets its own
# runner rather than editing this one.
B0_1_HARNESS = "research/b0_1_diagnostic/run_b0_1_diagnostic.py"
B0_1_HARNESS_SHA256 = ("baed30dc8c0799c2766286746acb73cde7457f3de301f8b00584bb312dda09d0", 25736)

VERSIONED_PROVENANCE_DIR = "research/b0_1_diagnostic/terminal_provenance"
LIVE_RUN_DIR = "artifacts/b0_1_diagnostic/runs/" + B0_1_DIAGNOSTIC_RUN_ID
LIVE_CLAIM = ("artifacts/b0_1_diagnostic/run_claims/%s.json"
              % B0_1_DIAGNOSTIC_RUN_ID)

# {versioned filename: (sha256, bytes)}
B0_1_DIAGNOSTIC_ARTEFACT_SHA256: dict[str, tuple[str, int]] = {
    "ca_transition_ledger.jsonl":    ("5b79345fc26a2b86a675a9b39eabf81f30bdb581aa7a305731c4876bbb90f0e2", 2725),
    "failure_record.jsonl":          ("37c4950c4fd2348e3cd03cde68612fc2cb82efea7a37089fd433e9edbc71e0b4", 1437),
    "final_result.json":             ("81ef1052c1e8490aa58b0323669757680809156cd5cbbd2a5caf1ce669b38750", 4810),
    "opening_state.jsonl":           ("60357f6c436fe67464c6d3f4f3732ce7fc9aee061936e7a8b8bd5125acaa5ab1", 171),
    "period_progress.jsonl":         ("d86d10d42a0bd90c536e525d7e65b5ccbf565785a4041d5f8f4bc9fd896ac167", 718),
    "pytest_clean_tree_e708fdb7.log": ("58c274c17505ef346498ce275c90ee238e5997305296e7385e21ca84d8d48ec4", 2651),
    "pytest_e708fdb7.log":           ("b135dd91136bd22285785415675fc67b15e503cbc5d35eea666f8aaf8ff1e57d", 3438),
    "run_claim.json":                ("3ad8f047bd2314543e1100ca49e4dd9dac3fba9f014e250c7b66ad30bf1d717f", 10454),
    "run_provenance.json":           ("3ad8f047bd2314543e1100ca49e4dd9dac3fba9f014e250c7b66ad30bf1d717f", 10454),
    "test_evidence.json":            ("1f3bd6184a06ff9630a3c65d9b92b17e4a705ac0c4f2f9126d78058d27c1bb59", 1267),
}

# Which live path each versioned copy mirrors. `run_claim.json` is the only
# rename: live it is named for the run_id, in the versioned copy it is not.
_LIVE_NAME = {"run_claim.json": LIVE_CLAIM}


class B0OneDiagnosticProtected(RuntimeError):
    """The accepted, immutable B0.1 terminal state no longer matches its pins."""


def _sha256_of(path: str) -> tuple[str, int]:
    raw = open(path, "rb").read()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _live_path(name: str) -> str:
    rel = _LIVE_NAME.get(name)
    if rel is None:
        if name.endswith(".log") or name == "test_evidence.json":
            rel = "artifacts/b0_1_diagnostic/" + name
        else:
            rel = LIVE_RUN_DIR + "/" + name
    return os.path.join(REPO_ROOT, rel)


def b0_1_diagnostic_identity() -> dict:
    """Measured now, for both the versioned and the live copy."""
    out = {}
    for name, (expected, size) in sorted(B0_1_DIAGNOSTIC_ARTEFACT_SHA256.items()):
        row: dict = {"pinned_sha256": expected, "pinned_bytes": size}
        vpath = os.path.join(REPO_ROOT, VERSIONED_PROVENANCE_DIR, name)
        if os.path.exists(vpath):
            sha, length = _sha256_of(vpath)
            row["versioned"] = {"present": True, "sha256": sha, "bytes": length,
                                "matches_pinned": sha == expected and length == size}
        else:
            row["versioned"] = {"present": False}
        lpath = _live_path(name)
        if os.path.exists(lpath):
            sha, length = _sha256_of(lpath)
            row["live"] = {"present": True, "sha256": sha, "bytes": length,
                           "matches_pinned": sha == expected and length == size}
        else:
            row["live"] = {"present": False}
        out[name] = row
    hpath = os.path.join(REPO_ROOT, B0_1_HARNESS)
    if os.path.exists(hpath):
        sha, length = _sha256_of(hpath)
        out[B0_1_HARNESS] = {
            "pinned_sha256": B0_1_HARNESS_SHA256[0],
            "pinned_bytes": B0_1_HARNESS_SHA256[1],
            "versioned": {"present": True, "sha256": sha, "bytes": length,
                          "matches_pinned": (sha, length) == B0_1_HARNESS_SHA256},
            "live": {"present": False},
        }
    else:
        out[B0_1_HARNESS] = {"versioned": {"present": False},
                            "live": {"present": False}}
    return out


def assert_b0_1_diagnostic_unmutated() -> dict:
    """R1: preserved bytes, checked rather than trusted.

    The versioned copy must be present and matching. The live copy is checked
    only when it exists -- a fresh clone legitimately has no `artifacts/` tree,
    and demanding one would make this assertion fail for the wrong reason. What
    is never tolerated is a live copy that exists and DISAGREES.
    """
    identity = b0_1_diagnostic_identity()
    broken = []
    for name, row in identity.items():
        v = row.get("versioned", {})
        if not v.get("present") or not v.get("matches_pinned"):
            broken.append("%s: versioned copy missing or altered" % name)
        live = row.get("live", {})
        if live.get("present") and not live.get("matches_pinned"):
            broken.append("%s: live copy altered" % name)
    if broken:
        raise B0OneDiagnosticProtected(
            "R1: the accepted B0.1 diagnostic terminal state no longer matches "
            "the bytes pinned in this module: %s. B0.1 is immutable; B0.2 "
            "exists because of what it recorded, and may not rewrite it."
            % broken)
    return identity
