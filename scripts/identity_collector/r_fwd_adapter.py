"""R-FWD prospective reference adapter (prereg §5/§10, FR-24/25/26/27/28).

Phase C scope note (disclosed in the final report's Limitations): this pass
qualifies the adapter's MECHANISM -- membership/tolerance/isolation/future-
access gates, and the append-only qualification ledger they populate -- using
a synthetic 255-month fixture standing in for the true frozen research panel
(`beat_0050.strategies.high52_lab.Panel` / `dual_confirm_mask`, commit
`5f3f5d31`). Running the adapter against that REAL panel is Phase D's "dry run
and parity" activity (prereg §12) -- explicitly out of scope for this Phase C
pass per user instruction to stop before Phase D.
"""
from identity_collector.timestamps import now_pair

FR28_FORBIDDEN_TARGETS = ["exec_ret.parquet", "obs_alpha.parquet"]


def membership_parity_result(adapter_membership: dict, oracle_membership: dict) -> dict:
    """Item 6 fix: previously only compared MEMBERSHIP CONTENT for keys
    present in oracle_membership, silently ignoring whether adapter_membership
    covered the exact same 255 month keys -- an adapter missing a month
    entirely (`.get(m, [])` defaulting to empty) was indistinguishable from an
    adapter that legitimately computed an empty membership for that month, and
    an adapter reporting EXTRA months outside the oracle's 255 was never
    checked at all. Key-set equality is now required first."""
    if len(oracle_membership) != 255:
        raise ValueError(f"oracle_membership must cover exactly 255 months (FR-25); got {len(oracle_membership)}")
    oracle_keys, adapter_keys = set(oracle_membership), set(adapter_membership)
    if oracle_keys != adapter_keys:
        missing = sorted(oracle_keys - adapter_keys)
        extra = sorted(adapter_keys - oracle_keys)
        raise ValueError(f"adapter/oracle month key sets differ -- missing={missing} extra={extra}")
    mismatched = sorted(m for m in oracle_membership if set(adapter_membership[m]) != set(oracle_membership[m]))
    return {
        "months_tested": 255,
        "exact_match_count": 255 - len(mismatched),
        "mismatched_months": mismatched,
    }


def raw_score_parity_result(adapter_scores: dict, oracle_scores: dict, tolerance: float = 1e-12) -> dict:
    common_keys = set(adapter_scores) & set(oracle_scores)
    if not common_keys:
        raise ValueError("no common raw-score keys between adapter and oracle -- degenerate input, cannot qualify")
    max_abs_diff = max(abs(adapter_scores[k] - oracle_scores[k]) for k in common_keys)
    return {
        "common_keys_count": len(common_keys),
        "max_abs_diff": max_abs_diff,
        "tolerance": "1e-12",
        "within_tolerance": max_abs_diff <= tolerance,
    }


def build_process_isolation_audit(
    r_fwd_process: dict, production_capture_process: dict,
    import_manifest_artifact: dict, bt_bundle_absent_from_production_process: bool,
    notes: str = "",
) -> dict:
    status = "PASS" if (
        r_fwd_process["pid"] != production_capture_process["pid"]
        and bt_bundle_absent_from_production_process
    ) else "FAIL"
    return {
        "status": status,
        "r_fwd_process": r_fwd_process,
        "production_capture_process": production_capture_process,
        "import_manifest_artifact": import_manifest_artifact,
        "bt_bundle_absent_from_production_process": bt_bundle_absent_from_production_process,
        "notes": notes,
    }


def build_future_input_access_audit(
    method: str, audit_tool_sha256: str, audited_entrypoint: str,
    forbidden_targets_reached: list, evidence_artifact: dict, notes: str = "",
    forbidden_targets: list = None,
) -> dict:
    forbidden_targets = list(forbidden_targets or FR28_FORBIDDEN_TARGETS)
    if not set(FR28_FORBIDDEN_TARGETS) <= set(forbidden_targets):
        raise ValueError("forbidden_targets must include both FR-28 targets: exec_ret.parquet, obs_alpha.parquet")
    status = "PASS" if not forbidden_targets_reached else "FAIL"
    return {
        "status": status,
        "method": method,
        "audit_tool_sha256": audit_tool_sha256,
        "audited_entrypoint": audited_entrypoint,
        "forbidden_targets": forbidden_targets,
        "forbidden_targets_reached": list(forbidden_targets_reached),
        "evidence_artifact": evidence_artifact,
        "notes": notes,
    }
