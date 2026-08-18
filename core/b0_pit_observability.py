"""O-B · PIT price-observability semantics for Frozen B0.

The rejected design was a global `last_price_date` lookup: "what is the final
trading day of this security in the database?". Asked during a replay standing at
2019-05-01, that question is answered with data from after 2019-05-01. The name
itself encodes the look-ahead, which is why it is gone rather than repaired.

What B0 actually needs is not permanence but *explainability at t*:

    standing at `as_of`, is there a price gap in a held position that nothing
    known through `as_of` accounts for?

Permanent disappearance is deliberately NOT a concept here. A security that
never trades again looks, on the first missing session, exactly like one that
resumes tomorrow — and only future data separates them. B0 therefore never
classifies "gone forever"; it classifies "unexplained as of today", and that
classification can change as more sessions are observed.

Four PIT observables, every one of them bounded by `as_of`:

    price_observed_through(t)        last session with an observed price, <= t
    expected_trading_sessions(t)     sessions the calendar known through t expects
    known_security_status(t)         listed / suspended / delisted, as filed <= t
    known_corporate_actions(t)       events with effective date <= t

Zero free parameters. There is no "tolerate N missing sessions" knob: any
expected session with no observed price and no known explanation aborts on the
day it is observed. A tolerance would be exactly the threshold W-1 refused, and
would silently mark a vanished holding at a stale price for N days.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


class LookAheadError(RuntimeError):
    """Fail-loud: information dated after `as_of` reached a PIT decision."""


class PriceObservabilityError(RuntimeError):
    """Fail-loud: a held position cannot be marked and nothing explains it."""


# --- gap classifications ------------------------------------------------------

CURRENT = "CURRENT"
EXPLAINED_SUSPENSION = "EXPLAINED_SUSPENSION"
EXPLAINED_CORPORATE_ACTION = "EXPLAINED_CORPORATE_ACTION"
UNEXPLAINED_GAP = "UNEXPLAINED_GAP"

GAP_CLASSIFICATIONS: tuple[str, ...] = (
    CURRENT, EXPLAINED_SUSPENSION, EXPLAINED_CORPORATE_ACTION, UNEXPLAINED_GAP,
)

# Security statuses that account for the absence of a traded price. `listed`
# does not: a listed name on an expected session with no price is a gap.
NON_TRADING_STATUSES: tuple[str, ...] = ("suspended", "delisted", "halted")
SECURITY_STATUSES: tuple[str, ...] = ("listed",) + NON_TRADING_STATUSES

# Deliberately absent, and named so that reintroducing one is visible in a diff.
STALE_MARK_SESSION_TOLERANCE = None


# --- look-ahead enforcement ---------------------------------------------------

def assert_not_after(as_of: str, **dated: str | None) -> None:
    """Every dated input must be <= as_of. This is the whole O-B ruling.

    Enforced on the arguments rather than trusted to the caller, because the
    rejected design's defect was a *signature* that made look-ahead expressible.
    """
    if not as_of:
        raise LookAheadError("as_of is required for any PIT observation")
    for name, value in dated.items():
        if value is None:
            continue
        if str(value) > str(as_of):
            raise LookAheadError(
                f"O-B: {name}={value!r} is dated after as_of={as_of!r}. Standing "
                f"at {as_of} that fact is not observable; a PIT decision must "
                f"not consume it."
            )


@dataclass(frozen=True)
class PitPriceObservation:
    """One held security, as observable standing at `as_of`.

    Every field is a PIT observable. There is no field naming a final or last
    trading day of the security, because that quantity does not exist at `as_of`.
    """
    as_of: str
    stock_id: str
    price_observed_through: str | None      # last session with a price, <= as_of
    expected_sessions: tuple[str, ...]      # calendar sessions known through as_of
    known_status: str = "listed"
    status_available_from: str | None = None    # O-E-1: when it became knowable
    explaining_corporate_action: str | None = None      # kind, effective <= as_of
    corporate_action_available_from: str | None = None

    def __post_init__(self) -> None:
        assert_not_after(
            self.as_of,
            price_observed_through=self.price_observed_through,
            status_available_from=self.status_available_from,
            corporate_action_available_from=self.corporate_action_available_from,
        )
        if self.known_status not in SECURITY_STATUSES:
            raise PriceObservabilityError(
                f"O-B/M-3: security status {self.known_status!r} is not defined; "
                f"known statuses are {SECURITY_STATUSES}")
        for s in self.expected_sessions:
            if str(s) > str(self.as_of):
                raise LookAheadError(
                    f"O-B: expected_sessions contains {s!r}, after as_of="
                    f"{self.as_of!r}. The trading calendar may only be consumed "
                    f"through as_of.")
        if self.known_status != "listed" and not self.status_available_from:
            raise PriceObservabilityError(
                f"O-B: status {self.known_status!r} must carry the date it became "
                f"known; an undated status cannot be shown to be PIT-available")
        if self.explaining_corporate_action and not self.corporate_action_available_from:
            raise PriceObservabilityError(
                "O-E-1: a corporate action offered as an explanation must carry "
                "the date it became publicly available")

    @property
    def missing_sessions(self) -> tuple[str, ...]:
        """Expected sessions after the last observed price, through as_of."""
        if not self.expected_sessions:
            return ()
        if self.price_observed_through is None:
            return tuple(self.expected_sessions)
        return tuple(s for s in self.expected_sessions
                     if str(s) > str(self.price_observed_through))

    @property
    def sessions_stale(self) -> int:
        return len(self.missing_sessions)


@dataclass(frozen=True)
class GapVerdict:
    stock_id: str
    classification: str
    sessions_stale: int
    reason: str = ""
    markable: bool = True
    stale_mark: bool = False
    diagnostics: Mapping[str, object] = field(default_factory=dict)


def _available_before(available_from: str | None, session: str) -> bool:
    """O-E-1: strictly before the session began. Same-day is not before."""
    return bool(available_from) and str(available_from) < str(session)


def classify_price_gap(obs: PitPriceObservation) -> GapVerdict:
    """Classify a held position's price gap using only information <= as_of."""
    stale = obs.sessions_stale

    if obs.price_observed_through is None:
        # Never priced through as_of: there is no number to mark it with, and no
        # amount of explanation supplies one.
        return GapVerdict(obs.stock_id, UNEXPLAINED_GAP, stale,
                          "held with no observed price at or before as_of",
                          markable=False)
    if stale == 0:
        return GapVerdict(obs.stock_id, CURRENT, 0)

    first_missing = obs.missing_sessions[0]

    if obs.known_status in NON_TRADING_STATUSES:
        # A known non-trading status is filed information, not an inference. The
        # position cannot trade and has no market price, so the last observed
        # price is the only PIT-available mark. That is forced, not chosen —
        # but it is flagged and counted so it can never pass unnoticed.
        #
        # O-E-1: it may only explain a session that began AFTER the status was
        # publicly available. A suspension filed after the close still carries
        # that day's date; using it to account for that day's missing price is
        # look-ahead wearing a correct-looking date.
        if not _available_before(obs.status_available_from, first_missing):
            return GapVerdict(
                obs.stock_id, UNEXPLAINED_GAP, stale,
                f"status {obs.known_status!r} became available "
                f"{obs.status_available_from}, not before the first missing "
                f"session {first_missing} (O-E-1)",
                markable=False)
        return GapVerdict(
            obs.stock_id, EXPLAINED_SUSPENSION, stale,
            f"status {obs.known_status!r} available from {obs.status_available_from}",
            stale_mark=True,
            diagnostics={"status": obs.known_status,
                         "available_from": obs.status_available_from,
                         "first_missing_session": first_missing})
    if obs.explaining_corporate_action:
        if not _available_before(obs.corporate_action_available_from, first_missing):
            return GapVerdict(
                obs.stock_id, UNEXPLAINED_GAP, stale,
                f"{obs.explaining_corporate_action} became available "
                f"{obs.corporate_action_available_from}, not before the first "
                f"missing session {first_missing} (O-E-1)",
                markable=False)
        return GapVerdict(
            obs.stock_id, EXPLAINED_CORPORATE_ACTION, stale,
            f"{obs.explaining_corporate_action} available from "
            f"{obs.corporate_action_available_from}",
            stale_mark=True,
            diagnostics={"kind": obs.explaining_corporate_action,
                         "available_from": obs.corporate_action_available_from,
                         "first_missing_session": first_missing})

    return GapVerdict(
        obs.stock_id, UNEXPLAINED_GAP, stale,
        f"{stale} expected session(s) since {obs.price_observed_through} with no "
        f"price and no known status or corporate action to account for it",
        markable=False)


