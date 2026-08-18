import pytest

from tests.conftest import make_stock
from core.advisor import InvestmentAdvisor
from core.fundamentals import FundamentalEngine
from core.scoring_manager import ScoringManager
from beat_0050.realbody import build_arm_panel as panel


@pytest.fixture(autouse=True)
def reset_research_flags():
    panel.reset_arm_state()
    yield
    panel.reset_arm_state()


def test_v0_default_is_unchanged_and_b3_only_removes_revenue_leg():
    stock = make_stock(revenue_accel=10.0, revenue_cum_yoy=20.0,
                       revenue_growth_streak=6, volume=0)
    scorer = ScoringManager()
    v0 = scorer._get_momentum_score(stock)
    ScoringManager.RESEARCH_ARM = "B3"
    b3 = scorer._get_momentum_score(stock)
    assert b3 == pytest.approx(v0 - (14.0 + 7.0 + 6.0))


def test_b1_uses_atr_slope_and_rsi_interpolation():
    stock = make_stock(current_price=100.0, ma5=100.0, ma20=100.0,
                       weekly_ma20=100.0, atr_pct=2.0, rsi=60.0,
                       macd_status="bearish", bb_status="",
                       ma_cross_status="neutral", volume=0)
    ScoringManager.RESEARCH_ARM = "B1"
    got = ScoringManager()._get_technical_score(stock)
    # Four equality points are half-full: 5+5+5+7.5; RSI at its peak is 25.
    assert got == pytest.approx(47.5)


def test_b5_hits_frozen_rule_r_nodes():
    stock = make_stock(mom_6m=7.5, mom_3m=4.0, rs_6m=-2.5, rs_3m=0.0,
                       revenue_accel=-4.0, revenue_cum_yoy=-5.0,
                       revenue_growth_streak=0, volume=0, ma20_bias=4.0,
                       volume_divergence=False, obv_rising=None)
    ScoringManager.RESEARCH_ARM = "B5"
    got = ScoringManager()._get_momentum_score(stock)
    assert got == pytest.approx(12.0 + 7.0 + 0.0 + 10.0)


def test_b2_removes_only_outer_whale_clip():
    stock = make_stock(foreign_net_ratio={1: 1.0}, trust_net_ratio={1: 1.0})
    scorer = ScoringManager()
    ScoringManager.RESEARCH_ARM = "B2"
    assert scorer._get_whale_score(stock) > 100.0


def test_b4_reweights_three_fundamental_groups_only():
    stock = make_stock(roe=20.0, net_margin=15.0, gross_margin=30.0,
                       rev_cagr=15.0, eps_cagr=20.0, debt_to_asset=30.0,
                       current_ratio=250.0, pe_vs_industry=30.0, volume=0)
    FundamentalEngine.RESEARCH_ARM = "B4"
    got = FundamentalEngine().evaluate(vars(stock))
    assert got["total_score"] == pytest.approx(100.0)
    assert got["group_scores"]["valuation"] == pytest.approx(0.0)


def test_c2_returns_base_weights_and_disables_dynamic_weight():
    stock = make_stock(current_price=110.0, ma5=100.0, ma20=90.0,
                       ma20_bias=10.0, rsi=60.0, volume=0)
    advisor = InvestmentAdvisor()
    base = dict(advisor.mode_weights)
    InvestmentAdvisor.RESEARCH_ARM = "C2"
    got, dyn = advisor._dynamic_weights(stock, base)
    assert got == base
    assert dyn is False


def test_apply_arm_resets_second_batch_flags_between_arms():
    panel.apply_arm("B3")
    assert ScoringManager.RESEARCH_ARM == "B3"
    panel.apply_arm("B4")
    assert ScoringManager.RESEARCH_ARM is None
    assert FundamentalEngine.RESEARCH_ARM == "B4"
    panel.apply_arm("C2")
    assert FundamentalEngine.RESEARCH_ARM is None
    assert InvestmentAdvisor.RESEARCH_ARM == "C2"
