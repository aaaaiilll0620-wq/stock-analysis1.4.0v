# -*- coding: utf-8 -*-
"""Checkpoint serialization of `PortfolioState`.

The point of these tests is not that a dict round-trips. It is that the
checkpoint cannot quietly stop being COMPLETE — the C-55 / B0.6 failure mode,
where a state gained a field, the hashed payload did not, and two materially
different states became indistinguishable.
"""
from __future__ import annotations

import dataclasses
import json
import os
from fractions import Fraction

import pytest

from core.b0_corporate_actions import _state_hash as ca_state_hash
from core.b0_state import (
    CashReceivable,
    HoldingSpell,
    PortfolioState,
    SecurityReceivable,
)
from research.b0_checkpoint.portfolio_checkpoint import (
    _COVERED,
    CHECKPOINT_FORMAT_VERSION,
    CheckpointError,
    checkpoint_hash,
    checkpoint_record,
    deserialize_state,
    read_checkpoints,
    serialize_state,
    terminal_state,
)
from core.b0_master_prereg import append_provenance_record


# The exact claim that stops the B0.7 replay at period 67 — a denominator no
# float can hold. If the checkpoint ever routes an entitlement through a float,
# this is the value that shows it.
BLOCKER_CLAIM = Fraction(1095000008783686330995078643,
                         1250000000000000000000000000)


def rich_state(as_of: str = "2020-01-30") -> PortfolioState:
    """A state with every field non-empty. An all-defaults state proves nothing."""
    return PortfolioState(
        as_of=as_of,
        cash=1234567.89,
        shares={"2330": 1000, "8913": 1044, "2454": 300},
        pending_exit={"2454": 300},
        cash_dividend_receivable=4821.5,
        stock_dividend_receivable={"2330": 42},
        security_receivables=(
            SecurityReceivable(
                security_id="9999", shares=BLOCKER_CLAIM,
                credit_tradable_date="2020-02-14", event_id="8913|conv|2020-01-14",
                source_security_id="8913", origin_effective_date="2020-01-14"),
            SecurityReceivable(
                security_id="1101", shares=Fraction(7, 2),
                credit_tradable_date="2020-03-02", event_id="1101|sd|2020-01-20",
                source_security_id="", origin_effective_date="2020-01-20"),
        ),
        cash_receivables=(
            CashReceivable(amount=250000.0, cash_available_date="2020-02-20",
                           event_id="8913|cash|2020-01-14",
                           source_security_id="8913"),
        ),
        applied_ca_event_ids=frozenset({"a|x|2019-12-01", "b|y|2019-06-30"}),
        pending_exit_on_receivable=frozenset({"9999"}),
        holding_spells=(
            HoldingSpell("2330", "2017-03-01", ""),
            HoldingSpell("8913", "2017-05-02", "2017-08-01"),
            HoldingSpell("2454", "2019-11-01", ""),
        ),
    )


# --- completeness --------------------------------------------------------------

@pytest.mark.parametrize("cls", list(_COVERED))
def test_covered_field_list_matches_the_live_dataclass(cls):
    """The guard that makes every other test in this file meaningful.

    If this fails, a field was added to a serialised dataclass and the
    checkpoint was not taught about it. Do NOT relax it — teach the
    (de)serializer the field.
    """
    assert tuple(f.name for f in dataclasses.fields(cls)) == _COVERED[cls]


def test_roundtrip_preserves_every_field():
    """Round-trip is CANONICAL-order preserving, not literal-order preserving.

    The serializer sorts the three tuple-valued fields, exactly as
    `ca._state_hash` already sorts its own payload, which is what makes the
    hash order-independent. So membership is compared, not sequence order.
    """
    st = rich_state()
    back = deserialize_state(json.loads(json.dumps(serialize_state(st))))
    unordered = {"security_receivables", "cash_receivables", "holding_spells"}
    for name in _COVERED[PortfolioState]:
        got, want = getattr(back, name), getattr(st, name)
        if name in unordered:
            assert sorted(got, key=repr) == sorted(want, key=repr), name
        else:
            assert got == want, name
    assert checkpoint_hash(back) == checkpoint_hash(st)


def test_entitlement_fraction_survives_exactly():
    """§6.1.9: no rounding at the transition stage, and none in transit either."""
    st = rich_state()
    back = deserialize_state(json.loads(json.dumps(serialize_state(st))))
    got = {r.security_id: r.shares for r in back.security_receivables}
    assert got["9999"] == BLOCKER_CLAIM
    assert isinstance(got["9999"], Fraction)
    assert got["9999"].denominator == BLOCKER_CLAIM.denominator
    assert got["1101"] == Fraction(7, 2)


# --- the hole this module exists to close --------------------------------------

