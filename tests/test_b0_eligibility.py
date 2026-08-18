"""P-1b layer 2 · who may be ranked at all (§4, §8.7).

The gate's job is to be strictly upstream of ordering (§4.5). What is tested is
that each of the three exclusions actually excludes, that they are reported
separately (§9.1 S-4 makes the elimination composition a disclosure requirement,
not a total), and that the two places §4 insists must stay separate — the
capacity gate and the order cap — cannot be satisfied by one another.

The risk layer is now completely specified and very small: `net_margin < -10` is
the whole of it (C-20, C-29 ~ C-31, C-36). What these tests guard is that the
four removed legs stay removed — including the one whose removal is easiest to
reason wrongly about, since C-29 stripped the sector exemption that used to
guard the current-ratio floor and the tempting inference is that the floor
therefore binds everyone.
"""

import pytest

from core.b0_eligibility import (
    ANTI_CHASE_IS_HARD_EXCLUDE,
    ELIGIBILITY_LAYERS,
    CASH_QUALITY_ALIAS_ALLOWED,
    CASH_QUALITY_FILTER_ENABLED,
    CURRENT_RATIO_FLOOR_ENABLED,
    DEBT_HARD_FILTER_ENABLED,
    FROZEN_RISK_FILTERS,
    NET_MARGIN_FLOOR_PCT,
    RISK_FINANCIAL_EXEMPTION,
    RISK_LAYER_COMPLETE,
    EligibilityError,
    RiskFilter,
    adv_floor,
    assert_anti_chase_is_not_a_gate,
    assert_no_cash_quality_alias,
    assert_no_removed_legacy_leg,
    assert_no_sector_exemption,
    assert_eligibility_precedes_ranking,
    assert_no_retired_adv_floor_identifier,
    evaluate,
    frozen_risk_filters,
    passes_investability,
)
from core.b0_features import FeaturePanel, required_feature_keys
from core.b0_open_items import UnspecifiedCoreBehaviour

NO_FILTERS: list[RiskFilter] = []


def row(**over):
    r = {k: 0.5 for k in required_feature_keys()}
    r.update(over)
    return r


def panel(names, incomplete=(), overrides=None):
    values = {}
    for n in names:
        values[n] = row(PEG=None) if n in incomplete else row()
        if overrides and n in overrides:
            values[n].update(overrides[n])
    return FeaturePanel("2020-06-30", values)


# --- the derived floor --------------------------------------------------------

def test_adv_floor_is_five_times_port_value_and_is_derived_each_period():
    assert adv_floor(2_000_000.0) == 10_000_000.0      # the C_ref coincidence
    assert adv_floor(50_000_000.0) == 250_000_000.0    # ... and it does not stick
    with pytest.raises(EligibilityError, match="4.2"):
        adv_floor(0.0)


def test_the_retired_research_switch_may_not_be_reused_as_an_identity():
    assert_no_retired_adv_floor_identifier(["adv_floor", "port_value"])
    with pytest.raises(EligibilityError, match="4.2"):
        assert_no_retired_adv_floor_identifier(["--adv-floor"])
    with pytest.raises(EligibilityError, match="coincidence"):
        assert_no_retired_adv_floor_identifier(["adv100w"])


def test_investability_is_a_capacity_question_not_a_fill_rule():
    floor = adv_floor(2_000_000.0)
    assert passes_investability(floor, floor) is True
    assert passes_investability(floor - 1, floor) is False


# --- the unspecified risk layer ----------------------------------------------

def test_the_risk_layer_is_one_unconditional_filter_and_is_complete():
    """C-20 + C-29/30/31/36: four of the five legacy legs are gone."""
    assert [f.key for f in FROZEN_RISK_FILTERS] == ["net_margin_floor"]
    assert NET_MARGIN_FLOOR_PCT == -10.0
    assert RISK_LAYER_COMPLETE is True
    assert frozen_risk_filters(allow_incomplete=False) == FROZEN_RISK_FILTERS


