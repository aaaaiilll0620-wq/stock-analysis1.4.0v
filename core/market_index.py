# -*- coding: utf-8 -*-
"""market_index.py — 大盤指數 / 量能 / 漲跌家數 的資料層 (市場燈號的**參考欄位**)。
================================================================================
定位:**只供顯示,不驅動訊號。** 市場燈號的曝險一律由 core/regime_exposure.py 的
**全市場等權指數**決定;本模組提供的加權指數與成交金額,是給使用者對照用的市場實況,
避免把「等權跌破 MA」誤讀成「大盤跌破 MA」(兩者可以同時一個站上、一個跌破)。

為什麼加權指數不進訊號:2026-07 的輸入序列頭對頭(docs/預註冊_RegimeInputLab.md)在
同一股利基礎下實測 —— 等權夏普 1.00 ≫ 加權價格 0.75 > 0050 原始 0.72,且加權與 0050
的曝險 86.5% 重疊、相關 0.916(同一個資訊)。加入加權的組合一律劣於單用等權。

資料源 (種子 + 增量,與 price_valuation 同一套設計):
  · 種子:FinMind TaiwanStockPrice(TAIEX) 一次性回補 2004-01 起 → 只在本機跑一次
  · 增量:TWSE rwd MI_INDEX,**收集器每日已經在抓的同一個 response**,零額外 API 成本
    (成交金額取「總計(1~15)」列,實測與 FinMind Trading_money 逐筆完全一致)

輸出:~/market_cache/taiex_daily.parquet
      欄位 = date / close / chg_pct / turnover / volume / adv / dec / unch
================================================================================
"""
from __future__ import annotations
import os
from pathlib import Path

import pandas as pd

MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
TAIEX_PARQUET = MARKET_CACHE / "taiex_daily.parquet"
COLS = ["date", "close", "chg_pct", "turnover", "volume", "adv", "dec", "unch"]


def _num(s):
    return pd.to_numeric(str(s).replace(",", "").replace("+", "").strip(), errors="coerce")


# ---------------------------------------------------------------- 種子 (一次性)
def seed_from_finmind(start: str = "2004-01-01") -> Path:
    """一次性回補歷史 (需 FINMIND_TOKEN)。已有檔案時只補缺口,不覆寫既有列。"""
    from dotenv import load_dotenv
    from FinMind.data import DataLoader
    load_dotenv()
    dl = DataLoader()
    dl.login_by_token(api_token=os.getenv("FINMIND_TOKEN"))
    d = dl.taiwan_stock_daily(stock_id="TAIEX", start_date=start,
                              end_date=pd.Timestamp.now().strftime("%Y-%m-%d"))
    df = pd.DataFrame({
        "date": d["date"].astype(str),
        "close": pd.to_numeric(d["close"], errors="coerce"),
        "chg_pct": pd.to_numeric(d["spread"], errors="coerce") / (
            pd.to_numeric(d["close"], errors="coerce")
            - pd.to_numeric(d["spread"], errors="coerce")) * 100,
        "turnover": pd.to_numeric(d["Trading_money"], errors="coerce"),
        "volume": pd.to_numeric(d["Trading_Volume"], errors="coerce"),
        "adv": pd.NA, "dec": pd.NA, "unch": pd.NA,      # 家數僅增量端有,歷史留空
    })
    return _upsert(df.dropna(subset=["close"]))


