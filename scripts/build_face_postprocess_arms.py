# -*- coding: utf-8 -*-
"""Build the frozen C1/C3 arms from the accepted diagnostic panel.

This is a score-only post-processor.  It does not join returns, run an OOS
test, or touch a canonical realbody panel.

Frozen definitions:
  C1: remove regime multipliers, retain per-stock dynamic weights.
  C3: percentile-transform the five advisor buckets within each as_of, while
      retaining the V0 effective weights, regime multipliers, and overrides.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RB_DIR = ROOT / "data" / "research_base"
DIAG_PATH = RB_DIR / "diag" / "diag_scores_adv100w_diag.parquet"
ARM_DIR = RB_DIR / "arms"
ADV_FLOOR = 1e6
PREREG_FREEZE_COMMIT = "4164993"
BUILDER_VERSION = "postprocess-1.0"
FACES = ("f_fund", "f_val", "f_tech", "f_mom", "f_whale")
BUCKETS = ("b_fund", "b_val", "b_tech", "b_mom", "b_whale")
FACE_KEYS = {
    "f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
    "f_mom": "momentum", "f_whale": "whale",
}
KEYS = ["as_of", "stock_id"]


def _base_weights() -> dict[str, float]:
    from core.scoring_manager import ScoringManager
    return dict(ScoringManager.MODES["balanced"]["composite_weights"])


def _effective_weights(regime, dyn_on: bool, *, use_regime: bool) -> dict[str, float]:
    """Mirror advisor.advise() weight arithmetic without invoking advisor."""
    w = _base_weights()
    if use_regime and regime:
        from core.regime import regime_multipliers
        mult = regime_multipliers(regime)
        w = {k: float(v) * float(mult.get(k, 1.0)) for k, v in w.items()}
    if bool(dyn_on):
        cut = w["valuation"] * 0.6
        w["valuation"] -= cut
        w["momentum"] += cut * 0.6
        w["whale"] += cut * 0.4
    total = sum(max(0.0, float(v)) for v in w.values())
    if total <= 0:
        raise ValueError("有效權重總和 <= 0")
    return {k: max(0.0, float(v)) / total for k, v in w.items()}


def _weighted_score(row: pd.Series, *, use_regime: bool, percentile_buckets: dict[str, float] | None = None) -> float:
    w = _effective_weights(row["regime"], bool(row["dyn_weight"]), use_regime=use_regime)
    vals = percentile_buckets or {b: row[b] for b in BUCKETS}
    score = sum(float(vals[b]) * w[FACE_KEYS[f]] for f, b in zip(FACES, BUCKETS))
    return float(round(score, 2))


def _percentile_desc(values: pd.Series) -> pd.Series:
    """Use high52_lab's stable descending rank formula, preserving NaN."""
    x = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(x)
    safe = np.where(ok, x, -np.inf)
    order = np.argsort(-safe, kind="stable")
    ranks = np.empty(len(x), dtype=float)
    ranks[order] = np.arange(1, len(x) + 1, dtype=float)
    n_valid = int(ok.sum())
    out = np.full(len(x), np.nan, dtype=float)
    if n_valid:
        out[ok] = 100.0 * (1.0 - (ranks[ok] - 1.0) / n_valid)
    return pd.Series(out, index=values.index)


def _c3_buckets(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for bucket in BUCKETS:
        out[bucket] = df.groupby("as_of", sort=False, group_keys=False)[bucket].transform(_percentile_desc)
    return out


def _assert_diag_integrity(df: pd.DataFrame) -> None:
    missing = [c for c in KEYS + ["real_composite", "regime", "dyn_weight", *BUCKETS] if c not in df.columns]
    if missing:
        raise RuntimeError(f"診斷面板缺少必要欄位: {missing}")
    if df.duplicated(KEYS).any():
        raise RuntimeError("診斷面板 (as_of, stock_id) 不唯一")
    if df["score_error"].fillna("").astype(str).ne("").any():
        raise RuntimeError("診斷面板含 score_error,拒絕後處理")
    if df["real_composite"].isna().any():
        raise RuntimeError("診斷面板含 real_composite NaN")

    # The accepted diagnostic panel's independent arithmetic must still agree
    # before it is used as the source for any candidate arm.
    err = (pd.to_numeric(df["real_composite"], errors="coerce")
           - pd.to_numeric(df["composite_indep"], errors="coerce")).abs()
    if (err > 0.01).any():
        raise RuntimeError(f"V0 診斷面板獨立合成不一致: {int((err > 0.01).sum())} 列")


def build_arm(arm: str, df: pd.DataFrame) -> pd.DataFrame:
    if arm not in ("C1", "C3"):
        raise ValueError(f"只接受 C1/C3,收到 {arm!r}")
    out = df.copy()
    if arm == "C1":
        out["real_composite"] = [
            _weighted_score(row, use_regime=False) for _, row in out.iterrows()
        ]
    else:
        pct = _c3_buckets(out)
        out["real_composite"] = [
            _weighted_score(row, use_regime=True,
                            percentile_buckets={b: pct.at[idx, b] for b in BUCKETS})
            for idx, row in out.iterrows()
        ]
        for b in BUCKETS:
            out[f"{b}_pct"] = pct[b]

    out["v0_real_composite"] = df["real_composite"].to_numpy()
    out["arm"] = arm
    out["builder_version"] = BUILDER_VERSION
    out["prereg_freeze_commit"] = PREREG_FREEZE_COMMIT
    out["panel_source"] = DIAG_PATH.name
    out["code_commit"] = _git_commit()
    out["postprocess_only"] = True
    return out


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(ROOT), text=True).strip()
    except Exception:
        return "unknown"


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=("C1", "C3"))
    ap.add_argument("--diag", type=Path, default=DIAG_PATH)
    args = ap.parse_args()

    df = pd.read_parquet(args.diag)
    df["as_of"] = df["as_of"].astype(str)
    df["stock_id"] = df["stock_id"].astype(str)
    _assert_diag_integrity(df)
    out = build_arm(args.arm, df)
    if len(out) != len(df) or out.duplicated(KEYS).any():
        raise RuntimeError("候選輸出鍵集合不完整或不唯一")
    if out["real_composite"].isna().any():
        raise RuntimeError("候選輸出 real_composite 含 NaN")

    path = ARM_DIR / f"arm_{args.arm}_scores_adv{int(ADV_FLOOR / 1e4)}w_arm.parquet"
    _atomic_write(out, path)
    report = {
        "arm": args.arm,
        "source": str(args.diag),
        "produced": int(len(out)),
        "coverage": 1.0,
        "duplicate_keys": int(out.duplicated(KEYS).sum()),
        "v0_max_abs_diff": float((out["v0_real_composite"] - df["real_composite"]).abs().max()),
        "postprocess_only": True,
        "out": str(path),
    }
    path.with_name(path.stem + "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
