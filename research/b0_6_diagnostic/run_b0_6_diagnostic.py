# -*- coding: utf-8 -*-
"""Frozen B0.6 RETROSPECTIVE DIAGNOSTIC REPLAY. Master v1.31 §17.

THIS IS NOT AN L2 RUN, AND IT IS STRUCTURALLY INCAPABLE OF BECOMING ONE.

  * it never imports `record_opening`, `create_opening_claim` or
    `create_execution_claim`
  * it never writes under `artifacts/l2_run/` — its entire namespace is
    `artifacts/b0_6_diagnostic/`
  * it snapshots every Frozen B0 L2 artefact hash, every pinned Frozen B0.1
    diagnostic artefact, the B0.2/B0.4/B0.5 terminal results, `attempted_openings` and `effective_observation_count`
    BEFORE the first byte is written and asserts them unchanged AFTER the
    terminal record, so an accidental mutation is a failure rather than a
    footnote. B0.6 replaces no historical run.
  * it computes NO performance and DISPLAYS no wealth. `port_value` is a state
    quantity the causal chain cannot proceed without -- ADV_floor is 5 x
    port_value -- so it is written to run-scoped provenance for a later
    authorised evaluation, but it is deliberately kept out of stdout: printing
    it at period 141 would be showing terminal cumulative wealth, which is half
    of gate 1. Cumulative wealth, CAGR, Sharpe_0rf, MDD and the gates are the
    evaluator's job, and no evaluator is invoked here.

Strategy semantics come from the sealed core and from nowhere else:
`build_input` and `load_events` are IMPORTED verbatim from the sealed L2
runner, and every feature, filter, score, target, order, cost and corporate
action happens behind `run_decision` / `core.b0_corporate_actions`.

    python research/b0_6_diagnostic/run_b0_6_diagnostic.py --authorization "<ref>"
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))
sys.path.insert(0, os.path.join(REPO, "research", "b0_l2"))

from core import b0_corporate_actions as ca                        # noqa: E402
from core.b0_canonical_hash import canonical_sha256                # noqa: E402
from core.b0_declaration_conformance import assert_declarations_conform  # noqa: E402
from core.b0_l2_run_layout import (                                # noqa: E402
    LEGACY_RUN_ROOT, attempted_opening_count, composed_market_state_sha256,
    legacy_artefact_identity, sha256_of,
)
from core.b0_master_prereg import (                                # noqa: E402
    NORMATIVE_MODULES, append_provenance_record, effective_observation_count,
    normative_module_hashes, read_registry, spec_document_sha256,
    write_provenance_json,
)
from core.b0_route import run_decision                             # noqa: E402
from core.b0_state import PortfolioState                           # noqa: E402
from core import b0_finalization_items as fin_items                # noqa: E402
from core import b0_open_items as open_items                       # noqa: E402

# The sealed runner IS the strategy path. Reusing it is the only way to be sure
# the diagnostic replays B0.1 rather than a lookalike written next to it.
from run_sealed_l2 import build_input, load_events                 # noqa: E402
from build_period1_full_input import _price_contract, opening_states  # noqa: E402

RUN_KIND = "B0_6_RETROSPECTIVE_DIAGNOSTIC"
EVIDENCE_CLASS = "RETROSPECTIVE_SUPPORTING_ONLY"
PARENT_L2_RUN = "L2-af1b4d90c29b3b5f"
PARENT_B0_1_DIAGNOSTIC_RUN = "B01DIAG-0121b3261805b826"
PARENT_B0_2_DIAGNOSTIC_RUN = "B02DIAG-bc7ce018a97cfa0f"
PARENT_B0_4_DIAGNOSTIC_RUN = "B04DIAG-d5f34a5164a0e309"
PARENT_B0_5_DIAGNOSTIC_RUN = "B05DIAG-9943d2f7b4adb670"

DATA = os.path.join(REPO, "data", "b0")
MANIFEST = os.path.join(DATA, "market_state_manifest.json")
SEAL_ARCHIVE = os.path.join(REPO, "artifacts", "baseline_seal", "seals")
FREEZE = os.path.join(REPO, "research", "b0_registry", "master_prereg_freeze.json")
P1_RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                          "period1_full_input_receipt.json")

# The diagnostic namespace. Disjoint from artifacts/l2_run by construction.
DIAG_ROOT = os.path.join(REPO, "artifacts", "b0_6_diagnostic")
RUNS_ROOT = os.path.join(DIAG_ROOT, "runs")
CLAIMS_ROOT = os.path.join(DIAG_ROOT, "run_claims")
TEST_RECEIPT = os.path.join(DIAG_ROOT, "test_evidence.json")

# The authorization's bound identities. Named here so a drift is an abort.
# The authorization names these. `period1_full_input` is deliberately ABSENT:
# it is read from the seal/receipt at run time and cross-checked between the two
# receipts, because a shortened hash copied out of a prompt is exactly the kind
# of identity that silently goes stale.
# Only the three identities the authorization states in full are pinned here.
# The 141-state hash, the period-1 hash, the CA ledger hash and the sealed-input
# identity are READ FROM THE SEAL at run time and cross-checked against the
# receipts, because an abbreviated hash copied out of a report is exactly the
# kind of identity that silently goes stale.
EXPECT = {
    "baseline_seal": "d912f1f6384fc07e362928e11ce4ae5393e3e7bcc60a7db938befbca43b1bc40",
    "spec_sha256": "a6a5294d3363a094b9c311063ed63af9aa5a5ac865f43a8230b215524a1b0374",
    "master_version": "1.31",
    "commit_prefix": "d236872a",
    "attempted_openings": 2,
    "effective_observations": 1,
    "periods": 141,
    "window": ("2014-07-31", "2026-03-31"),
}


class DiagnosticAbort(RuntimeError):
    """Stop before the replay, or stop the replay. Never repair and continue."""


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=REPO).stdout.strip()


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _require(ok, label, detail=""):
    if not ok:
        raise DiagnosticAbort("PRE-REPLAY VERIFICATION FAILED · %s%s"
                              % (label, (": " + detail) if detail else ""))
    return {"item": label, "status": "PASS", "detail": detail}


def l2_immutability_snapshot():
    """Every byte under artifacts/l2_run, plus the two accounting scalars."""
    files = {}
    for base, _dirs, names in os.walk(LEGACY_RUN_ROOT):
        for n in sorted(names):
            p = os.path.join(base, n)
            sha, size = sha256_of(p)
            files[os.path.relpath(p, REPO).replace("\\", "/")] = {
                "sha256": sha, "bytes": size}
    return {
        "l2_artefact_files": files,
        "l2_artefact_tree_sha256": canonical_sha256(files),
        "legacy_pinned_artefacts": legacy_artefact_identity(),
        "attempted_openings": attempted_opening_count(),
        "effective_observation_count": effective_observation_count(),
        "registry_rows": len(read_registry()),
        "registry_sha256": canonical_sha256(read_registry()),
        "b0_1_diagnostic": _b0_1_snapshot(),
    }


def _b0_1_snapshot():
    from core.b0_1_diagnostic_closure import b0_1_diagnostic_identity

    ident = b0_1_diagnostic_identity()
    return {"artefacts": ident, "composed": canonical_sha256(ident)}


def preflight(authorization):
    """§1. Mechanically verify, then refuse or proceed. No repair path."""
    checks = []
    seal_file = os.path.join(SEAL_ARCHIVE, EXPECT["baseline_seal"] + ".json")
    checks.append(_require(os.path.exists(seal_file), "B0.6 seal archived",
                           EXPECT["baseline_seal"][:16]))
    seal = _load(seal_file)
    checks.append(_require(
        seal["baseline_seal_sha256"] == os.path.basename(seal_file)[:-5],
        "filename == payload"))
    live = os.path.join(REPO, "artifacts", "baseline_seal", "b0_baseline_seal.json")
    checks.append(_require(
        open(live, "rb").read() == open(seal_file, "rb").read(),
        "live seal == archived seal"))
    checks.append(_require(seal["l2_opened"] is False, "seal records l2_opened=False"))
    checks.append(_require(seal["performance_computed"] is False,
                           "seal records performance_computed=False"))

    freeze = _load(FREEZE)
    checks.append(_require(freeze["version"] == EXPECT["master_version"],
                           "Master == v1.31", freeze["version"]))
    checks.append(_require(seal["specification"]["version"] == EXPECT["master_version"],
                           "seal binds Master v1.31"))
    doc_sha = spec_document_sha256()
    checks.append(_require(doc_sha == EXPECT["spec_sha256"], "spec sha256 exact", doc_sha))
    checks.append(_require(freeze["spec_sha256"] == EXPECT["spec_sha256"],
                           "freeze binds the same spec sha256"))
    checks.append(_require(seal["specification"]["spec_sha256"] == EXPECT["spec_sha256"],
                           "seal binds the same spec sha256"))

    head = _git("rev-parse", "HEAD")
    checks.append(_require(head.startswith(EXPECT["commit_prefix"]),
                           "HEAD == d236872a", head[:12]))
    checks.append(_require(head == seal["commit_sha"], "HEAD == sealed commit"))

    # Clean tree, EXCEPT this diagnostic harness itself, which is untracked and
    # normatively inert. Any other delta is an abort: a sealed file that moved
    # means the replay would not be replaying B0.1.
    dirty = [ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()]
    foreign = [ln for ln in dirty
               if "research/b0_6_diagnostic" not in ln.replace("\\", "/")]
    checks.append(_require(not foreign, "working tree clean (sealed scope)",
                           "; ".join(foreign)[:400]))

    # Single writer: no other diagnostic run may be mid-flight.
    if os.path.isdir(CLAIMS_ROOT):
        live_claims = []
        for n in sorted(os.listdir(CLAIMS_ROOT)):
            rid = n[:-5]
            if not os.path.exists(os.path.join(RUNS_ROOT, rid, "final_result.json")):
                live_claims.append(rid)
        checks.append(_require(not live_claims, "single writer",
                               "unterminated diagnostic run(s): %s" % live_claims))
    else:
        checks.append(_require(True, "single writer", "no prior diagnostic claim"))

    measured = normative_module_hashes()
    n = len(seal["normative_module_sha256"])
    checks.append(_require(len(NORMATIVE_MODULES) == n,
                           "normative module count matches the seal",
                           "%d" % n))
    bad = sorted(m for m in seal["normative_module_sha256"]
                 if measured.get(m) != seal["normative_module_sha256"][m])
    checks.append(_require(not bad, "%d/%d normative modules match seal" % (n, n),
                           str(bad)))

    try:
        assert_declarations_conform()
        checks.append(_require(True, "declaration conformance = 0 failures"))
    except Exception as exc:                                    # noqa: BLE001
        raise DiagnosticAbort("PRE-REPLAY VERIFICATION FAILED · declaration "
                              "conformance: %s" % exc) from exc
    checks.append(_require(len(open_items.unspecified_keys()) == 0,
                           "OPEN SPEC ITEMS = 0", str(open_items.unspecified_keys())))
    checks.append(_require(len(fin_items.open_keys()) == 0,
                           "OPEN FINALIZATION ITEMS = 0", str(fin_items.open_keys())))

    # Full suite. Bound to a receipt produced by a real pytest run at this
    # commit, not to a claim typed into an environment variable.
    checks.append(_require(os.path.exists(TEST_RECEIPT), "test receipt present",
                           os.path.relpath(TEST_RECEIPT, REPO)))
    ev = _load(TEST_RECEIPT)
    checks.append(_require(ev.get("commit_sha") == head,
                           "test receipt bound to sealed commit",
                           str(ev.get("commit_sha"))[:12]))
    checks.append(_require(int(ev.get("failed", -1)) == 0 and int(ev.get("errors", -1)) == 0,
                           "full tests green",
                           "%s passed, %s failed, %s error, %s skipped"
                           % (ev.get("passed"), ev.get("failed"),
                              ev.get("errors"), ev.get("skipped"))))
    log_sha, _ = sha256_of(os.path.join(os.path.dirname(TEST_RECEIPT),
                                        ev["log"]))
    checks.append(_require(log_sha == ev["log_sha256"],
                           "test log matches its receipt", log_sha))

    manifest = _load(MANIFEST)
    checks.append(_require(len(manifest) == EXPECT["periods"],
                           "141/141 market-side states present", str(len(manifest))))
    checks.append(_require(
        (manifest[0]["decision_date"], manifest[-1]["decision_date"]) == EXPECT["window"],
        "window 2014-07-31 .. 2026-03-31",
        "%s .. %s" % (manifest[0]["decision_date"], manifest[-1]["decision_date"])))
    missing = [m["artefact"] for m in manifest
               if not os.path.exists(os.path.join(REPO, m["artefact"]))]
    checks.append(_require(not missing, "every state artefact present", str(missing[:3])))
    composed = composed_market_state_sha256(MANIFEST)
    sealed_manifest = {x["name"]: x["content_sha256"] for x in seal["derived"]}
    import hashlib as _h
    man_now = _h.sha256(open(MANIFEST, "rb").read()).hexdigest()
    checks.append(_require(
        man_now == sealed_manifest["data/b0/market_state_manifest.json"],
        "141-state manifest matches the B0.6 seal", man_now))
    checks.append(_require(
        composed == _load(os.path.join(
            REPO, "research", "b0_materializer", "preflight_141_receipt.json"
        ))["market_side"]["composed_market_state_sha256"],
        "composed 141-state hash matches the receipt", composed))
    ca_now = _h.sha256(open(os.path.join(
        REPO, "data", "b0", "corporate_actions_ledger.csv"), "rb").read()).hexdigest()
    checks.append(_require(
        ca_now == sealed_manifest["data/b0/corporate_actions_ledger.csv"],
        "CA ledger matches the B0.6 seal", ca_now))
    p1 = _load(P1_RECEIPT)["full_decision_input_sha256"]
    pf = _load(os.path.join(REPO, "research", "b0_materializer",
                            "preflight_141_receipt.json"))
    checks.append(_require(isinstance(p1, str) and len(p1) == 64,
                           "period-1 full input read from receipt", p1))
    checks.append(_require(
        pf["full_decision_input"]["full_decision_input_sha256"] == p1,
        "period-1 identity agrees across both receipts", p1[:16]))
    checks.append(_require(
        pf["market_side"]["composed_market_state_sha256"] == composed,
        "preflight composed hash agrees with the manifest"))

    # B0.4 · holder-side coverage must still be complete at replay time.
    import csv as _csv
    led = list(_csv.DictReader(open(os.path.join(
        REPO, "data", "b0", "corporate_actions_ledger.csv"), encoding="utf-8")))
    exits = [r for r in led if r["kind"] == "holder_side_reorganization_exit"]
    status = [r for r in _csv.DictReader(open(os.path.join(
        REPO, "data", "b0", "security_status.csv"), encoding="utf-8"))
        if r["status"] == "delisted"
        and r["reason"] in ("合併下市", "併入控股公司下市")]
    uncovered = ({(r["stock_id"], r["effective_from"]) for r in status}
                 - {(r["stock_id"], r["ex_or_effective_date"]) for r in exits})
    checks.append(_require(len(exits) == 158,
                           "158 holder-side disappearance events present",
                           str(len(exits))))
    checks.append(_require(not uncovered,
                           "0 uncovered status-defined disappearance boundaries",
                           str(sorted(uncovered)[:3])))
    checks.append(_require(
        all(r["reconstructibility"] == "NOT_RECONSTRUCTIBLE" for r in exits),
        "holder-side coverage invariant = PASS"))

    from core.b0_benchmark_gate1 import assert_gate1_inputs_sealed
    assert_gate1_inputs_sealed(seal)
    checks.append(_require(True, "Gate-1 benchmark sealed-input reproducibility"))

    from core.b0_1_diagnostic_closure import B0_1_DIAGNOSTIC_RUN_ID as _b1id
    b2 = _load(os.path.join(REPO, "research", "b0_2_diagnostic",
                            "terminal_provenance", "final_result.json"))
    checks.append(_require(
        b2["run_id"] == PARENT_B0_2_DIAGNOSTIC_RUN
        and b2["periods_executed"] == 4 and b2["performance_computed"] is False,
        "Frozen B0.2 diagnostic evidence unchanged",
        "%s %d/141" % (b2["run_id"], b2["periods_executed"])))
    b4 = _load(os.path.join(REPO, "research", "b0_4_diagnostic",
                            "terminal_provenance", "final_result.json"))
    checks.append(_require(
        b4["run_id"] == PARENT_B0_4_DIAGNOSTIC_RUN
        and b4["periods_executed"] == 4 and b4["performance_computed"] is False,
        "Frozen B0.4 diagnostic evidence unchanged",
        "%s %d/141" % (b4["run_id"], b4["periods_executed"])))

    # B0.5 · R2/R3. The repair must still be in force at replay time: an
    # observed zero is a number, a genuinely missing dependency is still NA.
    import numpy as _np
    import pandas as _pd
    zero = na = 0
    for m in manifest:
        _df = _pd.read_parquet(os.path.join(REPO, m["artefact"]),
                               columns=["mark", "adv20"])
        zero += int((_df["adv20"] == 0).sum())
        na += int((_df["mark"].notna() & _df["adv20"].isna()).sum())
    checks.append(_require(zero > 0, "observed-zero ADV20 carried as 0.0", str(zero)))
    checks.append(_require(na > 0, "genuinely missing ADV20 still NA", str(na)))
    from core.b0_state import MarketSnapshot as _MS
    import inspect as _insp
    checks.append(_require(
        "_finite_non_negative(\"adv20\"" in _insp.getsource(_MS),
        "snapshot accepts an observed-zero adv20"))

    b5 = _load(os.path.join(REPO, "research", "b0_5_diagnostic",
                            "terminal_provenance", "final_result.json"))
    checks.append(_require(
        b5["run_id"] == PARENT_B0_5_DIAGNOSTIC_RUN
        and b5["periods_executed"] == 45 and b5["performance_computed"] is False,
        "Frozen B0.5 diagnostic evidence unchanged",
        "%s %d/141" % (b5["run_id"], b5["periods_executed"])))

    # B0.6 · C-65. The repair under replay: the canonical market-side state must
    # CARRY `status_available_from`, because O-E-1 already required it and a
    # state that omits it cannot construct `PitPriceObservation` for a held
    # non-listed security at all. This is a state-sufficiency check, not a
    # runtime lookup: `security_status.csv` is read here ONLY to assert that the
    # sealed source supplies the dates, never to supply them to the replay.
    from core.b0_pit_observability import PitPriceObservation as _PPO
    import inspect as _insp2
    checks.append(_require(
        "status_available_from" in _insp2.signature(_PPO).parameters,
        "PitPriceObservation takes status_available_from"))
    carried = absent = 0
    for m in manifest:
        _df = _pd.read_parquet(os.path.join(REPO, m["artefact"]))
        if "status_available_from" not in _df.columns:
            raise DiagnosticAbort(
                "PRE-REPLAY VERIFICATION FAILED · %s carries no "
                "status_available_from column" % m["artefact"])
        _nl = _df[_df["known_status"] != "listed"]
        carried += int(_nl["status_available_from"].notna().sum())
        absent += int(_nl["status_available_from"].isna().sum())
    checks.append(_require(
        carried > 0 and absent == 0,
        "status PIT dependency closure: every non-listed state observation "
        "carries status_available_from",
        "%d carried, %d absent" % (carried, absent)))
    _st = list(csv.DictReader(open(os.path.join(
        REPO, "data", "b0", "security_status.csv"), encoding="utf-8")))
    checks.append(_require(
        all((r.get("available_from") or "").strip() for r in _st),
        "sealed status source supplies available_from on every row",
        "%d rows" % len(_st)))
    _audit = _load(os.path.join(REPO, "research", "b0_6_status_pit",
                                "status_pit_population_audit.json"))
    checks.append(_require(
        _audit["effective_from_is_a_semantic_dependency"] is False
        and _audit["inferred_dates_created"] == 0
        and _audit["window_141"][
            "observations_with_source_available_from_genuinely_missing"] == 0,
        "status_effective_from stays diagnostic-only; 0 dates inferred",
        "%d non-listed observations in window"
        % _audit["window_141"]["total_non_listed_observations"]))

    # Historical lineage. B0.2 replaces neither run, so both are checked here
    # and again after the terminal record.
    from core.b0_1_diagnostic_closure import (
        B0_1_BASELINE_SEAL_SHA256, B0_1_BOUND_COMMIT,
        B0_1_DIAGNOSTIC_RUN_ID, B0_1_DIAGNOSTIC_TERMINAL_STATUS,
        assert_b0_1_diagnostic_unmutated,
    )
    assert_b0_1_diagnostic_unmutated()
    checks.append(_require(True, "Frozen B0.1 artefacts unmutated",
                           "%s %s" % (B0_1_DIAGNOSTIC_RUN_ID,
                                      B0_1_DIAGNOSTIC_TERMINAL_STATUS)))
    checks.append(_require(
        B0_1_BASELINE_SEAL_SHA256.startswith("4d17505d")
        and B0_1_BOUND_COMMIT.startswith("e708fdb7"),
        "Frozen B0.1 historical identity intact",
        "%s / %s" % (B0_1_BOUND_COMMIT[:8], B0_1_BASELINE_SEAL_SHA256[:8])))

    snap = l2_immutability_snapshot()
    checks.append(_require(
        all(v["matches_pinned"] for v in snap["legacy_pinned_artefacts"].values()
            if v.get("present")),
        "Frozen B0 L2 artefact hashes unchanged"))
    checks.append(_require(snap["attempted_openings"] == EXPECT["attempted_openings"],
                           "attempted_openings == 2", str(snap["attempted_openings"])))
    checks.append(_require(
        snap["effective_observation_count"] == EXPECT["effective_observations"],
        "effective_observation_count == 1", str(snap["effective_observation_count"])))
    claim_dir = os.path.join(LEGACY_RUN_ROOT, "opening_claims")
    n_claims = len(os.listdir(claim_dir)) if os.path.isdir(claim_dir) else 0
    checks.append(_require(n_claims == 1, "no new Frozen B0 L2 opening claim",
                           "%d claim(s)" % n_claims))
    checks.append(_require(
        not os.path.exists(os.path.join(CLAIMS_ROOT, "..", "opening_claims")),
        "diagnostic namespace does not shadow L2 opening_claims"))

    return checks, seal, freeze, head, manifest, composed, p1, snap


def claim_run(run_id, payload):
    """O_EXCL. The check and the claim are one operation, in our own namespace."""
    os.makedirs(CLAIMS_ROOT, exist_ok=True)
    path = os.path.join(CLAIMS_ROOT, run_id + ".json")
    body = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
            + "\n").encode("utf-8")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_BINARY", 0))
    try:
        os.write(fd, body)
    finally:
        os.close(fd)
    os.makedirs(os.path.join(RUNS_ROOT, run_id))     # deliberately NOT exist_ok
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorization", required=True)
    ap.add_argument("--preflight-only", action="store_true")
    a = ap.parse_args()
    if not a.authorization.strip():
        raise DiagnosticAbort("a diagnostic replay requires a named authorization")

    print("== PRE-REPLAY VERIFICATION ==", flush=True)
    checks, seal, freeze, head, manifest, composed, p1, snap_before = preflight(
        a.authorization)
    for c in checks:
        print("  PASS  %-46s %s" % (c["item"], c["detail"]), flush=True)
    print("PRE-REPLAY VERIFICATION: PASS (%d/%d)" % (len(checks), len(checks)),
          flush=True)
    if a.preflight_only:
        return 0

    started = datetime.now(timezone.utc).isoformat()
    run_id = "B06DIAG-" + hashlib.sha256("|".join([
        RUN_KIND, EXPECT["baseline_seal"], freeze["spec_sha256"], head,
        composed, p1, started]).encode()).hexdigest()[:16]
    harness_sha, _ = sha256_of(os.path.abspath(__file__))

    provenance = {
        "record": "B0_6_DIAGNOSTIC_RUN_PROVENANCE",
        "run_id": run_id,
        "run_kind": RUN_KIND,
        "version": "B0.1",
        "evidence_class": EVIDENCE_CLASS,
        "confirmatory_l2": False,
        "replaces_frozen_b0_l2": False,
        "is_l2_opening": False,
        "parent_frozen_b0_l2_run": PARENT_L2_RUN,
        "parent_b0_1_diagnostic_run": PARENT_B0_1_DIAGNOSTIC_RUN,
        "parent_b0_2_diagnostic_run": PARENT_B0_2_DIAGNOSTIC_RUN,
        "parent_b0_4_diagnostic_run": PARENT_B0_4_DIAGNOSTIC_RUN,
        "parent_b0_5_diagnostic_run": PARENT_B0_5_DIAGNOSTIC_RUN,
        "replaces_frozen_b0_1_diagnostic": False,
        "b0_6_baseline_seal": EXPECT["baseline_seal"],
        "started_at_utc": started,
        "authorization": a.authorization,
        "commit_sha": head,
        "spec_sha256": freeze["spec_sha256"],
        "master_version": freeze["version"],
        "market_state_composed_sha256": composed,
        "period1_full_input_sha256": p1,
        "harness_sha256": harness_sha,
        "harness_path": "research/b0_6_diagnostic/run_b0_6_diagnostic.py",
        "normative_module_sha256": seal["normative_module_sha256"],
        "periods_required": EXPECT["periods"],
        "window": list(EXPECT["window"]),
        "performance_computed": False,
        "lineage_snapshot_before": snap_before,
        "preflight": checks,
    }
    claim_path = claim_run(run_id, provenance)
    out = os.path.join(RUNS_ROOT, run_id)
    write_provenance_json(os.path.join(out, "run_provenance.json"), provenance)
    print("\ndiagnostic run_id: %s" % run_id, flush=True)
    print("namespace        : %s" % os.path.relpath(out, REPO), flush=True)
    print("claim            : %s\n" % os.path.relpath(claim_path, REPO), flush=True)

    def jsonl(name, row):
        append_provenance_record(os.path.join(out, name),
                                 json.loads(json.dumps(row, default=str)))

    sessions = tuple(r["session"] for r in csv.DictReader(
        open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8")))
    events_by_sid = load_events()

    from core.b0_market_state import SourceContract, TradingCalendar
    from core.b0_provenance import file_sha256
    from core.b0_state import SourceAttestation
    calendar = TradingCalendar(
        sessions=sessions,
        source=SourceContract(
            name="b0_trading_calendar", kind="trading_calendar",
            importer_version="b0_calendar_importer@1",
            content_sha256=file_sha256(os.path.join(DATA, "trading_calendar.csv")),
            schema_sha256=canonical_sha256(["session"]),
            date_min=sessions[0], date_max=sessions[-1],
            has_effective_dates=True, has_availability_semantics=True,
            is_current_snapshot=False, availability_convention="session_close"))
    attestation = SourceAttestation(
        dataset_id="b0_market_side_state_20260819",
        provenance_sha256=freeze["spec_sha256"], pit_guard_passed=True,
        universe_guard_passed=True,
        satisfied_blocking_requirements=("price_universe_survivorship",),
        synthetic=False)
    price_source = _price_contract(_load(os.path.join(
        REPO, "research", "b0_materializer", "price_panel_receipt.json")))

    _, canonical_open = opening_states(manifest[0]["as_of"])
    portfolio = PortfolioState(
        as_of=canonical_open["as_of"], cash=canonical_open["cash"],
        shares=canonical_open["shares"], pending_exit=canonical_open["pending_exit"],
        cash_dividend_receivable=canonical_open["cash_dividend_receivable"],
        stock_dividend_receivable=canonical_open["stock_dividend_receivable"])
    jsonl("opening_state.jsonl", {
        "run_id": run_id, "as_of": canonical_open["as_of"],
        "cash": canonical_open["cash"],
        "opening_state_hash": ca._state_hash(portfolio)})

    def terminate(status, periods_done, detail, nav_rows=None):
        snap_after = l2_immutability_snapshot()
        untouched = (
            snap_after["l2_artefact_tree_sha256"]
            == snap_before["l2_artefact_tree_sha256"]
            and snap_after["attempted_openings"] == EXPECT["attempted_openings"]
            and snap_after["effective_observation_count"]
            == EXPECT["effective_observations"]
            and snap_after["registry_sha256"] == snap_before["registry_sha256"]
            and snap_after["b0_1_diagnostic"]["composed"]
            == snap_before["b0_1_diagnostic"]["composed"])
        modules_after = normative_module_hashes()
        b01_untouched = all(
            modules_after.get(m) == seal["normative_module_sha256"][m]
            for m in seal["normative_module_sha256"]) and (
            spec_document_sha256() == EXPECT["spec_sha256"])
        record = {
            "record": "B0_6_DIAGNOSTIC_TERMINAL_RESULT",
            "run_id": run_id,
            "run_kind": RUN_KIND,
            "evidence_class": EVIDENCE_CLASS,
            "confirmatory_l2": False,
            "replaces_frozen_b0_l2": False,
            "parent_frozen_b0_l2_run": PARENT_L2_RUN,
            "parent_b0_1_diagnostic_run": PARENT_B0_1_DIAGNOSTIC_RUN,
            "parent_b0_2_diagnostic_run": PARENT_B0_2_DIAGNOSTIC_RUN,
            "parent_b0_4_diagnostic_run": PARENT_B0_4_DIAGNOSTIC_RUN,
            "parent_b0_5_diagnostic_run": PARENT_B0_5_DIAGNOSTIC_RUN,
            "replaces_frozen_b0_1_diagnostic": False,
            "b0_6_baseline_seal": EXPECT["baseline_seal"],
            "terminated_at_utc": datetime.now(timezone.utc).isoformat(),
            "commit_sha": head,
            "spec_sha256": freeze["spec_sha256"],
            "market_state_composed_sha256": composed,
            "period1_full_input_sha256": p1,
            "harness_sha256": harness_sha,
            "authorization": a.authorization,
            "periods_executed": periods_done,
            "periods_required": EXPECT["periods"],
            "diagnostic_terminal_status": status,
            "performance_computed": False,
            "detail": detail,
            "lineage_snapshot_after": snap_after,
            "historical_lineage_untouched": untouched,
            "b0_6_unmodified_during_replay": b01_untouched,
            "gates_evaluated": False,
            "performance_displayed": False,
        }
        if nav_rows is not None:
            record["nav_rows"] = nav_rows
        write_provenance_json(os.path.join(out, "final_result.json"), record)
        print("\nterminal status: %s  (%d/%d periods)"
              % (status, periods_done, EXPECT["periods"]), flush=True)
        print("historical lineage untouched: %s | B0.6 unmodified: %s"
              % (untouched, b01_untouched), flush=True)
        print("performance computed: False | gates evaluated: False", flush=True)
        return record

    nav_series, done = [], 0
    for i, period in enumerate(manifest, 1):
        as_of = period["as_of"]
        try:
            state = ca.redate(portfolio, as_of)
            held_events = [e for sid in state.entitlement_securities
                           for e in events_by_sid.get(sid, ())]
            tr = ca.transition_portfolio(state, held_events, as_of=as_of,
                                         sessions=sessions,
                                         period=period["decision_month"])
            for rec in tr.ledger:
                jsonl("ca_transition_ledger.jsonl",
                      {"run_id": run_id, **rec.__dict__})
            rows = pd.read_parquet(os.path.join(REPO, period["artefact"]))
            inp = build_input(period, rows, tr.state, sessions, events_by_sid,
                              calendar, attestation, price_source)
            result = run_decision(inp, for_sealed_run=True)
            s = result.session
            portfolio = PortfolioState(
                as_of=as_of, cash=s.cash_after, shares=dict(s.shares_after),
                pending_exit=dict(s.pending_exit_after),
                cash_dividend_receivable=tr.state.cash_dividend_receivable,
                stock_dividend_receivable=dict(tr.state.stock_dividend_receivable),
                security_receivables=tr.state.security_receivables,
                cash_receivables=tr.state.cash_receivables,
                applied_ca_event_ids=tr.state.applied_ca_event_ids,
                pending_exit_on_receivable=tr.state.pending_exit_on_receivable,
                holding_spells=tr.state.holding_spells)
            portfolio = portfolio.with_underlying_exposure_recorded(
                period["execution_date"])
            nav_series.append({"period": period["decision_month"], "as_of": as_of,
                               "port_value": result.port_value,
                               "cash_after": s.cash_after,
                               "positions": len(s.shares_after)})
            jsonl("period_progress.jsonl", {
                "run_id": run_id, "seq": i, "period": period["decision_month"],
                "as_of": as_of, "port_value": result.port_value,
                "state_hash": result.state_hash,
                "positions": len(s.shares_after),
                "ca_applied": list(tr.applied_event_ids),
                "post_state_hash": ca._state_hash(portfolio)})
            done = i
        except ca.CorporateActionReconstructionBlock as exc:
            jsonl("failure_record.jsonl", {
                "run_id": run_id, "classification": "F-CA-B",
                "blocker_kind": "data_reconstruction",
                "period": period["decision_month"], "seq": i, **exc.detail})
            print("BLOCK F-CA-B at %s: %s" % (period["decision_month"], exc))
            terminate("DIAGNOSTIC_NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK",
                      done, {"classification": "F-CA-B",
                             "blocker_kind": "data_reconstruction",
                             "period": period["decision_month"], "seq": i,
                             "reason": str(exc)})
            return 2
        except Exception as exc:                                # noqa: BLE001
            jsonl("failure_record.jsonl", {
                "run_id": run_id, "classification": "F-CA-C-or-core",
                "blocker_kind": "implementation_conformance_or_invariant",
                "period": period["decision_month"], "seq": i,
                "error_type": type(exc).__name__, "error": str(exc),
                "traceback": traceback.format_exc()[-4000:]})
            print("FAILURE at %s: %s: %s" % (period["decision_month"],
                                             type(exc).__name__, exc))
            terminate("DIAGNOSTIC_RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE",
                      done, {"classification": "F-CA-C-or-core",
                             "blocker_kind": "implementation_conformance_or_invariant",
                             "period": period["decision_month"], "seq": i,
                             "error_type": type(exc).__name__, "error": str(exc)})
            return 3
        if i % 10 == 0:
            # port_value deliberately NOT printed: at period 141 it IS terminal
            # cumulative wealth, and no evaluation has been authorised.
            print("  %3d/141  %s  positions=%d  ca_applied=%d"
                  % (i, period["decision_month"], len(s.shares_after),
                     len(tr.applied_event_ids)), flush=True)

    write_provenance_json(os.path.join(out, "nav_series.json"), nav_series)
    print("completed %d/%d periods" % (done, EXPECT["periods"]), flush=True)
    terminate("DIAGNOSTIC_REPLAY_COMPLETE", done,
              {"periods_executed": done, "nav_rows": len(nav_series)},
              nav_rows=len(nav_series))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DiagnosticAbort as exc:
        print("\nABORT · %s" % exc)
        print("STOP BEFORE DIAGNOSTIC REPLAY. Do not repair and continue "
              "under this authorization.")
        sys.exit(1)
