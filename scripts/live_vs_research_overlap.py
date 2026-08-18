# -*- coding: utf-8 -*-
"""live_vs_research_overlap.py — 量測「研究↔live 三層口徑落差」對雙確認選股名單的實際影響
================================================================================
**這是診斷,不是預註冊驗證**(研究紀律 §2:「診斷可自由跑,但診斷不是結論,不得據以下生產
決策」)。目的:composite_reconcile.py 只證明了「分數差異 100% 可歸因」(差在哪裡),
沒回答「差異大不大」——雙確認是門檻制(Top20%∩Top20%),真正要緊的是分數差會不會讓
股票跨過 20% 那條線,不是分數本身差多少。

比較兩種設定算出來的 composite,在同一批歷史日期、同一個股票母體上,
Top20% 名單的 Jaccard 重疊率:
  · 研究設定:`realbody_scores_adv100w.parquet`(H1-H5 驗證用的真身面板,
    估值窗 2004、籌碼源 institutional_flow 淨額)
  · live 設定:用**未經 bt_bundle 覆寫**的 `core.tej_bundle.tej_fetch_history`
    (即時口徑 = 估值窗 2019、籌碼源預設)+ `core.score_store.score_row()`
    現場重算(純記憶體,不寫任何快取,不動任何生產檔案)

c2 腿**不重算**:c2 的四個因子(value_ind/momentum/high52_prox/revenue_yoy)來自
`high52_lab.Panel` 的 `obs_alpha` 系factor 面板,獨立於 `core.tej_bundle` 的估值窗
與 bt_bundle 的籌碼覆寫,兩設定下 c2 相同(見 `high52_lab.py` import 檢查:未 import
bt_bundle)。本次只測 composite 腿的 Top20% membership 差異,並回報疊加 c2 之後
dual100 交集的 Jaccard。

⚠ **關鍵隔離**:本檔絕對不能 import `beat_0050.realbody.bt_bundle` 或任何會間接
匯入它的模組(`build_realbody_scores`/`composite_reconcile`/`build_arm_panel`/
`build_diag_panel`)——那個模組會對 `core.tej_bundle._PCT_HISTORY_START` 做
process-local 全域覆寫,一旦在本 process 匯入過,後面所有「live 設定」的重算
都會被污染成研究設定。`high52_lab.Panel` 經檢查未匯入 bt_bundle,可安全共用同一 process。

用法:
    python scripts/live_vs_research_overlap.py --dates 4
================================================================================
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ / "beat_0050" / "strategies"))   # high52_lab
sys.path.insert(0, str(PROJ / "beat_0050"))                  # honest_backtest(非必要但一致)
sys.path.insert(0, str(PROJ / "scripts"))                    # lab_paths
sys.path.insert(0, str(PROJ))

assert "beat_0050.realbody.bt_bundle" not in sys.modules, \
    "bt_bundle 已被匯入過,本次量測會被研究設定污染 —— 換一個乾淨的 process 再跑。"

from high52_lab import Panel  # noqa: E402
from core.tej_bundle import tej_fetch_history  # noqa: E402
from core.score_store import _engines, score_row  # noqa: E402

TARGET_TIER = "100萬"
TOP_PCT = 20


def _pct_topk(score: np.ndarray, valid: np.ndarray, top_pct: int) -> np.ndarray:
    """單一橫斷面(1D)版本的 `high52_lab.dual_confirm_mask.topk`,邏輯逐字對齊。"""
    ok = valid & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, kind="stable")
    rk = np.empty_like(order)
    rk[order] = np.arange(1, len(score) + 1)
    kk = max(1, int(ok.sum()) * top_pct // 100)
    return (rk <= kk) & ok


def _c2_topk_for_date(P: Panel, t: int, valid: np.ndarray) -> np.ndarray:
    """逐字沿用 `high52_lab.dual_confirm_mask` 內的 c2 定義,只取單一日期(t)橫斷面。"""
    def pct1(name):
        v = P.F[name][t]
        ok = valid & np.isfinite(v)
        x = np.where(ok, v, -np.inf)
        order = np.argsort(-x, kind="stable")
        rk = np.empty_like(order, dtype=np.float64)
        rk[order] = np.arange(1, len(v) + 1, dtype=np.float64)
        nv = max(1.0, ok.sum())
        return np.where(ok, 100.0 * (1.0 - (rk - 1) / nv), np.nan)

    f, v, h = pct1("revenue_yoy"), pct1("value_ind"), pct1("high52_prox")
    m = pct1("momentum")
    c2 = (v + f + h + (100 - m)) / 4
    return _pct_topk(c2, valid, TOP_PCT)


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    inter = int((a & b).sum())
    union = int((a | b).sum())
    return inter / union if union else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", type=int, default=4, help="等距取幾個歷史日期(在 OOS 段 2010+ 內取)")
    ap.add_argument("--out", default=str(PROJ / "outputs" / "live_vs_research_overlap.csv"))
    a = ap.parse_args()

    print("建研究側面板…")
    P = Panel(realbody_floor=1e6)
    print(f"面板 {P.T} 月 × {P.S} 檔")

    # 只在 OOS 段(dual100 H2 的 2010-01 起)取樣,不含 2005-2009 in-sample 段。
    oos_start = int(np.argmax(P.month_s >= "2010-01-01"))
    idx = np.linspace(oos_start, P.T - 1, a.dates).astype(int)
    dates = [(i, P.month_s[i]) for i in idx]
    print(f"取樣日期:{[d for _, d in dates]}")

    rows = []
    t0 = time.time()
    for t, as_of in dates:
        valid = P.tier_valid[TARGET_TIER][t]
        stock_ids = P.stocks[valid]
        n = len(stock_ids)
        print(f"\n=== {as_of}  母體 {n} 檔 ===", flush=True)

        comp_research = P.REAL_COMP[t]
        comp_live = np.full(P.S, np.nan)
        eng = _engines("balanced")
        for i, sid in enumerate(stock_ids, 1):
            j = np.where(P.stocks == sid)[0][0]
            try:
                bundle = tej_fetch_history(str(sid))
                row = score_row(bundle, as_of, "balanced", eng)
                if row is not None:
                    comp_live[j] = row["composite"]
            except Exception as e:
                print(f"  [{i}/{n}] {sid} 失敗:{type(e).__name__}: {e}")
            if i % 200 == 0:
                el = time.time() - t0
                print(f"  [{i}/{n}] ({el:.0f}s elapsed)", flush=True)

        c2_top = _c2_topk_for_date(P, t, valid)
        comp_research_top = _pct_topk(comp_research, valid, TOP_PCT)
        comp_live_top = _pct_topk(comp_live, valid, TOP_PCT)

        dual_research = comp_research_top & c2_top
        dual_live = comp_live_top & c2_top

        j_comp = jaccard(comp_research_top, comp_live_top)
        j_dual = jaccard(dual_research, dual_live)
        cov_live = float(np.isfinite(comp_live[valid]).mean())
        print(f"  live 端評分覆蓋率 {cov_live:.1%}")
        print(f"  composite Top20% Jaccard = {j_comp:.3f}  "
              f"(研究 {int(comp_research_top.sum())} 檔 / live {int(comp_live_top.sum())} 檔)")
        print(f"  dual100 交集 Jaccard      = {j_dual:.3f}  "
              f"(研究 {int(dual_research.sum())} 檔 / live {int(dual_live.sum())} 檔)")

        rows.append(dict(as_of=as_of, n_universe=n, live_coverage=cov_live,
                         n_research_composite_top=int(comp_research_top.sum()),
                         n_live_composite_top=int(comp_live_top.sum()),
                         jaccard_composite=j_comp,
                         n_research_dual=int(dual_research.sum()),
                         n_live_dual=int(dual_live.sum()),
                         jaccard_dual=j_dual))

    df = pd.DataFrame(rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 92)
    print("彙總(逐日期明細已存 " + a.out + ")")
    print("=" * 92)
    print(df.to_string(index=False))
    print(f"\ncomposite Top20% Jaccard:中位 {df['jaccard_composite'].median():.3f}  "
          f"範圍 {df['jaccard_composite'].min():.3f}~{df['jaccard_composite'].max():.3f}")
    print(f"dual100 交集 Jaccard:     中位 {df['jaccard_dual'].median():.3f}  "
          f"範圍 {df['jaccard_dual'].min():.3f}~{df['jaccard_dual'].max():.3f}")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
