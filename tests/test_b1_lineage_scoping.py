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


def test_the_window_was_declared_before_the_lineage_was_registered():
    """The separation is what makes B1's window admissible at all.

    v1.33 was rejected because a window moved AFTER its lineage had opened and
    scored. B1's window was frozen while B1 was still unregistered and could not
    run; registration came afterwards, on 2026-09-03. Both facts are now true at
    once, and the ORDER is the whole argument - so what is pinned here is that
    the window register and the lineage register are separate mechanisms, not
    that B1 is absent from one of them.
    """
    from core.b0_master_prereg import REGISTERED_L2_LINEAGES

    assert "B1" in declared_window_lineages()
    assert "B1" in REGISTERED_L2_LINEAGES
    # separable: a lineage may have a window and no registration. B2 has
    # neither, and asking either register about it fails closed rather than
    # defaulting to B0's answer.
    assert "B2" not in declared_window_lineages()
    assert "B2" not in REGISTERED_L2_LINEAGES
    with pytest.raises(UnregisteredLineage):
        lineage_spec("B2", "window_end")


def test_b1_is_registered_as_unspent_not_merely_present():
    """True and False mean different things here, and B1's value is the claim
    that its once-only observation budget is still intact."""
    from core.b0_master_prereg import REGISTERED_L2_LINEAGES, l2_replay_permitted

    assert REGISTERED_L2_LINEAGES["B1"] is True
    assert l2_replay_permitted("B1") is True
    assert l2_replay_permitted(FROZEN_B0_LINEAGE) is False


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


# =============================================================================
# The rest of the build chain: opener, runner, period-1 builder.
#
# Materialize -> freeze -> seal was made lineage-aware first. Everything AFTER
# the seal was not, and the gap was not cosmetic: the opener bound B0's seal
# archive, B0's freeze record and B0's period-1 receipt whatever lineage was
# being opened, and the runner would then have executed B0's `data/b0` panels
# and appended B1's terminal row to B0's opening registry.
# =============================================================================

OPENER = os.path.join(REPO, "scripts", "b0_open_l2.py")
RUNNER = os.path.join(REPO, "research", "b0_l2", "run_sealed_l2.py")
PERIOD1 = os.path.join(REPO, "research", "b0_materializer",
                       "build_period1_full_input.py")


def _rel(path):
    return os.path.relpath(path, REPO).replace("\\", "/")


# --- one reader for the whole chain ------------------------------------------

def test_only_the_specification_module_reads_the_lineage_environment():
    """Five stages, one reader.

    Each stage used to call `os.environ.get` with its own default and its own
    idea of how a lineage becomes a path suffix. Separate readers that must
    agree are readers that eventually will not, and the failure is not a crash:
    it is a seal binding one lineage's artefacts under another's name.
    """
    import re
    import subprocess

    # Naming the variable in a usage string is fine; READING it is what may
    # only happen once, so the probe looks for the read rather than the name.
    read = re.compile(r"(environ\b[^\n]*(B0_MATERIALIZE_LINEAGE|LINEAGE_ENV_VAR)"
                      r"|(B0_MATERIALIZE_LINEAGE|LINEAGE_ENV_VAR)[^\n]*environ\b)")
    proc = subprocess.run(["git", "ls-files", "--", "*.py"], cwd=REPO,
                          capture_output=True, text=True)
    hits = set()
    for rel in proc.stdout.splitlines():
        rel = rel.strip()
        if not rel or rel.startswith("tests/"):
            continue
        with open(os.path.join(REPO, rel), encoding="utf-8-sig") as fh:
            if read.search(fh.read()):
                hits.add(rel)
    assert hits == {"core/b0_master_prereg.py"}, (
        "the lineage environment variable must be read in exactly one place; "
        "these also read it: %s" % sorted(hits - {"core/b0_master_prereg.py"}))


def test_an_unregistered_lineage_is_refused_rather_than_defaulted():
    """In BOTH directions.

    Defaulting a mistyped `B1` to Frozen B0 would let a B1 build write over B0's
    sealed artefacts; accepting the string would build, freeze and seal a
    lineage with no registration behind it.
    """
    from core.b0_master_prereg import active_lineage

    assert active_lineage({}) == FROZEN_B0_LINEAGE
    assert active_lineage({"B0_MATERIALIZE_LINEAGE": ""}) == FROZEN_B0_LINEAGE
    assert active_lineage({"B0_MATERIALIZE_LINEAGE": " B1 "}) == "B1"
    for bad in ("FROZEN_BO", "b1", "B2", "../b0"):
        with pytest.raises(UnregisteredLineage):
            active_lineage({"B0_MATERIALIZE_LINEAGE": bad})


