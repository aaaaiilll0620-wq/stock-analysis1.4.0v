"""B-19 invariant: no silent runtime/config override on any B0-reachable path.

The claim under test:

    No B0 production-reachable runtime/config path may silently override factor
    definition, data window, data semantics, feature enablement, or execution
    policy outside the frozen preregistration.

Legal overrides are not forbidden — unregistered ones are. Every override must
resolve to exactly one frozen prereg clause or config key; anything else aborts
rather than falling back to a default.
"""

import pytest

from core.b0_invariants import (
    B0_ENTRY_MODULES,
    B0_REGISTERED_OVERRIDES,
    OVERRIDE_MODULES,
    OVERRIDE_SYMBOLS,
    OverrideNotRegistered,
    assert_override_registered,
    find_import_time_foreign_mutations,
    find_violations,
)


# --- the invariant itself ----------------------------------------------------

def test_B19_no_override_source_reachable_from_B0():
    violations = find_violations(B0_ENTRY_MODULES, OVERRIDE_MODULES, OVERRIDE_SYMBOLS)
    assert not violations, f"B-19 violated: {violations}"


def test_B19_no_import_time_foreign_mutation_reachable_from_B0():
    """The bt_bundle.py:27 pattern must never be reachable from B0."""
    found = find_import_time_foreign_mutations(B0_ENTRY_MODULES)
    assert not found, f"B-19 import-time foreign mutation: {found}"


# --- negative controls: both detectors must fire on the real offenders -------

def test_B19_detector_catches_bt_bundle_override_module():
    violations = find_violations(("beat_0050.realbody.bt_bundle",),
                                 OVERRIDE_MODULES, OVERRIDE_SYMBOLS)
    assert violations, "detector is inert on the known override module"


def test_B19_detector_catches_import_time_mutation_in_bt_bundle():
    """bt_bundle mutates core.tej_bundle._PCT_HISTORY_START at module scope."""
    found = find_import_time_foreign_mutations(("beat_0050.realbody.bt_bundle",))
    assert any(attr.endswith("_PCT_HISTORY_START") for _mod, attr in found), found


@pytest.mark.parametrize("carrier", [
    "core.scoring_manager",     # RESEARCH_ARM + 4 feature flags
    "core.valuation",           # RESEARCH_ARM
    "core.fundamentals",        # RESEARCH_ARM + USE_ASSET_TURNOVER
    "core.data_provider",       # TEJ_RUNTIME_OVERLAY_DIR
    "core.tej_bundle",          # _PCT_HISTORY_START
])
def test_B19_known_override_carriers_are_flagged(carrier):
    """These are permitted to exist — they are not permitted to be B0-reachable."""
    assert find_violations((carrier,), OVERRIDE_MODULES, OVERRIDE_SYMBOLS)


# --- the fail-loud registry --------------------------------------------------

def test_B19_registry_starts_empty():
    """B0 currently authorises no runtime override at all."""
    assert B0_REGISTERED_OVERRIDES == {}


def test_B19_unregistered_override_aborts():
    with pytest.raises(OverrideNotRegistered, match="no frozen preregistration clause"):
        assert_override_registered("TEJ_RUNTIME_OVERLAY")


def test_B19_no_default_fallback_path():
    """'Not registered' must be a stop, never a silently-defaulted value."""
    for key in ("", "unknown", "RESEARCH_ARM", "--adv-floor"):
        with pytest.raises(OverrideNotRegistered):
            assert_override_registered(key)


def test_B19_registered_override_returns_its_clause(monkeypatch):
    monkeypatch.setitem(B0_REGISTERED_OVERRIDES, "EXAMPLE_KEY", "prereg §9.9")
    assert assert_override_registered("EXAMPLE_KEY") == "prereg §9.9"


def test_B19_registry_values_must_be_non_empty():
    """A registered-but-blank clause would be provenance theatre."""
    for key, clause in B0_REGISTERED_OVERRIDES.items():
        assert clause and clause.strip(), f"{key} registered with empty clause"
