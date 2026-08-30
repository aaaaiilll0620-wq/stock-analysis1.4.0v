# -*- coding: utf-8 -*-
"""A2 / W4 · the production route's code closure and data inventory.

Both are DERIVED, and these tests exist because both derivations were wrong on
the first attempt in ways that would not have raised anything:

  * the code closure handled `from core.X import y` but not `from core import X`,
    reported 18 modules instead of 27, and silently dropped the entire decision
    layer. An under-inclusive closure produces an under-inclusive seal, which is
    worse than no seal because it looks complete.

  * the dataset floor was hand-listed at seven families and omitted `industry`
    and `bonus_shares`, both of which change decisions without raising.

So the point of this file is not that the numbers are 27 and 9. It is that the
derivation catches what a list would not.
"""
from __future__ import annotations

import ast
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_l3"))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))
sys.path.insert(0, os.path.join(REPO, "research", "b0_l3_runner"))

import l3_route_seal as rs                                        # noqa: E402
from core.b0_master_prereg import NORMATIVE_MODULES              # noqa: E402
from route_closure import (                                       # noqa: E402
    DATASET_FAMILIES,
    EXPECTED_OUTSIDE_CLOSURE,
    REQUIRED_DATASET_FLOOR,
    ROUTE_ENTRY_POINTS,
    RouteClosureError,
    _core_imports,
    assert_closure_is_wholly_normative,
    assert_inventories_agree,
    production_route_code_closure,
    retrospective_source_families,
    seal_payload,
    still_owed_before_a_seal_may_be_taken,
)

ROUTE_CLOSURE_PY = os.path.join(REPO, "research", "b0_l3", "route_closure.py")


# --- the derivation bug that made the first closure under-inclusive ------------

def test_both_import_forms_are_followed(tmp_path):
    """`from core import X` is how b0_route reaches the whole decision layer."""
    p = os.path.join(str(tmp_path), "probe.py")
    open(p, "w", encoding="utf-8").write(
        "from core import b0_decision as decision\n"
        "from core.b0_state import PortfolioState\n"
        "import core.b0_features\n")
    assert _core_imports(p) == {"b0_decision", "b0_state", "b0_features"}


def test_the_decision_layer_is_inside_the_closure():
    """The modules the first derivation dropped. If these ever fall out again,
    the seal stops covering how B0 actually decides."""
    closure = set(production_route_code_closure())
    for module in ("b0_decision", "b0_eligibility", "b0_features",
                   "b0_execution", "b0_cost_model"):
        assert module in closure, module


def test_the_closure_reaches_the_sources_that_shape_prices():
    """Share-unit adjustment and the bonus multiplier are reachable, which is
    why `bonus_shares` is a required dataset and not a nicety."""
    closure = set(production_route_code_closure())
    assert "b0_share_unit_adjustment" in closure
    assert "b0_bonus_share_source" in closure


# --- the closure boundary ------------------------------------------------------

def test_the_route_reaches_nothing_the_seal_would_not_bind():
    closure = assert_closure_is_wholly_normative()
    normative = {os.path.basename(m)[:-3] for m in NORMATIVE_MODULES}
    assert closure and set(closure) <= normative


def test_every_normative_module_outside_the_closure_has_a_stated_reason():
    closure = set(production_route_code_closure())
    normative = {os.path.basename(m)[:-3] for m in NORMATIVE_MODULES}
    outside = normative - closure
    assert outside == set(EXPECTED_OUTSIDE_CLOSURE)
    for reason in EXPECTED_OUTSIDE_CLOSURE.values():
        assert reason.strip()


def test_the_other_route_is_not_reachable_from_this_one():
    """B-20: a production run may not import the retrospective adapter."""
    assert "b0_adapter_retrospective" not in production_route_code_closure()


def test_the_entry_points_are_the_two_a_run_actually_has():
    assert ROUTE_ENTRY_POINTS == ("b0_adapter_production", "b0_route")


def test_an_unbound_module_would_be_refused(tmp_path, monkeypatch):
    """Negative control: if the route ever reached outside the normative set,
    the closure check must fail rather than shrug."""
    import route_closure as rc

    monkeypatch.setattr(
        rc, "production_route_code_closure",
        lambda *a, **k: tuple(sorted(set(production_route_code_closure())
                                     | {"b0_some_new_helper"})))
    with pytest.raises(RouteClosureError, match="outside the normative set"):
        rc.assert_closure_is_wholly_normative()


# --- the dataset inventory -----------------------------------------------------

def test_the_floor_is_the_nine_families_not_the_seven_i_first_listed():
    assert len(REQUIRED_DATASET_FLOOR) == 9
    for late in ("industry", "bonus_shares"):
        assert late in REQUIRED_DATASET_FLOOR, late


