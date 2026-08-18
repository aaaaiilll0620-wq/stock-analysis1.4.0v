# -*- coding: utf-8 -*-
"""dual100_top15_lab.py — 「dual100 交集算完後再取前 15 檔」的確認性檢定
================================================================================
預註冊:`docs/預註冊_TOP15濃縮.md`(2026-08-10 凍結)。本腳本只**執行**該文件寫死的
協定,不重新決定門檻。任何要改門檻的念頭,先回去讀
`docs/研究紀律_ResearchDiscipline.md` §2。

待驗對象:`real_composite` Top20% ∩ `c2` Top20% @ADV≥100萬(= 已驗證的 dual100,
`docs/預註冊_雙確認ADV100萬.md`)**算完之後**,再依 `real_composite` 百分位由高到低
取前 `TOP_N=15` 檔。選股規則本身不重測,只測濃縮這個額外動作有沒有把已驗證的風險
報酬特性弄壞。

  H1  前置閘(in-sample):全期夏普 >0050。H1 失敗即結案。
  H2  walk-forward(主假設):與 dual100 H2 同一段 OOS,固定 100萬 層(不重選 ADV 層)。
  H3  濃縮代價量化(次指標,揭露性質,不設通過/否定門檻):TOP15 vs dual100 完整交集
      vs 0050 的 MDD/持股數/換手率/選中股 adv20 三方比較。
  H4  滑價敏感度:0.60% 時夏普仍須 >0.68。
  H5  六時代穩健:≥4 段勝等權母體 且 ≥3 段夏普勝 0050。

用法:
    python beat_0050/strategies/dual100_top15_lab.py --part verify
    python beat_0050/strategies/dual100_top15_lab.py --part h1
    python beat_0050/strategies/dual100_top15_lab.py --part all
================================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))   # high52_lab
sys.path.insert(0, str(PROJ / "beat_0050"))                # honest_backtest
sys.path.insert(0, str(PROJ / "scripts"))                  # lab_paths

from high52_lab import (Panel, evaluate, met, met_vs, sharpe_only, turnover,  # noqa: E402
                        dual_confirm_mask, OUTDIR)
from honest_backtest import Engine, ERAS, SLIPPAGE_RT      # noqa: E402
from lab_paths import resolve_realbody, available_realbody_panels  # noqa: E402

# ---- 預註冊 §0/§2 凍結參數 ----
ADV_FLOOR = 1e6             # 與 dual100 相同,固定 100萬 層(§1 理由 1:不重選 ADV 層)
TOP_PCT = 20                # dual100 交集門檻,不變
TOP_N = 15                  # 本次待驗的濃縮參數,只測這一個值,不掃
TARGET_TIER = "100萬"
BENCH_SHARPE = 0.68
SLIP_GRID = [0.25, 0.40, 0.60, 0.80]
SLIP_PASS = 0.60
WF_MIN_TRAIN = 60
WF_STEP = 12
COV_MIN = 1.0


def dual_confirm_mask_topn(P: Panel, tier: str, top_pct: int = TOP_PCT,
                           top_n: int = TOP_N) -> np.ndarray:
    """dual100 交集(逐字沿用 `high52_lab.dual_confirm_mask`,不重寫)算完後,
    月內再依 `real_composite` 由高到低排序取前 top_n 檔。交集檔數 <top_n 則全留。
    """
    base = dual_confirm_mask(P, tier, top_pct=top_pct, source="real")
    composite = P.REAL_COMP.astype(np.float64)
    x = np.where(base, composite, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
    return base & (rk <= top_n)


def mask_to_holdings(P: Panel, M: np.ndarray) -> dict:
    out = {}
    for t in range(P.T):
        j = np.where(M[t])[0]
        if len(j):
            out[P.month_s[t]] = [str(s) for s in P.stocks[j]]
    return out


def const_slip(P: Panel, value: float) -> np.ndarray:
    return np.full_like(P.RET, value, dtype=P.RET.dtype)


def tier_coverage(P: Panel) -> float:
    valid = P.tier_valid[TARGET_TIER]
    return float(np.isfinite(P.REAL_COMP[valid]).mean()) if valid.any() else 0.0


def net_topn(P: Panel, slip: float | None = None) -> tuple:
    M = dual_confirm_mask_topn(P, TARGET_TIER, top_pct=TOP_PCT, top_n=TOP_N)
    S = P.SLIP if slip is None else const_slip(P, slip)
    return evaluate(M, P.RET, S), M


def net_full(P: Panel, slip: float | None = None) -> tuple:
    """dual100 完整交集(不濃縮),H3 拿來對照用。"""
    M = dual_confirm_mask(P, TARGET_TIER, top_pct=TOP_PCT, source="real")
    S = P.SLIP if slip is None else const_slip(P, slip)
    return evaluate(M, P.RET, S), M


def show(label: str, m: dict, turn: float = np.nan) -> None:
    print(f"{label:<30}{m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}"
          f"{m.get('mdd', np.nan):>9.1f}{m.get('n', 0):>7}"
          f"{turn * 100 if turn == turn else float('nan'):>10.1f}")


# ==============================================================================
def run_verify() -> None:
    print("=" * 92)
    print("面板驗收 — 與 dual100 同一份真身面板 @ ADV≥100萬")
    print("=" * 92)
    path = resolve_realbody(ADV_FLOOR)
    print(f"→ ADV≥{ADV_FLOOR:,.0f} 解析到:{path.name}")
    P = Panel(realbody_floor=ADV_FLOOR)
    print(f"面板 {P.T} 月 × {P.S} 檔")
    cov = tier_coverage(P)
    print(f"{TARGET_TIER} 層真身覆蓋率 {cov:.1%}")
    if cov < COV_MIN:
        raise RuntimeError(f"{TARGET_TIER} 層真身覆蓋率不足 {COV_MIN:.0%},無法往下跑。")
    M15 = dual_confirm_mask_topn(P, TARGET_TIER)
    Mfull = dual_confirm_mask(P, TARGET_TIER, top_pct=TOP_PCT, source="real")
    n15 = M15.sum(1)[M15.sum(1) > 0]
    nfull = Mfull.sum(1)[Mfull.sum(1) > 0]
    print(f"\n完整交集平均持股 {nfull.mean():.1f} 檔(中位 {np.median(nfull):.0f})")
    print(f"TOP15 濃縮後平均持股 {n15.mean():.1f} 檔(中位 {np.median(n15):.0f});"
          f"{(n15 < TOP_N).sum()} 個月交集本身就 <{TOP_N} 檔,濃縮沒有實際發生")
    print("\n✅ 驗收完成。下一步:--part h1(前置閘;H1 失敗即結案)")


# ==============================================================================
def run_h1(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H1  前置閘(in-sample):TOP15 濃縮版")
    print("=" * 92)
    net, M = net_topn(P)
    m = met(net)
    tn = turnover(M)
    print(f"\n{'策略':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show(f"TOP15 濃縮 @{TARGET_TIER}", m, tn)
    show("0050 含息買進持有", met(P.bench), 0.0)

    ok = m.get("sharpe", -9) > BENCH_SHARPE
    print(f"\nH1 全期夏普 {m.get('sharpe', np.nan):.2f} > {BENCH_SHARPE}(0050) → "
          f"{'✅通過,可跑 H2/H3/H4/H5' if ok else '❌未過 —— 依預註冊§3 出口2,結案'}")
    return {"h1": ok, "metrics": m}


# ==============================================================================
def run_h2(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H2  walk-forward(主假設):與 dual100 H2 同一段 OOS,固定 100萬 層")
    print("=" * 92)
    net, _ = net_topn(P)
    print(f"訓練窗 ≥{WF_MIN_TRAIN} 月(與 dual100 H2 一致,本文件不重選 ADV 層,"
          f"直接用固定 100萬 層走同一段時鐘)")

    span = slice(WF_MIN_TRAIN, P.T)
    m_fix, m_bh, ex = met_vs(net[span], P.bench[span])
    if ex:
        print(f"⚠ {ex} 個空手月 —— 已對齊共同月份比較。")
    print(f"\n{'':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show("H2  TOP15 OOS(固定100萬層)", m_fix)
    show(f"  └ 0050(同段 {m_bh.get('n',0)} 月)", m_bh, 0.0)

    h2 = (m_fix.get("sharpe", -9) > m_bh.get("sharpe", 9)) and \
         (m_fix.get("cagr", -9) > m_bh.get("cagr", 9))
    print(f"\nH2 OOS 夏普且 CAGR 勝 0050 → {'✅通過' if h2 else '❌否定'}")
    return {"h2": h2, "oos_metrics": m_fix, "bench_metrics": m_bh}


# ==============================================================================
def run_h3(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H3  濃縮代價量化(次指標,揭露性質,不設通過/否定門檻)")
    print("=" * 92)
    net15, M15 = net_topn(P)
    netfull, Mfull = net_full(P)
    m15, mfull, mbh = met(net15), met(netfull), met(P.bench)

    print(f"\n{'':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show("TOP15 濃縮版", m15, turnover(M15))
    show("dual100 完整交集版", mfull, turnover(Mfull))
    show("0050 含息買進持有", mbh, 0.0)

    n15 = M15.sum(1)[M15.sum(1) > 0]
    nfull = Mfull.sum(1)[Mfull.sum(1) > 0]
    adv15 = np.nanmedian(np.where(M15, P.ADV, np.nan))
    advfull = np.nanmedian(np.where(Mfull, P.ADV, np.nan))
    print(f"\n平均持股:TOP15 {n15.mean():.1f} 檔  完整交集 {nfull.mean():.1f} 檔")
    print(f"選中股 adv20 中位:TOP15 {adv15/1e4:,.0f} 萬/日  完整交集 {advfull/1e4:,.0f} 萬/日")
    mdd_delta = m15.get("mdd", np.nan) - mfull.get("mdd", np.nan)
    print(f"\nMDD 差(TOP15 − 完整交集) = {mdd_delta:+.1f}pp "
          f"({'惡化' if mdd_delta < 0 else '改善'},規格警語預期是惡化)")
    print("H3 是揭露性質,無通過/否定判定。")
    return {"h3_m15": m15, "h3_mfull": mfull, "h3_mdd_delta": float(mdd_delta),
           "h3_adv15": float(adv15), "h3_advfull": float(advfull)}


# ==============================================================================
def run_h4(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H4  滑價敏感度(集中名單單筆佔比更大,預期比 dual100 更敏感)")
    print("=" * 92)
    print(f"\n{'來回滑價%':<12}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'vs 0050':>10}")
    out = {}
    for s in SLIP_GRID:
        m = met(net_topn(P, slip=s)[0])
        out[s] = m
        mark = "✅" if m.get("sharpe", -9) > BENCH_SHARPE else "❌"
        print(f"{s:<12.2f}{m.get('cagr',np.nan):>9.2f}{m.get('sharpe',np.nan):>8.2f}"
              f"{m.get('mdd',np.nan):>9.1f}{mark:>10}")
    xs = np.array(SLIP_GRID)
    ys = np.array([out[s].get("sharpe", np.nan) for s in SLIP_GRID])
    be = np.nan
    for i in range(len(xs) - 1):
        if ys[i] > BENCH_SHARPE >= ys[i + 1]:
            be = xs[i] + (ys[i] - BENCH_SHARPE) / (ys[i] - ys[i + 1]) * (xs[i + 1] - xs[i])
            break
    ok = out[SLIP_PASS].get("sharpe", -9) > BENCH_SHARPE
    print(f"\n損益兩平滑價 ≈ {be:.2f}%")
    print(f"H4 滑價 {SLIP_PASS}% 時夏普 > {BENCH_SHARPE} → {'✅通過' if ok else '❌否定'}")
    return {"h4": ok, "breakeven": float(be), "grid": out}


# ==============================================================================
def run_h5(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H5  六時代穩健")
    print("=" * 92)
    net, M = net_topn(P)
    eng = Engine(adv_floor=ADV_FLOOR)
    ew_net = np.full(P.T, np.nan)
    ewm = eng.run(eng.universe_ew())["monthly"].set_index("as_of")["ret"]
    for t in range(P.T):
        if P.month_s[t] in ewm.index:
            ew_net[t] = ewm.loc[P.month_s[t]]

    print(f"\n{'時代':<18}{'策略CAGR':>10}{'等權母體':>10}{'差pp':>8}"
          f"{'策略夏普':>10}{'0050夏普':>10}{'判定':>12}")
    win_ew = win_bh = 0
    rows = []
    for name, s0, s1 in ERAS:
        sel = (P.month_s >= s0) & (P.month_s <= s1)
        if sel.sum() < 6:
            continue
        ms, me, mb = met(net[sel]), met(ew_net[sel]), met(P.bench[sel])
        a = ms.get("cagr", np.nan) > me.get("cagr", np.nan)
        b = ms.get("sharpe", np.nan) > mb.get("sharpe", np.nan)
        win_ew += bool(a)
        win_bh += bool(b)
        rows.append((name, ms, me, mb, a, b))
        print(f"{name:<18}{ms.get('cagr',np.nan):>10.2f}{me.get('cagr',np.nan):>10.2f}"
              f"{ms.get('cagr',np.nan)-me.get('cagr',np.nan):>8.2f}"
              f"{ms.get('sharpe',np.nan):>10.2f}{mb.get('sharpe',np.nan):>10.2f}"
              f"{('①' + ('✅' if a else '❌') + ' ③' + ('✅' if b else '❌')):>12}")
    ok = win_ew >= 4 and win_bh >= 3
    print(f"\n勝等權母體 {win_ew}/{len(rows)} 段(門檻 ≥4);夏普勝 0050 {win_bh}/{len(rows)} 段(門檻 ≥3)")
    print(f"H5 → {'✅通過' if ok else '❌否定'}")
    return {"h5": ok, "win_ew": win_ew, "win_bh": win_bh}


# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="verify",
                    choices=["verify", "h1", "h2", "h3", "h4", "h5", "all"])
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    if a.part == "verify":
        run_verify()
        return

    t0 = time.time()
    print(f"建面板…(真身面板涵蓋 ADV≥{ADV_FLOOR:,.0f})", flush=True)
    P = Panel(realbody_floor=ADV_FLOOR)
    print(f"面板 {P.T} 月 × {P.S} 檔 ({time.time()-t0:.0f}s)")

    res = {}
    if a.part in ("h1", "all"):
        res.update(run_h1(P))
        if a.part == "all" and not res.get("h1"):
            print("\n" + "=" * 92)
            print("H1 前置閘未過 → 依預註冊§3 出口2,結案。不執行 H2~H5。")
            print("=" * 92)
            return
    if a.part in ("h2", "all"):
        res.update(run_h2(P))
    if a.part in ("h3", "all"):
        res.update(run_h3(P))
    if a.part in ("h4", "all"):
        res.update(run_h4(P))
    if a.part in ("h5", "all"):
        res.update(run_h5(P))

    if a.part == "all":
        print("\n" + "=" * 92)
        print("預註冊判定總表(docs/預註冊_TOP15濃縮.md)")
        print("=" * 92)
        for k, lab in [("h1", "H1  前置閘"), ("h2", "H2  walk-forward(主)"),
                       ("h4", "H4  滑價穩健"), ("h5", "H5  時代穩健")]:
            v = res.get(k)
            print(f"{lab:<26}{'✅通過' if v else '❌否定' if v is not None else '—'}")
        print("H3  濃縮代價量化              揭露性質,無通過/否定(見上方輸出)")
        print("\n結果(不論正負)請寫進 docs/預註冊_TOP15濃縮.md §6。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
