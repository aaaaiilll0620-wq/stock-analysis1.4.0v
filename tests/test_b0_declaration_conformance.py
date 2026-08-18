"""F0-R1 / F0-R4 / F0-R7 · the declaration/behaviour binding, tested both ways.

`verify_declaration_bindings()` passing is necessary and not interesting on its
own — a check that never fails proves nothing. So every test here that asserts
conformance has a sibling that BREAKS the behaviour on an isolated copy and
requires the check to catch it.
"""

import pytest

from core.b0_canonical_hash import (
    CANONICAL_HASH_VERSION, canonical_json, canonical_sha256, canonicalise,
)
from core.b0_declaration_conformance import (
    BEHAVIORAL_CONFORMANCE,
    DECLARATION_BINDINGS,
    IMPLEMENTATION_DERIVED,
    PRODUCTION_REACHABLE_DECLARATIONS,
    DeclarationBinding,
    DeclarationConformanceError,
    assert_declarations_conform,
    summary,
    verify_declaration_bindings,
)
from core.b0_master_prereg import spec, specified_keys


# --- F0-R1 · what config_hash covers ------------------------------------------

def test_config_hash_scope_is_the_complete_declaration_registry():
    assert spec("config_hash_scope") == \
        "complete_machine_readable_declaration_registry"
    assert spec("config_hash_is_runtime_subset") is False


def test_every_bound_declaration_is_in_the_registry():
    """A declaration outside the registry is one config_hash does not cover."""
    assert set(PRODUCTION_REACHABLE_DECLARATIONS) <= set(specified_keys())


def test_state_hash_is_not_an_implementation_hash():
    assert spec("state_hash_scope") == "canonical_concrete_input_state_identity"
    assert spec("state_hash_is_an_implementation_hash") is False


def test_spec_sha256_scope_is_raw_document_bytes():
    assert spec("spec_sha256_scope") == \
        "raw_bytes_of_frozen_master_preregistration_document"


def test_implementation_identity_is_commit_plus_module_hashes():
    assert spec("implementation_identity") == \
        "code_commit_sha_plus_explicit_normative_module_hashes"


# --- F0-R4 · every declaration is backed ---------------------------------------

def test_all_declarations_conform():
    assert verify_declaration_bindings() == []
    assert assert_declarations_conform() is None


def test_the_register_covers_both_kinds_and_says_which():
    kinds = {b.kind for b in DECLARATION_BINDINGS}
    assert kinds == {IMPLEMENTATION_DERIVED, BEHAVIORAL_CONFORMANCE}
    s = summary()
    assert s["implementation_derived"] + s["behavioral_conformance"] == \
        s["declarations"]


def test_a_binding_must_name_its_evidence():
    with pytest.raises(DeclarationConformanceError, match="evidence"):
        DeclarationBinding("k", IMPLEMENTATION_DERIVED, "   ", lambda: None)


def test_an_unknown_binding_kind_aborts():
    with pytest.raises(DeclarationConformanceError, match="not defined"):
        DeclarationBinding("k", "probably_fine", "e", lambda: None)


def test_a_declaration_absent_from_the_registry_is_a_failure(monkeypatch):
    import core.b0_declaration_conformance as conform

    ghost = DeclarationBinding("not_a_registry_key", IMPLEMENTATION_DERIVED,
                               "nowhere", lambda: None)
    monkeypatch.setattr(conform, "DECLARATION_BINDINGS", (ghost,))
    failures = conform.verify_declaration_bindings()
    assert len(failures) == 1 and "absent from the frozen registry" in failures[0]


# --- the negative controls that make the checks worth running -----------------

def test_a_derived_declaration_moves_config_hash_when_the_module_moves(monkeypatch):
    """This is what IMPLEMENTATION_DERIVED actually buys.

    The binding's own check cannot catch a behaviour change here, and saying so
    is the point: both sides of that comparison read the same constant. The
    guarantee is upstream of the check — change the module and `config_hash`
    moves by itself, with nobody having to remember to update a sentence.
    """
    import core.b0_listing_spell as ls
    from core.b0_route import config_hash

    before = config_hash()
    monkeypatch.setattr(ls, "PRICE_LOOKBACK_SESSIONS", {"adv20": 999})
    assert config_hash() != before


