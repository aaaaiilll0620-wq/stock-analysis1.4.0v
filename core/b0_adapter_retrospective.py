"""Retrospective adapter (P-2): sealed-window sources -> canonical B0 state.

This module reads history and validates it. It decides nothing.

The whole of its output is a `CanonicalDecisionInput`, which `b0_route` consumes;
every strategy semantic — features, eligibility, scoring, ranking, targets,
execution, cost — happens behind `run_decision` and is therefore shared with the
production adapter by construction rather than by agreement.

The import list below is the enforcement. It contains `b0_route`, `b0_state`,
`b0_market_state` and the corporate-action / PIT-observability TYPES, and it
contains none of `b0_features`, `b0_eligibility`, `b0_decision`,
`b0_execution` — a check `tests/test_b0_adapter_parity.py` performs by AST, on
both adapters, so that "the adapter quietly became a second engine" is a test
failure rather than a code review that did not happen.

WHY THIS ADAPTER EXISTS AT ALL, given it computes nothing: because the two routes
differ in where data comes from and in what can be trusted about it. Retrospective
sources are files with a vintage; production sources are live queries. Those need
different validation, and B-20's real question is whether two different validation
paths hand the core the same state.

D-1. The retrospective route is the one D-1 actually threatens: it replays 141
months of a price universe that, from 2019, contains only securities still listed
at export time. `build_input` therefore refuses to construct a non-synthetic
input while `price_universe_survivorship` is unmet — the abort happens here, at
the source boundary, and not after a NAV has been produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from core.b0_corporate_actions import CorporateActionEvent, Exposure
from core.b0_listing_spell import ListingSpell, assert_spells_declared
from core.b0_market_state import SecurityStatusTable, TradingCalendar
from core.b0_pit_observability import PitPriceObservation
from core.b0_price_universe import PriceSourceContract, assert_price_source_admissible
from core.b0_route import (
    ROUTE_KIND_RETROSPECTIVE,
    CanonicalDecisionInput,
    RouteError,
    resolve_as_of,
    run_decision,
)
from core.b0_state import MarketSnapshot, PortfolioState, SourceAttestation


class RetrospectiveAdapterError(RuntimeError):
    """Fail-loud: a historical source cannot be turned into canonical state."""


@dataclass(frozen=True)
class RetrospectiveSources:
    """What a sealed-window replay is allowed to read.

    Every field is already-validated PIT material. The adapter's job is to check
    that claim and to shape it, not to compute from it.
    """
    calendar: TradingCalendar
    status_table: SecurityStatusTable | None
    attestation: SourceAttestation
    marks: Mapping[str, float]
    adv20: Mapping[str, float]
    sigma20d: Mapping[str, float]
    pit_inputs: Sequence[object]                  # features.SecurityPitInputs
    price_observations: Sequence[PitPriceObservation]
    corporate_action_events: Sequence[CorporateActionEvent] = ()
    exposures: Sequence[Exposure] = ()
    # D1-6. Optional only so a synthetic fixture need not invent one; a
    # non-synthetic replay without it aborts in `_assert_replayable`, because
    # "which price corpus was this?" is exactly what D-1 turns on.
    price_source: PriceSourceContract | None = None
    # O-G. Which listing spell each security is currently in. A real replay must
    # declare one for every security it supplies a price window for; a synthetic
    # fixture need not, for the same reason it need not name a price corpus.
    listing_spells: Sequence[ListingSpell] = ()


def build_input(sources: RetrospectiveSources,
                portfolio: PortfolioState,
                decision_date: str,
                execution_date: str,
                execution_prices: Mapping[str, float],
                untradable: frozenset[str] = frozenset(),
                ) -> CanonicalDecisionInput:
    """Sealed-window sources -> canonical state. No strategy semantics here."""
    as_of = resolve_as_of(decision_date, sources.calendar)
    if portfolio.as_of != as_of:
        raise RetrospectiveAdapterError(
            f"portfolio state is as of {portfolio.as_of} but the canonical "
            f"decision state for {decision_date} is {as_of} (§6.6). The adapter "
            f"does not re-date a portfolio; it reports the mismatch.")

    _assert_replayable(sources)

    snapshot = MarketSnapshot(
        as_of=as_of, attestation=sources.attestation,
        marks=dict(sources.marks), adv20=dict(sources.adv20),
        sigma20d=dict(sources.sigma20d))

    return CanonicalDecisionInput(
        route_kind=ROUTE_KIND_RETROSPECTIVE,
        decision_date=decision_date,
        as_of=as_of,
        snapshot=snapshot,
        portfolio=portfolio,
        pit_inputs=tuple(sources.pit_inputs),
        price_observations=tuple(sources.price_observations),
        corporate_action_events=tuple(sources.corporate_action_events),
        exposures=tuple(sources.exposures),
        execution_date=execution_date,
        execution_prices=dict(execution_prices),
        untradable=frozenset(untradable),
        listing_spells=tuple(sources.listing_spells),
    )


def _assert_replayable(sources: RetrospectiveSources) -> None:
    """D-1 and O-E, checked before any state is built.

    The blocking-requirement check duplicates one the route also performs. That
    is deliberate: the route's check is the backstop, and this one names the
    retrospective route specifically, because a replay is where a survivorship-
    filtered universe does its damage — 87 of the 141 window months (§2.8).
    """
    from core.b0_frozen_spec import unmet_blocking_requirements

    if not sources.attestation.synthetic:
        unmet = [r.key for r in unmet_blocking_requirements()
                 if r.key not in sources.attestation.satisfied_blocking_requirements]
        if unmet:
            raise RetrospectiveAdapterError(
                f"§2.8: the retrospective route may not replay real history while "
                f"{unmet} is unmet. From 2019 the price export contains only "
                f"securities still listed at export time, so every cross-sectional "
                f"quantity in the replay — including the equal-weight universe "
                f"benchmark row ① divides by — is biased upward.")
        # D1-6: naming the corpus is not optional for a real replay, and a
        # quarantined one fails loudly here rather than being quietly passed
        # over by cache selection or a runtime overlay.
        if sources.price_source is None:
            raise RetrospectiveAdapterError(
                "D1-6: a non-synthetic replay must declare which price corpus it "
                "read. An unnamed source cannot be shown not to be the "
                "survivorship-filtered one.")
        assert_price_source_admissible(sources.price_source)
        # O-G: the adapter holds the price history, so it is the layer that can
        # say which listing a 20-session window sits inside.
        assert_spells_declared(
            {sp.stock_id: sp for sp in sources.listing_spells},
            {"adv20": dict(sources.adv20), "sigma20d": dict(sources.sigma20d)})
    if sources.status_table is not None:
        sources.status_table.source.assert_pit_safe()


def run(sources: RetrospectiveSources,
        portfolio: PortfolioState,
        decision_date: str,
        execution_date: str,
        execution_prices: Mapping[str, float],
        untradable: frozenset[str] = frozenset(),
        *, for_sealed_run: bool):
    """Build canonical state, then hand it to the SHARED core. Nothing else."""
    inp = build_input(sources, portfolio, decision_date, execution_date,
                      execution_prices, untradable)
    if inp.route_kind != ROUTE_KIND_RETROSPECTIVE:      # pragma: no cover
        raise RouteError("adapter mislabelled its own route")
    return run_decision(inp, for_sealed_run=for_sealed_run)
