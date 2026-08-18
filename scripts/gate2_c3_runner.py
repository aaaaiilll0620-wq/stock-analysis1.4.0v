# -*- coding: utf-8 -*-
"""gate2_c3_runner.py — **C3**(Gate 1 唯一通過者)的 Gate 2 runner。

Gate 1(2026-08-02 執行,`GATE1_EXECUTION_MANIFEST.json`)的結論:12 個 arm 中
**只有 C3 同時通過 G1-a 與 G1-c**,其餘 11 個不進後續績效 Gate。本檔只處理 C3。

**本輪只做 `--preflight-only`。** 不產生 CAGR / Sharpe / MDD / 月報酬 / bootstrap 結果 ——
執行路徑 fail-closed,待 Codex 審查 + 使用者明示授權才解除。

凍結規格(第一批預註冊 §5 Gate 2 / §5-1):
  · 時鐘 80 月 2019-08-01 ~ 2026-03-31、報酬線 `exec_ret.fwd_x`、分數 `real_composite`;
  · **固定 100% 曝險、無 regime overlay**;
  · Gate 2-A `composite alone`(Top-20%,不與 c2 交集):ΔCAGR / ΔSharpe **只報 CI**,
    MDD 只報描述統計,**完全沒有通過條件**;
  · Gate 2-B `composite ∩ c2`(V0 完整策略包):ΔCAGR / ΔSharpe **只報 CI**,
    **唯一通過條件 = OOS MDD ≥ −22.01%**(V0 −17.01% 減 5pp 的風險護欄);
  · bootstrap 一律 import `gate2b_bootstrap.paired_block_bootstrap`,
    `L=12` / `B=10,000` / `seed=20260731`,**不得另寫一份**。

⚠ **命名衝突警告**:Gate 2-B 的 `c2` 是 **V0 完整策略包的第二確認腿**
(`lab_paths.add_c2`,= 產業內估值% / 營收YoY% / 距52週高% / 100−動能% 的平均),
**與 arm `C2`(拿掉 `_dynamic_weights`)完全無關**。兩者同名不同物,
本檔一律把策略腿寫成小寫 `c2`、arm 寫成大寫 `C2`。

用法:
    python -X utf8 scripts/gate2_c3_runner.py --preflight-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for p in (str(_HERE), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---- 凍結的 bootstrap:import,不得另寫 ----
from gate2b_bootstrap import (BLOCK_LEN, N_BOOT, SEED,               # noqa: E402
                              paired_block_bootstrap)
from lab_paths import (REAL_COMP_COL, RET_COL, load_real_panel,      # noqa: E402
                       resolve_realbody)

ARM = "C3"
ARM_DIR = _ROOT / "data" / "research_base" / "arms"
GATE1_DIR = _ROOT / "beat_0050" / "results" / "gate1"
OUT_DIR = _ROOT / "beat_0050" / "results" / "gate2"

CLOCK_LO, CLOCK_HI = "2019-08-01", "2026-03-31"
N_MONTHS_EXPECTED = 80
TOP_PCT = 20

# 凍結的 V0 基準(§1-1 / §1-2,80 月主時鐘)。只作對照,不重算。
V0_BASELINE = {
    "gate2a_composite_alone": {"CAGR_pct": 24.61, "Sharpe": 1.09, "MDD_pct": -22.51,
                               "source": "§1-2 / scripts/v0_composite_alone_baseline.py"},
    "gate2b_composite_int_c2": {"CAGR_pct": 28.00, "Sharpe": 1.34, "MDD_pct": -17.01,
                                "source": "§1-1 / scripts/v0_oos_window_baseline.py"},
}
# Gate 2 唯一保留的通過條件(§5 Gate 2-B):風險護欄,不是「優於 V0」的顯著性要求
MDD_GUARDRAIL_PCT = -22.01

BLOCKER = """\
⏸ Gate 2 **執行路徑 fail-closed** —— 本輪只允許 `--preflight-only`。

