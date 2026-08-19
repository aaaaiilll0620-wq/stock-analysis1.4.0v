"""§4.1a · sealed-input sufficiency — the test whose absence invalidated an L2 run.

Run `L2-2520c80aa980d681` executed all 141 periods and rejected 100% of the
universe in every one of them, because `revenue_accel` needs 18 months of monthly
revenue and the materializer supplied 13. Everything was green: 2,073 tests, 141
reproducible state hashes, a clean seal. None of it could catch this, because
identical inputs hash identically whether or not they are long enough.

T-1 .. T-6. The parameterisation over `required_feature_keys()` is the load-
bearing part: a frozen member added later joins these tests automatically, so the
next lookback gap is red before a seal rather than after an opening.
"""

import json
import os

import pytest

from core.b0_eligibility import required_feature_keys
from core.b0_features import (
    CALENDAR_INDEXED_SERIES,
    COMPRESSING_MISSING_PERIODS_ALLOWED,
    INTENTIONAL_ZERO_MARGIN,
    LOOKBACK_L_MONTHS,
    SecurityPitInputs,
    build_feature_panel,
    member_input_requirements,
    series_requirements,
)
from core.b0_master_prereg import spec

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")
CONV = spec("percentile_convention")

SERIES_FIELDS = ("net_income_by_quarter", "revenue_by_quarter",
                 "gross_profit_by_quarter", "eps_by_quarter",
                 "monthly_revenue", "month_end_prices")


def _panel_row(**lengths):
    kw = dict(stock_id="T", pit_industry="M1100", pbr_tse=1.0, per_tse=10.0,
              period_end_equity=1e9, total_liabilities=4e8, total_assets=1e9,
              current_assets=6e8, current_liabilities=3e8)
    for f in SERIES_FIELDS:
        n = lengths.get(f, 40)
        kw[f] = tuple(100.0 + 3.0 * i for i in range(n))
    return build_feature_panel("2020-01-31", [SecurityPitInputs(**kw)],
                               convention=CONV).values["T"]


# --- T-1 · transitive lookback closure, measured against the declaration ------

@pytest.mark.parametrize("member", sorted(required_feature_keys()))
def test_declared_requirement_equals_the_measured_one(member):
    """The accessor must not drift from the computation it describes."""
    declared = member_input_requirements()[member]
    for field, need in declared.items():
        assert _panel_row(**{field: need})[member] is not None, (
            "%s declares it needs %d of %s but is NA at that length"
            % (member, need, field))
        if need > 0:
            assert _panel_row(**{field: need - 1})[member] is None, (
                "%s declares it needs %d of %s but is computable with one fewer"
                % (member, need, field))


def test_every_frozen_member_participates():
    """A member added later cannot escape this file."""
    declared = member_input_requirements()
    missing = [m for m in required_feature_keys() if m not in declared]
    assert not missing, (
        "frozen members with no declared input requirement: %s" % missing)


# --- T-2 · supplied vs required, and zero margin must be intentional ----------

def _materializer_supply():
    import sys
    sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))
    import build_market_side_state as b

    return {"monthly_revenue": b.MONTHS_REVENUE,
            "month_end_prices": b.MONTH_ENDS_REQUIRED,
            "net_income_by_quarter": b.QUARTERS,
            "revenue_by_quarter": b.QUARTERS,
            "gross_profit_by_quarter": b.QUARTERS,
            "eps_by_quarter": b.QUARTERS}


@pytest.mark.parametrize("series", sorted(SERIES_FIELDS))
def test_the_materializer_supplies_at_least_what_is_required(series):
    required = series_requirements()[series]
    supplied = _materializer_supply()[series]
    assert supplied >= required, (
        "§4.1a: %s requires %d and the materializer supplies %d. This is the "
        "defect class that invalidated run L2-2520c80aa980d681."
        % (series, required, supplied))
    if supplied == required:
        assert series in INTENTIONAL_ZERO_MARGIN, (
            "§4.1a: %s is supplied with zero margin but is not declared "
            "intentional. Exactly-sufficient must be a decision, not a "
            "coincidence." % series)


def test_the_declared_zero_margins_are_actually_zero():
    req, sup = series_requirements(), _materializer_supply()
    for series in INTENTIONAL_ZERO_MARGIN:
        assert sup[series] == req[series], (
            "%s is declared zero-margin but supplies %d against a requirement "
            "of %d; either the declaration or the supply is stale"
            % (series, sup[series], req[series]))


