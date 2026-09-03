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
from core.b0_l2_run_layout import (                                 # noqa: E402
    attempted_opening_count, lineage_opening_claims_root, opening_claims,
)
from core.b0_master_prereg import (                                          # noqa: E402
    FROZEN_B0_LINEAGE, L2ReopeningUnreachable, NORMATIVE_MODULES,
    assert_l2_reopening_reachable, effective_observation_count,
    lineage_nonconsumption_path, lineage_registry_path, lineage_spec,
    normative_module_hashes, read_registry, spec, specified_keys,
)
from core.b0_provenance import (                                             # noqa: E402
    CodeProvenance, ConfigProvenance, DatasetProvenance,
    DerivedArtifactProvenance, ExecutionProvenance, NOT_EXECUTED_PRE_L2,
    NOT_PRODUCED_PRE_L2, OutputProvenance, ProvenanceError, ProvenanceManifest,
    RepoIdentityGuard, SEAL_STAGE_BASELINE, SpecificationProvenance,
    file_sha256, seal,
)

# --- lineage scoping ----------------------------------------------------------
# The SAME environment variable the materializer and the freeze-registry builder
# read. One variable for the whole build chain: three that must agree are three
# that eventually will not, and the failure would be a seal that bound one
# lineage's artefacts under another's name.
LINEAGE = os.environ.get("B0_MATERIALIZE_LINEAGE", FROZEN_B0_LINEAGE)
_SUFFIX = "" if LINEAGE == FROZEN_B0_LINEAGE else "_%s" % LINEAGE.lower()

FREEZE = os.path.join(REPO, "research", "b0_registry",
                      "master_prereg_freeze%s.json" % _SUFFIX)

# The data root this lineage's derived artefacts live under. The LINEAGE map in
# `build_derived` is keyed by artefact PATH, and those paths move with the
# lineage - a map still keyed on data/b0 would abort on every B1 artefact
# (which is what it did) rather than silently seal B0's.
DATA_ROOT = "data/b0" if LINEAGE == FROZEN_B0_LINEAGE else "data/%s" % LINEAGE.lower()
PRICE_CONTRACT = os.path.join(REPO, "research", "d1_price_universe",
                              "price_source_contract.json")
MARKET_CONTRACTS = os.path.join(REPO, "research", "p1a_o_e_market_state",
                                "market_state_contracts.json")
CA_PROVENANCE = os.path.join(REPO, "research", "p0_v1b_stock_dividend",
                             "corporate_action_provenance.json")

OUT_DIR = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                       os.path.join(REPO, "artifacts"),
                       "baseline_seal%s" % _SUFFIX)

FROZEN_B0_SEAL_DIR = os.path.join(REPO, "artifacts", "baseline_seal")


def assert_not_writing_into_frozen_b0_seals(path: str) -> None:
    """A non-B0 lineage may not write into Frozen B0's seal archive.

    The archive is append-only and content-addressed, so a foreign seal landing
    in it would not overwrite anything - it would do something worse, which is
    join B0's lineage ledger and be read later as one of B0's own seals.
    """
    if LINEAGE == FROZEN_B0_LINEAGE:
        return
    target = os.path.realpath(path)
    protected = os.path.realpath(FROZEN_B0_SEAL_DIR)
    if target == protected or target.startswith(protected + os.sep):
        raise SystemExit(
            "REFUSING TO WRITE: lineage %s resolved a seal path inside Frozen "
            "B0's seal archive (%s)." % (LINEAGE, target))

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


def _receipt(name: str) -> dict:
    return _load(os.path.join(REPO, "research", "b0_materializer",
                              "%s_receipt.json" % name),
                 "%s receipt" % name)


def _receipt_upstream(name: str, key: str) -> tuple[str, ...]:
    return tuple(sorted(s["sha256"] for s in _receipt(name)[key]))


def _valuation_upstream() -> tuple[str, ...]:
    out = set()
    for c in _receipt("valuation_panel")["contracts"]:
        out.update(c["upstream_sha256"].values())
    return tuple(sorted(out))


