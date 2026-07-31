# -*- coding: utf-8 -*-
"""gate2b_bootstrap.py — 預註冊 §5-1 的 **paired circular moving-block bootstrap**
的**凍結參考實作**,以及凍結前必須先做的**檢定力探測**。

Codex 第六輪 §1:Gate 2-B 不採用硬性點估計比較,改成預註冊的 paired block bootstrap
—— 以相同月份比較候選與 V0,CAGR / Sharpe 的 95% CI 下界須不低於 V0;
區塊長度、重抽次數、seed **必須現在寫死**。

本檔做兩件事:
  1. `paired_block_bootstrap()` —— 凍結的演算法本體(candidate runner 直接 import 它,
     不得另寫一份);
  2. `main()` —— **檢定力探測**:拿 V0 自己的兩條腿(`∩c2` vs `composite alone`)
     當一組「已知有差異」的對照,量出這個設定下 CI 的寬度。
     目的是在凍結**之前**確認這個 Gate 既不空洞(寬到誰都過不了)
     也不寬鬆(窄到雜訊都能過)。

**這不是 candidate OOS**:兩條腿都是 V0 的切片,此刻不存在任何 candidate。

用法:python scripts/gate2b_bootstrap.py
"""
from __future__ import annotations
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_HERE, _ROOT, os.path.join(_ROOT, "beat_0050", "strategies")):
    sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================================
# 凍結參數(Codex 第六輪 §1 要求「現在寫死」)—— 不得在看過 candidate 之後修改
# ============================================================================
BLOCK_LEN = 12          # 區塊長度(月)。理由見 §5-1:年度級的自我相關與 regime 持續性
N_BOOT = 10_000         # 重抽次數
SEED = 20260731         # 固定 seed(與 dual100_lab.SEED=20260730 刻意不同,兩者不共用)
CI_LOWER_Q = 2.5        # 雙尾 95% CI 的下界百分位
OOS_LO, OOS_HI = "2019-08-01", "2026-03-31"      # 主時鐘(80 月)
RF = 1.0                # 與 high52_lab.RF 相同;此處只為文件完整,實際呼叫 met()


def paired_block_bootstrap(r_cand: np.ndarray, r_v0: np.ndarray, met_fn,
                           block_len: int = BLOCK_LEN, n_boot: int = N_BOOT,
                           seed: int = SEED) -> dict:
    """**凍結演算法**:對 (candidate, V0) 的同月份配對報酬做 circular moving-block bootstrap。

    關鍵是 **paired**:每一次重抽產生**一組**索引序列,**同時**套用到兩條腿。
    兩條腿共用大部分持股 → 共同的市場雜訊在 Δ 裡自然抵銷,
    所以檢定的是「candidate 是否真的比 V0 好」,不是「兩者各自的絕對水準是否可區分」。

    演算法(逐字凍結):
      1. 兩腿先對齊到同一組 T 個月;任一腿為 NaN 的月份**兩腿一起剔除**;
      2. 每次重抽:抽 ceil(T/L) 個起點 s ~ Uniform{0..T-1},
         每個起點取 (s, s+1, …, s+L-1) mod T(**環狀**,不丟尾),串接後**截到剛好 T**;
      3. 同一組索引套用到兩腿 → 各自算 met_fn → Δ = cand − V0;
      4. 回 Δ 的 2.5 / 50 / 97.5 百分位。
    """
    r_cand = np.asarray(r_cand, float)
    r_v0 = np.asarray(r_v0, float)
    if r_cand.shape != r_v0.shape:
        raise ValueError(f"兩腿長度不同:{r_cand.shape} vs {r_v0.shape}")
    ok = np.isfinite(r_cand) & np.isfinite(r_v0)      # 同月份剔除,不得各自丟 NaN
    a, b = r_cand[ok], r_v0[ok]
    T = len(a)
    if T < block_len * 2:
        raise ValueError(f"共同月份僅 {T},不足 2 個區塊({block_len} 月)")

    n_blocks = int(np.ceil(T / block_len))
    rng = np.random.default_rng(seed)
    base = np.arange(block_len)
    d_cagr = np.empty(n_boot)
    d_sharpe = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, T, size=n_blocks)
        idx = ((starts[:, None] + base[None, :]) % T).ravel()[:T]
        ma, mb = met_fn(a[idx]), met_fn(b[idx])
        d_cagr[i] = ma.get("cagr", np.nan) - mb.get("cagr", np.nan)
        d_sharpe[i] = ma.get("sharpe", np.nan) - mb.get("sharpe", np.nan)

    def q(x):
        x = x[np.isfinite(x)]
        return (float(np.percentile(x, CI_LOWER_Q)), float(np.percentile(x, 50)),
                float(np.percentile(x, 100 - CI_LOWER_Q)))

    lo_c, md_c, hi_c = q(d_cagr)
    lo_s, md_s, hi_s = q(d_sharpe)
    m_obs_a, m_obs_b = met_fn(a), met_fn(b)
    return {
        "T": T, "n_blocks": n_blocks,
        "obs_d_cagr": m_obs_a["cagr"] - m_obs_b["cagr"],
        "obs_d_sharpe": m_obs_a["sharpe"] - m_obs_b["sharpe"],
        "ci_cagr": (lo_c, md_c, hi_c), "ci_sharpe": (lo_s, md_s, hi_s),
        "pass_cagr": lo_c >= 0.0, "pass_sharpe": lo_s >= 0.0,
    }


