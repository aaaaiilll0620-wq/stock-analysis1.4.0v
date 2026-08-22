# -*- coding: utf-8 -*-
"""W-1 EXPOSURE CENSUS over the 158 holder-side reorganization boundaries.

WHAT THIS IS

A MEASUREMENT of how many of the 158 `holder_side_reorganization_exit`
boundaries the Frozen B0 portfolio can possibly reach while holding, over the
141-period retrospective window. It exists to answer one scoping question:

    is the TWSE lineage on the critical path for completing a replay,
    or does the portfolio never reach those boundaries?

WHAT THIS IS NOT, AND MUST NOT BECOME

    * It is NOT an input to document selection. B0.8's acquisition protocol is
      frozen and applies uniformly to all 158. Nothing here may be used to
      decide WHICH documents get acquired -- that is exactly the outcome-driven
      selection the B0.8 router's `selection_blind_to` clause forbids.
    * It changes NO event's reconstruction_status. §15.6 forbids pre-repairing
      the NOT_RECONSTRUCTIBLE population to make replay easier, and this script
      repairs nothing.
    * It computes NO NAV, no return, no performance quantity and no gate.
    * It writes only under `artifacts/b0_exposure_census/` and
      `research/b0_exposure_census/`. It touches no sealed artefact, no L2 run
      directory, no B0.8 artefact and no CA ledger.

Its one admissible use is the §2.4 / O-C precedent already on the record:
"final seal 不要求把所有歷史事件都變成 reconstructible" -- W-1 is exposure
sensitive by design, so knowing the exposure envelope tells you how much of the
remaining data work is load-bearing.

THE THREE LAYERS

LAYER A · DEDUCTIVE, ZERO COMPUTATION

Every one of the 158 is NOT_RECONSTRUCTIBLE by construction (§15.3), and W-1
aborts on ANY exposed NOT_RECONSTRUCTIBLE event (§15.5). The B0.7 retrospective
diagnostic executed periods 1-66 (2014-07 .. 2019-12) and terminated on the
FIRST such exposure, 8913 at 2020-01-14. Therefore the portfolio was exposed to
exactly ZERO of the boundaries falling before 2020-01-14. That is not an
estimate; it follows from the gate's own semantics plus the recorded failure.

LAYER B · PATH-INDEPENDENT NECESSARY-CONDITION SCREEN

This is NOT a strict upper bound on exposure. It is a screen built on one
necessary condition under a tested set of assumptions; the three limitations
declared below are each a possible false-negative source. It is named that way
everywhere in the output, because "upper bound" would assert a completeness
this census does not establish.

A security is not held at its boundary by the DIRECT SELECTION route unless it
was ELIGIBLE in at least
one decision period at or before that boundary. Eligibility (§4.1 complete
case, §4.4 risk filters, §4.2 dynamic investability) is a pure function of the
sealed per-period market-state panel and `port_value`; it does not depend on
the portfolio's composition or on any corporate-action outcome. So it can be
evaluated for all 141 periods without a replay and without resolving a single
blocked event.

`port_value` enters only through `adv_floor = port_value * 5.0`. The dependence
is monotone: a LOWER port_value gives a LOWER floor and therefore a LARGER
eligible set. The screen is swept over port_values down to 500k -- a quarter of
the opening 2.0M -- and the envelope is the UNION over those levels, so it is
widened across the tested range rather than pinned to one assumed path.

LAYER C · ENGINEERING-PRIORITY CANDIDATE ENVELOPE

The post-2020-01-14 boundaries that survive Layer B, plus the known 8913
blocker, form the

    N-event load-bearing candidate envelope under the tested
    direct-selection assumptions

They are the events most likely to be load-bearing, which is an ordering of
engineering priority. They are NOT "the only events that can ever block a
replay", and this output must never be read that way. The canonical
acquisition universe stays 158; nothing here narrows it, and no lineage-
specific or event-specific route may be opened because a member of this
envelope happens to sit on it.

WHY THE RECENCY-TIGHTENED BOUND WAS REJECTED

"Selected in the last K periods before the boundary" looked like the natural
tightening and it admits 0 of 42. It is WRONG, and the one known positive
proves it: 8913's holding spells ended 2017-08-01, thirty-one periods before
its 2020-01-14 boundary, and the exposure that stopped the B0.7 replay was
`tradable_shares: 0` with two residual fractional CLAIMS. Exposure survives the
position. Only the loose form -- ever selected at or before the boundary -- is
a valid necessary condition, and it is the one reported.

DECLARED LIMITATIONS OF THE BOUND

    1. SUCCESSOR SECURITIES. A name can enter the portfolio by being credited
       as the successor of another reorganization, never having been selected.
       If such a successor is itself one of the 158, this bound misses it.
    2. RECOMPUTATION ERROR. The selection layer here is recomputed
       path-independently; the real run also has a drift policy and a real cash
       balance. The recomputation places 8913 in the target set from 2017-04
       while its true spell opened 2017-03-01, so it does not reproduce the run
       exactly. The port_value sweep and the union across its levels widen the
       envelope but do not close this gap.
    3. PORT_VALUE RANGE. Only 500k .. 4.0M is swept.

The result is therefore an ENVELOPE under tested assumptions, not a proof
of exposure and not an upper bound on it.

    python research/b0_exposure_census/exposure_census.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_l2"))

import pandas as pd                                        # noqa: E402

from core import b0_eligibility as eligibility             # noqa: E402
from core import b0_decision as decision                    # noqa: E402
from core import b0_features as features                   # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from core.b0_features import SecurityPitInputs             # noqa: E402
from core.b0_master_prereg import spec                     # noqa: E402
from run_sealed_l2 import _clean, _scalar                  # noqa: E402

B08 = os.path.join(REPO, "research", "b0_8_holder_terms")
REGISTER = os.path.join(B08, "event_register.json")
CENSUS_D61 = os.path.join(B08, "document_discovery_census_d6_1.json")
CENSUS_D66 = os.path.join(B08, "tpex_exhaustive_discovery_census_d6_6.json")
MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")
B07_FAIL = os.path.join(REPO, "research", "b0_7_diagnostic",
                        "terminal_provenance", "final_result.json")
B07_PROGRESS = os.path.join(REPO, "research", "b0_7_diagnostic",
                            "terminal_provenance", "period_progress.jsonl")
OUT = os.path.join(HERE, "exposure_census.json")

# The B0.7 diagnostic's terminal blocker. Layer A pivots on this date.
BLOCKER_DATE = "2020-01-14"
BLOCKER_SID = "8913"
PORT_VALUE_SWEEP = (500_000.0, 1_000_000.0, 2_000_000.0, 4_000_000.0)


def panel_for(period):
    df = pd.read_parquet(period["artefact"])
    pit = [SecurityPitInputs(
        stock_id=str(r.stock_id),
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
        pit_industry=str(r.pit_industry)) for r in df.itertuples()]
    adv20 = {str(r.stock_id): _scalar(r.adv20) for r in df.itertuples()
             if _scalar(r.adv20) is not None}
    panel = features.build_feature_panel(
        period["as_of"], pit, convention=spec("percentile_convention"))
    return panel, adv20


def main() -> int:
    reg = json.load(open(REGISTER, encoding="utf-8"))
    d61 = json.load(open(CENSUS_D61, encoding="utf-8"))
    d66 = json.load(open(CENSUS_D66, encoding="utf-8"))
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    b07 = json.load(open(B07_FAIL, encoding="utf-8"))
    assert len(manifest) == 141, len(manifest)
    assert b07["detail"]["event_id"].startswith(BLOCKER_SID), b07["detail"]

    lineage = {r["event_id"]: r["market_lineage"] for r in d61["results"]}
    doc61 = {r["event_id"]: r["classification"] for r in d61["results"]}
    doc66 = {r["event_id"]: r["classification"] for r in d66["results"]}

    lo, hi = manifest[0]["as_of"], manifest[-1]["as_of"]
    events = reg["events"]
    assert len(events) == 158, len(events)

    for e in events:
        e["lineage"] = lineage.get(e["event_id"], "LINEAGE_UNRESOLVED")
        e["in_window"] = lo <= e["effective_date"] <= hi
        e["document_class"] = doc66.get(e["event_id"]) or doc61.get(
            e["event_id"])
    inwin = [e for e in events if e["in_window"]]

    # ---- LAYER A -------------------------------------------------------------
    pre = [e for e in inwin if e["effective_date"] < BLOCKER_DATE]
    at = [e for e in inwin if e["effective_date"] == BLOCKER_DATE]
    post = [e for e in inwin if e["effective_date"] > BLOCKER_DATE]
    layer_a = {
        "basis": ("all 158 are NOT_RECONSTRUCTIBLE by construction (§15.3); "
                  "W-1 aborts on ANY exposed NOT_RECONSTRUCTIBLE event "
                  "(§15.5); the B0.7 diagnostic executed periods 1-66 without "
                  "aborting and terminated on 8913 at 2020-01-14"),
        "b0_7_terminal_event": b07["detail"]["event_id"],
        "b0_7_periods_executed": 66,
        "boundaries_before_blocker": len(pre),
        "boundaries_before_blocker_by_lineage": dict(
            Counter(e["lineage"] for e in pre)),
        "exposed_among_them": 0,
        "exposed_at_blocker": [e["security_id"] for e in at],
        "boundaries_after_blocker": len(post),
        "boundaries_after_blocker_by_lineage": dict(
            Counter(e["lineage"] for e in post)),
        "reading": ("the portfolio reached NONE of the %d pre-blocker "
                    "boundaries while holding; the open question is confined "
                    "to the %d post-blocker boundaries"
                    % (len(pre), len(post))),
    }
    print("LAYER A  pre-blocker %d -> exposed 0 | at blocker %s | post %d"
          % (len(pre), [e["security_id"] for e in at], len(post)), flush=True)

    # ---- LAYER B -------------------------------------------------------------
    targets = {e["security_id"]: e for e in inwin}
    seen = {pv: {sid: [] for sid in targets} for pv in PORT_VALUE_SWEEP}
    picked = {pv: {sid: [] for sid in targets} for pv in PORT_VALUE_SWEEP}
    floors = {}
    convention = spec("percentile_convention")
    tie_break = spec("selection_tie_break")
    for i, period in enumerate(manifest, 1):
        panel, adv20 = panel_for(period)
        for pv in PORT_VALUE_SWEEP:
            # Full-universe eligibility: `select` takes the top N_target of ALL
            # eligible names, so the target set cannot be evaluated in isolation.
            res = eligibility.evaluate(
                panel, adv20, pv,
                risk_filters=eligibility.frozen_risk_filters(
                    allow_incomplete=False))
            floors[pv] = res.adv_floor
            hits = set(res.eligible) & set(targets)
            for sid in hits:
                seen[pv][sid].append(period["as_of"])
            if hits:
                scores = decision.score_eligible(panel, res.eligible,
                                                 convention=convention)
                for sid in set(decision.select(
                        scores, tie_break=tie_break)) & set(targets):
                    picked[pv][sid].append(period["as_of"])
        if i % 20 == 0 or i == len(manifest):
            print("  selection %3d/141  %s" % (i, period["as_of"]), flush=True)

    def hit(table, pv, e):
        return any(d <= e["effective_date"] for d in table[pv][e["security_id"]])

    layer_b = {}
    for pv in PORT_VALUE_SWEEP:
        for name, table in (("eligibility", seen), ("selection", picked)):
            can = [e for e in post if hit(table, pv, e)]
            pre_can = [e for e in pre if hit(table, pv, e)]
            key = "%s__port_value_%d" % (name, int(pv))
            layer_b[key] = {
                "bound": name,
                "adv_floor": floors.get(pv),
                "post_blocker_total": len(post),
                "post_blocker_possibly_exposable": len(can),
                "post_blocker_possibly_exposable_by_lineage": dict(
                    Counter(e["lineage"] for e in can)),
                "post_blocker_structurally_impossible": len(post) - len(can),
                "post_blocker_possibly_exposable_ids": sorted(
                    (e["security_id"], e["effective_date"], e["lineage"],
                     e["document_class"]) for e in can),
                "control_pre_blocker_admitted": len(pre_can),
                "control_pre_blocker_total": len(pre),
                "control_pre_blocker_actual_exposed": 0,
                "control_false_positive_rate": round(
                    len(pre_can) / max(len(pre), 1), 3),
                "control_reading": (
                    "Layer A proves 0 of the %d pre-blocker boundaries were "
                    "actually exposed. A bound that admits many of them is "
                    "weak; one that admits few has demonstrated discriminating "
                    "power on ground truth." % len(pre)),
            }
            print("LAYER B  %-11s pv=%9.0f | post admits %2d/%d | "
                  "control admits %2d/%d (truth 0)"
                  % (name, pv, len(can), len(post), len(pre_can), len(pre)),
                  flush=True)

    # ---- LAYER B2 · recency-bounded selection ---------------------------------
    # "ever selected at or before the boundary" spans up to twelve years, which
    # is why it admits 10 pre-blocker boundaries whose true exposure is 0. A
    # name is held AT a boundary only if it survived the last rebalances before
    # it, so the necessary condition is tightened to the last K decision
    # periods. K is validated on the control set, where the truth is known.
    as_ofs = [p["as_of"] for p in manifest]

    def within_last_k(table, pv, e, k):
        prior = [d for d in as_ofs if d <= e["effective_date"]]
        if not prior:
            return False
        cutoff = prior[-k] if len(prior) >= k else prior[0]
        return any(cutoff <= d <= e["effective_date"]
                   for d in table[pv][e["security_id"]])

    layer_b2 = {}
    for k in (1, 2, 3, 6, 12):
        for pv in PORT_VALUE_SWEEP:
            can = [e for e in post if within_last_k(picked, pv, e, k)]
            pre_can = [e for e in pre if within_last_k(picked, pv, e, k)]
            layer_b2["selection_last_%d__port_value_%d" % (k, int(pv))] = {
                "k_periods_before_boundary": k,
                "adv_floor": floors.get(pv),
                "post_blocker_possibly_exposable": len(can),
                "post_blocker_possibly_exposable_by_lineage": dict(
                    Counter(e["lineage"] for e in can)),
                "post_blocker_ids": sorted(
                    (e["security_id"], e["effective_date"], e["lineage"],
                     e["document_class"]) for e in can),
                "control_pre_blocker_admitted": len(pre_can),
                "control_pre_blocker_total": len(pre),
                "control_pre_blocker_actual_exposed": 0,
                "control_false_positive_rate": round(
                    len(pre_can) / max(len(pre), 1), 3),
            }
        c = layer_b2["selection_last_%d__port_value_%d"
                     % (k, int(min(PORT_VALUE_SWEEP)))]
        print("LAYER B2 last-%-2d periods | post admits %2d/%d | "
              "control admits %2d/%d (truth 0)"
              % (k, c["post_blocker_possibly_exposable"], len(post),
                 c["control_pre_blocker_admitted"], len(pre)), flush=True)

    # ---- LAYER D · EXACT, from actual replay state ---------------------------
    # §18.2: a 2017 share_multiplier = 0.2 capital reduction left fractional
    # claims that `int()` can never credit, so the securities carrying them sit
    # in the economic-interest domain permanently. 8913 was simply the first of
    # them to delist. Unlike Layers B/C this is read off the ACTUAL B0.7 replay
    # state, not a recomputed selection layer, so it is exact -- but only for
    # claims that had formed by the B0.7 terminal period. Claims created after
    # 2020-01 are unknowable until the replay passes 8913, so this layer cannot
    # narrow the acquisition universe either.
    pp = [json.loads(x) for x in open(B07_PROGRESS, encoding="utf-8")
          if x.strip()]
    ever_claim, current_claim = set(), set(pp[-1].get("claim_only_securities")
                                           or [])
    for row in pp:
        ever_claim |= set(row.get("claim_only_securities") or [])
    by_sid = {e["security_id"]: e for e in events}
    layer_d = {
        "source": "B0.7 retrospective diagnostic period_progress.jsonl",
        "evidence_class": "EXACT_FROM_ACTUAL_REPLAY_STATE",
        "periods_covered": [pp[0]["period"], pp[-1]["period"]],
        "claim_bearing_securities_ever": len(ever_claim),
        "claim_bearing_securities_at_terminal_period": len(current_claim),
        "intersection_with_the_158_ever": sorted(set(by_sid) & ever_claim),
        "intersection_with_the_158_at_terminal_period": sorted(
            set(by_sid) & current_claim),
        "scope_limit": ("proves only what had formed by the B0.7 terminal "
                        "period; it does NOT establish that no new claim "
                        "appears after 2020-01, and therefore does not narrow "
                        "the B0.8 acquisition universe"),
        "value": ("engineering risk -- it is stronger evidence than the "
                  "selection screen because it is actual replay state"),
    }
    print("LAYER D  claim-bearing ever %d / at terminal %d | in the 158: "
          "ever %s, terminal %s"
          % (len(ever_claim), len(current_claim),
             layer_d["intersection_with_the_158_ever"],
             layer_d["intersection_with_the_158_at_terminal_period"]),
          flush=True)

    strict = layer_b["selection__port_value_%d" % int(min(PORT_VALUE_SWEEP))]
    # The envelope is the UNION over the swept port_value levels: no single
    # level is the run's actual path, so taking one of them would narrow the
    # envelope on an assumption the census cannot support.
    union_ids = {}
    for key, blk in layer_b.items():
        if key.startswith("selection__"):
            for row in blk["post_blocker_possibly_exposable_ids"]:
                union_ids[row[0]] = tuple(row)
    out = {
        "record": "B0_W1_EXPOSURE_CENSUS",
        "purpose": ("bound how many holder-side reorganization boundaries the "
                    "portfolio can reach while holding, over the 141-period "
                    "window"),
        "is_selection_input": False,
        "used_to_scope_document_acquisition": False,
        "b0_8_acquisition_protocol_remains_uniform_over_158": True,
        "reconstruction_classifications_changed": 0,
        "ca_ledger_unchanged": True,
        "sealed_artefacts_written": 0,
        "nav_computed": False,
        "performance_computed": False,
        "gates_evaluated": False,
        "window": [lo, hi],
        "population_total": len(events),
        "population_in_window": len(inwin),
        "in_window_by_lineage": dict(Counter(e["lineage"] for e in inwin)),
        "in_window_by_document_class": dict(
            Counter(e["document_class"] for e in inwin)),
        "layer_a_deductive": layer_a,
        "layer_b_eligibility_bound": layer_b,
        "layer_b2_recency_bounded_selection": layer_b2,
        "layer_d_exact_claim_bearing_intersection": layer_d,
        "declared_limitations": [
            "successor securities credited by a prior reorganization are not "
            "captured by a selection-based necessary condition",
            "the selection layer is recomputed path-independently and does not "
            "reproduce the sealed run exactly (8913 spell opens 2017-03-01, "
            "recomputed target entry 2017-04-28)",
            "port_value swept only over 500k .. 4.0M",
        ],
        "recency_bound_rejected_because": (
            "8913's exposure at 2020-01-14 was two residual fractional claims "
            "from spells that ended 2017-08-01, thirty-one periods earlier; a "
            "last-K-periods condition is a false negative on the one known "
            "positive"),
        "result_class": "ENVELOPE_NOT_PROOF",
        "layer_c_engineering_priority_candidate_envelope": {
            "name": ("%d-event load-bearing candidate envelope under the "
                     "tested direct-selection assumptions"
                     % (len(union_ids) + 1)),
            "is_a_strict_upper_bound_on_exposure": False,
            "why_not": ("the three declared limitations are each a possible "
                        "false-negative source: successor securities never "
                        "pass through selection, the recomputed selection "
                        "layer is not the sealed portfolio path, and "
                        "port_value is swept only over a tested range"),
            "post_8913_events": len(post),
            "identified_under_tested_envelope": len(union_ids),
            "known_actual_blocker": {BLOCKER_SID: BLOCKER_DATE},
            "engineering_priority_candidate_set": len(union_ids) + 1,
            "members": sorted(union_ids.values(), key=lambda r: r[1]),
            "by_lineage": dict(Counter(v[2] for v in union_ids.values())),
            "by_document_class": dict(
                Counter(v[3] for v in union_ids.values())),
            "control_false_positive_rate_of_the_bound":
                strict["control_false_positive_rate"],
            "claim_this_does_NOT_support": (
                "only these events can ever block a replay"),
            "claim_this_DOES_support": (
                "these are the events most likely to be load-bearing, and "
                "therefore an engineering-priority ordering -- not a "
                "restriction of the canonical acquisition universe"),
            "canonical_acquisition_universe_unchanged": 158,
        },
        "eligibility_periods_by_security": {
            sid: len(v) for sid, v in
            sorted(seen[min(PORT_VALUE_SWEEP)].items()) if v},
        "selected_periods_by_security": {
            sid: len(v) for sid, v in
            sorted(picked[min(PORT_VALUE_SWEEP)].items()) if v},
        "selected_dates_by_security": {
            sid: v for sid, v in
            sorted(picked[min(PORT_VALUE_SWEEP)].items()) if v},
    }
    out["census_sha256"] = canonical_sha256(out)
    os.makedirs(HERE, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
