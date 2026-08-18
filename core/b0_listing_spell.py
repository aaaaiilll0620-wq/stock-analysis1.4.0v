"""O-G · canonical listing spells for Frozen B0.

O-F closes with fail-loud semantics: an unexplained price gap in a HELD position
aborts, and one in a name B0 does not hold does not. That leaves a second
question O-F does not answer, and answering it wrongly is silent rather than
loud.

    `8102` is priced 2004-01-02 .. 2005-08-30, then nothing for 4,474 sessions,
    then priced again from 2023-10-27. The master says `listed_from=2023-10-27`
    and records no delisting at all: the earlier listing episode survives in the
    price corpus and in no other registered source.

Concatenating those two runs into one price history is not a data question. A
20-session ADV window anchored at 2023-11-01 would reach back through eighteen
years of absence and average two different listings of the same code; a 12-1
momentum would compute a return across a gap in which the security did not
trade. Both produce a number, neither number means anything, and nothing
downstream can tell.

So B0 carries the concept explicitly:

    A **listing spell** is a maximal run of expected sessions over which a
    security's price series is continuous, where a gap breaks the run unless
    something known BEFORE the gap explains it.

Three consequences, all of them normative:

1. **An explained gap does not break a spell.** A suspension is an interruption
   *within* one listing; the security comes back as itself.
2. **An unexplained gap followed by reappearance does.** The new spell starts at
   the first REOBSERVED session — not at the disappearance, and not at any date
   derived from the return.
3. **Price lookbacks reset at the spell start.** ADV20, sigma20d, momentum and
   every other price-window quantity are computed inside the current spell or
   they are NA. NA propagates to complete-case exclusion (§3.3), which is an
   existing, visible path — unlike a silently bridged window.

**O-G is not a repair of O-F, and must not be used as one.** The reappearance is
information from after the disappearance. It may open a new spell going forward;
it may NOT be run backwards to account for the original gap. If B0 held the
security when it vanished, the O-F exposure abort has already fired, and it fires
on what was knowable then. `assert_disappearance_not_explained_by_return` exists
to make that ordering a check rather than a convention.

Zero free parameters. There is no minimum spell length, no maximum gap that
counts as "the same listing", and no tolerance: the explained/unexplained
classification decides, and it is O-B's, not a new one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from core.b0_pit_observability import LookAheadError


class ListingSpellError(RuntimeError):
    """Fail-loud: a price window would cross a listing-spell boundary."""


# Deliberately absent, and named so that reintroducing one shows up in a diff.
# A "gaps shorter than N sessions keep the spell" rule would be the tolerance
# knob O-B refused, relocated.
SPELL_BRIDGING_SESSION_TOLERANCE = None

# Price-window quantities that must be computed inside one spell. The number is
# the sessions of history the quantity consumes; a spell shorter than that
# yields NA rather than a value computed from fewer or from foreign sessions.
PRICE_LOOKBACK_SESSIONS: dict[str, int] = {
    "adv20": 20,
    "sigma20d": 20,
}


@dataclass(frozen=True)
class ListingSpell:
    """One continuous listing episode, as observable standing at `as_of`.

    `end` is deliberately absent. Standing at t, the current spell has no end —
    asserting one would be the `last_price_date` look-ahead O-B removed, wearing
    a different name.
    """
    stock_id: str
    start: str                      # first session of this spell, <= as_of
    opened_by: str                  # "first_observation" | "reappearance"
    as_of: str

    def __post_init__(self) -> None:
        if not self.start or not self.as_of:
            raise ListingSpellError("O-G: a spell requires start and as_of")
        if str(self.start) > str(self.as_of):
            raise LookAheadError(
                f"O-G: spell start {self.start} is after as_of {self.as_of}")
        if self.opened_by not in ("first_observation", "reappearance"):
            raise ListingSpellError(
                f"O-G/M-3: opened_by {self.opened_by!r} is not defined")

    def contains(self, session: str) -> bool:
        return str(self.start) <= str(session) <= str(self.as_of)


def derive_current_spell(
    as_of: str,
    stock_id: str,
    expected_sessions: Sequence[str],
    priced_sessions: Iterable[str],
    gap_is_explained: Callable[[str], bool],
) -> ListingSpell | None:
    """The spell in force at `as_of`, from information bounded by `as_of`.

    `gap_is_explained(first_missing_session)` is the O-B/O-E-1 question, injected
    rather than recomputed: this module must not grow a second opinion about what
    explains a gap.
    """
    if not as_of:
        raise ListingSpellError("O-G: as_of is required")
    for s in expected_sessions:
        if str(s) > str(as_of):
            raise LookAheadError(
                f"O-G: expected_sessions contains {s!r}, after as_of={as_of!r}")
    priced = {str(s) for s in priced_sessions}
    for s in priced:
        if s > str(as_of):
            raise LookAheadError(
                f"O-G: a price dated {s!r} is after as_of={as_of!r}")

    sessions = [str(s) for s in expected_sessions if str(s) in priced or True]
    start, opened_by = None, "first_observation"
    run_start = None
    for s in sessions:
        if s in priced:
            if start is None:
                start = s
            elif run_start is not None:
                # A gap just closed. Whether it broke the spell was decided by
                # what was knowable at its FIRST missing session, never by the
                # fact that the series resumed.
                if not gap_is_explained(run_start):
                    start, opened_by = s, "reappearance"
            run_start = None
        elif start is not None and run_start is None:
            run_start = s
    if start is None:
        return None
    return ListingSpell(stock_id=stock_id, start=start,
                        opened_by=opened_by, as_of=as_of)


def spell_sessions(spell: ListingSpell,
                   expected_sessions: Sequence[str]) -> tuple[str, ...]:
    """Expected sessions inside the spell, through as_of."""
    return tuple(str(s) for s in expected_sessions
                 if spell.start <= str(s) <= spell.as_of)


def assert_window_within_spell(spell: ListingSpell,
                               window_sessions: Sequence[str]) -> None:
    """A price window may not reach back past the start of the current spell."""
    outside = [str(s) for s in window_sessions if str(s) < spell.start]
    if outside:
        raise ListingSpellError(
            f"O-G: {spell.stock_id} price window reaches {outside[0]}, before "
            f"the current listing spell began {spell.start} ({spell.opened_by}). "
            f"Bridging spells averages two different listings of one code and "
            f"produces a number with no meaning attached to it."
        )


def lookback_is_available(spell: ListingSpell,
                          expected_sessions: Sequence[str],
                          required_sessions: int) -> bool:
    """Does the current spell hold enough of its OWN history for the window?"""
    return len(spell_sessions(spell, expected_sessions)) >= required_sessions


def price_lookback_or_na(key: str,
                         spell: ListingSpell | None,
                         expected_sessions: Sequence[str],
                         value: float | None) -> float | None:
    """NA rather than a value, when the new spell is too short to support it.

    §3.3 already excludes NA on a complete-case basis, so this routes into an
    existing visible path instead of inventing a second one.
    """
    if key not in PRICE_LOOKBACK_SESSIONS:
        from core.b0_open_items import raise_unspecified
        raise_unspecified(
            f"o_g_price_lookback_{key}",
            context=(f"O-G: {key!r} is not registered in PRICE_LOOKBACK_SESSIONS, "
                     f"so how many sessions of spell history it needs is "
                     f"undefined"))
    if spell is None:
        return None
    if not lookback_is_available(spell, expected_sessions,
                                 PRICE_LOOKBACK_SESSIONS[key]):
        return None
    return value


def assert_price_lookbacks_reset(
    as_of: str,
    spells: Mapping[str, ListingSpell],
    expected_sessions: Sequence[str],
    supplied: Mapping[str, Mapping[str, float]],
) -> list[str]:
    """Route guard: no spell-crossing ADV20/sigma20d may reach the core.

    `supplied` is {key: {stock_id: value}}. The guard fires on a spell opened by
    a REAPPEARANCE that is shorter than the window, because that is the case
    where a number can be manufactured from a previous listing of the same code.

    It deliberately does NOT fire on a short `first_observation` spell. There is
    no earlier listing to bridge to there, so a window that cannot be filled is a
    calendar-depth question and not an O-G one; treating the two alike would make
    every short fixture look like a bridging violation and teach a reader to
    ignore the guard.

    Whether a spell was declared at all is a SOURCE obligation, checked by the
    adapters for non-synthetic input (`assert_spells_declared`), not here: the
    route cannot tell an undeclared spell from an absent security.
    """
    violations = []
    for key, by_id in supplied.items():
        need = PRICE_LOOKBACK_SESSIONS.get(key)
        if need is None:
            continue
        for stock_id in by_id:
            spell = spells.get(stock_id)
            if spell is None or spell.opened_by != "reappearance":
                continue
            if not lookback_is_available(spell, expected_sessions, need):
                violations.append(
                    f"{stock_id}:{key} needs {need} sessions but its current "
                    f"spell reopened {spell.start} by reappearance")
    if violations:
        raise ListingSpellError(
            f"O-G: standing at {as_of}, {len(violations)} price-window "
            f"value(s) span a listing-spell boundary: {violations[:8]}. The "
            f"required value is NA, not a number averaged across two listings."
        )
    return violations


def assert_spells_declared(
    spells: Mapping[str, ListingSpell],
    supplied: Mapping[str, Mapping[str, float]],
) -> None:
    """Source obligation: a real replay must say which spell each window is in.

    Synthetic fixtures are exempt for the same reason they are exempt from D1-6:
    they exist to exercise mechanics, and inventing a listing history for them
    would test the invention. A real source has the price history and therefore
    has no excuse.
    """
    missing = sorted({sid for key, by_id in supplied.items()
                      if key in PRICE_LOOKBACK_SESSIONS
                      for sid in by_id if sid not in spells})
    if missing:
        raise ListingSpellError(
            f"O-G: {len(missing)} securit(ies) carry a price-window quantity "
            f"with no listing spell declared: {missing[:8]}. Standing at t the "
            f"adapter holds the price history; an undeclared spell is a window "
            f"nobody has shown to lie inside one listing."
        )


def assert_disappearance_not_explained_by_return(
    spell: ListingSpell,
    disappearance_session: str,
    gap_is_explained: Callable[[str], bool],
) -> None:
    """A reappearance opens a spell; it never accounts for the earlier gap.

    Reading the return backwards is the most natural mistake here — the data
    'shows' the security was fine — and it would quietly undo the O-F abort.
    """
    if spell.opened_by != "reappearance":
        return
    if gap_is_explained(disappearance_session):
        return
    if str(disappearance_session) >= str(spell.start):
        raise ListingSpellError(
            f"O-G: {spell.stock_id} disappearance {disappearance_session} is not "
            f"before the spell opened at {spell.start}; the ordering that makes "
            f"the abort PIT-valid does not hold")


def assert_no_bridging_tolerance() -> None:
    """O-G admits no 'gaps under N sessions keep the spell' knob."""
    if SPELL_BRIDGING_SESSION_TOLERANCE is not None:
        raise ListingSpellError(
            "O-G: a bridging tolerance would let a short unexplained gap keep "
            "the old spell, which is the stale-mark tolerance O-B refused, "
            "moved one module across.")
