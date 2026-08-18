"""P-1b layer 1 · canonical feature values (§3, §8.7).

As of master preregistration v1.4 every member of the graph has a frozen formula,
so these tests pin formulas rather than assert that they abort. What each test is
really guarding is a DIFFERENT reading that the same words would also permit:
TTM against single quarter, aggregate margin against a mean of ratios, single
month against a three-month mean, price return against total return. §11 C-8 is
this project's shipped instance of a name outliving its definition, and an
equality assertion is what would have caught it.

No test derives a feature from the repository's price or fundamental panels.
"""

import pytest

from core.b0_features import (
    CONCEPTS,
    FEATURE_GRAPH,
    INDUSTRY_UNRESOLVED,
    LOOKBACK_L_MONTHS,
    MIN_INDUSTRY_GROUP,
    PERCENTILE_CONVENTION,
    PERCENTILE_CONVENTIONS,
    FeatureError,
    FeaturePanel,
    assert_lookback_within_L,
    assert_not_revived,
    compute_current_ratio,
    compute_debt_to_asset,
    compute_eps_growth,
    compute_margin_ttm,
    compute_momentum_12_1,
    compute_peg,
    compute_revenue_yoy,
    compute_roe_ttm,
    compute_revenue_accel,
    compute_value_ind_pct_b,
    concept_members,
    feature_percentile,
    feature_value,
    latest_published_statement,
    orientation,
    peg_availability_report,
    percentile_rank,
    required_feature_keys,
)
from core.b0_open_items import UnspecifiedCoreBehaviour

CONV = "average_rank"


def full_row(**over):
    row = {k: 0.5 for k in required_feature_keys()}
    row.update(over)
    return row


# --- the frozen graph ---------------------------------------------------------

def test_graph_is_the_eleven_members_of_3_1():
    assert set(CONCEPTS) == {"Quality", "Growth", "Value", "Momentum"}
    assert len(FEATURE_GRAPH) == 11
    assert set(concept_members("Quality")) == {
        "roe", "net_margin", "gross_margin", "debt_to_asset", "current_ratio"}
    assert set(concept_members("Growth")) == {
        "revenue_yoy", "revenue_accel", "eps_growth"}
    assert set(concept_members("Value")) == {"value_ind_pct_b", "PEG"}
    assert concept_members("Momentum") == ("momentum_12_1",)


def test_removed_features_cannot_be_revived():
    for dead in ("asset_turnover", "rev_cagr", "cum_yoy", "streak", "high52_prox"):
        assert dead not in required_feature_keys()
        with pytest.raises(FeatureError, match="3.4"):
            assert_not_revived([dead])


def test_no_retained_feature_exceeds_the_frozen_lookback():
    assert_lookback_within_L()
    assert LOOKBACK_L_MONTHS == 18
    assert max(f.pit_lookback_months for f in FEATURE_GRAPH) == 18


# --- orientation --------------------------------------------------------------

def test_every_member_has_a_frozen_direction():
    """C-19: B-09 Phase 1's 方向 column, carried into the master preregistration."""
    for key in ("roe", "net_margin", "gross_margin", "current_ratio",
                "revenue_yoy", "revenue_accel", "eps_growth",
                "value_ind_pct_b", "momentum_12_1"):
        assert orientation(key) == "+"
    for key in ("debt_to_asset", "PEG"):
        assert orientation(key) == "-"


def test_direction_is_bound_to_the_definition_not_to_the_call_site():
    """The scoring entry point has no way to express a direction (C-19)."""
    import inspect

    sig = inspect.signature(feature_percentile)
    assert "ascending" not in sig.parameters

    values = {"safe": 10.0, "levered": 90.0}
    pct = feature_percentile("debt_to_asset", values, convention=CONV)
    assert pct["safe"] == 1.0 and pct["levered"] == 0.0     # lower debt scores higher

    values = {"cheap": 0.5, "dear": 4.0}
    pct = feature_percentile("PEG", values, convention=CONV)
    assert pct["cheap"] == 1.0 and pct["dear"] == 0.0       # lower PEG scores higher


# --- the percentile primitive -------------------------------------------------

