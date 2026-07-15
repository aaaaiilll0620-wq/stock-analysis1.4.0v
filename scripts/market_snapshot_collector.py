"""TWSE/TPEx 全市場每日快照收集器 (§15 擴池 Phase 1,0 FinMind API)
================================================================================
用途:每日收盤後抓 TWSE/TPEx 官方開放端點的全市場快照 (價格/成交量/PE/PBR/殖利率),
      正規化成 TEJ price_valuation 的同一套欄位,存成單日 Parquet 逐日累積。

      歷史種子 = tej_cache/price_valuation (2019-01 ~ 2026-07-14,PER_TSE 與官方
      PEratio 已實測 100% 一致);本收集器只負責種子日之後的增量。
      下游 scripts/universe_screen_daily.py 用 DuckDB 把兩邊 union 起來跑 L1+L2 粗篩。

特性:
  - 端點不支援歷史日期,回傳的是「最新交易日」→ 假日/重複執行自動變 no-op (冪等)
  - **發布時序 (實測)**:TPEx 當天 ~14-16 點翻日,TWSE openapi 隔天清晨才翻日
    → 排程設在「隔天早上 08:30 收 T-1」(兩板此時一致);傍晚收永遠湊不齊
  - 四端點資料日必須一致才落地,避免混到跨日資料
  - 重試 + 列數 sanity check;失敗以非零 exit code 結束 (bat 記 log)
  - 漏收的日子無法回補 → 用 TEJ 手動匯出丟 tej_exports/inbox/ 重跑 tej_importer 補洞

用法:
  python scripts/market_snapshot_collector.py            # 收今日 (最新交易日) 快照
  python scripts/market_snapshot_collector.py --force    # 覆寫既有檔案
  python scripts/market_snapshot_collector.py --out-dir D:\\somewhere
================================================================================
"""
import os
import sys
import time
import argparse
import logging
from pathlib import Path

import requests
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
OUT_DIR = MARKET_CACHE / "price_valuation_daily"
CHIP_DIR = MARKET_CACHE / "institutional_flow_daily"

ENDPOINTS = {
    "twse_price": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    "twse_pe":    "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "tpex_price": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
    "tpex_pe":    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
}
MIN_ROWS = {"twse_price": 800, "twse_pe": 800, "tpex_price": 600, "tpex_pe": 600}


def fetch(name: str, url: str, tries: int = 5) -> pd.DataFrame:
    for i in range(tries):
        try:
            r = requests.get(url, timeout=60,
                             headers={"accept": "application/json", "user-agent": "Mozilla/5.0"})
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            if len(df) < MIN_ROWS[name]:
                raise ValueError(f"{name} 只回 {len(df)} 筆,低於 sanity 下限 {MIN_ROWS[name]}")
            return df
        except Exception as e:
            logger.warning(f"{name} 第 {i+1} 次失敗: {e}")
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def roc_to_iso(roc: str) -> str:
    roc = str(roc).strip()
    return f"{int(roc[:-4]) + 1911}-{roc[-4:-2]}-{roc[-2:]}"


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def is_common_stock(code: pd.Series) -> pd.Series:
    """四位數且不以 0 開頭 = 普通股 (排除 ETF 00xx、權證/受益證券等 5-6 位代號),同 TEJ 匯出範圍。"""
    return code.str.fullmatch(r"[1-9]\d{3}")


def collect() -> pd.DataFrame:
    # 各端點收盤後的發布時間不同,實測 TWSE openapi 到 17:40+ 才翻日 → 資料日不一致
    # 代表正處於發布窗:等 10 分鐘重抓,最多 8 次 (17:30 排程可涵蓋到 ~18:50)。
    for attempt in range(8):
        raw = {name: fetch(name, url) for name, url in ENDPOINTS.items()}
        dates = {name: roc_to_iso(df["Date"].iloc[0]) for name, df in raw.items()}
        if len(set(dates.values())) == 1:
            break
        logger.warning(f"四端點資料日不一致 (發布窗中?),10 分鐘後重抓 ({attempt+1}/8): {dates}")
        if attempt == 7:
            raise RuntimeError(f"四端點資料日持續不一致,不落地: {dates}")
        time.sleep(600)
    trade_date = dates["twse_price"]

    t = raw["twse_price"].rename(columns={"Code": "stock_id"})
    t = t[is_common_stock(t["stock_id"])]
    twse = pd.DataFrame({
        "stock_id": t["stock_id"],
        "open": num(t["OpeningPrice"]), "max": num(t["HighestPrice"]),
        "min": num(t["LowestPrice"]), "close": num(t["ClosingPrice"]),
        "Trading_Volume": num(t["TradeVolume"]),
    })
    pe = raw["twse_pe"].rename(columns={"Code": "stock_id"})
    twse = twse.merge(pd.DataFrame({
        "stock_id": pe["stock_id"], "PER_TSE": num(pe["PEratio"]),
        "PBR_TSE": num(pe["PBratio"]), "dividend_yield_TSE": num(pe["DividendYield"]),
    }), on="stock_id", how="left")

    o = raw["tpex_price"].rename(columns={"SecuritiesCompanyCode": "stock_id"})
    o = o[is_common_stock(o["stock_id"])]
    tpex = pd.DataFrame({
        "stock_id": o["stock_id"],
        "open": num(o["Open"]), "max": num(o["High"]),
        "min": num(o["Low"]), "close": num(o["Close"]),
        "Trading_Volume": num(o["TradingShares"]),
    })
    ope = raw["tpex_pe"].rename(columns={"SecuritiesCompanyCode": "stock_id"})
    tpex = tpex.merge(pd.DataFrame({
        "stock_id": ope["stock_id"], "PER_TSE": num(ope["PriceEarningRatio"]),
        "PBR_TSE": num(ope["PriceBookRatio"]), "dividend_yield_TSE": num(ope["YieldRatio"]),
    }), on="stock_id", how="left")

    df = pd.concat([twse, tpex], ignore_index=True)
    df.insert(1, "date", trade_date)
    df = df.dropna(subset=["close"]).drop_duplicates(subset=["stock_id"], keep="first")
    return df


