# -*- coding: utf-8 -*-
"""B1 CONFORMANCE DIAGNOSTIC REPLAY. Conformance only — no performance, ever.

THIS IS NOT AN L2 RUN, AND IT IS STRUCTURALLY INCAPABLE OF BECOMING ONE.

  * it never imports `record_opening`, `create_opening_claim`,
    `create_execution_claim` or `create_run_dir`
  * it never writes under `artifacts/l2_run*/` — its entire namespace is
    `artifacts/b1_conformance_diagnostic/`
  * it snapshots Frozen B0's whole L2 artefact tree, both lineages' opening
    accounting and every prior diagnostic's terminal result BEFORE the first
    byte is written, and asserts them unchanged AFTER the terminal record

WHY IT EXISTS

Six diagnostic replays have been run against this window and NOT ONE reached
141 periods: 2, 4, 4, 45, 66, 66. Every one found a blocker further along than
the last, and periods 67..141 have never been executed by anything. B0's
official L2 run terminated at period 2 and consumed the once-only observation
anyway (C-72: the budget is spent by the decision, not by the finish).

B1 has one observation and one only. Opening it to discover a period-67 defect
would spend that budget on a bug. So this answers the one question that decides
whether opening is worth it — DOES THE WINDOW EXECUTE END TO END — and it
answers it without opening anything.

WHAT IS DIFFERENT FROM B0.1 .. B0.7

B0.7 computed and printed performance on 141/141 completion. THIS DOES NOT, at
any completion count, and that is the entire point: a completed B1 replay that
printed a NAV path would BE the observation, and the sealed run afterwards would
be reading an answer someone had already seen.

`run_decision` returns `port_value` because the core computes it. It is never
stored, never aggregated, never printed and never written. That is enforced
rather than intended: every artefact row goes through `_conformance_only`, which
raises on any key outside `PERMITTED_ROW_KEYS`. A future edit that adds
`port_value` to a progress row fails loudly instead of quietly leaking the
answer into a file nobody re-reads.

    WSLENV=B0_MATERIALIZE_LINEAGE B0_MATERIALIZE_LINEAGE=B1 \
        python.exe research/b1_conformance_diagnostic/run_b1_conformance.py \
        --lineage B1
"""
from __future__ import annotations

import argparse
import csv
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
from core.b0_l2_run_layout import (                                # noqa: E402
    LEGACY_RUN_ROOT, composed_market_state_sha256, legacy_artefact_identity,
    lineage_attempted_opening_count, lineage_opening_claims_root,
    lineage_run_root, sha256_of,
)
from core.b0_master_prereg import (                                # noqa: E402
    FROZEN_B0_LINEAGE, REGISTERED_L2_LINEAGES, active_lineage,
    append_provenance_record, assert_declared_lineage,
    effective_observation_count, lineage_data_root, lineage_freeze_path,
    lineage_market_state_dataset_id, lineage_market_state_manifest,
    lineage_registry_path, lineage_seal_archive_root, lineage_spec,
    normative_module_hashes, read_registry, write_provenance_json,
)
from core.b0_route import run_decision                             # noqa: E402
from core.b0_state import PortfolioState                           # noqa: E402

from run_sealed_l2 import (                                        # noqa: E402
    build_input, hxa_anchor_for_run, load_events,
)
from build_period1_full_input import _price_contract, opening_states  # noqa: E402

RUN_KIND = "B1_CONFORMANCE_DIAGNOSTIC"
EVIDENCE_CLASS = "NOT_L3_EVIDENCE__CONFORMANCE_ONLY"

# What this run is allowed to establish, stated so it cannot drift into more.
ESTABLISHES = "whether the frozen window executes end to end, and where it stops"
DOES_NOT_ESTABLISH = (
    "any return, NAV, drawdown, Sharpe, benchmark comparison or gate outcome",
    "any evidence for or against the strategy hypothesis",
    "anything that reduces what the sealed L2 run must still do",
)
PERFORMANCE_COMPUTED = False
GATES_EVALUATED = False
BENCHMARK_BUILT = False

