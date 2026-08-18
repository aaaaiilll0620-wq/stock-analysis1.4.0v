"""Layer 2 of the canonical core (§8.7): who is allowed to be ranked at all.

Responsibility boundary, quoted from §8.7:

    b0_eligibility  only: PIT universe + complete-case + risk + dynamic
                          investability -> eligible set
                    must not: compute SelectionScore itself

That prohibition is structural, not stylistic. §4.5 requires exclusion to happen
strictly before ordering: if liquidity were filtered after ranking, breadth would
become an unstable residue (a Top-20 losing 5 names leaves 15), and "we hold 20
names" would quietly become "we hold whatever survived". This module therefore
never sees a score, and the type it returns carries names, not an ordering.

Three gates, reported separately because §9.1 S-4 requires the per-period
elimination composition to be disclosed rather than netted into one number:

  1. complete-case (§4.1)          — every required feature PIT-available, or the
                                     row leaves entirely. No imputation, no
                                     partial scoring.
  2. risk / data-quality (§4.4)    — one filter: net_margin < -10 (C-20, C-36).
  3. dynamic investability (§4.2)  — ADV20 >= ADV_floor(t) = 5 x port_value(t).

Gate 2 has a history worth keeping, because its final shape is much smaller than
its starting point. B-09 Phase 1 relocated the legacy F10 filters to this layer
rather than removing them, so anything surviving here is INHERITED rather than
chosen — a frozen constant, not a runtime knob. Reading the legacy predicate line
by line then showed it was not the four clean thresholds its summary suggested:
six constants, a financial-sector exemption, and one leg (`cash_quality`) whose
input nothing in the repository ever produced. C-29 through C-36 ruled on each
piece, and four of the five legs are gone.

What that leaves is a single unconditional fundamental filter. The two
balance-sheet ratios the removed legs were built on — `debt_to_asset` and
`current_ratio` — are now handled continuously inside Quality: a weak name is
penalised in its percentile rather than excluded by a cut-point, which is the
same direction §3.1 took when it drove manual cut-points to zero.

One inference is explicitly ruled OUT (C-36): removing the sector exemption that
guarded the current-ratio floor does NOT promote that floor into an unconditional
rule. Removing a carve-out and keeping the rule it carved out of are different
decisions, and only the first was made.

On the ADV floor: it is a per-period derived quantity, never a frozen parameter.
NT$10,000,000 is only its value when port_value == C_ref, and its numerical
coincidence with the retired `--adv-floor=1e7` switch is exactly that — a
coincidence, from an unrelated origin. §4.2 forbids reusing that identifier, and
`assert_no_retired_adv_floor_identifier` enforces it mechanically so the
coincidence cannot become a lineage claim in someone's later reading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

from core.b0_features import FeaturePanel, required_feature_keys
from core.b0_open_items import raise_unspecified

ELIGIBILITY_LAYERS: tuple[str, ...] = (
    "complete_case", "risk_hard_filter", "dynamic_investability",
)


class EligibilityError(RuntimeError):
    """Fail-loud: an eligibility input the canonical core must not absorb."""


# --- §4.2 dynamic investability ----------------------------------------------
# ADV_floor(t) = port_value(t) * w_target / X_buy. The multiple is read from the
# master preregistration rather than written here, so that a change to w_target
# or X_buy cannot leave a stale 5.0 behind in this module.

def adv_floor(port_value: float) -> float:
    """Per-period derived floor. NOT a frozen parameter (§4.2)."""
    from core.b0_master_prereg import spec

    if not math.isfinite(port_value) or port_value <= 0:
        raise EligibilityError(
            f"§4.2: ADV_floor derives from port_value, which must be finite and "
            f"> 0; got {port_value!r}. A floor derived from an unmarked or zero "
            f"portfolio is not a floor.")
    return float(port_value) * float(spec("adv_floor_multiple"))


# §4.2: the retired research switch must not be reused as an identifier, in any
# spelling, so that no later reader can describe the B0 gate as "inherited 1e7".
RETIRED_ADV_FLOOR_IDENTIFIERS: tuple[str, ...] = (
    "--adv-floor", "adv_floor_1e7", "ADV_FLOOR_1E7", "adv100w", "ADV_FLOOR_CONST",
)


def assert_no_retired_adv_floor_identifier(symbols: Iterable[str]) -> None:
    hit = sorted(set(symbols) & set(RETIRED_ADV_FLOOR_IDENTIFIERS))
    if hit:
        raise EligibilityError(
            f"§4.2: {hit} reuse the retired research switch's identity. The B0 "
            f"floor is a per-period derived quantity whose numerical agreement "
            f"with `--adv-floor=1e7` at C_ref is a coincidence of unrelated "
            f"origin, and must never be documented or coded as an inheritance.")


def passes_investability(adv20: float, floor: float) -> bool:
    """§4.2: can this name carry a full standard position within one session?

    The gate asks about CAPACITY at decision time. It is a different question
    from the order cap applied at send time (§6.4), and §4.2 requires the two to
    be two separate pieces of code — conflating them is how a capacity screen
    turns into a fill rule.
    """
    if not math.isfinite(adv20) or adv20 < 0:
        raise EligibilityError(f"adv20 must be finite and >= 0, got {adv20!r}")
    return float(adv20) >= float(floor)


# --- §4.4 risk / data-quality hard filters ------------------------------------

@dataclass(frozen=True)
class RiskFilter:
    """One hard exclusion.

    `predicate` receives the security's canonical feature row and returns True
    when the name is ADMISSIBLE. It takes values, not an identifier: a filter
    that could look up a security by name could encode a list.
    """
    key: str
    description: str
    predicate: Callable[[Mapping[str, float | None]], bool]


# C-20 · relocation of the legacy F10 hard filters (B-09 Phase 1: "Relocate ->
# Risk / Eligibility", NOT Remove), after reading the legacy predicate line by
# line rather than from its summary. `core/fundamentals.py:262-305` implements:
#
#   net_margin    < -10                      -> fail          (unconditional)
#   current_ratio < 50                       -> fail UNLESS is_financial
#   debt_to_asset > 85                       -> fail ONLY IF
#                     (current_ratio < 100 OR net_margin < 0) OR debt > 92
#                     ... and never if is_financial
#   cash_quality  < 0.5                      -> fail, if the field is present
#
# Six numeric constants and a sector exemption, not four thresholds — and
# `cash_quality` has no producer anywhere in the repository, so that leg never
# fired. What survives into B0:
#
#   C-20  net_margin < -10        FROZEN, unconditional — the ONLY survivor
#   C-29  is_financial exemption  REMOVED — no sector special case exists in B0
#   C-30  the debt tree           REMOVED — debt_to_asset survives ONLY as the
#                                 lower-is-better Quality feature (C-19); there
#                                 is no debt hard exclusion
#   C-31  cash_quality            REMOVED — and explicitly NOT re-pointed at
#                                 `ocf_to_net_income`, which is a different
#                                 quantity, not an alias
#   C-36  current_ratio < 50      REMOVED — and specifically NOT promoted to an
#                                 unconditional rule by C-29's removal of the
#                                 exemption that used to guard it. current_ratio
#                                 survives ONLY as the higher-is-better Quality
#                                 feature.
#
# The shape of the final layer is worth stating plainly: FOUR of the five legacy
# legs are gone, and the two balance-sheet ratios they were built on are now
# handled continuously inside Quality instead of as cut-points. That is the same
# direction §3.1 took when it drove manual cut-points to zero — a highly levered
# but profitable name is now penalised in its percentile rather than excluded.
NET_MARGIN_FLOOR_PCT = -10.0

# C-29. Named as a constant rather than simply left unimplemented: "B0 has no
# sector exemption" is a ruling, and a ruling that exists only as absent code is
# indistinguishable from an oversight.
RISK_FINANCIAL_EXEMPTION = False

# C-30 / C-31. Named for the same reason — and because both were live thresholds
# in the legacy predicate, a future reader finding them in `fundamentals.py`
# needs to see here that their absence was decided rather than missed.
DEBT_HARD_FILTER_ENABLED = False
CASH_QUALITY_FILTER_ENABLED = False
CASH_QUALITY_ALIAS_ALLOWED = False
CURRENT_RATIO_FLOOR_ENABLED = False          # C-36

# Every legacy leg that was removed, named so that re-introducing one is caught
# by a guard rather than by review. `current_ratio_floor` is on the list for a
# specific reason: C-29 removed the exemption that used to guard it, and the
# tempting inference is that the floor therefore applies to everyone. C-36 rules
# the opposite — removing an exemption does not promote the rule it guarded.
REMOVED_LEGACY_RISK_LEGS: tuple[str, ...] = (
    "debt_hard_filter", "cash_quality", "current_ratio_floor",
    "is_financial_exemption",
)


def assert_no_removed_legacy_leg(filter_keys: Iterable[str]) -> None:
    """C-30/C-31/C-36: a removed leg must not come back as a runtime filter."""
    suspects = {
        "debt_to_asset_ceiling": "debt_hard_filter",
        "debt_hard_filter": "debt_hard_filter",
        "max_debt_to_asset": "debt_hard_filter",
        "current_ratio_floor": "current_ratio_floor",
        "min_current_ratio": "current_ratio_floor",
        "cash_quality": "cash_quality",
        "min_cash_quality": "cash_quality",
    }
    hit = sorted({suspects[k] for k in filter_keys if k in suspects})
    if hit:
        raise EligibilityError(
            f"C-30/C-31/C-36: {hit} were removed from the B0 risk layer. The "
            f"underlying ratios survive as continuous Quality features, where a "
            f"weak name is penalised in its percentile rather than excluded by a "
            f"cut-point — which is the direction §3.1 already took.")


def assert_no_sector_exemption(applied_exemptions: Iterable[str] = ()) -> None:
    """C-29: no eligibility decision may depend on what industry a name is in.

    Beyond honouring the ruling, this closes a PIT hole: a sector exemption needs
    sector membership as of the decision date, and §2.3 records that 49.4% of
    names changed TSE sector at least once while `industry_map` is a current
    snapshot. Resolving an exemption against today's sector list would put
    look-ahead inside the eligibility gate.
    """
    if RISK_FINANCIAL_EXEMPTION:
        raise EligibilityError(
            "C-29: the financial-industry exemption was removed from B0.")
    hit = sorted(set(applied_exemptions))
    if hit:
        raise EligibilityError(
            f"C-29: {hit} applied a sector exemption. B0 has no is_financial "
            f"path, and an exemption resolved against a current sector snapshot "
            f"would be look-ahead inside the eligibility gate (§2.3).")


def assert_no_cash_quality_alias(filter_keys: Iterable[str]) -> None:
    """C-31: the removed leg must not return under another quantity's name."""
    suspects = {"cash_quality", "ocf_to_net_income", "cash_flow_quality",
                "ocf_ni", "cash_conversion"}
    hit = sorted(set(filter_keys) & suspects)
    if hit:
        raise EligibilityError(
            f"C-31: {hit} re-introduces the removed cash-quality leg. "
            f"`ocf_to_net_income` is a DIFFERENT quantity — undefined at zero "
            f"net income and sign-flipping with it — so adopting it would be "
            f"defining a new B0 filter, not relocating the old one.")