Codex 2026-08-02:「請先不要執行 Gate 2 或任何 candidate OOS 績效計算……
完成後回報檔案、測試、preflight 輸出;等 Codex 審查與使用者明示授權才可真正執行。」

而且在 Gate 2 執行**之前**還有一個未結的前置項:第一批預註冊 §8 執行順序的
第 4 步(Train + Validation 定義層診斷)與第 5 步(Validation 初選 → 走查協定)
目前**沒有任何可稽核產物**(見 `gate2_preflight.json` 的 `prereg_s8_audit`)。
§8 把它們排在第 6 步「OOS 只跑一次」之前。

本檔未產生任何 CAGR / Sharpe / MDD / 月報酬 / bootstrap 數字。
"""


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hr(t: str) -> None:
    print("\n" + "-" * 92)
    print(t)
    print("-" * 92)


# ==============================================================================
def audit_prereg_s8() -> dict:
    """**唯讀**稽核:§8 執行順序的第 4/5 步有沒有可稽核產物。缺什麼只報告,不補跑。"""
    rep = {
        "_what": "第一批預註冊 §8 執行順序的產物稽核(唯讀,不補跑)",
        "steps": {},
    }
    rb = _ROOT / "data" / "research_base"

    # step 1-2:runner + 12 個 arm 面板
    panels = sorted(ARM_DIR.glob("arm_*_scores_adv100w_arm.parquet"))
    rep["steps"]["s8_1_runner"] = {
        "required": "獨立 runner,不改 dual100_lab 的 V0 定義",
        "artifact": "beat_0050/realbody/build_arm_panel.py",
        "present": (_ROOT / "beat_0050" / "realbody" / "build_arm_panel.py").exists()}
    rep["steps"]["s8_2_panels"] = {
        "required": "每個 arm 一份獨立面板", "n_found": len(panels), "present": len(panels) >= 12}

    # step 3:Gate 2-A 基準(§1-2)
    rep["steps"]["s8_3_gate2a_baseline"] = {
        "required": "V0 composite-alone 基準已補算",
        "artifact": "scripts/v0_composite_alone_baseline.py + 預註冊 §1-2 凍結數字",
        "present": (_HERE / "v0_composite_alone_baseline.py").exists(),
        "frozen_values": V0_BASELINE["gate2a_composite_alone"]}

    # step 4:Train + Validation 定義層診斷
    diag_hits = []
    for pat in ("*train*", "*Train*", "*validation*", "*Validation*"):
        diag_hits += [str(p.relative_to(_ROOT)).replace("\\", "/")
                      for p in (_ROOT / "beat_0050" / "results").glob(pat)]
    rep["steps"]["s8_4_train_val_diagnostics"] = {
        "required": "Train(2005-01~2014-12,120月)+ Validation(2015-01~2018-12,48月)"
                    "的定義層 in-sample 診斷",
        "artifacts_found": diag_hits,
        "present": bool(diag_hits),
        "note": ("`beat_0050/results/diag_full.log` / `diag_2022.log` 是**診斷面板建置器**"
                 "的 log(建 diag_scores_adv100w_diag.parquet),不是 Train/Validation "
                 "定義層診斷 —— 兩者不可互相充當。")}

    # step 5:Validation 初選 → 走查協定
    wf_scripts = [str(p.relative_to(_ROOT)).replace("\\", "/")
                  for p in _HERE.glob("*walk*")] + \
                 [str(p.relative_to(_ROOT)).replace("\\", "/")
                  for p in (_ROOT / "beat_0050").rglob("*walk*")]
    rep["steps"]["s8_5_validation_select_walkforward"] = {
        "required": ("Validation 初選(arm 初選的唯一依據)→ 走查協定"
                     "(訓練窗≥60月、每12月重估、只用訓練窗內 Gate 1-a 的 t 挑一個 arm、"
                     "其後12月量測、只有落在主時鐘80月內的量測月進判定)"),
        "implementation_found": wf_scripts,
        "artifacts_found": [],
        "present": bool(wf_scripts)}

    # step 6:OOS 只跑一次
    g1 = GATE1_DIR / "GATE1_EXECUTION_MANIFEST.json"
    rep["steps"]["s8_6_oos_once"] = {
        "required": "OOS 只跑一次", "artifact": str(g1.relative_to(_ROOT)).replace("\\", "/"),
        "present": g1.exists(), "executed_at": (
            json.loads(g1.read_text(encoding="utf-8"))["executed_at_start"]
            if g1.exists() else None)}

    missing = [k for k, v in rep["steps"].items() if not v.get("present")]
    rep["missing_steps"] = missing
    rep["ordering_violation"] = bool(
        missing and rep["steps"]["s8_6_oos_once"]["present"]
        and any(k in missing for k in ("s8_4_train_val_diagnostics",
                                       "s8_5_validation_select_walkforward")))
    rep["verdict"] = ("§8 第 4/5 步缺可稽核產物,而第 6 步(OOS)已執行 —— 執行順序未依 §8"
                      if rep["ordering_violation"] else "§8 各步皆有產物")
    return rep


def bind_inputs() -> dict:
    """把 C3 面板 / V0 / Gate 1 execution manifest / provenance overlay 的 hash 綁進 preflight。"""
    c3 = ARM_DIR / f"arm_{ARM}_scores_adv100w_arm.parquet"
    v0 = Path(resolve_realbody(1e6))
    g1man = GATE1_DIR / "GATE1_EXECUTION_MANIFEST.json"
    ovl = GATE1_DIR / "GATE1_PROVENANCE_OVERLAY.json"
    for p in (c3, v0, g1man, ovl):
        if not p.exists():
            raise SystemExit(f"❌ 缺必要輸入:{p}")

    g1 = json.loads(g1man.read_text(encoding="utf-8"))
    return {
        "c3_panel": {"path": str(c3.relative_to(_ROOT)).replace("\\", "/"),
                     "sha256": sha256_file(c3)},
        "v0_panel": {"path": str(v0.relative_to(_ROOT)).replace("\\", "/"),
                     "sha256": sha256_file(v0)},
        "gate1_execution_manifest": {"path": str(g1man.relative_to(_ROOT)).replace("\\", "/"),
                                     "sha256": sha256_file(g1man)},
        "gate1_provenance_overlay": {"path": str(ovl.relative_to(_ROOT)).replace("\\", "/"),
                                     "sha256": sha256_file(ovl)},
        "_gate1": g1,
    }


def verify_c3_is_sole_gate1_passer(g1: dict) -> dict:
    """C3 的資格**從 Gate 1 execution manifest 讀出來**,不寫死在本檔。"""
    arms = g1["arms"]
    passed = [a for a, ok in zip(arms, g1["results"]["passed"]) if ok]
    ok = passed == [ARM]
    return {"arms": arms, "passed_arms": passed, "c3_is_sole_passer": ok,
            "T_star": g1["results"]["G1a"]["T_star"],
            "T_star_ind": g1["results"]["G1c"]["T_star"],
            "source": "GATE1_EXECUTION_MANIFEST.json(不寫死)",
            "failure": None if ok else f"Gate 1 通過者是 {passed},本檔只處理 {ARM}"}


def preflight() -> dict:
    rep: dict = {"arm": ARM, "failures": []}
    rep["inputs"] = bind_inputs()
    g1 = rep["inputs"].pop("_gate1")
    rep["gate1_verdict"] = verify_c3_is_sole_gate1_passer(g1)
    if not rep["gate1_verdict"]["c3_is_sole_passer"]:
        rep["failures"].append(rep["gate1_verdict"]["failure"])

    # ---- 凍結設定 ----
    rep["frozen"] = {
        "clock": [CLOCK_LO, CLOCK_HI], "n_months_expected": N_MONTHS_EXPECTED,
        "return_line": RET_COL, "score_column": REAL_COMP_COL, "top_pct": TOP_PCT,
        "exposure": "固定 100%", "regime_overlay": "無",
        "bootstrap": {"impl": "gate2b_bootstrap.paired_block_bootstrap(import,不另寫)",
                      "block_len_L": BLOCK_LEN, "n_boot_B": N_BOOT, "seed": SEED},
        "v0_baseline": V0_BASELINE,
        "gate2a_pass_condition": "無(描述性面板;ΔCAGR / ΔSharpe 只報 95% CI)",
        "gate2b_pass_condition": f"OOS MDD ≥ {MDD_GUARDRAIL_PCT}%(Gate 2 唯一保留的通過條件)",
    }
    expect = {"RET_COL": (RET_COL, "fwd_x"), "REAL_COMP_COL": (REAL_COMP_COL, "real_composite"),
              "BLOCK_LEN": (BLOCK_LEN, 12), "N_BOOT": (N_BOOT, 10000), "SEED": (SEED, 20260731)}
    bad = {k: v for k, (v, want) in expect.items() if v != want}
    rep["frozen_matches_prereg"] = not bad
    if bad:
        rep["failures"].append(f"凍結參數不符:{bad}")

    # ---- 可用報酬母體(**唯一合法來源**)----
    # ⚠ 不得拿 C3 原始 parquet 的列數當可用樣本(Codex 2026-08-02 §2):
    #   那份面板有分數但不保證有可執行的 `exec_ret.fwd_x`。
    #   合法母體只能由 `load_real_panel(drop_na_ret=True, min_coverage=1.0)` 產生 ——
    #   它是 obs_alpha ⋈ exec_ret ⋈ realbody 的交集,且零靜默損失。
    canon = load_real_panel(adv_floor=1e6, drop_na_ret=True, min_coverage=1.0)
    canon["as_of"] = canon["as_of"].astype(str)
    canon["stock_id"] = canon["stock_id"].astype(str)
    canon = canon[(canon["as_of"] >= CLOCK_LO) & (canon["as_of"] <= CLOCK_HI)]

    c3 = pd.read_parquet(ARM_DIR / f"arm_{ARM}_scores_adv100w_arm.parquet",
                         columns=["as_of", "stock_id", REAL_COMP_COL, "score_error"])
    c3["as_of"] = c3["as_of"].astype(str)
    c3["stock_id"] = c3["stock_id"].astype(str)
    c3w = c3[(c3["as_of"] >= CLOCK_LO) & (c3["as_of"] <= CLOCK_HI)]

    K = ["as_of", "stock_id"]
    ck = set(map(tuple, canon[K].to_numpy()))
    c3k = set(map(tuple, c3w[K].to_numpy()))
    missing = ck - c3k          # canonical 有、C3 沒分數 → 不可接受
    c3_only = c3k - ck          # C3 有分數、但沒有可執行報酬 → 必須揭露並排除

    merged = canon[K].merge(c3w, on=K, how="inner")
    n_months = int(canon["as_of"].nunique())
    rep["return_universe"] = {
        "_what": "唯一合法的可用報酬母體 —— load_real_panel(drop_na_ret=True, min_coverage=1.0)",
        "source": "lab_paths.load_real_panel(adv_floor=1e6, drop_na_ret=True, min_coverage=1.0)",
        "return_line": RET_COL,
        "canonical_keys_in_clock": len(ck),
        "n_months_in_clock": n_months,
        "c3_rows_in_clock_raw_panel": int(len(c3w)),
        "c3_covered_canonical_keys": len(ck & c3k),
        "c3_coverage": (len(ck & c3k) / len(ck)) if ck else 0.0,
        "canonical_keys_missing_c3_score": len(missing),
        "c3_only_rows_without_return_eligibility": len(c3_only),
        "note_excluded": ("這 %d 列有 C3 分數但**沒有可執行的 %s**,不具報酬資格,"
                          "一律排除,不得混入績效樣本。" % (len(c3_only), RET_COL)),
        "merged_rows": int(len(merged)),
        "merged_score_nan": int(merged[REAL_COMP_COL].isna().sum()),
        "duplicate_keys_c3": int(c3.duplicated(K).sum()),
        "score_error": int((c3["score_error"].fillna("").astype(str).str.strip() != "").sum()),
    }
    ru = rep["return_universe"]
    if n_months != N_MONTHS_EXPECTED:
        rep["failures"].append(f"canonical 母體月數 {n_months} != {N_MONTHS_EXPECTED}")
    if missing:
        rep["failures"].append(
            f"canonical 母體有 {len(missing)} 個鍵缺 C3 分數 —— 覆蓋不足不得執行 Gate 2")
    if ru["merged_rows"] != ru["canonical_keys_in_clock"]:
        rep["failures"].append(
            f"逐鍵比對後 {ru['merged_rows']} != canonical {ru['canonical_keys_in_clock']}")
    for k in ("merged_score_nan", "duplicate_keys_c3", "score_error"):
        if ru[k]:
            rep["failures"].append(f"{k} = {ru[k]}")

    # ---- §8 唯讀稽核 ----
    rep["prereg_s8_audit"] = audit_prereg_s8()
    # ⚠ 程序違序必須讓 preflight **失敗**(Codex 2026-08-02 §1)。
    # 否則「有程序違序」會被日後誤讀成「可以執行 Gate 2」—— 這正是靜默失效的形狀。
    if rep["prereg_s8_audit"]["ordering_violation"]:
        rep["failures"].append(
            "§8 執行順序違序:第 4/5 步(Train+Validation 定義層診斷、Validation 初選 → "
            "走查協定)缺可稽核產物,而第 6 步(OOS)已執行。"
            "Gate 2 不得在違序未處置前執行 —— 見 docs/協定偏差_FaceRedesignV2_S8.md。")

    rep["preflight_passed"] = not rep["failures"]
    rep["performance_computed"] = False
    rep["note_no_performance"] = ("本檔 preflight 未計算任何 CAGR / Sharpe / MDD / 月報酬 / "
                                  "bootstrap;未建構任何投組、未讀取報酬線數值。")
    return rep


# ==============================================================================
def run_gate2(*_a, **_k):
    """正式 Gate 2 —— **本輪不可呼叫**。

    解除後的實作契約(供審查):
      · 兩個遮罩都用凍結實作,不另寫:
          Gate 2-A `M = _topk(P, valid, C3_composite)`(Top-20%,不交集 c2);
          Gate 2-B `M = M_A & _topk(P, valid, c2)`,且必須通過
            `v0_composite_alone_baseline` 那道「加回 c2 腿 == high52_lab.dual_confirm_mask」
            的逐格自檢;
      · 月報酬用 `high52_lab.evaluate/met`,固定 100% 曝險、無 regime overlay;
      · ΔCAGR / ΔSharpe 一律走 `paired_block_bootstrap(r_cand, r_v0, met_fn,
        block_len=12, n_boot=10000, seed=20260731)`,**只報 2.5/50/97.5 百分位**;
      · Gate 2-A 無通過條件;Gate 2-B 唯一通過條件 `MDD ≥ −22.01%`,且 MDD **不做 bootstrap**
        (路徑相依,重抽會打散真實回撤路徑)。
    """
    raise SystemExit("❌ run_gate2 本輪不可執行 —— 待 Codex 審查 + 使用者明示授權。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight-only", dest="preflight_only", action="store_true",
                    help="本輪唯一允許的模式:只驗證,不產生任何績效數字")
    a = ap.parse_args()

    t0 = datetime.now(timezone.utc).astimezone()
    print("=" * 92)
    print(f"Gate 2 —— {ARM} runner(Gate 1 唯一通過者)")
    print("=" * 92)
    print(f"開始 : {t0.isoformat()}")
    print(f"命令 : {' '.join([os.path.basename(sys.argv[0])] + sys.argv[1:])}")

    if not a.preflight_only:
        print("\n" + BLOCKER)
        raise SystemExit(2)

    rep = preflight()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "gate2_preflight.json"
    rep["generated_at"] = t0.isoformat()
    rep["runner_sha256"] = sha256_file(Path(__file__).resolve())
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")

    hr("輸入綁定(hash)")
    for k, v in rep["inputs"].items():
        print(f"  {k:<26}{v['sha256'][:16]}…  {v['path']}")

    hr("Gate 1 資格(讀自 execution manifest,不寫死)")
    gv = rep["gate1_verdict"]
    print(f"  通過者 : {gv['passed_arms']}   C3 為唯一通過者 : {gv['c3_is_sole_passer']}")
    print(f"  T* = {gv['T_star']:.6f}   T*_ind = {gv['T_star_ind']:.6f}")

    hr("凍結設定")
    f = rep["frozen"]
    print(f"  時鐘 {f['clock'][0]} ~ {f['clock'][1]}({f['n_months_expected']} 月)  "
          f"報酬線 {f['return_line']}  分數 {f['score_column']}  Top-{f['top_pct']}%")
    print(f"  曝險 {f['exposure']}  regime overlay:{f['regime_overlay']}")
    print(f"  bootstrap L={f['bootstrap']['block_len_L']} B={f['bootstrap']['n_boot_B']:,} "
          f"seed={f['bootstrap']['seed']}  ({f['bootstrap']['impl']})")
    print(f"  Gate 2-A 通過條件 : {f['gate2a_pass_condition']}")
    print(f"  Gate 2-B 通過條件 : {f['gate2b_pass_condition']}")

    hr("可用報酬母體(未計算任何報酬數值)")
    ru = rep["return_universe"]
    print(f"  來源 : {ru['source']}")
    print(f"  canonical 鍵數(時鐘內)     : {ru['canonical_keys_in_clock']:,}"
          f"   月數 {ru['n_months_in_clock']}")
    print(f"  C3 原始面板時鐘內列數        : {ru['c3_rows_in_clock_raw_panel']:,}"
          f"   ← **不是**可用樣本")
    print(f"  C3 覆蓋 canonical            : {ru['c3_covered_canonical_keys']:,}"
          f" / {ru['canonical_keys_in_clock']:,}  = {ru['c3_coverage']:.6f}")
    print(f"  canonical 缺 C3 分數         : {ru['canonical_keys_missing_c3_score']:,}   ← 必須 0")
    print(f"  C3-only(無報酬資格,排除)   : {ru['c3_only_rows_without_return_eligibility']:,}")
    print(f"  逐鍵比對後列數               : {ru['merged_rows']:,}   "
          f"score NaN {ru['merged_score_nan']}  dup {ru['duplicate_keys_c3']}  "
          f"score_error {ru['score_error']}")

    hr("§8 執行順序稽核(唯讀,不補跑)")
    au = rep["prereg_s8_audit"]
    for k, v in au["steps"].items():
        print(f"  {'✅' if v.get('present') else '❌'} {k}")
    print(f"\n  缺少的步驟 : {au['missing_steps']}")
    print(f"  判定       : {au['verdict']}")

    print(f"\npreflight_passed = {rep['preflight_passed']}   "
          f"performance_computed = {rep['performance_computed']}")
    print(f"→ {out}")
    print("\n⚠ 未執行 Gate 2:未產生任何 CAGR / Sharpe / MDD / 月報酬 / bootstrap 數字。")
    if rep["failures"]:
        print("\n" + "=" * 92)
        for m in rep["failures"]:
            print(f"❌ {m}")
        print("=" * 92)
        # fail-closed 必須反映在退出碼 —— 否則自動化流程會把它當成通過
        raise SystemExit(3)


if __name__ == "__main__":
    main()
