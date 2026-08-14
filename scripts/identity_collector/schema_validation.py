"""Loads research/p0_r2_identity_collector/collector_schema.json (frozen,
approved, revision 13) and exposes:

  - validate(def_name, instance) -> (bool, [jsonschema.ValidationError, ...])
    Draft-07 schema-layer validation against one named definition.

  - the semantic-layer checks collector_schema.json's own
    `semantic_validation_rules_note` numbers (#1-#24) -- the cross-field /
    cross-object rules JSON Schema alone cannot express. Each check function
    returns (ok: bool, problems: list[str]); ok=True iff problems is empty.

This module NEVER writes to primary_root/mirror_root and NEVER reads
production sources -- it is pure validation logic over caller-supplied dicts.
"""
import json
from pathlib import Path

from jsonschema import Draft7Validator, RefResolver

from identity_collector.hashing import obj_hash
from identity_collector.timestamps import check_same_instant

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "research" / "p0_r2_identity_collector" / "collector_schema.json"

with open(SCHEMA_PATH, encoding="utf-8") as _f:
    SCHEMA = json.load(_f)

_RESOLVER = RefResolver.from_schema(SCHEMA)


def validate(def_name: str, instance) -> tuple[bool, list]:
    schema = {"$ref": f"#/definitions/{def_name}"}
    validator = Draft7Validator(schema, resolver=_RESOLVER)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return (len(errors) == 0), errors


def require_valid(def_name: str, instance):
    """Raise with a readable message if `instance` doesn't validate -- the
    fail-closed helper implementation code calls before it ever writes
    anything (NFR-5)."""
    ok, errors = validate(def_name, instance)
    if not ok:
        msgs = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise ValueError(f"{def_name} failed schema validation: {msgs}")


# ---------------------------------------------------------------------------
# Semantic checks (schema-inexpressible, cross-field/cross-object)
# ---------------------------------------------------------------------------

def check_1_process_isolation_pids_differ(process_isolation_audit: dict) -> tuple[bool, list]:
    a = process_isolation_audit["r_fwd_process"]["pid"]
    b = process_isolation_audit["production_capture_process"]["pid"]
    if a == b:
        return False, [f"r_fwd_process.pid == production_capture_process.pid ({a})"]
    return True, []


def check_2_timestamp_pair_same_instant(pair: dict) -> tuple[bool, list]:
    if not check_same_instant(pair):
        return False, [f"utc/local_taipei do not name the same instant at +8:00: {pair}"]
    return True, []


def _nearest_existing_ancestor(path, stat_fn) -> str:
    """EC-14 / FR-37: a root need not exist yet at Gate C-P check time, but
    SOME ancestor directory always does -- walk up until stat_fn succeeds."""
    from pathlib import Path
    p = Path(path)
    seen = set()
    while True:
        try:
            stat_fn(str(p))
            return str(p)
        except (FileNotFoundError, OSError):
            parent = p.parent
            if parent == p or str(parent) in seen:
                raise FileNotFoundError(f"no existing ancestor found for {path}")
            seen.add(str(p))
            p = parent


def check_3_roots_independent(primary_root: str, mirror_root: str, stat_fn=None) -> tuple[bool, list]:
    """FR-37 / EC-14: same path -> FAIL (already caught by realpath equality).
    Same filesystem/volume with DIFFERENT directories -> ALSO FAIL -- a single
    disk failure would take out both copies, defeating dual-copy redundancy.
    `stat_fn(path) -> os.stat_result`-shaped callable, injectable so tests can
    simulate two genuinely independent volumes (this sandbox has only one real
    filesystem mounted, so a real cross-volume positive case can't be
    constructed without an injected stat backend)."""
    import os
    if stat_fn is None:
        stat_fn = os.stat
    if not (os.path.isabs(primary_root) and os.path.isabs(mirror_root)):
        return False, ["primary_root/mirror_root must both be absolute paths"]
    p, m = os.path.realpath(primary_root), os.path.realpath(mirror_root)
    if p == m:
        return False, [f"primary_root and mirror_root resolve to the same path: {p}"]
    try:
        p_dev = stat_fn(_nearest_existing_ancestor(p, stat_fn)).st_dev
        m_dev = stat_fn(_nearest_existing_ancestor(m, stat_fn)).st_dev
    except FileNotFoundError as e:
        return False, [str(e)]
    if p_dev == m_dev:
        return False, [f"primary_root and mirror_root are on the same filesystem/volume (st_dev={p_dev}) -- same-volume, different-directory still FAILS Gate C-P (EC-14)"]
    return True, []