def _bonus_upstream() -> tuple[str, ...]:
    """C-51/R5: the upstream MANIFEST hash, not 1,383 individual payload hashes.

    The manifest is itself a hash over every payload identity, so binding it
    binds them; listing 1,383 hashes in a seal would make the seal unreadable
    without making it stronger.
    """
    r = _receipt("bonus_share_panel")
    return (r["upstream_manifest_sha256"],)


def _market_state_upstream() -> tuple[str, ...]:
    return tuple(sorted({
        _receipt(n)["content_sha256"] for n in
        ("financials_pit", "monthly_revenue_pit", "valuation_panel",
         "industry_pit", "price_panel", "bonus_share_panel")}))


def _benchmark_upstream() -> tuple:
    """The 145 raw TWSE monthly responses, from the panel's own receipt."""
    r = _load(os.path.join(REPO, "research", "b0_benchmark",
                           "benchmark_0050_panel_receipt.json"),
              "benchmark panel receipt")
    return tuple(sorted(r["upstream_raw_sha256"].values()))


def build_benchmark_block() -> dict:
    """B0.2 R8/R10 · everything gate 1 needs, bound into the seal itself.

    A gate-1 computation that has to go looking for a file after the run is a
    gate-1 computation whose inputs were never sealed. These are the bindings
    `core.b0_benchmark_gate1` checks for.
    """
    panel = _load(os.path.join(REPO, "research", "b0_benchmark",
                               "benchmark_0050_panel_receipt.json"),
                  "benchmark panel receipt")
    unit = _load(os.path.join(REPO, "research", "b0_benchmark",
                              "benchmark_0050_share_unit_events_receipt.json"),
                 "benchmark share-unit receipt")
    return {
        "security_id": "0050",
        "identity": "0050 buy-and-hold, dividend-inclusive",
        "evaluation_only": True,
        "benchmark_panel_content_sha256": panel["content_sha256"],
        "benchmark_panel_schema_sha256": panel["schema_sha256"],
        "benchmark_source_contract": {
            "authority": panel["source_authority"],
            "endpoint": panel["source_endpoint"],
            "traded_value_is_source_field": panel["traded_value_is_source_field"],
        },
        "benchmark_derivation_receipt":
            "research/b0_benchmark/benchmark_0050_panel_receipt.json",
        "benchmark_upstream_sha256": sorted(panel["upstream_raw_sha256"].values()),
        "benchmark_date_coverage": panel["coverage"],
        "benchmark_distributions_sha256": panel["distributions_sha256"],
        "benchmark_share_unit_events_sha256": unit["content_sha256"],
        "benchmark_share_unit_events_schema_sha256": unit["schema_sha256"],
        "benchmark_share_unit_derivation": unit["derivation"],
        "payment_date_classification": "OPTIONAL_NON_OUTCOME_AUDIT_FIELD",
    }


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
    # Local name shadows the module-level `LINEAGE`; this map is about
    # artefact ancestry, not about which lineage is being sealed.
    UPSTREAM_OF = {
        DATA_ROOT + "/corporate_actions_ledger.csv": ca_upstream,
        DATA_ROOT + "/stock_dividend_pit.csv": ca_upstream,
        DATA_ROOT + "/trading_calendar.csv": price_upstream,
        DATA_ROOT + "/security_status.csv": status_upstream,
        DATA_ROOT + "/price_universe_churn.csv": price_upstream,
        DATA_ROOT + "/price_universe_audit.csv": price_upstream,
        DATA_ROOT + "/price_universe_clusters.csv": price_upstream,
        DATA_ROOT + "/price_2019plus_new.parquet": price_upstream,
        DATA_ROOT + "/price_presence.parquet": price_upstream,
        DATA_ROOT + "/s3b_guard_fixture.csv": status_upstream,
        # The L2 sealed inputs. Each lineage is READ from that artefact's own
        # receipt rather than restated here: a hash typed twice is a hash that
        # can disagree with itself, and the receipt is what the builder actually
        # wrote.
        DATA_ROOT + "/financials_pit.parquet": _receipt_upstream(
            "financials_pit", "sources"),
        DATA_ROOT + "/monthly_revenue_pit.parquet": _receipt_upstream(
            "monthly_revenue_pit", "upstream_sources"),
        DATA_ROOT + "/industry_pit.parquet": _receipt_upstream(
            "industry_pit", "upstream_sources"),
        DATA_ROOT + "/valuation_panel.parquet": _valuation_upstream(),
        DATA_ROOT + "/price_panel.parquet": price_upstream,
        DATA_ROOT + "/bonus_share_panel.parquet": _bonus_upstream(),
        # Definition A. The manifest is the artefact that says all 141 exist;
        # its upstream is exactly the six sealed panels it was assembled from.
        DATA_ROOT + "/market_state_manifest.json": _market_state_upstream(),
        # B0.2 §13.4. Evaluation-only, and their lineage is read from the
        # benchmark receipts for the same reason as the L2 sealed inputs: a
        # hash typed twice is a hash that can disagree with itself.
        DATA_ROOT + "/benchmark_0050_panel.parquet": _benchmark_upstream(),
        DATA_ROOT + "/benchmark_0050_distributions.csv": _benchmark_upstream(),
        DATA_ROOT + "/benchmark_0050_share_unit_events.parquet": _benchmark_upstream(),
    }
    out = []
    for path, meta in freeze["derived_artefacts"].items():
        upstream = UPSTREAM_OF.get(path)
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
        "as_of": lineage_spec(LINEAGE, "window_start"),
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


