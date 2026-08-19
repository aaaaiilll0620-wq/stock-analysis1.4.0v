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
                          "B0_2_retrospective_replay")


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
FINALIZATION_ITEMS: tuple[FinalizationItem, ...] = (

    FinalizationItem(
        key="benchmark_construction_semantics",
        question=(
            "How is the frozen 9.3 row (3) benchmark -- 0050 buy-and-hold -- "
            "actually CONSTRUCTED? Specifically: (a) on which date is the "
            "position opened; (b) with what initial capital / notional; "
            "(c) how are shares sized, and is the fee solved inside or outside "
            "the capital constraint; (d) is the single benchmark purchase "
            "subject to the 6.4 1% ADV order cap and any other capacity rule, "
            "or to none; (e) at window end, is the position MARKED at the final "
            "session price or LIQUIDATED (which would add transaction_tax at "
            "0.003 plus fee and impact); (f) if 0050 has no observation on a "
            "required session, is the last observation carried, is the run "
            "blocked, or is the session dropped -- and is the session grid the "
            "B0 trading calendar or 0050's own observed sessions?"),
        why_it_matters=(
            "V-4 gate 1 is `net cumulative wealth > 0050 buy-and-hold`, a "
            "STRICT inequality and the single primary hypothesis (V-2, formal "
            "family size = 1). Every one of the six choices above moves the "
            "benchmark's terminal wealth: (e) alone is worth roughly 0.3% of "
            "it via transaction_tax, and 0.3% can decide a strict inequality. "
            "The master preregistration says only three things about this "
            "benchmark -- 9.3 names the row and mandates "
            "`core/b0_cost_model.py` for all four rows with costs computed "
            "from each row's OWN real trading events, 9.3 forbids forcing B0's "
            "trading impact onto it, and 2.5 requires it to be "
            "dividend-inclusive under the SAME dividend handling as the "
            "strategy. Nothing fixes the date, the notional, the sizing, the "
            "capacity treatment, the terminal treatment or the missing-session "
            "rule, and no key in the 217-key frozen registry covers any of "
            "them. Choosing them at implementation time is exactly the "
            "numerically-indistinguishable free parameter 1.5 (M-3) forbids -- "
            "and here it would be a free parameter sitting directly on the "
            "primary gate."),
        measured=(
            "Exhaustive sweep of the frozen master (v1.26, spec_sha256 "
            "6f452ea2...) for benchmark construction: 9.3 line 1361/1365, 9.4 "
            "line 1371, 2.5 line 317. That is the complete set. "
            "`specified_keys()` = 217, of which ZERO name a benchmark "
            "construction parameter. Of the eleven outcome-relevant semantics "
            "enumerated by the B0.2 authorization R6, five are uniquely "
            "determined (dividend inclusion 2.5; dividend cash-not-reinvested "
            "2.5 `same handling as the strategy`; explicit_fee and "
            "transaction_tax formulas and constants 7.1/7.1.2; impact computed "
            "from 0050's OWN sigma20D/ADV20 per 9.3) and six are not (initial "
            "date; initial capital/notional; share rounding and the fee/cash "
            "solve; capacity/ADV treatment; terminal valuation vs liquidation; "
            "missing-session handling). "
            "NOTE, because it disqualifies the most convenient source: 2.5's "
            "`same dividend handling as the strategy` means ex-date "
            "receivable -> cash at payment date with NO reinvestment, so a "
            "reinvesting total-return series (e.g. the legacy "
            "`beat_0050/data/benchmark/0050_tr.parquet`) is NOT an admissible "
            "benchmark input under the frozen semantics."),
        options=(
            "RULE each of the six explicitly, deriving from the strategy's own "
            "frozen clauses where a derivation exists (e.g. open at the period-1 "
            "execution date at open(t+1) per 6.5, notional = the sealed opening "
            "cash, terminal = MARK because the strategy's own terminal NAV is a "
            "mark and not a liquidation) -- and record each derivation, so the "
            "ruling is auditable rather than asserted.",
            "RULE that the benchmark is defined by an externally standard "
            "convention named in full (e.g. a stated total-return convention), "
            "accepting that this OVERRIDES 2.5's same-handling requirement and "
            "therefore requires 2.5 to be amended rather than silently read "
            "around.",
            "RULE that gate 1 cannot be evaluated under the current frozen "
            "text and amend 9.4 -- the primary gate -- before any replay. This "
            "is the option that must be taken if the first two cannot be done "
            "without looking at strategy performance.",
        ),
        blocks=("B0_2_retrospective_replay", "final_provenance_seal"),
        opened_by=(
            "B0.2 authorization R6 (benchmark semantics review), 2026-08-19. "
            "Reached from the B0.1 diagnostic terminal report, which found no "
            "sealed benchmark artefact in the B0.1 baseline seal's datasets or "
            "derived lists and no 0050 row in data/b0/price_panel.parquet. "
            "SEMANTICS RULED 2026-08-19 (M-3 ruling B1-B12, "
            "EVALUATION_PROTOCOL_COMPLETION) and recorded in "
            "core/b0_benchmark_construction.py. The item REMAINS OPEN per B10, "
            "which closes it only once the rules are in the Master/registry AND "
            "the canonical benchmark materialization is complete. "
            "MATERIALIZATION IS NOW BLOCKED ON DATA, AND THE RULING'S PREMISE "
            "FOR THAT STEP DOES NOT HOLD: R5 classified the gap as `not a data "
            "reconstruction block because admissible raw 0050 exports exist and "
            "are hash-manifested`, but the only hash-manifested 0050 lineage "
            "(tej_exports/DataExport0806/`0050 股價、報酬率 2005-20260806`, 10 "
            "xlsx) carries exactly three columns — date, ADJUSTED price, return "
            "%% — and is byte-identical to the REINVESTING total-return series "
            "beat_0050/data/benchmark/0050_tr.parquet (max |diff| = 0.000000 "
            "over 5,297 overlapping sessions; 2014-08-01 shows 11.3428 against "
            "a raw close of 66.25). B7 rules exactly that series inadmissible. "
            "It carries NO open (B1), NO volume (B4 adv20), NO raw close (B4 "
            "sigma20d) and NO dividend ex-date/DPS/payment-date (B7). "
            "beat_0050/data/benchmark/0050_raw.parquet has date+close only, no "
            "receipt and no manifest entry, so it satisfies neither B4 nor B7 "
            "nor B8's seal bindings. 0050 has 0 rows in "
            "data/b0/corporate_actions_ledger.csv and 0 rows in "
            "data/b0/price_panel.parquet. B8 forbids runtime live fetching, so "
            "no admissible path to these fields exists in the repository as it "
            "stands: acquiring 0050 open/volume/dividend lineage is a new "
            "sealed-input acquisition, which is a ruling to make, not an "
            "implementation detail."),
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
