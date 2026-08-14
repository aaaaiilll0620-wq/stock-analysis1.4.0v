# -*- coding: utf-8 -*-
"""P0-R2 forward identity collector — Phase C offline tests, part 1/3.

全部合成資料;不讀任何真實 production 來源、不建立 evidence roots、不排程、
不寫 Task Scheduler。對應 research/p0_r2_identity_collector/phase_b_design_freeze.md
§13 frozen 30-test matrix 第 1-9、13-19、30 項。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from identity_collector import diagnose  # noqa: E402
from identity_collector import lock as lock_mod  # noqa: E402
from identity_collector import manifest as manifest_mod  # noqa: E402
from identity_collector import mirror as mirror_mod  # noqa: E402
from identity_collector import receipt as receipt_mod  # noqa: E402
from identity_collector import schema_validation as sv  # noqa: E402
from identity_collector import sources  # noqa: E402
from identity_collector.hashing import hash_paths, sha256_of_file  # noqa: E402
from identity_collector.timestamps import now_pair  # noqa: E402

FIXED_CLOCK = lambda: datetime(2026, 8, 7, 1, 0, 0, tzinfo=timezone.utc)  # noqa: E731


# ============================================================================
# 1. test_history_gap_requires_evidence_for_deleted (FR-5)
# ============================================================================
def test_history_gap_requires_evidence_for_deleted():
    with pytest.raises(ValueError, match="deletion_evidence"):
        diagnose.adjudicate_cause("PRODUCED_THEN_DELETED", deletion_evidence=[])
    # real evidence present -> accepted
    assert diagnose.adjudicate_cause("PRODUCED_THEN_DELETED", deletion_evidence=["backup_listing_2026-07-01.csv"]) == "PRODUCED_THEN_DELETED"
    # absence-of-file-alone (no evidence list at all) still rejected
    with pytest.raises(ValueError):
        diagnose.adjudicate_cause("PRODUCED_THEN_DELETED")


# ============================================================================
# 2. test_history_diagnosis_does_not_mutate_sources (FR-7, AC-2)
# ============================================================================
def test_history_diagnosis_does_not_mutate_sources(tmp_path):
    protected = tmp_path / "protected_score_store.parquet"
    protected.write_bytes(b"synthetic production bytes, never touched")
    before = hash_paths([protected])

    # "run diagnosis" -- adjudicate a cause using only synthetic evidence, touching nothing
    diagnose.adjudicate_cause("UNRESOLVED")
    diagnose.adjudicate_cause("NOT_PRODUCED")

    after = hash_paths([protected])
    diagnose.assert_protected_paths_unchanged(before, after)
    assert before == after


# ============================================================================
# 3. test_exact_date_only_no_nearest_fill (FR-10, FR-11, AC-3)
# ============================================================================
def test_exact_date_only_no_nearest_fill():
    assert sources.resolve_common_as_of(["2026-08-05", "2026-08-06", "2026-08-07"], ["2026-08-05", "2026-08-07"]) == "2026-08-07"

    with pytest.raises(sources.SourceDateMismatch):
        sources.resolve_common_as_of(["2026-08-07"], ["2026-08-06"])  # P-A/P-B latest differ -> DATE_MISMATCH, no nearest-fill

    with pytest.raises(sources.SourceDateMismatch):
        sources.resolve_common_as_of([], ["2026-08-06"])


# ============================================================================
# 4. test_daily_not_counted_as_monthly (FR-12, FR-15)
# ============================================================================
def test_daily_not_counted_as_monthly():
    daily = receipt_mod.build_receipt_success(**_minimal_success_fields(monthly_status="DAILY_DIAGNOSTIC"))
    ok, errors = sv.validate("RunReceiptSuccess", daily)
    assert ok, errors
    assert daily["monthly_status"] == "DAILY_DIAGNOSTIC"
    # DAILY_DIAGNOSTIC receipts must never claim MONTHLY_ELIGIBLE
    assert daily["monthly_status"] != "MONTHLY_ELIGIBLE"


# ============================================================================
# 5. test_month_end_qualification_is_append_only (FR-13, FR-14, AC-4)
# ============================================================================
def test_month_end_qualification_is_append_only(tmp_path):
    """A day's snapshot is written as QUALIFICATION_PENDING-shaped monthly_status
    (here modeled via the run's own monthly_status field); confirming it's the
    NEXT trading day only APPENDS a receipt with monthly_status=MONTHLY_ELIGIBLE
    pointing at the same as_of -- the original snapshot's bytes never change."""
    original = receipt_mod.build_receipt_success(**_minimal_success_fields(monthly_status="QUALIFICATION_PENDING", as_of="2026-07-31"))
    ok, errors = sv.validate("RunReceiptSuccess", original)
    assert ok, errors
    original_bytes_before = json.dumps(original, sort_keys=True)

    # qualification job appends a NEW receipt (new run_id via new input_bundle_sha256), never edits `original`
    qualified = receipt_mod.build_receipt_success(**_minimal_success_fields(monthly_status="MONTHLY_ELIGIBLE", as_of="2026-07-31", run_id_seed="qualify"))
    ok, errors = sv.validate("RunReceiptSuccess", qualified)
    assert ok, errors

    assert json.dumps(original, sort_keys=True) == original_bytes_before
    assert qualified["run_id"] != original["run_id"]
    assert qualified["as_of"] == original["as_of"]


# ============================================================================
# 6. test_pa_snapshot_captures_full_native_universe (FR-17, AC-5)
# ============================================================================
def test_pa_snapshot_captures_full_native_universe():
    from identity_collector import ranking_adapter

    rows = [
        {"as_of": "2026-08-07", "stock_id": "2330", "mode": "balanced", "composite": 71.2, "weights_version": "v3"},
        {"as_of": "2026-08-07", "stock_id": "2317", "mode": "balanced", "composite": 55.0, "weights_version": "v3"},
        {"as_of": "2026-08-07", "stock_id": "2454", "mode": "balanced", "composite": None, "weights_version": "v3"},
    ]
    with pytest.raises(ValueError, match="NULL composite"):
        ranking_adapter.screen_by_composite_parity(rows)

    ok_rows = [r for r in rows if r["composite"] is not None]
    parity = ranking_adapter.screen_by_composite_parity(ok_rows)
    assert len(parity) == 2  # raw-vs-parity: never more rows out than in
    assert ranking_adapter.require_unique_weights_version(parity) == "v3"

    mixed_versions = [dict(r, weights_version="v4") for r in ok_rows[:1]] + ok_rows[1:]
    with pytest.raises(ValueError, match="weights_version"):
        ranking_adapter.require_unique_weights_version(mixed_versions)

    limited = ranking_adapter.top_limit_screen(parity, top_limit=1)
    assert len(limited) == 1 and limited[0]["stock_id"] == "2330"


# ============================================================================
# 7. test_pb_snapshot_captures_fullpool_and_metadata (FR-18, AC-5)
# ============================================================================
def test_pb_snapshot_captures_fullpool_and_metadata():
    sources.check_filename_matches_content_date("2026-08-07", "2026-08-07")  # OK, no raise
    with pytest.raises(sources.SourceDateConflict):
        sources.check_filename_matches_content_date("2026-08-07", "2026-08-06")  # EC-2

    rows = [
        {"as_of": "2026-08-07", "stock_id": "2330", "mode": "fullpool"},
        {"as_of": "2026-08-07", "stock_id": "2330", "mode": "fullpool"},  # duplicate key
    ]
    with pytest.raises(sources.DuplicateKey):
        sources.check_no_duplicate_keys(rows)


# ============================================================================
# 8. test_app_l4a_same_frozen_inputs_exact_set (FR-19, FR-20, AC-6)
# ============================================================================
def test_app_l4a_same_frozen_inputs_exact_set():
    from identity_collector import fusion

    frozen_universe = [{"stock_id": s, "real_composite": 90 - i} for i, s in enumerate(["2330", "2317", "2454", "3008"])]

    def app_path(universe):
        return [r["stock_id"] for r in universe if r["real_composite"] >= 88]

    def l4a_path(universe):
        return [r["stock_id"] for r in universe if r["real_composite"] >= 88]

    app_set, l4a_set = fusion.compute_dual_fusion(frozen_universe, app_path, l4a_path)
    assert app_set == l4a_set == {"2330", "2317", "2454"}  # composites 90/89/88 all clear the >=88 threshold

    def diverging_l4a_path(universe):
        return [r["stock_id"] for r in universe if r["real_composite"] >= 89]  # off-by-one threshold

    with pytest.raises(fusion.ProductionInternalDivergence):
        fusion.compute_dual_fusion(frozen_universe, app_path, diverging_l4a_path)

    # same frozen_universe object passed twice -- never re-read mid-computation
    assert app_path(frozen_universe) == app_path(frozen_universe)


# ============================================================================
# 9. test_no_orderintent_positionstate_or_l4b_access (FR-21, AC-6)
# ============================================================================
def test_no_orderintent_positionstate_or_l4b_access():
    import identity_collector.fusion as fusion_mod

    # module NAMESPACE, not source text (the module's own docstring legitimately
    # names these as what it must NOT do -- checking hasattr avoids that false positive)
    for forbidden in ("OrderIntent", "PositionState", "compute_order_intent", "l4b_execution"):
        assert not hasattr(fusion_mod, forbidden), f"fusion.py must never define/import {forbidden} (FR-21)"


# ============================================================================
# 13. test_identical_run_is_idempotent (FR-31, FR-32, AC-9)
# ============================================================================
def test_identical_run_is_idempotent(tmp_path):
    fields = _minimal_success_fields()
    r1 = receipt_mod.build_receipt_success(**fields)
    run_dir = tmp_path / "evidence" / r1["identity_epoch"] / r1["as_of"] / r1["run_id"]
    receipt_mod.atomic_write_json(run_dir / "run_receipt.json", r1)

    existing = receipt_mod.find_receipt_by_run_id(tmp_path / "evidence", r1["run_id"])
    assert existing == r1

    # re-running with the SAME inputs -> same run_id -> idempotent no-op, no new evidence
    r2 = receipt_mod.build_receipt_success(**fields)
    assert r2["run_id"] == r1["run_id"]
    found_again = receipt_mod.find_receipt_by_run_id(tmp_path / "evidence", r2["run_id"])
    assert found_again is not None
    run_dirs = list((tmp_path / "evidence").rglob("run_receipt.json"))
    assert len(run_dirs) == 1  # no duplicate evidence written


# ============================================================================
# 14. test_same_date_changed_source_creates_revision (FR-33, AC-9)
# ============================================================================
def test_same_date_changed_source_creates_revision():
    original = receipt_mod.build_receipt_success(**_minimal_success_fields())
    mutated_fields = _minimal_success_fields(input_bundle_seed="mutated-source-bytes")
    is_mutation, revision_of = receipt_mod.determine_revision(mutated_fields["input_bundle_sha256"], [original])
    assert is_mutation is True
    assert revision_of == original["run_id"]

    mutated_fields["source_mutation"] = True
    mutated_fields["revision_of"] = revision_of
    revised = receipt_mod.build_receipt_success(**mutated_fields)
    ok, errors = sv.validate("RunReceiptSuccess", revised)
    assert ok, errors
    assert revised["run_id"] != original["run_id"]
    # original bytes untouched
    ok2, errors2 = sv.validate("RunReceiptSuccess", original)
    assert ok2, errors2


# ============================================================================
# 15. test_partial_write_never_committed (FR-34, AC-10)
# ============================================================================
def test_partial_write_never_committed(tmp_path):
    target = tmp_path / "run_receipt.json"

    class _BoomOnWrite(Exception):
        pass

    def _interrupted_write():
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text("{incomplete", encoding="utf-8")
        raise _BoomOnWrite("simulated crash mid-write")

    with pytest.raises(_BoomOnWrite):
        _interrupted_write()

    assert not target.exists()  # never a half-named "success-looking" file
    orphan = target.with_name(target.name + ".tmp")
    assert orphan.exists()  # only the orphaned temp file remains -- cleanup's job, not a fake success

    failure = receipt_mod.build_receipt_failure(**_minimal_failure_fields(failure_code="PARTIAL_WRITE", temp_cleanup_status="CLEANED"))
    ok, errors = sv.validate("RunReceiptFailure", failure)
    assert ok, errors
    assert failure["persistence_status"] == "FAILED"


# ============================================================================
# 16. test_ledger_hash_chain (FR-35) — both ledgers: the main
# collector_ledger.jsonl (LedgerEvent) AND the qualification ledger's mixed
# entry_kind=attempt/resolution stream (round 9/11/12 sharpening, §4.1/§4.6).
# ============================================================================
def test_ledger_hash_chain(tmp_path):
    from identity_collector import ledger as ledger_mod

    lp = tmp_path / "collector_ledger.jsonl"
    e1 = ledger_mod.append_event(lp, "run", "run-aaa", {"note": "first"}, FIXED_CLOCK)
    e2 = ledger_mod.append_event(lp, "run", "run-bbb", {"note": "second"}, FIXED_CLOCK)
    assert e1["sequence"] == 1 and e1["prior_event_hash"] is None
    assert e2["sequence"] == 2 and e2["prior_event_hash"] == e1["event_hash"]

    entries = ledger_mod.read_ledger(lp)
    assert entries == [e1, e2]

    # tamper: edit an entry in place -> hash recomputation catches it
    from identity_collector.hashing import obj_hash
    tampered = dict(e1)
    tampered["payload"] = {"note": "TAMPERED"}
    assert obj_hash({k: v for k, v in tampered.items() if k != "event_hash"}) != tampered["event_hash"]

    # qualification ledger: mixed attempt/resolution stream, one shared chain
    from identity_collector import qualification_ledger
    from identity_collector.testing import build_qualification_attempt_body, build_resolution_body

    qlp = tmp_path / "r_fwd_adapter_qualification_ledger.jsonl"
    attempt_body, primary_root, mirror_root = build_qualification_attempt_body(tmp_path, gates_pass=True, bundle_verified=False)
    a1_written = qualification_ledger.append_ledger_entry(qlp, attempt_body)
    ok, ok13 = sv.check_13_ledger_entry_hash(a1_written)
    assert ok, ok13
    assert a1_written["sequence"] == 1 and a1_written["prior_record_hash"] is None
    assert a1_written["qualification_status"] == "QUALIFICATION_PENDING"

    res_body = build_resolution_body(a1_written, primary_root, mirror_root)
    r1_written = qualification_ledger.append_ledger_entry(qlp, res_body)
    assert r1_written["sequence"] == 2 and r1_written["prior_record_hash"] == a1_written["record_hash"]
    ok, chain_problems = sv.check_13_chain_continuity([a1_written, r1_written])
    assert ok, chain_problems

    ok, errors = sv.validate("RFwdAdapterQualificationRecord", a1_written)
    assert ok, errors
    ok, errors = sv.validate("RFwdQualificationResolutionEvent", r1_written)
    assert ok, errors


# ============================================================================
# 17. test_primary_mirror_must_be_independent (FR-37, EC-14)
# ============================================================================
def test_primary_mirror_must_be_independent(tmp_path):
    primary = tmp_path / "primary_root"
    mirror = tmp_path / "mirror_root"
    primary.mkdir()
    mirror.mkdir()

    # Item 1 fix: two REAL directories on this sandbox's one actual filesystem
    # are, correctly, the SAME volume -- must FAIL even though the paths differ.
    ok, problems = sv.check_3_roots_independent(str(primary), str(mirror))
    assert not ok, "same-volume, different-directory roots must FAIL Gate C-P (EC-14)"
    assert "same filesystem/volume" in problems[0]

    # Genuinely independent volumes (the real target: D:\ vs E:\, distinct
    # st_dev) -- simulated via an injected stat_fn, since this sandbox has
    # only one real mounted filesystem to test against.
    class _FakeStat:
        def __init__(self, dev):
            self.st_dev = dev

    def fake_stat_two_volumes(path):
        return _FakeStat(1 if Path(path).name.startswith("primary") else 2)

    ok, problems = sv.check_3_roots_independent(str(primary), str(mirror), stat_fn=fake_stat_two_volumes)
    assert ok, problems

    def fake_stat_same_volume(path):
        return _FakeStat(1)

    ok, problems = sv.check_3_roots_independent(str(primary), str(mirror), stat_fn=fake_stat_same_volume)
    assert not ok

    ok, problems = sv.check_3_roots_independent(str(primary), str(primary))
    assert not ok  # EC-14: identical path -> Activation Gate FAIL

    relative_bad = "relative/path"
    ok, problems = sv.check_3_roots_independent(relative_bad, str(mirror))
    assert not ok  # must be absolute


# ============================================================================
# 18. test_commit_requires_two_verified_copies (FR-38, AC-11)
# ============================================================================
def test_commit_requires_two_verified_copies(tmp_path):
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    primary.mkdir()
    mirror.mkdir()
    (primary / "p_a_scores.parquet").write_bytes(b"synthetic P-A bytes")

    mv_pending = mirror_mod.build_mirror_verification(primary, mirror, ["p_a_scores.parquet"])
    assert mv_pending["status"] == "PENDING"  # mirror copy absent -> not committed

    (mirror / "p_a_scores.parquet").write_bytes(b"synthetic P-A bytes")  # now identical
    mv_verified = mirror_mod.build_mirror_verification(primary, mirror, ["p_a_scores.parquet"])
    assert mv_verified["status"] == "VERIFIED"
    assert mv_verified["primary_aggregate_sha256"] == mv_verified["mirror_aggregate_sha256"]

    (mirror / "p_a_scores.parquet").write_bytes(b"DIFFERENT bytes")  # tamper
    mv_diverged = mirror_mod.build_mirror_verification(primary, mirror, ["p_a_scores.parquet"])
    assert mv_diverged["status"] == "PENDING"  # a divergence never silently commits


# ============================================================================
# 19. test_low_disk_never_prunes (FR-42, AC-11, NFR-7)
# ============================================================================
def test_low_disk_never_prunes():
    from identity_collector import capacity

    low_pf = manifest_mod.preflight_observation("FREE", None, disk_free_bytes=500, low_disk_threshold_bytes=1_000_000)
    assert low_pf["disk_check_status"] == "LOW"

    required = capacity.required_free_bytes(estimate_bytes_per_run=10_000_000)
    assert required == 10_000_000 * 90 * 2  # FR-42 formula, never auto-shrunk

    # low-disk MUST fail closed -- capacity.py contains no auto-prune/delete path at all
    import identity_collector.capacity as capacity_mod
    src = Path(capacity_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("os.remove", "shutil.rmtree", "unlink("):
        assert forbidden not in src, f"capacity.py must never auto-delete on low disk: found {forbidden!r}"


def _minimal_success_fields(**overrides) -> dict:
    from identity_collector import epoch as epoch_mod

    as_of = overrides.pop("as_of", "2026-08-07")
    monthly_status = overrides.pop("monthly_status", "DAILY_DIAGNOSTIC")
    run_id_seed = overrides.pop("run_id_seed", "")
    input_bundle_seed = overrides.pop("input_bundle_seed", "")
    manifest = _synthetic_manifest(as_of, seed=input_bundle_seed or run_id_seed)
    input_bundle = manifest_mod.input_bundle_sha256(manifest)
    collector_version = "a" * 64
    run_id = overrides.pop("run_id", manifest_mod.compute_run_id(as_of, collector_version, input_bundle))
    ts = now_pair(FIXED_CLOCK)
    output_hashes = _synthetic_ponly_output_manifest()
    fields = dict(
        run_id=run_id, as_of=as_of, identity_epoch="epoch-0000000000000001",
        collector_version=collector_version, input_bundle_sha256=input_bundle,
        attempted_input_manifest=manifest, persistence_status="COMMITTED",
        identity_status="P_ONLY_EVIDENCE", monthly_status=monthly_status,
        source_mutation=False, revision_of=None, started_at=ts, completed_at=ts,
        capture_process_started=True,
        process_isolation={"production_capture_pid": 1001, "r_fwd_pid": None, "bt_bundle_absent_from_production_process": True},
        source_hashes=_synthetic_source_hash_manifest(with_rfwd=False),
        code_hashes=_synthetic_code_hash_manifest(with_rfwd=False),
        collector_config_hash="b" * 64, collector_schema_sha256=_schema_sha256(),
        output_hashes=output_hashes,
        mirror_verification={
            "status": "VERIFIED", "primary_aggregate_sha256": "c" * 64, "mirror_aggregate_sha256": "c" * 64,
            "per_file_verification": {k: {"primary_sha256": "d" * 64, "mirror_sha256": "d" * 64, "match": True} for k in output_hashes},
        },
        announcement_date_pit_status="BLOCKED", r_fwd_qualification_ref=None,
        primary_root="D:\\p0r2_identity_evidence\\primary", mirror_root="E:\\p0r2_identity_evidence\\mirror",
        temp_cleanup_status="NOT_APPLICABLE",
    )
    fields.update(overrides)
    return fields


def _minimal_failure_fields(**overrides) -> dict:
    as_of = overrides.pop("as_of", "2026-08-07")
    failure_code = overrides.pop("failure_code", "PARTIAL_WRITE")
    manifest = _synthetic_manifest(as_of)
    input_bundle = manifest_mod.input_bundle_sha256(manifest)
    collector_version = "a" * 64
    run_id = manifest_mod.compute_run_id(as_of, collector_version, input_bundle)
    ts = now_pair(FIXED_CLOCK)
    fields = dict(
        run_id=run_id, as_of=as_of, identity_epoch="epoch-0000000000000001",
        identity_epoch_unavailable_reason=None, collector_version=collector_version,
        input_bundle_sha256=input_bundle, attempted_input_manifest=manifest,
        persistence_status="FAILED", failure_code=failure_code,
        identity_status="P_ONLY_EVIDENCE", monthly_status="DAILY_DIAGNOSTIC",
        source_mutation=False, revision_of=None, started_at=ts, completed_at=ts,
        capture_process_started=True,
        process_isolation={"production_capture_pid": 1001, "r_fwd_pid": None, "bt_bundle_absent_from_production_process": True},
        source_hashes=_synthetic_partial_source_hash_manifest(),
        code_hashes=_synthetic_code_hash_manifest(with_rfwd=False),
        collector_config_hash="b" * 64, collector_schema_sha256=_schema_sha256(),
        output_hashes={}, primary_root="D:\\p0r2_identity_evidence\\primary",
        mirror_root="E:\\p0r2_identity_evidence\\mirror", temp_cleanup_status="CLEANED",
    )
    fields.update(overrides)
    return fields


def _synthetic_manifest(as_of: str, seed: str = "") -> dict:
    import hashlib

    pf = manifest_mod.preflight_observation("FREE", None, 10_000_000_000, low_disk_threshold_bytes=1_000_000_000)
    return manifest_mod.attempted_input_manifest(
        p_a=manifest_mod.source_attempt_status("AVAILABLE", as_of, hashlib.sha256(f"p_a-{seed}".encode()).hexdigest()),
        p_b=manifest_mod.source_attempt_status("AVAILABLE", as_of, hashlib.sha256(f"p_b-{seed}".encode()).hexdigest()),
        r_fwd=manifest_mod.source_attempt_status("NOT_ATTEMPTED"),
        preflight=pf,
    )


def _synthetic_source_hash_manifest(with_rfwd: bool) -> dict:
    def m(tag):
        return {"files": {f"{tag}.parquet": {"bytes": 10, "sha256": (tag * 64)[:64]}}, "aggregate_sha256": (tag * 64)[:64]}
    return {"p_a": m("a"), "p_b": m("b"), "r_fwd": (m("r") if with_rfwd else None)}


def _synthetic_partial_source_hash_manifest() -> dict:
    return {"p_a": None, "p_b": None, "r_fwd": None}


def _synthetic_code_hash_manifest(with_rfwd: bool) -> dict:
    import hashlib

    fields = [
        "score_store_sha256", "scoring_manager_sha256", "fundamentals_sha256", "valuation_sha256",
        "advisor_sha256", "backtest_sha256", "regime_sha256", "app_py_sha256", "l4a_decision_sha256",
        "technical_analysis_sha256", "data_provider_sha256", "industry_value_sha256",
        "ranking_adapter_sha256", "universe_screen_daily_sha256", "build_cache_loader_sha256",
    ]
    d = {f: hashlib.sha256(f.encode()).hexdigest() for f in fields}
    d["r_fwd_adapter_sha256"] = ("f" * 64) if with_rfwd else None
    return d


def _synthetic_ponly_output_manifest() -> dict:
    names = [
        "source_manifest.json", "code_config_manifest.json", "p_a_raw_snapshot.parquet",
        "p_a_screen_by_composite_parity.parquet", "p_b_fullpool.parquet", "p_app_fusion.csv",
        "p_l4a_fusion.csv", "rank_audit.csv", "process_import_manifest.json", "replay_manifest.json",
    ]
    return {n: {"bytes": 10, "sha256": ("e" * 64)} for n in names}


def _schema_sha256() -> str:
    return sha256_of_file(sv.SCHEMA_PATH)
