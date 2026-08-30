# -*- coding: utf-8 -*-
"""B7 · the portfolio half of an L3 prospective decision.

`portfolio_checkpoint.py` could serialise a `PortfolioState` and had no caller.
`research/b0_l3/` could build everything about a period except the portfolio.
These tests are about the join between them, and specifically about the four
ways the join can be wrong while still looking right:

  * the opening state is verified on a hash that is BLIND to the spell ledger
    (`ca._state_hash`), so a hand-off silently loses B0.1's exposure ledger;
  * exposure is declared from the LISTING spell instead of the portfolio's own
    holding spell -- the defect that ended the official Frozen B0 L2 run in
    period 2;
  * a corporate-action term of exactly `0.0` is dropped, because L2's CSV-string
    truthiness test was transcribed onto typed values;
  * the market half and the portfolio half quietly restate each other.
"""
from __future__ import annotations

import json
import os
import sys
from fractions import Fraction

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import b0_corporate_actions as ca                        # noqa: E402
from core.b0_corporate_actions import (                            # noqa: E402
    NOT_RECONSTRUCTIBLE, RECONSTRUCTIBLE, CorporateActionEvent, Exposure,
)
from core.b0_state import (                                        # noqa: E402
    CashReceivable, HoldingSpell, PortfolioState, SecurityReceivable,
)
from research.b0_checkpoint import portfolio_side as ps            # noqa: E402
from research.b0_checkpoint.portfolio_checkpoint import (          # noqa: E402
    checkpoint_hash, checkpoint_record,
)


SESSIONS = tuple(
    "2026-03-%02d" % d for d in range(2, 32) if d not in (7, 8, 14, 15, 21, 22,
                                                          28, 29))
AS_OF = SESSIONS[-1]


def _state(as_of=AS_OF, **over) -> PortfolioState:
    kw = dict(
        as_of=as_of, cash=1_000_000.0,
        shares={"2330": 1000, "1101": 500},
        pending_exit={"1101": 500},
        cash_dividend_receivable=1200.0,
        stock_dividend_receivable={"2330": 42},
        security_receivables=(
            SecurityReceivable(
                security_id="9999", shares=Fraction(3, 7),
                credit_tradable_date="2026-04-10",
                event_id="8913|share_conversion|2026-03-02",
                source_security_id="8913",
                origin_effective_date="2026-03-02"),),
        cash_receivables=(
            CashReceivable(amount=50.0, cash_available_date="2026-04-10",
                           event_id="8913|cash|2026-03-02",
                           source_security_id="8913"),),
        applied_ca_event_ids=frozenset({"8913|share_conversion|2026-03-02"}),
        pending_exit_on_receivable=frozenset({"9999"}),
        holding_spells=(
            HoldingSpell("2330", "2025-01-02", ""),
            HoldingSpell("1101", "2025-06-02", ""),
        ))
    kw.update(over)
    return PortfolioState(**kw)


def _row(sid, **over):
    row = {
        "stock_id": sid, "mark": 100.0, "adv20": 5e8, "sigma20d": 0.02,
        "execution_open": 101.0, "spell_start": "2024-01-02",
        "known_status": "listed", "status_available_from": None,
        "status_effective_from": None,
    }
    row.update(over)
    return row


def _assembled(rows, as_of=AS_OF, decision_date="2026-03-31"):
    return {
        "period": {"decision_date": decision_date, "decision_month":
                   decision_date[:7], "as_of": as_of,
                   "execution_date": "2026-04-01"},
        "rows": rows,
    }


