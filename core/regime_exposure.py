# -*- coding: utf-8 -*-
"""regime_exposure.py — 市場燈號:現在該持有幾成 (多軸階梯 + 確認3d 遲滯)。
================================================================================
定位(**2026-08-10 最終**):**α=0.25 部分套用** —— 曝險階梯壓縮到 **75%~100%** 區間。

  · 等權全市場指數 vs MA50/100/200(站上幾條 → 原始階梯 3/3, 2/3, 1/3, 0)。
  · 遲滯(確認3d):每條 MA 的上/下穿要連續 3 天才翻狀態,濾掉碎波 whipsaw。
  · **α 內插**:`blended = 1 − α·(1 − raw)`,α=0.25 →
    原始 {0, 1/3, 2/3, 1} 變成實際曝險 **{75%, 83.3%, 91.7%, 100%}**。

⚠️ **這是「研究否定 + 使用者明文豁免」的部署決定,不是研究通過。**
   `docs/預註冊_OverlayAlpha強度掃描.md` 的凍結判定是 **HOα-4a 否定、無 validated 部署候選**
   (α=0.25 在滑價 0.60% 壓力下 CAGR 17.55% < 20% 門檻)。使用者於 2026-08-10 依 §6.3 前例
   **明文豁免該門檻**採用,理由與代價見下。**文件一律記為豁免,不得寫成研究通過。**

   **豁免的實測依據(事後描述性量測,`overlay_alpha_describe.py`)**:
   | | CAGR | 夏普 | MDD |
   |---|---|---|---|
   | OOS 裸上 | 22.48% | 1.11 | −33.73% |
   | OOS α=0.25 | 20.93% | **1.17** | **−27.91%** |
   | 全期裸上 | 20.59% | 0.90 | −71.67% |
   | 全期 α=0.25 | 20.28% | **1.01** | **−62.71%** |
   · 全期只付 **0.30pp** CAGR,換到 **8.95pp** 回撤改善;夏普四種情境全部改善。
   · HOα-4a 那關的關鍵背景:**裸上在同樣 0.60% 滑價下也只有 18.77%,一樣沒過 20% 門檻**
     —— 該門檻在那個壓力水準下沒有區分 overlay 與裸上。

   ⚠️ **兩個必須跟著引用的但書**:
   1. **價值集中在 2008**:六時代裡 CAGR 只有 2005-2009 那段贏(21.27% vs 17.60%),
      其餘五段都小輸;全期「幾乎免費」是被那一段拉起來的。**而那段對本訊號是 in-sample**
      (RegimeInputLab 是用全歷史挑訊號規則),真本事與後見之明無法乾淨拆開。
   2. **2022 型幫不上忙**:該段回撤只改善 1.27pp,CAGR 反而從 −0.62% 惡化到 −2.79%。
      對「陰跌碎波」型空頭,這一層近乎無效甚至扣分。

   三輪研究的完整結論(不要再引用舊的漂亮數字):
   · `預註冊_RegimeInputLab.md`(2026-07-28):26 個輸入/規則變體全部沒有更好;
     且虛無對照證明「組合訊號」贏不過「把舊訊號打 85 折」——改善都來自持有更少。
   · `預註冊_ExposureOverlay.md`(P-Overlay-C,2026-07-31):套在**實際部署的 dual100**
     上 = CAGR **15.61%** / MDD −20.56% → **CAGR 未達 20% 門檻,部署硬門檻否定**。
     且 HO2 失敗 → 依 §4 出口 3 **明文禁止宣稱擇時 alpha**,MDD 改善絕大部分只是
     「平均持有 67.4%」的結果。
   · `預註冊_OverlayAlpha強度掃描.md`(2026-08-10):α∈{0.25,0.50,0.75} 三個強度,
     最好的 α=0.25 基準情境下 CAGR 20.93% 勉強達標,但**滑價 0.60% 壓力下掉到
     17.55%,HOα-4a 否定** → 仍無 validated 部署候選。

   ⚠ 舊 docstring 曾引用「夏普 0.95 / MDD −25.4%」—— 那是 `regime_hysteresis_lab`
     套在**舊的「價值+基本面選股」籃子**上的數字,**不是實際部署的 dual100**,
     且不含上述否定結論。已於 2026-08-10 移除,不得再引用。

   ※ 訊號本身不是雜訊(虛無對照:零訊號的常數曝險夏普 0.62 vs 訊號版 1.00)。
     ⚠ **匯率要用對版本**:0.52pp/1pp 是**滿血 α=1** 的數字;**α=0.25 是 0.265pp/1pp
     (OOS)、全期只要 0.034pp/1pp**,效率約兩倍。舊文件引用 0.52 描述 α=0.25 是低估。

   ※ **HO2 的警告仍然有效**:overlay 的回撤改善在統計上**分不出**是擇時還是「平均持有較少」
     (gap +3.11pp < 5pp),依 P-Overlay-C §4 出口 3 **不得宣稱擇時 alpha**。採用 α=0.25
     買的是「較低的平均曝險 + 較淺的回撤」,**不是**「它看得準轉折」。

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

# ---- Overlay 強度 α (2026-08-10 使用者明文豁免後採用;見檔頭) ----
# blended = 1 − α·(1 − raw_ladder)。α=0 → 裸上恆 100%;α=1 → 原始滿血階梯(已測試否定)。
# α=0.25 → 實際曝險階梯 {75%, 83.3%, 91.7%, 100%}。
# ⚠ 這個值不是最佳化出來的,是 `docs/預註冊_OverlayAlpha強度掃描.md` §1 宣告的三個離散點
#   {0.25, 0.50, 0.75} 中唯一通過 HOα-1 的那個。**要改動請先讀該預註冊 §3 的凍結規則**:
#   不得因為「試試看別的值」就改,那需要另案預註冊。
OVERLAY_ALPHA = 0.25

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


# 標籤describe市場狀態 + 對應的 α=0.25 曝險。舊值(滿倉/偏多/防禦減碼/空手)語氣過重,
# 與實際只在 75%~100% 間移動的幅度不符,已於 2026-08-10 改寫。
LADDER_LABEL = {3: "趨勢完整 · 滿倉", 2: "趨勢部分轉弱 · 略減",
                1: "僅剩長期支撐 · 減碼", 0: "趨勢全數轉弱 · 減至下限"}


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
    # α 內插後,每跌破一條 MA 只扣 α/3 = 8.3 個百分點(不是整整 1/3)
    _step = OVERLAY_ALPHA / 3.0 * 100
    if broken:
        drivers.append("跌破 " + "、".join(f"MA{L['ma']}({L['gap_pct']:+.1f}%)" for L in broken)
                       + f" → 各扣 {_step:.1f}pp 曝險,共扣 {len(broken)*_step:.1f}pp")
    if held:
        drivers.append("仍站上 " + "、".join(f"MA{L['ma']}({L['gap_pct']:+.1f}%)" for L in held)
                       + f" → 保住 {len(held)}/3 條")
    drivers.append(f"最近一次變化:MA{recent['ma']} "
                   f"{'站上' if recent['above'] else '跌破'}已 {recent['days']} 天")
    if any(L["pending"] for L in lines):
        p = [L for L in lines if L["pending"]]
        drivers.append("⏳ " + "、".join(f"MA{L['ma']}" for L in p)
                       + " 原始價已翻但遲滯確認中(需連 3 天),曝險尚未跟著改")
    return {
        "headline": f"建議曝險 {expo*100:.1f}%({LADDER_LABEL[ladder_n]})"
                    f" —— 等權指數站上 3 條均線中的 {ladder_n} 條",
        "drivers": drivers,
        # 語氣對齊實際幅度:α=0.25 只在 75%~100% 間移動,不是「全數轉現金」那種等級。
        "meaning": ("多數個股的中長期趨勢仍完整,維持滿倉。" if ladder_n == 3 else
                    "部分中期趨勢已轉弱,小幅減碼。" if ladder_n == 2 else
                    "中期趨勢已轉弱、只剩長期均線撐著,續減。" if ladder_n == 1 else
                    "長中短期趨勢全數轉弱,減至下限 75%(不歸零)。"),
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
    raw_ladder_series = ladder / 3.0                     # 原始階梯 {0, 1/3, 2/3, 1}
    # ---- α 內插(2026-08-10 採用,見檔頭 OVERLAY_ALPHA)----
    #   blended = 1 − α·(1 − raw);α=0.25 → 階梯變成 {75%, 83.3%, 91.7%, 100%}
    target_series = 1.0 - OVERLAY_ALPHA * (1.0 - raw_ladder_series)
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
        "exposure": expo,                    # 今天實際該持有的(已套 α 內插 + 限速)
        "target_exposure": tgt,              # 訊號目標(已套 α 內插,未套限速)
        "raw_ladder_exposure": float(raw_ladder_series[-1]),   # 原始階梯值(α 前),供對照
        "overlay_alpha": OVERLAY_ALPHA,
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
