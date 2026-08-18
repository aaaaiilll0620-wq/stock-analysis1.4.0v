"""O-F step 2 - can the registered status source account for missing prices?

Three audits, from weakest to strongest, all driven from data and none of them
consulting a fixed list of names:

  A  as-of snapshot at the SAME as_of the earlier O-F diagnostic used, so the
     counts are directly comparable. Runs through `core.b0_pit_observability`,
     i.e. the production classifier, not a local re-implementation.
  B  terminal gaps over the whole corpus: every security whose price series
     stops while the corpus continues.
  C  interior gaps: every maximal run of expected-but-missing sessions strictly
     inside a security's own first..last span. This is the case a holding
     actually meets mid-life and the earlier diagnostic never looked at.

O-E-1 is applied unchanged in all three: a status may explain a session only if
it was available STRICTLY BEFORE that session began.

The previously reported example names are read from the earlier run's JSON and
REPORTED against, never used as a pass list: the verdict is the derived count.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import bisect
import csv
import json
import os
import sys
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_market_state import (                    # noqa: E402
    SecurityStatusTable, SourceContract, StatusRecord, TradingCalendar,
)
from core.b0_pit_observability import (               # noqa: E402
    UNEXPLAINED_GAP, NON_TRADING_STATUSES, PitPriceObservation,
    _available_before, classify_price_gap,
)

DATA = os.path.join(REPO, "data", "b0")
PRESENCE = os.path.join(DATA, "price_presence.parquet")
# The superseded diagnostic, frozen here. It used to be read straight out of
# the adapter-validation JSON, but that file now DELEGATES its universe scan to
# this audit -- reading it back would have made the regression compare this run
# against itself.
PRIOR = os.path.join(HERE, "prior_of_diagnostic.json")
OUT = os.path.join(HERE, "status_coverage_audit.json")

AS_OF_REGRESSION = "2020-06-29"        # the earlier O-F diagnostic's as_of


def load_calendar():
    with open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8") as fh:
        sessions = sorted(r["session"] for r in csv.DictReader(fh))
    contract = SourceContract(
        name="b0_trading_calendar", kind="trading_calendar",
        importer_version="b0_market_state_importer@2",
        content_sha256="c" * 64, schema_sha256="s" * 64,
        date_min=sessions[0], date_max=sessions[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    return sessions, TradingCalendar(sessions, contract)


def load_status():
    with open(os.path.join(DATA, "security_status.csv"), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    contract = SourceContract(
        name="b0_security_status", kind="security_status",
        importer_version="b0_market_state_importer@2",
        content_sha256="c" * 64, schema_sha256="s" * 64,
        date_min=min(r["effective_from"] for r in rows),
        date_max=max(r["effective_from"] for r in rows),
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    table = SecurityStatusTable(
        [StatusRecord(**{k: r[k] for k in
                         ("stock_id", "status", "effective_from",
                          "available_from", "reason", "source")}) for r in rows],
        contract)
    spans = defaultdict(list)
    for r in rows:
        spans[r["stock_id"]].append(
            (r["effective_from"], r["available_from"], r["status"], r["reason"]))
    for v in spans.values():
        v.sort()
    return rows, table, spans


def explains(spans, sid, session):
    """The state in force at `session`, using only records available before it."""
    known = [x for x in spans.get(sid, ())
             if x[0] <= session and _available_before(x[1], session)]
    if not known:
        return None
    eff, avail, status, reason = known[-1]
    return (status, avail, reason) if status in NON_TRADING_STATUSES else None


def blocked_by_o_e_1(spans, sid, session):
    """A record that would have explained the session but for O-E-1."""
    for eff, avail, status, reason in spans.get(sid, ()):
        if status in NON_TRADING_STATUSES and eff <= session and not \
                _available_before(avail, session):
            return (status, avail, reason)
    return None


def main():
    sessions, calendar = load_calendar()
    status_rows, status, spans = load_status()
    pres = pd.read_parquet(PRESENCE)
    by_id = defaultdict(list)
    for sid, date in zip(pres["stock_id"].astype(str), pres["date"]):
        by_id[sid].append(date)
    corpus_max = max(s for v in by_id.values() for s in v[-1:])

    report = {"study": "O-F status coverage audit",
              "read_only": True, "performance_computed": False,
              "status_source": {
                  "records": len(status_rows),
                  "securities": len({r["stock_id"] for r in status_rows}),
                  "by_status": dict(Counter(r["status"] for r in status_rows))},
              "universe": {"securities": len(by_id), "corpus_max": corpus_max}}

    # --- audit A : as-of snapshot, production classifier ---------------------
    window = [s for s in sessions if s <= AS_OF_REGRESSION]
    causes = Counter()
    a_unexplained = {"no_status_record": [], "o_e_1_same_day": [], "other": []}
    for sid, dates in by_id.items():
        if dates[0] > AS_OF_REGRESSION:
            continue
        i = bisect.bisect_right(dates, AS_OF_REGRESSION)
        observed_through = dates[i - 1] if i else None
        rec = status.explaining_record(sid, AS_OF_REGRESSION, AS_OF_REGRESSION)
        obs = PitPriceObservation(
            as_of=AS_OF_REGRESSION, stock_id=sid,
            price_observed_through=observed_through,
            expected_sessions=tuple(window),
            known_status=rec.status if rec else "listed",
            status_available_from=rec.available_from if rec else None)
        v = classify_price_gap(obs)
        if v.classification != UNEXPLAINED_GAP:
            causes[v.classification] += 1
            continue
        causes[UNEXPLAINED_GAP] += 1
        first_missing = obs.missing_sessions[0] if obs.missing_sessions else None
        if "O-E-1" in v.reason:
            a_unexplained["o_e_1_same_day"].append(
                {"stock_id": sid, "first_missing": first_missing,
                 "blocked": blocked_by_o_e_1(spans, sid, first_missing)})
        elif spans.get(sid):
            a_unexplained["other"].append(
                {"stock_id": sid, "first_missing": first_missing,
                 "reason": v.reason[:120]})
        else:
            a_unexplained["no_status_record"].append(
                {"stock_id": sid, "first_missing": first_missing,
                 "sessions_stale": v.sessions_stale})
    report["audit_A_as_of_snapshot"] = {
        "as_of": AS_OF_REGRESSION,
        "securities_scanned": sum(causes.values()),
        "by_classification": dict(causes),
        "unexplained_total": len(a_unexplained["no_status_record"])
                             + len(a_unexplained["o_e_1_same_day"])
                             + len(a_unexplained["other"]),
        "unexplained_by_cause": {k: len(v) for k, v in a_unexplained.items()},
        "unexplained_detail": a_unexplained,
        "enforced": False,
    }

    # --- audit B : terminal gaps over the whole corpus -----------------------
    b_unexplained, b_causes = [], Counter()
    for sid, dates in by_id.items():
        last = dates[-1]
        if last >= corpus_max:
            b_causes["still_trading_at_corpus_end"] += 1
            continue
        k = bisect.bisect_right(sessions, last)
        if k >= len(sessions):
            b_causes["no_session_after"] += 1
            continue
        nxt = sessions[k]
        if explains(spans, sid, nxt):
            b_causes["explained"] += 1
            continue
        blocked = blocked_by_o_e_1(spans, sid, nxt)
        b_causes["o_e_1_same_day" if blocked else
                 ("no_status_record" if not spans.get(sid) else "other")] += 1
        b_unexplained.append({"stock_id": sid, "last_price": last,
                              "first_missing": nxt,
                              "has_any_status_record": bool(spans.get(sid)),
                              "blocked_by_o_e_1": blocked})
    report["audit_B_terminal_gaps"] = {
        "securities": len(by_id), "by_cause": dict(b_causes),
        "unexplained": len(b_unexplained),
        "detail": sorted(b_unexplained, key=lambda r: r["first_missing"]),
    }

    # --- audit C : interior gaps ---------------------------------------------
    c_runs, c_causes = [], Counter()
    for sid, dates in by_id.items():
        have = set(dates)
        lo = bisect.bisect_left(sessions, dates[0])
        hi = bisect.bisect_right(sessions, dates[-1])
        run_start = None
        for s in sessions[lo:hi]:
            if s in have:
                if run_start is not None:
                    c_causes["explained" if explains(spans, sid, run_start)
                             else "unexplained"] += 1
                    if not explains(spans, sid, run_start):
                        c_runs.append({"stock_id": sid, "first_missing": run_start,
                                       "length": run_len,
                                       "blocked_by_o_e_1":
                                           blocked_by_o_e_1(spans, sid, run_start),
                                       "has_any_status_record": bool(spans.get(sid))})
                    run_start = None
            else:
                if run_start is None:
                    run_start, run_len = s, 0
                run_len += 1
    by_len = Counter(r["length"] for r in c_runs)
    report["audit_C_interior_gaps"] = {
        "runs_total": sum(c_causes.values()),
        "by_cause": dict(c_causes),
        "unexplained_runs": len(c_runs),
        "unexplained_securities": len({r["stock_id"] for r in c_runs}),
        "unexplained_run_length_histogram": dict(sorted(by_len.items())[:15]),
        "note": ("a run is NOT necessarily a mark gap. A security that leaves the "
                 "exchange and is relisted years later shows one enormous run "
                 "here, and during it no session was expected of it at all. P-6 "
                 "in the event-table audit splits the two."),
        "runs": sorted(c_runs, key=lambda r: -r["length"]),
    }

    # --- regression against the earlier O-F examples -------------------------
    ex = json.load(open(PRIOR, encoding="utf-8"))
    prior_names = sorted(ex["example_names_recorded"])
    now_unexplained = {d["stock_id"] for group in a_unexplained.values()
                       for d in group}
    report["regression_vs_prior_of_run"] = {
        "prior_by_cause": ex["by_cause"],
        "prior_example_names_recorded": prior_names,
        "prior_examples_still_unexplained": sorted(
            n for n in prior_names if n in now_unexplained),
        "prior_examples_now_explained": sorted(
            n for n in prior_names if n not in now_unexplained),
        "prior_measurement_defect": ex["measurement_defect"],
        "note": "the earlier run stored only 8 examples per cause; these names "
                "are REPORTED against, never used as a pass list. The verdict "
                "is the derived count in audit_A.",
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    a = report["audit_A_as_of_snapshot"]
    print(f"status source : {report['status_source']}")
    print(f"\naudit A @ {a['as_of']}: scanned {a['securities_scanned']}")
    print(f"  by classification : {a['by_classification']}")
    print(f"  UNEXPLAINED       : {a['unexplained_total']} "
          f"{a['unexplained_by_cause']}")
    print(f"  prior run         : {ex['by_cause']} (superseded proxy)")
    b = report["audit_B_terminal_gaps"]
    print(f"\naudit B terminal: {b['by_cause']}  UNEXPLAINED={b['unexplained']}")
    c = report["audit_C_interior_gaps"]
    print(f"\naudit C interior: runs={c['runs_total']} {c['by_cause']}")
    print(f"  unexplained runs={c['unexplained_runs']} over "
          f"{c['unexplained_securities']} securities")
    print(f"  length histogram : {c['unexplained_run_length_histogram']}")
    r = report["regression_vs_prior_of_run"]
    print(f"\nprior examples now explained    : {r['prior_examples_now_explained']}")
    print(f"prior examples still unexplained: {r['prior_examples_still_unexplained']}")
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
