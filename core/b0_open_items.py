"""P-1b open specification items — the M-3 register.

The master preregistration (v1.5) is the sole normative specification. §1.5 (M-3)
says that behaviour it does not define is UNSPECIFIED, must abort, and must never
resolve to whatever the implementer found reasonable, because a convenience
decision taken at implementation time is numerically indistinguishable from an
unregistered free parameter.

Building the four canonical core layers is the first activity that has to touch
every clause at once, so it is also the first activity that finds the gaps. This
module is where they are recorded, for two reasons:

  1. One enumerable list. `unspecified_keys()` is the machine-readable mirror of
     master preregistration §12.2, so "how much is still undecided" is a query,
     not a reading exercise.
  2. One abort path. Every layer raises through `raise_unspecified(key)`, so an
     UNSPECIFIED behaviour reached at runtime always names the item, the layer,
     and what a ruling would have to decide — never a stack trace at the point
     some default would silently have been applied.

Each item records `demoted_evidence`: what the pre-freeze closure documents say,
where they say anything. That is deliberately NOT a resolution. Per §0.1 those
documents were demoted to rationale on the day the master preregistration froze;
they no longer define what B0 is. The field exists so that a ruling can be made
quickly and with the prior reasoning in view, not so that an implementer can
quietly promote a closure sentence back to normative status.

MATERIALITY is stated for every item. An item whose consequence is "one basis
point on one month" and an item whose consequence is "the entire share ledger"
both have to be ruled on, but they do not have to be ruled on with the same
urgency, and pretending otherwise makes the list easier to ignore.

The register is currently EMPTY: every behaviour the canonical core reaches is
now specified (C-16 ~ C-36). That is the goal state, not the end of the
mechanism — the module stays because the next undetermined behaviour anybody
finds has to land here rather than in a default, and `raise_unspecified` on an
unregistered key deliberately raises KeyError to force that.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnspecifiedCoreBehaviour(RuntimeError):
    """M-3: a canonical-core behaviour the master preregistration does not fix.

    Deliberately distinct from `MasterPreregViolation`: nothing has been
    violated. The specification is silent, and silence must stop the run rather
    than be filled in.
    """


LAYERS: tuple[str, ...] = ("features", "eligibility", "decision", "execution")

# Materiality bands. Not thresholds — an ordering, so that a ruling session can
# start at the top rather than at whatever item happens to be first.
MATERIALITY_LEVELS: tuple[str, ...] = ("structural", "high", "moderate", "low")


@dataclass(frozen=True)
class OpenItem:
    key: str
    layer: str
    question: str
    why_it_matters: str
    materiality: str
    demoted_evidence: str = ""

    def __post_init__(self) -> None:
        if self.layer not in LAYERS:
            raise ValueError(f"unknown core layer {self.layer!r}; known: {LAYERS}")
        if self.materiality not in MATERIALITY_LEVELS:
            raise ValueError(
                f"unknown materiality {self.materiality!r}; known: {MATERIALITY_LEVELS}")
        if not self.question.strip() or not self.why_it_matters.strip():
            raise ValueError(
                f"{self.key}: an open item that does not state the question and its "
                f"consequence is not a record of anything")


OPEN_ITEMS: tuple[OpenItem, ...] = (

    # --- features -------------------------------------------------------------
    # RESOLVED and removed from this register. Every one was a master OMISSION,
    # not a decision anybody still had to make — which is why closing thirteen of
    # them added no free parameters:
    #   feature_orientation             -> C-19  B-09 Phase 1's 方向 column
    #   feature_formula_peg             -> C-17  standard definition, positive domain
    #   feature_formula_eps_growth      -> C-18  closure horizon + producer lineage
    #   feature_formula_roe             -> C-21  closure TTM + producer denominator
    #   feature_formula_margins         -> C-21  ditto, aggregate over aggregate
    #   feature_formula_balance_sheet   -> C-22  closure "當期" + §2.2 publication
    #   feature_formula_revenue_yoy     -> C-23  the 13-month lookback admits one
    #   feature_formula_momentum_12_1   -> C-24  §3.1 says "price momentum"
    #   adv20_definition                -> C-25  legacy producer lineage
    #   sigma20d_definition             -> C-26  B-14 P3 states it verbatim
    #   pending_exit_price_basis        -> C-27  §6.4 and §7.3 read together
    #   target_drift_policy             -> C-16  B-06/B-12 compute_order_intent
    #   risk_hard_filters               -> C-20  relocate, then C-29/30/31
    #   cross_sectional_percentile_conv -> C-35  average rank over ties
    #   selection_tie_break             -> C-33  (-score, stock_id ascending)
    #   share_rounding                  -> C-34  floor, 5% is a hard cap
    #   buy_priority_under_cash_constr  -> C-32  Selection rank order
    #   risk_filter_is_financial_exempt -> C-29  removed
    #   risk_filter_debt_conditional    -> C-30  removed
    #   risk_filter_cash_quality        -> C-31  removed, no alias
    #   risk_filter_current_ratio_floor -> C-36  removed; a removed
    #                                      exemption does not promote
    #                                      the rule it guarded

    OpenItem(
        key="value_pbr_lineage_2019plus",
        layer="features",
        materiality="structural",
        question=(
            "From which ADMISSIBLE source does `pbr_tse` come for decision dates "
            "2019-01-31 onward? Measured, not inferred: the TSE valuation columns "
            "(本益比-TSE / 股價淨值比-TSE) exist ONLY in the yearly-xlsx vintage of "
            "個股股價、本益比2004-20260817, which is the corpus D-1 quarantined for "
            "survivorship filtering (content sha256 aeda65b9…ea49c1). The vintage "
            "that REPLACED it for 2019+ — 股價 2019-2022.zip and "
            "股價2023-20260817.zip — carries only 本益比-TEJ / 股價淨值比-TEJ. So "
            "every candidate is already excluded by something frozen: the TSE "
            "series by D-1, and the TEJ series by B-09's lineage."
        ),
        why_it_matters=(
            "Value = industry-relative B/M is one of the four equally weighted "
            "Selection concepts (§3.2), and B-09 freezes it on the TSE PBR lineage. "
            "87 of the 141 sealed decision months are 2019-01-31 or later — the same "
            "87 months core/b0_adapter_retrospective.py already names as where a "
            "survivorship-filtered universe does its damage. Without a ruling the "
            "only reachable options each break a different frozen rule: substituting "
            "PBR_TEJ is the silent lineage substitution B-09 forbids; reading the "
            "quarantined corpus is the survivorship bias D-1 exists to remove; "
            "deriving B/M from book equity and shares outstanding is a new valuation "
            "field; and leaving pbr_tse NA makes §4.1 complete-case drop the entire "
            "universe for 62% of the window. Choosing among them at implementation "
            "time is exactly the unregistered free parameter M-3 forbids."
        ),
        demoted_evidence=(
            "B-09 Phase 1/2 closure fixes B/M on PBR_TSE and records the TSE-vs-TEJ "
            "distinction as deliberate. research/p0_b09_value_reference/"
            "build_b_value_reference.py reads ~/tej_cache/price_valuation, whose "
            "fingerprint IS the quarantined hash — so the existing "
            "b_value_reference_candidate_v2.parquet is contaminated from 2019 and "
            "cannot be promoted. D1-6 quarantines by content, so copying or renaming "
            "that corpus does not launder it. None of this is a ruling: the "
            "specification does not say what an admissible 2019+ TSE PBR source is."
        ),
    ),
)

_BY_KEY: dict[str, OpenItem] = {i.key: i for i in OPEN_ITEMS}

if len(_BY_KEY) != len(OPEN_ITEMS):  # pragma: no cover - structural guard
    raise RuntimeError("duplicate open-item key")


def unspecified_keys() -> tuple[str, ...]:
    return tuple(i.key for i in OPEN_ITEMS)


def open_items_for(layer: str) -> tuple[OpenItem, ...]:
    if layer not in LAYERS:
        raise ValueError(f"unknown core layer {layer!r}; known: {LAYERS}")
    return tuple(i for i in OPEN_ITEMS if i.layer == layer)


def get(key: str) -> OpenItem:
    try:
        return _BY_KEY[key]
    except KeyError:
        raise KeyError(
            f"{key!r} is not a registered open item. If a canonical-core layer "
            f"reached an undetermined behaviour, register it here first — the "
            f"point of this module is that the list is complete."
        ) from None


def raise_unspecified(key: str, *, context: str = "") -> None:
    """The single abort path for undetermined canonical-core behaviour."""
    item = get(key)
    where = f" [{context}]" if context else ""
    raise UnspecifiedCoreBehaviour(
        f"M-3: {item.key!r}{where} is UNSPECIFIED in the master preregistration "
        f"(layer: {item.layer}, materiality: {item.materiality}).\n"
        f"  Question : {item.question}\n"
        f"  Why      : {item.why_it_matters}\n"
        f"  Ruling required before this path may run. It must not resolve to an "
        f"implementation default."
    )


def summary() -> dict:
    """Machine-readable mirror of §12.2 for the canonical core."""
    return {
        "total": len(OPEN_ITEMS),
        "by_layer": {l: len(open_items_for(l)) for l in LAYERS},
        "by_materiality": {
            m: sum(1 for i in OPEN_ITEMS if i.materiality == m)
            for m in MATERIALITY_LEVELS},
        "keys": list(unspecified_keys()),
    }
