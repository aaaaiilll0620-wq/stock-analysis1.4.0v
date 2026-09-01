# -*- coding: utf-8 -*-
"""W4 · the valuation leaf and the four flat-directory leaves.

Valuation is the only family addressed by a KEY rather than a filename, because
C-48/C-49 make the exchange payload the lineage and forbid a TEJ substitute. The
rest land as directories and differ only by declaration.

The defect these exist for is the same one throughout: an enumeration that
answers, and a client that does not hear it.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

import build_flat_leaves as F                                    # noqa: E402
import build_valuation_leaf as V                                 # noqa: E402
from source_ownership_manifest import ManifestError              # noqa: E402

RUN, AS_OF = "L3-0000000000000001", "2026-03-30"
STORE = os.path.join(REPO, V.PAYLOAD_DIRECTORY)
harvested = pytest.mark.skipif(
    not os.path.isfile(os.path.join(STORE, "twse_%s.json" % AS_OF)),
    reason="valuation payloads not harvested")


# --- valuation: the payload key ------------------------------------------------

@harvested
def test_a_session_declares_both_boards():
    """The frozen universe is sii ∪ otc; one board answering is not an answer."""
    leaf = V.build(RUN, AS_OF)
    assert sorted(e["board"] for e in leaf["entries"]) == ["TPEx", "TWSE"]
    for e in leaf["entries"]:
        assert e["session"] == AS_OF
        assert e["rows"] > 0


@harvested
def test_the_two_boards_are_addressed_differently_because_they_are_different():
    leaf = V.build(RUN, AS_OF)
    by = {e["board"]: e for e in leaf["entries"]}
    assert by["TWSE"]["rows_path"] == ["data"]
    assert by["TPEx"]["rows_path"] == ["tables", 0, "data"]
    # Measured: TPEx publishes no 收盤價 on this endpoint.
    assert by["TWSE"]["carries_close"] is True
    assert by["TPEx"]["carries_close"] is False


def test_an_unharvested_session_aborts_rather_than_substituting():
    with pytest.raises(ManifestError, match="have not been harvested"):
        V.build(RUN, "1990-01-02")


def test_a_renamed_ratio_column_aborts(tmp_path):
    """THE valuation defect. `idx()` returns None on a renamed column and every
    row is then skipped, so the session silently becomes all-NA — and NA is a
    class the frozen lineage legitimately has, so nothing downstream blinks."""
    p = os.path.join(str(tmp_path), "twse_2026-03-30.json")
    json.dump({"stat": "OK", "fields": ["證券代號", "本益比", "PBR"],
               "data": [["1101", "10.0", "1.2"]]},
              open(p, "w", encoding="utf-8"), ensure_ascii=False)

    with pytest.raises(ManifestError, match="missing declared field"):
        V.read_payload_key(p, "twse")


def test_a_changed_payload_shape_aborts(tmp_path):
    p = os.path.join(str(tmp_path), "tpex_2026-03-30.json")
    json.dump({"stat": "OK", "data": [], "fields": []},   # no `tables`
              open(p, "w", encoding="utf-8"), ensure_ascii=False)
    with pytest.raises(ManifestError, match="declared payload shape"):
        V.read_payload_key(p, "tpex")


def test_zero_rows_is_not_the_same_fact_as_no_answer(tmp_path):
    p = os.path.join(str(tmp_path), "twse_2026-03-30.json")
    json.dump({"stat": "OK", "fields": ["證券代號", "本益比", "股價淨值比"],
               "data": []}, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    with pytest.raises(ManifestError, match="zero rows"):
        V.read_payload_key(p, "twse")


@harvested
def test_the_substitution_ban_travels_with_the_source():
    pol = V.build(RUN, AS_OF)["policies"]
    assert pol["substitution"]["rule"] == \
        "TEJ_SUBSTITUTION_FORBIDDEN_FOR_2019_PLUS"
    assert pol["close_source"]["rule"] == \
        "PRICED_UNIVERSE_COMES_FROM_THE_PRICE_PANEL_NOT_THE_PAYLOAD"


# --- flat families -------------------------------------------------------------

@pytest.mark.parametrize("dataset", sorted(F.FLAT_FAMILIES))
def test_each_flat_family_declares_exact_filenames_never_a_pattern(dataset):
    """A pattern is how a file joins the panel without anyone deciding it should."""
    consumed = F.FLAT_FAMILIES[dataset]["consumed"]
    assert consumed
    for name in consumed:
        assert "*" not in name and "?" not in name, name


@pytest.mark.parametrize("dataset", sorted(F.FLAT_FAMILIES))
def test_each_flat_family_builds_and_names_every_entry(dataset):
    landing = os.path.join(REPO, F.FLAT_FAMILIES[dataset]["landing"])
    if not os.path.isdir(landing):
        pytest.skip("%s export not present" % dataset)

    leaf = F.build(dataset, RUN, AS_OF)
    on_disk = {n for n in os.listdir(landing)
               if os.path.isfile(os.path.join(landing, n))}
    assert {e["locator"] for e in leaf["entries"]} == on_disk
    for e in leaf["entries"]:
        if e["disposition"] == "not_consumed":
            assert e["not_consumed_reason"]


# --- A-4 · provenance is declared per family, never defaulted -------------------

@pytest.mark.parametrize("dataset", sorted(F.FLAT_FAMILIES))
def test_each_flat_family_declares_its_own_provenance(dataset):
    """A default cannot be told apart downstream from a deliberate declaration."""
    spec = F.FLAT_FAMILIES[dataset]
    for field in F._FAMILY_PROVENANCE_FIELDS:
        assert spec.get(field), "%s declares no %s" % (dataset, field)


def test_the_calendar_is_the_live_family_and_says_so():
    """A-4. `~/market_cache/taiex_daily.parquet` is a FinMind seed plus daily
    TWSE increments, not a TEJ export. Stamping it TEJ/AUTHORITATIVE made the
    R-W1-2 audit unable to contradict a source swap in the one field that reads
    provenance -- and it hid N-1, since the family that decides WHEN then has no
    authoritative leg to reconcile against."""
    spec = F.FLAT_FAMILIES["calendar"]
    assert (spec["source_family"], spec["authority"]) == ("LIVE", "SUPPLEMENTARY")

    landing = os.path.join(REPO, spec["landing"])
    if not os.path.isdir(landing):
        pytest.skip("calendar cache not present")
    leaf = F.build("calendar", RUN, AS_OF)
    assert leaf["entries"], "calendar leaf has no entries"
    for e in leaf["entries"]:
        assert (e["source_family"], e["authority"]) == ("LIVE", "SUPPLEMENTARY")


@pytest.mark.parametrize("field", F._FAMILY_PROVENANCE_FIELDS)
def test_a_family_that_declares_no_provenance_is_unbuildable(monkeypatch, field):
    """Absence ABORTS. It may not fall back to the constant this replaced."""
    spec = dict(F.FLAT_FAMILIES["industry"])
    spec.pop(field)
    monkeypatch.setitem(F.FLAT_FAMILIES, "industry", spec)

    landing = os.path.join(REPO, spec["landing"])
    if not os.path.isdir(landing):
        pytest.skip("industry export not present")
    with pytest.raises(ManifestError, match="declares no"):
        F.build("industry", RUN, AS_OF)


def test_a_live_family_may_not_declare_itself_authoritative():
    """The engine already refuses the combination; A-4 must not route around it
    by declaring one."""
    spec = dict(F.FLAT_FAMILIES["calendar"])
    spec["authority"] = "AUTHORITATIVE"
    assert F._declared_provenance("calendar", spec) == {
        "source_family": "LIVE", "authority": "AUTHORITATIVE"}, (
        "_declared_provenance only checks ABSENCE; the combination is the "
        "manifest engine's call")

    from source_ownership_manifest import _assert_entry_vocabulary
    entry = {"locator": "taiex_daily.parquet", "source_family": "LIVE",
             "authority": "AUTHORITATIVE", "disposition": "consumed"}
    with pytest.raises(ManifestError, match="AUTHORITATIVE"):
        _assert_entry_vocabulary("calendar", entry)


def test_the_current_industry_table_is_refused_as_a_source():
    """O-E: the live industry map is NOT_PIT_SAFE — 49.4% of names changed
    sector under it — so the CURRENT table must not be consumed."""
    landing = os.path.join(REPO, F.FLAT_FAMILIES["industry"]["landing"])
    if not os.path.isdir(landing):
        pytest.skip("industry export not present")

    leaf = F.build("industry", RUN, AS_OF)
    by = {e["locator"]: e for e in leaf["entries"]}
    assert by["歷史產業類別.xlsx"]["disposition"] == "consumed"
    if "現在產業類別.xlsx" in by:
        assert by["現在產業類別.xlsx"]["disposition"] == "not_consumed"


def test_calendar_and_security_status_do_not_share_a_source():
    """CORRECTED. An earlier version of this test asserted they shared the TEJ
    suspension export — pinning a declaration that was simply wrong.
    `build_market_state.py` writes both files from ONE producer but TWO sources:
    `CAL_SRC = ~/market_cache/taiex_daily.parquet` (line 53) and
    `SUSP_GLOB = 暫停交易*.zip` (line 52). Sharing a producer is not sharing a
    source, and a test can pin a mistake as firmly as a fact."""
    assert F.FLAT_FAMILIES["calendar"]["landing"] != \
        F.FLAT_FAMILIES["security_status"]["landing"]
    assert F.FLAT_FAMILIES["calendar"]["consumed"] == ("taiex_daily.parquet",)


def test_only_consumed_archives_need_a_member_inventory():
    """The archive rule belongs to the engine, not to prices — but it exists to
    detect a change in what is READ. A not_consumed archive cannot change a
    value, so requiring an inventory for it would be ceremony."""
    landing = os.path.join(REPO, F.FLAT_FAMILIES["security_status"]["landing"])
    if not os.path.isdir(landing):
        pytest.skip("suspension export not present")

    leaf = F.build("security_status", RUN, AS_OF)
    seen_consumed = seen_skipped = False
    for e in leaf["entries"]:
        if e["format"] != "zip":
            continue
        if e["disposition"] == "consumed":
            assert e["members"], e["locator"]
            seen_consumed = True
        else:
            assert "members" not in e, e["locator"]
            seen_skipped = True
    assert seen_consumed and seen_skipped, "this export exercises both branches"


def test_an_undeclared_extension_in_the_landing_dir_aborts(tmp_path):
    landing = str(tmp_path)
    open(os.path.join(landing, "20260806091706.xlsx"), "wb").close()
    open(os.path.join(landing, "notes.txt"), "wb").close()

    with pytest.raises(ManifestError, match="not a declared format"):
        F.build("revenue", RUN, AS_OF, landing_dir=landing)


def test_a_declared_file_that_vanished_aborts(tmp_path):
    open(os.path.join(str(tmp_path), "other.xlsx"), "wb").close()
    with pytest.raises(ManifestError, match="not present"):
        F.build("revenue", RUN, AS_OF, landing_dir=str(tmp_path))


# --- what is deliberately NOT declared -----------------------------------------

@pytest.mark.parametrize("dataset", sorted(F.UNRESOLVED_FAMILIES))
def test_an_unestablished_upstream_is_refused_not_guessed(dataset):
    """`corporate_actions` decides holder outcomes and carries the
    NOT_RECONSTRUCTIBLE rows B0.7 terminates on. A guessed lineage there is the
    worst possible guess, so the aggregate stays NOT_READY for a nameable
    reason instead."""
    with pytest.raises(ManifestError, match="no declared source contract"):
        F.build(dataset, RUN, AS_OF)


def test_the_unresolved_families_are_exactly_the_gap_in_the_floor():
    from source_ownership_manifest import REQUIRED_DATASETS

    covered = set(F.FLAT_FAMILIES) | {"financials", "prices", "valuation"}
    assert set(REQUIRED_DATASETS) - covered == set(F.UNRESOLVED_FAMILIES)


@pytest.mark.parametrize("dataset", sorted(F.UNRESOLVED_FAMILIES))
def test_every_unresolved_family_says_why(dataset):
    assert len(F.UNRESOLVED_FAMILIES[dataset]) > 60
