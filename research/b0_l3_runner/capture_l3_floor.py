"""Prepare an L3 floor capture from immutable run-scoped source snapshots.

The default operation is a no-publication diagnostic.  It copies mutable
landing surfaces into a private staging directory, builds and verifies the two
capture leaves, derives the floor and its two leg summaries, then removes the
staging tree.  It never creates a formal run, lineage, route seal or receipt.

Publication is deliberately not implemented here yet.  The prepared result is
the user of the contract: after it has exposed the real constraints, a narrow
ratified transaction may publish the already-defined evidence.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

from core.b0_canonical_hash import file_sha256  # noqa: E402
from core.b0_l3_lineage_capture import (  # noqa: E402
    CAPTURE_AUTHORITY, CONTRACT_VERSION, DIAGNOSTIC_EXPECTED_FLOOR,
    FLOOR_CAPTURE_REQUIRED_DATASETS, PURPOSE_CAPTURE,
    RATIFIED_INVENTORY_AUTHORITY, assert_floor_is_a_trading_session,
    assert_prices_are_on_calendar, derive_leg_summaries,
    floor_capture_code_closure_sha256, next_attempt_run_id,
)
from research.b0_l3.l3_readers import read_calendar, read_prices  # noqa: E402
from research.b0_materializer import build_flat_leaves, build_prices_leaf  # noqa: E402
from research.b0_materializer.l3_temporal_snapshot import (  # noqa: E402
    TEMPORAL_SNAPSHOT_CONTRACT_VERSION, sessions_through,
    snapshot_directory,
)
from research.b0_materializer.source_ownership_manifest import (  # noqa: E402
    AGGREGATE_FILENAME, LEAF_FILENAME, assemble_aggregate, load_leaf,
    verify_aggregate, write_aggregate, write_leaf,
)

EVIDENCE_CLASS = "UNSEALED_DIAGNOSTIC"


class FloorCapturePreparationError(RuntimeError):
    """The no-publication preparation could not establish its evidence."""


def _repo_state(repo_root: str) -> dict:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True,
        text=True, check=True).stdout.strip()
    tracked = subprocess.run(
        ["git", "diff", "--quiet"], cwd=repo_root).returncode == 0 and \
        subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_root).returncode == 0
    untracked = not bool(subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_root,
        capture_output=True, text=True, check=True).stdout.strip())
    return {"commit_sha": head, "tracked_clean": tracked,
            "untracked_clean": untracked}


def _quarantined_rows(pre_2019_dir: str,
                      boundary: str = "2019-01-01") -> int:
    import pandas as pd

    count = 0
    for name in sorted(os.listdir(pre_2019_dir)):
        if not name.lower().endswith(".parquet"):
            continue
        frame = pd.read_parquet(os.path.join(pre_2019_dir, name),
                                columns=["date"])
        dates = pd.to_datetime(frame["date"], errors="coerce").dt.strftime(
            "%Y-%m-%d")
        count += int((dates >= boundary).sum())
    return count


def prepare_floor_capture(*, prior_attempt_id: str, capture_date: str,
                          calendar_source: str, prices_2019_source: str,
                          prices_pre_2019_source: str, final_run_dir: str,
                          staging_root: str, repo_root: str = REPO) -> dict:
    """Run the full source/read/floor path without publishing formal evidence."""
    try:
        capture_date = dt.date.fromisoformat(capture_date).isoformat()
    except ValueError as exc:
        raise FloorCapturePreparationError(
            "capture_date must be a real ISO date") from exc
    if capture_date != dt.date.today().isoformat():
        raise FloorCapturePreparationError(
            "capture_date %s is not today's actual source-observation date %s"
            % (capture_date, dt.date.today().isoformat()))
    run_id = next_attempt_run_id(prior_attempt_id,
                                 capture_date=capture_date)
    before_repo = _repo_state(repo_root)
    observed_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    os.makedirs(staging_root, exist_ok=True)
    root = tempfile.mkdtemp(prefix=run_id + "-", dir=staging_root)
    inputs = os.path.join(root, "inputs")
    validation = os.path.join(root, "validation")
    os.makedirs(validation)
    try:
        cal_stage = os.path.join(inputs, "calendar")
        p19_stage = os.path.join(inputs, "prices_2019")
        pre_stage = os.path.join(inputs, "prices_pre2019")
        snapshots = {
            "calendar": snapshot_directory(
                calendar_source, cal_stage, extensions=(".parquet",),
                declared_subdirectories=build_flat_leaves.FLAT_FAMILIES[
                    "calendar"].get("declared_subdirectories", ())),
            "prices_2019": snapshot_directory(
                prices_2019_source, p19_stage,
                extensions=build_prices_leaf.ENUMERATED_EXTENSIONS),
            "prices_pre2019": snapshot_directory(
                prices_pre_2019_source, pre_stage, extensions=(".parquet",)),
        }
        validation_leaves = {
            "calendar": build_flat_leaves.build(
                "calendar", run_id, capture_date, landing_dir=cal_stage,
                observed_at=observed_at),
            "prices": build_prices_leaf.build(
                run_id, capture_date, landing_dir=p19_stage,
                pre_2019_dir=pre_stage, observed_at=observed_at),
        }
        for leaf in validation_leaves.values():
            write_leaf(validation, leaf)
        aggregate = assemble_aggregate(
            run_dir=validation, run_id=run_id, as_of=capture_date,
            purpose=PURPOSE_CAPTURE, capture_authority=CAPTURE_AUTHORITY,
            required=FLOOR_CAPTURE_REQUIRED_DATASETS)
        aggregate_payload, aggregate_raw = write_aggregate(validation, aggregate)
        verify_aggregate(validation)

        sessions = sessions_through(read_calendar(validation), capture_date)
        if not sessions:
            raise FloorCapturePreparationError(
                "calendar has no session through capture date")
        prices = read_prices(validation, "1900-01-01", capture_date)
        assert_prices_are_on_calendar(prices["date"], sessions)
        floor = str(prices["date"].min())
        assert_floor_is_a_trading_session(floor, sessions)
        price_leaf = load_leaf(os.path.join(
            validation, LEAF_FILENAME % "prices"))
        legs = derive_leg_summaries(
            price_leaf, prices,
            rows_dropped_by_quarantine=_quarantined_rows(pre_stage))

        final_inputs = os.path.join(os.path.abspath(final_run_dir), "inputs")
        planned_leaves = {
            "calendar": build_flat_leaves.build(
                "calendar", run_id, capture_date, landing_dir=cal_stage,
                declared_landing_dir=os.path.join(final_inputs, "calendar"),
                observed_at=observed_at),
            "prices": build_prices_leaf.build(
                run_id, capture_date, landing_dir=p19_stage,
                pre_2019_dir=pre_stage,
                declared_landing_dir=os.path.join(final_inputs, "prices_2019"),
                declared_pre_2019_dir=os.path.join(
                    final_inputs, "prices_pre2019"), observed_at=observed_at),
        }
        if any(root.replace("\\", "/") in json.dumps(leaf)
               for leaf in planned_leaves.values()):
            raise FloorCapturePreparationError(
                "planned manifest retains a private staging path")
        planned_dir = os.path.join(root, "planned")
        os.makedirs(planned_dir)
        planned_leaf_receipts = {
            name: write_leaf(planned_dir, leaf)
            for name, leaf in planned_leaves.items()
        }
        planned_aggregate = assemble_aggregate(
            run_dir=planned_dir, run_id=run_id, as_of=capture_date,
            purpose=PURPOSE_CAPTURE, capture_authority=CAPTURE_AUTHORITY,
            required=FLOOR_CAPTURE_REQUIRED_DATASETS)
        planned_aggregate_payload, _ = write_aggregate(
            planned_dir, planned_aggregate)
        after_repo = _repo_state(repo_root)
        if after_repo != before_repo:
            raise FloorCapturePreparationError(
                "repository identity changed during capture preparation")
        freeze_path = os.path.join(
            repo_root, "research", "b0_registry", "master_prereg_freeze.json")
        with open(freeze_path, encoding="utf-8") as fh:
            freeze = json.load(fh)
        basis_preview = {
            "contract_version": CONTRACT_VERSION,
            "capture_authority": CAPTURE_AUTHORITY,
            "capture_run_id": run_id,
            "as_of": capture_date,
            "lineage_price_floor": floor,
            "price_leaf_payload_sha256": planned_leaf_receipts["prices"][
                "payload_sha256"],
            "aggregate_manifest_payload_sha256": planned_aggregate_payload,
            "leg_summaries": list(legs),
            "master_version": str(freeze["version"]),
            "spec_sha256": str(freeze["spec_sha256"]),
            "master_prereg_freeze_sha256": file_sha256(freeze_path),
            "floor_capture_code_closure_sha256":
                floor_capture_code_closure_sha256(repo_root),
            "repo_commit_sha": before_repo["commit_sha"],
        }
        return {
            "evidence_class": EVIDENCE_CLASS,
            "formal_publication_performed": False,
            "run_id": run_id,
            "capture_date": capture_date,
            "decision_date": None,
            "execution_date": None,
            "lineage_price_floor": floor,
            "diagnostic_expected_floor": DIAGNOSTIC_EXPECTED_FLOOR,
            "expected_floor_matched": floor == DIAGNOSTIC_EXPECTED_FLOOR,
            "source_max_session": max(sessions),
            "temporal_contract_version": TEMPORAL_SNAPSHOT_CONTRACT_VERSION,
            "snapshots": snapshots,
            "planned_leaf_payload_sha256": {
                name: receipt["payload_sha256"]
                for name, receipt in planned_leaf_receipts.items()},
            "planned_aggregate_payload_sha256": planned_aggregate_payload,
            "validation_aggregate_payload_sha256": aggregate_payload,
            "validation_aggregate_raw_sha256": aggregate_raw,
            "basis_preview": basis_preview,
            "repo_state": before_repo,
            "required_datasets_provenance": RATIFIED_INVENTORY_AUTHORITY,
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


__all__ = ["EVIDENCE_CLASS", "FloorCapturePreparationError",
           "prepare_floor_capture"]
