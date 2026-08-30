# -*- coding: utf-8 -*-
"""B7 · the PORTFOLIO half of one L3 prospective decision.

`l3_assemble` builds the market half and stops there, deliberately:

    price_observations and corporate_action_events are EMPTY here, and that is
    definition A, not an oversight. [...] With no portfolio there is nothing to
    ask about, so they belong to the portfolio side and the runner (B7) fills
    them once the checkpoint supplies portfolio[t].
        -- research/b0_l3/l3_assemble.py, build_production_sources

This module is that portfolio side. It is the piece that was missing between
`research/b0_checkpoint/portfolio_checkpoint.py` (which could serialise a
`PortfolioState` but had no caller) and `research/b0_l3/` (which could build
everything about a period EXCEPT the portfolio).

WHAT IT OWNS

  * the opening state comes from a CHECKPOINT and from nowhere else. There is
    no default, no zero-cash fallback and no "start flat" convenience: a
    forward track that invents its own opening balance is not continuing the
    sealed history, it is starting a different experiment under the same name.
  * `price_observations` and `exposures`, per HELD security, on the same rules
    the sealed L2 runner uses. They are TRANSCRIBED from
    `research/b0_l2/run_sealed_l2.py:build_input`, not re-derived, because
    P2-3 requires a field to mean one thing across both routes.
  * the L3 corporate-action event universe, which is L2's `load_events()`
    answered from a run's DECLARED sources instead of from `data/b0/`.
  * the next `PortfolioState`, and the checkpoint row that carries it.

WHAT IT DOES NOT OWN

  * no strategy semantics. This module never scores, ranks, sizes or trades;
    every one of those happens behind `run_decision`, which this module does
    not call. The runner does.
  * no span derivation. `price_span` / `bonus_window` reach it as arguments.
  * no market-side field. `assert_market_state_is_portfolio_free` states the
    boundary from the other side; `assert_portfolio_side_is_market_free`
    states it from this one.

TWO TRANSCRIPTION HAZARDS, NAMED RATHER THAN HOPED AWAY

  1. L2 reads its corporate-action ledger out of a CSV, so every cell arrives
     as a string and `if row.get("share_multiplier"):` is false only for the
     empty cell. The L3 reader returns TYPED values, where the same expression
     is also false for `0.0`. Transcribing the truthiness test would silently
     drop a zero-valued term. Every optional term here is therefore tested
     against `None` / `""` explicitly.
  2. `ca._state_hash` omits `holding_spells`, so it cannot verify that a state
     survived a checkpoint round-trip. `portfolio_checkpoint.checkpoint_hash`
     is the verification; the CA hash is recorded beside it as a cross-check
     against the producing harness's own `period_progress.jsonl`.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import b0_corporate_actions as ca                        # noqa: E402
from core.b0_canonical_hash import canonical_sha256                # noqa: E402
from core.b0_corporate_actions import (                            # noqa: E402
    NOT_RECONSTRUCTIBLE, CorporateActionEvent, Exposure,
)
from core.b0_pit_observability import PitPriceObservation          # noqa: E402
from core.b0_state import PortfolioState                           # noqa: E402

from research.b0_checkpoint.portfolio_checkpoint import (          # noqa: E402
    CHECKPOINT_FILENAME, CheckpointError, checkpoint_hash, checkpoint_record,
    read_checkpoints, terminal_state,
)

PORTFOLIO_SIDE_CONTRACT_VERSION = "b0_l3_portfolio_side@1"

# Transcribed from `run_sealed_l2.build_input`. A held security with no market
# row at as_of has no spell to read, and L2 falls back to "the 60th session
# back, or the start of the calendar if the calendar is shorter". It is named
# here rather than inlined because it is L2's number, not a choice this module
# is entitled to make, and every use of it is reported
# (`held_without_market_row`) rather than absorbed.
HELD_WITHOUT_MARKET_ROW_SPELL_FALLBACK_SESSIONS = 60

# The market-side fields. A portfolio-side payload carrying any of them would be
# `assert_market_state_is_portfolio_free` read backwards.
MARKET_FIELDS = ("marks", "adv20", "sigma20d", "pit_inputs", "listing_spells",
                 "execution_prices", "untradable")


class PortfolioSideError(RuntimeError):
    """Fail-loud: the portfolio half of a decision cannot be built as declared."""


def _text(value):
    """None-safe text for a nullable state column.

    L2's row artefact stores an absent status date as the STRING "None",
    because its read-back applies `str()` to every text column; the L3 rows
    carry a real `None`. Both arrive here and both must mean absent.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "None":
        return None
    return s


