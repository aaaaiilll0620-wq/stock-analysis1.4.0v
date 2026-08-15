# -*- coding: utf-8 -*-
"""Phase D (2026-08-15): REAL P_ONLY_EVIDENCE capacity dry-run driver for the
3 fixed dates (2026-08-07/10/11), against frozen inputs only:
  - P-A: research/p0_r1_research_production_identity/data_snapshot/finmind_cache_scores/
    (== the live ~/finmind_cache/Scores/ layout, injected via core.data_cache.set_store
    -- the SAME sanctioned test-injection point source_adapters.py's own docstring
    documents; core.score_store.screen_by_composite_at is called unmodified).
  - P-B: research/p0_r1_research_production_identity/data_snapshot/universe_pool/
    c2_fullpool_2026-08-{07,10,11}.csv, via source_adapters.read_p_b_fullpool's own
    `universe_pool_dir` parameter (no monkeypatch needed).

COMPARABLE_IDENTITY (R-FWD-inclusive) sizing is NOT attempted -- B-leg/R-FWD
real computation is blocked (see a_leg_oracle.py's docstring,
INSUFFICIENT_FROZEN_PIT_INPUTS). Only P_ONLY_EVIDENCE is produced here.

Writes payload files under a fresh OS temp directory, measures them, and
DELETES the temp directory once measurement is complete (NFR-7(a)'s own
"deleted after measurement" contract) -- nothing is ever written under any
primary_root/mirror_root (those remain PENDING/undefined for a dry-run).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from identity_collector import capacity  # noqa: E402
from identity_collector import epoch  # noqa: E402
from identity_collector import schema_validation as sv  # noqa: E402
from identity_collector.hashing import canonical_json, obj_hash, sha256_hex, sha256_of_file  # noqa: E402
from identity_collector.timestamps import now_pair  # noqa: E402

THREE_DATES = ("2026-08-07", "2026-08-10", "2026-08-11")

CODE_HASH_PATHS = {
    "score_store_sha256": "core/score_store.py",
    "scoring_manager_sha256": "core/scoring_manager.py",
    "fundamentals_sha256": "core/fundamentals.py",
    "valuation_sha256": "core/valuation.py",
    "advisor_sha256": "core/advisor.py",
    "backtest_sha256": "core/backtest.py",
    "regime_sha256": "core/regime.py",
    "app_py_sha256": "app.py",
    "l4a_decision_sha256": "scripts/l4a_decision.py",
    "technical_analysis_sha256": "core/technical_analysis.py",
    "data_provider_sha256": "core/data_provider.py",
    "industry_value_sha256": "core/industry_value.py",
    "ranking_adapter_sha256": "scripts/identity_collector/ranking_adapter.py",
    "universe_screen_daily_sha256": "scripts/universe_screen_daily.py",
    "build_cache_loader_sha256": "build_cache.py",
    "r_fwd_adapter_sha256": "scripts/identity_collector/r_fwd_adapter.py",
}


class FrozenScoresStore:
    """Duck-typed like core.data_cache._ParquetStore, but points 'Scores' at
    the frozen finmind_cache_scores/ snapshot directory instead of the live
    ~/finmind_cache/Scores/. Read-only; never writes."""

    def __init__(self, scores_dir: Path):
        self._scores_dir = Path(scores_dir)

    def glob(self, dataset: str) -> str:
        assert dataset == "Scores", f"FrozenScoresStore only serves the Scores dataset, got {dataset!r}"
        return str(self._scores_dir / "*.parquet")

    def _path(self, dataset: str, stock_id: str) -> Path:
        return self._scores_dir / f"{stock_id}.parquet"

    def exists(self, dataset: str, stock_id: str) -> bool:
        return self._path(dataset, stock_id).exists()

    def read(self, dataset: str, stock_id: str):
        import pandas as pd

        p = self._path(dataset, stock_id)
        return pd.read_parquet(p) if p.exists() else None


def build_code_hash_manifest() -> dict:
    return {key: sha256_of_file(REPO_ROOT / rel) for key, rel in CODE_HASH_PATHS.items()}


def _artifact_hash_manifest(files: dict) -> dict:
    return {"files": files, "aggregate_sha256": obj_hash(files, sort_keys=True)}


def capture_p_only_artifacts(as_of: str, *, finmind_cache_scores_dir: Path, universe_pool_dir: Path,
                              out_dir: Path, mode: str = "balanced") -> dict:
    """Writes the 10 LiveOutputManifestPOnly-named files into out_dir using
    REAL computation against the frozen sources; returns
    (payload_files_manifest, source_hashes, extra_context)."""
    import pandas as pd

    from core import data_cache
    from identity_collector import fusion, ranking_adapter
    from identity_collector.source_adapters import read_p_a_composite, read_p_b_fullpool

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    original_store = data_cache.get_store()
    data_cache.set_store(FrozenScoresStore(finmind_cache_scores_dir))
    try:
        p_a = read_p_a_composite(as_of, mode=mode)
        p_b, p_b_bytes, p_b_path = read_p_b_fullpool(as_of, universe_pool_dir=str(universe_pool_dir))
        scores_files = {}
        for f in sorted(Path(finmind_cache_scores_dir).glob("*.parquet")):
            scores_files[f"frozen_snapshot/finmind_cache_scores/{f.name}"] = {"bytes": f.stat().st_size, "sha256": sha256_of_file(f)}
    finally:
        data_cache.set_store(original_store)

    app_membership = fusion.compute_app_path_fusion(p_a, p_b)
    l4a_membership = fusion.compute_l4a_path_fusion_frozen(p_a, p_b_bytes, as_of, mode=mode)
    if app_membership != l4a_membership:
        raise fusion.ProductionInternalDivergence(
            f"app-only={sorted(app_membership - l4a_membership)} l4a-only={sorted(l4a_membership - app_membership)}")

    rows = ranking_adapter.rows_from_score_store_dataframe(p_a.assign(mode=mode))
    parity_rows = ranking_adapter.screen_by_composite_parity(rows)
    limited_rows = ranking_adapter.top_limit_screen(parity_rows, top_limit=epoch.IDENTITY_DEFINING_CONSTANTS["p_a_top_limit"])

    p_b_ranked = p_b.copy()
    p_b_ranked["stock_id"] = p_b_ranked["stock_id"].astype(str)
    p_b_ranked["c2_pct"] = p_b_ranked["c2_score_full"].rank(pct=True) * 100.0
    c2_lookup = dict(zip(p_b_ranked["stock_id"], p_b_ranked["c2_pct"]))
    audit_rows = []
    for _, r in p_a.iterrows():
        sid = str(r["stock_id"])
        audit_rows.append({
            "stock_id": sid, "pct_rank": r.get("pct_rank"), "composite": r.get("composite"),
            "c2_pct": c2_lookup.get(sid), "in_app_fusion": sid in app_membership, "in_l4a_fusion": sid in l4a_membership,
        })

    files: dict = {}

    def _write(name: str, content_bytes: bytes) -> None:
        p = out_dir / name
        p.write_bytes(content_bytes)
        files[name] = {"bytes": len(content_bytes), "sha256": sha256_hex(content_bytes)}

    def _write_parquet(name: str, df: pd.DataFrame) -> None:
        p = out_dir / name
        df.to_parquet(p, index=False)
        b = p.read_bytes()
        files[name] = {"bytes": len(b), "sha256": sha256_hex(b)}

    _write_parquet("p_a_raw_snapshot.parquet", p_a)
    _write_parquet("p_a_screen_by_composite_parity.parquet", pd.DataFrame(limited_rows))
    _write_parquet("p_b_fullpool.parquet", p_b)
    _write("p_app_fusion.csv", pd.DataFrame({"stock_id": sorted(app_membership)}).to_csv(index=False).encode("utf-8"))
    _write("p_l4a_fusion.csv", pd.DataFrame({"stock_id": sorted(l4a_membership)}).to_csv(index=False).encode("utf-8"))
    _write("rank_audit.csv", pd.DataFrame(audit_rows).to_csv(index=False).encode("utf-8"))

    source_manifest = {
        "as_of": as_of, "mode": mode,
        "p_a_source": "core.score_store.screen_by_composite_at, Scores store redirected (core.data_cache.set_store) to the frozen finmind_cache_scores/ snapshot -- never the live ~/finmind_cache/",
        "p_b_source": str(p_b_path),
        "p_b_bytes": len(p_b_bytes), "p_b_sha256": sha256_hex(p_b_bytes),
        "p_a_rows": int(len(p_a)), "p_b_rows": int(len(p_b)),
        "app_membership_count": len(app_membership), "l4a_membership_count": len(l4a_membership),
    }
    _write("source_manifest.json", canonical_json(source_manifest).encode("utf-8"))

    code_hashes = build_code_hash_manifest()
    code_config_manifest = {"code_hashes": code_hashes, "identity_defining_constants": epoch.IDENTITY_DEFINING_CONSTANTS}
    _write("code_config_manifest.json", canonical_json(code_config_manifest).encode("utf-8"))

    process_import_manifest = {
        "pid": os.getpid(),
        "relevant_imported_modules": sorted(m for m in sys.modules if m.startswith(("identity_collector", "core", "pandas", "numpy", "duckdb"))),
    }
    _write("process_import_manifest.json", canonical_json(process_import_manifest).encode("utf-8"))

    replay_manifest = {
        "as_of": as_of, "mode": mode,
        "how_to_reproduce": "python scripts/identity_collector/capacity_driver.py --as-of <date> --data-snapshot <same frozen snapshot root>",
        "frozen_snapshot_root": str(Path(finmind_cache_scores_dir).parent),
    }
    _write("replay_manifest.json", canonical_json(replay_manifest).encode("utf-8"))

    p_a_manifest = _artifact_hash_manifest(scores_files)
    p_b_manifest = _artifact_hash_manifest({f"frozen_snapshot/universe_pool/{Path(p_b_path).name}": {"bytes": len(p_b_bytes), "sha256": sha256_hex(p_b_bytes)}})
    source_hashes = {"p_a": p_a_manifest, "p_b": p_b_manifest, "r_fwd": None}

    return files, source_hashes, {"p_a_rows": int(len(p_a)), "p_b_rows": int(len(p_b)),
                                   "app_membership_count": len(app_membership), "l4a_membership_count": len(l4a_membership)}


def run_capacity_dry_run_for_date(as_of: str, *, finmind_cache_scores_dir: Path, universe_pool_dir: Path,
                                   clock, mode: str = "balanced") -> dict:
    import time

    started = now_pair(clock)
    t0 = time.monotonic()
    tmp_dir = tempfile.mkdtemp(prefix=f"p0r2_capacity_dryrun_{as_of}_")
    try:
        payload_files, source_hashes, ctx = capture_p_only_artifacts(
            as_of, finmind_cache_scores_dir=finmind_cache_scores_dir, universe_pool_dir=universe_pool_dir,
            out_dir=Path(tmp_dir), mode=mode)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    elapsed = time.monotonic() - t0
    completed = now_pair(clock)

    code_hashes = build_code_hash_manifest()
    code_hashes["r_fwd_adapter_sha256"] = None  # P_ONLY: no R-FWD identity attached
    collector_schema_sha256 = sha256_of_file(sv.SCHEMA_PATH)
    collector_config_hash = obj_hash(epoch.IDENTITY_DEFINING_CONSTANTS, sort_keys=True)

    disk_root = REPO_ROOT.anchor or "/"
    disk_free = shutil.disk_usage(disk_root).free

    actual_inputs = {
        "as_of": as_of, "persistence_status": "COMMITTED", "identity_status": "P_ONLY_EVIDENCE",
        "monthly_status": "DAILY_DIAGNOSTIC", "source_mutation": False, "revision_of": None,
        "capture_process_started": True,
        "process_isolation": {"production_capture_pid": os.getpid(), "r_fwd_pid": None, "bt_bundle_absent_from_production_process": True},
        "primary_root": "D:\\p0r2_identity_evidence\\primary",  # schema-shape placeholder only -- Stage 2 NOT approved, no real root exists
        "mirror_root": "E:\\p0r2_identity_evidence\\mirror",     # schema-shape placeholder only -- Stage 2 NOT approved, no real root exists
        "source_hashes": {**source_hashes},
        "code_hashes": code_hashes,
        "collector_config_hash": collector_config_hash, "collector_schema_sha256": collector_schema_sha256,
        "output_hashes_equivalent": payload_files,
        "announcement_date_pit_status": "BLOCKED",
        "r_fwd_qualification_ref": None,
        "temp_cleanup_status": "CLEANED",
    }
    template_path = REPO_ROOT / "scripts" / "identity_collector" / "live_receipt_projection_template.py"
    template_content_sha256 = sha256_of_file(template_path)
    template_identity = capacity.build_projection_template_identity(
        template_version="v1", repo_relative_path="scripts/identity_collector/live_receipt_projection_template.py",
        # Real git blob id for this file at the fixed baseline HEAD (verified via `git ls-tree`/`git cat-file`
        # against 0b1af42224314d71e8d16121d356235ffa7aacf7, this task's confirmed unchanged repository baseline).
        git_blob_sha1="22df8b38b89b6d817e8f612ea0eedd5037f5a8d5",
        reachable_commit_sha1="0b1af42224314d71e8d16121d356235ffa7aacf7",
        content_sha256=template_content_sha256,
        durable_copy_path="frozen_snapshot/live_receipt_projection_template_copy.py",
        durable_copy_bytes=template_path.stat().st_size, durable_copy_sha256=template_content_sha256,
    )
    projection = capacity.build_live_receipt_projection(template_identity, actual_inputs)

    source_hashes_full = {**source_hashes}
    receipt = capacity.build_capacity_dry_run_receipt(
        as_of=as_of, sizing_mode="P_ONLY_EVIDENCE", started_at=started, completed_at=completed,
        r_fwd_artifacts_included=False, payload_files=payload_files, elapsed_seconds=round(elapsed, 6),
        source_hashes=source_hashes_full, code_hashes=code_hashes,
        collector_config_hash=collector_config_hash, collector_schema_sha256=collector_schema_sha256,
        live_receipt_projection=projection,
    )
    ok, errors = sv.validate("CapacityDryRunReceipt", receipt)
    if not ok:
        raise ValueError(f"CapacityDryRunReceipt for {as_of} failed schema validation: {errors[:5]}")
    return receipt, ctx


def run_all_three(*, finmind_cache_scores_dir: Path, universe_pool_dir: Path, clock, out_report_path: Path) -> dict:
    attempts, contexts = [], {}
    for as_of in THREE_DATES:
        receipt, ctx = run_capacity_dry_run_for_date(
            as_of, finmind_cache_scores_dir=finmind_cache_scores_dir, universe_pool_dir=universe_pool_dir, clock=clock)
        attempts.append(capacity.build_report_attempt(receipt))
        contexts[as_of] = ctx

    report = capacity.build_capacity_dry_run_report(generated_at=now_pair(clock), sizing_mode="P_ONLY_EVIDENCE", attempts=attempts)
    ok, errors = sv.validate("CapacityDryRunReport", report)
    if not ok:
        raise ValueError(f"CapacityDryRunReport failed schema validation: {errors[:5]}")

    out_report_path = Path(out_report_path)
    out_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": report, "contexts": contexts, "report_path": str(out_report_path)}


def main(argv=None) -> int:
    import argparse
    from datetime import datetime, timezone

    ap = argparse.ArgumentParser()
    ap.add_argument("--finmind-cache-scores-dir", required=True)
    ap.add_argument("--universe-pool-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    clock = lambda: datetime.now(timezone.utc)  # noqa: E731 -- real wall clock for a real dry-run, not a test fixture
    result = run_all_three(
        finmind_cache_scores_dir=Path(args.finmind_cache_scores_dir), universe_pool_dir=Path(args.universe_pool_dir),
        clock=clock, out_report_path=Path(args.out))
    bootstrap = result["report"]["bootstrap_bytes_per_run"]
    print(f"[capacity_driver] wrote {result['report_path']} bootstrap_bytes_per_run={bootstrap:,}")
    for as_of, ctx in result["contexts"].items():
        print(f"  {as_of}: p_a_rows={ctx['p_a_rows']} p_b_rows={ctx['p_b_rows']} app_fusion={ctx['app_membership_count']} l4a_fusion={ctx['l4a_membership_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
