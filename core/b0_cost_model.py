"""Frozen B0 cost model — explicit fee / transaction tax / market impact, kept apart.

Frozen by docs/B14_CostModel_Closure_Phase1_2026-08-17.md (P1-P6) and
docs/B14_CostModel_Closure_Phase2_Spec_2026-08-17.md.

Deliberately a NEW module: scripts/l4b_execution.py and
scripts/portfolio_simulator_lab.py belong to Frozen A and are preserved as an
audit trail, so their BUY_COST/SELL_COST constants are neither edited nor
deleted. B0 imports this module instead; the legacy constants are simply
unreachable from the B0 path.

Model, per strategy child order of value V, side, instrument i, execution day t:

    explicit_fee    = max(MIN_FEE, V * COMMISSION_RATE)
    transaction_tax = V * TAX_RATE            if side == "sell" else 0
    impact          = V * IMPACT_K * sigma20d * sqrt(V / adv20)
    total           = explicit_fee + transaction_tax + impact

The three components are reported separately and MUST NOT be collapsed into one
proportional rate: their sources of uncertainty differ (declared broker policy /
external tax law / external prior estimate). Collapsing them makes "the cost
assumption was wrong" indistinguishable from "the strategy was wrong".

DISCLOSURE (D14-1) — B0 models only a square-root market-impact proxy. Bid-ask
spread, tick-size effects and intraday execution effects are NOT separately
modelled. This field must therefore NOT be read as a complete implicit trading
cost, AND no claim may be made about the direction of its bias: IMPACT_K = 1.0 is
an order-one external-prior reference, not a Taiwan-market estimate, so the proxy
may over- or under-state true impact. Any conclusion quoting B0 cost figures must
carry this, and must not describe the modelled figure as a bound in either
direction.

G14-3 — this module prices orders; it does NOT decide whether an order can trade.
Callers must have obtained an execution-layer determination first. `sigma20d == 0`
or `adv20 > 0` are NOT evidence of tradability: a suspended or limit-locked name
can show both while being untradable, and the correct answer there is
"execution infeasible", not "filled at zero impact". Fabricating a zero-impact
fill for something that never traded is the failure this guard exists to prevent.

No tunable-parameter override entry point is provided, by design: an adjustable
knob here would become a second `composite_weights`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

# --- Frozen constants (B-14 Phase 1, P1/P2/P4) -------------------------------
COMMISSION_RATE = 0.001425   # P1: B0 reference commission rate, d = 1.0, no discount assumed
MIN_FEE = 20.0               # P2: B0 reference BROKER POLICY, not statute; round lot == odd lot
TAX_RATE = 0.003             # securities transaction tax, sell side only
IMPACT_K = 1.0               # P4: order-one external-prior reference.
                             #     NOT a Taiwan-market empirical estimate — do not describe it as one.

_SIDES = ("buy", "sell")


class CostModelError(ValueError):
    """Fail-loud: an input the model must not silently absorb."""


@dataclass(frozen=True)
class CostBreakdown:
    """Three components kept apart on purpose (see module docstring)."""

    explicit_fee: float
    transaction_tax: float
    impact: float
    # G14-3: set when sigma20d == 0, i.e. the execution layer asserted a fill on a
    # name showing zero measured 20-day volatility. Legitimate but unusual — it is
    # surfaced on the receipt so it can be audited, never silently absorbed.
    zero_sigma_fill: bool = False

    @property
    def total(self) -> float:
        return self.explicit_fee + self.transaction_tax + self.impact

    @property
    def effective_rate(self) -> float:
        """total / value is not derivable here; callers divide by their own V."""
        raise AttributeError(
            "effective_rate needs the order value; compute total / value at the call site."
        )


def aggregate_fills(fills: Iterable[float]) -> float:
    """G14-2: sum fills of ONE child order before any fee is computed.

    MIN_FEE is charged per strategy child order, not per individual fill.
    Charging it per fill would systematically overstate explicit cost (a child
    order split into 5 fills would pay 5 x MIN_FEE).
    """
    values = list(fills)
    if not values:
        raise CostModelError("aggregate_fills: empty fill list")
    total = 0.0
    for v in values:
        if not math.isfinite(v):
            raise CostModelError(f"aggregate_fills: non-finite fill value {v!r}")
        if v < 0:
            raise CostModelError(f"aggregate_fills: negative fill value {v!r}")
        total += float(v)
    if total <= 0:
        raise CostModelError("aggregate_fills: aggregated value must be > 0")
    return total


def _check_lookahead(data_as_of: str, execution_date: str) -> None:
    """G14-1: sigma20d / adv20 windows must end strictly before execution.

    This also fixes the reading of P5: "當日 sigma20D / ADV20" for multi-day
    pending_exit child orders means *as of the prior close*, never including the
    execution day's own volume or return.
    """
    if not data_as_of or not execution_date:
        raise CostModelError("G14-1: both data_as_of and execution_date are required")
    if str(data_as_of) >= str(execution_date):
        raise CostModelError(
            f"G14-1 execution-day look-ahead: data_as_of={data_as_of} must be strictly "
            f"earlier than execution_date={execution_date}"
        )


def child_order_cost(
    value: float,
    side: str,
    sigma20d: float,
    adv20: float,
    data_as_of: str,
    execution_date: str,
    *,
    execution_confirmed: bool,
) -> CostBreakdown:
    """Cost of ONE strategy child order. `value` must already be fill-aggregated.

    Multi-day executions (pending_exit) call this once per trading day, each with
    that day's own pre-execution sigma20d/adv20 and the actually-filled value.
    No decay parameter is introduced (P5).

    `execution_confirmed` (G14-3) is the caller's explicit assertion that the
    execution layer determined this child order actually traded. It is keyword-only
    and has no default precisely so that no call site can price a fill it never
    established. This module never infers tradability from sigma20d or adv20.
    """
    if execution_confirmed is not True:
        raise CostModelError(
            "G14-3: execution_confirmed must be True — the execution layer, not the "
            "cost model, decides tradability. Do not price an unestablished fill."
        )
    _check_lookahead(data_as_of, execution_date)

    if side not in _SIDES:
        raise CostModelError(f"side must be one of {_SIDES}, got {side!r}")
    if not math.isfinite(value) or value <= 0:
        raise CostModelError(f"value must be finite and > 0, got {value!r}")
    if not math.isfinite(adv20) or adv20 <= 0:
        raise CostModelError(f"adv20 must be finite and > 0, got {adv20!r}")
    if not math.isfinite(sigma20d) or sigma20d < 0:
        raise CostModelError(f"sigma20d must be finite and >= 0, got {sigma20d!r}")

    explicit_fee = max(MIN_FEE, value * COMMISSION_RATE)
    transaction_tax = value * TAX_RATE if side == "sell" else 0.0
    # sigma20d == 0 yields zero impact by the model's own definition. It is NOT
    # evidence the order was tradable (G14-3) — the execution layer already
    # asserted that. Flagged on the receipt so it stays auditable.
    impact = value * IMPACT_K * sigma20d * math.sqrt(value / adv20)

    return CostBreakdown(explicit_fee=explicit_fee,
                         transaction_tax=transaction_tax,
                         impact=impact,
                         zero_sigma_fill=(sigma20d == 0.0))


def child_order_cost_from_fills(
    fills: Sequence[float],
    side: str,
    sigma20d: float,
    adv20: float,
    data_as_of: str,
    execution_date: str,
    *,
    execution_confirmed: bool,
) -> CostBreakdown:
    """Convenience wrapper enforcing G14-2 ordering: aggregate, then charge."""
    return child_order_cost(aggregate_fills(fills), side, sigma20d, adv20,
                            data_as_of, execution_date,
                            execution_confirmed=execution_confirmed)


# --- G14-4: B0 must never reach the Frozen-A proportional-cost path -----------

LEGACY_COST_SYMBOLS = ("BUY_COST", "SELL_COST")
LEGACY_COST_MODULES = ("l4b_execution", "portfolio_simulator_lab")

# Entry points of the B0 production-reachable graph.
#
# NOT the registry. `core.b0_invariants.B0_ENTRY_MODULES` is the single one the
# five invariants actually run over, and P-1b extended it with the four canonical
# core layers. This tuple is kept only because B-14 named it; it is deliberately
# left as the cost model's own entry so that two lists cannot drift into
# disagreeing about what "reachable" means. Append route entries there, not here.
B0_ENTRY_MODULES = ("core.b0_cost_model",)


def min_fee_breakeven_value(commission_rate: float = COMMISSION_RATE,
                            min_fee: float = MIN_FEE) -> float:
    """Order value below which MIN_FEE binds. At B0 defaults: ~NT$14,035.09."""
    return min_fee / commission_rate
