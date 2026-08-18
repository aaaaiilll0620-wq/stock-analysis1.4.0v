"""Reachability invariants for the Frozen B0 production graph.

Some B0 properties are not "does this function compute the right number" but
"is this thing unreachable from B0 at all". Those are proved by walking the
project-local import closure of B0's declared entry points and asserting that
certain modules and identifiers never appear in it.

Two such invariants are declared here:

  G14-4 (B-14) — B0 must never reach Frozen-A's proportional cost path.
  B-17         — no B0 production-reachable path in ranking / eligibility /
                 weight / cost may contain a regime-dependent alpha multiplier,
                 threshold, or branch.

Both are enforced the same way, so the graph machinery lives here once rather
than being copied into each test.

Design note: identifiers are collected from the AST as Name/Attribute nodes, so
declaring a forbidden symbol as a *string literal* (as this module does) never
counts as referencing it. That is what lets the guard describe what it forbids
without tripping over itself.
"""

from __future__ import annotations

import ast

import os
from typing import Iterable, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- B0 entry points ---------------------------------------------------------
# Every invariant below applies to the import closure of these modules, so
# extending the tuple extends the checks with no change to the tests.
#
# P-1b appended the four canonical core layers (§8.7) and the state contract they
# consume. They are not yet a route — no adapter feeds them (that is P-2) — but
# the invariants are static properties of the import graph, not of a run, so
# there is no reason to wait: a regime import or a Frozen-A cost constant reaching
# the core is caught the moment it is written rather than at route assembly.
B0_ENTRY_MODULES: tuple[str, ...] = (
    "core.b0_cost_model", "core.b0_corporate_actions",
    "core.b0_state", "core.b0_features", "core.b0_eligibility",
    "core.b0_decision", "core.b0_execution",
    # P-2: the shared route and its two adapters. Adding the adapters is the
    # point — they are the modules most exposed to legacy imports, since they
    # are where source access lives.
    "core.b0_route", "core.b0_adapter_retrospective", "core.b0_adapter_production",
    # D1-6: the price-source admissibility gate is route-reachable, so the same
    # regime / legacy-cost / override invariants apply to it.
    "core.b0_price_universe",
    # O-G: listing spells decide which sessions a price window may read, so the
    # module is route-reachable and carries the same invariants.
    "core.b0_listing_spell",
)

# --- O-F: current-snapshot delisting fields stay audit-only ------------------
# `公司資料.xlsx` and the 事件+下市 export answer "has this security been
# delisted, as of the export". Both rewrite history: 505 securities have their
# 上市別 overwritten on delisting, and 25 of the 27 exit-and-return securities
# have their earlier 下市日期 blanked entirely. They are legitimate AUDIT
# references and they are not runtime sources, so the boundary is a check rather
# than a note in a docstring.
AUDIT_ONLY_MODULES = (
    "research.d1_price_universe.audit_universe_vs_master",
    "audit_universe_vs_master",
)
AUDIT_ONLY_SYMBOLS = (
    "下市日期",          # current-snapshot delisting date
    "公司資料",          # the snapshot workbook itself
    "load_master",       # its loader
    "delisted_on",       # the field that loader produces
)


# --- G14-4: Frozen-A proportional cost path ---------------------------------
LEGACY_COST_MODULES = ("l4b_execution", "portfolio_simulator_lab")
LEGACY_COST_SYMBOLS = ("BUY_COST", "SELL_COST")

# --- B-17: regime-dependent decision inputs ---------------------------------
# Modules whose whole purpose is to make a decision depend on a market-regime
# label. Reporting-only regime labels are NOT listed here (see docs).
REGIME_DECISION_MODULES = ("core.regime", "core.regime_exposure")
# Identifiers that inject a regime label into ranking / weighting / gating.
REGIME_DECISION_SYMBOLS = (
    "REGIME_MULTIPLIERS",      # composite-weight multipliers
    "regime_multipliers",      # accessor for the above
    "regime_rating_gates",     # regime-dependent rating thresholds
    "classify_regime",         # produces the label consumed by the two above
    "current_regime",          # the advisor attribute the label is injected into
    "use_regime",              # backtest switch, defaults True
    "_regime_at",              # backtest per-date label lookup
    "OVERLAY_ALPHA",           # C-layer exposure overlay strength
)


