# -*- coding: utf-8 -*-
"""composite_c2_direction.py — 交集邊際訊號的方向:誰在誰的池子裡做精選?
================================================================================
不是預註冊(同 composite_c2_attribution.py):純歸因分解,不對候選下判定。

上一步(composite_c2_attribution.py)發現:
  - 交集(arm3)贏「c2 同集中度(arm5)」穩健顯著(t 2.34~4.90)
  - 交集(arm3)贏「綜合分同集中度(arm4)」從未顯著(t 1.02~1.75)
  - 但綜合分自己往尾端集中(arm1→arm4)Sharpe 反而下降 —— 矛盾:
    如果綜合分深挖尾端沒用,arm3 對 arm4 的邊際優勢(雖不顯著)從何而來?

本腳本用巢狀選股拆解方向:
  arm7 = 先過綜合分 Top20%(粗篩,~200檔),池內再用 c2 深選 Top-N(N=arm3 月度檔數)
  arm8 = 先過 c2 Top20%(粗篩),池內再用綜合分深選 Top-N
  若 arm7 ≈ arm3 → c2 在綜合分的合格池裡做精選,綜合分只是粗篩網
  若 arm8 ≈ arm3 → 綜合分在 c2 的合格池裡做精選,c2 只是粗篩網

外加兩個診斷:
  (a) overlap —— arm3 的月度選股有多少比例已經被 arm4/arm5(單腿深選)涵蓋
  (b) arm3 選中的股票,在「綜合分 Top20% 池」內部排名的百分位分布
      (是不是集中在池子最頂端,還是分散在整個 20% 帶內)

用法:python beat_0050/strategies/composite_c2_direction.py --tier 100萬 --window full
================================================================================
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from high52_lab import Panel, evaluate, met, turnover, paired  # noqa: E402
from composite_c2_attribution import (  # noqa: E402
    composite_and_c2_scores, topk_pct_mask, topk_n_mask, apply_window, SEED,
)


def topk_n_within(P: Panel, prefilter: np.ndarray, score: np.ndarray,
                  n_per_month: np.ndarray) -> np.ndarray:
    """在 prefilter 遮罩內(逐月),依 score 取前 N 檔(可變 N)。"""
    ok = prefilter & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
    kk = np.maximum(0, n_per_month.astype(int))
    return (rk <= kk[:, None]) & ok


def rank_pct_within(P: Panel, prefilter: np.ndarray, score: np.ndarray) -> np.ndarray:
    """逐月:在 prefilter 池內,score 的百分位排名(1=池內最好,越大越差;NaN=不在池內)。"""
    ok = prefilter & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.float64)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.float64)[None, :], axis=1)
    nv = ok.sum(1).astype(float)[:, None]
    pct = np.where(ok, (rk - 1) / np.maximum(nv - 1, 1), np.nan)  # 0=最好,1=池內最差
    return pct


def run(tier: str, window: str, adv_floor: float) -> None:
    print("\n" + "=" * 100)
    print(f"方向拆解 · ADV≥{tier} · window={window}(非預註冊)")
    print("=" * 100)
    P = Panel(realbody_floor=adv_floor)
    wmask = apply_window(P, window)
    composite, c2 = composite_and_c2_scores(P, tier)

    M1 = topk_pct_mask(P, composite, tier, 20)   # 綜合分 Top20%(粗篩池)
    M2 = topk_pct_mask(P, c2, tier, 20)          # c2 Top20%(粗篩池)
    M3 = M1 & M2                                 # 交集(觀測值)
    n3 = M3.sum(1).astype(np.int64)
    M4 = topk_n_mask(P, composite, tier, n3)      # 綜合分自己深選同 N(上一步的 arm4)
    M5 = topk_n_mask(P, c2, tier, n3)             # c2 自己深選同 N(上一步的 arm5)

    def clip(M):
        Mc = M.copy(); Mc[~wmask] = False; return Mc

    arms = {
        "3 交集(觀測值,寬20%∩寬20%)": clip(M3),
        "4 綜合分深選同N(全域=寬100%)": clip(M4),
        "5 c2深選同N(全域=寬100%)": clip(M5),
    }
    series = {k: evaluate(v, P.RET, P.SLIP) for k, v in arms.items()}

    print(f"\n{'arm':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月換手%':>10}{'月均檔數':>10}")
    for k, v in arms.items():
        m = met(series[k])
        act = v.sum(1) > 0
        avg_n = float(v.sum(1)[wmask & act].mean()) if (wmask & act).any() else float("nan")
        print(f"{k:<30}{m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}"
              f"{m.get('mdd', np.nan):>9.1f}{turnover(v)*100:>10.1f}{avg_n:>10.1f}")

    # ---- 粗篩寬度掃描:N(=arm3 逐月檔數)固定不動,只改「誰有資格參賽」的粗篩寬度 ----
    # 20% 端點 = arm3(交集)本身(數學恆等,見上一版 arm7/arm8 的教訓);
    # 100% 端點 = arm4/arm5(全域深選,無粗篩)。中間點量的是粗篩精確度的邊際價值:
    # 若換一個更寬的粗篩、把精選完全交給另一個分數,績效還在 → 粗篩只是門檻不是資訊來源。
    rng = np.random.default_rng(SEED + 7)
    widths = [10, 15, 20, 30, 50, 70, 100]
    print(f"\n粗篩寬度掃描(固定 N=arm3 逐月檔數,只改粗篩寬度,{'綜合分粗篩→c2深選':}):")
    print(f"{'綜合分粗篩寬度':<16}{'CAGR%':>9}{'夏普':>8}{'vs arm3 配對t':>16}")
    sweep_a = {}
    for w in widths:
        pref = M1 if w == 20 else topk_pct_mask(P, composite, tier, w)
        M = topk_n_within(P, pref, c2, n3)
        Mc = clip(M)
        s = evaluate(Mc, P.RET, P.SLIP)
        m = met(s)
        r = paired(series["3 交集(觀測值,寬20%∩寬20%)"], s, rng)
        sweep_a[w] = m.get("sharpe", np.nan)
        print(f"{w:>13}%  {m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}{r['t']:>16.2f}")

    print(f"\n粗篩寬度掃描(固定 N=arm3 逐月檔數,只改粗篩寬度,c2粗篩→綜合分深選):")
    print(f"{'c2粗篩寬度':<16}{'CAGR%':>9}{'夏普':>8}{'vs arm3 配對t':>16}")
    sweep_b = {}
    for w in widths:
        pref = M2 if w == 20 else topk_pct_mask(P, c2, tier, w)
        M = topk_n_within(P, pref, composite, n3)
        Mc = clip(M)
        s = evaluate(Mc, P.RET, P.SLIP)
        m = met(s)
        r = paired(series["3 交集(觀測值,寬20%∩寬20%)"], s, rng)
        sweep_b[w] = m.get("sharpe", np.nan)
        print(f"{w:>13}%  {m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}{r['t']:>16.2f}")

    print("\n判讀掃描:")
    drop_a = sweep_a[20] - sweep_a[100]
    drop_b = sweep_b[20] - sweep_b[100]
    print(f"  綜合分粗篩從 20%→100%(即拿掉粗篩,交給 c2 全權深選):夏普降 {drop_a:+.2f}"
          f"({'綜合分粗篩仍有價值' if drop_a > 0.05 else '拿掉綜合分粗篩幾乎無損,c2 自己就夠'})")
    print(f"  c2   粗篩從 20%→100%(即拿掉粗篩,交給綜合分全權深選):夏普降 {drop_b:+.2f}"
          f"({'c2 粗篩仍有價值' if drop_b > 0.05 else '拿掉 c2 粗篩幾乎無損,綜合分自己就夠'})")

    # ---- overlap 診斷:arm3 有多少比例已被 arm4/arm5(全域深選)涵蓋 ----
    def recall(sub: np.ndarray, full: np.ndarray, w: np.ndarray) -> float:
        num = (sub & full & w[:, None]).sum()
        den = (sub & w[:, None]).sum()
        return float(num / den) if den else float("nan")

    r4 = recall(M3, M4, wmask)
    r5 = recall(M3, M5, wmask)
    print(f"\noverlap(arm3 有多少比例落在...):")
    print(f"  綜合分全域深選(arm4)內: {r4*100:.1f}%")
    print(f"  c2   全域深選(arm5)內: {r5*100:.1f}%")
    print(f"  → 兩者都低,代表 arm3 的股票大多不是任何一邊自己排序的絕對頂尖,"
          f"而是要「兩邊都及格」才會被交集選中。")

    # ---- arm3 選中的股票,在各自粗篩池內部的排名百分位分布(0=池內最好,1=池內最差) ----
    pc_in1 = rank_pct_within(P, M1, c2)          # 在「綜合分池」內,用 c2 排 → arm3 落在哪
    pv_in2 = rank_pct_within(P, M2, composite)   # 在「c2 池」內,用綜合分排 → arm3 落在哪
    sel = M3 & wmask[:, None]
    v1 = pc_in1[sel]
    v2 = pv_in2[sel]
    print(f"\narm3 選中股票在粗篩池內部的排名百分位(0=池內最好,1=池內最差,N={sel.sum()}):")
    print(f"  綜合分池內,用 c2 排:平均 {np.nanmean(v1):.3f}  中位 {np.nanmedian(v1):.3f}  "
          f"P90 {np.nanpercentile(v1,90):.3f}")
    print(f"  c2 池內,用綜合分排:  平均 {np.nanmean(v2):.3f}  中位 {np.nanmedian(v2):.3f}  "
          f"P90 {np.nanpercentile(v2,90):.3f}")
    print("  → 數字越接近 0,代表 arm3 選中的股票在該池內部排名越靠前(該分數在做精選);"
          "越接近 0.5,代表該分數在池內幾乎不分高下(該分數只在做粗篩,精選是另一個分數做的)。")


def main() -> int:
    ap = argparse.ArgumentParser(description="方向拆解:誰在誰的池子裡做精選")
    ap.add_argument("--tier", default="100萬", choices=["100萬", "2000萬"])
    ap.add_argument("--window", default="full", choices=["full", "oos2010"])
    ap.add_argument("--adv-floor", type=float, default=None)
    args = ap.parse_args()
    floor = args.adv_floor or (1e6 if args.tier == "100萬" else 2e7)
    run(args.tier, args.window, floor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
