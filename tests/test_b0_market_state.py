"""O-E · trading-calendar and security-status source contracts.

The point of these tests is not that the sources parse. It is that a source
which cannot answer "what was known at t" is refused entry, and that the ways of
smuggling future knowledge in through the inputs are closed:

  * the full trading calendar is not reachable at all;
  * a current snapshot is NOT_PIT_SAFE and cannot be repaired into B0;
  * `unknown` is not silently promoted to `listed`;
  * O-E-1: a status filed after the close cannot explain that day's missing price.
"""

import os

import pytest

from core.b0_market_state import (
    NON_TRADING_STATUSES,
    NOT_PIT_SAFE,
    PIT_SAFE,
    SECURITY_STATUSES,
    STATUS_DELISTED,
    STATUS_LISTED,
    STATUS_SUSPENDED,
    STATUS_UNKNOWN,
    MarketStateError,
    NotPitSafeError,
    SecurityStatusTable,
    SourceContract,
    StatusRecord,
    TradingCalendar,
    assert_sources_registered,
    assert_unknown_is_not_normal,
    market_state_provenance,
)

SESSIONS = ("2019-04-25", "2019-04-26", "2019-04-29", "2019-04-30",
            "2019-05-01", "2019-05-02", "2019-05-03")


def _contract(**kw):
    base = dict(name="cal", kind="trading_calendar",
                importer_version="imp@1", content_sha256="c" * 64,
                schema_sha256="s" * 64, date_min="2004-01-02", date_max="2026-08-17",
                has_effective_dates=True, has_availability_semantics=True,
                is_current_snapshot=False)
    base.update(kw)
    return SourceContract(**base)


def _status_contract(**kw):
    return _contract(name="status", kind="security_status", **kw)


# --- source contract ----------------------------------------------------------

def test_a_current_snapshot_is_not_pit_safe():
    """The industry_map defect: today's state applied to history."""
    c = _contract(is_current_snapshot=True)
    assert c.pit_safety() == NOT_PIT_SAFE
    with pytest.raises(NotPitSafeError, match="industry_map"):
        c.assert_pit_safe()


def test_a_source_without_effective_dates_is_not_pit_safe():
    assert _contract(has_effective_dates=False).pit_safety() == NOT_PIT_SAFE


def test_a_status_source_without_availability_semantics_is_not_pit_safe():
    """O-E-1 is unanswerable without it, so the source cannot be admitted."""
    assert _status_contract(has_availability_semantics=False).pit_safety() == NOT_PIT_SAFE
    # a calendar does not need the same field
    assert _contract(has_availability_semantics=False).pit_safety() == PIT_SAFE


def test_an_unversioned_source_is_refused():
    """A runtime API returning an undated status is not an admissible source."""
    for field in ("importer_version", "content_sha256", "schema_sha256"):
        with pytest.raises(MarketStateError, match=field):
            _contract(**{field: ""})


def test_an_undefined_source_kind_aborts():
    with pytest.raises(MarketStateError, match="not defined"):
        _contract(kind="vibes")


def test_contract_converts_to_b21_dataset_provenance():
    p = _contract().to_dataset_provenance()
    p.validate()
    assert p.name == "cal" and p.importer_version == "imp@1"


def test_provenance_helper_refuses_a_non_pit_safe_source():
    with pytest.raises(NotPitSafeError):
        market_state_provenance(_contract(is_current_snapshot=True))


def test_required_source_kinds_must_be_registered():
    assert_sources_registered(["trading_calendar"], {"cal": _contract()})
    with pytest.raises(MarketStateError, match="security_status"):
        assert_sources_registered(["trading_calendar", "security_status"],
                                  {"cal": _contract()})


# --- calendar -----------------------------------------------------------------

def test_the_full_calendar_is_not_reachable():
    """Holidays are published in advance, which makes an unrestricted calendar
    the easiest way to smuggle look-ahead into a PIT computation."""
    cal = TradingCalendar(SESSIONS, _contract())
    assert not hasattr(cal, "sessions")
    assert not any(a in dir(cal) for a in ("all_sessions", "future_sessions"))


def test_sessions_through_truncates_at_as_of():
    cal = TradingCalendar(SESSIONS, _contract())
    got = cal.sessions_through("2019-04-30")
    assert got == ("2019-04-25", "2019-04-26", "2019-04-29", "2019-04-30")
    assert all(s <= "2019-04-30" for s in got)


def test_an_as_of_beyond_coverage_aborts():
    """Silently returning the whole calendar would assert sessions we never saw."""
    cal = TradingCalendar(SESSIONS, _contract())
    with pytest.raises(MarketStateError, match="beyond calendar coverage"):
        cal.sessions_through("2027-01-01")


def test_calendar_rejects_duplicates_and_emptiness():
    with pytest.raises(MarketStateError, match="duplicate"):
        TradingCalendar(SESSIONS + ("2019-05-03",), _contract())
    with pytest.raises(MarketStateError, match="empty"):
        TradingCalendar([], _contract())


def test_calendar_refuses_a_non_pit_safe_source():
    with pytest.raises(NotPitSafeError):
        TradingCalendar(SESSIONS, _contract(is_current_snapshot=True))


def test_calendar_refuses_the_wrong_source_kind():
    with pytest.raises(MarketStateError, match="not a trading_calendar"):
        TradingCalendar(SESSIONS, _status_contract())


def test_is_session_and_sessions_between_are_also_bounded():
    cal = TradingCalendar(SESSIONS, _contract())
    assert cal.is_session("2019-04-29", "2019-04-30")
    with pytest.raises(MarketStateError):
        cal.is_session("2019-05-03", "2027-01-01")
    assert cal.sessions_between("2019-04-26", "2019-04-30") == (
        "2019-04-29", "2019-04-30")


