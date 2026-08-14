"""Shared SYNTHETIC fixture builders for Phase C tests only -- not part of the
collector's runtime API, never imported by cli.py or any other production
module in this package. Every builder here writes only under a caller-supplied
tmp_path; none ever touches a real primary_root/mirror_root or production
source.
"""
from pathlib import Path

from identity_collector import SCHEMA_VERSION
from identity_collector import mirror as mirror_mod
from identity_collector import qualification_ledger
from identity_collector import r_fwd_adapter
from identity_collector import schema_validation as sv
from identity_collector.timestamps import now_pair

FIXED_CLOCK_UTC = "2026-08-07T01:00:00+00:00"


def _clock():
    from datetime import datetime, timezone
    return datetime(2026, 8, 7, 1, 0, 0, tzinfo=timezone.utc)


ARTIFACT_FILENAMES = ["process_import_manifest.json", "future_input_access_trace.json"]


def write_bundle_artifact_files(tmp_path: Path, uuid_part: str, primary_root: Path, mirror_root: Path, mismatch: bool = False) -> None:
    bundle_rel = f"r_fwd_qualification/{uuid_part}"
    for root in (primary_root, mirror_root):
        d = Path(root) / bundle_rel
        d.mkdir(parents=True, exist_ok=True)
    (Path(primary_root) / bundle_rel / "process_import_manifest.json").write_text('{"imports":["numpy","pandas"]}', encoding="utf-8")
    (Path(mirror_root) / bundle_rel / "process_import_manifest.json").write_text('{"imports":["numpy","pandas"]}', encoding="utf-8")
    (Path(primary_root) / bundle_rel / "future_input_access_trace.json").write_text('{"reached":[]}', encoding="utf-8")
    mirror_content = '{"reached":["TAMPERED"]}' if mismatch else '{"reached":[]}'
    (Path(mirror_root) / bundle_rel / "future_input_access_trace.json").write_text(mirror_content, encoding="utf-8")


