# -*- coding: utf-8 -*-
"""§9.3 row ① — the eligible universe, equal weighted. Row ① ONLY.

WHAT ROW ① ANSWERS

`◆ − ①` is SELECTION ABILITY: what the strategy added over holding everything it
was allowed to hold. `◆ − ③` is OPPORTUNITY COST and answers a different
question. Conflating them is what an earlier "the selection layer has no alpha"
finding was retracted for -- an equal-weight book starts ~5.77pp/year behind 0050
before a single name is picked -- so this row is what stops this opening being
read the same wrong way.

CONSTRUCTION DECISIONS, MADE EXPLICIT BECAUSE §9.3 DOES NOT MAKE THEM

The Master gives row ① one line: "B0 eligibility 通過的全母體等權". Everything
below is therefore a recorded construction choice, not a frozen rule, and each
is stated here rather than buried:

  weights      1/n over that period's eligible set. NOT §5's fixed 5%: §5 governs
               the STRATEGY and explicitly forbids 1/n, which is precisely why
               `decision.target_portfolio` cannot be reused here. Row ① is a
               benchmark, and 1/n is what "等權" means.
  cadence      rebalanced every decision period, matching the strategy's, so the
               two rows see the same trading calendar and the same cost events.
  execution    the SAME `execute_session` the strategy uses -- same cost model
               (§9.3 requires it), same ADV cap, same odd-lot rounding, same
               `pending_exit` carry. A cheaper paper approximation would make the
               difference partly an artefact of two different execution layers.
  buy order    stock_id ascending. `execute_session` fills cash-constrained buys
               in `buy_order`; the strategy passes SelectionScore rank. Row ①
               must not, because importing the score into the no-selection
               benchmark is exactly the thing being measured.
  dividends    the same CA engine as the strategy (§9.3 line 317: the equal-weight
               universe must be dividend-inclusive and handled identically).

THE SKIP (user ruling, 2026-09-03)

Row ① holds ~370 names against the strategy's 21, and 68 of the window's 90
holder-side reorganization exits fall on securities that were eligible before
their boundary. 69 of those 90 have no disposition rule at all, so §6.1.12 would
fail closed and row ① would simply not exist.

Ruled: row ① converts an exposed, unreconstructible holder-side exit to cash at
the last observed close strictly before the boundary, and does not block. This
happens HERE, in non-normative evaluation code, applied ONLY to row ①. The
frozen engine is untouched and so is the completed strategy run -- neither could
be changed anyway, since B1's observation is spent and §1.4 has closed the
specification.

⚠ DISCLOSURE THAT MUST TRAVEL WITH ANY `◆ − ①`. The measured bias of pricing an
exit at the pre-boundary close is predominantly an UNDERSTATEMENT (§2.3(3):
stock legs 6 understate / 2 flatter, one flattering by 20%). Understating row ①
makes `◆ − ①` larger, i.e. it flatters the strategy's apparent selection
ability. That is the direction this reading is most vulnerable to, so every
disposal is logged with its period, quantity and portfolio weight rather than
summarised.
"""
from __future__ import annotations

import dataclasses as _dc

from core import b0_corporate_actions as ca
from core import b0_execution as execution
from core.b0_master_prereg import spec
from core.b0_state import PortfolioState

ROW1_BUY_ORDER = "stock_id_ascending"
ROW1_WEIGHTING = "1/n over the period's eligible set"
ROW1_UNRECONSTRUCTIBLE_DISPOSAL = "CASH_AT_PRE_BOUNDARY_CLOSE"


class Row1Error(RuntimeError):
    """Row ① could not be constructed. Never silently approximated."""


def exposed_unreconstructible(state, events, as_of):
    """Exits row ① is exposed to that the FROZEN rule does not already handle.

    Events inside `HXA_CASH_SCOPE` are left alone: the engine disposes of those
    itself, under a rule with its own measured bias and its own provenance. Only
    what would otherwise BLOCK is taken here.
    """
    out = []
    for ev in events:
        if ev.kind != "holder_side_reorganization_exit":
            continue
        if ev.reconstructibility != ca.NOT_RECONSTRUCTIBLE:
            continue
        if str(ev.stock_id) in ca.HXA_CASH_SCOPE:
            continue
        if str(ev.ex_or_effective_date) > str(as_of):
            continue
        if ev.canonical_event_id() in state.applied_ca_event_ids:
            continue
        if not ca.is_exposed(state, ev, as_of=as_of):
            continue
        out.append(ev)
    return out


