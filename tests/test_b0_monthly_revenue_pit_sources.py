# -*- coding: utf-8 -*-
"""The monthly-revenue panel's SOURCE ENUMERATION, not its arithmetic.

THE DEFECT THESE EXIST FOR. `build_monthly_revenue_pit.build()` used to open its
corpus with

    files = sorted(glob.glob(os.path.join(CORPUS, "*.xlsx")))

A glob reports what it matched and is silent about what it did not. When
`月營收7月完整.zip` — the completed 202607 export — landed in that directory it
matched nothing, raised nothing, and the rebuild would have printed a clean
receipt for a panel whose July was 80% absent. Omission-by-glob cannot be caught
downstream, because the omitted rows leave no trace: it has to be impossible at
the enumeration.

So the builder now does what `build_flat_leaves.build()` does — force every
entry in the directory into consumed / not_consumed / unknown, and let `unknown`
abort — and the tests below drive that classifier rather than the panel.

Measured on the real corpus, 2026-08-30:

    20260806091706.xlsx  478,127 rows, 271 months 200401..202607. Its 202607 is
                         PARTIAL: 406 securities, announced 08-01..08-06.
    月營收7月完整.zip     2,002 rows, exactly 202607, announced 08-01..08-17.
                         A strict superset of the workbook's July (only-xlsx=0).
"""
from __future__ import annotations

import os
import sys
import zipfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

import build_flat_leaves as F                                    # noqa: E402
import build_monthly_revenue_pit as M                            # noqa: E402

ARCHIVE = "月營收7月完整.zip"
WORKBOOK = "20260806091706.xlsx"

corpus_present = pytest.mark.skipif(
    not os.path.isdir(M.CORPUS), reason="monthly revenue export not present")


def _staged(tmp_path, names, declarations=None, extensions=(".xlsx", ".zip"),
            consumed=(WORKBOOK, ARCHIVE)):
    """Point the builder at a tiny stand-in corpus.

    `landing` is set absolute so `_assert_corpus_is_the_declared_landing` still
    compares two real paths rather than being switched off for the test.
    """
    for name in names:
        open(os.path.join(str(tmp_path), name), "wb").close()
    family = dict(F.FLAT_FAMILIES["revenue"])
    family["landing"] = str(tmp_path)
    family["extensions"] = extensions
    family["consumed"] = consumed
    if declarations is not None:
        family["declarations"] = declarations
    return family


@pytest.fixture()
def staged(tmp_path, monkeypatch):
    def _apply(names, **kw):
        family = _staged(tmp_path, names, **kw)
        monkeypatch.setattr(M, "FAMILY", family)
        monkeypatch.setattr(M, "CORPUS", str(tmp_path))
        return str(tmp_path)
    return _apply


# --- the omission the glob could not report ------------------------------------

def test_a_file_that_is_neither_consumed_nor_rejected_aborts(staged):
    """THE regression. `*.xlsx` matched no `.zip` and said nothing about it."""
    staged([WORKBOOK, ARCHIVE, "月營收8月.7z"])
    with pytest.raises(SystemExit,
                       match="neither declared-consumed nor declared-rejected"):
        M.enumerate_corpus()


def test_the_abort_names_the_file_it_could_not_classify(staged):
    """'A file was skipped' and 'THIS file was skipped' are not the same fact."""
    staged([WORKBOOK, ARCHIVE, "月營收8月.7z"])
    with pytest.raises(SystemExit) as excinfo:
        M.enumerate_corpus()
    assert "月營收8月.7z" in str(excinfo.value)


def test_a_subdirectory_is_an_unknown_not_a_shrug(staged, tmp_path):
    """A directory is where a new file appears; skipping it is the same defect
    one level down."""
    staged([WORKBOOK, ARCHIVE])
    os.makedirs(os.path.join(str(tmp_path), "202608"))
    with pytest.raises(SystemExit,
                       match="neither declared-consumed nor declared-rejected"):
        M.enumerate_corpus()


def test_a_declared_source_that_vanished_aborts(staged):
    staged([WORKBOOK])
    with pytest.raises(SystemExit, match="declares .* as consumed"):
        M.enumerate_corpus()


def test_a_present_but_undeclared_workbook_is_rejected_by_name(staged):
    """Declared FORMAT, undeclared FILE: named not_consumed, never silently
    joined to the panel — the inverse failure of the glob."""
    staged([WORKBOOK, ARCHIVE, "20260901000000.xlsx"])
    consumed, not_consumed = M.enumerate_corpus()
    assert consumed == [WORKBOOK, ARCHIVE]
    assert not_consumed == ["20260901000000.xlsx"]


