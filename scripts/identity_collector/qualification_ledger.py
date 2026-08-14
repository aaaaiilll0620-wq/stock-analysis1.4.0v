"""research/p0_r2_identity_collector/r_fwd_adapter_qualification_ledger.jsonl —
append-only, hash-chained, mixed entry_kind=attempt/resolution stream
(phase_b_design_freeze.md §4, §4.6, §4.7). This module never writes under a
real primary_root/mirror_root (Stage 2 still PENDING) -- every path argument
here is caller-supplied (a pytest tmp_path pair in every Phase C test).
"""
import json
import uuid
from pathlib import Path

from identity_collector import SCHEMA_VERSION
from identity_collector import mirror as mirror_mod
from identity_collector.hashing import canonical_json, obj_hash, sha256_of_file
from identity_collector.timestamps import now_pair

# Item 4 fix: checkpoint building (PROTECTION_SCOPE + build_checkpoint) moved to
# checkpoint.py, which is generic across BOTH ledger types (this qualification
# ledger uses record_hash; collector_ledger.jsonl uses event_hash) -- the old
# copy here hardcoded record_hash and would have silently mis-checkpointed the
# main ledger had it ever been pointed there. Re-exported for compatibility.
from identity_collector.checkpoint import PROTECTION_SCOPE, build_checkpoint  # noqa: F401


def mint_record_id() -> str:
    return f"rfwdq-{uuid.uuid4()}"


def read_ledger(ledger_path) -> list:
    p = Path(ledger_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_ledger_entry(ledger_path, entry_body: dict) -> dict:
    """entry_body must NOT contain sequence/prior_record_hash/record_hash --
    those are computed here from the ledger's current tail (mechanical
    append-only, §4.1)."""
    for reserved in ("sequence", "prior_record_hash", "record_hash"):
        if reserved in entry_body:
            raise ValueError(f"entry_body must not pre-supply {reserved!r} -- computed by append_ledger_entry")
    prior = read_ledger(ledger_path)
    body = dict(entry_body)
    body["sequence"] = len(prior) + 1
    body["prior_record_hash"] = prior[-1]["record_hash"] if prior else None
    body["record_hash"] = obj_hash(body)
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(canonical_json(body) + "\n")
    return body


def build_qualification_bundle_location(record_id: str, primary_dir, mirror_dir, artifact_filenames: list) -> dict:
    uuid_part = record_id.removeprefix("rfwdq-")
    bundle_relative_root = f"r_fwd_qualification/{uuid_part}"
    primary_bundle_dir = Path(primary_dir) / bundle_relative_root
    mirror_bundle_dir = Path(mirror_dir) / bundle_relative_root
    artifact_set = {}
    for fname in artifact_filenames:
        p = primary_bundle_dir / fname
        artifact_set[fname] = {"bytes": p.stat().st_size, "sha256": sha256_of_file(p)}
    artifact_set["aggregate_sha256"] = mirror_mod.build_artifact_set_aggregate(artifact_set)
    mv = mirror_mod.build_mirror_verification(primary_bundle_dir, mirror_bundle_dir, artifact_filenames)
    return {
        "bundle_relative_root": bundle_relative_root,
        "artifact_set": artifact_set,
        "dual_copy_required": True,
        "mirror_verification": mv,
    }


def determine_qualification_status(membership_ok: bool, raw_score_ok: bool, isolation_ok: bool, future_access_ok: bool, bundle_verified: bool) -> str:
    if not (membership_ok and raw_score_ok and isolation_ok and future_access_ok):
        return "QUALIFICATION_FAILED"
    return "QUALIFIED" if bundle_verified else "QUALIFICATION_PENDING"


def effective_qualification_status(record_hash: str, ledger_entries: list) -> str:
    attempts = {e["record_hash"]: e for e in ledger_entries if e.get("entry_kind") == "attempt"}
    attempt = attempts.get(record_hash)
    if attempt is None:
        raise KeyError(f"no attempt entry with record_hash={record_hash}")
    if attempt["qualification_status"] in ("QUALIFIED", "QUALIFICATION_FAILED"):
        return attempt["qualification_status"]
    resolutions = [e for e in ledger_entries if e.get("entry_kind") == "resolution" and e["resolves_attempt_record_hash"] == record_hash]
    if resolutions:
        return sorted(resolutions, key=lambda r: r["sequence"])[-1]["new_qualification_status"]
    return "QUALIFICATION_PENDING"
