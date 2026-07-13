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


def _weekly_confirm_series(d: pd.DataFrame, ma_weeks: int = 24, slope_lookback_weeks: int = 4) -> pd.Series:
    """
    【多時間框確認,向量化版】把整段日線一次重取樣成週線 (W-FRI),算出每週的
    bull/neutral/bear,再 ffill 回日線索引 (PIT 安全:某交易日只可能對齊到「已收盤」
    的前一個週五,不會用到未來週線)。取代逐日呼叫版本,結果語意相同但只算一次。
    """
    idx = pd.to_datetime(d["date"])
    weekly = d.set_index(idx)["close"].resample("W-FRI").last().dropna()
    wma = weekly.rolling(ma_weeks).mean()
    wma_prev = wma.shift(slope_lookback_weeks)
    w_rising = wma > wma_prev
    w_raw = pd.Series("neutral", index=weekly.index)
    w_raw[(weekly > wma) & w_rising] = "bull"
    w_raw[(weekly < wma) & (~w_rising)] = "bear"
    daily_aligned = w_raw.reindex(idx, method="ffill").fillna("neutral")
    daily_aligned.index = d.index
    return daily_aligned


def _vol_adjusted_deep_break_series(close: pd.Series, ma: pd.Series, *, vol_lookback: int = 20,
                                     sigma_k: float = 2.0, min_break: float = 0.04, max_break: float = 0.15) -> pd.Series:
    """
    【波動率正規化深跌破,向量化版 —— 已驗證有內生性缺陷,預設關閉 (use_vol_adjusted_break=False)】
    原構想:固定門檻 (跌破 MA120×0.93) 沒考慮當下波動率,想用近期波動率動態調整。
    實測結果 (2025 關稅崩盤案例) 反而更差:2025-03-28 乖離已達 -7.0%,固定門檻立刻觸發;
    但當時初跌段本身已推高近 20 日已實現波動率,動態門檻反被撐大到 10.1%,
    導致快速通道延後到 2025-04-07(乖離 -17.6%,已是崩盤中段)才觸發——
    問題出在『用來源自同一段下跌的波動率去放寬同一段下跌的門檻』,存在內生性
    (下跌本身推高波動率 → 波動率又拉寬門檻 → 越該提早偵測的時候反而越晚觸發)。
    保留函式與參數供未來重新設計,但目前不建議啟用。
    """
    daily_vol = close.pct_change().rolling(vol_lookback).std()
    dyn_break = (sigma_k * daily_vol * (vol_lookback ** 0.5)).clip(lower=min_break, upper=max_break)
    dyn_break = dyn_break.fillna(min_break)
    return close < ma * (1 - dyn_break)


def _raw_regime_series(price_df: pd.DataFrame, *, ma_long: int = 120, slope_lookback: int = 20,
                       deep_break: float = 0.93, use_weekly_confirm: bool = True,
                       use_vol_adjusted_break: bool = False) -> pd.DataFrame:
    """
    一次算出整段歷史每日的『原始』regime (未套冷卻期),向量化取代逐日呼叫版,
    回傳含 date/raw 兩欄的 DataFrame,index 對齊排序後的交易日序列。
    raw ∈ {'bull','neutral','bear','bear_fast'} —— 'bear_fast' 是深跌破快速通道命中,
    後續套冷卻期時要豁免 (急殺不該被冷卻期拖慢反應)。
    """
    d = price_df[["date", "close"]].copy()
    d["date"] = d["date"].astype(str)
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)

    close = d["close"]
    ma = close.rolling(ma_long).mean()
    ma_prev = ma.shift(slope_lookback)
    rising = ma > ma_prev

    raw = pd.Series("neutral", index=d.index)
    raw[(close > ma) & rising] = "bull"
    raw[(close < ma) & (~rising)] = "bear"

    deep = (_vol_adjusted_deep_break_series(close, ma) if use_vol_adjusted_break
            else close < ma * deep_break)
    raw[deep.fillna(False)] = "bear_fast"

    if use_weekly_confirm:
        weekly = _weekly_confirm_series(d)
        conflict = raw.isin(["bull", "bear"]) & (weekly != "neutral") & (weekly != raw)
        raw[conflict] = "neutral"

    # 資料不足 (MA 尚未成形) → 一律中性,與原逐日版行為一致
    raw[ma.isna() | ma_prev.isna()] = "neutral"
    d["raw"] = raw
    return d[["date", "raw"]]


