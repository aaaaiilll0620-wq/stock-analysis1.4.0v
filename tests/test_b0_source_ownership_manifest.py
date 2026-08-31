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


# --- P1-1 · the floor is derived from the PURPOSE, never from the caller --------
#
# The reviewer's case: `assemble_aggregate(..., required=("prices",))` against a
# run directory holding one leaf produced an aggregate that recorded
# `required_datasets: ["prices"]` and `readiness: READY`, and BOTH reading gates
# believed it — `verify_aggregate` re-checked only the leaves the aggregate had
# chosen to index, `assert_ready` read the readiness string the same aggregate
# had written. A run could declare a one-family floor and be told it was ready.


def test_the_two_purposes_have_two_DIFFERENT_derived_floors():
    """C-71 · §20.8 vs §20.3. The narrower capture inventory is legitimate and
    must keep working; what may not happen is either floor being chosen per run."""
    from core.b0_l3_lineage_capture import (
        FLOOR_CAPTURE_REQUIRED_DATASETS, PURPOSE_CAPTURE,
    )
    from source_ownership_manifest import normative_floor

    assert normative_floor(PURPOSE_CAPTURE) == tuple(
        sorted(FLOOR_CAPTURE_REQUIRED_DATASETS)) == ("calendar", "prices")
    assert normative_floor(PURPOSE_PRODUCTION) == tuple(sorted(REQUIRED_DATASETS))
    assert normative_floor(PURPOSE_DIAGNOSTIC) == tuple(sorted(REQUIRED_DATASETS))
    assert normative_floor(PURPOSE_CAPTURE) != normative_floor(PURPOSE_PRODUCTION)

    with pytest.raises(ManifestError, match="purpose"):
        normative_floor("WHATEVER")


@pytest.mark.parametrize("purpose,binding", [
    (PURPOSE_PRODUCTION, {"route_seal_id": "L3SEAL-" + "a" * 64}),
    ("LINEAGE_FLOOR_CAPTURE", {"capture_authority": None}),
])
def test_NEGATIVE_a_lineage_making_purpose_may_not_narrow_its_floor(
        tmp_path, purpose, binding):
    """A caller that could shorten the requirement could omit a source and still
    look complete. Refused BEFORE any binding is checked, because a narrowed
    floor is not a binding problem — it is a different run."""
    run_dir = _full_run(tmp_path, ("prices",))
    with pytest.raises(ManifestError, match="derived from the PURPOSE"):
        assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                           purpose=purpose, required=("prices",), **binding)


def test_the_capture_inventory_is_fixed_in_BOTH_directions(tmp_path):
    """C-71. Short lets an off-calendar row set the floor; long puts a hash that
    cannot move the floor into the lineage identity. `assert_capture_inventory`
    owns the rule and is CALLED — this asserts the wiring, not a restatement."""
    from core.b0_l3_lineage_capture import CAPTURE_AUTHORITY, PURPOSE_CAPTURE

    run_dir = _full_run(tmp_path, ("calendar", "prices"))
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_CAPTURE,
                             capture_authority=CAPTURE_AUTHORITY)
    assert agg["required_datasets"] == ["calendar", "prices"]
    assert agg["readiness"] == READY
    write_aggregate(run_dir, agg)
    assert_ready(verify_aggregate(run_dir))          # the capture floor CONSUMES

    for wrong in (("prices",), ("calendar", "prices", "revenue")):
        with pytest.raises(ManifestError):
            assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                               purpose=PURPOSE_CAPTURE,
                               capture_authority=CAPTURE_AUTHORITY,
                               required=wrong)


def test_NEGATIVE_a_diagnostic_may_narrow_but_may_never_be_CONSUMED(tmp_path):
    """The reviewer's exact call. A diagnostic reads what it likes — that is what
    a diagnostic is — but `assert_ready` re-derives the floor from the purpose
    instead of reading the aggregate's account of itself."""
    run_dir = _full_run(tmp_path, ("prices",))
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC, required=("prices",))
    assert agg["readiness"] == READY                 # honest about ITS OWN set
    assert agg["required_datasets"] == ["prices"]

    with pytest.raises(ManifestError, match="derived from the PURPOSE"):
        assert_ready(agg)


def test_NEGATIVE_READY_must_mean_every_required_leaf_is_indexed(tmp_path):
    """The floor can be RIGHT and the index still short. `readiness` is one
    string; the two fields it summarises are checked against each other rather
    than trusted, because a READY that does not mean 'every required leaf is
    here' means nothing."""
    run_dir = _full_run(tmp_path)
    agg = assemble_aggregate(run_dir=run_dir, run_id=RUN, as_of=AS_OF,
                             purpose=PURPOSE_DIAGNOSTIC)
    assert set(agg["required_datasets"]) == set(REQUIRED_DATASETS)
    agg["leaves"].pop("prices")                  # floor intact, index short

    with pytest.raises(ManifestError, match="means nothing"):
        assert_ready(agg)


