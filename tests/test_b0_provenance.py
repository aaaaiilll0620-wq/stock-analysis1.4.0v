"""B-21 provenance / reproducibility tests.

Two claims under test:
  1. a sealed B0 run is uniquely bound to code, config, data, derived artifacts,
     initial state and as-of timestamps — every missing piece aborts;
  2. identical sealed inputs reproduce identical outputs, bit-exact.
"""

import dataclasses

import pytest

from core.b0_provenance import (
    FORBIDDEN_ENV,
    PROVENANCE_SECTIONS,
    SEALED_ENV_ALLOWLIST,
    CodeProvenance,
    ConfigProvenance,
    DatasetProvenance,
    DerivedArtifactProvenance,
    ExecutionProvenance,
    OutputProvenance,
    ProvenanceError,
    ProvenanceManifest,
    assert_no_unregistered_sources,
    SpecificationProvenance,
    seal,
    verify_replay,
)

CLEAN_ENV: dict[str, str] = {}


def _manifest(**over):
    m = ProvenanceManifest(
        specification=SpecificationProvenance(
            "docs/FrozenB0_MasterPreregistration.md", "s" * 64, "1.13"),
        code=CodeProvenance("a" * 40, False, None, "lock#1"),
        config=ConfigProvenance({"N_target": 20, "w_target": 0.05}, {}),
        data=(DatasetProvenance("price_valuation", "d1", "s1",
                                "2004-01-02", "2026-07-14", "tej_importer@1"),),
        derived=(DerivedArtifactProvenance("b_value_reference", "v1", ("d1",)),),
        execution=ExecutionProvenance("2026-03-31", "state#1",
                                      {"price_valuation": "2026-03-30"},
                                      "core.b0_route", "1.0.0"),
        output=OutputProvenance({"target_list": "o1", "nav": "o2"}),
    )
    return dataclasses.replace(m, **over) if over else m


# --- contract ----------------------------------------------------------------

def test_the_specification_section_is_required_and_bound(monkeypatch):
    """F0-R6: a sealed run names the specification it obeyed, directly."""
    m = _manifest()
    assert "specification" in m.sealed_input_sha256_payload_sections()
    other = dataclasses.replace(
        m, specification=SpecificationProvenance(
            "docs/FrozenB0_MasterPreregistration.md", "b" * 64, "1.13"))
    assert other.sealed_input_sha256 != m.sealed_input_sha256


def test_a_missing_spec_sha256_aborts():
    bad = SpecificationProvenance("docs/x.md", "", "1.13")
    with pytest.raises(ProvenanceError, match="spec_sha256"):
        seal(_manifest(specification=bad), final_seal=False, env=CLEAN_ENV)


def test_normative_module_hashes_are_required_for_a_final_seal(monkeypatch):
    """F0-R3: implementation identity is the commit SHA AND the module hashes."""
    import core.b0_declaration_conformance as conform
    import core.b0_frozen_spec as spec_mod

    monkeypatch.setattr(spec_mod, "BLOCKING_DATA_REQUIREMENTS", ())
    monkeypatch.setattr(conform, "DECLARATION_BINDINGS", ())
    with pytest.raises(ProvenanceError, match="normative module"):
        seal(_manifest(), final_seal=True, env=CLEAN_ENV)


def test_a_final_seal_passes_once_the_module_hashes_are_bound(monkeypatch):
    from core.b0_master_prereg import NORMATIVE_MODULES, normative_module_hashes

    import core.b0_frozen_spec as spec_mod

    monkeypatch.setattr(spec_mod, "BLOCKING_DATA_REQUIREMENTS", ())
    bound = CodeProvenance("a" * 40, False, None, "lock#1",
                           normative_module_hashes())
    digest = seal(_manifest(code=bound), final_seal=True, env=CLEAN_ENV)
    assert len(digest) == 64
    assert set(normative_module_hashes()) == set(NORMATIVE_MODULES)


