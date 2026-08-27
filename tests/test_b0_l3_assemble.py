# -*- coding: utf-8 -*-
"""W6b-2 (assembly) · nine parsed families -> one canonical decision state.

The readers were checked against nine sealed panels. The assembly is checked
against ONE number, and it is the strongest check in this tree:

    L2's sealed market_state_sha256 for 2026-03
      3a95d77e25fcd3ebd9c80fa461c27857c1dd22df8c41da20f50dfc42c9d81786

That hash covers marks, adv20, sigma20d, execution prices, untradable, the PIT
status dates, the listing spells, every SecurityPitInputs series and the
corporate-action events. Reproducing it from a run's declared source manifest is
a single statement that the whole assembly agrees with the frozen route.

MEASURED 2026-08-27 (opt in with B0_L3_PARITY=1):

    2026-03  1,958 securities  hash identical to L2's sealed state

WHAT GETTING THERE MEASURED
---------------------------
Two things that were wrong and one that was not:

  * the prices leaf declared only the 2019+ archive leg while its own docstring
    described two. With one leg, 1,706 of 1,958 spell starts moved, most of them
    to 2019-01-02 — the corpus edge wearing a listing date.
  * L2's row artefact stores a listed security's absent status dates as the
    STRING "None", because its read-back applies `str()` to every text column.
    Comparing that against an in-memory None reported 1,687 differences that do
    not exist; the hashed payload carries those fields only for non-listed rows.
  * `spell_start` then still differed, and that one is NOT a defect: it is a
    property of how deep the price span is. L2's own 1101 台泥 spell starts
    2013-01-02 because that is where `panel_span()` starts, not where 台泥
    listed.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(REPO, "research", "b0_materializer"),
           os.path.join(REPO, "research", "b0_l3")):
    sys.path.insert(0, _p)

import build_bonus_shares_leaf as B                              # noqa: E402
import build_corporate_actions_leaf as CA                        # noqa: E402
import build_financials_leaf as FIN                              # noqa: E402
import build_flat_leaves as F                                    # noqa: E402
import build_prices_leaf as P                                    # noqa: E402
import build_valuation_leaf as V                                 # noqa: E402
import l3_assemble as A                                          # noqa: E402
import l3_snapshot as S                                          # noqa: E402
import verify_assembly_parity as AP                              # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    assemble_aggregate, write_aggregate, write_leaf,
)

RUN, AS_OF, DECISION = "L3-0000000000000001", "2026-03-30", "2026-03-31"
SEALED_2026_03 = "3a95d77e25fcd3ebd9c80fa461c27857c1dd22df8c41da20f50dfc42c9d81786"

sources = pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO, P.LANDING_DIRECTORY)),
    reason="TEJ exports not present")
heavy = pytest.mark.skipif(
    os.environ.get("B0_L3_PARITY") != "1",
    reason="set B0_L3_PARITY=1 (reads hundreds of MB and rebuilds a period)")


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("l3asm"))
    for ds in sorted(F.FLAT_FAMILIES):
        write_leaf(d, F.build(ds, RUN, AS_OF))
    for mod in (FIN, P, B, V):
        write_leaf(d, mod.build(RUN, AS_OF))
    write_leaf(d, CA.build(RUN, AS_OF, run_dir=d))
    write_aggregate(d, assemble_aggregate(
        run_dir=d, run_id=RUN, as_of=AS_OF, route_seal_id="PENDING"))
    return d


@pytest.fixture(scope="module")
def assembled(run_dir):
    if os.environ.get("B0_L3_PARITY") != "1":
        pytest.skip("set B0_L3_PARITY=1")
    return A.assemble(run_dir, RUN, DECISION,
                      lineage_price_floor=AP.L2_PANEL_FLOOR)


# --- §19 / C-68 · the span endpoints are derived, and the floor is frozen --------

@sources
def test_the_lineage_floor_may_not_be_defaulted(run_dir):
    """§19.3. The floor sets the listing spells and therefore the state hash, so
    a run that did not declare one may not have one picked for it here."""
    with pytest.raises(A.AssemblyError, match="lineage_price_floor"):
        A.assemble(run_dir, RUN, DECISION)


@sources
def test_the_other_three_endpoints_are_not_caller_supplied(run_dir):
    """§19.2 / §19.5: this module is enforcement. There is no argument to pass
    an endpoint through, so a caller cannot quietly re-derive one."""
    import inspect

    params = set(inspect.signature(A.assemble).parameters)
    assert "price_span" not in params and "bonus_window" not in params
    assert A.SPAN_DERIVATION_AUTHORITY["producer"] == "core.b0_l3_price_span"
    assert A.SPAN_DERIVATION_AUTHORITY["this_module"] == (
        "ENFORCEMENT_NOT_SEMANTIC_AUTHORITY")
    assert dict(A.SPAN_DERIVATION_AUTHORITY["endpoints"])["price_span[1]"] == (
        "EXECUTION_DATE")


def test_the_producer_refuses_a_floor_from_unbound_sources():
    """§19.3 step 1: a floor is only capturable from a complete, hash-bound leaf."""
    from core.b0_l3_price_span import L3SpanError, capture_lineage_floor

    with pytest.raises(L3SpanError, match="hash-bound"):
        capture_lineage_floor("2004-01-02", source_manifest_is_hash_bound=False,
                              leg_coverage_is_complete=True,
                              quarantine_applied=True)
    assert capture_lineage_floor(
        "2004-01-02", source_manifest_is_hash_bound=True,
        leg_coverage_is_complete=True, quarantine_applied=True) == "2004-01-02"


# --- §2.8.3's two price legs ----------------------------------------------------

@sources
def test_both_price_legs_must_be_declared(run_dir):
    """§2.8.3 splits the lineage at 2019-01-01 and the halves live in different
    trees, so one landing directory cannot address both."""
    legs = A.assert_both_price_legs_are_declared(run_dir)
    assert legs["pre-2019"] > 2000            # one parquet per security
    assert legs["2019+"] == 2                 # the two declared archives


@sources
def test_a_prices_leaf_without_the_pre_2019_leg_is_refused(tmp_path):
    """Measured cost of the missing leg: 1,706 of 1,958 spell starts moved."""
    leaf = P.build(RUN, AS_OF)
    write_leaf(str(tmp_path), {**leaf,
                               "entries": [e for e in leaf["entries"]
                                           if e.get("leg") != "pre-2019"]})
    with pytest.raises(A.AssemblyError, match="no pre-2019 leg"):
        A.assert_both_price_legs_are_declared(str(tmp_path))


def test_the_two_legs_disagree_about_what_a_volume_number_means():
    """Applying either convention to the other does not raise — it moves every
    security 1000x across §4.2's absolute NTD liquidity floor."""
    import l3_readers as R

    assert R.VOLUME_THOUSANDS_TO_SHARES == 1000.0            # 2019+ leg
    assert "Trading_Volume" in R.PRE_2019_COLUMNS            # pre-2019 leg
    conv = P.LEG_UNIT_CONVENTIONS
    assert "ALREADY shares" in conv["pre-2019"]
    assert "thousands" in conv["2019+"]


