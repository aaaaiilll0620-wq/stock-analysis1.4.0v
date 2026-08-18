# -*- coding: utf-8 -*-
"""gate1_c3_hist_window.py — C3 歷史窗確認性檢定的凍結 runner。

預註冊:`docs/預註冊_C3歷史窗確認.md`。**統計邏輯一律 import,不另寫一份**
(逐字沿用 `gate1_delta_ic_maxt.build_month_blocks/delta_ic_t/joint_maxt_null/
assert_same_months`)。本檔只換:時鐘(2005-01~2019-07,預註冊 §2)、族系大小
(K=1,只有 C3)、seed(20260809,預註冊 §3)。

用法:
    python -X utf8 scripts/gate1_c3_hist_window.py --part preflight
    python -X utf8 scripts/gate1_c3_hist_window.py --part gate --i-am-executing-the-frozen-gate
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for p in (str(_HERE), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from gate1_delta_ic_maxt import (                                    # noqa: E402
    EPS_SD, MIN_N, V0_BASELINE,
    assert_same_months, build_month_blocks, delta_ic_t, joint_maxt_null,
)
from lab_paths import REAL_COMP_COL, RET_COL, load_real_panel        # noqa: E402

# ============================================================================
# 凍結參數(docs/預註冊_C3歷史窗確認.md §2/§3,不得因結果調整)
# ============================================================================
HIST_LO, HIST_HI = "2005-01-31", "2019-07-31"
N_PERM = 2000
SEED = 20260809
ALPHA = 0.05
N_ARMS = 1                 # K=1:只有 C3,無第二候選

ARM_DIR = _ROOT / "data" / "research_base" / "arms"
OUT_DIR = _ROOT / "beat_0050" / "results" / "gate1_c3_hist"
STARTED_NAME = "C3_HIST_EXECUTION_STARTED.json"
MANIFEST_NAME = "C3_HIST_EXECUTION_MANIFEST.json"

# 預註冊 §1 記錄的面板 sha256 —— 執行前複核,輸入必須是凍結時的那一份
EXPECT_V0_SHA256 = "a8a8bc4286d77023e36985238ba9d50a5a5ead5349e2b04c03c388bd8b4f21ab"
EXPECT_C3_SHA256 = "db90bbeef05caa4b6e0d59158eecaff035d9493540e635f1c8daaa3ac8e2bba5"

DECISION_RULE = "G1-a AND G1-c(單尾 α=0.05,K=1 permutation max-t 退化為單一 arm 檢定)"


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
def assemble() -> tuple[pd.DataFrame, dict]:
    rep: dict = {"inputs": {}, "checks": []}

    d = load_real_panel(adv_floor=1e6)
    rep["v0_panel_path"] = d.attrs.get("realbody_path")
    rep["v0_panel_sha256"] = sha256_file(Path(rep["v0_panel_path"]))
    d["as_of"] = d["as_of"].astype(str)
    d["stock_id"] = d["stock_id"].astype(str)

    rep["rows_before_clock"] = int(len(d))
    d = d[(d["as_of"] >= HIST_LO) & (d["as_of"] <= HIST_HI)].reset_index(drop=True)
    rep["rows_after_clock"] = int(len(d))
    rep["clock"] = [HIST_LO, HIST_HI]
    rep["as_of_in_clock"] = int(d["as_of"].nunique())

    d["_ind"] = d["tej_ind_name"].fillna("未分類")
    rep["n_industries"] = int(d["_ind"].nunique())

    n_base = len(d)
    p = ARM_DIR / "arm_C3_scores_adv100w_arm.parquet"
    if not p.exists():
        raise SystemExit(f"❌ 缺 C3 arm 面板:{p}")
    a = pd.read_parquet(p, columns=["as_of", "stock_id", REAL_COMP_COL, "score_error"])
    a["as_of"] = a["as_of"].astype(str)
    a["stock_id"] = a["stock_id"].astype(str)

    dup = int(a.duplicated(["as_of", "stock_id"]).sum())
    se = int((a["score_error"].fillna("").astype(str).str.strip() != "").sum())
    c3_sha = sha256_file(p)
    rep["inputs"]["C3"] = {"path": str(p), "sha256": c3_sha,
                           "rows_full_panel": int(len(a)), "duplicate_keys": dup,
                           "score_error": se, "baseline": "V0",
                           "score_column": REAL_COMP_COL}
    if dup:
        raise SystemExit(f"❌ C3 面板有 {dup} 個重複鍵")
    if se:
        raise SystemExit(f"❌ C3 面板 score_error 非空 {se} 列")

    a = a.drop(columns=["score_error"]).rename(columns={REAL_COMP_COL: "arm_C3"})
    d = d.merge(a, on=["as_of", "stock_id"], how="left")
    if len(d) != n_base:
        raise SystemExit(f"❌ 併入 C3 後列數變動 {n_base} → {len(d)}(鍵不唯一)")

    return d, rep


def preflight(d: pd.DataFrame, rep: dict) -> tuple[dict, dict]:
    arm_cols = ["arm_C3"]

    rep["frozen"] = {"HIST_LO": HIST_LO, "HIST_HI": HIST_HI, "N_PERM": N_PERM,
                     "SEED": SEED, "ALPHA": ALPHA, "MIN_N": MIN_N,
                     "EPS_SD": EPS_SD, "N_ARMS": N_ARMS,
                     "RET_COL": RET_COL, "REAL_COMP_COL": REAL_COMP_COL}
    expect = {"HIST_LO": "2005-01-31", "HIST_HI": "2019-07-31", "N_PERM": 2000,
              "SEED": 20260809, "ALPHA": 0.05, "MIN_N": 30, "EPS_SD": 1e-12,
              "N_ARMS": 1, "RET_COL": "fwd_x", "REAL_COMP_COL": "real_composite"}
    bad = {k: (rep["frozen"][k], v) for k, v in expect.items() if rep["frozen"][k] != v}
    rep["frozen_matches_prereg"] = not bad
    if bad:
        raise SystemExit(f"❌ 凍結設定與預註冊不符:{bad}")

    # 輸入面板必須是預註冊 §1 記錄的那一份,不得因面板被重建而靜默漂移
    v0_ok = rep["v0_panel_sha256"] == EXPECT_V0_SHA256
    c3_ok = rep["inputs"]["C3"]["sha256"] == EXPECT_C3_SHA256
    rep["panel_sha256_matches_prereg"] = {"v0": v0_ok, "c3": c3_ok}
    if not (v0_ok and c3_ok):
        raise SystemExit(
            f"❌ 面板 sha256 與預註冊 §1 記錄不符 —— 輸入已不是凍結時的那一份。\n"
            f"   V0 預期 {EXPECT_V0_SHA256} 實得 {rep['v0_panel_sha256']}\n"
            f"   C3 預期 {EXPECT_C3_SHA256} 實得 {rep['inputs']['C3']['sha256']}")

    c = "arm_C3"
    miss = int(d[c].isna().sum())
    rep["arm_coverage_in_clock"] = {"missing_in_clock": miss,
                                    "coverage": float(1.0 - miss / len(d)) if len(d) else 0.0}
    rep["all_arms_full_coverage"] = rep["arm_coverage_in_clock"]["coverage"] == 1.0

    rep["return_line"] = {"column": RET_COL, "source": "exec_ret(經 lab_paths.load_real_panel)",
                          "notna_rows": int(d[RET_COL].notna().sum())}
    rep["candidate_score"] = {"column": REAL_COMP_COL, "note": "C3 面板的真身分數"}

    blocks_a, info_a = build_month_blocks(d, arm_cols, v0_col=REAL_COMP_COL,
                                          ret_col=RET_COL, min_n=MIN_N, neutral_by=None)
    blocks_c, info_c = build_month_blocks(d, arm_cols, v0_col=REAL_COMP_COL,
                                          ret_col=RET_COL, min_n=MIN_N, neutral_by="_ind")
    assert_same_months(info_a, info_c)
    rep["common_sample"] = {
        "n_months_M_star": info_a["n_months"],
        "months_first": info_a["months"][:3], "months_last": info_a["months"][-3:],
        "dropped_months": info_a["dropped"],
        "n_stocks_per_month_min": int(min(len(b[2]) for b in blocks_a)),
        "n_stocks_per_month_max": int(max(len(b[2]) for b in blocks_a)),
        "n_stocks_per_month_median": float(np.median([len(b[2]) for b in blocks_a])),
        "G1a_G1c_same_months": True,
    }

    base_ok = d[RET_COL].notna() & d[REAL_COMP_COL].notna()
    rep["rows_excluded_by_arm"] = int((base_ok & d[c].isna()).sum())

    # 誠實揭露項(預註冊 §5-3):f_val / f_mom 在此窗的覆蓋率,供結果報告並列
    cov_extra = {}
    for col in ("f_val", "f_mom"):
        if col in d.columns:
            cov_extra[col] = float(d[col].notna().mean())
    rep["face_coverage_in_window"] = cov_extra

    checks = [
        ("C3 面板存在且無 dup/score_error", rep["inputs"]["C3"]["duplicate_keys"] == 0
         and rep["inputs"]["C3"]["score_error"] == 0),
        ("面板 sha256 與預註冊 §1 一致", v0_ok and c3_ok),
        ("窗內 C3 coverage = 1.0", rep["all_arms_full_coverage"]),
        (f"報酬線 = exec_ret.{RET_COL}", RET_COL == "fwd_x"),
        (f"候選分數 = {REAL_COMP_COL}", REAL_COMP_COL == "real_composite"),
        ("凍結參數符合預註冊", rep["frozen_matches_prereg"]),
        ("G1-a / G1-c 的 M* 一致", rep["common_sample"]["G1a_G1c_same_months"]),
        ("窗與原案 OOS 窗無重疊(2005-01~2019-07 早於 2019-08-01)", HIST_HI < "2019-08-01"),
    ]
    rep["preflight_checks"] = {n: bool(o) for n, o in checks}
    rep["preflight_passed"] = all(o for _, o in checks)
    return rep, {"blocks_a": blocks_a, "info_a": info_a, "blocks_c": blocks_c, "info_c": info_c}


# ==============================================================================
def run_gate(d: pd.DataFrame, rep: dict, blocks: dict) -> dict:
    baseline_idx = [V0_BASELINE]   # K=1,唯一的 arm 對 V0

    res = {"decision_rule": DECISION_RULE, "n_months_M_star": blocks["info_a"]["n_months"],
          "settings": {"n_perm": N_PERM, "seed": SEED, "alpha": ALPHA,
                       "baseline_idx": baseline_idx}}

    for tag, key in [("G1a", "blocks_a"), ("G1c", "blocks_c")]:
        t = delta_ic_t(blocks[key], baseline_idx)
        null = joint_maxt_null(blocks[key], n_perm=N_PERM, seed=SEED, alpha=ALPHA,
                               baseline_idx=baseline_idx)
        p_adj = float(np.mean(null["maxt"] >= t[0])) if np.isfinite(t[0]) else 1.0
        res[tag] = {"T_star": null["T_star"], "t": float(t[0]), "p_adj": p_adj,
                    "rho_hat": null["rho_hat"], "rho_status": null["rho_status"],
                    "degenerate": null["degenerate"]}

    pass_a = res["G1a"]["t"] > res["G1a"]["T_star"]
    pass_c = res["G1c"]["t"] > res["G1c"]["T_star"]
    res["pass_G1a"] = bool(pass_a)
    res["pass_G1c"] = bool(pass_c)
    res["passed"] = bool(pass_a and pass_c)
    return res


# ==============================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["preflight", "gate"], required=True)
    ap.add_argument("--i-am-executing-the-frozen-gate", action="store_true",
                    help="人為關卡:單發射擊制,--part gate 必須明確加此旗標")
    args = ap.parse_args()

    hr("組裝面板")
    d, rep = assemble()
    print(f"窗 {HIST_LO}~{HIST_HI}:{rep['rows_after_clock']} 列 / "
          f"{rep['as_of_in_clock']} 個 as_of")

    hr("Preflight")
    rep, blocks = preflight(d, rep)
    for name, ok in rep["preflight_checks"].items():
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\nM* = {rep['common_sample']['n_months_M_star']} 個月"
          f"(預期上限 175,實際以覆蓋規則為準)")
    print(f"視窗:{rep['common_sample']['months_first']} ... "
          f"{rep['common_sample']['months_last']}")
    if rep["common_sample"]["dropped_months"]:
        print(f"⚠ 剔除 {len(rep['common_sample']['dropped_months'])} 個月"
              f"(共同檔數 < {MIN_N}):{rep['common_sample']['dropped_months'][:5]}")
    print(f"誠實揭露 —— 窗內面覆蓋率:{rep['face_coverage_in_window']}")

    if not rep["preflight_passed"]:
        raise SystemExit("❌ Preflight 未通過,不執行正式檢定。")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "c3_hist_preflight.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n✅ Preflight 通過,已寫 {OUT_DIR / 'c3_hist_preflight.json'}")

    if args.part == "preflight":
        print("\n(只跑 preflight,--part gate 才會計算 ΔIC / 執行 permutation)")
        return 0

    # ---- 正式執行分支:單發射擊制人為關卡 ----
    if not args.__dict__["i_am_executing_the_frozen_gate"]:
        raise SystemExit(
            "❌ --part gate 需要明確加 --i-am-executing-the-frozen-gate。\n"
            "   這是單發射擊制的人為關卡:本案只能執行一次,執行前請確認"
            "已取得使用者明確授權(docs/預註冊_C3歷史窗確認.md §7)。")

    started_path = OUT_DIR / STARTED_NAME
    manifest_path = OUT_DIR / MANIFEST_NAME
    if manifest_path.exists():
        raise SystemExit(
            f"❌ {manifest_path} 已存在 —— 本案已執行過一次。單發射擊制不得重跑。\n"
            "   如需重跑,須先有明確理由並記錄在預註冊文件,不得靜默覆寫。")
    if started_path.exists():
        raise SystemExit(
            f"❌ {started_path} 已存在但沒有對應的 MANIFEST —— 上次執行可能中途失敗。\n"
            "   請先確認上次執行狀態,不要在不明狀態上疊加新的一次。")

    t0 = datetime.now(timezone.utc)
    started_path.write_text(json.dumps({"started_at": t0.isoformat()}, indent=2),
                            encoding="utf-8")

    hr("正式執行:ΔIC 檢定(K=1,單發)")
    res = run_gate(d, rep, blocks)
    t1 = datetime.now(timezone.utc)

    manifest = {
        "_what": "C3 歷史窗確認性檢定 execution manifest(單發,已執行,不可重跑)",
        "_prereg": ["docs/預註冊_C3歷史窗確認.md"],
        "executed_at_start": t0.isoformat(), "executed_at_end": t1.isoformat(),
        "command": "gate1_c3_hist_window.py --part gate --i-am-executing-the-frozen-gate",
        "inputs": rep["inputs"], "v0_panel": {"path": rep["v0_panel_path"],
                                              "sha256": rep["v0_panel_sha256"]},
        "return_line": rep["return_line"], "candidate_score": rep["candidate_score"],
        "clock": rep["clock"], "frozen": rep["frozen"],
        "common_sample": rep["common_sample"],
        "face_coverage_in_window": rep["face_coverage_in_window"],
        "results": res,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")

    hr("結果")
    print(f"G1-a:t={res['G1a']['t']:.4f}  T*={res['G1a']['T_star']:.4f}  "
          f"p_adj={res['G1a']['p_adj']:.4f}  {'✅ 通過' if res['pass_G1a'] else '❌ 未過'}")
    print(f"G1-c:t={res['G1c']['t']:.4f}  T*={res['G1c']['T_star']:.4f}  "
          f"p_adj={res['G1c']['p_adj']:.4f}  {'✅ 通過' if res['pass_G1c'] else '❌ 未過'}")
    print(f"\n判定(AND):{'✅ C3 通過' if res['passed'] else '❌ C3 未過'}")
    print(f"\n已寫 {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