def test_the_panel_and_its_manifest_read_the_same_directory(staged, monkeypatch,
                                                            tmp_path):
    """A leaf attesting one directory while the panel is built from another is a
    lineage claim about bytes nobody read."""
    staged([WORKBOOK, ARCHIVE])
    monkeypatch.setattr(M, "CORPUS", str(tmp_path / "elsewhere"))
    os.makedirs(str(tmp_path / "elsewhere"))
    with pytest.raises(SystemExit, match="does not declare"):
        M.enumerate_corpus()


# --- the reader is chosen by the DECLARED format, not by the extension ---------

def test_an_undeclared_format_has_no_reader(staged, tmp_path):
    """A guessed reader is how a UTF-16 tab file becomes one column silently."""
    staged([WORKBOOK, ARCHIVE],
           declarations={ARCHIVE: {"format": "zip:csv:big5:comma"}})
    with pytest.raises(SystemExit, match="no reader for"):
        M._read_declared(os.path.join(str(tmp_path), ARCHIVE), ARCHIVE)


def test_a_member_that_is_not_the_declared_kind_stops_the_build(staged, tmp_path):
    """A member added to a declared archive is as invisible as a file added to a
    declared directory."""
    staged([WORKBOOK])
    p = os.path.join(str(tmp_path), ARCHIVE)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("20260830033323.csv", "x")
        z.writestr("readme.txt", "y")
    with pytest.raises(SystemExit, match="declares csv members only"):
        M._read_declared(p, ARCHIVE)


@corpus_present
def test_the_declared_archive_reads_as_utf16_tab(staged):
    """The wrong (encoding, separator) pair yields ONE column and no error."""
    df = M._read_declared(os.path.join(M.CORPUS, ARCHIVE), ARCHIVE)
    assert len(df.columns) == 10, list(df.columns)
    assert len(df) == 2002
    assert set(df["年月"].astype(str)) == {"202607"}
    assert df["營收發布日"].min() == 20260801
    assert df["營收發布日"].max() == 20260817


# --- ownership: the overlapping month has exactly one claimant ------------------

def _frame(periods):
    import pandas as pd
    return pd.DataFrame({"_period": [str(p) for p in periods]})


def test_the_workbook_yields_its_partial_july(staged):
    """The workbook carries a 406-security July. It is dropped because the
    declaration YIELDS it, not because a de-duplicator preferred another row."""
    staged([WORKBOOK, ARCHIVE])
    kept = M._apply_declared_ownership(WORKBOOK, _frame(["202605", "202606",
                                                         "202607", "202607"]))
    assert sorted(kept["_period"]) == ["202605", "202606"]


def test_the_archive_owns_july_and_nothing_else(staged):
    staged([WORKBOOK, ARCHIVE])
    kept = M._apply_declared_ownership(ARCHIVE, _frame(["202607", "202607"]))
    assert len(kept) == 2


def test_a_period_a_source_neither_owns_nor_yields_aborts(staged):
    """Dropping it would be a silent skip; keeping it would give one month two
    canonical sources. The declaration must say which."""
    staged([WORKBOOK, ARCHIVE])
    with pytest.raises(SystemExit, match="neither OWNS nor YIELDS"):
        M._apply_declared_ownership(ARCHIVE, _frame(["202607", "202608"]))


def test_an_unreadable_period_is_not_a_droppable_one(staged):
    """`norm_period` refuses a 年月 it cannot parse: a month that cannot be
    named cannot be owned, and a row nobody can date must not be quietly kept."""
    from source_ownership_manifest import ManifestError
    staged([WORKBOOK, ARCHIVE])
    with pytest.raises(ManifestError, match="not one of the frozen formats"):
        M._apply_declared_ownership(ARCHIVE, _frame(["2026-07"]))


# --- the real corpus ------------------------------------------------------------

@corpus_present
def test_the_real_corpus_classifies_every_entry():
    consumed, not_consumed = M.enumerate_corpus()
    assert consumed == [WORKBOOK, ARCHIVE]
    on_disk = {n for n in os.listdir(M.CORPUS)
               if os.path.isfile(os.path.join(M.CORPUS, n))}
    assert set(consumed) | set(not_consumed) == on_disk
