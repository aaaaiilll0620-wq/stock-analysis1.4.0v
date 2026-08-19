# -*- coding: utf-8 -*-
"""B0.4 · holder-side reorganization coverage.

The B0.3 audit found 98 listed disappearing securities with no canonical event
at their boundary -- neither reconstructible nor unreconstructible, simply
absent. B0.4 makes every status-defined disappearance PRESENT and honestly
unresolved. It does not invent a conversion: what the source establishes is that
a listed security stopped trading and why, and that is all these events claim.
"""
from __future__ import annotations

import csv
import os
import re

import pytest

from core import b0_corporate_actions as ca
from core import b0_share_unit_adjustment as sua

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")
STATUS = os.path.join(REPO, "data", "b0", "security_status.csv")
EXIT_REASONS = ("合併下市", "併入控股公司下市")


def _ledger():
    return list(csv.DictReader(open(LEDGER, encoding="utf-8")))


def _exits():
    return [r for r in _ledger() if r["kind"] == "holder_side_reorganization_exit"]


def _state(sid, shares, as_of, start):
    from core.b0_state import HoldingSpell, PortfolioState
    return PortfolioState(as_of=as_of, cash=0.0, shares={sid: shares},
                          pending_exit={},
                          holding_spells=(HoldingSpell(sid, start),))


# --- coverage: every status-defined disappearance is materialized -------------

def test_every_status_defined_disappearance_has_a_canonical_event():
    """The coverage invariant the B0.3 audit falsified."""
    status = [r for r in csv.DictReader(open(STATUS, encoding="utf-8"))
              if r["status"] == "delisted" and r["reason"] in EXIT_REASONS]
    boundaries = {(r["stock_id"], r["effective_from"]) for r in status}
    events = {(r["stock_id"], r["ex_or_effective_date"]) for r in _exits()}
    assert boundaries, "no disappearance rows found in the status corpus"
    assert boundaries - events == set()
    assert len(status) == 158


def test_coverage_is_not_filtered_by_price_universe_window_or_holdings():
    """Scope is the corpus. The 98/90 counts are impact diagnostics only."""
    pd = pytest.importorskip("pandas")
    panel = pd.read_parquet(os.path.join(REPO, "data", "b0", "price_panel.parquet"),
                            columns=["stock_id"])
    in_universe = set(panel.stock_id.astype(str).unique())
    exits = _exits()
    assert len(exits) == 158
    outside = [r for r in exits if r["stock_id"] not in in_universe]
    assert outside, "expected some disappearances outside the price universe"
    assert len(outside) + len([r for r in exits
                               if r["stock_id"] in in_universe]) == 158
    outside_window = [r for r in exits
                      if not ("2014-07-31" <= r["ex_or_effective_date"] <= "2026-03-31")]
    assert outside_window, "expected some disappearances outside the window"


def test_events_carry_both_authoritative_reasons():
    reasons = {r["reason"] for r in _exits()}
    assert any("合併下市" in x for x in reasons)
    assert any("併入控股公司下市" in x for x in reasons)


# --- no invented conversion ---------------------------------------------------

def test_no_successor_ratio_cash_or_credit_is_asserted():
    for r in _exits():
        assert r["reconstructibility"] == "NOT_RECONSTRUCTIBLE"
        assert not str(r["credit_tradable_date"] or "").strip()
        assert not str(r["share_multiplier"] or "").strip()
        assert not str(r["cash_per_share"] or "").strip()
        assert not str(r["cash_payment_date"] or "").strip()


def test_the_event_can_never_reach_reconstructible():
    e = ca.classify("holder_side_reorganization_exit",
                    {"stock_id": "9001", "effective_date": "2020-01-06",
                     "status_reason": "合併下市"})
    assert e.reconstructibility == ca.NOT_RECONSTRUCTIBLE
    assert e.successor_security_id is None
    assert e.stock_ratio is None
    # even handed conversion-looking terms, this kind does not upgrade itself
    e2 = ca.classify("holder_side_reorganization_exit",
                     {"stock_id": "9001", "effective_date": "2020-01-06",
                      "status_reason": "合併下市", "successor_security_id": "9999",
                      "stock_ratio": 1, "credit_tradable_date": "2020-01-09"})
    assert e2.reconstructibility == ca.NOT_RECONSTRUCTIBLE


