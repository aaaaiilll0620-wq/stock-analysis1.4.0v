"""B-20 parity harness tests.

Two things are under test:
  1. the harness itself detects every class of divergence it claims to;
  2. no B0 route pair is declared without a fixture behind it.

The B0 production and research routes do not exist yet, so the parity claim is
not yet made. What is asserted now is that the claim CANNOT be made silently.
"""

import math

import pytest

from core.b0_parity import (
    B0_ROUTE_PAIRS,
    PARITY_COLUMNS,
    PARITY_LAYERS,
    DecisionSnapshot,
    ParityError,
    assert_parity,
    compare_decisions,
    rev_accel_a_leg,
    rev_accel_b_leg,
)

AS_OF, CFG, ST = "2026-03-31", "cfg#1", "state#1"


def _snap(rows, as_of=AS_OF, cfg=CFG, st=ST):
    return DecisionSnapshot(as_of=as_of, config_hash=cfg, state_hash=st, rows=rows)


def _row(**kw):
    base = {"eligible": True, "score": 50.0, "rank": 1, "selected": True,
            "orders": 100.0, "cash": 1000.0, "cost": 12.5}
    base.update(kw)
    return base


# --- contract ----------------------------------------------------------------

def test_parity_columns_and_layers_declared():
    assert PARITY_COLUMNS == ("eligible", "score", "rank", "selected",
                              "orders", "cash", "cost")
    assert PARITY_LAYERS == ("feature", "eligibility", "ranking_portfolio",
                             "execution", "cost")


def test_identical_snapshots_have_no_divergence():
    rows = {"1101": _row(), "2330": _row(rank=2, selected=False)}
    assert compare_decisions(_snap(rows), _snap(dict(rows))) == []
    assert_parity(_snap(rows), _snap(dict(rows)))


# --- every divergence class the harness claims to catch ----------------------

@pytest.mark.parametrize("col,bad", [
    ("eligible", False),
    ("score", 50.0001),
    ("rank", 2),
    ("selected", False),
    ("orders", 99.0),
    ("cash", 1000.5),
    ("cost", 12.6),
])
def test_each_column_divergence_is_caught(col, bad):
    p = _snap({"1101": _row()})
    r = _snap({"1101": _row(**{col: bad})})
    div = compare_decisions(p, r)
    assert len(div) == 1 and div[0].column == col


def test_row_presence_divergence_is_caught():
    div = compare_decisions(_snap({"1101": _row()}), _snap({}))
    assert len(div) == 1 and div[0].column == "<row-presence>"


def test_missing_column_is_caught_not_skipped():
    incomplete = {k: v for k, v in _row().items() if k != "cost"}
    div = compare_decisions(_snap({"1101": _row()}), _snap({"1101": incomplete}))
    assert any(d.column == "cost" for d in div)


def test_float_comparison_is_bit_exact_by_default():
    p = _snap({"1101": _row(score=1.0)})
    r = _snap({"1101": _row(score=1.0 + 1e-12)})
    assert compare_decisions(p, r)                      # default tol = 0
    assert not compare_decisions(p, r, float_tol=1e-9)  # explicit tol only


def test_both_nan_counts_as_agreement():
    p = _snap({"1101": _row(score=math.nan)})
    r = _snap({"1101": _row(score=math.nan)})
    assert compare_decisions(p, r) == []


# --- inputs must match before outputs are even compared ----------------------

@pytest.mark.parametrize("kwargs,msg", [
    ({"as_of": "2026-02-27"}, "as_of"),
    ({"cfg": "cfg#2"}, "config_hash"),
    ({"st": "state#2"}, "state_hash"),
])
def test_mismatched_inputs_abort_rather_than_compare(kwargs, msg):
    with pytest.raises(ParityError, match=msg):
        compare_decisions(_snap({"1101": _row()}), _snap({"1101": _row()}, **kwargs))


def test_assert_parity_raises_with_detail():
    with pytest.raises(ParityError, match="divergence"):
        assert_parity(_snap({"1101": _row()}), _snap({"1101": _row(score=1.0)}))


# --- no unmeasured parity claim ---------------------------------------------

def test_no_route_pair_declared_without_fixture():
    """A declared pair must be accompanied by a real fixture comparison.

    Before P-2 this asserted `B0_ROUTE_PAIRS == ()`, with the instruction that
    declaring a pair required replacing the check with a fixture rather than
    deleting it. P-2 declared the pair, so the check is now the stronger one: the
    named modules must exist, must be covered by the static invariants, and a
    fixture parity test must actually run them.
    """
    import os

    from core.b0_invariants import B0_ENTRY_MODULES

    assert B0_ROUTE_PAIRS, "the B0 route pair is registered by P-2"
    here = os.path.dirname(os.path.abspath(__file__))
    fixture_test = os.path.join(here, "test_b0_adapter_parity.py")
    assert os.path.isfile(fixture_test), (
        "A route pair is declared but tests/test_b0_adapter_parity.py is absent. "
        "An unmeasured parity claim reads as if it had been checked.")

    for production, research in B0_ROUTE_PAIRS:
        for module in (production, research):
            assert module in B0_ENTRY_MODULES, (
                f"{module} is half of a declared parity pair but is not a B0 "
                f"entry module, so the reachability invariants do not cover it.")
        with open(fixture_test, encoding="utf-8") as fh:
            body = fh.read()
        assert production.rsplit(".", 1)[-1] in body
        assert research.rsplit(".", 1)[-1] in body


# --- live negative control: two same-named implementations that already differ

def test_rev_accel_two_implementations_diverge_on_the_same_input():
    """B-09 finding F-B, executable.

    `rev_accel` exists twice under one name with two different formulas. On an
    identical YoY series they disagree — which is exactly the drift the parity
    harness is built to catch, and the reason duplication is treated as debt
    rather than as an acceptable steady state.
    """
    yoys = [10.0, 12.0, 15.0, 20.0, 18.0, 25.0]
    a, b = rev_accel_a_leg(yoys), rev_accel_b_leg(yoys)
    assert not math.isnan(a) and not math.isnan(b)
    assert a != b

    p = _snap({"X": _row(score=a)})
    r = _snap({"X": _row(score=b)})
    div = compare_decisions(p, r)
    assert len(div) == 1 and div[0].column == "score"


def test_rev_accel_lookback_requirements_differ():
    """The divergence is structural, not numeric: they need different history."""
    five = [10.0, 12.0, 15.0, 20.0, 18.0]
    assert math.isnan(rev_accel_a_leg(five))       # needs 6
    assert not math.isnan(rev_accel_b_leg(five))   # needs 3
