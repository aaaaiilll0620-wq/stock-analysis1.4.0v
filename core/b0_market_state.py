"""O-E · trading-calendar and security-status sources for Frozen B0.

O-B froze *how* a price gap is judged. It did not say where the trading calendar
and the security status come from, nor whether those inputs are themselves
point-in-time. That gap matters more than it looks: if the status table is a
current snapshot — as `industry_map.parquet` turned out to be, with 49.4% of
securities having changed industry — then the O-B guard consumes look-ahead at
its input layer and every one of its own PIT checks is bypassed.

Four things are closed here, plus one invariant.

1. **Trading calendar.** A traceable historical session sequence. The full
   sequence is deliberately NOT reachable: `sessions_through(as_of)` is the only
   accessor, so a replay standing at t cannot read a session dated after t. A
   calendar is future-knowable (holidays are published in advance), which makes
   it the easiest way to smuggle look-ahead into an otherwise PIT computation.

2. **Security status source.** Must carry historical effective dates. A source
   that only knows the latest state is marked NOT_PIT_SAFE and may not enter B0
   at all — it is not repaired, because "the current status, applied to history"
   is precisely the industry_map defect.

3. **Status semantics.** Four states, and `unknown` is NOT normal. A security
   with no status record explains nothing; if it also has a price gap, that gap
   is unexplained and aborts.

4. **Provenance.** Every source carries importer version, schema hash, content
   hash and coverage, and converts to a B-21 `DatasetProvenance`. A runtime API
   returning an unversioned status is not an admissible source.

**O-E-1 (availability semantics).** A status may only explain a missing session
that began AFTER the status was publicly available. `effective_from <= session`
is not sufficient: a suspension filed after the close still carries that day's
date, and using it to explain that day's missing price is look-ahead wearing a
correct-looking date. The rule is therefore `available_from < session`, strictly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


class MarketStateError(RuntimeError):
    """Fail-loud: a market-state input is unusable or not PIT-safe."""


class NotPitSafeError(MarketStateError):
    """The source cannot answer 'what was known at t' and may not enter B0."""


# --- source contract ----------------------------------------------------------

PIT_SAFE = "PIT_SAFE"
NOT_PIT_SAFE = "NOT_PIT_SAFE"

SOURCE_KINDS: tuple[str, ...] = ("trading_calendar", "security_status")


@dataclass(frozen=True)
class SourceContract:
    """What a market-state source must declare before B0 will read it."""
    name: str
    kind: str
    importer_version: str
    content_sha256: str
    schema_sha256: str
    date_min: str
    date_max: str
    has_effective_dates: bool
    has_availability_semantics: bool
    is_current_snapshot: bool
    availability_convention: str = ""     # how available_from is derived

    def __post_init__(self) -> None:
        if self.kind not in SOURCE_KINDS:
            raise MarketStateError(
                f"O-E/M-3: source kind {self.kind!r} is not defined; "
                f"known kinds are {SOURCE_KINDS}")
        for f in ("name", "importer_version", "content_sha256", "schema_sha256",
                  "date_min", "date_max"):
            if not str(getattr(self, f)).strip():
                raise MarketStateError(
                    f"O-E: source {self.name or '?'} must declare {f}. An "
                    f"unversioned runtime response is not an admissible source.")

    def pit_safety(self) -> str:
        if self.is_current_snapshot or not self.has_effective_dates:
            return NOT_PIT_SAFE
        if self.kind == "security_status" and not self.has_availability_semantics:
            return NOT_PIT_SAFE
        return PIT_SAFE

    def assert_pit_safe(self) -> None:
        if self.pit_safety() != PIT_SAFE:
            raise NotPitSafeError(
                f"O-E: source {self.name!r} is NOT_PIT_SAFE "
                f"(current_snapshot={self.is_current_snapshot}, "
                f"effective_dates={self.has_effective_dates}, "
                f"availability={self.has_availability_semantics}). A source that "
                f"cannot say what was known at t must not enter B0 — applying "
                f"today's state to history is the industry_map defect."
            )

    def to_dataset_provenance(self):
        """B-21 §3 entry, so a sealed run is bound to this exact source."""
        from core.b0_provenance import DatasetProvenance
        return DatasetProvenance(
            name=self.name, content_sha256=self.content_sha256,
            schema_sha256=self.schema_sha256, date_min=self.date_min,
            date_max=self.date_max, importer_version=self.importer_version)


# --- 1. trading calendar ------------------------------------------------------

class TradingCalendar:
    """Observed trading sessions. The full sequence is not publicly reachable.

    Only `sessions_through(as_of)` is exposed. Handing out the whole calendar
    would let a caller ask "is next month a holiday?", which is answerable in
    reality but not answerable *from data a replay is allowed to hold*.
    """

    def __init__(self, sessions: Iterable[str], source: SourceContract):
        if source.kind != "trading_calendar":
            raise MarketStateError(
                f"O-E: {source.name!r} is not a trading_calendar source")
        source.assert_pit_safe()
        s = tuple(sorted(str(x) for x in sessions))
        if not s:
            raise MarketStateError("O-E: trading calendar is empty")
        if len(set(s)) != len(s):
            raise MarketStateError("O-E: trading calendar contains duplicate sessions")
        self._sessions = s
        self.source = source

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def coverage(self) -> tuple[str, str]:
        return self._sessions[0], self._sessions[-1]

    def sessions_through(self, as_of: str) -> tuple[str, ...]:
        if not as_of:
            raise MarketStateError("O-E: as_of is required")
        if as_of > self._sessions[-1]:
            raise MarketStateError(
                f"O-E: as_of={as_of} is beyond calendar coverage "
                f"(ends {self._sessions[-1]}); the run cannot assert which "
                f"sessions were expected.")
        return tuple(s for s in self._sessions if s <= as_of)

    def is_session(self, date: str, as_of: str) -> bool:
        return date in set(self.sessions_through(as_of))

    def sessions_between(self, start: str, as_of: str) -> tuple[str, ...]:
        return tuple(s for s in self.sessions_through(as_of) if s > start)


# --- 2 / 3. security status ---------------------------------------------------

STATUS_LISTED = "listed"
STATUS_SUSPENDED = "suspended"
STATUS_DELISTED = "delisted"
STATUS_UNKNOWN = "unknown"

SECURITY_STATUSES: tuple[str, ...] = (
    STATUS_LISTED, STATUS_SUSPENDED, STATUS_DELISTED, STATUS_UNKNOWN)
NON_TRADING_STATUSES: tuple[str, ...] = (STATUS_SUSPENDED, STATUS_DELISTED)


# --- 3b. event semantics (O-F ruling 4) ---------------------------------------
#
# Appearing in the vendor's 暫停交易 export does NOT make a row a trading
# suspension. Measured over the 20260818 vintage: 1,135 of the 1,148 capital
# reduction / par-value rows have a price on EVERY session of their own declared
# window. Those rows describe a 停止過戶 book-closure period, during which the
# security keeps trading. Reading them as `suspended` puts a standing
# explanation over a window where a genuine gap could hide.
#
# The mapping below is normative and is reproduced in master prereg §11 C-42, so
# it is a specification a reader can check rather than a rule that exists only
# here. Order is significant: a 合併下市 row is a termination, not a suspension.
#
# UNKNOWN is not a failure of the classifier; it is a statement about the source.
# It fails CLOSED -- an unknown event yields no status record at all, so it can
# never explain a missing price. Promoting it to `suspended` is exactly the
# silent over-claim this ruling removes.

TRADING_SUSPENSION = "TRADING_SUSPENSION"
LISTING_TERMINATION = "LISTING_TERMINATION"
BOOK_CLOSURE = "BOOK_CLOSURE"
UNKNOWN_EVENT_SEMANTICS = "UNKNOWN"

EVENT_SEMANTICS: tuple[str, ...] = (
    TRADING_SUSPENSION, LISTING_TERMINATION, BOOK_CLOSURE, UNKNOWN_EVENT_SEMANTICS)

LISTING_TERMINATION_MARKERS: tuple[str, ...] = ("下市", "終止", "併入")
BOOK_CLOSURE_MARKERS: tuple[str, ...] = ("減資", "面額變更", "停止過戶")
TRADING_SUSPENSION_MARKERS: tuple[str, ...] = (
    "暫停", "停止交易", "停止買賣", "櫃檯買賣", "違規", "重整", "緊急處分",
    "禁止轉讓", "重大訊息", "重大事項", "重大消息", "股價敏感", "待公布",
    "待公佈", "之查證", "停工", "內部控制", "內控", "營業細則", "章則",
    "業務規則", "25%", "自行申請", "輔導", "股務代理", "股務", "法院裁定",
    "營運資金",
)

# Only these two semantics may become a status record. BOOK_CLOSURE and UNKNOWN
# map to None, which is the whole point of the ruling.
STATUS_BY_EVENT_SEMANTICS: dict[str, str | None] = {
    TRADING_SUSPENSION: STATUS_SUSPENDED,
    LISTING_TERMINATION: STATUS_DELISTED,
    BOOK_CLOSURE: None,
    UNKNOWN_EVENT_SEMANTICS: None,
}


def classify_event_semantics(reason: str) -> str:
    """What the source SAYS happened, before any status is inferred from it."""
    text = str(reason or "").strip()
    if not text or text == ".":
        return UNKNOWN_EVENT_SEMANTICS
    if any(w in text for w in LISTING_TERMINATION_MARKERS):
        return LISTING_TERMINATION
    if any(w in text for w in BOOK_CLOSURE_MARKERS):
        return BOOK_CLOSURE
    if any(w in text for w in TRADING_SUSPENSION_MARKERS):
        return TRADING_SUSPENSION
    return UNKNOWN_EVENT_SEMANTICS


def status_for_event(reason: str) -> str | None:
    """The status a vendor row may become, or None if it may not become one."""
    return STATUS_BY_EVENT_SEMANTICS[classify_event_semantics(reason)]


def assert_not_promoted_to_suspended(reason: str, status: str | None) -> None:
    """An importer must not hand a non-suspension row a suspension status."""
    semantics = classify_event_semantics(reason)
    allowed = STATUS_BY_EVENT_SEMANTICS[semantics]
    if status != allowed:
        raise MarketStateError(
            f"O-F ruling 4: reason {reason[:40]!r} has semantics {semantics}, "
            f"which may only produce {allowed!r}, but {status!r} was assigned. "
            f"A book-closure or uninterpretable row must fail closed — it "
            f"explains no missing price — rather than be promoted to suspended."
        )


@dataclass(frozen=True)
class StatusRecord:
    """One filed status change.

    `available_from` has no default on purpose. A source that cannot say when a
    status became publicly knowable cannot satisfy O-E-1, and defaulting it to
    `effective_from` would silently assert the very thing that needs proving.
    """
    stock_id: str
    status: str
    effective_from: str
    available_from: str
    reason: str
    source: str

    def __post_init__(self) -> None:
        if self.status not in SECURITY_STATUSES:
            raise MarketStateError(
                f"O-E/M-3: status {self.status!r} is not defined; "
                f"known statuses are {SECURITY_STATUSES}")
        if self.status == STATUS_UNKNOWN:
            raise MarketStateError(
                "O-E: 'unknown' is the ABSENCE of a record, not a filed status. "
                "Recording it as one would let an unknown state explain a gap.")
        for f in ("stock_id", "effective_from", "available_from", "source"):
            if not str(getattr(self, f)).strip():
                raise MarketStateError(f"O-E: StatusRecord requires {f}")
        if self.available_from < self.effective_from:
            # Legitimate for a pre-announced event (available earlier than it
            # binds); the reverse would be a filing that predates itself.
            pass

    def explains_session(self, session: str) -> bool:
        """O-E-1: strictly available BEFORE the session, and already in force."""
        return self.available_from < session and self.effective_from <= session


class SecurityStatusTable:
    def __init__(self, records: Iterable[StatusRecord], source: SourceContract):
        if source.kind != "security_status":
            raise MarketStateError(
                f"O-E: {source.name!r} is not a security_status source")
        source.assert_pit_safe()
        self.source = source
        self._by_id: dict[str, list[StatusRecord]] = {}
        for r in records:
            self._by_id.setdefault(r.stock_id, []).append(r)
        for k in self._by_id:
            self._by_id[k].sort(key=lambda r: (r.effective_from, r.available_from))

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_id.values())

    @property
    def securities(self) -> int:
        return len(self._by_id)

    def explaining_record(self, stock_id: str, session: str,
                          as_of: str) -> StatusRecord | None:
        """Latest non-trading status that explains `session`, known by `as_of`.

        Both bounds are applied: a record must have been available before the
        session began (O-E-1) AND must be knowable at as_of (plain PIT).
        """
        if session > as_of:
            raise MarketStateError(
                f"O-E: session {session} is after as_of {as_of}")
        best = None
        for r in self._by_id.get(stock_id, ()):
            if r.available_from > as_of:
                continue                      # not yet knowable at as_of
            if not r.explains_session(session):
                continue
            # A later `listed` record (a resumption) must be able to cancel an
            # earlier suspension, so every status competes for "latest in force"
            # and only then is it asked whether it is a non-trading one.
            if best is None or (r.effective_from, r.available_from) >= (
                    best.effective_from, best.available_from):
                best = r
        if best is None or best.status not in NON_TRADING_STATUSES:
            return None
        return best

    def status_is_known(self, stock_id: str) -> bool:
        return stock_id in self._by_id


def assert_unknown_is_not_normal(stock_id: str, table: SecurityStatusTable,
                                 has_price_gap: bool) -> None:
    """`unknown` must never be silently promoted to `listed`.

    Absence of a record is only harmless while there is nothing to explain; the
    moment a gap exists, an unknown status is a gap with no account of itself.
    """
    if has_price_gap and not table.status_is_known(stock_id):
        raise MarketStateError(
            f"O-E: {stock_id} has a price gap and no status record at all. "
            f"'unknown' is not 'trading normally' — an absent record explains "
            f"nothing and must not be read as an explanation."
        )


# --- 4. provenance ------------------------------------------------------------

def market_state_provenance(*sources: SourceContract) -> tuple:
    for s in sources:
        s.assert_pit_safe()
    return tuple(s.to_dataset_provenance() for s in sources)


def assert_sources_registered(required_kinds: Sequence[str],
                              sources: Mapping[str, SourceContract]) -> None:
    missing = [k for k in required_kinds
               if not any(s.kind == k for s in sources.values())]
    if missing:
        raise MarketStateError(
            f"O-E: no registered source for {missing}. B0 must not infer a "
            f"trading calendar or a security status from the price data it is "
            f"trying to validate.")
