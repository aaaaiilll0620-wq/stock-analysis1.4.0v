"""全市場粗篩歷史重放器 (0 API):對過去每個交易日重放 L0-L2 + 五因子 shortlist,
================================================================================
補生 outputs/universe_pool/{pool,shortlist}_{date}.csv,讓「連續在榜」等跨日統計
從第一天就有真實歷史。與 universe_screen_daily.py 同一套規則;PE 分位不重算,
直接讀 industry_value_ref.parquet (生產同款 2019 錨點),其餘因子 rolling 向量化,
全期一次算完 (~2-3 分鐘)。已存在的日期檔案跳過 (不覆蓋 live 產出)。

用法:
  python scripts/universe_screen_backfill.py                     # 補 2026-01-02 起
  python scripts/universe_screen_backfill.py --start 2025-07-01
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
CHIP_SNAP = MARKET_CACHE / "institutional_flow_daily"
REVENUE_LAG_DAYS = 10
DATA_START_CUTOFF = "2019-01-10"


def union_sql(con, base_glob: str, snap_glob: str, cols: str, snap_cols: str = None) -> pd.DataFrame:
    """snap_cols:快照側欄位表 (快照缺 stock_name 等欄時用 NULL 補齊);預設同 cols。"""
    tej_max = con.execute(f"SELECT MAX(date) FROM read_parquet('{base_glob}', union_by_name=true)").fetchone()[0]
    has_snap = Path(snap_glob).parent.exists() and any(Path(snap_glob).parent.glob("*.parquet"))
    extra = (f"UNION ALL BY NAME SELECT {snap_cols or cols} FROM read_parquet('{snap_glob}', union_by_name=true)"
             f" WHERE date > '{tej_max}'") if has_snap else ""
    return con.execute(f"SELECT {cols} FROM read_parquet('{base_glob}', union_by_name=true) {extra}"
                       f" ORDER BY stock_id, date").df()


def main():
    ap = argparse.ArgumentParser(description="粗篩歷史重放 (0 API)")
    ap.add_argument("--start", default="2026-01-02")
    ap.add_argument("--end", default=None)
    ap.add_argument("--adv-floor", type=float, default=10_000_000)
    ap.add_argument("--shortlist-union-pct", type=float, default=15.0)
    ap.add_argument("--out-dir", default=str(Path(project_root) / "outputs" / "universe_pool"))
    args = ap.parse_args()

    con = duckdb.connect()
    px = union_sql(con, f"{TEJ_CACHE}/price_valuation/*.parquet", f"{SNAP_DIR}/*.parquet",
                   "stock_id, date, stock_name, close, Trading_Volume",
                   snap_cols="stock_id, date, NULL AS stock_name, close, Trading_Volume")
    px["stock_name"] = px.groupby("stock_id", sort=False)["stock_name"].ffill()
    px = px[px["close"].notna()].reset_index(drop=True)   # 只留有報價列 (交易日基準的 rolling)

    g = px.groupby("stock_id", sort=False)
    px["adv20"] = g.apply(lambda d: (d["close"] * d["Trading_Volume"]).rolling(20).mean(),
                           include_groups=False).reset_index(level=0, drop=True)
    px["vol20"] = g["Trading_Volume"].transform(lambda s: s.rolling(20).sum())
    px["momentum20"] = g["close"].transform(lambda s: s.pct_change(20) * 100)
    px["high52_prox"] = g["close"].transform(lambda s: s / s.rolling(240, min_periods=120).max() * 100)
    first = g["date"].transform("min")
    px["listed_ok"] = ((first <= DATA_START_CUTOFF) |
                        ((pd.to_datetime(px["date"]) - pd.to_datetime(first)).dt.days >= 365))

    chip = union_sql(con, f"{TEJ_CACHE}/institutional_flow/*.parquet", f"{CHIP_SNAP}/*.parquet",
                     "stock_id, date, foreign_net, trust_net, dealer_net")
    chip["net_total"] = chip[["foreign_net", "trust_net", "dealer_net"]].sum(axis=1)
    chip["net20"] = (chip.groupby("stock_id", sort=False)["net_total"]
                        .transform(lambda s: s.rolling(20).sum()))
    px = px.merge(chip[["stock_id", "date", "net20"]], on=["stock_id", "date"], how="left")
    px["chip20_turnover"] = px["net20"] / px["vol20"].replace(0, np.nan)

    ref = pd.read_parquet(MARKET_CACHE / "industry_value_ref.parquet")
    px = px.merge(ref, on=["stock_id", "date"], how="left")   # pe_hist_pct/value_mkt_pct/value_ind_pct

    rev = con.execute(f"""
        SELECT stock_id, date, revenue_yoy_pct
        FROM read_parquet('{TEJ_CACHE}/revenue_growth/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    rev["known"] = (pd.to_datetime(rev["date"]) + pd.offsets.MonthEnd(0)
                     + pd.Timedelta(days=REVENUE_LAG_DAYS))
    rev["rev_accel"] = rev["revenue_yoy_pct"] - (rev.groupby("stock_id", sort=False)["revenue_yoy_pct"]
                                                    .transform(lambda s: s.rolling(3, min_periods=3).mean()))
    px["_dt"] = pd.to_datetime(px["date"])
    px = px.sort_values("_dt", kind="stable")
    rev = rev.sort_values("known", kind="stable")
    px = pd.merge_asof(px, rev[["stock_id", "known", "revenue_yoy_pct", "rev_accel"]],
                       left_on="_dt", right_on="known", by="stock_id", direction="backward")

    ind = pd.read_parquet(TEJ_CACHE / "industry_map.parquet",
                           columns=["stock_id", "tej_ind_name"]).rename(columns={"tej_ind_name": "industry"})
    px = px.merge(ind, on="stock_id", how="left")

    end = args.end or px["date"].max()
    px = px[(px["date"] >= args.start) & (px["date"] <= end)]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    FACTORS = ("value_ind_pct", "momentum20", "chip20_turnover", "high52_prox", "rev_accel")
    thr = 100.0 - args.shortlist_union_pct
    written = skipped = 0
    for as_of, d in px.groupby("date"):
        out_pool = out_dir / f"pool_{as_of}.csv"
        out_sl = out_dir / f"shortlist_{as_of}.csv"
        if out_pool.exists() and out_sl.exists():
            skipped += 1
            continue
        d = d[d["value_mkt_pct"].notna()].copy()                       # L0 因子可評估
        d = d[(d["adv20"] >= args.adv_floor) & d["listed_ok"]]          # L1 可投資性
        trap = (d["value_mkt_pct"] > 90) & ~(d["revenue_yoy_pct"] > 0)  # L2 陷阱排除
        d = d[~trap.fillna(False)]
        if len(d) < 50:
            continue
        for f in FACTORS:
            d[f"{f}_pool_pct"] = d[f].rank(pct=True) * 100.0
        union = np.logical_or.reduce([(d[f"{f}_pool_pct"] > thr).to_numpy() for f in FACTORS])
        d["composite"] = d[[f"{f}_pool_pct" for f in FACTORS]].mean(axis=1)
        cols = ["stock_id", "stock_name", "industry", "close", "adv20",
                "pe_hist_pct", "value_mkt_pct", "revenue_yoy_pct",
                *FACTORS, *(f"{f}_pool_pct" for f in FACTORS), "composite"]
        base = d[cols].rename(columns={"stock_name": "name", "value_mkt_pct": "value_pct",
                                        "revenue_yoy_pct": "revenue_yoy"}).set_index("stock_id")
        if not out_pool.exists():
            base.sort_values("adv20", ascending=False).to_csv(out_pool, encoding="utf-8-sig")
        if not out_sl.exists():
            (base[union].sort_values("composite", ascending=False)
                 .to_csv(out_sl, encoding="utf-8-sig"))
        written += 1
    print(f"重放完成:寫入 {written} 個交易日,跳過既有 {skipped} 日 → {out_dir}")


if __name__ == "__main__":
    main()