def _optional(row, key):
    """A ledger term that is present, versus one that is empty.

    NOT `if row.get(key):` -- see hazard 1 in the module docstring.
    """
    v = row.get(key)
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v


# --- the L3 corporate-action event universe -----------------------------------

def load_events(run_dir: str, *, bonus_window, ledger=None, sessions=None,
                status_rows=None) -> dict:
    """`run_sealed_l2.load_events()`, answered from a run's DECLARED sources.

    Same construction, same field meanings, same C-51 rule: the ratio for a
    stock dividend comes from the OFFICIAL bonus panel, never from the ledger's
    new-share count -- converting a count needs shares outstanding, which is
    exactly the reconstruction C-51 exists to avoid.

    The difference from L2 is only WHERE the two inputs come from. L2 reads
    `data/b0/corporate_actions_ledger.csv` and
    `data/b0/bonus_share_panel.parquet`, which are sealed artefacts of a frozen
    window. An L3 period may not read them: they stop where L2's window stops,
    and a prospective decision that silently used a panel ending in March would
    be deciding on an event universe that had quietly closed.

    `bonus_window` is an ARGUMENT for the same reason it is one in
    `l3_assemble.assemble` -- it moves the state, and this module may not pick
    it.
    """
    from l3_readers import read_bonus_shares, read_calendar, read_corporate_actions

    if bonus_window is None or len(tuple(bonus_window)) != 2:
        raise PortfolioSideError(
            "abort: bonus_window is required and has no default here. It "
            "decides which stock-dividend events carry an official holder "
            "multiplier, and an event without one is NOT_RECONSTRUCTIBLE -- so "
            "choosing it silently would be choosing which securities become "
            "unreconstructible.")
    if sessions is None:
        sessions = list(read_calendar(run_dir))
    if ledger is None:
        ledger = read_corporate_actions(run_dir, status_rows=status_rows)

    panel = read_bonus_shares(run_dir, str(bonus_window[0]), str(bonus_window[1]),
                              ledger=ledger, sessions=sessions)
    bonus = {}
    for r in panel.itertuples():
        if r.disposition == "OFFICIAL_BONUS_RATE":
            bonus[(str(r.stock_id), str(r.market_effective_session))] = (
                Fraction(str(r.bonus_shares_per_1000)) / 1000)

    holder_affecting = set(ca.holder_affecting_kinds())
    by_sid: dict = {}
    for row in ledger:
        kind = row["kind"]
        if kind not in holder_affecting:
            continue
        sid, ex = str(row["stock_id"]), row["ex_or_effective_date"]
        if not ex:
            continue
        recon = row["reconstructibility"]
        kw = dict(reason=_optional(row, "reason") or "", knowledge_ts=str(ex),
                  credit_tradable_date=_optional(row, "credit_tradable_date"),
                  cash_payment_date=_optional(row, "cash_payment_date"))
        share_multiplier = _optional(row, "share_multiplier")
        if share_multiplier is not None:
            kw["share_multiplier"] = float(share_multiplier)
        cash_per_share = _optional(row, "cash_per_share")
        if cash_per_share is not None:
            kw["cash_per_share"] = float(cash_per_share)
        if kind == "stock_dividend":
            ratio = bonus.get((sid, str(ex)))
            if ratio is None:
                recon = NOT_RECONSTRUCTIBLE
                kw["reason"] = kw["reason"] or (
                    "no admissible official bonus-share ratio (C-51)")
            else:
                kw["stock_ratio"] = ratio
                if not kw["credit_tradable_date"]:
                    recon = NOT_RECONSTRUCTIBLE
                    kw["reason"] = "no credit_tradable_date (W-1)"
        if recon == NOT_RECONSTRUCTIBLE and not kw["reason"]:
            kw["reason"] = "identity-change terms are not observable"
        by_sid.setdefault(sid, []).append(
            CorporateActionEvent(sid, kind, str(ex), recon, **kw))
    return {k: tuple(v) for k, v in by_sid.items()}


