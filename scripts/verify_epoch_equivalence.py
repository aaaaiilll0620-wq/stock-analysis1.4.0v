"""epoch-1 ≡ epoch-2 的等價性實測,回填進 provenance MANIFEST。

**要證的事**:第一批六個 arm(A1-A4 / C1 / C3)是用 08-01 11:35-11:41 之前的程式碼建的,
那個版本沒 commit、沒備份、拿不回來。若能證明「用**現行**程式碼重跑會得到相同結果」,
那六個面板就仍具備可重現 provenance —— 現行程式碼(HEAD + bundle 的 patch)即可還原它們。
證不出來的話,它們就是不可重現,必須整批重建。

**為什麼不能只看 diff**:四個 diff 確實都是 `RESEARCH_ARM` 旗標護欄下的加法,
肉眼看是 no-op。但本專案史上五次結論作廢**全部通過了肉眼審查**
(見 `docs/研究紀律_ResearchDiscipline.md`)。這裡要的是實測。

兩條路徑:

* **A1-A4** —— `--limit 8` 冒煙面板。epoch-1 版本(08-01 02:08-02:11)存在
  `provenance/epoch1_partials/`;用現行程式碼重跑後,比對 `arms/` 下的新檔。
  比對逐列、逐欄、含 NaN 位置,容差 0(要的是逐位元相同,不是「差不多」)。
* **C1 / C3** —— 後處理 arm,沒有冒煙檔。改成用現行程式碼在**記憶體內**從同一份診斷面板
  重建,與已落地的面板比對。全程唯讀,不覆寫任何研究產出。

用法:
    python -m scripts.verify_epoch_equivalence               # 兩條都跑,回填 manifest
    python -m scripts.verify_epoch_equivalence --part c1c3   # 只跑後處理那條
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RB_DIR = ROOT / "data" / "research_base"
ARM_DIR = RB_DIR / "arms"
PROV_DIR = ARM_DIR / "provenance"
EPOCH1_DIR = PROV_DIR / "epoch1_partials"
MANIFEST = PROV_DIR / "MANIFEST.json"

# epoch-1 的冒煙面板只有這四個。`arm_v0_*_partial_limit8` 是 08-01 14:59 建的
# (已在源碼修改之後)→ 它是 epoch-2,不能當對照組。
A_ARMS = ("A1", "A2", "A3", "A4")
KEY = ["as_of", "stock_id"]

# 對照組被複製進 bundle 時沒有保留 mtime(`cp` 未帶 `-p`),所以檔案時戳已不是建置時刻。
# 這裡記下複製前實測到的原始建置時刻,供稽核追溯。
EPOCH1_BUILT_AT = {"A1": "2026-08-01T02:08", "A2": "2026-08-01T02:09",
                   "A3": "2026-08-01T02:10", "A4": "2026-08-01T02:11"}


def _latest_build_source_mtime() -> float:
    """建置路徑源碼的最後修改時刻 —— epoch-1 / epoch-2 的分界。"""
    import os
    pats = [ROOT / "core", ROOT / "beat_0050" / "realbody"]
    latest = 0.0
    for base in pats:
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            latest = max(latest, os.path.getmtime(p))
    latest = max(latest, (ROOT / "scripts" / "build_face_postprocess_arms.py").stat().st_mtime)
    return latest


def compare_frames(old: pd.DataFrame, new: pd.DataFrame, label: str) -> dict:
    """逐欄逐列比對兩個面板。容差 0 —— 要的是逐位元相同。"""
    res: dict = {"label": label, "identical": False, "notes": []}

    # 建置時戳類欄位本來就會不同,不列入比對
    volatile = {"code_commit", "builder_version", "built_at", "run_id"}

    res["rows_old"], res["rows_new"] = int(len(old)), int(len(new))
    if len(old) != len(new):
        res["notes"].append(f"列數不同 {len(old)} vs {len(new)}")
        return res

    cols_old, cols_new = set(old.columns), set(new.columns)
    if cols_old != cols_new:
        res["notes"].append(f"欄位不同:只在舊={sorted(cols_old-cols_new)} "
                            f"只在新={sorted(cols_new-cols_old)}")
        return res

    for d in (old, new):
        for k in KEY:
            d[k] = d[k].astype(str)
    old = old.sort_values(KEY).reset_index(drop=True)
    new = new.sort_values(KEY).reset_index(drop=True)

    if not old[KEY].equals(new[KEY]):
        res["notes"].append("鍵集合或順序不同")
        return res

    diffs = {}
    for c in sorted(cols_old - volatile):
        a, b = old[c], new[c]
        na_mis = int((a.isna() != b.isna()).sum())
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            both = a.notna() & b.notna()
            d = (a[both].astype(float) - b[both].astype(float)).abs()
            k = int((d > 0).sum())
            if k or na_mis:
                diffs[c] = {"mismatch": k, "max_abs_diff": float(d.max()) if k else 0.0,
                            "nan_misalign": na_mis}
        else:
            k = int((a.astype(str) != b.astype(str)).sum())
            if k or na_mis:
                diffs[c] = {"mismatch": k, "nan_misalign": na_mis}

    res["column_diffs"] = diffs
    res["compared_columns"] = len(cols_old - volatile)
    res["identical"] = not diffs
    if diffs:
        res["notes"].append(f"{len(diffs)} 個欄位有差異 —— epoch 之間**不**等價")
    return res


def verify_a_partials() -> dict:
    out = {"method": ("A1-A4 的 --limit 8 冒煙面板:epoch-1 版本(08-01 02:08-02:11,"
                      "存於 provenance/epoch1_partials/)vs 用現行程式碼重跑的版本"),
           "epoch1_built_at": EPOCH1_BUILT_AT,
           "note_mtime": ("對照組複製進 bundle 時未保留 mtime,檔案時戳為複製時刻;"
                          "原始建置時刻見 epoch1_built_at。護欄改以『重跑結果晚於源碼最後修改』判定。"),
           "arms": {}}
    for arm in A_ARMS:
        name = f"arm_{arm}_scores_adv100w_arm_partial_limit8.parquet"
        old_p, new_p = EPOCH1_DIR / name, ARM_DIR / name
        if not old_p.exists():
            out["arms"][arm] = {"ERROR": f"缺 epoch-1 對照 {old_p}"}
            continue
        if not new_p.exists():
            out["arms"][arm] = {"ERROR": f"缺重跑結果 {new_p} —— 先跑 "
                                         f"build_arm_panel --arm {arm} --limit 8"}
            continue
        # 護欄:重跑結果必須真的是用 epoch-2 程式碼建的。
        # **不可**拿對照組的 mtime 當判準 —— 對照組是複製進 bundle 的,mtime 是複製時刻,
        # 不是原始建置時刻(原始為 08-01 02:08-02:11,見 EPOCH1_BUILT_AT)。
        # 正確判準:重跑結果的 mtime 必須晚於建置路徑源碼的最後修改時刻。
        if new_p.stat().st_mtime <= _latest_build_source_mtime():
            out["arms"][arm] = {"ERROR": "重跑結果早於源碼最後修改 —— 它不是 epoch-2 的產物"}
            continue
        out["arms"][arm] = compare_frames(pd.read_parquet(old_p),
                                          pd.read_parquet(new_p), f"{arm} partial_limit8")
    out["all_identical"] = all(v.get("identical") is True for v in out["arms"].values())
    return out


def verify_c1c3() -> dict:
    """用現行程式碼在記憶體內重建 C1/C3,與已落地面板比對。不寫任何檔。"""
    from scripts.build_face_postprocess_arms import DIAG_PATH, build_arm

    out = {"method": ("C1/C3 沒有冒煙檔。改用現行的 build_face_postprocess_arms.build_arm() "
                      "從同一份診斷面板在記憶體內重建,與已落地面板比對。全程唯讀。"),
           "diag_panel": DIAG_PATH.name, "arms": {}}
    diag = pd.read_parquet(DIAG_PATH)
    for arm in ("C1", "C3"):
        landed_p = ARM_DIR / f"arm_{arm}_scores_adv100w_arm.parquet"
        if not landed_p.exists():
            out["arms"][arm] = {"ERROR": "面板不存在"}
            continue
        rebuilt = build_arm(arm, diag.copy())
        landed = pd.read_parquet(landed_p)
        out["arms"][arm] = compare_frames(landed, rebuilt, f"{arm} 記憶體重建")
    out["all_identical"] = all(v.get("identical") is True for v in out["arms"].values())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("all", "a-partials", "c1c3"), default="all")
    a = ap.parse_args()

    result = {"run_at": datetime.now(timezone.utc).astimezone().isoformat(), "parts": {}}
    if a.part in ("all", "a-partials"):
        result["parts"]["a_partials"] = verify_a_partials()
    if a.part in ("all", "c1c3"):
        result["parts"]["c1c3"] = verify_c1c3()

    covered = {"a_partials": list(A_ARMS), "c1c3": ["C1", "C3"]}
    passed_arms, failed_arms = [], []
    for k, part in result["parts"].items():
        for arm, v in part["arms"].items():
            (passed_arms if v.get("identical") is True else failed_arms).append(arm)
    result["epoch1_arms_proved_reproducible"] = sorted(passed_arms)
    result["epoch1_arms_NOT_proved"] = sorted(failed_arms)
    result["verdict"] = ("epoch-1 ≡ epoch-2:現行程式碼可重現全部受測 arm"
                         if not failed_arms else
                         "❌ 有 arm 在兩個 epoch 之間不等價 —— 該 arm 的面板必須重建")
    if a.part != "all":
        result["⚠"] = f"只跑了 {a.part},未涵蓋 {set(covered) - set(result['parts'])}"

    print("=" * 96)
    print("epoch-1 ≡ epoch-2 等價性實測")
    print("=" * 96)
    for k, part in result["parts"].items():
        print(f"\n### {k}")
        print(f"    {part['method']}")
        for arm, v in part["arms"].items():
            if "ERROR" in v:
                print(f"    {arm}: ❌ {v['ERROR']}")
            elif v["identical"]:
                print(f"    {arm}: ✅ 逐列逐欄相同({v['compared_columns']} 欄 / "
                      f"{v['rows_new']:,} 列,容差 0)")
            else:
                print(f"    {arm}: ❌ 不等價 → {v['column_diffs']}")
    print(f"\n判定:{result['verdict']}")

    if a.part == "all" and MANIFEST.exists():
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        man["epoch_equivalence_test"] = result
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"→ 已回填 {MANIFEST}")
    elif a.part != "all":
        print("⚠ 非完整執行,不回填 manifest")

    if failed_arms:
        raise SystemExit(f"❌ 不等價的 arm:{sorted(set(failed_arms))}")


if __name__ == "__main__":
    main()
