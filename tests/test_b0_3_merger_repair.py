# -*- coding: utf-8 -*-
"""B0.3 · R6/R10 — the merger repair is defect-defined, and stays that way.

The repair itself made no event RECONSTRUCTIBLE, because no authoritative source
supplies the frozen holder-side fields. These tests pin the properties that must
hold whether or not a future acquisition changes that: selection is by defect
signature and never by holdings, no event-specific dispatch is permitted, and an
event without sufficient evidence stays unresolved.
"""
from __future__ import annotations

import csv
import json
import os
import re

import pytest

from core import b0_corporate_actions as ca
from core import b0_finalization_items as fin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(REPO, "research", "b0_3_merger_repair",
                     "merger_defect_audit.json")
SOURCES = os.path.join(REPO, "research", "b0_3_merger_repair",
                       "merger_source_availability.json")
LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")


def _audit():
    return json.load(open(AUDIT, encoding="utf-8"))


# --- R2 · defect-defined selection --------------------------------------------

def test_selection_is_by_defect_signature_over_the_whole_corpus():
    a = _audit()
    assert a["merger_events_total"] == a["merger_events_matching_defect_signature"]
    assert a["merger_events_outside_defect_signature"] == 0
    assert a["distinct_securities"] == 186


def test_audit_scope_is_not_restricted_to_the_window_or_to_holdings():
    """R2 forbids scoping to what B0 encountered or to the pre-abort period."""
    a = _audit()
    assert a["within_141_window"] < a["merger_events_matching_defect_signature"]
    assert a["date_span"][0] < "2014-07-31"          # reaches before the window
    assert a["date_span"][1] > "2014-11-14"          # and past the abort
    assert "holding" in a["selection"] or "holding" in a["selection"].lower()


def test_no_in_scope_event_carries_any_frozen_holder_side_field():
    a = _audit()
    assert list(a["in_scope_field_presence"]) == ["<none>"]
    assert a["in_scope_field_presence"]["<none>"] == 220


# --- R6 · 4123 is regression evidence, never a special case -------------------

def test_both_4123_events_are_handled_by_the_corpus_wide_rule():
    a = _audit()
    for k in ("4123_2014-11-14", "4123_2022-06-30"):
        ev = a["reference_events"][k]
        assert ev is not None
        assert ev["reconstructibility"] == "NOT_RECONSTRUCTIBLE"
        assert ev["reason"] == a["defect_reason_verbatim"]


def test_no_event_specific_repair_dispatch_exists_in_the_ca_core():
    """R6 structural guard: no security id, date or event id may steer the
    classifier. A repair that needs a special case is not a repair."""
    src = open(ca.__file__, encoding="utf-8").read()
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    assert "4123" not in code
    for pat in (r'"\d{4}-\d{2}-\d{2}"\s*(?:==|!=)', r"stock_id\s*==\s*['\"]\d{4}"):
        assert not re.search(pat, code), pat


def test_issuer_side_handling_is_a_single_rule_not_a_table_of_events():
    """Every tr_fg1 row goes through one handler with no per-event branching."""
    import inspect
    src = inspect.getsource(ca.handle_issuer_side_merger_share_issuance)
    assert "_issuer_side_share_issuance" in src
    assert not re.search(r"\d{4}-\d{2}-\d{2}", src)
    assert "4123" not in src


# --- R5 · unresolved remains unresolved ---------------------------------------

def test_nothing_was_made_reconstructible_without_evidence():
    """The B0.3 audit found no acquirable data; the repair was semantic."""
    s = json.load(open(SOURCES, encoding="utf-8"))
    assert s["events_newly_reconstructible"] == 0


def test_every_tr_fg1_row_is_now_issuer_side_not_applicable():
    """B0.3: the 220 rows were reclassified by SOURCE FIELD, not by kind name."""
    rows = [r for r in csv.DictReader(open(LEDGER, encoding="utf-8"))
            if r["source_field"] == "合併(仟股)"]
    assert len(rows) == 220
    assert {r["kind"] for r in rows} == {"issuer_side_merger_share_issuance"}
    assert {r["reconstructibility"] for r in rows} == {"NOT_APPLICABLE"}


def test_every_con3_row_is_now_issuer_side_not_applicable():
    rows = [r for r in csv.DictReader(open(LEDGER, encoding="utf-8"))
            if r["source_field"] == "股份轉換(仟股"]
    assert len(rows) == 33
    assert {r["kind"] for r in rows} == {"issuer_side_share_conversion_issuance"}
    assert {r["reconstructibility"] for r in rows} == {"NOT_APPLICABLE"}


def test_no_holder_side_conversion_row_was_synthesised():
    """R6/R7: none may be invented without authoritative counterparty terms."""
    rows = [r for r in csv.DictReader(open(LEDGER, encoding="utf-8"))
            if r["kind"] == "holder_side_security_conversion"]
    assert rows == []


