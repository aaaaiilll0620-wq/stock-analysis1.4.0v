# -*- coding: utf-8 -*-
"""B1 lineage scoping: a second lineage must not be able to reach B0's artefacts.

The failure this guards against is not malice. It is an ordinary
`python build_market_side_state.py` with the wrong environment, which would
rewrite Frozen B0's 141 sealed market-side state hashes in place.
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(REPO, "research", "b0_materializer",
                       "build_market_side_state.py")

from core.b0_master_prereg import (  # noqa: E402
    FROZEN_B0_LINEAGE, LINEAGE_WINDOW_KEYS, UnregisteredLineage,
    UnspecifiedBehaviour, declared_window_lineages, lineage_spec, spec,
)


def _load_builder(lineage=None):
    if lineage is None:
        os.environ.pop("B0_MATERIALIZE_LINEAGE", None)
    else:
        os.environ["B0_MATERIALIZE_LINEAGE"] = lineage
    try:
        s = importlib.util.spec_from_file_location("_bmss_probe", BUILDER)
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        return m
    finally:
        os.environ.pop("B0_MATERIALIZE_LINEAGE", None)


# --- the accessor -----------------------------------------------------------

def test_frozen_b0_window_is_not_restated_it_delegates():
    """B0's three numbers must keep exactly one home (the C-55 shape)."""
    for key in LINEAGE_WINDOW_KEYS:
        assert lineage_spec(FROZEN_B0_LINEAGE, key) == spec(key)


def test_b1_has_its_own_window_and_it_is_the_derived_one():
    assert lineage_spec("B1", "window_start") == "2014-07-31"
    assert lineage_spec("B1", "window_end") == "2026-07-31"
    assert lineage_spec("B1", "window_months") == 145
    # and it must not have leaked into Frozen B0
    assert spec("window_end") == "2026-03-31"
    assert spec("window_months") == 141


@pytest.mark.parametrize("bad", ["B2", "FROZEN_BO", "b1", ""])
def test_an_undeclared_lineage_fails_closed(bad):
    """A silent fallback to B0 is how a B1 build overwrites B0."""
    with pytest.raises(UnregisteredLineage):
        lineage_spec(bad, "window_end")


def test_a_non_window_key_is_not_answerable_per_lineage():
    with pytest.raises(UnspecifiedBehaviour):
        lineage_spec("B1", "concepts")


def test_declaring_a_window_is_not_registering_the_lineage():
    """B1 may have a window declared and STILL have no reopening path.

    The separation is what makes the declaration admissible: v1.33 was rejected
    because a window moved after its lineage had opened, so B1's window has to
    be frozen BEFORE B1 can run.
    """
    from core.b0_master_prereg import REGISTERED_L2_LINEAGES
    assert "B1" in declared_window_lineages()
    assert "B1" not in REGISTERED_L2_LINEAGES


# --- the write guard --------------------------------------------------------

def test_default_lineage_keeps_b0_paths_and_window_exactly():
    m = _load_builder()
    assert m.LINEAGE == FROZEN_B0_LINEAGE
    assert os.path.realpath(m.OUTDIR) == os.path.realpath(
        os.path.join(REPO, "data", "b0", "market_state"))
    assert (m.WINDOW_START, m.WINDOW_END, m.WINDOW_MONTHS) == (
        "2014-07-31", "2026-03-31", 141)


def test_b1_gets_its_own_root_and_its_own_receipt():
    m = _load_builder("B1")
    assert os.path.realpath(m.OUTDIR) == os.path.realpath(
        os.path.join(REPO, "data", "b1", "market_state"))
    assert m.RECEIPT.endswith("market_side_state_receipt_b1.json")
    assert (m.WINDOW_START, m.WINDOW_END, m.WINDOW_MONTHS) == (
        "2014-07-31", "2026-07-31", 145)


@pytest.mark.parametrize("target", [
    os.path.join("data", "b0", "market_state"),
    os.path.join("data", "b0", "market_state", "2014-08.parquet"),
    os.path.join("data", "b1", "..", "b0", "market_state", "x.parquet"),
])
def test_a_non_b0_lineage_may_not_write_under_b0_state(target):
    """Resolved-path check, so `..` and symlinks cannot walk in."""
    m = _load_builder("B1")
    with pytest.raises(SystemExit):
        m.assert_not_writing_into_frozen_b0(os.path.join(REPO, target))


def test_the_guard_does_not_obstruct_its_own_lineage_or_b0():
    b1 = _load_builder("B1")
    b1.assert_not_writing_into_frozen_b0(
        os.path.join(REPO, "data", "b1", "market_state", "2014-08.parquet"))
    b0 = _load_builder()
    b0.assert_not_writing_into_frozen_b0(
        os.path.join(REPO, "data", "b0", "market_state", "2014-08.parquet"))
