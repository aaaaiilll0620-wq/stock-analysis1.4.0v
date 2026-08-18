# -*- coding: utf-8 -*-
"""overlay_alpha_recon.py — 三個中間 α 的**第二條獨立實作對帳**(純計算驗證)
================================================================================
**這不是新的 arm、不是新研究、不產生任何新的判定。** 它只回答一件事:
`overlay_alpha_lab.py` 對 α ∈ {0.25, 0.50, 0.75} 算出來的數字,能不能被一條
**不呼叫它任何核心計算函式**的獨立實作重現到 0.01pp 以內。

**為什麼需要**(2026-08-10 Codex 凍結後方法審查第 10 點):
`docs/研究紀律_ResearchDiscipline.md` §3 要求「凡進判定的淨值序列」由兩套獨立實作
逐期對帳;`docs/預註冊_ExposureOverlay.md` §3-C 自己也明訂矩陣/向量與持股字典兩條
路徑、差異 >0.01pp 即視為 bug。但 `overlay_alpha_lab.run_recon()` 只驗了 **α=0 與
α=1 兩個端點** —— 端點只能證明「blend 在邊界退化正確」,**無法排除中間 α 在 blend、
限速器、初始曝險、成本落點或索引對齊上的共同錯誤**(端點會把這類錯誤一起消掉)。

**獨立性邊界(明講,不含糊)**:
  · 本體日報酬 `rA` 取 `overlay_lab.ledger_body_daily()` —— 那是「持股單位數×開盤價
    +股利現金」的部位帳本路徑,與 `BodyDaily._build()` 的報酬連乘路徑是兩套實作
    (原案 §3-C 指定的第二路徑),不是本案要驗的對象。
  · **本案要驗的 α 專屬鏈路(訊號去抖動→階梯→blend→限速→overlay 報酬→指標)
    全部在本檔內從規格重寫**,不 import `overlay_alpha_lab` 的任何函式。
  · 凍結常數(cap/成本/現金腿)在本檔**照規格硬編**,再與 `overlay_lab` 的值互相
    assert —— 任一邊漂移都會被抓到,不是單方面沿用。

判定:任一項超過 0.01pp → 該 α 的原結果標記 **「無效/未判定」**(不是「研究否定」,
見 Codex 審查第 9 點的三分類),須查清實作後重跑,**不得**直接拿去下結論。

用法:python beat_0050/strategies/overlay_alpha_recon.py
================================================================================
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parent.parent.parent
for _p in (PROJ, PROJ / "scripts", PROJ / "beat_0050" / "strategies"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 資料層與「本體第二路徑」可以 import(那是被驗對象以外的東西);
# α 專屬計算鏈路一律不 import,見檔頭「獨立性邊界」。
from overlay_lab import (Panel, dual_confirm_mask, BodyDaily, ledger_body_daily,  # noqa: E402
                         ADV_FLOOR, TARGET_TIER, TOP_PCT)
import overlay_lab as OL          # noqa: E402 — 僅用於取「待對帳的原始輸出」與常數互檢
import overlay_alpha_lab as AL    # noqa: E402 — 僅用於取「待對帳的原始輸出」,不用其計算
from regime_signal_lab import build_regime_features                        # noqa: E402

# ---- 凍結常數:照規格硬編(不從 OL 沿用),稍後與 OL 互相 assert ----
SPEC_CAP = 0.20            # RATE_LIMIT_CAP(預註冊_ExposureRateLimit)
SPEC_DERISK = 0.285        # DERISK_COST(%,單邊曝險調整成本)
SPEC_RF_ANNUAL = 1.0       # 無風險年利率(%)
SPEC_UP = SPEC_DOWN = 3    # 遲滯確認天數
SPEC_WF_MIN_TRAIN = 60     # OOS 起點(第 60 個月)
ALPHAS = [0.25, 0.50, 0.75]
TOL = 0.01                 # pp


def assert_constants_match() -> None:
    """雙向互檢:本檔硬編的規格值 vs overlay_lab 的常數。任一邊漂移都要炸。"""
    pairs = [("RATE_LIMIT_CAP", SPEC_CAP, OL.RATE_LIMIT_CAP),
             ("DERISK_COST", SPEC_DERISK, OL.DERISK_COST),
             ("R_CASH_D", SPEC_RF_ANNUAL / 252.0, OL.R_CASH_D),
             ("UP_CONFIRM", SPEC_UP, OL.UP_CONFIRM),
             ("DOWN_CONFIRM", SPEC_DOWN, OL.DOWN_CONFIRM),
             ("WF_MIN_TRAIN", SPEC_WF_MIN_TRAIN, OL.WF_MIN_TRAIN)]
    bad = [f"{k}: 本檔規格值 {a!r} ≠ overlay_lab {b!r}" for k, a, b in pairs
           if not np.isclose(float(a), float(b))]
    if bad:
        raise SystemExit("❌ 凍結常數不一致(對帳前置檢查):\n  " + "\n  ".join(bad))
    print(f"[recon] 凍結常數雙向互檢通過({len(pairs)} 項)")


# ==============================================================================
# 以下全部從規格重寫,**不呼叫 overlay_lab / overlay_alpha_lab 的計算函式**
# ==============================================================================
def indep_debounce(above: np.ndarray, up: int, down: int) -> np.ndarray:
    """遲滯:翻 True 需連續 up 天,翻 False 需連續 down 天。
    與 regime_hysteresis_lab.debounce 語意相同但獨立重寫(用 run-length 思路)。"""
    n = len(above)
    state = np.empty(n, dtype=bool)
    cur = bool(above[0])
    run_t = run_f = 0
    for i in range(n):
        if above[i]:
            run_t += 1
            run_f = 0
        else:
            run_f += 1
            run_t = 0
        if (not cur) and run_t >= up:
            cur = True
        elif cur and run_f >= down:
            cur = False
        state[i] = cur
    return state


def indep_ladder(feat: pd.DataFrame) -> np.ndarray:
    """三軸階梯:三條 MA 各自去抖動後的 above 狀態平均 → {0, 1/3, 2/3, 1}。"""
    ew = feat["ew"].to_numpy(float)
    parts = []
    for w in (50, 100, 200):
        parts.append(indep_debounce(ew >= feat[f"ma{w}"].to_numpy(float),
                                    SPEC_UP, SPEC_DOWN).astype(float))
    return (parts[0] + parts[1] + parts[2]) / 3.0


def indep_align(sig_dates: list[str], sig: np.ndarray, want: np.ndarray) -> np.ndarray:
    """把訊號對齊到 body 日期格點:取 ≤ 該日的最後一個訊號值。
    OL 用 bisect 逐日迴圈;這裡用 np.searchsorted 向量化 —— 不同機制,同語意。"""
    fd = np.asarray(sig_dates)
    idx = np.searchsorted(fd, np.asarray([str(d) for d in want]), side="right") - 1
    out = np.where(idx >= 0, sig[np.clip(idx, 0, len(sig) - 1)], 1.0)
    return out.astype(float)


def indep_blend(sig: np.ndarray, alpha: float) -> np.ndarray:
    """α 內插:blended = 1 − α·(1 − sig)。α=0→恆1;α=1→原訊號。"""
    return 1.0 - alpha * (1.0 - np.asarray(sig, float))


def indep_rate_limit(sig: np.ndarray, cap: float) -> np.ndarray:
    """e(0)=1.0;e(d) = e(d−1) + clip(sig(d−1) − e(d−1), ∓cap)。回傳長度 D+1。
    **用 sig(d−1) 不用 sig(d)** —— 無 look-ahead(規格 §3-A-D)。
    這裡用逐步累加 + 顯式上下界,不重用 OL 的寫法。"""
    D = len(sig)
    e = np.empty(D + 1, dtype=float)
    e[0] = 1.0
    prev = 1.0
    for d in range(1, D + 1):
        delta = prev - e[d - 1]
        if delta > cap:
            delta = cap
        elif delta < -cap:
            delta = -cap
        e[d] = e[d - 1] + delta
        prev = sig[d - 1]
    return e


def indep_overlay_returns(rA: np.ndarray, e_full: np.ndarray) -> np.ndarray:
    """r_AC(d) = e(d)·r_A(d) + (1−e(d))·r_cash − |e(d)−e(d−1)|·DERISK_COST。"""
    e = e_full[1:]
    e_prev = e_full[:-1]
    r_cash = SPEC_RF_ANNUAL / 252.0
    return e * rA + (1.0 - e) * r_cash - np.abs(e - e_prev) * SPEC_DERISK


def indep_nav(r_pct: np.ndarray) -> np.ndarray:
    nav = np.empty(len(r_pct), dtype=float)
    acc = 1.0
    for i, r in enumerate(r_pct):
        acc *= (1.0 + r / 100.0)
        nav[i] = acc
    return nav


def indep_cagr(nav: np.ndarray, ppy: float) -> float:
    return float((nav[-1] ** (ppy / len(nav)) - 1.0) * 100.0)


def indep_mdd(nav: np.ndarray) -> float:
    peak = -np.inf
    worst = 0.0
    for v in nav:
        if v > peak:
            peak = v
        dd = v / peak - 1.0
        if dd < worst:
            worst = dd
    return float(worst * 100.0)


def indep_monthly(r_ac: np.ndarray, month_of_day: np.ndarray) -> pd.Series:
    """月聚合:月內日報酬複利成一個月報酬(%)。"""
    df = pd.DataFrame({"m": month_of_day, "r": r_ac})
    return df.groupby("m")["r"].apply(lambda s: (np.prod(1.0 + s.to_numpy() / 100.0) - 1.0) * 100.0)


# ==============================================================================
def main() -> None:
    t0 = time.time()
    assert_constants_match()

    print(f"建面板…(本體 A = dual100 月頻,ADV≥{ADV_FLOOR:,.0f})", flush=True)
    P = Panel(realbody_floor=ADV_FLOOR)
    M = dual_confirm_mask(P, TARGET_TIER, top_pct=TOP_PCT, source="real")
    body = BodyDaily(P, M)

    # --- 本體第二路徑(部位帳本),供獨立鏈路使用 ---
    rb_all = ledger_body_daily(body)
    if not np.all(np.isfinite(rb_all)):
        raise SystemExit("❌ 帳本路徑有非有限值,無法作為獨立對帳基礎。")
    d_body = float(np.max(np.abs(rb_all - body.r_daily)))
    print(f"[recon] 本體兩路徑(帳本 vs 連乘)最大逐日差 {d_body:.3g} pp "
          f"{'✅' if d_body <= TOL else '❌'}")
    if d_body > TOL:
        raise SystemExit("❌ 本體層就對不上,α 對帳無意義,先修本體。")

    # --- OOS 遮罩(獨立重算,不呼叫 body.oos_mask()) ---
    oos = body.month_of_day >= SPEC_WF_MIN_TRAIN
    idx = np.where(oos)[0]
    dates = body.dates[idx]
    rA_indep = rb_all[idx]                 # ← 獨立路徑用帳本序列
    mod = body.month_of_day[idx]

    # --- 獨立訊號鏈路 ---
    feat = build_regime_features()
    sig_dates = feat["date"].astype(str).tolist()
    ladder = indep_ladder(feat)
    sig_aligned = indep_align(sig_dates, ladder, dates)

    print(f"\n{'='*98}")
    print("三個中間 α 的第二條獨立實作對帳(容差 0.01pp;超標 → 標記「無效/未判定」)")
    print(f"{'='*98}")
    print(f"{'α':<7}{'Δe逐日':>11}{'Δr逐日':>11}{'ΔNAV相對':>12}{'Δ月報酬':>11}"
          f"{'ΔCAGR':>9}{'ΔMDD':>9}{'Δē':>9}{'ΔTV':>9}{'Δ成本':>9}{'判定':>7}")

    verdicts = {}
    for alpha in ALPHAS:
        # ---- 獨立鏈路 ----
        blended = indep_blend(sig_aligned, alpha)
        e_ind = indep_rate_limit(blended, SPEC_CAP)
        r_ind = indep_overlay_returns(rA_indep, e_ind)
        nav_ind = indep_nav(r_ind)
        mon_ind = indep_monthly(r_ind, mod)

        # ---- 待驗的原始輸出(overlay_alpha_lab)----
        S = AL.build_series_alpha(body, alpha, "oos")
        nav_lab = S["nav"]
        mon_lab = indep_monthly(S["r_ac"], mod)   # 同一種聚合法,底層日序列不同源

        d_e = float(np.max(np.abs(e_ind - S["e_full"])))
        d_r = float(np.max(np.abs(r_ind - S["r_ac"])))
        d_nav = float(np.max(np.abs(nav_ind / nav_lab - 1.0) * 100.0))
        d_mon = float(np.max(np.abs(mon_ind.to_numpy() - mon_lab.to_numpy())))
        d_cagr = abs(indep_cagr(nav_ind, 252.0) - indep_cagr(nav_lab, 252.0))
        d_mdd = abs(indep_mdd(nav_ind) - indep_mdd(nav_lab))
        d_ebar = abs(float(e_ind[1:].mean()) - float(S["e"].mean())) * 100.0
        tv_i = float(np.abs(np.diff(e_ind)).sum())
        tv_l = float(np.abs(np.diff(S["e_full"])).sum())
        d_tv = abs(tv_i - tv_l)
        d_cost = abs(tv_i - tv_l) * SPEC_DERISK

        worst = max(d_e * 100.0, d_r, d_nav, d_mon, d_cagr, d_mdd, d_ebar, d_tv * 100.0, d_cost)
        ok = worst <= TOL
        verdicts[alpha] = ok
        print(f"{alpha:<7.2f}{d_e:>11.3g}{d_r:>11.3g}{d_nav:>12.3g}{d_mon:>11.3g}"
              f"{d_cagr:>9.3g}{d_mdd:>9.3g}{d_ebar:>9.3g}{d_tv:>9.3g}{d_cost:>9.3g}"
              f"{'✅' if ok else '❌':>7}")

    print(f"\n(Δe/ΔTV 為曝險單位,判定時換算成 pp;ΔNAV 為相對差 %;其餘單位 pp)")
    all_ok = all(verdicts.values())
    print(f"\n第二條獨立實作對帳 → {'✅ 三個中間 α 全部一致' if all_ok else '❌ 有 α 對不上'}")
    if all_ok:
        print("  → 中間 α 的計算已符合專案雙路徑規則(研究紀律 §3)。"
              "**這只證明計算正確,不改變任何研究判定**——HOα-4a 否定、裸上決策維持不變。")
    else:
        bad = [a for a, v in verdicts.items() if not v]
        print(f"  → α={bad} 的原結果依 Codex 審查第 9 點應標記「無效/未判定」"
              f"(**不是研究否定**),查清實作後才可重跑。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
