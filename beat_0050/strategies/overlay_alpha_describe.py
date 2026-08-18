# -*- coding: utf-8 -*-
"""overlay_alpha_describe.py — α=0.25 的**事後描述性量測**(不是判定、不是新 arm)
================================================================================
⚠️ **這份輸出不得作為研究結論引用。**

`docs/預註冊_OverlayAlpha強度掃描.md` 的凍結判定是 **HOα-4a 否定、無 validated 部署候選**,
本檔**不改變、也不挑戰**該判定。本檔只補三個「凍結測試沒問到、但使用者做部署取捨時需要」
的描述性數字:

  1. **裸上 vs α=0.25 在同一滑價下的相對比較** —— HOα-4a 是拿 α=0.25@0.60% 去對
     **絕對門檻 20%**,從未與**裸上@0.60%** 直接比較。相對退化幅度才是取捨資訊。
  2. **全期(255 月)MDD** —— 所有既有 MDD 數字都在 OOS 段;使用者真正在意的
     「全期 −68~70%」對 α=0.25 是多少,**從未量過**。
  3. **六時代分佈** —— 2008/2022 兩段壓力期的表現。

**性質**:純計算描述,與 `overlay_alpha_recon.py` 同級(該檔已驗證本計算路徑在三個中間 α
上與獨立實作一致到 1e-13 pp)。**事後(post-hoc)**:這些數字是在看過凍結判定之後才算的,
依研究紀律 §2 **不得反過來當成推翻或補救該判定的證據**,只能作為使用者「要不要走
§6.3 式明文豁免」的決策輸入。

用法:python beat_0050/strategies/overlay_alpha_describe.py
================================================================================
"""
from __future__ import annotations

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

import overlay_lab as OL          # noqa: E402
import overlay_alpha_lab as AL    # noqa: E402
from beat_0050.honest_backtest import ERAS   # noqa: E402

ALPHA = 0.25
SLIP_STRESS = 0.60


def metrics(r: np.ndarray) -> dict:
    nav = OL.nav_of(r)
    return {"cagr": OL.cagr_pct(nav, 252.0), "mdd": OL.mdd_pct(nav),
            "sharpe": OL.sharpe_of(r, 252.0), "n": len(r)}