def test_the_quarantined_era_is_a_date_not_a_file():
    """D-1 quarantined the 2019+ ERA of the pre-2019 cache, not the cache. The
    same parquet holds admissible and quarantined rows, so which files are
    declared cannot express the restriction."""
    assert P.QUARANTINED_ERA_POLICY["boundary"] == "2019-01-01"
    assert P.QUARANTINED_ERA_POLICY["applies_to_leg"] == "pre-2019"


# --- definition B ---------------------------------------------------------------

def test_the_market_state_may_not_carry_a_portfolio():
    """portfolio[t] is causally generated by executing t-1; a market-side hash
    with a placeholder for it would be a hash of a fabrication."""
    for field in A.PORTFOLIO_FIELDS:
        with pytest.raises(A.AssemblyError, match="portfolio"):
            A.assert_market_state_is_portfolio_free({"as_of": "x", field: 0})


@sources
@heavy
def test_the_assembled_payload_is_portfolio_free(assembled):
    assert not (set(A.PORTFOLIO_FIELDS) & set(assembled["payload"]))
    A.assert_market_state_is_portfolio_free(assembled["payload"])


# --- the rules come from core, not from a second copy --------------------------

def test_the_depths_are_derived_from_the_frozen_members():
    """The first sealed L2 run rejected 100% of the universe in every period
    because its builder said 13 where `revenue_accel` needs 18, and nothing
    compared the two."""
    from core.b0_features import series_requirements

    req = series_requirements()
    assert A.MONTHS_REVENUE == req["monthly_revenue"] == 18
    assert A.MONTH_ENDS_REQUIRED == req["month_end_prices"] == 14
    assert A.QUARTERS >= req["eps_by_quarter"]