def test_NEGATIVE_a_resealed_aggregate_cannot_shrink_its_own_index(tmp_path):
    """The self hash proves only that nobody edited the file after it was
    written. Recompute it and the aggregate is internally perfect — so the read
    end reconciles it against the leaves that are actually in the run
    directory, not against its own index."""
    run_dir = _full_run(tmp_path)
    write_aggregate(run_dir, assemble_aggregate(
        run_dir=run_dir, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))

    p = os.path.join(run_dir, AGGREGATE_FILENAME)
    doc = json.load(open(p, encoding="utf-8"))
    doc["required_datasets"] = ["prices"]
    doc["leaves"] = {"prices": doc["leaves"]["prices"]}
    doc.pop(SELF_HASH_FIELD)
    doc[SELF_HASH_FIELD] = payload_sha256(doc)       # internally consistent
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n")

    load_aggregate(p)                                # the self hash still passes
    with pytest.raises(ManifestError, match="not indexed by the aggregate"):
        verify_aggregate(run_dir)


def test_NEGATIVE_a_hand_written_readiness_is_recomputed_not_read(tmp_path):
    """`readiness` is a fact about the source set, not a field the manifest may
    assert about itself."""
    run_dir = _full_run(tmp_path, tuple(d for d in REQUIRED_DATASETS
                                        if d != "prices"))
    write_aggregate(run_dir, assemble_aggregate(
        run_dir=run_dir, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))

    p = os.path.join(run_dir, AGGREGATE_FILENAME)
    doc = json.load(open(p, encoding="utf-8"))
    assert doc["readiness"] == NOT_READY
    doc["readiness"] = READY
    doc["missing_datasets"] = []
    doc.pop(SELF_HASH_FIELD)
    doc[SELF_HASH_FIELD] = payload_sha256(doc)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n")

    with pytest.raises(ManifestError, match="records readiness"):
        verify_aggregate(run_dir)


# --- P1-2 · the reader boundary re-verifies the contract ------------------------
#
# `load_leaf` checked shape, the self hash and ownership overlap. It did not
# re-run the closed vocabularies, so a leaf produced by an older or different
# writer — or by hand — carried an illegal `source_family` straight through.
# The payload hash proves the file has not changed since it was written; it
# proves nothing about whether what was written was admissible.


def _leaf_past_the_writer(tmp_path, mutate, dataset="prices"):
    """Build a legal leaf, mutate it, write it. The self hash is recomputed by
    `write_leaf`, so what lands on disk is internally consistent and illegal."""
    leaf = _leaf(dataset)
    mutate(leaf)
    write_leaf(str(tmp_path), leaf)
    return os.path.join(str(tmp_path), LEAF_FILENAME % dataset)


@pytest.mark.parametrize("label,mutate,message", [
    ("undefined source family",
     lambda l: l["entries"][0].update(source_family="MADE_UP_VENDOR"),
     "not one of"),
    ("R-W1-2: live authority",
     lambda l: l["entries"][0].update(source_family="LIVE",
                                      authority="AUTHORITATIVE"),
     "AUTHORITATIVE"),
    ("undefined disposition",
     lambda l: l["entries"][0].update(disposition="maybe"),
     "not one of"),
    ("consumed archive with no member inventory",
     lambda l: l["entries"][0].update(format="zip"),
     "no member inventory"),
    ("another contract's leaf",
     lambda l: l.update(contract_version="SOME_OTHER_CONTRACT_V9"),
     "this engine enforces"),
    ("a leaf that consumes nothing",
     lambda l: l["entries"][0].update(disposition="not_consumed",
                                      not_consumed_reason="none of it"),
     "consumes nothing"),
])
def test_NEGATIVE_load_leaf_re_runs_the_writers_vocabulary(
        tmp_path, label, mutate, message):
    path = _leaf_past_the_writer(tmp_path, mutate)
    with pytest.raises(ManifestError, match=message):
        load_leaf(path)


# --- P1-3 · a locator names ONE file inside its landing directory ---------------


@pytest.mark.parametrize("locator", [
    r"..\outside.txt", "../outside.txt", "sub/inner.xlsx", r"sub\inner.xlsx",
    "..", ".", "", "C:\\Windows\\win.ini", "/etc/passwd",
])
def test_NEGATIVE_a_locator_may_not_be_a_path_expression(locator):
    """`os.path.join(landing, locator)` treats a locator as a path expression, so
    `..\\x` resolves outside the landing directory — and the raw_sha256 check
    does NOT notice, because it hashes whatever file was reached."""
    from source_ownership_manifest import assert_single_path_component

    with pytest.raises(ManifestError):
        assert_single_path_component(locator, owner="a test")


def test_NEGATIVE_an_escaping_locator_is_refused_at_BOTH_ends(tmp_path):
    with pytest.raises(ManifestError, match="separator"):
        build_leaf(dataset="prices", run_id=RUN, as_of=AS_OF,
                   entries=[_entry(r"..\outside.xlsx")])

    path = _leaf_past_the_writer(
        tmp_path, lambda l: l["entries"][0].update(locator=r"..\outside.xlsx"))
    with pytest.raises(ManifestError, match="separator"):
        load_leaf(path)