def test_convention_must_be_named_and_only_one_is_legal():
    """C-35: average rank over ties, and no selectable alternative."""
    with pytest.raises(TypeError):
        percentile_rank({"a": 1.0, "b": 2.0})          # keyword-only, no default
    assert PERCENTILE_CONVENTION == "average_rank"
    assert PERCENTILE_CONVENTIONS == ("average_rank",)
    with pytest.raises(FeatureError, match="C-35"):
        percentile_rank({"a": 1.0, "b": 2.0}, convention="ordinal_rank")


def test_equal_raw_values_receive_equal_percentiles():
    """C-35: the tie rule, stated as the property it has to have."""
    values = {"a": 1.0, "b": 1.0, "c": 3.0}
    pct = percentile_rank(values, convention=CONV)
    assert pct["a"] == pct["b"] == 0.25
    assert pct["c"] == 1.0


def test_percentiles_do_not_depend_on_row_order():
    """Two adapters building the panel differently must agree bit-exactly."""
    values = {"a": 1.0, "b": 1.0, "c": 3.0, "d": 2.0, "e": 3.0}
    forward = percentile_rank(values, convention=CONV)
    backward = percentile_rank(dict(reversed(list(values.items()))),
                               convention=CONV)
    assert forward == backward


def test_the_portfolio_tie_break_does_not_leak_into_feature_scoring():
    """C-35 vs C-33: stock_id breaks PORTFOLIO ties, never FEATURE ties.

    If it leaked, a security would earn alpha for having a low identifier.
    """
    tied = percentile_rank({"AAAA": 5.0, "ZZZZ": 5.0}, convention=CONV)
    assert tied["AAAA"] == tied["ZZZZ"]


def test_percentile_is_monotone_and_spans_the_unit_interval():
    p = percentile_rank({"lo": 1.0, "mid": 5.0, "hi": 9.0}, convention=CONV)
    assert p["lo"] == 0.0 and p["hi"] == 1.0 and 0 < p["mid"] < 1
    d = percentile_rank({"lo": 1.0, "mid": 5.0, "hi": 9.0}, convention=CONV,
                        ascending=False)
    assert d["lo"] == 1.0 and d["hi"] == 0.0


def test_a_rank_is_undefined_below_two_members():
    assert MIN_INDUSTRY_GROUP == 2
    with pytest.raises(FeatureError, match="3.2"):
        percentile_rank({"only": 1.0}, convention=CONV)


def test_a_nan_reaching_the_ranker_means_the_complete_case_gate_was_bypassed():
    with pytest.raises(FeatureError, match="4.1"):
        percentile_rank({"a": 1.0, "b": float("nan")}, convention=CONV)


# --- value_ind_pct_b (§3.2, fully determined) ---------------------------------

def test_value_is_ranked_within_the_pit_industry_and_higher_bm_is_cheaper():
    pbr = {"a": 1.0, "b": 2.0, "c": 4.0, "x": 1.0, "y": 2.0}
    ind = {"a": "水泥", "b": "水泥", "c": "水泥", "x": "鋼鐵", "y": "鋼鐵"}
    out = compute_value_ind_pct_b(pbr, ind, convention=CONV)
    # B/M = 1/PBR, so the lowest PBR in a group is the cheapest and ranks top.
    assert out["a"] == 1.0 and out["c"] == 0.0
    assert out["x"] == 1.0 and out["y"] == 0.0        # ranked within its own group


def test_unresolved_industry_yields_na_and_is_never_backfilled():
    out = compute_value_ind_pct_b(
        {"a": 1.0, "b": 2.0, "u": 1.5},
        {"a": "水泥", "b": "水泥", "u": INDUSTRY_UNRESOLVED},
        convention=CONV)
    assert out["u"] is None
    assert out["a"] is not None


def test_non_positive_book_to_price_is_undefined_not_expensive():
    out = compute_value_ind_pct_b(
        {"a": 1.0, "b": 2.0, "z": 0.0, "w": -1.0},
        {k: "水泥" for k in ("a", "b", "z", "w")}, convention=CONV)
    assert out["z"] is None and out["w"] is None


def test_group_below_the_rank_minimum_yields_na():
    out = compute_value_ind_pct_b({"a": 1.0, "solo": 3.0},
                                  {"a": "水泥", "solo": "航運"}, convention=CONV)
    assert out["solo"] is None


# --- revenue_accel (§2.1, fully determined, delegated) ------------------------

