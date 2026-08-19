"""Master preregistration clauses M-1 / M-2 / M-3.

These are the three rulings made at master-freeze time. Each is tested with a
negative control, because a clause that cannot be made to fire has not been
shown to constrain anything.
"""

import json

import pytest

from core.b0_master_prereg import (
    L2_FORBIDDEN_WORDS,
    L2_NOT_EVALUABLE,
    L2_NOT_SUPPORTED,
    L2_OUTCOMES,
    L2_SUPPORTED,
    NORMATIVE_PRECEDENCE,
    PIPELINE_STAGES,
    DataRepair,
    L2Opening,
    MasterPreregViolation,
    UnspecifiedBehaviour,
    assert_corporate_action_precedes_mark,
    assert_l2_wording,
    assert_no_scattered_dispatch,
    assert_repair_admissible,
    assert_rerun_admissible,
    assert_specified,
    assert_stage_order,
    classify_l2_termination,
    read_registry,
    record_opening,
    spec,
    specified_keys,
)


# --- precedence --------------------------------------------------------------

def test_precedence_is_declared_not_left_to_the_reader():
    assert NORMATIVE_PRECEDENCE == (
        "master_preregistration", "closure_prose", "legacy_code_or_comment")


# --- M-1 · pipeline order ----------------------------------------------------

def test_canonical_stage_order():
    assert PIPELINE_STAGES == (
        "pit_raw_state", "corporate_action_transition", "portfolio_mark",
        "eligibility", "features", "selection_score", "target_portfolio",
        "order_intents", "execution", "costs", "post_trade_nav")


def test_a_full_run_in_order_passes():
    assert_stage_order(list(PIPELINE_STAGES))


def test_stages_may_be_skipped_but_never_reordered():
    assert_stage_order(["pit_raw_state", "portfolio_mark", "post_trade_nav"])
    with pytest.raises(MasterPreregViolation, match="M-1"):
        assert_stage_order(["portfolio_mark", "corporate_action_transition"])


def test_marking_before_the_corporate_action_transition_is_rejected():
    """A mark taken on pre-event share counts is a silent NAV error."""
    with pytest.raises(MasterPreregViolation, match="M-1"):
        assert_corporate_action_precedes_mark(
            ["pit_raw_state", "portfolio_mark", "corporate_action_transition"])


def test_marking_with_no_transition_stage_at_all_is_rejected():
    with pytest.raises(MasterPreregViolation, match="O-A"):
        assert_corporate_action_precedes_mark(["pit_raw_state", "portfolio_mark"])


@pytest.mark.parametrize("stage", [
    "eligibility", "features", "selection_score", "target_portfolio",
    "order_intents", "execution", "costs", "post_trade_nav"])
def test_O_A_no_downstream_stage_may_run_without_the_transition(stage):
    """O-A: mandatory before ANY valuation or ordering, not merely before the
    mark. Discovering at execution time that a holding already had a corporate
    action is the failure this removes."""
    with pytest.raises(MasterPreregViolation, match="O-A"):
        assert_corporate_action_precedes_mark(["pit_raw_state", stage])


def test_O_A_a_raw_only_run_needs_no_transition():
    assert_corporate_action_precedes_mark(["pit_raw_state"])


def test_O_A_the_stage_carries_both_exposure_guards():
    from core.b0_master_prereg import CORPORATE_ACTION_STAGE_GUARDS
    assert CORPORATE_ACTION_STAGE_GUARDS == (
        "assert_exposure_reconstructible", "assert_no_unexplained_price_gap")


def test_eligibility_cannot_precede_the_mark_it_is_derived_from():
    """ADV_floor = 5 x port_value, so eligibility depends on the mark."""
    with pytest.raises(MasterPreregViolation):
        assert_stage_order(["eligibility", "portfolio_mark"])


def test_features_cannot_precede_eligibility():
    with pytest.raises(MasterPreregViolation):
        assert_stage_order(["features", "eligibility"])


def test_an_unknown_stage_is_unspecified_not_ignored():
    with pytest.raises(UnspecifiedBehaviour, match="M-3"):
        assert_stage_order(["pit_raw_state", "regime_overlay"])


# --- O-D · intraday sequence -------------------------------------------------

