import math
import pandas as pd
import numpy as np
from typing import Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class TechnicalEngine:
    def __init__(self):
        pass
    """專門處理純技術指標的計算引擎"""
    @staticmethod 
    def _sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """[輔助函數] 清洗數據:確保 date 為 datetime index,且 close/price/volume 欄位無誤"""
        if df.empty or not isinstance(df, pd.DataFrame) or 'date' not in df.columns:
            return df

        try:
            idx = pd.to_datetime(df['date'], errors='coerce')
            if idx.isna().any():
                logger.warning("Some dates could not be parsed correctly. Proceeding with valid rows.")
            df_indexed = df.set_index(idx).copy()
            df_indexed.index.name = 'date'
            df_indexed = df_indexed[~df_indexed.index.isna()]
        except Exception:
            return df

        if 'close' in df_indexed.columns:
            try:
                close_col = pd.to_numeric(df_indexed['close'], errors='coerce')
                clean_close = close_col.ffill().bfill()
                df_indexed['close'] = clean_close
            except Exception:
                pass

        return df_indexed

    def calculate_weekly_ma20(self, df: pd.DataFrame) -> float:
        df = df.copy()

        if 'close' not in df.columns:
            logger.error("calculate_weekly_ma20: 'close' column missing.")
            return 0.0
        df['close'] = pd.to_numeric(df['close'], errors='coerce')

        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date']).set_index('date')

        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                logger.error("calculate_weekly_ma20: Index is not DatetimeIndex and cannot be converted.")
                return 0.0

        weekly_df = df['close'].resample('W').last().ffill()

        actual_count = len(weekly_df)
        if actual_count == 0:
            return 0.0

        window_size = 20 if actual_count >= 20 else actual_count
        ma20_series = weekly_df.rolling(window=window_size, min_periods=1).mean()

        if ma20_series.dropna().empty:
            return 0.0

        return float(ma20_series.iloc[-1])

    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> dict:
        """
        動態參數的 MACD 計算。
        【修正】原版把進階狀態 (bullish_strong / bullish_recovery / 黃金交叉) 算出來卻
        沒有放進回傳值,只回傳一個簡單的 macd>signal 比較。現在改為完整回傳,
        讓 scoring_manager 能據此做技術面細分。
        """
        clean_df = df.copy()
        if len(clean_df) < max(fast, slow):
            return {"error": "Insufficient data"}
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()

        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()

        curr_macd = df['macd'].iloc[-1]
        prev_macd = df['macd'].iloc[-2]
        curr_signal = df['signal'].iloc[-1]
        prev_signal = df['signal'].iloc[-2]

        is_golden_cross = (prev_macd <= prev_signal) and (curr_macd > curr_signal)
        is_death_cross = (prev_macd >= prev_signal) and (curr_macd < curr_signal)

        status = "neutral"
        mid_band = df['close'].rolling(window=20).mean().iloc[-1]

        if is_golden_cross and curr_macd > 0:
            status = "bullish_strong"        # 零軸上方金叉
        elif is_golden_cross and curr_macd < 0 and curr_macd > (mid_band * -0.2):
            status = "bullish_recovery"      # 低位金叉,反彈機會
        elif is_death_cross:
            status = "bearish"
        elif curr_macd > curr_signal:
            status = "neutral"               # 多頭續勢但無新交叉
        else:
            status = "bearish"

        return {
            "val": float(curr_macd),
            "sig": float(curr_signal),
            "status": status,                                     # 進階狀態(供評分使用)
            "cross": "golden" if is_golden_cross else ("death" if is_death_cross else "none"),
            "above_zero": bool(curr_macd > 0),
            "simple": "bullish" if curr_macd > curr_signal else "bearish",
            "params": f"{fast},{slow},{signal}"
        }
    @staticmethod
    def calculate_bb(df: pd.DataFrame, window=20, std=2) -> Dict[str, Any]:
        """計算布林帶 (Bollinger Bands)"""
        df['ma'] = df['close'].rolling(window=window).mean()
        df['std'] = df['close'].rolling(window=window).std()
        df['upper'] = df['ma'] + (df['std'] * std)
        df['lower'] = df['ma'] - (df['std'] * std)
        df['bb_width'] = (df['upper'] - df['lower']) / df['ma']

        current_bw = df['bb_width'].iloc[-1]
        avg_bw = df['bb_width'].rolling(window=20).mean().iloc[-1]
        status = "squeezing" if current_bw < (avg_bw * 0.8) else "expanding"

        upper_band = df['upper'].iloc[-1]
        lower_band = df['lower'].iloc[-1]
        mid_band = df['ma'].iloc[-1]
        squeeze_ratio = (upper_band - lower_band) / mid_band if mid_band != 0 else 1.0
        return {
            "upper": upper_band,
            "lower": lower_band,
            "bandwidth": current_bw,
            "squeeze_ratio": squeeze_ratio,
            "status": status
        }
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, window=14) -> dict:
        """計算相對強弱指數 (RSI)"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        curr_rsi = df['rsi'].iloc[-1]
        return {
            "val": curr_rsi,
            "status": "overbought" if curr_rsi > 70 else ("oversold" if curr_rsi < 30 else "neutral")
        }
    
    @staticmethod
    def calculate_ma(df: pd.DataFrame, window: int) -> pd.Series:
        """計算移動平均線,確保即使數據不足也能回傳正確的 Series (不為 None)"""
        if 'close' in df.columns:
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            return df['close'].rolling(window=window, min_periods=1).mean()
        else:
            import numpy as np
            return pd.Series([np.nan] * len(df))
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, window=20, std=2):
        bb = self.calculate_bb(df, window, std)
        return pd.Series(bb['upper'], index=df.index), pd.Series(bb['lower'], index=df.index)
    
    @staticmethod
    def calculate_kd(df: pd.DataFrame, n=9) -> dict:
        """計算 KDJ 指標 """
        low_min = df['low'].rolling(window=n).min()
        high_max = df['high'].rolling(window=n).max()
        range_val = high_max - low_min
        df['RSV'] = (df['close'] - low_min) / (high_max - low_min) * 100 if range_val.iloc[-1] != 0 else 0
        df['K'] = df['RSV'].rolling(window=n).mean()
        df['D'] = df['K'].rolling(window=n).mean()
        df['J'] = 3 * df['K'] - 2 * df['D']

        curr_k = df['K'].iloc[-1]
        curr_d = df['D'].iloc[-1]
        curr_j = df['J'].iloc[-1]

        return {
            "K": curr_k,
            "D": curr_d,
            "J": curr_j,
            "status": "strong_momentum" if curr_j > 100 else ("weak_momentum" if curr_j < 0 else "neutral")
        }

    @staticmethod
    def calculate_atr(df: pd.DataFrame, window: int = 14) -> float:
        """
        平均真實區間 ATR(14):波動度指標,供類別B防守區間與產業分類。
        相容 FinMind 欄位命名 (high/low 或 max/min);資料不足回傳 0.0。
        """
        if df is None or df.empty or 'close' not in df.columns:
            return 0.0
        high_col = 'high' if 'high' in df.columns else ('max' if 'max' in df.columns else None)
        low_col = 'low' if 'low' in df.columns else ('min' if 'min' in df.columns else None)
        if high_col is None or low_col is None:
            return 0.0
        h = pd.to_numeric(df[high_col], errors='coerce')
        l = pd.to_numeric(df[low_col], errors='coerce')
        c = pd.to_numeric(df['close'], errors='coerce')
        prev_c = c.shift(1)
        tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=window, min_periods=1).mean().iloc[-1]
        return float(atr) if pd.notna(atr) else 0.0

    @staticmethod
    def calculate_volume_analysis(df: pd.DataFrame) -> dict:
        """量能分析:包含成交量爆發與量價關係"""
        avg_volume = df['volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['volume'] / avg_volume

        change = df['close'].diff()
        df['obv'] = (np.sign(change).fillna(0) * df['volume']).cumsum()

        curr_vol = df['volume'].iloc[-1]
        curr_ratio = df['vol_ratio'].iloc[-1]
        curr_close = df['close'].iloc[-1]
        prev_close = df['close'].shift(1).iloc[-1]
        current_obv = df['obv'].iloc[-1]
        prev_obv = df['obv'].shift(1).iloc[-1]

        is_high_volume = curr_ratio > 2.0
        price_up = curr_close > prev_close
        obv_rising = current_obv > prev_obv
        is_divergence = False
        if curr_close > df['close'].iloc[-2] and curr_ratio < 1.0:
            is_divergence = True

        return {
            "curr_vol": curr_vol,
            "vol_ratio": curr_ratio,
            "is_high_volume": bool(is_high_volume),
            "trend_match": "good" if (price_up and is_high_volume) else "weak",
            "divergence_warning": is_divergence,
            "obv_rising": bool(obv_rising)
        }
    @staticmethod
    def calculate_ma_cross(df: pd.DataFrame, short=20, long=60) -> dict:
        """移動平均線交叉分析 (MA Cross)"""
        df[f'ma_{short}'] = df['close'].rolling(window=short).mean()
        df[f'ma_{long}'] = df['close'].rolling(window=long).mean()

        curr_short = df[f'ma_{short}'].iloc[-1]
        curr_long = df[f'ma_{long}'].iloc[-1]
        prev_short = df[f'ma_{short}'].iloc[-2]
        prev_long = df[f'ma_{long}'].iloc[-2]

        status = "neutral"
        if prev_short <= prev_long and curr_short > curr_long:
            status = "golden_cross"
        elif prev_short >= prev_long and curr_short < curr_long:
            status = "death_cross"

        return {
            "ma_short": curr_short,
            "ma_long": curr_long,
            "status": status
        }
    

    @staticmethod
    def calculate_bias(df: pd.DataFrame, window: int) -> float:
        """
        乖離率 (Bias Ratio) = (收盤 - MA) / MA * 100。
        正乖離過大代表短線漲多易回檔;負乖離過大代表超跌。回傳最新一期百分比。
        """
        if 'close' not in df.columns or df.empty:
            return 0.0
        close = pd.to_numeric(df['close'], errors='coerce')
        ma = close.rolling(window=window, min_periods=1).mean()
        if ma.empty or ma.iloc[-1] == 0 or pd.isna(ma.iloc[-1]):
            return 0.0
        return float((close.iloc[-1] - ma.iloc[-1]) / ma.iloc[-1] * 100.0)

    @staticmethod
    def calculate_trailing_return(prices, lookback: int, skip: int = 0) -> float:
        """
        中期價格動能 (Trailing Return) = close[-1-skip] / close[-1-skip-lookback] − 1 (%)。
        skip 用來略過最近數日 (避開短線反轉污染,類似學術動能的 12-1)。
        接受價格 DataFrame (取 'close' 欄) 或收盤 Series;資料不足回傳 0.0 (中性)。
        """
        if prices is None:
            return 0.0
        if hasattr(prices, "columns"):
            c = pd.to_numeric(prices["close"], errors="coerce").dropna() if "close" in prices.columns else None
        else:
            c = pd.to_numeric(prices, errors="coerce").dropna()
        if c is None or len(c) < (lookback + skip + 1):
            return 0.0
        now = c.iloc[-1 - skip]
        then = c.iloc[-1 - skip - lookback]
        return float((now / then - 1.0) * 100.0) if then else 0.0

    @staticmethod
    def calculate_volume_spike(df: pd.DataFrame, window: int = 20) -> float:
        """
        量能爆發倍數 (Volume Spike) = 當日成交量 / 近 window 日均量。
        > 2 代表明顯放量,常見於突破或出貨。回傳最新一期倍數 (無資料回 1.0)。
        """
        if 'volume' not in df.columns or df.empty:
            return 1.0
        vol = pd.to_numeric(df['volume'], errors='coerce')
        avg = vol.rolling(window=window, min_periods=1).mean()
        if avg.empty or avg.iloc[-1] == 0 or pd.isna(avg.iloc[-1]):
            return 1.0
        return float(vol.iloc[-1] / avg.iloc[-1])

    def analyze_stock(self, raw_data: dict) -> dict:
        """整合所有指標的分析入口"""
        results: Dict[str, Any] = {}
        if not isinstance(raw_data, dict):
            raise ValueError("raw_data must be a dict of timeframes to list-like OHLCV records")

        for tf, data in raw_data.items():
            df = pd.DataFrame(data)
            if 'close' not in df.columns:
                results[f"{tf}_analysis"] = {"error": "missing close column"}
                continue

            try:
                analysis = {
                    "macd": self.calculate_macd(df.copy()),
                    "kd": self.calculate_kd(df.copy()),
                    "bb": self.calculate_bb(df.copy()),
                    "rsi": self.calculate_rsi(df.copy()),
                    "volume": self.calculate_volume_analysis(df.copy()),
                    "ma_cross": self.calculate_ma_cross(df.copy())
                }
            except Exception as e:
                analysis = {"error": str(e)}

            results[f"{tf}_analysis"] = analysis

        return results

    # ==================================================================
    # 動態追高門檻 (Adaptive Chase Band) — 依個股波動體質彈性化「追高」判定
    # ==================================================================
    @staticmethod
    def calculate_adaptive_chase_band(df, price_series, cur,
                                      z: float = 3.0, horizon: int = 25,
                                      atr_window: int = 14,
                                      min_band: float = 15.0,
                                      max_band: float = 45.0) -> dict:
        """
        以個股「近期波動體質」動態決定：現價要偏離 POC 多少 % 才算『追高/已離成本區』，
        取代原本寫死的 25%。回傳一個 dict，核心欄位是 threshold_pct(動態門檻)。

        為什麼要動態化(踩過的痛點)：
          牛皮大型股(低波動)漲 15% 可能已是極端超漲；中小型飆股(高波動)帶量噴到 35%
          都還在主升段。用同一把 25% 尺去量兩者，不是太早剁掉飆股、就是太晚警示牛皮股。

        波動度估計(取兩來源較大值 → 較保守/寬鬆的擴張上限，寧可讓強勢股多跑一段)：
          1) 日報酬率標準差 σ_ret(%)：對「gap 校正後」的收盤序列計算，永遠可得
             (合成/無 high-low 的資料也能用) —— 對應需求中的「近 90 天報酬率標準差」。
          2) ATR(atr_window) 佔『現價』的百分比：需 high/low(或 max/min)欄位，缺則略過。
             註：以『現價』為分母(非 POC)。對飆股而言 POC 遠在下方，用 POC 當分母會把
             波動% 灌爆；以現價為分母才是標準 ATR% 語意，且套上下限夾擠後對追高股等價。

        門檻模型(可調)：允許價格在 horizon 個交易日的持有窗內，做一次 z 倍標準差的順勢
          延伸才算追高 → band = z * sqrt(horizon) * σ_daily，再夾在 [min_band, max_band]。
          預設 z=3、horizon=25 → 係數=15：σ≈1%(牛皮)→貼 15% 下限；σ≈3%(妖股)→頂到 45%。
        """
        empty = {"threshold_pct": 25.0, "volatility_pct": None,
                 "atr_pct": None, "ret_std_pct": None, "source": ""}
        if price_series is None or len(price_series) < 3 or not cur:
            return empty

        ret = pd.Series(price_series).pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        std_pct = float(ret.std(ddof=1) * 100.0) if len(ret) > 2 else 0.0
        vol_pct, source = std_pct, "std"

        atr_pct = None
        high_col = 'high' if 'high' in df.columns else ('max' if 'max' in df.columns else None)
        low_col = 'low' if 'low' in df.columns else ('min' if 'min' in df.columns else None)
        if high_col and low_col:
            atr = TechnicalEngine.calculate_atr(df, window=atr_window)
            if atr and atr > 0:
                atr_pct = atr / cur * 100.0
                if atr_pct > vol_pct:            # 取較大者 → 較寬鬆(保守)的追高上限
                    vol_pct, source = atr_pct, "atr"

        coeff = z * math.sqrt(max(int(horizon), 1))
        threshold = min(max(coeff * vol_pct, min_band), max_band)
        return {
            "threshold_pct": round(float(threshold), 1),
            "volatility_pct": round(float(vol_pct), 2),
            "atr_pct": (round(float(atr_pct), 2) if atr_pct is not None else None),
            "ret_std_pct": round(float(std_pct), 2),
            "source": source,
        }

    # ==================================================================
    # 籌碼成本區 (Volume Profile) — 大戶成本區 / 支撐壓力 / 買進區間
    # ==================================================================
    @staticmethod
    def calculate_volume_profile(df, lookback: int = 90, bins: int = 30,
                                 value_area_pct: float = 0.70,
                                 chase_z: float = 3.0, chase_horizon: int = 25,
                                 min_chase_band: float = 15.0,
                                 max_chase_band: float = 45.0,
                                 strong_above_ratio: float = 0.4,
                                 strong_above_floor: float = 10.0,
                                 strong_above_cap: float = 25.0) -> dict:
        """
        以「最近 lookback 個交易日」的量價分布,找出市場/大戶的主要成本區。
          POC (Point of Control):成交量最密集的價位 = 主要成本區中心
          價值區間 VAL~VAH:涵蓋 value_area_pct(預設70%)成交量的價格帶 = 支撐~壓力
          現價相對位置:下方(便宜/有支撐) / 區內(成本帶) / 上方(偏高/追高)
        注意:lookback 預設 90 天(近期時間窗),反映『當前』成本區;過長會混入舊價格區間,
              使 POC 落在早已脫離的低價帶,失去參考意義。
        回傳 dict;資料不足時各值為 None、status 為 ""。
        """
        import numpy as np
        empty = {"poc": None, "val": None, "vah": None, "price_vs_poc_pct": None,
                 "status": "", "support": None, "resistance": None,
                 "chase_threshold_pct": None, "volatility_pct": None, "vol_source": ""}
        if df is None or len(df) < 30 or "close" not in df.columns or "volume" not in df.columns:
            return empty
        d = df.copy()
        # 先按日期排序 (確保 tail 取到的是『最近』而非資料原順序中的任意段落)
        if "date" in d.columns:
            d = d.sort_values("date")
        d = d.tail(lookback).copy()
        price = pd.to_numeric(d["close"], errors="coerce")
        vol = pd.to_numeric(d["volume"], errors="coerce")
        m = price.notna() & vol.notna() & (vol >= 0)
        price, vol = price[m].reset_index(drop=True), vol[m].reset_index(drop=True)
        if len(price) < 30:
            return empty
        # 跳空回補:視窗內若有分割/減資/大額配息造成的價格斷點 (單日跳動 >30%),
        #   會讓 POC 落在『事件前的舊價格尺度』,與現價/支撐壓力兜不起來 → 先接平。
        pv = price.values.astype(float).copy()
        factor = np.ones(len(pv))
        for i in range(1, len(pv)):
            if pv[i] > 0 and pv[i - 1] > 0:
                ratio = pv[i] / pv[i - 1]
                if ratio < 0.7 or ratio > 1.5:
                    factor[:i] *= ratio
        if not np.allclose(factor, 1.0):
            pv = pv * factor
            price = pd.Series(pv)
        if price.max() <= price.min():
            return empty
        # 以整個 lookback 視窗的量價分布計算成本區(不再限縮現價 ±25% 價格帶);
        #   由 lookback(近期時間窗)本身控制樣本的時間範圍,價格帶不設人工上下限。
        lo, hi = float(price.min()), float(price.max())
        edges = np.linspace(lo, hi, bins + 1)
        idx = np.clip(np.digitize(price.values, edges) - 1, 0, bins - 1)
        vol_by_bin = np.zeros(bins)
        for i, v in zip(idx, vol.values):
            vol_by_bin[i] += v
        centers = (edges[:-1] + edges[1:]) / 2.0
        total = vol_by_bin.sum()
        if total <= 0:
            return empty
        poc_i = int(vol_by_bin.argmax())
        poc = float(centers[poc_i])

        # 價值區間:由 POC 向兩側擴張,直到累積達 value_area_pct
        order = np.argsort(vol_by_bin)[::-1]
        acc, chosen = 0.0, set()
        for i in order:
            chosen.add(int(i))
            acc += vol_by_bin[i]
            if acc / total >= value_area_pct:
                break
        val = float(centers[min(chosen)])
        vah = float(centers[max(chosen)])

        cur = float(price.iloc[-1])
        price_vs_poc = (cur - poc) / poc * 100.0 if poc else None
        cur_i = int(np.clip(np.digitize([cur], edges)[0] - 1, 0, bins - 1))

        # 【現價相對位置 — 修正籌碼誤判 + 動態波動門檻】
        # 以『與 POC(主成本中心)的距離』判斷是否追高,而非只看 greedy 價值區的 VAL/VAH 邊界。
        # 一檔由低基期大幅上漲的股票,近月換手會把高檔各價位都墊出量能,VAH 被拉到接近現價;
        # 但主成本 (POC) 仍遠在下方。此時現價其實是『站在主成本區上方很多』,若只用 cur<=VAH 判斷
        # 會誤歸為『成本區內』,下游再據此當成『成本帶下緣/偏防守區』——把追高說成防守買點(危險)。
        #
        # 追高門檻不再寫死 25%,改由 calculate_adaptive_chase_band 依個股波動體質動態決定:
        #   牛皮股門檻自動收窄(貼近 15%)、飆股門檻自動放寬(可到 45%),避免用同一把尺
        #   一體適用。門檻與波動度一併回傳,供下游(回測 Trailing Stop)沿用同一套動態標準。
        band = TechnicalEngine.calculate_adaptive_chase_band(
            d, price, cur, z=chase_z, horizon=chase_horizon,
            min_band=min_chase_band, max_band=max_chase_band)
        chase_threshold = band["threshold_pct"]
        extended_above = (cur > poc and price_vs_poc is not None
                          and price_vs_poc >= chase_threshold)

        # 【強勢臨界點動態化 — 與追高門檻線性連動】
        # 舊版 strong_above_pct 寫死 15%,對不同波動體質一體適用並不理想:牛皮股 15% 已算噴很多、
        #   妖股 15% 還在主升段。改成隨 calculate_adaptive_chase_band 的動態追高門檻線性縮放:
        #     strong_above_pct = chase_threshold_pct * strong_above_ratio (預設 0.4)
        #   再夾在 [strong_above_floor, strong_above_cap] = [10%, 25%],四捨五入 1 位:
        #     牛皮股門檻 15% → 6% 過度敏感 → 拉回下限 10%;
        #     妖股門檻 45% → 18% 落在區間內;若日後門檻更寬(理論上 >62.5%)才會頂到 25% 上限。
        #   仍排在 extended_above『之後』判定:因 strong_above_pct(≤ ~18) 恆 < chase_threshold(≥15),
        #   極端追高永遠先攔截,分流順序與腳下支撐計算(狀態字首仍為「主」)完全不受影響。
        strong_above_pct = round(
            max(min(chase_threshold * strong_above_ratio, strong_above_cap), strong_above_floor), 1)

        # 【狀態細分 — 修正「站在主成本區上方卻被判成套牢區」的邏輯矛盾】
        # 舊版只用粗暴三元 (上方/下方/區內)。痛點 (8210 勤誠):POC 890、現價 1175 (+32%)、
        #   支撐 1011、壓力 1301。飆股動態門檻放寬到 ~35% → 未觸發 extended_above;高檔換手
        #   把 VAH 墊高到接近現價 → cur < vah。結果 +32% 的強勢股掉進 else 的『成本區內(套牢
        #   賣壓區)』,下游生成『現價落在成本帶中段套牢區,但大戶成本在 890』的自相矛盾文字。
        #
        # 解法:在「極端追高 (extended_above / 破 VAH)」與「貼著成本帶 (in-band)」之間,補一段
        #   獨立的『主成本區上方(波段強勢/未過熱)』狀態 —— 現價明顯高於 POC (>= strong_above_pct)
        #   但尚未觸發極端追高門檻。如此 +32% 的現價不再被委屈塞進套牢區。
        #   strong_above_pct 已改為隨動態追高門檻線性縮放(見上方計算),恆小於 chase_threshold,
        #   故極端分流永遠先判、順序不受影響。
        #
        # 注意:狀態字串下游以『子字串』比對分流 (advisor 判 "下方" / "上方");故所有『高於成本』
        #   的狀態措辭都必須含 "上方"、且絕不可出現 "下方" 二字,否則會被錯誤分流成『相對便宜』。
        above_poc = (cur > poc)
        if extended_above or cur > vah:
            status = "上方(偏高/追高,已離成本區)"
        elif cur < val:
            status = "下方(相對便宜/上方套牢輕)"
        elif above_poc and price_vs_poc is not None and price_vs_poc >= strong_above_pct:
            status = "主成本區上方(波段強勢/未過熱)"
        else:
            status = "成本區內(套牢賣壓區,需帶量突破)"

        # 支撐/壓力:掃描全部『高量能節點 (HVN:量能 >= POC 的 25%)』,而非僅限 70% 價值區成員——
        #   否則漲勢途中未進價值區的中繼換手平台會被忽略,使支撐直接跳空到 POC、與 POC 硬重合而
        #   看似失靈(例:4958 支撐硬等於成本 202)。改用 HVN 後,像 8046 主成本區上緣另有換手節點
        #   (POC 911、支撐 938) 的情形才能被正確標出。
        hvn_thresh = vol_by_bin[poc_i] * 0.25
        hvn = [float(centers[i]) for i in range(bins) if vol_by_bin[i] >= hvn_thresh]
        # 【雙引擎階梯式支撐/壓力:POC(定海神針) + 近期 HVN(動態雷達)】
        # 依『現價相對主成本區的位階』分三段取支撐,兼顧飆股靈敏度與牛皮股穩定度,
        #   且完全沿用字首分流(advisor 仍靠子字串對齊,此處僅決定數值不動狀態字串):
        #   ① 極端追高(字串以 "上方" 開頭):現價腳下已懸空 → 排除過熱節點,支撐往『下方』退守。
        #   ② 波段強勢緩衝(字串以 "主" 開頭):主升段(如 8210),不理會遠在底部的 POC →
        #        支撐鎖在現價腳下最近、已密集換手的次級 HVN 平台(如 1011)。
        #   ③ 常態/盤整/牛皮股(其餘,如 成本區內/下方):近期 HVN 與 POC 高度重疊 →
        #        支撐直接對齊最穩固的歷史大戶成本 POC(定海神針),維持精準打底防禦。
        if status.startswith("上方"):
            # ① 追高:現價『腳下』所在價格帶那根節點不是可退守的支撐(站在上面談不上防守),
            #   支撐取現價所在 bin『下方』最近的量能節點(真正的回檔退守位),壓力取上方最近節點。
            #   如此 4958 現價 588 會落在近期換手密集帶下緣的 571,而非被推到過低的 522。
            lo_edge, hi_edge = float(edges[cur_i]), float(edges[cur_i + 1])
            below = [c for c in hvn if c < lo_edge]
            above = [c for c in hvn if c > hi_edge]
            support = float(max(below)) if below else None
            resistance = float(min(above)) if above else None
        elif status.startswith("主"):
            # ② 波段強勢:支撐貼現價腳下最近的次級 HVN 平台(當下踩著的有效防守位),
            #   不讓它回落到遠在底部的 POC(否則科技飆股主升段支撐會過於遲鈍)。壓力取上方最近節點。
            below = [c for c in hvn if c <= cur]
            above = [c for c in hvn if c >= cur]
            support = float(max(below)) if below else None
            resistance = float(min(above)) if above else None
        else:
            # ③ 常態/盤整/牛皮股:支撐對齊 POC(定海神針)——此類股近期 HVN 與 POC 高度重疊,直接
            #   錨定歷史大戶成本最穩固。惟守住常識『支撐不得高於現價』:若 POC 仍在現價之上(如
            #   『下方』狀態跌破大戶成本),POC 此時是壓力而非支撐 → 支撐退回現價腳下最近 HVN。
            below = [c for c in hvn if c <= cur]
            above = [c for c in hvn if c >= cur]
            if poc <= cur:
                support = float(poc)
            else:
                support = float(max(below)) if below else None
            resistance = float(min(above)) if above else None

        return {"poc": round(poc), "val": round(val), "vah": round(vah),
                "price_vs_poc_pct": (round(price_vs_poc, 1) if price_vs_poc is not None else None),
                "status": status,
                "support": (round(support) if support else None),
                "resistance": (round(resistance) if resistance else None),
                # 動態追高門檻 & 波動體質(供回測 Trailing Stop / 出場邏輯沿用)
                "chase_threshold_pct": chase_threshold,
                "volatility_pct": band["volatility_pct"],
                "vol_source": band["source"]}