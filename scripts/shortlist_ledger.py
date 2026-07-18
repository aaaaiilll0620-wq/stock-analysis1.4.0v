# -*- coding: utf-8 -*-
"""shortlist_ledger.py — 活體對帳:凍結預測 vs 已實現報酬,雙軌監控 (0 API)
================================================================================
組合層兩步走的第一步 (devlog §20-E 後續):每天的 pool/shortlist CSV 就是凍結的
預測;本腳本在 20/60 交易日報酬窗口成熟後回頭對帳。**雙軌設計** (2026-07-18
首跑診斷的教訓:池級 IC +0.054 在期望帶內,shortlist 圈人後 +0.021 且極吵——
範圍受限效應,§19 誠實邊界的活體重演):

  軌1 池級訊號健康 (primary):pool_{date}.csv (~918 檔) 池內重建 c2 → 已實現
       Rank IC,對照 alpha gate 期望帶 +0.05~0.09 (六時代,20d)。訊號死活看這裡。
  軌2 使用面 (secondary):shortlist 內排序 IC、top-30 相對 shortlist/pool 的
       超額。使用者「由上往下瀏覽」的實際體驗看這裡;已知 top10−next15≈0,
       此軌吵是預期,趨勢性惡化才是警訊。

- 價格線:TEJ 種子 ∪ 官方每日快照 (同 universe_screen_daily.load_union 接縫)
- 2026-07-17 (C2 接線日) 前 cohort 標記 backfill (重放),之後 live——live 序列
  才是真正的活體樣本外成績單
- 已知限制:close 未還原除權息 (與整條驗證鏈同口徑);相鄰日名單高度重疊,
  推論看「非重疊序列」(每 h 交易日取一 cohort) 的 t 值
- c2 池內重建與生產公式逐檔 parity 檢查 (每次跑都驗)

用法:
  python scripts/shortlist_ledger.py              # 對帳報告 + 寫 outputs/universe_pool/ledger.csv
  python scripts/shortlist_ledger.py --horizons 20
================================================================================
"""
from __future__ import annotations

import os
import re
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
SNAP_DIR = MARKET_CACHE / "price_valuation_daily"
POOL_DIR = PROJECT_ROOT / "outputs" / "universe_pool"
LEDGER_OUT = POOL_DIR / "ledger.csv"

LIVE_START = "2026-07-17"        # C2 接線生產日
MIN_STOCKS_PER_DAY = 500         # 交易日曆:當日收盤檔數門檻
IC_BAND = (0.05, 0.09)           # alpha gate 六時代期望帶 (20d,L1 池)
EXPECT_NOTE = "alpha gate 六時代 IC +0.05~0.09 (20d,L1池);2026YTD健檢 +0.038"


def load_prices() -> pd.DataFrame:
    """TEJ 種子 ∪ 官方快照的收盤價 (同 universe_screen_daily 接縫)。"""
    con = duckdb.connect()
    tej_max = con.execute(f"""
        SELECT MAX(date) FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
    """).fetchone()[0]
    has_snap = SNAP_DIR.exists() and any(SNAP_DIR.glob("*.parquet"))
    snap_sql = f"""
        UNION ALL BY NAME
        SELECT stock_id, date, close
        FROM read_parquet('{SNAP_DIR}/*.parquet', union_by_name=true)
        WHERE date > '{tej_max}'""" if has_snap else ""
    px = con.execute(f"""
        SELECT stock_id, date, close
        FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        {snap_sql}
    """).df()
    con.close()
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    return px.dropna(subset=["close"])


def trading_calendar(px: pd.DataFrame) -> list[str]:
    cnt = px.groupby("date").size()
    return sorted(cnt[cnt >= MIN_STOCKS_PER_DAY].index)


def load_cohort_dates() -> list[str]:
    out = []
    for f in sorted(POOL_DIR.glob("pool_*.csv")):
        m = re.match(r"pool_(\d{4}-\d{2}-\d{2})\.csv", f.name)
        if m and (POOL_DIR / f"shortlist_{m.group(1)}.csv").exists():
            out.append(m.group(1))
    return out


def build_pool_c2(pool: pd.DataFrame) -> pd.Series | None:
    """池級 c2:優先用生產存欄,退而用 backfill 存欄+營收池內重排。

    直接重排原始因子欄會因 CSV 精度往返翻轉平手排名 (high52_prox 觀測 maxdiff
    0.07 pct),故一律以存欄為準。舊 live 薄格式 (2026-07-15~17,因子欄缺) 回傳
    None → 軌1 略過該 cohort (軌2 shortlist 不受影響)。
    """
    if "c2_score" in pool.columns:                       # 新 live 格式 (2026-07-20 起)
        return pool["c2_score"]
    if "value_ind_pct_pool_pct" in pool.columns:         # backfill 格式
        rev = (pool["revenue_yoy_pool_pct"] if "revenue_yoy_pool_pct" in pool.columns
               else pool["revenue_yoy"].rank(pct=True) * 100.0)
        return pd.concat([pool["value_ind_pct_pool_pct"], rev,
                          pool["high52_prox_pool_pct"],
                          100.0 - pool["momentum20_pool_pct"]],
                         axis=1).mean(axis=1, skipna=True)
    return None