def recompute_record_hash(record: dict, exclude=("record_hash",)) -> str:
    body = {k: v for k, v in record.items() if k not in exclude}
    return obj_hash(body)


def check_13_ledger_entry_hash(entry: dict) -> tuple[bool, list]:
    recomputed = recompute_record_hash(entry)
    if recomputed != entry.get("record_hash"):
        return False, [f"record_hash does not recompute: stored={entry.get('record_hash')} recomputed={recomputed}"]
    return True, []


def check_13_chain_continuity(entries: list) -> tuple[bool, list]:
    problems = []
    entries_sorted = sorted(entries, key=lambda e: e["sequence"])
    for i, e in enumerate(entries_sorted):
        expected_seq = i + 1
        if e["sequence"] != expected_seq:
            problems.append(f"sequence gap at position {i}: expected {expected_seq}, got {e['sequence']}")
        if e["sequence"] == 1:
            if e.get("prior_record_hash") is not None:
                problems.append("sequence==1 entry has non-null prior_record_hash")
        else:
            prev = entries_sorted[i - 1]
            if e.get("prior_record_hash") != prev.get("record_hash"):
                problems.append(f"entry sequence={e['sequence']} prior_record_hash does not equal predecessor's record_hash")
        ok, hash_problems = check_13_ledger_entry_hash(e)
        problems.extend(hash_problems)
    return len(problems) == 0, problems


def check_17_record_id_not_derived_from_hash(record_id: str, record_hash: str) -> tuple[bool, list]:
    uuid_part = record_id.split("-", 1)[1] if "-" in record_id else record_id
    if record_hash.startswith(uuid_part.replace("-", "")[:16]):
        return False, ["record_id looks like a prefix-derivative of record_hash (round-9 circular construction)"]
    return True, []


_CANONICAL_ARTIFACT_PATH = {
    "PROCESS_IMPORT_MANIFEST": "process_import_manifest.json",
    "FUTURE_INPUT_ACCESS_TRACE": "future_input_access_trace.json",
}


def check_19_bundle_paths(record_id: str, bundle_location: dict, process_isolation_audit: dict, future_input_access_audit: dict) -> tuple[bool, list]:
    problems = []
    uuid_part = record_id.removeprefix("rfwdq-")
    expected_root = f"r_fwd_qualification/{uuid_part}"
    if bundle_location["bundle_relative_root"] != expected_root:
        problems.append(f"bundle_relative_root {bundle_location['bundle_relative_root']!r} != expected {expected_root!r}")
    audits = {
        "PROCESS_IMPORT_MANIFEST": process_isolation_audit["import_manifest_artifact"],
        "FUTURE_INPUT_ACCESS_TRACE": future_input_access_audit["evidence_artifact"],
    }
    for role, artifact in audits.items():
        if artifact["relative_path"] != _CANONICAL_ARTIFACT_PATH[role]:
            problems.append(f"{role} artifact relative_path {artifact['relative_path']!r} != canonical {_CANONICAL_ARTIFACT_PATH[role]!r}")
    return len(problems) == 0, problems


def check_22_artifact_set_aggregate(artifact_set: dict) -> tuple[bool, list]:
    files = {k: v["sha256"] for k, v in artifact_set.items() if k != "aggregate_sha256"}
    recomputed = obj_hash(files)
    if recomputed != artifact_set.get("aggregate_sha256"):
        return False, [f"artifact_set.aggregate_sha256 does not recompute: stored={artifact_set.get('aggregate_sha256')} recomputed={recomputed}"]
    return True, []


