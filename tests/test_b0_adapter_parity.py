"""P-2 · B-20 adapter parity on a deterministic canonical fixture.

The claim being measured is NOT "two engines agree". There is one engine —
`core.b0_route.run_decision` — and §8.7 says what parity therefore has to check:
whether the two adapters supply the same `as_of` / config / state and consume the
output correctly.

So these tests do two things, and the second matters more than the first:

  1. run both adapters over one fixture and require bit-exact agreement;
  2. prove the adapters CANNOT contain strategy semantics, by AST — no import of
     b0_features / b0_eligibility / b0_decision / b0_execution, and no reference
     to any of the forbidden entry points. A parity test on two engines proves
     they agree today; a structural proof that there is only one engine is what
     stops them diverging tomorrow (`core/b0_parity.py` module docstring).

Every number below is invented. The fixture attests itself synthetic, which
`assert_price_state_admissible` refuses to let near a sealed run, and D-1 remains
unmet throughout — see `test_d1_still_blocks_the_real_retrospective_route`.
"""

import ast

import pytest

from core import b0_adapter_production as production
from core import b0_adapter_retrospective as retrospective
from core.b0_features import SecurityPitInputs
from core.b0_listing_spell import ListingSpell, ListingSpellError
from core.b0_market_state import SourceContract, TradingCalendar
from core.b0_parity import B0_ROUTE_PAIRS, ParityError
from core.b0_pit_observability import PitPriceObservation
from core.b0_route import (
    ROUTE_PARITY_COLUMNS,
    CanonicalDecisionInput,
    RouteError,
    assert_route_parity,
    config_hash,
    resolve_as_of,
    run_decision,
)
from core.b0_state import PortfolioState, SourceAttestation

SESSIONS = ("2020-06-24", "2020-06-25", "2020-06-26", "2020-06-29",
            "2020-06-30", "2020-07-01")
DECISION = "2020-06-30"
AS_OF = "2020-06-29"
EXEC_DAY = "2020-07-01"

NAMES = ("1101", "2330", "2454", "3008")


