# -*- coding: utf-8 -*-
"""Per-period serialization of `PortfolioState` — the resumption surface.

Every B0.x diagnostic harness so far writes two things per period: a NAV row
(`nav_series.json`) and a progress row (`period_progress.jsonl`). The progress
row carries `post_state_hash` — a hash, which can *verify* a state but cannot
*reconstitute* one. So the portfolio side of the run has never been persisted,
and the only way to reach period N has always been to replay periods 1..N-1.

That is correct for the replay itself and this module does not change it: a
sealed run stays a from-period-1 deterministic replay, and a checkpoint is
NEVER an admissible starting state for one. What the checkpoint is for is the
hand-off — the terminal state at the end of a completed window is the opening
state a forward (L3 / production-route) track has to begin from, and today that
state exists only in memory and is destroyed when the process exits.

Two failure modes this module is built against, both of which this repository
has already paid for once:

  * **C-55 / B0.6 payload gotcha** — a state gained fields, the hashed payload
    did not, and two materially different states hashed identically. So the
    field coverage here is checked MECHANICALLY against `dataclasses.fields`
    (`_assert_field_coverage`). Adding a field to `PortfolioState` and not to
    this module raises at import time rather than silently writing a checkpoint
    that has quietly stopped being complete.

  * **`ca._state_hash` is deliberately narrower than the state.** It omits
    `holding_spells` (B0.1's exposure ledger). A round-trip verified against it
    alone would therefore pass while losing the spell ledger entirely. So
    `checkpoint_hash()` here covers every field, and the CA hash is recorded
    ALONGSIDE it — as a cross-check against `period_progress.jsonl`, not as the
    verification.

Exactness: `SecurityReceivable.shares` is a `Fraction` and §6.1.9 forbids
rounding it. It is written as its exact `"n/d"` string form and read back with
`Fraction(str)`, so no float ever touches the entitlement. Floats that are
genuinely floats (`cash`, receivable amounts) are written by the canonical JSON
primitive with no rounding or normalisation.
"""
from __future__ import annotations

import dataclasses
import json
import os
from fractions import Fraction

from core.b0_canonical_hash import canonical_sha256
from core.b0_corporate_actions import _state_hash as ca_state_hash
from core.b0_state import (
    CashReceivable,
    HoldingSpell,
    PortfolioState,
    SecurityReceivable,
)

CHECKPOINT_FORMAT_VERSION = "b0_portfolio_checkpoint@1"
CHECKPOINT_FILENAME = "portfolio_checkpoint.jsonl"

# --- the cohort a checkpoint belongs to ----------------------------------------
#
# A checkpoint carries a state, and a state carries CASH. Nothing in it used to
# carry the COHORT that cash belongs to, and the L3 prospective track runs two
# registered cells side by side (L3_PRIMARY_20M at NT$20,000,000 and
# L3_SECONDARY_50M at NT$50,000,000). Cohort identity was therefore asserted at
# genesis and then dropped: from period 2 onward the only thing separating the
# two tracks was the magnitude of `state.cash`.
#
# That is not a cosmetic gap. NAV is the input to
# `core.b0_eligibility.adv_floor(port_value)`, so a checkpoint handed to the
# wrong track silently changes the ELIGIBLE POPULATION and then produces a
# decision that looks entirely normal. The cohort has to travel WITH the state.
#
# `cohort_id` is a row field and NOT part of the hashed state payload:
# `checkpoint_sha256` covers `serialize_state(state)` alone, so adding this
# neither moves any state hash already written nor changes
# `portfolio_side.handoff_hash`. It is always present — empty string when the
# writer named none — because a field that can be absent is a field a reader
# has to guess about.
CHECKPOINT_COHORT_FIELD = "cohort_id"

# How a reader is required to treat the cohort field. Declared, never inferred.
COHORT_MUST_BE_NAMED = "COHORT_MUST_BE_NAMED_BY_EVERY_ROW"
COHORT_MAY_PREDATE_THE_LINEAGE = "COHORT_MAY_PREDATE_THE_LINEAGE"
COHORT_RULES = (COHORT_MUST_BE_NAMED, COHORT_MAY_PREDATE_THE_LINEAGE)


class CheckpointError(RuntimeError):
    """Fail-loud: a checkpoint could not be written, read or verified."""


# --- mechanical field coverage -------------------------------------------------
# The frozen field list of every dataclass this module serialises. Compared
# against the live dataclass at import time. This is the C-55 lesson expressed
# as a structural guard rather than as a comment asking a future author to
# remember.

