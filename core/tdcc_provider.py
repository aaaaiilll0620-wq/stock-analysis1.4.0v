"""
TDCC 集保戶股權分散表爬蟲模組 (骨架)
================================================================================
資料來源:台灣集中保管結算所 (TDCC) 公開資料
  https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5
  → 回傳「最新一週」全市場所有股票的股權分散表 (CSV, UTF-8)

特性與定位
--------------------------------------------------------------------------------
* 每週五傍晚更新,結算基準日通常為當週最後一個交易日 → 先天有最多約一週 lag。
* 完全免費、公開,獨立於 FinMind,不受 FinMind 付費分級限制。
* 因為是「週更 + 有 lag」的結構性資料,本系統將其定位為
  【確認層 / 背離警示】,而非即時進場觸發訊號 (詳見檔尾 SCORING NOTE)。

本模組只負責「取得 → 快取 → 解析 → 計算週變化」,不介入評分;
是否讓它影響分數由 main.Config.USE_TDCC_CHIP 決定 (預設 False = 純參考)。

⚠️ 這是骨架:HTTP 抓取需要對外網路,請在本機有網路的環境執行。
    離線時本模組仍可 import,並會以快取 (若有) 或回傳「資料不足」降級。
================================================================================
"""

from __future__ import annotations

import os
import sys
import io
import glob
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 持股分級對照 (TDCC「持股分級」欄位為 1~17 的整數)
#   單位:股。1 張 = 1,000 股;千張 = 1,000,000 股。
#   註:實際級距偶有微調,若解析異常請對照當期 CSV 的「持股分級」文字調整。
# ------------------------------------------------------------------------------
HOLDING_LEVELS: Dict[int, str] = {
    1: "1-999 股", 2: "1,000-5,000", 3: "5,001-10,000", 4: "10,001-15,000",
    5: "15,001-20,000", 6: "20,001-30,000", 7: "30,001-40,000",
    8: "40,001-50,000", 9: "50,001-100,000", 10: "100,001-200,000",
    11: "200,001-400,000", 12: "400,001-600,000", 13: "600,001-800,000",
    14: "800,001-1,000,000", 15: "1,000,001 以上 (千張大戶)",
    16: "差異數調整", 17: "合計",
}

THOUSAND_LOT_LEVEL = 15               # 千張大戶 (>1,000 張 = >1,000,000 股)
BIG_HOLDER_LEVELS = (12, 13, 14, 15)  # 400 張以上視為「大戶」
RETAIL_LEVELS = (1, 2, 3)             # 5 張以下視為「散戶」(可依需求調整)
TOTAL_LEVEL = 17                      # 合計列


