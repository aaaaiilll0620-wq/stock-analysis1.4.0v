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

FOUR MODES, AND WHY THE DEFAULT IS THE HARMLESS ONE

    preflight   verify and print. Writes nothing, claims nothing.
    intent      materialize the decision cut-off and run the canonical scoring
                path, but record no execution, costs, or post-trade state.
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
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

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

from research.b0_checkpoint import portfolio_checkpoint as pc      # noqa: E402
from research.b0_checkpoint import portfolio_side as ps            # noqa: E402
from research.b0_materializer.l3_temporal_snapshot import (        # noqa: E402
    TemporalSnapshotError, assert_append_only_continuity,
)

RUN_KIND = "B0_L3_PROSPECTIVE"
HARNESS_PATH = "research/b0_l3_runner/run_l3_prospective.py"
MODES = ("preflight", "intent", "assemble", "execute")

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
DECISION_INTENT = "decision_intent.json"
PUBLICATION_COMMIT = "publication_commit.json"
SNAPSHOT_RECEIPT = "l3_snapshot_receipt.json"

# L3 prospective capacity cohorts are not Frozen B0's historical C_ref.  They
# are named explicitly because NAV changes the ADV gate and therefore the
# selected population.  A bare number is not an admissible cohort identity.
L3_GENESIS_COHORTS = {
    "L3_PRIMARY_20M": 20_000_000.0,
    "L3_SECONDARY_50M": 50_000_000.0,
}
SYNTHETIC_PARITY_COHORT = "SYNTHETIC_FROZEN_CREF_PARITY"

# The cohorts a CONTINUATION may name. Same identities, plus the fixture one so
# that a synthetic multi-period track is expressible -- a fixture track that
# could not continue would have to be re-genesised every period, which is the
# one shape that hides a crossed checkpoint.
L3_LINEAGE_COHORTS = (*sorted(L3_GENESIS_COHORTS), SYNTHETIC_PARITY_COHORT)

# --- the source-revision stop rule (§1 / §6 of the governing ruling draft) ------
#
# "A later source update is admissible only when the previously captured
#  overlap is byte/semantic-digest identical and the new rows are a strict
#  append. A revision inside the overlap is a stop, not a quiet refresh."
#
# `l3_temporal_snapshot.assert_append_only_continuity` implements exactly that
# and had NO CALLER anywhere in `research/`, `core/` or `tests/` outside its own
# unit test, so on the decision route the rule did not exist. It is wired in
# below over the run's DECLARED SOURCE SET -- the rows of the source-ownership
# leaves -- which is the row set this route actually stands on.
#
# The row is projected to source IDENTITY only. `observed_at` is deliberately
# excluded: it records when THIS run looked at the file, so including it would
# make every comparison fail for a reason that is not a revision.
SOURCE_CONTINUITY_ROW_FIELDS: tuple[str, ...] = (
    "locator", "format", "raw_sha256", "export_vintage", "source_family",
    "authority", "disposition",
)
SOURCE_CONTINUITY_DATE_FIELD = "export_vintage"
SOURCE_CONTINUITY_PRIMARY_KEY: tuple[str, ...] = ("locator",)
NO_SOURCE_BASELINE = "NO_PRIOR_SOURCE_MANIFEST_FIRST_RUN_OF_THIS_LINEAGE"
SOURCE_CONTINUITY_MODES = ("intent", "assemble", "execute")

_VERSION_RE = re.compile(r"\*\*(?:版本|Version)\s*[:：]\*\*\s*([0-9]+\.[0-9]+)")


def _taipei_today() -> date:
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def _assert_intent_claim_is_today(decision_date: str) -> None:
    """A prospective decision may not be pre-dated or back-dated."""
    try:
        claimed = date.fromisoformat(str(decision_date))
    except ValueError as exc:
        raise L3RunAbort("decision date is not ISO YYYY-MM-DD") from exc
    today = _taipei_today()
    if claimed != today:
        raise L3RunAbort(
            "abort: a prospective decision intent may be recorded only on its "
            "actual Asia/Taipei decision date; claimed %s, today is %s. A "
            "future claim invents an observation and a late claim is backdating."
            % (claimed.isoformat(), today.isoformat()))


