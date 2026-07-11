# -*- coding: utf-8 -*-
"""
資料層完整度稽核 (Data-Layer Completeness Audit)  —— 對應開發日誌第12點第1項
================================================================================
目的:找出「composite 系統性偏低、分數門檻多數過不了」的資料層根因。
     不再靠猜,而是對『本機快取』逐檔、逐 as_of 量測三個關鍵訊號在 PIT 重建時
     是否 **缺漏 / 落 None / 被打成 0**:
        · 週線 MA20      (technical +15 分的來源)
        · 月營收動能      (momentum 最多 +30 分:accel / cum_yoy / streak)
        · 法人買賣天數    (whale 主體:每連買 1 天 +20 分)

全程 **0 API**(純讀 data_cache 的 Parquet + 重跑 build_pit_stockdata)。
執行:
    python audit_data_completeness.py                    # 預設池、抽 12 個月末 as_of
    python audit_data_completeness.py 2330 2454 3661     # 指定股票
    python audit_data_completeness.py --n-dates 24       # 抽更多 as_of
    python audit_data_completeness.py --modes balanced   # scores 維度稽核只看某模式
輸出:主控台摘要 + outputs/audit/ 下兩份 CSV(逐列面板 + 原始快取覆蓋)。
================================================================================
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

# --- 專案匯入(以本檔所在目錄為根)---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import data_cache
from core.backtest import cached_fetch_history, build_pit_stockdata

try:
    from core import score_store
    _HAS_SCORE_STORE = True
except Exception:
    _HAS_SCORE_STORE = False


# ------------------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------------------
def _load_pool(cli_syms):
    """股票池:命令列 > watchlist.txt > 內建分散化測試池。"""
    if cli_syms:
        return list(cli_syms)
    # 優先沿用 build_cache 的名單載入(與網頁選股同一批)
    try:
        from build_cache import _load_pool as _bc_pool  # type: ignore
        pool = _bc_pool()
        if pool:
            return [s for s, _ in pool] if isinstance(pool[0], tuple) else list(pool)
    except Exception:
        pass
    try:
        from tests.run_backtest import DIVERSIFIED_POOL
        return list(DIVERSIFIED_POOL)
    except Exception:
        return ["2330", "2454", "2317", "2408", "3661"]


def _monthly_asof(bundle, n_dates):
    """從該檔價格 date 取每月最後一個交易日,回傳最後 n 個(由舊到新)。"""
    df = getattr(bundle, "price", None)
    if df is None or "date" not in df.columns or df.empty:
        return []
    d = pd.to_datetime(df["date"], errors="coerce").dropna().sort_values()
    if d.empty:
        return []
    last_per_month = d.groupby(d.dt.to_period("M")).max()
    picks = list(last_per_month.astype("datetime64[ns]").dt.strftime("%Y-%m-%d"))
    return picks[-n_dates:] if n_dates and len(picks) > n_dates else picks


def _rev_months_available(bundle, as_of):
    """as_of 當下,月營收快取切片內可用的月份數(粗估 PIT 可算性)。"""
    rev = getattr(bundle, "revenue", None)
    if rev is None or "date" not in rev.columns:
        return 0
    sl = rev[rev["date"].astype(str) <= str(as_of)]
    return int(len(sl))


# ------------------------------------------------------------------------------
# Part A — 原始快取覆蓋(每檔每資料集:有無、列數、日期範圍、關鍵欄位 NaN)
# ------------------------------------------------------------------------------
def audit_raw_coverage(symbols):
    key_cols = {
        "price":   ["close"],
        "revenue": ["revenue", "revenue_year", "revenue_month"],
        "chip":    [],   # 欄位依 FinMind 版本而異,只看有無/列數/日期
        "per":     ["PER"],
        "income":  [],
        "balance": [],
        "cashflow": [],
        "shareholding": [],
    }
    rows = []
    for sym in symbols:
        for field, dataset in data_cache.BUNDLE_DATASETS.items():
            df = data_cache.read_cached(dataset, sym)
            rec = {"stock_id": sym, "field": field, "dataset": dataset,
                   "exists": df is not None and not getattr(df, "empty", True),
                   "rows": 0, "date_min": None, "date_max": None, "nan_flag": ""}
            if rec["exists"]:
                rec["rows"] = len(df)
                if "date" in df.columns:
                    dd = pd.to_datetime(df["date"], errors="coerce")
                    rec["date_min"] = str(dd.min().date()) if dd.notna().any() else None
                    rec["date_max"] = str(dd.max().date()) if dd.notna().any() else None
                bad = []
                for c in key_cols.get(field, []):
                    if c not in df.columns:
                        bad.append(f"{c}:缺欄")
                    else:
                        r = pd.to_numeric(df[c], errors="coerce").isna().mean()
                        if r > 0.1:
                            bad.append(f"{c}:NaN{r*100:.0f}%")
                rec["nan_flag"] = "; ".join(bad)
            rows.append(rec)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------
# Part B — PIT 訊號面板(逐檔 × 逐 as_of 重建,量測三訊號缺漏)
# ------------------------------------------------------------------------------
def audit_pit_panel(symbols, n_dates):
    rows = []
    for sym in symbols:
        bundle = cached_fetch_history(sym, refresh=False)
        asofs = _monthly_asof(bundle, n_dates)
        if not asofs:
            print(f"  [{sym}] ⚠️ 無價格快取,略過(先跑 build_cache.py)")
            continue
        for as_of in asofs:
            stock = build_pit_stockdata(bundle, as_of)
            if stock is None:
                rows.append({"stock_id": sym, "as_of": as_of, "pit_ok": False})
                continue
            wma = getattr(stock, "weekly_ma20", None)
            cur = getattr(stock, "current_price", None)
            accel = getattr(stock, "revenue_accel", None)
            cum = getattr(stock, "revenue_cum_yoy", None)
            streak = getattr(stock, "revenue_growth_streak", None)
            tbuy = getattr(stock, "institutional_buy_days", None)
            fbuy = getattr(stock, "foreign_buy_days", None)
            rows.append({
                "stock_id": sym, "as_of": as_of, "pit_ok": True,
                # 週線 MA:是否 <=0(丟分)或 == 現價(fallback/退化)
                "weekly_ma20": wma,
                "wma_dead": (wma is None) or (wma <= 0) or (cur is not None and abs((wma or 0) - cur) < 1e-6),
                # 月營收動能三欄是否落 None
                "rev_accel_none": accel is None,
                "rev_cum_none": cum is None,
                "rev_streak0": (streak or 0) == 0,
                "rev_months": _rev_months_available(bundle, as_of),
                # 法人天數
                "trust_buy_days": tbuy or 0,
                "foreign_buy_days": fbuy or 0,
                "whale_days0": ((tbuy or 0) == 0 and (fbuy or 0) == 0),
            })
    return pd.DataFrame(rows)


def summarize_panel(panel):
    if panel.empty:
        print("  (面板為空)")
        return
    ok = panel[panel["pit_ok"] == True].copy()
    n = len(ok)
    total = len(panel)
    print(f"\n面板列數:{total}(可重建 {n} / 資料不足 {total-n})")
    if n == 0:
        return

    def pct(col):
        return f"{ok[col].mean()*100:5.1f}%"

    print("\n── 三訊號『缺漏率』(越高代表該訊號在 PIT 常常無效 → 系統性丟分)──")
    print(f"  週線MA 退化 (<=0 或 =現價 → 技術面丟15分)   : {pct('wma_dead')}")
    print(f"  營收加速度 accel = None (動能丟最多14分)      : {pct('rev_accel_none')}")
    print(f"  營收累計YoY cum = None (動能丟最多10分)       : {pct('rev_cum_none')}")
    print(f"  營收連續成長月數 streak = 0                    : {pct('rev_streak0')}")
    print(f"  法人買賣『雙 0 天』(whale 主體歸零)          : {pct('whale_days0')}")

    print(f"\n  as_of 當下可用月營收月數:中位 {ok['rev_months'].median():.0f}"
          f"  最少 {ok['rev_months'].min():.0f}  最多 {ok['rev_months'].max():.0f}")
    print(f"  法人連買天數 (trust/foreign) 中位:"
          f"{ok['trust_buy_days'].median():.0f} / {ok['foreign_buy_days'].median():.0f}")

    print("\n── 各檔『缺漏最嚴重』排行(依三訊號綜合缺漏率)──")
    g = ok.groupby("stock_id").agg(
        wma_dead=("wma_dead", "mean"),
        accel_none=("rev_accel_none", "mean"),
        whale0=("whale_days0", "mean"),
        rev_months=("rev_months", "median"),
    )
    g["缺漏分"] = (g["wma_dead"] + g["accel_none"] + g["whale0"]) / 3
    g = g.sort_values("缺漏分", ascending=False)
    for sym, r in g.head(12).iterrows():
        print(f"  {sym}  缺漏分 {r['缺漏分']*100:4.0f}%  | 週線退化 {r['wma_dead']*100:3.0f}%"
              f"  accel None {r['accel_none']*100:3.0f}%  法人雙0 {r['whale0']*100:3.0f}%"
              f"  月營收月數 {r['rev_months']:.0f}")


# ------------------------------------------------------------------------------
# Part C — Scores 快取維度稽核(0 API,讀已落地的五維分)
# ------------------------------------------------------------------------------
def audit_scores(modes):
    if not _HAS_SCORE_STORE or not score_store._has_scores():
        print("  (尚未建 scores 快取,或 score_store 不可用 → 跳過 Part C)")
        return
    dims = ["fundamental", "valuation", "technical", "momentum", "whale", "composite", "data_confidence"]
    for mode in modes:
        try:
            df = score_store.latest_scores(mode=mode)
        except Exception as e:
            print(f"  [{mode}] 讀取失敗:{e}")
            continue
        if df is None or df.empty:
            print(f"  [{mode}] 無資料")
            continue
        print(f"\n── mode = {mode}  (n={len(df)}) ──")
        for d in dims:
            if d not in df.columns:
                continue
            s = pd.to_numeric(df[d], errors="coerce")
            zero = (s == 0).mean() * 100
            print(f"  {d:16s} 中位 {s.median():5.1f}  平均 {s.mean():5.1f}"
                  f"  min {s.min():5.1f}  =0 比例 {zero:4.0f}%")
        # 找出把 composite 拖低的維度:各維中位數 vs composite 中位數
        comp_med = pd.to_numeric(df["composite"], errors="coerce").median()
        laggards = []
        for d in ["fundamental", "valuation", "technical", "momentum", "whale"]:
            if d in df.columns:
                m = pd.to_numeric(df[d], errors="coerce").median()
                if m < comp_med:
                    laggards.append((d, m))
        laggards.sort(key=lambda x: x[1])
        if laggards:
            txt = ", ".join(f"{d}({m:.0f})" for d, m in laggards)
            print(f"  → 低於 composite 中位({comp_med:.0f})的維度(拖累主嫌):{txt}")


# ------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="資料層完整度稽核 (0 API)")
    ap.add_argument("symbols", nargs="*", help="股票代號(不給 → watchlist / 預設池)")
    ap.add_argument("--n-dates", type=int, default=12, help="每檔抽樣的月末 as_of 數(預設12)")
    ap.add_argument("--modes", nargs="*", default=["balanced"], help="Part C 稽核的模式")
    args = ap.parse_args()

    symbols = _load_pool(args.symbols)
    print("=" * 78)
    print(f"資料層完整度稽核  |  {datetime.now():%Y-%m-%d %H:%M}  |  快取:{data_cache.CACHE_DIR}")
    print(f"股票池 {len(symbols)} 檔  |  每檔抽 {args.n_dates} 個月末 as_of  |  0 API")
    print("=" * 78)

    print("\n### Part A — 原始快取覆蓋 ###")
    cov = audit_raw_coverage(symbols)
    miss = cov[(~cov["exists"]) | (cov["nan_flag"] != "")]
    if miss.empty:
        print("  ✅ 所有資料集皆存在、關鍵欄位無明顯 NaN。")
    else:
        print("  ⚠️ 有缺漏/NaN 的資料集:")
        for _, r in miss.iterrows():
            flag = "不存在" if not r["exists"] else r["nan_flag"]
            print(f"    {r['stock_id']:6s} {r['field']:12s} {flag}")

    print("\n### Part B — PIT 三訊號缺漏面板 ###")
    panel = audit_pit_panel(symbols, args.n_dates)
    summarize_panel(panel)

    print("\n### Part C — Scores 五維維度稽核 ###")
    audit_scores(args.modes)

    # 落地 CSV
    outdir = os.path.join("outputs", "audit")
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    cov.to_csv(os.path.join(outdir, f"raw_coverage_{stamp}.csv"), index=False, encoding="utf-8-sig")
    if not panel.empty:
        panel.to_csv(os.path.join(outdir, f"pit_panel_{stamp}.csv"), index=False, encoding="utf-8-sig")
    print(f"\n📄 明細已存 {outdir}/(raw_coverage_*.csv, pit_panel_*.csv)")
    print("\n判讀指引:")
    print("  · 某訊號『缺漏率』偏高 → 回對應來源修:")
    print("      週線MA → technical_analysis.calculate_weekly_ma20 / build_pit_stockdata L243")
    print("      月營收 → data_provider._calc_rev_momentum + backtest._slice(無公告時差,注意 look-ahead)")
    print("      法人   → data_provider._net_buy_lots / 連買天數計法 + chip 快取覆蓋")
    print("  · Part C 若某維中位遠低於 composite,且 Part B 對應訊號缺漏率高 → 即為擠 α 的破口。")


if __name__ == "__main__":
    main()
