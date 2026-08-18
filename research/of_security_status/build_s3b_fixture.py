"""S-3b · build the real-data, non-performance enforcement fixture.

O-F closes with an incomplete source, so S-3b cannot be "no unexplained gaps
anywhere". What it can be, and what the ruling makes it, is ENFORCEMENT: does the
route actually abort on the case that matters, and actually not abort on the case
that does not?

Four properties, each carried by a REAL security drawn from the O-F audit:

  pit_safe_status_explains              a gap a filed, PIT-available status
                                        accounts for -> EXPLAINED, run proceeds
  held_unexplained_gap_aborts           the same shape of gap with no PIT-safe
                                        status, HELD -> abort
  unheld_unexplained_gap_does_not_abort the identical observation, NOT held ->
                                        no abort (O-F: the universe is allowed
                                        to be incomplete)
  all_routes_invoke_the_guard           structural, checked by the verifier

Names are selected by the audit, not typed in: the builder takes whatever the
audit put in each bucket and records which one it used, so the fixture cannot
quietly become a curated pass list.

No return, IC, Sharpe, ranking, selection or NAV quantity is computed, and no
price LEVEL appears in the fixture -- only session identity and status.
"""

import bisect
import csv
import json
import os
import sys
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

DATA = os.path.join(REPO, "data", "b0")
AUDIT = os.path.join(HERE, "status_coverage_audit.json")
OUT = os.path.join(DATA, "s3b_guard_fixture.csv")
OUT_JSON = os.path.join(HERE, "s3b_fixture_provenance.json")

FIELDS = ("property", "stock_id", "as_of", "price_observed_through",
          "expected_sessions", "known_status", "status_available_from",
          "held", "expected_outcome", "selected_by")


def main():
    audit = json.load(open(AUDIT, encoding="utf-8"))
    as_of = audit["audit_A_as_of_snapshot"]["as_of"]

    with open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8") as fh:
        sessions = sorted(r["session"] for r in csv.DictReader(fh))
    with open(os.path.join(DATA, "security_status.csv"), encoding="utf-8") as fh:
        status_rows = list(csv.DictReader(fh))
    spans = defaultdict(list)
    for r in status_rows:
        spans[r["stock_id"]].append(r)

    pres = pd.read_parquet(os.path.join(DATA, "price_presence.parquet"))
    dates = defaultdict(list)
    for sid, d in zip(pres["stock_id"].astype(str), pres["date"]):
        dates[sid].append(d)

    def observed_through(sid):
        d = dates.get(sid, ())
        i = bisect.bisect_right(d, as_of)
        return d[i - 1] if i else None

    def window(sid):
        """Sessions from the last observed price through as_of, inclusive.

        This is all `classify_price_gap` needs to reproduce `missing_sessions`,
        and it keeps the fixture small enough to read by eye.
        """
        last = observed_through(sid)
        i = bisect.bisect_left(sessions, last)
        j = bisect.bisect_right(sessions, as_of)
        return sessions[i:j]

    rows = []

    # --- 1. a gap a PIT-available status explains ----------------------------
    explained = _explained_case(dates, spans, sessions, as_of)
    if explained is None:
        raise SystemExit("no explained case found in real data; S-3b cannot be "
                         "proved on a fixture that has no positive control")
    sid, rec = explained
    rows.append({
        "property": "pit_safe_status_explains", "stock_id": sid, "as_of": as_of,
        "price_observed_through": observed_through(sid),
        "expected_sessions": ";".join(window(sid)),
        "known_status": rec["status"],
        "status_available_from": rec["available_from"],
        "held": "1", "expected_outcome": "EXPLAINED_SUSPENSION",
        "selected_by": "first security whose gap a PIT-available status explains",
    })

    # --- 2/3. the same shape of gap with no PIT-safe status ------------------
    unexplained = audit["audit_A_as_of_snapshot"]["unexplained_detail"]
    pick = (unexplained["no_status_record"] or unexplained["o_e_1_same_day"]
            or unexplained["other"])
    if not pick:
        raise SystemExit("no unexplained case in real data; the abort side of "
                         "S-3b would be untested")
    sid = pick[0]["stock_id"]
    base = {
        "stock_id": sid, "as_of": as_of,
        "price_observed_through": observed_through(sid),
        "expected_sessions": ";".join(window(sid)),
        "known_status": "listed", "status_available_from": "",
        "selected_by": "first entry in the audit's unexplained bucket",
    }
    rows.append({**base, "property": "held_unexplained_gap_aborts",
                 "held": "1", "expected_outcome": "ABORT"})
    rows.append({**base, "property": "unheld_unexplained_gap_does_not_abort",
                 "held": "0", "expected_outcome": "NO_ABORT"})

    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        w.writerows(rows)

    from core.b0_provenance import file_sha256
    prov = {"study": "S-3b enforcement fixture", "read_only": True,
            "performance_computed": False, "selection_computed": False,
            "as_of": as_of, "cases": len(rows),
            "properties": sorted({r["property"] for r in rows}),
            "fixture": os.path.relpath(OUT, REPO).replace("\\", "/"),
            "fixture_sha256": file_sha256(OUT),
            "derived_from": {
                "status": "data/b0/security_status.csv",
                "calendar": "data/b0/trading_calendar.csv",
                "presence": "data/b0/price_presence.parquet",
                "audit": "research/of_security_status/status_coverage_audit.json"},
            "rows": rows}
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=1)

    for r in rows:
        print(f"{r['property']:<38} {r['stock_id']:<6} "
              f"observed_through={r['price_observed_through']} "
              f"status={r['known_status']} -> {r['expected_outcome']}")
    print("fixture sha256:", prov["fixture_sha256"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


def _explained_case(dates, spans, sessions, as_of):
    """The first security whose gap at `as_of` a PIT-available status explains."""
    from core.b0_market_state import NON_TRADING_STATUSES
    from core.b0_pit_observability import _available_before

    for sid in sorted(dates):
        d = dates[sid]
        i = bisect.bisect_right(d, as_of)
        if not i:
            continue
        last = d[i - 1]
        if last >= as_of:
            continue
        k = bisect.bisect_right(sessions, last)
        if k >= len(sessions) or sessions[k] > as_of:
            continue
        first_missing = sessions[k]
        known = [r for r in spans.get(sid, ())
                 if r["effective_from"] <= first_missing
                 and _available_before(r["available_from"], first_missing)
                 and r["available_from"] <= as_of]
        if not known:
            continue
        rec = sorted(known, key=lambda r: (r["effective_from"],
                                           r["available_from"]))[-1]
        if rec["status"] in NON_TRADING_STATUSES:
            return sid, rec
    return None


if __name__ == "__main__":
    sys.exit(main())
