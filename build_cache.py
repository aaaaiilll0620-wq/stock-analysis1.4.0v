"""
建庫 / 每日增量更新 FinMind 本機 Parquet 快取 (限流並行)
================================================================================
用法:
  首次建庫 (整批,測試池 ~45 檔):   python build_cache.py --full
  每日增量更新 (補新資料 + 自動刷新當天 scores):  python build_cache.py
  只更新原始資料、不算 scores:       python build_cache.py --no-scores
  指定代號:                          python build_cache.py 2330 2454 2317
  跨股選股示範 (最新 PER 由低到高):   python build_cache.py --screen
  建綜合分快取 (五維 composite):      python build_cache.py --build-scores
  只建單一模式:                      python build_cache.py --build-scores --modes balanced
  跨股綜合分排名示範:                 python build_cache.py --screen-composite
  調整並行/限流:                     python build_cache.py --workers 5 --throttle 0.2

說明:
  · 快取存在 <FINMIND_CACHE 或 家目錄/finmind_cache>,刻意放 OneDrive 外避免反覆同步。
  · 純追加資料集 (股價/PER/籌碼/流通股) 只補增量;財報/月營收會整批覆蓋 (因事後會被修正)。
  · 並行只加快『建庫速度』,不會減少 API 次數;workers 建議 4~6、必要時加 throttle 避免撞每小時上限。
  · 建好之後,回測用   python tests\\run_backtest.py --cache   即可 0 次 API 讀本機。
  · --build-scores 讀本機原始快取算五維綜合分並落地 (0 API),供 --screen-composite 跨股排名。
  · 日更一步到位:一般的 python build_cache.py 在增量更新原始資料後,會『順手』用剛更新的
    本機快取刷新當天 scores (0 API);不想算 scores 時加 --no-scores 即可。
================================================================================
"""
import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
logging.basicConfig(level=logging.WARNING)

from core.data_provider import DataProvider
from core import data_cache


def load_watchlist(path=None):
    """讀專案根目錄的 watchlist.txt → 回傳代號清單 (去重、保序)。
    格式:一行一檔,行內第一個 token 視為代號;空行或 # 開頭整行略過;
         代號後可加名稱/註解 (例 '2330  台積電' 或 '2330  # 台積電')。
    檔案不存在或無有效代號 → 回傳 None (由呼叫端決定回退)。"""
    path = path or os.path.join(project_root, "watchlist.txt")
    if not os.path.exists(path):
        return None
    codes = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                code = line.split()[0].strip().upper()   # 取第一個 token 當代號
                if code and not code.startswith("#") and code not in codes:
                    codes.append(code)
    except Exception as e:
        print(f"(watchlist.txt 讀取失敗,改用內建測試池:{e})")
        return None
    return codes or None


def load_watchlist_names(path=None):
    """讀 watchlist.txt → 回傳 {代號: 股名} 對照表 (供 scores 快取顯示正確名稱)。
    格式:代號後面接的第一個 token 視為股名;可有 '#' 註解符 (例 '2330  台積電'
         或 '2330  # 台積電' 都會解析出『台積電』)。沒寫名稱的代號不列入。
    檔案不存在或解析失敗 → 回傳 {} (呼叫端會退回以代號當名稱)。"""
    path = path or os.path.join(project_root, "watchlist.txt")
    names = {}
    if not os.path.exists(path):
        return names
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                code = parts[0].strip().upper()
                if not code or code.startswith("#"):
                    continue
                rest = line[len(parts[0]):].strip()   # 代號之後的整段
                if rest.startswith("#"):               # 去掉註解符號 '#'
                    rest = rest.lstrip("#").strip()
                if rest:
                    name = rest.split()[0].strip()     # 取第一個 token 當股名
                    if name and not name.startswith("#"):
                        names[code] = name
    except Exception as e:
        print(f"(watchlist.txt 名稱解析失敗,名稱將以代號代替:{e})")
    return names


def _load_pool():
    """預設清單來源:優先 watchlist.txt,沒有就回退回測分散化測試池。"""
    codes = load_watchlist()
    if codes:
        print(f"(已從 watchlist.txt 讀入 {len(codes)} 檔自選股)")
        return codes
    try:
        from tests.run_backtest import DIVERSIFIED_POOL
        return list(DIVERSIFIED_POOL)
    except Exception:
        return ["2330", "2454", "2317"]


def build(symbols, workers=5, force_full=False, throttle=0.0):
    """限流並行建庫 / 更新。回傳總 API 呼叫次數。"""
    DataProvider._ensure_login()
    api = data_cache.unwrap(DataProvider._api)   # 用底層原始 loader,直接建庫、不走代理的新鮮度判斷
    # 產業別對照表抓一次 (供 sector / is_financial;本身有 30 天磁碟快取)
    try:
        DataProvider._ensure_industry_map()
    except Exception as e:
        print(f"(產業別對照表更新略過:{e})")

    n = len(symbols)
    tally = {"calls": 0, "done": 0}
    t0 = time.time()

    def _one(sym):
        c = 0
        for ds in data_cache.ALL_DATASETS:
            _, calls = data_cache.update_dataset(api, ds, sym, force_full=force_full)
            c += calls
            if throttle:
                time.sleep(throttle)
        return sym, c

    print(f"開始{'整批建庫' if force_full else '增量更新'} {n} 檔 "
          f"(workers={workers}, throttle={throttle}s)  快取:{data_cache.CACHE_DIR}")
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(_one, s): s for s in symbols}
        for fut in as_completed(futs):
            sym, c = fut.result()
            tally["calls"] += c
            tally["done"] += 1
            print(f"  [{tally['done']}/{n}] {sym}  (+{c} API)")

    dt = time.time() - t0
    print(f"\n✅ 完成:{n} 檔,共 {tally['calls']} 次 API 呼叫,耗時 {dt:.0f}s。")
    print(f"   之後回測讀本機:python tests\\run_backtest.py --cache   (0 次 API)")
    return tally["calls"]


