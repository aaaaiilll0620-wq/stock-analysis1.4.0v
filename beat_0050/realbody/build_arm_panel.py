# -*- coding: utf-8 -*-
"""build_arm_panel.py — FaceRedesignV2 **第一批 candidate arm 的面板建置器**
================================================================================
預註冊:`docs/預註冊_FaceRedesignV2_草案.md`(**2026-08-01 凍結**,基準 commit `4164993`)。
本檔只**執行**該文件 §4 寫死的 arm 定義,不重新決定任何規格。

**凍結的 §8 執行順序第 1–2 步**:
  1. 建新 runner —— **獨立檔案**,不改 `dual100_lab.py` 的 V0 定義(本檔);
  2. 每個 arm 各建一份面板 —— **獨立檔名、獨立目錄,不覆寫 V0,不進 canonical glob**。

## 本檔實作的 arm(A 層,資料定義修正)

| arm | 唯一變更 | 實作機制 |
|---|---|---|
| `v0` | 無(**自檢用**) | 什麼都不注入 → 必須與 V0 面板逐列相同 |
| `A1` | 補 0050 歷史 → **只讓 RS 在 2005-2018 生效** | 注入 `core.backtest._rs_bench_bundle` |
| `A2` | 補 0050 歷史 → **只讓 regime 在 2005-2018 生效** | 注入 `core.score_store._bench_state` |

**A1/A2 的隔離是「拼接資料源 + 單一消費端注入」**(預註冊 §4 A 層):
`core/scoring_manager.py` / `core/advisor.py` / `core/regime.py` / `core/backtest.py`
**一行不改、旗標一個不翻**。兩個消費端各有自己的模組級 lazy 全域,所以可以只注入一個。

> A3(缺值語意中性化)與 A4(f_val 配方統一)**不在本檔** —— 它們需要在
> `core/backtest.py` / `core/valuation.py` 加 arm 旗標(預註冊 §4-1 / §4-2 的變更範圍
> 本來就落在那兩個函式內),屬於「要動生產檔案」的類別,另立 runner 並另行驗收。

## 硬性驗收閘門(不過就 `SystemExit`,不寫檔)

1. **覆蓋率**:產出列數必須等於 V0 面板的同一批 `(stock_id, as_of)`,缺一列即失敗;
2. **`--arm v0` 必須與 V0 面板逐列相同**(`|Δ| ≤ 0.01`)—— 這是證明 runner 忠實的唯一方法;
3. **A1/A2 的足跡必須符合預註冊的邊界污染窗**:
   `as_of ≥ 2019-08-31`(主 OOS 時鐘)的列**必須與 V0 完全相同**。
   若 OOS 段出現差異 → 注入洩漏到了另一個消費端,是 bug,不是研究結果;
4. **A1/A2 在 2005-2018 必須真的改變了某些列** —— 一個「什麼都沒改」的 arm
   在 Gate 1 會被 `EPS_SD` 守衛判成「與 V0 無差異」,那代表注入沒生效。

## 明確不做

不跑 OOS、不算 IC、不算任何績效指標、不下策略結論。本檔只產出**分數面板**。
Gate 1/2/3/4 的判定另由 `scripts/gate1_delta_ic_maxt.py` 等凍結實作處理。

用法:
    python -m beat_0050.realbody.build_arm_panel --arm v0 --limit 8    # runner 忠實度自檢
    python -m beat_0050.realbody.build_arm_panel --arm A1 --limit 8    # arm 冒煙
    python -m beat_0050.realbody.build_arm_panel --arm A1              # 全循環(約 80 分鐘)
================================================================================
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BUILDER_VERSION = "arm-1.0"
MODE = "balanced"
PROJ = Path(__file__).resolve().parents[2]
RB_DIR = PROJ / "data" / "research_base"
ARM_DIR = RB_DIR / "arms"                 # 獨立目錄,與 diag/ 及 canonical 面板都分開
ADV_FLOOR = 1e6
PREREG_FREEZE_COMMIT = "4164993"          # 預註冊凍結的基準 commit

# 拼接基準序列(預註冊 §4 A 層寫死):repo 全史 < 接縫 ⊕ 生產快取 ≥ 接縫
FULL_0050 = PROJ / "beat_0050" / "data" / "benchmark" / "0050_raw.parquet"
SEAM = "2019-01-02"
# 主 OOS 時鐘的起點 —— 驗收閘門 3 用它切「必須與 V0 相同」的那一段
OOS_LO = "2019-08-31"

FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
FACE2KEY = {"f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
            "f_mom": "momentum", "f_whale": "whale"}
ARMS = ("v0", "A1", "A2", "A3", "A4")

_ENG = None
_CTX: dict = {}


# ==============================================================================
# 拼接序列(A1/A2 共用同一份)
# ==============================================================================
def spliced_benchmark() -> pd.DataFrame:
    """`S` = repo 全史(date < SEAM)⊕ 生產快取(date ≥ SEAM),再套生產的 `_back_adjust`。

    預註冊 §4 A 層已實測:兩份序列在重疊的 1,827 列上 `close` **逐列相同**
    (max|Δ| = 0.000000),接縫無跳空 → 這是**同一條序列的歷史延長,不是換資料源**。
    """
    from core import data_cache
    from core.backtest import _back_adjust
    cache = data_cache.read_cached("TaiwanStockPrice", "0050")
    if cache is None or cache.empty:
        raise SystemExit("❌ 生產 0050 快取讀不到 —— 先跑 python build_cache.py 0050")
    cache = cache.copy()
    cache["date"] = cache["date"].astype(str)
    repo = pd.read_parquet(FULL_0050)
    repo["date"] = repo["date"].astype(str)

    # 重疊區間必須逐列相同,否則拼接就是換資料源 → 直接拒絕
    ov = repo.merge(cache[["date", "close"]], on="date", suffixes=("_r", "_c"))
    d = (ov["close_r"].astype(float) - ov["close_c"].astype(float)).abs()
    if len(ov) == 0 or float(d.max()) > 1e-9:
        raise SystemExit(
            f"❌ 兩份 0050 在重疊 {len(ov)} 列上不相同(max|Δ|={float(d.max()) if len(ov) else float('nan')})"
            " —— 拼接前提不成立,不得繼續。")

    s = pd.concat([repo.loc[repo["date"] < SEAM, ["date", "close"]],
                   cache.loc[cache["date"] >= SEAM, ["date", "close"]]],
                  ignore_index=True).sort_values("date").reset_index(drop=True)
    return _back_adjust(s)


# ==============================================================================
# arm 注入(**每個 arm 只碰一個消費端**)
# ==============================================================================
def apply_arm(arm: str) -> None:
    """在 worker 內套用 arm。除了指定的那一個模組級全域,什麼都不動。"""
    if arm == "v0":
        return
    # --- A3 / A4:設生產模組的 arm 旗標(預設 None = V0 行為)。**arm 之間不得混合** ---
    if arm in ("A3", "A4"):
        import core.backtest as bt
        from core.valuation import ValuationEngine
        # 互斥設定:一次只有一個 arm 生效,另一個必須明確是 None
        bt.RESEARCH_ARM = "A3" if arm == "A3" else None
        ValuationEngine.RESEARCH_ARM = "A4" if arm == "A4" else None
        return
    S = spliced_benchmark()
    if arm == "A1":
        # RS 消費端:core.backtest.benchmark_trailing_return 的 lazy 全域
        import core.backtest as bt
        bt._rs_bench_bundle = S
        bt._rs_mom_cache.clear()
        # regime 消費端刻意不動 → advisor.current_regime 逐月與 V0 相同
    elif arm == "A2":
        # regime 消費端:core.score_store._regime_at 的 lazy 全域
        import core.score_store as ss
        from core.backtest import HistoryBundle
        ss._bench_state = {"bundle": HistoryBundle(symbol="0050", price=S), "tried": True}
        ss._regime_by_asof.clear()
        # RS 消費端刻意不動 → rs_3m / rs_6m 逐月與 V0 相同
    else:
        raise SystemExit(f"❌ 未知 arm {arm!r};本檔只實作 {ARMS}")


def out_path_for(arm: str, adv_floor: float, partial: str | None) -> Path:
    """arm 面板住 arms/,檔名以 `_arm` 結尾 —— **刻意不符** `realbody_scores_adv*w.parquet`,
    所以 `lab_paths.available_realbody_panels()` 結構上撿不到它(目錄 + 檔名雙保險)。"""
    name = f"arm_{arm}_scores_adv{int(adv_floor / 1e4)}w_arm"
    if partial:
        name += f"_partial_{partial}"
    return ARM_DIR / f"{name}.parquet"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(PROJ), text=True).strip()
    except Exception:
        return "unknown"


# ==============================================================================
# 評分迴圈(與 build_diag_panel._diag_rows 同一套管線,只多了 arm 注入)
# ==============================================================================
def _init_worker(ctx):
    global _ENG, _CTX
    warnings.filterwarnings("ignore")
    from core.score_store import _engines
    from core.data_provider import DataProvider
    # 與 build_realbody_scores / build_diag_panel 同一道 fail-closed 閘門
    DataProvider._ensure_industry_map(strict=True)
    apply_arm(ctx["arm"])              # ← 注入必須在建引擎「之前」,免得引擎快取到 V0 狀態
    _ENG = _engines(MODE)
    _CTX = ctx


def _arm_rows(task):
    from beat_0050.realbody.bt_bundle import bt_fetch_history
    from core.backtest import build_pit_stockdata
    from core.score_store import _regime_at

    sid, asofs = task
    fund, val, scorer, advisor = _ENG
    try:
        bundle = bt_fetch_history(sid)
    except Exception as e:
        return [], [{"stock_id": sid, "as_of": a, "reason": "bundle",
                     "err": f"{type(e).__name__}: {e}"[:200]} for a in asofs]

    out, fails = [], []
    for asof in asofs:
        try:
            stock = build_pit_stockdata(bundle, asof)
        except Exception as e:
            fails.append({"stock_id": sid, "as_of": asof, "reason": "pit_error",
                          "err": f"{type(e).__name__}: {e}"[:200]})
            continue
        if stock is None:
            fails.append({"stock_id": sid, "as_of": asof, "reason": "no_data",
                          "err": "build_pit_stockdata 判定資料不足(預期缺口)"})
            continue
        try:
            fund_res = fund.evaluate(vars(stock))
            val_res = val.evaluate(vars(stock))
            score = scorer.calculate_score(stock)

            f = {"f_fund": float(fund_res.get("total_score")),
                 "f_val": float(val_res.get("valuation_score", 0.0)),
                 "f_tech": float(score.technical_score),
                 "f_mom": float(score.momentum_score),
                 "f_whale": float(score.whale_score)}

            washout, _n = advisor._detect_washout(stock)
            val_override = "資料不足" in val_res.get("valuation_status", "")
            b = {"b_fund": f["f_fund"],
                 "b_val": 50.0 if val_override else f["f_val"],
                 "b_tech": f["f_tech"],
                 "b_mom": f["f_mom"],
                 "b_whale": (min(100.0, max(f["f_whale"], 60.0) + 5.0) if washout
                             else f["f_whale"])}

            regime = _regime_at(asof)
            dyn_on = bool(advisor._bull_stack(stock)
                          and stock.ma20_bias >= advisor.trend_bias_min
                          and stock.rsi >= advisor.lead_rsi_min)

            comp_indep = _indep_composite(b, _CTX["base_w"], regime, dyn_on)

            advisor.current_regime = regime
            advisor.advise(stock, fund_res, val_res, score)   # 權威分數仍由生產 advisor 產出

            out.append({
                "as_of": str(asof), "stock_id": str(sid),
                "real_composite": float(score.total_score), "rating": score.rating,
                **f, **b,
                "regime": regime or "neutral",
                "dyn_weight": bool(dyn_on),
                "val_override": bool(val_override),
                "washout_override": bool(washout),
                "valuation_basis": val_res.get("valuation_basis", ""),
                "composite_indep": comp_indep,
                # arm 專屬的觀測欄位:RS 是否計分(A1 的直接足跡)
                "rs_6m_scored": stock.rs_6m is not None,
                "rs_3m_scored": stock.rs_3m is not None,
                "score_error": "",
            })
        except Exception as e:
            fails.append({"stock_id": sid, "as_of": asof, "reason": "score_error",
                          "err": f"{type(e).__name__}: {e}"[:200]})
    return out, fails


def _indep_composite(b: dict, base_w: dict, regime, dyn_on: bool) -> float:
    """合成算術的獨立重寫(規格 = `core/advisor.py:advise` 的 regime → dyn → 加權三段)。

    ⚠ 這是**自檢欄**,不是權威分數 —— 判斷式(`_bull_stack` / `_detect_washout`)
    仍共用生產 advisor,所以它**不是**研究紀律 §3 的「第二條獨立實作」。
    診斷面板已在 263,928 列上證明這套算術與生產 advisor 逐列相同。
    """
    from core.regime import regime_multipliers
    mult = regime_multipliers(regime) if regime else {k: 1.0 for k in base_w}
    mw = {k: float(v) * float(mult.get(k, 1.0)) for k, v in base_w.items()}
    if dyn_on:
        cut = mw.get("valuation", 0.0) * 0.6
        mw["valuation"] -= cut
        mw["momentum"] = mw.get("momentum", 0.0) + cut * 0.6
        mw["whale"] = mw.get("whale", 0.0) + cut * 0.4
    buckets = {FACE2KEY[c]: b["b_" + c[2:]] for c in FACES}
    wsum = sum(max(0.0, mw.get(k, 0.0)) for k in buckets)
    if wsum <= 0:
        return float("nan")
    return round(sum(buckets[k] * mw.get(k, 0.0) for k in buckets) / wsum, 2)


def _atomic_write_parquet(df, path: Path) -> None:
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


# ==============================================================================
# 驗收閘門
# ==============================================================================
def acceptance(arm: str, got: pd.DataFrame, v0: pd.DataFrame, partial: bool) -> dict:
    """回 report dict;任何硬性條件不過 → 呼叫端 SystemExit(不寫檔)。"""
    rep = {"arm": arm, "partial": partial, "failures": []}
    key = ["as_of", "stock_id"]
    m = got.merge(v0[key + ["real_composite"]], on=key, how="inner",
                  suffixes=("", "_v0"))
    rep["produced"] = int(len(got))
    rep["compared_rows"] = int(len(m))
    if len(m) != len(got):
        rep["failures"].append(f"有 {len(got) - len(m)} 列在 V0 面板裡找不到對應鍵")

    d = (m["real_composite"] - m["real_composite_v0"]).abs()
    same = d <= 0.01
    rep["same_rate"] = float(same.mean()) if len(m) else float("nan")
    rep["max_abs_diff"] = float(d.max()) if len(m) else float("nan")
    rep["changed_rows"] = int((~same).sum())

    # --- 閘門 2:v0 模式必須逐列相同 ---
    if arm == "v0":
        if rep["changed_rows"] != 0:
            rep["failures"].append(
                f"--arm v0 有 {rep['changed_rows']} 列與 V0 面板不同(max|Δ|={rep['max_abs_diff']:.4f})"
                " —— runner 不忠實,任何 arm 結果都不可信")
    elif arm in ("A3", "A4"):
        # A3/A4 全期都改 → **沒有** OOS 必須相同的約束(預註冊 §4-1 / §4-2)。
        # 但仍要求「真的改到東西」,否則旗標沒生效。
        if rep["changed_rows"] == 0:
            rep["failures"].append(
                f"{arm} 一列都沒改到 —— arm 旗標沒生效"
                "(Gate 1 的 EPS_SD 守衛會把它判成『與 V0 無差異』)")
    else:
        # --- 閘門 3:主 OOS 時鐘那一段必須與 V0 完全相同 ---
        oos = m[m["as_of"] >= OOS_LO]
        n_oos_diff = int((~(oos["real_composite"] - oos["real_composite_v0"]).abs().le(0.01)).sum())
        rep["oos_rows"] = int(len(oos))
        rep["oos_changed_rows"] = n_oos_diff
        if n_oos_diff != 0:
            rep["failures"].append(
                f"{arm} 在主 OOS 時鐘({OOS_LO} 起)有 {n_oos_diff} / {len(oos)} 列與 V0 不同"
                " —— 注入洩漏到另一個消費端,是 bug 不是研究結果")
        # --- 閘門 4:2005-2018 必須真的改到東西 ---
        pre = m[m["as_of"] < "2019-01-01"]
        n_pre_diff = int((~(pre["real_composite"] - pre["real_composite_v0"]).abs().le(0.01)).sum())
        rep["pre2019_rows"] = int(len(pre))
        rep["pre2019_changed_rows"] = n_pre_diff
        if len(pre) > 0 and n_pre_diff == 0:
            rep["failures"].append(
                f"{arm} 在 2005-2018 一列都沒改到 —— 注入沒生效"
                "(Gate 1 的 EPS_SD 守衛會把它判成『與 V0 無差異』)")
    # --- 自檢:合成算術重算 vs 生產 advisor(觀測欄,不過只警告不擋)---
    if "composite_indep" in got.columns:
        di = (got["real_composite"] - got["composite_indep"]).abs()
        rep["indep_match_rate"] = float((di <= 0.01).mean())
        rep["indep_max_abs_diff"] = float(di.max())
    rep["passed"] = not rep["failures"]
    return rep


def main():
    from scripts.lab_paths import resolve_realbody
    from core.scoring_manager import ScoringManager
    from core.score_store import _weights_version

    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--adv-floor", type=float, default=ADV_FLOOR)
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 檔(冒煙,寫 _partial)")
    ap.add_argument("--year", type=int, default=None, help="只跑某年(驗證,寫 _partial)")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    t0 = time.time()
    v0_path = resolve_realbody(a.adv_floor)
    v0 = pd.read_parquet(v0_path)
    v0["as_of"] = v0["as_of"].astype(str)
    v0["stock_id"] = v0["stock_id"].astype(str)

    print("=" * 96)
    print(f"build_arm_panel — arm = **{a.arm}**")
    print("=" * 96)
    print(f"預註冊:docs/預註冊_FaceRedesignV2_草案.md(2026-08-01 凍結,基準 commit "
          f"{PREREG_FREEZE_COMMIT})")
    print(f"V0 面板:{v0_path.name}  {len(v0):,} 列 / {v0['as_of'].nunique()} 個 as_of")

    tasks_df = v0[["stock_id", "as_of"]].copy()
    partial = None
    if a.year:
        tasks_df = tasks_df[tasks_df["as_of"].str[:4] == str(a.year)]
        partial = f"year{a.year}"
    if a.limit:
        keep = sorted(tasks_df["stock_id"].unique())[:a.limit]
        tasks_df = tasks_df[tasks_df["stock_id"].isin(keep)]
        partial = (partial + "_" if partial else "") + f"limit{a.limit}"
    expected = len(tasks_df)
    tasks = [(sid, sorted(g["as_of"].tolist()))
             for sid, g in tasks_df.groupby("stock_id")]
    print(f"任務:{len(tasks):,} 檔 / 期望 {expected:,} 列"
          f"{'(局部:' + partial + ')' if partial else '(全循環)'}")

    # ⚠ 五維 composite 權重在 `composite_weights`;`weights` 是三維原始評分權重
    #   (研究紀律裡反覆強調過的那個混淆點),取錯會讓自檢欄變成無意義的數字。
    base_w = dict(ScoringManager.MODES[MODE]["composite_weights"])
    print(f"五維名目權重(composite_weights):{base_w}")
    ctx = {"arm": a.arm, "base_w": base_w}

    # 主行程也套一次 arm,好在單行程模式與 log 裡看到一致狀態
    if a.workers <= 1:
        _init_worker(ctx)
        results = [_arm_rows(t) for t in tasks]
    else:
        from concurrent.futures import ProcessPoolExecutor
        results = []
        with ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker,
                                 initargs=(ctx,)) as ex:
            for i, r in enumerate(ex.map(_arm_rows, tasks), 1):
                results.append(r)
                if i % 200 == 0:
                    print(f"  … {i}/{len(tasks)} 檔  {time.time()-t0:.0f}s", flush=True)

    rows = [r for rs, _ in results for r in rs]
    fails = [f for _, fs in results for f in fs]
    if not rows:
        raise SystemExit("❌ 一列都沒產出")
    got = pd.DataFrame(rows)
    got["as_of"] = got["as_of"].astype(str)
    got["stock_id"] = got["stock_id"].astype(str)
    dup = got.duplicated(subset=["as_of", "stock_id"])
    if dup.any():
        raise SystemExit(f"❌ 輸出有 {int(dup.sum())} 列重複鍵 —— 迴圈的 bug,不要去重掩蓋。")

    got["arm"] = a.arm
    got["weights_version"] = _weights_version(MODE)
    got["builder_version"] = BUILDER_VERSION
    got["code_commit"] = _git_commit()
    got["prereg_freeze_commit"] = PREREG_FREEZE_COMMIT
    got["panel_source"] = v0_path.name
    got["mode"] = MODE
    got["built_at"] = pd.Timestamp.utcnow().isoformat()

    rep = acceptance(a.arm, got, v0, partial is not None)
    rep.update(expected=expected, coverage=len(got) / expected if expected else 0.0,
               n_fails=len(fails), elapsed_sec=round(time.time() - t0, 1),
               v0_panel=v0_path.name, out=str(out_path_for(a.arm, a.adv_floor, partial)))
    if rep["coverage"] < 1.0 and not partial:
        rep["failures"].append(f"覆蓋率 {rep['coverage']:.4%} < 100% —— 全循環不接受靜默缺口")
        rep["passed"] = False

    print("\n" + "-" * 96)
    print(f"產出 {rep['produced']:,} / 期望 {expected:,}   覆蓋率 {rep['coverage']:.4%}"
          f"   失敗 {len(fails)}")
    print(f"vs V0 逐列相同(|Δ|≤0.01):{rep['same_rate']:.4%}   "
          f"max|Δ| {rep['max_abs_diff']:.4f}   改變的列 {rep['changed_rows']:,}")
    if "indep_match_rate" in rep:
        print(f"合成算術重算 vs advisor(自檢):{rep['indep_match_rate']:.4%}   "
              f"max {rep['indep_max_abs_diff']:.4f}")
    if a.arm in ("A1", "A2"):
        print(f"  主 OOS 時鐘({OOS_LO} 起)改變的列:{rep['oos_changed_rows']} / "
              f"{rep['oos_rows']:,}   ← 必須是 0")
        print(f"  2005-2018 改變的列:{rep['pre2019_changed_rows']:,} / "
              f"{rep['pre2019_rows']:,}   ← 必須 > 0")
        if "rs_6m_scored" in got.columns:
            pre = got[got["as_of"] < "2019-01-01"]
            print(f"  (觀測)2005-2018 的 rs_6m 有計分比例:"
                  f"{pre['rs_6m_scored'].mean():.2%}")
    if fails:
        by = pd.Series([f["reason"] for f in fails]).value_counts().to_dict()
        print(f"  失敗原因分布:{by}")

    if not rep["passed"]:
        print("\n" + "=" * 96)
        for msg in rep["failures"]:
            print(f"❌ {msg}")
        print("=" * 96)
        raise SystemExit("❌ 驗收未過 —— **不寫檔**。上面的差異是 bug 信號,不是研究結果。")

    out = out_path_for(a.arm, a.adv_floor, partial)
    _atomic_write_parquet(got, out)
    out.with_name(out.stem + "_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 驗收通過 → {out}")
    print(f"   report → {out.with_name(out.stem + '_report.json').name}")
    print(f"   耗時 {rep['elapsed_sec']:.0f}s")


if __name__ == "__main__":
    main()
