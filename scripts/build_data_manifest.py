# -*- coding: utf-8 -*-
"""build_data_manifest.py — 為 tej_exports/DataExport0806 建立 SHA-256 manifest。

DataExport0806 是新的唯一 authoritative raw snapshot (取代 tej_exports/inbox*)。
本腳本逐檔算 SHA-256 + 大小 + mtime,輸出：
  tej_exports/DataExport0806_manifest.csv   —— relpath,size_bytes,sha256,mtime_iso
  tej_exports/DataExport0806_manifest.sha256 —— `sha256sum -c` 相容格式

用法:
  python scripts/build_data_manifest.py
  python scripts/build_data_manifest.py --verify   # 用既有 manifest 逐檔重算並比對，不寫檔
"""
import csv
import hashlib
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "tej_exports" / "DataExport0806"
CSV_OUT = PROJECT_ROOT / "tej_exports" / "DataExport0806_manifest.csv"
SHA256_OUT = PROJECT_ROOT / "tej_exports" / "DataExport0806_manifest.sha256"

CHUNK = 8 * 1024 * 1024


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def walk_files():
    return sorted(
        p for p in DATA_ROOT.rglob("*") if p.is_file()
    )


def build():
    files = walk_files()
    if not files:
        raise FileNotFoundError(f"{DATA_ROOT} 底下沒有任何檔案")

    rows = []
    for i, p in enumerate(files, 1):
        rel = p.relative_to(DATA_ROOT).as_posix()
        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        digest = sha256_of(p)
        rows.append((rel, size, digest, mtime))
        print(f"[{i}/{len(files)}] {digest[:12]}  {size:>12,}  {rel}", file=sys.stderr)

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["relpath", "size_bytes", "sha256", "mtime_utc"])
        w.writerows(rows)

    with open(SHA256_OUT, "w", encoding="utf-8", newline="\n") as f:
        for rel, _size, digest, _mtime in rows:
            f.write(f"{digest}  {rel}\n")

    total_bytes = sum(r[1] for r in rows)
    print(f"\n{len(rows)} 檔，共 {total_bytes:,} bytes ({total_bytes/1e9:.2f} GB)", file=sys.stderr)
    print(f"寫入 {CSV_OUT}", file=sys.stderr)
    print(f"寫入 {SHA256_OUT}", file=sys.stderr)


def verify():
    if not CSV_OUT.exists():
        raise FileNotFoundError(f"找不到既有 manifest：{CSV_OUT}，請先不帶 --verify 執行一次")

    with open(CSV_OUT, encoding="utf-8") as f:
        expected = {row["relpath"]: row for row in csv.DictReader(f)}

    actual_files = {p.relative_to(DATA_ROOT).as_posix() for p in walk_files()}
    expected_files = set(expected)

    missing = expected_files - actual_files      # manifest 有記錄，但檔案不見了
    extra = actual_files - expected_files         # 檔案存在，但 manifest 沒記錄過（新增/未收錄）
    mismatched = []

    for rel in sorted(expected_files & actual_files):
        p = DATA_ROOT / rel
        digest = sha256_of(p)
        if digest != expected[rel]["sha256"]:
            mismatched.append(rel)
        else:
            print(f"OK    {rel}", file=sys.stderr)

    if missing:
        print(f"\n缺少 {len(missing)} 檔（manifest 有、實際沒有）:", file=sys.stderr)
        for r in sorted(missing):
            print(f"  MISSING  {r}", file=sys.stderr)
    if extra:
        print(f"\n多出 {len(extra)} 檔（實際有、manifest 沒收錄）:", file=sys.stderr)
        for r in sorted(extra):
            print(f"  EXTRA    {r}", file=sys.stderr)
    if mismatched:
        print(f"\n{len(mismatched)} 檔 SHA-256 不符:", file=sys.stderr)
        for r in mismatched:
            print(f"  MISMATCH {r}", file=sys.stderr)

    ok = not missing and not extra and not mismatched
    print("\n" + ("PASS：manifest 與實際檔案完全吻合" if ok else "FAIL：manifest 與實際檔案不一致，見上方"), file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        sys.exit(verify())
    else:
        build()
