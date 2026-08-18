# -*- coding: utf-8 -*-
"""scripts/build_v2_candidate.py 的 Phase A4 synthetic 測試——品質證據
sidecar(§C.9)、supplement_provenance(§C.10)、逐 dataset build receipt +
彙總 build receipt 完整版(§C.5)、11-dataset stop-on-first-failure 協調
(§D)、import 白名單靜態檢查(§C.6)。

跟 `test_build_v2_candidate.py`(Phase A2a-A3c)同一套紀律:只用本檔
synthetic fixture(寫在 `tmp_path` 底下),不讀取任何真實的
`tej_exports/DataExport0806*`/`~/tej_cache`/`tej_exports/inbox*`,不 import/
呼叫任何獨立 verifier(本輪尚未實作),不呼叫 `tej_importer.load_source()`
本身——orchestrator 測試一律用注入的假 `load_dataset_fn`。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

b = pytest.importorskip("build_v2_candidate")

VALID_HASH_A = "a" * 64
VALID_HASH_B = "b" * 64
VALID_HASH_C = "c" * 64
VALID_SNAPSHOT_ID = "a" * 64


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _cell_record(**overrides) -> dict:
    record = {
        "dataset": "price_valuation",
        "source_relpath": "個股股價、本益比2004-20260806/foo.xlsx",
        "source_file_sha256": VALID_HASH_A,
        "source_container_member": "sheet1",
        "source_row_number": 5,
        "stock_id": "2330",
        "date": "2020-01-02",
        "source_column": "收盤價",
        "target_column": "close",
        "raw_token": None,
        "is_blank": True,
        "is_unparseable": False,
        "parser": "pd.to_numeric",
        "unit_scale_applied": 1.0,
        "resulting_value": None,
        "dedup_key": None,
    }
    record.update(overrides)
    if record["dedup_key"] is None:
        record["dedup_key"] = b.dedup_key_v1(
            record["dataset"],
            record["source_relpath"],
            record["source_container_member"],
            record["source_row_number"],
            record["target_column"],
        )
    return record


def _unparseable_cell_record(**overrides) -> dict:
    base = {
        "is_blank": False,
        "is_unparseable": True,
        "raw_token": ".",
        "source_row_number": 6,
    }
    base.update(overrides)
    return _cell_record(**base)


# ----------------------------------------------------------------------------
# 1. dedup_key_v1
# ----------------------------------------------------------------------------


def test_dedup_key_v1_known_vector():
    key = b.dedup_key_v1("price_valuation", "a/b.xlsx", "sheet1", 5, "close")
    payload = b'["dedup_key_v1","price_valuation","a/b.xlsx","sheet1",5,"close"]'
    assert key == b.sha256_hex(payload)


def test_dedup_key_v1_null_container_member_uses_json_null():
    key = b.dedup_key_v1("tdcc_weekly", "a/b.zip", None, 1, "holders")
    payload = b'["dedup_key_v1","tdcc_weekly","a/b.zip",null,1,"holders"]'
    assert key == b.sha256_hex(payload)


def test_dedup_key_v1_rejects_non_int_row_number():
    with pytest.raises(ValueError):
        b.dedup_key_v1("d", "r", "m", "5", "t")


def test_dedup_key_v1_rejects_bool_row_number():
    with pytest.raises(ValueError):
        b.dedup_key_v1("d", "r", "m", True, "t")


def test_dedup_key_v1_one_field_change_alters_key():
    base = b.dedup_key_v1("d", "r", "m", 1, "t")
    assert b.dedup_key_v1("d2", "r", "m", 1, "t") != base
    assert b.dedup_key_v1("d", "r2", "m", 1, "t") != base
    assert b.dedup_key_v1("d", "r", "m2", 1, "t") != base
    assert b.dedup_key_v1("d", "r", "m", 2, "t") != base
    assert b.dedup_key_v1("d", "r", "m", 1, "t2") != base


# ----------------------------------------------------------------------------
# 2. quality sidecar (§C.9)
# ----------------------------------------------------------------------------


def test_build_quality_sidecar_round_trips_through_validate():
    records = [_cell_record(), _unparseable_cell_record()]
    sidecar = b.build_quality_sidecar(dataset="price_valuation", cell_records=records)
    assert sidecar["schema"] == b.QUALITY_SIDECAR_SCHEMA_TAG
    assert sidecar["record_count"] == 2
    b.validate_quality_sidecar(sidecar)


def test_build_quality_sidecar_rejects_wrong_field_set():
    bad = _cell_record()
    del bad["raw_token"]
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_build_quality_sidecar_rejects_dataset_mismatch():
    bad = _cell_record(dataset="institutional_flow")
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_blank": True, "is_unparseable": True},
        {"is_blank": False, "is_unparseable": False},
    ],
)
def test_build_quality_sidecar_rejects_blank_unparseable_not_mutually_exclusive(overrides):
    bad = _cell_record(**overrides)
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_build_quality_sidecar_rejects_raw_token_present_when_blank():
    bad = _cell_record(is_blank=True, is_unparseable=False, raw_token="oops")
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_build_quality_sidecar_rejects_missing_raw_token_when_unparseable():
    bad = _unparseable_cell_record(raw_token=None)
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_build_quality_sidecar_rejects_non_null_resulting_value():
    bad = _cell_record(resulting_value=1.0)
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_build_quality_sidecar_rejects_wrong_parser_literal():
    bad = _cell_record(parser="numpy.float64")
    with pytest.raises(ValueError):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_build_quality_sidecar_rejects_tampered_dedup_key():
    bad = _cell_record()
    bad["dedup_key"] = "f" * 64
    with pytest.raises(ValueError, match="dedup_key"):
        b.build_quality_sidecar(dataset="price_valuation", cell_records=[bad])


def test_write_quality_sidecar_exclusive_create(tmp_path):
    sidecar = b.build_quality_sidecar(
        dataset="price_valuation", cell_records=[_cell_record()]
    )
    path = tmp_path / "price_valuation.sidecar.json"
    abs_path, digest = b.write_quality_sidecar(path, sidecar)
    assert abs_path.exists()
    assert digest == b.sha256_hex(abs_path.read_bytes())
    with pytest.raises(ValueError, match="排他建立"):
        b.write_quality_sidecar(path, sidecar)


def test_write_quality_sidecar_rejects_invalid_content_without_writing(tmp_path):
    bad_sidecar = {"schema": b.QUALITY_SIDECAR_SCHEMA_TAG, "dataset": "x", "record_count": 1, "records": []}
    path = tmp_path / "x.sidecar.json"
    with pytest.raises(ValueError):
        b.write_quality_sidecar(path, bad_sidecar)
    assert not path.exists()


# ----------------------------------------------------------------------------
# 3. supplement_provenance (§C.10)
# ----------------------------------------------------------------------------


def _merge_profile(**overrides) -> dict:
    profile = {
        "pre_merge_row_count": 100,
        "post_merge_row_count": 100,
        "native_columns": ["stock_id", "date", "eps", "net_income", "operating_income"],
        "supplement_columns": ["roe_after_tax"],
        "rows_supplement_key_not_covered": 20,
    }
    profile.update(overrides)
    return profile


def test_build_supplement_provenance_happy_path():
    result = b.build_supplement_provenance(
        supplement_receipt_path="tej_exports/legacy_supplement/receipt.json",
        supplement_receipt_sha256=VALID_HASH_A,
        supplement_identity_value=VALID_HASH_A,
        affected_columns=["roe_after_tax"],
        merge_profile=_merge_profile(),
        rows_with_supplement_value=80,
    )
    sp = result["supplement_provenance"]
    assert sp["source_class"] == "LEGACY_DERIVED_SUPPLEMENT"
    assert sp["is_pit"] is False
    assert sp["non_overlap_assertion"]["overlap"] == []
    assert sp["row_counts"] == {
        "pre_merge_rows": 100,
        "post_merge_rows": 100,
        "rows_with_supplement_value": 80,
        "rows_supplement_key_not_covered": 20,
    }


def test_build_supplement_provenance_rejects_sha256_not_equal_to_identity():
    with pytest.raises(ValueError, match="supplement_identity"):
        b.build_supplement_provenance(
            supplement_receipt_path="p",
            supplement_receipt_sha256=VALID_HASH_A,
            supplement_identity_value=VALID_HASH_B,
            affected_columns=["roe_after_tax"],
            merge_profile=_merge_profile(),
            rows_with_supplement_value=80,
        )


def test_build_supplement_provenance_rejects_unsorted_affected_columns():
    with pytest.raises(ValueError, match="sorted"):
        b.build_supplement_provenance(
            supplement_receipt_path="p",
            supplement_receipt_sha256=VALID_HASH_A,
            supplement_identity_value=VALID_HASH_A,
            affected_columns=["z", "a"],
            merge_profile=_merge_profile(),
            rows_with_supplement_value=80,
        )


def test_build_supplement_provenance_rejects_column_overlap():
    profile = _merge_profile(native_columns=["stock_id", "date", "roe_after_tax"])
    with pytest.raises(ValueError, match="重疊"):
        b.build_supplement_provenance(
            supplement_receipt_path="p",
            supplement_receipt_sha256=VALID_HASH_A,
            supplement_identity_value=VALID_HASH_A,
            affected_columns=["roe_after_tax"],
            merge_profile=profile,
            rows_with_supplement_value=80,
        )


def test_build_supplement_provenance_rejects_row_count_expansion():
    profile = _merge_profile(post_merge_row_count=101)
    with pytest.raises(ValueError, match="post_merge_rows"):
        b.build_supplement_provenance(
            supplement_receipt_path="p",
            supplement_receipt_sha256=VALID_HASH_A,
            supplement_identity_value=VALID_HASH_A,
            affected_columns=["roe_after_tax"],
            merge_profile=profile,
            rows_with_supplement_value=80,
        )


def test_build_supplement_provenance_rejects_inconsistent_row_accounting():
    with pytest.raises(ValueError, match="rows_with_supplement_value"):
        b.build_supplement_provenance(
            supplement_receipt_path="p",
            supplement_receipt_sha256=VALID_HASH_A,
            supplement_identity_value=VALID_HASH_A,
            affected_columns=["roe_after_tax"],
            merge_profile=_merge_profile(),
            rows_with_supplement_value=79,  # 79 + 20 != 100
        )


def test_build_supplement_provenance_rejects_missing_merge_profile_key():
    profile = _merge_profile()
    del profile["rows_supplement_key_not_covered"]
    with pytest.raises(ValueError, match="缺少必要欄位"):
        b.build_supplement_provenance(
            supplement_receipt_path="p",
            supplement_receipt_sha256=VALID_HASH_A,
            supplement_identity_value=VALID_HASH_A,
            affected_columns=["roe_after_tax"],
            merge_profile=profile,
            rows_with_supplement_value=80,
        )


# ----------------------------------------------------------------------------
# 4. 逐 dataset build receipt (§C.5 第 1 項)
# ----------------------------------------------------------------------------


def _schema_metadata() -> dict:
    return {
        "logical_types": {"close": "float64"},
        "actual_dtypes": {"close": "float64"},
        "arrow_types": {"close": "double"},
    }


def _per_file_stage_one_counts(*, blank=1, unparseable=1) -> list:
    return [
        {
            "source_relpath": "a.xlsx",
            "source_file_sha256": VALID_HASH_A,
            "source_container_member": "sheet1",
            "counts": [
                {
                    "dataset": "price_valuation",
                    "source_column": "收盤價",
                    "target_column": "close",
                    "source_row_count": 10,
                    "column_present_row_count": 10,
                    "column_absent_row_count": 0,
                    "parsed_numeric_cell_count": 10 - blank - unparseable,
                    "blank_cell_count": blank,
                    "unparseable_cell_count": unparseable,
                }
            ],
        }
    ]


def _final_null_causes() -> dict:
    return {
        "close": {
            "RETAINED_BLANK": 1,
            "RETAINED_UNPARSEABLE": 1,
            "SOURCE_COLUMN_ABSENT": 0,
            "SUPPLEMENT_KEY_NOT_COVERED": 0,
            "OTHER_UNEXPLAINED": 0,
        }
    }


def _success_receipt_kwargs(**overrides) -> dict:
    kwargs = dict(
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        dataset="price_valuation",
        start_timestamp_utc="2026-08-16T00:00:00Z",
        end_timestamp_utc="2026-08-16T00:00:01Z",
        source_files=[["a.xlsx", VALID_HASH_A]],
        row_count=10,
        stock_count=1,
        date_min="2020-01-01",
        date_max="2020-01-10",
        schema_metadata=_schema_metadata(),
        coverage_matrix=[],
        duplicate_mapping=[],
        final_null_causes=_final_null_causes(),
        final_null_counts_from_output={"close": 2},
        sidecar_path="/tmp/x.sidecar.json",
        sidecar_sha256=VALID_HASH_B,
        sidecar_record_count=2,
        per_file_stage_one_counts=_per_file_stage_one_counts(),
        supplement_provenance=None,
    )
    kwargs.update(overrides)
    return kwargs


def test_build_per_dataset_receipt_success_round_trips_through_validate():
    receipt = b.build_per_dataset_receipt_success(**_success_receipt_kwargs())
    b.validate_per_dataset_receipt(receipt)
    assert receipt["status"] == b.DATASET_BUILD_SUCCEEDED
    assert receipt["exit_code"] == 0
    assert receipt["error"] is None


def test_build_per_dataset_receipt_success_rejects_sidecar_count_mismatch():
    kwargs = _success_receipt_kwargs(sidecar_record_count=99)
    with pytest.raises(ValueError, match="sidecar_record_count"):
        b.build_per_dataset_receipt_success(**kwargs)


def test_build_per_dataset_receipt_success_rejects_final_null_causes_mismatch():
    kwargs = _success_receipt_kwargs(final_null_counts_from_output={"close": 3})
    with pytest.raises(ValueError, match="final_null_causes"):
        b.build_per_dataset_receipt_success(**kwargs)


def test_build_per_dataset_receipt_success_rejects_final_null_causes_column_set_mismatch():
    kwargs = _success_receipt_kwargs(final_null_counts_from_output={"other": 2})
    with pytest.raises(ValueError, match="欄位集合不符"):
        b.build_per_dataset_receipt_success(**kwargs)


def test_build_per_dataset_receipt_success_rejects_unsorted_source_files():
    kwargs = _success_receipt_kwargs(
        source_files=[["b.xlsx", VALID_HASH_A], ["a.xlsx", VALID_HASH_B]]
    )
    with pytest.raises(ValueError, match="sorted"):
        b.build_per_dataset_receipt_success(**kwargs)


def test_build_per_dataset_receipt_success_rejects_bad_final_null_cause_keys():
    kwargs = _success_receipt_kwargs(final_null_causes={"close": {"WRONG_KEY": 2}})
    with pytest.raises(ValueError, match="final_null_causes"):
        b.build_per_dataset_receipt_success(**kwargs)


def test_build_per_dataset_receipt_failure_requires_nonzero_exit_code():
    with pytest.raises(ValueError, match="exit_code"):
        b.build_per_dataset_receipt_failure(
            snapshot_id_v1_value=VALID_SNAPSHOT_ID,
            run_id="run-1",
            dataset="price_valuation",
            start_timestamp_utc="t0",
            end_timestamp_utc="t1",
            exit_code=0,
            error_type="ValueError",
            error_message="boom",
        )


def test_build_per_dataset_receipt_failure_round_trips_through_validate():
    receipt = b.build_per_dataset_receipt_failure(
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        dataset="institutional_gross",
        start_timestamp_utc="t0",
        end_timestamp_utc="t1",
        exit_code=1,
        error_type="ValueError",
        error_message="欄位缺席",
    )
    b.validate_per_dataset_receipt(receipt)
    assert receipt["status"] == b.DATASET_BUILD_FAILED
    assert receipt["row_count"] is None
    assert receipt["source_files"] == []
    assert receipt["error"] == {"error_type": "ValueError", "error_message": "欄位缺席"}


def test_validate_per_dataset_receipt_rejects_succeeded_with_error_present():
    receipt = b.build_per_dataset_receipt_success(**_success_receipt_kwargs())
    receipt["error"] = {"error_type": "X", "error_message": "Y"}
    with pytest.raises(ValueError, match="error"):
        b.validate_per_dataset_receipt(receipt)


def test_validate_per_dataset_receipt_rejects_missing_field():
    receipt = b.build_per_dataset_receipt_success(**_success_receipt_kwargs())
    del receipt["row_count"]
    with pytest.raises(ValueError, match="欄位集合不符"):
        b.validate_per_dataset_receipt(receipt)


def test_write_per_dataset_receipt_exclusive_create(tmp_path):
    receipt = b.build_per_dataset_receipt_success(**_success_receipt_kwargs())
    path = tmp_path / "receipt.json"
    abs_path, digest = b.write_per_dataset_receipt(path, receipt)
    assert abs_path.exists()
    with pytest.raises(ValueError, match="排他建立"):
        b.write_per_dataset_receipt(path, receipt)


# ----------------------------------------------------------------------------
# 5. 彙總 build receipt 完整版 (§C.5 第 2 項)
# ----------------------------------------------------------------------------


def _identity_kwargs(**overrides) -> dict:
    kwargs = dict(
        manifest_identity=VALID_HASH_A,
        manifest_sha256_file_identity=VALID_HASH_B,
        supplement_identity=VALID_HASH_C,
        importer_identity=VALID_HASH_A,
        extractor_identity=VALID_HASH_B,
        builder_identity=VALID_HASH_C,
        dependency_lock_identity=VALID_HASH_A,
        runtime_environment_identity_v1_value=VALID_HASH_B,
        preregistration_commit="deadbeef",
    )
    kwargs.update(overrides)
    return kwargs


def _per_dataset_entry(dataset: str, digest: str = VALID_HASH_A) -> dict:
    return {"dataset": dataset, "path": f"/tmp/{dataset}.json", "sha256": digest}


_ELEVEN_DATASETS = (
    "price_valuation", "institutional_flow", "fundamentals_quarterly",
    "revenue_growth", "monthly_revenue", "financial_statements",
    "institutional_gross", "margin_balance", "industry_map", "tdcc_weekly",
    "director_pledge",
)


def _aggregate_kwargs(**overrides) -> dict:
    kwargs = dict(
        **_identity_kwargs(),
        run_id="run-1",
        authorized_verifier_identity=VALID_HASH_C,
        overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        environment_creation_receipt_path="/tmp/env.json",
        environment_creation_receipt_sha256=VALID_HASH_A,
        environment_creation_identity_value=VALID_HASH_B,
        per_dataset_receipts=[_per_dataset_entry(d) for d in _ELEVEN_DATASETS],
        lock_selected_inventory=[["pandas", "2.2.2"]],
        lock_selected_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes([["pandas", "2.2.2"]], sort_keys=False)
        ),
        installed_inventory=[["pandas", "2.2.2"]],
        installed_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes([["pandas", "2.2.2"]], sort_keys=False)
        ),
        bootstrap_tool_inventory=[["pip", "24.0"]],
        expected_dataset_order=_ELEVEN_DATASETS,
    )
    kwargs.update(overrides)
    return kwargs


def test_build_aggregate_build_receipt_happy_path_round_trips():
    receipt = b.build_aggregate_build_receipt(**_aggregate_kwargs())
    assert receipt["schema"] == b.AGGREGATE_BUILD_RECEIPT_SCHEMA_TAG
    assert len(receipt["per_dataset_receipts"]) == 11
    b.validate_aggregate_build_receipt(receipt, expected_dataset_order=_ELEVEN_DATASETS)


def test_build_aggregate_build_receipt_partial_failure_subset_ok():
    kwargs = _aggregate_kwargs(
        overall_status="BUILD_FAILED_PARTIAL",
        per_dataset_receipts=[_per_dataset_entry(d) for d in _ELEVEN_DATASETS[:3]],
    )
    receipt = b.build_aggregate_build_receipt(**kwargs)
    b.validate_aggregate_build_receipt(receipt, expected_dataset_order=_ELEVEN_DATASETS)


def test_build_aggregate_build_receipt_rejects_partial_status_with_full_dataset_set():
    kwargs = _aggregate_kwargs(overall_status="BUILD_FAILED_PARTIAL")
    with pytest.raises(ValueError, match="BUILD_FAILED_PARTIAL"):
        b.build_aggregate_build_receipt(**kwargs)


def test_build_aggregate_build_receipt_rejects_complete_status_missing_dataset():
    kwargs = _aggregate_kwargs(
        per_dataset_receipts=[_per_dataset_entry(d) for d in _ELEVEN_DATASETS[:10]]
    )
    with pytest.raises(ValueError, match="缺"):
        b.build_aggregate_build_receipt(**kwargs)


def test_build_aggregate_build_receipt_rejects_dataset_outside_frozen_order():
    kwargs = _aggregate_kwargs(
        per_dataset_receipts=[_per_dataset_entry(d) for d in _ELEVEN_DATASETS[:10]]
        + [_per_dataset_entry("not_a_real_dataset")],
    )
    with pytest.raises(ValueError):
        b.build_aggregate_build_receipt(**kwargs)


def test_build_aggregate_build_receipt_rejects_lock_selected_inventory_sha_mismatch():
    kwargs = _aggregate_kwargs(lock_selected_inventory_sha256=VALID_HASH_C)
    with pytest.raises(ValueError, match="lock_selected_inventory_sha256"):
        b.build_aggregate_build_receipt(**kwargs)


def test_validate_aggregate_build_receipt_rejects_missing_field():
    receipt = b.build_aggregate_build_receipt(**_aggregate_kwargs())
    del receipt["installed_inventory"]
    with pytest.raises(ValueError, match="欄位集合不符"):
        b.validate_aggregate_build_receipt(receipt, expected_dataset_order=_ELEVEN_DATASETS)


def test_write_aggregate_build_receipt_exclusive_create(tmp_path):
    receipt = b.build_aggregate_build_receipt(**_aggregate_kwargs())
    path = tmp_path / "aggregate.json"
    abs_path, digest = b.write_aggregate_build_receipt(
        path, receipt, expected_dataset_order=_ELEVEN_DATASETS
    )
    assert abs_path.exists()
    with pytest.raises(ValueError, match="排他建立"):
        b.write_aggregate_build_receipt(
            path, receipt, expected_dataset_order=_ELEVEN_DATASETS
        )


# ----------------------------------------------------------------------------
# 6. 11-dataset stop-on-first-failure 協調 (§D)
# ----------------------------------------------------------------------------


def _make_evidence_bundle(dataset: str, *, blank=1, unparseable=1) -> dict:
    cell_records = []
    if blank:
        cell_records.append(
            _cell_record(dataset=dataset, source_row_number=1, is_blank=True, is_unparseable=False)
        )
    if unparseable:
        cell_records.append(
            _unparseable_cell_record(dataset=dataset, source_row_number=2)
        )
    return {
        "cell_records": cell_records,
        "per_file_stage_one_counts": _per_file_stage_one_counts(blank=blank, unparseable=unparseable),
        "coverage_matrix": [],
        "duplicate_mapping": [],
        "final_null_causes": {
            "close": {
                "RETAINED_BLANK": blank,
                "RETAINED_UNPARSEABLE": unparseable,
                "SOURCE_COLUMN_ABSENT": 0,
                "SUPPLEMENT_KEY_NOT_COVERED": 0,
                "OTHER_UNEXPLAINED": 0,
            }
        },
        "supplement_merge_profile": None,
        "schema": _schema_metadata(),
    }


def _make_combined_df_summary(*, blank=1, unparseable=1) -> dict:
    return {
        "source_files": [["a.xlsx", VALID_HASH_A]],
        "row_count": 10,
        "stock_count": 1,
        "date_min": "2020-01-01",
        "date_max": "2020-01-10",
        "final_null_counts": {"close": blank + unparseable},
    }


def _counter():
    state = {"n": 0}

    def _now():
        state["n"] += 1
        return f"2026-08-16T00:00:{state['n']:02d}Z"

    return _now


def _filename_fn(kind: str):
    def _fn(dataset: str) -> str:
        return f"{dataset}.{kind}.json"

    return _fn


def _staging_fixture():
    """Codex review 修正(REQUEST CHANGES 第 3 項):建立一組簡單的
    in-memory `stage`/`publish`/`discard` 三支 callable，模擬真正的
    『staging 位置 → atomic publish 進 cache/<dataset>/』機制。`state` 記錄
    三者各自的呼叫順序，供測試斷言『publish 只在後段驗證通過之後才發生』、
    『discard 只清掉失敗那個 dataset 的 staging，不影響已 publish 的
    1..N-1』。"""
    state = {"staged": [], "published": [], "discarded": []}

    def stage_fn(dataset, summary):
        state["staged"].append(dataset)
        return {"dataset": dataset, "summary": summary}

    def publish_fn(dataset, token):
        assert token["dataset"] == dataset
        state["published"].append(dataset)

    def discard_fn(dataset, token):
        assert token["dataset"] == dataset
        state["discarded"].append(dataset)

    return state, stage_fn, publish_fn, discard_fn


def test_orchestrator_all_success_writes_receipts_sidecars_and_publishes_in_order(tmp_path):
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    order = ("price_valuation", "institutional_flow", "industry_map")
    state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    def load_dataset_fn(dataset):
        return _make_combined_df_summary(), _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=order,
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )

    assert result["overall_status"] == "BUILD_COMPLETE_AWAITING_VERIFICATION"
    assert result["failed_dataset"] is None
    assert result["succeeded_datasets"] == list(order)
    assert state["staged"] == list(order)
    assert state["published"] == list(order)
    assert state["discarded"] == []
    assert len(result["per_dataset_receipts"]) == 3
    for dataset in order:
        assert (receipt_dir / f"{dataset}.receipt.json").exists()
        assert (sidecar_dir / f"{dataset}.sidecar.json").exists()


def test_orchestrator_stops_on_first_failure_and_preserves_prior_evidence(tmp_path):
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    order = ("price_valuation", "institutional_flow", "industry_map")
    state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    def load_dataset_fn(dataset):
        if dataset == "institutional_flow":
            raise ValueError("欄位缺席,fail-closed")
        return _make_combined_df_summary(), _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=order,
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )

    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "institutional_flow"
    assert result["succeeded_datasets"] == ["price_valuation"]
    assert len(result["per_dataset_receipts"]) == 2  # 1 success + 1 failure, 3rd never attempted

    # institutional_flow 在 load_dataset_fn 就失敗(還沒進到 stage 這一步)，
    # 所以 stage/discard 都完全沒被呼叫；price_valuation 正常 stage+publish。
    assert state["staged"] == ["price_valuation"]
    assert state["published"] == ["price_valuation"]
    assert state["discarded"] == []

    # 第一個 dataset 的證據保留在磁碟上，當作診斷證據
    assert (receipt_dir / "price_valuation.receipt.json").exists()
    assert (sidecar_dir / "price_valuation.sidecar.json").exists()
    # 失敗的 dataset 有 receipt(記錄失敗),但沒有 sidecar(解析沒完成)
    assert (receipt_dir / "institutional_flow.receipt.json").exists()
    assert not (sidecar_dir / "institutional_flow.sidecar.json").exists()
    # 第三個 dataset 完全沒被嘗試
    assert not (receipt_dir / "industry_map.receipt.json").exists()
    assert not (sidecar_dir / "industry_map.sidecar.json").exists()

    import json

    failed_receipt = json.loads(
        (receipt_dir / "institutional_flow.receipt.json").read_text(encoding="utf-8")
    )
    assert failed_receipt["status"] == b.DATASET_BUILD_FAILED
    assert failed_receipt["error"]["error_type"] == "ValueError"
    assert "fail-closed" in failed_receipt["error"]["error_message"]

    success_receipt = json.loads(
        (receipt_dir / "price_valuation.receipt.json").read_text(encoding="utf-8")
    )
    assert success_receipt["status"] == b.DATASET_BUILD_SUCCEEDED


def test_orchestrator_stage_failure_triggers_stop_without_discard(tmp_path):
    """`stage_dataset_fn` 自己失敗——這個 dataset 從沒真的被 stage 過，
    `discard_staged_dataset_fn` 不該被呼叫(沒有 staging_token 可以清)。"""
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    discarded = []

    def load_dataset_fn(dataset):
        return _make_combined_df_summary(), _make_evidence_bundle(dataset)

    def stage_fn(dataset, summary):
        raise OSError("staging area disk full")

    result = b.run_build_stop_on_first_failure(
        dataset_order=("price_valuation", "institutional_flow"),
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=lambda d, t: pytest.fail("不該被呼叫"),
        discard_staged_dataset_fn=lambda d, t: discarded.append(d),
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )
    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "price_valuation"
    assert discarded == []  # stage 本身就失敗，沒有 token 可以 discard
    assert not (sidecar_dir / "price_valuation.sidecar.json").exists()


def test_orchestrator_accounting_failure_after_staging_discards_staging_and_sidecar(tmp_path):
    """Codex review 反例(REQUEST CHANGES 第 3 項要求的三種 post-persist
    failure 之一):`stage_dataset_fn` 成功、sidecar 也成功寫出，但
    `build_per_dataset_receipt_success` 的 accounting 交叉核對失敗
    (`final_null_counts` 跟 `evidence_bundle['final_null_causes']` 對不
    上)——這個 dataset 的 staging 輸出跟已經寫出的 sidecar 都必須被清掉，
    不能已經『發布』。"""
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    order = ("price_valuation", "institutional_flow")
    state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    def load_dataset_fn(dataset):
        summary = _make_combined_df_summary()
        if dataset == "institutional_flow":
            summary["final_null_counts"] = {"close": 999}  # 故意跟 evidence_bundle 對不上
        return summary, _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=order,
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )

    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "institutional_flow"
    # 第一個 dataset 正常 publish；第二個 stage 了但從未 publish，且被 discard。
    assert state["staged"] == ["price_valuation", "institutional_flow"]
    assert state["published"] == ["price_valuation"]
    assert state["discarded"] == ["institutional_flow"]
    # 第二個 dataset 的 sidecar 一度成功寫出，但 accounting 失敗後必須被刪除
    # ——不留下一份『品質證據看似自洽，但正式狀態是 FAILED』的孤兒 sidecar。
    assert (sidecar_dir / "price_valuation.sidecar.json").exists()
    assert not (sidecar_dir / "institutional_flow.sidecar.json").exists()

    import json

    failed_receipt = json.loads(
        (receipt_dir / "institutional_flow.receipt.json").read_text(encoding="utf-8")
    )
    assert failed_receipt["status"] == b.DATASET_BUILD_FAILED
    assert "final_null_causes" in failed_receipt["error"]["error_message"]


def test_orchestrator_sidecar_write_failure_discards_staging(tmp_path, monkeypatch):
    """三種 post-persist failure 之二:sidecar **寫入**本身失敗(不是內容
    驗證失敗)——staging 輸出必須被清掉。"""
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    def raising_write_quality_sidecar(path, sidecar):
        raise OSError("simulated disk full writing sidecar")

    monkeypatch.setattr(b, "write_quality_sidecar", raising_write_quality_sidecar)

    def load_dataset_fn(dataset):
        return _make_combined_df_summary(), _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=("price_valuation",),
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )
    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "price_valuation"
    assert state["staged"] == ["price_valuation"]
    assert state["published"] == []
    assert state["discarded"] == ["price_valuation"]

    import json

    failed_receipt = json.loads(
        (receipt_dir / "price_valuation.receipt.json").read_text(encoding="utf-8")
    )
    assert "simulated disk full" in failed_receipt["error"]["error_message"]


def test_orchestrator_receipt_write_failure_discards_staging_and_sidecar(tmp_path, monkeypatch):
    """三種 post-persist failure 之三:成功 receipt 的**寫入**本身失敗
    (accounting 已經通過、sidecar 也已經成功寫出，只有最後落地這一步失敗)
    ——staging 輸出跟已寫出的 sidecar 都必須被清掉，且第二次(寫失敗
    receipt)的呼叫必須真的成功寫出失敗證據。"""
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    call_count = {"n": 0}
    real_write = b.write_per_dataset_receipt

    def flaky_write_per_dataset_receipt(path, receipt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("simulated disk full writing per-dataset receipt")
        return real_write(path, receipt)

    monkeypatch.setattr(b, "write_per_dataset_receipt", flaky_write_per_dataset_receipt)

    def load_dataset_fn(dataset):
        return _make_combined_df_summary(), _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=("price_valuation",),
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )
    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "price_valuation"
    assert state["staged"] == ["price_valuation"]
    assert state["published"] == []  # 從沒到達 publish 這一步
    assert state["discarded"] == ["price_valuation"]
    # 第一次寫入(SUCCEEDED)失敗，sidecar 因此也要被清掉；
    # 第二次寫入(FAILED,同一個檔名)必須成功落地。
    assert not (sidecar_dir / "price_valuation.sidecar.json").exists()
    assert call_count["n"] == 2

    import json

    failed_receipt = json.loads(
        (receipt_dir / "price_valuation.receipt.json").read_text(encoding="utf-8")
    )
    assert failed_receipt["status"] == b.DATASET_BUILD_FAILED
    assert "simulated disk full writing per-dataset receipt" in failed_receipt["error"]["error_message"]


def test_orchestrator_publish_failure_discards_staging_and_sidecar_and_receipt(tmp_path):
    """publish 本身(atomic rename 等價機制)失敗——即使 accounting/sidecar/
    receipt 全部驗證通過，只要最後 publish 失敗，這個 dataset 依然必須被
    視為整體失敗:staging 清掉、已寫出的 sidecar 跟『看似成功』的 receipt
    都要被清掉，只留一份 FAILED receipt。"""
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    state, stage_fn, _publish_fn, discard_fn = _staging_fixture()

    def failing_publish_fn(dataset, token):
        state["published"].append(dataset)
        raise OSError("simulated atomic publish failure")

    def load_dataset_fn(dataset):
        return _make_combined_df_summary(), _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=("price_valuation",),
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=failing_publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )
    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "price_valuation"
    assert state["discarded"] == ["price_valuation"]
    assert not (sidecar_dir / "price_valuation.sidecar.json").exists()

    import json

    failed_receipt = json.loads(
        (receipt_dir / "price_valuation.receipt.json").read_text(encoding="utf-8")
    )
    assert failed_receipt["status"] == b.DATASET_BUILD_FAILED
    assert "simulated atomic publish failure" in failed_receipt["error"]["error_message"]


def test_orchestrator_propagates_supplement_provenance_when_present(tmp_path):
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    _state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    supplement_provenance = b.build_supplement_provenance(
        supplement_receipt_path="tej_exports/legacy_supplement/receipt.json",
        supplement_receipt_sha256=VALID_HASH_A,
        supplement_identity_value=VALID_HASH_A,
        affected_columns=["roe_after_tax"],
        merge_profile=_merge_profile(),
        rows_with_supplement_value=80,
    )

    def load_dataset_fn(dataset):
        bundle = _make_evidence_bundle(dataset)
        bundle["supplement_provenance"] = supplement_provenance
        return _make_combined_df_summary(), bundle

    result = b.run_build_stop_on_first_failure(
        dataset_order=("fundamentals_quarterly",),
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )
    assert result["overall_status"] == "BUILD_COMPLETE_AWAITING_VERIFICATION"

    import json

    receipt = json.loads(
        (receipt_dir / "fundamentals_quarterly.receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["supplement_provenance"] == supplement_provenance


def test_orchestrator_rejects_empty_dataset_order():
    _state, stage_fn, publish_fn, discard_fn = _staging_fixture()
    with pytest.raises(ValueError, match="non-empty"):
        b.run_build_stop_on_first_failure(
            dataset_order=(),
            load_dataset_fn=lambda d: (_make_combined_df_summary(), _make_evidence_bundle(d)),
            stage_dataset_fn=stage_fn,
            publish_staged_dataset_fn=publish_fn,
            discard_staged_dataset_fn=discard_fn,
            snapshot_id_v1_value=VALID_SNAPSHOT_ID,
            run_id="run-1",
            per_dataset_receipt_dir=".",
            quality_sidecar_dir=".",
            make_receipt_filename_fn=_filename_fn("receipt"),
            make_sidecar_filename_fn=_filename_fn("sidecar"),
            now_fn=_counter(),
        )


def test_orchestrator_rejects_duplicate_dataset_order():
    _state, stage_fn, publish_fn, discard_fn = _staging_fixture()
    with pytest.raises(ValueError, match="重複"):
        b.run_build_stop_on_first_failure(
            dataset_order=("price_valuation", "price_valuation"),
            load_dataset_fn=lambda d: (_make_combined_df_summary(), _make_evidence_bundle(d)),
            stage_dataset_fn=stage_fn,
            publish_staged_dataset_fn=publish_fn,
            discard_staged_dataset_fn=discard_fn,
            snapshot_id_v1_value=VALID_SNAPSHOT_ID,
            run_id="run-1",
            per_dataset_receipt_dir=".",
            quality_sidecar_dir=".",
            make_receipt_filename_fn=_filename_fn("receipt"),
            make_sidecar_filename_fn=_filename_fn("sidecar"),
            now_fn=_counter(),
        )


def test_orchestrator_malformed_combined_df_summary_fails_closed(tmp_path):
    receipt_dir = tmp_path / "build_receipts"
    sidecar_dir = tmp_path / "quality_sidecars"
    receipt_dir.mkdir()
    sidecar_dir.mkdir()

    state, stage_fn, publish_fn, discard_fn = _staging_fixture()

    def load_dataset_fn(dataset):
        summary = _make_combined_df_summary()
        del summary["row_count"]  # malformed
        return summary, _make_evidence_bundle(dataset)

    result = b.run_build_stop_on_first_failure(
        dataset_order=("price_valuation",),
        load_dataset_fn=load_dataset_fn,
        stage_dataset_fn=stage_fn,
        publish_staged_dataset_fn=publish_fn,
        discard_staged_dataset_fn=discard_fn,
        snapshot_id_v1_value=VALID_SNAPSHOT_ID,
        run_id="run-1",
        per_dataset_receipt_dir=receipt_dir,
        quality_sidecar_dir=sidecar_dir,
        make_receipt_filename_fn=_filename_fn("receipt"),
        make_sidecar_filename_fn=_filename_fn("sidecar"),
        now_fn=_counter(),
    )
    assert result["overall_status"] == "BUILD_FAILED_PARTIAL"
    assert result["failed_dataset"] == "price_valuation"
    # summary 在 _require_combined_df_summary 就被擋下——連 stage 都沒發生。
    assert state["staged"] == []
    assert state["discarded"] == []


# ----------------------------------------------------------------------------
# 7. import 白名單靜態檢查 (§C.6)
# ----------------------------------------------------------------------------


def test_check_import_whitelist_allows_clean_module(tmp_path):
    f = tmp_path / "clean.py"
    f.write_text("import os\nimport pandas as pd\nfrom pathlib import Path\n", encoding="utf-8")
    b.check_import_whitelist(f)  # 不 raise


def test_check_import_whitelist_rejects_core_import(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("import core.data_provider\n", encoding="utf-8")
    with pytest.raises(ValueError, match="core"):
        b.check_import_whitelist(f)


def test_check_import_whitelist_rejects_beat_0050_from_import(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("from beat_0050.strategies import high52_lab\n", encoding="utf-8")
    with pytest.raises(ValueError, match="beat_0050"):
        b.check_import_whitelist(f)


def test_check_import_whitelist_rejects_bare_beat_0050_import(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("import beat_0050\n", encoding="utf-8")
    with pytest.raises(ValueError):
        b.check_import_whitelist(f)


def test_check_import_whitelist_does_not_false_positive_on_similarly_named_package(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("import core_utils_unrelated\nimport beat_0050_other\n", encoding="utf-8")
    b.check_import_whitelist(f)  # 不 raise -- 只精確比對 top-level 名稱


def test_check_import_whitelist_does_not_exec_the_target_file(tmp_path):
    f = tmp_path / "would_blow_up.py"
    f.write_text("raise RuntimeError('should never execute')\n", encoding="utf-8")
    b.check_import_whitelist(f)  # 純 AST parse,不執行


def test_check_import_whitelist_against_real_tej_importer():
    """§C.6 的真正回歸檢查:對現行工作樹的 tej_importer.py 本身跑一次。"""
    b.check_import_whitelist(REPO_ROOT / "tej_importer.py")


def test_check_import_whitelist_against_real_build_v2_candidate():
    """§C.6:「這條檢查應該同時涵蓋 tej_importer.py 跟新 builder 腳本兩份
    檔案」——對這個 builder 腳本自己也跑一次。"""
    b.check_import_whitelist(REPO_ROOT / "scripts" / "build_v2_candidate.py")


# ----------------------------------------------------------------------------
# 8. dataset 凍結順序漂移偵測(§B——orchestrator 的 dataset_order 是注入值,
#    這裡確保注入值真的等於 tej_importer.DATASETS 的目前順序,不會悄悄
#    分岔)。
# ----------------------------------------------------------------------------


def test_frozen_eleven_dataset_order_matches_tej_importer_datasets():
    sys.path.insert(0, str(REPO_ROOT))
    import tej_importer

    assert tuple(tej_importer.DATASETS.keys()) == _ELEVEN_DATASETS