def test_the_assembler_imports_its_rules_rather_than_restating_them():
    import ast

    path = os.path.join(REPO, "research", "b0_l3", "l3_assemble.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}

    assert {"core.b0_listing_spell", "core.b0_share_unit_adjustment",
            "core.b0_state", "core.b0_features"} <= imported
    assert "tej_importer" not in imported
    assert not [m for m in imported if m.startswith("build_")]


def test_the_assembler_never_writes_to_the_sealed_data_directory():
    import ast

    for name in ("l3_assemble.py", "verify_assembly_parity.py"):
        path = os.path.join(REPO, "research", "b0_l3", name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                dotted = getattr(fn, "attr", "") or getattr(fn, "id", "")
                assert dotted not in ("to_parquet", "to_csv"), name


# --- L2's round-trip artefact ---------------------------------------------------

def test_a_listed_securitys_absent_status_dates_read_back_as_none():
    """L2's row artefact stores them as the string "None" because its read-back
    applies `str()` to every text column. That is a property of the parquet
    round-trip, not of the state L2 hashed, and comparing against it naively
    reported 1,687 differences that do not exist."""
    assert set(AP.NULLABLE_STRING_COLUMNS) == {"status_available_from",
                                               "status_effective_from"}
    assert "status_available_from" not in AP.STRING_COLUMNS


# --- parity ---------------------------------------------------------------------

@sources
@heavy
def test_the_assembled_state_is_the_state_l2_sealed(assembled):
    """The whole point. One hash, every field."""
    assert assembled["market_state_sha256"] == SEALED_2026_03
    assert assembled["securities"] == 1958
    assert assembled["period"]["as_of"] == AS_OF
    assert assembled["period"]["execution_date"] == "2026-04-01"


@sources
@heavy
def test_verify_market_state_reports_the_match(run_dir):
    got = AP.verify_market_state(run_dir, RUN, DECISION)
    assert got["market_state_sha256"] == SEALED_2026_03
    assert got["decision_month"] == "2026-03"
    assert got["price_coverage_floor"] == "2013-01-02"
    # L2's own sealed spells sit at its panel-span floor for most securities.
    assert got["spell_starts_at_price_coverage_floor"] > 1000


@sources
@heavy
def test_a_shallower_price_span_moves_the_state(run_dir):
    """Negative control, and the finding it pins: `spell_start` is a property of
    the corpus depth, not of the security."""
    with pytest.raises(AP.AssemblyParityError, match="spell_start"):
        AP.verify_market_state(run_dir, RUN, DECISION,
                               lineage_price_floor="2019-01-01")


# --- the seam into the route ----------------------------------------------------

@sources
@heavy
def test_the_assembly_produces_production_sources(assembled, run_dir):
    """`ProductionSources` has the same field names, units and NA semantics as
    the retrospective one — P2-3 requires a field to mean one thing across both
    routes."""
    from core.b0_state import SourceAttestation

    attestation = SourceAttestation(
        dataset_id="l3_market_side_state",
        provenance_sha256="0" * 64,
        pit_guard_passed=True, universe_guard_passed=True,
        satisfied_blocking_requirements=(), synthetic=False)
    sources_obj, exec_px, untradable = A.build_production_sources(
        assembled, run_dir, attestation)

    assert len(sources_obj.pit_inputs) == assembled["securities"]
    assert len(sources_obj.listing_spells) == assembled["securities"]
    assert sources_obj.marks == assembled["payload"]["marks"]
    assert exec_px == assembled["payload"]["execution_prices"]
    assert sorted(untradable) == assembled["payload"]["untradable"]

    # O-E: the full series is HELD but only reachable through as_of. Handing
    # out the whole sequence would let a caller ask "is next month a holiday?",
    # which is answerable in reality but not from data a replay may hold.
    cal = sources_obj.calendar
    assert not hasattr(cal, "sessions")
    assert cal.sessions_through(AS_OF)[-1] == AS_OF
    assert cal.coverage[1] > AS_OF          # §6.5's execution session is inside
    # O-E, at the point where a live feed would smuggle 'now' in.
    sources_obj.status_table.source.assert_pit_safe()
    assert all(s.as_of == AS_OF and s.start <= AS_OF
               for s in sources_obj.listing_spells)

    # Definition A, not an oversight: both are consumed per HELD position —
    # `assert_no_unexplained_gap_in_holdings` asks whether a gap in something B0
    # OWNS is explained, and B0.4's block fires on held + exit +
    # NOT_RECONSTRUCTIBLE. With no portfolio there is nothing to ask about, so
    # they belong to the portfolio side and the runner (B7) fills them.
    assert sources_obj.price_observations == ()
    assert sources_obj.corporate_action_events == ()
    assert sources_obj.exposures == ()


# --- RECEIPT_ONLY -> MATERIALIZED -----------------------------------------------

@sources
@heavy
def test_the_receipt_becomes_materialized_only_with_an_assembled_state(
        run_dir, assembled):
    only = S.build_receipt(run_dir, RUN, DECISION)
    assert only["state"] == S.STATE_RECEIPT_ONLY
    with pytest.raises(S.L3SnapshotError, match="have not been parsed"):
        S.assert_snapshot_complete(only)

    full = S.build_receipt(run_dir, RUN, DECISION, assembled=assembled)
    assert full["state"] == S.STATE_MATERIALIZED
    S.assert_snapshot_complete(full)
    assert full["market_state_sha256"] == SEALED_2026_03
    assert full["portfolio_side_materialized"] is False
    assert full["decision_layer_invoked"] is False
    # §19.4: the receipt binds BOTH floors, plus what the run did about their
    # relation. The corpus reaches deeper than L2's panel floor, so this parity
    # run is the `earlier` disposition: clipped, never quietly deepened.
    assert full["lineage_price_floor"] == AP.L2_PANEL_FLOOR
    assert full["observed_price_coverage_floor"] < AP.L2_PANEL_FLOOR
    assert full["floor_disposition"] == (
        "CLIP_TO_LINEAGE_FLOOR_NEW_LINEAGE_VERSION_REQUIRED")
    assert full["span_derivation_authority"]["ruling"] == "C-LF"


@sources
@heavy
def test_a_state_for_another_period_may_not_certify_this_receipt(
        run_dir, assembled):
    other = {**assembled,
             "period": {**assembled["period"], "decision_date": "2026-02-27"}}
    with pytest.raises(S.L3SnapshotError, match="is for decision date"):
        S.build_receipt(run_dir, RUN, DECISION, assembled=other)
