"""全市場「產業內估值位階」參考表建構器 (§15-G 產業中性化 → 生產估值重修,0 FinMind API)
================================================================================
背景:TEJ 全市場驗證 (DevLog §15-G) 證實 value 因子的正解是「產業內排名」——
      decile 10 陷阱三期 -0.45/-0.17/-0.42 → -0.07/-0.04/-0.42,IC 三期全升。
      生產池只有幾十檔,產業分組太小,必須拿「全市場」當排名母體 → 本腳本
      用 TEJ 歷史種子 ∪ TWSE/TPEx 每日快照 (同 universe_screen_daily 的資料面)
      預算出每檔每日的產業內估值位階,生產端/實驗端只要查表。

構造 (完全鏡射 scripts/tej_universe_screen_validation.py 的定義):
  pe_hist_pct:個股自身歷史 PE expanding 分位 (含當日、只取 >0、樣本 >= 60,
               當日 PE 無效 → NaN)
  value = 100 - pe_hist_pct (越高越便宜)
  value_mkt_pct:value 在當日全市場的百分位 (0-100,越高越便宜)
  value_ind_pct:value 在當日「TEJ 產業」內的百分位;分組 < 5 檔退回 value_mkt_pct
                 (驗證勝出組態:tej_ind 層,分組>=5 覆蓋率 93.9%)

輸出:market_cache/industry_value_ref.parquet (stock_id, date, 上述欄位)
用法:
  python scripts/build_industry_value_ref.py                 # 全量重建 (~2-4 分鐘)
  python scripts/build_industry_value_ref.py --since 2022-01-01   # 只算某日起 (省時)
================================================================================
"""
import os
import sys
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
SNAP_DIR = MARKET_CACHE / "price_valuation_daily"
OUT = MARKET_CACHE / "industry_value_ref.parquet"

MIN_PCT_SAMPLES = 60
MIN_GROUP = 5
# v4.5 生產估值是用「2019 起的 expanding 窗」過閘門的;TEJ 補匯 2004-2018 歷史後,
# 若不錨定起點,分位分佈會整批改變 → 預設鎖 2019,研究用途才改。
PE_HISTORY_START = "2019-01-01"


def load_pe_union(con) -> pd.DataFrame:
    tej_max = con.execute(f"""
        SELECT MAX(date) FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
    """).fetchone()[0]
    has_snap = SNAP_DIR.exists() and any(SNAP_DIR.glob("*.parquet"))
    snap_sql = f"""
        UNION ALL BY NAME
        SELECT stock_id, date, PER_TSE
        FROM read_parquet('{SNAP_DIR}/*.parquet', union_by_name=true)
        WHERE date > '{tej_max}'""" if has_snap else ""
    return con.execute(f"""
        SELECT stock_id, date, PER_TSE
        FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        {snap_sql}
        ORDER BY stock_id, date
    """).df()


def expanding_pe_pct(pe: np.ndarray) -> np.ndarray:
    """對整條序列算 expanding 分位 (含當日,只取 >0,樣本>=60;無效日 NaN)。
    向量化:有效值間兩兩比較 + 沿時間 cumsum。"""
    out = np.full(len(pe), np.nan)
    valid_idx = np.where(~np.isnan(pe) & (pe > 0))[0]
    if len(valid_idx) < MIN_PCT_SAMPLES:
        return out
    x = pe[valid_idx]
    less = (x[:, None] < x[None, :]).cumsum(axis=0)     # less[i,j] = #(x[:i+1] < x[j])
    k = np.arange(1, len(x) + 1)
    pct = less.diagonal() / k * 100.0                    # 第 j 個有效日的 expanding 分位
    pct[: MIN_PCT_SAMPLES - 1] = np.nan                  # 樣本不足期間無效
    out[valid_idx] = pct
    return out


def main():
    ap = argparse.ArgumentParser(description="全市場產業內估值位階參考表 (0 FinMind API)")
    ap.add_argument("--since", default=None, help="只輸出此日期(含)之後的列 (計算仍用全歷史)")
    ap.add_argument("--pe-history-start", default=PE_HISTORY_START,
                     help=f"expanding 窗起點 (預設 {PE_HISTORY_START},與 v4.5 閘門驗證一致;"
                          "研究全歷史請設 2004-01-01)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    con = duckdb.connect()
    t0 = time.time()
    px = load_pe_union(con)
    px = px[px["date"] >= args.pe_history_start].reset_index(drop=True)
    ind = pd.read_parquet(TEJ_CACHE / "industry_map.parquet")[["stock_id", "tej_ind_name"]]
    print(f"載入 {px['stock_id'].nunique()} 檔 × {len(px)} 列 ({time.time()-t0:.0f}s)")

    t0 = time.time()
    px["pe_hist_pct"] = (px.groupby("stock_id")["PER_TSE"]
                            .transform(lambda s: expanding_pe_pct(s.to_numpy())))
    print(f"expanding PE 分位完成 ({time.time()-t0:.0f}s)")

    px["value"] = 100.0 - px["pe_hist_pct"]
    if args.since:
        px = px[px["date"] >= args.since]
    px = px.merge(ind, on="stock_id", how="left")

    t0 = time.time()
    valid = px["value"].notna()
    v = px[valid]
    mkt_pct = v.groupby("date")["value"].rank(pct=True) * 100.0
    ind_pct = v.groupby(["date", "tej_ind_name"])["value"].rank(pct=True) * 100.0
    grp_size = v.groupby(["date", "tej_ind_name"])["value"].transform("size")
    px.loc[valid, "value_mkt_pct"] = mkt_pct
    px.loc[valid, "value_ind_pct"] = ind_pct.where(grp_size >= MIN_GROUP, mkt_pct)
    print(f"橫斷面排名完成 ({time.time()-t0:.0f}s)")

    out_cols = ["stock_id", "date", "pe_hist_pct", "value_mkt_pct", "value_ind_pct"]
    out_df = px.loc[px["pe_hist_pct"].notna(), out_cols]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.tmp")
    out_df.to_parquet(tmp, index=False)
    os.replace(tmp, out_path)
    print(f"已輸出 {len(out_df)} 列 → {out_path}"
          f" (日期 {out_df['date'].min()} ~ {out_df['date'].max()})")


if __name__ == "__main__":
    main()
