"""P-2 · the shared route: stage order, wired guards, and the D-1 boundary.

`tests/test_b0_adapter_parity.py` measures whether the two adapters agree. This
file tests the thing they agree THROUGH.

The tests that matter most here are the S-3b ones. Until P-2 the corporate-action
and price-observability guards existed and were unit-tested, but nothing that
produced a NAV called them — §11 C-3 split S-3 into S-3a and S-3b precisely so
that "the data is in place" could not be read as "the guard is enforced". These
tests close that gap from the other side: they show the guards abort a run that
would otherwise have produced a portfolio.

Every fixture is synthetic and attests itself so.
"""

import pytest

from core.b0_corporate_actions import (
    NOT_RECONSTRUCTIBLE,
    CorporateActionError,
    CorporateActionEvent,
    Exposure,
)
from core.b0_master_prereg import PIPELINE_STAGES, MasterPreregViolation
from core.b0_pit_observability import PitPriceObservation, PriceObservabilityError
from core.b0_route import (
    CanonicalDecisionInput,
    RouteError,
    canonical_config,
    config_hash,
    resolve_as_of,
    run_decision,
)
from core.b0_state import CoreStateError, MarketSnapshot, PortfolioState
from tests.test_b0_adapter_parity import (
    ADV20,
    AS_OF,
    ATTESTATION,
    DECISION,
    EXEC_DAY,
    EXEC_PRICES,
    MARKS,
    SESSIONS,
    SIGMA,
    calendar,
    observations,
    pit_inputs,
    portfolio,
)


def canonical_input(**over) -> CanonicalDecisionInput:
    kw = dict(
        route_kind="production", decision_date=DECISION, as_of=AS_OF,
        snapshot=MarketSnapshot(as_of=AS_OF, attestation=ATTESTATION,
                                marks=MARKS, adv20=ADV20, sigma20d=SIGMA),
        portfolio=portfolio(), pit_inputs=pit_inputs(),
        price_observations=observations(), corporate_action_events=(),
        exposures=(), execution_date=EXEC_DAY, execution_prices=EXEC_PRICES,
        untradable=frozenset())
    kw.update(over)
    return CanonicalDecisionInput(**kw)


# --- M-1 · the route declares and obeys the canonical order -------------------

def test_the_route_runs_every_stage_in_canonical_order():
    result = run_decision(canonical_input(), for_sealed_run=False)
    assert result.stages == PIPELINE_STAGES
    assert result.stages.index("corporate_action_transition") < \
        result.stages.index("portfolio_mark")
    assert result.stages.index("eligibility") < \
        result.stages.index("selection_score")


def test_exclusion_happens_before_any_ordering():
    """§4.5: the eligible set is decided from availability, not from scores."""
    result = run_decision(canonical_input(), for_sealed_run=False)
    assert set(result.scores) <= set(result.eligibility.eligible)


# --- S-3b · the guards are actually invoked by a NAV-producing path -----------

def test_an_exposed_unreconstructible_action_aborts_the_whole_route():
    """W-1 exposure gate, wired. Before P-2 nothing on a NAV path called it."""
    event = CorporateActionEvent(
        stock_id="1101", kind="merger", ex_or_effective_date="2020-06-15",
        reconstructibility=NOT_RECONSTRUCTIBLE,
        reason="counterparty not in corpus")
    # B0.1/R2: exposure is the portfolio's own spell ledger. The declared
    # `exposures` tuple is kept only as a redundant conformance assertion, so it
    # must AGREE with the ledger rather than define it.
    import dataclasses

    from core.b0_state import HoldingSpell

    held = dataclasses.replace(
        portfolio(), holding_spells=(HoldingSpell("1101", "2020-06-01"),))
    exposure = Exposure(stock_id="1101", held_from="2020-06-01",
                        held_until=AS_OF)
    with pytest.raises(CorporateActionError, match="W-1/W-3"):
        run_decision(canonical_input(corporate_action_events=(event,),
                                     portfolio=held,
                                     exposures=(exposure,)),
                     for_sealed_run=False)


def test_a_caller_declared_exposure_that_disagrees_with_the_ledger_fails_loud():
    """B0.1/R2: the retrospective adapter declared the LISTING SPELL as the
    holding interval. Keeping the field as a checked redundancy turns that class
    of mistake into a red light instead of an economic input."""
    import dataclasses

    from core.b0_state import HoldingSpell

    held = dataclasses.replace(
        portfolio(), holding_spells=(HoldingSpell("1101", "2020-06-01"),))
    lying = Exposure(stock_id="1101", held_from="1999-01-01", held_until=AS_OF)
    with pytest.raises(CorporateActionError, match="disagrees with the canonical"):
        run_decision(canonical_input(portfolio=held, exposures=(lying,)),
                     for_sealed_run=False)


def test_an_event_we_never_held_does_not_abort():
    """The per-event rule stays affordable because exposure is what matters."""
    event = CorporateActionEvent(
        stock_id="9999", kind="merger", ex_or_effective_date="2020-06-15",
        reconstructibility=NOT_RECONSTRUCTIBLE, reason="not held")
    run_decision(canonical_input(corporate_action_events=(event,), exposures=()),
                 for_sealed_run=False)


