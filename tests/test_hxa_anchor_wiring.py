# -*- coding: utf-8 -*-
"""The test that would have caught it: does the PRODUCTION path supply an anchor?

`tests/test_hxa_cash_forced_exit.py` covers HX-A/CASH with five tests and all
five passed while the rule could not fire in any real run. Every one of them
supplied its own `_anchor()`. A test that provides the dependency under test
proves the engine honours an anchor and says nothing about whether anybody hands
it one -- and nobody did. `transition_portfolio(hxa_anchor=None)` is the silent
default, so the B1 conformance diagnostic stopped at 66/141 on
`8913|holder_side_reorganization_exit|2020-01-14`: the single event the rule was
written to unblock, and the same wall B0.6 and B0.7 hit.

So these tests never construct an anchor. They ask the production code for one.
"""
import ast
import importlib.util
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(REPO, "research", "b0_l2", "run_sealed_l2.py")
DIAGNOSTIC = os.path.join(REPO, "research", "b1_conformance_diagnostic",
                          "run_b1_conformance.py")
PRODUCTION_CALLERS = (RUNNER, DIAGNOSTIC)

# Measured from data/b1/price_panel.parquet, and the same session
# test_hxa_cash_forced_exit.py:117 already asserts the engine records.
BLOCKER = ("8913", "2020-01-14")
EXPECTED_ANCHOR = (13.3, "2020-01-13")


def _load(path, name, lineage=None):
    if lineage is None:
        os.environ.pop("B0_MATERIALIZE_LINEAGE", None)
    else:
        os.environ["B0_MATERIALIZE_LINEAGE"] = lineage
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.environ.pop("B0_MATERIALIZE_LINEAGE", None)


# --- behavioural: the production factory really produces a working anchor ----

def test_the_production_factory_resolves_the_event_that_blocked_the_window():
    """Not a fixture, not a lambda -- the function the runner itself calls."""
    runner = _load(RUNNER, "_hxa_probe_b1", "B1")
    anchor = runner.hxa_anchor_for_run()
    assert anchor is not None, (
        "the sealed runner supplies no HX-A/CASH anchor, so the rule cannot "
        "fire and 8913 blocks the window at period 67")
    got = anchor(*BLOCKER)
    assert got is not None, "no anchor resolved for the one in-scope blocker"
    price, session = got
    assert (round(float(price), 4), session) == EXPECTED_ANCHOR


def test_frozen_b0_gets_no_anchor():
    """HX-A/CASH is B1's ruling. It was 'B1 only' in a comment and nowhere else.

    A scope that lives only in a comment is not a scope: the runner is shared,
    so without this branch a B0 invocation would apply another lineage's ruling
    to B0's window.
    """
    runner = _load(RUNNER, "_hxa_probe_b0")
    assert runner.LINEAGE == "FROZEN_B0"
    assert runner.hxa_anchor_for_run() is None


def test_the_anchor_declines_rather_than_guessing():
    """Both refusals return None so §6.1.12 fails closed exactly as before."""
    runner = _load(RUNNER, "_hxa_probe_refuse", "B1")
    anchor = runner.hxa_anchor_for_run()
    assert anchor("999999", "2020-01-14") is None          # no such security
    # Strictly before the boundary (R8): the boundary's own session and
    # anything after it are post-event data and may never price the exit.
    price, session = anchor(*BLOCKER)
    assert session < BLOCKER[1]
    first = anchor("8913", "1990-01-01")
    assert first is None, "nothing precedes the panel's first session"


# --- structural: every production call site passes it ------------------------

def _transition_calls(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name == "transition_portfolio":
            out.append(node)
    return out


@pytest.mark.parametrize("path", PRODUCTION_CALLERS,
                         ids=[os.path.basename(p) for p in PRODUCTION_CALLERS])
def test_every_production_transition_call_passes_an_anchor(path):
    """`hxa_anchor` defaults to None, so omitting it is silent. This is the
    check that turns that silence into a red test."""
    calls = _transition_calls(path)
    assert calls, "no transition_portfolio call found in %s" % path
    for call in calls:
        kwargs = {k.arg for k in call.keywords if k.arg}
        assert "hxa_anchor" in kwargs, (
            "%s:%d calls transition_portfolio without hxa_anchor. The parameter "
            "defaults to None and the rule then cannot fire -- which is exactly "
            "how HX-A/CASH shipped frozen, implemented, tested and inert."
            % (os.path.relpath(path, REPO), call.lineno))
