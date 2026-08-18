# -*- coding: utf-8 -*-
"""gate1_assemble_12arm.py — Gate 1 的**正式 12-arm candidate assembly runner**。

`scripts/gate1_delta_ic_maxt.py` 的 `main()` 只跑 `synthetic_suite()`,而檔頭 :19 自己
寫明「synthetic arm 不是 candidate arm」—— 那是檢定程序的校準,**不是** Gate 1 結果。
本檔負責缺的那一半:把 12 個已落地的 candidate 面板組成 frozen candidate score matrix,
跑完整 preflight,再交給凍結的統計函式。

**統計邏輯一律 import,不另寫一份**(第一批預註冊 §5-2:「arm runner 必須 import
這兩個函式,不得另寫一份」)——
`build_month_blocks()` / `delta_ic_t()` / `joint_maxt_null()` / `assert_same_months()`
與全部凍結參數都從 `gate1_delta_ic_maxt` 取,本檔不重新定義任何一個。

用法:
    python -X utf8 scripts/gate1_assemble_12arm.py --part preflight
    python -X utf8 scripts/gate1_assemble_12arm.py --part gate      # 目前 fail-closed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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

# ---- 凍結的統計實作與參數:一律 import,本檔不重新定義 ----
from gate1_delta_ic_maxt import (                                    # noqa: E402
    ALPHA, EPS_SD, MIN_N, N_ARMS, N_PERM, OOS_HI, OOS_LO, SEED, V0_BASELINE,
    _check_baseline_idx, assert_same_months, build_month_blocks,
    delta_ic_t, joint_maxt_null,
)
from lab_paths import REAL_COMP_COL, RET_COL, load_real_panel        # noqa: E402

ARM_DIR = _ROOT / "data" / "research_base" / "arms"
PROV = ARM_DIR / "provenance" / "MANIFEST.json"
OUT_DIR = _ROOT / "beat_0050" / "results" / "gate1"

# 預註冊申報的搜尋空間 = 這 12 個,不多不少(第一批 §4-5 + 第二批 §6)
FIRST_BATCH = ("A1", "A2", "A3", "A4", "C1", "C3")
SECOND_BATCH = ("B1", "B2", "B3", "B4", "B5", "C2")
ALL_ARMS = FIRST_BATCH + SECOND_BATCH

# 每個 arm 的 ΔIC 配對基準(來自凍結預註冊,不得因結果調整)
#   第一批 §5-2 表:ΔIC(t) = IC_arm(t) − IC_V0(t)
#   第二批 §0-1  :第二批所有 arm 的對照組是 V0-C3(= 第一批 C3 arm 的分數)
ARM_BASELINE = {**{a: "V0" for a in FIRST_BATCH},
                **{a: "V0-C3" for a in SECOND_BATCH}}

# ---------------------------------------------------------------------------
# **硬編碼的 baseline 宣告表**(勘誤 E1 / Codex 2026-08-02 §2)
#
#   索引 : 0   1   2   3   4   5   6   7   8   9  10  11
#   arm  : A1  A2  A3  A4  C1  C3  B1  B2  B3  B4  B5  C2
#   base : V0  V0  V0  V0  V0  V0  C3  C3  C3  C3  C3  C3
#
# `-1` = V0(build_month_blocks 的 v0_col);`5` = 族內索引 5,即 C3。
# 這張表在看到任何 candidate 統計量之前寫死,**不得因結果調整**。
# G1-a(raw)與 G1-c(產業內中性化)**共用同一份 mapping** —— 中性化只改分數的
# 前處理,不改誰對誰配對。
BASELINE_IDX = [V0_BASELINE] * 6 + [5] * 6
IDX_C3 = 5

# ---------------------------------------------------------------------------
# **武裝機制** —— 首次正式 permutation 的人為關卡。
#
# 單發射擊制:Gate 1 只能跑一次,跑完 T* 就定了。
#
# 舊設計用原始碼常數 `EXECUTION_APPROVED` 武裝,已廢除(Codex 2026-08-02 §1):
# 改原始碼會**改變 runner 的 sha256**,而 runner hash 記在已驗過的 overlay 裡 ——
# 等於「授權」這個動作本身就會破壞 provenance,使用者被迫在「授權」與「保持 overlay
# 有效」之間二選一。
#
# 現行設計:授權是一個**外部 JSON 檔**,綁定當前 overlay 的 sha256。
# 授權不碰任何原始碼 → runner hash 不變、overlay 不失效。
# 開火需要兩者同時到位:
#   1. 命令列旗標 `--i-am-executing-the-frozen-gate`
#   2. `--authorization <file.json>`,內容須綁定當前 overlay 的 sha256
ARM_FLAG = "--i-am-executing-the-frozen-gate"
AUTH_TOKEN = "gate1-first-official-permutation"

# 單發射擊的檔案鎖。三個檔任一存在 → 拒絕執行(不得刪除,只能人工封存)。
STARTED_NAME = "GATE1_EXECUTION_STARTED.json"
MANIFEST_NAME = "GATE1_EXECUTION_MANIFEST.json"
FAILURE_NAME = "GATE1_EXECUTION_FAILURE.json"

# 逐 arm 判定:G1-a(raw)與 G1-c(產業內中性化)兩者的 t 都必須超過各自的 T*。
# 第一批 §7 / Codex 第九輪 §2:通過條件是 **AND**,G1-b 純描述不作條件。
DECISION_RULE = "G1-a AND G1-c(單尾 α=0.05,各自對自己的 T*)"


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
    """組成 frozen candidate score matrix。

    候選分數一律取各 arm 面板的 `real_composite`(真身),**不用** `composite_indep`、
    不用衍生欄。報酬線由 `load_real_panel` 提供的 `exec_ret.fwd_x`(`RET_COL`)。
    """
    rep: dict = {"inputs": {}, "checks": []}

    d = load_real_panel(adv_floor=1e6)
    rep["v0_panel_path"] = d.attrs.get("realbody_path")
    rep["v0_panel_sha256"] = sha256_file(Path(rep["v0_panel_path"]))
    d["as_of"] = d["as_of"].astype(str)
    d["stock_id"] = d["stock_id"].astype(str)

    rep["rows_before_clock"] = int(len(d))
    d = d[(d["as_of"] >= OOS_LO) & (d["as_of"] <= OOS_HI)].reset_index(drop=True)
    rep["rows_after_clock"] = int(len(d))
    rep["clock"] = [OOS_LO, OOS_HI]
    rep["as_of_in_clock"] = int(d["as_of"].nunique())

    # 產業欄:與凍結 runner 的 main() 逐字相同
    d["_ind"] = d["tej_ind_name"].fillna("未分類")
    rep["n_industries"] = int(d["_ind"].nunique())

    n_base = len(d)
    for arm in ALL_ARMS:
        p = ARM_DIR / f"arm_{arm}_scores_adv100w_arm.parquet"
        if not p.exists():
            raise SystemExit(f"❌ 缺 arm 面板:{p}")
        a = pd.read_parquet(p, columns=["as_of", "stock_id", REAL_COMP_COL, "score_error"])
        a["as_of"] = a["as_of"].astype(str)
        a["stock_id"] = a["stock_id"].astype(str)

        dup = int(a.duplicated(["as_of", "stock_id"]).sum())
        se = int((a["score_error"].fillna("").astype(str).str.strip() != "").sum())
        rep["inputs"][arm] = {
            "path": str(p), "sha256": sha256_file(p),
            "rows_full_panel": int(len(a)), "duplicate_keys": dup,
            "score_error": se, "baseline": ARM_BASELINE[arm],
            "score_column": REAL_COMP_COL,
        }
        if dup:
            raise SystemExit(f"❌ {arm} 面板有 {dup} 個重複鍵")
        if se:
            raise SystemExit(f"❌ {arm} 面板 score_error 非空 {se} 列")

        a = a.drop(columns=["score_error"]).rename(columns={REAL_COMP_COL: f"arm_{arm}"})
        d = d.merge(a, on=["as_of", "stock_id"], how="left")
        if len(d) != n_base:
            raise SystemExit(f"❌ 併入 {arm} 後列數變動 {n_base} → {len(d)}(鍵不唯一)")

    return d, rep


def preflight(d: pd.DataFrame, rep: dict) -> dict:
    arm_cols = [f"arm_{a}" for a in ALL_ARMS]

    # ---- 1. 凍結設定複核 ----
    rep["frozen"] = {"OOS_LO": OOS_LO, "OOS_HI": OOS_HI, "N_PERM": N_PERM,
                     "SEED": SEED, "ALPHA": ALPHA, "MIN_N": MIN_N,
                     "EPS_SD": EPS_SD, "N_ARMS": N_ARMS,
                     "RET_COL": RET_COL, "REAL_COMP_COL": REAL_COMP_COL}
    expect = {"OOS_LO": "2019-08-01", "OOS_HI": "2026-03-31", "N_PERM": 2000,
              "SEED": 20260731, "ALPHA": 0.05, "MIN_N": 30, "EPS_SD": 1e-12,
              "N_ARMS": 12, "RET_COL": "fwd_x", "REAL_COMP_COL": "real_composite"}
    bad = {k: (rep["frozen"][k], v) for k, v in expect.items() if rep["frozen"][k] != v}
    rep["frozen_matches_instruction"] = not bad
    if bad:
        raise SystemExit(f"❌ 凍結設定與指示不符:{bad}")

    if len(arm_cols) != N_ARMS:
        raise SystemExit(f"❌ arm 數 {len(arm_cols)} != N_ARMS {N_ARMS}")

    # ---- 2. 各 arm 在主時鐘內的覆蓋 ----
    cov = {}
    for a in ALL_ARMS:
        c = f"arm_{a}"
        miss = int(d[c].isna().sum())
        cov[a] = {"missing_in_clock": miss,
                  "coverage": float(1.0 - miss / len(d)) if len(d) else 0.0}
    rep["arm_coverage_in_clock"] = cov
    rep["all_arms_full_coverage"] = all(v["coverage"] == 1.0 for v in cov.values())

    # ---- 3. 報酬線 / 候選分數欄 ----
    rep["return_line"] = {"column": RET_COL,
                          "source": "exec_ret(經 lab_paths.load_real_panel)",
                          "notna_rows": int(d[RET_COL].notna().sum())}
    rep["candidate_score"] = {"column": REAL_COMP_COL,
                              "note": "各 arm 面板的真身分數;未使用 composite_indep 或任何衍生欄"}

    # ---- 4. 共同月份 M* / 共同股票集 I(t)(用凍結的 build_month_blocks)----
    # I(t) = fwd_x + V0 分數 + 全部 12 個 arm 分數皆非缺的交集(第一批 §5-2 表)
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

    # 各 arm 因交集被剔除的股票數(§5-2 表「必報」項)
    excl = {}
    for a in ALL_ARMS:
        c = f"arm_{a}"
        base_ok = d[RET_COL].notna() & d[REAL_COMP_COL].notna()
        excl[a] = int((base_ok & d[c].isna()).sum())
    rep["rows_excluded_by_each_arm"] = excl

    # ---- 5. baseline 宣告表(硬編碼 + 逐項驗證)----
    # 驗證 1:族內第 5 個必須真的是 C3 —— 若 ALL_ARMS 的順序被動過,索引 5 就會指錯 arm,
    #        而 permutation 照樣跑得出數字。這道檢查是防止那種靜默錯位。
    if ALL_ARMS[IDX_C3] != "C3":
        raise SystemExit(f"❌ BASELINE_IDX 假定索引 {IDX_C3} 是 C3,實際是 "
                         f"{ALL_ARMS[IDX_C3]!r} —— arm 順序被動過")
    # 驗證 2:交給凍結函式的型別/範圍/自我指涉檢查(不做靜默轉型)
    checked = _check_baseline_idx(BASELINE_IDX, N_ARMS)
    # 驗證 3:硬編碼表必須與 ARM_BASELINE 的文字宣告逐項一致
    mism = []
    for k, arm in enumerate(ALL_ARMS):
        want = "V0" if ARM_BASELINE[arm] == "V0" else "V0-C3"
        got = "V0" if checked[k] == V0_BASELINE else f"arm_{ALL_ARMS[checked[k]]}"
        if (want == "V0") != (got == "V0") or (want == "V0-C3" and got != "arm_C3"):
            mism.append((arm, want, got))
    if mism:
        raise SystemExit(f"❌ BASELINE_IDX 與 ARM_BASELINE 宣告不一致:{mism}")

    rep["baseline_idx"] = [int(v) for v in checked]
    rep["baseline_idx_verified"] = True
    rep["baseline_idx_map"] = {
        arm: ("V0" if checked[k] == V0_BASELINE else f"arm_{ALL_ARMS[checked[k]]}")
        for k, arm in enumerate(ALL_ARMS)}
    rep["baseline_shared_by_g1a_and_g1c"] = True
    rep["baseline_declaration"] = {
        "first_batch": {"arms": list(FIRST_BATCH), "baseline": "V0",
                        "source": "第一批預註冊 §5-2:ΔIC(t) = IC_arm(t) − IC_V0(t)",
                        "column": REAL_COMP_COL},
        "second_batch": {"arms": list(SECOND_BATCH), "baseline": "V0-C3",
                         "source": "第二批預註冊 §0-1:第二批所有 arm 的對照組是 V0-C3",
                         "column": "arm_C3(= 第一批 C3 面板的 real_composite)"},
        "note_g1c": ("G1-c 時 V0 與 C3 兩條 baseline 腿都取產業內中性化後的 rank score,"
                     "與各 arm 同一前處理(勘誤 E2)。mapping 與 G1-a 完全相同。"),
    }

    # ---- 6. 判定 ----
    # ⚠ `preflight_checks` / `preflight_passed` **必須由本函式產出**,
    # 不得由 main() 的列印區塊當副作用設定(attempt 1 的根因:gate 分支在
    # 列印區塊之前就讀 `rep["preflight_passed"]` → KeyError,統計未擊發但單發已認領)。
    # 呼叫端只讀不寫。
    checks = [
        ("12 個 arm 都有資料", len(rep["inputs"]) == N_ARMS),
        ("無 duplicate keys", all(v["duplicate_keys"] == 0 for v in rep["inputs"].values())),
        ("score_error 全為 0", all(v["score_error"] == 0 for v in rep["inputs"].values())),
        ("主時鐘內各 arm coverage = 1.0", rep["all_arms_full_coverage"]),
        (f"報酬線 = exec_ret.{RET_COL}", RET_COL == "fwd_x"),
        (f"候選分數 = {REAL_COMP_COL}", REAL_COMP_COL == "real_composite"),
        ("凍結參數符合指示", rep["frozen_matches_instruction"]),
        ("G1-a / G1-c 的 M* 一致", rep["common_sample"]["G1a_G1c_same_months"]),
    ]
    rep["preflight_checks"] = {n: bool(o) for n, o in checks}
    rep["preflight_passed"] = all(o for _, o in checks)
    # blocks 一併回傳:執行分支直接沿用 preflight 驗過的那一份,不重建。
    # 重建等於多一條可能與 preflight 不一致的路徑。
    return rep, {"blocks_a": blocks_a, "info_a": info_a,
                 "blocks_c": blocks_c, "info_c": info_c}


# ==============================================================================
# 正式執行分支
# ==============================================================================
def verify_overlay_or_die() -> dict:
    """執行前先驗 Gate 1 provenance overlay —— 任何一項不符就不准開火。

    overlay 的 `--check` 會逐檔重算父 MANIFEST、12 個面板 / report / audit、
    Gate 1 實際讀取的 V0 面板、Gate 1 產物與勘誤 patch,並交叉核對抄錄值。
    """
    import build_gate1_provenance_overlay as OVL

    if not OVL.OUT.exists():
        raise SystemExit(f"❌ 找不到 Gate 1 provenance overlay:{OVL.OUT}\n"
                         "   先跑 scripts/build_gate1_provenance_overlay.py")
    ov = json.loads(OVL.OUT.read_text(encoding="utf-8"))
    parent = json.loads(OVL.PARENT_MANIFEST.read_text(encoding="utf-8"))
    items = OVL.build_check_items(ov, parent, root=OVL.ROOT, arm_dir=OVL.ARM_DIR,
                                  v0_path=OVL.resolve_v0_path(),
                                  parent_path=OVL.PARENT_MANIFEST)
    fails = OVL.verify_fingerprints(items) + OVL.cross_check_parent(ov, parent)
    if fails:
        for m in fails:
            print(f"❌ {m}")
        raise SystemExit(f"❌ overlay 驗證失敗 {len(fails)} 項 —— 輸入已不是凍結的那一份,"
                         "不得執行正式 Gate 1。")
    return {"overlay_path": str(OVL.OUT), "overlay_sha256": OVL.sha256_file(OVL.OUT),
            "items_verified": len(items), "passed": True}


def load_authorization(auth_path, overlay_path) -> dict:
    """讀取並驗證 Gate 1 授權檔。**必須綁定當前 overlay 的 sha256。**

    純函式化(路徑由呼叫端注入)以便合成測試驗真正上線的這一段。
    任何一項不符一律 raise —— 授權不成立時,連 candidate 面板都不該被讀取。
    """
    if auth_path is None:
        raise SystemExit(
            f"❌ 未提供授權檔。正式執行需 `--authorization <file.json>`,"
            f"內容須綁定當前 overlay 的 sha256(見 --print-authorization-template)。")
    p = Path(auth_path)
    if not p.exists():
        raise SystemExit(f"❌ 授權檔不存在:{p}")
    try:
        content = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"❌ 授權檔不是合法 JSON:{p}({exc})") from None
    if not isinstance(content, dict):
        raise SystemExit(f"❌ 授權檔頂層必須是物件:{p}")
    if content.get("authorizes") != AUTH_TOKEN:
        raise SystemExit(f"❌ 授權檔的 `authorizes` 必須是 {AUTH_TOKEN!r},"
                         f"實得 {content.get('authorizes')!r}")

    ovp = Path(overlay_path)
    if not ovp.exists():
        raise SystemExit(f"❌ 找不到 overlay:{ovp}")
    actual = sha256_file(ovp)
    declared = content.get("overlay_sha256")
    if not declared:
        raise SystemExit("❌ 授權檔缺 `overlay_sha256` —— 授權必須綁定特定一份 overlay,"
                         "否則等於空白支票。")
    if declared != actual:
        raise SystemExit(
            "❌ 授權檔綁定的 overlay 與現行的不符 —— 授權之後輸入或程式碼被改過了。\n"
            f"   授權檔宣告 {declared}\n   現行 overlay {actual}")
    return {"path": str(p), "sha256": sha256_file(p),
            "overlay_sha256": actual, "content": content}


def claim_execution(*, started_path, manifest_path, failure_path, payload) -> dict:
    """以 **exclusive create** 建立 STARTED,作為單發射擊的認領。

    三個檔任一已存在就拒絕:
      · MANIFEST 存在 → 已經開過火;
      · STARTED 存在  → 上一次開火沒走完(可能仍在跑,也可能中途死掉);
      · FAILURE 存在  → 上一次失敗了,尚未人工封存。
    `O_CREAT | O_EXCL` 讓「檢查」與「建立」是同一個原子動作,
    兩個行程同時開火時只有一個拿得到。
    """
    for p, what in ((manifest_path, "EXECUTION_MANIFEST"),
                    (started_path, "EXECUTION_STARTED"),
                    (failure_path, "EXECUTION_FAILURE")):
        if Path(p).exists():
            raise SystemExit(
                f"❌ {what} 已存在:{p}\n"
                "   Gate 1 是單發射擊 —— 不得重跑覆寫。要重跑必須先**人工封存**既有檔案"
                "(改名並記錄理由),並取得新的授權檔。")
    fd = os.open(str(started_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return payload


def atomic_write_json(path, payload) -> Path:
    """temp file + `os.replace` 的原子落地。

    直接 `write_text` 的話,寫到一半掛掉會留下**半份 JSON 卻叫著正式檔名** ——
    那份東西看起來就是正式結果。改成先寫 `.tmp` 再原子換名:
    正式檔名要嘛不存在,要嘛就是完整的。
    失敗時 `.tmp` 刻意保留(證據),但它不叫正式檔名,不會被誤認。
    """
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def assemble_execution_manifest(*, rep, res, ovl, auth, started, t0, t1,
                                argv, started_path) -> dict:
    """組出最終 manifest(含授權欄位)。抽成函式以便合成測試注入失敗。"""
    man = build_execution_manifest(rep, res, ovl, t0, t1, argv)
    man["authorization"] = {"path": auth["path"], "sha256": auth["sha256"],
                            "overlay_sha256": auth["overlay_sha256"],
                            "content": auth["content"]}
    man["execution_started_record"] = started
    man["execution_started_file"] = str(started_path)
    return man


def write_failure_record(*, failure_path, started, error,
                         candidate_statistics_computed: bool = False,
                         recovery_payload=None) -> None:
    """執行失敗時另寫失敗紀錄。**絕不刪除 STARTED** ——

    刪掉 STARTED 就等於把「已經開過一槍」的痕跡抹掉,下一次會被當成首發。
    重跑必須人工封存 + 新授權。

    `candidate_statistics_computed=True` 代表 **permutation 已經跑完、單發已擊發**,
    只是結果封存失敗。這種情形最危險:若不留下 `recovery_payload`,那一槍的結果
    就永久遺失,而重跑會構成第二次射擊。
    """
    rec = {
        "_what": "Gate 1 執行失敗紀錄。STARTED 刻意保留,不得刪除。",
        "failed_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "error_type": type(error).__name__,
        "error": str(error),
        "started_record": started,
        "candidate_statistics_computed": bool(candidate_statistics_computed),
        "note": ("重跑前必須人工封存 STARTED 與本檔(改名並記錄理由),"
                 "並取得綁定新 overlay 的新授權檔。"),
    }
    if candidate_statistics_computed:
        rec["⚠"] = ("**單發已擊發** —— permutation 已跑完,失敗發生在結果封存階段。"
                    "正式結果保存在下方 recovery_payload,**不得靠重跑取得**;"
                    "重跑等於第二次射擊,會使 T* 失去單發射擊的語意。")
        rec["recovery_payload"] = recovery_payload
    else:
        rec["note_not_fired"] = "permutation 未執行完成,沒有 candidate 統計量產生。"
    Path(failure_path).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def authorization_template(overlay_path) -> dict:
    """印給使用者自己存檔用的樣板 —— 印出樣板**不構成授權**,建立檔案才是。"""
    return {
        "authorizes": AUTH_TOKEN,
        "overlay_sha256": sha256_file(Path(overlay_path)),
        "authorized_by": "<你的名字>",
        "authorized_at": "<ISO 8601 時間>",
        "note": "<為什麼現在可以開火;審查依據>",
    }


def run_gate1(blocks_a, info_a, blocks_c, info_c, baseline_idx,
              n_perm: int = N_PERM, seed: int = SEED,
              alpha: float = ALPHA) -> dict:
    """凍結的 Gate 1 判定 —— G1-a 與 G1-c **共用同一份 `baseline_idx`**。

    純函式:吃 blocks 吐結果,不讀檔不寫檔。合成測試驗的就是這一段。
    統計全部來自凍結實作的 `delta_ic_t()` / `joint_maxt_null()`,本函式不自算任何統計量。
    """
    assert_same_months(info_a, info_c)          # 兩版必須跑在同一組 M* 上

    t_a = delta_ic_t(blocks_a, baseline_idx=baseline_idx)
    t_c = delta_ic_t(blocks_c, baseline_idx=baseline_idx)
    null_a = joint_maxt_null(blocks_a, n_perm=n_perm, seed=seed, alpha=alpha,
                             baseline_idx=baseline_idx)
    null_c = joint_maxt_null(blocks_c, n_perm=n_perm, seed=seed, alpha=alpha,
                             baseline_idx=baseline_idx)

    def _padj(t_obs, maxt):
        # 單步 max-t 的 adjusted p。`(1+#{maxt ≥ t})/(1+B)` 是置換檢定的標準保守慣例
        # (p 不會是 0)。⚠ 這是**報告用的衍生量**,凍結預註冊定義的判定門檻是 `t > T*`;
        # 兩者在 α=0.05 下一致,但以 T* 為準。
        return np.array([(1 + int(np.sum(maxt >= t))) / (1 + len(maxt)) for t in t_obs])

    p_a, p_c = _padj(t_a, null_a["maxt"]), _padj(t_c, null_c["maxt"])
    pass_a = t_a > null_a["T_star"]
    pass_c = t_c > null_c["T_star"]

    return {
        "decision_rule": DECISION_RULE,
        "n_months_M_star": info_a["n_months"],
        "settings": {"n_perm": n_perm, "seed": seed, "alpha": alpha,
                     "baseline_idx": [int(v) for v in baseline_idx]},
        "G1a": {"T_star": null_a["T_star"], "t": t_a.tolist(), "p_adj": p_a.tolist(),
                "rho_hat": null_a["rho_hat"], "rho_status": null_a["rho_status"],
                "degenerate": bool(null_a["degenerate"])},
        "G1c": {"T_star": null_c["T_star"], "t": t_c.tolist(), "p_adj": p_c.tolist(),
                "rho_hat": null_c["rho_hat"], "rho_status": null_c["rho_status"],
                "degenerate": bool(null_c["degenerate"])},
        "pass_G1a": pass_a.tolist(),
        "pass_G1c": pass_c.tolist(),
        "passed": (pass_a & pass_c).tolist(),
        "note_rho": ("rho_hat 是族內 t 的平均兩兩相關(**混合基準**:V0 腿與 C3 腿),"
                     "不再等同單一來源造成的相關(勘誤 §4-2)。"),
        "note_p_adj": ("p_adj 為報告用衍生量,凍結的判定門檻是 t > T*。"),
    }


def build_execution_manifest(rep: dict, res: dict, ovl: dict,
                             t0, t1, argv: list) -> dict:
    """**獨立的** execution manifest —— 與 provenance overlay 分開。

    overlay 記的是「輸入與程式碼是哪一份」;本檔記的是「這一次開火做了什麼、得到什麼」。
    兩者分開,因為 Gate 1 是單發射擊:overlay 可以重建,execution 不可以。
    """
    return {
        "_what": "Gate 1 首次正式執行的 execution manifest(單發射擊,不得重跑覆寫)。",
        "_prereg": ["docs/預註冊_FaceRedesignV2_草案.md §5-2",
                    "docs/預註冊_FaceRedesignV2_第二批_B層草案.md §0-1 / §7",
                    "docs/勘誤_Gate1_PerArmBaseline.md"],
        "executed_at_start": t0.isoformat(),
        "executed_at_end": t1.isoformat(),
        "command": " ".join(argv),
        "authorization_mechanism": ("外部授權 JSON 綁定 overlay sha256 + 命令列旗標;"
                                    "不使用原始碼常數(改碼會變更 runner hash 並使 overlay 失效)"),
        "provenance_overlay": ovl,
        "inputs": rep["inputs"],
        "v0_panel": {"path": rep["v0_panel_path"], "sha256": rep["v0_panel_sha256"]},
        "return_line": rep["return_line"],
        "candidate_score": rep["candidate_score"],
        "clock": rep["clock"],
        "frozen": rep["frozen"],
        "baseline_idx": rep["baseline_idx"],
        "baseline_idx_map": rep["baseline_idx_map"],
        "common_sample": rep["common_sample"],
        "preflight_checks": rep["preflight_checks"],
        "arms": list(ALL_ARMS),
        "results": res,
        "runner_sha256": rep["runner_sha256"],
        "frozen_impl_sha256": rep["frozen_impl_sha256"],
        "performance_analysis_executed": False,
        "note_no_performance": ("本次只執行 Gate 1。未執行 CAGR / Sharpe / MDD / 累積報酬 / "
                                "策略績效排名,亦未計算 V0-C3 的績效(第二批 R1 時序限制)。"),
    }


# ==============================================================================
BLOCKER = """\
⏸ 正式 Gate 1 **暫緩執行** —— 統計阻斷點已解除,但本輪仍 fail-closed。

