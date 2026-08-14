"""LedgerHeadCheckpointPayload/Record — generic across BOTH ledger types.

Item 4 fix: `collector_ledger.jsonl` entries carry `event_hash`;
`r_fwd_adapter_qualification_ledger.jsonl` entries carry `record_hash`. The
previous checkpoint builder (formerly qualification_ledger.build_checkpoint)
hardcoded `record_hash`, which would have silently mis-checkpointed
collector_ledger.jsonl (KeyError at best, a wrong/absent head hash at worst)
had it ever been pointed at the main ledger. This module picks the right
field from `ledger_name` and is the single checkpoint builder for both.
"""
import json
from pathlib import Path

from identity_collector import SCHEMA_VERSION
from identity_collector import mirror as mirror_mod
from identity_collector.hashing import canonical_json, obj_hash
from identity_collector.timestamps import now_pair

HASH_FIELD_BY_LEDGER_NAME = {
    "collector_ledger.jsonl": "event_hash",
    "r_fwd_adapter_qualification_ledger.jsonl": "record_hash",
}

PROTECTION_SCOPE = {
    "detects": ["single_sided_ledger_truncation_without_checkpoint_update"],
    "does_not_detect": ["simultaneous_rollback_of_ledger_and_checkpoint_to_a_consistent_earlier_state"],
    "note": (
        "This checkpoint proves the ledger has not been shortened WITHOUT also rewriting the checkpoint "
        "(semantic check #20's tail-match). It provides NO protection if an actor rewrites both the ledger "
        "tail and this checkpoint together to an earlier, internally-consistent state -- "
        "head_sequence/head_record_hash/record_count/payload_sha256 would all still agree with each other "
        "and with the (rolled-back) ledger tail, just at an earlier point. Full protection against a "
        "simultaneous rollback would require an external, independently-controlled anchor (third-party "
        "timestamping, WORM storage, or an append log this collector does not itself control) -- out of "
        "scope for this design freeze. This is a deliberately NARROWED claim, not a claim of complete "
        "rollback protection; the earlier 'dual-copy durable, so tail-truncation becomes detectable' "
        "phrasing above must be read against this scope, not beyond it."
    ),
}


def read_ledger(ledger_path) -> list:
    """Both ledger types are line-delimited JSON with a `sequence` field --
    structurally interchangeable for reading; only the head-hash FIELD NAME
    differs (hash_field_for), never the read mechanics."""
    p = Path(ledger_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def hash_field_for(ledger_name: str) -> str:
    if ledger_name not in HASH_FIELD_BY_LEDGER_NAME:
        raise ValueError(f"unknown ledger_name {ledger_name!r}; must be one of {sorted(HASH_FIELD_BY_LEDGER_NAME)}")
    return HASH_FIELD_BY_LEDGER_NAME[ledger_name]


def build_checkpoint(ledger_path, ledger_name: str, primary_root, mirror_root, clock) -> dict:
    entries = read_ledger(ledger_path)
    if not entries:
        raise ValueError("cannot checkpoint an empty ledger")
    hash_field = hash_field_for(ledger_name)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ledger_name": ledger_name,
        "head_sequence": entries[-1]["sequence"],
        "head_record_hash": entries[-1][hash_field],
        "record_count": len(entries),
        "checkpointed_at": now_pair(clock),
    }
    payload_sha256 = obj_hash(payload)
    payload_bytes = len(canonical_json(payload).encode("utf-8"))
    rel_path = f"{ledger_name}.checkpoint.json"
    for root in (primary_root, mirror_root):
        p = Path(root) / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(canonical_json(payload), encoding="utf-8")
    mv = mirror_mod.build_mirror_verification(primary_root, mirror_root, [rel_path])
    return {
        "schema_version": SCHEMA_VERSION,
        "payload": payload,
        "payload_sha256": payload_sha256,
        "payload_bytes": payload_bytes,
        "storage": {"relative_path": rel_path, "dual_copy_required": True, "mirror_verification": mv},
        "protection_scope": PROTECTION_SCOPE,
    }