def _apply_hysteresis(raw_series: pd.Series, confirm_days: int = 5,
                      bear_enter_k: int = 2, bear_enter_m: int = 5,
                      bear_exit_k: int = 10, bear_exit_m: int = 10) -> list:
    """
    【冷卻期/遲滯,K-of-M 密度版】把『原始』regime 序列轉成『已確認』regime 序列。

    v1(純連續天數)踩到一個結構性缺陷:『連續 N 天』對雜訊極度敏感——2022 年底陰跌
    探底期原始訊號常連續碰到 bear 2~3 天就被一天雜訊打斷、計數器歸零重來,導致
    bear_enter_confirm_days 在敏感度分析裡出現真實懸崖 (1~3 天結果穩定,4 天直接讓
    2022 排序力從 +0.35% 崩到 -0.36%,見舊版驗證註記)。
    v2 改用『近 M 天內至少 K 天』的密度多數決取代『連續 N 天』:中間夾雜 1~2 天雜訊
    不會讓判斷歸零重來,只要密度夠就能確認,結構上不再有這種「單一雜訊日打斷整個
    計數」的斷崖 (K=M 時等同於原本的連續版,是純粹的泛化、非行為改變)。
      · 'bear_fast' (深跌破快速通道) 豁免此機制,一命中立刻確認為 'bear',
        保留對急殺的即時反應 (2025 關稅崩盤案例已驗證這條快速通道本身夠快)。
      · 【不對稱,防守要快、解除警報要慢】三組 (K, M) 分開設定:
          - 進入 bear (neutral/bull → bear):bear_enter_k/m (預設 2/5,偏快、偏寬容)
          - 離開 bear (bear → neutral/bull):bear_exit_k/m (預設 10/10,偏慢、等同原連續版)
          - 其餘 (bull ↔ neutral):confirm_days (K=M=confirm_days,維持原連續行為,
            此側未觀察到懸崖問題,不需要改)
    """
    confirmed = []
    current = "neutral"
    history: list = []
    for r in raw_series:
        r_norm = "bear" if r == "bear_fast" else r
        history.append(r_norm)
        if r == "bear_fast":
            current = "bear"
        elif r_norm != current:
            if r_norm == "bear":
                k, m = bear_enter_k, bear_enter_m
            elif current == "bear":
                k, m = bear_exit_k, bear_exit_m
            else:
                k, m = confirm_days, confirm_days
            if history[-m:].count(r_norm) >= k:
                current = r_norm
        confirmed.append(current)
    return confirmed


_SERIES_CACHE: dict = {}


def _confirmed_regime_series(price_df: pd.DataFrame, *, ma_long: int = 120, slope_lookback: int = 20,
                             deep_break: float = 0.93, use_weekly_confirm: bool = True,
                             use_vol_adjusted_break: bool = False, confirm_days: int = 5,
                             bear_enter_k: int = 2, bear_enter_m: int = 5,
                             bear_exit_k: int = 10, bear_exit_m: int = 10) -> pd.Series:
    """整段歷史的『已確認』regime,依 date 字串索引;同一份 price_df + 參數只算一次 (memoized)。"""
    key = (id(price_df), len(price_df), str(price_df["date"].iloc[-1]) if len(price_df) else "",
           ma_long, slope_lookback, deep_break, use_weekly_confirm, use_vol_adjusted_break,
           confirm_days, bear_enter_k, bear_enter_m, bear_exit_k, bear_exit_m)
    cached = _SERIES_CACHE.get(key)
    if cached is not None:
        return cached
    raw_df = _raw_regime_series(price_df, ma_long=ma_long, slope_lookback=slope_lookback,
                                deep_break=deep_break, use_weekly_confirm=use_weekly_confirm,
                                use_vol_adjusted_break=use_vol_adjusted_break)
    confirmed = _apply_hysteresis(raw_df["raw"], confirm_days=confirm_days,
                                  bear_enter_k=bear_enter_k, bear_enter_m=bear_enter_m,
                                  bear_exit_k=bear_exit_k, bear_exit_m=bear_exit_m)
    series = pd.Series(confirmed, index=raw_df["date"])
    _SERIES_CACHE[key] = series
    return series


