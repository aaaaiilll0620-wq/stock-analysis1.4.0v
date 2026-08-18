"""D-1 - rebuild the price-universe audit, on either corpus.

Composition for `new`, stated explicitly because it is the one thing a reader
must not have to infer:

    years <= 2018   existing yearly export (never the defect; 2012-2017 showed
                    ordinary churn against the independent reference)
    years >= 2019   the 20260817 re-export, wholesale

That is a vintage boundary, not a patch. Nothing here selects securities: the
2019+ era is replaced in full and re-verified from scratch, and no list derived
from the old corpus is consulted at any point.

`old` runs the same code over the contaminated corpus, so the negative control
is GENERATED rather than asserted -- the two verdicts come from one code path.

Produces, all from data:
  * annual universe churn vs the independent security master
  * terminal-date cluster regression
  * security-level completeness, where an early termination must be explained by
    the reference's delisting date or by the registered PIT-safe status source
  * known-case evidence (driven by the master's delisting dates, not a fixed list)

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import bisect
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from audit_universe_vs_master import (            # noqa: E402
    _covered_by_status, _load_status_spans, load_master,
)

OLD_CACHE = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
NEW_COVERAGE = os.path.join(REPO, "data", "b0", "price_2019plus_new.parquet")

YEARS = [str(y) for y in range(2012, 2027)]
VINTAGE_BOUNDARY = "2019"
NON_TRADING = ("suspended", "delisted")


def coverage(which):
    """stock_id -> (years set, first, last)."""
    years = defaultdict(set)
    first, last = {}, {}
    cutoff = f"{VINTAGE_BOUNDARY}-01-01" if which == "new" else None

    for f in sorted(glob.glob(os.path.join(OLD_CACHE, "*.parquet"))):
        df = pd.read_parquet(f, columns=["stock_id", "date"])
        if df.empty:
            continue
        sid = str(df["stock_id"].iloc[0])
        d = df["date"].astype(str)
        keep = d[d < cutoff] if cutoff else d
        if keep.empty:
            continue
        years[sid] |= {x[:4] for x in keep}
        first[sid] = keep.min()
        last[sid] = keep.max()

    if which == "new":
        new = pd.read_parquet(NEW_COVERAGE)
        for r in new.itertuples(index=False):
            sid = str(r.stock_id)
            years[sid] |= set(str(r.years).split(","))
            if sid not in first or r.first < first[sid]:
                first[sid] = r.first
            last[sid] = r.last if sid not in last or r.last > last[sid] else last[sid]
    return years, first, last


def load_calendar():
    path = os.path.join(REPO, "data", "b0", "trading_calendar.csv")
    with open(path, encoding="utf-8") as fh:
        return sorted(r["session"] for r in csv.DictReader(fh))


def next_session(calendar, after):
    i = bisect.bisect_right(calendar, after)
    return calendar[i] if i < len(calendar) else None


def explained(sid, term_date, corpus_max, by_id, status, calendar):
    """Is a terminated series accounted for by something already known?

    The test is applied at the FIRST MISSING SESSION, exactly as O-B applies it:
    the security stopped being priced after `term_date`, so the question is
    whether anything accounts for the very next session it should have traded.

    A delisting recorded FOUR YEARS LATER does not account for it -- that is the
    contradiction, not the explanation. (An earlier version of this predicate had
    the comparison the wrong way round and reported the contaminated corpus as
    having zero unexplained terminations, which the negative control caught.)
    """
    if term_date >= corpus_max:
        return True
    nxt = next_session(calendar, term_date)
    if nxt is None:
        return True                      # nothing after it on the calendar
    m = by_id.get(sid)
    if m and m["delisted_on"] and m["delisted_on"] <= nxt:
        return True                      # it had already left the exchange
    return any(st in NON_TRADING and eff <= nxt
               for eff, st in status.get(sid, ()))


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "new"
    if which not in ("new", "old"):
        print("usage: rebuild_audit_new_source.py [new|old]")
        return 2

    out_dir = (os.path.join(REPO, "data", "b0") if which == "new"
               else os.path.join(REPO, "tests", "fixtures", "d1_contaminated"))
    os.makedirs(out_dir, exist_ok=True)
    audit_csv = os.path.join(out_dir, "price_universe_audit.csv")
    cluster_csv = os.path.join(out_dir, "price_universe_clusters.csv")
    churn_csv = os.path.join(out_dir, "price_universe_churn.csv")
    out_json = os.path.join(HERE, f"audit_{which}_source.json")

    master = load_master()
    equity = [m for m in master if m["exchange_listed_from"]]
    by_id = {m["stock_id"]: m for m in equity}
    status = _load_status_spans()
    calendar = load_calendar()

    years, first, last = coverage(which)
    corpus_max = max(last.values())
    print(f"[{which}] {len(years):,} securities, max date {corpus_max}")
    if which == "new":
        print("  <= 2018 existing yearly export")
        print("  >= 2019 the 20260817 re-export (wholesale)")
    else:
        print("  entire range from the contaminated corpus")

    # --- annual churn --------------------------------------------------------
    exits_observed = {}
    for a, b in zip(YEARS, YEARS[1:]):
        in_a = {s for s, ys in years.items() if a in ys}
        in_b = {s for s, ys in years.items() if b in ys}
        exits_observed[a] = len(in_a - in_b)

    report = {}
    print("\n  year  expected observed missing   (%)  unexpl  exits obs/exp")
    for y in YEARS:
        y0, y1 = f"{y}-01-01", f"{y}-12-31"
        expected = {m["stock_id"] for m in equity
                    if m["exchange_listed_from"] <= y1
                    and (m["delisted_on"] is None or m["delisted_on"] >= y0)}
        observed = {s for s, ys in years.items() if y in ys}
        missing = expected - observed
        later = {s for s in missing
                 if by_id[s]["delisted_on"] is None or by_id[s]["delisted_on"] > y1}
        unexplained = {s for s in later
                       if not _covered_by_status(status.get(s, ()), y0, y1)}
        report[y] = {
            "year": y,
            "expected_from_reference": len(expected),
            "observed_in_corpus": len(observed),
            "missing": len(missing),
            "missing_pct": round(100.0 * len(missing) / len(expected), 2) if expected else None,
            "missing_though_listed_after_year_end": len(later),
            "unexplained_missing_though_listed": len(unexplained),
            "exits_observed": exits_observed.get(y),
            "exits_expected_from_reference": sum(
                1 for m in equity if m["delisted_on"] and m["delisted_on"][:4] == y),
            "unexplained_ids": sorted(unexplained)[:20],
        }
        r = report[y]
        print("  %s   %5d    %5d   %4d %6.2f    %4d    %s/%d"
              % (y, r["expected_from_reference"], r["observed_in_corpus"],
                 r["missing"], r["missing_pct"] or 0.0,
                 r["unexplained_missing_though_listed"],
                 r["exits_observed"], r["exits_expected_from_reference"]))

    # --- security-level completeness ----------------------------------------
    unexplained_terminations = []
    for sid in last:
        if explained(sid, last[sid], corpus_max, by_id, status, calendar):
            continue
        unexplained_terminations.append(
            {"stock_id": sid, "last_price": last[sid],
             "reference_delisted": (by_id.get(sid) or {}).get("delisted_on")})
    unexplained_ids = {e["stock_id"] for e in unexplained_terminations}
    print(f"\nsecurity-level: {len(unexplained_terminations)} unexplained early "
          f"terminations")
    for e in unexplained_terminations[:10]:
        print("   ", e)

    # --- terminal-date clusters ---------------------------------------------
    term = Counter(d for s, d in last.items() if d < corpus_max)
    clusters = {}
    for d, n in term.items():
        if n < 2:
            continue
        clusters[d] = {
            "corpus_terminations": n,
            "unexplained_terminations_on_date": sum(
                1 for s, x in last.items() if x == d and s in unexplained_ids),
            "reference_delistings_on_date": sum(
                1 for m in equity if m["delisted_on"] == d),
        }
    top = sorted(clusters.items(),
                 key=lambda kv: -kv[1]["corpus_terminations"])[:12]
    print("\nterminal-date clusters (>=2), largest first:")
    for d, v in top:
        print("   %s  n=%3d  unexplained=%3d  ref delistings that day=%d"
              % (d, v["corpus_terminations"],
                 v["unexplained_terminations_on_date"],
                 v["reference_delistings_on_date"]))
    print("   2018-12-28:", clusters.get("2018-12-28", "ABSENT"))

    # --- known cases ---------------------------------------------------------
    known = []
    for sid, m in sorted(by_id.items()):
        d = m["delisted_on"]
        if not d or d < "2019-01-01" or sid not in last:
            continue
        known.append({"stock_id": sid, "reference_delisted": d,
                      "last_price": last[sid],
                      "explained": explained(sid, last[sid], corpus_max,
                                             by_id, status, calendar)})
    ok = sum(1 for k in known if k["explained"])
    print(f"\nknown cases (reference delisting >= 2019): {len(known)}; "
          f"explained through to their exit: {ok}")
    for k in known[:10]:
        print("   ", k)

    # --- emit verifier inputs ------------------------------------------------
    cols = ["year", "expected_from_reference", "observed_in_corpus", "missing",
            "missing_though_listed_after_year_end",
            "unexplained_missing_though_listed",
            "exits_observed", "exits_expected_from_reference"]
    with open(audit_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for y in YEARS:
            w.writerow({c: report[y].get(c) for c in cols})

    with open(cluster_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "date", "corpus_terminations", "unexplained_terminations_on_date",
            "reference_delistings_on_date"])
        w.writeheader()
        for d, v in sorted(clusters.items()):
            w.writerow({"date": d, **v})

    with open(churn_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "year", "securities", "dropped_next_year", "added_next_year",
            "dropped_but_traded_to_year_end", "year_end_session"])
        w.writeheader()
        for a, b in zip(YEARS, YEARS[1:]):
            in_a = {s for s, ys in years.items() if a in ys}
            in_b = {s for s, ys in years.items() if b in ys}
            dropped = in_a - in_b
            year_end = max((last[s] for s in in_a if last[s][:4] == a), default="")
            w.writerow({
                "year": a, "securities": len(in_a),
                "dropped_next_year": len(dropped),
                "added_next_year": len(in_b - in_a),
                "dropped_but_traded_to_year_end": sum(
                    1 for s in dropped if last.get(s, "") == year_end),
                "year_end_session": year_end})

    payload = {
        "study": f"D-1 audit ({which} source)",
        "read_only": True, "performance_computed": False,
        "which": which,
        "composition": ({"<=2018": "existing yearly export",
                         ">=2019": "20260817 re-export (wholesale)"}
                        if which == "new" else {"all": "contaminated corpus"}),
        "securities": len(years), "corpus_max": corpus_max,
        "per_year": report,
        "terminal_date_clusters": clusters,
        "unexplained_early_terminations": unexplained_terminations,
        "known_cases": known,
    }
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    for p in (out_json, audit_csv, cluster_csv, churn_csv):
        print("wrote", os.path.relpath(p, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