# --- the structural half of "no performance" ---------------------------------
# An allow-list, not a deny-list. A deny-list of forbidden names is a list
# somebody has to remember to extend; this fails closed on anything new.
PERMITTED_ROW_KEYS: frozenset = frozenset({
    "run_id", "seq", "period", "as_of", "state_hash", "post_state_hash",
    "positions", "ca_applied", "claim_only_securities", "classification",
    "blocker_kind", "error", "error_type", "traceback", "reason",
    "security_id", "event_id", "event_kind", "effective_date",
    "underlying_exposure_applies", "claim_interest_applies", "holding_spells",
    "tradable_shares", "missing_fields", "exposure", "last_valid_state_hash",
    "opening_state_hash", "kind", "detail", "lineage",
})
FORBIDDEN_SUBSTRINGS = ("port_value", "nav", "cash", "value", "return",
                        "sharpe", "drawdown", "pnl", "profit", "benchmark",
                        "metric", "performance")


class PerformanceLeak(RuntimeError):
    """A conformance artefact tried to carry a performance quantity."""


class DiagnosticAbort(RuntimeError):
    """Stop before the replay, or stop the replay. Never repair and continue."""


def _conformance_only(row: dict) -> dict:
    """Every artefact row passes through here. Both checks, on purpose.

    The allow-list is the real gate. The substring scan is a second, dumber
    net that catches a permitted-looking key carrying a forbidden quantity
    (`detail` full of NAV, say) before it reaches a file.
    """
    bad = sorted(set(row) - PERMITTED_ROW_KEYS)
    if bad:
        raise PerformanceLeak(
            "conformance-only: %s is not a permitted artefact key. This run may "
            "record WHETHER the window executes and WHERE it stops, and nothing "
            "else. If the key is genuinely conformance evidence, add it to "
            "PERMITTED_ROW_KEYS deliberately." % bad)
    blob = json.dumps(row, ensure_ascii=False, default=str).lower()
    for token in FORBIDDEN_SUBSTRINGS:
        if '"%s"' % token in blob or "'%s'" % token in blob:
            raise PerformanceLeak(
                "conformance-only: a row carries a %r field. Seeing this run's "
                "performance would BE the once-only observation, and the sealed "
                "run afterwards would be reading an answer already seen."
                % token)
    return row


# --- lineage ------------------------------------------------------------------

LINEAGE = active_lineage()

DATA = lineage_data_root(LINEAGE)
MANIFEST = lineage_market_state_manifest(LINEAGE)
FREEZE = lineage_freeze_path(LINEAGE)
SEAL_ARCHIVE = lineage_seal_archive_root(LINEAGE)
REGISTRY = lineage_registry_path(LINEAGE)

DIAG_ROOT = os.path.join(REPO, "artifacts", "b1_conformance_diagnostic")
RUNS_ROOT = os.path.join(DIAG_ROOT, "runs")
CLAIMS_ROOT = os.path.join(DIAG_ROOT, "run_claims")

# Prior diagnostics: snapshotted to prove this run did not touch them, and
# reported so the terminal record says what "further than ever before" means.
PRIOR_DIAGNOSTICS = {
    "b0_1": ("B01DIAG-0121b3261805b826", 2),
    "b0_2": ("B02DIAG-bc7ce018a97cfa0f", 4),
    "b0_4": ("B04DIAG-d5f34a5164a0e309", 4),
    "b0_5": ("B05DIAG-9943d2f7b4adb670", 45),
    "b0_6": ("B06DIAG-055dbf317d3f67ac", 66),
    "b0_7": ("B07DIAG-fb6b6b54381ec4f9", 66),
}
DEEPEST_PRIOR_REPLAY = 66


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=REPO).stdout.strip()


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _require(ok, label, detail=""):
    print("  %-58s %s" % (label, "OK" if ok else "FAIL"), flush=True)
    return {"check": label, "ok": bool(ok), "detail": detail}


# --- what must be unchanged afterwards ---------------------------------------

