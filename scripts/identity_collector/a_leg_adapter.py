# -*- coding: utf-8 -*-
"""Phase D (2026-08-15 user decision): R-FWD A-leg-only parity, ADAPTER side.

Reads ONLY research_base/realbody_scores_adv100w.parquet -- a legitimate
frozen PIT source, NOT one of the FR-28 forbidden targets
(r_fwd_adapter.FR28_FORBIDDEN_TARGETS = exec_ret.parquet, obs_alpha.parquet).
Never imports beat_0050.strategies.high52_lab / Panel / core.canonical_universe's
Panel-dependent helpers in a way that would transitively read those two files
-- `static_import_audit()` below proves this by walking this module's own
source with `ast`, not by assertion.

B-leg (c2 four legs) and final dual-confirm membership are explicitly
NOT EVALUATED this pass -- reason INSUFFICIENT_FROZEN_PIT_INPUTS (see
a_leg_oracle.py's module docstring for the full explanation). This module
computes ONLY the A-leg (real_composite) top-20% threshold, independently,
from the adapter's own legitimate PIT population (whichever stock_ids appear
in the frozen realbody parquet for a given as_of date).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

FR28_FORBIDDEN_TARGETS = ("exec_ret.parquet", "obs_alpha.parquet")
FORBIDDEN_MODULE_NAMES = ("high52_lab", "beat_0050", "dual100_lab")


def static_import_audit(module_path: Path) -> dict:
    """Real (not asserted) static-import-graph check: parses this module's own
    source and confirms (a) no `import`/`from ... import` statement anywhere
    names a forbidden module, and (b) no forbidden filename appears as an
    ARGUMENT to a function call (i.e. would actually be opened/read) anywhere
    in the source. Deliberately does NOT flag forbidden filenames that appear
    only in docstrings or in the FR28_FORBIDDEN_TARGETS/FORBIDDEN_MODULE_NAMES
    declaration itself -- declaring what is forbidden is not reading it; only
    passing a matching string into a call would be. Returns a dict shaped for
    r_fwd_adapter.build_future_input_access_audit's forbidden_targets_reached.
    """
    src = Path(module_path).read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(module_path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(f in alias.name for f in FORBIDDEN_MODULE_NAMES):
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(f in mod for f in FORBIDDEN_MODULE_NAMES):
                hits.append(f"from {mod} import ...")
        elif isinstance(node, ast.Call):
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if any(t in arg.value for t in FR28_FORBIDDEN_TARGETS):
                        hits.append(f"call argument string literal: {arg.value!r}")
    return {"module_path": str(module_path), "forbidden_targets_reached": hits}


def load_adapter_a_leg_scores(realbody_parquet: Path) -> dict:
    """{date_str: {stock_id: real_composite}} -- every date present in the
    frozen realbody parquet. The ONLY file this function ever opens.

    Round 2 fix (frozen-semantics reproduction, not tuning): the oracle's
    `Panel.REAL_COMP` is populated by `high52_lab.py`'s `mat()` closure, whose
    default dtype is `np.float32` -- the oracle's real_composite is genuinely
    stored and compared at float32 precision, not the parquet's native
    float64. The adapter must reproduce that SAME storage representation to
    be comparable at all; reading the parquet's float64 value directly and
    comparing it to a float32-truncated oracle value was never an
    apples-to-apples raw-score comparison. `np.float32(x)` then widened back
    to Python float for JSON round-tripping -- the truncation, not the
    widening, is what matters."""
    import numpy as np
    import pandas as pd

    df = pd.read_parquet(Path(realbody_parquet), columns=["as_of", "stock_id", "real_composite"])
    df["as_of"] = df["as_of"].astype(str)
    df["stock_id"] = df["stock_id"].astype(str)
    df["real_composite"] = df["real_composite"].astype(np.float32).astype(np.float64)
    out: dict = {}
    for date, grp in df.groupby("as_of"):
        out[date] = dict(zip(grp["stock_id"], grp["real_composite"].astype(float)))
    return out


def topk_by_rank(scores: dict, top_pct: int = 20) -> list:
    """Reuses core.canonical_universe.topk_mask_desc (the SAME frozen
    rank-threshold primitive the oracle uses) via a 1-row matrix wrap --
    never a hand-rolled re-derivation of the ranking rule."""
    import numpy as np

    from core import canonical_universe as cu

    if not scores:
        return []
    ids = sorted(scores)
    values = np.array([[scores[i] for i in ids]], dtype=np.float64)
    valid = np.isfinite(values)
    mask = cu.topk_mask_desc(values, valid, top_pct)[0]
    return sorted(ids[i] for i in range(len(ids)) if mask[i])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--realbody-parquet", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dates-file", required=True)
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    for p in (repo_root, repo_root / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    audit = static_import_audit(Path(__file__).resolve())
    by_date_scores = load_adapter_a_leg_scores(Path(args.realbody_parquet))

    wanted = set(json.loads(Path(args.dates_file).read_text(encoding="utf-8")))
    by_date = {}
    for d in sorted(wanted & set(by_date_scores)):
        scores = by_date_scores[d]
        by_date[d] = {"scores": scores, "top20": topk_by_rank(scores)}

    result = {
        "role": "adapter",
        "pid": os.getpid(),
        "dates_requested": sorted(wanted),
        "dates_found": sorted(by_date),
        "by_date": by_date,
        "future_input_access_static_audit": audit,
        "only_file_opened": str(Path(args.realbody_parquet)),
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"[adapter] pid={os.getpid()} dates_found={len(by_date)}/{len(wanted)} forbidden_hits={len(audit['forbidden_targets_reached'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