# --- the opening state ---------------------------------------------------------

OPENING_GENESIS = "GENESIS"
OPENING_CONTINUATION = "CONTINUATION"
OPENING_KINDS = (OPENING_GENESIS, OPENING_CONTINUATION)

# The fields a genesis cohort must be empty in, beyond the five
# `core.b0_opening_state.PORTFOLIO_ECONOMIC_FIELDS` that module already fixes.
# A genesis portfolio has held nothing, so no corporate action can have reached
# it, no claim can have been created and no exposure spell can have opened.
GENESIS_MUST_BE_EMPTY = ("security_receivables", "cash_receivables",
                         "applied_ca_event_ids", "pending_exit_on_receivable",
                         "holding_spells")


def handoff_hash(record) -> str:
    """The identity of one hand-off, as opposed to the identity of one state.

    `checkpoint_record`'s `checkpoint_sha256` covers the STATE payload and
    nothing else -- deliberately, because that is what makes two byte-equal
    states hash equally. But it means the row's `run_id`, `period` and `seq`
    are carried beside an identity that does not cover them, so a state can be
    lifted out of one run's checkpoint file and presented as another run's
    terminal without any hash noticing.

    This binds the four together. It is computed here rather than added to
    `portfolio_checkpoint.checkpoint_record`, because changing that record's
    shape would change every `checkpoint_sha256` already written.
    """
    return canonical_sha256({
        "format": str(record.get("format", "")),
        "run_id": str(record.get("run_id", "")),
        "period": str(record.get("period", "")),
        "seq": int(record.get("seq", 0)),
        "checkpoint_sha256": str(record.get("checkpoint_sha256", "")),
    })


def assert_genesis_cohort(state: PortfolioState, *, c_ref: float) -> dict:
    """A1: the first prospective period opens on an INDEPENDENT cohort.

    Not "a portfolio that happens to be small" and not L2's terminal wealth:
    the registered opening state is `C_ref` in cash and nothing else, and the
    shape of it comes from `core.b0_opening_state.registered_opening_state` --
    the normative producer -- rather than from five equality checks written
    here. Writing them here is how a genesis cohort quietly acquires a
    position.
    """
    from core.b0_opening_state import (
        PORTFOLIO_ECONOMIC_FIELDS, registered_opening_state,
    )

    registered = registered_opening_state(state.as_of, c_ref)
    mismatched = []
    for field in PORTFOLIO_ECONOMIC_FIELDS:
        want = registered[field]
        got = getattr(state, field)
        got = dict(got) if isinstance(got, dict) or hasattr(got, "items") else got
        if got != want:
            mismatched.append((field, got, want))
    if mismatched:
        raise PortfolioSideError(
            "abort: this is declared a GENESIS opening but it is not the "
            "registered opening state (A1). Differing: %s.\n"
            "A genesis cohort is C_ref in cash and nothing else; anything else "
            "is a continuation wearing a genesis label, and the lineage it "
            "continues would go unrecorded."
            % [(f, g, w) for f, g, w in mismatched])
    non_empty = [f for f in GENESIS_MUST_BE_EMPTY if getattr(state, f)]
    if non_empty:
        raise PortfolioSideError(
            "abort: a GENESIS opening carries %s. A cohort that has held "
            "nothing cannot have a claim, an applied corporate action or an "
            "exposure spell." % non_empty)
    return {"c_ref": float(c_ref),
            "economic_fields_verified": list(PORTFOLIO_ECONOMIC_FIELDS),
            "empty_fields_verified": list(GENESIS_MUST_BE_EMPTY)}


