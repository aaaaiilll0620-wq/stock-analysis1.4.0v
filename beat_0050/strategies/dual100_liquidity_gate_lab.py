# -*- coding: utf-8 -*-
"""Preregistered liquidity-eligibility variants for the validated dual100 strategy.

Protocol: docs/預註冊_流動性資格門檻V1.md
This runner does not mutate the frozen dual100 implementation or deployment settings.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJ / "beat_0050"))
sys.path.insert(0, str(PROJ / "scripts"))

from high52_lab import (Panel, dual_confirm_mask, evaluate, met, turnover)  # noqa: E402
from honest_backtest import Engine, ERAS, SLIPPAGE_RT  # noqa: E402

BASELINE_FLOOR = 1_000_000.0
CANDIDATES = {"L20": 20_000_000.0, "L50": 50_000_000.0, "L100": 100_000_000.0}
TOP_PCT = 20
SEED = 20260810
BOOT_BLOCK = 12
BOOT_REPS = 5_000
OOS_START = "2010-01-01"
BENCH_SHARPE = 0.68
SLIP_GRID = (0.25, 0.40, 0.60, 0.80)
OUTDIR = PROJ / "beat_0050" / "results" / "liquidity_gate_v1"


def _percentile(P: Panel, valid: np.ndarray, values: np.ndarray) -> np.ndarray:
    ok = valid & np.isfinite(values)
    x = np.where(ok, values, -np.inf).astype(np.float64)
    order = np.argsort(-x, axis=1, kind="stable")
    rank = np.empty(order.shape, dtype=np.float64)
    np.put_along_axis(
        rank, order, np.arange(1, P.S + 1, dtype=np.float64)[None, :], axis=1
    )
    count = ok.sum(1).astype(float)[:, None]
    return np.where(ok, 100.0 * (1.0 - (rank - 1) / np.maximum(count, 1)), np.nan)


def _top_mask(P: Panel, valid: np.ndarray, score: np.ndarray) -> np.ndarray:
    ok = valid & np.isfinite(score)
    x = np.where(ok, score, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    rank = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(
        rank, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1
    )
    keep = np.maximum(1, (ok.sum(1) * TOP_PCT // 100).astype(int))
    return (rank <= keep[:, None]) & ok


def liquidity_mask(P: Panel, floor: float) -> np.ndarray:
    """Re-rank both dual100 legs inside a fixed ex-ante liquidity universe."""
    valid = P.HAS_RET & (P.ADV >= floor)
    coverage = float(np.isfinite(P.REAL_COMP[valid]).mean()) if valid.any() else 0.0
    if coverage < 1.0:
        raise RuntimeError(
            f"real_composite coverage at ADV>={floor:,.0f} is {coverage:.3%}; require 100%"
        )

    revenue = _percentile(P, valid, P.F["revenue_yoy"])
    value_ind = _percentile(P, valid, P.F["value_ind"])
    momentum = _percentile(P, valid, P.F["momentum"])
    high52 = _percentile(P, valid, P.F["high52_prox"])
    c2 = (value_ind + revenue + high52 + (100.0 - momentum)) / 4.0
    return _top_mask(P, valid, P.REAL_COMP.astype(np.float64)) & _top_mask(P, valid, c2)


def _constant_slip(P: Panel, value: float) -> np.ndarray:
    return np.full_like(P.RET, value, dtype=P.RET.dtype)


def _series(P: Panel, mask: np.ndarray, slip: float | None = None) -> np.ndarray:
    slip_panel = P.SLIP if slip is None else _constant_slip(P, slip)
    return evaluate(mask, P.RET, slip_panel)


def _jsonable(value):
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def verify_protocol(P: Panel, masks: dict[str, np.ndarray]) -> dict:
    old_l20 = dual_confirm_mask(P, "2000萬", top_pct=TOP_PCT, source="real")
    parity = bool(np.array_equal(old_l20, masks["L20"]))
    if not parity:
        raise RuntimeError("L20 mask differs from frozen dual_confirm_mask")
    coverage = {}
    for name, floor in CANDIDATES.items():
        valid = P.HAS_RET & (P.ADV >= floor)
        coverage[name] = float(np.isfinite(P.REAL_COMP[valid]).mean())
        if coverage[name] < 1.0:
            raise RuntimeError(f"{name} real_composite coverage is not 100%")
    return {"l20_mask_parity": parity, "coverage": coverage}


def matrix_engine_reconciliation(P: Panel, mask: np.ndarray, floor: float) -> dict:
    holdings = {
        P.month_s[t]: [str(P.stocks[j]) for j in np.where(mask[t])[0]]
        for t in range(P.T)
        if mask[t].any()
    }
    matrix = pd.Series(
        {P.month_s[t]: v for t, v in enumerate(_series(P, mask, SLIPPAGE_RT)) if np.isfinite(v)}
    )
    engine = Engine(adv_floor=floor)
    engine_monthly = engine.run(holdings)["monthly"].set_index("as_of")["ret"]
    common = matrix.index.intersection(engine_monthly.index)
    delta = (matrix.loc[common] - engine_monthly.loc[common]).abs()
    maximum = float(delta.max()) if len(delta) else float("nan")
    return {"months": len(common), "max_abs_pp": maximum, "pass": maximum < 0.01}


def _oos_selector(P: Panel, *series: np.ndarray) -> np.ndarray:
    valid = P.month_s >= OOS_START
    valid &= np.isfinite(P.bench)
    for values in series:
        valid &= np.isfinite(values)
    return valid


def block_bootstrap_lower(delta: np.ndarray, reps: int) -> dict:
    rng = np.random.default_rng(SEED)
    n = len(delta)
    if n < BOOT_BLOCK:
        raise RuntimeError(f"bootstrap sample too short: {n}")
    starts = rng.integers(0, n, size=(reps, int(np.ceil(n / BOOT_BLOCK))))
    offsets = np.arange(BOOT_BLOCK)
    indices = (starts[:, :, None] + offsets[None, None, :]) % n
    samples = delta[indices.reshape(reps, -1)[:, :n]]
    annualized = samples.mean(axis=1) * 12.0
    alpha = 0.05 / len(CANDIDATES)
    lower = float(np.quantile(annualized, alpha))
    return {
        "reps": reps,
        "block_months": BOOT_BLOCK,
        "bonferroni_alpha": alpha,
        "annual_mean_diff_pp": float(delta.mean() * 12.0),
        "lower_bound_pp": lower,
        "pass": lower > -2.0,
    }


def era_gate(P: Panel, net: np.ndarray, mask: np.ndarray, floor: float) -> dict:
    engine = Engine(adv_floor=floor)
    ew_monthly = engine.run(engine.universe_ew())["monthly"].set_index("as_of")["ret"]
    ew = np.full(P.T, np.nan)
    for t, month in enumerate(P.month_s):
        if month in ew_monthly.index:
            ew[t] = ew_monthly.loc[month]

    rows = []
    win_ew = 0
    win_0050 = 0
    for era, start, end in ERAS:
        select = (P.month_s >= start) & (P.month_s <= end)
        if select.sum() < 6:
            continue
        strategy_m = met(net[select])
        ew_m = met(ew[select])
        bench_m = met(P.bench[select])
        beats_ew = strategy_m.get("cagr", np.nan) > ew_m.get("cagr", np.nan)
        beats_0050 = strategy_m.get("sharpe", np.nan) > bench_m.get("sharpe", np.nan)
        win_ew += bool(beats_ew)
        win_0050 += bool(beats_0050)
        rows.append({
            "era": era,
            "strategy": strategy_m,
            "universe_ew": ew_m,
            "benchmark": bench_m,
            "beats_ew": beats_ew,
            "beats_0050": beats_0050,
        })

    counts = mask.sum(axis=1)
    counts = counts[counts > 0]
    avg_count = float(counts.mean()) if len(counts) else 0.0
    p10_count = float(np.quantile(counts, 0.10)) if len(counts) else 0.0
    passed = win_ew >= 4 and win_0050 >= 3 and avg_count >= 20 and p10_count >= 12
    return {
        "win_ew": win_ew,
        "win_0050": win_0050,
        "avg_holdings": avg_count,
        "p10_holdings": p10_count,
        "eras": rows,
        "pass": passed,
    }


def evaluate_candidate(
    P: Panel,
    name: str,
    floor: float,
    mask: np.ndarray,
    baseline_net: np.ndarray,
    reps: int,
) -> dict:
    net = _series(P, mask)
    recon = matrix_engine_reconciliation(P, mask, floor)
    counts = mask.sum(axis=1)
    # Every common strategy month must have at least one holding. Filtering
    # counts>0 before checking would make this gate tautological and silently
    # allow an empty portfolio month.
    h1 = recon["pass"] and bool(np.all(counts > 0))

    oos = _oos_selector(P, net, baseline_net)
    candidate_oos = met(net[oos])
    baseline_oos = met(baseline_net[oos])
    bench_oos = met(P.bench[oos])
    h2 = (
        candidate_oos.get("sharpe", -np.inf) > bench_oos.get("sharpe", np.inf)
        and candidate_oos.get("cagr", -np.inf) > bench_oos.get("cagr", np.inf)
        and candidate_oos.get("sharpe", -np.inf) >= baseline_oos.get("sharpe", np.inf) - 0.10
        and candidate_oos.get("cagr", -np.inf) >= baseline_oos.get("cagr", np.inf) - 2.0
    )

    h3_detail = block_bootstrap_lower(net[oos] - baseline_net[oos], reps)
    slip = {str(value): met(_series(P, mask, value)) for value in SLIP_GRID}
    h4 = slip["0.6"].get("sharpe", -np.inf) > BENCH_SHARPE
    h5_detail = era_gate(P, net, mask, floor)

    return {
        "floor": floor,
        "full_metrics": met(net),
        "turnover": turnover(mask),
        "h1": h1,
        "h1_reconciliation": recon,
        "h2": h2,
        "h2_candidate_oos": candidate_oos,
        "h2_baseline_oos": baseline_oos,
        "h2_benchmark_oos": bench_oos,
        "h3": h3_detail["pass"],
        "h3_detail": h3_detail,
        "h4": h4,
        "h4_grid": slip,
        "h5": h5_detail["pass"],
        "h5_detail": h5_detail,
        "pass_all": bool(h1 and h2 and h3_detail["pass"] and h4 and h5_detail["pass"]),
    }


def run(reps: int) -> dict:
    print("Building frozen real-score panel...", flush=True)
    P = Panel(realbody_floor=BASELINE_FLOOR)
    baseline_mask = liquidity_mask(P, BASELINE_FLOOR)
    masks = {name: liquidity_mask(P, floor) for name, floor in CANDIDATES.items()}
    verify = verify_protocol(P, masks)
    baseline_net = _series(P, baseline_mask)

    results = {}
    for name, floor in CANDIDATES.items():
        print(f"Evaluating {name} (ADV20 >= {floor:,.0f})...", flush=True)
        results[name] = evaluate_candidate(P, name, floor, masks[name], baseline_net, reps)

    winner = next(
        (name for name in ("L100", "L50", "L20") if results[name]["pass_all"]),
        None,
    )
    payload = {
        "protocol": "docs/預註冊_流動性資格門檻V1.md",
        "baseline_floor": BASELINE_FLOOR,
        "oos_start": OOS_START,
        "seed": SEED,
        "verify": verify,
        "baseline_full_metrics": met(baseline_net),
        "results": results,
        "winner": winner,
        "deployable": winner is not None,
    }
    return _jsonable(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-reps", type=int, default=BOOT_REPS)
    args = parser.parse_args()
    if args.bootstrap_reps < 1:
        raise SystemExit("--bootstrap-reps must be >= 1")
    payload = run(args.bootstrap_reps)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    output = OUTDIR / "result.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for name, result in payload["results"].items():
        rows.append({
            "candidate": name,
            "adv_floor": result["floor"],
            "h1": result["h1"],
            "h2": result["h2"],
            "h3": result["h3"],
            "h4": result["h4"],
            "h5": result["h5"],
            "pass_all": result["pass_all"],
            "oos_cagr": result["h2_candidate_oos"].get("cagr"),
            "oos_sharpe": result["h2_candidate_oos"].get("sharpe"),
            "avg_holdings": result["h5_detail"]["avg_holdings"],
            "p10_holdings": result["h5_detail"]["p10_holdings"],
        })
    pd.DataFrame(rows).to_csv(OUTDIR / "summary.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({"winner": payload["winner"], "results": rows}, ensure_ascii=False, indent=2))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
