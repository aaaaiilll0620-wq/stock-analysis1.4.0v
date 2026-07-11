"""
本機資料快取層 (Parquet + DuckDB)
================================================================================
目的:FinMind 的歷史資料是唯讀、只往後追加的時間序列。把每檔的完整歷史抓一次存到
      本機 Parquet,之後回測 / 個股分析直接讀檔 = 0 次 API;每天只補「上次之後」的新
      資料 (增量極小)。跨股選股用 DuckDB 直接查同一批 Parquet,不用重複匯入。

分工:
  · 原始資料層 (本檔):每檔每資料集一個 Parquet,唯讀、只追加、保 PIT。
  · 查詢層 (DuckDB):duck_query() + tbl() 對 Parquet 跑 SQL,做跨股橫向選股。

原則:
  · 只快取「原始歷史」;as-of 時間切片邏輯仍留在 build_pit_stockdata (無未來函數)。
  · 純追加資料集 (股價/PER/籌碼/流通股) 只補增量;會被事後修正的 (財報/月營收) 整批覆蓋。
  · 快取預設放在專案外的非同步資料夾 (環境變數 FINMIND_CACHE 可覆蓋),避免 OneDrive 反覆同步。
================================================================================
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# 快取根目錄:預設家目錄下的 finmind_cache (刻意放 OneDrive 外)。可用環境變數覆蓋。
CACHE_DIR = Path(os.environ.get("FINMIND_CACHE", str(Path.home() / "finmind_cache")))
HISTORY_START = "2019-01-01"          # 每檔歷史抓取起點 (percentile / 中期動能需要 2~3 年)

# HistoryBundle 欄位 → FinMind dataset (與 core.backtest.fetch_history 對齊)
BUNDLE_DATASETS: Dict[str, str] = {
    "price": "TaiwanStockPrice",
    "per": "TaiwanStockPER",
    "revenue": "TaiwanStockMonthRevenue",
    "income": "TaiwanStockFinancialStatements",
    "balance": "TaiwanStockBalanceSheet",
    "cashflow": "TaiwanStockCashFlowsStatement",
    "chip": "TaiwanStockInstitutionalInvestorsBuySell",
    "shareholding": "TaiwanStockShareholding",
}
ALL_DATASETS: List[str] = list(BUNDLE_DATASETS.values())

# 純追加資料集 → 只補增量;其餘 (財報/月營收) 會被事後修正 → 每次整批覆蓋。
APPEND_ONLY = {
    "TaiwanStockPrice", "TaiwanStockPER",
    "TaiwanStockInstitutionalInvestorsBuySell", "TaiwanStockShareholding",
}

# 去重鍵 (依資料集特性;同日可能多列)。找不到就退回用 date,再退回全欄位。
_DEDUP_KEYS: Dict[str, List[str]] = {
    "TaiwanStockInstitutionalInvestorsBuySell": ["date", "name"],
    "TaiwanStockFinancialStatements": ["date", "type"],
    "TaiwanStockBalanceSheet": ["date", "type"],
    "TaiwanStockCashFlowsStatement": ["date", "type"],
    "TaiwanStockMonthRevenue": ["revenue_year", "revenue_month"],
}


# ------------------------------------------------------------------------------
# 儲存後端 (可抽換:預設 Parquet on disk;測試可換記憶體 store)
# ------------------------------------------------------------------------------
class _ParquetStore:
    """每檔每資料集一個 Parquet:<CACHE_DIR>/<dataset>/<stock_id>.parquet。原子寫入。"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, dataset: str, stock_id: str) -> Path:
        return self.root / dataset / f"{stock_id}.parquet"

    def read(self, dataset: str, stock_id: str) -> Optional[pd.DataFrame]:
        p = self._path(dataset, stock_id)
        if p.exists():
            try:
                return pd.read_parquet(p)
            except Exception as e:
                logger.warning(f"讀取快取失敗 {p}: {e}")
        return None

    def write(self, dataset: str, stock_id: str, df: pd.DataFrame) -> None:
        p = self._path(dataset, stock_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)               # 同一檔案系統上為原子操作

    def exists(self, dataset: str, stock_id: str) -> bool:
        return self._path(dataset, stock_id).exists()

    def glob(self, dataset: str) -> str:
        return str(self.root / dataset / "*.parquet")