def main() -> None:
    t0 = time.time()
    OL._assert_frozen()
    print("⚠️ 事後描述性量測 —— 不改變 HOα-4a 否定判定,不得當作研究結論引用。\n")

    print(f"建面板…(dual100 月頻,ADV≥{OL.ADV_FLOOR:,.0f})", flush=True)
    P = OL.Panel(realbody_floor=OL.ADV_FLOOR)
    M = OL.dual_confirm_mask(P, OL.TARGET_TIER, top_pct=OL.TOP_PCT, source="real")
    body = OL.BodyDaily(P, M)
    body_s = body.with_slip(SLIP_STRESS)
    print(f"面板 {P.T} 月 × {P.S} 檔;日序列 {len(body.r_daily)} 日 ({time.time()-t0:.0f}s)")

    # ---------------------------------------------------------------- 1. 同滑價下的相對比較
    print("\n" + "=" * 96)
    print("① 裸上 vs α=0.25 —— **同一滑價下**的相對比較(HOα-4a 從未做過這個對照)")
    print("=" * 96)
    print(f"\n{'情境':<34}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'平均曝險':>10}")
    rows = {}
    for slip_tag, b in (("基準(面板實測 tick_slip)", body), (f"壓力(滑價 {SLIP_STRESS}%)", body_s)):
        for a_tag, a in (("裸上 α=0", 0.0), (f"overlay α={ALPHA}", ALPHA)):
            S = AL.build_series_alpha(b, a, "oos")
            m = metrics(S["r_ac"])
            rows[(slip_tag, a_tag)] = m
            print(f"{slip_tag + ' · ' + a_tag:<34}{m['cagr']:>9.2f}{m['sharpe']:>8.2f}"
                  f"{m['mdd']:>9.2f}{S['e'].mean():>10.4f}")

    print(f"\n{'':<34}{'ΔCAGR':>9}{'Δ夏普':>8}{'ΔMDD':>9}{'每1pp MDD 的CAGR成本':>22}")
    for slip_tag in ("基準(面板實測 tick_slip)", f"壓力(滑價 {SLIP_STRESS}%)"):
        n_ = rows[(slip_tag, "裸上 α=0")]
        o_ = rows[(slip_tag, f"overlay α={ALPHA}")]
        d_cagr = o_["cagr"] - n_["cagr"]
        d_mdd = abs(n_["mdd"]) - abs(o_["mdd"])          # 正 = MDD 改善
        rate = (-d_cagr / d_mdd) if d_mdd > 0 else float("nan")
        print(f"{slip_tag + ' :  overlay − 裸上':<34}{d_cagr:>+9.2f}"
              f"{o_['sharpe']-n_['sharpe']:>+8.2f}{d_mdd:>+9.2f}{rate:>22.3f}")
    print("\n(ΔMDD 正值 = overlay 讓回撤變淺;最右欄 = 買 1pp 回撤改善要付幾 pp 的 CAGR)")

    # ---------------------------------------------------------------- 2. 全期 MDD
    print("\n" + "=" * 96)
    print("② 全期(255 月,含 2005-2009 in-sample 段)—— 使用者真正在意的『−68~70%』對應到哪")
    print("=" * 96)
    print(f"\n{'情境':<34}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'平均曝險':>10}")
    full = {}
    for a_tag, a in (("裸上 α=0", 0.0), (f"overlay α={ALPHA}", ALPHA)):
        S = AL.build_series_alpha(body, a, "full")
        m = metrics(S["r_ac"])
        full[a_tag] = (m, S)
        print(f"{a_tag:<34}{m['cagr']:>9.2f}{m['sharpe']:>8.2f}{m['mdd']:>9.2f}"
              f"{S['e'].mean():>10.4f}")
    dn, do = full["裸上 α=0"][0], full[f"overlay α={ALPHA}"][0]
    d_mdd_full = abs(dn["mdd"]) - abs(do["mdd"])
    d_cagr_full = do["cagr"] - dn["cagr"]
    print(f"\n全期 overlay − 裸上:ΔCAGR {d_cagr_full:+.2f}pp、ΔMDD {d_mdd_full:+.2f}pp"
          f"(正=回撤變淺)"
          + (f"、每 1pp MDD 成本 {-d_cagr_full/d_mdd_full:.3f}pp" if d_mdd_full > 0 else ""))
    print("※ 全期日路徑 MDD 與 H4 的月度 −68~70% 是不同量測路徑(日路徑通常更深),不可直接互換引用。")

    # ---------------------------------------------------------------- 3. 六時代
    print("\n" + "=" * 96)
    print("③ 六時代 MDD 分佈(描述性;2008/2022 是壓力段)")
    print("=" * 96)
    S_n, S_o = full["裸上 α=0"][1], full[f"overlay α={ALPHA}"][1]
    dts = np.array([str(x)[:10] for x in S_n["dates"]])
    print(f"\n{'時代':<20}{'裸上MDD%':>11}{'α=0.25 MDD%':>14}{'改善pp':>9}"
          f"{'裸上CAGR%':>11}{'α=0.25 CAGR%':>14}")
    for name, s, e_ in ERAS:
        sel = (dts >= s) & (dts <= e_)
        if sel.sum() < 20:
            continue
        mn, mo = metrics(S_n["r_ac"][sel]), metrics(S_o["r_ac"][sel])
        print(f"{name:<20}{mn['mdd']:>11.2f}{mo['mdd']:>14.2f}"
              f"{abs(mn['mdd'])-abs(mo['mdd']):>9.2f}{mn['cagr']:>11.2f}{mo['cagr']:>14.2f}")

    print("\n" + "=" * 96)
    print("⚠️ 再次聲明:以上為**事後描述**,HOα-4a 否定判定不變、無 validated 部署候選。")
    print("   若據此採用 α=0.25,那是**使用者明文豁免凍結門檻的部署決策**(比照 §6.3 前例),")
    print("   必須在文件中記為『研究否定 + 人為豁免』,不得記為『研究通過』。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
