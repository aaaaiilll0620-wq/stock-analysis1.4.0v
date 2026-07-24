"""
綜合分歷史回填 (個股頁『近 N 日綜合分走勢』用) — 0 FinMind API
================================================================================
build_cache.py --build-scores 只在『最新交易日』建一列;每日排程往後累積,故新進名單
的個股歷史點數不足。本腳本對『最近 N 個交易日』各建一次 scores,讓每檔名單股票一次補滿
近 N 日連續走勢。

  · 母體:預設讀最新 UniversePool/pool_*.csv (與每日排程同一批 ~900 檔);可用 --universe-from 指定。
  · 交易日:取基準 0050 快取的最後 N 個交易日 (PIT,與 score_store 的 regime 同一套日曆)。
  · 來源:source='tej' → 純本機 TEJ 快取,0 FinMind API。
  · 冪等:score_store 以 (as_of, mode) 去重、keep last,重跑安全。

用法:
  python scripts/backfill_score_history.py                 # 最近 10 交易日 × 最新 pool × balanced
  python scripts/backfill_score_history.py --days 15 --modes balanced conservative
  python scripts/backfill_score_history.py --universe-from cloud_cache/UniversePool/pool_2026-07-24.csv
================================================================================
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import score_store
from core.backtest import load_benchmark
from core.scoring_manager import ScoringManager

_POOL_GLOB = "cloud_cache/UniversePool/pool_*.csv"


def _latest_pool() -> str | None:
    files = sorted(glob.glob(_POOL_GLOB))
    return files[-1] if files else None


def _load_symbols(path: str) -> list[str]:
    import csv
    codes, seen = [], set()
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = str(row.get("stock_id", "")).strip()
            if sid and sid not in seen:
                seen.add(sid); codes.append(sid)
    return codes


def _trading_days(n: int) -> list[str]:
    """基準 0050 快取的最後 n 個交易日 (由舊到新)。無基準快取 → 空清單。"""
    b = load_benchmark("0050")
    if b is None or getattr(b, "price", None) is None or b.price.empty:
        return []
    days = sorted(pd.to_datetime(b.price["date"], errors="coerce").dropna().dt.date.astype(str).unique())
    return days[-n:]


def main() -> None:
    ap = argparse.ArgumentParser(description="綜合分近 N 日歷史回填 (0 FinMind API)")
    ap.add_argument("--days", type=int, default=10, help="回填最近幾個交易日 (預設 10)")
    ap.add_argument("--modes", nargs="*", default=["balanced"],
                    help="要回填的模式 (預設 balanced;可多個)")
    ap.add_argument("--universe-from", default=None,
                    help="pool_*.csv / shortlist_*.csv 路徑;省略則用最新 pool")
    ap.add_argument("--source", choices=["tej", "finmind"], default="tej",
                    help="資料源 (預設 tej = 0 API)")
    args = ap.parse_args()

    for m in args.modes:
        if m not in ScoringManager.MODES:
            sys.exit(f"未知模式 {m!r};可用:{list(ScoringManager.MODES)}")

    pool_path = args.universe_from or _latest_pool()
    if not pool_path or not os.path.exists(pool_path):
        sys.exit(f"找不到母體 CSV (glob={_POOL_GLOB});請用 --universe-from 指定。")
    symbols = _load_symbols(pool_path)
    if not symbols:
        sys.exit(f"{pool_path} 讀不到任何 stock_id。")

    days = _trading_days(args.days)
    if not days:
        sys.exit("取不到交易日 (基準 0050 快取缺?);請先確認 benchmark 快取存在。")

    print(f"回填母體:{len(symbols)} 檔 (from {os.path.basename(pool_path)})")
    print(f"回填交易日:{len(days)} 天  {days[0]} … {days[-1]}")
    print(f"模式:{args.modes}  來源:{args.source}\n")

    total = 0
    for i, day in enumerate(days, 1):
        print(f"[{i}/{len(days)}] as_of={day} …", flush=True)
        try:
            total += score_store.build_scores(symbols=symbols, modes=args.modes,
                                               as_of=day, source=args.source)
        except Exception as e:
            print(f"  ⚠️ {day} 回填失敗 (跳過): {e}")

    print(f"\n✅ 回填完成:寫入 {total} 列。個股頁『近日綜合分走勢』即可看到連續 {len(days)} 日。")
    if args.source == "tej":
        print("   (0 FinMind API;若要同步到雲端 App,記得跑 deploy_scores.py。)")


if __name__ == "__main__":
    main()
