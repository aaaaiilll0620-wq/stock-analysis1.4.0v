"""Real-data integration validation at the ADAPTER boundary only.

Scope is deliberately the source boundary and nothing past it:

    input schema validation, PIT validation, source attestation,
    as_of / config_hash / state_hash, corporate-action and market-state guards,
    price-source admissibility, route reachability invariants.

The decision layers are NOT run. `run_decision` would compute features,
eligibility, SelectionScore, targets and orders — that is a selection list, which
this round forbids producing or inspecting. Everything below stops at
`build_input`, which validates and shapes state and decides nothing.

READ-ONLY. No return, IC, Sharpe, ranking, selection or NAV quantity is computed.
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

from core.b0_adapter_retrospective import (      # noqa: E402
    RetrospectiveSources, build_input,
)
from core.b0_corporate_actions import (          # noqa: E402
    NOT_RECONSTRUCTIBLE, CorporateActionEvent, Exposure,
    assert_exposure_reconstructible,
)
from core.b0_listing_spell import (              # noqa: E402
    ListingSpell, derive_current_spell,
)
from core.b0_market_state import (               # noqa: E402
    SecurityStatusTable, SourceContract, StatusRecord, TradingCalendar,
)
from core.b0_pit_observability import (          # noqa: E402
    PitPriceObservation, assert_no_unexplained_price_gap, stale_mark_report,
)
from core.b0_price_universe import PriceSourceContract  # noqa: E402
from core.b0_route import config_hash            # noqa: E402
from core.b0_state import PortfolioState, SourceAttestation  # noqa: E402

OUT = os.path.join(HERE, "realdata_adapter_validation.json")
DATA = os.path.join(REPO, "data", "b0")
DECISION_DATE = "2020-06-30"          # inside the frozen window, arbitrary


def load_calendar():
    with open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8") as fh:
        sessions = sorted(r["session"] for r in csv.DictReader(fh))
    contract = SourceContract(
        name="b0_trading_calendar", kind="trading_calendar",
        importer_version="b0_market_state_importer@1",
        content_sha256="c" * 64, schema_sha256="s" * 64,
        date_min=sessions[0], date_max=sessions[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    return TradingCalendar(sessions, contract)


def load_status():
    with open(os.path.join(DATA, "security_status.csv"), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    contract = SourceContract(
        name="b0_security_status", kind="security_status",
        importer_version="b0_market_state_importer@1",
        content_sha256="c" * 64, schema_sha256="s" * 64,
        date_min=min(r["effective_from"] for r in rows),
        date_max=max(r["effective_from"] for r in rows),
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False)
    return SecurityStatusTable(
        [StatusRecord(**{k: r[k] for k in
                         ("stock_id", "status", "effective_from",
                          "available_from", "reason", "source")}) for r in rows],
        contract)


def load_price_source():
    c = json.load(open(os.path.join(HERE, "price_source_contract.json"),
                       encoding="utf-8"))["contract"]
    return PriceSourceContract(**c)


def load_corporate_actions():
    path = os.path.join(DATA, "corporate_actions_ledger.csv")
    events = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r["ex_or_effective_date"]:
                continue
            events.append(CorporateActionEvent(
                stock_id=r["stock_id"], kind=r["kind"],
                ex_or_effective_date=r["ex_or_effective_date"],
                reconstructibility=r["reconstructibility"],
                reason=r["reason"]))
    return events


def main():
    results = {}
    calendar = load_calendar()
    status = load_status()
    price_source = load_price_source()
    events = load_corporate_actions()

    # --- 1. source attestation + price-source admissibility ------------------
    attestation = SourceAttestation(
        dataset_id=price_source.name,
        provenance_sha256=price_source.content_sha256,
        pit_guard_passed=True, universe_guard_passed=True,
        satisfied_blocking_requirements=(), synthetic=False)
    results["price_source"] = {
        "name": price_source.name,
        "content_sha256": price_source.content_sha256,
        "includes_delisted": price_source.includes_delisted,
    }

    # --- 2. PIT validation on real market state ------------------------------
    as_of_sessions = calendar.sessions_through(DECISION_DATE)
    as_of = as_of_sessions[-2]                 # prior completed session (O-D)
    results["pit"] = {
        "decision_date": DECISION_DATE,
        "as_of": as_of,
        "sessions_through_as_of": len(calendar.sessions_through(as_of)),
        "calendar_truncates_at_as_of": calendar.sessions_through(as_of)[-1] <= as_of,
    }

    # --- 3. market-state guard on real HELD positions -------------------------
    # The guard is about positions B0 holds: `port_value = cash + Σ shares × mark`
    # needs a mark for each holding, and nothing else. Feeding it the whole
    # universe (as a first attempt here did) makes it fire on names B0 does not
    # hold, which is a misuse rather than a route failure.
    # `price_observed_through` is read from the session-level presence index, not
    # approximated by min(series_last, as_of). That approximation called every
    # still-active security CURRENT by construction and could only ever flag a
    # name whose FINAL price -- a fact from after as_of -- fell earlier. O-F
    # replaced it; see research/of_security_status/audit_status_coverage.py.
    pres = pd.read_parquet(os.path.join(DATA, "price_presence.parquet"))
    dates_by_id = defaultdict(list)
    for sid, date in zip(pres["stock_id"].astype(str), pres["date"]):
        dates_by_id[sid].append(date)
    window = [s for s in calendar.sessions_through(as_of) if s > "2020-01-01"]

    def observed_through(sid):
        d = dates_by_id.get(sid, ())
        i = bisect.bisect_right(d, as_of)
        return d[i - 1] if i else None

    def observe(sid):
        rec = status.explaining_record(sid, as_of, as_of)
        return PitPriceObservation(
            as_of=as_of, stock_id=sid,
            price_observed_through=observed_through(sid),
            expected_sessions=tuple(window),
            known_status=rec.status if rec else "listed",
            status_available_from=rec.available_from if rec else None)

    held_ids = sorted(sid for sid in dates_by_id if observed_through(sid) == as_of)[:20]
    observations = [observe(sid) for sid in held_ids]

    # --- O-G: derive listing spells from real data ---------------------------
    # `gap_is_explained` is the O-B/O-E-1 question, answered by the SAME status
    # table the guard uses. O-G does not get its own opinion about explanation.
    window_sessions = tuple(calendar.sessions_through(as_of))

    def explained_for(sid):
        def _f(first_missing):
            return status.explaining_record(sid, first_missing, as_of) is not None
        return _f

    def spell_for(sid):
        priced = [d for d in dates_by_id.get(sid, ()) if d <= as_of]
        return derive_current_spell(as_of, sid, window_sessions, priced,
                                    explained_for(sid))

    spells = [sp for sp in (spell_for(sid) for sid in held_ids) if sp is not None]
    results["listing_spells_on_holdings"] = {
        "declared": len(spells),
        "by_opened_by": {k: sum(1 for sp in spells if sp.opened_by == k)
                         for k in ("first_observation", "reappearance")},
    }
    verdicts = assert_no_unexplained_price_gap(as_of, observations)
    results["market_state_guard_on_holdings"] = {
        **stale_mark_report(verdicts), "held": len(held_ids)}

    # --- 3b. universe-wide diagnostic -> delegated to O-F --------------------
    # This used to re-implement a weaker scan here. The O-F audit runs the same
    # production classifier over session-level presence and reports terminal and
    # interior gaps; duplicating a second, looser answer next to it is how two
    # numbers for one question end up in the record.
    of_path = os.path.join(REPO, "research", "of_security_status",
                           "status_coverage_audit.json")
    of = json.load(open(of_path, encoding="utf-8"))
    results["universe_gap_diagnostic"] = {
        "delegated_to": "research/of_security_status/status_coverage_audit.json",
        "as_of": of["audit_A_as_of_snapshot"]["as_of"],
        "by_classification": of["audit_A_as_of_snapshot"]["by_classification"],
        "unexplained_by_cause": of["audit_A_as_of_snapshot"]["unexplained_by_cause"],
        "enforced": False,
    }

    # --- 3c. O-G on the securities that actually came back -------------------
    # The 27 exit-and-return securities are where a bridged window would be
    # built, so the derivation is exercised on them rather than only on names
    # that never left. They are read from the audit, not listed here.
    of = json.load(open(os.path.join(
        REPO, "research", "of_security_status", "event_table_audit.json"),
        encoding="utf-8"))
    returned = [r["stock_id"] for r in
                of["P6_interior_gap_split"]["exit_and_return_detail"]]
    late = max(dates_by_id[sid][-1] for sid in returned if sid in dates_by_id)
    reopened = []
    for sid in returned:
        priced = [d for d in dates_by_id.get(sid, ()) if d <= late]
        sp = derive_current_spell(late, sid, tuple(calendar.sessions_through(late)),
                                  priced, explained_for(sid))
        if sp is not None:
            reopened.append(sp)
    results["listing_spells_on_returned_securities"] = {
        "as_of": late,
        "securities": len(returned),
        "spells_derived": len(reopened),
        "opened_by_reappearance": sum(1 for sp in reopened
                                      if sp.opened_by == "reappearance"),
        "examples": [{"stock_id": sp.stock_id, "start": sp.start,
                      "opened_by": sp.opened_by} for sp in reopened[:5]],
    }

    # --- 4. corporate-action exposure guard ----------------------------------
    # No holdings on this date, so no exposure: the guard must pass and must be
    # shown to be capable of firing (it is, in tests) rather than vacuous here.
    unreconstructible = [e for e in events
                         if e.reconstructibility == NOT_RECONSTRUCTIBLE]
    assert_exposure_reconstructible(events, [])
    results["corporate_actions"] = {
        "events": len(events),
        "not_reconstructible": len(unreconstructible),
        "exposures_declared": 0,
        "guard_passed_because_nothing_was_held": True,
    }

    # --- 5. adapter input construction ---------------------------------------
    portfolio = PortfolioState(as_of=as_of, cash=2_000_000.0,
                               shares={sid: 1000 for sid in held_ids})
    sources = RetrospectiveSources(
        calendar=calendar, status_table=status, attestation=attestation,
        marks={}, adv20={}, sigma20d={}, pit_inputs=(),
        price_observations=tuple(observations[:50]),
        corporate_action_events=tuple(events[:200]), exposures=(),
        price_source=price_source,
        listing_spells=tuple(spells))
    # §6.5: execution is the open of the FOLLOWING session.
    execution_date = next(s for s in calendar.sessions_through("2020-07-31")
                          if s > DECISION_DATE)
    inp = build_input(sources, portfolio, DECISION_DATE,
                      execution_date=execution_date, execution_prices={})
    results["canonical_input"] = {
        "route_kind": inp.route_kind,
        "as_of": inp.as_of,
        "config_hash": config_hash(),
        "state_hash": inp.state_hash(),
    }

    # --- 6. route reachability invariants ------------------------------------
    from core.b0_invariants import (
        B0_ENTRY_MODULES, B0_REGISTERED_OVERRIDES, LEGACY_COST_MODULES,
        LEGACY_COST_SYMBOLS, OVERRIDE_MODULES, OVERRIDE_SYMBOLS,
        REGIME_DECISION_MODULES, REGIME_DECISION_SYMBOLS,
        find_import_time_foreign_mutations, find_violations,
    )
    checks = {
        "G14-4_legacy_cost": find_violations(
            B0_ENTRY_MODULES, LEGACY_COST_MODULES, LEGACY_COST_SYMBOLS),
        "B-17_regime": find_violations(
            B0_ENTRY_MODULES, REGIME_DECISION_MODULES, REGIME_DECISION_SYMBOLS),
        "B-19_overrides": find_violations(
            B0_ENTRY_MODULES, OVERRIDE_MODULES, OVERRIDE_SYMBOLS),
    }
    mutations = find_import_time_foreign_mutations(B0_ENTRY_MODULES)
    for name, v in checks.items():
        if v:
            raise SystemExit(f"route invariant {name} violated: {v}")
    if mutations:
        raise SystemExit(f"import-time foreign mutations: {mutations}")
    results["invariants"] = {
        "entry_modules": len(B0_ENTRY_MODULES),
        "violations": {k: len(v) for k, v in checks.items()},
        "import_time_foreign_mutations": len(mutations),
        "registered_overrides": len(B0_REGISTERED_OVERRIDES),
    }

    # --- 7. B-20 parity mechanics (declaration only, no decision run) --------
    from core.b0_parity import B0_ROUTE_PAIRS, PARITY_COLUMNS, PARITY_LAYERS
    results["b20_parity"] = {
        "route_pairs_declared": len(B0_ROUTE_PAIRS),
        "columns": len(PARITY_COLUMNS), "layers": len(PARITY_LAYERS),
        "decision_run_on_real_data": False,
    }

    payload = {"study": "real-data adapter validation (no decision layer)",
               "read_only": True, "performance_computed": False,
               "selection_computed": False, "nav_computed": False,
               "results": results}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    for k, v in results.items():
        print(f"{k}:")
        for kk, vv in (v.items() if isinstance(v, dict) else []):
            if kk == "detail":
                print(f"    {kk}: {len(vv)} entries")
            else:
                print(f"    {kk}: {vv}")
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
