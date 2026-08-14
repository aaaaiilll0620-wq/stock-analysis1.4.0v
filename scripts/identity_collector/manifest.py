"""AttemptedInputManifest / PreflightObservation / FR-31 run_id (item 1 of
collector_schema.json's own design notes: "ALWAYS computable, regardless of
how early a run fails").
"""
from identity_collector.hashing import obj_hash

DISK_FREE_BYTES_MAX = 9223372036854775807  # int64 max — PreflightObservation.disk_free_bytes maximum
LOCK_HOLDER_PID_MAX = 4294967295  # Windows DWORD PID ceiling — PreflightObservation.lock_holder_pid maximum


def preflight_observation(lock_state: str, lock_holder_pid, disk_free_bytes, low_disk_threshold_bytes: int) -> dict:
    if lock_state in ("HELD", "STALE_DETECTED"):
        if lock_holder_pid is None:
            raise ValueError(f"lock_state={lock_state} requires a real lock_holder_pid")
    else:
        lock_holder_pid = None

    if disk_free_bytes is None:
        disk_check_status = "UNKNOWN"
    elif disk_free_bytes < low_disk_threshold_bytes:
        disk_check_status = "LOW"
    else:
        disk_check_status = "OK"
    if disk_check_status == "UNKNOWN":
        disk_free_bytes = None

    return {
        "lock_state": lock_state,
        "lock_holder_pid": lock_holder_pid,
        "disk_check_status": disk_check_status,
        "disk_free_bytes": disk_free_bytes,
    }


def source_attempt_status(status: str, observed_date=None, aggregate_sha256=None) -> dict:
    if status == "AVAILABLE":
        if observed_date is None or aggregate_sha256 is None:
            raise ValueError("AVAILABLE requires observed_date and aggregate_sha256")
    else:
        observed_date, aggregate_sha256 = None, None
    return {"status": status, "observed_date": observed_date, "aggregate_sha256": aggregate_sha256}


def attempted_input_manifest(p_a: dict, p_b: dict, r_fwd: dict, preflight: dict) -> dict:
    return {"p_a": p_a, "p_b": p_b, "r_fwd": r_fwd, "preflight": preflight}


def input_bundle_sha256(manifest: dict) -> str:
    return obj_hash(manifest)


def compute_run_id(as_of: str, collector_version: str, input_bundle_sha256_value: str) -> str:
    """FR-31, unconditional: sha256_hex(canonical_json({as_of, collector_version,
    input_bundle_sha256}, sort_keys=true)). No other formula exists for any receipt type."""
    return obj_hash({"as_of": as_of, "collector_version": collector_version, "input_bundle_sha256": input_bundle_sha256_value})


# §6a receipt taxonomy — pre-source failure_code -> identity_epoch_unavailable_reason, 1:1
FAILURE_CODE_TO_EPOCH_UNAVAILABLE_REASON = {
    "LOCK_HELD": "LOCK_HELD_BEFORE_CAPTURE",
    "LOW_DISK": "LOW_DISK_BEFORE_CAPTURE",
    "MISSING_P_A": "P_A_NOT_CAPTURED_BEFORE_EPOCH_READ",
    "MISSING_P_B": "P_B_NOT_CAPTURED_BEFORE_EPOCH_READ",
    "DATE_MISMATCH": "DATE_MISMATCH_BEFORE_EPOCH_READ",
    "SOURCE_DATE_CONFLICT": "SOURCE_DATE_CONFLICT_BEFORE_EPOCH_READ",
}
PRE_SOURCE_FAILURE_CODES = frozenset(FAILURE_CODE_TO_EPOCH_UNAVAILABLE_REASON)
POST_SOURCE_FAILURE_CODES = frozenset({"HASH_MISMATCH", "SCHEMA_FAILURE", "PARTIAL_WRITE"})
