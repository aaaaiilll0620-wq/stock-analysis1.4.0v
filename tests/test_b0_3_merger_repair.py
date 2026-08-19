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


def test_merger_handling_is_a_single_rule_not_a_table_of_events():
    """Every merger goes through one handler with no per-event branching."""
    import inspect
    src = inspect.getsource(ca.handle_merger)
    assert "_identity_change_unobservable" in src
    assert not re.search(r"\d{4}-\d{2}-\d{2}", src)


# --- R5 · unresolved remains unresolved ---------------------------------------

def test_nothing_was_made_reconstructible_without_evidence():
    s = json.load(open(SOURCES, encoding="utf-8"))
    assert s["events_newly_reconstructible"] == 0
    assert s["events_remaining_not_reconstructible"] == 220


def test_every_merger_in_the_ledger_is_still_not_reconstructible():
    rows = [r for r in csv.DictReader(open(LEDGER, encoding="utf-8"))
            if r["kind"] == "merger"]
    assert len(rows) == 220
    assert {r["reconstructibility"] for r in rows} == {"NOT_RECONSTRUCTIBLE"}


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

def test_frozen_merger_requirements_are_unchanged():
    assert ca.REQUIRED_FIELDS["merger"] == (
        "successor_security_id", "stock_ratio", "credit_tradable_date")
    assert "merger" in ca.IDENTITY_CHANGING_KINDS
    assert "merger" in ca.holder_affecting_kinds()


def test_exposure_semantics_are_untouched():
    from core.b0_state import HoldingSpell, PortfolioState

    sp = HoldingSpell("4123", "2014-08-01")
    st = PortfolioState(as_of="2014-11-28", cash=0.0, shares={"4123": 1044},
                        pending_exit={}, holding_spells=(sp,))
    assert sp.covers("2014-08-01") is False       # H.start < E, still exclusive
    assert sp.covers("2014-11-14") is True
    assert st.exposure_applies("4123", "2014-11-14", "2014-11-28") is True
    assert st.active_exposure_projection("2014-11-28") == (sp,)


def test_a_genuinely_exposed_unresolved_merger_still_aborts():
    """R10: fail-loud is preserved, not quietly relaxed by the repair."""
    from core.b0_state import HoldingSpell, PortfolioState

    ev = ca.CorporateActionEvent("4123", "merger", "2014-11-14",
                                 ca.NOT_RECONSTRUCTIBLE, "unit test")
    st = PortfolioState(as_of="2014-11-28", cash=0.0, shares={"4123": 1044},
                        pending_exit={},
                        holding_spells=(HoldingSpell("4123", "2014-08-01"),))
    hit = ca.exposed_unreconstructible_events([ev], st, as_of="2014-11-28")
    assert [e.stock_id for e in hit] == ["4123"]


def test_an_unexposed_unresolved_merger_does_not_abort():
    from core.b0_state import HoldingSpell, PortfolioState

    ev = ca.CorporateActionEvent("4123", "merger", "2014-11-14",
                                 ca.NOT_RECONSTRUCTIBLE, "unit test")
    st = PortfolioState(as_of="2014-11-28", cash=0.0, shares={"2330": 100},
                        pending_exit={},
                        holding_spells=(HoldingSpell("2330", "2014-08-01"),))
    assert ca.exposed_unreconstructible_events([ev], st, as_of="2014-11-28") == []


# --- R12 · the semantics question is registered, not decided ------------------

def test_the_semantics_question_is_an_open_m3_and_blocks_the_repair():
    assert "merger_holder_side_leg_semantics" in fin.open_keys()
    blocked = {i.key for i in fin.items_blocking("B0_3_data_repair")}
    assert "merger_holder_side_leg_semantics" in blocked
    with pytest.raises(fin.FinalizationBlocked):
        fin.assert_not_blocked("B0_3_data_repair")


def test_the_m3_names_the_share_conversion_blast_radius():
    """33 share_conversion events carry the identical frozen requirement."""
    a = _audit()
    assert a["share_conversion_same_signature"] == 33
    item = [i for i in fin.FINALIZATION_ITEMS
            if i.key == "merger_holder_side_leg_semantics"][0]
    assert "share_conversion" in item.measured
    assert len(item.options) >= 3