def classify_regime(bench_price_df, as_of, *, ma_long: int = 120,
                    slope_lookback: int = 20, deep_break: float = 0.93,
                    use_weekly_confirm: bool = True, use_vol_adjusted_break: bool = False,
                    confirm_days: int = 5, bear_enter_k: int = 2, bear_enter_m: int = 5,
                    bear_exit_k: int = 10, bear_exit_m: int = 10) -> str:
    """
    以基準 (0050) 的 PIT 切片判斷 regime:
      · 收盤『站上』長均線 (MA120) 且長均線『上彎』 → 'bull'
      · 收盤『跌破』長均線 且長均線『下彎』        → 'bear'
      · 【快速通道】收盤 < MA120 × deep_break (固定深跌破 7%) → 直接 'bear',不等斜率翻負、
        也不等週線確認、也不等冷卻期 (保留對急殺的即時反應)。曾試過改用波動率動態門檻
        (use_vol_adjusted_break=True),但實測 2025 關稅崩盤案例反而因『下跌本身推高波動率
        → 門檻被放寬』而延後偵測,故預設關閉不用 (見 _vol_adjusted_deep_break_series)。
      · 其餘 (騎線 / 均線與價背離)                → 'neutral'
      · 【多時間框確認】慢速路徑判定的 bull/bear,需與週線趨勢同向 (或週線中性) 才放行
        (use_weekly_confirm 可關閉)。實測對 whipsaw 幾乎沒有抑制效果,保留但不是主力解法。
      · 【冷卻期/遲滯,主力解法,K-of-M 密度版,不對稱】慢速路徑訊號需在近 M 天內累積
        K 天同向才真正切換,期間維持原確認狀態,直接壓 whipsaw 且不像純連續版那樣
        被單一雜訊日打斷歸零;進入 bear 用寬容的 bear_enter_k/m (防守要快)、離開 bear
        用嚴格的 bear_exit_k/m (解除警報要慢)、其餘 (bull↔neutral) 用 confirm_days
        (K=M,見 _apply_hysteresis docstring 與模組底部驗證註記)。
    資料不足 (< ma_long + slope_lookback) → 'neutral'。
    PIT 保證:_confirmed_regime_series 逐日往前推進、只用 ≤ 當日資料,不會偷看未來,
    只是為了效能把整段歷史一次算好、用 date 當索引查找 (等同對每個 as_of 各呼叫一次)。
    """
    if bench_price_df is None:
        return "neutral"
    if "date" not in bench_price_df.columns or "close" not in bench_price_df.columns:
        return "neutral"
    series = _confirmed_regime_series(bench_price_df, ma_long=ma_long, slope_lookback=slope_lookback,
                                      deep_break=deep_break, use_weekly_confirm=use_weekly_confirm,
                                      use_vol_adjusted_break=use_vol_adjusted_break,
                                      confirm_days=confirm_days,
                                      bear_enter_k=bear_enter_k, bear_enter_m=bear_enter_m,
                                      bear_exit_k=bear_exit_k, bear_exit_m=bear_exit_m)
    eligible = series[series.index <= str(as_of)]
    if eligible.empty:
        return "neutral"
    return eligible.iloc[-1]


def regime_multipliers(regime) -> dict:
    """回傳該 regime 的五維權重乘數;未知/None → 中性 (全 1.0)。"""
    return REGIME_MULTIPLIERS.get(regime or "neutral", REGIME_MULTIPLIERS["neutral"])


# regime → 評級 gate 調整 (供 InvestmentAdvisor._decide_rating 使用)。
# 動機:REGIME_MULTIPLIERS 只調整 total_score 的『排序』權重,v4.2 已讓 2022 空頭排序力
#   轉正 (-0.84%→+0.32%),但『評級』(強烈推薦/強勢買進) 的門檻 min_score/chip_min/whale_hot
#   是固定值、不吃 regime——導致空頭段仍常給出強推/強買,買進桶多空仍 -2.99%。
# 依同一份 2022 歸因 (見上方 REGIME_MULTIPLIERS 註解):籌碼在持續陰跌盤是反指標
#   (IC -0.092),動能才是唯一有效因子 (IC +0.049)。因此 bear 段只加嚴『籌碼閘門』
#   (chip_min / whale_hot,對應 E1 強烈推薦、E2 順勢強推、強勢買進的點火條件),
#   min_score 也墊高讓一般門檻更嚴;momentum 閘門 (mom_hot) 不動,避免錯殺真動能股。
#   讓 bear 段自動更接近『空手』(v3 的市場層級超能力,拉到評級層級)。
# ⚠ 這些數字是可調旋鈕,改後需以 --cycle (2022 空頭) + --validate 複驗買進桶多空。
REGIME_RATING_GATES = {
    "bull":    {"min_score_add": 0.0, "chip_min_mult": 1.00, "whale_hot_mult": 1.00},
    "neutral": {"min_score_add": 0.0, "chip_min_mult": 1.00, "whale_hot_mult": 1.00},
    "bear":    {"min_score_add": 10.0, "chip_min_mult": 1.50, "whale_hot_mult": 1.40},
}


def regime_rating_gates(regime) -> dict:
    """回傳該 regime 的評級門檻調整;未知/None → 中性 (不調整)。"""
    return REGIME_RATING_GATES.get(regime or "neutral", REGIME_RATING_GATES["neutral"])
