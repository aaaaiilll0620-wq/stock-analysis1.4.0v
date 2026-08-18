# -*- coding: utf-8 -*-
"""build_liveconfig_scores.py — 全循環:對 obs_alpha 母體逐月跑「live 設定」五面綜合分。
================================================================================
`beat_0050/realbody/build_realbody_scores.py` 的最小差異分支。**唯一的實質差異**:
`_score_stock` 呼叫 `core.tej_bundle.tej_fetch_history`(vanilla,不 import
`beat_0050.realbody.bt_bundle`),不套研究端的兩個覆寫(估值窗 2004、籌碼源淨額)——
用的是**生產環境當下實際在用**的設定(估值窗 2019、籌碼源 institutional_gross/participation)。

預註冊:`docs/預註冊_Live設定驗證.md`(2026-08-10 凍結)。目的:量「估值窗/籌碼源
只揭露不修」這個裁決,套在**實際在跑的設定**上,單獨拿去驗 H1-H4,通不通得過——
之前只驗過研究設定(`docs/預註冊_雙確認ADV100萬.md`)跟兩者的名單重疊率
(`scripts/live_vs_research_overlap.py`),沒直接驗過 live 設定自己的績效。

⚠ 與 `build_realbody_scores.py` 共用同一套 fail-closed 覆蓋率/score_error/atomic-write
機制,不重寫、不放寬。**本檔絕對不 import `beat_0050.realbody.bt_bundle`**——那個模組
會對 `core.tej_bundle._PCT_HISTORY_START` 做 process-local 全域覆寫,一旦匯入就會把
本檔要測的「live 設定」污染成研究設定。

用法:python scripts/build_liveconfig_scores.py --year 2023        # 驗證單年
      python scripts/build_liveconfig_scores.py                    # 全循環 2005-2026
      python scripts/build_liveconfig_scores.py --adv-floor 1e6     # 對齊 dual100 的 100萬 層
================================================================================
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import warnings
from pathlib import Path
import pandas as pd

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

assert "beat_0050.realbody.bt_bundle" not in sys.modules, \
    "bt_bundle 已被匯入過,本次建置會被研究設定污染 —— 換一個乾淨的 process 再跑。"

# 與 build_realbody_scores.py 同理:lazy import 避免匯入即觸發 FinMind 登入。
from beat_0050.honest_backtest import OBS_ALPHA

RB_DIR = Path(__file__).resolve().parent.parent / "data" / "research_base"
OUT_DEFAULT = RB_DIR / "liveconfig_scores.parquet"
ADV_FLOOR = 2e7
MODE = "balanced"
COV_MIN = 0.99


def out_path_for(adv_floor: float) -> Path:
    if abs(adv_floor - ADV_FLOOR) < 1:
        return OUT_DEFAULT
    return RB_DIR / f"liveconfig_scores_adv{int(adv_floor / 1e4)}w.parquet"


def assert_obs_unique(obs) -> None:
    dup = obs.duplicated(["stock_id", "as_of"], keep=False)
    if dup.any():
        raise SystemExit(
            f"❌ 輸入母體 obs_alpha(過濾後)有 {int(dup.sum())} 列重複鍵 (stock_id, as_of),例:"
            f"{obs.loc[dup, ['stock_id', 'as_of']].head(5).to_dict('records')}。\n"
            "這是 obs_alpha 的 build 問題(scripts/alpha_gate_lab.py --build)—— 修上游,不要在此去重。")


def _atomic_write_parquet(df, path: Path) -> None:
    import os
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _is_canonical_name(path: Path) -> bool:
    name = path.name
    if name == OUT_DEFAULT.name:
        return True
    stem = path.stem
    if stem.startswith("liveconfig_scores_adv") and stem.endswith("w"):
        try:
            float(stem.split("adv")[-1].rstrip("w"))
            return True
        except ValueError:
            return False
    return False

_ENG = None


def _init_worker():
    global _ENG
    warnings.filterwarnings("ignore")
    assert "beat_0050.realbody.bt_bundle" not in sys.modules, \
        "worker process 內 bt_bundle 已被匯入 —— 不應該發生,查 fork 前的 import 狀態。"
    from core.score_store import _engines
    from core.data_provider import DataProvider
    DataProvider._ensure_industry_map(strict=True)
    _ENG = _engines(MODE)


def _score_stock(task):
    """與 build_realbody_scores._score_stock 邏輯逐字相同,唯一差異:
    `tej_fetch_history`(vanilla,live 設定)取代 `bt_fetch_history`(研究設定覆寫)。"""
    from core.tej_bundle import tej_fetch_history   # vanilla —— 不覆寫估值窗/籌碼源
    from core.score_store import score_row
    sid, asofs = task
    try:
        bundle = tej_fetch_history(sid)
    except Exception as e:
        return [], [{"stock_id": sid, "as_of": a, "reason": "bundle",
                     "err": f"{type(e).__name__}: {e}"[:200]} for a in asofs]
    out, fails = [], []
    for asof in asofs:
        reason, err = None, ""
        try:
            r = score_row(bundle, asof, MODE, _ENG, strict=True)
            if r is None:
                reason, err = "no_data", "build_pit_stockdata 判定資料不足(預期缺口)"
        except Exception as e:
            r, reason, err = None, "score_error", f"{type(e).__name__}: {e}"[:200]
        if r and r.get("composite") is not None:
            out.append({"as_of": asof, "stock_id": sid,
                        "live_composite": r.get("composite"), "rating": r.get("rating"),
                        "f_tech": r.get("technical"), "f_mom": r.get("momentum"),
                        "f_whale": r.get("whale"), "f_fund": r.get("fundamental"),
                        "f_val": r.get("valuation")})
        else:
            fails.append({"stock_id": sid, "as_of": asof,
                          "reason": reason or "composite_none", "err": err})
    return out, fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None, help="只跑某年 (驗證用)")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 檔 (驗證用)")
    ap.add_argument("--adv-floor", type=float, default=ADV_FLOOR,
                    help="ADV 門檻 (預設 2e7 = 2000萬);非預設值會寫到帶後綴的新檔")
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--workers", type=int, default=6, help="平行進程數")
    ap.add_argument("--allow-score-errors", action="store_true")
    ap.add_argument("--min-coverage", type=float, default=1.0)
    args = ap.parse_args()
    adv_floor = float(args.adv_floor)
    cov_min = float(args.min_coverage)
    partial = bool(args.year or args.limit)
    if not args.out:
        p = out_path_for(adv_floor)
        args.out = str(p.with_name(p.stem + "_partial.parquet") if partial else p)
    else:
        args.out = str(args.out)
        if partial and _is_canonical_name(Path(args.out)):
            safe = Path(args.out).with_name(Path(args.out).stem + "_partial.parquet")
            print(f"[build] ⚠ 局部跑(--year/--limit)不得寫正規檔名 {Path(args.out).name};"
                  f"強制改寫 {safe.name}")
            args.out = str(safe)
    if partial:
        print(f"[build] --year/--limit 局部跑 → 寫到 {Path(args.out).name}(不覆蓋正規面板)")

    obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "adv20", "listed_ok"])
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= adv_floor)].copy()  # noqa: E712
    obs["as_of"] = obs["as_of"].astype(str)
    obs["stock_id"] = obs["stock_id"].astype(str)
    assert_obs_unique(obs)
    print(f"[build] live 設定 ADV≥{adv_floor:,.0f} → {len(obs):,} stock-months, "
          f"{obs['stock_id'].nunique()} 檔 → {args.out}", flush=True)
    if args.year:
        obs = obs[obs["as_of"].str.startswith(str(args.year))]
    stocks = sorted(obs["stock_id"].unique())
    if args.limit:
        stocks = stocks[:args.limit]
    asof_by_stock = obs.groupby("stock_id")["as_of"].apply(lambda s: sorted(set(s)))

    tasks = [(sid, asof_by_stock.get(sid, [])) for sid in stocks]
    expected = int(sum(len(a) for _, a in tasks))
    rows, fails, t0, done = [], [], time.time(), 0
    from multiprocessing import Pool
    with Pool(args.workers, initializer=_init_worker) as pool:
        for i, (res, fl) in enumerate(pool.imap_unordered(_score_stock, tasks, chunksize=4)):
            rows.extend(res); fails.extend(fl); done += len(res)
            if (i + 1) % 100 == 0:
                el = time.time() - t0
                print(f"  {i+1}/{len(stocks)} 檔, {done} 列, {len(fails)} 缺, {el:.0f}s "
                      f"({done/el:.0f} 列/s, 估剩 ~{(len(stocks)-i-1)/(i+1)*el/60:.0f} 分)", flush=True)

    out = pd.DataFrame(rows)
    el = time.time() - t0

    if len(out):
        dup = out.duplicated(["stock_id", "as_of"], keep=False)
        if dup.any():
            raise SystemExit(
                f"❌ 建置輸出有 {int(dup.sum())} 列重複鍵 (stock_id, as_of) —— "
                "評分迴圈的 bug,不是資料缺口。")
    got = len(out) if len(out) else 0
    cov = got / expected if expected else 0.0
    fdf = pd.DataFrame(fails, columns=["stock_id", "as_of", "reason", "err"])
    n_score_err = int((fdf["reason"] == "score_error").sum()) if len(fdf) else 0
    report = {"config": "live(estval_window=2019, chip=institutional_gross)",
              "adv_floor": adv_floor, "expected_stock_months": expected,
              "produced_stock_months": got, "coverage": round(cov, 6),
              "min_coverage": cov_min, "score_errors": n_score_err,
              "missing": int(expected - got), "elapsed_sec": round(el, 1),
              "by_reason": (fdf["reason"].value_counts().to_dict() if len(fdf) else {}),
              "stocks_fully_missing": (
                  sorted(fdf[fdf.reason == "bundle"]["stock_id"].unique().tolist())[:200]
                  if len(fdf) else []),
              "out": str(args.out)}
    print(f"\n{'='*72}\n建置對帳\n{'='*72}")
    print(f"期望 stock-months {expected:,}   實際產出 {got:,}   覆蓋率 {cov:.4%}   "
          f"缺 {expected - got:,}")
    if len(fdf):
        print(f"缺失原因分布:{report['by_reason']}")
        print(f"整支抓不到 bundle 的股票 {fdf[fdf.reason=='bundle']['stock_id'].nunique()} 檔")
        print("逐年缺失:", fdf["as_of"].astype(str).str[:4].value_counts().sort_index().to_dict())
    if n_score_err:
        print(f"\n❌ 偵測到 {n_score_err} 個 score_error(評分管線丟例外,非資料缺口)。範例:")
        print(fdf[fdf.reason == "score_error"][["stock_id", "as_of", "err"]].head(5).to_string(index=False))

    fatal_errs = n_score_err > 0 and not args.allow_score_errors
    run_failed = (cov < cov_min) or fatal_errs
    canonical_ok = (cov >= 1.0) and (n_score_err == 0)
    report["canonical_name_used"] = canonical_ok
    if not canonical_ok and not run_failed:
        print(f"⚠ 非完美建置(覆蓋率 {cov:.4%}、score_error {n_score_err})但通過放寬門檻 "
              f"{cov_min:.2%} —— 一律寫非正規檔名。")
    out_path = Path(args.out)
    if not canonical_ok:
        suffix = ".INCOMPLETE.parquet" if run_failed else ".EXPLORE.parquet"
        out_path = out_path.with_suffix(suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_parquet(out, out_path)
    if len(fdf):
        _atomic_write_parquet(fdf, out_path.with_name(out_path.stem + "_missing.parquet"))
    Path(out_path.with_name(out_path.stem + "_report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    mark = "✅" if canonical_ok else ("❌" if run_failed else "⚠️")
    print(f"\n{mark} {len(out)} 列 "
          f"({out['stock_id'].nunique() if len(out) else 0} 檔 × "
          f"{out['as_of'].nunique() if len(out) else 0} 月), {el:.0f}s → {out_path}")
    print(f"   {'正規面板' if canonical_ok else '非正規名'}"
          f";對帳報告 → {out_path.with_name(out_path.stem + '_report.json')}")
    if len(out):
        print(f"live_composite: 中位 {out['live_composite'].median():.1f}, "
              f"範圍 {out['live_composite'].min():.1f}~{out['live_composite'].max():.1f}")
        print("評級分布:", out["rating"].value_counts().to_dict())
    if run_failed:
        why = []
        if cov < cov_min:
            why.append(f"覆蓋率 {cov:.2%} < {cov_min:.2%}")
        if fatal_errs:
            why.append(f"{n_score_err} 個 score_error")
        raise SystemExit(f"\n❌ 建置未過:{' 且 '.join(why)} —— 已寫成 {out_path.name}(非正規檔名)。")


if __name__ == "__main__":
    main()