def test_the_derived_check_catches_a_declaration_frozen_into_a_literal(monkeypatch):
    """The failure mode a derived binding CAN catch: somebody replaces the
    derivation with a copy of today's value, and the link is quietly gone."""
    import core.b0_master_prereg as prereg

    real = prereg._spec_registry

    def literal_copy():
        reg = dict(real())
        reg["price_lookback_sessions"] = (("adv20", 20), ("sigma20d", 20), ("x", 1))
        return reg

    monkeypatch.setattr(prereg, "_spec_registry", literal_copy)
    failures = verify_declaration_bindings()
    assert any("price_lookback_sessions" in f for f in failures)


def test_the_o_f_conformance_check_catches_an_unscoped_guard(monkeypatch):
    """Make the guard abort on names B0 does not hold; the sentence still says
    `held_positions_only`, so only the behavioural check can notice."""
    import core.b0_pit_observability as pit

    def unscoped(as_of, observations, holdings):
        return pit.assert_no_unexplained_price_gap(as_of, observations)

    monkeypatch.setattr(pit, "assert_no_unexplained_gap_in_holdings", unscoped)
    failures = verify_declaration_bindings()
    assert any("unexplained_gap_abort_scope" in f for f in failures)
    assert spec("unexplained_gap_abort_scope") == "held_positions_only"


def test_the_o_e_1_conformance_check_catches_a_relaxed_availability_rule(monkeypatch):
    import core.b0_pit_observability as pit

    monkeypatch.setattr(pit, "_available_before",
                        lambda available_from, session: bool(available_from))
    failures = verify_declaration_bindings()
    assert any("o_e_1_availability_rule" in f for f in failures)


def test_the_o_g_conformance_check_catches_a_bridged_spell(monkeypatch):
    """Let an unexplained gap keep the old spell; the declaration cannot tell."""
    import core.b0_listing_spell as ls

    real = ls.derive_current_spell

    def never_reopens(as_of, stock_id, expected, priced, gap_is_explained):
        return real(as_of, stock_id, expected, priced, lambda _s: True)

    monkeypatch.setattr(ls, "derive_current_spell", never_reopens)
    failures = verify_declaration_bindings()
    assert any("listing_spell_break_rule" in f for f in failures)


def test_a_seal_refuses_while_a_declaration_does_not_conform(monkeypatch):
    import core.b0_declaration_conformance as conform

    def broken():
        raise DeclarationConformanceError("synthetic drift")

    monkeypatch.setattr(conform, "DECLARATION_BINDINGS", (
        DeclarationBinding("N_target", BEHAVIORAL_CONFORMANCE, "synthetic",
                           broken),))
    with pytest.raises(DeclarationConformanceError, match="synthetic drift"):
        conform.assert_declarations_conform()


# --- F0-R7 · one hashing primitive --------------------------------------------

def test_route_and_provenance_share_one_hash_function():
    from core.b0_provenance import _h
    from core.b0_route import _hash

    assert _hash is not None and _h is not None
    payload = {"t": (1, 2), "n": None, "b": True, "s": "中文", "f": 1.5}
    assert _hash(payload) == _h(payload) == canonical_sha256(payload)


def test_there_is_no_second_serializer_left_in_core():
    """AST-free but sufficient: the two former implementations are gone."""
    import inspect

    from core import b0_provenance, b0_route

    for module in (b0_route, b0_provenance):
        src = inspect.getsource(module)
        assert "json.dumps" not in src, (
            f"{module.__name__} serialises on its own again; F0-R7 says one "
            f"primitive")


def test_the_primitive_is_versioned_and_declared():
    assert spec("canonical_hash_primitive") == CANONICAL_HASH_VERSION
    assert dict(spec("canonical_hash_json_settings"))["sort_keys"] is True


@pytest.mark.parametrize("a,b", [
    (None, "None"),
    (True, 1),
    (False, 0),
    (1, "1"),
])
def test_the_encoding_keeps_distinct_values_distinct(a, b):
    assert canonical_sha256({"k": a}) != canonical_sha256({"k": b})


def test_tuple_and_list_hash_alike_so_a_container_choice_is_not_a_change():
    assert canonical_sha256({"k": (1, 2)}) == canonical_sha256({"k": [1, 2]})


def test_dict_key_order_cannot_change_a_hash():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_non_string_keys_are_canonicalised_rather_than_raising():
    """The old provenance serializer raised on a tuple key; the route's did not.
    One primitive means one answer."""
    assert canonicalise({(1, 2): "x"}) == {"(1, 2)": "x"}
    assert canonical_sha256({(1, 2): "x"})


def test_whitespace_cannot_enter_the_serialisation():
    assert " " not in canonical_json({"a": 1, "b": [1, 2]})


def test_chinese_is_not_escaped_so_the_payload_stays_readable():
    assert "中文" in canonical_json({"k": "中文"})