def calendar() -> TradingCalendar:
    contract = SourceContract(
        name="synthetic_calendar", kind="trading_calendar",
        importer_version="test", content_sha256="1" * 64, schema_sha256="0" * 64,
        date_min=SESSIONS[0], date_max=SESSIONS[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    return TradingCalendar(SESSIONS, contract)


ATTESTATION = SourceAttestation(
    dataset_id="p2_fixture", provenance_sha256="f" * 64,
    pit_guard_passed=True, universe_guard_passed=True,
    satisfied_blocking_requirements=(), synthetic=True)


def pit_inputs():
    """Four securities that differ on every concept, so ranking is not a tie."""
    out = []
    for i, sid in enumerate(NAMES):
        scale = 1.0 + i
        out.append(SecurityPitInputs(
            stock_id=sid,
            net_income_by_quarter=tuple(10.0 * scale + q for q in range(8)),
            revenue_by_quarter=tuple(100.0 * scale for _ in range(8)),
            gross_profit_by_quarter=tuple(30.0 * scale + q for q in range(8)),
            eps_by_quarter=tuple(1.0 + 0.1 * scale * q for q in range(8)),
            period_end_equity=500.0 * scale,
            total_liabilities=200.0 + 10.0 * i,
            total_assets=1000.0,
            current_assets=300.0 + 20.0 * i,
            current_liabilities=100.0,
            monthly_revenue=tuple(50.0 * scale + m for m in range(30)),
            month_end_prices=tuple(20.0 + 0.5 * scale * m for m in range(20)),
            per_tse=10.0 + i,
            pbr_tse=1.0 + 0.5 * i,
            pit_industry="半導體" if i % 2 else "水泥",
        ))
    return tuple(out)


def observations():
    return tuple(
        PitPriceObservation(as_of=AS_OF, stock_id=sid,
                            price_observed_through=AS_OF,
                            expected_sessions=tuple(s for s in SESSIONS
                                                    if s <= AS_OF))
        for sid in NAMES)


def spells():
    """One spell per fixture name, opened at the first session of the fixture.

    `first_observation`, not `reappearance`: the fixture has no gap, so there is
    no earlier listing to bridge to. A reappearance spell is exercised directly
    in `tests/test_b0_listing_spell.py`.
    """
    return tuple(ListingSpell(stock_id=sid, start=SESSIONS[0],
                              opened_by="first_observation", as_of=AS_OF)
                 for sid in NAMES)


def portfolio() -> PortfolioState:
    return PortfolioState(AS_OF, 5_000_000.0, {"1101": 1000})


MARKS = {sid: 20.0 + 10.0 * i for i, sid in enumerate(NAMES)}
ADV20 = {sid: 5e8 for sid in NAMES}
SIGMA = {sid: 0.02 for sid in NAMES}
EXEC_PRICES = {sid: MARKS[sid] * 1.01 for sid in NAMES}


def retrospective_sources():
    return retrospective.RetrospectiveSources(
        calendar=calendar(), status_table=None, attestation=ATTESTATION,
        marks=MARKS, adv20=ADV20, sigma20d=SIGMA,
        pit_inputs=pit_inputs(), price_observations=observations())


def production_sources():
    return production.ProductionSources(
        calendar=calendar(), status_table=None, attestation=ATTESTATION,
        marks=MARKS, adv20=ADV20, sigma20d=SIGMA,
        pit_inputs=pit_inputs(), price_observations=observations())


def run_both():
    r = retrospective.run(retrospective_sources(), portfolio(), DECISION,
                          EXEC_DAY, EXEC_PRICES, for_sealed_run=False)
    p = production.run(production_sources(), portfolio(), DECISION,
                       EXEC_DAY, EXEC_PRICES, for_sealed_run=False)
    return p, r


# --- P2-1 · as_of parity ------------------------------------------------------

def test_both_routes_resolve_the_same_as_of_from_one_decision_date():
    assert resolve_as_of(DECISION, calendar()) == AS_OF
    p, r = run_both()
    assert p.as_of == r.as_of == AS_OF
    assert p.as_of != DECISION          # never the month-end label itself


def test_a_month_end_label_used_as_as_of_fails_loud():
    """§6.6: decision state comes from the prior COMPLETED session."""
    with pytest.raises(RouteError, match="6.6"):
        CanonicalDecisionInput(
            route_kind="production", decision_date=DECISION, as_of=DECISION,
            snapshot=None,          # never reached: as_of is checked first
            portfolio=portfolio(), pit_inputs=(), price_observations=(),
            corporate_action_events=(), exposures=(),
            execution_date=EXEC_DAY, execution_prices={}, untradable=frozenset())


def test_an_as_of_mismatch_between_routes_aborts_before_outputs():
    p, r = run_both()
    shifted = type(r)(**{**r.__dict__, "as_of": "2020-06-26"})
    with pytest.raises(ParityError, match="as_of mismatch"):
        assert_route_parity(p, shifted)


# --- P2-2 · config parity -----------------------------------------------------

def test_one_config_hash_for_both_routes_and_no_adapter_override():
    p, r = run_both()
    assert p.config_hash == r.config_hash == config_hash()

    # There is no adapter-side config to diverge: neither source dataclass has a
    # field that could carry one.
    for cls in (retrospective.RetrospectiveSources, production.ProductionSources):
        fields = set(cls.__dataclass_fields__)
        assert not (fields & {"config", "overrides", "params", "arm", "settings"})


def test_a_config_hash_mismatch_aborts_before_outputs():
    p, r = run_both()
    forged = type(r)(**{**r.__dict__, "config_hash": "not-the-frozen-config"})
    with pytest.raises(ParityError, match="config_hash mismatch"):
        assert_route_parity(p, forged)


# --- P2-3 / P2-4 · state parity, inputs first ---------------------------------

def test_identical_state_hashes_to_the_same_value_from_either_route():
    p, r = run_both()
    assert p.state_hash == r.state_hash


def test_the_route_label_is_not_part_of_the_state():
    """Otherwise no two routes could ever agree on a state hash."""
    ri = retrospective.build_input(retrospective_sources(), portfolio(), DECISION,
                                   EXEC_DAY, EXEC_PRICES)
    pi = production.build_input(production_sources(), portfolio(), DECISION,
                                EXEC_DAY, EXEC_PRICES)
    assert ri.route_kind != pi.route_kind
    assert ri.state_hash() == pi.state_hash()


def test_a_state_difference_changes_the_hash_and_aborts_before_outputs():
    p, r = run_both()
    other = retrospective.run(
        retrospective.RetrospectiveSources(
            calendar=calendar(), status_table=None, attestation=ATTESTATION,
            marks={**MARKS, "1101": 21.0}, adv20=ADV20, sigma20d=SIGMA,
            pit_inputs=pit_inputs(), price_observations=observations()),
        portfolio(), DECISION, EXEC_DAY, EXEC_PRICES, for_sealed_run=False)
    assert other.state_hash != r.state_hash
    with pytest.raises(ParityError, match="state_hash mismatch"):
        assert_route_parity(p, other)


def test_na_is_distinguished_from_zero_in_the_state_hash():
    """§4.1 acts on the difference, so the hash has to preserve it."""
    def build(value):
        rows = list(pit_inputs())
        rows[0] = SecurityPitInputs(**{**rows[0].__dict__, "per_tse": value})
        return retrospective.build_input(
            retrospective.RetrospectiveSources(
                calendar=calendar(), status_table=None, attestation=ATTESTATION,
                marks=MARKS, adv20=ADV20, sigma20d=SIGMA,
                pit_inputs=tuple(rows), price_observations=observations()),
            portfolio(), DECISION, EXEC_DAY, EXEC_PRICES).state_hash()

    assert build(None) != build(0.0)


# --- P2-5 · deterministic output parity ---------------------------------------

def test_the_two_adapters_agree_bit_exactly():
    p, r = run_both()
    assert_route_parity(p, r)              # float_tol = 0.0 by default


def test_parity_covers_every_layer_the_ruling_named():
    for column in ("eligible", "score", "rank", "selected", "target_shares",
                   "orders", "shares_after", "pending_exit",
                   "explicit_fee", "transaction_tax", "impact",
                   "roe", "PEG", "value_ind_pct_b", "momentum_12_1"):
        assert column in ROUTE_PARITY_COLUMNS


def test_a_route_may_not_be_compared_with_itself():
    p, _ = run_both()
    with pytest.raises(RouteError, match="comparing a route with itself"):
        assert_route_parity(p, p)


def test_agreement_on_names_alone_is_not_parity():
    """Two runs can pick the same stocks from different inputs (P2-4)."""
    p, r = run_both()
    forged = type(r)(**{**r.__dict__, "state_hash": "different-inputs"})
    assert p.targets.selected == forged.targets.selected      # same names ...
    with pytest.raises(ParityError, match="state_hash"):      # ... still aborts
        assert_route_parity(p, forged)


# --- the structural claim: there is only one engine ---------------------------

FORBIDDEN_LAYER_IMPORTS = ("b0_features", "b0_eligibility", "b0_decision",
                           "b0_execution")

FORBIDDEN_SEMANTIC_SYMBOLS = (
    "build_feature_panel", "feature_percentile", "percentile_rank",
    "compute_roe_ttm", "compute_peg", "compute_eps_growth",
    "compute_value_ind_pct_b", "compute_revenue_accel", "compute_momentum_12_1",
    "evaluate", "frozen_risk_filters", "adv_floor", "passes_investability",
    "score_eligible", "selection_score", "rank", "select", "target_portfolio",
    "target_shares", "execute_session", "required_sells", "order_cap_value",
    "child_order_cost", "classify", "register_handler",
)


def _adapter_sources():
    for mod in (retrospective, production):
        with open(mod.__file__, encoding="utf-8") as fh:
            yield mod.__name__, fh.read()


@pytest.mark.parametrize("attr", ["retrospective", "production"])
def test_an_adapter_does_not_import_any_canonical_layer(attr):
    mod = {"retrospective": retrospective, "production": production}[attr]
    with open(mod.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)

    hits = sorted(n for n in imported
                  if any(f in n for f in FORBIDDEN_LAYER_IMPORTS))
    assert not hits, (
        f"{mod.__name__} imports canonical layer(s) {hits}. An adapter that can "
        f"reach the layers directly can re-implement them, which is how one "
        f"engine becomes two.")


def test_no_adapter_calls_a_strategy_semantic_entry_point():
    for name, src in _adapter_sources():
        tree = ast.parse(src)
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
        hits = sorted(called & set(FORBIDDEN_SEMANTIC_SYMBOLS))
        assert not hits, f"{name} calls strategy semantics directly: {hits}"


def test_both_adapters_reach_the_core_only_through_run_decision():
    for name, src in _adapter_sources():
        assert "run_decision" in src, f"{name} never enters the shared core"
        tree = ast.parse(src)
        entries = {n.func.id for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "run_decision" in entries


def test_the_registered_route_pair_is_these_two_adapters():
    assert B0_ROUTE_PAIRS == (
        ("core.b0_adapter_production", "core.b0_adapter_retrospective"),)


# --- D-1 is not worked around --------------------------------------------------

def test_d1_still_blocks_the_real_retrospective_route():
    """The replay is exactly what a survivorship-filtered universe damages."""
    from core.b0_frozen_spec import unmet_blocking_requirements

    unmet = tuple(r.key for r in unmet_blocking_requirements())
    real = SourceAttestation(
        dataset_id="tej_price_export", provenance_sha256="a" * 64,
        pit_guard_passed=True, universe_guard_passed=True,
        satisfied_blocking_requirements=(), synthetic=False)
    sources = retrospective.RetrospectiveSources(
        calendar=calendar(), status_table=None, attestation=real,
        marks=MARKS, adv20=ADV20, sigma20d=SIGMA,
        pit_inputs=pit_inputs(), price_observations=observations())

    if unmet:
        with pytest.raises(retrospective.RetrospectiveAdapterError, match="2.8"):
            retrospective.build_input(sources, portfolio(), DECISION, EXEC_DAY,
                                      EXEC_PRICES)
        return

    # D-1 is met, so the blocking-requirement gate lets the replay through — but
    # D1-6 still requires it to say WHICH price corpus it read, so that the
    # quarantined one cannot be reached by cache selection or an overlay.
    import dataclasses

    from core.b0_price_universe import CONTAMINATED_CORPUS_SHA256, PriceSourceContract

    with pytest.raises(retrospective.RetrospectiveAdapterError, match="D1-6"):
        retrospective.build_input(sources, portfolio(), DECISION, EXEC_DAY,
                                  EXEC_PRICES)

    admissible = PriceSourceContract(
        name="b0_price_universe_20260817", importer_version="imp@2",
        content_sha256="f" * 64, schema_sha256="s" * 64,
        date_min="2004-01-02", date_max="2026-08-17", securities=2306,
        includes_delisted=True, audit_sha256="a" * 64)
    named = dataclasses.replace(sources, price_source=admissible)

    # O-G: naming the corpus is still not enough. A real replay supplies ADV20
    # and sigma20d, and until it says which listing spell those 20 sessions sit
    # inside, nobody has shown the window does not bridge two listings of one
    # code (25 of the 27 exit-and-return securities have no recorded delisting
    # anywhere but the price series itself).
    with pytest.raises(ListingSpellError, match="no listing spell declared"):
        retrospective.build_input(named, portfolio(), DECISION, EXEC_DAY,
                                  EXEC_PRICES)

    with_spells = dataclasses.replace(named, listing_spells=spells())
    retrospective.build_input(with_spells, portfolio(), DECISION, EXEC_DAY,
                              EXEC_PRICES)

    from core.b0_price_universe import PriceUniverseError
    with pytest.raises(PriceUniverseError, match="quarantined"):
        retrospective.build_input(
            dataclasses.replace(with_spells, price_source=dataclasses.replace(
                admissible, content_sha256=CONTAMINATED_CORPUS_SHA256)),
            portfolio(), DECISION, EXEC_DAY, EXEC_PRICES)


def test_a_synthetic_fixture_may_not_feed_a_sealed_run():
    with pytest.raises(Exception, match="synthetic"):
        retrospective.run(retrospective_sources(), portfolio(), DECISION,
                          EXEC_DAY, EXEC_PRICES, for_sealed_run=True)