def _checkpoint_file(tmp_path, state, *, run_id="L3-0000000000000001",
                     period="2026-03", seq=1):
    path = tmp_path / "portfolio_checkpoint.jsonl"
    rec = checkpoint_record(run_id=run_id, seq=seq, period=period, state=state)
    path.write_bytes(
        (json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n").encode())
    return str(path), rec


def _continuation(path, rec, **over):
    """Every lineage argument a CONTINUATION must name, correct by default."""
    from core.b0_canonical_hash import file_sha256

    kw = dict(kind=ps.OPENING_CONTINUATION,
              producer_run_id=rec["run_id"],
              expect_period=rec["period"],
              expect_seq=int(rec["seq"]),
              expect_checkpoint_sha256=rec["checkpoint_sha256"],
              expect_handoff_sha256=ps.handoff_hash(rec),
              expect_file_sha256=file_sha256(path))
    kw.update(over)
    return kw


GENESIS_C_REF = 2_000_000.0


def _genesis_state(as_of="2026-02-26", **over):
    kw = dict(as_of=as_of, cash=GENESIS_C_REF, shares={})
    kw.update(over)
    return PortfolioState(**kw)


# --- the opening state ----------------------------------------------------------

def test_opening_state_round_trips_on_the_full_hash_not_the_ca_hash(tmp_path):
    """The hand-off is verified on the identity that covers `holding_spells`."""
    state = _state()
    path, rec = _checkpoint_file(tmp_path, state)

    opened, prov = ps.opening_state(path, **_continuation(path, rec))

    assert checkpoint_hash(opened) == checkpoint_hash(state)
    assert prov["checkpoint_sha256"] == rec["checkpoint_sha256"]
    assert prov["ca_state_hash"] == ca._state_hash(state)
    assert prov["opening_source"] == "portfolio_checkpoint"
    # The ledger survives in full. Its ORDER is canonicalised by the serializer
    # (`sorted` by stock_id/start/end) rather than preserved, which is what makes
    # two byte-equal states serialise byte-equally -- so the comparison here is
    # by content and the hash above is what proves nothing moved.
    assert set(opened.holding_spells) == set(state.holding_spells)
    assert len(opened.holding_spells) == len(state.holding_spells)


def test_the_ca_hash_alone_could_not_have_caught_a_lost_spell_ledger(tmp_path):
    """Why the verification is `checkpoint_hash` and not `ca._state_hash`.

    This is the whole reason `portfolio_checkpoint` exists as a separate
    identity. If it ever stops being true, the hand-off has silently become
    verifiable by a hash that does not see B0.1's exposure ledger.
    """
    state = _state()
    stripped = PortfolioState(**{
        **{f: getattr(state, f) for f in
           ("as_of", "cash", "shares", "pending_exit",
            "cash_dividend_receivable", "stock_dividend_receivable",
            "security_receivables", "cash_receivables", "applied_ca_event_ids",
            "pending_exit_on_receivable")},
        "holding_spells": ()})

    assert ca._state_hash(stripped) == ca._state_hash(state)      # blind
    assert checkpoint_hash(stripped) != checkpoint_hash(state)    # not blind


def test_opening_state_refuses_a_terminal_the_caller_did_not_authorise(tmp_path):
    state = _state()
    path, rec = _checkpoint_file(tmp_path, state, period="2026-03", seq=1)

    with pytest.raises(Exception):
        ps.opening_state(path, **_continuation(path, rec,
                                               expect_period="2026-02"))
    with pytest.raises(Exception):
        ps.opening_state(path, **_continuation(path, rec, expect_seq=2))
    with pytest.raises(ps.PortfolioSideError):
        ps.opening_state(path, **_continuation(
            path, rec, expect_checkpoint_sha256="00" * 32))
    # and the authorised one still opens
    ps.opening_state(path, **_continuation(path, rec))


def test_there_is_no_opening_state_without_a_checkpoint(tmp_path):
    """No default, no zero-cash fallback, no 'start flat'."""
    with pytest.raises(Exception):
        ps.opening_state(str(tmp_path / "does_not_exist.jsonl"),
                         kind=ps.OPENING_GENESIS, c_ref=GENESIS_C_REF)


def test_the_opening_kind_is_declared_never_inferred(tmp_path):
    """A file cannot say whether it opens a lineage or continues one."""
    path, rec = _checkpoint_file(tmp_path, _state())

    with pytest.raises(TypeError):
        ps.opening_state(path)                       # kind is keyword-REQUIRED
    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, kind="MAYBE")
    assert "never an inference" in str(exc.value)


# --- CONTINUATION: the lineage must be mechanically provable ----------------------

@pytest.mark.parametrize("absent", [
    "producer_run_id", "expect_period", "expect_seq",
    "expect_checkpoint_sha256", "expect_handoff_sha256", "expect_file_sha256"])
def test_a_continuation_must_name_its_whole_lineage(tmp_path, absent):
    """Every one of these used to default to skipped, so any file opened any period."""
    path, rec = _checkpoint_file(tmp_path, _state())
    blank = 0 if absent == "expect_seq" else ""

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, **_continuation(path, rec, **{absent: blank}))
    assert absent in str(exc.value)
    assert "mechanically provable" in str(exc.value)


