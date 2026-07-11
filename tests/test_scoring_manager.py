import pytest

from core.scoring_manager import ScoringManager


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        ScoringManager(mode="yolo")


@pytest.mark.parametrize("mode", ["conservative", "aggressive", "balanced"])
def test_valid_modes_construct(mode):
    sm = ScoringManager(mode=mode)
    assert sm.config["weights"]["technical"] + sm.config["weights"]["momentum"] + sm.config["weights"]["whale"] == pytest.approx(1.0)


class TestTechnicalScore:
    def setup_method(self):
        self.sm = ScoringManager(mode="balanced")

    def test_perfect_alignment_maxes_out_ma_structure(self, stock_factory):
        stock = stock_factory(current_price=110, ma5=105, ma20=100, weekly_ma20=90,
                               rsi=60, macd_status="bullish_strong", bb_status="squeezing")
        score = self.sm._get_technical_score(stock)
        # 30 (均線) + 15 (週線) + 25 (RSI 50-70) + 20 (MACD strong) + 8 (squeeze) = 98
        assert score == 98.0

    def test_all_bearish_scores_zero(self, stock_factory):
        stock = stock_factory(current_price=90, ma5=95, ma20=100, weekly_ma20=110,
                               rsi=20, macd_status="bearish", bb_status="")
        score = self.sm._get_technical_score(stock)
        assert score == 0.0

    @pytest.mark.parametrize("rsi,expected_component", [
        (55, 25),   # 健康偏強
        (45, 18),   # 中性偏弱
        (72, 15),   # 過熱但可接受
        (35, 10),   # 偏弱
        (80, 8),    # 過熱只給少量
        (20, 0),    # 超弱
    ])
    def test_rsi_bands(self, stock_factory, rsi, expected_component):
        # 其餘因子全部歸零，只留 RSI 貢獻
        stock = stock_factory(current_price=90, ma5=95, ma20=100, weekly_ma20=0,
                               rsi=rsi, macd_status="bearish", bb_status="")
        score = self.sm._get_technical_score(stock)
        assert score == expected_component

    def test_score_never_exceeds_100_even_if_components_overflow(self, stock_factory):
        stock = stock_factory(current_price=110, ma5=105, ma20=100, weekly_ma20=90,
                               rsi=60, macd_status="bullish_strong", bb_status="squeezing")
        score = self.sm._get_technical_score(stock)
        assert score <= 100.0


class TestMomentumScore:
    def setup_method(self):
        self.sm = ScoringManager(mode="balanced")

    def test_zero_liquidity_low_volume_floor(self, stock_factory):
        stock = stock_factory(change_percent=-5, volume=100, volume_spike=0.5, ma20_bias=-20)
        score = self.sm._get_momentum_score(stock)
        assert score == 0.0

    def test_full_momentum_breakout(self, stock_factory):
        stock = stock_factory(change_percent=8, volume=1000, volume_spike=3.0, ma20_bias=5)
        score = self.sm._get_momentum_score(stock)
        # 35 (漲幅) + 35 (爆量) + 30 (健康正乖離) = 100
        assert score == 100.0

    def test_low_volume_zombie_stock_capped_regardless_of_spike_ratio(self, stock_factory):
        # 量能太小 (< 200 張)，即使 spike 比率很高也不該被視為有效爆量
        stock = stock_factory(change_percent=0.5, volume=50, volume_spike=10.0, ma20_bias=0)
        score = self.sm._get_momentum_score(stock)
        # 13 (漲幅 0<c<=2) + 0 (量能太小，兩個門檻都不到) + 22 (貼近均線) = 35
        assert score == 35.0

    @pytest.mark.parametrize("bias,expected", [
        (5, 30),    # 溫和偏多
        (10, 20),   # 偏強
        (-3, 22),   # 貼均線整理
        (20, 8),    # 過度正乖離
        (-8, 12),   # 弱勢超跌
        (-15, 0),   # 明顯破線
    ])
    def test_bias_bands(self, stock_factory, bias, expected):
        stock = stock_factory(change_percent=-3, volume=50, volume_spike=1.0, ma20_bias=bias)
        score = self.sm._get_momentum_score(stock)
        assert score == expected


class TestWhaleScore:
    def setup_method(self):
        self.sm = ScoringManager(mode="balanced")

    def test_no_activity_scores_zero(self, stock_factory):
        stock = stock_factory(institutional_buy_days=0, foreign_buy_days=0,
                               institutional_sell_days=0, foreign_sell_days=0)
        assert self.sm._get_whale_score(stock) == 0.0

    def test_both_buying_gets_combo_bonus(self, stock_factory):
        stock = stock_factory(institutional_buy_days=3, foreign_buy_days=3,
                               institutional_sell_days=0, foreign_sell_days=0)
        # trust=60, foreign=60 -> (30+30)+15 = 75
        assert self.sm._get_whale_score(stock) == 75.0

    def test_selling_penalty_can_drive_score_to_zero_floor(self, stock_factory):
        stock = stock_factory(institutional_buy_days=0, foreign_buy_days=0,
                               institutional_sell_days=10, foreign_sell_days=10)
        # combined = 0 - 80 - 60 = -140 -> clamp 0
        assert self.sm._get_whale_score(stock) == 0.0

    def test_buy_days_saturate_at_5_days(self, stock_factory):
        stock = stock_factory(institutional_buy_days=5, foreign_buy_days=0,
                               institutional_sell_days=0, foreign_sell_days=0)
        stock_more = stock_factory(institutional_buy_days=10, foreign_buy_days=0,
                                    institutional_sell_days=0, foreign_sell_days=0)
        # 兩者都應該被 min(...,100) 封頂在同一個 whale_score
        assert self.sm._get_whale_score(stock) == self.sm._get_whale_score(stock_more)


class TestCalculateScoreIntegration:
    def test_weights_apply_correctly_and_round(self, stock_factory):
        sm = ScoringManager(mode="aggressive")
        stock = stock_factory()
        result = sm.calculate_score(stock)
        w = sm.config["weights"]  # 直接讀當前模式權重,避免測試跟 MODES 設定脫鉤
        expected_total = round(
            result.technical_score * w["technical"]
            + result.momentum_score * w["momentum"]
            + result.whale_score * w["whale"], 2
        )
        assert result.total_score == expected_total
        assert result.symbol == stock.symbol
        assert result.name == stock.name

    def test_comment_flags_whale_combo_and_selling(self, stock_factory):
        sm = ScoringManager(mode="balanced")
        stock = stock_factory(institutional_buy_days=5, foreign_buy_days=5,
                               institutional_sell_days=0, foreign_sell_days=2,
                               current_price=110, ma5=105, ma20=100)
        result = sm.calculate_score(stock)
        assert "土洋法人強力聯手" in result.summary
        assert "法人調節中" in result.summary

    def test_comment_defaults_to_consolidation_when_no_signals(self, stock_factory):
        sm = ScoringManager(mode="balanced")
        stock = stock_factory(institutional_buy_days=0, foreign_buy_days=0,
                               institutional_sell_days=0, foreign_sell_days=0,
                               current_price=90, ma5=95, ma20=100)
        result = sm.calculate_score(stock)
        assert "目前處於盤整震盪格局" in result.summary