def test_no_third_party_source_determines_holder_economics():
    s = json.load(open(SOURCES, encoding="utf-8"))
    third = [x for x in s["sources_examined"] if x.get("priority") == "excluded"]
    assert third and "comparator" in third[0]["note"]


def test_inference_routes_are_explicitly_refused():
    s = json.load(open(SOURCES, encoding="utf-8"))
    for forbidden in ("post-event prices", "share-count changes",
                      "NAV continuity", "strategy results"):
        assert forbidden in s["inference_sources_refused"]


def test_source_selection_declares_independence_from_outcomes():
    s = json.load(open(SOURCES, encoding="utf-8"))
    for k in ("B0 holdings", "NAV", "whether an event blocks replay",
              "subsequent strategy performance"):
        assert k in s["selection_independent_of"]


# --- R7 · B0.2 CA semantics untouched -----------------------------------------

def test_the_holder_side_leg_keeps_the_frozen_requirements():
    """R3: the requirements did not relax, they moved to the leg that owns them."""
    assert ca.REQUIRED_FIELDS["holder_side_security_conversion"] == (
        "successor_security_id", "stock_ratio", "credit_tradable_date")
    # B0.4 added holder_side_reorganization_exit alongside it; both are
    # holder-side identity changes, and neither is an issuer-side row.
    assert "holder_side_security_conversion" in ca.IDENTITY_CHANGING_KINDS
    assert "holder_side_security_conversion" in ca.holder_affecting_kinds()


def test_issuer_side_issuance_is_not_holder_affecting():
    """R2: this is the whole repair."""
    for k in ("issuer_side_merger_share_issuance",
              "issuer_side_share_conversion_issuance"):
        assert k not in ca.holder_affecting_kinds()
        assert k not in ca.IDENTITY_CHANGING_KINDS


def test_exposure_semantics_are_untouched():
    from core.b0_state import HoldingSpell, PortfolioState

    sp = HoldingSpell("4123", "2014-08-01")
    st = PortfolioState(as_of="2014-11-28", cash=0.0, shares={"4123": 1044},
                        pending_exit={}, holding_spells=(sp,))
    assert sp.covers("2014-08-01") is False       # H.start < E, still exclusive
    assert sp.covers("2014-11-14") is True
    assert st.exposure_applies("4123", "2014-11-14", "2014-11-28") is True
    assert st.active_exposure_projection("2014-11-28") == (sp,)


def test_a_genuinely_exposed_unresolved_conversion_still_aborts():
    """R9/R10: fail-loud is preserved, not quietly relaxed by the repair."""
    from core.b0_state import HoldingSpell, PortfolioState

    ev = ca.CorporateActionEvent("4123", "holder_side_security_conversion",
                                 "2014-11-14", ca.NOT_RECONSTRUCTIBLE, "unit test")
    st = PortfolioState(as_of="2014-11-28", cash=0.0, shares={"4123": 1044},
                        pending_exit={},
                        holding_spells=(HoldingSpell("4123", "2014-08-01"),))
    hit = ca.exposed_unreconstructible_events([ev], st, as_of="2014-11-28")
    assert [e.stock_id for e in hit] == ["4123"]


def test_an_unexposed_unresolved_conversion_does_not_abort():
    from core.b0_state import HoldingSpell, PortfolioState

    ev = ca.CorporateActionEvent("4123", "holder_side_security_conversion",
                                 "2014-11-14", ca.NOT_RECONSTRUCTIBLE, "unit test")
    st = PortfolioState(as_of="2014-11-28", cash=0.0, shares={"2330": 100},
                        pending_exit={},
                        holding_spells=(HoldingSpell("2330", "2014-08-01"),))
    assert ca.exposed_unreconstructible_events([ev], st, as_of="2014-11-28") == []


# --- R12 · the semantics question is registered, not decided ------------------

def test_the_semantics_question_was_ruled_and_the_repair_is_unblocked():
    """It was filed rather than taken, then ruled, then implemented."""
    assert "merger_holder_side_leg_semantics" not in fin.open_keys()
    fin.assert_not_blocked("B0_3_data_repair")
    src = open(fin.__file__, encoding="utf-8").read()
    assert "merger_holder_side_leg_semantics -> M-3 ruling" in src


def test_the_ruling_reached_the_share_conversion_population_too():
    """The 33 con3 events were re-audited from source lineage, not by name."""
    a = _audit()
    assert a["share_conversion_same_signature"] == 33
    rows = [r for r in csv.DictReader(open(LEDGER, encoding="utf-8"))
            if r["source_field"] == "股份轉換(仟股"]
    assert len(rows) == 33


# --- R8 · survivor holdings regression (must not mention any security id) -----

