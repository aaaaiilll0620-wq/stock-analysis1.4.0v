# -*- coding: utf-8 -*-
"""regime_exposure.py — 市場燈號:現在該持有幾成 (多軸階梯 + 確認3d 遲滯)。
================================================================================
定位:把 beat_0050 全循環驗證過的「曝險訊號」搬成 App 可用的即時燈號。
邏輯與回測**完全一致**(beat_0050/strategies/regime_hysteresis_lab.py 定案版):
  · 等權全市場指數 vs MA50/100/200(站上幾條 → 曝險 3/3, 2/3, 1/3, 0)。
  · 遲滯(確認3d):每條 MA 的上/下穿要連續 3 天才翻狀態,濾掉碎波 whipsaw。
訊號是**反應式**(判斷該承受多少風險),**非預測方向**。全循環含息回測:此訊號疊在
價值+基本面選股上,夏普 0.83 > 0050 0.69、MDD -24% 優於 -54%(2005-2026)。

資料源:~/tej_cache/price_valuation(全市場日線,收集器每日更新)。非投資建議。
================================================================================
"""
from __future__ import annotations
import os
import json
from pathlib import Path
import numpy as np
import pandas as pd

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
SNAPSHOT = Path(__file__).resolve().parent.parent / "cloud_cache" / "regime_exposure.json"
UP_CONFIRM = 3
DOWN_CONFIRM = 3


def _debounce(cond: np.ndarray, up: int, down: int) -> np.ndarray:
    """cond=True 表站上MA。翻True需連續up天、翻False需連續down天(不對稱遲滯)。"""
    state = np.empty(len(cond), bool)
    s = bool(cond[0]); u = d = 0
    for i, c in enumerate(cond):
        if c:
            u += 1; d = 0
        else:
            d += 1; u = 0
        if not s and u >= up:
            s = True
        elif s and d >= down:
            s = False
        state[i] = s
    return state


def _ew_index() -> pd.DataFrame:
    """等權全市場指數 (日) + MA50/100/200。讀 tej_cache 種子 ∪ market_cache 每日快照
    (與 live 評分同一新鮮度:collector 每日 17:30 寫快照,燈號自動追到最新交易日)。"""
    import duckdb
    con = duckdb.connect()
    globs = [f"'{TEJ_CACHE}/price_valuation/*.parquet'"]
    daily_dir = MARKET_CACHE / "price_valuation_daily"
    if daily_dir.exists() and any(daily_dir.glob("*.parquet")):
        globs.append(f"'{daily_dir}/*.parquet'")
    px = con.execute(f"""
        SELECT stock_id, date, close FROM
        read_parquet([{', '.join(globs)}], union_by_name=true)
        WHERE close > 0
    """).df()
    px = px.drop_duplicates(["stock_id", "date"]).sort_values(["stock_id", "date"])
    px["ret"] = px.groupby("stock_id")["close"].pct_change()
    daily = (px[(px["ret"].notna()) & (px["ret"].abs() < 0.5)]
             .groupby("date")["ret"].mean().sort_index())
    ew = (1 + daily).cumprod()
    f = pd.DataFrame({"date": ew.index.astype(str), "ew": ew.values})
    for w in (50, 100, 200):
        f[f"ma{w}"] = f["ew"].rolling(w, min_periods=w).mean()
    return f.dropna(subset=["ma200"]).reset_index(drop=True)


def compute_exposure(tail_days: int = 120) -> dict:
    """回傳當前曝險狀態 dict:
       exposure(0~1)、ladder_n(0~3)、lines(每條MA的站上與否+確認天數)、
       as_of(最新交易日)、hist(近 tail_days 的日曝險序列,供 sparkline)。"""
    f = _ew_index()
    states = {}
    for w in (50, 100, 200):
        raw = (f["ew"] >= f[f"ma{w}"]).to_numpy()
        states[w] = _debounce(raw, UP_CONFIRM, DOWN_CONFIRM)
    ladder = (states[50].astype(int) + states[100] + states[200])  # 0..3
    expo_series = ladder / 3.0

    # 每條 MA:確認狀態(驅動曝險) + 原始站上與否 + 已維持天數
    lines = []
    for w in (50, 100, 200):
        s = states[w]
        cur = bool(s[-1])
        days = 1
        for j in range(len(s) - 2, -1, -1):
            if s[j] == cur:
                days += 1
            else:
                break
        gap = float(f["ew"].iloc[-1] / f[f"ma{w}"].iloc[-1] - 1) * 100
        raw_above = bool(f["ew"].iloc[-1] >= f[f"ma{w}"].iloc[-1])
        lines.append({"ma": w, "above": cur, "raw_above": raw_above,
                      "pending": raw_above != cur,          # 原始已翻、遲滯確認中
                      "days": days, "gap_pct": gap})

    hist = pd.DataFrame({"date": f["date"].tolist()[-tail_days:],
                         "曝險%": (expo_series[-tail_days:] * 100)})
    return {
        "exposure": float(expo_series[-1]),
        "ladder_n": int(ladder[-1]),
        "as_of": str(f["date"].iloc[-1]),
        "lines": lines,
        "hist": hist,
    }


# ---- 快照持久化:本機算 → 寫 cloud_cache;雲端(無 tej_cache)讀快照 ----
def persist_snapshot(state: dict | None = None) -> Path:
    """算出當前曝險並寫入 cloud_cache/regime_exposure.json(供雲端 & 每日更新)。"""
    state = state or compute_exposure()
    out = dict(state)
    out["hist"] = state["hist"].to_dict("records")
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return SNAPSHOT


def load_snapshot() -> dict:
    d = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    d["hist"] = pd.DataFrame(d["hist"])
    return d


def get_exposure() -> dict:
    """本機能讀到 tej_cache 就即時算(最新);否則(雲端)退回 cloud_cache 快照。"""
    try:
        return compute_exposure()
    except Exception:
        return load_snapshot()


if __name__ == "__main__":
    p = persist_snapshot()
    print(f"✅ 快照已寫入 {p}")
