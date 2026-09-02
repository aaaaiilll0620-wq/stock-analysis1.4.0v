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
    FROZEN_B0_LINEAGE, LINEAGE_WINDOW_KEYS, MASTER_PREREG_DOCS,
    UnregisteredLineage, UnspecifiedBehaviour, declared_window_lineages,
    lineage_spec, spec, spec_document_sha256,
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


# --- preregistration documents ----------------------------------------------

def test_frozen_b0_document_hash_is_unchanged_by_default():
    """Every existing caller - including the pinned diagnostic runners - must
    keep the exact number it had before the lineage argument existed."""
    assert spec_document_sha256() == spec_document_sha256(FROZEN_B0_LINEAGE)
    assert MASTER_PREREG_DOCS[FROZEN_B0_LINEAGE] == (
        "docs/FrozenB0_MasterPreregistration.md")


def test_b1_has_its_own_document_and_it_is_not_b0s():
    assert MASTER_PREREG_DOCS["B1"] == "docs/B1_MasterPreregistration.md"
    assert spec_document_sha256("B1") != spec_document_sha256(FROZEN_B0_LINEAGE)


def test_a_lineage_without_a_document_fails_closed():
    """Reporting B0's hash for a lineage with no document of its own would let
    a run attest to a specification it does not follow."""
    with pytest.raises(UnregisteredLineage):
        spec_document_sha256("B2")


def test_b1_document_states_the_inheritance_base_it_actually_inherits():
    """B1 inherits B0's specification BY REFERENCE at a pinned sha256.

    If B0's document is ever edited, that pin silently becomes a claim about a
    document that no longer exists - and B1's whole 'differences only' structure
    rests on it. This test is the only thing that would notice.
    """
    doc = os.path.join(REPO, MASTER_PREREG_DOCS["B1"])
    text = open(doc, encoding="utf-8").read()
    actual = spec_document_sha256(FROZEN_B0_LINEAGE)
    assert actual in text, (
        "B1's preregistration names an inheritance base sha256 that is not the "
        "current sha256 of %s (now %s). Either B0's document was edited - which "
        "§0 of B1's document forbids - or the pin was never updated."
        % (MASTER_PREREG_DOCS[FROZEN_B0_LINEAGE], actual))


def test_b1_document_pins_the_window_the_code_declares():
    """The document and `_LINEAGE_WINDOWS` must not drift apart."""
    text = open(os.path.join(REPO, MASTER_PREREG_DOCS["B1"]),
                encoding="utf-8").read()
    assert lineage_spec("B1", "window_end") in text
    assert str(lineage_spec("B1", "window_months")) in text