def test_a_continuation_refuses_a_state_lifted_from_another_run(tmp_path):
    path, rec = _checkpoint_file(tmp_path, _state(), run_id="L3-SOMEONE-ELSE")

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, **_continuation(path, rec,
                                               producer_run_id="L3-MINE"))
    assert "written by run" in str(exc.value)


def test_the_handoff_hash_sees_what_the_checkpoint_hash_is_blind_to(tmp_path):
    """Same state, different run: `checkpoint_sha256` cannot tell them apart.

    That is correct for a STATE identity and fatal for a HAND-OFF identity, so
    the two are separate hashes and the continuation contract binds both.
    """
    state = _state()
    mine = checkpoint_record(run_id="L3-MINE", seq=1, period="2026-03",
                             state=state)
    theirs = checkpoint_record(run_id="L3-THEIRS", seq=9, period="2019-07",
                               state=state)

    assert mine["checkpoint_sha256"] == theirs["checkpoint_sha256"]   # blind
    assert ps.handoff_hash(mine) != ps.handoff_hash(theirs)           # not blind


def test_a_continuation_refuses_a_handoff_hash_that_does_not_match(tmp_path):
    path, rec = _checkpoint_file(tmp_path, _state())

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, **_continuation(
            path, rec, expect_handoff_sha256="11" * 32))
    assert "run_id / period / seq" in str(exc.value)


def test_a_continuation_refuses_a_file_whose_earlier_rows_were_rewritten(
        tmp_path):
    """The terminal row can be identical while the history behind it is not."""
    state = _state()
    path, rec = _checkpoint_file(tmp_path, state)
    stale_file_hash = _continuation(path, rec)["expect_file_sha256"]

    # prepend an earlier period: same terminal row, different file
    earlier = checkpoint_record(run_id=rec["run_id"], seq=0, period="2026-02",
                                state=_state(as_of="2026-02-26"))
    rewritten = checkpoint_record(run_id=rec["run_id"], seq=1,
                                  period="2026-03", state=state)
    with open(path, "wb") as fh:
        for row in (earlier, rewritten):
            fh.write((json.dumps(row, ensure_ascii=False, sort_keys=True)
                      + "\n").encode())

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, **_continuation(
            path, rec, expect_file_sha256=stale_file_hash))
    assert "earlier row was rewritten" in str(exc.value)


# --- GENESIS: A1's independent cohort ---------------------------------------------

def test_a_genesis_opening_is_a1s_registered_cohort(tmp_path):
    path, rec = _checkpoint_file(tmp_path, _genesis_state(), run_id="L3-GEN",
                                 period="2026-02", seq=1)

    opened, prov = ps.opening_state(path, kind=ps.OPENING_GENESIS,
                                    c_ref=GENESIS_C_REF)

    assert opened.cash == GENESIS_C_REF
    assert prov["opening_kind"] == ps.OPENING_GENESIS
    assert prov["genesis_cohort"]["c_ref"] == GENESIS_C_REF
    assert prov["positions"] == 0


def test_a_genesis_opening_must_name_c_ref(tmp_path):
    path, _ = _checkpoint_file(tmp_path, _genesis_state())

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, kind=ps.OPENING_GENESIS)
    assert "c_ref" in str(exc.value)


