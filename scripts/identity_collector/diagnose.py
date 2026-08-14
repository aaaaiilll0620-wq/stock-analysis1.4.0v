"""Phase H cause taxonomy (Phase H itself already archived, commit `099b9b15`
per research/p0_r2_identity_collector/history_gap_*). Phase C only needs the
decision rule re-testable in isolation: FR-4 (fixed enum), FR-5 (deletion
claims need real evidence), AC-2 (diagnosis never mutates).
"""
CAUSE_CODES = frozenset({
    "NOT_PRODUCED", "PRODUCED_THEN_DELETED", "PRODUCED_ELSEWHERE_NOT_SYNCED",
    "OVERWRITTEN_OR_TRUNCATED", "DATE_DISCOVERY_OR_FORMAT_BUG", "UNRESOLVED",
})


def adjudicate_cause(claimed_cause: str, deletion_evidence: list | None = None) -> str:
    if claimed_cause not in CAUSE_CODES:
        raise ValueError(f"unknown cause code {claimed_cause!r}; must be one of {sorted(CAUSE_CODES)}")
    if claimed_cause == "PRODUCED_THEN_DELETED" and not deletion_evidence:
        raise ValueError(
            "PRODUCED_THEN_DELETED requires deletion_evidence (manifest/log/commit/backup-listing/"
            "filesystem evidence) -- current absence of a file alone is never sufficient (FR-5)"
        )
    return claimed_cause


def record_protected_path_hashes(paths: list, hash_fn) -> dict:
    return {str(p): hash_fn(p) for p in paths}


def assert_protected_paths_unchanged(before: dict, after: dict) -> None:
    """AC-2: protected paths' content hashes MUST be identical before/after diagnosis."""
    changed = sorted(k for k in before if before[k] != after.get(k))
    if changed:
        raise AssertionError(f"diagnosis mutated protected paths: {changed}")
