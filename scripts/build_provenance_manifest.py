"""FaceRedesignV2 12 arm 面板的 provenance manifest。

**問題**:`build_arm_panel._git_commit()` 只讀 HEAD,不檢查工作區是否 dirty。
12 份面板的 `code_commit` 欄全部記 `b166dca`,但實作 arm 旗標的四個檔案從未 commit
—— 照面板記的 commit 檢出來重現會得到 V0,而且**不會報錯**。

本檔產出一個 bundle,讓 `HEAD + bundle` 能精確還原建置當下的程式樹:

    provenance/
      MANIFEST.json            ← 雜湊鏈 + 程式碼世代判定 + 面板/報告/稽核指紋
      worktree_tracked.patch   ← 已追蹤檔的完整 diff(套在 HEAD 上還原)
      untracked/               ← 未追蹤但建置有用到的 .py 原檔

**刻意不做的事**:不改任何面板、不改 `_git_commit()`、不 commit。
manifest 是**描述**現況的,不是修正現況的 —— 修正要等使用者決定怎麼補記已建好的面板。

用法:
    python -m scripts.build_provenance_manifest
    python -m scripts.build_provenance_manifest --check   # 只驗證既有 manifest,不覆寫
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RB_DIR = ROOT / "data" / "research_base"
ARM_DIR = RB_DIR / "arms"
OUT_DIR = ARM_DIR / "provenance"

ARMS = ("A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "B5", "C1", "C2", "C3")

# 建置有用到、但未被 git 追蹤的檔案 —— 光記雜湊不夠,內容要一起收進 bundle
UNTRACKED_CRITICAL = (
    "scripts/audit_arm_panel.py",
    "scripts/build_face_postprocess_arms.py",
    "tests/test_second_batch_arms.py",
    "tests/test_face_postprocess_arms.py",
)

# 雜湊範圍:這三個目錄下的所有 .py = arm 建置與稽核的 import 閉包上界
SOURCE_DIRS = ("core", "beat_0050", "scripts")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git(*args: str) -> str:
    # git 一律吐 UTF-8;本機 console 是 cp950,不指定會在中文 commit 訊息上炸開
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                   encoding="utf-8", errors="replace",
                                   stderr=subprocess.DEVNULL)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


# ==============================================================================
def collect_repo() -> tuple[dict, bytes]:
    head_full = git("rev-parse", "HEAD").strip()
    porcelain = [ln for ln in git("status", "--porcelain",
                                  "--untracked-files=all").splitlines() if ln.strip()]
    # 已追蹤檔的完整 diff。`--binary` 讓 patch 可無損還原;`-U10` 留足上下文。
    patch = subprocess.check_output(["git", "diff", "--binary", "-U10", "HEAD"],
                                    cwd=ROOT, stderr=subprocess.DEVNULL)
    rep = {
        "head_commit_short": git("rev-parse", "--short", "HEAD").strip(),
        "head_commit": head_full,
        "head_subject": git("log", "-1", "--format=%s").strip(),
        "head_committed_at": git("log", "-1", "--format=%cI").strip(),
        "is_dirty": bool(patch.strip()) or any(ln.startswith("??") for ln in porcelain),
        "tracked_modified": [ln[3:] for ln in porcelain if ln[:2].strip() == "M"],
        "untracked_count": sum(1 for ln in porcelain if ln.startswith("??")),
        "status_porcelain": porcelain,
        "tracked_diff_file": "worktree_tracked.patch",
        "tracked_diff_sha256": sha256_bytes(patch),
        "tracked_diff_bytes": len(patch),
    }
    return rep, patch


def collect_sources() -> dict:
    tracked = set(git("ls-files").splitlines())
    out = {}
    for d in SOURCE_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(ROOT).as_posix()
            st = p.stat()
            out[rel] = {
                "sha256": sha256_file(p),
                "bytes": st.st_size,
                "mtime": iso(st.st_mtime),
                "git_state": ("tracked" if rel in tracked else "UNTRACKED"),
            }
    return out


def collect_environment() -> dict:
    pkgs = {}
    for name in ("pandas", "numpy", "pyarrow", "scipy"):
        try:
            pkgs[name] = __import__(name).__version__
        except Exception as exc:                       # noqa: BLE001
            pkgs[name] = f"<不可用: {exc}>"
    return {
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": pkgs,
    }


def collect_panels(sources: dict) -> tuple[dict, dict]:
    """回傳 (每個 arm 的指紋, 程式碼世代判定)。

    世代判定:比對「arm 的建置**啟動**時刻」與「建置用源碼檔的最後修改時刻」。
    啟動時刻 = 面板 mtime − report 的 elapsed_sec(面板自己記錄的建置耗時)。
    """
    # 建置路徑上的源碼檔(不含稽核工具 —— 稽核在建置之後,不影響面板內容)
    build_sources = [k for k in sources
                     if k.startswith(("core/", "beat_0050/realbody/"))
                     or k == "scripts/build_face_postprocess_arms.py"]
    latest_src_mtime = max(sources[k]["mtime"] for k in build_sources)
    latest_src_file = max(build_sources, key=lambda k: sources[k]["mtime"])

    arms, epochs = {}, {}
    for arm in ARMS:
        panel = ARM_DIR / f"arm_{arm}_scores_adv100w_arm.parquet"
        report = panel.with_name(panel.stem + "_report.json")
        audit = ARM_DIR / f"arm_{arm}_integrity_audit.json"
        if not panel.exists():
            arms[arm] = {"ERROR": "面板不存在"}
            continue

        rep_j = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        aud_j = json.loads(audit.read_text(encoding="utf-8")) if audit.exists() else {}

        finished = panel.stat().st_mtime
        elapsed = rep_j.get("elapsed_sec")
        started = iso(finished - elapsed) if isinstance(elapsed, (int, float)) else None

        entry = {
            "panel": panel.name,
            "panel_sha256": sha256_file(panel),
            "panel_bytes": panel.stat().st_size,
            "panel_finished_at": iso(finished),
            "build_elapsed_sec": elapsed,
            "build_started_at": started,
            "report": report.name if report.exists() else None,
            "report_sha256": sha256_file(report) if report.exists() else None,
            "audit": audit.name if audit.exists() else None,
            "audit_sha256": sha256_file(audit) if audit.exists() else None,
            "rows": rep_j.get("produced") or aud_j.get("rows"),
            "coverage": rep_j.get("coverage") or aud_j.get("coverage"),
            "postprocess_only": bool(rep_j.get("postprocess_only")),
            "code_commit_recorded_in_panel": None,   # 下面填
            "audit_passed": aud_j.get("passed"),
            "audit_failures": aud_j.get("failures", []),
        }

        # 面板自己記的 code_commit —— 這正是有問題的那個欄位
        try:
            import pandas as pd
            col = pd.read_parquet(panel, columns=["code_commit"])
            entry["code_commit_recorded_in_panel"] = str(col["code_commit"].iloc[0])
        except Exception as exc:                     # noqa: BLE001
            entry["code_commit_recorded_in_panel"] = f"<讀取失敗: {exc}>"

        if started is not None:
            entry["code_epoch"] = ("epoch-2(= 現行工作區)" if started > latest_src_mtime
                                   else "epoch-1(早於現行工作區,原始碼未保存)")
            entry["code_epoch_basis"] = "啟動時刻(mtime − elapsed_sec)vs 源碼最後修改"
        elif iso(finished) < latest_src_mtime:
            # postprocess arm 的 report 沒有 elapsed_sec。但 started ≤ finished,
            # 而 finished 已早於源碼最後修改 → 啟動必然更早,epoch-1 是確定的,不是推測。
            entry["code_epoch"] = "epoch-1(早於現行工作區,原始碼未保存)"
            entry["code_epoch_basis"] = ("無 elapsed_sec;改用 finished < 源碼最後修改 "
                                         "→ started ≤ finished < 修改時刻,epoch-1 為確定結論")
        else:
            entry["code_epoch"] = "未知(report 無 elapsed_sec 且 finished 晚於源碼修改)"
            entry["code_epoch_basis"] = "無法判定"
        arms[arm] = entry

    epochs = {
        "判定方式": "arm 建置啟動時刻(面板 mtime − elapsed_sec) vs 建置路徑源碼檔的最後 mtime",
        "建置路徑源碼最後修改": {"file": latest_src_file, "mtime": latest_src_mtime},
        "epoch-1": sorted(a for a, e in arms.items()
                          if str(e.get("code_epoch", "")).startswith("epoch-1")),
        "epoch-2": sorted(a for a, e in arms.items()
                          if str(e.get("code_epoch", "")).startswith("epoch-2")),
        "⚠": ("epoch-1 的 arm 是用**早於現行工作區**的程式碼建的,那個版本沒有 commit 也沒有備份。"
              "本 bundle 的 patch 只還原得到 epoch-2。epoch-1 的可重現性必須另以"
              "『用 epoch-2 程式碼重跑並比對』的等價性實測來建立 —— 見 "
              "MANIFEST.json 的 epoch_equivalence_test 欄位。"),
    }
    return arms, epochs


def collect_v0() -> dict:
    p = RB_DIR / "realbody_scores_adv100w.parquet"
    return {"path": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size,
            "mtime": iso(p.stat().st_mtime)}


# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只驗證既有 manifest 的雜湊是否仍成立,不覆寫")
    a = ap.parse_args()

    manifest_path = OUT_DIR / "MANIFEST.json"

    if a.check:
        if not manifest_path.exists():
            raise SystemExit(f"❌ 沒有 manifest:{manifest_path}")
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        bad = []
        for rel, meta in old["source_files"].items():
            p = ROOT / rel
            if not p.exists():
                bad.append(f"{rel} 已不存在")
            elif sha256_file(p) != meta["sha256"]:
                bad.append(f"{rel} 內容已變更")
        for arm, e in old["arms"].items():
            p = ARM_DIR / e.get("panel", "")
            if e.get("panel_sha256") and p.exists() and sha256_file(p) != e["panel_sha256"]:
                bad.append(f"arm {arm} 面板已被改寫")
        print(f"manifest : {manifest_path}")
        print(f"產生於   : {old['generated_at']}")
        if bad:
            for m in bad:
                print(f"❌ {m}")
            raise SystemExit(f"❌ {len(bad)} 項與 manifest 不符 —— provenance 已失效。")
        print(f"✅ {len(old['source_files'])} 個源碼檔 + {len(old['arms'])} 個面板雜湊全部相符")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "untracked").mkdir(exist_ok=True)

    # 重生成不得清掉已回填的等價性實測 —— 但源碼若已變動,舊結果就不再適用,必須失效。
    prior_test, prior_note = None, None
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior_test = old.get("epoch_equivalence_test")
        if prior_test:
            prior_note = ("沿用前次 verify_epoch_equivalence 的結果;"
                          "若下方 repo.tracked_diff_sha256 與實測當時不同,此結果已失效,須重跑。")

    repo, patch = collect_repo()
    (OUT_DIR / "worktree_tracked.patch").write_bytes(patch)

    captured = {}
    for rel in UNTRACKED_CRITICAL:
        src = ROOT / rel
        if not src.exists():
            captured[rel] = "<不存在>"
            continue
        dst = OUT_DIR / "untracked" / Path(rel).name
        shutil.copy2(src, dst)
        captured[rel] = {"copied_to": f"untracked/{dst.name}", "sha256": sha256_file(src)}

    sources = collect_sources()
    arms, epochs = collect_panels(sources)

    manifest = {
        "_what": "FaceRedesignV2 12 arm 面板的完整 provenance。HEAD + worktree_tracked.patch "
                 "+ untracked/ = 建置當下的程式樹。",
        "_prereg": ["docs/預註冊_FaceRedesignV2_草案.md(第一批 A1-A4 + C1 + C3)",
                    "docs/預註冊_FaceRedesignV2_第二批_B層草案.md(第二批 B1-B5 + C2)"],
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "repo": repo,
        "untracked_captured": captured,
        "environment": collect_environment(),
        "source_files": sources,
        "v0_panel": collect_v0(),
        "arms": arms,
        "code_epochs": epochs,
        "epoch_equivalence_test": prior_test,   # 由 scripts/verify_epoch_equivalence.py 回填
        "epoch_equivalence_test_note": prior_note,
        "known_provenance_gaps": [
            "面板的 `code_commit` 欄記 HEAD 但工作區 dirty —— 該欄位單獨看會誤導,"
            "必須配本 manifest 的 tracked_diff_sha256 一起讀。",
            "arm B4 的 report `elapsed_sec` 與 chain log 的耗時不符,落地檔來自非 chain 的重跑"
            "(codex 曾用不同方式跑過 B4 並中斷);內容已過獨立稽核,但建置行程來源不唯一。",
            "epoch-1 的六個 arm 原始碼未保存,可重現性依賴等價性實測。",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    print("=" * 96)
    print("provenance manifest")
    print("=" * 96)
    print(f"HEAD          : {repo['head_commit_short']}  {repo['head_subject']}")
    print(f"dirty         : {repo['is_dirty']}  "
          f"(已追蹤修改 {len(repo['tracked_modified'])} 檔 / 未追蹤 {repo['untracked_count']} 項)")
    print(f"patch         : {repo['tracked_diff_bytes']:,} bytes  "
          f"sha256={repo['tracked_diff_sha256'][:16]}…")
    print(f"源碼指紋      : {len(sources)} 個 .py")
    print(f"未追蹤已收錄  : {len([v for v in captured.values() if isinstance(v, dict)])} 檔")
    print(f"V0 面板       : sha256={manifest['v0_panel']['sha256'][:16]}…")
    print()
    print(f"{'arm':<5}{'epoch':<28}{'rows':>9}{'audit':>8}  panel sha256")
    for arm in ARMS:
        e = arms[arm]
        print(f"{arm:<5}{str(e.get('code_epoch','?')):<28}"
              f"{(e.get('rows') or 0):>9,}{str(e.get('audit_passed')):>8}  "
              f"{str(e.get('panel_sha256'))[:16]}…")
    print()
    print(f"epoch-1 : {epochs['epoch-1']}")
    print(f"epoch-2 : {epochs['epoch-2']}")
    print()
    print(f"→ {manifest_path}")
    if prior_test:
        print(f"\nepoch 等價性實測:{prior_test.get('verdict')}")
        print(f"  已證可重現:{prior_test.get('epoch1_arms_proved_reproducible')}")
        if prior_test.get("epoch1_arms_NOT_proved"):
            print(f"  ❌ 未證:{prior_test['epoch1_arms_NOT_proved']}")
        print(f"  {prior_note}")
    else:
        print("\n⚠ epoch_equivalence_test 尚未回填 —— 在那之前,epoch-1 的六個 arm "
              "**不具備**可重現 provenance。跑 scripts.verify_epoch_equivalence。")


if __name__ == "__main__":
    main()
