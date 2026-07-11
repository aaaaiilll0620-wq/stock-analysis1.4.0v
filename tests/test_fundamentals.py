import math

import pytest

from core.fundamentals import FundamentalEngine


def good_data(**overrides):
    """一組能通過所有硬門檻、分數中上的基本面資料。"""
    base = dict(
        roe=15.0, net_margin=10.0, gross_margin=25.0,
        rev_cagr=8.0, eps_cagr=10.0,
        debt_to_asset=40.0, current_ratio=150.0,
        pe_vs_industry=15.0, cash_quality=1.0,
        revenue_growth=8.0, net_income_growth=10.0,
        operating_cash_flow=1000.0, free_cash_flow=500.0,
        net_income=800.0, ocf_to_net_income=1.25,
    )
    base.update(overrides)
    return base


class TestHardFilters:
    def setup_method(self):
        self.engine = FundamentalEngine()

    def test_passes_when_all_metrics_healthy(self):
        result = self.engine.evaluate(good_data())
        assert result["is_passed"] is True
        assert result["reasons"] == []

    def test_fails_when_debt_to_asset_too_high(self):
        result = self.engine.evaluate(good_data(debt_to_asset=90.0))
        assert result["is_passed"] is False
        assert any("Debt too high" in r for r in result["reasons"])

    def test_fails_when_current_ratio_too_low(self):
        result = self.engine.evaluate(good_data(current_ratio=30.0))
        assert result["is_passed"] is False
        assert any("Current ratio too low" in r for r in result["reasons"])

    def test_fails_when_net_margin_severely_negative(self):
        result = self.engine.evaluate(good_data(net_margin=-20.0))
        assert result["is_passed"] is False
        assert any("Net margin too low" in r for r in result["reasons"])

    def test_missing_core_field_fails_and_is_tracked(self):
        result = self.engine.evaluate(good_data(debt_to_asset=None))
        assert result["is_passed"] is False
        assert "debt_to_asset" in result["missing_fields"]
        assert any("Missing core debt_to_asset" in r for r in result["reasons"])

    def test_poor_cash_quality_fails_even_if_core_metrics_ok(self):
        result = self.engine.evaluate(good_data(cash_quality=0.2))
        assert result["is_passed"] is False
        assert any("Poor cash flow quality" in r for r in result["reasons"])

    def test_missing_non_core_cash_quality_does_not_fail(self):
        result = self.engine.evaluate(good_data(cash_quality=None))
        assert result["is_passed"] is True


class TestScoring:
    def setup_method(self):
        self.engine = FundamentalEngine()

    def test_weights_are_normalized_to_one(self):
        engine = FundamentalEngine(weights={"profitability": 3, "growth": 1, "safety": 1, "valuation": 1})
        assert sum(engine.weights.values()) == pytest.approx(1.0)

    def test_extreme_good_values_score_near_100(self):
        result = self.engine.evaluate(good_data(
            roe=25, net_margin=20, gross_margin=40,
            rev_cagr=20, eps_cagr=25,
            debt_to_asset=20, current_ratio=300,
            pe_vs_industry=5,
        ))
        assert result["total_score"] > 90

    def test_extreme_bad_values_within_hard_limits_score_near_zero(self):
        # 仍要過硬門檻 (debt<=85, current_ratio>=50, net_margin>=-10)
        result = self.engine.evaluate(good_data(
            roe=0, net_margin=-10, gross_margin=5,
            rev_cagr=-10, eps_cagr=0,
            debt_to_asset=80, current_ratio=55,
            pe_vs_industry=35,
        ))
        assert result["total_score"] < 15

    def test_missing_value_scores_zero_for_that_metric(self):
        v = self.engine._calculate_score(None, {"lower": 0, "upper": 100})
        assert v == 0.0

    def test_sentinel_minus_999_scores_zero(self):
        v = self.engine._calculate_score(-999, {"lower": 0, "upper": 100})
        assert v == 0.0

    def test_reverse_scoring_when_lower_greater_than_upper(self):
        # debt_to_asset: lower=60(0分) upper=30(100分)，數字越小分數越高
        bounds = {"lower": 60.0, "upper": 30.0}
        assert self.engine._calculate_score(60.0, bounds) == 0.0
        assert self.engine._calculate_score(30.0, bounds) == 100.0
        assert self.engine._calculate_score(45.0, bounds) == pytest.approx(50.0)


