"""
TEJ 全市場歷史批次匯入器
================================================================================
用途:TEJ Pro 沒有 API,只能用本機用戶端手動批次匯出 (單次查詢上限約 1 年)。這支
      腳本讀取你丟進 tej_exports/inbox*/ 的多份年度 xlsx 匯出檔,正規化欄位對齊
      FinMind 慣例,合併去重後存成獨立的 Parquet 歷史庫。

      跟 core/data_cache.py 的 finmind_cache 刻意分開存放:兩者信任等級不同。
      TEJ 這份是「人工批次匯入、無 PIT 保證」,只供 §12 全市場擴池規劃書 Phase 2
      的粗篩規則回溯驗證用,不進生產環境的每日 PIT 評分管線。

支援兩種資料集 (--dataset 切換):

  price_valuation (預設,讀 tej_exports/inbox/):
    用 TEJ「未調整股價(日)」查詢精靈匯出,欄位順序:
      代號,名稱,年月日,開盤價,最高價,最低價,收盤價,成交量(千股),
      本益比-TSE,本益比-TEJ,股價淨值比-TSE,股價淨值比-TEJ,股利殖利率-TSE[,股利殖利率-TEJ]

  institutional_flow (讀 tej_exports/inbox_chip/):
    用 TEJ 籌碼資料庫「三大法人買賣超」查詢精靈匯出,已選欄位務必照這個順序勾:
      外資買賣超(千股), 投信買賣超(千股), 自營買賣超(千股)
    (代號/名稱/年月日三欄由查詢精靈自動附加在最前面,不用手動勾)

  fundamentals_quarterly (讀 tej_exports/inbox_fundamentals/):
    單季財報,已選欄位順序:歸屬母公司淨利(損)、每股盈餘(EPS)、ROE(A)稅後、營業利益(損失)
    (皆單季非累計;金融股無標準營業利益科目,該欄可能為空)

  revenue_growth (讀 tej_exports/inbox_revenue/):
    單月營收成長率 (年增率/YoY,非合併) 一個欄位

  industry_map (讀 tej_exports/inbox_industry/,靜態對照表,無日期):
    代號/名稱 + TSE產業_代碼/名稱 + TEJ產業_代碼/名稱 + TEJ子產業_代碼/名稱
    (查詢精靈會把每個產業欄位展開成 原始/代碼/名稱 三欄,只取代碼與名稱)

  tdcc_weekly (讀 tej_exports/inbox_tdcc/,集保股權分散週頻):
    1000張以上(比率)、1張以下(比率)、1-5張(比率)、5-10張(比率)、集保總人數、集保總張數(千股)

  director_pledge (讀 tej_exports/inbox_pledge/,公司治理月頻):
    董監質押%、董監持股%、集團名稱

用法:
  python tej_importer.py                                 # 匯入 price_valuation
  python tej_importer.py --dataset institutional_flow     # 匯入法人買賣超
  python tej_importer.py --dataset fundamentals_quarterly # 匯入單季財報
  python tej_importer.py --dataset revenue_growth         # 匯入月營收年增率

  股票範圍/日期範圍兩種資料集都要一致:上市+上櫃、不含 ETF、同一段日期,
  之後 Phase 2 才能用 (stock_id, date) 對齊合併。

限制:欄位對應寫死在 DATASETS[...]["column_map"],依查詢精靈目前的勾選順序。
      之後改變勾選組合或順序,要同步更新對應的 column_map。
================================================================================
"""
import os
import sys
import glob
import logging
import argparse
from pathlib import Path

import pandas as pd

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TEJ_CACHE_DIR = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))