def test_the_current_ratio_floor_is_removed_not_made_unconditional():
    """C-36: removing a carve-out does not promote the rule it carved out of."""
    assert CURRENT_RATIO_FLOOR_ENABLED is False
    filters = frozen_risk_filters(allow_incomplete=False)
    res = evaluate(panel(["illiquid_but_profitable"],
                         overrides={"illiquid_but_profitable":
                                    {"current_ratio": 20.0, "net_margin": 8.0}}),
                   {"illiquid_but_profitable": 1e9}, 2_000_000.0,
                   risk_filters=filters)
    assert res.eligible == ("illiquid_but_profitable",)
    # ... and it is still a higher-is-better Quality feature, not dropped
    from core.b0_features import FEATURE_BY_KEY
    assert FEATURE_BY_KEY["current_ratio"].orientation == "+"


def test_a_removed_leg_cannot_return_as_a_runtime_filter():
    assert_no_removed_legacy_leg(["net_margin_floor"])
    for revived in ("min_current_ratio", "max_debt_to_asset", "min_cash_quality"):
        with pytest.raises(EligibilityError, match="C-30/C-31/C-36"):
            assert_no_removed_legacy_leg([revived])


def test_there_is_no_sector_exemption_anywhere_in_eligibility():
    """C-29: removed, and named so its absence reads as decided not forgotten."""
    assert RISK_FINANCIAL_EXEMPTION is False
    assert_no_sector_exemption()
    with pytest.raises(EligibilityError, match="C-29"):
        assert_no_sector_exemption(["is_financial"])


def test_the_legacy_debt_hard_filter_tree_is_gone():
    """C-30: debt_to_asset survives only as the Quality feature (C-19)."""
    from core.b0_features import FEATURE_BY_KEY

    assert DEBT_HARD_FILTER_ENABLED is False
    assert not [f for f in FROZEN_RISK_FILTERS if "debt" in f.key]
    # ... and it is still a lower-is-better Selection feature, not dropped
    assert FEATURE_BY_KEY["debt_to_asset"].orientation == "-"


def test_a_deeply_indebted_but_profitable_name_is_no_longer_hard_excluded():
    """The 85/92/100/0 conditional tree is not relocated (C-30)."""
    filters = frozen_risk_filters(allow_incomplete=True)
    res = evaluate(panel(["levered"],
                         overrides={"levered": {"debt_to_asset": 95.0,
                                                "net_margin": 8.0}}),
                   {"levered": 1e9}, 2_000_000.0, risk_filters=filters)
    assert res.eligible == ("levered",)


def test_the_cash_quality_leg_cannot_return_under_another_name():
    """C-31: removed, and explicitly not re-pointed at ocf_to_net_income."""
    assert CASH_QUALITY_FILTER_ENABLED is False
    assert CASH_QUALITY_ALIAS_ALLOWED is False
    assert_no_cash_quality_alias(["net_margin_floor"])
    for alias in ("cash_quality", "ocf_to_net_income", "cash_conversion"):
        with pytest.raises(EligibilityError, match="C-31"):
            assert_no_cash_quality_alias([alias])


def test_allow_incomplete_has_no_default_so_evidence_cannot_be_produced_by_omission():
    with pytest.raises(TypeError):
        frozen_risk_filters()


def test_the_relocated_net_margin_floor_excludes_deep_losses_unconditionally():
    filters = frozen_risk_filters(allow_incomplete=True)
    res = evaluate(panel(["ok", "deep_loss"],
                         overrides={"ok": {"net_margin": -9.9},
                                    "deep_loss": {"net_margin": -10.1}}),
                   {"ok": 1e9, "deep_loss": 1e9},
                   2_000_000.0, risk_filters=filters)
    assert res.eligible == ("ok",)
    assert res.rejected["risk_hard_filter"] == ("deep_loss",)


