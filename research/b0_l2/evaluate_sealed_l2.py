# -*- coding: utf-8 -*-
"""Stage 1 of the L2 evaluation: re-derive the sealed run and recover §9.7.

WHY A RE-DERIVATION IS NEEDED AT ALL

The sealed runner recorded, per period, only `port_value`, `state_hash`,
`positions` and the applied CA ids. §9.7 requires eight categories and most of
them were computed and then discarded: the three cost columns live on each
`Receipt`, the per-layer eliminations on `EligibilityResult.rejected`, the ADV
floor path on `EligibilityResult.adv_floor`, `zero_sigma_fill` and
`adv_cap_shortfall_value` on `SessionResult`. All of it existed inside
`run_decision` and none of it was written down.

§9.7 is not a nice-to-have: "開封時必須全數輸出，缺一項即該次開封作廢". So the
detail has to be recovered, and the only honest way to recover it is to compute
the same deterministic function over the same sealed inputs again.

WHY THAT IS NOT A SECOND OBSERVATION

Because it is checked to be the SAME run, not another one. Every period's
`state_hash` and `post_state_hash` must equal what the sealed run recorded, and
a single mismatch aborts. A re-derivation that reproduces 141 recorded hashes is
the recorded run, re-expressed; it cannot be a different look at the window
because it is not free to differ. The once-only observation was spent by
`L2-688d001e44b5d517`; this reads that observation out, it does not take another.

The inverse is the real risk and it is the reason for the abort: if the hashes
did NOT match, the detail collected here would describe some other computation
while wearing the sealed run's name. That is this project's most expensive bug
shape, so it is checked at every period rather than once at the end.

WHAT THIS STAGE DOES NOT DO

No ladder, no V-4 verdict, no registry row. §9.3 rows ①②③ and §9.4's three
AND conditions are stage 2; writing an outcome before the ladder exists would be
a verdict formed from row ◆ alone.

    B0_MATERIALIZE_LINEAGE=B1 python research/b0_l2/evaluate_sealed_l2.py \
        L2-688d001e44b5d517 --lineage B1
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))
sys.path.insert(0, HERE)

from core import b0_corporate_actions as ca                      # noqa: E402
from core.b0_canonical_hash import canonical_sha256              # noqa: E402
from core.b0_l2_run_layout import resolve_run_dir, sha256_of     # noqa: E402
from core.b0_master_prereg import (                              # noqa: E402
    active_lineage, assert_declared_lineage, lineage_data_root,
    lineage_freeze_path, lineage_market_state_dataset_id,
    lineage_market_state_manifest, write_provenance_json,
)
from core.b0_route import run_decision                           # noqa: E402
from core.b0_state import PortfolioState                         # noqa: E402

from run_sealed_l2 import build_input, hxa_anchor_for_run, load_events  # noqa: E402
from build_period1_full_input import _price_contract, opening_states    # noqa: E402

LINEAGE = active_lineage()
DATA = lineage_data_root(LINEAGE)
MANIFEST = lineage_market_state_manifest(LINEAGE)
FREEZE = lineage_freeze_path(LINEAGE)

# Its own namespace. The run directory is the immutable record of what happened;
# an evaluation is a reading of it and must not be able to grow inside it.
OUT_ROOT = os.path.join(REPO, "artifacts", "l2_evaluation%s"
                        % ("" if LINEAGE == "FROZEN_B0" else "_" + LINEAGE.lower()))


class DerivationMismatch(RuntimeError):
    """A re-derived period is not the period the sealed run recorded."""


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def bind_run(run_id: str) -> dict:
    """The sealed run this evaluation reads, and proof it terminated cleanly."""
    d = resolve_run_dir(run_id, LINEAGE)
    opening = _load(os.path.join(d, "opening_record.json"))
    final = _load(os.path.join(d, "final_result.json"))
    progress = [json.loads(l) for l in
                open(os.path.join(d, "period_progress.jsonl"), encoding="utf-8")
                if l.strip()]
    nav = _load(os.path.join(d, "nav_series.json"))

    if final.get("formal_outcome") is not None:
        raise DerivationMismatch(
            "%s already carries formal_outcome %r. An outcome is written once."
            % (run_id, final["formal_outcome"]))
    if final["periods_executed"] != final["periods_required"]:
        raise DerivationMismatch(
            "%s executed %d of %d periods. A partial run has no §9.7 report to "
            "produce; its terminal record already says what happened."
            % (run_id, final["periods_executed"], final["periods_required"]))
    for name, seq in (("period_progress", len(progress)), ("nav_series", len(nav))):
        if seq != final["periods_required"]:
            raise DerivationMismatch(
                "%s has %d rows and the run required %d"
                % (name, seq, final["periods_required"]))
    return {"run_dir": d, "opening": opening, "final": final,
            "progress": progress, "nav": nav,
            "recorded_hashes": {r["period"]: (r["state_hash"],
                                              r["post_state_hash"])
                                for r in progress}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--lineage", default="")
    a = ap.parse_args()
    assert_declared_lineage(a.lineage, LINEAGE)

    bound = bind_run(a.run_id)
    manifest = _load(MANIFEST)
    freeze = _load(FREEZE)
    print("=" * 78)
    print("L2 EVALUATION stage 1 - re-derivation  (%s)" % LINEAGE)
    print("=" * 78)
    print("run              : %s" % a.run_id)
    print("periods recorded : %d" % len(bound["progress"]))
    print("spec             : %s" % freeze["spec_sha256"][:16])
    print("seal             : %s" % bound["opening"]["baseline_seal_sha256"][:16])
    print(flush=True)

    sessions = tuple(r["session"] for r in csv.DictReader(
        open(os.path.join(DATA, "trading_calendar.csv"), encoding="utf-8")))
    events_by_sid = load_events()
    hxa_anchor = hxa_anchor_for_run()

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
        as_of=canonical_open["as_of"], cash=canonical_open["cash"],
        shares=canonical_open["shares"], pending_exit=canonical_open["pending_exit"],
        cash_dividend_receivable=canonical_open["cash_dividend_receivable"],
        stock_dividend_receivable=canonical_open["stock_dividend_receivable"])
    opening_cash = float(canonical_open["cash"])

    periods, eligible_names, ca_kind_status = [], [], Counter()
    exposed_not_reconstructible = []

    for i, period in enumerate(manifest, 1):
        as_of, pname = period["as_of"], period["decision_month"]
        state = ca.redate(portfolio, as_of)
        held = [e for sid in state.entitlement_securities
                for e in events_by_sid.get(sid, ())]
        tr = ca.transition_portfolio(state, held, as_of=as_of, sessions=sessions,
                                     period=pname, hxa_anchor=hxa_anchor)
        for rec in tr.ledger:
            ca_kind_status[(rec.event_kind, rec.reconstructibility)] += 1
            if rec.reconstructibility == ca.NOT_RECONSTRUCTIBLE:
                exposed_not_reconstructible.append({
                    "period": pname, "event_id": rec.event_id,
                    "event_kind": rec.event_kind, "security_id": rec.security_id,
                    "disposition": ("HXA_APPLIED" if rec.hxa_applied else "APPLIED"),
                    "hxa_price_basis": rec.hxa_price_basis})
        rows = pd.read_parquet(os.path.join(REPO, period["artefact"]))
        inp = build_input(period, rows, tr.state, sessions, events_by_sid,
                          calendar, attestation, price_source)
        result = run_decision(inp, for_sealed_run=True)
        s = result.session

        recorded = bound["recorded_hashes"].get(pname)
        if recorded is None:
            raise DerivationMismatch("the sealed run has no period %r" % pname)
        if result.state_hash != recorded[0]:
            raise DerivationMismatch(
                "period %s: re-derived decision state %s, the sealed run "
                "recorded %s. This is NOT the same run and nothing collected "
                "here may be attributed to it."
                % (pname, result.state_hash[:16], recorded[0][:16]))

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
        post = ca._state_hash(portfolio)
        if post != recorded[1]:
            raise DerivationMismatch(
                "period %s: re-derived post state %s, the sealed run recorded %s"
                % (pname, post[:16], recorded[1][:16]))

        elig = result.eligibility
        # Row ① needs the NAMES, not the count. Stage 1 recorded only counts,
        # which is why testing "the skipped events are a small share" required
        # this second pass rather than a lookup.
        eligible_names.append({"period": pname, "as_of": as_of,
                               "eligible": list(elig.eligible)})
        periods.append({
            "seq": i, "period": pname, "as_of": as_of,
            "execution_date": period["execution_date"],
            "port_value": result.port_value,
            "cash_after": s.cash_after,
            "positions": len(s.shares_after),
            # S-6 / §9.7: the three cost columns stay apart, never a total only.
            "explicit_fee": sum(r.explicit_fee for r in s.receipts),
            "transaction_tax": sum(r.transaction_tax for r in s.receipts),
            "impact": sum(r.impact for r in s.receipts),
            "turnover_value": s.turnover_value,
            "child_orders": len(s.receipts),
            "zero_sigma_fills": s.zero_sigma_fills,
            "adv_cap_shortfall_value": s.adv_cap_shortfall_value,
            "adv_floor": elig.adv_floor,
            "eligibility_counts": elig.counts,
            "pending_exit_names": len(s.pending_exit_after),
            "pending_exit_shares": int(sum(s.pending_exit_after.values())),
            "stale_marks": len(result.stale_marks),
            "state_hash": result.state_hash, "post_state_hash": post,
        })
        if i % 20 == 0:
            print("  %3d/%d  %s  hashes match" % (i, len(manifest), pname),
                  flush=True)

    out_dir = os.path.join(OUT_ROOT, a.run_id)
    detail = {
        "record": "B0_L2_EVALUATION_STAGE1_REDERIVATION",
        "stage": 1,
        "establishes": "the recorded run, re-expressed with the §9.7 detail it "
                       "computed and discarded",
        "does_not_establish": ["§9.3 ladder rows 1/2/3", "§9.4 V-4 verdict",
                               "any opening-registry outcome"],
        "lineage": LINEAGE, "run_id": a.run_id,
        "baseline_seal_sha256": bound["opening"]["baseline_seal_sha256"],
        "spec_sha256": freeze["spec_sha256"],
        "commit_sha": bound["opening"]["commit_sha"],
        "periods_rederived": len(periods),
        "decision_state_hashes_matched": len(periods),
        "post_state_hashes_matched": len(periods),
        "opening_cash": opening_cash,
        "corporate_action_status_counts": {
            "%s|%s" % k: v for k, v in sorted(ca_kind_status.items())},
        # §9.7 requires this list EVEN IF EMPTY.
        "exposed_not_reconstructible_events": exposed_not_reconstructible,
        "per_period": periods,
    }
    write_provenance_json(os.path.join(out_dir, "evaluation_stage1.json"), detail)
    write_provenance_json(os.path.join(out_dir, "eligible_names.json"),
                          eligible_names)

    print()
    print("=" * 78)
    print("periods re-derived        : %d / %d" % (len(periods), len(manifest)))
    print("decision state hashes     : %d matched, 0 mismatched" % len(periods))
    print("post state hashes         : %d matched, 0 mismatched" % len(periods))
    print("exposed NOT_RECONSTRUCTIBLE: %d" % len(exposed_not_reconstructible))
    print("written                   : %s"
          % os.path.relpath(os.path.join(out_dir, "evaluation_stage1.json"), REPO))
    print("=" * 78)
    print("stage 2 (ladder + V-4) NOT run. No outcome has been written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
