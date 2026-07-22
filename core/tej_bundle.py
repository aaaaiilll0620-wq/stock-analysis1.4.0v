"""
TEJ → HistoryBundle 轉接器 (五維綜合分改用純 TEJ 資料源)
================================================================================
定位:讓 core.score_store.build_scores 走的 PIT 評分管線
      (cached_fetch_history → build_pit_stockdata → ScoringManager → advisor)
      改吃本機 TEJ 快取,而非 FinMind 8 資料集。**評分數學完全不動** ——
      本模組只把 TEJ Parquet reshape 成 FinMind 同構的 HistoryBundle 欄位,
      build_pit_stockdata 的 as_of PIT 切片與計分邏輯原封不動直接吃。

資料源對映 (~/tej_cache/<dataset>/<stock_id>.parquet):
  bundle.price        ← price_valuation   (open/max/min/close/Trading_Volume)   + _back_adjust
  bundle.per          ← price_valuation   (PER_TSE→PER / PBR_TSE→PBR / dividend_yield_TSE→dividend_yield)
  bundle.revenue      ← monthly_revenue   (經 backtest._pit_revenue:真實公告日 PIT 對齊)
  bundle.income       ← financial_statements  (wide→long:Revenue/GrossProfit/OperatingIncome/IncomeAfterTaxes/EPS)
  bundle.balance      ← financial_statements  (wide→long:TotalAssets/Liabilities/CurrentAssets/CurrentLiabilities/Equity)
  bundle.cashflow     ← financial_statements  (wide→long:營業現金流/資本支出)
  bundle.chip         ← institutional_gross   (wide→long:date/name/buy/sell,單位:股)
  bundle.shareholding ← tdcc_weekly (發行股數) ∪ institutional_gross (外資持股%)

口徑對齊要點:
  · 財報 date:TEJ 標季末月 1 號 (Q1=YYYY-03-01) → 轉季末日 (YYYY-03-31),
    與 FinMind 路徑及 build_pit._published (季末+45天才算已公告) 口徑一致。
  · 財報長格式:type 用英文科目名 (與 build_pit 的 _latest_value/_value_series 首選鍵一致),
    origin_name 留空 (中文比對是次選,英文對得上就不需要)。
  · 發行股數:tdcc_weekly.total_lots_thousand 實為「千股」(2330≈25,932,370 → ×1000=2.59e10 股)。
  · 缺任一資料集 → 該欄回 None;build_pit 對缺欄有中性預設 (該維退化為中性,不會炸)。

已知降級 (相對 FinMind 路徑,皆為「少加分」而非「錯加分」,安全):
  · RS 疊加 (rs_3m/6m) 仍讀 data_cache 的 0050 (FinMind 快取);若無則留 None 不計分。
  · EPS 為單季 (TEJ),YoY 成長率的量綱與 FinMind 若不同,只影響成長率絕對值、方向一致。
================================================================================
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Tuple

import pandas as pd

from core.backtest import HistoryBundle, _back_adjust, _pit_revenue

logger = logging.getLogger(__name__)

TEJ_CACHE_DIR = os.environ.get("TEJ_CACHE", os.path.join(os.path.expanduser("~"), "tej_cache"))


def _read(dataset: str, symbol: str, columns=None) -> Optional[pd.DataFrame]:
    """讀 tej_cache/<dataset>/<symbol>.parquet;無檔/壞檔/空表 → None (由上層降級)。"""
    p = os.path.join(TEJ_CACHE_DIR, dataset, f"{symbol}.parquet")
    if not os.path.exists(p):
        return None
    try:
        df = pd.read_parquet(p, columns=columns) if columns else pd.read_parquet(p)
    except Exception:                                   # 舊檔缺欄 → 全欄再讀一次
        try:
            df = pd.read_parquet(p)
        except Exception as e:
            logger.warning(f"[{symbol}] TEJ {dataset} 讀取失敗: {e}")
            return None
    return df if (df is not None and not df.empty) else None


# ------------------------------------------------------------------ price / per
def _price_valuation(symbol: str) -> Optional[pd.DataFrame]:
    """日K+估值全歷史 = TEJ 種子 ∪ 收集器每日快照 (as_of 追到最新交易日)。
    優先複用 DataProvider._read_local_price_valuation (已實測的種子∪快照合併,重疊以 TEJ 為準);
    其新鮮度閘門觸發或離線 → 退回純 TEJ 種子 (as_of 止於種子最後日,仍可評分)。"""
    d = None
    try:
        from core.data_provider import DataProvider
        d = DataProvider._read_local_price_valuation(symbol)     # 種子∪快照,含 PER_TSE 等
    except Exception:
        d = None
    if d is None:
        d = _read("price_valuation", symbol)                     # 純種子退路
    return d


def _tej_price(symbol: str) -> Optional[pd.DataFrame]:
    """日線 (FinMind 同構:date/open/max/min/close/Trading_Volume) + 跳空回補。"""
    d = _price_valuation(symbol)
    if d is None:
        return None
    keep = [c for c in ("date", "open", "max", "min", "close", "Trading_Volume") if c in d.columns]
    d = d[keep].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return _back_adjust(d)


# 估值百分位窗起點:與 core.data_cache.HISTORY_START / universe_screen 的 PE_HISTORY_START 一致。
# TEJ 種子可回溯到 2004,但 PE/PB 分位的計分校準是在 2019+ 窗上驗證的;不鎖窗會讓
# 同一檔的估值分數因歷史深度而異 (口徑漂移),故裁到 2019 起,三條路徑 (FinMind/粗篩/TEJ) 對齊。
_PCT_HISTORY_START = "2019-01-01"


def _tej_per(symbol: str) -> Optional[pd.DataFrame]:
    """估值歷史 (PER/PBR/dividend_yield;官方 TSE 口徑,與粗篩 PER_TSE 一致)。
    百分位窗鎖 2019 起,與 FinMind 路徑及 universe_screen 同口徑。"""
    d = _price_valuation(symbol)
    if d is None or "PER_TSE" not in d.columns:
        return None
    keep = [c for c in ("date", "PER_TSE", "PBR_TSE", "dividend_yield_TSE") if c in d.columns]
    d = d[keep].rename(columns={"PER_TSE": "PER", "PBR_TSE": "PBR",
                                "dividend_yield_TSE": "dividend_yield"})
    d = d.dropna(subset=["date"]).sort_values("date")
    d = d[d["date"].astype(str) >= _PCT_HISTORY_START]
    return d.reset_index(drop=True) if not d.empty else None


# ------------------------------------------------------------------ 三大財報 (wide → long)
# TEJ financial_statements 寬欄 → build_pit 需要的 FinMind 長格式 type 名。
_INCOME_MAP = {                     # 損益表科目
    "revenue": "Revenue",
    "gross_profit": "GrossProfit",
    "operating_income": "OperatingIncome",
    "net_income": "IncomeAfterTaxes",
    "eps": "EPS",
}
_BALANCE_MAP = {                    # 資產負債表科目
    "total_assets": "TotalAssets",
    "total_liabilities": "Liabilities",
    "current_assets": "CurrentAssets",
    "current_liabilities": "CurrentLiabilities",
    "equity": "Equity",
}
_CASHFLOW_MAP = {                   # 現金流量表科目
    "operating_cash_flow": "CashFlowsProvidedFromUsedInOperatingActivities",
    "capex": "AcquisitionOfPropertyPlantAndEquipment",
}


def _to_long(df: pd.DataFrame, colmap: dict) -> Optional[pd.DataFrame]:
    """把寬表選定欄位 melt 成 FinMind 長格式 (date/type/value/origin_name)。
    date 由 TEJ 季末月 1 號 → 季末日 (與 FinMind 及 build_pit._published 口徑一致)。"""
    have = {src: dst for src, dst in colmap.items() if src in df.columns}
    if not have:
        return None
    qend = (pd.to_datetime(df["date"], errors="coerce") + pd.offsets.MonthEnd(0)) \
        .dt.strftime("%Y-%m-%d")
    parts = []
    for src, dst in have.items():
        v = pd.to_numeric(df[src], errors="coerce")
        parts.append(pd.DataFrame({"date": qend, "type": dst, "value": v, "origin_name": ""}))
    out = pd.concat(parts, ignore_index=True).dropna(subset=["date", "value"])
    return out.sort_values("date").reset_index(drop=True) if not out.empty else None


def _tej_financials(symbol: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """一次讀 financial_statements,拆成 (income, balance, cashflow) 三張長表。"""
    d = _read("financial_statements", symbol)
    if d is None or "date" not in d.columns:
        return None, None, None
    return _to_long(d, _INCOME_MAP), _to_long(d, _BALANCE_MAP), _to_long(d, _CASHFLOW_MAP)


# ------------------------------------------------------------------ 籌碼 (wide → long)
def _tej_chip(symbol: str) -> Optional[pd.DataFrame]:
    """法人買賣毛額 → FinMind TaiwanStockInstitutionalInvestorsBuySell 同構長格式
    (date/name/buy/sell,單位:股)。build_pit 以 name 分外資/投信,自動找 buy/sell 欄。
    優先複用 DataProvider._read_local_chip (institutional_gross 種子 ∪ 收集器毛額快照,追到最新日);
    其覆蓋/新鮮度閘門觸發 → 退回純 institutional_gross 種子 reshape。"""
    try:
        from core.data_provider import DataProvider
        d = DataProvider._read_local_chip(symbol, "2019-01-01")   # 已是 date/name/buy/sell 長格式
        if d is not None and not d.empty:
            return d
    except Exception:
        pass
    d = _read("institutional_gross", symbol,
              ["date", "foreign_buy", "foreign_sell", "trust_buy", "trust_sell"])
    if d is None:
        return None
    d = d.dropna(subset=["date"]).sort_values("date")
    f = d[["date", "foreign_buy", "foreign_sell"]].rename(
        columns={"foreign_buy": "buy", "foreign_sell": "sell"})
    f["name"] = "Foreign_Investor"
    t = d[["date", "trust_buy", "trust_sell"]].rename(
        columns={"trust_buy": "buy", "trust_sell": "sell"})
    t["name"] = "Investment_Trust"
    out = pd.concat([f, t], ignore_index=True).dropna(subset=["buy", "sell"])
    return out.sort_values("date").reset_index(drop=True) if not out.empty else None


# ------------------------------------------------------------------ 股權 (發行股數 / 外資持股%)
def _tej_shareholding(symbol: str) -> Optional[pd.DataFrame]:
    """FinMind TaiwanStockShareholding 同構:date + NumberOfSharesIssued + ForeignInvestmentSharesRatio。
    發行股數取自 tdcc_weekly.total_lots_thousand (千股 → 股);外資持股% 取自 institutional_gross。
    build_pit 對此欄做 _slice 後取 .iloc[-1],故給「歷史時序」即可 (PIT 安全)。"""
    tdcc = _read("tdcc_weekly", symbol, ["date", "total_lots_thousand"])
    shares = None
    if tdcc is not None and "total_lots_thousand" in tdcc.columns:
        s = tdcc.dropna(subset=["date"]).sort_values("date").copy()
        s["NumberOfSharesIssued"] = pd.to_numeric(s["total_lots_thousand"], errors="coerce") * 1000.0
        shares = s[["date", "NumberOfSharesIssued"]].dropna(subset=["NumberOfSharesIssued"])
        if shares.empty:
            shares = None

    fr = _read("institutional_gross", symbol, ["date", "foreign_holding_pct"])
    fratio = None
    if fr is not None and "foreign_holding_pct" in fr.columns:
        f = fr.dropna(subset=["date"]).sort_values("date").copy()
        f["ForeignInvestmentSharesRatio"] = pd.to_numeric(f["foreign_holding_pct"], errors="coerce")
        fratio = f[["date", "ForeignInvestmentSharesRatio"]].dropna(subset=["ForeignInvestmentSharesRatio"])
        if fratio.empty:
            fratio = None

    if shares is None and fratio is None:
        return None
    if shares is None:
        return fratio.reset_index(drop=True)
    if fratio is None:
        return shares.reset_index(drop=True)
    # 兩者以日期 outer merge → 同一列可含股數與外資% (build_pit 只取切片後最後一列的欄值)
    out = pd.merge(shares, fratio, on="date", how="outer").sort_values("date")
    out["NumberOfSharesIssued"] = out["NumberOfSharesIssued"].ffill()
    out["ForeignInvestmentSharesRatio"] = out["ForeignInvestmentSharesRatio"].ffill()
    return out.reset_index(drop=True)


# ------------------------------------------------------------------ 對外:組 bundle
def tej_fetch_history(symbol: str, name: Optional[str] = None) -> HistoryBundle:
    """
    以本機 TEJ 快取組出 FinMind 同構的 HistoryBundle (0 FinMind API)。
    介面與 core.backtest.cached_fetch_history 相容,可直接注入 build_pit_stockdata。
    任一資料集缺失 → 該欄 None (該維在評分時退化為中性,不中止)。
    """
    return HistoryBundle(
        symbol=str(symbol),
        name=name,
        price=_tej_price(symbol),
        per=_tej_per(symbol),
        revenue=_pit_revenue(symbol, None),
        **dict(zip(("income", "balance", "cashflow"), _tej_financials(symbol))),
        chip=_tej_chip(symbol),
        shareholding=_tej_shareholding(symbol),
    )
