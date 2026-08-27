"""§19 · C-LF — the L3 prospective route's span endpoints, and their only producer.

L2's `price_span` and `bonus_window` each have a frozen derivation, but BOTH are
anchored on `window_start`: `build_price_panel.panel_span()` starts at January of
the calendar year of `window_start - lookback_L_months`, and the bonus window
starts the day after the P_{t-13} month-end session of the first decision month.
A single prospective decision has no `window_start`, so for the L3 route those
endpoints were UNSPECIFIED (§1.5, M-3 `l3_prospective_price_span_floor`) and had
to be ruled on before any prospective run could exist.

§19 is that ruling. This module is the ruling in the only form a route can check;
the master preregistration remains the sole semantic authority, and
`research/b0_l3/l3_assemble.py` / `l3_snapshot.py` are ENFORCEMENT — they must
refuse a span that did not come from here, and must never default one.

THREE OF THE FOUR ENDPOINTS ARE DERIVED, NOT CHOSEN (§19.2):

  price_span[1]    = execution_date. The canonical state reads only `<= as_of`,
                     so this endpoint never enters the state hash; its one
                     obligation is to cover the §6.5 execution session, and a
                     span that does not is an abort rather than a shorter run.
  bonus_window[1]  = as_of. This one is an ANTI-LOOK-AHEAD bound, not a neutral
                     endpoint: C-50/R3 divides every price BEFORE a boundary, so
                     a boundary later than as_of would restate the whole reach a
                     decision reads using an event that has not happened yet —
                     and the hashed payload carries adjusted LEVELS
                     (`month_end_prices`), not only momentum's ratio, so that
                     restatement moves the state hash.
  bonus_window[0]  = the day after the earliest required month-end price. There
                     is a SUFFICIENCY PLATEAU below it, because C-50/R3 divides
                     only what precedes the boundary: an event older than the
                     reach restates only prices older than the reach. The day
                     after is EXACTLY sufficient — a boundary on the month-end
                     session itself still cannot move any value in the reach. A
                     start LATER than that can miss a boundary inside the reach,
                     and that aborts.

THE ONE DEGREE OF FREEDOM IS THE FLOOR (§19.3):

  price_span[0]    = `lineage_price_floor`, captured ONCE at lineage inception
                     from a complete, hash-bound price leaf after the D-1
                     quarantine, and then frozen for that lineage.

The floor is not a cosmetic depth setting: it IS `spell_start`, which is a hashed
state field, and through the observed-session count inside the spell it gates
ADV20 / sigma20d availability and O-G's month-end blanking. Two routes reading
spans of different depth produce different spell starts for the SAME security at
the SAME as_of. That is why it is registered in the specification rather than
declared per run.

NO DATE IN THIS MODULE IS NORMATIVE. What is frozen is the RULE. The diagnostic
measurement that supported the ruling expected `2004-01-02`; if the first run
through the L3 manifests produces anything else, that is a stop-and-report, not a
value to adopt silently (§19.7).
"""

from __future__ import annotations

import datetime

# --- identity ------------------------------------------------------------------

M3_KEY = "l3_prospective_price_span_floor"
RULING = "C-LF"
FLOOR_RULE = "INCEPTION_CAPTURED_CORPUS_COVERAGE_FLOOR"
APPLIES_TO = "L3_PROSPECTIVE_ROUTE_ONLY"
MASTER_SECTION = "§19"

# L2's own values, recorded so that a reader can see they are NOT reused here.
# They are the output of a different rule on a different route, and this module
# never consults them.
L2_REFERENCE_SPANS = (
    ("price_span", ("2013-01-01", "2026-04-01")),
    ("bonus_window", ("2013-06-29", "2026-03-31")),
)

# §19.2, as data so that a change is a visible edit rather than a new call site.
ENDPOINT_DERIVATIONS: tuple[tuple[str, str], ...] = (
    ("bonus_window[0]", "DAY_AFTER_EARLIEST_REQUIRED_MONTH_END_PRICE"),
    ("bonus_window[1]", "AS_OF"),
    ("price_span[0]", "LINEAGE_PRICE_FLOOR"),
    ("price_span[1]", "EXECUTION_DATE"),
)

# §19.3 step 3. The three dispositions, keyed by how the period's observed
# coverage floor relates to the frozen lineage floor.
LATER, EQUAL, EARLIER = "later", "equal", "earlier"
FLOOR_DRIFT_POLICY: tuple[tuple[str, str], ...] = (
    (EARLIER, "CLIP_TO_LINEAGE_FLOOR_NEW_LINEAGE_VERSION_REQUIRED"),
    (EQUAL, "PROCEED"),
    (LATER, "ABORT_MISSING_REQUIRED_HISTORY"),
)
_DISPOSITION = dict(FLOOR_DRIFT_POLICY)


class L3SpanError(RuntimeError):
    """Fail-loud: a span endpoint was not produced by the frozen derivation."""


