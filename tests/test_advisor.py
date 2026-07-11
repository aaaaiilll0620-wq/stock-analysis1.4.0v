import pytest

from core.advisor import InvestmentAdvisor
from core.models import ScoreResult


def make_score_result(total_score=70.0, technical_score=70.0, momentum_score=70.0, whale_score=70.0):
    return ScoreResult(
        symbol="2330", name="台積電", total_score=total_score,
        technical_score=technical_score, momentum_score=momentum_score,
        whale_score=whale_score, summary="test"
    )


FUND_OK = {
    "is_passed": True,
    "cash_flow_health": {"risk_level": "healthy", "notes": ["健康"]},
    "profit_quality": {"risk": False, "note": "", "moat": "中等護城河"},
    "quality_flag": "現金流健康",
    "confidence": 100.0,
    "reasons": [],
}

VAL_CHEAP = {"valuation_status": "估值偏低 (便宜)", "valuation_score": 80.0, "confidence": 100.0}
VAL_FAIR = {"valuation_status": "估值合理", "valuation_score": 55.0, "confidence": 100.0}
VAL_EXPENSIVE = {"valuation_status": "估值偏高 (昂貴)", "valuation_score": 20.0, "confidence": 100.0}


class TestDecideRating:
    def setup_method(self):
        self.advisor = InvestmentAdvisor(min_score=60.0)

    def test_hard_fail_forces_avoid(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=2)
        fund = dict(FUND_OK, is_passed=False)
        score = make_score_result(total_score=90)
        rating = self.advisor._decide_rating(stock, fund, VAL_CHEAP, score)
        assert rating == self.advisor.RATING_AVOID

    def test_cash_high_risk_forces_avoid(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=2)
        fund = dict(FUND_OK, cash_flow_health={"risk_level": "high_risk", "notes": ["負現金流"]})
        score = make_score_result(total_score=90)
        rating = self.advisor._decide_rating(stock, fund, VAL_CHEAP, score)
        assert rating == self.advisor.RATING_AVOID

    def test_expensive_and_low_score_forces_avoid(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=2)
        score = make_score_result(total_score=30)
        rating = self.advisor._decide_rating(stock, FUND_OK, VAL_EXPENSIVE, score)
        assert rating == self.advisor.RATING_AVOID

    def test_broken_momentum_with_oversold_rsi_forces_avoid(self, stock_factory):
        stock = stock_factory(rsi=25, ma20_bias=-10)
        score = make_score_result(total_score=70, momentum_score=10)
        rating = self.advisor._decide_rating(stock, FUND_OK, VAL_FAIR, score)
        assert rating == self.advisor.RATING_AVOID

    def test_all_three_pillars_aligned_gives_strong(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=5)
        score = make_score_result(total_score=70)
        rating = self.advisor._decide_rating(stock, FUND_OK, VAL_CHEAP, score)
        assert rating == self.advisor.RATING_STRONG

    def test_below_min_score_downgrades_to_watch(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=5)
        score = make_score_result(total_score=40)  # below min_score=60
        rating = self.advisor._decide_rating(stock, FUND_OK, VAL_CHEAP, score)
        assert rating == self.advisor.RATING_WATCH

    def test_profit_quality_risk_downgrades_to_watch(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=5)
        fund = dict(FUND_OK, profit_quality={"risk": True, "note": "獲利品質存疑", "moat": "未知"})
        score = make_score_result(total_score=70)
        rating = self.advisor._decide_rating(stock, fund, VAL_CHEAP, score)
        assert rating == self.advisor.RATING_WATCH

    def test_chasing_high_bias_downgrades_to_watch(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=20)  # > bias_chase(15)
        score = make_score_result(total_score=70)
        rating = self.advisor._decide_rating(stock, FUND_OK, VAL_CHEAP, score)
        assert rating == self.advisor.RATING_WATCH


