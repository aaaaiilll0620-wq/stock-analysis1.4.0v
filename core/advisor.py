import logging
from datetime import datetime
from typing import Dict, Any, Optional
from core.models import StockData, ScoreResult

logger = logging.getLogger(__name__)


class InvestmentAdvisor:
    """
    智慧決策建議系統 (Investment Advisor) —— 系統的「導航功能」。

    綜合三大支柱後輸出:
      - rating            評級標籤:強烈推薦 / 觀望追蹤 / 謹慎避開
      - valuation_status  估值高低判定 (由 ValuationEngine 帶入)
      - quality_flag      獲利/財務健康狀態 (由 FundamentalEngine 帶入)
      - actionable_advice 人類可讀的操作指令 (規則引擎依情境優先序挑選)

    三大支柱:
      1) 品質 (Quality)   ← FundamentalEngine.evaluate():is_passed / 現金流 / 獲利品質
      2) 估值 (Valuation) ← ValuationEngine.evaluate():valuation_score / status
      3) 動態 (Dynamic)   ← ScoringManager:total_score / momentum / RSI / 乖離 / 籌碼
    """

    RATING_SUPER = "強勢買進"     # 【新增·最高級】順勢動能主流飆股 (特赦估值/RSI/乖離)
    RATING_STRONG = "強烈推薦"     # 價值型:低估值 + 動能健康 + 不過熱
    RATING_WATCH = "觀望追蹤"
    RATING_AVOID = "謹慎避開"

    # 四級評級排序 (供回測統計/排序/多空價差使用;數字越大越積極看多)
    RATING_ORDER = ["謹慎避開", "觀望追蹤", "強烈推薦", "強勢買進"]
    RATING_RANK = {"謹慎避開": 0, "觀望追蹤": 1, "強烈推薦": 2, "強勢買進": 3}

    # 【漏洞三】產業分流:決定「財報 : 市場(技術+籌碼)」的比重
    #   A 大型權值/成長股 → 財報主導;B 景氣循環/籌碼波動股 → 市場(技術+籌碼)主導。
    SECTOR_FUND_WEIGHT = {"A": 0.50, "B": 0.20}
    # 模式預設市場內部傾斜 (技術/動能/籌碼);由 build_engines 傳入當前模式覆蓋。
    # 五大類綜合權重 (基本面/估值/技術/動能/籌碼);build_engines 依模式傳入覆蓋。
    DEFAULT_MODE_WEIGHTS = {"fundamental": 0.25, "valuation": 0.20,
                            "technical": 0.20, "momentum": 0.15, "whale": 0.20}
    MARGIN_DROP_WASHOUT = -8.0     # 融資10日變化 <= -8% 視為散戶明顯退場

    def __init__(self, min_score: float = 60.0, mode_weights: Dict[str, float] = None,
                 mode_name: str = "balanced"):
        # min_score 建議傳入 ScoringManager 當前模式的門檻,使評級與策略模式一致
        self.min_score = min_score
        self.mode_weights = mode_weights or dict(self.DEFAULT_MODE_WEIGHTS)
        self.mode_name = mode_name
        # 【市場 Regime】由回測/計分迴圈逐 as_of 設定 ('bull'/'neutral'/'bear');None → 不調整權重。
        self.current_regime = None
        # 依模式調整「嚴格度」:保守更早示警超買/追高、要求更強籌碼確認;積極更容許突破追高
        profile = {
            "conservative": dict(rsi_overbought=65.0, rsi_extreme=72.0, bias_chase=12.0, chip_min=45.0),
            "balanced":     dict(rsi_overbought=72.0, rsi_extreme=78.0, bias_chase=15.0, chip_min=30.0),
            "aggressive":   dict(rsi_overbought=75.0, rsi_extreme=82.0, bias_chase=18.0, chip_min=30.0),
        }.get(mode_name, dict(rsi_overbought=72.0, rsi_extreme=78.0, bias_chase=15.0, chip_min=30.0))
        self.rsi_overbought = profile["rsi_overbought"]
        self.rsi_extreme = profile["rsi_extreme"]
        self.rsi_oversold = 30.0
        self.bias_chase = profile["bias_chase"]     # 20 日正乖離超過此值視為追高
        self.chip_min = profile["chip_min"]         # 籌碼分低於此值不給強推
        self.spike_breakout = 2.0     # 量能爆發倍數突破門檻

        # 【新增】順勢動能「強勢買進」軌道門檻 (中性偏積極):
        #   動能分 / 籌碼分需同時「熱」,才特赦估值/RSI/乖離,把主流飆股納入最高級。
        lead = {
            "conservative": dict(mom_hot=52.0, whale_hot=48.0, rev_hot=15.0, tech_hot=70.0),
            "balanced":     dict(mom_hot=46.0, whale_hot=42.0, rev_hot=12.0, tech_hot=65.0),
            "aggressive":   dict(mom_hot=42.0, whale_hot=36.0, rev_hot=10.0, tech_hot=60.0),
        }.get(mode_name, dict(mom_hot=46.0, whale_hot=42.0, rev_hot=12.0, tech_hot=65.0))
        self.mom_hot = lead["mom_hot"]       # 價量動能分達此值視為「動能強」(單日快照,較噪)
        self.whale_hot = lead["whale_hot"]   # 籌碼分達此值視為「主力/法人點火」(強勢買進門檻)
        self.rev_hot = lead["rev_hot"]       # 營收年增/累計年增達此值視為「營收動能極強」(較穩)
        self.tech_hot = lead["tech_hot"]     # 技術分達此值視為「趨勢結構強」(多頭排列/MACD/週線,較穩)
        self.trend_bias_min = 7.0            # 動態權重/強勢多頭判定的最小正乖離
        self.lead_rsi_min = 53.0             # 動態權重觸發的最小 RSI (確認偏多)

    # ==================================================================
    # 主入口
    # ==================================================================
    def advise(self, stock: StockData, fund_result: Dict[str, Any],
               val_result: Dict[str, Any], score_result: ScoreResult) -> ScoreResult:
        """在既有 ScoreResult 上補齊評級與建議欄位並回傳 (in-place 補值)。"""
        # 【漏洞二】主力洗盤尾聲偵測 → 可能墊高籌碼分,避免假跌破被錯殺
        washout, washout_note = self._detect_washout(stock)

        # 綜合決策分數:五大類 (基本面/估值/技術/動能/籌碼) 明確加權,比重由 mode_weights 決定。
        category = getattr(stock, "sector_category", "B")
        chip_bucket = float(score_result.whale_score)
        if washout:
            chip_bucket = min(100.0, max(chip_bucket, 60.0) + 5.0)   # 洗盤尾聲不給極低分並加分
        # 估值資料不足 (score 0) 以中性 50 計,避免把「沒資料」當「最貴」
        val_status = val_result.get("valuation_status", "")
        val_score = float(val_result.get("valuation_score", 0.0))
        val_bucket = 50.0 if "資料不足" in val_status else val_score
        buckets = {
            "fundamental": float(fund_result.get("total_score", 50.0)),
            "valuation": val_bucket,
            "technical": float(score_result.technical_score),
            "momentum": float(score_result.momentum_score),
            "whale": chip_bucket,
        }
        mw = self.mode_weights
        # 【市場 Regime 層】空頭段自動降動能/技術、加重基本面 (乘數在 core.regime;current_regime
        #   由回測/計分迴圈逐 as_of 設定,None → 不調整)。在 per-stock 動態權重之前先套市場層級調整。
        if getattr(self, "current_regime", None):
            from core.regime import regime_multipliers
            _mult = regime_multipliers(self.current_regime)
            mw = {k: float(v) * float(_mult.get(k, 1.0)) for k, v in mw.items()}
        wsum = sum(max(0.0, float(mw.get(k, 0.0))) for k in buckets)
        if wsum <= 0:
            mw = self.DEFAULT_MODE_WEIGHTS
        # 【動態權重】強勢多頭排列時,自動降低估值佔比、改由動能與籌碼主導 (順勢加分)
        mw, dyn_on = self._dynamic_weights(stock, mw)
        wsum = sum(max(0.0, float(mw.get(k, 0.0))) for k in buckets)
        if wsum <= 0:
            mw = self.DEFAULT_MODE_WEIGHTS
            wsum = sum(mw.get(k, 0.0) for k in buckets)
        composite = sum(buckets[k] * float(mw.get(k, 0.0)) for k in buckets) / wsum
        score_result.total_score = float(round(composite, 2))
        score_result._dynamic_weight = dyn_on

        # 類別B:以 ATR 給防守區間 (2×ATR 停損參考),供建議語使用
        defensive_stop = 0.0
        if stock.atr > 0 and stock.current_price > 0:
            defensive_stop = round(stock.current_price - 2.0 * stock.atr, 2)
        score_result._category = category
        score_result._washout = (washout, washout_note)
        score_result._defensive_stop = defensive_stop

        rating = self._decide_rating(stock, fund_result, val_result, score_result)
        core = self._generate_advice(stock, fund_result, val_result, score_result, rating)
        advice_main = f"【{rating}】{core}"

        # 綜合資料信心:取基本面、估值、個股資料三者最保守值
        conf = min(
            fund_result.get("confidence", 100.0),
            val_result.get("confidence", 100.0),
            getattr(stock, "data_confidence", 100.0),
        )

        # 附註 (結構化):每則獨立,供報告分行顯示;actionable_advice 仍合併為單一字串供表格/匯出
        notes = []
        mom = self._timely_growth_note(stock)
        if mom:
            notes.append(self._strip_parens(mom))
        cross_note = self._revenue_profit_crosscheck(stock)
        if cross_note:
            notes.append(self._strip_parens(cross_note))
        buy_zone = self._buy_zone_note(stock)
        if buy_zone:
            notes.append(buy_zone)
        if conf < 65.0:
            notes.append(f"ℹ️資料完整度:僅 {conf:.0f}%,信心偏低,建議人工覆核")

        advice_combined = advice_main + "".join(f"({n})" for n in notes)

        score_result.rating = rating
        score_result.quality_flag = fund_result.get("quality_flag", "數據不足")
        if cross_note:
            score_result.quality_flag += "·⚠️增收不增利"
        score_result.valuation_status = val_result.get("valuation_status", "估值中性")
        score_result.valuation_score = val_result.get("valuation_score", 0.0)
        score_result.peg_ratio = val_result.get("peg_ratio")
        score_result.valuation_basis = val_result.get("valuation_basis", "絕對")
        score_result.valuation_label = val_result.get("valuation_label", "")
        score_result.actionable_advice = advice_combined
        score_result.advice_main = advice_main       # 主建議 (供報告分行)
        score_result.advice_notes = notes            # 附註清單 (供報告分行)
        score_result.fundamental_label = self._fundamental_label(stock, fund_result)
        score_result.trend_label = self._trend_label(stock)
        score_result.data_confidence = float(round(conf, 1))
        return score_result

    @staticmethod
    def _strip_parens(s: str) -> str:
        s = s.strip()
        if s.startswith("(") and s.endswith(")"):
            return s[1:-1]
        return s

    def _buy_zone_note(self, stock) -> str:
        """依籌碼成本區給出『買進區間』:用離現價最近的量能支撐/壓力並標示距離,
        太遠時老實提示『短期不易到達/追高風險』,不硬給不切實際的價位。"""
        poc = getattr(stock, "cost_zone_poc", None)
        status = getattr(stock, "cost_zone_status", "")
        cur = getattr(stock, "current_price", None)
        sup = getattr(stock, "cost_zone_support", None)
        res = getattr(stock, "cost_zone_resistance", None)
        val = getattr(stock, "value_area_low", None)
        vah = getattr(stock, "value_area_high", None)
        conf = getattr(stock, "cost_zone_confidence", None)
        hvn = getattr(stock, "cost_zone_hvn_levels", []) or []
        if not poc or not status or not cur:
            return ""

        def _lvl(level, kind):
            if not level:
                return None
            d = (level - cur) / cur * 100.0
            tag = f"{int(round(level))}({d:+.0f}%)"
            if abs(d) > 12:
                tag += ",距離較遠短期不易到達" if kind == "pull" else ",需大幅上漲"
            return tag

        conf_tag = f"（信心 {float(conf):.0f}%）" if conf is not None else ""
        node_tag = ""
        if hvn:
            near_nodes = [int(round(x)) for x in hvn[:3]]
            if near_nodes:
                node_tag = f" 關鍵量能節點:{'/'.join(str(x) for x in near_nodes)}。"

        if "下方" in status:
            r = _lvl(res, "up")
            body = (f"現價位於大戶成本區下方(相對便宜)。上方壓力約 {r}。" if r
                    else "現價位於大戶成本區下方(相對便宜)。") + "守穩不破前低即為分批布局區。"
        elif "上方" in status:
            s = _lvl(sup, "pull")
            # 細分:『主成本區上方(波段強勢/未過熱)』與『極端追高(已離成本區/破 VAH)』給不同語氣,
            #   避免把大戶成本仍遠在下方、僅波段偏強的個股一律說成『追高風險較高』(對 8210 型飆股失真)。
            if ("未過熱" in status) or ("波段強勢" in status):
                body = (f"現價站上主成本區、波段偏強但尚未過熱。最近支撐約 {s}。" if s
                        else "現價站上主成本區、波段偏強但尚未過熱。") + "順勢者可續抱,回測支撐不破仍屬健康,不宜在壓力前追價。"
            else:
                body = (f"現價已在成本區上方(追高)。最近支撐約 {s}。" if s
                        else "現價已在成本區上方(追高)。") + "追高風險較高,回檔守穩支撐再進較穩。"
        else:
            s, r = _lvl(sup, "pull"), _lvl(res, "up")
            parts = [x for x in (f"支撐約 {s}" if s else None, f"壓力約 {r}" if r else None) if x]
            in_band_desc = "現價落在成本帶內"
            near_support = False
            near_resistance = False
            dist_support = None
            dist_resistance = None
            if sup is not None and float(cur) > 0:
                dist_support = abs((float(cur) - float(sup)) / float(cur))
                near_support = dist_support <= 0.035
            if res is not None and float(cur) > 0:
                dist_resistance = abs((float(res) - float(cur)) / float(cur))
                near_resistance = dist_resistance <= 0.035

            # 兩端都不算很近時,再用「相對接近哪一端」補判斷,避免支撐顯示 -0% 卻被歸在中段。
            if dist_support is not None and dist_resistance is not None:
                if dist_support <= min(0.05, dist_resistance * 0.6):
                    near_support = True
                    near_resistance = False
                elif dist_resistance <= min(0.05, dist_support * 0.6):
                    near_resistance = True
                    near_support = False

            # 優先依「離最近支撐/壓力距離」判斷位置,比用整段 VAL~VAH 百分位更貼近交易語意。
            if near_support and not near_resistance:
                in_band_desc = "現價位於成本帶下緣(偏防守區)"
            elif near_resistance and not near_support:
                in_band_desc = "現價位於成本帶上緣(接近壓力區)"
            elif val is not None and vah is not None and float(vah) > float(val):
                band_w = float(vah) - float(val)
                pos = (float(cur) - float(val)) / band_w
                if pos <= 0.25:
                    in_band_desc = "現價位於成本帶下緣(偏防守區)"
                elif pos >= 0.75:
                    in_band_desc = "現價位於成本帶上緣(接近壓力區)"
                else:
                    in_band_desc = "現價落在成本帶中段(套牢賣壓區)"
            if parts:
                body = f"{in_band_desc}。{'、'.join(parts)}。帶量突破壓力或回測支撐再進。"
            else:
                tail = ",待帶量突破再進。" if "賣壓區" in in_band_desc else "。"
                body = f"{in_band_desc}{tail}"
        # POC 大漲修正:現價遠高於全域 POC (>1.3×) 時,該 POC 多是早期低價累積帶,
        #   不是『現在的成本區』(否則會出現「成本區202 vs 支撐554」的矛盾)。改標為早期累積區、
        #   僅供歷史參考,可操作成本區以 body 內『現價下方最近高量支撐』為準。
        poc_i = int(round(poc))
        if cur and poc and float(cur) > float(poc) * 1.3:
            return (f"💰買進區間:早期累積區約 {poc_i}(現價已遠高於此,僅供歷史參考、非當前成本區)"
                    f";可操作成本區以現價下方最近高量支撐為準——{body}{node_tag}")
        return f"💰買進區間:大戶成本區約 {poc_i}{conf_tag};{body}{node_tag}"

    def _timely_growth_note(self, stock) -> str:
        """
        以「月營收即時動能」補足季報時間差:當月營收動能明顯轉強時,
        用實際數字 (累計年增/連續成長月數/加速) 給出即時判讀,並在季報落後時提示以月營收為準。
        動能不明顯則回傳空字串。
        """
        rc = getattr(stock, "rev_cagr", None)                 # 近3月均月營收 YoY
        accel = getattr(stock, "revenue_accel", None)
        streak = getattr(stock, "revenue_growth_streak", 0) or 0
        cum = getattr(stock, "revenue_cum_yoy", None)
        strong = ((rc is not None and rc >= 15.0) or
                  (accel is not None and accel > 0 and streak >= 3) or
                  (cum is not None and cum >= 15.0))
        if not strong:
            return ""
        parts = []
        if cum is not None:
            parts.append(f"累計營收年增 {cum:+.1f}%")
        elif rc is not None:
            parts.append(f"近3月營收年增 {rc:+.1f}%")
        if streak >= 2:
            parts.append(f"連續 {streak} 月成長")
        if accel is not None and accel > 0:
            parts.append("動能加速")
        read = "、".join(parts) if parts else "月營收動能轉強"

        # 季報時間差
        tail = ""
        fin_asof = getattr(stock, "financials_asof", None)
        if fin_asof:
            try:
                d = datetime.strptime(str(fin_asof)[:10].replace("/", "-"), "%Y-%m-%d")
                months_lag = (datetime.now() - d).days / 30.0
                if months_lag >= 2.5:
                    tail = (f";季報僅至 {str(fin_asof)[:10]}(約 {months_lag:.0f} 個月前),"
                            f"獲利年增尚未反映近期成長,請以月營收為即時依據")
            except Exception:
                pass
        return f"(📈即時動能:{read}{tail})"

    def _revenue_profit_crosscheck(self, stock) -> str:
        """
        增收是否增利:月營收動能強、但季報毛利率在下滑 → 示警「純衝營收 (增收不增利)」。
        毛利率同步走穩/走升則不示警 (視為健康成長)。回傳警語或空字串。
        """
        rc = getattr(stock, "rev_cagr", None)
        cum = getattr(stock, "revenue_cum_yoy", None)
        streak = getattr(stock, "revenue_growth_streak", 0) or 0
        accel = getattr(stock, "revenue_accel", None)
        strong_rev = ((rc is not None and rc >= 15.0) or
                      (cum is not None and cum >= 15.0) or
                      (accel is not None and accel > 0 and streak >= 3))
        gmt = getattr(stock, "gross_margin_trend", None)
        if not strong_rev or gmt is None:
            return ""
        if gmt <= -1.5:
            return (f"(⚠️增收不增利:營收動能強,但毛利率較前季走弱 {gmt:.1f} 個百分點,"
                    f"獲利未必同步放大,慎防以價換量或成本侵蝕)")
        return ""

    # ==================================================================
    # 評級判定
    # ==================================================================
    def _detect_washout(self, stock) -> tuple:
        """
        【漏洞二】主力洗盤尾聲偵測:
          條件 = 股價回檔 + 法人短線賣超 + 融資大減(散戶退場) [+ 大戶回補(若有 TDCC)]。
          命中時視為「假跌破、真洗盤」,籌碼面不應給極低分。
        回傳 (bool, note)。
        """
        price_weak = (stock.change_percent < 0) or (stock.ma20_bias < 0)
        inst_short = (stock.foreign_sell_days > 0 or stock.institutional_sell_days > 0
                      or stock.large_holder_activity < 0)
        retail_exit = stock.margin_change_pct <= self.MARGIN_DROP_WASHOUT
        # 若有 TDCC 大戶資料,額外要求「大戶未同步減碼」以提高可信度
        big_holder_ok = True
        if stock.big_holder_ratio > 0:
            big_holder_ok = stock.big_holder_weekly_change >= 0
        if price_weak and inst_short and retail_exit and big_holder_ok:
            extra = ""
            if stock.big_holder_ratio > 0:
                extra = f"、千張大戶週變化 {stock.big_holder_weekly_change:+.2f}pp"
            note = (f"主力洗盤尾聲:股價回檔、法人短線賣超,但融資10日大減 "
                    f"{stock.margin_change_pct:.1f}%(散戶退場){extra}")
            return True, note
        return False, ""

    # ------------------------------------------------------------------
    # 順勢 / 籌碼 / 動態權重 輔助判斷 (重構核心)
    # ------------------------------------------------------------------
    @staticmethod
    def _bull_stack(stock) -> bool:
        """短均線多頭排列:現價站上月線且 5 日線在 20 日線之上 (順勢基本盤)。"""
        p, m5, m20 = stock.current_price, stock.ma5, stock.ma20
        if p <= 0 or m5 <= 0 or m20 <= 0:
            return False
        return (p > m20) and (m5 >= m20)

    def _uptrend(self, stock) -> bool:
        """穩健多頭趨勢 (較單日動能穩定):站上月線 + 站穩週線 + 中期未死叉。
        刻意不綁 ma5>=ma20 —— 5 日線在健康回檔時會短暫下彎,綁死它會把回測到月線的
        主流強勢股錯殺;改以『站上月線(較穩)』為核心,用趨勢結構而非短均線雜訊認定順勢。"""
        p, m20 = stock.current_price, stock.ma20
        if p <= 0 or m20 <= 0:
            return False
        above_ma20 = p > m20
        weekly_ok = (stock.weekly_ma20 <= 0) or (p >= stock.weekly_ma20 * 0.98)
        mid_ok = stock.ma_cross_status != "death_cross"
        return above_ma20 and weekly_ok and mid_ok

    def _revenue_hot(self, stock) -> bool:
        """營收動能極強 (較穩定、不隨單日快照跳動):年增/累計年增達標,或連續成長月數足。"""
        return ((stock.rev_cagr or 0) >= self.rev_hot
                or (stock.revenue_cum_yoy or 0) >= self.rev_hot
                or (stock.revenue_growth_streak or 0) >= 3)

    def _momentum_hot(self, stock, score_result) -> bool:
        """動能達標 (三選一,避免被單日快照雜訊卡死):
          價量動能分 (單日,較噪) / 技術趨勢結構分 (多頭排列·MACD·週線,較穩) / 營收動能 (較穩)。"""
        return (float(score_result.momentum_score) >= self.mom_hot
                or float(score_result.technical_score) >= self.tech_hot
                or self._revenue_hot(stock))

    @staticmethod
    def _chip_inflow(stock) -> bool:
        """實質籌碼流入:法人連買 / 近期淨流入 / 大戶回補 任一為真。"""
        return (stock.institutional_buy_days > 0 or stock.foreign_buy_days > 0
                or stock.large_holder_activity > 0 or stock.foreign_flow > 0
                or stock.trust_flow > 0 or stock.big_holder_weekly_change > 0)

    def _chips_ok(self, stock, score_result) -> bool:
        """順勢買進的籌碼確認 (中等門檻):有實質流入且籌碼分不弱 (>= chip_min)。"""
        return self._chip_inflow(stock) and float(score_result.whale_score) >= self.chip_min

    def _chips_igniting(self, stock, score_result) -> bool:
        """主力/法人『點火』(強勢買進門檻):須有實質流入,且滿足下列任一強度訊號 ——
          籌碼分達熱區 (>= whale_hot) / 土洋同步連買 / 法人高度主導盤面。
          用『土洋同買·法人主導』作為替代點火訊號,避免因 whale_score 計分天生偏低而漏掉真主流股。"""
        if not self._chip_inflow(stock):
            return False
        whale = float(score_result.whale_score)
        dual_buy = stock.institutional_buy_days > 0 and stock.foreign_buy_days > 0
        heavy = stock.institutional_participation >= 40.0
        return whale >= self.whale_hot or dual_buy or heavy

    @staticmethod
    def _blowoff_risk(stock) -> bool:
        """衰竭/出貨保護:價漲量縮背離 且 主力同步調節/賣超 → 追高危險,不給最高級。"""
        distributing = (stock.large_holder_activity < 0 or stock.big_holder_weekly_change < 0
                        or stock.institutional_sell_days > 0 or stock.foreign_sell_days > 0)
        return bool(stock.volume_divergence and distributing)

    def _super_buy_qualifies(self, stock, fund_result, val_result, score_result) -> bool:
        """
        【強勢買進】判定軌道 —— 專門捕捉「順勢動能主流股」:
          條件 = 穩健多頭趨勢 + (價量或營收) 動能強 + 主力/法人瘋狂點火
                 + 基本面未壞 + 非昂貴泡泡 + 未見衰竭出貨。
          命中時『特赦』估值過高 / RSI 過熱 / 乖離過大的限制 —— 不再要求它「已經極端」,
          只要它是有籌碼、有動能的主流強勢股就納入最高級 (這是修正恐高症的關鍵)。
        """
        if not self._fund_not_broken(fund_result):
            return False
        if val_result.get("valuation_label", "") == "昂貴泡泡":       # 成長跟不上股價 → 不特赦
            return False
        if not self._uptrend(stock):                                  # 穩健多頭趨勢
            return False
        if not self._momentum_hot(stock, score_result):              # 動能 (價量 or 營收) 強
            return False
        if not self._chips_igniting(stock, score_result):            # 主力/法人瘋狂點火
            return False
        if self._blowoff_risk(stock):                                # 衰竭/出貨保護
            return False
        return True

    @staticmethod
    def _fund_not_broken(fund_result) -> bool:
        """基本面底線:硬門檻過、現金流非高風險、無獲利動態風險。"""
        if not fund_result.get("is_passed", False):
            return False
        if fund_result.get("cash_flow_health", {}).get("risk_level") == "high_risk":
            return False
        if fund_result.get("profit_quality", {}).get("risk", False):
            return False
        return True

    def _rebound_rescue(self, stock, score_result) -> bool:
        """
        逆勢偏誤救援:被判『謹慎避開』但『趨勢翻多/突破壓力 + 籌碼實質流入』→
        強制改列『觀望追蹤』,把像南亞科那類落底反彈的股票移出避開桶,
        避免避開桶反而藏著贏家 (反向指標),並保留後續參與的機會。
        """
        above_ma20 = stock.ma20 > 0 and stock.current_price > stock.ma20
        turning_up = above_ma20 and stock.ma5 >= stock.ma20          # 短均線翻多 (趨勢轉折)
        vol_break = (stock.volume_spike or 1.0) >= self.spike_breakout and stock.change_percent > 2.0
        res = getattr(stock, "cost_zone_resistance", None)
        zone_break = bool(res) and stock.current_price >= float(res)
        breakout = turning_up or vol_break or zone_break
        whale_in = self._chip_inflow(stock) and float(score_result.whale_score) >= self.chip_min * 0.6
        return bool(breakout and whale_in)

    def _dynamic_weights(self, stock, base: Dict[str, float]):
        """
        動態權重:當個股處於『強勢多頭排列』(多頭排列 + 正乖離達標 + RSI 偏多) 時,
        自動把估值 (valuation) 權重砍 60%,轉移給動能 (momentum) 與籌碼 (whale),
        讓分數由順勢動能主導,不再被『便宜與否』拖累主流飆股。回傳 (新權重, 是否啟用)。
        """
        w = {k: float(v) for k, v in base.items()}
        strong_trend = (self._bull_stack(stock)
                        and stock.ma20_bias >= self.trend_bias_min
                        and stock.rsi >= self.lead_rsi_min)
        if not strong_trend:
            return w, False
        v = w.get("valuation", 0.0)
        cut = v * 0.6
        w["valuation"] = v - cut
        w["momentum"] = w.get("momentum", 0.0) + cut * 0.6
        w["whale"] = w.get("whale", 0.0) + cut * 0.4
        return w, True

    def _decide_rating(self, stock, fund_result, val_result, score_result) -> str:
        # 【bear 段評級閘門】total_score 的排序權重已隨 regime 調整 (見 advise() 的
        #   regime_multipliers),但評級門檻 (min_score/chip_min/whale_hot) 原本固定,
        #   空頭段照樣常給強推/強買。這裡依 core.regime.regime_rating_gates 暫時墊高
        #   門檻 (chip_min/whale_hot 因籌碼在空頭是反指標而加嚴更多),讓評級也自動
        #   更接近空手;呼叫結束後還原,避免污染下一支股票或下一次呼叫的門檻。
        from core.regime import regime_rating_gates
        gate = regime_rating_gates(getattr(self, "current_regime", None))
        _orig_gates = (self.min_score, self.chip_min, self.whale_hot)
        self.min_score = _orig_gates[0] + gate["min_score_add"]
        self.chip_min = _orig_gates[1] * gate["chip_min_mult"]
        self.whale_hot = _orig_gates[2] * gate["whale_hot_mult"]
        try:
            return self._decide_rating_inner(stock, fund_result, val_result, score_result)
        finally:
            self.min_score, self.chip_min, self.whale_hot = _orig_gates

    def _decide_rating_inner(self, stock, fund_result, val_result, score_result) -> str:
        is_passed = fund_result.get("is_passed", False)
        cash_risk = fund_result.get("cash_flow_health", {}).get("risk_level", "unknown")
        profit_risk = fund_result.get("profit_quality", {}).get("risk", False)
        val_status = val_result.get("valuation_status", "")
        total = score_result.total_score
        rsi = stock.rsi
        bias = stock.ma20_bias

        # --- (A) 硬性致命避開 (基本面/現金流/破線潰散):這些連強勢買進都救不了 ---
        hard_avoid = (
            (not is_passed)
            or (cash_risk == "high_risk")
            or (rsi and rsi < self.rsi_oversold and score_result.momentum_score < 20)  # 破線 + 動能潰散
        )
        if hard_avoid:
            if self._rebound_rescue(stock, score_result):
                return self.RATING_WATCH
            return self.RATING_AVOID

        # --- (B) 【強勢買進】順勢動能主流股:特赦估值/RSI/乖離,列最高級 ---
        #   須在『估值型軟避開』之前判定 —— 主流飆股綜合分常被估值拖低,不能因此被錯殺。
        if self._super_buy_qualifies(stock, fund_result, val_result, score_result):
            return self.RATING_SUPER

        # --- (C) 估值型軟避開:又貴、綜合分又低,且非主流強勢 → 避開 (可被反彈救援救回觀望) ---
        if ("偏高" in val_status) and total < 50:
            if self._rebound_rescue(stock, score_result):
                return self.RATING_WATCH
            return self.RATING_AVOID

        # --- (D) 主力洗盤尾聲:待止穩分批 → 觀望追蹤 ---
        washout, _ = getattr(score_result, "_washout", (False, ""))
        if washout:
            return self.RATING_WATCH

        # --- (E) 【強烈推薦】兩條路 (擇一即可),把強勢主流股救出觀望桶 ---
        quality_ok = (cash_risk in ("healthy", "watch")) and not profit_risk
        valuation_ok = ("偏低" in val_status) or ("合理" in val_status)
        not_bubble = val_result.get("valuation_label", "") != "昂貴泡泡"
        chip_ok = score_result.whale_score >= self.chip_min

        #   (E1) 價值型:估值偏低/合理 + 分數達門檻 + 不過熱 + 籌碼不弱 (原邏輯)
        value_strong = (quality_ok and valuation_ok and chip_ok
                        and total >= self.min_score
                        and rsi < self.rsi_extreme and bias <= self.bias_chase)
        #   (E2) 順勢型:穩健多頭 + 籌碼實質流入 + 非泡沫/衰竭 (捕捉『強但未極端』的主流股)
        trend_strong = (quality_ok and not_bubble and self._uptrend(stock)
                        and self._chips_ok(stock, score_result)
                        and not self._blowoff_risk(stock)
                        and total >= (self.min_score - 5))
        if value_strong or trend_strong:
            # 記錄是走哪一條路進強推,供建議語 (順勢型不該叫人「等回檔」)
            score_result._strong_kind = "value" if value_strong else "trend"
            return self.RATING_STRONG

        # --- (F) 其餘:觀望追蹤 ---
        return self.RATING_WATCH

    # ==================================================================
    # 可執行建議 (規則引擎,依優先序挑最貼切的一句)
    # ==================================================================
    def _generate_advice(self, stock, fund_result, val_result, score_result, rating) -> str:
        cash_health = fund_result.get("cash_flow_health", {})
        cash_risk = cash_health.get("risk_level", "unknown")
        profit_q = fund_result.get("profit_quality", {})
        val_status = val_result.get("valuation_status", "")
        rsi = stock.rsi
        bias = stock.ma20_bias
        spike = stock.volume_spike or 1.0
        c = stock.change_percent
        above_ma20 = stock.ma20 > 0 and stock.current_price > stock.ma20

        # 1) 硬門檻未過 → 直接避開
        if not fund_result.get("is_passed", False):
            reasons = fund_result.get("reasons", [])
            rtxt = f" ({reasons[0]})" if reasons else ""
            return f"未通過基本面安全門檻{rtxt},不建議介入,建議謹慎避開。"

        # 2) 現金流高風險 → 財務紅燈
        if cash_risk == "high_risk":
            note = cash_health.get("notes", ["營業現金流異常"])[0]
            return f"財務體質亮紅燈:{note},即使技術面轉強亦建議謹慎避開。"

        # 3) 獲利動態風險 → 獲利品質存疑
        if profit_q.get("risk"):
            return f"{profit_q.get('note','獲利品質存疑')};建議降低持股信心,先觀望追蹤本業能否跟上。"

        # 3b) 【漏洞二】主力洗盤尾聲:假跌破真洗盤,不追殺、留意打底
        washout, washout_note = getattr(score_result, "_washout", (False, ""))
        if washout:
            return (f"{washout_note};研判為主力洗盤尾聲而非潰敗,籌碼面不宜過度看空,"
                    f"可將其列入打底候選、待量價止穩分批介入。")

        # 3c-0) 【強勢買進】順勢動能主流股:專屬語氣,優先於其他訊號
        if rating == self.RATING_SUPER:
            chip_bits = []
            if stock.institutional_buy_days > 0:
                chip_bits.append(f"投信連買{stock.institutional_buy_days}天")
            if stock.foreign_buy_days > 0:
                chip_bits.append(f"外資連買{stock.foreign_buy_days}天")
            chip = "、".join(chip_bits) if chip_bits else "主力資金持續點火"
            stop = getattr(score_result, "_defensive_stop", 0.0)
            tail = f"動態防守參考約 {stop} 元;" if stop > 0 else ""
            return (f"順勢動能主流股:均線多頭排列、動能強勁({chip}),"
                    f"雖估值/位階偏高,但成長與籌碼撐得住,屬強勢買進標的。"
                    f"{tail}建議順勢續抱,以動態籌碼支撐停損/移動停利控管風險,不預設賣點、讓利潤奔跑。")

        # 3c-1) 【強烈推薦·順勢型】強但未極端的主流股:不叫人「等回檔」,給順勢分批語氣
        if rating == self.RATING_STRONG and getattr(score_result, "_strong_kind", "") == "trend":
            chip_bits = []
            if stock.institutional_buy_days > 0:
                chip_bits.append(f"投信連買{stock.institutional_buy_days}天")
            if stock.foreign_buy_days > 0:
                chip_bits.append(f"外資連買{stock.foreign_buy_days}天")
            chip = "、".join(chip_bits) if chip_bits else "法人/主力資金淨流入"
            stop = getattr(score_result, "_defensive_stop", 0.0)
            tail = f"回測支撐 (約 {stop} 元) 不破前續抱;" if stop > 0 else ""
            return (f"均線多頭排列、籌碼實質流入({chip}),屬順勢強勢的主流標的。"
                    f"雖非最便宜,但趨勢與籌碼站在同一邊,可順勢偏多操作、拉回不破均線分批布局。"
                    f"{tail}以動態支撐停損/移動停利控管風險。")

        # 3c) 【漏洞一】本業獲利爆發 (營運槓桿):強勢而非風險
        if profit_q.get("operating_leverage") and rating in (self.RATING_SUPER, self.RATING_STRONG, self.RATING_WATCH):
            return (f"{profit_q.get('note','本業獲利爆發')};屬營運槓桿帶動的強勢獲利,"
                    f"可視技術面回檔分批布局。")

        # 4) 突破訊號:放量 + 上漲 + 站上均線
        if spike > self.spike_breakout and c > 3 and above_ma20 and bias <= self.bias_chase:
            return (f"成交量異常放大 ({spike:.1f} 倍均量) 伴隨帶量突破且站穩月線,"
                    f"動能強勁,可考慮順勢分批切入。")

        # 5) 好公司但超買 / 追高
        if rating in (self.RATING_STRONG, self.RATING_WATCH):
            if rsi >= self.rsi_overbought or bias > self.bias_chase:
                return (f"基本面體質良好,但目前處於超買區 (RSI {rsi:.0f}、"
                        f"20日乖離 {bias:+.1f}%),追高風險高,建議等待回檔再分批布局。")

        # 6) 估值偏貴但體質佳
        if "偏高" in val_status:
            return "公司體質不俗,但股價已反映利多、估值偏貴,建議列入追蹤、等回檔至合理區間再議。"

        # 7) 強烈推薦的常態:估值合理 + 動能健康
        if rating == self.RATING_STRONG:
            chip = ""
            if stock.institutional_buy_days > 0 and stock.foreign_buy_days > 0:
                chip = f"且土洋法人同步進場 (投信連買{stock.institutional_buy_days}天/外資連買{stock.foreign_buy_days}天),"
            base = (f"獲利穩健、{val_status}{chip}技術動能健康,"
                    f"屬價格合理的優質標的,建議分批布局。")
            # 類別B(景氣循環/籌碼波動股):附 ATR 防守區間
            cat = getattr(score_result, "_category", "B")
            stop = getattr(score_result, "_defensive_stop", 0.0)
            if cat == "B" and stop > 0:
                base += f"因屬波動較大類股,防守參考 2×ATR 停損約 {stop} 元。"
            return base

        # 8) 籌碼調節警示
        if stock.institutional_sell_days > 0 or stock.foreign_sell_days > 0:
            return (f"法人正在調節 (投信連賣{stock.institutional_sell_days}天/"
                    f"外資連賣{stock.foreign_sell_days}天),量價未明,建議觀望追蹤等籌碼止穩。")

        # 9) 預設:訊號分歧
        return "基本面、估值與動能訊號分歧,方向未明,建議觀望追蹤,等待更明確的量價或籌碼訊號。"

    # ==================================================================
    # 濃縮評語:基本面評價 (供表格「基本面評價」欄使用)
    # ==================================================================
    def _fundamental_label(self, stock, fund_result) -> str:
        """把基本面體質壓縮成一句短評 + 最關鍵佐證,例如「優異 (ROE 22%)」。"""
        if not fund_result.get("is_passed", True):
            return "體質不佳 (未過門檻)"

        cash_risk = fund_result.get("cash_flow_health", {}).get("risk_level", "unknown")
        if cash_risk == "high_risk":
            return "現金流警訊"
        if fund_result.get("profit_quality", {}).get("risk"):
            return "獲利存疑 (動態風險)"

        roe = stock.roe
        gm = stock.gross_margin
        has_roe = roe is not None
        has_gm = gm is not None
        if not has_roe and not has_gm:
            return "資料不足"

        # 依最亮眼的指標給評級 (由高到低)
        if has_roe and roe >= 20:
            return f"優異 (ROE {roe:.0f}%)"
        if has_gm and gm >= 45:
            return f"優異 (毛利 {gm:.0f}%)"
        if (has_roe and roe >= 15) or (has_gm and gm >= 40):
            tag = f"ROE {roe:.0f}%" if (has_roe and roe >= 15) else f"毛利 {gm:.0f}%"
            return f"極佳 ({tag})"
        if (has_roe and roe >= 10) or (has_gm and gm >= 25):
            return "優良"
        return "普通"

    # ==================================================================
    # 濃縮評語:動態趨勢 (供表格「動態趨勢」欄使用)
    # ==================================================================
    def _trend_label(self, stock) -> str:
        """把量價/RSI/乖離壓縮成一句趨勢短評,例如「強勁 (量能 3.2倍)」。"""
        rsi = stock.rsi
        bias = stock.ma20_bias
        spike = stock.volume_spike or 1.0
        c = stock.change_percent

        # 主流強勢:多頭排列 + 明顯正乖離 + 偏多 RSI → 順勢動能 (優先於「過熱」判定)
        if (self._bull_stack(stock) and bias is not None and bias > self.bias_chase
                and rsi is not None and rsi >= self.rsi_overbought):
            return "主流強勢 (順勢動能)"
        # 過熱:超買或正乖離過大
        if (rsi is not None and rsi >= self.rsi_extreme) or (bias is not None and bias >= self.bias_chase):
            return "過熱 (超買/過度擴張)"
        # 強勁:帶量且非下跌
        if spike >= self.spike_breakout and (c is None or c >= 0):
            return f"強勁 (量能 {spike:.1f}倍)"
        # 弱勢:RSI 偏低
        if rsi is not None and rsi < 40:
            return "弱勢 (RSI 偏低)"
        # 健康多頭:RSI 溫和且乖離為正
        if rsi is not None and 45 <= rsi <= 70 and (bias is None or bias >= 0):
            return "健康 (多頭)"
        # 其餘:區間整理
        return "整理 (區間)"
