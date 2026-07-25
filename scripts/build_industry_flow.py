"""
建/更新『法人資金流向產業』快照 (想法2 B版) — 0 FinMind API
================================================================================
把全市場法人淨買 × 收盤價,依 TEJ 產業別聚合成各產業每日淨流入(億元) + 成交額,
落地成 cloud_cache/IndustryFlow/{flow,members}.parquet,供 app『🏭 法人流向』分頁讀。

資料源 = TEJ 種子 (~/tej_cache,2004 起全歷史) ∪ collector 每日快照 (~/market_cache)。

兩種模式:
  · **增量 (--incremental)**:只把「基底之後、還沒落地」的交易日各寫成一個小檔
    (flow ~10KB + members ~30KB)。給每日排程用 —— snapshot 要 commit 進 repo 而 parquet
    無法 diff,每天重寫 13MB 基底等於每天一顆 13MB 新 blob (一年 3GB+ git 歷史)。
  · **全量 (預設)**:重建歷史基底 (13MB)。只在首次、或改了範圍/產業分類表時跑。

用法:
  python scripts/build_industry_flow.py --incremental     # 每日增量 (排程用,冪等)
  python scripts/build_industry_flow.py                   # 全量重建,預設近 3 年
  python scripts/build_industry_flow.py --start 2004-01-01    # 全量,全歷史
  python scripts/build_industry_flow.py --days 60         # 全量,只保留最近 60 個交易日
  python scripts/build_industry_flow.py --no-history      # 全量,只用 collector 快照
  python scripts/build_industry_flow.py --compact         # 把逐日檔折進基底並清空 (別天天跑)

跑完若要同步到雲端 App,一併 commit cloud_cache/IndustryFlow 再 push
(每日排程走 deploy_scores.py,它會 `git add cloud_cache`,自動含這裡的增量檔)。
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
    ap.add_argument("--incremental", action="store_true",
                    help="只補基底之後尚未落地的交易日 (每日排程用,冪等、每天約 40KB)")
    ap.add_argument("--compact", action="store_true",
                    help="把逐日增量檔折進歷史基底並清空 (會重寫 13MB 基底,別天天跑)")
    ap.add_argument("--fold-after", type=int, default=90,
                    help="增量模式下,逐日檔超過這個數量就提醒該 --compact 了 (預設 90)")
    args = ap.parse_args()

    if args.compact:
        n_f, n_m = IF.compact(members_days=args.member_days)
        if n_f == 0:
            print("ℹ️ 沒有逐日增量檔,無須 compact。")
        else:
            print(f"✅ 已折進基底:flow {n_f:,} 列 / members {n_m:,} 列,逐日檔已清空。")
        return

    if args.incremental:
        # 每日排程走這條。collector 沒收到當天資料 → 沒有可補的日子,直接 no-op (不算失敗)。
        base = IF.base_max_date()
        added = IF.append_days()
        pend = IF.daily_dates()
        if added:
            print(f"✅ 增量新增 {len(added)} 個交易日:{', '.join(added)}")
        else:
            print(f"ℹ️ 沒有新的交易日可補 (基底至 {base};collector 快照可能還沒到今天)。")
        if pend:
            _mb = sum(f.stat().st_size for d in (IF.DAILY_FLOW_DIR, IF.DAILY_MEMBERS_DIR)
                      for f in d.glob("*.parquet")) / 1e6
            print(f"   逐日檔 {len(pend)} 天 ({pend[0]}～{pend[-1]}),共 {_mb:.2f} MB")
            if len(pend) >= args.fold_after:
                print(f"⚠️  逐日檔已達 {len(pend)} 天 —— 建議跑一次 "
                      "`python scripts/build_industry_flow.py --compact` 折進基底。")
        return

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
