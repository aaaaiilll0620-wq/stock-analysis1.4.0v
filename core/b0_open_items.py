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
now specified (C-16 ~ C-36, plus C-48, C-49, C-50 and C-51 — the items that needed a
ruling rather than a recovered omission). That is the goal state, not the end of the
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
    #
    # And one item that was NOT an omission — it needed a decision, not a
    # recovery, and is the only entry here that ever added a normative sentence:
    #
    #   value_pbr_lineage_2019plus      -> C-48  RULED AND CLOSED (2026-08-18)
    #
    # Nothing in the demoted closures said what an admissible 2019+ TSE PBR
    # source is. The ruling rests on measurement: official exchange PBR
    # reproduces the frozen lineage exactly where the two overlap (TWSE 32,284
    # comparisons at 100.00%, TPEx 26,419 at 99.96%), and the official series
    # never carries a security the frozen lineage lacks — so admitting it
    # CONTINUES the B-09 lineage rather than substituting for it. The ruling, its
    # two recorded limitations and the sealed-source contract live in
    # core/b0_valuation_source.py, where a route can check them rather than read
    # them.
    #
    #   value_per_lineage_2019plus      -> C-49  RULED AND CLOSED (2026-08-19)
    #
    # The same gap for `per_tse`, found while materialising the panel C-48
    # unblocked, and ruled on its OWN evidence rather than by analogy — PE has a
    # domain (C-17: PE > 0) that B/M does not, so the two ratios do not even
    # share an NA population. Reconciled first: TWSE 26,062 comparisons with one
    # single-tick difference, TPEx 18,815 with none, and after the yearly
    # export's 0.0 sentinel is read as the absence it is, the two sources agree
    # about EVERY missing value on both boards.
    #
    #   momentum_price_adjustment       -> C-50  RULED AND CLOSED (2026-08-19)
    #
    # The adjustment is a SHARE-UNIT one, not a total-return one: adjust for a
    # deterministic transformation of an existing holder's shares, never for a
    # change in shares outstanding — so `share_multiplier != 1` is not
    # sufficient and dilution never touches a price series. Cash dividends stay
    # visible because §3.1 froze a PRICE relative. Only momentum_12_1 and
    # sigma20d read the adjusted series; marks, execution, NAV, notional, fees
    # and ADV20 stay on observed prices. core/b0_share_unit_adjustment.py is the
    # single producer, and R8's fail-loud paths are what exposed the one
    # remaining input question above.
    #
    #   stock_dividend_holder_multiplier_source -> C-51  RULED AND CLOSED (2026-08-19)
    #
    # The input C-50/R8 exposed, and the one item here that was closed by going
    # and looking rather than by reasoning: BOTH exchanges publish the
    # holder-level ratio directly — TWSE field A of the 除權除息計算結果表 detail,
    # TPEx 每仟股無償配股 in its range table — so the shares-outstanding
    # denominator never has to be reconstructed. The unit was measured against
    # the exchanges' own reference-price identity (per-1,000 satisfies it to
    # max |Δ| 0.005 / 0.0999; decimal-ratio and percent readings miss by 953 to
    # 2,095), not read off the column name. 2,399 of 3,215 events in the frozen
    # lookback window carry an official ratio, 0 transport failures, and the
    # unresolved share of the priced universe falls from a median of 10.56% to
    # 1.41% — below the §2.3 exclusion the specification already accepts. The
    # ruling, the two residual dispositions and the sealed-source contract live
    # in core/b0_bonus_share_source.py, where a route can check them.

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
