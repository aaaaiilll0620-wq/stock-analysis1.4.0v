"""Layer 3 of the canonical core (§8.7): eligible names -> SelectionScore -> targets.

Responsibility boundary, quoted from §8.7:

    b0_decision   only: eligible names + canonical features + portfolio state
                        -> SelectionScore -> rank -> Top20 -> 5% targets
                  must not: re-implement the feature formulas

The prohibition is why this module imports the percentile primitive from
`b0_features` instead of carrying its own: two implementations of one convention
is how bit-exact B-20 parity fails with no visible cause. `FORBIDDEN_SYMBOLS`
records the formula entry points this layer must never reference, and the test
suite checks it by AST rather than by reading.

Scoring, from §3.1, with zero manual cut-points and zero free parameters:

    every member  -> continuous cross-sectional percentile over the ELIGIBLE set
    within concept-> equal weight
    across concept-> equal weight
    SelectionScore = mean(Quality, Growth, Value, Momentum)

The cross-section is the eligible set, not the raw universe, because §4.5 places
exclusion strictly before ordering: percentiles taken over names that were about
to be excluded would rank survivors against non-participants.

Sizing, from §5, is deliberately rigid:

    N_target = 20,  w_target = w_max = 5% per name, fixed
    len(selected) = min(20, len(eligible))
    sum(w) <= 100%, and a shortfall goes to cash — never to renormalisation

1/n weighting is forbidden in as many words. Fifteen eligible names means
15 x 5% = 75% invested and 25% cash, NOT 6.67% each: renormalising would make
w_max vacuous and would push single-name exposure to its maximum in exactly the
periods when the opportunity set — and usually liquidity with it — is thinnest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from core.b0_features import (
    CONCEPTS,
    FeaturePanel,
    concept_members,
    feature_percentile,
    required_feature_keys,
)

# Feature-formula entry points this layer must never touch (§8.7). Checked by AST
# in tests/test_b0_decision.py, in the same spirit as assert_no_scattered_dispatch.
#
# `percentile_rank` is on the list even though it is not a formula: it takes an
# `ascending` argument, so calling it here would put feature direction back in
# the hands of the call site. C-19 binds direction to the feature definition, and
# `feature_percentile` is the entry point that has no way to override it.
FORBIDDEN_SYMBOLS: tuple[str, ...] = (
    "compute_revenue_accel", "compute_value_ind_pct_b", "compute_peg",
    "compute_eps_growth", "feature_value", "percentile_rank",
    "rev_accel_a_leg", "rev_accel_b_leg",
)


class DecisionError(RuntimeError):
    """Fail-loud: a selection input the canonical core must not absorb."""


# --- scoring ------------------------------------------------------------------

def member_percentiles(panel: FeaturePanel, eligible: Sequence[str], *,
                       convention: str) -> dict[str, dict[str, float]]:
    """Per-feature cross-sectional percentile over the eligible set.

    Orientation is applied here, once, by asking `b0_features`. This layer never
    decides a sign: `orientation()` aborts for the members §3.1 leaves unsigned.
    """
    names = tuple(sorted(eligible))
    if not names:
        return {}

    # Completeness is checked over the whole panel first. Interleaving it with
    # the orientation lookup would let an M-3 abort on one member hide a
    # complete-case breach on another, and the second is the more urgent defect:
    # it means the §4.1 gate was bypassed upstream.
    raw_by_key: dict[str, dict[str, float]] = {}
    for key in required_feature_keys():
        raw: dict[str, float] = {}
        for sid in names:
            v = panel.values[sid].get(key)
            if v is None:
                raise DecisionError(
                    f"§4.1: {sid} reached ranking with {key!r} unavailable. "
                    f"Complete-case exclusion happens in b0_eligibility; a None "
                    f"here means the gate was bypassed, and partial scoring is "
                    f"forbidden.")
            raw[sid] = float(v)
        raw_by_key[key] = raw

    out: dict[str, dict[str, float]] = {}
    for key, raw in raw_by_key.items():
        # Direction comes from the feature's own definition (C-19). This layer
        # has no way to express a different one, which is the point.
        out[key] = feature_percentile(key, raw, convention=convention)
    return out


def concept_score(percentiles: Mapping[str, Mapping[str, float]],
                  concept: str, stock_id: str) -> float:
    """Equal weight within concept (§3.1)."""
    members = concept_members(concept)
    vals = []
    for m in members:
        try:
            vals.append(float(percentiles[m][stock_id]))
        except KeyError:
            raise DecisionError(
                f"{stock_id}: no percentile for {m!r} in concept {concept!r}. "
                f"Concept means are over the full frozen membership; dropping an "
                f"absent member would reweight the concept silently.") from None
    return sum(vals) / len(vals)


def selection_score(percentiles: Mapping[str, Mapping[str, float]],
                    stock_id: str) -> float:
    """SelectionScore = mean(Quality, Growth, Value, Momentum) — equal weight."""
    concepts = [concept_score(percentiles, c, stock_id) for c in CONCEPTS]
    return sum(concepts) / len(concepts)


def score_eligible(panel: FeaturePanel, eligible: Sequence[str], *,
                   convention: str) -> dict[str, float]:
    pcts = member_percentiles(panel, eligible, convention=convention)
    return {sid: selection_score(pcts, sid) for sid in sorted(eligible)}


# --- ranking ------------------------------------------------------------------

# C-33: the canonical sort key is (-SelectionScore, stock_id ascending).
#
# `len(selected) = min(20, len(eligible))` is exact, so a tie spanning rank 20
# must be resolved by something. Left to sort stability it would be resolved by
# input row order — by whichever adapter built the panel — and two adapters
# ordering rows differently would produce different portfolios while passing
# every guard, defeating B-20 parity from the inside.
#
# Market cap, ADV and any other alpha are FORBIDDEN as the secondary key. Each
# would be a second, unregistered selection signal entering through the tie:
# "prefer the larger name when scores tie" is a size tilt, and it would never
# appear in the free-parameter count because it looks like a sorting detail.
SELECTION_TIE_BREAK = "stock_id_ascending"
TIE_BREAKS: tuple[str, ...] = (SELECTION_TIE_BREAK,)
FORBIDDEN_TIE_BREAK_KEYS: tuple[str, ...] = (
    "market_cap", "adv20", "turnover", "score_secondary", "listing_date",
)


def rank(scores: Mapping[str, float], *, tie_break: str) -> tuple[str, ...]:
    """Order by SelectionScore, highest first; ties by stock_id ascending."""
    if tie_break != SELECTION_TIE_BREAK:
        raise DecisionError(
            f"C-33: the canonical sort key is (-SelectionScore, stock_id "
            f"ascending); got tie_break={tie_break!r}. Market cap, ADV and any "
            f"other alpha are forbidden as a secondary key — each would be a "
            f"second selection signal entering through the tie.")
    for sid, s in scores.items():
        if s is None or not math.isfinite(float(s)):
            raise DecisionError(f"{sid}: non-finite SelectionScore {s!r}")
    return tuple(sid for sid, _ in
                 sorted(scores.items(), key=lambda kv: (-float(kv[1]), kv[0])))


def select(scores: Mapping[str, float], *, tie_break: str) -> tuple[str, ...]:
    """§5: len(selected) = min(N_target, len(eligible))."""
    from core.b0_master_prereg import spec

    n_target = int(spec("N_target"))
    return rank(scores, tie_break=tie_break)[:min(n_target, len(scores))]


# --- targets ------------------------------------------------------------------

@dataclass(frozen=True)
class TargetPortfolio:
    """Target weights only. No share counts, no prices — those are execution."""
    as_of: str
    selected: tuple[str, ...]
    weights: Mapping[str, float]
    cash_weight: float
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if total > 1.0 + 1e-12:
            raise DecisionError(
                f"§5: target weights sum to {total}. B0 does not lever (§6.4).")
        if abs(total + self.cash_weight - 1.0) > 1e-12:
            raise DecisionError(
                f"§5: weights ({total}) + cash ({self.cash_weight}) must be 1.0; "
                f"a shortfall goes to cash and is never renormalised away.")


def target_portfolio(as_of: str, selected: Sequence[str]) -> TargetPortfolio:
    """§5: fixed 5% per name, shortfall to cash, 1/n explicitly forbidden."""
    from core.b0_master_prereg import spec

    w_target = float(spec("w_target"))
    w_max = float(spec("w_max"))
    n_target = int(spec("N_target"))
    if w_target != w_max:
        raise DecisionError(
            f"§5: w_target ({w_target}) and w_max ({w_max}) are the same frozen "
            f"quantity; a gap between them would be a sizing free parameter.")
    if bool(spec("reweight_when_under_target_breadth")):
        raise DecisionError(
            "§5: renormalising to full investment when fewer than N_target names "
            "are eligible is forbidden in as many words. It would make w_max "
            "vacuous and would maximise single-name exposure in exactly the "
            "periods when the opportunity set is thinnest.")

    names = tuple(selected)
    if len(names) != len(set(names)):
        raise DecisionError("selected contains duplicates")
    if len(names) > n_target:
        raise DecisionError(
            f"§5: {len(names)} selected exceeds N_target = {n_target}")

    weights = {sid: w_target for sid in names}
    invested = w_target * len(names)
    return TargetPortfolio(
        as_of=as_of,
        selected=names,
        weights=weights,
        cash_weight=1.0 - invested,
        diagnostics={"breadth": len(names), "n_target": n_target,
                     "under_invested_by_breadth": len(names) < n_target},
    )


def assert_no_reweighting(weights: Mapping[str, float]) -> None:
    """A 1/n portfolio is detectable after the fact; this names it."""
    from core.b0_master_prereg import spec

    if not weights:
        return
    w_target = float(spec("w_target"))
    n = len(weights)
    if n and all(abs(w - 1.0 / n) < 1e-12 for w in weights.values()) \
            and abs(1.0 / n - w_target) > 1e-12:
        raise DecisionError(
            f"§5: {n} positions at 1/{n} = {1.0/n:.6f} each is 1/n weighting, "
            f"which is forbidden. The frozen weight is {w_target} per name with "
            f"the remainder in cash.")
