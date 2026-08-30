import os

import pytest

from research.b0_materializer.l3_temporal_snapshot import (
    TemporalSnapshotError, assert_append_only_continuity, sessions_through,
    snapshot_directory,
)


def test_normal_extension_is_admitted_but_history_is_not_rewritten():
    prior = [{"date": "2026-08-25", "close": 100.0},
             {"date": "2026-08-26", "close": 101.0}]
    extended = prior + [{"date": "2026-08-27", "close": 102.0}]
    got = assert_append_only_continuity(
        prior, extended, date_field="date", primary_key=("date",))
    assert got["appended_rows"] == 1
    assert got["prior_full_semantic_digest"] == \
        got["current_overlap_semantic_digest"]

    revised = [{"date": "2026-08-25", "close": 99.0}, *extended[1:]]
    with pytest.raises(TemporalSnapshotError,
                       match="HISTORICAL_SOURCE_REVISION"):
        assert_append_only_continuity(
            prior, revised, date_field="date", primary_key=("date",))


def test_coverage_regression_is_not_an_update():
    old = [{"date": "2026-08-25"}, {"date": "2026-08-26"}]
    with pytest.raises(TemporalSnapshotError,
                       match="SOURCE_COVERAGE_REGRESSION"):
        assert_append_only_continuity(
            old, old[:1], date_field="date", primary_key=("date",))


def test_decision_view_hides_later_snapshot_rows():
    assert sessions_through(
        ("2026-08-25", "2026-08-26", "2026-08-28"), "2026-08-26") == (
            "2026-08-25", "2026-08-26")


def test_snapshot_copy_is_byte_exact_and_refuses_reuse(tmp_path):
    source = tmp_path / "landing"
    source.mkdir()
    (source / "a.parquet").write_bytes(b"a")
    (source / "b.parquet").write_bytes(b"b")
    destination = tmp_path / "snapshot"
    got = snapshot_directory(str(source), str(destination),
                             extensions=(".parquet",))
    assert got["entry_count"] == 2
    assert (destination / "a.parquet").read_bytes() == b"a"
    with pytest.raises(TemporalSnapshotError, match="already exists"):
        snapshot_directory(str(source), str(destination),
                           extensions=(".parquet",))


def test_snapshot_refuses_unknown_entries_before_creating_destination(tmp_path):
    source = tmp_path / "landing"
    source.mkdir()
    (source / "known.parquet").write_bytes(b"a")
    (source / "unknown.txt").write_bytes(b"b")
    destination = tmp_path / "snapshot"
    with pytest.raises(TemporalSnapshotError, match="undeclared entry"):
        snapshot_directory(str(source), str(destination),
                           extensions=(".parquet",))
    assert not os.path.lexists(destination)