def test_intraday_sequence_is_frozen():
    from core.b0_master_prereg import INTRADAY_SEQUENCE
    assert INTRADAY_SEQUENCE == (
        "start_of_trading_day", "apply_known_effective_corporate_actions",
        "establish_tradable_holdings", "obtain_permitted_execution_price",
        "execute_child_orders", "apply_costs", "end_of_day_state")


def test_a_full_intraday_run_in_order_passes():
    from core.b0_master_prereg import INTRADAY_SEQUENCE, assert_intraday_order
    assert_intraday_order(list(INTRADAY_SEQUENCE))


def test_corporate_actions_must_be_applied_before_holdings_are_established():
    from core.b0_master_prereg import assert_intraday_order
    with pytest.raises(MasterPreregViolation, match="O-D"):
        assert_intraday_order(["start_of_trading_day",
                               "establish_tradable_holdings",
                               "apply_known_effective_corporate_actions"])


def test_a_price_may_not_be_obtained_before_the_holding_is_established():
    from core.b0_master_prereg import assert_intraday_order
    with pytest.raises(MasterPreregViolation, match="O-D"):
        assert_intraday_order(["obtain_permitted_execution_price",
                               "establish_tradable_holdings"])


def test_an_unknown_intraday_step_aborts():
    from core.b0_master_prereg import assert_intraday_order
    with pytest.raises(UnspecifiedBehaviour, match="O-D/M-3"):
        assert_intraday_order(["start_of_trading_day", "intraday_rebalance_peek"])


def test_decision_inputs_must_come_from_a_completed_prior_session():
    from core.b0_master_prereg import assert_decision_inputs_are_prior_session
    assert_decision_inputs_are_prior_session(
        "2019-05-01", {"adv20": "2019-04-30", "prices": "2019-04-30"})
    with pytest.raises(MasterPreregViolation, match="O-D"):
        assert_decision_inputs_are_prior_session(
            "2019-05-01", {"adv20": "2019-04-30", "prices": "2019-05-01"})


def test_credit_events_match_the_dividend_rulings():
    assert spec("cash_dividend_credit_event") == "payment_date"
    assert spec("decision_state_source") == "prior_completed_trading_session"


# --- O-B / O-C are recorded as frozen policy ---------------------------------

def test_O_B_permanent_disappearance_is_not_a_concept():
    assert spec("permanent_disappearance_is_a_concept") is False
    assert spec("stale_mark_session_tolerance") is None


def test_O_C_unflagged_capitalisation_gets_no_derivation_model():
    """No inference from a month-end registration stamp, and no new source is
    required before the final seal; a repair goes through the M-2 protocol."""
    assert spec("unflagged_capitalisation_policy") == "NOT_RECONSTRUCTIBLE_no_derivation"


def test_only_the_engine_may_dispatch_on_event_kinds():
    assert_no_scattered_dispatch({
        "core.b0_corporate_actions": ["handle_merger", "HANDLER_FUNCS"],
        "core.b0_execution": ["apply_corporate_actions", "port_value"],
    })


def test_scattered_dispatch_in_execution_is_rejected():
    with pytest.raises(MasterPreregViolation, match="core.b0_execution"):
        assert_no_scattered_dispatch({
            "core.b0_execution": ["handle_stock_dividend", "handle_merger"]})


def test_the_real_modules_do_not_scatter_dispatch():
    """Applied to the actual B0 modules, not only to a hand-made mapping."""
    import ast
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mapping = {}
    for name in sorted(os.listdir(os.path.join(repo, "core"))):
        if not name.startswith("b0_") or not name.endswith(".py"):
            continue
        path = os.path.join(repo, "core", name)
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        syms = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        syms |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        mapping[f"core.{name[:-3]}"] = syms
    assert "core.b0_corporate_actions" in mapping
    assert_no_scattered_dispatch(mapping)


# --- M-2 · L2 termination taxonomy -------------------------------------------

