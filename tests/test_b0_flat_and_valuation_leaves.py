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


# --- A-4: the declared source family must match what produced the bytes -------

def test_a_family_landing_outside_the_tej_export_tree_is_not_declared_tej():
    """A-4. The defect: `build_flat_leaves` hardcoded `source_family: "TEJ"` /
    `authority: "AUTHORITATIVE"` for EVERY entry of every flat family. Three of
    the four are TEJ exports, so the constant was accidentally right for them
    and wrong for exactly one — `calendar`, whose bytes are
    `~/market_cache/taiex_daily.parquet`, produced by `core/market_index.py`
    from a FinMind `TaiwanStockPrice(TAIEX)` seed plus daily TWSE `MI_INDEX`
    increments.

    Not a tidiness issue. R-W1-2 rules that two source families coexist with TEJ
    authoritative and the live feed supplying immediacy; the manifest is the
    artefact that ruling is verified from, so a live-derived file stamped TEJ
    makes the ruling unfalsifiable AND is indistinguishable from a source swap.

    Pinned as an INVARIANT rather than as a table of expected values: a family
    whose landing surface is inside `tej_exports/` is a TEJ export, one outside
    it is not, and the declaration must agree with where the bytes live. A new
    family gets checked by the same rule instead of being added to a list."""
    tej_root = os.path.join(REPO, "tej_exports")
    for dataset, spec in sorted(F.FLAT_FAMILIES.items()):
        landing = os.path.abspath(os.path.join(REPO, spec["landing"]))
        inside = (landing == tej_root
                  or landing.startswith(tej_root + os.sep))
        assert (spec["source_family"] == "TEJ") is inside, (
            "%s lands at %s and declares source_family=%r"
            % (dataset, landing, spec["source_family"]))
        if not inside:
            # R-W1-2 through the engine's own vocabulary: a live source supplies
            # immediacy, not authority.
            assert spec["authority"] == "SUPPLEMENTARY", dataset

    # And the one that made this concrete, named — the calendar decides WHEN,
    # and it has no authoritative leg at all. That fact is now IN the artefact.
    assert F.FLAT_FAMILIES["calendar"]["source_family"] == "LIVE"


def test_every_entry_carries_its_family_declaration_not_a_default():
    """The stamp reaches the bytes, not just the spec dict."""
    for dataset, spec in sorted(F.FLAT_FAMILIES.items()):
        landing = os.path.join(REPO, spec["landing"])
        if not os.path.isdir(landing):
            pytest.skip("%s landing not present" % dataset)
        leaf = F.build(dataset, RUN, AS_OF)
        assert leaf["entries"]
        for e in leaf["entries"]:
            assert e["source_family"] == spec["source_family"], e["locator"]
            assert e["authority"] == spec["authority"], e["locator"]


@pytest.mark.parametrize("field", ["source_family", "authority"])
def test_a_family_that_declares_no_source_family_aborts(
        field, tmp_path, monkeypatch):
    """The fix is not 'change TEJ to LIVE for calendar'. A default is what
    produced the defect: it is indistinguishable downstream from a deliberate
    declaration. So an undeclared family must be UNBUILDABLE."""
    landing = str(tmp_path)
    open(os.path.join(landing, "歷史產業類別.xlsx"), "wb").close()
    F.build("industry", RUN, AS_OF, landing_dir=landing)      # control: builds

    spec = dict(F.FLAT_FAMILIES["industry"])
    spec.pop(field)
    monkeypatch.setitem(F.FLAT_FAMILIES, "industry", spec)
    with pytest.raises(ManifestError, match="declares no"):
        F.build("industry", RUN, AS_OF, landing_dir=landing)


# A third family invented HERE ("FINMIND") is refused by
# `source_ownership_manifest._assert_entry_vocabulary` on the way through
# `build_leaf`, and `test_b0_prices_leaf.py:114` already pins that. Measured
# rather than assumed: with `_declared_provenance`'s own vocabulary loop deleted
# the abort still fires, so a copy of it here would be a second authentication
# of one fact — the shape B2 was.


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


# --- revenue: a mixed-format family with a contested month ---------------------
#
# `月營收7月完整.zip` arrived 2026-08-30 and was REFUSED by the enumeration until
# it was declared — the correct behaviour, and the reason these tests pin the
# declaration rather than the abort.

def _revenue_leaf():
    landing = os.path.join(REPO, F.FLAT_FAMILIES["revenue"]["landing"])
    if not os.path.isdir(landing):
        pytest.skip("revenue export not present")
    return F.build("revenue", RUN, AS_OF)


