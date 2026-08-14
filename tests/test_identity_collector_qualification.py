# -*- coding: utf-8 -*-
"""P0-R2 forward identity collector — Phase C offline tests, part 2/3: R-FWD
adapter qualification (FR-24/25/26/27/28).

Phase C scope note (see final report Limitations): these tests qualify the
adapter's MECHANISM -- membership/tolerance/isolation/future-access gates,
the append-only ledger, and check #10's precise resolution-pinning -- against
a SYNTHETIC 255-month fixture standing in for the true frozen research panel.
Running the adapter against the REAL panel is Phase D's "dry run and parity"
(prereg §12), explicitly out of scope for this Phase C pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from identity_collector import qualification_ledger  # noqa: E402
from identity_collector import r_fwd_adapter  # noqa: E402
from identity_collector import schema_validation as sv  # noqa: E402
from identity_collector.testing import build_qualification_attempt_body, build_resolution_body  # noqa: E402


# ============================================================================
# 10. test_r_fwd_255_month_membership_parity (FR-25, AC-7)
# ============================================================================
def test_r_fwd_255_month_membership_parity(tmp_path):
    attempt_body, primary_root, mirror_root = build_qualification_attempt_body(tmp_path, gates_pass=True, bundle_verified=True)
    assert attempt_body["membership_parity_result"]["months_tested"] == 255
    assert attempt_body["membership_parity_result"]["exact_match_count"] == 255
    assert attempt_body["membership_parity_result"]["mismatched_months"] == []
    assert attempt_body["process_isolation_audit"]["status"] == "PASS"
    assert attempt_body["future_input_access_audit"]["status"] == "PASS"
    assert attempt_body["qualification_status"] == "QUALIFIED"

    qlp = tmp_path / "r_fwd_adapter_qualification_ledger.jsonl"
    attempt_written = qualification_ledger.append_ledger_entry(qlp, attempt_body)
    for f in ("sequence", "prior_record_hash", "record_hash", "record_id"):
        assert attempt_written.get(f) is not None or f == "prior_record_hash"
    ok, errors = sv.validate("RFwdAdapterQualificationRecord", attempt_written)
    assert ok, errors

    # a mismatch anywhere -> QUALIFICATION_FAILED, not QUALIFIED
    failing_body, _p, _m = build_qualification_attempt_body(tmp_path, gates_pass=False, bundle_verified=True)
    assert failing_body["qualification_status"] == "QUALIFICATION_FAILED"
    assert failing_body["membership_parity_result"]["exact_match_count"] < 255

    # --- round 13 sharpening: RFwdQualificationRef must pin the EXACT resolution ---
    pending_body, p_root, m_root = build_qualification_attempt_body(tmp_path, gates_pass=True, bundle_verified=False)
    pending_written = qualification_ledger.append_ledger_entry(qlp, pending_body)
    assert pending_written["qualification_status"] == "QUALIFICATION_PENDING"

    completed_at = {"utc": "2026-08-07T02:00:00.000000+00:00", "local_taipei": "2026-08-07T10:00:00.000000+08:00"}
    ref_null = {"record_id": pending_written["record_id"], "record_hash": pending_written["record_hash"],
                "r_fwd_adapter_sha256": pending_written["r_fwd_adapter_sha256"], "resolution_record_hash": None}
    attempts_by_hash = {attempt_written["record_hash"]: attempt_written, pending_written["record_hash"]: pending_written}
    ok, why = sv.check_10_resolve_qualification_ref(ref_null, attempts_by_hash, {}, completed_at)
    assert not ok, "P1 regression: a PENDING attempt with resolution_record_hash=null must never resolve"

    resolution_body = build_resolution_body(pending_written, p_root, m_root)
    resolution_written = qualification_ledger.append_ledger_entry(qlp, resolution_body)
    ok, errors = sv.validate("RFwdQualificationResolutionEvent", resolution_written)
    assert ok, errors

    ref_pinned = dict(ref_null, resolution_record_hash=resolution_written["record_hash"])
    resolutions_by_hash = {resolution_written["record_hash"]: resolution_written}
    ok, why = sv.check_10_resolve_qualification_ref(ref_pinned, attempts_by_hash, resolutions_by_hash, completed_at)
    assert ok, why

    # re-validating the identical ref_null AFTER the resolution now exists in the ledger -- verdict unchanged
    ok_again, why_again = sv.check_10_resolve_qualification_ref(ref_null, attempts_by_hash, resolutions_by_hash, completed_at)
    assert not ok_again, "re-validation invariance violated: ref_null must stay rejected regardless of what was later appended"

    ok, problems = sv.check_24_resolution_matches_attempt_bundle(resolution_written, pending_written)
    assert ok, problems


# ============================================================================
# 11. test_r_fwd_raw_score_tolerance (FR-26, AC-7)
# ============================================================================
def test_r_fwd_raw_score_tolerance():
    within = r_fwd_adapter.raw_score_parity_result({"2330": 71.2, "2317": 55.0}, {"2330": 71.2, "2317": 55.0})
    assert within["within_tolerance"] is True
    assert within["max_abs_diff"] == 0.0
    assert within["tolerance"] == "1e-12"

    outside = r_fwd_adapter.raw_score_parity_result({"2330": 71.2 + 1e-6}, {"2330": 71.2})
    assert outside["within_tolerance"] is False
    assert outside["max_abs_diff"] > 1e-12

    with pytest.raises(ValueError, match="no common raw-score keys"):
        r_fwd_adapter.raw_score_parity_result({"2330": 1.0}, {"2317": 2.0})


# ============================================================================
# 12. test_r_fwd_cannot_read_exec_ret_or_future_inputs (FR-28, AC-8)
# ============================================================================
def test_r_fwd_cannot_read_exec_ret_or_future_inputs():
    evidence_artifact = {"artifact_role": "FUTURE_INPUT_ACCESS_TRACE", "relative_path": "future_input_access_trace.json", "bytes": 10, "sha256": "a" * 64}

    clean = r_fwd_adapter.build_future_input_access_audit(
        method="STATIC_IMPORT_GRAPH", audit_tool_sha256="b" * 64,
        audited_entrypoint="scripts.identity_collector.r_fwd_adapter:compute_membership",
        forbidden_targets_reached=[], evidence_artifact=evidence_artifact,
    )
    assert clean["status"] == "PASS"
    assert set(r_fwd_adapter.FR28_FORBIDDEN_TARGETS) <= set(clean["forbidden_targets"])

    leaked = r_fwd_adapter.build_future_input_access_audit(
        method="RUNTIME_IMPORT_MONITOR", audit_tool_sha256="c" * 64,
        audited_entrypoint="scripts.identity_collector.r_fwd_adapter:compute_membership",
        forbidden_targets_reached=["exec_ret.parquet"], evidence_artifact=evidence_artifact,
    )
    assert leaked["status"] == "FAIL"

    with pytest.raises(ValueError, match="forbidden_targets must include"):
        r_fwd_adapter.build_future_input_access_audit(
            method="STATIC_IMPORT_GRAPH", audit_tool_sha256="d" * 64, audited_entrypoint="x:y",
            forbidden_targets_reached=[], evidence_artifact=evidence_artifact,
            forbidden_targets=["exec_ret.parquet"],  # missing obs_alpha.parquet
        )

    # process isolation half of FR-24 -- same module, adjacent gate
    r_fwd_process = {"pid": 3001, "executable_path": "C:\\rfwd.exe", "argv_sha256": "e" * 64, "started_at": {"utc": "2026-08-07T00:00:00.000000+00:00", "local_taipei": "2026-08-07T08:00:00.000000+08:00"}}
    same_pid = dict(r_fwd_process, pid=3001)
    audit = r_fwd_adapter.build_process_isolation_audit(
        r_fwd_process=r_fwd_process, production_capture_process=same_pid,
        import_manifest_artifact={"artifact_role": "PROCESS_IMPORT_MANIFEST", "relative_path": "process_import_manifest.json", "bytes": 1, "sha256": "f" * 64},
        bt_bundle_absent_from_production_process=True,
    )
    assert audit["status"] == "FAIL"  # same pid -> isolation violated even though bt_bundle absent