原阻斷點(凍結函式只支援單一 baseline,與第二批 §0-1 的 V0-C3 條款衝突)
已由 Codex 2026-08-02 裁決採 per-arm baseline 解決,勘誤見
`docs/勘誤_Gate1_PerArmBaseline.md`,實作見 `gate1_delta_ic_maxt._delta_ic_matrix()`。

正式執行分支(`run_gate1()` + `build_execution_manifest()`)**已實作並通過合成測試**,
overlay 驗證與 preflight 也都已跑過。擋住的是最後的**武裝閘門**:

  Codex 2026-08-02:「先只完成正式執行分支的程式與合成測試,不執行 candidate Gate 1……
  完成後再交我審查一次,才執行首次正式 permutation。」

Gate 1 是**單發射擊** —— 跑完 T* 就定了。開火需要**兩把鑰匙**同時到位:

  1. 命令列旗標 `--i-am-executing-the-frozen-gate`
  2. `--authorization <file.json>`,內容須綁定當前 overlay 的 sha256

授權是**外部檔案**而非原始碼常數:改原始碼會變更 runner 的 sha256,
而 runner hash 記在已驗過的 overlay 裡 —— 那會讓「授權」本身破壞 provenance。
樣板:`--print-authorization-template`(印樣板不構成授權,建立檔案才是)。