def test_a_name_that_resolves_outside_its_directory_is_refused(tmp_path):
    """Containment is decided by `realpath` + `commonpath`, not by inspecting the
    joined string — a string test is exactly what a symlink passes."""
    from source_ownership_manifest import assert_resolves_inside

    landing = os.path.join(str(tmp_path), "landing")
    os.makedirs(landing)
    open(os.path.join(landing, "declared.xlsx"), "wb").write(b"legitimate\n")
    open(os.path.join(str(tmp_path), "outside.xlsx"), "wb").write(b"not ours\n")

    assert assert_resolves_inside(landing, "declared.xlsx") == os.path.join(
        landing, "declared.xlsx")
    with pytest.raises(ManifestError):
        assert_resolves_inside(landing, os.path.join(str(tmp_path),
                                                     "outside.xlsx"))


def test_NEGATIVE_the_aggregates_leaf_path_is_the_same_kind_of_name(tmp_path):
    """`leaves[...]["path"]` is a filename read out of JSON and joined to the run
    directory — the identical shape, one tier up."""
    run_dir = _full_run(tmp_path)
    write_aggregate(run_dir, assemble_aggregate(
        run_dir=run_dir, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))

    p = os.path.join(run_dir, AGGREGATE_FILENAME)
    doc = json.load(open(p, encoding="utf-8"))
    doc["leaves"]["prices"]["path"] = r"..\source_manifest_prices.json"
    doc.pop(SELF_HASH_FIELD)
    doc[SELF_HASH_FIELD] = payload_sha256(doc)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n")

    with pytest.raises(ManifestError, match="separator"):
        verify_aggregate(run_dir)


# --- P2-11 · a manifest is published, not claimed and then filled in ------------
#
# `_write_immutable` claimed the FINAL path with O_EXCL and wrote afterwards.
# Two consequences, both measured: an interruption between the two left a
# ZERO-BYTE manifest that (a) could never be rewritten, because manifests are
# immutable, and (b) was already READABLE -- a concurrent leaf builder or the
# aggregate barrier could open it and fail on a JSON decode error attributed to
# the wrong cause.

class _PowerLoss(RuntimeError):
    """Whatever kills a process between the claim and the last byte."""


def test_an_interrupted_manifest_leaves_nothing_and_is_retryable(tmp_path,
                                                                 monkeypatch):
    import source_ownership_manifest as som

    path = str(tmp_path / (LEAF_FILENAME % "prices"))

    def _die(_path, _blob):
        raise _PowerLoss("between the claim and the bytes")

    monkeypatch.setattr(som, "publish_bytes_exclusively", _die)
    with pytest.raises(_PowerLoss):
        som._write_immutable(path, {"a": 1})
    monkeypatch.undo()

    assert not os.path.exists(path)
    assert os.listdir(str(tmp_path)) == [], "a temporary was left behind"

    payload, raw = som._write_immutable(path, {"a": 1})
    assert len(payload) == 64 and len(raw) == 64
    assert json.load(open(path, encoding="utf-8"))["a"] == 1


def test_a_manifest_is_never_visible_half_written(tmp_path):
    """Whatever appears at the final name is complete, or nothing is there."""
    import source_ownership_manifest as som

    path = str(tmp_path / (LEAF_FILENAME % "prices"))
    som._write_immutable(path, {"a": 1, "b": "\u503c"})

    # The temporary carries a distinguishing suffix and does not survive.
    assert os.listdir(str(tmp_path)) == [os.path.basename(path)]
    doc = json.load(open(path, encoding="utf-8"))
    assert doc["b"] == "\u503c" and SELF_HASH_FIELD in doc


def test_publishing_over_an_existing_manifest_still_fails(tmp_path):
    """Immutability was the whole point and had to survive the change."""
    import source_ownership_manifest as som

    path = str(tmp_path / (LEAF_FILENAME % "prices"))
    som._write_immutable(path, {"a": 1})
    before = open(path, "rb").read()

    with pytest.raises(ManifestError, match="already exists"):
        som._write_immutable(path, {"a": 2})
    assert open(path, "rb").read() == before


def test_the_manifest_bytes_did_not_move(tmp_path):
    """Every leaf and aggregate hash in this project is a hash of these bytes."""
    import source_ownership_manifest as som

    doc = {"schema_version": "x", "z": [1, {"k": "\u503c"}], "a": None}
    path = str(tmp_path / "leaf.json")
    som._write_immutable(path, doc)

    body = {k: v for k, v in doc.items() if k != SELF_HASH_FIELD}
    body[SELF_HASH_FIELD] = som.payload_sha256(body)
    expected = ((json.dumps(body, ensure_ascii=False, sort_keys=True, indent=1)
                 + "\n").replace("\r\n", "\n").encode("utf-8"))
    with open(path, "rb") as fh:
        assert fh.read() == expected
