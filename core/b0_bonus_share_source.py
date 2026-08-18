"""C-51 · the canonical holder-multiplier source for stock dividends.

C-50 ruled WHAT a share-unit adjustment is and left one input open: a stock
dividend is an eligible holder-level transformation (R2) with a market-effective
boundary (R4), but none of the registered artefacts carried the multiplier. The
ledger holds a new-share COUNT, and turning a count into `old x m = new` needs
shares outstanding at the boundary — a quantity with its own lineage question.
`stock_dividend_holder_multiplier_source` was registered under M-3 rather than
guessed. This module is the ruling that closed it.

The finding that made the ruling possible: **both exchanges publish the holder
ratio directly.** TWSE prints it as field A of the 除權除息計算結果表 detail and
TPEx prints it in the 除權除息 range table itself, and each exchange separates it
from the employee-bonus and cash-capital-increase legs — the same split C-50/R2
had already ruled eligible / ineligible. So no denominator has to be
reconstructed at all.

The unit was MEASURED, not read off the column name. Each published number was
checked against the exchange's own reference-price identity

    參考價 = (前收 − 現金股利 + 認購價 x 認購率) / (1 + 無償配股率 + 認購率)

using only the exchange's own published components. This does not derive `m`
from a price — `m` is published — it asks which reading of the units satisfies
the publisher's own arithmetic, and exactly one does:

    per 1,000 shares held   TPEx  max |Δ| 0.0050  100.00% within 0.01 (n=1,106)
                            TWSE  max |Δ| 0.0999   97.92% within 0.01 (n=1,253)
    decimal ratio           TPEx  max |Δ| 2095.11    0% ; TWSE 1527.98    0%
    percent                 TPEx  max |Δ|  953.18    0% ; TWSE 1035.86    0%

Coverage over the 3,215 canonical stock-dividend events the 141-period lookback
can reach: 2,376 matched with a strictly positive official ratio (73.90%), zero
matched-with-zero, zero unresolved transport failures. The share of the priced
universe whose 13-month window contains an unresolved event falls from a median
of 10.56% to 1.41% — below the §2.3 industry-UNRESOLVED exclusion the frozen
specification already accepts.

Three things this module makes impossible rather than discouraged:

  * **The denominator cannot come back.** `新股股數 / 流通在外股數`, current
    shares outstanding, and reference-price inversion are named and refused, not
    merely unused. Each of them is a way to manufacture a plausible multiplier.
  * **A live endpoint cannot be a source.** L2 reading `TWT49UDetail` mid-run
    would make a sealed result depend on what a web service answered that
    afternoon. 1,371 payloads are harvested, hashed and bound first.
  * **A residual cannot quietly become a number.** Pre-listing events are
    NOT_APPLICABLE rather than missing (R2); a scheduled date that fell on a
    closed market maps to the exact next observed session and to nothing else
    (R3); anything left over stays UNRESOLVED and reaches C-50/R8 (R4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

# Bumped when parsing or normalisation of an official payload changes in a way
# that could move a number. R5: it is part of the sealed identity, so a silent
# parser fix cannot masquerade as the same source.
BONUS_PARSER_VERSION = "official_bonus_share_parser_v1"
BONUS_IMPORTER_VERSION = "b0_bonus_share_importer@1"


class BonusShareSourceError(RuntimeError):
    """Fail-loud: a bonus-share source or disposition the ruling does not allow."""


class UnresolvedBonusEvent(BonusShareSourceError):
    """R4: no official ratio, not pre-listing, not a closure-day rescheduling."""


# --- R1 · the canonical source and the canonical conversion -------------------

OFFICIAL_BOARDS: tuple[str, ...] = ("TWSE", "TPEx")

# The published field, per board. Named in full because the two exchanges write
# the per-thousand unit differently — TWSE 每千股, TPEx 每仟股 — and normalising
# the two spellings into one lookup is exactly how a present field gets read as
# absent.
OFFICIAL_BONUS_FIELD: Mapping[str, str] = {
    "TWSE": "A. 按普通股股東持股比例每千股無償配股",
    "TPEx": "每仟股無償配股",
}

OFFICIAL_ENDPOINT: Mapping[str, str] = {
    "TWSE": "https://www.twse.com.tw/rwd/zh/exRight/TWT49UDetail?STK_NO=&T1=",
    "TPEx": "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ?startDate=&endDate=",
}

# The measured unit. A constant rather than a literal 1000 in a formula, so that
# "what unit is this" is answerable without reading arithmetic.
BONUS_UNIT = "shares_per_1000_held"
BONUS_PER_1000_DIVISOR = 1000.0

CANONICAL_CONVERSION = "holder_multiplier = 1 + bonus_shares_per_1000 / 1000"

# R1 · every other way of arriving at a multiplier, named so that reintroducing
# one is a visible edit rather than an import.
FORBIDDEN_MULTIPLIER_SOURCES: tuple[str, ...] = (
    "new_shares_over_shares_outstanding",
    "current_shares_outstanding",
    "reference_price_inversion",
    "cash_dividend_corpus",
    "employee_bonus_shares",
    "paid_capital_increase_shares",
)


def holder_multiplier_from_bonus(bonus_shares_per_1000: float) -> float:
    """R1: the canonical conversion. The only admissible one."""
    try:
        b = float(bonus_shares_per_1000)
    except (TypeError, ValueError):
        raise UnresolvedBonusEvent(
            f"C-51/R1: bonus_shares_per_1000 {bonus_shares_per_1000!r} is not "
            f"numeric; a multiplier may not be inferred from it") from None
    if b != b or b < 0:
        raise UnresolvedBonusEvent(
            f"C-51/R1: bonus_shares_per_1000 {b!r} is not a valid allotment")
    return 1.0 + b / BONUS_PER_1000_DIVISOR


def assert_multiplier_source_admissible(source: str) -> None:
    """R1: only the official exchange field is authoritative."""
    if source in FORBIDDEN_MULTIPLIER_SOURCES:
        raise BonusShareSourceError(
            f"C-51/R1: {source!r} is not an admissible holder-multiplier source. "
            f"The official exchange bonus-share field is the authoritative "
            f"holder-level ratio; {list(FORBIDDEN_MULTIPLIER_SOURCES)} are all "
            f"refused, including for gap-filling.")
    if source != "official_exchange_bonus_share":
        raise BonusShareSourceError(
            f"C-51/R1: {source!r} is not the canonical source name "
            f"'official_exchange_bonus_share'")


# --- R2 · pre-listing residuals ------------------------------------------------
# Not missing data. If the security had not appeared on either PIT trading board
# when the event happened, B0 has no market history there to adjust, and
# requiring a pre-listing adjustment chain would invent one. The listing spell
# still starts from the security's own canonical post-listing history, so this
# disposition never excludes anything that comes after.

PRE_LISTING_DISPOSITION = "NOT_APPLICABLE_TO_B0_MARKET_HISTORY"
MATCHED_DISPOSITION = "OFFICIAL_BONUS_RATE"
UNRESOLVED_DISPOSITION = "UNRESOLVED"
DISPOSITIONS: tuple[str, ...] = (
    MATCHED_DISPOSITION, PRE_LISTING_DISPOSITION, UNRESOLVED_DISPOSITION)

# R2 · established from contemporaneous exchange appearance, never from a
# current label. §2.3 already showed the current 上市別 is rewritten on
# delisting, so reading it backwards is look-ahead.
BOARD_ATTRIBUTION_SOURCE = "contemporaneous_exchange_payload"
CURRENT_LISTING_LABEL_ALLOWED = False


def is_pre_listing(event_session: str,
                   prior_official_sessions: Sequence[str]) -> bool:
    """R2: had the security appeared on either official board before this event?

    `prior_official_sessions` are the sessions on which the exchanges themselves
    published this security — PIT evidence, bounded by the event. An exchange
    publishes the ex-right calculation for every security on its board, so a
    bonus issue absent from both boards on its own date, by a security with no
    earlier board appearance at all, is a listing fact and not a data gap.
    """
    if not event_session:
        raise BonusShareSourceError("C-51/R2: event_session is required")
    for s in prior_official_sessions:
        if str(s) > str(event_session):
            raise BonusShareSourceError(
                f"C-51/R2: {s!r} is after the event session {event_session!r}; "
                f"a pre-listing classification may not use later information.")
    return not any(str(s) < str(event_session) for s in prior_official_sessions)


def assert_not_current_board_status(source: str) -> None:
    if source != BOARD_ATTRIBUTION_SOURCE:
        raise BonusShareSourceError(
            f"C-51/R2: board attribution must come from "
            f"{BOARD_ATTRIBUTION_SOURCE!r}, not {source!r}. The current 上市別 "
            f"label is rewritten on delisting (§2.3), so using it to decide what "
            f"was listed in 2014 is look-ahead.")


# --- R3 · non-trading scheduled ex-right dates --------------------------------
# MEASURED: 13 official ex-right dates in the harvested window are not sessions
# in the frozen calendar, and in every case the canonical ledger date is exactly
# the first observed session strictly after. All are market-closure days
# (2013-08-21, 2014-07-23, 2015-07-10, 2016-07-08, 2016-09-28, 2019-08-09,
# 2019-09-30, 2023-08-03, 2024-07-24, 2024-07-25). The exchange kept the
# scheduled date; the market-effective event moved.
#
# This is event-date NORMALIZATION, not tolerance. C-50/R4 already says the
# boundary is the market-effective session; this only says which official row
# describes it.

EVENT_DATE_NORMALIZATION = (
    "If the official scheduled ex-right date is not an observed trading "
    "session, and the canonical ledger ex_or_effective_date equals the first "
    "observed trading session strictly after that scheduled date, they "
    "represent the same market-effective event.")
NEAREST_DATE_MATCHING_ALLOWED = False
DATE_TOLERANCE_DAYS = 0


def market_effective_session(scheduled_date: str,
                             sessions: Sequence[str]) -> str:
    """R3: the session the scheduled ex-right date actually took effect on.

    The scheduled date itself when it IS a session — the normal case, and no
    normalization happens. Otherwise the FIRST observed session strictly after
    it, and nothing else: not the nearest, not the previous, not within N days.
    """
    if not scheduled_date:
        raise BonusShareSourceError("C-51/R3: scheduled_date is required")
    ordered = sorted(str(s) for s in sessions)
    if str(scheduled_date) in set(ordered):
        return str(scheduled_date)
    for s in ordered:
        if s > str(scheduled_date):
            return s
    raise UnresolvedBonusEvent(
        f"C-51/R3: no observed trading session after the scheduled ex-right "
        f"date {scheduled_date!r}; the market-effective session is not "
        f"reconstructible")


def assert_same_market_effective_event(scheduled_date: str,
                                       ledger_date: str,
                                       sessions: Sequence[str]) -> None:
    """R3: the ONLY admissible way an official row and a ledger row differ.

    Equal dates, or a scheduled date that is not a session whose exact next
    observed session is the ledger date. Every other pairing — including one
    calendar day apart when both are sessions, and two sessions after a closure
    — is rejected, because admitting it would be the ±N-day matching R3 forbids.
    """
    if str(scheduled_date) == str(ledger_date):
        return
    ordered = sorted(str(s) for s in sessions)
    if str(scheduled_date) in set(ordered):
        raise BonusShareSourceError(
            f"C-51/R3: the scheduled ex-right date {scheduled_date!r} IS an "
            f"observed session, so it is its own market-effective session; it "
            f"may not be matched to {ledger_date!r}. Nearest-date matching is "
            f"not admissible (NEAREST_DATE_MATCHING_ALLOWED="
            f"{NEAREST_DATE_MATCHING_ALLOWED}).")
    exact = market_effective_session(scheduled_date, ordered)
    if exact != str(ledger_date):
        raise BonusShareSourceError(
            f"C-51/R3: the first observed session after the closed-market "
            f"scheduled date {scheduled_date!r} is {exact!r}, not "
            f"{ledger_date!r}. Only the exact next observed session normalises; "
            f"there is no tolerance window (DATE_TOLERANCE_DAYS="
            f"{DATE_TOLERANCE_DAYS}).")


# --- R4 · what is left over ----------------------------------------------------

def resolve_disposition(*, official_bonus_per_1000: float | None,
                        pre_listing: bool) -> str:
    """R1/R2/R4: exactly one disposition, and no fourth answer exists."""
    if official_bonus_per_1000 is not None:
        return MATCHED_DISPOSITION
    if pre_listing:
        return PRE_LISTING_DISPOSITION
    return UNRESOLVED_DISPOSITION


def assert_no_inferred_multiplier(disposition: str, multiplier) -> None:
    """R4: an unresolved event must not carry a number."""
    if disposition == UNRESOLVED_DISPOSITION and multiplier is not None:
        raise BonusShareSourceError(
            f"C-51/R4: an UNRESOLVED event carries multiplier {multiplier!r}. "
            f"It must reach C-50/R8 fail-loud / NA / complete-case, or a new "
            f"M-3 item — never an inferred factor.")
    if disposition == PRE_LISTING_DISPOSITION and multiplier is not None:
        raise BonusShareSourceError(
            f"C-51/R2: a {PRE_LISTING_DISPOSITION} event carries multiplier "
            f"{multiplier!r}. B0 has no pre-listing market history to adjust.")


# --- R5 · the sealed source contract -------------------------------------------

@dataclass(frozen=True)
class BonusShareSourceContract:
    """D1-7 / C-48 shape, applied to the official bonus-share panel."""

    name: str
    endpoints: Mapping[str, str]
    importer_version: str
    parser_version: str
    schema_sha256: str
    content_sha256: str
    upstream_manifest_sha256: str
    upstream_sha256: Mapping[str, str]     # every raw payload, by key
    date_min: str
    date_max: str
    events_total: int
    events_matched: int
    events_not_applicable: int
    events_unresolved: int
    securities: int
    live_fetch: bool
    bonus_unit: str = BONUS_UNIT
    conversion: str = CANONICAL_CONVERSION
    board_attribution_source: str = BOARD_ATTRIBUTION_SOURCE

    def __post_init__(self) -> None:
        for f in ("name", "importer_version", "parser_version", "schema_sha256",
                  "content_sha256", "upstream_manifest_sha256", "date_min",
                  "date_max"):
            if not str(getattr(self, f)).strip():
                raise BonusShareSourceError(
                    f"C-51/R5: bonus-share source {self.name or '?'} must "
                    f"declare {f}. A hash written only in a findings document "
                    f"is not provenance a route can check.")
        if not self.upstream_sha256:
            raise BonusShareSourceError(
                f"C-51/R5: {self.name} declares no upstream payload hashes.")
        if self.events_total <= 0 or self.securities <= 0:
            raise BonusShareSourceError(
                f"C-51/R5: {self.name}: events and securities must be > 0")
        parts = (self.events_matched + self.events_not_applicable +
                 self.events_unresolved)
        if parts != self.events_total:
            raise BonusShareSourceError(
                f"C-51/R5: {self.name}: coverage does not partition the event "
                f"set ({self.events_matched} + {self.events_not_applicable} + "
                f"{self.events_unresolved} != {self.events_total}). A coverage "
                f"statistic that does not add up is not a coverage statistic.")


def assert_bonus_source_admissible(contract: BonusShareSourceContract) -> None:
    """Every way of getting an inadmissible multiplier in fails loudly here."""
    if contract.live_fetch:
        raise BonusShareSourceError(
            f"C-51/R5: {contract.name!r} declares live_fetch=True. No live "
            f"TWSE/TPEx request is admissible during L2; the panel must be "
            f"materialised, hashed and provenance-bound first.")
    if contract.parser_version != BONUS_PARSER_VERSION:
        raise BonusShareSourceError(
            f"C-51/R5: {contract.name!r} was built by parser "
            f"{contract.parser_version!r} but this build is "
            f"{BONUS_PARSER_VERSION!r}. A parser change can move a number, so it "
            f"changes the source identity rather than being invisible.")
    if contract.importer_version != BONUS_IMPORTER_VERSION:
        raise BonusShareSourceError(
            f"C-51/R5: {contract.name!r} declares importer "
            f"{contract.importer_version!r}, not {BONUS_IMPORTER_VERSION!r}")
    if contract.bonus_unit != BONUS_UNIT:
        raise BonusShareSourceError(
            f"C-51/R1: {contract.name!r} declares unit {contract.bonus_unit!r}; "
            f"the measured unit is {BONUS_UNIT!r}")
    if contract.conversion != CANONICAL_CONVERSION:
        raise BonusShareSourceError(
            f"C-51/R1: {contract.name!r} declares conversion "
            f"{contract.conversion!r}, not the canonical "
            f"{CANONICAL_CONVERSION!r}")
    assert_not_current_board_status(contract.board_attribution_source)
    for board in contract.endpoints:
        if board not in OFFICIAL_BOARDS:
            raise BonusShareSourceError(
                f"C-51/R5: {contract.name!r} declares endpoint for board "
                f"{board!r}; known boards are {OFFICIAL_BOARDS}")


def coverage_record(contract: BonusShareSourceContract) -> dict:
    """R5: the coverage statistics that travel with any use of this source."""
    return {
        "events_total": contract.events_total,
        "matched_official_bonus_rate": contract.events_matched,
        PRE_LISTING_DISPOSITION.lower(): contract.events_not_applicable,
        "unresolved": contract.events_unresolved,
        "matched_rate": round(contract.events_matched / contract.events_total, 6),
        "date_min": contract.date_min,
        "date_max": contract.date_max,
        "securities": contract.securities,
    }
