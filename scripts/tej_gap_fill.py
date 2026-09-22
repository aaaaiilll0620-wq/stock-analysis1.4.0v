"""
TEJ 小窗口補洞 → market_cache 收集器逐日快照格式
================================================================================
收集器 (market_snapshot_collector.py) 的官方端點不提供歷史日期,停跑的日子補不回來。
這支把一段 TEJ 手動匯出 (UTF-16 + Tab 的 .csv) 轉成收集器的逐日檔,填回缺口:

  chip.csv            → ~/market_cache/institutional_flow_daily/{date}.parquet
  price.csv + price_tse.csv
                      → ~/market_cache/price_valuation_daily/{date}.parquet
  margin.csv          → ~/market_cache/margin_daily/{date}.parquet
  revenue_YYYYMM.csv  → ~/market_cache/monthly_revenue/{YYYY-MM}.parquet

口徑 (對齊收集器,見 market_snapshot_collector.py):
  · 範圍 = is_common_stock (四位數、不以 0 開頭)
  · 法人:千股 → 股、張 → 股 (TEJ 已四捨五入到千股/張,精度比 T86 粗,與 TEJ 種子同)
  · 估值只用 -TSE 欄 (PER_TSE 與官方 PEratio 一致);**不用 -TEJ 欄頂替** —— 口徑不同
  · 月營收:release_date 用 TEJ「營收發布日」(真實公告日,比收集器「首次見到日」更準);
    revenue_last_year / cum_revenue_last_year 取 tej_cache 種子去年同月的
    revenue / cum_revenue,種子沒有就留 NaN,不用 YoY 反推。

安全:
  · 預設 dry-run,--apply 才寫。
  · 既有逐日檔**一律不覆寫** (收集器資料優先);月營收檔存在時只追加缺的公司
    (同收集器 upsert 語意)。
  · 每次 --apply 寫的檔案清單落在 {src}/written_files.txt,要撤銷就刪那些檔。
  · --verify DATE:拿 TEJ 轉出來的那天跟收集器既有檔逐檔比對,不寫任何東西。

用法:
  python scripts/tej_gap_fill.py                                   # dry-run
  python scripts/tej_gap_fill.py --apply
  python scripts/tej_gap_fill.py --verify 2026-09-21               # 重疊日對帳
================================================================================
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
DEFAULT_SRC = PROJECT_ROOT / "tej_exports" / "gap_20260903_0921"

CHIP_DIR = MARKET_CACHE / "institutional_flow_daily"
PRICE_DIR = MARKET_CACHE / "price_valuation_daily"
MARGIN_DIR = MARKET_CACHE / "margin_daily"
REV_DIR = MARKET_CACHE / "monthly_revenue"


# ------------------------------------------------------------------------------
def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-16", sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df["stock_id"] = df["證券代碼"].str.strip().str.split().str[0]
    df = df[df["stock_id"].str.fullmatch(r"[1-9]\d{3}")].copy()
    if "年月日" in df:
        df["date"] = pd.to_datetime(df["年月日"].str.strip(), format="%Y%m%d").dt.strftime("%Y-%m-%d")
    return df


def _num(s: pd.Series) -> pd.Series:
    """TEJ 缺值是 '.';千分位逗號去掉。"""
    return pd.to_numeric(s.str.strip().str.replace(",", "", regex=False)
                         .replace({".": np.nan, "": np.nan}), errors="coerce")


def _require(df: pd.DataFrame, cols: list, name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name}:缺少必要欄位 {missing} —— 匯出漏勾或 TEJ 改名,不放行")


def _as_int(s: pd.Series) -> pd.Series:
    """收集器的量類欄位是 int64;有 NaN 時保留 float,不用 0 填。"""
    return s.round().astype("int64") if s.notna().all() else s


# ------------------------------------------------------------------------------
def build_chip(src: Path) -> pd.DataFrame:
    df = _read(src / "chip.csv")
    need = ["外資買賣超(千股)", "投信買賣超(千股)", "自營買賣超(千股)",
            "外資買進張數", "外資賣出張數", "投信買進張數", "投信賣出張數"]
    _require(df, need, "chip.csv")
    out = pd.DataFrame({
        "stock_id": df["stock_id"], "date": df["date"],
        "foreign_net": _num(df["外資買賣超(千股)"]) * 1000,
        "trust_net": _num(df["投信買賣超(千股)"]) * 1000,
        "dealer_net": _num(df["自營買賣超(千股)"]) * 1000,
        "foreign_buy": _num(df["外資買進張數"]) * 1000,
        "foreign_sell": _num(df["外資賣出張數"]) * 1000,
        "trust_buy": _num(df["投信買進張數"]) * 1000,
        "trust_sell": _num(df["投信賣出張數"]) * 1000,
    })
    return out.dropna(subset=["foreign_net", "trust_net", "dealer_net"])


def build_price(src: Path) -> pd.DataFrame:
    px = _read(src / "price.csv")
    _require(px, ["開盤價(元)", "最高價(元)", "最低價(元)", "收盤價(元)", "成交量(千股)"], "price.csv")
    tse = _read(src / "price_tse.csv")
    _require(tse, ["本益比-TSE", "股價淨值比-TSE", "股利殖利率-TSE"], "price_tse.csv")
    a = pd.DataFrame({
        "stock_id": px["stock_id"], "date": px["date"],
        "open": _num(px["開盤價(元)"]), "max": _num(px["最高價(元)"]),
        "min": _num(px["最低價(元)"]), "close": _num(px["收盤價(元)"]),
        "Trading_Volume": _num(px["成交量(千股)"]) * 1000,
    })
    b = pd.DataFrame({
        "stock_id": tse["stock_id"], "date": tse["date"],
        "PER_TSE": _num(tse["本益比-TSE"]), "PBR_TSE": _num(tse["股價淨值比-TSE"]),
        "dividend_yield_TSE": _num(tse["股利殖利率-TSE"]),
    })
    for name, d in (("price.csv", a), ("price_tse.csv", b)):
        if d.duplicated(["stock_id", "date"]).any():
            raise ValueError(f"{name}:(stock_id, date) 有重複列")
    out = a.merge(b, on=["stock_id", "date"], how="left", validate="one_to_one")
    unmatched = out["PBR_TSE"].isna() & out["close"].notna()
    if unmatched.mean() > 0.05:
        raise ValueError(f"price 與 price_tse 對不上的列 {unmatched.mean():.1%} —— 兩份匯出範圍不同?")
    return out.dropna(subset=["close"])


def build_margin(src: Path) -> pd.DataFrame:
    df = _read(src / "margin.csv")
    _require(df, ["融資餘額(張)"], "margin.csv")
    out = pd.DataFrame({"stock_id": df["stock_id"], "date": df["date"],
                        "margin_balance": _num(df["融資餘額(張)"])})
    return out.dropna(subset=["margin_balance"])


def build_revenue(path: Path) -> pd.DataFrame:
    df = _read(path)
    _require(df, ["年月", "營收發布日", "單月營收成長率％", "單月營收(千元)"], path.name)
    ym = df["年月"].str.strip()
    df["month"] = ym.str[:4] + "-" + ym.str[4:6] + "-01"
    out = pd.DataFrame({
        "stock_id": df["stock_id"], "date": df["month"],
        "release_date": pd.to_datetime(df["營收發布日"].str.strip(), format="%Y%m%d",
                                       errors="coerce").dt.strftime("%Y-%m-%d"),
        "revenue_yoy_pct": _num(df["單月營收成長率％"]),
        "stock_name": df["證券代碼"].str.strip().str.split(n=1).str[1].fillna(""),
        "revenue": _num(df["單月營收(千元)"]) * 1000,
        "cum_revenue": (_num(df["累計營收(千元)"]) * 1000 if "累計營收(千元)" in df
                        else np.nan),
    }).dropna(subset=["revenue", "release_date"])

    # 去年同月:取 tej_cache 種子,不用 YoY 反推
    ly = {}
    for m in out["date"].unique():
        ly_month = f"{int(m[:4]) - 1}{m[4:]}"
        for sid in out.loc[out["date"] == m, "stock_id"]:
            f = TEJ_CACHE / "monthly_revenue" / f"{sid}.parquet"
            if not f.exists():
                continue
            s = pd.read_parquet(f, columns=["date", "revenue", "cum_revenue"])
            hit = s[s["date"].astype(str).str[:10] == ly_month]
            if len(hit):
                ly[(sid, m)] = (hit["revenue"].iloc[-1], hit["cum_revenue"].iloc[-1])
    key = list(zip(out["stock_id"], out["date"]))
    out["revenue_last_year"] = [ly.get(k, (np.nan, np.nan))[0] for k in key]
    out["cum_revenue_last_year"] = [ly.get(k, (np.nan, np.nan))[1] for k in key]
    # 種子的去年值若跟 TEJ 本月 YoY 的分母對不上 (去年營收事後更正/合併口徑變動),
    # 兩個去年欄都留 NaN —— 寧缺不錯。
    implied = (out["revenue"] / out["revenue_last_year"] - 1) * 100
    stale = (implied - out["revenue_yoy_pct"]).abs() >= 0.05
    if stale.any():
        print(f"  {path.name}:{int(stale.sum())} 檔種子去年值與 TEJ YoY 分母不符 → 去年欄留 NaN"
              f" ({', '.join(out.loc[stale, 'stock_id'].head(10))}{' …' if stale.sum() > 10 else ''})")
    out.loc[stale, ["revenue_last_year", "cum_revenue_last_year"]] = np.nan
    cols =["stock_id", "date", "release_date", "revenue_yoy_pct", "stock_name",
            "revenue", "revenue_last_year", "cum_revenue", "cum_revenue_last_year"]
    return out[cols]


# ------------------------------------------------------------------------------
def _write_daily(dir_: Path, df: pd.DataFrame, dates: list, apply: bool, written: list) -> None:
    int_cols = [c for c in df.columns if c in ("foreign_net", "trust_net", "dealer_net",
                "foreign_buy", "foreign_sell", "trust_buy", "trust_sell",
                "Trading_Volume", "margin_balance")]
    for d in dates:
        g = df[df["date"] == d].sort_values("stock_id").reset_index(drop=True)
        out = dir_ / f"{d}.parquet"
        if g.empty:
            print(f"  {dir_.name} {d}: TEJ 無資料 → 略過")
            continue
        if out.exists():
            print(f"  {dir_.name} {d}: 已有收集器檔 → 不覆寫")
            continue
        for c in int_cols:
            g[c] = _as_int(g[c])
        print(f"  {dir_.name} {d}: {len(g)} 檔" + ("" if apply else "  (dry-run)"))
        if apply:
            dir_.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".parquet.tmp")
            g.to_parquet(tmp, index=False)
            os.replace(tmp, out)
            written.append(str(out))


def _write_revenue(df: pd.DataFrame, apply: bool, written: list) -> None:
    for month, g in df.groupby("date"):
        out = REV_DIR / f"{month[:7]}.parquet"
        if out.exists():
            prev = pd.read_parquet(out)
            g = g[~g["stock_id"].isin(set(prev["stock_id"]))]
            print(f"  monthly_revenue {month[:7]}: 既有 {len(prev)} 檔,追加 {len(g)} 檔")
            if g.empty:
                continue
            merged = pd.concat([prev, g], ignore_index=True)
        else:
            merged = g
            print(f"  monthly_revenue {month[:7]}: 新檔 {len(g)} 檔 (去年同月補到"
                  f" {g['revenue_last_year'].notna().sum()} 檔)")
        print("" if apply else "    (dry-run)", end="")
        if apply:
            REV_DIR.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".parquet.tmp")
            merged.sort_values("stock_id").reset_index(drop=True).to_parquet(tmp, index=False)
            os.replace(tmp, out)
            written.append(str(out))


# ------------------------------------------------------------------------------
def verify(src: Path, date_: str) -> int:
    """重疊日對帳:TEJ 轉出的值 vs 收集器既有檔,逐欄列出一致率。"""
    frames = {"institutional_flow_daily": (build_chip(src), CHIP_DIR),
              "price_valuation_daily": (build_price(src), PRICE_DIR),
              "margin_daily": (build_margin(src), MARGIN_DIR)}
    bad = 0
    for name, (tej, dir_) in frames.items():
        f = dir_ / f"{date_}.parquet"
        if not f.exists():
            print(f"{name}: 收集器沒有 {date_} 的檔,無法對帳")
            continue
        col = pd.read_parquet(f)
        t = tej[tej["date"] == date_]
        m = t.merge(col, on="stock_id", suffixes=("_tej", "_col"))
        print(f"\n{name} {date_}: TEJ {len(t)} 檔 / 收集器 {len(col)} 檔 / 交集 {len(m)}")
        for c in [c for c in col.columns if c not in ("stock_id", "date")]:
            a, b = m[f"{c}_tej"].astype(float), m[f"{c}_col"].astype(float)
            both = a.notna() & b.notna()
            # 法人/成交量 TEJ 是千股 → 容許 ±500 股;張 → ±500 股;價格/估值容許 0.01
            tol = 500 if c.endswith(("_net", "_buy", "_sell")) or c == "Trading_Volume" else 0.011
            if c == "Trading_Volume":   # TEJ 成交量(千股) 是無條件捨去,不是四捨五入
                ok = ((b - a) >= 0) & ((b - a) < 1000) & both
            else:
                ok = ((a - b).abs() <= tol) & both
            rate = ok.sum() / max(both.sum(), 1)
            nan_mismatch = (a.isna() != b.isna()).sum()
            flag = "OK " if rate >= 0.99 else "!! "
            bad += rate < 0.99
            print(f"  {flag}{c:20s} 一致 {rate:6.1%} ({ok.sum()}/{both.sum()})  缺值不一致 {nan_mismatch}")
            if rate < 0.99:
                ex = m.loc[both & ~ok, ["stock_id", f"{c}_tej", f"{c}_col"]].head(5)
                print(ex.to_string(index=False))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--start", default="2026-09-03")
    ap.add_argument("--end", default="2026-09-18",
                    help="最後一天;預設不含 9/21 —— 那天留給收集器,當作對帳重疊日")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", metavar="DATE", default=None)
    args = ap.parse_args()
    src = Path(args.src)

    if args.verify:
        return verify(src, args.verify)

    chip, price, margin = build_chip(src), build_price(src), build_margin(src)
    dates = sorted(d for d in chip["date"].unique() if args.start <= d <= args.end)
    print(f"來源 {src}\n補洞日期 {len(dates)} 天:{dates[0]} ~ {dates[-1]}\n")
    for name, d in (("chip", chip), ("price", price), ("margin", margin)):
        print(f"{name}: 每日檔數 {d.groupby('date').size().agg(['min', 'max']).tolist()}"
              f",缺值率 " + ", ".join(f"{c}={d[c].isna().mean():.1%}"
                                    for c in d.columns if c not in ("stock_id", "date")))
    print()

    written: list = []
    _write_daily(CHIP_DIR, chip, dates, args.apply, written)
    _write_daily(PRICE_DIR, price, dates, args.apply, written)
    _write_daily(MARGIN_DIR, margin, sorted(set(margin["date"]) & set(
        d for d in margin["date"] if "2026-09-02" <= d <= args.end)), args.apply, written)
    for rev in sorted(src.glob("revenue_*.csv")):
        _write_revenue(build_revenue(rev), args.apply, written)

    if args.apply:
        log = src / "written_files.txt"
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"# {pd.Timestamp.now():%Y-%m-%d %H:%M:%S}\n" + "\n".join(written) + "\n")
        print(f"\n寫入 {len(written)} 個檔案,清單 → {log}")
    else:
        print("\n(dry-run,沒有寫任何檔案;加 --apply 才寫)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