_CLAIMS_ROOT = lineage_opening_claims_root(LINEAGE)
_REGISTRY = lineage_registry_path(LINEAGE)
_NONCONSUMPTION = lineage_nonconsumption_path(LINEAGE)


def build_l2_opening_protocol() -> dict:
    """Read from the frozen registry — the gate must predate the numbers."""
    return {
        "window_start": lineage_spec(LINEAGE, "window_start"),
        "window_end": lineage_spec(LINEAGE, "window_end"),
        "window_months": lineage_spec(LINEAGE, "window_months"),
        "first_eligible_decision_month": spec("first_eligible_decision_month"),
        "outcomes": list(spec("l2_outcomes")),
        "sharpe_metric_name": spec("sharpe_metric_name"),
        "openings_permitted": 1,
        "opening_requires_explicit_user_authorisation": True,
        # v1.22 R1/R2. `openings_permitted: 1` is a budget, so the baseline has
        # to say how much of it is spent -- and the answer is not simply "how
        # many rows are in the registry". One attempt is recorded and it did not
        # consume an observation, which is a distinction the seal must carry
        # rather than leave to be re-derived from prose later.
        # C-59/R3: attempted openings are derived from immutable OPENING
        # events, not from terminal registry rows. Counting rows meant an
        # opening whose process died was invisible to the very budget it spent.
        # C-72/R1 as a PER-LINEAGE budget. These four were global reads, which
        # for a second lineage is not a mislabel but a wrong answer: a B1 seal
        # would have recorded B0's two attempts, B0's two terminal rows, B0's
        # open baseline and B0's ONE CONSUMED OBSERVATION - and
        # `effective_observations_to_date: 1` against `openings_permitted: 1`
        # reads as a budget already spent. B1 has spent none.
        "lineage": LINEAGE,
        "opening_registry": os.path.relpath(_REGISTRY, REPO).replace("\\", "/"),
        "attempted_openings_recorded": attempted_opening_count(
            _CLAIMS_ROOT, include_legacy=(LINEAGE == FROZEN_B0_LINEAGE)),
        "terminal_registry_rows": len(read_registry(_REGISTRY)),
        "open_baselines": [c["baseline_seal_sha256"][:16]
                           for c in opening_claims(_CLAIMS_ROOT)],
        "effective_observations_to_date": effective_observation_count(
            _REGISTRY, _NONCONSUMPTION),
        "non_consuming_outcomes": list(spec("l2_non_consuming_outcomes")),
        "non_consumption_conditions": list(spec("l2_non_consumption_conditions")),
    }


