"""Canonical hashing — reuses scripts/build_v2_candidate.py's convention verbatim
(collector_schema.json Sha256Hex: "sha256(json.dumps(obj, ensure_ascii=True,
separators=(',',':'), sort_keys=True).encode('utf-8')).hexdigest() for objects,
or a streaming 8 MiB chunked sha256 for files"). Reimported, not reimplemented,
so there is exactly one canonicalization in this repository, not two that could
silently drift apart.
"""
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from build_v2_candidate import canonical_json_bytes, sha256_hex, sha256_of_file  # noqa: E402


def canonical_json(obj, *, sort_keys: bool = True) -> str:
    return canonical_json_bytes(obj, sort_keys=sort_keys).decode("utf-8")


def obj_hash(obj, *, sort_keys: bool = True) -> str:
    """sha256_hex over canonical_json(obj) — the object-hash half of Sha256Hex's
    two conventions. `sort_keys` defaults True (objects); pass False for arrays
    per build_v2_candidate.py's own note (sort_keys doesn't affect array order,
    kept explicit at call sites that hash arrays to avoid an implicit default)."""
    return sha256_hex(canonical_json_bytes(obj, sort_keys=sort_keys))


def hash_paths(paths) -> dict:
    """{str(path): sha256_of_file(path)} -- the reusable before/after snapshot
    for every "this action must not mutate X" assertion (AC-2, AC-15, ...)."""
    return {str(p): sha256_of_file(p) for p in paths}


__all__ = ["canonical_json", "obj_hash", "sha256_hex", "sha256_of_file", "canonical_json_bytes", "hash_paths"]
