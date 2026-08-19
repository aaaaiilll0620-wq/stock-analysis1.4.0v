# -*- coding: utf-8 -*-
"""B0.5 · ADV20 observed-zero conformance.

OBSERVED_ZERO != NOT_OBSERVED. Twenty fully observed sessions on which nobody
traded average to 0.0; that is a liquidity observation and the frozen floor
rejects it. Encoding it as absence made 4.2 abort instead, which is how
B04DIAG-d5f34a5164a0e309 stopped at 5/141 on a name quoted all year at a frozen
price with no turnover.

The formula, lookback, floor, ordering, order cap and portfolio construction are
untouched -- this is a zero-versus-missing repair and nothing else.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pytest

from core.b0_eligibility import EligibilityError, passes_investability
from core.b0_execution import order_cap_value
from core.b0_state import CoreStateError, MarketSnapshot, SourceAttestation

ATT = SourceAttestation(
    dataset_id="t", provenance_sha256="x", pit_guard_passed=True,
    universe_guard_passed=True,
    satisfied_blocking_requirements=("price_universe_survivorship",),
    synthetic=False)


def _rolling_mean(values, n):
    """The producer's own primitive, imported by path so the test binds to it."""
    import importlib.util, os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "research", "b0_materializer",
                        "build_market_side_state.py")
    spec = importlib.util.spec_from_file_location("_bmss", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._rolling_mean(np.asarray(values, dtype=float), n)


# --- R1 · the arithmetic ------------------------------------------------------

def test_twenty_observed_zero_volume_sessions_give_adv20_zero_not_na():
    close = np.full(20, 46.7)
    volume = np.zeros(20)
    adv = _rolling_mean(close * volume, 20)
    assert math.isfinite(adv[-1])
    assert adv[-1] == 0.0


def test_zeros_participate_in_a_mixed_window():
    close = np.full(20, 10.0)
    volume = np.zeros(20)
    volume[:10] = 100.0          # half the window traded
    adv = _rolling_mean(close * volume, 20)
    assert adv[-1] == pytest.approx(10.0 * 100.0 * 10 / 20)


def test_fewer_than_required_sessions_is_na():
    adv = _rolling_mean(np.full(19, 1.0), 20)
    assert not math.isfinite(adv[-1])


def test_a_missing_raw_observation_makes_the_window_na():
    """A complete session index but one absent required value stays NA."""
    turnover = np.full(20, 1.0)
    turnover[5] = np.nan
    adv = _rolling_mean(turnover, 20)
    assert not math.isfinite(adv[-1])


# --- R2 · zero is carried, not dropped ---------------------------------------

def test_the_snapshot_accepts_an_observed_zero_adv20():
    snap = MarketSnapshot(as_of="2014-11-28", attestation=ATT,
                          marks={"X": 46.7}, adv20={"X": 0.0},
                          sigma20d={"X": 0.0})
    assert snap.adv20["X"] == 0.0


def test_a_negative_adv20_is_still_rejected():
    with pytest.raises(CoreStateError):
        MarketSnapshot(as_of="d", attestation=ATT, marks={"X": 1.0},
                       adv20={"X": -1.0}, sigma20d={"X": 0.0})


def test_a_zero_mark_is_still_rejected():
    """Only turnover gained a meaningful zero. A price of zero is still nonsense."""
    with pytest.raises(CoreStateError):
        MarketSnapshot(as_of="d", attestation=ATT, marks={"X": 0.0},
                       adv20={"X": 1.0}, sigma20d={"X": 0.0})


# --- R4 · a zero-liquidity candidate fails the floor, it does not abort -------

def test_adv20_zero_fails_the_liquidity_floor_without_aborting():
    assert passes_investability(0.0, 1e7) is False


def test_a_missing_adv20_still_aborts():
    """R2: NA is reserved for a genuinely unavailable dependency, and 4.2's
    abort on it is unchanged."""
    from core import b0_eligibility as el
    src = open(el.__file__, encoding="utf-8").read()
    assert "no ADV20 for" in src


def test_complete_case_candidate_with_zero_adv20_is_ineligible_not_fatal():
    floor = 5.0 * 2_000_000.0
    assert passes_investability(0.0, floor) is False
    assert passes_investability(floor, floor) is True


# --- R5 · a held name with zero ADV20 has zero capacity -----------------------

def test_zero_adv20_gives_zero_executable_capacity():
    assert order_cap_value(0.0, 0.01) == 0.0


def test_capacity_is_not_manufactured_for_a_zero_adv20_holding():
    from core.b0_execution import cap_shares
    assert cap_shares(order_cap_value(0.0, 0.01), 46.7) == 0


def test_the_order_cap_still_rejects_a_negative_adv20():
    from core.b0_execution import ExecutionError
    with pytest.raises(ExecutionError):
        order_cap_value(-1.0, 0.01)


# --- R3 · corpus-wide, no special case ---------------------------------------

def test_no_security_or_period_specific_dispatch_in_the_producer():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "research", "b0_materializer",
                        "build_market_side_state.py")
    code = "\n".join(ln for ln in open(path, encoding="utf-8").read().splitlines()
                     if not ln.strip().startswith("#"))
    assert "6240" not in code
    assert not re.search(r"==\s*['\"]2014-11", code)
    assert not re.search(r"stock_id\s*==\s*['\"]\d{4}", code)


def test_the_producer_no_longer_encodes_an_observed_zero_as_absence():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "research", "b0_materializer",
                        "build_market_side_state.py")
    code = "\n".join(ln for ln in open(path, encoding="utf-8").read().splitlines()
                     if not ln.strip().startswith("#"))
    assert "elif adv <= 0:" not in code


# --- R4/R8 · the frozen formula and lookback did not move --------------------

def test_the_frozen_adv_formula_and_lookback_are_unchanged():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "research", "b0_materializer",
                        "build_market_side_state.py")
    src = open(path, encoding="utf-8").read()
    assert "turnover = close * volume" in src        # not traded_value, not VWAP
    assert "ADV_SESSIONS" in src
