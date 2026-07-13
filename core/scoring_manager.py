from typing import Dict, List
from core.models import StockData, ScoreResult

class ScoringManager:
    # ------------------------------------------------------------------
    # v4.4 候選訊號開關 (未來優化藍圖 7、10):每個訊號獨立 A/B
    # (scripts/factor_experiments.py,45檔池、月頻持有20日、全期+2022空頭雙段)。
    # 無資料 (欄位 None) 時一律不動分,live/舊快取相容。
    # A/B 結果 (綜合多空 全期/2022,基線 +2.63%/−0.95%):
    #   RS   +2.78%/−0.44% ✅ 過 (動能IC +0.077→+0.079,2022綜合止血) → 預設開
    #   KD   +2.53%/−1.09% ❌ 技術IC反而降 (0.011→0.004) → 關
    #   %B   +2.32%/−1.09% ❌ 兩段皆拖累 → 關
    #   OBV  +2.71%/−1.16% ❌ 全期小幅改善但2022明顯變差 → 關
    # ------------------------------------------------------------------
    USE_RS_OVERLAY = True     # 相對強弱 RS (個股中期報酬−0050 同期) 疊加進動能面
    USE_KD_FULL = False       # 完整 KD (K/D 相對位置) 進技術面 — 未過篩,保留供複測
    USE_BBP = False           # 布林 %B 位階進技術面 — 未過篩,保留供複測
    USE_OBV_TREND = False     # OBV 20日趨勢進動能面確認層 — 未過篩,保留供複測

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
            # v4.2 依 2023–2025 因子歸因重配 (balanced):
            #   動能 IC+0.077/多空+2.81%/留一+0.46 (最強單因子,原僅16%嚴重低配) → 加重至 0.27;
            #   估值 留一 −0.78 (拿掉反而更好) → 砍至 0.08;技術 留一 −0.03 (中性) → 降至 0.19;
            #   籌碼 弱但非負 (+0.05) → 微降至 0.15;基本面 留一 +0.41 (穩) → 維持 0.31。
            #   ⚠ 這是 in-sample 歸因,須經 --validate(train/test)+ --cycle(2021–22 空頭) 複驗才留。
            #   舊版(如需回退):fund .30 / val .10 / tech .26 / mom .16 / whale .18
            "composite_weights": {"fundamental": 0.31, "valuation": 0.08,
                                  "technical": 0.19, "momentum": 0.27, "whale": 0.15},
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

        # (7) 布林 %B 位階 (v4.4 候選):上半帶健康偏強加分,突破上軌過遠/貼下軌扣分
        if self.USE_BBP and data.bb_percent_b is not None:
            b = data.bb_percent_b
            if   0.5 <= b <= 0.95: score += 5
            elif b > 1.05:         score -= 4    # 衝出上軌過遠,過度擴張
            elif b < 0.05:         score -= 2    # 貼下軌弱勢

        # (8) 完整 KD (v4.4 候選):K>D 偏多且未過熱加分,K<D 且弱勢扣分
        if self.USE_KD_FULL:
            if data.kd_k > data.kd_d and 20.0 <= data.kd_j <= 90.0:
                score += 5
            elif data.kd_k < data.kd_d and data.kd_j < 20.0:
                score -= 3

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

        # ---- (A2) 相對強弱 RS 疊加 (v4.4 候選,±8 有界):跑贏大盤加分、明顯跑輸扣分 ----
        #   無 0050 快取 / 個股歷史不足 (rs_6m=None) → 不動分,維持相容。
        if self.USE_RS_OVERLAY and data.rs_6m is not None:
            r6 = data.rs_6m
            r3 = data.rs_3m if data.rs_3m is not None else 0.0
            if   r6 > 20 and r3 > 0:  score += 8    # 中期強勢跑贏且近3月仍領先
            elif r6 > 8:              score += 5
            elif r6 > 0:              score += 2
            elif r6 < -15:            score -= 6    # 明顯落後大盤 (弱勢股)
            elif r6 < -5:             score -= 3

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
        # OBV 20日趨勢 (v4.4 候選):比單日 obv_rising 穩;量能趨勢向上小加分、向下小扣分
        if self.USE_OBV_TREND and data.obv_above_ma20 is not None:
            score += 4 if data.obv_above_ma20 else -2

        return min(max(score, 0.0), 100.0)

    # ------------------------------------------------------------------
    # 籌碼面 (v4.2 重構):以「多天期法人淨參與率」為基底,連買天數降級為 bonus
    # ------------------------------------------------------------------
    #   背景:稽核 (item 1) 顯示舊版 whale 中位僅 26、37% 掛 0,主因是舊基底
    #   `連買天數×20` 是嚴格連續計數,大型股法人買賣交錯 → 天數恆為 0 → 基底塌陷。
    #   但 chip 資料完整,淨流向資訊被壓在 ±25 的 adj 裡浪費掉。
    #   重構:淨參與率 (net ÷ 同期量,signed、市值中性、幾乎不為0) 拉回當 0-100 基底,
    #        給出跨股 spread;連續買超天數改當小額 bonus (仍獎勵真正的持續吸籌)。
    #   天期 1/3/5/10/20 分開加權:短天期看即時、長天期看趨勢。
    _HORIZON_WEIGHTS = {1: 0.10, 3: 0.15, 5: 0.25, 10: 0.25, 20: 0.25}
    _RATIO_TO_POINTS = 300.0   # 淨參與率 → 分數斜率 (±0.1 淨參與 ≈ ±30 分);可調,改後需 --attribution 複驗

    def _get_whale_score(self, data: StockData) -> float:
        fr = data.foreign_net_ratio or {}
        tr = data.trust_net_ratio or {}

        # 無多天期資料 (live 尚未接線 / 無 chip) → 回退舊版計法,維持相容
        if not fr and not tr:
            return self._legacy_whale_score(data)

        # ---- 基底:多天期法人淨參與率加權 (signed) → 0-100,中性≈48 ----
        hw = self._HORIZON_WEIGHTS
        combined_ratio = sum(
            hw[n] * (float(fr.get(n, 0.0) or 0.0) + float(tr.get(n, 0.0) or 0.0))
            for n in hw
        )
        score = 48.0 + combined_ratio * self._RATIO_TO_POINTS

        # ---- 土洋同步 (5/10 日皆同買) → 確認加分 ----
        if (fr.get(5, 0) > 0 and tr.get(5, 0) > 0) or (fr.get(10, 0) > 0 and tr.get(10, 0) > 0):
            score += 8.0

        # ---- 連續買/賣超天數:降級為 bonus/penalty (各 cap 3 天,最多 ±12) ----
        score += min(data.foreign_buy_days, 3) * 2.0 + min(data.institutional_buy_days, 3) * 2.0
        score -= min(data.foreign_sell_days, 3) * 2.0 + min(data.institutional_sell_days, 3) * 2.0

        # ---- 確認層 (±15 有界):投信吸籌比 / 法人參與 / 力道放大 / 量能集中 ----
        #   注意:large_holder_activity / foreign_flow / trust_flow 已由上面的淨參與率涵蓋,
        #   不再重複計分 (避免因子共線放大同一訊號)。
        adj = 0.0
        if data.whale_concentration >= 1.0:
            adj += 8.0
        elif data.whale_concentration >= 0.3:
            adj += 4.0
        if data.institutional_participation >= 40.0:
            adj += 4.0
        elif data.institutional_participation >= 25.0:
            adj += 2.0
        if combined_ratio > 0 and data.flow_acceleration >= 1.5:
            adj += 5.0          # 淨買且力道放大 = 加速吸籌
        if data.volume_concentration >= 55.0:
            adj += 3.0
        elif 0.0 < data.volume_concentration < 45.0:
            adj -= 3.0
        adj = max(-15.0, min(15.0, adj))

        # ---- TDCC 確認層 (±8,預設關閉為 0) ----
        tdcc_adj = 0.0
        wchg = data.big_holder_weekly_change
        if wchg > 0:
            tdcc_adj += min(wchg * 4.0, 8.0)
        elif wchg < 0:
            tdcc_adj += max(wchg * 4.0, -8.0)
            if combined_ratio > 0:
                tdcc_adj -= 3.0          # 背離:法人在買、大戶卻週減 (趁強出貨)
        tdcc_adj = max(-8.0, min(8.0, tdcc_adj))

        return min(max(score + adj + tdcc_adj, 0.0), 100.0)

    # ------------------------------------------------------------------
    # 舊版籌碼計法 (連買天數為基底) — 僅在無多天期淨參與率資料時回退使用
    # ------------------------------------------------------------------
    def _legacy_whale_score(self, data: StockData) -> float:
        trust_days = data.institutional_buy_days
        foreign_days = data.foreign_buy_days
        trust_sell = data.institutional_sell_days
        foreign_sell = data.foreign_sell_days

        trust_score = min(trust_days * 20.0, 100.0)
        foreign_score = min(foreign_days * 20.0, 100.0)
        if trust_days > 0 and foreign_days > 0:
            combined = (trust_score * 0.5) + (foreign_score * 0.5) + 15.0
        else:
            combined = (trust_score * 0.5) + (foreign_score * 0.5)
        combined -= trust_sell * 8.0 + foreign_sell * 6.0

        adj = 0.0
        if data.large_holder_activity > 0:
            adj += 8.0
        elif data.large_holder_activity < 0:
            adj -= 8.0
        if data.foreign_flow > 0:
            adj += 4.0
        elif data.foreign_flow < 0:
            adj -= 4.0
        if data.trust_flow > 0:
            adj += 4.0
        elif data.trust_flow < 0:
            adj -= 4.0
        if data.large_holder_activity > 0 and data.flow_acceleration >= 1.5:
            adj += 5.0
        if data.whale_concentration >= 1.0:
            adj += 8.0
        elif data.whale_concentration >= 0.3:
            adj += 4.0
        if data.institutional_participation >= 40.0:
            adj += 4.0
        elif data.institutional_participation >= 25.0:
            adj += 2.0
        if data.volume_concentration >= 55.0:
            adj += 3.0
        elif 0.0 < data.volume_concentration < 45.0:
            adj -= 3.0
        adj = max(-25.0, min(25.0, adj))

        tdcc_adj = 0.0
        wchg = data.big_holder_weekly_change
        if wchg > 0:
            tdcc_adj += min(wchg * 4.0, 8.0)
        elif wchg < 0:
            tdcc_adj += max(wchg * 4.0, -8.0)
            if data.large_holder_activity > 0:
                tdcc_adj -= 3.0
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