def build_manifest() -> ProvenanceManifest:
    freeze = _load(FREEZE, "master preregistration freeze registry")
    datasets = build_data()
    return ProvenanceManifest(
        specification=SpecificationProvenance.from_frozen_master(
            freeze["version"], lineage=LINEAGE),
        code=build_code(),
        config=build_config(),
        data=datasets,
        derived=build_derived(freeze),
        execution=build_execution(datasets),
        output=OutputProvenance.pre_l2_baseline(),
        l2_opening_protocol=build_l2_opening_protocol(),
    )


# --- C-52/R1 · immutable, content-addressed seal retention --------------------

SEAL_ARCHIVE = os.path.join(OUT_DIR, "seals")
# Co-located with the immutable bodies it indexes, and deliberately NOT under
# version control. The ledger can only be written AFTER a seal hash exists, so
# a tracked ledger would dirty the tree every time a seal is taken and the
# commit that cleaned it would invalidate the commit_sha the seal just bound.
# The tracked copy under research/b0_registry/ is the historical snapshot of
# what the chain looked like at commit time.
SEAL_LINEAGE = os.path.join(OUT_DIR, "baseline_seal_lineage.jsonl")


class SealOverwrite(RuntimeError):
    """C-52/R1: a seal body is immutable. Overwriting one destroys evidence."""


def seal_archive_path(seal_hash: str) -> str:
    return os.path.join(SEAL_ARCHIVE, "%s.json" % seal_hash)


