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


# --- R6 · the M-3 item is registered, and it blocks the right stages ----------

def test_benchmark_semantics_is_an_open_m3_item():
    assert gate1.GATE1_SEMANTICS_ITEM in fin.open_keys()


def test_benchmark_semantics_blocks_the_b0_2_replay_and_the_seal():
    item = fin.get(gate1.GATE1_SEMANTICS_ITEM) if hasattr(fin, "get") else None
    blocked = {i.key for i in fin.items_blocking("B0_2_retrospective_replay")}
    assert gate1.GATE1_SEMANTICS_ITEM in blocked
    blocked_seal = {i.key for i in fin.items_blocking("final_provenance_seal")}
    assert gate1.GATE1_SEMANTICS_ITEM in blocked_seal
    assert item is None or len(item.options) >= 2


def test_b0_2_replay_stage_is_mechanically_blocked():
    with pytest.raises(fin.FinalizationBlocked):
        fin.assert_not_blocked("B0_2_retrospective_replay")


def test_final_provenance_seal_is_mechanically_blocked():
    """R12: B0.2 cannot be sealed while gate 1's semantics are unruled."""
    with pytest.raises(fin.FinalizationBlocked):
        fin.assert_not_blocked("final_provenance_seal")


def test_l2_opening_is_not_collaterally_blocked():
    """The benchmark gap is a B0.2 concern; it must not re-block Frozen B0 L2."""
    fin.assert_not_blocked("L2_opening")


def test_no_frozen_key_defines_benchmark_construction():
    """The measured basis of the M-3 finding, asserted rather than recalled."""
    hits = [k for k in specified_keys()
            if any(t in k.lower() for t in ("benchmark", "0050", "notional"))]
    assert hits == []


# --- R8 · the pre-replay invariant --------------------------------------------

def test_gate1_module_is_normative():
    assert "core/b0_benchmark_gate1.py" in NORMATIVE_MODULES


def test_gate1_inputs_are_not_currently_sealed():
    with pytest.raises(gate1.Gate1InputsNotSealed):
        gate1.assert_gate1_inputs_sealed()


def test_gate1_refusal_names_both_independent_reasons():
    """Closing one of the two does not close the other, so both are reported."""
    with pytest.raises(gate1.Gate1InputsNotSealed) as exc:
        gate1.assert_gate1_inputs_sealed()
    msg = str(exc.value)
    assert gate1.GATE1_SEMANTICS_ITEM in msg
    assert gate1.BENCHMARK_PANEL in msg


def test_gate1_status_is_measurable_without_asserting():
    status = gate1.gate1_input_status()
    assert status["panel_present"] is False
    assert status["semantics_ruled"] is False
    assert status["gate1_reproducible_from_sealed_inputs"] is False
    assert set(status["bindings_missing"]) == set(gate1.GATE1_REQUIRED_BINDINGS)


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
