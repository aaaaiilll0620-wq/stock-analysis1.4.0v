# -*- coding: utf-8 -*-
"""B0.8 · D8.2B · SUCCESSOR CREDIT-DATE SOURCE-FAMILY COVERAGE CLOSURE.

D8.2A established a gate result, not a family audit:

    BULK_STOCK_ACQUISITION = NO_GO
    CONFIRMED_SUCCESSOR_CREDIT_POSITIVES = 0

This stage does two things and keeps them separable:

  1. CORRECTS the D8.2A record -- discloses the three controls whose raw
     regex hits were withdrawn on scope re-check, why, and the 17-vs-16
     control-count deviation. No control is deleted retrospectively; the
     withdrawal evidence is re-derived here from the cached (offline, no
     network) MOPS bodies D8.2A already fetched.

  2. AUDITS, per first-party source family (NOT a bulk event crawl), whether
     that family represents an explicit holder-inbound successor-share
     credit/delivery date for the SAME merger/share-conversion transaction.
     This draws on prior B0.8 closures (D6.4-D6.6 TPEx, D7.0b-2/D7.6 MOPS,
     D7.0c/adjudication-supplement TDCC, D7.2b/D7.2c routing+presence,
     D7.5 consideration semantics) rather than re-crawling.

Nothing here materialises a canonical value, changes a reconstruction
classification, touches the CA ledger, or starts a bulk/dual extraction.

    python research/b0_8_holder_terms/successor_credit_source_family_coverage_d8_2b.py
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
import successor_side_history_and_presence_d7_2c as CR       # noqa: E402

D82A = os.path.join(HERE, "credit_date_representability_gate_d8_2a.json")
D72C = os.path.join(HERE, "successor_side_history_and_presence_d7_2c.json")
D76 = os.path.join(HERE, "disappearing_party_edoc_consideration_d7_6.json")
D75 = os.path.join(HERE, "consideration_semantics_source_closure_d7_5.json")
D70B2 = os.path.join(HERE, "mops_body_route_closure_d7_0b_2.json")
D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
D70C = os.path.join(HERE, "tdcc_public_access_feasibility_d7_0c.json")
ADJ_D70C = os.path.join(HERE, "adjudication_supplement_d7_0c.json")
OUT = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b.json")

# same scope machinery as D8.2A -- re-applied offline to the three withdrawn
# controls to produce disclosable, quoted evidence for the withdrawal.
CREDIT_STRICT = re.compile(
    r"帳簿劃撥|劃撥交付|劃撥配發|配發交付|交付新股|新股交付|發放新股|"
    r"新股發放|換發股份[^。]{0,4}?交付|股份交付")
DISQUALIFY = ("應賣", "交存", "公開收購", "轉換公司債", "可轉債", "債權人",
              "贖回", "賣回", "收購說明書")
WINDOW = 140
WITHDRAWN = [
    ("6008", "2883", "凱基證券股份有限公司"),
    ("4429", "4433", "聚紡股份有限公司"),
    ("8420", "8938", "明揚國際科技股份有限公司"),
]


def reverify_withdrawn():
    """Re-run the UNSCOPED credit regex against the same cached bodies D8.2A
    already fetched (no network) and show what it matched before scope
    disqualification removed it."""
    out = {}
    for sid, code, dn in WITHDRAWN:
        rows = []
        for y in CR.YEARS:
            yr, _hit, _av = CR.enum_year(code, y)
            rows.extend(yr)
        cands = [r for r in rows if any(v in r["subject"] for v in CR.TXN_VOCAB)
                 and not any(n in r["subject"] for n in CR.ACCOUNTING_NOISE)]
        stem = dn.replace("股份有限公司", "")
        hits = []
        for r in cands:
            body = CR.fetch_body(code, r)
            if not body:
                continue
            same = (dn and dn in body) or (stem and stem in body) or re.search(
                r"(?:代號|代碼)[：:\s]*" + re.escape(sid), body)
            if not same:
                continue
            for m in CREDIT_STRICT.finditer(body):
                lo = max(0, m.start() - WINDOW)
                win = body[lo:m.end() + WINDOW]
                disq = [d for d in DISQUALIFY if d in win]
                if disq:
                    hits.append({"subject": r["subject"][:60], "date": r["date"],
                                 "raw_match": m.group(0),
                                 "disqualifiers_in_window": disq,
                                 "window": win[:220]})
        if sid == "6008" or sid == "4429":
            reason = "DIFFERENT_CORPORATE_ACTION_TENDER_OFFER_DEPOSIT"
        else:
            reason = "DIFFERENT_CORPORATE_ACTION_CB_CONVERSION"
        out[sid] = {"successor_code": code, "raw_unscoped_hits": len(hits),
                     "withdrawal_reason": reason, "evidence": hits[:2]}
    return out


def tpex_credit_field_scope_check():
    """The two D6.6 TPEx termination-bulletin bodies with
    payment_or_credit_date=true (1787, 3144) both carry
    stock_consideration=false / cash_consideration=true -- i.e. the field
    present is a cash settlement/payment date, not a successor SHARE credit
    date, and is out of D8.2B section-5 scope regardless."""
    d66 = json.load(open(D66, encoding="utf-8"))
    out = []
    for r in d66["results"]:
        for bucket in ("candidates", "qualifying"):
            for c in r.get(bucket, []) or []:
                fp = c.get("field_presence") or {}
                if fp.get("payment_or_credit_date"):
                    out.append({"security_id": r.get("security_id"),
                                "field_presence": fp,
                                "in_scope_for_stock_credit":
                                    bool(fp.get("stock_consideration"))})
    # de-dup by security_id
    seen, dedup = set(), []
    for o in out:
        if o["security_id"] in seen:
            continue
        seen.add(o["security_id"])
        dedup.append(o)
    return dedup


def main() -> int:
    d82a = json.load(open(D82A, encoding="utf-8"))
    d72c = json.load(open(D72C, encoding="utf-8"))
    d76 = json.load(open(D76, encoding="utf-8"))
    d75 = json.load(open(D75, encoding="utf-8"))
    d70b2 = json.load(open(D70B2, encoding="utf-8"))
    d70c = json.load(open(D70C, encoding="utf-8"))
    adj_d70c = json.load(open(ADJ_D70C, encoding="utf-8"))

    withdrawn = reverify_withdrawn()
    tpex_scope = tpex_credit_field_scope_check()

    per_stratum_selected = {}
    for c in d82a["per_control"]:
        k = "%s|%s" % (c["venue"], c["band"])
        per_stratum_selected[k] = per_stratum_selected.get(k, 0) + 1

    d8_2a_correction = {
        "gate_result": "NO_REPRODUCIBLE_POSITIVE_IN_BOUNDED_CONTROL_SET",
        "BULK_STOCK_ACQUISITION": d82a["BULK_STOCK_ACQUISITION"],
        "CONFIRMED_SUCCESSOR_CREDIT_POSITIVES": len(d82a["positives"]),
        "withdrawn_positive_controls": withdrawn,
        "control_count_deviation": {
            "controls_selected": d82a["sampling"]["controls_selected"],
            "frozen_target_range": [12, 16],
            "reason": "TARGET=16 stratified round-robin selection, plus 8420 "
                      "appended unconditionally as the carried known control "
                      "(D8.2A sampling.8420_carried_as_known_control_not_"
                      "semantics_definer) since it was not drawn naturally "
                      "within the first 16",
        },
        "eligible_pool_by_stratum": d82a["sampling"]["by_stratum"],
        "selected_controls_by_stratum": per_stratum_selected,
        "per_event_outcomes": [
            {"security_id": c["security_id"], "venue": c["venue"],
             "band": c["band"], "successor_code": c["successor_code"],
             "result": c["result"],
             "carried_known_control": c.get("carried_known_control", False)}
            for c in d82a["per_control"]
        ],
        "does_not_establish": "global or event-level NOT_RECONSTRUCTIBLE",
    }

    family_matrix = {
        "successor_side_MOPS_material_announcements": {
            "route_available": True,
            "query_executed_successfully": True,
            "transaction_linked_records_returned": True,
            "full_text_available": True,
            "credit_delivery_field_expected_by_doc_type": True,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": "Full ROC 90-113 successor-side MOPS "
                "history enumerated (D7.2c), 301 candidate bodies fetched. "
                "One SUCCESSOR_CREDIT_FIELD_PRESENT hit (8420) was raised "
                "before scope-disqualification existed; re-verified here "
                "(offline, cached body) as a convertible-bond conversion "
                "procedure for 明揚一, not a merger share credit -- withdrawn.",
            "disposition": "TRANSACTION_DOC_PRESENT_FIELD_ABSENT",
            "basis_sha256": d72c.get("presence_sha256"),
        },
        "disappearing_side_MOPS_material_announcements": {
            "route_available": False,
            "query_executed_successfully": True,
            "transaction_linked_records_returned": False,
            "full_text_available": False,
            "credit_delivery_field_expected_by_doc_type": True,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": d70b2.get("verdict"),
            "disposition": "ROUTE_ERROR_OR_ACCESS_LIMITATION",
            "detail": d70b2.get("route_status"),
        },
        "MOPS_electronic_document_archive": {
            "route_available": True,
            "query_executed_successfully": True,
            "transaction_linked_records_returned": True,
            "full_text_available": True,
            "credit_delivery_field_expected_by_doc_type": True,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": "D7.6 tested this route (doc.twse.com.tw "
                "t57sb01, distinct from the material-announcement endpoint) "
                "for CONSIDERATION-TYPE existence (cash/stock/mixed) across "
                "the TPEX_59 population -- 54/59 reconciled, 5 not yet "
                "exhausted. It has NOT yet been re-scanned specifically for "
                "explicit holder-inbound credit-DATE semantics; this is a "
                "distinct not-yet-executed query against an already-reachable "
                "route, not a route or coverage failure.",
            "disposition": "NOT_YET_TESTED_FOR_THIS_FIELD",
            "disposition_note": "outside the D8.2B permitted taxonomy -- "
                "reported for transparency, not a closure disposition",
            "basis": d76.get("TPEX_59_final"),
        },
        "TWSE_same_transaction_records": {
            "route_available": None,
            "query_executed_successfully": False,
            "transaction_linked_records_returned": False,
            "full_text_available": False,
            "credit_delivery_field_expected_by_doc_type": None,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": "No first-party TWSE surface distinct "
                "from (a) MOPS material announcements, already audited "
                "above, and (b) TDCC's TWSE-scoped STK-series lists, "
                "already audited under TDCC below, has been identified or "
                "queried in prior B0.8 stages as a separate 'TWSE bulletin' "
                "family for this semantic.",
            "disposition": "ROUTE_ERROR_OR_ACCESS_LIMITATION",
        },
        "TPEx_same_transaction_records": {
            "route_available": True,
            "query_executed_successfully": True,
            "transaction_linked_records_returned": True,
            "full_text_available": True,
            "credit_delivery_field_expected_by_doc_type": True,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": "D6.6 exhaustive census of TPEx static "
                "termination bulletins: 39 unique event bodies, "
                "payment_or_credit_date present on only 2 (1787, 3144) -- "
                "both re-checked here and both have stock_consideration="
                "false / cash_consideration=true, i.e. a cash settlement "
                "date, not a successor share credit date; out of section-5 "
                "scope regardless.",
            "disposition": "TRANSACTION_DOC_PRESENT_FIELD_ABSENT",
            "field_presence_counts": {"payment_or_credit_date_hits": 2,
                                      "of_unique_bodies": 39,
                                      "in_scope_for_stock_credit": 0},
            "scope_check_detail": tpex_scope,
        },
        "TDCC_surfaces": {
            "route_available": True,
            "query_executed_successfully": True,
            "transaction_linked_records_returned": False,
            "full_text_available": True,
            "credit_delivery_field_expected_by_doc_type": True,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": "OD-1-7 (有價證券帳簿劃撥配發交付日期一覽表) "
                "and PORTAL-QRYPS carry a delivery/credit-date field by "
                "schema, but OD-1-7's observed coverage window is "
                "2025-01-02..present -- it does not reach any of the "
                "2004-2024 control vintages. SM-STK003 (合併換票一覽表) "
                "carries only 消滅公司/存續公司/換票比率 (D7.1b's reader); "
                "no delivery/credit-date column was found on inspection, "
                "so its D7.0c capable_of_settlement_or_credit_date=true "
                "flag is a schema-name heuristic not confirmed by content "
                "and should not be relied on without re-inspection. The "
                "adjudication supplement additionally establishes 0 of 10 "
                "documented TDCC public surfaces expose a settlement/"
                "payment date for the cash-leg case (8913), by the same "
                "schema-first method.",
            "disposition": "HISTORICAL_COVERAGE_UNAVAILABLE",
            "surfaces": [{"id": s["id"], "name": s["name"],
                          "capable_of_settlement_or_credit_date":
                              s.get("capable_of_settlement_or_credit_date"),
                          "coverage_range": s.get("coverage_range")}
                         for s in d70c.get("surfaces", [])],
        },
        "issuer_or_surviving_company_formal_transaction_documents": {
            "route_available": True,
            "query_executed_successfully": True,
            "transaction_linked_records_returned": True,
            "full_text_available": True,
            "credit_delivery_field_expected_by_doc_type": True,
            "explicit_holder_inbound_credit_date_found": False,
            "coverage_limitation": "D7.5's AB9 denominator: 30 confirmed "
                "stock-bearing of 59, but 7 remain SEMANTIC_UNKNOWN (6 "
                "source-family-not-exhausted -- holdco 股份轉換公開說明書 or "
                "unlisted-survivor formal/regulatory filing still "
                "retrievable in principle; 1 foreign public-authoritative "
                "boundary, 6514). Formal transaction documents (shareholder "
                "circulars, merger agreements) established CONSIDERATION "
                "TYPE for several events (D7.6 AC-series) but were not "
                "examined there for an explicit credit-DATE field.",
            "disposition": "TRANSACTION_DOC_PRESENT_FIELD_ABSENT",
            "basis": d75.get("AB9_denominator"),
        },
    }

    valid_positives = []  # none survive scope re-check anywhere in this pass

    verdict = "NO_PUBLIC_AUTHORITATIVE_REPRESENTATION_ESTABLISHED"
    blocked_families = [k for k, v in family_matrix.items()
                        if v["disposition"] in
                        ("HISTORICAL_COVERAGE_UNAVAILABLE",
                         "ROUTE_ERROR_OR_ACCESS_LIMITATION",
                         "NOT_YET_TESTED_FOR_THIS_FIELD")]
    if blocked_families:
        verdict = "CLOSURE_BLOCKED_BY_COVERAGE_OR_ACCESS"

    out = {
        "record": "B0_8_D8_2B_SUCCESSOR_CREDIT_DATE_SOURCE_FAMILY_COVERAGE_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {
            "d8_2a_gate_sha256": d82a["gate_sha256"],
            "d7_2c_presence_sha256": d72c.get("presence_sha256"),
            "d7_6_closure_sha256": d76.get("closure_sha256"),
            "d7_5_closure_sha256": d75.get("closure_sha256"),
            "d6_6_census_sha256": None,
        },
        "d8_2a_correction": d8_2a_correction,
        "family_by_period_coverage_matrix": family_matrix,
        "families_where_no_period_stratified_breakdown_exists": True,
        "families_reported_at_population_level_reason": "prior B0.8 closures "
            "(D6.x/D7.x) were run and reported at whole-population level, "
            "not stratified by the four D8.2A bands; re-stratifying would "
            "require a new pass, which this stage does not run "
            "(not a bulk crawl).",
        "valid_positives": valid_positives,
        "blocked_or_limited_families": blocked_families,
        "source_family_closure_verdict": verdict,
        "event_level_adjudication_admissible": False,
        "event_level_adjudication_admissible_reason": "3 of 7 families "
            "(disappearing-side MOPS material announcements, TWSE "
            "same-transaction records, and the not-yet-tested MOPS e-doc "
            "archive credit-date rescan) are not closed; D7.5's own "
            "denominator still carries 7 SEMANTIC_UNKNOWN events. A later "
            "adjudication rule may map completed family coverage to "
            "event-specific evidence once those are closed -- not here.",

        # structural findings preserved separately, unchanged
        "structural_exclusions_carried_unchanged": {
            "CASH_ONLY_settlement_acquisition": "SCHEMA_CONSUMER_CONFORMANCE_CONFLICT",
            "4152_elective": "SCHEMA_OR_EVENT_CLASS_CONFLICT",
        },

        # invariants
        "twse_99_bulk_acquisition_started": False,
        "canonical_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "frozen_schema_modified": False,
        "consumer_modified": False,
        "ca_ledger_or_states_changed": False,
        "dual_extraction_started": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("D8.2A correction: CONFIRMED_SUCCESSOR_CREDIT_POSITIVES =",
          d8_2a_correction["CONFIRMED_SUCCESSOR_CREDIT_POSITIVES"])
    print("withdrawn:", list(withdrawn.keys()))
    print("blocked/limited families:", blocked_families)
    print("SOURCE_FAMILY_CLOSURE_VERDICT:", verdict)
    print("event_level_adjudication_admissible: False")
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
