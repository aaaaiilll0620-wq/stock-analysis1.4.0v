# -*- coding: utf-8 -*-
"""Run-scoped immutable input snapshots and temporal continuity guards.

Landing directories are mutable ingestion surfaces.  A formal L3 run consumes
only copied bytes under its own immutable run directory.  A later landing
update is admitted when it only appends dates; changing an already-observed row
is a source revision and fails loud.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil


TEMPORAL_SNAPSHOT_CONTRACT_VERSION = "b0_l3_temporal_snapshot@1"


class TemporalSnapshotError(RuntimeError):
    """The snapshot is incomplete, changed during copy, or revises history."""


def _canonical_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def semantic_digest(value) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def snapshot_directory(source: str, destination: str, *, extensions,
                       declared_subdirectories=()) -> dict:
    """Copy one flat source surface and prove the source did not move mid-copy.

    This is a staging operation.  ``destination`` must not exist and must be
    outside every formal run/lineage root until the caller has completed all
    validation and publishes the staged run exclusively.
    """
    source = os.path.abspath(source)
    destination = os.path.abspath(destination)
    allowed = {str(ext).lower() for ext in extensions}
    if not os.path.isdir(source):
        raise TemporalSnapshotError("source directory does not exist: %s" % source)
    if os.path.lexists(destination):
        raise TemporalSnapshotError(
            "snapshot destination already exists: %s" % destination)

    declared_dirs = set(declared_subdirectories)
    entries = []
    seen_dirs = []
    unknown = []
    for name in sorted(os.listdir(source)):
        path = os.path.join(source, name)
        if os.path.isdir(path) and not os.path.islink(path) and name in declared_dirs:
            seen_dirs.append(name)
        elif os.path.islink(path) or not os.path.isfile(path):
            unknown.append(name)
        elif os.path.splitext(name)[1].lower() not in allowed:
            unknown.append(name)
        else:
            entries.append(name)
    if unknown:
        raise TemporalSnapshotError(
            "%d undeclared entry/entries in %s: %s"
            % (len(unknown), source, unknown[:20]))
    if not entries:
        raise TemporalSnapshotError("source directory is empty: %s" % source)

    os.makedirs(destination)
    inventory = []
    try:
        for name in entries:
            src = os.path.join(source, name)
            dst = os.path.join(destination, name)
            before = os.stat(src)
            shutil.copy2(src, dst)
            after = os.stat(src)
            if (before.st_size, before.st_mtime_ns) != \
                    (after.st_size, after.st_mtime_ns):
                raise TemporalSnapshotError(
                    "source changed while being copied: %s" % src)
            src_hash = _file_sha256(src)
            dst_hash = _file_sha256(dst)
            if src_hash != dst_hash:
                raise TemporalSnapshotError(
                    "snapshot bytes disagree with source: %s" % src)
            inventory.append({"path": name.replace("\\", "/"),
                              "bytes": before.st_size,
                              "raw_sha256": dst_hash})
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "contract_version": TEMPORAL_SNAPSHOT_CONTRACT_VERSION,
        "source": source.replace("\\", "/"),
        "snapshot": destination.replace("\\", "/"),
        "entry_count": len(inventory),
        "declared_subdirectories_seen": sorted(seen_dirs),
        "raw_inventory_digest": semantic_digest(inventory),
        "entries": inventory,
    }


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_rows(rows, *, primary_key) -> list:
    rows = [dict(row) for row in rows]
    if not rows:
        raise TemporalSnapshotError("EMPTY_SOURCE")
    keys = tuple(primary_key)
    ordered = sorted(rows, key=lambda row: tuple(str(row[k]) for k in keys))
    identities = [tuple(str(row[k]) for k in keys) for row in ordered]
    if len(identities) != len(set(identities)):
        raise TemporalSnapshotError("DUPLICATE_PRIMARY_KEY")
    return ordered


def assert_append_only_continuity(previous_rows, current_rows, *,
                                  date_field: str, primary_key) -> dict:
    """Admit appended dates; reject mutation/deletion of the observed prefix."""
    previous = canonical_rows(previous_rows, primary_key=primary_key)
    current = canonical_rows(current_rows, primary_key=primary_key)
    prior_max = max(str(row[date_field]) for row in previous)
    current_max = max(str(row[date_field]) for row in current)
    if current_max < prior_max:
        raise TemporalSnapshotError("SOURCE_COVERAGE_REGRESSION")
    overlap = [row for row in current if str(row[date_field]) <= prior_max]
    if _canonical_bytes(previous) != _canonical_bytes(overlap):
        raise TemporalSnapshotError("HISTORICAL_SOURCE_REVISION")
    return {
        "prior_source_max_date": prior_max,
        "current_source_max_date": current_max,
        "prior_full_semantic_digest": semantic_digest(previous),
        "current_overlap_semantic_digest": semantic_digest(overlap),
        "current_full_semantic_digest": semantic_digest(current),
        "appended_rows": len(current) - len(overlap),
    }


def sessions_through(sessions, decision_as_of: str) -> tuple:
    """The decision view; snapshot coverage after ``decision_as_of`` is hidden."""
    return tuple(sorted({str(day) for day in sessions
                         if str(day) <= str(decision_as_of)}))


__all__ = [
    "TEMPORAL_SNAPSHOT_CONTRACT_VERSION",
    "TemporalSnapshotError",
    "assert_append_only_continuity",
    "canonical_rows",
    "semantic_digest",
    "sessions_through",
    "snapshot_directory",
]
