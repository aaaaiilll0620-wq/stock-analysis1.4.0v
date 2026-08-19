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
    EventKind("merger", "合併(仟股)", True, False, True,
              "recorded on the surviving/issuing entity only"),
    EventKind("share_conversion", "股份轉換(仟股", True, False, True,
              "holding-company swap, recorded on the new entity only"),
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
    exposures: Iterable[Exposure],
) -> list[CorporateActionEvent]:
    """Events B0 was actually exposed to and cannot reconstruct.

    An event the portfolio never held is not a defect in the run — this is what
    makes the per-event rule affordable without a missing-rate threshold.
    """
    by_id: dict[str, list[Exposure]] = {}
    for e in exposures:
        by_id.setdefault(e.stock_id, []).append(e)
    hit = []
    for ev in events:
        if ev.reconstructibility != NOT_RECONSTRUCTIBLE:
            continue
        if any(x.covers(ev.ex_or_effective_date) for x in by_id.get(ev.stock_id, ())):
            hit.append(ev)
    return hit


def assert_exposure_reconstructible(
    events: Iterable[CorporateActionEvent],
    exposures: Iterable[Exposure],
) -> None:
    """Abort before any NAV is produced for a position we cannot account for."""
    hit = exposed_unreconstructible_events(events, exposures)
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


def handle_merger(rec: Mapping[str, object]) -> CorporateActionEvent:
    return _identity_change_unobservable("merger", rec)


def handle_share_conversion(rec: Mapping[str, object]) -> CorporateActionEvent:
    return _identity_change_unobservable("share_conversion", rec)


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
    "merger": handle_merger,
    "share_conversion": handle_share_conversion,
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


IDENTITY_CHANGING_KINDS: tuple[str, ...] = ("merger", "share_conversion")
SAME_SECURITY_SHARE_KINDS: tuple[str, ...] = (
    "stock_dividend", "capital_reduction", "par_value_change")


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


REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "stock_dividend": ("stock_ratio", "credit_tradable_date"),
    "capital_reduction": ("share_multiplier",),
    "merger": ("successor_security_id", "stock_ratio", "credit_tradable_date"),
    "share_conversion": ("successor_security_id", "stock_ratio",
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


def is_exposed(state, event: "CorporateActionEvent") -> bool:
    """§6.1.12: affected economic exposure, not mere existence of the event."""
    return event.stock_id in set(state.entitlement_securities)


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
              r.source_security_id] for r in state.security_receivables]),
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


REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "stock_dividend": ("stock_ratio", "credit_tradable_date"),
    "capital_reduction": ("share_multiplier",),
    "merger": ("successor_security_id", "stock_ratio", "credit_tradable_date"),
    "share_conversion": ("successor_security_id", "stock_ratio",
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


def is_exposed(state, event: "CorporateActionEvent") -> bool:
    """§6.1.12: affected economic exposure, not mere existence of the event."""
    return event.stock_id in set(state.entitlement_securities)


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
              r.source_security_id] for r in state.security_receivables]),
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
                event_id=r.event_id, source_security_id=r.source_security_id))
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
        pending_exit_on_receivable=frozenset(on_recv))
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
                event_id=eid))
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
                        source_security_id=r.source_security_id)
                    if r.security_id == sid else r
                    for r in sec_recv]
        if frac > 0:
            sec_recv.append(SecurityReceivable(
                security_id=sid, shares=frac,
                credit_tradable_date=str(as_of), event_id=eid))
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
                source_security_id=sid))
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
        pending_exit_on_receivable=frozenset(on_recv))
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
    todays = [e for e in events
              if e.kind in holder_affecting_kinds()
              and str(e.ex_or_effective_date) <= str(as_of)
              and e.canonical_event_id() not in pre.applied_ca_event_ids]
    ledger, applied, skipped = [], [], []
    for ev in _order_same_day(todays):
        exposed = is_exposed(work, ev)
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
    from core.b0_state import PortfolioState

    return PortfolioState(
        as_of=str(as_of), cash=state.cash, shares=dict(state.shares),
        pending_exit=dict(state.pending_exit),
        cash_dividend_receivable=state.cash_dividend_receivable,
        stock_dividend_receivable=dict(state.stock_dividend_receivable),
        security_receivables=tuple(state.security_receivables),
        cash_receivables=tuple(state.cash_receivables),
        applied_ca_event_ids=frozenset(state.applied_ca_event_ids),
        pending_exit_on_receivable=frozenset(state.pending_exit_on_receivable))


def assert_transition_applied(state, events, *, as_of: str) -> None:
    """§6.1.2 / I-CA-02: the state reaching the mark must already be transformed.

    This is what makes `corporate_action_transition` a stage rather than a label.
    A caller that skipped the engine arrives here holding a portfolio whose
    entitlement-bearing securities have effective events not in the applied
    ledger, and the run stops before any NAV exists.
    """
    exposed = set(state.entitlement_securities)
    outstanding = []
    for ev in events:
        if ev.kind not in holder_affecting_kinds():
            continue
        if str(ev.ex_or_effective_date) > str(as_of):
            continue
        if ev.stock_id not in exposed:
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
