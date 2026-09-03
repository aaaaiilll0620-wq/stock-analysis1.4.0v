# -*- coding: utf-8 -*-
"""§9.3 row ③ (0050 buy-and-hold) and the §9.4 V-4 gate.

WHAT IS HERE AND WHAT IS NOT

Row ③ and V-4 only. Rows ① (eligible-universe equal weight) and ② (matched
random selection, N draws, median + null p) are separate work: both require
running the execution layer over counterfactual target portfolios, and ② does it
N times. They are §9.7 REPORTING requirements, not V-4 inputs -- §9.4's three
conditions are decided by row ◆ and row ③ alone -- so the gate can be computed
before they exist. The OUTCOME may not be written before they exist, because
§9.7 voids an opening that omits any category.

WHY ROW ③ IS BUILT AND NOT READ

Nothing in the repository produces it. `core/b0_benchmark_construction.py`
freezes the constants and the two ledger transitions; `core/b0_benchmark_gate1.py`
checks that the inputs are sealed. Neither walks the window. This does, out of
the sealed panel, using the frozen pieces rather than around them.

⚠ `core/b0_benchmark_gate1.py:41` pins `BENCHMARK_PANEL = "data/b0/..."`, so its
`panel_present` check reads Frozen B0's file whatever lineage is asked. The
SUBSTANTIVE part of that module's check is lineage-correct (it reads the seal's
bindings and the manifest rows), so the defect mislabels rather than misleads --
and it is NOT fixed here. That module is normative, B1's observation is already
spent, and §1.4 no-post-hoc-rescue closes the specification once a lineage has
produced an outcome. It is recorded, not repaired.

CONVENTIONS (§9.4 freezes the predicates, not the arithmetic)

The Master freezes the three gate predicates and the `Sharpe_0rf` rf convention
(V-6). It does not freeze an annualisation factor, a year count or a drawdown
sampling frequency. Those are named here, identically to the B0.7 diagnostic's
`performance()`, so that the two cannot quietly diverge; a test pins the
agreement. Every verdict is invariant to them -- gate 2 turns on W_T > W_0 and
gate 3 on mean(returns) > 0, and no positive scale factor moves a sign.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import os
from datetime import date

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.b0_benchmark_construction import (                     # noqa: E402
    BENCHMARK_CASH_EARNS_INTEREST, BENCHMARK_IDENTITY, BENCHMARK_SECURITY,
    BenchmarkLedger, DIVIDEND_REINVESTED, TERMINAL_LIQUIDATION,
    TERMINAL_TREATMENT, apply_dividend_ex_date, apply_share_unit_event,
    solve_initial_shares,
)
from core.b0_frozen_spec import (                                # noqa: E402
    SHARPE_METRIC_NAME, assert_sharpe_named_explicitly,
)
from core.b0_state import compute_sigma20d                       # noqa: E402

# The materializer's own windows, so row ③'s cost inputs are built the way every
# other security's were. A second set of constants here would be a second
# convention wearing the same name.
ADV_SESSIONS = 20
SIGMA_SESSIONS = 20


class LadderError(RuntimeError):
    """Row ③ could not be built from the sealed inputs. Never approximated."""


def performance(marked, opening_wealth):
    """The reporting arithmetic, stated rather than assumed frozen.

    `marked` is a sequence of {"as_of", "wealth"} in window order. Identical in
    every convention to the B0.7 diagnostic's `performance()`; see the module
    docstring for why that matters.
    """
    w = [float(r["wealth"]) for r in marked]
    w0 = float(opening_wealth)
    rets, prev = [], w0
    for x in w:
        rets.append(x / prev - 1.0 if prev else 0.0)
        prev = x
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    d0 = date.fromisoformat(marked[0]["as_of"])
    dT = date.fromisoformat(marked[-1]["as_of"])
    years = (dT - d0).days / 365.25
    peak, mdd = w0, 0.0
    for x in [w0] + w:
        peak = max(peak, x)
        mdd = max(mdd, (peak - x) / peak if peak else 0.0)
    assert_sharpe_named_explicitly(SHARPE_METRIC_NAME)
    return {
        "opening_wealth": w0, "terminal_wealth": w[-1],
        "wealth_multiple": w[-1] / w0, "cumulative_return": w[-1] / w0 - 1.0,
        "years": years,
        "cagr": (w[-1] / w0) ** (1.0 / years) - 1.0 if years > 0 and w0 > 0 else None,
        "sharpe_metric_name": SHARPE_METRIC_NAME,
        "sharpe_0rf": (mean / sd * math.sqrt(12.0)) if sd > 0 else None,
        "mean_period_return": mean, "stdev_period_return_ddof1": sd,
        "mdd": mdd, "periods": len(w),
        "conventions": {
            "return_series": "period-over-period simple returns of the marked "
                             "NAV points",
            "cagr": "(W_T/W_0)**(1/years) - 1, years = actual days / 365.25",
            "sharpe": "mean/stdev(ddof=1) x sqrt(12), rf = 0",
            "mdd": "max peak-to-trough decline of the same marked series",
            "gate_verdicts_are_invariant_to_these": True,
        },
    }


def _cost_inputs(panel: pd.DataFrame, as_of: str) -> tuple:
    """adv20 and sigma20d for 0050 at `as_of`, built the materializer's way.

    turnover = close x volume and a 20-session mean; sigma20d from
    `compute_sigma20d` over 21 closes. RAW closes are correct here: 0050's only
    share-unit event is 2025-06-18 and the single benchmark purchase is at the
    window's first execution date in 2014, so no adjustment factor is in scope.
    A later purchase would have to revisit this.
    """
    sessions = list(panel["session"])
    i = bisect.bisect_right(sessions, as_of) - 1
    if i < 0:
        raise LadderError("no 0050 session at or before %s" % as_of)
    if sessions[i] != as_of:
        raise LadderError(
            "0050 has no session on %s (nearest earlier %s). The benchmark must "
            "be marked on the same session the strategy stands on."
            % (as_of, sessions[i]))
    close = panel["close"].to_numpy(dtype=float)
    vol = panel["volume_shares"].to_numpy(dtype=float)
    if i + 1 < ADV_SESSIONS or i + 1 < SIGMA_SESSIONS + 1:
        raise LadderError("insufficient 0050 history at %s" % as_of)
    adv20 = float(np.mean((close * vol)[i - ADV_SESSIONS + 1:i + 1]))
    sigma = compute_sigma20d(list(close[i - SIGMA_SESSIONS:i + 1]))
    if sigma is None:
        raise LadderError("sigma20d is undefined for 0050 at %s" % as_of)
    return adv20, float(sigma)


def build_row3(manifest, opening_cash: float, data_root: str) -> dict:
    """0050 buy-and-hold, dividend-inclusive, marked on the strategy's sessions."""
    panel = pd.read_parquet(
        os.path.join(data_root, "benchmark_0050_panel.parquet"))
    panel = panel.assign(session=panel["session"].astype(str)) \
                 .sort_values("session", kind="mergesort").reset_index(drop=True)
    sessions = list(panel["session"])
    close_at = dict(zip(sessions, panel["close"].astype(float)))
    open_at = dict(zip(sessions, panel["open"].astype(float)))

    events = pd.read_parquet(
        os.path.join(data_root, "benchmark_0050_share_unit_events.parquet"))
    unit_events = sorted(
        ((str(r.effective_date), float(r.holder_multiplier),
          "%s|%s" % (BENCHMARK_SECURITY, r.effective_date))
         for r in events.itertuples()
         if str(r.security_id) == BENCHMARK_SECURITY), key=lambda x: x[0])
    with open(os.path.join(data_root, "benchmark_0050_distributions.csv"),
              encoding="utf-8") as fh:
        dists = sorted(((str(r["ex_date"]), float(r["cash_per_unit"]))
                        for r in csv.DictReader(fh) if r.get("cash_per_unit")),
                       key=lambda x: x[0])

    first = manifest[0]
    buy_session = str(first["execution_date"])
    if buy_session not in open_at:
        raise LadderError(
            "0050 has no session on the window's first execution date %s"
            % buy_session)
    adv20, sigma = _cost_inputs(panel, str(first["as_of"]))
    entry = solve_initial_shares(
        open_at[buy_session], float(opening_cash), sigma, adv20,
        data_as_of=str(first["as_of"]), execution_date=buy_session)
    if entry["shares"] <= 0:
        raise LadderError("C_ref buys no whole 0050 share at %s" % buy_session)

    ledger = BenchmarkLedger(shares=int(entry["shares"]),
                             cash=float(entry["residual_cash"]))
    ui, di, marked = 0, 0, []
    for period in manifest:
        as_of = str(period["as_of"])
        # Everything with an ex/effective date at or before this mark, in order.
        while ui < len(unit_events) and unit_events[ui][0] <= as_of:
            d, mult, eid = unit_events[ui]
            if d > buy_session:
                ledger = apply_share_unit_event(ledger, eid, mult)
            ui += 1
        while di < len(dists) and dists[di][0] <= as_of:
            d, cps = dists[di]
            if d > buy_session:
                ledger = apply_dividend_ex_date(ledger, cps)
            di += 1
        if as_of not in close_at:
            raise LadderError("0050 has no close on %s" % as_of)
        marked.append({"as_of": as_of, "period": period["decision_month"],
                       "wealth": ledger.wealth(close_at[as_of]),
                       "shares": ledger.shares, "cash": ledger.cash,
                       "receivable": ledger.receivable})

    perf = performance(marked, opening_cash)
    return {
        "row": "3", "identity": BENCHMARK_IDENTITY,
        "security_id": BENCHMARK_SECURITY,
        "entry": {**entry, "execution_date": buy_session,
                  "adv20": adv20, "sigma20d": sigma},
        "share_unit_events_applied": ledger.applied_share_unit_events,
        "distributions_accrued": di,
        "terminal_receivable": ledger.receivable,
        "frozen_constants": {
            "dividend_reinvested": DIVIDEND_REINVESTED,
            "cash_earns_interest": BENCHMARK_CASH_EARNS_INTEREST,
            "terminal_treatment": TERMINAL_TREATMENT,
            "terminal_liquidation": TERMINAL_LIQUIDATION,
        },
        "performance": perf, "marked": marked,
    }


