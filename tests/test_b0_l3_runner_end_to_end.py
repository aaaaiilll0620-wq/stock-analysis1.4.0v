# -*- coding: utf-8 -*-
"""B7 end to end: a declared source set + a checkpoint -> one decision input.

This is the join the other two test files each check one half of. It runs the
runner's `build_period` over the SAME nine-leaf fixture
`tests/test_b0_l3_assemble.py` uses, opens from a real checkpoint file, and
stops one call short of the decision layer.

It stops there deliberately. `build_period` produces a `CanonicalDecisionInput`
and never calls `run_decision`, so this test proves the whole portfolio side --
opening, redate, transition, price observations, exposure, event delivery, the
`ProductionSources` join and both receipts -- without producing a prospective
observation. The first execution of the strategy route is gated separately in
`tests/test_b0_l3_runner.py` and is not reachable from here.

HEAVY. Opt in with B0_L3_PARITY=1: the fixture rebuilds nine leaves from
hundreds of megabytes of declared sources.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_l3_runner"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_bonus_shares_leaf as B                                # noqa: E402
import build_corporate_actions_leaf as CA                          # noqa: E402
import build_financials_leaf as FIN                                # noqa: E402
import build_flat_leaves as F                                      # noqa: E402
import build_prices_leaf as P                                      # noqa: E402
import build_valuation_leaf as V                                   # noqa: E402
import run_l3_prospective as R                                     # noqa: E402
import verify_assembly_parity as AP                                # noqa: E402
from core.b0_benchmark_construction import C_REF                   # noqa: E402
from core.b0_l3_lineage_capture import PURPOSE_DIAGNOSTIC          # noqa: E402
from core.b0_state import PortfolioState                           # noqa: E402
from research.b0_checkpoint import portfolio_side as ps            # noqa: E402
from source_ownership_manifest import (                            # noqa: E402
    assemble_aggregate, write_aggregate, write_leaf,
)

RUN, AS_OF, DECISION = "L3-00000000000000e2", "2026-03-30", "2026-03-31"
SEALED_2026_03 = "3a95d77e25fcd3ebd9c80fa461c27857c1dd22df8c41da20f50dfc42c9d81786"


def _spans():
    """Whichever span contract `l3_assemble` is on today.

    L2's own endpoints on the older contract; L2's price-span floor as the
    lineage floor on the §19 one. The sealed-hash comparison below is what
    decides whether the two agree -- it is not assumed here. If §19's derived
    `bonus_window` ever produces a different market state than L2's, that
    comparison is the thing that says so, and it is a finding about the
    derivation rather than a fixture to adjust.
    """
    contract = R.assembly_span_contract()
    if contract == R.CONTRACT_LINEAGE_FLOOR:
        return {"source": "test", "assembly_span_contract": contract,
                "lineage_price_floor": AP.L2_PRICE_SPAN[0]}
    return {"source": "explicit_caller_declaration",
            "assembly_span_contract": contract,
            "price_span": AP.L2_PRICE_SPAN,
            "bonus_window": AP.L2_BONUS_WINDOW}


def _span_argv():
    if R.assembly_span_contract() == R.CONTRACT_LINEAGE_FLOOR:
        return ["--lineage-price-floor", AP.L2_PRICE_SPAN[0]]
    return ["--price-span-from", AP.L2_PRICE_SPAN[0],
            "--price-span-to", AP.L2_PRICE_SPAN[1],
            "--bonus-window-from", AP.L2_BONUS_WINDOW[0],
            "--bonus-window-to", AP.L2_BONUS_WINDOW[1]]


heavy = pytest.mark.skipif(
    os.environ.get("B0_L3_PARITY") != "1",
    reason="set B0_L3_PARITY=1 (reads hundreds of MB and rebuilds a period)")
sources = pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO, P.LANDING_DIRECTORY)),
    reason="TEJ exports not present")


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    if os.environ.get("B0_L3_PARITY") != "1":
        pytest.skip("set B0_L3_PARITY=1")
    d = str(tmp_path_factory.mktemp("l3run"))
    for ds in sorted(F.FLAT_FAMILIES):
        write_leaf(d, F.build(ds, RUN, AS_OF))
    for mod in (FIN, P, B, V):
        write_leaf(d, mod.build(RUN, AS_OF))
    write_leaf(d, CA.build(RUN, AS_OF, run_dir=d))
    # §20 / C-70: this fixture reads sources to check something and stops one
    # call short of the decision layer, so it is UNSEALED_DIAGNOSTIC and binds
    # nothing. The pre-C-70 `route_seal_id="PENDING"` this replaced is the exact
    # placeholder `PLACEHOLDER_ROUTE_SEAL_IDS` exists to refuse.
    write_aggregate(d, assemble_aggregate(
        run_dir=d, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))
    return d


@pytest.fixture(scope="module")
def opening_checkpoint(tmp_path_factory):
    """A GENESIS opening: A1's independent cohort, written by the checkpoint module.

    `C_REF` comes from `core.b0_benchmark_construction`, not from a literal --
    the cohort is defined by the frozen constant, and a fixture that named its
    own number would pass `assert_genesis_cohort` by agreeing with itself.

    All-cash and spell-free is not a convenience here, it is what A1 IS. The
    held-security paths are covered against synthetic market rows in
    `tests/test_b0_portfolio_side.py`.
    """
    d = str(tmp_path_factory.mktemp("l3open"))
    # as_of is the PRECEDING period's, not this one's: a checkpoint is
    # portfolio[t-1] and the runner redates it. A fixture that pre-dated the
    # state to the period being decided would hide whether `redate` is called
    # at all.
    ps.append_checkpoint(d, run_id="L3-GENESIS", period="2026-02",
                         state=PortfolioState(as_of="2026-02-26",
                                              cash=C_REF, shares={}))
    return ps.checkpoint_file(d)


@heavy
@sources
def test_build_period_reproduces_the_sealed_market_state_and_builds_the_input(
        run_dir, opening_checkpoint):
    built = R.build_period(run_dir, RUN, DECISION, _spans(), opening_checkpoint,
                           opening_kind=ps.OPENING_GENESIS, c_ref=C_REF,
                           expect_opening_period="2026-02", expect_opening_seq=1,
                           synthetic_sources=True)

    # the market half is byte-identical to L2's sealed state for the period
    assert built["assembled"]["market_state_sha256"] == SEALED_2026_03
    # and the portfolio half reached the input without the decision layer
    assert built["decision_layer_invoked"] is False
    inp = built["decision_input"]
    assert inp.as_of == built["as_of"]
    # the opening state was carried FORWARD, not read as already standing here
    assert built["opening_state"].as_of == "2026-02-26"
    assert built["redated"].as_of == built["as_of"]
    assert inp.portfolio.as_of == built["as_of"]
    assert inp.route_kind


@heavy
@sources
def test_the_portfolio_half_is_the_half_the_market_side_left_empty(
        run_dir, opening_checkpoint):
    built = R.build_period(run_dir, RUN, DECISION, _spans(), opening_checkpoint,
                           opening_kind=ps.OPENING_GENESIS, c_ref=C_REF,
                           synthetic_sources=True)

    side = built["side"]
    # an all-cash opening holds nothing, so both fields are legitimately empty --
    # what matters is that they came from the PORTFOLIO side and that the market
    # side did not fill them.
    assert side.price_observations == tuple(
        o for o in built["sources"].price_observations)
    assert side.corporate_action_events == tuple(
        built["sources"].corporate_action_events)
    assert side.exposures == tuple(built["sources"].exposures)
    assert len(side.price_observations) == len(built["opening_state"].shares)

    payload = built["portfolio_side_payload"]
    for field in ps.MARKET_FIELDS:
        assert field not in payload


@heavy
@sources
def test_the_event_universe_comes_from_the_declared_sources_not_from_data_b0(
        run_dir):
    """L2's sealed ledger stops where L2's window stops; an L3 period may not use it."""
    from l3_readers import read_calendar

    sessions = tuple(read_calendar(run_dir))
    events = ps.load_events(run_dir, bonus_window=AP.L2_BONUS_WINDOW,
                            sessions=sessions)

    assert events, "the declared source set produced no holder-affecting events"
    kinds = {e.kind for evs in events.values() for e in evs}
    from core import b0_corporate_actions as ca

    assert kinds <= set(ca.holder_affecting_kinds())


@heavy
@sources
def test_assemble_mode_writes_both_receipts_and_never_a_checkpoint(
        run_dir, opening_checkpoint):
    """`assemble` ends with ASSEMBLED_DECISION_LAYER_NOT_INVOKED and no new state."""
    rc = R.main([
        "--mode", "assemble", "--run-id", RUN, "--run-dir", run_dir,
        "--decision-date", DECISION, "--authorization", "test-fixture",
        "--opening-checkpoint", opening_checkpoint,
        "--opening-kind", ps.OPENING_GENESIS, "--c-ref", str(C_REF),
        "--synthetic-sources"] + _span_argv())
    assert rc == 0

    with open(os.path.join(run_dir, R.FINAL_RESULT), encoding="utf-8") as fh:
        final = json.load(fh)
    assert final["terminal_status"] == "ASSEMBLED_DECISION_LAYER_NOT_INVOKED"
    assert final["decision_layer_invoked"] is False
    assert final["performance_computed"] is False
    assert final["closure_transaction"]["in_transaction"] in (True, False)

    with open(os.path.join(run_dir, R.PORTFOLIO_RECEIPT), encoding="utf-8") as fh:
        receipt = json.load(fh)
    assert receipt["market_state_sha256"] == SEALED_2026_03
    assert len(receipt["portfolio_side_sha256"]) == 64
    # the opening is recorded as what it was, with both identities and the
    # cohort it was verified against
    opening = receipt["opening"]
    assert opening["opening_kind"] == ps.OPENING_GENESIS
    assert opening["genesis_cohort"]["c_ref"] == C_REF
    assert len(opening["checkpoint_sha256"]) == 64
    assert len(opening["handoff_sha256"]) == 64
    assert len(opening["checkpoint_file_sha256"]) == 64
    assert opening["producer_run_id"] == "L3-GENESIS"
    assert os.path.exists(os.path.join(run_dir, R.OPENING_RECORD))
    # no portfolio[t+1] was produced, because no decision was made
    assert not os.path.exists(ps.checkpoint_file(run_dir))