def test_frozen_b0s_paths_are_the_historical_ones_byte_for_byte():
    """Every helper must reproduce B0's existing paths exactly.

    They are quoted in the Master, in the attestation ledger and in seventeen
    archived seals. A helper that "tidied" one of them would invalidate evidence
    to gain symmetry.
    """
    from core import b0_l2_run_layout as layout
    from core.b0_master_prereg import (
        DEFAULT_REGISTRY_PATH, lineage_data_root, lineage_freeze_path,
        lineage_market_state_manifest, lineage_period1_receipt_path,
        lineage_registry_path, lineage_seal_archive_root, lineage_suffix,
    )

    b0 = FROZEN_B0_LINEAGE
    assert lineage_suffix(b0) == ""
    assert _rel(lineage_data_root(b0)) == "data/b0"
    assert _rel(lineage_freeze_path(b0)) == \
        "research/b0_registry/master_prereg_freeze.json"
    assert lineage_registry_path(b0) == DEFAULT_REGISTRY_PATH
    assert _rel(layout.lineage_run_root(b0)) == "artifacts/l2_run"
    assert layout.lineage_opening_claims_root(b0) == layout.OPENING_CLAIMS_ROOT
    assert layout.lineage_runs_root(b0) == layout.RUNS_ROOT

    # The R5 admission constants and the helpers must resolve to the same
    # strings. `assert_runner_admissible` reads the constants for B0 so that the
    # opening-protocol tests can substitute a whole fake repository and drive
    # the real code; this is the assertion that stops the two from drifting.
    assert layout.FREEZE_PATH == lineage_freeze_path(b0)
    assert layout.MANIFEST_PATH == lineage_market_state_manifest(b0)
    assert layout.PERIOD1_RECEIPT == lineage_period1_receipt_path(b0)
    assert layout.SEAL_ARCHIVE_ROOT == lineage_seal_archive_root(b0)


def test_every_b1_path_is_disjoint_from_every_b0_path():
    from core import b0_l2_run_layout as layout
    from core.b0_master_prereg import (
        lineage_data_root, lineage_freeze_path, lineage_market_state_manifest,
        lineage_nonconsumption_path, lineage_period1_receipt_path,
        lineage_registry_path, lineage_seal_archive_root, lineage_seal_dir,
    )

    resolvers = (lineage_data_root, lineage_freeze_path,
                 lineage_market_state_manifest, lineage_nonconsumption_path,
                 lineage_period1_receipt_path, lineage_registry_path,
                 lineage_seal_archive_root, lineage_seal_dir,
                 layout.lineage_run_root, layout.lineage_runs_root,
                 layout.lineage_opening_claims_root)
    for resolve in resolvers:
        b0, b1 = resolve(FROZEN_B0_LINEAGE), resolve("B1")
        assert b0 != b1, "%s does not separate the lineages" % resolve.__name__
        assert not os.path.realpath(b1).startswith(
            os.path.realpath(b0) + os.sep), (
            "%s puts B1 inside B0's tree" % resolve.__name__)


# --- the opening accounting --------------------------------------------------

def test_b1_does_not_inherit_b0s_spent_observation_budget():
    """The defect this replaced was silent and terminal.

    The accounting counted claim FILES IN A GLOBAL DIRECTORY, so B1 would have
    reported `attempted_openings 2 / effective_observations 1` against
    `openings_permitted 1` - a budget already exhausted, for a lineage that has
    opened nothing.
    """
    from core.b0_l2_run_layout import (
        LEGACY_ATTEMPTED_OPENING, lineage_attempted_opening_count,
    )
    from core.b0_master_prereg import (
        effective_observation_count, lineage_registry_path, read_registry,
    )

    assert lineage_attempted_opening_count(FROZEN_B0_LINEAGE) >= 1
    assert lineage_attempted_opening_count("B1") == 0
    assert effective_observation_count(lineage_registry_path("B1")) == 0
    assert read_registry(lineage_registry_path("B1")) == []
    # B0's own pre-C-59 first attempt is B0's. It is pinned in the module
    # rather than reconstructed, so it enters the count by a DEFAULT rather
    # than by a file on disk - and counting it for B1 would be the mirror image
    # of the fault above: recording an attempt B1 never made.
    from core.b0_l2_run_layout import (
        attempted_openings, lineage_opening_claims_root,
    )

    b1_root = lineage_opening_claims_root("B1")
    assert attempted_openings(b1_root, include_legacy=False) == []
    leaked = attempted_openings(b1_root, include_legacy=True)
    assert [c["run_id"] for c in leaked] == [LEGACY_ATTEMPTED_OPENING["run_id"]]


