# -*- coding: utf-8 -*-
"""regime_exposure.py — 市場燈號:現在該持有幾成 (多軸階梯 + 確認3d 遲滯)。
================================================================================
定位:把 beat_0050 全循環驗證過的「曝險訊號」搬成 App 可用的即時燈號。
邏輯與回測**完全一致**(beat_0050/strategies/regime_hysteresis_lab.py 定案版):
  · 等權全市場指數 vs MA50/100/200(站上幾條 → 曝險 3/3, 2/3, 1/3, 0)。
  · 遲滯(確認3d):每條 MA 的上/下穿要連續 3 天才翻狀態,濾掉碎波 whipsaw。
訊號是**反應式**(判斷該承受多少風險),**非預測方向**。全循環含息回測:此訊號疊在
價值+基本面選股上,夏普 0.95 > 0050 0.69、MDD -25.4% 優於 -54%(2005-2026)。
  ※ 數字對應本檔實際採用的 UP_CONFIRM=DOWN_CONFIRM=3,即 regime_hysteresis_lab 的
    「+對稱確認3d」列(CAGR 16.4 / 夏普 0.95 / MDD -25.44),**月換手**、來回成本 0.72%。
    舊版誤植的 0.83/-27% 出自同表「+慢回補10d/降1」——**評估過但未採用**的參數,
    已於 2026-07-28 更正;2026-07-29 再依滑價上修(0.10→0.25%)重跑,1.01→0.95。

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

# ---- 曝險調整速率限制 (docs/預註冊_ExposureRateLimit.md, 2026-07-29 預註冊) ----
# 問題:階梯規則對「單次調整幅度」沒有上限。實測 266 次調整中有 **20 次 >1/3、最大 100%**
#      —— 單日清空 25 檔部位在操作上不可行。多加均線無法解決(相鄰均線會同時翻,L5a 的
#      >1/3 次數反而從 20 增為 68);只有速率限制器**由建構保證**上限。
# 方案:每個交易日朝目標最多移動 CAP,**對加碼與減碼對稱適用**。訊號完全不變,只約束路徑。
# 代價:夏普 0.95→0.92、CAGR −0.55pp(回測內)+ 手續費低消綁定 −0.29pp(回測外) ≈ −0.85pp/年。
# 冷卻期:依 SOP §6 後設規則,規則變更不得在燈號變動後 5 個交易日內生效 →
#        訊號變動日 2026-07-28 起算,生效日 2026-08-05。此日之前限速器不作用。
RATE_LIMIT_CAP = 0.20            # 每交易日最大曝險調整幅度 (1/5)
RATE_LIMIT_FROM = "2026-08-05"   # 生效日 (含當日);之前完全不改變行為


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


LADDER_LABEL = {3: "滿倉 risk-on", 2: "偏多", 1: "防禦減碼", 0: "空手 risk-off"}


def _rate_limit(dates: list, target: np.ndarray, cap: float, start: str) -> np.ndarray:
    """速率限制:自 start 日起,每日朝 target 最多移動 cap(雙向對稱)。
    start 之前原樣輸出 → 生效日以當日實際曝險為起點,不回頭改寫歷史。"""
    out = np.array(target, float)
    cur = None
    for i, d in enumerate(dates):
        if d < start:
            continue
        if cur is None:                      # 生效日:以當下實際曝險為起點
            cur = float(target[i - 1]) if i > 0 else float(target[i])
        cur += float(np.clip(target[i] - cur, -cap, cap))
        out[i] = cur
    return out


def _reason(lines: list, ladder_n: int, expo: float) -> dict:
    """把曝險數字翻成「為什麼是這個燈號」。純粹是階梯規則的白話版,不引入新判斷。"""
    held = [L for L in lines if L["above"]]
    broken = [L for L in lines if not L["above"]]
    recent = min(lines, key=lambda L: L["days"])          # 最近一次翻狀態的那條
    drivers = []
    if broken:
        drivers.append("跌破 " + "、".join(f"MA{L['ma']}({L['gap_pct']:+.1f}%)" for L in broken)
                       + f" → 各扣 1/3 曝險,共扣 {len(broken)}/3")
    if held:
        drivers.append("仍站上 " + "、".join(f"MA{L['ma']}({L['gap_pct']:+.1f}%)" for L in held)
                       + f" → 保留 {len(held)}/3 曝險")
    drivers.append(f"最近一次變化:MA{recent['ma']} "
                   f"{'站上' if recent['above'] else '跌破'}已 {recent['days']} 天")
    if any(L["pending"] for L in lines):
        p = [L for L in lines if L["pending"]]
        drivers.append("⏳ " + "、".join(f"MA{L['ma']}" for L in p)
                       + " 原始價已翻但遲滯確認中(需連 3 天),曝險尚未跟著改")
    return {
        "headline": f"曝險 {expo*100:.0f}%({LADDER_LABEL[ladder_n]})"
                    f" —— 等權指數站上 3 條均線中的 {ladder_n} 條",
        "drivers": drivers,
        "meaning": ("多數個股的中長期趨勢仍完整,維持較高曝險。" if ladder_n == 3 else
                    "部分中期趨勢轉弱,開始逐階減碼。" if ladder_n == 2 else
                    "中期趨勢已轉弱、只剩長期支撐,大幅減碼。" if ladder_n == 1 else
                    "長中短期趨勢全數轉弱,主動選股部位全數轉現金。"),
    }


def compute_exposure(tail_days: int = 120) -> dict:
    """回傳當前曝險狀態 dict:
       exposure(0~1)、ladder_n(0~3)、lines(每條MA的站上與否+確認天數)、
       as_of(最新交易日)、hist(近 tail_days 的日曝險序列,供 sparkline)、
       reason(為什麼是這個燈號)、market(加權指數/量能等**參考**欄位,不驅動訊號)。"""
    f = _ew_index()
    states = {}
    for w in (50, 100, 200):
        raw = (f["ew"] >= f[f"ma{w}"]).to_numpy()
        states[w] = _debounce(raw, UP_CONFIRM, DOWN_CONFIRM)
    ladder = (states[50].astype(int) + states[100] + states[200])  # 0..3
    target_series = ladder / 3.0
    # 訊號(target)不變;限速只約束「走過去的路徑」,且生效日前完全不作用
    expo_series = _rate_limit(f["date"].tolist(), target_series,
                              RATE_LIMIT_CAP, RATE_LIMIT_FROM)

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

    # 加權指數/量能/漲跌家數:**只供對照顯示**,不進訊號 (見 core/market_index.py 開頭說明)
    try:
        from core.market_index import get_context
        market = get_context()
    except Exception:
        market = None

    expo, n = float(expo_series[-1]), int(ladder[-1])
    tgt = float(target_series[-1])
    as_of = str(f["date"].iloc[-1])
    gap = tgt - expo
    return {
        "exposure": expo,                    # 今天實際該持有的(已套用限速)
        "target_exposure": tgt,              # 訊號目標(階梯原值)
        "ladder_n": n,
        "as_of": as_of,
        "lines": lines,
        "hist": hist,
        "reason": _reason(lines, n, tgt),
        "market": market,
        "rate_limit": {
            "active": as_of >= RATE_LIMIT_FROM,
            "cap": RATE_LIMIT_CAP,
            "effective_from": RATE_LIMIT_FROM,
            "gap": gap,
            "days_to_target": int(np.ceil(abs(gap) / RATE_LIMIT_CAP - 1e-9)) if abs(gap) > 1e-9 else 0,
        },
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
