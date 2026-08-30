# -*- coding: utf-8 -*-
"""W4 · the prices leaf: archives, two source families, and the sentinel zero.

Prices is the family that breaks the financials shape, in three ways W1
measured on the 25-session overlap between TEJ and the live feed:

    close disagreements            1   a sentinel zero
    volume disagreements      47,047   97.9%, all < 1,000 shares (units)
    live-only securities         722   27-31 per session (population)

None of the three raises anything on its own. All three change decisions.
"""
from __future__ import annotations

import os
import sys
import zipfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

import build_prices_leaf as P                                    # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    ManifestError,
    assert_archive_members_match,
    build_leaf,
)

RUN, AS_OF = "L3-0000000000000001", "2026-08-28"
LANDING = os.path.join(REPO, P.LANDING_DIRECTORY)
live = pytest.mark.skipif(not os.path.isdir(LANDING),
                          reason="TEJ price export not present")


def _entry(locator="a.zip", **kw):
    e = {"locator": locator, "format": "zip", "raw_sha256": "0" * 64,
         "export_vintage": "2026-08-18",
         "observed_at": "2026-08-26T19:00:00+08:00",
         "source_family": "TEJ", "authority": "AUTHORITATIVE",
         "disposition": "consumed",
         "members": [{"name": "x.csv", "size": 10, "crc32": "deadbeef"}]}
    e.update(kw)
    return e


def _leaf(entries):
    return build_leaf(dataset="prices", run_id=RUN, as_of=AS_OF, entries=entries)


# --- an archive is not a file ---------------------------------------------------

def test_an_archive_without_a_member_inventory_is_refused():
    """`*.zip` is not a contract: a member added to or removed from a declared
    zip is invisible to the zip's own path."""
    bad = _entry()
    del bad["members"]
    with pytest.raises(ManifestError, match="no member inventory"):
        _leaf([bad])


@pytest.mark.parametrize("field", ["name", "size", "crc32"])
def test_a_member_must_be_fully_identified(field):
    bad = _entry()
    bad["members"][0][field] = ""
    with pytest.raises(ManifestError, match="missing"):
        _leaf([bad])


