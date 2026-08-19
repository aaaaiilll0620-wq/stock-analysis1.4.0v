# -*- coding: utf-8 -*-
"""B0.2 · the frozen 0050 benchmark construction protocol (M-3 ruling B1-B12).

The V-4 gate-1 benchmark -- `0050 buy-and-hold`, dividend-inclusive, frozen cost
model on its own real trading events -- had an IDENTITY in the Master but no
CONSTRUCTION. Six outcome-relevant choices were undetermined, and because gate 1
is a strict inequality and the single primary hypothesis, each of them was a free
parameter sitting directly on the primary gate. The M-3 ruling
`benchmark_construction_semantics` closed that gap by adjudication, classified as
EVALUATION_PROTOCOL_COMPLETION: not a strategy change, and decided BEFORE any
retrospective performance observation.

This module is the machine-readable record of that ruling. It states the rules
and implements the one piece that is pure arithmetic (B3's share/cash solve). It
deliberately owns NO data: the benchmark panel does not exist yet, and the
sufficiency contract below is what refuses to pretend otherwise.

WHAT IS FROZEN HERE, AND WHAT IS NOT
------------------------------------
B1-B7 are frozen semantics, transcribed from the ruling. B4 in particular is
NEWLY frozen in B0.2 and must never be described as having been explicit in
v1.26 -- the ruling says so in terms, and `CONSTRUCTION_RULES` records it.

`REQUIRED_LINEAGE_FIELDS` is DERIVED from B1-B7 rather than chosen: each entry
names the rule that needs it. That is what makes
`assert_benchmark_lineage_sufficient` a conformance check and not a wishlist.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.b0_cost_model import (
    COMMISSION_RATE, IMPACT_K, MIN_FEE, TAX_RATE, child_order_cost,
)

BENCHMARK_SECURITY = "0050"
BENCHMARK_IDENTITY = "0050 buy-and-hold, dividend-inclusive"
BENCHMARK_IDENTITY_CHANGED_IN_B0_2 = False
BENCHMARK_PROTOCOL_STATUS = "EVALUATION_PROTOCOL_COMPLETION"

# B2. Frozen initial benchmark cash.
C_REF = 2_000_000.0
BENCHMARK_CASH_EARNS_INTEREST = False

# B3 / B5. The benchmark's only real trading event is its initial buy.
BUY_TAX_RATE = 0.0
TERMINAL_TREATMENT = "MARK_TO_MARKET"
TERMINAL_LIQUIDATION = False

# B4. Newly frozen in B0.2, NOT explicit in v1.26.
APPLY_B0_ADV_CAPACITY_THROTTLE_TO_BENCHMARK = False
B4_NEWLY_FROZEN_IN_B0_2 = True

# B7.
DIVIDEND_REINVESTED = False
TOTAL_RETURN_SERIES_IS_ADMISSIBLE = False

# R1. Under the frozen economics -- cash earns no interest, dividends are never
# reinvested, the benchmark makes no post-initial-buy discretionary trades, and
# both cash and receivables enter NAV at face -- moving a fixed amount from
# receivable to cash changes classification and nothing else. So the historical
# payment date is an audit convenience, not a gate-1 input.
DIVIDEND_PAYMENT_DATE_CLASSIFICATION = "OPTIONAL_NON_OUTCOME_AUDIT_FIELD"
PAYMENT_DATE_IS_OUTCOME_REQUIRED = False

# R2. With no authoritative payment date the receivable is simply established at
# the ex-date and carried at face -- possibly past the terminal boundary. That is
# the honest state, and it is wealth-identical to any later crediting.
UNPAID_RECEIVABLE_MAY_REMAIN_OUTSTANDING = True

# R4. The split is NOT economically vacuous. It is vacuous only for the 2014
# sigma20d/ADV20 statistics, which are eleven years earlier; for buy-and-hold
# wealth the holder ledger must carry it.
SHARE_UNIT_EVENTS_ARE_OUTCOME_REQUIRED = True

CONSTRUCTION_RULES: dict[str, str] = {
    "B1": ("Initial timing. The benchmark starts with cash at the same economic "
           "origin as B0 and buys at the same canonical first executable trading "
           "timestamp used by B0 period 1, at the same canonical execution-price "
           "convention an ordinary B0 buy would use at that timestamp, sourced "
           "from the sealed 0050 benchmark lineage. NOT decision-date close, NOT "
           "source inception, NOT month-start, NOT an independently chosen date."),
    "B2": ("Initial capital. initial benchmark cash = C_ref = NT$2,000,000. "
           "Benchmark cash earns no interest."),
    "B3": ("Initial share/cash solve. Integer shares, odd-lot-capable ledger "
           "semantics. Take the maximum non-negative integer q with "
           "q*px + explicit_fee(q*px) + impact(q*px) <= available cash. Buy tax "
           "= 0. No borrowing. Residual stays benchmark cash. Dividend cash is "
           "not reinvested."),
    "B4": ("Capacity. B0's 1% ADV20 child-order throttle does NOT apply to the "
           "benchmark. The benchmark has one initial real buy event, priced by "
           "the frozen cost model using 0050's OWN adv20 and sigma20d. NEWLY "
           "FROZEN IN B0.2 -- this was not explicit in v1.26 and must not be "
           "represented as though it were."),
    "B5": ("Terminal treatment. Mark-to-market at the same canonical terminal "
           "valuation timestamp B0 strategy net wealth uses. No benchmark-only "
           "terminal liquidation, therefore no terminal sell commission, "
           "transaction tax or sell impact is charged merely to close the "
           "evaluation."),
    "B6": ("Missing sessions. Required benchmark trade/valuation observations "
           "must exist on the exact canonical required sessions. No "
           "interpolation, forward fill, backward fill or future inference. A "
           "missing required dependency makes gate 1 NON-EVALUABLE and must "
           "fail loud."),
    "B7": ("Dividends. Ex-date entitlement -> receivable -> cash at payment "
           "date -> NOT reinvested. A reinvesting total-return series is not an "
           "admissible substitute for benchmark wealth construction."),
}


@dataclass(frozen=True)
class LineageField:
    """One field a benchmark panel must carry, and the rule that requires it."""
    field: str
    required_by: str
    why: str


# DERIVED from B1-B7. Each entry names its rule; none is here by preference.
REQUIRED_LINEAGE_FIELDS: tuple[LineageField, ...] = (
    LineageField("open", "B1",
                 "the initial purchase uses B0's canonical execution-price "
                 "convention at the first executable timestamp"),
    LineageField("close", "B4/B5",
                 "raw close drives sigma20d and every mark-to-market valuation"),
    LineageField("volume", "B4",
                 "adv20 = mean(close * volume) over the last 20 observed sessions"),
    LineageField("dividend_ex_date", "B7", "creates the receivable"),
    LineageField("dividend_cash_per_share", "B7", "sizes the receivable"),
    LineageField("share_unit_effective_date", "R4/R6",
                 "the session on which the holder share count changes"),
    LineageField("holder_multiplier", "R4/R6",
                 "the factor applied to the holder share count, exactly once"),
)

# R1/R8. Recorded so its absence is a known, ruled state rather than an omission
# nobody noticed -- and so that a later acquisition has somewhere to land.
OPTIONAL_AUDIT_FIELDS: tuple[LineageField, ...] = (
    LineageField("dividend_payment_date", "R1",
                 "reclassifies a receivable as cash; wealth-neutral under B2/B7, "
                 "so it is an audit field and not a gate-1 input"),
)


class BenchmarkLineageInsufficient(RuntimeError):
    """B6: a required benchmark dependency is absent. Gate 1 is non-evaluable."""


class BenchmarkConstructionError(RuntimeError):
    """A benchmark construction rule was violated."""


def solve_initial_shares(execution_price: float, available_cash: float,
                         sigma20d: float, adv20: float, *,
                         data_as_of: str, execution_date: str) -> dict:
    """B3 · the maximum affordable integer share count, fee and impact included.

    Impact is superlinear in value (V^1.5), so this is not a division: the
    largest affordable q is found by taking the fee-free upper bound and walking
    down until the full frozen cost of the order fits. Walking DOWN from a proven
    upper bound is what makes the result the maximum rather than merely a
    feasible one -- and the loop is bounded because every step strictly reduces q.

    Buy tax is zero (B3), which is the frozen cost model's own `side="buy"`
    behaviour rather than a benchmark-specific exemption.
    """
    if not math.isfinite(execution_price) or execution_price <= 0:
        raise BenchmarkConstructionError(
            "B1: execution price must be finite and > 0, got %r" % execution_price)
    if not math.isfinite(available_cash) or available_cash < 0:
        raise BenchmarkConstructionError(
            "B2: available cash must be finite and >= 0, got %r" % available_cash)

    q = int(available_cash // execution_price)      # fee-free upper bound
    while q > 0:
        value = q * execution_price
        cost = child_order_cost(value, "buy", sigma20d, adv20,
                                data_as_of=data_as_of,
                                execution_date=execution_date,
                                execution_confirmed=True)
        if cost.transaction_tax != 0.0:             # B3, asserted not assumed
            raise BenchmarkConstructionError(
                "B3: buy tax must be 0, cost model returned %r"
                % cost.transaction_tax)
        if value + cost.total <= available_cash:
            return {"shares": q, "execution_price": float(execution_price),
                    "gross_value": value,
                    "explicit_fee": cost.explicit_fee,
                    "impact": cost.impact,
                    "transaction_tax": cost.transaction_tax,
                    "total_cost": cost.total,
                    "residual_cash": available_cash - value - cost.total,
                    "zero_sigma_fill": cost.zero_sigma_fill}
        q -= 1
    return {"shares": 0, "execution_price": float(execution_price),
            "gross_value": 0.0, "explicit_fee": 0.0, "impact": 0.0,
            "transaction_tax": 0.0, "total_cost": 0.0,
            "residual_cash": float(available_cash), "zero_sigma_fill": False}


def derive_holder_multiplier(prev_close: float, resumption_close: float,
                             resumption_change: float) -> float:
    """R6 · the multiplier, reproducible from the admitted TWSE lineage alone.

    TWSE reopens a split security quoting the day's change against its OWN
    adjusted prior reference, so that reference is `close - change` and the
    holder multiplier is `prev_close / reference`. Nothing here consults a
    benchmark or strategy quantity, which is what R6 requires; the price jump
    itself is never used, because it also contains the market's movement across
    the suspension.
    """
    reference = float(resumption_close) - float(resumption_change)
    if reference <= 0:
        raise BenchmarkConstructionError(
            "R6: TWSE adjusted reference is %r; a multiplier cannot be derived"
            % reference)
    raw = float(prev_close) / reference
    m = round(raw)
    if abs(raw - m) >= 0.01 or m < 2:
        raise BenchmarkConstructionError(
            "R6: %r is not an integer holder multiplier within tolerance; "
            "refusing to round a number this specification cannot justify" % raw)
    if abs(float(prev_close) / m - reference) > 0.05:      # one tick
        raise BenchmarkConstructionError(
            "R6: integer multiplier %d does not reproduce the TWSE reference "
            "%.4f from prev_close %.4f" % (m, reference, prev_close))
    return float(m)


@dataclass(frozen=True)
class BenchmarkLedger:
    """R5 · the two transitions are different shapes and stay different.

    A cash distribution moves value into a claim and never touches the share
    count. A share-unit split multiplies the share count and creates no income.
    Collapsing them -- which is exactly what an adjusted or total-return price
    series does -- makes both unrecoverable.
    """
    shares: int
    cash: float = 0.0
    receivable: float = 0.0
    applied_share_unit_events: tuple = ()

    def wealth(self, raw_close: float) -> float:
        """Raw mark price, never an adjusted one (B5/R4)."""
        return self.shares * float(raw_close) + self.cash + self.receivable


def apply_share_unit_event(ledger: BenchmarkLedger, event_id: str,
                           multiplier: float) -> BenchmarkLedger:
    """R4/R7 · q -> q*multiplier, exactly once. No income, no receivable."""
    from dataclasses import replace

    if event_id in ledger.applied_share_unit_events:
        raise BenchmarkConstructionError(
            "R7: share-unit event %s has already been applied to this ledger; "
            "applying it twice would silently multiply the holding again"
            % event_id)
    if multiplier <= 0:
        raise BenchmarkConstructionError("R4: multiplier must be > 0")
    shares = ledger.shares * multiplier
    if abs(shares - round(shares)) > 1e-9:
        raise BenchmarkConstructionError(
            "R4: %r x %r is not a whole number of shares" % (ledger.shares, multiplier))
    return replace(ledger, shares=int(round(shares)),
                   applied_share_unit_events=tuple(ledger.applied_share_unit_events)
                   + (event_id,))


def apply_dividend_ex_date(ledger: BenchmarkLedger,
                           cash_per_unit: float) -> BenchmarkLedger:
    """B7/R5 · entitlement -> receivable at face. Share count untouched."""
    from dataclasses import replace

    if cash_per_unit <= 0:
        raise BenchmarkConstructionError("B7: cash_per_unit must be > 0")
    return replace(ledger,
                   receivable=ledger.receivable + ledger.shares * float(cash_per_unit))


def apply_dividend_payment(ledger: BenchmarkLedger, amount: float) -> BenchmarkLedger:
    """B7/R2 · receivable -> cash at face. Wealth-neutral by construction.

    Never reinvested (B7), and the benchmark holds no interest-bearing cash (B2),
    so this is a reclassification. R2 permits it to never happen at all.
    """
    from dataclasses import replace

    if amount < 0 or amount > ledger.receivable + 1e-9:
        raise BenchmarkConstructionError(
            "B7: cannot credit %r against a receivable of %r"
            % (amount, ledger.receivable))
    return replace(ledger, cash=ledger.cash + float(amount),
                   receivable=ledger.receivable - float(amount))


def lineage_field_status(available_fields) -> dict:
    """Which B1-B7 dependencies a candidate source actually carries."""
    have = {str(f).strip().lower() for f in (available_fields or ())}

    def present(name: str) -> bool:
        return any(name in h for h in have)

    return {f.field: {"required_by": f.required_by, "why": f.why,
                      "present": present(f.field)}
            for f in REQUIRED_LINEAGE_FIELDS}


def assert_benchmark_lineage_sufficient(available_fields,
                                        source: str = "") -> dict:
    """B6 · fail loud on a missing required dependency. Never fill it in."""
    status = lineage_field_status(available_fields)
    missing = sorted(k for k, v in status.items() if not v["present"])
    # R8 states it separately because it is the dependency that was nearly
    # missed: it is invisible in the ex-rights table and only shows up if
    # something goes looking for holder-unit transformations specifically.
    if "share_unit_effective_date" in missing or "holder_multiplier" in missing:
        status.setdefault("_note", {})
    if missing:
        detail = "; ".join(
            "%s (required by %s: %s)" % (m, status[m]["required_by"], status[m]["why"])
            for m in missing)
        raise BenchmarkLineageInsufficient(
            "B6: benchmark lineage%s is missing %d required dependency(ies) — %s. "
            "Gate 1 is NON-EVALUABLE. B6 forbids interpolation, forward fill, "
            "backward fill and future inference, and B7 forbids substituting a "
            "reinvesting total-return series, so there is no admissible way to "
            "supply these from what is present."
            % ((" %s" % source) if source else "", len(missing), detail))
    return status


def assert_strategy_wealth_is_mark_to_market() -> dict:
    """B5's precondition, mechanically, rather than as a recollection.

    B5 says: if B0 strategy net wealth is itself a forced terminal liquidation
    rather than a mark, STOP and report the contradiction. `mark_portfolio`
    values cash + marked positions + receivables and no route, decision or
    execution path closes positions to end the window, so the benchmark's
    mark-to-market terminal treatment is symmetric with the strategy's.
    """
    import inspect

    from core.b0_state import mark_portfolio

    src = inspect.getsource(mark_portfolio)
    if "port_value=float(portfolio.cash) + sum(position_values.values())" not in src:
        raise BenchmarkConstructionError(
            "B5: core.b0_state.mark_portfolio no longer computes net wealth as "
            "cash + marked positions + receivables. B5's symmetry premise must "
            "be re-established before the benchmark's terminal treatment can be "
            "called symmetric with the strategy's.")
    return {"strategy_terminal_treatment": "MARK_TO_MARKET",
            "benchmark_terminal_treatment": TERMINAL_TREATMENT,
            "symmetric": True, "contradiction": False}


FROZEN_CONSTANTS = {
    "C_REF": C_REF,
    "COMMISSION_RATE": COMMISSION_RATE,
    "MIN_FEE": MIN_FEE,
    "TAX_RATE": TAX_RATE,
    "BUY_TAX_RATE": BUY_TAX_RATE,
    "IMPACT_K": IMPACT_K,
    "BENCHMARK_CASH_EARNS_INTEREST": BENCHMARK_CASH_EARNS_INTEREST,
    "DIVIDEND_REINVESTED": DIVIDEND_REINVESTED,
    "TERMINAL_TREATMENT": TERMINAL_TREATMENT,
    "APPLY_B0_ADV_CAPACITY_THROTTLE_TO_BENCHMARK":
        APPLY_B0_ADV_CAPACITY_THROTTLE_TO_BENCHMARK,
}
