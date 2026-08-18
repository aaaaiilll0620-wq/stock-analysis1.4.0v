# -*- coding: utf-8 -*-
"""封存一次 Gate 1 執行嘗試 —— 移動而非刪除,並留下可稽核的封存 manifest。

Gate 1 是單發射擊:`GATE1_EXECUTION_STARTED.json` / `..._FAILURE.json` /
`..._MANIFEST.json` 任一存在,`claim_execution()` 就會按設計拒絕下一次執行。
要進行下一次嘗試,原路徑**必須清空** —— 但清空只能是「移走」,不能是「刪除」:
刪掉 STARTED 等於抹掉「已經開過一槍」的痕跡,下一次會被誤當首發。

本檔把該次嘗試的檔案移進 `archive/<attempt-id>/`,並寫一份封存 manifest,
記錄原始路徑、封存後路徑、每個檔案的 SHA-256、時間、封存理由,
以及**那一次到底有沒有擊發**(從 FAILURE 紀錄讀,不靠人工轉述)。

用法:
    python -X utf8 scripts/archive_gate1_attempt.py --id attempt1_xxx --reason "…"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE_DIR = ROOT / "beat_0050" / "results" / "gate1"
ARCHIVE_ROOT = GATE_DIR / "archive"

# 會阻擋下一次 claim 的檔案 + 該次嘗試綁定的授權檔
TARGETS = ("GATE1_EXECUTION_STARTED.json", "GATE1_EXECUTION_FAILURE.json",
           "GATE1_EXECUTION_MANIFEST.json", "gate1_authorization.json")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="封存識別碼,例如 attempt1_preflight_keyerror")
    ap.add_argument("--reason", required=True, help="封存理由(寫進 manifest)")
    a = ap.parse_args()

    dest = ARCHIVE_ROOT / a.id
    if dest.exists():
        raise SystemExit(f"❌ 封存目錄已存在:{dest} —— 換一個 --id,不得覆寫既有封存。")
    dest.mkdir(parents=True)

    moved, present = [], []
    for name in TARGETS:
        src = GATE_DIR / name
        if not src.exists():
            moved.append({"file": name, "existed": False})
            continue
        present.append(name)
        sha = sha256_file(src)
        dst = dest / name
        shutil.move(str(src), str(dst))
        moved.append({"file": name, "existed": True,
                      "original_path": str(src.relative_to(ROOT)).replace("\\", "/"),
                      "archived_path": str(dst.relative_to(ROOT)).replace("\\", "/"),
                      "sha256": sha,
                      "sha256_after_move": sha256_file(dst)})

    # 「有沒有擊發」從 FAILURE 紀錄讀,不靠人工轉述
    fired = None
    fpath = dest / "GATE1_EXECUTION_FAILURE.json"
    if fpath.exists():
        fired = bool(json.loads(fpath.read_text(encoding="utf-8"))
                     .get("candidate_statistics_computed", False))

    man = {
        "_what": "Gate 1 執行嘗試的封存紀錄。檔案是**移動**不是刪除。",
        "attempt_id": a.id,
        "archived_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "reason": a.reason,
        "files": moved,
        "files_present_at_archive": present,
        "candidate_statistics_computed": fired,
        "run_gate1_not_called": (fired is False),
        "no_execution_manifest": not (dest / "GATE1_EXECUTION_MANIFEST.json").exists(),
        "original_paths_cleared": [n for n in present
                                   if not (GATE_DIR / n).exists()],
        "note": ("原路徑已清空,下一次 claim_execution() 才不會按設計拒絕。"
                 "封存內容不得刪除 —— 它是「這一次嘗試存在過」的唯一證據。"),
    }
    out = dest / "ARCHIVE_MANIFEST.json"
    out.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 92)
    print(f"Gate 1 嘗試封存 — {a.id}")
    print("=" * 92)
    print(f"理由 : {a.reason}")
    for m in moved:
        if m["existed"]:
            print(f"  移動 {m['file']:<34} sha256={m['sha256'][:16]}…  → {m['archived_path']}")
        else:
            print(f"  (不存在){m['file']}")
    print(f"\ncandidate_statistics_computed : {man['candidate_statistics_computed']}")
    print(f"run_gate1_not_called          : {man['run_gate1_not_called']}")
    print(f"no_execution_manifest         : {man['no_execution_manifest']}")
    print(f"原路徑已清空                  : {man['original_paths_cleared']}")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
