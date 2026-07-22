# -*- coding: utf-8 -*-
"""dca_calc.py — 定期定額(DCA)模擬 + 資金加權報酬率(MWRR/IRR)。
================================================================================
給一串月報酬(%)與每月投入金額,算:期末價值、總投入、路徑、最大回撤、MWRR(年化)。
MWRR = 把「你每月投入的時間與金額」算進去的個人真實報酬,與 TWRR(策略本身報酬)不同。
非投資建議。
================================================================================
"""
from __future__ import annotations
from typing import List, Dict


def simulate_dca(rets_pct: List[float], monthly_amount: float) -> Dict:
    """每月月初投入 monthly_amount,再套當月報酬。回期末/投入/路徑/最大回撤。"""
    value = invested = 0.0
    peak = 0.0
    mdd = 0.0
    path = []
    for r in rets_pct:
        value += monthly_amount
        invested += monthly_amount
        value *= (1 + r / 100.0)
        peak = max(peak, value)
        if peak > 0:
            mdd = min(mdd, value / peak - 1)
        path.append(value)
    return {"final": value, "invested": invested, "path": path, "mdd": mdd * 100}


def mwrr_annual(rets_pct: List[float], monthly_amount: float, final: float) -> float:
    """解月利率 r 使 Σ C·(1+r)^(N-i) = final,回年化 MWRR(%)。二分法。"""
    n = len(rets_pct)
    if n == 0 or final <= 0:
        return float("nan")

    def fv(r):
        return sum(monthly_amount * (1 + r) ** (n - i) for i in range(n))

    lo, hi = -0.99, 1.0                       # 月利率搜尋範圍
    if fv(lo) > final or fv(hi) < final:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if fv(mid) > final:
            hi = mid
        else:
            lo = mid
    r = (lo + hi) / 2
    return ((1 + r) ** 12 - 1) * 100.0
