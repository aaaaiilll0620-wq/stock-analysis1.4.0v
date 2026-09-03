# -*- coding: utf-8 -*-
"""Stage 2b: build §9.3 row ① and report `◆ − ①`, the selection-ability line.

Walks the same 141 periods with the same inputs and the same execution layer,
holding the whole eligible universe equal-weighted instead of the 20 the
strategy chose. See `l2_row1.py` for every construction decision and for the
user's 2026-09-03 skip ruling and its disclosed bias direction.

    B0_MATERIALIZE_LINEAGE=B1 python research/b0_l2/evaluate_stage2b_row1.py \
        L2-688d001e44b5d517 --lineage B1
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))
sys.path.insert(0, HERE)

from core import b0_corporate_actions as ca                      # noqa: E402
from core.b0_canonical_hash import canonical_sha256              # noqa: E402
from core.b0_l2_run_layout import resolve_run_dir                # noqa: E402
from core.b0_master_prereg import (                              # noqa: E402
    active_lineage, assert_declared_lineage, lineage_data_root,
    lineage_freeze_path, lineage_market_state_dataset_id,
    lineage_market_state_manifest, write_provenance_json,
)
from core.b0_state import PortfolioState                         # noqa: E402

from run_sealed_l2 import build_input, hxa_anchor_for_run, load_events  # noqa: E402
from build_period1_full_input import _price_contract, opening_states    # noqa: E402
from l2_ladder import performance                                # noqa: E402
from l2_row1 import (                                            # noqa: E402
    ROW1_BUY_ORDER, ROW1_UNRECONSTRUCTIBLE_DISPOSAL, ROW1_WEIGHTING,
    Row1Error, dispose_at_pre_boundary_close, execute_row1_period,
    exposed_unreconstructible, mark_book, restore_sd_skip,
)

LINEAGE = active_lineage()
DATA = lineage_data_root(LINEAGE)
OUT_ROOT = os.path.join(REPO, "artifacts", "l2_evaluation%s"
                        % ("" if LINEAGE == "FROZEN_B0" else "_" + LINEAGE.lower()))


def _load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--lineage", default="")
    a = ap.parse_args()
    assert_declared_lineage(a.lineage, LINEAGE)

    out_dir = os.path.join(OUT_ROOT, a.run_id)
    stage1 = _load(os.path.join(out_dir, "evaluation_stage1.json"))
    elig_by_period = {r["period"]: r["eligible"]
                      for r in _load(os.path.join(out_dir, "eligible_names.json"))}
    manifest = _load(lineage_market_state_manifest(LINEAGE))
    freeze = _load(lineage_freeze_path(LINEAGE))
    opening_cash = float(stage1["opening_cash"])

    sessions = tuple(r["session"] for r in csv.DictReader(
        open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8")))
    events_by_sid = load_events()
    events_by_sid, sd_skip_stats = restore_sd_skip(
        events_by_sid, os.path.join(DATA, "corporate_actions_ledger.csv"))
    print("SD-SKIP restored from the ledger: %d event(s) over %d ledger rows"
          % (sd_skip_stats["events_restored"],
             sd_skip_stats["ledger_sd_skip_rows"]), flush=True)
    anchor = hxa_anchor_for_run()
    if anchor is None:
        raise Row1Error("row 1's skip ruling needs a price anchor and this "
                        "lineage supplies none")

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
    attestation = SourceAttestation(
        dataset_id=lineage_market_state_dataset_id(LINEAGE),
        provenance_sha256=freeze["spec_sha256"], pit_guard_passed=True,
        universe_guard_passed=True,
        satisfied_blocking_requirements=("price_universe_survivorship",),
        synthetic=False)
    price_source = _price_contract(_load(os.path.join(
        REPO, "research", "b0_materializer", "price_panel_receipt.json")))

    _, canonical_open = opening_states(manifest[0]["as_of"])
    portfolio = PortfolioState(
        as_of=canonical_open["as_of"], cash=opening_cash,
        shares=canonical_open["shares"], pending_exit=canonical_open["pending_exit"],
        cash_dividend_receivable=canonical_open["cash_dividend_receivable"],
        stock_dividend_receivable=canonical_open["stock_dividend_receivable"])

    marked, disposals, per_period = [], [], []
    for i, period in enumerate(manifest, 1):
        as_of, pname = period["as_of"], period["decision_month"]
        state = ca.redate(portfolio, as_of)
        held = [e for sid in state.entitlement_securities
                for e in events_by_sid.get(sid, ())]

        rows = pd.read_parquet(os.path.join(REPO, period["artefact"]))
        marks = {str(r.stock_id): float(r.mark) for r in rows.itertuples()
                 if r.mark == r.mark}
        pv_pre = mark_book(state, marks)

        # The user's ruling, before the engine gets a chance to fail closed.
        for ev in exposed_unreconstructible(state, held, as_of):
            got = dispose_at_pre_boundary_close(state, ev, anchor, pname, pv_pre)
            if got is None:
                continue                      # no anchor -> §6.1.12 still governs
            state, log = got
            disposals.append(log)

        tr = ca.transition_portfolio(state, held, as_of=as_of, sessions=sessions,
                                     period=pname, hxa_anchor=anchor)
        inp = build_input(period, rows, tr.state, sessions, events_by_sid,
                          calendar, attestation, price_source)
        pv = mark_book(tr.state, marks)
        session, meta = execute_row1_period(
            pre_trade=tr.state, eligible=elig_by_period[pname], marks=marks,
            adv20=inp.snapshot.adv20, sigma20d=inp.snapshot.sigma20d,
            execution_prices=inp.execution_prices, untradable=inp.untradable,
            as_of=as_of, execution_date=period["execution_date"], port_value=pv)
        s = session
        portfolio = PortfolioState(
            as_of=as_of, cash=s.cash_after, shares=dict(s.shares_after),
            pending_exit=dict(s.pending_exit_after),
            cash_dividend_receivable=tr.state.cash_dividend_receivable,
            stock_dividend_receivable=dict(tr.state.stock_dividend_receivable),
            security_receivables=tr.state.security_receivables,
            cash_receivables=tr.state.cash_receivables,
            applied_ca_event_ids=tr.state.applied_ca_event_ids,
            pending_exit_on_receivable=tr.state.pending_exit_on_receivable,
            holding_spells=tr.state.holding_spells)
        portfolio = portfolio.with_underlying_exposure_recorded(
            period["execution_date"])
        wealth = mark_book(portfolio, marks)
        marked.append({"as_of": as_of, "period": pname, "wealth": wealth})
        per_period.append({
            "seq": i, "period": pname, "as_of": as_of, "wealth": wealth,
            "eligible": len(elig_by_period[pname]),
            "names_targeted": meta["names_targeted"],
            "weight_each": meta["weight_each"],
            "breadth": meta["breadth"],
            "positions": len(s.shares_after),
            "explicit_fee": sum(r.explicit_fee for r in s.receipts),
            "transaction_tax": sum(r.transaction_tax for r in s.receipts),
            "impact": sum(r.impact for r in s.receipts),
            "turnover_value": s.turnover_value,
            "child_orders": len(s.receipts)})
        if i % 20 == 0:
            print("  %3d/%d  %s  eligible=%d  positions=%d"
                  % (i, len(manifest), pname, len(elig_by_period[pname]),
                     len(s.shares_after)), flush=True)

    row1 = performance(marked, opening_cash)
    strat = stage1  # for provenance only
    nav = _load(os.path.join(resolve_run_dir(a.run_id, LINEAGE),
                             "nav_series.json"))
    strategy = performance([{"as_of": r["as_of"], "wealth": r["port_value"]}
                            for r in nav], opening_cash)

    record = {
        "record": "B0_L2_EVALUATION_STAGE2B_ROW1",
        "stage": "2b", "lineage": LINEAGE, "run_id": a.run_id,
        "baseline_seal_sha256": strat["baseline_seal_sha256"],
        "spec_sha256": strat["spec_sha256"],
        "construction": {
            "weighting": ROW1_WEIGHTING, "buy_order": ROW1_BUY_ORDER,
            "cadence": "every decision period, matching the strategy",
            "execution_layer": "the same execute_session the strategy used",
            "unreconstructible_disposal": ROW1_UNRECONSTRUCTIBLE_DISPOSAL,
            "authority": "user ruling 2026-09-03; §9.3 specifies only "
                         "'eligibility 通過的全母體等權'",
        },
        "row_1_performance": row1,
        "row_0_performance": strategy,
        "selection_ability_row0_minus_row1": {
            "terminal_wealth_difference":
                strategy["terminal_wealth"] - row1["terminal_wealth"],
            "cagr_difference": strategy["cagr"] - row1["cagr"],
            "sharpe_difference": strategy["sharpe_0rf"] - row1["sharpe_0rf"],
        },
        "sd_skip_restored_from_ledger": sd_skip_stats,
        "skip_ruling_disclosure": {
            "disposals": len(disposals),
            "bias_direction": "pricing an exit at the pre-boundary close "
                              "predominantly UNDERSTATES it (§2.3(3): 6 of 8 "
                              "stock legs), and understating row 1 makes "
                              "row0-row1 LARGER, i.e. it flatters the "
                              "strategy's apparent selection ability",
            "events": disposals,
        },
        "per_period": per_period,
    }
    write_provenance_json(os.path.join(out_dir, "evaluation_stage2b.json"), record)

    print()
    print("=" * 78)
    print("%-24s %18s %18s" % ("", "row 0  strategy", "row 1  eligible EW"))
    for k in ("terminal_wealth", "wealth_multiple", "cagr", "sharpe_0rf", "mdd"):
        print("%-24s %18.4f %18.4f" % (k, strategy[k], row1[k]))
    d = record["selection_ability_row0_minus_row1"]
    print()
    print("SELECTION ABILITY  row0 - row1")
    print("  terminal wealth  %+18.2f" % d["terminal_wealth_difference"])
    print("  CAGR             %+18.4f" % d["cagr_difference"])
    print("  Sharpe_0rf       %+18.4f" % d["sharpe_difference"])
    print()
    print("skip ruling applied to %d event(s)" % len(disposals))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