def opening_state(checkpoint_file: str, *, kind: str,
                  producer_run_id: str = "", expect_period: str = "",
                  expect_seq: int = 0, expect_checkpoint_sha256: str = "",
                  expect_handoff_sha256: str = "",
                  expect_file_sha256: str = "", c_ref: float = 0.0) -> tuple:
    """The forward track's opening balance. From a checkpoint, or not at all.

    `kind` is REQUIRED and has no default, because the two openings are
    different contracts and the difference is not inferable from the file:

        GENESIS       the first prospective period. There is no producer run to
                      name, and instead the state itself must be A1's
                      registered cohort -- `c_ref` in cash, nothing held,
                      nothing claimed, no spell. `c_ref` is then required.
        CONTINUATION  every later period. There is nothing to check about the
                      state's CONTENT (it is whatever executing the previous
                      period produced), so the whole burden falls on the
                      lineage: which run produced it, which period, which seq,
                      and the two hashes over the row and the file. All of
                      them are required, because a hand-off nobody can trace
                      is indistinguishable from a state somebody assembled.

    Previously every one of those was optional and defaulted to skipped, so any
    self-consistent checkpoint opened any period. Returns
    `(PortfolioState, provenance_dict)`.
    """
    from core.b0_canonical_hash import file_sha256

    if kind not in OPENING_KINDS:
        raise PortfolioSideError(
            "abort: opening kind %r is not one of %s. Whether a period opens a "
            "lineage or continues one is a declaration, never an inference "
            "from the file it was handed." % (kind, list(OPENING_KINDS)))

    rows = read_checkpoints(checkpoint_file)
    last = rows[-1]

    if kind == OPENING_CONTINUATION:
        required = {"producer_run_id": producer_run_id,
                    "expect_period": expect_period,
                    "expect_seq": expect_seq,
                    "expect_checkpoint_sha256": expect_checkpoint_sha256,
                    "expect_handoff_sha256": expect_handoff_sha256,
                    "expect_file_sha256": expect_file_sha256}
        absent = sorted(k for k, v in required.items() if not v)
        if absent:
            raise PortfolioSideError(
                "abort: a CONTINUATION opening must name its whole lineage; "
                "missing %s. Run N -> run N+1 is the only thing that makes "
                "this a continuation of anything, and it has to be mechanically "
                "provable rather than asserted in a commit message." % absent)
        if str(last.get("run_id", "")) != str(producer_run_id):
            raise PortfolioSideError(
                "abort: the terminal checkpoint was written by run %r, the "
                "caller named producer %r. A state lifted out of another run's "
                "file is not this lineage's opening balance."
                % (last.get("run_id"), producer_run_id))

    state = terminal_state(checkpoint_file, expect_period=expect_period,
                           expect_seq=expect_seq)
    got = checkpoint_hash(state)
    if expect_checkpoint_sha256 and got != str(expect_checkpoint_sha256):
        raise PortfolioSideError(
            "abort: the terminal checkpoint hashes %s, the caller named %s. A "
            "hand-off whose opening state is not the one that was authorised "
            "is a different run." % (got[:16], str(expect_checkpoint_sha256)[:16]))

    row_hash = handoff_hash(last)
    if expect_handoff_sha256 and row_hash != str(expect_handoff_sha256):
        raise PortfolioSideError(
            "abort: the terminal hand-off hashes %s, the caller named %s. The "
            "STATE may match while the run_id / period / seq around it do not, "
            "which is exactly what this second identity exists to catch."
            % (row_hash[:16], str(expect_handoff_sha256)[:16]))

    measured_file = file_sha256(checkpoint_file)
    if expect_file_sha256 and measured_file != str(expect_file_sha256):
        raise PortfolioSideError(
            "abort: the checkpoint FILE hashes %s, the caller named %s. The "
            "terminal row can be identical while an earlier row was rewritten, "
            "and the file hash is the only thing that sees that."
            % (measured_file[:16], str(expect_file_sha256)[:16]))

    genesis = {}
    if kind == OPENING_GENESIS:
        if not c_ref:
            raise PortfolioSideError(
                "abort: a GENESIS opening must name `c_ref`. A1's cohort is "
                "defined by it, and a genesis that accepted whatever cash the "
                "file happened to carry would verify nothing.")
        if len(rows) != 1 or int(last["seq"]) != 1:
            raise PortfolioSideError(
                "abort: a GENESIS checkpoint file holds exactly one row at "
                "seq 1; this one holds %d row(s) ending at seq %d. A lineage "
                "that already has history is not opening."
                % (len(rows), int(last["seq"])))
        genesis = assert_genesis_cohort(state, c_ref=float(c_ref))

    return state, {
        "contract_version": PORTFOLIO_SIDE_CONTRACT_VERSION,
        "opening_source": "portfolio_checkpoint",
        "opening_kind": kind,
        "producer_run_id": str(last.get("run_id", "")),
        "checkpoint_file": os.path.abspath(checkpoint_file).replace("\\", "/"),
        "checkpoint_file_sha256": measured_file,
        "checkpoint_rows": len(rows),
        "terminal_period": last["period"],
        "terminal_seq": int(last["seq"]),
        "checkpoint_sha256": got,
        "handoff_sha256": row_hash,
        # The narrower of the two state identities, recorded so this state can
        # be tied to a `post_state_hash` in the producing harness's
        # period_progress.jsonl. It is a CROSS-CHECK: it is blind to
        # holding_spells and must never be used to verify the round-trip.
        "ca_state_hash": ca._state_hash(state),
        "as_of": state.as_of,
        "positions": len([1 for v in dict(state.shares).values() if v > 0]),
        "open_spells": len([1 for sp in state.holding_spells if not sp.end]),
        "genesis_cohort": genesis,
    }


