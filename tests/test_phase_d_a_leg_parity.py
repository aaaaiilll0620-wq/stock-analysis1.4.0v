# -*- coding: utf-8 -*-
"""Phase D (2026-08-15, Round 2 correction) offline tests for the A-leg-only
parity runner. Round 2 changes covered here:
  1. Membership is NOT_EVALUATED (population-difference diagnostics only,
     never an official common-population-intersection verdict).
  2. Adapter reproduces the oracle's actual float32 storage representation
     before raw-score comparison (frozen-semantics reproduction, not tuning).

Synthetic-fixture unit tests for the runner MECHANISM, same convention as
Phase C's tests/test_identity_collector_qualification.py -- the actual run
against the real frozen snapshot is a separate driver invocation.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from identity_collector import a_leg_parity  # noqa: E402
from identity_collector import a_leg_adapter  # noqa: E402
from identity_collector import a_leg_oracle  # noqa: E402


# ============================================================================
# a_leg_parity.population_diagnostics / a_leg_month_comparison / aggregate
# ============================================================================
def test_population_diagnostics_equal_populations():
    oracle = {"2330": 90.0, "2317": 50.0, "1101": 10.0}
    adapter = {"2330": 90.0, "2317": 50.0, "1101": 10.0}
    diag = a_leg_parity.population_diagnostics(oracle, adapter)
    assert diag["same_population_count"] is True
    assert diag["same_population_set"] is True
    assert diag["oracle_only_count"] == diag["adapter_only_count"] == 0


def test_population_diagnostics_different_populations():
    oracle = {"A": 1.0, "B": 2.0, "D": 3.0}
    adapter = {"A": 1.0, "B": 2.0}
    diag = a_leg_parity.population_diagnostics(oracle, adapter)
    assert diag["same_population_count"] is False
    assert diag["same_population_set"] is False
    assert diag["oracle_only_count"] == 1
    assert diag["adapter_only_count"] == 0
    assert diag["common_population"] == 2


def test_a_leg_month_comparison_never_reports_membership_verdict():
    """Round 2: no membership exact-match field survives -- only NOT_EVALUATED
    plus the reason code, alongside population diagnostics."""
    oracle = {"scores": {"A": 99.0, "B": 50.0}, "top20": ["A"]}
    adapter = {"scores": {"A": 99.0, "B": 50.0}, "top20": ["A"]}
    result = a_leg_parity.a_leg_month_comparison(oracle, adapter)
    assert result["membership_status"] == "NOT_EVALUATED"
    assert result["membership_reason_code"] == "INSUFFICIENT_FROZEN_DECISION_TIME_UNIVERSE_INPUTS"
    assert "membership" not in result  # Round 1's official-looking field must not reappear
    assert result["population_diagnostics"]["same_population_set"] is True


def test_a_leg_month_comparison_raw_score_still_computed():
    oracle = {"scores": {"2330": 90.0}, "top20": ["2330"]}
    adapter = {"scores": {"2330": 90.0 + 1e-6}, "top20": ["2330"]}
    result = a_leg_parity.a_leg_month_comparison(oracle, adapter)
    assert result["raw_score_parity"]["within_tolerance"] is False
    assert result["raw_score_parity"]["max_abs_diff"] > 1e-12


def test_a_leg_month_comparison_no_common_keys():
    oracle = {"scores": {"A": 1.0}, "top20": ["A"]}
    adapter = {"scores": {"B": 2.0}, "top20": ["B"]}
    result = a_leg_parity.a_leg_month_comparison(oracle, adapter)
    assert result["raw_score_parity"]["common_keys_count"] == 0
    assert result["raw_score_parity"]["within_tolerance"] is None


def test_aggregate_a_leg_parity_membership_not_evaluated_with_population_summary():
    oracle_by_date, adapter_by_date = {}, {}
    for i in range(255):
        d = f"{2005 + i // 12}-{(i % 12) + 1:02d}-28"
        same = i % 2 == 0
        scores = {"2330": 90.0, "2317": 50.0}
        oracle_by_date[d] = {"scores": scores, "top20": ["2330"]}
        adapter_by_date[d] = {"scores": dict(scores) if same else {"2330": 90.0}, "top20": ["2330"]}
    result = a_leg_parity.aggregate_a_leg_parity(oracle_by_date, adapter_by_date)
    assert result["months_tested"] == 255
    assert result["membership_status"] == "NOT_EVALUATED"
    assert "membership_exact_match_count" not in result  # Round 1's field must not reappear
    summary = result["population_diagnostics_summary"]
    assert summary["same_population_set_months"] + summary["different_population_set_months"] == 255
    assert summary["same_population_set_months"] == 128  # i even: 0,2,...,254 -> 128 months
    assert result["raw_score_within_tolerance_all_dates"] is True  # "2330" common in every month, identical value


def test_aggregate_a_leg_parity_reports_date_set_mismatches():
    oracle_by_date = {"2020-01-31": {"scores": {"A": 1.0}, "top20": ["A"]}}
    adapter_by_date = {"2020-02-29": {"scores": {"A": 1.0}, "top20": ["A"]}}
    result = a_leg_parity.aggregate_a_leg_parity(oracle_by_date, adapter_by_date)
    assert result["months_tested"] == 0
    assert result["dates_missing_from_oracle_only"] == ["2020-02-29"]
    assert result["dates_missing_from_adapter_only"] == ["2020-01-31"]


# ============================================================================
# a_leg_adapter mechanism -- synthetic parquet fixture, float32 representation fix
# ============================================================================
def test_a_leg_adapter_loads_and_ranks_from_synthetic_realbody_parquet(tmp_path):
    df = pd.DataFrame({
        "as_of": ["2020-01-31"] * 5 + ["2020-02-29"] * 5,
        "stock_id": ["1", "2", "3", "4", "5"] * 2,
        "real_composite": [90.0, 80.0, 70.0, 60.0, 50.0, 10.0, 20.0, 30.0, 40.0, 50.0],
    })
    p = tmp_path / "realbody_scores_adv100w.parquet"
    df.to_parquet(p, index=False)

    by_date = a_leg_adapter.load_adapter_a_leg_scores(p)
    assert set(by_date) == {"2020-01-31", "2020-02-29"}
    assert by_date["2020-01-31"]["1"] == 90.0

    top20 = a_leg_adapter.topk_by_rank(by_date["2020-01-31"], top_pct=20)
    assert top20 == ["1"]


def test_a_leg_adapter_applies_float32_storage_representation(tmp_path):
    """Round 2 regression test for the frozen-semantics reproduction fix:
    a float64 value that is NOT exactly representable in float32 must come
    back truncated to its float32-rounded value, matching what
    Panel.REAL_COMP (built via high52_lab.py's float32-default `mat()`)
    would actually carry for the same underlying number."""
    exact_value = 71.23456789012345  # not exactly representable in float32
    df = pd.DataFrame({"as_of": ["2020-01-31"], "stock_id": ["1"], "real_composite": [exact_value]})
    p = tmp_path / "realbody_scores_adv100w.parquet"
    df.to_parquet(p, index=False)

    by_date = a_leg_adapter.load_adapter_a_leg_scores(p)
    loaded = by_date["2020-01-31"]["1"]
    expected_float32_truncated = float(np.float32(exact_value))
    assert loaded == expected_float32_truncated
    assert loaded != exact_value  # the truncation must be real, not a no-op


def test_float32_truncation_brings_common_key_raw_scores_within_tolerance():
    """Proves the Round 2 fix actually closes the ~1e-6 gap Round 1 measured:
    an oracle-shaped float32 value and an adapter-shaped float64 value that
    both originate from the SAME underlying number are within 1e-12 once the
    adapter also truncates to float32 -- and are NOT within 1e-12 if it
    doesn't (reproducing Round 1's exact failure mode as a regression guard)."""
    from identity_collector import r_fwd_adapter

    raw_value = 71.234567890123  # arbitrary high-precision float64 source value
    oracle_value = float(np.float32(raw_value))  # Panel.REAL_COMP's real representation

    # Round 1 behavior (adapter uses native float64) -- must NOT be within tolerance.
    without_fix = r_fwd_adapter.raw_score_parity_result({"X": raw_value}, {"X": oracle_value})
    assert without_fix["within_tolerance"] is False
    assert without_fix["max_abs_diff"] > 1e-12

    # Round 2 fix (adapter also truncates to float32 before comparison).
    adapter_value = float(np.float32(raw_value))
    with_fix = r_fwd_adapter.raw_score_parity_result({"X": adapter_value}, {"X": oracle_value})
    assert with_fix["within_tolerance"] is True
    assert with_fix["max_abs_diff"] == 0.0


def test_a_leg_adapter_static_import_audit_finds_no_forbidden_reference():
    module_path = REPO_ROOT / "scripts" / "identity_collector" / "a_leg_adapter.py"
    audit = a_leg_adapter.static_import_audit(module_path)
    assert audit["forbidden_targets_reached"] == [], audit


def test_a_leg_adapter_module_never_imports_high52_lab_statically():
    src = (REPO_ROOT / "scripts" / "identity_collector" / "a_leg_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not any("high52_lab" in n or "beat_0050" in n for n in names), names


# ============================================================================
# a_leg_oracle mechanism -- topk reuses canonical_universe.topk_mask_desc
# ============================================================================
def test_a_leg_oracle_by_date_uses_canonical_universe_topk_primitive():
    class FakePanel:
        pass

    P = FakePanel()
    P.REAL_COMP = np.array([[90.0, 80.0, 70.0, 60.0, 50.0]])
    P.tier_valid = {"100萬": np.array([[True, True, True, True, True]])}
    P.month_s = np.array(["2020-01-31"])
    P.stocks = np.array(["1", "2", "3", "4", "5"])

    by_date = a_leg_oracle.oracle_a_leg_by_date(P)
    assert by_date["2020-01-31"]["scores"]["1"] == 90.0
    assert by_date["2020-01-31"]["top20"] == ["1"]  # floor(5*20/100)=1