def _date(value: str, what: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise L3SpanError(
            "abort: %s must be an ISO date (YYYY-MM-DD); got %r" % (what, value))


# --- §19.3 · the floor ----------------------------------------------------------

def capture_lineage_floor(observed_price_coverage_floor: str,
                          source_manifest_is_hash_bound: bool,
                          leg_coverage_is_complete: bool,
                          quarantine_applied: bool) -> str:
    """The ONE-TIME capture at lineage inception. Returns the frozen floor.

    Every precondition is an explicit argument rather than an assumption, because
    each one has already failed in this project at least once:

      * a partially declared price leg (only the 2019+ archives) silently gave
        1,706 of 1,958 securities a fabricated spell start of 2019-01-02;
      * the D-1 quarantine is on an ERA of the pre-2019 cache, not on the cache,
        so the same file holds admissible and quarantined rows and the boundary
        has to be enforced at read time;
      * a floor read from files nobody hashed is not evidence a seal can bind.

    None of these can be inferred from the date string, so a caller that cannot
    attest to them may not capture a floor.
    """
    floor = str(observed_price_coverage_floor)
    _date(floor, "observed_price_coverage_floor")
    missing = [name for name, ok in (
        ("source_manifest_is_hash_bound", source_manifest_is_hash_bound),
        ("leg_coverage_is_complete", leg_coverage_is_complete),
        ("quarantine_applied", quarantine_applied)) if not ok]
    if missing:
        raise L3SpanError(
            "abort: a lineage price floor may only be captured from a complete, "
            "hash-bound price leaf with the D-1 quarantine applied; unattested: "
            "%s (§19.3 step 1)" % ", ".join(missing))
    return floor


def floor_relation(lineage_price_floor: str,
                   observed_price_coverage_floor: str) -> str:
    """`later` / `equal` / `earlier` — the observed floor, relative to the frozen one."""
    frozen = _date(lineage_price_floor, "lineage_price_floor")
    observed = _date(observed_price_coverage_floor, "observed_price_coverage_floor")
    if observed > frozen:
        return LATER
    if observed == frozen:
        return EQUAL
    return EARLIER


def assert_floor_conforms(lineage_price_floor: str,
                          observed_price_coverage_floor: str) -> str:
    """§19.3 step 3 / §19.4. Returns the disposition, or aborts.

    `later` is the only aborting relation: the declared sources no longer reach
    the depth this lineage was frozen at, so the state it would produce is not
    the state the lineage promises. `earlier` does NOT widen the run — the
    lineage stays clipped to its frozen floor, and adopting the new history is a
    new lineage version, never a quiet deepening of this one.
    """
    relation = floor_relation(lineage_price_floor, observed_price_coverage_floor)
    if relation == LATER:
        raise L3SpanError(
            "abort: the declared sources reach only %s but this lineage is frozen "
            "at %s. The required history is missing, and a shallower floor would "
            "silently move spell_start and the state hash (§19.3)."
            % (observed_price_coverage_floor, lineage_price_floor))
    return _DISPOSITION[relation]


# --- §19.2 · the endpoints ------------------------------------------------------

def price_span(lineage_price_floor: str, execution_date: str) -> tuple[str, str]:
    """(`lineage_price_floor`, `execution_date`). Never defaulted, never widened."""
    lo = str(lineage_price_floor)
    hi = str(execution_date)
    _date(lo, "lineage_price_floor")
    _date(hi, "execution_date")
    if hi < lo:
        raise L3SpanError(
            "abort: execution_date %s precedes the lineage price floor %s" % (hi, lo))
    return lo, hi


def earliest_required_month_end_month(as_of: str) -> str:
    """The oldest calendar month `month_end_prices` reaches, as `YYYY-MM`.

    Read from `series_requirements()` rather than restated: the supply is a
    declared ZERO-MARGIN one, so a member whose horizon deepens must turn this
    red instead of being absorbed by slack.
    """
    from core.b0_features import series_requirements

    months = int(series_requirements()["month_end_prices"])
    if months < 1:
        raise L3SpanError(
            "abort: month_end_prices requires %d months; a span cannot be derived "
            "from a non-positive depth" % months)
    d = _date(as_of, "as_of")
    total = d.year * 12 + (d.month - 1) - (months - 1)
    return "%04d-%02d" % (total // 12, total % 12 + 1)


def bonus_window(as_of: str, earliest_required_month_end_session: str
                 ) -> tuple[str, str]:
    """(day after the earliest required month-end price, `as_of`).

    The caller supplies the SESSION because only the price frame knows which
    session ends a month; this module fixes what is done with it. Passing a
    session that does not belong to the month `earliest_required_month_end_month`
    identifies is an abort, not a shorter window: it is how a window silently
    stops covering the reach it exists to cover.
    """
    end = str(as_of)
    session = str(earliest_required_month_end_session)
    _date(end, "as_of")
    d = _date(session, "earliest_required_month_end_session")
    required_month = earliest_required_month_end_month(end)
    if session[:7] != required_month:
        raise L3SpanError(
            "abort: the earliest required month-end session %s is not in %s, the "
            "oldest month month_end_prices reaches from as_of %s (§19.2)"
            % (session, required_month, end))
    start = (d + datetime.timedelta(days=1)).isoformat()
    if start > end:
        raise L3SpanError(
            "abort: bonus_window would be empty (%s .. %s)" % (start, end))
    return start, end


def spans(lineage_price_floor: str, as_of: str, execution_date: str,
          earliest_required_month_end_session: str,
          observed_price_coverage_floor: str) -> dict:
    """All four endpoints plus the §19.4 receipt binding, in one call.

    Both floors are returned together on purpose: a receipt that carries only the
    frozen one cannot be audited against the period's data, and one that carries
    only the observed one does not say what the lineage promised.
    """
    disposition = assert_floor_conforms(lineage_price_floor,
                                        observed_price_coverage_floor)
    return {
        "price_span": price_span(lineage_price_floor, execution_date),
        "bonus_window": bonus_window(as_of, earliest_required_month_end_session),
        "lineage_price_floor": str(lineage_price_floor),
        "observed_price_coverage_floor": str(observed_price_coverage_floor),
        "floor_disposition": disposition,
        "floor_rule": FLOOR_RULE,
        "ruling": RULING,
        "applies_to": APPLIES_TO,
    }