@pytest.mark.parametrize("over,why", [
    ({"cash": 1_999_999.0}, "cash"),
    ({"shares": {"2330": 1}}, "shares"),
    ({"cash_dividend_receivable": 1.0}, "cash_dividend_receivable"),
    ({"stock_dividend_receivable": {"2330": 5}}, "stock_dividend_receivable"),
])
def test_a_genesis_opening_refuses_anything_that_is_not_the_cohort(
        tmp_path, over, why):
    path, _ = _checkpoint_file(tmp_path, _genesis_state(**over))

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, kind=ps.OPENING_GENESIS, c_ref=GENESIS_C_REF)
    assert why in str(exc.value)


def test_a_genesis_opening_refuses_a_claim_or_a_spell(tmp_path):
    """A cohort that has held nothing cannot have a claim or an exposure spell."""
    path, _ = _checkpoint_file(tmp_path, _genesis_state(
        holding_spells=(HoldingSpell("2330", "2025-01-02", "2025-06-30"),)))

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(path, kind=ps.OPENING_GENESIS, c_ref=GENESIS_C_REF)
    assert "holding_spells" in str(exc.value)


def test_a_lineage_with_history_is_not_opening(tmp_path):
    run_dir = str(tmp_path)
    ps.append_checkpoint(run_dir, run_id="L3-GEN", period="2026-01",
                         state=_genesis_state(as_of="2026-01-30"))
    ps.append_checkpoint(run_dir, run_id="L3-GEN", period="2026-02",
                         state=_genesis_state())

    with pytest.raises(ps.PortfolioSideError) as exc:
        ps.opening_state(ps.checkpoint_file(run_dir),
                         kind=ps.OPENING_GENESIS, c_ref=GENESIS_C_REF)
    assert "already has history" in str(exc.value)


def test_the_genesis_cohort_shape_comes_from_the_normative_producer():
    """Not from equality checks written in the portfolio side."""
    from core.b0_opening_state import registered_opening_state

    registered = registered_opening_state("2026-02-26", GENESIS_C_REF)
    state = _genesis_state()

    for field, want in registered.items():
        if field == "as_of":
            continue
        got = getattr(state, field)
        assert (dict(got) if hasattr(got, "items") else got) == want
    ps.assert_genesis_cohort(state, c_ref=GENESIS_C_REF)


# --- price observations and exposure --------------------------------------------

def test_price_observations_are_built_for_held_securities_only():
    state = _state()
    rows = [_row("2330"), _row("1101"), _row("2454")]     # 2454 is not held
    side = ps.build_portfolio_side(_assembled(rows), state, sessions=SESSIONS,
                                   events_by_sid={})

    observed = sorted(o.stock_id for o in side.price_observations)
    assert observed == sorted(state.held_securities)
    assert "2454" not in observed


def test_expected_sessions_stop_at_as_of_and_start_at_the_spell():
    state = _state()
    rows = [_row("2330", spell_start=SESSIONS[3]), _row("1101"),
            _row("9999")]
    side = ps.build_portfolio_side(_assembled(rows), state, sessions=SESSIONS,
                                   events_by_sid={})
    by_sid = {o.stock_id: o for o in side.price_observations}

    assert by_sid["2330"].expected_sessions == tuple(SESSIONS[3:])
    assert max(by_sid["2330"].expected_sessions) == AS_OF
    assert by_sid["2330"].price_observed_through == AS_OF


def test_a_held_security_with_no_market_row_is_reported_not_absorbed():
    """The shape B0.6 and B0.7 both ended on has to be visible in provenance."""
    state = _state()
    rows = [_row("2330"), _row("1101")]      # 9999 is a claim with no market row
    side = ps.build_portfolio_side(_assembled(rows), state, sessions=SESSIONS,
                                   events_by_sid={})

    assert "9999" in side.held_without_market_row
    orphan = {o.stock_id: o for o in side.price_observations}["9999"]
    assert orphan.price_observed_through is None
    assert orphan.known_status == "listed"


