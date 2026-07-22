# -*- coding: utf-8 -*-
"""build_benchmark.py — 把 TEJ 匯出的 0050 還原股價 (8 個 xlsx 分段) 固化成單一 parquet。
================================================================================
來源:TEJ「調整股價(日)-除權息調整」資料庫,已含配息再投入權值。
輸入:beat_0050/data/benchmark/0050 *.xlsx (表頭在第 2 列:年月日/收盤價(元)/報酬率％,新到舊)
輸出:beat_0050/data/benchmark/0050_tr.parquet  欄位 = date(str) / adj_close(float) / ret_pct(float)

還原收盤價 (adj_close) 已內含股息再投入 → 直接當總報酬指數,honest_backtest 不再需要
BENCH_YIELD 概略殖利率補丁。跨 8 檔還原基準一致 (已驗證交界無水位跳斷)。

用法:python beat_0050/build_benchmark.py   # 重建 parquet;xlsx 有更新時重跑
================================================================================
"""
from __future__ import annotations
import glob
import os
from pathlib import Path
import pandas as pd

BENCH_DIR = Path(__file__).resolve().parent / "data" / "benchmark"
OUT_PARQUET = BENCH_DIR / "0050_tr.parquet"


def build() -> pd.DataFrame:
    files = sorted(glob.glob(str(BENCH_DIR / "0050 *.xlsx")))
    if not files:
        raise FileNotFoundError(f"找不到 0050 xlsx 於 {BENCH_DIR}")
    parts = []
    for f in files:
        d = pd.read_excel(f, header=1)              # 第 0 列是垃圾標題,第 1 列才是表頭
        d = d.iloc[:, :3]
        d.columns = ["date", "adj_close", "ret_pct"]
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d")
    df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce")
    df["ret_pct"] = pd.to_numeric(df["ret_pct"], errors="coerce")
    df = df.dropna(subset=["date", "adj_close"]).drop_duplicates("date")
    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df.to_parquet(OUT_PARQUET, index=False)
    span = f'{df["date"].iloc[0]} → {df["date"].iloc[-1]}'
    eq = (1 + df["ret_pct"].fillna(0) / 100).prod()
    print(f"✅ 寫出 {OUT_PARQUET.name}: {len(df)} 列, {span}")
    print(f"   全期含息總報酬 {(eq-1)*100:.1f}%  (對照使用者實測 1675.9%)")
    return df


if __name__ == "__main__":
    build()
