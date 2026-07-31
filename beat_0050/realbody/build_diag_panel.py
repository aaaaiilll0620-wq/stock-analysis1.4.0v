# -*- coding: utf-8 -*-
"""build_diag_panel.py — Phase 1 診斷面板:**只增加觀測欄位,不改任何分數**
================================================================================
Codex 第二輪審查授權的唯一動作(§下一步-Phase 1)。

**做什麼**:對 V0 canonical 面板的同一批 (stock_id, as_of),用同一套計分管線重跑一次,
把「產生那個分數時的狀態」全部記下來 —— 那些狀態目前只存在於 `advisor.advise()` 的區域變數裡,
面板一個都沒存,導致任何合成層歸因都只能反推。

**做完之後多了什麼**(全部是觀測欄位,零個是新分數):

    原始五面      f_fund / f_val / f_tech / f_mom / f_whale     (與 V0 面板相同)
    實際合成bucket b_fund / b_val / b_tech / b_mom / b_whale     ← 新
    regime        regime                                        ← 新
    動態權重       dyn_weight                                    ← 新
    覆寫旗標       val_override / washout_override               ← 新
    資料缺口       data_gaps / n_raw_gaps / pe_missing /         ← 新
                  income_missing / balance_missing / cashflow_missing
    錯誤          score_error                                    ← 新
    版本          weights_version / builder_version /            ← 新
                  code_commit / mode / panel_source / built_at

**硬性約束(逐條對應 Codex 的禁令)**:
  · 輸出**只寫** `data/research_base/diag/`,**永遠不碰** `realbody_scores*.parquet`。
  · 不改五維權重、不改任一面的計分公式、不做百分位/z-score、不改缺值填法。
  · 不跑 OOS、不跑 H1–H5、不下任何策略結論。
  · `real_composite` 由**生產的 `advisor.advise()`** 產出(不是本檔算的),
    本檔額外算的 `composite_indep` 只是**合成算術重算**,用來當逐列自檢。

**驗收閘門**:每一列的 `real_composite` 必須與 V0 canonical 面板**逐列相同**
(`|Δ| ≤ 0.01`)。不同的列會被列出來 —— 那代表面板過期或環境漂移,是 bug 信號,不是診斷結果。

用法:
    python -m beat_0050.realbody.build_diag_panel --limit 20      # 驗證(寫 _partial)
    python -m beat_0050.realbody.build_diag_panel                 # 全循環(數小時)
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

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if hasattr(sys.stdout, "reconfigure"):     # Windows 主控台預設 cp950,壓不住 ⚠ / ✅
    sys.stdout.reconfigure(encoding="utf-8")

BUILDER_VERSION = "diag-1.0"          # 本檔的欄位契約版本;改欄位就要進版
MODE = "balanced"
RB_DIR = Path(__file__).resolve().parents[2] / "data" / "research_base"
DIAG_DIR = RB_DIR / "diag"            # ← Codex 指定的獨立目錄
ADV_FLOOR = 1e6

# 五面 → advisor 的 bucket key(順序固定,寫檔欄序依此)
FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
FACE2KEY = {"f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
            "f_mom": "momentum", "f_whale": "whale"}

_ENG = None
_CTX: dict = {}


def out_path_for(adv_floor: float, partial: str | None) -> Path:
    """診斷面板永遠住 diag/,而且檔名**刻意不符** `realbody_scores_adv*w.parquet` 這個 glob。

    `lab_paths.available_realbody_panels()` 用該 glob 撿正規面板,`resolve_realbody()` 據以解析。
    檔名以 `_diag` 結尾 → glob 不命中 → 診斷面板**結構上不可能**被當成正規面板讀走。
    (目錄隔離是第一道,檔名不符 glob 是第二道。)
    """
    name = f"diag_scores_adv{int(adv_floor / 1e4)}w_diag"
    if partial:
        # 局部跑帶上是哪一種局部(--year 2022 / --limit 8),避免兩次不同的驗證互相覆蓋。
        name += f"_partial_{partial}"
    return DIAG_DIR / f"{name}.parquet"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(RB_DIR.parents[1]), text=True).strip()
    except Exception:
        return "unknown"


def _init_worker(ctx):
    global _ENG, _CTX
    warnings.filterwarnings("ignore")
    from core.score_store import _engines
    from core.data_provider import DataProvider
    # 與 build_realbody_scores 同一道 fail-closed 閘門:產業表拿不到就別開始評分,
    # 否則 is_financial 全 False,金融股的 f_fund 會被靜默壓低。
    DataProvider._ensure_industry_map(strict=True)
    _ENG = _engines(MODE)
    _CTX = ctx


def _published_missing(df, as_of, lag_days: int) -> bool:
    """as_of 當下這個財報資料集有沒有『已公告』的列(重寫 build_pit_stockdata 的 _published)。"""
    if df is None or "date" not in getattr(df, "columns", []):
        return True
    ok = df[pd.to_datetime(df["date"], errors="coerce") + pd.Timedelta(days=lag_days)
            <= pd.to_datetime(as_of)]
    return ok.empty


def _diag_rows(task):
    """(sid, [as_of...]) → (rows, fails)。每檔 bundle 只建一次。"""
    from beat_0050.realbody.bt_bundle import bt_fetch_history
    from core.backtest import build_pit_stockdata, PUBLISH_LAG_DAYS
    from core.score_store import _regime_at, _BUNDLE_GAP_LABELS, _LENS_GAP_LABELS

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

            # ---- 原始五面(= V0 面板存的那五個值)----
            f = {"f_fund": float(fund_res.get("total_score")),
                 "f_val": float(val_res.get("valuation_score", 0.0)),
                 "f_tech": float(score.technical_score),
                 "f_mom": float(score.momentum_score),
                 "f_whale": float(score.whale_score)}

            # ---- advisor 合成時**實際使用**的 bucket(advise:84-102 的規格)----
            washout, _note = advisor._detect_washout(stock)
            val_status = val_res.get("valuation_status", "")
            val_override = "資料不足" in val_status
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

            # ---- 合成算術重算(自檢用;**不是**寫進面板的權威分數)----
            comp_indep = _indep_composite(b, _CTX["base_w"], regime, dyn_on)

            # ---- 權威分數:呼叫生產的 advisor(in-place 覆寫 score)----
            advisor.current_regime = regime
            advisor.advise(stock, fund_res, val_res, score)

            # ---- 資料缺口(與 core.score_store.score_row 同一套標籤)----
            gaps = [lab for fld, lab in _BUNDLE_GAP_LABELS if getattr(bundle, fld, None) is None]
            n_raw = len(gaps)
            gaps += [_LENS_GAP_LABELS.get(m, m) for m in (val_res.get("missing_fields") or [])]

            out.append({
                "as_of": str(asof), "stock_id": str(sid),
                "real_composite": float(score.total_score), "rating": score.rating,
                **f, **b,
                "composite_indep": comp_indep,
                "regime": regime or "neutral",
                "dyn_weight": bool(dyn_on),
                "val_override": bool(val_override),
                "washout_override": bool(washout),
                "valuation_basis": val_res.get("valuation_basis", ""),
                "data_gaps": "；".join(dict.fromkeys(gaps)),
                "n_raw_gaps": int(n_raw),
                "pe_missing": bool(stock.pe_ratio is None),
                "income_missing": _published_missing(bundle.income, asof, PUBLISH_LAG_DAYS),
                "balance_missing": _published_missing(bundle.balance, asof, PUBLISH_LAG_DAYS),
                "cashflow_missing": _published_missing(bundle.cashflow, asof, PUBLISH_LAG_DAYS),
                "score_error": "",
            })
        except Exception as e:
            fails.append({"stock_id": sid, "as_of": asof, "reason": "score_error",
                          "err": f"{type(e).__name__}: {e}"[:200]})
    return out, fails


def _indep_composite(b: dict, base_w: dict, regime, dyn_on: bool) -> float:
    """合成算術的獨立重寫(規格見 core/advisor.py:advise 第 103–120 行)。

    ⚠ 這是**獨立的合成算術重算**,不是研究紀律 §3 的「第二條獨立實作」——
    判斷式(`_bull_stack` / `_detect_washout`)與預測器都共用生產的。用途是逐列自檢。
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