def test_the_two_routes_name_the_same_source_families():
    """P2-3: a field means one thing across both routes, so if the retrospective
    materializer grows a tenth source this is where the staleness shows up."""
    assert_inventories_agree()
    assert len(retrospective_source_families()) == len(DATASET_FAMILIES)


def test_a_source_the_other_route_loads_cannot_be_dropped_here(monkeypatch):
    import route_closure as rc

    monkeypatch.setattr(
        rc, "DATASET_FAMILIES",
        {k: v for k, v in DATASET_FAMILIES.items() if k != "bonus_shares"})
    with pytest.raises(RouteClosureError, match="does not declare"):
        rc.assert_inventories_agree()


def test_every_family_says_what_it_feeds_and_how_it_is_addressed():
    from core.b0_adapter_production import ProductionSources
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ProductionSources)}
    # `execution_prices` is a build_input argument rather than a sources field.
    fields.add("execution_prices")

    for name, d in DATASET_FAMILIES.items():
        assert d["feeds"], name
        assert d["locator_form"], name
        assert d["leaf_notes"].strip(), name
        for fed in d["feeds"]:
            assert fed in fields, "%s feeds unknown field %s" % (name, fed)


def test_the_three_locator_forms_are_distinct_because_the_sources_are():
    """One extension whitelist cannot describe a flat directory, an archive and
    a keyed payload store."""
    forms = {d["locator_form"] for d in DATASET_FAMILIES.values()}
    assert forms == {"flat_directory_filename",
                     "archive_with_member_inventory",
                     "board_date_payload_key",
                     "archive_set_plus_leaf_dependency",
                     "harvested_payload_key"}
    assert DATASET_FAMILIES["prices"]["locator_form"] == \
        "archive_with_member_inventory"
    assert DATASET_FAMILIES["valuation"]["locator_form"] == \
        "board_date_payload_key"
    # corporate_actions has two upstreams, only one of which is a directory;
    # bonus_shares is addressed by harvested payload key like valuation.
    assert DATASET_FAMILIES["corporate_actions"]["locator_form"] == \
        "archive_set_plus_leaf_dependency"
    assert DATASET_FAMILIES["bonus_shares"]["locator_form"] == \
        "harvested_payload_key"


def test_the_manifest_engine_uses_the_derived_floor():
    """The engine must not keep its own copy — that is how they drift."""
    from source_ownership_manifest import REQUIRED_DATASETS
    assert tuple(REQUIRED_DATASETS) == REQUIRED_DATASET_FLOOR

    path = os.path.join(REPO, "research", "b0_materializer",
                        "source_ownership_manifest.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    assigned = [n for n in ast.walk(tree)
                if isinstance(n, ast.AnnAssign)
                and getattr(n.target, "id", "") == "REQUIRED_DATASETS"]
    assert not assigned, "REQUIRED_DATASETS is re-declared instead of imported"


# --- what a seal would bind ----------------------------------------------------

def test_the_seal_payload_owes_nothing_while_nothing_is_genuinely_outstanding():
    """Direction one of the honesty check: empty, and empty for a REASON.

    Emptiness here is a measurement — every fact behind a `done` claim was
    re-checked on this call — not a decision someone recorded once. The three
    items cleared since v1.34 (the master freeze, the portfolio side, the
    runner) are each re-derived; the fourth, the `lineage_price_floor` capture,
    was re-homed to `write_route_seal`'s `verified_capture_binding`, which is a
    mechanical gate rather than a sentence, and is deliberately not restated
    here.
    """
    payload = seal_payload()
    assert payload["closure_kind"] == \
        "PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE"
    owed = payload["still_owed_before_a_seal_may_be_taken"]
    assert owed == [], owed

    # ... and on that basis the seal gate accepts, rather than being unable to
    # refuse.
    assert rs.assert_route_is_sealable()["code_closure_size"] > 0

    # What has landed must appear in `done` and NOT in `owed`.
    done = " ".join(payload["done"]).lower()
    for finished in ("leaf producers", "readers", "assembly", "portfolio",
                     "runner", "freeze"):
        assert finished in done, finished
    for finished in ("leaf producer", "reader"):
        assert not any(finished in o.lower() for o in owed), finished