def _net_margin_admissible(row: Mapping[str, float | None]) -> bool:
    v = row.get("net_margin")
    if v is None:
        raise EligibilityError(
            "§4.4/§4.1: net_margin is unavailable at the risk layer. "
            "Complete-case runs first, so this cannot be reached with a gap.")
    return float(v) >= NET_MARGIN_FLOOR_PCT


FROZEN_RISK_FILTERS: tuple[RiskFilter, ...] = (
    RiskFilter("net_margin_floor",
               f"legacy F10: net_margin < {NET_MARGIN_FLOOR_PCT} -> ineligible "
               f"(unconditional in the legacy predicate)",
               _net_margin_admissible),
)

# C-36 closed the last one. The risk layer is now completely specified: one
# unconditional fundamental filter, no sector special case, no cut-point on
# either balance-sheet ratio, and no undetermined behaviour anywhere in it.
RISK_LAYER_COMPLETE = True
RISK_LAYER_OPEN_ITEMS: tuple[str, ...] = ()

# §3.3 / §4.4: Anti-chase (M9 + Q4 + M11) is a continuous state. It is reported,
# it does not exclude, and it does not size. Named as a constant so that turning
# it into a gate is a visible diff rather than an added `if`.
ANTI_CHASE_IS_HARD_EXCLUDE = False


