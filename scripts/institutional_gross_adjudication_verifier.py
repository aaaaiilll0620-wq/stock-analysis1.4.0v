# -*- coding: utf-8 -*-
"""institutional_gross_adjudication_verifier.py — 唯讀驗證器 (Round 10 review)。

只讀一份**已經存在**的 `institutional_gross_trust_holding_pct_adjudication.py`
產出的 receipt,獨立重新計算所有可驗證的東西並逐項比對,回報結果。

**這支腳本本身不寫任何檔案**:不呼叫
`institutional_gross_trust_holding_pct_adjudication.main()`,不建立新的
receipt,不碰任何 parquet cache 或 legacy supplement 的寫入路徑。它會讀取真實
的 old/new parquet 快取跟兩份原始 Excel (為了獨立重算 hash/manifest/anchor
統計/分類),但只讀不寫。

用法:python scripts/institutional_gross_adjudication_verifier.py <receipt_path>
"""
import json
import sys
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))
import institutional_gross_trust_holding_pct_adjudication as adj  # noqa: E402


def _sha256_of(path: Path) -> str:
    return adj._sha256_of(path)


def verify_receipt(receipt_path) -> dict:
    """回傳 `{"ok": bool, "checks": {name: bool}, "failures": {name: detail},
    "info": {name: value}}`。純唯讀:只讀檔案、重算、比對,不寫入任何東西、不
    呼叫 `institutional_gross_trust_holding_pct_adjudication.main()`。"""
    checks = {}
    failures = {}
    info = {}

    def check(name, condition, detail=None):
        ok = bool(condition)
        checks[name] = ok
        if not ok:
            failures[name] = detail

    receipt_path = Path(receipt_path)
    check("receipt_file_exists", receipt_path.exists(), {"path": str(receipt_path)})
    if not receipt_path.exists():
        return {"ok": False, "checks": checks, "failures": failures, "info": info}

    with open(receipt_path, encoding="utf-8") as f:
        r = json.load(f)

    # 純資訊性欄位 (供人交叉比對用),不是通過/失敗判定,不計入 ok。
    info["receipt_file_sha256"] = _sha256_of(receipt_path)
    info["verifier_script_sha256"] = _sha256_of(SCRIPT_PATH)

    # ---- 1. script/raw/parquet manifest hash ----
    check("script_hash_matches_current_file",
          r.get("script_sha256") == _sha256_of(adj.SCRIPT_PATH),
          {"receipt": r.get("script_sha256"), "actual": _sha256_of(adj.SCRIPT_PATH)})

    for name in ("old_raw", "new_raw"):
        entry = (r.get("raw_source_files") or {}).get(name, {})
        p = Path(entry.get("path", ""))
        actual = _sha256_of(p) if p.exists() else None
        check(f"{name}_hash_matches_current_file", p.exists() and entry.get("sha256") == actual,
              {"receipt": entry.get("sha256"), "actual": actual, "path": str(p)})

    actual_old_manifest = adj.build_manifest(adj.OLD_PARQUET_ROOT)
    actual_new_manifest = adj.build_manifest(adj.NEW_PARQUET_ROOT)
    check("old_parquet_manifest_matches_current",
          actual_old_manifest == (r.get("parquet_manifests") or {}).get("old"))
    check("new_parquet_manifest_matches_current",
          actual_new_manifest == (r.get("parquet_manifests") or {}).get("new"))

    # ---- 2. anchor 重現:獨立重算,不只信任 receipt 自己記錄的重算值 ----
    old = adj.load_parquet_dir(adj.OLD_PARQUET_ROOT)
    new = adj.load_parquet_dir(adj.NEW_PARQUET_ROOT)
    structural = adj.compute_structural_stats(old, new)
    cols, merged = adj.compute_six_column_stats(old, new)
    anchor_repro = r.get("anchor_reproduction") or {}
    check("structural_matches_receipt_claim", structural == anchor_repro.get("reproduced_structural"))
    check("columns_matches_receipt_claim", cols == anchor_repro.get("reproduced_columns"))

    anchor_path = Path(r.get("anchor_receipt_path", ""))
    if anchor_path.exists():
        with open(anchor_path, encoding="utf-8") as f:
            anchor = json.load(f)
        anchor_ig = (anchor.get("datasets") or {}).get("institutional_gross", {})
        check("structural_matches_true_anchor", adj.compare_structural_to_anchor(structural, anchor_ig) == [])
        check("columns_matches_true_anchor",
              adj.compare_columns_to_anchor(cols, anchor_ig.get("columns", {})) == [])
    else:
        check("anchor_receipt_exists", False, {"path": str(anchor_path)})

    # ---- 3. mismatch_records:存在、筆數、唯一鍵、必要欄位 ----
    records = r.get("mismatch_records")
    check("mismatch_records_present", isinstance(records, list) and len(records) > 0,
          {"type": type(records).__name__})
    total = (r.get("mismatch_scope") or {}).get("total_mismatch_instances")
    check("mismatch_records_count_matches_total",
          isinstance(records, list) and len(records) == total,
          {"records": len(records) if isinstance(records, list) else None, "total": total})

    if isinstance(records, list) and records:
        seen = set()
        dup_keys = []
        missing_field_records = []
        for rec in records:
            key = (rec.get("stock_id"), rec.get("date"), rec.get("column"))
            if key in seen:
                dup_keys.append(key)
            seen.add(key)
            missing = [f for f in adj.REQUIRED_RECORD_FIELDS if f not in rec]
            if missing:
                missing_field_records.append({"key": key, "missing": missing})
        check("mismatch_records_keys_unique", not dup_keys, {"duplicate_keys": dup_keys[:10]})
        check("mismatch_records_have_required_fields", not missing_field_records,
              {"examples": missing_field_records[:10]})

        # ---- 4. 摘要「只從 mismatch_records」重建,逐項比對 receipt 裡存的版本 ----
        rebuilt = adj.summarize_records(records)
        for field in ("classification_counts_overall", "classification_counts_by_column",
                      "classification_counts_by_stock", "classification_counts_by_date",
                      "diff_distribution_by_column"):
            check(f"{field}_reconstructs_from_records", rebuilt.get(field) == r.get(field))

        # ---- 5. RAW_SOURCES_DIFFER 的兩個驗證旗標必須全部是 true ----
        rsd = [rec for rec in records if rec.get("classification") == "RAW_SOURCES_DIFFER"]
        bad_rsd = [rec for rec in rsd
                   if not (rec.get("old_raw_matches_old_parquet") is True
                           and rec.get("new_raw_matches_new_parquet") is True)]
        check("all_raw_sources_differ_flags_true", not bad_rsd,
              {"bad_count": len(bad_rsd), "examples": bad_rsd[:5]})

        # ---- 6. unparseable 記錄要保留字面 raw_token,不能只剩 NaN ----
        unresolved = [rec for rec in records if rec.get("classification") == "UNRESOLVED_SCHEMA_OR_UNIT"]
        bad_tokens = [
            rec for rec in unresolved
            if not ((rec.get("old_raw_is_unparseable") and rec.get("old_raw_token") is not None)
                    or (rec.get("new_raw_is_unparseable") and rec.get("new_raw_token") is not None))
        ]
        check("unparseable_records_preserve_raw_token", not bad_tokens,
              {"bad_count": len(bad_tokens), "examples": bad_tokens[:5]})
    else:
        for name in ("mismatch_records_keys_unique", "mismatch_records_have_required_fields",
                      "all_raw_sources_differ_flags_true", "unparseable_records_preserve_raw_token"):
            check(name, False, {"reason": "mismatch_records missing or empty"})
        for field in ("classification_counts_overall", "classification_counts_by_column",
                      "classification_counts_by_stock", "classification_counts_by_date",
                      "diff_distribution_by_column"):
            check(f"{field}_reconstructs_from_records", False, {"reason": "mismatch_records missing or empty"})

    # ---- 7. status:沒有核准/選邊,一律 REVIEW_REQUIRED ----
    check("overall_status_is_review_required", r.get("overall_status") == "REVIEW_REQUIRED",
          {"actual": r.get("overall_status")})

    # ---- 8. 之前三份 receipt 的出處標記:路徑存在、雜湊吻合、狀態標籤正確 ----
    provenance = r.get("prior_receipts_provenance") or {}
    for name, expected in adj.PRIOR_RECEIPTS_PROVENANCE.items():
        entry = provenance.get(name, {})
        p = Path(entry.get("path", ""))
        actual_hash = _sha256_of(p) if p.exists() else None
        check(f"provenance_{name}_matches_current_file",
              p.exists() and entry.get("sha256") == actual_hash and entry.get("status") == expected["status"],
              {"expected_status": expected["status"], "recorded": entry, "actual_hash": actual_hash})

    ok = all(checks.values())
    result = {"ok": ok, "checks": checks, "failures": failures, "info": info}
    return result


def main():
    if len(sys.argv) != 2:
        print("用法:python scripts/institutional_gross_adjudication_verifier.py <receipt_path>",
              file=sys.stderr)
        sys.exit(2)
    result = verify_receipt(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