_COVERED = {
    PortfolioState: (
        "as_of", "cash", "shares", "pending_exit", "cash_dividend_receivable",
        "stock_dividend_receivable", "security_receivables", "cash_receivables",
        "applied_ca_event_ids", "pending_exit_on_receivable", "holding_spells",
    ),
    SecurityReceivable: (
        "security_id", "shares", "credit_tradable_date", "event_id",
        "source_security_id", "origin_effective_date",
    ),
    CashReceivable: (
        "amount", "cash_available_date", "event_id", "source_security_id",
    ),
    HoldingSpell: ("stock_id", "start", "end"),
}


def _assert_field_coverage() -> None:
    for cls, covered in _COVERED.items():
        live = tuple(f.name for f in dataclasses.fields(cls))
        missing = [n for n in live if n not in covered]
        stale = [n for n in covered if n not in live]
        if missing or stale:
            raise CheckpointError(
                "%s has drifted from this checkpoint's field list "
                "(unserialised: %s; no longer on the dataclass: %s). A "
                "checkpoint that silently stops carrying a field is the C-55 "
                "defect: it round-trips, it hashes, and it is wrong. Add the "
                "field to _COVERED and to the (de)serializer together."
                % (cls.__name__, missing or "none", stale or "none"))


_assert_field_coverage()


# --- serialization -------------------------------------------------------------

def _ser_security_receivable(r: SecurityReceivable) -> dict:
    return {
        "security_id": r.security_id,
        # exact: "n/d", never a float. §6.1.9.
        "shares": str(Fraction(r.shares)),
        "credit_tradable_date": r.credit_tradable_date,
        "event_id": r.event_id,
        "source_security_id": r.source_security_id,
        "origin_effective_date": r.origin_effective_date,
    }


def _de_security_receivable(d: dict) -> SecurityReceivable:
    return SecurityReceivable(
        security_id=str(d["security_id"]),
        shares=Fraction(str(d["shares"])),
        credit_tradable_date=str(d["credit_tradable_date"]),
        event_id=str(d["event_id"]),
        source_security_id=str(d.get("source_security_id", "")),
        origin_effective_date=str(d.get("origin_effective_date", "")),
    )


def _ser_cash_receivable(r: CashReceivable) -> dict:
    return {
        "amount": r.amount,
        "cash_available_date": r.cash_available_date,
        "event_id": r.event_id,
        "source_security_id": r.source_security_id,
    }


def _de_cash_receivable(d: dict) -> CashReceivable:
    return CashReceivable(
        amount=float(d["amount"]),
        cash_available_date=str(d["cash_available_date"]),
        event_id=str(d["event_id"]),
        source_security_id=str(d.get("source_security_id", "")),
    )


def _ser_spell(s: HoldingSpell) -> dict:
    return {"stock_id": s.stock_id, "start": s.start, "end": s.end}


def _de_spell(d: dict) -> HoldingSpell:
    return HoldingSpell(stock_id=str(d["stock_id"]), start=str(d["start"]),
                        end=str(d.get("end", "")))


def serialize_state(state: PortfolioState) -> dict:
    """`PortfolioState` -> a plain dict the canonical JSON primitive accepts.

    Ordering is canonical everywhere a set or an unordered mapping is involved,
    so two byte-equal states serialise byte-equally.
    """
    return {
        "as_of": state.as_of,
        "cash": state.cash,
        "shares": dict(sorted(dict(state.shares).items())),
        "pending_exit": dict(sorted(dict(state.pending_exit).items())),
        "cash_dividend_receivable": state.cash_dividend_receivable,
        "stock_dividend_receivable": dict(
            sorted(dict(state.stock_dividend_receivable).items())),
        "security_receivables": sorted(
            (_ser_security_receivable(r) for r in state.security_receivables),
            key=lambda d: (d["security_id"], d["credit_tradable_date"],
                           d["event_id"], d["shares"])),
        "cash_receivables": sorted(
            (_ser_cash_receivable(r) for r in state.cash_receivables),
            key=lambda d: (d["cash_available_date"], d["event_id"],
                           d["source_security_id"], d["amount"])),
        "applied_ca_event_ids": sorted(state.applied_ca_event_ids),
        "pending_exit_on_receivable": sorted(state.pending_exit_on_receivable),
        "holding_spells": sorted(
            (_ser_spell(s) for s in state.holding_spells),
            key=lambda d: (d["stock_id"], d["start"], d["end"])),
    }


