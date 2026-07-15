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

第二段 (池內 shortlist,0 FinMind API):
  五因子 = 產業內估值位階 + 20日動能 + 20日法人買賣超/成交量
           + 52週高點接近度 (突破) + 營收加速度 (最新YoY − 近3月均YoY)。
  池內各因子取前 --shortlist-union-pct (預設15%) 聯集 → shortlist_{date}.csv
  (~400 檔,composite 排序供由高往低瀏覽)。
  依據 (§16-C + 但書2三連測,雙視野 20/60 日皆驗):5F vs 3F 召回 +8~9pp、
  2022 超額改善 25-30%、月留存 +8pp,三期無一變差;突破與營收加速是唯二
  2022 單因子為正的選股訊號。視野解讀:因子在 60 日 (季度) 視野的空頭傷害
  約為 20 日視野的一半,shortlist 建議以波段視野使用。
  注意:緊縮池 2022 空頭段超額整體仍偏負,shortlist 是「分流參考」不是投組。

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
PE_HISTORY_START = "2019-01-01"    # PE expanding 窗起點,與 §15/v4.5 閘門驗證一致
                                    # (TEJ 補匯 2004-2018 後不鎖起點會改變分位分佈)
DATA_START_CUTOFF = "2019-01-10"   # 2019 起點就存在的股票不是新 IPO (補匯後改看實際首日)
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
    ap.add_argument("--shortlist-union-pct", type=float, default=15.0,
                     help="第二段聯集:各因子取池內前 N%% (預設 15)")
    ap.add_argument("--out-dir", default=str(Path(project_root) / "outputs" / "universe_pool"))
    args = ap.parse_args()

    con = duckdb.connect()
    px = load_union(con)
    as_of = px["date"].max()
    print(f"資料截至 {as_of},{px['stock_id'].nunique()} 檔,{len(px)} 列 (TEJ 種子 ∪ 官方快照)")

    # --- Level 0 regime 警示旗 (§16-E):全市場等權指數 < 其 MA200 → 空頭。
    #     2005-2026 十二個 episode 實證:空頭月 shortlist 超額 -0.14 vs 多頭月 +0.25,
    #     空頭時參考性降低 (配方「切換」的預註冊假設已被樣本外否決,只掛旗不切換)。
    ret = px.sort_values(["stock_id", "date"]).groupby("stock_id")["close"].pct_change()
    daily = (pd.DataFrame({"date": px["date"], "ret": ret})
             .query("ret.notna() and abs(ret) < 0.5")
             .groupby("date")["ret"].mean().sort_index())
    ew_index = (1 + daily).cumprod()
    bear_regime = bool(ew_index.iloc[-1] < ew_index.rolling(200).mean().iloc[-1])
    print(f"市場 regime (等權指數 vs MA200): {'⚠️ 空頭——shortlist 歷史上此狀態超額為負,參考性降低' if bear_regime else '多頭'}")

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

    pe_grp = px[px["date"] >= PE_HISTORY_START].groupby("stock_id")
    pe_pct = pe_grp["PER_TSE"].apply(pe_hist_pct)     # 低 = 歷史上便宜 (2019 起 expanding 窗)
    value = 100.0 - pe_pct                             # 高 = 便宜 (同驗證腳本)
    value_pct = value.rank(pct=True) * 100.0           # 全市場橫斷面

    rev = latest_revenue_yoy(con, as_of).set_index("stock_id")

    pool = pd.DataFrame({
        "close": latest["close"], "adv20": adv20, "listed_ok": listed_ok,
        "pe_hist_pct": pe_pct, "value_pct": value_pct,
        "revenue_yoy": rev["revenue_yoy_pct"], "rev_month": rev["rev_month"],
    })
    pool["bear_regime"] = bear_regime
    n_all = len(pool)
    quoted = latest["close"].notna().reindex(pool.index, fill_value=False)
    pool = pool[quoted]                                         # 今日有報價 (下市股自然出局)
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

    # --- 第二段:池內三因子聯集 shortlist ---
    vind = con.execute(f"""
        SELECT stock_id, value_ind_pct
        FROM read_parquet('{MARKET_CACHE}/industry_value_ref.parquet')
        WHERE date = '{as_of}'
    """).df().set_index("stock_id")["value_ind_pct"]

    tej_chip_max = con.execute(f"""
        SELECT MAX(date) FROM read_parquet('{TEJ_CACHE}/institutional_flow/*.parquet', union_by_name=true)
    """).fetchone()[0]
    chip_snap_dir = MARKET_CACHE / "institutional_flow_daily"
    chip_sql = f"""
        UNION ALL BY NAME
        SELECT stock_id, date, foreign_net, trust_net, dealer_net
        FROM read_parquet('{chip_snap_dir}/*.parquet', union_by_name=true)
        WHERE date > '{tej_chip_max}'""" if (chip_snap_dir.exists()
                                              and any(chip_snap_dir.glob("*.parquet"))) else ""
    chip = con.execute(f"""
        SELECT stock_id, date, foreign_net, trust_net, dealer_net
        FROM read_parquet('{TEJ_CACHE}/institutional_flow/*.parquet', union_by_name=true)
        {chip_sql}
        ORDER BY stock_id, date
    """).df()
    chip["net_total"] = chip[["foreign_net", "trust_net", "dealer_net"]].sum(axis=1)
    chip = chip[chip["date"] <= as_of]
    net20 = chip.groupby("stock_id")["net_total"].apply(lambda s: s.tail(20).sum())
    vol20 = g["Trading_Volume"].apply(lambda s: s.tail(20).sum())

    def mom20(s: pd.Series) -> float:
        s = s.dropna()
        if len(s) < 21 or not s.iloc[-21]:
            return np.nan
        return float((s.iloc[-1] - s.iloc[-21]) / s.iloc[-21] * 100.0)

    def high52_prox(s: pd.Series) -> float:
        """收盤價 / 近240交易日最高收盤 ×100 (至少120樣本;越高=越接近52週高)。"""
        s = s.dropna().tail(240)
        if len(s) < 120 or not s.max():
            return np.nan
        return float(s.iloc[-1] / s.max() * 100.0)

    # 營收加速度:最新已知單月 YoY − 近3個已知月份平均 YoY (PIT: 月底+10天才算已知)
    rev_all = con.execute(f"""
        SELECT stock_id, date, revenue_yoy_pct
        FROM read_parquet('{TEJ_CACHE}/revenue_growth/*.parquet', union_by_name=true)
    """).df()
    rev_all["known"] = (pd.to_datetime(rev_all["date"]) + pd.offsets.MonthEnd(0)
                         + pd.Timedelta(days=REVENUE_LAG_DAYS))
    rev_all = rev_all[rev_all["known"] <= pd.Timestamp(as_of)].sort_values("date")

    def rev_accel(s: pd.Series) -> float:
        s = s.dropna().tail(3)
        if len(s) < 3:
            return np.nan
        return float(s.iloc[-1] - s.mean())

    FACTORS = ("value_ind_pct", "momentum20", "chip20_turnover", "high52_prox", "rev_accel")
    sl = l2.copy()
    sl["value_ind_pct"] = vind.reindex(sl.index)
    sl["momentum20"] = g["close"].apply(mom20).reindex(sl.index)
    sl["chip20_turnover"] = (net20 / vol20.replace(0, np.nan)).reindex(sl.index)
    sl["high52_prox"] = g["close"].apply(high52_prox).reindex(sl.index)
    sl["rev_accel"] = (rev_all.groupby("stock_id")["revenue_yoy_pct"]
                          .apply(rev_accel).reindex(sl.index))
    for f in FACTORS:
        sl[f"{f}_pool_pct"] = sl[f].rank(pct=True) * 100.0
    thr = 100.0 - args.shortlist_union_pct
    union = np.logical_or.reduce([(sl[f"{f}_pool_pct"] > thr).to_numpy() for f in FACTORS])
    sl["composite"] = sl[[f"{f}_pool_pct" for f in FACTORS]].mean(axis=1)
    shortlist = sl[union].sort_values("composite", ascending=False)
    out2 = out_dir / f"shortlist_{as_of}.csv"
    shortlist.to_csv(out2, encoding="utf-8-sig")
    print(f"第二段聯集 (各因子前 {args.shortlist_union_pct:.0f}%): shortlist {len(shortlist)} 檔"
          f" → {out2}")


if __name__ == "__main__":
    main()