def test_exposure_comes_from_the_portfolios_own_spell_ledger():
    """B0.1/R2: never the listing spell. The market row's spell_start differs."""
    state = _state()
    rows = [_row("2330", spell_start="2010-01-04"), _row("1101")]
    side = ps.build_portfolio_side(_assembled(rows), state, sessions=SESSIONS,
                                   events_by_sid={})

    held_from = {e.stock_id: e.held_from for e in side.exposures}
    assert held_from["2330"] == "2025-01-02"          # the HOLDING spell
    assert held_from["2330"] != "2010-01-04"          # not the listing spell


def test_only_active_spells_are_declared_after_an_exit_and_a_re_entry():
    """B0.2/R2: the closed spell stays in the ledger and out of the declaration."""
    state = _state(holding_spells=(
        HoldingSpell("2330", "2020-01-02", "2021-06-30"),      # closed
        HoldingSpell("2330", "2025-01-02", ""),                # current
        HoldingSpell("1101", "2025-06-02", ""),
    ))
    side = ps.build_portfolio_side(_assembled([_row("2330"), _row("1101")]),
                                   state, sessions=SESSIONS, events_by_sid={})

    spells_2330 = sorted(e.held_from for e in side.exposures
                         if e.stock_id == "2330")
    assert spells_2330 == ["2025-01-02"]
    # and the ledger itself is untouched -- the closed spell is still there
    assert len(state.holding_spells) == 3


def test_the_two_halves_must_stand_on_the_same_day():
    with pytest.raises(ps.PortfolioSideError):
        ps.build_portfolio_side(_assembled([_row("2330")], as_of="2026-02-27"),
                                _state(), sessions=SESSIONS, events_by_sid={})


# --- the ProductionSources join ---------------------------------------------------

class _FakeSources:
    """Only the fields `complete_sources` touches; `replace` needs a dataclass."""


def _market_sources():
    from core.b0_adapter_production import ProductionSources
    from core.b0_market_state import SourceContract, TradingCalendar

    calendar = TradingCalendar(
        sessions=SESSIONS,
        source=SourceContract(
            name="t", kind="trading_calendar", importer_version="t@1",
            content_sha256="a" * 64, schema_sha256="b" * 64,
            date_min=SESSIONS[0], date_max=SESSIONS[-1],
            has_effective_dates=True, has_availability_semantics=True,
            is_current_snapshot=False, availability_convention="session_close"))
    from core.b0_state import SourceAttestation

    return ProductionSources(
        calendar=calendar, status_table=None,
        attestation=SourceAttestation(
            dataset_id="t", provenance_sha256="c" * 64, pit_guard_passed=True,
            universe_guard_passed=True,
            satisfied_blocking_requirements=("price_universe_survivorship",),
            synthetic=True),
        marks={"2330": 100.0}, adv20={"2330": 1.0}, sigma20d={"2330": 0.1},
        pit_inputs=(), price_observations=(), corporate_action_events=(),
        exposures=(), listing_spells=())


def test_complete_sources_fills_exactly_three_fields_and_restates_nothing():
    side = ps.build_portfolio_side(_assembled([_row("2330"), _row("1101")]),
                                   _state(), sessions=SESSIONS, events_by_sid={})
    market = _market_sources()
    joined = ps.complete_sources(market, side)

    assert joined.price_observations == side.price_observations
    assert joined.corporate_action_events == side.corporate_action_events
    assert joined.exposures == side.exposures
    # every market-side field is the SAME object, not a rebuilt one
    for field in ("calendar", "status_table", "attestation", "marks", "adv20",
                  "sigma20d", "pit_inputs", "listing_spells"):
        assert getattr(joined, field) is getattr(market, field)