def test_the_outcome_taxonomy_is_closed_and_unrenamed():
    """v1.21 added the two names 6.1.14 already defined; nothing was renamed.

    Previously this asserted a count of three. The count was never the
    property worth pinning - the first sealed L2 run terminated in an outcome
    the vocabulary could not express, and a count would have forbidden the fix
    rather than caught the gap. What matters is that the original three keep
    their exact spellings and the set stays closed.
    """
    from core.b0_master_prereg import (
        L2_NOT_EVALUABLE_CA_BLOCK, L2_RUN_INVALID_CONFORMANCE)

    assert L2_SUPPORTED == "SUPPORTED"
    assert L2_NOT_SUPPORTED == "NOT_SUPPORTED"
    assert L2_NOT_EVALUABLE == "NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK"
    assert set(L2_OUTCOMES) == {
        L2_SUPPORTED, L2_NOT_SUPPORTED, L2_NOT_EVALUABLE,
        L2_NOT_EVALUABLE_CA_BLOCK, L2_RUN_INVALID_CONFORMANCE}


def test_a_reconstruction_abort_is_not_a_strategy_failure():
    from core.b0_corporate_actions import CorporateActionError
    assert classify_l2_termination(
        CorporateActionError("held through an unreconstructible event")
    ) == L2_NOT_EVALUABLE


def test_a_blocking_data_requirement_is_also_not_evaluable():
    from core.b0_frozen_spec import FrozenSpecViolation
    assert classify_l2_termination(FrozenSpecViolation("blocked")) == L2_NOT_EVALUABLE


def test_an_unclassified_termination_does_not_default_to_not_supported():
    """The dangerous default: any crash silently becoming a verdict."""
    with pytest.raises(UnspecifiedBehaviour, match="M-3"):
        classify_l2_termination(ZeroDivisionError("boom"))


def test_a_normal_termination_is_decided_by_the_gate_not_here():
    with pytest.raises(UnspecifiedBehaviour):
        classify_l2_termination(None)


@pytest.mark.parametrize("word", L2_FORBIDDEN_WORDS)
def test_l2_may_not_claim_validation(word):
    assert_l2_wording("B0 is Supported against the frozen benchmark.")
    with pytest.raises(MasterPreregViolation):
        assert_l2_wording(f"B0 is {word.lower()} on the window.")


# --- M-2 · opening registry ---------------------------------------------------

def _opening(**kw):
    base = dict(opened_at="2026-09-01T00:00:00Z", spec_sha256="s" * 64,
                code_commit="c" * 40, data_manifest_sha256="d" * 64,
                outcome=L2_NOT_EVALUABLE, detail="held 2317 through a gap")
    base.update(kw)
    return L2Opening(**base)


def test_an_opening_must_identify_what_was_run():
    for missing in ("spec_sha256", "code_commit", "data_manifest_sha256"):
        with pytest.raises(MasterPreregViolation, match=missing):
            _opening(**{missing: ""})


def test_an_undefined_outcome_is_rejected():
    with pytest.raises(UnspecifiedBehaviour):
        _opening(outcome="INCONCLUSIVE")


def test_a_not_evaluable_opening_is_still_recorded(tmp_path):
    """It touched the sealed window, so it counts as an effective observation."""
    path = str(tmp_path / "registry.jsonl")
    record_opening(_opening(), path)
    record_opening(_opening(opened_at="2026-10-01T00:00:00Z", outcome=L2_SUPPORTED), path)
    rows = read_registry(path)
    assert len(rows) == 2
    assert rows[0]["outcome"] == L2_NOT_EVALUABLE
    assert json.loads(json.dumps(rows))          # round-trips


def test_registry_is_append_only_in_effect(tmp_path):
    path = str(tmp_path / "registry.jsonl")
    record_opening(_opening(), path)
    record_opening(_opening(opened_at="2026-10-01T00:00:00Z"), path)
    assert len({r["opened_at"] for r in read_registry(path)}) == 2


def test_missing_registry_reads_as_empty_not_as_an_error(tmp_path):
    assert read_registry(str(tmp_path / "nope.jsonl")) == []


# --- M-2 · re-run admissibility ----------------------------------------------

def _repair(**kw):
    base = dict(description="65 stock dividends lack a credit date",
                independent_source="TWSE public filings, whole event class",
                scope="whole_source", performance_consulted=False,
                selected_by_portfolio_exposure=False)
    base.update(kw)
    return DataRepair(**base)


def test_a_clean_repair_permits_re_running_a_not_evaluable_window():
    assert_rerun_admissible(_opening(outcome=L2_NOT_EVALUABLE), _repair())


