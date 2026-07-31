# -*- coding: utf-8 -*-
"""v0_composite_alone_baseline.py — 把 V0 的 **`composite alone`**(只用
`real_composite` Top-20%,**不與 c2 交集**)在各區間的 CAGR / Sharpe / MDD
固定成**單一精確數字**,供預註冊 §5 **Gate 2-A** 的相對基準使用。

**這不是「執行新的 OOS」**,理由與 `v0_oos_window_baseline.py` 完全相同:
  1. 量的對象是 **V0 baseline 的一條腿**,不是任何 candidate arm;
  2. 此刻**不存在任何 candidate** —— 不可能「看結果挑 arm」;
  3. Codex 第五輪 §2 明確要求「Gate 2-A 基準現在就補算」。門檻必須在看到
     candidate 數字**之前**凍結。

與 `v0_oos_window_baseline.py`(= Gate 2-B 的 `composite ∩ c2` 基準)**唯一的差別**
是遮罩少了 c2 那一腿。母體、top_pct、成本、報酬線、時鐘、指標函數全部相同:
  母體 `listed_ok & adv20≥1e6` / Top-20% / 等權 / `exec_ret.fwd_x` /
  手續費 0.47% + 面板實測 `tick_slip`。

**自檢(硬性)**:本檔自己算的 `topk()` 必須與凍結的
`high52_lab.dual_confirm_mask()` 逐格相同(把 c2 腿加回去之後),不同即 raise。
這保證「少一條腿」是唯一的差別,不是另一套實作。

用法:python scripts/v0_composite_alone_baseline.py
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

# ⚠ 2026-07-31 Codex 第六輪 §3:OOS 主時鐘改成 2019-08 ~ 2026-03(80 月)。
#    87 月版只作 robustness 描述,不得作為判定依據。
WINDOWS = [
    ("Train      2005-01~2014-12", "2005-01-01", "2014-12-31"),
    ("Validation 2015-01~2018-12", "2015-01-01", "2018-12-31"),
    ("**OOS(主)** 2019-08~2026-03", "2019-08-01", "2026-03-31"),
    ("OOS(robust) 2019-01~2026-03", "2019-01-01", "2026-03-31"),
    ("全期(對照)  2005-01~2026-03", "2005-01-01", "2026-03-31"),
]
OOS_ERAS = [
    ("19-21(截短) 2019-08~2021-12", "2019-08-01", "2021-12-31"),
    ("2022        2022-01~2022-12", "2022-01-01", "2022-12-31"),
    ("23-26       2023-01~2026-03", "2023-01-01", "2026-03-31"),
]
PRIMARY = "**OOS(主)** 2019-08~2026-03"
TOP_PCT = 20


def _pct(P, valid, name):
    """層內百分位 —— 與 high52_lab.dual_confirm_mask 內的 pct() 逐字相同。"""
    v = P.F[name]
    ok = valid & np.isfinite(v)
    x = np.where(ok, v, -np.inf).astype(np.float64)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.float64)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.float64)[None, :], axis=1)
    nv = ok.sum(1).astype(float)[:, None]
    return np.where(ok, 100.0 * (1.0 - (rk - 1) / np.maximum(nv, 1)), np.nan)


def _topk(P, valid, score):
    """Top-20% 遮罩 —— 與 high52_lab.dual_confirm_mask 內的 topk() 逐字相同。"""
    ok = valid & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rk = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
    kk = np.maximum(1, (ok.sum(1) * TOP_PCT // 100).astype(int))
    return (rk <= kk[:, None]) & ok


def main():
    from dual100_lab import TARGET_TIER, ADV_FLOOR
    from high52_lab import Panel, evaluate, met, turnover, dual_confirm_mask

    P = Panel(realbody_floor=ADV_FLOOR)
    valid = P.tier_valid[TARGET_TIER]
    months = P.month_s

    comp = P.REAL_COMP.astype(np.float64)
    M_comp = _topk(P, valid, comp)

    # ---- 自檢:把 c2 腿加回去必須等於凍結的 dual_confirm_mask ----
    f, v, m = _pct(P, valid, "revenue_yoy"), _pct(P, valid, "value_ind"), _pct(P, valid, "momentum")
    c2 = (v + f + _pct(P, valid, "high52_prox") + (100 - m)) / 4
    M_dual_mine = M_comp & _topk(P, valid, c2)
    M_dual_frozen = dual_confirm_mask(P, TARGET_TIER, top_pct=TOP_PCT, source="real")
    if not np.array_equal(M_dual_mine, M_dual_frozen):
        raise SystemExit(
            f"自檢失敗:本檔的 topk 與 high52_lab.dual_confirm_mask 不同 "
            f"({int((M_dual_mine ^ M_dual_frozen).sum())} 格不同)。"
            "不得把不同實作的結果當成 V0 基準。")
    print("✅ 自檢:加回 c2 腿後與凍結的 dual_confirm_mask **逐格相同** "
          f"({M_comp.shape[0]}×{M_comp.shape[1]} 格)")

    ret_comp = evaluate(M_comp, P.RET, P.SLIP)
    ret_dual = evaluate(M_dual_frozen, P.RET, P.SLIP)

    print(f"\n面板:{P.realbody_path.name}   {len(months)} 月   {months[0]} ~ {months[-1]}")
    print("規則:real_composite Top-20% @ADV≥100萬,等權,exec_ret.fwd_x,"
          "成本 0.47%+面板實測滑價(**不含 c2 腿**)")
    print("\n⚠ 這是 **V0 baseline 的描述性切片**,不是任何 candidate 的 OOS 結果。\n")

    print(f"{'區間':<30}{'月數':>6}{'CAGR%':>9}{'Sharpe':>9}{'MDD%':>9}{'換手%':>9}{'持股':>7}")
    out = {}
    for label, lo, hi in WINDOWS + OOS_ERAS:
        sel = (months >= lo) & (months <= hi)
        mm = met(np.where(sel, ret_comp, np.nan))
        t = turnover(M_comp[sel])
        n_hold = float(M_comp[sel].sum(1).mean())
        out[label] = mm
        print(f"{label:<30}{mm.get('n', 0):>6}{mm.get('cagr', np.nan):>9.2f}"
              f"{mm.get('sharpe', np.nan):>9.2f}{mm.get('mdd', np.nan):>9.2f}"
              f"{t*100 if t == t else np.nan:>9.1f}{n_hold:>7.0f}")

    print(f"\n{'(對照)composite ∩ c2(主時鐘)':<30}", end="")
    sel = (months >= "2019-08-01") & (months <= "2026-03-31")
    md = met(np.where(sel, ret_dual, np.nan))
    print(f"{md.get('n', 0):>6}{md.get('cagr', np.nan):>9.2f}{md.get('sharpe', np.nan):>9.2f}"
          f"{md.get('mdd', np.nan):>9.2f}{turnover(M_dual_frozen[sel])*100:>9.1f}"
          f"{float(M_dual_frozen[sel].sum(1).mean()):>7.0f}   ← Gate 2-B 基準(§1-1)")

    oos = out[PRIMARY]
    print("\n" + "=" * 84)
    print("→ 預註冊 §5 **Gate 2-A** 的基準(**凍結用,單一精確數字**):")
    print(f"   V0 `composite alone` 在**主 OOS 時鐘**(2019-08-31 ~ 2026-03-31,{oos['n']} 月):")
    print(f"     CAGR = **{oos['cagr']:.2f}%**   Sharpe = **{oos['sharpe']:.2f}**   "
          f"MDD = **{oos['mdd']:.2f}%**")
    print("=" * 84)
    print("\n註:區間切片沿用 v0_oos_window_baseline.py 的同一慣例 ——")
    print("    先在全期算月報酬(含跨區間的換手成本),再切窗算指標;")
    print("    因此窗首月的成本是「相對前一月持股」的增量換手,不是 100% 建倉。")
    print("    Gate 2-A 與 Gate 2-B 的基準必須用同一慣例,candidate 也一樣。")


if __name__ == "__main__":
    main()