def test_it_is_not_represented_as_a_stock_to_stock_conversion():
    assert "holder_side_reorganization_exit" != "holder_side_security_conversion"
    e = ca.classify("holder_side_reorganization_exit",
                    {"stock_id": "9001", "effective_date": "2020-01-06",
                     "status_reason": "合併下市"})
    assert e.kind == "holder_side_reorganization_exit"


def test_the_boundary_is_not_copied_into_holder_economic_fields():
    e = ca.classify("holder_side_reorganization_exit",
                    {"stock_id": "9001", "effective_date": "2020-01-06",
                     "status_reason": "合併下市"})
    assert e.ex_or_effective_date == "2020-01-06"
    assert e.credit_tradable_date is None
    assert e.cash_payment_date is None
    assert e.diagnostics["boundary_kind"] == "holder_resolution_required_by_boundary"


def test_no_pairing_to_any_survivor_is_inferred():
    """The 399 issuer-side events and the 158 boundaries stay independent."""
    for r in _exits():
        assert not str(r.get("share_multiplier") or "").strip()
    e = ca.classify("holder_side_reorganization_exit",
                    {"stock_id": "9001", "effective_date": "2020-01-06",
                     "status_reason": "合併下市"})
    assert e.successor_security_id is None


# --- runtime: fail-loud, and BEFORE the price-gap path ------------------------

def test_held_at_the_boundary_raises_a_ca_reconstruction_block():
    ev = ca.classify("holder_side_reorganization_exit",
                     {"stock_id": "9001", "effective_date": "2020-01-06",
                      "status_reason": "合併下市"})
    st = _state("9001", 1000, as_of="2020-02-28", start="2019-06-03")
    hit = ca.exposed_unreconstructible_events([ev], st, as_of="2020-02-28")
    assert [e.stock_id for e in hit] == ["9001"]
    with pytest.raises(ca.CorporateActionReconstructionBlock):
        ca.transition_portfolio(st, [ev], as_of="2020-02-28",
                                sessions=("2020-01-06", "2020-02-28"),
                                period="2020-02")


def test_not_held_does_not_abort():
    ev = ca.classify("holder_side_reorganization_exit",
                     {"stock_id": "9001", "effective_date": "2020-01-06",
                      "status_reason": "合併下市"})
    st = _state("2330", 1000, as_of="2020-02-28", start="2019-06-03")
    assert ca.exposed_unreconstructible_events([ev], st, as_of="2020-02-28") == []
    r = ca.transition_portfolio(st, [ev], as_of="2020-02-28",
                                sessions=("2020-01-06", "2020-02-28"),
                                period="2020-02")
    assert dict(r.state.shares) == {"2330": 1000}


def test_the_ca_block_is_reached_before_the_unexplained_gap_path():
    """Ordering asserted structurally, not by reading line numbers.

    A held reorganization exit must stop the run as a corporate-action
    reconstruction block, not be reported as an unexplained price gap on a
    security whose disappearance the status corpus already explains.
    """
    import inspect

    from core import b0_route

    src = inspect.getsource(b0_route.run_decision)
    ca_at = src.index("assert_exposure_reconstructible")
    gap_at = src.index("assert_no_unexplained_gap_in_holdings")
    mark_at = src.index("mark_portfolio(")
    assert ca_at < gap_at < mark_at


def test_share_unit_treatment_is_identity_change_not_a_multiplier():
    assert sua.assert_kind_classified("holder_side_reorganization_exit") == \
        "identity_change"
    assert "holder_side_reorganization_exit" not in sua.ELIGIBLE_KINDS


# --- structural: no event-specific dispatch -----------------------------------

def test_no_security_or_date_specific_repair_dispatch():
    src = open(ca.__file__, encoding="utf-8").read()
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    assert "4123" not in code
    assert not re.search(r"stock_id\s*==\s*['\"]\d{4}", code)


def test_the_exit_handler_is_one_rule_for_all_reasons():
    import inspect
    src = inspect.getsource(ca.handle_holder_side_reorganization_exit)
    assert not re.search(r"\d{4}-\d{2}-\d{2}", src)
    # the reason is carried, never branched on
    assert "if reason ==" not in src
