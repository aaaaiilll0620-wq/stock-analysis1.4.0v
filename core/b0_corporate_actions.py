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
