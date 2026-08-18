"""C-50 · share-unit price adjustment — the single canonical producer.

`compute_momentum_12_1` requires a price series already adjusted for §2.4
share-count events and says the adjustment is not its own choice. Nothing said
what the adjustment WAS, so `momentum_price_adjustment` was registered under M-3
and ruled (R1-R8). This module is the ruling, in the only form a route can check.

The distinction the ruling turns on, because everything else follows from it:

    adjust for a deterministic transformation of the shares an EXISTING HOLDER
    holds — not for a change in the company's shares outstanding.

`share_multiplier != 1` is not sufficient. A convertible bond converting, an
employee share issue, a cash capital increase and a treasury cancellation all
move shares outstanding without multiplying anybody's existing position, and
adjusting a price series for them would manufacture a return out of dilution.
A stock dividend, a split, a reverse split and a capital-reduction share exchange
do multiply it, and leaving those unadjusted reports a split as a -50% momentum.

Two further properties are deliberate:

  * **SHARE_UNIT_ADJUSTED, never TOTAL_RETURN_ADJUSTED.** Cash dividends,
    returned cash, subscription prices and rights values never enter. §3.1 names
    the member a PRICE relative, so a total-return series would answer a
    different question under the same name.
  * **The raw panel stays raw.** Only `momentum_12_1` and `sigma20d` read the
    adjusted series (R6). Marks, execution prices, NAV, portfolio value, order
    notional, fees, tax and ADV20 read observed market prices, because those are
    quantities in money that was actually paid or actually traded — an adjusted
    price is a comparability device, not a price anything changed hands at.

Fail-loud, never a guessed factor (R8): an eligible event whose holder multiplier
is absent or ambiguous, whose market-effective boundary cannot be reconstructed,
or whose same-security identity cannot be established, raises. The caller turns
that into NA under the already-frozen complete-case semantics; it does not
substitute a factor it finds plausible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

ADJUSTMENT_BASIS = "SHARE_UNIT_ADJUSTED"
NOT_THIS_BASIS = "TOTAL_RETURN_ADJUSTED"

# R2 · a holder-level multiplicative transformation of the SAME security.
ELIGIBLE_KINDS: tuple[str, ...] = (
    "stock_dividend",        # bonus shares: old x (1 + rate) = new
    "capital_reduction",     # share exchange on a reduced unit
    "par_value_change",      # unit transformation, incl. split / reverse split
)

# R2 · shares outstanding moved; no existing position was multiplied.
INELIGIBLE_KINDS: tuple[str, ...] = (
    "cash_capital_increase",
    "convertible_bond_conversion",
    "employee_bonus",
    "treasury_cancellation",
    "other_share_change",
)

# R5 · identity changes. A successor security uses its OWN canonical history and
# its own listing spell; no synthetic A->B series is ever spliced.
IDENTITY_CHANGE_KINDS: tuple[str, ...] = (
    "merger", "share_conversion", "transfer_in",
)

# R6 · who reads which series. Stated as data so that a new consumer is a visible
# edit rather than an import.
ADJUSTED_CONSUMERS: tuple[str, ...] = ("momentum_12_1", "sigma20d")
RAW_CONSUMERS: tuple[str, ...] = (
    "marks", "execution_prices", "nav", "portfolio_market_value",
    "order_notional", "fees_tax", "adv20",
)

# R3 · what may never enter the factor.
EXCLUDED_FROM_FACTOR: tuple[str, ...] = (
    "cash_dividend_amount", "returned_cash", "subscription_price",
    "subscription_rights_value", "total_return_reinvestment",
)

# R4 · the boundary is the market-effective session, never the credit date.
BOUNDARY_FIELD = "ex_or_effective_date"
NOT_BOUNDARY_FIELD = "credit_tradable_date"


class ShareUnitAdjustmentError(RuntimeError):
    """Fail-loud: an adjustment was requested that the ruling does not authorise."""


class UnreconstructibleAdjustment(ShareUnitAdjustmentError):
    """R8: an eligible event whose factor cannot be derived. NA, never a guess."""


@dataclass(frozen=True)
class ShareUnitEvent:
    """One authorised boundary: `multiplier` transforms an existing holding."""

    stock_id: str
    kind: str
    boundary_session: str          # first session quoted on the new unit basis
    multiplier: float             # old_holder_shares x m = new_holder_shares

    def __post_init__(self) -> None:
        if self.kind not in ELIGIBLE_KINDS:
            raise ShareUnitAdjustmentError(
                f"C-50/R2: {self.kind!r} is not an eligible kind. Eligible: "
                f"{ELIGIBLE_KINDS}; ineligible despite moving shares outstanding: "
                f"{INELIGIBLE_KINDS}; identity changes (R5): "
                f"{IDENTITY_CHANGE_KINDS}.")
        if not self.boundary_session:
            raise UnreconstructibleAdjustment(
                f"C-50/R4: {self.stock_id} {self.kind} has no market-effective "
                f"boundary session")
        if not (self.multiplier > 0):
            raise UnreconstructibleAdjustment(
                f"C-50/R8: {self.stock_id} {self.kind} multiplier "
                f"{self.multiplier!r} is not positive")
        if self.multiplier == 1.0:
            raise ShareUnitAdjustmentError(
                f"C-50: {self.stock_id} {self.kind} multiplier is exactly 1; an "
                f"event that transforms nothing must not create a boundary")


def assert_kind_classified(kind: str) -> str:
    """Every ledger kind must be classified. An unknown one aborts (R8)."""
    if kind in ELIGIBLE_KINDS:
        return "eligible"
    if kind in INELIGIBLE_KINDS:
        return "ineligible"
    if kind in IDENTITY_CHANGE_KINDS:
        return "identity_change"
    raise UnreconstructibleAdjustment(
        f"C-50/R8: corporate-action kind {kind!r} is not classified by the "
        f"ruling. Its disposition is ambiguous, so it may not be silently "
        f"treated as ineligible — that would be a guess with the same shape as "
        f"guessing a factor.")


def holder_multiplier(record: Mapping[str, object]) -> float:
    """R2: the multiplier, only when the record PROVES old x m = new.

    `share_multiplier` is the only field that states the holder-level
    transformation directly. A new-share COUNT does not: turning it into a
    multiplier needs shares outstanding at the boundary, which is a different
    quantity with its own lineage question.
    """
    kind = str(record.get("kind") or "")
    assert_kind_classified(kind)
    if kind not in ELIGIBLE_KINDS:
        raise ShareUnitAdjustmentError(
            f"C-50/R2: {kind!r} does not transform an existing holding")
    if str(record.get("reconstructibility") or "") != "RECONSTRUCTIBLE":
        raise UnreconstructibleAdjustment(
            f"C-50/R8: {record.get('stock_id')} {kind} is not RECONSTRUCTIBLE "
            f"({record.get('reason') or 'no reason recorded'})")
    raw = str(record.get("share_multiplier") or "").strip()
    if not raw:
        raise UnreconstructibleAdjustment(
            f"C-50/R8: {record.get('stock_id')} {kind} carries no "
            f"share_multiplier. A holder multiplier may not be inferred from a "
            f"new-share count without shares outstanding at the boundary.")
    try:
        m = float(raw)
    except ValueError:
        raise UnreconstructibleAdjustment(
            f"C-50/R8: {record.get('stock_id')} {kind} share_multiplier "
            f"{raw!r} is not numeric") from None
    if not (m > 0):
        raise UnreconstructibleAdjustment(
            f"C-50/R8: {record.get('stock_id')} {kind} multiplier {m} is not "
            f"positive")
    return m


def boundary_session(effective_date: str, sessions: Sequence[str]) -> str:
    """R4: the first session quoted on the new unit basis.

    The ex-right / new-unit / resumption date itself when it is a session, else
    the next one. `credit_tradable_date` is never consulted: it governs when
    credited shares become available to the portfolio, which is a different
    question from when the quote changes basis.
    """
    if not effective_date:
        raise UnreconstructibleAdjustment(
            "C-50/R4: no ex_or_effective_date, so no market-effective boundary")
    for s in sessions:
        if str(s) >= str(effective_date):
            return str(s)
    raise UnreconstructibleAdjustment(
        f"C-50/R4: no trading session on or after {effective_date}; the "
        f"boundary is not reconstructible")


def factors_for(events: Sequence[ShareUnitEvent]) -> tuple[tuple[str, float], ...]:
    """Authorised boundaries for one security, ascending, multipliers compounded
    per boundary if several land on the same session."""
    by_session: dict[str, float] = {}
    for e in events:
        by_session[e.boundary_session] = by_session.get(
            e.boundary_session, 1.0) * float(e.multiplier)
    return tuple(sorted(by_session.items()))


def adjusted_series(sessions: Sequence[str],
                    prices: Sequence[float | None],
                    factors: Sequence[tuple[str, float]]) -> list[float | None]:
    """R3: `adjusted = raw / m` for every price BEFORE the boundary, compounded.

    A price on or after every boundary is returned unchanged, so the most recent
    end of the series — the end a decision stands on — is always the raw quote.
    """
    if len(sessions) != len(prices):
        raise ShareUnitAdjustmentError(
            "C-50: sessions and prices must be the same length")
    ordered = sorted(factors)
    out: list[float | None] = []
    for s, p in zip(sessions, prices):
        if p is None:
            out.append(None)
            continue
        divisor = 1.0
        for boundary, m in ordered:
            if str(s) < str(boundary):
                divisor *= float(m)
        out.append(float(p) / divisor if divisor != 1.0 else float(p))
    return out


def assert_consumer_reads_adjusted(name: str) -> None:
    if name in RAW_CONSUMERS:
        raise ShareUnitAdjustmentError(
            f"C-50/R6: {name!r} must read RAW observed prices. It is a quantity "
            f"in money actually paid or actually traded; an adjusted price is a "
            f"comparability device and was never transacted at.")
    if name not in ADJUSTED_CONSUMERS:
        raise ShareUnitAdjustmentError(
            f"C-50/R6: {name!r} is not a declared consumer of the adjusted "
            f"series. Adding one is a specification change, not an import.")


def assert_consumer_reads_raw(name: str) -> None:
    if name in ADJUSTED_CONSUMERS:
        raise ShareUnitAdjustmentError(
            f"C-50/R6: {name!r} reads the share-unit-adjusted series; a raw "
            f"series would give it a mechanical split shock.")
    if name not in RAW_CONSUMERS:
        raise ShareUnitAdjustmentError(
            f"C-50/R6: {name!r} is not a declared consumer of raw prices")


def assert_no_total_return_component(component: str) -> None:
    """R3: the factor is share units only."""
    if component in EXCLUDED_FROM_FACTOR:
        raise ShareUnitAdjustmentError(
            f"C-50/R3: {component!r} may not enter a share-unit factor. This "
            f"basis is {ADJUSTMENT_BASIS}, not {NOT_THIS_BASIS}.")


def assert_no_identity_splice(kind: str, from_id: str, to_id: str) -> None:
    """R5: a successor security uses its own history, never a spliced one."""
    if str(from_id) != str(to_id):
        raise ShareUnitAdjustmentError(
            f"C-50/R5: {kind} maps {from_id} -> {to_id}. Price history may not "
            f"be spliced across security identities; the successor satisfies the "
            f"listing-spell and history requirements from its own canonical "
            f"history.")
