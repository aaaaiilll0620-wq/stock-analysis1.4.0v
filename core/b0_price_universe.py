"""D-1 · price-universe completeness verification.

The defect: from 2019 the price export contains only securities still listed at
export time, so 87 of the 141 window months replay a universe from which every
later-delisted security has been removed. Every cross-sectional quantity built on
it — the complete-case population, the eligibility counts, and the equal-weight
universe that benchmark rung (1) divides by — is biased upward.

WHAT THIS MODULE MUST NOT DO, all of which would produce a verifier that passes
for the wrong reason:

  * hard-code the securities observed to be missing. The list was READ OFF the
    contaminated corpus; a verifier that checks for those names would pass any
    corpus that happens to contain them and fail nothing else.
  * accept a manual `satisfied` flag. Satisfaction is computed or it is nothing.
  * require "at least N delistings a year". That is an invented threshold, and a
    threshold is a number somebody can move until the data fits.
  * consult holdings, SelectionScore, or any performance quantity. Whether the
    data is admissible cannot depend on what the strategy does with it.

Instead the gates are STRUCTURAL IMPOSSIBILITIES — statements that cannot be true
of any real market, at any magnitude:

  C1  A year in which an independent reference records delistings while the
      corpus loses nobody at all. Securities left the exchange; the corpus says
      none did. One such year is a contradiction; the size does not matter.
  C2  A date on which two or more securities' price series terminate for good
      and those terminations are UNEXPLAINED — neither the reference's delisting
      date nor a filed non-trading status accounts for them. Real departures do
      not synchronise; export boundaries do.

      C2 originally compared the cluster date against delistings recorded ON that
      same date. That was wrong and had to be corrected: a delisting date is by
      construction at or after the last trading day (typically the next day, and
      after a long suspension it can be seven months later), so "no delisting on
      this exact date" is the NORMAL case for a perfectly clean cluster. The
      first form fired on 2018-09-17 — six securities whose last session was the
      17th, whose filed status turns to `delisted` on the 18th, and whose formal
      delisting is 2018-10-01 — which is not a defect at all. It happened to also
      fire on the real contamination, so the false positive was masked. The
      corrected gate uses the same "unexplained" notion as the security-level
      check, and still fails the contaminated corpus (90 terminations on
      2018-12-28 whose reference delistings fall in 2019-2024).

Magnitude is REPORTED (`unexplained_missing_though_listed`) so a reader can size
the damage, but it is deliberately not a gate: turning it into one would require
choosing how much absence is acceptable, and there is no defensible number.

The reference (`基本資料/公司資料.xlsx`) is a CURRENT SNAPSHOT — its 上市別 column
is rewritten on delisting, which is why scope must be taken from the historical
listing-date columns instead. Under O-E it is therefore NOT_PIT_SAFE and may
never become a B0 runtime input; it is admissible here because auditing whether
another source is complete is not a point-in-time decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

# The reference may audit; it may not be read at decision time.
REFERENCE_IS_AUDIT_ONLY: bool = True
REFERENCE_IS_CURRENT_SNAPSHOT: bool = True

# Named so that reintroducing either is visible in a diff.
MINIMUM_DELISTINGS_PER_YEAR = None
ACCEPTABLE_MISSING_FRACTION = None


class PriceUniverseError(RuntimeError):
    """Fail-loud: a price source cannot be shown to carry a complete universe."""


AUDIT_REQUIRED_FIELDS: tuple[str, ...] = (
    "year", "expected_from_reference", "observed_in_corpus", "missing",
    "missing_though_listed_after_year_end", "unexplained_missing_though_listed",
    "exits_observed", "exits_expected_from_reference",
)

CLUSTER_REQUIRED_FIELDS: tuple[str, ...] = (
    "date", "corpus_terminations", "unexplained_terminations_on_date",
)


@dataclass(frozen=True)
class UniverseVerdict:
    admissible: bool
    detail: str
    diagnostics: Mapping[str, object] = field(default_factory=dict)


def _int(v, name, where):
    if v is None or (isinstance(v, float) and v != v) or str(v).strip() == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        raise PriceUniverseError(f"{where}: {name}={v!r} is not a count") from None


def verify_price_universe(audit_rows: Sequence[Mapping],
                          cluster_rows: Sequence[Mapping] = ()) -> UniverseVerdict:
    """Structural-impossibility gates. No names, no thresholds, no flags."""
    if not audit_rows:
        return UniverseVerdict(False, "price-universe audit is absent")
    missing_cols = [c for c in AUDIT_REQUIRED_FIELDS if c not in audit_rows[0]]
    if missing_cols:
        return UniverseVerdict(False, f"audit is missing columns: {missing_cols}")

    c1_years, magnitude = [], {}
    for r in audit_rows:
        year = str(r.get("year"))
        obs = _int(r.get("exits_observed"), "exits_observed", year)
        exp = _int(r.get("exits_expected_from_reference"),
                   "exits_expected_from_reference", year)
        unexplained = _int(r.get("unexplained_missing_though_listed"),
                           "unexplained_missing_though_listed", year)
        # obs is None for the final year: there is no following year to compare
        # against, so no claim can be made about it either way.
        if obs is not None and exp is not None and obs == 0 and exp > 0:
            c1_years.append({"year": year, "exits_expected": exp})
        if unexplained:
            magnitude[year] = unexplained

    c2_dates = []
    if cluster_rows:
        missing_cols = [c for c in CLUSTER_REQUIRED_FIELDS if c not in cluster_rows[0]]
        if missing_cols:
            return UniverseVerdict(False, f"cluster report is missing columns: {missing_cols}")
        for r in cluster_rows:
            date = str(r.get("date"))
            n = _int(r.get("corpus_terminations"), "corpus_terminations", date)
            bad = _int(r.get("unexplained_terminations_on_date"),
                       "unexplained_terminations_on_date", date)
            if n is not None and bad is not None and n >= 2 and bad >= 2:
                c2_dates.append({"date": date, "terminations": n,
                                 "unexplained": bad})

    diagnostics = {
        "years_audited": len(audit_rows),
        "C1_years_with_no_exits_despite_reference_delistings": c1_years,
        "C2_unexplained_termination_clusters": c2_dates,
        "unexplained_missing_though_listed_by_year": magnitude,
        "magnitude_is_reported_not_gated": True,
    }

    problems = []
    if c1_years:
        yrs = ", ".join(f"{d['year']}(ref={d['exits_expected']})" for d in c1_years)
        problems.append(
            f"C1: {len(c1_years)} year(s) in which the corpus lost no securities at "
            f"all while the reference records delistings: {yrs}")
    if c2_dates:
        ds = ", ".join(f"{d['date']}(n={d['terminations']}, "
                       f"unexplained={d['unexplained']})" for d in c2_dates)
        problems.append(
            f"C2: {len(c2_dates)} date(s) where price series terminate together "
            f"with nothing accounting for them: {ds}")

    if problems:
        return UniverseVerdict(False, "; ".join(problems), diagnostics)
    return UniverseVerdict(
        True, f"{len(audit_rows)} years show ordinary entry/exit churn", diagnostics)


# --- D1-6 · source admissibility ---------------------------------------------
# Closing D-1 is not only "a better export exists". The contaminated one must
# stop being selectable, or a cache-order change silently reinstates it.

@dataclass(frozen=True)
class PriceSourceContract:
    name: str
    importer_version: str
    content_sha256: str
    schema_sha256: str
    date_min: str
    date_max: str
    securities: int
    includes_delisted: bool          # the whole point of the re-export
    audit_sha256: str                # the audit that verified it
    lineage: str = ""

    def __post_init__(self) -> None:
        for f in ("name", "importer_version", "content_sha256", "schema_sha256",
                  "date_min", "date_max", "audit_sha256"):
            if not str(getattr(self, f)).strip():
                raise PriceUniverseError(
                    f"D1-7: price source {self.name or '?'} must declare {f}. "
                    f"A hash written only in a closure document is not provenance "
                    f"the route can check.")
        if self.securities <= 0:
            raise PriceUniverseError(f"D1-7: {self.name}: securities must be > 0")

    def to_dataset_provenance(self):
        from core.b0_provenance import DatasetProvenance
        return DatasetProvenance(
            name=self.name, content_sha256=self.content_sha256,
            schema_sha256=self.schema_sha256, date_min=self.date_min,
            date_max=self.date_max, importer_version=self.importer_version)


# Fingerprints of sources shown to be survivorship-filtered. Quarantine is by
# content hash, not by path: renaming or copying a contaminated export must not
# launder it.
CONTAMINATED_CORPUS_SHA256 = (
    "aeda65b99ec9d4b4e02f96e20e3d915c5519329d010415f2be3e4cb667ea49c1")

_QUARANTINED: dict[str, str] = {
    # The 2019+ vintage of ~/tej_cache/price_valuation. Identified by content,
    # not by name: this is one artefact, not a list of securities, so nothing
    # here tells the verifier which stocks to look for.
    CONTAMINATED_CORPUS_SHA256: (
        "survivorship-filtered from 2019: the independent security master records "
        "8-18 delistings a year for 2019-2025 while this corpus loses nobody, and "
        "90 price series terminate together on 2018-12-28 with no delisting behind "
        "that date"
    ),
}


def quarantine_source(content_sha256: str, reason: str) -> None:
    if not content_sha256.strip() or not reason.strip():
        raise PriceUniverseError(
            "D1-6: a quarantine entry needs the content hash and the reason")
    _QUARANTINED[content_sha256] = reason


def quarantined_sources() -> Mapping[str, str]:
    return dict(_QUARANTINED)


def assert_price_source_admissible(contract: PriceSourceContract) -> None:
    """A contaminated source must fail loudly, never be silently deselected."""
    reason = _QUARANTINED.get(contract.content_sha256)
    if reason is not None:
        raise PriceUniverseError(
            f"D1-6: price source {contract.name!r} (sha {contract.content_sha256[:12]}) "
            f"is quarantined: {reason}. It may not be reached through a runtime "
            f"overlay, a fallback, or cache selection."
        )
    if not contract.includes_delisted:
        raise PriceUniverseError(
            f"D1-6: price source {contract.name!r} declares includes_delisted="
            f"False. A universe filtered to survivors is the D-1 defect itself, "
            f"whatever else the source gets right."
        )