def _state(sid, shares, as_of="2020-02-28", start="2020-01-02"):
    from core.b0_state import HoldingSpell, PortfolioState
    return PortfolioState(as_of=as_of, cash=0.0, shares={sid: shares},
                          pending_exit={},
                          holding_spells=(HoldingSpell(sid, start),))


def test_r8_holding_the_survivor_is_untouched_by_its_own_merger_issuance():
    """B0 holds S; tr_fg1 says S issued shares because D merged into S.
    Expected: shares unchanged, no claim, no conversion, no abort."""
    survivor = "S0001"
    ev = ca.classify("issuer_side_merger_share_issuance",
                     {"stock_id": survivor, "effective_date": "2020-01-06"})
    assert ev.reconstructibility == ca.NOT_APPLICABLE

    st = _state(survivor, 1000)
    # not holder-affecting, so it is not even in the engine's event population
    assert "issuer_side_merger_share_issuance" not in ca.holder_affecting_kinds()
    # and it can never raise an exposure abort
    assert ca.exposed_unreconstructible_events([ev], st, as_of="2020-02-28") == []

    result = ca.transition_portfolio(st, [ev], as_of="2020-02-28",
                                     sessions=("2020-01-06", "2020-02-28"),
                                     period="2020-02")
    assert dict(result.state.shares) == {survivor: 1000}
    assert result.state.security_receivables == ()
    assert result.state.cash_receivables == ()
    assert result.state.stock_dividend_receivable == {}


def test_r8_same_for_issuer_side_share_conversion_issuance():
    issuer = "S0002"
    ev = ca.classify("issuer_side_share_conversion_issuance",
                     {"stock_id": issuer, "effective_date": "2020-01-06"})
    assert ev.reconstructibility == ca.NOT_APPLICABLE
    st = _state(issuer, 500)
    result = ca.transition_portfolio(st, [ev], as_of="2020-02-28",
                                     sessions=("2020-01-06", "2020-02-28"),
                                     period="2020-02")
    assert dict(result.state.shares) == {issuer: 500}


# --- R9 · disappearing holder regression --------------------------------------

def test_r9_disappearing_holder_with_authoritative_terms_converts_once():
    from fractions import Fraction
    disappearing, successor = "D0001", "S0003"
    ev = ca.classify("holder_side_security_conversion", {
        "stock_id": disappearing, "effective_date": "2020-01-06",
        "successor_security_id": successor, "stock_ratio": Fraction(1, 2),
        "credit_tradable_date": "2020-01-09"})
    assert ev.reconstructibility == ca.RECONSTRUCTIBLE

    st = _state(disappearing, 1000)
    result = ca.transition_portfolio(
        st, [ev], as_of="2020-02-28",
        sessions=("2020-01-06", "2020-01-09", "2020-02-28"), period="2020-02")
    assert dict(result.state.shares).get(disappearing, 0) == 0
    assert result.state.applied_ca_event_ids
    # applying the same event again is refused, so the conversion is once-only
    before = dict(result.state.shares)
    again = ca.transition_portfolio(
        result.state, [ev], as_of="2020-02-28",
        sessions=("2020-01-06", "2020-01-09", "2020-02-28"), period="2020-02")
    assert dict(again.state.shares) == before


def test_r9_disappearing_holder_without_terms_stays_unresolved_and_aborts():
    disappearing = "D0002"
    ev = ca.classify("holder_side_security_conversion",
                     {"stock_id": disappearing, "effective_date": "2020-01-06"})
    assert ev.reconstructibility == ca.NOT_RECONSTRUCTIBLE
    st = _state(disappearing, 1000)
    hit = ca.exposed_unreconstructible_events([ev], st, as_of="2020-02-28")
    assert [e.stock_id for e in hit] == [disappearing]
    with pytest.raises(ca.CorporateActionReconstructionBlock):
        ca.transition_portfolio(st, [ev], as_of="2020-02-28",
                                sessions=("2020-01-06", "2020-02-28"),
                                period="2020-02")


# --- R10 · dilution economics are not synthesised ------------------------------

def test_r10_no_synthetic_dilution_adjustment_is_created():
    """Reclassifying issuer-side issuance must not invent a portfolio haircut."""
    from core import b0_share_unit_adjustment as sua
    for k in ("issuer_side_merger_share_issuance",
              "issuer_side_share_conversion_issuance"):
        assert sua.assert_kind_classified(k) == "ineligible"
        assert k not in sua.ELIGIBLE_KINDS
    assert sua.assert_kind_classified("holder_side_security_conversion") == \
        "identity_change"


def test_r4_reclassification_is_keyed_on_source_field_not_kind_name():
    """The ledger carries provenance so a future audit need not trust the name."""
    rows = list(csv.DictReader(open(LEDGER, encoding="utf-8")))
    assert "source_field" in rows[0]
    by_field = {r["source_field"] for r in rows
                if r["kind"] == "issuer_side_merger_share_issuance"}
    assert by_field == {"合併(仟股)"}
