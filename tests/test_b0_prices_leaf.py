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
