"""B0.8 · holder-side reorganization terms: source policy and extraction schema.

FROZEN BEFORE ANY TRANSACTION TERM IS INSPECTED (R4/R5).

That ordering is the whole point. A source policy written after looking at the
values is a policy shaped by which values would be convenient, and the
convenient value here is obvious: 8913 is the security that stopped the B0.7
replay, so any rule permissive enough to resolve it would resolve it for the
wrong reason. The policy is therefore fixed first, corpus-wide, and 8913 passes
through it as one of 158.

WHAT B0.8 IS

    B0.8   HOLDER_SIDE_REORGANIZATION_TERMS_DATA_REPAIR
    parent Frozen B0.7
    class  DataRepair

The B0.4 repair (C-63) created `holder_side_reorganization_exit` to record a
fact the authoritative status source really does establish: that a listed
security ceased trading through a reorganization. It deliberately recorded
nothing else, because nothing else was established, and it set every event to
NOT_RECONSTRUCTIBLE for that reason. B0.8 asks a different question -- can the
HOLDER TERMS be acquired from an authoritative source -- and it is a DataRepair
because the answer changes data, never semantics.

WHAT CHANGED SINCE THE B0.3 DETERMINATION

The B0.3 source-availability audit refused MOPS prose disclosures on the ground
that "conversion terms appear narratively, not as structured fields, so no
deterministic machine extraction is available". R4 overturns that premise
explicitly: a source does not have to be a structured API to be admissible, and
official prose is admissible where extraction is REPRODUCIBLE and
PROVENANCE-BOUND. So prose is back in scope, under the R6 protocol -- raw
document preserved and hash-bound, exact location recorded, and two independent
extractions that must agree on every outcome-relevant field.

That is a change in what may be READ. It is not a change in what may be
INFERRED: `FORBIDDEN_INFERENCE_INPUTS` below is unchanged and absolute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

VERSION = "B0.8"
REPAIR_CLASS = "DataRepair"
PARENT = "Frozen B0.7"
SCOPE = "HOLDER_SIDE_REORGANIZATION_TERMS_DATA_REPAIR"

# The kind this repair may touch. One kind, named, so that scope creep into the
# stock-dividend / capital-reduction fractional settlement R9 protects would be
# a code change rather than a judgement call.
REPAIRABLE_EVENT_KIND = "holder_side_reorganization_exit"


class HolderTermsPolicyViolation(RuntimeError):
    """A source, a schema field or a classification broke the frozen policy."""


# --- R4 · source priority, frozen before values ------------------------------

@dataclass(frozen=True)
class SourceClass:
    rank: int
    key: str
    description: str
    admissible: bool
    structured_required: bool


SOURCE_PRIORITY: tuple[SourceClass, ...] = (
    SourceClass(
        1, "official_exchange_or_mops",
        "TWSE / TPEx / MOPS official disclosure, including prose material "
        "announcements", True, False),
    SourceClass(
        2, "issuer_or_surviving_company_filing",
        "formal issuer or surviving-company filing or transaction document",
        True, False),
    SourceClass(
        3, "other_documented_first_party_legal_disclosure",
        "another explicitly documented first-party legal disclosure", True,
        False),
    SourceClass(
        99, "third_party_dataset",
        "reconstructed or vendor dataset -- COMPARATOR ONLY, may never "
        "determine canonical holder economics", False, False),
)

ADMISSIBLE_SOURCE_KEYS: tuple[str, ...] = tuple(
    s.key for s in SOURCE_PRIORITY if s.admissible)
COMPARATOR_ONLY_SOURCE_KEYS: tuple[str, ...] = tuple(
    s.key for s in SOURCE_PRIORITY if not s.admissible)

# R4, stated as a constant so it cannot quietly become "structured only" again.
PROSE_IS_ADMISSIBLE = True
PROSE_ADMISSIBILITY_CONDITIONS: tuple[str, ...] = (
    "the raw document is preserved and hash-bound",
    "the exact location of the terms inside it is recorded",
    "extraction is reproducible from the preserved bytes alone",
    "an independent second extraction agrees on every outcome-relevant field",
)

# --- R8 · what may never enter a reconstruction ------------------------------
# Absolute, and deliberately including the two that would be tempting HERE: the
# B0.7 blocker's ~NT$14 exposure, and the fact that it blocks at all.
FORBIDDEN_INFERENCE_INPUTS: tuple[str, ...] = (
    "post_event_prices",
    "price_ratios",
    "nav_continuity",
    "market_capitalization_continuity",
    "b0_holdings",
    "b0_claim_size",
    "whether_the_event_blocks_replay",
    "eventual_strategy_performance",
)
MATERIALITY_WAIVER_AUTHORIZED = False


# --- R5 · the extraction schema, frozen before values ------------------------

@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str                  # identity | terms | timing | provenance
    outcome_relevant: bool     # R6 requires exact agreement on these
    description: str


EXTRACTION_SCHEMA: tuple[FieldSpec, ...] = (
    FieldSpec("old_security_id", "identity", True,
              "the disappearing security as it is identified in the ledger"),
    FieldSpec("transaction_type", "identity", True,
              "merger / holding-company share transfer / other, as the "
              "authoritative document names it"),
    FieldSpec("successor_security_id", "terms", True,
              "the security the holder receives; absent for a pure cash exit"),
    FieldSpec("stock_conversion_ratio", "terms", True,
              "successor shares per one old share, exact rational"),
    FieldSpec("cash_consideration_per_old_share", "terms", True,
              "cash per one old share; absent for a pure stock exchange"),
    FieldSpec("holder_effective_boundary", "timing", True,
              "the date on which the holder ceases to hold the old security"),
    FieldSpec("settlement_date", "timing", True,
              "when cash consideration becomes available to the holder"),
    FieldSpec("successor_credit_date", "timing", True,
              "when successor shares are credited to the holder"),
    FieldSpec("successor_tradable_date", "timing", True,
              "when credited successor shares become tradable"),
    FieldSpec("fractional_share_treatment", "terms", True,
              "what the document says happens to a fractional entitlement: "
              "cash in lieu, retained claim, or unstated"),
    FieldSpec("source_document_identity", "provenance", False,
              "authority, endpoint and document identifier"),
    FieldSpec("source_publication_date", "provenance", False,
              "the document's own publication date"),
    FieldSpec("source_raw_sha256", "provenance", False,
              "sha256 of the preserved raw bytes"),
    FieldSpec("source_location", "provenance", False,
              "exact location or text span the terms were read from"),
)

SCHEMA_FIELDS: tuple[str, ...] = tuple(f.name for f in EXTRACTION_SCHEMA)
OUTCOME_RELEVANT_FIELDS: tuple[str, ...] = tuple(
    f.name for f in EXTRACTION_SCHEMA if f.outcome_relevant)
PROVENANCE_FIELDS: tuple[str, ...] = tuple(
    f.name for f in EXTRACTION_SCHEMA if f.kind == "provenance")


def schema_identity() -> dict:
    """A hashable statement of the frozen schema, for the freeze record."""
    from core.b0_canonical_hash import canonical_sha256

    payload = {
        "version": VERSION,
        "repair_class": REPAIR_CLASS,
        "scope": SCOPE,
        "repairable_event_kind": REPAIRABLE_EVENT_KIND,
        "source_priority": [[s.rank, s.key, s.admissible] for s in SOURCE_PRIORITY],
        "prose_is_admissible": PROSE_IS_ADMISSIBLE,
        "prose_conditions": list(PROSE_ADMISSIBILITY_CONDITIONS),
        "schema": [[f.name, f.kind, f.outcome_relevant] for f in EXTRACTION_SCHEMA],
        "reconstruction_classes": list(RECONSTRUCTION_CLASSES),
        "forbidden_inference_inputs": list(FORBIDDEN_INFERENCE_INPUTS),
        "materiality_waiver_authorized": MATERIALITY_WAIVER_AUTHORIZED,
    }
    return {"payload": payload, "schema_sha256": canonical_sha256(payload)}


# --- R7 · the reconstruction taxonomy ----------------------------------------

RECONSTRUCTIBLE_STOCK = "RECONSTRUCTIBLE_STOCK"
RECONSTRUCTIBLE_CASH = "RECONSTRUCTIBLE_CASH"
RECONSTRUCTIBLE_MIXED = "RECONSTRUCTIBLE_MIXED"
NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE"

RECONSTRUCTION_CLASSES: tuple[str, ...] = (
    RECONSTRUCTIBLE_STOCK, RECONSTRUCTIBLE_CASH, RECONSTRUCTIBLE_MIXED,
    NOT_RECONSTRUCTIBLE,
)

# What each resolved class must carry. A class whose required fields are not all
# present is not that class -- it is NOT_RECONSTRUCTIBLE. There is no partial
# credit, because a partially specified transition is exactly what §6.1.7
# refuses to run.
CLASS_REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    RECONSTRUCTIBLE_STOCK: (
        "successor_security_id", "stock_conversion_ratio",
        "holder_effective_boundary", "successor_credit_date"),
    RECONSTRUCTIBLE_CASH: (
        "cash_consideration_per_old_share", "holder_effective_boundary",
        "settlement_date"),
    RECONSTRUCTIBLE_MIXED: (
        "successor_security_id", "stock_conversion_ratio",
        "cash_consideration_per_old_share", "holder_effective_boundary",
        "successor_credit_date", "settlement_date"),
}


def _present(terms: Mapping[str, object], field: str) -> bool:
    v = terms.get(field)
    return v is not None and str(v).strip() != ""


def classify_reconstruction(terms: Mapping[str, object]) -> str:
    """R7 · the class the acquired terms actually support. Never an assumption.

    R7 warns specifically against assuming every merger or holding-company
    disappearance is stock-for-stock. So the class is decided by which legs the
    document establishes, and a document that establishes a stock leg without a
    credit date establishes no runnable transition at all.
    """
    unknown = sorted(set(terms) - set(SCHEMA_FIELDS))
    if unknown:
        raise HolderTermsPolicyViolation(
            f"R5: {unknown} are not in the frozen extraction schema. The schema "
            f"was frozen before values were inspected precisely so that it could "
            f"not grow a field because some event needed one.")
    has_stock = _present(terms, "successor_security_id") and _present(
        terms, "stock_conversion_ratio")
    has_cash = _present(terms, "cash_consideration_per_old_share")
    for cls in (RECONSTRUCTIBLE_MIXED, RECONSTRUCTIBLE_STOCK, RECONSTRUCTIBLE_CASH):
        if cls == RECONSTRUCTIBLE_MIXED and not (has_stock and has_cash):
            continue
        if cls == RECONSTRUCTIBLE_STOCK and not has_stock:
            continue
        if cls == RECONSTRUCTIBLE_CASH and not has_cash:
            continue
        if all(_present(terms, f) for f in CLASS_REQUIRED_FIELDS[cls]):
            return cls
    return NOT_RECONSTRUCTIBLE


def assert_extraction_admissible(record: Mapping[str, object]) -> None:
    """R4/R6 · refuse a record before it can become a canonical value."""
    src = str(record.get("source_class", ""))
    if src in COMPARATOR_ONLY_SOURCE_KEYS:
        raise HolderTermsPolicyViolation(
            f"R4: {src!r} is comparator-only and may never determine canonical "
            f"holder economics.")
    if src not in ADMISSIBLE_SOURCE_KEYS:
        raise HolderTermsPolicyViolation(
            f"R4: {src!r} is not a frozen source class; admissible classes are "
            f"{ADMISSIBLE_SOURCE_KEYS}.")
    for field in PROVENANCE_FIELDS:
        if not _present(record, field):
            raise HolderTermsPolicyViolation(
                f"R6: an upgraded event must carry {field}; an extraction that "
                f"cannot be returned to its source is not reproducible.")
    used = [k for k in FORBIDDEN_INFERENCE_INPUTS if record.get(k)]
    if used:
        raise HolderTermsPolicyViolation(
            f"R8: {used} were recorded as reconstruction inputs. Market and "
            f"portfolio outcomes may never determine holder economics, and no "
            f"materiality waiver exists.")


def assert_independent_agreement(first: Mapping[str, object],
                                 second: Mapping[str, object]) -> None:
    """R6 · two extractions from the SAME authoritative source must agree.

    Exactly, on every outcome-relevant field. Not "substantially", and not on a
    subset: a disagreement about a credit date is a disagreement about when the
    holder owned what, and there is no reading of that which is a rounding
    difference.
    """
    disagree = [f for f in OUTCOME_RELEVANT_FIELDS
                if str(first.get(f) or "").strip()
                != str(second.get(f) or "").strip()]
    if disagree:
        raise HolderTermsPolicyViolation(
            f"R6: independent extractions disagree on {disagree}. The event "
            f"stays NOT_RECONSTRUCTIBLE; choosing between them by price, "
            f"portfolio continuity or later returns is forbidden by R8.")
