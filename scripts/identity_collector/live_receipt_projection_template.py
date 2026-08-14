"""Frozen module path (collector_schema.json ProjectionTemplateIdentity.repo_relative_path
== "scripts/identity_collector/live_receipt_projection_template.py"). The
deterministic assembly function: placeholder_policy + actual_inputs ->
RunReceiptSuccess-shaped dict, per phase_b_design_freeze.md §8.
"""


def assemble_projected_receipt(placeholder_policy: dict, actual_inputs: dict) -> dict:
    ph = placeholder_policy
    ai = actual_inputs
    assembled = {
        "schema_version": "p0r2-collector-schema-v1",
        "run_id": ph["run_id_placeholder"],
        "as_of": ai["as_of"],
        "identity_epoch": ph["identity_epoch_placeholder"],
        "collector_version": ph["collector_version_placeholder"],
        "input_bundle_sha256": ph["input_bundle_sha256_placeholder"],
        "attempted_input_manifest": ph["attempted_input_manifest_placeholder"],
        "persistence_status": ai["persistence_status"],
        "identity_status": ai["identity_status"],
        "monthly_status": ai["monthly_status"],
        "source_mutation": ai["source_mutation"],
        "revision_of": ai["revision_of"],
        "started_at": ph["started_at_placeholder"],
        "completed_at": ph["completed_at_placeholder"],
        "capture_process_started": ai["capture_process_started"],
        "process_isolation": ai["process_isolation"],
        "source_hashes": ai["source_hashes"],
        "code_hashes": ai["code_hashes"],
        "collector_config_hash": ai["collector_config_hash"],
        "collector_schema_sha256": ai["collector_schema_sha256"],
        "output_hashes": ai["output_hashes_equivalent"],
        "mirror_verification": {
            "status": "VERIFIED",
            "primary_aggregate_sha256": ph["mirror_hash_placeholder"],
            "mirror_aggregate_sha256": ph["mirror_hash_placeholder"],
            "per_file_verification": {
                fname: {"primary_sha256": ph["mirror_hash_placeholder"], "mirror_sha256": ph["mirror_hash_placeholder"], "match": True}
                for fname in ai["output_hashes_equivalent"]
            },
        },
        "announcement_date_pit_status": ai["announcement_date_pit_status"],
        "r_fwd_qualification_ref": ai["r_fwd_qualification_ref"],
        "primary_root": ai["primary_root"],
        "mirror_root": ai["mirror_root"],
        "temp_cleanup_status": ai["temp_cleanup_status"],
    }
    return assembled