def deserialize_state(payload: dict) -> PortfolioState:
    """The inverse. Every core validator runs — a checkpoint is not a bypass."""
    return PortfolioState(
        as_of=str(payload["as_of"]),
        cash=float(payload["cash"]),
        shares={str(k): int(v) for k, v in dict(payload["shares"]).items()},
        pending_exit={str(k): int(v)
                      for k, v in dict(payload["pending_exit"]).items()},
        cash_dividend_receivable=float(payload["cash_dividend_receivable"]),
        stock_dividend_receivable={
            str(k): int(v)
            for k, v in dict(payload["stock_dividend_receivable"]).items()},
        security_receivables=tuple(
            _de_security_receivable(d) for d in payload["security_receivables"]),
        cash_receivables=tuple(
            _de_cash_receivable(d) for d in payload["cash_receivables"]),
        applied_ca_event_ids=frozenset(
            str(x) for x in payload["applied_ca_event_ids"]),
        pending_exit_on_receivable=frozenset(
            str(x) for x in payload["pending_exit_on_receivable"]),
        holding_spells=tuple(_de_spell(d) for d in payload["holding_spells"]),
    )


def checkpoint_hash(state: PortfolioState) -> str:
    """Full-coverage state identity — every field, `holding_spells` included.

    NOT interchangeable with `core.b0_corporate_actions._state_hash`, which is
    scoped to the CA transition contract and omits the spell ledger.
    """
    return canonical_sha256(serialize_state(state))


def assert_roundtrip(state: PortfolioState) -> PortfolioState:
    """Serialise, read back, and refuse to proceed unless nothing moved.

    Verified on the FULL-coverage hash. Verifying on the CA hash would pass
    while dropping `holding_spells`, which is precisely the hole this exists to
    close.
    """
    back = deserialize_state(json.loads(json.dumps(serialize_state(state))))
    before, after = checkpoint_hash(state), checkpoint_hash(back)
    if before != after:
        raise CheckpointError(
            "checkpoint round-trip changed the state: %s -> %s. The state is "
            "not being written completely." % (before[:16], after[:16]))
    return back


# --- record shape --------------------------------------------------------------

def checkpoint_record(*, run_id: str, seq: int, period: str,
                      state: PortfolioState, verify: bool = True,
                      cohort_id: str = "") -> dict:
    """One checkpoint row. `ca_state_hash` is a cross-check, not the check.

    It is written so a checkpoint can be tied to the `post_state_hash` the
    harness already records in `period_progress.jsonl` for the same period —
    two independently-computed identities over one state.

    `cohort_id` names the capacity cohort this state belongs to — see
    `CHECKPOINT_COHORT_FIELD`. It defaults to empty rather than being required
    because this record predates the cohort and a writer that cannot name one
    must say so rather than guess; a READER that requires it says so with
    `assert_checkpoint_cohort(..., rule=COHORT_MUST_BE_NAMED)`, which is where
    the refusal lives.
    """
    if verify:
        assert_roundtrip(state)
    payload = serialize_state(state)
    return {
        "format": CHECKPOINT_FORMAT_VERSION,
        "run_id": run_id,
        "seq": int(seq),
        "period": period,
        CHECKPOINT_COHORT_FIELD: str(cohort_id or ""),
        "checkpoint_sha256": canonical_sha256(payload),
        "ca_state_hash": ca_state_hash(state),
        "positions": len([1 for v in payload["shares"].values() if v > 0]),
        "open_spells": len([s for s in payload["holding_spells"]
                            if not s["end"]]),
        "state": payload,
    }