def assert_no_unexplained_price_gap(
    as_of: str,
    observations: Iterable[PitPriceObservation],
) -> list[GapVerdict]:
    """Abort before marking if any held position has an unexplained gap.

    Returns the verdicts for the survivors so that the mark stage can consume
    `stale_mark` rather than re-deriving it.
    """
    verdicts = [classify_price_gap(o) for o in observations]
    bad = [v for v in verdicts if v.classification == UNEXPLAINED_GAP]
    if bad:
        detail = "; ".join(f"{v.stock_id} ({v.reason})" for v in bad[:10])
        more = f" and {len(bad) - 10} more" if len(bad) > 10 else ""
        raise PriceObservabilityError(
            f"O-B: standing at {as_of}, {len(bad)} held position(s) have a price "
            f"gap nothing known through {as_of} explains: {detail}{more}. "
            f"Treating a missing price as zero, or dropping the position, is the "
            f"silent NAV error this guard exists to prevent."
        )
    return verdicts


def assert_no_unexplained_gap_in_holdings(
    as_of: str,
    observations: Iterable[PitPriceObservation],
    holdings: Mapping[str, float] | Iterable[str],
) -> list[GapVerdict]:
    """O-F: the abort is scoped to EXPOSURE, structurally rather than by habit.

    `assert_no_unexplained_price_gap` aborts on whatever it is handed, which made
    "only pass it holdings" a caller convention — and a convention is what an
    earlier validation run broke when it fed the guard the whole universe and
    read the resulting abort as a route failure.

    The universe is not clean and O-F does not require it to be: an unexplained
    gap in a name B0 does not hold is a diagnostic. The same gap in a name B0
    holds is a NAV that cannot be computed, and it aborts.
    """
    held = set(holdings)
    scoped = [o for o in observations if o.stock_id in held]
    verdicts = assert_no_unexplained_price_gap(as_of, scoped)
    return verdicts