@pytest.mark.parametrize("outcome", [L2_SUPPORTED, L2_NOT_SUPPORTED])
def test_a_decided_window_may_never_be_re_run(outcome):
    with pytest.raises(MasterPreregViolation, match="no-post-hoc-rescue"):
        assert_rerun_admissible(_opening(outcome=outcome), _repair())


def test_re_running_without_a_repair_is_rejected():
    """v1.22: the message now NAMES the required kind, because R3 made the kinds
    non-interchangeable. Matching the bare word `repair` would pass whichever
    kind the message demanded, which is the distinction under test."""
    with pytest.raises(MasterPreregViolation, match="requires a DataRepair"):
        assert_rerun_admissible(_opening(outcome=L2_NOT_EVALUABLE), None)


def test_a_repair_chosen_after_seeing_performance_is_a_rescue():
    with pytest.raises(MasterPreregViolation, match="post-hoc rescue"):
        assert_repair_admissible(_repair(performance_consulted=True))


def test_repairing_only_what_the_portfolio_held_is_rejected():
    """'B0 happens to hold this one, let us fix that event' selects the data by
    the portfolio, which is the exact move the ruling forbids."""
    with pytest.raises(MasterPreregViolation, match="selects the data"):
        assert_repair_admissible(_repair(selected_by_portfolio_exposure=True))


def test_a_repair_must_name_its_independent_source():
    with pytest.raises(MasterPreregViolation, match="independent source"):
        assert_repair_admissible(_repair(independent_source="  "))


def test_an_undefined_repair_scope_aborts():
    with pytest.raises(UnspecifiedBehaviour):
        assert_repair_admissible(_repair(scope="the_ones_that_matter"))


# --- M-3 · no specification-by-code ------------------------------------------

def test_spec_has_no_default_argument():
    """A default is precisely how an undefined behaviour becomes a silent choice."""
    import inspect
    params = inspect.signature(spec).parameters
    assert set(params) == {"key"}
    assert not any(p in params for p in ("default", "fallback", "or_else"))


def test_an_undefined_key_aborts_rather_than_returning_a_reasonable_value():
    with pytest.raises(UnspecifiedBehaviour, match="M-3"):
        spec("rebalance_buffer_pct")


def test_frozen_values_are_sourced_from_the_modules_that_froze_them():
    from core import b0_corporate_actions as ca
    from core import b0_cost_model as cost
    from core import b0_frozen_spec as fs

    assert spec("commission_rate") == cost.COMMISSION_RATE
    assert spec("min_fee") == cost.MIN_FEE
    assert spec("tax_rate") == cost.TAX_RATE
    assert spec("impact_k") == cost.IMPACT_K
    assert spec("sharpe_metric_name") == fs.SHARPE_METRIC_NAME
    assert spec("chip_semantics") == fs.CHIP_SEMANTICS
    assert spec("cash_capital_increase_subscribe") is ca.CASH_CAPITAL_INCREASE_SUBSCRIBE
    assert spec("missing_data_rate_threshold") is None


def test_the_execution_and_selection_policy_is_pinned():
    assert spec("N_target") == 20
    assert spec("w_target") == spec("w_max") == 0.05
    assert spec("X_buy") == spec("X_sell") == 0.01
    assert spec("adv_floor_multiple") == spec("w_target") / spec("X_buy")
    assert spec("selection_free_parameters") == 0
    assert spec("concepts") == ("Quality", "Growth", "Value", "Momentum")
    assert spec("lookback_L_months") == 18
    assert spec("window_months") == 141
    assert spec("leverage_allowed") is False
    assert spec("reweight_when_under_target_breadth") is False


def test_assert_specified_reports_every_missing_key_at_once():
    assert_specified("N_target", "w_target")
    with pytest.raises(UnspecifiedBehaviour) as exc:
        assert_specified("N_target", "slippage_buffer", "rebalance_jitter")
    assert "slippage_buffer" in str(exc.value)
    assert "rebalance_jitter" in str(exc.value)


def test_no_key_is_silently_absent_from_the_listing():
    keys = specified_keys()
    assert keys == tuple(sorted(set(keys)))
    for k in ("N_target", "impact_k", "pipeline_stages", "l2_outcomes",
              "window_start", "window_end"):
        assert k in keys
