# -*- coding: utf-8 -*-
"""composite_c2_attribution.py — 拆解「雙確認贏過兩條腿單獨」是訊號互補還是集中度
================================================================================
不是預註冊:本腳本**不對任何候選下 pass/fail 判定**,只做歸因分解,不影響
`docs/預註冊_雙確認ADV100萬.md` 或任何 Gate 的既有結論。

問題:全期 CAGR(ADV≥2000萬):綜合分 10.97 < 純 c2 12.58 < 雙確認(交集)14.97。
交集比兩條腿單獨都好,但交集同時把持股從 ~100 檔壓到 ~25 檔。訊號效應與
集中度效應從未被分開過。

六個 arm:
  1. 綜合分 Top-20%(全寬度)
  2. c2      Top-20%(全寬度)
  3. 雙確認 = 綜合分 Top-20% ∩ c2 Top-20%(觀測值,持股數逐月變動)
  4. 綜合分 Top-N,N = arm3 逐月實際持股數(同集中度,只有綜合分訊號)
  5. c2      Top-N,N 同上(同集中度,只有 c2 訊號)
  6. 隨機 Top-N,N 同上,×REPS(換手對齊虛無,集中度的下界)

判讀:arm3 ≈ max(arm4, arm5) → 贏的是集中度,不是訊號互補。
     arm3 顯著 > max(arm4, arm5) 且兩者都顯著 > arm6 → 訊號互補是真的。

用法:
    python beat_0050/strategies/composite_c2_attribution.py --tier 100萬
    python beat_0050/strategies/composite_c2_attribution.py --tier 2000萬 --window oos2010
    python beat_0050/strategies/composite_c2_attribution.py --tier 100萬 --reps 500
================================================================================
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from high52_lab import (Panel, evaluate, met, turnover, paired)  # noqa: E402

SEED = 20260809
OUTDIR = PROJ / "beat_0050" / "results"


# ------------------------------------------------------------------------------
def _pct(P: Panel, tier: str, factor: str) -> np.ndarray:
    """逐月橫斷面百分位(0~100,越高越好)。與 dual_confirm_mask 內部 pct() 邏輯相同,
    此處獨立複製 —— 不修改凍結中的 high52_lab.py。"""
    valid = P.tier_valid[tier]
    v = P.F[factor]
    ok = valid & np.isfinite(v)
    x = np.where(ok, v, -np.inf).astype(np.float64)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.float64)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.float64)[None, :], axis=1)
    nv = ok.sum(1).astype(float)[:, None]
    return np.where(ok, 100.0 * (1.0 - (rk - 1) / np.maximum(nv, 1)), np.nan)


def composite_and_c2_scores(P: Panel, tier: str) -> tuple[np.ndarray, np.ndarray]:
    """回 (composite, c2) 分數矩陣。composite = 真身 REAL_COMP;
    c2 定義沿用 dual_confirm_mask:(value_ind + revenue_yoy + high52_prox + (100-momentum)) / 4。

    覆蓋率閘門與 dual_confirm_mask 相同(min_cov=1.0,零靜默損失):該 tier 母體
    必須 100% 有真身分數,否則 raise —— 不靜默退化成「∩ 面板門檻」。"""
    valid = P.tier_valid[tier]
    cov = np.isfinite(P.REAL_COMP[valid]).mean() if valid.any() else 0.0
    if cov < 1.0:
        raise ValueError(
            f"tier={tier} 的真身綜合分覆蓋率僅 {cov:.1%}(面板 {P.realbody_path},"
            f"門檻 ADV≥{P.realbody_floor:,.0f})。用 --adv-floor 指到能覆蓋此 tier 的面板。")
    f, v = _pct(P, tier, "revenue_yoy"), _pct(P, tier, "value_ind")
    m = _pct(P, tier, "momentum")
    h = _pct(P, tier, "high52_prox")
    c2 = (v + f + h + (100 - m)) / 4
    composite = P.REAL_COMP.astype(np.float64)
    return composite, c2


def topk_pct_mask(P: Panel, score: np.ndarray, tier: str, top_pct: int = 20) -> np.ndarray:
    """逐月依百分比取前 top_pct%(與 dual_confirm_mask 的 topk() 邏輯一致)。"""
    valid = P.tier_valid[tier]
    ok = valid & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
    kk = np.maximum(1, (ok.sum(1) * top_pct // 100).astype(int))
    return (rk <= kk[:, None]) & ok


def topk_n_mask(P: Panel, score: np.ndarray, tier: str, n_per_month: np.ndarray) -> np.ndarray:
    """逐月依**給定檔數**(可變 N)取分數最高的前 N 檔。N=0 的月份回全 False。"""
    valid = P.tier_valid[tier]
    ok = valid & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
    kk = np.maximum(0, n_per_month.astype(int))
    return (rk <= kk[:, None]) & ok


def random_masks_n(P: Panel, tier: str, n_per_month: np.ndarray, reps: int, rng):
    """換手對齊虛無:每月隨機取 n_per_month[t] 檔(可變 N 版的 _random_masks)。"""
    valid = P.tier_valid[tier]
    nn = np.maximum(0, n_per_month.astype(int))
    for _ in range(reps):
        u = rng.random((P.T, P.S))
        x = np.where(valid, u, np.inf)
        order = np.argsort(x, axis=1, kind="stable")
        rk = np.empty(order.shape, dtype=np.int32)
        np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
        M = (rk <= nn[:, None]) & valid
        yield M


def apply_window(P: Panel, window: str):
    """回布林遮罩(月),window in {'full','oos2010'}。"""
    if window == "full":
        return np.ones(P.T, dtype=bool)
    if window == "oos2010":
        return P.month_s >= "2010-01-01"
    raise ValueError(f"未知 window={window!r}")


def run(tier: str, window: str, reps: int, adv_floor: float) -> None:
    print("\n" + "=" * 100)
    print(f"歸因拆解 · ADV≥{tier} · window={window} · reps={reps}(非預註冊,不對候選下判定)")
    print("=" * 100)
    P = Panel(realbody_floor=adv_floor)
    wmask = apply_window(P, window)

    composite, c2 = composite_and_c2_scores(P, tier)
    M1 = topk_pct_mask(P, composite, tier, 20)
    M2 = topk_pct_mask(P, c2, tier, 20)
    M3 = M1 & M2
    n3 = M3.sum(1).astype(np.int64)
    M4 = topk_n_mask(P, composite, tier, n3)
    M5 = topk_n_mask(P, c2, tier, n3)

    def clip(M):
        Mc = M.copy()
        Mc[~wmask] = False
        return Mc

    arms = {
        "1 綜合分 Top20%(全寬)": clip(M1),
        "2 c2 Top20%(全寬)": clip(M2),
        "3 雙確認=交集(觀測值)": clip(M3),
        "4 綜合分 Top-N(同集中度)": clip(M4),
        "5 c2 Top-N(同集中度)": clip(M5),
    }
    series = {k: evaluate(v, P.RET, P.SLIP) for k, v in arms.items()}

    print(f"\n{'arm':<28}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}{'月均檔數':>10}")
    for k, v in arms.items():
        m = met(series[k])
        avg_n = float(v.sum(1)[wmask & (v.sum(1) > 0)].mean()) if (wmask & (v.sum(1) > 0)).any() else float("nan")
        print(f"{k:<28}{m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}"
              f"{m.get('mdd', np.nan):>9.1f}{m.get('n', 0):>7}{turnover(v)*100:>10.1f}{avg_n:>10.1f}")
    mb = met(P.bench[wmask])
    print(f"{'0050 含息買進持有':<28}{mb.get('cagr', np.nan):>9.2f}{mb.get('sharpe', np.nan):>8.2f}"
          f"{mb.get('mdd', np.nan):>9.1f}{mb.get('n', 0):>7}{0.0:>10.1f}{'':>10}")

    # ---- 配對檢定:arm3 是否顯著贏 arm4 / arm5(同集中度下,交集有沒有多資訊)----
    rng = np.random.default_rng(SEED)
    print(f"\n{'配對比較':<34}{'月數':>6}{'平均月差pp':>12}{'配對t':>8}{'bootstrap 95%CI':>22}")
    for tag, x, y in [("3 − 4(交集 vs 綜合分同N)", "3 雙確認=交集(觀測值)", "4 綜合分 Top-N(同集中度)"),
                      ("3 − 5(交集 vs c2同N)", "3 雙確認=交集(觀測值)", "5 c2 Top-N(同集中度)")]:
        r = paired(series[x], series[y], rng)
        print(f"{tag:<34}{r['n']:>6}{r['mean']:>12.3f}{r['t']:>8.2f}"
              f"{'[' + format(r['boot_lo'], '.3f') + ', ' + format(r['boot_hi'], '.3f') + ']':>22}")

    # ---- arm6:換手對齊隨機虛無(集中度下界)。用 arm3 的逐月 N,同時對照母體 = 綜合分∪c2 有效範圍 ----
    n3w = n3.copy()
    n3w[~wmask] = 0
    obs3 = met(series["3 雙確認=交集(觀測值)"])
    obs4 = met(series["4 綜合分 Top-N(同集中度)"])
    obs5 = met(series["5 c2 Top-N(同集中度)"])
    sharpes = np.empty(reps)
    for i, M in enumerate(random_masks_n(P, tier, n3w, reps, rng)):
        m = met(evaluate(M, P.RET, P.SLIP))
        sharpes[i] = m.get("sharpe", np.nan)
    sharpes = sharpes[np.isfinite(sharpes)]
    print(f"\narm6 隨機同 N({reps} 次,換手對齊):夏普 p50={np.percentile(sharpes,50):.2f}  "
          f"p95={np.percentile(sharpes,95):.2f}  p99={np.percentile(sharpes,99):.2f}")
    for tag, obs in [("arm3(交集)", obs3), ("arm4(綜合分同N)", obs4), ("arm5(c2同N)", obs5)]:
        if "sharpe" not in obs:
            continue
        pctile = float(np.mean(sharpes < obs["sharpe"]) * 100)
        print(f"  {tag} 夏普 {obs['sharpe']:.2f} → 虛無百分位 {pctile:.1f}%")

    # ---- 判讀提示 ----
    print("\n判讀:")
    s3, s4, s5 = obs3.get("sharpe", np.nan), obs4.get("sharpe", np.nan), obs5.get("sharpe", np.nan)
    best45 = max(s4, s5) if np.isfinite(s4) and np.isfinite(s5) else np.nan
    if np.isfinite(s3) and np.isfinite(best45):
        gap = s3 - best45
        print(f"  arm3 夏普 {s3:.2f} vs max(arm4,arm5) {best45:.2f} → 差 {gap:+.2f}")
        if gap <= 0.05:
            print("  → arm3 ≈ max(arm4,arm5):交集贏的主要是集中度,不是訊號互補。")
        else:
            print("  → arm3 顯著優於同集中度單腿:訊號互補可能是真的(仍需配對 t 檢視顯著性)。")


def main() -> int:
    ap = argparse.ArgumentParser(description="歸因拆解:雙確認贏是訊號互補還是集中度")
    ap.add_argument("--tier", default="100萬", choices=["100萬", "2000萬"])
    ap.add_argument("--window", default="full", choices=["full", "oos2010"])
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--adv-floor", type=float, default=None,
                    help="真身面板門檻;預設依 --tier 對應(100萬→1e6,2000萬→2e7)")
    args = ap.parse_args()
    floor = args.adv_floor
    if floor is None:
        floor = 1e6 if args.tier == "100萬" else 2e7
    run(args.tier, args.window, args.reps, floor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