def check_23_bundle_three_way_consistency(bundle_location: dict, process_isolation_audit: dict, future_input_access_audit: dict) -> tuple[bool, list]:
    problems = []
    artifact_set = bundle_location["artifact_set"]
    per_file = bundle_location["mirror_verification"]["per_file_verification"]
    audit_refs = {
        "process_import_manifest.json": process_isolation_audit["import_manifest_artifact"],
        "future_input_access_trace.json": future_input_access_audit["evidence_artifact"],
    }
    for fname, audit_ref in audit_refs.items():
        if fname not in artifact_set or fname not in per_file:
            problems.append(f"{fname} missing from artifact_set or mirror per_file_verification")
            continue
        a, p = artifact_set[fname], per_file[fname]
        if a["sha256"] != p["primary_sha256"]:
            problems.append(f"{fname}: artifact_set.sha256 != mirror per-file primary_sha256")
        if a["sha256"] != audit_ref["sha256"]:
            problems.append(f"{fname}: artifact_set.sha256 != audit evidence sha256")
        if a["bytes"] != audit_ref["bytes"]:
            problems.append(f"{fname}: artifact_set.bytes ({a['bytes']}) != audit evidence bytes ({audit_ref['bytes']})")
    ok_agg, agg_problems = check_22_artifact_set_aggregate(artifact_set)
    problems.extend(agg_problems)
    mv = bundle_location["mirror_verification"]
    if artifact_set.get("aggregate_sha256") != mv.get("primary_aggregate_sha256"):
        problems.append("artifact_set.aggregate_sha256 != mirror_verification.primary_aggregate_sha256")
    return len(problems) == 0, problems


def check_10_resolve_qualification_ref(ref: dict, attempts_by_hash: dict, resolutions_by_hash: dict, receipt_completed_at: dict) -> tuple[bool, str]:
    """Round 13 rule. attempts_by_hash/resolutions_by_hash: {record_hash: entry}."""
    attempt = attempts_by_hash.get(ref["record_hash"])
    if attempt is None or attempt.get("record_id") != ref["record_id"] or attempt.get("entry_kind") != "attempt":
        return False, "attempt does not resolve"
    if attempt["r_fwd_adapter_sha256"] != ref["r_fwd_adapter_sha256"]:
        return False, "r_fwd_adapter_sha256 mismatch"
    status = attempt["qualification_status"]
    if status == "QUALIFICATION_FAILED":
        return False, "attempt is QUALIFICATION_FAILED"
    if status == "QUALIFIED":
        if ref["resolution_record_hash"] is not None:
            return False, "attempt already QUALIFIED; resolution_record_hash must be null"
        return True, "self-sufficient"
    if status == "QUALIFICATION_PENDING":
        if ref["resolution_record_hash"] is None:
            return False, "PENDING attempt with no resolution_record_hash pinned"
        res = resolutions_by_hash.get(ref["resolution_record_hash"])
        if res is None or res.get("entry_kind") != "resolution":
            return False, "resolution_record_hash does not resolve to a real resolution event"
        if res["resolves_attempt_record_id"] != attempt["record_id"] or res["resolves_attempt_record_hash"] != attempt["record_hash"]:
            return False, "pinned resolution does not resolve THIS attempt"
        if res["new_qualification_status"] != "QUALIFIED":
            return False, "pinned resolution's new_qualification_status is not QUALIFIED"
        if res["generated_at"]["utc"] > receipt_completed_at["utc"]:
            return False, "pinned resolution's generated_at is after receipt completed_at"
        return True, "resolved via pinned resolution event"
    return False, "unknown qualification_status"


def check_24_resolution_matches_attempt_bundle(resolution: dict, attempt: dict) -> tuple[bool, list]:
    problems = []
    if resolution.get("entry_kind") != "resolution":
        problems.append("not a resolution entry")
        return False, problems
    if attempt.get("qualification_status") != "QUALIFICATION_PENDING":
        problems.append("attempt was not QUALIFICATION_PENDING at write time")
    if resolution["resolves_attempt_record_id"] != attempt["record_id"] or resolution["resolves_attempt_record_hash"] != attempt["record_hash"]:
        problems.append("resolution does not reference this attempt")
        return False, problems
    attempt_artifact_set = attempt["bundle_location"]["artifact_set"]
    res_per_file = resolution["mirror_verification"]["per_file_verification"]
    for fname in ("process_import_manifest.json", "future_input_access_trace.json"):
        if attempt_artifact_set[fname]["sha256"] != res_per_file[fname]["primary_sha256"]:
            problems.append(f"{fname}: resolution mirror_verification diverges from attempt's artifact_set")
    return len(problems) == 0, problems