class TestProfitQuality:
    def setup_method(self):
        self.engine = FundamentalEngine()

    def test_does_not_flag_risk_when_growth_gap_large_but_operating_ratio_missing(self):
        result = self.engine._evaluate_profit_quality({
            "revenue_growth": 5.0, "net_income_growth": 40.0
        })
        assert result["risk"] is False
        assert "缺本業獲利占比資料" in result["note"]

    def test_no_risk_when_operating_profit_ratio_above_80pct(self):
        result = self.engine._evaluate_profit_quality({
            "revenue_growth": 32.8, "net_income_growth": 99.7, "operating_profit_ratio": 0.85
        })
        assert result["risk"] is False
        assert result.get("operating_leverage") is True
        assert "本業獲利爆發" in result["note"]

    def test_flags_risk_when_operating_profit_ratio_below_80pct(self):
        result = self.engine._evaluate_profit_quality({
            "revenue_growth": 5.0, "net_income_growth": 40.0, "operating_profit_ratio": 0.65
        })
        assert result["risk"] is True
        assert "<80%" in result["note"]

    def test_flags_divergence_when_net_income_negative_but_revenue_positive(self):
        result = self.engine._evaluate_profit_quality({
            "revenue_growth": 5.0, "net_income_growth": -10.0
        })
        assert result["risk"] is True
        assert "獲利品質背離" in result["note"]

    def test_no_risk_when_growth_rates_aligned(self):
        result = self.engine._evaluate_profit_quality({
            "revenue_growth": 10.0, "net_income_growth": 12.0
        })
        assert result["risk"] is False

    def test_missing_growth_data_notes_but_does_not_crash(self):
        result = self.engine._evaluate_profit_quality({})
        assert result["risk"] is False
        assert "缺營收/淨利年增率" in result["note"]

    @pytest.mark.parametrize("gross,moat", [
        (50, "強護城河"),
        (25, "中等護城河"),
        (5, "弱護城河"),
    ])
    def test_moat_classification(self, gross, moat):
        result = self.engine._evaluate_profit_quality({"gross_margin": gross})
        assert result["moat"] == moat


class TestCashFlowHealth:
    def setup_method(self):
        self.engine = FundamentalEngine()

    def test_negative_ocf_is_high_risk(self):
        result = self.engine._evaluate_cash_flow_health({"operating_cash_flow": -100.0})
        assert result["risk_level"] == "high_risk"

    def test_missing_ocf_returns_unknown(self):
        result = self.engine._evaluate_cash_flow_health({})
        assert result["risk_level"] == "unknown"

    def test_low_cash_conversion_ratio_is_watch(self):
        result = self.engine._evaluate_cash_flow_health({
            "operating_cash_flow": 100.0, "net_income": 1000.0
        })
        # ratio = 0.1 < 0.5 threshold
        assert result["risk_level"] == "watch"

    def test_negative_fcf_downgrades_healthy_to_watch(self):
        result = self.engine._evaluate_cash_flow_health({
            "operating_cash_flow": 1000.0, "net_income": 800.0, "free_cash_flow": -50.0
        })
        assert result["risk_level"] == "watch"

    def test_all_healthy_when_no_red_flags(self):
        result = self.engine._evaluate_cash_flow_health({
            "operating_cash_flow": 1000.0, "net_income": 800.0, "free_cash_flow": 500.0
        })
        assert result["risk_level"] == "healthy"
        assert "健康" in result["notes"][0]


class TestQualityFlagComposition:
    def setup_method(self):
        self.engine = FundamentalEngine()

    def test_flag_reflects_hard_fail(self):
        flag = self.engine._compose_quality_flag({}, {"risk_level": "unknown"}, is_passed=False)
        assert "⚠️未過基本面門檻" in flag

    def test_flag_defaults_to_insufficient_when_nothing_notable(self):
        flag = self.engine._compose_quality_flag({}, {}, is_passed=True)
        assert flag == "數據不足"


class TestConfidenceScore:
    def setup_method(self):
        self.engine = FundamentalEngine()

    def test_confidence_100_when_nothing_missing(self):
        result = self.engine.evaluate(good_data())
        assert result["confidence"] == 100.0

    def test_confidence_drops_per_missing_field(self):
        result = self.engine.evaluate(good_data(eps_cagr=None))
        assert result["confidence"] < 100.0

    def test_confidence_floors_at_zero(self):
        result = self.engine.evaluate({})
        assert result["confidence"] >= 0.0
        assert result["is_passed"] is False
