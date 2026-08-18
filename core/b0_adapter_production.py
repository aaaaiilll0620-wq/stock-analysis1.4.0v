"""Production adapter (P-2): live sources -> canonical B0 state.

Mirror image of the retrospective adapter, and deliberately the same shape: read,
validate, hand over a `CanonicalDecisionInput`. It decides nothing, and it
imports none of the four canonical layers — checked by AST in
`tests/test_b0_adapter_parity.py`.

The difference between the two adapters is entirely in what has to be PROVEN
about the source, and that difference is the reason B-20 is a real test rather
than a formality:

  * a retrospective source is a file with a vintage, and its danger is that the
    vintage knows the future (§2.8 D-1);
  * a live source is current by construction, and its danger is the opposite —
    that it has no history at all, so a value read today gets silently used as
    though it had been knowable at the decision date.

Hence `_assert_live_source_is_pit_safe`. O-E already ruled that a source which
only knows its latest state is `NOT_PIT_SAFE` and may not enter B0 or be
repaired into it; that ruling exists because `industry_map` is exactly such a
source and 49.4% of names changed sector under it. A production adapter is the
natural place for that defect to re-enter, so the check lives here as well as in
the market-state layer.

B-19 also bears on this module specifically: production is where a runtime
override would be introduced if one ever were. `B0_REGISTERED_OVERRIDES` is empty
(zero authorisations), and this adapter offers no parameter that could carry one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from core.b0_corporate_actions import CorporateActionEvent, Exposure
from core.b0_listing_spell import ListingSpell, assert_spells_declared
from core.b0_market_state import SecurityStatusTable, TradingCalendar
from core.b0_pit_observability import PitPriceObservation
from core.b0_route import (
    ROUTE_KIND_PRODUCTION,
    CanonicalDecisionInput,
    RouteError,
    resolve_as_of,
    run_decision,
)
from core.b0_state import MarketSnapshot, PortfolioState, SourceAttestation


class ProductionAdapterError(RuntimeError):
    """Fail-loud: a live source cannot be turned into canonical state."""


@dataclass(frozen=True)
class ProductionSources:
    """What the live route is allowed to read.

    Same schema as `RetrospectiveSources` — same field names, same units, same
    NA semantics — because P2-3 requires that a field mean one thing across both
    routes. Two dataclasses rather than one because their VALIDATION differs;
    if they ever needed to differ in CONTENT, that would be a specification
    change, not an adapter change.
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
    # O-G. Same field, same meaning as the retrospective route (P2-3).
    listing_spells: Sequence[ListingSpell] = ()


def build_input(sources: ProductionSources,
                portfolio: PortfolioState,
                decision_date: str,
                execution_date: str,
                execution_prices: Mapping[str, float],
                untradable: frozenset[str] = frozenset(),
                ) -> CanonicalDecisionInput:
    """Live sources -> canonical state. No strategy semantics here."""
    as_of = resolve_as_of(decision_date, sources.calendar)
    if portfolio.as_of != as_of:
        raise ProductionAdapterError(
            f"portfolio state is as of {portfolio.as_of} but the canonical "
            f"decision state for {decision_date} is {as_of} (§6.6).")

    _assert_live_source_is_pit_safe(sources)

    snapshot = MarketSnapshot(
        as_of=as_of, attestation=sources.attestation,
        marks=dict(sources.marks), adv20=dict(sources.adv20),
        sigma20d=dict(sources.sigma20d))

    return CanonicalDecisionInput(
        route_kind=ROUTE_KIND_PRODUCTION,
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


def _assert_live_source_is_pit_safe(sources: ProductionSources) -> None:
    """O-E, at the point where a live feed would otherwise smuggle 'now' in."""
    if sources.status_table is not None:
        sources.status_table.source.assert_pit_safe()
    if not str(sources.attestation.provenance_sha256).strip():
        raise ProductionAdapterError(
            "B-21 §8.6: a runtime source that returns unversioned state is not a "
            "qualifying source. A run whose inputs cannot be identified cannot be "
            "replayed, and recording that it was unversioned does not fix it.")
    from core.b0_state import assert_price_state_admissible

    assert_price_state_admissible(sources.attestation, for_sealed_run=False)
    if not sources.attestation.synthetic:
        # O-G, same obligation as the retrospective route (P2-3): a live feed
        # that can quote a 20-session ADV can say which listing those sessions
        # belong to.
        assert_spells_declared(
            {sp.stock_id: sp for sp in sources.listing_spells},
            {"adv20": dict(sources.adv20), "sigma20d": dict(sources.sigma20d)})


def run(sources: ProductionSources,
        portfolio: PortfolioState,
        decision_date: str,
        execution_date: str,
        execution_prices: Mapping[str, float],
        untradable: frozenset[str] = frozenset(),
        *, for_sealed_run: bool):
    """Build canonical state, then hand it to the SHARED core. Nothing else."""
    inp = build_input(sources, portfolio, decision_date, execution_date,
                      execution_prices, untradable)
    if inp.route_kind != ROUTE_KIND_PRODUCTION:        # pragma: no cover
        raise RouteError("adapter mislabelled its own route")
    return run_decision(inp, for_sealed_run=for_sealed_run)