def check_8_effective_persistence_status(receipt: dict, mirror_events_for_run: list) -> str:
    """mirror_events_for_run: LedgerEvent payloads (event_type=='mirror') for this run_id,
    in append order."""
    if receipt["persistence_status"] == "COMMITTED":
        return "COMMITTED"
    if receipt["persistence_status"] == "PENDING_MIRROR":
        verified = [e for e in mirror_events_for_run if e["payload"]["new_status"] == "VERIFIED"]
        if verified:
            return "COMMITTED"
        return "PENDING_MIRROR"
    return "FAILED"


def check_11_mirror_recovery_per_file(mirror_payload: dict, original_receipt: dict) -> tuple[bool, list]:
    """Item 3 fix (round 1): key-set equality (no missing, no extra) checked
    first and independently -- a recovery naming a SUBSET or SUPERSET of the
    original receipt's real output files no longer passes just because the
    keys it DID name hash-matched.

    Item 1 fix (round 2, P1): round 1 still had a real gap -- it verified
    `primary_sha256` against the ORIGINAL receipt but never verified
    `mirror_sha256` against `primary_sha256` AT ALL, never checked that the
    `match` flag reflected actual equality, never checked
    `primary_aggregate_sha256 == mirror_aggregate_sha256` (check #7's own
    rule, folded in here since check #7 is not independently invoked on the
    recovery path), and never validated `original_receipt_sha256` /
    `original_output_aggregate_sha256` against a real recomputation at all --
    a payload could have `primary_sha256` correct (matching the original) but
    `mirror_sha256` diverging into a DIFFERENT, INTERNALLY SELF-CONSISTENT set
    (its own aggregate would still recompute correctly FROM those wrong
    values), and this check would have accepted it as VERIFIED. All five are
    now checked."""
    problems = []
    mv = mirror_payload["mirror_verification"]
    if mv is None:
        return True, []  # legal only when new_status==PENDING; schema enforces the pairing

    original_outputs = original_receipt["output_hashes"]
    original_keys = set(original_outputs)
    recovery_keys = set(mv["per_file_verification"])
    missing = sorted(original_keys - recovery_keys)
    extra = sorted(recovery_keys - original_keys)
    if missing:
        problems.append(f"recovery per_file_verification is MISSING files the original receipt has: {missing}")
    if extra:
        problems.append(f"recovery per_file_verification names EXTRA files not in the original receipt: {extra}")

    for fname in sorted(original_keys & recovery_keys):
        entry = mv["per_file_verification"][fname]
        if entry["primary_sha256"] != original_outputs[fname]["sha256"]:
            problems.append(f"{fname}: recovery primary_sha256 != original output_hashes sha256")
        # THE actual definition of "the mirror copy is verified": its hash
        # must equal the primary copy's hash for this file, not merely be
        # internally self-consistent with the other mirror entries.
        if entry["mirror_sha256"] != entry["primary_sha256"]:
            problems.append(f"{fname}: mirror_sha256 != primary_sha256 -- mirror copy diverges from primary")
        actual_match = entry["mirror_sha256"] is not None and entry["mirror_sha256"] == entry["primary_sha256"]
        if entry.get("match") != actual_match:
            problems.append(f"{fname}: match={entry.get('match')!r} does not reflect actual hash equality (should be {actual_match})")

    recomputed_primary = obj_hash({k: v["primary_sha256"] for k, v in mv["per_file_verification"].items()})
    recomputed_mirror = obj_hash({k: v["mirror_sha256"] for k, v in mv["per_file_verification"].items()})
    if recomputed_primary != mv["primary_aggregate_sha256"]:
        problems.append("primary_aggregate_sha256 does not recompute")
    if mv["status"] == "VERIFIED":
        if recomputed_mirror != mv["mirror_aggregate_sha256"]:
            problems.append("mirror_aggregate_sha256 does not recompute")
        # check #7's rule, folded in: VERIFIED requires the two aggregates to
        # be EQUAL to each other, not merely each independently self-consistent.
        if mv["primary_aggregate_sha256"] != mv["mirror_aggregate_sha256"]:
            problems.append("primary_aggregate_sha256 != mirror_aggregate_sha256 (status=VERIFIED requires equality)")

    recomputed_receipt_sha256 = obj_hash(original_receipt)
    if mirror_payload["original_receipt_sha256"] != recomputed_receipt_sha256:
        problems.append("original_receipt_sha256 does not match a recomputed hash of the original receipt")
    original_own_aggregate = original_receipt["mirror_verification"]["primary_aggregate_sha256"]
    if mirror_payload["original_output_aggregate_sha256"] != original_own_aggregate:
        problems.append("original_output_aggregate_sha256 does not match the original receipt's own primary_aggregate_sha256")

    return len(problems) == 0, problems