def v4_gate(strategy_perf: dict, row3_perf: dict) -> dict:
    """§9.4, frozen. Three conditions, ANDed -- ONE composite hypothesis.

    §9.8's clarification is load-bearing and is restated in the output: the AND
    is a single intersection hypothesis, not three tests, so it cannot inflate a
    type-I error. Conditions 2 and 3 are not alpha thresholds; they exist to stop
    a strategy that lost money being called Supported because the benchmark lost
    more.
    """
    c1 = strategy_perf["terminal_wealth"] > row3_perf["terminal_wealth"]
    c2 = strategy_perf["cagr"] is not None and strategy_perf["cagr"] > 0
    c3 = (strategy_perf["sharpe_0rf"] is not None
          and strategy_perf["sharpe_0rf"] > 0)
    return {
        "gate": "V-4",
        "conditions": {
            "1_net_cumulative_wealth_gt_0050_buy_and_hold": {
                "pass": bool(c1),
                "strategy_terminal_wealth": strategy_perf["terminal_wealth"],
                "benchmark_terminal_wealth": row3_perf["terminal_wealth"],
                "difference": strategy_perf["terminal_wealth"]
                              - row3_perf["terminal_wealth"]},
            "2_net_cagr_gt_0": {"pass": bool(c2), "value": strategy_perf["cagr"]},
            "3_net_sharpe_0rf_gt_0": {
                "pass": bool(c3), "value": strategy_perf["sharpe_0rf"],
                "metric_name": SHARPE_METRIC_NAME},
        },
        "all_three_pass": bool(c1 and c2 and c3),
        "combination": "AND",
        "statistical_reading": "a single composite (intersection) hypothesis, "
                               "not three tests; AND only makes passing harder",
        "excluded_from_the_gate": "beating Frozen A. It is a historical "
                                  "comparator, never an opponent (§9.4).",
    }
