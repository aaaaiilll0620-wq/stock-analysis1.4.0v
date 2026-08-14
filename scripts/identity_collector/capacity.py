"""NFR-7 capacity (erratum E2 rev.9, APPROVED): bootstrap dry-run estimate,
P95 switch after 20 live runs. CapacityDryRunReceipt/Report are explicitly
NOT RunReceipts (FR-42a) -- never written under primary_root/mirror_root,
never carry a run_id.
"""
import math

from identity_collector import SCHEMA_VERSION
from identity_collector import schema_validation as sv
from identity_collector.hashing import canonical_json, obj_hash
from identity_collector.live_receipt_projection_template import assemble_projected_receipt

BOOTSTRAP_MULTIPLIER = 1.5
SAFETY_MULTIPLIER = 2
SCHEDULED_RUNS_HORIZON = 90
P95_WINDOW = 20

_POLICY_PROPS = sv.SCHEMA["definitions"]["LiveReceiptProjectionPlaceholderPolicy"]["properties"]


def placeholder_policy() -> dict:
    """Reads every placeholder value straight from the frozen schema's own
    `const`s -- never hand-copied, so it cannot silently drift from
    collector_schema.json revision 13."""
    return {k: _POLICY_PROPS[k]["const"] for k in (
        "run_id_placeholder", "identity_epoch_placeholder", "collector_version_placeholder",
        "input_bundle_sha256_placeholder", "attempted_input_manifest_placeholder",
        "live_timestamp_format", "started_at_placeholder", "completed_at_placeholder",
        "mirror_hash_placeholder", "conservatism_note",
    )}


def bootstrap_bytes_per_run(attempt_total_bytes_list: list) -> int:
    return math.ceil(BOOTSTRAP_MULTIPLIER * max(attempt_total_bytes_list))


def required_free_bytes(estimate_bytes_per_run: int) -> int:
    """FR-42: estimate_bytes_per_run * 90 * 2."""
    return estimate_bytes_per_run * SCHEDULED_RUNS_HORIZON * SAFETY_MULTIPLIER


def capacity_estimate(bootstrap_bytes: int, recent_live_run_bytes: list) -> int:
    """NFR-7(b): first 20 live runs use bootstrap. NFR-7(c): after 20, use
    max(bootstrap, P95(last 20)) -- bootstrap is a floor that only rises."""
    if len(recent_live_run_bytes) < P95_WINDOW:
        return bootstrap_bytes
    window = sorted(recent_live_run_bytes[-P95_WINDOW:])
    idx = min(math.ceil(0.95 * len(window)) - 1, len(window) - 1)
    return max(bootstrap_bytes, window[idx])


def build_projection_template_identity(*, template_version, repo_relative_path, git_blob_sha1, reachable_commit_sha1, content_sha256, durable_copy_path, durable_copy_bytes, durable_copy_sha256) -> dict:
    return {
        "template_version": template_version,
        "repo_relative_path": repo_relative_path,
        "git_blob_sha1": git_blob_sha1,
        "reachable_commit_sha1": reachable_commit_sha1,
        "content_sha256": content_sha256,
        "durable_copy": {"relative_path": durable_copy_path, "bytes": durable_copy_bytes, "sha256": durable_copy_sha256},
    }


def build_live_receipt_projection(projection_template: dict, actual_inputs: dict) -> dict:
    policy = placeholder_policy()
    assembled = assemble_projected_receipt(policy, actual_inputs)
    ok, errors = sv.validate("ProjectedRunReceipt", assembled)
    if not ok:
        raise ValueError(f"assembled projection is not a valid ProjectedRunReceipt: {[str(e) for e in errors[:3]]}")
    projected_sha = obj_hash(assembled)
    projected_bytes = len(canonical_json(assembled).encode("utf-8"))
    return {
        "schema_version": SCHEMA_VERSION,
        "projection_only": True,
        "projection_template": projection_template,
        "placeholder_policy": policy,
        "actual_inputs": actual_inputs,
        "projected_object_sha256": projected_sha,
        "projected_object_bytes": projected_bytes,
    }


def build_capacity_dry_run_receipt(*, as_of, sizing_mode, started_at, completed_at, r_fwd_artifacts_included, payload_files, elapsed_seconds, source_hashes, code_hashes, collector_config_hash, collector_schema_sha256, live_receipt_projection) -> dict:
    payload_bytes = sum(v["bytes"] for v in payload_files.values())
    payload_sha256 = obj_hash(payload_files)
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "sizing_mode": sizing_mode,
        "started_at": started_at,
        "completed_at": completed_at,
        "artifact_set_complete": True,
        "r_fwd_artifacts_included": r_fwd_artifacts_included,
        "payload_files": payload_files,
        "payload_bytes": payload_bytes,
        "payload_sha256": payload_sha256,
        "live_receipt_projection": live_receipt_projection,
        "elapsed_seconds": elapsed_seconds,
        "source_hashes": source_hashes,
        "code_hashes": code_hashes,
        "collector_config_hash": collector_config_hash,
        "collector_schema_sha256": collector_schema_sha256,
    }


def attempt_total_bytes(receipt: dict) -> int:
    return receipt["payload_bytes"] + receipt["live_receipt_projection"]["projected_object_bytes"]


def build_capacity_dry_run_report(*, generated_at, sizing_mode, attempts: list, clock=None) -> dict:
    if len(attempts) != 3 or {a["receipt"]["as_of"] for a in attempts} != {"2026-08-07", "2026-08-10", "2026-08-11"}:
        raise ValueError("capacity dry-run report requires exactly 3 attempts, one per the 3 frozen P-B dates")
    totals = [attempt_total_bytes(a["receipt"]) for a in attempts]
    bootstrap = bootstrap_bytes_per_run(totals)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "sizing_mode": sizing_mode,
        "attempts": attempts,
        "bootstrap_bytes_per_run": bootstrap,
        "bootstrap_formula": "ceil(1.5 * max(attempts[*].attempt_total_bytes))",
    }


def build_report_attempt(receipt: dict) -> dict:
    receipt_sha256 = obj_hash(receipt)
    receipt_bytes = len(canonical_json(receipt).encode("utf-8"))
    return {
        "receipt": receipt,
        "receipt_sha256": receipt_sha256,
        "receipt_bytes": receipt_bytes,
        "attempt_total_bytes": attempt_total_bytes(receipt),
    }
