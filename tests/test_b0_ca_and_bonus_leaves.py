# -*- coding: utf-8 -*-
"""W4 · the last two leaves: a dependency-bearing archive set, and payload keys.

`corporate_actions` is the only family whose rows come from two upstreams — the
seven 配股相關 archives, and security_status, which is the ONLY source that
establishes the disappearing side of a reorganization. It binds the other family
by leaf payload hash rather than restating its files.

`bonus_shares` is addressed by harvested payload key, not filename, and the key
is not allowed to be the truth: it must follow from the structured request.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

import build_bonus_shares_leaf as B                              # noqa: E402
import build_corporate_actions_leaf as CA                        # noqa: E402
import build_flat_leaves as F                                    # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    SELF_HASH_FIELD, ManifestError, assemble_aggregate, write_leaf,
)

RUN, AS_OF = "L3-0000000000000001", "2026-03-30"
CA_LANDING = os.path.join(REPO, CA.LANDING_DIRECTORY)
B_STORE = os.path.join(REPO, B.PAYLOAD_DIRECTORY)
ca_live = pytest.mark.skipif(not os.path.isdir(CA_LANDING),
                             reason="配股相關 export not present")
b_live = pytest.mark.skipif(not os.path.isdir(B_STORE),
                            reason="bonus payload store not present")


# --- corporate_actions: seven archives, one dependency -------------------------

def test_the_declared_archive_set_is_the_seven_the_producer_reads():
    assert len(CA.CONSUMED) == 7
    assert all(n.startswith("配股相關") for n in CA.CONSUMED)


@ca_live
def test_every_consumed_archive_inventories_its_members():
    leaf = CA.build(RUN, AS_OF)
    for e in leaf["entries"]:
        if e["disposition"] == "consumed":
            assert e["members"], e["locator"]


@ca_live
def test_the_dependency_binds_this_runs_security_status_leaf(tmp_path):
    run_dir = str(tmp_path)
    status = F.build("security_status", RUN, AS_OF)
    rec = write_leaf(run_dir, status)

    leaf = CA.build(RUN, AS_OF, run_dir=run_dir)
    dep = leaf["derived_dependencies"]["security_status"]
    # The self-hash is stamped at WRITE time, so the binding is to the written
    # leaf's payload hash — not to anything the in-memory dict carries.
    assert SELF_HASH_FIELD not in status
    assert dep["payload_sha256"] == rec["payload_sha256"]
    assert dep["leaf"] == rec["path"]


@ca_live
def test_building_before_the_status_leaf_exists_aborts(tmp_path):
    """The dependency is on THIS run's declared status source, so it cannot be
    formed before that source has been declared."""
    with pytest.raises(ManifestError, match="has not been written for this run"):
        CA.build(RUN, AS_OF, run_dir=str(tmp_path))


@ca_live
def test_a_status_leaf_from_another_run_is_refused(tmp_path):
    run_dir = str(tmp_path)
    write_leaf(run_dir, F.build("security_status", "L3-OTHER", AS_OF))
    with pytest.raises(ManifestError, match="not"):
        CA.build(RUN, AS_OF, run_dir=run_dir)


@ca_live
def test_a_dependency_pointing_at_a_different_hash_is_caught(tmp_path):
    """The aggregate re-checks the binding: a dependency bound to another run's
    source is a coincidence, not a dependency."""
    run_dir = str(tmp_path)
    for ds in sorted(F.FLAT_FAMILIES):
        write_leaf(run_dir, F.build(ds, RUN, AS_OF))
    leaf = CA.build(RUN, AS_OF, run_dir=run_dir)
    leaf["derived_dependencies"]["security_status"]["payload_sha256"] = "9" * 64
    write_leaf(run_dir, leaf)

    with pytest.raises(ManifestError, match="is not a dependency"):
        assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                           route_seal_id="x",
                           required=tuple(sorted(F.FLAT_FAMILIES))
                           + ("corporate_actions",))


@ca_live
def test_the_stale_provenance_record_is_named_as_inadmissible():
    """`corporate_action_provenance.json` binds ledger f426…, which predates
    B0.3 and B0.4; the current ledger is c838…."""
    pol = CA.build(RUN, AS_OF)["policies"]["derived_artefact"]
    assert "f426" in pol["detail"] and "c838" in pol["detail"]
    assert pol["builder"].endswith("build_corporate_action_ledger.py")


# --- bonus_shares: the key must follow from the request ------------------------

@pytest.mark.parametrize("key,layer", [
    ("twse_range_20260101_20260331", "twse_range"),
    ("tpex_range_20260101_20260331", "tpex_range"),
    ("twse_detail_1101_20180726", "twse_detail"),
])
def test_the_three_frozen_key_forms_round_trip(key, layer):
    request = B.parse_key(key)
    assert request["layer"] == layer
    assert B.recompute_key(request) == key


@pytest.mark.parametrize("bad", [
    "twse_range_2026_20260331", "tpex_detail_1101_20180726",
    "twse_range_20260101", "nasdaq_range_20260101_20260331", ""])
def test_a_key_outside_the_frozen_forms_is_refused(bad):
    with pytest.raises(ManifestError, match="not one of the frozen"):
        B.parse_key(bad)


def test_a_renamed_envelope_is_caught(tmp_path):
    """filename stem, envelope key and recomputed key must all agree."""
    p = os.path.join(str(tmp_path), "twse_range_20260101_20260630.json")
    json.dump({"key": "twse_range_20260101_20260331", "url": "http://x",
               "sha256": "0" * 64, "bytes": 1, "payload": {}},
              open(p, "w", encoding="utf-8"))
    with pytest.raises(ManifestError, match="disagrees with itself"):
        B.read_envelope(p)


@pytest.mark.parametrize("field", ["key", "url", "sha256", "bytes"])
def test_an_envelope_missing_provenance_is_refused(tmp_path, field):
    doc = {"key": "twse_range_20260101_20260331", "url": "http://x",
           "sha256": "0" * 64, "bytes": 1, "payload": {}}
    del doc[field]
    p = os.path.join(str(tmp_path), "twse_range_20260101_20260331.json")
    json.dump(doc, open(p, "w", encoding="utf-8"))
    with pytest.raises(ManifestError, match="has no"):
        B.read_envelope(p)


def test_a_non_envelope_in_the_store_aborts(tmp_path):
    open(os.path.join(str(tmp_path), "notes.txt"), "wb").close()
    with pytest.raises(ManifestError, match="not envelopes"):
        B.build(RUN, AS_OF, payload_dir=str(tmp_path))


@b_live
def test_the_corpus_census_matches_the_three_layers():
    leaf = B.build(RUN, AS_OF)
    census = leaf["policies"]["corpus_census"]
    assert census["counts"] == {"twse_range": 52, "tpex_range": 52,
                                "twse_detail": 1279}
    assert census["total"] == 1383 == len(leaf["entries"])


@b_live
def test_every_entry_carries_the_structured_request_not_only_the_key():
    for e in B.build(RUN, AS_OF)["entries"][:50]:
        assert e["payload_key"] and e["request_params"] and e["url"]
        assert e["exchange"] in ("TWSE", "TPEx")
        assert B.recompute_key({"layer": e["layer"],
                                "params": e["request_params"]}) == e["payload_key"]


@b_live
def test_observed_at_is_not_passed_off_as_a_retrieval_time():
    """These envelopes carry no retrieval timestamp and mtime is not one —
    it changes on copy or restore."""
    pol = B.build(RUN, AS_OF)["policies"]["observed_at_semantics"]
    assert pol["retrieved_at_available"] is False
    assert "mtime" in pol["detail"]


# --- the corrections this round applied ----------------------------------------

def test_security_status_consumes_six_suspension_archives_not_the_event_zip():
    """`build_market_state.py:52` — `SUSP_GLOB = 暫停交易*.zip`, with the comment
    that 事件+下市.zip is a DIFFERENT source. The first declaration here had it
    backwards and was also built from a truncated listing."""
    consumed = F.FLAT_FAMILIES["security_status"]["consumed"]
    assert len(consumed) == 6
    assert all(n.startswith("暫停交易") for n in consumed)
    assert "事件+下市.zip" not in consumed


def test_the_calendar_does_not_come_from_the_tej_suspension_export():
    """`build_market_state.py:53` reads ~/market_cache/taiex_daily.parquet.
    Sharing a producer file is not sharing a source."""
    spec = F.FLAT_FAMILIES["calendar"]
    assert spec["consumed"] == ("taiex_daily.parquet",)
    assert "market_cache" in spec["landing"]
    assert "DataExport" not in spec["landing"]


def test_a_new_sibling_in_the_shared_cache_root_would_abort(tmp_path):
    """The calendar lands in a shared cache root, so its siblings are declared —
    and a NEW one is an unknown, not a shrug."""
    landing = str(tmp_path)
    open(os.path.join(landing, "taiex_daily.parquet"), "wb").close()
    os.makedirs(os.path.join(landing, "surprise_feed"))
    with pytest.raises(ManifestError, match="not a declared format"):
        F.build("calendar", RUN, AS_OF, landing_dir=landing)
