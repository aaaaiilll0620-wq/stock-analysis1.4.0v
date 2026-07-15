"""全市場產業內估值位階查詢 (v4.5,0 FinMind API)
================================================================================
資料:market_cache/industry_value_ref.parquet,由 scripts/build_industry_value_ref.py
      從「TEJ 歷史種子 ∪ TWSE/TPEx 每日快照」預算 (全市場 1,952 檔、2019-04 起)。
定義:value_ind_pct = 個股「自身歷史 PE expanding 分位」在全市場同 TEJ 產業內的
      橫斷面百分位 (0-100,越高 = 相對同業越便宜;產業分組 <5 檔退回全市場排名)。
      構造與驗證見 DevLog §15-G (TEJ 全市場三期驗證勝出組態)。
用法:
  industry_value_pct("2330")               # live:最新一列 (過舊 > MAX_STALE_DAYS 回 None)
  industry_value_pct("2330", "2024-03-29") # 回測 PIT:as_of 當日或之前最近一列
查無值回 None → ValuationEngine 自動退回現行 PEG+位階配方,不硬中性化。
================================================================================
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REF_PATH = (Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
            / "industry_value_ref.parquet")
MAX_STALE_DAYS = 10   # 對齊日與最近資料列差超過此天數 → 視為無資料 (防用到過期位階)

_BY_SYMBOL: Optional[dict] = None


def _load() -> dict:
    global _BY_SYMBOL
    if _BY_SYMBOL is None:
        if REF_PATH.exists():
            df = pd.read_parquet(REF_PATH, columns=["stock_id", "date", "value_ind_pct"])
            _BY_SYMBOL = {sid: (g["date"].to_numpy(), g["value_ind_pct"].to_numpy())
                          for sid, g in df.groupby("stock_id", sort=False)}
        else:
            _BY_SYMBOL = {}
    return _BY_SYMBOL


def industry_value_pct(symbol: str, as_of: Optional[str] = None) -> Optional[float]:
    """回傳 (symbol, as_of) 的產業內估值位階;as_of=None 表 live (今天)。查無/過舊回 None。"""
    entry = _load().get(str(symbol))
    if not entry:
        return None
    dates, vals = entry
    anchor = as_of or datetime.now().strftime("%Y-%m-%d")
    i = int(np.searchsorted(dates, anchor, side="right")) - 1   # 當日或之前最近一列 (PIT)
    if i < 0:
        return None
    if (pd.Timestamp(anchor) - pd.Timestamp(dates[i])).days > MAX_STALE_DAYS:
        return None
    v = vals[i]
    return None if pd.isna(v) else float(v)
