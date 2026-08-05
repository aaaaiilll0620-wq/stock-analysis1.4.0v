# -*- coding: utf-8 -*-
"""Phase 1 Full-Universe Audit runner 的結構稽核測試。

規格:docs/規格_推薦投組系統V2_Phase1_FullUniverseAudit.md §9。

只用本檔 `tmp_path` 產生的 synthetic parquet fixture —— **不讀取、不指向**任何
`~/tej_cache`、`~/finmind_cache`、`data/research_base/` 下的真實檔案。核心稽核
函式 (`audit_dataset`/`audit_obs_exec_pair`/`audit_frozen_panels`/`run_audit`)
全部吃顯式路徑參數,呼叫這些函式本身不會觸發 CLI 的 `--execute` 安全閘門。

⚠ 不計算任何報酬/IC/CAGR/Sharpe/MDD/Top K,不產生任何訊號或投組建議。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

audit = pytest.importorskip("portfolio_v2_phase1_audit")


# =============================================================================
# fixtures —— 全部合成資料,寫在 tmp_path 底下
# =============================================================================

def _price_valuation_spec():
    return audit.DATASET_SPECS["tej_price_valuation"]


def _good_price_df(stock_id: str = "1101", n: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="D")
    return pd.DataFrame({
        "stock_id": [stock_id] * n,
        "date": dates.strftime("%Y-%m-%d"),
        "open": np.linspace(10, 11, n),
        "max": np.linspace(10.5, 11.5, n),
        "min": np.linspace(9.5, 10.5, n),
        "close": np.linspace(10, 11, n),
        "Trading_Volume": np.arange(1000, 1000 + n),
        "PER_TSE": np.linspace(12, 13, n),
        "PER_TEJ": np.linspace(12, 13, n),
        "PBR_TSE": np.linspace(1.2, 1.3, n),
        "PBR_TEJ": np.linspace(1.2, 1.3, n),
        "dividend_yield_TSE": np.linspace(2.0, 2.1, n),
    })


def _write_parquet(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def _obs_alpha_df(keys) -> pd.DataFrame:
    as_of, stock_id = zip(*keys)
    return pd.DataFrame({
        "as_of": list(as_of), "stock_id": list(stock_id),
        "adv20": [1e7] * len(keys), "listed_ok": [True] * len(keys),
    })


def _exec_ret_df(keys, fwd_x=None) -> pd.DataFrame:
    as_of, stock_id = zip(*keys)
    n = len(keys)
    return pd.DataFrame({
        "as_of": list(as_of), "stock_id": list(stock_id),
        "fwd_x": (fwd_x if fwd_x is not None else [0.01] * n),
        "px_in": [100.0] * n, "tick_slip": [0.0] * n,
    })


def _realbody_df(keys) -> pd.DataFrame:
    as_of, stock_id = zip(*keys)
    n = len(keys)
    return pd.DataFrame({
        "as_of": list(as_of), "stock_id": list(stock_id),
        "real_composite": [0.5] * n, "rating": ["A"] * n,
        "f_fund": [0.1] * n, "f_val": [0.1] * n, "f_tech": [0.1] * n,
        "f_mom": [0.1] * n, "f_whale": [0.1] * n,
    })


def _build_all_a_datasets(tmp_path) -> dict:
    """把 6 個 A 類 dataset 各寫一份結構乾淨的檔案,回傳 {dataset_id: root} 供 run_audit() 用。"""
    roots = {}
    for dataset_id, spec in audit.DATASET_SPECS.items():
        root = tmp_path / dataset_id
        if dataset_id in ("tej_price_valuation", "finmind_price"):
            df = _good_price_df("1101")
        elif dataset_id == "tej_institutional_gross":
            df = pd.DataFrame({
                "stock_id": ["1101"], "date": ["2024-01-02"],
                "foreign_buy": [1.0], "foreign_sell": [1.0],
                "trust_buy": [1.0], "trust_sell": [1.0],
                "foreign_holding_pct": [10.0], "trust_holding_pct": [5.0],
            })
        elif dataset_id == "tej_margin_balance":
            df = pd.DataFrame({"stock_id": ["1101"], "date": ["2024-01-02"],
                                "margin_balance": [100.0], "short_balance": [10.0]})
        elif dataset_id == "tej_tdcc_weekly":
            df = pd.DataFrame({
                "stock_id": ["1101"], "date": ["2024-01-05"],
                "ratio_1000up": [10.0], "ratio_le1": [20.0], "ratio_1to5": [15.0],
                "ratio_5to10": [5.0], "holders": [1000], "total_lots_thousand": [500000.0],
            })
        elif dataset_id == "tej_director_pledge":
            df = pd.DataFrame({
                "stock_id": ["1101"], "date": ["2024-01-01"],
                "pledge_pct": [0.0], "director_holding_pct": [5.0], "group_name": [""],
            })
        else:
            raise AssertionError(f"未覆蓋的 dataset_id: {dataset_id}")
        _write_parquet(root / "1101.parquet", df)
        roots[dataset_id] = root
    return roots


def _all_missing_dataset_roots(tmp_path) -> dict:
    return {dsid: tmp_path / "missing" / dsid for dsid in audit.DATASET_SPECS}


# =============================================================================
# audit_file / audit_dataset —— 類別 A(逐股 TEJ/FinMind 原始檔)
# =============================================================================

def test_normal_file_passes(tmp_path):
    root = tmp_path / "price_valuation"
    _write_parquet(root / "1101.parquet", _good_price_df("1101"))

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "PASS"
    assert report["file_count"] == 1
    f = report["files"][0]
    assert f["status"] == "PASS"
    assert f["missing_columns"] == []
    assert f["empty_file"] is False
    assert f["duplicate_key_rows"] == 0
    assert f["bad_date_rows"] == 0
    assert f["filename_stock_id_mismatch_rows"] == 0


def test_missing_column_fails(tmp_path):
    root = tmp_path / "price_valuation"
    df = _good_price_df("1101").drop(columns=["PER_TSE"])
    _write_parquet(root / "1101.parquet", df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "FAIL"
    f = report["files"][0]
    assert f["status"] == "FAIL"
    assert "PER_TSE" in f["missing_columns"]


def test_duplicate_key_fails(tmp_path):
    root = tmp_path / "price_valuation"
    df = _good_price_df("1101", n=3)
    df.loc[len(df)] = df.loc[0]  # 重複同一個 date
    _write_parquet(root / "1101.parquet", df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "FAIL"
    assert report["files"][0]["duplicate_key_rows"] > 0


def test_filename_stock_id_mismatch_fails(tmp_path):
    root = tmp_path / "price_valuation"
    df = _good_price_df("2330")  # 內容是 2330,檔名卻是 1101
    _write_parquet(root / "1101.parquet", df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "FAIL"
    f = report["files"][0]
    assert f["status"] == "FAIL"
    assert f["filename_stock_id_mismatch_rows"] == len(df)


def test_bad_date_fails(tmp_path):
    root = tmp_path / "price_valuation"
    df = _good_price_df("1101", n=4)
    df.loc[1, "date"] = "not-a-date"
    _write_parquet(root / "1101.parquet", df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "FAIL"
    assert report["files"][0]["bad_date_rows"] == 1


def test_read_failure_does_not_abort_other_files(tmp_path):
    """規格 §6.5:逐檔失敗不中斷 —— 一個壞檔不得讓其餘檔案沒被稽核到。"""
    root = tmp_path / "price_valuation"
    root.mkdir(parents=True)
    _write_parquet(root / "1101.parquet", _good_price_df("1101"))
    (root / "2330.parquet").write_bytes(b"not a real parquet file")

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "FAIL"
    assert report["file_count"] == 2
    by_name = {f["path"]: f for f in report["files"]}
    assert by_name["1101.parquet"]["status"] == "PASS"
    assert by_name["2330.parquet"]["status"] == "FAIL"
    assert by_name["2330.parquet"]["read_ok"] is False
    assert by_name["2330.parquet"]["read_error"]


def test_missing_root_dir_is_missing_not_fail(tmp_path):
    root = tmp_path / "does_not_exist"
    report = audit.audit_dataset(_price_valuation_spec(), root)
    assert report["status"] == "MISSING"
    assert report["files"] == []


def test_empty_root_dir_is_empty_not_fail(tmp_path):
    root = tmp_path / "price_valuation"
    root.mkdir(parents=True)
    report = audit.audit_dataset(_price_valuation_spec(), root)
    assert report["status"] == "EMPTY"
    assert report["files"] == []


def test_coverage_and_nulls_are_measured_not_judged(tmp_path):
    """短覆蓋率、含 null 數值欄不應該讓結構乾淨的檔案變成 FAIL —— 只記錄在 measured。"""
    root = tmp_path / "price_valuation"
    df = _good_price_df("1101", n=2)  # 只有 2 天,覆蓋率極短
    df.loc[0, "PER_TSE"] = np.nan
    _write_parquet(root / "1101.parquet", df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "PASS"
    measured = report["files"][0]["measured"]
    assert measured["date_min"] is not None
    assert measured["date_max"] is not None
    assert measured["null_counts"]["PER_TSE"] == 1


# =============================================================================
# 修正必修2:零列 parquet fail-closed
# =============================================================================

def test_empty_file_zero_rows_fails(tmp_path):
    root = tmp_path / "price_valuation"
    empty_df = _good_price_df("1101", n=0)  # schema 合法,0 列
    _write_parquet(root / "1101.parquet", empty_df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    assert report["status"] == "FAIL"
    f = report["files"][0]
    assert f["status"] == "FAIL"
    assert f["empty_file"] is True
    assert f["missing_columns"] == []  # schema 本身沒問題,純粹是 0 列
    assert f["measured"]["row_count"] == 0


# =============================================================================
# 修正必修1:讀檔一律先讀 schema metadata,再只投影允許欄位(obs_alpha 不得含 fwd)
# =============================================================================

def test_read_projected_parquet_never_requests_fwd_for_obs_alpha(tmp_path, monkeypatch):
    obs_p = tmp_path / "obs_alpha.parquet"
    df = _obs_alpha_df([("2024-01-31", "1101"), ("2024-01-31", "2330")])
    df["fwd"] = [999.0, -999.0]  # 即使檔案裡真的存在 fwd 欄
    _write_parquet(obs_p, df)

    real_read_parquet = audit.pd.read_parquet
    requested_columns_calls = []

    def _spy_read_parquet(path, columns=None, **kwargs):
        requested_columns_calls.append(columns)
        return real_read_parquet(path, columns=columns, **kwargs)

    monkeypatch.setattr(audit.pd, "read_parquet", _spy_read_parquet)

    f = audit.audit_file(obs_p, audit.OBS_ALPHA_REQUIRED_COLUMNS,
                          audit.OBS_ALPHA_KEY_COLUMNS, date_column="as_of")

    assert f.status == "PASS"
    assert requested_columns_calls, "read_parquet 應該至少被呼叫一次"
    for requested in requested_columns_calls:
        assert requested is not None, "必須顯式投影欄位,不得整檔載入(columns=None 等於整檔讀)"
        assert "fwd" not in requested


def test_read_projected_parquet_reports_missing_without_requesting_it(tmp_path):
    """allowed_columns 裡有一欄根本不存在於檔案 schema 時,不該把它塞進 columns= 去讀。"""
    obs_p = tmp_path / "obs_alpha.parquet"
    _write_parquet(obs_p, _obs_alpha_df([("2024-01-31", "1101")]))

    df, missing, num_rows = audit.read_projected_parquet(
        obs_p, ("as_of", "stock_id", "does_not_exist_column"))

    assert missing == ["does_not_exist_column"]
    assert "does_not_exist_column" not in df.columns
    assert num_rows == 1


def test_obs_alpha_fwd_column_never_required_or_touched(tmp_path):
    """規格 §2.2:obs_alpha.fwd 不得被列為必要欄位、不得被讀取檢查。"""
    assert "fwd" not in audit.OBS_ALPHA_REQUIRED_COLUMNS
    keys = [("2024-01-31", "1101")]
    obs_p = tmp_path / "obs_alpha.parquet"
    df = _obs_alpha_df(keys)
    df["fwd"] = [999.0]
    _write_parquet(obs_p, df)

    f = audit.audit_file(obs_p, audit.OBS_ALPHA_REQUIRED_COLUMNS,
                          audit.OBS_ALPHA_KEY_COLUMNS, date_column="as_of")
    assert f.status == "PASS"
    assert "fwd" not in f.measured["null_counts"]
    assert "fwd" not in f.measured["non_finite_counts"]
    assert "fwd" not in f.measured["coercion_failure_counts"]


# =============================================================================
# obs_alpha / exec_ret —— 類別 B
# =============================================================================

def test_obs_exec_normal_pass_and_keyset_aligned(tmp_path):
    keys = [("2024-01-31", "1101"), ("2024-01-31", "2330")]
    obs_p = tmp_path / "obs_alpha.parquet"
    exec_p = tmp_path / "exec_ret.parquet"
    _write_parquet(obs_p, _obs_alpha_df(keys))
    _write_parquet(exec_p, _exec_ret_df(keys))

    result = audit.audit_obs_exec_pair(obs_p, exec_p)

    assert result["obs_alpha_status"] == "PASS"
    assert result["exec_ret_status"] == "PASS"
    assert result["keyset_status"] == "PASS"
    assert result["measured"]["in_both"] == 2
    assert result["measured"]["only_in_obs_alpha"] == 0
    assert result["measured"]["only_in_exec_ret"] == 0


def test_obs_exec_keyset_misalignment_is_measured_not_judged(tmp_path):
    obs_keys = [("2024-01-31", "1101"), ("2024-01-31", "9999")]
    exec_keys = [("2024-01-31", "1101"), ("2024-01-31", "2330")]
    obs_p = tmp_path / "obs_alpha.parquet"
    exec_p = tmp_path / "exec_ret.parquet"
    _write_parquet(obs_p, _obs_alpha_df(obs_keys))
    _write_parquet(exec_p, _exec_ret_df(exec_keys))

    result = audit.audit_obs_exec_pair(obs_p, exec_p)

    assert result["obs_alpha_status"] == "PASS"
    assert result["exec_ret_status"] == "PASS"
    assert result["keyset_status"] == "PASS"  # 量測本身成功;數量差異只是 MEASURED_NOT_JUDGED
    assert result["measured"]["only_in_obs_alpha"] == 1
    assert result["measured"]["only_in_exec_ret"] == 1
    assert result["measured"]["in_both"] == 1


def test_exec_ret_fwd_x_missing_and_nonfinite_measured(tmp_path):
    keys = [("2024-01-31", "1101"), ("2024-01-31", "2330"), ("2024-01-31", "2603")]
    exec_p = tmp_path / "exec_ret.parquet"
    _write_parquet(exec_p, _exec_ret_df(keys, fwd_x=[0.01, np.nan, np.inf]))

    f = audit.audit_file(exec_p, audit.EXEC_RET_REQUIRED_COLUMNS,
                          audit.EXEC_RET_KEY_COLUMNS, date_column="as_of",
                          numeric_check_columns=audit.EXEC_RET_NUMERIC_CHECK_COLUMNS)

    assert f.status == "PASS"
    assert f.measured["null_counts"]["fwd_x"] == 1
    assert f.measured["non_finite_counts"]["fwd_x"] == 1
    assert f.measured["coercion_failure_counts"]["fwd_x"] == 0


def test_obs_or_exec_missing_file_reports_missing(tmp_path):
    obs_p = tmp_path / "obs_alpha.parquet"  # 不存在
    exec_p = tmp_path / "exec_ret.parquet"
    _write_parquet(exec_p, _exec_ret_df([("2024-01-31", "1101")]))

    result = audit.audit_obs_exec_pair(obs_p, exec_p)

    assert result["obs_alpha_status"] == "MISSING"
    assert result["exec_ret_status"] == "PASS"
    assert result["keyset_status"] == "NOT_MEASURED"  # gap 已由 obs_alpha_status 反映,不重複算
    assert result["measured"]["in_both"] is None


# ---- 修正必修1(第二輪 review):key-set 量測本身失敗必須 fail-closed --------------

def test_keyset_measurement_failure_is_fail_closed(tmp_path, monkeypatch):
    """兩檔各自的個別稽核都成功,但 key-set 第二次投影讀取途中丟例外 —— 不得只
    靜靜寫進 measured.error,keyset_status 必須是 FAIL,且要能傳到 overall_status。"""
    keys = [("2024-01-31", "1101")]
    obs_p = tmp_path / "obs_alpha.parquet"
    exec_p = tmp_path / "exec_ret.parquet"
    _write_parquet(obs_p, _obs_alpha_df(keys))
    _write_parquet(exec_p, _exec_ret_df(keys))

    real_read_projected = audit.read_projected_parquet

    def _boom(path, allowed_columns):
        if tuple(allowed_columns) == ("as_of", "stock_id"):  # 只有 key-set 階段會用純鍵欄投影
            raise RuntimeError("simulated key-set read failure")
        return real_read_projected(path, allowed_columns)

    monkeypatch.setattr(audit, "read_projected_parquet", _boom)

    result = audit.audit_obs_exec_pair(obs_p, exec_p)

    assert result["obs_alpha_status"] == "PASS"  # 個別檔案稽核用的是完整必要欄位,不受影響
    assert result["exec_ret_status"] == "PASS"
    assert result["keyset_status"] == "FAIL"
    assert "error" in result["measured"]


def test_run_audit_fails_when_keyset_measurement_fails(tmp_path, monkeypatch):
    roots = _build_all_a_datasets(tmp_path)
    research_base = tmp_path / "research_base"
    keys = [("2024-01-31", "1101")]
    _write_parquet(research_base / "obs_alpha.parquet", _obs_alpha_df(keys))
    _write_parquet(research_base / "exec_ret.parquet", _exec_ret_df(keys))
    _write_parquet(research_base / "realbody_scores.parquet", _realbody_df(keys))

    real_read_projected = audit.read_projected_parquet

    def _boom(path, allowed_columns):
        if tuple(allowed_columns) == ("as_of", "stock_id"):
            raise RuntimeError("simulated key-set read failure")
        return real_read_projected(path, allowed_columns)

    monkeypatch.setattr(audit, "read_projected_parquet", _boom)

    report = audit.run_audit(dataset_roots=roots, research_base=research_base)

    assert report["overall_status"] == "FAIL"
    assert report["obs_exec_keyset"]["keyset_status"] == "FAIL"
    # 個別 dataset/檔案結構仍乾淨,證明這個 FAIL 確實是 keyset_status 傳導的,不是巧合
    assert all(d["status"] == "PASS" for d in report["datasets"].values())


# =============================================================================
# 修正必修7:coercion_failure_counts(字串轉數值失敗,既非 null 也非 non-finite)
# =============================================================================

def test_coercion_failure_counts_captures_unparseable_strings(tmp_path):
    root = tmp_path / "price_valuation"
    df = _good_price_df("1101", n=3)
    df["PER_TSE"] = df["PER_TSE"].astype(str)
    df.loc[1, "PER_TSE"] = "abc"  # 無法轉數值的字串雜訊,原始值非缺值
    _write_parquet(root / "1101.parquet", df)

    report = audit.audit_dataset(_price_valuation_spec(), root)

    f = report["files"][0]
    assert f["status"] == "PASS"  # 結構仍乾淨,只是記錄
    assert f["measured"]["coercion_failure_counts"]["PER_TSE"] == 1
    assert f["measured"]["null_counts"].get("PER_TSE", 0) == 0
    assert f["measured"]["non_finite_counts"].get("PER_TSE", 0) == 0


# =============================================================================
# frozen realbody_scores* —— 類別 C(只讀 hash/schema/鍵完整性)
# =============================================================================

def test_frozen_panel_normal_pass_with_hash(tmp_path):
    p = tmp_path / "realbody_scores.parquet"
    _write_parquet(p, _realbody_df([("2024-01-31", "1101"), ("2024-01-31", "2330")]))

    result = audit.audit_frozen_panels([p], research_base_exists=True)

    assert result["status"] == "PASS"
    entry = result["files"]["realbody_scores.parquet"]
    assert entry["status"] == "PASS"
    assert entry["sha256"] is not None
    assert len(entry["sha256"]) == 64


def test_frozen_panel_duplicate_key_fails(tmp_path):
    p = tmp_path / "realbody_scores.parquet"
    df = _realbody_df([("2024-01-31", "1101")])
    df.loc[1] = df.loc[0]
    _write_parquet(p, df)

    result = audit.audit_frozen_panels([p], research_base_exists=True)

    assert result["status"] == "FAIL"
    assert result["files"]["realbody_scores.parquet"]["status"] == "FAIL"
    assert result["files"]["realbody_scores.parquet"]["duplicate_key_rows"] > 0


def test_frozen_panel_does_not_modify_file(tmp_path):
    p = tmp_path / "realbody_scores.parquet"
    _write_parquet(p, _realbody_df([("2024-01-31", "1101")]))
    before = p.read_bytes()

    audit.audit_frozen_panels([p], research_base_exists=True)

    assert p.read_bytes() == before


def test_frozen_panels_no_files_but_dir_exists_is_empty_group(tmp_path):
    result = audit.audit_frozen_panels([], research_base_exists=True)
    assert result["status"] == "EMPTY"
    assert result["files"] == {}


def test_frozen_panels_research_base_missing_is_missing_group(tmp_path):
    result = audit.audit_frozen_panels([], research_base_exists=False)
    assert result["status"] == "MISSING"
    assert result["files"] == {}


# =============================================================================
# run_audit —— 整份報告的 overall_status 判定(規格 §4.3)
# =============================================================================

def test_run_audit_all_missing_is_pass_with_gaps(tmp_path):
    research_base = tmp_path / "research_base"  # 不建立
    report = audit.run_audit(dataset_roots=_all_missing_dataset_roots(tmp_path),
                              research_base=research_base)

    assert report["overall_status"] == "PASS_WITH_GAPS"
    assert all(d["status"] == "MISSING" for d in report["datasets"].values())
    assert report["obs_exec_keyset"]["obs_alpha_status"] == "MISSING"
    assert report["frozen_panels"]["status"] == "MISSING"
    assert report["frozen_panels"]["files"] == {}


def test_run_audit_one_dataset_fail_propagates_to_overall(tmp_path):
    roots = _all_missing_dataset_roots(tmp_path)
    bad_root = tmp_path / "price_valuation_bad"
    df = _good_price_df("1101").drop(columns=["close"])  # 缺欄 → FAIL
    _write_parquet(bad_root / "1101.parquet", df)
    roots["tej_price_valuation"] = bad_root

    report = audit.run_audit(dataset_roots=roots, research_base=tmp_path / "research_base")

    assert report["overall_status"] == "FAIL"
    assert report["datasets"]["tej_price_valuation"]["status"] == "FAIL"


def test_run_audit_fully_populated_is_pass(tmp_path):
    roots = _build_all_a_datasets(tmp_path)

    research_base = tmp_path / "research_base"
    keys = [("2024-01-31", "1101")]
    _write_parquet(research_base / "obs_alpha.parquet", _obs_alpha_df(keys))
    _write_parquet(research_base / "exec_ret.parquet", _exec_ret_df(keys))
    _write_parquet(research_base / "realbody_scores.parquet", _realbody_df(keys))

    report = audit.run_audit(dataset_roots=roots, research_base=research_base)

    assert report["overall_status"] == "PASS"
    assert all(d["status"] == "PASS" for d in report["datasets"].values())
    assert report["obs_exec_keyset"]["obs_alpha_status"] == "PASS"
    assert report["obs_exec_keyset"]["exec_ret_status"] == "PASS"
    assert report["frozen_panels"]["status"] == "PASS"
    assert report["frozen_panels"]["files"]["realbody_scores.parquet"]["status"] == "PASS"


def test_run_audit_output_is_deterministic(tmp_path):
    research_base = tmp_path / "research_base"
    report1 = audit.run_audit(dataset_roots=_all_missing_dataset_roots(tmp_path),
                               research_base=research_base)
    report2 = audit.run_audit(dataset_roots=_all_missing_dataset_roots(tmp_path),
                               research_base=research_base)
    assert report1 == report2


# ---- 修正必修3:run_audit() 不得有真實路徑預設值,省略即 fail-closed --------------

def test_run_audit_no_args_raises_type_error(tmp_path):
    with pytest.raises(TypeError):
        audit.run_audit()


def test_run_audit_missing_dataset_root_key_raises_value_error(tmp_path):
    incomplete_roots = _all_missing_dataset_roots(tmp_path)
    incomplete_roots.pop("tej_price_valuation")
    with pytest.raises(ValueError):
        audit.run_audit(dataset_roots=incomplete_roots, research_base=tmp_path / "research_base")


# ---- 修正必修6:只有 frozen 缺失、其餘全 PASS → PASS_WITH_GAPS -------------------

def test_only_frozen_missing_yields_pass_with_gaps(tmp_path):
    roots = _build_all_a_datasets(tmp_path)

    research_base = tmp_path / "research_base"
    keys = [("2024-01-31", "1101")]
    _write_parquet(research_base / "obs_alpha.parquet", _obs_alpha_df(keys))
    _write_parquet(research_base / "exec_ret.parquet", _exec_ret_df(keys))
    # 故意不寫任何 realbody_scores*.parquet,但 research_base 目錄本身存在

    report = audit.run_audit(dataset_roots=roots, research_base=research_base)

    assert report["overall_status"] == "PASS_WITH_GAPS"
    assert report["frozen_panels"]["status"] == "EMPTY"
    assert all(d["status"] == "PASS" for d in report["datasets"].values())
    assert report["obs_exec_keyset"]["obs_alpha_status"] == "PASS"


# =============================================================================
# CLI 安全閘門 —— 規格 §6
# =============================================================================

def test_cli_default_does_not_touch_real_paths(monkeypatch, capsys):
    called = {"hit": False}

    def _boom(*a, **kw):
        called["hit"] = True
        raise AssertionError("run_audit() 不應該在沒有安全旗標時被呼叫")

    monkeypatch.setattr(audit, "run_audit", _boom)

    rc = audit.main([])
    assert rc == 0
    assert called["hit"] is False
    out = capsys.readouterr().out
    assert "不掃描任何真實資料" in out


def test_cli_execute_only_returns_2(monkeypatch, capsys):
    called = {"hit": False}
    monkeypatch.setattr(audit, "run_audit", lambda *a, **kw: called.update(hit=True))

    rc = audit.main(["--execute"])

    assert rc == 2
    assert called["hit"] is False
    err = capsys.readouterr().err
    assert "i-understand-this-reads-real-cache" in err


def test_cli_confirmation_only_returns_2(monkeypatch, capsys):
    called = {"hit": False}
    monkeypatch.setattr(audit, "run_audit", lambda *a, **kw: called.update(hit=True))

    rc = audit.main(["--i-understand-this-reads-real-cache"])

    assert rc == 2
    assert called["hit"] is False
    err = capsys.readouterr().err
    assert "--execute" in err


def test_cli_both_flags_builds_real_paths_and_invokes_run_audit(monkeypatch, capsys):
    captured = {}

    def _stub(dataset_roots, research_base):
        captured["dataset_roots"] = dataset_roots
        captured["research_base"] = research_base
        return {"overall_status": "PASS", "datasets": {}, "obs_exec_keyset": {},
                "frozen_panels": {"status": "PASS", "files": {}}, "spec_version": "1.0"}

    monkeypatch.setattr(audit, "run_audit", _stub)

    rc = audit.main(["--execute", "--i-understand-this-reads-real-cache"])

    assert rc == 0
    assert set(captured["dataset_roots"]) == set(audit.DATASET_SPECS)
    assert captured["research_base"] == audit._real_research_base()
    out = capsys.readouterr().out
    assert '"overall_status": "PASS"' in out


def test_cli_fail_overall_status_returns_exit_code_1(monkeypatch):
    stub_report = {"overall_status": "FAIL", "datasets": {}, "obs_exec_keyset": {},
                    "frozen_panels": {"status": "FAIL", "files": {}}, "spec_version": "1.0"}
    monkeypatch.setattr(audit, "run_audit", lambda *a, **kw: stub_report)

    rc = audit.main(["--execute", "--i-understand-this-reads-real-cache"])
    assert rc == 1


# ---- 修正必修5:輸出 deterministic 名實相符,不得含 generated_at 之類的時間戳 -----

def test_cli_output_is_byte_identical_across_two_runs(monkeypatch, tmp_path):
    stub_report = {"overall_status": "PASS_WITH_GAPS", "datasets": {}, "obs_exec_keyset": {},
                    "frozen_panels": {"status": "MISSING", "files": {}}, "spec_version": "1.0"}
    monkeypatch.setattr(audit, "run_audit", lambda *a, **kw: dict(stub_report))

    out1 = tmp_path / "r1.json"
    out2 = tmp_path / "r2.json"
    audit.main(["--execute", "--i-understand-this-reads-real-cache", "--output", str(out1)])
    audit.main(["--execute", "--i-understand-this-reads-real-cache", "--output", str(out2)])

    bytes1, bytes2 = out1.read_bytes(), out2.read_bytes()
    assert bytes1 == bytes2
    assert b"generated_at" not in bytes1
