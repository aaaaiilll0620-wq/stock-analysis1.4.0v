"""Layer 4 of the canonical core (§8.7): targets -> orders -> fills -> receipts.

Responsibility boundary, quoted from §8.7:

    b0_execution   only: validated pre-trade state + target state -> sell-first
                         -> pending_exit -> buy -> 1% ADV caps -> share ledger
                         -> b0_cost_model -> receipts
                   the corporate-action engine MUST be its upstream, and must not
                   hide inside it as a scatter of `if event_type`

So this module contains no event-kind branch at all. It receives a portfolio
state that `core.b0_corporate_actions` has already transformed and validated
(§6.1: that stage is mandatory before any valuation or ordering), and it receives
the tradability determination rather than inferring one. `sigma20d == 0` and
`adv20 > 0` are not evidence that a name can trade (§7.5) — a suspended or
limit-locked security can show both.

The frozen rebalance-day order (§6.4), which may not be permuted:

    1. generate required sells
    2. execute them within that day's sell capacity (X_sell = 1% of ADV20)
    3. whatever did not fill becomes `pending_exit`
    4. buy using cash that has ACTUALLY been realised

Step 4 is the rule that makes the other three matter. Financing a new position
with the expected proceeds of a sale that did not fill is leverage arriving
through the back door, and §6.4 forbids both it and negative cash outright. The
asymmetry that follows is execution reality rather than a modelling error: entry
eligibility requires a full position to be establishable within one session
(§4.2), while an exit is allowed to take as many sessions as the 1% cap needs.
A portfolio can therefore be temporarily under-invested while still holding
residual old names, and §9.7 requires that to be reported rather than smoothed.

Costs come from `core.b0_cost_model` unchanged — it is reused, never reimplemented
here. Its three components stay separated all the way onto the receipt (§7.2,
S-6): collapsing them into one rate would make "the cost assumption was wrong"
indistinguishable from "the strategy was wrong".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from core.b0_cost_model import CostBreakdown, aggregate_fills, child_order_cost
from core.b0_state import PortfolioState

SIDES: tuple[str, ...] = ("buy", "sell")

# C-16 (master omission correction, not a new ruling). Every decision date resets
# each surviving position to its 5% target:
#
#     target_value_i(t) = 0.05 * port_value(t)
#     order_delta_i     = target_shares_i - current_shares_i
#
# subject to the sell-first / cash / 1% ADV / pending_exit constraints below. B-06
# and B-12 already specified `compute_order_intent` this way and B-14 describes a
# surviving holding as producing a small delta rebalance after a month of drift;
# the master preregistration simply never carried it across. B0 is NOT
# buy-and-hold-until-dropped.
#
# The alternative reading is not kept as a selectable branch. An unreachable
# option is documentation; a reachable one is a free parameter waiting for a
# call site.
TARGET_DRIFT_POLICY = "rebalance_to_5pct_each_decision"
DRIFT_POLICIES: tuple[str, ...] = (TARGET_DRIFT_POLICY,)

# C-32: rank-first fill. After the sells, the buys are processed in Selection
# rank order, highest score first, each one limited by three things at once —
# its target shortfall, the 1% ADV cap, and the cash that has actually been
# realised. No borrowing, and no proportional scaling.
#
# Pro-rata is removed rather than left selectable. Scaling every target by a
# common factor would silently convert a cash shortfall into a WEIGHT decision:
# twenty names at 4% is a different portfolio from sixteen names at 5% plus
# cash, and §5 already fixed which of those B0 is.
BUY_PRIORITY = "rank"
BUY_PRIORITIES: tuple[str, ...] = (BUY_PRIORITY,)

# C-34: floor to a whole share. Odd lots are enabled (§6.3), so the smallest
# tradable unit is one share and `floor` is the only rounding that cannot breach
# `w_max`. Nearest rounding could push a high-priced name above the 5% hard cap
# by up to half a share's value; the rounding remainder stays in cash, which is
# the same treatment §5 gives every other shortfall.
SHARE_ROUNDING = "floor"
SHARE_ROUNDINGS: tuple[str, ...] = (SHARE_ROUNDING,)

# C-27. A `pending_exit` residual is re-capped against the executing session's
# OWN ADV20 every day, taken as of that session's prior close. This follows from
# two clauses that were already frozen and only needed stating together: §6.4
# caps each day's traded value at 1% of ADV20 and carries the remainder forward
# to zero, and §7.3 charges each execution day with that day's own pre-execution
# sigma20d/ADV20. Freezing the cap at the first day's ADV20 instead would let a
# name whose liquidity collapsed keep selling at its old capacity.
PENDING_EXIT_CAP_BASIS = "per_session_adv20_as_of_prior_close"


class ExecutionError(RuntimeError):
    """Fail-loud: an execution input the canonical core must not absorb."""


# --- orders -------------------------------------------------------------------

@dataclass(frozen=True)
class ChildOrder:
    """One strategy child order for one security on one session.

    `MIN_FEE` is charged per child order, not per fill (§7.3, G14-2), so fills
    are aggregated before the cost model is called — a child order split into
    five fills must not pay five minimum fees.
    """
    stock_id: str
    side: str
    shares: int
    price: float
    execution_date: str

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ExecutionError(f"side must be one of {SIDES}, got {self.side!r}")
        if not isinstance(self.shares, int) or self.shares <= 0:
            raise ExecutionError(
                f"§6.3: shares must be a positive whole number, got {self.shares!r}")
        if not math.isfinite(self.price) or self.price <= 0:
            raise ExecutionError(f"price must be finite and > 0, got {self.price!r}")

    @property
    def value(self) -> float:
        return self.shares * self.price


@dataclass(frozen=True)
class Receipt:
    """§9.7 / S-6: the three cost components stay apart, per child order."""
    stock_id: str
    side: str
    shares: int
    price: float
    value: float
    execution_date: str
    explicit_fee: float
    transaction_tax: float
    impact: float
    zero_sigma_fill: bool

    @property
    def total_cost(self) -> float:
        return self.explicit_fee + self.transaction_tax + self.impact

    @property
    def cash_delta(self) -> float:
        """Signed effect on cash: proceeds net of costs, or outlay plus costs."""
        if self.side == "sell":
            return self.value - self.total_cost
        return -(self.value + self.total_cost)


def _receipt(order: ChildOrder, cost: CostBreakdown) -> Receipt:
    return Receipt(
        stock_id=order.stock_id, side=order.side, shares=order.shares,
        price=order.price, value=order.value, execution_date=order.execution_date,
        explicit_fee=cost.explicit_fee, transaction_tax=cost.transaction_tax,
        impact=cost.impact, zero_sigma_fill=cost.zero_sigma_fill)


# --- caps ---------------------------------------------------------------------

def order_cap_value(adv20: float, cap_rate: float) -> float:
    """§6.4: a single day's buy or sell value may not exceed 1% of ADV20.

    §4.2 requires this to be separate code from the eligibility gate. They ask
    different questions — "can this name carry a standard position at all" versus
    "is this particular order too large today" — and merging them turns a
    capacity screen into a fill rule.
    """
    if not math.isfinite(adv20) or adv20 < 0:
        raise ExecutionError(f"adv20 must be finite and >= 0, got {adv20!r}")
    return float(adv20) * float(cap_rate)


def cap_shares(cap_value: float, price: float) -> int:
    if not math.isfinite(price) or price <= 0:
        raise ExecutionError(f"price must be finite and > 0, got {price!r}")
    return int(math.floor(max(cap_value, 0.0) / price))


def target_shares(target_value: float, price: float, *, share_rounding: str) -> int:
    """Convert a target value into whole shares (§6.3, C-34).

        target_shares = floor(target_value / reference_price)

    `w_max` = 5% is a HARD cap on the executed position, not only on the target,
    which is what makes `floor` the only admissible rounding: nearest could carry
    a high-priced name above the cap by up to half a share's value. The remainder
    stays in cash (§5), like every other shortfall.
    """
    if share_rounding != SHARE_ROUNDING:
        raise ExecutionError(
            f"C-34: share rounding is frozen to {SHARE_ROUNDING!r}; got "
            f"{share_rounding!r}. Nearest rounding can breach the 5% hard cap, "
            f"and the rounding shortfall belongs in cash.")
    if not math.isfinite(price) or price <= 0:
        raise ExecutionError(f"price must be finite and > 0, got {price!r}")
    raw = float(target_value) / float(price)
    if raw <= 0:
        return 0
    return int(math.floor(raw))


# --- the rebalance-day sequence ----------------------------------------------

@dataclass(frozen=True)
class SessionResult:
    execution_date: str
    receipts: tuple[Receipt, ...]
    shares_after: Mapping[str, int]
    cash_after: float
    pending_exit_after: Mapping[str, int]
    adv_cap_shortfall_value: float
    intraday_steps: tuple[str, ...]
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    @property
    def zero_sigma_fills(self) -> int:
        return sum(1 for r in self.receipts if r.zero_sigma_fill)

    @property
    def turnover_value(self) -> float:
        return sum(r.value for r in self.receipts)


def required_sells(pre_trade: PortfolioState,
                   target_share_counts: Mapping[str, int],
                   *, drift_policy: str) -> dict[str, int]:
    """Step 1 of §6.4. Carried `pending_exit` is always part of the requirement.

    `drift_policy` stays an explicit argument even though C-16 froze it to a
    single value: a call site that names the policy it believes it is running
    cannot silently inherit a different one later.
    """
    if drift_policy != TARGET_DRIFT_POLICY:
        raise ExecutionError(
            f"C-16: target drift policy is frozen to {TARGET_DRIFT_POLICY!r}; got "
            f"{drift_policy!r}. Every decision date resets a surviving position "
            f"to its 5% target (order_delta = target_shares - current_shares). "
            f"Hold-until-dropped is a different strategy, not a variant.")

    sells: dict[str, int] = {}
    for sid, held in pre_trade.shares.items():
        wanted = int(target_share_counts.get(sid, 0))
        if wanted <= 0:
            sells[sid] = held
            continue
        if held > wanted:
            # Drift trim: the surviving position is brought back to target.
            sells[sid] = held - wanted
    for sid, qty in pre_trade.pending_exit.items():
        sells[sid] = max(sells.get(sid, 0), int(qty))
    return {k: v for k, v in sorted(sells.items()) if v > 0}


def _affordable_shares(cash: float, price: float, max_shares: int,
                       sigma20d: float, adv20: float,
                       data_as_of: str, execution_date: str) -> int:
    """Largest whole share count whose value PLUS costs fits in realised cash.

    Not a modelling choice: §6.4 forbids negative cash, and a buy's fee and
    impact are paid out of the same cash as its value. Costs rise with value, so
    the feasible count is found by bisection rather than by assuming a rate.
    """
    if max_shares <= 0:
        return 0

    def outlay(n: int) -> float:
        value = n * price
        c = child_order_cost(value, "buy", sigma20d, adv20, data_as_of,
                             execution_date, execution_confirmed=True)
        return value + c.total

    if outlay(max_shares) <= cash:
        return max_shares
    lo, hi = 0, max_shares
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if outlay(mid) <= cash:
            lo = mid
        else:
            hi = mid - 1
    return lo


def execute_session(*,
                    execution_date: str,
                    data_as_of: str,
                    pre_trade: PortfolioState,
                    target_share_counts: Mapping[str, int],
                    prices: Mapping[str, float],
                    adv20: Mapping[str, float],
                    sigma20d: Mapping[str, float],
                    untradable: frozenset[str],
                    drift_policy: str,
                    buy_priority: str,
                    buy_order: Sequence[str],
                    x_sell: float,
                    x_buy: float) -> SessionResult:
    """One trading session of the frozen §6.4 sequence, sells strictly first.

    `prices` are that session's permitted execution prices (§6.5: `open(t+1)` on
    the decision's following session, and the following session again for each
    carried `pending_exit` day). `data_as_of` is the prior close: G14-1 requires
    the sigma20d/ADV20 window to end strictly before the execution day, and the
    cost model enforces it independently.

    `untradable` is the execution-layer determination, passed in rather than
    inferred (§7.5). Names in it can neither be sold nor bought today; a required
    sell that cannot execute carries forward as `pending_exit`, which remains a
    held position.
    """
    if buy_priority != BUY_PRIORITY:
        raise ExecutionError(
            f"C-32: cash-constrained buys are filled in Selection rank order; "
            f"got buy_priority={buy_priority!r}. Proportional scaling would turn "
            f"a cash shortfall into a weight decision, and §5 already fixed the "
            f"weights.")
    if str(data_as_of) >= str(execution_date):
        raise ExecutionError(
            f"G14-1: data_as_of={data_as_of} must be strictly earlier than "
            f"execution_date={execution_date}")

    steps: list[str] = ["start_of_trading_day"]
    # The corporate-action transition already happened upstream (§6.1 O-A); this
    # module records the step it consumes rather than performing a dispatch.
    steps.append("apply_known_effective_corporate_actions")
    steps.append("establish_tradable_holdings")
    steps.append("obtain_permitted_execution_price")

    shares = dict(pre_trade.shares)
    cash = float(pre_trade.cash)
    receipts: list[Receipt] = []
    shortfall_value = 0.0
    carried: dict[str, int] = {}

    def _px(sid: str) -> float:
        try:
            px = float(prices[sid])
        except KeyError:
            raise ExecutionError(
                f"§6.5: no permitted execution price for {sid!r} on "
                f"{execution_date}. An order without a price does not become a "
                f"fill at some other number.") from None
        if not math.isfinite(px) or px <= 0:
            raise ExecutionError(f"price for {sid!r} must be finite and > 0")
        return px

    # --- steps 1-3: sells, capped, remainder carried --------------------------
    wanted_sells = required_sells(pre_trade, target_share_counts,
                                  drift_policy=drift_policy)
    steps.append("execute_child_orders")
    for sid, qty in wanted_sells.items():
        held = int(shares.get(sid, 0))
        qty = min(qty, held)
        if qty <= 0:
            continue
        if sid in untradable:
            carried[sid] = qty
            continue
        px = _px(sid)
        cap = cap_shares(order_cap_value(adv20.get(sid, 0.0), x_sell), px)
        fill = min(qty, cap)
        if fill < qty:
            shortfall_value += (qty - fill) * px
            carried[sid] = qty - fill
        if fill <= 0:
            continue
        value = aggregate_fills([fill * px])
        cost = child_order_cost(value, "sell", float(sigma20d.get(sid, 0.0)),
                                float(adv20[sid]), data_as_of, execution_date,
                                execution_confirmed=True)
        order = ChildOrder(sid, "sell", fill, px, execution_date)
        r = _receipt(order, cost)
        receipts.append(r)
        cash += r.cash_delta
        shares[sid] = held - fill
        if shares[sid] == 0:
            del shares[sid]

    if cash < 0:
        raise ExecutionError(
            f"§6.4: sell costs drove cash to {cash}. B0 does not borrow, and a "
            f"negative balance here means the pre-trade state was already "
            f"infeasible.")

    # --- step 4: buys, funded only by cash that has actually been realised ----
    buys: dict[str, int] = {}
    for sid, wanted in target_share_counts.items():
        if sid in untradable:
            continue
        need = int(wanted) - int(shares.get(sid, 0))
        if need > 0:
            buys[sid] = need
    if buys:
        # C-32: Selection rank order, highest score first. `buy_order` is the
        # ranked list the decision layer produced; anything the caller left out
        # of it is appended deterministically rather than dropped, so a name can
        # never be silently skipped by an incomplete ranking.
        ordered = [s for s in buy_order if s in buys]
        ordered += [s for s in sorted(buys) if s not in ordered]

        for sid in ordered:
            need = int(buys.get(sid, 0))
            if need <= 0:
                continue
            px = _px(sid)
            cap = cap_shares(order_cap_value(adv20.get(sid, 0.0), x_buy), px)
            n = min(need, cap)
            if n < need:
                shortfall_value += (need - n) * px
            n = _affordable_shares(cash, px, n, float(sigma20d.get(sid, 0.0)),
                                   float(adv20.get(sid, 0.0)), data_as_of,
                                   execution_date)
            if n <= 0:
                continue
            value = aggregate_fills([n * px])
            cost = child_order_cost(value, "buy", float(sigma20d.get(sid, 0.0)),
                                    float(adv20[sid]), data_as_of, execution_date,
                                    execution_confirmed=True)
            order = ChildOrder(sid, "buy", n, px, execution_date)
            r = _receipt(order, cost)
            receipts.append(r)
            cash += r.cash_delta
            if cash < 0:
                raise ExecutionError(
                    f"§6.4: buying {n} {sid} drove cash to {cash}; unrealised "
                    f"proceeds must never fund a position.")
            shares[sid] = int(shares.get(sid, 0)) + n

    steps.append("apply_costs")
    steps.append("end_of_day_state")

    from core.b0_master_prereg import assert_intraday_order
    assert_intraday_order(steps)

    pending = {k: int(v) for k, v in sorted(carried.items())
               if int(v) > 0 and k in shares}
    return SessionResult(
        execution_date=execution_date,
        receipts=tuple(receipts),
        shares_after=dict(sorted(shares.items())),
        cash_after=cash,
        pending_exit_after=pending,
        adv_cap_shortfall_value=shortfall_value,
        intraday_steps=tuple(steps),
        diagnostics={
            "sells_requested": wanted_sells,
            "drift_policy": drift_policy,
            "buy_priority": buy_priority,
            "untradable": tuple(sorted(untradable)),
        },
    )


def cost_totals(receipts: Sequence[Receipt]) -> dict[str, float]:
    """§9.7: totals reported per component, never as one effective rate (§7.2)."""
    return {
        "explicit_fee": sum(r.explicit_fee for r in receipts),
        "transaction_tax": sum(r.transaction_tax for r in receipts),
        "impact": sum(r.impact for r in receipts),
        "zero_sigma_fills": sum(1 for r in receipts if r.zero_sigma_fill),
        "traded_value": sum(r.value for r in receipts),
    }
