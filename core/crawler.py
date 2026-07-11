"""
crawler.py

⚠️ 【建議棄用 / DEPRECATED】
此模組原本直接爬 TWSE T86 CSV 計算投信連買天數,但有兩個問題:
  1. 邏輯較脆弱:用 datetime.now() - i 天硬抓,遇到週末/國定假日/休市會回傳 None,
     原版遇到 None 是 continue(跳過),可能把「昨天休市」誤判成連續(已改為明確處理)。
  2. 與 data_provider.py 的 FinMind 版本重複,兩套邏輯可能給出不一致的天數。

data_provider._calculate_consecutive_streak() 已用 FinMind 資料在記憶體內以
「淨買賣超 (buy - sell)」精準計算連買/連賣天數,且能同時處理外資子類別合併。
新專案請直接使用 data_provider,本檔僅保留作為備援/離線比對。
"""

import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger(__name__)


class StockCrawler:
    @staticmethod
    def _fetch_daily_data(date_str: str):
        """輔助函數:抓取單日三大法人資料。回傳 DataFrame 或 None(當日休市/抓取失敗)。"""
        url = f"https://www.twse.com.tw/fund/T86?response=csv&date={date_str}&selectType=ALL"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return None

            content = response.text.split('\n')
            data_lines = [line for line in content if '證券代號' in line or (len(line.split('","')) > 5)]
            if len(data_lines) < 2:
                return None

            df = pd.read_csv(StringIO('\n'.join(data_lines)))
            df['證券代號'] = df['證券代號'].astype(str).str.strip()
            return df
        except Exception as e:
            logger.warning(f"TWSE 單日抓取失敗 {date_str}: {e}")
            return None

    def get_consecutive_buy_days(self, symbol: str, max_days: int = 20) -> int:
        """
        計算投信連續買超天數。

        【修正】原版把「抓取失敗」與「當日休市」都當成 continue,可能虛增天數。
        現在區分兩種情況:
          - 抓不到整份資料 (df is None):視為休市/非交易日,跳過不計、也不中斷。
          - 有整份資料但查無該股 (停牌):同樣跳過不中斷。
          - 有資料且該股買超 <= 0:才真正中斷連續天數。
        另外把預設回溯天數拉大到 20,避免遇到連假時交易日樣本不足。
        """
        consecutive_days = 0
        checked_trading_days = 0

        for i in range(max_days * 2):  # 預留假日緩衝
            if checked_trading_days >= max_days:
                break

            target_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            df = self._fetch_daily_data(target_date)

            # 整份抓不到 → 視為非交易日,不計也不中斷
            if df is None:
                continue

            checked_trading_days += 1

            stock_row = df[df['證券代號'] == symbol]
            if stock_row.empty:
                # 該股當日無資料(停牌),跳過但不中斷
                continue

            raw_val = str(stock_row.iloc[0]['投信買賣超股數']).replace(',', '').strip()
            buy_val = int(raw_val) if raw_val.replace('-', '').isdigit() else 0

            if buy_val > 0:
                consecutive_days += 1
            else:
                # 買超為 0 或賣超 → 中斷
                break

            time.sleep(0.5)  # 遵守 API 使用規範

        return consecutive_days