class TestGenerateAdvice:
    def setup_method(self):
        self.advisor = InvestmentAdvisor(min_score=60.0)

    def test_hard_fail_advice_mentions_reason(self, stock_factory):
        stock = stock_factory()
        fund = dict(FUND_OK, is_passed=False, reasons=["Debt too high: 90%"])
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, fund, VAL_FAIR, score, self.advisor.RATING_AVOID)
        assert "未通過基本面安全門檻" in advice
        assert "Debt too high" in advice

    def test_cash_risk_advice_mentions_red_flag(self, stock_factory):
        stock = stock_factory()
        fund = dict(FUND_OK, cash_flow_health={"risk_level": "high_risk", "notes": ["營業現金流為負"]})
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, fund, VAL_FAIR, score, self.advisor.RATING_AVOID)
        assert "財務體質亮紅燈" in advice

    def test_profit_risk_advice(self, stock_factory):
        stock = stock_factory()
        fund = dict(FUND_OK, profit_quality={"risk": True, "note": "獲利動態風險：淨利虛增", "moat": "未知"})
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, fund, VAL_FAIR, score, self.advisor.RATING_WATCH)
        assert "獲利動態風險" in advice

    def test_breakout_signal_advice(self, stock_factory):
        stock = stock_factory(volume_spike=3.0, change_percent=5, current_price=110, ma20=100, ma20_bias=5)
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, FUND_OK, VAL_FAIR, score, self.advisor.RATING_STRONG)
        assert "成交量異常放大" in advice

    def test_overbought_advice_for_strong_or_watch_rating(self, stock_factory):
        stock = stock_factory(rsi=80, ma20_bias=5, volume_spike=1.0, change_percent=1)
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, FUND_OK, VAL_FAIR, score, self.advisor.RATING_WATCH)
        assert "超買區" in advice

    def test_expensive_valuation_advice(self, stock_factory):
        stock = stock_factory(rsi=50, ma20_bias=2, volume_spike=1.0, change_percent=1)
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, FUND_OK, VAL_EXPENSIVE, score, self.advisor.RATING_WATCH)
        assert "估值偏貴" in advice

    def test_strong_rating_normal_advice_mentions_batch_entry(self, stock_factory):
        stock = stock_factory(rsi=50, ma20_bias=2, volume_spike=1.0, change_percent=1,
                               institutional_buy_days=3, foreign_buy_days=3)
        score = make_score_result()
        advice = self.advisor._generate_advice(stock, FUND_OK, VAL_CHEAP, score, self.advisor.RATING_STRONG)
        assert "分批布局" in advice
        assert "土洋法人同步進場" in advice

    def test_selling_pressure_advice(self, stock_factory):
        stock = stock_factory(rsi=50, ma20_bias=2, volume_spike=1.0, change_percent=1,
                               institutional_sell_days=3, foreign_sell_days=0)
        score = make_score_result(total_score=45)  # keep rating out of STRONG
        advice = self.advisor._generate_advice(stock, FUND_OK, VAL_FAIR, score, self.advisor.RATING_WATCH)
        assert "法人正在調節" in advice

    def test_default_advice_when_signals_are_mixed(self, stock_factory):
        stock = stock_factory(rsi=50, ma20_bias=2, volume_spike=1.0, change_percent=1)
        score = make_score_result(total_score=45)
        advice = self.advisor._generate_advice(stock, FUND_OK, VAL_FAIR, score, self.advisor.RATING_WATCH)
        assert "訊號分歧" in advice


class TestAdviseFullPipeline:
    def setup_method(self):
        self.advisor = InvestmentAdvisor(min_score=60.0)

    def test_advise_populates_score_result_fields(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=5)
        score = make_score_result(total_score=70)
        result = self.advisor.advise(stock, FUND_OK, VAL_CHEAP, score)
        assert result.rating == self.advisor.RATING_STRONG
        assert result.valuation_status == "估值偏低 (便宜)"
        assert result.valuation_score == 80.0
        assert result.quality_flag == "現金流健康"
        assert result.actionable_advice != ""
        assert result.data_confidence == 100.0

    def test_low_confidence_appends_manual_review_note(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=5, data_confidence=50.0)
        fund = dict(FUND_OK, confidence=50.0)
        score = make_score_result(total_score=70)
        result = self.advisor.advise(stock, fund, VAL_CHEAP, score)
        assert "資料完整度" in result.actionable_advice
        assert "僅 50%" in result.actionable_advice
        assert result.data_confidence == 50.0

    def test_confidence_takes_most_conservative_of_three_sources(self, stock_factory):
        stock = stock_factory(rsi=55, ma20_bias=5, data_confidence=90.0)
        fund = dict(FUND_OK, confidence=40.0)
        val = dict(VAL_CHEAP, confidence=95.0)
        score = make_score_result(total_score=70)
        result = self.advisor.advise(stock, fund, val, score)
        assert result.data_confidence == 40.0


