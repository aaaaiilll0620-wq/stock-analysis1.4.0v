"""
§12 全市場擴池規劃書 Phase 2 — TEJ 全市場粗篩規則回溯驗證
================================================================================
用途:用 tej_importer.py 批次匯入的全市場歷史 (tej_cache/price_valuation +
      tej_cache/institutional_flow,1952 檔、2019-2026) 驗證候選粗篩規則本身
      有沒有排序力:

        PE 歷史分位低 (value) + 近期動能轉強 (momentum) + 法人近期淨買超為正 (chip)

      方法論比照 scripts/factor_experiments.py:同時看「2023-2025 全期」與
      「2022 空頭段」兩個窗口的 Rank IC / 市場中性多空價差,避免只配適多頭。
      通過門檻與 v4.4 同一套標準:全期與 2022 空頭都不能明顯變差。

      0 API,純讀本機 tej_cache Parquet (DuckDB)。這支腳本只做規則驗證,
      不進生產環境的每日 PIT 評分管線 (TEJ 資料無 PIT 保證,見 tej_importer.py)。

因子定義:
  · value:PE 歷史分位 (own-history expanding percentile,同 core/data_provider.py
    _percentile_rank 邏輯:值 <= 0 排除、樣本 < 60 天視為無效),分數 = 100 - 分位
    (分位越低代表越便宜,轉成分數後越高越便宜)。
  · momentum:近 20 個交易日報酬率 (%)。
  · chip:外資+投信+自營商近 20 個交易日淨買超股數合計。
  三個因子在同一天的全市場橫斷面各自轉成百分位 (0-100) 後,composite = 三者平均
  (等權;--weights 可自訂)。

用法:
  python scripts/tej_universe_screen_validation.py
  python scripts/tej_universe_screen_validation.py --holding 10   # 改持有期
================================================================================
"""
from __future__ import annotations

import os
import sys
import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

TEJ_CACHE_DIR = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
PERIODS = [
    ("2023-2025", "2023-01-01", "2025-12-31"),
    ("2022空頭", "2022-01-01", "2022-12-31"),
    ("2019-2021(樣本外)", "2019-01-01", "2021-12-31"),
]
MIN_PCT_SAMPLES = 60          # 同 core/data_provider.py._percentile_rank
PE_HISTORY_START = "2019-01-01"   # tej_cache 資料起點,PE 分位用「起點至 as_of」的 expanding window

# 財報/月營收「所屬期間」→「市場實際能看到」的公告延遲,避免用未來才公佈的數字驗證 (look-ahead)。
QUARTERLY_ANNOUNCE_LAG_DAYS = 45   # 季報約股期結束後1.5個月公佈
MONTHLY_ANNOUNCE_LAG_DAYS = 10     # 月營收約次月10日前公佈


