"""P-1b · the canonical core's input contract and its open-item register.

Every fixture here is synthetic and says so. That is not a convenience: D-1 (§2.8)
records that the price universe currently in the repository excludes securities
delisted after 2018, so any test that derived a plausible-looking selection from
it would be validating the implementation against contaminated data — and would
look exactly as green as a correct one.

What is checked here is the boundary, not the strategy:

  * an input must attest to what it is, and a synthetic input may never feed a
    sealed run;
  * while a blocking data requirement is unmet, real data cannot enter the core;
  * the share ledger refuses states that §6.3/§6.4 forbid;
  * marking fails loud on an unpriced holding instead of valuing it at zero.
"""

import pytest

from core.b0_frozen_spec import unmet_blocking_requirements
from core.b0_open_items import (
    LAYERS,
    MATERIALITY_LEVELS,
    OPEN_ITEMS,
    UnspecifiedCoreBehaviour,
    get,
    open_items_for,
    raise_unspecified,
    summary,
    unspecified_keys,
)
from core.b0_pit_observability import GapVerdict
from core.b0_state import (
    ADV20_SESSIONS,
    SIGMA20D_RETURNS,
    CoreStateError,
    MarketSnapshot,
    PortfolioState,
    SourceAttestation,
    assert_price_state_admissible,
    compute_adv20,
    compute_sigma20d,
    mark_portfolio,
)

SYNTHETIC = SourceAttestation(
    dataset_id="synthetic_fixture",
    provenance_sha256="0" * 64,
    pit_guard_passed=True,
    universe_guard_passed=True,
    satisfied_blocking_requirements=(),
    synthetic=True,
)


def snapshot(**over) -> MarketSnapshot:
    kw = dict(as_of="2020-06-30", attestation=SYNTHETIC,
              marks={"1101": 40.0, "2330": 300.0},
              adv20={"1101": 5e7, "2330": 5e9},
              sigma20d={"1101": 0.02, "2330": 0.015})
    kw.update(over)
    return MarketSnapshot(**kw)


# --- attestation --------------------------------------------------------------

def test_attestation_must_identify_itself():
    with pytest.raises(CoreStateError):
        SourceAttestation("", "abc", True, True, (), True)
    with pytest.raises(CoreStateError):
        SourceAttestation("d", "  ", True, True, (), True)


def test_synthetic_input_may_not_feed_a_sealed_run():
    assert_price_state_admissible(SYNTHETIC, for_sealed_run=False)
    with pytest.raises(CoreStateError, match="synthetic"):
        assert_price_state_admissible(SYNTHETIC, for_sealed_run=True)


def test_failed_guards_are_refused_regardless_of_run_kind():
    for bad in (SourceAttestation("d", "h", False, True, (), True),
                SourceAttestation("d", "h", True, False, (), True)):
        with pytest.raises(CoreStateError):
            assert_price_state_admissible(bad, for_sealed_run=False)


def test_real_data_cannot_enter_while_a_blocking_requirement_is_unmet():
    """§2.8 D-1 wired to the live registry, not to a copy of its conclusion."""
    unmet = tuple(r.key for r in unmet_blocking_requirements())
    real = SourceAttestation("tej_price_export", "a" * 64, True, True, (), False)
    if unmet:
        with pytest.raises(CoreStateError) as e:
            assert_price_state_admissible(real, for_sealed_run=False)
        assert str(list(unmet)) in str(e.value) or unmet[0] in str(e.value)
    else:
        assert_price_state_admissible(real, for_sealed_run=False)


def test_attesting_the_requirement_is_what_clears_it():
    unmet = tuple(r.key for r in unmet_blocking_requirements())
    att = SourceAttestation("tej_price_export", "a" * 64, True, True, unmet, False)
    assert_price_state_admissible(att, for_sealed_run=False)


# --- share ledger -------------------------------------------------------------

def test_no_negative_cash():
    with pytest.raises(CoreStateError, match="6.4"):
        PortfolioState("2020-06-30", -1.0, {})


def test_shares_are_whole_and_non_negative():
    with pytest.raises(CoreStateError, match="6.3"):
        PortfolioState("2020-06-30", 0.0, {"1101": 10.5})
    with pytest.raises(CoreStateError, match="6.3"):
        PortfolioState("2020-06-30", 0.0, {"1101": -5})


