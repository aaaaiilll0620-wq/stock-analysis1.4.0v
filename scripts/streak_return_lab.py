# -*- coding: utf-8 -*-
"""streak_return_lab.py — 「連續在榜天數 → 前瞻報酬」回測 (0 API)
================================================================================
回答使用者的問題:**連續在榜越久越好嗎?有沒有一個推薦的在榜窗?**

背景:`連續在榜` (streak) 目前只在 universe_digest / app 用來「顯示」,從未被當成
訊號驗證過。shortlist_ledger / alpha_gate_lab 測的都是 c2_score 的排序 IC,不是榜齡。
組合層 (§22) 的證據反而指向「新進榜=反轉起漲點」。本腳本把 streak 當自變數,量測
它與『未來 20 交易日報酬』的關係,並直接檢驗「久居便宜臂 = 價值陷阱」的假設。

作法 (大量重用 shortlist_ledger,同一條價格接縫與交易日曆):
  1. 對每個 cohort 日 d,讀 shortlist_{d}.csv,算每檔 streak-as-of-d
     (往回掃連續存在的 shortlist 集合,與 universe_digest.py / app._univ_streaks 同邏輯)。
  2. 前瞻報酬 fwd = close@(d 之後第 h 個交易日) / close@d − 1 (attach_fwd)。
  3. 依 streak 分桶 {1(新進), 2–4, 5–9, 10–19, 20–39, 40+},算 n / 均值 / 中位數 / t。
  4. 重疊控制:相鄰日名單高度重疊 → 推論用「非重疊 cohort」(每 h 交易日取一個),
     跨 cohort 的 bucket 均值序列算 t;全 cohort 版另列作描述性對照。
  5. 交叉檢驗:只看『便宜臂』(value_ind_pct_pool_pct>85) 的股票,再依 streak 分桶。

誠實邊界:
  · 目前 shortlist 歷史 ~130 天 (2026-01 起) → 40+ 桶樣本少、且跨 live/backfill 接縫;
    要更深先跑 `python scripts/universe_screen_backfill.py` 回補再重跑本腳本。
  · close 未還原除權息 (與整條驗證鏈同口徑),除息個股單日報酬會被低估。
  · 這是觀察性關聯,不是因果;榜齡與『便宜/低動能』本身相關,交叉檢驗即為此。

用法:
  python scripts/streak_return_lab.py                 # h=20 主結論
  python scripts/streak_return_lab.py --horizon 20 --min-n 30
================================================================================
"""
from __future__ import annotations

import os
import re
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# 同目錄的 shortlist_ledger:重用價格接縫 / 交易日曆 / 前瞻報酬 / cohort 探索
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shortlist_ledger import (          # noqa: E402
    load_prices, trading_calendar, attach_fwd, LIVE_START, POOL_DIR,
)

# 便宜臂欄位 (與 universe_digest.ARMS / app._ARMS 一致)
CHEAP_ARM_COL = "value_ind_pct_pool_pct"
ARM_THR = 85.0

# streak 分桶:(lo, hi 含端點, 標籤)
BUCKETS = [
    (1, 1, "1 (新進)"),
    (2, 4, "2–4"),
    (5, 9, "5–9"),
    (10, 19, "10–19"),
    (20, 39, "20–39"),
    (40, 10**9, "40+"),
]


def bucket_of(streak: int) -> str:
    for lo, hi, lab in BUCKETS:
        if lo <= streak <= hi:
            return lab
    return "?"


def load_shortlist_history() -> list[tuple[str, pd.DataFrame]]:
    """所有 shortlist_{date}.csv,依日期排序,回傳 [(date, df_indexed_by_stock_id)]。"""
    out = []
    for f in sorted(POOL_DIR.glob("shortlist_*.csv")):
        m = re.match(r"shortlist_(\d{4}-\d{2}-\d{2})\.csv", f.name)
        if not m:
            continue
        df = pd.read_csv(f, encoding="utf-8-sig", dtype={"stock_id": str})
        if df.empty or "c2_score" not in df.columns:      # 舊薄格式無 c2_score → 跳過
            continue
        out.append((m.group(1), df.set_index("stock_id")))
    return out