def test_a_normative_module_hash_change_moves_the_sealed_input(monkeypatch):
    from core.b0_master_prereg import normative_module_hashes

    hashes = normative_module_hashes()
    a = _manifest(code=CodeProvenance("a" * 40, False, None, "lock#1", hashes))
    tampered = dict(hashes)
    tampered["core/b0_route.py"] = "0" * 64
    b = _manifest(code=CodeProvenance("a" * 40, False, None, "lock#1", tampered))
    assert a.sealed_input_sha256 != b.sealed_input_sha256


def test_seven_sections_declared():
    """F0-R6 added `specification`: a run is bound to its rules, not only its
    inputs. The count is asserted so that adding a section is a deliberate act."""
    assert PROVENANCE_SECTIONS == (
        "specification", "code", "config", "data", "derived", "execution",
        "output")


def test_clean_manifest_seals():
    # final_seal=False: V-1b blocks every final seal until the stock-dividend
    # source lands. That block is asserted in tests/test_b0_frozen_spec.py.
    assert len(seal(_manifest(), final_seal=False, env=CLEAN_ENV)) == 64


def test_sealed_inputs_exclude_outputs():
    """Changing only outputs must not change the sealed-input hash."""
    a = _manifest()
    b = _manifest(output=OutputProvenance({"target_list": "DIFFERENT", "nav": "o2"}))
    assert a.sealed_input_sha256 == b.sealed_input_sha256
    assert a.output_sha256 != b.output_sha256
    assert a.manifest_sha256 != b.manifest_sha256


@pytest.mark.parametrize("field_name,value", [
    ("code", CodeProvenance("", False, None, "lock#1")),
    ("config", ConfigProvenance({}, {})),
    ("execution", ExecutionProvenance("", "s", {"a": "b"}, "m", "v")),
    ("output", OutputProvenance({"x": ""})),
])
def test_incomplete_sections_abort(field_name, value):
    with pytest.raises(ProvenanceError):
        seal(_manifest(**{field_name: value}), final_seal=False, env=CLEAN_ENV)


@pytest.mark.parametrize("section", ["data", "derived"])
def test_empty_collection_sections_abort(section):
    with pytest.raises(ProvenanceError, match="missing sections"):
        seal(_manifest(**{section: ()}), final_seal=False, env=CLEAN_ENV)


# --- 1. code -----------------------------------------------------------------

def test_dirty_tree_fails_a_final_seal():
    dirty = CodeProvenance("a" * 40, True, "diff#1", "lock#1")
    with pytest.raises(ProvenanceError, match="dirty"):
        seal(_manifest(code=dirty), final_seal=True, env=CLEAN_ENV)


def test_dirty_tree_allowed_only_with_diff_hash_on_non_final_seal():
    with_diff = CodeProvenance("a" * 40, True, "diff#1", "lock#1")
    seal(_manifest(code=with_diff), final_seal=False, env=CLEAN_ENV)

    without = CodeProvenance("a" * 40, True, None, "lock#1")
    with pytest.raises(ProvenanceError, match="dirty_diff_sha256"):
        seal(_manifest(code=without), final_seal=False, env=CLEAN_ENV)


# --- 2. config ---------------------------------------------------------------

def test_empty_override_clause_is_provenance_theatre():
    cfg = ConfigProvenance({"N_target": 20}, {"SOME_KEY": "   "})
    with pytest.raises(ProvenanceError, match="theatre"):
        seal(_manifest(config=cfg), final_seal=False, env=CLEAN_ENV)


def test_config_hash_is_order_independent():
    a = ConfigProvenance({"a": 1, "b": 2}, {})
    b = ConfigProvenance({"b": 2, "a": 1}, {})
    assert a.config_sha256 == b.config_sha256


# --- 3 / 4. data + derived ---------------------------------------------------

@pytest.mark.parametrize("missing", ["content_sha256", "schema_sha256",
                                     "date_min", "date_max", "importer_version"])
