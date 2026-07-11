import pytest

from core.valuation import ValuationEngine


class TestScoreMetric:
    def setup_method(self):
        self.engine = ValuationEngine()

    def test_none_returns_none(self):
        assert self.engine._score_metric(None, {"lower": 0, "upper": 100}) is None

    def test_lower_bound_scores_zero_upper_scores_100(self):
        bounds = {"lower": 30.0, "upper": 8.0}
        assert self.engine._score_metric(30.0, bounds) == 0.0
        assert self.engine._score_metric(8.0, bounds) == 100.0

    def test_midpoint_scores_50(self):
        bounds = {"lower": 30.0, "upper": 8.0}
        assert self.engine._score_metric(19.0, bounds) == pytest.approx(50.0)

    def test_clamped_outside_range(self):
        bounds = {"lower": 30.0, "upper": 8.0}
        assert self.engine._score_metric(50.0, bounds) == 0.0
        assert self.engine._score_metric(0.0, bounds) == 100.0


class TestEvaluate:
    def setup_method(self):
        self.engine = ValuationEngine()

    def test_cheap_stock_classified_correctly(self):
        result = self.engine.evaluate({
            "pe_ratio": 8.0, "pb_ratio": 0.8, "price_to_sales": 0.5, "dividend_yield": 6.0
        })
        assert result["valuation_score"] == 100.0
        assert result["valuation_status"] == "估值偏低 (便宜)"
        assert result["missing_fields"] == []
        assert result["confidence"] == 100.0

    def test_expensive_stock_classified_correctly(self):
        result = self.engine.evaluate({
            "pe_ratio": 30.0, "pb_ratio": 4.0, "price_to_sales": 8.0, "dividend_yield": 0.5
        })
        # PE/PB/PS 皆觸下限得 0 分,殖利率 0.5% 依內插得 8.33 分 × 權重 0.2 = 1.67
        assert result["valuation_score"] == pytest.approx(1.67, abs=0.01)
        assert result["valuation_status"] == "估值偏高 (昂貴)"

    def test_dividend_yield_zero_is_treated_as_missing(self):
        result = self.engine.evaluate({
            "pe_ratio": 15.0, "pb_ratio": 2.0, "price_to_sales": 2.0, "dividend_yield": 0.0
        })
        assert "dividend_yield" in result["missing_fields"]
        assert result["inputs"]["dividend_yield"] is None

    def test_all_missing_gives_zero_score_and_no_data_status(self):
        result = self.engine.evaluate({})
        assert result["valuation_score"] == 0.0
        assert result["valuation_status"] == "估值資料不足"
        # confidence = max(0, 100 - 4個缺欄位*20) = 20，並非 0
        assert result["confidence"] == pytest.approx(20.0)
        assert set(result["missing_fields"]) == {"pe", "pb", "ps", "dividend_yield"}

    def test_partial_missing_reweights_available_metrics(self):
        # 只有 PE 資料，其餘缺失：valuation_score 應完全由 PE 決定 (100%權重)
        result = self.engine.evaluate({"pe_ratio": 8.0})
        assert result["valuation_score"] == 100.0
        assert result["confidence"] == pytest.approx(100.0 - 3 * 20.0)

    def test_confidence_never_negative(self):
        # 只有 4 個估值欄位，最多缺 4 個 -> confidence 下限為 20，但公式本身有 max(0, ...) 保護
        result = self.engine.evaluate({})
        assert result["confidence"] >= 0.0


class TestExpensiveClassification:
    """本益比歷史高檔時,用 PEG／營收成長交叉驗證「成長溢價」vs「昂貴泡泡」。"""

    def setup_method(self):
        self.engine = ValuationEngine()

    def test_high_percentile_with_low_peg_labeled_growth_premium(self):
        # PEG = 30/50 = 0.6 < 1，獲利有跟上股價 -> 成長溢價，分數不被砍
        result = self.engine.evaluate({
            "pe_ratio": 30.0, "pe_percentile": 97.0, "eps_cagr": 50.0,
        })
        assert result["valuation_label"] == "成長溢價"
        assert result["valuation_score"] > 8.0

    def test_high_percentile_with_strong_revenue_labeled_growth_premium(self):
        # 沒有正成長率可算 PEG，但月營收年增夠強 -> 一樣算成長溢價
        result = self.engine.evaluate({
            "pe_ratio": 30.0, "pe_percentile": 90.0, "revenue_cum_yoy": 25.0,
        })
        assert result["valuation_label"] == "成長溢價"

    def test_high_percentile_with_weak_growth_labeled_bubble_and_capped(self):
        # 本益比歷史高檔，成長資料存在但太弱 (營收年增 3% < 15%、無正 PEG) -> 昂貴泡泡，分數壓到 cap 以下
        result = self.engine.evaluate({
            "pe_percentile": 90.0, "pb_percentile": 10.0, "dividend_yield_percentile": 80.0,
            "revenue_cum_yoy": 3.0,
        })
        assert result["valuation_label"] == "昂貴泡泡"
        assert result["valuation_score"] <= self.engine.BUBBLE_SCORE_CAP

    def test_high_percentile_with_no_growth_data_not_labeled_bubble(self):
        # 本益比歷史高檔但成長資料全缺 -> 無法交叉驗證，不硬判泡泡也不砍分
        result = self.engine.evaluate({
            "pe_percentile": 90.0, "pb_percentile": 10.0, "dividend_yield_percentile": 80.0,
        })
        assert result["valuation_label"] == ""
        assert result["valuation_score"] > self.engine.BUBBLE_SCORE_CAP

    def test_low_percentile_no_label(self):
        # 本益比歷史位階不到門檻，不觸發成長溢價／泡泡分類
        result = self.engine.evaluate({
            "pe_ratio": 15.0, "pe_percentile": 50.0, "eps_cagr": 20.0,
        })
        assert result["valuation_label"] == ""

    def test_absolute_branch_has_empty_label(self):
        # 兩者(PEG/歷史位階)皆缺，退回絕對門檻分支，不應觸發分類
        result = self.engine.evaluate({"pe_ratio": 15.0, "pb_ratio": 2.0})
        assert result["valuation_label"] == ""
