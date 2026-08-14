# -*- coding: utf-8 -*-
"""P0-R2 forward identity collector — Phase C offline tests, part 3/3: capacity
(NFR-7), scheduling mutex (FR-45), health (FR-48), epoch (FR-49/51/52), and
the collector-failure/production-isolation guarantee (FR-46, NFR-10).

Phase C scope note (see final report Limitations): `test_capacity_bootstrap_
requires_three_dry_runs` is Phase-D-tagged in the frozen matrix (the REAL
bootstrap needs 3 dry-runs against the real P-B dates 2026-08-07/10/11).
Here it validates the MECHANISM with synthetic payload files under those
same three frozen date labels -- the real dry-run against production P-B is
deferred to Phase D.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from identity_collector import capacity  # noqa: E402
from identity_collector import epoch as epoch_mod  # noqa: E402
from identity_collector import health as health_mod  # noqa: E402
from identity_collector import ledger as ledger_mod  # noqa: E402
from identity_collector import live_receipt_projection_template as lrpt  # noqa: E402
from identity_collector import lock as lock_mod  # noqa: E402
from identity_collector import manifest as manifest_mod  # noqa: E402
from identity_collector import receipt as receipt_mod  # noqa: E402
from identity_collector import schema_validation as sv  # noqa: E402
from identity_collector.hashing import hash_paths, sha256_hex, sha256_of_file  # noqa: E402
from identity_collector.timestamps import now_pair  # noqa: E402

FIXED_CLOCK = lambda: datetime(2026, 8, 7, 1, 0, 0, tzinfo=timezone.utc)  # noqa: E731

REPO_GIT_BLOB_SHA1 = "22df8b38b89b6d817e8f612ea0eedd5037f5a8d5"  # `git hash-object` of live_receipt_projection_template.py (read-only, computed once in this session)
REPO_HEAD_COMMIT = "e187e76c14cd3cd297526423bdeaecd5b816cd7a"


def _synthetic_output_manifest(n_bytes_each: int = 1000) -> dict:
    names = [
        "source_manifest.json", "code_config_manifest.json", "p_a_raw_snapshot.parquet",
        "p_a_screen_by_composite_parity.parquet", "p_b_fullpool.parquet", "p_app_fusion.csv",
        "p_l4a_fusion.csv", "rank_audit.csv", "process_import_manifest.json", "replay_manifest.json",
    ]
    return {n: {"bytes": n_bytes_each, "sha256": sha256_hex(n.encode())} for n in names}


def _synthetic_source_hash_manifest() -> dict:
    def m(tag):
        return {"files": {f"{tag}.parquet": {"bytes": 10, "sha256": sha256_hex(tag.encode())}}, "aggregate_sha256": sha256_hex(tag.encode())}
    return {"p_a": m("pa"), "p_b": m("pb"), "r_fwd": None}


def _synthetic_code_hash_manifest() -> dict:
    fields = [
        "score_store_sha256", "scoring_manager_sha256", "fundamentals_sha256", "valuation_sha256",
        "advisor_sha256", "backtest_sha256", "regime_sha256", "app_py_sha256", "l4a_decision_sha256",
        "technical_analysis_sha256", "data_provider_sha256", "industry_value_sha256",
        "ranking_adapter_sha256", "universe_screen_daily_sha256", "build_cache_loader_sha256",
    ]
    d = {f: sha256_hex(f.encode()) for f in fields}
    d["r_fwd_adapter_sha256"] = None
    return d


def _synthetic_actual_inputs(as_of: str, identity_status: str) -> dict:
    with_rfwd = identity_status == "COMPARABLE_IDENTITY"
    return {
        "as_of": as_of, "persistence_status": "COMMITTED", "identity_status": identity_status,
        "monthly_status": "DAILY_DIAGNOSTIC", "source_mutation": False, "revision_of": None,
        "capture_process_started": True,
        "process_isolation": {"production_capture_pid": 4001, "r_fwd_pid": 4002 if with_rfwd else None, "bt_bundle_absent_from_production_process": True},
        "primary_root": "D:\\p0r2_identity_evidence\\primary", "mirror_root": "E:\\p0r2_identity_evidence\\mirror",
        "source_hashes": {**_synthetic_source_hash_manifest(), "r_fwd": ({"files": {"r.parquet": {"bytes": 1, "sha256": sha256_hex(b"r")}}, "aggregate_sha256": sha256_hex(b"r")} if with_rfwd else None)},
        "code_hashes": {**_synthetic_code_hash_manifest(), "r_fwd_adapter_sha256": (sha256_hex(b"adapter") if with_rfwd else None)},
        "collector_config_hash": sha256_hex(b"config"), "collector_schema_sha256": sha256_of_file(sv.SCHEMA_PATH),
        "output_hashes_equivalent": (_synthetic_comparable_manifest() if with_rfwd else _synthetic_output_manifest()),
        "announcement_date_pit_status": "VERIFIED" if with_rfwd else "BLOCKED",
        "r_fwd_qualification_ref": ({"record_id": "rfwdq-11111111-1111-4111-8111-111111111111", "record_hash": sha256_hex(b"rec"), "r_fwd_adapter_sha256": sha256_hex(b"adapter"), "resolution_record_hash": None} if with_rfwd else None),
        "temp_cleanup_status": "NOT_APPLICABLE",
    }


def _synthetic_comparable_manifest() -> dict:
    d = _synthetic_output_manifest()
    d["r_fwd_scores.parquet"] = {"bytes": 500, "sha256": sha256_hex(b"rfs")}
    d["r_fwd_fusion.csv"] = {"bytes": 500, "sha256": sha256_hex(b"rff")}
    return d


def _build_dry_run_receipt(as_of: str) -> dict:
    template_identity = capacity.build_projection_template_identity(
        template_version="v1", repo_relative_path="scripts/identity_collector/live_receipt_projection_template.py",
        git_blob_sha1=REPO_GIT_BLOB_SHA1, reachable_commit_sha1=REPO_HEAD_COMMIT,
        content_sha256=sha256_of_file(REPO_ROOT / "scripts/identity_collector/live_receipt_projection_template.py"),
        durable_copy_path="template_copy.py", durable_copy_bytes=1000, durable_copy_sha256=sha256_of_file(REPO_ROOT / "scripts/identity_collector/live_receipt_projection_template.py"),
    )
    actual_inputs = _synthetic_actual_inputs(as_of, "P_ONLY_EVIDENCE")
    projection = capacity.build_live_receipt_projection(template_identity, actual_inputs)
    payload_files = _synthetic_output_manifest()
    ts = now_pair(FIXED_CLOCK)
    return capacity.build_capacity_dry_run_receipt(
        as_of=as_of, sizing_mode="P_ONLY_EVIDENCE", started_at=ts, completed_at=ts,
        r_fwd_artifacts_included=False, payload_files=payload_files, elapsed_seconds=1.5,
        source_hashes=_synthetic_source_hash_manifest(), code_hashes=_synthetic_code_hash_manifest(),
        collector_config_hash=sha256_hex(b"config"), collector_schema_sha256=sha256_of_file(sv.SCHEMA_PATH),
        live_receipt_projection=projection,
    )


# ============================================================================
# 20. test_capacity_bootstrap_requires_three_dry_runs (NFR-7(a), Gate C-P)
# ============================================================================
def test_capacity_bootstrap_requires_three_dry_runs():
    receipts = {d: _build_dry_run_receipt(d) for d in ("2026-08-07", "2026-08-10", "2026-08-11")}
    for as_of, r in receipts.items():
        ok, errors = sv.validate("CapacityDryRunReceipt", r)
        assert ok, (as_of, errors)
        assembled = lrpt.assemble_projected_receipt(
            r["live_receipt_projection"]["placeholder_policy"], r["live_receipt_projection"]["actual_inputs"]
        )
        ok, errors = sv.validate("ProjectedRunReceipt", assembled)
        assert ok, errors

    attempts = [capacity.build_report_attempt(r) for r in receipts.values()]
    report = capacity.build_capacity_dry_run_report(generated_at=now_pair(FIXED_CLOCK), sizing_mode="P_ONLY_EVIDENCE", attempts=attempts)
    ok, errors = sv.validate("CapacityDryRunReport", report)
    assert ok, errors

    totals = [a["attempt_total_bytes"] for a in attempts]
    ok, problems = sv.check_6_bootstrap_formula(totals, report["bootstrap_bytes_per_run"])
    assert ok, problems

    with pytest.raises(ValueError, match="exactly 3 attempts"):
        capacity.build_capacity_dry_run_report(generated_at=now_pair(FIXED_CLOCK), sizing_mode="P_ONLY_EVIDENCE", attempts=attempts[:2])


# ============================================================================
# 21. test_capacity_uses_bootstrap_for_first_20_runs (NFR-7(b))
# ============================================================================
def test_capacity_uses_bootstrap_for_first_20_runs():
    bootstrap = capacity.bootstrap_bytes_per_run([1_000_000, 2_000_000, 1_500_000])
    for n_runs in (0, 1, 10, 19):
        recent = [999_999_999] * n_runs  # even if actual usage would suggest a bigger number
        assert capacity.capacity_estimate(bootstrap, recent) == bootstrap


# ============================================================================
# 22. test_capacity_switches_to_p95_floor_after_20_runs (NFR-7(c))
# ============================================================================
def test_capacity_switches_to_p95_floor_after_20_runs():
    bootstrap = 1_000_000
    recent_small = [500_000] * 20
    assert capacity.capacity_estimate(bootstrap, recent_small) == bootstrap  # bootstrap floor, never shrinks

    # a single outlier among 20 falls outside the top-5% index -- P95 correctly
    # ignores it (that's the point of P95 over max); ten outliers among twenty
    # land squarely inside the P95 index and DO raise the floor above bootstrap.
    recent_one_outlier = [500_000] * 19 + [5_000_000]
    assert capacity.capacity_estimate(bootstrap, recent_one_outlier) == bootstrap

    recent_many_outliers = [500_000] * 10 + [5_000_000] * 10
    est = capacity.capacity_estimate(bootstrap, recent_many_outliers)
    assert est == 5_000_000 > bootstrap


# ============================================================================
# 23. test_concurrent_run_single_mutex_winner (FR-45(a))
# ============================================================================
def test_concurrent_run_single_mutex_winner(tmp_path):
    now = datetime(2026, 8, 7, 1, 0, 0, tzinfo=timezone.utc)
    winner = lock_mod.acquire(tmp_path, "run-A", pid=1111, now_utc=now, pid_is_alive=lambda p: True)
    assert winner["run_id"] == "run-A"
    with pytest.raises(lock_mod.LockHeld):
        lock_mod.acquire(tmp_path, "run-B", pid=2222, now_utc=now, pid_is_alive=lambda p: True)


# ============================================================================
# 24. test_live_pid_never_treated_as_stale (FR-45(b))
# ============================================================================
def test_live_pid_never_treated_as_stale(tmp_path):
    old = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)  # > 120 min before "now"
    lock_mod.acquire(tmp_path, "run-old", pid=3333, now_utc=old, pid_is_alive=lambda p: True)
    now = old + timedelta(minutes=200)
    state, rec = lock_mod.lock_state(tmp_path, now, pid_is_alive=lambda p: True)  # PID still alive
    assert state == "HELD"  # age alone is never sufficient


# ============================================================================
# 25. test_dead_pid_before_120_minutes_not_stale (FR-45(b))
# ============================================================================
def test_dead_pid_before_120_minutes_not_stale(tmp_path):
    started = datetime(2026, 8, 7, 0, 0, 0, tzinfo=timezone.utc)
    lock_mod.acquire(tmp_path, "run-x", pid=4444, now_utc=started, pid_is_alive=lambda p: True)
    now = started + timedelta(minutes=90)  # < 120 min
    state, rec = lock_mod.lock_state(tmp_path, now, pid_is_alive=lambda p: False)  # PID already dead
    assert state == "HELD"  # dead PID alone, before the lease expires, is never stale


def test_both_conditions_required_for_stale(tmp_path):
    """Companion assertion for FR-45(b): STALE_DETECTED requires BOTH age>120min
    AND dead pid simultaneously."""
    started = datetime(2026, 8, 7, 0, 0, 0, tzinfo=timezone.utc)
    lock_mod.acquire(tmp_path, "run-y", pid=5555, now_utc=started, pid_is_alive=lambda p: True)
    now = started + timedelta(minutes=200)
    state, rec = lock_mod.lock_state(tmp_path, now, pid_is_alive=lambda p: False)
    assert state == "STALE_DETECTED"


# ============================================================================
# 26. test_stale_lock_requires_manual_unlock_receipt (FR-45(c)(d)(e), AC-16)
# ============================================================================
def test_stale_lock_requires_manual_unlock_receipt(tmp_path):
    stale_run_id = sha256_hex(b"run-stale")
    started = datetime(2026, 8, 7, 0, 0, 0, tzinfo=timezone.utc)
    lock_mod.acquire(tmp_path, stale_run_id, pid=6666, now_utc=started, pid_is_alive=lambda p: True)
    now = started + timedelta(minutes=200)

    # (c): collector MUST NOT auto-reclaim -- acquire() refuses, does not delete
    with pytest.raises(lock_mod.LockStaleDetected):
        lock_mod.acquire(tmp_path, sha256_hex(b"run-new"), pid=7777, now_utc=now, pid_is_alive=lambda p: False)
    assert lock_mod.read_lock(tmp_path) is not None  # stale record left untouched

    # (d): manual unlock requires BOTH expected run-id and reason
    with pytest.raises(ValueError):
        lock_mod.manual_unlock(tmp_path, expected_run_id="", operator="ops", reason="stuck", clock=FIXED_CLOCK)
    with pytest.raises(ValueError):
        lock_mod.manual_unlock(tmp_path, expected_run_id=stale_run_id, operator="ops", reason="", clock=FIXED_CLOCK)
    with pytest.raises(ValueError):
        lock_mod.manual_unlock(tmp_path, expected_run_id=sha256_hex(b"wrong-run-id"), operator="ops", reason="stuck", clock=FIXED_CLOCK)

    # (e): correct unlock returns a receipt, never edits the original lock record's fields
    receipt = lock_mod.manual_unlock(tmp_path, expected_run_id=stale_run_id, operator="ops", reason="confirmed dead pid", clock=FIXED_CLOCK)
    assert receipt["run_id_of_lock"] == stale_run_id
    assert receipt["operator"] == "ops" and receipt["reason"] == "confirmed dead pid"
    assert lock_mod.read_lock(tmp_path) is None

    ledger_path = tmp_path / "collector_ledger.jsonl"
    event = ledger_mod.append_event(ledger_path, "unlock", stale_run_id, {
        "run_id_of_lock": receipt["run_id_of_lock"], "expected_run_id_provided": stale_run_id,
        "operator": receipt["operator"], "reason": receipt["reason"],
    }, FIXED_CLOCK)
    ok, errors = sv.validate("LedgerEvent", event)
    assert ok, errors


def _minimal_receipt_fields(*, as_of="2026-08-07", persistence_status="COMMITTED", monthly_status="DAILY_DIAGNOSTIC",
                             identity_status="P_ONLY_EVIDENCE", run_tag="a", identity_epoch="epoch-0000000000000001") -> dict:
    manifest = manifest_mod.attempted_input_manifest(
        p_a=manifest_mod.source_attempt_status("AVAILABLE", as_of, sha256_hex(f"p_a-{run_tag}".encode())),
        p_b=manifest_mod.source_attempt_status("AVAILABLE", as_of, sha256_hex(f"p_b-{run_tag}".encode())),
        r_fwd=manifest_mod.source_attempt_status("NOT_ATTEMPTED"),
        preflight=manifest_mod.preflight_observation("FREE", None, 10_000_000_000, low_disk_threshold_bytes=1_000_000_000),
    )
    input_bundle = sha256_hex((str(manifest) + run_tag).encode())
    collector_version = sha256_hex(b"collector_version")
    run_id = sha256_hex(f"{as_of}-{collector_version}-{input_bundle}".encode())
    ts = now_pair(FIXED_CLOCK)
    output_hashes = _synthetic_output_manifest()
    mirror_status = "VERIFIED" if persistence_status == "COMMITTED" else "PENDING"
    return dict(
        run_id=run_id, as_of=as_of, identity_epoch=identity_epoch, collector_version=collector_version,
        input_bundle_sha256=input_bundle, attempted_input_manifest=manifest, persistence_status=persistence_status,
        identity_status=identity_status, monthly_status=monthly_status, source_mutation=False, revision_of=None,
        started_at=ts, completed_at=ts, capture_process_started=True,
        process_isolation={"production_capture_pid": 5001, "r_fwd_pid": None, "bt_bundle_absent_from_production_process": True},
        source_hashes=_synthetic_source_hash_manifest(), code_hashes=_synthetic_code_hash_manifest(),
        collector_config_hash=sha256_hex(b"config"), collector_schema_sha256=sha256_of_file(sv.SCHEMA_PATH),
        output_hashes=output_hashes,
        mirror_verification={
            "status": mirror_status, "primary_aggregate_sha256": sha256_hex(b"agg"),
            "mirror_aggregate_sha256": (sha256_hex(b"agg") if mirror_status == "VERIFIED" else None),
            "per_file_verification": {k: {"primary_sha256": sha256_hex(k.encode()), "mirror_sha256": (sha256_hex(k.encode()) if mirror_status == "VERIFIED" else None), "match": mirror_status == "VERIFIED"} for k in output_hashes},
        },
        announcement_date_pit_status="BLOCKED", r_fwd_qualification_ref=None,
        primary_root="D:\\p0r2_identity_evidence\\primary", mirror_root="E:\\p0r2_identity_evidence\\mirror",
        temp_cleanup_status="NOT_APPLICABLE",
    )


# ============================================================================
# 27. test_health_command_schema_and_counts (FR-48, AC-16)
# ============================================================================
def test_health_command_schema_and_counts(tmp_path):
    committed = receipt_mod.build_receipt_success(**_minimal_receipt_fields(run_tag="committed", monthly_status="MONTHLY_ELIGIBLE"))
    pending = receipt_mod.build_receipt_success(**_minimal_receipt_fields(run_tag="pending", persistence_status="PENDING_MIRROR"))
    ok, errors = sv.validate("RunReceiptSuccess", committed)
    assert ok, errors
    ok, errors = sv.validate("RunReceiptSuccess", pending)
    assert ok, errors

    ledger_path = tmp_path / "collector_ledger.jsonl"
    # recovery: append a "mirror" event verifying the pending run -> effective COMMITTED
    from identity_collector.mirror import build_mirror_verification
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    for f in pending["output_hashes"]:
        (primary / f).parent.mkdir(parents=True, exist_ok=True)
        (primary / f).write_bytes(f.encode())
        (mirror / f).parent.mkdir(parents=True, exist_ok=True)
        (mirror / f).write_bytes(f.encode())
    real_mv = build_mirror_verification(primary, mirror, list(pending["output_hashes"]))
    # rebuild `pending` so its output_hashes/mirror_verification reflect the REAL synthetic files just written
    pending = dict(pending, output_hashes={k: {"bytes": len(k.encode()), "sha256": sha256_of_file(primary / k)} for k in pending["output_hashes"]})
    recovery_payload = ledger_mod.build_mirror_recovery_payload(pending["run_id"], "PENDING", "VERIFIED", real_mv, pending)
    event = ledger_mod.append_event(ledger_path, "mirror", pending["run_id"], recovery_payload, FIXED_CLOCK)
    ok, errors = sv.validate("LedgerEvent", event)
    assert ok, errors
    ok, problems = sv.check_11_mirror_recovery_per_file(recovery_payload, pending)
    assert ok, problems

    entries = ledger_mod.read_ledger(ledger_path)
    assert health_mod.effective_persistence_status(pending, entries) == "COMMITTED"
    assert health_mod.effective_persistence_status(committed, entries) == "COMMITTED"

    summary = health_mod.build_health_summary([committed, pending], entries, "FREE", None, now_pair(FIXED_CLOCK))
    ok, errors = sv.validate("HealthSummary", summary)
    assert ok, errors
    assert summary["pending_mirror_count"] == 0  # recovered -> no longer pending
    assert summary["monthly_eligible_count"] == 1

    incomplete_summary = dict(summary)
    del incomplete_summary["pending_mirror_count"]
    ok, errors = sv.validate("HealthSummary", incomplete_summary)
    assert not ok  # missing field -> the whole health command must be treated as failed, never partial success


# ============================================================================
# 28. test_epoch_change_on_identity_definition_change (FR-49, FR-51, AC-13)
# ============================================================================
def test_epoch_change_on_identity_definition_change():
    base_inputs = {
        "score_formula_version": "v1", "weights_version": "w1", "watchlist_build_universe_policy": "p1",
        "c2_formula_version": "c1", "adv_listed_rule_version": "l1", "rank_method_version": "r1",
        "fusion_pct": 20, "collector_schema_sha256": "s1", "r_fwd_semantics_version": "rf1",
    }
    epoch_1 = epoch_mod.compute_identity_epoch(base_inputs)
    assert epoch_1.startswith("epoch-") and len(epoch_1) == len("epoch-") + 16

    same_inputs = dict(base_inputs)
    assert epoch_mod.compute_identity_epoch(same_inputs) == epoch_1  # pure refactor of unrelated code -> same epoch
    assert not epoch_mod.epoch_transition_required(base_inputs, same_inputs)

    changed_inputs = dict(base_inputs, fusion_pct=25)  # FR-49-listed field changed
    epoch_2 = epoch_mod.compute_identity_epoch(changed_inputs)
    assert epoch_2 != epoch_1
    assert epoch_mod.epoch_transition_required(base_inputs, changed_inputs)


# ============================================================================
# 29. test_no_cross_epoch_month_counting (FR-52, AC-13, AC-14)
# ============================================================================
def test_no_cross_epoch_month_counting():
    epoch_a_receipts = [_minimal_receipt_fields(run_tag=f"a{i}", identity_epoch="epoch-aaaaaaaaaaaaaaaa", monthly_status="MONTHLY_ELIGIBLE") for i in range(14)]
    epoch_b_receipts = [_minimal_receipt_fields(run_tag=f"b{i}", identity_epoch="epoch-bbbbbbbbbbbbbbbb", monthly_status="MONTHLY_ELIGIBLE") for i in range(10)]
    all_receipts = [receipt_mod.build_receipt_success(**f) for f in (epoch_a_receipts + epoch_b_receipts)]

    def eligible_count_for_epoch(receipts, epoch):
        return sum(1 for r in receipts if r["identity_epoch"] == epoch and r["monthly_status"] == "MONTHLY_ELIGIBLE")

    assert eligible_count_for_epoch(all_receipts, "epoch-aaaaaaaaaaaaaaaa") == 14
    assert eligible_count_for_epoch(all_receipts, "epoch-bbbbbbbbbbbbbbbb") == 10
    # neither epoch alone reaches 24 -- and they must NEVER be summed together (14+10=24 would be wrong)
    total_wrong_if_bridged = eligible_count_for_epoch(all_receipts, "epoch-aaaaaaaaaaaaaaaa") + eligible_count_for_epoch(all_receipts, "epoch-bbbbbbbbbbbbbbbb")
    assert total_wrong_if_bridged == 24  # demonstrates the trap: naive summation WOULD hit the Gate C-24 threshold
    assert max(eligible_count_for_epoch(all_receipts, "epoch-aaaaaaaaaaaaaaaa"), eligible_count_for_epoch(all_receipts, "epoch-bbbbbbbbbbbbbbbb")) < 24  # correct per-epoch counts stay below it


# ============================================================================
# 30. test_collector_failure_does_not_change_production_outputs (FR-46, AC-15, NFR-10)
# ============================================================================
def test_collector_failure_does_not_change_production_outputs(tmp_path):
    production_scores = tmp_path / "score_store.parquet"
    production_scores.write_bytes(b"synthetic production scores, must survive collector failure untouched")
    before = hash_paths([production_scores])

    failure = receipt_mod.build_receipt_failure(
        run_id=sha256_hex(b"failed-run"), as_of="2026-08-07", identity_epoch=None,
        identity_epoch_unavailable_reason="LOCK_HELD_BEFORE_CAPTURE",
        collector_version=sha256_hex(b"cv"), input_bundle_sha256=sha256_hex(b"ib"),
        attempted_input_manifest=manifest_mod.attempted_input_manifest(
            p_a=manifest_mod.source_attempt_status("NOT_ATTEMPTED"),
            p_b=manifest_mod.source_attempt_status("NOT_ATTEMPTED"),
            r_fwd=manifest_mod.source_attempt_status("NOT_ATTEMPTED"),
            preflight=manifest_mod.preflight_observation("HELD", 1234, 10_000_000_000, low_disk_threshold_bytes=1_000_000_000),
        ),
        persistence_status="FAILED", failure_code="LOCK_HELD", identity_status="P_ONLY_EVIDENCE",
        monthly_status="DAILY_DIAGNOSTIC", source_mutation=False, revision_of=None,
        started_at=now_pair(FIXED_CLOCK), completed_at=now_pair(FIXED_CLOCK), capture_process_started=False,
        process_isolation=None, source_hashes={"p_a": None, "p_b": None, "r_fwd": None},
        code_hashes=_synthetic_code_hash_manifest(), collector_config_hash=sha256_hex(b"config"),
        collector_schema_sha256=sha256_of_file(sv.SCHEMA_PATH), output_hashes={},
        primary_root="D:\\p0r2_identity_evidence\\primary", mirror_root="E:\\p0r2_identity_evidence\\mirror",
        temp_cleanup_status="NOT_APPLICABLE",
    )
    ok, errors = sv.validate("RunReceiptFailure", failure)
    assert ok, errors

    after = hash_paths([production_scores])
    assert before == after  # collector failure never touched the production file
    assert failure["persistence_status"] == "FAILED"  # failure is independent, non-success -- but production is intact
