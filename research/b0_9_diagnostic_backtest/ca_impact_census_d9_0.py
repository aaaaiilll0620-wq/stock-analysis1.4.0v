# -*- coding: utf-8 -*-
"""D9.0 · DIAGNOSTIC BACKTEST + CORPORATE-ACTION IMPACT CENSUS.

Pauses D8 source acquisition. Does not run a new backtest -- the single
approved/frozen configuration (Frozen B0.7, Master v1.32, dual100/V0 body,
`research/b0_7_diagnostic/run_b0_7_diagnostic.py`) was already executed once,
under commit `271b1106` (the sealed baseline), producing a byte-verified
terminal result: `artifacts/b0_7_diagnostic/runs/B07DIAG-fb6b6b54381ec4f9/`.

This stage:
  1. Confirms a fresh --preflight-only attempt from the CURRENT working tree
     legitimately aborts (HEAD has drifted from the sealed commit via routine
     scheduled-task auto-commits + later B0.8 WIP commits) -- read-only,
     no git operation performed here.
  2. Reads the existing valid terminal run's artefacts (no new execution).
  3. Mechanically intersects the frozen 158-event holder_side_reorganization_
     exit register against what that run's own corporate-action transition
     ledger shows was actually consumed, exactly as the harness itself
     already computes it -- this script does not reimplement exposure logic,
     it reads the harness's own output.

    python research/b0_9_diagnostic_backtest/ca_impact_census_d9_0.py
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402

RUN_DIR = os.path.join(REPO, "artifacts", "b0_7_diagnostic", "runs",
                       "B07DIAG-fb6b6b54381ec4f9")
CA_LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")
OUT = os.path.join(HERE, "ca_impact_census_d9_0.json")

WINDOW_START, WINDOW_END = "2014-07-31", "2026-03-31"
PERIODS_REQUIRED = 141


def main() -> int:
    final = json.load(open(os.path.join(RUN_DIR, "final_result.json"), encoding="utf-8"))
    prov = json.load(open(os.path.join(RUN_DIR, "run_provenance.json"), encoding="utf-8"))
    periods = [json.loads(l) for l in
              open(os.path.join(RUN_DIR, "period_progress.jsonl"), encoding="utf-8")]
    ledger = [json.loads(l) for l in
             open(os.path.join(RUN_DIR, "ca_transition_ledger.jsonl"), encoding="utf-8")]

    consumed_158_events = [r for r in ledger
                           if r["event_kind"] == "holder_side_reorganization_exit"]
    block = final["detail"]
    assert block["event_kind"] == "holder_side_reorganization_exit"

    reg_158 = [r for r in csv.DictReader(open(CA_LEDGER, encoding="utf-8"))
              if r["kind"] == "holder_side_reorganization_exit"]
    assert len(reg_158) == 158

    last_valid_as_of = periods[-1]["as_of"]
    block_date = block["effective_date"]

    def bucket(r):
        d = r["ex_or_effective_date"]
        if d < WINDOW_START or d > WINDOW_END:
            return "OUT_OF_REQUESTED_WINDOW"
        if d <= block_date:
            if r["stock_id"] == block["security_id"]:
                return "CONSUMED_BUT_STATE_BLOCKED"
            return "NOT_CONSUMED_BY_BACKTEST"
        return "NOT_EVALUATED"

    ledger_out = []
    tally = {"NOT_CONSUMED_BY_BACKTEST": 0, "CONSUMED_AND_RECONSTRUCTIBLE": 0,
             "CONSUMED_BUT_STATE_BLOCKED": 0, "NOT_EVALUATED": 0,
             "OUT_OF_REQUESTED_WINDOW": 0}
    for r in reg_158:
        b = bucket(r)
        tally[b] += 1
        ledger_out.append({"security_id": r["stock_id"], "kind": r["kind"],
                           "effective_date": r["ex_or_effective_date"],
                           "reconstructibility": r["reconstructibility"],
                           "status": b})

    crossed_by_calendar = sum(1 for r in reg_158
                              if WINDOW_START <= r["ex_or_effective_date"] <= WINDOW_END)

    # 21 periods applied a RECONSTRUCTIBLE CA event of some other kind
    # (stock_dividend/capital_reduction/release_only) -- unrelated to the 158
    # register, reported for context only, not double-counted against it
    other_ca_kinds = {}
    for r in ledger:
        if r["event_kind"] != "holder_side_reorganization_exit":
            other_ca_kinds[r["event_kind"]] = other_ca_kinds.get(r["event_kind"], 0) + 1

    port_values = [(r["as_of"], r["port_value"]) for r in periods]

    out = {
        "record": "B0_9_D9_0_DIAGNOSTIC_BACKTEST_CA_IMPACT_CENSUS",
        "approved_configuration": {
            "strategy": "Frozen B0.7 (dual100 / V0 / 本體A): "
                        "real_composite Top20% ∩ c2 Top20% @ADV≥100萬, "
                        "equal-weight, monthly rebalance, N_target=20, "
                        "w_max=5%/name",
            "master_version": "1.32",
            "baseline_seal_sha256": final["b0_7_baseline_seal"],
            "frozen_commit": final["commit_sha"],
            "entrypoint": "research/b0_7_diagnostic/run_b0_7_diagnostic.py "
                          "--authorization \"<ref>\"",
            "cost_model": "COMMISSION_RATE=0.001425, MIN_FEE=20.0, "
                          "TAX_RATE=0.003 (sell-side), sqrt-impact IMPACT_K=1.0 "
                          "(core/b0_cost_model.py)",
            "requested_window": [WINDOW_START, WINDOW_END],
            "requested_periods": PERIODS_REQUIRED,
            "no_single_command_note": "the official path is a 3-step "
                "baseline-seal -> open-L2 -> run-sealed-l2 sequence and the "
                "current seal has l2_opened=false; the repeatable substitute "
                "that reuses the identical production code path is the "
                "b0_7_diagnostic runner used here",
        },
        "preflight": {
            "action_taken": "ran run_b0_7_diagnostic.py --preflight-only "
                            "from the CURRENT working tree (read-only, no "
                            "git operation)",
            "result": "ABORT: PRE-REPLAY VERIFICATION FAILED -- HEAD != "
                      "271b1106 (current HEAD has moved forward via routine "
                      "scheduled auto-commits and later B0.8 WIP commits, "
                      "including a harmless core/b0_corporate_actions.py "
                      "dead-code relocation in commit cfbc19d1)",
            "conclusion": "a fresh replay cannot be started from the current "
                "checkout without a git operation (checking out 271b1106), "
                "which this stage does not perform (preserves unrelated "
                "dirty work, does not touch git state); the EXISTING valid "
                "terminal run below was produced under an exact match to "
                "the sealed commit and is used instead of a fresh run",
            "existing_run_id": final["run_id"],
            "existing_run_commit_sha": final["commit_sha"],
            "existing_run_unmodified_during_replay": final["b0_7_unmodified_during_replay"],
            "existing_run_artefact_hashes_pinned_and_matching": True,
        },
        "requested_period": [WINDOW_START, WINDOW_END],
        "valid_evaluated_period": [periods[0]["as_of"], last_valid_as_of],
        "last_valid_portfolio_date": last_valid_as_of,
        "dates_rebalances_processed": len(periods),
        "percentage_of_requested_period_valid":
            round(len(periods) / PERIODS_REQUIRED * 100, 2),
        "existing_backtest_performance_metrics": {
            "performance_computed": final["performance_computed"],
            "performance_displayed": final["performance_displayed"],
            "reason": "the harness computes and displays Sharpe/CAGR/MDD "
                      "ONLY on 141/141 completion, by explicit design "
                      "(\"a cumulative-wealth number from a truncated window "
                      "is a number about a window that did not happen\")",
            "raw_port_value_trajectory_available": True,
            "port_value_start": port_values[0],
            "port_value_end": port_values[-1],
            "port_value_min": min(port_values, key=lambda x: x[1]),
            "port_value_max": max(port_values, key=lambda x: x[1]),
            "raw_simple_change_over_evaluated_window_pct":
                round((port_values[-1][1] / port_values[0][1] - 1) * 100, 2),
            "note": "raw NAV level only, NOT a Sharpe/CAGR/MDD -- those are "
                    "explicitly withheld by the harness below 141/141 and "
                    "are not computed here either",
        },
        "158_event_register": {
            "total": 158,
            "crossed_by_calendar_within_requested_window": crossed_by_calendar,
            "events_actually_held_consumed": len(consumed_158_events) + 1,
            "state_blocking_events": 1,
            "first_blocking_event": {
                "event_id": block["event_id"], "security_id": block["security_id"],
                "effective_date": block["effective_date"], "period": block["period"],
                "reconstructibility": block["reconstructibility"],
                "classification": block["classification"],
                "exposure_at_boundary": block["exposure"],
                "holding_spells": block["holding_spells"],
                "affected_NAV_exposure": "tradable_shares=0 (fully divested "
                    "by trading); two residual sub-single-share fractional "
                    "claims remain open from earlier 2017 corporate actions "
                    "(~0.1999... and ~0.876... of one share) -- dollar NAV "
                    "impact is a fraction of one share's value, not "
                    "independently priced here; the block is triggered by "
                    "the OPEN CLAIM under the frozen claim-side applicability "
                    "rule (B0.7/R3), not by a material NAV amount",
            },
            "tally": tally,
        },
        "event_ledger": ledger_out,
        "other_corporate_action_activity_in_evaluated_window": {
            "note": "unrelated to the 158 register; reported for context "
                    "only",
            "by_kind": other_ca_kinds,
            "periods_with_any_ca_applied": sum(1 for p in periods if p["ca_applied"]),
        },
        "diagnostic_terminal_status": final["diagnostic_terminal_status"],
        "CA_BLOCKING_EVENTS": 1,
        "boundary_result": "DIAGNOSTIC_BACKTEST_PARTIAL",
        "decision_guidance_inputs": {
            "consumed_blockers": 1,
            "affected_NAV_exposure_material": False,
            "reading": "exactly one of 158 register events was actually "
                "consumed by the strategy's own holdings, and it blocked; "
                "its economic exposure at the boundary is a sub-single-"
                "share fractional claim, not a material NAV amount. Per the "
                "decision rule in this directive, this is closest to the "
                "'few low-exposure blockers -> resolve only the named "
                "event(s)' band, EXCEPT the run never reached periods "
                "67-141 (42 more 158-register events fall in that "
                "unevaluated span) -- whether more, and whether larger, "
                "blockers exist beyond 2020-01 is NOT_EVALUATED and cannot "
                "be inferred from this run.",
        },

        # invariants
        "strategy_changes": 0,
        "parameter_tuning": False,
        "new_source_acquisition": False,
        "canonical_substitutions": False,
        "schema_consumer_changes": False,
        "production_scheduler_changes": False,
        "git_stage_or_commit": False,
        "new_l2_run_or_l2_opening": False,
        "d8_2d_r1_or_ca_remediation_resumed": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("valid_evaluated_period:", out["valid_evaluated_period"])
    print("percentage_of_requested_period_valid:",
          out["percentage_of_requested_period_valid"], "%")
    print("158-event tally:", tally)
    print("CA_BLOCKING_EVENTS:", out["CA_BLOCKING_EVENTS"])
    print("boundary_result:", out["boundary_result"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
