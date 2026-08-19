# -*- coding: utf-8 -*-
"""R1 · the accepted B0.1 diagnostic terminal state is immutable.

B0.2 exists because run B01DIAG-0121b3261805b826 stopped at 2/141 on a
conformance defect. If that record can drift, the justification for B0.2 drifts
with it, so these are regression tests rather than documentation.
"""
from __future__ import annotations

import json
import os

import pytest

from core import b0_1_diagnostic_closure as closure
from core.b0_master_prereg import NORMATIVE_MODULES

REPO = closure.REPO_ROOT
TP = os.path.join(REPO, closure.VERSIONED_PROVENANCE_DIR)


def test_closure_module_is_normative():
    assert "core/b0_1_diagnostic_closure.py" in NORMATIVE_MODULES


def test_b0_1_artefacts_match_their_pins():
    closure.assert_b0_1_diagnostic_unmutated()


def test_every_pinned_artefact_has_a_versioned_copy():
    identity = closure.b0_1_diagnostic_identity()
    missing = [n for n, r in identity.items() if not r["versioned"]["present"]]
    assert missing == []


def test_harness_bytes_are_preserved_exactly():
    identity = closure.b0_1_diagnostic_identity()
    row = identity[closure.B0_1_HARNESS]
    assert row["versioned"]["matches_pinned"]
    assert row["versioned"]["sha256"] == closure.B0_1_HARNESS_SHA256[0]


def test_a_mutated_artefact_is_caught(tmp_path, monkeypatch):
    """The pin has to be load-bearing, not decorative."""
    name = "final_result.json"
    original = open(os.path.join(TP, name), "rb").read()
    try:
        with open(os.path.join(TP, name), "wb") as fh:
            fh.write(original + b" ")
        with pytest.raises(closure.B0OneDiagnosticProtected):
            closure.assert_b0_1_diagnostic_unmutated()
    finally:
        with open(os.path.join(TP, name), "wb") as fh:
            fh.write(original)
    closure.assert_b0_1_diagnostic_unmutated()


def test_terminal_state_is_the_one_b0_2_was_authorised_against():
    body = json.load(open(os.path.join(TP, "final_result.json"), encoding="utf-8"))
    assert body["run_id"] == closure.B0_1_DIAGNOSTIC_RUN_ID
    assert body["diagnostic_terminal_status"] == closure.B0_1_DIAGNOSTIC_TERMINAL_STATUS
    assert body["periods_executed"] == closure.B0_1_DIAGNOSTIC_PERIODS_EXECUTED
    assert body["periods_required"] == closure.B0_1_DIAGNOSTIC_PERIODS_REQUIRED
    assert body["performance_computed"] is False
    assert body["evidence_class"] == closure.B0_1_DIAGNOSTIC_EVIDENCE_CLASS
    assert body["confirmatory_l2"] is False
    assert body["replaces_frozen_b0_l2"] is False


def test_b0_1_baseline_identity_is_not_moved_by_a_later_closure_commit():
    """The closure commit is not the baseline. Named so a reader cannot conflate."""
    body = json.load(open(os.path.join(TP, "run_provenance.json"), encoding="utf-8"))
    assert body["commit_sha"] == closure.B0_1_BOUND_COMMIT
    assert body["b0_1_baseline_seal"] == closure.B0_1_BASELINE_SEAL_SHA256
    assert body["spec_sha256"] == closure.B0_1_SPEC_SHA256
    assert body["master_version"] == closure.B0_1_MASTER_VERSION