def test_pending_exit_is_a_subset_of_what_is_held():
    with pytest.raises(CoreStateError, match="pending_exit"):
        PortfolioState("2020-06-30", 0.0, {"1101": 100}, {"2330": 10})
    with pytest.raises(CoreStateError, match="pending_exit"):
        PortfolioState("2020-06-30", 0.0, {"1101": 100}, {"1101": 500})
    PortfolioState("2020-06-30", 0.0, {"1101": 100}, {"1101": 40})


# --- marking ------------------------------------------------------------------

def test_unpriced_holding_fails_loud_and_is_never_worth_zero():
    p = PortfolioState("2020-06-30", 1000.0, {"9999": 100})
    with pytest.raises(CoreStateError, match="6.2"):
        mark_portfolio(p, snapshot())


def test_nav_includes_both_receivables():
    p = PortfolioState("2020-06-30", 1000.0, {"1101": 100},
                       cash_dividend_receivable=250.0,
                       stock_dividend_receivable={"1101": 10})
    m = mark_portfolio(p, snapshot())
    assert m.position_values["1101"] == 100 * 40.0
    assert m.receivable_value == 250.0 + 10 * 40.0
    assert m.port_value == 1000.0 + 4000.0 + 650.0


def test_mark_consumes_gap_verdicts_and_refuses_an_unmarkable_holding():
    p = PortfolioState("2020-06-30", 0.0, {"1101": 100})
    stale = GapVerdict("1101", "EXPLAINED_SUSPENSION", 3, stale_mark=True)
    m = mark_portfolio(p, snapshot(), [stale])
    assert m.stale_marked == ("1101",) and m.max_sessions_stale == 3

    bad = GapVerdict("1101", "UNEXPLAINED_GAP", 3, markable=False)
    with pytest.raises(CoreStateError, match="O-B"):
        mark_portfolio(p, snapshot(), [bad])


def test_a_guard_that_skips_a_holding_is_not_a_guard():
    p = PortfolioState("2020-06-30", 0.0, {"1101": 100, "2330": 10})
    with pytest.raises(CoreStateError, match="verdict"):
        mark_portfolio(p, snapshot(), [GapVerdict("1101", "CURRENT", 0)])


def test_marking_across_dates_is_not_a_mark():
    p = PortfolioState("2020-06-29", 0.0, {"1101": 100})
    with pytest.raises(CoreStateError):
        mark_portfolio(p, snapshot())


# --- ADV20 and sigma20d (C-25, C-26) ------------------------------------------

def test_adv20_is_the_mean_traded_value_of_twenty_observed_sessions():
    assert compute_adv20([1000.0] * 20) == pytest.approx(1000.0)
    assert compute_adv20([0.0] * 19 + [2000.0]) == pytest.approx(100.0)
    # only the 20 most recent count
    assert compute_adv20([9e9] + [1000.0] * 20) == pytest.approx(1000.0)


def test_adv20_is_none_below_twenty_observed_sessions():
    """§4.2: a missing liquidity observation is not evidence of liquidity."""
    assert compute_adv20([1000.0] * 19) is None


def test_sigma20d_is_the_unannualised_std_of_daily_log_returns():
    """B-14 P3, verbatim: trailing 20 sessions, log returns, PIT, unannualised."""
    import math
    import statistics

    closes = [100.0 * (1.01 ** i) if i % 2 == 0 else 100.0 * (1.01 ** i) * 0.99
              for i in range(21)]
    rets = [math.log(closes[i + 1] / closes[i]) for i in range(20)]
    assert compute_sigma20d(closes) == pytest.approx(statistics.stdev(rets))

    # A constant series has zero volatility — legal, and §7.5 says it is NOT
    # evidence the name could trade.
    assert compute_sigma20d([50.0] * 21) == pytest.approx(0.0)


def test_sigma20d_is_not_annualised():
    """The 15.9x error the definition exists to prevent, stated as a test."""
    import math

    closes = [100.0 * (1.02 ** i) if i % 2 else 100.0 * (1.02 ** i) * 0.97
              for i in range(21)]
    daily = compute_sigma20d(closes)
    assert daily is not None and daily > 0
    assert daily < 0.5                                  # a daily sigma, not annual
    assert SIGMA20D_RETURNS == 20 and ADV20_SESSIONS == 20


def test_sigma20d_needs_twenty_one_closes_and_positive_prices():
    assert compute_sigma20d([100.0] * 20) is None
    assert compute_sigma20d([0.0] + [100.0] * 20) is None
    assert compute_sigma20d([None] + [100.0] * 20) is None


