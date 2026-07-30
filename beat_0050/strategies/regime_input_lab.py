# -*- coding: utf-8 -*-
"""regime_input_lab.py — 市場燈號「輸入序列」頭對頭 + 虛無對照 (否定結果存檔)。
================================================================================
補既有兩支 lab 的缺口:`regime_signal_lab` / `regime_hysteresis_lab` 都**固定用等權指數
當輸入、只比規則**;本腳本**固定規則、只換輸入**,並加上決定性的**虛無對照**。

結論(2026-07-28,完整記錄見 docs/預註冊_RegimeInputLab.md):
  · 加權與 0050 曝險 86.5% 重疊、相關 0.916 → 同一個資訊,不是新維度
  · 同一股利基礎下 等權 1.01 ≫ 加權價格 0.77 > 0050 原始 0.74
  · **所有候選的 MDD 改善都只是「持有更少」** —— 等權訊號 × 0.85 就能複製,
    且夏普還更高。→ 維持現行等權訊號不變。

重點方法論:
  (1) 多輸入比較**必須先對齊共同日期軸**,否則 apply_daily_expo 的預設滿倉會偽造 alpha。
  (2) 任何「改善」都要跟**同平均曝險**的虛無對照比,否則量到的是風險旋鈕不是識別力。

用法:python beat_0050/strategies/regime_input_lab.py
================================================================================
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from beat_0050.honest_backtest import Engine, ERAS
from existing_composite import build_factors, holdings_for
from regime_signal_lab import metrics, era_sharpe
from regime_hysteresis_lab import debounce, apply_daily_expo

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", str(Path.home() / "market_cache")))
BENCH_DIR = ROOT / "beat_0050" / "data" / "benchmark"
UP = DN = 3
MAS = (50, 100, 200)


# ------------------------------------------------------------------ 資料層
def load_px() -> pd.DataFrame:
    import duckdb
    globs = [f"'{TEJ_CACHE}/price_valuation/*.parquet'"]
    daily = MARKET_CACHE / "price_valuation_daily"
    if daily.exists() and any(daily.glob("*.parquet")):
        globs.append(f"'{daily}/*.parquet'")
    px = duckdb.connect().execute(f"""
        SELECT stock_id, date, close FROM
        read_parquet([{', '.join(globs)}], union_by_name=true) WHERE close > 0
    """).df()
    return px.drop_duplicates(["stock_id", "date"]).sort_values(["stock_id", "date"])


def ew_series(px: pd.DataFrame) -> pd.DataFrame:
    """全市場等權指數(不含息,與 production 的 _ew_index 同一算法)。"""
    p = px.copy()
    p["ret"] = p.groupby("stock_id")["close"].pct_change()
    d = (p[(p["ret"].notna()) & (p["ret"].abs() < 0.5)]
         .groupby("date")["ret"].mean().sort_index())
    return pd.DataFrame({"date": d.index.astype(str), "v": (1 + d).cumprod().values})


def breadth_series(px: pd.DataFrame, w: int = 100) -> pd.DataFrame:
    """站上自身 MA{w} 的個股佔比(%)。有界,不像等權指數會被單日跌幅拉走。"""
    wide = px.pivot(index="date", columns="stock_id", values="close").sort_index()
    ma = wide.rolling(w, min_periods=w).mean()
    valid = ma.notna() & wide.notna()
    pct = ((wide >= ma) & valid).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan) * 100
    d = pd.DataFrame({"date": pct.index.astype(str), "v": pct.values}).dropna()
    return d[d["date"] >= "2004-01-01"].reset_index(drop=True)


def _finmind_daily(stock_id: str, cache: Path) -> pd.DataFrame:
    """FinMind 個股日線,落地快取後重跑不再打 API。"""
    if cache.exists():
        return pd.read_parquet(cache)
    from dotenv import load_dotenv
    from FinMind.data import DataLoader
    load_dotenv()
    dl = DataLoader()
    dl.login_by_token(api_token=os.getenv("FINMIND_TOKEN"))
    d = dl.taiwan_stock_daily(stock_id=stock_id, start_date="2003-01-01",
                              end_date=pd.Timestamp.now().strftime("%Y-%m-%d"))
    d = d[["date", "close"]].sort_values("date").reset_index(drop=True)
    d["date"] = d["date"].astype(str)
    cache.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(cache, index=False)
    return d


def input_series() -> dict[str, pd.DataFrame]:
    """五條候選輸入,**依股利基礎分組**(混著比會量到股利而不是訊號)。"""
    px = load_px()
    out = {"等權(不含息)": ew_series(px)}

    taiex = MARKET_CACHE / "taiex_daily.parquet"          # core/market_index.py 維護
    if taiex.exists():
        d = pd.read_parquet(taiex)
        out["加權價格(不含息)"] = pd.DataFrame({"date": d["date"].astype(str), "v": d["close"]})
    d = _finmind_daily("0050", BENCH_DIR / "0050_raw.parquet")
    out["0050原始(不含息)"] = pd.DataFrame({"date": d["date"], "v": d["close"]})
    tr = BENCH_DIR / "0050_tr.parquet"
    if tr.exists():
        d = pd.read_parquet(tr)
        out["0050還原(含息)"] = pd.DataFrame({"date": d["date"].astype(str), "v": d["adj_close"]})
    return out, px


# ------------------------------------------------------------------ 訊號層
def add_ma(f: pd.DataFrame) -> pd.DataFrame:
    f = f.copy()
    for w in MAS:
        f[f"ma{w}"] = f["v"].rolling(w, min_periods=w).mean()
    return f.dropna(subset=["ma200"]).reset_index(drop=True)


def ladder_expo(f: pd.DataFrame) -> np.ndarray:
    """多軸階梯 + 遲滯3d(= production core/regime_exposure.py 的定案規則)。"""
    s = [debounce((f["v"] >= f[f"ma{w}"]).values, UP, DN) for w in MAS]
    return (s[0].astype(float) + s[1] + s[2]) / 3.0


def align(dates_from: list, expo: np.ndarray, axis: list) -> pd.Series:
    """對齊到共同日期軸(前值填補,無未來函數)。**跳過這步會偽造 alpha,見 §3.4。**"""
    return (pd.Series(np.asarray(expo, float), index=pd.Index(dates_from, name="date"))
            .reindex(pd.Index(axis, name="date")).ffill())


# ------------------------------------------------------------------ 主程式
def main() -> None:
    print("loading ...", flush=True)
    raw, px = input_series()
    feats = {k: add_ma(v) for k, v in raw.items()}
    br = breadth_series(px, 100)

    axis = sorted(set.intersection(*[set(f["date"]) for f in feats.values()], set(br["date"])))
    print(f"共同日期軸 {len(axis)} 天 ({axis[0]} → {axis[-1]})", flush=True)

    A = {k: align(f["date"].tolist(), ladder_expo(f), axis) for k, f in feats.items()}
    A["廣度佔比"] = align(br["date"].tolist(), np.clip(br["v"].values / 100, 0, 1), axis)

    # ---- 冗餘檢定 ----
    print("\n" + "=" * 92)
    print("冗餘檢定 — 曝險完全相同 % (上三角) / 相關係數 (下三角)")
    print("=" * 92)
    ks = list(A.keys())
    print(f"{'':<18}" + "".join(f"{k[:12]:>14}" for k in ks))
    for i, a in enumerate(ks):
        row = f"{a[:17]:<18}"
        for j, b in enumerate(ks):
            row += (f"{(A[a] == A[b]).mean()*100:>13.1f}%" if j >= i
                    else f"{A[a].corr(A[b]):>14.3f}")
        print(row)
    print("\n平均曝險: " + "  ".join(f"{k} {A[k].mean()*100:.1f}%" for k in ks))

    # ---- 回測:候選 + 虛無對照 ----
    print("\nengine ...", flush=True)
    eng = Engine()
    dual = eng.run(holdings_for(build_factors(), "dual"))["monthly"].reset_index(drop=True)
    bench = dual["bench"].values
    es_b = era_sharpe(dual["as_of"], bench)

    sig = {f"輸入·{k}": A[k].values for k in ks}
    sig["組合·平均(等權+廣度)"] = ((A["等權(不含息)"] + A["廣度佔比"]) / 2).values
    for c in (0.85, 0.75):                        # 對照1:同訊號、只是持有更少
        sig[f"對照1·等權×{c:.2f}"] = (A["等權(不含息)"] * c).values
    for c in (0.55,):                             # 對照2:零訊號的常數曝險
        sig[f"對照2·常數{c:.0%}"] = np.full(len(axis), c)

    cols = ["CAGR", "波動", "夏普", "Sortino", "Calmar", "MDD"]
    rows = []
    for n, e in sig.items():
        r = apply_daily_expo(dual, axis, np.asarray(e, float))
        m = metrics(r)
        et = era_sharpe(dual["as_of"], r)
        rows.append({"配置": n, "平均曝險": float(np.mean(e)) * 100,
                     **{c: m.get(c, np.nan) for c in cols}, "2022": et["2022空頭"],
                     "勝0050": sum(1 for x, _, _ in ERAS if et[x] > es_b[x])})

    print("\n" + "=" * 100)
    print("頭對頭 + 虛無對照 — 把候選跟『同平均曝險』的對照組對齊看")
    print("=" * 100)
    print(f"{'配置':<24}{'平均曝險':>9}" + "".join(f"{c:>9}" for c in cols) + f"{'2022':>8}{'勝0050':>8}")
    print("-" * 100)
    for r in rows:
        print(f"{r['配置']:<24}{r['平均曝險']:>8.1f}%"
              + "".join(f"{r[c]:>9.2f}" for c in cols)
              + f"{r['2022']:>8.2f}{r['勝0050']:>8d}")
    mb = metrics(bench)
    print("-" * 100)
    print(f"{'0050買進持有':<24}{'-':>9}" + "".join(f"{mb.get(c, np.nan):>9.2f}" for c in cols)
          + f"{es_b['2022空頭']:>8.2f}{'-':>8}")
    print("\n判讀:候選若沒明顯高過同曝險的『對照1』→ 那不是識別力,是風險旋鈕(可免費轉)。")
    print("      『對照2』遠差於全部 → 現行訊號本身是有價值的,只是已接近這套框架的上限。")


if __name__ == "__main__":
    main()
