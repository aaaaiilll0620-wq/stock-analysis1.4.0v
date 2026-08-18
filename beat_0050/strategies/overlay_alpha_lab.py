# -*- coding: utf-8 -*-
"""overlay_alpha_lab.py — Overlay 強度掃描:α 內插(裸上 ↔ 已否定的滿血 overlay)
================================================================================
**依 `docs/預註冊_OverlayAlpha強度掃描.md`(2026-08-10 凍結)實作。**

`docs/預註冊_ExposureOverlay.md`(P-Overlay-C)測的是滿血 overlay(α=1),MDD 遠優於
門檻但 CAGR 不足,硬否定。該文件 §7.5 留了一句「更輕的 overlay 須另行預註冊」——
本檔就是那份預註冊的實作。**不重寫任何機制**,只在 `overlay_lab.py` 的日訊號與
限速器之間插入一個 blend 步驟:

    blended_sig(d) = 1 − α·(1 − sig(d))        α=0 → 裸上;α=1 → 已測試否定的滿血版

之後逐字沿用 `overlay_lab.rate_limited()` / `overlay_lab.overlay_returns()`,
不改一行。凡是這裡沒有重新定義的東西(成本模型、OOS 窗、Panel/本體建構),
一律從 `overlay_lab` import,不重寫、不允許漂移。

用法:
    python beat_0050/strategies/overlay_alpha_lab.py --part recon   # HOα-0 對帳自檢
    python beat_0050/strategies/overlay_alpha_lab.py --part ho1     # 三個 α 的部署門檻
    python beat_0050/strategies/overlay_alpha_lab.py --part all
================================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parent.parent.parent
for _p in (PROJ, PROJ / "scripts", PROJ / "beat_0050" / "strategies"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import overlay_lab as OL  # noqa: E402 — 逐字沿用,不重寫

ALPHA_GRID = [0.25, 0.50, 0.75]     # 預註冊 §1 凍結:只測這三點,不掃連續
RECON_TOL = 0.01                     # 與原案 RECON_TOL 一致(pp)

# 原案凍結數字(docs/預註冊_ExposureOverlay.md §7.3,α=1 對帳基準)
FROZEN_ALPHA1_CAGR = 15.61
FROZEN_ALPHA1_MDD = -20.56


def build_series_alpha(body: "OL.BodyDaily", alpha: float, window: str = "oos") -> dict:
    """`overlay_lab.build_series` 的 α 版:唯一差異是訊號先 blend 向裸上,
    其餘(限速器、overlay_returns、OOS 窗選取)逐字相同。"""
    m = body.oos_mask() if window == "oos" else np.ones(len(body.r_daily), bool)
    idx = np.where(m)[0]
    dates, rA = body.dates[idx], body.r_daily[idx]
    sig = OL.daily_signal(dates)
    blended = 1.0 - alpha * (1.0 - sig)
    e_full = OL.rate_limited(blended)
    r_ac = OL.overlay_returns(rA, e_full)
    return {"idx": idx, "dates": dates, "rA": rA, "sig": blended, "e_full": e_full,
            "e": e_full[1:], "r_ac": r_ac, "nav": OL.nav_of(r_ac)}


def _gate(m: dict) -> bool:
    return abs(m["mdd"]) <= OL.MDD_GATE and m["cagr"] >= OL.CAGR_GATE


def run_recon(body: "OL.BodyDaily") -> bool:
    print("\n" + "=" * 92)
    print("HOα-0 — 對帳自檢(α=0 應重現裸上 A;α=1 應重現凍結的 P-Overlay-C 數字)")
    print("=" * 92)
    ok = True

    S0 = build_series_alpha(body, 0.0, "oos")
    d0 = float(np.max(np.abs(S0["r_ac"] - S0["rA"])))
    ok0 = d0 <= RECON_TOL
    print(f"α=0  A×C vs 裸上 rA:最大逐日差 {d0:.4g} pp  {'✅' if ok0 else '❌'}")
    ok &= ok0

    S1 = build_series_alpha(body, 1.0, "oos")
    m1 = OL.show_daily("α=1  A×C(應=原滿血 overlay)", S1["r_ac"])
    d_cagr = abs(m1["cagr"] - FROZEN_ALPHA1_CAGR)
    d_mdd = abs(m1["mdd"] - FROZEN_ALPHA1_MDD)
    ok1 = d_cagr <= RECON_TOL and d_mdd <= RECON_TOL
    print(f"  CAGR {m1['cagr']:.2f}% vs 凍結 {FROZEN_ALPHA1_CAGR}%  差 {d_cagr:.4g}pp")
    print(f"  MDD  {m1['mdd']:.2f}% vs 凍結 {FROZEN_ALPHA1_MDD}%  差 {d_mdd:.4g}pp")
    print(f"  → {'✅重現' if ok1 else '❌對不上'}")
    ok &= ok1

    print(f"\nHOα-0 → {'✅通過,可往下跑 α 掃描' if ok else '❌對帳失敗 —— 中止,查 blend 實作,不做任何 α 判定'}")
    return bool(ok)


def run_ho1_alpha(body: "OL.BodyDaily") -> dict:
    print("\n" + "=" * 92)
    print(f"HOα-1 — 部署門檻,逐 α 判定(α ∈ {ALPHA_GRID})")
    print("=" * 92)
    print(f"\n{'α':<8}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'ē(平均曝險)':>14}{'判定':>8}")
    results = {}
    for alpha in ALPHA_GRID:
        S = build_series_alpha(body, alpha, "oos")
        nav = S["nav"]
        m = {"cagr": OL.cagr_pct(nav, 252.0), "mdd": OL.mdd_pct(nav),
             "sharpe": OL.sharpe_of(S["r_ac"], 252.0), "n": len(S["r_ac"])}
        ok = _gate(m)
        print(f"{alpha:<8.2f}{m['cagr']:>9.2f}{m['sharpe']:>8.2f}{m['mdd']:>9.2f}"
              f"{S['e'].mean():>14.4f}{'✅' if ok else '❌':>8}")
        results[alpha] = {"metrics": m, "ok": ok}
    passing = sorted(a for a, r in results.items() if r["ok"])
    print(f"\n通過 HOα-1 的 α:{passing if passing else '無'}")
    if not passing:
        print("→ 三個 α 全部否定:α 內插這條路也關閉,記錄否定結果,不得再試其他 α 值"
              "(預註冊 §3)。")
    else:
        print(f"→ 依預註冊 §3 決策規則,候選 = 最小的通過 α = {passing[0]}"
              "(最保守也最接近裸上、犧牲 CAGR 最少),須再過 HOα-3 且 HOα-4a 才算候選成立。")
    return {"results": results, "passing": passing}


def run_ho3_alpha(body: "OL.BodyDaily", alpha: float) -> dict:
    print("\n" + "=" * 92)
    print(f"HOα-3 — 相位對齊虛無(α={alpha},逐字沿用原 HO3 方法論,B={OL.HO3_B})")
    print("=" * 92)
    S = build_series_alpha(body, alpha, "oos")
    rA, e_full = S["rA"], S["e_full"]
    D = len(rA)
    e, e_prev = e_full[1:], e_full[:-1]
    base = (1.0 - e) * OL.R_CASH_D - np.abs(e - e_prev) * OL.DERISK_COST
    dd_real = abs(OL.mdd_pct(OL.nav_of(S["r_ac"])))
    rng = np.random.default_rng(OL.HO3_SEED)
    taus = rng.integers(1, D, size=OL.HO3_B)
    dd = np.empty(OL.HO3_B)
    t0 = time.time()
    for b in range(OL.HO3_B):
        rot = np.roll(rA, -int(taus[b]))
        dd[b] = abs(OL.mdd_pct(OL.nav_of(e * rot + base)))
        if b % 250 == 0:
            print(f"  {b}/{OL.HO3_B} ({time.time()-t0:.0f}s)", flush=True)
    p = float((1 + np.sum(dd <= dd_real)) / (OL.HO3_B + 1))
    ok = p < OL.HO3_ALPHA
    print(f"\n  虛無 |MDD| 分布:p5 {np.percentile(dd,5):.2f}  中位 {np.median(dd):.2f}  "
          f"p95 {np.percentile(dd,95):.2f}")
    print(f"  實際 |MDD| {dd_real:.2f}  → p = {p:.4f}")
    print(f"HOα-3(α={alpha}) → {'✅通過' if ok else '❌否定'}(門檻 p<{OL.HO3_ALPHA})")
    return {"ho3": ok, "p": p}


def run_ho4a_alpha(body: "OL.BodyDaily", alpha: float) -> dict:
    print("\n" + "=" * 92)
    print(f"HOα-4a — 滑價穩健(α={alpha},來回 {OL.H4_SLIP}%)")
    print("=" * 92)
    body4 = body.with_slip(OL.H4_SLIP)
    S4 = build_series_alpha(body4, alpha, "oos")
    m = OL.show_daily(f"A×C(α={alpha}) @滑價 {OL.H4_SLIP}%", S4["r_ac"])
    ok = _gate(m)
    print(f"\nHOα-4a(α={alpha}) |MDD| {abs(m['mdd']):.2f}% ≤ {OL.MDD_GATE}% 且 CAGR "
          f"{m['cagr']:.2f}% ≥ {OL.CAGR_GATE}% → {'✅通過' if ok else '❌否定'}")
    return {"ho4a": ok, "metrics": m}


def main() -> None:
    ap = argparse.ArgumentParser(description="Overlay α 強度掃描(門檻已凍結,見預註冊)")
    ap.add_argument("--part", default="recon",
                    choices=["recon", "ho1", "ho3", "ho4a", "all"])
    a = ap.parse_args()
    OL._assert_frozen()   # 確認底層 overlay_lab 的凍結常數沒被動過

    t0 = time.time()
    print(f"建面板…(本體 A = dual100 月頻,ADV≥{OL.ADV_FLOOR:,.0f})", flush=True)
    P = OL.Panel(realbody_floor=OL.ADV_FLOOR)
    M = OL.dual_confirm_mask(P, OL.TARGET_TIER, top_pct=OL.TOP_PCT, source="real")
    body = OL.BodyDaily(P, M)
    print(f"面板 {P.T} 月 × {P.S} 檔;本體日序列 {len(body.r_daily)} 日 "
          f"({time.time()-t0:.0f}s)")

    if not run_recon(body):
        raise SystemExit("\n❌ HOα-0 對帳未過,中止(預註冊 §3:對帳失敗不做任何 α 判定)。")
    if a.part == "recon":
        print(f"\n總耗時 {time.time()-t0:.0f}s")
        return

    ho1 = run_ho1_alpha(body)
    if a.part == "ho1":
        print(f"\n總耗時 {time.time()-t0:.0f}s")
        return

    candidate = ho1["passing"][0] if ho1["passing"] else None
    if a.part == "ho3":
        if candidate is None:
            raise SystemExit("❌ 沒有 α 通過 HOα-1,無候選可測 HOα-3。")
        run_ho3_alpha(body, candidate)
    elif a.part == "ho4a":
        if candidate is None:
            raise SystemExit("❌ 沒有 α 通過 HOα-1,無候選可測 HOα-4a。")
        run_ho4a_alpha(body, candidate)
    elif a.part == "all":
        print("\n" + "=" * 92)
        print("Overlay α 強度掃描 —— 判定總表")
        print("=" * 92)
        if candidate is None:
            print("HOα-1 三個 α 全部否定 → α 內插這條路關閉,不再往下跑 HOα-3/4a。")
        else:
            r3 = run_ho3_alpha(body, candidate)
            r4 = run_ho4a_alpha(body, candidate)
            hard = bool(r3["ho3"]) and bool(r4["ho4a"])
            print(f"\n候選 α = {candidate}")
            print(f"HOα-1  部署門檻(主)  ✅通過")
            print(f"HOα-3  相位對齊虛無  {'✅通過' if r3['ho3'] else '❌否定'}")
            print(f"HOα-4a 滑價穩健(硬)  {'✅通過' if r4['ho4a'] else '❌否定'}")
            print(f"\n**三關全過** → {'✅ validated 部署候選' if hard else '❌ 未成立'}"
                  "(通過≠可上線,見預註冊 §4)")
    print(f"\n結果(不論正負)請寫入 docs/預註冊_OverlayAlpha強度掃描.md §6。")
    print(f"總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
