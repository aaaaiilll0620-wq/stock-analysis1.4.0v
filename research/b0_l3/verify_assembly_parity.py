# -*- coding: utf-8 -*-
"""W6b-2 (assembly) · the assembled state must be the state L2 sealed.

The readers were checked field by field against nine sealed panels. The assembly
is checked against ONE number: `market_state_sha256` in
`data/b0/market_state_manifest.json`. That hash covers the whole market-side
payload — marks, adv20, sigma20d, execution prices, untradable, PIT status
dates, listing spells, every SecurityPitInputs series, and the corporate-action
events — so reproducing it is a single statement that the entire assembly agrees.

WHY 2026-03 IS THE ONLY PERIOD THAT CAN BE CHECKED
---------------------------------------------------
Not a convenience. The valuation family's locator is `board_date_payload_key`:
one harvested payload per board per SESSION, and a run's leaf declares the
session its decision stands on. A run bound to as_of 2026-03-30 therefore holds
the valuation for that session and no other, so it can assemble that period and
only that period.

2026-03-30 is `resolve_as_of(2026-03-31)`, and 2026-03-31 is `window_end` — the
141st and last frozen decision. The one period an L3 run's declared sources can
build is exactly the one L2 already sealed, which is the only reason this
comparison exists at all.

L2'S OWN DEPTH IS PASSED IN AS THE LINEAGE FLOOR, AND THAT IS THE POINT
-----------------------------------------------------------------------
Since §19 / C-68 the endpoints are derived by `core.b0_l3_price_span`; the only
input left is the lineage floor. This harness passes **L2's panel-span floor**,
because comparing against L2's sealed state means reading L2's depth — a floor
chosen for parity, never the value an L3 lineage would capture. Note what that
exercises: the corpus reaches deeper than 2013-01-01, so §19.3's `earlier`
disposition fires and the run stays CLIPPED to the declared floor instead of
quietly deepening. The bonus window is now derived (day after the earliest
required month-end price .. as_of) rather than L2's `window_end`-anchored one;
those differ only by boundaries in `(as_of, window_end]`, and for 2026-03 the
ledger has none of an eligible kind.

WHEN THE HASH DIFFERS
---------------------
A hash mismatch says "something moved" and nothing else, which is useless for
fixing it. So `explain_divergence` re-reads L2's own row artefact and reports
which COLUMNS differ and for how many securities — the same shape of answer the
reader parity gives. `--measure` reports instead of raising, for establishing
what a known gap costs; nothing calls it in place of the check.

READ-ONLY with respect to `data/b0/`.

    python research/b0_l3/verify_assembly_parity.py <run_dir> <run_id> \
        [decision_date] [--measure]
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from l3_assemble import assemble                                 # noqa: E402

L2_MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")
L2_ROWS_DIR = os.path.join(REPO, "data", "b0", "market_state")

# L2's panel-span floor: `build_price_panel.panel_span()` starts at January of
# the year of window_start minus lookback_L_months. It is passed as the LINEAGE
# FLOOR so that this comparison reads L2's depth. It is a parity input, not a
# candidate `lineage_price_floor` for any real L3 lineage (§19.7).
L2_PANEL_FLOOR = "2013-01-01"

# Kept for reference and for the divergence report's prose. `assemble` no longer
# accepts either: the upper price endpoint is the §6.5 execution session and the
# bonus window is derived from as_of (§19.2).
L2_PRICE_SPAN = ("2013-01-01", "2026-04-01")
L2_BONUS_WINDOW = ("2013-06-29", "2026-03-31")

DEFAULT_DECISION_DATE = "2026-03-31"

LIST_COLUMNS = ("month_end_prices", "monthly_revenue", "net_income_by_quarter",
                "revenue_by_quarter", "gross_profit_by_quarter",
                "eps_by_quarter", "corporate_action_events")
SCALAR_COLUMNS = ("mark", "adv20", "sigma20d", "execution_open", "per_tse",
                  "pbr_tse", "period_end_equity", "total_liabilities",
                  "total_assets", "current_assets", "current_liabilities")
STRING_COLUMNS = ("spell_start", "known_status", "pit_industry")
# Nullable on purpose. A LISTED security has no status dates, and L2's row
# artefact stores that absence as the four-character string "None" because its
# read-back applies `str()` to every text column. That is a property of the
# parquet round-trip, not of the state L2 hashed — `market_state_payload`
# carries these only for non-listed rows — so comparing the round-trip against
# an in-memory None would report 1,687 differences that do not exist.
NULLABLE_STRING_COLUMNS = ("status_available_from", "status_effective_from")


class AssemblyParityError(SystemExit):
    """Fail-loud: the assembled state is not the state L2 sealed."""


def _f(v):
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def l2_rows(decision_month: str) -> list:
    """The exact inverse of what L2's builder wrote.

    Parquet round-trips a Python list of floats as a numpy array and `None` as
    NaN, so a naive read-back compares differently from what was hashed. This is
    the one place that knows the round-trip.
    """
    import pandas as pd

    path = os.path.join(L2_ROWS_DIR, "%s.parquet" % decision_month)
    if not os.path.isfile(path):
        raise AssemblyParityError(
            "abort: L2 sealed no market state for %s, so there is nothing to "
            "check the assembly against." % decision_month)
    rows = pd.read_parquet(path).to_dict("records")
    for r in rows:
        r["stock_id"] = str(r["stock_id"])
        for k in LIST_COLUMNS:
            v = r[k]
            if v is None:
                r[k] = []
            elif k == "corporate_action_events":
                r[k] = [[str(x) for x in list(e)] for e in list(v)]
            else:
                r[k] = [_f(x) for x in list(v)]
        for k in SCALAR_COLUMNS:
            r[k] = _f(r[k])
        for k in STRING_COLUMNS:
            r[k] = str(r[k])
        for k in NULLABLE_STRING_COLUMNS:
            v = r[k]
            r[k] = None if v is None or str(v) in ("None", "nan", "") else str(v)
    return rows


def l2_period(decision_month: str) -> dict:
    with open(L2_MANIFEST, encoding="utf-8") as fh:
        for entry in json.load(fh):
            if entry["decision_month"] == decision_month:
                return entry
    raise AssemblyParityError(
        "abort: %s is not one of L2's sealed decision months." % decision_month)


def explain_divergence(got_rows, want_rows) -> dict:
    """Which columns moved, and for how many securities."""
    a = {r["stock_id"]: r for r in want_rows}
    b = {r["stock_id"]: r for r in got_rows}
    report = {
        "securities_l2": len(a), "securities_l3": len(b),
        "only_in_l2": sorted(set(a) - set(b))[:10],
        "only_in_l3": sorted(set(b) - set(a))[:10],
        "columns": {},
    }
    shared = sorted(set(a) & set(b))
    for col in (SCALAR_COLUMNS + STRING_COLUMNS
                + NULLABLE_STRING_COLUMNS + LIST_COLUMNS):
        diff = [s for s in shared if a[s][col] != b[s][col]]
        if diff:
            s = diff[0]
            report["columns"][col] = {
                "securities": len(diff),
                "example": {"stock_id": s, "l2": a[s][col], "l3": b[s][col]},
            }
    return report


def verify_market_state(run_dir: str, run_id: str,
                        decision_date: str = DEFAULT_DECISION_DATE,
                        lineage_price_floor: str = L2_PANEL_FLOOR) -> dict:
    """Rebuild the period from declared sources; require L2's sealed hash."""
    got = assemble(run_dir, run_id, decision_date,
                   lineage_price_floor=lineage_price_floor)
    month = got["period"]["decision_month"]
    want = l2_period(month)

    for field in ("decision_date", "as_of", "execution_date"):
        if got["period"][field] != want[field]:
            raise AssemblyParityError(
                "abort: %s disagrees — L2 %s, L3 %s. The period derivation is "
                "wrong before any value is compared."
                % (field, want[field], got["period"][field]))

    if got["market_state_sha256"] != want["market_state_sha256"]:
        detail = explain_divergence(got["rows"], l2_rows(month))
        raise AssemblyParityError(
            "abort: the assembled market state is not the one L2 sealed.\n"
            "  L2 %s\n  L3 %s\n%s"
            % (want["market_state_sha256"], got["market_state_sha256"],
               json.dumps(detail, ensure_ascii=False, indent=1)[:4000]))

    return {
        "decision_month": month,
        "as_of": got["period"]["as_of"],
        "execution_date": got["period"]["execution_date"],
        "securities": got["securities"],
        "market_state_sha256": got["market_state_sha256"],
        "marks": len(got["payload"]["marks"]),
        "adv20": len(got["payload"]["adv20"]),
        "sigma20d": len(got["payload"]["sigma20d"]),
        "execution_prices": len(got["payload"]["execution_prices"]),
        "untradable": len(got["payload"]["untradable"]),
        "bonus_window": got["bonus_window"],
        "price_span": got["price_span"],
        "lineage_price_floor": got["lineage_price_floor"],
        "observed_price_coverage_floor": got["observed_price_coverage_floor"],
        "floor_disposition": got["floor_disposition"],
        "price_legs": got["price_legs"],
        "price_coverage_floor": got["price_coverage_floor"],
        "spell_starts_at_price_coverage_floor":
            got["spell_starts_at_price_coverage_floor"],
    }