def test_a_risk_filter_reads_values_not_identifiers():
    """A predicate that could look up a security by name could encode a list."""
    f = FROZEN_RISK_FILTERS[0]
    assert f.predicate({"net_margin": 5.0}) is True
    assert f.predicate({"net_margin": -50.0}) is False


def test_anti_chase_is_a_state_and_never_a_gate():
    assert ANTI_CHASE_IS_HARD_EXCLUDE is False
    assert_anti_chase_is_not_a_gate()


# --- the three gates ----------------------------------------------------------

def test_incomplete_case_removes_the_whole_row_and_is_never_partially_scored():
    res = evaluate(panel(["a", "b"], incomplete=["b"]), {"a": 1e9, "b": 1e9},
                   2_000_000.0, risk_filters=NO_FILTERS)
    assert res.eligible == ("a",)
    assert res.rejected["complete_case"] == ("b",)
    assert res.diagnostics["missing_by_feature"]["PEG"] == 1


def test_illiquid_names_are_excluded_by_the_derived_floor():
    res = evaluate(panel(["big", "small"]), {"big": 2e7, "small": 9_999_999.0},
                   2_000_000.0, risk_filters=NO_FILTERS)
    assert res.eligible == ("big",)
    assert res.rejected["dynamic_investability"] == ("small",)
    assert res.adv_floor == 10_000_000.0


def test_risk_filters_when_supplied_exclude_and_are_reported_separately():
    banned = RiskFilter("solvency", "fixture", lambda row: row["roe"] > 0)
    res = evaluate(panel(["good", "bad"], overrides={"bad": {"roe": -1.0}}),
                   {"good": 1e9, "bad": 1e9},
                   2_000_000.0, risk_filters=[banned])
    assert res.eligible == ("good",)
    assert res.rejected["risk_hard_filter"] == ("bad",)
    assert set(res.rejected) == set(ELIGIBILITY_LAYERS)


def test_elimination_composition_is_reported_not_netted():
    banned = RiskFilter("solvency", "fixture", lambda row: row["roe"] > 0)
    res = evaluate(panel(["ok", "c", "r", "l"], incomplete=["c"],
                         overrides={"r": {"roe": -1.0}}),
                   {"ok": 1e9, "c": 1e9, "r": 1e9, "l": 1.0},
                   2_000_000.0, risk_filters=[banned])
    counts = res.counts
    assert counts["universe"] == 4 and counts["eligible"] == 1
    assert counts["rejected_complete_case"] == 1
    assert counts["rejected_risk_hard_filter"] == 1
    assert counts["rejected_dynamic_investability"] == 1


def test_a_missing_liquidity_observation_is_not_evidence_of_liquidity():
    with pytest.raises(EligibilityError, match="4.2"):
        evaluate(panel(["a"]), {}, 2_000_000.0, risk_filters=NO_FILTERS)


def test_a_name_with_no_panel_row_aborts_rather_than_being_assumed():
    with pytest.raises(EligibilityError, match="4.1"):
        evaluate(panel(["a"]), {"a": 1e9, "ghost": 1e9}, 2_000_000.0,
                 risk_filters=NO_FILTERS, universe=["a", "ghost"])


def test_risk_filters_argument_has_no_default():
    with pytest.raises(TypeError):
        evaluate(panel(["a"]), {"a": 1e9}, 2_000_000.0)


# --- ordering -----------------------------------------------------------------

def test_exclusion_must_come_before_ordering():
    assert_eligibility_precedes_ranking(
        ["eligibility", "features", "selection_score"])
    with pytest.raises(EligibilityError, match="4.5"):
        assert_eligibility_precedes_ranking(["features", "selection_score"])


def test_reordering_the_pipeline_is_caught_by_m1():
    from core.b0_master_prereg import MasterPreregViolation

    with pytest.raises(MasterPreregViolation):
        assert_eligibility_precedes_ranking(["selection_score", "eligibility"])
