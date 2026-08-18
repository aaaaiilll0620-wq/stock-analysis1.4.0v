# -*- coding: utf-8 -*-
"""DataExport0806 -> 網站 runtime overlay。

只發布最新低頻資料，不覆寫 `~/tej_cache`:
  - financial_statements:DataExport0806 財報目錄中最新匯出檔的所有列。
  - monthly_revenue:完整匯入後只保留最新月。

網站讀取時才與 frozen per-stock 歷史合併，overlay 對同鍵優先。
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tej_importer as ti

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "runtime_cache" / "dataexport0806"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    check = pd.read_parquet(tmp)
    if list(check.columns) != list(df.columns) or len(check) != len(df):
        raise RuntimeError(f"{target.name}:atomic staging 複驗失敗")
    os.replace(tmp, target)


def _preflight(dataset: str):
    spec = ti.DATASETS[dataset]
    files = ti._source_files(spec)
    ti._manifest_preflight(files, spec, dataset)
    return spec, files


def build_financial(output_dir: Path) -> dict:
    spec, files = _preflight("financial_statements")
    frames = []
    sources = []
    for priority, source in enumerate(sorted(files, key=lambda p: (p.stat().st_mtime_ns, p.name))):
        one = ti._load_one(source, spec)
        one["_runtime_source_priority"] = priority
        frames.append(one)
        sources.append({"source": source.relative_to(ti.DATA_ROOT).as_posix(),
                        "source_sha256": _sha256(source), "priority": priority})
    combined = pd.concat(frames, ignore_index=True, sort=False)
    latest_date = combined["date"].max()
    latest = combined[combined["date"] == latest_date].copy()
    duplicate_rows = int(latest.duplicated(["stock_id", "date"], keep=False).sum())
    duplicate_keys = int(latest.loc[
        latest.duplicated(["stock_id", "date"], keep=False), ["stock_id", "date"]
    ].drop_duplicates().shape[0])
    # Runtime overlay 的凍結規則:同季重複時，較晚匯出的 TEJ 檔是較新更正版。
    # 優先序與每份 source hash 寫進 receipt，不使用無記錄的 keep-last。
    df = (latest.sort_values(["stock_id", "date", "_runtime_source_priority"])
          .drop_duplicates(["stock_id", "date"], keep="last")
          .drop(columns=["_runtime_source_priority"])
          .reset_index(drop=True))
    ti._check_duplicate_key_conflicts(df, "financial_statements_runtime_overlay_resolved")
    target = output_dir / "financial_statements.parquet"
    _atomic_parquet(df, target)
    return {"sources_in_precedence_order": sources,
            "conflict_policy": "later_source_mtime_wins_with_manifest_hash_receipt",
            "duplicate_rows_seen": duplicate_rows, "duplicate_keys_resolved": duplicate_keys,
            "rows": len(df), "stocks": int(df.stock_id.nunique()),
            "date_min": str(df.date.min()), "date_max": str(df.date.max())}


def build_monthly(output_dir: Path) -> dict:
    _preflight("monthly_revenue")
    full = ti.load_source("monthly_revenue")
    latest_date = full["date"].max()
    df = full[full["date"] == latest_date].copy()
    ti._check_duplicate_key_conflicts(df, "monthly_revenue_runtime_overlay")
    target = output_dir / "monthly_revenue.parquet"
    _atomic_parquet(df, target)
    return {"source": "DataExport0806/monthly_revenue (latest month after full validation)",
            "rows": len(df), "stocks": int(df.stock_id.nunique()),
            "date_min": str(df.date.min()), "date_max": str(df.date.max())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--datasets", nargs="+", choices=("financial_statements", "monthly_revenue"),
                        default=("financial_statements", "monthly_revenue"))
    args = parser.parse_args()

    result = {}
    if "financial_statements" in args.datasets:
        result["financial_statements"] = build_financial(args.output_dir)
    if "monthly_revenue" in args.datasets:
        result["monthly_revenue"] = build_monthly(args.output_dir)
    receipt_path = args.output_dir / "receipt.json"
    existing = {}
    if receipt_path.exists():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8")).get("datasets", {})
        except Exception:
            existing = {}
    receipt = {"schema_version": "dataexport0806_runtime_overlay_v1",
               "built_at_utc": datetime.now(timezone.utc).isoformat(),
               "datasets": {**existing, **result}}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