def universe_gap_diagnostic(
    as_of: str,
    observations: Iterable[PitPriceObservation],
    holdings: Mapping[str, float] | Iterable[str] = (),
) -> dict:
    """Classify every name without aborting on the ones B0 does not hold.

    O-F closes with an incomplete source, so this count is expected to be
    non-zero forever. It is reported so that "we never looked" and "we looked and
    none of them were held" stay distinguishable in the record.
    """
    held = set(holdings)
    verdicts = [(o, classify_price_gap(o)) for o in observations]
    unexplained = [(o, v) for o, v in verdicts
                   if v.classification == UNEXPLAINED_GAP]
    return {
        "as_of": as_of,
        "securities": len(verdicts),
        "by_classification": {
            c: sum(1 for _, v in verdicts if v.classification == c)
            for c in GAP_CLASSIFICATIONS},
        "unexplained_total": len(unexplained),
        "unexplained_held": sum(1 for o, _ in unexplained if o.stock_id in held),
        "unexplained_not_held": sum(1 for o, _ in unexplained
                                    if o.stock_id not in held),
        "aborts": bool([o for o, _ in unexplained if o.stock_id in held]),
        "enforced": False,
    }


def stale_mark_report(verdicts: Sequence[GapVerdict]) -> dict:
    """Mandatory disclosure: which marks were stale, and by how many sessions."""
    stale = [v for v in verdicts if v.stale_mark]
    return {
        "positions": len(verdicts),
        "stale_marks": len(stale),
        "by_classification": {
            c: sum(1 for v in verdicts if v.classification == c)
            for c in GAP_CLASSIFICATIONS},
        "max_sessions_stale": max((v.sessions_stale for v in stale), default=0),
        "detail": [{"stock_id": v.stock_id, "classification": v.classification,
                    "sessions_stale": v.sessions_stale, "reason": v.reason}
                   for v in stale],
    }


def assert_no_tolerance_policy() -> None:
    """O-B admits no 'tolerate N missing sessions' knob."""
    if STALE_MARK_SESSION_TOLERANCE is not None:
        raise PriceObservabilityError(
            "O-B: a stale-mark session tolerance would mark a vanished holding "
            "at its last price for N days and call it explained. Gaps are "
            "classified, never tolerated."
        )
