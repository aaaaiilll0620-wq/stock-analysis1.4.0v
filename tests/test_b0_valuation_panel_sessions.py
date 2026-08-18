"""The valuation panel's as-of session must be the ROUTE's, for all 141 periods.

This exists because the two plausible conventions differ on most months and
agree on the rest, so a panel built on the wrong one produces no error, no gap
and no implausible number — it just answers a slightly different question 85
times out of 141.

    route (§6.6)   last completed session STRICTLY BEFORE the decision date
    audit          last session on or before the month end

The first test re-derives the panel's session rule through `resolve_as_of`
itself. The second pins the hazard: if the two conventions ever silently become
the same thing, that is a change to `resolve_as_of` and it should fail here
rather than pass quietly.
"""

import csv
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "b0_valuation_lineage_audit"))

from core.b0_market_state import SourceContract, TradingCalendar   # noqa: E402
from core.b0_master_prereg import spec                     # noqa: E402
from core.b0_route import resolve_as_of                    # noqa: E402
from harvest_official_pbr import (                          # noqa: E402
    decision_sessions,
    route_as_of_sessions,
)

PANEL = os.path.join(REPO, "data", "b0", "valuation_panel.parquet")


@pytest.fixture(scope="module")
def calendar() -> TradingCalendar:
    with open(os.path.join(REPO, "data", "b0", "trading_calendar.csv"),
              encoding="utf-8") as fh:
        sessions = tuple(sorted(r["session"] for r in csv.DictReader(fh)))
    contract = SourceContract(
        name="b0_trading_calendar", kind="trading_calendar",
        importer_version="frozen", content_sha256="0" * 64,
        schema_sha256="0" * 64, date_min=sessions[0], date_max=sessions[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    return TradingCalendar(sessions, contract)


@pytest.fixture(scope="module")
def periods():
    first = str(spec("first_eligible_decision_month"))
    last = str(spec("window_end"))[:7]
    return route_as_of_sessions(first, last)


def test_all_141_periods_resolve_through_the_route(periods, calendar):
    assert len(periods) == spec("window_months") == 141
    for _month, decision_date, as_of in periods:
        assert resolve_as_of(decision_date, calendar) == as_of


def test_the_month_end_convention_is_a_different_answer(periods):
    """85 of 141 — the reason this file exists."""
    audit = {m: s for m, _d, s in decision_sessions("2014-07", "2026-03")}
    differing = [m for m, _d, s in periods if audit[m] != s]
    assert len(differing) == 85
    for month in differing:
        route_as_of = dict((m, s) for m, _d, s in periods)[month]
        assert route_as_of < audit[month]      # strictly earlier, never later


def test_the_as_of_is_always_strictly_before_the_decision_date(periods):
    for _month, decision_date, as_of in periods:
        assert as_of < decision_date


@pytest.mark.skipif(not os.path.exists(PANEL), reason="panel not built yet")
def test_the_built_panel_carries_exactly_those_sessions(periods, calendar):
    import pandas as pd

    panel = pd.read_parquet(PANEL)
    expected = {(m, d, s) for m, d, s in periods}
    got = set(map(tuple, panel[["decision_month", "decision_date", "as_of"]]
                  .drop_duplicates().values.tolist()))
    assert got == expected
    for decision_date, as_of in panel[["decision_date", "as_of"]].drop_duplicates().values:
        assert resolve_as_of(str(decision_date), calendar) == str(as_of)


@pytest.mark.skipif(not os.path.exists(PANEL), reason="panel not built yet")
def test_no_zero_ratio_survives_into_the_panel():
    """The 0.0 sentinel is an absence, and absences are NA in the panel."""
    import pandas as pd

    panel = pd.read_parquet(PANEL)
    for col in ("pbr_tse", "per_tse"):
        vals = panel[col].dropna()
        assert (vals > 0).all(), f"{col} carries a non-positive value"