def test_revenue_accel_is_pinned_to_the_a_leg_definition():
    """§11 C-8: one name, two formulas, shipped. An equality assertion is the fix."""
    from core.b0_parity import rev_accel_a_leg, rev_accel_b_leg

    yoys = [1.0, 2.0, 3.0, 10.0, 11.0, 12.0]
    assert compute_revenue_accel(yoys) == pytest.approx(9.0)
    assert compute_revenue_accel(yoys) == pytest.approx(rev_accel_a_leg(yoys))
    # The B leg is a different number under the same name — the drift itself.
    assert compute_revenue_accel(yoys) != pytest.approx(rev_accel_b_leg(yoys))


def test_insufficient_revenue_history_is_an_absence_not_a_zero():
    assert compute_revenue_accel([1.0, 2.0, 3.0, 4.0, 5.0]) is None
    assert compute_revenue_accel([]) is None


# --- the undetermined nine ----------------------------------------------------

def test_every_member_of_the_graph_now_has_a_frozen_formula():
    """v1.4: the M-3 abort path stays, but nothing routes to it any more."""
    from core.b0_features import _FORMULA_ITEM

    assert [f.key for f in FEATURE_GRAPH if f.formula is None] == []
    assert _FORMULA_ITEM == {}


# --- Quality TTM (C-21) -------------------------------------------------------

def test_roe_is_ttm_net_income_over_period_end_equity():
    # four quarters of 25 each = 100 TTM, on equity of 500 -> 20%
    assert compute_roe_ttm([10.0, 25.0, 25.0, 25.0, 25.0], 500.0) == pytest.approx(20.0)


def test_roe_needs_four_consecutive_reported_quarters():
    assert compute_roe_ttm([25.0, 25.0, 25.0], 500.0) is None
    # a gap inside the window is not skipped over: 3 quarters vs 4 is not a ratio
    assert compute_roe_ttm([25.0, None, 25.0, 25.0], 500.0) is None


def test_roe_is_undefined_on_non_positive_equity():
    """Same principle as C-17's PEG domain: the sign would otherwise invert."""
    assert compute_roe_ttm([25.0, 25.0, 25.0, 25.0], -500.0) is None
    assert compute_roe_ttm([25.0, 25.0, 25.0, 25.0], 0.0) is None


def test_margin_is_aggregate_over_aggregate_not_a_mean_of_ratios():
    profit = [30.0, 10.0, 10.0, 10.0]
    revenue = [30.0, 100.0, 100.0, 100.0]
    # aggregate: 60 / 330 = 18.18%; mean of ratios would be (100+10+10+10)/4 = 32.5%
    assert compute_margin_ttm(profit, revenue) == pytest.approx(60 / 330 * 100)
    assert compute_margin_ttm(profit, revenue) != pytest.approx(32.5)


def test_margin_is_undefined_without_revenue():
    assert compute_margin_ttm([1.0] * 4, [0.0] * 4) is None


# --- current-quarter balance sheet (C-22) ------------------------------------

def test_balance_sheet_ratios_are_percentage_points():
    assert compute_debt_to_asset(85.0, 100.0) == pytest.approx(85.0)
    assert compute_current_ratio(150.0, 100.0) == pytest.approx(150.0)
    assert compute_debt_to_asset(85.0, 0.0) is None
    assert compute_current_ratio(150.0, 0.0) is None


def test_current_means_the_latest_statement_actually_published(  ):
    """§2.2: a statement dated before as_of but published after it is not available."""
    statements = [
        {"quarter": "2020Q1", "release_date": "2020-05-15", "total_assets": 100.0},
        {"quarter": "2020Q2", "release_date": "2020-08-14", "total_assets": 110.0},
    ]
    got = latest_published_statement(statements, "2020-06-30")
    assert got["quarter"] == "2020Q1"
    assert latest_published_statement(statements, "2020-08-14")["quarter"] == "2020Q2"
    assert latest_published_statement(statements, "2020-01-01") is None


# --- revenue_yoy (C-23) -------------------------------------------------------

def test_revenue_yoy_is_a_single_month_comparison():
    series = [100.0] + [0.0] * 11 + [130.0]      # m-12 = 100, m = 130
    assert compute_revenue_yoy(series) == pytest.approx(30.0)


def test_revenue_yoy_needs_thirteen_months():
    assert compute_revenue_yoy([100.0] * 12) is None


