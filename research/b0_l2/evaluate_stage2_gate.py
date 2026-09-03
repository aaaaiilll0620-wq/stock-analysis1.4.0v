# -*- coding: utf-8 -*-
"""Stage 2a: §9.3 row ③, and the §9.4 V-4 gate. NO OUTCOME IS WRITTEN.

The verdict is determined here and it is not written here, and the gap between
those two is deliberate.

§9.4's three conditions are decided by row ◆ and row ③ alone, so the gate can be
computed as soon as the benchmark exists. §9.7 says the reporting schema must be
output IN FULL at opening -- "缺一項即該次開封作廢" -- and rows ① and ② do not
exist yet. An outcome recorded against an incomplete report would void the very
opening it claims to conclude.

There is a second reason, and it is the one this project has already been burned
by. Losing to 0050 is row ◆ minus row ③: OPPORTUNITY COST. Whether the selection
layer has any skill is row ◆ minus row ①, a different question with a different
answer, and the prior retraction of "the selection layer has no alpha" turned on
exactly that confusion -- an equal-weight book starts ~5.77pp/year behind 0050
before any stock is picked, so a single benchmark reads a weighting difference as
an absence of skill. Writing NOT_SUPPORTED and stopping would re-make that
mistake with better provenance.

    B0_MATERIALIZE_LINEAGE=B1 python research/b0_l2/evaluate_stage2_gate.py \
        L2-688d001e44b5d517 --lineage B1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_l2_run_layout import resolve_run_dir                # noqa: E402
from core.b0_master_prereg import (                              # noqa: E402
    active_lineage, assert_declared_lineage, lineage_data_root,
    lineage_market_state_manifest, write_provenance_json,
)
from l2_ladder import build_row3, performance, v4_gate           # noqa: E402

LINEAGE = active_lineage()
OUT_ROOT = os.path.join(REPO, "artifacts", "l2_evaluation%s"
                        % ("" if LINEAGE == "FROZEN_B0" else "_" + LINEAGE.lower()))


def _load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--lineage", default="")
    a = ap.parse_args()
    assert_declared_lineage(a.lineage, LINEAGE)

    run_dir = resolve_run_dir(a.run_id, LINEAGE)
    stage1 = _load(os.path.join(OUT_ROOT, a.run_id, "evaluation_stage1.json"))
    if stage1["decision_state_hashes_matched"] != stage1["periods_rederived"]:
        raise SystemExit("abort: stage 1 did not verify every period")
    nav = _load(os.path.join(run_dir, "nav_series.json"))
    manifest = _load(lineage_market_state_manifest(LINEAGE))
    opening_cash = float(stage1["opening_cash"])

    marked = [{"as_of": r["as_of"], "period": r["period"],
               "wealth": r["port_value"]} for r in nav]
    strategy = performance(marked, opening_cash)
    row3 = build_row3(manifest, opening_cash, lineage_data_root(LINEAGE))
    gate = v4_gate(strategy, row3["performance"])

    record = {
        "record": "B0_L2_EVALUATION_STAGE2A_ROW3_AND_V4",
        "stage": "2a",
        "lineage": LINEAGE, "run_id": a.run_id,
        "baseline_seal_sha256": stage1["baseline_seal_sha256"],
        "spec_sha256": stage1["spec_sha256"],
        "commit_sha": stage1["commit_sha"],
        "rows_present": ["0_strategy", "3_benchmark_0050_buy_and_hold"],
        "rows_absent": ["1_eligible_universe_equal_weight",
                        "2_matched_random_selection_median_and_null_p"],
        "row_0_strategy": strategy,
        "row_3_benchmark": {k: v for k, v in row3.items() if k != "marked"},
        "ladder_differences_computable_now": {
            "opportunity_cost_row0_minus_row3":
                strategy["terminal_wealth"] - row3["performance"]["terminal_wealth"],
        },
        "ladder_differences_not_yet_computable": {
            "selection_ability_row0_minus_row1": None,
            "footprint_row0_minus_row2_with_null_p": None,
        },
        "v4": gate,
        "v4_verdict_is_determined": True,
        "outcome_written": False,
        "outcome_withheld_because": [
            "§9.7 requires the full reporting schema at opening; rows 1 and 2 "
            "are absent and an opening whose report omits a category is void",
            "row 0 minus row 3 is OPPORTUNITY COST, not evidence about the "
            "selection layer; that is row 0 minus row 1, and conflating them is "
            "the error a prior 'no alpha' finding was retracted for",
        ],
        "benchmark_gate1_module_defect": {
            "module": "core/b0_benchmark_gate1.py",
            "line": 41,
            "defect": "BENCHMARK_PANEL is pinned to data/b0/, so panel_present "
                      "reads Frozen B0's file for every lineage",
            "impact": "mislabels rather than misleads: the substantive check "
                      "reads the seal bindings and the manifest rows, which are "
                      "lineage-correct",
            "not_repaired_because": "the module is normative and B1's "
                                    "observation is spent; §1.4 closes the "
                                    "specification once a lineage has an "
                                    "outcome. Recorded, not repaired.",
        },
    }
    out = os.path.join(OUT_ROOT, a.run_id, "evaluation_stage2a.json")
    write_provenance_json(out, record)
    write_provenance_json(
        os.path.join(OUT_ROOT, a.run_id, "row3_marked_series.json"),
        row3["marked"])

    b = row3["performance"]
    print("=" * 78)
    print("§9.3 ladder (rows available) and §9.4 V-4   [%s / %s]"
          % (LINEAGE, a.run_id))
    print("=" * 78)
    print("%-24s %18s %18s" % ("", "row 0  strategy", "row 3  0050 B&H"))
    for k in ("terminal_wealth", "wealth_multiple", "cagr", "sharpe_0rf", "mdd"):
        print("%-24s %18.4f %18.4f" % (k, strategy[k], b[k]))
    print()
    for name, c in gate["conditions"].items():
        print("  %-46s %s" % (name, "PASS" if c["pass"] else "FAIL"))
    print("  %-46s %s" % ("ALL THREE (AND)",
                          "PASS" if gate["all_three_pass"] else "FAIL"))
    print()
    print("rows still absent : %s" % ", ".join(record["rows_absent"]))
    print("outcome written   : NO  (see outcome_withheld_because)")
    print("written           : %s" % os.path.relpath(out, REPO))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
