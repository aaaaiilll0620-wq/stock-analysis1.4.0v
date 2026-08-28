# -*- coding: utf-8 -*-
"""O-H · the financials source directory must be enumerated, not globbed at.

`load_raw` used `glob("*.xlsx")`. A glob reports what it matched and says nothing
about what it skipped, so "the importer cannot read this file" and "there is no
such file" produced identical builds.

The live instance: on 2026-08-26 the export directory gained a UTF-16 `.csv` of
period 202606 and lost a workbook the previous receipt names. Neither event
raised anything. It turned out to be harmless, but that was established by hand
afterwards — which is the property the builder is supposed to establish itself.

These tests are about the guard alone. They parse nothing, build no panel and
write no receipt.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

from build_financials_pit import (                            # noqa: E402
    ACCEPTED_SOURCE_EXTENSIONS,
    _entry_kind,
    assert_source_dir_holds_only_accepted_files,
)


def _touch(d, name: str, content: bytes = b"x") -> str:
    p = os.path.join(str(d), name)
    with open(p, "wb") as fh:
        fh.write(content)
    return p


# --- the accepted case ---------------------------------------------------------

def test_a_pure_xlsx_directory_passes_and_returns_every_workbook(tmp_path):
    _touch(tmp_path, "20260806090633.xlsx")
    _touch(tmp_path, "202606 財報583家 8-10.xlsx")

    got = assert_source_dir_holds_only_accepted_files(str(tmp_path))

    # sorted by name: "202606 " < "2026080" at index 5 ('6' < '8')
    assert [os.path.basename(p) for p in got] == [
        "202606 財報583家 8-10.xlsx", "20260806090633.xlsx"]


def test_the_returned_list_is_what_the_builder_reads(tmp_path):
    """The guard's output IS the source list, so the two cannot disagree."""
    a = _touch(tmp_path, "a.xlsx")
    b = _touch(tmp_path, "b.xlsx")
    assert sorted(assert_source_dir_holds_only_accepted_files(str(tmp_path))) == \
        sorted([a, b])


# --- subdirectories are unknowns, not absences ---------------------------------
#
# The export surface is expected to be flat. An unexpected subtree is exactly
# where an exporter would drop a new data file, and a non-recursive glob would
# never mention it — the same lineage risk as the file a flat glob skips.

def test_an_empty_subdirectory_aborts(tmp_path):
    """Empty TODAY is not a property of the directory, only of this moment."""
    _touch(tmp_path, "real.xlsx")
    os.makedirs(os.path.join(str(tmp_path), "archive"))

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    assert "archive" in msg
    assert "<directory>" in msg


def test_a_subdirectory_containing_a_data_file_aborts(tmp_path):
    """The case the flat-glob would hide completely: data one level down.
    A readable format one level down is still invisible to a flat listing."""
    _touch(tmp_path, "real.xlsx")
    sub = os.path.join(str(tmp_path), "2026Q2")
    os.makedirs(sub)
    _touch(sub, "financials.csv", b"\xff\xfe")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    assert "2026Q2" in msg
    assert "<directory>" in msg


def test_a_subdirectory_of_xlsx_also_aborts(tmp_path):
    """Even a subtree full of ACCEPTED formats is an unknown: nothing has said
    whether those workbooks belong to this panel."""
    _touch(tmp_path, "real.xlsx")
    sub = os.path.join(str(tmp_path), "nested")
    os.makedirs(sub)
    _touch(sub, "more.xlsx")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    assert "<directory>" in str(exc.value)


def test_a_directory_named_like_a_workbook_is_still_a_directory(tmp_path):
    """Classification is by entry type first, never by the name's suffix."""
    _touch(tmp_path, "real.xlsx")
    os.makedirs(os.path.join(str(tmp_path), "decoy.xlsx"))

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    assert "decoy.xlsx" in msg
    assert "<directory>" in msg


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlink support")
def test_a_symlink_is_rejected_and_labelled_as_one(tmp_path):
    """`isfile`/`isdir` follow the link and would report the TARGET's type,
    hiding an indirection that can be repointed later without anything here
    changing.

    Skips on Windows without the privilege to create symlinks. Measured
    separately on 2026-08-26: a symlink created from WSL on `/mnt/c` is not
    recognised by the Windows interpreter at all — `islink`, `isfile` and
    `isdir` are ALL False — so it lands in the `<other entry type>` branch. It
    is still REJECTED, which is the property that matters; only the label
    degrades. A native Windows symlink reaches the branch this test covers.
    """
    real = _touch(tmp_path, "real.xlsx")
    link = os.path.join(str(tmp_path), "alias.xlsx")
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    assert "alias.xlsx" in msg
    assert "<symlink -> file>" in msg


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlink support")
def test_a_dangling_symlink_is_labelled_unresolved_not_file(tmp_path):
    """`isdir` returns False on a broken link WITHOUT raising, so classifying by
    it alone reports a target that is not there as one that is."""
    _touch(tmp_path, "real.xlsx")
    link = os.path.join(str(tmp_path), "ghost.xlsx")
    try:
        os.symlink(os.path.join(str(tmp_path), "gone.xlsx"), link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    assert "ghost.xlsx" in msg
    assert "<symlink -> unresolved>" in msg
    assert "<symlink -> file>" not in msg


# --- an unreadable format still stops the build --------------------------------
#
# ⚠ SCOPE MOVED. These originally used `.csv`, because at O-H time the 2026-08-26
# event WAS an unreadable-format event. A3 then made the csv a first-class source
# (UTF-16 / tab), so rejecting it by extension would now be wrong. What the
# extension gate still owns is "this builder has no reader for that"; whether a
# READABLE file may contribute is the ownership contract's job, and lives in
# `tests/test_b0_financials_source_contract.py`.
#
# The 2026-08-26 event itself is still covered end-to-end — as an UNDECLARED
# file, and as a DECLARED file that vanished — in that other file.

def test_an_unreadable_format_stops_the_build(tmp_path):
    _touch(tmp_path, "20260806090633.xlsx")
    _touch(tmp_path, "financials.parquet")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))

    msg = str(exc.value)
    assert "financials.parquet" in msg            # the filename
    assert ".parquet" in msg                      # the extension
    assert ".xlsx" in msg and ".csv" in msg       # the accepted format(s)
    assert str(tmp_path) in msg                   # where to look
    assert "SILENTLY" in msg