def build_qualification_attempt_body(tmp_path: Path, *, gates_pass: bool = True, bundle_verified: bool = True) -> dict:
    """Returns an entry_body ready for qualification_ledger.append_ledger_entry
    (no sequence/prior_record_hash/record_hash yet)."""
    primary_root = tmp_path / "primary"
    mirror_root = tmp_path / "mirror"
    record_id = qualification_ledger.mint_record_id()
    uuid_part = record_id.removeprefix("rfwdq-")
    write_bundle_artifact_files(tmp_path, uuid_part, primary_root, mirror_root)
    if not bundle_verified:
        # leave mirror copy absent -> MirrorVerification.status stays PENDING
        import shutil
        shutil.rmtree(Path(mirror_root) / f"r_fwd_qualification/{uuid_part}")

    bundle_location = qualification_ledger.build_qualification_bundle_location(record_id, primary_root, mirror_root, ARTIFACT_FILENAMES)

    isolation_audit = r_fwd_adapter.build_process_isolation_audit(
        r_fwd_process={"pid": 2001, "executable_path": "C:\\collector\\r_fwd.exe", "argv_sha256": "a" * 64, "started_at": now_pair(_clock)},
        production_capture_process={"pid": 2002, "executable_path": "C:\\collector\\capture.exe", "argv_sha256": "b" * 64, "started_at": now_pair(_clock)},
        import_manifest_artifact={"artifact_role": "PROCESS_IMPORT_MANIFEST", "relative_path": "process_import_manifest.json",
                                    "bytes": bundle_location["artifact_set"]["process_import_manifest.json"]["bytes"],
                                    "sha256": bundle_location["artifact_set"]["process_import_manifest.json"]["sha256"]},
        bt_bundle_absent_from_production_process=gates_pass,
        notes="ok" if gates_pass else "bt_bundle leaked",
    )
    future_audit = r_fwd_adapter.build_future_input_access_audit(
        method="STATIC_IMPORT_GRAPH", audit_tool_sha256="c" * 64,
        audited_entrypoint="scripts.identity_collector.r_fwd_adapter:compute_membership",
        forbidden_targets_reached=[] if gates_pass else ["exec_ret.parquet"],
        evidence_artifact={"artifact_role": "FUTURE_INPUT_ACCESS_TRACE", "relative_path": "future_input_access_trace.json",
                             "bytes": bundle_location["artifact_set"]["future_input_access_trace.json"]["bytes"],
                             "sha256": bundle_location["artifact_set"]["future_input_access_trace.json"]["sha256"]},
        notes="ok" if gates_pass else "forbidden target reached",
    )
    oracle_membership = {f"{2005 + i // 12}-{(i % 12) + 1:02d}-28": ["2330", "2317"] for i in range(255)}
    adapter_membership = dict(oracle_membership) if gates_pass else {**oracle_membership, "2005-01-28": ["2330"]}
    membership_result = r_fwd_adapter.membership_parity_result(adapter_membership, oracle_membership)
    raw_score_result = r_fwd_adapter.raw_score_parity_result(
        {"2330": 71.2, "2317": 55.0}, {"2330": 71.2, "2317": 55.0} if gates_pass else {"2330": 71.2 + 1e-6, "2317": 55.0},
    )
    qualification_status = qualification_ledger.determine_qualification_status(
        membership_result["exact_match_count"] == 255, raw_score_result["within_tolerance"],
        isolation_audit["status"] == "PASS", future_audit["status"] == "PASS",
        bundle_location["mirror_verification"]["status"] == "VERIFIED",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "entry_kind": "attempt",
        "record_id": record_id,
        "generated_at": now_pair(_clock),
        "r_fwd_adapter_sha256": "d" * 64,
        "oracle_hashes": {
            "high52_lab_sha256": "09fbe6efa34e5c6e8481adafddad58d073970227c7804c8a269e6ed29b0f72f8"[:64],
            "dual100_lab_sha256": "526164361c54cd62ac38fdbb3661eeca658e0fec040385579fee17fe0b47f7f0"[:64],
            "canonical_universe_sha256": "a717f1f8e1c04efe4def04ae317e0fbd10d0340dbc6c06222eff35499e54e68b"[:64],
            "lab_paths_sha256": "8cb132fc436d26f41c579932f636ecfa947a27f964a728f01a8d5e453528d0b0"[:64],
            "build_arm_panel_sha256": "9f2fcb61581919153e3cd1f81e123f908106ba36aca0a297e0d6e5af9dbbd3b3"[:64],
        },
        "qualification_status": qualification_status,
        "bundle_location": bundle_location,
        "aggregate_hash_formula": mirror_mod.AGGREGATE_HASH_FORMULA,
        "membership_parity_result": membership_result,
        "raw_score_parity_result": raw_score_result,
        "process_isolation_audit": isolation_audit,
        "future_input_access_audit": future_audit,
    }, primary_root, mirror_root


def build_resolution_body(attempt_written: dict, primary_root: Path, mirror_root: Path) -> dict:
    uuid_part = attempt_written["record_id"].removeprefix("rfwdq-")
    bundle_rel = f"r_fwd_qualification/{uuid_part}"
    # re-create the mirror copy so the bundle can now verify
    write_bundle_artifact_files(None, uuid_part, primary_root, mirror_root)
    mv = mirror_mod.build_mirror_verification(Path(primary_root) / bundle_rel, Path(mirror_root) / bundle_rel, ARTIFACT_FILENAMES)
    return {
        "schema_version": SCHEMA_VERSION,
        "entry_kind": "resolution",
        "resolves_attempt_record_id": attempt_written["record_id"],
        "resolves_attempt_record_hash": attempt_written["record_hash"],
        "previous_qualification_status": "QUALIFICATION_PENDING",
        "new_qualification_status": "QUALIFIED",
        "mirror_verification": mv,
        "generated_at": now_pair(_clock),
    }