def test_ca_state_hash_is_blind_to_holding_spells_and_checkpoint_hash_is_not():
    """The negative control.

    `ca._state_hash` is scoped to the CA transition contract and omits B0.1's
    spell ledger. A checkpoint verified against it alone would round-trip
    "successfully" while dropping exposure history. So the two hashes must
    genuinely differ in scope, and this asserts it rather than trusting it.
    """
    st = rich_state()
    no_spells = dataclasses.replace(st, holding_spells=())

    assert ca_state_hash(st) == ca_state_hash(no_spells)          # blind
    assert checkpoint_hash(st) != checkpoint_hash(no_spells)      # not blind


def test_checkpoint_hash_moves_for_every_field():
    """No field may be inert in the hashed payload (the C-55 defect, generalised)."""
    st = rich_state()
    base = checkpoint_hash(st)
    mutations = {
        "as_of": "2020-02-27",
        "cash": 1234567.90,
        "shares": {"2330": 1000, "8913": 1043, "2454": 300},
        "pending_exit": {"2454": 299},
        "cash_dividend_receivable": 4821.6,
        "stock_dividend_receivable": {"2330": 43},
        "security_receivables": st.security_receivables[:1],
        "cash_receivables": (),
        "applied_ca_event_ids": frozenset({"a|x|2019-12-01"}),
        "pending_exit_on_receivable": frozenset(),
        "holding_spells": st.holding_spells[:2],
    }
    assert set(mutations) == set(_COVERED[PortfolioState])
    for name, value in mutations.items():
        assert checkpoint_hash(dataclasses.replace(st, **{name: value})) != base, name


def test_serialization_is_order_independent():
    st = rich_state()
    shuffled = dataclasses.replace(
        st,
        shares={"2454": 300, "2330": 1000, "8913": 1044},
        security_receivables=tuple(reversed(st.security_receivables)),
        holding_spells=tuple(reversed(st.holding_spells)),
    )
    assert checkpoint_hash(shuffled) == checkpoint_hash(st)


def test_deserialize_runs_the_core_validators():
    """A checkpoint is not a way in past §6.4."""
    payload = serialize_state(rich_state())
    payload["cash"] = -1.0
    with pytest.raises(Exception):
        deserialize_state(payload)


# --- file-level behaviour ------------------------------------------------------

def _write(path, records):
    for rec in records:
        append_provenance_record(path, json.loads(json.dumps(rec, default=str)))


def test_read_checkpoints_verifies_recorded_hashes(tmp_path):
    path = os.path.join(str(tmp_path), "portfolio_checkpoint.jsonl")
    rec = checkpoint_record(run_id="R1", seq=1, period="2020-01",
                            state=rich_state())
    assert rec["format"] == CHECKPOINT_FORMAT_VERSION
    _write(path, [rec])
    assert len(read_checkpoints(path)) == 1

    tampered = json.loads(json.dumps(rec))
    tampered["state"]["cash"] = 999999.0
    path2 = os.path.join(str(tmp_path), "tampered.jsonl")
    _write(path2, [tampered])
    with pytest.raises(CheckpointError, match="altered since it was written"):
        read_checkpoints(path2)


def test_terminal_state_reconstitutes_the_last_period(tmp_path):
    path = os.path.join(str(tmp_path), "cp.jsonl")
    _write(path, [
        checkpoint_record(run_id="R1", seq=1, period="2019-12",
                          state=rich_state("2019-12-31")),
        checkpoint_record(run_id="R1", seq=2, period="2020-01",
                          state=rich_state("2020-01-30")),
    ])
    st = terminal_state(path, expect_period="2020-01", expect_seq=2)
    assert st.as_of == "2020-01-30"
    assert checkpoint_hash(st) == checkpoint_hash(rich_state("2020-01-30"))


def test_terminal_state_refuses_a_hand_off_the_caller_did_not_ask_for(tmp_path):
    """A short run must not become someone's opening balance."""
    path = os.path.join(str(tmp_path), "cp.jsonl")
    _write(path, [checkpoint_record(run_id="R1", seq=67, period="2020-01",
                                    state=rich_state())])
    with pytest.raises(CheckpointError, match="not the run it was taken for"):
        terminal_state(path, expect_period="2026-03")
    with pytest.raises(CheckpointError, match="did not reach the period"):
        terminal_state(path, expect_seq=141)


def test_out_of_order_or_duplicated_periods_are_refused(tmp_path):
    path = os.path.join(str(tmp_path), "cp.jsonl")
    _write(path, [
        checkpoint_record(run_id="R1", seq=2, period="2020-01", state=rich_state()),
        checkpoint_record(run_id="R1", seq=1, period="2019-12", state=rich_state()),
    ])
    with pytest.raises(CheckpointError, match="strictly increasing"):
        read_checkpoints(path)


def test_ca_state_hash_cross_check_is_recorded(tmp_path):
    """The tie-back to `period_progress.jsonl`'s `post_state_hash`."""
    st = rich_state()
    rec = checkpoint_record(run_id="R1", seq=1, period="2020-01", state=st)
    assert rec["ca_state_hash"] == ca_state_hash(st)
    assert rec["checkpoint_sha256"] != rec["ca_state_hash"]
    assert rec["positions"] == 3
    assert rec["open_spells"] == 2