# --- the portfolio half of one period -----------------------------------------

@dataclass(frozen=True)
class PortfolioSide:
    """Everything the market side left empty, plus the transition that made it."""
    as_of: str
    state: PortfolioState                    # POST-transition portfolio[t]
    price_observations: tuple
    exposures: tuple
    corporate_action_events: tuple
    applied_ca_event_ids: tuple
    claim_only_securities: tuple
    held_without_market_row: tuple
    transition_ledger: tuple


def transition(portfolio: PortfolioState, *, as_of: str, sessions,
               events_by_sid, period: str = ""):
    """§6.1.1's order, unchanged: redate, then transition, then validate.

    Carried out by `core.b0_corporate_actions` and by nothing here. The one
    thing this function adds is that the event set handed to the engine is
    derived from the REDATED state's entitlement securities, which is the
    domain B0.7 froze -- shares OR claims, not the spell ledger alone.
    """
    state = ca.redate(portfolio, str(as_of))
    held_events = [e for sid in state.entitlement_securities
                   for e in events_by_sid.get(sid, ())]
    return state, ca.transition_portfolio(
        state, held_events, as_of=str(as_of), sessions=tuple(sessions),
        period=str(period))


def build_portfolio_side(assembled: dict, portfolio: PortfolioState, *,
                         sessions, events_by_sid) -> PortfolioSide:
    """portfolio[t] + the market side -> the two fields the market side left empty.

    `portfolio` is the POST-transition state, exactly as `run_sealed_l2` passes
    `tr.state` into its own `build_input`: delivery and exposure are properties
    of the state the decision is actually made on.
    """
    period = assembled["period"]
    as_of = str(period["as_of"])
    if str(portfolio.as_of) != as_of:
        raise PortfolioSideError(
            "abort: the portfolio state is as of %s, the assembled market side "
            "is for %s. §6.6 resolves one as_of per decision and the two halves "
            "must stand on the same day." % (portfolio.as_of, as_of))

    rows_by_sid = {str(r["stock_id"]): r for r in assembled["rows"]}
    upto = [str(s) for s in sessions if str(s) <= as_of]
    if not upto:
        raise PortfolioSideError(
            "abort: the declared calendar has no session on or before %s; there "
            "is no history for a price observation to be expected over." % as_of)

    obs, exposures, orphan = [], [], []
    for sid in portfolio.held_securities:
        sid = str(sid)
        row = rows_by_sid.get(sid)
        if row is not None:
            start = str(row["spell_start"])
        else:
            # L2's fallback, transcribed. Reported, never absorbed: a held
            # security with no market row at as_of is the shape B0.6 and B0.7
            # both ended on, and it must be visible in the run's provenance
            # rather than reconstructed later from a stack trace.
            orphan.append(sid)
            n = HELD_WITHOUT_MARKET_ROW_SPELL_FALLBACK_SESSIONS
            start = str(upto[-n] if len(upto) > n else upto[0])
        expected = tuple(s for s in upto if s >= start)
        obs.append(PitPriceObservation(
            as_of=as_of, stock_id=sid,
            price_observed_through=as_of if row is not None else None,
            expected_sessions=expected,
            known_status=(str(row["known_status"]) if row is not None
                          else "listed"),
            status_available_from=(_text(row["status_available_from"])
                                   if row is not None else None),
            status_effective_from=(_text(row["status_effective_from"])
                                   if row is not None else None)))
        # B0.1/R2 and B0.2/R2: the portfolio's OWN spell ledger, and only the
        # spells active at as_of. The listing spell is a different object, and
        # declaring it here is what ended the official Frozen B0 L2 run in
        # period 2.
        for sp in portfolio.holding_spells:
            if str(sp.stock_id) != sid:
                continue
            if not (str(sp.start) <= as_of
                    and (sp.open or as_of <= str(sp.end))):
                continue
            exposures.append(Exposure(stock_id=sid, held_from=str(sp.start),
                                      held_until=str(sp.end or as_of)))

    # B0.7 · R10: the carrier is the normative module's, over the frozen
    # economic-interest set -- not a set assembled inside the loop above, which
    # is narrower than the one the transition engine was already fed.
    delivered = tuple(ca.deliver_ca_events(events_by_sid, portfolio, as_of=as_of))
    ca.assert_ca_event_delivery_conforms(delivered, portfolio, as_of=as_of)
    # The redundant consistency assertion (B0.1/R6): the caller's declaration is
    # checked against the state, it does not define it.
    ca.assert_caller_exposures_conform(tuple(exposures), portfolio, as_of=as_of)

    return PortfolioSide(
        as_of=as_of, state=portfolio,
        price_observations=tuple(obs), exposures=tuple(exposures),
        corporate_action_events=delivered,
        applied_ca_event_ids=tuple(sorted(portfolio.applied_ca_event_ids)),
        claim_only_securities=tuple(portfolio.claim_only_securities(as_of)),
        held_without_market_row=tuple(sorted(orphan)),
        transition_ledger=())


