"""Layer 1 of the canonical core (§8.7): PIT input -> canonical feature values.

Responsibility boundary, quoted from §8.7:

    b0_features   only: PIT input -> canonical feature values
                  must not know: Top20, 5%, cash, execution

So there is no portfolio in this module, no notion of how many names will be
picked, and no weight. It answers one question per security per decision date:
what is this feature worth, using only information published on or before the
prior completed trading session (§6.6 DECISION_STATE_SOURCE).

As of master preregistration v1.4 every one of the eleven members has a frozen
formula. Two were frozen from the start (`revenue_accel` by §2.1, whose A-leg
definition binds L = 18 and therefore the whole window; `value_ind_pct_b` by
§3.2). The other nine were resolved by C-17 through C-24, and none of them was
resolved by choosing: each came from a demoted closure, from the standard
definition that closure invoked, or from reading the legacy producer line by
line. Where two sources disagreed, §0.2 precedence settled it — closure prose
over legacy code — and the disagreement is recorded in §11 rather than smoothed
over.

`_FORMULA_ITEM` is therefore empty, and deliberately kept: it is the M-3 abort
path, so a member added later without a formula lands there instead of in
somebody's reasonable default. §11 C-8 is this project's shipped instance of that
failure, and §3.4's Remove list exists because earlier definitions drifted
without anyone deciding to change them.

The percentile primitive lives here rather than in `b0_decision`, even though the
member-level percentile is a scoring step, because `value_ind_pct_b` is DEFINED
as a percentile. One implementation, imported by the decision layer, is the only
arrangement in which the two layers cannot drift into different tie conventions —
which would break B-20's bit-exact parity with no visible cause.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from core.b0_open_items import raise_unspecified

CONCEPTS: tuple[str, ...] = ("Quality", "Growth", "Value", "Momentum")

# The industry assignment of a security whose PIT timeline cannot be resolved
# (§2.3, 92 securities). It is not a sector; it is the absence of one, and it
# propagates to Value = NA and thence to complete-case exclusion. It must never
# be back-filled from the current snapshot.
INDUSTRY_UNRESOLVED = "UNRESOLVED"

# §3.2: the mathematical lower bound at which a rank is defined, not a tuned
# sample threshold. MIN_PCT_SAMPLES was Removed (§3.4) and must not return.
MIN_INDUSTRY_GROUP = 2


class FeatureError(RuntimeError):
    """Fail-loud: a feature input the canonical core must not absorb."""


@dataclass(frozen=True)
class FeatureDefinition:
    """One member of the frozen feature graph (§3.1).

    `orientation` is None where the master preregistration does not fix whether a
    higher raw value should earn a higher percentile. `formula` is None where it
    does not fix how the value is computed. Both aborts route through the same
    open-item register.
    """
    key: str
    concept: str
    orientation: str | None        # "+" | "-" | None = UNSPECIFIED
    formula: str | None            # None = UNSPECIFIED
    pit_lookback_months: int
    note: str = ""

    def __post_init__(self) -> None:
        if self.concept not in CONCEPTS:
            raise FeatureError(
                f"{self.key}: concept {self.concept!r} is not one of {CONCEPTS}")
        if self.orientation not in ("+", "-", None):
            raise FeatureError(f"{self.key}: orientation must be '+', '-' or None")


# §3.1 frozen graph. Orientation is recorded as derived where the concept's
# standard definition fixes it uniquely (a Growth member scores growth, a Value
# member defined as "higher = cheaper" scores cheapness — §3.2 cites Fama-French
# HML explicitly, whose long leg is high book-to-market). It is left UNSPECIFIED
# for the two members whose raw metric points against its own concept name:
# scored the wrong way those do not add noise, they inverse the concept, and
# nothing downstream can detect it.
FEATURE_GRAPH: tuple[FeatureDefinition, ...] = (
    # Quality
    FeatureDefinition("roe", "Quality", "+", "ttm_net_income_over_period_end_equity",
                      13, "C-21: TTM per closure, period-end denominator per lineage"),
    FeatureDefinition("net_margin", "Quality", "+", "ttm_aggregate_margin", 13,
                      "C-21: TTM profit over TTM revenue, not a mean of ratios"),
    FeatureDefinition("gross_margin", "Quality", "+", "ttm_aggregate_margin", 13,
                      "C-21"),
    FeatureDefinition("debt_to_asset", "Quality", "-", "current_quarter_ratio", 4,
                      "C-19 direction '−'; C-22 current-quarter balance sheet"),
    FeatureDefinition("current_ratio", "Quality", "+", "current_quarter_ratio", 4,
                      "C-22"),
    # Growth
    FeatureDefinition("revenue_yoy", "Growth", "+", "single_month_yoy", 13,
                      "C-23: the 13-month lookback admits exactly one reading"),
    FeatureDefinition("revenue_accel", "Growth", "+", "a_leg_3m_mean_diff", 18,
                      "§2.1: the window-binding factor; L = 18 derives from it"),
    FeatureDefinition("eps_growth", "Growth", "+", "quarterly_yoy_abs_denominator",
                      16, "C-18: lineage-confirmed against the legacy producer"),
    # Value
    FeatureDefinition("value_ind_pct_b", "Value", "+",
                      "pit_industry_bm_percentile", 0,
                      "§3.2: higher = cheaper; B/M = 1 / PBR_TSE"),
    FeatureDefinition("PEG", "Value", "-", "standard_peg_positive_domain", 16,
                      "C-17: standard PEG, lower is better; defined only on "
                      "PE > 0 and growth > 0"),
    # Momentum
    FeatureDefinition("momentum_12_1", "Momentum", "+", "price_return_12_1", 13,
                      "C-24: price relative from t-13 to t-1"),
)

FEATURE_BY_KEY: dict[str, FeatureDefinition] = {f.key: f for f in FEATURE_GRAPH}

# §3.4 — Removed and not revivable. Named so that a reintroduction is a diff, not
# an archaeology exercise.
REMOVED_FEATURES: tuple[str, ...] = (
    "asset_turnover", "rev_cagr", "cum_yoy", "streak", "value_ind_pct",
    "pe_vs_industry", "high52_prox", "momentum20_pct", "eps_cagr",
    "MIN_PCT_SAMPLES", "PE_HISTORY_START", "FUSION_PCT", "TOP_N",
    "DATA_START_CUTOFF",
)

# §2.1: the frozen lookback. A retained feature needing more than this is the
# ONLY condition that unfreezes the window — and never performance.
LOOKBACK_L_MONTHS = 18


def required_feature_keys() -> tuple[str, ...]:
    """Every member of the graph. §4.1 complete-case is defined over exactly this."""
    return tuple(f.key for f in FEATURE_GRAPH)


def concept_members(concept: str) -> tuple[str, ...]:
    if concept not in CONCEPTS:
        raise FeatureError(f"unknown concept {concept!r}; frozen: {CONCEPTS}")
    return tuple(f.key for f in FEATURE_GRAPH if f.concept == concept)


def assert_not_revived(keys: Sequence[str]) -> None:
    """§3.4: a Removed feature reaching the core aborts."""
    revived = sorted(set(keys) & set(REMOVED_FEATURES))
    if revived:
        raise FeatureError(
            f"§3.4: {revived} were Removed from the feature graph and may not be "
            f"revived. Their removal is part of what makes the frozen window 141 "
            f"months long; reintroducing one silently changes L.")


def assert_lookback_within_L() -> None:
    """§2.1: the sole unfreeze condition is a retained feature exceeding L."""
    over = [(f.key, f.pit_lookback_months) for f in FEATURE_GRAPH
            if f.pit_lookback_months > LOOKBACK_L_MONTHS]
    if over:
        raise FeatureError(
            f"§2.1: {over} exceed the frozen lookback L = {LOOKBACK_L_MONTHS}. "
            f"This is the one condition that unfreezes the window — it must be "
            f"ruled on, not absorbed.")


def orientation(key: str) -> str:
    """The sign with which a raw value enters its percentile (§3.1, C-19).

    Bound to the feature definition, never supplied by a caller. A layer that
    could pass `ascending=True/False` per call would make direction a runtime
    choice, and a direction chosen at the call site does not add noise — it
    inverts the concept while leaving a well-formed SelectionScore behind.
    """
    f = FEATURE_BY_KEY.get(key)
    if f is None:
        raise FeatureError(f"{key!r} is not a member of the frozen feature graph")
    if f.orientation is None:
        raise_unspecified("feature_orientation", context=key)
    return f.orientation


def feature_percentile(key: str, values: Mapping[str, float], *,
                       convention: str) -> dict[str, float]:
    """Cross-sectional percentile of ONE member, oriented by its definition.

    This is the only entry point the decision layer uses. It deliberately has no
    direction parameter: `orientation()` answers that from the frozen graph.
    """
    return percentile_rank(values, convention=convention,
                           ascending=(orientation(key) == "+"))


# --- the percentile primitive -------------------------------------------------
# C-35: average rank over ties. Equal raw values receive EQUAL percentiles, and
# the result does not depend on the order rows arrived in — which is what makes
# B-20's bit-exact parity achievable across two adapters that build their panels
# differently.
#
# The `ordinal_rank` alternative is removed rather than left selectable. It would
# have had to break ties by something, and the only something available is the
# row order or the stock id: the first makes the output adapter-dependent, the
# second leaks the PORTFOLIO tie-break (C-33) back into FEATURE scoring, where a
# security would gain alpha for having a low stock id.
#
# `convention` stays an explicit argument even though only one value is legal,
# for the same reason as C-16's drift policy: a call site that names what it
# believes it is computing cannot silently inherit something else later.

PERCENTILE_CONVENTION = "average_rank"
PERCENTILE_CONVENTIONS: tuple[str, ...] = (PERCENTILE_CONVENTION,)


def percentile_rank(values: Mapping[str, float], *, convention: str,
                    ascending: bool = True) -> dict[str, float]:
    """Continuous cross-sectional percentile on [0, 1].

    `ascending=True` means the lowest raw value receives the lowest percentile.
    Feature orientation is applied by the caller, not inferred here.
    """
    if convention != PERCENTILE_CONVENTION:
        raise FeatureError(
            f"C-35: the cross-sectional percentile convention is frozen to "
            f"{PERCENTILE_CONVENTION!r}; got {convention!r}. Equal raw values must "
            f"receive equal percentiles, and the result must not depend on row "
            f"order — an ordinal convention would have to break ties by the row "
            f"order or by the stock id, and the second would leak the portfolio "
            f"tie-break (C-33) into feature scoring.")
    if not values:
        return {}
    for sid, v in values.items():
        if v is None or not math.isfinite(float(v)):
            raise FeatureError(
                f"percentile_rank: {sid} has non-finite value {v!r}. §4.1 removes "
                f"incomplete cases before ranking; a NaN reaching here means the "
                f"complete-case gate was bypassed.")

    n = len(values)
    if n < MIN_INDUSTRY_GROUP:
        # §3.2 records 2 as the mathematical lower bound at which a rank is
        # defined, not as a tuned sample threshold. A one-member cross-section
        # carries no rank information: 0.5 would assert median-ness and 0 or 1
        # would assert an extreme, and all three would be inventions.
        raise FeatureError(
            f"percentile_rank: {n} member(s) in the cross-section; a rank is "
            f"defined only from {MIN_INDUSTRY_GROUP} (§3.2). Callers decide what "
            f"an undefined percentile means in their layer — this function does "
            f"not manufacture one.")

    # Grouped by VALUE, never sorted by stock_id. Sorting by (value, stock_id)
    # would produce the same numbers here, but it would mean the identifier is
    # part of the computation — and the next person to add a convention would
    # inherit that. Distinct values are ordered; tied values form one group.
    distinct = sorted({float(v) for v in values.values()}, reverse=not ascending)
    members: dict[float, list[str]] = {}
    for sid, v in values.items():
        members.setdefault(float(v), []).append(sid)

    out: dict[str, float] = {}
    position = 0
    for value in distinct:
        group = members[value]
        span = len(group)
        # Tied values share the mean of the ranks the group spans, so every
        # member of the group gets the identical percentile (C-35).
        avg = position + (span - 1) / 2.0
        for sid in group:
            out[sid] = avg / (n - 1)
        position += span
    return out


# --- the two determined feature computations ---------------------------------

REVENUE_ACCEL_YOYS_REQUIRED = 6


def compute_revenue_accel(yoys: Sequence[float]) -> float | None:
    """§2.1 A-leg: mean(last 3 YoY) - mean(prior 3 YoY). Needs 6 YoYs.

    This is the factor the frozen window is bound to: L = 18 is derived from it,
    so its formula is not an implementation detail — a change here moves the
    first eligible decision month.

    Written here rather than imported from `core.b0_parity`, whose two functions
    declare themselves a negative control for drift ("neither is B0's
    definition"). Depending on a negative control would mean that editing the
    demonstration edits the strategy. The two are pinned to agree by test
    instead, which is the stronger arrangement: §11 C-8 records that `rev_accel`
    already shipped as two different formulas under one name, and an equality
    assertion is what would have caught it.

    Returns None when fewer than six YoYs are available point-in-time. That is an
    absence, not a zero: §4.1 excludes the whole row, and nothing is imputed.
    """
    usable = [float(v) for v in yoys
              if v is not None and math.isfinite(float(v))]
    if len(usable) < REVENUE_ACCEL_YOYS_REQUIRED:
        return None
    return sum(usable[-3:]) / 3.0 - sum(usable[-6:-3]) / 3.0


def compute_value_ind_pct_b(pbr_tse: Mapping[str, float],
                            pit_industry: Mapping[str, str],
                            *, convention: str) -> dict[str, float | None]:
    """§3.2 Ruling B: within-PIT-industry cross-sectional percentile of B/M.

    B/M = 1 / PBR_TSE, higher = cheaper. Returns None for any security whose
    value is not defined at this date — an UNRESOLVED PIT industry (§2.3), a
    missing or non-positive PBR, or an industry group below the minimum at which
    a rank exists. None propagates to complete-case exclusion (§4.1); it is never
    imputed and never back-filled from a current snapshot.

    Lineage caveat that travels with any use of this number (§3.2): `1/PBR_TSE`
    is certified as canonical BE/ME IN AGGREGATE only — 12 annual median ratios
    in 0.936-1.091 — with wide row-level dispersion. Row-level certification
    would need TEJ's definition document, which is a known-unobtainable vendor
    dependency and must not be substituted with any non-authoritative account.
    """
    groups: dict[str, dict[str, float]] = {}
    undefined: list[str] = []

    for sid, ind in pit_industry.items():
        if ind == INDUSTRY_UNRESOLVED or not str(ind).strip():
            undefined.append(sid)
            continue
        pbr = pbr_tse.get(sid)
        if pbr is None or not math.isfinite(float(pbr)) or float(pbr) <= 0:
            # Non-positive book-to-price is not "expensive", it is undefined.
            undefined.append(sid)
            continue
        groups.setdefault(str(ind), {})[sid] = 1.0 / float(pbr)

    out: dict[str, float | None] = {sid: None for sid in undefined}
    for ind, members in groups.items():
        if len(members) < MIN_INDUSTRY_GROUP:
            for sid in members:
                out[sid] = None
            continue
        ranked = percentile_rank(members, convention=convention, ascending=True)
        out.update(ranked)
    return out


# --- Quality: TTM profitability (C-21) ---------------------------------------
# B-09 Phase 3 §5 groups roe / net_margin / gross_margin under "Quality TTM" at a
# 13-month lookback, while the legacy producer computes all three from a single
# quarter (`core/data_provider.py:628-636`, whose own comment reads
# "近似 ROE(單季)"). §0.2 settles the conflict: closure prose outranks legacy
# code, so B0 is TTM. The legacy code still decides the parts the closure is
# silent about — the period-end denominator and the percentage-point unit.

TTM_QUARTERS = 4


def _last_n(values: Sequence[float | None], n: int) -> list[float] | None:
    """The n most recent quarters, or None if any of them is unusable.

    Deliberately not "the n most recent usable values": skipping a quarter with
    no report would silently compare a 4-quarter sum against a 3-quarter one.
    """
    if len(values) < n:
        return None
    window = list(values[-n:])
    if any(v is None or not math.isfinite(float(v)) for v in window):
        return None
    return [float(v) for v in window]


def compute_roe_ttm(net_income_by_quarter: Sequence[float | None],
                    period_end_equity: float | None) -> float | None:
    """Return on equity, trailing twelve months, in PERCENTAGE POINTS.

        roe = ( Σ_{k=0..3} net_income_{q-k} ) / equity_q * 100

    numerator   sum of the four most recent quarterly net incomes, where q is the
                latest quarter whose real publication date is on or before the
                decision date (§2.2, C-22)
    denominator PERIOD-END equity of that same quarter q — not average equity,
                and not equity from any later statement

    Period-end rather than average because that is what the legacy producer used
    (`net_inc / equity`), and because average equity would need a second
    statement date whose PIT availability is a separate question the closure
    never opened.

    equity <= 0 -> None. A negative denominator flips the sign of the ratio while
    leaving it well-formed: a profitable company with negative book equity would
    score as deeply unprofitable. This follows the same principle C-17 applied to
    PEG — the positive domain is part of the measure, not a filter on it.
    """
    ni = _last_n(net_income_by_quarter, TTM_QUARTERS)
    if ni is None or period_end_equity is None:
        return None
    eq = float(period_end_equity)
    if not math.isfinite(eq) or eq <= 0:
        return None
    return sum(ni) / eq * 100.0


def compute_margin_ttm(profit_by_quarter: Sequence[float | None],
                       revenue_by_quarter: Sequence[float | None]) -> float | None:
    """`net_margin` / `gross_margin`, trailing twelve months, PERCENTAGE POINTS.

        margin = ( Σ_{k=0..3} profit_{q-k} ) / ( Σ_{k=0..3} revenue_{q-k} ) * 100

    Aggregate over aggregate, not the mean of four quarterly ratios. A margin is
    profit per unit of revenue, so the twelve-month margin is twelve months of
    profit over twelve months of revenue; averaging ratios would weight a quiet
    quarter equally with a peak one and is not what "TTM margin" denotes
    anywhere. This is the standard-definition-first principle §3.2 already
    invokes.

    Revenue sum <= 0 -> None.
    """
    p = _last_n(profit_by_quarter, TTM_QUARTERS)
    r = _last_n(revenue_by_quarter, TTM_QUARTERS)
    if p is None or r is None:
        return None
    total_revenue = sum(r)
    if total_revenue <= 0:
        return None
    return sum(p) / total_revenue * 100.0


# --- Quality: current-quarter balance sheet (C-22) ----------------------------
# B-09 Phase 3 §5 lists these separately as "Quality 當期(負債比/流動比)" at a
# 4-month lookback: point-in-time balance-sheet ratios, not TTM flows. Which
# statement is "current" at a month-end is already frozen by §2.2 — the latest
# one whose real publication date is on or before the decision date, never a
# fixed lag proxy.

def latest_published_statement(statements: Sequence[Mapping[str, object]],
                               as_of: str, *,
                               date_key: str = "release_date") -> Mapping | None:
    """§2.2: the most recent statement actually published by `as_of`.

    A statement dated before `as_of` but published after it is not available;
    this is why B0 reads real publication dates and forbids fixed-lag proxies.
    """
    published = [s for s in statements
                 if s.get(date_key) and str(s[date_key]) <= str(as_of)]
    if not published:
        return None
    return max(published, key=lambda s: str(s[date_key]))


def compute_debt_to_asset(total_liabilities: float | None,
                          total_assets: float | None) -> float | None:
    """Percentage points, current quarter. Lower is better (C-19)."""
    if total_liabilities is None or total_assets is None:
        return None
    liab, assets = float(total_liabilities), float(total_assets)
    if not math.isfinite(liab) or not math.isfinite(assets) or assets <= 0:
        return None
    return liab / assets * 100.0


def compute_current_ratio(current_assets: float | None,
                          current_liabilities: float | None) -> float | None:
    """Percentage points, current quarter (the legacy unit: 150.0 means 1.5x)."""
    if current_assets is None or current_liabilities is None:
        return None
    ca, cl = float(current_assets), float(current_liabilities)
    if not math.isfinite(ca) or not math.isfinite(cl) or cl <= 0:
        return None
    return ca / cl * 100.0


# --- Growth: revenue_yoy (C-23) ----------------------------------------------

REVENUE_YOY_MONTHS_BACK = 12


def compute_revenue_yoy(monthly_revenue: Sequence[float | None]) -> float | None:
    """Single-month year-over-year revenue growth, in PERCENTAGE POINTS.

        revenue_yoy_m = (revenue_m - revenue_{m-12}) / |revenue_{m-12}| * 100

    The single-month reading is not a preference: B-09 Phase 3 §5 gives this
    member a 13-month lookback, and 13 = 1 month + 12 for the comparison. A
    3-month-mean YoY would need 15, so the frozen lookback admits exactly one
    reading. (`revenue_accel` is the member built from 3-month means, and §2.1
    gives it 18 accordingly.)

    Unit and denominator form follow C-18, so that `revenue_accel` — a difference
    of two YoY means — operates on quantities in one scale.
    """
    if len(monthly_revenue) < REVENUE_YOY_MONTHS_BACK + 1:
        return None
    latest = monthly_revenue[-1]
    base = monthly_revenue[-1 - REVENUE_YOY_MONTHS_BACK]
    if latest is None or base is None:
        return None
    latest, base = float(latest), float(base)
    if not math.isfinite(latest) or not math.isfinite(base) or base == 0:
        return None
    return (latest - base) / abs(base) * 100.0


# --- Momentum: 12-1 (C-24) ----------------------------------------------------

MOMENTUM_SKIP_MONTHS = 1
MOMENTUM_FORMATION_MONTHS = 12


def compute_momentum_12_1(month_end_prices: Sequence[float | None]) -> float | None:
    """12-1 PRICE momentum, in PERCENTAGE POINTS.

        momentum = (P_{t-1} / P_{t-13} - 1) * 100

    Twelve months of price change ending one month before the decision date. The
    endpoints follow from the frozen 13-month lookback: reaching P_{t-13} from t
    needs exactly 13 months of history.

    PRICE return, not total return. §3.1 names the member "12-1 price momentum",
    and the standard Jegadeesh-Titman construction is a price relative. This is
    also the one place where §2.5's dividend requirement does NOT reach: that
    clause governs NAV and benchmark construction, where excluding dividends
    would understate both; a momentum FEATURE is a ranking signal, and its frozen
    name settles which relative it is.

    The price series must already be adjusted for the share-count events of
    §2.4 — a split shows up in an unadjusted series as a -50% momentum reading
    that has nothing to do with the return anyone earned. Adjustment is not a
    choice this function makes; it is a property of the input the corporate-
    action stage has already produced.
    """
    need = MOMENTUM_FORMATION_MONTHS + MOMENTUM_SKIP_MONTHS
    if len(month_end_prices) < need + 1:
        return None
    end = month_end_prices[-1 - MOMENTUM_SKIP_MONTHS]
    start = month_end_prices[-1 - need]
    if end is None or start is None:
        return None
    end, start = float(end), float(start)
    if not math.isfinite(end) or not math.isfinite(start) or start <= 0:
        return None
    return (end / start - 1.0) * 100.0


# --- eps_growth (C-18: horizon from closure, form from lineage) ---------------

EPS_GROWTH_QUARTERS_BACK = 4          # "季 YoY" = the same quarter one year earlier


def compute_eps_growth(eps_by_quarter: Sequence[float]) -> float | None:
    """Quarterly year-over-year EPS growth, in PERCENTAGE POINTS.

        eps_growth = (EPS_t - EPS_{t-4}) / |EPS_{t-4}| * 100

    Three parts, three different sources, recorded so the next reader does not
    have to redo the archaeology:

      * horizon — B-09 Phase 3 §5 states "eps_growth (季 YoY)", lookback 16.
      * denominator and unit — read off the legacy producer. `eps_cagr` was never
        a CAGR: it is `fundamental_data["eps_growth"]`, produced by
        `core.data_provider.DataProvider._yoy_growth`, which returns
        `(latest - prior) / abs(prior) * 100.0`. The absolute value in the
        denominator keeps the sign of the growth meaningful when the base period
        was a loss, and the result is percentage points, not a decimal fraction.
      * indexing — B0 compares fiscal quarter t with quarter t-4 directly. The
        legacy producer matched by date proximity to (latest - 365 days) with a
        +/-60 day acceptance window; that tolerance is NOT carried over. It is a
        free parameter, it sits in the Selection path, and §9.1 S-1 puts the
        count of those at zero. B0 has quarter indices and needs no tolerance.

    Deliberately NOT carried over: the legacy fallback
    `if eps_growth is None: eps_growth = net_income_growth`
    (`core/data_provider.py:656-657`). Substituting a different series for a
    missing one is imputation, and §4.1 forbids it in as many words — the row
    leaves under complete-case instead. Keeping the fallback would also put two
    different measures under one name, which is the §11 C-8 failure exactly.

    Returns None when there is no comparable base quarter or the base is zero.
    """
    series = [None if v is None or not math.isfinite(float(v)) else float(v)
              for v in eps_by_quarter]
    if len(series) < EPS_GROWTH_QUARTERS_BACK + 1:
        return None
    latest = series[-1]
    base = series[-1 - EPS_GROWTH_QUARTERS_BACK]
    if latest is None or base is None or base == 0.0:
        return None
    return (latest - base) / abs(base) * 100.0


# --- PEG (C-17: standard definition, positive domain only) --------------------

def compute_peg(per_tse: float | None,
                eps_growth_pct: float | None) -> float | None:
    """Standard PEG = PE / EPS growth in percentage points. Lower is better.

    Defined only where PE > 0 AND growth > 0. Everywhere else it is NA, which
    §4.1 turns into exclusion of the whole row.

    The positive domain is the definition, not a filter. Allowing negatives would
    let PE = -10 with growth = -20% produce PEG = +0.5 — a number that ranks as
    "cheap growth" while describing a loss-making company whose earnings are
    shrinking. A signed PEG is not a stricter version of PEG; it is a different
    quantity with an inverted meaning in one of its quadrants.

    UNIT: `eps_growth_pct` is in percentage points because `compute_eps_growth`
    returns percentage points (C-18). If a caller ever supplies a decimal
    fraction, PEG comes out 100x too large — so the unit is asserted at the call
    site by construction rather than trusted.

    The resulting missingness is conditional on the cycle: in a bad year more
    names have non-positive growth and leave the universe. §3.2 already records
    that pattern as a conditional universe change rather than random
    missingness, so §9.7 carries PEG availability as a mandatory diagnostic. It
    is reported, never used to adjust the specification.
    """
    if per_tse is None or eps_growth_pct is None:
        return None
    pe = float(per_tse)
    g = float(eps_growth_pct)
    if not math.isfinite(pe) or not math.isfinite(g):
        return None
    if pe <= 0 or g <= 0:
        return None
    return pe / g


def peg_availability_report(peg_values: Mapping[str, float | None]) -> dict:
    """§9.7 mandatory diagnostic: how much of the universe PEG removes."""
    total = len(peg_values)
    defined = sum(1 for v in peg_values.values() if v is not None)
    return {
        "universe": total,
        "peg_defined": defined,
        "peg_na": total - defined,
        "peg_coverage": (defined / total) if total else 0.0,
    }


# --- per-member dispatch ---------------------------------------------------

def feature_value(key: str, **inputs) -> float:
    """Compute one canonical feature value. Aborts where §3 fixes no formula."""
    f = FEATURE_BY_KEY.get(key)
    if f is None:
        assert_not_revived([key])
        raise FeatureError(
            f"{key!r} is not a member of the frozen feature graph "
            f"{required_feature_keys()}")
    if f.formula is None:
        raise_unspecified(_FORMULA_ITEM[key], context=key)
    if key == "revenue_accel":
        return compute_revenue_accel(inputs["yoys"])
    if key == "eps_growth":
        return compute_eps_growth(inputs["eps_by_quarter"])
    if key == "PEG":
        return compute_peg(inputs.get("per_tse"), inputs.get("eps_growth_pct"))
    if key == "roe":
        return compute_roe_ttm(inputs["net_income_by_quarter"],
                               inputs.get("period_end_equity"))
    if key in ("net_margin", "gross_margin"):
        return compute_margin_ttm(inputs["profit_by_quarter"],
                                  inputs["revenue_by_quarter"])
    if key == "debt_to_asset":
        return compute_debt_to_asset(inputs.get("total_liabilities"),
                                     inputs.get("total_assets"))
    if key == "current_ratio":
        return compute_current_ratio(inputs.get("current_assets"),
                                     inputs.get("current_liabilities"))
    if key == "revenue_yoy":
        return compute_revenue_yoy(inputs["monthly_revenue"])
    if key == "momentum_12_1":
        return compute_momentum_12_1(inputs["month_end_prices"])
    raise FeatureError(
        f"{key}: has a frozen formula ({f.formula!r}) but no per-security call "
        f"path; `value_ind_pct_b` is cross-sectional and is computed by "
        f"`compute_value_ind_pct_b` over the whole universe at once.")


# Which open item covers which member's formula.
# Empty as of v1.4: every member of the frozen graph now has a frozen formula.
# Kept rather than deleted because the abort path it feeds is the M-3 mechanism —
# a member added later without a formula must land here, not in a default.
_FORMULA_ITEM: dict[str, str] = {}


# --- the panel the decision layer consumes ------------------------------------

@dataclass(frozen=True)
class FeaturePanel:
    """Canonical feature values for one decision date.

    `values[stock_id][feature_key]` is a float or None. None means "not available
    point-in-time", which §4.1 turns into exclusion of the whole row — never into
    an imputed value and never into partial scoring.
    """
    as_of: str
    values: Mapping[str, Mapping[str, float | None]]

    def __post_init__(self) -> None:
        required = set(required_feature_keys())
        for sid, row in self.values.items():
            extra = set(row) - required
            if extra:
                assert_not_revived(sorted(extra))
                raise FeatureError(
                    f"{sid}: {sorted(extra)} are not members of the frozen graph. "
                    f"A feature that is not in §3.1 does not enter SelectionScore.")
            missing = required - set(row)
            if missing:
                raise FeatureError(
                    f"{sid}: missing feature keys {sorted(missing)}. The panel must "
                    f"state availability for every member — an absent key and an "
                    f"unavailable value are different claims, and §4.1 acts on the "
                    f"second.")

    def available(self, stock_id: str) -> tuple[str, ...]:
        row = self.values[stock_id]
        return tuple(k for k in required_feature_keys() if row.get(k) is not None)

    def is_complete(self, stock_id: str) -> bool:
        return len(self.available(stock_id)) == len(required_feature_keys())


# --- the panel builder (P-2) --------------------------------------------------
# §8.7 gives this layer "PIT input -> canonical feature values", so assembling
# the panel belongs here and NOT in an adapter. If an adapter built panels, each
# one would decide which function computes which member, and the two would be two
# feature layers wearing the word "adapter".

@dataclass(frozen=True)
class SecurityPitInputs:
    """Raw PIT inputs for ONE security at ONE decision date.

    Quarterly and monthly series run oldest -> newest and must already be
    filtered to what was published on or before `as_of` (§2.2). This module does
    not filter by date: an adapter that hands over unpublished figures has
    already broken PIT, and the guard for that is the adapter's own contract plus
    `assert_feature_inputs_are_pit`.
    """
    stock_id: str
    net_income_by_quarter: tuple[float | None, ...] = ()
    revenue_by_quarter: tuple[float | None, ...] = ()
    gross_profit_by_quarter: tuple[float | None, ...] = ()
    eps_by_quarter: tuple[float | None, ...] = ()
    period_end_equity: float | None = None
    total_liabilities: float | None = None
    total_assets: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    monthly_revenue: tuple[float | None, ...] = ()
    month_end_prices: tuple[float | None, ...] = ()
    per_tse: float | None = None
    pbr_tse: float | None = None
    pit_industry: str = INDUSTRY_UNRESOLVED


def _trailing_revenue_yoys(monthly_revenue: Sequence[float | None],
                           count: int) -> list[float | None]:
    """The `count` most recent monthly YoYs, newest last.

    Each one comes from `compute_revenue_yoy` rather than from a second growth
    formula written here, so `revenue_accel` is a difference of exactly the
    quantity `revenue_yoy` reports (§3.5).
    """
    out: list[float | None] = []
    for back in range(count - 1, -1, -1):
        series = monthly_revenue[:len(monthly_revenue) - back] if back else monthly_revenue
        out.append(compute_revenue_yoy(series))
    return out


def build_feature_panel(as_of: str,
                        inputs: Sequence[SecurityPitInputs],
                        *, convention: str) -> FeaturePanel:
    """Raw PIT inputs -> the canonical panel. The only panel builder in B0.

    `value_ind_pct_b` is computed over the PIT-INDUSTRY cross-section of the
    supplied universe, not over the eligible set. That is forced rather than
    chosen: §4.1 makes availability of this member one of the conditions for
    being eligible, so a definition that needed the eligible set first would be
    circular. §3.2 says the group is the industry, and the industry it is.

    Every other member is per-security and therefore independent of which names
    are present.
    """
    by_id = {s.stock_id: s for s in inputs}
    if len(by_id) != len(inputs):
        raise FeatureError("build_feature_panel: duplicate stock_id in inputs")

    value_pct = compute_value_ind_pct_b(
        {s.stock_id: s.pbr_tse for s in inputs if s.pbr_tse is not None},
        {s.stock_id: s.pit_industry for s in inputs},
        convention=convention)

    values: dict[str, dict[str, float | None]] = {}
    for s in inputs:
        eps_growth = compute_eps_growth(s.eps_by_quarter)
        yoys = _trailing_revenue_yoys(s.monthly_revenue, 6)
        row: dict[str, float | None] = {
            "roe": compute_roe_ttm(s.net_income_by_quarter, s.period_end_equity),
            "net_margin": compute_margin_ttm(s.net_income_by_quarter,
                                             s.revenue_by_quarter),
            "gross_margin": compute_margin_ttm(s.gross_profit_by_quarter,
                                               s.revenue_by_quarter),
            "debt_to_asset": compute_debt_to_asset(s.total_liabilities,
                                                   s.total_assets),
            "current_ratio": compute_current_ratio(s.current_assets,
                                                   s.current_liabilities),
            "revenue_yoy": compute_revenue_yoy(s.monthly_revenue),
            "revenue_accel": (compute_revenue_accel([y for y in yoys if y is not None])
                              if all(y is not None for y in yoys) else None),
            "eps_growth": eps_growth,
            "value_ind_pct_b": value_pct.get(s.stock_id),
            "PEG": compute_peg(s.per_tse, eps_growth),
            "momentum_12_1": compute_momentum_12_1(s.month_end_prices),
        }
        values[s.stock_id] = row
    return FeaturePanel(as_of, values)


def assert_feature_inputs_are_pit(decision_date: str,
                                  input_dates: Mapping[str, str]) -> None:
    """§6.6: every decision input is dated strictly before the decision date."""
    from core.b0_master_prereg import assert_decision_inputs_are_prior_session
    assert_decision_inputs_are_prior_session(decision_date, input_dates)


# --- 4.1a - input sufficiency, derived from the frozen members ----------------
# READ-ONLY introspection. Nothing here defines, changes or reinterprets a
# financial formula; every number is assembled from the constants the members
# already froze, so the requirement cannot drift away from the computation.
#
# It exists because the first sealed L2 run rejected 100% of the universe in all
# 141 periods: `revenue_accel` needs 18 months of monthly revenue and the
# materializer supplied 13. Nothing compared the two, and 141/141 reproducible
# hashes cannot compare them - identical inputs hash identically whether or not
# they are long enough.

INPUT_SERIES: tuple[str, ...] = (
    "net_income_by_quarter", "revenue_by_quarter", "gross_profit_by_quarter",
    "eps_by_quarter", "monthly_revenue", "month_end_prices",
)


def member_input_requirements() -> dict:
    """{member: {series: minimum length}}, derived, never restated."""
    ttm = TTM_QUARTERS
    eps_q = EPS_GROWTH_QUARTERS_BACK + 1
    yoy_m = REVENUE_YOY_MONTHS_BACK + 1
    accel_m = yoy_m + REVENUE_ACCEL_YOYS_REQUIRED - 1
    mom_m = MOMENTUM_FORMATION_MONTHS + MOMENTUM_SKIP_MONTHS + 1
    return {
        "roe": {"net_income_by_quarter": ttm},
        "net_margin": {"net_income_by_quarter": ttm, "revenue_by_quarter": ttm},
        "gross_margin": {"gross_profit_by_quarter": ttm, "revenue_by_quarter": ttm},
        "debt_to_asset": {},
        "current_ratio": {},
        "eps_growth": {"eps_by_quarter": eps_q},
        "PEG": {"eps_by_quarter": eps_q},
        "revenue_yoy": {"monthly_revenue": yoy_m},
        "revenue_accel": {"monthly_revenue": accel_m},
        "momentum_12_1": {"month_end_prices": mom_m},
        "value_ind_pct_b": {},
    }


def series_requirements() -> dict:
    """{series: deepest requirement across all frozen members}.

    Consumer-specific by construction. `lookback_L_months = 18` is the deepest
    MONTHLY dependency horizon - set by `revenue_accel` - and is not a universal
    length every monthly array must have.
    """
    out = {k: 0 for k in INPUT_SERIES}
    for reqs in member_input_requirements().values():
        for series, n in reqs.items():
            out[series] = max(out[series], n)
    return out


# 4.1a-R2. The positional readers above (`series[-1]` vs `series[-13]` / `[-5]`)
# require a calendar-indexed series: a compressed one silently shifts the
# comparison base. Declared so a producer can be checked against it.
CALENDAR_INDEXED_SERIES: tuple[str, ...] = (
    "net_income_by_quarter", "revenue_by_quarter", "gross_profit_by_quarter",
    "eps_by_quarter", "monthly_revenue", "month_end_prices",
)
MISSING_PERIOD_ENCODING = "explicit_None"
COMPRESSING_MISSING_PERIODS_ALLOWED = False

# Declared zero-margin supplies. Stating them is the point: a margin of 0 is
# "exactly sufficient", and it must be a decision somebody made rather than a
# coincidence a future formula change would silently break. Both entries are
# ruled: supply is set to the requirement rather than padded, so that a member
# whose horizon deepens turns the sufficiency test red instead of being absorbed
# by slack nobody could justify.
INTENTIONAL_ZERO_MARGIN: tuple[str, ...] = ("month_end_prices", "monthly_revenue")
