"""
回測框架 (Backtest) —— 把「看起來合理」變成「證明有效」
================================================================================
核心:point-in-time(時間點對齊),杜絕未來函數(look-ahead bias)。
  在回測某一天時,只用「那天當下真的拿得到」的資料重建 StockData,再跑你現有的
  ScoringManager / ValuationEngine / FundamentalEngine / InvestmentAdvisor,
  取得當時的評級與分數;之後再量測「後續 N 日報酬」作為結果。

杜絕未來函數的三道防線:
  1. 價格 / PER / 月營收:只取 date <= as_of 的切片。
  2. 財報:季報有公告時差,季末後約 45 天才公告 → 回測日尚未公告的季報一律不用。
  3. 未來報酬:用 as_of 當日 vs as_of+持有天數 的收盤價 (這是「結果」,允許取未來)。

用法 (本機、有網路):
    from core.backtest import Backtester
    bt = Backtester(symbols=["2330","2454","2344", ...])
    bt.load()                                  # 每檔抓一次完整歷史 (5 個資料集)
    records = bt.run(start="2023-01-01", end="2025-12-31",
                     rebalance="M", holding_days=20)   # 每月評級,持有20交易日
    bt.summarize(records)                       # 各評級桶的後續報酬 / 勝率 / 樣本數

離線 (無 FinMind) 時可用 Backtester.self_test() 以合成資料驗證流程是否正確。
================================================================================
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable

import pandas as pd
import numpy as np

from core.models import StockData
from core.technical_analysis import TechnicalEngine
from core.data_provider import DataProvider
from core.fundamentals import FundamentalEngine
from core.valuation import ValuationEngine
from core.scoring_manager import ScoringManager
from core.advisor import InvestmentAdvisor

logger = logging.getLogger(__name__)

import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


def output_path(subdir: str, filename: str) -> str:
    """統一輸出路徑:<專案根>/outputs/<subdir>/<filename>,資料夾不存在自動建立。"""
    d = _os.path.join(_PROJECT_ROOT, "outputs", subdir)
    _os.makedirs(d, exist_ok=True)
    return _os.path.join(d, filename)


PUBLISH_LAG_DAYS = 45          # 季報公告時差 (季末後約 45 天才公告,保守估)
HISTORY_START = "2019-01-01"   # 每檔歷史抓取起點 (percentile 需要 2~3 年以上)

# 四級評級常數 (與 InvestmentAdvisor 對齊,供統計/排序/多空價差使用)
R_SUPER, R_STRONG, R_WATCH, R_AVOID = (
    InvestmentAdvisor.RATING_SUPER, InvestmentAdvisor.RATING_STRONG,
    InvestmentAdvisor.RATING_WATCH, InvestmentAdvisor.RATING_AVOID,
)
# 顯示/統計順序:由最積極看多 → 最保守 (多空價差 = 最積極桶 − 避開桶)
RATING_DISPLAY = [R_SUPER, R_STRONG, R_WATCH, R_AVOID]
RATING_RANK = dict(InvestmentAdvisor.RATING_RANK)   # {避開:0, 觀望:1, 強推:2, 強勢買進:3}
BUY_GRADES = (R_SUPER, R_STRONG)                    # 「買進」等級 (權益曲線預設納入 + 觀望)


@dataclass
class HistoryBundle:
    """單檔的完整原始歷史 (一次抓好,回測時反覆切片)。"""
    symbol: str
    name: str = ""
    price: Optional[pd.DataFrame] = None       # TaiwanStockPrice
    per: Optional[pd.DataFrame] = None         # TaiwanStockPER
    revenue: Optional[pd.DataFrame] = None     # TaiwanStockMonthRevenue
    income: Optional[pd.DataFrame] = None       # TaiwanStockFinancialStatements
    balance: Optional[pd.DataFrame] = None       # TaiwanStockBalanceSheet (負債比/流動比率)
    cashflow: Optional[pd.DataFrame] = None       # TaiwanStockCashFlowsStatement (營業現金流/資本支出)
    chip: Optional[pd.DataFrame] = None        # TaiwanStockInstitutionalInvestorsBuySell
    shareholding: Optional[pd.DataFrame] = None   # TaiwanStockShareholding (流通股數/外資持股;供投信吸籌比 whale_concentration)


# ==============================================================================
# 1) 抓取完整歷史 (每檔一次;本機有網路時執行)
# ==============================================================================
def _back_adjust(price_df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    跳空回補(兜底):偵測「單日異常跳動」(分割/大額配息造成的價格斷點),把斷點之前的
    價格乘上比例接平,讓序列連續。台股日漲跌幅 ±10%,故單日 ratio 落在異常區間
    (< 0.7 或 > 1.5) 幾乎必為公司行為而非真實交易 → 安全,不誤傷正常波動。
    即使 FinMind 還原股價對某些 ETF/個股 (如 0050 分割) 還原不乾淨,這層也能補上。
    """
    if price_df is None or price_df.empty or "close" not in price_df.columns:
        return price_df
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(df["close"], errors="coerce").values
    n = len(close)
    if n < 2:
        return df
    factor = np.ones(n)
    hits = 0
    for i in range(1, n):
        if not (close[i] > 0 and close[i - 1] > 0):
            continue
        ratio = close[i] / close[i - 1]
        if ratio < 0.7 or ratio > 1.5:          # 異常跳空 → 視為分割/大額配息
            factor[:i] *= ratio                  # 斷點之前全部縮放到當前尺度
            hits += 1
    if hits == 0:
        return df
    for col in ("open", "max", "min", "close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") * factor
    logger.info(f"跳空回補:接平 {hits} 處價格斷點 (分割/大額配息)。")
    return df


# 是否嘗試 FinMind 還原股價 (TaiwanStockPriceAdj)。此資料集需付費 (Sponsor) 等級,
# 免費 (register) 帳號會抓取失敗。預設 False → 直接用免費股價 + 跳空回補 (_back_adjust)。
# 升級付費後可設 True,優先採用官方還原股價 (仍保留跳空回補當兜底)。
USE_ADJUSTED_PRICE = False


def fetch_history(symbol: str, start_date: str = HISTORY_START) -> HistoryBundle:
    """抓取單檔回測所需的資料集完整歷史。失敗的資料集以 None 帶過。"""
    api = DataProvider._api
    DataProvider._ensure_login()

    def _get(dataset):
        try:
            df = api.get_data(dataset=dataset, data_id=symbol, start_date=start_date)
            return df if df is not None and not df.empty else None
        except Exception as e:
            logger.warning(f"[{symbol}] {dataset} 抓取失敗: {e}")
            return None

    # 價格來源:
    #   付費帳號 (USE_ADJUSTED_PRICE=True) → 優先官方還原股價;失敗再退回免費股價。
    #   免費帳號 (預設) → 直接用免費股價,不去戳註定失敗的付費 API。
    price = None
    if USE_ADJUSTED_PRICE:
        price = _get("TaiwanStockPriceAdj")
    if price is None:
        price = _get("TaiwanStockPrice")
    # 跳空回補:偵測分割/大額配息造成的價格斷崖並接平 (免費帳號還原的主力手段)。
    price = _back_adjust(price)

    return HistoryBundle(
        symbol=symbol,
        price=price,
        per=_get("TaiwanStockPER"),
        revenue=_get("TaiwanStockMonthRevenue"),
        income=_get("TaiwanStockFinancialStatements"),
        balance=_get("TaiwanStockBalanceSheet"),
        cashflow=_get("TaiwanStockCashFlowsStatement"),
        chip=_get("TaiwanStockInstitutionalInvestorsBuySell"),
        shareholding=_get("TaiwanStockShareholding"),   # 流通股數/外資持股 (投信吸籌比、市值分類)
    )


def cached_fetch_history(symbol: str, refresh: bool = False) -> HistoryBundle:
    """
    回測 / 個股分析用:優先讀本機 Parquet 快取重建 HistoryBundle (可直接注入 Backtester.load)。
      · refresh=False (預設):純讀快取,0 次 API。快取需先以 build_cache.py 建好。
      · refresh=True:對每個資料集補抓增量後再組 (會用 API,適合當天要用最新資料時)。
    價格的跳空回補 (_back_adjust) 在載入時套用;快取只存原始資料,維持 PIT 乾淨。
    """
    from core import data_cache
    api = None
    if refresh:
        DataProvider._ensure_login()
        api = DataProvider._api
    dfs = {}
    for field, dataset in data_cache.BUNDLE_DATASETS.items():
        if refresh and api is not None:
            df, _ = data_cache.update_dataset(api, dataset, symbol)
        else:
            df = data_cache.read_cached(dataset, symbol)
        dfs[field] = df if (df is not None and not df.empty) else None
    return HistoryBundle(
        symbol=symbol,
        price=_back_adjust(dfs.get("price")),
        per=dfs.get("per"), revenue=dfs.get("revenue"), income=dfs.get("income"),
        balance=dfs.get("balance"), cashflow=dfs.get("cashflow"),
        chip=dfs.get("chip"), shareholding=dfs.get("shareholding"),
    )


def load_benchmark(symbol: str, refresh: bool = False) -> Optional[HistoryBundle]:
    """
    基準指數 (如 0050) 載入:優先讀本機快取 (0 API),快取無價格才即時抓 (fallback)。
    先在本機跑一次 `python build_cache.py 0050` 把它建進快取,之後回測 / RS / Regime 皆 0 API。
    這解決了原本 benchmark 每跑一次就即時抓 0050 全歷史 (~8 支請求) 的 API 浪費。
    """
    try:
        b = cached_fetch_history(symbol, refresh=refresh)
        if b is not None and getattr(b, "price", None) is not None and not b.price.empty:
            return b
    except Exception as e:
        logger.debug(f"基準 {symbol} 讀快取失敗,改即時抓: {e}")
    return fetch_history(symbol)


# ==============================================================================
# 2) point-in-time 重建 StockData (只用 as_of 當下拿得到的資料)
# ==============================================================================
_tech = TechnicalEngine()


def _slice(df: Optional[pd.DataFrame], as_of: str, col: str = "date") -> Optional[pd.DataFrame]:
    if df is None or df.empty or col not in df.columns:
        return None
    out = df[df[col].astype(str) <= str(as_of)]
    return out if not out.empty else None


def _norm_price(price_df: pd.DataFrame) -> pd.DataFrame:
    """統一 FinMind 欄位供 TechnicalEngine 使用:
    Trading_Volume→volume(股→張)、close→數值、max→high、min→low。"""
    p = price_df.copy()
    if "Trading_Volume" in p.columns and "volume" not in p.columns:
        p["volume"] = pd.to_numeric(p["Trading_Volume"], errors="coerce") / 1000.0  # 股→張
    p["close"] = pd.to_numeric(p["close"], errors="coerce")
    # KD / ATR 需要 high/low (FinMind 為 max/min) → 補上
    if "max" in p.columns and "high" not in p.columns:
        p["high"] = pd.to_numeric(p["max"], errors="coerce")
    if "min" in p.columns and "low" not in p.columns:
        p["low"] = pd.to_numeric(p["min"], errors="coerce")
    return p


# --- 相對強弱 RS (v4.4):大盤 (0050) 截至 as_of 的中期報酬,模組層快取避免重複載入/重算 ---
_RS_BENCHMARK = "0050"
_rs_bench_bundle = None          # None=未載入, False=載入失敗 (快取無 0050)
_rs_mom_cache: Dict[tuple, Optional[float]] = {}


def benchmark_trailing_return(as_of: str, lookback: int, skip: int = 5) -> Optional[float]:
    """大盤 (0050) 截至 as_of 的 trailing return (%),與個股 mom_3m/6m 同參數 (skip=5)。
    僅讀本機快取 (0 API);快取沒建 0050 → 回 None,RS 欄位留 None 不計分。"""
    global _rs_bench_bundle
    key = (str(as_of), lookback)
    if key in _rs_mom_cache:
        return _rs_mom_cache[key]
    if _rs_bench_bundle is None:
        try:
            from core import data_cache
            df = data_cache.read_cached("TaiwanStockPrice", _RS_BENCHMARK)
            _rs_bench_bundle = _back_adjust(df) if (df is not None and not df.empty) else False
        except Exception:
            _rs_bench_bundle = False
    val = None
    if _rs_bench_bundle is not False:
        sliced = _slice(_rs_bench_bundle, as_of)
        if sliced is not None and len(sliced) >= lookback + skip + 1:
            val = _tech.calculate_trailing_return(_norm_price(sliced), lookback, skip=skip)
    _rs_mom_cache[key] = val
    return val


def _industry_value_pct_safe(symbol: str, as_of: str):
    """產業內估值位階 PIT 查詢 (v4.5);參考表缺失/查無值回 None,由估值引擎退回現行配方。"""
    try:
        from core.industry_value import industry_value_pct
        return industry_value_pct(symbol, as_of)
    except Exception:
        return None