# ------------------------------------------------------------------------------
# 1) 讀本機 TEJ 全市場快取
# ------------------------------------------------------------------------------
def load_market(cache_dir: Path = TEJ_CACHE_DIR):
    con = duckdb.connect()
    price = con.execute(f"""
        SELECT stock_id, date, close, PER_TEJ, Trading_Volume
        FROM read_parquet('{cache_dir}/price_valuation/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    chip = con.execute(f"""
        SELECT stock_id, date, foreign_net, trust_net, dealer_net
        FROM read_parquet('{cache_dir}/institutional_flow/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    fund = con.execute(f"""
        SELECT stock_id, date, eps, roe_after_tax, net_income, operating_income
        FROM read_parquet('{cache_dir}/fundamentals_quarterly/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    rev = con.execute(f"""
        SELECT stock_id, date, revenue_yoy_pct
        FROM read_parquet('{cache_dir}/revenue_growth/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    con.close()

    # date 欄位是「所屬期間」(季報=季末月第一天,月營收=當月第一天),
    # 換算成「市場實際能看到」的 known_date = 期間月底 + 公告延遲,供 merge_asof 用。
    fund["known_date"] = (pd.to_datetime(fund["date"]) + pd.offsets.MonthEnd(0)
                           + pd.Timedelta(days=QUARTERLY_ANNOUNCE_LAG_DAYS))
    rev["known_date"] = (pd.to_datetime(rev["date"]) + pd.offsets.MonthEnd(0)
                          + pd.Timedelta(days=MONTHLY_ANNOUNCE_LAG_DAYS))
    return price, chip, fund, rev


def rebalance_dates(all_dates: list, start: str, end: str, freq: str = "M") -> list:
    """比照 core/backtest.py Backtester._rebalance_dates:每期最後一個交易日。"""
    dates = sorted(d for d in set(all_dates) if start <= d <= end)
    if not dates:
        return []
    s = pd.Series(pd.to_datetime(dates), index=pd.to_datetime(dates))
    key = s.dt.to_period("W" if freq.upper().startswith("W") else "M")
    picked = s.groupby(key).max()
    return [d.strftime("%Y-%m-%d") for d in picked]


# ------------------------------------------------------------------------------
# PIT 安全合併:財報/月營收用 known_date (公告後才算數) 對齊到股價日期,backward-asof
# (as_of 當天只能看到「已公佈」的最新一筆,不能偷看未來財報)。
# ------------------------------------------------------------------------------
def attach_pit_fundamentals(g: pd.DataFrame, fund_g, rev_g) -> pd.DataFrame:
    gg = g.copy()
    gg["_dt"] = pd.to_datetime(gg["date"])

    if fund_g is not None and not fund_g.empty:
        fg = fund_g.sort_values("known_date")[["known_date", "eps", "roe_after_tax",
                                                "net_income", "operating_income"]].copy()
        # 多季獲利穩定度:最近 4 個已公佈單季中 EPS>0 的季數 (0-4,不足 4 季為 NaN)
        fg["eps_pos_q4"] = (fg["eps"] > 0).rolling(4, min_periods=4).sum()
        gg = pd.merge_asof(gg, fg, left_on="_dt", right_on="known_date", direction="backward")
        gg = gg.drop(columns=["known_date"])
    else:
        gg["eps"] = np.nan
        gg["roe_after_tax"] = np.nan
        gg["net_income"] = np.nan
        gg["operating_income"] = np.nan
        gg["eps_pos_q4"] = np.nan

    if rev_g is not None and not rev_g.empty:
        rg = rev_g.sort_values("known_date")[["known_date", "revenue_yoy_pct"]].copy()
        # 營收趨勢平滑:最近 3 個已公佈月份的 YoY 均值 (單月太抖)
        rg["rev_yoy_3m"] = rg["revenue_yoy_pct"].rolling(3, min_periods=3).mean()
        gg = pd.merge_asof(gg, rg, left_on="_dt", right_on="known_date", direction="backward")
        gg = gg.drop(columns=["known_date"])
    else:
        gg["revenue_yoy_pct"] = np.nan
        gg["rev_yoy_3m"] = np.nan

    return gg.drop(columns=["_dt"]).reset_index(drop=True)


# ------------------------------------------------------------------------------
# 2) 逐股計算三因子 + 品質欄位 + 前瞻報酬 (只在 rebalance 日評估)
# ------------------------------------------------------------------------------
def build_observations(price: pd.DataFrame, chip: pd.DataFrame, dates: list,
                        holding_days: int, momentum_window: int = 20,
                        chip_window: int = 20, chip_mode: str = "turnover",
                        fund: pd.DataFrame = None, rev: pd.DataFrame = None,
                        quality_filter: str = "none") -> list:
    obs = []
    chip["net_total"] = chip[["foreign_net", "trust_net", "dealer_net"]].sum(axis=1)
    chip_by_stock = {sid: g.sort_values("date").reset_index(drop=True)
                      for sid, g in chip.groupby("stock_id")}
    fund_by_stock = {sid: g for sid, g in fund.groupby("stock_id")} if fund is not None else {}
    rev_by_stock = {sid: g for sid, g in rev.groupby("stock_id")} if rev is not None else {}
    date_set = set(dates)

    for sid, g in price.groupby("stock_id"):
        g = g.sort_values("date").reset_index(drop=True)
        g["close"] = pd.to_numeric(g["close"], errors="coerce")
        g["PER_TEJ"] = pd.to_numeric(g["PER_TEJ"], errors="coerce")
        g["Trading_Volume"] = pd.to_numeric(g["Trading_Volume"], errors="coerce")
        g = attach_pit_fundamentals(g, fund_by_stock.get(sid), rev_by_stock.get(sid))
        # 52 週高點 (240 交易日 rolling max,至少半年樣本才算數)
        g["_roll_max240"] = g["close"].rolling(240, min_periods=120).max()
        idx_by_date = {d: i for i, d in enumerate(g["date"])}
        vol_by_date = dict(zip(g["date"], g["Trading_Volume"]))

        c = chip_by_stock.get(sid)
        c_by_date = None
        if c is not None:
            c["net_total"] = pd.to_numeric(c["net_total"], errors="coerce")
            c["volume"] = c["date"].map(vol_by_date)   # 從股價資料對齊同日成交量,供市值中性化
            c_by_date = {d: i for i, d in enumerate(c["date"])}

        for as_of in g["date"]:
            if as_of not in date_set:
                continue
            i0 = idx_by_date[as_of]

            # --- momentum: 近 momentum_window 交易日報酬率 ---
            if i0 < momentum_window:
                continue
            p0, pN = g.loc[i0, "close"], g.loc[i0 - momentum_window, "close"]
            if not pN or pd.isna(p0) or pd.isna(pN):
                continue
            momentum = float((p0 - pN) / pN * 100.0)

            # --- 長週期動能 (60/120 日) 與 52 週高點接近度 (粗篩層候選因子) ---
            def _mom(win):
                if i0 < win:
                    return None
                pw = g.loc[i0 - win, "close"]
                return None if (pd.isna(pw) or not pw) else float((p0 - pw) / pw * 100.0)
            mom60, mom120 = _mom(60), _mom(120)
            hi = g.loc[i0, "_roll_max240"]
            high52_prox = None if (pd.isna(hi) or not hi) else float(p0 / hi * 100.0)

            # --- value: PE 歷史分位 (expanding,起點至 as_of,排除 <=0,樣本 >=60) ---
            hist = g.loc[:i0, "PER_TEJ"].dropna()
            hist = hist[hist > 0]
            cur_pe = g.loc[i0, "PER_TEJ"]
            if pd.isna(cur_pe) or cur_pe <= 0 or len(hist) < MIN_PCT_SAMPLES:
                continue
            pe_pct = float((hist < cur_pe).mean() * 100.0)
            value = 100.0 - pe_pct

            # --- chip: 近 chip_window 交易日三大法人淨買超,
            #     turnover 模式除以同期總成交量做市值中性化 (避免大型股絕對量偏誤) ---
            if c_by_date is None or as_of not in c_by_date:
                continue
            ci0 = c_by_date[as_of]
            if ci0 < chip_window - 1:
                continue
            window = c.loc[ci0 - (chip_window - 1):ci0]
            net_sum = float(window["net_total"].sum())
            if chip_mode == "turnover":
                vol_sum = float(window["volume"].sum())
                if not vol_sum or pd.isna(vol_sum):
                    continue
                chip_flow = net_sum / vol_sum
            else:
                chip_flow = net_sum

            # --- 品質欄位 (PIT-safe,已用 known_date 對齊,見 attach_pit_fundamentals) ---
            eps = g.loc[i0, "eps"]
            roe = g.loc[i0, "roe_after_tax"]
            rev_yoy = g.loc[i0, "revenue_yoy_pct"]
            op_inc = g.loc[i0, "operating_income"]
            net_inc = g.loc[i0, "net_income"]
            eps_pos_q4 = g.loc[i0, "eps_pos_q4"]
            rev_yoy_3m = g.loc[i0, "rev_yoy_3m"]

            if quality_filter == "eps_positive":
                # 保守處理:未知 (尚未有任何已公佈財報,如 2019 初期) 一律視為不合格,
                # 不讓「資料還沒出來」被誤判成「安全」。
                if pd.isna(eps) or eps <= 0:
                    continue
            elif quality_filter == "no_fake_earnings":
                # 假性便宜偵測:EPS>0 但單季營業利益<=0 → 帳面獲利全靠業外,
                # PE 假性偏低 (價值陷阱假設的原型)。營業利益 NaN 一律放行:
                # 金融股損益表無標準營業利益科目,濾掉等於誤殺整個板塊。
                if not pd.isna(eps) and not pd.isna(op_inc) and eps > 0 and op_inc <= 0:
                    continue

            # --- 前瞻報酬 (holding_days 交易日後收盤) ---
            i1 = i0 + holding_days
            if i1 >= len(g):
                continue
            p1 = g.loc[i1, "close"]
            if pd.isna(p1) or not p0:
                continue
            fwd = float((p1 - p0) / p0 * 100.0)

            obs.append({"as_of": as_of, "stock_id": sid,
                        "value": value, "momentum": momentum, "chip": chip_flow, "fwd": fwd,
                        "eps": None if pd.isna(eps) else float(eps),
                        "roe": None if pd.isna(roe) else float(roe),
                        "revenue_yoy": None if pd.isna(rev_yoy) else float(rev_yoy),
                        "op_income": None if pd.isna(op_inc) else float(op_inc),
                        "net_income": None if pd.isna(net_inc) else float(net_inc),
                        "mom60": mom60, "mom120": mom120, "high52_prox": high52_prox,
                        "eps_pos_q4": None if pd.isna(eps_pos_q4) else float(eps_pos_q4),
                        "rev_yoy_3m": None if pd.isna(rev_yoy_3m) else float(rev_yoy_3m)})
    return obs


# ------------------------------------------------------------------------------
# 3) 同日橫斷面百分位化 + composite
# ------------------------------------------------------------------------------
def add_cross_sectional_pct_and_composite(rows: list, weights=None, value_cap_pct=None) -> list:
    """value_cap_pct:設定後,value_pct 超過此百分位的極端便宜端會對稱折返懲罰
    (診斷發現 decile 10=最便宜10% 三期都是負超額報酬,疑似價值陷阱)。"""
    w = weights or {"value": 1 / 3, "momentum": 1 / 3, "chip": 1 / 3}
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["as_of"]].append(r)
    for _, items in by_date.items():
        for factor in ("value", "momentum", "chip"):
            vals = pd.Series([it[factor] for it in items])
            pct = vals.rank(pct=True) * 100.0
            for it, p in zip(items, pct):
                it[f"{factor}_pct"] = float(p)
        if value_cap_pct is not None:
            for it in items:
                vp = it["value_pct"]
                if vp > value_cap_pct:
                    it["value_pct"] = 2 * value_cap_pct - vp   # 超過 cap 的極端便宜端,對稱折返懲罰
        for it in items:
            it["composite"] = sum(it[f"{f}_pct"] * w.get(f, 0.0) for f in ("value", "momentum", "chip"))
    return rows


# ------------------------------------------------------------------------------
# 4) 指標 (與 scripts/factor_experiments.py 同一套定義)
# ------------------------------------------------------------------------------
def rank_ic(rows, key):
    by = defaultdict(list)
    for r in rows:
        by[r["as_of"]].append((r[key], r["fwd"]))
    ics = []
    for _, items in by.items():
        if len(items) < 4:
            continue
        xs = pd.Series([x for x, _ in items]).rank()
        ys = pd.Series([y for _, y in items]).rank()
        if xs.std() == 0 or ys.std() == 0:
            continue
        ics.append(float(xs.corr(ys)))
    return float(np.mean(ics)) if ics else float("nan")


def spread(rows, key, q=1 / 3, min_per_side=5):
    by = defaultdict(list)
    for r in rows:
        by[r["as_of"]].append((r[key], r["fwd"]))
    sps = []
    for _, items in by.items():
        k = int(len(items) * q)
        if k < min_per_side:
            continue
        items.sort(key=lambda x: x[0])
        sps.append(float(np.mean([f for _, f in items[-k:]]) - np.mean([f for _, f in items[:k]])))
    return float(np.mean(sps)) if len(sps) >= 3 else float("nan")


def decile_returns(rows, key, n=10):
    """依 key 把每期橫斷面切成 n 等分,回傳每個桶 (1=最低值...n=最高值) 的
    平均『市場中性超額報酬』(該股當天 fwd - 當天全市場平均 fwd) 與樣本數,
    逐期算完再平均。市場中性化是必要的,否則不同月份的大盤漲跌會蓋過因子本身的效果
    (同 spread()/rank_ic() 的邏輯:只看同一天內的相對排序,不看跨天的絕對水準)。"""
    by = defaultdict(list)
    for r in rows:
        by[r["as_of"]].append((r[key], r["fwd"]))
    bucket_rets = defaultdict(list)
    bucket_counts = defaultdict(list)
    for _, items in by.items():
        if len(items) < n * 2:
            continue
        mkt_mean = float(np.mean([f for _, f in items]))
        items = [(k, f - mkt_mean) for k, f in items]
        items.sort(key=lambda x: x[0])
        edges = np.linspace(0, len(items), n + 1).astype(int)
        for b in range(n):
            chunk = items[edges[b]:edges[b + 1]]
            if not chunk:
                continue
            bucket_rets[b + 1].append(float(np.mean([f for _, f in chunk])))
            bucket_counts[b + 1].append(len(chunk))
    return {b: (float(np.mean(bucket_rets[b])), int(np.mean(bucket_counts[b])))
            for b in sorted(bucket_rets)}


def fmt(x):
    return "n/a" if np.isnan(x) else f"{x:+.3f}"


# ------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="TEJ 全市場粗篩規則回溯驗證 (0 API)")
    ap.add_argument("--holding", type=int, default=20, help="持有天數 (交易日,預設20)")
    ap.add_argument("--momentum-window", type=int, default=20, help="動能回看天數 (交易日,預設20)")
    ap.add_argument("--chip-window", type=int, default=20, help="法人流向回看天數 (交易日,預設20)")
    ap.add_argument("--chip-mode", choices=["turnover", "raw"], default="turnover",
                     help="turnover=淨買超÷同期成交量(市值中性,預設);raw=原始股數加總")
    ap.add_argument("--cache-dir", default=str(TEJ_CACHE_DIR))
    ap.add_argument("--weights", default=None,
                     help="自訂 composite 權重,例如 'value=0.5,momentum=0.5,chip=0' (預設等權三因子)")
    ap.add_argument("--diagnose", choices=["value", "momentum", "chip"], default=None,
                     help="改印該因子的十分位後續報酬拆解,不印 IC/多空總表")
    ap.add_argument("--value-cap-pct", type=float, default=None,
                     help="value_pct 超過此百分位的極端便宜端對稱折返懲罰 (例如 80);預設不啟用")
    ap.add_argument("--quality-filter", choices=["none", "eps_positive", "no_fake_earnings"],
                     default="none",
                     help="eps_positive=排除當下已知最新單季EPS<=0或未知的股票(PIT-safe);"
                          "no_fake_earnings=排除EPS>0但單季營業利益<=0的假性便宜股(業外墊高EPS,"
                          "營業利益NaN如金融股一律放行);預設不濾")
    ap.add_argument("--dump-obs", default=None, metavar="PATH",
                     help="把三期原始觀測值 (含品質欄位,未過濾未百分位化) 輸出成 Parquet 後結束,"
                          "供離線快速迭代過濾實驗,不用每次重跑逐股迴圈")
    ap.add_argument("--dump-start", default=None, help="搭配 --dump-obs:自訂單一區間起日 (取代三期)")
    ap.add_argument("--dump-end", default=None, help="搭配 --dump-obs:自訂單一區間迄日")
    args = ap.parse_args()
    cache_dir = Path(args.cache_dir)
    weights = None
    if args.weights:
        weights = {}
        for kv in args.weights.split(","):
            k, v = kv.split("=")
            weights[k.strip()] = float(v)

    print("讀取 tej_cache 全市場快取 (DuckDB)…")
    price, chip, fund, rev = load_market(cache_dir)
    print(f"  price_valuation: {len(price)} 列 / {price['stock_id'].nunique()} 檔")
    print(f"  institutional_flow: {len(chip)} 列 / {chip['stock_id'].nunique()} 檔")
    print(f"  fundamentals_quarterly: {len(fund)} 列 / {fund['stock_id'].nunique()} 檔")
    print(f"  revenue_growth: {len(rev)} 列 / {rev['stock_id'].nunique()} 檔")

    all_dates = price["date"].unique().tolist()

    if args.dump_obs:
        frames = []
        dump_periods = ([("custom", args.dump_start, args.dump_end)]
                        if args.dump_start and args.dump_end else PERIODS)
        for pname, start, end in dump_periods:
            dates = rebalance_dates(all_dates, start, end, "M")
            obs = build_observations(price, chip, dates, args.holding, args.momentum_window,
                                      args.chip_window, args.chip_mode,
                                      fund=fund, rev=rev, quality_filter="none")
            df = pd.DataFrame(obs)
            df["period"] = pname
            frames.append(df)
        out = pd.concat(frames, ignore_index=True)
        out.to_parquet(args.dump_obs, index=False)
        print(f"已輸出 {len(out)} 列觀測至 {args.dump_obs}")
        return

    if args.diagnose:
        key = f"{args.diagnose}_pct"
        print(f"\n{args.diagnose} 因子十分位拆解 (decile 1=因子值最低...10=最高;單位:% 市場中性超額報酬,已扣當天全市場平均)")
        for pname, start, end in PERIODS:
            dates = rebalance_dates(all_dates, start, end, "M")
            obs = build_observations(price, chip, dates, args.holding, args.momentum_window,
                                      args.chip_window, args.chip_mode,
                                      fund=fund, rev=rev, quality_filter=args.quality_filter)
            obs = add_cross_sectional_pct_and_composite(obs, weights=weights, value_cap_pct=args.value_cap_pct)
            buckets = decile_returns(obs, key)
            print(f"\n[{pname}] (觀測數 {len(obs)})")
            print("  decile: " + "  ".join(f"{b:>7}" for b in range(1, 11)))
            print("  fwd%:   " + "  ".join(f"{buckets.get(b, (float('nan'), 0))[0]:>7.3f}" for b in range(1, 11)))
            print("  n:      " + "  ".join(f"{buckets.get(b, (float('nan'), 0))[1]:>7d}" for b in range(1, 11)))
        return

    print(f"\n{'期間':<12}{'觀測數':>10}{'value IC':>10}{'moment IC':>10}{'chip IC':>10}{'綜合IC':>10}"
          f"{'value多空':>10}{'moment多空':>11}{'chip多空':>10}{'綜合多空':>10}")
    print("-" * 100)

    results = {}
    for pname, start, end in PERIODS:
        dates = rebalance_dates(all_dates, start, end, "M")
        obs = build_observations(price, chip, dates, args.holding, args.momentum_window,
                                  args.chip_window, args.chip_mode,
                                  fund=fund, rev=rev, quality_filter=args.quality_filter)
        obs = add_cross_sectional_pct_and_composite(obs, weights=weights, value_cap_pct=args.value_cap_pct)
        results[pname] = obs
        n = len(obs)
        print(f"{pname:<12}{n:>10}"
              f"{fmt(rank_ic(obs, 'value_pct')):>10}{fmt(rank_ic(obs, 'momentum_pct')):>10}"
              f"{fmt(rank_ic(obs, 'chip_pct')):>10}{fmt(rank_ic(obs, 'composite')):>10}"
              f"{fmt(spread(obs, 'value_pct')):>10}{fmt(spread(obs, 'momentum_pct')):>11}"
              f"{fmt(spread(obs, 'chip_pct')):>10}{fmt(spread(obs, 'composite')):>10}")

    print("\n判讀:通過門檻同 v4.4——全期(2023-2025)與 2022 空頭段的『綜合IC/綜合多空』都要 > 0"
          "\n     且 2022 段不能比全期明顯變差。若某單因子長期 <= 0,可考慮從 composite 拿掉該因子重測。")


if __name__ == "__main__":
    main()
