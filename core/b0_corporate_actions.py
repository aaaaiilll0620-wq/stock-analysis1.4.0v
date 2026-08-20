"""W-1..W-4 · Corporate-action closure for Frozen B0.

Completion condition (user ruling):

    Every corporate action that changes B0's actual holdings / cash / security
    identity must have a canonical handler. Where the event data is insufficient,
    the run must fail loudly *at the moment the portfolio is actually exposed to
    that event* — it must never silently produce a NAV.

Two ideas make that enforceable and they are deliberately separated:

  1. **Reconstructibility is a per-event property, decided by the data.** Three
     states, never two: RECONSTRUCTIBLE / NOT_RECONSTRUCTIBLE / NOT_APPLICABLE.
     pass/fail cannot distinguish "the system knows it cannot rebuild this event"
     from "the system never noticed the event existed" — and at final-seal time
     that difference is the whole point.

  2. **Exposure, not existence, is what aborts.** 65 stock dividends in the
     window have no credit date. If B0 never held those names on those dates,
     they are irrelevant; if it did, the share ledger is wrong and no NAV may be
     produced. Deciding at exposure time is what makes W-1's "no interpolation,
     no missing-rate threshold" affordable.

W-1  missing credit date  -> per-event NOT_RECONSTRUCTIBLE, abort on exposure.
     No interpolation. No missing-rate threshold anywhere in this module.
W-2  credit == ex-right   -> legal zero-day receivable. Only credit < ex fails.
W-3  every share-changing event enters the ledger, each with its own verifier.
W-4  B0 never subscribes to a cash capital increase. Fixed False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


class CorporateActionError(RuntimeError):
    """Fail-loud: B0 is exposed to an event it cannot reconstruct."""


# --- three-state reconstructibility ------------------------------------------

RECONSTRUCTIBLE = "RECONSTRUCTIBLE"
NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE"
NOT_APPLICABLE = "NOT_APPLICABLE"

RECONSTRUCTIBILITY_STATES: tuple[str, ...] = (
    RECONSTRUCTIBLE, NOT_RECONSTRUCTIBLE, NOT_APPLICABLE,
)


# --- W-4 · cash capital increase ---------------------------------------------
# Ruling: B0 never subscribes. This is a policy constant, not a strategy state:
# a subscription decision would add a sizing rule, a funding rule and a timing
# rule, all unpreregistered. Not subscribing keeps our share count unchanged, so
# the event degrades to dilution already carried in the market price.
CASH_CAPITAL_INCREASE_SUBSCRIBE: bool = False


def assert_never_subscribes(subscribe: bool) -> None:
    if subscribe != CASH_CAPITAL_INCREASE_SUBSCRIBE:
        raise CorporateActionError(
            "W-4: B0 never subscribes to a cash capital increase; "
            f"got subscribe={subscribe!r}. This is frozen policy and is not "
            "selectable from strategy state."
        )


# --- W-2 · receivable ordering -----------------------------------------------
# Ruling: credit_date == ex_right_date is a legal zero-day receivable. Only a
# credit date strictly BEFORE ex-right is impossible and must fail.
ZERO_DAY_RECEIVABLE_ALLOWED: bool = True


def classify_receivable_ordering(ex_right: str | None, credit: str | None) -> str:
    """'ok' | 'zero_day' | 'missing' | 'before_ex'."""
    if ex_right is None:
        return "no_ex_right"
    if credit is None:
        return "missing"
    if credit > ex_right:
        return "ok"
    if credit == ex_right:
        return "zero_day"
    return "before_ex"


# --- event taxonomy -----------------------------------------------------------

@dataclass(frozen=True)
class EventKind:
    key: str
    source_column: str
    changes_our_shares: bool
    changes_our_cash: bool
    changes_security_identity: bool
    note: str


# Split by the only question that matters to a share ledger: does it change what
# WE hold? A convertible-bond conversion is the largest event class in the corpus
# (8,049 in window) and changes none of our three quantities — the dilution is
# already in the market price. Counting it would be activity, not accounting.
EVENT_KINDS: tuple[EventKind, ...] = (
    EventKind("stock_dividend", "盈餘增資(仟股)+公積增資(仟股)", True, False, False,
              "receivable shares credited at 上市日/發放日"),
    EventKind("capital_reduction", "減資(仟股)", True, True, False,
              "shares cancelled; may return cash per share"),
    # B0.3 · R1/R2/R5. These two were the conflation. The source export is a
    # PER-SECURITY share-formation table -- one row per 證券代碼 + 年月日, carrying
    # that security's own 總股數(仟股) and the deltas that compose it -- so
    # 合併(仟股) (tr_fg1) and 股份轉換(仟股 (con3) are shares THIS security
    # ISSUED because another company disappeared into it. For a holder of the
    # surviving/issuing security that is capital formation, not a conversion:
    # the share count is untouched and the dilution is already in the price,
    # exactly as for 証券轉換_可轉債 and 現金增資 below.
    #
    # Modelling them as holder-side identity changes is what made every one of
    # them demand a successor security and a ratio the issuer-side row never
    # had, and what aborted the B0.2 replay on a security B0 held as SURVIVOR.
    EventKind("issuer_side_merger_share_issuance", "合併(仟股)", False, False, False,
              "shares issued by the surviving company because another company "
              "merged into it; a holder of the survivor is diluted, not converted"),
    EventKind("issuer_side_share_conversion_issuance", "股份轉換(仟股", False, False,
              False,
              "shares issued by this company for a share conversion; issuer-side "
              "capital formation unless provenance proves the row is the "
              "disappearing-security leg"),
    # R3. The holder-side leg is a DIFFERENT event on a DIFFERENT security -- the
    # one that disappears. It is declared here so the model can express it and so
    # a genuinely exposed holder still fails loud; the corpus carries no such
    # rows today, and none may be synthesised (R6/R7).
    EventKind("holder_side_security_conversion", "<disappearing-security lineage>",
              True, True, True,
              "the disappearing security converts into a successor; requires the "
              "conversion terms and is NOT_RECONSTRUCTIBLE without them"),
    # B0.4. What the corpus DOES establish about a disappearance, and nothing
    # more. security_status states that a listed security stopped trading and why;
    # it does not state what the holder received. Representing that as a
    # stock-to-stock conversion would be inventing terms, and representing it as
    # nothing at all is what left 98 boundaries silently uncovered. So this kind
    # carries identity + boundary + authoritative reason, and its reconstruction
    # status is NOT_RECONSTRUCTIBLE by construction.
    EventKind("holder_side_reorganization_exit",
              "security_status.reason (合併下市 / 併入控股公司下市)",
              True, True, True,
              "a listed security ceased trading through a reorganization; the "
              "holder outcome is not established by this source"),
    EventKind("par_value_change", "變更股票面額股數(仟股)", True, False, False,
              "share count scales by old_par/new_par; no P&L"),
    EventKind("cash_capital_increase", "現金增資(仟股)", False, False, False,
              "W-4: never subscribed, therefore our shares never change"),
    EventKind("convertible_bond_conversion", "証券轉換_可轉債(仟股)", False, False, False,
              "issuer total shares only; dilution already in price"),
    EventKind("treasury_cancellation", "庫藏股註銷(仟股)", False, False, False,
              "issuer total shares only"),
    EventKind("employee_bonus", "員工分紅(仟股)", False, False, False,
              "issuer total shares only"),
    EventKind("transfer_in", "受讓(仟股)", False, False, False,
              "issuer total shares only"),
    EventKind("other_share_change", "其它(仟股)", False, False, False,
              "issuer total shares only"),
)

EVENT_KIND_BY_KEY: dict[str, EventKind] = {e.key: e for e in EVENT_KINDS}


def holder_affecting_kinds() -> tuple[str, ...]:
    return tuple(e.key for e in EVENT_KINDS
                 if e.changes_our_shares or e.changes_our_cash
                 or e.changes_security_identity)


# --- canonical handler registry ----------------------------------------------
# Fail-loud registry, same shape as B-19: an unregistered holder-affecting kind
# aborts rather than defaulting to "ignore". Silence is the failure mode this
# whole closure exists to remove.

_HANDLERS: dict[str, str] = {}


def register_handler(kind: str, handler_name: str) -> None:
    if kind not in EVENT_KIND_BY_KEY:
        raise CorporateActionError(f"W-3: unknown corporate-action kind {kind!r}")
    _HANDLERS[kind] = handler_name


def registered_handlers() -> Mapping[str, str]:
    return dict(_HANDLERS)


def assert_every_holder_affecting_kind_has_a_handler() -> None:
    missing = [k for k in holder_affecting_kinds() if k not in _HANDLERS]
    if missing:
        raise CorporateActionError(
            f"W-3: corporate-action kinds change B0 holdings/cash/identity but "
            f"have no canonical handler: {missing}. An unhandled event is a "
            f"silent NAV error, so this aborts rather than defaulting to ignore."
        )


# --- the events themselves ----------------------------------------------------

@dataclass(frozen=True)
class CorporateActionEvent:
    stock_id: str
    kind: str
    ex_or_effective_date: str
    reconstructibility: str
    reason: str = ""
    # populated only when RECONSTRUCTIBLE
    credit_tradable_date: str | None = None
    new_shares_thousands: float | None = None
    share_multiplier: float | None = None       # par change / reduction survival
    cash_per_share: float | None = None
    cash_payment_date: str | None = None
    zero_day_receivable: bool = False
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    # §6.1.5 · the dates and identities a state transition needs. Defaulted so
    # that the classification-only call sites that predate §6.1 keep working;
    # `assert_transition_fields_present` is what makes them mandatory at the
    # moment a transition is actually attempted on an exposed holding.
    event_id: str = ""
    knowledge_ts: str | None = None
    successor_security_id: str | None = None
    stock_ratio: object | None = None           # Fraction: new shares per old

    def __post_init__(self) -> None:
        if self.reconstructibility not in RECONSTRUCTIBILITY_STATES:
            raise CorporateActionError(
                f"reconstructibility must be one of {RECONSTRUCTIBILITY_STATES}, "
                f"got {self.reconstructibility!r}"
            )
        if self.reconstructibility == NOT_RECONSTRUCTIBLE and not self.reason:
            raise CorporateActionError(
                f"{self.stock_id}/{self.kind}: NOT_RECONSTRUCTIBLE requires a "
                f"reason — an unexplained gap is indistinguishable from an "
                f"unnoticed event"
            )

    @property
    def cash_available_date(self) -> str | None:
        """§6.1.5 name for the date a cash claim becomes spendable."""
        return self.cash_payment_date

    def canonical_event_id(self) -> str:
        """Deterministic and stable (I-CA-01/I-CA-12).

        Derived from the event's own identifying facts rather than from a row
        number or an insertion order, so the same event in a rebuilt corpus is
        the same event and cannot be applied twice under two names.
        """
        if self.event_id:
            return self.event_id
        return "%s|%s|%s" % (self.stock_id, self.kind, self.ex_or_effective_date)


# --- exposure gate ------------------------------------------------------------

@dataclass(frozen=True)
class Exposure:
    """What B0 actually held, per security, over a date interval."""
    stock_id: str
    held_from: str
    held_until: str            # inclusive

    def covers(self, date: str) -> bool:
        return self.held_from <= date <= self.held_until


def exposed_unreconstructible_events(
    events: Iterable[CorporateActionEvent],
    state,
    *,
    as_of: str,
) -> list[CorporateActionEvent]:
    """Events B0 was actually exposed to and cannot reconstruct.

    B0.1 · R2/R3: the exposure comes from the canonical state, not from an
    `Exposure` the caller assembled. The retrospective adapter built those from
    the LISTING SPELL, which made B0 look exposed to a security's entire history
    from the day it listed — so even this gate, which had the right interval
    semantics all along, was being fed the wrong interval.
    B0.7 / R5: and the exposure is now the COMBINED economic interest. An
    outstanding claim denominated in S remains an economic interest in S when
    the underlying share count is zero, so a NOT_RECONSTRUCTIBLE holder-side
    event on S fails loud here rather than surfacing later as a price gap.
    """
    hit = []
    for ev in events:
        if ev.reconstructibility != NOT_RECONSTRUCTIBLE:
            continue
        if ca_economic_interest_applies(state, ev, as_of=as_of):
            hit.append(ev)
    return hit


def assert_caller_exposures_conform(exposures, state, as_of: str = "") -> None:
    """B0.1 · R2, corrected by B0.2 · R2. A caller may declare; it may not DEFINE.

    The retrospective adapter declared `held_from = <listing spell start>`, so
    B0 looked exposed to every corporate action a security ever had. Keeping the
    field as a checked redundancy — rather than deleting it — turns that class of
    mistake into a fail-loud mismatch instead of a silent economic input.

    B0.2 · R2 fixes WHICH canonical set it is redundant against. This compared a
    caller's CURRENT exposure declaration against `exposure_spells()`, the
    COMPLETE historical ledger. Those sets are equal only while no position has
    ever been fully exited: the first exit leaves a closed spell in the ledger
    that no current declaration can legitimately contain, and the assertion then
    fails forever. It is a domain mismatch between two of the three concepts R2
    separates, not a disagreement about any economic quantity — no interval rule,
    no event, no claim and no NAV is involved.

    The comparison is now against `active_exposure_projection(as_of)`. Closed
    spells stay in the ledger and stay available to `exposure_applies`, which is
    frozen and untouched; they are simply not a CURRENT exposure for a caller to
    declare. On exit-then-re-entry the caller declares the re-entry spell only,
    while the ledger keeps both — so an event belonging to the earlier spell can
    still never be replayed onto the later position.
    """
    when = str(as_of or getattr(state, "as_of", "") or "")
    declared = {(x.stock_id, str(x.held_from)) for x in (exposures or ())}
    canonical = {(sp.stock_id, str(sp.start))
                 for sp in state.active_exposure_projection(when)}
    if declared and declared != canonical:
        only_caller = sorted(declared - canonical)[:5]
        only_state = sorted(canonical - declared)[:5]
        raise CorporateActionError(
            f"B0.2/R2: caller-declared exposure disagrees with the canonical "
            f"holding-spell ledger. caller-only={only_caller} "
            f"state-only={only_state}. Exposure is a property of what B0 held, "
            f"not of what the caller believes it held.")


def economic_interest_securities(state) -> tuple[str, ...]:
    """B0.7 / R10 - the securities a corporate action could reach.

    Delegates to the frozen `entitlement_securities`, which already is exactly
    the §6.1.12 list: tradable position, security receivable, the source
    security a claim came from, and unresolved pending exits. It is named here
    because the two consumers of the event carrier disagreed about scope - the
    transition engine was fed events for `entitlement_securities` while
    `build_input` assembled the carrier from `held_securities`, which is
    narrower. One name, read by both, is what removes the disagreement.
    """
    return tuple(state.entitlement_securities)


def deliver_ca_events(events_by_sid, state, *, as_of: str):
    """R10: every PIT-available event on an economic interest, exactly once.

    Delivery is NOT a global broadcast (R9 withdrew that): an event for a
    security the portfolio has no economic interest in has nothing to reach, and
    the B0.7 audit showed the previous carrier already delivered without a
    current market row. What delivery must not depend on is market-row presence,
    selection universe, eligibility, ranking - and it does not, because this
    reads the portfolio and the event ledger and nothing else.
    """
    seen, out = set(), []
    for sid in economic_interest_securities(state):
        for ev in events_by_sid.get(sid, ()):
            if str(ev.ex_or_effective_date) > str(as_of):
                continue                       # not PIT-available yet (R5)
            # A claim names both its own security and the source it came
            # from, so one event can be reached twice through one portfolio.
            key = ev.canonical_event_id()
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    return tuple(out)


def assert_ca_event_delivery_conforms(delivered, state, *, as_of: str) -> None:
    """R10, as a gate on what actually arrived at the CA consumer.

    Checks the half that is answerable without the source ledger: no duplicate
    reaches the engine, and nothing arrives before the frozen PIT rule allows.
    The other half - undelivered = 0 - holds by construction in
    `deliver_ca_events` and is measured over the whole window by the B0.7
    delivery audit.

    Delivery scope is a FLOOR, never a ceiling. An earlier draft of this gate
    also rejected events for securities the portfolio has no interest in, and
    `test_an_event_we_never_held_does_not_abort` failed within the minute:
    §6.1.12 says `NOT_RECONSTRUCTIBLE + zero exposure -> log as irrelevant ->
    continue`, so an event with nothing to reach is a documented no-op and not
    an error. What must never happen is the opposite - a required event that
    does not arrive.
    """
    ids = [e.canonical_event_id() for e in delivered]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise CorporateActionTransitionError(
            f"R10: {len(dupes)} corporate-action event(s) reached the engine "
            f"more than once: {dupes[:5]}. I-CA-01 makes exactly-once an "
            f"economic property, so a duplicated delivery is a defect even when "
            f"`applied_ca_event_ids` happens to absorb it.")
    early = sorted({e.canonical_event_id() for e in delivered
                    if str(e.ex_or_effective_date) > str(as_of)})
    if early:
        raise CorporateActionTransitionError(
            f"R10/R5: {len(early)} event(s) not yet PIT-available at {as_of} "
            f"reached the engine: {early[:5]}. Coverage means every event the "
            f"frozen PIT rule already allows, never every future event.")


def assert_exposure_reconstructible(
    events: Iterable[CorporateActionEvent],
    state,
    *,
    as_of: str,
) -> None:
    """Abort before any NAV is produced for a position we cannot account for."""
    hit = exposed_unreconstructible_events(events, state, as_of=as_of)
    if hit:
        detail = "; ".join(
            f"{e.stock_id} {e.kind} {e.ex_or_effective_date} ({e.reason})" for e in hit[:10])
        more = f" and {len(hit) - 10} more" if len(hit) > 10 else ""
        raise CorporateActionError(
            f"W-1/W-3: B0 held {len(hit)} position(s) through a corporate action "
            f"it cannot reconstruct: {detail}{more}. No NAV may be produced. "
            f"Interpolation and ratio inference are not permitted."
        )


# --- holder-side identity changes are unobservable here ----------------------
# Mergers and share conversions are recorded ONLY on the surviving/issuing
# entity, with no counterparty column in the corpus (verified: no 換股/被/存續/
# 消滅 column exists among the 33). So if B0 holds the entity that DISAPPEARS,
# no row here will ever match it, and this module cannot detect the exposure.
#
# The holder-side detector lives in core.b0_pit_observability instead, and is
# deliberately NOT phrased as "the position disappeared": that is a statement
# about the future. It asks the only PIT-answerable question — standing at
# `as_of`, is there a price gap nothing known through `as_of` explains?
# (O-B, closed in P-1a. The earlier `assert_no_unexplained_disappearance`, which
# took a global last_price_date lookup, was removed for encoding look-ahead in
# its own signature.)
HOLDER_SIDE_DETECTOR = "core.b0_pit_observability.assert_no_unexplained_price_gap"


# --- canonical handlers -------------------------------------------------------
# Each takes an already-normalised record (source parsing lives in the importer,
# not here) and returns the three-state classification. Every handler is written
# so that the ONLY way to reach RECONSTRUCTIBLE is for the required quantities to
# be present and to reconcile — never by falling through.

def _f(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == ".":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _d(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def handle_stock_dividend(rec: Mapping[str, object]) -> CorporateActionEvent:
    """W-1 + W-2. Needs an ex-right date, a share quantity and a credit date."""
    sid, ex = str(rec.get("stock_id", "")), _d(rec.get("ex_right_date"))
    new_shares = _f(rec.get("new_shares_thousands"))
    ratio = _f(rec.get("distribution_ratio_pct"))
    credit = _d(rec.get("credit_tradable_date"))
    is_ex_right_event = bool(rec.get("is_ex_right_event", True))

    if ex is None:
        return CorporateActionEvent(sid, "stock_dividend", "", NOT_RECONSTRUCTIBLE,
                                    "no ex-right date")
    if not is_ex_right_event:
        # 配股(Y/N)='N' rows carry new shares but no 配股率 and no credit date,
        # and their 年月日 is a month-end registration stamp, not an ex-right day.
        # Treating them as ex-right stock dividends would invent an event date.
        return CorporateActionEvent(
            sid, "stock_dividend", ex, NOT_RECONSTRUCTIBLE,
            "capitalisation recorded without an ex-right flag: no distribution "
            "rate and no credit date; 年月日 is a registration stamp",
            new_shares_thousands=new_shares)

    order = classify_receivable_ordering(ex, credit)
    if order == "before_ex":
        return CorporateActionEvent(sid, "stock_dividend", ex, NOT_RECONSTRUCTIBLE,
                                    f"credit date {credit} precedes ex-right {ex}")
    if order == "missing":
        # W-1: per event, no interpolation, no threshold.
        return CorporateActionEvent(sid, "stock_dividend", ex, NOT_RECONSTRUCTIBLE,
                                    "no 股票股利上市日/發放日 — the receivable has no "
                                    "observable credit date",
                                    new_shares_thousands=new_shares)
    if new_shares is None and ratio is None:
        return CorporateActionEvent(sid, "stock_dividend", ex, NOT_RECONSTRUCTIBLE,
                                    "neither new-share count nor distribution rate")
    return CorporateActionEvent(
        sid, "stock_dividend", ex, RECONSTRUCTIBLE,
        credit_tradable_date=credit,
        new_shares_thousands=new_shares,
        zero_day_receivable=(order == "zero_day"),
        diagnostics={"distribution_ratio_pct": ratio, "ordering": order})


def handle_capital_reduction(rec: Mapping[str, object]) -> CorporateActionEvent:
    """Shares cancelled, optionally returning cash. Both legs must be datable."""
    sid = str(rec.get("stock_id", ""))
    eff = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date"))
    rate = _f(rec.get("reduction_rate_pct"))
    cash_ps = _f(rec.get("cash_per_share")) or 0.0
    cash_date = _d(rec.get("cash_payment_date"))

    if eff is None:
        return CorporateActionEvent(sid, "capital_reduction", "", NOT_RECONSTRUCTIBLE,
                                    "no 除權減資基準日")
    if rate is None:
        return CorporateActionEvent(sid, "capital_reduction", eff, NOT_RECONSTRUCTIBLE,
                                    "no reduction rate and it could not be derived "
                                    "from share counts on this row")
    if cash_ps > 0 and cash_date is None:
        # Cash without a date cannot be placed in the NAV series at all.
        return CorporateActionEvent(sid, "capital_reduction", eff, NOT_RECONSTRUCTIBLE,
                                    f"returns {cash_ps} per share but carries no "
                                    f"減資現金退款日")
    return CorporateActionEvent(
        sid, "capital_reduction", eff, RECONSTRUCTIBLE,
        share_multiplier=1.0 - rate / 100.0,
        cash_per_share=cash_ps or None,
        cash_payment_date=cash_date,
        diagnostics={"reduction_rate_pct": rate})


def _identity_change_unobservable(kind: str, rec: Mapping[str, object]) -> CorporateActionEvent:
    sid = str(rec.get("stock_id", ""))
    eff = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date")) or ""
    return CorporateActionEvent(
        sid, kind, eff, NOT_RECONSTRUCTIBLE,
        "recorded only on the surviving/issuing entity; the corpus carries no "
        "counterparty security and no conversion ratio, so the holder-side leg "
        "cannot be rebuilt")


def _issuer_side_share_issuance(kind: str, rec: Mapping[str, object],
                                note: str) -> CorporateActionEvent:
    """B0.3 · R2/R5. Issuer-side capital formation. Our shares do not move.

    Deliberately the same shape as the convertible-bond and cash-increase
    handlers, because it is the same economics: the issuer's total share count
    changed, ours did not, and the dilution is in the price.
    """
    sid = str(rec.get("stock_id", ""))
    eff = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date")) or ""
    return CorporateActionEvent(sid, kind, eff, NOT_APPLICABLE, note)


def handle_issuer_side_merger_share_issuance(
        rec: Mapping[str, object]) -> CorporateActionEvent:
    return _issuer_side_share_issuance(
        "issuer_side_merger_share_issuance", rec,
        "issuer-side only: shares issued by the surviving company on a merger; "
        "the holder of the survivor is diluted, not converted")


def handle_issuer_side_share_conversion_issuance(
        rec: Mapping[str, object]) -> CorporateActionEvent:
    return _issuer_side_share_issuance(
        "issuer_side_share_conversion_issuance", rec,
        "issuer-side only: shares issued by this company for a share conversion")


def handle_holder_side_reorganization_exit(
        rec: Mapping[str, object]) -> CorporateActionEvent:
    """B0.4 · a KNOWN disappearance with an UNKNOWN holder outcome.

    Deliberately unable to reach RECONSTRUCTIBLE. The successor, ratio, cash
    consideration and credit date are not merely absent from this record -- they
    are not established by the source it comes from, and a future repair that
    obtains them from authoritative disclosures should emit a
    `holder_side_security_conversion`, not quietly upgrade this one.

    The date carried here is the DISAPPEARANCE / non-trading boundary, which is
    what the status corpus actually establishes. It is explicitly NOT a claimed
    holder economic effective, settlement, credit or payment date; those stay
    null. Its meaning is "once a held position reaches this point, continuing
    requires a reconstructible holder outcome".
    """
    sid = str(rec.get("stock_id", ""))
    boundary = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date")) or ""
    reason = str(rec.get("status_reason", "") or "").strip()
    return CorporateActionEvent(
        sid, "holder_side_reorganization_exit", boundary, NOT_RECONSTRUCTIBLE,
        "authoritative status reason %r establishes that this listed security "
        "ceased trading through a reorganization; it does not establish the "
        "successor security, conversion ratio, cash consideration or credit "
        "date, so the holder outcome is not reconstructible from it" % reason,
        diagnostics={"boundary_kind": "holder_resolution_required_by_boundary",
                     "status_reason": reason,
                     "successor_security_id": None, "stock_ratio": None,
                     "cash_per_share": None, "credit_tradable_date": None})


def handle_holder_side_security_conversion(
        rec: Mapping[str, object]) -> CorporateActionEvent:
    """R3/R7. Terms or nothing -- and nothing means fail loud, not a guess."""
    sid = str(rec.get("stock_id", ""))
    eff = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date")) or ""
    successor = str(rec.get("successor_security_id", "") or "").strip()
    ratio = rec.get("stock_ratio")
    credit = _d(rec.get("credit_tradable_date"))
    if successor and ratio and credit:
        return CorporateActionEvent(
            sid, "holder_side_security_conversion", eff, RECONSTRUCTIBLE,
            successor_security_id=successor, stock_ratio=ratio,
            credit_tradable_date=credit,
            cash_per_share=rec.get("cash_per_share") or None)
    return CorporateActionEvent(
        sid, "holder_side_security_conversion", eff, NOT_RECONSTRUCTIBLE,
        "the disappearing security's conversion terms are not authoritatively "
        "determined; R7 forbids inferring them from issued-share counts, prices, "
        "market capitalisation, NAV continuity or holdings")





PAR_RECONCILE_TOL = 0.001        # share counts are reported in whole 仟股


def handle_par_value_change(rec: Mapping[str, object]) -> CorporateActionEvent:
    """Share count scales by old_par/new_par and must reconcile with the counts.

    Accepting the ratio without the reconciliation would let a bad par value
    silently rescale a position.
    """
    sid = str(rec.get("stock_id", ""))
    eff = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date"))
    old_par, new_par = _f(rec.get("old_par")), _f(rec.get("new_par"))
    changed = _f(rec.get("changed_shares_thousands"))
    total_after = _f(rec.get("total_shares_thousands"))

    if eff is None:
        return CorporateActionEvent(sid, "par_value_change", "", NOT_RECONSTRUCTIBLE,
                                    "no effective date")
    if not old_par or not new_par:
        return CorporateActionEvent(sid, "par_value_change", eff, NOT_RECONSTRUCTIBLE,
                                    "old or new par value unavailable")
    if changed is None or not total_after:
        return CorporateActionEvent(sid, "par_value_change", eff, NOT_RECONSTRUCTIBLE,
                                    "share counts unavailable")
    before = total_after - changed
    if before <= 0:
        return CorporateActionEvent(sid, "par_value_change", eff, NOT_RECONSTRUCTIBLE,
                                    f"implied pre-event shares {before:.0f} is not "
                                    f"positive; the row does not describe a rescale")
    expected = before * (old_par / new_par)
    err = abs(expected - total_after) / total_after
    if err > PAR_RECONCILE_TOL:
        return CorporateActionEvent(sid, "par_value_change", eff, NOT_RECONSTRUCTIBLE,
                                    f"par ratio {old_par}->{new_par} does not "
                                    f"reconcile with share counts (err={err:.4f})")
    return CorporateActionEvent(sid, "par_value_change", eff, RECONSTRUCTIBLE,
                                share_multiplier=old_par / new_par,
                                diagnostics={"reconcile_err": err})


def handle_cash_capital_increase(rec: Mapping[str, object]) -> CorporateActionEvent:
    """W-4: never subscribed, so our share count is untouched by construction."""
    assert_never_subscribes(bool(rec.get("subscribe", CASH_CAPITAL_INCREASE_SUBSCRIBE)))
    sid = str(rec.get("stock_id", ""))
    eff = _d(rec.get("effective_date")) or _d(rec.get("ex_right_date")) or ""
    return CorporateActionEvent(sid, "cash_capital_increase", eff, NOT_APPLICABLE,
                                "W-4: B0 never subscribes; our share count is unchanged")


HANDLER_FUNCS = {
    "stock_dividend": handle_stock_dividend,
    "capital_reduction": handle_capital_reduction,
    "issuer_side_merger_share_issuance": handle_issuer_side_merger_share_issuance,
    "issuer_side_share_conversion_issuance":
        handle_issuer_side_share_conversion_issuance,
    "holder_side_security_conversion": handle_holder_side_security_conversion,
    "holder_side_reorganization_exit": handle_holder_side_reorganization_exit,
    "par_value_change": handle_par_value_change,
    "cash_capital_increase": handle_cash_capital_increase,
}

for _kind, _fn in HANDLER_FUNCS.items():
    register_handler(_kind, _fn.__name__)


def classify(kind: str, rec: Mapping[str, object]) -> CorporateActionEvent:
    """Dispatch to the canonical handler, or abort. There is no default branch."""
    fn = HANDLER_FUNCS.get(kind)
    if fn is None:
        spec = EVENT_KIND_BY_KEY.get(kind)
        if spec is None:
            raise CorporateActionError(f"W-3: unknown corporate-action kind {kind!r}")
        return CorporateActionEvent(
            str(rec.get("stock_id", "")), kind,
            _d(rec.get("effective_date")) or _d(rec.get("ex_right_date")) or "",
            NOT_APPLICABLE, f"issuer-side only: {spec.note}")
    return fn(rec)


# --- explicit non-existence of a missing-rate threshold ----------------------
# W-1 forbids one. Naming its absence keeps a future "just allow 3%" from being
# added as an innocuous constant.
MISSING_DATA_RATE_THRESHOLD = None
INTERPOLATION_ALLOWED: bool = False


def assert_no_threshold_policy() -> None:
    if MISSING_DATA_RATE_THRESHOLD is not None or INTERPOLATION_ALLOWED:
        raise CorporateActionError(
            "W-1: corporate-action gaps are resolved per event at exposure time. "
            "A missing-rate threshold or interpolation would silently rebuild the "
            "very quantity that is missing."
        )


# =============================================================================
# §6.1 · CORPORATE ACTION STATE TRANSITION
# =============================================================================
# What was missing, and why its absence was not visible: every handler above
# returns a CorporateActionEvent — a CLASSIFICATION. Classifying an event is not
# applying it. A portfolio that went ex-rights yesterday and is marked today on
# pre-ex share counts produces a NAV that is wrong by exactly the entitlement,
# and nothing downstream can tell, because the number is well-formed.
#
# §6.1.2: this module is the sole dispatch authority. Everything below consumes
# a PortfolioState and returns a validated transformed PortfolioState, and no
# other module may branch on `kind`.
#
# The three quantities the transition keeps apart (§6.1.4):
#
#     owned      an economic claim exists            -> counts in NAV
#     tradable   execution may sell it               -> counts in `shares`
#     spendable  execution may fund a buy with it    -> counts in `cash`
#
# A stock dividend is owned at the ex-right session and tradable at the credit
# date. A capital-reduction refund is owned at the effective date and spendable
# at the payment date. Collapsing either pair lets execution sell shares that do
# not exist yet or spend money that has not arrived.

from fractions import Fraction                                    # noqa: E402


class CorporateActionTransitionError(CorporateActionError):
    """F-CA-C: an implementation/invariant failure during a transition."""


class CorporateActionReconstructionBlock(CorporateActionError):
    """F-CA-B: a NOT_RECONSTRUCTIBLE event on a holding B0 is exposed to.

    Distinct from `CorporateActionTransitionError` on purpose: one says the data
    cannot support the transition, the other says the code did the wrong thing.
    §6.1.14 gives them different formal outcomes and only one of them is ever a
    legitimate L2 result.
    """

    def __init__(self, message: str, *, detail: Mapping[str, object]):
        super().__init__(message)
        self.detail = dict(detail)


IDENTITY_CHANGING_KINDS: tuple[str, ...] = ("holder_side_security_conversion",
                                           "holder_side_reorganization_exit")
SAME_SECURITY_SHARE_KINDS: tuple[str, ...] = (
    "stock_dividend", "capital_reduction", "par_value_change")

# B0.7 / R4. The event kinds whose ALREADY-FROZEN transition acts on outstanding
# same-security claims, and therefore the only kinds that may use the claim
# applicability domain. This is a reading of §6.1.7, not a new rule:
#
#   A. stock_dividend       new claim = Q x r,  Q = entitlement-bearing shares
#   B. capital_reduction    post = Q x m; cash receivable = Q x c; and the
#                           outstanding same-security claims scale by m
#   C/D. merger / share_conversion (IDENTITY_CHANGING_KINDS)
#                           successor claim = Q x r, old-identity claims removed
#   E. par_value_change     Q_new = Q x P_old / P_new
#
# and §6.1.12 already names `security receivable` as affected economic exposure.
# In the code every one of those branches reads `entitlement`, which is
# `pre_shares + same_claims` (see `_apply_one`). Text and code agree on all
# five, so R4's M-3 escape is not needed - but the agreement is asserted
# MECHANICALLY rather than asserted here: `assert_claim_bearing_registry_conforms`
# probes each holder-affecting kind with a claim-only state and derives the set
# from what the transition actually does.
#
# The eight non-holder-affecting kinds are excluded structurally: they never
# reach `_apply_one` at all. A claim is NOT automatically eligible for every
# corporate action.
CLAIM_BEARING_EVENT_KINDS: tuple[str, ...] = (
    SAME_SECURITY_SHARE_KINDS + IDENTITY_CHANGING_KINDS)


@dataclass(frozen=True)
class TransitionRecord:
    """§6.1.17 · one immutable audit row per holder-affecting transition."""
    period: str
    event_id: str
    event_kind: str
    security_id: str
    successor_security_id: str | None
    knowledge_ts: str | None
    effective_date: str
    credit_tradable_date: str | None
    cash_available_date: str | None
    pre_tradable_shares: int
    post_tradable_shares: int
    created_security_receivables: tuple
    released_security_receivables: tuple
    created_cash_receivables: tuple
    released_cash: float
    pending_exit_before: int
    pending_exit_after: int
    reconstructibility: str
    blocking_reason: str | None
    pre_state_hash: str
    post_state_hash: str
    event_source_hash: str


@dataclass(frozen=True)
class CorporateActionTransitionResult:
    """The validated transformed state, plus everything needed to audit it."""
    state: object                                  # PortfolioState
    ledger: tuple                                  # tuple[TransitionRecord, ...]
    applied_event_ids: tuple
    skipped_unexposed: tuple                       # NOT_RECONSTRUCTIBLE, no exposure


def ca_economic_interest_applies(state, event: "CorporateActionEvent", *,
                                 as_of: str) -> bool:
    """B0.7 / R3 - THE applicability rule. Two domains, OR-combined.

        ca_economic_interest_applies
            = underlying_exposure_applies  OR  claim_interest_applies

    B0.1 gave exposure a time dimension and made the holding-spell ledger the
    single source of it. That was right and is untouched. What it did not carry
    is that a spell is the lifecycle of UNDERLYING SHARES, while §6.1.12 defines
    affected economic exposure more widely:

        affected economic exposure 包含 tradable position、security receivable、
        entitlement-bearing claim、unresolved pending-exit claim

    So a portfolio holding nothing but an uncreditable fractional claim in S is
    exposed to S by the frozen text and invisible to S's events in the code. The
    B0.6 replay died of exactly that: 27 such claims had accumulated, each one a
    marked NAV asset that no corporate action could reach, and the first one
    whose security disappeared surfaced as an unexplained price gap instead of
    as the reorganization it was.

    THE CLAIM IS NOT RENAMED INTO UNDERLYING EXPOSURE (R2/R3). No spell opens,
    reopens or extends; `holding_spells` still means what B0.1/R1 froze. The two
    domains are asked separately and only the ANSWER is combined.

    Only `CLAIM_BEARING_EVENT_KINDS` may use the second domain, because only
    those kinds have a frozen transition that acts on same-security claims.
    """
    if state.underlying_exposure_applies(
            event.stock_id, str(event.ex_or_effective_date), str(as_of)):
        return True
    if event.kind not in CLAIM_BEARING_EVENT_KINDS:
        return False
    return state.claim_interest_applies(event.stock_id,
                                        str(event.ex_or_effective_date))


def assert_claim_bearing_registry_conforms() -> None:
    """R4, mechanically. Derive the claim-bearing set from the transition itself.

    A hand-kept list of "kinds that consume same_claims" is a sentence that goes
    stale the first time a branch changes - the exact failure mode F0-R4 exists
    to close. So the set is DERIVED: probe each holder-affecting kind with a
    state that has zero shares and one claim, and see whether the transition's
    output depends on the claim being there.
    """
    from fractions import Fraction

    from core.b0_state import PortfolioState, SecurityReceivable

    sessions = tuple("2020-01-%02d" % d for d in range(1, 32))
    as_of, sid = "2020-01-15", "T001"
    probe_kwargs = {
        "stock_dividend": dict(stock_ratio=Fraction(1, 10),
                               credit_tradable_date="2020-01-20"),
        "capital_reduction": dict(share_multiplier=0.5, cash_per_share=3.0,
                                  cash_payment_date="2020-01-25"),
        "par_value_change": dict(share_multiplier=2.0),
        "holder_side_security_conversion": dict(
            successor_security_id="T002", stock_ratio=Fraction(1, 2),
            credit_tradable_date="2020-01-20"),
        "holder_side_reorganization_exit": dict(
            successor_security_id="T002", stock_ratio=Fraction(1, 2),
            credit_tradable_date="2020-01-20"),
    }

    def probe(kind, with_claim):
        claims = ()
        if with_claim:
            claims = (SecurityReceivable(
                security_id=sid, shares=Fraction(7, 4),
                credit_tradable_date="2030-01-01", event_id="seed|x|2019-01-01",
                origin_effective_date="2019-01-01"),)
        state = PortfolioState(as_of=as_of, cash=0.0, shares={},
                               security_receivables=claims)
        ev = CorporateActionEvent(sid, kind, as_of, RECONSTRUCTIBLE,
                                  knowledge_ts=as_of,
                                  **probe_kwargs.get(kind, {}))
        post, _ = _apply_one(state, ev, as_of, sessions)
        return _state_hash(post)

    derived = []
    for kind in holder_affecting_kinds():
        if kind not in probe_kwargs:
            raise CorporateActionError(
                f"R4: holder-affecting kind {kind!r} has no probe, so whether it "
                f"consumes same-security claims was never determined. A kind "
                f"nobody probed is a kind nobody knows the answer for.")
        if probe(kind, True) != probe(kind, False):
            derived.append(kind)
    if tuple(sorted(derived)) != tuple(sorted(CLAIM_BEARING_EVENT_KINDS)):
        raise CorporateActionError(
            f"R4: CLAIM_BEARING_EVENT_KINDS declares "
            f"{tuple(sorted(CLAIM_BEARING_EVENT_KINDS))} but the frozen "
            f"transitions actually consume same-security claims for "
            f"{tuple(sorted(derived))}. The declaration and the code disagree "
            f"about which events reach a claim.")


def is_exposed(state, event: "CorporateActionEvent", *, as_of: str) -> bool:
    """B0.1 · §6.1.12 exposure, delegated to THE canonical predicate.

    Membership was never the question. `event.stock_id in entitlement_securities`
    answers "does B0 hold this security NOW", and the official Frozen B0 L2 run
    aborted because that returned True for a 2012 event against a position opened
    in 2014. The question §2.5 W-1 actually asks is whether B0's holding interval
    covers the event boundary, and R1 adds the state that can answer it.

    B0.7 / R3 corrects the second half of that. Claims are still not UNDERLYING
    exposure - no spell opens for one - but §6.1.12 counts a security receivable
    as affected economic exposure, and the frozen transitions in §6.1.7 all act
    on `pre_shares + same_claims`. So this delegates to the combined rule.
    """
    return ca_economic_interest_applies(state, event, as_of=as_of)


REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "stock_dividend": ("stock_ratio", "credit_tradable_date"),
    "capital_reduction": ("share_multiplier",),
    "holder_side_security_conversion": ("successor_security_id", "stock_ratio",
                                       "credit_tradable_date"),
    "_retired_share_conversion": ("successor_security_id", "stock_ratio",
                         "credit_tradable_date"),
    "par_value_change": ("share_multiplier",),
}


def assert_transition_fields_present(event: "CorporateActionEvent") -> None:
    """§6.1.7: a transition may not proceed on a partially specified event.

    Checked at transition time rather than at classification time, because an
    event nobody is exposed to never needs these fields (§6.1.12).
    """
    missing = [f for f in REQUIRED_FIELDS.get(event.kind, ())
               if getattr(event, f, None) in (None, "")]
    if event.kind == "capital_reduction" and event.cash_per_share:
        if not event.cash_available_date:
            missing.append("cash_available_date")
    if missing:
        raise CorporateActionReconstructionBlock(
            "§6.1.7: %s/%s on %s cannot be transitioned: missing %s"
            % (event.stock_id, event.kind, event.ex_or_effective_date, missing),
            detail={"security_id": event.stock_id, "event_kind": event.kind,
                    "event_id": event.canonical_event_id(),
                    "effective_date": event.ex_or_effective_date,
                    "missing_fields": missing})


def assert_no_look_ahead(event: "CorporateActionEvent", cutoff: str) -> None:
    """I-CA-06: a transition may not use information that was not knowable."""
    if event.knowledge_ts and str(event.knowledge_ts) > str(cutoff):
        raise CorporateActionTransitionError(
            "I-CA-06: %s/%s became knowable at %s, after the evaluation cutoff "
            "%s. Applying it now is look-ahead."
            % (event.stock_id, event.kind, event.knowledge_ts, cutoff))




def _state_hash(state) -> str:
    """I-CA-12: byte-equivalent states hash identically."""
    from core.b0_canonical_hash import canonical_sha256

    return canonical_sha256({
        "as_of": state.as_of,
        "cash": state.cash,
        "shares": dict(sorted(state.shares.items())),
        "pending_exit": dict(sorted(state.pending_exit.items())),
        "cash_dividend_receivable": state.cash_dividend_receivable,
        "stock_dividend_receivable": dict(
            sorted(state.stock_dividend_receivable.items())),
        "security_receivables": sorted(
            [[r.security_id, str(r.shares), r.credit_tradable_date, r.event_id,
              r.source_security_id, r.origin_effective_date]
             for r in state.security_receivables]),
        "cash_receivables": sorted(
            [[r.amount, r.cash_available_date, r.event_id, r.source_security_id]
             for r in state.cash_receivables]),
        "applied_ca_event_ids": sorted(state.applied_ca_event_ids),
        "pending_exit_on_receivable": sorted(state.pending_exit_on_receivable),
    })


def _event_hash(event: "CorporateActionEvent") -> str:
    from core.b0_canonical_hash import canonical_sha256

    return canonical_sha256([
        event.stock_id, event.kind, event.ex_or_effective_date,
        event.reconstructibility, event.credit_tradable_date,
        str(event.stock_ratio) if event.stock_ratio is not None else None,
        event.share_multiplier, event.cash_per_share, event.cash_payment_date,
        event.successor_security_id, event.knowledge_ts,
    ])


def _first_session_on_or_after(date: str, sessions: Sequence[str]) -> str:
    """§6.1.6: a claim matures on the first eligible portfolio-state timestamp."""
    for s in sessions:
        if str(s) >= str(date):
            return str(s)
    raise CorporateActionReconstructionBlock(
        "§6.1.6: no portfolio-state timestamp on or after %s; the release point "
        "is outside the canonical calendar" % date,
        detail={"date": date})


# --- §6.1.6 step 1/3 - releasing matured claims --------------------------------

def _release_matured(state, as_of: str):
    """Security claims that became tradable and cash claims that became spendable.

    §6.1.9: only the INTEGRAL part of a claim can become a tradable share. Any
    remainder stays a claim rather than being rounded away - a rounded
    entitlement is an entitlement that silently ceased to exist.
    """
    from core.b0_state import PortfolioState, SecurityReceivable

    shares = dict(state.shares)
    pending = dict(state.pending_exit)
    on_recv = set(state.pending_exit_on_receivable)
    kept_sec, released_sec = [], []
    for r in state.security_receivables:
        if str(r.credit_tradable_date) > str(as_of):
            kept_sec.append(r)
            continue
        whole = int(r.shares)
        rest = r.shares - whole
        if whole:
            shares[r.security_id] = shares.get(r.security_id, 0) + whole
            released_sec.append((r.security_id, whole, r.event_id))
            # §6.1.10: an exit obligation carried on the claim becomes a real
            # pending exit the moment the shares exist.
            if r.security_id in on_recv:
                pending[r.security_id] = shares[r.security_id]
        if rest > 0:
            # The remainder is still owned. It is not tradable and it is not
            # discarded; it stays until official settlement semantics exist.
            kept_sec.append(SecurityReceivable(
                security_id=r.security_id, shares=rest,
                credit_tradable_date=r.credit_tradable_date,
                event_id=r.event_id, source_security_id=r.source_security_id,
                # B0.7/R8: a remainder is the SAME claim, partially released.
                # Restamping it with today would make it younger than the event
                # that created it and hide it from that event's own successors.
                origin_effective_date=r.origin_effective_date))
        elif whole and r.security_id in on_recv:
            on_recv.discard(r.security_id)

    cash = float(state.cash)
    kept_cash, released_cash = [], 0.0
    for r in state.cash_receivables:
        if str(r.cash_available_date) > str(as_of):
            kept_cash.append(r)
        else:
            cash += float(r.amount)
            released_cash += float(r.amount)

    new = PortfolioState(
        as_of=state.as_of, cash=cash, shares=shares, pending_exit=pending,
        cash_dividend_receivable=state.cash_dividend_receivable,
        stock_dividend_receivable=dict(state.stock_dividend_receivable),
        security_receivables=tuple(kept_sec), cash_receivables=tuple(kept_cash),
        applied_ca_event_ids=frozenset(state.applied_ca_event_ids),
        pending_exit_on_receivable=frozenset(on_recv),
        # B0.1: a corporate action never opens or closes a holding spell.
        # Spells are driven by actual acquisition and exit; carrying the
        # ledger unchanged is what stops a transition fabricating exposure.
        holding_spells=tuple(state.holding_spells))
    return new, tuple(released_sec), released_cash


# --- §6.1.7 - the transition table ---------------------------------------------

def _apply_one(state, event: "CorporateActionEvent", as_of: str,
               sessions: Sequence[str]):
    """One holder-affecting event -> transformed state + audit fields.

    Atomic (I-CA-13): the new state is constructed in full and validated by
    PortfolioState.__post_init__ before it is returned. Nothing is mutated in
    place, so a raise leaves the caller holding the pre-state.
    """
    from core.b0_state import CashReceivable, PortfolioState, SecurityReceivable

    kind = event.kind
    sid = event.stock_id
    eid = event.canonical_event_id()
    pre_shares = int(state.shares.get(sid, 0))
    pre_pending = int(state.pending_exit.get(sid, 0))

    shares = dict(state.shares)
    pending = dict(state.pending_exit)
    on_recv = set(state.pending_exit_on_receivable)
    sec_recv = list(state.security_receivables)
    cash_recv = list(state.cash_receivables)
    created_sec, created_cash = [], []

    # Entitlement-bearing shares: what an event acts on. Uncredited claims on the
    # SAME security are entitlement-bearing too, which is what makes a chained
    # event apply to the whole holding rather than to the credited part of it.
    same_claims = sum((r.shares for r in sec_recv if r.security_id == sid),
                      Fraction(0))
    entitlement = Fraction(pre_shares) + same_claims
    full_exit = pre_shares > 0 and pre_pending == pre_shares

    if kind == "stock_dividend":
        ratio = Fraction(event.stock_ratio)
        new_claim = entitlement * ratio
        if new_claim > 0:
            credit = _first_session_on_or_after(
                event.credit_tradable_date, sessions)
            sec_recv.append(SecurityReceivable(
                security_id=sid, shares=new_claim, credit_tradable_date=credit,
                event_id=eid,
                origin_effective_date=str(event.ex_or_effective_date)))
            created_sec.append((sid, str(new_claim), credit))
            # §6.1.10: a position already under a full-exit obligation does not
            # get a new permanent holding out of a stock dividend.
            if full_exit:
                on_recv.add(sid)

    elif kind in ("capital_reduction", "par_value_change"):
        m = Fraction(str(event.share_multiplier))
        post = int(Fraction(pre_shares) * m)
        frac = Fraction(pre_shares) * m - post
        shares.pop(sid, None)
        if post > 0:
            shares[sid] = post
        # uncredited claims on the same security scale by the same multiplier
        sec_recv = [SecurityReceivable(
                        security_id=r.security_id, shares=r.shares * m,
                        credit_tradable_date=r.credit_tradable_date,
                        event_id=r.event_id,
                        source_security_id=r.source_security_id,
                        # scaled, not recreated: same claim, same origin
                        origin_effective_date=r.origin_effective_date)
                    if r.security_id == sid else r
                    for r in sec_recv]
        if frac > 0:
            sec_recv.append(SecurityReceivable(
                security_id=sid, shares=frac,
                credit_tradable_date=str(as_of), event_id=eid,
                origin_effective_date=str(event.ex_or_effective_date)))
            created_sec.append((sid, str(frac), str(as_of)))
        if kind == "capital_reduction" and event.cash_per_share:
            amount = float(entitlement) * float(event.cash_per_share)
            if amount > 0:
                avail = _first_session_on_or_after(
                    event.cash_available_date, sessions)
                cash_recv.append(CashReceivable(
                    amount=amount, cash_available_date=avail, event_id=eid,
                    source_security_id=sid))
                created_cash.append((amount, avail))
        # §6.1.10: the exit obligation scales with the surviving shares.
        pending.pop(sid, None)
        if pre_pending and post > 0:
            pending[sid] = post if full_exit else min(
                post, max(1, int(Fraction(pre_pending) * m)))

    elif kind in IDENTITY_CHANGING_KINDS:
        successor = str(event.successor_security_id)
        ratio = Fraction(event.stock_ratio)
        # I-CA-07: the old identity ends here. No splice, no alias.
        shares.pop(sid, None)
        pending.pop(sid, None)
        on_recv.discard(sid)
        sec_recv = [r for r in sec_recv if r.security_id != sid]
        new_claim = entitlement * ratio
        if new_claim > 0:
            credit = _first_session_on_or_after(
                event.credit_tradable_date, sessions)
            sec_recv.append(SecurityReceivable(
                security_id=successor, shares=new_claim,
                credit_tradable_date=credit, event_id=eid,
                source_security_id=sid,
                origin_effective_date=str(event.ex_or_effective_date)))
            created_sec.append((successor, str(new_claim), credit))
            if full_exit:
                on_recv.add(successor)
        if event.cash_per_share:
            amount = float(entitlement) * float(event.cash_per_share)
            if amount > 0:
                avail = _first_session_on_or_after(
                    event.cash_available_date or event.ex_or_effective_date,
                    sessions)
                cash_recv.append(CashReceivable(
                    amount=amount, cash_available_date=avail, event_id=eid,
                    source_security_id=sid))
                created_cash.append((amount, avail))
    else:
        raise CorporateActionTransitionError(
            "§6.1.2: %r reached the transition engine but is not a "
            "holder-affecting kind" % kind)

    new = PortfolioState(
        as_of=state.as_of, cash=state.cash, shares=shares, pending_exit=pending,
        cash_dividend_receivable=state.cash_dividend_receivable,
        stock_dividend_receivable=dict(state.stock_dividend_receivable),
        security_receivables=tuple(sec_recv), cash_receivables=tuple(cash_recv),
        applied_ca_event_ids=frozenset(state.applied_ca_event_ids) | {eid},
        pending_exit_on_receivable=frozenset(on_recv),
        # B0.1: a corporate action never opens or closes a holding spell.
        # Spells are driven by actual acquisition and exit; carrying the
        # ledger unchanged is what stops a transition fabricating exposure.
        holding_spells=tuple(state.holding_spells))
    target = event.successor_security_id or sid
    return new, {
        "pre_tradable_shares": pre_shares,
        "post_tradable_shares": int(new.shares.get(target, 0)),
        "created_security_receivables": tuple(created_sec),
        "created_cash_receivables": tuple(created_cash),
        "pending_exit_before": pre_pending,
        "pending_exit_after": int(new.pending_exit.get(target, 0)),
    }


# --- §6.1.13 - the mandatory invariants ----------------------------------------

def assert_transition_invariants(pre, post, events, *, as_of: str,
                                 applied: Sequence[str]) -> None:
    """I-CA-01 .. I-CA-15, all of them, before mark_portfolio may run.

    They are checked on the RESULT rather than asserted by construction: a
    transition that produced an impossible state has to be caught by something
    that did not also produce it.
    """
    from core.b0_state import CashReceivable, SecurityReceivable

    # I-CA-01 exactly once
    if len(set(applied)) != len(applied):
        raise CorporateActionTransitionError(
            "I-CA-01: an event was applied more than once: %s" % sorted(applied))
    already = set(pre.applied_ca_event_ids) & set(applied)
    if already:
        raise CorporateActionTransitionError(
            "I-CA-01: %s were already in the applied ledger" % sorted(already))

    # I-CA-02 no stale exposure
    for ev in events:
        if ev.kind in IDENTITY_CHANGING_KINDS and ev.stock_id in post.shares:
            raise CorporateActionTransitionError(
                "I-CA-02/I-CA-07: %s still holds tradable shares of %s after a "
                "%s" % (post.as_of, ev.stock_id, ev.kind))

    # I-CA-03 no free shares / I-CA-04 no free cash
    known = set(pre.applied_ca_event_ids) | set(applied)
    for r in post.security_receivables:
        if r.event_id not in known and r not in pre.security_receivables:
            raise CorporateActionTransitionError(
                "I-CA-03: security receivable %s traces to no applied event"
                % (r.security_id,))
    for r in post.cash_receivables:
        if r.event_id not in known and r not in pre.cash_receivables:
            raise CorporateActionTransitionError(
                "I-CA-04: cash receivable of %s traces to no applied event"
                % (r.amount,))

    # I-CA-05 receivable separation
    for r in post.security_receivables:
        if str(r.credit_tradable_date) <= str(as_of):
            if r.shares >= 1:
                raise CorporateActionTransitionError(
                    "I-CA-05: %s carries a matured whole-share claim that was "
                    "not released into tradable shares" % r.security_id)
    for r in post.cash_receivables:
        if str(r.cash_available_date) <= str(as_of):
            raise CorporateActionTransitionError(
                "I-CA-05: a matured cash receivable was not released into "
                "available cash")

    # I-CA-06 no look-ahead
    for ev in events:
        assert_no_look_ahead(ev, as_of)

    # I-CA-09 execution eligibility: a claim is never a tradable share
    claim_ids = {r.security_id for r in post.security_receivables}
    for sid in claim_ids:
        held = int(post.shares.get(sid, 0))
        claimed = sum((r.shares for r in post.security_receivables
                       if r.security_id == sid), Fraction(0))
        if claimed <= 0:
            raise CorporateActionTransitionError(
                "I-CA-09: non-positive claim recorded for %s" % sid)
        del held

    # I-CA-10 pending-exit continuity
    for ev in events:
        if ev.stock_id in pre.pending_exit and ev.kind in IDENTITY_CHANGING_KINDS:
            successor = ev.successor_security_id
            carried = (successor in post.pending_exit
                       or successor in post.pending_exit_on_receivable)
            if not carried:
                raise CorporateActionTransitionError(
                    "I-CA-10: the exit obligation on %s vanished across a %s"
                    % (ev.stock_id, ev.kind))

    # I-CA-14 flag conformance
    for ev in events:
        spec_kind = EVENT_KIND_BY_KEY[ev.kind]
        if spec_kind.changes_our_shares:
            moved = (dict(post.shares) != dict(pre.shares)
                     or post.security_receivables != pre.security_receivables)
            if not moved:
                raise CorporateActionTransitionError(
                    "I-CA-14: %s declares changes_our_shares=True but the "
                    "transition of %s produced no share-state effect. A handler "
                    "that can no-op is a silent NAV error."
                    % (ev.kind, ev.stock_id))
        if spec_kind.changes_our_cash and ev.cash_per_share:
            moved = (post.cash != pre.cash
                     or post.cash_receivables != pre.cash_receivables)
            if not moved:
                raise CorporateActionTransitionError(
                    "I-CA-14: %s on %s declares cash consideration but produced "
                    "no cash effect" % (ev.kind, ev.stock_id))

    # structural: the state validated itself on construction (I-CA-13 atomicity)
    if not isinstance(post.applied_ca_event_ids, frozenset):
        raise CorporateActionTransitionError(
            "I-CA-01: the applied-event ledger must be an immutable set")


def assert_no_adjusted_price_double_count(valuation_basis: str) -> None:
    """I-CA-15: shares were adjusted explicitly, so prices must not be again."""
    if valuation_basis != "RAW_OBSERVED":
        raise CorporateActionTransitionError(
            "I-CA-15: portfolio state has been explicitly transitioned for "
            "corporate actions, so valuation must use raw observed prices; "
            "%r would compensate for the same event twice." % valuation_basis)


# --- §6.1.11 - ordering of multiple same-day events ----------------------------

def _order_same_day(events: Sequence["CorporateActionEvent"]):
    """Deterministic causal order, or NOT_RECONSTRUCTIBLE.

    §6.1.11 forbids deciding economic causality by alphabetical kind, event id or
    row order. Where a source states a sequence it is used; where the events
    commute the order cannot matter; otherwise the ambiguity is real and is
    reported as such.
    """
    by_day = {}
    for ev in events:
        by_day.setdefault((ev.stock_id, ev.ex_or_effective_date), []).append(ev)
    ordered = []
    for key in sorted(by_day):
        group = by_day[key]
        if len(group) == 1:
            ordered.extend(group)
            continue
        seqs = [ev.diagnostics.get("event_sequence") for ev in group]
        if all(s is not None for s in seqs) and len(set(seqs)) == len(seqs):
            ordered.extend(sorted(group,
                                  key=lambda e: e.diagnostics["event_sequence"]))
            continue
        kinds = {ev.kind for ev in group}
        # Two same-security share multipliers commute; anything involving an
        # identity change or a cash leg does not.
        commutes = kinds <= {"par_value_change", "capital_reduction"} and not any(
            ev.cash_per_share for ev in group)
        if commutes:
            ordered.extend(sorted(group, key=lambda e: e.kind))
            continue
        raise CorporateActionReconstructionBlock(
            "§6.1.11: %s has %d non-commuting holder-affecting events on %s with "
            "no source-provided causal sequence" % (key[0], len(group), key[1]),
            detail={"security_id": key[0], "effective_date": key[1],
                    "event_kinds": sorted(kinds),
                    "missing_fields": ["event_sequence"]})
    return tuple(ordered)


# --- §6.1.6 - the canonical intra-period transition ----------------------------

def transition_portfolio(state, events: Sequence["CorporateActionEvent"], *,
                         as_of: str, sessions: Sequence[str],
                         period: str = "") -> "CorporateActionTransitionResult":
    """PortfolioState[t-1] + today's events -> validated PortfolioState[t].

    The order in §6.1.6 is not a style choice. Releasing matured claims first is
    what lets a stock dividend credited today be sold today; applying events
    before the mark is what stops a post-ex holding being valued on pre-ex share
    counts; validating before returning is what makes a wrong transition an abort
    rather than a number.
    """
    from core.b0_state import PortfolioState

    pre = state
    pre_hash = _state_hash(pre)

    # 1. release claims created in earlier periods that matured on or before today
    work, released_sec, released_cash = _release_matured(pre, as_of)

    # 2. apply today's effective holder-affecting events
    # B0.1 · R2/R3. An event is this period's business only if ONE holding
    # spell covers both its boundary and today. Everything else is historical to
    # some other exposure, or to no exposure of B0's at all: it is not applied,
    # it creates no claim, and it cannot block.
    candidates = [e for e in events
                  if e.kind in holder_affecting_kinds()
                  and str(e.ex_or_effective_date) <= str(as_of)
                  and e.canonical_event_id() not in pre.applied_ca_event_ids]
    #
    # B0.7 · R3/R5: the filter is the COMBINED economic interest, and it is taken
    # against `work` rather than `pre`. Under B0.1 the two were the same state
    # for this purpose - a transition never touches `holding_spells`, so the
    # answer could not differ. It can now: step 1 releases matured claims, so a
    # claim ledger read from `pre` is the ledger of yesterday. §6.1.6 puts the
    # release BEFORE the apply, and §6.1.7 takes `Q` at the moment of
    # application, so the moment of application is the state to ask.
    out_of_spell = [e.canonical_event_id() for e in candidates
                    if not ca_economic_interest_applies(work, e, as_of=as_of)]
    todays = [e for e in candidates
              if ca_economic_interest_applies(work, e, as_of=as_of)]
    ledger, applied, skipped = [], [], []
    skipped.extend(out_of_spell)
    for ev in _order_same_day(todays):
        exposed = is_exposed(work, ev, as_of=as_of)
        if ev.reconstructibility == NOT_RECONSTRUCTIBLE:
            # §6.1.12: existence is not the blocking condition; exposure is.
            if not exposed:
                skipped.append(ev.canonical_event_id())
                continue
            raise CorporateActionReconstructionBlock(
                "§6.1.12: %s/%s on %s is NOT_RECONSTRUCTIBLE and B0 is exposed "
                "(%s)" % (ev.stock_id, ev.kind, ev.ex_or_effective_date, ev.reason),
                detail={"security_id": ev.stock_id, "event_kind": ev.kind,
                        "event_id": ev.canonical_event_id(),
                        "effective_date": ev.ex_or_effective_date,
                        # B0.7: the blocker names its own status and moment.
                        # A record that says only "blocked" leaves the next
                        # reader to re-derive what this already knew.
                        "reconstructibility": ev.reconstructibility,
                        "as_of": str(as_of),
                        "exposure": {
                            "tradable_shares": int(work.shares.get(ev.stock_id, 0)),
                            "pending_exit": int(
                                work.pending_exit.get(ev.stock_id, 0)),
                            "claims": [str(r.shares) for r in
                                       work.security_receivables
                                       if r.security_id == ev.stock_id]},
                        "missing_fields": [ev.reason],
                        "pre_state_hash": pre_hash,
                        "last_valid_state_hash": _state_hash(work)})
        if not exposed:
            skipped.append(ev.canonical_event_id())
            continue
        assert_no_look_ahead(ev, as_of)
        assert_transition_fields_present(ev)
        before = work
        work, audit = _apply_one(work, ev, as_of, sessions)
        applied.append(ev.canonical_event_id())
        ledger.append(TransitionRecord(
            period=period or as_of,
            event_id=ev.canonical_event_id(), event_kind=ev.kind,
            security_id=ev.stock_id,
            successor_security_id=ev.successor_security_id,
            knowledge_ts=ev.knowledge_ts,
            effective_date=ev.ex_or_effective_date,
            credit_tradable_date=ev.credit_tradable_date,
            cash_available_date=ev.cash_available_date,
            created_security_receivables=audit["created_security_receivables"],
            released_security_receivables=(),
            created_cash_receivables=audit["created_cash_receivables"],
            released_cash=0.0,
            pre_tradable_shares=audit["pre_tradable_shares"],
            post_tradable_shares=audit["post_tradable_shares"],
            pending_exit_before=audit["pending_exit_before"],
            pending_exit_after=audit["pending_exit_after"],
            reconstructibility=ev.reconstructibility,
            blocking_reason=None,
            pre_state_hash=_state_hash(before),
            post_state_hash=_state_hash(work),
            event_source_hash=_event_hash(ev)))

    # 3. release claims this step created that mature today (zero-day, §6.1.7A)
    work, zero_day_sec, zero_day_cash = _release_matured(work, as_of)

    # 5. invariants, on the result
    assert_transition_invariants(pre, work, [e for e in _order_same_day(todays)
                                             if e.canonical_event_id() in applied],
                                 as_of=as_of, applied=applied)

    if ledger:
        first = ledger[0]
        ledger[0] = TransitionRecord(
            **{**first.__dict__,
               "released_security_receivables": released_sec + zero_day_sec,
               "released_cash": released_cash + zero_day_cash})
    elif released_sec or released_cash:
        ledger.append(TransitionRecord(
            period=period or as_of, event_id="", event_kind="release_only",
            security_id="", successor_security_id=None, knowledge_ts=None,
            effective_date=as_of, credit_tradable_date=None,
            cash_available_date=None, pre_tradable_shares=0,
            post_tradable_shares=0,
            created_security_receivables=(), released_security_receivables=(
                released_sec + zero_day_sec),
            created_cash_receivables=(), released_cash=(
                released_cash + zero_day_cash),
            pending_exit_before=0, pending_exit_after=0,
            reconstructibility=NOT_APPLICABLE, blocking_reason=None,
            pre_state_hash=pre_hash, post_state_hash=_state_hash(work),
            event_source_hash=""))

    return CorporateActionTransitionResult(
        state=work, ledger=tuple(ledger), applied_event_ids=tuple(applied),
        skipped_unexposed=tuple(skipped))


def redate(state, as_of: str):
    """Carry a validated state to the next decision point.

    Only the timestamp moves. It is separate from `transition_portfolio` because
    moving a date and changing an economic quantity are different acts, and C-53
    forbids the second one being smuggled inside the first.
    """
    import dataclasses

    # B0.1: `replace` rather than a hand-listed constructor. The explicit list
    # silently dropped `holding_spells` the moment that field was added, and
    # dropping the exposure ledger IS changing an economic quantity - exactly
    # what this function's own docstring forbids.
    return dataclasses.replace(state, as_of=str(as_of))


def assert_transition_applied(state, events, *, as_of: str) -> None:
    """§6.1.2 / I-CA-02: the state reaching the mark must already be transformed.

    This is what makes `corporate_action_transition` a stage rather than a label.
    A caller that skipped the engine arrives here holding a portfolio whose
    entitlement-bearing securities have effective events not in the applied
    ledger, and the run stops before any NAV exists.
    """
    outstanding = []
    for ev in events:
        if ev.kind not in holder_affecting_kinds():
            continue
        if str(ev.ex_or_effective_date) > str(as_of):
            continue
        # B0.1 · R3 / B0.7 · R3: the same canonical predicate, all the way down.
        # A membership test here would reintroduce the defect one layer below
        # the one that was fixed, and an underlying-only test would reintroduce
        # B0.7's one layer below that.
        if not ca_economic_interest_applies(state, ev, as_of=as_of):
            continue
        if ev.canonical_event_id() in state.applied_ca_event_ids:
            continue
        outstanding.append("%s/%s@%s" % (ev.stock_id, ev.kind,
                                         ev.ex_or_effective_date))
    if outstanding:
        raise CorporateActionTransitionError(
            "§6.1.1: %d holder-affecting event(s) are effective on or before %s "
            "on securities B0 is exposed to, and were never applied: %s. Marking "
            "now would value a post-event holding on pre-event share counts."
            % (len(outstanding), as_of, outstanding[:5]))