def _assert_cohort_identity(args) -> dict:
    """The ONE cohort this period belongs to, for either opening contract.

    Cohort identity used to be asserted at GENESIS and then dropped. From
    period 2 the checkpoint carried cash and nothing else, so the two
    registered cells were distinguishable only by the magnitude of that cash --
    and NAV is precisely what sets `core.b0_eligibility.adv_floor(port_value)`,
    so a checkpoint crossed between the cells produces a normal-looking
    decision over a silently different eligible population.

    So both contracts name a cohort, and each names it with its OWN argument:

        GENESIS       `--genesis-cohort` + `--c-ref`. The cash must be the
                      registered cash of that cell; a bare number is not an
                      admissible cohort identity.
        CONTINUATION  `--lineage-cohort`. There is no `--c-ref` to check
                      against -- the cash is whatever executing the previous
                      period produced -- so the declaration is verified against
                      the CHECKPOINT instead, by
                      `portfolio_checkpoint.assert_checkpoint_cohort`.

    One argument per contract and no third form, for the same reason
    `resolve_spans` refuses an endpoint belonging to the other span contract:
    an argument that would be ignored is a decision input the caller believes
    it supplied.
    """
    cohort_id = str(getattr(args, "genesis_cohort", "") or "")
    lineage_cohort = str(getattr(args, "lineage_cohort", "") or "")
    c_ref = float(getattr(args, "c_ref", 0.0) or 0.0)

    if args.opening_kind != ps.OPENING_GENESIS:
        if cohort_id or c_ref:
            raise L3RunAbort(
                "abort: CONTINUATION may not name a genesis cohort or c_ref")
        if not lineage_cohort:
            raise L3RunAbort(
                "abort: CONTINUATION must name the cohort its lineage was "
                "opened under (--lineage-cohort, one of %s). The two "
                "registered cells differ only by opening cash, cash is the "
                "input to adv_floor(port_value), and a continuation that "
                "names no cohort cannot be shown not to have crossed them."
                % sorted(L3_LINEAGE_COHORTS))
        if lineage_cohort not in L3_LINEAGE_COHORTS:
            raise L3RunAbort(
                "abort: --lineage-cohort %r is not a registered cohort: %s"
                % (lineage_cohort, sorted(L3_LINEAGE_COHORTS)))
        if (lineage_cohort == SYNTHETIC_PARITY_COHORT
                and not bool(getattr(args, "synthetic_sources", False))):
            raise L3RunAbort(
                "abort: the Frozen C_ref parity cohort is fixture-only")
        return {"cohort_id": lineage_cohort,
                # The cohort a lineage was BORN into, carried forward. It is
                # the same fact at period 1 and at period 40, which is what
                # makes it admissible as a phase-invariant contract field.
                "genesis_cohort_id": lineage_cohort,
                "opening_cash": 0.0,
                "cohort_source": "declared_and_verified_against_the_checkpoint"}

    if lineage_cohort:
        raise L3RunAbort(
            "abort: --lineage-cohort belongs to the CONTINUATION contract; a "
            "GENESIS opening names --genesis-cohort and --c-ref")
    if cohort_id == SYNTHETIC_PARITY_COHORT:
        # S-4. `core.b0_state` already refuses a synthetic input for a sealed
        # run, so this path cannot reach sealed evidence. It is tightened here
        # anyway, at the layer that hands out cohort identities, because the
        # escape hatch was `expected = c_ref` -- the fixture cohort accepted
        # ANY opening cash, including the registered cash of a real cell.
        if not bool(getattr(args, "synthetic_sources", False)):
            raise L3RunAbort(
                "abort: the Frozen C_ref parity cohort is fixture-only")
        if bool(getattr(args, "sealed_evidence", False)):
            raise L3RunAbort(
                "abort: the Frozen C_ref parity cohort may not open a run "
                "declared as sealed evidence. Fixtures exist to test "
                "mechanics, not to produce evidence "
                "(core.b0_state: a synthetic input may not feed a sealed run).")
        if c_ref <= 0:
            raise L3RunAbort(
                "abort: the Frozen C_ref parity cohort still requires a "
                "positive opening cash; caller named %.2f" % c_ref)
        borrowed = sorted(name for name, cash in L3_GENESIS_COHORTS.items()
                          if float(cash) == c_ref)
        if borrowed:
            raise L3RunAbort(
                "abort: the parity cohort was handed %.2f, which is the "
                "registered opening cash of %s. NAV is the input to "
                "adv_floor(port_value), so a fixture opened at a registered "
                "cell's cash selects that cell's eligible population and every "
                "record it writes is indistinguishable from the real one. A "
                "fixture may not borrow a registered cohort's identity; name "
                "that cohort or use a different opening cash."
                % (c_ref, ", ".join(borrowed)))
        expected = c_ref
    else:
        if cohort_id not in L3_GENESIS_COHORTS:
            raise L3RunAbort(
                "abort: GENESIS must name one registered prospective cohort: %s"
                % sorted(L3_GENESIS_COHORTS))
        expected = L3_GENESIS_COHORTS[cohort_id]
    if c_ref != float(expected) or c_ref <= 0:
        raise L3RunAbort(
            "abort: genesis cohort %s requires opening cash %.2f; caller named %.2f"
            % (cohort_id, expected, c_ref))
    return {"cohort_id": cohort_id, "genesis_cohort_id": cohort_id,
            "opening_cash": c_ref, "cohort_source": "registered_genesis_cell"}


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


_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(*args) -> str:
    """One git command. An unobtainable answer is a STOP, never an empty string.

    This used to swallow `OSError` and return `""`, and it returned `""` for a
    non-zero exit as well. `provenance["commit_sha"]` and the publication
    marker's `commit_sha` are written from it, so both could carry the empty
    string -- which reads, in every later audit, exactly like a repository
    identity that was established and happened to be blank.
    `l3_route_seal.current_repo_identity` is strict, so a SEALED path was
    protected; an unsealed intent was not.
    """
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=REPO)
    except OSError as exc:
        raise L3RunAbort(
            "abort: git could not be executed (%s), so this run cannot name "
            "the repository revision it was run at. An unobtainable repo "
            "identity is a stop, not an empty string." % exc) from exc
    if proc.returncode != 0:
        raise L3RunAbort(
            "abort: `git %s` exited %d: %s"
            % (" ".join(args), proc.returncode,
               ((proc.stderr or "").strip().splitlines() or ["no stderr"])[0]))
    return proc.stdout.strip()


def repo_commit_sha() -> str:
    """The 40-hex revision this run is executed at, or an abort.

    Shape-checked rather than trusted: `git rev-parse` exiting 0 is not the
    same fact as it having answered with a commit.
    """
    sha = _git("rev-parse", "HEAD")
    if not _COMMIT_SHA_RE.match(sha):
        raise L3RunAbort(
            "abort: `git rev-parse HEAD` answered %r, which is not a 40-hex "
            "commit sha. A run may not record an unresolvable revision as its "
            "identity." % sha)
    return sha


