# -*- coding: utf-8 -*-
"""dual100_liveconfig_lab.py — 用「live 設定」重新驗證 dual100 的確認性檢定
================================================================================
預註冊:`docs/預註冊_Live設定驗證.md`(2026-08-10 凍結)。本腳本只**執行**該文件寫死的
協定,不重新決定門檻。

待驗對象:選股規則不變(`composite` Top20% ∩ `c2` Top20% @ADV≥100萬),但 composite
腿改用**生產環境實際在用的設定**(估值窗 2019、籌碼源 institutional_gross)重算,
不是研究驗證用的真身面板(估值窗 2004、籌碼源 institutional_flow 淨額)。

  H1  前置閘(in-sample):全期夏普 >0050 且基準階梯①選股階 >0。H1 失敗即結案。
  H2  walk-forward(主假設):與 dual100 H2 同一段 OOS,固定 100萬 層。
  H3  滑價敏感度:0.60% 時夏普仍須 >0.68。
  H4  六時代穩健:≥4 段勝等權母體 且 ≥3 段夏普勝 0050。

用法:
    python beat_0050/strategies/dual100_liveconfig_lab.py --part verify
    python beat_0050/strategies/dual100_liveconfig_lab.py --part h1
    python beat_0050/strategies/dual100_liveconfig_lab.py --part all
================================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))   # high52_lab
sys.path.insert(0, str(PROJ / "beat_0050"))                # honest_backtest
sys.path.insert(0, str(PROJ / "scripts"))                  # lab_paths

assert "beat_0050.realbody.bt_bundle" not in sys.modules, \
    "bt_bundle 已被匯入過 —— 這支腳本不該碰它(會跟研究設定混淆),換乾淨 process 再跑。"

from high52_lab import Panel, evaluate, met, met_vs, turnover, dual_confirm_mask, OUTDIR  # noqa: E402
from honest_backtest import Engine, ERAS, SLIPPAGE_RT  # noqa: E402

LIVE_PANEL_PATH = PROJ / "data" / "research_base" / "liveconfig_scores_adv100w.parquet"
TARGET_TIER = "100萬"
TOP_PCT = 20
BENCH_SHARPE = 0.68
SLIP_GRID = [0.25, 0.40, 0.60, 0.80]
SLIP_PASS = 0.60
WF_MIN_TRAIN = 60


def load_liveconfig_panel() -> Panel:
    """建 Panel 時照常載入研究面板(F/RET/SLIP/ADV/tier_valid/bench 全部共用,
    這些都不受估值窗/籌碼源覆寫影響),**建完後**把 `_real_comp` 換成 live 設定重算的版本。
    這是唯一安全、不重寫 Panel 建構邏輯的做法——REAL_COMP 只是個私有屬性 + property,
    覆寫它不影響 Panel 其他任何共用資料。"""
    if not LIVE_PANEL_PATH.exists():
        raise SystemExit(f"❌ 找不到 {LIVE_PANEL_PATH}。先跑 "
                         f"python scripts/build_liveconfig_scores.py --adv-floor 1e6"
                         f"(背景建置,1.5~2 小時)。")
    P = Panel(realbody_floor=1e6)   # 借用研究面板的 F/RET/SLIP/ADV/tier_valid/bench(共用不變)

    lv = pd.read_parquet(LIVE_PANEL_PATH, columns=["as_of", "stock_id", "live_composite"])
    lv["as_of"] = lv["as_of"].astype(str)
    lv["stock_id"] = lv["stock_id"].astype(str)
    mi = {m: i for i, m in enumerate(P.month_s)}
    si = {s: j for j, s in enumerate(P.stocks)}
    r = lv["as_of"].map(mi)
    c = lv["stock_id"].map(si)
    ok = r.notna() & c.notna()
    if not ok.all():
        n_drop = int((~ok).sum())
        print(f"[load] {n_drop} 列 live 設定分數對不到本 Panel 的 (month, stock) 索引"
              f"(通常是面板 truncate 掉的月份,如 0050 無基準的最後一個月)——正常,略過。")
    mat = np.full((P.T, P.S), np.nan, dtype=np.float32)
    mat[r[ok].to_numpy(int), c[ok].to_numpy(int)] = lv.loc[ok, "live_composite"].to_numpy(np.float64)
    cov = np.isfinite(mat[P.tier_valid[TARGET_TIER]]).mean()
    print(f"[load] live 設定 composite 已載入,{TARGET_TIER} 層覆蓋率 {cov:.2%}")
    P._real_comp = mat
    return P


def const_slip(P: Panel, value: float) -> np.ndarray:
    return np.full_like(P.RET, value, dtype=P.RET.dtype)


def mask_to_holdings(P: Panel, M: np.ndarray) -> dict:
    out = {}
    for t in range(P.T):
        j = np.where(M[t])[0]
        if len(j):
            out[P.month_s[t]] = [str(s) for s in P.stocks[j]]
    return out


def tier_net(P: Panel, slip: float | None = None) -> tuple:
    M = dual_confirm_mask(P, TARGET_TIER, top_pct=TOP_PCT, source="real")
    S = P.SLIP if slip is None else const_slip(P, slip)
    return evaluate(M, P.RET, S), M


def show(label: str, m: dict, turn: float = np.nan) -> None:
    print(f"{label:<30}{m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}"
          f"{m.get('mdd', np.nan):>9.1f}{m.get('n', 0):>7}"
          f"{turn * 100 if turn == turn else float('nan'):>10.1f}")


def run_verify() -> None:
    print("=" * 92)
    print("面板驗收 — live 設定(2019窗/institutional_gross) @ ADV≥100萬")
    print("=" * 92)
    P = load_liveconfig_panel()
    print(f"面板 {P.T} 月 × {P.S} 檔")
    net, M = tier_net(P)
    n_avg = M.sum(1)[M.sum(1) > 0].mean()
    print(f"平均持股 {n_avg:.1f} 檔")
    print("\n✅ 驗收完成。下一步:--part h1(前置閘;H1 失敗即結案)")


def run_h1(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H1  前置閘(in-sample):live 設定雙確認 @ADV≥100萬")
    print("=" * 92)
    net, M = tier_net(P)
    m = met(net)
    tn = turnover(M)
    print(f"\n{'策略':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show(f"live 設定雙確認 @{TARGET_TIER}", m, tn)
    show("0050 含息買進持有", met(P.bench), 0.0)

    eng = Engine(adv_floor=1e6)
    holdings = mask_to_holdings(P, M)
    L = eng.report_ladder(holdings, f"live 設定雙確認 @{TARGET_TIER}", reps=50)
    s, ew = L["策略"], L["等權母體"]
    pass_sharpe = s["夏普"] > BENCH_SHARPE
    pass_pick = s["CAGR%"] > ew["CAGR%"]
    ok = pass_sharpe and pass_pick
    print(f"\nH1-a 全期夏普 {s['夏普']:.2f} > {BENCH_SHARPE}(0050)  → {'✅' if pass_sharpe else '❌'}")
    print(f"H1-b ①選股階 {s['CAGR%']-ew['CAGR%']:+.2f} pp/年 > 0        → {'✅' if pass_pick else '❌'}")
    print(f"\nH1 前置閘 → {'✅通過,可跑 H2/H3/H4' if ok else '❌未過 —— 依預註冊§3 出口3,結案'}")
    return {"h1": ok, "metrics": m, "ladder": L}


def run_h2(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H2  walk-forward(主假設):與 dual100 H2 同一段 OOS,固定 100萬 層")
    print("=" * 92)
    net, _ = tier_net(P)
    span = slice(WF_MIN_TRAIN, P.T)
    m_fix, m_bh, ex = met_vs(net[span], P.bench[span])
    if ex:
        print(f"⚠ {ex} 個空手月 —— 已對齊共同月份比較。")
    print(f"\n{'':<30}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    show("H2  live 設定 OOS(固定100萬層)", m_fix)
    show(f"  └ 0050(同段 {m_bh.get('n',0)} 月)", m_bh, 0.0)
    h2 = (m_fix.get("sharpe", -9) > m_bh.get("sharpe", 9)) and \
         (m_fix.get("cagr", -9) > m_bh.get("cagr", 9))
    print(f"\nH2 OOS 夏普且 CAGR 勝 0050 → {'✅通過' if h2 else '❌否定'}")
    return {"h2": h2}


def run_h3(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H3  滑價敏感度")
    print("=" * 92)
    print(f"\n{'來回滑價%':<12}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'vs 0050':>10}")
    out = {}
    for s in SLIP_GRID:
        m = met(tier_net(P, slip=s)[0])
        out[s] = m
        mark = "✅" if m.get("sharpe", -9) > BENCH_SHARPE else "❌"
        print(f"{s:<12.2f}{m.get('cagr',np.nan):>9.2f}{m.get('sharpe',np.nan):>8.2f}"
              f"{m.get('mdd',np.nan):>9.1f}{mark:>10}")
    xs = np.array(SLIP_GRID)
    ys = np.array([out[s].get("sharpe", np.nan) for s in SLIP_GRID])
    be = np.nan
    for i in range(len(xs) - 1):
        if ys[i] > BENCH_SHARPE >= ys[i + 1]:
            be = xs[i] + (ys[i] - BENCH_SHARPE) / (ys[i] - ys[i + 1]) * (xs[i + 1] - xs[i])
            break
    ok = out[SLIP_PASS].get("sharpe", -9) > BENCH_SHARPE
    print(f"\n損益兩平滑價 ≈ {be:.2f}%")
    print(f"H3 滑價 {SLIP_PASS}% 時夏普 > {BENCH_SHARPE} → {'✅通過' if ok else '❌否定'}")
    return {"h3": ok, "breakeven": float(be)}


def run_h4(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H4  六時代穩健")
    print("=" * 92)
    net, M = tier_net(P)
    eng = Engine(adv_floor=1e6)
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
    print(f"H4 → {'✅通過' if ok else '❌否定'}")
    return {"h4": ok, "win_ew": win_ew, "win_bh": win_bh}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="verify",
                    choices=["verify", "h1", "h2", "h3", "h4", "all"])
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    if a.part == "verify":
        run_verify()
        return

    t0 = time.time()
    print("建面板(live 設定)…", flush=True)
    P = load_liveconfig_panel()
    print(f"面板 {P.T} 月 × {P.S} 檔 ({time.time()-t0:.0f}s)")

    res = {}
    if a.part in ("h1", "all"):
        res.update(run_h1(P))
        if a.part == "all" and not res.get("h1"):
            print("\n" + "=" * 92)
            print("H1 前置閘未過 → 依預註冊§3 出口3,結案。不執行 H2~H4。")
            print("=" * 92)
            return
    if a.part in ("h2", "all"):
        res.update(run_h2(P))
    if a.part in ("h3", "all"):
        res.update(run_h3(P))
    if a.part in ("h4", "all"):
        res.update(run_h4(P))

    if a.part == "all":
        print("\n" + "=" * 92)
        print("預註冊判定總表(docs/預註冊_Live設定驗證.md)")
        print("=" * 92)
        for k, lab in [("h1", "H1  前置閘"), ("h2", "H2  walk-forward(主)"),
                       ("h3", "H3  滑價穩健"), ("h4", "H4  時代穩健")]:
            v = res.get(k)
            print(f"{lab:<26}{'✅通過' if v else '❌否定' if v is not None else '—'}")
        print("\n結果(不論正負)請寫進 docs/預註冊_Live設定驗證.md §6。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
