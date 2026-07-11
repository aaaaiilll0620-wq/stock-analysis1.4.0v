import sys
from pathlib import Path

import pandas as pd
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.models import StockData


def make_stock(**overrides) -> StockData:
    """建立一個「體質健康、估值合理、動能中性」的基準 StockData，
    測試時只覆寫想觀察的欄位，避免每個測試都要填滿 30 個欄位。"""
    defaults = dict(
        symbol="2330",
        name="台積電",
        current_price=100.0,
        volume=10000,
        change_percent=1.0,
        ma5=98.0,
        ma20=95.0,
        weekly_ma20=90.0,
        ma5_bias=2.0,
        ma20_bias=5.0,
        volume_spike=1.5,
        rsi=55.0,
        macd=0.5,
        macd_status="neutral",
        macd_golden_cross=False,
        bb_status="",
        institutional_buy_days=0,
        institutional_sell_days=0,
        foreign_buy_days=0,
        foreign_sell_days=0,
        pe_ratio=15.0,
        pb_ratio=2.0,
        price_to_sales=2.0,
        dividend_yield=3.0,
        roe=15.0,
        net_margin=10.0,
        gross_margin=25.0,
        debt_to_asset=40.0,
        current_ratio=150.0,
        rev_cagr=8.0,
        revenue_growth=8.0,
        eps_cagr=10.0,
        net_income_growth=10.0,
        pe_vs_industry=15.0,
        operating_cash_flow=1000.0,
        free_cash_flow=500.0,
        capex=-500.0,
        net_income=800.0,
        ocf_to_net_income=1.25,
        data_confidence=100.0,
    )
    defaults.update(overrides)
    return StockData(**defaults)


@pytest.fixture
def stock_factory():
    return make_stock


def make_ohlcv(closes, volumes=None, start="2024-01-01"):
    """依收盤價序列組出最小可用的 OHLCV DataFrame，供技術指標函式使用。"""
    n = len(closes)
    dates = pd.date_range(start=start, periods=n, freq="D")
    if volumes is None:
        volumes = [1000] * n
    return pd.DataFrame({
        "date": dates,
        "close": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "volume": volumes,
    })


@pytest.fixture
def ohlcv_factory():
    return make_ohlcv
