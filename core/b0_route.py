"""The shared Frozen B0 route (P-2). One engine, two adapters.

§8.7 fixes the shape:

                      ┌─ retrospective adapter
    PIT source ───────┤                          ──> canonical state ──> B0 core
                      └─ production adapter

and states what parity therefore has to measure:

    真正需要 parity 的不是兩套演算法，而是兩個 adapter 是否向 canonical core
    提供相同的 state / config / as_of，並正確消費輸出。

This module is that core's single entry point. It is the ONLY place in the
repository that calls the four canonical layers in sequence, which is what makes
"there is one engine" a structural fact rather than a claim: an adapter cannot
become a second engine without importing layers that
`tests/test_b0_adapter_parity.py` proves it does not import.

WHAT AN ADAPTER MAY DO
    read a source, validate it (PIT, provenance, schema), and hand over a
    `CanonicalDecisionInput`.

WHAT AN ADAPTER MAY NOT DO
    anything on the list in §8.7 and its P-2 extension — feature formulas,
    orientation, percentiles, complete-case, risk or ADV eligibility,
    SelectionScore, ranking, targets, tie-break, share rounding, buy priority,
    sell-first, pending_exit, the 1% cap, corporate-action dispatch, the cost
    formula, or any regime-dependent branch. Every one of those lives behind
    `run_decision`.

ON STAGE ORDER
    M-1 orders `eligibility` before `features`, and this route declares exactly
    that. The feature panel is nonetheless built while the raw state is being
    assembled, because it is a pure function of PIT inputs: nothing downstream
    can change a feature value, so the moment of its computation is
    unobservable. What M-1 actually constrains — exclusion strictly before
    ordering (§4.5) — is honoured, because the eligible set is decided from
    AVAILABILITY before any percentile is taken over VALUES.

    The one member where this could have mattered is `value_ind_pct_b`, which is
    itself cross-sectional. Its cross-section is the PIT industry over the
    supplied universe, not the eligible set — see `build_feature_panel`, where
    the circularity that forces it is recorded.

D-1 REMAINS UNMET, and this route does not work around it. Every run passes the
snapshot attestation through `assert_price_state_admissible`, so a real price
universe still aborts at the input boundary while `price_universe_survivorship`
is outstanding. Fixtures declare themselves synthetic and may not feed a sealed
run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from core import b0_decision as decision
from core import b0_eligibility as eligibility
from core import b0_execution as execution
from core import b0_features as features
from core.b0_canonical_hash import canonical_sha256, canonicalise
from core.b0_corporate_actions import (
    assert_transition_applied,
    CorporateActionEvent,
    Exposure,
    assert_caller_exposures_conform,
    assert_exposure_reconstructible,
)
from core.b0_listing_spell import (
    ListingSpell,
    assert_price_lookbacks_reset,
)
from core.b0_market_state import TradingCalendar
from core.b0_master_prereg import (
    PIPELINE_STAGES,
    assert_corporate_action_precedes_mark,
    assert_decision_inputs_are_prior_session,
    assert_stage_order,
    spec,
    specified_keys,
)
from core.b0_pit_observability import (
    PitPriceObservation,
    assert_no_unexplained_gap_in_holdings,
    stale_mark_report,
)
from core.b0_state import (
    MarketSnapshot,
    PortfolioState,
    assert_price_state_admissible,
    mark_portfolio,
)

ROUTE_KIND_RETROSPECTIVE = "retrospective"
ROUTE_KIND_PRODUCTION = "production"
ROUTE_KINDS: tuple[str, ...] = (ROUTE_KIND_RETROSPECTIVE, ROUTE_KIND_PRODUCTION)


class RouteError(RuntimeError):
    """Fail-loud: the shared route was handed something it must not run on."""


# --- P2-2 · one config, hashed --------------------------------------------------
# There is no per-adapter config object to diverge, because there is no adapter
# config at all: the canonical config IS the frozen spec registry. An adapter
# that wanted a knob would have to add a key to the master preregistration, which
# is a §11 change with a hash change behind it.

def canonical_config() -> dict[str, Any]:
    return {k: spec(k) for k in specified_keys()}


# F0-R7: one primitive. `_stable` / `_hash` are kept as names because the route
# reads better with them, but they are aliases now, not a second implementation.
_stable = canonicalise


def _hash(payload: Any) -> str:
    return canonical_sha256(payload)


def config_hash() -> str:
    """One hash for both routes. Not per-adapter, by construction."""
    return _hash(canonical_config())


# --- P2-1 · one as_of semantics -------------------------------------------------

def resolve_as_of(decision_date: str, calendar: TradingCalendar) -> str:
    """§6.6: decision state comes from the prior COMPLETED trading session.

    Canonical here rather than in each adapter, because "the same decision point"
    is exactly the thing the two routes have to agree on. A retrospective adapter
    reaching for a month-end label while production reaches for the prior close
    would be two different timestamps wearing one name — and the outputs might
    still agree often enough to look like parity.
    """
    sessions = calendar.sessions_through(decision_date)
    prior = [s for s in sessions if str(s) < str(decision_date)]
    if not prior:
        raise RouteError(
            f"§6.6: no completed trading session before {decision_date}; there is "
            f"no PIT state to decide from.")
    return prior[-1]


# --- P2-3 · the canonical input state ------------------------------------------

@dataclass(frozen=True)
class CanonicalDecisionInput:
    """Everything the core needs, and nothing an adapter decided.

    The schema is the contract: a field means the same thing on both routes or
    the state hashes differ. Absence is encoded explicitly (`None`), never as 0
    or as an empty string, because §4.1 acts on the difference.
    """
    route_kind: str
    decision_date: str
    as_of: str
    snapshot: MarketSnapshot
    portfolio: PortfolioState
    pit_inputs: tuple[features.SecurityPitInputs, ...]
    price_observations: tuple[PitPriceObservation, ...]
    corporate_action_events: tuple[CorporateActionEvent, ...]
    exposures: tuple[Exposure, ...]
    execution_date: str
    execution_prices: Mapping[str, float]
    untradable: frozenset[str]
    # O-G. Which listing spell each security is currently in. Empty is legal
    # only where no price-window quantity is supplied; `assert_price_lookbacks_
    # reset` is what makes that conditional real rather than a comment.
    listing_spells: tuple[ListingSpell, ...] = ()

    def __post_init__(self) -> None:
        if self.route_kind not in ROUTE_KINDS:
            raise RouteError(
                f"route_kind must be one of {ROUTE_KINDS}, got {self.route_kind!r}")
        if str(self.as_of) >= str(self.decision_date):
            raise RouteError(
                f"§6.6: as_of {self.as_of} is not strictly before the decision "
                f"date {self.decision_date}.")
        if str(self.execution_date) <= str(self.decision_date):
            raise RouteError(
                f"§6.5: execution happens at the open of the following session; "
                f"{self.execution_date} is not after {self.decision_date}.")
        if self.snapshot.as_of != self.as_of or self.portfolio.as_of != self.as_of:
            raise RouteError(
                f"snapshot/portfolio must be as of {self.as_of}; got "
                f"{self.snapshot.as_of} / {self.portfolio.as_of}.")

    def state_payload(self) -> dict[str, Any]:
        """The hashed view. Deliberately excludes `route_kind`.

        Two routes supplying identical state must hash identically, so the label
        saying which route supplied it cannot be part of the state.
        """
        return {
            "as_of": self.as_of,
            "decision_date": self.decision_date,
            "execution_date": self.execution_date,
            "marks": dict(self.snapshot.marks),
            "adv20": dict(self.snapshot.adv20),
            "sigma20d": dict(self.snapshot.sigma20d),
            "cash": self.portfolio.cash,
            "shares": dict(self.portfolio.shares),
            "pending_exit": dict(self.portfolio.pending_exit),
            "cash_dividend_receivable": self.portfolio.cash_dividend_receivable,
            "stock_dividend_receivable": dict(
                self.portfolio.stock_dividend_receivable),
            "pit_inputs": [
                {"stock_id": s.stock_id,
                 "net_income_by_quarter": s.net_income_by_quarter,
                 "revenue_by_quarter": s.revenue_by_quarter,
                 "gross_profit_by_quarter": s.gross_profit_by_quarter,
                 "eps_by_quarter": s.eps_by_quarter,
                 "period_end_equity": s.period_end_equity,
                 "total_liabilities": s.total_liabilities,
                 "total_assets": s.total_assets,
                 "current_assets": s.current_assets,
                 "current_liabilities": s.current_liabilities,
                 "monthly_revenue": s.monthly_revenue,
                 "month_end_prices": s.month_end_prices,
                 "per_tse": s.per_tse,
                 "pbr_tse": s.pbr_tse,
                 "pit_industry": s.pit_industry}
                for s in sorted(self.pit_inputs, key=lambda x: x.stock_id)],
            "price_observations": [
                {"stock_id": o.stock_id,
                 "price_observed_through": o.price_observed_through,
                 "expected_sessions": o.expected_sessions,
                 "known_status": o.known_status,
                 "status_available_from": o.status_available_from,
                 "explaining_corporate_action": o.explaining_corporate_action,
                 "corporate_action_available_from": o.corporate_action_available_from}
                for o in sorted(self.price_observations, key=lambda x: x.stock_id)],
            "corporate_action_events": [
                {"stock_id": e.stock_id, "kind": e.kind,
                 "ex_or_effective_date": e.ex_or_effective_date,
                 "reconstructibility": e.reconstructibility}
                for e in sorted(self.corporate_action_events,
                                key=lambda x: (x.stock_id, x.ex_or_effective_date))],
            "exposures": [
                {"stock_id": x.stock_id, "held_from": x.held_from,
                 "held_until": x.held_until}
                for x in sorted(self.exposures, key=lambda x: x.stock_id)],
            "execution_prices": dict(sorted(self.execution_prices.items())),
            "untradable": sorted(self.untradable),
            # O-G: the spell start decides which sessions a price window may
            # read, so two runs that disagree about it are not the same state.
            "listing_spells": [
                {"stock_id": sp.stock_id, "start": sp.start,
                 "opened_by": sp.opened_by}
                for sp in sorted(self.listing_spells, key=lambda x: x.stock_id)],
            "attestation": {
                "dataset_id": self.snapshot.attestation.dataset_id,
                "provenance_sha256": self.snapshot.attestation.provenance_sha256,
                "synthetic": self.snapshot.attestation.synthetic},
        }

    def state_hash(self) -> str:
        return _hash(self.state_payload())


# --- the result ----------------------------------------------------------------

# P2-5. Wider than `b0_parity.PARITY_COLUMNS`, which stays untouched: the frozen
# harness keeps its seven-column contract and this route passes a superset for
# its own fixtures.
ROUTE_PARITY_COLUMNS: tuple[str, ...] = (
    "eligible", "score", "rank", "selected",
    "target_shares", "orders", "shares_after", "pending_exit",
    "explicit_fee", "transaction_tax", "impact",
) + tuple(features.required_feature_keys())


@dataclass(frozen=True)
class RouteResult:
    route_kind: str
    decision_date: str
    as_of: str
    config_hash: str
    state_hash: str
    stages: tuple[str, ...]
    panel: features.FeaturePanel
    eligibility: eligibility.EligibilityResult
    scores: Mapping[str, float]
    ranking: tuple[str, ...]
    targets: decision.TargetPortfolio
    target_shares: Mapping[str, int]
    session: execution.SessionResult
    port_value: float
    stale_marks: Mapping[str, Any]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def rows(self) -> dict[str, dict[str, Any]]:
        """Per-security view for B-20 comparison."""
        out: dict[str, dict[str, Any]] = {}
        selected = set(self.targets.selected)
        rank_of = {sid: i for i, sid in enumerate(self.ranking)}
        cost_by_id: dict[str, list[float]] = {}
        for r in self.session.receipts:
            acc = cost_by_id.setdefault(r.stock_id, [0.0, 0.0, 0.0, 0.0])
            acc[0] += r.explicit_fee
            acc[1] += r.transaction_tax
            acc[2] += r.impact
            acc[3] += r.shares if r.side == "buy" else -r.shares
        for sid in sorted(self.panel.values):
            fee, tax, impact, delta = cost_by_id.get(sid, [0.0, 0.0, 0.0, 0.0])
            row: dict[str, Any] = {
                "eligible": sid in self.eligibility.eligible,
                "score": self.scores.get(sid),
                "rank": rank_of.get(sid),
                "selected": sid in selected,
                "target_shares": self.target_shares.get(sid, 0),
                "orders": delta,
                "shares_after": self.session.shares_after.get(sid, 0),
                "pending_exit": self.session.pending_exit_after.get(sid, 0),
                "explicit_fee": fee,
                "transaction_tax": tax,
                "impact": impact,
            }
            row.update({k: self.panel.values[sid].get(k)
                        for k in features.required_feature_keys()})
            out[sid] = row
        return out

    def to_snapshot(self):
        from core.b0_parity import DecisionSnapshot

        return DecisionSnapshot(as_of=self.as_of, config_hash=self.config_hash,
                                state_hash=self.state_hash, rows=self.rows())


# --- the one entry point --------------------------------------------------------

def run_decision(inp: CanonicalDecisionInput, *,
                 for_sealed_run: bool) -> RouteResult:
    """The whole of Frozen B0 for one decision date. Called by both adapters.

    `for_sealed_run` is keyword-only with no default: whether this run may
    produce sealed evidence is a declaration, never an inference.
    """
    stages: list[str] = []

    # --- pit_raw_state ----------------------------------------------------------
    stages.append("pit_raw_state")
    assert_price_state_admissible(inp.snapshot.attestation,
                                  for_sealed_run=for_sealed_run)
    assert_decision_inputs_are_prior_session(
        inp.decision_date,
        {"market_snapshot": inp.as_of, "portfolio_state": inp.as_of})

    convention = spec("percentile_convention")
    panel = features.build_feature_panel(inp.as_of, inp.pit_inputs,
                                         convention=convention)

    # --- corporate_action_transition (O-A: mandatory, both guards) --------------
    stages.append("corporate_action_transition")
    # B0.1 · R2. Economic truth is the canonical portfolio's own spell ledger.
    # `inp.exposures` is retained only as a redundant conformance assertion: a
    # caller that assembles exposure itself is a caller that can assemble it
    # wrongly, which is exactly what happened.
    assert_caller_exposures_conform(inp.exposures, inp.portfolio)
    assert_exposure_reconstructible(inp.corporate_action_events, inp.portfolio,
                                    as_of=inp.as_of)
    # §6.1.2: the stage is the TRANSITION, not the guards around it. The engine
    # runs before the input is built, so what is checked here is that it ran —
    # a classification-only pipeline reaches this line with an untransformed
    # portfolio and stops, which is the defect this clause exists to catch.
    assert_transition_applied(inp.portfolio, inp.corporate_action_events,
                              as_of=inp.as_of)
    # O-F: scoped to EXPOSURE. An unexplained gap in a name B0 does not hold is
    # a diagnostic about an incomplete status source; the same gap in a HELD
    # name is a NAV that cannot be computed, and it aborts here.
    verdicts = assert_no_unexplained_gap_in_holdings(
        inp.as_of, inp.price_observations, inp.portfolio.held_securities)
    # O-G: a price window that reaches past the start of the current listing
    # spell averages two different listings of one code. NA is the required
    # value; a number is not.
    assert_price_lookbacks_reset(
        inp.as_of, {sp.stock_id: sp for sp in inp.listing_spells},
        tuple(sorted({s for o in inp.price_observations
                      for s in o.expected_sessions})),
        {"adv20": dict(inp.snapshot.adv20),
         "sigma20d": dict(inp.snapshot.sigma20d)})

    # --- portfolio_mark ---------------------------------------------------------
    stages.append("portfolio_mark")
    marked = mark_portfolio(inp.portfolio, inp.snapshot, verdicts)

    # --- eligibility (strictly before any ordering, §4.5) ----------------------
    stages.append("eligibility")
    elig = eligibility.evaluate(
        panel, inp.snapshot.adv20, marked.port_value,
        risk_filters=eligibility.frozen_risk_filters(allow_incomplete=False))

    # --- features / selection_score / target_portfolio -------------------------
    stages.append("features")
    stages.append("selection_score")
    scores = decision.score_eligible(panel, elig.eligible, convention=convention)
    ranking = decision.rank(scores, tie_break=spec("selection_tie_break"))
    selected = decision.select(scores, tie_break=spec("selection_tie_break"))

    stages.append("target_portfolio")
    targets = decision.target_portfolio(inp.decision_date, selected)
    decision.assert_no_reweighting(targets.weights)

    # --- order_intents ----------------------------------------------------------
    stages.append("order_intents")
    rounding = spec("share_rounding")
    target_share_counts: dict[str, int] = {}
    for sid, weight in targets.weights.items():
        target_share_counts[sid] = execution.target_shares(
            weight * marked.port_value, inp.snapshot.mark_price(sid),
            share_rounding=rounding)

    # --- execution / costs / post_trade_nav ------------------------------------
    stages.append("execution")
    session = execution.execute_session(
        execution_date=inp.execution_date,
        data_as_of=inp.as_of,
        pre_trade=inp.portfolio,
        target_share_counts=target_share_counts,
        prices=inp.execution_prices,
        adv20=inp.snapshot.adv20,
        sigma20d=inp.snapshot.sigma20d,
        untradable=inp.untradable,
        drift_policy=spec("target_drift_policy"),
        buy_priority=spec("buy_priority"),
        buy_order=ranking,
        x_sell=float(spec("X_sell")),
        x_buy=float(spec("X_buy")))
    stages.append("costs")
    stages.append("post_trade_nav")

    # M-1 / O-A, checked on what actually ran rather than on the module's shape.
    assert_stage_order(stages)
    assert_corporate_action_precedes_mark(stages)

    return RouteResult(
        route_kind=inp.route_kind,
        decision_date=inp.decision_date,
        as_of=inp.as_of,
        config_hash=config_hash(),
        state_hash=inp.state_hash(),
        stages=tuple(stages),
        panel=panel,
        eligibility=elig,
        scores=scores,
        ranking=ranking,
        targets=targets,
        target_shares=target_share_counts,
        session=session,
        port_value=marked.port_value,
        stale_marks=stale_mark_report(verdicts),
        diagnostics={
            "eligibility_counts": elig.counts,
            "peg_coverage": features.peg_availability_report(
                {sid: panel.values[sid]["PEG"] for sid in panel.values}),
            "cost_totals": execution.cost_totals(session.receipts),
            "under_invested_by_breadth":
                targets.diagnostics["under_invested_by_breadth"],
            "pipeline_stages": tuple(PIPELINE_STAGES),
        },
    )


# --- P2-4 · inputs before outputs ----------------------------------------------

def assert_route_parity(production: RouteResult, retrospective: RouteResult, *,
                        float_tol: float = 0.0) -> None:
    """B-20 on two RouteResults. Inputs are compared first, and can abort alone.

    `float_tol` defaults to 0.0 — bit-exact. A non-zero value here would have to
    be justified per column at the call site; §8.5 forbids a global tolerance
    because it lets a definitional difference hide inside rounding.
    """
    from core.b0_parity import assert_parity

    if production.route_kind == retrospective.route_kind:
        raise RouteError(
            f"both results came from the {production.route_kind!r} route; "
            f"comparing a route with itself measures nothing.")
    assert_parity(production.to_snapshot(), retrospective.to_snapshot(),
                  ROUTE_PARITY_COLUMNS, float_tol=float_tol)
