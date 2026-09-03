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


def test_b1_inherits_frozen_b0s_window_by_reference_not_by_copy():
    """B1's retrospective leg IS Frozen B0's window, and must stay so.

    The first declaration gave B1 its own 145-month window ending 2026-07-31,
    justified from `trading_calendar.csv` ending 2026-08-17. The calendar is not
    the binding corpus: every sealed panel is clipped to B0's window_end
    (price_panel date_max 2026-04-01, valuation_panel 141 periods, financials
    and revenue window_end 2026-03-31), so the four extra months had no as-of
    price, no execution price and no valuation.

    Inheritance rather than a literal 141 is the point. A copy agrees right up
    until the day it does not, and a shared window is what isolates B1's three
    corporate-action rulings as the only moving part between the two lineages.

    It does NOT mean B1's market-side state equals B0's. That was drafted and
    measured false: `reconstructibility` travels from the ledger into the hashed
    market state, so CA-1 reaches the market side without ever being called from
    it, and 129 of 141 periods differ - all 795 changes in the single direction
    NOT_RECONSTRUCTIBLE -> NOT_APPLICABLE.
    """
    for key in LINEAGE_WINDOW_KEYS:
        assert lineage_spec("B1", key) == spec(key)
    assert lineage_spec("B1", "window_end") == "2026-03-31"
    assert lineage_spec("B1", "window_months") == 141


def test_the_four_extra_months_have_no_sealed_inputs_to_be_evaluated_over():
    """The falsified justification, kept as a regression.

    If someone re-extends B1's window from the trading calendar, this is the
    fact that has to be dealt with first rather than discovered at build time.
    """
    import csv as _csv
    import json as _json

    cal = sorted(r["session"] for r in _csv.DictReader(
        open(os.path.join(REPO, "data", "b0", "trading_calendar.csv"),
             encoding="utf-8")))
    assert cal[-1] == "2026-08-17", (
        "the trading calendar no longer ends where the falsified B1 window "
        "justification said it did; re-derive that argument before trusting it")

    receipt = _json.load(open(
        os.path.join(REPO, "research", "b0_materializer",
                     "price_panel_receipt.json"), encoding="utf-8"))
    assert receipt["date_max"] == "2026-04-01", (
        "the price panel's coverage moved. The B1 window was inherited BECAUSE "
        "the panel stopped at B0's last execution date; if that is no longer "
        "true the inheritance is a choice again and needs its own ruling.")
    assert receipt["date_max"] < cal[-1], (
        "calendar and price coverage now agree, which is the one thing the "
        "original 145-month derivation assumed and which was never true")


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
        "2014-07-31", "2026-03-31", 141)


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
    """The document and the window register must not drift apart."""
    text = open(os.path.join(REPO, MASTER_PREREG_DOCS["B1"]),
                encoding="utf-8").read()
    assert lineage_spec("B1", "window_end") in text
    assert str(lineage_spec("B1", "window_months")) in text
    # The withdrawn 145-month window may still APPEAR in the document - the
    # withdrawal is recorded there - but the row that DECLARES window_end must
    # carry the operative value, not the withdrawn one.
    row = [l for l in text.splitlines() if l.startswith("| `window_end` |")]
    assert len(row) == 1, "expected exactly one window_end declaration row"
    assert lineage_spec("B1", "window_end") in row[0]
    assert "2026-07-31" not in row[0]


# --- the rest of the build chain --------------------------------------------
# The materializer was made lineage-aware first and the other two stages were
# not, which meant a B1 build could produce B1 market states and then freeze and
# seal B0's hashes under B1's name. All three stages read the SAME environment
# variable so that one setting governs the whole chain.

FREEZER = os.path.join(REPO, "research", "b0_registry",
                       "freeze_master_prereg.py")
SEALER = os.path.join(REPO, "scripts", "b0_baseline_seal.py")


def _load_script(path, name, lineage=None):
    if lineage is None:
        os.environ.pop("B0_MATERIALIZE_LINEAGE", None)
    else:
        os.environ["B0_MATERIALIZE_LINEAGE"] = lineage
    try:
        s = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        return m
    finally:
        os.environ.pop("B0_MATERIALIZE_LINEAGE", None)


def test_the_freezer_keeps_b0s_paths_exactly_by_default():
    f = _load_script(FREEZER, "_freeze_probe_b0")
    assert f.DATA_ROOT == "data/b0"
    assert os.path.basename(f.OUT) == "master_prereg_freeze.json"
    assert f.DERIVED_ARTEFACTS == f._DERIVED_ARTEFACTS_B0


def test_the_freezer_re_roots_onto_b1_without_shortening_the_list():
    """A lineage that sealed a SHORTER list of artefacts than B0 and called it
    the same baseline would be attesting to less than it appears to."""
    f = _load_script(FREEZER, "_freeze_probe_b1", "B1")
    assert f.DATA_ROOT == "data/b1"
    assert os.path.basename(f.OUT) == "master_prereg_freeze_b1.json"
    assert len(f.DERIVED_ARTEFACTS) == len(f._DERIVED_ARTEFACTS_B0)
    assert all(p.startswith("data/b1/") for p in f.DERIVED_ARTEFACTS)


def test_the_freezer_refuses_to_overwrite_b0s_freeze_registry():
    f = _load_script(FREEZER, "_freeze_probe_guard", "B1")
    with pytest.raises(SystemExit):
        f.assert_not_overwriting_frozen_b0(
            os.path.join(f.HERE, "master_prereg_freeze.json"))


def test_the_sealer_reads_the_freeze_record_of_the_lineage_it_seals():
    b0 = _load_script(SEALER, "_seal_probe_b0")
    b1 = _load_script(SEALER, "_seal_probe_b1", "B1")
    assert os.path.basename(b0.FREEZE) == "master_prereg_freeze.json"
    assert os.path.basename(b1.FREEZE) == "master_prereg_freeze_b1.json"
    assert os.path.basename(b0.OUT_DIR) == "baseline_seal"
    assert os.path.basename(b1.OUT_DIR) == "baseline_seal_b1"


def test_a_foreign_seal_may_not_land_in_b0s_seal_archive():
    """The archive is content-addressed and append-only, so a foreign seal would
    not overwrite anything - it would join B0's lineage ledger and be read later
    as one of B0's own."""
    b1 = _load_script(SEALER, "_seal_probe_guard", "B1")
    with pytest.raises(SystemExit):
        b1.assert_not_writing_into_frozen_b0_seals(
            os.path.join(REPO, "artifacts", "baseline_seal", "seals"))


def test_the_seal_names_the_document_it_hashes():
    """A seal naming B1's document while hashing B0's would attest to a
    specification it does not follow."""
    from core.b0_provenance import SpecificationProvenance

    for lineage in (FROZEN_B0_LINEAGE, "B1"):
        sp = SpecificationProvenance.from_frozen_master("x.y", lineage=lineage)
        assert sp.document == MASTER_PREREG_DOCS[lineage]
        assert sp.spec_sha256 == spec_document_sha256(lineage)
    b0 = SpecificationProvenance.from_frozen_master("1.37")
    assert b0.document == MASTER_PREREG_DOCS[FROZEN_B0_LINEAGE]


def test_an_unregistered_lineage_cannot_have_its_document_hashed():
    with pytest.raises(UnregisteredLineage):
        spec_document_sha256("B2")
