"""F-0 · what each of the three hashes is actually responsible for.

Opened because a `config_hash` was reported unchanged across v1.10 -> v1.11 while
O-F and O-G changed production-reachable behaviour. The reported number turned
out to have been captured before the registry keys were added (see
`research/f0_hash_boundary/`), but the question it raised is real and is what
these tests pin down:

    spec_sha256   the master preregistration DOCUMENT bytes
    config_hash   every key in the frozen spec registry, no subset
    state_hash    the canonical input state, listing spells included

The mutation controls run on an ISOLATED copy of the registry. Nothing here
edits the frozen master, and `run_decision` is never called — an input is built
and hashed, and that is all.
"""

import dataclasses

import pytest

from core import b0_listing_spell as ls
from core import b0_market_state as ms
from core.b0_listing_spell import ListingSpell
from core.b0_master_prereg import spec, specified_keys
from core.b0_provenance import ConfigProvenance
from core.b0_route import _hash, canonical_config, config_hash
from tests.test_b0_adapter_parity import (
    AS_OF, ATTESTATION, DECISION, EXEC_DAY, EXEC_PRICES, MARKS, NAMES, SESSIONS,
    ADV20, SIGMA, observations, pit_inputs, portfolio, spells,
)
from core.b0_route import CanonicalDecisionInput
from core.b0_state import MarketSnapshot


def an_input(**over) -> CanonicalDecisionInput:
    kw = dict(
        route_kind="production", decision_date=DECISION, as_of=AS_OF,
        snapshot=MarketSnapshot(as_of=AS_OF, attestation=ATTESTATION,
                                marks=MARKS, adv20=ADV20, sigma20d=SIGMA),
        portfolio=portfolio(), pit_inputs=pit_inputs(),
        price_observations=observations(), corporate_action_events=(),
        exposures=(), execution_date=EXEC_DAY, execution_prices=EXEC_PRICES,
        untradable=frozenset(), listing_spells=spells())
    kw.update(over)
    return CanonicalDecisionInput(**kw)


# --- F0-1 · the payload each hash is taken over -------------------------------

def test_config_hash_is_the_whole_registry_not_a_subset():
    assert set(canonical_config()) == set(specified_keys())
    assert config_hash() == _hash({k: spec(k) for k in specified_keys()})


def test_every_registry_key_is_load_bearing_for_config_hash():
    """Mutation control over ALL keys, on an isolated copy.

    This is the claim 'config_hash covers the entire registry', measured rather
    than read off the comprehension that builds it.
    """
    cfg = canonical_config()
    base = _hash(cfg)
    unmoved = []
    for key, value in cfg.items():
        mutated = dict(cfg)
        mutated[key] = _perturb(value)
        if _hash(mutated) == base:
            unmoved.append(key)
    assert unmoved == []