def read_checkpoints(path: str) -> list:
    """Read a checkpoint jsonl, verifying each row's recorded hash."""
    if not os.path.exists(path):
        raise CheckpointError("no checkpoint file at %s" % path)
    rows = []
    with open(path, "rb") as fh:
        for n, raw in enumerate(fh.read().decode("utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            rec = json.loads(raw)
            if rec.get("format") != CHECKPOINT_FORMAT_VERSION:
                raise CheckpointError(
                    "%s line %d: format %r, expected %r"
                    % (path, n, rec.get("format"), CHECKPOINT_FORMAT_VERSION))
            got = canonical_sha256(rec["state"])
            if got != rec["checkpoint_sha256"]:
                raise CheckpointError(
                    "%s line %d (period %s): recorded %s, recomputed %s — the "
                    "checkpoint has been altered since it was written"
                    % (path, n, rec.get("period"),
                       str(rec["checkpoint_sha256"])[:16], got[:16]))
            rows.append(rec)
    if not rows:
        raise CheckpointError("%s holds no checkpoint rows" % path)
    seqs = [r["seq"] for r in rows]
    if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
        raise CheckpointError(
            "%s: seq column is not a strictly increasing sequence (%s ...). A "
            "checkpoint file with a repeated or reordered period cannot say "
            "which state is terminal." % (path, seqs[:8]))
    return rows


def cohort_of(record: dict) -> str:
    """The cohort one checkpoint row names, or "" if it names none."""
    return str(record.get(CHECKPOINT_COHORT_FIELD, "") or "")


def assert_checkpoint_cohort(path: str, *, expected_cohort_id: str,
                             rule: str) -> dict:
    """The cohort a checkpoint file carries, verified against the caller's.

    `rule` is REQUIRED and has no default, because the two cases are different
    contracts and the difference is not inferable from the file:

        COHORT_MUST_BE_NAMED
            a CONTINUATION. Every row must name a cohort, all rows must name
            the SAME one, and it must be the one the caller declared. A row
            that names none, or a file that names a different cell, is the
            crossed-checkpoint defect and it aborts: NAV feeds
            `adv_floor(port_value)`, so continuing the wrong track produces a
            normal-looking decision over a silently different population.

        COHORT_MAY_PREDATE_THE_LINEAGE
            a GENESIS opening. The file was written before this lineage
            existed, so it is allowed to name nothing — but if it DOES name a
            cohort, that cohort must be this one. "Older than the field" is a
            reason for absence; it is not a reason to ignore a disagreement.

    Returns what was verified, so the run can record it rather than assert it.
    """
    if rule not in COHORT_RULES:
        raise CheckpointError(
            "abort: cohort rule %r is not one of %s. How a reader treats the "
            "cohort field is a declaration, never an inference."
            % (rule, list(COHORT_RULES)))
    expected = str(expected_cohort_id or "")
    if not expected:
        raise CheckpointError(
            "abort: a checkpoint cohort check must name the cohort it expects. "
            "Verifying against an unnamed cohort verifies nothing.")

    rows = read_checkpoints(path)
    named = {cohort_of(r) for r in rows}
    unnamed = [int(r["seq"]) for r in rows if not cohort_of(r)]

    if rule == COHORT_MUST_BE_NAMED and unnamed:
        raise CheckpointError(
            "abort: %s row(s) at seq %s name no cohort (%s), and this hand-off "
            "is a CONTINUATION. The two registered L3 cells differ only by "
            "opening cash, and cash is the input to adv_floor(port_value) — a "
            "checkpoint that cannot say which cell it belongs to cannot open "
            "the next period of either.\n  file: %s"
            % (len(unnamed), unnamed[:8], CHECKPOINT_COHORT_FIELD, path))

    disagreeing = sorted(c for c in named if c and c != expected)
    if disagreeing:
        raise CheckpointError(
            "abort: this checkpoint names cohort(s) %s; the run declared %r. A "
            "checkpoint crossed between two capacity cells yields a decision "
            "that looks normal and was taken over a different eligible "
            "population.\n  file: %s" % (disagreeing, expected, path))
    return {
        "cohort_id": expected,
        "cohort_rule": rule,
        "rows_verified": len(rows),
        "rows_naming_a_cohort": len(rows) - len(unnamed),
        "rows_naming_no_cohort": len(unnamed),
    }


def terminal_state(path: str, *, expect_period: str = "",
                   expect_seq: int = 0) -> PortfolioState:
    """The last checkpointed state, reconstituted and re-verified.

    This is the hand-off surface — the opening state a forward track begins
    from. `expect_period` / `expect_seq` are the caller's assertion about WHICH
    terminal it wants; a hand-off that silently accepts a short run is how a
    partial replay becomes an opening balance.
    """
    rows = read_checkpoints(path)
    last = rows[-1]
    if expect_period and last["period"] != expect_period:
        raise CheckpointError(
            "terminal checkpoint is %s, caller expected %s — this file is not "
            "the run it was taken for" % (last["period"], expect_period))
    if expect_seq and int(last["seq"]) != int(expect_seq):
        raise CheckpointError(
            "terminal checkpoint is seq %d, caller expected %d — the run did "
            "not reach the period this hand-off assumes"
            % (int(last["seq"]), int(expect_seq)))
    state = deserialize_state(last["state"])
    if checkpoint_hash(state) != last["checkpoint_sha256"]:
        raise CheckpointError(
            "terminal checkpoint for %s did not survive reconstitution"
            % last["period"])
    return state