def lineage_snapshot() -> dict:
    """Both lineages' accounting, plus every byte of B0's L2 artefact tree."""
    files = {}
    for root in (LEGACY_RUN_ROOT, lineage_run_root(LINEAGE)):
        if not os.path.isdir(root):
            continue
        for base, _dirs, names in os.walk(root):
            for n in sorted(names):
                p = os.path.join(base, n)
                sha, size = sha256_of(p)
                files[os.path.relpath(p, REPO).replace("\\", "/")] = {
                    "sha256": sha, "bytes": size}
    accounting = {}
    for name in sorted(REGISTERED_L2_LINEAGES):
        reg = lineage_registry_path(name)
        rows = read_registry(reg) if os.path.exists(reg) else []
        accounting[name] = {
            "attempted_openings": lineage_attempted_opening_count(name),
            "effective_observation_count": (
                effective_observation_count(reg) if os.path.exists(reg) else 0),
            "registry_rows": len(rows),
            "registry_sha256": canonical_sha256(rows),
            "opening_claims_present": os.path.isdir(
                lineage_opening_claims_root(name)),
        }
    diag = {}
    for key, (run_id, periods) in sorted(PRIOR_DIAGNOSTICS.items()):
        fr = os.path.join(REPO, "artifacts", "%s_diagnostic" % key, "runs",
                          run_id, "final_result.json")
        entry = {"run_id": run_id, "periods_executed": periods}
        if os.path.exists(fr):
            entry["final_result_sha256"] = sha256_of(fr)[0]
        diag[key] = entry
    return {
        "l2_artefact_files": files,
        "l2_artefact_tree_sha256": canonical_sha256(files),
        "legacy_pinned_artefacts": legacy_artefact_identity(),
        "accounting": accounting,
        "prior_diagnostics": diag,
    }


def preflight() -> tuple[dict, list]:
    """Everything that must hold before the first byte. Abort, never repair."""
    print("\npreflight", flush=True)
    checks = []

    checks.append(_require(LINEAGE != FROZEN_B0_LINEAGE,
                           "lineage is not Frozen B0", LINEAGE))
    checks.append(_require(REGISTERED_L2_LINEAGES.get(LINEAGE) is True,
                           "lineage is registered and its budget is intact"))

    seal_dir = SEAL_ARCHIVE
    seals = sorted(n for n in os.listdir(seal_dir)) if os.path.isdir(seal_dir) else []
    checks.append(_require(len(seals) >= 1, "a baseline seal exists",
                           "%d archived" % len(seals)))
    ledger = os.path.join(os.path.dirname(seal_dir), "baseline_seal_lineage.jsonl")
    current = None
    if os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    e = json.loads(line)
                    if e.get("state") == "CURRENT":
                        current = e
    checks.append(_require(current is not None, "the seal ledger names a CURRENT seal"))
    seal = _load(os.path.join(seal_dir, current["baseline_seal_sha256"] + ".json")) \
        if current else {}
    checks.append(_require(seal.get("l2_opened") is False,
                           "the current seal records l2_opened = false"))

    freeze = _load(FREEZE)
    checks.append(_require(
        seal.get("specification", {}).get("spec_sha256") == freeze["spec_sha256"],
        "sealed spec identity == frozen spec identity"))

    head = _git("rev-parse", "HEAD")
    checks.append(_require(head == seal.get("commit_sha"),
                           "HEAD is the sealed commit", head[:8]))
    checks.append(_require(not _git("status", "--porcelain"),
                           "working tree is clean"))

    manifest = _load(MANIFEST)
    periods = int(lineage_spec(LINEAGE, "window_months"))
    checks.append(_require(len(manifest) == periods,
                           "manifest periods == frozen window",
                           "%d" % len(manifest)))
    # Against the materializer's own receipt, not against a key the seal does
    # not have. `seal.get("sealed_inputs", {}).get(k, composed)` compared the
    # value with itself and passed unconditionally — a check that cannot fail
    # is worse than no check, because it reads like coverage.
    composed = composed_market_state_sha256(MANIFEST)
    receipt_path = os.path.join(
        REPO, "research", "b0_materializer",
        "market_side_state_receipt%s.json"
        % ("" if LINEAGE == FROZEN_B0_LINEAGE else "_" + LINEAGE.lower()))
    receipt = _load(receipt_path)
    checks.append(_require(
        composed == receipt["composed_market_state_sha256"],
        "composed market state matches the materializer receipt",
        composed[:16]))
    checks.append(_require(
        int(receipt["periods_built"]) == periods,
        "receipt periods_built == frozen window"))

    acct = lineage_snapshot()["accounting"][LINEAGE]
    checks.append(_require(
        acct["attempted_openings"] == 0 and acct["effective_observation_count"] == 0,
        "this lineage has spent nothing yet",
        json.dumps(acct, sort_keys=True)))

    mods = normative_module_hashes()
    checks.append(_require(
        all(mods.get(m) == h for m, h in freeze["normative_modules"].items()),
        "all normative modules match the freeze registry"))

    # The property this whole file exists to guarantee.
    checks.append(_require(PERFORMANCE_COMPUTED is False
                           and GATES_EVALUATED is False
                           and BENCHMARK_BUILT is False,
                           "conformance only: no performance, no gate, no benchmark"))

    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise DiagnosticAbort(
            "preflight failed: %s" % [c["check"] for c in failed])
    return {"seal": current["baseline_seal_sha256"], "freeze": freeze,
            "head": head, "manifest": manifest, "composed": composed,
            "periods": periods}, checks


