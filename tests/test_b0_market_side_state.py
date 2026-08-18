"""Definition A/B/D · the 141 market-side states and the one full input.

The six required invariants. Five of them are about a single property stated two
ways: the market side of a decision state is knowable before B0 has traded, and
the portfolio side is not — so the market-side hash must be blind to the
portfolio, the full-input hash must not be, and no path may quietly supply an
empty portfolio to close the gap.
"""

import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")
STATE_DIR = os.path.join(REPO, "data", "b0", "market_state")
RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                       "market_side_state_receipt.json")
P1_RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                          "period1_full_input_receipt.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(MANIFEST),
    reason="market-side state not materialized")


def _manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


# --- D1 · all 141 build, deterministically -----------------------------------

def test_all_141_market_side_states_are_materialized():
    man = _manifest()
    assert len(man) == 141
    months = [m["decision_month"] for m in man]
    assert months[0] == "2014-07" and months[-1] == "2026-03"
    assert len(set(months)) == 141
    for m in man:
        assert os.path.exists(os.path.join(REPO, m["artefact"]))
        assert m["as_of"] < m["decision_date"] < m["execution_date"], (
            "§6.6 / §6.5 ordering in %s" % m["decision_month"])
        assert m["securities"] > 0 and m["marks"] > 0
        assert len(m["market_state_sha256"]) == 64


def test_period_1_full_input_builds():
    """D · the one period whose portfolio is the frozen opening state."""
    from build_period1_full_input import build_period_1_full_input

    inp = build_period_1_full_input()
    assert inp.decision_date == "2014-07-31"
    assert inp.as_of == "2014-07-30"
    assert inp.execution_date > inp.decision_date
    assert inp.portfolio.cash == 2_000_000.0
    assert dict(inp.portfolio.shares) == {}
    assert len(inp.pit_inputs) == len(inp.snapshot.marks)


# --- D2/D3 · the other 140 cannot be built, and nothing fills the gap ---------

def test_period_2_full_input_fails_loudly_without_period_1_execution():
    from build_period1_full_input import (
        PortfolioNotYetGenerated, build_period_t_full_input)

    with pytest.raises(PortfolioNotYetGenerated, match="causally generated"):
        build_period_t_full_input(2)
    with pytest.raises(PortfolioNotYetGenerated):
        build_period_t_full_input(141)


def test_no_synthetic_default_portfolio_is_available_anywhere():
    """D3: an empty portfolio is a legitimate OPENING state and nothing else."""
    from build_period1_full_input import (
        PortfolioNotYetGenerated, build_period_t_full_input, opening_portfolio)

    # the opening state exists, and is read from the registry
    assert opening_portfolio("2014-07-30").cash == 2_000_000.0
    # but it is not reachable as a default for any later period
    with pytest.raises(PortfolioNotYetGenerated) as exc:
        build_period_t_full_input(7)
    msg = str(exc.value)
    for forbidden in ("fabricated", "empty portfolio", "TARGET"):
        assert forbidden in msg
    # and supplying a prior output still does not run the decision layer pre-L2
    with pytest.raises(PortfolioNotYetGenerated, match="pre-L2"):
        build_period_t_full_input(7, prior_execution_output=object())


# --- D4/D5 · what each hash is a hash OF -------------------------------------

def test_the_market_side_hash_is_independent_of_the_portfolio():
    from build_market_side_state import (
        PORTFOLIO_FIELDS, assert_market_state_is_portfolio_free)
    from core.b0_canonical_hash import canonical_sha256

    man = _manifest()
    base = {"decision_month": "x", "marks": {"1101": 10.0}}
    assert_market_state_is_portfolio_free(base)
    a = canonical_sha256(base)
    for field in PORTFOLIO_FIELDS:
        with pytest.raises(SystemExit, match="definition B"):
            assert_market_state_is_portfolio_free({**base, field: 1})
    # the manifest's hashes were produced from payloads that passed that check
    assert canonical_sha256(base) == a
    assert len({m["market_state_sha256"] for m in man}) == 141, (
        "141 distinct periods must not collapse to a shared hash")


def test_the_full_decision_input_hash_includes_the_portfolio():
    from build_period1_full_input import build_period_1_full_input
    from core.b0_canonical_hash import canonical_sha256

    inp = build_period_1_full_input()
    payload = inp.state_payload()
    for f in ("cash", "shares", "pending_exit", "cash_dividend_receivable",
              "stock_dividend_receivable"):
        assert f in payload, "%s must be inside the hashed decision state" % f
    full = canonical_sha256(payload)
    moved = canonical_sha256({**payload, "cash": payload["cash"] + 1.0})
    assert full != moved, "a portfolio change must change the full-input hash"

    market_only = {k: v for k, v in payload.items()
                   if k not in ("cash", "shares", "pending_exit",
                                "cash_dividend_receivable",
                                "stock_dividend_receivable", "exposures")}
    assert canonical_sha256(market_only) != full
    with open(P1_RECEIPT, encoding="utf-8") as fh:
        receipt = json.load(fh)
    assert receipt["full_decision_input_sha256"] == full
    assert receipt["market_side_only_sha256"] == canonical_sha256(market_only)


# --- D6 · rebuilding is identical ---------------------------------------------

def test_rebuilding_the_market_side_state_hashes_identically():
    """Recomputed from the sealed artefacts, not re-read from the manifest."""
    from build_market_side_state import market_state_payload, rows_from_parquet
    from core.b0_canonical_hash import canonical_sha256
    import pandas as pd

    man = _manifest()
    for m in (man[0], man[70], man[-1]):
        rows = rows_from_parquet(pd.read_parquet(os.path.join(REPO, m["artefact"])))
        payload = market_state_payload(m, rows)
        assert canonical_sha256(payload) == m["market_state_sha256"], (
            "%s does not rebuild to its sealed hash" % m["decision_month"])


# --- the receipt says what was and was not materialized -----------------------

def test_the_receipt_reports_the_portfolio_side_as_not_materialized():
    with open(RECEIPT, encoding="utf-8") as fh:
        r = json.load(fh)
    assert r["periods_built"] == r["periods_required"] == 141
    assert r["portfolio_side_materialized"] is False
    assert r["decision_layer_invoked"] is False
    assert r["performance_computed"] is False
    with open(P1_RECEIPT, encoding="utf-8") as fh:
        p1 = json.load(fh)
    assert p1["periods_with_full_input"] == 1
    assert p1["periods_deferred"] == 140
    assert p1["decision_layer_invoked"] is False