def main():
    from scripts.lab_paths import resolve_realbody
    from core.scoring_manager import ScoringManager
    from core.score_store import _weights_version

    ap = argparse.ArgumentParser()
    ap.add_argument("--adv-floor", type=float, default=ADV_FLOOR)
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 檔(驗證用,寫 _partial)")
    ap.add_argument("--year", type=int, default=None, help="只跑某年(驗證用,寫 _partial)")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    src = resolve_realbody(args.adv_floor)          # V0 canonical 面板 = 母體與驗收基準
    v0 = pd.read_parquet(src, columns=["as_of", "stock_id", "real_composite"] + FACES)
    v0["as_of"] = v0["as_of"].astype(str)
    v0["stock_id"] = v0["stock_id"].astype(str)

    partial = (f"year{args.year}" if args.year else
               (f"limit{args.limit}" if args.limit else None))
    out_path = out_path_for(args.adv_floor, partial)
    print(f"[diag] 母體來源(唯讀):{src}")
    print(f"[diag] 輸出:{out_path}")
    print(f"[diag] ⚠ 本檔**不會**寫入 {RB_DIR}/realbody_scores*.parquet")

    work = v0
    if args.year:
        work = work[work["as_of"].str.startswith(str(args.year))]
    stocks = sorted(work["stock_id"].unique())
    if args.limit:
        stocks = stocks[:args.limit]
        work = work[work["stock_id"].isin(stocks)]
    asof_by_stock = work.groupby("stock_id")["as_of"].apply(lambda s: sorted(set(s)))
    tasks = [(sid, list(asof_by_stock.get(sid, []))) for sid in stocks]
    expected = int(sum(len(a) for _, a in tasks))
    print(f"[diag] {len(stocks)} 檔 / {expected:,} stock-months", flush=True)

    ctx = {"base_w": dict(ScoringManager.MODES[MODE]["composite_weights"])}
    rows, fails, t0 = [], [], time.time()
    from multiprocessing import Pool
    with Pool(args.workers, initializer=_init_worker, initargs=(ctx,)) as pool:
        for i, (res, fl) in enumerate(pool.imap_unordered(_diag_rows, tasks, chunksize=4)):
            rows.extend(res); fails.extend(fl)
            if (i + 1) % 100 == 0:
                el = time.time() - t0
                print(f"  {i+1}/{len(stocks)} 檔, {len(rows):,} 列, {len(fails)} 缺, {el:.0f}s "
                      f"(估剩 ~{(len(stocks)-i-1)/(i+1)*el/60:.0f} 分)", flush=True)

    d = pd.DataFrame(rows)
    el = time.time() - t0
    if d.empty:
        raise SystemExit("❌ 一列都沒產出")

    dup = d.duplicated(["stock_id", "as_of"], keep=False)
    if dup.any():
        raise SystemExit(f"❌ 輸出有 {int(dup.sum())} 列重複鍵 —— 評分迴圈的 bug,不要去重掩蓋。")

    # ---- 版本資訊(逐列;欄位少、值重複,parquet 壓縮後成本可忽略)----
    d["mode"] = MODE
    d["weights_version"] = _weights_version(MODE)
    d["builder_version"] = BUILDER_VERSION
    d["code_commit"] = _git_commit()
    d["panel_source"] = src.name
    d["built_at"] = pd.Timestamp.utcnow().isoformat()

    # ================= 驗收閘門 =================
    m = d.merge(v0, on=["as_of", "stock_id"], how="inner", suffixes=("", "_v0"))
    dv = (m["real_composite"] - m["real_composite_v0"]).abs()
    same = (dv <= 0.01)
    face_ok = {c: bool(((m[c] - m[c + "_v0"]).abs() <= 1e-6).all()) for c in FACES}
    ind = (d["composite_indep"] - d["real_composite"]).abs()

    cov = len(d) / expected if expected else 0.0
    n_score_err = int(sum(1 for f in fails if f.get("reason") == "score_error"))
    n_bad = int((~same).sum())
    n_uncompared = int(len(d) - len(m))
    n_face_bad = [c for c, ok in face_ok.items() if not ok]

    print(f"\n{'='*78}\n驗收\n{'='*78}")
    print(f"產出 {len(d):,} / 期望 {expected:,}  覆蓋率 {cov:.4%}  缺 {expected-len(d):,}")
    if fails:
        print(f"缺失原因:{pd.DataFrame(fails)['reason'].value_counts().to_dict()}")
    print(f"與 V0 面板可比對的列:{len(m):,}(未能比對 {n_uncompared:,})")
    print(f"  real_composite 逐列相同(|Δ|≤0.01):**{same.mean()*100:.4f}%**  max|Δ| {dv.max():.4f}")
    print(f"  五面逐列相同:{face_ok}")
    print(f"  合成算術重算 vs advisor(自檢):|Δ|≤0.01 {(ind <= 0.01).mean()*100:.4f}%  max {ind.max():.4f}")
    if n_bad:
        print(f"\n❌ 有 {n_bad} 列與 V0 不同 —— 那是面板過期/環境漂移的 bug 信號,不是診斷結果。範例:")
        print(m.loc[~same, ["stock_id", "as_of", "real_composite", "real_composite_v0"]]
              .head(10).to_string(index=False))

    # ---- 五道致命條件(任一不過 → 落 .INCOMPLETE 檔名 + 非零退出)----
    #   診斷面板的用途是「解釋 V0」,它只要有一列對不上 V0,就不能拿來解釋 V0。
    #   覆蓋率不足同理:少掉的那些列會讓後續任何比例型統計(regime 佔比、缺值率)失真。
    failures = []
    if cov < 1.0:
        failures.append(f"覆蓋率 {cov:.4%} < 100%(缺 {expected-len(d):,} 列)")
    if n_score_err:
        failures.append(f"{n_score_err} 個 score_error(評分管線例外,非資料缺口)")
    if n_bad:
        failures.append(f"{n_bad} 列 real_composite 與 V0 不符(門檻 |Δ|≤0.01)")
    if n_face_bad:
        failures.append(f"五面與 V0 不符:{n_face_bad}")
    if n_uncompared:
        failures.append(f"{n_uncompared:,} 列無法與 V0 比對(鍵對不上)")

    print(f"\n新增觀測欄位的分布:")
    print(f"  regime          : {d['regime'].value_counts(normalize=True).round(4).to_dict()}")
    print(f"  dyn_weight      : {d['dyn_weight'].mean()*100:.2f}%")
    print(f"  val_override    : {d['val_override'].mean()*100:.2f}%")
    print(f"  washout_override: {d['washout_override'].mean()*100:.2f}%")
    print(f"  pe_missing      : {d['pe_missing'].mean()*100:.2f}%")
    print(f"  三大財報全缺     : {(d['income_missing'] & d['balance_missing'] & d['cashflow_missing']).mean()*100:.2f}%")
    print(f"  有 data_gaps    : {(d['data_gaps'] != '').mean()*100:.2f}%")

    # 未過 → 佔用 .INCOMPLETE 檔名,乾淨的名字留給真正通過的建置(沿用 build_realbody_scores 的慣例)
    if failures:
        out_path = out_path.with_suffix(".INCOMPLETE.parquet")

    _atomic_write_parquet(d, out_path)
    if fails:
        _atomic_write_parquet(pd.DataFrame(fails),
                              out_path.with_name(out_path.stem + "_missing.parquet"))
    report = {"panel_source": src.name, "out": str(out_path), "builder_version": BUILDER_VERSION,
              "code_commit": d["code_commit"].iloc[0], "weights_version": d["weights_version"].iloc[0],
              "expected": expected, "produced": int(len(d)), "coverage": round(cov, 6),
              "compared_rows": int(len(m)), "uncompared_rows": n_uncompared,
              "v0_match_rate": round(float(same.mean()), 6), "v0_max_abs_diff": float(dv.max()),
              "faces_match": face_ok, "score_errors": n_score_err,
              "partial": partial or False, "passed": not failures, "failures": failures,
              "elapsed_sec": round(el, 1),
              "by_reason": (pd.DataFrame(fails)["reason"].value_counts().to_dict() if fails else {})}
    out_path.with_name(out_path.stem + "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'✅' if not failures else '❌'} {len(d):,} 列 → {out_path}  ({el:.0f}s)")
    print(f"   報告 → {out_path.with_name(out_path.stem + '_report.json')}")
    if failures:
        raise SystemExit("❌ 驗收未過:" + " 且 ".join(failures) +
                         f"\n已寫成 {out_path.name}(.INCOMPLETE,不佔用乾淨檔名)。"
                         "\n診斷面板的用途是解釋 V0 —— 有一列對不上就不能拿來解釋 V0。先查原因再用。")


if __name__ == "__main__":
    main()
