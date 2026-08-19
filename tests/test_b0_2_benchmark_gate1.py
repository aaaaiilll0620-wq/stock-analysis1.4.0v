# -*- coding: utf-8 -*-
"""B0.2 · R5/R6/R8 — gate 1's inputs, and the M-3 that blocks them.

V-4 gate 1 is `net cumulative wealth > 0050 buy-and-hold`. Two independent
things are missing and both must stay fatal until separately closed:

  R6  the frozen master does not DETERMINE how that benchmark is constructed
  R8  no benchmark artefact exists or is bound into any seal

These tests exist because the failure mode they guard is silent: a replay that
does not check would run 141 periods and only then discover it has nothing to
compare against, at the exact moment reaching for an unsealed file is most
tempting.
"""
from __future__ import annotations

import pytest

from core import b0_benchmark_gate1 as gate1
from core import b0_finalization_items as fin
from core.b0_master_prereg import NORMATIVE_MODULES, specified_keys


# --- the M-3 is CLOSED, and the gates it held are released --------------------

def test_benchmark_semantics_is_closed():
    """Closed only after BOTH halves of R11: semantics frozen AND lineage
    materialized and seal-bindable.

    Scoped to THIS item. The register is a live mechanism and may legitimately
    hold other items later -- asserting it is empty would make an unrelated
    filing look like a benchmark regression.
    """
    assert gate1.GATE1_SEMANTICS_ITEM not in fin.open_keys()


def test_the_benchmark_item_no_longer_blocks_anything():
    """Again scoped to this item rather than to the register as a whole."""
    for stage in fin.BLOCKS:
        blockers = {i.key for i in fin.items_blocking(stage)}
        assert gate1.GATE1_SEMANTICS_ITEM not in blockers, stage
    # the B0.2 replay stage is specifically clear of the benchmark gap
    fin.assert_not_blocked("B0_2_retrospective_replay")


def test_the_blocking_mechanism_itself_was_not_retired(monkeypatch):
    """Negative control: the item went away, the gate did not."""
    item = fin.FinalizationItem(
        key="synthetic", question="q?", why_it_matters="w",
        measured="m", options=("a", "b"),
        blocks=("B0_2_retrospective_replay",), opened_by="test")
    monkeypatch.setattr(fin, "FINALIZATION_ITEMS", (item,))
    with pytest.raises(fin.FinalizationBlocked):
        fin.assert_not_blocked("B0_2_retrospective_replay")


def test_no_frozen_key_defines_benchmark_construction():
    """The construction protocol lives in 13.2/13.3 and its normative module,
    not as loose registry keys."""
    hits = [k for k in specified_keys()
            if any(t in k.lower() for t in ("benchmark", "0050", "notional"))]
    assert hits == []


# --- R8 · the pre-replay invariant --------------------------------------------

def test_gate1_module_is_normative():
    assert "core/b0_benchmark_gate1.py" in NORMATIVE_MODULES


def test_gate1_still_refuses_a_seal_that_binds_no_benchmark():
    """R10: the check is about THIS seal, not about the repo in general."""
    with pytest.raises(gate1.Gate1InputsNotSealed):
        gate1.assert_gate1_inputs_sealed({"datasets": [], "derived": []})


def test_gate1_passes_against_a_seal_that_binds_the_benchmark():
    """R10 · reproducible from seal-bound code + datasets, nothing discovered
    at runtime."""
    seal = {
        "derived": [{"name": gate1.BENCHMARK_PANEL}],
        "benchmark": {k: "bound" for k in gate1.GATE1_REQUIRED_BINDINGS},
    }
    status = gate1.assert_gate1_inputs_sealed(seal)
    assert status["gate1_reproducible_from_sealed_inputs"] is True


def test_gate1_refusal_still_names_the_reason_when_a_binding_is_dropped():
    seal = {
        "derived": [{"name": gate1.BENCHMARK_PANEL}],
        "benchmark": {k: "bound" for k in gate1.GATE1_REQUIRED_BINDINGS
                      if k != "benchmark_upstream_sha256"},
    }
    with pytest.raises(gate1.Gate1InputsNotSealed) as exc:
        gate1.assert_gate1_inputs_sealed(seal)
    assert "benchmark_upstream_sha256" in str(exc.value)


def test_gate1_status_is_measurable_without_asserting():
    import os

    status = gate1.gate1_input_status()
    panel = os.path.join(gate1.REPO_ROOT, gate1.BENCHMARK_PANEL)
    assert status["panel_present"] is os.path.exists(panel)
    assert status["semantics_ruled"] is True
    # no seal passed, so the bindings are all still unmeasured
    assert set(status["bindings_missing"]) == set(gate1.GATE1_REQUIRED_BINDINGS)


def test_the_real_b0_2_seal_satisfies_gate1():
    """Bound to the seal actually on disk, once it has been taken."""
    import json
    import os

    live = os.path.join(gate1.REPO_ROOT, "artifacts", "baseline_seal",
                        "b0_baseline_seal.json")
    if not os.path.exists(live):
        pytest.skip("no baseline seal in this working tree")
    seal = json.load(open(live, encoding="utf-8"))
    if "benchmark" not in seal:
        pytest.skip("seal predates the B0.2 benchmark bindings")
    gate1.assert_gate1_inputs_sealed(seal)


def test_a_seal_without_benchmark_rows_does_not_satisfy_gate1():
    seal = {"datasets": [{"name": "b0_price_universe_20260817"}],
            "derived": [{"name": "data/b0/price_panel.parquet"}]}
    status = gate1.gate1_input_status(seal)
    assert status["benchmark_rows_in_manifest"] == []
    with pytest.raises(gate1.Gate1InputsNotSealed):
        gate1.assert_gate1_inputs_sealed(seal)


def test_a_seal_that_names_a_benchmark_but_binds_nothing_still_fails():
    """Naming an artefact is not binding it. R8 wants reproducibility."""
    seal = {"derived": [{"name": "data/b0/benchmark_0050_panel.parquet"}]}
    status = gate1.gate1_input_status(seal)
    assert status["benchmark_rows_in_manifest"] != []
    assert status["bindings_missing"]
    with pytest.raises(gate1.Gate1InputsNotSealed):
        gate1.assert_gate1_inputs_sealed(seal)


def test_the_invariant_encodes_no_benchmark_semantics():
    """R6: this module must not be where a free parameter quietly lands.

    If someone later adds a date, a notional or a rounding rule here, that is a
    convention chosen by an implementer rather than ruled -- exactly what the
    open M-3 item exists to prevent.
    """
    src = open(gate1.__file__, encoding="utf-8").read()
    body = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    _, _, after_docstring = body.partition('"""')
    _, _, code = after_docstring.partition('"""')
    for forbidden in ("2014-07-31", "2014-08-01", "2000000", "2_000_000",
                      "0.001425", "0.003", "IMPACT_K", "floor("):
        assert forbidden not in code, (
            "%s appears in the gate-1 invariant; benchmark semantics are "
            "unruled and must not be chosen here" % forbidden)
