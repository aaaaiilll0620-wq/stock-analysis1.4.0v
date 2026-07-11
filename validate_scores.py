"""
綜合分排名有效性驗證 — 分位數階梯 + Rank IC (讀本機快取,0 API)
================================================================================
問題:網頁選股 / scores 快取是用『五維綜合分』排名的。這個排名到底有沒有預測力?
      「綜合分高的股票,後續 N 日報酬真的比較好嗎?」

本腳本用回測的 point-in-time 機制 (與 core.backtest 完全同一套,無未來函數) 回答:
  1) 分位數階梯:每個評級日把股票依綜合分切成 Q1..Qn (Q1 最低分、Qn 最高分),
     看各桶的『後續報酬平均 / 勝率』是不是隨分數階梯狀遞增 —— 最直觀的「分數有沒有用」。
  2) 市場中性多空:同日『最高桶 − 最低桶』的後續報酬差,逐期算再平均 (剃除大盤 beta)。
  3) Rank IC:每期綜合分 vs 後續報酬的 Spearman 秩相關均值 + ICIR + %>0 (最純的因子有效性)。

universe (母體) 預設對齊 scores 快取『實際排名的那批股票』(score_store.cached_symbols),
確保「驗證的名單 = 網頁選股的名單」。快取沒建時退回回測分散化測試池。

與現有工具的關係 (互補,不重造):
  · 深入的 train/test 多空、留一貢獻、五維各自 IC → 已在 tests/run_backtest.py:
        python tests/run_backtest.py --cache --attribution -m balanced
        python tests/run_backtest.py --cache --validate   -m balanced
        python tests/run_backtest.py --cache --cycle       -m balanced
  · 本腳本補的是它們沒有的『綜合分完整分位數階梯』,並把 universe 綁到 scores 快取。

用法 (需先 build_cache.py 建好原始快取;0 API):
  python validate_scores.py                         # balanced, 2023-2025, 月頻, 持有20, 五分位
  python validate_scores.py --modes balanced conservative aggressive
  python validate_scores.py --start 2022-01-01 --end 2025-12-31 --quantiles 5 --holding 20
  python validate_scores.py 2330 2454 2317          # 指定 universe (覆蓋 scores 快取名單)
================================================================================
"""
from __future__ import annotations

import os
import sys
import argparse
from collections import defaultdict
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
logging.basicConfig(level=logging.WARNING)

from core.backtest import Backtester, cached_fetch_history, output_path
from core.scoring_manager import ScoringManager
from core import score_store


# ------------------------------------------------------------------------------
# universe 解析:預設對齊 scores 快取名單,退回回測測試池
# ------------------------------------------------------------------------------
def resolve_universe(explicit: Optional[Sequence[str]], mode: Optional[str]) -> List[str]:
    if explicit:
        return [s.strip().upper() for s in explicit if s.strip()]
    syms = score_store.cached_symbols(mode=None)     # 跨模式聯集 = 網頁選股實際涵蓋的股票
    if syms:
        return syms
    try:
        from tests.run_backtest import DIVERSIFIED_POOL
        return list(DIVERSIFIED_POOL)
    except Exception:
        return ["2330", "2454", "2317"]


# ------------------------------------------------------------------------------
# 指標:Rank IC / 分位數階梯 / 市場中性多空 (皆基於 (as_of, composite, fwd) 觀測)
# ------------------------------------------------------------------------------
def rank_ic(scored) -> Optional[dict]:
    """每期綜合分 vs 後續報酬的 Spearman 秩相關。回傳 mean/std/ICIR/%>0/期數。"""
    by = defaultdict(list)
    for as_of, score, fwd, _rating in scored:
        by[as_of].append((score, fwd))
    ics = []
    for _, items in by.items():
        if len(items) < 4:
            continue
        xs = pd.Series([x for x, _ in items]).rank()
        ys = pd.Series([y for _, y in items]).rank()
        if xs.std() == 0 or ys.std() == 0:
            continue
        ics.append(float(xs.corr(ys)))
    if len(ics) < 3:
        return None
    arr = np.array(ics)
    mean, std = float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    return {
        "mean": mean,
        "std": std,
        "icir": (mean / std) if std > 0 else float("nan"),
        "pct_pos": float((arr > 0).mean() * 100),
        "periods": len(ics),
    }