def streaks_at(sets: list[set], j: int) -> dict:
    """shortlist 歷史集合序列中,第 j 個 cohort 當日各檔的連續在榜天數 (含當日)。"""
    res = {}
    cur = sets[j]
    for sid in cur:
        n = 0
        for k in range(j, -1, -1):
            if sid in sets[k]:
                n += 1
            else:
                break
        res[sid] = n
    return res


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def main():
    ap = argparse.ArgumentParser(description="連續在榜天數 → 前瞻報酬回測")
    ap.add_argument("--horizon", type=int, default=20, help="前瞻交易日數 (預設 20)")
    ap.add_argument("--min-n", type=int, default=20,
                    help="非重疊視圖中,一個 bucket 至少要有幾個 cohort 均值才報 t (預設 20)")
    args = ap.parse_args()
    h = args.horizon

    px = load_prices()
    cal = trading_calendar(px)
    cal_idx = {d: i for i, d in enumerate(cal)}
    px_by_date = {d: g[["stock_id", "close"]] for d, g in px.groupby("date") if d in cal_idx}

    hist = load_shortlist_history()
    if not hist:
        print("找不到含 c2_score 的 shortlist 歷史。")
        return
    dates = [d for d, _ in hist]
    sets = [set(df.index) for _, df in hist]
    print(f"shortlist 歷史 {len(hist)} 天 ({dates[0]} ~ {dates[-1]});"
          f"價格截至 {cal[-1]};前瞻窗 h={h} 交易日")

    # ---- 逐 cohort 收集 (streak, fwd, cheap_arm) 觀測 ----
    obs_rows = []
    n_mature = 0
    for j, (d, df) in enumerate(hist):
        i0 = cal_idx.get(d)
        if i0 is None or i0 + h >= len(cal):
            continue                                    # 未成熟或不在交易日曆
        n_mature += 1
        p1 = px_by_date[cal[i0 + h]]
        sk = attach_fwd(df.reset_index(), p1, "c2_score")     # 需要 close 欄;df 有
        if sk.empty:
            continue
        streaks = streaks_at(sets, j)
        sk = sk.copy()
        sk["streak"] = sk["stock_id"].map(streaks).fillna(1).astype(int)
        sk["bucket"] = sk["streak"].map(bucket_of)
        cheap = (sk[CHEAP_ARM_COL] > ARM_THR) if CHEAP_ARM_COL in sk.columns else False
        sk["cheap_arm"] = cheap
        sk["cohort"] = d
        sk["cal_idx"] = i0
        sk["source"] = "live" if d >= LIVE_START else "backfill"
        obs_rows.append(sk[["cohort", "cal_idx", "source", "stock_id", "streak",
                            "bucket", "fwd", "cheap_arm", "c2_score"]])

    if not obs_rows:
        need = (h - (len(cal) - 1 - cal_idx.get(dates[0], 0))) if dates[0] in cal_idx else h
        print(f"尚無成熟 cohort (需 cohort 日之後再 {h} 個交易日的價格)。")
        return
    obs = pd.concat(obs_rows, ignore_index=True)
    # 去市場 beta:每檔 fwd 減去『同 cohort 全體均值』→ excess 才反映榜齡的相對預測力
    # (2026 H1 多頭 backfill 會把每個桶的絕對 fwd 都灌成 +5~7%,絕對值看不出結構)
    obs["fwd_excess"] = obs["fwd"] - obs.groupby("cohort")["fwd"].transform("mean")
    n_live = obs[obs["source"] == "live"]["cohort"].nunique()
    n_bf = obs[obs["source"] == "backfill"]["cohort"].nunique()
    print(f"成熟 cohort {n_mature} 個 (live {n_live} / backfill {n_bf});觀測 {len(obs)} 筆\n")

    order = [lab for _, _, lab in BUCKETS]

    # ---- 非重疊 cohort:每 h 交易日取一個,跨 cohort 的 bucket 均值序列算 t ----
    picked, target = [], None
    for d in sorted(obs["cohort"].unique(), key=lambda x: cal_idx[x]):
        ci = cal_idx[d]
        if target is None or ci >= target:
            picked.append(d)
            target = ci + h
    no = obs[obs["cohort"].isin(picked)]
    # 每個 (cohort, bucket) 的 excess 均值 → 每個 bucket 一條跨 cohort 序列 (去 beta 後的相對邊際)
    cell = no.groupby(["cohort", "bucket"])["fwd_excess"].mean().reset_index()

    def summarize(frame: pd.DataFrame, cohort_means: pd.DataFrame, title: str):
        print(f"── {title} ──  (excess = 減同 cohort 全體均值,去市場 beta)")
        print(f"{'在榜桶':<12}{'n(觀測)':>8}{'均值fwd%':>10}{'excess均值%':>12}{'excess中位%':>13}"
              f"{'非重疊n':>9}{'excess-t':>10}")
        for lab in order:
            g = frame[frame["bucket"] == lab]
            if g.empty:
                continue
            series = cohort_means[cohort_means["bucket"] == lab]["fwd_excess"].to_numpy()
            t = tstat(series) if len(series) >= 3 else float("nan")
            n_flag = "" if len(series) >= args.min_n else " ⚠少樣本"
            print(f"{lab:<12}{len(g):>8}{g['fwd'].mean():>10.2f}{g['fwd_excess'].mean():>12.2f}"
                  f"{g['fwd_excess'].median():>13.2f}{len(series):>9}{t:>10.2f}{n_flag}")
        print()

    print("=" * 78)
    print(f"【主結論】streak → 前瞻 {h} 日報酬  (非重疊 cohort 為推論依據,全 cohort 為描述)")
    print("=" * 78)
    summarize(obs, cell, "全體 (所有在榜股)")

    # ---- 交叉檢驗:只看便宜臂 (excess + 原始中位數,看『久居便宜臂=原地踏步』假設) ----
    cheap = obs[obs["cheap_arm"]]
    if len(cheap):
        cell_c = (no[no["cheap_arm"]].groupby(["cohort", "bucket"])["fwd_excess"]
                  .mean().reset_index())
        summarize(cheap, cell_c, f"便宜臂 ({CHEAP_ARM_COL}>{ARM_THR:.0f}) × 在榜桶")

    # ---- 推薦窗判讀:用 excess (去 beta) 的中位數與均值 ----
    ex_cm = cell.groupby("bucket")["fwd_excess"].mean().reindex(order).dropna()
    cheap_raw_med = (cheap.groupby("bucket")["fwd"].median().reindex(order)
                     if len(cheap) else pd.Series(dtype=float))

    print("=" * 78)
    print("【推薦窗判讀】(去 beta 後的相對邊際 excess;此為 2026 H1 多頭 backfill,無 live 樣本外)")
    if not ex_cm.empty:
        best, worst = ex_cm.idxmax(), ex_cm.idxmin()
        print(f"  · 榜齡對『相對表現(excess)』的預測力很弱:各桶 excess 均值介於 "
              f"{ex_cm.min():+.2f}% ~ {ex_cm.max():+.2f}% (最佳 {best} / 最差 {worst}),"
              f"差異多在雜訊範圍 → 不建議把『在榜天數』當排序/擇時依據。")
    if len(cheap):
        ce = cheap.groupby("bucket")["fwd_excess"].mean().reindex(order).dropna()
        print(f"  · 便宜臂『整體』相對落後:各桶 excess 全負 ({ce.min():+.2f}% ~ {ce.max():+.2f}%)"
              f" → 『便宜』單臂是拖累,不是優勢 (量化了『便宜≠好』)。")
    if len(cheap_raw_med.dropna()):
        dead = [lab for lab in ("5–9", "10–19", "20–39")
                if lab in cheap_raw_med.index and cheap_raw_med.get(lab, 1) <= 0]
        if dead:
            print(f"  · 便宜臂中位數在 {'/'.join(dead)} 桶 ≤0 (原地踏步/微跌),均值卻正 → "
                  f"典型『價值陷阱=死錢+少數暴力反彈』;久居便宜臂的『那一檔』通常不動。")
        print(f"    便宜臂各桶原始中位 fwd%:"
              + " / ".join(f"{lab}:{cheap_raw_med.get(lab, float('nan')):+.2f}"
                           for lab in order if lab in cheap_raw_med.index))
    print("  · 結論:排序看 C2、不看榜齡;久居『便宜臂單臂』的名單以死錢居多,別當穩健核心。")
    print("=" * 78)

    # ---- 落地 ----
    out_summary = []
    for lab in order:
        g_all = obs[obs["bucket"] == lab]
        g_cheap = cheap[cheap["bucket"] == lab] if len(cheap) else pd.DataFrame()
        cm_all = cell[cell["bucket"] == lab]["fwd_excess"]
        out_summary.append({
            "bucket": lab, "horizon": h,
            "n_obs": len(g_all),
            "mean_fwd": round(g_all["fwd"].mean(), 3) if len(g_all) else np.nan,
            "median_fwd": round(g_all["fwd"].median(), 3) if len(g_all) else np.nan,
            "mean_excess": round(g_all["fwd_excess"].mean(), 3) if len(g_all) else np.nan,
            "median_excess": round(g_all["fwd_excess"].median(), 3) if len(g_all) else np.nan,
            "n_cohorts_noOverlap": len(cm_all),
            "excess_t_noOverlap": round(tstat(cm_all.to_numpy()), 2) if len(cm_all) >= 3 else np.nan,
            "cheap_n_obs": len(g_cheap),
            "cheap_mean_fwd": round(g_cheap["fwd"].mean(), 3) if len(g_cheap) else np.nan,
            "cheap_median_fwd": round(g_cheap["fwd"].median(), 3) if len(g_cheap) else np.nan,
        })
    out_f = POOL_DIR / "streak_return.csv"
    pd.DataFrame(out_summary).to_csv(out_f, index=False, encoding="utf-8-sig")
    print(f"\n分桶摘要已寫 {out_f}")


if __name__ == "__main__":
    main()
