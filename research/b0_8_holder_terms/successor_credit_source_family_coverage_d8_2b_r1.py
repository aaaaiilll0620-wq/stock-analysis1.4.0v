# -*- coding: utf-8 -*-
"""B0.8 · D8.2B-R1 · RECORD CORRECTION AND OFFLINE GAP AUDIT.

Corrects the D8.2B closure (successor_credit_source_family_coverage_d8_2b.json)
without rewriting it. Preserves D8.2A and D8.2B as-is; this is an additive
correction record.

Four corrections/additions, all offline (no network, no new acquisition):

  1. Control accounting relabelled: 16 primary stratified + 1 supplemental
     carried control (8420) = 17 total. Gate unchanged.
  2. Positive accounting: distinguishes VALIDATED_POSITIVES_IN_INSPECTED_
     APPLICABLE_MATERIAL (0) from families that were never actually
     evaluated for this field (which D8.2B wrongly folded into "0 positives
     across all seven families").
  3. Offline gap audit:
       A. Re-scans every already-cached MOPS t57sb01 PDF (D7.6's
          d7_6_edoc_raw cache, 45 files / 7 residual events) for
          holder-inbound successor-share credit-date semantics specifically
          -- D7.6 itself only classified consideration TYPE (cash/stock/
          mixed), never this field. Result cached at
          artifacts/b0_8_holder_terms/d8_2b_r1_edoc_credit_date_audit.json
          (produced separately under the Windows pypdf environment this
          repo's PDF tooling requires; reads only the existing cache, no
          network).
       B. Reinspects the 7 D7.5 SEMANTIC_UNKNOWN events against D7.6's
          CURRENT per_event state (later than D7.5's AB9 snapshot, which
          D8.2B incorrectly cited as still-current). D7.6 already resolved
          2 of the 7. This corrects D8.2B's "6 not exhausted vs 1
          exhausted" framing, which does not match either D7.5 or D7.6.
       C. Checks the frozen router registry (router_freeze_record.json
          primary_surfaces) for a TWSE surface distinct from MOPS/TDCC.
       D. Rebuilds the family-by-period matrix using genuine band-level
          evidence where it exists (D8.2A per_control bands, D6.6
          by_event_year_and_class + event_register.json dates for the two
          TPEx field hits, event_register.json dates for the 7 D7.6
          residuals) and NOT_EVALUATED where it does not.

    python research/b0_8_holder_terms/successor_credit_source_family_coverage_d8_2b_r1.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402

D82A = os.path.join(HERE, "credit_date_representability_gate_d8_2a.json")
D82B = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b.json")
D75 = os.path.join(HERE, "consideration_semantics_source_closure_d7_5.json")
D76 = os.path.join(HERE, "disappearing_party_edoc_consideration_d7_6.json")
D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
D70C = os.path.join(HERE, "tdcc_public_access_feasibility_d7_0c.json")
REG = os.path.join(HERE, "event_register.json")
ROUTER = os.path.join(HERE, "router_freeze_record.json")
EDOC_AUDIT = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                          "d8_2b_r1_edoc_credit_date_audit.json")
OUT = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b_r1.json")

BANDS = (("2004-2009", 2004, 2009), ("2010-2014", 2010, 2014),
         ("2015-2019", 2015, 2019), ("2020-2026", 2020, 2026))


def band_of(date_str):
    y = int(date_str[:4])
    for name, lo, hi in BANDS:
        if lo <= y <= hi:
            return name
    return None


def main() -> int:
    d82a = json.load(open(D82A, encoding="utf-8"))
    d82b = json.load(open(D82B, encoding="utf-8"))
    d75 = json.load(open(D75, encoding="utf-8"))
    d76 = json.load(open(D76, encoding="utf-8"))
    d66 = json.load(open(D66, encoding="utf-8"))
    d70c = json.load(open(D70C, encoding="utf-8"))
    reg = json.load(open(REG, encoding="utf-8"))
    router = json.load(open(ROUTER, encoding="utf-8"))
    edoc_audit = json.load(open(EDOC_AUDIT, encoding="utf-8"))

    eff = {e["security_id"]: e["effective_date"] for e in reg["events"]}

    # ---- 1. control accounting -------------------------------------------
    control_accounting = {
        "primary_stratified_controls": 16,
        "supplemental_carried_control": 1,
        "supplemental_carried_control_id": "8420",
        "total_diagnostic_controls": d82a["sampling"]["controls_selected"],
        "CONTROL_COUNT_DEVIATION": "17_vs_frozen_total_12_to_16",
        "gate_result": "NO_REPRODUCIBLE_POSITIVE_IN_BOUNDED_CONTROL_SET",
        "BULK_STOCK_ACQUISITION": d82a["BULK_STOCK_ACQUISITION"],
        "rerun_required": False,
    }

    # ---- 2. positive accounting --------------------------------------
    positive_accounting = {
        "VALIDATED_POSITIVES_IN_INSPECTED_APPLICABLE_MATERIAL": 0,
        "basis": "17 D8.2A controls (successor-side MOPS) + 45 cached "
                "MOPS t57sb01 PDFs for 5 of 7 D7.6 residual events + "
                "39 unique TPEx termination-bulletin bodies (D6.6) were "
                "actually inspected for this field. Zero scoped holder-"
                "inbound credit-date hits in any of them.",
        "families_NOT_folded_into_this_zero": [
            "disappearing_side_MOPS_material_announcements "
            "(SOURCE_FAMILY_OR_ROUTE_NOT_ESTABLISHED for this population)",
            "TWSE_same_transaction_records "
            "(route identified but does not encode this semantic)",
            "TDCC_surfaces for bands 2004-2009/2010-2014/2015-2019 "
            "(HISTORICAL_COVERAGE_UNAVAILABLE)",
            "issuer_or_surviving_company_formal_transaction_documents "
            "for ~52 of 59 events (NOT_EVALUATED_FOR_THIS_FIELD)",
            "2 of 7 D7.6 residual events (3582, 6514) with zero cached "
            "MOPS e-doc PDFs (NOT_EVALUATED_FOR_THIS_FIELD)",
        ],
    }

    # ---- 3A. MOPS t57sb01 offline credit-date audit ------------------
    edoc_by_band = {}
    resid_dates = {"3562": "2020-02-17", "5384": "2017-08-22",
                   "5491": "2017-12-19", "5818": "2007-11-23",
                   "8705": "2012-12-26", "3582": "2014-12-25",
                   "6514": "2024-10-09"}
    for sid, rec in edoc_audit.items():
        b = band_of(resid_dates[sid])
        edoc_by_band.setdefault(b, []).append({"security_id": sid, **rec})

    # ---- 3B. reinspect the 7 D7.5 SEMANTIC_UNKNOWN events vs D7.6 CURRENT state
    ab2 = d75["AB2_two_axis_results"]
    original_unknown = sorted(sid for sid, v in ab2.items()
                              if v.get("consideration_semantics") == "UNKNOWN")
    d76_current = {sid: d76["per_event"][sid]["result"]
                  for sid in original_unknown if sid in d76.get("per_event", {})}
    resolved = [sid for sid, r in d76_current.items()
               if r in ("STOCK_ONLY_ESTABLISHED", "CASH_ONLY_ESTABLISHED",
                        "MIXED_ESTABLISHED")]
    still_not_exhausted = [sid for sid, r in d76_current.items()
                           if r == "SOURCE_FAMILY_NOT_EXHAUSTED"]
    routing_error = [sid for sid, r in d76_current.items()
                     if r == "ROUTING_OR_ACQUISITION_ERROR"]
    genuine_boundary = [sid for sid, r in d76_current.items()
                        if r == "PUBLIC_AUTHORITATIVE_BOUNDARY"]

    reinspection_7_unknown = {
        "original_d7_5_semantic_unknown_count": len(original_unknown),
        "original_d7_5_semantic_unknown_events": original_unknown,
        "corrects_d8_2b_error": "D8.2B cited D7.5's AB9 snapshot (7 "
            "SEMANTIC_UNKNOWN, '6 not exhausted + 1 foreign boundary') as "
            "still current. D7.6 is a LATER stage in the same pipeline and "
            "already resolved 2 of the 7 (5384, 5491 -> STOCK_ONLY_"
            "ESTABLISHED). D8.2B also mis-cited 6514 as the exhausted "
            "PUBLIC_AUTHORITATIVE_BOUNDARY; D7.6's actual current per_event "
            "record shows 6514 = SOURCE_FAMILY_NOT_EXHAUSTED (113 docs "
            "listed on the e-doc surface, 0 scanned/cached) -- that "
            "docstring example in d7_6's own source was illustrative and "
            "does not match its own output.",
        "resolved_by_d7_6": resolved,
        "still_unresolved": sorted(still_not_exhausted + routing_error),
        "of_which_SOURCE_FAMILY_NOT_EXHAUSTED": sorted(still_not_exhausted),
        "of_which_ROUTING_OR_ACQUISITION_ERROR_distinct_from_exhaustion":
            sorted(routing_error),
        "of_which_genuine_PUBLIC_AUTHORITATIVE_BOUNDARY": sorted(genuine_boundary),
        "reading": "Per current cached state: 2 resolved, 4 SOURCE_FAMILY_"
            "NOT_EXHAUSTED (3562, 3582, 6514, 8705), 1 ROUTING_OR_"
            "ACQUISITION_ERROR (5818 -- listing_ok=false, an access "
            "failure, not an exhaustion state), 0 genuine exhausted "
            "boundaries. The premise of 'one exhausted event' is not "
            "supported by the artefacts as they currently stand.",
    }

    # ---- 3C. TWSE same-transaction family check against frozen registry
    primary_surfaces = router.get("primary_surfaces", [])
    twse_domain_surfaces = [s for s in primary_surfaces if "twse.com.tw" in s]
    non_mops_twse = [s for s in twse_domain_surfaces if "mopsov" not in s]
    twse_family_check = {
        "frozen_registry_file": "router_freeze_record.json",
        "primary_surfaces_in_registry": primary_surfaces,
        "twse_domain_surfaces": twse_domain_surfaces,
        "distinct_non_mops_twse_surface_identified": bool(non_mops_twse),
        "identified_surface": non_mops_twse[0] if non_mops_twse else None,
        "surface_function": ("delisted/suspended-security listing status "
                             "feed (suspendListingCsvAndHtml) -- not a "
                             "same-transaction / merger-consideration "
                             "document" if non_mops_twse else None),
        "reading": "A TWSE-domain, non-MOPS surface IS present in the "
            "frozen registry, so 'no route was ever identified' is false. "
            "But by its own name and function it is a listing/suspension "
            "status feed, structurally incapable of carrying holder-"
            "inbound consideration or credit-date content -- the correct "
            "disposition is SOURCE_FAMILY_DOES_NOT_ENCODE_THIS_SEMANTIC, "
            "not ROUTE_ERROR_OR_ACCESS_LIMITATION (D8.2B's prior labelling) "
            "and not SOURCE_FAMILY_OR_ROUTE_NOT_ESTABLISHED.",
    }

    # ---- family 1 (successor-side MOPS) per-band from D8.2A per_control --
    fam1_by_band = {}
    for c in d82a["per_control"]:
        fam1_by_band.setdefault(c["band"], []).append(
            {"security_id": c["security_id"], "venue": c["venue"],
             "result": c["result"]})

    # ---- family 5 (TPEx) band membership for the two field_presence hits -
    tpex_hits = d82b["family_by_period_coverage_matrix"][
        "TPEx_same_transaction_records"]["scope_check_detail"]
    tpex_hit_bands = {h["security_id"]: band_of(eff[h["security_id"]])
                      for h in tpex_hits}
    d66_years_with_unique_docs = set()
    for k, n in d66.get("by_event_year_and_class", {}).items():
        yr, cls = k.split("|", 1)
        if cls == "STATIC_EVENT_DOCUMENT_UNIQUE" and n > 0:
            d66_years_with_unique_docs.add(int(yr))

    def band_has_tpex_unique_docs(band_name):
        lo, hi = next((lo, hi) for n, lo, hi in BANDS if n == band_name)
        return any(lo <= y <= hi for y in d66_years_with_unique_docs)

    matrix = {}
    for band_name, _, _ in BANDS:
        matrix[band_name] = {
            "successor_side_MOPS_material_announcements": {
                "disposition": ("TRANSACTION_DOC_PRESENT_FIELD_ABSENT"
                                if fam1_by_band.get(band_name) else
                                "NOT_EVALUATED_FOR_THIS_FIELD"),
                "events_inspected": fam1_by_band.get(band_name, []),
            },
            "disappearing_side_MOPS_material_announcements": {
                "disposition": "SOURCE_FAMILY_OR_ROUTE_NOT_ESTABLISHED",
                "note": "structural, input-independent source refusal "
                        "(D7.0b-2) -- applies uniformly, not period-specific",
            },
            "MOPS_electronic_document_archive": {
                "disposition": ("PARTIAL_COVERAGE" if edoc_by_band.get(band_name)
                                else "NOT_EVALUATED_FOR_THIS_FIELD"),
                "events_inspected": edoc_by_band.get(band_name, []),
                "note": "covers only the 7 D7.5 residual events with cached "
                        "PDFs, not the full 59-event population",
            },
            "TWSE_same_transaction_records": {
                "disposition": "SOURCE_FAMILY_DOES_NOT_ENCODE_THIS_SEMANTIC",
                "note": "uniform: identified surface is a listing-status "
                        "feed regardless of period",
            },
            "TPEx_same_transaction_records": {
                "disposition": ("TRANSACTION_DOC_PRESENT_FIELD_ABSENT"
                                if band_has_tpex_unique_docs(band_name)
                                else "NOT_EVALUATED_FOR_THIS_FIELD"),
                "field_hits_in_band": [sid for sid, b in tpex_hit_bands.items()
                                       if b == band_name],
                "note": "D6.6 exhaustive census computed field_presence "
                        "for every candidate/qualifying body across all "
                        "bands; UNIQUE documents exist in every band per "
                        "by_event_year_and_class",
            },
            "TDCC_surfaces": {
                "disposition": ("HISTORICAL_COVERAGE_UNAVAILABLE"
                                if band_name != "2020-2026" else
                                "PARTIAL_COVERAGE"),
                "note": ("OD-1-7/PORTAL-QRYPS window starts 2025-01-02; no "
                         "part of this band is reachable"
                         if band_name != "2020-2026" else
                         "only the 2025-01-02..2026-08-20 slice of this "
                         "band is within the OD-1-7/PORTAL-QRYPS coverage "
                         "window, and no event-specific query was actually "
                         "executed against it here -- capability is "
                         "schema/coverage_range only"),
            },
            "issuer_or_surviving_company_formal_transaction_documents": {
                "disposition": "NOT_EVALUATED_FOR_THIS_FIELD",
                "note": "formal transaction documents were used (D7.4-D7.6) "
                        "to establish consideration TYPE, not re-examined "
                        "for a credit-DATE field, for the ~52 events "
                        "outside the D7.6 residual set audited above",
            },
        }

    out = {
        "record": "B0_8_D8_2B_R1_RECORD_CORRECTION_AND_OFFLINE_GAP_AUDIT",
        "b0_8_state": "WIP, UNSEALED",
        "preserves_unmodified": ["credit_date_representability_gate_d8_2a.json",
                                 "successor_credit_source_family_coverage_d8_2b.json"],
        "inputs": {
            "d8_2a_gate_sha256": d82a["gate_sha256"],
            "d8_2b_closure_sha256": d82b["closure_sha256"],
            "d7_5_closure_sha256": d75["closure_sha256"],
            "d7_6_closure_sha256": d76.get("closure_sha256"),
        },
        "control_accounting": control_accounting,
        "positive_accounting": positive_accounting,
        "gap_audit": {
            "A_mops_edoc_credit_date_rescan": {
                "method": "offline re-scan of cached t57sb01 PDFs, Windows "
                          "pypdf, no network, no new acquisition",
                "cache_source": "artifacts/b0_8_holder_terms/d7_6_edoc_raw "
                                "(45 files, 5 of 7 residual events; 3582 "
                                "and 6514 have zero cached PDFs)",
                "result_file": "artifacts/b0_8_holder_terms/"
                               "d8_2b_r1_edoc_credit_date_audit.json",
                "per_event": edoc_audit,
                "reading": "0 scoped holder-inbound credit-date hits, and "
                          "0 raw (unscoped) CREDIT_STRICT matches at all, "
                          "across 30 successfully-read same-transaction-"
                          "linked PDFs; 15 of 45 cached PDFs were "
                          "unreadable by pypdf (no extractable text layer "
                          "-- OCR-dependent, consistent with D7.6's own "
                          "AC8_ocr_dependent_classifications finding) and "
                          "were never actually text-inspected for this "
                          "field.",
            },
            "B_seven_unknown_reinspection": reinspection_7_unknown,
            "C_twse_family_registry_check": twse_family_check,
        },
        "family_by_period_coverage_matrix": matrix,
        "documents_events_actually_inspected": {
            "d8_2a_successor_side_MOPS_controls": 17,
            "mops_edoc_pdfs_read": sum(v.get("pdfs_read", 0)
                                      for v in edoc_audit.values()),
            "mops_edoc_pdfs_cached_but_unreadable": sum(
                v.get("pdfs_unreadable", 0) for v in edoc_audit.values()),
            "tpex_termination_bulletin_unique_bodies": 39,
        },
        "valid_positives": [],
        "not_evaluated_cells": [
            (band, fam) for band, fams in matrix.items()
            for fam, v in fams.items()
            if v["disposition"] == "NOT_EVALUATED_FOR_THIS_FIELD"
        ],
        "remaining_accessible_acquisition_gaps": [
            "3582 and 6514: MOPS e-doc archive lists documents "
            "(docs_on_edoc_surface=43 and 113) but none were ever fetched "
            "into cache -- fetching them would be new acquisition, not run here",
            "15 of 45 cached MOPS e-doc PDFs are OCR-dependent and unread",
            "TDCC OD-1-7/PORTAL-QRYPS: capability is schema/coverage_range "
            "only; no event-specific query executed even for the "
            "2025-01-02..present slice",
            "issuer/surviving-company formal transaction documents: ~52 of "
            "59 events never re-examined for a credit-date field "
            "specifically (only for consideration type)",
        ],
        "source_family_closure_verdict": "CLOSURE_BLOCKED_BY_COVERAGE_OR_ACCESS",
        "event_level_adjudication_admissible": False,

        # invariants
        "twse_99_bulk_acquisition_started": False,
        "canonical_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "frozen_schema_modified": False,
        "consumer_modified": False,
        "ca_ledger_or_states_changed": False,
        "dual_extraction_started": False,
        "network_used": False,
        "new_source_acquisition": False,
        "bulk_crawl": False,
        "d8_3_started": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("control_accounting:", control_accounting)
    print("positive_accounting.VALIDATED...:",
          positive_accounting["VALIDATED_POSITIVES_IN_INSPECTED_APPLICABLE_MATERIAL"])
    print("7-unknown reinspection ->", reinspection_7_unknown["reading"])
    print("TWSE family check ->", twse_family_check["reading"][:100], "...")
    print("verdict:", out["source_family_closure_verdict"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