def collect_chip(trade_date: str, force: bool = False) -> None:
    """三大法人買賣超快照 (TWSE rwd T86 + TPEx 3insti),正規化成 TEJ institutional_flow
    同一套欄位 (foreign_net=外陸資+外資自營商合計,單位:股)。接縫已實測與 TEJ 一致
    (7/14 比對:foreign/dealer 100%、trust 96.7% 在千股容差內)。
    法人資料缺一天可容忍 (下游是 20 日窗),故失敗只記 log 不讓整批收集失敗。"""
    out = CHIP_DIR / f"{trade_date}.parquet"
    if out.exists() and not force:
        logger.info(f"法人快照 {out} 已存在 → no-op")
        return
    frames = []

    ymd = trade_date.replace("-", "")
    r = requests.get(f"https://www.twse.com.tw/rwd/zh/fund/T86?date={ymd}"
                     f"&selectType=ALLBUT0999&response=json",
                     timeout=60, headers={"user-agent": "Mozilla/5.0"})
    d = r.json()
    if d.get("stat") == "OK" and d.get("data"):
        tw = pd.DataFrame(d["data"], columns=d["fields"])
        tw["stock_id"] = tw["證券代號"].astype(str).str.strip()
        tw = tw[is_common_stock(tw["stock_id"])]
        frames.append(pd.DataFrame({
            "stock_id": tw["stock_id"],
            "foreign_net": (num(tw["外陸資買賣超股數(不含外資自營商)"])
                             + num(tw["外資自營商買賣超股數"])),
            "trust_net": num(tw["投信買賣超股數"]),
            "dealer_net": num(tw["自營商買賣超股數"]),
        }))
    else:
        raise ValueError(f"T86 無資料 (stat={d.get('stat')})")

    o = fetch("tpex_price", "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading")
    o.columns = [c.replace(" ", "") for c in o.columns]   # 官方欄名夾雜空白,正規化後對應
    if roc_to_iso(o["Date"].iloc[0]) != trade_date:
        raise ValueError(f"TPEx 法人資料日 {o['Date'].iloc[0]} 與 {trade_date} 不符")
    o["stock_id"] = o["SecuritiesCompanyCode"].astype(str).str.strip()
    o = o[is_common_stock(o["stock_id"])]
    frames.append(pd.DataFrame({
        "stock_id": o["stock_id"],
        "foreign_net": num(o["ForeignInvestorsIncludeMainlandAreaInvestors-Difference"]),
        "trust_net": num(o["SecuritiesInvestmentTrustCompanies-Difference"]),
        "dealer_net": num(o["Dealers-Difference"]),
    }))

    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["stock_id"], keep="first")
    df.insert(1, "date", trade_date)
    CHIP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, out)
    logger.info(f"法人快照已落地 {trade_date}: {len(df)} 檔 → {out}")


def main():
    ap = argparse.ArgumentParser(description="TWSE/TPEx 全市場每日快照收集器 (0 FinMind API)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--force", action="store_true", help="覆寫既有的當日檔案")
    args = ap.parse_args()

    df = collect()
    trade_date = df["date"].iloc[0]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{trade_date}.parquet"
    if out.exists() and not args.force:
        logger.info(f"{out} 已存在 (資料日 {trade_date},假日或重複執行) → no-op")
    else:
        tmp = out.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        os.replace(tmp, out)
        logger.info(f"已落地 {trade_date}: {len(df)} 檔 (上市+上櫃普通股),"
                    f" PE 有值 {df['PER_TSE'].notna().sum()} 檔 → {out}")

    try:
        collect_chip(trade_date, force=args.force)
    except Exception as e:
        logger.warning(f"法人快照失敗 (價格快照不受影響,20日窗可容忍缺一天): {e}")


if __name__ == "__main__":
    main()