def build_pit_stockdata(bundle: HistoryBundle, as_of: str) -> Optional[StockData]:
    """
    以 as_of 為基準,用「當下拿得到」的切片重建 StockData。
    僅計算可乾淨切片的特徵 (技術/估值/營收動能/基本面子集),其餘留中性預設。
    資料不足回傳 None。
    """
    price = _slice(bundle.price, as_of)
    if price is None or len(price) < 25:
        return None

    # --- 價格/量:統一欄位供 TechnicalEngine 使用 (共用 _norm_price) ---
    p = _norm_price(price)
    close = p["close"].dropna()
    if len(close) < 25:
        return None
    last_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    change_pct = (last_price - prev_price) / prev_price * 100.0 if prev_price else 0.0

    ma5 = float(_tech.calculate_ma(p, 5).iloc[-1])
    ma20 = float(_tech.calculate_ma(p, 20).iloc[-1])
    try:
        weekly_ma20 = float(_tech.calculate_weekly_ma20(p.copy()))
    except Exception:
        weekly_ma20 = last_price
    ma5_bias = _tech.calculate_bias(p, 5)
    ma20_bias = _tech.calculate_bias(p, 20)
    vol_spike = _tech.calculate_volume_spike(p, 20)
    mom_6m = _tech.calculate_trailing_return(p, 120, skip=5)   # 近6月動能 (略過最近5日避短線反轉)
    mom_3m = _tech.calculate_trailing_return(p, 60, skip=5)    # 近3月動能
    # 相對強弱 RS (v4.4):個股動能 − 大盤同期;個股歷史不足或無 0050 快取 → None 不計分
    rs_3m = rs_6m = None
    if len(close) >= 60 + 5 + 1:
        b3 = benchmark_trailing_return(as_of, 60)
        if b3 is not None:
            rs_3m = mom_3m - b3
    if len(close) >= 120 + 5 + 1:
        b6 = benchmark_trailing_return(as_of, 120)
        if b6 is not None:
            rs_6m = mom_6m - b6
    atr = _tech.calculate_atr(p, 14)
    atr_pct = (atr / last_price * 100.0) if last_price else 0.0
    try:
        rsi = float(_tech.calculate_rsi(p.copy())["val"])
    except Exception:
        rsi = 50.0
    macd_golden = False
    try:
        _macd = _tech.calculate_macd(p.copy())
        macd_status = _macd.get("status", "neutral")
        macd_golden = (_macd.get("cross") == "golden")   # 與 live 一致:剛出現黃金交叉 → 技術面加分
    except Exception:
        macd_status = "neutral"
    bb_percent_b = None
    try:
        _bb = _tech.calculate_bb(p.copy())
        bb_status = _bb.get("status", "")
        bb_percent_b = _bb.get("percent_b")
    except Exception:
        bb_status = ""
    # 新接入訊號:KD(完整 K/D/J) / MA20-60 交叉 / OBV 量價 (與即時系統一致)
    kd_j_val, ma_cross_status, obv_rising_val, volume_divergence_val = 50.0, "neutral", None, False
    kd_k_val = kd_d_val = 50.0
    obv_above_ma20_val = None
    try:
        _kd = _tech.calculate_kd(p.copy())
        if _kd.get("J") is not None and not pd.isna(_kd.get("J")):
            kd_j_val = float(_kd["J"])
        if _kd.get("K") is not None and not pd.isna(_kd.get("K")):
            kd_k_val = float(_kd["K"])
        if _kd.get("D") is not None and not pd.isna(_kd.get("D")):
            kd_d_val = float(_kd["D"])
    except Exception:
        pass
    try:
        ma_cross_status = _tech.calculate_ma_cross(p.copy(), 20, 60).get("status", "neutral")
    except Exception:
        pass
    try:
        _v = _tech.calculate_volume_analysis(p.copy())
        obv_rising_val = bool(_v.get("obv_rising"))
        volume_divergence_val = bool(_v.get("divergence_warning"))
        obv_above_ma20_val = _v.get("obv_above_ma20")
    except Exception:
        pass
    vp = {"poc": None, "val": None, "vah": None, "price_vs_poc_pct": None, "status": ""}
    try:
        vp = _tech.calculate_volume_profile(p.copy())
    except Exception:
        pass
    volume_lots = float(p["volume"].iloc[-1]) if "volume" in p.columns else 0.0
    volume_concentration = DataProvider._calc_volume_concentration(p, 20)   # 近20日上漲日量佔比% (與 live 一致)

    # --- 估值:PER/PBR/殖利率 + 歷史百分位 (以 as_of 當下的歷史算) ---
    pe_val = pb_val = dy_val = None
    pe_pct = pb_pct = dy_pct = None
    per = _slice(bundle.per, as_of)
    if per is not None:
        per = per.copy()
        for c in ("PER", "PBR", "dividend_yield"):
            if c in per.columns:
                per[c] = pd.to_numeric(per[c], errors="coerce")
        last = per.iloc[-1]
        pe_val = float(last.get("PER")) if pd.notna(last.get("PER")) else None
        pb_val = float(last.get("PBR")) if pd.notna(last.get("PBR")) else None
        dy_val = float(last.get("dividend_yield")) if pd.notna(last.get("dividend_yield")) else None
        if "PER" in per.columns and pe_val is not None:
            pe_pct = DataProvider._percentile_rank(per["PER"], pe_val, positive_only=True)
        if "PBR" in per.columns and pb_val is not None:
            pb_pct = DataProvider._percentile_rank(per["PBR"], pb_val, positive_only=True)
        if "dividend_yield" in per.columns and dy_val is not None:
            dy_pct = DataProvider._percentile_rank(per["dividend_yield"], dy_val, positive_only=False)

    # --- 月營收動能 ---
    rev = _slice(bundle.revenue, as_of)
    rev_growth = DataProvider._calc_rev_yoy(rev) if rev is not None else 0.0
    rev_trend = DataProvider._calc_rev_yoy_smoothed(rev) if rev is not None else None
    mom = DataProvider._calc_rev_momentum(rev) if rev is not None else {}

    # --- 基本面子集 (只用「已公告」的季報:季末 + 45 天 <= as_of) ---
    roe = net_margin = gross_margin = 0.0
    debt_to_asset = 0.0
    current_ratio = 100.0          # 中性預設 (剛好過流動比率門檻 50),待資產負債表覆寫
    eps_growth = ni_growth = None
    net_inc_abs = None
    operating_profit_ratio = None
    asset_turnover_val = None
    operating_cash_flow = free_cash_flow = capex = ocf_to_net_income = None
    as_of_dt = pd.to_datetime(as_of)

    def _published(df):
        if df is None or "date" not in df.columns:
            return None
        ok = df[pd.to_datetime(df["date"], errors="coerce") + pd.Timedelta(days=PUBLISH_LAG_DAYS) <= as_of_dt]
        return ok if not ok.empty else None

    q_revenue = None               # 最新已公告季營收 (供資產週轉率 asset_turnover)
    inc = _published(bundle.income)
    if inc is not None:
        rev_v = DataProvider._latest_value(inc, ["Revenue"], ["營業收入"])
        gp_v = DataProvider._latest_value(inc, ["GrossProfit"], ["營業毛利"])
        ni_v = DataProvider._latest_value(inc, ["IncomeAfterTaxes", "ProfitLoss"],
                                          ["本期淨利", "綜合損益總額"])
        if rev_v:
            q_revenue = rev_v
            if gp_v is not None:
                gross_margin = gp_v / rev_v * 100.0
            if ni_v is not None:
                net_margin = ni_v / rev_v * 100.0
        ni_growth = DataProvider._yoy_growth(
            DataProvider._value_series(inc, ["IncomeAfterTaxes", "ProfitLoss"],
                                       ["本期淨利", "綜合損益總額"]))
        eps_growth = DataProvider._yoy_growth(
            DataProvider._value_series(inc, ["EPS", "BasicEarningsLossPerShare"],
                                       ["基本每股盈餘", "每股盈餘"]))
        net_inc_abs = ni_v      # 絕對淨利,供 ROE 與現金含金量 OCF/NI 共用
        # 本業獲利占比 = 營業利益 / 稅後淨利 (獲利品質判準;>0.8 表獲利主要來自本業)
        op_inc = DataProvider._latest_value(inc, ["OperatingIncome"], ["營業利益"])
        if op_inc is not None and net_inc_abs not in (None, 0):
            operating_profit_ratio = op_inc / net_inc_abs

    # --- 資產負債表 (負債比 / 流動比率 / ROE;與 data_provider 同一套科目與公式) ---
    bs = _published(bundle.balance)
    if bs is not None:
        total_assets = DataProvider._latest_value(bs, ['TotalAssets'], ['資產總計', '資產總額'])
        total_liab = DataProvider._latest_value(bs, ['Liabilities', 'TotalLiabilities'], ['負債總計', '負債總額'])
        curr_assets = DataProvider._latest_value(bs, ['CurrentAssets'], ['流動資產'])
        curr_liab = DataProvider._latest_value(bs, ['CurrentLiabilities'], ['流動負債'])
        equity = DataProvider._latest_value(
            bs, ['Equity', 'EquityAttributableToOwnersOfParent'],
            ['權益總計', '權益總額', '歸屬於母公司業主之權益'])

        if total_assets and total_liab is not None:
            debt_to_asset = total_liab / total_assets * 100.0
        # 總資產週轉率 (v4.4):年化季營收 ÷ 總資產;經營效率訊號,供 fundamentals 計分候選
        if total_assets and q_revenue:
            asset_turnover_val = q_revenue * 4.0 / total_assets
        if curr_liab and curr_assets is not None:
            current_ratio = curr_assets / curr_liab * 100.0
        if equity and net_inc_abs is not None:
            roe = net_inc_abs / equity * 100.0     # 近似 ROE (單季),與即時系統一致

    # --- 現金流量表 (營業現金流/資本支出/自由現金流/現金含金量;與 data_provider 同一套科目) ---
    #     品質關卡需要「營業現金流」,缺了會判 unknown → 強推被卡死,故必須重建。
    cf = _published(bundle.cashflow)
    if cf is not None:
        ocf = DataProvider._latest_value(
            cf, ['CashFlowsProvidedFromUsedInOperatingActivities',
                 'NetCashProvidedByUsedInOperatingActivities',
                 'CashProvidedByUsedInOperatingActivities'],
            ['營業活動之淨現金流', '營業活動之現金流量', '營業活動現金流'])
        capex = DataProvider._latest_value(
            cf, ['AcquisitionOfPropertyPlantAndEquipment',
                 'PaymentsToAcquirePropertyPlantAndEquipment',
                 'PropertyAndPlantAndEquipment'],
            ['取得不動產、廠房及設備', '購置不動產、廠房及設備', '取得不動產廠房及設備'])
        if ocf is not None:
            operating_cash_flow = ocf
            if capex is not None:
                free_cash_flow = ocf + capex if capex < 0 else ocf - capex
            if net_inc_abs not in (None, 0):
                ocf_to_net_income = ocf / net_inc_abs

    # --- 籌碼:連續買賣超 + 法人流向 (point-in-time,與即時系統同一套算法) ---
    trust_days = foreign_days = trust_sell = foreign_sell = 0
    large_holder_activity = foreign_flow = trust_flow = 0.0
    flow_acceleration = 1.0
    institutional_participation = 0.0
    trust_net20_shares = 0.0          # 投信近20日淨買超股數 (供投信吸籌比 whale_concentration)
    foreign_net_ratio: dict = {}      # 外資多天期淨參與率 {1,3,5,10,20}
    trust_net_ratio: dict = {}        # 投信多天期淨參與率 {1,3,5,10,20}
    chip = _slice(bundle.chip, as_of)
    if chip is not None and "name" in chip.columns:
        ns = chip["name"].astype(str).str.strip()
        trust_df = chip[ns.isin(["Investment_Trust", "Investment Trust", "投信"])]
        foreign_df = chip[ns.isin(["Foreign_Investor", "Foreign_Dealer_Self", "Foreign Investor", "外資"])]
        # 自動尋找 buy / sell 欄位 (排除比例欄位)
        bc, sc = "buy", "sell"
        for col in chip.columns:
            cl = col.lower()
            if "buy" in cl and col != "buy_share_per":
                bc = col
            if "sell" in cl and col != "sell_share_per":
                sc = col
        try:
            trust_days = DataProvider._calculate_consecutive_streak(trust_df, bc, sc, "buy")
            trust_sell = DataProvider._calculate_consecutive_streak(trust_df, bc, sc, "sell")
            foreign_days = DataProvider._calculate_consecutive_streak(foreign_df, bc, sc, "buy")
            foreign_sell = DataProvider._calculate_consecutive_streak(foreign_df, bc, sc, "sell")

            dates_sorted = sorted(chip["date"].astype(str).unique())

            def _cut(n):
                return dates_sorted[-n] if len(dates_sorted) >= n else dates_sorted[0]
            cut5, cut10, cut20 = _cut(5), _cut(10), _cut(20)

            foreign_flow = DataProvider._net_buy_lots(foreign_df, bc, sc, cut10)   # 外資近10日淨買超(張)
            trust_flow = DataProvider._net_buy_lots(trust_df, bc, sc, cut10)       # 投信近10日淨買超(張)
            f5 = DataProvider._net_buy_lots(foreign_df, bc, sc, cut5)
            t5 = DataProvider._net_buy_lots(trust_df, bc, sc, cut5)
            large_holder_activity = f5 + t5                                       # 主力近5日淨買超(張)
            f20 = DataProvider._net_buy_lots(foreign_df, bc, sc, cut20)
            t20 = DataProvider._net_buy_lots(trust_df, bc, sc, cut20)
            trust_net20_shares = t20 * 1000.0                    # 張→股,供投信吸籌比
            main5_daily, main20_daily = (f5 + t5) / 5.0, (f20 + t20) / 20.0
            if main20_daily > 0 and main5_daily > 0:
                flow_acceleration = float(main5_daily / main20_daily)
            elif main5_daily > 0 >= main20_daily:
                flow_acceleration = 2.0
            # 法人成交占比:外資+投信近10日 (買+賣) 股數 / (2 × 同期總成交股數)
            inst_gross = (DataProvider._gross_trade_shares(foreign_df, bc, sc, cut10)
                          + DataProvider._gross_trade_shares(trust_df, bc, sc, cut10))
            mkt_vol = DataProvider._market_volume_shares(p, 10)
            if mkt_vol > 0:
                institutional_participation = float(inst_gross / (2.0 * mkt_vol) * 100.0)

            # === 多天期法人淨參與率 (whale 重構基底):net(張) ÷ 同期總量(張),signed、市值中性 ===
            def _vol_lots(nn):
                return float(p["volume"].tail(nn).sum()) if "volume" in p.columns else 0.0
            for _n in (1, 3, 5, 10, 20):
                _cn = _cut(_n)
                _vn = _vol_lots(_n)
                if _vn > 0:
                    foreign_net_ratio[_n] = DataProvider._net_buy_lots(foreign_df, bc, sc, _cn) / _vn
                    trust_net_ratio[_n] = DataProvider._net_buy_lots(trust_df, bc, sc, _cn) / _vn
        except Exception as e:
            logger.debug(f"[{bundle.symbol}] {as_of} 籌碼流向計算略過: {e}")

    # --- 投信吸籌比 + 產業分流 (PIT:流通股數只取 date<=as_of;產業別為靜態屬性,用當前對照表安全) ---
    whale_concentration = 0.0
    foreign_hold_ratio = 0.0
    shares_outstanding = 0.0
    sh = _slice(bundle.shareholding, as_of)
    if sh is not None:
        if "NumberOfSharesIssued" in sh.columns:
            shares = pd.to_numeric(sh.iloc[-1]["NumberOfSharesIssued"], errors="coerce")
            if not pd.isna(shares) and shares > 0:
                shares_outstanding = float(shares)
                whale_concentration = float(trust_net20_shares / shares * 100.0)  # 投信近20日淨買超÷流通股%
        if "ForeignInvestmentSharesRatio" in sh.columns:
            fr_ratio = pd.to_numeric(sh.iloc[-1]["ForeignInvestmentSharesRatio"], errors="coerce")
            if not pd.isna(fr_ratio):
                foreign_hold_ratio = float(fr_ratio)

    industry = ""
    sector_category = "B"
    is_financial = False
    try:
        from core.sector import SectorClassifier
        industry = DataProvider._ensure_industry_map().get(str(bundle.symbol)) or ""
        market_cap = (last_price * shares_outstanding) if (last_price > 0 and shares_outstanding > 0) else None
        sector_category = SectorClassifier.classify(
            bundle.symbol, industry=industry, foreign_ratio=foreign_hold_ratio,
            atr_pct=atr_pct, market_cap=market_cap)
        is_financial = bool(industry and any(k in industry for k in ("金融", "保險", "銀行", "證券")))
    except Exception as e:
        logger.debug(f"[{bundle.symbol}] {as_of} 產業分流略過 (離線/無對照表): {e}")

    return StockData(
        symbol=bundle.symbol, name=bundle.name or bundle.symbol,
        current_price=last_price, volume=int(volume_lots), change_percent=change_pct,
        pe_ratio=pe_val, pb_ratio=pb_val, dividend_yield=(dy_val or 0.0),
        pe_percentile=pe_pct, pb_percentile=pb_pct, dividend_yield_percentile=dy_pct,
        industry_value_percentile=_industry_value_pct_safe(bundle.symbol, as_of),
        roe=roe, net_margin=net_margin, gross_margin=gross_margin,
        debt_to_asset=debt_to_asset, current_ratio=current_ratio,
        asset_turnover=asset_turnover_val,
        operating_cash_flow=operating_cash_flow, free_cash_flow=free_cash_flow,
        capex=capex, net_income=net_inc_abs, ocf_to_net_income=ocf_to_net_income,
        operating_profit_ratio=operating_profit_ratio,
        pe_vs_industry=(pe_val if pe_val is not None else 10.0),   # 與 live 一致:餵入原始 PE 供 fundamentals 評分
        rev_cagr=(rev_trend if rev_trend is not None else rev_growth),
        revenue_growth=rev_growth,
        eps_cagr=(eps_growth if eps_growth is not None else 0.0),
        net_income_growth=(ni_growth if ni_growth is not None else 0.0),
        revenue_mom=mom.get("mom"),
        revenue_cum_yoy=mom.get("cum_yoy"), revenue_accel=mom.get("accel"),
        revenue_growth_streak=int(mom.get("streak") or 0),
        revenue_asof=mom.get("asof"),
        ma5=ma5, ma20=ma20, weekly_ma20=weekly_ma20,
        ma5_bias=ma5_bias, ma20_bias=ma20_bias, volume_spike=vol_spike,
        mom_3m=mom_3m, mom_6m=mom_6m, rs_3m=rs_3m, rs_6m=rs_6m,
        rsi=rsi, macd_status=macd_status, macd_golden_cross=macd_golden, bb_status=bb_status,
        bb_percent_b=bb_percent_b,
        kd_j=kd_j_val, kd_k=kd_k_val, kd_d=kd_d_val, ma_cross_status=ma_cross_status,
        obv_rising=obv_rising_val, obv_above_ma20=obv_above_ma20_val,
        volume_divergence=volume_divergence_val,
        cost_zone_poc=vp.get("poc"), value_area_low=vp.get("val"),
        value_area_high=vp.get("vah"), price_vs_poc_pct=vp.get("price_vs_poc_pct"),
        cost_zone_status=vp.get("status", ""),
        cost_zone_support=vp.get("support"), cost_zone_resistance=vp.get("resistance"),
        atr=atr, atr_pct=atr_pct,
        institutional_buy_days=trust_days, institutional_sell_days=trust_sell,
        foreign_buy_days=foreign_days, foreign_sell_days=foreign_sell,
        large_holder_activity=large_holder_activity,
        foreign_flow=foreign_flow, trust_flow=trust_flow,
        flow_acceleration=flow_acceleration,
        institutional_participation=institutional_participation,
        whale_concentration=whale_concentration,
        foreign_net_ratio=foreign_net_ratio, trust_net_ratio=trust_net_ratio,
        volume_concentration=volume_concentration,
        sector_category=sector_category, industry=industry, is_financial=is_financial,
    )


