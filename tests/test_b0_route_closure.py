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
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_l3"))
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

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
)


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

def test_the_seal_payload_no_longer_repeats_landed_or_writer_owned_gates():
    """Code closure is complete; capture existence is checked by the writer."""
    payload = seal_payload()
    assert payload["closure_kind"] == \
        "PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE"
    owed = payload["still_owed_before_a_seal_may_be_taken"]
    assert owed == []

    # What has landed must appear in `done` and NOT in `owed`.
    done = " ".join(payload["done"]).lower()
    for finished in ("leaf producers", "readers", "assembly", "portfolio",
                     "runner", "freeze"):
        assert finished in done, finished


def test_the_seal_payload_carries_both_halves():
    payload = seal_payload()
    # 27 -> 28 at v1.34 / C-68 (`b0_l3_price_span`, the §19 span producer) and
    # 28 -> 29 at v1.35 / C-70 (`b0_l3_lineage_capture`, the §20 capture
    # contract). Both are reachable because the spec registry reads their
    # declarations.
    assert payload["code_closure_size"] == len(payload["code_closure"]) == 29
    assert payload["required_dataset_floor"] == list(REQUIRED_DATASET_FLOOR)
    assert set(payload["dataset_families"]) == set(DATASET_FAMILIES)
