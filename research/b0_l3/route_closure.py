# -*- coding: utf-8 -*-
"""A2 / W4 · what the production route IS, derived rather than declared.

Two questions had to be answered before an L3 run can be sealed or its sources
declared, and §9.9 answers neither:

    A2   what does "production route sealed" cover — the adapter alone, or the
         whole replayable route?
    W4   which dataset families must a run's source manifest carry?

Both are answered here by DERIVATION, because a hand-written list is exactly how
a source goes missing. That is not hypothetical: the first provisional floor in
`source_ownership_manifest.REQUIRED_DATASETS` was hand-listed at seven families
and silently omitted `industry` and `bonus_shares` — both of which shape a
decision (`SecurityPitInputs.pit_industry` is a feature input, and the bonus
panel supplies the holder multiplier behind the share-unit-adjusted price series
that momentum reads). A list nobody derived is a list nobody checked.

CODE CLOSURE (A2)
-----------------
Transitive `core.*` imports from the two entry points a production run has:
`b0_adapter_production` (sources -> canonical state) and `b0_route`
(`run_decision`). Measured 2026-08-26: **27 of the 31 normative modules**, and
nothing outside the normative set.

⚠ The derivation must handle `from core import b0_decision` as well as
`from core.b0_decision import ...`. A first pass here handled only the second
form, reported 18 modules, and silently dropped the entire decision layer —
`b0_decision`, `b0_eligibility`, `b0_features`, `b0_execution` and their
dependencies. An under-inclusive closure produces an under-inclusive seal, which
is worse than no seal: it looks complete.

The four normative modules OUTSIDE the closure are outside it for a reason, and
the reason is checked (`EXPECTED_OUTSIDE_CLOSURE`): a B0.1 historical pin, the
retrospective adapter (the other route), and the two 0050 benchmark modules
(L2 evaluation, not production decision-making).

DATA INVENTORY (W4)
-------------------
Nine dataset families, each mapped to the `ProductionSources` field it feeds and
the locator form its leaf must use. Cross-checked against the retrospective
materializer's `load_sources()`, which is the only other place the same question
is answered — P2-3 requires a field to mean one thing across both routes, so the
two inventories must agree family for family.
"""
from __future__ import annotations

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from core.b0_master_prereg import NORMATIVE_MODULES              # noqa: E402

ROUTE_ENTRY_POINTS: tuple[str, ...] = ("b0_adapter_production", "b0_route")

# Normative, but not part of a production decision. Named so that "not in the
# closure" is a checked claim rather than a leftover.
EXPECTED_OUTSIDE_CLOSURE: dict = {
    "b0_1_diagnostic_closure":
        "immutable pin of the B0.1 diagnostic terminal; history, not route",
    "b0_adapter_retrospective":
        "the OTHER route; a production run must not import it (B-20)",
    "b0_benchmark_construction":
        "0050 benchmark, §13.2-13.4 — L2 evaluation, not decision-making",
    "b0_benchmark_gate1":
        "L2 gate arithmetic; never consulted while deciding",
}


class RouteClosureError(RuntimeError):
    """Fail-loud: the route is not what the closure says it is."""


# --- code closure --------------------------------------------------------------