def load_cohort(date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳 (pool 含 c2 欄或無, shortlist 含生產 c2_score),並做 parity 檢查。"""
    pool = pd.read_csv(POOL_DIR / f"pool_{date}.csv", encoding="utf-8-sig",
                       dtype={"stock_id": str})
    sl = pd.read_csv(POOL_DIR / f"shortlist_{date}.csv", encoding="utf-8-sig",
                     dtype={"stock_id": str})
    if "c2_score" not in sl.columns or sl.empty or pool.empty:
        return pd.DataFrame(), pd.DataFrame()
    c2 = build_pool_c2(pool)
    if c2 is None:
        return pool.drop(columns=["c2"], errors="ignore"), sl
    pool["c2"] = c2
    chk = pool[["stock_id", "c2"]].merge(sl[["stock_id", "c2_score"]], on="stock_id")
    diff = (chk["c2"] - chk["c2_score"]).abs().max()
    # 0.01 容忍:防未來營收欄精度平手 (存欄法觀測 maxdiff 0.000000)
    assert diff < 0.01, f"{date} 池級 c2 與生產 c2_score 不一致 (maxdiff={diff})"
    return pool, sl


def quintile_returns(score: pd.Series, fwd: pd.Series) -> list[float]:
    """Q1(低分)→Q5(高分) 平均報酬。"""
    q = pd.qcut(score.rank(method="first"), 5, labels=False)
    return [float(fwd[q == i].mean()) for i in range(5)]


def attach_fwd(df: pd.DataFrame, p1: pd.DataFrame, score_col: str) -> pd.DataFrame:
    d = df.merge(p1.rename(columns={"close": "p1"}), on="stock_id", how="left")
    d["fwd"] = (d["p1"] / d["close"] - 1.0) * 100.0
    return d.dropna(subset=["fwd", score_col])


def reconcile(date: str, pool: pd.DataFrame, sl: pd.DataFrame, p1: pd.DataFrame,
              mature: str, horizon: int, i0: int) -> list[dict]:
    rows = []
    src = "live" if date >= LIVE_START else "backfill"
    base = {"cohort": date, "horizon": horizon, "mature": mature,
            "source": src, "cal_idx": i0}

    pk = attach_fwd(pool, p1, "c2") if "c2" in pool.columns else pd.DataFrame()
    if len(pk) >= 100:
        qs = quintile_returns(pk["c2"], pk["fwd"])
        rows.append({**base, "level": "pool", "n": len(pk),
                     "coverage": len(pk) / len(pool),
                     "ic": float(pk["c2"].rank().corr(pk["fwd"].rank())),
                     "q1": qs[0], "q2": qs[1], "q3": qs[2], "q4": qs[3], "q5": qs[4],
                     "q5_q1": qs[4] - qs[0],
                     "top30_excess": float(pk.nlargest(30, "c2")["fwd"].mean()
                                           - pk["fwd"].mean())})
    sk = attach_fwd(sl, p1, "c2_score")
    if len(sk) >= 50:
        qs = quintile_returns(sk["c2_score"], sk["fwd"])
        top30 = sk.nlargest(30, "c2_score")["fwd"].mean()
        rows.append({**base, "level": "shortlist", "n": len(sk),
                     "coverage": len(sk) / len(sl),
                     "ic": float(sk["c2_score"].rank().corr(sk["fwd"].rank())),
                     "q1": qs[0], "q2": qs[1], "q3": qs[2], "q4": qs[3], "q5": qs[4],
                     "q5_q1": qs[4] - qs[0],
                     "top30_excess": float(top30 - sk["fwd"].mean()),
                     "top30_vs_pool": (float(top30 - pk["fwd"].mean())
                                       if len(pk) >= 100 else np.nan)})
    return rows


def non_overlap(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """每 horizon 個交易日取一個 cohort (相鄰名單重疊,推論用非重疊序列)。"""
    picked, target = [], None
    for _, row in df.sort_values("cal_idx").iterrows():
        if target is None or row["cal_idx"] >= target:
            picked.append(row)
            target = row["cal_idx"] + horizon
    return pd.DataFrame(picked)


def report(results: pd.DataFrame, horizon: int):
    d = results[results["horizon"] == horizon]
    if d.empty:
        print(f"\n--- h={horizon}:尚無成熟 cohort ---")
        return
    pool = d[d["level"] == "pool"]
    sl = d[d["level"] == "shortlist"]
    print(f"\n--- h={horizon} 交易日:成熟 cohort {pool['cohort'].nunique()} 個 "
          f"({d['cohort'].min()} ~ {d['cohort'].max()}) ---")

    no = non_overlap(pool, horizon)
    ic_no = no["ic"].to_numpy()
    t = ic_no.mean() / ic_no.std(ddof=1) * np.sqrt(len(ic_no)) if len(ic_no) > 2 else np.nan
    in_band = "在期望帶內 ✓" if IC_BAND[0] <= ic_no.mean() <= IC_BAND[1] else (
        "高於期望帶" if ic_no.mean() > IC_BAND[1] else "低於期望帶 ⚠")
    print(f"  [軌1 池級訊號健康] 非重疊 n={len(no)}:IC {ic_no.mean():+.3f} (t={t:.1f}) → {in_band}"
          f"{'' if horizon == 20 else ' (期望帶為20d量尺,60d僅趨勢參考)'}")
    print(f"    全 cohort 平均 IC {pool['ic'].mean():+.3f};五分位%:"
          + " / ".join(f"{pool[q].mean():+.2f}" for q in ["q1", "q2", "q3", "q4", "q5"])
          + f";Q5−Q1 {pool['q5_q1'].mean():+.2f}%;top30−pool {pool['top30_excess'].mean():+.2f}%")

    if len(sl):
        no_s = non_overlap(sl, horizon)
        print(f"  [軌2 使用面 shortlist] 非重疊 IC {no_s['ic'].mean():+.3f};"
              f"top30 − shortlist {sl['top30_excess'].mean():+.2f}%;"
              f"top30 − pool {sl['top30_vs_pool'].mean():+.2f}% "
              f"(此軌吵是預期:top10−next15≈0,看趨勢不看單月)")
    for src in ["backfill", "live"]:
        s = pool[pool["source"] == src]
        if len(s):
            print(f"  [{src}] {s['cohort'].nunique()} cohort,池級 IC 平均 {s['ic'].mean():+.3f}")


def main():
    ap = argparse.ArgumentParser(description="pool/shortlist 活體對帳 (0 API)")
    ap.add_argument("--horizons", type=int, nargs="+", default=[20, 60])
    args = ap.parse_args()

    px = load_prices()
    cal = trading_calendar(px)
    cal_idx = {d: i for i, d in enumerate(cal)}
    px_by_date = {d: g[["stock_id", "close"]] for d, g in px.groupby("date") if d in cal_idx}
    dates = load_cohort_dates()
    print(f"價格資料截至 {cal[-1]};cohort {len(dates)} 個 "
          f"(live 自 {LIVE_START} 起 {sum(1 for c in dates if c >= LIVE_START)} 個)")

    rows = []
    n_parity, n_thin = 0, 0
    for date in dates:
        i0 = cal_idx.get(date)
        if i0 is None:
            continue
        pool, sl = load_cohort(date)                 # 含 c2 parity 檢查 (薄格式除外)
        if pool.empty:
            continue
        if "c2" in pool.columns:
            n_parity += 1
        else:
            n_thin += 1
        for h in args.horizons:
            if i0 + h >= len(cal):
                continue
            rows.extend(reconcile(date, pool, sl, px_by_date[cal[i0 + h]],
                                  cal[i0 + h], h, i0))
    results = pd.DataFrame(rows)
    if results.empty:
        print("尚無任何成熟 cohort。")
        return
    print(f"c2 parity 檢查:{n_parity} cohort 池級重建 vs 生產 c2_score 一致 ✓"
          + (f";{n_thin} cohort 為舊 live 薄格式 (無因子欄),軌1 略過" if n_thin else ""))

    print(f"\n================ 對帳報告 (對照:{EXPECT_NOTE}) ================")
    for h in args.horizons:
        report(results, h)

    live = [c for c in dates if c >= LIVE_START]
    if live:
        i0 = cal_idx.get(live[0])
        if i0 is not None and i0 + min(args.horizons) >= len(cal):
            need = i0 + min(args.horizons) - len(cal) + 1
            print(f"\nlive cohort 首個對帳日:{live[0]} 起再 {need} 個交易日後 (h={min(args.horizons)})")

    results.drop(columns=["cal_idx"]).to_csv(LEDGER_OUT, index=False, encoding="utf-8-sig")
    print(f"per-cohort 明細已寫 {LEDGER_OUT}")


if __name__ == "__main__":
    main()