def measure_divergence(run_dir: str, run_id: str,
                       decision_date: str = DEFAULT_DECISION_DATE,
                       lineage_price_floor: str = L2_PANEL_FLOOR) -> dict:
    """Report the difference instead of raising on it.

    For establishing WHAT a known source gap costs, rather than for accepting
    it. Nothing calls this in place of `verify_market_state`.
    """
    got = assemble(run_dir, run_id, decision_date,
                   lineage_price_floor=lineage_price_floor)
    month = got["period"]["decision_month"]
    want = l2_period(month)
    same = got["market_state_sha256"] == want["market_state_sha256"]
    out = {
        "decision_month": month,
        "hash_matches": same,
        "l2_sha256": want["market_state_sha256"],
        "l3_sha256": got["market_state_sha256"],
        "securities_l2": want["securities"],
        "securities_l3": got["securities"],
        "price_coverage_floor": got["price_coverage_floor"],
        "spell_starts_at_price_coverage_floor":
            got["spell_starts_at_price_coverage_floor"],
    }
    if not same:
        out["divergence"] = explain_divergence(got["rows"], l2_rows(month))
    return out


def main(argv) -> int:
    if len(argv) < 3:
        print("usage: verify_assembly_parity.py <run_dir> <run_id> "
              "[decision_date] [--measure]")
        return 2
    run_dir, run_id = argv[1], argv[2]
    rest = [a for a in argv[3:] if not a.startswith("--")]
    decision_date = rest[0] if rest else DEFAULT_DECISION_DATE
    fn = measure_divergence if "--measure" in argv else verify_market_state
    print(json.dumps(fn(run_dir, run_id, decision_date), ensure_ascii=False,
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
