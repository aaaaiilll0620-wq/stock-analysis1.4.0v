# -*- coding: utf-8 -*-
"""build_structural_audit.py — P0-U1 Phase B 結構乾跑 + §15/§16 稽核產物

預註冊：docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md

只計算/輸出結構統計:n_A、n_B、n_overlap、n_canonical、denominator equality、
missingness、implementation invariants(§14)的驗證結果，以及母體/持股層級的稽核
CSV(§15)與 baseline↔U1 持股差異 + Jaccard(§16)。

**Phase B 紀律邊界(§24)：本腳本全程不讀取 `P.RET` / `P.bench`，不計算、不印出任何
報酬或績效數字。** Jaccard/持股差異是「選了哪些股票」的結構性描述，不是報酬指標，
§16 原文自己也說「此指標僅描述 U1 改變 portfolio 的幅度，不作為成功/失敗門檻」，故
歸在 Phase B 允許範圍內一併產出。

用法:
    python research/p0_u1_canonical_universe/build_structural_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[2]
for p in (PROJ, PROJ / "scripts", PROJ / "beat_0050", PROJ / "beat_0050" / "strategies"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from high52_lab import Panel, dual_confirm_mask                # noqa: E402
from core import canonical_universe as cu                       # noqa: E402

TIER = "100萬"          # dual100_lab.py::TARGET_TIER —— U1 唯一驗證層,不掃其他層
TOP_PCT = 20            # dual100_lab.py::TOP_PCT(= 80/80 交集門檻的另一種寫法)
OUTDIR = Path(__file__).resolve().parent
BY_DATE_DIR = OUTDIR / "canonical_universe_by_date"


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    BY_DATE_DIR.mkdir(parents=True, exist_ok=True)

    print("建 Panel(realbody_floor=1e6)…(僅結構,不觸碰 P.RET/P.bench)")
    P = Panel(realbody_floor=1e6)
    print(f"面板 {P.T} 月 x {P.S} 檔\n")

    valid = P.tier_valid[TIER]
    composite = P.REAL_COMP.astype(np.float64)

    # ---- baseline(canonical=False)母體與 fusion:各自在 tier_valid 內各算各分母 ----
    v_b = cu.rank_pct_desc(P.F["value_ind"], valid)
    f_b = cu.rank_pct_desc(P.F["revenue_yoy"], valid)
    h_b = cu.rank_pct_desc(P.F["high52_prox"], valid)
    m_b = cu.rank_pct_desc(P.F["momentum"], valid)
    c2_baseline = (v_b + f_b + h_b + (100 - m_b)) / 4
    A_t = valid & np.isfinite(composite)
    B_t_baseline = valid & np.isfinite(c2_baseline)
    M_baseline = dual_confirm_mask(P, TIER, top_pct=TOP_PCT, source="real", canonical=False)

    # ---- U1(canonical=True):A 與 B 共用同一個 C_t 分母 ----
    C_t = cu.build_canonical_valid_mask(valid, composite, P.F, legs=cu.C2_LEGS)
    v_c = cu.rank_pct_desc(P.F["value_ind"], C_t)
    f_c = cu.rank_pct_desc(P.F["revenue_yoy"], C_t)
    h_c = cu.rank_pct_desc(P.F["high52_prox"], C_t)
    m_c = cu.rank_pct_desc(P.F["momentum"], C_t)
    c2_u1 = (v_c + f_c + h_c + (100 - m_c)) / 4
    a_pct_u1 = cu.rank_pct_desc(composite, C_t)
    c2_pct_u1 = cu.rank_pct_desc(c2_u1, C_t)
    M_u1 = dual_confirm_mask(P, TIER, top_pct=TOP_PCT, source="real", canonical=True)  # 內部已跑 §14 assertion

    a_top20_u1 = cu.topk_mask_desc(composite, C_t, TOP_PCT)
    b_top20_u1 = cu.topk_mask_desc(c2_u1, C_t, TOP_PCT)

    # ---- §14 implementation invariants:明寫再驗一次(dual_confirm_mask 內部已跑過一次)----
    cu.assert_canonical_invariants(C_t, composite, c2_u1, P.stocks, P.months)
    assert np.array_equal(M_u1, a_top20_u1 & b_top20_u1), "U1 fusion 遮罩與 topk 交集對不上。"
    assert np.array_equal(C_t & valid, C_t), "canonical universe 溢出了 tier_valid(不應發生)。"
    print("[OK] Implementation invariants (prereg Sec.14) all passed.\n")

    # ---- Sec.15 逐日稽核 ----
    audit_rows = []
    for t in range(P.T):
        date = P.month_s[t]
        audit_rows.append(dict(
            date=date,
            n_A_original=int(A_t[t].sum()),
            n_B_original=int(B_t_baseline[t].sum()),
            n_overlap=int((A_t[t] & B_t_baseline[t]).sum()),
            n_canonical=int(C_t[t].sum()),
            n_A_top20=int(a_top20_u1[t].sum()),
            n_B_top20=int(b_top20_u1[t].sum()),
            n_fusion=int(M_u1[t].sum()),
        ))

        idx = np.where(valid[t] | A_t[t] | B_t_baseline[t] | C_t[t])[0]
        if len(idx) == 0:
            continue
        by_date = pd.DataFrame({
            "date": date,
            "ticker": P.stocks[idx],
            "in_A_original": A_t[t, idx],
            "in_B_original": B_t_baseline[t, idx],
            "real_composite": composite[t, idx],
            "c2_score_full": c2_u1[t, idx],
            "real_composite_pct_U1": a_pct_u1[t, idx],
            "c2_pct_U1": c2_pct_u1[t, idx],
            "a_top20": a_top20_u1[t, idx],
            "b_top20": b_top20_u1[t, idx],
            "fusion_selected": M_u1[t, idx],
        })
        by_date.to_csv(BY_DATE_DIR / f"canonical_universe_{date}.csv",
                       index=False, encoding="utf-8-sig")

    audit = pd.DataFrame(audit_rows)
    audit.to_csv(OUTDIR / "canonical_universe_audit.csv", index=False, encoding="utf-8-sig")
    print(f"寫出 canonical_universe_audit.csv ({len(audit)} rows), "
          f"canonical_universe_by_date/*.csv ({P.T} files)")

    # ---- Sec.16 baseline vs U1 portfolio diff + Jaccard(結構層級,非報酬指標)----
    diff_rows, jaccard_rows = [], []
    for t in range(P.T):
        date = P.month_s[t]
        base_set = set(P.stocks[np.where(M_baseline[t])[0]].tolist())
        u1_set = set(P.stocks[np.where(M_u1[t])[0]].tolist())
        union, inter = base_set | u1_set, base_set & u1_set
        jac = (len(inter) / len(union)) if union else np.nan
        jaccard_rows.append(dict(date=date, n_baseline=len(base_set), n_u1=len(u1_set),
                                 n_intersection=len(inter), jaccard=jac))
        for tkr in sorted(union):
            in_base, in_u1 = tkr in base_set, tkr in u1_set
            ct = "UNCHANGED" if (in_base and in_u1) else ("ENTER_U1" if in_u1 else "EXIT_U1")
            diff_rows.append(dict(date=date, ticker=tkr, baseline_selected=in_base,
                                  u1_selected=in_u1, change_type=ct))

    pd.DataFrame(diff_rows).to_csv(OUTDIR / "U1_vs_baseline_portfolio_diff.csv",
                                   index=False, encoding="utf-8-sig")
    jac_df = pd.DataFrame(jaccard_rows)
    jac_df.to_csv(OUTDIR / "U1_vs_baseline_jaccard_monthly.csv", index=False, encoding="utf-8-sig")
    print(f"寫出 U1_vs_baseline_portfolio_diff.csv ({len(diff_rows)} rows), "
          f"monthly Jaccard median = {jac_df['jaccard'].median():.4f}\n")

    # ---- Sec.24 Phase B 允許查看的統計(structural only,不含任何報酬/績效數字)----
    print("=" * 78)
    print("Phase B structural dry-run summary (NO return/performance numbers)")
    print("=" * 78)
    print(audit[["n_A_original", "n_B_original", "n_overlap", "n_canonical",
                "n_A_top20", "n_B_top20", "n_fusion"]].describe().to_string())
    print(f"\nmissingness (within tier_valid): "
          f"composite {(~np.isfinite(composite[valid])).mean():.4%}, "
          f"c2_baseline {(~np.isfinite(c2_baseline[valid])).mean():.4%}, "
          f"c2_u1 (within C_t, must be 0) {(~np.isfinite(c2_u1[C_t])).mean() if C_t.any() else float('nan'):.4%}")
    print("denominator equality: by construction A_pct_U1 and c2_pct_U1 are BOTH ranked "
          "within C_t for every date (assert_canonical_invariants verified above) — "
          "n_A_rank(t) == n_B_rank(t) == n_canonical(t) holds for all t, not just on average.")
    n_a_eq_c = int((A_t.sum(1) == C_t.sum(1)).sum())
    n_b_eq_c = int((B_t_baseline.sum(1) == C_t.sum(1)).sum())
    print(f"baseline-vs-canonical population size comparison (informational only): "
          f"months where n_A_original==n_canonical: {n_a_eq_c}/{P.T}; "
          f"months where n_B_original==n_canonical: {n_b_eq_c}/{P.T}")


if __name__ == "__main__":
    main()