def test_complete_sources_refuses_a_market_side_that_already_filled_them():
    """Definition A, enforced rather than trusted."""
    import dataclasses

    side = ps.build_portfolio_side(_assembled([_row("2330"), _row("1101")]),
                                   _state(), sessions=SESSIONS, events_by_sid={})
    market = _market_sources()

    with pytest.raises(ps.PortfolioSideError):
        ps.complete_sources(
            dataclasses.replace(market, price_observations=(object(),)), side)
    with pytest.raises(ps.PortfolioSideError):
        ps.complete_sources(
            dataclasses.replace(market, exposures=(
                Exposure(stock_id="2330", held_from="2025-01-02",
                         held_until=AS_OF),)), side)


def test_the_portfolio_side_payload_carries_no_market_field():
    side = ps.build_portfolio_side(_assembled([_row("2330"), _row("1101")]),
                                   _state(), sessions=SESSIONS, events_by_sid={})
    payload = ps.portfolio_side_payload(side)

    for field in ps.MARKET_FIELDS:
        assert field not in payload
    with pytest.raises(ps.PortfolioSideError):
        ps.assert_portfolio_side_is_market_free({**payload, "marks": {}})


# --- the CSV-truthiness hazard ----------------------------------------------------

def test_a_zero_valued_ledger_term_is_not_dropped(monkeypatch):
    """Hazard 1: L2 reads strings, the L3 reader returns typed values.

    `if row.get("cash_per_share"):` is false for `0.0` and true for the string
    `"0.0"`. Transcribing the expression rather than the intent would silently
    turn a zero-cash event into an event with no cash term at all.
    """
    import types

    ledger = [{
        "stock_id": "1101", "kind": "capital_reduction",
        "source_field": "x", "ex_or_effective_date": "2026-03-10",
        "reconstructibility": RECONSTRUCTIBLE, "reason": "",
        "credit_tradable_date": "2026-03-20", "new_shares_thousands": None,
        "share_multiplier": 0.8, "cash_per_share": 0.0,
        "cash_payment_date": "2026-03-25", "zero_day_receivable": False,
    }]

    class _Panel:
        def itertuples(self):
            return iter(())

    fake = types.ModuleType("l3_readers")
    fake.read_corporate_actions = lambda *a, **k: ledger
    fake.read_calendar = lambda *a, **k: SESSIONS
    fake.read_bonus_shares = lambda *a, **k: _Panel()
    monkeypatch.setitem(sys.modules, "l3_readers", fake)

    events = ps.load_events("unused", bonus_window=("2025-02-28", AS_OF),
                            ledger=ledger, sessions=SESSIONS)

    ev = events["1101"][0]
    assert ev.cash_per_share == 0.0
    assert ev.share_multiplier == 0.8


def test_a_stock_dividend_without_an_official_ratio_is_not_reconstructible(
        monkeypatch):
    """C-51: the ratio comes from the official panel, never from a share count."""
    import types

    ledger = [{
        "stock_id": "2330", "kind": "stock_dividend", "source_field": "x",
        "ex_or_effective_date": "2026-03-10",
        "reconstructibility": RECONSTRUCTIBLE, "reason": "",
        "credit_tradable_date": "2026-03-20",
        "new_shares_thousands": 1000.0, "share_multiplier": None,
        "cash_per_share": None, "cash_payment_date": None,
        "zero_day_receivable": False,
    }]

    class _Panel:
        def itertuples(self):
            return iter(())

    fake = types.ModuleType("l3_readers")
    fake.read_corporate_actions = lambda *a, **k: ledger
    fake.read_calendar = lambda *a, **k: SESSIONS
    fake.read_bonus_shares = lambda *a, **k: _Panel()
    monkeypatch.setitem(sys.modules, "l3_readers", fake)

    ev = ps.load_events("unused", bonus_window=("2025-02-28", AS_OF),
                        ledger=ledger, sessions=SESSIONS)["2330"][0]

    assert ev.reconstructibility == NOT_RECONSTRUCTIBLE
    assert "C-51" in ev.reason
    assert ev.stock_ratio is None      # a count was NOT converted into a ratio


def test_load_events_refuses_to_choose_a_bonus_window():
    with pytest.raises(ps.PortfolioSideError):
        ps.load_events("unused", bonus_window=None, ledger=[],
                       sessions=SESSIONS)


