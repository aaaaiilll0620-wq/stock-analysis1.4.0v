"""C-48 · the frozen lineage of `pbr_tse`, and what a source must declare.

B-09 freezes Value on the TSE exchange PBR series. It did not say what an
ADMISSIBLE 2019+ source of that series is, and P-1b registered the gap as
`value_pbr_lineage_2019plus`. This module is where the ruling that closed it
lives, because a ruling recorded only in a document is not something a route can
check.

The ruling (R1-R7, §11 C-48) rests on measurement, not on preference. Official
exchange PBR was compared against the admissible pre-2019 lineage on the same
security and the same trading session across all 36 month-ends 2016-2018:

    TWSE 上市   32,284 comparisons   100.00% exact equality, max |Δ| = 0.00
    TPEx 上櫃   26,419 comparisons    99.96% exact equality, max |Δ| = 0.09
                the 11 differences are confined to 2016-01 / 2016-02, and the
                median signed difference is 0.00 on both boards
    official_only = 0 — the exchange series never carries a security the frozen
                lineage lacks, so admitting it cannot widen the universe
    same-session keying independently confirmed: 18,963 of 18,963 closes agree

That is lineage CONTINUITY evidence — same stock, same session, same number —
not an argument that official data is nicer. All 87 affected decision months were
harvested from both exchanges with zero unresolved transport failures.

Three things this module deliberately makes impossible rather than discouraged:

  * **`PBR_TEJ` cannot be selected.** It is not a fallback, not a gap-filler and
    not a tie-break. B-09 froze the TSE lineage; a second valuation column
    reachable at run time is the silent substitution the freeze exists to stop.
  * **A live endpoint cannot be a source.** L2 reading `GET .../peQryDate` mid-run
    would mean the numbers behind a sealed result depend on what a web service
    answered that afternoon. Sources must be harvested, hashed and bound first.
  * **A missing ratio cannot become a number.** No imputation, no cross-board
    backfill, no book-equity-over-shares derivation. NA propagates to §4.1
    complete-case, which is the behaviour B0 already has for this field.

The TPEx limitation is recorded rather than papered over: before the source began
exposing statement-vintage metadata (measured: absent 2024-12-31, present
2025-01-02), the historical payload does not name the financial-statement period
behind the denominator. The admissible claim is "the official contemporaneous
daily exchange PBR for that session"; the inadmissible one is any statement about
WHICH statement vintage stood behind it. Both are stated verbatim below so that a
later reader cannot upgrade the first into the second by paraphrase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# Bumped when the parsing or normalisation of an official payload changes in a
# way that could move a number. It is part of the sealed identity, so a silent
# parser fix cannot masquerade as the same source.
VALUATION_PARSER_VERSION = "official_pbr_parser_v1"


class ValuationSourceError(RuntimeError):
    """Fail-loud: a valuation source contradicts the frozen lineage."""


# --- R1 · the lineage, by era -------------------------------------------------
# The boundary is the SAME one §2.8.3 already fixed for prices. Two vintages of
# one field, split at one date, is a boundary; a per-year choice would be a free
# parameter.

LINEAGE_BOUNDARY = "2019-01-01"

VALUATION_LINEAGE: tuple[tuple[str, str, str], ...] = (
    ("<= 2018-12-31", "yearly_export_pbr_tse",
     "股價淨值比-TSE from the admissible yearly export — the `<= 2018` side of "
     "the §2.8.3 vintage boundary"),
    (">= 2019-01-01", "official_exchange_pbr",
     "TWSE 個股日本益比、殖利率及股價淨值比 for 上市, TPEx 個股本益比、殖利率及"
     "股價淨值比 for 上櫃, keyed to the trading session"),
)

OFFICIAL_BOARDS: tuple[str, ...] = ("TWSE", "TPEx")

# R1. Not a preference — the frozen definition B-09 already carries.
VALUE_DEFINITION = "B/M = 1 / PBR, industry-relative cross-sectional percentile"
TEJ_SUBSTITUTION_ALLOWED = False

# R5. A source is admissible only once it is harvested, hashed and bound.
RUNTIME_FETCH_ALLOWED = False

# R2. Verbatim, because the difference between these two sentences is the whole
# limitation and paraphrase erodes it.
TPEX_PRE_VINTAGE_ADMISSIBLE_CLAIM = (
    "Official historical daily PBR is admissible.")
TPEX_PRE_VINTAGE_INADMISSIBLE_CLAIM = (
    "Exact underlying financial-statement vintage is not directly observable "
    "from the historical payload and must not be claimed.")
TPEX_VINTAGE_DISCLOSURE_FIRST_SESSION = "2025-01-02"
TPEX_VINTAGE_MAY_BE_INFERRED = False

# R3. The four forbidden repairs, named so that adding one is a visible edit.
MISSING_VALUE_POLICY = "NA -> §4.1 complete-case"
FORBIDDEN_GAP_REPAIRS: tuple[str, ...] = (
    "tej_pbr_fallback",
    "imputation",
    "cross_board_backfill",
    "derived_book_to_market_replacement",
)

# R4. Board attribution is point-in-time by construction: a security is 上市 on
# session s because TWSE published it on s. §2.3 shows the current 上市別 label is
# rewritten on delisting, so back-filling history from it is look-ahead.
BOARD_ATTRIBUTION_SOURCE = "contemporaneous_exchange_payload"
CURRENT_LISTING_LABEL_ALLOWED = False


# --- R5 · what a sealed valuation source must declare -------------------------

@dataclass(frozen=True)
class ValuationSourceContract:
    """D1-7 shape, applied to the valuation series rather than to prices."""

    name: str
    era: str                        # one of VALUATION_LINEAGE[i][0]
    lineage: str                    # one of VALUATION_LINEAGE[i][1]
    importer_version: str
    parser_version: str
    content_sha256: str
    schema_sha256: str
    date_min: str
    date_max: str
    sessions: int
    securities: int
    coverage_rate_min: float
    coverage_rate_max: float
    na_policy: str
    live_fetch: bool
    upstream_sha256: Mapping[str, str]   # raw payload identity, per unit
    board_attribution_source: str = BOARD_ATTRIBUTION_SOURCE

    def __post_init__(self) -> None:
        for f in ("name", "era", "lineage", "importer_version", "parser_version",
                  "content_sha256", "schema_sha256", "date_min", "date_max"):
            if not str(getattr(self, f)).strip():
                raise ValuationSourceError(
                    f"C-48: valuation source {self.name or '?'} must declare {f}. "
                    f"A hash written only in a closure document is not provenance "
                    f"the route can check.")
        if self.sessions <= 0 or self.securities <= 0:
            raise ValuationSourceError(
                f"C-48: {self.name}: sessions and securities must be > 0")
        if not self.upstream_sha256:
            raise ValuationSourceError(
                f"C-48: {self.name} declares no upstream payload hashes. A panel "
                f"whose inputs cannot be named is not a sealed source.")


def known_lineages() -> tuple[str, ...]:
    return tuple(l for _, l, _ in VALUATION_LINEAGE)


def lineage_for(session: str) -> str:
    """Which frozen lineage owns a trading session. No third answer exists."""
    if not session or len(session) < 10:
        raise ValuationSourceError(
            f"C-48: {session!r} is not a trading session date")
    return ("official_exchange_pbr" if session >= LINEAGE_BOUNDARY
            else "yearly_export_pbr_tse")


def assert_valuation_source_admissible(contract: ValuationSourceContract) -> None:
    """Every way of getting the wrong series in has to fail loudly here."""
    if contract.lineage not in known_lineages():
        raise ValuationSourceError(
            f"C-48: {contract.name!r} declares lineage {contract.lineage!r}, which "
            f"is not one of the two frozen lineages {known_lineages()}. "
            f"PBR_TEJ in particular is not an admissible lineage under B-09.")
    if contract.era not in {e for e, _, _ in VALUATION_LINEAGE}:
        raise ValuationSourceError(
            f"C-48: {contract.name!r} declares era {contract.era!r}, which is not "
            f"one of the two frozen eras.")
    expected = dict((e, l) for e, l, _ in VALUATION_LINEAGE)[contract.era]
    if contract.lineage != expected:
        raise ValuationSourceError(
            f"C-48: era {contract.era} is frozen to lineage {expected!r}, but "
            f"{contract.name!r} declares {contract.lineage!r}. The boundary is "
            f"part of the specification, not a per-run choice.")
    if contract.live_fetch or RUNTIME_FETCH_ALLOWED:
        raise ValuationSourceError(
            f"C-48 / R5: {contract.name!r} declares live_fetch=True. L2 must "
            f"consume a harvested, hashed and provenance-bound source; a result "
            f"whose numbers depend on what a web service answered during the run "
            f"is not reproducible and not sealed.")
    if contract.na_policy != MISSING_VALUE_POLICY:
        raise ValuationSourceError(
            f"C-48 / R3: {contract.name!r} declares na_policy "
            f"{contract.na_policy!r}. The frozen policy is {MISSING_VALUE_POLICY!r}; "
            f"{list(FORBIDDEN_GAP_REPAIRS)} are all forbidden.")
    if contract.board_attribution_source != BOARD_ATTRIBUTION_SOURCE:
        raise ValuationSourceError(
            f"C-48 / R4: board attribution must come from "
            f"{BOARD_ATTRIBUTION_SOURCE!r}, not {contract.board_attribution_source!r}. "
            f"The current 上市別 label is rewritten on delisting (§2.3).")
    if contract.parser_version != VALUATION_PARSER_VERSION:
        raise ValuationSourceError(
            f"C-48: {contract.name!r} was built by parser "
            f"{contract.parser_version!r} but this build is "
            f"{VALUATION_PARSER_VERSION!r}. A parser change can move a number, so "
            f"it changes the source identity rather than being invisible.")


def limitation_record() -> dict:
    """R2/R6: the disclosures that must travel with any use of this series."""
    return {
        "tpex_pre_vintage": {
            "admissible": TPEX_PRE_VINTAGE_ADMISSIBLE_CLAIM,
            "inadmissible": TPEX_PRE_VINTAGE_INADMISSIBLE_CLAIM,
            "vintage_disclosure_first_session":
                TPEX_VINTAGE_DISCLOSURE_FIRST_SESSION,
            "may_be_inferred": TPEX_VINTAGE_MAY_BE_INFERRED,
            "status": "disclosed source-lineage limitation, not an M-3 blocker",
        },
        "coverage_regime_2025": {
            "observation": (
                "official coverage rises from the historical ~94-95% band to as "
                "high as 98.42% after 2025"),
            "may_modify_selection_semantics": False,
            "may_modify_historical_eligibility": False,
            "reopens_b09": False,
            "reopens_b09_only_if": "evidence of a valuation-semantic break",
        },
    }
