"""Canonical B0 core state — the source-agnostic input contract (P-1b).

§8.7 assigns responsibilities to four modules and says nothing about where their
inputs come from. That silence is the point: the core must not know whether a
price arrived from a TEJ yearly export, a runtime API, or a fixture. A call like

    load_price_export_2019(...)

inside `b0_features` would put the data layer's defects inside the strategy
layer, and the D-1 re-export would then become a core change rather than a data
change. This module holds the shapes those inputs take, and nothing else.

WHAT THIS MODULE DOES NOT CONTAIN: no strategy semantics, no feature formula, no
selection rule, no I/O. The one behaviour it does carry is portfolio marking
(§6.2), which is state construction rather than a decision — the marked value is
an input to eligibility (ADV_floor = 5 x port_value), not an output of it.

D-1 (§2.8). The canonical core must not consume a price universe that has not
been shown free of the survivorship filter: from 2019 the yearly exports contain
only securities still listed at export time, contaminating 87 of the 141 window
months. The core cannot check that itself — it never opens a file — so the input
carries an attestation, and `assert_price_state_admissible` cross-checks that
attestation against the live blocking-requirement registry in
`core.b0_frozen_spec`. While D-1 is unmet, every non-synthetic run aborts here,
at the input boundary, rather than producing an upward-biased NAV.

The attestation is deliberately not a boolean the caller can set to True and
forget. `satisfied_blocking_requirements` names which requirements the supplier
claims to have discharged, and the check is a comparison against the registry, so
a requirement added later invalidates old attestations instead of silently
passing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence


class CoreStateError(RuntimeError):
    """Fail-loud: an input the canonical core must not silently absorb."""


# --- provenance / admissibility of the inputs ---------------------------------

@dataclass(frozen=True)
class SourceAttestation:
    """What the supplying adapter asserts about a canonical input.

    No field has a default. An attestation must be made, not omitted into
    existence — the same reason `DataRepair` (M-2) and `execution_confirmed`
    (G14-3) have none.
    """
    dataset_id: str
    provenance_sha256: str          # B-21 DatasetProvenance content hash
    pit_guard_passed: bool          # O-B/O-E: every dated field bounded by as_of
    universe_guard_passed: bool     # §2.8: churn verifier ran and passed
    satisfied_blocking_requirements: tuple[str, ...]
    synthetic: bool                 # a fixture, admissible only outside sealed runs

    def __post_init__(self) -> None:
        for f in ("dataset_id", "provenance_sha256"):
            if not str(getattr(self, f)).strip():
                raise CoreStateError(
                    f"SourceAttestation.{f} is required — an input that cannot "
                    f"identify itself cannot be sealed (B-21 §8.6)")
        if not isinstance(self.satisfied_blocking_requirements, tuple):
            raise CoreStateError(
                "satisfied_blocking_requirements must be a tuple so the "
                "attestation stays hashable and immutable")


def assert_price_state_admissible(att: SourceAttestation, *,
                                  for_sealed_run: bool) -> None:
    """Refuse a price universe that has not been shown fit for B0.

    `for_sealed_run` is keyword-only and has no default: whether this run is one
    that may produce sealed evidence is the caller's declaration, never an
    inference from what happens to be installed.
    """
    if not att.pit_guard_passed:
        raise CoreStateError(
            f"{att.dataset_id}: the PIT guard has not passed. O-E exists because a "
            f"current-snapshot source bypasses every downstream PIT check at the "
            f"input layer (industry_map: 49.4% of names changed sector).")
    if not att.universe_guard_passed:
        raise CoreStateError(
            f"{att.dataset_id}: the universe-completeness guard has not passed. "
            f"See §2.8 — a price export that silently drops delisted securities "
            f"biases every cross-sectional quantity upward, including the "
            f"equal-weight universe benchmark that row ① of the ladder divides by.")

    if att.synthetic:
        if for_sealed_run:
            raise CoreStateError(
                f"{att.dataset_id}: a synthetic input may not feed a sealed run. "
                f"Fixtures exist to test mechanics, not to produce evidence.")
        return

    from core.b0_frozen_spec import unmet_blocking_requirements

    unmet = tuple(r.key for r in unmet_blocking_requirements())
    outstanding = tuple(k for k in unmet
                        if k not in att.satisfied_blocking_requirements)
    if outstanding:
        raise CoreStateError(
            f"{att.dataset_id}: blocking data requirement(s) {list(outstanding)} "
            f"are unmet and not attested. The canonical core may be built and "
            f"tested while they are open, but it may not consume real data "
            f"through them (§2.8, §12.2)."
        )


# --- market snapshot ----------------------------------------------------------

def _finite_positive(name: str, stock_id: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0:
        raise CoreStateError(
            f"{name}[{stock_id}] must be finite and > 0, got {value!r}")
    return v


# --- the two derived market quantities (C-25, C-26) ---------------------------
# ADV20 and sigma20d are load-bearing in three separate clauses each — the
# eligibility gate (§4.2), the 1% order cap (§6.4) and the impact term (§7.1) —
# so one definition has to serve all three. They are computed here, at the point
# where the snapshot that carries them is built, rather than in whichever layer
# happens to consume them first.

ADV20_SESSIONS = 20
SIGMA20D_RETURNS = 20
# Sample standard deviation. B-14 P3 fixes everything else about sigma20d and is
# silent on this; ddof=1 is what "standard deviation of a sample" denotes, and
# the difference from ddof=0 is a factor of sqrt(20/19) ~ 1.026 on the impact
# term. Named rather than inlined so the choice is visible and reversible.
SIGMA20D_DDOF = 1


def compute_adv20(traded_values: Sequence[float | None]) -> float | None:
    """Mean daily traded VALUE over the last 20 observed sessions (C-25).

        adv20 = mean( close_s * volume_s )  over the 20 most recent sessions

    "Observed" sessions, not calendar days: a security suspended for part of the
    window contributes the sessions it actually traded, which is the same
    convention O-E applies to the trading calendar and the same one the legacy
    producer used (`universe_screen_daily.py:165`, `dollar_vol.tail(20).mean()`).

    Fewer than 20 observed sessions -> None. A shorter window would silently
    change the measure for exactly the illiquid and newly-listed names the §4.2
    gate exists to remove, and §4.2 treats a missing liquidity observation as
    absence of evidence rather than evidence of eligibility.
    """
    usable = [float(v) for v in traded_values
              if v is not None and math.isfinite(float(v)) and float(v) >= 0]
    if len(usable) < ADV20_SESSIONS:
        return None
    window = usable[-ADV20_SESSIONS:]
    return sum(window) / ADV20_SESSIONS


def compute_sigma20d(closes: Sequence[float | None]) -> float | None:
    """Trailing 20-session standard deviation of daily LOG returns (C-26).

    B-14 P3, quoted: "trailing 20 交易日 log return 標準差, PIT, 未年化".

    UNANNUALISED, and that is not a detail: sigma20d multiplies the impact term
    linearly (§7.1), so an annualised reading would overstate modelled impact by
    about 15.9x. §7.6 forbids claiming a direction for the cost model's bias, so
    such an error would not even be conservatively signed.

    Needs 21 consecutive observed closes to form 20 returns. Any non-positive
    close makes the log return undefined -> None; a price of zero is not a -100%
    return, it is a data defect.
    """
    if len(closes) < SIGMA20D_RETURNS + 1:
        return None
    window = list(closes[-(SIGMA20D_RETURNS + 1):])
    if any(c is None or not math.isfinite(float(c)) or float(c) <= 0
           for c in window):
        return None
    rets = [math.log(float(window[i + 1]) / float(window[i]))
            for i in range(len(window) - 1)]
    n = len(rets)
    mean = sum(rets) / n
    divisor = n - SIGMA20D_DDOF
    if divisor <= 0:
        return None
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / divisor)


@dataclass(frozen=True)
class MarketSnapshot:
    """PIT market state as of the prior completed trading session (O-D).

    `as_of` is that session, not the decision date. DECISION_STATE_SOURCE is
    `prior_completed_trading_session` for EVERY decision input (§6.6), so the
    snapshot carries the session it was built from and callers check the decision
    date against it with `assert_decision_inputs_are_prior_session`.
    """
    as_of: str
    attestation: SourceAttestation
    marks: Mapping[str, float]      # PIT full-market mark price, §6.2
    adv20: Mapping[str, float]
    sigma20d: Mapping[str, float]

    def __post_init__(self) -> None:
        if not str(self.as_of).strip():
            raise CoreStateError("MarketSnapshot.as_of is required")
        for sid, px in self.marks.items():
            _finite_positive("marks", sid, px)
        for sid, v in self.adv20.items():
            _finite_positive("adv20", sid, v)
        for sid, s in self.sigma20d.items():
            sv = float(s)
            if not math.isfinite(sv) or sv < 0:
                raise CoreStateError(
                    f"sigma20d[{sid}] must be finite and >= 0, got {s!r}")

    def mark_price(self, stock_id: str) -> float:
        """§6.2: a held name with no mark fails loud. It is never worth zero.

        Treating an absent price as zero, or dropping the position, is the silent
        NAV error O-B and this accessor both exist to prevent — and the mark must
        never be sourced from the candidate list, because then selection would be
        deciding valuation.
        """
        try:
            return float(self.marks[stock_id])
        except KeyError:
            raise CoreStateError(
                f"§6.2: no PIT mark price for held security {stock_id!r} as of "
                f"{self.as_of}. A holding absent from the price source is not "
                f"worth 0 and must not be dropped — abort and resolve the input."
            ) from None


# --- §6.1.4 · dated claims ------------------------------------------------------
# The distinction the whole corporate-action transition turns on:
#
#     owned  !=  tradable  !=  spendable
#
# A stock-dividend entitlement is owned from the ex-right session and tradable
# only from the credit date. A capital-reduction refund is owned from the
# effective date and spendable only from the payment date. Collapsing either
# pair lets execution sell shares nobody holds yet or spend cash nobody has
# received, and both look like ordinary fills in a receipt.

@dataclass(frozen=True)
class SecurityReceivable:
    """§6.1.4: a security claim that is owned but not yet tradable.

    `shares` is a Fraction, not an int. §6.1.9 forbids rounding at the transition
    stage, because a rounded entitlement is an entitlement that silently ceased
    to exist; the integral part becomes tradable at release and any remainder
    stays a claim until official settlement semantics can be reconstructed.
    """
    security_id: str
    shares: object                     # fractions.Fraction, kept exact
    credit_tradable_date: str
    event_id: str
    source_security_id: str = ""       # set when identity changed (merger etc.)

    def __post_init__(self) -> None:
        from fractions import Fraction

        if not str(self.security_id).strip():
            raise CoreStateError("SecurityReceivable.security_id is required")
        if not isinstance(self.shares, Fraction):
            raise CoreStateError(
                f"§6.1.9: SecurityReceivable.shares must be an exact Fraction, "
                f"got {type(self.shares).__name__}. A float entitlement is a "
                f"rounding decision taken where none is authorised.")
        if self.shares <= 0:
            raise CoreStateError(
                f"SecurityReceivable[{self.security_id}] = {self.shares} must be "
                f"a positive claim")
        if not str(self.credit_tradable_date).strip():
            raise CoreStateError(
                f"§6.1.5: SecurityReceivable[{self.security_id}] has no "
                f"credit_tradable_date; when it becomes tradable is not "
                f"inferable from when it was created.")
        if not str(self.event_id).strip():
            raise CoreStateError(
                "I-CA-03: a security receivable must name the event that created "
                "it, or the shares are untraceable")


@dataclass(frozen=True)
class CashReceivable:
    """§6.1.4: a fixed cash claim, owned but not yet spendable."""
    amount: float
    cash_available_date: str
    event_id: str
    source_security_id: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise CoreStateError(
                f"CashReceivable amount {self.amount!r} must be finite and > 0")
        if not str(self.cash_available_date).strip():
            raise CoreStateError(
                "§6.1.5: a cash receivable has no cash_available_date; when it "
                "becomes spendable is not inferable from when it was created.")
        if not str(self.event_id).strip():
            raise CoreStateError(
                "I-CA-04: a cash receivable must name the event that created it")


@dataclass(frozen=True)
class HoldingSpell:
    """B0.1 · one continuous interval of UNDERLYING share exposure.

    The official Frozen B0 L2 run aborted because the engine asked "is this
    security in the portfolio now?" and then applied an event from 2012 to a
    position opened in 2014. Exposure has a time dimension and the state did not
    carry it, so the question could not be asked correctly.

    The interval rule is asymmetric, and the asymmetry is derived rather than
    chosen. The frozen intraday order applies corporate actions BEFORE the same
    day's execution (`INTRADAY_SEQUENCE`, §6.1.6 step 2 before step 9), and
    §6.1.7 A defines `Q` as the entitlement-bearing shares held BEFORE the
    conversion. So:

        bought on the event date  -> the shares did not exist when Q was taken
        sold on the event date    -> the shares still existed when Q was taken

    which is exactly `start < event_date <= end`.

    The driver is UNDERLYING shares, never claims. A stock-dividend receivable
    that outlives the sale of the shares that earned it stays alive under its own
    frozen lifecycle, but it does not keep this spell open: a holder of a claim
    is not a shareholder of record for the NEXT event.
    """
    stock_id: str
    start: str
    end: str = ""              # "" means still open

    def __post_init__(self) -> None:
        if not str(self.stock_id).strip():
            raise CoreStateError("a holding spell must name its security")
        if not str(self.start).strip():
            raise CoreStateError(
                f"holding spell for {self.stock_id} has no start; exposure "
                f"without a start date is the defect this type exists to remove")
        if self.end and str(self.end) < str(self.start):
            raise CoreStateError(
                f"holding spell for {self.stock_id} ends {self.end} before it "
                f"starts {self.start}")

    @property
    def open(self) -> bool:
        return not str(self.end).strip()

    def covers(self, date: str) -> bool:
        """`start < date <= end`. See the class docstring for the derivation."""
        date = str(date)
        if not (str(self.start) < date):
            return False
        return self.open or date <= str(self.end)


def record_underlying_exposure(spells, shares: Mapping[str, int],
                               as_of: str) -> tuple:
    """Advance the spell ledger to the end-of-day share ledger of `as_of`.

    Called once per period on the state that leaves execution, which is what
    `INTRADAY_SEQUENCE` calls `end_of_day_state`. Opening and closing on the
    execution date is what makes the same-day rule above come out right.
    """
    held = {sid for sid, n in dict(shares).items() if n > 0}
    out, seen_open = [], set()
    for sp in spells:
        if sp.open and sp.stock_id not in held:
            out.append(HoldingSpell(sp.stock_id, sp.start, str(as_of)))
        else:
            out.append(sp)
            if sp.open:
                seen_open.add(sp.stock_id)
    for sid in sorted(held - seen_open):
        out.append(HoldingSpell(sid, str(as_of)))
    return tuple(sorted(out, key=lambda x: (x.stock_id, x.start)))


# --- portfolio state ----------------------------------------------------------

@dataclass(frozen=True)
class PortfolioState:
    """The share ledger (§6.3): canonical unit is the share, odd lots enabled.

    `pending_exit` names positions whose exit is incomplete (§6.4). They are a
    subset of `shares`, not a separate pool: the shares are still held, still
    counted in port_value, and their unrealised proceeds are not available cash.

    §6.1.4 adds the three fields a corporate-action transition needs and that a
    plain share ledger cannot express: dated security claims, dated cash claims,
    and the exactly-once ledger of events already applied. `cash` remains
    AVAILABLE cash — the quantity execution may spend — and `shares` remains
    TRADABLE shares.
    """
    as_of: str
    cash: float
    shares: Mapping[str, int]
    pending_exit: Mapping[str, int] = field(default_factory=dict)
    cash_dividend_receivable: float = 0.0          # V-1a, credited at payment_date
    stock_dividend_receivable: Mapping[str, int] = field(default_factory=dict)
    # §6.1.4
    security_receivables: tuple = ()               # tuple[SecurityReceivable, ...]
    cash_receivables: tuple = ()                   # tuple[CashReceivable, ...]
    applied_ca_event_ids: frozenset = frozenset()  # I-CA-01, exactly-once ledger
    # §6.1.10. A full-exit obligation that survived an event which left the
    # position non-tradable (a merger successor, an uncredited stock dividend).
    # It cannot live in `pending_exit`, which is defined over shares actually
    # held; dropping it instead would let a corporate action quietly resurrect a
    # position B0 had already decided to exit.
    pending_exit_on_receivable: frozenset = frozenset()
    # B0.1 · R1. The canonical, state-owned exposure ledger. Driven by
    # UNDERLYING shares only: a claim that outlives its underlying position does
    # not keep a spell open, because the holder of a claim is not a shareholder
    # of record for the next event.
    holding_spells: tuple = ()          # tuple[HoldingSpell, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.cash):
            raise CoreStateError(f"cash must be finite, got {self.cash!r}")
        if self.cash < 0:
            raise CoreStateError(
                f"§6.4: negative cash ({self.cash}) — B0 does not borrow. This is "
                f"the no-leverage rule, not a numerical tolerance.")
        if self.cash_dividend_receivable < 0:
            raise CoreStateError("cash_dividend_receivable must be >= 0")
        for sid, n in self.shares.items():
            if not isinstance(n, int) or n < 0:
                raise CoreStateError(
                    f"§6.3: shares[{sid}] = {n!r}; the ledger holds whole shares "
                    f"and no LOT_SIZE arithmetic (G4).")
        for sid, n in self.pending_exit.items():
            if sid not in self.shares:
                raise CoreStateError(
                    f"§6.4: pending_exit[{sid}] has no position. A pending exit is "
                    f"an unfinished sale of shares still held, not a phantom.")
            if not isinstance(n, int) or n <= 0 or n > self.shares[sid]:
                raise CoreStateError(
                    f"§6.4: pending_exit[{sid}] = {n!r} is not a positive quantity "
                    f"within the {self.shares[sid]} shares held.")
        for sid, n in self.stock_dividend_receivable.items():
            if not isinstance(n, int) or n <= 0:
                raise CoreStateError(
                    f"stock_dividend_receivable[{sid}] = {n!r} must be a positive "
                    f"share count")
        for r in self.security_receivables:
            if not isinstance(r, SecurityReceivable):
                raise CoreStateError(
                    f"§6.1.4: security_receivables must hold SecurityReceivable, "
                    f"got {type(r).__name__}")
        for r in self.cash_receivables:
            if not isinstance(r, CashReceivable):
                raise CoreStateError(
                    f"§6.1.4: cash_receivables must hold CashReceivable, got "
                    f"{type(r).__name__}")

    @property
    def held_securities(self) -> tuple[str, ...]:
        """Every security B0 has an economic claim on, tradable or not.

        I-CA-08 marks over this set, so a successor security received in a merger
        is inside it from the moment the claim exists — otherwise the interval
        between the merger and the credit date would silently drop out of NAV.
        """
        return tuple(sorted(
            set(self.shares) | set(self.stock_dividend_receivable)
            | {r.security_id for r in self.security_receivables}))

    def tradable_shares(self, stock_id: str) -> int:
        """V-1b: receivable shares are NOT sellable before they are credited."""
        return int(self.shares.get(stock_id, 0))

    def spendable_cash(self) -> float:
        """§6.1.4: cash receivables are owned; they are not spendable."""
        return float(self.cash)

    def is_exposed_at(self, stock_id: str, date: str) -> bool:
        """Was B0 a shareholder of record on `date`? Ledger primitive."""
        return any(sp.covers(date) for sp in self.holding_spells
                   if sp.stock_id == stock_id)

    def exposure_applies(self, stock_id: str, event_date: str,
                         as_of: str) -> bool:
        """B0.1 · THE canonical exposure predicate.

        ONE spell must cover BOTH the event boundary and the moment of
        application. Testing the boundary alone is not enough: an event that was
        never applied while its spell was open would otherwise be applied to a
        LATER, unrelated position in the same security — the exit-then-re-entry
        case. The economic claim belongs to the exposure that earned it, and
        that exposure has to still be the one B0 holds.
        """
        return any(sp.covers(event_date) and sp.covers(as_of)
                   for sp in self.holding_spells if sp.stock_id == stock_id)

    def exposure_spells(self) -> tuple:
        """The COMPLETE historical ledger: open spells and closed ones alike.

        B0.2 · R2 names this explicitly because it was being used for two
        different questions. It answers exactly one: "every interval of
        underlying exposure B0 has ever had." Historical corporate-action
        adjudication needs all of it; a caller describing what B0 holds NOW
        needs `active_exposure_projection` instead.
        """
        return tuple(self.holding_spells)

    def active_exposure_projection(self, as_of: str = "") -> tuple:
        """B0.2 · R2: the spells that are CURRENT at `as_of`.

        The third of the three concepts, and the one that did not exist. B0.1
        had a complete historical ledger and a historical CA predicate, and then
        asked a caller's CURRENT declaration to equal the HISTORICAL ledger. The
        two agree only until the first position is fully exited, at which point
        every closed spell is a permanent mismatch — which is precisely how the
        B0.1 diagnostic replay died at period 3 with five securities bought on
        2014-08-01 and sold before 2014-09.

        "Current" is has-begun-and-has-not-ended. It is deliberately NOT
        `covers()`: `covers` answers the corporate-action question and is frozen
        by §12.4 / R3, so reusing it here would tie a projection to an interval
        rule derived for a different purpose. A spell that opened on `as_of` is
        current (B0 holds those shares) even though it is not exposed to an event
        dated `as_of` — those are different questions and now have different
        predicates.
        """
        when = str(as_of or self.as_of)
        return tuple(sp for sp in self.holding_spells
                     if str(sp.start) <= when
                     and (sp.open or when <= str(sp.end)))

    def with_underlying_exposure_recorded(self, as_of: str = "") -> "PortfolioState":
        """The end-of-day state, with its spell ledger advanced."""
        from dataclasses import replace

        return replace(self, holding_spells=record_underlying_exposure(
            self.holding_spells, self.shares, as_of or self.as_of))

    @property
    def entitlement_securities(self) -> tuple[str, ...]:
        """Securities on which a holder-affecting event would touch us (§6.1.12)."""
        return tuple(sorted(
            set(self.shares) | set(self.stock_dividend_receivable)
            | {r.security_id for r in self.security_receivables}
            | {r.source_security_id for r in self.security_receivables
               if r.source_security_id}
            | {r.source_security_id for r in self.cash_receivables
               if r.source_security_id}
            | set(self.pending_exit)))


# --- portfolio mark (§6.2) ----------------------------------------------------

@dataclass(frozen=True)
class MarkedPortfolio:
    as_of: str
    port_value: float
    cash: float
    position_values: Mapping[str, float]
    receivable_value: float
    stale_marked: tuple[str, ...]
    max_sessions_stale: int


def mark_portfolio(portfolio: PortfolioState,
                   snapshot: MarketSnapshot,
                   gap_verdicts: Sequence[object] = ()) -> MarkedPortfolio:
    """§6.2 portfolio mark, consuming O-B verdicts rather than re-deriving them.

    `gap_verdicts` are `core.b0_pit_observability.GapVerdict` values produced by
    the corporate-action stage, which by O-A has already run (that stage is
    mandatory before any valuation). They are consumed, not recomputed: the mark
    stage must not become a second place where "is this price gap explained?" is
    answered, or the two answers will eventually disagree.
    """
    if portfolio.as_of != snapshot.as_of:
        raise CoreStateError(
            f"portfolio state is as of {portfolio.as_of} but the market snapshot "
            f"is as of {snapshot.as_of}; marking across dates is not a mark.")

    by_id = {getattr(v, "stock_id"): v for v in gap_verdicts}
    held = portfolio.held_securities
    if gap_verdicts:
        missing = [s for s in held if s not in by_id]
        if missing:
            raise CoreStateError(
                f"O-A/O-B: held securities {missing} have no price-gap verdict. "
                f"The guard runs over the whole holding or it is not a guard.")
        unmarkable = [s for s in held
                      if not getattr(by_id[s], "markable", True)]
        if unmarkable:
            raise CoreStateError(
                f"O-B: {unmarkable} were classified unmarkable; "
                f"assert_no_unexplained_price_gap should already have aborted. "
                f"Reaching the mark stage with an unmarkable holding means the "
                f"mandatory stage was skipped (§6.1 O-A).")

    position_values: dict[str, float] = {}
    for sid, n in sorted(portfolio.shares.items()):
        position_values[sid] = n * snapshot.mark_price(sid)

    receivable = float(portfolio.cash_dividend_receivable)
    for sid, n in sorted(portfolio.stock_dividend_receivable.items()):
        # V-1b: not yet tradable, but NAV must include it. Excluding it would
        # understate NAV for the whole interval between ex-right and credit.
        receivable += n * snapshot.mark_price(sid)
    # §6.1.8 / I-CA-08. Same rule, applied to the dated claims a corporate-action
    # transition creates. `mark_price` fails loud on an unmarkable security, so a
    # successor received in a merger that has no canonical mark aborts here
    # rather than being valued at zero.
    for r in sorted(portfolio.security_receivables,
                    key=lambda x: (x.security_id, x.credit_tradable_date)):
        receivable += float(r.shares) * snapshot.mark_price(r.security_id)
    for r in sorted(portfolio.cash_receivables,
                    key=lambda x: (x.cash_available_date, x.event_id)):
        # Face value: a fixed cash claim is not re-priced, and discounting it
        # would be a valuation model this specification does not carry.
        receivable += float(r.amount)

    stale = tuple(sorted(s for s in held
                         if getattr(by_id.get(s), "stale_mark", False)))
    max_stale = max((int(getattr(by_id[s], "sessions_stale", 0)) for s in stale),
                    default=0)

    return MarkedPortfolio(
        as_of=portfolio.as_of,
        port_value=float(portfolio.cash) + sum(position_values.values()) + receivable,
        cash=float(portfolio.cash),
        position_values=position_values,
        receivable_value=receivable,
        stale_marked=stale,
        max_sessions_stale=max_stale,
    )