_store = _ParquetStore(CACHE_DIR)


def set_store(store) -> None:
    """抽換儲存後端 (供測試注入記憶體 store)。"""
    global _store
    _store = store


def get_store():
    return _store


# ------------------------------------------------------------------------------
# 核心:讀取 / 去重 / 增量更新
# ------------------------------------------------------------------------------
def _dedup(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    keys = _DEDUP_KEYS.get(dataset)
    keys = [k for k in keys if k in df.columns] if keys else []
    if not keys and "date" in df.columns:
        keys = ["date"]
    if "date" in df.columns:
        df = df.sort_values("date")
    df = df.drop_duplicates(subset=keys, keep="last") if keys else df.drop_duplicates(keep="last")
    return df.reset_index(drop=True)


def read_cached(dataset: str, stock_id: str) -> Optional[pd.DataFrame]:
    """讀本機快取 (無則 None)。"""
    return _store.read(dataset, stock_id)


def update_dataset(api, dataset: str, stock_id: str, force_full: bool = False,
                   history_start: str = HISTORY_START) -> Tuple[Optional[pd.DataFrame], int]:
    """
    更新單一 (dataset, stock) 的快取。回傳 (合併後 df, 本次 API 呼叫次數)。
      · 純追加資料集:從本機最後日期起補增量 (含最後一天,以吸收當天更新),再併回去重。
      · 會被修正的資料集 (財報/月營收) 或 force_full:整批重抓覆蓋。
    """
    existing = _store.read(dataset, stock_id)
    incremental = (existing is not None and not force_full
                   and dataset in APPEND_ONLY and "date" in existing.columns
                   and not existing.empty)
    if incremental:
        start = str(pd.to_datetime(existing["date"], errors="coerce").max().date())
        base: Optional[pd.DataFrame] = existing
    else:
        start = history_start
        base = None

    try:
        new = api.get_data(dataset=dataset, data_id=stock_id, start_date=start)
    except Exception as e:
        logger.warning(f"[{stock_id}] {dataset} 抓取失敗: {e}")
        return existing, 1

    if new is None or (hasattr(new, "empty") and new.empty):
        return existing, 1                       # 沒有新資料,保留現況 (仍算 1 次 API)

    combined = new if base is None else pd.concat([base, new], ignore_index=True)
    combined = _dedup(combined, dataset)
    _store.write(dataset, stock_id, combined)
    return combined, 1


# ------------------------------------------------------------------------------
# 查詢層:DuckDB 直接查 Parquet (跨股選股)
# ------------------------------------------------------------------------------
def tbl(dataset: str) -> str:
    """回傳可嵌入 SQL 的 read_parquet(...) 片段:跨全部股票、依欄名聯集 (容忍 schema 差異)。"""
    return f"read_parquet('{_store.glob(dataset)}', union_by_name=true)"


def duck_query(sql: str) -> pd.DataFrame:
    """對 Parquet 快取跑 DuckDB SQL,回傳 DataFrame。用 tbl('<dataset>') 產生資料來源片段。

    範例 (全市場最新一日、依 PER 由低到高的價值選股):
        import core.data_cache as dc
        sql = f'''
            SELECT stock_id, date, PER, PBR, dividend_yield
            FROM {dc.tbl("TaiwanStockPER")}
            QUALIFY row_number() OVER (PARTITION BY stock_id ORDER BY date DESC) = 1
            ORDER BY PER
        '''
        dc.duck_query(sql)
    """
    import duckdb
    con = duckdb.connect()
    try:
        return con.execute(sql).df()
    finally:
        con.close()


# ------------------------------------------------------------------------------
# 讀寫穿透快取 (Read-through / Write-through):把 FinMind DataLoader 包一層,
# 讓『回測』與『個股即時分析』只要打 API 就自動落地快取、之後自動重用。
# ------------------------------------------------------------------------------
CACHE_ENABLED = True          # 全域開關:包住 DataProvider._api 後,所有查詢自動走快取
FORCE_REFRESH = False         # True → 一律重抓刷新舊快取 (main.py --refresh / build_cache --full)
STALE_DAYS = 2                # 純追加資料集:本機最後日期距今 <= 此天數即視為新鮮、不再打 API
TODAY_OVERRIDE = None         # 測試用:固定「今天」(YYYY-MM-DD);正式為 None → 用系統當日

# 會走穿透快取的『每股』資料集 (需帶 data_id)。清單外或無 data_id 者原樣直通,不快取。
_CACHEABLE = set(ALL_DATASETS) | {"TaiwanStockMarginPurchaseShortSale"}


def _today(today=None):
    if today is not None:
        return pd.Timestamp(today)
    if TODAY_OVERRIDE:
        return pd.Timestamp(TODAY_OVERRIDE)
    return pd.Timestamp.today().normalize()


def ensure_fresh(api, dataset: str, stock_id: str, force: bool = False,
                 today=None, stale_days: Optional[int] = None) -> Tuple[Optional[pd.DataFrame], int]:
    """
    確保 (dataset, stock) 的本機快取夠新;必要時才打 API。回傳 (完整歷史 df, api 呼叫次數)。
      · 快取不存在 → 抓完整歷史。
      · 純追加資料集 (股價/PER/籌碼/流通股):最後日期距今 <= stale_days 就用快取 (0 API),
        否則只補增量 (1 次小 API)。
      · 會被修正的資料集 (財報/月營收):有就用,不自動重抓;force 才整批刷新。
    """
    stale_days = STALE_DAYS if stale_days is None else stale_days
    existing = _store.read(dataset, stock_id)
    if existing is not None and not force:
        if dataset not in APPEND_ONLY:
            return existing, 0                      # restated:有就用,force 才刷新
        if "date" in existing.columns and not existing.empty:
            last = pd.to_datetime(existing["date"], errors="coerce").max()
            if pd.notna(last) and (_today(today) - last).days <= stale_days:
                return existing, 0                  # 純追加:夠新就用
    return update_dataset(api, dataset, stock_id, force_full=force)


class CachingDataLoader:
    """
    包住 FinMind DataLoader 的透明快取代理。對『每股 + 允許清單內』的 get_data:
    先確保本機完整歷史夠新 (缺/過期才打 API),再依呼叫端的 start_date/end_date 切片回傳。
    其餘查詢 (無 data_id、如 TaiwanStockInfo,或清單外) 原樣直通、不快取。
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        # login_by_token / 其他方法直接代理到底層 loader
        return getattr(self._inner, name)

    def get_data(self, dataset=None, data_id=None, start_date=None, end_date=None, **kwargs):
        if (not CACHE_ENABLED) or (not data_id) or (dataset not in _CACHEABLE):
            return self._inner.get_data(dataset=dataset, data_id=data_id,
                                        start_date=start_date, end_date=end_date, **kwargs)
        df, _ = ensure_fresh(self._inner, dataset, str(data_id), force=FORCE_REFRESH)
        if df is None:
            return pd.DataFrame()
        out = df
        if "date" in out.columns:
            if start_date:
                out = out[out["date"].astype(str) >= str(start_date)]
            if end_date:
                out = out[out["date"].astype(str) <= str(end_date)]
        return out.reset_index(drop=True)


def install(inner):
    """把底層 DataLoader 包成快取代理 (已包過則原樣回傳)。"""
    return inner if isinstance(inner, CachingDataLoader) else CachingDataLoader(inner)


def unwrap(api):
    """取回底層原始 DataLoader (build_cache 直接建庫時用,避免走代理的新鮮度判斷)。"""
    return api._inner if isinstance(api, CachingDataLoader) else api