# --- momentum 12-1 (C-24) -----------------------------------------------------

def test_momentum_skips_the_most_recent_month():
    # index -14 .. -1; P_t-13 = 100, P_t-1 = 150, and the last month is ignored
    prices = [100.0] + [0.0] * 11 + [150.0, 999.0]
    assert compute_momentum_12_1(prices) == pytest.approx(50.0)


def test_momentum_needs_fourteen_month_end_observations():
    assert compute_momentum_12_1([100.0] * 13) is None


def test_momentum_is_undefined_on_a_non_positive_base():
    assert compute_momentum_12_1([0.0] + [1.0] * 13) is None


# --- eps_growth (C-18) --------------------------------------------------------

def test_eps_growth_is_quarterly_yoy_in_percentage_points():
    eps = [1.0, 1.1, 1.2, 1.3, 2.0]          # t-4 = 1.0, t = 2.0
    assert compute_eps_growth(eps) == pytest.approx(100.0)


def test_eps_growth_uses_an_absolute_denominator_so_a_loss_base_keeps_its_sign():
    """Lineage: (latest - prior) / abs(prior) * 100 in the legacy producer."""
    # base = -2.0 (a loss), latest = -1.0 (a smaller loss) -> improvement, positive
    assert compute_eps_growth([-2.0, 0.0, 0.0, 0.0, -1.0]) == pytest.approx(50.0)
    # base = -2.0, latest = -3.0 (a bigger loss) -> deterioration, negative
    assert compute_eps_growth([-2.0, 0.0, 0.0, 0.0, -3.0]) == pytest.approx(-50.0)


def test_eps_growth_is_na_without_a_comparable_base_quarter():
    assert compute_eps_growth([1.0, 1.1, 1.2, 2.0]) is None      # only 4 quarters
    assert compute_eps_growth([0.0, 1.0, 1.0, 1.0, 2.0]) is None  # zero base
    assert compute_eps_growth([None, 1.0, 1.0, 1.0, 2.0]) is None


def test_the_legacy_net_income_fallback_is_not_carried_over():
    """§4.1 forbids imputation; substituting a different series is imputation."""
    from core.b0_master_prereg import spec

    assert spec("eps_growth_net_income_fallback") is False


# --- PEG (C-17) ---------------------------------------------------------------

def test_peg_is_pe_over_growth_in_percentage_points():
    assert compute_peg(20.0, 10.0) == pytest.approx(2.0)
    # The unit trap: a decimal growth of 0.10 would give 200, not 2.
    assert compute_peg(20.0, 0.10) == pytest.approx(200.0)


def test_peg_is_undefined_outside_the_positive_domain():
    assert compute_peg(-10.0, 20.0) is None      # negative PE
    assert compute_peg(20.0, -20.0) is None      # shrinking earnings
    assert compute_peg(-10.0, -20.0) is None     # the absurd quadrant: not +0.5
    assert compute_peg(20.0, 0.0) is None
    assert compute_peg(None, 20.0) is None


def test_peg_missingness_is_reported_rather_than_engineered_away():
    report = peg_availability_report({"a": 1.5, "b": None, "c": 2.0, "d": None})
    assert report["peg_defined"] == 2 and report["peg_na"] == 2
    assert report["peg_coverage"] == pytest.approx(0.5)


def test_a_feature_outside_the_graph_is_not_computed_at_all():
    with pytest.raises(FeatureError):
        feature_value("sharpe_of_the_stock")


# --- the panel ----------------------------------------------------------------

def test_panel_distinguishes_an_absent_key_from_an_unavailable_value():
    row = full_row()
    del row["PEG"]
    with pytest.raises(FeatureError, match="missing feature keys"):
        FeaturePanel("2020-06-30", {"1101": row})

    p = FeaturePanel("2020-06-30", {"1101": full_row(PEG=None)})
    assert p.is_complete("1101") is False
    assert "PEG" not in p.available("1101")


def test_panel_refuses_a_feature_that_is_not_in_the_frozen_graph():
    with pytest.raises(FeatureError, match="3.4"):
        FeaturePanel("2020-06-30", {"1101": full_row(asset_turnover=0.9)})
    with pytest.raises(FeatureError, match="do not enter|not members"):
        FeaturePanel("2020-06-30", {"1101": full_row(my_new_alpha=0.9)})