class TestCompositeWeights:
    """五維度(基本面/估值/技術/動能/籌碼)加權合成 total_score，比重完全由 mode_weights 決定。"""

    def test_equal_component_scores_give_same_total_regardless_of_weights(self, stock_factory):
        # 五個分項都是 60 分時，不管權重怎麼分，加權平均都應該是 60。
        advisor = InvestmentAdvisor(min_score=60.0, mode_weights={
            "fundamental": 0.40, "valuation": 0.40,
            "technical": 0.069, "momentum": 0.031, "whale": 0.10,
        })
        stock = stock_factory(rsi=55, ma20_bias=2)
        fund = dict(FUND_OK, total_score=60.0)
        val = dict(VAL_FAIR, valuation_score=60.0)
        score = make_score_result(total_score=0.0, technical_score=60.0,
                                   momentum_score=60.0, whale_score=60.0)
        result = advisor.advise(stock, fund, val, score)
        assert result.total_score == pytest.approx(60.0)

    def test_weights_reflect_selected_mode(self, stock_factory):
        # 基本面 100 分、其餘 0 分：conservative(基本面40%) 應該比 aggressive(基本面5%) 的總分高很多。
        stock = stock_factory(rsi=55, ma20_bias=2)
        fund = dict(FUND_OK, total_score=100.0)
        val = dict(VAL_FAIR, valuation_score=0.0)

        conservative = InvestmentAdvisor(min_score=70.0, mode_weights={
            "fundamental": 0.40, "valuation": 0.40,
            "technical": 0.069, "momentum": 0.031, "whale": 0.10,
        })
        aggressive = InvestmentAdvisor(min_score=60.0, mode_weights={
            "fundamental": 0.05, "valuation": 0.05,
            "technical": 0.30, "momentum": 0.40, "whale": 0.20,
        })
        score_c = make_score_result(total_score=0.0, technical_score=0.0,
                                     momentum_score=0.0, whale_score=0.0)
        score_a = make_score_result(total_score=0.0, technical_score=0.0,
                                     momentum_score=0.0, whale_score=0.0)
        result_c = conservative.advise(stock, fund, val, score_c)
        result_a = aggressive.advise(stock, fund, val, score_a)
        assert result_c.total_score == pytest.approx(40.0)
        assert result_a.total_score == pytest.approx(5.0)
        assert result_c.total_score > result_a.total_score

    def test_missing_weight_keys_fall_back_to_default(self, stock_factory):
        # mode_weights 沒帶任何 key 時 (wsum<=0)，改用 DEFAULT_MODE_WEIGHTS，不應噴錯。
        advisor = InvestmentAdvisor(min_score=60.0, mode_weights={})
        stock = stock_factory(rsi=55, ma20_bias=2)
        score = make_score_result(total_score=0.0, technical_score=50.0,
                                   momentum_score=50.0, whale_score=50.0)
        val = dict(VAL_FAIR, valuation_score=50.0)
        result = advisor.advise(stock, dict(FUND_OK, total_score=50.0), val, score)
        assert result.total_score == pytest.approx(50.0)

    def test_insufficient_valuation_data_treated_as_neutral_50(self, stock_factory):
        # 估值資料不足 (score=0) 時，val_bucket 應以中性 50 計入總分，不把「沒資料」當「最貴」。
        advisor = InvestmentAdvisor(min_score=60.0, mode_weights={
            "fundamental": 0.0, "valuation": 1.0,
            "technical": 0.0, "momentum": 0.0, "whale": 0.0,
        })
        stock = stock_factory(rsi=55, ma20_bias=2)
        val_no_data = {"valuation_status": "估值資料不足", "valuation_score": 0.0, "confidence": 20.0}
        score = make_score_result(total_score=0.0)
        result = advisor.advise(stock, FUND_OK, val_no_data, score)
        assert result.total_score == pytest.approx(50.0)
