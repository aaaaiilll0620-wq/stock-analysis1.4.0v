"""TWSE/TPEx 全市場每日快照收集器 (§15 擴池 Phase 1,0 FinMind API)
================================================================================
用途:每日收盤後抓 TWSE/TPEx 官方開放端點的全市場快照 (價格/成交量/PE/PBR/殖利率),
      正規化成 TEJ price_valuation 的同一套欄位,存成單日 Parquet 逐日累積。

      歷史種子 = tej_cache/price_valuation (2019-01 ~ 2026-07-14,PER_TSE 與官方
      PEratio 已實測 100% 一致);本收集器只負責種子日之後的增量。
      下游 scripts/universe_screen_daily.py 用 DuckDB 把兩邊 union 起來跑 L1+L2 粗篩。

特性:
  - 端點不支援歷史日期,回傳的是「最新交易日」→ 假日/重複執行自動變 no-op (冪等)
  - **發布時序 (實測)**:TPEx openapi 當天 ~14-16 點翻日;TWSE openapi 快照版隔天
    清晨才翻日 → TWSE 改走 rwd 介面 (指定日期、當天下午發布),目標日由 TPEx 決定,
    傍晚 17:30 排程收「當天」資料
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
REV_DIR = MARKET_CACHE / "monthly_revenue"
MARGIN_DIR = MARKET_CACHE / "margin_daily"
SHARE_DIR = MARKET_CACHE / "shareholding_daily"

REV_ENDPOINTS = {
    "twse_rev": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "tpex_rev": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
}

# TPEx openapi 當天 ~14-16 點翻日;TWSE 改用 rwd 介面 (支援指定日期,當天下午即發布,
# openapi 快照版要隔天清晨才翻日 → 棄用)。目標日由 TPEx 決定,TWSE 按日期精準抓。
ENDPOINTS = {
    "tpex_price": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
    "tpex_pe":    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
}
MIN_ROWS = {"tpex_price": 600, "tpex_pe": 600}


def fetch_twse_rwd(path: str, params: str, tries: int = 5) -> dict:
    """TWSE rwd JSON API;stat!='OK' (該日未發布/假日) 以 ValueError 拋出讓上層重試。"""
    url = f"https://www.twse.com.tw/rwd/zh/{path}?{params}&response=json"
    for i in range(tries):
        try:
            r = requests.get(url, timeout=60, headers={"user-agent": "Mozilla/5.0"})
            r.raise_for_status()
            d = r.json()
            if d.get("stat") != "OK":
                raise ValueError(f"rwd {path} stat={d.get('stat')} (該日資料未發布?)")
            return d
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"rwd {path} 第 {i+1} 次失敗: {e}")
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


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
    # 目標日 = TPEx openapi 的資料日 (當天 ~14-16 點翻日);太早跑 (兩個 TPEx 端點
    # 不同步) 就等 10 分鐘重抓。TWSE 用 rwd 按目標日精準抓,未發布同樣重試。
    for attempt in range(8):
        try:
            raw = {name: fetch(name, url) for name, url in ENDPOINTS.items()}
            dates = {name: roc_to_iso(df["Date"].iloc[0]) for name, df in raw.items()}
            if len(set(dates.values())) != 1:
                raise ValueError(f"TPEx 兩端點資料日不一致: {dates}")
            trade_date = dates["tpex_price"]
            ymd = trade_date.replace("-", "")
            mi = fetch_twse_rwd("afterTrading/MI_INDEX", f"date={ymd}&type=ALLBUT0999")
            bw = fetch_twse_rwd("afterTrading/BWIBBU_d", f"date={ymd}&selectType=ALL")
            break
        except ValueError as e:
            logger.warning(f"發布窗中,10 分鐘後重抓 ({attempt+1}/8): {e}")
            if attempt == 7:
                raise RuntimeError(f"重試耗盡,不落地: {e}")
            time.sleep(600)

    stock_tbl = next(t for t in mi["tables"] if "證券代號" in (t.get("fields") or []))
    t = pd.DataFrame(stock_tbl["data"], columns=stock_tbl["fields"])
    t["stock_id"] = t["證券代號"].astype(str).str.strip()
    t = t[is_common_stock(t["stock_id"])]
    if len(t) < 800:
        raise RuntimeError(f"TWSE MI_INDEX 個股僅 {len(t)} 檔,低於 sanity 下限")
    twse = pd.DataFrame({
        "stock_id": t["stock_id"],
        "open": num(t["開盤價"]), "max": num(t["最高價"]),
        "min": num(t["最低價"]), "close": num(t["收盤價"]),
        "Trading_Volume": num(t["成交股數"]),
    })
    pe = pd.DataFrame(bw["data"], columns=bw["fields"])
    pe["stock_id"] = pe["證券代號"].astype(str).str.strip()
    twse = twse.merge(pd.DataFrame({
        "stock_id": pe["stock_id"], "PER_TSE": num(pe["本益比"]),
        "PBR_TSE": num(pe["股價淨值比"]), "dividend_yield_TSE": num(pe["殖利率(%)"]),
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
            # 買賣毛額 (2026-07-16 起):institutional_participation (法人成交占比) 需要
            # 買+賣總量,淨額算不出來;歷史由 TEJ institutional_gross 種子補
            "foreign_buy": (num(tw["外陸資買進股數(不含外資自營商)"])
                             + num(tw["外資自營商買進股數"])),
            "foreign_sell": (num(tw["外陸資賣出股數(不含外資自營商)"])
                              + num(tw["外資自營商賣出股數"])),
            "trust_buy": num(tw["投信買進股數"]),
            "trust_sell": num(tw["投信賣出股數"]),
        }))
    else:
        raise ValueError(f"T86 無資料 (stat={d.get('stat')})")

    o = fetch("tpex_price", "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading")
    o.columns = [c.replace(" ", "") for c in o.columns]   # 官方欄名夾雜空白,正規化後對應
    if roc_to_iso(o["Date"].iloc[0]) != trade_date:
        raise ValueError(f"TPEx 法人資料日 {o['Date'].iloc[0]} 與 {trade_date} 不符")
    o["stock_id"] = o["SecuritiesCompanyCode"].astype(str).str.strip()
    o = o[is_common_stock(o["stock_id"])]

    def _ocol(name):
        """TPEx 欄位防禦性取值:官方欄名偶有調整,缺欄回 NaN 不炸整批。"""
        if name in o.columns:
            return num(o[name])
        logger.warning(f"TPEx 3insti 缺欄位 {name},該欄以 NaN 落地")
        return pd.Series([float("nan")] * len(o), index=o.index)

    frames.append(pd.DataFrame({
        "stock_id": o["stock_id"],
        "foreign_net": num(o["ForeignInvestorsIncludeMainlandAreaInvestors-Difference"]),
        "trust_net": num(o["SecuritiesInvestmentTrustCompanies-Difference"]),
        "dealer_net": num(o["Dealers-Difference"]),
        "foreign_buy": _ocol("ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy"),
        "foreign_sell": _ocol("ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell"),
        "trust_buy": _ocol("SecuritiesInvestmentTrustCompanies-TotalBuy"),
        "trust_sell": _ocol("SecuritiesInvestmentTrustCompanies-TotalSell"),
    }))

    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["stock_id"], keep="first")
    df.insert(1, "date", trade_date)
    CHIP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, out)
    logger.info(f"法人快照已落地 {trade_date}: {len(df)} 檔 → {out}")


def _upsert_daily(dir_: Path, date_: str, rows: pd.DataFrame) -> None:
    """把 rows (含 stock_id) upsert 進 {date}.parquet:既有股票保留、只追加新股票 → 冪等。"""
    dir_.mkdir(parents=True, exist_ok=True)
    out = dir_ / f"{date_}.parquet"
    rows = rows.copy()
    rows.insert(1, "date", date_)
    if out.exists():
        prev = pd.read_parquet(out)
        rows = rows[~rows["stock_id"].isin(set(prev["stock_id"]))]
        if rows.empty:
            return
        rows = pd.concat([prev, rows], ignore_index=True)
    tmp = out.with_suffix(".parquet.tmp")
    rows.sort_values("stock_id").reset_index(drop=True).to_parquet(tmp, index=False)
    os.replace(tmp, out)
    logger.info(f"{dir_.name} {date_}: 共 {len(rows)} 檔 → {out}")


def collect_margin(trade_date: str, force: bool = False) -> None:
    """融資餘額 (TWSE rwd MI_MARGN + TPEx openapi margin_balance),單位:張。
    時序:MI_MARGN 當日資料約 21:00 才發布 → 17:30 跑通常收到的是 T-1;
    TPEx 端點只回最新日。兩市場**各按自己的資料日**寫逐日檔 (個股只屬一個市場,
    序列內部一致即可),當日缺的次日自動補。歷史由 TEJ margin_balance 種子補。
    MI_MARGN 融資/融券兩組欄位重名 → 按位置取 (融資今日餘額 = 第 7 欄)。"""
    # TWSE:試 trade_date,未發布就往回補最多 3 個日曆天中缺的檔
    got_twse = False
    d0 = pd.Timestamp(trade_date)
    for back in range(4):
        dt = (d0 - pd.Timedelta(days=back)).strftime("%Y-%m-%d")
        if dt < "2026-07-15":                      # 只補收集器上線後的日子
            break
        out = MARGIN_DIR / f"{dt}.parquet"
        if out.exists() and not force and back > 0:
            break                                   # 已補到既有檔 → 停
        try:
            d = fetch_twse_rwd("marginTrading/MI_MARGN",
                               f"date={dt.replace('-', '')}&selectType=ALL")
        except Exception as e:
            logger.info(f"MI_MARGN {dt} 未發布/假日 ({e}),往前一天試")
            continue
        tbl = next((t for t in d.get("tables", []) if "代號" in (t.get("fields") or [])), None)
        if tbl is None or not tbl.get("data"):
            continue
        tw = pd.DataFrame(tbl["data"])
        ids = tw.iloc[:, 0].astype(str).str.strip()
        keep = is_common_stock(ids)
        rows = pd.DataFrame({"stock_id": ids[keep],
                             "margin_balance": num(tw.iloc[:, 6][keep])}).dropna()
        if len(rows) < 500:
            raise ValueError(f"MI_MARGN {dt} 僅 {len(rows)} 檔,低於 sanity 下限")
        _upsert_daily(MARGIN_DIR, dt, rows)
        got_twse = True
        break
    if not got_twse:
        logger.warning("MI_MARGN 近 4 天皆無資料可收 (連假?)")

    # TPEx:端點只回最新日,按它自己的 Date 落地
    o = fetch("tpex_price", "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance")
    o.columns = [c.replace(" ", "") for c in o.columns]
    tpex_date = roc_to_iso(o["Date"].iloc[0])
    o["stock_id"] = o["SecuritiesCompanyCode"].astype(str).str.strip()
    o = o[is_common_stock(o["stock_id"])]
    rows = pd.DataFrame({"stock_id": o["stock_id"],
                         "margin_balance": num(o["MarginPurchaseBalance"])}).dropna()
    if len(rows) < 500:
        raise ValueError(f"TPEx 融資僅 {len(rows)} 檔,低於 sanity 下限")
    _upsert_daily(MARGIN_DIR, tpex_date, rows)


def collect_shareholding(trade_date: str, force: bool = False) -> None:
    """發行股數 + 外資持股比率快照:
      發行股數 = TWSE t187ap03_L「已發行普通股數」+ TPEx t187ap03_O IssueShares
      外資比率 = TWSE rwd MI_QFIIS「全體外資及陸資持股比率」(TPEx 無公開端點 → NaN;
                 分類器有市值主判,外資比率僅第4順位後備,缺值影響可忽略)
    下游只用「最新一筆」(流通股數 → 市值/P-S/投信吸籌比),不需歷史種子。"""
    out = SHARE_DIR / f"{trade_date}.parquet"
    if out.exists() and not force:
        logger.info(f"持股快照 {out} 已存在 → no-op")
        return

    frames = []
    for url, id_col, share_col in [
        ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "公司代號", "已發行普通股數或TDR原股發行股數"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "SecuritiesCompanyCode", "IssueShares"),
    ]:
        r = requests.get(url, timeout=60,
                         headers={"accept": "application/json", "user-agent": "Mozilla/5.0"})
        r.raise_for_status()
        b = pd.DataFrame(r.json())
        b["stock_id"] = b[id_col].astype(str).str.strip()
        b = b[is_common_stock(b["stock_id"])]
        frames.append(pd.DataFrame({"stock_id": b["stock_id"],
                                    "shares_issued": num(b[share_col])}))
    df = pd.concat(frames, ignore_index=True).dropna(subset=["shares_issued"])
    df = df.drop_duplicates(subset=["stock_id"], keep="first")

    # MI_QFIIS 當日可能尚未發布 → 往回最多 3 個日曆天取最近可得的外資比率
    ratio = None
    d0 = pd.Timestamp(trade_date)
    for back in range(4):
        dt = (d0 - pd.Timedelta(days=back)).strftime("%Y%m%d")
        try:
            q = fetch_twse_rwd("fund/MI_QFIIS", f"date={dt}&selectType=ALLBUT0999")
            qd = pd.DataFrame(q["data"], columns=q["fields"])
            qd["stock_id"] = qd["證券代號"].astype(str).str.strip()
            ratio = pd.DataFrame({"stock_id": qd["stock_id"],
                                  "foreign_ratio": num(qd["全體外資及陸資持股比率"])})
            break
        except Exception as e:
            logger.info(f"MI_QFIIS {dt} 未發布 ({e}),往前一天試")
    if ratio is not None:
        df = df.merge(ratio, on="stock_id", how="left")
    else:
        logger.warning("MI_QFIIS 近 4 天皆無資料,外資比率以 NaN 落地")
        df["foreign_ratio"] = float("nan")

    if len(df) < 1500:
        raise ValueError(f"持股快照僅 {len(df)} 檔,低於 sanity 下限 1500")
    df.insert(1, "date", trade_date)
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, out)
    logger.info(f"持股快照已落地 {trade_date}: {len(df)} 檔"
                f" (外資比率有值 {df['foreign_ratio'].notna().sum()}) → {out}")


def collect_monthly_revenue() -> None:
    """全市場月營收快照 (TWSE t187ap05_L + TPEx mopsfin_t187ap05_O),正規化成
    tej_cache/monthly_revenue 同一套欄位 (千元→元),逐「營收月份」一檔累積:
      ~/market_cache/monthly_revenue/{YYYY-MM}.parquet

    PIT 設計:端點回傳「當前申報月」的批次快照 (月初只有已公告的公司,~10 日到齊)。
    每日收集時,既有檔案內已出現的公司**原樣保留** (release_date=首次見到的日期,
    ≈實際公告日),只追加新公告的公司 → 冪等、release_date 不會被後續覆蓋。
    公告後更正的營收不回寫 (保持 PIT 快照);校正靠之後的 TEJ 手動匯出 (匯入端
    以 TEJ 為準去重)。月營收缺一天可容忍 (次日補齊),失敗只記 log。"""
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    frames = []
    for name, url in REV_ENDPOINTS.items():
        r = requests.get(url, timeout=60,
                         headers={"accept": "application/json", "user-agent": "Mozilla/5.0"})
        r.raise_for_status()
        frames.append(pd.DataFrame(r.json()))
    d = pd.concat(frames, ignore_index=True)
    if "公司代號" not in d.columns or d.empty:
        raise ValueError("月營收端點回傳格式異常 (無 公司代號 欄)")
    d["stock_id"] = d["公司代號"].astype(str).str.strip()
    d = d[is_common_stock(d["stock_id"])]

    ym = d["資料年月"].astype(str).str.strip()          # ROC 年月,如 11506
    d["date"] = (ym.str[:-2].astype(int) + 1911).astype(str) + "-" + ym.str[-2:] + "-01"

    snap = pd.DataFrame({
        "stock_id": d["stock_id"],
        "date": d["date"],
        "release_date": today,                          # 首次見到 ≈ 公告日 (見 docstring)
        "revenue_yoy_pct": num(d["營業收入-去年同月增減(%)"]),
        "stock_name": d["公司名稱"].astype(str).str.strip(),
        "revenue": num(d["營業收入-當月營收"]) * 1000,   # 千元 → 元,對齊 TEJ 匯入慣例
        "revenue_last_year": num(d["營業收入-去年當月營收"]) * 1000,
        "cum_revenue": num(d["累計營業收入-當月累計營收"]) * 1000,
        "cum_revenue_last_year": num(d["累計營業收入-去年累計營收"]) * 1000,
    }).dropna(subset=["revenue"]).drop_duplicates(subset=["stock_id", "date"], keep="first")

    REV_DIR.mkdir(parents=True, exist_ok=True)
    for month, g in snap.groupby("date"):
        out = REV_DIR / f"{month[:7]}.parquet"
        if out.exists():
            prev = pd.read_parquet(out)
            new_rows = g[~g["stock_id"].isin(set(prev["stock_id"]))]
            if new_rows.empty:
                logger.info(f"月營收 {month[:7]}: 無新公告公司 → no-op ({len(prev)} 檔)")
                continue
            merged = pd.concat([prev, new_rows], ignore_index=True)
            added = len(new_rows)
        else:
            merged = g
            added = len(g)
        tmp = out.with_suffix(".parquet.tmp")
        merged.sort_values("stock_id").reset_index(drop=True).to_parquet(tmp, index=False)
        os.replace(tmp, out)
        logger.info(f"月營收 {month[:7]}: +{added} 檔 → 共 {len(merged)} 檔 → {out}")


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

    try:
        collect_monthly_revenue()
    except Exception as e:
        logger.warning(f"月營收快照失敗 (價格快照不受影響,次日自動補齊): {e}")

    try:
        collect_margin(trade_date, force=args.force)
    except Exception as e:
        logger.warning(f"融資快照失敗 (10日窗可容忍缺一天): {e}")

    try:
        collect_shareholding(trade_date, force=args.force)
    except Exception as e:
        logger.warning(f"持股快照失敗 (用最新一筆,次日自動補): {e}")


if __name__ == "__main__":
    main()