授權與認領全部在**讀取任何 candidate 面板之前**完成;
`GATE1_EXECUTION_STARTED.json` 以 exclusive create 落地作為單發射擊的認領。
STARTED / MANIFEST / FAILURE 任一存在即拒絕執行,失敗時 STARTED **不刪除**,
另寫 FAILURE 紀錄;重跑須人工封存 + 新授權。

開火時以下列宣告呼叫凍結函式(已驗證,見 preflight 的 baseline_idx 區塊),
G1-a 與 G1-c **共用同一份** mapping:

       baseline_idx = [-1, -1, -1, -1, -1, -1, 5, 5, 5, 5, 5, 5]

本輪未執行任何 permutation、未產生任何 T* / ΔIC / t / p-value。
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("preflight", "gate"), default="preflight")
    ap.add_argument(ARM_FLAG, dest="armed", action="store_true",
                    help="正式開火的第一把鑰匙(第二把是 --authorization)")
    ap.add_argument("--authorization", default=None,
                    help="Gate 1 授權 JSON,內容須綁定當前 overlay 的 sha256")
    ap.add_argument("--print-authorization-template", action="store_true",
                    help="印出授權檔樣板(印樣板不構成授權,建立檔案才是)")
    a = ap.parse_args()

    t0 = datetime.now(timezone.utc).astimezone()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = " ".join([os.path.basename(sys.argv[0])] + sys.argv[1:])

    import build_gate1_provenance_overlay as OVL
    if a.print_authorization_template:
        print(json.dumps(authorization_template(OVL.OUT), ensure_ascii=False, indent=2))
        print(f"\n# 存成檔案後以 --authorization <path> 提供。"
              f"\n# 綁定的 overlay:{OVL.OUT}")
        return

    print("=" * 92)
    print("Gate 1 —— 正式 12-arm candidate assembly runner")
    print("=" * 92)
    print(f"開始 : {t0.isoformat()}")
    print(f"命令 : {cmd}")

    ovl = auth = started = None
    if a.part == "gate":
        # =====================================================================
        # 步驟 1-3 **完全不碰 candidate** —— 只讀命令列、授權檔與 overlay 檔本身。
        #
        # ⚠ 順序是刻意的(Codex 2026-08-02 複核指出的漏洞):
        #   `verify_overlay_or_die()` 的 47 項檢查**本身就會逐檔讀取並雜湊
        #   12 個 candidate panel 與 V0**。把它排在授權之前,等於未授權的呼叫
        #   照樣讀了 candidate。所以它被移到 STARTED 認領之後(步驟 4)。
        # =====================================================================
        print("\n[1/6] 命令列武裝旗標 …")
        if not a.armed:
            print(BLOCKER)
            raise SystemExit(2)
        print(f"      ✅ {ARM_FLAG}")

        print("[2/6] 驗證授權檔(綁定 overlay 檔本身的 sha256)…")
        auth = load_authorization(a.authorization, OVL.OUT)
        print(f"      ✅ {auth['path']}  sha256={auth['sha256'][:16]}…")

        print(f"[3/6] 認領執行(exclusive create {STARTED_NAME})…")
        started = claim_execution(
            started_path=OUT_DIR / STARTED_NAME,
            manifest_path=OUT_DIR / MANIFEST_NAME,
            failure_path=OUT_DIR / FAILURE_NAME,
            payload={
                "_what": "Gate 1 正式執行的認領紀錄。在讀取任何 candidate 面板之前落地。",
                "started_at": t0.isoformat(), "command": cmd,
                "overlay_sha256": auth["overlay_sha256"],
                "runner_sha256": sha256_file(Path(__file__).resolve()),
                "frozen_impl_sha256": sha256_file(_HERE / "gate1_delta_ic_maxt.py"),
                "authorization_path": auth["path"],
                "authorization_sha256": auth["sha256"],
                "baseline_idx": list(BASELINE_IDX),
                "baseline_map": {arm: ("V0" if BASELINE_IDX[k] == V0_BASELINE
                                       else f"arm_{ALL_ARMS[BASELINE_IDX[k]]}")
                                 for k, arm in enumerate(ALL_ARMS)},
                "n_perm": N_PERM, "seed": SEED, "alpha": ALPHA,
                "note": "本檔失敗時亦不得刪除;重跑須人工封存 + 新授權。",
            })
        print(f"      ✅ 已落地 {OUT_DIR / STARTED_NAME}")

        # ---- 步驟 4-5:此後才可讀取／雜湊 candidate。失敗一律保留 STARTED + 寫 FAILURE ----
        try:
            print("[4/6] 驗證 Gate 1 provenance overlay(逐檔重算,含 candidate)…")
            ovl = verify_overlay_or_die()
            print(f"      ✅ {ovl['items_verified']} 項雜湊相符")

            print("[5/6] 組裝 + preflight …")
            d, rep = assemble()
            rep, blk = preflight(d, rep)
            if not rep["preflight_passed"]:
                raise RuntimeError("preflight 未全過")
        except BaseException as exc:                      # noqa: BLE001
            write_failure_record(failure_path=OUT_DIR / FAILURE_NAME,
                                 started=started, error=exc)
            print(f"❌ 失敗,STARTED 保留(禁止重跑),失敗紀錄 → {OUT_DIR / FAILURE_NAME}")
            raise
    else:
        d, rep = assemble()
        rep, blk = preflight(d, rep)
    rep["run_started_at"] = t0.isoformat()
    rep["runner_path"] = str(Path(__file__).resolve())
    rep["runner_sha256"] = sha256_file(Path(__file__))
    rep["frozen_impl_path"] = str(_HERE / "gate1_delta_ic_maxt.py")
    rep["frozen_impl_sha256"] = sha256_file(_HERE / "gate1_delta_ic_maxt.py")
    rep["manifest_sha256"] = sha256_file(PROV) if PROV.exists() else None
    rep["performance_analysis_executed"] = False
    rep["note_no_performance"] = ("本次未執行 CAGR / Sharpe / MDD / 累積報酬 / 任何策略績效"
                                  "或 Gate 1 以外的 candidate OOS 分析。")

    hr("輸入")
    print(f"V0 面板       : {Path(rep['v0_panel_path']).name}  "
          f"sha256={rep['v0_panel_sha256'][:16]}…")
    print(f"主時鐘        : {OOS_LO} ~ {OOS_HI}   "
          f"{rep['rows_before_clock']:,} → {rep['rows_after_clock']:,} 列  "
          f"{rep['as_of_in_clock']} 個 as_of")
    print(f"報酬線        : {RET_COL}(exec_ret)  非缺 {rep['return_line']['notna_rows']:,} 列")
    print(f"候選分數欄    : {REAL_COMP_COL}(真身)")
    print(f"產業欄        : tej_ind_name → _ind,{rep['n_industries']} 類")
    print(f"\n{'arm':<5}{'baseline':<9}{'面板列數':>10}{'dup':>5}{'scErr':>7}"
          f"{'時鐘內缺值':>11}{'coverage':>10}  sha256")
    for arm in ALL_ARMS:
        i = rep["inputs"][arm]
        c = rep["arm_coverage_in_clock"][arm]
        print(f"{arm:<5}{i['baseline']:<9}{i['rows_full_panel']:>10,}{i['duplicate_keys']:>5}"
              f"{i['score_error']:>7}{c['missing_in_clock']:>11,}{c['coverage']:>10.6f}  "
              f"{i['sha256'][:16]}…")

    hr("Preflight")
    cs = rep["common_sample"]
    # 只讀不寫 —— 判定由 preflight() 產出(見該函式 §6)
    for name, ok in rep["preflight_checks"].items():
        print(f"  {'✅' if ok else '❌'} {name}")

    print(f"\nbaseline 宣告表(硬編碼,已驗證):")
    print(f"  baseline_idx = {rep['baseline_idx']}")
    print(f"  {'索引':<5}{'arm':<6}{'base':<10}")
    for k, arm in enumerate(ALL_ARMS):
        print(f"  {k:<5}{arm:<6}{rep['baseline_idx_map'][arm]:<10}")
    print(f"  G1-a / G1-c 共用同一份 mapping : {rep['baseline_shared_by_g1a_and_g1c']}")
    print(f"  凍結函式已 import(本輪未呼叫):"
          f"{delta_ic_t.__name__} / {joint_maxt_null.__name__}")

    print(f"\n共同月份 M*   : {cs['n_months_M_star']} 個月  "
          f"({cs['months_first'][0]} … {cs['months_last'][-1]})")
    print(f"共同股票 |I(t)| : min {cs['n_stocks_per_month_min']} / "
          f"median {cs['n_stocks_per_month_median']:.0f} / max {cs['n_stocks_per_month_max']}")
    print(f"因 min_n<{MIN_N} 剔除的月份 : {cs['dropped_months'] or '無'}")
    print(f"各 arm 造成的額外剔除列數 : {rep['rows_excluded_by_each_arm']}")

    t1 = datetime.now(timezone.utc).astimezone()
    rep["run_finished_at"] = t1.isoformat()

    if a.part == "gate":
        # ---- 步驟 6:正式開火(單發射擊;STARTED 已在讀面板之前落地)----
        exec_out = OUT_DIR / MANIFEST_NAME
        print(f"[6/6] 執行凍結 Gate 1(N_PERM={N_PERM} × 2 版,seed={SEED})…")
        # 開火 + 組 manifest + 原子落地 **在同一個 failure-handled 區塊內**。
        # 舊版把封存放在 try 之外:輸出階段一掛,STARTED 留著卻沒有 FAILURE,
        # 而且那一槍算出來的結果會直接遺失(Codex 2026-08-02 最終複核)。
        res = man = None
        try:
            res = run_gate1(blk["blocks_a"], blk["info_a"],
                            blk["blocks_c"], blk["info_c"], BASELINE_IDX)
            t1 = datetime.now(timezone.utc).astimezone()
            man = assemble_execution_manifest(
                rep=rep, res=res, ovl=ovl, auth=auth, started=started,
                t0=t0, t1=t1,
                argv=[os.path.basename(sys.argv[0])] + sys.argv[1:],
                started_path=OUT_DIR / STARTED_NAME)
            atomic_write_json(exec_out, man)
        except BaseException as exc:                      # noqa: BLE001
            # 失敗**不刪 STARTED** —— 抹掉痕跡會讓下一次被當成首發。
            fired = res is not None
            write_failure_record(
                failure_path=OUT_DIR / FAILURE_NAME, started=started, error=exc,
                candidate_statistics_computed=fired,
                # 已擊發但封存失敗 → 把結果與(可能已組好的)manifest 一起留下,
                # 否則那一槍就永久遺失,而重跑構成第二次射擊。
                recovery_payload=({"results": res, "manifest": man} if fired else None))
            print(f"❌ 執行失敗,STARTED 保留,失敗紀錄 → {OUT_DIR / FAILURE_NAME}")
            if fired:
                print("⚠ **單發已擊發** —— 正式結果保存在 FAILURE 的 recovery_payload,"
                      "不得靠重跑取得。")
            raise

        hr("Gate 1 判定")
        print(f"T*      = {res['G1a']['T_star']:.4f}   "
              f"T*_ind = {res['G1c']['T_star']:.4f}   M* = {res['n_months_M_star']} 月")
        print(f"{'arm':<5}{'base':<8}{'t(G1a)':>9}{'p_adj':>9}"
              f"{'t(G1c)':>9}{'p_adj':>9}{'判定':>8}")
        for k, arm in enumerate(ALL_ARMS):
            print(f"{arm:<5}{rep['baseline_idx_map'][arm]:<8}"
                  f"{res['G1a']['t'][k]:>9.3f}{res['G1a']['p_adj'][k]:>9.4f}"
                  f"{res['G1c']['t'][k]:>9.3f}{res['G1c']['p_adj'][k]:>9.4f}"
                  f"{('✅ 通過' if res['passed'][k] else '—'):>8}")
        print(f"\n判定規則 : {res['decision_rule']}")
        print(f"→ {exec_out}")
        return

    rep["gate_executed"] = False
    rep["gate_blocker"] = BLOCKER
    out = OUT_DIR / "gate1_preflight.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    print(f"\n結束 : {t1.isoformat()}")
    print(f"→ {out}")
    print("\n⚠ 未執行正式 Gate 1(permutation / T* / ΔIC 全部未跑)。原因見 --part gate。")


if __name__ == "__main__":
    main()
