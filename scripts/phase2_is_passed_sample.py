# -*- coding: utf-8 -*-
"""phase2_is_passed_sample.py — 抽樣量測「基本面硬門檻通過率 vs 資料缺口」

**為什麼要單獨跑**:`FundamentalEngine.evaluate()['is_passed']`(三個硬門檻的結果)
**不在診斷面板裡** —— 面板存的是分數,不是門檻判定。要量它就得重建 bundle,
所以只能抽樣,不能全 panel。

**這只是診斷**:不改任何公式、不下策略結論。

用法:python scripts/phase2_is_passed_sample.py --stocks 40
"""
from __future__ import annotations
import argparse
import os
import sys
import time

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIAG = os.path.join(os.path.dirname(_HERE), "data", "research_base", "diag",
                    "diag_scores_adv100w_diag.parquet")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks", type=int, default=40)
    ap.add_argument("--out", type=str,
                    default="beat_0050/results/phase2_is_passed_sample.csv")
    args = ap.parse_args()

    from beat_0050.realbody.bt_bundle import bt_fetch_history
    from core.backtest import build_pit_stockdata
    from core.fundamentals import FundamentalEngine

    diag = pd.read_parquet(DIAG, columns=["as_of", "stock_id", "f_fund", "pe_missing",
                                          "income_missing", "balance_missing",
                                          "cashflow_missing", "data_gaps", "rating"])
    diag["as_of"] = diag["as_of"].astype(str)
    diag["stock_id"] = diag["stock_id"].astype(str)
    ids = sorted(diag["stock_id"].unique())
    step = max(1, len(ids) // args.stocks)
    sample = ids[::step][:args.stocks]
    sub = diag[diag["stock_id"].isin(sample)]
    print(f"診斷面板 {len(diag):,} 列 / {len(ids)} 檔")
    print(f"抽樣 {len(sample)} 檔 → {len(sub):,} stock-months(等距抽樣)", flush=True)

    fe = FundamentalEngine()
    rows, t0 = [], time.time()
    for i, sid in enumerate(sample, 1):
        try:
            b = bt_fetch_history(sid)
        except Exception:
            continue
        for a in sorted(sub[sub["stock_id"] == sid]["as_of"].unique()):
            st = build_pit_stockdata(b, a)
            if st is None:
                continue
            r = fe.evaluate(vars(st))
            rows.append({"stock_id": sid, "as_of": a,
                         "is_passed": bool(r["is_passed"]),
                         "n_missing_fields": len(r["missing_fields"]),
                         "fund_confidence": float(r["confidence"]),
                         "grp_profit": r["group_scores"]["profitability"],
                         "grp_growth": r["group_scores"]["growth"],
                         "grp_safety": r["group_scores"]["safety"],
                         "grp_val": r["group_scores"]["valuation"]})
        if i % 10 == 0:
            el = time.time() - t0
            print(f"  [{i}/{len(sample)}] {len(rows):,} 列, {el:.0f}s "
                  f"(估剩 ~{(len(sample)-i)/i*el/60:.1f} 分)", flush=True)

    d = pd.DataFrame(rows).merge(sub, on=["stock_id", "as_of"], how="inner")
    d["all3_missing"] = d["income_missing"] & d["balance_missing"] & d["cashflow_missing"]
    d["has_gaps"] = d["data_gaps"] != ""
    d.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"\n明細 → {args.out}   {len(d):,} 列")

    print("\n" + "=" * 88)
    print("基本面硬門檻通過率 vs 資料缺口(抽樣)")
    print("=" * 88)
    print(f"{'分組':<34}{'列數':>9}{'is_passed%':>12}{'f_fund中位':>12}{'信心中位':>10}")
    groups = [("全體", pd.Series(True, index=d.index)),
              ("三大財報全缺", d["all3_missing"]),
              ("僅損益表缺", d["income_missing"] & ~d["all3_missing"]),
              ("PE 缺失", d["pe_missing"]),
              ("有 data_gaps", d["has_gaps"]),
              ("無任何缺口", ~d["has_gaps"] & ~d["pe_missing"] & ~d["all3_missing"])]
    for name, m in groups:
        if m.sum() == 0:
            print(f"{name:<34}{0:>9}{'—':>12}{'—':>12}{'—':>10}")
            continue
        g = d[m]
        print(f"{name:<34}{len(g):>9,}{g['is_passed'].mean()*100:>11.2f}%"
              f"{g['f_fund'].median():>12.1f}{g['fund_confidence'].median():>10.1f}")

    print("\n四個組分數的中位(看缺值把哪一組推到極端):")
    print(f"{'分組':<34}{'獲利':>9}{'成長':>9}{'安全':>9}{'估值':>9}")
    for name, m in groups:
        if m.sum() == 0:
            continue
        g = d[m]
        print(f"{name:<34}{g['grp_profit'].median():>9.1f}{g['grp_growth'].median():>9.1f}"
              f"{g['grp_safety'].median():>9.1f}{g['grp_val'].median():>9.1f}")


if __name__ == "__main__":
    main()
