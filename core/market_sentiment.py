import pandas as pd
import numpy as np
from typing import Dict, Any
from .config import fm  # 從 config 直接導入已啟動的對象

# ⚠️ 注意:此模組目前尚未被 main.py 主流程引用,屬於獨立/實驗性籌碼分析工具。
#    本次僅修掉會直接當機的兩個 bug(未定義的 self.thresholds、evaluate 缺 return),
#    但底層資料源仍需確認:FinMind 的 DataLoader 並沒有 get_market_data() 方法,
#    正式接入時請改用 fm.get_data(dataset='TaiwanStockPrice', data_id=..., start_date=...),
#    且股票代號請用 '2330' 而非 Yahoo 格式的 '2330.TW'。

class StockAnalysisFinMind:
    def __init__(self, symbol, interval="1d"):
        """
        symbol: 股票代號 (例如 '2330')
        interval: 時間區間 ('1m', '5m', '1h', '1d', '1w')
        """
        self.symbol = symbol
        self.interval = interval

        # 【修正】原版直接使用 self.thresholds 卻從未定義,一呼叫 evaluate 就 AttributeError。
        self.thresholds = {
            "high_whale": 70.0,   # 主力活躍度高門檻
            "mid_whale": 40.0     # 主力活躍度中門檻
        }

        # ⚠️ 下行為原始寫法,FinMind SDK 實際無 get_market_data;正式使用請改 get_data。
        # self.df = fm.get_market_data(symbol=self.symbol, tr=True)
        try:
            self.df = fm.get_data(
                dataset='TaiwanStockPrice',
                data_id=self.symbol,
                start_date='2024-01-01'
            )
            # 統一欄位名:TaiwanStockPrice 的成交量欄位為 Trading_Volume
            if self.df is not None and 'Trading_Volume' in self.df.columns and 'volume' not in self.df.columns:
                self.df = self.df.rename(columns={'Trading_Volume': 'volume'})
        except Exception:
            self.df = pd.DataFrame()

    def analyze_volume_distribution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """分析成交量集中度,回傳各價格區塊的計數與相關資訊。"""
        prices = df['close'].tolist()
        if not prices:
            return {"bins": [], "counts": [], "bin_size": 0, "min_price": None}
        max_price = max(prices)
        min_price = min(prices)
        range_price = max_price - min_price

        num_bins = 50
        if range_price == 0:
            bin_size = 1.0
        else:
            bin_size = range_price / num_bins

        counts = [0] * num_bins
        bins = []
        for price in df['close']:
            idx = int((price - min_price) // bin_size) if bin_size > 0 else 0
            idx = idx % num_bins
            bins.append(idx)
            counts[idx] += 1

        return {"bins": bins, "counts": counts, "bin_size": bin_size, "min_price": min_price, "max_price": max_price}

    def evaluate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raw_data = {
            "volume_growth": data.get("volume_growth"),
            "volume_stability": data.get("volume_stability"),
            "whale_activity": data.get("whale_activity") or 0,
            "short_interest": data.get("short_interest"),
            "liquidity_score": data.get("liquidity_score") or 0
        }

        # 基礎門檻:排除成交過低的「殭屍股」
        min_liquidity = 50000  # 假設為最小每日成交金額
        is_liquid = raw_data["liquidity_score"] >= min_liquidity

        # 依主力活躍度給籌碼分數
        whale_score = 0
        if raw_data["whale_activity"] > self.thresholds["high_whale"]:
            whale_score = 100
        elif raw_data["whale_activity"] > self.thresholds["mid_whale"]:
            whale_score = 50

        # 【修正】原版沒有 return,呼叫端永遠拿到 None。
        return {
            "is_liquid": bool(is_liquid),
            "whale_score": whale_score,
            "liquidity_score": raw_data["liquidity_score"]
        }

    def calculate_volume_profile(self, bin_size):
        """分析成交密集區 (尋找大戶成本區)"""
        df_recent = self.df.tail(250).copy()
        if df_recent.empty:
            return None, False
        min_p = df_recent['close'].min()
        max_p = df_recent['close'].max()
        bins = np.arange(min_p, max_p + bin_size, bin_size)
        if len(bins) < 2:
            return None, None
        df_recent['price_bin'] = pd.cut(df_recent['close'], bins=bins)

        volume_profile = df_recent.groupby('price_bin', observed=False)['volume'].sum()

        best_cost_zone = volume_profile.idxmax()
        total_vol = volume_profile.sum()
        is_concentrated = (volume_profile.max() / total_vol) > 0.1
        return best_cost_zone, is_concentrated

    def analyze_accumulation(self):
        """籌碼蓄積分析:觀察近期的成交量與價格變動關係"""
        df_recent = self.df.tail(20).copy()
        avg_vol = df_recent['volume'].iloc[:-1].mean()
        df_recent['vol_ratio'] = df_recent['volume'] / avg_vol
        return df_recent

    def run_screening(self, bin_size=None):
        """核心篩選函數"""
        if bin_size is None:
            current_price = self.df['close'].iloc[-1]
            bin_size = max(1, int(current_price * 0.02))

        best_cost_zone, is_concentrated = self.calculate_volume_profile(bin_size=bin_size)

        if best_cost_zone is None:
            print("數據不足,無法計算籌碼分布。")
            return

        current_price = self.df['close'].iloc[-1]

        print(f"--- 股票 {self.symbol} 分析報告 ---")
        print(f"目前價格: {current_price}")
        print(f"分析區塊大小 (bin_size): {bin_size}")
        print(f"核心成本區: {best_cost_zone}")

        dist_to_cost = abs(current_price - best_cost_zone.mid)

        if dist_to_cost < bin_size and is_concentrated:
            print("【篩選通過】強勢籌碼支撐!目前價格與核心區非常接近且籌碼高度集中。")
        elif dist_to_cost < bin_size:
            print("【警告】處於成本帶,但籌碼分布較散(可能有短線參與多)。")
        else:
            print("【排除】目前價格與核心成本區距離過遠。")
