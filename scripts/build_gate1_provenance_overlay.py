# -*- coding: utf-8 -*-
"""Gate 1 專用的 provenance overlay。

**為什麼要 overlay 而不是重生成 MANIFEST**(Codex 2026-08-02 §1):
`data/research_base/arms/provenance/MANIFEST.json` 是 **12 個面板** 的固定 snapshot,
它凍結的是「這批面板是用什麼程式碼建的」。Gate 1 的勘誤動到
`scripts/gate1_delta_ic_maxt.py` —— 那是**分析**碼,不是**建置**碼,面板一個位元都沒變。
重生成 MANIFEST 會把面板 snapshot 與分析碼綁在一起,兩者的生命週期不同,
之後每改一次分析碼就得動一次面板 snapshot,反而讓「面板有沒有被改過」變得看不出來。

→ 本檔另建一層 overlay,**父節點記錄原 MANIFEST 的 sha256**,
   自己只記 Gate 1 這一層的產物。原 MANIFEST 一個位元都不動。

用法:
    python -X utf8 scripts/build_gate1_provenance_overlay.py
    python -X utf8 scripts/build_gate1_provenance_overlay.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT_MANIFEST = ROOT / "data" / "research_base" / "arms" / "provenance" / "MANIFEST.json"
ARM_DIR = ROOT / "data" / "research_base" / "arms"
OUT_DIR = ROOT / "beat_0050" / "results" / "gate1"
OUT = OUT_DIR / "GATE1_PROVENANCE_OVERLAY.json"
PATCH_NAME = "erratum_frozen_impl.patch"

# Gate 1 這一層的產物 —— 勘誤、被改的凍結實作、runner、兩份測試
TRACKED = {
    "erratum": "docs/勘誤_Gate1_PerArmBaseline.md",
    "frozen_impl": "scripts/gate1_delta_ic_maxt.py",
    "runner": "scripts/gate1_assemble_12arm.py",
    "test_frozen_11": "tests/test_gate1_delta_ic.py",
    "test_per_arm_baseline": "tests/test_gate1_per_arm_baseline.py",
    "test_overlay_check": "tests/test_gate1_overlay_check.py",
    "test_execution_branch": "tests/test_gate1_execution_branch.py",
    "test_cli_ordering": "tests/test_gate1_cli_ordering.py",
    "overlay_builder": "scripts/build_gate1_provenance_overlay.py",
    "archive_tool": "scripts/archive_gate1_attempt.py",
}

# 已封存的執行嘗試 —— 單發射擊的歷史證據,必須納入 --check(封存內容不得被竄改)
ARCHIVE_DIR = OUT_DIR / "archive"

# 僅記錄、**不納入 --check** 的產物。
# `gate1_preflight.json` 是 runner 每次執行都會重寫的**產物**,不是輸入 ——
# 把它列進 --check 會讓「跑一次 preflight」就使 overlay 失效(自我失效),
# 反而逼人習慣性重建 overlay,削弱它作為凍結證據的意義。
# 它的內容在正式執行時會被完整嵌進 GATE1_EXECUTION_MANIFEST.json,那才是權威紀錄。
INFORMATIONAL = {
    "preflight_output": "beat_0050/results/gate1/gate1_preflight.json",
}

TEST_CMD = ("python -X utf8 -m pytest tests/test_gate1_delta_ic.py "
            "tests/test_gate1_per_arm_baseline.py tests/test_gate1_overlay_check.py "
            "tests/test_gate1_execution_branch.py tests/test_gate1_cli_ordering.py -q")
FULL_TEST_CMD = "python -X utf8 -m pytest tests/ -q"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                   encoding="utf-8", errors="replace",
                                   stderr=subprocess.DEVNULL).strip()


def resolve_v0_path() -> Path:
    """Gate 1 **實際讀取**的 V0 面板路徑 —— 走 runner 走的同一條解析,不用寫死的檔名。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from lab_paths import resolve_realbody          # noqa: PLC0415
    return Path(resolve_realbody(1e6))


# ==============================================================================
# 逐檔重算的驗證核心
#   刻意寫成「吃 (label, path, expected_sha) 清單」的純函式:
#   `--check` 與合成測試共用同一段程式碼,測試才驗得到真正上線的那條路徑。
# ==============================================================================
def verify_fingerprints(items) -> list[str]:
    """對每一項**重新計算** sha256 並比對。回失敗訊息清單(逐項指名檔案)。"""
    fails = []
    for label, path, expected in items:
        p = Path(path)
        if not p.exists():
            fails.append(f"{label}:檔案不存在 → {p}")
            continue
        actual = sha256_file(p)
        if actual != expected:
            fails.append(f"{label}:內容已變更 → {p}\n"
                         f"      預期 {expected}\n      實得 {actual}")
    return fails


