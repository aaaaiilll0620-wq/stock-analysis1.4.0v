# -*- coding: utf-8 -*-
"""Phase D A-leg-only parity comparison (pure functions, unit-testable with
synthetic fixtures). Reuses r_fwd_adapter.raw_score_parity_result verbatim
for the raw-score axis -- never a second tolerance implementation.

Round 2 correction (per user 2026-08-15 review of Round 1's result):

1. Membership is NOT a reportable parity-gate result this round.
   `adapter_population(date)` = "every stock_id present in the frozen
   realbody parquet for that date" is NOT the frozen design's decision-time
   universe (`listed_ok(as_of) & adv20(as_of) >= 1,000,000`, phase_b_design_
   freeze.md Sec.10/12) -- it is merely whichever rows an independently-built
   upstream file happened to contain. Computing membership over the
   common-population intersection and reporting a 169/255-style verdict
   (Round 1's mistake) manufactures an official-looking number out of two
   populations that were never independently, correctly constructed to be
   comparable in the first place. Reason code: reused module-level constant
   `MEMBERSHIP_NOT_EVALUATED_REASON`.

   Population-difference DIAGNOSTICS are still computed and returned (never
   discarded -- they are the evidence for why membership is NOT_EVALUATED,
   and Round 1's mismatch pattern turned out to be entirely explained by
   population inequality, not by any score-precision effect: every single
   mismatched date in Round 1 had oracle_population != adapter_population;
   every equal-population date matched exactly). They MUST NOT be read as a
   parity-gate verdict.

2. Raw-score parity (over common keys) remains a real, computable metric
   once both sides use the SAME float32 storage representation the oracle's
   Panel.REAL_COMP actually carries (see a_leg_adapter.py's Round 2 fix) --
   this is unaffected by the decision-time-universe problem, since raw-score
   comparison only ever looks at keys both sides independently reported a
   score for.
"""
from __future__ import annotations

from identity_collector import r_fwd_adapter

MEMBERSHIP_NOT_EVALUATED_REASON = "INSUFFICIENT_FROZEN_DECISION_TIME_UNIVERSE_INPUTS"


def population_diagnostics(oracle_scores: dict, adapter_scores: dict) -> dict:
    """Informational only -- see module docstring. Never a parity-gate input."""
    oracle_keys, adapter_keys = set(oracle_scores), set(adapter_scores)
    common = oracle_keys & adapter_keys
    return {
        "oracle_population": len(oracle_keys),
        "adapter_population": len(adapter_keys),
        "common_population": len(common),
        "same_population_count": len(oracle_keys) == len(adapter_keys),
        "same_population_set": oracle_keys == adapter_keys,
        "oracle_only_count": len(oracle_keys - adapter_keys),
        "adapter_only_count": len(adapter_keys - oracle_keys),
    }


def a_leg_month_comparison(oracle_entry: dict, adapter_entry: dict, tolerance: float = 1e-12) -> dict:
    """oracle_entry/adapter_entry: {"scores": {stock_id: float}, "top20": [...]}.
    `top20` is retained on the input structures (still useful as a diagnostic
    for population-difference investigation) but this function no longer
    derives an official membership verdict from it -- see module docstring
    item 1."""
    oracle_scores, adapter_scores = oracle_entry["scores"], adapter_entry["scores"]
    diag = population_diagnostics(oracle_scores, adapter_scores)
    common = set(oracle_scores) & set(adapter_scores)
    if common:
        raw = r_fwd_adapter.raw_score_parity_result(
            {k: adapter_scores[k] for k in common}, {k: oracle_scores[k] for k in common}, tolerance=tolerance,
        )
    else:
        raw = {"common_keys_count": 0, "max_abs_diff": None, "tolerance": f"{tolerance:g}", "within_tolerance": None}

    return {
        "population_diagnostics": diag,
        "raw_score_parity": raw,
        "membership_status": "NOT_EVALUATED",
        "membership_reason_code": MEMBERSHIP_NOT_EVALUATED_REASON,
    }


def aggregate_a_leg_parity(oracle_by_date: dict, adapter_by_date: dict, tolerance: float = 1e-12) -> dict:
    dates = sorted(set(oracle_by_date) & set(adapter_by_date))
    per_date = {d: a_leg_month_comparison(oracle_by_date[d], adapter_by_date[d], tolerance) for d in dates}

    diffs = [per_date[d]["raw_score_parity"]["max_abs_diff"] for d in dates if per_date[d]["raw_score_parity"]["max_abs_diff"] is not None]
    within = [per_date[d]["raw_score_parity"]["within_tolerance"] for d in dates if per_date[d]["raw_score_parity"]["within_tolerance"] is not None]

    same_pop_set_dates = [d for d in dates if per_date[d]["population_diagnostics"]["same_population_set"]]
    diff_pop_set_dates = [d for d in dates if not per_date[d]["population_diagnostics"]["same_population_set"]]

    return {
        "scope": "A_LEG_ONLY",
        "months_tested": len(dates),
        "membership_status": "NOT_EVALUATED",
        "membership_reason_code": MEMBERSHIP_NOT_EVALUATED_REASON,
        "raw_score_max_abs_diff": max(diffs) if diffs else None,
        "raw_score_tolerance": f"{tolerance:g}",
        "raw_score_within_tolerance_all_dates": all(within) if within else None,
        "raw_score_common_keys_dates_with_data": len(diffs),
        "population_diagnostics_summary": {
            "note": "Informational only -- NOT a parity-gate result (see module docstring item 1).",
            "same_population_set_months": len(same_pop_set_dates),
            "different_population_set_months": len(diff_pop_set_dates),
        },
        "dates_missing_from_oracle_only": sorted(set(adapter_by_date) - set(oracle_by_date)),
        "dates_missing_from_adapter_only": sorted(set(oracle_by_date) - set(adapter_by_date)),
        "per_date": per_date,
    }
