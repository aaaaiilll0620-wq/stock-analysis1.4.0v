# -*- coding: utf-8 -*-
"""build_realbody_scores.py — B全循環:對 obs_alpha 母體逐月跑 App 真身五面綜合分。
================================================================================
對 obs_alpha 的每個 (stock_id, as_of)(listed_ok & adv20 過濾),用回測版 bundle 跑真身
score_row → 真實綜合分。輸出面板供後續組 dual 持股、餵誠實引擎、對 proxy/0050 比。

蘋果對蘋果:跑在 obs_alpha 相同 stock-months(同母體、同 fwd),真身 vs proxy 直接可比。
效能:每檔 bundle 只建一次,對其所有 as_of 逐一評分。

用法:python -m beat_0050.realbody.build_realbody_scores --year 2023       # 驗證單年
      python -m beat_0050.realbody.build_realbody_scores                   # 全循環 2005-2026
      (--limit N 只跑前 N 檔;--out 指定輸出)
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 只匯入純資料常數(honest_backtest 頂層僅 numpy/pandas,不碰 core → 無網路)。
# 歷史原因:core.data_provider 的 class-body `_api = DataLoader()` 會讓 bt_bundle /
# core.score_store 在**匯入時**觸發 FinMind 登入(Codex 第二輪第 1 點),當時以 lazy import 止血。
# 根因已於 2026-07-31 修掉(`DataProvider._get_api()` 延遲建立,見 tests/test_import_hygiene.py),
# 此處的 lazy import 保留:仍可省下 worker 外的 SDK 匯入成本,且是防呆的第二道。
from beat_0050.honest_backtest import OBS_ALPHA

RB_DIR = Path(__file__).resolve().parents[2] / "data" / "research_base"
OUT_DEFAULT = RB_DIR / "realbody_scores.parquet"     # ADV≥2000萬 那份的正規路徑
ADV_FLOOR = 2e7                                       # 預設門檻 (可用 --adv-floor 覆寫)
MODE = "balanced"
COV_MIN = 0.99      # **探索模式**的放寬下限(不是預設)。--min-coverage 預設已改 1.0(零靜默損失);
                    # 要容忍已知合法缺口才顯式傳 --min-coverage 0.99。低於門檻一律不落正規檔名。


def out_path_for(adv_floor: float) -> Path:
    """非預設門檻一律寫到帶後綴的新檔 —— 不覆蓋既有的 realbody_scores.parquet。
    那份跑了數小時,build 中途失敗或評分邏輯有變時,舊檔是唯一的退路。"""
    if abs(adv_floor - ADV_FLOOR) < 1:
        return OUT_DEFAULT
    return RB_DIR / f"realbody_scores_adv{int(adv_floor / 1e4)}w.parquet"


def assert_obs_unique(obs) -> None:
    """輸入母體 (stock_id, as_of) 唯一性硬檢查(Codex 第五輪)。

    tasks 用 `sorted(set(as_of))` 建,會**靜默去重**輸入的重複 (stock_id, as_of)。
    若 obs_alpha 有重複鍵,`expected` 會被低估 → 即使實際少算資料,coverage 仍可能假性 100%。
    所以在算 `expected` **之前**就 raise,重複 = 上游 build 的 bug,不靠 set() 掩蓋。
    """
    dup = obs.duplicated(["stock_id", "as_of"], keep=False)
    if dup.any():
        raise SystemExit(
            f"❌ 輸入母體 obs_alpha(過濾後)有 {int(dup.sum())} 列重複鍵 (stock_id, as_of),例:"
            f"{obs.loc[dup, ['stock_id', 'as_of']].head(5).to_dict('records')}。\n"
            "sorted(set(as_of)) 會把它們靜默去重、低估 expected,讓覆蓋率假性 100%。\n"
            "這是 obs_alpha 的 build 問題(scripts/alpha_gate_lab.py --build)—— 修上游,不要在此去重。")


def _atomic_write_parquet(df, path: Path) -> None:
    """原子寫入:同目錄 .tmp → os.replace。中斷不會留半截檔;正規面板永遠是完整或不存在。"""
    import os
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _is_canonical_name(path: Path) -> bool:
    """這個檔名會被 lab_paths.available_realbody_panels() 撿成『正規完整面板』嗎?
    = `realbody_scores.parquet` 或 `realbody_scores_adv<N>w.parquet`。
    與 lab_paths 的 glob 規則對齊,是局部跑禁止覆寫的判準。"""
    name = path.name
    if name == OUT_DEFAULT.name:
        return True
    stem = path.stem
    if stem.startswith("realbody_scores_adv") and stem.endswith("w"):
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
    from core.score_store import _engines          # lazy:worker 內才拉 core(避免匯入即登入)
    from core.data_provider import DataProvider
    # fail-closed 閘門(Codex 第一輪審查 §三-1):產業別對照表是研究建置路徑上唯一會碰 FinMind
    # 的地方,而它下游有四層連續吞錯,終點會**靜默**改變 f_fund(金融股豁免全失效)。
    # 研究建置不接受靜默降級 → 顯式 strict=True,取不到就讓這個 worker 直接死掉。
    # 註:快取新鮮(<30 天)時這行只是讀 JSON,不連網。
    DataProvider._ensure_industry_map(strict=True)
    _ENG = _engines(MODE)


def _score_stock(task):
    """(sid, [as_of...]) → (rows, fails);每檔 bundle 只建一次,對其所有 as_of 評分。

    **不再靜默回 []**(審查官第 2 點):抓不到 bundle / 評分失敗的 stock-month 會
    連同原因記到 `fails`,由 main() 匯總成對帳報告。

    缺失原因分三類(Codex 第二輪第 4 點:別把 bug 和資料缺口混為一談):
      · `bundle`      —— 整支股票抓不到歷史(fetch 例外)
      · `no_data`     —— score_row 乾淨回 None,即 build_pit_stockdata 判定該 stock-month
                         無足夠資料。**這是預期中的資料缺口**,不是錯誤。
      · `score_error` —— 評分管線**丟出例外**(strict=True 讓 score_row re-raise)。
                         這是真正的程式/資料異常,記下完整型別+訊息;若某型別在報告裡成群出現,
                         就是系統性 bug 的信號,不會被當成零星資料缺口稀釋掉。
    """
    from beat_0050.realbody.bt_bundle import bt_fetch_history   # lazy(見 _init_worker)
    from core.score_store import score_row
    sid, asofs = task
    try:
        bundle = bt_fetch_history(sid)
    except Exception as e:
        # 整支股票沒了 —— 記成該股全部 as_of 的缺失,而不是回一個空 list 就算了。
        return [], [{"stock_id": sid, "as_of": a, "reason": "bundle",
                     "err": f"{type(e).__name__}: {e}"[:200]} for a in asofs]
    out, fails = [], []
    for asof in asofs:
        reason, err = None, ""
        try:
            # strict=True:資料不足 → 乾淨回 None(no_data);評分丟例外 → 往上拋(score_error)。
            r = score_row(bundle, asof, MODE, _ENG, strict=True)
            if r is None:
                reason, err = "no_data", "build_pit_stockdata 判定資料不足(預期缺口)"
        except Exception as e:
            r, reason, err = None, "score_error", f"{type(e).__name__}: {e}"[:200]
        if r and r.get("composite") is not None:
            out.append({"as_of": asof, "stock_id": sid,
                        "real_composite": r.get("composite"), "rating": r.get("rating"),
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
    ap.add_argument("--allow-score-errors", action="store_true",
                    help="容許 score_error(評分管線例外)不致命。預設關 —— 例外是 bug 信號,"
                         "不論覆蓋率模式都應終止,除非已確認純屬資料異常而非程式錯誤。")
    ap.add_argument("--min-coverage", type=float, default=1.0,
                    help="覆蓋率致命下限,**預設 1.0 = 零靜默損失**(Codex 第二輪第 3 點:正規面板"
                         f"預設就該零缺;現有兩份實測 100%)。低於此不落正規檔名並 exit。放寬到"
                         f" {COV_MIN}(探索模式)須顯式傳 --min-coverage {COV_MIN},用於『某股某期本來"
                         "就沒財報』這類已知合法缺口 —— 缺哪些一律列在對帳報告,永不靜默。")
    args = ap.parse_args()
    adv_floor = float(args.adv_floor)
    cov_min = float(args.min_coverage)
    # --year / --limit 是驗證用的**局部**跑法,產出不是完整面板。原本它們會寫進正規檔名,
    # 把跑了數小時的那份覆蓋成一小塊(out_path_for 的 docstring 只防了 --adv-floor 這條路)。
    # 一律改寫到 _partial 後綴 —— resolve_realbody() 不認這個名字,撿不到半成品。
    partial = bool(args.year or args.limit)
    if not args.out:
        p = out_path_for(adv_floor)
        args.out = str(p.with_name(p.stem + "_partial.parquet") if partial else p)
    else:
        args.out = str(args.out)
        # Codex 審查點 2:局部跑就算**明寫** `--out realbody_scores.parquet` 也不准落在正規檔名上。
        # 前一版只在「沒給 --out」時加 _partial,`--year 2023 --out <正規名>` 仍會覆蓋完整面板。
        # 正規名 = resolve_realbody()/available_realbody_panels() 會撿的名字,一律強制轉 _partial。
        if partial and _is_canonical_name(Path(args.out)):
            safe = Path(args.out).with_name(Path(args.out).stem + "_partial.parquet")
            print(f"[build] ⚠ 局部跑(--year/--limit)不得寫正規檔名 {Path(args.out).name};"
                  f"強制改寫 {safe.name}(resolve_realbody 不會撿到它)")
            args.out = str(safe)
    if partial:
        print(f"[build] --year/--limit 局部跑 → 寫到 {Path(args.out).name}(不覆蓋正規面板)")

    obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "adv20", "listed_ok"])
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= adv_floor)].copy()  # noqa: E712
    obs["as_of"] = obs["as_of"].astype(str)
    obs["stock_id"] = obs["stock_id"].astype(str)
    assert_obs_unique(obs)     # 算 expected 前先擋輸入重複鍵(見該函式)
    print(f"[build] ADV≥{adv_floor:,.0f} → {len(obs):,} stock-months, "
          f"{obs['stock_id'].nunique()} 檔 → {args.out}", flush=True)
    if args.year:
        obs = obs[obs["as_of"].str.startswith(str(args.year))]
    stocks = sorted(obs["stock_id"].unique())
    if args.limit:
        stocks = stocks[:args.limit]
    # 已驗證無重複,set() 只是為了排序/型別,不再承擔去重責任。
    asof_by_stock = obs.groupby("stock_id")["as_of"].apply(lambda s: sorted(set(s)))

    tasks = [(sid, asof_by_stock.get(sid, [])) for sid in stocks]
    expected = int(sum(len(a) for _, a in tasks))     # 應該產出的 stock-month 數(對帳基準)
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

    # ------------------------------------------------------------------
    # 建置對帳(審查官第 2 點:「數字正常但母體被砍」)
    # 期望 stock-month vs 實際產出,逐原因列出缺口,並把明細落地成 sidecar。
    # 覆蓋率不足 → 寫成 `.INCOMPLETE.parquet`,**不佔用正規檔名**:
    # resolve_realbody() 只認正規命名,所以半成品不可能被 lab 靜默讀成完整面板。
    # ------------------------------------------------------------------
    # Codex 審查點 3:不能用 drop_duplicates 算覆蓋率來『掩蓋』重複列 —— 那會讓 got 看起來
    # 剛好等於 expected(cov 正常),但寫出的 out 仍帶重複鍵,下游 Panel 才炸。
    # 建置端就硬檢查:重複鍵 = 上游邏輯有 bug,直接 raise,不落地半成品。
    # (現行 tasks 依 sorted(set(asof)) × 唯一 stock 產生,結構上不會有重複;這是防未來改壞。)
    if len(out):
        dup = out.duplicated(["stock_id", "as_of"], keep=False)
        if dup.any():
            raise SystemExit(
                f"❌ 建置輸出有 {int(dup.sum())} 列重複鍵 (stock_id, as_of),例:"
                f"{out.loc[dup, ['stock_id', 'as_of']].head(5).to_dict('records')}。\n"
                "這是評分迴圈的 bug(同一 stock-month 被算兩次),不是資料缺口 —— "
                "修 _score_stock / tasks 建構,不要靠去重掩蓋。")
    got = len(out) if len(out) else 0        # 已保證無重複,直接用列數
    cov = got / expected if expected else 0.0
    fdf = pd.DataFrame(fails, columns=["stock_id", "as_of", "reason", "err"])
    # score_error = 評分管線丟出的**真實例外**(不是資料缺口)。它是 bug 信號,不論覆蓋率模式
    # 都不該被吸收成缺失列後繼續產結論(Codex 第三輪第 2 點)。預設致命,除非顯式 --allow-score-errors。
    n_score_err = int((fdf["reason"] == "score_error").sum()) if len(fdf) else 0
    report = {"adv_floor": adv_floor, "expected_stock_months": expected,
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

    # ------------------------------------------------------------------
    # 兩件事**分開**判定(Codex 第四輪第 2 點:檔名隔離):
    #   canonical_ok —— 能不能佔用正規檔名。**只有完美**(cov==1.0 且 0 個 score_error)才行,
    #                   與 --min-coverage / --allow-score-errors 無關。任何瑕疵一律寫非正規名,
    #                   正式資料目錄永遠不會被半成品/探索面板污染。
    #   run_failed   —— 這次跑算不算失敗(退非零)。由門檻旗標決定:探索模式可以「成功」收工,
    #                   但它的產物仍在非正規名下,resolve_realbody() 撿不到。
    # ------------------------------------------------------------------
    fatal_errs = n_score_err > 0 and not args.allow_score_errors
    run_failed = (cov < cov_min) or fatal_errs
    canonical_ok = (cov >= 1.0) and (n_score_err == 0)
    report["canonical_name_used"] = canonical_ok
    if not canonical_ok and not run_failed:
        # 探索模式:過了(放寬的)門檻,但非完美 → 仍不給正規名。
        print(f"⚠ 非完美建置(覆蓋率 {cov:.4%}、score_error {n_score_err})但通過放寬門檻 "
              f"{cov_min:.2%} —— 一律寫**非正規檔名**,正式面板不受污染;要當正式面板必須零缺零錯。")
    out_path = Path(args.out)
    if not canonical_ok:
        suffix = ".INCOMPLETE.parquet" if run_failed else ".EXPLORE.parquet"
        out_path = out_path.with_suffix(suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 原子寫入(Codex 第二輪結尾):先寫 .tmp 再 os.replace —— 建置中斷/當機不會留下半截的
    # 正規面板讓 lab 讀到。os.replace 在同一檔案系統上是原子的。
    _atomic_write_parquet(out, out_path)
    if len(fdf):
        _atomic_write_parquet(fdf, out_path.with_name(out_path.stem + "_missing.parquet"))
    Path(out_path.with_name(out_path.stem + "_report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    mark = "✅" if canonical_ok else ("❌" if run_failed else "⚠️")
    print(f"\n{mark} {len(out)} 列 "
          f"({out['stock_id'].nunique() if len(out) else 0} 檔 × "
          f"{out['as_of'].nunique() if len(out) else 0} 月), {el:.0f}s → {out_path}")
    print(f"   {'正規面板' if canonical_ok else '非正規名(resolve_realbody 不會撿到)'}"
          f";對帳報告 → {out_path.with_name(out_path.stem + '_report.json')}")
    if len(out):
        print(f"real_composite: 中位 {out['real_composite'].median():.1f}, "
              f"範圍 {out['real_composite'].min():.1f}~{out['real_composite'].max():.1f}")
        print("評級分布:", out["rating"].value_counts().to_dict())
    if run_failed:
        why = []
        if cov < cov_min:
            why.append(f"覆蓋率 {cov:.2%} < {cov_min:.2%}")
        if fatal_errs:
            why.append(f"{n_score_err} 個 score_error(評分 bug,非資料缺口;"
                       "確認是資料而非程式問題才用 --allow-score-errors)")
        raise SystemExit(
            f"\n❌ 建置未過:{' 且 '.join(why)} —— 已寫成 {out_path.name}(非正規檔名,"
            f"resolve_realbody() 不會撿到它)。\n"
            f"明細見 {out_path.stem}_missing.parquet。修好再重跑;不要手動改名成正規檔名。")


if __name__ == "__main__":
    main()
