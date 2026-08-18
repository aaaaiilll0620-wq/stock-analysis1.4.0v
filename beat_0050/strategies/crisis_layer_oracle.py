# -*- coding: utf-8 -*-
"""crisis_layer_oracle.py — 第二層(系統性風險)的**完美後見之明上界**測試
================================================================================
⚠️ **這不是一個可實作的策略,是一個上界(upper bound)。** 它假設你**事先就知道**
每次信用危機的精確起訖日期,在那些窗口內把曝險砍到指定水準。真實世界裡你只會在
利差已經噴出去之後才知道 —— 所以真實規則的表現**必定劣於本檔的數字**。

**用途**:回答一個決定性問題 —— 「值不值得花力氣去建 credit/vol 第二層?」
  · 若連完美後見之明版都改善有限 → **真實規則不可能更好,這條線可以直接關掉。**
  · 若完美版顯著改善 → 才值得繼續評估「真實訊號能多接近這個上界」。

**危機窗定義(依 ICE BofA US HY OAS 的歷史高點,人工標註)**:
  GFC(2008)、歐債(2011)、油價/中國(2015-16)、COVID(2020)。
  日期取自公開的利差走勢轉折,**不是最佳化出來的** —— 但仍是後見之明,見上。

**性質**:描述性上界估計,非預註冊假設檢定,**不產生任何研究判定**。

用法:python beat_0050/strategies/crisis_layer_oracle.py
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

import overlay_lab as OL   # noqa: E402

ALPHA = 0.25               # 現行採用的 overlay 強度(第一層)
CRISIS_LEVELS = [0.50, 0.40]

# 人工標註的信用危機窗(HY OAS 明顯抬升的期間)
CRISIS_WINDOWS = [
    ("GFC 金融海嘯",   "2008-09-15", "2009-06-30"),
    ("歐債危機",       "2011-08-01", "2011-12-31"),
    ("油價/中國",      "2015-12-01", "2016-02-29"),
    ("COVID",          "2020-03-01", "2020-06-30"),
]


def metrics(r: np.ndarray) -> dict:
    nav = OL.nav_of(r)
    return {"cagr": OL.cagr_pct(nav, 252.0), "mdd": OL.mdd_pct(nav),
            "sharpe": OL.sharpe_of(r, 252.0)}


def main() -> None:
    t0 = time.time()
    OL._assert_frozen()
    print("⚠️ 完美後見之明上界 —— 不是可實作策略,真實規則必定更差。\n")

    P = OL.Panel(realbody_floor=OL.ADV_FLOOR)
    M = OL.dual_confirm_mask(P, OL.TARGET_TIER, top_pct=OL.TOP_PCT, source="real")
    body = OL.BodyDaily(P, M)

    # 全期日序列
    mask = np.ones(len(body.r_daily), bool)
    idx = np.where(mask)[0]
    dates = np.array([str(d)[:10] for d in body.dates[idx]])
    rA = body.r_daily[idx]
    raw_sig = OL.daily_signal(body.dates[idx])
    sig_alpha = 1.0 - ALPHA * (1.0 - raw_sig)

    in_crisis = np.zeros(len(dates), bool)
    print(f"{'危機窗':<16}{'起':<12}{'訖':<12}{'交易日':>7}")
    for name, s, e in CRISIS_WINDOWS:
        w = (dates >= s) & (dates <= e)
        in_crisis |= w
        print(f"{name:<16}{s:<12}{e:<12}{int(w.sum()):>7}")
    print(f"{'合計':<16}{'':<12}{'':<12}{int(in_crisis.sum()):>7}"
          f"  ({in_crisis.mean()*100:.1f}% 的交易日)")

    print("\n" + "=" * 92)
    print("全期(2005-2026)結果 —— 完美後見之明的危機層能多買到多少?")
    print("=" * 92)
    print(f"\n{'配置':<40}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'平均曝險':>10}")

    rows = {}
    # 基準1:裸上
    e0 = OL.rate_limited(np.ones_like(sig_alpha))
    r0 = OL.overlay_returns(rA, e0)
    rows["裸上(α=0)"] = (metrics(r0), e0[1:].mean())
    # 基準2:現行 α=0.25
    e1 = OL.rate_limited(sig_alpha)
    r1 = OL.overlay_returns(rA, e1)
    rows[f"現行:α={ALPHA}(第一層)"] = (metrics(r1), e1[1:].mean())
    # 加上完美危機層
    for lv in CRISIS_LEVELS:
        sig_c = np.where(in_crisis, np.minimum(sig_alpha, lv), sig_alpha)
        ec = OL.rate_limited(sig_c)
        rc = OL.overlay_returns(rA, ec)
        rows[f"α={ALPHA} + 完美危機層砍到 {lv*100:.0f}%"] = (metrics(rc), ec[1:].mean())

    for k, (m, ebar) in rows.items():
        print(f"{k:<40}{m['cagr']:>9.2f}{m['sharpe']:>8.2f}{m['mdd']:>9.2f}{ebar:>10.4f}")

    base = rows[f"現行:α={ALPHA}(第一層)"][0]
    print(f"\n{'':<40}{'ΔCAGR':>9}{'Δ夏普':>8}{'ΔMDD':>9}   (vs 現行 α=0.25)")
    for lv in CRISIS_LEVELS:
        k = f"α={ALPHA} + 完美危機層砍到 {lv*100:.0f}%"
        m = rows[k][0]
        print(f"{k:<40}{m['cagr']-base['cagr']:>+9.2f}{m['sharpe']-base['sharpe']:>+8.2f}"
              f"{abs(base['mdd'])-abs(m['mdd']):>+9.2f}")
    print("\n(ΔMDD 正值 = 回撤變淺)")

    # 逐危機窗:那段期間策略自己表現如何
    print("\n" + "=" * 92)
    print("逐危機窗:該窗內策略(現行 α=0.25)的實際表現 —— 判斷「值不值得砍」")
    print("=" * 92)
    print(f"\n{'危機窗':<16}{'窗內報酬%':>11}{'窗內MDD%':>11}{'砍到50%可省':>13}{'判讀':>22}")
    for name, s, e in CRISIS_WINDOWS:
        w = (dates >= s) & (dates <= e)
        if w.sum() < 5:
            continue
        seg = r1[w]
        nav = OL.nav_of(seg)
        tot = (nav[-1] - 1.0) * 100.0
        mdd = OL.mdd_pct(nav)
        saved = -tot * 0.5 if tot < 0 else -tot * 0.5   # 砍一半 → 損益也大致砍一半
        verdict = "✅ 該砍" if tot < -5 else ("❌ 砍了會虧" if tot > 5 else "— 影響小")
        print(f"{name:<16}{tot:>11.2f}{mdd:>11.2f}{saved:>13.2f}{verdict:>22}")

    print("\n※「砍到50%可省」= 窗內報酬 × 50% 的粗估;正值=省下虧損,負值=少賺。")
    print("\n" + "=" * 92)
    print("⚠️ 再次聲明:以上是**完美後見之明**(事先知道每次危機的精確起訖日)。")
    print("   真實的 credit/vol 規則只會在利差已經噴出後才觸發 → **表現必定劣於本表**。")
    print("   若本表的改善幅度就已經有限,真實規則不可能更好。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
