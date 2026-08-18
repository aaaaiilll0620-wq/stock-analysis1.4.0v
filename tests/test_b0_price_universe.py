"""D-1 · price-universe completeness verification.

The load-bearing test here is the NEGATIVE CONTROL (D1-5): it is not enough to
show that a clean corpus passes. The verifier has to be shown failing on the
actual contamination this project hit, or "it passes" means nothing.

The other tests exist to stop the verifier passing for the wrong reason: no
hard-coded security names, no magnitude threshold, no settable flag, and no
dependence on anything the strategy does.
"""

import csv
import os

import pytest

from core.b0_price_universe import (
    ACCEPTABLE_MISSING_FRACTION,
    AUDIT_REQUIRED_FIELDS,
    CONTAMINATED_CORPUS_SHA256,
    MINIMUM_DELISTINGS_PER_YEAR,
    REFERENCE_IS_AUDIT_ONLY,
    REFERENCE_IS_CURRENT_SNAPSHOT,
    PriceSourceContract,
    PriceUniverseError,
    assert_price_source_admissible,
    quarantine_source,
    quarantined_sources,
    verify_price_universe,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_CSV = os.path.join(REPO, "data", "b0", "price_universe_audit.csv")
CLUSTER_CSV = os.path.join(REPO, "data", "b0", "price_universe_clusters.csv")
CHURN_CSV = os.path.join(REPO, "data", "b0", "price_universe_churn.csv")
# The contaminated corpus, audited by the SAME code path and frozen as a fixture
# so the negative control survives the repaired data replacing the live files.
OLD_DIR = os.path.join(REPO, "tests", "fixtures", "d1_contaminated")


def _csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _row(year, *, exits_observed, exits_expected, unexplained=0, expected=1700,
         observed=1700, missing=0, later=0):
    return {"year": year, "expected_from_reference": expected,
            "observed_in_corpus": observed, "missing": missing,
            "missing_though_listed_after_year_end": later,
            "unexplained_missing_though_listed": unexplained,
            "exits_observed": exits_observed,
            "exits_expected_from_reference": exits_expected}


def _clean_audit():
    """Ordinary churn: exits every year, in the same order as the reference."""
    return [_row(str(y), exits_observed=e, exits_expected=x)
            for y, e, x in [(2019, 14, 15), (2020, 17, 18), (2021, 15, 15),
                            (2022, 16, 17), (2023, 9, 8), (2024, 11, 10)]]


# --- D1-5 · negative control on the real contamination -----------------------

def test_D1_5_the_real_contaminated_audit_fails():
    """The verifier must be shown catching the defect we actually hit."""
    old = os.path.join(OLD_DIR, "price_universe_audit.csv")
    if not os.path.exists(old):
        pytest.skip("contaminated fixture not built in this checkout")
    v = verify_price_universe(
        _csv(old), _csv(os.path.join(OLD_DIR, "price_universe_clusters.csv")))
    assert not v.admissible
    assert "C1" in v.detail and "C2" in v.detail
    c1 = v.diagnostics["C1_years_with_no_exits_despite_reference_delistings"]
    assert {d["year"] for d in c1} >= {"2019", "2020", "2021", "2022"}
    c2 = v.diagnostics["C2_unexplained_termination_clusters"]
    assert any(d["date"] == "2018-12-28" and d["unexplained"] >= 2 for d in c2)


def test_D1_5_the_contaminated_corpus_also_fails_the_source_only_backstop():
    """The backstop needs no reference at all and must fail on its own."""
    from core.b0_frozen_spec import verify_price_universe_churn
    old = os.path.join(OLD_DIR, "price_universe_churn.csv")
    if not os.path.exists(old):
        pytest.skip("contaminated fixture not built in this checkout")
    r = verify_price_universe_churn(_csv(old))
    assert not r.satisfied and "zero departures" in r.detail


def test_D1_9_the_repaired_source_passes_both_verifications():
    """The candidate 20260817 source, judged by the same functions."""
    from core.b0_frozen_spec import verify_price_universe_churn
    if not os.path.exists(AUDIT_CSV):
        pytest.skip("audit not built in this checkout")
    assert verify_price_universe(_csv(AUDIT_CSV), _csv(CLUSTER_CSV)).admissible
    assert verify_price_universe_churn(_csv(CHURN_CSV)).satisfied


def test_D1_9_the_2018_12_28_cluster_is_gone_from_the_repaired_source():
    """Regression evidence only — 'all 90 back' is NOT the pass condition."""
    if not os.path.exists(CLUSTER_CSV):
        pytest.skip("audit not built in this checkout")
    rows = _csv(CLUSTER_CSV)
    assert not [r for r in rows if r["date"] == "2018-12-28"]
    assert all(int(r["unexplained_terminations_on_date"]) == 0 for r in rows)


def test_D1_9_exits_returned_in_every_year_2019_to_2025():
    if not os.path.exists(AUDIT_CSV):
        pytest.skip("audit not built in this checkout")
    by_year = {r["year"]: r for r in _csv(AUDIT_CSV)}
    for y in ("2019", "2020", "2021", "2022", "2023", "2024", "2025"):
        assert int(by_year[y]["exits_observed"]) > 0, y


def test_D1_5_a_clean_audit_passes():
    v = verify_price_universe(_clean_audit())
    assert v.admissible, v.detail
    assert not v.diagnostics["C1_years_with_no_exits_despite_reference_delistings"]


def test_D1_5_the_two_verdicts_come_from_the_same_function():
    """No separate 'strict mode' that only the old data is run through."""
    assert verify_price_universe(_clean_audit()).admissible
    bad = _clean_audit() + [_row("2025", exits_observed=0, exits_expected=8)]
    assert not verify_price_universe(bad).admissible


# --- C1 · a year with no exits while the reference records delistings --------

def test_C1_fires_on_a_single_year_regardless_of_size():
    """One contradiction is enough; the gate is structural, not a magnitude."""
    v = verify_price_universe([_row("2019", exits_observed=0, exits_expected=1)])
    assert not v.admissible and "C1" in v.detail


def test_C1_does_not_fire_when_the_reference_also_records_no_delistings():
    v = verify_price_universe([_row("2019", exits_observed=0, exits_expected=0)])
    assert v.admissible


def test_C1_ignores_the_final_year_which_has_no_successor():
    """`exits_observed` is undefined for the last audited year, and an undefined
    count must not be read as zero."""
    rows = _clean_audit() + [_row("2026", exits_observed=None, exits_expected=7)]
    assert verify_price_universe(rows).admissible


# --- C2 · synchronised terminations -----------------------------------------

def test_C2_fires_on_a_cluster_of_unexplained_terminations():
    v = verify_price_universe(
        _clean_audit(),
        [{"date": "2018-12-28", "corpus_terminations": 90,
          "unexplained_terminations_on_date": 54}])
    assert not v.admissible and "C2" in v.detail


def test_C2_does_not_fire_when_the_terminations_are_accounted_for():
    """The delisting date is at or AFTER the last trading day — often the next
    day, and after a long suspension months later. Comparing the cluster date
    against delistings on that same date fired on clean data (2018-09-17: six
    securities, last session the 17th, `delisted` status the 18th, formal
    delisting 2018-10-01), which is why C2 asks whether it is explained."""
    v = verify_price_universe(
        _clean_audit(),
        [{"date": "2018-09-17", "corpus_terminations": 6,
          "unexplained_terminations_on_date": 0}])
    assert v.admissible


def test_C2_needs_an_actual_cluster_not_a_lone_termination():
    v = verify_price_universe(
        _clean_audit(),
        [{"date": "2020-06-30", "corpus_terminations": 1,
          "unexplained_terminations_on_date": 1}])
    assert v.admissible


# --- the verifier must not pass for the wrong reason --------------------------

def test_no_threshold_constants_exist():
    assert MINIMUM_DELISTINGS_PER_YEAR is None
    assert ACCEPTABLE_MISSING_FRACTION is None


def test_magnitude_is_reported_but_not_gated():
    """A magnitude gate would need a defensible number, and there isn't one."""
    rows = [dict(r) for r in _clean_audit()]
    rows[0]["unexplained_missing_though_listed"] = 77
    v = verify_price_universe(rows)
    assert v.admissible
    assert v.diagnostics["unexplained_missing_though_listed_by_year"]["2019"] == 77
    assert v.diagnostics["magnitude_is_reported_not_gated"] is True


def test_the_verdict_does_not_depend_on_any_security_name():
    """The observed-missing list was read off the broken corpus. A verifier that
    looked for those names would pass any corpus containing them."""
    import inspect

    import core.b0_price_universe as mod
    src = inspect.getsource(mod)
    # the audit schema carries counts only — no identifier column at all
    assert not any("stock" in c or "symbol" in c for c in AUDIT_REQUIRED_FIELDS)
    for name in ("1258", "1701", "2358", "1333"):
        assert name not in src


def test_there_is_no_settable_satisfied_flag():
    import inspect

    from core.b0_price_universe import UniverseVerdict
    params = inspect.signature(verify_price_universe).parameters
    assert set(params) == {"audit_rows", "cluster_rows"}
    assert "admissible" in UniverseVerdict.__dataclass_fields__
    # ... and it is computed, never passed in
    assert "admissible" not in params


def test_the_verifier_takes_no_holdings_or_performance_input():
    """Admissibility of the data cannot depend on what the strategy does with it."""
    import inspect
    src = inspect.getsource(verify_price_universe).lower()
    for banned in ("holding", "portfolio", "selectionscore", "sharpe",
                   "cagr", "nav", "pnl", "weight"):
        assert banned not in src, banned
    assert set(inspect.signature(verify_price_universe).parameters) == {
        "audit_rows", "cluster_rows"}


def test_a_malformed_count_aborts_rather_than_being_skipped():
    with pytest.raises(PriceUniverseError, match="not a count"):
        verify_price_universe([_row("2019", exits_observed="lots", exits_expected=3)])


def test_missing_columns_are_reported():
    v = verify_price_universe([{"year": "2019"}])
    assert not v.admissible and "missing columns" in v.detail


def test_an_absent_audit_is_not_a_pass():
    assert not verify_price_universe([]).admissible


# --- the reference is audit-only ---------------------------------------------

def test_the_reference_may_not_become_a_runtime_source():
    """公司資料 is a current snapshot whose 上市別 is rewritten on delisting."""
    assert REFERENCE_IS_AUDIT_ONLY is True
    assert REFERENCE_IS_CURRENT_SNAPSHOT is True


def test_the_reference_would_be_refused_by_O_E():
    from core.b0_market_state import NOT_PIT_SAFE, SourceContract
    c = SourceContract(
        name="company_master", kind="security_status", importer_version="i@1",
        content_sha256="c" * 64, schema_sha256="s" * 64,
        date_min="1962-02-09", date_max="2026-08-06",
        has_effective_dates=True, has_availability_semantics=False,
        is_current_snapshot=True)
    assert c.pit_safety() == NOT_PIT_SAFE


# --- D1-6 · source admissibility ---------------------------------------------

def _contract(**kw):
    base = dict(name="b0_price", importer_version="imp@1",
                content_sha256="f" * 64, schema_sha256="s" * 64,
                date_min="2004-01-02", date_max="2026-07-14",
                securities=2400, includes_delisted=True, audit_sha256="a" * 64)
    base.update(kw)
    return PriceSourceContract(**base)


def test_the_contaminated_corpus_is_quarantined_by_content_hash():
    assert CONTAMINATED_CORPUS_SHA256 in quarantined_sources()
    with pytest.raises(PriceUniverseError, match="quarantined"):
        assert_price_source_admissible(_contract(content_sha256=CONTAMINATED_CORPUS_SHA256))


def test_renaming_a_quarantined_source_does_not_launder_it():
    with pytest.raises(PriceUniverseError, match="quarantined"):
        assert_price_source_admissible(
            _contract(name="totally_new_price_source",
                      content_sha256=CONTAMINATED_CORPUS_SHA256))


def test_a_survivor_only_source_is_refused_even_if_not_yet_quarantined():
    with pytest.raises(PriceUniverseError, match="includes_delisted"):
        assert_price_source_admissible(_contract(includes_delisted=False))


def test_a_complete_source_is_admissible():
    assert_price_source_admissible(_contract())


def test_quarantine_entries_require_a_reason():
    with pytest.raises(PriceUniverseError):
        quarantine_source("d" * 64, "  ")


# --- D1-7 · provenance --------------------------------------------------------

def test_contract_requires_every_identity_field():
    for f in ("importer_version", "content_sha256", "schema_sha256",
              "date_min", "date_max", "audit_sha256"):
        with pytest.raises(PriceUniverseError, match=f):
            _contract(**{f: ""})


def test_contract_converts_to_b21_dataset_provenance():
    p = _contract().to_dataset_provenance()
    p.validate()
    assert p.name == "b0_price" and p.importer_version == "imp@1"


def test_a_hash_in_a_document_is_not_provenance():
    """The contract exists so the route can check it, not so a closure can
    quote it."""
    with pytest.raises(PriceUniverseError, match="closure document"):
        _contract(audit_sha256="")


# --- D1-6 · the route actually consults the gate ------------------------------

def _sources(**kw):
    from core.b0_adapter_retrospective import RetrospectiveSources
    from core.b0_market_state import SourceContract, TradingCalendar
    from core.b0_state import SourceAttestation

    cal = TradingCalendar(
        ("2020-06-29", "2020-06-30"),
        SourceContract(name="cal", kind="trading_calendar", importer_version="i@1",
                       content_sha256="c" * 64, schema_sha256="s" * 64,
                       date_min="2020-06-29", date_max="2020-06-30",
                       has_effective_dates=True, has_availability_semantics=True,
                       is_current_snapshot=False))
    base = dict(
        calendar=cal, status_table=None,
        attestation=SourceAttestation(
            dataset_id="price", provenance_sha256="p" * 64,
            pit_guard_passed=True, universe_guard_passed=True,
            satisfied_blocking_requirements=("price_universe_survivorship",),
            synthetic=False),
        marks={}, adv20={}, sigma20d={}, pit_inputs=(), price_observations=())
    base.update(kw)
    return RetrospectiveSources(**base)


def _replay(sources):
    from core.b0_adapter_retrospective import _assert_replayable
    _assert_replayable(sources)


def test_a_real_replay_must_name_its_price_corpus():
    from core.b0_adapter_retrospective import RetrospectiveAdapterError
    with pytest.raises(RetrospectiveAdapterError, match="D1-6"):
        _replay(_sources(price_source=None))


def test_a_real_replay_refuses_the_quarantined_corpus():
    with pytest.raises(PriceUniverseError, match="quarantined"):
        _replay(_sources(price_source=_contract(
            content_sha256=CONTAMINATED_CORPUS_SHA256)))


def test_a_real_replay_refuses_a_survivor_only_corpus():
    with pytest.raises(PriceUniverseError, match="includes_delisted"):
        _replay(_sources(price_source=_contract(includes_delisted=False)))


def test_a_real_replay_accepts_an_admissible_corpus():
    _replay(_sources(price_source=_contract()))


def test_a_synthetic_fixture_need_not_name_a_corpus():
    """Fixtures are how the guards themselves are tested; requiring a real
    corpus there would make the guard untestable."""
    from core.b0_state import SourceAttestation
    _replay(_sources(price_source=None, attestation=SourceAttestation(
        dataset_id="fixture", provenance_sha256="p" * 64,
        pit_guard_passed=True, universe_guard_passed=True,
        satisfied_blocking_requirements=(), synthetic=True)))


def test_the_gate_is_route_reachable():
    from core.b0_invariants import B0_ENTRY_MODULES
    assert "core.b0_price_universe" in B0_ENTRY_MODULES


def test_B19_still_forbids_the_runtime_overlay_that_could_reinstate_it():
    """The overlay env var is the other way a contaminated corpus comes back."""
    from core.b0_invariants import B0_REGISTERED_OVERRIDES, OVERRIDE_SYMBOLS
    assert "TEJ_RUNTIME_OVERLAY_DIR" in OVERRIDE_SYMBOLS
    assert B0_REGISTERED_OVERRIDES == {}


# --- integration: the blocking requirement uses this verifier -----------------

def test_D1_is_satisfied_by_the_repaired_source():
    from core.b0_frozen_spec import BLOCKING_DATA_REQUIREMENTS

    if not os.path.exists(AUDIT_CSV):
        pytest.skip("audit not built in this checkout")
    req = {r.key: r for r in BLOCKING_DATA_REQUIREMENTS}["price_universe_survivorship"]
    res = req.verify()
    assert res.satisfied, res.detail
    assert res.diagnostics["source_only_backstop"]["satisfied"] is True


def test_the_year_end_vanisher_signal_is_reported_not_gated():
    """All 16 occurrences in the repaired corpus have a reference delisting on or
    within days of the next session, and at least one occurs every year — gating
    on `> 0` would block every real corpus rather than detect anything."""
    from core.b0_frozen_spec import verify_price_universe_churn
    rows = [{"year": "2019", "securities": 1800, "dropped_next_year": 12,
             "dropped_but_traded_to_year_end": 1}]
    r = verify_price_universe_churn(rows)
    assert r.satisfied
    assert r.diagnostics["vanished_at_year_end_is_reported_not_gated"] is True
    assert r.diagnostics["vanished_after_trading_to_year_end"] == {"2019": 1}