# --- the open-item register ---------------------------------------------------

def test_every_open_item_is_well_formed_and_unique():
    keys = unspecified_keys()
    assert len(keys) == len(set(keys)) == len(OPEN_ITEMS)
    for item in OPEN_ITEMS:
        assert item.layer in LAYERS
        assert item.materiality in MATERIALITY_LEVELS
        assert item.question.strip() and item.why_it_matters.strip()


@pytest.fixture
def temporary_open_item():
    """Register an item for the duration of one test.

    The real register is empty (C-16 ~ C-36 closed everything), but the abort
    path still has to work — the next undetermined behaviour anybody finds must
    land there rather than in a default. So the mechanism is exercised against a
    stand-in rather than left untested because the list happens to be empty.
    """
    import core.b0_open_items as mod

    item = mod.OpenItem(
        key="fixture_only_item", layer="features",
        question="Does the abort path still name the question?",
        why_it_matters="An untested abort path is an abort path nobody has run.",
        materiality="low")
    original = mod.OPEN_ITEMS
    mod._BY_KEY[item.key] = item
    mod.OPEN_ITEMS = original + (item,)
    try:
        yield item
    finally:
        del mod._BY_KEY[item.key]
        mod.OPEN_ITEMS = original


def test_abort_names_the_question_rather_than_a_stack_trace(temporary_open_item):
    with pytest.raises(UnspecifiedCoreBehaviour) as e:
        raise_unspecified(temporary_open_item.key, context="unit test")
    msg = str(e.value)
    assert "M-3" in msg and temporary_open_item.key in msg
    assert temporary_open_item.question[:30] in msg
    assert get(temporary_open_item.key) is temporary_open_item


def test_the_register_is_empty_and_that_is_the_goal_state():
    """C-16 ~ C-36: every behaviour the canonical core reaches is specified."""
    assert OPEN_ITEMS == ()
    assert summary()["total"] == 0


def test_an_unregistered_gap_cannot_be_aborted_on():
    """The register is only useful if reaching a gap forces it to be listed."""
    with pytest.raises(KeyError):
        raise_unspecified("some_behaviour_nobody_wrote_down")


def test_the_four_layers_are_covered_by_the_static_invariants():
    """§8.4: the invariants are static, so they apply before a route exists."""
    from core.b0_invariants import B0_ENTRY_MODULES

    for mod in ("core.b0_features", "core.b0_eligibility", "core.b0_decision",
                "core.b0_execution", "core.b0_state"):
        assert mod in B0_ENTRY_MODULES


def test_spec_names_the_open_question_when_one_is_registered(temporary_open_item):
    from core.b0_master_prereg import UnspecifiedBehaviour, spec

    with pytest.raises(UnspecifiedBehaviour) as e:
        spec(temporary_open_item.key)
    assert "OPEN specification item" in str(e.value)
    assert "Question" in str(e.value)


def test_spec_still_aborts_on_a_key_nobody_registered():
    from core.b0_master_prereg import UnspecifiedBehaviour, spec

    with pytest.raises(UnspecifiedBehaviour, match="b0_open_items"):
        spec("some_knob_an_implementer_wanted")


def test_the_selection_path_is_now_fully_specified():
    """S-1's precondition, checkable rather than asserted."""
    from core.b0_master_prereg import assert_selection_path_is_fully_specified

    assert_selection_path_is_fully_specified()


def test_s1_fails_loud_again_if_any_behaviour_reopens(temporary_open_item):
    """The check is not a constant: one open item takes S-1 back to PENDING."""
    from core.b0_master_prereg import (
        UnspecifiedBehaviour, assert_selection_path_is_fully_specified)

    with pytest.raises(UnspecifiedBehaviour, match="S-1"):
        assert_selection_path_is_fully_specified()


def test_no_open_item_is_quietly_also_a_frozen_parameter():
    """An item cannot be both undecided and already answered."""
    from core.b0_master_prereg import specified_keys

    assert not (set(unspecified_keys()) & set(specified_keys()))


def test_summary_is_the_machine_readable_mirror_of_12_2():
    s = summary()
    assert s["total"] == len(OPEN_ITEMS)
    assert sum(s["by_layer"].values()) == s["total"]
    assert sum(s["by_materiality"].values()) == s["total"]
    assert all(open_items_for(l) or True for l in LAYERS)