def with_transition_ledger(side: PortfolioSide, tr) -> PortfolioSide:
    """Attach the transition's own ledger rows for the runner to write out."""
    return replace(
        side,
        transition_ledger=tuple(dict(rec.__dict__) for rec in tr.ledger),
        applied_ca_event_ids=tuple(sorted(tr.applied_event_ids)))


def complete_sources(market_sources, side: PortfolioSide):
    """Fill the two fields `build_production_sources` left empty, and only those.

    `dataclasses.replace` rather than a fresh construction: a hand-rebuilt
    `ProductionSources` is a place for a market-side field to be quietly
    dropped, and the market side is not this module's to restate.
    """
    if market_sources.price_observations or market_sources.corporate_action_events:
        raise PortfolioSideError(
            "abort: the market-side ProductionSources already carries "
            "price_observations (%d) / corporate_action_events (%d). Definition "
            "A puts both on the portfolio side; a market side that filled them "
            "answered a question nobody asked."
            % (len(market_sources.price_observations),
               len(market_sources.corporate_action_events)))
    if market_sources.exposures:
        raise PortfolioSideError(
            "abort: the market-side ProductionSources already declares "
            "exposures; exposure is a property of the portfolio's spell ledger.")
    return replace(market_sources,
                   price_observations=side.price_observations,
                   corporate_action_events=side.corporate_action_events,
                   exposures=side.exposures)


def portfolio_side_payload(side: PortfolioSide) -> dict:
    """The hashable portfolio-side view. The mirror of `market_state_payload`.

    Deliberately absent: marks, adv20, sigma20d, pit_inputs, listing spells,
    execution prices and the untradable set. Those are causally generated by
    OBSERVING the market at as_of, and a portfolio-side hash that restated them
    would make the two halves indistinguishable from one another.
    """
    payload = {
        "as_of": side.as_of,
        "checkpoint_sha256": checkpoint_hash(side.state),
        "ca_state_hash": ca._state_hash(side.state),
        "price_observations": [
            {"stock_id": o.stock_id,
             "price_observed_through": o.price_observed_through,
             "expected_sessions": len(o.expected_sessions),
             "expected_sessions_from": (o.expected_sessions[0]
                                        if o.expected_sessions else None),
             "known_status": o.known_status,
             "status_available_from": o.status_available_from,
             "status_effective_from": o.status_effective_from}
            for o in sorted(side.price_observations, key=lambda x: x.stock_id)],
        "exposures": [
            {"stock_id": e.stock_id, "held_from": e.held_from,
             "held_until": e.held_until}
            for e in sorted(side.exposures,
                            key=lambda x: (x.stock_id, x.held_from))],
        "corporate_action_events": sorted(
            e.canonical_event_id() for e in side.corporate_action_events),
        "applied_ca_event_ids": list(side.applied_ca_event_ids),
        "claim_only_securities": list(side.claim_only_securities),
        "held_without_market_row": list(side.held_without_market_row),
    }
    assert_portfolio_side_is_market_free(payload)
    return payload


