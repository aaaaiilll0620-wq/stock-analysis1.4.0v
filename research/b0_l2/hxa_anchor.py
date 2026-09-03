# -*- coding: utf-8 -*-
"""The P_anchor resolver HX-A/CASH needs, and the reason it lives out here.

`core.b0_corporate_actions` takes the anchor as a CALLABLE
(`transition_portfolio(hxa_anchor=...)`) so that the corporate-action engine
never grows a dependency on price data. That separation is right and this module
does not undo it — it supplies the callable from the sealed price panel, once,
for whichever lineage is being run.

WHAT WENT WRONG WITHOUT IT

HX-A/CASH was frozen in B1's preregistration (§2.3(3)) and implemented in the
engine on 2026-09-03. Nothing supplied the anchor. `hxa_anchor` defaulted to
None, so the rule could not fire in any real run, and the B1 conformance
diagnostic stopped at 66/141 on the ONE event the rule exists to unblock
(`8913|holder_side_reorganization_exit|2020-01-14`) — the same wall B0.6 and
B0.7 hit, in the same place.

Five tests covered the rule and all five passed, because each one supplied its
own `_anchor()`. A test that provides the dependency under test proves the
engine and says nothing about the pipeline. `test_hxa_anchor_wiring.py` is the
one that would have caught this: it asserts the PRODUCTION callers pass an
anchor, not that the engine honours one.

THE RULE (frozen; this module implements it, it does not decide it)

    P_anchor  = the close of the last OBSERVED session strictly before the
                ceased-trading boundary
    staleness = at most 10 trading sessions of gap (enforced in the engine)
    Q_total   = tradable + same-security claims, exact, unrounded (engine)

Two refusals, both returning None so that §6.1.12 fails closed exactly as it did
before this module existed. Declining is always safe here; guessing is not.
"""
from __future__ import annotations

import os

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The engine re-checks strictly-before and the staleness cap, and its check is
# the normative one. This bound only stops the resolver from scanning the whole
# panel; it is deliberately WIDER than the engine's cap so that a stale anchor
# reaches the engine and is refused there with its own message, rather than
# being silently invisible here.
LOOKBACK_SESSIONS_SCANNED = 400


class HxaAnchorSource:
    """One pass over the sealed price panel, then O(1) per lookup."""

    def __init__(self, price_panel_path: str):
        self.path = price_panel_path
        df = pd.read_parquet(price_panel_path,
                             columns=["stock_id", "date", "close"])
        df = df.assign(stock_id=df["stock_id"].astype(str),
                       date=df["date"].astype(str))
        df = df.sort_values(["stock_id", "date"], kind="mergesort")
        self._by_sid: dict[str, tuple] = {}
        for sid, grp in df.groupby("stock_id", sort=False):
            self._by_sid[sid] = (tuple(grp["date"]), tuple(grp["close"]))

    def __call__(self, stock_id, boundary_date):
        """(price, session) for the last observed close strictly before the
        boundary, or None. None is a refusal, never a fallback."""
        sid, boundary = str(stock_id), str(boundary_date)
        leg = self._by_sid.get(sid)
        if leg is None:
            return None
        dates, closes = leg
        # Walk backwards from the boundary. `date < boundary` is strict, which
        # is R8: a close AT or AFTER the boundary is post-event data and is
        # never an admissible liquidation price.
        idx = None
        lo, hi = 0, len(dates)
        while lo < hi:                                   # rightmost date < boundary
            mid = (lo + hi) // 2
            if dates[mid] < boundary:
                lo = mid + 1
            else:
                hi = mid
        idx = lo - 1
        if idx < 0:
            return None
        scanned = 0
        while idx >= 0 and scanned < LOOKBACK_SESSIONS_SCANNED:
            close = closes[idx]
            if close is not None and float(close) > 0.0:
                return float(close), dates[idx]
            # A zero close is NOT an observation of a zero price. W1 §6.1
            # measured a live-source sentinel zero standing in for "did not
            # trade", and `valuation_sentinel_zero_is_undefined` already rules
            # the same shape on the valuation leg. Pricing a forced liquidation
            # at 0 would zero the position's whole value without raising.
            idx -= 1
            scanned += 1
        return None


def anchor_for_lineage(lineage: str = ""):
    """The resolver bound to ONE lineage's sealed price panel."""
    from core.b0_master_prereg import active_lineage, lineage_data_root

    lineage = lineage or active_lineage()
    return HxaAnchorSource(
        os.path.join(lineage_data_root(lineage), "price_panel.parquet"))
