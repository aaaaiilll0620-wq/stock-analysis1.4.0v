"""M-3 register for specification gaps OUTSIDE the canonical core layers.

`core.b0_open_items` is the P-1b register: it holds behaviours a canonical-core
LAYER reaches at runtime, and `assert_selection_path_is_fully_specified` reads it
as "is the Selection path fully specified". A gap in provenance or hash scope is
not a Selection-path behaviour, and filing it there would make S-1 report a false
red — so it gets its own register rather than a widened one.

What lands here has the same M-3 status as anything in the other register: the
master preregistration is silent, silence is not a licence to choose, and the
run that would depend on the choice stops. The difference is only WHICH run
stops. These items block **finalization** — the final provenance seal — because
that is the step whose meaning depends on them.

The register is consulted by `core.b0_provenance.seal(final_seal=True)`, so an
open item is a mechanical stop and not a note somebody has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass

BLOCKS: tuple[str, ...] = ("final_provenance_seal", "L2_opening",
                          "B0_2_retrospective_replay",
                          "B0_3_data_repair")


class FinalizationBlocked(RuntimeError):
    """M-3: finalization depends on a scope the specification has not defined."""


@dataclass(frozen=True)
class FinalizationItem:
    key: str
    question: str
    why_it_matters: str
    measured: str                  # what the audit actually found
    options: tuple[str, ...]       # candidate rulings, NOT a recommendation
    blocks: tuple[str, ...]
    opened_by: str

    def __post_init__(self) -> None:
        for f in ("key", "question", "why_it_matters", "measured", "opened_by"):
            if not str(getattr(self, f)).strip():
                raise ValueError(f"{self.key or '?'}: {f} is required")
        if len(self.options) < 2:
            raise ValueError(
                f"{self.key}: an item with fewer than two candidate rulings is a "
                f"decision already taken, which is what this register exists to "
                f"prevent")
        bad = [b for b in self.blocks if b not in BLOCKS]
        if bad:
            raise ValueError(f"{self.key}: unknown blocked stage(s) {bad}")


# RESOLVED and removed from this register:
#
#   hash_scope_boundary -> F0-R1 ~ F0-R7 (master prereg v1.13, §11 C-46).
#       config_hash = the COMPLETE machine-readable declaration registry;
#       spec_sha256 = raw-byte identity of the frozen master document;
#       implementation identity = commit SHA + explicit normative-module hashes;
#       production-reachable declarations = implementation-derived or backed by
#           an executable behavioural conformance check
#           (core/b0_declaration_conformance.py);
#       state_hash = canonical concrete input-state identity, never an
#           implementation hash;
#       the B-21 manifest binds all of them DIRECTLY;
#       one shared serialization/hash primitive (core/b0_canonical_hash.py).
#
#   pre_l2_seal_semantics -> M-3 ruling of 2026-08-18 (master prereg v1.14, C-47).
#       OPENED because the seal Master §13.3 requires BEFORE L2 may open could
#       not be taken at all: `seal()` rejects an empty section, and `execution`
#       (decision_date) plus `output` (target/intent/receipt/NAV hashes) can only
#       be populated by running the B0 route -- the very step the seal exists to
#       authorise. The four candidate readings were: (a) bind a production-adapter
#       decision, (b) seal atomically with the L2 run, (c) define a separate
#       repo-only seal, (d) relax PROVENANCE_SECTIONS.
#
#       RULED: two-stage provenance, neither of the four verbatim.
#         B0 BASELINE SEAL (pre-L2) binds spec_sha256, the complete registry
#           config_hash, canonical hash schema/version, commit SHA, clean-tree
#           identity, all normative-module hashes, dataset hashes/schema/coverage/
#           importer lineage, derived inputs + upstream lineage, the opening state
#           hash, route identity, and the L2 opening protocol; and records
#           execution.status = NOT_EXECUTED_PRE_L2, output.status =
#           NOT_PRODUCED_PRE_L2 as EXPLICIT states rather than blanks.
#         L2 RUN PROVENANCE (post-execution) references baseline_seal_sha256 and
#           adds the concrete execution/output hashes. It may not mutate or
#           replace the baseline (`assert_baseline_not_mutated`).
#       No B0 decision route may be run merely to satisfy the baseline seal, and
#       a baseline carrying fabricated outputs is rejected, not tolerated.
#
# The register stays. It is empty because the items were ruled on, not because
# the mechanism was retired -- the next finalization-blocking gap lands here
# rather than in somebody's judgement about whether a seal is safe.
#
# Registering an item here changes this module's hash, and this module is a
# NORMATIVE_MODULE. That is the intended cost: the ruling of 2026-08-18 states
# explicitly that v1.13 hashes must NOT be preserved by routing around the
# registration mechanism. v1.13 is kept as historical lineage instead.
#   l2_reopening_after_run_invalid -> RULING of 2026-08-19 (master prereg v1.22,
#       C-56). OPENED because run L2-2520c80aa980d681 terminated in 6.1.14
#       F-CA-C, and 6.1.14 states the re-opening PATH without saying whether the
#       invalid run consumed the once-only observation -- while M-2's
#       assert_rerun_admissible could not express the case at all, admitting a
#       re-run only under a DataRepair whose scopes are DATA scopes.
#
#       RULED: NOT CONSUMED. The run produced no non-empty SelectionScore
#       cross-section, no target or executed portfolio, no NAV, and no
#       CAGR/Sharpe/MDD/benchmark was computed or viewed. It remains an
#       ATTEMPTED L2 execution and is preserved permanently in provenance --
#       not deleted, not overwritten, not relabelled -- but it is not an
#       effective observation under B-18 4.3.
#
#       The rule is NARROW, and deliberately not "crashed runs never count":
#       non-consumption requires all seven conditions in
#       NON_CONSUMPTION_CONDITIONS, and is admissible only for
#       RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE.
#       M-2 gained ImplementationConformanceRepair so the case is RECOGNISED
#       rather than misclassified as a data repair.
#       Closing this item unblocks L2_opening MECHANICALLY only. Nothing here
#       authorises an opening: 6.1.14 still requires the repairs, a new valid
#       Baseline Seal, and fresh explicit authorization, and
#       assert_reopening_admissible refuses an opening that binds the same
#       baseline the invalid run bound.
#
# RESOLVED and removed from this register:
#
#   benchmark_construction_semantics -> M-3 rulings of 2026-08-19/20 (master
#       prereg v1.27, 13.2/13.3, C-61). OPENED because 9.4 gate 1 is
#       `net cumulative wealth > 0050 buy-and-hold`, a strict inequality and the
#       single primary hypothesis, while the master fixed only the benchmark's
#       IDENTITY. Six outcome-relevant construction choices were undetermined
#       and none of the 217 frozen keys named one, so each was a free parameter
#       sitting directly on the primary gate.
#
#       RULED, in three passes, and in every pass BEFORE any performance was
#       observed -- which is what makes the completion admissible at all:
#         B1-B7   construction protocol frozen (timing, C_ref, share/cash solve,
#                 no ADV throttle, mark-to-market terminal, fail-loud sessions,
#                 dividends never reinvested).
#         R1/R2   dividend payment date is OPTIONAL_NON_OUTCOME_AUDIT_FIELD.
#                 Under B2 + B7 + 2.5 a fixed amount sitting in `receivable`
#                 versus `cash` is the same wealth, so an unavailable payment
#                 date leaves the receivable outstanding rather than licensing
#                 an inferred date.
#         R4-R7   the 2025-06-18 1:4 share-unit split is outcome-required. It is
#                 vacuous only for the 2014 sigma20d/ADV20 lookback; the holder
#                 ledger applies holder_multiplier = 4.0 exactly once, q -> 4q,
#                 with raw marks unchanged and no receivable created.
#
#       Closed only once BOTH halves of the R11 condition held: the semantics
#       are frozen AND the canonical lineage is materialized and seal-bindable.
#       The second half required acquiring new authoritative TWSE raw data,
#       because the premise that admissible sources already existed was
#       mechanically falsified -- the only manifested 0050 lineage was the
#       reinvesting total-return series B7 excludes, carrying no open, no
#       volume, no raw close and no distribution events.
#
FINALIZATION_ITEMS: tuple[FinalizationItem, ...] = (

    FinalizationItem(
        key="merger_holder_side_leg_semantics",
        question=(
            "Does a `合併(仟股)` row on the SURVIVING entity describe a "
            "holder-affecting IDENTITY CHANGE for a holder of that surviving "
            "security -- as the frozen model asserts -- or does it describe the "
            "surviving issuer's own share ISSUANCE, whose only effect on an "
            "existing holder is dilution already carried in the price? The two "
            "readings demand different data and produce different verdicts: the "
            "first needs successor_security_id + stock_ratio + "
            "credit_tradable_date and is NOT_RECONSTRUCTIBLE without them; the "
            "second is NOT_APPLICABLE and needs nothing."),
        why_it_matters=(
            "This is the single reason the B0.2 diagnostic replay is blocked, "
            "and it cannot be settled by acquiring data. All 220 merger events "
            "in the corpus carry the SAME defect signature and NONE of the three "
            "frozen holder-side fields; no reachable authoritative source "
            "supplies them (see merger_source_availability.json), so under R5 "
            "they all remain NOT_RECONSTRUCTIBLE and a faithful DataRepair "
            "changes nothing. The alternative reading WOULD clear the block -- "
            "which is precisely why an implementer must not take it. It would "
            "change `holder_affecting_kinds()`, `IDENTITY_CHANGING_KINDS` and "
            "the 6.1 transition table, all frozen, so R12 makes it a STOP rather "
            "than a repair. Deciding it because it unblocks a replay is the "
            "exact move R5 forbids."),
        measured=(
            "Corpus-wide audit over the whole ledger, defect-defined and "
            "independent of holdings: 46,275 ledger rows, 220 merger events, "
            "220/220 matching the defect signature verbatim, 0 outside it, 186 "
            "distinct securities, 2004-03-01 .. 2025-07-24, 53 inside the "
            "141-period window. Holder-side field presence across all 220 "
            "in-scope events: NONE of successor_security_id, stock_ratio or "
            "credit_tradable_date is populated on any of them. 33 "
            "share_conversion events carry the identical signature and the "
            "identical frozen requirement, so any ruling here reaches them too. "
            "The importer maps the TEJ column `合併(仟股)` -- the surviving "
            "issuer's own share-count delta -- onto a kind the core declares "
            "holder-affecting and identity-changing; the ledger's own stated "
            "reason (`recorded only on the surviving/issuing entity`) is what "
            "raises the question. Both 4123 events (2014-11-14, the B0.2 "
            "blocker, and 2022-06-30) sit inside this scope and were audited "
            "through the corpus-wide rule with no event-specific handling."),
        options=(
            "RULE that the frozen reading stands: a merger row is a "
            "holder-affecting identity change. All 220 then remain "
            "NOT_RECONSTRUCTIBLE, B0.2's fail-loud block is correct and final on "
            "current data, and the 141-period window is unevaluable until an "
            "authoritative counterparty/ratio lineage is acquired from outside "
            "this repository.",
            "RULE that `合併(仟股)` on the surviving entity is issuer-side only, "
            "as `convertible_bond_conversion` and `cash_capital_increase` "
            "already are, making it NOT_APPLICABLE for a holder of the survivor "
            "-- and state explicitly where the holder-of-the-DISAPPEARING-entity "
            "leg is then represented, because that leg is genuinely "
            "holder-affecting and must not vanish with the reclassification.",
            "RULE a split treatment: issuer-side share issuance is "
            "NOT_APPLICABLE, while a separately sourced disappearing-entity "
            "event class carries the holder-side identity change. This requires "
            "new sealed inputs and a 6.1 amendment, so it is a version boundary, "
            "not a repair.",
        ),
        blocks=("B0_3_data_repair", "final_provenance_seal"),
        opened_by=(
            "B0.3 ruling R2/R12, 2026-08-20. The corpus-wide merger audit found "
            "no data defect that acquisition can fix, and the only repair that "
            "would clear the B0.2 block is a change to frozen CA semantics, "
            "which R12 routes to M-3 rather than to an implementer."),
    ),
)


_BY_KEY: dict[str, FinalizationItem] = {i.key: i for i in FINALIZATION_ITEMS}

if len(_BY_KEY) != len(FINALIZATION_ITEMS):      # pragma: no cover
    raise RuntimeError("duplicate finalization-item key")


def open_keys() -> tuple[str, ...]:
    return tuple(i.key for i in FINALIZATION_ITEMS)


def items_blocking(stage: str) -> tuple[FinalizationItem, ...]:
    if stage not in BLOCKS:
        raise ValueError(f"unknown stage {stage!r}; known stages are {BLOCKS}")
    return tuple(i for i in FINALIZATION_ITEMS if stage in i.blocks)


def assert_not_blocked(stage: str) -> None:
    """Abort while a scope this stage depends on is still undefined."""
    blocking = items_blocking(stage)
    if blocking:
        detail = "; ".join(f"{i.key}: {i.question}" for i in blocking)
        raise FinalizationBlocked(
            f"M-3: {stage} is blocked by {len(blocking)} undefined "
            f"specification scope(s) — {detail}. The implementer must not pick "
            f"the scope; a ruling has to."
        )


def summary() -> dict:
    """Machine-readable mirror, so 'how much is undecided' stays a query."""
    return {
        "total": len(FINALIZATION_ITEMS),
        "keys": list(open_keys()),
        "by_stage": {s: len(items_blocking(s)) for s in BLOCKS},
    }
