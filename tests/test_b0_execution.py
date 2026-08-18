"""P-1b layer 4 · orders, fills, the share ledger and receipts (§6, §7, §8.7).

The tests that matter here are the ones about money that does not exist yet.
§6.4's four steps exist to stop one specific thing: financing a new position with
the expected proceeds of a sale that has not filled. That is leverage arriving
through the back door, and it is invisible in a NAV series — the portfolio simply
looks like it rebalanced more cleanly than it could have.

So: sells strictly first, capped at 1% of ADV20; whatever does not fill becomes
`pending_exit` and stays a held position; buys are funded only from cash that has
actually been realised, costs included.

All prices, ADVs and volatilities below are invented. Nothing here is evidence
about any security.
"""

import pytest

from core.b0_execution import (
    BUY_PRIORITIES,
    BUY_PRIORITY,
    DRIFT_POLICIES,
    TARGET_DRIFT_POLICY,
    ChildOrder,
    ExecutionError,
    cap_shares,
    cost_totals,
    execute_session,
    order_cap_value,
    required_sells,
    target_shares,
)
from core.b0_open_items import UnspecifiedCoreBehaviour
from core.b0_state import PortfolioState

DAY = "2020-07-01"
PRIOR = "2020-06-30"
POLICY = TARGET_DRIFT_POLICY
PRIORITY = "rank"


def session(**over):
    kw = dict(
        execution_date=DAY, data_as_of=PRIOR,
        pre_trade=PortfolioState(PRIOR, 1_000_000.0, {}),
        target_share_counts={},
        prices={"A": 100.0, "B": 50.0, "C": 20.0},
        adv20={"A": 1e9, "B": 1e9, "C": 1e9},
        sigma20d={"A": 0.02, "B": 0.02, "C": 0.02},
        untradable=frozenset(),
        drift_policy=POLICY, buy_priority=PRIORITY, buy_order=("A", "B", "C"),
        x_sell=0.01, x_buy=0.01,
    )
    kw.update(over)
    return execute_session(**kw)


# --- orders and caps ----------------------------------------------------------

def test_a_child_order_is_whole_shares_at_a_real_price():
    with pytest.raises(ExecutionError, match="6.3"):
        ChildOrder("A", "buy", 10.5, 100.0, DAY)
    with pytest.raises(ExecutionError, match="6.3"):
        ChildOrder("A", "buy", 0, 100.0, DAY)
    with pytest.raises(ExecutionError):
        ChildOrder("A", "hold", 10, 100.0, DAY)
    assert ChildOrder("A", "buy", 10, 100.0, DAY).value == 1000.0


def test_the_daily_cap_is_one_percent_of_adv20_by_value():
    assert order_cap_value(1_000_000.0, 0.01) == 10_000.0
    assert cap_shares(10_000.0, 100.0) == 100
    assert cap_shares(10_050.0, 100.0) == 100        # never rounds up through it


# --- the undetermined execution behaviours -----------------------------------

def test_the_drift_policy_is_frozen_to_a_per_decision_rebalance():
    """C-16: order_delta = target_shares - current_shares, every decision date."""
    assert TARGET_DRIFT_POLICY == "rebalance_to_5pct_each_decision"
    assert DRIFT_POLICIES == (TARGET_DRIFT_POLICY,)

    pre = PortfolioState(PRIOR, 0.0, {"A": 100})
    drifted = {"A": 80}          # still selected, but drifted above its 5% target
    assert required_sells(pre, drifted, drift_policy=POLICY) == {"A": 20}


def test_a_position_below_target_is_topped_up_rather_than_left_to_drift():
    pre = PortfolioState(PRIOR, 100_000.0, {"A": 60})
    r = session(pre_trade=pre, target_share_counts={"A": 100})
    assert r.shares_after["A"] == 100
    assert [x.side for x in r.receipts] == ["buy"]


