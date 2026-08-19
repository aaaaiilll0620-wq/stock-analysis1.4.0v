# -*- coding: utf-8 -*-
"""The sealed 141-period L2 retrospective run. Once-only.

Reads the opening record, replays the frozen window through the SHARED core, and
writes append-only provenance. It contains no strategy semantics: every feature,
filter, score, target, order and cost happens behind `run_decision`, and every
corporate action happens behind `core.b0_corporate_actions`.

Causal chain per period, in the order §6.1.1 freezes:

    PortfolioState[t-1]
      -> redate to as_of[t]
      -> corporate_action_engine (release matured, apply effective, invariants)
      -> CanonicalDecisionInput
      -> run_decision  (features -> eligibility -> score -> targets -> execution)
      -> PortfolioState[t]

Nothing here may be tuned, retried, patched or skipped.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import traceback
from fractions import Fraction

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

from core import b0_corporate_actions as ca                      # noqa: E402
from core.b0_canonical_hash import canonical_sha256              # noqa: E402
from core.b0_corporate_actions import (                          # noqa: E402
    NOT_RECONSTRUCTIBLE, RECONSTRUCTIBLE, CorporateActionEvent, Exposure,
)
from core.b0_features import SecurityPitInputs                   # noqa: E402
from core.b0_listing_spell import ListingSpell                   # noqa: E402
from core.b0_master_prereg import (                             # noqa: E402
    append_provenance_record, write_provenance_json,
)
from core.b0_pit_observability import PitPriceObservation        # noqa: E402
from core.b0_route import ROUTE_KIND_RETROSPECTIVE, run_decision # noqa: E402
from core.b0_state import PortfolioState                         # noqa: E402

from build_period1_full_input import (                           # noqa: E402
    _clean, _price_contract, _scalar, opening_states,
)

DATA = os.path.join(REPO, "data", "b0")
OUT = os.path.join(REPO, "artifacts", "l2_run")
MANIFEST = os.path.join(DATA, "market_state_manifest.json")


def _jsonl(name, row):
    """R5: one primitive, in a normative module, writing binary LF bytes.

    `newline="\n"` here was correct but local — the registry writer in
    `core.b0_master_prereg` did not have it, and the same logical opening record
    therefore hashed differently on Windows. A provenance byte rule that each
    caller re-implements is a rule that one caller will get wrong.
    """
    append_provenance_record(os.path.join(OUT, name),
                             json.loads(json.dumps(row, default=str)))


def load_events():
    """Ledger + C-51 bonus panel -> normalized CorporateActionEvent per security.

    The ratio for a stock dividend comes from the sealed bonus panel (C-51), not
    from the ledger's new-share count: converting a count needs shares
    outstanding, which is exactly the reconstruction C-51 exists to avoid.
    """
    bonus = {}
    bp = pd.read_parquet(os.path.join(DATA, "bonus_share_panel.parquet"))
    for r in bp.itertuples():
        if r.disposition == "OFFICIAL_BONUS_RATE":
            bonus[(str(r.stock_id), str(r.market_effective_session))] = \
                Fraction(str(r.bonus_shares_per_1000)) / 1000
    by_sid = {}
    with open(os.path.join(DATA, "corporate_actions_ledger.csv"), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            kind = row["kind"]
            if kind not in ca.holder_affecting_kinds():
                continue
            sid, ex = str(row["stock_id"]), row["ex_or_effective_date"]
            if not ex:
                continue
            recon = row["reconstructibility"]
            kw = dict(reason=row.get("reason") or "", knowledge_ts=ex,
                      credit_tradable_date=row.get("credit_tradable_date") or None,
                      cash_payment_date=row.get("cash_payment_date") or None)
            if row.get("share_multiplier"):
                kw["share_multiplier"] = float(row["share_multiplier"])
            if row.get("cash_per_share"):
                kw["cash_per_share"] = float(row["cash_per_share"])
            if kind == "stock_dividend":
                ratio = bonus.get((sid, ex))
                if ratio is None:
                    recon = NOT_RECONSTRUCTIBLE
                    kw["reason"] = kw["reason"] or (
                        "no admissible official bonus-share ratio (C-51)")
                else:
                    kw["stock_ratio"] = ratio
                    if not kw["credit_tradable_date"]:
                        recon = NOT_RECONSTRUCTIBLE
                        kw["reason"] = "no credit_tradable_date (W-1)"
            if recon == NOT_RECONSTRUCTIBLE and not kw["reason"]:
                kw["reason"] = "identity-change terms are not observable"
            ev = CorporateActionEvent(sid, kind, ex, recon, **kw)
            by_sid.setdefault(sid, []).append(ev)
    return by_sid


def build_input(period, rows, portfolio, sessions, events_by_sid, calendar,
                attestation, price_source):
    from core.b0_route import CanonicalDecisionInput
    from core.b0_state import MarketSnapshot

    as_of = period["as_of"]
    marks, adv20, sigma20d, exec_px, untradable = {}, {}, {}, {}, set()
    pit_inputs, spells = [], []
    for r in rows.itertuples():
        sid = str(r.stock_id)
        if _scalar(r.mark) is not None:
            marks[sid] = _scalar(r.mark)
        if _scalar(r.adv20) is not None:
            adv20[sid] = _scalar(r.adv20)
        if _scalar(r.sigma20d) is not None:
            sigma20d[sid] = _scalar(r.sigma20d)
        if _scalar(r.execution_open) is not None:
            exec_px[sid] = _scalar(r.execution_open)
        if r.known_status != "listed":
            untradable.add(sid)
        spells.append(ListingSpell(stock_id=sid, start=str(r.spell_start),
                                   opened_by="first_observation", as_of=as_of))
        pit_inputs.append(SecurityPitInputs(
            stock_id=sid,
            net_income_by_quarter=_clean(r.net_income_by_quarter),
            revenue_by_quarter=_clean(r.revenue_by_quarter),
            gross_profit_by_quarter=_clean(r.gross_profit_by_quarter),
            eps_by_quarter=_clean(r.eps_by_quarter),
            period_end_equity=_scalar(r.period_end_equity),
            total_liabilities=_scalar(r.total_liabilities),
            total_assets=_scalar(r.total_assets),
            current_assets=_scalar(r.current_assets),
            current_liabilities=_scalar(r.current_liabilities),
            monthly_revenue=_clean(r.monthly_revenue),
            month_end_prices=_clean(r.month_end_prices),
            per_tse=_scalar(r.per_tse), pbr_tse=_scalar(r.pbr_tse),
            pit_industry=str(r.pit_industry)))

    held = list(portfolio.held_securities)
    spell_by = {s.stock_id: s for s in spells}
    obs, exposures, ca_events = [], [], []
    upto = [s for s in sessions if s <= as_of]
    for sid in held:
        sp = spell_by.get(sid)
        start = sp.start if sp else upto[-60] if len(upto) > 60 else upto[0]
        expected = tuple(s for s in upto if s >= start)
        priced = rows.loc[rows.stock_id == sid]
        through = as_of if len(priced) else None
        obs.append(PitPriceObservation(
            as_of=as_of, stock_id=sid, price_observed_through=through,
            expected_sessions=expected,
            known_status=str(priced.iloc[0].known_status) if len(priced) else "listed"))
        exposures.append(Exposure(stock_id=sid, held_from=start, held_until=as_of))
        ca_events.extend(e for e in events_by_sid.get(sid, ())
                         if e.ex_or_effective_date <= as_of)

    snapshot = MarketSnapshot(as_of=as_of, attestation=attestation, marks=marks,
                              adv20=adv20, sigma20d=sigma20d)
    return CanonicalDecisionInput(
        route_kind=ROUTE_KIND_RETROSPECTIVE, decision_date=period["decision_date"],
        as_of=as_of, snapshot=snapshot, portfolio=portfolio,
        pit_inputs=tuple(pit_inputs), price_observations=tuple(obs),
        corporate_action_events=tuple(ca_events), exposures=tuple(exposures),
        execution_date=period["execution_date"], execution_prices=exec_px,
        untradable=frozenset(untradable), listing_spells=tuple(spells))


def main() -> int:
    opening = json.load(open(os.path.join(OUT, "opening_record.json"),
                             encoding="utf-8"))
    run_id = opening["run_id"]
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    sessions = tuple(r["session"] for r in csv.DictReader(
        open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8")))
    events_by_sid = load_events()

    from core.b0_market_state import SourceContract, TradingCalendar
    from core.b0_provenance import file_sha256
    from core.b0_state import SourceAttestation
    calendar = TradingCalendar(
        sessions=sessions,
        source=SourceContract(
            name="b0_trading_calendar", kind="trading_calendar",
            importer_version="b0_calendar_importer@1",
            content_sha256=file_sha256(os.path.join(DATA, "trading_calendar.csv")),
            schema_sha256=canonical_sha256(["session"]),
            date_min=sessions[0], date_max=sessions[-1],
            has_effective_dates=True, has_availability_semantics=True,
            is_current_snapshot=False, availability_convention="session_close"))
    freeze = json.load(open(os.path.join(
        REPO, "research", "b0_registry", "master_prereg_freeze.json"),
        encoding="utf-8"))
    attestation = SourceAttestation(
        dataset_id="b0_market_side_state_20260819",
        provenance_sha256=freeze["spec_sha256"], pit_guard_passed=True,
        universe_guard_passed=True,
        satisfied_blocking_requirements=("price_universe_survivorship",),
        synthetic=False)
    price_source = _price_contract(json.load(open(os.path.join(
        REPO, "research", "b0_materializer", "price_panel_receipt.json"),
        encoding="utf-8")))

    _, canonical_open = opening_states(manifest[0]["as_of"])
    portfolio = PortfolioState(
        as_of=canonical_open["as_of"], cash=canonical_open["cash"],
        shares=canonical_open["shares"], pending_exit=canonical_open["pending_exit"],
        cash_dividend_receivable=canonical_open["cash_dividend_receivable"],
        stock_dividend_receivable=canonical_open["stock_dividend_receivable"])

    nav_series, done = [], 0
    for i, period in enumerate(manifest, 1):
        as_of = period["as_of"]
        try:
            state = ca.redate(portfolio, as_of)
            held_events = [e for sid in state.entitlement_securities
                           for e in events_by_sid.get(sid, ())]
            tr = ca.transition_portfolio(state, held_events, as_of=as_of,
                                         sessions=sessions,
                                         period=period["decision_month"])
            for rec in tr.ledger:
                _jsonl("ca_transition_ledger.jsonl",
                       {"run_id": run_id, **rec.__dict__})
            rows = pd.read_parquet(period["artefact"])
            inp = build_input(period, rows, tr.state, sessions, events_by_sid,
                              calendar, attestation, price_source)
            result = run_decision(inp, for_sealed_run=True)
            s = result.session
            portfolio = PortfolioState(
                as_of=as_of, cash=s.cash_after, shares=dict(s.shares_after),
                pending_exit=dict(s.pending_exit_after),
                cash_dividend_receivable=tr.state.cash_dividend_receivable,
                stock_dividend_receivable=dict(tr.state.stock_dividend_receivable),
                security_receivables=tr.state.security_receivables,
                cash_receivables=tr.state.cash_receivables,
                applied_ca_event_ids=tr.state.applied_ca_event_ids,
                pending_exit_on_receivable=tr.state.pending_exit_on_receivable)
            nav_series.append({"period": period["decision_month"], "as_of": as_of,
                               "port_value": result.port_value,
                               "cash_after": s.cash_after,
                               "positions": len(s.shares_after)})
            _jsonl("period_progress.jsonl", {
                "run_id": run_id, "seq": i, "period": period["decision_month"],
                "as_of": as_of, "port_value": result.port_value,
                "state_hash": result.state_hash,
                "positions": len(s.shares_after),
                "ca_applied": list(tr.applied_event_ids),
                "post_state_hash": ca._state_hash(portfolio)})
            done = i
        except ca.CorporateActionReconstructionBlock as exc:
            _jsonl("failure_record.jsonl", {
                "run_id": run_id, "classification": "F-CA-B",
                "formal_result": "NOT EVALUABLE — CORPORATE ACTION RECONSTRUCTION BLOCK",
                "period": period["decision_month"], "seq": i, **exc.detail})
            print("BLOCK F-CA-B at %s: %s" % (period["decision_month"], exc))
            return 2
        except Exception as exc:                     # noqa: BLE001
            _jsonl("failure_record.jsonl", {
                "run_id": run_id, "classification": "F-CA-C-or-core",
                "period": period["decision_month"], "seq": i,
                "error_type": type(exc).__name__, "error": str(exc),
                "traceback": traceback.format_exc()[-4000:]})
            print("FAILURE at %s: %s: %s" % (period["decision_month"],
                                             type(exc).__name__, exc))
            return 3
        if i % 20 == 0:
            print("  %d/141  %s  port_value=%.2f" % (i, period["decision_month"],
                                                     result.port_value), flush=True)

    write_provenance_json(os.path.join(OUT, "nav_series.json"), nav_series)
    print("completed %d/141 periods" % done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
