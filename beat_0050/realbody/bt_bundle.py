# -*- coding: utf-8 -*-
"""bt_bundle.py — B全循環複驗專用的 HistoryBundle 包裝 (不動 live tej_bundle)。
================================================================================
在 core.tej_bundle.tej_fetch_history 之上做兩個**回測專用**覆寫,只在本行程生效,
不改任何檔案、不影響 live App:

  修1 估值窗:core.tej_bundle._PCT_HISTORY_START 2019→2004
       (live 鎖 2019 是為對齊即時口徑;全循環回測要讓 2005-2018 估值面有真實百分位)。
  修2 籌碼源:bundle.chip 改讀 institutional_flow(淨額,2004+),取代覆蓋不足的 institutional_gross。
       淨額→FinMind同構 date/name/buy/sell:buy=max(net,0)、sell=max(-net,0)(單位:股)。
       淨額比/連買天數正確;participation(buy+sell)以|net|近似會略低估(僅±小bonus)。

用法:from beat_0050.realbody.bt_bundle import bt_fetch_history
      bundle = bt_fetch_history("2330")   # 介面同 tej_fetch_history,可直接餵 score_row
================================================================================
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
import pandas as pd

import core.tej_bundle as _tb
from core.backtest import HistoryBundle

# --- 修1:放寬估值百分位窗到 2004 (process-local,live 檔案不動) ---
_tb._PCT_HISTORY_START = "2004-01-01"

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))


# --- 修2:institutional_flow(淨額)→ FinMind 同構 chip 長格式 (date/name/buy/sell,股) ---
def _flow_chip(symbol: str):
    p = TEJ_CACHE / "institutional_flow" / f"{symbol}.parquet"
    if not p.exists():
        return None
    try:
        d = pd.read_parquet(p, columns=["date", "foreign_net", "trust_net"])
    except Exception:
        return None
    if d is None or d.empty:
        return None
    d = d.dropna(subset=["date"]).sort_values("date")
    parts = []
    for col, name in [("foreign_net", "Foreign_Investor"), ("trust_net", "Investment_Trust")]:
        if col not in d.columns:
            continue
        net = pd.to_numeric(d[col], errors="coerce")
        parts.append(pd.DataFrame({
            "date": d["date"].values,
            "name": name,
            "buy": np.clip(net.values, 0, None),      # 淨買 → 掛 buy
            "sell": np.clip(-net.values, 0, None),    # 淨賣 → 掛 sell
        }))
    if not parts:
        return None
    out = pd.concat(parts, ignore_index=True).dropna(subset=["buy", "sell"])
    return out.sort_values("date").reset_index(drop=True) if not out.empty else None


def bt_fetch_history(symbol: str, name=None) -> HistoryBundle:
    """回測版 bundle:估值窗放寬(修1,已於 import 時生效)+ 籌碼改 flow(修2)。"""
    b = _tb.tej_fetch_history(symbol, name)
    ch = _flow_chip(str(symbol))
    if ch is not None:
        b.chip = ch
    return b
