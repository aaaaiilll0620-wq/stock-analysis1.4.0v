# -*- coding: utf-8 -*-
"""Phase D orchestrator: spawns a_leg_oracle.py and a_leg_adapter.py as two
genuinely separate OS processes, reads their JSON outputs, and produces the
A-leg-only parity result + a LIMITED process/future-input check. Never writes
under any primary/mirror evidence root; writes only to the path given via
--out (intended: research/p0_r2_identity_collector/).

Frozen-input-only: the two subprocess CLIs are given explicit frozen paths
(research_base dir, benchmark parquet, realbody parquet) -- this script never
resolves a live path itself.

Round 2 correction (per user 2026-08-15 review): Round 1 called
r_fwd_adapter.build_process_isolation_audit / build_future_input_access_audit
-- functions designed for a REAL FR-24/FR-28 qualification claim backed by a
genuine PROCESS_IMPORT_MANIFEST / FUTURE_INPUT_ACCESS_TRACE evidence artifact
-- with fabricated bytes=0/all-zero-SHA256 placeholder artifacts standing in
for evidence that was never actually written, and mislabeled the oracle
(a reference/research computation over the frozen snapshot) as
"production_capture_process" (a term that means something specific and
different in this design: the LIVE production process a real R-FWD run must
be isolated from). Both PASS-shaped results were misleading. This round
builds a separate, honestly-labeled, explicitly non-authoritative structure
instead -- no PASS/FAIL claim, no r_fwd_adapter audit-builder call, no
qualification record."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))


def run_a_leg_parity(*, research_base: Path, benchmark: Path, realbody_parquet: Path,
                      dates: list, python_exe: str = sys.executable) -> dict:
    from identity_collector import a_leg_parity

    scripts_dir = REPO_ROOT / "scripts"
    oracle_cli = scripts_dir / "identity_collector" / "a_leg_oracle.py"
    adapter_cli = scripts_dir / "identity_collector" / "a_leg_adapter.py"

    with tempfile.TemporaryDirectory(prefix="p0r2_a_leg_parity_") as tmp:
        tmp = Path(tmp)
        dates_file = tmp / "dates.json"
        dates_file.write_text(json.dumps(sorted(dates)), encoding="utf-8")
        oracle_out = tmp / "oracle_result.json"
        adapter_out = tmp / "adapter_result.json"

        oracle_proc = subprocess.run(
            [python_exe, str(oracle_cli), "--research-base", str(research_base),
             "--benchmark", str(benchmark), "--dates-file", str(dates_file), "--out", str(oracle_out)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        adapter_proc = subprocess.run(
            [python_exe, str(adapter_cli), "--realbody-parquet", str(realbody_parquet),
             "--dates-file", str(dates_file), "--out", str(adapter_out)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )

        if oracle_proc.returncode != 0:
            raise RuntimeError(f"oracle subprocess failed (rc={oracle_proc.returncode}):\n{oracle_proc.stdout}\n{oracle_proc.stderr}")
        if adapter_proc.returncode != 0:
            raise RuntimeError(f"adapter subprocess failed (rc={adapter_proc.returncode}):\n{adapter_proc.stdout}\n{adapter_proc.stderr}")

        oracle_result = json.loads(oracle_out.read_text(encoding="utf-8"))
        adapter_result = json.loads(adapter_out.read_text(encoding="utf-8"))

    oracle_pid, adapter_pid = oracle_result["pid"], adapter_result["pid"]

    # LIMITED, honestly-labeled process-separation check -- NOT a FR-24 audit
    # (no PROCESS_IMPORT_MANIFEST evidence artifact was written; "oracle" is
    # a reference/research computation, never called production_capture_process).
    process_separation_check = {
        "status": "LIMITED_A_LEG_PROCESS_SEPARATION_ONLY",
        "oracle_role": "reference computation over the frozen research snapshot (Panel/REAL_COMP/tier_valid) -- NOT production capture",
        "adapter_role": "R-FWD A-leg adapter (realbody parquet only)",
        "oracle_pid": oracle_pid, "adapter_pid": adapter_pid,
        "pids_distinct": oracle_pid != adapter_pid,
        "note": "Verifies only that the two subprocess.run() invocations ran as distinct OS processes. No PROCESS_IMPORT_MANIFEST artifact, no bt_bundle-absence evidence was captured or written. The full FR-24 process-isolation audit contract is NOT_EVALUATED this round.",
    }
    static_audit = adapter_result["future_input_access_static_audit"]
    future_input_check = {
        "status": "LIMITED_STATIC_CHECK_ONLY",
        "method": "STATIC_IMPORT_GRAPH (ast.walk over a_leg_adapter.py's own source, in-process, not a written evidence artifact)",
        "forbidden_targets_reached": static_audit["forbidden_targets_reached"],
        "only_file_opened": adapter_result.get("only_file_opened"),
        "note": "No FUTURE_INPUT_ACCESS_TRACE evidence artifact was written. The full FR-28 future-input-access audit contract is NOT_EVALUATED this round.",
    }

    parity = a_leg_parity.aggregate_a_leg_parity(oracle_result["by_date"], adapter_result["by_date"])

    return {
        "scope": "A_LEG_ONLY",
        "b_leg_status": "NOT_EVALUATED",
        "b_leg_reason_code": "INSUFFICIENT_FROZEN_PIT_INPUTS",
        "final_fusion_membership_status": "NOT_EVALUATED",
        "final_fusion_reason_code": "INSUFFICIENT_FROZEN_PIT_INPUTS",
        "full_fr24_fr28_audit_status": "NOT_EVALUATED",
        "qualification_status": "NOT_QUALIFIED_A_LEG_ONLY_SCOPE",
        "process_separation_check": process_separation_check,
        "future_input_static_check": future_input_check,
        "oracle": {"pid": oracle_pid, "panel_months": oracle_result.get("panel_months"), "panel_stocks": oracle_result.get("panel_stocks"),
                   "dates_found": len(oracle_result["dates_found"])},
        "adapter": {"pid": adapter_pid, "dates_found": len(adapter_result["dates_found"])},
        "a_leg_parity_result": parity,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--research-base", required=True)
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--realbody-parquet", required=True)
    ap.add_argument("--dates-file", required=True, help="JSON list of the 255 canonical as_of dates")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    dates = json.loads(Path(args.dates_file).read_text(encoding="utf-8"))
    result = run_a_leg_parity(
        research_base=Path(args.research_base), benchmark=Path(args.benchmark),
        realbody_parquet=Path(args.realbody_parquet), dates=dates,
    )
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    p = result["a_leg_parity_result"]
    print(f"[a_leg_parity_runner] months_tested={p['months_tested']} membership_status={p['membership_status']} "
          f"raw_score_max_abs_diff={p['raw_score_max_abs_diff']} within_tol_all={p['raw_score_within_tolerance_all_dates']} "
          f"same_population_set_months={p['population_diagnostics_summary']['same_population_set_months']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
