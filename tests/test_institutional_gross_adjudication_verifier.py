# -*- coding: utf-8 -*-
"""synthetic 測試:scripts/institutional_gross_adjudication_verifier.py (Round 10
review)。

建立一份完全自足、自洽的合成 receipt + 合成 parquet/script/來源檔環境 (全部在
`tmp_path` 底下,透過 monkeypatch 換掉 `institutional_gross_trust_holding_pct_
adjudication` 模組的路徑常數),驗證 `verify_receipt()` 在合法輸入下回報 ok=True,
並在各種竄改/缺漏情境下正確回報 ok=False、失敗原因明確。**不讀取**任何真實的
`~/tej_cache`、round3 scratchpad 快取,或 `tej_exports/inbox_chip_gross`/
`DataExport0806` 底下的原始檔——這支驗證器本身是唯讀的,但這裡的測試連它會去讀
的路徑都是合成的,不會碰到真實資料。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

adj = pytest.importorskip("institutional_gross_trust_holding_pct_adjudication")
verifier = pytest.importorskip("institutional_gross_adjudication_verifier")


KEY_COLS = ["stock_id", "date"]


def _write_parquet_dir(root: Path, frames: dict):
    root.mkdir(parents=True, exist_ok=True)
    for sid, df in frames.items():
        df.to_parquet(root / f"{sid}.parquet", index=False)


@pytest.fixture
def synthetic_env(tmp_path, monkeypatch):
    """建一組完全自洽的合成環境:old/new parquet、假腳本檔、三份「前一輪」
    receipt 佔位檔,並把 `adj` 模組的路徑常數換成這些合成路徑。回傳一個可以
    用來組出合法 receipt、也可以自由竄改的 builder。"""
    old_root = tmp_path / "old_cache" / "institutional_gross"
    new_root = tmp_path / "new_cache" / "institutional_gross"
    old_df = pd.DataFrame({
        "stock_id": ["1101"], "date": ["2026-04-01"],
        "foreign_buy": [1000.0], "foreign_sell": [1000.0], "trust_buy": [1000.0],
        "trust_sell": [1000.0], "foreign_holding_pct": [13.0], "trust_holding_pct": [10.0],
    })
    new_df = pd.DataFrame({
        "stock_id": ["1101"], "date": ["2026-04-01"],
        "foreign_buy": [1000.0], "foreign_sell": [1000.0], "trust_buy": [1000.0],
        "trust_sell": [1000.0], "foreign_holding_pct": [13.0], "trust_holding_pct": [10.03],
    })
    _write_parquet_dir(old_root, {"1101": old_df})
    _write_parquet_dir(new_root, {"1101": new_df})
    monkeypatch.setattr(adj, "OLD_PARQUET_ROOT", old_root)
    monkeypatch.setattr(adj, "NEW_PARQUET_ROOT", new_root)

    fake_script = tmp_path / "fake_adjudication_script.py"
    fake_script.write_text("# synthetic stand-in for the adjudication script\n", encoding="utf-8")
    monkeypatch.setattr(adj, "SCRIPT_PATH", fake_script)

    prior = {}
    for name, status in (("round8", "diagnostic_superseded"),
                          ("round9_first", "diagnostic_invalid_accounting"),
                          ("round9_second", "diagnostic_post_deviation_unauthorized_rerun")):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps({"dummy": name}), encoding="utf-8")
        prior[name] = {"path": p, "status": status}
    monkeypatch.setattr(adj, "PRIOR_RECEIPTS_PROVENANCE", prior)

    old_raw = tmp_path / "old_raw.xlsx"
    new_raw = tmp_path / "new_raw.xlsx"
    old_raw.write_bytes(b"synthetic old raw excel stand-in")
    new_raw.write_bytes(b"synthetic new raw excel stand-in")

    anchor_path = tmp_path / "anchor.json"

    old_full = adj.load_parquet_dir(old_root)
    new_full = adj.load_parquet_dir(new_root)
    structural = adj.compute_structural_stats(old_full, new_full)
    cols, _ = adj.compute_six_column_stats(old_full, new_full)
    anchor_path.write_text(json.dumps({
        "old_root": str(old_root.parent), "new_root": str(new_root.parent),
        "datasets": {"institutional_gross": {**structural, "columns": cols}},
    }), encoding="utf-8")

    records = [{
        "stock_id": "1101", "date": "2026-04-01", "column": "trust_holding_pct",
        "mismatch_kind": "value_mismatch", "old_parquet": 10.0, "new_parquet": 10.03,
        "old_raw_token": "10.0", "new_raw_token": "10.03",
        "old_raw_parsed": 10.0, "new_raw_parsed": 10.03,
        "old_raw_is_blank": False, "new_raw_is_blank": False,
        "old_raw_is_unparseable": False, "new_raw_is_unparseable": False,
        "unit_scale": "none", "classification": "RAW_SOURCES_DIFFER",
        "signed_diff_new_minus_old": 0.03, "abs_diff": 0.03,
        "old_raw_matches_old_parquet": True, "new_raw_matches_new_parquet": True,
    }]
    summaries = adj.summarize_records(records)

    def _sha(p):
        return adj._sha256_of(Path(p))

    def build_receipt():
        return {
            "script_sha256": _sha(fake_script),
            "anchor_receipt_path": str(anchor_path),
            "anchor_reproduction": {"reproduced_structural": structural, "reproduced_columns": cols},
            "parquet_manifests": {"old": adj.build_manifest(old_root), "new": adj.build_manifest(new_root)},
            "raw_source_files": {
                "old_raw": {"path": str(old_raw), "sha256": _sha(old_raw)},
                "new_raw": {"path": str(new_raw), "sha256": _sha(new_raw)},
            },
            "mismatch_scope": {"total_mismatch_instances": len(records)},
            "mismatch_records": copy.deepcopy(records),
            **copy.deepcopy(summaries),
            "overall_status": "REVIEW_REQUIRED",
            "prior_receipts_provenance": {
                name: {"path": str(info["path"]), "sha256": _sha(info["path"]), "status": info["status"]}
                for name, info in prior.items()
            },
        }

    return build_receipt


def _write_receipt_file(tmp_path, receipt, name="receipt.json"):
    p = tmp_path / name
    p.write_text(json.dumps(receipt, ensure_ascii=False, default=str), encoding="utf-8")
    return p


# =============================================================================
# Happy path
# =============================================================================

def test_verify_receipt_passes_on_valid_synthetic_receipt(tmp_path, synthetic_env):
    receipt = synthetic_env()
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is True, result["failures"]
    assert all(result["checks"].values())


def test_verify_receipt_reports_false_for_missing_file(tmp_path):
    result = verifier.verify_receipt(tmp_path / "does_not_exist.json")
    assert result["ok"] is False
    assert result["checks"]["receipt_file_exists"] is False


# =============================================================================
# Tampering / omission scenarios — each must be caught, never silently pass
# =============================================================================

def test_verify_receipt_catches_tampered_script_hash(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["script_sha256"] = "0" * 64
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["script_hash_matches_current_file"] is False


def test_verify_receipt_catches_tampered_raw_hash(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["raw_source_files"]["old_raw"]["sha256"] = "0" * 64
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["old_raw_hash_matches_current_file"] is False


def test_verify_receipt_catches_tampered_parquet_manifest(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["parquet_manifests"]["old"][0]["sha256"] = "0" * 64
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["old_parquet_manifest_matches_current"] is False


def test_verify_receipt_catches_anchor_reproduction_mismatch(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["anchor_reproduction"]["reproduced_structural"]["old_key_count"] = 999
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["structural_matches_receipt_claim"] is False


def test_verify_receipt_catches_mismatch_records_count_mismatch(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["mismatch_scope"]["total_mismatch_instances"] = 999
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["mismatch_records_count_matches_total"] is False


def test_verify_receipt_catches_duplicated_record_key(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["mismatch_records"].append(dict(receipt["mismatch_records"][0]))
    receipt["mismatch_scope"]["total_mismatch_instances"] = len(receipt["mismatch_records"])
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["mismatch_records_keys_unique"] is False


def test_verify_receipt_catches_record_missing_required_field(tmp_path, synthetic_env):
    receipt = synthetic_env()
    del receipt["mismatch_records"][0]["abs_diff"]
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["mismatch_records_have_required_fields"] is False


def test_verify_receipt_catches_summary_not_reconstructible_from_records(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["classification_counts_overall"]["RAW_SOURCES_DIFFER"] = 999
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["classification_counts_overall_reconstructs_from_records"] is False


def test_verify_receipt_catches_false_raw_sources_differ_flag(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["mismatch_records"][0]["old_raw_matches_old_parquet"] = False
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["all_raw_sources_differ_flags_true"] is False


def test_verify_receipt_catches_unparseable_record_missing_raw_token(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["mismatch_records"][0]["classification"] = "UNRESOLVED_SCHEMA_OR_UNIT"
    receipt["mismatch_records"][0]["new_raw_is_unparseable"] = True
    receipt["mismatch_records"][0]["new_raw_token"] = None   # 文字證據不見了
    receipt["mismatch_records"][0]["old_raw_is_unparseable"] = False
    # 這筆現在分類變了,summaries 對不上是預期的另一個失敗,這個測試只關心
    # raw_token 這一項檢查本身有沒有正確觸發。
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["checks"]["unparseable_records_preserve_raw_token"] is False


def test_verify_receipt_catches_wrong_overall_status(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["overall_status"] = "APPROVED"
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["overall_status_is_review_required"] is False


def test_verify_receipt_catches_tampered_provenance_hash(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["prior_receipts_provenance"]["round8"]["sha256"] = "0" * 64
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["provenance_round8_matches_current_file"] is False


def test_verify_receipt_catches_wrong_provenance_status_label(tmp_path, synthetic_env):
    receipt = synthetic_env()
    receipt["prior_receipts_provenance"]["round9_first"]["status"] = "diagnostic_superseded"
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["provenance_round9_first_matches_current_file"] is False


def test_verify_receipt_catches_missing_mismatch_records(tmp_path, synthetic_env):
    receipt = synthetic_env()
    del receipt["mismatch_records"]
    p = _write_receipt_file(tmp_path, receipt)
    result = verifier.verify_receipt(p)
    assert result["ok"] is False
    assert result["checks"]["mismatch_records_present"] is False


def test_verify_receipt_never_writes_a_file(tmp_path, synthetic_env):
    """核心保證:驗證器不寫任何東西。跑完之後 tmp_path 底下的檔案集合不變。"""
    receipt = synthetic_env()
    p = _write_receipt_file(tmp_path, receipt)
    before = sorted(f.relative_to(tmp_path).as_posix() for f in tmp_path.rglob("*") if f.is_file())
    verifier.verify_receipt(p)
    after = sorted(f.relative_to(tmp_path).as_posix() for f in tmp_path.rglob("*") if f.is_file())
    assert before == after