# 依欄位「位置」對應,不依賴欄位名稱字串比對 (Excel 表頭在部分終端機/編碼環境下
# 讀出來會亂碼,但欄位順序穩定,位置對應比較保險)。
DATASETS = {
    "price_valuation": {
        "inbox": Path(project_root) / "tej_exports" / "inbox",
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "open",
            4: "max",
            5: "min",
            6: "close",
            7: "_volume_thousand_shares",   # 千股 → FinMind 慣例為股,需 ×1000
            8: "PER_TSE",
            9: "PER_TEJ",
            10: "PBR_TSE",
            11: "PBR_TEJ",
            12: "dividend_yield_TSE",
            13: "dividend_yield_TEJ",       # 選配欄位,不一定每份匯出都有
        },
        "thousand_cols": {"_volume_thousand_shares": "Trading_Volume"},
        "numeric_cols": ["open", "max", "min", "close", "PER_TSE", "PER_TEJ",
                          "PBR_TSE", "PBR_TEJ", "dividend_yield_TSE", "dividend_yield_TEJ"],
    },
    "institutional_flow": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_chip",
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "_foreign_net_thousand",
            4: "_trust_net_thousand",
            5: "_dealer_net_thousand",
        },
        "thousand_cols": {
            "_foreign_net_thousand": "foreign_net",
            "_trust_net_thousand": "trust_net",
            "_dealer_net_thousand": "dealer_net",
        },
        "numeric_cols": [],
    },
    # 單季財報 (歸屬母公司淨利/EPS/ROE 皆為單季、稅後);"date" 是季度期間 (如 "2026/03"),
    # 解析後為該月第一天,只當期間標籤用,不是真實公告日 (無 PIT 保證,見檔頭說明)。
    "fundamentals_quarterly": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_fundamentals",
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "_net_income_thousand",
            4: "eps",
            5: "roe_after_tax",
            6: "_operating_income_thousand",
        },
        "thousand_cols": {"_net_income_thousand": "net_income",
                           "_operating_income_thousand": "operating_income"},
        "numeric_cols": ["eps", "roe_after_tax"],
    },
    # 單月營收成長率 (年增率/YoY,非合併);"date" 同上,是月份期間標籤。
    "revenue_growth": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_revenue",
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "revenue_yoy_pct",
        },
        "thousand_cols": {},
        "numeric_cols": ["revenue_yoy_pct"],
    },
    # 靜態產業對照表 (無日期欄):存成單一 parquet,不逐股拆檔。
    "industry_map": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_industry",
        "static": True,
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            4: "tse_ind_code",
            5: "tse_ind_name",
            7: "tej_ind_code",
            8: "tej_ind_name",
            10: "tej_subind_code",
            11: "tej_subind_name",
        },
        "thousand_cols": {},
        "numeric_cols": [],
    },
    # 集保股權分散 (週頻,資料日=週五);known_date 對齊在分析端處理 (公布約次週初)。
    "tdcc_weekly": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_tdcc",
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "ratio_1000up",
            4: "ratio_le1",
            5: "ratio_1to5",
            6: "ratio_5to10",
            7: "holders",
            8: "total_lots_thousand",
        },
        "thousand_cols": {},
        "numeric_cols": ["ratio_1000up", "ratio_le1", "ratio_1to5", "ratio_5to10",
                          "holders", "total_lots_thousand"],
    },
    # 董監質押/持股 (月頻,"date"=年月期間標籤);集團名稱為文字欄,保留原樣。
    "director_pledge": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_pledge",
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "pledge_pct",
            4: "director_holding_pct",
            5: "group_name",
        },
        "thousand_cols": {},
        "numeric_cols": ["pledge_pct", "director_holding_pct"],
    },
}


def _load_one(path: Path, spec: dict) -> pd.DataFrame:
    df = pd.read_excel(path)
    n = df.shape[1]
    column_map = spec["column_map"]
    rename = {df.columns[i]: name for i, name in column_map.items() if i < n}
    df = df.rename(columns=rename)

    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    if spec.get("static"):
        return df[[c for c in column_map.values() if c in df.columns]].dropna(subset=["stock_id"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    for src, dst in spec["thousand_cols"].items():
        if src in df.columns:
            df[dst] = pd.to_numeric(df[src], errors="coerce") * 1000
            df = df.drop(columns=[src])

    for col in spec["numeric_cols"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["stock_id", "date"])


def load_inbox(dataset: str) -> pd.DataFrame:
    spec = DATASETS[dataset]
    inbox_dir = spec["inbox"]
    files = sorted(glob.glob(str(inbox_dir / "*.xlsx")))
    if not files:
        raise FileNotFoundError(f"{inbox_dir} 底下沒有找到任何 .xlsx 檔案")

    frames = []
    for f in files:
        logger.info(f"讀取 {f}")
        frames.append(_load_one(Path(f), spec))

    combined = pd.concat(frames, ignore_index=True)
    if spec.get("static"):
        return (combined.drop_duplicates(subset=["stock_id"], keep="last")
                        .sort_values("stock_id").reset_index(drop=True))
    combined = combined.sort_values(["stock_id", "date"])
    combined = combined.drop_duplicates(subset=["stock_id", "date"], keep="last")
    return combined.reset_index(drop=True)


def save_by_stock(df: pd.DataFrame, dataset: str, cache_dir: Path = TEJ_CACHE_DIR) -> int:
    out_dir = cache_dir / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for stock_id, g in df.groupby("stock_id"):
        p = out_dir / f"{stock_id}.parquet"
        tmp = p.with_suffix(".parquet.tmp")
        g.sort_values("date").reset_index(drop=True).to_parquet(tmp, index=False)
        os.replace(tmp, p)
        n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description="TEJ 全市場歷史批次匯入")
    parser.add_argument("--dataset", choices=list(DATASETS), default="price_valuation")
    parser.add_argument("--cache-dir", default=str(TEJ_CACHE_DIR), help="輸出 Parquet 根目錄")
    args = parser.parse_args()

    df = load_inbox(args.dataset)
    if DATASETS[args.dataset].get("static"):
        out = Path(args.cache_dir) / f"{args.dataset}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        logger.info(f"靜態對照表共 {len(df)} 檔,已寫入 {out}")
        return
    logger.info(f"合併後共 {len(df)} 列,{df['stock_id'].nunique()} 檔,"
                f"日期範圍 {df['date'].min()} ~ {df['date'].max()}")
    n = save_by_stock(df, args.dataset, Path(args.cache_dir))
    logger.info(f"已寫入 {n} 檔股票的 Parquet 至 {args.cache_dir}/{args.dataset}/")


if __name__ == "__main__":
    main()
