"""FR-37/38/39, MirrorVerification + AggregateHashFormula. Compares real files
on two independent roots (primary/mirror) -- callers pass real directories
(a pytest tmp_path pair in every Phase C test, never primary_root/mirror_root
proper, since those remain PENDING per Stage 2).
"""
from pathlib import Path

from identity_collector.hashing import obj_hash, sha256_of_file

AGGREGATE_HASH_FORMULA = {
    "formula": "sha256_hex(canonical_json({relative_path: member_sha256 for each file}, sort_keys=true))",
    "canonical_json_rule": "json.dumps(obj, ensure_ascii=True, separators=(',',':'), sort_keys=True)",
    "selectors": {
        "artifact_selector": "ArtifactFileEntry.sha256",
        "primary_selector": "MirrorFileComparisonEntry.primary_sha256",
        "mirror_selector": "MirrorFileComparisonEntry.mirror_sha256",
    },
    "sort_rule": "keys sorted by Unicode code point via sort_keys=True; no locale, no case folding, no path normalization",
    "encoding": "utf-8",
}


def build_mirror_verification(primary_dir, mirror_dir, filenames: list) -> dict:
    per_file = {}
    for fname in filenames:
        p_path = Path(primary_dir) / fname
        if not p_path.exists():
            raise FileNotFoundError(f"primary copy missing required file: {fname}")
        p_hash = sha256_of_file(p_path)
        m_path = Path(mirror_dir) / fname
        m_hash = sha256_of_file(m_path) if m_path.exists() else None
        per_file[fname] = {"primary_sha256": p_hash, "mirror_sha256": m_hash, "match": m_hash == p_hash}

    all_match = bool(per_file) and all(e["match"] for e in per_file.values())
    primary_agg = obj_hash({k: v["primary_sha256"] for k, v in per_file.items()})
    mirror_agg = obj_hash({k: v["mirror_sha256"] for k, v in per_file.items()}) if all_match else None
    return {
        "status": "VERIFIED" if all_match else "PENDING",
        "primary_aggregate_sha256": primary_agg,
        "mirror_aggregate_sha256": mirror_agg,
        "per_file_verification": per_file,
    }


def build_artifact_set_aggregate(artifact_entries: dict) -> str:
    """QualificationBundleLocation.artifact_set.aggregate_sha256 (check #22)."""
    return obj_hash({k: v["sha256"] for k, v in artifact_entries.items()})
