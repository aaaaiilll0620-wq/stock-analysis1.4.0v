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

L2_OUTCOMES: tuple[str, ...] = (L2_SUPPORTED, L2_NOT_SUPPORTED, L2_NOT_EVALUABLE)

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


def record_opening(entry: L2Opening, path: str = DEFAULT_REGISTRY_PATH) -> None:
    """Append-only. A NOT_EVALUABLE opening is recorded exactly like any other.

    The registry counts effective observations (B-18 §4.3), and a run that
    touched the sealed window touched it regardless of how it ended.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True) + "\n")


def read_registry(path: str = DEFAULT_REGISTRY_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def assert_rerun_admissible(previous: L2Opening, repair: DataRepair | None) -> None:
    """Only a NOT_EVALUABLE opening may be re-run on the same window."""
    if previous.outcome in (L2_SUPPORTED, L2_NOT_SUPPORTED):
        raise MasterPreregViolation(
            f"no-post-hoc-rescue: the window already produced "
            f"{previous.outcome}. A changed specification is a new version "
            f"(B1, B2 ...) whose primary evidence must be L3, not this window."
        )
    if repair is None:
        raise MasterPreregViolation(
            "M-2: re-running after a data-reconstruction block requires a repair; "
            "re-running unchanged would abort identically.")
    assert_repair_admissible(repair)


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
    from core import b0_opening_state as opn
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