def claim_run(run_id: str, payload: dict) -> str:
    """O_EXCL, in our own namespace. Never an L2 opening claim."""
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
    os.makedirs(os.path.join(RUNS_ROOT, run_id))       # deliberately NOT exist_ok
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lineage", default="",
                    help="confirm the lineage; this CHECKS, it does not set")
    a = ap.parse_args()
    assert_declared_lineage(a.lineage, LINEAGE)

    print("=" * 78)
    print("%s  (%s)" % (RUN_KIND, LINEAGE))
    print("=" * 78)
    print("establishes     : %s" % ESTABLISHES)
    for line in DOES_NOT_ESTABLISH:
        print("does NOT        : %s" % line)
    print("deepest prior   : %d / 141 (six replays, none reached the end)"
          % DEEPEST_PRIOR_REPLAY)

    bound, checks = preflight()
    manifest, periods = bound["manifest"], bound["periods"]
    snap_before = lineage_snapshot()
    modules_before = normative_module_hashes()

    started = datetime.now(timezone.utc).isoformat()
    run_id = "B1CONF-" + canonical_sha256(
        [RUN_KIND, LINEAGE, bound["seal"], bound["head"], bound["composed"],
         started])[:16]
    claim_path = claim_run(run_id, {
        "run_id": run_id, "run_kind": RUN_KIND, "lineage": LINEAGE,
        "evidence_class": EVIDENCE_CLASS, "started_at_utc": started,
        "baseline_seal_sha256": bound["seal"], "commit_sha": bound["head"],
        "spec_sha256": bound["freeze"]["spec_sha256"],
        "market_state_composed_sha256": bound["composed"],
        "is_l2_opening": False, "performance_computed": PERFORMANCE_COMPUTED,
    })
    out = os.path.join(RUNS_ROOT, run_id)
    print("\nrun_id    : %s" % run_id)
    print("namespace : %s" % os.path.relpath(out, REPO))
    print("claim     : %s\n" % os.path.relpath(claim_path, REPO), flush=True)

    def jsonl(name, row):
        append_provenance_record(
            os.path.join(out, name),
            json.loads(json.dumps(_conformance_only(row), default=str)))

    sessions = tuple(r["session"] for r in csv.DictReader(
        open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8")))
    events_by_sid = load_events()
    # From the SEALED runner, not a copy. The whole value of this diagnostic is
    # that it exercises the path the L2 run will take; a locally-built anchor
    # would be the same mistake the tests made.
    hxa_anchor = hxa_anchor_for_run()
    print("HX-A/CASH anchor resolver: %s"
          % ("supplied" if hxa_anchor is not None else "NONE (Frozen B0)"),
          flush=True)

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
        dataset_id=lineage_market_state_dataset_id(LINEAGE),
        provenance_sha256=bound["freeze"]["spec_sha256"], pit_guard_passed=True,
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
        "opening_state_hash": ca._state_hash(portfolio)})

    def terminate(status, periods_done, detail):
        snap_after = lineage_snapshot()
        untouched = (
            snap_after["l2_artefact_tree_sha256"]
            == snap_before["l2_artefact_tree_sha256"]
            and snap_after["accounting"] == snap_before["accounting"]
            and snap_after["prior_diagnostics"] == snap_before["prior_diagnostics"]
            and snap_after["legacy_pinned_artefacts"]
            == snap_before["legacy_pinned_artefacts"])
        unmodified = normative_module_hashes() == modules_before
        record = {
            "record": "B1_CONFORMANCE_DIAGNOSTIC_TERMINAL_RESULT",
            "run_id": run_id, "run_kind": RUN_KIND, "lineage": LINEAGE,
            "evidence_class": EVIDENCE_CLASS,
            "terminated_at_utc": datetime.now(timezone.utc).isoformat(),
            "baseline_seal_sha256": bound["seal"],
            "commit_sha": bound["head"],
            "spec_sha256": bound["freeze"]["spec_sha256"],
            "market_state_composed_sha256": bound["composed"],
            "status": status,
            "periods_executed": periods_done,
            "periods_required": periods,
            "deepest_prior_replay": DEEPEST_PRIOR_REPLAY,
            "reached_further_than_any_prior_replay":
                periods_done > DEEPEST_PRIOR_REPLAY,
            "window_executes_end_to_end": periods_done == periods,
            "performance_computed": PERFORMANCE_COMPUTED,
            "gates_evaluated": GATES_EVALUATED,
            "benchmark_built": BENCHMARK_BUILT,
            "establishes": ESTABLISHES,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
            "is_l2_opening": False,
            "l2_accounting_untouched": untouched,
            "normative_modules_unmodified": unmodified,
            "accounting_before": snap_before["accounting"],
            "accounting_after": snap_after["accounting"],
            "detail": detail,
        }
        write_provenance_json(os.path.join(out, "final_result.json"), record)
        print("\n" + "=" * 78)
        print("status                  : %s" % status)
        print("periods executed        : %d / %d" % (periods_done, periods))
        print("further than any prior  : %s  (deepest was %d)"
              % (periods_done > DEEPEST_PRIOR_REPLAY, DEEPEST_PRIOR_REPLAY))
        print("performance computed    : %s" % PERFORMANCE_COMPUTED)
        print("L2 accounting untouched : %s" % untouched)
        print("normative code unchanged: %s" % unmodified)
        print("=" * 78, flush=True)
        return record

    done = 0
    for i, period in enumerate(manifest, 1):
        as_of = period["as_of"]
        try:
            state = ca.redate(portfolio, as_of)
            held_events = [e for sid in state.entitlement_securities
                           for e in events_by_sid.get(sid, ())]
            tr = ca.transition_portfolio(state, held_events, as_of=as_of,
                                         sessions=sessions,
                                         period=period["decision_month"],
                                         hxa_anchor=hxa_anchor)
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
            # No port_value, no cash, no NAV row. `positions` is a COUNT: it
            # says the decision layer produced a portfolio, not what it was
            # worth.
            jsonl("period_progress.jsonl", {
                "run_id": run_id, "seq": i, "period": period["decision_month"],
                "as_of": as_of, "state_hash": result.state_hash,
                "positions": len(s.shares_after),
                "ca_applied": list(tr.applied_event_ids),
                "claim_only_securities": list(
                    tr.state.claim_only_securities(as_of)),
                "post_state_hash": ca._state_hash(portfolio)})
            done = i
        except ca.CorporateActionReconstructionBlock as exc:
            d = {k: v for k, v in dict(exc.detail).items()
                 if k in PERMITTED_ROW_KEYS}
            sid = d.get("security_id")
            st = state          # `tr` is unassigned this period; see B0.7
            d.update({
                "underlying_exposure_applies": st.underlying_exposure_applies(
                    sid, str(d.get("effective_date")), as_of) if sid else None,
                "claim_interest_applies": st.claim_interest_applies(
                    sid, str(d.get("effective_date"))) if sid else None,
                "holding_spells": [(sp.start, sp.end or "OPEN")
                                   for sp in st.holding_spells
                                   if sp.stock_id == sid],
            })
            jsonl("failure_record.jsonl", {
                "run_id": run_id, "classification": "F-CA-B",
                "blocker_kind": "historical_reconstruction_or_evaluability",
                "period": period["decision_month"], "seq": i, **d})
            print("BLOCK F-CA-B at %s (seq %d): %s"
                  % (period["decision_month"], i, exc), flush=True)
            terminate("DIAGNOSTIC_BLOCKED_CORPORATE_ACTION_RECONSTRUCTION",
                      done, {"classification": "F-CA-B",
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
            print("FAILURE at %s (seq %d): %s: %s"
                  % (period["decision_month"], i, type(exc).__name__, exc),
                  flush=True)
            terminate("DIAGNOSTIC_IMPLEMENTATION_CONFORMANCE_FAILURE", done,
                      {"classification": "F-CA-C-or-core",
                       "period": period["decision_month"], "seq": i,
                       "error_type": type(exc).__name__, "error": str(exc)})
            return 3
        if i % 10 == 0:
            # Period count and position count only. Never a value.
            print("  %3d/%d  %s  positions=%d"
                  % (i, periods, period["decision_month"],
                     len(s.shares_after)), flush=True)

    terminate("DIAGNOSTIC_WINDOW_EXECUTES_END_TO_END", done,
              {"periods_executed": done,
               "note": "conformance only; no performance was computed or seen"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