# --- B-19: runtime / config override integrity -------------------------------
# Modules that exist to override frozen semantics at runtime.
OVERRIDE_MODULES = ("beat_0050.realbody.bt_bundle",)
# Identifiers that silently change factor definition, data window, data
# semantics, feature enablement, or execution policy when set.
OVERRIDE_SYMBOLS = (
    "RESEARCH_ARM",              # arm switch, mutates scoring in 5 modules
    "TEJ_RUNTIME_OVERLAY_DIR",   # env-driven dataset merge layer
    "_PCT_HISTORY_START",        # valuation percentile window (2019 vs 2004)
    "bt_fetch_history",          # backtest-only bundle wrapper
    "USE_RS_OVERLAY",            # feature flags, all A/B-fitted
    "USE_KD_FULL",
    "USE_BBP",
    "USE_OBV_TREND",
    "USE_ASSET_TURNOVER",
)

# Every legal B0 override must resolve to exactly one frozen prereg clause or
# config key. An override with no entry here is a silent semantic change and
# must abort — never fall back to a default (B-19 rule).
B0_REGISTERED_OVERRIDES: dict[str, str] = {
    # key -> frozen prereg clause / config key that authorises it
}


class OverrideNotRegistered(RuntimeError):
    """Fail-loud: a runtime override with no frozen-prereg provenance."""


def assert_override_registered(key: str) -> str:
    """Return the authorising clause for `key`, or abort.

    Deliberately has no default branch: 'not registered' is a stop, not a
    fallback. A fallback here would reintroduce exactly the silent override this
    guard exists to prevent.
    """
    clause = B0_REGISTERED_OVERRIDES.get(key)
    if not clause:
        raise OverrideNotRegistered(
            f"B-19: runtime override {key!r} has no frozen preregistration clause. "
            f"Register it against a unique clause/config key, or remove it. "
            f"Defaulting is not permitted."
        )
    return clause


def find_import_time_foreign_mutations(entry_modules: Iterable[str]) -> list[tuple[str, str]]:
    """Module-level assignments to ANOTHER module's attribute.

    This is the `bt_bundle.py:27` pattern — `_tb._PCT_HISTORY_START = "2004-01-01"`
    at module scope. Merely importing such a module silently changes a third
    module's behaviour process-wide, for every consumer, including ones that never
    asked. It is the hardest override class to notice by reading call sites,
    because there is no call site.
    """
    found: list[tuple[str, str]] = []
    for name, src in local_import_closure(entry_modules):
        tree = ast.parse(src)
        for node in tree.body:                      # module scope only
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    found.append((name, f"{target.value.id}.{target.attr}"))
    return found


def _module_path(name: str) -> str | None:
    """Resolve a dotted module name to a file under REPO_ROOT, WITHOUT importing.

    Importing would execute the module. Several modules in this repository have
    destructive import side effects (core/data_provider.py instantiates a
    DataLoader at class-body scope, which opens a network login), so a guard that
    imported its targets would be both unsafe and slower than the static answer
    it actually needs. Reachability is a static property; resolve it statically.
    """
    rel = name.replace(".", os.sep)
    for candidate in (os.path.join(REPO_ROOT, rel + ".py"),
                      os.path.join(REPO_ROOT, rel, "__init__.py")):
        if os.path.isfile(candidate):
            return candidate
    return None


def local_import_closure(entry_modules: Iterable[str]) -> list[tuple[str, str]]:
    """Transitive closure of project-local imports as (module_name, source) pairs.

    Third-party and stdlib modules are out of scope: they cannot reference this
    project's identifiers. Names that do not resolve to a file inside the repo
    are skipped for exactly that reason — never imported, never executed.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    stack = list(entry_modules)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        path = _module_path(name)
        if path is None:
            continue
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        out.append((name, src))
        pkg = name.rsplit(".", 1)[0] if "." in name else ""
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                stack += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:                      # relative import
                    base = pkg
                    for _ in range(node.level - 1):
                        base = base.rsplit(".", 1)[0] if "." in base else ""
                    target = f"{base}.{node.module}" if node.module else base
                    if target:
                        stack.append(target)
                elif node.module:
                    stack.append(node.module)
    return out


def referenced_names(src: str) -> set[str]:
    """Identifiers referenced in code. String literals are excluded by design."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def find_violations(entry_modules: Iterable[str],
                    forbidden_modules: Sequence[str],
                    forbidden_symbols: Sequence[str]) -> list[tuple[str, str]]:
    """(module, reason) for every forbidden module or symbol reachable from entry."""
    violations: list[tuple[str, str]] = []
    for name, src in local_import_closure(entry_modules):
        if any(name == m or name.endswith("." + m.rsplit(".", 1)[-1])
               for m in forbidden_modules):
            violations.append((name, "reaches forbidden module"))
            continue
        hits = referenced_names(src) & set(forbidden_symbols)
        if hits:
            violations.append((name, f"references {sorted(hits)}"))
    return violations