def test_an_unexplained_price_gap_aborts_before_a_portfolio_exists():
    """O-B, wired. A vanished holding must not become a silent NAV error."""
    gapped = tuple(
        PitPriceObservation(
            as_of=AS_OF, stock_id=o.stock_id,
            price_observed_through=("2020-06-24" if o.stock_id == "1101"
                                    else o.price_observed_through),
            expected_sessions=o.expected_sessions)
        for o in observations())
    with pytest.raises(PriceObservabilityError, match="O-B"):
        run_decision(canonical_input(price_observations=gapped),
                     for_sealed_run=False)


def test_a_suspension_known_before_the_gap_is_explained_and_marked_stale():
    """The other side of O-B: explained gaps mark stale, flagged and counted."""
    obs = []
    for o in observations():
        if o.stock_id == "1101":
            obs.append(PitPriceObservation(
                as_of=AS_OF, stock_id="1101",
                price_observed_through="2020-06-24",
                expected_sessions=o.expected_sessions,
                known_status="suspended",
                status_available_from="2020-06-24"))
        else:
            obs.append(o)
    result = run_decision(canonical_input(price_observations=tuple(obs)),
                          for_sealed_run=False)
    assert result.stale_marks["stale_marks"] == 1
    assert result.stale_marks["max_sessions_stale"] >= 1


def test_a_held_name_with_no_mark_price_aborts_rather_than_valuing_at_zero():
    with pytest.raises(CoreStateError, match="6.2"):
        run_decision(
            canonical_input(
                portfolio=PortfolioState(AS_OF, 1_000.0, {"9999": 10}),
                price_observations=observations() + (
                    PitPriceObservation(as_of=AS_OF, stock_id="9999",
                                        price_observed_through=AS_OF,
                                        expected_sessions=tuple(
                                            s for s in SESSIONS if s <= AS_OF)),)),
            for_sealed_run=False)


# --- the input contract --------------------------------------------------------

def test_decision_state_must_come_from_a_completed_prior_session():
    with pytest.raises(RouteError, match="6.6"):
        canonical_input(as_of=DECISION)


def test_execution_must_follow_the_decision_date():
    with pytest.raises(RouteError, match="6.5"):
        canonical_input(execution_date=AS_OF)


def test_state_dated_differently_from_as_of_is_refused():
    with pytest.raises(RouteError, match="as of"):
        canonical_input(portfolio=PortfolioState("2020-06-26", 1000.0, {}))


def test_for_sealed_run_has_no_default():
    with pytest.raises(TypeError):
        run_decision(canonical_input())


def test_resolve_as_of_needs_a_completed_session():
    with pytest.raises(RouteError, match="6.6"):
        resolve_as_of(SESSIONS[0], calendar())


# --- config --------------------------------------------------------------------

def test_the_canonical_config_is_the_frozen_spec_registry():
    cfg = canonical_config()
    assert cfg["N_target"] == 20
    assert cfg["w_target"] == 0.05
    assert cfg["share_rounding"] == "floor"
    assert cfg["percentile_convention"] == "average_rank"
    assert config_hash() == config_hash()          # deterministic


def test_the_config_hash_moves_when_the_frozen_config_moves():
    """A silent spec edit must not leave the hash saying nothing changed."""
    import core.b0_route as route

    baseline = config_hash()
    original = route.canonical_config
    route.canonical_config = lambda: {**original(), "N_target": 19}
    try:
        assert config_hash() != baseline
    finally:
        route.canonical_config = original
    assert config_hash() == baseline


# --- the output the ruling asked to be comparable ------------------------------

def test_the_result_carries_every_layer_p2_named():
    r = run_decision(canonical_input(), for_sealed_run=False)
    rows = r.rows()
    assert rows, "the fixture must actually produce decisions"
    sample = rows["3008"]
    for column in ("eligible", "score", "rank", "selected", "target_shares",
                   "orders", "shares_after", "pending_exit",
                   "explicit_fee", "transaction_tax", "impact"):
        assert column in sample
    assert r.diagnostics["cost_totals"]["explicit_fee"] > 0


def test_a_surviving_holding_is_rebalanced_toward_its_target():
    """C-16 through the route: order_delta = target_shares - current_shares."""
    r = run_decision(canonical_input(), for_sealed_run=False)
    held_before = portfolio().shares["1101"]
    assert r.target_shares["1101"] > held_before
    bought = [x for x in r.session.receipts
              if x.stock_id == "1101" and x.side == "buy"]
    assert bought and bought[0].shares == r.target_shares["1101"] - held_before


def test_thin_breadth_leaves_cash_rather_than_reweighting():
    """§5 through the route: four names is 20% invested, not 100%."""
    r = run_decision(canonical_input(), for_sealed_run=False)
    assert len(r.targets.selected) == 4
    assert r.targets.cash_weight == pytest.approx(0.80)
    assert all(w == 0.05 for w in r.targets.weights.values())


# --- D-1 ----------------------------------------------------------------------

def test_a_synthetic_input_cannot_produce_sealed_evidence():
    with pytest.raises(CoreStateError, match="synthetic"):
        run_decision(canonical_input(), for_sealed_run=True)


def test_an_unknown_stage_would_be_rejected():
    """M-3 through M-1: a stage the specification does not define aborts."""
    from core.b0_master_prereg import UnspecifiedBehaviour, assert_stage_order

    with pytest.raises(UnspecifiedBehaviour):
        assert_stage_order(["pit_raw_state", "my_extra_stage"])
    with pytest.raises(MasterPreregViolation):
        assert_stage_order(["portfolio_mark", "corporate_action_transition"])