def test_a_repacked_archive_is_detected(tmp_path):
    p = os.path.join(str(tmp_path), "a.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("one.csv", "a,b\n1,2\n")

    with zipfile.ZipFile(p) as z:
        i = z.infolist()[0]
        good = _entry(members=[{"name": i.filename, "size": i.file_size,
                                "crc32": "%08x" % i.CRC}])
    assert_archive_members_match(p, good)                 # baseline holds

    with zipfile.ZipFile(p, "a") as z:                    # a member appears
        z.writestr("two.csv", "c\n3\n")
    with pytest.raises(ManifestError, match="members added"):
        assert_archive_members_match(p, good)


def test_a_member_whose_content_changed_is_detected(tmp_path):
    p = os.path.join(str(tmp_path), "a.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("one.csv", "a,b\n1,2\n")
    entry = _entry(members=[{"name": "one.csv", "size": 8, "crc32": "00000000"}])
    with pytest.raises(ManifestError, match="changed"):
        assert_archive_members_match(p, entry)


# --- two source families, TEJ authoritative ------------------------------------

def test_a_live_source_may_not_claim_authority():
    """R-W1-2: the live feed supplies immediacy, not authority."""
    with pytest.raises(ManifestError, match="AUTHORITATIVE"):
        _leaf([_entry(source_family="LIVE", authority="AUTHORITATIVE")])


def test_a_live_source_is_admissible_as_supplementary():
    leaf = _leaf([_entry(),
                  _entry("live.parquet", format="parquet",
                         source_family="LIVE", authority="SUPPLEMENTARY",
                         members=None)])
    assert len(leaf["entries"]) == 2


@pytest.mark.parametrize("field,bad", [
    ("source_family", "FINMIND"), ("authority", "PRIMARY"),
    ("disposition", "maybe")])
def test_vocabularies_are_closed(field, bad):
    with pytest.raises(ManifestError, match="not one of"):
        _leaf([_entry(**{field: bad})])


# --- present but deliberately unused -------------------------------------------

def test_an_unused_file_must_say_why():
    """'deliberately unused' and 'silently skipped' look identical from outside."""
    with pytest.raises(ManifestError, match="without a reason"):
        _leaf([_entry(), _entry("2019DataExport.xlsx", format="xlsx",
                                disposition="not_consumed", members=None)])


def test_a_leaf_that_consumes_nothing_is_refused():
    with pytest.raises(ManifestError, match="consumes nothing"):
        _leaf([_entry(disposition="not_consumed",
                      not_consumed_reason="superseded")])


# --- the policies travel with the bytes ----------------------------------------

def test_the_sentinel_zero_ruling_is_carried_beside_the_source():
    """A held position marked 0.0 zeroes its NAV without raising. The consumer
    must not be able to reach the source without meeting this."""
    pol = P.SENTINEL_ZERO_POLICY
    assert pol["rule"] == "LIVE_ZERO_PRICE_IS_UNDEFINED_AND_MUST_FAIL_LOUD"
    assert pol["applies_to_family"] == "LIVE"
    assert set(pol["fields"]) == {"open", "close"}
    assert "5906" in pol["measured"]


def test_tej_authority_covers_units_and_precision_not_only_values():
    """C-25 pins adv20 to close x volume and §4.2 applies an absolute NTD floor,
    so a 999-share rounding can flip a name across the threshold."""
    d = P.UNIT_AUTHORITY
    assert d["rule"] == "TEJ_AUTHORITATIVE_COVERS_UNITS_AND_PRECISION"
    assert "47,047" in d["measured"]


def test_the_population_cut_is_declared_not_discovered():
    d = P.POPULATION_AUTHORITY
    assert d["rule"] == "TEJ_DEFINES_THE_POPULATION"
    assert "722" in d["measured"]


# --- against the real export ---------------------------------------------------

@live
def test_the_real_export_declares_every_entry_it_holds():
    """Per LEG, because §2.8.3 gives this family two landing surfaces.

    The export directory and the pre-2019 cache are different trees, so "every
    entry on disk is declared" has to be asked of each separately — asking it of
    the union would compare one directory's listing against both legs' entries
    and pass for the wrong reason.
    """
    leaf = P.build(RUN, AS_OF)
    export_leg = [e for e in leaf["entries"] if e.get("leg") != "pre-2019"]
    on_disk = {n for n in os.listdir(LANDING)
               if os.path.isfile(os.path.join(LANDING, n))}
    assert {e["locator"] for e in export_leg} == on_disk

    consumed = [e for e in export_leg if e["disposition"] == "consumed"]
    assert sorted(e["locator"] for e in consumed) == sorted(P.CONSUMED_ARCHIVES)
    for e in consumed:
        assert e["members"], e["locator"]


def test_the_pre_2019_leg_declares_the_whole_cache():
    """The other surface. `build_price_panel.py:159` reaches it with
    `glob("*.parquet")`, so a security appearing in or vanishing from that
    directory changes the universe without changing any path."""
    leaf = P.build(RUN, AS_OF)
    cache = [e for e in leaf["entries"] if e.get("leg") == "pre-2019"]
    on_disk = {n for n in os.listdir(P.PRE_2019_LEG["landing"])
               if n.lower().endswith(".parquet")}
    assert {e["locator"] for e in cache} == on_disk
    assert len(cache) > 2000
    assert all(e["disposition"] == "consumed" for e in cache)
    # The landing travels with the entry: this leg is not under the leaf's own
    # landing directory at all.
    assert all(e["landing_directory"] for e in cache)


def test_the_quarantine_is_declared_beside_the_leg_it_constrains():
    """D-1 quarantined the 2019+ ERA of that cache, not the cache. The same
    parquet holds admissible and quarantined rows, so which files are declared
    cannot express the restriction — the policy has to travel with them."""
    leaf = P.build(RUN, AS_OF)
    pol = leaf["policies"]["quarantined_era"]
    assert pol["boundary"] == "2019-01-01"
    assert pol["applies_to_leg"] == "pre-2019"
    units = leaf["policies"]["leg_unit_conventions"]
    assert "ALREADY shares" in units["pre-2019"]
    assert "thousands" in units["2019+"]


@live
def test_the_declared_zip_hashes_match_the_sealed_price_receipt():
    """Independent cross-check: the L2 receipt recorded these hashes when the
    panel was built, and this leaf derives them from the bytes again."""
    import json

    receipt = json.load(open(os.path.join(
        REPO, "research", "b0_materializer", "price_panel_receipt.json"),
        encoding="utf-8"))
    declared = {e["locator"]: e["raw_sha256"] for e in P.build(RUN, AS_OF)["entries"]}
    for name, sha in receipt["upstream_zip_sha256"].items():
        assert declared[name] == sha, name


@live
def test_an_undeclared_archive_in_the_directory_would_be_caught(tmp_path):
    """W1: `build_price_panel.py:195` globs `*.zip`, so a new archive is
    silently INCLUDED — O-H inverted, and worse."""
    import shutil

    staged = os.path.join(str(tmp_path), "landing")
    shutil.copytree(LANDING, staged)
    with zipfile.ZipFile(os.path.join(staged, "股價_extra.zip"), "w") as z:
        z.writestr("rogue.csv", "x\n")

    leaf = P.build(RUN, AS_OF, landing_dir=staged)
    rogue = [e for e in leaf["entries"] if e["locator"] == "股價_extra.zip"]
    assert rogue, "a new archive must appear in the enumeration"
    # It enumerates, and because it is not in CONSUMED_ARCHIVES it is declared
    # not_consumed WITH a reason — never silently swept into the panel.
    assert rogue[0]["disposition"] == "not_consumed"
    assert rogue[0]["not_consumed_reason"]


# --- the 2026-08 slice: declared, and declared LIMITED --------------------------
#
# 股價0817-0828.zip is admissible as prices and inadmissible as evidence of
# coverage, and nothing in its bytes says so. Both halves are pinned here.

def test_the_filename_is_not_the_span():
    """The archive is named 0817-0828 and does not contain 2026-08-17 at all.
    `covers` is measured (17,586 rows over 9 sessions, 2026-08-18 .. 08-28), so
    a reader who trusts the name is contradicted by the declaration rather than
    by a surprise further downstream."""
    d = P.CONSUMED_ARCHIVE_DECLARATIONS["股價0817-0828.zip"]
    assert tuple(d["covers"]) == ("2026-08-18", "2026-08-28")
    assert d["leg"] == "2019+"


def test_the_roster_snapshot_limitation_is_a_named_declared_property():
    """A current-roster query cannot contain anything that left the exchange
    before it ran, at any session count. Same eleven columns, same real prices,
    a different fact — and the difference never raises."""
    lim = P.ROSTER_SNAPSHOT_LIMITATION
    assert lim["property"] == (
        "ROSTER_SNAPSHOT_DERIVED_DOES_NOT_EVIDENCE_DELISTED_COVERAGE")
    assert lim["roster_basis"] == P.ROSTER_BASIS_CURRENT_SNAPSHOT
    assert "1,954" in lim["measured"]
    assert "1589" in lim["corroboration"]          # padded, not omitted
    assert "includes_delisted" in lim["inadmissible_as"]
    assert "2019-2025" in lim["does_not_change_includes_delisted"]


def test_the_family_policy_names_which_archives_may_not_be_cited():
    """Derived from the declarations, so the family-level statement cannot drift
    from the per-archive one. It does NOT restate the D1-6 verdict: whether the
    COMPOSED corpus includes delisted securities is decided by
    `assert_price_source_admissible`, never by one archive's entry."""
    pol = P.DELISTED_COVERAGE_POLICY
    assert pol["may_not_be_cited_toward_includes_delisted"] == [
        "股價0817-0828.zip"]
    assert pol["roster_basis_by_archive"]["股價2023-20260817.zip"] == (
        P.ROSTER_BASIS_BULK_HISTORICAL)
    assert pol["d1_6_gate_owner"].endswith("assert_price_source_admissible")
    assert set(pol["declared_limitations"]) == {"股價0817-0828.zip"}


@live
def test_the_limitation_travels_on_the_entry_and_in_the_leaf():
    """A future reader must see 'roster-snapshot-derived' without re-deriving it
    from the row counts, so it rides the entry AND the family's policies."""
    leaf = P.build(RUN, AS_OF)
    by = {e["locator"]: e for e in leaf["entries"]}
    e = by["股價0817-0828.zip"]
    assert e["disposition"] == "consumed" and e["leg"] == "2019+"
    assert e["roster_basis"] == P.ROSTER_BASIS_CURRENT_SNAPSHOT
    assert e["covers"] == ["2026-08-18", "2026-08-28"]
    assert e["declared_properties"]["delisted_coverage"]["property"] == (
        "ROSTER_SNAPSHOT_DERIVED_DOES_NOT_EVIDENCE_DELISTED_COVERAGE")
    assert by["股價2023-20260817.zip"]["roster_basis"] == (
        P.ROSTER_BASIS_BULK_HISTORICAL)
    assert leaf["policies"]["delisted_coverage"][
        "may_not_be_cited_toward_includes_delisted"] == ["股價0817-0828.zip"]


# --- export_vintage is read off the file, not chosen by a branch ----------------

def test_a_zip_vintage_comes_from_its_own_member_timestamps(tmp_path):
    """The old stamp was `"2026-08-18" if consumed else "2026-08-06"` — a
    coincidence encoded as a rule. 股價0817-0828.zip was packed 2026-08-30 and
    would have inherited 2026-08-18 the moment it became consumed: a date 12
    days before the file existed, with nothing to raise about it."""
    p = os.path.join(str(tmp_path), "z.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(zipfile.ZipInfo("early.csv", (2026, 8, 18, 3, 37, 4)), "a\n")
        z.writestr(zipfile.ZipInfo("late.csv", (2026, 8, 30, 3, 31, 22)), "b\n")
    assert P.export_vintage(p, "zip", "0" * 64) == "2026-08-30"


def test_a_workbook_with_no_recorded_vintage_is_refused():
    """The `else` branch was a guess too — 23 of the 24 workbooks were exported
    2026-07-14/15, not 2026-08-06. A workbook whose bytes the capture manifest
    does not know now aborts BY NAME rather than taking a default."""
    with pytest.raises(ManifestError, match="not recorded"):
        P.export_vintage("nowhere/新增.xlsx", "xlsx", "f" * 64)


@live
def test_every_archive_carries_its_own_vintage():
    leaf = P.build(RUN, AS_OF)
    by = {e["locator"]: e["export_vintage"] for e in leaf["entries"]
          if e.get("leg") != "pre-2019"}
    assert by["股價0817-0828.zip"] == "2026-08-30"        # not 2026-08-18
    assert by["股價2023-20260817.zip"] == "2026-08-18"
    assert by["股價 2019-2022.zip"] == "2026-08-18"
    assert by["2004DataExport.xlsx"] == "2026-07-15"      # not 2026-08-06
    assert by["2019DataExport.xlsx"] == "2026-07-14"
    assert by["個股股價、本益比20260715-0806.xlsx"] == "2026-08-06"
    # The ternary could produce exactly two distinct values over the directory.
    assert len(set(by.values())) > 2


@live
def test_a_declared_archive_is_declared_by_its_bytes(tmp_path):
    """Same name, different bytes is a different source. A name-only inventory
    waves the swap through; the hash names it."""
    import shutil

    staged = os.path.join(str(tmp_path), "landing")
    shutil.copytree(LANDING, staged)
    with zipfile.ZipFile(os.path.join(staged, "股價0817-0828.zip"), "w") as z:
        z.writestr("20260830033123.csv", "not the real export\n")
    with pytest.raises(ManifestError, match="hashes to"):
        P.build(RUN, AS_OF, landing_dir=staged)


# --- the panel's count guard is now an inventory --------------------------------

def _panel():
    import build_price_panel

    return build_price_panel


def _declared_dir(tmp, names):
    B = _panel()
    decl = {}
    for i, name in enumerate(names):
        p = os.path.join(tmp, name)
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("m.csv", "row%d\n" % i)
        decl[name] = {"leg": "2019+", "raw_sha256": B._file_sha(p),
                      "covers": ("2019-01-02", "2026-08-28"),
                      "roster_basis": P.ROSTER_BASIS_BULK_HISTORICAL}
    return B, decl


def test_three_declared_archives_pass_where_a_count_guard_refused_them(
        tmp_path, monkeypatch):
    """`len(zips) != 2` admitted ANY two zips and refused the right three. An
    inventory passes a declared archive at any count."""
    B, decl = _declared_dir(str(tmp_path), ("a.zip", "b.zip", "c.zip"))
    monkeypatch.setattr(B, "CONSUMED_ARCHIVE_DECLARATIONS", decl)
    paths, upstream = B.declared_zip_inventory(str(tmp_path))
    assert len(paths) == 3
    assert set(upstream) == set(decl)


def test_an_undeclared_archive_aborts_the_panel_by_name(tmp_path, monkeypatch):
    """The failure a bare count cannot see: a stray file that keeps the total
    plausible. It is named, not counted."""
    B, decl = _declared_dir(str(tmp_path), ("a.zip", "b.zip", "c.zip"))
    monkeypatch.setattr(B, "CONSUMED_ARCHIVE_DECLARATIONS", decl)
    with zipfile.ZipFile(os.path.join(str(tmp_path), "股價_extra.zip"), "w") as z:
        z.writestr("rogue.csv", "x\n")
    with pytest.raises(SystemExit, match="股價_extra"):
        B.declared_zip_inventory(str(tmp_path))


def test_a_declared_archive_that_is_absent_aborts_by_name(tmp_path, monkeypatch):
    """Fail-closed in the other direction too: a declared source that is not
    there is a silent skip, not a shorter panel."""
    B, decl = _declared_dir(str(tmp_path), ("a.zip", "b.zip"))
    decl["c.zip"] = {"leg": "2019+", "raw_sha256": "0" * 64,
                     "covers": ("2019-01-02", "2026-08-28"),
                     "roster_basis": P.ROSTER_BASIS_BULK_HISTORICAL}
    monkeypatch.setattr(B, "CONSUMED_ARCHIVE_DECLARATIONS", decl)
    with pytest.raises(SystemExit, match="absent"):
        B.declared_zip_inventory(str(tmp_path))


def test_a_declared_archive_whose_bytes_changed_aborts(tmp_path, monkeypatch):
    B, decl = _declared_dir(str(tmp_path), ("a.zip", "b.zip"))
    monkeypatch.setattr(B, "CONSUMED_ARCHIVE_DECLARATIONS", decl)
    with zipfile.ZipFile(os.path.join(str(tmp_path), "b.zip"), "w") as z:
        z.writestr("m.csv", "swapped\n")
    with pytest.raises(SystemExit,
                       match="different bytes is a different source"):
        B.declared_zip_inventory(str(tmp_path))


@live
def test_the_real_directory_holds_exactly_the_declared_archives():
    B = _panel()
    paths, upstream = B.declared_zip_inventory()
    assert sorted(os.path.basename(p) for p in paths) == sorted(
        P.CONSUMED_ARCHIVE_DECLARATIONS)
    assert upstream["股價0817-0828.zip"] == P.CONSUMED_ARCHIVE_DECLARATIONS[
        "股價0817-0828.zip"]["raw_sha256"]


# --- how many members a declared archive may hold -------------------------------
#
# The panel producer read `namelist()[0]`; `l3_readers.read_prices` requires
# exactly one member. Measured on the two-member fixture below before the fix:
# the producer returned 1 row carrying only 1101 and dropped 9999 without a
# word, while the reader refused the identical archive. One corpus, opposite
# behaviour, and nothing failed on the producing side.

PRICE_HEADER = ("證券代碼", "年月日", "開盤價(元)", "收盤價(元)", "成交量(千股)")


def _price_archive(path, members):
    """A TEJ-dialect price archive: UTF-16, tab-separated, one CSV per member."""
    with zipfile.ZipFile(path, "w") as z:
        for name, rows in members:
            body = "\n".join(["\t".join(PRICE_HEADER)] +
                             ["\t".join(r) for r in rows]) + "\n"
            z.writestr(name, body.encode("utf-16"))
    return path


def _one_declared_archive(B, monkeypatch, path):
    """Stand the inventory gate down; this is about what is INSIDE the file."""
    monkeypatch.setattr(
        B, "declared_zip_inventory",
        lambda zip_dir="": ([path], {os.path.basename(path): "0" * 64}))


def test_a_two_member_archive_aborts_the_panel_by_name(tmp_path, monkeypatch):
    """The producer may not answer a two-member export by reading the first
    member. `leg` and `roster_basis` are declared per ARCHIVE and neither is
    derivable from the rows, so a second member has no declaration to stand
    on — and the reader already refuses it."""
    B = _panel()
    p = _price_archive(os.path.join(str(tmp_path), "two.zip"), [
        ("a.csv", [("1101 台泥", "20190102", "10", "11", "5")]),
        ("b.csv", [("9999 乙", "20190103", "20", "21", "7")])])
    _one_declared_archive(B, monkeypatch, p)
    with pytest.raises(SystemExit, match="holds 2 member"):
        B.zip_leg("2019-01-01", "2019-12-31")


def test_a_directory_entry_counts_as_a_member_at_both_ends(tmp_path,
                                                           monkeypatch):
    """`build_prices_leaf._members` lists every `infolist()` entry, directories
    included, and the reader counts THAT list. Counting them differently here
    would rebuild the same disagreement one entry-kind down."""
    B = _panel()
    p = _price_archive(os.path.join(str(tmp_path), "dir.zip"),
                       [("a.csv", [("1101 台泥", "20190102", "10", "11", "5")])])
    with zipfile.ZipFile(p, "a") as z:
        z.writestr("sub/", b"")
    assert len(P._members(p)) == 2
    _one_declared_archive(B, monkeypatch, p)
    with pytest.raises(SystemExit, match="holds 2 member"):
        B.zip_leg("2019-01-01", "2019-12-31")


def test_a_single_member_archive_is_read_whole(tmp_path, monkeypatch):
    """The contract is ONE member, not zero: the admissible case still parses,
    still applies the 千股 -> shares conversion, and still keeps its rows."""
    B = _panel()
    p = _price_archive(os.path.join(str(tmp_path), "one.zip"), [
        ("a.csv", [("1101 台泥", "20190102", "10", "11", "5"),
                   ("9999 乙", "20190103", "20", "21", "7")])])
    _one_declared_archive(B, monkeypatch, p)
    out, upstream = B.zip_leg("2019-01-01", "2019-12-31")
    assert sorted(out["stock_id"]) == ["1101", "9999"]
    assert sorted(out["volume_shares"]) == [5000.0, 7000.0]
    assert set(upstream) == {"one.zip"}


def _cache_dir(tmp, rows):
    import pandas as pd

    p = os.path.join(tmp, "1101.parquet")
    pd.DataFrame(rows, columns=["stock_id", "date", "open", "close",
                                "Trading_Volume"]).to_parquet(p, index=False)
    return tmp


def test_a_cache_leg_that_contributes_nothing_aborts_by_name(tmp_path,
                                                             monkeypatch):
    """The same class of absence as the missing-file abort beside it, for the
    case that leaves the files in place: every declared parquet read, every row
    filtered away by the era cut. It used to die one line down in
    `pandas.concat([])` with `ValueError: No objects to concatenate`, naming
    neither the cache nor the span that emptied it."""
    B = _panel()
    monkeypatch.setattr(B, "OLD_CACHE", _cache_dir(
        str(tmp_path), [("1101", "2019-01-02", 10.0, 11.0, 5000.0)]))
    with pytest.raises(SystemExit, match="yielded no row"):
        B.cache_leg("2013-01-01", "2026-08-28")


def test_a_cache_leg_with_a_pre_2019_row_still_builds(tmp_path, monkeypatch):
    """And the guard is emptiness, not strictness: one admissible row is a leg."""
    B = _panel()
    monkeypatch.setattr(B, "OLD_CACHE", _cache_dir(
        str(tmp_path), [("1101", "2018-12-28", 10.0, 11.0, 5000.0),
                        ("1101", "2019-01-02", 10.0, 11.0, 5000.0)]))
    out = B.cache_leg("2013-01-01", "2026-08-28")
    assert list(out["date"]) == ["2018-12-28"]


@live
def test_every_real_declared_archive_holds_exactly_one_member():
    """The corpus this contract is written against, measured rather than
    assumed: three archives, one CSV each. The gate changes no bytes today."""
    for name in sorted(P.CONSUMED_ARCHIVE_DECLARATIONS):
        assert len(P._members(os.path.join(LANDING, name))) == 1


# --- S-9 · the declared span is re-measured, never trusted ----------------------
#
# `raw_sha256` catches a REPACKED archive. It cannot see an archive whose bytes
# are exactly what was declared and whose SPAN was written down wrong — and the
# precedent is in this directory: 股價0817-0828.zip is NAMED for 0817 and starts
# on 2026-08-18. A hand-measured constant nothing re-measures is the filename
# one indirection later.

TEJ_HEADER = ("證券代碼", "年月日", "開盤價(元)", "最高價(元)", "最低價(元)",
              "收盤價(元)", "成交量(千股)", "成交值(千元)", "流通在外股數(千股)",
              "本益比-TEJ", "股價淨值比-TEJ")


def _tej_zip(path, days, member="m.csv", header=TEJ_HEADER, extra_members=()):
    """A TEJ-shaped archive: UTF-16, tab separated, 年月日 as YYYYMMDD."""
    def body(rows):
        lines = ["\t".join(header)]
        for d in rows:
            lines.append("\t".join(
                ["1101 台泥", d] + ["1.0"] * (len(header) - 2)))
        return ("\n".join(lines) + "\n").encode("utf-16")

    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, body(days))
        for name, rows in extra_members:
            z.writestr(name, body(rows))
    return path


def _declare(monkeypatch, path, locator, covers, **kw):
    from core.b0_canonical_hash import file_sha256

    d = {"leg": "2019+", "raw_sha256": file_sha256(path), "covers": covers,
         "roster_basis": P.ROSTER_BASIS_BULK_HISTORICAL}
    d.update(kw)
    monkeypatch.setattr(P, "CONSUMED_ARCHIVE_DECLARATIONS", {locator: d})
    monkeypatch.setattr(P, "CONSUMED_ARCHIVES", (locator,))
    P._SPAN_CACHE.clear()
    return d


def test_a_mis_declared_span_is_caught_though_the_bytes_are_right(
        tmp_path, monkeypatch):
    """The exact hole `raw_sha256` leaves open. The archive is byte-identical to
    its declaration; only the span written beside it is wrong."""
    p = _tej_zip(os.path.join(str(tmp_path), "股價_x.zip"),
                 ["20260818", "20260828"])
    d = _declare(monkeypatch, p, "股價_x.zip", ("2026-08-17", "2026-08-28"))
    with pytest.raises(ManifestError, match="mis-declared span"):
        P.assert_declared_span(p, "股價_x.zip", d["raw_sha256"])


def test_a_correctly_declared_span_passes_and_reports_what_it_measured(
        tmp_path, monkeypatch):
    """Mutation control for the test above: the same code path must be able to
    PASS, or the check is just a raise."""
    p = _tej_zip(os.path.join(str(tmp_path), "股價_x.zip"),
                 ["20260828", "20260818", "20260820"])
    d = _declare(monkeypatch, p, "股價_x.zip", ("2026-08-18", "2026-08-28"))
    out = P.assert_declared_span(p, "股價_x.zip", d["raw_sha256"])
    assert out["observed_covers"] == ["2026-08-18", "2026-08-28"]
    assert out["rows"] == 3


def test_the_span_covers_every_member_not_only_the_first(tmp_path, monkeypatch):
    """`build_price_panel.zip_leg` reads `namelist()[0]`, so a second member is
    invisible to it. The declaration speaks for the whole archive, so the span
    is measured over all of them and a member that reaches past the declared end
    is named rather than skipped."""
    p = _tej_zip(os.path.join(str(tmp_path), "股價_x.zip"), ["20260818"],
                 member="a.csv", extra_members=[("b.csv", ["20260901"])])
    d = _declare(monkeypatch, p, "股價_x.zip", ("2026-08-18", "2026-08-18"))
    with pytest.raises(ManifestError, match="mis-declared span"):
        P.assert_declared_span(p, "股價_x.zip", d["raw_sha256"])
    P._SPAN_CACHE.clear()
    assert P.observed_archive_span(p, d["raw_sha256"])["members_read"] == [
        "a.csv", "b.csv"]


def test_the_date_column_is_located_by_name_not_by_position(tmp_path, monkeypatch):
    """A reordered export would shift a positional read silently into another
    column, and 開盤價 parsed as a date is a span nobody can question."""
    header = TEJ_HEADER[:1] + ("交易日",) + TEJ_HEADER[2:]
    p = _tej_zip(os.path.join(str(tmp_path), "股價_x.zip"), ["20260818"],
                 header=header)
    d = _declare(monkeypatch, p, "股價_x.zip", ("2026-08-18", "2026-08-18"))
    with pytest.raises(ManifestError, match="no 年月日 column"):
        P.assert_declared_span(p, "股價_x.zip", d["raw_sha256"])

    # And when it IS present but moved, it is followed rather than assumed: the
    # dates here sit in the LAST column, where a positional read would find a
    # price instead and publish it as a span.
    P._SPAN_CACHE.clear()
    moved = TEJ_HEADER[:1] + TEJ_HEADER[2:] + ("年月日",)
    q = os.path.join(str(tmp_path), "股價_y.zip")
    row = ["1101 台泥"] + ["1.0"] * 9 + ["20260818"]
    text = "\t".join(moved) + "\n" + "\t".join(row) + "\n"
    with zipfile.ZipFile(q, "w") as z:
        z.writestr("m.csv", text.encode("utf-16"))
    assert P.observed_archive_span(q, "c" * 64)["observed_covers"] == [
        "2026-08-18", "2026-08-18"]


def test_an_unreadable_date_field_aborts_rather_than_being_guessed(
        tmp_path, monkeypatch):
    p = _tej_zip(os.path.join(str(tmp_path), "股價_x.zip"), ["2026/08/18"])
    d = _declare(monkeypatch, p, "股價_x.zip", ("2026-08-18", "2026-08-18"))
    with pytest.raises(ManifestError, match="neither YYYYMMDD nor YYYY-MM-DD"):
        P.assert_declared_span(p, "股價_x.zip", d["raw_sha256"])


def test_an_archive_with_no_data_rows_evidences_no_span(tmp_path, monkeypatch):
    p = _tej_zip(os.path.join(str(tmp_path), "股價_x.zip"), [])
    d = _declare(monkeypatch, p, "股價_x.zip", ("2026-08-18", "2026-08-18"))
    with pytest.raises(ManifestError, match="evidences no span"):
        P.assert_declared_span(p, "股價_x.zip", d["raw_sha256"])


def test_the_span_memo_is_keyed_on_the_bytes(tmp_path):
    """The memo is what makes a full re-measure affordable per process. It is
    sound only because the key is the hash `build()` has just recomputed from
    the bytes — so different bytes can never collect another file's span."""
    a = _tej_zip(os.path.join(str(tmp_path), "a.zip"), ["20260818"])
    b = _tej_zip(os.path.join(str(tmp_path), "b.zip"), ["20200102", "20200103"])
    P._SPAN_CACHE.clear()
    assert P.observed_archive_span(a, "a" * 64)["observed_covers"] == [
        "2026-08-18", "2026-08-18"]
    assert P.observed_archive_span(b, "b" * 64)["observed_covers"] == [
        "2020-01-02", "2020-01-03"]
    assert set(P._SPAN_CACHE) == {"a" * 64, "b" * 64}


@live
def test_the_real_declared_spans_are_what_the_archives_actually_hold():
    """Against the bytes, not against the constants beside them."""
    P._SPAN_CACHE.clear()
    spans = P.verify_declared_spans()
    assert set(spans) == set(P.CONSUMED_ARCHIVE_DECLARATIONS)
    assert spans["股價0817-0828.zip"]["observed_covers"] == [
        "2026-08-18", "2026-08-28"]
    assert spans["股價0817-0828.zip"]["rows"] == 17586
    assert spans["股價2023-20260817.zip"]["observed_covers"][1] == "2026-08-17"
    assert spans["股價 2019-2022.zip"]["observed_covers"] == [
        "2019-01-02", "2022-12-30"]


@live
def test_the_verified_span_travels_on_the_entry():
    leaf = P.build(RUN, AS_OF)
    by = {e["locator"]: e for e in leaf["entries"]}
    e = by["股價0817-0828.zip"]
    assert e["covers_verified"]["observed_covers"] == e["covers"]
    assert e["covers_verified"]["rows"] == 17586
    pol = leaf["policies"]["declared_span_verification"]
    assert pol["memoised_on"] == "raw_sha256"
    assert any("MISSING" in s for s in pol["does_not_catch"])


# --- S-8 · the declared set against the SEALED contract -------------------------
#
# The fingerprint gate recomputes the composed manifest from
# `data/b0/price_2019plus_new.parquet`, a sealed artefact that stops at the
# contract's date_max. It never opens the archives, so it cannot see one
# declared beside them.

def _payload(**over):
    import json

    with open(os.path.join(REPO, P.SEALED_PRICE_CONTRACT_JSON),
              encoding="utf-8") as fh:
        payload = json.load(fh)
    payload["contract"] = dict(payload["contract"], **over.pop("contract", {}))
    payload.update(over)
    return payload


CACHE = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
composed = pytest.mark.skipif(
    not (os.path.isdir(CACHE)
         and os.path.isfile(os.path.join(REPO, "data", "b0",
                                         "price_2019plus_new.parquet"))),
    reason="the composed corpus is not present in this clone")


@composed
def test_the_fingerprint_gate_cannot_see_the_declared_set_diverge():
    """S-8, reproduced as a standing characterisation.

    Both of these are true at the same time, and that is the whole finding: the
    sealed fingerprint reproduces exactly while the declared archive set and the
    contract describe different compositions. The second gate is not a
    restatement of the first — it is the only one that can see this."""
    import build_price_panel as B

    contract = B.sealed_contract()
    assert B.assert_reads_the_sealed_source(contract) == contract.content_sha256

    payload = _payload()
    assert sorted(payload["upstream_zips"]) != sorted(
        P.CONSUMED_ARCHIVE_DECLARATIONS)
    assert max(d["covers"][1] for d in
               P.CONSUMED_ARCHIVE_DECLARATIONS.values()) > contract.date_max

    record = P.reconcile_declarations_with_sealed_contract(
        payload=payload, panel_end=P.panel_end_session())
    assert record["divergences"] == {
        "股價0817-0828.zip": [P.DIVERGENCE_NOT_IN_CONTRACT,
                              P.DIVERGENCE_BEYOND_DATE_MAX]}


def test_the_declared_set_reconciles_today_and_says_on_what_condition():
    record = P.reconcile_declarations_with_sealed_contract(
        payload=_payload(), panel_end=P.panel_end_session())
    granted = record["allowances_granted"]["股價0817-0828.zip"]
    assert granted["condition"] == P.ALLOWANCE_CONDITION_PANEL_CLIPS
    checked = granted["checked"][P.CONSUMER_L2_PANEL]
    assert checked["read_end_before_archive_start"] is True
    assert checked["read_end"] == "2026-04-01"
    assert checked["archive_first_covered_session"] == "2026-08-18"
    assert record["reconciled_without_allowance"] == [
        "股價 2019-2022.zip", "股價2023-20260817.zip"]


# --- the clip is a fact about a READER, and the leaf has more than one ----------
#
# The condition was checked every build and checked correctly — against
# `panel_end_session()`, which is the L2 composed panel's end. The L3 prospective
# route reads [lineage_price_floor, execution_session] and never inherits
# `window_end`, so the archive the panel clips away is read in full there.

def test_the_l3_route_reads_straight_through_the_archive_the_panel_clips():
    """D-1, reproduced. Both statements are true of the same archive at once."""
    from core import b0_l3_price_span as lsp

    covers = P.CONSUMED_ARCHIVE_DECLARATIONS["股價0817-0828.zip"]["covers"]
    panel_end = P.panel_end_session()

    # the L2 panel: clipped, which is exactly what the allowance says
    assert panel_end == "2026-04-01"
    assert panel_end < covers[0] == "2026-08-18"

    # the L3 route, Month 1 (U-2: decision 2026-09-30, execution 2026-10-01).
    # `l3_readers.read_prices(run_dir, SOURCE_DEPTH_PROBE, price_span[1])` clips
    # to price_span[1] and to nothing else.
    l3_read_end = lsp.price_span("2004-01-02", "2026-10-01")[1]
    assert l3_read_end == "2026-10-01"
    assert l3_read_end >= covers[1] == "2026-08-28"
    assert not (l3_read_end < covers[0])


def test_the_allowance_names_the_consumer_it_was_checked_for():
    record = P.reconcile_declarations_with_sealed_contract(
        payload=_payload(), panel_end=P.panel_end_session())
    granted = record["allowances_granted"]["股價0817-0828.zip"]
    assert granted["granted_to_consumers"] == [P.CONSUMER_L2_PANEL]
    assert granted["denied_to_consumers"] == [P.CONSUMER_L3_PROSPECTIVE]
    # checked ONCE PER GRANTED CONSUMER, and never for a denied one
    assert sorted(granted["checked"]) == [P.CONSUMER_L2_PANEL]
    assert granted["checked"][P.CONSUMER_L2_PANEL]["consumer"] == \
        P.CONSUMER_L2_PANEL
    assert P.CONSUMER_L3_PROSPECTIVE in granted["not_granted_to_consumers_because"]


def test_the_refusal_list_covers_every_consumer_including_the_empty_ones():
    """A consumer looks itself up by name. Absent from the map must not be
    readable as 'nothing refused for me'."""
    record = P.reconcile_declarations_with_sealed_contract(
        payload=_payload(), panel_end=P.panel_end_session())
    denied = record["archives_denied_to_consumer"]
    assert sorted(denied) == sorted(P.LEAF_CONSUMERS) == record["leaf_consumers"]
    assert denied[P.CONSUMER_L2_PANEL] == []
    assert denied[P.CONSUMER_L3_PROSPECTIVE] == ["股價0817-0828.zip"]


def _regrant(monkeypatch, **over):
    key = ("股價0817-0828.zip", _payload()["contract"]["content_sha256"])
    monkeypatch.setitem(
        P.ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES, key,
        dict(P.ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES[key], **over))


def test_the_clip_may_not_be_granted_to_a_consumer_whose_end_is_unknowable(
        monkeypatch):
    """The defect, expressed as the edit that would hide it again.

    Adding the L3 route to the grant would make the leaf say the archive is
    allowed there — while `read_end < covers[0]` cannot even be evaluated,
    because §19.2's endpoint belongs to a run this module does not know about."""
    _regrant(monkeypatch, granted_to_consumers=(P.CONSUMER_L2_PANEL,
                                                P.CONSUMER_L3_PROSPECTIVE))
    with pytest.raises(ManifestError, match="NOT derivable in this module"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session())


def test_an_allowance_that_names_no_consumer_is_refused(monkeypatch):
    """A leaf-wide allowance is the same defect one level in."""
    _regrant(monkeypatch, granted_to_consumers=())
    with pytest.raises(ManifestError, match="names no consumer"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session())


def test_a_consumer_outside_the_declared_set_is_refused(monkeypatch):
    _regrant(monkeypatch, granted_to_consumers=("SOME_OTHER_READER",))
    with pytest.raises(ManifestError, match="not in the declared consumer set"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session())


def test_a_consumer_added_later_forces_the_allowance_to_be_re_adjudicated(
        monkeypatch):
    """The hole this closes: a third reader appears and inherits a silence."""
    monkeypatch.setitem(P.LEAF_CONSUMERS, "L4_SOME_FUTURE_READER", {
        "reads_through": "?", "read_end_derivation": "?",
        "read_end_is_derivable_here": False, "derived_by": "?",
        "why_not_derivable_here": "fixture"})
    with pytest.raises(ManifestError, match="neither grants nor explains"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session())


def test_a_consumer_that_claims_a_derivable_end_must_actually_be_derived(
        monkeypatch):
    """Fail-closed the other way: a consumer declared derivable but never given
    a read end would be skipped on every allowance."""
    monkeypatch.setitem(P.LEAF_CONSUMERS, "L4_SOME_FUTURE_READER", {
        "reads_through": "?", "read_end_derivation": "?",
        "read_end_is_derivable_here": True, "derived_by": "?"})
    with pytest.raises(ManifestError, match="produces no read end"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session())


@pytest.mark.parametrize("panel_end", ["2026-08-18", "2026-09-30"])
def test_the_allowance_dies_the_moment_the_panel_stops_clipping_it(panel_end):
    """The trap this whole check exists for. 'The panel clips this away today'
    is a fact about a FROZEN WINDOW, so it is re-checked against the panel end
    in use rather than restated — move `window_end` past 2026-04 and the build
    aborts instead of quietly carrying rows the contract does not cover."""
    with pytest.raises(ManifestError, match="no longer true"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=panel_end)


def test_an_allowance_is_void_when_the_source_is_re_registered():
    """Keyed to the sealed fingerprint, not to the contract's NAME:
    `register_price_source.py` hard-codes the name, so a recomposition would
    keep it and let a stale allowance survive the event it must not survive."""
    payload = _payload(contract={"content_sha256": "9" * 64})
    with pytest.raises(ManifestError, match="no allowance is declared"):
        P.reconcile_declarations_with_sealed_contract(
            payload=payload, panel_end=P.panel_end_session())


def test_an_undeclared_divergence_names_both_sides():
    """A fourth archive reaching past the contract, with nothing written for
    it — the case that used to pass silently."""
    decl = dict(P.CONSUMED_ARCHIVE_DECLARATIONS)
    decl["股價0901-0930.zip"] = {
        "leg": "2019+", "raw_sha256": "e" * 64,
        "covers": ("2026-09-01", "2026-09-30"),
        "roster_basis": P.ROSTER_BASIS_CURRENT_SNAPSHOT}
    with pytest.raises(ManifestError, match="股價0901-0930.zip"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session(),
            declarations=decl)


def test_an_allowance_may_not_be_granted_by_a_reason_in_prose(monkeypatch):
    """The condition vocabulary is closed and every member is CHECKED. An
    allowance that explains itself instead of proving itself aborts."""
    key = ("股價0817-0828.zip", _payload()["contract"]["content_sha256"])
    monkeypatch.setitem(
        P.ARCHIVE_BEYOND_SEALED_CONTRACT_ALLOWANCES, key,
        {"condition": "it is fine, the panel clips it away"})
    with pytest.raises(ManifestError, match="not one of"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session())


def test_a_spent_allowance_must_be_removed_not_left_standing():
    """Fail-closed in the other direction: an allowance against this exact
    fingerprint that no longer describes a divergence is a standing permission
    nobody re-reads."""
    decl = {n: d for n, d in P.CONSUMED_ARCHIVE_DECLARATIONS.items()
            if n != "股價0817-0828.zip"}
    with pytest.raises(ManifestError, match="no longer describe a divergence"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session(),
            declarations=decl)


def test_an_archive_the_contract_stands_on_must_be_declared():
    """A source the sealed corpus was composed from that this module does not
    read is a shorter panel wearing the sealed fingerprint."""
    decl = {n: d for n, d in P.CONSUMED_ARCHIVE_DECLARATIONS.items()
            if n != "股價 2019-2022.zip"}
    with pytest.raises(ManifestError, match="does not name"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end=P.panel_end_session(),
            declarations=decl)


def test_the_contract_and_the_declaration_must_name_the_same_bytes():
    payload = _payload()
    payload["upstream_zips"] = dict(payload["upstream_zips"])
    payload["upstream_zips"]["股價 2019-2022.zip"] = "d" * 64
    with pytest.raises(ManifestError, match="different bytes is a different"):
        P.reconcile_declarations_with_sealed_contract(
            payload=payload, panel_end=P.panel_end_session())


@pytest.mark.parametrize("over", [
    {"contract": {"date_max": ""}}, {"contract": {"content_sha256": ""}}])
def test_a_contract_that_cannot_state_its_own_coverage_aborts(over):
    with pytest.raises(ManifestError, match="must declare name, date_max"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(**over), panel_end=P.panel_end_session())


def test_a_document_with_nothing_to_reconcile_against_aborts():
    payload = _payload()
    payload.pop("upstream_zips")
    with pytest.raises(ManifestError, match="nothing to reconcile"):
        P.reconcile_declarations_with_sealed_contract(
            payload=payload, panel_end=P.panel_end_session())


def test_the_panel_end_is_a_measurement_not_an_argument_of_convenience():
    """An allowance whose reason is 'the panel clips this away' is void if the
    clip cannot be read, so an unusable panel end aborts rather than defaulting."""
    with pytest.raises(ManifestError, match="neither YYYYMMDD nor YYYY-MM-DD"):
        P.reconcile_declarations_with_sealed_contract(
            payload=_payload(), panel_end="the panel clips it")


def test_the_panel_end_has_one_owner():
    """`build_price_panel.panel_span()` consumes it. A clip defined in two
    places is a clip that can move in one of them."""
    import build_price_panel as B

    assert B.panel_span()[1] == P.panel_end_session() == "2026-04-01"


@live
def test_the_reconciliation_is_recorded_in_the_leaf():
    leaf = P.build(RUN, AS_OF)
    rec = leaf["policies"]["sealed_source_reconciliation"]
    assert rec["sealed_contract_name"] == "b0_price_universe_20260817"
    assert rec["sealed_contract_date_max"] == "2026-08-17"
    assert rec["declared_archives"] == sorted(P.CONSUMED_ARCHIVE_DECLARATIONS)
    assert rec["divergences"] == {
        "股價0817-0828.zip": [P.DIVERGENCE_NOT_IN_CONTRACT,
                              P.DIVERGENCE_BEYOND_DATE_MAX]}
    assert rec["panel_end_checked"] == "2026-04-01"
    assert "R-W1-1" in rec["allowances_granted"]["股價0817-0828.zip"][
        "why_the_contract_was_not_reissued"]
    # ...and the consumer scope travels with it, so the L3 route can read its
    # own refusal out of the leaf rather than re-deriving the allowance logic.
    assert rec["archives_denied_to_consumer"][P.CONSUMER_L3_PROSPECTIVE] == [
        "股價0817-0828.zip"]
    assert rec["archives_denied_to_consumer"][P.CONSUMER_L2_PANEL] == []


@live
def test_the_leaf_always_publishes_the_consumer_scope(tmp_path):
    """The route's gate reads this record. `build()` reconciles unconditionally,
    so the scope cannot be absent from a leaf this module produced."""
    import ast

    leaf = P.build(RUN, AS_OF)
    assert "archives_denied_to_consumer" in \
        leaf["policies"]["sealed_source_reconciliation"]

    tree = ast.parse(open(P.__file__, encoding="utf-8").read())
    build_fn = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "build")
    calls = [n for n in ast.walk(build_fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "")
             == "reconcile_declarations_with_sealed_contract"]
    assert len(calls) == 1
    # and it is not guarded by anything
    assert not [n for n in ast.walk(build_fn)
                if isinstance(n, (ast.If, ast.Try))
                and any(isinstance(c, ast.Call)
                        and getattr(c.func, "id", "")
                        == "reconcile_declarations_with_sealed_contract"
                        for c in ast.walk(n))]
