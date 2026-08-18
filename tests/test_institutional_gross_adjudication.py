# -*- coding: utf-8 -*-
"""synthetic 測試:scripts/institutional_gross_trust_holding_pct_adjudication.py
(Round 8B review 初版,Round 9 review 擴充)。

只用本檔的 synthetic fixture (寫在 `tmp_path` 底下)——**不讀取**任何真實的
`~/tej_cache`、scratchpad 下的 round3 快取、或 `tej_exports/inbox_chip_gross`/
`tej_exports/DataExport0806` 原始檔。規則見
docs/資料快照遷移_DataExport0806.md §10。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

adj = pytest.importorskip("institutional_gross_trust_holding_pct_adjudication")


# =============================================================================
# 1. build_manifest —— 唯讀 manifest (anchor 沒有,這裡誠實建一份)
# =============================================================================

def test_build_manifest_lists_relpath_size_sha256(tmp_path):
    (tmp_path / "1101.parquet").write_bytes(b"hello")
    (tmp_path / "1102.parquet").write_bytes(b"world!")
    manifest = adj.build_manifest(tmp_path)
    names = {m["relpath"] for m in manifest}
    assert names == {"1101.parquet", "1102.parquet"}
    for m in manifest:
        assert m["sha256"]
        assert m["size_bytes"] > 0


def test_build_manifest_empty_when_root_missing(tmp_path):
    assert adj.build_manifest(tmp_path / "does_not_exist") == []


# =============================================================================
# 2. compute_structural_stats / compute_six_column_stats —— 精確重現 anchor 用
# =============================================================================

def _make_df(rows):
    return pd.DataFrame(rows)


def test_compute_structural_stats_basic():
    old = _make_df([
        {"stock_id": "1101", "date": "2026-04-01"},
        {"stock_id": "1102", "date": "2026-04-01"},
    ])
    new = _make_df([
        {"stock_id": "1101", "date": "2026-04-01"},
        {"stock_id": "1103", "date": "2026-04-01"},
    ])
    stats = adj.compute_structural_stats(old, new)
    assert stats["old_key_count"] == 2
    assert stats["new_key_count"] == 2
    assert stats["missing_keys_count"] == 1     # 1102 老有新無
    assert stats["extra_keys_count"] == 1       # 1103 新有老無
    assert stats["overlap_key_count"] == 1
    assert stats["old_stock_count"] == 2
    assert stats["new_stock_count"] == 2
    assert stats["missing_stock_ids_count"] == 1


def test_compute_six_column_stats_matches_hand_computed():
    key = {"stock_id": "1101", "date": "2026-04-01"}
    old = pd.DataFrame([{**key, "foreign_buy": 1000.0, "foreign_sell": 1.0, "trust_buy": 1.0,
                          "trust_sell": 1.0, "foreign_holding_pct": 1.0, "trust_holding_pct": 10.0}])
    new = pd.DataFrame([{**key, "foreign_buy": 1000.0, "foreign_sell": 1.0, "trust_buy": 1.0,
                          "trust_sell": 1.0, "foreign_holding_pct": np.nan, "trust_holding_pct": 10.5}])
    stats, merged = adj.compute_six_column_stats(old, new)
    assert stats["foreign_buy"]["n_exact_equal"] == 1
    assert stats["foreign_buy"]["n_value_mismatch"] == 0
    assert stats["foreign_holding_pct"]["n_null_mismatch"] == 1
    assert stats["trust_holding_pct"]["n_value_mismatch"] == 1
    assert stats["trust_holding_pct"]["max_abs_diff"] == pytest.approx(0.5)
    assert stats["trust_holding_pct"]["median_abs_diff"] == pytest.approx(0.5)
    assert len(merged) == 1


def test_compare_structural_to_anchor_detects_mismatch():
    reproduced = {"old_key_count": 5, "new_key_count": 5, "missing_keys_count": 0,
                  "extra_keys_count": 0, "overlap_key_count": 5, "old_stock_count": 1,
                  "new_stock_count": 1, "missing_stock_ids_count": 0,
                  "missing_columns_old": [], "missing_columns_new": []}
    anchor = dict(reproduced)
    anchor["old_key_count"] = 999   # 竄改
    mismatches = adj.compare_structural_to_anchor(reproduced, anchor)
    assert any(m["field"] == "old_key_count" for m in mismatches)


def test_compare_structural_to_anchor_no_mismatch_when_identical():
    reproduced = {"old_key_count": 5, "new_key_count": 5, "missing_keys_count": 0,
                  "extra_keys_count": 0, "overlap_key_count": 5, "old_stock_count": 1,
                  "new_stock_count": 1, "missing_stock_ids_count": 0,
                  "missing_columns_old": [], "missing_columns_new": []}
    assert adj.compare_structural_to_anchor(reproduced, dict(reproduced)) == []


def test_compare_columns_to_anchor_detects_mismatch():
    reproduced_cols = {"trust_holding_pct": {"n_compared": 10, "n_null_mismatch": 0,
                                              "n_exact_equal": 8, "n_value_mismatch": 2,
                                              "max_abs_diff": 1.0, "median_abs_diff": 0.5}}
    anchor_cols = {"trust_holding_pct": {**reproduced_cols["trust_holding_pct"], "n_value_mismatch": 999}}
    mismatches = adj.compare_columns_to_anchor(reproduced_cols, anchor_cols)
    assert any(m["column"] == "trust_holding_pct" and m["field"] == "n_value_mismatch" for m in mismatches)


# =============================================================================
# 3. enumerate_mismatch_instances
# =============================================================================

def test_enumerate_mismatch_instances_captures_exactly_the_mismatches():
    old = pd.DataFrame([{"stock_id": "1101", "date": "2026-04-01", "foreign_buy": 1.0,
                          "foreign_sell": 1.0, "trust_buy": 1.0, "trust_sell": 1.0,
                          "foreign_holding_pct": 1.0, "trust_holding_pct": 10.0}])
    new = pd.DataFrame([{"stock_id": "1101", "date": "2026-04-01", "foreign_buy": 1.0,
                          "foreign_sell": 1.0, "trust_buy": 1.0, "trust_sell": 1.0,
                          "foreign_holding_pct": 1.0, "trust_holding_pct": 20.0}])
    _, merged = adj.compute_six_column_stats(old, new)
    instances = adj.enumerate_mismatch_instances(merged)
    assert len(instances) == 1
    assert instances.iloc[0]["column"] == "trust_holding_pct"
    assert instances.iloc[0]["mismatch_kind"] == "value_mismatch"


def test_enumerate_mismatch_instances_empty_when_no_mismatch():
    key = {"stock_id": "1101", "date": "2026-04-01", "foreign_buy": 1.0, "foreign_sell": 1.0,
           "trust_buy": 1.0, "trust_sell": 1.0, "foreign_holding_pct": 1.0, "trust_holding_pct": 10.0}
    old = pd.DataFrame([key])
    new = pd.DataFrame([dict(key)])
    _, merged = adj.compute_six_column_stats(old, new)
    instances = adj.enumerate_mismatch_instances(merged)
    assert instances.empty


# =============================================================================
# 4. parse_old_raw / parse_new_raw —— schema/key/date/unit 對應 + fail-closed
#    (Round 9 review: 驗證在 filter 之前的全量上做,不去重,回傳證據字典)
# =============================================================================

def _write_old_raw_xlsx(path: Path, rows):
    pd.DataFrame(rows, columns=["代號", "名稱", "年月日", "外資買進張數", "外資賣出張數",
                                 "投信買進張數", "投信賣出張數", "外資總投資股率%", "投信持股率%"]
                 ).to_excel(path, index=False)


def _write_new_raw_xlsx(path: Path, rows):
    pd.DataFrame(rows, columns=["證券代碼", "年月日", "外資買進張數", "外資賣出張數",
                                 "投信買進張數", "投信賣出張數", "外資總投資股率%", "投信持股率%"]
                 ).to_excel(path, index=False)


def test_parse_old_raw_converts_lots_to_shares_and_parses_slash_date(tmp_path):
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [[1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2]])
    evidence = adj.parse_old_raw(p)
    key = ("1101", "2026-04-01")
    assert evidence["foreign_buy"][key]["parsed_value"] == 10_000        # 10 張 → 10,000 股
    assert evidence["foreign_buy"][key]["unit_scale"] == "x1000"
    assert evidence["trust_holding_pct"][key]["parsed_value"] == pytest.approx(0.2)   # 百分比原樣
    assert evidence["trust_holding_pct"][key]["unit_scale"] == "none"


def test_parse_new_raw_splits_combined_id_and_parses_numeric_date(tmp_path):
    p = tmp_path / "new.xlsx"
    _write_new_raw_xlsx(p, [["1101 台泥", 20260401, 10, 5, 2, 1, 13.0, 0.2]])
    evidence = adj.parse_new_raw(p)
    key = ("1101", "2026-04-01")
    assert evidence["trust_buy"][key]["parsed_value"] == 2_000
    assert key in evidence["trust_holding_pct"]


def test_parse_raw_filters_to_needed_keys(tmp_path):
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],
        [1102, "亞泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],
    ])
    evidence = adj.parse_old_raw(p, needed_keys={("1101", "2026-04-01")})
    assert set(evidence["trust_holding_pct"].keys()) == {("1101", "2026-04-01")}


# ---- Round 9: 驗證在 filter 之前的全量上做,無效 id/date 一律 raise ----

def test_parse_old_raw_invalid_stock_id_raises_even_outside_needed_keys(tmp_path):
    """一列 stock_id 無效,但它根本不在 needed_keys 範圍內——驗證必須在 filter
    之前對整份原始檔做,不能因為這列「反正用不到」就放過去。"""
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],
        ["nan", "X", "2026/04/02", 10, 5, 2, 1, 13.0, 0.2],   # 無效 stock_id,且不在 needed_keys
    ])
    with pytest.raises(adj.RawSchemaError) as exc_info:
        adj.parse_old_raw(p, needed_keys={("1101", "2026-04-01")})
    assert exc_info.value.kind == "invalid_keys"
    assert exc_info.value.count == 1


def test_parse_old_raw_invalid_date_raises(tmp_path):
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [[1101, "台泥", "not-a-date", 10, 5, 2, 1, 13.0, 0.2]])
    with pytest.raises(adj.RawSchemaError) as exc_info:
        adj.parse_old_raw(p)
    assert exc_info.value.kind == "invalid_keys"


def test_parse_old_raw_identical_duplicate_raises_no_dedup(tmp_path):
    """Round 9 review:完全相同的重複列也要 raise,不能像 Round 8 那樣安全去重。"""
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],   # 完全重複
    ])
    with pytest.raises(adj.RawSchemaError) as exc_info:
        adj.parse_old_raw(p)
    assert exc_info.value.kind == "duplicate_keys"
    assert exc_info.value.count == 1
    assert exc_info.value.samples


def test_parse_old_raw_conflicting_duplicate_raises(tmp_path):
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],
        [1101, "台泥", "2026/04/01", 99, 5, 2, 1, 13.0, 0.2],   # 同 key,foreign_buy 不同
    ])
    with pytest.raises(adj.RawSchemaError) as exc_info:
        adj.parse_old_raw(p)
    assert exc_info.value.kind == "duplicate_keys"


def test_parse_old_raw_duplicate_detected_before_needed_keys_filter(tmp_path):
    """重複鍵不在 needed_keys 範圍內,依然要被抓到——驗證發生在 filter 之前。"""
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, 0.2],
        [1199, "X", "2026/05/01", 10, 5, 2, 1, 13.0, 0.2],
        [1199, "X", "2026/05/01", 20, 5, 2, 1, 13.0, 0.2],   # 1199 重複,不在 needed_keys
    ])
    with pytest.raises(adj.RawSchemaError, match="重複"):
        adj.parse_old_raw(p, needed_keys={("1101", "2026-04-01")})


# ---- Round 9: raw_token 保留原始文字,合法空白跟不可解析文字分開標記 ----

def test_parse_old_raw_preserves_literal_dot_as_raw_token(tmp_path):
    """文字 "." 轉成數字會失敗,但 raw_token 必須完整保留這個字面文字,不能只剩
    parsed_value=NaN,審查者才看得出「原始檔裡到底寫了什麼」。"""
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [[4130, "健亞", "2026/07/02", 10, 5, 2, 1, 13.0, "."]])
    evidence = adj.parse_old_raw(p)
    ev = evidence["trust_holding_pct"][("4130", "2026-07-02")]
    assert ev["raw_token"] == "."
    assert ev["parsed_value"] is None
    assert ev["is_blank"] is False
    assert ev["is_unparseable"] is True


def test_parse_old_raw_distinguishes_blank_from_unparseable(tmp_path):
    p = tmp_path / "old.xlsx"
    _write_old_raw_xlsx(p, [
        [1101, "台泥", "2026/04/01", 10, 5, 2, 1, 13.0, None],          # 合法空白
        [1102, "亞泥", "2026/04/02", 10, 5, 2, 1, 13.0, "garbled"],     # 非空白但轉不成數字
    ])
    evidence = adj.parse_old_raw(p)
    blank_ev = evidence["trust_holding_pct"][("1101", "2026-04-01")]
    unparse_ev = evidence["trust_holding_pct"][("1102", "2026-04-02")]
    assert blank_ev["is_blank"] is True
    assert blank_ev["is_unparseable"] is False
    assert blank_ev["raw_token"] is None
    assert unparse_ev["is_blank"] is False
    assert unparse_ev["is_unparseable"] is True
    assert unparse_ev["raw_token"] == "garbled"


# =============================================================================
# 5. classify_instance —— §10.4 決策樹的每一支
# =============================================================================

def test_classify_both_raw_match_old():
    assert adj.classify_instance(old_r=10.0, new_r=10.0, old_p=10.0, new_p=20.0) == "BOTH_RAW_MATCH_OLD"


def test_classify_both_raw_match_new():
    assert adj.classify_instance(old_r=20.0, new_r=20.0, old_p=10.0, new_p=20.0) == "BOTH_RAW_MATCH_NEW"


def test_classify_neither_match_when_raw_agree_but_matches_no_parquet():
    assert adj.classify_instance(old_r=99.0, new_r=99.0, old_p=10.0, new_p=20.0) == "NEITHER_MATCH"


def test_classify_raw_sources_differ_each_matches_own_parquet():
    assert adj.classify_instance(old_r=10.0, new_r=20.0, old_p=10.0, new_p=20.0) == "RAW_SOURCES_DIFFER"


def test_classify_old_raw_only_match():
    assert adj.classify_instance(old_r=10.0, new_r=99.0, old_p=10.0, new_p=20.0) == "OLD_RAW_ONLY_MATCH"


def test_classify_new_raw_only_match():
    assert adj.classify_instance(old_r=99.0, new_r=20.0, old_p=10.0, new_p=20.0) == "NEW_RAW_ONLY_MATCH"


def test_classify_neither_match_when_raw_differ_and_neither_matches_own_parquet():
    assert adj.classify_instance(old_r=99.0, new_r=88.0, old_p=10.0, new_p=20.0) == "NEITHER_MATCH"


def test_classify_treats_both_nan_as_equal():
    assert adj.classify_instance(old_r=np.nan, new_r=np.nan, old_p=np.nan, new_p=5.0) == "BOTH_RAW_MATCH_OLD"


# =============================================================================
# 6. classify_all —— evidence-dict 整合、RAW_KEY_MISSING/UNRESOLVED、
#    signed_diff/abs_diff、RAW_SOURCES_DIFFER 的兩個驗證旗標 (Round 9)
# =============================================================================

def _mismatch_row(column="trust_holding_pct", old_p=10.0, new_p=20.0, kind="value_mismatch"):
    return pd.DataFrame([{"stock_id": "1101", "date": "2026-04-01", "column": column,
                           "old_p": old_p, "new_p": new_p, "mismatch_kind": kind}])


def _ev(parsed, raw_token=None, is_blank=False, is_unparseable=False, unit_scale="none"):
    return {"raw_token": raw_token if raw_token is not None else (None if parsed is None else str(parsed)),
            "parsed_value": parsed, "is_blank": is_blank, "is_unparseable": is_unparseable,
            "unit_scale": unit_scale}


def test_classify_all_raw_key_missing_when_key_absent_from_one_raw_source():
    mismatches = _mismatch_row()
    old_evidence = {"trust_holding_pct": {}}    # 1101 不在裡面
    new_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(20.0)}}
    result = adj.classify_all(mismatches, old_evidence, new_evidence)
    assert result.iloc[0]["classification"] == "RAW_KEY_MISSING"


def test_classify_all_unresolved_schema_or_unit_when_flagged():
    mismatches = _mismatch_row()
    old_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(None, raw_token=".", is_unparseable=True)}}
    new_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(20.0)}}
    result = adj.classify_all(mismatches, old_evidence, new_evidence)
    row = result.iloc[0]
    assert row["classification"] == "UNRESOLVED_SCHEMA_OR_UNIT"
    assert row["old_raw_token"] == "."


def test_classify_all_normal_case_records_raw_sources_differ_flags():
    mismatches = _mismatch_row()
    old_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(10.0)}}
    new_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(20.0)}}
    result = adj.classify_all(mismatches, old_evidence, new_evidence)
    row = result.iloc[0]
    assert row["classification"] == "RAW_SOURCES_DIFFER"
    assert bool(row["old_raw_matches_old_parquet"]) is True
    assert bool(row["new_raw_matches_new_parquet"]) is True


def test_classify_all_non_raw_sources_differ_has_null_flags():
    mismatches = _mismatch_row()
    old_evidence = {"trust_holding_pct": {}}
    new_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(20.0)}}
    result = adj.classify_all(mismatches, old_evidence, new_evidence)
    row = result.iloc[0]
    assert row["classification"] == "RAW_KEY_MISSING"
    assert row["old_raw_matches_old_parquet"] is None
    assert row["new_raw_matches_new_parquet"] is None


def test_classify_all_records_signed_and_abs_diff_for_value_mismatch():
    mismatches = _mismatch_row(old_p=10.0, new_p=13.5, kind="value_mismatch")
    old_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(10.0)}}
    new_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(13.5)}}
    result = adj.classify_all(mismatches, old_evidence, new_evidence)
    row = result.iloc[0]
    assert row["signed_diff_new_minus_old"] == pytest.approx(3.5)
    assert row["abs_diff"] == pytest.approx(3.5)


def test_classify_all_null_mismatch_has_no_diff():
    mismatches = _mismatch_row(old_p=10.0, new_p=np.nan, kind="null_mismatch")
    old_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(10.0)}}
    new_evidence = {"trust_holding_pct": {("1101", "2026-04-01"): _ev(None, is_blank=True)}}
    result = adj.classify_all(mismatches, old_evidence, new_evidence)
    row = result.iloc[0]
    assert row["signed_diff_new_minus_old"] is None
    assert row["abs_diff"] is None


# =============================================================================
# 7. build_diff_distribution —— 精確分布,不分箱,null/unparseable 分開計數
# =============================================================================

def test_build_diff_distribution_exact_no_binning():
    classified = pd.DataFrame([
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": 0.03,
         "mismatch_kind": "value_mismatch", "classification": "RAW_SOURCES_DIFFER"},
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": 0.03,
         "mismatch_kind": "value_mismatch", "classification": "RAW_SOURCES_DIFFER"},
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": -0.5,
         "mismatch_kind": "value_mismatch", "classification": "RAW_SOURCES_DIFFER"},
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": None,
         "mismatch_kind": "null_mismatch", "classification": "RAW_SOURCES_DIFFER"},
        {"column": "foreign_holding_pct", "signed_diff_new_minus_old": None,
         "mismatch_kind": "null_mismatch", "classification": "UNRESOLVED_SCHEMA_OR_UNIT"},
    ])
    dist = adj.build_diff_distribution(classified)
    thp = dist["trust_holding_pct"]
    assert thp[repr(0.03)] == 2
    assert thp[repr(-0.5)] == 1
    assert thp["null_mismatch"] == 1
    assert "UNRESOLVED_SCHEMA_OR_UNIT" not in thp
    fhp = dist["foreign_holding_pct"]
    # 這一列同時是 null_mismatch (parquet 層級) 又是 UNRESOLVED_SCHEMA_OR_UNIT
    # (raw 層級無法解析)——這正是真實資料裡 26 筆的實際狀況。不能兩個桶各計一次
    # (那樣加總會對不上 total),classification 優先,只落進 UNRESOLVED_SCHEMA_
    # OR_UNIT 這一個桶。
    assert fhp["UNRESOLVED_SCHEMA_OR_UNIT"] == 1
    assert fhp["null_mismatch"] == 0
    assert sum(fhp.values()) == 1


def test_build_diff_distribution_sums_to_total_per_column():
    """互斥性的核心不變量:每欄的桶加總要等於該欄的列數 (Round 9 review 要求的
    完整性斷言,對應真實執行時 by_column/by_stock/by_date/diff_distribution 都要
    加總對得起來)。"""
    classified = pd.DataFrame([
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": 0.03,
         "mismatch_kind": "value_mismatch", "classification": "RAW_SOURCES_DIFFER"},
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": None,
         "mismatch_kind": "null_mismatch", "classification": "RAW_KEY_MISSING"},
        {"column": "trust_holding_pct", "signed_diff_new_minus_old": None,
         "mismatch_kind": "value_mismatch", "classification": "RAW_KEY_MISSING"},
    ])
    dist = adj.build_diff_distribution(classified)
    assert sum(dist["trust_holding_pct"].values()) == 3


# =============================================================================
# 8. summarize_records / validate_mismatch_records (Round 10 review)
# =============================================================================

def _sample_records():
    return [
        {"stock_id": "1101", "date": "2026-04-01", "column": "trust_holding_pct",
         "mismatch_kind": "value_mismatch", "old_parquet": 10.0, "new_parquet": 10.03,
         "old_raw_token": "10.0", "new_raw_token": "10.03",
         "old_raw_parsed": 10.0, "new_raw_parsed": 10.03,
         "old_raw_is_blank": False, "new_raw_is_blank": False,
         "old_raw_is_unparseable": False, "new_raw_is_unparseable": False,
         "unit_scale": "none", "classification": "RAW_SOURCES_DIFFER",
         "signed_diff_new_minus_old": 0.03, "abs_diff": 0.03,
         "old_raw_matches_old_parquet": True, "new_raw_matches_new_parquet": True},
        {"stock_id": "4130", "date": "2026-07-02", "column": "foreign_holding_pct",
         "mismatch_kind": "null_mismatch", "old_parquet": 3.04, "new_parquet": None,
         "old_raw_token": "3.04", "new_raw_token": ".",
         "old_raw_parsed": 3.04, "new_raw_parsed": None,
         "old_raw_is_blank": False, "new_raw_is_blank": False,
         "old_raw_is_unparseable": False, "new_raw_is_unparseable": True,
         "unit_scale": "none", "classification": "UNRESOLVED_SCHEMA_OR_UNIT",
         "signed_diff_new_minus_old": None, "abs_diff": None,
         "old_raw_matches_old_parquet": None, "new_raw_matches_new_parquet": None},
    ]


def test_summarize_records_reconstructs_counts():
    records = _sample_records()
    summaries = adj.summarize_records(records)
    assert summaries["classification_counts_overall"] == {
        "RAW_SOURCES_DIFFER": 1, "UNRESOLVED_SCHEMA_OR_UNIT": 1}
    assert summaries["classification_counts_by_stock"] == {"1101": 1, "4130": 1}
    assert summaries["classification_counts_by_date"] == {"2026-04-01": 1, "2026-07-02": 1}
    assert sum(summaries["diff_distribution_by_column"]["trust_holding_pct"].values()) == 1
    assert sum(summaries["diff_distribution_by_column"]["foreign_holding_pct"].values()) == 1


def test_validate_mismatch_records_passes_when_valid():
    adj.validate_mismatch_records(_sample_records(), expected_total=2)   # 不 raise 就算過


def test_validate_mismatch_records_raises_on_count_mismatch():
    with pytest.raises(AssertionError, match="筆數"):
        adj.validate_mismatch_records(_sample_records(), expected_total=999)


def test_validate_mismatch_records_raises_on_duplicate_key():
    records = _sample_records()
    dup = dict(records[0])
    records.append(dup)   # 同一個 (stock_id, date, column) 出現兩次
    with pytest.raises(AssertionError, match="重複"):
        adj.validate_mismatch_records(records, expected_total=3)


def test_validate_mismatch_records_raises_on_missing_field():
    records = _sample_records()
    del records[0]["signed_diff_new_minus_old"]
    with pytest.raises(AssertionError, match="缺少必要欄位"):
        adj.validate_mismatch_records(records, expected_total=2)


# =============================================================================
# 9. receipt 排他建立 (跟其他 diff receipt 一致的慣例)
# =============================================================================

def test_write_receipt_is_exclusive_create(tmp_path, monkeypatch):
    monkeypatch.setattr(adj, "RECEIPT_DIR", tmp_path)
    p1 = adj._write_receipt({"dummy": True})
    assert p1.exists()
    with pytest.raises(FileExistsError):
        with open(p1, "x", encoding="utf-8") as f:
            f.write("{}")