def test_a_freeze_that_regains_an_unmet_blocker_is_owed_and_the_gate_refuses(
        tmp_path, monkeypatch):
    """Direction two, injected as a real condition rather than stubbed.

    A REAL freeze record — the repository's own, with one field changed to what
    it would say if a blocking data requirement's verifier stopped being
    satisfied — is written to disk and the module is pointed at it. Nothing
    about `seal_payload` or `assert_route_is_sealable` is replaced; they read
    the injected fact and must both react to it.
    """
    import route_closure as rc

    with open(rc.MASTER_FREEZE_PATH, encoding="utf-8") as fh:
        record = json.load(fh)
    assert record["unmet_blocking_requirements"] == [], \
        "the repository freeze is expected to be clean before injection"
    record["unmet_blocking_requirements"] = ["price_universe_cross_source_audit"]

    injected = os.path.join(str(tmp_path), "master_prereg_freeze.json")
    with open(injected, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False)
    monkeypatch.setattr(rc, "MASTER_FREEZE_PATH", injected)

    owed = rc.seal_payload()["still_owed_before_a_seal_may_be_taken"]
    assert owed, "an unmet blocking requirement must be declared, not swallowed"
    assert any("price_universe_cross_source_audit" in o for o in owed), owed

    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_route_is_sealable()
    assert "price_universe_cross_source_audit" in str(exc.value)


def test_a_route_component_that_went_missing_is_owed_and_the_gate_refuses(
        monkeypatch):
    """The other half of direction two: a `done` claim with nothing behind it.

    The runner's entry is repointed at a path that does not exist — which is
    what the repository would look like if the runner were removed — and the
    gate must refuse and name it.
    """
    import route_closure as rc

    gone = dict(rc.ROUTE_COMPONENTS)
    name = "prospective runner invoking the native decision route"
    assert name in gone, sorted(gone)
    gone[name] = {
        "path": os.path.join("research", "b0_l3_runner",
                             "run_l3_prospective_removed.py"),
        "must_reference": ("run_decision",),
    }
    monkeypatch.setattr(rc, "ROUTE_COMPONENTS", gone)

    owed = rc.seal_payload()["still_owed_before_a_seal_may_be_taken"]
    assert any("run_l3_prospective_removed.py" in o for o in owed), owed

    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_route_is_sealable()
    assert "not on disk" in str(exc.value)


def test_a_component_that_stops_doing_what_its_claim_says_is_owed(monkeypatch):
    """Presence is not the claim. `done` says the runner INVOKES the native
    decision route, so a file that no longer references `run_decision` owes it —
    checked against a real file in the repository that genuinely does not."""
    import route_closure as rc

    hollow = dict(rc.ROUTE_COMPONENTS)
    hollow["prospective runner invoking the native decision route"] = {
        # a real, present, parseable module that does not call run_decision
        "path": os.path.join("research", "b0_l3", "route_closure.py"),
        "must_reference": ("run_decision",),
    }
    monkeypatch.setattr(rc, "ROUTE_COMPONENTS", hollow)

    owed = rc.seal_payload()["still_owed_before_a_seal_may_be_taken"]
    assert any("run_decision" in o and "no longer references" in o
               for o in owed), owed
    with pytest.raises(rs.RouteSealError):
        rs.assert_route_is_sealable()


def test_the_owed_list_is_derived_on_every_call_not_written_down():
    """The regression this file exists to prevent a second time.

    The list was once replaced by the literal `[]`, which left the gate that
    reads it unable to fail under any input. A literal there — empty or not — is
    the defect, so the payload's value must be a CALL.
    """
    tree = ast.parse(open(ROUTE_CLOSURE_PY, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "seal_payload")
    values = [v for ret in ast.walk(fn) if isinstance(ret, ast.Return)
              and isinstance(ret.value, ast.Dict)
              for k, v in zip(ret.value.keys, ret.value.values)
              if isinstance(k, ast.Constant)
              and k.value == "still_owed_before_a_seal_may_be_taken"]
    assert len(values) == 1, "the owed key must be produced exactly once"
    assert isinstance(values[0], ast.Call), \
        "the owed list is a literal again; the seal gate cannot fail on it"

    # and the derivation is callable on its own, returning a container the gate
    # can be empty or non-empty about
    assert isinstance(still_owed_before_a_seal_may_be_taken(), tuple)


def test_the_seal_payload_carries_both_halves():
    payload = seal_payload()
    # 27 -> 28 at v1.34 / C-68 (`b0_l3_price_span`, the §19 span producer) and
    # 28 -> 29 at v1.35 / C-70 (`b0_l3_lineage_capture`, the §20 capture
    # contract). Both are reachable because the spec registry reads their
    # declarations.
    assert payload["code_closure_size"] == len(payload["code_closure"]) == 29
    assert payload["required_dataset_floor"] == list(REQUIRED_DATASET_FLOOR)
    assert set(payload["dataset_families"]) == set(DATASET_FAMILIES)