def write_decision_record(path: str, payload) -> bytes:
    """A lineage / decision record, claimed EXCLUSIVELY and then written.

    `core.b0_master_prereg.write_provenance_json` opens `"wb"`, which
    truncates: writing the same name twice replaces the first record and
    nothing says so. In practice the O_EXCL snapshot receipt and the O_EXCL
    publication marker make a same-directory re-run abort before it gets here,
    so this is belt-and-braces -- but "belt-and-braces" is not the same fact as
    "exclusive", and the specification requires exclusive creation for lineage
    and decision records.

    The claim is a separate `O_CREAT | O_EXCL` call and the BYTES are still
    written by the provenance primitive, so the record's content is byte-
    identical to what it has always been. `core/b0_master_prereg.py` is not
    editable from here, which is why the exclusivity is expressed as a claim
    around it rather than as a mode change inside it.
    """
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise L3RunAbort(
            "abort: %s already exists in this run directory. Decision and "
            "lineage records are claimed exclusively; re-deciding a period is "
            "a NEW run, never an overwrite of the record of the first one."
            % os.path.basename(path)) from exc
    os.close(fd)
    return write_provenance_json(path, payload)


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
    try:
        seal_payload = rs.assert_route_is_sealable()
    except rs.RouteSealError as exc:
        raise L3RunAbort(
            "L3 PREFLIGHT FAILED · %s · route is not sealable: %s"
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
    seal = rs.load_route_seal(seal_id)
    verified = rs.assert_seal_binds_current_route(seal)
    checks.append(_require(
        True, "%s · route seal binds the current working tree"
        % ROUTE_EXECUTION_GATE,
        "%s · %d files" % (seal_id[:16], verified["verified_files"])))
    rs.assert_aggregate_names_this_seal(aggregate, seal_id)
    checks.append(_require(
        True, "%s · source aggregate names this route seal"
        % ROUTE_EXECUTION_GATE, str(aggregate.get("route_seal_id"))[:16]))
    return checks


# --- the source-revision stop rule ---------------------------------------------

def declared_source_rows(run_dir: str) -> dict:
    """`dataset -> the source-identity rows that run declares`.

    Read through `verify_aggregate` / `load_leaf` rather than off the raw JSON,
    so a baseline whose leaves have been edited since they were indexed is
    refused by the manifest engine before it is ever used as a baseline.
    """
    from source_ownership_manifest import (
        LEAF_FILENAME, ManifestError, load_leaf, verify_aggregate,
    )

    try:
        aggregate = verify_aggregate(run_dir)
        rows = {}
        for dataset in sorted(aggregate["leaves"]):
            leaf = load_leaf(os.path.join(run_dir, LEAF_FILENAME % dataset))
            entries = []
            for i, entry in enumerate(leaf["entries"]):
                absent = [f for f in SOURCE_CONTINUITY_ROW_FIELDS
                          if not entry.get(f)]
                if absent:
                    raise L3RunAbort(
                        "abort: %s entry %d (%s) cannot state its source "
                        "identity: %s. A row that cannot say what it is cannot "
                        "be compared against what it was."
                        % (dataset, i, entry.get("locator", "<unnamed>"), absent))
                entries.append({f: str(entry[f])
                                for f in SOURCE_CONTINUITY_ROW_FIELDS})
            rows[dataset] = entries
        return rows
    except ManifestError as exc:
        raise L3RunAbort(
            "abort: the source set at %s could not be read as a comparison "
            "surface: %s" % (run_dir, exc)) from exc


def assert_source_continuity(directory: str, *, prior_manifest: str,
                             no_prior_declared: bool) -> dict:
    """Wire the ruling draft's stop rule onto this run's declared sources.

    THE BASELINE IS THE PRECEDING RUN'S OWN SOURCE MANIFEST, named by
    `--prior-source-manifest <run>/source_ownership_manifest.json`. It is not
    discovered, because "the latest run directory" is a guess about which
    lineage a run continues, and a baseline picked by guess is a baseline that
    can be picked to pass.

    THE FIRST RUN OF A LINEAGE HAS NO BASELINE, and that is declared, not
    inferred: `--no-prior-source-manifest` records `NO_SOURCE_BASELINE` in the
    provenance of every receipt. A silent skip and a genuinely first run look
    identical afterwards, which is the whole reason the declaration exists.
    Only a GENESIS opening may make it -- a CONTINUATION by definition has a
    predecessor, so "no baseline" there is a claim that contradicts the opening
    contract, and it is refused in `preflight`.

    The comparison is PER DATASET FAMILY, keyed on `locator` and dated by
    `export_vintage`. Per family rather than globally because families are
    exported on their own cadences: a new prices archive dated inside the
    calendar family's already-observed span is an append to prices, not a
    revision of anything, and a global date axis would call it a stop.
    """
    if bool(prior_manifest) == bool(no_prior_declared):
        raise L3RunAbort(
            "abort: exactly one of --prior-source-manifest and "
            "--no-prior-source-manifest must be declared. Whether a run has a "
            "source baseline is a fact about its lineage; inferring it from an "
            "empty argument is how a revision becomes a quiet refresh.")

    current = declared_source_rows(directory)
    if no_prior_declared:
        return {
            "rule": "APPEND_ONLY_OR_STOP",
            "baseline": NO_SOURCE_BASELINE,
            "baseline_manifest": "",
            "baseline_run_id": "",
            "datasets_declared": sorted(current),
            "datasets_compared": [],
            "datasets_without_baseline": sorted(current),
            "per_dataset": {},
        }

    prior_manifest = os.path.abspath(prior_manifest)
    if not os.path.isfile(prior_manifest):
        raise L3RunAbort(
            "abort: the declared source baseline is absent: %s" % prior_manifest)
    prior_dir = os.path.dirname(prior_manifest)
    if os.path.normcase(prior_dir) == os.path.normcase(os.path.abspath(directory)):
        raise L3RunAbort(
            "abort: a run may not be its own source baseline. "
            "--prior-source-manifest must name the PRECEDING run's "
            "source_ownership_manifest.json.")

    from source_ownership_manifest import AGGREGATE_FILENAME

    if os.path.basename(prior_manifest) != AGGREGATE_FILENAME:
        raise L3RunAbort(
            "abort: --prior-source-manifest must name a %s; got %s"
            % (AGGREGATE_FILENAME, os.path.basename(prior_manifest)))

    previous = declared_source_rows(prior_dir)
    baseline = _load(prior_manifest)

    disappeared = sorted(set(previous) - set(current))
    if disappeared:
        raise L3RunAbort(
            "abort: source family/families %s were declared by the baseline "
            "run %r and are not declared by this one. A family that stops "
            "being declared is not an append; it is a source this run decided "
            "without." % (disappeared, baseline.get("run_id")))

    per_dataset, compared, unbaselined = {}, [], []
    for dataset in sorted(current):
        if dataset not in previous:
            # A family the route gained since the baseline. Recorded by name so
            # it is countable later; it cannot be compared against rows that do
            # not exist, and pretending it was compared would be the lie.
            unbaselined.append(dataset)
            per_dataset[dataset] = {
                "status": "NEW_FAMILY_NO_BASELINE_ROWS",
                "current_rows": len(current[dataset])}
            continue
        try:
            report = assert_append_only_continuity(
                previous[dataset], current[dataset],
                date_field=SOURCE_CONTINUITY_DATE_FIELD,
                primary_key=SOURCE_CONTINUITY_PRIMARY_KEY)
        except TemporalSnapshotError as exc:
            raise L3RunAbort(
                "abort: declared source family %r fails the append-only "
                "continuity rule against baseline run %r: %s.\n"
                "A later source update is admissible only when the previously "
                "observed overlap is digest-identical and the new rows are a "
                "strict append. A revision inside the overlap is a stop, not a "
                "quiet refresh -- the decision this run would take stands on "
                "bytes that are not the bytes the previous run stood on."
                % (dataset, baseline.get("run_id"), exc)) from exc
        compared.append(dataset)
        per_dataset[dataset] = {"status": "APPEND_ONLY", **report}

    return {
        "rule": "APPEND_ONLY_OR_STOP",
        "baseline": "PRIOR_RUN_SOURCE_OWNERSHIP_MANIFEST",
        "baseline_manifest": prior_manifest.replace("\\", "/"),
        "baseline_run_id": str(baseline.get("run_id", "")),
        "baseline_as_of": str(baseline.get("as_of", "")),
        "baseline_payload_sha256": str(baseline.get("payload_sha256", "")),
        "datasets_declared": sorted(current),
        "datasets_compared": compared,
        "datasets_without_baseline": unbaselined,
        "per_dataset": per_dataset,
    }


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
    # An args-level contradiction, refused before any source set is read.
    # "This lineage has no source baseline" is a statement only a first run can
    # make, and a CONTINUATION has a preceding run by definition.
    if args.opening_kind != ps.OPENING_GENESIS and args.no_prior_source_manifest:
        raise L3RunAbort(
            "abort: --no-prior-source-manifest is a GENESIS-only declaration. "
            "A CONTINUATION has a preceding run by definition, and 'this "
            "lineage has no source baseline' contradicts the opening contract "
            "it was invoked under.")

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
    cohort = _assert_cohort_identity(args)
    checks.append(_require(True, "opening cohort identity bound",
                           "%s (%s)" % (cohort["cohort_id"],
                                        cohort["cohort_source"])))

    # The source baseline. Declared for every mode that CONSUMES the source set
    # and writes receipts; `preflight` writes nothing, so it reports the
    # declaration rather than requiring one.
    if args.mode in SOURCE_CONTINUITY_MODES:
        continuity = assert_source_continuity(
            directory, prior_manifest=args.prior_source_manifest,
            no_prior_declared=bool(args.no_prior_source_manifest))
        checks.append(_require(
            True, "declared sources are append-only against their baseline",
            "%s; compared %d family/families, %d without baseline rows"
            % (continuity["baseline"], len(continuity["datasets_compared"]),
               len(continuity["datasets_without_baseline"]))))
    elif args.prior_source_manifest or args.no_prior_source_manifest:
        continuity = assert_source_continuity(
            directory, prior_manifest=args.prior_source_manifest,
            no_prior_declared=bool(args.no_prior_source_manifest))
        checks.append(_require(
            True, "declared sources are append-only against their baseline",
            continuity["baseline"]))
    else:
        continuity = {"rule": "APPEND_ONLY_OR_STOP",
                      "baseline": "NOT_DECLARED_PREFLIGHT_WRITES_NOTHING"}
        checks.append({
            "item": "declared source baseline",
            "status": "OPEN",
            "detail": "not declared; required for %s"
                      % (SOURCE_CONTINUITY_MODES,)})

    if args.mode == "intent":
        _assert_intent_claim_is_today(args.decision_date)
        checks.append(_require(True, "decision claim date is today in Asia/Taipei",
                               str(args.decision_date)))

    if args.mode == "execute":
        prior = str(getattr(args, "prior_intent", "") or "")
        expected_sha = str(getattr(args, "expect_prior_intent_sha256", "") or "")
        if not prior or not expected_sha:
            raise L3RunAbort(
                "abort: execute requires --prior-intent and "
                "--expect-prior-intent-sha256; execution may not re-decide a "
                "period with no immutable intent hand-off")
        if not os.path.isfile(prior):
            raise L3RunAbort("abort: prior decision intent file is absent: %s" % prior)
        measured = file_sha256(prior)
        if measured != expected_sha:
            raise L3RunAbort(
                "abort: prior intent file hashes %s; caller named %s"
                % (measured[:16], expected_sha[:16]))
        checks.append(_require(True, "prior decision intent file hash bound",
                               measured[:16]))

    tx = closure_transaction_state()
    spans_state = span_derivation_state()
    # Reported at every mode, gating every decision invocation. A preflight that hid the
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
        "item": "%s · A2 route seal" % ROUTE_EXECUTION_GATE,
        "status": "PASS" if sealable else "OPEN",
        "detail": "%s; aggregate route_seal_id=%r"
                  % (why[:90], aggregate.get("route_seal_id"))})

    if args.mode in ("intent", "execute"):
        checks += assert_route_execution_admissible(aggregate, args.route_seal_id)
        if args.sealed_evidence is None:
            raise L3RunAbort(
                "abort: --sealed-evidence / --no-sealed-evidence must be "
                "declared for a decision invocation. Whether a run may produce sealed "
                "evidence is a declaration, never an inference "
                "(run_decision(for_sealed_run=...)).")
    return checks, directory, aggregate, tx, spans_state, cohort, continuity


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
                 synthetic_sources: bool = False,
                 decision_intent_only: bool = False,
                 cohort_id: str = "") -> dict:
    """Both halves of one period, and its canonical input.

    The decision layer is NOT invoked here. This function ends one call short of
    it on purpose: everything below is source handling and state construction,
    and it must be possible to verify all of it without producing an
    observation.
    """
    # S-1. The cohort travels WITH the state, and it is verified before the
    # state is allowed to open anything. A CONTINUATION must name one and the
    # file must agree; a GENESIS opening checkpoint predates the field, so it
    # may name none -- but if it names one it must be this one.
    cohort_id = str(cohort_id or "")
    if opening_kind == ps.OPENING_CONTINUATION and not cohort_id:
        raise L3RunAbort(
            "abort: a CONTINUATION period must name the cohort its lineage "
            "was opened under before it may read an opening checkpoint. "
            "Without it the two registered cells are separated only by the "
            "magnitude of `cash`, which is the input to adv_floor(port_value).")
    cohort_verification = {"cohort_id": cohort_id, "cohort_rule": "",
                           "rows_verified": 0}
    if cohort_id:
        try:
            cohort_verification = pc.assert_checkpoint_cohort(
                opening_checkpoint, expected_cohort_id=cohort_id,
                rule=(pc.COHORT_MUST_BE_NAMED
                      if opening_kind == ps.OPENING_CONTINUATION
                      else pc.COHORT_MAY_PREDATE_THE_LINEAGE))
        except pc.CheckpointError as exc:
            raise L3RunAbort(str(exc)) from exc

    import l3_assemble as A

    contract = assembly_span_contract()
    if contract == CONTRACT_LINEAGE_FLOOR:
        assembler = (A.assemble_decision_intent if decision_intent_only
                     else A.assemble)
        assembled = assembler(directory, run_id, decision_date,
                              lineage_price_floor=spans["lineage_price_floor"])
    elif contract == CONTRACT_EXPLICIT_SPANS:
        if decision_intent_only:
            raise L3RunAbort(
                "abort: decision intent requires the lineage-floor span "
                "contract; the legacy explicit span contract encodes an "
                "execution endpoint and cannot represent execution_date=null.")
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
    as_of = str(period["as_of"])
    exec_date = (str(period["execution_date"])
                 if period.get("execution_date") is not None else None)

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
    decision_input = (
        A.build_decision_intent_input(assembled, sources, side.state)
        if decision_intent_only else
        A.build_decision_input(assembled, sources, side.state,
                               exec_px, untradable))
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
        "cohort_verification": cohort_verification,
        "redated": redated,
        "transition": tr,
        "side": side,
        "sources": sources,
        "execution_prices": exec_px,
        "untradable": untradable,
        "decision_input": decision_input,
        "decision_intent_only": bool(decision_intent_only),
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
    receipt_builder = (S.build_intent_receipt
                       if built.get("decision_intent_only")
                       else S.build_receipt)
    receipt = receipt_builder(
        directory, run_id, str(built["period"]["decision_date"]),
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
        "execution_date": built.get("execution_date"),
        "opening": built["opening_provenance"],
        # The cohort this period belongs to, verified against the checkpoint
        # that opened it rather than inferred from its cash.
        "cohort": built["cohort_verification"],
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
        "decision_cutoff_state_sha256":
            built["assembled"]["decision_cutoff_state_sha256"],
        "snapshot_receipt_sha256": receipt_sha,
        "decision_layer_invoked": False,
        "decision_intent_only": bool(built.get("decision_intent_only")),
        "performance_computed": False,
        "evidence_class": "NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED",
        "provenance": provenance,
    }
    write_decision_record(os.path.join(directory, PORTFOLIO_RECEIPT),
                          portfolio_receipt)
    write_decision_record(os.path.join(directory, OPENING_RECORD), {
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


# --- the two-phase decision hand-off: what is COMPARED, what is only RECORDED ---
#
# A prospective period is observed in two phases. Phase A (`--mode intent`) runs
# ON the decision date, when the next trading session has not happened: there is
# no execution date, no opening price, no cost and no post-trade state. Phase B
# (`--mode execute`) runs after that session is observed and must consume phase
# A's immutable record, so that EXECUTION CANNOT SILENTLY RE-DECIDE.
#
# That purpose fixes the admission rule for the equality contract, and it is a
# rule about construction rather than about fixtures:
#
#   a field may be COMPARED only if it is knowable at the decision cut-off and
#   is therefore IDENTICAL IN BOTH PHASES BY CONSTRUCTION.
#
# A field that differs by construction cannot express "nothing was re-decided";
# binding one makes phase B structurally unreachable, which is exactly what
# `market_state_sha256` did. `l3_assemble.market_state_payload` carries
# `execution_date` and every `execution_open`, so its hash is DEFINED to move
# between the phases -- and `l3_assemble.decision_cutoff_payload` exists for
# precisely this reason: it is the same payload with those two execution facts
# blanked, it is already computed by `_assemble` and already written into the
# portfolio receipt as `decision_cutoff_state_sha256`, and it is the
# phase-invariant identity of the market facts the decision actually stood on.
#
# `market_state_sha256` is NOT dropped, because it is not noise: it is the
# identity of the state each phase was really computed from, it is what the
# snapshot receipt of each run binds, and it is the only link from a published
# intent back to its own receipt. It is kept as RECORDED-BUT-NOT-COMPARED --
# still immutable (it sits inside `decision_intent.json`, which is bound by
# `intent_payload_sha256` and by the publication-commit marker's file hash),
# but never used as an equality gate. The two sets are named, disjoint and
# checked below so that a later field cannot join either one by accident.
DECISION_CONTRACT_COMPARED_FIELDS: tuple[str, ...] = (
    "as_of", "commit_sha", "config_hash", "decision_cutoff_state_sha256",
    "decision_date", "genesis_cohort_id", "harness_sha256",
    "indicative_target_shares", "opening_c_ref", "portfolio_side_sha256",
    "ranking", "route_kind", "route_seal_id", "sealed_evidence", "selected",
    "stages", "target_weights",
)

# Phase-dependent BY CONSTRUCTION. Recorded as provenance, never compared.
DECISION_CONTRACT_RECORDED_FIELDS: tuple[str, ...] = (
    "market_state_sha256",
)


def _assert_contract_field_sets(payload: dict) -> None:
    """No field joins the equality contract without being classified first."""
    overlap = sorted(set(DECISION_CONTRACT_COMPARED_FIELDS)
                     & set(DECISION_CONTRACT_RECORDED_FIELDS))
    if overlap:
        raise L3RunAbort(
            "abort: field(s) %s are declared both compared and recorded; a "
            "field is one or the other and the distinction is the contract"
            % overlap)
    unclassified = sorted(set(payload) - set(DECISION_CONTRACT_COMPARED_FIELDS))
    if unclassified:
        raise L3RunAbort(
            "abort: the decision contract carries unclassified field(s) %s. "
            "Every compared field must be phase-invariant by construction; add "
            "it to DECISION_CONTRACT_COMPARED_FIELDS only after establishing "
            "that, and to DECISION_CONTRACT_RECORDED_FIELDS otherwise."
            % unclassified)
    absent = sorted(set(DECISION_CONTRACT_COMPARED_FIELDS) - set(payload))
    if absent:
        raise L3RunAbort(
            "abort: the decision contract omits declared compared field(s) %s; "
            "a contract that silently stops carrying a field compares nothing "
            "about it" % absent)


def decision_contract_payload(built: dict, intent, provenance: dict) -> dict:
    """The exact decision semantics the following execution must consume.

    EQUALITY FIELDS ONLY -- see DECISION_CONTRACT_COMPARED_FIELDS above for why
    the market-state hash is not among them and where it went instead.
    """
    payload = {
        "route_kind": intent.route_kind,
        "decision_date": intent.decision_date,
        "as_of": intent.as_of,
        "config_hash": intent.config_hash,
        "stages": list(intent.stages),
        "decision_cutoff_state_sha256":
            built["assembled"]["decision_cutoff_state_sha256"],
        "portfolio_side_sha256": canonical_sha256(
            built["portfolio_side_payload"]),
        "ranking": list(intent.ranking),
        "selected": list(intent.targets.selected),
        "target_weights": dict(sorted(intent.targets.weights.items())),
        "indicative_target_shares": dict(sorted(intent.target_shares.items())),
        "genesis_cohort_id": provenance.get("genesis_cohort_id", ""),
        "opening_c_ref": provenance.get("opening_c_ref", 0.0),
        "route_seal_id": provenance.get("route_seal_id"),
        "sealed_evidence": provenance.get("sealed_evidence"),
        "commit_sha": provenance.get("commit_sha"),
        "harness_sha256": provenance.get("harness_sha256"),
    }
    _assert_contract_field_sets(payload)
    return payload


def decision_state_provenance_payload(built: dict) -> dict:
    """Recorded, never compared: the phase's own market-state identity.

    In an intent run this equals the decision-cut-off hash by construction (no
    execution date, no opens); in an execution run it does not, and the
    difference is the observed execution session -- not a re-decision.
    """
    return {name: built["assembled"][name]
            for name in DECISION_CONTRACT_RECORDED_FIELDS}


def decision_intent_payload(run_id: str, built: dict, intent,
                            provenance: dict) -> dict:
    """Serializable decision observation, explicitly not an execution."""
    contract = decision_contract_payload(built, intent, provenance)
    # Recorded alongside the contract, deliberately outside it. The top-level
    # splat of both keeps every previously published field readable at the same
    # key; only the COMPARED half is inside `decision_contract`.
    recorded = decision_state_provenance_payload(built)
    base = {
        "record": "B0_L3_DECISION_INTENT",
        "run_id": run_id,
        "run_kind": RUN_KIND,
        **contract,
        **recorded,
        "decision_contract": contract,
        "decision_contract_sha256": canonical_sha256(contract),
        "decision_contract_compared_fields":
            list(DECISION_CONTRACT_COMPARED_FIELDS),
        "decision_state_provenance": recorded,
        "decision_state_provenance_compared": False,
        "execution_date": None,
        "execution_observed": False,
        "decision_layer_invoked": True,
        "execution_layer_invoked": False,
        "performance_computed": False,
        "stages": list(intent.stages),
        "eligible_count": len(intent.eligibility.eligible),
        "sizing_price_basis": "AS_OF_MARK_NOT_EXECUTION_PRICE",
        "port_value_at_as_of": intent.port_value,
        "costs": None,
        "post_trade_state": None,
        "provenance": provenance,
    }
    return {**base, "intent_payload_sha256": canonical_sha256(base)}


def assert_prior_intent_matches(prior_path: str, built: dict, intent,
                                provenance: dict) -> dict:
    """Verify the decision-date record and the execution-time reconstruction."""
    prior_dir = os.path.dirname(os.path.abspath(prior_path))
    marker_path = os.path.join(prior_dir, PUBLICATION_COMMIT)
    if not os.path.isfile(marker_path):
        raise L3RunAbort(
            "abort: prior intent has no publication commit marker; a partial "
            "multi-file publication is not an executable decision intent")
    with open(marker_path, "r", encoding="utf-8") as fh:
        marker = json.load(fh)
    if (marker.get("record") != "B0_L3_PUBLICATION_COMMIT"
            or marker.get("mode") != "intent"):
        raise L3RunAbort("abort: prior publication marker is not an intent commit")
    files = marker.get("files")
    if not isinstance(files, dict) or DECISION_INTENT not in files:
        raise L3RunAbort("abort: prior publication marker omits decision_intent.json")
    for name, expected in files.items():
        if os.path.basename(str(name)) != str(name):
            raise L3RunAbort("abort: publication marker contains a non-leaf path")
        path = os.path.join(prior_dir, str(name))
        if not os.path.isfile(path) or file_sha256(path) != str(expected):
            raise L3RunAbort(
                "abort: prior publication bundle member is absent or changed: %s"
                % name)
    with open(prior_path, "r", encoding="utf-8") as fh:
        prior = json.load(fh)
    if (prior.get("record") != "B0_L3_DECISION_INTENT"
            or prior.get("run_kind") != RUN_KIND
            or prior.get("execution_observed") is not False
            or prior.get("execution_layer_invoked") is not False):
        raise L3RunAbort("abort: prior file is not a completed decision intent")
    outer_sha = str(prior.get("intent_payload_sha256", ""))
    outer = dict(prior)
    outer.pop("intent_payload_sha256", None)
    if canonical_sha256(outer) != outer_sha:
        raise L3RunAbort("abort: prior intent outer payload hash is invalid")
    contract = prior.get("decision_contract")
    if not isinstance(contract, dict):
        raise L3RunAbort("abort: prior intent has no decision_contract")
    stored_sha = str(prior.get("decision_contract_sha256", ""))
    if canonical_sha256(contract) != stored_sha:
        raise L3RunAbort("abort: prior intent decision_contract hash is invalid")
    # The prior contract must have the SHAPE this runner compares. A record
    # written under a different field set is not comparable, and the failure a
    # shape check prevents is the silent one: an equality test that passes
    # because a decision-bearing field is simply absent from both sides.
    phase_dependent = sorted(set(DECISION_CONTRACT_RECORDED_FIELDS)
                             & set(contract))
    if sorted(contract) != sorted(DECISION_CONTRACT_COMPARED_FIELDS):
        raise L3RunAbort(
            "abort: prior intent's decision_contract has a different field set "
            "than this runner compares (extra %s, missing %s)%s"
            % (sorted(set(contract) - set(DECISION_CONTRACT_COMPARED_FIELDS)),
               sorted(set(DECISION_CONTRACT_COMPARED_FIELDS) - set(contract)),
               ("; field(s) %s are phase-dependent by construction and can "
                "never be equality fields" % phase_dependent)
               if phase_dependent else ""))
    current = decision_contract_payload(built, intent, provenance)
    if current != contract:
        differing = sorted(k for k in set(current) | set(contract)
                           if current.get(k) != contract.get(k))
        raise L3RunAbort(
            "abort: execution reconstruction differs from the immutable "
            "decision intent in fields %s" % differing)
    return prior


def commit_publication(directory: str, run_id: str, mode: str,
                       decision_date: str, provenance: dict,
                       names: tuple[str, ...]) -> dict:
    """Make a multi-file publication valid by writing its marker last.

    Individual immutable files can survive a process crash.  They have no
    official meaning until this O_EXCL marker binds every member's raw bytes.
    A half-published directory is therefore fail-loud, never a valid intent.
    """
    files = {}
    for name in names:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            files[name] = file_sha256(path)
    required = {SNAPSHOT_RECEIPT, PORTFOLIO_RECEIPT, OPENING_RECORD,
                FINAL_RESULT}
    if mode == "intent":
        required.add(DECISION_INTENT)
    missing = sorted(required - set(files))
    if missing:
        raise L3RunAbort(
            "abort: publication bundle is incomplete before commit: %s" % missing)
    marker = {
        "record": "B0_L3_PUBLICATION_COMMIT",
        "run_id": run_id,
        "run_kind": RUN_KIND,
        "mode": mode,
        "decision_date": decision_date,
        "route_seal_id": provenance.get("route_seal_id"),
        "sealed_evidence": provenance.get("sealed_evidence"),
        "commit_sha": provenance.get("commit_sha"),
        "harness_sha256": provenance.get("harness_sha256"),
        "files": dict(sorted(files.items())),
    }
    path = os.path.join(directory, PUBLICATION_COMMIT)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise L3RunAbort(
            "abort: publication commit already exists; a completed bundle is "
            "immutable") from exc
    raw = ((json.dumps(marker, ensure_ascii=False, sort_keys=True, indent=1)
            + "\n").replace("\r\n", "\n").encode("utf-8"))
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    return marker


# --- entry point -----------------------------------------------------------------

def _provenance(args, directory, aggregate, tx, spans_state, spans,
                cohort, continuity) -> dict:
    return {
        "record": "B0_L3_PROSPECTIVE_RUN_PROVENANCE",
        "run_id": args.run_id,
        "run_kind": RUN_KIND,
        "mode": args.mode,
        "authorization": args.authorization,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        # S-6: an unobtainable repository identity aborts here rather than
        # being recorded as an empty string.
        "commit_sha": repo_commit_sha(),
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
        # S-1. On a CONTINUATION this used to be "" -- the cohort was asserted
        # at genesis and never again. It is now the cohort the LINEAGE was
        # opened under, for both opening contracts, so it stays a phase-
        # invariant compared field of the decision contract and it is no longer
        # blank from period 2 onward.
        "genesis_cohort_id": cohort["genesis_cohort_id"],
        "cohort_id": cohort["cohort_id"],
        "cohort_source": cohort["cohort_source"],
        "opening_c_ref": float(cohort["opening_cash"]),
        # S-2. Where this run's source baseline came from, or the explicit
        # declaration that this lineage has none yet.
        "source_continuity": continuity,
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
                    help="intent/execute: the seal that content-binds the whole "
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
    ap.add_argument("--genesis-cohort", default="",
                    choices=["", *sorted(L3_GENESIS_COHORTS),
                             SYNTHETIC_PARITY_COHORT],
                    help="GENESIS only: the named L3 prospective capacity cohort")
    ap.add_argument("--lineage-cohort", default="",
                    choices=["", *L3_LINEAGE_COHORTS],
                    help="CONTINUATION only: the cohort this lineage was "
                         "opened under. Verified against the cohort every row "
                         "of --opening-checkpoint names; a checkpoint that "
                         "names a different cohort, or none, aborts")
    # --- the source baseline: one declaration, and no silent third state -----
    # `--no-prior-source-manifest` is not "skip the check". It is the recorded
    # statement that this lineage has no earlier run to compare against, and it
    # is refused for a CONTINUATION, which has one by definition.
    ap.add_argument("--prior-source-manifest", default="",
                    help="the PRECEDING run's source_ownership_manifest.json; "
                         "this run's declared sources must be a strict append "
                         "to it")
    ap.add_argument("--no-prior-source-manifest", action="store_true",
                    help="GENESIS only: declare that this is the first run of "
                         "the lineage and has no source baseline")
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
    ap.add_argument("--prior-intent", default="",
                    help="execute only: immutable decision_intent.json from the "
                         "decision-date run")
    ap.add_argument("--expect-prior-intent-sha256", default="",
                    help="execute only: raw sha256 of --prior-intent")
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
    (checks, directory, aggregate, tx, spans_state, cohort,
     continuity) = preflight(args)
    for c in checks:
        print("  %-5s %-58s %s" % (c["status"], c["item"], c["detail"]),
              flush=True)
    if args.mode == "preflight":
        print("\npreflight only: nothing claimed, nothing written.", flush=True)
        print("route execution admissible: %s"
              % (not tx["in_transaction"]
                 and spans_state["spans_have_a_registered_derivation"]),
              flush=True)
        return 0

    # §6.6 resolves as_of BEFORE the spans can be derived from it, so the plan
    # runs first. It writes nothing.
    import l3_snapshot as S

    planned = (S.plan_decision_intent(directory, args.run_id,
                                      args.decision_date)
               if args.mode == "intent" else
               S.plan(directory, args.run_id, args.decision_date))
    spans = resolve_spans(args, as_of=str(planned["as_of"]),
                          execution_date=(str(planned["execution_date"])
                                          if planned.get("execution_date")
                                          else ""),
                          contract=spans_state["assembly_span_contract"])
    provenance = _provenance(args, directory, aggregate, tx, spans_state,
                             spans, cohort, continuity)

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
            synthetic_sources=args.synthetic_sources,
            decision_intent_only=(args.mode == "intent"),
            cohort_id=cohort["cohort_id"])
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

    # Decision modes complete the whole decision computation in memory before
    # claiming any immutable receipt.  A scoring/invariant failure therefore
    # leaves no half-published period that cannot be retried.
    prepared_intent = None
    prior_intent = None
    if args.mode in ("intent", "execute"):
        from core.b0_route import (DecisionIntentInput, build_decision_intent)

        intent_input = (built["decision_input"] if args.mode == "intent" else
                        DecisionIntentInput.from_canonical(
                            built["decision_input"]))
        try:
            prepared_intent = build_decision_intent(
                intent_input, for_sealed_run=bool(args.sealed_evidence))
            if args.mode == "execute":
                prior_intent = assert_prior_intent_matches(
                    args.prior_intent, built, prepared_intent, provenance)
        except Exception as exc:                            # noqa: BLE001
            # No receipt has been claimed yet.  The exception itself is the
            # fail-loud observation; publishing a failure row here would
            # recreate the partial-run problem this ordering prevents.
            raise L3RunAbort(
                "decision preparation failed before publication: %s: %s"
                % (type(exc).__name__, exc)) from exc

    receipt = write_period_receipts(directory, args.run_id, built, spans,
                                    provenance)
    print("\nmarket state    %s" % built["assembled"]["market_state_sha256"],
          flush=True)
    print("portfolio side  %s" % receipt["portfolio_side_sha256"], flush=True)
    print("opening         %s (%s, seq %d)"
          % (built["opening_provenance"]["checkpoint_sha256"][:16],
             built["opening_provenance"]["terminal_period"],
             built["opening_provenance"]["terminal_seq"]), flush=True)

    if args.mode == "intent":
        intent = prepared_intent
        payload = decision_intent_payload(args.run_id, built, intent,
                                          provenance)
        write_decision_record(os.path.join(directory, DECISION_INTENT), payload)
        write_decision_record(os.path.join(directory, FINAL_RESULT), {
            "record": "B0_L3_PROSPECTIVE_TERMINAL_RESULT",
            "run_id": args.run_id,
            "run_kind": RUN_KIND,
            "terminal_status": "DECISION_INTENT_RECORDED_EXECUTION_PENDING",
            "terminated_at_utc": datetime.now(timezone.utc).isoformat(),
            "decision_layer_invoked": True,
            "execution_layer_invoked": False,
            "performance_computed": False,
            "execution_date": None,
            "intent_payload_sha256": payload["intent_payload_sha256"],
            "portfolio_side_sha256": receipt["portfolio_side_sha256"],
            "market_state_sha256": built["assembled"]["market_state_sha256"],
            # The identity the later execution will actually be held to. In an
            # intent run it equals the market-state hash by construction; the
            # execution run is where the two part company.
            "decision_cutoff_state_sha256":
                built["assembled"]["decision_cutoff_state_sha256"],
            **{k: provenance[k] for k in
               ("commit_sha", "harness_sha256", "harness_path",
                "closure_transaction", "span_derivation", "spans",
                "genesis_cohort_id", "cohort_id", "source_continuity")},
        })
        commit_publication(
            directory, args.run_id, "intent", args.decision_date, provenance,
            (SNAPSHOT_RECEIPT, PORTFOLIO_RECEIPT, OPENING_RECORD, CA_LEDGER,
             DECISION_INTENT, FINAL_RESULT))
        print("\nterminal status: DECISION_INTENT_RECORDED_EXECUTION_PENDING",
              flush=True)
        print("selected: %d; indicative shares use %s close"
              % (len(intent.targets.selected), intent.as_of), flush=True)
        return 0

    if args.mode == "assemble":
        write_decision_record(os.path.join(directory, FINAL_RESULT), {
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
                "closure_transaction", "span_derivation", "spans",
                "genesis_cohort_id", "cohort_id", "source_continuity")},
        })
        commit_publication(
            directory, args.run_id, "assemble", args.decision_date, provenance,
            (SNAPSHOT_RECEIPT, PORTFOLIO_RECEIPT, OPENING_RECORD, CA_LEDGER,
             FINAL_RESULT))
        print("\nterminal status: ASSEMBLED_DECISION_LAYER_NOT_INVOKED",
              flush=True)
        return 0

    # --- execute -----------------------------------------------------------------
    from core.b0_route import run_decision

    try:
        # The core boundary deliberately recomputes the native intent.  The
        # prior artefact is an equality gate, never an injectable order list.
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
        write_decision_record(os.path.join(directory, FINAL_RESULT), {
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
                "closure_transaction", "span_derivation", "spans",
                "genesis_cohort_id", "cohort_id", "source_continuity")},
        })
        raise
    # S-1. Written here rather than through `portfolio_side.append_checkpoint`
    # for one reason: that function cannot name a cohort, and a checkpoint
    # written without one is a hand-off the NEXT period is required to
    # refuse. The two calls below are exactly what it does, plus the cohort.
    rec = pc.checkpoint_record(run_id=args.run_id, seq=ps.next_seq(directory),
                               period=str(built["period"]["decision_month"]),
                               state=nxt, verify=True,
                               cohort_id=cohort["cohort_id"])
    append_provenance_record(ps.checkpoint_file(directory), rec)
    append_provenance_record(os.path.join(directory, PERIOD_PROGRESS), {
        "run_id": args.run_id, "seq": int(rec["seq"]),
        "period": str(built["period"]["decision_month"]),
        "as_of": built["as_of"], "port_value": result.port_value,
        "state_hash": result.state_hash,
        "positions": len(result.session.shares_after),
        "applied_ca_event_ids": list(built["side"].applied_ca_event_ids),
        "post_checkpoint_sha256": rec["checkpoint_sha256"],
        "post_state_hash": rec["ca_state_hash"],
        "prior_intent_file_sha256": file_sha256(args.prior_intent),
        "decision_contract_sha256":
            prior_intent["decision_contract_sha256"]})
    write_decision_record(os.path.join(directory, FINAL_RESULT), {
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
        # BOTH phases' market-state identities, side by side, plus the one they
        # are actually bound to. `market_state_sha256` here and
        # `intent_market_state_sha256` DIFFER BY CONSTRUCTION -- the observed
        # execution session is inside one payload and absent from the other --
        # and recording the pair is what makes that difference auditable
        # instead of merely asserted in a comment.
        "market_state_sha256": built["assembled"]["market_state_sha256"],
        "intent_market_state_sha256":
            (prior_intent.get("decision_state_provenance")
             or {}).get("market_state_sha256"),
        "decision_cutoff_state_sha256":
            built["assembled"]["decision_cutoff_state_sha256"],
        "post_checkpoint_sha256": rec["checkpoint_sha256"],
        "prior_intent_file_sha256": file_sha256(args.prior_intent),
        "decision_contract_sha256":
            prior_intent["decision_contract_sha256"],
        **{k: provenance[k] for k in
           ("commit_sha", "harness_sha256", "harness_path",
            "closure_transaction", "span_derivation", "spans",
            "genesis_cohort_id", "cohort_id", "source_continuity")},
    })
    commit_publication(
        directory, args.run_id, "execute", args.decision_date, provenance,
        (SNAPSHOT_RECEIPT, PORTFOLIO_RECEIPT, OPENING_RECORD, CA_LEDGER,
         PERIOD_PROGRESS, "portfolio_checkpoint.jsonl", FINAL_RESULT))
    print("\nterminal status: PERIOD_EXECUTED  port_value=%.2f"
          % result.port_value, flush=True)
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    try:
        sys.exit(main())
    except L3RunAbort as exc:
        print("\nABORT: %s" % exc, flush=True)
        sys.exit(4)
