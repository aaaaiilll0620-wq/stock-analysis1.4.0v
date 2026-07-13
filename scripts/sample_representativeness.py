"""
樣本代表性量化 (Next Steps #4) —— 0 API，純讀本機快取
--------------------------------------------------------------
背景 (見開發日誌 §12-D)：原始 45 檔測試池是刻意跨產業、低相關性篩選出來的，
換一批沒有刻意篩選的股票，排序力 (市場中性價差) 會打折甚至失效。
但打折幅度從未被量化，也不知道能否用一個簡單規則 (如低相關性篩選) 在擴池時維持排序力。

做法：
  1. 用本機已快取的 76 檔 (45 原始 + 31 獨立新增) 當「母體」，全程 0 API。
  2. 定義「平均兩兩相關係數」作為股票池「分散化程度」的量化指標。
  3. 跑三種池子並比較各市場週期的市場中性價差：
       a. baseline      = 原始 45 檔
       b. random_45 xN  = 從 76 檔母體隨機抽 45 檔 (不做任何篩選)，重複 N 次
       c. greedy_low_45 = 貪婪法從 76 檔挑出「平均相關性最低」的 45 檔
  4. 用 (avg_corr, 市場中性價差) 的散佈，回答「打折幅度 vs 分散化程度」的關係，
     並檢驗 greedy_low_45 是否能重現 baseline 的排序力（回答「篩選規則能否維持排序力」）。

用法：
  python scripts\\sample_representativeness.py                # 預設 8 次隨機抽樣
  python scripts\\sample_representativeness.py --reps 20
"""
import argparse
import itertools
import os
import random
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import pandas as pd

from core import data_cache
from core.backtest import Backtester, cached_fetch_history

from tests.run_backtest import DIVERSIFIED_POOL

CACHE_DIR = data_cache.CACHE_DIR


def all_cached_symbols():
    price_dir = CACHE_DIR / "TaiwanStockPrice"
    ids = sorted(p.stem for p in price_dir.glob("*.parquet"))
    return [s for s in ids if s != "0050"]


def load_returns(symbols):
    """讀快取價格，回傳每日報酬率的寬表 (index=date, columns=symbol)。0 API。"""
    series = {}
    for sym in symbols:
        df = data_cache.read_cached("TaiwanStockPrice", sym)
        if df is None or df.empty or "close" not in df.columns:
            continue
        s = df[["date", "close"]].dropna()
        s["date"] = pd.to_datetime(s["date"], errors="coerce")
        s = s.dropna().drop_duplicates("date").set_index("date")["close"].astype(float)
        series[sym] = s.sort_index().pct_change()
    return pd.DataFrame(series)


def avg_pairwise_corr(returns_df, symbols):
    sub = returns_df[[s for s in symbols if s in returns_df.columns]]
    corr = sub.corr()
    n = len(corr)
    if n < 2:
        return float("nan")
    off_diag_sum = corr.values.sum() - np.trace(corr.values)
    return float(off_diag_sum / (n * (n - 1)))


def greedy_low_corr_pool(returns_df, universe, size, seed_symbol=None):
    """貪婪法：每步挑「加入後平均相關性增幅最小」的股票，直到湊滿 size 檔。"""
    universe = [s for s in universe if s in returns_df.columns]
    remaining = set(universe)
    if seed_symbol is None:
        # 種子：與母體其他股票平均相關性最低者
        corr_all = returns_df[universe].corr()
        avg_corr = (corr_all.sum() - 1.0) / (len(universe) - 1)
        seed_symbol = avg_corr.idxmin()
    selected = [seed_symbol]
    remaining.discard(seed_symbol)
    while len(selected) < size and remaining:
        best_sym, best_corr = None, None
        for cand in remaining:
            trial = selected + [cand]
            c = avg_pairwise_corr(returns_df, trial)
            if best_corr is None or c < best_corr:
                best_corr, best_sym = c, cand
        selected.append(best_sym)
        remaining.discard(best_sym)
    return selected


def run_pool(label, symbols, avg_corr):
    bt = Backtester(symbols=symbols, mode="balanced")
    bt.load(fetcher=cached_fetch_history)
    rows = bt.cycle_robustness()
    out = []
    for r in rows:
        seg_label, rng, neutral, buy_spread, bench_pct, verdict = r
        out.append({
            "pool": label, "n": len(symbols), "avg_corr": avg_corr,
            "segment": seg_label, "range": rng, "neutral_spread": neutral,
            "buy_spread": buy_spread, "verdict": verdict,
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="樣本代表性量化 (0 API)")
    ap.add_argument("--reps", type=int, default=8, help="隨機抽樣次數 (預設 8)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    universe = all_cached_symbols()
    print(f"母體 (本機已快取): {len(universe)} 檔")
    baseline = [s for s in DIVERSIFIED_POOL if s in universe]
    print(f"Baseline (原始池): {len(baseline)} 檔")

    returns_df = load_returns(universe)
    print(f"報酬率矩陣: {returns_df.shape[1]} 檔 x {returns_df.shape[0]} 交易日\n")

    results = []

    base_corr = avg_pairwise_corr(returns_df, baseline)
    print(f"[baseline] 平均兩兩相關 = {base_corr:.4f}")
    results += run_pool("baseline_45", baseline, base_corr)

    for i in range(args.reps):
        pool = random.sample(universe, len(baseline))
        c = avg_pairwise_corr(returns_df, pool)
        label = f"random_45_#{i+1}"
        print(f"[{label}] 平均兩兩相關 = {c:.4f}")
        results += run_pool(label, pool, c)

    greedy = greedy_low_corr_pool(returns_df, universe, len(baseline))
    greedy_corr = avg_pairwise_corr(returns_df, greedy)
    print(f"[greedy_low_corr_45] 平均兩兩相關 = {greedy_corr:.4f}")
    results += run_pool("greedy_low_corr_45", greedy, greedy_corr)

    df = pd.DataFrame(results)
    out_path = os.path.join(project_root, "scripts", "sample_representativeness_result.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n完整結果已存: {out_path}")

    print("\n" + "=" * 90)
    print("彙總：各池子在『2022 空頭』段的市場中性價差 vs 平均兩兩相關係數")
    print("=" * 90)
    seg_2022 = df[df["segment"].str.contains("2022")]
    for _, row in seg_2022.iterrows():
        print(f"{row['pool']:<22} avg_corr={row['avg_corr']:.4f}  neutral_spread={row['neutral_spread']:<20} {row['verdict']}")


if __name__ == "__main__":
    main()
