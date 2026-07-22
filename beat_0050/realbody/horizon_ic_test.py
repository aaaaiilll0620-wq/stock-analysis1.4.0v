# -*- coding: utf-8 -*-
"""horizon_ic_test.py — 各面 IC × 持有期:技術/籌碼是否短天期更強、價值/基本面是否衰減?
================================================================================
用日線算各 as_of 的 1/3/5/10/20 交易日前瞻報酬,對五面分數逐月算 IC(排序相關)。
若技術/籌碼 IC 在短天期較高、價值/基本面在長天期較高 → 印證「短線技術籌碼重、長線價值重」。

誠實邊界:標的股票報酬(未含權證衰減/價差);未扣成本(短天期換手成本另計)。
================================================================================
"""
from __future__ import annotations
import sys
import bisect
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from beat_0050.honest_backtest import TEJ_CACHE

RB = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"
FACES = {"f_tech": "技術面", "f_mom": "動能面", "f_val": "估值面", "f_fund": "基本面", "f_whale": "籌碼面"}
HOR = [1, 3, 5, 10, 20]


def fwd_returns(rb: pd.DataFrame) -> pd.DataFrame:
    """對每檔用日線算各 as_of 的 H 日前瞻報酬。"""
    out = []
    for sid, g in rb.groupby("stock_id"):
        p = TEJ_CACHE / "price_valuation" / f"{sid}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["date", "close"]).dropna().sort_values("date")
        d["date"] = d["date"].astype(str)
        dates = d["date"].tolist(); close = d["close"].to_numpy(float)
        for asof in g["as_of"].unique():
            i = bisect.bisect_right(dates, asof) - 1
            if i < 0 or close[i] <= 0:
                continue
            row = {"as_of": asof, "stock_id": sid}
            for h in HOR:
                if i + h < len(close) and close[i + h] > 0:
                    r = close[i + h] / close[i] - 1.0
                    row[f"h{h}"] = r if abs(r) < 0.9 else np.nan   # 濾分割/異常
            out.append(row)
    return pd.DataFrame(out)


if __name__ == "__main__":
    rb = pd.read_parquet(RB)
    rb["as_of"] = rb["as_of"].astype(str); rb["stock_id"] = rb["stock_id"].astype(str)
    for f in FACES:
        rb[f] = pd.to_numeric(rb[f], errors="coerce")
    print("算各持有期前瞻報酬中(讀 ~2000 檔日線)...", flush=True)
    fr = fwd_returns(rb)
    m = rb.merge(fr, on=["as_of", "stock_id"], how="inner")

    def ic(df, face, hcol):
        ics = [g[face].rank(pct=True).corr(g[hcol].rank(pct=True))
               for _, g in df.groupby("as_of") if len(g) >= 50 and g[hcol].notna().sum() >= 40]
        ics = np.array([x for x in ics if not np.isnan(x)])
        t = ics.mean() / ics.std(ddof=1) * np.sqrt(len(ics)) if len(ics) > 1 else np.nan
        return ics.mean(), t

    print("\n" + "=" * 66)
    print("各面 IC × 持有期(排序相關;粗體=|t|>3 穩定)")
    print("=" * 66)
    print(f"{'面':<8}" + "".join(f"{'h'+str(h):>11}" for h in HOR))
    for f, lab in FACES.items():
        cells = []
        for h in HOR:
            v, t = ic(m, f, f"h{h}")
            star = "*" if abs(t) > 3 else " "
            cells.append(f"{v:+.4f}{star}")
        print(f"{lab:<8}" + "".join(f"{c:>11}" for c in cells))
    print("\n* = |t|>3。看技術/籌碼是否 h1→h20 遞減(短線強)、價值/基本面是否遞增(長線強)。")
