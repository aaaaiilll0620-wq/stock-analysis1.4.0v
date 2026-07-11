"""
dynamic_stop_engine.py — 動態籌碼支撐停損 / 分層移動停利(獨立、可直接運行版本)

從 core/backtest.py 抽出、已驗證可正確運行的路徑相依出場核心。
輸入一段日 K(需含 date, close, volume;有 open/high/low 更佳)+ 進場日,
逐根 K 動態更新籌碼成本區,收盤『實質』跌破防線 → 隔日開盤市價出清,回傳這筆交易結果。

三道防線(優先序):
  1) 動態支撐停損:status 為『上方(追高)』或『成本區內』時,收盤 < 當前動態 support → 出場。
     (只認收盤 close < support,盤中假跌破不算;下方/相對便宜狀態不套用此線。)
  2) 移動停利 — 分層併用,取較緊者(min):
       a. σ 移動停利(Chandelier 式,日常主鎖):giveback_a = trail_mult × volatility_pct(%)。
          高波動飆股 buffer 大(不易被洗)、低波動牛皮股 buffer 小(緊貼防線鎖利)。
       b. 追高門檻硬上限(regime 級 backstop):giveback_b = cap_mult × chase_threshold_pct(%)。
          σ 失真時封頂『從最高點的最大回吐』。實際 buffer = min(a, b)。
  3) 時間停損:達 holding_days 未觸發 → 到期收盤出場(與固定持有期相容,績效可比)。

無未來函數:每根 K 只用 date<=當根 的切片重算成本區;訊號當根收盤觸發、隔日開盤才成交。

依賴:core.technical_analysis.TechnicalEngine.calculate_volume_profile
      (內含動態追高門檻 calculate_adaptive_chase_band,回傳 support/status/
       chase_threshold_pct/volatility_pct)。獨立執行時請確保 core 套件可被 import。
"""
import pandas as pd

try:
    from core.technical_analysis import TechnicalEngine
    _calc_vp = TechnicalEngine.calculate_volume_profile
except Exception:  # 純獨立測試的後備:同資料夾放一份 volume profile 模組亦可
    import importlib.util as _u, os as _os
    _p = _os.path.join(_os.path.dirname(__file__), "Volume profile.py")
    _spec = _u.spec_from_file_location("_vp_mod", _p)
    _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
    _calc_vp = _m.calculate_volume_profile


def _norm_price(price_df: pd.DataFrame) -> pd.DataFrame:
    """統一 FinMind 欄位供技術函式使用:Trading_Volume→volume(股→張)、close→數值、max→high、min→low。"""
    p = price_df.copy()
    if "Trading_Volume" in p.columns and "volume" not in p.columns:
        p["volume"] = pd.to_numeric(p["Trading_Volume"], errors="coerce") / 1000.0  # 股→張
    p["close"] = pd.to_numeric(p["close"], errors="coerce")
    if "max" in p.columns and "high" not in p.columns:
        p["high"] = pd.to_numeric(p["max"], errors="coerce")
    if "min" in p.columns and "low" not in p.columns:
        p["low"] = pd.to_numeric(p["min"], errors="coerce")
    return p


def cost_zone_on(price_df: pd.DataFrame, as_of: str) -> dict | None:
    """在 as_of『當下』(僅用 date<=as_of 的切片)重算籌碼成本區。
    回傳含 support / status / chase_threshold_pct / volatility_pct;資料不足回 None。無未來函數。"""
    if price_df is None or "date" not in price_df.columns:
        return None
    sl = price_df[price_df["date"].astype(str) <= str(as_of)]
    if sl is None or len(sl) < 30:
        return None
    p = _norm_price(sl)
    if p["close"].dropna().shape[0] < 30:
        return None
    try:
        return _calc_vp(p)
    except Exception:
        return None


def simulate_exit(price_df: pd.DataFrame, as_of: str, holding_days: int = 20,
                  use_support_stop: bool = True, use_trailing: bool = True,
                  trail_mult: float = 2.5, cap_mult: float = 1.0,
                  min_hold: int = 1) -> dict | None:
    """
    路徑相依出場模擬:進場 = as_of 收盤,逐根 K 更新籌碼區,跌破防線 → 隔日開盤市價出清。
    回傳 dict:forward_return(%)、exit_reason、bars_held、exit_date;資料不足回 None。
    exit_reason ∈ {dynamic_support, vol_trailing, chase_cap, time_stop}。
    """
    if price_df is None or "date" not in price_df.columns:
        return None
    d = price_df.copy()
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

    def _exit(t_i: int, reason: str) -> dict:
        """第 t_i 根收盤觸發 → 隔日(t_i+1)開盤市價出清;無隔日則以當根收盤。"""
        j = t_i + 1
        if j <= len(d) - 1:
            px = float(d.loc[j, open_col]) if open_col else float(d.loc[j, "close"])
            xd = str(d.loc[j, "date"])
        else:
            px = float(d.loc[t_i, "close"])
            xd = str(d.loc[t_i, "date"])
        return {"forward_return": (px - p0) / p0 * 100.0, "exit_reason": reason,
                "bars_held": t_i - i0, "exit_date": xd}

    for t in range(i0 + 1, last_i + 1):
        as_of_t = str(d.loc[t, "date"])
        close_t = float(d.loc[t, "close"])
        peak = max(peak, close_t)
        held = t - i0
        cz = cost_zone_on(d, as_of_t)
        if not cz or held < min_hold:
            continue
        support = cz.get("support")
        status = cz.get("status", "") or ""
        vol_pct = cz.get("volatility_pct")
        chase_thr = cz.get("chase_threshold_pct")

        # 1) 動態支撐停損 (追高 或 成本區內;收盤跌破)
        if use_support_stop and support and close_t < float(support) \
                and (status.startswith("上方") or status.startswith("成本區內")):
            return _exit(t, "dynamic_support")

        # 2) 移動停利:σ 日常鎖 + 追高門檻硬上限,取較緊者(min)
        if use_trailing:
            givebacks = []
            if vol_pct:
                givebacks.append(("vol_trailing", trail_mult * float(vol_pct)))
            if chase_thr:
                givebacks.append(("chase_cap", cap_mult * float(chase_thr)))
            if givebacks:
                reason, buf = min(givebacks, key=lambda kv: kv[1])
                if close_t < peak * (1.0 - buf / 100.0):
                    return _exit(t, reason)

    # 3) 時間停損:到期收盤
    return {"forward_return": (float(d.loc[last_i, "close"]) - p0) / p0 * 100.0,
            "exit_reason": "time_stop", "bars_held": last_i - i0,
            "exit_date": str(d.loc[last_i, "date"])}


if __name__ == "__main__":
    # 範例:讀一段日 K(需 date, close, volume;有 open/high/low 更佳),對某進場日模擬出場
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "4958_actual_data.csv"
    entry = sys.argv[2] if len(sys.argv) > 2 else None
    df = pd.read_csv(path)
    if entry is None:                       # 未指定進場日 → 取「倒數第 25 根」示範(需留出前後窗)
        entry = str(df.sort_values("date")["date"].iloc[-25])
    cz = cost_zone_on(df, entry)
    print(f"進場日 {entry}")
    if cz:
        print(f"  成本區: status={cz.get('status','')[:10]}  support={cz.get('support')}  "
              f"chase_threshold={cz.get('chase_threshold_pct')}%  volatility={cz.get('volatility_pct')}%")
    for tm in (2.0, 2.5, 3.5):
        r = simulate_exit(df, entry, holding_days=25, trail_mult=tm, cap_mult=1.0)
        print(f"  trail_mult={tm}: {r}")