def check_7_mirror_aggregates_equal(mv: dict) -> tuple[bool, list]:
    """Standalone form of the equality check folded into check #11 above --
    exposed separately so it can be run on any MirrorVerification object, not
    only inside a mirror-recovery payload (e.g. a run receipt's own
    mirror_verification at COMMIT time)."""
    if mv["status"] != "VERIFIED":
        return True, []
    if mv["primary_aggregate_sha256"] != mv["mirror_aggregate_sha256"]:
        return False, [f"primary_aggregate_sha256 ({mv['primary_aggregate_sha256'][:8]}...) != mirror_aggregate_sha256 ({mv['mirror_aggregate_sha256'][:8]}...) while status=VERIFIED"]
    return True, []


def check_20_checkpoint_record(record: dict, ledger_entries: list) -> tuple[bool, list]:
    """Item 4 fix: the on-disk tail's head-hash FIELD NAME depends on
    ledger_name -- collector_ledger.jsonl entries carry `event_hash`,
    r_fwd_adapter_qualification_ledger.jsonl entries carry `record_hash`.
    Previously hardcoded to `record_hash`, which would have silently failed
    (or worse, silently passed with a coincidental match) for the main
    ledger."""
    from identity_collector.checkpoint import hash_field_for
    from identity_collector.hashing import canonical_json

    problems = []
    payload = record["payload"]
    recomputed_sha = obj_hash(payload)
    recomputed_bytes = len(canonical_json(payload).encode("utf-8"))
    if recomputed_sha != record["payload_sha256"]:
        problems.append("payload_sha256 does not recompute from embedded payload")
    if recomputed_bytes != record["payload_bytes"]:
        problems.append("payload_bytes does not recompute from embedded payload")
    if payload["record_count"] != payload["head_sequence"]:
        problems.append("record_count != head_sequence")
    if len(ledger_entries) != payload["head_sequence"]:
        problems.append(f"on-disk ledger tail ({len(ledger_entries)} entries) != head_sequence ({payload['head_sequence']}) -- truncation")
    else:
        hash_field = hash_field_for(payload["ledger_name"])
        if ledger_entries and ledger_entries[-1][hash_field] != payload["head_record_hash"]:
            problems.append(f"on-disk ledger tail's last {hash_field} != head_record_hash")
    rel_path = record["storage"]["relative_path"]
    pf = record["storage"]["mirror_verification"]["per_file_verification"]
    if rel_path not in pf:
        problems.append(f"storage.relative_path {rel_path!r} not a key in per_file_verification")
    elif pf[rel_path]["primary_sha256"] != record["payload_sha256"]:
        problems.append("storage per-file primary_sha256 != payload_sha256")
    return len(problems) == 0, problems


def check_6_bootstrap_formula(attempt_total_bytes_list: list, bootstrap_bytes_per_run: int) -> tuple[bool, list]:
    import math
    expected = math.ceil(1.5 * max(attempt_total_bytes_list))
    if expected != bootstrap_bytes_per_run:
        return False, [f"bootstrap_bytes_per_run={bootstrap_bytes_per_run} != ceil(1.5*max(...))={expected}"]
    return True, []