def dispose_at_pre_boundary_close(state, ev, anchor, period, port_value):
    """The user's ruling, applied to ONE event. Returns (state, log) or refuses.

    Refusing (returning None) leaves §6.1.12 to fail closed exactly as before.
    A disposal with no price is a guess, and the ruling was to skip the blockers,
    not to invent numbers for them.
    """
    got = anchor(ev.stock_id, str(ev.ex_or_effective_date))
    if got is None:
        return None
    price, session = got
    q = ca.hxa_cash_quantity(state, ev.stock_id)
    proceeds = float(q) * float(price)

    shares = {k: v for k, v in state.shares.items() if k != ev.stock_id}
    pending = {k: v for k, v in state.pending_exit.items() if k != ev.stock_id}
    kept = tuple(r for r in state.security_receivables
                 if r.security_id != ev.stock_id)
    on_recv = tuple(x for x in state.pending_exit_on_receivable
                    if x != ev.stock_id)
    new = _dc.replace(state, cash=float(state.cash) + proceeds, shares=shares,
                      pending_exit=pending, security_receivables=kept,
                      pending_exit_on_receivable=on_recv,
                      applied_ca_event_ids=tuple(state.applied_ca_event_ids)
                      + (ev.canonical_event_id(),))
    return new, {
        "period": period, "event_id": ev.canonical_event_id(),
        "security_id": ev.stock_id,
        "effective_date": str(ev.ex_or_effective_date),
        "anchor_price": float(price), "anchor_session": str(session),
        "quantity": str(q), "proceeds": proceeds,
        "portfolio_weight_at_disposal": (proceeds / port_value
                                         if port_value else None),
        "basis": ROW1_UNRECONSTRUCTIBLE_DISPOSAL,
        "rule": "row-1 construction ruling 2026-09-03; NOT a frozen CA rule",
    }


def equal_weight_targets(eligible, port_value, marks, execution_prices,
                         untradable):
    """1/n of the marked book, in whole permitted share units.

    THE DENOMINATOR IS THE FULL ELIGIBLE SET, not the executable subset. Some
    eligible names have no permitted execution price on the execution session --
    `execute_session` refuses those outright ("an order without a price does not
    become a fill at some other number"), which is correct and is left alone.

    Dividing by the executable subset instead would silently concentrate the
    book into whatever happened to be tradable that day, making row ① a slightly
    different portfolio every period for reasons that have nothing to do with
    equal weighting. Shortfall goes to cash, which is the same discipline §5
    imposes on the strategy when breadth is thin.
    """
    eligible = sorted(set(eligible))
    if not eligible:
        return {}, 0.0, {"eligible": 0, "targetable": 0, "no_price": 0,
                         "untradable": 0, "no_mark": 0}
    w = 1.0 / len(eligible)
    rounding = spec("share_rounding")
    out, drop = {}, {"no_mark": 0, "no_price": 0, "untradable": 0}
    for sid in eligible:
        if sid not in marks or not marks[sid] > 0:
            drop["no_mark"] += 1
            continue
        if sid in untradable:
            drop["untradable"] += 1
            continue
        if sid not in execution_prices:
            drop["no_price"] += 1
            continue
        out[sid] = execution.target_shares(w * port_value, marks[sid],
                                           share_rounding=rounding)
    return out, w, {"eligible": len(eligible), "targetable": len(out), **drop}