def test_the_legacy_run_identity_belongs_to_frozen_b0_alone():
    from core.b0_l2_run_layout import LEGACY_RUN_ID, LegacyRunProtected, run_dir

    assert run_dir(LEGACY_RUN_ID) == run_dir(LEGACY_RUN_ID, FROZEN_B0_LINEAGE)
    with pytest.raises(LegacyRunProtected):
        run_dir(LEGACY_RUN_ID, "B1")


def test_the_run_directory_guard_knows_about_every_lineage(tmp_path):
    """A guard that knows one run root stops being a guard when a second exists.

    `assert_not_creating_run_dir` compared against Frozen B0's runs root only,
    so a generic provenance writer pointed inside B1's run tree would have been
    waved through and created the directory the opener is the sole creator of.
    """
    from core import b0_l2_run_layout as layout

    for lineage in (FROZEN_B0_LINEAGE, "B1"):
        inside = os.path.join(layout.lineage_runs_root(lineage), "L2-nope")
        with pytest.raises(layout.PreOpeningOrphan):
            layout.assert_not_creating_run_dir(inside)
    layout.assert_not_creating_run_dir(str(tmp_path))      # outside: allowed


# --- opener / runner / period-1 builder --------------------------------------

def test_the_opener_binds_the_seal_archive_of_the_lineage_it_opens():
    b0 = _load_script(OPENER, "_open_probe_b0")
    b1 = _load_script(OPENER, "_open_probe_b1", "B1")
    assert _rel(b0.SEAL_ARCHIVE) == "artifacts/baseline_seal/seals"
    assert _rel(b1.SEAL_ARCHIVE) == "artifacts/baseline_seal_b1/seals"
    assert _rel(b0.FREEZE) == "research/b0_registry/master_prereg_freeze.json"
    assert _rel(b1.FREEZE) == "research/b0_registry/master_prereg_freeze_b1.json"
    assert _rel(b0.MANIFEST) == "data/b0/market_state_manifest.json"
    assert _rel(b1.MANIFEST) == "data/b1/market_state_manifest.json"
    assert _rel(b0.PERIOD1_RECEIPT) == \
        "research/b0_materializer/period1_full_input_receipt.json"
    assert _rel(b1.PERIOD1_RECEIPT) == \
        "research/b0_materializer/period1_full_input_receipt_b1.json"
    assert _rel(b0.REGISTRY) == "research/b0_registry/l2_opening_registry.jsonl"
    assert _rel(b1.REGISTRY) == \
        "research/b0_registry/l2_opening_registry_b1.jsonl"


def test_the_opener_still_asks_the_reopening_gate_itself():
    """Resolving the lineage dynamically makes this MORE load-bearing, not less.

    C-72's finding was that the guard living in `assert_reopening_admissible`
    was not enough, because this entry point never consulted it. That must not
    quietly regress into "the environment decides".
    """
    src = open(OPENER, encoding="utf-8").read()
    assert "assert_l2_reopening_reachable(LINEAGE)" in src
    b0 = _load_script(OPENER, "_open_probe_gate")
    assert b0.LINEAGE == FROZEN_B0_LINEAGE
    with pytest.raises(b0.L2ReopeningUnreachable):
        b0.assert_l2_reopening_reachable(FROZEN_B0_LINEAGE)


