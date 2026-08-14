"""collector_ledger.jsonl — the main evidence LedgerEvent stream (FR-35, §7).
Distinct from qualification_ledger.py's r_fwd_adapter_qualification_ledger.jsonl
(a separate file/chain, per phase_b_design_freeze.md).
"""
import json
from pathlib import Path

from identity_collector.hashing import canonical_json, obj_hash
from identity_collector.timestamps import now_pair


def read_ledger(ledger_path) -> list:
    p = Path(ledger_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_event(ledger_path, event_type: str, run_id: str, payload: dict, clock) -> dict:
    prior = read_ledger(ledger_path)
    body = {
        "sequence": len(prior) + 1,
        "event_type": event_type,
        "run_id": run_id,
        "prior_event_hash": prior[-1]["event_hash"] if prior else None,
        "payload": payload,
        "recorded_at": now_pair(clock),
    }
    body["event_hash"] = obj_hash(body)
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(canonical_json(body) + "\n")
    return body


def mirror_events_for_run(ledger_entries: list, run_id: str) -> list:
    return [e for e in ledger_entries if e["event_type"] == "mirror" and e["payload"]["run_id"] == run_id]


def build_mirror_recovery_payload(run_id: str, previous_status: str, new_status: str, mirror_verification, original_receipt: dict) -> dict:
    """FR-39/AC-11, §6.1: binds the recovery to the original receipt's ACTUAL
    bytes (not just its filenames) via original_receipt_sha256 +
    original_output_aggregate_sha256."""
    original_receipt_sha256 = obj_hash(original_receipt)
    original_output_aggregate_sha256 = original_receipt["mirror_verification"]["primary_aggregate_sha256"]
    return {
        "run_id": run_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "mirror_verification": mirror_verification,
        "original_receipt_sha256": original_receipt_sha256,
        "original_output_aggregate_sha256": original_output_aggregate_sha256,
    }


def append_mirror_recovery_event(ledger_path, run_id: str, previous_status: str, new_status: str, mirror_verification, original_receipt: dict, clock) -> dict:
    """Item 3 fix: the ONLY sanctioned way to append a 'mirror' recovery event.
    Runs semantic check #11 (key-set equality + per-file hash equality against
    the original receipt's REAL output_hashes) BEFORE writing anything -- a
    recovery event that is missing files, names extra files, or diverges on
    any hash can no longer enter the ledger through this path at all. (Calling
    the generic `append_event` directly for event_type="mirror" bypasses this
    and is no longer the documented way to record a recovery.)"""
    from identity_collector import schema_validation as sv

    payload = build_mirror_recovery_payload(run_id, previous_status, new_status, mirror_verification, original_receipt)
    if new_status == "VERIFIED":
        ok, problems = sv.check_11_mirror_recovery_per_file(payload, original_receipt)
        if not ok:
            raise ValueError(f"mirror recovery failed check #11 -- refusing to append: {problems}")
    return append_event(ledger_path, "mirror", run_id, payload, clock)