def screen_demo():
    """跨股選股示範:用 DuckDB 直接查 Parquet 快取,列出全市場最新一日 PER 最低的 20 檔。"""
    sql = f"""
        SELECT stock_id, date,
               ROUND(PER, 1)  AS per,
               ROUND(PBR, 2)  AS pbr,
               ROUND(dividend_yield, 2) AS yield_pct
        FROM {data_cache.tbl('TaiwanStockPER')}
        WHERE PER IS NOT NULL AND PER > 0
        QUALIFY row_number() OVER (PARTITION BY stock_id ORDER BY date DESC) = 1
        ORDER BY per
        LIMIT 20
    """
    try:
        df = data_cache.duck_query(sql)
    except Exception as e:
        print(f"⚠️ DuckDB 查詢失敗 (是否已 pip install duckdb、且已建庫?):{e}")
        return
    print("\n跨股選股示範 — 全市場最新一日 PER 最低 20 檔 (價值面初篩):")
    print(df.to_string(index=False))
    print("\n(這只是示範:duck_query() + tbl('<dataset>') 可自由組任意跨股 SQL。"
          "完整綜合分選股見 --build-scores / --screen-composite。)")


def build_scores_demo(symbols, modes=None, refresh=False):
    """用五維綜合分建立 / 更新 scores 快取 (讀本機原始快取,0 API)。
    會從 watchlist.txt 讀入 {代號: 股名},讓 scores 快取存正確股名 (例 2330 → 台積電),
    避免『綜合分選股』頁的名稱欄跟代號一樣。"""
    from core import score_store
    names = load_watchlist_names()
    return score_store.build_scores(symbols=symbols, modes=modes, refresh=refresh, names=names)


def screen_composite_demo(mode="balanced"):
    """跨股綜合分排名示範:讀 scores 快取,列出綜合分 >= 門檻的前 20 檔。"""
    from core import score_store
    from core.scoring_manager import ScoringManager
    if mode not in ScoringManager.MODES:
        print(f"⚠️ 未知模式 {mode!r};可用:{list(ScoringManager.MODES)}")
        return
    min_score = ScoringManager.MODES[mode]["min_score"]
    try:
        df = score_store.screen_by_composite(mode=mode, min_composite=min_score, top=20)
    except Exception as e:
        print(f"⚠️ 綜合分排名查詢失敗 (是否已先跑 python build_cache.py --build-scores ?):{e}")
        return
    print(f"\n跨股綜合分排名示範 — mode={mode}, 綜合分 >= {min_score} (前 20;pct_rank=universe 內百分位):")
    if df.empty:
        print("(查無資料:先 build_cache.py --build-scores 建 scores,或放寬門檻)")
        return
    print(df.to_string(index=False))
    print("\n(可自由組合:core.score_store.screen_by_composite(mode=..., ratings=['強勢買進','強烈推薦'], ...))")


def main():
    ap = argparse.ArgumentParser(description="FinMind 本機 Parquet 快取建庫 / 更新")
    ap.add_argument("symbols", nargs="*", help="股票代號;省略則用分散化測試池")
    ap.add_argument("--full", action="store_true", help="整批重抓覆蓋 (首次建庫或想強制刷新)")
    ap.add_argument("--workers", type=int, default=5, help="並行 worker 數 (預設 5;過高易撞每小時上限)")
    ap.add_argument("--throttle", type=float, default=0.0, help="每次 API 後暫停秒數 (限流;預設 0)")
    ap.add_argument("--screen", action="store_true", help="跑跨股選股示範查詢 (原始欄位 PER;不建庫)")
    ap.add_argument("--build-scores", action="store_true",
                    help="用五維綜合分建立/更新 scores 快取 (讀本機原始快取,0 API)")
    ap.add_argument("--screen-composite", action="store_true",
                    help="跨股綜合分排名示範 (讀 scores 快取;不建庫)")
    ap.add_argument("--modes", nargs="*", default=None,
                    help="scores 要建/查哪些模式 (預設全部三個);例:--modes balanced")
    ap.add_argument("--score-refresh", action="store_true",
                    help="建 scores 前先對各資料集補抓增量 (會用 API;預設 0 API 純讀快取)")
    ap.add_argument("--no-scores", action="store_true",
                    help="日更時只更新原始資料,不自動刷新 scores")
    args = ap.parse_args()

    if args.screen:
        screen_demo()
        return

    if args.screen_composite:
        mode = args.modes[0] if args.modes else "balanced"
        screen_composite_demo(mode)
        return

    if args.build_scores:
        symbols = [s.strip().upper() for s in args.symbols] if args.symbols else _load_pool()
        build_scores_demo(symbols, modes=args.modes, refresh=args.score_refresh)
        return

    symbols = [s.strip().upper() for s in args.symbols] if args.symbols else _load_pool()
    build(symbols, workers=args.workers, force_full=args.full, throttle=args.throttle)

    # 日更一步到位:原始資料剛更新完 → 直接用本機快取刷新當天 scores (0 API)。
    # scores 失敗不影響已完成的原始快取更新 (獨立 try),可稍後單獨 --build-scores 補。
    if not args.no_scores:
        print("\n── 接著刷新當天綜合分 scores (讀剛更新的本機快取,0 API) ──")
        try:
            build_scores_demo(symbols, modes=args.modes, refresh=False)
        except Exception as e:
            print(f"⚠️ scores 刷新失敗 (原始快取已更新;可稍後單獨跑 python build_cache.py --build-scores):{e}")


if __name__ == "__main__":
    main()
