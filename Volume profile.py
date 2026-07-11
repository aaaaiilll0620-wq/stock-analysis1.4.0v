"""
volume_profile.py — 籌碼成本區 / 量價分布計算(獨立、可直接運行版本)

從 TechnicalEngine 抽出、已驗證可正確運行的核心成本計算函式。
輸入一段日 K(需含 close, volume;有 date/high/low 更佳),輸出主力成本區與支撐/壓力判讀。

回傳 dict 欄位:
    poc                主力成本區中心(成交量最密集價位, Point of Control)
    val / vah          價值區下緣 / 上緣(涵蓋 value_area_pct 成交量的價格帶)
    price_vs_poc_pct   現價相對 POC 的乖離(%);> 0 代表在成本上方
    status             現價相對成本區:上方(追高) / 成本區內 / 下方(相對便宜)
    support            現價下方最近的高量能節點(可退守支撐);無則 None
    resistance         現價上方最近的高量能節點(壓力);無則 None
    chase_threshold_pct 本次判定所用的『動態追高門檻』(%),依個股波動體質而定
    volatility_pct     波動體質估計值(取 ATR% 與日報酬率標準差較大者)
    vol_source         波動來源:"atr"(有 high/low)/ "std"(僅收盤)
    (資料不足時各值為 None、status 為 "")

設計重點(踩過的坑,勿回退):
  1. lookback 預設 90:近期時間窗;過長會混入早已脫離的舊價格帶,使 POC 失真。
  2. 不再限縮「現價 ±25%」價格帶:改由 lookback 控制樣本時間範圍。
  3. 追高判定看『與 POC 的距離』,但門檻不再寫死 25% —— 改用『動態波動門檻』:
     牛皮股(低波動)自動收窄到 ~15%;飆股(高波動)自動放寬到 ~45%。詳見
     _adaptive_chase_band。連續強漲股的近月換手會把 VAH 墊到貼近現價,只看邊界會誤判。
  4. 支撐/壓力掃描『全部高量能節點 HVN(>= POC 量能 25%)』,不是只挑價值區成員;
     追高時排除現價腳下那根節點,取下方最近節點當退守位(避免支撐硬等於 POC / 或過低)。
  5. status 字串下游常以子字串分流(先判 "下方" 再判 "上方"),故追高措辭僅含 "上方"、
     絕不可出現 "下方" 二字。
"""
import math
import numpy as np
import pandas as pd


def _calc_atr(df, window: int = 14):
    """平均真實區間 ATR;相容 high/low 或 max/min;缺欄位回傳 0.0。"""
    if df is None or df.empty or "close" not in df.columns:
        return 0.0
    high_col = "high" if "high" in df.columns else ("max" if "max" in df.columns else None)
    low_col = "low" if "low" in df.columns else ("min" if "min" in df.columns else None)
    if high_col is None or low_col is None:
        return 0.0
    h = pd.to_numeric(df[high_col], errors="coerce")
    l = pd.to_numeric(df[low_col], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=window, min_periods=1).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else 0.0


def _adaptive_chase_band(df, price_series, cur, z: float = 3.0, horizon: int = 25,
                         atr_window: int = 14, min_band: float = 15.0,
                         max_band: float = 45.0) -> dict:
    """
    依個股「近期波動體質」動態決定:現價偏離 POC 多少 % 才算『追高』,取代寫死的 25%。

    波動度估計(取兩來源較大者 → 較保守/寬鬆的擴張上限):
      1) 日報酬率標準差 σ_ret(%):對 gap 校正後收盤序列計算,永遠可得。
      2) ATR(atr_window) 佔『現價』百分比:需 high/low(或 max/min),缺則略過。
         (以現價為分母而非 POC:對飆股 POC 遠在下方會把波動% 灌爆。)

    門檻:允許價格在 horizon 個交易日內做一次 z 倍標準差的順勢延伸才算追高 →
      band = z * sqrt(horizon) * σ_daily,夾在 [min_band, max_band]。
      預設 z=3、horizon=25(係數 15):σ≈1%→貼 15%;σ≈3%→頂 45%。
    """
    empty = {"threshold_pct": 25.0, "volatility_pct": None,
             "atr_pct": None, "ret_std_pct": None, "source": ""}
    if price_series is None or len(price_series) < 3 or not cur:
        return empty
    ret = pd.Series(price_series).pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    std_pct = float(ret.std(ddof=1) * 100.0) if len(ret) > 2 else 0.0
    vol_pct, source = std_pct, "std"

    atr_pct = None
    high_col = "high" if "high" in df.columns else ("max" if "max" in df.columns else None)
    low_col = "low" if "low" in df.columns else ("min" if "min" in df.columns else None)
    if high_col and low_col:
        atr = _calc_atr(df, window=atr_window)
        if atr and atr > 0:
            atr_pct = atr / cur * 100.0
            if atr_pct > vol_pct:
                vol_pct, source = atr_pct, "atr"

    coeff = z * math.sqrt(max(int(horizon), 1))
    threshold = min(max(coeff * vol_pct, min_band), max_band)
    return {"threshold_pct": round(float(threshold), 1),
            "volatility_pct": round(float(vol_pct), 2),
            "atr_pct": (round(float(atr_pct), 2) if atr_pct is not None else None),
            "ret_std_pct": round(float(std_pct), 2),
            "source": source}