def test_hold_until_dropped_is_not_a_selectable_variant():
    """An unreachable alternative is documentation; a reachable one is a knob."""
    pre = PortfolioState(PRIOR, 0.0, {"A": 100})
    with pytest.raises(ExecutionError, match="C-16"):
        required_sells(pre, {"A": 80}, drift_policy="hold_until_dropped")


def test_buys_are_filled_in_selection_rank_order():
    """C-32: rank-first, and proportional scaling is not a selectable variant."""
    assert BUY_PRIORITY == "rank"
    assert BUY_PRIORITIES == (BUY_PRIORITY,)
    with pytest.raises(ExecutionError, match="C-32"):
        session(buy_priority="pro_rata")

    # NT$12,000 of cash against two NT$10,000 targets: the higher-ranked name is
    # filled first and completely, rather than both being scaled to 60%.
    r = session(pre_trade=PortfolioState(PRIOR, 12_000.0, {}),
                target_share_counts={"A": 100, "B": 200},
                buy_order=("A", "B"))
    assert r.shares_after["A"] == 100
    assert r.shares_after.get("B", 0) < 200
    assert r.cash_after >= 0


def test_rank_order_follows_the_ranking_not_the_alphabet():
    r = session(pre_trade=PortfolioState(PRIOR, 12_000.0, {}),
                target_share_counts={"A": 100, "B": 200},
                buy_order=("B", "A"))          # B outranks A this month
    assert r.shares_after["B"] == 200
    assert r.shares_after.get("A", 0) < 100


def test_share_rounding_is_floor_and_the_five_percent_cap_is_hard():
    """C-34: floor to one share; nearest could carry a name through w_max."""
    assert target_shares(10_000.0, 300.0, share_rounding="floor") == 33
    with pytest.raises(ExecutionError, match="C-34"):
        target_shares(10_000.0, 300.0, share_rounding="nearest")

    # 33 shares at 300 = 9,900 <= the 10,000 target; nearest would have given 33
    # here but 34 (= 10,200, above the cap) at a target of 10,150.
    assert target_shares(10_150.0, 300.0, share_rounding="floor") == 33
    assert 33 * 300.0 <= 10_150.0
    # the rounding shortfall stays in cash (§5), it is not spent elsewhere
    assert target_shares(9_900.0, 300.0, share_rounding="floor") == 33


# --- the frozen rebalance-day sequence ---------------------------------------

def test_a_dropped_name_is_sold_in_full_when_capacity_allows():
    pre = PortfolioState(PRIOR, 0.0, {"A": 100})
    r = session(pre_trade=pre, target_share_counts={})
    assert "A" not in r.shares_after
    assert r.pending_exit_after == {}
    assert [x.side for x in r.receipts] == ["sell"]
    assert r.cash_after == pytest.approx(10_000.0 - r.receipts[0].total_cost)


def test_an_unfilled_exit_becomes_pending_and_remains_held():
    pre = PortfolioState(PRIOR, 0.0, {"A": 1000})
    # 1% of ADV20 = NT$10,000 = 100 shares at 100.0, so 900 cannot leave today.
    r = session(pre_trade=pre, target_share_counts={}, adv20={"A": 1_000_000.0})
    assert r.shares_after["A"] == 900
    assert r.pending_exit_after == {"A": 900}
    assert r.adv_cap_shortfall_value == pytest.approx(90_000.0)


def test_a_carried_pending_exit_is_re_attempted_the_next_session():
    pre = PortfolioState(PRIOR, 0.0, {"A": 900}, {"A": 900})
    r = session(pre_trade=pre, target_share_counts={}, adv20={"A": 1_000_000.0})
    assert r.shares_after["A"] == 800
    assert r.pending_exit_after == {"A": 800}


