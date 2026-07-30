# -*- coding: utf-8 -*-
"""build_exec_ret.py — 為 obs_alpha 全面板建「可執行」前瞻報酬欄。
================================================================================
問題(見記憶 obs-alpha-fwd-close-bias):
    obs_alpha.fwd = close(T) → close(T+20)。訊號在 T 收盤才算得出來,這條線買不到。
    實測 high52 高換手 arm 因此被高估 5.6pp/年。所有建在 fwd 上的 lab 都繼承這個偏誤。

本腳本用 tej_cache 日價格線,對面板每一列算:
    fwd_t1 = open(T+1) → open(T+21)   ← 可執行基準(訊號日收盤算出,隔日開盤下單)
    fwd_t2 = open(T+2) → open(T+22)   ← 慢一天的敏感度對照
    fwd_cc = close(T) → close(T+20)   ← 重算 obs_alpha.fwd 當作對帳用
含息方式沿用既有慣例:dividend_yield_TSE(T) / 12 加在報酬上。
另存 px_in(進場開盤價)與 tick_slip(1 跳價差 / 進場價 × 1.15),供成本模型逐列使用。

    fwd_x   = open(本月訊號日+1) → open(下月訊號日+1)   ← **主用**。串接無縫隙無重疊,
                                                        串起來正好等於買進持有
    fwd_x60 = open(本月訊號日+1) → open(3 個月後訊號日+1) ← 60 交易日視野(籃內離散度用)

輸出:data/research_base/exec_ret.parquet
      (as_of, stock_id, fwd_x, fwd_x60, fwd_t1, fwd_t2, fwd_cc, px_in, tick_slip)
================================================================================
"""
from __future__ import annotations
import os
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJ = Path(r"C:\dev\Project 1")
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
OBS_ALPHA = PROJ / "data" / "research_base" / "obs_alpha.parquet"
OUT = PROJ / "data" / "research_base" / "exec_ret.parquet"
HOLD = 20  # 交易日


