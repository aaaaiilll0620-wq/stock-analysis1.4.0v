# -*- coding: utf-8 -*-
"""Frozen B0.7 RETROSPECTIVE DIAGNOSTIC REPLAY. Master v1.32 §18.

THIS IS NOT AN L2 RUN, AND IT IS STRUCTURALLY INCAPABLE OF BECOMING ONE.

  * it never imports `record_opening`, `create_opening_claim` or
    `create_execution_claim`
  * it never writes under `artifacts/l2_run/` -- its entire namespace is
    `artifacts/b0_7_diagnostic/`
  * it snapshots every Frozen B0 L2 artefact hash, the pinned B0.1 diagnostic
    identity, the B0.2/B0.4/B0.5/B0.6 terminal results, `attempted_openings`
    and `effective_observation_count` BEFORE the first byte is written and
    asserts them unchanged AFTER the terminal record.

WHAT IS DIFFERENT FROM B0.1 .. B0.6

Performance computation is AUTHORIZED AND REQUIRED -- but only on 141/141
completion. Below 141 the metric block is not computed, not displayed and not
written. That is not a courtesy: a cumulative-wealth number from a truncated
window is a number about a window that did not happen.

PRE-SEAL DISCLOSURE (bound into provenance, not a footnote)

The B0.7 repair was preceded by a read-only scratch traversal of periods 1-67
that observed historical state-transition consequences, including claim-bearing
corporate-action applications. B0.7 is therefore NOT historically untouched and
NOT fully blind through that prefix. No performance quantity and no gate was
computed or inspected during it. This changes nothing about the evidence class,
which is and remains RETROSPECTIVE_SUPPORTING_ONLY.

Strategy semantics come from the sealed core and from nowhere else: `build_input`
and `load_events` are IMPORTED verbatim from the sealed L2 runner, and every
feature, filter, score, target, order, cost and corporate action happens behind
`run_decision` / `core.b0_corporate_actions`.

    python research/b0_7_diagnostic/run_b0_7_diagnostic.py --authorization "<ref>"
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import traceback
from datetime import date, datetime, timezone

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

from run_sealed_l2 import build_input, load_events                 # noqa: E402
from build_period1_full_input import _price_contract, opening_states  # noqa: E402

RUN_KIND = "B0_7_RETROSPECTIVE_DIAGNOSTIC"
EVIDENCE_CLASS = "RETROSPECTIVE_SUPPORTING_ONLY"
PARENT_L2_RUN = "L2-af1b4d90c29b3b5f"
PARENT_DIAGNOSTICS = {
    "b0_1": ("B01DIAG-0121b3261805b826", 2),
    "b0_2": ("B02DIAG-bc7ce018a97cfa0f", 4),
    "b0_4": ("B04DIAG-d5f34a5164a0e309", 4),
    "b0_5": ("B05DIAG-9943d2f7b4adb670", 45),
    "b0_6": ("B06DIAG-055dbf317d3f67ac", 66),
}

DATA = os.path.join(REPO, "data", "b0")
MANIFEST = os.path.join(DATA, "market_state_manifest.json")
SEAL_ARCHIVE = os.path.join(REPO, "artifacts", "baseline_seal", "seals")
FREEZE = os.path.join(REPO, "research", "b0_registry", "master_prereg_freeze.json")
P1_RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                          "period1_full_input_receipt.json")
PREFLIGHT_RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                                 "preflight_141_receipt.json")

DIAG_ROOT = os.path.join(REPO, "artifacts", "b0_7_diagnostic")
RUNS_ROOT = os.path.join(DIAG_ROOT, "runs")
CLAIMS_ROOT = os.path.join(DIAG_ROOT, "run_claims")
TEST_RECEIPT = os.path.join(DIAG_ROOT, "test_evidence.json")

# The authorization's bound identities. A drift is an abort, never a repair.
EXPECT = {
    "baseline_seal":
        "c973cff3dfae700323c092551fd666f0b004def9be19bfd51233df0f797a1798",
    "spec_sha256":
        "d9212c8f1a6781709307f7428905287904fd2a6651bd431f43d2e5ac7b66efd3",
    "composed_141":
        "0b68f44e38716cf5dc0ab29ac8dccb645c203d748102ac27f33831186653e405",
    "master_version": "1.32",
    "commit_prefix": "271b1106",
    "attempted_openings": 2,
    "effective_observations": 1,
    "periods": 141,
    "window": ("2014-07-31", "2026-03-31"),
}

# Bound into provenance verbatim, per the authorization.
PRESEAL_DISCLOSURE = {
    "preseal_retrospective_path_exposure": True,
    "preseal_path_exposure_through_period": 67,
    "preseal_performance_inspection": False,
    "preseal_gate_inspection": False,
    "note": ("The pre-seal traversal was a dependency/conformance audit. It "
             "observed historical state-transition consequences, including "
             "claim-bearing corporate-action applications, so B0.7 is neither "
             "historically untouched nor fully blind through that prefix. It "
             "computed and inspected no performance quantity and no gate. The "
             "evidence class is unchanged in both directions."),
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


def _b0_1_snapshot():
    from core.b0_1_diagnostic_closure import b0_1_diagnostic_identity

    ident = b0_1_diagnostic_identity()
    return {"artefacts": ident, "composed": canonical_sha256(ident)}


def lineage_snapshot():
    """Every byte under artifacts/l2_run, plus the accounting scalars."""
    files = {}
    for base, _dirs, names in os.walk(LEGACY_RUN_ROOT):
        for n in sorted(names):
            p = os.path.join(base, n)
            sha, size = sha256_of(p)
            files[os.path.relpath(p, REPO).replace("\\", "/")] = {
                "sha256": sha, "bytes": size}
    diag = {}
    for key, (run_id, periods) in sorted(PARENT_DIAGNOSTICS.items()):
        fr = os.path.join(REPO, "artifacts", "%s_diagnostic" % key, "runs",
                          run_id, "final_result.json")
        if not os.path.exists(fr):
            fr = os.path.join(REPO, "research", "%s_diagnostic" % key,
                              "terminal_provenance", "final_result.json")
        entry = {"run_id": run_id, "expected_periods": periods}
        if os.path.exists(fr):
            sha, _ = sha256_of(fr)
            rec = _load(fr)
            entry.update({"final_result_sha256": sha,
                          "periods_executed": rec.get("periods_executed"),
                          "performance_computed": rec.get("performance_computed")})
        diag[key] = entry
    return {
        "l2_artefact_files": files,
        "l2_artefact_tree_sha256": canonical_sha256(files),
        "legacy_pinned_artefacts": legacy_artefact_identity(),
        "attempted_openings": attempted_opening_count(),
        "effective_observation_count": effective_observation_count(),
        "registry_rows": len(read_registry()),
        "registry_sha256": canonical_sha256(read_registry()),
        "b0_1_diagnostic": _b0_1_snapshot(),
        "prior_diagnostics": diag,
    }


def preflight():
    """Mechanically verify, then refuse or proceed. There is no repair path."""
    checks = []

    seal_file = os.path.join(SEAL_ARCHIVE, EXPECT["baseline_seal"] + ".json")
    checks.append(_require(os.path.exists(seal_file), "B0.7 seal archived",
                           EXPECT["baseline_seal"][:16]))
    seal = _load(seal_file)
    seal_bytes_sha, _ = sha256_of(seal_file)
    checks.append(_require(
        seal["baseline_seal_sha256"] == os.path.basename(seal_file)[:-5],
        "seal filename == payload identity"))
    live = os.path.join(REPO, "artifacts", "baseline_seal", "b0_baseline_seal.json")
    checks.append(_require(open(live, "rb").read() == open(seal_file, "rb").read(),
                           "live seal == archived seal bytes", seal_bytes_sha[:16]))
    checks.append(_require(seal["l2_opened"] is False, "seal records l2_opened=False"))
    checks.append(_require(seal["performance_computed"] is False,
                           "seal records performance_computed=False"))

    freeze = _load(FREEZE)
    checks.append(_require(freeze["version"] == EXPECT["master_version"],
                           "Master == v1.32", freeze["version"]))
    checks.append(_require(
        seal["specification"]["version"] == EXPECT["master_version"],
        "seal binds Master v1.32"))
    doc_sha = spec_document_sha256()
    checks.append(_require(doc_sha == EXPECT["spec_sha256"], "spec sha256 exact",
                           doc_sha))
    checks.append(_require(freeze["spec_sha256"] == EXPECT["spec_sha256"],
                           "freeze binds the same spec sha256"))
    checks.append(_require(
        seal["specification"]["spec_sha256"] == EXPECT["spec_sha256"],
        "seal binds the same spec sha256"))

    head = _git("rev-parse", "HEAD")
    checks.append(_require(head.startswith(EXPECT["commit_prefix"]),
                           "HEAD == 271b1106", head[:12]))
    checks.append(_require(head == seal["commit_sha"], "HEAD == sealed commit"))

    dirty = [ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()]
    foreign = [ln for ln in dirty
               if "research/b0_7_diagnostic" not in ln.replace("\\", "/")]
    checks.append(_require(not foreign, "working tree clean (sealed scope)",
                           "; ".join(foreign)[:400]))

    if os.path.isdir(CLAIMS_ROOT):
        unterminated = [n[:-5] for n in sorted(os.listdir(CLAIMS_ROOT))
                        if not os.path.exists(os.path.join(
                            RUNS_ROOT, n[:-5], "final_result.json"))]
        checks.append(_require(not unterminated, "single writer",
                               str(unterminated)))
    else:
        checks.append(_require(True, "single writer", "no prior diagnostic claim"))

    measured = normative_module_hashes()
    n = len(seal["normative_module_sha256"])
    checks.append(_require(len(NORMATIVE_MODULES) == n,
                           "normative module count matches the seal", str(n)))
    bad = sorted(m for m in seal["normative_module_sha256"]
                 if measured.get(m) != seal["normative_module_sha256"][m])
    checks.append(_require(not bad, "%d/%d normative modules match seal" % (n, n),
                           str(bad)))

    try:
        assert_declarations_conform()
    except Exception as exc:                                    # noqa: BLE001
        raise DiagnosticAbort("PRE-REPLAY VERIFICATION FAILED · declaration "
                              "conformance: %s" % exc) from exc
    checks.append(_require(True, "declaration conformance = 0 failures"))
    checks.append(_require(len(open_items.unspecified_keys()) == 0,
                           "OPEN SPEC ITEMS = 0",
                           str(open_items.unspecified_keys())))
    checks.append(_require(len(fin_items.open_keys()) == 0,
                           "OPEN FINALIZATION ITEMS = 0", str(fin_items.open_keys())))

    checks.append(_require(os.path.exists(TEST_RECEIPT), "test receipt present"))
    ev = _load(TEST_RECEIPT)
    checks.append(_require(ev.get("commit_sha") == head,
                           "test receipt bound to sealed commit",
                           str(ev.get("commit_sha"))[:12]))
    checks.append(_require(int(ev.get("failed", -1)) == 0
                           and int(ev.get("errors", -1)) == 0,
                           "full suite green", ev.get("summary", "")))
    log_sha, _ = sha256_of(os.path.join(DIAG_ROOT, ev["log"]))
    checks.append(_require(log_sha == ev["log_sha256"],
                           "test log matches its receipt", log_sha[:16]))

    manifest = _load(MANIFEST)
    checks.append(_require(len(manifest) == EXPECT["periods"],
                           "141/141 market-side states present", str(len(manifest))))
    checks.append(_require(
        (manifest[0]["decision_date"], manifest[-1]["decision_date"])
        == EXPECT["window"], "window 2014-07-31 .. 2026-03-31"))
    missing = [m["artefact"] for m in manifest
               if not os.path.exists(os.path.join(REPO, m["artefact"]))]
    checks.append(_require(not missing, "every state artefact present",
                           str(missing[:3])))
    composed = composed_market_state_sha256(MANIFEST)
    checks.append(_require(composed == EXPECT["composed_141"],
                           "composed 141-state hash exact", composed))
    sealed = {x["name"]: x["content_sha256"] for x in seal["derived"]}
    man_now = hashlib.sha256(open(MANIFEST, "rb").read()).hexdigest()
    checks.append(_require(
        man_now == sealed["data/b0/market_state_manifest.json"],
        "141-state manifest matches the B0.7 seal", man_now[:16]))
    ca_path = os.path.join(DATA, "corporate_actions_ledger.csv")
    ca_now = hashlib.sha256(open(ca_path, "rb").read()).hexdigest()
    checks.append(_require(ca_now == sealed["data/b0/corporate_actions_ledger.csv"],
                           "CA ledger identity exact", ca_now[:16]))

    p1 = _load(P1_RECEIPT)["full_decision_input_sha256"]
    pf = _load(PREFLIGHT_RECEIPT)
    checks.append(_require(isinstance(p1, str) and len(p1) == 64,
                           "period-1 full input read from receipt", p1))
    checks.append(_require(
        pf["full_decision_input"]["full_decision_input_sha256"] == p1,
        "period-1 identity agrees across both receipts", p1[:16]))
    checks.append(_require(
        pf["market_side"]["composed_market_state_sha256"] == composed,
        "preflight composed hash agrees with the manifest"))

    # --- B0.7 · the repair under replay --------------------------------------
    ca.assert_claim_bearing_registry_conforms()
    checks.append(_require(True, "CLAIM_BEARING_EVENT_KINDS registry conformance",
                           ",".join(ca.CLAIM_BEARING_EVENT_KINDS)))
    checks.append(_require(
        set(ca.CLAIM_BEARING_EVENT_KINDS) == set(ca.holder_affecting_kinds())
        and len(ca.CLAIM_BEARING_EVENT_KINDS) == 5,
        "claim applicability is not broadened beyond the derived classes"))
    _, canonical_open0 = opening_states(manifest[0]["as_of"])
    probe = PortfolioState(
        as_of=canonical_open0["as_of"], cash=canonical_open0["cash"],
        shares=canonical_open0["shares"],
        pending_exit=canonical_open0["pending_exit"],
        cash_dividend_receivable=canonical_open0["cash_dividend_receivable"],
        stock_dividend_receivable=canonical_open0["stock_dividend_receivable"])
    delivered = ca.deliver_ca_events({}, probe, as_of=probe.as_of)
    ca.assert_ca_event_delivery_conforms(delivered, probe, as_of=probe.as_of)
    checks.append(_require(True,
                           "ECONOMIC_INTEREST_EVENT_DELIVERY_INVARIANT wired"))

    from core.b0_benchmark_construction import assert_strategy_wealth_is_mark_to_market
    from core.b0_benchmark_gate1 import assert_gate1_inputs_sealed

    assert_gate1_inputs_sealed(seal)
    checks.append(_require(True, "Gate-1 sealed-input reproducibility"))
    sym = assert_strategy_wealth_is_mark_to_market()
    checks.append(_require(sym["symmetric"] and not sym["contradiction"],
                           "B5 terminal treatment symmetric (mark-to-market)"))

    # --- historical evidence --------------------------------------------------
    from core.b0_1_diagnostic_closure import (
        B0_1_BASELINE_SEAL_SHA256, B0_1_BOUND_COMMIT,
        assert_b0_1_diagnostic_unmutated,
    )

    assert_b0_1_diagnostic_unmutated()
    checks.append(_require(
        B0_1_BASELINE_SEAL_SHA256.startswith("4d17505d")
        and B0_1_BOUND_COMMIT.startswith("e708fdb7"),
        "Frozen B0.1 historical identity intact"))
    snap = lineage_snapshot()
    for key, entry in sorted(snap["prior_diagnostics"].items()):
        checks.append(_require(
            entry.get("periods_executed") == entry["expected_periods"]
            and entry.get("performance_computed") is False,
            "Frozen %s diagnostic evidence unchanged" % key.upper().replace("_", "."),
            "%s %s/141" % (entry["run_id"], entry.get("periods_executed"))))
    checks.append(_require(
        all(v["matches_pinned"] for v in snap["legacy_pinned_artefacts"].values()
            if v.get("present")),
        "Frozen B0 L2 artefact hashes unchanged"))
    checks.append(_require(
        snap["attempted_openings"] == EXPECT["attempted_openings"],
        "Frozen B0 attempted_openings == 2", str(snap["attempted_openings"])))
    checks.append(_require(
        snap["effective_observation_count"] == EXPECT["effective_observations"],
        "Frozen B0 effective_observation_count == 1",
        str(snap["effective_observation_count"])))
    claim_dir = os.path.join(LEGACY_RUN_ROOT, "opening_claims")
    n_claims = len(os.listdir(claim_dir)) if os.path.isdir(claim_dir) else 0
    checks.append(_require(n_claims == 1, "no new Frozen B0 L2 opening claim",
                           "%d claim(s)" % n_claims))
    checks.append(_require(
        not os.path.exists(os.path.join(DIAG_ROOT, "opening_claims")),
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


# --- the 0050 benchmark, built only if 141/141 completes ----------------------

def build_benchmark(manifest):
    """§13 / B1-B7. The sealed 0050 buy-and-hold, from frozen primitives only."""
    from core.b0_benchmark_construction import (
        BENCHMARK_SECURITY, C_REF, BenchmarkLedger, apply_dividend_ex_date,
        apply_share_unit_event, solve_initial_shares,
    )
    from core.b0_state import compute_sigma20d

    panel = pd.read_parquet(os.path.join(DATA, "benchmark_0050_panel.parquet"))
    panel["session"] = panel["session"].astype(str)
    panel = panel.sort_values("session").reset_index(drop=True)
    by_session = {r.session: r for r in panel.itertuples()}

    first = manifest[0]
    as_of, exec_day = first["as_of"], first["execution_date"]
    if exec_day not in by_session:
        raise DiagnosticAbort(
            "B6: the benchmark panel has no observation on the canonical first "
            "executable session %s; gate 1 is NON-EVALUABLE" % exec_day)

    # B4: 0050's OWN adv20 / sigma20d, on the canonical definitions.
    upto = [s for s in panel["session"] if s <= as_of]
    if len(upto) < 21:
        raise DiagnosticAbort(
            "B6: only %d benchmark sessions on or before %s; sigma20d needs 21"
            % (len(upto), as_of))
    window = upto[-20:]
    adv20 = sum(by_session[s].close * by_session[s].volume_shares
                for s in window) / 20.0
    closes = [by_session[s].close for s in upto[-21:]]
    sigma20d = compute_sigma20d(closes)

    solved = solve_initial_shares(
        float(by_session[exec_day].open), C_REF, float(sigma20d), float(adv20),
        data_as_of=as_of, execution_date=exec_day)
    ledger = BenchmarkLedger(shares=solved["shares"], cash=solved["residual_cash"])

    dists = [r for r in csv.DictReader(open(
        os.path.join(DATA, "benchmark_0050_distributions.csv"), encoding="utf-8"))]
    units = pd.read_parquet(
        os.path.join(DATA, "benchmark_0050_share_unit_events.parquet"))

    terminal = manifest[-1]["as_of"]
    # R5: the two transitions are different shapes, but they share one TIMELINE.
    # A distribution on the far side of a split entitles the post-split share
    # count, so applying every split first and every ex-date afterwards would
    # over-credit the earlier dividends. They are merged and walked in date
    # order for that reason, not for tidiness.
    timeline = []
    for _, ev in units.iterrows():
        eff = str(ev["effective_date"])
        if str(ev["security_id"]) == BENCHMARK_SECURITY and exec_day < eff <= terminal:
            timeline.append((eff, "unit", ev))
    for row in dists:
        ex = str(row["ex_date"])
        if exec_day < ex <= terminal:
            timeline.append((ex, "dist", row))
    # A split and an ex-date on the SAME session would be an ordering the sealed
    # lineage does not state, and guessing it is exactly what §6.1.11 forbids.
    same_day = {d for d, _, _ in timeline
                if sum(1 for x, _, _ in timeline if x == d) > 1}
    if same_day:
        raise DiagnosticAbort(
            "B6/§6.1.11: benchmark events share session(s) %s and the sealed "
            "lineage states no causal order between them" % sorted(same_day))

    applied_units, applied_dists = [], []
    for when, kind, obj in sorted(timeline, key=lambda t: t[0]):
        if kind == "unit":
            eid = "%s|%s|%s" % (obj["security_id"], obj["event_class"], when)
            ledger = apply_share_unit_event(
                ledger, eid, float(obj["holder_multiplier"]))
            applied_units.append({
                "event_id": eid, "effective_date": when,
                "holder_multiplier": float(obj["holder_multiplier"]),
                "shares_after": ledger.shares})
        else:
            cpu = float(obj["cash_per_unit"])
            shares_at_ex = ledger.shares
            ledger = apply_dividend_ex_date(ledger, cpu)
            applied_dists.append({"ex_date": when, "cash_per_unit": cpu,
                                  "shares_at_ex": shares_at_ex,
                                  "receivable_after": ledger.receivable})
    if terminal not in by_session:
        raise DiagnosticAbort(
            "B6: the benchmark panel has no observation on the canonical "
            "terminal valuation session %s; gate 1 is NON-EVALUABLE" % terminal)
    wealth = ledger.wealth(float(by_session[terminal].close))
    return {
        "security": BENCHMARK_SECURITY,
        "identity": "0050 buy-and-hold, dividend-inclusive",
        "initial_cash": C_REF,
        "initial_execution_session": exec_day,
        "initial_execution_price": solved["execution_price"],
        "adv20_used": float(adv20), "sigma20d_used": float(sigma20d),
        "initial_shares": solved["shares"],
        "initial_explicit_fee": solved["explicit_fee"],
        "initial_impact": solved["impact"],
        "initial_transaction_tax": solved["transaction_tax"],
        "residual_cash": solved["residual_cash"],
        "share_unit_events_applied": applied_units,
        "distributions_applied": applied_dists,
        "terminal_session": terminal,
        "terminal_close": float(by_session[terminal].close),
        "terminal_shares": ledger.shares,
        "terminal_cash": ledger.cash,
        "terminal_receivable": ledger.receivable,
        "terminal_wealth": wealth,
        "wealth_multiple": wealth / C_REF,
        "cumulative_return": wealth / C_REF - 1.0,
        "terminal_treatment": "MARK_TO_MARKET",
        "dividends_reinvested": False,
    }


def performance(nav_rows, opening_cash):
    """Only ever called on 141/141. Conventions are stated, not assumed frozen.

    The Master freezes the three gate PREDICATES (§9.4) and the Sharpe rf
    convention (V-6), but it does not freeze an annualisation factor, a
    year-count convention or a drawdown sampling frequency. Those are reporting
    choices and are named here rather than buried:

        return series   period-over-period simple returns of the 141 marked
                        NAV points, the series B0 actually produces
        CAGR            (W_T / W_0) ** (1 / years) - 1, years = actual days/365.25
        Sharpe_0rf      mean / stdev(ddof=1) of that series x sqrt(12), rf = 0,
                        ddof=1 matching the project's own sigma convention
        MDD             max peak-to-trough decline of the same 141 points

    Every gate verdict is invariant to all of them: gate 2 is decided by
    W_T > W_0 and gate 3 by mean(returns) > 0, and no positive scaling factor
    can move a sign. The NUMBERS depend on the conventions; the PASS/FAIL does
    not, which is why the conventions are reportable rather than an M-3.
    """
    w = [float(r["port_value"]) for r in nav_rows]
    w0 = float(opening_cash)
    rets = []
    prev = w0
    for x in w:
        rets.append(x / prev - 1.0 if prev else 0.0)
        prev = x
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    d0 = date.fromisoformat(nav_rows[0]["as_of"])
    dT = date.fromisoformat(nav_rows[-1]["as_of"])
    years = (dT - d0).days / 365.25
    cagr = (w[-1] / w0) ** (1.0 / years) - 1.0 if years > 0 and w0 > 0 else None
    peak, mdd = w0, 0.0
    for x in [w0] + w:
        peak = max(peak, x)
        mdd = max(mdd, (peak - x) / peak if peak else 0.0)
    return {
        "opening_wealth": w0,
        "terminal_wealth": w[-1],
        "wealth_multiple": w[-1] / w0,
        "cumulative_return": w[-1] / w0 - 1.0,
        "years": years,
        "cagr": cagr,
        "sharpe_metric_name": "Sharpe_0rf",
        "sharpe_0rf": (mean / sd * math.sqrt(12.0)) if sd > 0 else None,
        "mean_period_return": mean,
        "stdev_period_return_ddof1": sd,
        "mdd": mdd,
        "periods": len(w),
        "conventions": {
            "return_series": "period-over-period simple returns of 141 marked NAV points",
            "cagr": "(W_T/W_0)**(1/years) - 1, years = actual days / 365.25",
            "sharpe": "mean/stdev(ddof=1) x sqrt(12), rf = 0",
            "mdd": "max peak-to-trough decline of the same marked series",
            "gate_verdicts_are_invariant_to_these": True,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorization", required=True)
    ap.add_argument("--preflight-only", action="store_true")
    a = ap.parse_args()
    if not a.authorization.strip():
        raise DiagnosticAbort("a diagnostic replay requires a named authorization")

    print("== PRE-REPLAY VERIFICATION ==", flush=True)
    checks, seal, freeze, head, manifest, composed, p1, snap_before = preflight()
    for c in checks:
        print("  PASS  %-52s %s" % (c["item"], c["detail"]), flush=True)
    print("PRE-REPLAY VERIFICATION: PASS (%d/%d)" % (len(checks), len(checks)),
          flush=True)
    if a.preflight_only:
        return 0

    started = datetime.now(timezone.utc).isoformat()
    run_id = "B07DIAG-" + hashlib.sha256("|".join([
        RUN_KIND, EXPECT["baseline_seal"], freeze["spec_sha256"], head,
        composed, p1, started]).encode()).hexdigest()[:16]
    harness_sha, _ = sha256_of(os.path.abspath(__file__))

    provenance = {
        "record": "B0_7_DIAGNOSTIC_RUN_PROVENANCE",
        "run_id": run_id,
        "run_kind": RUN_KIND,
        "version": "B0.7",
        "evidence_class": EVIDENCE_CLASS,
        "confirmatory_l2": False,
        "replaces_frozen_b0_l2": False,
        "is_l2_opening": False,
        "parent_frozen_b0_l2_run": PARENT_L2_RUN,
        "parent_diagnostic_runs": {k: v[0] for k, v in PARENT_DIAGNOSTICS.items()},
        "b0_7_baseline_seal": EXPECT["baseline_seal"],
        "started_at_utc": started,
        "authorization": a.authorization,
        "commit_sha": head,
        "spec_sha256": freeze["spec_sha256"],
        "master_version": freeze["version"],
        "market_state_composed_sha256": composed,
        "period1_full_input_sha256": p1,
        "harness_sha256": harness_sha,
        "harness_path": "research/b0_7_diagnostic/run_b0_7_diagnostic.py",
        "normative_module_sha256": seal["normative_module_sha256"],
        "periods_required": EXPECT["periods"],
        "window": list(EXPECT["window"]),
        "performance_authorized_on_141_of_141": True,
        "performance_computed": False,
        "lineage_snapshot_before": snap_before,
        "preflight": checks,
        **PRESEAL_DISCLOSURE,
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
    opening_cash = float(canonical_open["cash"])
    jsonl("opening_state.jsonl", {
        "run_id": run_id, "as_of": canonical_open["as_of"],
        "cash": opening_cash, "opening_state_hash": ca._state_hash(portfolio)})

    def terminate(status, periods_done, detail, nav_rows=None, metrics=None):
        snap_after = lineage_snapshot()
        untouched = (
            snap_after["l2_artefact_tree_sha256"]
            == snap_before["l2_artefact_tree_sha256"]
            and snap_after["attempted_openings"] == EXPECT["attempted_openings"]
            and snap_after["effective_observation_count"]
            == EXPECT["effective_observations"]
            and snap_after["registry_sha256"] == snap_before["registry_sha256"]
            and snap_after["b0_1_diagnostic"]["composed"]
            == snap_before["b0_1_diagnostic"]["composed"]
            and all(snap_after["prior_diagnostics"][k].get("final_result_sha256")
                    == snap_before["prior_diagnostics"][k].get("final_result_sha256")
                    for k in snap_before["prior_diagnostics"]))
        modules_after = normative_module_hashes()
        unmodified = all(
            modules_after.get(m) == seal["normative_module_sha256"][m]
            for m in seal["normative_module_sha256"]) and (
            spec_document_sha256() == EXPECT["spec_sha256"])
        record = {
            "record": "B0_7_DIAGNOSTIC_TERMINAL_RESULT",
            "run_id": run_id,
            "run_kind": RUN_KIND,
            "evidence_class": EVIDENCE_CLASS,
            "confirmatory_l2": False,
            "replaces_frozen_b0_l2": False,
            "parent_frozen_b0_l2_run": PARENT_L2_RUN,
            "parent_diagnostic_runs": {k: v[0] for k, v in PARENT_DIAGNOSTICS.items()},
            "b0_7_baseline_seal": EXPECT["baseline_seal"],
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
            "performance_computed": metrics is not None,
            "gates_evaluated": bool(metrics and "gates" in metrics),
            "performance_displayed": metrics is not None,
            "detail": detail,
            "lineage_snapshot_after": snap_after,
            "historical_lineage_untouched": untouched,
            "b0_7_unmodified_during_replay": unmodified,
            **PRESEAL_DISCLOSURE,
        }
        if nav_rows is not None:
            record["nav_rows"] = len(nav_rows)
        if metrics is not None:
            record["metrics"] = metrics
        write_provenance_json(os.path.join(out, "final_result.json"), record)
        print("\nterminal status: %s  (%d/%d periods)"
              % (status, periods_done, EXPECT["periods"]), flush=True)
        print("historical lineage untouched: %s | B0.7 unmodified: %s"
              % (untouched, unmodified), flush=True)
        print("performance computed: %s | gates evaluated: %s"
              % (record["performance_computed"], record["gates_evaluated"]),
              flush=True)
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
                "claim_only_securities": list(tr.state.claim_only_securities(as_of)),
                "post_state_hash": ca._state_hash(portfolio)})
            done = i
        except ca.CorporateActionReconstructionBlock as exc:
            d = dict(exc.detail)
            sid = d.get("security_id")
            # `state` and not `tr.state`: the block is raised from inside
            # `transition_portfolio`, so `tr` is unassigned this period and any
            # value it holds belongs to the PREVIOUS one.
            st = state
            d.update({
                "underlying_exposure_applies": st.underlying_exposure_applies(
                    sid, str(d.get("effective_date")), as_of) if sid else None,
                "claim_interest_applies": st.claim_interest_applies(
                    sid, str(d.get("effective_date"))) if sid else None,
                "holding_spells": [(sp.start, sp.end or "OPEN")
                                   for sp in st.holding_spells
                                   if sp.stock_id == sid],
                "tradable_shares": int(dict(st.shares).get(sid, 0)) if sid else None,
            })
            jsonl("failure_record.jsonl", {
                "run_id": run_id, "classification": "F-CA-B",
                "blocker_kind": "historical_reconstruction_or_evaluability",
                "period": period["decision_month"], "seq": i, **d})
            print("BLOCK F-CA-B at %s: %s" % (period["decision_month"], exc))
            terminate("DIAGNOSTIC_NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK",
                      done, {"classification": "F-CA-B",
                             "blocker_kind":
                                 "historical_reconstruction_or_evaluability",
                             "period": period["decision_month"], "seq": i,
                             "reason": str(exc), **d})
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
                             "blocker_kind":
                                 "implementation_conformance_or_invariant",
                             "period": period["decision_month"], "seq": i,
                             "error_type": type(exc).__name__, "error": str(exc)})
            return 3
        if i % 10 == 0:
            print("  %3d/141  %s  positions=%d  ca_applied=%d"
                  % (i, period["decision_month"], len(s.shares_after),
                     len(tr.applied_event_ids)), flush=True)

    if done != EXPECT["periods"]:                       # defensive, unreachable
        raise DiagnosticAbort("loop ended at %d/141 without a blocker" % done)

    write_provenance_json(os.path.join(out, "nav_series.json"), nav_series)

    # --- 141/141. Performance and gates are now REQUIRED. --------------------
    metrics = performance(nav_series, opening_cash)
    bench = build_benchmark(manifest)
    metrics["benchmark"] = bench
    g1 = metrics["terminal_wealth"] > bench["terminal_wealth"]
    g2 = metrics["cagr"] is not None and metrics["cagr"] > 0
    g3 = metrics["sharpe_0rf"] is not None and metrics["sharpe_0rf"] > 0
    metrics["gates"] = {
        "gate_1_net_cumulative_wealth_gt_0050": bool(g1),
        "gate_2_net_cagr_gt_0": bool(g2),
        "gate_3_net_sharpe_0rf_gt_0": bool(g3),
        "all_three": bool(g1 and g2 and g3),
        "verdict_note": ("Gate arithmetic only. This is "
                         "RETROSPECTIVE_SUPPORTING_ONLY evidence: it is not an "
                         "L2 result and confers no L2 verdict."),
    }
    write_provenance_json(os.path.join(out, "performance.json"), metrics)

    print("\n== PERFORMANCE (141/141, authorized) ==", flush=True)
    print("  strategy terminal wealth   %.2f  (x%.4f, %+.2f%%)"
          % (metrics["terminal_wealth"], metrics["wealth_multiple"],
             100 * metrics["cumulative_return"]), flush=True)
    print("  0050 terminal wealth       %.2f  (x%.4f, %+.2f%%)"
          % (bench["terminal_wealth"], bench["wealth_multiple"],
             100 * bench["cumulative_return"]), flush=True)
    print("  CAGR                       %.4f%%" % (100 * metrics["cagr"]), flush=True)
    print("  Sharpe_0rf                 %.4f" % metrics["sharpe_0rf"], flush=True)
    print("  MDD                        %.4f%%" % (100 * metrics["mdd"]), flush=True)
    print("  Gate 1 / 2 / 3             %s / %s / %s"
          % ("PASS" if g1 else "FAIL", "PASS" if g2 else "FAIL",
             "PASS" if g3 else "FAIL"), flush=True)

    terminate("DIAGNOSTIC_COMPLETED_141_OF_141", done,
              {"classification": "COMPLETE", "blocker_kind": None},
              nav_rows=nav_series, metrics=metrics)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DiagnosticAbort as exc:
        print("\nABORT: %s" % exc, flush=True)
        sys.exit(4)
