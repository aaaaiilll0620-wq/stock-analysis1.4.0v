"""identity_epoch (FR-49/50/51/52) and collector_version (phase_b_design_freeze.md
§11's frozen formula, reproduced verbatim below).
"""
from identity_collector.hashing import obj_hash, sha256_of_file

# phase_b_design_freeze.md §11 — frozen, do not edit without a new prereg round.
IDENTITY_DEFINING_CONSTANTS = {
    "adv_floor_c2": 1000000, "fusion_pct": 20, "top_n": None, "p_a_top_limit": 3000,
    "r_fwd_min_cov": 1.0, "r_fwd_canonical": False, "tolerance": "1e-12",
    "listed_ok_data_start_cutoff": "2019-01-10", "publish_lag_days": 45,
    "dual100_cov_min_effective": 1.0,
}

# FR-49 — any change to one of these MUST open a new identity_epoch.
EPOCH_DEFINING_FIELDS = (
    "score_formula_version", "weights_version", "watchlist_build_universe_policy",
    "c2_formula_version", "adv_listed_rule_version", "rank_method_version",
    "fusion_pct", "collector_schema_sha256", "r_fwd_semantics_version",
)


def compute_identity_epoch(epoch_inputs: dict) -> str:
    missing = set(EPOCH_DEFINING_FIELDS) - set(epoch_inputs)
    if missing:
        raise ValueError(f"epoch_inputs missing required fields: {sorted(missing)}")
    digest = obj_hash({k: epoch_inputs[k] for k in EPOCH_DEFINING_FIELDS})
    return f"epoch-{digest[:16]}"


def compute_collector_version(collector_code_files: dict[str, str], collector_schema_sha256: str, resolved_callables: dict) -> str:
    """collector_code_files: {rel_path: absolute_path}. Hashes each file's real
    bytes (sha256_of_file), never a stored/asserted hash — same discipline as
    every other CodeHashManifest entry in this design."""
    file_hashes = {rel: sha256_of_file(path) for rel, path in sorted(collector_code_files.items())}
    return obj_hash({
        "collector_code_files": file_hashes,
        "collector_schema_sha256": collector_schema_sha256,
        "resolved_callables": resolved_callables,
        "identity_defining_constants": IDENTITY_DEFINING_CONSTANTS,
    })


def epoch_transition_required(old_epoch_inputs: dict, new_epoch_inputs: dict) -> bool:
    """FR-50: pure code refactor MAY continue the same epoch only after parity
    regression exact match -- callers decide that separately (out of this
    function's scope); this only detects whether an EPOCH-DEFINING field changed."""
    return any(old_epoch_inputs.get(k) != new_epoch_inputs.get(k) for k in EPOCH_DEFINING_FIELDS)