def test_a_residual_is_recapped_against_the_executing_sessions_own_adv20():
    """C-27: §6.4's daily cap and §7.3's per-day inputs, read together."""
    from core.b0_execution import PENDING_EXIT_CAP_BASIS

    assert PENDING_EXIT_CAP_BASIS == "per_session_adv20_as_of_prior_close"
    pre = PortfolioState(PRIOR, 0.0, {"A": 900}, {"A": 900})
    # Liquidity collapsed to a tenth overnight: today's cap must follow it down,
    # not stay at the capacity the first session happened to have.
    r = session(pre_trade=pre, target_share_counts={}, adv20={"A": 100_000.0})
    assert r.shares_after["A"] == 890
    assert r.pending_exit_after == {"A": 890}


def test_an_untradable_name_cannot_be_sold_and_carries_forward():
    pre = PortfolioState(PRIOR, 0.0, {"A": 100})
    r = session(pre_trade=pre, target_share_counts={},
                untradable=frozenset({"A"}))
    assert r.receipts == ()
    assert r.shares_after["A"] == 100
    assert r.pending_exit_after == {"A": 100}


def test_an_untradable_name_is_not_bought_either():
    r = session(target_share_counts={"A": 100}, untradable=frozenset({"A"}))
    assert r.receipts == ()
    assert r.shares_after == {}


def test_buys_are_funded_only_by_cash_that_has_actually_been_realised():
    """The whole point of §6.4: an unfilled sale finances nothing."""
    pre = PortfolioState(PRIOR, 0.0, {"A": 1000})
    r = session(pre_trade=pre,
                target_share_counts={"B": 200},          # wants NT$10,000
                adv20={"A": 1_000_000.0, "B": 1e9, "C": 1e9})
    sold = next(x for x in r.receipts if x.side == "sell")
    bought = [x for x in r.receipts if x.side == "buy"]
    assert sold.value == pytest.approx(10_000.0)         # only 100 of 1000 filled
    # Realised cash is the sale minus its costs, so the full 200-share buy
    # (NT$10,000 + costs) cannot be afforded.
    assert bought and bought[0].shares < 200
    assert r.cash_after >= 0


def test_cash_never_goes_negative_even_when_the_target_is_unaffordable():
    r = session(pre_trade=PortfolioState(PRIOR, 5_000.0, {}),
                target_share_counts={"A": 100})          # NT$10,000 of stock
    assert r.cash_after >= 0
    assert r.shares_after.get("A", 0) * 100.0 <= 5_000.0


def test_costs_are_charged_and_the_three_components_stay_apart():
    r = session(target_share_counts={"A": 50})
    rec = r.receipts[0]
    assert rec.side == "buy"
    assert rec.transaction_tax == 0.0                    # buy side pays no tax
    assert rec.explicit_fee > 0 and rec.impact > 0
    totals = cost_totals(r.receipts)
    assert set(totals) >= {"explicit_fee", "transaction_tax", "impact"}
    with pytest.raises(AttributeError):
        _ = rec.total_cost / 0 if False else rec.__getattribute__("effective_rate")


def test_the_sell_side_pays_transaction_tax():
    pre = PortfolioState(PRIOR, 0.0, {"A": 50})
    r = session(pre_trade=pre, target_share_counts={})
    assert r.receipts[0].transaction_tax == pytest.approx(5_000.0 * 0.003)


def test_the_intraday_sequence_is_recorded_and_checked():
    r = session(target_share_counts={"A": 10})
    assert r.intraday_steps[0] == "start_of_trading_day"
    assert r.intraday_steps[-1] == "end_of_day_state"
    assert list(r.intraday_steps).index("apply_known_effective_corporate_actions") \
        < list(r.intraday_steps).index("obtain_permitted_execution_price")


def test_execution_day_data_may_not_come_from_the_execution_day():
    with pytest.raises(ExecutionError, match="G14-1"):
        session(data_as_of=DAY)


def test_an_order_without_a_permitted_price_does_not_become_a_fill():
    with pytest.raises(ExecutionError, match="6.5"):
        session(target_share_counts={"Z": 10}, adv20={"Z": 1e9},
                sigma20d={"Z": 0.02})