def test_dataset_requires_every_identity_field(missing):
    kw = dict(name="d", content_sha256="c", schema_sha256="s",
              date_min="a", date_max="b", importer_version="i")
    kw[missing] = ""
    with pytest.raises(ProvenanceError):
        seal(_manifest(data=(DatasetProvenance(**kw),)), final_seal=False, env=CLEAN_ENV)


def test_derived_artifact_without_upstream_aborts():
    orphan = DerivedArtifactProvenance("b_value_reference", "v1", ())
    with pytest.raises(ProvenanceError, match="upstream"):
        seal(_manifest(derived=(orphan,)), final_seal=False, env=CLEAN_ENV)


# --- environment: the TEJ_RUNTIME_OVERLAY rule -------------------------------

def test_forbidden_env_is_declared():
    assert "TEJ_RUNTIME_OVERLAY" in FORBIDDEN_ENV


def test_unregistered_overlay_fails_rather_than_being_recorded():
    with pytest.raises(ProvenanceError, match="another"):
        seal(_manifest(), final_seal=False, env={"TEJ_RUNTIME_OVERLAY": "/tmp/overlay"})


def test_overlay_permitted_only_with_a_frozen_clause():
    cfg = ConfigProvenance({"N_target": 20}, {"TEJ_RUNTIME_OVERLAY": "prereg §12.3"})
    seal(_manifest(config=cfg), final_seal=False, env={"TEJ_RUNTIME_OVERLAY": "/tmp/overlay"})


def test_allowlisted_env_only_relocates_hashed_inputs():
    """These may differ per machine; dataset content is hashed independently."""
    assert set(SEALED_ENV_ALLOWLIST) == {"TEJ_CACHE", "MARKET_CACHE", "FINMIND_CACHE"}
    env = {v: "/somewhere/else" for v in SEALED_ENV_ALLOWLIST}
    seal(_manifest(), final_seal=False, env=env)


def test_assert_no_unregistered_sources_is_callable_standalone():
    assert_no_unregistered_sources({}, registered_overrides={})
    with pytest.raises(ProvenanceError):
        assert_no_unregistered_sources({"TEJ_RUNTIME_OVERLAY": "x"},
                                       registered_overrides={})


# --- deterministic replay invariant ------------------------------------------

def test_identical_run_replays():
    verify_replay(_manifest(), _manifest())


def test_same_inputs_different_outputs_abort():
    other = _manifest(output=OutputProvenance({"target_list": "DIFFERENT", "nav": "o2"}))
    with pytest.raises(ProvenanceError, match="no declared non-determinism"):
        verify_replay(_manifest(), other)


def test_replay_of_different_inputs_is_rejected_as_not_a_replay():
    other = _manifest(execution=ExecutionProvenance(
        "2026-03-31", "state#DIFFERENT", {"price_valuation": "2026-03-30"},
        "core.b0_route", "1.0.0"))
    with pytest.raises(ProvenanceError, match="not a replay"):
        verify_replay(_manifest(), other)


def test_declared_nondeterminism_is_per_artifact_not_global():
    a = dataclasses.replace(_manifest(), declared_nondeterminism=("nav",))
    b = dataclasses.replace(
        _manifest(output=OutputProvenance({"target_list": "o1", "nav": "DIFFERENT"})),
        declared_nondeterminism=("nav",))
    verify_replay(a, b)          # declared artifact may differ

    c = dataclasses.replace(
        _manifest(output=OutputProvenance({"target_list": "DIFFERENT", "nav": "o2"})),
        declared_nondeterminism=("nav",))
    with pytest.raises(ProvenanceError, match="target_list"):
        verify_replay(a, c)      # undeclared artifact may not


def test_no_global_tolerance_parameter_exists():
    """A tolerance knob would let a real difference hide inside rounding."""
    import inspect
    params = set(inspect.signature(verify_replay).parameters)
    assert params == {"original", "replay"}
    assert not any("tol" in p for p in params)