class TDCCProvider:
    """TDCC 股權分散表:抓取 / 快取 / 解析 / 週變化。"""

    OPENDATA_URL = "https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5"
    # 快取目錄:PyInstaller 打包時改用 exe 所在目錄 (見 data_provider 同一處理)
    if getattr(sys, "frozen", False):
        CACHE_DIR = os.path.join(os.path.dirname(sys.executable), "data", "tdcc")
    else:
        CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "data", "tdcc")
    STALE_DAYS = 5                    # 快取超過 N 天才重新抓 (呼應週更頻率,避免重複下載)
    REQUEST_TIMEOUT = 20

    # ==========================================================================
    # 1) 取得原始資料 (需網路)
    # ==========================================================================
    @classmethod
    def fetch_all_latest(cls) -> Optional[pd.DataFrame]:
        """
        下載 TDCC 最新一週「全市場」股權分散表原始 CSV,回傳正規化後的 DataFrame:
            欄位 = [date, stock_id, level, people, shares, percent]
        需要對外網路;失敗回傳 None (不拋例外,交由上層降級)。
        """
        try:
            import requests  # 延遲載入:離線 import 本模組時不需要 requests
        except ImportError:
            logger.warning("未安裝 requests,無法抓取 TDCC 資料;請 pip install requests。")
            return None

        try:
            resp = requests.get(cls.OPENDATA_URL, timeout=cls.REQUEST_TIMEOUT)
            resp.encoding = "utf-8"
            if resp.status_code != 200 or not resp.text:
                logger.warning(f"TDCC 回應異常 status={resp.status_code}")
                return None
            raw = pd.read_csv(io.StringIO(resp.text))
        except Exception as e:
            logger.warning(f"TDCC 下載/解析失敗: {e}")
            return None

        return cls._normalize(raw)

    @staticmethod
    def _normalize(raw: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        將 TDCC 原始欄位 (中文) 正規化。原始欄位常見為:
            資料日期, 證券代號, 持股分級, 人數, 股數, 占集保庫存數比例%
        欄名偶有空白/全形差異,故以「包含關鍵字」比對。
        """
        if raw is None or raw.empty:
            return None

        def _find(cols, *keys):
            for c in cols:
                cs = str(c).replace(" ", "")
                if any(k in cs for k in keys):
                    return c
            return None

        cols = list(raw.columns)
        col_date = _find(cols, "資料日期", "date")
        col_id = _find(cols, "證券代號", "stock_id", "代號")
        col_lv = _find(cols, "持股分級", "分級", "level")
        col_ppl = _find(cols, "人數", "people")
        col_sh = _find(cols, "股數", "shares")
        col_pct = _find(cols, "比例", "percent", "占")

        need = [col_date, col_id, col_lv, col_sh, col_pct]
        if any(c is None for c in need):
            logger.warning(f"TDCC 欄位比對失敗,實際欄位: {cols}")
            return None

        df = pd.DataFrame({
            "date": raw[col_date].astype(str).str.strip(),
            "stock_id": raw[col_id].astype(str).str.strip(),
            "level": pd.to_numeric(raw[col_lv], errors="coerce"),
            "people": pd.to_numeric(raw[col_ppl], errors="coerce") if col_ppl else 0,
            "shares": pd.to_numeric(raw[col_sh], errors="coerce"),
            "percent": pd.to_numeric(raw[col_pct], errors="coerce"),
        }).dropna(subset=["level"])
        df["level"] = df["level"].astype(int)
        return df

    # ==========================================================================
    # 2) 快取 (每個「資料日期」存一份快照,用來算週變化)
    # ==========================================================================
    @classmethod
    def _ensure_cache_dir(cls):
        os.makedirs(cls.CACHE_DIR, exist_ok=True)

    @classmethod
    def _snapshot_path(cls, data_date: str) -> str:
        safe = str(data_date).replace("/", "-").replace(" ", "")
        return os.path.join(cls.CACHE_DIR, f"tdcc_{safe}.parquet")

    @classmethod
    def list_snapshot_dates(cls) -> List[str]:
        """回傳快取中已有的資料日期 (由舊到新排序)。"""
        cls._ensure_cache_dir()
        dates = []
        for p in glob.glob(os.path.join(cls.CACHE_DIR, "tdcc_*.parquet")):
            name = os.path.basename(p)[len("tdcc_"):-len(".parquet")]
            dates.append(name)
        return sorted(dates)

    @classmethod
    def save_snapshot(cls, df: pd.DataFrame) -> Optional[str]:
        """把一份全市場快照存進快取 (以其 date 命名);回傳資料日期。"""
        if df is None or df.empty:
            return None
        cls._ensure_cache_dir()
        data_date = str(df["date"].iloc[0])
        path = cls._snapshot_path(data_date)
        try:
            df.to_parquet(path, index=False)
        except Exception:
            # 無 pyarrow 時退回 csv
            df.to_csv(path.replace(".parquet", ".csv"), index=False)
        return data_date

    @classmethod
    def _load_snapshot(cls, data_date: str) -> Optional[pd.DataFrame]:
        p = cls._snapshot_path(data_date)
        try:
            if os.path.exists(p):
                return pd.read_parquet(p)
            csv = p.replace(".parquet", ".csv")
            if os.path.exists(csv):
                return pd.read_csv(csv, dtype={"stock_id": str})
        except Exception as e:
            logger.warning(f"讀取 TDCC 快照失敗 {data_date}: {e}")
        return None

    @classmethod
    def update(cls) -> Optional[str]:
        """
        視需要更新快取:若最新快照已在 STALE_DAYS 內則跳過網路 (呼應週更頻率),
        否則抓取最新一週並存檔。回傳最新資料日期 (或 None)。
        每次「排行掃描」開始前呼叫一次即可,不需每檔都抓 (全市場一次到位)。
        """
        existing = cls.list_snapshot_dates()
        if existing:
            try:
                last = datetime.strptime(existing[-1][:10].replace("/", "-"), "%Y-%m-%d")
                if datetime.now() - last < timedelta(days=cls.STALE_DAYS):
                    return existing[-1]      # 仍新鮮,不重抓
            except Exception:
                pass
        df = cls.fetch_all_latest()
        if df is None:
            return existing[-1] if existing else None
        return cls.save_snapshot(df)

    # ==========================================================================
    # 3) 單檔解析:千張大戶佔比 / 大戶佔比 / 散戶佔比
    # ==========================================================================
    @classmethod
    def _distribution_for(cls, stock_id: str, snap: pd.DataFrame) -> Optional[Dict[str, float]]:
        if snap is None or snap.empty:
            return None
        sub = snap[snap["stock_id"].astype(str) == str(stock_id)]
        if sub.empty:
            return None
        by_level = sub.set_index("level")["percent"].to_dict()

        def _pct(level):
            return float(by_level.get(level, 0.0) or 0.0)

        thousand = _pct(THOUSAND_LOT_LEVEL)
        big = sum(_pct(l) for l in BIG_HOLDER_LEVELS)
        retail = sum(_pct(l) for l in RETAIL_LEVELS)
        return {
            "thousand_lot_ratio": round(thousand, 3),   # 千張大戶佔比 %
            "big_holder_ratio": round(big, 3),          # 400 張以上大戶佔比 %
            "retail_ratio": round(retail, 3),           # 散戶佔比 %
        }

    # ==========================================================================
    # 4) 週變化 + 對外主入口
    # ==========================================================================
    @classmethod
    def get_chip_metrics(cls, stock_id: str) -> Dict[str, object]:
        """
        回傳單檔 TDCC 籌碼結構指標 (供顯示與可選評分):
            {
              data_date, thousand_lot_ratio, big_holder_ratio, retail_ratio,
              thousand_lot_wchange, big_holder_wchange,   # 週變化 (百分點)
              is_stale, available
            }
        找不到資料時 available=False,所有數值為 0,交由上層降級 (不影響現有日線評分)。
        """
        empty = {
            "data_date": None, "thousand_lot_ratio": 0.0, "big_holder_ratio": 0.0,
            "retail_ratio": 0.0, "thousand_lot_wchange": 0.0, "big_holder_wchange": 0.0,
            "is_stale": True, "available": False,
        }

        dates = cls.list_snapshot_dates()
        if not dates:
            return empty

        latest = cls._load_snapshot(dates[-1])
        cur = cls._distribution_for(stock_id, latest)
        if cur is None:
            return empty

        # 週變化:與前一份快照相比 (若只有一份則週變化為 0)
        tl_wchg = bh_wchg = 0.0
        if len(dates) >= 2:
            prev = cls._load_snapshot(dates[-2])
            prev_dist = cls._distribution_for(stock_id, prev)
            if prev_dist:
                tl_wchg = round(cur["thousand_lot_ratio"] - prev_dist["thousand_lot_ratio"], 3)
                bh_wchg = round(cur["big_holder_ratio"] - prev_dist["big_holder_ratio"], 3)

        # 新鮮度:資料日期距今超過 ~10 天視為過期 (週更 + 節假日緩衝)
        is_stale = True
        try:
            d = datetime.strptime(str(dates[-1])[:10].replace("/", "-"), "%Y-%m-%d")
            is_stale = (datetime.now() - d) > timedelta(days=10)
        except Exception:
            pass

        return {
            "data_date": dates[-1],
            "thousand_lot_ratio": cur["thousand_lot_ratio"],
            "big_holder_ratio": cur["big_holder_ratio"],
            "retail_ratio": cur["retail_ratio"],
            "thousand_lot_wchange": tl_wchg,
            "big_holder_wchange": bh_wchg,
            "is_stale": is_stale,
            "available": True,
        }


# ==============================================================================
# SCORING NOTE — 這份資料「該不該影響分數」的設計說明
# ------------------------------------------------------------------------------
# 定位:週更 + 有 lag → 不當即時進場觸發,當「確認層 / 背離警示」,小權重有界影響。
#
# 建議的評分掛法 (已在 scoring_manager._get_whale_score 以 ±8 有界實作,預設關閉):
#   * 千張大戶/大戶佔比「週增」 → 大戶回補、籌碼收斂 → 小幅加分 (確認)。
#   * 佔比「週減」 → 大戶調節、籌碼鬆動 → 小幅減分。
#   * 【背離警示 · 最有價值】股價/日線法人在買、但大戶佔比週減
#     (大戶趁強出貨給散戶) → 額外扣分,並可於 advisor 產生警語。
#
# 開關:main.Config.USE_TDCC_CHIP
#   False (預設) → 純參考,只顯示在確認模式,不影響分數。
#   True          → big_holder_weekly_change 進入 whale 微調 (仍有 ±8 上限)。
#
# 使用流程 (本機、有網路):
#   1) 每次排行掃描前呼叫一次 TDCCProvider.update()  (全市場一次抓好、存快照)。
#   2) 每檔 TDCCProvider.get_chip_metrics(stock_id) 取結構指標與週變化。
#   3) 需要週變化需累積「至少兩週」快照;第一次跑只有當週、週變化為 0 屬正常。
# ==============================================================================
