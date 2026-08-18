# -*- coding: utf-8 -*-
"""Take the B0 BASELINE SEAL — the pre-L2 seal (M-3 ruling 2026-08-18, C-47).

This assembles the manifest Master v1.14 requires BEFORE L2 may open, and takes
`seal(final_seal=True)` over it.

WHAT THIS DOES NOT DO, by construction:

  * it does not import or call `core.b0_route.run_decision`
  * it does not build a portfolio, read a return series, or rank a universe
  * it computes no CAGR, Sharpe, MDD, IC, win rate or any other performance
  * it produces no selection list, target, intent, receipt or NAV

`execution.status = NOT_EXECUTED_PRE_L2` and `output.status =
NOT_PRODUCED_PRE_L2` state that absence explicitly, and `seal()` REJECTS a
baseline that carries a decision date or an output hash. There is therefore no
path through this script that quietly starts L2.

Every value bound here is read from an existing frozen record — the freeze
registry, the D-1 price-source contract, the O-E market-state contracts, the
corporate-action provenance, and the frozen parameter registry itself. Nothing
is invented at seal time; a value this script cannot find is an abort, not a
default.

    python scripts/b0_baseline_seal.py            # take the seal
    python scripts/b0_baseline_seal.py --dry-run  # assemble + validate only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import CANONICAL_HASH_VERSION, canonical_sha256  # noqa: E402
from core.b0_master_prereg import (                                          # noqa: E402
    NORMATIVE_MODULES, normative_module_hashes, spec, specified_keys,
)
from core.b0_provenance import (                                             # noqa: E402
    CodeProvenance, ConfigProvenance, DatasetProvenance,
    DerivedArtifactProvenance, ExecutionProvenance, NOT_EXECUTED_PRE_L2,
    NOT_PRODUCED_PRE_L2, OutputProvenance, ProvenanceError, ProvenanceManifest,
    RepoIdentityGuard, SEAL_STAGE_BASELINE, SpecificationProvenance,
    file_sha256, seal,
)

FREEZE = os.path.join(REPO, "research", "b0_registry", "master_prereg_freeze.json")
PRICE_CONTRACT = os.path.join(REPO, "research", "d1_price_universe",
                              "price_source_contract.json")
MARKET_CONTRACTS = os.path.join(REPO, "research", "p1a_o_e_market_state",
                                "market_state_contracts.json")
CA_PROVENANCE = os.path.join(REPO, "research", "p0_v1b_stock_dividend",
                             "corporate_action_provenance.json")

OUT_DIR = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                       os.path.join(REPO, "artifacts"), "baseline_seal")

ROUTE_MODULE = "core.b0_route"


def _load(path: str, what: str) -> dict:
    if not os.path.isfile(path):
        raise SystemExit(f"abort: missing {what}: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _git(*args: str) -> str:
    proc = subprocess.run(("git",) + args, cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"abort: git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


# --- sections -----------------------------------------------------------------

def build_code() -> CodeProvenance:
    head = _git("rev-parse", "HEAD").strip()
    dirty = bool(_git("status", "--porcelain").strip())
    lock = os.path.join(REPO, "requirements.txt")
    return CodeProvenance(
        commit_sha=head, dirty=dirty, dirty_diff_sha256=None,
        dependency_lock_sha256=file_sha256(lock) if os.path.isfile(lock) else None,
        normative_module_sha256=normative_module_hashes())


def build_config() -> ConfigProvenance:
    """F0-R1: the COMPLETE declaration registry, not a runtime subset."""
    return ConfigProvenance(
        canonical={k: spec(k) for k in specified_keys()},
        registered_overrides={})


def build_data() -> tuple[DatasetProvenance, ...]:
    datasets: list[DatasetProvenance] = []

    price = _load(PRICE_CONTRACT, "D-1 price source contract")["b21_dataset_provenance"]
    datasets.append(DatasetProvenance(**price))

    for c in _load(MARKET_CONTRACTS, "O-E market-state contracts")["contracts"]:
        datasets.append(DatasetProvenance(
            name=c["name"], content_sha256=c["content_sha256"],
            schema_sha256=c["schema_sha256"], date_min=c["date_min"],
            date_max=c["date_max"], importer_version=c["importer_version"]))

    if not datasets:
        raise SystemExit("abort: no dataset provenance found")
    return tuple(datasets)


def build_derived(freeze: dict) -> tuple[DerivedArtifactProvenance, ...]:
    """Each derived artefact with the upstream hashes it was built from."""
    ca = _load(CA_PROVENANCE, "corporate-action provenance")
    ca_upstream = tuple(sorted(ca["upstream_zips"].values()))
    status_upstream = tuple(sorted(freeze["upstream_security_status_zips"].values()))
    price_upstream = (_load(PRICE_CONTRACT, "D-1 price source contract")
                      ["b21_dataset_provenance"]["content_sha256"],)

    # Which upstream corpus each derived artefact actually descends from. An
    # artefact whose lineage is not stated here is not sealed: `derived`
    # validation rejects an empty `upstream_sha256`.
    LINEAGE = {
        "data/b0/corporate_actions_ledger.csv": ca_upstream,
        "data/b0/stock_dividend_pit.csv": ca_upstream,
        "data/b0/trading_calendar.csv": price_upstream,
        "data/b0/security_status.csv": status_upstream,
        "data/b0/price_universe_churn.csv": price_upstream,
        "data/b0/price_universe_audit.csv": price_upstream,
        "data/b0/price_universe_clusters.csv": price_upstream,
        "data/b0/price_2019plus_new.parquet": price_upstream,
        "data/b0/price_presence.parquet": price_upstream,
        "data/b0/s3b_guard_fixture.csv": status_upstream,
    }
    out = []
    for path, meta in freeze["derived_artefacts"].items():
        upstream = LINEAGE.get(path)
        if not upstream:
            raise SystemExit(
                f"abort: derived artefact {path} has no declared upstream lineage. "
                f"An artefact without its inputs is not reconstructible, and "
                f"guessing the lineage would be specification-by-code.")
        out.append(DerivedArtifactProvenance(
            name=path, content_sha256=meta["sha256"], upstream_sha256=upstream))
    return tuple(out)


def build_execution(datasets: tuple[DatasetProvenance, ...]) -> ExecutionProvenance:
    """Opening state + route identity. No decision is taken or implied."""
    # The opening state is fully determined by the frozen registry: B0 starts
    # the evaluation window holding nothing but C_ref in cash. This is read from
    # the specification, not produced by running anything.
    opening = {
        "as_of": spec("window_start"),
        "cash": spec("C_ref"),
        "shares": {},
        "pending_exit": {},
        "cash_dividend_receivable": 0.0,
        "stock_dividend_receivable": {},
    }
    return ExecutionProvenance.pre_l2_baseline(
        initial_state_sha256=canonical_sha256(opening),
        market_data_as_of={d.name: d.date_max for d in datasets},
        route_module=ROUTE_MODULE,
        route_version=CANONICAL_HASH_VERSION)


def build_l2_opening_protocol() -> dict:
    """Read from the frozen registry — the gate must predate the numbers."""
    return {
        "window_start": spec("window_start"),
        "window_end": spec("window_end"),
        "window_months": spec("window_months"),
        "first_eligible_decision_month": spec("first_eligible_decision_month"),
        "outcomes": list(spec("l2_outcomes")),
        "sharpe_metric_name": spec("sharpe_metric_name"),
        "openings_permitted": 1,
        "opening_requires_explicit_user_authorisation": True,
    }


def build_manifest() -> ProvenanceManifest:
    freeze = _load(FREEZE, "master preregistration freeze registry")
    datasets = build_data()
    return ProvenanceManifest(
        specification=SpecificationProvenance.from_frozen_master(freeze["version"]),
        code=build_code(),
        config=build_config(),
        data=datasets,
        derived=build_derived(freeze),
        execution=build_execution(datasets),
        output=OutputProvenance.pre_l2_baseline(),
        l2_opening_protocol=build_l2_opening_protocol(),
    )


# --- entry point --------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble and validate, but do not write the seal record")
    a = ap.parse_args()

    print("=" * 78)
    print("B0 BASELINE SEAL — pre-L2 (Master v1.14, C-47)")
    print("=" * 78)

    # Snapshot BEFORE any of the reads below, so the guard spans the whole
    # critical section rather than only its last instant.
    guard = RepoIdentityGuard.snapshot(repo_root=REPO)
    print(f"HEAD          : {guard.expected_head}")
    print(f"clean tree    : {guard.expected_clean}")
    if not guard.expected_clean:
        raise SystemExit("abort: working tree is dirty; a final seal may not be taken")

    m = build_manifest()
    assert m.stage == SEAL_STAGE_BASELINE, "assembled manifest is not a baseline"

    print(f"spec          : {m.specification.document} v{m.specification.version}")
    print(f"spec_sha256   : {m.specification.spec_sha256}")
    print(f"config keys   : {len(m.config.canonical)}  config_hash {m.config.config_sha256}")
    print(f"normative mods: {len(m.code.normative_module_sha256)} / {len(NORMATIVE_MODULES)}")
    print(f"datasets      : {len(m.data)}  -> {[d.name for d in m.data]}")
    print(f"derived       : {len(m.derived)}")
    print(f"opening state : {m.execution.initial_state_sha256}")
    print(f"route         : {m.execution.route_module} @ {m.execution.route_version}")
    print(f"execution     : {m.execution.status}")
    print(f"output        : {m.output.status}")

    seal_hash = seal(m, final_seal=True, guard=guard)
    print()
    print(f"BASELINE SEAL : {seal_hash}")
    print(f"sealed inputs : {m.sealed_input_sha256}")

    if a.dry_run:
        print("\n--dry-run: seal validated, record NOT written")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    record = {
        "seal": "B0_BASELINE_SEAL",
        "stage": m.stage,
        "baseline_seal_sha256": seal_hash,
        "sealed_input_sha256": m.sealed_input_sha256,
        "canonical_hash_version": m.canonical_hash_version,
        "taken_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "commit_sha": m.code.commit_sha,
        "clean_tree": not m.code.dirty,
        "specification": {"document": m.specification.document,
                          "version": m.specification.version,
                          "spec_sha256": m.specification.spec_sha256},
        "config_hash": m.config.config_sha256,
        "config_key_count": len(m.config.canonical),
        "normative_module_sha256": dict(m.code.normative_module_sha256),
        "datasets": [d.__dict__ for d in m.data],
        "derived": [{"name": d.name, "content_sha256": d.content_sha256,
                     "upstream_sha256": list(d.upstream_sha256)} for d in m.derived],
        "execution": {"status": m.execution.status,
                      "initial_state_sha256": m.execution.initial_state_sha256,
                      "market_data_as_of": dict(m.execution.market_data_as_of),
                      "route_module": m.execution.route_module,
                      "route_version": m.execution.route_version,
                      "decision_date": None},
        "output": {"status": m.output.status, "artifacts": {}},
        "l2_opening_protocol": m.l2_opening_protocol,
        "l2_opened": False,
        "performance_computed": False,
        "selection_computed": False,
        "note": ("Pre-L2 baseline. No B0 decision route was run; no selection, "
                 "portfolio, NAV or performance quantity exists at this seal."),
    }
    out = os.path.join(OUT_DIR, "b0_baseline_seal.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"written       : {out}")
    print(f"record sha256 : {file_sha256(out)}")
    print("\nL2 NOT opened. Opening L2 requires explicit user authorisation.")


if __name__ == "__main__":
    main()