def _report(name: str, res: dict) -> None:
    lo_c, md_c, hi_c = res["ci_cagr"]
    lo_s, md_s, hi_s = res["ci_sharpe"]
    print(f"\n{name}(共同月份 {res['T']},每次抽 {res['n_blocks']} 個 {BLOCK_LEN} 月區塊)")
    print(f"  ΔCAGR   觀測 {res['obs_d_cagr']:+7.2f}pp   "
          f"95% CI [{lo_c:+7.2f}, {hi_c:+7.2f}]   中位 {md_c:+7.2f}   "
          f"下界≥0 → {'✅ 過' if res['pass_cagr'] else '❌ 不過'}")
    print(f"  ΔSharpe 觀測 {res['obs_d_sharpe']:+7.3f}    "
          f"95% CI [{lo_s:+7.3f}, {hi_s:+7.3f}]   中位 {md_s:+7.3f}   "
          f"下界≥0 → {'✅ 過' if res['pass_sharpe'] else '❌ 不過'}")


def main():
    from dual100_lab import TARGET_TIER, ADV_FLOOR
    from high52_lab import Panel, evaluate, met, dual_confirm_mask

    sys.path.insert(0, _HERE)
    from v0_composite_alone_baseline import _topk

    P = Panel(realbody_floor=ADV_FLOOR)
    valid = P.tier_valid[TARGET_TIER]
    months = P.month_s
    sel = (months >= OOS_LO) & (months <= OOS_HI)

    M_dual = dual_confirm_mask(P, TARGET_TIER, top_pct=20, source="real")
    M_alone = _topk(P, valid, P.REAL_COMP.astype(np.float64))
    r_dual = np.where(sel, evaluate(M_dual, P.RET, P.SLIP), np.nan)
    r_alone = np.where(sel, evaluate(M_alone, P.RET, P.SLIP), np.nan)

    print("=" * 92)
    print("Gate 2-B 的 paired block bootstrap —— **凍結參數 + 檢定力探測**")
    print("=" * 92)
    print(f"凍結參數:區塊長度 L = {BLOCK_LEN} 月 / 重抽 B = {N_BOOT:,} 次 / "
          f"seed = {SEED} / CI 下界 = 第 {CI_LOWER_Q} 百分位(雙尾 95%)")
    print(f"主時鐘:{OOS_LO} ~ {OOS_HI}")
    print("\n⚠ 這**不是 candidate OOS** —— 兩條腿都是 V0 的切片,此刻不存在任何 candidate。")
    print("   目的只有一個:在凍結前確認這個 Gate 有沒有可用的鑑別力。")

    # --- 探測 1:V0 vs V0(退化情形,Δ 必須恆為 0,CI 必須是 [0,0])---
    res0 = paired_block_bootstrap(r_dual, r_dual, met, n_boot=1000)
    _report("探測 1  V0 ∩c2  vs  自己(退化檢查,CI 必須恰為 [0, 0])", res0)
    assert abs(res0["ci_cagr"][0]) < 1e-9 and abs(res0["ci_cagr"][2]) < 1e-9, \
        "退化檢查失敗:同一條腿的 Δ 應恆為 0"
    print("  ✅ 退化檢查通過:paired 索引確實同時套用到兩腿")

    # --- 探測 2:∩c2 vs composite alone(V0 的兩條腿,已知有差異)---
    res1 = paired_block_bootstrap(r_dual, r_alone, met)
    _report("探測 2  V0 ∩c2  vs  V0 composite alone(檢定力探測)", res1)

    # --- 探測 3:反向(把較差的那條當 candidate,必須不過)---
    res2 = paired_block_bootstrap(r_alone, r_dual, met)
    _report("探測 3  反向:composite alone 當 candidate(必須不過)", res2)

    print("\n" + "=" * 92)
    print("判讀(寫進預註冊 §5-1):")
    lo_c = res1["ci_cagr"][0]
    print(f"  · V0 的兩條腿相差 {res1['obs_d_cagr']:+.2f}pp CAGR;這個設定下 CI 下界 "
          f"{lo_c:+.2f}pp → {'能' if lo_c >= 0 else '**不能**'}判定為顯著。")
    print("  · 若連『c2 那一腿的貢獻』這種量級的差異都判不出顯著,那 Gate 2-B 對")
    print("    『單一定義修正』(預期效果更小)幾乎不可能通過 —— 這必須在凍結前講清楚,")
    print("    而不是等 6 個 arm 全部 E4 出局才發現門檻是空的。")
    print("=" * 92)


if __name__ == "__main__":
    main()