def calculate_volume_profile(df, lookback: int = 90, bins: int = 30,
                             value_area_pct: float = 0.70,
                             chase_z: float = 3.0, chase_horizon: int = 25,
                             min_chase_band: float = 15.0,
                             max_chase_band: float = 45.0) -> dict:
    empty = {"poc": None, "val": None, "vah": None, "price_vs_poc_pct": None,
             "status": "", "support": None, "resistance": None,
             "chase_threshold_pct": None, "volatility_pct": None, "vol_source": ""}
    if df is None or len(df) < 30 or "close" not in df.columns or "volume" not in df.columns:
        return empty

    d = df.copy()
    # 先按日期排序,確保 tail 取到的是『最近』而非資料原順序中的任意段落
    if "date" in d.columns:
        d = d.sort_values("date")
    d = d.tail(lookback).copy()

    price = pd.to_numeric(d["close"], errors="coerce")
    vol = pd.to_numeric(d["volume"], errors="coerce")
    mask = price.notna() & vol.notna() & (vol >= 0)
    price, vol = price[mask].reset_index(drop=True), vol[mask].reset_index(drop=True)
    if len(price) < 30:
        return empty

    # 跳空回補:視窗內若有分割/減資/大額配息造成的價格斷點(單日跳動 >30%),
    #   會讓 POC 落在事件前的舊價格尺度、與現價兜不起來 → 先把斷點前的價格接平。
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

    # 以整個 lookback 視窗的量價分布計算成本區(不設現價 ±25% 人工價格帶上下限)
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

    # 價值區間:由高量 bin 起累積,直到達 value_area_pct
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

    # 現價相對位置:以與 POC 的距離判追高,但門檻『動態化』(依波動體質),不再寫死 25%。
    # 措辭僅含 "上方",不可出現 "下方"(下游以子字串分流)。
    band = _adaptive_chase_band(d, price, cur, z=chase_z, horizon=chase_horizon,
                                min_band=min_chase_band, max_band=max_chase_band)
    chase_threshold = band["threshold_pct"]
    extended_above = (cur > poc and price_vs_poc is not None
                      and price_vs_poc >= chase_threshold)
    if extended_above or cur > vah:
        status = "上方(偏高/追高,已離成本區)"
    elif cur < val:
        status = "下方(相對便宜/上方套牢輕)"
    else:
        status = "成本區內(套牢賣壓區,需帶量突破)"

    # 支撐/壓力:掃描全部高量能節點 HVN(量能 >= POC 的 25%)
    hvn_thresh = vol_by_bin[poc_i] * 0.25
    hvn = [float(centers[i]) for i in range(bins) if vol_by_bin[i] >= hvn_thresh]
    if status.startswith("上方"):
        # 追高:排除現價腳下那根節點,支撐取現價所在 bin『下方』最近的量能節點(退守位)
        lo_edge, hi_edge = float(edges[cur_i]), float(edges[cur_i + 1])
        below = [c for c in hvn if c < lo_edge]
        above = [c for c in hvn if c > hi_edge]
    else:
        # 一般:支撐可貼近現價(當下踩著的量能節點,屬防守位)
        below = [c for c in hvn if c <= cur]
        above = [c for c in hvn if c >= cur]
    support = float(max(below)) if below else None
    resistance = float(min(above)) if above else None

    return {
        "poc": round(poc),
        "val": round(val),
        "vah": round(vah),
        "price_vs_poc_pct": (round(price_vs_poc, 1) if price_vs_poc is not None else None),
        "status": status,
        "support": (round(support) if support else None),
        "resistance": (round(resistance) if resistance else None),
        # 動態追高門檻 & 波動體質(供回測 Trailing Stop / 出場邏輯沿用同一套標準)
        "chase_threshold_pct": chase_threshold,
        "volatility_pct": band["volatility_pct"],
        "vol_source": band["source"],
    }


if __name__ == "__main__":
    # 範例:讀一段日 K(需 date, close, volume;有 high/low 更佳),印出成本區判讀
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "4958_actual_data.csv"
    df = pd.read_csv(path)
    result = calculate_volume_profile(df)
    print(f"現價 {df['close'].iloc[-1]:.0f}")
    for k, v in result.items():
        print(f"  {k:18} {v}")
