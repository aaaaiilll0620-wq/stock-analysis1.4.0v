"""
建/更新『法人資金流向產業』快照 (想法2 B版) — 0 FinMind API
================================================================================
把全市場法人淨買 × 收盤價,依 TEJ 產業別聚合成各產業每日淨流入(億元) + 成交額,
落地成 cloud_cache/IndustryFlow/{flow,members}.parquet,供 app『🏭 法人流向』分頁讀。

資料源 = TEJ 種子 (~/tej_cache,2004 起全歷史) ∪ collector 每日快照 (~/market_cache)。

用法:
  python scripts/build_industry_flow.py                  # 預設近 3 年 (雲端 repo 友善)
  python scripts/build_industry_flow.py --start 2004-01-01   # 全歷史
  python scripts/build_industry_flow.py --days 60        # 只保留最近 60 個交易日
  python scripts/build_industry_flow.py --no-history     # 只用 collector 快照 (不吃 TEJ 種子)

跑完若要同步到雲端 App,一併 commit cloud_cache/IndustryFlow/*.parquet 再 push。
================================================================================
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import industry_flow as IF

DEFAULT_YEARS = 3


def main() -> None:
    ap = argparse.ArgumentParser(description="建產業法人流向快照 (0 FinMind API)")
    ap.add_argument("--days", type=int, default=None, help="只保留最近 N 個交易日")
    ap.add_argument("--start", default=None,
                    help=f"起始日 YYYY-MM-DD (預設近 {DEFAULT_YEARS} 年;--days 優先)")
    ap.add_argument("--member-days", type=int, default=250,
                    help="下鑽成分股只留最近 N 個交易日 (預設 250;全歷史太大)")
    ap.add_argument("--no-history", action="store_true",
                    help="不吃 TEJ 種子,只用 collector 每日快照")
    args = ap.parse_args()

    start = args.start
    if not args.days and not start:
        start = f"{date.today().year - DEFAULT_YEARS}-01-01"

    history = not args.no_history
    print(f"來源:{'TEJ 種子 ' + str(IF.TEJ_CHIP_DIR) + ' ∪ ' if history else ''}"
          f"每日快照 {IF.CHIP_DIR}")
    print(f"範圍:{'最近 ' + str(args.days) + ' 個交易日' if args.days else '自 ' + str(start)}"
          f"　｜　成分股保留最近 {args.member_days} 日")

    n_flow, n_mem = IF.build_snapshot(days=args.days, start=start,
                                      members_days=args.member_days, history=history)
    df = IF.load_flow(IF.DEFAULT_LEVEL)
    print(f"✅ flow {n_flow:,} 列 → {IF.SNAPSHOT} "
          f"({IF.SNAPSHOT.stat().st_size / 1e6:.1f} MB)")
    print(f"✅ members {n_mem:,} 列 → {IF.MEMBERS_SNAPSHOT} "
          f"({IF.MEMBERS_SNAPSHOT.stat().st_size / 1e6:.1f} MB)")
    if not df.empty:
        print(f"   {IF.DEFAULT_LEVEL}:{df['industry'].nunique()} 產業 × {df['date'].nunique()} 交易日"
              f" ({df['date'].min()} ～ {df['date'].max()})")
    mb = (IF.SNAPSHOT.stat().st_size + IF.MEMBERS_SNAPSHOT.stat().st_size) / 1e6
    if mb > 15:
        print(f"⚠️  兩檔合計 {mb:.0f} MB —— snapshot 會 commit 進 repo,parquet 無法 diff,"
              "每次重建都是一顆新 blob。要天天重建請縮短 --start 或 --member-days。")
    print("   同步雲端:git add cloud_cache/IndustryFlow 後 commit + push。")


if __name__ == "__main__":
    main()