# --- portfolio[t+1] and the checkpoint --------------------------------------------

class _Session:
    def __init__(self, cash, shares, pending):
        self.cash_after = cash
        self.shares_after = shares
        self.pending_exit_after = pending


class _Result:
    def __init__(self, session):
        self.session = session


def test_advance_takes_cash_from_execution_and_claims_from_the_transition():
    transitioned = _state()
    result = _Result(_Session(777.0, {"2330": 1200}, {}))

    nxt = ps.advance(decision_result=result, transitioned=transitioned,
                     as_of=AS_OF, execution_date="2026-04-01")

    assert nxt.cash == 777.0                       # execution
    assert dict(nxt.shares) == {"2330": 1200}      # execution
    assert nxt.security_receivables == transitioned.security_receivables
    assert nxt.cash_receivables == transitioned.cash_receivables
    assert nxt.applied_ca_event_ids == transitioned.applied_ca_event_ids
    assert nxt.cash_dividend_receivable == transitioned.cash_dividend_receivable
    # the spell ledger advanced to the EXECUTION date: 1101 left, 2330 stayed
    closed = {sp.stock_id: sp.end for sp in nxt.holding_spells}
    assert closed["1101"] == "2026-04-01"
    assert closed["2330"] == ""


def test_checkpoints_accumulate_with_a_strictly_increasing_seq(tmp_path):
    run_dir = str(tmp_path)
    assert ps.next_seq(run_dir) == 1

    first = ps.append_checkpoint(run_dir, run_id="L3-1", period="2026-03",
                                 state=_state())
    assert first["seq"] == 1
    assert ps.next_seq(run_dir) == 2

    second = ps.append_checkpoint(
        run_dir, run_id="L3-1", period="2026-04",
        state=_state(as_of="2026-04-30", holding_spells=(
            HoldingSpell("2330", "2025-01-02", ""),
            HoldingSpell("1101", "2025-06-02", ""))))
    assert second["seq"] == 2

    path = ps.checkpoint_file(run_dir)
    reopened, prov = ps.opening_state(path, **_continuation(path, second))
    assert reopened.as_of == "2026-04-30"
    assert prov["checkpoint_sha256"] == second["checkpoint_sha256"]
    assert prov["handoff_sha256"] == ps.handoff_hash(second)
    assert prov["producer_run_id"] == "L3-1"


def test_a_checkpoint_row_is_round_tripped_before_it_is_written(tmp_path):
    """`verify=True` is not decoration: an unwritable state is never recorded."""
    rec = ps.append_checkpoint(str(tmp_path), run_id="L3-1", period="2026-03",
                               state=_state())
    raw = open(ps.checkpoint_file(str(tmp_path)), encoding="utf-8").read()
    row = json.loads(raw.strip())

    assert row["checkpoint_sha256"] == rec["checkpoint_sha256"]
    assert row["state"]["security_receivables"][0]["shares"] == "3/7"


# --- corporate-action delivery ------------------------------------------------------

def test_delivery_is_over_the_economic_interest_set_not_the_share_ledger():
    """B0.7/R10: a claim-only security is reached, a stranger is not."""
    state = _state()
    ev_claim = CorporateActionEvent(
        "9999", "capital_reduction", "2026-03-10", NOT_RECONSTRUCTIBLE,
        reason="terms not observable", knowledge_ts="2026-03-10")
    ev_stranger = CorporateActionEvent(
        "5555", "capital_reduction", "2026-03-10", NOT_RECONSTRUCTIBLE,
        reason="terms not observable", knowledge_ts="2026-03-10")

    side = ps.build_portfolio_side(
        _assembled([_row("2330"), _row("1101")]), state, sessions=SESSIONS,
        events_by_sid={"9999": (ev_claim,), "5555": (ev_stranger,)})

    reached = {e.stock_id for e in side.corporate_action_events}
    assert "9999" in reached
    assert "5555" not in reached

