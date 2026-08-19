# -*- coding: utf-8 -*-
"""B0.6 · status PIT state sufficiency.

The canonical market-side state carried `known_status` but not the date that
status became knowable, so `PitPriceObservation` -- which refuses an undated
non-listed status under O-E-1 -- could not be constructed at all for a held
suspended or delisted name. B05DIAG-9943d2f7b4adb670 stopped at 46/141 on
exactly that. The date was never missing; it was sitting in the sealed status
corpus, unpropagated.

This repair supplies the date the frozen rule already required. It changes no
boundary, no classification and no markability rule.
"""
from __future__ import annotations

import csv
import json
import os
import re

import pytest

from core.b0_pit_observability import (
    EXPLAINED_SUSPENSION, NON_TRADING_STATUSES, PitPriceObservation,
    PriceObservabilityError, UNEXPLAINED_GAP, classify_price_gap,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(REPO, "research", "b0_6_status_pit",
                     "status_pit_population_audit.json")
STATUS = os.path.join(REPO, "data", "b0", "security_status.csv")

SESSIONS = ("2018-04-24", "2018-04-25", "2018-04-26", "2018-04-27")


# --- R1 · the dependency tuple is exactly what the frozen consumers read ------

def test_the_semantic_dependency_tuple_is_status_plus_available_from():
    a = json.load(open(AUDIT, encoding="utf-8"))
    assert a["dependency_tuple_required_by_frozen_consumers"] == [
        "known_status", "status_available_from"]
    assert a["effective_from_is_a_semantic_dependency"] is False


def test_no_frozen_rule_consults_effective_from():
    """R1: close declared dependencies, do not invent new status semantics."""
    src = open(os.path.join(REPO, "core", "b0_pit_observability.py"),
               encoding="utf-8").read()
    body = src.split("def classify_price_gap", 1)[1]
    assert "status_effective_from" not in body


# --- R5 · the six required cases ---------------------------------------------

def test_listed_status_with_a_complete_tuple_constructs():
    o = PitPriceObservation(as_of="2018-04-27", stock_id="X",
                            price_observed_through="2018-04-27",
                            expected_sessions=SESSIONS, known_status="listed")
    assert o.known_status == "listed"


def test_suspended_status_with_both_dates_constructs():
    o = PitPriceObservation(as_of="2018-04-27", stock_id="X",
                            price_observed_through="2018-04-26",
                            expected_sessions=SESSIONS,
                            known_status="suspended",
                            status_available_from="2018-04-26",
                            status_effective_from="2018-04-26")
    assert o.status_available_from == "2018-04-26"
    assert o.status_effective_from == "2018-04-26"


def test_a_non_listed_status_without_available_from_still_fails_loud():
    with pytest.raises(PriceObservabilityError):
        PitPriceObservation(as_of="2018-04-27", stock_id="X",
                            price_observed_through="2018-04-26",
                            expected_sessions=SESSIONS,
                            known_status="suspended")


def test_available_from_after_the_boundary_may_not_explain_the_earlier_gap():
    """O-E-1 unchanged: a status filed on the first missing session is too late."""
    o = PitPriceObservation(as_of="2018-04-27", stock_id="X",
                            price_observed_through="2018-04-25",
                            expected_sessions=SESSIONS,
                            known_status="suspended",
                            status_available_from="2018-04-26")
    assert classify_price_gap(o).classification == UNEXPLAINED_GAP


def test_available_from_satisfying_the_boundary_explains_it_exactly_as_before():
    o = PitPriceObservation(as_of="2018-04-27", stock_id="X",
                            price_observed_through="2018-04-25",
                            expected_sessions=SESSIONS,
                            known_status="suspended",
                            status_available_from="2018-04-25")
    v = classify_price_gap(o)
    assert v.classification == EXPLAINED_SUSPENSION
    assert v.stale_mark is True


def test_the_tuple_survives_state_to_build_input_to_observation():
    """R5: materialized state -> build_input -> PitPriceObservation, intact."""
    pd = pytest.importorskip("pandas")
    man = json.load(open(os.path.join(REPO, "data", "b0",
                                      "market_state_manifest.json"),
                         encoding="utf-8"))
    period = next((m for m in man if m["decision_month"] == "2018-04"), man[0])
    df = pd.read_parquet(period["artefact"])
    if "status_available_from" not in df.columns:
        pytest.skip("state not yet re-materialized in this working tree")
    nl = df[df.known_status != "listed"]
    if not len(nl):
        pytest.skip("no non-listed row in this period")
    row = nl.iloc[0]
    assert str(row.status_available_from).strip()
    o = PitPriceObservation(
        as_of=period["as_of"], stock_id=str(row.stock_id),
        price_observed_through=period["as_of"], expected_sessions=(period["as_of"],),
        known_status=str(row.known_status),
        status_available_from=str(row.status_available_from),
        status_effective_from=str(row.status_effective_from))
    assert o.status_available_from == str(row.status_available_from)


# --- R2 · the state is sufficient; no runtime side lookup --------------------

def test_the_runner_does_not_side_lookup_the_status_corpus():
    src = open(os.path.join(REPO, "research", "b0_l2", "run_sealed_l2.py"),
               encoding="utf-8").read()
    body = src.split("def build_input", 1)[1]
    code = chr(10).join(ln for ln in body.splitlines()
                        if not ln.strip().startswith("#"))
    assert "security_status" not in code
    assert "read_csv" not in code


# --- R3 · PIT semantics untouched --------------------------------------------

def test_the_status_taxonomy_and_boundary_are_unchanged():
    assert NON_TRADING_STATUSES == ("suspended", "delisted", "halted")
    src = open(os.path.join(REPO, "core", "b0_pit_observability.py"),
               encoding="utf-8").read()
    assert "_available_before(obs.status_available_from, first_missing)" in src


# --- R4 · corpus-wide, no special case ---------------------------------------

def test_no_security_or_date_specific_status_dispatch():
    for rel in (("research", "b0_materializer", "build_market_side_state.py"),
                ("core", "b0_pit_observability.py")):
        path = os.path.join(REPO, *rel)
        code = "\n".join(ln for ln in open(path, encoding="utf-8").read().splitlines()
                         if not ln.strip().startswith("#"))
        assert "2327" not in code, path
        assert not re.search(r"==\s*['\"]2018-04", code), path
        assert not re.search(r"stock_id\s*==\s*['\"]\d{4}", code), path


# --- R6 · the audit, and no invented dates -----------------------------------

def test_every_non_listed_observation_has_a_source_available_from():
    a = json.load(open(AUDIT, encoding="utf-8"))["window_141"]
    assert a["total_non_listed_observations"] == 421
    assert a["observations_with_source_available_from"] == 421
    assert a["observations_with_source_available_from_genuinely_missing"] == 0


def test_no_date_was_inferred_or_forward_filled():
    a = json.load(open(AUDIT, encoding="utf-8"))
    assert a["inferred_dates_created"] == 0
    rows = list(csv.DictReader(open(STATUS, encoding="utf-8")))
    assert len(rows) == 1375
    assert all(str(r["available_from"]).strip() for r in rows)


# --- R8 · diagnostic attribution, decision unchanged -------------------------

def test_the_exception_now_names_the_security_and_its_dates():
    with pytest.raises(PriceObservabilityError) as exc:
        PitPriceObservation(as_of="2018-04-27", stock_id="2327",
                            price_observed_through="2018-04-26",
                            expected_sessions=SESSIONS,
                            known_status="suspended",
                            status_effective_from="2018-04-27")
    msg = str(exc.value)
    for token in ("security_id='2327'", "status='suspended'",
                  "effective_from='2018-04-27'", "available_from=None",
                  "as_of='2018-04-27'"):
        assert token in msg, msg


def test_enrichment_changed_neither_the_decision_nor_the_exception_class():
    """Same invalid synthetic input, same class, same trigger condition."""
    bad = dict(as_of="2018-04-27", stock_id="X",
               price_observed_through="2018-04-26",
               expected_sessions=SESSIONS, known_status="suspended")
    with pytest.raises(PriceObservabilityError) as exc:
        PitPriceObservation(**bad)
    assert type(exc.value) is PriceObservabilityError
    # and the same input WITH the date is still accepted
    ok = PitPriceObservation(status_available_from="2018-04-26", **bad)
    assert ok.status_available_from == "2018-04-26"


def test_status_effective_from_never_changes_a_classification():
    base = dict(as_of="2018-04-27", stock_id="X",
                price_observed_through="2018-04-25",
                expected_sessions=SESSIONS, known_status="suspended",
                status_available_from="2018-04-25")
    a = classify_price_gap(PitPriceObservation(**base))
    b = classify_price_gap(PitPriceObservation(status_effective_from="1999-01-01",
                                               **base))
    assert (a.classification, a.stale_mark) == (b.classification, b.stale_mark)
