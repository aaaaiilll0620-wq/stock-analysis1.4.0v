# -*- coding: utf-8 -*-
"""dual100_lab.py — 「雙確認 @ ADV≥100萬」的確認性檢定
================================================================================
預註冊:`docs/預註冊_雙確認ADV100萬.md`(2026-07-30 凍結,**早於面板落地**)。
本腳本只**執行**該文件寫死的協定,不重新決定門檻。任何要改門檻的念頭,
先回去讀 `docs/研究紀律_ResearchDiscipline.md` §2。

待驗對象:真身 `real_composite` Top-20% ∩ `c2` Top-20%,母體 ADV≥100萬,等權,
報酬線 `exec_ret.fwd_x`(含息、可執行)。

  H1   前置閘(in-sample):全期夏普 >0050 且基準階梯①選股階 >0。**H1 失敗即結案。**
  H2   walk-forward:把「選哪個 ADV 層」交給協定,量它的 OOS。high52 就是死在這關。
  H2b  固定 100萬 層的同段 OOS(拆解用)
  H3   虛無對照:①對齊 footprint 隨機 ②報酬置換 ③配置置換 + 解析式 DSR
  H4   滑價敏感度(低 ADV 池的主要威脅):0.60% 時夏普仍須 >0.68
  H5   六時代穩健:≥4 段勝等權母體 且 ≥3 段夏普勝 0050

用法:
    python beat_0050/strategies/dual100_lab.py --part verify   # 面板驗收(先跑這個)
    python beat_0050/strategies/dual100_lab.py --part h1       # 前置閘
    python beat_0050/strategies/dual100_lab.py --part h2
    python beat_0050/strategies/dual100_lab.py --part h3 --reps 500
    python beat_0050/strategies/dual100_lab.py --part h4
    python beat_0050/strategies/dual100_lab.py --part h5
    python beat_0050/strategies/dual100_lab.py --part all
================================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from math import erf, log, sqrt
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
                        paired, dual_confirm_mask, ADV_TIERS, FEE_RT, OUTDIR)
from honest_backtest import Engine, ERAS, SLIPPAGE_RT      # noqa: E402
from lab_paths import resolve_realbody, available_realbody_panels  # noqa: E402

# ---- 預註冊 §0/§3 凍結參數 ----
ADV_FLOOR = 1e6            # 待驗層
TOP_PCT = 20               # 不掃
RET_COL = "fwd_x"
SEED = 20260730
WF_MIN_TRAIN = 60          # 月;協定沿用 high52_lab.run_h1
WF_STEP = 12
BENCH_SHARPE = 0.68        # 0050 含息買進持有(全期);H1/H4 的門檻
SLIP_GRID = [0.25, 0.40, 0.60, 0.80]
SLIP_PASS = 0.60           # H4 門檻
# 真身層的搜尋空間(預註冊 §3:「無門檻」層無真身分數,排除)
TIER_SPACE = ["2000萬", "500萬", "100萬"]
TARGET_TIER = "100萬"
# 研究結論路徑的覆蓋率門檻 = **1.0(零靜默損失)**,與 build_realbody_scores 的預設一致
# (Codex 第三輪第 1 點:會產出研究結論的入口都該零缺,99% 只保留給顯式探索)。
# 三層實測皆 100%,故 1.0 不會擋掉現行驗證。要在已知合法缺口的探索面板上跑,
# 顯式改此值並在預註冊 §7 標記為探索性結果。
COV_MIN = float(__import__("os").environ.get("DUAL100_COV_MIN", "1.0"))


# ==============================================================================
# 工具
# ==============================================================================
def mask_to_holdings(P: Panel, M: np.ndarray) -> dict:
    """遮罩 → {as_of: [stock_id]},餵給 honest_backtest.Engine(第二條路徑)。"""
    out = {}
    for t in range(P.T):
        j = np.where(M[t])[0]
        if len(j):
            out[P.month_s[t]] = [str(s) for s in P.stocks[j]]
    return out


def const_slip(P: Panel, value: float) -> np.ndarray:
    """常數滑價面板 —— 讓矩陣路徑與 Engine 的成本模型完全一致,才對得起帳。"""
    return np.full_like(P.RET, value, dtype=P.RET.dtype)


def tier_coverage(P: Panel, tier: str) -> float:
    valid = P.tier_valid[tier]
    return float(np.isfinite(P.REAL_COMP[valid]).mean()) if valid.any() else 0.0


def testable_tiers(P: Panel) -> list:
    """實際有真身覆蓋率的層。預註冊 §3 要求:被排除的層必須印出來,不得靜默跳過。"""
    ok = []
    print(f"\n{'ADV 層':<10}{'真身覆蓋率':>12}{'納入':>8}")
    for tier in TIER_SPACE:
        cov = tier_coverage(P, tier)
        good = cov >= COV_MIN
        print(f"{tier:<10}{cov:>11.1%}{'✅' if good else '❌排除':>8}")
        if good:
            ok.append(tier)
    if TARGET_TIER not in ok:
        raise RuntimeError(
            f"待驗層 {TARGET_TIER} 的真身覆蓋率不足 —— 面板還沒建好或建到一半。\n"
            f"現有面板:{ {f'{k:,.0f}': v.name for k, v in available_realbody_panels().items()} }\n"
            f"請確認 build_realbody_scores --adv-floor {ADV_FLOOR:.0f} 已完成。")
    if len(ok) < len(TIER_SPACE):
        print(f"⚠ 搜尋空間由 {len(TIER_SPACE)} 縮為 {len(ok)} —— 須記入預註冊 §7。")
    return ok


def tier_net(P: Panel, tier: str, slip: float | None = None, canonical: bool = False) -> tuple:
    """(月度淨報酬%, 遮罩)。slip=None 用面板實測 tick_slip;給數值則用常數。

    canonical=False(預設)與抽取 --canonical 開關前逐位元相同(P0-U1 §9)。
    canonical=True:套用 docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md 的
    共同排名母體(A/B 同分母),唯一自變項,其餘門檻/流程完全不變。
    """
    M = dual_confirm_mask(P, tier, top_pct=TOP_PCT, source="real", canonical=canonical)
    S = P.SLIP if slip is None else const_slip(P, slip)
    return evaluate(M, P.RET, S), M


def show(label: str, m: dict, turn: float = np.nan) -> None:
    print(f"{label:<30}{m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}"
          f"{m.get('mdd', np.nan):>9.1f}{m.get('n', 0):>7}"
          f"{turn * 100 if turn == turn else float('nan'):>10.1f}")


# ==============================================================================
# verify — 面板驗收(預註冊 §6-2)
# ==============================================================================
def run_verify() -> None:
    print("=" * 92)
    print("面板驗收 — 真身分數 @ ADV≥100萬")
    print("=" * 92)
    panels = available_realbody_panels()
    print("現有真身面板:")
    for f, p in sorted(panels.items()):
        mb = p.stat().st_size / 1e6
        print(f"  ADV≥{f:>12,.0f}  {p.name:<40}{mb:>8.1f} MB")
    path = resolve_realbody(ADV_FLOOR)
    print(f"\n→ ADV≥{ADV_FLOOR:,.0f} 解析到:{path.name}")

    rb = pd.read_parquet(path)
    print(f"\n列數 {len(rb):,}   檔數 {rb['stock_id'].nunique():,}   "
          f"月數 {rb['as_of'].nunique()}   區間 {rb['as_of'].min()} ~ {rb['as_of'].max()}")
    rc = rb["real_composite"]
    print(f"real_composite: 中位 {rc.median():.1f}  範圍 {rc.min():.1f}~{rc.max():.1f}  "
          f"缺值 {rc.isna().mean():.2%}")
    print(f"評級分布: {rb['rating'].value_counts().to_dict()}")

    print("\n建面板並逐層量真身覆蓋率…")
    P = Panel(realbody_floor=ADV_FLOOR)
    print(f"面板 {P.T} 月 × {P.S} 檔")
    testable_tiers(P)
    n_target = P.tier_valid[TARGET_TIER].sum()
    print(f"\n待驗層 {TARGET_TIER} 母體 {n_target:,} stock-months")
    print("\n✅ 驗收完成。下一步:--part h1(前置閘;H1 失敗即結案)")


# ==============================================================================
# H1 — 前置閘 + 兩路徑對帳(預註冊 §2 H1、§3 對帳)
# ==============================================================================
def run_h1(P: Panel, canonical: bool = False) -> dict:
    print("\n" + "=" * 92)
    print(f"H1  前置閘(in-sample):真身雙確認 @ADV≥100萬{' [P0-U1 canonical]' if canonical else ''}")
    print("=" * 92)
    net, M = tier_net(P, TARGET_TIER, canonical=canonical)
    m = met(net)
    tn = turnover(M)
    print(f"\n{'策略':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show(f"真身雙確認 @{TARGET_TIER}", m, tn)
    mb = met(P.bench)
    show("0050 含息買進持有", mb, 0.0)

    n_avg = M.sum(1)[M.sum(1) > 0].mean()
    adv_sel = np.nanmedian(np.where(M, P.ADV, np.nan))
    print(f"\n平均持股 {n_avg:.1f} 檔;選中股 adv20 中位 {adv_sel/1e4:,.0f} 萬/日")
    print("  (替身時代:48 檔、11,652 萬/日。若這裡顯著更低,H4 的安全邊際要重估 —— 預註冊 §5-4)")

    # ---- 第二條路徑:honest_backtest.Engine(持股字典)+ 基準階梯三階 ----
    print("\n建 Engine(第二條獨立路徑)…", flush=True)
    eng = Engine(adv_floor=ADV_FLOOR)
    holdings = mask_to_holdings(P, M)
    L = eng.report_ladder(holdings, f"真身雙確認 @{TARGET_TIER}", reps=50)

    # ---- 逐月對帳:成本模型對齊(常數滑價)後,兩路徑必須一致 ----
    print("\n" + "-" * 92)
    print("兩路徑對帳(矩陣 vs Engine;成本模型對齊為常數滑價 "
          f"{SLIPPAGE_RT}%)")
    print("-" * 92)
    net_c, _ = tier_net(P, TARGET_TIER, slip=SLIPPAGE_RT, canonical=canonical)
    em = eng.run(holdings)["monthly"]
    a = pd.Series({P.month_s[t]: net_c[t] for t in range(P.T) if np.isfinite(net_c[t])})
    b = pd.Series(em.set_index("as_of")["ret"])
    common = a.index.intersection(b.index)
    d = (a[common] - b[common]).abs()
    print(f"共同月份 {len(common)}   最大差 {d.max():.4f} pp   中位差 {d.median():.4f} pp")
    recon = bool(d.max() < 0.01)
    print(f"對帳門檻 <0.01pp → {'✅一致' if recon else '❌不一致 —— 視為 bug,先查清再往下跑'}")
    if not recon:
        print(d.nlargest(5).to_string())

    s, ew = L["策略"], L["等權母體"]
    pass_sharpe = s["夏普"] > BENCH_SHARPE
    pass_pick = s["CAGR%"] > ew["CAGR%"]
    ok = pass_sharpe and pass_pick and recon
    print(f"\nH1-a 全期夏普 {s['夏普']:.2f} > {BENCH_SHARPE}(0050)  → {'✅' if pass_sharpe else '❌'}")
    print(f"H1-b ①選股階 {s['CAGR%']-ew['CAGR%']:+.2f} pp/年 > 0        → {'✅' if pass_pick else '❌'}")
    print(f"H1-c 兩路徑對帳                                → {'✅' if recon else '❌'}")
    print(f"\nH1 前置閘 → {'✅通過,可跑 H2~H5' if ok else '❌未過 —— 依預註冊 §4 出口,結案,不跑 H2~H5'}")
    return {"h1": ok, "metrics": m, "ladder": L, "recon_max": float(d.max())}


# ==============================================================================
# H2 / H2b — walk-forward(主假設)
# ==============================================================================
def run_h2(P: Panel, canonical: bool = False) -> dict:
    print("\n" + "=" * 92)
    print(f"H2  walk-forward:把「選哪個 ADV 層」交給協定(high52 就是死在這關)"
          f"{' [P0-U1 canonical]' if canonical else ''}")
    print("=" * 92)
    tiers = testable_tiers(P)
    NET = np.vstack([tier_net(P, t, canonical=canonical)[0] for t in tiers])
    print(f"\n候選 {len(tiers)} 層 × {P.T} 月;訓練窗 ≥{WF_MIN_TRAIN} 月,每 {WF_STEP} 月重選")

    oos = np.full(P.T, np.nan)
    picks = []
    t = WF_MIN_TRAIN
    while t < P.T:
        end = min(t + WF_STEP, P.T)
        sh = np.array([sharpe_only(NET[i, :t]) for i in range(len(tiers))])
        if np.all(~np.isfinite(sh)):
            t = end
            continue
        i = int(np.nanargmax(sh))
        oos[t:end] = NET[i, t:end]
        picks.append({"from": P.month_s[t][:7], "to": P.month_s[end - 1][:7],
                      "tier": tiers[i], "train_sharpe": float(sh[i])})
        t = end

    print(f"\n{'重選期間':<20}{'選中的層':<12}{'訓練夏普':>10}")
    for p in picks:
        print(f"{p['from']}~{p['to']:<12}{p['tier']:<12}{p['train_sharpe']:>10.2f}")
    n_target = sum(1 for p in picks if p["tier"] == TARGET_TIER)

    span = slice(WF_MIN_TRAIN, P.T)
    fixed = NET[tiers.index(TARGET_TIER)]
    # 硬性同時鐘:協定空手月(訓練窗內無合格層)與策略腿一起排除,基準也只取相同月份
    # (與 high52_lab.run_h1 一致,Codex 第二輪第 2 點)。ex=0 時等於全期基準。
    m_oos, m_bh_a, ex_a = met_vs(oos[span], P.bench[span])
    m_fix, m_bh_b, ex_b = met_vs(fixed[span], P.bench[span])

    print(f"\nOOS 期間 {P.month_s[WF_MIN_TRAIN]} ~ {P.month_s[-1]}({m_oos.get('n',0)} 月,"
          f"{len(picks)} 次重選;選中 {TARGET_TIER} 共 {n_target}/{len(picks)} 次)")
    if ex_a:
        print(f"⚠ H2 協定有 {ex_a} 個空手月 —— 已對齊共同月份比較。")
    if ex_b:
        print(f"⚠ H2b 固定層有 {ex_b} 個空手月 —— 同上。")
    print(f"\n{'':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show("H2  協定 walk-forward", m_oos)
    show(f"  └ 0050(同 H2 {m_bh_a.get('n',0)} 月)", m_bh_a, 0.0)
    show(f"H2b 固定 {TARGET_TIER} 層", m_fix)
    show(f"  └ 0050(同 H2b {m_bh_b.get('n',0)} 月)", m_bh_b, 0.0)

    h2 = (m_oos.get("sharpe", -9) > m_bh_a.get("sharpe", 9)) and \
         (m_oos.get("cagr", -9) > m_bh_a.get("cagr", 9))
    h2b = (m_fix.get("sharpe", -9) > m_bh_b.get("sharpe", 9)) and \
          (m_fix.get("cagr", -9) > m_bh_b.get("cagr", 9))
    print(f"\nH2  協定 OOS 夏普且 CAGR 勝 0050   → {'✅通過' if h2 else '❌否定'}")
    print(f"H2b 固定層 OOS 夏普且 CAGR 勝 0050 → {'✅通過' if h2b else '❌否定'}")
    if not h2 and h2b:
        print("\n→ 預註冊 §4 出口 2:「池的選擇有效,但無法即時複製」。"
              "不採用動態選池;要主張固定池須另行預註冊前瞻驗證。**不得直接當通過。**")
    if not h2 and not h2b:
        print("\n→ 預註冊 §4 出口 3:與 high52 同命。記錄否定結果、收工。"
              "不得改門檻、不得換母體、不得換報酬線、不得追加 arm。")
    return {"h2": h2, "h2b": h2b, "picks": picks, "oos": oos}


# ==============================================================================
# H3 — 虛無對照(三組)+ DSR
# ==============================================================================
def run_h3(P: Panel, reps: int = 500, canonical: bool = False) -> dict:
    print("\n" + "=" * 92)
    print(f"H3  虛無對照(reps={reps}){' [P0-U1 canonical]' if canonical else ''}")
    print("=" * 92)
    rng = np.random.default_rng(SEED)
    net, M = tier_net(P, TARGET_TIER, canonical=canonical)
    obs = met(net)
    print(f"觀測:真身雙確認 @{TARGET_TIER}  CAGR {obs['cagr']:.2f}%  夏普 {obs['sharpe']:.2f}")

    # ---- H3-1 對齊 footprint 的隨機(由 Engine.ladder 提供,持股數與換手率都對齊) ----
    print("\n[H3-1] 對齊 footprint 的隨機組合…", flush=True)
    eng = Engine(adv_floor=ADV_FLOOR)
    L = eng.ladder(mask_to_holdings(P, M), reps=min(reps, 200))
    p1 = L["對齊隨機"]["p_null"]
    ok1 = p1 < 0.01
    print(f"  隨機中位夏普 {L['對齊隨機']['夏普']:.2f}  p95 {L['對齊隨機']['null_p95']:.2f}  "
          f"策略 {L['策略']['夏普']:.2f}  → 虛無 p={p1:.3f}  {'✅' if ok1 else '❌'}(門檻 <0.01)")

    # ---- H3-2 報酬置換(保留真實選股 → 換手/滑價結構不變,只打斷報酬對應) ----
    print("\n[H3-2] 報酬逐月置換…", flush=True)
    valid = P.tier_valid[TARGET_TIER]
    rng2 = np.random.default_rng(SEED + 1)
    sb = np.empty(reps)
    t0 = time.time()
    for i in range(reps):
        RP = P.RET.copy()
        for t in range(P.T):
            j = np.where(valid[t])[0]
            if len(j) > 1:
                RP[t, j] = P.RET[t, rng2.permutation(j)]
        sb[i] = met(evaluate(M, RP, P.SLIP)).get("sharpe", np.nan)
        if i % 100 == 0:
            print(f"  {i}/{reps} ({time.time()-t0:.0f}s)", flush=True)
    sb = sb[np.isfinite(sb)]
    p2 = float(np.mean(sb >= obs["sharpe"]))
    ok2 = p2 < 0.01
    print(f"  置換夏普 p50 {np.percentile(sb,50):.2f}  p99 {np.percentile(sb,99):.2f}  "
          f"→ p={p2:.4f}  {'✅' if ok2 else '❌'}(門檻 <0.01)")

    # ---- H3-3 配置置換(對宣告的搜尋空間)+ 解析式 DSR ----
    print("\n[H3-3] 配置置換:對宣告的 ADV 層搜尋空間取最大夏普的虛無分布…", flush=True)
    tiers = testable_tiers(P)
    masks = {t: dual_confirm_mask(P, t, top_pct=TOP_PCT, source="real", canonical=canonical)
             for t in tiers}
    sh_obs = np.array([met(evaluate(masks[t], P.RET, P.SLIP)).get("sharpe", np.nan) for t in tiers])
    rng3 = np.random.default_rng(SEED + 2)
    nrep = max(50, reps // 5)
    maxes = np.empty(nrep)
    t0 = time.time()
    any_valid = P.HAS_RET
    for r in range(nrep):
        RP = P.RET.copy()
        for t in range(P.T):
            j = np.where(any_valid[t])[0]
            if len(j) > 1:
                RP[t, j] = P.RET[t, rng3.permutation(j)]
        maxes[r] = np.nanmax([met(evaluate(masks[t], RP, P.SLIP)).get("sharpe", np.nan)
                              for t in tiers])
        if r % 20 == 0:
            print(f"  {r}/{nrep} ({time.time()-t0:.0f}s)", flush=True)
    p95 = float(np.percentile(maxes, 95))
    i_t = tiers.index(TARGET_TIER)
    ok_perm = bool(sh_obs[i_t] > p95)
    print(f"  置換 max-夏普:p50 {np.percentile(maxes,50):.3f}  p95 {p95:.3f}  "
          f"觀測 {sh_obs[i_t]:.3f} → {'✅' if ok_perm else '❌'}")

    # 解析式 DSR(Bailey & López de Prado 2014);N = 宣告的 arm 數
    N = int(np.isfinite(sh_obs).sum())
    var_sh = float(np.nanvar(sh_obs, ddof=1)) if N > 1 else 0.0
    gamma, e = 0.5772156649, np.e
    z = sqrt(2 * log(N)) if N > 1 else 0.0
    exp_max = sqrt(var_sh) * ((1 - gamma) * (z if z else 1e-9) +
                              gamma * (sqrt(2 * log(N / e)) if N > e else 0.0))
    rets = net[np.isfinite(net)] / 100.0
    nobs = len(rets)
    sr_m = rets.mean() / rets.std(ddof=1)
    sk = float(pd.Series(rets).skew())
    ku = float(pd.Series(rets).kurtosis()) + 3.0
    sr0 = exp_max / np.sqrt(12)
    denom = sqrt(max(1 - sk * sr_m + (ku - 1) / 4 * sr_m ** 2, 1e-9))
    zstat = (sr_m - sr0) * sqrt(nobs - 1) / denom
    dsr = 0.5 * (1 + erf(zstat / sqrt(2)))
    ok_dsr = (1 - dsr) < 0.05
    print(f"  DSR:N={N} trials, Var(SR)={var_sh:.4f}, E[max SR]年化≈{exp_max:.3f}, "
          f"偏態 {sk:+.2f}, 峰態 {ku:.2f}")
    print(f"       DSR={dsr:.4f} → p={1-dsr:.4f}  {'✅' if ok_dsr else '❌'}(門檻 <0.05)")
    print("  ⚠ 預註冊 §3 已揭露:雙確認規則本身是先前工作的產物,N=3 **低估**真實多重比較。"
          "本項只主張「在宣告空間內未見選擇性偏誤」。")

    ok3 = ok_perm and ok_dsr
    ok = ok1 and ok2 and ok3
    print(f"\nH3 三組虛無(全須通過)→ {'✅通過' if ok else '❌否定'}")
    np.savez(OUTDIR / "dual100_h3.npz", sb=sb, maxes=maxes, sh_obs=sh_obs,
             tiers=np.array(tiers))
    return {"h3": ok, "h3_1": ok1, "h3_2": ok2, "h3_3": ok3, "p1": p1, "p2": p2,
            "dsr_p": 1 - dsr}


# ==============================================================================
# H4 — 滑價敏感度
# ==============================================================================
def run_h4(P: Panel, canonical: bool = False) -> dict:
    print("\n" + "=" * 92)
    print(f"H4  滑價敏感度(低 ADV 池的主要威脅){' [P0-U1 canonical]' if canonical else ''}")
    print("=" * 92)
    print(f"\n{'來回滑價%':<12}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'vs 0050':>10}")
    out = {}
    for s in SLIP_GRID:
        m = met(tier_net(P, TARGET_TIER, slip=s, canonical=canonical)[0])
        out[s] = m
        mark = "✅" if m.get("sharpe", -9) > BENCH_SHARPE else "❌"
        print(f"{s:<12.2f}{m.get('cagr',np.nan):>9.2f}{m.get('sharpe',np.nan):>8.2f}"
              f"{m.get('mdd',np.nan):>9.1f}{mark:>10}")
    # 損益兩平:夏普跌到 0050 的滑價值(線性內插)
    xs = np.array(SLIP_GRID)
    ys = np.array([out[s].get("sharpe", np.nan) for s in SLIP_GRID])
    be = np.nan
    for i in range(len(xs) - 1):
        if ys[i] > BENCH_SHARPE >= ys[i + 1]:
            be = xs[i] + (ys[i] - BENCH_SHARPE) / (ys[i] - ys[i + 1]) * (xs[i + 1] - xs[i])
            break
    ok = out[SLIP_PASS].get("sharpe", -9) > BENCH_SHARPE
    print(f"\n損益兩平滑價 ≈ {be:.2f}%(替身時代 0.70%)")
    print(f"H4 滑價 {SLIP_PASS}% 時夏普 > {BENCH_SHARPE} → {'✅通過' if ok else '❌否定'}")
    print("  ⚠ 零股撮合的溢折價無歷史資料可回測(預註冊 §5-3);本項是代理,不是證明。")
    return {"h4": ok, "breakeven": float(be), "grid": out}


# ==============================================================================
# H5 — 六時代穩健
# ==============================================================================
def run_h5(P: Panel, canonical: bool = False) -> dict:
    print("\n" + "=" * 92)
    print(f"H5  六時代穩健{' [P0-U1 canonical]' if canonical else ''}")
    print("=" * 92)
    net, M = tier_net(P, TARGET_TIER, canonical=canonical)
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


def _announce_cov_gate() -> None:
    """把生效的覆蓋率門檻印進 run log(= provenance)。<1.0 一定是被 DUAL100_COV_MIN 降過,
    必印醒目橫幅提醒:這是探索模式,結論不可與預註冊假設並列,須記入 §7(Codex 第四輪第 1 點)。"""
    if abs(COV_MIN - 1.0) < 1e-12:
        print(f"[provenance] 真身覆蓋率門檻 COV_MIN = {COV_MIN}(零靜默損失,預設)")
    else:
        print("=" * 92)
        print(f"⚠⚠ 探索模式:COV_MIN 已由環境變數 DUAL100_COV_MIN 降為 {COV_MIN}(<1.0)。")
        print("   本次所有判定都在**非完整母體**上產出 —— 不得與預註冊假設並列,")
        print("   必須在 docs/預註冊_雙確認ADV100萬.md §7 明確標記為探索性結果。")
        print("=" * 92)


# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="verify",
                    choices=["verify", "h1", "h2", "h3", "h4", "h5", "all"])
    ap.add_argument("--reps", type=int, default=500)
    ap.add_argument("--canonical", action="store_true",
                    help="P0-U1(docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md):"
                         "A/B 百分位改用共同排名母體 C_t,唯一自變項。預設關閉"
                         "(=現行 frozen baseline,逐位元不變,§9)。")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    _announce_cov_gate()
    if a.canonical:
        print("=" * 92)
        print("⚠⚠ P0-U1 canonical universe 模式已開啟 —— 這不是 frozen baseline。")
        print("   A(real_composite)與 B(c2 四腳)百分位改在共同母體 C_t 內計算,")
        print("   其餘門檻/流程完全不變(docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md)。")
        print("=" * 92)

    if a.part == "verify":
        run_verify()
        return

    t0 = time.time()
    print(f"建面板…(報酬線 {RET_COL},真身面板涵蓋 ADV≥{ADV_FLOOR:,.0f})", flush=True)
    P = Panel(realbody_floor=ADV_FLOOR)
    print(f"面板 {P.T} 月 × {P.S} 檔 ({time.time()-t0:.0f}s)")

    res = {}
    if a.part in ("h1", "all"):
        res.update(run_h1(P, canonical=a.canonical))
        if a.part == "all" and not res.get("h1"):
            print("\n" + "=" * 92)
            print("H1 前置閘未過 → 依預註冊 §4,結案。不執行 H2~H5。")
            print("=" * 92)
            return
    if a.part in ("h2", "all"):
        res.update(run_h2(P, canonical=a.canonical))
    if a.part in ("h3", "all"):
        res.update(run_h3(P, a.reps, canonical=a.canonical))
    if a.part in ("h4", "all"):
        res.update(run_h4(P, canonical=a.canonical))
    if a.part in ("h5", "all"):
        res.update(run_h5(P, canonical=a.canonical))

    if a.part == "all":
        print("\n" + "=" * 92)
        print("預註冊判定總表")
        print("=" * 92)
        for k, lab in [("h1", "H1  前置閘"), ("h2", "H2  walk-forward(主)"),
                       ("h2b", "H2b 固定層 OOS"), ("h3", "H3  虛無對照"),
                       ("h4", "H4  滑價穩健"), ("h5", "H5  時代穩健")]:
            v = res.get(k)
            print(f"{lab:<26}{'✅通過' if v else '❌否定' if v is not None else '—'}")
        print("\n結果(不論正負)請寫進 docs/預註冊_雙確認ADV100萬.md §7 與 docs/開發日誌_DevLog.md。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