def build_check_items(ov: dict, parent: dict, *, root: Path,
                      arm_dir: Path, v0_path: Path,
                      parent_path: Path) -> list[tuple[str, Path, str]]:
    """組出 `--check` 要重算的**全部**項目。

    Codex 2026-08-02 指出的漏洞:舊版只驗父 manifest 本身與 Gate 1 檔案,
    12 個 panel hash 只是**抄錄**,面板被改寫仍會顯示通過。
    這裡把父 manifest 記錄的每一個資料產物都拉進來逐檔重算。
    """
    items: list[tuple[str, Path, str]] = []

    # (a) 父 manifest 本身
    items.append(("父 MANIFEST", parent_path, ov["parent"]["sha256"]))

    # (b) 12 個 arm 面板 —— 逐檔重算,不採信抄錄值
    for arm, sha in ov["parent"]["panel_sha256"].items():
        name = parent["arms"][arm]["panel"]
        items.append((f"arm {arm} 面板", arm_dir / name, sha))

    # (c) 12 份 report + 12 份 integrity audit
    for arm, sha in ov["parent"].get("report_sha256", {}).items():
        items.append((f"arm {arm} report", arm_dir / parent["arms"][arm]["report"], sha))
    for arm, sha in ov["parent"].get("audit_sha256", {}).items():
        items.append((f"arm {arm} audit", arm_dir / parent["arms"][arm]["audit"], sha))

    # (d) Gate 1 實際讀取的 V0 面板
    items.append(("V0 面板(Gate 1 實讀)", v0_path, ov["parent"]["v0_panel"]["sha256"]))

    # (e) Gate 1 本層產物
    for role, meta in ov["files"].items():
        items.append((f"Gate1 {role}", root / meta["path"], meta["sha256"]))

    # (f) 勘誤 patch 檔本身 —— 不可只驗它被記下來的值
    items.append(("勘誤 patch", root / ov["erratum"]["frozen_impl_patch_path"],
                  ov["erratum"]["frozen_impl_patch_sha256"]))

    # (g) 已封存的執行嘗試 —— 單發射擊的歷史證據,被竄改必須看得出來
    for attempt, meta in ov.get("prior_attempts", {}).items():
        for rel, sha in meta.get("files", {}).items():
            items.append((f"封存 {attempt}/{Path(rel).name}", root / rel, sha))
    return items


def cross_check_parent(ov: dict, parent: dict) -> list[str]:
    """overlay 抄錄的值必須與**父 manifest 的現行內容**一致。

    (b)(c)(d) 是「檔案 vs 抄錄值」;這裡是「抄錄值 vs 父檔現值」。
    兩者都要,否則改父檔 + 改 overlay 抄錄值就能對穿。
    """
    fails = []
    for arm, sha in ov["parent"]["panel_sha256"].items():
        live = parent.get("arms", {}).get(arm, {}).get("panel_sha256")
        if live != sha:
            fails.append(f"arm {arm} 面板 hash:overlay 抄錄 {sha} ≠ 父檔現值 {live}")
    live_v0 = parent.get("v0_panel", {}).get("sha256")
    if live_v0 != ov["parent"]["v0_panel"]["sha256"]:
        fails.append(f"V0 面板 hash:overlay 抄錄 {ov['parent']['v0_panel']['sha256']} "
                     f"≠ 父檔現值 {live_v0}")
    return fails


def run_tests(cmd: str) -> dict:
    """實際跑一次測試並記錄結果 —— overlay 不接受「聽說有過」。"""
    r = subprocess.run(cmd.split(), cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-1:]
    return {"command": cmd, "returncode": r.returncode,
            "summary": tail[0] if tail else "", "passed": r.returncode == 0}