def quantile_ladder(scored, n: int = 5) -> Optional[dict]:
    """
    每期依綜合分把股票分成 n 桶 (rank 法,避免 qcut 邊界重複問題),
    彙整各桶『後續報酬平均 / 勝率 / 樣本數』(pooled),並算逐期平均的最高−最低桶多空。
    回傳 dict:ladder(list) / long_short / ls_periods / mono_spearman;樣本不足回 None。
    """
    per_bucket = defaultdict(list)          # bucket(1..n) -> [fwd,...]  (pooled)
    ls_per_date = []                        # 逐期 (最高桶均 − 最低桶均)
    by = defaultdict(list)
    for as_of, score, fwd, _rating in scored:
        by[as_of].append((score, fwd))

    for _, items in by.items():
        if len(items) < n:                  # 該期樣本數需 >= 桶數才能切
            continue
        s = pd.Series([x for x, _ in items])
        f = pd.Series([y for _, y in items])
        ranks = s.rank(method="first")
        buckets = np.ceil(ranks / len(items) * n).clip(1, n).astype(int)
        for b, fwd in zip(buckets, f):
            per_bucket[int(b)].append(float(fwd))
        top = f[buckets == n]
        bot = f[buckets == 1]
        if len(top) and len(bot):
            ls_per_date.append(float(top.mean() - bot.mean()))

    if not per_bucket or len(ls_per_date) < 3:
        return None

    ladder = []
    for b in range(1, n + 1):
        vals = per_bucket.get(b, [])
        if not vals:
            ladder.append({"q": b, "n": 0, "avg": float("nan"), "win": float("nan")})
            continue
        v = np.array(vals)
        ladder.append({
            "q": b, "n": len(v),
            "avg": float(v.mean()),
            "win": float((v > 0).mean() * 100),
        })

    # 階梯單調性:桶序 (1..n) 與桶平均報酬的 Spearman 秩相關 (越接近 +1 越單調遞增)
    means = [row["avg"] for row in ladder if not np.isnan(row["avg"])]
    idx = [row["q"] for row in ladder if not np.isnan(row["avg"])]
    mono = float(pd.Series(idx).rank().corr(pd.Series(means).rank())) if len(means) >= 3 else float("nan")

    return {
        "ladder": ladder,
        "long_short": float(np.mean(ls_per_date)),
        "ls_periods": len(ls_per_date),
        "mono_spearman": mono,
    }


# ------------------------------------------------------------------------------
# 單一模式驗證
# ------------------------------------------------------------------------------
def validate_mode(symbols: List[str], mode: str, start: str, end: str,
                  rebalance: str, holding: int, n_quantiles: int) -> Optional[dict]:
    bt = Backtester(symbols=symbols, mode=mode)
    print(f"\n[{mode}] 載入 {len(symbols)} 檔本機快取並預算 PIT 特徵 (0 API)…")
    bt.load(fetcher=lambda s: cached_fetch_history(s, refresh=False))
    cache = bt._precompute(start, end, rebalance, holding)
    if not cache:
        print(f"[{mode}] ⚠️ 無足夠資料 (是否已 build_cache.py 建原始快取、且日期區間有交易日?)")
        return None
    scored = bt._scored_records(cache, bt.advisor)   # [(as_of, composite, fwd, rating)]
    if not scored:
        print(f"[{mode}] ⚠️ 評分結果為空。")
        return None

    ic = rank_ic(scored)
    lad = quantile_ladder(scored, n=n_quantiles)
    obs_dates = sorted({r[0] for r in scored})

    # ---- 輸出 ----
    print("\n" + "=" * 72)
    print(f"綜合分排名有效性 — 模式 {mode}  ({start} ~ {end}, {rebalance}頻, 持有{holding}日)")
    print(f"  universe {len(symbols)} 檔 | 觀測 {len(scored)} 筆 | 評級期 {len(obs_dates)} 期"
          f" | 門檻 min_score {ScoringManager.MODES[mode]['min_score']}")
    print("=" * 72)

    if lad:
        print(f"\n【分位數階梯】綜合分由低到高分 {n_quantiles} 桶,各桶後續報酬 (pooled):")
        print(f"  {'桶':>3} {'樣本':>6} {'平均報酬%':>10} {'勝率%':>8}")
        for row in lad["ladder"]:
            avg = "n/a" if np.isnan(row["avg"]) else f"{row['avg']:+.2f}"
            win = "n/a" if np.isnan(row["win"]) else f"{row['win']:.1f}"
            tag = "  ← 最高分" if row["q"] == n_quantiles else ("  ← 最低分" if row["q"] == 1 else "")
            print(f"  Q{row['q']:>2} {row['n']:>6} {avg:>10} {win:>8}{tag}")
        mono = lad["mono_spearman"]
        mono_s = "n/a" if np.isnan(mono) else f"{mono:+.2f}"
        print(f"\n  市場中性多空 (最高桶 − 最低桶,逐期平均):{lad['long_short']:+.2f}%"
              f"  (含 {lad['ls_periods']} 期)")
        print(f"  階梯單調性 (桶序 vs 桶均報酬 Spearman):{mono_s}"
              f"  {'✅ 明顯單調遞增' if (not np.isnan(mono) and mono >= 0.7) else ''}")
    else:
        print("\n【分位數階梯】樣本不足以分桶 (universe 或期數太少)。")

    if ic:
        icir = "n/a" if np.isnan(ic["icir"]) else f"{ic['icir']:+.2f}"
        print(f"\n【Rank IC】綜合分 vs 後續報酬 Spearman 秩相關 (每期一值,再彙整):")
        print(f"  平均 IC {ic['mean']:+.3f} | 標準差 {ic['std']:.3f} | ICIR {icir} "
              f"| IC>0 佔 {ic['pct_pos']:.0f}% | {ic['periods']} 期")
        verdict = ("✅ 有排序力" if ic["mean"] > 0.02 else
                   "⚠️ 排序力偏弱" if ic["mean"] > 0 else "❌ 無正向排序力")
        print(f"  判定:{verdict}  (參考:Rank IC 平均 > 0.02~0.03 一般視為有效因子)")
    else:
        print("\n【Rank IC】有效期數不足,無法估計。")

    return {"mode": mode, "ic": ic, "ladder": lad, "n_obs": len(scored),
            "n_periods": len(obs_dates), "universe": len(symbols)}


