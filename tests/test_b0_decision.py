"""P-1b layer 3 · SelectionScore, ranking and targets (§3.1, §5, §8.7).

Scoring mechanics are tested against injected percentiles rather than against a
feature panel, for two reasons. The honest one: nine of the eleven formulas are
UNSPECIFIED, so a panel of real feature values does not exist yet. The better
one: a scoring test that had to build real features would be testing the feature
layer again, and would go green or red for reasons that have nothing to do with
whether concept weighting is equal.

The sizing rules get the most attention because §5 forbids the obvious
implementation. `1/n` is the natural thing to write and it is banned in as many
words: it would make `w_max` vacuous and would push single-name exposure to its
maximum in precisely the periods when the opportunity set is thinnest.
"""

import ast

import pytest

from core.b0_decision import (
    FORBIDDEN_SYMBOLS,
    FORBIDDEN_TIE_BREAK_KEYS,
    TIE_BREAKS,
    DecisionError,
    assert_no_reweighting,
    concept_score,
    member_percentiles,
    rank,
    score_eligible,
    select,
    selection_score,
    target_portfolio,
)
from core.b0_features import FeaturePanel, required_feature_keys
from core.b0_open_items import UnspecifiedCoreBehaviour

TIE = "stock_id_ascending"


def percentiles(spec: dict[str, dict[str, float]]):
    """spec[stock][feature] -> percentile, filled to the full frozen graph."""
    out = {}
    for key in required_feature_keys():
        out[key] = {sid: vals.get(key, 0.5) for sid, vals in spec.items()}
    return out


# --- scoring ------------------------------------------------------------------

def test_concepts_are_equally_weighted_within_and_across():
    p = percentiles({"a": {"roe": 1.0, "net_margin": 1.0, "gross_margin": 1.0,
                           "debt_to_asset": 1.0, "current_ratio": 1.0}})
    assert concept_score(p, "Quality", "a") == 1.0
    assert concept_score(p, "Momentum", "a") == 0.5
    # Quality at 1.0, the other three concepts at 0.5 -> (1 + .5 + .5 + .5) / 4
    assert selection_score(p, "a") == pytest.approx(0.625)


def test_a_single_member_concept_is_not_weighted_less_than_a_five_member_one():
    """Momentum has one member and Quality has five; §3.1 weights them equally."""
    q = percentiles({"a": {k: 1.0 for k in
                           ("roe", "net_margin", "gross_margin",
                            "debt_to_asset", "current_ratio")}})
    m = percentiles({"a": {"momentum_12_1": 1.0}})
    assert selection_score(q, "a") == selection_score(m, "a")


def test_dropping_an_absent_member_would_reweight_the_concept_so_it_aborts():
    p = percentiles({"a": {}})
    del p["roe"]["a"]
    with pytest.raises(DecisionError, match="reweight"):
        concept_score(p, "Quality", "a")


def test_a_none_reaching_ranking_means_the_complete_case_gate_was_bypassed():
    row = {k: 0.5 for k in required_feature_keys()}
    row["PEG"] = None
    panel = FeaturePanel("2020-06-30", {"a": row, "b":
                                        {k: 0.5 for k in required_feature_keys()}})
    with pytest.raises(DecisionError, match="4.1"):
        member_percentiles(panel, ["a", "b"], convention="average_rank")


def test_scoring_runs_end_to_end_now_that_direction_is_frozen():
    """C-19 closed the last blocker on the scoring path itself."""
    base = {k: 0.5 for k in required_feature_keys()}
    good = dict(base, roe=9.0, debt_to_asset=10.0, PEG=0.5)
    poor = dict(base, roe=1.0, debt_to_asset=90.0, PEG=9.0)
    panel = FeaturePanel("2020-06-30", {"good": good, "poor": poor})

    scores = score_eligible(panel, ["good", "poor"], convention="average_rank")
    # Low leverage and low PEG must score ABOVE their opposites, not below.
    assert scores["good"] > scores["poor"]


