# -*- coding: utf-8 -*-
"""build_realbody_scores.py — B全循環:對 obs_alpha 母體逐月跑 App 真身五面綜合分。
================================================================================
對 obs_alpha 的每個 (stock_id, as_of)(listed_ok & adv20 過濾),用回測版 bundle 跑真身
score_row → 真實綜合分。輸出面板供後續組 dual 持股、餵誠實引擎、對 proxy/0050 比。

蘋果對蘋果:跑在 obs_alpha 相同 stock-months(同母體、同 fwd),真身 vs proxy 直接可比。
效能:每檔 bundle 只建一次,對其所有 as_of 逐一評分。

用法:python -m beat_0050.realbody.build_realbody_scores --year 2023       # 驗證單年
      python -m beat_0050.realbody.build_realbody_scores                   # 全循環 2005-2026
      (--limit N 只跑前 N 檔;--out 指定輸出)
================================================================================
"""
from __future__ import annotations
import argparse
import sys
import time
import warnings
from pathlib import Path
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from beat_0050.honest_backtest import OBS_ALPHA
from beat_0050.realbody.bt_bundle import bt_fetch_history
from core.score_store import score_row, _engines

OUT_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "research_base" / "realbody_scores.parquet"
ADV_FLOOR = 2e7
MODE = "balanced"

_ENG = None


def _init_worker():
    global _ENG
    warnings.filterwarnings("ignore")
    _ENG = _engines(MODE)


def _score_stock(task):
    """(sid, [as_of...]) → [row...];每檔 bundle 只建一次,對其所有 as_of 評分。"""
    sid, asofs = task
    try:
        bundle = bt_fetch_history(sid)
    except Exception:
        return []
    out = []
    for asof in asofs:
        try:
            r = score_row(bundle, asof, MODE, _ENG)
        except Exception:
            r = None
        if r:
            out.append({"as_of": asof, "stock_id": sid,
                        "real_composite": r.get("composite"), "rating": r.get("rating"),
                        "f_tech": r.get("technical"), "f_mom": r.get("momentum"),
                        "f_whale": r.get("whale"), "f_fund": r.get("fundamental"),
                        "f_val": r.get("valuation")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None, help="只跑某年 (驗證用)")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 檔 (驗證用)")
    ap.add_argument("--out", type=str, default=str(OUT_DEFAULT))
    ap.add_argument("--workers", type=int, default=6, help="平行進程數")
    args = ap.parse_args()

    obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "adv20", "listed_ok"])
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= ADV_FLOOR)]        # noqa: E712
    obs["as_of"] = obs["as_of"].astype(str)
    if args.year:
        obs = obs[obs["as_of"].str.startswith(str(args.year))]
    stocks = sorted(obs["stock_id"].astype(str).unique())
    if args.limit:
        stocks = stocks[:args.limit]
    asof_by_stock = obs.groupby(obs["stock_id"].astype(str))["as_of"].apply(lambda s: sorted(set(s)))

    tasks = [(sid, asof_by_stock.get(sid, [])) for sid in stocks]
    rows, t0, done = [], time.time(), 0
    from multiprocessing import Pool
    with Pool(args.workers, initializer=_init_worker) as pool:
        for i, res in enumerate(pool.imap_unordered(_score_stock, tasks, chunksize=4)):
            rows.extend(res); done += len(res)
            if (i + 1) % 100 == 0:
                el = time.time() - t0
                print(f"  {i+1}/{len(stocks)} 檔, {done} 列, {el:.0f}s "
                      f"({done/el:.0f} 列/s, 估剩 ~{(len(stocks)-i-1)/(i+1)*el/60:.0f} 分)", flush=True)

    out = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    el = time.time() - t0
    print(f"\n✅ {len(out)} 列 ({out['stock_id'].nunique()} 檔 × {out['as_of'].nunique()} 月), "
          f"{el:.0f}s → {args.out}")
    if len(out):
        print(f"real_composite: 中位 {out['real_composite'].median():.1f}, "
              f"範圍 {out['real_composite'].min():.1f}~{out['real_composite'].max():.1f}")
        print("評級分布:", out["rating"].value_counts().to_dict())


if __name__ == "__main__":
    main()