def _core_imports(path: str) -> set:
    """Every `core.*` module this file imports, in BOTH import forms."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "core":
                out |= {a.name for a in node.names}       # from core import X
            elif node.module and node.module.startswith("core."):
                out.add(node.module.split(".", 1)[1])     # from core.X import y
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("core."):
                    out.add(a.name.split(".", 1)[1])      # import core.X
    return out


def production_route_code_closure(entry_points=ROUTE_ENTRY_POINTS) -> tuple:
    """Transitive `core.*` closure of the production route, sorted."""
    seen, queue = set(), list(entry_points)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = os.path.join(REPO, "core", module + ".py")
        if os.path.exists(path):
            queue += [d for d in _core_imports(path) if d not in seen]
    return tuple(sorted(seen))


def assert_closure_is_wholly_normative() -> tuple:
    """The route may not reach code the seal does not bind."""
    closure = set(production_route_code_closure())
    normative = {os.path.basename(m)[:-3] for m in NORMATIVE_MODULES}

    unbound = sorted(closure - normative)
    if unbound:
        raise RouteClosureError(
            "the production route reaches %d module(s) outside the normative "
            "set: %s. A seal that binds only normative modules would not bind "
            "these, so a change to them would move the route without moving its "
            "seal." % (len(unbound), unbound))

    outside = sorted(normative - closure)
    unexplained = [m for m in outside if m not in EXPECTED_OUTSIDE_CLOSURE]
    if unexplained:
        raise RouteClosureError(
            "%d normative module(s) are outside the route closure with no "
            "recorded reason: %s. Either the route stopped using them or the "
            "derivation is under-inclusive; both need saying out loud."
            % (len(unexplained), unexplained))
    return tuple(sorted(closure))


# --- data inventory ------------------------------------------------------------
#
# `locator_form` is what a leaf entry must use to address a member of that
# family. They differ on purpose: a flat directory of workbooks, an archive whose
# members must be inventoried, and a keyed payload store are three different
# shapes, and one extension whitelist cannot describe all three.

DATASET_FAMILIES: dict = {
    "financials": {
        "feeds": ("pit_inputs",),
        "retrospective_loader_name": "fin",
        "locator_form": "flat_directory_filename",
        "leaf_notes": "accepted extensions .xlsx/.csv; period owns/yields",
    },
    "revenue": {
        "feeds": ("pit_inputs",),
        "retrospective_loader_name": "rev",
        "locator_form": "flat_directory_filename",
        "leaf_notes": "monthly_revenue, 18-month depth (revenue_accel)",
    },
    "valuation": {
        "feeds": ("pit_inputs",),
        "retrospective_loader_name": "val",
        "locator_form": "board_date_payload_key",
        "leaf_notes": (
            "per_tse / pbr_tse. NOT a *.json glob: each payload is addressed by "
            "board (TWSE|TPEx) + session date + payload key + hash. The frozen "
            "2019+ lineage forbids TEJ substitution, so the exchange payload IS "
            "the source and its identity must be exact."),
    },
    "industry": {
        "feeds": ("pit_inputs",),
        "retrospective_loader_name": "ind",
        "locator_form": "flat_directory_filename",
        "leaf_notes": (
            "SecurityPitInputs.pit_industry. O-E ruled the live industry_map "
            "NOT_PIT_SAFE (49.4% of names changed sector), so a leaf must name a "
            "dated snapshot, never a current-state lookup."),
    },
    "prices": {
        "feeds": ("marks", "adv20", "sigma20d", "price_observations",
                  "execution_prices"),
        "retrospective_loader_name": "px",
        "locator_form": "archive_with_member_inventory",
        "leaf_notes": (
            "NOT a *.zip glob: the leaf declares each ZIP, its hash, AND the "
            "full member inventory. An archive that gained or lost a member "
            "without the inventory changing is the same silent-skip defect one "
            "level down."),
    },
    "calendar": {
        "feeds": ("calendar",),
        "retrospective_loader_name": "cal",
        "locator_form": "flat_directory_filename",
        "leaf_notes": (
            "fixes as_of (§6.6) and the execution session (§6.5). It decides "
            "WHEN, which decides everything else."),
    },
    "security_status": {
        "feeds": ("status_table", "price_observations", "listing_spells"),
        "retrospective_loader_name": "status",
        "locator_form": "flat_directory_filename",
        "leaf_notes": (
            "known_status + status_available_from. B0.6 exists because the "
            "second field was missing from the state."),
    },
    "corporate_actions": {
        "feeds": ("corporate_action_events",),
        "retrospective_loader_name": "ledger",
        "locator_form": "archive_set_plus_leaf_dependency",
        "leaf_notes": (
            "holder outcomes. NOT_RECONSTRUCTIBLE rows are part of the source, "
            "not an absence to be filtered out."),
    },
    "bonus_shares": {
        "feeds": ("price_observations",),
        "retrospective_loader_name": "bonus",
        "locator_form": "harvested_payload_key",
        "leaf_notes": (
            "C-51 holder multiplier `m = 1 + 每千股無償配股/1000`, the only "
            "admissible source for the share-unit adjustment that the momentum "
            "price series is built on. Omitting it does not raise; it silently "
            "changes momentum."),
    },
}

REQUIRED_DATASET_FLOOR: tuple[str, ...] = tuple(sorted(DATASET_FAMILIES))


def retrospective_source_families() -> tuple:
    """The families `build_market_side_state.load_sources()` returns.

    Read off its `return` statement rather than trusted from memory: P2-3
    requires the two routes to mean the same thing by a field, so if the
    retrospective loader grows a tenth source the production inventory is stale
    and this is where that shows up.
    """
    path = os.path.join(REPO, "research", "b0_materializer",
                        "build_market_side_state.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "load_sources":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value,
                                                              ast.Tuple):
                    return tuple(e.id for e in sub.value.elts
                                 if isinstance(e, ast.Name))
    raise RouteClosureError(
        "could not read load_sources()'s return tuple; the cross-check between "
        "the two routes' source inventories cannot be made")


def assert_inventories_agree() -> None:
    """Production inventory and retrospective loader must name the same families."""
    theirs = set(retrospective_source_families())
    mine = {d["retrospective_loader_name"] for d in DATASET_FAMILIES.values()}

    missing = sorted(theirs - mine)
    if missing:
        raise RouteClosureError(
            "the retrospective materializer loads %d source(s) the production "
            "inventory does not declare: %s. A source that decides a "
            "retrospective decision decides a prospective one too."
            % (len(missing), missing))
    extra = sorted(mine - theirs)
    if extra:
        raise RouteClosureError(
            "the production inventory declares %d family(ies) the retrospective "
            "materializer does not load: %s. Either it is genuinely "
            "production-only and should say so, or it is a typo."
            % (len(extra), extra))


# --- what a seal would bind ----------------------------------------------------

def seal_payload() -> dict:
    """Everything A2's closure covers, ready to be hashed into a route seal.

    This does NOT take a seal: A2 ruled the closure is the whole replayable
    route. What it does is fix WHAT is sealed, so the boundary is not
    renegotiated at sealing time.  Lineage/capture existence is enforced by the
    route-seal writer itself and therefore is not duplicated as a stale text
    item here.
    """
    closure = assert_closure_is_wholly_normative()
    assert_inventories_agree()
    return {
        "closure_kind": "PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE",
        "entry_points": list(ROUTE_ENTRY_POINTS),
        "code_closure": list(closure),
        "code_closure_size": len(closure),
        "normative_modules_outside_closure": {
            k: v for k, v in sorted(EXPECTED_OUTSIDE_CLOSURE.items())},
        "required_dataset_floor": list(REQUIRED_DATASET_FLOOR),
        "dataset_families": {
            k: {"feeds": list(v["feeds"]), "locator_form": v["locator_form"]}
            for k, v in sorted(DATASET_FAMILIES.items())},
        "still_owed_before_a_seal_may_be_taken": [],
        "done": [
            "nine dataset leaf producers + aggregate assembler (W6a/W4)",
            "L3 run-scoped immutable run layout (W7)",
            "W6b snapshot receipt, period derivation and guards",
            "W6b-2 readers: all nine families parse, each verified against its "
            "sealed L2 counterpart (verify_reader_parity.py)",
            "W6b-2 assembly: market-side CanonicalDecisionInput, verified "
            "against L2's sealed market_state_sha256 for 2026-03 "
            "(verify_assembly_parity.py); RECEIPT_ONLY -> MATERIALIZED",
            "portfolio-side checkpoint materialization (B7)",
            "prospective runner invokes the native decision route",
            "Master freeze advanced beyond the stale v1.32 blocker",
        ],
    }


if __name__ == "__main__":
    import json

    print(json.dumps(seal_payload(), ensure_ascii=False, indent=1))