# --- status semantics ---------------------------------------------------------

def test_four_statuses_and_unknown_is_not_filed():
    assert set(SECURITY_STATUSES) == {
        STATUS_LISTED, STATUS_SUSPENDED, STATUS_DELISTED, STATUS_UNKNOWN}
    assert set(NON_TRADING_STATUSES) == {STATUS_SUSPENDED, STATUS_DELISTED}
    with pytest.raises(MarketStateError, match="ABSENCE of a record"):
        StatusRecord("1234", STATUS_UNKNOWN, "2019-04-26", "2019-04-26", "x", "s")


def test_available_from_has_no_default():
    """Defaulting it to effective_from would assert the thing O-E-1 must prove."""
    import inspect
    params = inspect.signature(StatusRecord).parameters
    assert params["available_from"].default is inspect.Parameter.empty


def test_an_undefined_status_aborts():
    with pytest.raises(MarketStateError, match="not defined"):
        StatusRecord("1234", "probably_fine", "2019-04-26", "2019-04-26", "x", "s")


def _table(*records):
    return SecurityStatusTable(records, _status_contract())


def _rec(**kw):
    base = dict(stock_id="1234", status=STATUS_SUSPENDED,
                effective_from="2019-04-26", available_from="2019-04-26",
                reason="減資", source="TEJ")
    base.update(kw)
    return StatusRecord(**base)


def test_O_E_1_a_status_filed_that_day_cannot_explain_that_day():
    """The whole invariant: `effective_from <= session` is not sufficient."""
    r = _rec(effective_from="2019-04-29", available_from="2019-04-29")
    assert not r.explains_session("2019-04-29")
    assert r.explains_session("2019-04-30")


def test_O_E_1_holds_through_the_table_lookup():
    t = _table(_rec(effective_from="2019-04-29", available_from="2019-04-29"))
    assert t.explaining_record("1234", "2019-04-29", "2019-05-01") is None
    assert t.explaining_record("1234", "2019-04-30", "2019-05-01") is not None


def test_a_late_filing_cannot_reach_back_to_an_earlier_session():
    """Effective early, filed late: the record binds from 04-26 but only became
    knowable on 05-02, so it accounts for nothing before that."""
    t = _table(_rec(effective_from="2019-04-26", available_from="2019-05-02"))
    assert t.explaining_record("1234", "2019-04-29", "2019-05-03") is None
    assert t.explaining_record("1234", "2019-05-03", "2019-05-03") is not None


def test_a_session_after_as_of_is_rejected():
    t = _table(_rec())
    with pytest.raises(MarketStateError, match="after as_of"):
        t.explaining_record("1234", "2019-05-03", "2019-05-01")


def test_a_resumption_cancels_an_earlier_suspension():
    t = _table(_rec(effective_from="2019-04-26", available_from="2019-04-26"),
               _rec(status=STATUS_LISTED, effective_from="2019-04-30",
                    available_from="2019-04-30", reason="resume"))
    assert t.explaining_record("1234", "2019-04-29", "2019-05-03") is not None
    assert t.explaining_record("1234", "2019-05-02", "2019-05-03") is None


def test_a_delisting_keeps_explaining():
    t = _table(_rec(status=STATUS_DELISTED, effective_from="2019-04-26",
                    available_from="2019-04-26", reason="合併下市"))
    r = t.explaining_record("1234", "2019-05-02", "2019-05-03")
    assert r is not None and r.status == STATUS_DELISTED


def test_unknown_is_not_promoted_to_normal():
    t = _table(_rec())
    assert_unknown_is_not_normal("1234", t, has_price_gap=True)      # known
    assert_unknown_is_not_normal("9999", t, has_price_gap=False)     # nothing to explain
    with pytest.raises(MarketStateError, match="not 'trading normally'"):
        assert_unknown_is_not_normal("9999", t, has_price_gap=True)


def test_status_table_refuses_a_non_pit_safe_source():
    with pytest.raises(NotPitSafeError):
        SecurityStatusTable([_rec()], _status_contract(is_current_snapshot=True))


# --- the built sources --------------------------------------------------------

def _built():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return (os.path.join(repo, "data", "b0", "trading_calendar.csv"),
            os.path.join(repo, "data", "b0", "security_status.csv"))


def test_the_built_sources_load_as_pit_safe():
    import csv

    cal_path, status_path = _built()
    if not (os.path.exists(cal_path) and os.path.exists(status_path)):
        pytest.skip("market-state sources not built in this checkout")

    with open(cal_path, encoding="utf-8") as fh:
        sessions = [r["session"] for r in csv.DictReader(fh)]
    cal = TradingCalendar(sessions, _contract(
        date_min=sessions[0], date_max=sessions[-1]))
    assert len(cal) > 5000
    assert cal.sessions_through("2019-05-01")[-1] <= "2019-05-01"

    with open(status_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    table = SecurityStatusTable(
        [StatusRecord(**{k: r[k] for k in
                         ("stock_id", "status", "effective_from",
                          "available_from", "reason", "source")}) for r in rows],
        _status_contract(date_min=min(r["effective_from"] for r in rows),
                         date_max=max(r["effective_from"] for r in rows)))
    assert table.securities > 500
    assert {r["status"] for r in rows} <= set(SECURITY_STATUSES)


def test_every_built_status_row_carries_an_availability_date():
    import csv

    _, status_path = _built()
    if not os.path.exists(status_path):
        pytest.skip("market-state sources not built in this checkout")
    with open(status_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(r["available_from"].strip() for r in rows)
