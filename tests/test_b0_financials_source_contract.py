# -*- coding: utf-8 -*-
"""A3 · the frozen financials source contract: two formats, declared ownership.

The two exports overlap AND disagree. Measured 2026-08-26 on period 202606: the
workbook has 318 securities, the csv has 1,879 (a strict superset), and on the
318 they share, 16 of 57 columns differ — some only in formatting, but
`加權平均股數` differs on 201 rows by up to 106,846 shares and `每股盈餘` on 15
rows by up to 0.16. A later export carrying more finalised numbers is normal.

That makes both naive rules wrong: "abort on any collision" aborts every build,
and "last writer wins" silently picks a winner for a canonical input. So
ownership is DECLARED, and the only thing that is ever dropped is a period a
file has explicitly yielded.

These tests drive the contract with injected declarations. They read no sealed
artefact and write no panel.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

from build_financials_pit import (                            # noqa: E402
    ACCEPTED_SOURCE_EXTENSIONS,
    CSV_DELIMITER,
    CSV_ENCODING,
    SOURCE_OWNERSHIP,
    SourceContractError,
    _norm_period,
    _owns_predicate,
    _read_source,
    assert_every_file_is_declared,
    assert_periods_conform,
)

XL = "20260806090633.xlsx"
CSV = "2026 0826 2385家.csv"

TWO = {
    XL: {"owns": "<= 202603", "yields": ("202606",)},
    CSV: {"owns": ("202606",), "yields": ()},
}


def _paths(tmp_path, *names):
    out = []
    for n in names:
        p = os.path.join(str(tmp_path), n)
        open(p, "wb").close()
        out.append(p)
    return out


# --- the declared shapes -------------------------------------------------------

def test_both_formats_are_accepted():
    assert ACCEPTED_SOURCE_EXTENSIONS == (".xlsx", ".csv")


def test_the_csv_dialect_is_pinned_not_sniffed():
    """It is a csv only by extension: BOM ff fe, zero commas, tab-separated.
    Reading it with the default separator yields a one-column frame."""
    assert CSV_ENCODING == "utf-16"
    assert CSV_DELIMITER == "\t"


@pytest.mark.parametrize("raw,want", [
    ("202606", "202606"), ("2026/06", "202606"), (" 202603 ", "202603"),
])
def test_period_normalisation_accepts_both_frozen_formats(raw, want):
    assert _norm_period(raw) == want


@pytest.mark.parametrize("bad", ["2026", "20260601", "2026-06", "abc", ""])
def test_a_third_period_format_is_refused(bad):
    with pytest.raises(SourceContractError):
        _norm_period(bad)


def test_ownership_forms_and_their_boundaries():
    explicit, _ = _owns_predicate(("202606",))
    assert explicit("202606") and not explicit("202603")

    bound, _ = _owns_predicate("<= 202603")
    assert bound("202603") and bound("200506")       # inclusive
    assert not bound("202606")


def test_an_unparsable_declaration_is_treated_as_no_declaration():
    with pytest.raises(SourceContractError, match="not a supported form"):
        _owns_predicate("latest")


# --- structural: files vs declarations -----------------------------------------

def test_a_conforming_pair_passes(tmp_path):
    assert_every_file_is_declared(_paths(tmp_path, XL, CSV), TWO)


def test_an_undeclared_file_aborts(tmp_path):
    files = _paths(tmp_path, XL, CSV, "surprise_2026Q3.xlsx")
    with pytest.raises(SourceContractError) as exc:
        assert_every_file_is_declared(files, TWO)
    assert "surprise_2026Q3.xlsx" in str(exc.value)
    assert "not declared" in str(exc.value)


def test_a_declared_file_that_vanished_aborts(tmp_path):
    """The 2026-08-26 event: `202606 財報583家 8-10.xlsx` disappeared and only
    the previous receipt remembered it."""
    three = dict(TWO)
    three["202606 財報583家 8-10.xlsx"] = {"owns": ("202512",), "yields": ()}

    with pytest.raises(SourceContractError) as exc:
        assert_every_file_is_declared(_paths(tmp_path, XL, CSV), three)
    msg = str(exc.value)
    assert "202606 財報583家 8-10.xlsx" in msg
    assert "NOT PRESENT" in msg


def test_two_files_owning_one_period_aborts(tmp_path):
    both = {
        XL: {"owns": "<= 202606", "yields": ()},      # now reaches 202606 too
        CSV: {"owns": ("202606",), "yields": ()},
    }
    with pytest.raises(SourceContractError) as exc:
        assert_every_file_is_declared(_paths(tmp_path, XL, CSV), both)
    msg = str(exc.value)
    assert "202606" in msg
    assert "both" in msg


# --- content: periods vs declarations ------------------------------------------

def test_owned_periods_are_kept_and_yielded_ones_reported(tmp_path):
    owned, yielded = assert_periods_conform(
        XL, ["202512", "202603", "202606"], TWO)
    assert owned == ("202512", "202603")
    assert yielded == ("202606",)


def test_the_owner_of_a_period_does_not_also_yield_it():
    owned, yielded = assert_periods_conform(CSV, ["202606"], TWO)
    assert owned == ("202606",)
    assert yielded == ()


def test_a_period_neither_owned_nor_yielded_aborts():
    """A new quarter appearing in an old export must be ruled on, not absorbed."""
    with pytest.raises(SourceContractError) as exc:
        assert_periods_conform(XL, ["202603", "202609"], TWO)
    msg = str(exc.value)
    assert "202609" in msg
    assert "neither OWNS nor YIELDS" in msg


def test_yielding_is_declared_never_inferred():
    """Same data, but with the yield removed from the declaration: the rows that
    were legitimately dropped before must now stop the build."""
    no_yield = {XL: {"owns": "<= 202603", "yields": ()}, CSV: TWO[CSV]}
    with pytest.raises(SourceContractError, match="202606"):
        assert_periods_conform(XL, ["202603", "202606"], no_yield)


# --- the reader ----------------------------------------------------------------

def test_the_csv_reader_handles_utf16_tab(tmp_path):
    p = os.path.join(str(tmp_path), "x.csv")
    with open(p, "w", encoding="utf-16", newline="") as fh:
        fh.write("證券代碼\t年月\t每股盈餘\n1101 台泥\t202606\t1.23\n")

    df = _read_source(p)
    assert list(df.columns) == ["證券代碼", "年月", "每股盈餘"]
    assert len(df) == 1
    assert df["年月"].iloc[0] == 202606


def test_reading_the_csv_as_comma_separated_would_collapse_it(tmp_path):
    """Why the dialect is pinned: the wrong separator does not raise, it just
    returns one column, and every required column then looks missing."""
    import pandas as pd

    p = os.path.join(str(tmp_path), "x.csv")
    with open(p, "w", encoding="utf-16", newline="") as fh:
        fh.write("證券代碼\t年月\n1101\t202606\n")

    wrong = pd.read_csv(p, encoding="utf-16", sep=",")
    assert len(wrong.columns) == 1                     # silently collapsed
    assert len(_read_source(p).columns) == 2


def test_an_extension_with_no_reader_fails_loudly(tmp_path):
    p = os.path.join(str(tmp_path), "x.parquet")
    open(p, "wb").close()
    with pytest.raises(SourceContractError, match="no reader"):
        _read_source(p)


def test_every_accepted_extension_has_a_reader(tmp_path):
    """The guard must never admit a format the dispatch cannot read."""
    for ext in ACCEPTED_SOURCE_EXTENSIONS:
        p = os.path.join(str(tmp_path), "probe" + ext)
        open(p, "wb").close()
        with pytest.raises(Exception) as exc:          # empty file, but reached
            _read_source(p)
        assert "no reader" not in str(exc.value), ext


# --- the live declaration ------------------------------------------------------

def test_the_shipped_declaration_covers_both_live_sources():
    assert set(SOURCE_OWNERSHIP) == {XL, CSV}
    assert SOURCE_OWNERSHIP[XL]["yields"] == ("202606",)
    assert SOURCE_OWNERSHIP[CSV]["owns"] == ("202606",)


def test_the_shipped_declaration_has_no_overlapping_owner(tmp_path):
    assert_every_file_is_declared(
        _paths(tmp_path, *sorted(SOURCE_OWNERSHIP)), SOURCE_OWNERSHIP)