def execute_row1_period(*, pre_trade, eligible, marks, adv20, sigma20d,
                        execution_prices, untradable, as_of, execution_date,
                        port_value):
    """One row ① period through the SAME execution layer the strategy used."""
    targets, w, breadth = equal_weight_targets(
        eligible, port_value, marks, execution_prices, untradable)

    # A HELD name with no permitted execution price cannot be sold today, and
    # §6.4 requires every non-target position to be sold. The strategy never met
    # this -- 20 chosen names always had prices -- but row ① holds ~370 and does.
    #
    # `untradable` is defined (§7.5) as the execution-layer determination of what
    # cannot trade today, passed in rather than inferred. "There is no permitted
    # execution price for it" is exactly that determination, so such names are
    # added to it and carry forward as `pending_exit`, which is the mechanism the
    # layer already has for a required sell that cannot execute. Nothing is
    # invented and no position is written off.
    referenced = set(pre_trade.shares) | set(pre_trade.pending_exit) | set(targets)
    unpriced = {sid for sid in referenced if sid not in execution_prices}
    breadth["held_unpriced_carried_as_pending_exit"] = len(
        unpriced - set(untradable))
    untradable = frozenset(set(untradable) | unpriced)
    session = execution.execute_session(
        execution_date=execution_date, data_as_of=as_of, pre_trade=pre_trade,
        target_share_counts=targets, prices=execution_prices, adv20=adv20,
        sigma20d=sigma20d, untradable=untradable,
        drift_policy=spec("target_drift_policy"),
        buy_priority=spec("buy_priority"),
        # NOT SelectionScore rank. See the module docstring.
        buy_order=tuple(sorted(targets)),
        x_sell=float(spec("X_sell")), x_buy=float(spec("X_buy")))
    return session, {"names_targeted": len(targets), "weight_each": w,
                     "breadth": breadth}


def mark_book(state, marks):
    """Mark-to-market on the same marks the strategy's period used."""
    value = float(state.cash)
    for sid, q in state.shares.items():
        if sid in marks:
            value += int(q) * float(marks[sid])
    for sid, q in state.pending_exit.items():
        if sid in marks:
            value += int(q) * float(marks[sid])
    for r in state.security_receivables:
        if r.security_id in marks:
            value += float(r.shares) * float(marks[r.security_id])
    value += float(getattr(state, "cash_dividend_receivable", 0.0) or 0.0)
    return value


# --- the ledger's own SD-SKIP disposition, restored for row ① -----------------

def restore_sd_skip(events_by_sid, ledger_path):
    """`load_events` overrides SD-SKIP rows back to NOT_RECONSTRUCTIBLE.

    MEASURED. The sealed ledger carries 160 stock_dividend rows disposed of as
    NOT_APPLICABLE with the SD-SKIP reason -- the operator ruling that a bonus
    leg with no observable credit date is DROPPED rather than blocking. The
    sealed runner's `load_events` then re-derives reconstructibility from the
    C-51 bonus panel, and an SD-SKIP row has no OFFICIAL_BONUS_RATE entry by
    construction, so `ratio is None` forces NOT_RECONSTRUCTIBLE. The ledger's
    adjudicated disposition is overwritten by the loader that reads it, and the
    SD-SKIP reason string survives on an event the ruling says should not exist
    -- which is how the block message quotes a rule that was supposed to prevent
    it.

    This is the third instance today of the same shape: a ruling implemented in
    the engine and defeated at the boundary that feeds it.

    ⚠ THE COMPLETED STRATEGY RUN IS UNAFFECTED, and that is checked rather than
    assumed: §6.1.12 blocks only on EXPOSURE, the two dispositions are
    indistinguishable for an unexposed event, and the run completed 141/141 --
    so it was never exposed to one. The override could not have changed a single
    recorded state hash.

    Row ① holds ~375 names and does meet them, so it honours the LEDGER, which
    is the adjudicated record and a sealed input. This is not an invented skip:
    it is the disposition the ruling already assigned.
    """
    import csv as _csv

    skip = set()
    with open(ledger_path, encoding="utf-8") as fh:
        for row in _csv.DictReader(fh):
            if (row["kind"] == "stock_dividend"
                    and row["reconstructibility"] == ca.NOT_APPLICABLE
                    and "SD-SKIP" in (row.get("reason") or "")):
                skip.add((str(row["stock_id"]), str(row["ex_or_effective_date"])))
    restored = 0
    out = {}
    for sid, evs in events_by_sid.items():
        fixed = []
        for ev in evs:
            if ((str(ev.stock_id), str(ev.ex_or_effective_date)) in skip
                    and ev.reconstructibility != ca.NOT_APPLICABLE):
                ev = _dc.replace(ev, reconstructibility=ca.NOT_APPLICABLE)
                restored += 1
            fixed.append(ev)
        out[sid] = tuple(fixed)
    return out, {"ledger_sd_skip_rows": len(skip), "events_restored": restored}
