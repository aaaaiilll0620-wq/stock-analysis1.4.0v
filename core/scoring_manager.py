from typing import Dict, List
from core.models import StockData, ScoreResult

class ScoringManager:
    MODES = {
        "conservative": {
            # 保守:仍重技術/籌碼穩定,但動能與籌碼佔比已拉高,估值/基本面退居確認角色
            "weights": {"technical": 0.42, "momentum": 0.28, "whale": 0.30},
            # 五大類綜合權重 (基本面/估值/技術/動能/籌碼),用於 advisor 綜合分
            "composite_weights": {"fundamental": 0.28, "valuation": 0.17,
                                  "technical": 0.20, "momentum": 0.16, "whale": 0.19},
            "min_score": 64,
            "description": "順勢為主、估值退居確認;門檻略高。"
        },
        "aggressive": {
            # 積極:動能與籌碼點火主導,估值權重壓到最低
            "weights": {"technical": 0.22, "momentum": 0.50, "whale": 0.28},
            "composite_weights": {"fundamental": 0.12, "valuation": 0.08,
                                  "technical": 0.22, "momentum": 0.34, "whale": 0.24},
            "min_score": 55,
            "description": "動能突破 + 籌碼點火主導,估值最輕;門檻低。"
        },
        "balanced": {
            # 平衡:綜合權重改依『因子歸因』(2023–2025, Rank IC) 校準:
            #   基本面 IC +0.176 (最強) → 大幅加重;技術 IC +0.051 → 微加重;
            #   動能 IC −0.027、單因子多空 −1.26% (反向拖累) → 大幅降權;
            #   估值 IC +0.049 但留一貢獻 −0.76% (冗餘) → 略降;籌碼 IC +0.028 (弱) → 略降。
            #   同時把高分維度 (基本面/技術) 加重會抬升 composite 中位數 → 緩解分數門檻瓶頸。
            "weights": {"technical": 0.32, "momentum": 0.38, "whale": 0.30},
            "composite_weights": {"fundamental": 0.30, "valuation": 0.10,
                                  "technical": 0.26, "momentum": 0.16, "whale": 0.18},
            "min_score": 54,
            "description": "以基本面+技術為排序核心 (因子歸因校準),動能/估值退居確認。"
        }
    }

    def __init__(self, mode: str = "balanced"):
        if mode not in self.MODES:
            raise ValueError(f"Unknown mode: {mode}")
        self.mode = mode
        self.config = self.MODES[mode]

    def calculate_score(self, data: StockData) -> ScoreResult:
        tech_score = self._get_technical_score(data)
        mom_score = self._get_momentum_score(data)
        whale_score = self._get_whale_score(data)

        w = self.config["weights"]
        total_score = (
            tech_score * w["technical"] +
            mom_score * w["momentum"] +
            whale_score * w["whale"]
        )
        total_score = round(total_score, 2)
        comment = self._generate_comment(data, total_score, tech_score, whale_score)

        return ScoreResult(
            symbol=data.symbol,
            name=data.name,
            total_score=total_score,
            technical_score=tech_score,
            momentum_score=mom_score,
            whale_score=whale_score,
            summary=comment
        )

    # ------------------------------------------------------------------
    # 技術面:多因子細分,不再兩個門檻就滿分
    # 配分:均線結構 30 + 週線趨勢 15 + RSI 位階 25 + MACD 20 + 布林 8 = 最高 98
    # ------------------------------------------------------------------
    def _get_technical_score(self, data: StockData) -> float:
        score = 0.0

        # (1) 短均線結構 (最多 30)
        if data.current_price > data.ma5:  score += 10
        if data.ma5 > data.ma20:           score += 10
        if data.current_price > data.ma20: score += 10

        # (2) 週線中期趨勢 (15):站上週線 MA20 代表中期偏多
        if data.weekly_ma20 > 0 and data.current_price > data.weekly_ma20:
            score += 15

        # (3) RSI 位階 (最多 25):健康偏強加分,過熱/超弱扣分
        rsi = data.rsi
        if 50 <= rsi <= 70:      score += 25
        elif 40 <= rsi < 50:     score += 18
        elif 70 < rsi <= 75:     score += 15
        elif 30 <= rsi < 40:     score += 10
        elif rsi > 75:           score += 8    # 過熱僅給少量
        # rsi < 30 給 0

        # (4) MACD 動能 (最多 20)
        if data.macd_status == "bullish_strong":
            score += 20
        elif data.macd_status == "bullish_recovery" or data.macd_golden_cross:
            score += 15
        elif data.macd_status == "neutral":
            score += 8
        # bearish 給 0

        # (5) 布林帶狀態 (最多 8):收斂視為潛在突破前兆給小分
        if data.bb_status == "squeezing":
            score += 8
        elif data.bb_status == "expanding":
            score += 5

        # (6) MA 20/60 交叉 (中長期趨勢確認;預設 neutral 不動分)
        if data.ma_cross_status == "golden_cross":
            score += 6          # 20 站上 60,中期轉多
        elif data.ma_cross_status == "death_cross":
            score -= 8          # 20 跌破 60,中期轉空

        return min(max(score, 0.0), 100.0)

    # ------------------------------------------------------------------
    # 動能面:漲跌幅與量能分級(單位:張),不再兩個 50 分門檻就滿分
    # ------------------------------------------------------------------
    def _get_momentum_score(self, data: StockData) -> float:
        """
        動能面 (重建版 — 因子歸因驅動)。
        背景:因子歸因顯示舊版『單日漲跌幅 + 量能爆發』的動能分 Rank IC 為負 (−0.027)、
              單因子多空 −1.26% —— 那是『短線追高偵測器』,在台股會被短線反轉打臉。
        改以兩個正向、較穩定的來源為核心,單日訊號退居確認:
          (A) 中期價格動能 (近3~6個月相對強度) — 正向動能因子的主體。      最多 45
          (B) 營收動能 (加速度 / 累計年增 / 連續成長月數) — 成長領先指標。   最多 30
          (C) 短線確認與健康度 (量能 + 乖離 + 量價背離抑制) — 僅作確認。     最多 25
        """
        score = 0.0

        # ---- (A) 中期價格動能 (最多 45):近6月為主 + 近3月確認 ----
        m6 = data.mom_6m or 0.0
        m3 = data.mom_3m or 0.0
        if   m6 > 40:   score += 30
        elif m6 > 25:   score += 25
        elif m6 > 12:   score += 19
        elif m6 > 3:    score += 12
        elif m6 > -8:   score += 6
        # 近6月 <= -8% (中期弱勢) 給 0
        if   m3 > 20:   score += 15
        elif m3 > 8:    score += 11
        elif m3 > 0:    score += 7
        elif m3 > -8:   score += 3
        # 動能衰竭抑制:近6月仍強、但近3月已明顯轉弱 → 趨勢轉折,扣分
        if m6 > 12 and m3 < -5:
            score -= 8

        # ---- (B) 營收動能 (最多 30):台股最即時的成長領先指標,較價格動能穩定 ----
        accel = data.revenue_accel
        cum = data.revenue_cum_yoy
        streak = data.revenue_growth_streak or 0
        if accel is not None:
            if   accel > 8:    score += 14   # 成長加速
            elif accel > 2:    score += 10
            elif accel > -2:   score += 5
            # accel <= -2 (成長減速) 給 0
        if cum is not None:
            if   cum > 25:     score += 10
            elif cum > 10:     score += 7
            elif cum > 0:      score += 4
        if   streak >= 6:      score += 6
        elif streak >= 3:      score += 3

        # ---- (C) 短線確認與健康度 (最多 25):量能 + 乖離,退居確認角色 ----
        v = data.volume
        spike = data.volume_spike if data.volume_spike else 1.0
        if v >= 500:
            if   spike > 2.0:  score += 10
            elif spike > 1.3:  score += 7
            elif spike > 0.8:  score += 4
        b = data.ma20_bias
        if   0 < b <= 8:       score += 10   # 溫和偏多,最健康
        elif -5 <= b <= 0:     score += 8    # 貼均線整理
        elif 8 < b <= 15:      score += 5    # 稍追高
        elif b > 15:           score += 1    # 過度追高
        elif -12 <= b < -5:    score += 3
        # 量價背離 / 過熱抑制 (追高警訊)
        if data.volume_divergence:
            score -= 5
        elif data.obv_rising is True:
            score += 5
        if data.kd_j > 100:
            score -= 3

        return min(max(score, 0.0), 100.0)

    # ------------------------------------------------------------------
    # 籌碼面:雙法人連買加分,並對連續賣超扣分
    # ------------------------------------------------------------------
    def _get_whale_score(self, data: StockData) -> float:
        trust_days = data.institutional_buy_days
        foreign_days = data.foreign_buy_days
        trust_sell = data.institutional_sell_days
        foreign_sell = data.foreign_sell_days

        # 每連買 1 天 20 分,最高 100
        trust_score = min(trust_days * 20.0, 100.0)
        foreign_score = min(foreign_days * 20.0, 100.0)

        # 土洋通吃(兩者同時買進)額外加分
        if trust_days > 0 and foreign_days > 0:
            combined = (trust_score * 0.5) + (foreign_score * 0.5) + 15.0
        else:
            combined = (trust_score * 0.5) + (foreign_score * 0.5)

        # 【新增】連續賣超懲罰:投信殺傷力略高於外資
        combined -= trust_sell * 8.0 + foreign_sell * 6.0

        # 【v3 籌碼微調】有界疊加 (最多 ±25):剔除自營商雜訊,改以短天期淨流向、
        #   投信吸籌、法人參與度、買超力道放大為主 —— 對中小型主力股更敏感。
        adj = 0.0
        # 主力動態:外資+投信近5日淨買超(領先訊號)
        if data.large_holder_activity > 0:
            adj += 8.0
        elif data.large_holder_activity < 0:
            adj -= 8.0
        # 外資 / 投信 近10日淨流向
        if data.foreign_flow > 0:
            adj += 4.0
        elif data.foreign_flow < 0:
            adj -= 4.0
        if data.trust_flow > 0:
            adj += 4.0
        elif data.trust_flow < 0:
            adj -= 4.0
        # 買超力道放大:近5日日均 > 近20日日均 (加速吸籌),僅在淨買時獎勵
        if data.large_holder_activity > 0 and data.flow_acceleration >= 1.5:
            adj += 5.0
        # 投信吸籌比:投信近20日吸走越多流通股 = 中小型股籌碼高度集中 (只獎勵,不因大型股天生低而懲罰)
        if data.whale_concentration >= 1.0:
            adj += 8.0
        elif data.whale_concentration >= 0.3:
            adj += 4.0
        # 法人成交占比:法人主導盤面
        if data.institutional_participation >= 40.0:
            adj += 4.0
        elif data.institutional_participation >= 25.0:
            adj += 2.0
        # 成交量集中度:量能集中上漲/下跌
        if data.volume_concentration >= 55.0:
            adj += 3.0
        elif 0.0 < data.volume_concentration < 45.0:
            adj -= 3.0
        adj = max(-25.0, min(25.0, adj))

        # 【TDCC 確認層】大戶佔比「週變化」——預設關閉時此值為 0、不影響分數。
        #   獨立 ±8 有界,與日線訊號分開:週增=大戶回補確認,週減=調節。
        #   背離警示:日線主力在買、但千張大戶卻週減 (趁強出貨) → 額外扣分。
        tdcc_adj = 0.0
        wchg = data.big_holder_weekly_change
        if wchg > 0:
            tdcc_adj += min(wchg * 4.0, 8.0)
        elif wchg < 0:
            tdcc_adj += max(wchg * 4.0, -8.0)
            if data.large_holder_activity > 0:
                tdcc_adj -= 3.0          # 背離:買盤 vs 大戶出貨
        tdcc_adj = max(-8.0, min(8.0, tdcc_adj))

        return min(max(combined + adj + tdcc_adj, 0.0), 100.0)

    def _generate_comment(self, data: StockData, total: float, tech: float, whale: float) -> str:
        status_tags = []

        if whale > 70:
            status_tags.append(
                f"土洋法人強力聯手 (投信連買{data.institutional_buy_days}天/外資連買{data.foreign_buy_days}天)"
            )
        elif data.institutional_buy_days > 0:
            status_tags.append(f"投信內資鎖碼連買{data.institutional_buy_days}天")

        # 賣超警示(即使連買為 0,也能看出是否正在被調節)
        if data.institutional_sell_days > 0 or data.foreign_sell_days > 0:
            status_tags.append(
                f"⚠️法人調節中 (投信連賣{data.institutional_sell_days}天/外資連賣{data.foreign_sell_days}天)"
            )

        if tech > 70:
            status_tags.append("技術面短均線多頭排列")

        tags_str = "，".join(status_tags) if status_tags else "目前處於盤整震盪格局"
        return f"綜合評分 {total} 分。{tags_str}。"