def test_the_completed_july_archive_is_a_declared_source():
    """The workbook was exported 2026-08-06 and its July is PARTIAL: 406 of
    2,002 securities, only those that had announced by then. A panel built from
    it alone at an as_of after 08-10 would look complete and be 80% short."""
    by = {e["locator"]: e for e in _revenue_leaf()["entries"]}
    assert by["20260806091706.xlsx"]["disposition"] == "consumed"
    assert by["月營收7月完整.zip"]["disposition"] == "consumed"


def test_the_archive_declares_what_its_member_actually_is():
    """A zip by container, a UTF-16LE tab csv by content — the financials idiom
    (`2026 0826 2385家.csv` is declared `csv:utf-16:tab` for the same reason).
    The `zip:` prefix is what keeps the member inventory mandatory."""
    entry = {e["locator"]: e
             for e in _revenue_leaf()["entries"]}["月營收7月完整.zip"]
    assert entry["format"] == "zip:csv:utf-16:tab"
    assert [m["name"] for m in entry["members"]] == ["20260830033323.csv"]


def test_the_two_revenue_sources_own_disjoint_months():
    """Both files carry 202607. Exactly one may be canonical for it: the later
    export OWNS it (2,002 securities, a strict superset — only-xlsx = 0) and the
    workbook YIELDS it."""
    from source_ownership_manifest import owns_predicate

    by = {e["locator"]: e for e in _revenue_leaf()["entries"]}
    book, zipped = by["20260806091706.xlsx"], by["月營收7月完整.zip"]
    assert book["owns"] == "<= 202606" and book["yields"] == ["202607"]
    assert zipped["owns"] == ["202607"]

    owns_book, _ = owns_predicate(book["owns"])
    owns_zip, _ = owns_predicate(zipped["owns"])
    for period in ("202605", "202606", "202607"):
        assert not (owns_book(period) and owns_zip(period)), period
    assert owns_zip("202607") and not owns_book("202607")


def _staged_revenue_landing(tmp_path):
    """A stand-in landing with the two declared names; the archive is a real
    zip because a consumed archive must inventory its members."""
    import zipfile

    open(os.path.join(str(tmp_path), "20260806091706.xlsx"), "wb").close()
    with zipfile.ZipFile(
            os.path.join(str(tmp_path), "月營收7月完整.zip"), "w") as z:
        z.writestr("20260830033323.csv", "x")
    return str(tmp_path)


def test_a_second_claimant_for_one_month_is_refused(tmp_path, monkeypatch):
    """Negative control on the split above: let the workbook keep 202607 and the
    leaf must not build."""
    landing = _staged_revenue_landing(tmp_path)
    monkeypatch.setitem(F.FLAT_FAMILIES["revenue"], "declarations", {
        "20260806091706.xlsx": {"owns": "<= 202607"},
        "月營收7月完整.zip": {"format": "zip:csv:utf-16:tab",
                              "owns": ["202607"]},
    })
    with pytest.raises(ManifestError, match="OWNED by both"):
        F.build("revenue", RUN, AS_OF, landing_dir=landing)


def test_ownership_is_declared_for_every_consumed_source_or_for_none(
        tmp_path, monkeypatch):
    """An entry without `owns` is invisible to `assert_no_overlapping_ownership`
    — an undeclared claimant no overlap check can see. Families that address
    their members some other way (security_status' six archives) declare none,
    and that stays legal."""
    landing = _staged_revenue_landing(tmp_path)
    monkeypatch.setitem(F.FLAT_FAMILIES["revenue"], "declarations", {
        "月營收7月完整.zip": {"format": "zip:csv:utf-16:tab",
                              "owns": ["202607"]},
    })
    with pytest.raises(ManifestError, match="ownership is declared for every"):
        F.build("revenue", RUN, AS_OF, landing_dir=landing)

    assert "declarations" not in F.FLAT_FAMILIES["security_status"]
    if os.path.isdir(os.path.join(
            REPO, F.FLAT_FAMILIES["security_status"]["landing"])):
        F.build("security_status", RUN, AS_OF)


def test_a_declaration_aimed_at_a_file_the_family_does_not_consume_is_refused(
        tmp_path, monkeypatch):
    """It would sit in the spec looking like a decision that was made, while the
    engine applied nothing."""
    landing = _staged_revenue_landing(tmp_path)
    monkeypatch.setitem(F.FLAT_FAMILIES["revenue"], "declarations", {
        **F.FLAT_FAMILIES["revenue"]["declarations"],
        "20260901000000.xlsx": {"owns": ["202608"]},
    })
    with pytest.raises(ManifestError, match="which it does not consume"):
        F.build("revenue", RUN, AS_OF, landing_dir=landing)


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
