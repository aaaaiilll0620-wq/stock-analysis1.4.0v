# -*- coding: utf-8 -*-
"""The L3 PROSPECTIVE route runner. One invocation, one decision period.

WHY THIS IS A NEW FILE AND NOT AN EDIT

`research/b0_7_diagnostic/run_b0_7_diagnostic.py` is pinned: its own sha256 is
recorded inside the `final_result.json` of the run it already completed, so its
bytes are evidence. Adding an L3 mode to it would invalidate that record. The
L3 runner is therefore a separate harness that IMPORTS nothing from it and
re-implements no strategy semantics -- every feature, filter, score, target,
order and cost happens behind `run_decision`, and every corporate action
happens behind `core.b0_corporate_actions`, exactly as in L2.

ONE INVOCATION = ONE PERIOD, AND THAT IS STRUCTURAL

`l3_snapshot.write_receipt` claims `l3_snapshot_receipt.json` with O_EXCL, so a
run directory certifies exactly one decision date. A forward track is therefore
a SEQUENCE of run directories, and what carries it from one to the next is the
portfolio checkpoint -- which is precisely the hand-off
`research/b0_checkpoint/portfolio_checkpoint.py` was written for and had no
caller for. Run N's `portfolio_checkpoint.jsonl` is run N+1's `--opening-checkpoint`.

There is no replay here and there cannot be one. A checkpoint is never an
admissible starting state for a REPLAY (a sealed replay is a from-period-1
deterministic re-execution); it is only ever admissible as the opening state of
a FORWARD track, which is what this runner drives.

THREE MODES, AND WHY THE DEFAULT IS THE HARMLESS ONE

    preflight   verify and print. Writes nothing, claims nothing.
    assemble    build both halves of the period and write the receipts. The
                decision layer is NOT invoked: `build_decision_input` produces
                the `CanonicalDecisionInput` and stops there. This is the mode
                that proves the portfolio side works without deciding anything.
    execute     the above, then `run_decision`, then portfolio[t+1] and its
                checkpoint row.

`assemble` and `execute` are alternatives, not a sequence: both write the
snapshot receipt, `write_receipt` claims it with O_EXCL, and a period is
observed once. Running `assemble` first and `execute` afterwards in the same
run directory therefore aborts at the receipt -- which is the intended answer,
not an inconvenience. Re-deciding a period is a NEW run.

`execute` is refused unless `assert_route_execution_admissible()` passes. That
function is not a courtesy flag: the first execution of the L3 strategy route
produces the first prospective observation this project has, and it may not
happen while the specification it would be executed under is mid-transaction.
It is mechanical on both halves, and both are currently expected to be RED:

    SPECIFICATION   `closure_transaction_state()` -- the Master document, the
                    normative module set and `master_prereg_freeze.json` must
                    agree.
    ROUTE           `l3_route_seal` -- `route_closure` must declare nothing
                    still owed, a seal must content-bind the COMPLETE A2 route
                    (not just the `core.*` decision closure), the working tree
                    must still hash to it, and the run's source aggregate must
                    name that same seal rather than a placeholder such as
                    `PENDING`.

WHAT THIS RUNNER DOES NOT DECIDE

  * `price_span` / `bonus_window`. Both move the state hash. Exactly one span
    argument exists per assembly contract, and an argument belonging to the
    OTHER contract is refused by name rather than ignored -- see
    `resolve_spans`.
  * the opening state. It comes from a checkpoint, under one of two explicit
    contracts (`--opening-kind GENESIS|CONTINUATION`), or the run aborts. A
    continuation must name its whole lineage -- producer run, period, seq, row
    hash and file hash -- and a genesis must be A1's registered cohort.
  * whether the run is sealed evidence. `--sealed-evidence` is an explicit
    declaration with no default, mirroring `run_decision(for_sealed_run=...)`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import b0_finalization_items as fin_items                # noqa: E402
from core import b0_l3_run_layout as layout                        # noqa: E402
from core import b0_open_items as open_items                       # noqa: E402
from core.b0_canonical_hash import canonical_sha256, file_sha256   # noqa: E402
from core.b0_declaration_conformance import (                      # noqa: E402
    assert_declarations_conform,
)
from core.b0_master_prereg import (                                # noqa: E402
    NORMATIVE_MODULES, append_provenance_record, normative_module_hashes,
    spec_document_sha256, write_provenance_json,
)
from core.b0_state import SourceAttestation                        # noqa: E402

import l3_route_seal as rs                                          # noqa: E402

from research.b0_checkpoint import portfolio_side as ps            # noqa: E402

RUN_KIND = "B0_L3_PROSPECTIVE"
HARNESS_PATH = "research/b0_l3_runner/run_l3_prospective.py"
MODES = ("preflight", "assemble", "execute")

MASTER_DOC = os.path.join(REPO, "docs", "FrozenB0_MasterPreregistration.md")
FREEZE = os.path.join(REPO, "research", "b0_registry", "master_prereg_freeze.json")

# The gate's name, so a refusal can be quoted rather than paraphrased.
ROUTE_EXECUTION_GATE = "L3_PROSPECTIVE_ROUTE_FIRST_EXECUTION"

OPENING_RECORD = "l3_opening_record.json"
PORTFOLIO_RECEIPT = "l3_portfolio_side_receipt.json"
PERIOD_PROGRESS = "period_progress.jsonl"
CA_LEDGER = "ca_transition_ledger.jsonl"
FAILURE_RECORD = "failure_record.jsonl"
FINAL_RESULT = "final_result.json"

_VERSION_RE = re.compile(r"\*\*(?:版本|Version)\s*[:：]\*\*\s*([0-9]+\.[0-9]+)")


class L3RunAbort(RuntimeError):
    """Stop before the period, or stop the period. Never repair and continue."""


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _require(ok, label, detail="") -> dict:
    if not ok:
        raise L3RunAbort("L3 PREFLIGHT FAILED · %s%s"
                         % (label, (": " + detail) if detail else ""))
    return {"item": label, "status": "PASS", "detail": str(detail)}


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=REPO).stdout.strip()
    except OSError:                                          # pragma: no cover
        return ""


def declared_master_version(path: str = MASTER_DOC) -> str:
    """The version the Master document declares about ITSELF.

    Read from the document rather than from the freeze record, because the
    whole point of the comparison below is that the two can disagree -- and
    they do, during a closure transaction.
    """
    with open(path, encoding="utf-8") as fh:
        head = fh.read(8192)
    m = _VERSION_RE.search(head)
    if not m:
        raise L3RunAbort(
            "abort: %s does not declare a version in its first 8 KB. A run "
            "cannot bind a specification that will not name itself." % path)
    return m.group(1)


# --- the closure gate ----------------------------------------------------------

def closure_transaction_state() -> dict:
    """Is the Frozen B0 specification currently mid-transaction?

    Every field here is measured, none is asserted. A closure transaction is a
    period in which the Master document, the normative module set and the
    freeze record are deliberately out of step while a ruling lands. Running the
    first prospective decision inside that window would bind an L3 observation
    to a specification identity that does not exist yet -- and an observation is
    not repeatable, so there is no second chance to bind it to the right one.

    The four disagreements this reports are the four that can occur:

      * the document declares a version the freeze record does not pin;
      * the document's bytes are not the bytes the freeze record pins;
      * a normative module's bytes are not the bytes the freeze record pins;
      * the normative module SET has changed size (a module was added by the
        transaction and the freeze record has not adopted it).
    """
    freeze = _load(FREEZE)
    pinned_modules = dict(freeze.get("normative_modules") or {})
    measured = normative_module_hashes()

    module_mismatch = sorted(
        m for m in set(pinned_modules) | set(measured)
        if pinned_modules.get(m) != measured.get(m))
    doc_version = declared_master_version()
    doc_sha = spec_document_sha256()

    state = {
        "freeze_version": str(freeze.get("version", "")),
        "document_version": doc_version,
        "freeze_spec_sha256": str(freeze.get("spec_sha256", "")),
        "document_spec_sha256": doc_sha,
        "version_agrees": str(freeze.get("version", "")) == doc_version,
        "spec_sha_agrees": str(freeze.get("spec_sha256", "")) == doc_sha,
        "normative_modules_pinned": len(pinned_modules),
        "normative_modules_measured": len(measured),
        "normative_module_set_agrees":
            len(pinned_modules) == len(NORMATIVE_MODULES),
        "normative_module_mismatch": module_mismatch,
        "normative_modules_agree": not module_mismatch,
    }
    state["in_transaction"] = not (
        state["version_agrees"] and state["spec_sha_agrees"]
        and state["normative_module_set_agrees"]
        and state["normative_modules_agree"])
    return state


CONTRACT_LINEAGE_FLOOR = "lineage_floor"        # §19 / C-68, spans derived
CONTRACT_EXPLICIT_SPANS = "explicit_spans"      # pre-v1.34, four endpoints
CONTRACT_UNKNOWN = "unknown"


def assembly_span_contract():
    """Which span contract `l3_assemble` is currently on, read from the module.

    This runner sits directly downstream of an assembly that is being re-wired
    by §19 / C-68, and the two contracts take DIFFERENT arguments:

        pre-v1.34   assemble(..., price_span=, bonus_window=)  -- four endpoints
                    supplied by the caller, with `UNREGISTERED_SPAN_DERIVATIONS`
                    published as the assembly's own admission that no rule
                    produced them.
        §19/C-68    assemble(..., lineage_price_floor=)        -- one frozen
                    input, every other endpoint derived by
                    `core.b0_l3_price_span`, and caller-supplied overrides
                    refused.

    The contract is DETECTED rather than assumed, because guessing wrong does
    not fail loudly: `assemble(..., price_span=...)` against the newer signature
    is a TypeError, and a runner pinned to the older one would go on supplying
    endpoints the assembly has stopped accepting. Detection also makes the gate
    below honest -- "the spans have a registered derivation" is then a statement
    about the code that will actually run.
    """
    import inspect

    import l3_assemble as A

    params = inspect.signature(A.assemble).parameters
    if "lineage_price_floor" in params:
        return CONTRACT_LINEAGE_FLOOR
    if "price_span" in params and "bonus_window" in params:
        return CONTRACT_EXPLICIT_SPANS
    return CONTRACT_UNKNOWN


def span_derivation_state() -> dict:
    """Does a PROSPECTIVE decision have a registered span derivation yet?

    On the older contract `l3_assemble` publishes
    `UNREGISTERED_SPAN_DERIVATIONS`, which is the assembly saying, in its own
    words, that `price_span` and `bonus_window` reached it without a rule. §19 /
    C-68 registers the rule in `core.b0_l3_price_span` and replaces that list
    with `SPAN_DERIVATION_AUTHORITY`.

    An unregistered span is admissible for `assemble` -- the receipt names the
    choice. It is not admissible for the FIRST EXECUTION of the route, which is
    why this is a gate input rather than a warning.
    """
    import l3_assemble as A

    contract = assembly_span_contract()
    unregistered = tuple(getattr(A, "UNREGISTERED_SPAN_DERIVATIONS", ()) or ())
    authority = dict(getattr(A, "SPAN_DERIVATION_AUTHORITY", {}) or {})
    try:
        from core import b0_l3_price_span as lsp
        registered_module = True
        floor_rule, applies_to = lsp.FLOOR_RULE, lsp.APPLIES_TO
    except Exception:                                       # noqa: BLE001
        registered_module, floor_rule, applies_to = False, "", ""
    return {
        "assembly_span_contract": contract,
        "assembly_unregistered_span_derivations": list(unregistered),
        "assembly_span_derivation_authority": authority,
        "span_rule_module_present": registered_module,
        "span_floor_rule": floor_rule,
        "span_applies_to": applies_to,
        "spans_have_a_registered_derivation": bool(
            registered_module and contract == CONTRACT_LINEAGE_FLOOR
            and not unregistered),
    }


def assert_route_execution_admissible(aggregate=None, seal_id: str = "") -> list:
    """The gate on the FIRST execution of the L3 strategy route.

    Refuses, with the measured reason, while any of the following holds:

      * the specification is mid-closure-transaction;
      * declaration conformance does not pass;
      * OPEN SPEC ITEMS or OPEN FINALIZATION ITEMS is non-empty;
      * the core decision closure reaches code the seal does not bind;
      * `price_span` / `bonus_window` still have no registered prospective
        derivation;
      * `route_closure` still declares items owed before a seal may be taken;
      * no route seal is named, the named seal does not content-bind the
        current working tree, or the run's source aggregate names a different
        seal (or a placeholder such as `PENDING`).

    None of these is a property of this runner. They are properties of the
    specification and the route the run would be executed under, which is the
    point: a prospective observation happens once, and the identity it binds
    has to exist before it happens.
    """
    checks = []
    tx = closure_transaction_state()
    checks.append(_require(
        not tx["in_transaction"],
        "%s · specification is not mid-closure-transaction" % ROUTE_EXECUTION_GATE,
        "doc v%s / freeze v%s; spec_sha agrees=%s; modules pinned=%d measured=%d "
        "mismatched=%d" % (tx["document_version"], tx["freeze_version"],
                           tx["spec_sha_agrees"], tx["normative_modules_pinned"],
                           tx["normative_modules_measured"],
                           len(tx["normative_module_mismatch"]))))

    try:
        assert_declarations_conform()
    except Exception as exc:                                # noqa: BLE001
        raise L3RunAbort("L3 PREFLIGHT FAILED · %s · declaration conformance: %s"
                         % (ROUTE_EXECUTION_GATE, exc)) from exc
    checks.append(_require(True, "declaration conformance = 0 failures"))

    checks.append(_require(len(open_items.unspecified_keys()) == 0,
                           "OPEN SPEC ITEMS = 0",
                           str(open_items.unspecified_keys())))
    checks.append(_require(len(fin_items.open_keys()) == 0,
                           "OPEN FINALIZATION ITEMS = 0",
                           str(fin_items.open_keys())))

    from route_closure import assert_closure_is_wholly_normative

    closure = assert_closure_is_wholly_normative()
    checks.append(_require(True, "core decision closure is wholly normative",
                           "%d modules" % len(closure)))

    spans = span_derivation_state()
    checks.append(_require(
        spans["spans_have_a_registered_derivation"],
        "%s · price_span / bonus_window have a registered derivation"
        % ROUTE_EXECUTION_GATE,
        "assembly contract=%s; still unregistered: %s"
        % (spans["assembly_span_contract"],
           spans["assembly_unregistered_span_derivations"] or "none")))

    # --- A2: the WHOLE replayable route, not the decision core -----------------
    # `assert_closure_is_wholly_normative` above covers `core.*` reached from
    # the two adapter entry points. A2 ruled the closure is the whole replayable
    # route, and everything between a declared source file and `run_decision` --
    # the readers, the assembly, the snapshot, the run layout, the checkpoint,
    # the portfolio side and this runner -- sits outside it. A gate that stopped
    # at the core would let the first prospective observation bind the code that
    # DECIDES while leaving unbound every line that decides what it SEES.
    # `l3_route_seal` raises `RouteSealError`, which is NOT this runner's abort
    # type. Every other refusal in this function is an `L3RunAbort` naming
    # ROUTE_EXECUTION_GATE, and `main()` reports that as a clean preflight
    # refusal; a foreign type escapes as a traceback instead, and the gate name
    # -- the only thing that tells an operator WHICH gate stopped them -- never
    # reaches the message. Unreachable at this runner's original base, where the
    # closure-transaction checks above aborted first; reachable from v1.37, where
    # they pass.
    try:
        seal_payload = rs.assert_route_is_sealable()
    except rs.RouteSealError as exc:
        raise L3RunAbort("L3 PREFLIGHT FAILED · %s · route is not sealable: %s"
                         % (ROUTE_EXECUTION_GATE, exc)) from exc
    checks.append(_require(
        True, "%s · route_closure declares nothing still owed"
        % ROUTE_EXECUTION_GATE,
        "core closure %d modules" % seal_payload["code_closure_size"]))
    seal_id = str(seal_id or "").strip()
    if not seal_id:
        raise L3RunAbort(
            "L3 PREFLIGHT FAILED · %s · no route seal named. An execution must "
            "name the seal that content-binds the complete A2 route "
            "(--route-seal-id); there is no default and no 'latest'."
            % ROUTE_EXECUTION_GATE)
    try:
        seal = rs.load_route_seal(seal_id)
        verified = rs.assert_seal_binds_current_route(seal)
    except rs.RouteSealError as exc:
        raise L3RunAbort("L3 PREFLIGHT FAILED · %s · route seal %s does not "
                         "bind this working tree: %s"
                         % (ROUTE_EXECUTION_GATE, seal_id[:16], exc)) from exc
    checks.append(_require(
        True, "%s · route seal binds the current working tree"
        % ROUTE_EXECUTION_GATE,
        "%s · %d files" % (seal_id[:16], verified["verified_files"])))
    try:
        rs.assert_aggregate_names_this_seal(aggregate, seal_id)
    except rs.RouteSealError as exc:
        raise L3RunAbort("L3 PREFLIGHT FAILED · %s · the source aggregate does "
                         "not name this route seal: %s"
                         % (ROUTE_EXECUTION_GATE, exc)) from exc
    checks.append(_require(
        True, "%s · source aggregate names this route seal"
        % ROUTE_EXECUTION_GATE, str(aggregate.get("route_seal_id"))[:16]))
    return checks


# --- preflight ------------------------------------------------------------------

def resolve_run_directory(run_id: str, run_dir: str = "") -> str:
    """The one directory this period may write into. Never created here.

    W7B5: only `create_run_dir` claims a run directory. A runner that could
    create one is a runner that can silently start a second run under the same
    identity.
    """
    if run_dir:
        directory = os.path.abspath(run_dir)
        layout.assert_not_creating_run_dir(directory)
        if not os.path.isdir(directory):
            raise L3RunAbort(
                "abort: %s does not exist. The run directory is claimed by the "
                "source harvest (create_run_dir), not by this runner." % directory)
        return directory
    return layout.assert_run_dir_exists(run_id)


LEGACY_SPAN_ARGS = ("price_span_from", "price_span_to", "bonus_window_from",
                    "bonus_window_to")


def resolve_spans(args, *, as_of: str, execution_date: str,
                  contract: str = "") -> dict:
    """The one span argument the contract in force takes. Never a default.

    `as_of` and `execution_date` are the RESOLVED ones from `l3_snapshot.plan`,
    which is why this runs after the plan and not in the argument parser: §6.6
    can move as_of back across a month boundary, and a span derived from the
    decision date instead would be a span for a different day.

    Every argument that does not belong to the contract in force is REFUSED BY
    NAME. Ignoring one is worse than refusing it: the caller believes it
    supplied a decision input, the run proceeds on an endpoint nobody asked
    for, and nothing in the receipt says the two differ. The two §19 "hint"
    arguments this runner used to accept (`--earliest-month-end-session`,
    `--observed-price-floor`) are gone entirely -- under §19 the assembly reads
    both off the calendar and the declared sources, and a caller-supplied
    answer to either is exactly the override §19 refuses.
    """
    contract = contract or assembly_span_contract()
    supplied = [n for n in LEGACY_SPAN_ARGS if getattr(args, n, "")]

    if contract == CONTRACT_LINEAGE_FLOOR:
        if supplied:
            raise L3RunAbort(
                "abort: this assembly is on the §19 / C-68 contract, where "
                "price_span and bonus_window are DERIVED and a caller-supplied "
                "override is refused. Remove: %s. Pass --lineage-price-floor "
                "only." % ", ".join("--" + n.replace("_", "-")
                                    for n in supplied))
        if not args.lineage_price_floor:
            raise L3RunAbort(
                "abort: --lineage-price-floor is required and has no default. "
                "It is captured ONCE at lineage inception and is then a "
                "constant of that lineage; it sets the listing spells and "
                "therefore the state hash, so a floor picked at call time is a "
                "state-hash decision nobody ruled on. See "
                "core.b0_l3_price_span.capture_lineage_floor.")
        return {
            "source": "core.b0_l3_price_span (derived inside l3_assemble)",
            "assembly_span_contract": contract,
            "lineage_price_floor": str(args.lineage_price_floor),
        }

    if contract == CONTRACT_EXPLICIT_SPANS:
        if args.lineage_price_floor:
            raise L3RunAbort(
                "abort: --lineage-price-floor belongs to the §19 / C-68 "
                "contract, and this assembly is still on the one that takes "
                "four explicit endpoints. It would be ignored, and an ignored "
                "span argument is a decision input the caller believes it "
                "supplied.")
        missing = [n for n in LEGACY_SPAN_ARGS if not getattr(args, n, "")]
        if missing:
            raise L3RunAbort(
                "abort: this assembly takes four explicit span endpoints and "
                "%d of them %s missing (%s). They have no default, for the "
                "reason l3_assemble states: both spans move the state hash and "
                "the frozen spec derives them only for L2's 141-period panel."
                % (len(missing), "is" if len(missing) == 1 else "are",
                   ", ".join("--" + n.replace("_", "-") for n in missing)))
        if str(args.price_span_to) < str(execution_date):
            raise L3RunAbort(
                "abort: --price-span-to is %s but §6.5 executes at the open of "
                "%s. A span that stops before the execution session cannot "
                "price the trade the decision authorises."
                % (args.price_span_to, execution_date))
        return {
            "source": "explicit_caller_declaration",
            "assembly_span_contract": contract,
            "price_span": (args.price_span_from, args.price_span_to),
            "bonus_window": (args.bonus_window_from, args.bonus_window_to),
            "resolved_as_of": str(as_of),
            "resolved_execution_date": str(execution_date),
        }

    raise L3RunAbort(
        "abort: l3_assemble.assemble takes neither `lineage_price_floor` nor "
        "`price_span`/`bonus_window`. The span contract this runner sits "
        "downstream of has changed again, and guessing which argument to pass "
        "would be guessing at a decision input.")



def preflight(args) -> tuple:
    """Verify, then refuse or proceed. There is no repair path."""
    checks = []
    if not str(args.authorization or "").strip():
        raise L3RunAbort("an L3 period requires a named authorization")
    checks.append(_require(args.mode in MODES, "mode is one of %s" % (MODES,),
                           args.mode))
    # `--route-seal-id` is read ONLY by `assert_route_execution_admissible`,
    # which only `--mode execute` calls. Outside execute it was recorded in
    # `_provenance` and otherwise ignored, while `S.build_receipt` fell back to
    # the aggregate's own id -- so one run could carry two different seal
    # identities and nothing raised. Refused here for the reason `resolve_spans`
    # gives about span endpoints: an ignored argument is a decision input the
    # caller believes it supplied.
    if args.mode != "execute" and str(args.route_seal_id or "").strip():
        raise L3RunAbort(
            "abort: --route-seal-id is an execute-mode input, and --mode %s "
            "does not reach the route seal gate. A seal id supplied to a mode "
            "that ignores it reads as bound in the provenance and binds "
            "nothing." % args.mode)

    directory = resolve_run_directory(args.run_id, args.run_dir)
    checks.append(_require(True, "run directory resolved",
                           os.path.basename(directory)))

    from source_ownership_manifest import assert_ready, verify_aggregate

    aggregate = verify_aggregate(directory)
    assert_ready(aggregate)
    checks.append(_require(aggregate["run_id"] == args.run_id,
                           "source aggregate names this run",
                           str(aggregate["run_id"])))
    checks.append(_require(True, "declared source set is READY",
                           "%d families" % len(aggregate["required_datasets"])))

    checks.append(_require(os.path.exists(args.opening_checkpoint),
                           "opening checkpoint present",
                           str(args.opening_checkpoint)))

    tx = closure_transaction_state()
    spans_state = span_derivation_state()
    # Reported at every mode, gating only at `execute`. A preflight that hid the
    # transaction until somebody asked to execute would be a preflight that
    # tells you least when it matters most.
    checks.append({
        "item": "%s · closure transaction" % ROUTE_EXECUTION_GATE,
        "status": "OPEN" if tx["in_transaction"] else "PASS",
        "detail": "doc v%s / freeze v%s" % (tx["document_version"],
                                            tx["freeze_version"])})
    checks.append({
        "item": "%s · span derivation" % ROUTE_EXECUTION_GATE,
        "status": ("PASS" if spans_state["spans_have_a_registered_derivation"]
                   else "OPEN"),
        "detail": "assembly contract=%s; still unregistered: %s"
                  % (spans_state["assembly_span_contract"],
                     spans_state["assembly_unregistered_span_derivations"]
                     or "none")})
    try:
        rs.assert_route_is_sealable()
        sealable, why = True, "route_closure declares nothing owed"
    except Exception as exc:                                # noqa: BLE001
        # Deliberately broad: this line REPORTS, it does not gate. `seal_payload`
        # also runs the closure and inventory assertions, which raise
        # `RouteClosureError`, and a reporting line that crashed the preflight
        # would hide every other check below it. The gate itself
        # (`assert_route_execution_admissible`) lets the same exception through.
        sealable = False
        why = "%s: %s" % (type(exc).__name__, str(exc).splitlines()[0])
    checks.append({
        # SEALABILITY only: `assert_route_is_sealable` means `route_closure`
        # declares nothing owed. It does NOT mean a seal exists, nor that one
        # binds this route -- `assert_seal_binds_current_route` is reached only
        # from the execute gate below.
        "item": "%s · A2 route seal (sealability only)" % ROUTE_EXECUTION_GATE,
        "status": "PASS" if sealable else "OPEN",
        "detail": "%s; aggregate route_seal_id=%r"
                  % (why[:90], aggregate.get("route_seal_id"))})

    if args.mode == "execute":
        checks += assert_route_execution_admissible(aggregate, args.route_seal_id)
        if args.sealed_evidence is None:
            raise L3RunAbort(
                "abort: --sealed-evidence / --no-sealed-evidence must be "
                "declared for an execution. Whether a run may produce sealed "
                "evidence is a declaration, never an inference "
                "(run_decision(for_sealed_run=...)).")
    return checks, directory, aggregate, tx, spans_state


# --- the period ------------------------------------------------------------------

def _attestation(aggregate: dict, synthetic: bool) -> SourceAttestation:
    """B-21 §8.6: the run's own source identity, not a borrowed one.

    `provenance_sha256` is the aggregate's self-hash, which transitively covers
    every leaf and every declared file of THIS run. Reusing L2's sealed dataset
    id here would attest to a corpus this period did not read.
    """
    from source_ownership_manifest import SELF_HASH_FIELD

    return SourceAttestation(
        dataset_id="l3_source_ownership_%s" % aggregate["run_id"],
        provenance_sha256=str(aggregate[SELF_HASH_FIELD]),
        pit_guard_passed=True, universe_guard_passed=True,
        satisfied_blocking_requirements=("price_universe_survivorship",),
        synthetic=bool(synthetic))


def build_period(directory: str, run_id: str, decision_date: str, spans: dict,
                 opening_checkpoint: str, *, opening_kind: str,
                 c_ref: float = 0.0, producer_run_id: str = "",
                 expect_opening_period: str = "",
                 expect_opening_seq: int = 0,
                 expect_opening_sha256: str = "",
                 expect_handoff_sha256: str = "",
                 expect_checkpoint_file_sha256: str = "",
                 synthetic_sources: bool = False) -> dict:
    """Both halves of one period, and the `CanonicalDecisionInput` they make.

    The decision layer is NOT invoked here. This function ends one call short of
    it on purpose: everything below is source handling and state construction,
    and it must be possible to verify all of it without producing an
    observation.
    """
    import l3_assemble as A

    contract = assembly_span_contract()
    if contract == CONTRACT_LINEAGE_FLOOR:
        assembled = A.assemble(
            directory, run_id, decision_date,
            lineage_price_floor=spans["lineage_price_floor"])
    elif contract == CONTRACT_EXPLICIT_SPANS:
        assembled = A.assemble(directory, run_id, decision_date,
                               price_span=tuple(spans["price_span"]),
                               bonus_window=tuple(spans["bonus_window"]))
    else:
        raise L3RunAbort(
            "abort: l3_assemble.assemble takes neither `lineage_price_floor` "
            "nor `price_span`/`bonus_window`. The span contract this runner "
            "sits downstream of has changed again and guessing which arguments "
            "to pass would be guessing at a decision input.")
    period = assembled["period"]
    as_of, exec_date = str(period["as_of"]), str(period["execution_date"])

    # The REALISED endpoints, read back from the assembly rather than from what
    # the caller asked for. Under §19 the caller never named them, and even on
    # the older contract the assembly is the thing that actually used them --
    # so this is the only pair `load_events` may be keyed on.
    realised = {"price_span": tuple(assembled["price_span"]),
                "bonus_window": tuple(assembled["bonus_window"])}

    from l3_readers import read_calendar

    sessions = tuple(read_calendar(directory))

    opening, opening_prov = ps.opening_state(
        opening_checkpoint, kind=opening_kind, c_ref=float(c_ref or 0.0),
        producer_run_id=producer_run_id,
        expect_period=expect_opening_period,
        expect_seq=int(expect_opening_seq or 0),
        expect_checkpoint_sha256=expect_opening_sha256,
        expect_handoff_sha256=expect_handoff_sha256,
        expect_file_sha256=expect_checkpoint_file_sha256)

    # ONE event universe, read once and used by both consumers. Building it
    # twice is how the transition engine and the delivery carrier end up
    # answering from two different sets, which is the disagreement B0.7 · R10
    # closed.
    events_by_sid = ps.load_events(directory,
                                   bonus_window=realised["bonus_window"],
                                   sessions=sessions)
    redated, tr = ps.transition(opening, as_of=as_of, sessions=sessions,
                                events_by_sid=events_by_sid,
                                period=str(period["decision_month"]))
    side = ps.build_portfolio_side(assembled, tr.state, sessions=sessions,
                                   events_by_sid=events_by_sid)
    side = ps.with_transition_ledger(side, tr)

    aggregate = assembled["period"]["aggregate"]
    attestation = _attestation(aggregate, synthetic_sources)
    market_sources, exec_px, untradable = A.build_production_sources(
        assembled, directory, attestation)
    sources = ps.complete_sources(market_sources, side)
    decision_input = A.build_decision_input(assembled, sources, side.state,
                                            exec_px, untradable)
    return {
        "assembled": assembled,
        "assembly_span_contract": contract,
        "realised_spans": realised,
        "period": period,
        "as_of": as_of,
        "execution_date": exec_date,
        "sessions": sessions,
        "opening_state": opening,
        "opening_provenance": opening_prov,
        "redated": redated,
        "transition": tr,
        "side": side,
        "sources": sources,
        "execution_prices": exec_px,
        "untradable": untradable,
        "decision_input": decision_input,
        "portfolio_side_payload": ps.portfolio_side_payload(side),
        "decision_layer_invoked": False,
    }


def write_period_receipts(directory: str, run_id: str, built: dict, spans: dict,
                          provenance: dict) -> dict:
    """The snapshot receipt (market side) and the portfolio-side receipt.

    Two receipts, not one merged object, because the two halves are hashed
    separately: `assert_market_state_is_portfolio_free` and
    `assert_portfolio_side_is_market_free` are the same rule read from either
    end, and a single blended payload would make both unenforceable.
    """
    import l3_snapshot as S

    layout.assert_not_creating_run_dir(directory)
    receipt = S.build_receipt(directory, run_id,
                              str(built["period"]["decision_date"]),
                              assembled=built["assembled"])
    S.assert_snapshot_complete(receipt)
    receipt_sha = S.write_receipt(directory, receipt)

    payload = built["portfolio_side_payload"]
    portfolio_receipt = {
        "contract_version": ps.PORTFOLIO_SIDE_CONTRACT_VERSION,
        "run_id": run_id,
        "run_kind": RUN_KIND,
        "decision_date": str(built["period"]["decision_date"]),
        "as_of": built["as_of"],
        "execution_date": built["execution_date"],
        "opening": built["opening_provenance"],
        # What the caller DECLARED and what the assembly actually USED, side by
        # side. Under §19 the caller declares only the lineage floor, so the two
        # are not the same object and a receipt carrying only one of them cannot
        # be audited.
        "spans_declared": {k: list(v) if isinstance(v, (list, tuple)) else v
                           for k, v in spans.items()},
        "spans_realised": {k: list(v)
                           for k, v in built["realised_spans"].items()},
        "assembly_span_contract": built["assembly_span_contract"],
        "portfolio_side_sha256": canonical_sha256(payload),
        "portfolio_side": payload,
        "transition": {
            "applied_ca_event_ids": list(built["side"].applied_ca_event_ids),
            "ledger_rows": len(built["side"].transition_ledger),
            "claim_only_securities": list(built["side"].claim_only_securities),
            "held_without_market_row":
                list(built["side"].held_without_market_row),
        },
        "market_state_sha256": built["assembled"]["market_state_sha256"],
        "snapshot_receipt_sha256": receipt_sha,
        "decision_layer_invoked": False,
        "performance_computed": False,
        "evidence_class": "NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED",
        "provenance": provenance,
    }
    write_provenance_json(os.path.join(directory, PORTFOLIO_RECEIPT),
                          portfolio_receipt)
    write_provenance_json(os.path.join(directory, OPENING_RECORD), {
        "record": "B0_L3_OPENING_RECORD",
        "run_id": run_id,
        "run_kind": RUN_KIND,
        **built["opening_provenance"],
    })
    for row in built["side"].transition_ledger:
        append_provenance_record(
            os.path.join(directory, CA_LEDGER),
            json.loads(json.dumps({"run_id": run_id, **row}, default=str)))
    return portfolio_receipt


# --- entry point -----------------------------------------------------------------

def _provenance(args, directory, aggregate, tx, spans_state, spans) -> dict:
    return {
        "record": "B0_L3_PROSPECTIVE_RUN_PROVENANCE",
        "run_id": args.run_id,
        "run_kind": RUN_KIND,
        "mode": args.mode,
        "authorization": args.authorization,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit_sha": _git("rev-parse", "HEAD"),
        "harness_path": HARNESS_PATH,
        "harness_sha256": file_sha256(os.path.abspath(__file__)),
        "portfolio_side_contract": ps.PORTFOLIO_SIDE_CONTRACT_VERSION,
        "run_directory": os.path.abspath(directory).replace("\\", "/"),
        "source_run_id": aggregate["run_id"],
        "required_datasets": list(aggregate["required_datasets"]),
        "closure_transaction": tx,
        "span_derivation": spans_state,
        "spans": {k: list(v) if isinstance(v, (list, tuple)) else v
                  for k, v in spans.items()},
        "sealed_evidence": args.sealed_evidence,
        "route_seal_id": args.route_seal_id,
        "opening_kind": args.opening_kind,
        "aggregate_route_seal_id": aggregate.get("route_seal_id"),
        "normative_module_count": len(NORMATIVE_MODULES),
        "decision_layer_invoked": False,
        "performance_computed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="preflight", choices=list(MODES))
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--run-dir", default="",
                    help="the claimed run directory; defaults to the canonical "
                         "artifacts/l3_run/runs/<run_id>")
    ap.add_argument("--decision-date", required=True)
    ap.add_argument("--authorization", required=True)
    ap.add_argument("--route-seal-id", default="",
                    help="execute only: the seal that content-binds the whole "
                         "A2 route; must equal the source aggregate's "
                         "route_seal_id and may not be a placeholder")
    ap.add_argument("--opening-checkpoint", required=True,
                    help="portfolio_checkpoint.jsonl of the PRECEDING run")
    ap.add_argument("--opening-kind", required=True, choices=list(ps.OPENING_KINDS),
                    help="GENESIS opens a lineage (A1 cohort, --c-ref "
                         "required); CONTINUATION continues one and must name "
                         "the whole hand-off")
    ap.add_argument("--c-ref", type=float, default=0.0,
                    help="GENESIS only: the registered opening cash (A1)")
    ap.add_argument("--producer-run-id", default="",
                    help="CONTINUATION only: the run that WROTE the checkpoint")
    ap.add_argument("--expect-opening-period", default="")
    ap.add_argument("--expect-opening-seq", type=int, default=0)
    ap.add_argument("--expect-opening-sha256", default="",
                    help="CONTINUATION only: checkpoint_sha256 of the terminal row")
    ap.add_argument("--expect-handoff-sha256", default="",
                    help="CONTINUATION only: identity of the terminal ROW "
                         "(run_id + period + seq + state)")
    ap.add_argument("--expect-checkpoint-file-sha256", default="",
                    help="CONTINUATION only: raw sha256 of the whole file")
    # --- span endpoints: one argument per contract, and no third form ---------
    # The four explicit endpoints belong to the pre-v1.34 assembly only;
    # `--lineage-price-floor` belongs to the §19 one. `resolve_spans` refuses
    # any argument that does not belong to the contract in force rather than
    # ignoring it -- an ignored endpoint is a decision input the caller believes
    # it supplied.
    ap.add_argument("--price-span-from", default="")
    ap.add_argument("--price-span-to", default="")
    ap.add_argument("--bonus-window-from", default="")
    ap.add_argument("--bonus-window-to", default="")
    ap.add_argument("--lineage-price-floor", default="",
                    help="§19 contract: the one frozen span input")
    ap.add_argument("--synthetic-sources", action="store_true",
                    help="declare the sources synthetic (fixtures); a sealed "
                         "run may not")
    ap.add_argument("--sealed-evidence", dest="sealed_evidence",
                    action="store_true", default=None)
    ap.add_argument("--no-sealed-evidence", dest="sealed_evidence",
                    action="store_false")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    print("== L3 PROSPECTIVE PREFLIGHT (%s) ==" % args.mode, flush=True)
    checks, directory, aggregate, tx, spans_state = preflight(args)
    for c in checks:
        print("  %-5s %-58s %s" % (c["status"], c["item"], c["detail"]),
              flush=True)
    if args.mode == "preflight":
        print("\npreflight only: nothing claimed, nothing written.", flush=True)
        # NOT a computed admissibility verdict. The previous line here was
        # `not in_transaction and spans_have_a_registered_derivation`, which
        # omits every seal condition `assert_route_execution_admissible`
        # enforces -- so once the closure settled and the spans registered it
        # would print True on a tree where no seal had ever been taken, while
        # `--mode execute` hard-aborts. Preflight reports what it checked.
        still_open = [c["item"] for c in checks
                      if str(c["item"]).startswith(ROUTE_EXECUTION_GATE)
                      and c["status"] != "PASS"]
        print("route execution admissible: NOT EVALUATED IN PREFLIGHT "
              "(only --mode execute runs assert_route_execution_admissible, "
              "which additionally requires a real seal that binds this route)",
              flush=True)
        print("gate preconditions still open: %s"
              % ("; ".join(still_open) if still_open else "none"), flush=True)
        return 0

    # §6.6 resolves as_of BEFORE the spans can be derived from it, so the plan
    # runs first. It writes nothing.
    import l3_snapshot as S

    planned = S.plan(directory, args.run_id, args.decision_date)
    spans = resolve_spans(args, as_of=str(planned["as_of"]),
                          execution_date=str(planned["execution_date"]),
                          contract=spans_state["assembly_span_contract"])
    provenance = _provenance(args, directory, aggregate, tx, spans_state, spans)

    try:
        built = build_period(
            directory, args.run_id, args.decision_date, spans,
            args.opening_checkpoint,
            opening_kind=args.opening_kind, c_ref=args.c_ref,
            producer_run_id=args.producer_run_id,
            expect_opening_period=args.expect_opening_period,
            expect_opening_seq=args.expect_opening_seq,
            expect_opening_sha256=args.expect_opening_sha256,
            expect_handoff_sha256=args.expect_handoff_sha256,
            expect_checkpoint_file_sha256=args.expect_checkpoint_file_sha256,
            synthetic_sources=args.synthetic_sources)
    except Exception as exc:                                # noqa: BLE001
        # The one failure shape this track already knows by name is B0.7's:
        # a corporate action on a held security whose terms are not
        # reconstructible. It is classified rather than lumped in with an
        # implementation fault, because the two mean opposite things about
        # whether the run may be repaired.
        from core.b0_corporate_actions import CorporateActionReconstructionBlock

        block = isinstance(exc, CorporateActionReconstructionBlock)
        append_provenance_record(os.path.join(directory, FAILURE_RECORD), {
            "run_id": args.run_id, "stage": "assemble",
            "decision_date": args.decision_date,
            "classification": "F-CA-B" if block else "F-CA-C-or-core",
            "blocker_kind": ("historical_reconstruction_or_evaluability"
                             if block
                             else "implementation_conformance_or_invariant"),
            "detail": dict(getattr(exc, "detail", {}) or {}),
            "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exc()[-4000:]})
        raise

    receipt = write_period_receipts(directory, args.run_id, built, spans,
                                    provenance)
    print("\nmarket state    %s" % built["assembled"]["market_state_sha256"],
          flush=True)
    print("portfolio side  %s" % receipt["portfolio_side_sha256"], flush=True)
    print("opening         %s (%s, seq %d)"
          % (built["opening_provenance"]["checkpoint_sha256"][:16],
             built["opening_provenance"]["terminal_period"],
             built["opening_provenance"]["terminal_seq"]), flush=True)

    if args.mode == "assemble":
        write_provenance_json(os.path.join(directory, FINAL_RESULT), {
            "record": "B0_L3_PROSPECTIVE_TERMINAL_RESULT",
            "run_id": args.run_id,
            "run_kind": RUN_KIND,
            "terminal_status": "ASSEMBLED_DECISION_LAYER_NOT_INVOKED",
            "terminated_at_utc": datetime.now(timezone.utc).isoformat(),
            "decision_layer_invoked": False,
            "performance_computed": False,
            "evidence_class": "NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED",
            "portfolio_side_sha256": receipt["portfolio_side_sha256"],
            "market_state_sha256": built["assembled"]["market_state_sha256"],
            **{k: provenance[k] for k in
               ("commit_sha", "harness_sha256", "harness_path",
                "closure_transaction", "span_derivation", "spans")},
        })
        print("\nterminal status: ASSEMBLED_DECISION_LAYER_NOT_INVOKED",
              flush=True)
        return 0

    # --- execute -----------------------------------------------------------------
    from core.b0_route import run_decision

    try:
        result = run_decision(built["decision_input"],
                              for_sealed_run=bool(args.sealed_evidence))
        nxt = ps.advance(decision_result=result,
                         transitioned=built["side"].state,
                         as_of=built["as_of"],
                         execution_date=built["execution_date"])
    except Exception as exc:                                # noqa: BLE001
        append_provenance_record(os.path.join(directory, FAILURE_RECORD), {
            "run_id": args.run_id, "stage": "decision",
            "decision_date": args.decision_date,
            "classification": "F-CA-C-or-core",
            "blocker_kind": "implementation_conformance_or_invariant",
            "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exc()[-4000:]})
        write_provenance_json(os.path.join(directory, FINAL_RESULT), {
            "record": "B0_L3_PROSPECTIVE_TERMINAL_RESULT",
            "run_id": args.run_id,
            "run_kind": RUN_KIND,
            "terminal_status": "PERIOD_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE",
            "terminated_at_utc": datetime.now(timezone.utc).isoformat(),
            "decision_layer_invoked": True,
            "performance_computed": False,
            "error_type": type(exc).__name__, "error": str(exc),
            **{k: provenance[k] for k in
               ("commit_sha", "harness_sha256", "harness_path",
                "closure_transaction", "span_derivation", "spans")},
        })
        raise
    rec = ps.append_checkpoint(directory, run_id=args.run_id,
                               period=str(built["period"]["decision_month"]),
                               state=nxt)
    append_provenance_record(os.path.join(directory, PERIOD_PROGRESS), {
        "run_id": args.run_id, "seq": int(rec["seq"]),
        "period": str(built["period"]["decision_month"]),
        "as_of": built["as_of"], "port_value": result.port_value,
        "state_hash": result.state_hash,
        "positions": len(result.session.shares_after),
        "applied_ca_event_ids": list(built["side"].applied_ca_event_ids),
        "post_checkpoint_sha256": rec["checkpoint_sha256"],
        "post_state_hash": rec["ca_state_hash"]})
    write_provenance_json(os.path.join(directory, FINAL_RESULT), {
        "record": "B0_L3_PROSPECTIVE_TERMINAL_RESULT",
        "run_id": args.run_id,
        "run_kind": RUN_KIND,
        "terminal_status": "PERIOD_EXECUTED",
        "terminated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_layer_invoked": True,
        "for_sealed_run": bool(args.sealed_evidence),
        # One period is not a track. A cumulative-wealth number from one
        # decision is a number about a window that has not happened.
        "performance_computed": False,
        "portfolio_side_sha256": receipt["portfolio_side_sha256"],
        "market_state_sha256": built["assembled"]["market_state_sha256"],
        "post_checkpoint_sha256": rec["checkpoint_sha256"],
        **{k: provenance[k] for k in
           ("commit_sha", "harness_sha256", "harness_path",
            "closure_transaction", "span_derivation", "spans")},
    })
    print("\nterminal status: PERIOD_EXECUTED  port_value=%.2f"
          % result.port_value, flush=True)
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    try:
        sys.exit(main())
    except L3RunAbort as exc:
        print("\nABORT: %s" % exc, flush=True)
        sys.exit(4)