def _perturb(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "_F0"
    if isinstance(value, tuple):
        return value + ("F0",)
    if isinstance(value, dict):
        return {**value, "F0": True}
    if value is None:
        return "F0"
    return str(value) + "_F0"


def test_none_is_not_the_string_none_in_the_config_payload():
    """`spell_bridging_tolerance = None` is a ruling. A None that quietly became
    the string 'None' would hash differently but read the same in a report."""
    assert spec("spell_bridging_tolerance") is None
    assert spec("stale_mark_session_tolerance") is None
    assert _hash({"k": None}) != _hash({"k": "None"})


def test_true_is_not_one_in_the_config_payload():
    assert _hash({"k": True}) != _hash({"k": 1})


def test_key_order_cannot_leak_into_config_hash():
    cfg = canonical_config()
    reversed_order = {k: cfg[k] for k in reversed(list(cfg))}
    assert _hash(reversed_order) == _hash(cfg)


def test_the_two_config_serializers_agree_on_the_frozen_registry():
    """`b0_route._hash` and `b0_provenance._h` are different functions.

    They agree on the registry as frozen. They are NOT proved equivalent in
    general, and this test exists so that the day they disagree is a failure
    rather than two provenance records with two different config hashes.
    """
    cfg = canonical_config()
    assert ConfigProvenance(canonical=cfg,
                            registered_overrides={}).config_sha256 == config_hash()


# --- F0-3 · mutation controls, by category -----------------------------------

@pytest.mark.parametrize("key", [
    "N_target", "w_max", "X_buy", "share_rounding", "selection_tie_break",
    "commission_rate", "impact_k", "adv_floor_multiple",
])
def test_a_strategy_or_runtime_decision_key_moves_config_hash(key):
    cfg = canonical_config()
    mutated = dict(cfg)
    mutated[key] = _perturb(cfg[key])
    assert _hash(mutated) != _hash(cfg)


@pytest.mark.parametrize("key", [
    "unexplained_gap_abort_scope", "listing_spell_break_rule",
    "price_lookback_sessions", "spell_bridging_tolerance",
    "status_by_event_semantics", "o_e_1_availability_rule",
])
def test_a_production_reachable_state_semantic_key_moves_config_hash(key):
    """O-F / O-G declarations are in the registry, so they are in the hash.

    What this does NOT prove is that the declaration tracks the behaviour — see
    `test_the_o_f_o_g_declarations_that_are_derived_from_code`.
    """
    cfg = canonical_config()
    mutated = dict(cfg)
    mutated[key] = _perturb(cfg[key])
    assert _hash(mutated) != _hash(cfg)


@pytest.mark.parametrize("key", [
    "sharpe_metric_name", "l3_checkpoint_interval_months", "l2_outcomes",
    "window_months",
])
def test_a_reporting_only_key_also_moves_config_hash(key):
    """Reporting-only keys are NOT excluded from config_hash in this design.

    Recorded as a test rather than a comment because the natural assumption —
    'config_hash is the runtime subset' — is false here, and a reader who
    assumes it will mis-read every parity failure.
    """
    cfg = canonical_config()
    mutated = dict(cfg)
    mutated[key] = _perturb(cfg[key])
    assert _hash(mutated) != _hash(cfg)


def test_only_a_minority_of_registry_keys_are_read_at_runtime():
    """config_hash is a DECLARATION hash, not a runtime-parameter hash."""
    import ast

    from core.b0_invariants import B0_ENTRY_MODULES, local_import_closure

    read = set()
    for _name, src in local_import_closure(B0_ENTRY_MODULES):
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and getattr(
                    node.func, "id", getattr(node.func, "attr", None)) == "spec":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        read.add(arg.value)
    assert read, "no spec() lookups found at all — the scan is broken"
    assert read < set(specified_keys())


# --- the declaration / behaviour seam ----------------------------------------

def test_the_o_f_o_g_declarations_that_are_derived_from_code():
    """These keys READ their value from the module that implements the rule.

    Change the behaviour and the declaration moves with it, so config_hash moves
    too. This is the property the literal-valued declarations below do not have.
    """
    assert spec("status_event_semantics") == ms.EVENT_SEMANTICS
    assert dict(spec("status_by_event_semantics")) == ms.STATUS_BY_EVENT_SEMANTICS
    assert dict(spec("price_lookback_sessions")) == ls.PRICE_LOOKBACK_SESSIONS
    assert spec("spell_bridging_tolerance") is ls.SPELL_BRIDGING_SESSION_TOLERANCE
    assert spec("unknown_event_semantics_fails_closed") == (
        ms.STATUS_BY_EVENT_SEMANTICS[ms.UNKNOWN_EVENT_SEMANTICS] is None)
    assert spec("book_closure_may_explain_absence") == (
        ms.STATUS_BY_EVENT_SEMANTICS[ms.BOOK_CLOSURE] is not None)


LITERAL_DECLARATIONS = (
    "o_e_1_availability_rule",
    "unexplained_gap_abort_scope",
    "status_source_completeness_required",
    "listing_spell_break_rule",
    "price_lookback_reset_at_spell_start",
    "reappearance_may_explain_earlier_gap",
    "snapshot_delisting_fields_are_audit_only",
)


def test_the_literal_declarations_are_recorded_as_such():
    """A prose value in the registry cannot detect a change in the code it
    describes. They are enumerated so the gap is countable, not hidden."""
    for key in LITERAL_DECLARATIONS:
        assert isinstance(spec(key), (str, bool))
    assert set(LITERAL_DECLARATIONS) <= set(specified_keys())


# --- F0-4 · what state_hash is responsible for --------------------------------

def test_state_hash_moves_when_a_listing_spell_start_moves():
    """The O-G question, answered by measurement.

    If a spell boundary shifts, the state is not the same state, and B-20 must
    see that before it compares any output.
    """
    base = an_input()
    moved = an_input(listing_spells=tuple(
        dataclasses.replace(sp, start=SESSIONS[1]) for sp in spells()))
    assert base.state_hash() != moved.state_hash()


def test_state_hash_moves_when_a_spell_changes_how_it_was_opened():
    base = an_input()
    reopened = an_input(listing_spells=tuple(
        dataclasses.replace(sp, opened_by="reappearance") for sp in spells()))
    assert base.state_hash() != reopened.state_hash()


def test_state_hash_moves_when_a_spell_is_dropped_entirely():
    base = an_input()
    fewer = an_input(listing_spells=spells()[:-1])
    assert base.state_hash() != fewer.state_hash()


def test_declaring_no_spells_at_all_is_a_different_state():
    assert an_input().state_hash() != an_input(listing_spells=()).state_hash()


def test_spell_order_does_not_change_state_hash():
    """Two adapters must be free to build the same set in a different order."""
    a = an_input(listing_spells=spells())
    b = an_input(listing_spells=tuple(reversed(spells())))
    assert a.state_hash() == b.state_hash()


def test_config_hash_does_not_move_when_only_state_moves():
    """The division of labour, stated as a measurement rather than a comment."""
    before = config_hash()
    an_input(listing_spells=tuple(
        dataclasses.replace(sp, start=SESSIONS[1]) for sp in spells())).state_hash()
    assert config_hash() == before


def test_route_kind_is_excluded_from_state_hash():
    """Two routes supplying identical state must hash identically."""
    assert an_input(route_kind="production").state_hash() == \
        an_input(route_kind="retrospective").state_hash()


def test_as_of_config_and_state_answer_three_different_questions():
    """B-20 compares all three because no one of them subsumes another."""
    base = an_input()
    assert base.as_of == AS_OF                                   # when
    assert config_hash() == _hash(canonical_config())            # under what rules
    assert base.state_hash() != _hash(canonical_config())        # on what inputs


# --- F0-5 · what the B-21 manifest binds --------------------------------------

def test_the_provenance_manifest_binds_code_config_and_initial_state():
    from core.b0_provenance import ProvenanceManifest

    fields = set(ProvenanceManifest.__dataclass_fields__)
    assert {"code", "config", "data", "derived", "execution", "output"} <= fields


def test_the_provenance_manifest_has_no_spec_sha256_binding():
    """A sealed run does not name which master preregistration it obeyed.

    Recorded as a measurement rather than a docstring: the day a `spec_sha256`
    binding is added, this test is what tells the next reader that its absence
    was known and deliberate rather than never noticed.
    """
    from dataclasses import fields as dc_fields

    from core.b0_provenance import (
        CodeProvenance, ConfigProvenance, ExecutionProvenance, ProvenanceManifest,
    )

    assert "spec_sha256" not in ProvenanceManifest.__dataclass_fields__
    for section in (CodeProvenance, ConfigProvenance, ExecutionProvenance):
        assert "spec_sha256" not in {f.name for f in dc_fields(section)}


def test_the_l2_opening_registry_DOES_bind_spec_sha256():
    """The other registry binds it, which is what makes the manifest's silence
    a boundary question rather than a project-wide oversight."""
    from core.b0_master_prereg import L2Opening

    assert "spec_sha256" in L2Opening.__dataclass_fields__
    assert "code_commit" in L2Opening.__dataclass_fields__
    assert "data_manifest_sha256" in L2Opening.__dataclass_fields__


def test_spec_sha256_is_taken_over_the_document_bytes_only():
    import os

    from core.b0_master_prereg import MASTER_PREREG_DOC
    from core.b0_provenance import file_sha256

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doc = os.path.join(repo, MASTER_PREREG_DOC)
    assert file_sha256(doc) != config_hash()
    assert MASTER_PREREG_DOC.endswith(".md")
