"""Frozen B0 Master Preregistration — the mechanically enforceable clauses.

`docs/FrozenB0_MasterPreregistration.md` is the sole normative specification for
Frozen B0. The individual B-01..B-21 / W-1..W-4 closures are demoted to
rationale, evidence and audit trail. Precedence when they disagree:

    Master Preregistration  >  closure prose  >  legacy code / comments

This module carries the clauses that can be enforced by a machine rather than by
reading, because this project already has a documented case (`rev_accel`) where
a comment saying "must not drift" did not stop drift. Three of them are new
rulings made at master-freeze time:

  M-1  Canonical pipeline order, with the corporate-action state transition
       placed BEFORE portfolio marking. Execution must not dispatch on event
       kinds itself.
  M-2  L2 termination taxonomy. A deterministic abort caused by a data /
       reconstruction gap is NOT `Not Supported` — the strategy did not fail,
       we merely cannot know the correct NAV. It is
       `NOT_EVALUABLE — DATA_RECONSTRUCTION_BLOCK`, it still consumes a registry
       entry, and re-running the same Frozen B0 is admissible only under a
       repair that is independent of strategy performance and not scoped to the
       portfolio's own exposure.
  M-3  No specification-by-code. Behaviour the master preregistration does not
       define is UNSPECIFIED and must abort. It must never resolve to a
       developer's reasonable default, because that is how a new free parameter
       enters at implementation time — currently the largest remaining research
       risk in this project.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Iterable, Mapping, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MASTER_PREREG_DOC = "docs/FrozenB0_MasterPreregistration.md"

# F0-R3 · implementation identity = commit SHA + EXPLICIT normative-module
# hashes. The list lives here rather than in the freeze script because which
# modules are normative is part of the specification, not part of a reporting
# tool: a module added to B0 and left off this list would be sealed by the
# commit SHA alone, which is exactly the implicit binding F0-R3 removes.
NORMATIVE_MODULES: tuple[str, ...] = (
    "core/b0_master_prereg.py",
    "core/b0_canonical_hash.py",
    "core/b0_corporate_actions.py",
    "core/b0_pit_observability.py",
    "core/b0_market_state.py",
    "core/b0_listing_spell.py",
    "core/b0_frozen_spec.py",
    "core/b0_cost_model.py",
    "core/b0_invariants.py",
    "core/b0_parity.py",
    "core/b0_provenance.py",
    "core/b0_open_items.py",
    "core/b0_finalization_items.py",
    "core/b0_l2_run_layout.py",
    "core/b0_declaration_conformance.py",
    "core/b0_state.py",
    "core/b0_features.py",
    "core/b0_eligibility.py",
    "core/b0_decision.py",
    "core/b0_execution.py",
    "core/b0_route.py",
    "core/b0_adapter_retrospective.py",
    "core/b0_adapter_production.py",
    "core/b0_price_universe.py",
    "core/b0_valuation_source.py",
    "core/b0_share_unit_adjustment.py",
    "core/b0_bonus_share_source.py",
    "core/b0_opening_state.py",
    "core/b0_1_diagnostic_closure.py",
    "core/b0_benchmark_gate1.py",
    "core/b0_benchmark_construction.py",
)


def normative_module_hashes() -> dict:
    """{path: sha256} for every normative module, raw bytes (F0-R3)."""
    from core.b0_canonical_hash import file_sha256

    return {m: file_sha256(os.path.join(REPO_ROOT, m)) for m in NORMATIVE_MODULES}


def spec_document_sha256() -> str:
    """F0-R2: raw-byte identity of the frozen master preregistration."""
    from core.b0_canonical_hash import file_sha256

    return file_sha256(os.path.join(REPO_ROOT, MASTER_PREREG_DOC))

# Precedence order, most authoritative first. Recorded so that a future reader
# resolving a conflict does not have to reconstruct the intent.
NORMATIVE_PRECEDENCE: tuple[str, ...] = (
    "master_preregistration", "closure_prose", "legacy_code_or_comment",
)


class MasterPreregViolation(RuntimeError):
    """Fail-loud: something contradicted the master preregistration."""


class UnspecifiedBehaviour(MasterPreregViolation):
    """M-3: behaviour reached that the master preregistration does not define."""


# --- M-1 · canonical pipeline order ------------------------------------------
# The corporate-action state transition happens BEFORE the portfolio is marked,
# because marking a portfolio whose share counts are still pre-event values a
# stale NAV, and because eligibility (ADV_floor = 5 x port_value) is derived from
# that mark. Placing it after marking would let a decision date that falls inside
# a corporate-action interval resolve differently depending on execution-order
# accidents.

PIPELINE_STAGES: tuple[str, ...] = (
    "pit_raw_state",
    "corporate_action_transition",       # includes the exposure guards (O-A)
    "portfolio_mark",
    "eligibility",
    "features",
    "selection_score",
    "target_portfolio",
    "order_intents",
    "execution",
    "costs",
    "post_trade_nav",
)

_STAGE_INDEX = {s: i for i, s in enumerate(PIPELINE_STAGES)}

# O-A · the corporate-action stage is not merely first, it is MANDATORY before
# any holding is valued or any order is generated. Discovering at execution time
# that yesterday's holding had already undergone a corporate action is precisely
# the failure this ordering removes.
PRE_MARK_MANDATORY_STAGE = "corporate_action_transition"
CORPORATE_ACTION_STAGE_GUARDS: tuple[str, ...] = (
    "assert_exposure_reconstructible",
    "assert_no_unexplained_price_gap",
)
# Stages that must never run before the mandatory stage.
STAGES_REQUIRING_TRANSITION: tuple[str, ...] = (
    "portfolio_mark", "eligibility", "features", "selection_score",
    "target_portfolio", "order_intents", "execution", "costs", "post_trade_nav",
)


def assert_stage_order(observed: Sequence[str]) -> None:
    """Observed stages must appear in canonical order, with no unknown stage.

    Stages may be skipped (a diagnostic run need not place orders) but may never
    be reordered: order is the whole content of this clause.
    """
    last = -1
    for name in observed:
        idx = _STAGE_INDEX.get(name)
        if idx is None:
            raise UnspecifiedBehaviour(
                f"M-1/M-3: {name!r} is not a stage defined by the master "
                f"preregistration. Known stages: {PIPELINE_STAGES}"
            )
        if idx <= last:
            prev = PIPELINE_STAGES[last]
            raise MasterPreregViolation(
                f"M-1: pipeline stage {name!r} ran after {prev!r}; the canonical "
                f"order is {PIPELINE_STAGES}. Corporate-action transitions must "
                f"precede portfolio marking, and marking must precede eligibility."
            )
        last = idx


def assert_corporate_action_precedes_mark(observed: Sequence[str]) -> None:
    """O-A: the transition stage is mandatory before ANY valuation or ordering.

    Checked on its own, not merely as a consequence of the ordering, because a
    run that skips the stage entirely satisfies `assert_stage_order` trivially.
    """
    downstream = [s for s in observed if s in STAGES_REQUIRING_TRANSITION]
    if not downstream:
        return
    if PRE_MARK_MANDATORY_STAGE not in observed:
        raise MasterPreregViolation(
            f"M-1/O-A: {downstream[0]!r} ran without a "
            f"{PRE_MARK_MANDATORY_STAGE!r} stage. Valuing or trading a holding "
            f"whose share count is still a pre-event value is a silent NAV error."
        )
    assert_stage_order([s for s in observed
                        if s in (PRE_MARK_MANDATORY_STAGE,) + STAGES_REQUIRING_TRANSITION])


# --- O-D · intraday sequence --------------------------------------------------
# A monthly decision date can fall on a corporate-action date. Without a fixed
# intraday order the same day can produce different NAVs depending on which
# effect was applied first, which is a free parameter wearing an implementation
# detail's clothes.

INTRADAY_SEQUENCE: tuple[str, ...] = (
    "start_of_trading_day",
    "apply_known_effective_corporate_actions",
    "establish_tradable_holdings",
    "obtain_permitted_execution_price",
    "execute_child_orders",
    "apply_costs",
    "end_of_day_state",
)

_INTRADAY_INDEX = {s: i for i, s in enumerate(INTRADAY_SEQUENCE)}

# Decision state is built from the last COMPLETED session, never from the day
# being executed. This is the same rule G14-1 already applies to sigma20d/adv20,
# stated once for every decision input rather than per-field.
DECISION_STATE_SOURCE = "prior_completed_trading_session"

# Cash reaches available cash on its payment date, never on ex-date (V-1a).
CASH_DIVIDEND_CREDIT_EVENT = "payment_date"
STOCK_DIVIDEND_CREDIT_EVENT = "max(股票股利上市日, 股票股利發放日)"


def assert_intraday_order(observed: Sequence[str]) -> None:
    last = -1
    for name in observed:
        idx = _INTRADAY_INDEX.get(name)
        if idx is None:
            raise UnspecifiedBehaviour(
                f"O-D/M-3: {name!r} is not an intraday step defined by the master "
                f"preregistration. Known steps: {INTRADAY_SEQUENCE}")
        if idx <= last:
            raise MasterPreregViolation(
                f"O-D: intraday step {name!r} ran after "
                f"{INTRADAY_SEQUENCE[last]!r}; the canonical order is "
                f"{INTRADAY_SEQUENCE}. Corporate actions are applied before the "
                f"tradable holding is established, which is before any price is "
                f"obtained.")
        last = idx


def assert_decision_inputs_are_prior_session(decision_date: str,
                                             input_dates: Mapping[str, str]) -> None:
    """Every decision input must be dated strictly before the decision date."""
    late = {k: v for k, v in input_dates.items() if str(v) >= str(decision_date)}
    if late:
        raise MasterPreregViolation(
            f"O-D: decision inputs {late} are not strictly earlier than the "
            f"decision date {decision_date}. Decision state comes from the "
            f"{DECISION_STATE_SOURCE}.")


# Only the corporate-action engine may dispatch on event kinds. If execution or
# valuation imports the individual handlers, the `if dividend / if merger /
# if reduction` scatter this clause forbids has already happened.
CORPORATE_ACTION_ENGINE_MODULE = "core.b0_corporate_actions"
CORPORATE_ACTION_PRIVATE_SYMBOLS: tuple[str, ...] = (
    "handle_stock_dividend", "handle_capital_reduction", "handle_merger",
    "handle_share_conversion", "handle_par_value_change",
    "handle_cash_capital_increase", "HANDLER_FUNCS",
)


def assert_no_scattered_dispatch(module_symbols: Mapping[str, Iterable[str]]) -> None:
    """`module_symbols` maps module name -> identifiers it references.

    Downstream stages must consume an already-transformed portfolio state, not
    re-derive it per event type.
    """
    offenders = {}
    for module, symbols in module_symbols.items():
        if module == CORPORATE_ACTION_ENGINE_MODULE:
            continue
        hit = sorted(set(symbols) & set(CORPORATE_ACTION_PRIVATE_SYMBOLS))
        if hit:
            offenders[module] = hit
    if offenders:
        raise MasterPreregViolation(
            f"M-1: {offenders} dispatch on corporate-action kinds directly. "
            f"Only {CORPORATE_ACTION_ENGINE_MODULE} may; every other stage takes "
            f"a validated transformed state."
        )


# --- M-2 · L2 termination taxonomy -------------------------------------------

L2_SUPPORTED = "SUPPORTED"
L2_NOT_SUPPORTED = "NOT_SUPPORTED"
L2_NOT_EVALUABLE = "NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK"
# v1.21. The two outcomes Master v1.20 6.1.14 already defines in words. They
# are added to the MACHINE vocabulary and nothing is renamed or generalised: the
# first sealed L2 run terminated in F-CA-C and could not record its own result,
# because the registry could only express three outcomes and none of them was
# true. A `RUN_INVALID_*` family is deliberately NOT created - it would reopen
# which defects are INVALID vs NOT_EVALUABLE, which consume the observation, and
# how they take precedence, none of which is in question here.
L2_NOT_EVALUABLE_CA_BLOCK = "NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK"
L2_RUN_INVALID_CONFORMANCE = "RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE"

L2_OUTCOMES: tuple[str, ...] = (
    L2_SUPPORTED, L2_NOT_SUPPORTED, L2_NOT_EVALUABLE,
    L2_NOT_EVALUABLE_CA_BLOCK, L2_RUN_INVALID_CONFORMANCE,
)
# 6.1.14 F-CA-C: a run that ended here proved nothing about the strategy and
# must never be read as evidence about it.
L2_NON_EVIDENTIAL_OUTCOMES: tuple[str, ...] = (
    L2_NOT_EVALUABLE, L2_NOT_EVALUABLE_CA_BLOCK, L2_RUN_INVALID_CONFORMANCE,
)

# `Validated` belongs to L3 and may never be written at L2 (B-18 §0.1).
L2_FORBIDDEN_WORDS: tuple[str, ...] = (
    "VALIDATED", "STATISTICALLY PROVEN", "OOS EDGE CONFIRMED", "OUT-OF-SAMPLE",
)


def classify_l2_termination(exc: BaseException | None) -> str:
    """A deterministic data/reconstruction abort is NOT a strategy failure.

    Calling it `Not Supported` would record a verdict about the strategy that the
    run never actually produced — and would then trigger the no-post-hoc-rescue
    rule, permanently burning the window over a data gap.
    """
    if exc is None:
        raise UnspecifiedBehaviour(
            "M-2/M-3: the outcome of a run that terminated normally is decided by "
            "the V-4 gate, not by this function."
        )
    from core.b0_corporate_actions import CorporateActionError
    from core.b0_frozen_spec import FrozenSpecViolation

    if isinstance(exc, (CorporateActionError, FrozenSpecViolation)):
        return L2_NOT_EVALUABLE
    raise UnspecifiedBehaviour(
        f"M-3: {type(exc).__name__} is not a termination mode the master "
        f"preregistration classifies. It must be ruled on before it can be "
        f"reported — it must not default to {L2_NOT_SUPPORTED}."
    )


def assert_l2_wording(text: str) -> None:
    upper = text.upper()
    for word in L2_FORBIDDEN_WORDS:
        if word in upper:
            raise MasterPreregViolation(
                f"L2 output may not contain {word!r}. L2 is retrospective on a "
                f"window that prior research already touched; `Validated` is "
                f"reserved for L3."
            )


@dataclass(frozen=True)
class DataRepair:
    """A repair that may permit re-running the same Frozen B0 after M-2.

    Every field is a condition the user ruled on; none has a default, so a repair
    cannot be declared admissible by omission.
    """
    description: str
    independent_source: str          # where the corrected data comes from
    scope: str                       # "event_class" | "whole_source"
    performance_consulted: bool      # must be False
    selected_by_portfolio_exposure: bool   # must be False

    ADMISSIBLE_SCOPES: ClassVar[tuple[str, ...]] = ("event_class", "whole_source")


def assert_repair_admissible(repair: DataRepair) -> None:
    """Repair must be blind to performance and to what B0 happened to hold."""
    if not repair.description.strip() or not repair.independent_source.strip():
        raise MasterPreregViolation(
            "M-2: a repair must name what was wrong and the independent source "
            "that corrects it.")
    if repair.performance_consulted:
        raise MasterPreregViolation(
            "M-2: the repair was chosen after looking at strategy performance. "
            "That makes the re-run a post-hoc rescue, not a repair.")
    if repair.selected_by_portfolio_exposure:
        raise MasterPreregViolation(
            "M-2: repairing only the events B0 happened to hold selects the data "
            "by the portfolio. Repair the whole event class or the whole source.")
    if repair.scope not in repair.ADMISSIBLE_SCOPES:
        raise UnspecifiedBehaviour(
            f"M-2/M-3: repair scope {repair.scope!r} is not defined; admissible "
            f"scopes are {repair.ADMISSIBLE_SCOPES}.")


@dataclass(frozen=True)
class ImplementationConformanceRepair:
    """M-2/R3 (v1.22): the OTHER admissible repair — implementation, not data.

    Run `L2-2520c80aa980d681` could not be expressed by `DataRepair` at all. Its
    defect was that the materializer supplied 13 months of monthly revenue
    against a frozen requirement of 18: the semantics were already frozen and
    correct, the DATA was already present and correct, and there was nothing to
    re-import from an independent source. Forcing it into `DataRepair` would have
    required naming an `independent_source` that does not exist — a fabricated
    provenance field — and would have recorded an implementation defect as a data
    defect, which is the substitution §6.1.14 exists to forbid.

    The scope is deliberately narrow: this repair may only make the
    implementation or its materialized inputs conform to semantics that were
    ALREADY FROZEN BEFORE the invalid run. A repair that changes what B0 means is
    not a repair, it is a new version.
    """
    description: str
    frozen_semantics_reference: str    # the clause the implementation violated
    semantics_frozen_before_run: bool  # must be True
    changes_strategy_semantics: bool   # must be False
    performance_consulted: bool        # must be False
    selected_by_portfolio_exposure: bool   # must be False

    # R3: naming them makes "I did not change the strategy" a checked claim
    # rather than an assurance in a commit message.
    FORBIDDEN_SUBJECTS: ClassVar[tuple[str, ...]] = (
        "factor_definition", "factor_weight", "threshold",
        "portfolio_construction", "execution", "cost", "universe_rule",
        "corporate_action_semantics", "performance_driven_data_policy",
    )


def assert_conformance_repair_admissible(
        repair: ImplementationConformanceRepair) -> None:
    """R3: conformance only. Anything that moves the specification is refused."""
    if not repair.description.strip():
        raise MasterPreregViolation(
            "M-2/R3: a conformance repair must name what failed to conform.")
    if not repair.frozen_semantics_reference.strip():
        raise MasterPreregViolation(
            "M-2/R3: a conformance repair must cite the frozen clause the "
            "implementation violated. Without it there is no way to tell "
            "conformance from a specification change.")
    if not repair.semantics_frozen_before_run:
        raise MasterPreregViolation(
            "M-2/R3: the semantics being conformed to were not frozen before the "
            "invalid run. Conforming to semantics written afterwards is a "
            "specification change wearing a repair's name.")
    if repair.changes_strategy_semantics:
        raise MasterPreregViolation(
            "M-2/R3: this repair changes strategy semantics. Admissible subjects "
            "exclude " + ", ".join(repair.FORBIDDEN_SUBJECTS) + ".")
    if repair.performance_consulted:
        raise MasterPreregViolation(
            "M-2/R3: the repair was chosen after looking at strategy "
            "performance. That makes the re-run a post-hoc rescue.")
    if repair.selected_by_portfolio_exposure:
        raise MasterPreregViolation(
            "M-2/R3: repairing only what B0 happened to hold selects the fix by "
            "the portfolio.")


REPAIR_KINDS: tuple[type, ...] = (DataRepair, ImplementationConformanceRepair)


def assert_any_repair_admissible(repair: object) -> None:
    """Dispatch by KIND, never by duck-typing — the kinds are not interchangeable."""
    if isinstance(repair, DataRepair):
        assert_repair_admissible(repair)
    elif isinstance(repair, ImplementationConformanceRepair):
        assert_conformance_repair_admissible(repair)
    else:
        raise UnspecifiedBehaviour(
            f"M-2/M-3: {type(repair).__name__} is not a defined repair kind; "
            f"defined kinds are {tuple(k.__name__ for k in REPAIR_KINDS)}.")


@dataclass(frozen=True)
class L2Opening:
    """One unsealing of the retrospective window. Recorded whatever happens."""
    opened_at: str
    spec_sha256: str
    code_commit: str
    data_manifest_sha256: str
    outcome: str
    detail: str = ""
    repair_of: str | None = None       # opened_at of the opening this repairs

    def __post_init__(self) -> None:
        if self.outcome not in L2_OUTCOMES:
            raise UnspecifiedBehaviour(
                f"M-2/M-3: {self.outcome!r} is not an L2 outcome; defined "
                f"outcomes are {L2_OUTCOMES}.")
        for f in ("opened_at", "spec_sha256", "code_commit", "data_manifest_sha256"):
            if not str(getattr(self, f)).strip():
                raise MasterPreregViolation(
                    f"M-2: opening registry entry requires {f} — an entry that "
                    f"cannot identify what was run is not a record.")


DEFAULT_REGISTRY_PATH = os.path.join(
    REPO_ROOT, "research", "b0_registry", "l2_opening_registry.jsonl")

# --- R5 (v1.22) - deterministic provenance bytes ------------------------------
# The registry is a RAW-BYTE provenance record and .gitattributes already freezes
# LF as the repository canonical representation for exactly that reason. But
# `record_opening` wrote through a text-mode handle, so on Windows the line
# terminator became CRLF: the same logical record produced different bytes, and
# therefore a different hash, depending on who ran it. Writing in BINARY mode is
# the fix rather than passing a newline= keyword, because a keyword argument can
# be dropped by the next edit while a bytes payload cannot be silently
# translated.
PROVENANCE_RECORD_ENCODING = "utf-8"
PROVENANCE_LINE_TERMINATOR = "\n"


def _assert_not_creating_run_dir(directory: str) -> None:
    """C-59/R4: a generic writer may never become a run-directory creator.

    Before this, that was true only because `resolve_run_dir` happened to be
    called first. Call order is not a structure; this check is at the write, so
    it holds however the writer is reached.
    """
    from core.b0_l2_run_layout import assert_not_creating_run_dir
    assert_not_creating_run_dir(directory)


def canonical_record_bytes(payload: Mapping[str, Any]) -> bytes:
    """The exact bytes one provenance record occupies. Platform-independent."""
    line = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)
    blob = (line + PROVENANCE_LINE_TERMINATOR).encode(PROVENANCE_RECORD_ENCODING)
    # Post-condition, not decoration: one record occupies exactly one line, and
    # the only line terminator in it is the declared one. `json.dumps` escapes
    # breaks inside strings today, so this holds - it is here to turn a future
    # serialiser change into a failure instead of a corrupted append-only file.
    if blob.count(b"\n") != 1 or not blob.endswith(b"\n") or b"\r" in blob:
        raise MasterPreregViolation(
            "provenance: a record must occupy exactly one line terminated by a "
            "single LF; the append-only file cannot be read back otherwise.")
    return blob


def append_provenance_record(path: str, payload: Mapping[str, Any]) -> bytes:
    """Append-only, binary, LF. Returns the bytes written so callers can hash."""
    directory = os.path.dirname(path)
    if directory:
        _assert_not_creating_run_dir(directory)
        os.makedirs(directory, exist_ok=True)
    blob = canonical_record_bytes(payload)
    with open(path, "ab") as fh:            # binary: no newline translation
        fh.write(blob)
    return blob


def write_provenance_json(path: str, payload: Any, *, indent: int = 1) -> bytes:
    """The document form of the same rule, for opening / run provenance files."""
    directory = os.path.dirname(path)
    if directory:
        _assert_not_creating_run_dir(directory)
        os.makedirs(directory, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent)
    blob = (body + PROVENANCE_LINE_TERMINATOR).replace(
        "\r\n", "\n").encode(PROVENANCE_RECORD_ENCODING)
    with open(path, "wb") as fh:
        fh.write(blob)
    return blob


def record_opening(entry: L2Opening, path: str = DEFAULT_REGISTRY_PATH) -> None:
    """Append-only. A NOT_EVALUABLE opening is recorded exactly like any other.

    The registry records every unsealing of the window. Whether an entry COUNTS
    as an effective observation (B-18 4.3) is a separate question answered by
    `effective_observation_count`, not by whether the row exists: R1/R2 of the
    ruling of 2026-08-19 defines one narrow non-consuming case, and pretending
    such a run never happened would be the alternative that destroys provenance.
    """
    append_provenance_record(path, asdict(entry))


def read_registry(path: str = DEFAULT_REGISTRY_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --- R1 / R2 (v1.22) - the narrow non-consumption rule ------------------------
# ONLY this outcome may ever be non-consuming, and only when every condition
# below holds. The rule is deliberately NOT "a crashed run never counts": a run
# that produced a single cross-section of scores over a non-empty universe has
# looked at the window, whatever exception ended it afterwards.
NON_CONSUMING_OUTCOMES: tuple[str, ...] = (L2_RUN_INVALID_CONFORMANCE,)

NON_CONSUMPTION_CONDITIONS: tuple[str, ...] = (
    "zero_effective_decision_observations",
    "no_portfolio_nav_or_performance_produced_or_viewed",
    "defect_is_implementation_or_input_conformance",
    "repair_independent_of_observed_performance",
    "invalid_run_immutable",
    "new_baseline_seal_taken",
    "fresh_explicit_authorization_required",
)

# R1 (v1.23) - condition 2 said "no portfolio / NAV / performance INFORMATION
# produced or viewed" and never defined `information`, which left two readings
# that disagree about the run in hand: the file `nav_series.json` exists and
# holds 141 rows, and every one of those rows is the sealed opening cash with no
# position. Ruled in favour of the strategy-dependent reading, with the carve-out
# stated rather than implied.
CONDITION_2_DEFINITION = (
    "No strategy-dependent portfolio, NAV, return, performance metric, "
    "benchmark comparison, or other strategy-outcome information was produced "
    "or viewed. A deterministic restatement of the sealed opening economic "
    "state, produced before any effective strategy decision, is not "
    "strategy-outcome information.")

# R2. An opening-state restatement is admissible ONLY if every recorded row is
# economically identical to the sealed opening state. Date progression alone
# does not make a record strategy-dependent.
OPENING_STATE_RESTATEMENT_REQUIREMENTS: tuple[str, ...] = (
    "same_cash",
    "zero_positions",
    "no_pending_strategy_generated_holdings",
    "no_target_portfolio",
    "no_executed_portfolio",
    "no_strategy_generated_return",
    "no_benchmark_relative_quantity",
    "no_performance_metric",
)

# R3. Any of these makes condition 2 FALSE. This is NOT "a constant NAV means
# non-consumption": a NAV that is constant at some value the strategy traded its
# way to is strategy-dependent, which is why the test is equality with the
# SEALED OPENING cash rather than mere constancy.
CONDITION_2_NEGATIVE_BOUNDARY: tuple[str, ...] = (
    "any non-empty strategy portfolio",
    "any NAV change caused by B0 decisions or execution",
    "any strategy return",
    "any target or execution result",
    "any performance metric",
    "any benchmark comparison",
    "any other quantity that could only be known after an effective B0 decision",
)

# Row keys that can only exist once an effective B0 decision has been taken.
# Presence alone is disqualifying; the value is not consulted, because a field
# named `sharpe` set to null is still a record shaped by having looked.
STRATEGY_OUTCOME_ROW_KEYS: tuple[str, ...] = (
    "target", "target_portfolio", "executed", "executed_portfolio", "receipt",
    "trades", "fills", "turnover", "selection", "selection_score", "top20",
    "ret", "return", "returns", "period_return", "cumulative_return",
    "cagr", "sharpe", "mdd", "max_drawdown", "benchmark", "excess_return",
    "alpha", "information_ratio", "win_rate", "ic",
)

class ConditionTwoContradicted(MasterPreregViolation):
    """The immutable run artefacts disagree with the attestation."""


def verify_opening_state_restatement(
        run_dir: str | None = None,
        opening_cash: float | None = None,
        run_id: str | None = None) -> dict:
    """R5: condition 2, checked against the run's own immutable artefacts.

    An attestation boolean is a claim by whoever wrote it. This reads the rows
    back and refuses to agree unless every one of them is economically the sealed
    opening state. Raises `ConditionTwoContradicted` on the first row that is
    not; returns the evidence it actually measured when they all are.
    """
    if opening_cash is None:
        opening_cash = float(spec("C_ref"))
    if run_dir is None:
        if run_id is None:
            raise UnspecifiedBehaviour(
                "C-58/R4: condition 2 must be verified against a NAMED run. "
                "There is no default run and no `latest`: resolving identity "
                "through a mutable pointer is how one run's evidence gets read "
                "out from under another.")
        from core.b0_l2_run_layout import resolve_run_dir
        run_dir = resolve_run_dir(run_id)

    nav_path = os.path.join(run_dir, "nav_series.json")
    prog_path = os.path.join(run_dir, "period_progress.jsonl")
    final_path = os.path.join(run_dir, "final_result.json")
    if not os.path.exists(nav_path) and not os.path.exists(prog_path):
        raise ConditionTwoContradicted(
            f"R5: {run_dir} holds no nav_series.json or period_progress.jsonl, "
            f"so condition 2 cannot be verified. Absence of evidence is not "
            f"evidence: the observation counts until the artefacts are present.")

    rows: list[tuple[str, int, dict]] = []
    if os.path.exists(nav_path):
        with open(nav_path, encoding="utf-8") as fh:
            for i, row in enumerate(json.load(fh)):
                rows.append(("nav_series.json", i, row))
    if os.path.exists(prog_path):
        with open(prog_path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if line.strip():
                    rows.append(("period_progress.jsonl", i, json.loads(line)))

    values, positions = set(), set()
    for source, i, row in rows:
        for key in row:
            if key.lower() in STRATEGY_OUTCOME_ROW_KEYS:
                raise ConditionTwoContradicted(
                    f"R3: {source} row {i} carries {key!r}, a quantity that can "
                    f"only be known after an effective B0 decision.")
        for field in ("port_value", "cash_after", "nav"):
            if field in row and row[field] is not None:
                values.add(float(row[field]))
                if float(row[field]) != opening_cash:
                    raise ConditionTwoContradicted(
                        f"R3: {source} row {i} has {field}={row[field]!r} "
                        f"against a sealed opening cash of {opening_cash!r}. A "
                        f"NAV that moved is strategy-outcome information - "
                        f"constancy at some other value would be too.")
        for field in ("positions", "holdings", "shares", "pending_exit",
                      "security_receivables", "stock_dividend_receivable"):
            if field not in row:
                continue
            held = row[field]
            count = held if isinstance(held, (int, float)) else len(held or ())
            positions.add(count)
            if count:
                raise ConditionTwoContradicted(
                    f"R3: {source} row {i} holds {field}={held!r}. A non-empty "
                    f"strategy portfolio makes condition 2 false.")

    from core.b0_l2_run_layout import sha256_of

    artefacts = {}
    for name in ("opening_record.json", "period_progress.jsonl",
                 "nav_series.json", "final_result.json"):
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            sha, size = sha256_of(path)
            artefacts[name] = {
                "path": os.path.relpath(path, REPO_ROOT).replace("\\", "/"),
                "sha256": sha, "bytes": size}

    evidence = {
        "run_id": run_id,
        "run_dir": os.path.relpath(run_dir, REPO_ROOT).replace("\\", "/"),
        "artefacts": artefacts,
        "rows_checked": len(rows),
        "sealed_opening_cash": opening_cash,
        "distinct_value_fields_observed": sorted(values),
        "distinct_position_counts_observed": sorted(positions),
        "strategy_outcome_keys_found": [],
        "requirements_verified": list(OPENING_STATE_RESTATEMENT_REQUIREMENTS),
    }

    if os.path.exists(final_path):
        with open(final_path, encoding="utf-8") as fh:
            final = json.load(fh)
        if final.get("performance_computed") is not False:
            raise ConditionTwoContradicted(
                f"R3: {final_path} records performance_computed="
                f"{final.get('performance_computed')!r}.")
        ev = final.get("evidence", {})
        for field in ("receipts_total", "positions_held_any_period",
                      "corporate_action_transitions_applied"):
            if field in ev and ev[field]:
                raise ConditionTwoContradicted(
                    f"R3: {final_path} records {field}={ev[field]!r}.")
        evidence["final_result_performance_computed"] = False
        evidence["final_result_receipts_total"] = ev.get("receipts_total")
        evidence["final_result_positions_held_any_period"] = ev.get(
            "positions_held_any_period")

    return evidence


# All seven are required. They are split by WHICH MECHANISM CAN ACTUALLY CHECK
# THEM: 1-5 are facts about a run that already ended and are attested from its
# immutable artefacts; 6-7 are preconditions on the NEXT opening, and a boolean
# written before the new seal exists would be an undertaking dressed up as an
# observation. Comparing the two seal identities at reopening is the stronger
# check, so 6-7 are enforced at the call site instead of self-attested.
NON_CONSUMPTION_ENFORCEMENT: Mapping[str, str] = {
    "zero_effective_decision_observations": "attested",
    # R5: the boolean summarises; `verify_opening_state_restatement` decides.
    "no_portfolio_nav_or_performance_produced_or_viewed":
        "attested_and_verified",
    "defect_is_implementation_or_input_conformance": "attested",
    "repair_independent_of_observed_performance": "attested",
    "invalid_run_immutable": "attested",
    "new_baseline_seal_taken": "assert_reopening_admissible",
    "fresh_explicit_authorization_required": "assert_reopening_admissible",
}

ATTESTED_CONDITIONS: tuple[str, ...] = tuple(
    c for c in NON_CONSUMPTION_CONDITIONS
    if NON_CONSUMPTION_ENFORCEMENT[c] in ("attested", "attested_and_verified"))

# The one condition that is not taken on trust when the artefacts are readable.
ARTEFACT_VERIFIED_CONDITIONS: tuple[str, ...] = tuple(
    c for c in NON_CONSUMPTION_CONDITIONS
    if NON_CONSUMPTION_ENFORCEMENT[c] == "attested_and_verified")


@dataclass(frozen=True)
class NonConsumptionAttestation:
    """Recorded ALONGSIDE the opening, never inside it.

    The invalid run own record stays byte-identical, including the
    `l2_opening_consumed: true` the runner wrote conservatively when it
    terminated. That field was the implementer default; this attestation is the
    ruling that supersedes it. Editing the artefact instead would have destroyed
    the evidence that the two ever disagreed.
    """
    opened_at: str                 # identifies the opening; does not mutate it
    run_id: str
    outcome: str
    ruling: str                    # which ruling made this determination
    evidence: str                  # what was measured, not what was hoped
    # R2 conditions 1-5. Conditions 6-7 are enforced by
    # `assert_reopening_admissible`, see NON_CONSUMPTION_ENFORCEMENT.
    zero_effective_decision_observations: bool
    no_portfolio_nav_or_performance_produced_or_viewed: bool
    defect_is_implementation_or_input_conformance: bool
    repair_independent_of_observed_performance: bool
    invalid_run_immutable: bool

    def __post_init__(self) -> None:
        if self.outcome not in NON_CONSUMING_OUTCOMES:
            raise MasterPreregViolation(
                f"R2: {self.outcome!r} can never be non-consuming. Only "
                f"{NON_CONSUMING_OUTCOMES} is in scope, and this rule must not "
                f"be generalised into 'crashed runs never count'.")
        for f in ("opened_at", "run_id", "ruling", "evidence"):
            if not str(getattr(self, f)).strip():
                raise MasterPreregViolation(
                    f"R2: a non-consumption attestation requires {f}.")


def assert_non_consumption_admissible(
        att: NonConsumptionAttestation,
        *,
        run_dir: str | None = None,
        require_artefacts: bool = False) -> dict | None:
    """Conditions 1-5, named individually so a failure says which one.

    R5: condition 2 is not taken on trust. When the run's immutable artefacts
    are readable they are read, and a contradiction raises rather than being
    outvoted by the boolean. `require_artefacts=True` (the reopening gate) also
    refuses when they are missing: at the moment of asking to re-open the
    window, "I cannot check" is not the same as "it checks out".
    """
    for cond in ATTESTED_CONDITIONS:
        if not getattr(att, cond):
            raise MasterPreregViolation(
                f"R2: {att.run_id} is not non-consuming - condition {cond!r} "
                f"does not hold. All {len(NON_CONSUMPTION_CONDITIONS)} "
                f"conditions are required; any one of them failing means the "
                f"observation was spent.")
    for cond, site in NON_CONSUMPTION_ENFORCEMENT.items():
        if site not in ("attested", "attested_and_verified",
                        "assert_reopening_admissible"):
            raise UnspecifiedBehaviour(
                f"R2: condition {cond!r} has no enforcement site.")
    # C-58/R4: the run under adjudication is the one the attestation names.
    resolved = run_dir
    if resolved is None:
        from core.b0_l2_run_layout import run_dir as layout_run_dir
        resolved = layout_run_dir(att.run_id)
    readable = any(os.path.exists(os.path.join(resolved, f))
                   for f in ("nav_series.json", "period_progress.jsonl"))
    if not readable and not require_artefacts:
        return None
    return verify_opening_state_restatement(resolved, run_id=att.run_id)


DEFAULT_NONCONSUMPTION_PATH = os.path.join(
    REPO_ROOT, "research", "b0_registry", "l2_nonconsumption_ledger.jsonl")


def record_non_consumption(att: NonConsumptionAttestation,
                           path: str = DEFAULT_NONCONSUMPTION_PATH) -> None:
    assert_non_consumption_admissible(att)
    append_provenance_record(path, asdict(att))


def read_non_consumption(path: str = DEFAULT_NONCONSUMPTION_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def effective_observation_count(
        registry_path: str = DEFAULT_REGISTRY_PATH,
        attestation_path: str = DEFAULT_NONCONSUMPTION_PATH,
        run_dir: str | None = None) -> int:
    """B-18 4.3: how many times the sealed window has actually been observed.

    An attestation excuses a row only if the ROW own outcome is in scope, so a
    mis-filed attestation cannot retire a SUPPORTED result.
    """
    return len(effective_observations(registry_path, attestation_path, run_dir))


def effective_observations(
        registry_path: str = DEFAULT_REGISTRY_PATH,
        attestation_path: str = DEFAULT_NONCONSUMPTION_PATH,
        run_dir: str | None = None) -> tuple[str, ...]:
    """WHICH runs consumed an observation, not merely how many.

    A count alone cannot be checked against reality: `== 1` is satisfied by any
    run at all. The identity set makes the governed statement testable - the one
    effective observation of the Frozen B0 window is a NAMED run.
    """
    excused = set()
    for a in read_non_consumption(attestation_path):
        att = NonConsumptionAttestation(**a)
        assert_non_consumption_admissible(att, run_dir=run_dir)
        excused.add(att.opened_at)
    out = []
    for row in read_registry(registry_path):
        if row["opened_at"] in excused and row["outcome"] in NON_CONSUMING_OUTCOMES:
            continue
        try:
            run_id = json.loads(row.get("detail") or "{}").get("run_id", "")
        except ValueError:
            run_id = ""
        out.append(run_id or row["opened_at"])
    return tuple(out)


def assert_rerun_admissible(
        previous: L2Opening,
        repair: "DataRepair | ImplementationConformanceRepair | None") -> None:
    """Which repair KIND is admissible is decided by how the run ended.

    R3: the kinds are not interchangeable. Accepting a `DataRepair` for a
    conformance failure would record an implementation defect as a data defect,
    and accepting a conformance repair for a reconstruction block would let a
    missing source be closed by editing code.
    """
    if previous.outcome in (L2_SUPPORTED, L2_NOT_SUPPORTED):
        raise MasterPreregViolation(
            f"no-post-hoc-rescue: the window already produced "
            f"{previous.outcome}. A changed specification is a new version "
            f"(B1, B2 ...) whose primary evidence must be L3, not this window."
        )
    if previous.outcome == L2_RUN_INVALID_CONFORMANCE:
        expected: type = ImplementationConformanceRepair
        why = ("6.1.14 F-CA-C: the semantics were already frozen and the data "
               "was already present; what failed was the implementation")
    else:
        expected = DataRepair
        why = ("M-2: a reconstruction block is a DATA gap and is closed by an "
               "independent source, not by changing code")
    if repair is None:
        raise MasterPreregViolation(
            f"M-2: re-running after {previous.outcome} requires a "
            f"{expected.__name__}; re-running unchanged would abort identically.")
    if not isinstance(repair, expected):
        raise MasterPreregViolation(
            f"M-2/R3: {previous.outcome} requires a {expected.__name__}, not a "
            f"{type(repair).__name__} - {why}.")
    assert_any_repair_admissible(repair)


def assert_reopening_admissible(
        previous: L2Opening,
        repair: "DataRepair | ImplementationConformanceRepair | None",
        *,
        previous_baseline_seal_sha256: str,
        new_baseline_seal_sha256: str,
        authorization_reference: str,
        attestation: "NonConsumptionAttestation | None" = None,
        run_dir: str | None = None) -> None:
    """R2 conditions 6 and 7, enforced rather than attested.

    A boolean saying "a new seal was taken" is worth nothing next to comparing
    the two seal identities, and 6.1.14 says explicitly that the clause does not
    itself grant a retry - so the authorization must be NAMED at the call site.
    """
    assert_rerun_admissible(previous, repair)
    assert set(NON_CONSUMPTION_CONDITIONS) - set(ATTESTED_CONDITIONS) == {
        "new_baseline_seal_taken", "fresh_explicit_authorization_required"}
    for name, value in (("previous_baseline_seal_sha256",
                         previous_baseline_seal_sha256),
                        ("new_baseline_seal_sha256", new_baseline_seal_sha256),
                        ("authorization_reference", authorization_reference)):
        if not str(value).strip():
            raise MasterPreregViolation(f"R2: re-opening requires {name}.")
    if previous_baseline_seal_sha256 == new_baseline_seal_sha256:
        raise MasterPreregViolation(
            "R2 condition 6: re-opening requires a NEW Baseline Seal. The "
            "proposed opening binds the same baseline the invalid run bound, "
            "which means nothing was actually repaired and re-sealed.")
    # R5: if the previous run is being carried as non-consuming, the artefacts
    # that justify that must be present AND must agree, here, at the gate.
    if previous.outcome in NON_CONSUMING_OUTCOMES:
        claims = ([attestation] if attestation is not None
                  else [NonConsumptionAttestation(**a)
                        for a in read_non_consumption()
                        if a["opened_at"] == previous.opened_at])
        if not claims:
            raise MasterPreregViolation(
                f"R2: {previous.outcome} is only non-consuming under an "
                f"attestation, and none is recorded for {previous.opened_at}. "
                f"Without one the observation was spent.")
        for claim in claims:
            assert_non_consumption_admissible(claim, run_dir=run_dir,
                                              require_artefacts=True)


# --- M-3 · no specification-by-code ------------------------------------------
# Every knob B0 is permitted to have is enumerated here, sourced from the module
# that froze it. `spec()` deliberately takes no `default` argument: a default is
# precisely the mechanism by which an undefined behaviour becomes a silent
# choice.

def _spec_registry() -> dict[str, Any]:
    from core import b0_corporate_actions as ca
    from core import b0_cost_model as cost
    from core import b0_decision as dec
    from core import b0_eligibility as elig
    from core import b0_execution as ex
    from core import b0_features as feat
    from core import b0_frozen_spec as fs
    from core import b0_canonical_hash as chash
    from core import b0_declaration_conformance as conform
    from core import b0_listing_spell as spell
    from core import b0_market_state as ms
    from core import b0_provenance as prov
    from core import b0_share_unit_adjustment as sua
    from core import b0_bonus_share_source as bsrc
    from core import b0_l2_run_layout as layout
    from core import b0_opening_state as opn
    from core import b0_corporate_actions as ca
    from core import b0_valuation_source as vsrc
    prereg_modules = NORMATIVE_MODULES
    from core import b0_pit_observability as pit
    from core import b0_state as st

    return {
        # B-06 / B-12 execution policy
        "C_ref": 2_000_000.0,
        "N_target": 20,
        "w_target": 0.05,
        "w_max": 0.05,
        "X_buy": 0.01,
        "X_sell": 0.01,
        "entry_eligibility_horizon_days": 1,
        "adv_floor_multiple": 5.0,          # w_target / X_buy
        "odd_lot_enabled": True,
        "ledger_unit": "shares",
        "buy_shortfall_policy": "cash",
        "sell_shortfall_policy": "pending_exit_carry_forward",
        "reweight_when_under_target_breadth": False,
        "leverage_allowed": False,
        "negative_cash_allowed": False,
        # B-09 selection
        "concepts": ("Quality", "Growth", "Value", "Momentum"),
        "concept_weighting": "equal",
        "selection_free_parameters": 0,
        "lookback_L_months": 18,
        "first_eligible_decision_month": "2014-07",
        "window_months": 141,
        "window_start": "2014-07-31",
        "window_end": "2026-03-31",
        # v1.15 · C-48 · the `pbr_tse` lineage ruling (R1-R7). Unlike C-16..C-36
        # this one is a DECISION, not a recovered omission: the master was silent
        # on what an admissible 2019+ source is, and silence had to be replaced by
        # a sentence. It adds no free parameter — the era boundary is the one
        # §2.8.3 already fixed for prices, and every alternative it names is
        # forbidden rather than selectable.
        "value_definition": vsrc.VALUE_DEFINITION,
        "value_pbr_lineage": vsrc.VALUATION_LINEAGE,
        "value_pbr_lineage_boundary": vsrc.LINEAGE_BOUNDARY,
        "value_pbr_official_boards": vsrc.OFFICIAL_BOARDS,
        "value_pbr_tej_substitution_allowed": vsrc.TEJ_SUBSTITUTION_ALLOWED,
        "value_pbr_runtime_fetch_allowed": vsrc.RUNTIME_FETCH_ALLOWED,
        "value_pbr_parser_version": vsrc.VALUATION_PARSER_VERSION,
        "value_pbr_missing_value_policy": vsrc.MISSING_VALUE_POLICY,
        "value_pbr_forbidden_gap_repairs": vsrc.FORBIDDEN_GAP_REPAIRS,
        "value_pbr_board_attribution_source": vsrc.BOARD_ATTRIBUTION_SOURCE,
        "value_pbr_current_listing_label_allowed":
            vsrc.CURRENT_LISTING_LABEL_ALLOWED,
        "value_pbr_tpex_vintage_first_session":
            vsrc.TPEX_VINTAGE_DISCLOSURE_FIRST_SESSION,
        "value_pbr_tpex_vintage_may_be_inferred":
            vsrc.TPEX_VINTAGE_MAY_BE_INFERRED,
        # v1.16 · C-49 · the same ruling for `per_tse`, taken on its own evidence
        # rather than by analogy. PE is not PBR with a different numerator: it has
        # a domain (C-17: PE > 0), and both sources therefore carry a large
        # legitimate NA class that B/M does not have. Reconciled separately before
        # closing — see §11 C-49.
        "value_ratios": vsrc.RATIOS,
        "value_per_lineage": vsrc.PER_VALUATION_LINEAGE,
        "value_per_tej_substitution_allowed": vsrc.TEJ_SUBSTITUTION_ALLOWED,
        "valuation_sentinel_zero_is_undefined": vsrc.SENTINEL_ZERO_IS_UNDEFINED,
        "valuation_sentinel_zero_eras": vsrc.SENTINEL_ZERO_ERAS,
        # v1.17 · C-50 · share-unit price adjustment (R1-R8). The criterion is a
        # deterministic transformation of an EXISTING HOLDER's shares, never a
        # change in shares outstanding — so `share_multiplier != 1` is not
        # sufficient, and dilution never adjusts a price series.
        "share_unit_adjustment_basis": sua.ADJUSTMENT_BASIS,
        "share_unit_eligible_kinds": sua.ELIGIBLE_KINDS,
        "share_unit_ineligible_kinds": sua.INELIGIBLE_KINDS,
        "share_unit_identity_change_kinds": sua.IDENTITY_CHANGE_KINDS,
        "share_unit_adjusted_consumers": sua.ADJUSTED_CONSUMERS,
        "share_unit_raw_consumers": sua.RAW_CONSUMERS,
        "share_unit_excluded_from_factor": sua.EXCLUDED_FROM_FACTOR,
        "share_unit_boundary_field": sua.BOUNDARY_FIELD,
        "share_unit_not_boundary_field": sua.NOT_BOUNDARY_FIELD,
        # v1.18 · C-51 · the holder multiplier C-50 needed and no registered
        # artefact carried. Both exchanges publish the holder-level ratio
        # directly, and their own field layout separates it from the employee
        # bonus and cash-increase legs exactly as R2 had already ruled — so no
        # shares-outstanding denominator is reconstructed anywhere.
        "bonus_share_official_field": bsrc.OFFICIAL_BONUS_FIELD,
        "bonus_share_official_endpoint": bsrc.OFFICIAL_ENDPOINT,
        "bonus_share_unit": bsrc.BONUS_UNIT,
        "bonus_share_conversion": bsrc.CANONICAL_CONVERSION,
        "bonus_share_forbidden_sources": bsrc.FORBIDDEN_MULTIPLIER_SOURCES,
        "bonus_share_parser_version": bsrc.BONUS_PARSER_VERSION,
        "bonus_share_importer_version": bsrc.BONUS_IMPORTER_VERSION,
        "bonus_share_dispositions": bsrc.DISPOSITIONS,
        "bonus_share_pre_listing_disposition": bsrc.PRE_LISTING_DISPOSITION,
        "bonus_share_board_attribution_source": bsrc.BOARD_ATTRIBUTION_SOURCE,
        "bonus_share_current_listing_label_allowed":
            bsrc.CURRENT_LISTING_LABEL_ALLOWED,
        "bonus_share_event_date_normalization": bsrc.EVENT_DATE_NORMALIZATION,
        "bonus_share_nearest_date_matching_allowed":
            bsrc.NEAREST_DATE_MATCHING_ALLOWED,
        "bonus_share_date_tolerance_days": bsrc.DATE_TOLERANCE_DAYS,
        # v1.19 · C-53 · the opening-state seam. A boundary rule for period 1
        # and nothing else: two datings of one economic state, both bound, and
        # no generic facility for re-dating a portfolio.
        "opening_state_registered_date": opn.REGISTERED_OPENING_STATE_DATE,
        "opening_state_canonical_date": opn.CANONICAL_OPENING_STATE_DATE,
        "opening_state_normalization_scope": opn.NORMALIZATION_SCOPE,
        "opening_state_economic_fields": opn.PORTFOLIO_ECONOMIC_FIELDS,
        "opening_state_permitted_date_fields":
            opn.PERMITTED_DATE_METADATA_FIELDS,
        # v1.20 - C-54 - the corporate-action STATE TRANSITION. The v1.19
        # baseline declared five holder-affecting kinds and shipped only
        # their classifiers; a classification is not a transition, and the
        # gap was a silent NAV error waiting for the first sealed run.
        "ca_transition_authority": "core.b0_corporate_actions",
        "ca_holder_affecting_kinds": ca.holder_affecting_kinds(),
        "ca_identity_changing_kinds": ca.IDENTITY_CHANGING_KINDS,
        "ca_same_security_share_kinds": ca.SAME_SECURITY_SHARE_KINDS,
        "ca_required_transition_fields": {
            k: v for k, v in sorted(ca.REQUIRED_FIELDS.items())},
        "ca_state_dimensions": (
            "tradable_positions", "available_cash",
            "security_receivables", "cash_receivables",
            "pending_exits", "applied_corporate_action_event_ids"),
        "ca_owned_tradable_spendable_distinct": True,
        "ca_valuation_basis": "RAW_OBSERVED",
        "ca_fractional_entitlement_policy": "retain_as_non_tradable_claim",
        "ca_rounding_at_transition_allowed": False,
        "ca_nearest_date_event_ordering_allowed": False,
        "ca_invariants": tuple("I-CA-%02d" % i for i in range(1, 16)),
        "ca_failure_classes": ("F-CA-A", "F-CA-B", "F-CA-C"),
        # v1.21 - C-55 - 4.1a input sufficiency. Requirements are DERIVED
        # from the frozen members, so a producer cannot drift away from the
        # computation it feeds without turning a test red.
        "feature_input_requirements": {
            k: tuple(sorted(v.items()))
            for k, v in sorted(feat.member_input_requirements().items())},
        "feature_series_requirements": tuple(
            sorted(feat.series_requirements().items())),
        "feature_calendar_indexed_series": feat.CALENDAR_INDEXED_SERIES,
        "feature_missing_period_encoding": feat.MISSING_PERIOD_ENCODING,
        "feature_compressing_missing_periods_allowed":
            feat.COMPRESSING_MISSING_PERIODS_ALLOWED,
        "feature_intentional_zero_margin": feat.INTENTIONAL_ZERO_MARGIN,
        "l2_outcomes": L2_OUTCOMES,
        "l2_non_evidential_outcomes": L2_NON_EVIDENTIAL_OUTCOMES,
        # v1.22 - R1/R2/R3/R5. Non-evidential and non-consuming are DIFFERENT
        # properties: all three non-evidential outcomes prove nothing about the
        # strategy, but only one of them can leave the once-only observation
        # unspent, and only under all seven conditions.
        "l2_non_consuming_outcomes": NON_CONSUMING_OUTCOMES,
        "l2_non_consumption_conditions": NON_CONSUMPTION_CONDITIONS,
        "l2_non_consumption_enforcement": tuple(
            sorted(NON_CONSUMPTION_ENFORCEMENT.items())),
        # v1.23 - C-57. Condition 2 now has a definition and a verifier.
        "l2_condition_2_definition": CONDITION_2_DEFINITION,
        "l2_opening_state_restatement_requirements":
            OPENING_STATE_RESTATEMENT_REQUIREMENTS,
        "l2_condition_2_negative_boundary": CONDITION_2_NEGATIVE_BOUNDARY,
        "l2_strategy_outcome_row_keys": STRATEGY_OUTCOME_ROW_KEYS,
        "l2_artefact_verified_conditions": ARTEFACT_VERIFIED_CONDITIONS,
        # v1.24 - C-58. One run, one immutable directory.
        "l2_run_artefacts": layout.RUN_ARTEFACTS,
        "l2_legacy_run_id": layout.LEGACY_RUN_ID,
        "l2_legacy_run_artefact_sha256": tuple(
            sorted(layout.LEGACY_RUN_ARTEFACT_SHA256.items())),
        "l2_canonical_run_identity": layout.CANONICAL_RUN_IDENTITY,
        "l2_latest_pointer_is_canonical": layout.LATEST_POINTER_IS_CANONICAL,
        # v1.25 - C-59. The opening boundary is an event, and state is derived.
        "l2_opening_claim_fields": layout.OPENING_CLAIM_FIELDS,
        "l2_run_states": layout.RUN_STATES,
        "l2_opening_boundary": "canonical_opening_claim_exclusive_create",
        "l2_execution_claim_artefact": layout.EXECUTION_CLAIM,
        "l2_terminal_result_artefact": layout.TERMINAL_RESULT,
        "l2_attempted_opening_source": "immutable_opening_events_not_terminal_rows",
        # v1.26 - B0.1 / C-60. Corporate-action exposure has a time dimension.
        "ca_exposure_predicate":
            "PortfolioState.exposure_applies(stock_id, event_date, as_of)",
        "ca_exposure_interval_rule": "H.start < E.effective_date <= H.end",
        "ca_exposure_spell_driver": "underlying_tradable_shares",
        "ca_claim_only_state_is_exposure": False,
        "ca_caller_declared_exposure_is_authoritative": False,
        "ca_same_spell_must_cover_event_and_application": True,
        "l2_repair_kinds": tuple(k.__name__ for k in REPAIR_KINDS),
        "l2_conformance_repair_forbidden_subjects":
            ImplementationConformanceRepair.FORBIDDEN_SUBJECTS,
        "provenance_record_encoding": PROVENANCE_RECORD_ENCODING,
        "provenance_line_terminator": PROVENANCE_LINE_TERMINATOR,
        # B-14 cost
        "commission_rate": cost.COMMISSION_RATE,
        "min_fee": cost.MIN_FEE,
        "tax_rate": cost.TAX_RATE,
        "impact_k": cost.IMPACT_K,
        # O-1 / V-5 / V-6
        "chip_semantics": fs.CHIP_SEMANTICS,
        "sharpe_metric_name": fs.SHARPE_METRIC_NAME,
        "risk_free_rate": fs.RISK_FREE_RATE,
        "cash_earns_interest": fs.CASH_EARNS_INTEREST,
        "l3_first_checkpoint_months": fs.L3_FIRST_CHECKPOINT_MONTHS,
        "l3_checkpoint_interval_months": fs.L3_CHECKPOINT_INTERVAL_MONTHS,
        # W-1..W-4 corporate actions
        "cash_capital_increase_subscribe": ca.CASH_CAPITAL_INCREASE_SUBSCRIBE,
        "zero_day_receivable_allowed": ca.ZERO_DAY_RECEIVABLE_ALLOWED,
        "missing_data_rate_threshold": ca.MISSING_DATA_RATE_THRESHOLD,
        "interpolation_allowed": ca.INTERPOLATION_ALLOWED,
        # M-1 / M-2
        "pipeline_stages": PIPELINE_STAGES,
        "l2_outcomes": L2_OUTCOMES,
        # O-A / O-B / O-C / O-D (closed in P-1a)
        "pre_mark_mandatory_stage": PRE_MARK_MANDATORY_STAGE,
        "corporate_action_stage_guards": CORPORATE_ACTION_STAGE_GUARDS,
        "intraday_sequence": INTRADAY_SEQUENCE,
        "decision_state_source": DECISION_STATE_SOURCE,
        "cash_dividend_credit_event": CASH_DIVIDEND_CREDIT_EVENT,
        "stock_dividend_credit_event": STOCK_DIVIDEND_CREDIT_EVENT,
        "stale_mark_session_tolerance": pit.STALE_MARK_SESSION_TOLERANCE,
        # O-E (closed in P-1a2)
        "trading_calendar_semantics": "observed_sessions_only",
        "security_status_states": ms.SECURITY_STATUSES,
        "unknown_status_is_normal": False,
        "status_availability_rule": "available_from < missing_session (O-E-1)",
        "market_state_sources_require_provenance": True,
        "unflagged_capitalisation_policy": "NOT_RECONSTRUCTIBLE_no_derivation",
        "permanent_disappearance_is_a_concept": False,
        # P-1b rulings (v1.3). Every one of these is a master OMISSION
        # CORRECTION: the semantics already existed in a demoted closure or in
        # the standard definition the closure invoked, and were simply not
        # carried across at freeze time. None of them is a new strategy choice,
        # which is why they add no free parameters — see §11 C-16..C-20.
        "target_drift_policy": ex.TARGET_DRIFT_POLICY,          # C-16
        "peg_definition": "PER_TSE / eps_growth_pct",           # C-17
        "peg_domain": "PE > 0 and eps_growth_pct > 0, else NA",
        "eps_growth_definition": "(EPS_t - EPS_t-4) / abs(EPS_t-4) * 100",  # C-18
        "eps_growth_quarters_back": feat.EPS_GROWTH_QUARTERS_BACK,
        "eps_growth_net_income_fallback": False,
        "feature_orientations": tuple(
            (f.key, f.orientation) for f in feat.FEATURE_GRAPH),  # C-19
        "orientation_is_caller_selectable": False,
        "risk_filter_relocation": "legacy_F10_relocated_not_rechosen",  # C-20
        "net_margin_floor_pct": elig.NET_MARGIN_FLOOR_PCT,
        "risk_layer_complete": elig.RISK_LAYER_COMPLETE,
        "selection_tie_breaks_available": dec.TIE_BREAKS,
        # v1.4 · the A/B/C resolutions (C-21 ~ C-27). Same character as above:
        # every one came from a demoted closure, from the standard definition it
        # invoked, or from the legacy producer — none from a preference.
        "roe_definition":                                               # C-21
            "sum(net_income, 4 quarters) / period_end_equity * 100",
        "roe_requires_positive_equity": True,
        "margin_definition":                                            # C-21
            "sum(profit, 4 quarters) / sum(revenue, 4 quarters) * 100",
        "ttm_quarters": feat.TTM_QUARTERS,
        "balance_sheet_basis": "latest_statement_published_on_or_before_as_of",
        "revenue_yoy_definition":                                       # C-23
            "(revenue_m - revenue_m-12) / abs(revenue_m-12) * 100",
        "momentum_12_1_definition":                                     # C-24
            "(P_t-1 / P_t-13 - 1) * 100, price return, corporate-action adjusted",
        "momentum_uses_total_return": False,
        "adv20_definition":                                             # C-25
            "mean(close * volume) over the 20 most recent OBSERVED sessions",
        "adv20_sessions": st.ADV20_SESSIONS,
        "sigma20d_definition":                                          # C-26
            "std of daily log returns over trailing 20 sessions, PIT, UNANNUALISED",
        "sigma20d_returns": st.SIGMA20D_RETURNS,
        "sigma20d_ddof": st.SIGMA20D_DDOF,
        "sigma20d_annualised": False,
        "pending_exit_cap_basis": ex.PENDING_EXIT_CAP_BASIS,            # C-27
        # v1.5 · C-28 ~ C-35. These are explicit specification COMPLETION, not
        # runtime tunables: each names a convention the specification had left
        # unstated, and none of them is reachable as a parameter — the code
        # accepts one value and rejects every other.
        "sigma20d_ddof_is_sample": st.SIGMA20D_DDOF == 1,               # C-28
        "risk_financial_exemption": elig.RISK_FINANCIAL_EXEMPTION,      # C-29
        "debt_hard_filter_enabled": elig.DEBT_HARD_FILTER_ENABLED,      # C-30
        "cash_quality_filter_enabled": elig.CASH_QUALITY_FILTER_ENABLED,  # C-31
        "cash_quality_alias_allowed": elig.CASH_QUALITY_ALIAS_ALLOWED,
        "buy_priority": ex.BUY_PRIORITY,                                # C-32
        "proportional_scaling_allowed": False,
        "selection_tie_break": dec.SELECTION_TIE_BREAK,                 # C-33
        "selection_sort_key": "(-SelectionScore, stock_id ascending)",
        "forbidden_tie_break_keys": dec.FORBIDDEN_TIE_BREAK_KEYS,
        "share_rounding": ex.SHARE_ROUNDING,                            # C-34
        "w_max_is_hard_cap": True,
        "rounding_shortfall_policy": "cash",
        "percentile_convention": feat.PERCENTILE_CONVENTION,            # C-35
        "percentile_depends_on_row_order": False,
        "current_ratio_floor_enabled": elig.CURRENT_RATIO_FLOOR_ENABLED,  # C-36
        "fundamental_hard_risk_filters": tuple(
            f.key for f in elig.FROZEN_RISK_FILTERS),
        "removed_legacy_risk_legs": elig.REMOVED_LEGACY_RISK_LEGS,
        # v1.11 · O-F / O-G. Four rulings that decide route behaviour, so they
        # are looked up through `spec()` like every other frozen value rather
        # than read off whichever module happens to hold the constant.
        "o_e_1_availability_rule": "available_from < first_missing_session",
        "unexplained_gap_abort_scope": "held_positions_only",
        "status_source_completeness_required": False,
        "status_event_semantics": ms.EVENT_SEMANTICS,
        "status_by_event_semantics": tuple(
            sorted((k, v) for k, v in ms.STATUS_BY_EVENT_SEMANTICS.items())),
        "unknown_event_semantics_fails_closed": (
            ms.STATUS_BY_EVENT_SEMANTICS[ms.UNKNOWN_EVENT_SEMANTICS] is None),
        "book_closure_may_explain_absence": (
            ms.STATUS_BY_EVENT_SEMANTICS[ms.BOOK_CLOSURE] is not None),
        "listing_spell_break_rule": (
            "unexplained_gap_then_reappearance_opens_a_spell_at_the_first_"
            "reobserved_session"),
        "price_lookback_reset_at_spell_start": True,
        "price_lookback_sessions": tuple(
            sorted(spell.PRICE_LOOKBACK_SESSIONS.items())),
        "spell_bridging_tolerance": spell.SPELL_BRIDGING_SESSION_TOLERANCE,
        "reappearance_may_explain_earlier_gap": False,
        "snapshot_delisting_fields_are_audit_only": True,
        # v1.13 · F0-R1 ~ F0-R7. The hash boundary is itself a declaration now,
        # so a change to it moves config_hash like any other ruling. Every value
        # here is DERIVED from the module that implements it (F0-R4): a prose
        # copy of these sentences would be the exact defect F-0 found.
        "config_hash_scope": "complete_machine_readable_declaration_registry",
        "config_hash_is_runtime_subset": False,
        "spec_sha256_scope": "raw_bytes_of_frozen_master_preregistration_document",
        "implementation_identity": (
            "code_commit_sha_plus_explicit_normative_module_hashes"),
        "normative_modules": prereg_modules,
        "declaration_binding_kinds": tuple(
            sorted(conform.binding_kinds().items())),
        "state_hash_scope": "canonical_concrete_input_state_identity",
        "state_hash_is_an_implementation_hash": False,
        "final_manifest_bound_sections": prov.PROVENANCE_SECTIONS,
        "canonical_hash_primitive": chash.CANONICAL_HASH_VERSION,
        "canonical_hash_json_settings": (
            ("ensure_ascii", chash.JSON_ENSURE_ASCII),
            ("separators", chash.JSON_SEPARATORS),
            ("sort_keys", chash.JSON_SORT_KEYS),
        ),
    }


# --- S-1 · is the Selection path fully specified? -----------------------------

def assert_selection_path_is_fully_specified() -> None:
    """S-1's precondition, made checkable rather than asserted.

    S-1 claims the Selection path carries zero RUNTIME TUNABLE free parameters.
    That claim was `PENDING` for as long as any behaviour on the path was
    undetermined: a threshold nobody had chosen yet cannot be shown to be an
    inherited constant.

    What this checks:
      * nothing in the canonical core is registered as UNSPECIFIED;
      * the risk layer declares itself complete, consistently with that;
      * every member of the feature graph has a frozen formula and direction;
      * the conventions that were rulings (C-32 ~ C-35) each admit exactly one
        value, so no call site can select a different one.

    What it does NOT prove: that a production route obeys any of this. That is
    S-2 and S-3b, and both remain PENDING until a route exists. Specification
    completeness and enforcement are different claims, and §11 C-3 records what
    happens when they get merged into one green light.
    """
    from core import b0_decision as dec
    from core import b0_eligibility as elig
    from core import b0_execution as ex
    from core import b0_features as feat
    from core.b0_open_items import OPEN_ITEMS

    if OPEN_ITEMS:
        raise UnspecifiedBehaviour(
            f"S-1: {[i.key for i in OPEN_ITEMS]} are still UNSPECIFIED. The "
            f"free-parameter claim cannot be checked while a behaviour on the "
            f"path has not been decided.")
    if not elig.RISK_LAYER_COMPLETE:
        raise UnspecifiedBehaviour(
            "S-1: the risk layer does not declare itself complete.")

    unformulated = [f.key for f in feat.FEATURE_GRAPH if f.formula is None]
    undirected = [f.key for f in feat.FEATURE_GRAPH if f.orientation is None]
    if unformulated or undirected:
        raise UnspecifiedBehaviour(
            f"S-1: feature members without a frozen formula {unformulated} or "
            f"direction {undirected}.")

    single_valued = {
        "percentile_convention": feat.PERCENTILE_CONVENTIONS,
        "selection_tie_break": dec.TIE_BREAKS,
        "target_drift_policy": ex.DRIFT_POLICIES,
        "buy_priority": ex.BUY_PRIORITIES,
        "share_rounding": ex.SHARE_ROUNDINGS,
    }
    multi = {k: v for k, v in single_valued.items() if len(v) != 1}
    if multi:
        raise MasterPreregViolation(
            f"S-1: {multi} admit more than one value. A convention with a "
            f"selectable alternative is a runtime tunable parameter, whatever "
            f"the documentation calls it.")


def spec(key: str) -> Any:
    """Look up a frozen B0 parameter. Unknown key aborts — there is no default.

    A `default=` argument is deliberately absent: with one, an undefined
    behaviour silently becomes whatever the call site felt was reasonable.
    """
    registry = _spec_registry()
    if key not in registry:
        from core.b0_open_items import OPEN_ITEMS

        known = {i.key: i for i in OPEN_ITEMS}
        if key in known:
            # Already registered as an open item by P-1b: say which question is
            # unanswered rather than only that the key is absent.
            item = known[key]
            raise UnspecifiedBehaviour(
                f"M-3: {key!r} is an OPEN specification item (layer: {item.layer}, "
                f"materiality: {item.materiality}), not a frozen parameter.\n"
                f"  Question: {item.question}\n"
                f"  It must be ruled on and frozen here before any path reads it."
            )
        raise UnspecifiedBehaviour(
            f"M-3: {key!r} is not defined by the master preregistration. "
            f"UNSPECIFIED must abort and be raised as an open item — it must not "
            f"resolve to an implementation default. Register it in "
            f"core.b0_open_items if a canonical-core path reached it."
        )
    return registry[key]


def specified_keys() -> tuple[str, ...]:
    return tuple(sorted(_spec_registry()))


def assert_specified(*keys: str) -> None:
    missing = [k for k in keys if k not in _spec_registry()]
    if missing:
        raise UnspecifiedBehaviour(
            f"M-3: {missing} reached at runtime but are not defined by the master "
            f"preregistration. Abort and open a specification item.")