def test_a_high_debt_name_is_not_rewarded_for_its_debt():
    """The inversion C-19 exists to prevent, stated as an assertion."""
    base = {k: 0.5 for k in required_feature_keys()}
    panel = FeaturePanel("2020-06-30", {
        "levered": dict(base, debt_to_asset=95.0),
        "safe": dict(base, debt_to_asset=5.0)})
    scores = score_eligible(panel, ["levered", "safe"], convention="average_rank")
    assert scores["safe"] > scores["levered"]


# --- ranking ------------------------------------------------------------------

def test_tie_break_is_required_and_frozen_to_stock_id_ascending():
    """C-33: canonical sort key is (-SelectionScore, stock_id ascending)."""
    with pytest.raises(TypeError):
        rank({"a": 1.0})
    assert TIE_BREAKS == ("stock_id_ascending",)
    assert rank({"bbb": 0.5, "aaa": 0.5}, tie_break=TIE) == ("aaa", "bbb")


def test_no_other_alpha_may_enter_through_the_tie():
    """Market cap or ADV as a secondary key would be an unregistered signal."""
    for forbidden in FORBIDDEN_TIE_BREAK_KEYS:
        with pytest.raises(DecisionError, match="C-33"):
            rank({"a": 1.0, "b": 1.0}, tie_break=forbidden)


def test_ranking_is_highest_score_first():
    assert rank({"a": 0.1, "b": 0.9, "c": 0.5}, tie_break=TIE) == ("b", "c", "a")
    assert TIE_BREAKS == ("stock_id_ascending",)


def test_selection_is_capped_at_n_target():
    scores = {f"s{i:02d}": 1.0 - i / 100 for i in range(30)}
    assert len(select(scores, tie_break=TIE)) == 20


def test_selection_shrinks_to_breadth_when_fewer_names_are_eligible():
    scores = {f"s{i}": 1.0 - i / 10 for i in range(5)}
    assert len(select(scores, tie_break=TIE)) == 5


# --- targets ------------------------------------------------------------------

def test_full_breadth_is_five_percent_each_and_fully_invested():
    tp = target_portfolio("2020-06-30", [f"s{i:02d}" for i in range(20)])
    assert set(tp.weights.values()) == {0.05}
    assert tp.cash_weight == pytest.approx(0.0)


def test_thin_breadth_goes_to_cash_and_never_to_one_over_n():
    tp = target_portfolio("2020-06-30", [f"s{i}" for i in range(15)])
    assert all(w == 0.05 for w in tp.weights.values())
    assert sum(tp.weights.values()) == pytest.approx(0.75)
    assert tp.cash_weight == pytest.approx(0.25)
    assert tp.diagnostics["under_invested_by_breadth"] is True
    # the forbidden alternative, stated so the intent survives a later reading
    assert tp.weights["s0"] != pytest.approx(1 / 15)


def test_one_over_n_weighting_is_detected_after_the_fact():
    assert_no_reweighting({f"s{i}": 0.05 for i in range(20)})
    with pytest.raises(DecisionError, match="1/n"):
        assert_no_reweighting({f"s{i}": 1 / 15 for i in range(15)})


def test_more_than_n_target_names_cannot_be_targeted():
    with pytest.raises(DecisionError, match="N_target"):
        target_portfolio("2020-06-30", [f"s{i:02d}" for i in range(21)])


def test_duplicate_selection_aborts():
    with pytest.raises(DecisionError, match="duplicate"):
        target_portfolio("2020-06-30", ["a", "a"])


# --- the §8.7 responsibility boundary, checked mechanically -------------------

def test_the_decision_layer_does_not_reimplement_a_feature_formula():
    """§8.7: b0_decision must not re-derive features. Checked by AST, not by eye."""
    import core.b0_decision as mod

    with open(mod.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not (called & set(FORBIDDEN_SYMBOLS)), (
        f"b0_decision calls a feature-formula entry point: "
        f"{sorted(called & set(FORBIDDEN_SYMBOLS))}")
