# -*- coding: utf-8 -*-
"""W6a · L3 source ownership manifests, leaf + aggregate.

The contract these enforce:

    a leaf owns one dataset's source semantics, immutably
    the aggregate indexes every REQUIRED dataset and states readiness honestly
    a W6b receipt binds ONE hash (the aggregate's) and covers every source
    transitively

The four negative cases are the point: a missing leaf, a hash that does not
match, a run_id / as_of that disagrees between tiers, and a source nobody
declared. Each must abort or report NOT_READY — never proceed.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

from core.b0_l3_lineage_capture import (                          # noqa: E402
    PURPOSE_DIAGNOSTIC, PURPOSE_PRODUCTION,
)        # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    AGGREGATE_FILENAME,
    L3_CONTRACT_VERSION,
    LEAF_FILENAME,
    NOT_READY,
    READY,
    REQUIRED_DATASETS,
    SELF_HASH_FIELD,
    ManifestError,
    assemble_aggregate,
    assert_periods_conform,
    assert_ready,
    build_leaf,
    load_aggregate,
    load_leaf,
    payload_sha256,
    verify_aggregate,
    write_aggregate,
    write_leaf,
)

RUN = "L3-0000000000000001"
AS_OF = "2026-08-28"
SEAL = "seal-abc123"


def _entry(locator="a.xlsx", **kw):
    e = {"locator": locator, "format": "xlsx", "raw_sha256": "0" * 64,
         "export_vintage": "2026-08-06",
         "observed_at": "2026-08-26T19:00:00+08:00",
         "source_family": "TEJ", "authority": "AUTHORITATIVE",
         "disposition": "consumed"}
    e.update(kw)
    return e


def _zip_entry(locator="a.zip", **kw):
    return _entry(locator, format="zip",
                  members=[{"name": "x.csv", "size": 10, "crc32": "deadbeef"}],
                  **kw)


def _leaf(dataset, run_id=RUN, as_of=AS_OF, entries=None):
    return build_leaf(dataset=dataset, run_id=run_id, as_of=as_of,
                      entries=entries or [_entry()])


def _full_run(tmp_path, required=REQUIRED_DATASETS):
    run_dir = str(tmp_path)
    for d in required:
        write_leaf(run_dir, _leaf(d))
    return run_dir


# --- leaf shape ----------------------------------------------------------------

def test_a_leaf_carries_the_run_and_the_decision_date():
    leaf = _leaf("financials")
    assert leaf["run_id"] == RUN and leaf["as_of"] == AS_OF
    assert leaf["contract_version"] == L3_CONTRACT_VERSION


@pytest.mark.parametrize("field", [
    "locator", "format", "raw_sha256", "export_vintage", "observed_at",
    "source_family", "authority", "disposition"])
def test_every_entry_field_is_required_never_defaulted(field):
    bad = _entry()
    bad[field] = ""
    with pytest.raises(ManifestError, match="missing"):
        build_leaf(dataset="financials", run_id=RUN, as_of=AS_OF, entries=[bad])


@pytest.mark.parametrize("missing", ["run_id", "as_of", "dataset"])
def test_a_leaf_without_identity_is_refused(missing):
    kw = {"dataset": "financials", "run_id": RUN, "as_of": AS_OF,
          "entries": [_entry()]}
    kw[missing] = ""
    with pytest.raises(ManifestError):
        build_leaf(**kw)


def test_a_locator_declared_twice_is_refused():
    with pytest.raises(ManifestError, match="more than once"):
        build_leaf(dataset="financials", run_id=RUN, as_of=AS_OF,
                   entries=[_entry("a.xlsx"), _entry("a.xlsx")])


# --- ownership -----------------------------------------------------------------

def test_the_transcribed_financials_split_is_expressible():
    leaf = build_leaf(
        dataset="financials", run_id=RUN, as_of=AS_OF,
        entries=[_entry("wb.xlsx", owns="<= 202603", yields=["202606"]),
                 _entry("new.csv", format="csv:utf-16:tab", owns=["202606"],
                        yields=[])])
    owned, yielded = assert_periods_conform(
        leaf["entries"][0], ["202512", "202603", "202606"])
    assert owned == ("202512", "202603") and yielded == ("202606",)


def test_two_owners_for_one_period_is_refused():
    with pytest.raises(ManifestError, match="OWNED by both"):
        build_leaf(dataset="financials", run_id=RUN, as_of=AS_OF,
                   entries=[_entry("a.xlsx", owns="<= 202606", yields=[]),
                            _entry("b.csv", owns=["202606"], yields=[])])


def test_a_period_neither_owned_nor_yielded_aborts():
    e = _entry("wb.xlsx", owns="<= 202603", yields=["202606"])
    with pytest.raises(ManifestError, match="neither OWNS nor YIELDS"):
        assert_periods_conform(e, ["202603", "202609"])


def test_a_source_family_without_period_ownership_is_still_valid():
    """Prices address members by zip inventory, valuation by board/date key.
    Ownership overlap is only meaningful where ownership is in period terms."""
    leaf = build_leaf(dataset="prices", run_id=RUN, as_of=AS_OF,
                      entries=[_zip_entry("a.zip"), _zip_entry("b.zip")])
    assert len(leaf["entries"]) == 2


# --- immutability --------------------------------------------------------------

def test_a_leaf_cannot_be_overwritten(tmp_path):
    write_leaf(str(tmp_path), _leaf("financials"))
    with pytest.raises(ManifestError, match="immutable"):
        write_leaf(str(tmp_path), _leaf("financials"))


def test_an_edited_leaf_is_detected(tmp_path):
    write_leaf(str(tmp_path), _leaf("financials"))
    p = os.path.join(str(tmp_path), LEAF_FILENAME % "financials")
    doc = json.load(open(p, encoding="utf-8"))
    doc["entries"][0]["raw_sha256"] = "9" * 64          # hash field left stale
    open(p, "w", encoding="utf-8").write(json.dumps(doc))

    with pytest.raises(ManifestError, match="EDITED since it was written"):
        load_leaf(p)


def test_the_self_hash_excludes_itself(tmp_path):
    write_leaf(str(tmp_path), _leaf("financials"))
    doc = load_leaf(os.path.join(str(tmp_path), LEAF_FILENAME % "financials"))
    assert payload_sha256(doc) == doc[SELF_HASH_FIELD]


# --- aggregate: the four negative cases ----------------------------------------

def test_a_complete_run_is_ready_and_binds_every_leaf(tmp_path):
    run_dir = _full_run(tmp_path)
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC)
    assert agg["readiness"] == READY
    assert set(agg["leaves"]) == set(REQUIRED_DATASETS)
    for rec in agg["leaves"].values():
        assert len(rec["raw_sha256"]) == 64
        assert len(rec["payload_sha256"]) == 64
    assert_ready(agg)


def test_NEGATIVE_a_missing_leaf_reports_not_ready(tmp_path):
    partial = tuple(d for d in REQUIRED_DATASETS if d != "prices")
    run_dir = _full_run(tmp_path, partial)

    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC)
    assert agg["readiness"] == NOT_READY
    assert agg["missing_datasets"] == ["prices"]
    with pytest.raises(ManifestError, match=NOT_READY):
        assert_ready(agg)


def test_NEGATIVE_a_leaf_changed_after_indexing_is_detected(tmp_path):
    run_dir = _full_run(tmp_path)
    write_aggregate(run_dir, assemble_aggregate(
        run_dir=run_dir, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))

    p = os.path.join(run_dir, LEAF_FILENAME % "financials")
    body = open(p, "rb").read()
    open(p, "wb").write(body + b" ")                    # one byte

    with pytest.raises(ManifestError, match="changed since the aggregate"):
        verify_aggregate(run_dir)


def test_NEGATIVE_a_leaf_from_another_run_is_refused(tmp_path):
    run_dir = str(tmp_path)
    for d in REQUIRED_DATASETS:
        write_leaf(run_dir, _leaf(d, run_id="L3-OTHER" if d == "prices" else RUN))

    with pytest.raises(ManifestError, match="belongs to run"):
        assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                           purpose=PURPOSE_DIAGNOSTIC)


def test_NEGATIVE_a_leaf_with_a_different_as_of_is_refused(tmp_path):
    run_dir = str(tmp_path)
    for d in REQUIRED_DATASETS:
        write_leaf(run_dir, _leaf(d, as_of="2026-07-30" if d == "revenue"
                                  else AS_OF))

    with pytest.raises(ManifestError, match="as of"):
        assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                           purpose=PURPOSE_DIAGNOSTIC)


def test_NEGATIVE_an_undeclared_source_manifest_is_refused(tmp_path):
    run_dir = _full_run(tmp_path)
    write_leaf(run_dir, _leaf("sentiment_overlay"))     # nobody required this

    with pytest.raises(ManifestError, match="not in REQUIRED_DATASETS"):
        assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                           purpose=PURPOSE_DIAGNOSTIC)


# --- the floor is not the caller's to lower ------------------------------------

def test_the_required_floor_covers_the_decision_shaping_sources():
    """Not only the four panels: calendar fixes as_of and the execution session,
    status decides observability, and the CA ledger decides holder outcomes."""
    for dataset in ("calendar", "corporate_actions", "financials", "prices",
                    "revenue", "security_status", "valuation"):
        assert dataset in REQUIRED_DATASETS


def test_the_floor_now_names_the_ratified_W4_A2_inventory(tmp_path):
    """v1.35 / C-70 / §20.8. This used to assert PROVISIONAL. The inventory it
    was owed by exists: the floor IS `route_closure.REQUIRED_DATASET_FLOOR`, and
    a capture refuses a provenance that still calls itself provisional."""
    from core.b0_l3_lineage_capture import (
        RATIFIED_INVENTORY_AUTHORITY, assert_inventory_is_ratified,
    )
    sys.path.insert(0, os.path.join(REPO, "research", "b0_l3"))
    from route_closure import REQUIRED_DATASET_FLOOR

    run_dir = _full_run(tmp_path)
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC)
    assert agg["required_datasets_provenance"] == RATIFIED_INVENTORY_AUTHORITY
    assert_inventory_is_ratified(agg["required_datasets_provenance"])
    assert "W4/A2" in agg["required_datasets_provenance"]
    assert set(agg["required_datasets"]) == set(REQUIRED_DATASET_FLOOR)
    assert set(REQUIRED_DATASETS) == set(REQUIRED_DATASET_FLOOR)


def test_an_aggregate_needs_the_route_seal_it_was_consumed_by(tmp_path):
    """§20.3 (C-70): a production run binds a REAL seal. An empty string and
    'PENDING' are placeholders — they read as bound in every audit that only
    checks the field is present."""
    run_dir = _full_run(tmp_path)
    for placeholder in ("", "PENDING"):
        with pytest.raises(ManifestError, match="placeholder"):
            assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                               purpose=PURPOSE_PRODUCTION,
                               route_seal_id=placeholder)
    with pytest.raises(ManifestError, match="purpose"):
        assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                           purpose="WHATEVER", route_seal_id=SEAL)


# --- what W6b will bind --------------------------------------------------------

def test_one_aggregate_hash_covers_every_source_transitively(tmp_path):
    run_dir = _full_run(tmp_path)
    _, raw = write_aggregate(run_dir, assemble_aggregate(
        run_dir=run_dir, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))

    # A receipt binds `raw`. Re-checking it re-checks every leaf.
    agg = load_aggregate(os.path.join(run_dir, AGGREGATE_FILENAME))
    assert set(agg["leaves"]) == set(REQUIRED_DATASETS)
    assert len(raw) == 64
    verify_aggregate(run_dir)


def test_a_not_ready_aggregate_is_still_written_but_never_consumed(tmp_path):
    """The incomplete state is a fact worth preserving; it just may not run."""
    run_dir = _full_run(tmp_path, tuple(REQUIRED_DATASETS[:2]))
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC)
    write_aggregate(run_dir, agg)
    assert os.path.isfile(os.path.join(run_dir, AGGREGATE_FILENAME))
    with pytest.raises(ManifestError):
        assert_ready(load_aggregate(os.path.join(run_dir, AGGREGATE_FILENAME)))


def test_an_aggregate_cannot_be_overwritten(tmp_path):
    run_dir = _full_run(tmp_path)
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC)
    write_aggregate(run_dir, agg)
    with pytest.raises(ManifestError, match="immutable"):
        write_aggregate(run_dir, agg)


# --- L2 must stay untouched ----------------------------------------------------

def test_the_l3_engine_does_not_import_the_l2_constant():
    """The ruling: no reverse dependency. L2's contract is finished and separate."""
    import ast

    for name in ("source_ownership_manifest.py", "build_financials_leaf.py"):
        path = os.path.join(REPO, "research", "b0_materializer", name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "build_financials_pit" not in node.module, name
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert "build_financials_pit" not in a.name, name
            # A RUNTIME reference, not the word. Both files discuss the L2
            # constant in prose on purpose — explaining why the coupling is
            # forbidden is not the coupling.
            if isinstance(node, ast.Name):
                assert node.id != "SOURCE_OWNERSHIP", name
            if isinstance(node, ast.Attribute):
                assert node.attr != "SOURCE_OWNERSHIP", name


def test_the_two_contracts_are_separately_versioned():
    assert L3_CONTRACT_VERSION == "L3_PROSPECTIVE_SOURCE_MANIFEST_CONTRACT_V1"