# ==============================================================================
# 3) 回測引擎
# ==============================================================================
class Backtester:
    def __init__(self, symbols: List[str], names: Optional[Dict[str, str]] = None,
                 mode: str = "balanced"):
        self.symbols = symbols
        self.names = names or {}
        self.mode = mode
        self.bundles: Dict[str, HistoryBundle] = {}
        # 引擎 (與正式流程同一套)
        self.fund = FundamentalEngine()
        self.val = ValuationEngine()
        self.scorer = ScoringManager(mode=mode)
        self.advisor = InvestmentAdvisor(
            min_score=ScoringManager.MODES[mode]["min_score"],
            mode_weights=ScoringManager.MODES[mode].get("composite_weights"),
            mode_name=mode,
        )
        # 【市場 Regime】用基準 (0050) 逐 as_of 判斷多頭/空頭 → 空頭降動能加重基本面。
        #   use_regime=False 可完全關閉 (A/B 對照);benchmark 快取無資料時自動退回不調整。
        self.use_regime = True
        self.regime_benchmark = "0050"
        self.benchmark_bundle = None      # 延遲載入 (第一次 _regime_at 時)
        self._regime_cache: Dict[str, Optional[str]] = {}

    def _regime_at(self, as_of: str) -> Optional[str]:
        """回傳 as_of 當下的大盤 regime ('bull'/'neutral'/'bear');關閉或無基準快取 → None。"""
        if not self.use_regime:
            return None
        if self.benchmark_bundle is None:
            try:
                self.benchmark_bundle = load_benchmark(self.regime_benchmark) or False
            except Exception:
                self.benchmark_bundle = False
        if not self.benchmark_bundle:
            return None
        key = str(as_of)
        if key not in self._regime_cache:
            from core.regime import classify_regime
            self._regime_cache[key] = classify_regime(self.benchmark_bundle.price, key)
        return self._regime_cache[key]

    def load(self, fetcher: Callable[[str], HistoryBundle] = None):
        """抓取每檔完整歷史 (本機執行)。可注入 fetcher 供測試。"""
        fetcher = fetcher or fetch_history
        for sym in self.symbols:
            b = fetcher(sym)
            b.name = self.names.get(sym, sym)
            self.bundles[sym] = b
        return self

    def _score_one(self, bundle: HistoryBundle, as_of: str) -> Optional[dict]:
        stock = build_pit_stockdata(bundle, as_of)
        if stock is None:
            return None
        try:
            fund_res = self.fund.evaluate(vars(stock))
            val_res = self.val.evaluate(vars(stock))
            score = self.scorer.calculate_score(stock)
            score.raw_stock = stock
            score.fund_info = fund_res
            self.advisor.current_regime = self._regime_at(as_of)
            self.advisor.advise(stock, fund_res, val_res, score)
        except Exception as e:
            logger.warning(f"[{bundle.symbol}] {as_of} 評分失敗: {e}")
            return None
        # 診斷:記錄「強烈推薦」各道關卡是否通過 (與 advisor._decide_rating 同一套邏輯)
        adv = self.advisor
        cash_risk = fund_res.get("cash_flow_health", {}).get("risk_level", "unknown")
        profit_risk = fund_res.get("profit_quality", {}).get("risk", False)
        val_status = val_res.get("valuation_status", "")
        washout = getattr(score, "_washout", (False, ""))[0]
        gates = {
            # 價值型『強烈推薦』關卡 (原邏輯)
            "g_基本面過門檻": bool(fund_res.get("is_passed", False)),
            "g_品質OK": (cash_risk in ("healthy", "watch")) and not profit_risk,
            "g_估值OK": ("偏低" in val_status) or ("合理" in val_status),
            "g_分數達門檻": score.total_score >= adv.min_score,
            "g_RSI不過熱": stock.rsi < adv.rsi_extreme,
            "g_不追高": stock.ma20_bias <= adv.bias_chase,
            "g_籌碼OK": score.whale_score >= adv.chip_min,
            "g_非洗盤": not washout,
            # 順勢動能『強勢買進』軌道關卡 (與 advisor 實際判定式對齊,供診斷主流飆股是否被捕捉)
            "g_多頭排列": adv._uptrend(stock),
            "g_動能夠強": adv._momentum_hot(stock, score),
            "g_籌碼點火": adv._chips_igniting(stock, score),
            "g_非衰竭出貨": not adv._blowoff_risk(stock),
        }
        rec = {"symbol": bundle.symbol, "name": bundle.name or bundle.symbol,
               "as_of": as_of, "price": stock.current_price,
               "rating": score.rating, "total_score": score.total_score,
               "whale_score": score.whale_score, "valuation_status": val_status,
               "valuation_label": getattr(score, "valuation_label", ""),
               "sector": getattr(stock, "sector_category", "")}
        rec.update(gates)
        return rec

    @staticmethod
    def _forward_return(bundle: HistoryBundle, as_of: str, holding_days: int) -> Optional[float]:
        """as_of 當日收盤 → as_of 之後第 holding_days 個交易日收盤的報酬率 (%)。"""
        if bundle.price is None or "date" not in bundle.price.columns:
            return None
        df = bundle.price.copy()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        idx = df.index[df["date"].astype(str) <= str(as_of)]
        if len(idx) == 0:
            return None
        i0 = idx[-1]
        i1 = i0 + holding_days
        if i1 >= len(df):
            return None
        p0, p1 = df.loc[i0, "close"], df.loc[i1, "close"]
        return float((p1 - p0) / p0 * 100.0) if p0 else None

    # --------------------------------------------------------------
    # 動態籌碼支撐停損 (Dynamic Cost-Zone Stop) — 持股期間逐根 K 更新
    # --------------------------------------------------------------
    @staticmethod
    def _cost_zone_on(bundle: HistoryBundle, as_of: str) -> Optional[dict]:
        """在 as_of『當下』(僅用 date<=as_of 的切片)重算籌碼成本區,
        回傳含 support / status / chase_threshold_pct / volatility_pct。無未來函數。"""
        price = _slice(bundle.price, as_of)
        if price is None or len(price) < 30:
            return None
        p = _norm_price(price)
        if p["close"].dropna().shape[0] < 30:
            return None
        try:
            return _tech.calculate_volume_profile(p)
        except Exception:
            return None

    @staticmethod
    def _simulate_exit(bundle: HistoryBundle, as_of: str, holding_days: int = 20,
                       use_support_stop: bool = True, use_trailing: bool = True,
                       trail_mult: float = 2.5, cap_mult: float = 1.0,
                       min_hold: int = 1) -> Optional[dict]:
        """
        路徑相依出場模擬(取代固定持有期):進場 = as_of 收盤,持股期間逐根 K 以
        _cost_zone_on 動態更新籌碼區,收盤『實質』跌破防線 → 隔日開盤市價出清。

        出場防線(優先序):
          1) 動態支撐停損:status 為『上方(追高)』或『成本區內』時,收盤 < 當前動態 support → 出場。
             (依你定調:盤中假跌破不算,只認收盤 close < support;下方/相對便宜狀態不套用此線。)
          2) 移動停利 — 分層併用,取較緊者(min):
               a. σ 移動停利(Chandelier 式,日常主鎖):giveback_a = trail_mult × volatility_pct(%)。
                  高波動飆股 buffer 大(不易被洗)、低波動牛皮股 buffer 小(緊貼防線鎖利)。
               b. 追高門檻硬上限(regime 級 backstop):giveback_b = cap_mult × chase_threshold_pct(%)。
                  當 σ 估計失真(急縮或暴衝)導致 a 過鬆時,用它硬性封頂『從最高點的最大回吐』。
             實際 buffer = min(giveback_a, giveback_b);收盤 < peak × (1 − buffer/100) → 出場。
          3) 時間停損:達 holding_days 未觸發 → 到期收盤出場(與原 _forward_return 相容,績效可比)。

        回傳 dict:forward_return(%)、exit_reason、bars_held、exit_date;資料不足回 None。
        """
        df = bundle.price
        if df is None or "date" not in df.columns:
            return None
        d = df.copy()
        d["close"] = pd.to_numeric(d["close"], errors="coerce")
        d = d.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        idx = d.index[d["date"].astype(str) <= str(as_of)]
        if len(idx) == 0:
            return None
        i0 = int(idx[-1])
        p0 = float(d.loc[i0, "close"])
        if not p0:
            return None
        open_col = "open" if "open" in d.columns else None
        peak = p0
        last_i = min(i0 + holding_days, len(d) - 1)

        def _exit(t_close_i, price_i, reason):
            """在第 t_close_i 根收盤觸發 → 隔日(t_close_i+1)開盤市價出清;無隔日則以當根收盤。"""
            j = t_close_i + 1
            if j <= len(d) - 1:
                px = float(d.loc[j, open_col]) if open_col else float(d.loc[j, "close"])
                xd = str(d.loc[j, "date"])
            else:
                px = float(d.loc[t_close_i, "close"])
                xd = str(d.loc[t_close_i, "date"])
            return {"forward_return": (px - p0) / p0 * 100.0, "exit_reason": reason,
                    "bars_held": t_close_i - i0, "exit_date": xd}

        for t in range(i0 + 1, last_i + 1):
            as_of_t = str(d.loc[t, "date"])
            close_t = float(d.loc[t, "close"])
            peak = max(peak, close_t)
            held = t - i0
            cz = Backtester._cost_zone_on(bundle, as_of_t)
            if not cz or held < min_hold:
                continue
            support = cz.get("support")
            status = cz.get("status", "") or ""
            vol_pct = cz.get("volatility_pct")
            chase_thr = cz.get("chase_threshold_pct")

            # 1) 動態支撐停損 (追高 或 成本區內;收盤跌破)
            if use_support_stop and support and close_t < float(support) \
                    and (status.startswith("上方") or status.startswith("成本區內")):
                return _exit(t, close_t, "dynamic_support")

            # 2) 移動停利:σ 日常鎖 + 追高門檻硬上限,取較緊者
            if use_trailing:
                givebacks = []
                if vol_pct:
                    givebacks.append(("vol_trailing", trail_mult * float(vol_pct)))
                if chase_thr:
                    givebacks.append(("chase_cap", cap_mult * float(chase_thr)))
                if givebacks:
                    reason, buf = min(givebacks, key=lambda kv: kv[1])
                    if close_t < peak * (1.0 - buf / 100.0):
                        return _exit(t, close_t, reason)

        # 3) 時間停損:到期收盤 (與原 _forward_return 等價)
        return {"forward_return": (float(d.loc[last_i, "close"]) - p0) / p0 * 100.0,
                "exit_reason": "time_stop", "bars_held": last_i - i0,
                "exit_date": str(d.loc[last_i, "date"])}

    def _rebalance_dates(self, start: str, end: str, freq: str) -> List[str]:
        """由任一檔的交易日,取每期(M/W)最後一個交易日作為評級日。"""
        all_dates = set()
        for b in self.bundles.values():
            if b.price is not None and "date" in b.price.columns:
                all_dates.update(b.price["date"].astype(str).tolist())
        dates = sorted(d for d in all_dates if start <= d <= end)
        if not dates:
            return []
        s = pd.Series(pd.to_datetime(dates), index=pd.to_datetime(dates))
        key = s.dt.to_period("W" if freq.upper().startswith("W") else "M")
        picked = s.groupby(key).max()
        return [d.strftime("%Y-%m-%d") for d in picked]

    def run(self, start: str, end: str, rebalance: str = "M",
            holding_days: int = 20, exit_mode: str = "dynamic_stop", **stop_kw) -> pd.DataFrame:
        """逐評級日 × 逐檔:產生 (評級, 分數, 後續報酬) 記錄表。

        exit_mode:
          "dynamic_stop" (預設,核心) 動態籌碼支撐停損 + 分層移動停利 (holding_days 為最長持有上限);
                         收盤實質跌破量價成本區 (POC/Support) 或觸發 σ 移動停利 (Chandelier) 即果斷出場,
                         不再傻抱固定天數。額外 **stop_kw 透傳給 _simulate_exit。
          "horizon"      固定持有 holding_days 根 K → 收盤出場 (原行為,供對照/回歸測試用)。
        dynamic_stop 的 **stop_kw:use_support_stop / use_trailing / trail_mult / cap_mult / min_hold;
        輸出多帶 exit_reason / bars_held / exit_date。
        """
        rows = []
        for as_of in self._rebalance_dates(start, end, rebalance):
            for sym, b in self.bundles.items():
                rec = self._score_one(b, as_of)
                if rec is None:
                    continue
                if exit_mode == "dynamic_stop":
                    sim = self._simulate_exit(b, as_of, holding_days, **stop_kw)
                    if sim is None:
                        continue
                    rec.update(sim)                     # forward_return / exit_reason / bars_held / exit_date
                else:
                    fwd = self._forward_return(b, as_of, holding_days)
                    if fwd is None:
                        continue
                    rec["forward_return"] = fwd
                rows.append(rec)
        df = pd.DataFrame(rows)
        df.attrs["holding"] = holding_days
        df.attrs["exit_mode"] = exit_mode
        return df

    # --------------------------------------------------------------
    # 4) 統計:各評級桶的後續報酬 / 勝率 / 樣本數 + 多空價差
    # --------------------------------------------------------------
    @staticmethod
    def _dw(s) -> int:
        """字串顯示寬度 (中文/全形算 2)。"""
        return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))

    @classmethod
    def _pad(cls, s, width, align="left") -> str:
        s = str(s)
        gap = max(0, width - cls._dw(s))
        if align == "right":
            return " " * gap + s
        return s + " " * gap

    @classmethod
    def _print_table(cls, headers, rows, aligns=None):
        """CJK 寬度感知的表格輸出 (中文不再歪)。"""
        aligns = aligns or (["left"] + ["right"] * (len(headers) - 1))
        cols = list(zip(*([headers] + rows))) if rows else [[h] for h in headers]
        widths = [max(cls._dw(x) for x in col) for col in cols]
        line = "  ".join(cls._pad(h, widths[i], aligns[i]) for i, h in enumerate(headers))
        print(line)
        print("─" * cls._dw(line))
        for r in rows:
            print("  ".join(cls._pad(c, widths[i], aligns[i]) for i, c in enumerate(r)))

    @classmethod
    def summarize(cls, records: pd.DataFrame, by: str = "rating") -> pd.DataFrame:
        if records is None or records.empty:
            print("無回測記錄。")
            return pd.DataFrame()

        order = RATING_DISPLAY   # [強勢買進, 強烈推薦, 觀望追蹤, 謹慎避開]

        # ---- (A) 依評級分桶:後續報酬 / 勝率 / 樣本數 ----
        g = records.groupby(by)["forward_return"]
        stat = pd.DataFrame({
            "cnt": g.count(), "mean": g.mean().round(2), "med": g.median().round(2),
            "win": (records.assign(w=records["forward_return"] > 0).groupby(by)["w"].mean() * 100).round(1),
            "std": g.std().round(2),
        })
        keys = [o for o in order if o in stat.index] + [i for i in stat.index if i not in order]
        stat = stat.reindex(keys)

        print("\n" + "=" * 64)
        print(f"回測結果 ①  依「{by}」分桶 — 後續 {records.attrs.get('holding', '')}日報酬")
        print("=" * 64)
        rows = [[k, str(int(stat.loc[k, "cnt"])), f'{stat.loc[k,"mean"]:+.2f}',
                 f'{stat.loc[k,"med"]:+.2f}', f'{stat.loc[k,"win"]:.1f}', f'{stat.loc[k,"std"]:.2f}']
                for k in stat.index]
        cls._print_table(["評級/分類", "樣本數", "平均報酬%", "中位數%", "勝率%", "標準差"], rows)

        # 多空價差 (絕對報酬):優先『強勢買進 − 謹慎避開』,逐級退回
        if R_AVOID in stat.index:
            for buy_bucket in (R_SUPER, R_STRONG, R_WATCH):
                if buy_bucket in stat.index:
                    spread = stat.loc[buy_bucket, "mean"] - stat.loc[R_AVOID, "mean"]
                    tag = "多空價差" if buy_bucket in (R_SUPER, R_STRONG) else "分化幅度"
                    note = "  ← 正且大代表評級有鑑別力" if buy_bucket == R_SUPER else \
                           f"  (以 {buy_bucket} 為買進桶;此區間未出現更高級)"
                    print(f"\n{tag} ({buy_bucket} − {R_AVOID}):{spread:+.2f}%{note}")
                    break

        # 市場中性多空 (同日『買進級 − 避開』再平均):剔除大盤 beta,才是真正的鑑別力。
        #   大多頭時避開桶也被大盤灌成正報酬,絕對價差會失真;同日相對比較把大盤漲跌抵銷。
        if "as_of" in records.columns and R_AVOID in stat.index:
            buy_set = {R_SUPER, R_STRONG}
            per_day = []
            for _, g in records.groupby("as_of"):
                b = g[g["rating"].isin(buy_set)]["forward_return"]
                a = g[g["rating"] == R_AVOID]["forward_return"]
                if len(b) >= 1 and len(a) >= 1:
                    per_day.append(float(b.mean() - a.mean()))
            if len(per_day) >= 3:
                mn = float(np.mean(per_day))
                win = float(np.mean([1.0 if x > 0 else 0.0 for x in per_day]) * 100)
                print(f"市場中性多空 (同日 買進級 − 避開,剔除大盤beta):{mn:+.2f}%"
                      f"  (含 {len(per_day)} 期、期勝率 {win:.0f}%)  ← 這才是去 beta 的真實鑑別力")

        # ---- (B) 個股 × 評級 明細:看得出「是誰、被評成什麼」 ----
        if "symbol" in records.columns and by == "rating":
            print("\n" + "=" * 64)
            print("回測結果 ②  個股明細 — 各股在回測期間被評為各評級的次數與平均報酬")
            print("=" * 64)
            name_map = records.drop_duplicates("symbol").set_index("symbol")["name"].to_dict() \
                if "name" in records.columns else {}
            rows = []
            for sym, grp in records.groupby("symbol"):
                nm = name_map.get(sym, "")
                cnt_by = grp["rating"].value_counts().to_dict()
                avg_ret = grp["forward_return"].mean()
                dominant = grp["rating"].mode().iloc[0] if not grp["rating"].mode().empty else ""
                rows.append([
                    f"{sym} {nm}",
                    str(cnt_by.get(R_SUPER, 0)),
                    str(cnt_by.get(R_STRONG, 0)),
                    str(cnt_by.get(R_WATCH, 0)),
                    str(cnt_by.get(R_AVOID, 0)),
                    f"{avg_ret:+.2f}",
                    dominant,
                ])
            cls._print_table(
                ["股票", "強勢", "強推", "觀望", "避開", "平均報酬%", "多數評級"], rows)

        # ③ 每次都印買進級診斷 (兩軌關卡未過率),方便持續調校門檻
        if by == "rating" and "g_籌碼OK" in records.columns:
            cls.diagnose(records)

        return stat.rename(columns={"cnt": "樣本數", "mean": "平均報酬%", "med": "中位數報酬%",
                                    "win": "勝率%", "std": "標準差"})

    # 兩條買進軌道的關卡分組 (診斷用):價值型『強烈推薦』與順勢動能『強勢買進』
    VALUE_GATES = ["g_基本面過門檻", "g_品質OK", "g_估值OK", "g_分數達門檻",
                   "g_RSI不過熱", "g_不追高", "g_籌碼OK", "g_非洗盤"]
    MOMENTUM_GATES = ["g_基本面過門檻", "g_品質OK", "g_多頭排列", "g_動能夠強",
                      "g_籌碼點火", "g_非衰竭出貨"]

    @classmethod
    def diagnose(cls, records: pd.DataFrame):
        """診斷為何無買進級:綜合分分布 + 各關卡未過率 + 兩軌 (價值/動能) 分別的瓶頸。"""
        gate_cols = [c for c in records.columns if c.startswith("g_")]
        if not gate_cols:
            print("(無關卡診斷資料,請用最新版 backtest.py 重跑)")
            return
        n = len(records)
        print("\n" + "=" * 64)
        print("回測結果 ③  買進級診斷 — 為什麼沒有『強勢買進 / 強烈推薦』?")
        print("=" * 64)

        # (a) 綜合分分布
        ts = records["total_score"]
        print("綜合分分布:")
        print(f"  最低 {ts.min():.1f}｜中位 {ts.median():.1f}｜平均 {ts.mean():.1f}｜最高 {ts.max():.1f}")
        pass_score = (records["g_分數達門檻"]).mean() * 100
        print(f"  達到『分數門檻』的比例:{pass_score:.0f}%")

        # (b) 各關卡未過率 (越高越可能是瓶頸)
        rows = []
        for g in gate_cols:
            fail = int((~records[g].astype(bool)).sum())
            rows.append([g[2:], str(fail), f"{fail / n * 100:.1f}"])
        rows.sort(key=lambda r: float(r[2]), reverse=True)
        print("\n各關卡『未通過』次數 (未過率高者即瓶頸):")
        cls._print_table(["關卡", "未過次數", "未過率%"], rows)

        # (c) 兩軌分別「同時通過全部關卡」= 本可列為該買進級
        def _track(track_gates, label):
            cols = [g for g in track_gates if g in records.columns]
            if not cols:
                return
            all_pass = int(records[cols].astype(bool).all(axis=1).sum())
            print(f"\n[{label}] 同時通過該軌全部關卡 (= 應可入選):{all_pass}/{n}")
            gb = records[cols].astype(bool)
            one = records[(~gb).sum(axis=1) == 1]
            if not one.empty:
                og = ~one[cols].astype(bool)
                blk = {g[2:]: int(og[g].sum()) for g in cols if int(og[g].sum())}
                r2 = sorted([[k, str(v)] for k, v in blk.items()], key=lambda r: int(r[1]), reverse=True)
                print(f"  『只差一道關卡』{len(one)} 筆,卡在:")
                cls._print_table(["關卡 (只差這一道)", "次數"], r2)

        _track(cls.VALUE_GATES, "價值型·強烈推薦")
        _track(cls.MOMENTUM_GATES, "順勢動能·強勢買進")
        print("\n→ 放寬未過率最高的那道關卡,最能增加對應買進級的入選數。")

    # --------------------------------------------------------------
    # 5) 權益曲線:每期買進符合策略的股票(等權),複利串成累積報酬,對比大盤
    # --------------------------------------------------------------
    @staticmethod
    def _price_on(bundle: HistoryBundle, date: str) -> Optional[float]:
        if bundle is None or bundle.price is None or "date" not in bundle.price.columns:
            return None
        d = bundle.price[bundle.price["date"].astype(str) <= str(date)]
        if d.empty:
            return None
        c = pd.to_numeric(d.sort_values("date")["close"], errors="coerce").dropna()
        return float(c.iloc[-1]) if not c.empty else None

    def equity_curve(self, start: str, end: str, rebalance: str = "M",
                     strategy_ratings=(R_SUPER, R_STRONG),
                     benchmark: str = "0050", benchmark_bundle: Optional[HistoryBundle] = None,
                     plot: bool = True) -> pd.DataFrame:
        """
        每個評級日買進所有「評級 ∈ strategy_ratings」的股票(等權),持有到下一評級日換股,
        複利串成權益曲線;與大盤(預設 0050)buy&hold 對比。
        區間報酬用「評級日→下一評級日」,無重疊、無未來函數。
        """
        dates = self._rebalance_dates(start, end, rebalance)
        if len(dates) < 2:
            print("評級日不足,無法建立權益曲線。")
            return pd.DataFrame()
        if benchmark_bundle is None and benchmark:
            try:
                benchmark_bundle = load_benchmark(benchmark)
            except Exception as e:
                logger.warning(f"基準 {benchmark} 抓取失敗,略過對比: {e}")

        strat_eq, bench_eq = [1.0], [1.0]
        rows = []
        for d0, d1 in zip(dates, dates[1:]):
            rets = []
            for sym, b in self.bundles.items():
                rec = self._score_one(b, d0)
                if rec and rec["rating"] in strategy_ratings:
                    p0, p1 = self._price_on(b, d0), self._price_on(b, d1)
                    if p0 and p1:
                        rets.append(p1 / p0 - 1.0)
            port_ret = float(np.mean(rets)) if rets else 0.0
            strat_eq.append(strat_eq[-1] * (1.0 + port_ret))
            br = 0.0
            if benchmark_bundle is not None:
                bp0, bp1 = self._price_on(benchmark_bundle, d0), self._price_on(benchmark_bundle, d1)
                if bp0 and bp1:
                    br = bp1 / bp0 - 1.0
            bench_eq.append(bench_eq[-1] * (1.0 + br))
            rows.append({"date": d1, "持股數": len(rets),
                         "本期策略%": round(port_ret * 100, 2), "本期大盤%": round(br * 100, 2),
                         "策略淨值": round(strat_eq[-1], 4), "大盤淨值": round(bench_eq[-1], 4)})

        curve = pd.DataFrame(rows)
        self._report_equity(curve, dates, strat_eq, bench_eq,
                             benchmark_bundle is not None, benchmark, plot)
        return curve

    def ranked_equity_curve(self, start: str, end: str, rebalance: str = "M",
                            top_n: int = 5, weighting: str = "score",
                            require_pass: bool = True, benchmark: str = "0050",
                            benchmark_bundle: Optional[HistoryBundle] = None,
                            plot: bool = True) -> pd.DataFrame:
        """
        【排序配置 long-only】每期依綜合分排序,只買最高分的 top_n 檔,持有到下一評級日換股。
        直接利用『市場中性檢驗確認的排序能力』做集中多頭配置 (不放空,散戶可實作)。

          weighting = "score"  → 依 (綜合分) 加權,分數越高配越多 (預設)。
                      "equal"  → top_n 等權。
          require_pass = True  → 僅在通過基本面硬門檻的股票中排序 (剔除地雷)。
        區間報酬用「評級日→下一評級日」,無重疊、無未來函數。
        """
        dates = self._rebalance_dates(start, end, rebalance)
        if len(dates) < 2:
            print("評級日不足,無法建立排序權益曲線。")
            return pd.DataFrame()
        if benchmark_bundle is None and benchmark:
            try:
                benchmark_bundle = load_benchmark(benchmark)
            except Exception as e:
                logger.warning(f"基準 {benchmark} 抓取失敗,略過對比: {e}")

        strat_eq, bench_eq = [1.0], [1.0]
        rows = []
        for d0, d1 in zip(dates, dates[1:]):
            ranked = []
            for sym, b in self.bundles.items():
                rec = self._score_one(b, d0)
                if not rec:
                    continue
                if require_pass and not rec.get("g_基本面過門檻", True):
                    continue
                p0, p1 = self._price_on(b, d0), self._price_on(b, d1)
                if p0 and p1:
                    ranked.append((float(rec["total_score"]), p1 / p0 - 1.0))
            ranked.sort(key=lambda x: x[0], reverse=True)
            picks = ranked[:top_n]
            if picks:
                if weighting == "equal":
                    port_ret = float(np.mean([r for _, r in picks]))
                else:                                   # 分數加權 (分數平移為正權重)
                    lo = min(s for s, _ in picks)
                    base = [max(s - lo + 1e-6, 1e-6) for s, _ in picks]
                    wsum = sum(base) or 1.0
                    port_ret = float(sum(w / wsum * r for w, (_, r) in zip(base, picks)))
            else:
                port_ret = 0.0
            strat_eq.append(strat_eq[-1] * (1.0 + port_ret))
            br = 0.0
            if benchmark_bundle is not None:
                bp0, bp1 = self._price_on(benchmark_bundle, d0), self._price_on(benchmark_bundle, d1)
                if bp0 and bp1:
                    br = bp1 / bp0 - 1.0
            bench_eq.append(bench_eq[-1] * (1.0 + br))
            rows.append({"date": d1, "持股數": len(picks),
                         "本期策略%": round(port_ret * 100, 2), "本期大盤%": round(br * 100, 2),
                         "策略淨值": round(strat_eq[-1], 4), "大盤淨值": round(bench_eq[-1], 4)})

        curve = pd.DataFrame(rows)
        print("\n" + "=" * 64)
        print(f"排序配置 long-only — 每期買綜合分前 {top_n} 名 ({weighting} 加權)"
              f"{' · 僅過門檻股' if require_pass else ''}")
        print("=" * 64)
        self._report_equity(curve, dates, strat_eq, bench_eq,
                             benchmark_bundle is not None, benchmark, plot)
        return curve

    @staticmethod
    def _metrics(eq: List[float], first: str, last: str) -> dict:
        arr = np.array(eq)
        total = arr[-1] - 1.0
        years = max((pd.to_datetime(last) - pd.to_datetime(first)).days / 365.25, 1e-6)
        cagr = arr[-1] ** (1 / years) - 1.0 if arr[-1] > 0 else -1.0
        run_max = np.maximum.accumulate(arr)
        mdd = float((arr / run_max - 1.0).min())
        return {"total": total, "cagr": cagr, "mdd": mdd}

    @classmethod
    def _report_equity(cls, curve, dates, strat_eq, bench_eq, has_bench, benchmark, plot):
        if curve.empty:
            return
        sm = cls._metrics(strat_eq, dates[0], dates[-1])
        print("\n" + "=" * 64)
        print(f"權益曲線 — 每期買進策略標的(等權)、複利  ({dates[0]} ~ {dates[-1]})")
        print("=" * 64)
        rows = [["策略(本系統)", f"{sm['total']*100:+.1f}", f"{sm['cagr']*100:+.1f}", f"{sm['mdd']*100:.1f}"]]
        if has_bench:
            bm = cls._metrics(bench_eq, dates[0], dates[-1])
            rows.append([f"大盤 {benchmark}", f"{bm['total']*100:+.1f}", f"{bm['cagr']*100:+.1f}", f"{bm['mdd']*100:.1f}"])
        cls._print_table(["組合", "總報酬%", "年化%", "最大回檔%"], rows)
        if has_bench:
            excess = (strat_eq[-1] - 1) - (bench_eq[-1] - 1)
            print(f"\n超額報酬 (策略 − 大盤):{excess*100:+.1f}%  ← 正代表贏過大盤")
        win_n = int((curve["本期策略%"] > 0).sum())
        print(f"期勝率:{win_n/len(curve)*100:.0f}%  ({win_n}/{len(curve)} 期為正)")
        cls._ascii_curve(strat_eq, bench_eq if has_bench else None)
        if plot:
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                x = [pd.to_datetime(dates[0])] + [pd.to_datetime(d) for d in curve["date"]]
                try:
                    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Arial Unicode MS", "DejaVu Sans"]
                    plt.rcParams["axes.unicode_minus"] = False
                except Exception:
                    pass
                plt.figure(figsize=(10, 5))
                plt.plot(x, strat_eq, label="Strategy", linewidth=2)
                if has_bench:
                    plt.plot(x, bench_eq, label=f"Benchmark {benchmark}", linewidth=2, linestyle="--")
                plt.title("Backtest Equity Curve")
                plt.ylabel("Equity (start=1)")
                plt.legend(); plt.grid(alpha=0.3)
                _png = output_path("charts", "equity_curve.png")
                plt.savefig(_png, dpi=120, bbox_inches="tight")
                print(f"\n📈 權益曲線圖已存:{_png}")
            except ImportError:
                print("\n(未安裝 matplotlib,略過 PNG;pip install matplotlib 可產圖)")

    @staticmethod
    def _ascii_curve(strat_eq, bench_eq=None, width=56, height=10):
        series = {"策略": strat_eq}
        if bench_eq is not None:
            series["大盤"] = bench_eq
        lo = min(min(s) for s in series.values())
        hi = max(max(s) for s in series.values())
        rng = (hi - lo) or 1.0

        def sample(eq):
            if len(eq) <= width:
                return eq
            idx = np.linspace(0, len(eq) - 1, width).astype(int)
            return [eq[i] for i in idx]
        grid = [[" "] * width for _ in range(height)]
        for nm, mark in (("大盤", "."), ("策略", "*")):
            if nm not in series:
                continue
            s = sample(series[nm])
            for xi, v in enumerate(s):
                yi = height - 1 - int((v - lo) / rng * (height - 1))
                grid[yi][xi] = mark
        print("\nASCII 走勢 (  * 策略   . 大盤  ):")
        for i, row in enumerate(grid):
            tag = f"{hi:5.2f} " if i == 0 else (f"{lo:5.2f} " if i == height - 1 else "      ")
            print(f"  {tag}│" + "".join(row))
        print("        └" + "─" * width)

    # --------------------------------------------------------------
    # 6) 參數網格搜尋:找出「多空價差最大」的權重/門檻組合
    # --------------------------------------------------------------
    # 預設五維度綜合權重方案 (fundamental/valuation/technical/momentum/whale)
    WEIGHT_PROFILES = {
        "均衡":     {"fundamental": 0.25, "valuation": 0.20, "technical": 0.20, "momentum": 0.15, "whale": 0.20},
        "重基本面": {"fundamental": 0.40, "valuation": 0.20, "technical": 0.15, "momentum": 0.10, "whale": 0.15},
        "重估值":   {"fundamental": 0.20, "valuation": 0.35, "technical": 0.15, "momentum": 0.15, "whale": 0.15},
        "重動能":   {"fundamental": 0.15, "valuation": 0.15, "technical": 0.25, "momentum": 0.30, "whale": 0.15},
        "重籌碼":   {"fundamental": 0.15, "valuation": 0.15, "technical": 0.15, "momentum": 0.15, "whale": 0.40},
    }

    def _precompute(self, start, end, rebalance, holding_days):
        """對每個 (評級日 × 檔) 預先算好 point-in-time 特徵、基本面、估值、後續報酬。
        這些都與『參數』無關,只算一次,之後每組參數重複使用 → 網格搜尋才快。"""
        cache = []
        for as_of in self._rebalance_dates(start, end, rebalance):
            for sym, b in self.bundles.items():
                stock = build_pit_stockdata(b, as_of)
                if stock is None:
                    continue
                fwd = self._forward_return(b, as_of, holding_days)
                if fwd is None:
                    continue
                try:
                    fr = self.fund.evaluate(vars(stock))
                    vr = self.val.evaluate(vars(stock))
                    base = self.scorer.calculate_score(stock)   # tech/mom/whale 與參數無關
                except Exception:
                    continue
                cache.append((as_of, stock, fr, vr, base.technical_score,
                              base.momentum_score, base.whale_score, fwd))
        return cache

    def _score_cache_with(self, cache, advisor):
        """用指定 advisor 重跑評級,回傳 {評級: [後續報酬,...]}。"""
        from core.models import ScoreResult
        buckets = {R_SUPER: [], R_STRONG: [], R_WATCH: [], R_AVOID: []}
        for as_of, stock, fr, vr, tech, mom, whale, fwd in cache:
            sr = ScoreResult(symbol=stock.symbol, name=stock.name, total_score=0.0,
                             technical_score=tech, momentum_score=mom, whale_score=whale,
                             summary="")
            sr.raw_stock = stock
            sr.fund_info = fr
            try:
                advisor.current_regime = self._regime_at(as_of)
                advisor.advise(stock, fr, vr, sr)
            except Exception:
                continue
            if sr.rating in buckets:
                buckets[sr.rating].append(fwd)
        return buckets

    @staticmethod
    def _bucket_spread(buckets, min_samples, signal_mode="buy_grade"):
        """
        由分桶算多空價差;樣本不足回傳 None。
          signal_mode='strong_only' → 買進桶 = 強勢買進 + 強烈推薦 (兩個真正的買進級)
          signal_mode='buy_grade'   → 買進桶 = 強勢買進 + 強烈推薦 + 觀望追蹤 (路線一)
        回傳 (spread, buy_mean, avoid_mean, n_top, n_watch, n_avoid)。
        n_top = 強勢買進 + 強烈推薦 的樣本數。
        """
        import numpy as np
        super_, strong = buckets.get(R_SUPER, []), buckets.get(R_STRONG, [])
        watch, avoid = buckets.get(R_WATCH, []), buckets.get(R_AVOID, [])
        top = list(super_) + list(strong)
        buy = top if signal_mode == "strong_only" else top + list(watch)
        if len(buy) < min_samples or len(avoid) < min_samples:
            return None
        bm, am = float(np.mean(buy)), float(np.mean(avoid))
        return (bm - am, bm, am, len(top), len(watch), len(avoid))

    def validate_signal(self, start, end, rebalance="M", holding_days=20,
                        min_samples=8, train_ratio=0.6):
        """
        路線一驗證:用『當前模式的預設參數』,把「只買強推」vs「買進(強推+觀望)」
        兩種訊號定義的 train/test 多空價差攤開對比,判斷哪一種當買進訊號較穩健。
        """
        print("預先計算 point-in-time 特徵 (只算一次)...")
        cache = self._precompute(start, end, rebalance, holding_days)
        if not cache:
            print("無足夠資料。")
            return
        dates_sorted = sorted({c[0] for c in cache})
        split_date = dates_sorted[max(1, int(len(dates_sorted) * train_ratio))]
        train = [c for c in cache if c[0] < split_date]
        test = [c for c in cache if c[0] >= split_date]
        bk_train = self._score_cache_with(train, self.advisor)
        bk_test = self._score_cache_with(test, self.advisor)

        print("\n" + "=" * 64)
        print(f"路線一驗證 — 兩種買進訊號定義的 train/test 多空價差")
        print(f"  (模式 {self.mode} 預設參數;train ~{split_date} 前 / test 之後)")
        print("=" * 64)
        rows = []
        verdict = {}
        for mode, label in (("strong_only", "只買強推"), ("buy_grade", "買進=強推+觀望")):
            tr = self._bucket_spread(bk_train, min_samples, mode)
            te = self._bucket_spread(bk_test, max(3, min_samples // 2), mode)
            tr_s = f'{tr[0]:+.2f}' if tr else "n/a"
            te_s = f'{te[0]:+.2f}' if te else "n/a"
            hold = "✅ train/test 皆正" if (tr and te and tr[0] > 0 and te[0] > 0) else \
                   ("❌ 未同時為正" if (tr and te) else "—樣本不足")
            rows.append([label, tr_s, te_s, hold])
            verdict[mode] = (tr[0] if tr else None, te[0] if te else None,
                             tr and te and tr[0] > 0 and te[0] > 0)
        self._print_table(["買進訊號定義", "train價差%", "test價差%", "樣本外驗證"], rows)

        bg = verdict["buy_grade"]
        so = verdict["strong_only"]
        print()
        if bg[2]:
            print("👉 路線一成立:『買進=強推+觀望』在 train/test 都為正 → 這是現在就能用的有效策略。")
            print("   用法:把『觀望追蹤』與以上視為買進候選 (系統核心價值 = 篩掉爛股 + 參與多頭)。")
        elif so[2]:
            print("👉『只買強推』反而較穩;但強推樣本通常偏少,建議加大股票池再確認。")
        else:
            print("⚠️ 上述『絕對報酬』檢驗未過 → 再看下方『市場中性』檢驗,剃除大盤漲跌後是否有排序力。")

        # ---- 路線 Y:市場中性分位數檢驗 (剃除大盤 beta) ----
        #   每個評級日『同一天內』比較:綜合分最高前 1/3 vs 最低後 1/3 的後續報酬差。
        #   因為是同日相對比較,大盤的絕對漲跌自動抵銷 → 純檢驗系統的『排序能力』。
        sc_train = self._scored_records(train, self.advisor)
        sc_test = self._scored_records(test, self.advisor)
        qtr = self._quantile_spread(sc_train)
        qte = self._quantile_spread(sc_test)
        print("\n" + "=" * 64)
        print("市場中性檢驗 (路線Y) — 同日『高分前1/3 − 低分後1/3』報酬差")
        print("=" * 64)
        qtr_s = f'{qtr[0]:+.2f}% (含 {qtr[1]} 期)' if qtr else "樣本不足"
        qte_s = f'{qte[0]:+.2f}% (含 {qte[1]} 期)' if qte else "樣本不足"
        self._print_table(["分位數多空 (市場中性)", "數值"],
                          [["train 前1/3 − 後1/3", qtr_s], ["test  前1/3 − 後1/3", qte_s]])
        if qtr and qte:
            if qtr[0] > 0 and qte[0] > 0:
                print("\n✅ 市場中性檢驗過關:綜合分『排序』在 train/test 都能拉出正價差 →")
                print("   系統確實有選股排序能力,只是被大盤絕對漲跌淹沒。可用『分位數多空/相對配重』方式運用。")
            elif qtr[0] > 0 >= qte[0]:
                print("\n❌ 排序能力樣本外失效 (train 正、test 負) → 綜合分與未來相對強弱關係不穩定。")
            else:
                print("\n❌ 連 train 的排序都非正 → 目前綜合分不具穩定排序力,建議轉『品質篩選器』定位。")
        print("\n說明:市場中性檢驗若過、但絕對報酬檢驗不過,代表系統會『排序』但不會擇時;")
        print("     實務上可用『買最高分一籃、放空/避開最低分一籃』或依分數加減碼來運用。")
        return verdict

    def _scored_records(self, cache, advisor):
        """回傳 [(as_of, total_score, forward_return, rating), ...] 供分位數檢驗。"""
        from core.models import ScoreResult
        out = []
        for as_of, stock, fr, vr, tech, mom, whale, fwd in cache:
            sr = ScoreResult(symbol=stock.symbol, name=stock.name, total_score=0.0,
                             technical_score=tech, momentum_score=mom, whale_score=whale, summary="")
            sr.raw_stock = stock
            sr.fund_info = fr
            try:
                advisor.current_regime = self._regime_at(as_of)
                advisor.advise(stock, fr, vr, sr)
            except Exception:
                continue
            out.append((as_of, sr.total_score, fwd, sr.rating))
        return out

    @staticmethod
    def _quantile_spread(scored, q=1 / 3, min_per_side=2):
        """每期同日 top q vs bottom q 的報酬差,再平均。回傳 (平均價差, 有效期數) 或 None。"""
        import numpy as np
        from collections import defaultdict
        by_date = defaultdict(list)
        for as_of, score, fwd, rating in scored:
            by_date[as_of].append((score, fwd))
        spreads = []
        for as_of, items in by_date.items():
            n = len(items)
            k = int(n * q)
            if k < min_per_side:
                continue
            items.sort(key=lambda x: x[0])          # 依綜合分升冪
            bottom = [f for _, f in items[:k]]
            top = [f for _, f in items[-k:]]
            spreads.append(float(np.mean(top) - np.mean(bottom)))
        if len(spreads) < 3:
            return None
        return float(np.mean(spreads)), len(spreads)

    # --------------------------------------------------------------
    # 多市場週期穩健性 (Next Steps #3):跨多頭/空頭段量測排序力,避免過度配適
    # --------------------------------------------------------------
    # 預設市場週期分段 (依台股大盤 0050 走勢:2021 多頭、2022 空頭、2023-2025 多頭)
    CYCLE_SEGMENTS = [
        ("2021 多頭", "2021-01-01", "2021-12-31"),
        ("2022 空頭", "2022-01-01", "2022-12-31"),
        ("2023–2025 多頭", "2023-01-01", "2025-12-31"),
    ]

    def cycle_robustness(self, segments=None, rebalance="M", holding_days=20,
                         q=1 / 3, benchmark="0050"):
        """
        跨市場週期穩健性:對每個區間量測『市場中性排序力』(同日綜合分前 q − 後 q 的後續報酬差)。
        目的是確認選股排序 α 不是只在 2023–2025 多頭有效 —— 若 2022 空頭段仍為正,
        代表排序力穩健、非過度配適於單一多頭段。
        """
        segments = segments or self.CYCLE_SEGMENTS
        bench_bundle = None
        if benchmark:
            try:
                bench_bundle = load_benchmark(benchmark)
            except Exception as e:
                logger.warning(f"基準 {benchmark} 抓取失敗,略過大盤對照: {e}")

        print("\n" + "=" * 74)
        print("多市場週期穩健性 — 各週期『市場中性排序力』(前1/3 − 後1/3 後續報酬差)")
        print("=" * 74)
        rows = []
        for label, s, e in segments:
            cache = self._precompute(s, e, rebalance, holding_days)
            if not cache:
                rows.append([label, f"{s}~{e}", "資料不足", "n/a", "n/a", "—"])
                continue
            scored = self._scored_records(cache, self.advisor)
            qr = self._quantile_spread(scored, q=q)
            bk = self._score_cache_with(cache, self.advisor)
            bs = self._bucket_spread(bk, min_samples=5, signal_mode="strong_only")
            bench_pct = "n/a"
            if bench_bundle is not None:
                p0, p1 = self._price_on(bench_bundle, s), self._price_on(bench_bundle, e)
                if p0 and p1:
                    bench_pct = f"{(p1 / p0 - 1.0) * 100:+.1f}"
            neutral = f"{qr[0]:+.2f}% ({qr[1]}期)" if qr else "樣本不足"
            buy_spread = f"{bs[0]:+.2f}%" if bs else "n/a"
            verdict = "✅ 排序力保持" if (qr and qr[0] > 0) else \
                      ("⚠️ 樣本不足" if not qr else "❌ 排序力失效")
            rows.append([label, f"{s}~{e}", neutral, buy_spread, bench_pct, verdict])
        self._print_table(
            ["市場週期", "區間", "市場中性價差", "買進桶多空", "大盤%", "判定"], rows)
        print("\n說明:『市場中性價差』為同日高分前1/3 − 低分後1/3 的後續報酬差 (剃除大盤 beta),")
        print("     是純排序力指標。若空頭段 (2022) 仍為正,代表排序 α 穩健、非過度配適於多頭。")
        return rows

    # --------------------------------------------------------------
    # 分項因子歸因 (Next Steps #5):拆解五維度對市場中性價差的邊際貢獻
    # --------------------------------------------------------------
    def factor_attribution(self, start, end, rebalance="M", holding_days=20, q=1 / 3):
        """
        拆解五維度 (基本面/估值/技術/動能/籌碼) 各自對『市場中性排序力』的貢獻,
        用三個互補角度找出有效/無效因子:
          1) Rank IC:每期該維度分數 vs 後續報酬的 Spearman 秩相關均值 (最純的因子有效性)。
          2) 單因子多空:只用該維度排序的同日前q−後q 報酬差 (該因子獨立排序力)。
          3) 留一貢獻 (leave-one-out):綜合價差 − 抽掉該維度後的綜合價差 (現行權重下的邊際貢獻)。
        依此判斷哪些因子該砍、哪些該加重。
        """
        import numpy as np
        from collections import defaultdict

        cache = self._precompute(start, end, rebalance, holding_days)
        if not cache:
            print("無足夠資料。")
            return None
        dims = ["fundamental", "valuation", "technical", "momentum", "whale"]
        dim_label = {"fundamental": "基本面", "valuation": "估值面", "technical": "技術面",
                     "momentum": "動能面", "whale": "籌碼面"}

        obs = []   # (as_of, {dim: score}, fwd)
        for as_of, stock, fr, vr, tech, mom, whale, fwd in cache:
            vstatus = vr.get("valuation_status", "")
            val_bucket = 50.0 if "資料不足" in vstatus else float(vr.get("valuation_score", 0.0))
            b = {"fundamental": float(fr.get("total_score", 50.0)),
                 "valuation": val_bucket,
                 "technical": float(tech), "momentum": float(mom), "whale": float(whale)}
            obs.append((as_of, b, fwd))

        mw = dict(self.advisor.mode_weights)

        def _spread(scorefn):
            scored = [(as_of, scorefn(b), fwd, None) for as_of, b, fwd in obs]
            return self._quantile_spread(scored, q=q)

        def _comp(b, weights):
            wsum = sum(max(0.0, weights.get(k, 0.0)) for k in dims) or 1.0
            return sum(b[k] * float(weights.get(k, 0.0)) for k in dims) / wsum

        def _rank_ic(scorefn):
            by = defaultdict(list)
            for as_of, b, fwd in obs:
                by[as_of].append((scorefn(b), fwd))
            ics = []
            for _, items in by.items():
                if len(items) < 4:
                    continue
                xs = pd.Series([x for x, _ in items]).rank()
                ys = pd.Series([y for _, y in items]).rank()
                if xs.std() == 0 or ys.std() == 0:
                    continue
                ics.append(float(xs.corr(ys)))
            return (float(np.mean(ics)), len(ics)) if ics else None

        full = _spread(lambda b: _comp(b, mw))
        full_ic = _rank_ic(lambda b: _comp(b, mw))

        print("\n" + "=" * 78)
        print(f"分項因子歸因 — 五維度對市場中性排序力的貢獻  ({start} ~ {end}, 模式 {self.mode})")
        print("=" * 78)
        full_s = f"{full[0]:+.2f}% ({full[1]}期)" if full else "樣本不足"
        full_ic_s = f"{full_ic[0]:+.3f}" if full_ic else "n/a"
        print(f"綜合分基準:市場中性價差 {full_s}　｜　綜合 Rank IC {full_ic_s}")
        print("-" * 78)

        rows = []
        for d in dims:
            st = _spread(lambda b, dd=d: b[dd])
            ic = _rank_ic(lambda b, dd=d: b[dd])
            w2 = {k: v for k, v in mw.items() if k != d}
            lo = _spread(lambda b, w=w2: _comp(b, w))
            marginal = (full[0] - lo[0]) if (full and lo) else None
            st_s = f"{st[0]:+.2f}%" if st else "n/a"
            ic_s = f"{ic[0]:+.3f}" if ic else "n/a"
            mg_s = f"{marginal:+.2f}%" if marginal is not None else "n/a"
            # 判定:IC 與獨立多空同向為正 → 有效;皆負或近零 → 檢討/砍
            eff = "—"
            if ic and st:
                if ic[0] > 0.02 and st[0] > 0:
                    eff = "✅ 有效"
                elif ic[0] < -0.02 or st[0] < 0:
                    eff = "❌ 反向/無效"
                else:
                    eff = "➖ 中性偏弱"
            rows.append([dim_label[d], f"{mw.get(d, 0.0)*100:.0f}%", ic_s, st_s, mg_s, eff])
        self._print_table(
            ["維度", "現行權重", "Rank IC", "單因子多空", "留一邊際貢獻", "判定"], rows)
        print("\n判讀:")
        print("  · Rank IC > 0 且『單因子多空』為正 → 該維度確有排序力,可考慮加重。")
        print("  · Rank IC 為負或近零、且單因子多空 ≤ 0 → 該維度可能拖累,建議降權或檢討訊號品質。")
        print("  · 留一邊際貢獻 = 綜合價差 − 抽掉該維度後的價差;為負代表『拿掉它反而更好』。")
        return rows

    # --------------------------------------------------------------
    # 線一:市場中性權益曲線 (做多前1/3、做空後1/3,剃除大盤 beta)
    # --------------------------------------------------------------
    def market_neutral_curve(self, start, end, rebalance="M", q=1 / 3,
                             benchmark="0050", benchmark_bundle=None,
                             min_stocks=6, plot=True):
        """
        每個評級日按綜合分排序,做多前 q(等權)、做空後 q(等權),持有到下一評級日換股。
          多空組合報酬 = 前段平均報酬 − 後段平均報酬 (市場中性,大盤漲跌自動抵銷)
        另提供『純做多前段 vs 大盤』對照,並計算多空曲線與大盤的相關性 (應接近 0)。
        """
        import numpy as np
        dates = self._rebalance_dates(start, end, rebalance)
        if len(dates) < 3:
            print("評級日不足,無法建立曲線。")
            return pd.DataFrame()
        if benchmark_bundle is None and benchmark:
            try:
                benchmark_bundle = load_benchmark(benchmark)
            except Exception as e:
                logger.warning(f"基準 {benchmark} 抓取失敗,略過對比: {e}")

        ls_eq, long_eq, bench_eq = [1.0], [1.0], [1.0]
        ls_rets, bench_rets = [], []
        rows = []
        for d0, d1 in zip(dates, dates[1:]):
            scored = []
            for sym, b in self.bundles.items():
                rec = self._score_one(b, d0)
                if rec is None:
                    continue
                p1 = self._price_on(b, d1)
                if not rec.get("price") or not p1:
                    continue
                period_ret = p1 / rec["price"] - 1.0
                scored.append((rec["total_score"], period_ret))
            if len(scored) < min_stocks:
                ls_eq.append(ls_eq[-1]); long_eq.append(long_eq[-1]); 
                br = self._bench_ret(benchmark_bundle, d0, d1)
                bench_eq.append(bench_eq[-1] * (1 + br))
                continue
            scored.sort(key=lambda x: x[0])
            k = max(1, int(len(scored) * q))
            bottom = [r for _, r in scored[:k]]
            top = [r for _, r in scored[-k:]]
            long_ret = float(np.mean(top))
            short_ret = float(np.mean(bottom))
            ls_ret = long_ret - short_ret            # 市場中性:多前段、空後段
            br = self._bench_ret(benchmark_bundle, d0, d1)

            ls_eq.append(ls_eq[-1] * (1 + ls_ret))
            long_eq.append(long_eq[-1] * (1 + long_ret))
            bench_eq.append(bench_eq[-1] * (1 + br))
            ls_rets.append(ls_ret); bench_rets.append(br)
            rows.append({"date": d1, "多空報酬%": round(ls_ret * 100, 2),
                         "做多前段%": round(long_ret * 100, 2),
                         "做空後段%": round(-short_ret * 100, 2),
                         "大盤%": round(br * 100, 2)})

        curve = pd.DataFrame(rows)
        self._report_market_neutral(curve, dates, ls_eq, long_eq, bench_eq,
                                     ls_rets, bench_rets,
                                     benchmark_bundle is not None, benchmark, plot)
        return curve

    @classmethod
    def _bench_ret(cls, bundle, d0, d1):
        if bundle is None:
            return 0.0
        p0, p1 = cls._price_on(bundle, d0), cls._price_on(bundle, d1)
        return (p1 / p0 - 1.0) if (p0 and p1) else 0.0

    @classmethod
    def _report_market_neutral(cls, curve, dates, ls_eq, long_eq, bench_eq,
                               ls_rets, bench_rets, has_bench, benchmark, plot):
        import numpy as np
        if curve.empty:
            print("無有效期數。")
            return
        print("\n" + "=" * 66)
        print(f"市場中性策略曲線 (線一) — 做多前1/3、做空後1/3  ({dates[0]} ~ {dates[-1]})")
        print("=" * 66)
        m_ls = cls._metrics(ls_eq, dates[0], dates[-1])
        m_lo = cls._metrics(long_eq, dates[0], dates[-1])
        rows = [["多空對沖 (市場中性)", f"{m_ls['total']*100:+.1f}", f"{m_ls['cagr']*100:+.1f}", f"{m_ls['mdd']*100:.1f}"],
                ["純做多前1/3", f"{m_lo['total']*100:+.1f}", f"{m_lo['cagr']*100:+.1f}", f"{m_lo['mdd']*100:.1f}"]]
        if has_bench:
            m_b = cls._metrics(bench_eq, dates[0], dates[-1])
            rows.append([f"大盤 {benchmark}", f"{m_b['total']*100:+.1f}", f"{m_b['cagr']*100:+.1f}", f"{m_b['mdd']*100:.1f}"])
        cls._print_table(["組合", "總報酬%", "年化%", "最大回檔%"], rows)

        win = (curve["多空報酬%"] > 0).mean() * 100
        print(f"\n多空對沖期勝率:{win:.0f}%  ({int((curve['多空報酬%']>0).sum())}/{len(curve)} 期為正)")
        if has_bench and len(ls_rets) >= 3:
            corr = float(np.corrcoef(ls_rets, bench_rets)[0, 1])
            print(f"多空報酬 與 大盤報酬 的相關性:{corr:+.2f}  "
                  f"(接近 0 代表真市場中性,績效不靠大盤方向)")
        print("\n解讀:多空對沖曲線上升 = 你的『排序能力』本身在賺錢 (前段跑贏後段),")
        print("     與大盤漲跌無關;這就是這次樣本外驗證通過的 alpha 落地成的策略。")

        cls._ascii_curve(ls_eq, bench_eq if has_bench else None)
        if plot:
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                x = [pd.to_datetime(dates[0])] + [pd.to_datetime(d) for d in curve["date"]]
                plt.figure(figsize=(10, 5))
                plt.plot(x, ls_eq, label="Long-Short (Market Neutral)", linewidth=2)
                plt.plot(x, long_eq, label="Long Top 1/3", linewidth=1.5, linestyle=":")
                if has_bench:
                    plt.plot(x, bench_eq, label=f"Benchmark {benchmark}", linewidth=1.5, linestyle="--")
                plt.title("Market-Neutral Strategy Equity Curve")
                plt.ylabel("Equity (start=1)")
                plt.legend(); plt.grid(alpha=0.3)
                _png = output_path("charts", "market_neutral_curve.png")
                plt.savefig(_png, dpi=120, bbox_inches="tight")
                print(f"\n📈 市場中性曲線圖已存:{_png}")
            except ImportError:
                print("\n(未安裝 matplotlib,略過 PNG)")

    def optimize(self, start, end, rebalance="M", holding_days=20,
                 min_scores=(60, 65, 70), chip_mins=(20, 30, 40),
                 weight_profiles=None, min_samples=8, top_n=10, train_ratio=0.6,
                 signal_mode="buy_grade"):
        """
        網格搜尋 + 自動 train/test 切分驗證。
          signal_mode='buy_grade'(預設,路線一) → 買進桶=強推+觀望;'strong_only' → 只買強推。
          1) 樣本按日期切前段 train / 後段 test;2) 只在 train 排名;3) 自動套到 test 對照。
        """
        weight_profiles = weight_profiles or self.WEIGHT_PROFILES
        print(f"預先計算 point-in-time 特徵 (只算一次)... [買進訊號:{signal_mode}]")
        cache = self._precompute(start, end, rebalance, holding_days)
        if not cache:
            print("無足夠資料。")
            return pd.DataFrame()

        # 依日期切 train / test (前段最佳化、後段驗證)
        dates_sorted = sorted({c[0] for c in cache})
        if len(dates_sorted) < 4:
            print("評級日太少,無法切 train/test。請拉長期間或加密頻率。")
            return pd.DataFrame()
        split_idx = max(1, int(len(dates_sorted) * train_ratio))
        split_date = dates_sorted[split_idx]
        train = [c for c in cache if c[0] < split_date]
        test = [c for c in cache if c[0] >= split_date]
        print(f"樣本 {len(cache)} 筆 → train {len(train)} 筆 (~{split_date} 前) / test {len(test)} 筆 (之後)")
        print(f"開始網格搜尋 {len(weight_profiles)}×{len(min_scores)}×{len(chip_mins)} = "
              f"{len(weight_profiles)*len(min_scores)*len(chip_mins)} 組...")

        rows = []
        for wp_name, cw in weight_profiles.items():
            for ms in min_scores:
                for cm in chip_mins:
                    adv = InvestmentAdvisor(min_score=ms, mode_weights=cw, mode_name=self.mode)
                    adv.chip_min = cm
                    tr = self._bucket_spread(self._score_cache_with(train, adv), min_samples, signal_mode)
                    if tr is None:
                        continue
                    te = self._bucket_spread(self._score_cache_with(test, adv),
                                             max(3, min_samples // 2), signal_mode)
                    rows.append({
                        "權重方案": wp_name, "min_score": ms, "chip_min": cm,
                        "train價差%": round(tr[0], 2),
                        "test價差%": (round(te[0], 2) if te else None),
                        "train強推": tr[3], "test強推": (te[3] if te else 0),
                    })
        if not rows:
            print("所有組合樣本都不足,請放寬 min_samples 或加更多股票/拉長期間。")
            return pd.DataFrame()

        res = pd.DataFrame(rows).sort_values("train價差%", ascending=False).reset_index(drop=True)
        print("\n" + "=" * 74)
        print(f"參數網格搜尋 — 依『train 多空價差』排名,並對照 test 驗證 (前 {top_n} 名)")
        print("=" * 74)
        disp = []
        for _, r in res.head(top_n).iterrows():
            te = r["test價差%"]
            hold = "✅撐住" if (te is not None and te > 0) else ("❌崩壞" if te is not None else "—樣本不足")
            disp.append([r["權重方案"], str(r["min_score"]), str(r["chip_min"]),
                         f'{r["train價差%"]:+.2f}',
                         (f'{te:+.2f}' if te is not None else "n/a"), hold])
        self._print_table(["權重方案", "門檻", "籌碼門檻", "train價差%", "test價差%", "樣本外驗證"], disp)

        # 結論:train 最佳者在 test 是否撐住
        best = res.iloc[0]
        te = best["test價差%"]
        tr_best = best["train價差%"]
        print(f"\ntrain 最佳:{best['權重方案']} + min_score={best['min_score']} + "
              f"chip_min={best['chip_min']} → train {tr_best:+.2f}%", end="")
        if tr_best <= 0:
            print(f" (train 本身即非正 → 此股票池尚無有效鑑別力,調參數無意義)。")
        elif te is None:
            print(f",但 test 樣本不足無法驗證 (謹慎看待)。")
        elif te > 0:
            print(f",test {te:+.2f}% → 樣本外仍為正,較可信 ✅")
        else:
            print(f",但 test {te:+.2f}% → 樣本外轉負,判定過度配適,不建議採用 ❌")

        # 更穩健的推薦:train 與 test 都為正、且 test 價差最大者
        robust = res[(res["train價差%"] > 0) & (res["test價差%"].fillna(-99) > 0)]
        if not robust.empty:
            rb = robust.sort_values("test價差%", ascending=False).iloc[0]
            print(f"\n👉 較穩健的推薦 (train/test 皆正、test 最大):{rb['權重方案']} + "
                  f"min_score={rb['min_score']} + chip_min={rb['chip_min']} "
                  f"(train {rb['train價差%']:+.2f}% / test {rb['test價差%']:+.2f}%)")
            print("   把這組填進 scoring_manager 的 MODES,即為經樣本外驗證的參數。")
        else:
            print("\n⚠️ 沒有任何組合能在 train 與 test 同時為正 → 目前策略在此股票池尚無穩定鑑別力,")
            print("   建議先擴大/更換股票池,或回頭檢視各維度訊號,而非硬調參數。")
        return res

    # --------------------------------------------------------------
    # 7) 評級變動追蹤:某檔評級改變 (尤其升級到強推) 時記錄,累積樣本
    # --------------------------------------------------------------
    @classmethod
    def track_rating_changes(cls, records: pd.DataFrame):
        """偵測每檔『評級變動』(如 觀望→強推),並統計變動後的後續報酬。"""
        if records is None or records.empty or "as_of" not in records.columns:
            print("無記錄可追蹤。")
            return pd.DataFrame()
        rank = RATING_RANK   # {謹慎避開:0, 觀望追蹤:1, 強烈推薦:2, 強勢買進:3}
        changes = []
        for sym, grp in records.sort_values("as_of").groupby("symbol"):
            prev = None
            nm = grp["name"].iloc[0] if "name" in grp.columns else sym
            for _, r in grp.iterrows():
                cur = r["rating"]
                if prev is not None and cur != prev:
                    direction = "升級" if rank.get(cur, 1) > rank.get(prev, 1) else "降級"
                    changes.append({"symbol": sym, "name": nm, "as_of": r["as_of"],
                                    "from": prev, "to": cur, "方向": direction,
                                    "forward_return": r.get("forward_return", float("nan"))})
                prev = cur
        if not changes:
            print("回測期間無評級變動 (可能因評級穩定或樣本太少)。")
            return pd.DataFrame()
        ch = pd.DataFrame(changes)

        print("\n" + "=" * 64)
        print("評級變動追蹤 — 變動後的後續報酬")
        print("=" * 64)
        import numpy as np
        rows = []
        for (frm, to), g in ch.groupby(["from", "to"]):
            rows.append([f"{frm}→{to}", str(len(g)),
                         f'{g["forward_return"].mean():+.2f}',
                         f'{(g["forward_return"] > 0).mean()*100:.0f}'])
        rows.sort(key=lambda x: x[0])
        cls._print_table(["評級變動", "次數", "變動後平均報酬%", "勝率%"], rows)

        # 特別看「升級到買進級 (強勢買進 / 強烈推薦)」的成效 (最有價值的訊號)
        up_buy = ch[ch["to"].isin([R_SUPER, R_STRONG])]
        if not up_buy.empty:
            print(f"\n升級到買進級 (強勢買進/強烈推薦) 共 {len(up_buy)} 次,"
                  f"後續平均報酬 {up_buy['forward_return'].mean():+.2f}%、"
                  f"勝率 {(up_buy['forward_return']>0).mean()*100:.0f}%")
            up_super = ch[ch["to"] == R_SUPER]
            if not up_super.empty:
                print(f"  其中升級到『強勢買進』{len(up_super)} 次,"
                      f"後續平均報酬 {up_super['forward_return'].mean():+.2f}%、"
                      f"勝率 {(up_super['forward_return']>0).mean()*100:.0f}%")
            print("最近幾次升級到買進級:")
            recent = up_buy.sort_values("as_of").tail(8)
            r2 = [[r["as_of"], f'{r["symbol"]} {r["name"]}', f'{r["from"]}→{r["to"]}',
                   f'{r["forward_return"]:+.2f}'] for _, r in recent.iterrows()]
            cls._print_table(["日期", "股票", "變動", "後續報酬%"], r2)
        return ch

    # --------------------------------------------------------------
    # 8) 市場中性權益曲線:每期買前⅓、放空後⅓,賺排序價差 (剃除大盤 beta)
    # --------------------------------------------------------------
    def _scores_on(self, as_of):
        """回傳該日 [(symbol, total_score), ...] (可評分者)。"""
        out = []
        for sym, b in self.bundles.items():
            rec = self._score_one(b, as_of)
            if rec is not None:
                out.append((sym, rec["total_score"]))
        return out

    @staticmethod
    def _bench_ret(bundle, d0, d1):
        if bundle is None:
            return 0.0
        p0 = Backtester._price_on(bundle, d0)
        p1 = Backtester._price_on(bundle, d1)
        return (p1 / p0 - 1.0) if (p0 and p1) else 0.0

    def market_neutral_curve(self, start, end, rebalance="M", q=1 / 3,
                             benchmark="0050", benchmark_bundle=None,
                             min_stocks=6, plot=True):
        """
        線一:把已驗證的『排序能力』做成可執行策略的權益曲線。
          每個評級日按綜合分排序 → 買前 q(等權)、放空後 q(等權)。
          市場中性報酬 = 前⅓報酬 − 後⅓報酬 (大盤漲跌對兩邊一致 → 自動抵銷)。
          另算『純做多前⅓ vs 大盤』對照,並回報與大盤的相關性 (中性應接近 0)。
        """
        dates = self._rebalance_dates(start, end, rebalance)
        if len(dates) < 2:
            print("評級日不足,無法建立曲線。")
            return pd.DataFrame()
        if benchmark_bundle is None and benchmark:
            try:
                benchmark_bundle = load_benchmark(benchmark)
            except Exception as e:
                logger.warning(f"基準 {benchmark} 抓取失敗,略過對比: {e}")

        ls_eq, long_eq, bench_eq = [1.0], [1.0], [1.0]
        ls_rets, bench_rets, rows = [], [], []
        for d0, d1 in zip(dates, dates[1:]):
            scores = self._scores_on(d0)
            br = self._bench_ret(benchmark_bundle, d0, d1)

            def period_ret(sym):
                p0 = self._price_on(self.bundles[sym], d0)
                p1 = self._price_on(self.bundles[sym], d1)
                return (p1 / p0 - 1.0) if (p0 and p1) else None

            if len(scores) >= min_stocks:
                scores.sort(key=lambda x: x[1])            # 依綜合分升冪
                k = max(1, int(len(scores) * q))
                bottom, top = scores[:k], scores[-k:]
                top_r = [r for r in (period_ret(s) for s, _ in top) if r is not None]
                bot_r = [r for r in (period_ret(s) for s, _ in bottom) if r is not None]
            else:
                top_r = bot_r = []

            if top_r and bot_r:
                long_ret, short_ret = float(np.mean(top_r)), float(np.mean(bot_r))
                ls_ret = long_ret - short_ret
                ls_eq.append(ls_eq[-1] * (1 + ls_ret))
                long_eq.append(long_eq[-1] * (1 + long_ret))
                bench_eq.append(bench_eq[-1] * (1 + br))
                ls_rets.append(ls_ret)
                bench_rets.append(br)
                rows.append({"date": d1, "前⅓檔數": len(top_r), "後⅓檔數": len(bot_r),
                             "多空報酬%": round(ls_ret * 100, 2),
                             "純做多前⅓%": round(long_ret * 100, 2),
                             "大盤%": round(br * 100, 2)})
            else:
                ls_eq.append(ls_eq[-1])
                long_eq.append(long_eq[-1])
                bench_eq.append(bench_eq[-1] * (1 + br))

        curve = pd.DataFrame(rows)
        self._report_market_neutral(curve, dates, ls_eq, long_eq, bench_eq,
                                    ls_rets, bench_rets,
                                    benchmark_bundle is not None, benchmark, q, plot)
        return curve

    @classmethod
    def _report_market_neutral(cls, curve, dates, ls_eq, long_eq, bench_eq,
                               ls_rets, bench_rets, has_bench, benchmark, q, plot):
        if curve.empty:
            print("無足夠資料建立市場中性曲線 (可能每期可評分股票數 < min_stocks)。")
            return
        pct = int(round(q * 100))
        m_ls = cls._metrics(ls_eq, dates[0], dates[-1])
        m_lo = cls._metrics(long_eq, dates[0], dates[-1])
        print("\n" + "=" * 68)
        print(f"市場中性權益曲線 (線一) — 每期買前{pct}%、放空後{pct}%  ({dates[0]} ~ {dates[-1]})")
        print("=" * 68)
        rows = [["多空對沖 (前⅓−後⅓)", f"{m_ls['total']*100:+.1f}", f"{m_ls['cagr']*100:+.1f}", f"{m_ls['mdd']*100:.1f}"],
                ["純做多前⅓",           f"{m_lo['total']*100:+.1f}", f"{m_lo['cagr']*100:+.1f}", f"{m_lo['mdd']*100:.1f}"]]
        if has_bench:
            m_b = cls._metrics(bench_eq, dates[0], dates[-1])
            rows.append([f"大盤 {benchmark}", f"{m_b['total']*100:+.1f}", f"{m_b['cagr']*100:+.1f}", f"{m_b['mdd']*100:.1f}"])
        cls._print_table(["策略", "總報酬%", "年化%", "最大回檔%"], rows)

        win = (curve["多空報酬%"] > 0).mean() * 100
        print(f"\n多空對沖期勝率:{win:.0f}%  ({int((curve['多空報酬%']>0).sum())}/{len(curve)} 期為正)")
        if has_bench and len(ls_rets) >= 3:
            corr = float(np.corrcoef(ls_rets, bench_rets)[0, 1])
            print(f"多空對沖 vs 大盤 相關性:{corr:+.2f}  "
                  f"({'接近 0,確實市場中性 ✅' if abs(corr) < 0.3 else '偏高,仍受大盤影響'})")
        print("解讀:多空對沖曲線越穩定向上、與大盤相關性越低,代表排序能力越純粹、越不靠大盤。")

        cls._ascii_curve(ls_eq, bench_eq if has_bench else None)
        if plot:
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                x = [pd.to_datetime(dates[0])] + [pd.to_datetime(d) for d in curve["date"]]
                # ls_eq / long_eq 長度 = 期數+1;對齊 x
                xx = x[:len(ls_eq)]
                plt.figure(figsize=(10, 5))
                plt.plot(xx, ls_eq[:len(xx)], label="Market-Neutral (Long-Short)", linewidth=2)
                plt.plot(xx, long_eq[:len(xx)], label="Long Top-Tercile", linewidth=1.5, linestyle=":")
                if has_bench:
                    plt.plot(xx, bench_eq[:len(xx)], label=f"Benchmark {benchmark}", linewidth=1.5, linestyle="--")
                plt.title("Market-Neutral Equity Curve")
                plt.ylabel("Equity (start=1)")
                plt.legend(); plt.grid(alpha=0.3)
                _png = output_path("charts", "market_neutral_curve.png")
                plt.savefig(_png, dpi=120, bbox_inches="tight")
                print(f"\n📈 市場中性曲線圖已存:{_png}")
            except ImportError:
                print("\n(未安裝 matplotlib,略過 PNG;ASCII 走勢仍可參考)")

    # --------------------------------------------------------------
    # 離線自我測試 (合成資料,驗證流程與 point-in-time 邏輯)
    # --------------------------------------------------------------
    @staticmethod
    def self_test():
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2021-01-01", "2024-12-31")
        n = len(dates)
        # 造一檔「趨勢向上」的合成股:價格隨機漫步帶正漂移
        price = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.02, n)))
        vol = rng.integers(2000, 8000, n)
        price_df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": price, "max": price * 1.01, "min": price * 0.99,
            "close": price, "Trading_Volume": vol * 1000,
        })
        per_df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "PER": rng.uniform(12, 28, n), "PBR": rng.uniform(2, 5, n),
            "dividend_yield": rng.uniform(1, 4, n),
        })
        b = HistoryBundle(symbol="TEST", name="合成股", price=price_df, per=per_df)
        bt = Backtester(symbols=["TEST"])
        bt.bundles = {"TEST": b}
        recs = bt.run("2022-01-01", "2024-06-30", rebalance="M", holding_days=20)
        print(f"合成回測產生 {len(recs)} 筆記錄 (應 > 0 且無未來函數錯誤)")
        if not recs.empty:
            bt.summarize(recs)
        return recs