def assert_portfolio_side_is_market_free(payload) -> None:
    """`assert_market_state_is_portfolio_free`, read from the other side."""
    leaked = [k for k in MARKET_FIELDS if k in payload]
    if leaked:
        raise PortfolioSideError(
            "abort: the portfolio-side payload carries market field(s) %s. The "
            "two halves are hashed separately so that neither can quietly "
            "restate the other." % leaked)


# --- portfolio[t+1] and its checkpoint -----------------------------------------

def advance(*, decision_result, transitioned: PortfolioState, as_of: str,
            execution_date: str) -> PortfolioState:
    """The end-of-period state. Transcribed from the sealed L2 runner.

    Cash, shares and pending_exit come from EXECUTION; every claim-side field
    comes from the TRANSITION. Taking the claim fields from the execution
    session instead is how a matured receivable gets re-credited, and taking
    cash from the transition is how a trade goes unrecorded.
    """
    s = decision_result.session
    state = PortfolioState(
        as_of=str(as_of), cash=s.cash_after, shares=dict(s.shares_after),
        pending_exit=dict(s.pending_exit_after),
        cash_dividend_receivable=transitioned.cash_dividend_receivable,
        stock_dividend_receivable=dict(transitioned.stock_dividend_receivable),
        security_receivables=transitioned.security_receivables,
        cash_receivables=transitioned.cash_receivables,
        applied_ca_event_ids=transitioned.applied_ca_event_ids,
        pending_exit_on_receivable=transitioned.pending_exit_on_receivable,
        holding_spells=transitioned.holding_spells)
    return state.with_underlying_exposure_recorded(str(execution_date))


def checkpoint_file(run_dir: str) -> str:
    return os.path.join(run_dir, CHECKPOINT_FILENAME)


def next_seq(run_dir: str) -> int:
    """The seq a new checkpoint row must carry, read from the file itself.

    Not a counter the runner keeps: a counter in memory says 1 again after a
    restart, and `read_checkpoints` would then refuse the whole file for a
    non-increasing seq -- after it had already been written.
    """
    path = checkpoint_file(run_dir)
    if not os.path.exists(path):
        return 1
    return int(read_checkpoints(path)[-1]["seq"]) + 1


def append_checkpoint(run_dir: str, *, run_id: str, period: str,
                      state: PortfolioState, seq: int = 0) -> dict:
    """One verified checkpoint row, appended with the provenance primitive.

    `checkpoint_record(verify=True)` round-trips the state through the full
    serializer BEFORE the row is written, so a state that cannot survive being
    written is never recorded as though it had.
    """
    from core.b0_master_prereg import append_provenance_record

    rec = checkpoint_record(run_id=str(run_id),
                            seq=int(seq) or next_seq(run_dir),
                            period=str(period), state=state, verify=True)
    append_provenance_record(checkpoint_file(run_dir), rec)
    return rec


__all__ = [
    "GENESIS_MUST_BE_EMPTY",
    "HELD_WITHOUT_MARKET_ROW_SPELL_FALLBACK_SESSIONS",
    "MARKET_FIELDS",
    "OPENING_CONTINUATION",
    "OPENING_GENESIS",
    "OPENING_KINDS",
    "PORTFOLIO_SIDE_CONTRACT_VERSION",
    "CheckpointError",
    "PortfolioSide",
    "PortfolioSideError",
    "advance",
    "append_checkpoint",
    "assert_genesis_cohort",
    "assert_portfolio_side_is_market_free",
    "build_portfolio_side",
    "checkpoint_file",
    "complete_sources",
    "handoff_hash",
    "load_events",
    "next_seq",
    "opening_state",
    "portfolio_side_payload",
    "transition",
    "with_transition_ledger",
]