# --- T-3 · the frozen registry and the measured requirement must agree -------

def test_lookback_l_months_is_the_deepest_monthly_requirement():
    """Had this existed, the defect would have been red before the seal."""
    assert series_requirements()["monthly_revenue"] == LOOKBACK_L_MONTHS == 18
    assert spec("lookback_L_months") == LOOKBACK_L_MONTHS
    # and it is NOT a universal length for every monthly array
    assert series_requirements()["month_end_prices"] == 14 != LOOKBACK_L_MONTHS


# --- T-4/T-5 · the sealed artefacts, not just the constants -------------------

def _manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


pytestmark_needs_state = pytest.mark.skipif(
    not os.path.exists(MANIFEST), reason="market-side state not materialized")


@pytestmark_needs_state
def test_every_sealed_period_supplies_enough():
    import pandas as pd

    req = series_requirements()
    for m in _manifest():
        df = pd.read_parquet(os.path.join(REPO, m["artefact"]))
        for series, col in (("monthly_revenue", "monthly_revenue"),
                            ("month_end_prices", "month_end_prices"),
                            ("eps_by_quarter", "eps_by_quarter")):
            longest = df[col].map(lambda a: 0 if a is None else len(a)).max()
            assert longest >= req[series], (
                "%s supplies at most %d of %s, needs %d"
                % (m["decision_month"], longest, series, req[series]))


@pytestmark_needs_state
def test_complete_case_is_reachable_in_every_period():
    """T-5. A universe-wide rejection is now a test failure, not a valid run.

    Reachability only — no count, no name, no score is asserted or inspected.
    """
    import sys

    import pandas as pd
    sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))
    from build_period1_full_input import _clean, _scalar

    for m in _manifest():
        df = pd.read_parquet(os.path.join(REPO, m["artefact"]))
        inputs = [SecurityPitInputs(
            stock_id=str(r.stock_id),
            net_income_by_quarter=_clean(r.net_income_by_quarter),
            revenue_by_quarter=_clean(r.revenue_by_quarter),
            gross_profit_by_quarter=_clean(r.gross_profit_by_quarter),
            eps_by_quarter=_clean(r.eps_by_quarter),
            period_end_equity=_scalar(r.period_end_equity),
            total_liabilities=_scalar(r.total_liabilities),
            total_assets=_scalar(r.total_assets),
            current_assets=_scalar(r.current_assets),
            current_liabilities=_scalar(r.current_liabilities),
            monthly_revenue=_clean(r.monthly_revenue),
            month_end_prices=_clean(r.month_end_prices),
            per_tse=_scalar(r.per_tse), pbr_tse=_scalar(r.pbr_tse),
            pit_industry=str(r.pit_industry)) for r in df.itertuples()]
        panel = build_feature_panel(m["as_of"], inputs, convention=CONV)
        keys = list(required_feature_keys())
        reachable = any(all(v.get(k) is not None for k in keys)
                        for v in panel.values.values())
        assert reachable, (
            "§4.1a: no security passes complete-case in %s. The frozen core "
            "cannot select from an empty set, and a run that proceeds anyway "
            "produces no evidence." % m["decision_month"])


# --- T-6 · calendar continuity ------------------------------------------------

def test_the_producer_declares_calendar_indexing():
    assert COMPRESSING_MISSING_PERIODS_ALLOWED is False
    for s in ("monthly_revenue", "eps_by_quarter", "month_end_prices"):
        assert s in CALENDAR_INDEXED_SERIES


@pytestmark_needs_state
def test_sealed_series_are_calendar_indexed_not_compressed():
    """A compressed series has fewer entries than its span; None marks the gap."""
    import pandas as pd

    req = series_requirements()
    for m in _manifest()[:6] + _manifest()[-6:]:
        df = pd.read_parquet(os.path.join(REPO, m["artefact"]))
        for col, need in (("monthly_revenue", req["monthly_revenue"]),
                          ("eps_by_quarter", req["eps_by_quarter"]),
                          ("month_end_prices", req["month_end_prices"])):
            lens = df[col].map(lambda a: 0 if a is None else len(a))
            nonzero = lens[lens > 0]
            assert (nonzero == nonzero.max()).all(), (
                "%s/%s: series have ragged lengths %s, which is what compressing "
                "missing periods looks like"
                % (m["decision_month"], col, sorted(set(nonzero))[:5]))
            assert nonzero.max() >= need
