"""B-17 invariant: no regime-dependent decision input is reachable from B0.

The claim under test is deliberately narrow. It is NOT "regime does not predict
anything" — that would be a research question, and B-17 is not re-opening one.
It is:

    No B0 production-reachable path in ranking / eligibility / weight / cost
    contains a regime-dependent alpha multiplier, threshold, or branch.

Regime as a reporting label or as ex-post attribution is permitted, provided it
never flows back into a decision. That distinction is what this test enforces:
it checks reachability from B0's declared entry points, not the existence of
regime code anywhere in the repository.
"""

import pytest

from core.b0_invariants import (
    B0_ENTRY_MODULES,
    LEGACY_COST_MODULES,
    LEGACY_COST_SYMBOLS,
    REGIME_DECISION_MODULES,
    REGIME_DECISION_SYMBOLS,
    find_violations,
    local_import_closure,
    referenced_names,
)


def test_b0_entry_points_declared():
    assert B0_ENTRY_MODULES, "B0_ENTRY_MODULES must not be empty"
    assert "core.b0_cost_model" in B0_ENTRY_MODULES


# --- B-17: the invariant itself ---------------------------------------------

def test_B17_no_regime_dependent_decision_reachable_from_B0():
    """When the B0 execution route is assembled and appended to
    B0_ENTRY_MODULES, this check applies to it automatically."""
    violations = find_violations(B0_ENTRY_MODULES,
                                 REGIME_DECISION_MODULES,
                                 REGIME_DECISION_SYMBOLS)
    assert not violations, f"B-17 violated: {violations}"


def test_B17_detector_is_not_inert():
    """Negative control: the guard must fire on a graph that really does carry
    a regime-dependent decision. core.advisor applies regime_multipliers to the
    composite weights and regime_rating_gates to the rating thresholds."""
    violations = find_violations(("core.advisor",),
                                 REGIME_DECISION_MODULES,
                                 REGIME_DECISION_SYMBOLS)
    assert violations, "detector is inert — it would not have caught a real violation"


@pytest.mark.parametrize("entry", ["core.advisor", "core.backtest"])
def test_B17_known_frozen_A_carriers_are_flagged(entry):
    """Both known Frozen-A carriers must be detectable. They are permitted to
    exist — they are simply not allowed to be reachable from B0."""
    assert find_violations((entry,), REGIME_DECISION_MODULES, REGIME_DECISION_SYMBOLS)


# --- G14-4 shares the same machinery ----------------------------------------

def test_G14_4_no_legacy_cost_path_reachable_from_B0():
    violations = find_violations(B0_ENTRY_MODULES,
                                 LEGACY_COST_MODULES,
                                 LEGACY_COST_SYMBOLS)
    assert not violations, f"G14-4 violated: {violations}"


def test_G14_4_detector_is_not_inert():
    violations = find_violations(("scripts.l4b_execution",),
                                 LEGACY_COST_MODULES,
                                 LEGACY_COST_SYMBOLS)
    assert violations, "detector is inert"


# --- machinery sanity --------------------------------------------------------

def test_string_literals_do_not_count_as_references():
    """The guard modules name what they forbid as string literals; that must not
    register as a reference, or every guard would flag itself."""
    src = 'FORBIDDEN = ("BUY_COST", "classify_regime")\nx = 1\n'
    assert not (referenced_names(src) & {"BUY_COST", "classify_regime"})


def test_closure_stays_inside_the_repo():
    for name, _src in local_import_closure(("core.b0_cost_model",)):
        assert not name.startswith(("pandas", "numpy", "duckdb")), name


def test_b0_invariants_module_does_not_trip_itself():
    """core.b0_invariants is itself project-local and will appear in closures."""
    assert not find_violations(("core.b0_invariants",),
                               REGIME_DECISION_MODULES, REGIME_DECISION_SYMBOLS)
    assert not find_violations(("core.b0_invariants",),
                               LEGACY_COST_MODULES, LEGACY_COST_SYMBOLS)
