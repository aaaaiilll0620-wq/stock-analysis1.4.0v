# -*- coding: utf-8 -*-
"""B0.8 · D8.2B-R2 · STOCK-APPLICABILITY DENOMINATOR REPAIR.

D8.2B / D8.2B-R1 treated "document inspected, zero credit-date hits" as
negative evidence about successor-share credit dates without first checking
that the *event* the document belongs to is confirmed stock-bearing. A
zero-hit result on a CASH_ONLY or CONSIDERATION_UNKNOWN event says nothing
about successor-share credit dates -- there is no successor share.

This stage rebuilds the denominator: for every event referenced anywhere in
D8.2B-R1's evidence, freeze its CURRENT authoritative consideration class
(from D8.0/D7.4/D7.6, not re-derived), then keeps only CONFIRMED_STOCK_
BEARING events' documents as admissible negative evidence. Preserves
D8.2A/D8.2B/D8.2B-R1 unmodified.

Offline only: reads only already-cached artefacts and the already-cached
d7_6_edoc_raw PDFs (re-checking per-file readability, which is not new
acquisition -- the files were already fetched by D7.6). No OCR is run; the
Windows pypdf re-read below only reports which already-cached files fail to
extract text, it does not remediate them.

    python research/b0_8_holder_terms/successor_credit_source_family_coverage_d8_2b_r2.py
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

D80 = os.path.join(HERE, "extraction_readiness_freeze_d8_0.json")
D74 = os.path.join(HERE, "residual_consideration_closure_d7_4.json")
D76 = os.path.join(HERE, "disappearing_party_edoc_consideration_d7_6.json")
D82A = os.path.join(HERE, "credit_date_representability_gate_d8_2a.json")
D82B = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b.json")
D82B_R1 = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b_r1.json")
D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
D70C = os.path.join(HERE, "tdcc_public_access_feasibility_d7_0c.json")
REG = os.path.join(HERE, "event_register.json")
EDOC_AUDIT = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                          "d8_2b_r1_edoc_credit_date_audit.json")
OUT = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b_r2.json")

BANDS = (("2004-2009", 2004, 2009), ("2010-2014", 2010, 2014),
         ("2015-2019", 2015, 2019), ("2020-2026", 2020, 2026))


def band_of(date_str):
    y = int(date_str[:4])
    for name, lo, hi in BANDS:
        if lo <= y <= hi:
            return name
    return None


# Exact per-file readability re-check, 5384/5491 only (Windows pypdf,
# offline, already-cached files -- see D8.2B-R1's cache). Not re-derived
# generically here to keep this record self-contained and auditable; the
# raw per-file results are quoted directly.
EDOC_FILE_READABILITY = {
    "5384": {
        "5384_2016_5384_20160616F01.pdf": "OK",
        "5384_2016_5384_20160616F02.pdf": "OK",
        "5384_2016_5384_20160616F05.pdf": "EMPTY_TEXT",
        "5384_2016_5384_20160616F13.pdf": "OK",
        "5384_2016_5384_20160616F17.pdf": "OK",
        "5384_2017_5384_20170615F01.pdf": "OK",
        "5384_2017_5384_20170615F02.pdf": "OK",
        "5384_2017_5384_20170615F05.pdf": "EMPTY_TEXT",
        "5384_2017_5384_20170615F13.pdf": "OK",
        "5384_2017_5384_20170615F14.pdf": "OK",
        "5384_2017_5384_20170615F15.pdf": "OK",
        "5384_2017_5384_20170615F17.pdf": "OK",
    },
    "5491": {
        "5491_2016_5491_20160615F01.pdf": "OK",
        "5491_2016_5491_20160615F02.pdf": "ENCRYPTED_MISSING_CRYPTOGRAPHY_LIB",
        "5491_2016_5491_20160615F05.pdf": "ENCRYPTED_MISSING_CRYPTOGRAPHY_LIB",
        "5491_2016_5491_20160615F17.pdf": "EMPTY_TEXT",
        "5491_2017_5491_20170613F01.pdf": "OK",
        "5491_2017_5491_20170613F02.pdf": "OK",
    },
}

# d7_6_docs_raw: a SEPARATE cached corpus (already-extracted .txt/.extract.json
# sidecars) never inspected by D8.2A/D8.2B/D8.2B-R1. Listed here by filename
# only -- NOT opened or read in this pass ("do not inspect the larger
# formal-document corpus yet"). Files tied to a counterparty of a
# CONFIRMED_STOCK_BEARING event are flagged as requiring field audit; files
# tied only to still-CONSIDERATION_UNKNOWN events are not (non-diagnostic
# either way, so auditing them would not change the denominator).
D7_6_DOCS_RAW_INVENTORY = [
    {"file": "201709_3709_B07.pdf", "counterparty_of": "5384",
     "has_txt_sidecar": True, "has_extract_json": True},
    {"file": "201712_3710_B07.pdf", "counterparty_of": "5491",
     "has_txt_sidecar": True, "has_extract_json": False},
    {"file": "202002_3713_B07.pdf", "counterparty_of": "3562",
     "has_txt_sidecar": True, "has_extract_json": True},
]


def main() -> int:
    d80 = json.load(open(D80, encoding="utf-8"))
    d74 = json.load(open(D74, encoding="utf-8"))
    d76 = json.load(open(D76, encoding="utf-8"))
    d82a = json.load(open(D82A, encoding="utf-8"))
    d82b = json.load(open(D82B, encoding="utf-8"))
    d82b_r1 = json.load(open(D82B_R1, encoding="utf-8"))
    d66 = json.load(open(D66, encoding="utf-8"))
    d70c = json.load(open(D70C, encoding="utf-8"))
    reg = json.load(open(REG, encoding="utf-8"))
    edoc_audit = json.load(open(EDOC_AUDIT, encoding="utf-8"))

    eff = {e["security_id"]: e["effective_date"] for e in reg["events"]}
    sem = {e["security_id"]: e["consideration_semantics"]
          for e in d80["per_event"] if e["venue"] == "TPEX"}
    twse_stock_established = {r["security_id"] for r in d74["per_event"]
                              if r.get("result") == "STOCK_ONLY_ESTABLISHED"}
    resid_sem = {sid: v.get("semantics") for sid, v in d76["per_event"].items()}

    # ---- 1. freeze the applicable population -----------------------------
    def classify(sid, twse_stk003_basis=False):
        if sid == "4152":
            return "SCHEMA_OR_EVENT_CLASS_CONFLICT"
        s = sem.get(sid)
        r = resid_sem.get(sid)
        if s in ("STOCK_ONLY", "MIXED") or r == "STOCK_ONLY" \
                or sid in twse_stock_established or twse_stk003_basis:
            return "CONFIRMED_STOCK_BEARING"
        if s == "CASH_ONLY" or r == "CASH_ONLY":
            return "CONFIRMED_NON_STOCK"
        return "CONSIDERATION_UNKNOWN"

    # every event referenced in D8.2B-R1 evidence
    referenced = set()
    for c in d82a["per_control"]:
        referenced.add(c["security_id"])
    for sid in resid_sem:
        referenced.add(sid)
    for r in d66["results"]:
        if r.get("classification") == "STATIC_EVENT_DOCUMENT_UNIQUE":
            referenced.add(r["security_id"])

    twse_basis_ids = {c["security_id"] for c in d82a["per_control"]
                      if "TDCC STK003" in c["stock_basis"]}
    classification = {sid: classify(sid, sid in twse_basis_ids)
                      for sid in sorted(referenced)}
    denom_counts = {}
    for cls in classification.values():
        denom_counts[cls] = denom_counts.get(cls, 0) + 1

    # ---- 2. rebase prior document evidence --------------------------------
    rebased = []

    # family: successor-side MOPS (D8.2A's 17 controls)
    for c in d82a["per_control"]:
        sid = c["security_id"]
        cls = classification[sid]
        admissible = cls == "CONFIRMED_STOCK_BEARING"
        rebased.append({
            "event_id": sid, "family": "successor_side_MOPS_material_announcements",
            "band": c["band"], "current_consideration_class": cls,
            "same_transaction_linkage": c["result"] not in
                ("APPLICABLE_SOURCE_ROUTE_EXHAUSTED_NO_CREDIT_FIELD",),
            "document_readable": c.get("linked_docs", 0) > 0,
            "credit_date_audit_performed": True,
            "credit_date_result": c["result"],
            "negative_evidence_admissible": admissible,
            "disposition_if_not_admissible":
                None if admissible else "NON_DIAGNOSTIC_FOR_SUCCESSOR_CREDIT_DATE",
        })

    # family: MOPS e-doc archive rescan (D8.2B-R1's 7 residual events)
    for sid, rec in edoc_audit.items():
        cls = classification.get(sid, "CONSIDERATION_UNKNOWN")
        admissible = cls == "CONFIRMED_STOCK_BEARING"
        rebased.append({
            "event_id": sid, "family": "MOPS_electronic_document_archive",
            "band": band_of(eff[sid]), "current_consideration_class": cls,
            "same_transaction_linkage": rec.get("same_transaction_linked_pdfs", 0) > 0,
            "document_readable": rec.get("pdfs_read", 0) > 0,
            "credit_date_audit_performed": rec.get("cached_pdfs", 0) > 0,
            "credit_date_result": ("NO_SCOPED_HITS" if rec.get("pdfs_read", 0) > 0
                                   else "NO_CACHED_DOCUMENT"),
            "negative_evidence_admissible": admissible,
            "disposition_if_not_admissible":
                None if admissible else "NON_DIAGNOSTIC_FOR_SUCCESSOR_CREDIT_DATE",
        })

    # family: TPEx same-transaction records (D6.6's 39 unique-doc events)
    tpex_hit_ids = {h["security_id"] for h in d82b["family_by_period_coverage_matrix"][
        "TPEx_same_transaction_records"]["scope_check_detail"]}
    for r in d66["results"]:
        if r.get("classification") != "STATIC_EVENT_DOCUMENT_UNIQUE":
            continue
        sid = r["security_id"]
        cls = classification.get(sid, "CONSIDERATION_UNKNOWN")
        admissible = cls == "CONFIRMED_STOCK_BEARING"
        rebased.append({
            "event_id": sid, "family": "TPEx_same_transaction_records",
            "band": band_of(eff[sid]) if sid in eff else None,
            "current_consideration_class": cls,
            "same_transaction_linkage": True,
            "document_readable": True,
            "credit_date_audit_performed": True,
            "credit_date_result": ("FIELD_PRESENT_BUT_NON_STOCK"
                                   if sid in tpex_hit_ids else
                                   "FIELD_ABSENT"),
            "negative_evidence_admissible": admissible and sid not in tpex_hit_ids,
            "disposition_if_not_admissible":
                None if (admissible and sid not in tpex_hit_ids) else
                "NON_DIAGNOSTIC_FOR_SUCCESSOR_CREDIT_DATE",
        })

    admissible_negatives = [r for r in rebased if r["negative_evidence_admissible"]]
    non_diagnostic_removed = [r for r in rebased if not r["negative_evidence_admissible"]]

    # ---- 3. offline gaps ----------------------------------------------
    ocr_required = []
    for sid, files in EDOC_FILE_READABILITY.items():
        if classification.get(sid) != "CONFIRMED_STOCK_BEARING":
            continue
        for fn, status in files.items():
            if status != "OK":
                ocr_required.append({"event_id": sid, "file": fn, "status": status})

    cached_formal_docs_needing_audit = [
        {**d, "consideration_class": classification.get(d["counterparty_of"])}
        for d in D7_6_DOCS_RAW_INVENTORY
        if classification.get(d["counterparty_of"]) == "CONFIRMED_STOCK_BEARING"
    ]

    confirmed_stock_ids = {sid for sid, c in classification.items()
                           if c == "CONFIRMED_STOCK_BEARING"}
    has_doc_ids = {r["event_id"] for r in rebased
                  if r["credit_date_audit_performed"]}
    no_doc = sorted(confirmed_stock_ids - has_doc_ids)
    no_doc_events = [{"event_id": sid, "band": band_of(eff[sid]) if sid in eff else None}
                     for sid in no_doc]

    # ---- 4. TDCC applicability -----------------------------------------
    WIN_LO, WIN_HI = "2025-01-02", "2026-08-20"
    tdcc_applicable = sorted(sid for sid in confirmed_stock_ids
                             if sid in eff and WIN_LO <= eff[sid] <= WIN_HI)
    tdcc_window_status = ("NOT_APPLICABLE" if not tdcc_applicable
                          else "NOT_EVALUATED_FOR_THIS_FIELD")

    # ---- 5. corrected family-by-period matrix ----------------------------
    def band_bucket(records, family):
        out = {b[0]: [] for b in BANDS}
        for r in records:
            if r["family"] == family and r["band"] in out:
                out[r["band"]].append(r)
        return out

    fam1 = band_bucket(admissible_negatives, "successor_side_MOPS_material_announcements")
    fam3 = band_bucket(admissible_negatives, "MOPS_electronic_document_archive")
    fam5 = band_bucket(admissible_negatives, "TPEx_same_transaction_records")

    matrix = {}
    for band_name, _, _ in BANDS:
        matrix[band_name] = {
            "successor_side_MOPS_material_announcements": {
                "disposition": ("TRANSACTION_DOC_PRESENT_FIELD_ABSENT"
                                if fam1[band_name] else "NOT_EVALUATED_FOR_THIS_FIELD"),
                "admissible_events": [r["event_id"] for r in fam1[band_name]],
            },
            "disappearing_side_MOPS_material_announcements": {
                "disposition": "SOURCE_FAMILY_OR_ROUTE_NOT_ESTABLISHED",
                "note": "unchanged from D8.2B-R1 -- structural refusal, "
                        "not stock-applicability-dependent",
            },
            "MOPS_electronic_document_archive": {
                "disposition": ("PARTIAL_COVERAGE" if fam3[band_name]
                                else "NOT_EVALUATED_FOR_THIS_FIELD"),
                "admissible_events": [r["event_id"] for r in fam3[band_name]],
                "note": "only 5384/5491 (2015-2019) are CONFIRMED_STOCK_"
                        "BEARING among the 7 residual events; 3562/3582/"
                        "5818/6514/8705 removed as CONSIDERATION_UNKNOWN "
                        "-> NON_DIAGNOSTIC_FOR_SUCCESSOR_CREDIT_DATE",
            },
            "TWSE_same_transaction_records": {
                "disposition": "SOURCE_FAMILY_DOES_NOT_ENCODE_THIS_SEMANTIC",
                "note": "unchanged -- identified surface is a listing-"
                        "status feed regardless of stock-applicability",
            },
            "TPEx_same_transaction_records": {
                "disposition": ("TRANSACTION_DOC_PRESENT_FIELD_ABSENT"
                                if fam5[band_name] else "NOT_EVALUATED_FOR_THIS_FIELD"),
                "admissible_events": [r["event_id"] for r in fam5[band_name]],
                "note": "1787/3144 (the only 2 raw field.payment_or_credit_"
                        "date hits) removed -- both CONFIRMED_NON_STOCK",
            },
            "TDCC_surfaces": {
                "disposition": ("HISTORICAL_COVERAGE_UNAVAILABLE"
                                if band_name != "2020-2026" else
                                tdcc_window_status),
                "note": ("no part of this band reaches the OD-1-7/"
                         "PORTAL-QRYPS window" if band_name != "2020-2026"
                         else "1 confirmed-stock event (4945, 2025-09-02) "
                              "falls in the observed window; no query run"),
            },
            "issuer_or_surviving_company_formal_transaction_documents": {
                "disposition": "NOT_EVALUATED_FOR_THIS_FIELD",
                "note": "unchanged -- includes the newly-identified "
                        "d7_6_docs_raw cache for 5384/5491's counterparties, "
                        "not opened in this pass",
            },
        }

    out = {
        "record": "B0_8_D8_2B_R2_STOCK_APPLICABILITY_DENOMINATOR_REPAIR",
        "b0_8_state": "WIP, UNSEALED",
        "preserves_unmodified": [
            "credit_date_representability_gate_d8_2a.json",
            "successor_credit_source_family_coverage_d8_2b.json",
            "successor_credit_source_family_coverage_d8_2b_r1.json",
        ],
        "inputs": {
            "d8_2a_gate_sha256": d82a["gate_sha256"],
            "d8_2b_closure_sha256": d82b["closure_sha256"],
            "d8_2b_r1_closure_sha256": d82b_r1["closure_sha256"],
        },
        "applicable_population": {
            "events_referenced_in_d8_2b_r1_evidence": len(referenced),
            "classification": classification,
            "denominator_counts": denom_counts,
            "rule": "only CONFIRMED_STOCK_BEARING events may contribute "
                    "negative evidence about a missing successor credit date",
        },
        "rebased_document_evidence": rebased,
        "admissible_negative_count": len(admissible_negatives),
        "non_diagnostic_removed_count": len(non_diagnostic_removed),
        "non_diagnostic_removed": non_diagnostic_removed,
        "offline_gaps": {
            "OCR_REQUIRED_CONFIRMED_STOCK_DOCUMENTS": ocr_required,
            "CACHED_FORMAL_DOCS_REQUIRING_FIELD_AUDIT_FOR_CONFIRMED_STOCK_EVENTS":
                cached_formal_docs_needing_audit,
            "CONFIRMED_STOCK_EVENTS_WITH_NO_APPLICABLE_CACHED_DOCUMENT": no_doc_events,
            "3582_6514_excluded_reason": "CONSIDERATION_UNKNOWN -- not "
                "included merely because PDFs are listed on the e-doc "
                "surface; stock consideration not independently established",
        },
        "tdcc_applicability": {
            "observed_window": [WIN_LO, WIN_HI],
            "applicable_event_count": len(tdcc_applicable),
            "applicable_event_ids": tdcc_applicable,
            "TDCC_CURRENT_WINDOW": tdcc_window_status,
        },
        "family_by_period_coverage_matrix": matrix,
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
        "new_pdf_acquisition": False,
        "ocr_performed": False,
        "bulk_crawl": False,
        "d8_3_started": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("denominator_counts:", denom_counts)
    print("admissible_negative_count:", len(admissible_negatives))
    print("non_diagnostic_removed_count:", len(non_diagnostic_removed))
    print("OCR_REQUIRED_CONFIRMED_STOCK_DOCUMENTS:", len(ocr_required))
    print("CACHED_FORMAL_DOCS_REQUIRING_FIELD_AUDIT:", len(cached_formal_docs_needing_audit))
    print("CONFIRMED_STOCK_EVENTS_WITH_NO_APPLICABLE_CACHED_DOCUMENT:", no_doc)
    print("TDCC_CURRENT_WINDOW:", tdcc_window_status, tdcc_applicable)
    print("verdict:", out["source_family_closure_verdict"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
