# -*- coding: utf-8 -*-
"""Phase D (2026-08-15 user decision): R-FWD A-leg-only parity, ORACLE side.

Scope note: B-leg (c2: value_ind/revenue_yoy/high52_prox/momentum) and final
dual-confirm fusion membership are NOT EVALUATED this pass -- their PIT raw
inputs (HistoryBundle's price/per/revenue/income/balance/cashflow/chip/
shareholding datasets, per phase_b_design_freeze.md Sec.10) are not present in
the authorized frozen snapshot (research/p0_r1_research_production_identity/
data_snapshot/ + research/p0_u1_canonical_universe/canonical_universe_by_date/).
Reason code: INSUFFICIENT_FROZEN_PIT_INPUTS. See docs note in
a_leg_adapter.py for the adapter side of this same scope limit.

Oracle = beat_0050.strategies.high52_lab.Panel.REAL_COMP restricted to
Panel.tier_valid["100萬"], top-20% via core.canonical_universe.topk_mask_desc
-- the SAME frozen ranking primitive dual_confirm_mask's internal `topk()`
closure uses (canonical_universe.py's own docstring: extracted verbatim,
never reimplemented). The oracle legitimately reads obs_alpha.parquet /
exec_ret.parquet / the realbody panel -- those are the oracle's real, prereg
Sec.12-designated inputs. FR-28's prohibition on reading those two files
applies to the ADAPTER side only (a_leg_adapter.py), never to this oracle.

Runs as a standalone CLI so it can be launched as a genuinely separate OS
process from a_leg_adapter.py (FR-24 process isolation) -- see
a_leg_parity_runner.py, which spawns both as subprocesses.

Path redirection: `lab_paths.RESEARCH_BASE`/`OBS_ALPHA`/`EXEC_RET` and
`high52_lab.OBS_ALPHA`/`EXEC_RET`/`BENCH_TR` are hardcoded to the LIVE
`data/research_base/` / `beat_0050/data/benchmark/` paths (not parameterized
by either module). `build_panel_from_frozen` monkeypatches those module-level
attributes, in this throwaway subprocess only, to point at the frozen
snapshot instead -- no file on disk is touched, and high52_lab.py/
lab_paths.py are never edited.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def build_panel_from_frozen(research_base_dir: Path, benchmark_path: Path, realbody_floor: float = 1e6):
    repo_root = Path(__file__).resolve().parents[2]
    for p in (repo_root, repo_root / "scripts", repo_root / "beat_0050", repo_root / "beat_0050" / "strategies"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import lab_paths

    research_base_dir = Path(research_base_dir)
    lab_paths.RESEARCH_BASE = research_base_dir
    lab_paths.OBS_ALPHA = research_base_dir / "obs_alpha.parquet"
    lab_paths.EXEC_RET = research_base_dir / "exec_ret.parquet"

    import high52_lab

    high52_lab.OBS_ALPHA = research_base_dir / "obs_alpha.parquet"
    high52_lab.EXEC_RET = research_base_dir / "exec_ret.parquet"
    high52_lab.BENCH_TR = Path(benchmark_path)

    return high52_lab.Panel(realbody_floor=realbody_floor)


def oracle_a_leg_by_date(panel, tier: str = "100萬", top_pct: int = 20) -> dict:
    """{date_str: {"scores": {stock_id: real_composite}, "top20": [stock_id,...]}}
    for every month in the panel. `valid` = tier_valid[tier] & finite(real_composite)
    -- the same population dual_confirm_mask's A-leg uses internally."""
    import numpy as np

    from core import canonical_universe as cu

    composite = panel.REAL_COMP.astype(np.float64)
    valid = panel.tier_valid[tier] & np.isfinite(composite)
    top_mask = cu.topk_mask_desc(composite, valid, top_pct)
    out = {}
    for t, date in enumerate(panel.month_s):
        idx = np.where(valid[t])[0]
        scores = {str(panel.stocks[i]): float(composite[t, i]) for i in idx}
        top = [str(panel.stocks[i]) for i in np.where(top_mask[t])[0]]
        out[str(date)] = {"scores": scores, "top20": sorted(top)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--research-base", required=True)
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dates-file", required=True, help="JSON list of as_of date strings to include in output")
    ap.add_argument("--realbody-floor", type=float, default=1e6)
    args = ap.parse_args(argv)

    panel = build_panel_from_frozen(Path(args.research_base), Path(args.benchmark), args.realbody_floor)
    by_date = oracle_a_leg_by_date(panel)
    wanted = set(json.loads(Path(args.dates_file).read_text(encoding="utf-8")))
    filtered = {d: v for d, v in by_date.items() if d in wanted}
    result = {
        "role": "oracle",
        "pid": os.getpid(),
        "panel_months": panel.T,
        "panel_stocks": panel.S,
        "dates_requested": sorted(wanted),
        "dates_found": sorted(filtered),
        "by_date": filtered,
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"[oracle] pid={os.getpid()} panel_months={panel.T} dates_found={len(filtered)}/{len(wanted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
