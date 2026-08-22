# -*- coding: utf-8 -*-
"""B0.8 · D8.2C · EXACT OFFLINE DOCUMENT AUDIT.

Closes the seven documents D8.2B-R2 left as open gaps. Offline throughout:

  - 2 cached formal-document sidecars (already-extracted .txt/.extract.json
    under d7_6_docs_raw) inspected directly -- no new acquisition.
  - 5 cached-but-unread MOPS e-doc PDFs processed:
      3 with an empty pypdf text layer -> images extracted via pypdf
        (already installed, no network) and OCR'd with the Windows OS's
        built-in Windows.Media.Ocr engine, zh-Hant-TW language (already
        present on this machine -- no install, no model fetch). Raw OCR
        output cached at artifacts/b0_8_holder_terms/d8_2c_ocr/
        edoc_ocr_results_utf8.txt. CJK OCR engines emit a space between
        every recognised character; multi-character compound terms are
        matched here only after that inter-character spacing is stripped.
      2 AES-encrypted -> passwordless decrypt attempted with already-
        installed pypdf; both fail (`cryptography` package, needed for
        AES, is not installed on this machine) -> ENCRYPTED_DOCUMENT_
        NOT_EXTRACTABLE_OFFLINE, not conflated with OCR failure.

Preserves D8.2A/D8.2B/D8.2B-R1/D8.2B-R2 unmodified.

    python research/b0_8_holder_terms/successor_credit_source_family_coverage_d8_2c.py
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

D82A = os.path.join(HERE, "credit_date_representability_gate_d8_2a.json")
D82B = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b.json")
D82B_R1 = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b_r1.json")
D82B_R2 = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2b_r2.json")
DOCS_RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_6_docs_raw")
OCR_CACHE = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d8_2c_ocr",
                         "edoc_ocr_results_utf8.txt")
OUT = os.path.join(HERE, "successor_credit_source_family_coverage_d8_2c.json")

CREDIT_STRICT = re.compile(
    r"帳簿劃撥|劃撥交付|劃撥配發|配發交付|交付新股|新股交付|發放新股|"
    r"新股發放|換發股份[^。]{0,4}?交付|股份交付")
NEVER = ("新股上市", "上市日期", "上櫃日期", "開始買賣", "掛牌",
         "合併基準日", "股份轉換基準日", "停止過戶")
TXN_LINK_TERMS = ("股份轉換", "投資控股", "換股比例")


def strip_inter_cjk_spaces(s: str) -> str:
    cjk = r"一-鿿"
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"(?<=[%s])[ \t]+(?=[%s])" % (cjk, cjk), "", s)
    return s


def main() -> int:
    d82a = json.load(open(D82A, encoding="utf-8"))
    d82b = json.load(open(D82B, encoding="utf-8"))
    d82b_r1 = json.load(open(D82B_R1, encoding="utf-8"))
    d82b_r2 = json.load(open(D82B_R2, encoding="utf-8"))

    # ---- 1. accounting reconciliation --------------------------------
    rebased = d82b_r2["rebased_document_evidence"]
    assert len(rebased) == 63, "expected 63 event-family records, got %d" % len(rebased)

    classification = d82b_r2["applicable_population"]["classification"]
    unique_events_by_class = {}
    for sid, cls in classification.items():
        unique_events_by_class.setdefault(cls, []).append(sid)
    unique_counts = {k: len(v) for k, v in unique_events_by_class.items()}
    assert sum(unique_counts.values()) == len(classification)

    def bucket(rec):
        if rec["current_consideration_class"] == "SCHEMA_OR_EVENT_CLASS_CONFLICT":
            return "SCHEMA_OR_EVENT_CLASS_CONFLICT"
        if rec["negative_evidence_admissible"]:
            return "ADMISSIBLE_NEGATIVE_EVIDENCE"
        if rec["current_consideration_class"] == "CONFIRMED_NON_STOCK":
            return "NON_DIAGNOSTIC_NON_STOCK"
        if rec["current_consideration_class"] == "CONSIDERATION_UNKNOWN":
            return "NON_DIAGNOSTIC_CONSIDERATION_UNKNOWN"
        return "OTHER_EXPLICIT_DISPOSITION"

    family_records_by_class = {}
    for r in rebased:
        b = bucket(r)
        family_records_by_class.setdefault(b, []).append(r["event_id"])
    family_record_counts = {k: len(v) for k, v in family_records_by_class.items()}
    total_check = sum(family_record_counts.values())
    reconciled = (total_check == 63)
    if not reconciled:
        print("ACCOUNTING DID NOT RECONCILE:", total_check, "!= 63 -- STOPPING")
        return 1

    # disappearing-side MOPS correction: family and 3 attempted routes
    # (legacy ajax_t05st01, v2 detail API, signed redirect) are established
    # in D7.0b-2; the disposition is access/coverage, not "not established"
    disappearing_side_correction = {
        "prior_disposition_d8_2b_r1_r2": "SOURCE_FAMILY_OR_ROUTE_NOT_ESTABLISHED",
        "corrected_disposition": "ROUTE_ERROR_OR_ACCESS_LIMITATION",
        "reason": "the MOPS material-announcement family is well-established "
                  "and D7.0b-2 documents 3 distinct attempted routes (R1 "
                  "legacy ajax_t05st01, R3 v2 detail API, R4 signed "
                  "redirect), all refused/dead for this population -- this "
                  "is an access/coverage failure on an established family, "
                  "not an unidentified route",
    }

    # ---- 2. audit the 2 cached formal-document sidecars -------------------
    formal_docs = {}
    for fn, event_id, cp_name in [
        ("201709_3709_B07.pdf", "5384", "鑫聯大投資控股"),
        ("201712_3710_B07.pdf", "5491", "連展投資控股"),
    ]:
        txt_path = os.path.join(DOCS_RAW, fn + ".txt")
        txt = open(txt_path, encoding="utf-8").read()
        same_txn = sum(txt.count(t) for t in TXN_LINK_TERMS) + txt.count(event_id)
        hits = []
        for m in CREDIT_STRICT.finditer(txt):
            lo, hi = max(0, m.start() - 60), m.end() + 80
            hits.append({"label": m.group(0), "window": txt[lo:hi][:200]})
        m2 = re.search(r"(?:%s)" % "|".join(TXN_LINK_TERMS), txt)
        sample_ctx = None
        if m2:
            lo, hi = max(0, m2.start() - 40), m2.end() + 60
            sample_ctx = txt[lo:hi].replace("\n", " ")
        formal_docs[fn] = {
            "event_id": event_id, "counterparty": cp_name,
            "source_document_identity": "confirmed -- own MOPS t57sb01 "
                "e-doc filing, path matches counterparty code (extract.json)",
            "same_canonical_transaction": same_txn > 0,
            "same_transaction_term_hits": same_txn,
            "confirmed_stock_bearing": classification.get(event_id) ==
                "CONFIRMED_STOCK_BEARING",
            "holder_inbound_direction": "successor/newco's own prospectus, "
                "股份轉換 share-for-share exchange context",
            "credit_date_hits": hits,
            "sample_linkage_context": sample_ctx,
            "result": ("VALID_SUCCESSOR_CREDIT_DATE_PRESENT" if hits else
                      "APPLICABLE_DOCUMENT_FIELD_ABSENT"),
        }

    # ---- 3. the 5 MOPS e-doc PDFs -----------------------------------------
    ocr_raw = open(OCR_CACHE, encoding="utf-8").read()
    ocr_nospace = strip_inter_cjk_spaces(ocr_raw)
    ocr_by_file = {}
    for chunk in ocr_nospace.split("=====FILE:")[1:]:
        name, body = chunk.split("=====\n", 1)
        ocr_by_file.setdefault(name.rsplit(".p", 1)[0], []).append(body)

    def scan(sid_key, label):
        body = "".join(ocr_by_file.get(sid_key, []))
        hits = []
        for m in CREDIT_STRICT.finditer(body):
            lo, hi = max(0, m.start() - 60), m.end() + 80
            hits.append({"label": m.group(0), "window": body[lo:hi][:200]})
        same_txn = sum(body.count(t) for t in TXN_LINK_TERMS)
        readable_chars = len(re.sub(r"[\s、。,.:：;；()（）0-9CDOB\-]", "", body))
        return {"label": label, "ocr_chars_total": len(body),
                "ocr_readable_cjk_chars": readable_chars,
                "same_transaction_term_hits": same_txn,
                "credit_date_hits": hits}

    d1 = scan("5384_2016_5384_20160616F05.pdf", "5384 FY2015 AGM minutes (2016-06-16)")
    d2 = scan("5384_2017_5384_20170615F05.pdf", "5384 FY2016 AGM minutes / 股份轉換 resolution (2017-06-15)")
    d3 = scan("5491_2016_5491_20160615F17.pdf", "5491 attachment F17 (2016-06-15), 1 page")

    ocr_results = {
        "5384_2016_5384_20160616F05.pdf": {
            **d1,
            "result": "DIFFERENT_TRANSACTION_OR_CORPORATE_ACTION",
            "reason": "27/27 pages OCR'd and read; zero mention of 股份轉換 "
                      "or the counterparty anywhere -- this is 5384's own "
                      "prior-year (FY2015) routine annual meeting (dividend "
                      "distribution, financial/audit reports, R&D status), "
                      "not the share-conversion transaction",
        },
        "5384_2017_5384_20170615F05.pdf": {
            **d2,
            "result": ("VALID_SUCCESSOR_CREDIT_DATE_PRESENT" if d2["credit_date_hits"]
                       else "APPLICABLE_DOCUMENT_FIELD_ABSENT"),
            "reason": "66/66 pages OCR'd and read; substantial 股份轉換 "
                      "board-resolution text confirmed (ratio, effective/"
                      "base-date clauses, OTC-delisting clause -- all "
                      "excluded date types per scope) but zero occurrence "
                      "of any accepted credit/delivery compound term",
        },
        "5491_2016_5491_20160615F17.pdf": {
            **d3,
            "result": "TEXT_EXTRACTION_UNAVAILABLE",
            "reason": "1/1 page OCR'd mechanically without engine error, "
                      "but output is unreadable noise ('CO、0 C.0 C*D "
                      "C.O一0543 0B……0') -- no substantive CJK text "
                      "recovered; likely a seal/signature or graphical "
                      "cover page, not a text page",
        },
        "5491_2016_5491_20160615F02.pdf": {
            "result": "ENCRYPTED_DOCUMENT_NOT_EXTRACTABLE_OFFLINE",
            "reason": "pypdf attempts passwordless (empty-password) "
                      "decrypt automatically on read; fails with "
                      "'cryptography>=3.1 is required for AES algorithm' "
                      "-- that package is not installed on this machine "
                      "and was not installed to fix this. Not a bypass "
                      "attempt (no password other than empty was tried) "
                      "and not an OCR failure (no text layer was ever "
                      "reached).",
        },
        "5491_2016_5491_20160615F05.pdf": {
            "result": "ENCRYPTED_DOCUMENT_NOT_EXTRACTABLE_OFFLINE",
            "reason": "same as F02 -- AES-encrypted, cryptography package "
                      "not installed",
        },
    }

    all_seven = {**{k: v["result"] for k, v in formal_docs.items()},
                **{k: v["result"] for k, v in ocr_results.items()}}
    valid_positives = [k for k, r in all_seven.items()
                       if r == "VALID_SUCCESSOR_CREDIT_DATE_PRESENT"]
    inspected_successfully = [k for k, r in all_seven.items()
                              if r in ("VALID_SUCCESSOR_CREDIT_DATE_PRESENT",
                                       "APPLICABLE_DOCUMENT_FIELD_ABSENT",
                                       "DIFFERENT_TRANSACTION_OR_CORPORATE_ACTION")]
    unreadable = [k for k, r in all_seven.items()
                 if r in ("TEXT_EXTRACTION_UNAVAILABLE",
                          "ENCRYPTED_DOCUMENT_NOT_EXTRACTABLE_OFFLINE")]

    # ---- 5. source-family matrix changes -----------------------------
    matrix = json.loads(json.dumps(d82b_r2["family_by_period_coverage_matrix"]))
    for band in matrix:
        matrix[band]["disappearing_side_MOPS_material_announcements"] = {
            "disposition": "ROUTE_ERROR_OR_ACCESS_LIMITATION",
            "note": disappearing_side_correction["reason"],
        }
    # MOPS e-doc archive, 2015-2019 band: 5384/5491 now individually resolved
    matrix["2015-2019"]["MOPS_electronic_document_archive"] = {
        "disposition": "TRANSACTION_DOC_PRESENT_FIELD_ABSENT",
        "admissible_events": ["5384", "5491"],
        "note": "D8.2C fully resolved both admissible residual events for "
                "this band: 5384 via 2017 AGM resolution text (OCR) + its "
                "counterparty's prospectus (formal doc), 5491 via its "
                "counterparty's prospectus (formal doc); the encrypted/"
                "unreadable 5491 e-doc files did not carry the only "
                "evidence for 5491 -- the prospectus did",
        "no_longer_partial_coverage_reason": "all admissible-event "
            "documents for this band are now either read or exhausted "
            "(2 encrypted, 1 illegible -- but 5491 was independently "
            "resolved via its formal prospectus, so the band closes "
            "field-absent rather than partial)",
    }

    out = {
        "record": "B0_8_D8_2C_EXACT_OFFLINE_DOCUMENT_AUDIT",
        "b0_8_state": "WIP, UNSEALED",
        "preserves_unmodified": [
            "credit_date_representability_gate_d8_2a.json",
            "successor_credit_source_family_coverage_d8_2b.json",
            "successor_credit_source_family_coverage_d8_2b_r1.json",
            "successor_credit_source_family_coverage_d8_2b_r2.json",
        ],
        "inputs": {"d8_2b_r2_closure_sha256": d82b_r2["closure_sha256"]},
        "accounting_reconciliation": {
            "reconciled": reconciled,
            "UNIQUE_EVENTS_BY_CONSIDERATION_CLASS": unique_counts,
            "unique_events_detail": unique_events_by_class,
            "EVENT_FAMILY_RECORDS_BY_CONSIDERATION_CLASS": family_record_counts,
            "event_family_records_detail": family_records_by_class,
            "total_family_records": total_check,
            "disappearing_side_mops_correction": disappearing_side_correction,
        },
        "formal_document_sidecar_audit": formal_docs,
        "mops_edoc_pdf_processing": {
            "method": {
                "empty_text_layer_files": "pypdf image extraction (already "
                    "installed) -> Windows.Media.Ocr, zh-Hant-TW (OS-"
                    "resident language pack, no install/model fetch)",
                "encrypted_files": "passwordless pypdf decrypt attempt only",
                "ocr_cache": "artifacts/b0_8_holder_terms/d8_2c_ocr/"
                             "edoc_ocr_results_utf8.txt",
                "cjk_ocr_spacing_note": "the OCR engine emits a space "
                    "between every recognised CJK character; compound-term "
                    "matching is performed only after stripping spaces "
                    "between adjacent CJK characters",
            },
            "per_document": ocr_results,
        },
        "per_document_result": all_seven,
        "valid_positives": valid_positives,
        "documents_inspected_successfully": inspected_successfully,
        "documents_unreadable": unreadable,
        "documents_unreadable_reasons": {
            "5491_2016_5491_20160615F17.pdf": "TEXT_EXTRACTION_UNAVAILABLE",
            "5491_2016_5491_20160615F02.pdf": "ENCRYPTED_DOCUMENT_NOT_EXTRACTABLE_OFFLINE",
            "5491_2016_5491_20160615F05.pdf": "ENCRYPTED_DOCUMENT_NOT_EXTRACTABLE_OFFLINE",
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
        "software_installed": False,
        "language_models_fetched": False,
        "encryption_bypassed": False,
        "3582_6514_fetched": False,
        "d8_3_started": False,
        "bulk_crawl": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("accounting reconciled:", reconciled, "| total:", total_check)
    print("UNIQUE_EVENTS_BY_CONSIDERATION_CLASS:", unique_counts)
    print("EVENT_FAMILY_RECORDS_BY_CONSIDERATION_CLASS:", family_record_counts)
    print("documents inspected successfully:", inspected_successfully)
    print("documents unreadable:", unreadable)
    print("valid positives:", valid_positives)
    print("verdict:", out["source_family_closure_verdict"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
