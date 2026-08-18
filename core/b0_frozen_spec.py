"""Frozen B0 specification constants that carry a decision, not a preference.

Everything here was ruled by the user and must not be re-opened by editing a
default. Each entry names the ruling that fixed it. Rules that can be enforced
mechanically are enforced here rather than living only in prose, because this
project already has a documented case (`rev_accel`) where a comment saying
"must not drift" did not stop drift.

Rulings recorded: O-1 (chip semantics), V-1b (stock-dividend data requirement),
V-5 (L3 checkpoints), V-6 (Sharpe convention).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence


class FrozenSpecViolation(RuntimeError):
    """Fail-loud: something contradicted a frozen B0 ruling."""


# --- O-1 · Confirmation chip semantics ---------------------------------------
# Ruling: C1 is "multi-horizon institutional NET participation". Net measures
# direction; gross measures activity/participation intensity — a different
# concept. The choice is semantic, not empirical.
CHIP_SEMANTICS: str = "net"
CHIP_SEMANTICS_FORBIDDEN: tuple[str, ...] = ("gross",)
CHIP_GROSS_ROLE: str = "diagnostic_only"   # never canonical Confirmation


def assert_chip_semantics(semantics: str) -> None:
    """Gross may not be a fallback and may not be selected at runtime."""
    if semantics != CHIP_SEMANTICS:
        raise FrozenSpecViolation(
            f"O-1: Confirmation chip semantics is frozen to {CHIP_SEMANTICS!r}; "
            f"got {semantics!r}. Gross is diagnostic-only — it is not a fallback "
            f"and is not runtime-selectable."
        )


# --- V-6 · Sharpe convention -------------------------------------------------
# Ruling: rf = 0, named explicitly. Importing an external Taiwan risk-free
# series would immediately add which rate / which tenor / daily-vs-monthly
# alignment / PIT availability / missing values / whether cash earns it — a
# cluster of new degrees of freedom and data dependencies.
SHARPE_METRIC_NAME: str = "Sharpe_0rf"
RISK_FREE_RATE: float = 0.0
CASH_EARNS_INTEREST: bool = False   # keeps NAV and Sharpe economically consistent


def assert_sharpe_named_explicitly(name: str) -> None:
    """Documents must not say a bare 'Sharpe' — the convention must be visible."""
    if name != SHARPE_METRIC_NAME:
        raise FrozenSpecViolation(
            f"V-6: the L2 gate metric must be reported as {SHARPE_METRIC_NAME!r}, "
            f"not {name!r}. A bare 'Sharpe' hides the rf convention."
        )


# --- V-5 · L3 prospective maturity checkpoints -------------------------------
# Ruling: 36, 60, 84, 108, 132, ... No early graduation before 36; if NOT YET
# VALIDATED at a checkpoint, the next formal assessment is 24 months later.
# 24 carries no statistical magic — it is a stopping policy chosen to be sparse
# and simple rather than to reintroduce optional stopping.
L3_FIRST_CHECKPOINT_MONTHS: int = 36
L3_CHECKPOINT_INTERVAL_MONTHS: int = 24


def l3_checkpoints(count: int = 5) -> tuple[int, ...]:
    if count < 1:
        raise FrozenSpecViolation("V-5: checkpoint count must be >= 1")
    return tuple(L3_FIRST_CHECKPOINT_MONTHS + L3_CHECKPOINT_INTERVAL_MONTHS * i
                 for i in range(count))


def is_l3_assessment_month(months_elapsed: int) -> bool:
    """True only on a frozen checkpoint. Every other month is a peek, not a test."""
    if months_elapsed < L3_FIRST_CHECKPOINT_MONTHS:
        return False
    return (months_elapsed - L3_FIRST_CHECKPOINT_MONTHS) % L3_CHECKPOINT_INTERVAL_MONTHS == 0


def next_l3_checkpoint(months_elapsed: int) -> int:
    """Smallest frozen checkpoint at or after `months_elapsed`."""
    if months_elapsed <= L3_FIRST_CHECKPOINT_MONTHS:
        return L3_FIRST_CHECKPOINT_MONTHS
    over = months_elapsed - L3_FIRST_CHECKPOINT_MONTHS
    steps = -(-over // L3_CHECKPOINT_INTERVAL_MONTHS)      # ceil
    return L3_FIRST_CHECKPOINT_MONTHS + L3_CHECKPOINT_INTERVAL_MONTHS * steps


def assert_l3_assessment_allowed(months_elapsed: int) -> None:
    if not is_l3_assessment_month(months_elapsed):
        raise FrozenSpecViolation(
            f"V-5: month {months_elapsed} is not a frozen L3 checkpoint. "
            f"Next permitted assessment: month {next_l3_checkpoint(months_elapsed)}. "
            f"Assessing off-checkpoint is optional stopping."
        )


# --- V-1b · Blocking data requirements ---------------------------------------

@dataclass(frozen=True)
class VerificationResult:
    satisfied: bool
    detail: str
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BlockingDataRequirement:
    key: str
    reason: str
    required_fields: tuple[str, ...]
    blocks: tuple[str, ...]
    verifier: str                      # name in _VERIFIERS
    source_path: str = ""

    def verify(self) -> VerificationResult:
        """Satisfaction is DERIVED from the data, never asserted by hand.

        There is deliberately no settable `satisfied` field: a boolean someone
        can flip is exactly how a blocking requirement gets closed without the
        data ever arriving.
        """
        fn = _VERIFIERS.get(self.verifier)
        if fn is None:
            return VerificationResult(False, f"no verifier registered: {self.verifier!r}")
        return fn(self)


# --- V-1b verifier -----------------------------------------------------------

STOCK_DIVIDEND_REQUIRED_FIELDS: tuple[str, ...] = (
    "stock_id", "ex_right_date", "distribution_ratio_or_new_shares",
    "actual_credit_tradable_date",
    # W-1: the source must carry its own three-state classification, so that a
    # known gap is distinguishable from an unnoticed event.
    "reconstructibility", "reason",
)


def _text(v) -> str:
    """Empty-safe string. A CSV reader turns a blank cell into NaN, whose str()
    is the truthy 'nan' — that would let a missing reason pass as present."""
    if v is None or v != v:            # NaN
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", ".") else s


def _parse_date(v) -> str | None:
    """Accept YYYYMMDD or YYYY/MM/DD or YYYY-MM-DD; return normalised or None."""
    if v is None:
        return None
    s = str(v).strip().replace("/", "-")
    if not s or s == ".":
        return None
    if len(s) == 8 and s.isdigit():
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    parts = s.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    y, m, d = (int(p) for p in parts)
    if not (1900 <= y <= 2999 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, m, d)


def verify_stock_dividend_rows(rows: Sequence[dict]) -> VerificationResult:
    """Non-performance verification only: schema, date semantics, coverage.

    Checks exactly what V-1a/V-1b need to be implementable — never any return,
    ranking or selection quantity.

    Under the W-1/W-2 rulings this verifies that the source is *semantically
    sufficient and correctly classified*, not that it is complete. A row with no
    credit date is a legitimate NOT_RECONSTRUCTIBLE event; it fails when the
    portfolio is actually exposed to it (core.b0_corporate_actions), not here.
    What still fails at source level are defects that no exposure test could
    recover from: a missing column, an unparseable ex-right date, or a credit
    date that precedes ex-right.
    """
    from core.b0_corporate_actions import (
        NOT_RECONSTRUCTIBLE, RECONSTRUCTIBILITY_STATES, classify_receivable_ordering,
    )

    if not rows:
        return VerificationResult(False, "source is empty or absent")

    missing_cols = [c for c in STOCK_DIVIDEND_REQUIRED_FIELDS if c not in rows[0]]
    if missing_cols:
        return VerificationResult(False, f"missing required columns: {missing_cols}")

    n = len(rows)
    bad_ex = before_ex = 0
    ordering: dict[str, int] = {}
    states: dict[str, int] = {}
    years: dict[str, int] = {}
    unclassified = 0
    for r in rows:
        ex = _parse_date(r.get("ex_right_date"))
        cr = _parse_date(r.get("actual_credit_tradable_date"))
        ratio = r.get("distribution_ratio_or_new_shares")
        if ex is None:
            bad_ex += 1
        else:
            years[ex[:4]] = years.get(ex[:4], 0) + 1

        order = classify_receivable_ordering(ex, cr)
        ordering[order] = ordering.get(order, 0) + 1
        if order == "before_ex":
            before_ex += 1

        # The source must state its own classification; a source that carries
        # only raw fields leaves "we cannot rebuild this" and "we never saw it"
        # indistinguishable at final-seal time.
        st = _text(r.get("reconstructibility"))
        if st not in RECONSTRUCTIBILITY_STATES:
            unclassified += 1
        else:
            states[st] = states.get(st, 0) + 1
        if st == NOT_RECONSTRUCTIBLE and not _text(r.get("reason")):
            unclassified += 1
        if ratio is None or str(ratio).strip() in ("", "."):
            pass          # per-event concern, carried by `reconstructibility`

    diagnostics = {
        "rows": n,
        "bad_ex_right_date": bad_ex,
        "receivable_ordering": dict(sorted(ordering.items())),
        "reconstructibility": dict(sorted(states.items())),
        "rows_by_ex_right_year": dict(sorted(years.items())),
    }

    problems = []
    if bad_ex:
        problems.append(f"{bad_ex} unparseable ex_right_date")
    if before_ex:
        # W-2 allows credit == ex-right (a zero-day receivable). A credit date
        # strictly BEFORE ex-right is not a short interval, it is impossible.
        problems.append(f"{before_ex} rows where the credit date precedes ex-right")
    if unclassified:
        problems.append(f"{unclassified} rows without a valid reconstructibility "
                        f"state and reason")

    if problems:
        return VerificationResult(False, "; ".join(problems), diagnostics)
    return VerificationResult(True, f"{n} rows verified and classified", diagnostics)


def _verify_stock_dividend_source(req: "BlockingDataRequirement") -> VerificationResult:
    path = req.source_path
    if not path or not os.path.exists(path):
        return VerificationResult(
            False, f"authoritative stock-dividend source not present at {path or '<unset>'}")
    try:
        import pandas as pd
        df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
        rows = df.to_dict("records")
    except Exception as exc:                       # noqa: BLE001 - reported, not hidden
        return VerificationResult(False, f"source unreadable: {exc}")
    return verify_stock_dividend_rows(rows)


# --- D-1 verifier · price-universe survivorship ------------------------------

PRICE_UNIVERSE_REQUIRED_FIELDS: tuple[str, ...] = (
    "year", "securities", "dropped_next_year", "dropped_but_traded_to_year_end",
)


def verify_price_universe_churn(rows: Sequence[dict]) -> VerificationResult:
    """A price corpus that never loses a security is survivorship-truncated.

    Delistings happen every year in any real market. A vintage that reports zero
    departures is not a market observation, it is a universe filter — and a
    filter applied at export time knows which securities survived, which is the
    strongest form of look-ahead a price source can carry.

    Non-performance only: this counts securities, never returns.
    """
    if not rows:
        return VerificationResult(False, "price-universe churn report is absent")
    missing_cols = [c for c in PRICE_UNIVERSE_REQUIRED_FIELDS if c not in rows[0]]
    if missing_cols:
        return VerificationResult(False, f"missing required columns: {missing_cols}")

    zero_drop_years, late_drop_years = [], []
    for r in rows:
        year = str(r.get("year"))
        try:
            dropped = int(r.get("dropped_next_year") or 0)
            to_end = int(r.get("dropped_but_traded_to_year_end") or 0)
        except (TypeError, ValueError):
            return VerificationResult(False, f"unparseable churn counts for {year}")
        if dropped == 0:
            zero_drop_years.append(year)
        if to_end > 0:
            late_drop_years.append((year, to_end))

    diagnostics = {
        "years": len(rows),
        "zero_departure_years": zero_drop_years,
        # REPORTED, NOT GATED. A security that trades to the final session of a
        # year and delists in the first days of January vanishes exactly like a
        # filtered-out one, and that happens every year: all 16 occurrences in the
        # repaired corpus have a reference delisting on or within days of the next
        # trading session. Gating on `> 0` would therefore fail every real corpus,
        # which is not a gate but a permanent block. The contradiction it was
        # reaching for — terminations nothing accounts for — is what C2 in
        # core.b0_price_universe measures, using the same `explained` instrument
        # the security-level check uses.
        "vanished_after_trading_to_year_end": dict(late_drop_years),
        "vanished_at_year_end_is_reported_not_gated": True,
    }
    if zero_drop_years:
        # This one IS structural and needs no reference: securities leave the
        # exchange every year, so a year that loses nobody is a filter.
        return VerificationResult(
            False,
            f"{len(zero_drop_years)} year(s) with zero departures {zero_drop_years}",
            diagnostics)
    return VerificationResult(True, f"{len(rows)} years of churn verified", diagnostics)


def _read_rows(path: str):
    import pandas as pd
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    return df.to_dict("records")


def _verify_price_universe_source(req: "BlockingDataRequirement") -> VerificationResult:
    """Cross-source audit first; the source-only churn report is the backstop.

    Two verifications rather than one because they fail for different reasons: the
    audit compares the corpus against an independent security master and can say
    "securities left the exchange and this corpus lost nobody", while the churn
    report needs no reference at all and still catches the shape of the defect.
    A repaired corpus has to satisfy both.
    """
    from core.b0_price_universe import verify_price_universe

    path = req.source_path
    if not path or not os.path.exists(path):
        return VerificationResult(
            False, f"price-universe audit not present at {path or '<unset>'}")
    clusters_path = os.path.join(os.path.dirname(path), "price_universe_clusters.csv")
    try:
        rows = _read_rows(path)
        clusters = _read_rows(clusters_path) if os.path.exists(clusters_path) else []
    except Exception as exc:                       # noqa: BLE001 - reported, not hidden
        return VerificationResult(False, f"source unreadable: {exc}")

    verdict = verify_price_universe(rows, clusters)
    diagnostics = dict(verdict.diagnostics)

    churn_path = os.path.join(os.path.dirname(path), "price_universe_churn.csv")
    if os.path.exists(churn_path):
        backstop = verify_price_universe_churn(_read_rows(churn_path))
        diagnostics["source_only_backstop"] = {
            "satisfied": backstop.satisfied, "detail": backstop.detail}
        if verdict.admissible and not backstop.satisfied:
            return VerificationResult(
                False, f"cross-source audit passed but the source-only backstop "
                       f"did not: {backstop.detail}", diagnostics)

    return VerificationResult(verdict.admissible, verdict.detail, diagnostics)


# --- S-3b verifier (O-F ruling 5) --------------------------------------------
#
# S-3b is ENFORCEMENT, not source completeness. O-F closed with an incomplete
# status source on purpose: 293 of 352 terminations in the corpus have no
# PIT-available explanation and never will, because the only source that knows
# them all is a current snapshot that rewrites its own history. Requiring zero
# would therefore never be met, and a requirement that can never be met stops
# being read.
#
# What CAN be required is that the route behaves correctly on both sides of the
# exposure line. The verifier does not read a verdict; it RUNS the production
# guard over real securities and compares what happened.

S3B_ENFORCEMENT_PROPERTIES: tuple[str, ...] = (
    "pit_safe_status_explains",
    "held_unexplained_gap_aborts",
    "unheld_unexplained_gap_does_not_abort",
    "all_routes_invoke_the_guard",
)

S3B_REQUIRED_FIELDS: tuple[str, ...] = (
    "property", "stock_id", "as_of", "price_observed_through",
    "expected_sessions", "known_status", "status_available_from",
    "held", "expected_outcome",
)

# The exposure-scoped guard, and the unscoped one it replaced. A route calling
# the second directly would abort on names B0 does not hold, which O-F ruled is
# a diagnostic rather than a failure.
S3B_GUARD_SYMBOL = "assert_no_unexplained_gap_in_holdings"
S3B_FORBIDDEN_DIRECT_GUARD = "assert_no_unexplained_price_gap"
S3B_ROUTE_MODULES: tuple[str, ...] = (
    "core.b0_route", "core.b0_adapter_retrospective",
    "core.b0_adapter_production")


def verify_status_guard_enforcement(rows: Sequence[dict]) -> VerificationResult:
    """Run the real guard on real securities; derive the verdict from what it did."""
    from core.b0_pit_observability import (
        EXPLAINED_SUSPENSION, PitPriceObservation, PriceObservabilityError,
        assert_no_unexplained_gap_in_holdings, classify_price_gap,
    )

    if not rows:
        return VerificationResult(False, "S-3b enforcement fixture is absent")
    missing_cols = [c for c in S3B_REQUIRED_FIELDS if c not in rows[0]]
    if missing_cols:
        return VerificationResult(False, f"missing required columns: {missing_cols}")

    proved: set[str] = set()
    problems: list[str] = []
    diagnostics: dict = {"cases": len(rows), "securities": sorted(
        {_text(r["stock_id"]) for r in rows})}

    for r in rows:
        prop = _text(r["property"])
        sid = _text(r["stock_id"])
        as_of = _text(r["as_of"])
        sessions = tuple(x for x in _text(r["expected_sessions"]).split(";") if x)
        try:
            obs = PitPriceObservation(
                as_of=as_of, stock_id=sid,
                price_observed_through=_text(r["price_observed_through"]) or None,
                expected_sessions=sessions,
                known_status=_text(r["known_status"]) or "listed",
                status_available_from=_text(r["status_available_from"]) or None)
        except Exception as exc:                       # pragma: no cover
            problems.append(f"{prop}/{sid}: observation rejected: {exc}")
            continue

        if prop == "pit_safe_status_explains":
            verdict = classify_price_gap(obs)
            if verdict.classification != EXPLAINED_SUSPENSION:
                problems.append(
                    f"{sid}: a PIT-available {obs.known_status!r} status filed "
                    f"{obs.status_available_from} classified as "
                    f"{verdict.classification}, not {EXPLAINED_SUSPENSION}")
            else:
                proved.add(prop)
                diagnostics["explained_case"] = {
                    "stock_id": sid, "status": obs.known_status,
                    "available_from": obs.status_available_from,
                    "sessions_stale": verdict.sessions_stale}

        elif prop == "held_unexplained_gap_aborts":
            try:
                assert_no_unexplained_gap_in_holdings(as_of, [obs], {sid: 1000})
                problems.append(
                    f"{sid}: a HELD position with an unexplained gap did not "
                    f"abort. That is the silent NAV this guard exists to stop.")
            except PriceObservabilityError:
                proved.add(prop)
                diagnostics["abort_case"] = {
                    "stock_id": sid, "sessions_stale": obs.sessions_stale}

        elif prop == "unheld_unexplained_gap_does_not_abort":
            try:
                assert_no_unexplained_gap_in_holdings(as_of, [obs], {})
                proved.add(prop)
            except PriceObservabilityError as exc:
                problems.append(
                    f"{sid}: an unexplained gap in a name B0 does NOT hold "
                    f"aborted the route ({exc}). O-F ruled that a diagnostic.")
        else:
            problems.append(f"unknown fixture property {prop!r}")

    route_problems, route_diag = _verify_routes_invoke_guard()
    problems += route_problems
    diagnostics["route_coverage"] = route_diag
    if not route_problems:
        proved.add("all_routes_invoke_the_guard")

    unproved = [x for x in S3B_ENFORCEMENT_PROPERTIES if x not in proved]
    if unproved:
        problems.append(f"properties not proved: {unproved}")
    diagnostics["properties_proved"] = sorted(proved)
    if problems:
        return VerificationResult(False, "; ".join(problems), diagnostics)
    return VerificationResult(
        True, f"{len(S3B_ENFORCEMENT_PROPERTIES)} enforcement properties proved "
              f"on real securities", diagnostics)


def _verify_routes_invoke_guard() -> tuple[list, dict]:
    """Structural: one guard, called by the shared route, bypassed by nobody."""
    from core.b0_invariants import local_import_closure, referenced_names

    problems, diag = [], {}
    sources = dict(local_import_closure(S3B_ROUTE_MODULES))
    for module in S3B_ROUTE_MODULES:
        src = sources.get(module)
        if src is None:
            problems.append(f"{module}: not reachable in the import closure")
            continue
        names = referenced_names(src)
        diag[module] = {
            "calls_exposure_scoped_guard": S3B_GUARD_SYMBOL in names,
            "calls_unscoped_guard": S3B_FORBIDDEN_DIRECT_GUARD in names,
        }
        if S3B_FORBIDDEN_DIRECT_GUARD in names:
            problems.append(
                f"{module} calls {S3B_FORBIDDEN_DIRECT_GUARD} directly, which "
                f"aborts on names B0 does not hold (O-F ruling 2)")
    if not any(d["calls_exposure_scoped_guard"] for d in diag.values()):
        problems.append(
            f"no route module calls {S3B_GUARD_SYMBOL}; the guard exists but "
            f"nothing that produces a NAV invokes it (the S-3a/S-3b split)")
    return problems, diag


def _verify_status_guard_enforcement(req) -> VerificationResult:
    import csv as _csv

    if not req.source_path or not os.path.exists(req.source_path):
        return VerificationResult(
            False, f"S-3b enforcement fixture not built: {req.source_path}")
    try:
        with open(req.source_path, encoding="utf-8") as fh:
            rows = list(_csv.DictReader(fh))
    except OSError as exc:                             # pragma: no cover
        return VerificationResult(False, f"fixture unreadable: {exc}")
    return verify_status_guard_enforcement(rows)


_VERIFIERS = {"stock_dividend_source": _verify_stock_dividend_source,
              "price_universe_source": _verify_price_universe_source,
              "status_guard_enforcement": _verify_status_guard_enforcement}


BLOCKING_DATA_REQUIREMENTS: tuple[BlockingDataRequirement, ...] = (
    BlockingDataRequirement(
        key="stock_dividend_pit_source",
        reason=(
            "The 除權息 corpus is cash-dividend only: it carries no distribution "
            "ratio and no share credit date (schema verified across all six "
            "period files; 基本資料/公司資料.xlsx carries none either). Inferring "
            "the ratio from the ex-reference price would build a new model on a "
            "data gap — the same move already refused for TDCC publication lag. "
            "Ignoring stock dividends would instead distort the share ledger and "
            "NAV on every affected name. Closed by the 配股相關 export, which "
            "carries absolute new-share counts, 除權日 and 上市日/發放日; per W-1 "
            "each row must also carry its own three-state reconstructibility, and "
            "an unreconstructible event aborts when the portfolio is exposed to "
            "it rather than being interpolated or thresholded away."
        ),
        required_fields=STOCK_DIVIDEND_REQUIRED_FIELDS,
        blocks=("S-3", "final_provenance_seal"),
        verifier="stock_dividend_source",
        # Built by research/p0_v1b_stock_dividend/build_corporate_action_ledger.py
        # from the 配股相關 export; carries the W-1 three-state classification.
        source_path=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "b0", "stock_dividend_pit.csv"),
    ),
    BlockingDataRequirement(
        key="price_universe_survivorship",
        reason=(
            "The per-year price export drops 11-20 securities a year through "
            "2018, none of them trading to year-end, then drops 110 at "
            "2018->2019 (90 of which traded to the final session of 2018) and "
            "then loses NOBODY in 2019-2024. Zero delistings across six years "
            "is not a market fact. 74 of those 90 have independent evidence of "
            "existing after 2018 in other exports (52 carry a delisting-type "
            "suspension dated 2019-2025; e.g. 1701 delisted 2024-08-21 yet its "
            "price series stops 2018-12-28). The 2019+ vintage therefore "
            "contains only securities still listed at export time, which makes "
            "the investable universe survivorship-filtered for 87 of the 141 "
            "window months. Reconstructing the missing names from the surviving "
            "ones is impossible, and proceeding would bias every population "
            "count, the equal-weight benchmark rung, and any retrospective "
            "result upward. The remedy is a re-export of 2019-2026 prices "
            "including delisted securities, exactly as the 配股相關 export "
            "already does."
        ),
        required_fields=PRICE_UNIVERSE_REQUIRED_FIELDS,
        blocks=("S-3", "final_provenance_seal", "L2_opening"),
        verifier="price_universe_source",
        # The cross-source audit against the independent security master; the
        # source-only churn report beside it is checked as a backstop.
        source_path=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "b0", "price_universe_audit.csv"),
    ),
    BlockingDataRequirement(
        key="security_status_guard_enforcement",
        reason=(
            "O-F closed with an INCOMPLETE status source, by ruling. The vendor "
            "suspension export records halts and not all delistings; 293 of 352 "
            "terminations in the corpus have no PIT-available explanation, and "
            "the only source that identifies them all is a current snapshot "
            "whose delisting date lands on or after the first missing session in "
            "282 of 286 measured cases, and which has blanked the earlier exit "
            "of 25 of the 27 securities that later relisted. No re-export fixes "
            "that, so S-3b cannot be source completeness. It is enforcement: a "
            "PIT-safe status must EXPLAIN, an unexplained gap in a HELD security "
            "must ABORT, the same gap in a security B0 does not hold must NOT "
            "abort, and every route must reach the one exposure-scoped guard. "
            "The verifier runs the production guard over real securities rather "
            "than reading an attestation."
        ),
        required_fields=S3B_REQUIRED_FIELDS,
        blocks=("S-3b",),
        verifier="status_guard_enforcement",
        source_path=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "b0", "s3b_guard_fixture.csv"),
    ),
)


def unmet_blocking_requirements() -> list[BlockingDataRequirement]:
    """Runs each verifier — the answer comes from the data, not from a flag."""
    return [r for r in BLOCKING_DATA_REQUIREMENTS if not r.verify().satisfied]


def assert_no_blocking_requirements(stage: str = "final_provenance_seal") -> None:
    """Abort while any requirement blocking `stage` is unmet."""
    unmet = [r for r in unmet_blocking_requirements() if stage in r.blocks]
    if unmet:
        keys = ", ".join(r.key for r in unmet)
        raise FrozenSpecViolation(
            f"V-1b: {stage} is blocked by unmet data requirement(s): {keys}. "
            f"Neither inference from adjacent fields nor omission is permitted."
        )