def save_summary(results: List[dict], start: str, end: str) -> Optional[str]:
    """把各模式的關鍵指標存成一張 CSV,方便留存/比較。"""
    rows = []
    for r in results:
        if not r:
            continue
        ic = r.get("ic") or {}
        lad = r.get("ladder") or {}
        rows.append({
            "mode": r["mode"], "universe": r["universe"],
            "obs": r["n_obs"], "periods": r["n_periods"],
            "ic_mean": round(ic.get("mean", float("nan")), 4) if ic else None,
            "icir": round(ic.get("icir", float("nan")), 3) if ic else None,
            "ic_pct_pos": round(ic.get("pct_pos", float("nan")), 1) if ic else None,
            "long_short_pct": round(lad.get("long_short", float("nan")), 3) if lad else None,
            "ladder_monotonicity": round(lad.get("mono_spearman", float("nan")), 3) if lad else None,
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    path = output_path("validation", f"composite_validation_{start}_{end}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def main():
    ap = argparse.ArgumentParser(description="綜合分排名有效性驗證 (分位數階梯 + Rank IC;0 API)")
    ap.add_argument("symbols", nargs="*", help="universe 代號;省略則對齊 scores 快取名單")
    ap.add_argument("--modes", nargs="*", default=["balanced"],
                    help="要驗證的模式 (預設 balanced);例:--modes balanced conservative aggressive")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--rebalance", default="M", help="M(月) 或 W(週)")
    ap.add_argument("--holding", type=int, default=20, help="後續報酬持有交易日數 (預設 20)")
    ap.add_argument("--quantiles", type=int, default=5, help="分位數桶數 (預設 5)")
    ap.add_argument("--no-save", action="store_true", help="不輸出 CSV 摘要")
    args = ap.parse_args()

    for m in args.modes:
        if m not in ScoringManager.MODES:
            print(f"⚠️ 未知模式 {m!r};可用:{list(ScoringManager.MODES)}")
            return

    symbols = resolve_universe(args.symbols, mode=None)
    src = "指定" if args.symbols else ("scores 快取名單" if score_store.cached_symbols() else "回測測試池(scores 快取尚未建)")
    print(f"universe 來源:{src} — 共 {len(symbols)} 檔")

    results = []
    for m in args.modes:
        results.append(validate_mode(symbols, m, args.start, args.end,
                                     args.rebalance, args.holding, args.quantiles))

    if not args.no_save:
        path = save_summary(results, args.start, args.end)
        if path:
            print(f"\n📄 摘要已存:{path}")

    print("\n說明:分位數階梯與市場中性多空為『相對排序』證據 (剃除大盤);Rank IC 為因子有效性核心指標。")
    print("     更深入的 train/test 樣本外、留一貢獻、五維各自 IC 見:"
          "python tests/run_backtest.py --cache --attribution/--validate/--cycle")


if __name__ == "__main__":
    main()