def test_an_unreadable_file_alone_is_not_reported_as_an_empty_directory(tmp_path):
    """`no source workbook` would be the wrong diagnosis: there IS a source."""
    _touch(tmp_path, "financials.parquet")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    assert "financials.parquet" in str(exc.value)
    assert "no source workbook" not in str(exc.value)


def test_a_csv_is_now_accepted_by_the_extension_gate(tmp_path):
    """A3: the csv is a source. It is admitted HERE and adjudicated by the
    ownership contract, not turned away at the door."""
    _touch(tmp_path, "20260806090633.xlsx")
    _touch(tmp_path, "2026 0826 2385家.csv", b"\xff\xfe")

    got = assert_source_dir_holds_only_accepted_files(str(tmp_path))
    assert sorted(os.path.basename(p) for p in got) == [
        "2026 0826 2385家.csv", "20260806090633.xlsx"]


# --- a mixed directory may not be silently narrowed ----------------------------

def test_a_mixed_directory_is_never_silently_reduced_to_readable_files(tmp_path):
    """The whole defect in one assertion: valid sources present must NOT
    license ignoring the rest."""
    _touch(tmp_path, "good_one.xlsx")
    _touch(tmp_path, "good_two.csv")
    _touch(tmp_path, "extra.parquet")

    with pytest.raises(SystemExit):
        assert_source_dir_holds_only_accepted_files(str(tmp_path))


def test_every_rejected_file_is_named_not_just_the_first(tmp_path):
    _touch(tmp_path, "keep.xlsx")
    for n in ("a.parquet", "b.txt", "c.json"):
        _touch(tmp_path, n)

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    for n in ("a.parquet", "b.txt", "c.json"):
        assert n in msg, n
    assert "3 entr(y/ies)" in msg


def test_an_extensionless_file_is_reported_readably(tmp_path):
    _touch(tmp_path, "keep.xlsx")
    _touch(tmp_path, "README")

    with pytest.raises(SystemExit) as exc:
        assert_source_dir_holds_only_accepted_files(str(tmp_path))
    msg = str(exc.value)
    assert "README" in msg
    assert "<no extension>" in msg


def test_extension_matching_is_case_insensitive(tmp_path):
    """`.XLSX` is the same format; rejecting it would be a different bug."""
    _touch(tmp_path, "SHOUTING.XLSX")
    got = assert_source_dir_holds_only_accepted_files(str(tmp_path))
    assert [os.path.basename(p) for p in got] == ["SHOUTING.XLSX"]


# --- the symlink label itself, without needing OS symlink privileges -----------
#
# Both tests above skip on a Windows box without the create-symlink right, which
# would leave the three-way label unexercised. These drive `_entry_kind` with
# `islink` forced, so the branch is covered wherever the suite runs.

@pytest.mark.parametrize("kind,expected", [
    ("missing", "<symlink -> unresolved>"),
    ("file", "<symlink -> file>"),
    ("dir", "<symlink -> directory>"),
])
def test_symlink_label_reflects_the_target(tmp_path, monkeypatch, kind, expected):
    if kind == "missing":
        path = os.path.join(str(tmp_path), "gone.xlsx")
    elif kind == "file":
        path = _touch(tmp_path, "there.xlsx")
    else:
        path = os.path.join(str(tmp_path), "adir")
        os.makedirs(path)

    monkeypatch.setattr(os.path, "islink", lambda p: p == path)
    assert _entry_kind(path) == expected


def test_a_dangling_link_is_never_described_as_a_file(tmp_path, monkeypatch):
    """The regression this fix exists for: `isdir` returns False on a broken
    link without raising, so classifying by it alone said "-> file"."""
    path = os.path.join(str(tmp_path), "gone.xlsx")
    monkeypatch.setattr(os.path, "islink", lambda p: p == path)
    assert "unresolved" in _entry_kind(path)
    assert _entry_kind(path) != "<symlink -> file>"


# --- boundary conditions -------------------------------------------------------

def test_an_empty_directory_is_not_an_error_here(tmp_path):
    """Emptiness is `load_raw`'s diagnosis to make, not this guard's."""
    assert assert_source_dir_holds_only_accepted_files(str(tmp_path)) == []


def test_a_missing_directory_fails_loudly(tmp_path):
    missing = os.path.join(str(tmp_path), "not_there")
    with pytest.raises(SystemExit, match="does not exist"):
        assert_source_dir_holds_only_accepted_files(missing)


def test_the_accepted_set_is_pinned(tmp_path):
    """Widening this is a deliberate act against the frozen importer spec, so it
    should show up as a diff here. `.csv` was added by A3 together with a reader
    and an ownership declaration — never on its own."""
    assert ACCEPTED_SOURCE_EXTENSIONS == (".xlsx", ".csv")