def main() -> None:
    t0 = time.time()
    obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "fwd"])
    print(f"面板 {len(obs):,} 列 / {obs['as_of'].nunique()} 月 / {obs['stock_id'].nunique()} 檔")

    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.register("obs", obs[["as_of", "stock_id"]])

    con.execute(f"""
        CREATE TEMP TABLE px AS
        SELECT stock_id, date, open, close, dividend_yield_TSE AS dy,
               row_number() OVER (PARTITION BY stock_id ORDER BY date) AS i
        FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        WHERE close > 0
    """)
    print(f"日價格線 {con.execute('SELECT count(*) FROM px').fetchone()[0]:,} 列  "
          f"({time.time()-t0:.0f}s)")

    # ASOF JOIN:每個 (as_of, stock_id) 取 <= as_of 的最後一個交易日
    base = con.execute("""
        SELECT o.as_of, o.stock_id, p.i AS i0, p.dy, p.close AS c0
        FROM obs o ASOF JOIN px p
          ON o.stock_id = p.stock_id AND p.date <= o.as_of
    """).df()

    # 執行對齊窗:本月出場日 = 下一個 as_of 的隔日開盤 → 串起來無縫隙、無重疊
    months = np.array(sorted(base["as_of"].unique()))
    tmap = {m: i for i, m in enumerate(months)}
    base["t"] = base["as_of"].map(tmap)
    base = base.sort_values(["stock_id", "t"]).reset_index(drop=True)
    g = base.groupby("stock_id")
    nt, ni = g["t"].shift(-1), g["i0"].shift(-1)
    base["ix"] = np.where(nt == base["t"] + 1, ni, np.nan)    # 僅接受「緊鄰的下一個月」
    # 60 交易日視野(≈3 個月)的執行對齊窗,供 basket_dispersion_lab 取代 obs_dump_h60.fwd
    nt3, ni3 = g["t"].shift(-3), g["i0"].shift(-3)
    base["ix3"] = np.where(nt3 == base["t"] + 3, ni3, np.nan)
    con.register("base", base[["as_of", "stock_id", "i0", "ix", "ix3", "dy", "c0"]])

    res = con.execute(f"""
        SELECT b.as_of, b.stock_id,
               a1.open AS o1, a2.open AS o2,
               b1.open AS q1, b2.open AS q2,
               x2.open AS ox, x3.open AS ox3,
               b.c0, cc.close AS c1,
               least(greatest(coalesce(b.dy, 0), 0), 15) / 12.0 AS dy12
        FROM base b
        LEFT JOIN px a1 ON a1.stock_id = b.stock_id AND a1.i = b.i0 + 1
        LEFT JOIN px a2 ON a2.stock_id = b.stock_id AND a2.i = b.i0 + 1 + {HOLD}
        LEFT JOIN px b1 ON b1.stock_id = b.stock_id AND b1.i = b.i0 + 2
        LEFT JOIN px b2 ON b2.stock_id = b.stock_id AND b2.i = b.i0 + 2 + {HOLD}
        LEFT JOIN px x2 ON x2.stock_id = b.stock_id AND x2.i = CAST(b.ix AS BIGINT) + 1
        LEFT JOIN px x3 ON x3.stock_id = b.stock_id AND x3.i = CAST(b.ix3 AS BIGINT) + 1
        LEFT JOIN px cc ON cc.stock_id = b.stock_id AND cc.i = b.i0 + {HOLD}
    """).df()
    print(f"join 完成 {len(res):,} 列  ({time.time()-t0:.0f}s)")

    def ret(pin, pout, dy12):
        pin = pd.to_numeric(pin, errors="coerce")
        pout = pd.to_numeric(pout, errors="coerce")
        r = np.where((pin > 0) & (pout > 0), (pout / pin - 1) * 100 + dy12, np.nan)
        return r

    out = pd.DataFrame({
        "as_of": res["as_of"],
        "stock_id": res["stock_id"],
        "fwd_x": ret(res["o1"], res["ox"], res["dy12"]),        # 執行對齊窗(主用,≈20 交易日)
        "fwd_x60": ret(res["o1"], res["ox3"], res["dy12"] * 3),  # 3 個月窗(≈60 交易日)
        "fwd_t1": ret(res["o1"], res["o2"], res["dy12"]),
        "fwd_t2": ret(res["q1"], res["q2"], res["dy12"]),
        "fwd_cc": ret(res["c0"], res["c1"], res["dy12"]),
    })
    px_in = pd.to_numeric(res["o1"], errors="coerce")
    out["px_in"] = px_in
    tk = np.full(len(px_in), 5.0)
    for hi, t in [(1000, 1.0), (500, 0.5), (100, 0.1), (50, 0.05), (10, 0.01)]:
        tk = np.where(px_in.fillna(1e9) < hi, t, tk)
    out["tick_slip"] = np.clip(tk / px_in * 100 * 1.15, 0.05, 2.0)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)

    # ---- 對帳 ----
    chk = out.merge(obs, on=["as_of", "stock_id"], how="left")
    m = chk["fwd_cc"].notna() & chk["fwd"].notna()
    d = (chk.loc[m, "fwd_cc"] - chk.loc[m, "fwd"])
    print("\n" + "=" * 74)
    print("對帳:重算的 close→close vs 面板既有 fwd 欄")
    print("=" * 74)
    print(f"可比列數 {m.sum():,}  |  差值 中位 {d.median():+.4f}pp  平均 {d.mean():+.4f}pp  "
          f"|差|>1pp 佔 {(d.abs() > 1).mean()*100:.2f}%")
    print(f"(fwd 欄不含息,重算的含 dy/12,故應有正的小偏移 ≈ 年化股利/12)")
    for c in ["fwd_x", "fwd_x60", "fwd_t1", "fwd_t2", "fwd_cc"]:
        print(f"{c:<8} 覆蓋率 {out[c].notna().mean()*100:5.1f}%  均值 {out[c].mean():+6.3f}pp")
    print(f"\n→ {OUT}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
