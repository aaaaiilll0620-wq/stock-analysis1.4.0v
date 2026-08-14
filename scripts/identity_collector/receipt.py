"""RunReceiptSuccess/Failure — atomic write (FR-34), idempotency (FR-32),
revision-on-source-mutation (FR-33). Every path here is caller-supplied
(a pytest tmp_path in every Phase C test) -- never a real primary_root.
"""
import json
import os
from pathlib import Path

from identity_collector import SCHEMA_VERSION
from identity_collector.hashing import canonical_json


def atomic_write_json(path, obj) -> None:
    """FR-34: temp path, then atomic rename. Never leaves a half-named target
    file if interrupted (only an orphaned .tmp, which cleanup can remove)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(canonical_json(obj), encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX and NTFS


def find_receipt_by_run_id(run_dir_root, run_id: str):
    """FR-32: same run identity re-run MUST be idempotent no-op, returning the
    existing receipt. Scans committed run_receipt.json files under
    run_dir_root (a per-run-directory tree, never scanned lazily mid-write)."""
    root = Path(run_dir_root)
    if not root.exists():
        return None
    for p in root.rglob("run_receipt.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if rec.get("run_id") == run_id:
            return rec
    return None


def determine_revision(new_input_bundle_sha256: str, prior_receipts_for_as_of: list) -> tuple[bool, str | None]:
    """FR-33: same as_of, different source bytes -> new revision. Only
    considers receipts that actually produced evidence (COMMITTED/
    PENDING_MIRROR); a prior FAILED attempt is not something to revise."""
    candidates = [r for r in prior_receipts_for_as_of if r.get("persistence_status") in ("COMMITTED", "PENDING_MIRROR")]
    if not candidates:
        return False, None
    latest = max(candidates, key=lambda r: r["completed_at"]["utc"])
    if latest["input_bundle_sha256"] == new_input_bundle_sha256:
        return False, None
    return True, latest["run_id"]


def build_receipt_success(**fields) -> dict:
    fields.setdefault("schema_version", SCHEMA_VERSION)
    required = (
        "run_id", "as_of", "identity_epoch", "collector_version", "input_bundle_sha256",
        "attempted_input_manifest", "persistence_status", "identity_status", "monthly_status",
        "source_mutation", "revision_of", "started_at", "completed_at", "capture_process_started",
        "process_isolation", "source_hashes", "code_hashes", "collector_config_hash",
        "collector_schema_sha256", "output_hashes", "mirror_verification",
        "announcement_date_pit_status", "r_fwd_qualification_ref", "primary_root", "mirror_root",
        "temp_cleanup_status",
    )
    missing = [f for f in required if f not in fields]
    if missing:
        raise ValueError(f"build_receipt_success missing fields: {missing}")
    return {"schema_version": fields.pop("schema_version"), **{k: fields[k] for k in required}}


def build_receipt_failure(**fields) -> dict:
    fields.setdefault("schema_version", SCHEMA_VERSION)
    required = (
        "run_id", "as_of", "identity_epoch", "identity_epoch_unavailable_reason", "collector_version",
        "input_bundle_sha256", "attempted_input_manifest", "persistence_status", "failure_code",
        "identity_status", "monthly_status", "source_mutation", "revision_of", "started_at",
        "completed_at", "capture_process_started", "process_isolation", "source_hashes", "code_hashes",
        "collector_config_hash", "collector_schema_sha256", "output_hashes", "primary_root",
        "mirror_root", "temp_cleanup_status",
    )
    missing = [f for f in required if f not in fields]
    if missing:
        raise ValueError(f"build_receipt_failure missing fields: {missing}")
    return {"schema_version": fields.pop("schema_version"), **{k: fields[k] for k in required}}
