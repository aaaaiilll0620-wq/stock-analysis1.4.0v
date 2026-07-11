# -*- coding: utf-8 -*-
"""
市場 Regime 偵測 (PIT-clean) — 用大盤基準 (預設 0050) 判斷 多頭 / 中性 / 空頭
================================================================================
動機:--cycle 顯示排序力在 2021、2023–25 多頭很強,但 2022 空頭失效
     (市場中性 −0.84%、買進桶多空 −2.79%)。根因是『動能因子在空頭反轉盤會被打臉』——
     這是動能的本質,靜態權重無法兩全。解法:讓 composite 權重隨大盤 regime 調整:
       · 空頭 → 砍動能/技術、加重基本面 (抗跌、IC 穩)
       · 多頭 → 趨勢因子維持或略增
     這也把 v3「沒訊號自動空手」的超能力往上提一層 (市場層級的順勢/避險)。

PIT 保證:只用 date ≤ as_of 的基準價格;資料不足一律回 'neutral' (安全:不調整權重)。
本模組不碰 API、不改分數計算本身,只輸出 regime 標籤與對應的權重乘數。
================================================================================
"""
from __future__ import annotations

import pandas as pd

# regime → 五維權重「乘數」(乘在 mode_weights 上;advise() 會重新正規化,故不需自行歸一)。
#   空頭:動能砍到 0.45×、技術 0.70×,基本面 1.60×、估值 1.20× → 排序改由抗跌的基本面主導。
#   多頭:動能 1.10×、技術 1.05× → 順勢略增。中性:不動。
#   ⚠ 這些乘數是可調旋鈕,改後需以 --cycle (2022 空頭) + --validate 複驗。
REGIME_MULTIPLIERS = {
    "bull":    {"fundamental": 1.00, "valuation": 1.00, "technical": 1.05, "momentum": 1.10, "whale": 1.00},
    "neutral": {"fundamental": 1.00, "valuation": 1.00, "technical": 1.00, "momentum": 1.00, "whale": 1.00},
    # v3 方向反轉:2022-only 歸因推翻 v1/v2 的「空頭靠基本面防守、動能會被打臉」假設——
    #   2022 實測:動能是唯一有效因子 (IC +0.049/多空 +0.79%);毒藥是籌碼 (IC −0.092/−2.13%)
    #   與技術面 (−0.037/−2.83%),基本面也小負 (−0.022)。持續陰跌盤裡橫斷面動能有效 (弱者恆弱),
    #   法人買超變逆向指標、多頭排列被均值回歸打臉。→ bear 改為:保動能、砍籌碼/技術、估值降。
    #   v2 值 (已證偽,勿回退):fund 2.0/val 1.6/tech .55/mom .15/whale .85 → 2022 反而 −0.60→−0.74
    #   v1 值:fund 1.6/val 1.2/tech .70/mom .45/whale .90 → 2022 −0.60
    "bear":    {"fundamental": 1.00, "valuation": 0.60, "technical": 0.30, "momentum": 1.50, "whale": 0.30},
}


def classify_regime(bench_price_df, as_of, *, ma_long: int = 120,
                    slope_lookback: int = 20, deep_break: float = 0.93) -> str:
    """
    以基準 (0050) 的 PIT 切片判斷 regime:
      · 收盤『站上』長均線 (MA120) 且長均線『上彎』 → 'bull'
      · 收盤『跌破』長均線 且長均線『下彎』        → 'bear'
      · 【快速通道】收盤 < MA120 × deep_break (深跌破 7%) → 直接 'bear',不等斜率翻負。
        (v2 加入:2022 年 1 月開跌但 MA120 斜率 3~4 月才翻負,原版年初殺最兇時 regime
         還停在 neutral、濾網沒開 → 深跌破位視為急跌熊市確認,提早切換。)
      · 其餘 (騎線 / 均線與價背離)                → 'neutral'
    資料不足 (< ma_long + slope_lookback) → 'neutral'。
    """
    if bench_price_df is None:
        return "neutral"
    if "date" not in bench_price_df.columns or "close" not in bench_price_df.columns:
        return "neutral"
    df = bench_price_df[bench_price_df["date"].astype(str) <= str(as_of)]
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < ma_long + slope_lookback:
        return "neutral"
    ma = close.rolling(ma_long).mean()
    last = float(close.iloc[-1])
    ma_now = float(ma.iloc[-1])
    ma_prev = float(ma.iloc[-1 - slope_lookback])
    if pd.isna(ma_now) or pd.isna(ma_prev):
        return "neutral"
    if last < ma_now * deep_break:          # 深跌破快速通道:急跌不等均線下彎
        return "bear"
    rising = ma_now > ma_prev
    if last > ma_now and rising:
        return "bull"
    if last < ma_now and not rising:
        return "bear"
    return "neutral"


def regime_multipliers(regime) -> dict:
    """回傳該 regime 的五維權重乘數;未知/None → 中性 (全 1.0)。"""
    return REGIME_MULTIPLIERS.get(regime or "neutral", REGIME_MULTIPLIERS["neutral"])
