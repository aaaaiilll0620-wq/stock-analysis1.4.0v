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
    """v4.4 動能面（因子歸因重寫，見 core/scoring_manager._get_momentum_score 的 docstring）：
        A 中期價格動能（mom_6m / mom_3m，≤45） + B 營收動能（≤30） + C 短線量能/乖離確認（≤25）。
    舊版以 change_percent（單日漲幅）為核心，因 Rank IC 為負（−0.027，短線追高偵測器）於 2026-07-13
    v4.4 整段重寫；change_percent 已**完全不計分**。本測試同步改為鎖 v4.4 的三段分數帶。
    （舊測試假設 change_percent 驅動 35 分，是 v4.4 之前的公式。）
    """

    def setup_method(self):
        self.sm = ScoringManager(mode="balanced")

    # A/B/C 全部歸零的基準：中期動能<=-8（A=0）、營收全缺（B=0）、量能不足且明顯破線（C=0）。
    _ZERO = dict(mom_6m=-10.0, mom_3m=-10.0,
                 revenue_accel=None, revenue_cum_yoy=None, revenue_growth_streak=0,
                 volume=100, volume_spike=0.5, ma20_bias=-15.0)

    def _score(self, stock_factory, **ov):
        base = dict(self._ZERO)
        base.update(ov)
        return self.sm._get_momentum_score(stock_factory(**base))

    def test_all_weak_floors_at_zero(self, stock_factory):
        # 中期動能弱 + 無營收動能 + 量能不足 + 破線 → 觸地板 0
        assert self._score(stock_factory) == 0.0

    def test_full_breakout_maxes_at_100(self, stock_factory):
        # A 45（m6>40 +30、m3>20 +15）+ B 30（accel>8 +14、cum>25 +10、streak>=6 +6）
        #   + C 25（量能爆發 +10、健康乖離 +10、OBV 上升確認 +5）= 100
        s = self._score(stock_factory, mom_6m=50, mom_3m=25,
                        revenue_accel=10, revenue_cum_yoy=30, revenue_growth_streak=6,
                        volume=1000, volume_spike=3.0, ma20_bias=5, obv_rising=True)
        assert s == 100.0

    @pytest.mark.parametrize("m6,m3,expected", [
        (50, 25, 45),    # 近6月>40(+30) + 近3月>20(+15)
        (30, 10, 36),    # >25(+25) + >8(+11)
        (15, 1, 26),     # >12(+19) + >0(+7)
        (5, -1, 15),     # >3(+12) + >-8(+3)
        (-5, -6, 9),     # >-8(+6) + >-8(+3)
        (-10, -10, 0),   # 皆<=-8 → 0
        (30, -6, 20),    # 近6月強(+25)+近3月(+3) 但近3月轉弱觸發衰竭抑制(-8) = 20
    ])
    def test_midterm_price_momentum_bands(self, stock_factory, m6, m3, expected):
        # B=C 歸零（沿用 _ZERO 的 volume/spike/bias/營收），只驗 A 中期動能分量
        assert self._score(stock_factory, mom_6m=m6, mom_3m=m3) == expected

    @pytest.mark.parametrize("volume,spike,expected", [
        (1000, 3.0, 10),   # 量足 + 爆量(spike>2.0)
        (1000, 1.5, 7),    # 量足 + 放量(spike>1.3)
        (1000, 1.0, 4),    # 量足 + 微幅(spike>0.8)
        (1000, 0.8, 0),    # 量足但 spike 不到門檻
        (100, 5.0, 0),     # spike 很高但量能<500 → 不算有效爆量
    ])
    def test_volume_confirmation_bands(self, stock_factory, volume, spike, expected):
        # A=B=0、乖離=-15(0 分)，只驗 C 的量能確認分量
        assert self._score(stock_factory, volume=volume, volume_spike=spike) == expected

    def test_low_volume_zombie_spike_does_not_leak(self, stock_factory):
        # 量能太小（<500 張）即使 spike=10 也不給量能分；此處只剩健康乖離(+10)
        s = self._score(stock_factory, volume=50, volume_spike=10.0, ma20_bias=5)
        assert s == 10.0

    @pytest.mark.parametrize("bias,expected", [
        (5, 10),     # 溫和偏多 0<b<=8，最健康
        (3, 10),     # 同上帶
        (-3, 8),     # 貼均線整理 -5<=b<=0
        (0, 8),      # 邊界 0 落在 -5<=b<=0 帶
        (10, 5),     # 稍追高 8<b<=15
        (20, 1),     # 過度追高 b>15
        (-8, 3),     # 弱勢超跌 -12<=b<-5
        (-15, 0),    # 明顯破線 b<-12
    ])
    def test_bias_bands(self, stock_factory, bias, expected):
        # A=B=0、量能不足(volume=100)，只驗 C 的乖離分量
        assert self._score(stock_factory, ma20_bias=bias) == expected


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
