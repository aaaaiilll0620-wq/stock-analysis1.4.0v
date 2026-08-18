"""B-20 production / research decision-path parity harness.

The claim B-20 must eventually support:

    Frozen B0's five semantic layers — feature, eligibility, ranking/portfolio,
    execution, cost — are identical on the production-reachable path and on the
    research/preregistered path.

Parity cannot be asserted by inspection when two implementations exist; it has to
be *measured* on a deterministic fixture. This module provides the measurement,
the fixture contract, and the route registry.

Design stance, inherited from core/canonical_universe.py (P0-U1): where two
implementations of one definition exist, the preferred resolution is to extract
the primitive verbatim into a canonical shared engine, NOT to keep two copies
alive and police them with a test. A passing parity test on duplicated logic
proves the copies agree *today*; it does not stop them diverging tomorrow, and
this repository already contains a case where two same-named implementations
silently diverged (see `rev_accel`, B-09 finding F-B).

Tests therefore serve two different roles here, and the distinction matters:
  - for CONVERGED code, the test is a regression guard;
  - for DUPLICATED code, the test is a drift detector and a standing debt marker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# The seven per-decision output columns that must match column-by-column.
PARITY_COLUMNS: tuple[str, ...] = (
    "eligible",   # bool  — passed complete-case + investability + risk gates
    "score",      # float — SelectionScore
    "rank",       # int   — descending rank within the eligible set
    "selected",   # bool  — in the target list
    "orders",     # float — signed share delta for the decision
    "cash",       # float — post-decision cash
    "cost",       # float — total modelled cost for the decision
)

# Layers whose semantics parity must cover.
PARITY_LAYERS: tuple[str, ...] = (
    "feature", "eligibility", "ranking_portfolio", "execution", "cost",
)

# (production_entry_module, research_entry_module) pairs. Declaring a pair
# without a fixture is itself a failure (see tests): an unmeasured parity claim
# is worse than an absent one, because it reads as if it had been checked.
#
# Registered by P-2. Note what the pair now IS: two adapters, not two engines.
# Both call `core.b0_route.run_decision`, so the fixture measures whether they
# supply the same as_of / config / state and consume the output correctly —
# §8.7's "the parity that is actually needed". The module docstring's preferred
# resolution (extract the primitive, do not police two copies) is what was done.
B0_ROUTE_PAIRS: tuple[tuple[str, str], ...] = (
    ("core.b0_adapter_production", "core.b0_adapter_retrospective"),
)


class ParityError(AssertionError):
    """Fail-loud: the two paths disagree, or a parity claim is unmeasured."""


@dataclass(frozen=True)
class Divergence:
    key: Any
    column: str
    production: Any
    research: Any

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return (f"{self.key!r}.{self.column}: "
                f"production={self.production!r} research={self.research!r}")


@dataclass
class DecisionSnapshot:
    """One decision date's output from ONE path.

    `rows` maps an instrument key to its per-column values. `config_hash` and
    `state_hash` pin the inputs: parity between two paths fed different inputs
    is meaningless, so they are compared first.
    """

    as_of: str
    config_hash: str
    state_hash: str
    rows: Mapping[Any, Mapping[str, Any]] = field(default_factory=dict)


def _equal(a: Any, b: Any, *, float_tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) or isinstance(b, float):
            if math.isnan(a) and math.isnan(b):
                return True          # both-absent is agreement, not disagreement
            return abs(float(a) - float(b)) <= float_tol
        return a == b
    return a == b


def compare_decisions(production: DecisionSnapshot,
                      research: DecisionSnapshot,
                      columns: Sequence[str] = PARITY_COLUMNS,
                      *,
                      float_tol: float = 0.0) -> list[Divergence]:
    """Column-by-column comparison. `float_tol = 0.0` means bit-exact by default.

    A non-zero tolerance must be justified per column at the call site; a blanket
    tolerance would let a real definitional difference hide inside rounding.
    """
    if production.as_of != research.as_of:
        raise ParityError(f"as_of mismatch: {production.as_of} vs {research.as_of}")
    if production.config_hash != research.config_hash:
        raise ParityError("config_hash mismatch — the two paths were not given "
                          "the same frozen config; parity is undefined")
    if production.state_hash != research.state_hash:
        raise ParityError("state_hash mismatch — the two paths were not given "
                          "the same portfolio state; parity is undefined")

    out: list[Divergence] = []
    for key in sorted(set(production.rows) | set(research.rows), key=repr):
        p = production.rows.get(key)
        r = research.rows.get(key)
        if p is None or r is None:
            out.append(Divergence(key, "<row-presence>",
                                  p is not None, r is not None))
            continue
        for col in columns:
            if col not in p or col not in r:
                out.append(Divergence(key, col,
                                      p.get(col, "<missing>"), r.get(col, "<missing>")))
                continue
            if not _equal(p[col], r[col], float_tol=float_tol):
                out.append(Divergence(key, col, p[col], r[col]))
    return out


def assert_parity(production: DecisionSnapshot,
                  research: DecisionSnapshot,
                  columns: Sequence[str] = PARITY_COLUMNS,
                  *,
                  float_tol: float = 0.0) -> None:
    div = compare_decisions(production, research, columns, float_tol=float_tol)
    if div:
        raise ParityError(f"{len(div)} divergence(s): "
                          + "; ".join(str(d) for d in div[:10]))


# --- The two rev_accel definitions, extracted verbatim for drift demonstration.
# Same name, same stated concept, different formula. Kept here ONLY as the
# harness's live negative control (B-09 finding F-B); neither is B0's definition.

def rev_accel_b_leg(yoys: Sequence[float]) -> float:
    """scripts/universe_screen_daily.py:286-290 — latest YoY minus 3-month mean."""
    s = [v for v in yoys if v is not None and not math.isnan(v)][-3:]
    if len(s) < 3:
        return math.nan
    return s[-1] - (sum(s) / len(s))


def rev_accel_a_leg(yoys: Sequence[float]) -> float:
    """core/data_provider.py:1003-1006 — 3-month mean minus prior 3-month mean."""
    s = [v for v in yoys if v is not None and not math.isnan(v)]
    if len(s) < 6:
        return math.nan
    return sum(s[-3:]) / 3 - sum(s[-6:-3]) / 3