def write_immutable(record: dict, seal_hash: str) -> tuple[str, str]:
    """Write the seal body to its content-addressed path. Never overwrite.

    The path IS the identity, so a second seal with the same hash is the same
    seal and a different one cannot land on the same name. The convenience
    pointer at `b0_baseline_seal.json` is a copy; losing it costs nothing,
    whereas the archive is the evidence a later L2 run points back at.
    """
    assert_not_writing_into_frozen_b0_seals(SEAL_ARCHIVE)
    os.makedirs(SEAL_ARCHIVE, exist_ok=True)
    archive = seal_archive_path(seal_hash)
    if os.path.exists(archive):
        raise SealOverwrite(
            "C-52/R1: %s already exists. A baseline seal body is immutable; "
            "if this is the same seal there is nothing to write, and if it is "
            "a different one it must not claim this identity." % archive)
    body = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + chr(10)
    with open(archive, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(body)

    # R1: the payload hash must reproduce the identity the filename claims.
    reopened = json.load(open(archive, encoding="utf-8"))
    if reopened.get("baseline_seal_sha256") != seal_hash:
        raise SealOverwrite(
            "C-52/R1: %s does not reopen to the seal hash its name claims "
            "(%s)." % (archive, seal_hash))
    if os.path.basename(archive) != "%s.json" % reopened["baseline_seal_sha256"]:
        raise SealOverwrite(
            "C-52/R1: archival filename and payload identity disagree")

    pointer = os.path.join(OUT_DIR, "b0_baseline_seal.json")
    with open(pointer, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(body)
    return archive, pointer


def record_lineage(seal_hash: str, manifest) -> None:
    """Append-only supersession ledger. Predecessors are never rewritten."""
    entries = []
    if os.path.exists(SEAL_LINEAGE):
        with open(SEAL_LINEAGE, encoding="utf-8") as fh:
            entries = [json.loads(l) for l in fh if l.strip()]
    if any(e.get("baseline_seal_sha256") == seal_hash for e in entries):
        return
    prior = [e for e in entries if e.get("state") == "CURRENT"]
    for e in prior:
        e["state"] = "SUPERSEDED"
        e["superseded_by"] = seal_hash
    predecessor = None
    if prior:
        predecessor = (prior[-1].get("baseline_seal_sha256")
                       or prior[-1].get("historical_hash_prefix"))
    entries.append({
        "seq": len(entries) + 1,
        "baseline_seal_sha256": seal_hash,
        "master_version": manifest.specification.version,
        "commit_sha": manifest.code.commit_sha,
        "state": "CURRENT",
        "historical_hash_recorded": True,
        "canonical_body_available": True,
        "archive_path": os.path.relpath(seal_archive_path(seal_hash), REPO)
                        .replace("\\", "/"),
        "supersedes": predecessor,
        "l2_opened": False,
    })
    with open(SEAL_LINEAGE, "w", encoding="utf-8", newline=chr(10)) as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + chr(10))


# --- entry point --------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble and validate, but do not write the seal record")
    a = ap.parse_args()

    print("=" * 78)
    print("%s BASELINE SEAL — pre-L2 (Master v1.14, C-47)" % LINEAGE)
    print("=" * 78)
    print("lineage       : %s" % LINEAGE)
    print("freeze record : %s" % os.path.relpath(FREEZE, REPO))
    print("seal archive  : %s" % os.path.relpath(OUT_DIR, REPO))

    # C-72 / §9.6e-R5. A Baseline Seal exists to authorise an L2 opening
    # (§13.3). Frozen B0 has no opening left to authorise, so TAKING a new seal
    # for this lineage has no admissible consumer — and R2 condition 6 ("a new
    # Baseline Seal is taken") is exactly the door a new seal would look like it
    # was opening. Refused here rather than three steps later at the opener,
    # because a seal that gets taken is already a fact in the lineage ledger.
    #
    # `--dry-run` is NOT refused, and the asymmetry with `b0_open_l2.py` is the
    # whole point. This mode assembles and validates and writes nothing: it is a
    # read-only consistency audit over the frozen corpus, and it stays useful
    # precisely BECAUSE the window is closed. The opener's dry run is different
    # in kind — it prints a record asserting that an opening is available, and
    # that answer is wrong. Closing a reopening path does not license deleting
    # an audit that never opened anything.
    try:
        assert_l2_reopening_reachable(LINEAGE)
    except L2ReopeningUnreachable as exc:
        if not a.dry_run:
            raise SystemExit(
                "abort: %s\n"
                "Taking a new Baseline Seal cannot change this: condition 6 is "
                "not an entrance, and the seal would bind a window that is "
                "closed. `--dry-run` remains available as a read-only audit."
                % exc)
        print("NOTE (C-72 / Master 9.6e-R5): Frozen B0 L2 reopening is "
              "UNREACHABLE.")
        print("      %s" % exc)
        print("      --dry-run continues as a READ-ONLY audit: it validates "
              "the assembled")
        print("      seal and writes no seal record and no lineage entry. It "
              "is not, and")
        print("      may not be reported as, a seal that was taken.")
        print()

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
        "benchmark": build_benchmark_block(),
        "l2_opening_protocol": m.l2_opening_protocol,
        "l2_opened": False,
        "performance_computed": False,
        "selection_computed": False,
        "note": ("Pre-L2 baseline. No B0 decision route was run; no selection, "
                 "portfolio, NAV or performance quantity exists at this seal."),
    }
    # C-52/R1. The content-addressed path is the archival identity; the pointer
    # is a convenience copy. `write_immutable` aborts rather than overwrite, and
    # reopens what it wrote to check the body reproduces the name it was given.
    archive, pointer = write_immutable(record, seal_hash)
    record_lineage(seal_hash, m)
    print(f"archived      : {archive}")
    print(f"record sha256 : {file_sha256(archive)}")
    print(f"latest pointer: {pointer}  (convenience copy, NOT the identity)")
    print("\nL2 NOT opened. Opening L2 requires explicit user authorisation.")


if __name__ == "__main__":
    main()
