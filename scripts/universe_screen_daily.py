"""全市場每日粗篩 L1+L2 (§15 定案配方,0 FinMind API)
================================================================================
資料 = TEJ 歷史種子 (tej_cache/price_valuation,~2026-07-14) ∪ 官方每日快照
       (market_cache/price_valuation_daily,由 market_snapshot_collector.py 累積),
       接縫已實測:PER_TSE 與官方 PEratio 100% 一致。

粗篩配方 (docs/開發日誌_DevLog_135557.md §15-D 定案):
  L0 因子可評估:當日 PE 有效且自身歷史樣本 >= 60 (TSE 慣例虧損股 PE 空白 → 排除;
                驗證母體隱含此條件,不加會混入 ~490 檔驗證未覆蓋的股票)
  L1 可投資性:20 日均成交金額 >= 10M NTD,且上市滿一年 (種子起點就存在者視為老股)
  L2 陷阱排除:PE 歷史分位 value_pct > 90 (全市場橫斷面) 且 最新已知單月營收 YoY <= 0
              (營收未知者保守視為 <=0;PE 分位用個股自身 expanding 歷史,>0、樣本>=60)
  預期產出 ~700-810 檔候選池 → 下游精算評分 (未接線)
  --include-no-pe 可保留 L0 排除者 (虧損/新股,驗證未覆蓋,自行斟酌)

用法:
  python scripts/universe_screen_daily.py                # 以最新可用交易日跑粗篩
  python scripts/universe_screen_daily.py --adv-floor 20000000
輸出:outputs/universe_pool/pool_{date}.csv + stdout 摘要
================================================================================
"""
import os
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
SNAP_DIR = MARKET_CACHE / "price_valuation_daily"

MIN_PCT_SAMPLES = 60
DATA_START_CUTOFF = "2019-01-10"   # 種子起點就存在的股票不是新 IPO
REVENUE_LAG_DAYS = 10              # 月營收約次月 10 日前公佈


def load_union(con) -> pd.DataFrame:
    tej_max = con.execute(f"""
        SELECT MAX(date) FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
    """).fetchone()[0]
    snap_glob = str(SNAP_DIR / "*.parquet")
    has_snap = SNAP_DIR.exists() and any(SNAP_DIR.glob("*.parquet"))
    snap_sql = f"""
        UNION ALL BY NAME
        SELECT stock_id, date, close, Trading_Volume, PER_TSE
        FROM read_parquet('{snap_glob}', union_by_name=true)
        WHERE date > '{tej_max}'""" if has_snap else ""
    df = con.execute(f"""
        SELECT stock_id, date, close, Trading_Volume, PER_TSE
        FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        {snap_sql}
        ORDER BY stock_id, date
    """).df()
    return df


def latest_revenue_yoy(con, as_of: str) -> pd.DataFrame:
    """最新『已公佈』單月營收 YoY:期間月底 + 10 天 <= as_of 才算已知 (PIT-safe)。"""
    rev = con.execute(f"""
        SELECT stock_id, date, revenue_yoy_pct
        FROM read_parquet('{TEJ_CACHE}/revenue_growth/*.parquet', union_by_name=true)
    """).df()
    rev["known"] = (pd.to_datetime(rev["date"]) + pd.offsets.MonthEnd(0)
                     + pd.Timedelta(days=REVENUE_LAG_DAYS))
    rev = rev[rev["known"] <= pd.Timestamp(as_of)]
    rev = rev.sort_values("date").groupby("stock_id").tail(1)
    return rev[["stock_id", "revenue_yoy_pct", "date"]].rename(columns={"date": "rev_month"})


def main():
    ap = argparse.ArgumentParser(description="全市場每日粗篩 L1+L2 (0 FinMind API)")
    ap.add_argument("--adv-floor", type=float, default=10_000_000, help="20日均成交金額下限 (NTD)")
    ap.add_argument("--include-no-pe", action="store_true",
                     help="保留 PE 無效股 (虧損/新股;預設排除,與驗證母體一致)")
    ap.add_argument("--out-dir", default=str(Path(project_root) / "outputs" / "universe_pool"))
    args = ap.parse_args()

    con = duckdb.connect()
    px = load_union(con)
    as_of = px["date"].max()
    print(f"資料截至 {as_of},{px['stock_id'].nunique()} 檔,{len(px)} 列 (TEJ 種子 ∪ 官方快照)")

    g = px.groupby("stock_id")
    latest = px[px["date"] == as_of].set_index("stock_id")

    # --- L1:20 日均成交金額 + 上市滿一年 ---
    px["dollar_vol"] = px["close"] * px["Trading_Volume"]
    adv20 = g["dollar_vol"].apply(lambda s: s.tail(20).mean())
    first_date = g["date"].min()
    listed_ok = (first_date <= DATA_START_CUTOFF) | (
        (pd.Timestamp(as_of) - pd.to_datetime(first_date)).dt.days >= 365)

    # --- L2:PE 自身歷史 expanding 分位 → 全市場橫斷面 value_pct ---
    def pe_hist_pct(s: pd.Series) -> float:
        """同 tej_universe_screen_validation.py:當日 PE 無效 (空白=虧損/或<=0) 即無分位;
        expanding 歷史含當日、只取 >0、樣本 >= 60。"""
        cur = s.iloc[-1]
        if pd.isna(cur) or cur <= 0:
            return np.nan
        hist = s.dropna()
        hist = hist[hist > 0]
        if len(hist) < MIN_PCT_SAMPLES:
            return np.nan
        return float((hist < cur).mean() * 100.0)

    pe_pct = g["PER_TSE"].apply(pe_hist_pct)          # 低 = 歷史上便宜
    value = 100.0 - pe_pct                             # 高 = 便宜 (同驗證腳本)
    value_pct = value.rank(pct=True) * 100.0           # 全市場橫斷面

    rev = latest_revenue_yoy(con, as_of).set_index("stock_id")

    pool = pd.DataFrame({
        "close": latest["close"], "adv20": adv20, "listed_ok": listed_ok,
        "pe_hist_pct": pe_pct, "value_pct": value_pct,
        "revenue_yoy": rev["revenue_yoy_pct"], "rev_month": rev["rev_month"],
    })
    n_all = len(pool)
    pool = pool[latest["close"].notna()]                        # 今日有報價
    l0 = pool if args.include_no_pe else pool[pool["value_pct"].notna()]
    l1 = l0[(l0["adv20"] >= args.adv_floor) & l0["listed_ok"]]
    trap = (l1["value_pct"] > 90) & ~(l1["revenue_yoy"] > 0)
    l2 = l1[~trap.fillna(False)]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"pool_{as_of}.csv"
    l2.sort_values("adv20", ascending=False).to_csv(out, encoding="utf-8-sig")
    print(f"全市場 {n_all} → 今日有報價 {len(pool)} → L0 因子可評估 {len(l0)}"
          f" → L1 可投資性 {len(l1)} → L2 陷阱排除 -{int(trap.fillna(False).sum())}"
          f" → 候選池 {len(l2)} 檔")
    print(f"已輸出 {out}")


if __name__ == "__main__":
    main()