def assert_anti_chase_is_not_a_gate() -> None:
    if ANTI_CHASE_IS_HARD_EXCLUDE:
        raise EligibilityError(
            "§3.3: Anti-chase is a continuous state and must not hard-exclude. "
            "Turning it into a gate reintroduces a manual cut-point into a layer "
            "whose free-parameter count §9.1 S-1 asserts is zero.")


def frozen_risk_filters(*, allow_incomplete: bool) -> tuple[RiskFilter, ...]:
    """The relocated §4.4 layer.

    `allow_incomplete` is keyword-only and has no default. Diagnostics and tests
    may run on the one relocated leg; anything producing evidence may not,
    because three quarters of the intended layer is still undetermined and a
    partially-applied risk filter is not a conservative version of the whole one.
    """
    if not allow_incomplete and not RISK_LAYER_COMPLETE:
        raise_unspecified(RISK_LAYER_OPEN_ITEMS[0],
                          context=f"risk layer incomplete; also open: "
                                  f"{list(RISK_LAYER_OPEN_ITEMS[1:])}")
    if RISK_LAYER_COMPLETE and RISK_LAYER_OPEN_ITEMS:
        raise EligibilityError(
            f"the risk layer claims to be complete while {list(RISK_LAYER_OPEN_ITEMS)} "
            f"are still open — one of the two is wrong.")
    return FROZEN_RISK_FILTERS


