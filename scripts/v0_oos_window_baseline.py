# -*- coding: utf-8 -*-
"""v0_oos_window_baseline.py — 把 V0 在**未來 OOS 區間**的 MDD / CAGR / Sharpe
固定成**單一精確數字**,供預註冊 §5 的 MDD 相對門檻使用。

**這不是「執行新的 OOS」**(Codex 第三輪 §7 的禁令),理由三點:
  1. 量的對象是 **V0 baseline 本身**,不是任何 candidate arm。V0 的 H1–H5 已於
     2026-07-30 跑完並落記,它的績效不是未知數,這裡只是把已凍結的策略切一個子區間。
  2. **沒有任何 candidate 存在** —— 不存在「看結果挑 arm」的可能。
  3. Codex 第四輪 §4 明確要求:「V0 基準值要先固定成單一精確數字」。門檻必須在看到
     candidate 數字**之前**凍結,所以這一步一定要在凍結前做。

用的是完全凍結的既有工具:`dual100_lab.tier_net()`(規則 = `real_composite` Top-20%
∩ `c2` Top-20% @ADV≥100萬,等權,`exec_ret.fwd_x`,成本 0.72%),只多做一件事:
把月度報酬序列切到指定區間再算指標。

用法:python scripts/v0_oos_window_baseline.py
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

# 預註冊草案 §2 的區間(**凍結前先固定 V0 的基準值**)
#
# ⚠ 2026-07-31 Codex 第六輪 §3:OOS 的**主時鐘改成 2019-08 ~ 2026-03(80 月)**
#    —— 統一避開 A1/A2 的邊界污染窗(2019-01~07)。87 月版**只作 robustness 描述**,
#    不得作為判定依據,也不得在兩者衝突時擇一(那是結果相依的選擇)。
WINDOWS = [
    ("Train      2005-01~2014-12", "2005-01-01", "2014-12-31"),
    ("Validation 2015-01~2018-12", "2015-01-01", "2018-12-31"),
    ("**OOS(主)** 2019-08~2026-03", "2019-08-01", "2026-03-31"),
    ("OOS(robust) 2019-01~2026-03", "2019-01-01", "2026-03-31"),
    ("全期(對照)  2005-01~2026-03", "2005-01-01", "2026-03-31"),
]
# Gate 3 的時代穩健:ERAS 與**主 OOS 時鐘**的交集(第一段被截短,必須揭露)
OOS_ERAS = [
    ("19-21(截短) 2019-08~2021-12", "2019-08-01", "2021-12-31"),
    ("2022        2022-01~2022-12", "2022-01-01", "2022-12-31"),
    ("23-26       2023-01~2026-03", "2023-01-01", "2026-03-31"),
]
PRIMARY = "**OOS(主)** 2019-08~2026-03"


def main():
    from dual100_lab import tier_net, TARGET_TIER, ADV_FLOOR
    from high52_lab import Panel, met, met_vs, turnover

    P = Panel(realbody_floor=ADV_FLOOR)
    ret, M = tier_net(P, TARGET_TIER)          # V0 規則,凍結參數,面板實測滑價
    bench = P.BENCH if hasattr(P, "BENCH") else None
    months = P.month_s

    print(f"面板:{P.realbody_path.name}   {len(months)} 月   "
          f"{months[0]} ~ {months[-1]}")
    print("規則:real_composite Top-20% ∩ c2 Top-20% @ADV≥100萬,等權,exec_ret.fwd_x,"
          "成本 0.47%+面板實測滑價")
    print("\n⚠ 這是 **V0 baseline 的描述性切片**,不是任何 candidate 的 OOS 結果。\n")

    print(f"{'區間':<30}{'月數':>6}{'CAGR%':>9}{'Sharpe':>9}{'MDD%':>9}{'換手%':>9}")
    out = {}
    for label, lo, hi in WINDOWS + OOS_ERAS:
        if label == OOS_ERAS[0][0]:
            print("-" * 72 + "  ← 以下為 Gate 3 的 OOS 內時代(描述性)")
        sel = (months >= lo) & (months <= hi)
        r = np.where(sel, ret, np.nan)
        m = met(r)
        t = turnover(M[sel])
        out[label] = m
        print(f"{label:<30}{m.get('n', 0):>6}{m.get('cagr', np.nan):>9.2f}"
              f"{m.get('sharpe', np.nan):>9.2f}{m.get('mdd', np.nan):>9.2f}"
              f"{t*100 if t == t else np.nan:>9.1f}")

    oos = out[PRIMARY]
    print("\n" + "=" * 78)
    print("→ 預註冊 §5 **Gate 2-B** 的基準(**凍結用,單一精確數字**):")
    print(f"   V0 在**主 OOS 時鐘**(2019-08-31 ~ 2026-03-31,{oos['n']} 月)的策略本體:")
    print(f"     CAGR = **{oos['cagr']:.2f}%**   Sharpe = **{oos['sharpe']:.2f}**   "
          f"MDD = **{oos['mdd']:.2f}%**")
    print(f"   → MDD 非劣性門檻:≥ {oos['mdd']:.2f} − 5.00 = **{oos['mdd']-5:.2f}%**")
    print("   → CAGR / Sharpe 改用 paired block bootstrap 的 95% CI 下界(預註冊 §5-1),"
          "不再用點估計比較")
    print("=" * 78)
    print("\n註:此處的 MDD 是**策略本體**(固定 100% 曝險、無 regime 曝險 overlay)。")
    print("    不得與 `core/regime_exposure.py` overlay 後的 MDD 混用。")


if __name__ == "__main__":
    main()