def test_the_runner_reads_the_panels_and_registry_of_its_own_lineage():
    b0 = _load_script(RUNNER, "_run_probe_b0")
    b1 = _load_script(RUNNER, "_run_probe_b1", "B1")
    assert _rel(b0.DATA) == "data/b0"
    assert _rel(b1.DATA) == "data/b1"
    assert _rel(b0.FREEZE) == "research/b0_registry/master_prereg_freeze.json"
    assert _rel(b1.FREEZE) == "research/b0_registry/master_prereg_freeze_b1.json"
    # A B1 terminal row appended to B0's opening registry would move B0's
    # once-only accounting, which is the one number C-72 closed.
    assert _rel(b0.REGISTRY) == "research/b0_registry/l2_opening_registry.jsonl"
    assert _rel(b1.REGISTRY) == \
        "research/b0_registry/l2_opening_registry_b1.jsonl"


def test_the_runner_takes_its_window_length_from_the_specification():
    """C-55: 141 was written as a literal in four places in the runner.

    That was correct for exactly as long as one lineage existed. A window length
    with two homes agrees right up until the day it does not.
    """
    b1 = _load_script(RUNNER, "_run_probe_periods", "B1")
    assert b1.PERIODS == lineage_spec("B1", "window_months")
    body = open(RUNNER, encoding="utf-8").read()
    code = [l for l in body.splitlines()
            if "141" in l and not l.lstrip().startswith("#")]
    assert code == [], "the window length is hard-coded again: %s" % code


def test_the_attestation_names_the_dataset_it_actually_read():
    """An attestation is a claim about which bytes were read.

    B1 attesting to `b0_market_side_state_20260819` would be a false one that
    hashes perfectly cleanly, which is this project's most expensive bug shape.
    """
    from core.b0_master_prereg import lineage_market_state_dataset_id

    assert lineage_market_state_dataset_id(FROZEN_B0_LINEAGE) == \
        "b0_market_side_state_20260819"
    assert lineage_market_state_dataset_id("B1") != \
        lineage_market_state_dataset_id(FROZEN_B0_LINEAGE)
    with pytest.raises(UnregisteredLineage):
        lineage_market_state_dataset_id("B2")


def test_the_period_1_builder_writes_its_receipt_under_its_own_lineage():
    """The opener pins this receipt as `period1_full_input_sha256`.

    A receipt written under the wrong name is not an untidy file: it is one
    lineage's period-1 decision input bound into another's opening claim, and
    nothing downstream would notice.
    """
    b0 = _load_script(PERIOD1, "_p1_probe_b0")
    b1 = _load_script(PERIOD1, "_p1_probe_b1", "B1")
    assert _rel(b0.RECEIPT) == \
        "research/b0_materializer/period1_full_input_receipt.json"
    assert _rel(b1.RECEIPT) == \
        "research/b0_materializer/period1_full_input_receipt_b1.json"
    assert _rel(b0.DATA) == "data/b0"
    assert _rel(b1.DATA) == "data/b1"


# --- the intent check --------------------------------------------------------

def test_a_stated_lineage_is_checked_never_used_to_set_the_lineage():
    """The failure that produced this was measured, not imagined.

    `B0_MATERIALIZE_LINEAGE=B1 python.exe build_period1_full_input.py` run from
    WSL builds Frozen B0: the variable does not reach a Windows interpreter
    unless WSLENV names it as well. Nothing was violated, so nothing fired -
    every REFUSING TO WRITE guard in this chain protects B0 from a B1 build, and
    this is the other direction.

    The flag must not become a second way to SET the lineage; two setters are
    how the readers came to disagree in the first place.
    """
    from core.b0_master_prereg import (
        LineageIntentMismatch, assert_declared_lineage,
    )

    assert assert_declared_lineage(None, "B1") == "B1"
    assert assert_declared_lineage("", "B1") == "B1"
    assert assert_declared_lineage(" B1 ", "B1") == "B1"
    with pytest.raises(LineageIntentMismatch) as exc:
        assert_declared_lineage("B1", FROZEN_B0_LINEAGE)
    assert "WSLENV" in str(exc.value)
    # and it does not quietly become the answer
    assert assert_declared_lineage(None, FROZEN_B0_LINEAGE) == FROZEN_B0_LINEAGE


def test_every_stage_of_the_chain_checks_the_stated_lineage():
    stages = (
        os.path.join(REPO, "research", "b0_materializer",
                     "build_market_side_state.py"),
        PERIOD1, FREEZER, SEALER, OPENER, RUNNER,
    )
    for path in stages:
        src = open(path, encoding="utf-8-sig").read()
        assert "assert_declared_lineage(" in src, \
            "%s cannot be told which lineage it was meant to build" % _rel(path)