# --- the gate -----------------------------------------------------------------

@dataclass(frozen=True)
class EligibilityResult:
    """Names, never an ordering (§4.5).

    Rejections are kept per layer because §9.1 S-4 makes the per-period
    elimination composition a disclosure requirement: "how many names were
    excluded" without "by which gate" cannot answer whether a period's breadth
    collapsed for liquidity reasons or data reasons.
    """
    as_of: str
    universe: tuple[str, ...]
    eligible: tuple[str, ...]
    rejected: Mapping[str, tuple[str, ...]]
    adv_floor: float
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "universe": len(self.universe),
            "eligible": len(self.eligible),
            **{f"rejected_{layer}": len(self.rejected.get(layer, ()))
               for layer in ELIGIBILITY_LAYERS},
        }


def evaluate(panel: FeaturePanel,
             adv20: Mapping[str, float],
             port_value: float,
             *,
             risk_filters: Sequence[RiskFilter],
             universe: Sequence[str] | None = None) -> EligibilityResult:
    """Run the three gates in the frozen order and return the eligible set.

    `risk_filters` is required and has no default. There is no code path in which
    this module supplies its own — that is the whole content of the §4.4 open
    item, and a default here would close it by accident.
    """
    assert_anti_chase_is_not_a_gate()

    names = tuple(sorted(universe if universe is not None else panel.values.keys()))
    unknown = [s for s in names if s not in panel.values]
    if unknown:
        raise EligibilityError(
            f"universe contains {unknown[:5]} with no row in the feature panel. "
            f"An absent row is not the same claim as an unavailable value (§4.1) "
            f"and must not be silently treated as one.")

    floor = adv_floor(port_value)
    rejected: dict[str, list[str]] = {layer: [] for layer in ELIGIBILITY_LAYERS}
    survivors: list[str] = []
    missing_by_feature: dict[str, int] = {k: 0 for k in required_feature_keys()}

    for sid in names:
        # 1. complete-case (§4.1)
        absent = [k for k in required_feature_keys()
                  if panel.values[sid].get(k) is None]
        if absent:
            for k in absent:
                missing_by_feature[k] += 1
            rejected["complete_case"].append(sid)
            continue
        # 2. risk / data quality (§4.4)
        blocked = [f.key for f in risk_filters
                   if not f.predicate(panel.values[sid])]
        if blocked:
            rejected["risk_hard_filter"].append(sid)
            continue
        # 3. dynamic investability (§4.2)
        if sid not in adv20:
            raise EligibilityError(
                f"§4.2: no ADV20 for {sid!r}. A missing liquidity observation is "
                f"not evidence of liquidity; it must abort rather than default to "
                f"eligible or ineligible.")
        if not passes_investability(adv20[sid], floor):
            rejected["dynamic_investability"].append(sid)
            continue
        survivors.append(sid)

    return EligibilityResult(
        as_of=panel.as_of,
        universe=names,
        eligible=tuple(survivors),
        rejected={k: tuple(v) for k, v in rejected.items()},
        adv_floor=floor,
        diagnostics={"missing_by_feature": missing_by_feature,
                     "risk_filters_applied": tuple(f.key for f in risk_filters)},
    )


def assert_eligibility_precedes_ranking(observed_stages: Sequence[str]) -> None:
    """§4.5 / M-1: exclusion strictly before ordering."""
    from core.b0_master_prereg import assert_stage_order

    assert_stage_order(observed_stages)
    if "selection_score" in observed_stages and "eligibility" not in observed_stages:
        raise EligibilityError(
            "§4.5: a selection score was produced without an eligibility stage. "
            "Ranking first and filtering after makes breadth an unstable residue.")
