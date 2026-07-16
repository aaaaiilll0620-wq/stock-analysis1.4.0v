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

  fundamentals_quarterly (讀 tej_exports/inbox_fundamentals/,7欄舊版,已被 financial_statements 取代):
    單季財報,已選欄位順序:歸屬母公司淨利(損)、每股盈餘(EPS)、ROE(A)稅後、營業利益(損失)
    (皆單季非累計;金融股無標準營業利益科目,該欄可能為空)

  financial_statements (讀 tej_exports/inbox_fundamentals/,16欄完整版):
    IFRS 三大財報單季,查詢精靈欄位順序:
      證券代碼(含名稱), 年月, 季別, 營業收入淨額, 營業毛利, 營業利益, 歸屬母公司淨利(損),
      每股盈餘, 常續性稅後淨利, 資產總額, 負債總額, 流動資產, 流動負債, 股東權益總額,
      來自營運之現金流量, 購置不動產廠房設備(含預付)-CFI
    (金額皆千元 → 匯入轉為元;capex 為 CFI 流出,原始多為負值,保留正負號)

  revenue_growth (讀 tej_exports/inbox_revenue/,4欄舊版,已被 monthly_revenue 取代):
    單月營收成長率 (年增率/YoY,非合併) 一個欄位

  monthly_revenue (讀 tej_exports/inbox_revenue/,8欄完整版):
    查詢精靈欄位順序:
      證券代碼(含名稱), 年月, 營收發布日, 單月營收成長率%, 單月營收(千元),
      去年單月營收(千元), 累計營收(千元), 去年累計營收(千元)
    (release_date=真實公告日,供 PIT 對齊;金額千元 → 匯入轉為元)

  industry_map (讀 tej_exports/inbox_industry/,靜態對照表,無日期):
    代號/名稱 + TSE產業_代碼/名稱 + TEJ產業_代碼/名稱 + TEJ子產業_代碼/名稱
    (查詢精靈會把每個產業欄位展開成 原始/代碼/名稱 三欄,只取代碼與名稱)

  institutional_gross (讀 tej_exports/inbox_chip_gross/,法人毛額+持股率,15欄):
    用 TEJ 籌碼資料庫查詢精靈,已選欄位順序:
      外資買賣超(千股), 投信買賣超(千股), 自營買賣超(千股),
      外資買進張數, 外資賣出張數, 投信買進張數, 投信賣出張數,
      自營商買進張數, 自營商賣出張數, 外資總投資股率%, 投信持股率%, 自營持股率%
    (張 ≡ 千股 → 匯入 ×1000 轉股;供 institutional_participation 法人成交占比,
     淨額算不出毛額 → 收集器 2026-07-16 起有存,更早的靠這份種子)

  margin_balance (讀 tej_exports/inbox_margin/,融資融券,10欄):
    已選欄位:融資餘額(張), 融資買進(張), 融資賣出(張), 融資增減(張), 融資使用率,
             融券餘額(張), 券資比
    (張與 FinMind MarginPurchaseTodayBalance 同單位;分析只用融資餘額,其餘留供研究)

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
        "expect_cols": 7,          # 舊版 7 欄匯出;同 inbox 的 16 欄新檔由 financial_statements 讀
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
        "expect_cols": 4,          # 舊版 4 欄匯出;同 inbox 的 8 欄新檔由 monthly_revenue 讀
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "revenue_yoy_pct",
        },
        "thousand_cols": {},
        "numeric_cols": ["revenue_yoy_pct"],
    },
    # 月營收完整版 (取代 revenue_growth):原始金額供 TTM 營收/P-S 與動能計算,
    # release_date 為真實公告日 (PIT 對齊用)。證券代碼欄為「1101 台泥」合併格式 → 拆分。
    "monthly_revenue": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_revenue",
        "expect_cols": 8,
        "id_name_combined": True,
        "date_format": "%Y%m",     # 年月 = 201901
        "column_map": {
            0: "stock_id",
            1: "date",
            2: "release_date",
            3: "revenue_yoy_pct",
            4: "_revenue_thousand",
            5: "_revenue_ly_thousand",
            6: "_cum_revenue_thousand",
            7: "_cum_revenue_ly_thousand",
        },
        "extra_date_cols": {"release_date": "%Y%m%d"},
        "thousand_cols": {
            "_revenue_thousand": "revenue",
            "_revenue_ly_thousand": "revenue_last_year",
            "_cum_revenue_thousand": "cum_revenue",
            "_cum_revenue_ly_thousand": "cum_revenue_last_year",
        },
        "numeric_cols": ["revenue_yoy_pct"],
    },
    # 三大財報完整版 (取代 fundamentals_quarterly):單季 IFRS,金額千元 → 元。
    # capex (購置不動產廠房設備-CFI) 為投資活動流出,原始多為負值,保留正負號
    # (下游 FCF = OCF + capex(負) 的既有邏輯直接相容)。
    "financial_statements": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_fundamentals",
        "expect_cols": 16,
        "id_name_combined": True,
        "date_format": "%Y%m",     # 年月 = 201903 (季末月,期間標籤,非公告日)
        "column_map": {
            0: "stock_id",
            1: "date",
            2: "quarter",
            3: "_revenue_thousand",
            4: "_gross_profit_thousand",
            5: "_operating_income_thousand",
            6: "_net_income_thousand",
            7: "eps",
            8: "_recurring_ni_thousand",
            9: "_total_assets_thousand",
            10: "_total_liab_thousand",
            11: "_current_assets_thousand",
            12: "_current_liab_thousand",
            13: "_equity_thousand",
            14: "_ocf_thousand",
            15: "_capex_thousand",
        },
        "thousand_cols": {
            "_revenue_thousand": "revenue",
            "_gross_profit_thousand": "gross_profit",
            "_operating_income_thousand": "operating_income",
            "_net_income_thousand": "net_income",
            "_recurring_ni_thousand": "recurring_net_income",
            "_total_assets_thousand": "total_assets",
            "_total_liab_thousand": "total_liabilities",
            "_current_assets_thousand": "current_assets",
            "_current_liab_thousand": "current_liabilities",
            "_equity_thousand": "equity",
            "_ocf_thousand": "operating_cash_flow",
            "_capex_thousand": "capex",
        },
        "numeric_cols": ["eps", "quarter"],
    },
    # 法人買賣毛額+持股率 (日頻):institutional_participation (法人成交占比) 需要買+賣總量;
    # 買賣超淨額已有 institutional_flow,此處只取毛額 (張≡千股 → ×1000) 與持股率。
    "institutional_gross": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_chip_gross",
        "expect_cols": 15,
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            6: "_foreign_buy_lots",
            7: "_foreign_sell_lots",
            8: "_trust_buy_lots",
            9: "_trust_sell_lots",
            12: "foreign_holding_pct",
            13: "trust_holding_pct",
        },
        "thousand_cols": {
            "_foreign_buy_lots": "foreign_buy",
            "_foreign_sell_lots": "foreign_sell",
            "_trust_buy_lots": "trust_buy",
            "_trust_sell_lots": "trust_sell",
        },
        "numeric_cols": ["foreign_holding_pct", "trust_holding_pct"],
    },
    # 融資融券 (日頻,張 ≡ FinMind 單位,不換算)。分析用 margin_balance,融券留供研究。
    "margin_balance": {
        "inbox": Path(project_root) / "tej_exports" / "inbox_margin",
        "expect_cols": 10,
        "column_map": {
            0: "stock_id",
            1: "stock_name",
            2: "date",
            3: "margin_balance",
            8: "short_balance",
        },
        "thousand_cols": {},
        "numeric_cols": ["margin_balance", "short_balance"],
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

    # 欄數守門:同一個 inbox 可能同時放新舊版匯出檔 (欄位組合不同),
    # 只讀欄數吻合的檔案,其餘跳過 (由對應的另一個 dataset 讀)。
    expect = spec.get("expect_cols")
    if expect is not None and n != expect:
        logger.info(f"  跳過 {path.name}:{n} 欄 != 本資料集預期 {expect} 欄")
        return pd.DataFrame()

    column_map = spec["column_map"]
    rename = {df.columns[i]: name for i, name in column_map.items() if i < n}
    df = df.rename(columns=rename)

    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    # 查詢精靈部分匯出格式的證券代碼欄為「1101 台泥」合併格式 → 拆成代號+名稱
    if spec.get("id_name_combined"):
        parts = df["stock_id"].str.split(n=1)
        df["stock_id"] = parts.str[0].str.strip()
        df["stock_name"] = parts.str[1].str.strip()
    if spec.get("static"):
        return df[[c for c in column_map.values() if c in df.columns]].dropna(subset=["stock_id"])

    date_fmt = spec.get("date_format")
    if date_fmt:
        # 整數期間標籤 (如 201901) → 先轉純數字字串再按格式解析
        raw = df["date"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        df["date"] = pd.to_datetime(raw, format=date_fmt, errors="coerce").dt.strftime("%Y-%m-%d")
    else:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col, fmt in (spec.get("extra_date_cols") or {}).items():
        if col in df.columns:
            raw = df[col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            df[col] = pd.to_datetime(raw, format=fmt, errors="coerce").dt.strftime("%Y-%m-%d")

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

    frames = [x for x in frames if not x.empty]
    if not frames:
        raise FileNotFoundError(f"{inbox_dir} 底下沒有欄數吻合本資料集的檔案")
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