# ---------------------------------------------------------------- 增量 (每日)
def parse_mi_index(mi: dict) -> pd.DataFrame:
    """從 TWSE rwd MI_INDEX 的 response 取出當日大盤三件事。
    收集器已為個股快照抓過同一個 response → 直接複用,不另外打 API。"""
    date_ = f'{mi["date"][:4]}-{mi["date"][4:6]}-{mi["date"][6:]}'
    rec = {"date": date_, "close": None, "chg_pct": None,
           "turnover": None, "volume": None, "adv": None, "dec": None, "unch": None}

    for t in mi.get("tables", []):
        f = t.get("fields") or []
        data = t.get("data") or []
        if "指數" in f and "收盤指數" in f:                     # 價格指數表
            for row in data:
                if str(row[0]).strip() == "發行量加權股價指數":
                    rec["close"] = _num(row[1])
                    rec["chg_pct"] = _num(row[f.index("漲跌百分比(%)")])
                    break
        elif "成交金額(元)" in f:                                # 大盤統計資訊
            for row in data:
                if str(row[0]).strip().startswith("總計"):       # 與 FinMind 逐筆一致
                    rec["turnover"] = _num(row[1])
                    rec["volume"] = _num(row[2])
                    break
        elif "類型" in f and "股票" in f:                        # 漲跌證券數合計
            for row in data:
                k = str(row[0]).strip()
                v = _num(str(row[f.index("股票")]).split("(")[0])
                if k.startswith("上漲"):
                    rec["adv"] = v
                elif k.startswith("下跌"):
                    rec["dec"] = v
                elif k.startswith("持平"):
                    rec["unch"] = v
    if rec["close"] is None:
        raise ValueError("MI_INDEX 找不到發行量加權股價指數")
    return pd.DataFrame([rec])[COLS]


def _upsert(rows: pd.DataFrame) -> Path:
    """按 date 冪等 upsert:既有日期的**已有值一律保留**,只補空欄 (種子無漲跌家數,
    由增量端補上),新日期直接追加。"""
    rows = rows[COLS].dropna(subset=["date", "close"])
    if TAIEX_PARQUET.exists():
        prev = pd.read_parquet(TAIEX_PARQUET)
        dup = rows[rows["date"].isin(set(prev["date"]))]
        if not dup.empty:                       # 既有日期:只把 prev 的空欄填起來
            prev = (prev.set_index("date")
                        .combine_first(dup.set_index("date"))
                        .reset_index())[COLS]
        rows = rows[~rows["date"].isin(set(prev["date"]))]
        rows = prev if rows.empty else pd.concat([prev, rows], ignore_index=True)
    TAIEX_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    tmp = TAIEX_PARQUET.with_suffix(".parquet.tmp")
    rows.sort_values("date").reset_index(drop=True).to_parquet(tmp, index=False)
    os.replace(tmp, TAIEX_PARQUET)
    return TAIEX_PARQUET


def update_from_mi_index(mi: dict) -> Path:
    return _upsert(parse_mi_index(mi))


# ---------------------------------------------------------------- 顯示層
def get_context() -> dict | None:
    """回傳市場燈號頁要顯示的大盤實況;讀不到資料回 None(頁面自動略過此區塊)。"""
    if not TAIEX_PARQUET.exists():
        return None
    d = pd.read_parquet(TAIEX_PARQUET).sort_values("date").reset_index(drop=True)
    if len(d) < 200:
        return None
    for w in (50, 100, 200):
        d[f"ma{w}"] = d["close"].rolling(w, min_periods=w).mean()
    d["amt20"] = d["turnover"].rolling(20, min_periods=20).mean()
    d["amt60"] = d["turnover"].rolling(60, min_periods=60).mean()
    r = d.iloc[-1]
    lines = [{"ma": w, "above": bool(r["close"] >= r[f"ma{w}"]),
              "gap_pct": float(r["close"] / r[f"ma{w}"] - 1) * 100} for w in (50, 100, 200)]
    adv, dec = r.get("adv"), r.get("dec")
    return {
        "as_of": str(r["date"]),
        "close": float(r["close"]),
        "chg_pct": float(r["chg_pct"]) if pd.notna(r["chg_pct"]) else None,
        "lines": lines,
        "turnover": float(r["turnover"]) if pd.notna(r["turnover"]) else None,
        "amt_vs_60d": (float(r["turnover"] / r["amt60"]) if pd.notna(r["amt60"]) else None),
        "amt20_vs_60": (float(r["amt20"] / r["amt60"]) if pd.notna(r["amt60"]) else None),
        "adv": int(adv) if pd.notna(adv) else None,
        "dec": int(dec) if pd.notna(dec) else None,
    }


if __name__ == "__main__":
    p = seed_from_finmind()
    d = pd.read_parquet(p)
    print(f"✅ {p}: {len(d)} 列, {d['date'].iloc[0]} → {d['date'].iloc[-1]}")