def build() -> dict:
    if not PARENT_MANIFEST.exists():
        raise SystemExit(f"❌ 找不到父 manifest:{PARENT_MANIFEST}")
    parent = json.loads(PARENT_MANIFEST.read_text(encoding="utf-8"))

    files = {}
    for role, rel in TRACKED.items():
        p = ROOT / rel
        if not p.exists():
            raise SystemExit(f"❌ 缺 {role}:{p}")
        files[role] = {"path": rel, "sha256": sha256_file(p), "bytes": p.stat().st_size}

    informational = {}
    for role, rel in INFORMATIONAL.items():
        p = ROOT / rel
        informational[role] = ({"path": rel, "sha256": sha256_file(p),
                                "checked_by_check": False}
                               if p.exists() else {"path": rel, "sha256": None,
                                                   "checked_by_check": False})

    # 已封存的執行嘗試:逐檔記 hash,納入 --check
    prior_attempts = {}
    if ARCHIVE_DIR.exists():
        for d in sorted(p for p in ARCHIVE_DIR.iterdir() if p.is_dir()):
            man_p = d / "ARCHIVE_MANIFEST.json"
            entry = {"files": {}, "archive_manifest": None}
            for f in sorted(d.iterdir()):
                if f.is_file():
                    entry["files"][str(f.relative_to(ROOT)).replace("\\", "/")] = \
                        sha256_file(f)
            if man_p.exists():
                m = json.loads(man_p.read_text(encoding="utf-8"))
                entry["archive_manifest"] = {
                    "reason": m.get("reason"),
                    "archived_at": m.get("archived_at"),
                    "candidate_statistics_computed": m.get("candidate_statistics_computed"),
                    "run_gate1_not_called": m.get("run_gate1_not_called"),
                    "no_execution_manifest": m.get("no_execution_manifest"),
                }
            prior_attempts[d.name] = entry

    v0_path = resolve_v0_path()

    # 凍結實作相對 HEAD 的 diff —— 勘誤到底改了什麼,逐位元可查
    diff = subprocess.check_output(
        ["git", "diff", "--binary", "-U10", "HEAD", "--", TRACKED["frozen_impl"]],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    patch_path = OUT_DIR / PATCH_NAME
    patch_path.write_bytes(diff)

    ov = {
        "_what": ("Gate 1 專用 provenance overlay。父節點是 12 個面板的固定 snapshot;"
                  "本層只記 Gate 1 的勘誤、分析碼與測試。原 MANIFEST 未被修改。"),
        "_why_overlay": ("勘誤動到的是分析碼(gate1_delta_ic_maxt.py),不是建置碼,"
                         "面板一個位元都沒變 —— 面板 snapshot 與分析碼的生命週期不同,"
                         "綁在一起會讓「面板有沒有被改過」變得看不出來。"),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "parent": {
            "path": str(PARENT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(PARENT_MANIFEST),
            "generated_at": parent.get("generated_at"),
            "unmodified": True,
            "note": ("父 manifest 的 `--check` 現在會就 gate1_delta_ic_maxt.py 報一項不符 —— "
                     "那是本勘誤**授權且預期**的變更,12 個面板的 hash 全部仍相符。"
                     "父檔刻意不重生成,見 _why_overlay。"),
            "panels_still_matching": sorted(parent.get("arms", {}).keys()),
            "panel_sha256": {a: e.get("panel_sha256")
                             for a, e in parent.get("arms", {}).items()},
            "report_sha256": {a: e.get("report_sha256")
                              for a, e in parent.get("arms", {}).items()
                              if e.get("report_sha256")},
            "audit_sha256": {a: e.get("audit_sha256")
                             for a, e in parent.get("arms", {}).items()
                             if e.get("audit_sha256")},
            # Gate 1 **實際讀取**的 V0 面板(走 runner 同一條 resolve,不寫死檔名)
            "v0_panel": {
                "path": str(v0_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(v0_path),
                "matches_parent_manifest": (
                    sha256_file(v0_path) == parent.get("v0_panel", {}).get("sha256")),
            },
        },
        "erratum": {
            "id": "Gate1-PerArmBaseline",
            "ruling": "Codex 2026-08-02:採 per-arm baseline,12 arms 維持單一 joint max-t family",
            "clauses": ["E1 逐 arm 宣告配對基準", "E2 共用 M*/I(t)/置換索引;G1-c 兩腿同為中性化 rank",
                        "E3 max 跨全族 12 個 arm"],
            "baseline_idx": [-1, -1, -1, -1, -1, -1, 5, 5, 5, 5, 5, 5],
            "baseline_idx_map": {"A1": "V0", "A2": "V0", "A3": "V0", "A4": "V0",
                                 "C1": "V0", "C3": "V0",
                                 "B1": "arm_C3", "B2": "arm_C3", "B3": "arm_C3",
                                 "B4": "arm_C3", "B5": "arm_C3", "C2": "arm_C3"},
            "frozen_impl_patch": PATCH_NAME,
            "frozen_impl_patch_path": str(patch_path.relative_to(ROOT)).replace("\\", "/"),
            # 記的是**落地檔**重算出來的值,不是記憶體裡那份 diff 的值 ——
            # 兩者理應相同,但 --check 驗的是磁碟上那個檔(Codex §4)
            "frozen_impl_patch_sha256": sha256_file(patch_path),
        },
        "files": files,
        "informational_outputs": informational,
        "prior_attempts": prior_attempts,
        "tests": [run_tests(TEST_CMD), run_tests(FULL_TEST_CMD)],
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": {n: __import__(n).__version__ for n in ("numpy", "pandas")},
        },
        "git": {"head": git("rev-parse", "HEAD"),
                "head_short": git("rev-parse", "--short", "HEAD")},
        "gate1_executed": False,
        "candidate_statistics_produced": False,
        "note_not_executed": ("本輪未執行 permutation,未產生任何 candidate 的 "
                              "ΔIC / t / T* / p-value / 績效數字。--part gate 仍 fail-closed。"),
    }
    return ov


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    if a.check:
        if not OUT.exists():
            raise SystemExit(f"❌ 沒有 overlay:{OUT}")
        ov = json.loads(OUT.read_text(encoding="utf-8"))
        if not PARENT_MANIFEST.exists():
            raise SystemExit(f"❌ 找不到父 manifest:{PARENT_MANIFEST}")
        parent = json.loads(PARENT_MANIFEST.read_text(encoding="utf-8"))

        items = build_check_items(ov, parent, root=ROOT, arm_dir=ARM_DIR,
                                  v0_path=resolve_v0_path(),
                                  parent_path=PARENT_MANIFEST)
        fails = verify_fingerprints(items) + cross_check_parent(ov, parent)

        n_panel = len(ov["parent"]["panel_sha256"])
        n_rep = len(ov["parent"].get("report_sha256", {}))
        n_aud = len(ov["parent"].get("audit_sha256", {}))
        print("=" * 92)
        print("Gate 1 provenance overlay —— --check(逐檔重算)")
        print("=" * 92)
        print(f"重算項目 : 父 MANIFEST 1 + arm 面板 {n_panel} + report {n_rep} + "
              f"audit {n_aud} + V0 面板 1 + Gate1 產物 {len(ov['files'])} + 勘誤 patch 1 "
              f"= {len(items)} 項")
        print(f"另加交叉核對 : overlay 抄錄值 vs 父 manifest 現行內容 "
              f"({n_panel} 個面板 + V0)")
        for m in fails:
            print(f"❌ {m}")
        if fails:
            raise SystemExit(f"\n❌ {len(fails)} 項不符 —— Gate 1 provenance 失效,"
                             "不得執行正式 Gate 1。")
        print(f"\n✅ {len(items)} 項雜湊全部相符,抄錄值與父檔現行內容一致")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ov = build()
    OUT.write_text(json.dumps(ov, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 92)
    print("Gate 1 provenance overlay")
    print("=" * 92)
    print(f"父 MANIFEST   : {ov['parent']['path']}")
    print(f"  sha256      : {ov['parent']['sha256']}")
    print(f"  未修改      : {ov['parent']['unmodified']}  "
          f"(12 個面板 hash 全部仍相符)")
    print(f"Git HEAD      : {ov['git']['head']}")
    print(f"\n{'角色':<24}{'sha256':<66}路徑")
    for role, m in ov["files"].items():
        print(f"{role:<24}{m['sha256']:<66}{m['path']}")
    if ov.get("prior_attempts"):
        print("\n已封存的執行嘗試(納入 --check):")
        for k, v in ov["prior_attempts"].items():
            am = v.get("archive_manifest") or {}
            print(f"  {k}  檔案 {len(v['files'])} 個  "
                  f"已擊發={am.get('candidate_statistics_computed')}  "
                  f"無 manifest={am.get('no_execution_manifest')}")

    print(f"\n勘誤 patch    : erratum_frozen_impl.patch  "
          f"sha256={ov['erratum']['frozen_impl_patch_sha256'][:16]}…")
    print(f"baseline_idx  : {ov['erratum']['baseline_idx']}")
    print("\n測試(本檔實際重跑,不採信轉述):")
    for t in ov["tests"]:
        print(f"  {'✅' if t['passed'] else '❌'} {t['summary']}")
        print(f"     {t['command']}")
    print(f"\nGate 1 已執行 : {ov['gate1_executed']}   "
          f"candidate 統計已產生 : {ov['candidate_statistics_produced']}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
