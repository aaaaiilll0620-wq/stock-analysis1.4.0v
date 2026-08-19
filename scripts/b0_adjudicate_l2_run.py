# -*- coding: utf-8 -*-
"""Post-run adjudication / closure record for a terminated L2 run.

The runner writes what it observed. Governance decides what it MEANS, and the
two can disagree — here they do. Run `L2-af1b4d90c29b3b5f` terminated with
`NOT EVALUABLE — CORPORATE ACTION RECONSTRUCTION BLOCK`, and the ruling of
2026-08-19 supersedes that with `RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE`
because the blocking event predates B0's holding interval by roughly 23 months.

The disagreement is the point, so this record is written ALONGSIDE the run and
mutates none of its artefacts. Every hash below is measured from the files at
the moment of adjudication, not transcribed.

    python scripts/b0_adjudicate_l2_run.py --run-id <id> --governed-outcome <name> \
        --ruling "<reference>" --reason "<one line>"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core.b0_l2_run_layout import (                                # noqa: E402
    attempted_opening_count, opening_claim_path, resolve_run_dir, run_state,
    sha256_of,
)
from core.b0_master_prereg import (                                # noqa: E402
    L2_OUTCOMES, append_provenance_record, effective_observation_count,
    read_registry,
)

LEDGER = os.path.join(REPO, "research", "b0_registry",
                      "l2_adjudication_ledger.jsonl")

RUN_FILES = ("opening_record.json", "execution_claim.json",
             "period_progress.jsonl", "failure_record.jsonl",
             "final_result.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--governed-outcome", required=True)
    ap.add_argument("--ruling", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.governed_outcome not in L2_OUTCOMES:
        raise SystemExit("abort: %r is not a frozen L2 outcome" % a.governed_outcome)
    for field, value in (("ruling", a.ruling), ("reason", a.reason)):
        if not value.strip():
            raise SystemExit("abort: --%s is required" % field)
        if "\n" in value or "\r" in value:
            raise SystemExit("abort: --%s must be a single line" % field)

    directory = resolve_run_dir(a.run_id)
    final = json.load(open(os.path.join(directory, "final_result.json"),
                           encoding="utf-8"))
    if final["run_id"] != a.run_id:
        raise SystemExit("abort: %s holds a terminal result for %r"
                         % (directory, final["run_id"]))
    state = run_state(a.run_id)
    if state != "TERMINAL":
        raise SystemExit(
            "abort: %s is %s, not TERMINAL. A run is adjudicated once it has "
            "reached a governed terminal state, not before." % (a.run_id, state))

    artefacts = {}
    for name in RUN_FILES:
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            continue
        sha, size = sha256_of(path)
        artefacts[name] = {"sha256": sha, "bytes": size,
                           "path": os.path.relpath(path, REPO).replace("\\", "/")}

    seal = final["baseline_seal_sha256"]
    claim_path = opening_claim_path(seal)
    claim_sha, _ = sha256_of(claim_path)
    claim = json.load(open(claim_path, encoding="utf-8"))

    rows = [r for r in read_registry()
            if json.loads(r["detail"] or "{}").get("run_id") == a.run_id]
    if len(rows) != 1:
        raise SystemExit("abort: expected exactly one registry row for %s, "
                         "found %d" % (a.run_id, len(rows)))

    record = {
        "record": "B0_L2_POST_RUN_ADJUDICATION",
        "adjudicated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ruling": a.ruling,
        "run_id": a.run_id,
        "baseline_seal_sha256": seal,
        "baseline_commit_sha": final["commit_sha"],
        "spec_sha256": final["spec_sha256"],
        "market_state_composed_sha256": final["market_state_composed_sha256"],
        "period1_full_input_sha256": final["period1_full_input_sha256"],
        "opening_claim_sha256": claim_sha,
        "opening_claim_path": os.path.relpath(claim_path, REPO).replace("\\", "/"),
        "opened_at": claim["opened_at"],
        "authorization": claim["authorization"],
        "run_artefact_sha256": artefacts,
        "raw_runner_outcome": final["formal_outcome"],
        "raw_runner_detail": final["detail"],
        "governed_outcome": a.governed_outcome,
        "governed_reason": a.reason,
        "registry_row_outcome": rows[0]["outcome"],
        "evaluated_periods": final["periods_executed"],
        "required_periods": final["periods_required"],
        "attempted_openings": attempted_opening_count(),
        "effective_observation_count": effective_observation_count(),
        "performance_computed": False,
        "v4_executed": False,
        "mutates_run_artefacts": False,
        "note": ("This record is written ALONGSIDE the run. It does not modify "
                 "final_result.json, failure_record.jsonl, period_progress.jsonl, "
                 "the opening record, the opening claim, the execution claim, or "
                 "the opening registry row. The raw runner classification and "
                 "the governed classification are both retained precisely so "
                 "that the disagreement between them stays visible."),
    }

    if a.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=1))
        print("\n--dry-run: nothing written")
        return 0

    append_provenance_record(LEDGER, record)
    sha, size = sha256_of(LEDGER)
    print("run_id                     : %s" % a.run_id)
    print("raw runner outcome         : %s" % final["formal_outcome"])
    print("governed outcome           : %s" % a.governed_outcome)
    print("evaluated periods          : %d / %d" % (final["periods_executed"],
                                                    final["periods_required"]))
    print("attempted_openings         : %d" % record["attempted_openings"])
    print("effective_observation_count: %d" % record["effective_observation_count"])
    print("adjudication ledger        : %s (%d bytes)"
          % (os.path.relpath(LEDGER, REPO), size))
    print("ledger sha256              : %s" % sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
