# -*- coding: utf-8 -*-
"""B0.8 · ADJUDICATION SUPPLEMENT to D7.0c. Read-only. No artefact rewritten.

WHY A SUPPLEMENT RATHER THAN A REWRITE

D7.0c recorded `n1_premise.independently_verified_by_d7_0c = false` because a
public search for 股款轉換價款支付一覽表 returned nothing at the time. That record
is correct as of when it was made and is NOT rewritten: an artefact that
retroactively acquires evidence it did not have is an artefact whose provenance
no longer means anything. Later evidence is carried here instead, at
adjudication level, with its own verification status stated per claim.

WHAT THIS SUPPLEMENT VERIFIED, AND WHAT IT COULD NOT

Two distinct claims were put forward in adjudication. They did not survive
verification equally, and collapsing them would overstate the record.

  VERIFIED · the operational function exists, from TDCC first-party material.
      TDCC's own 服務窗口 directory lists 股務部 as handling
      「現金對價股份轉換/合併銷帳、無實體退場作業」.
      Fetched from www.tdcc.com.tw and hashed here.

  NOT VERIFIED · the named record class 股款轉換價款支付一覽表.
      The cited procedure PDF returns HTTP 404 from both m.tdcc.com.tw and
      www.tdcc.com.tw on this network path, and a domain-scoped search of
      tdcc.com.tw does not surface the phrase. The document may well exist and
      be reachable elsewhere; this stage simply did not reach it, and says so
      rather than inheriting the claim.

THE LEVEL DISTINCTION THAT ADJUDICATION ITSELF DREW, KEPT INTACT

    an institutional record CLASS exists
        is not
    an inventory of 14 historical event-specific records exists

A 2026 procedure document -- or a 2026 service directory -- describes current
practice. It does not establish that each 2015..2026 event left a same-named,
same-format, retrievable record. So the event-level statement is confined to
what was actually tested: no public value was acquired.

WHAT D7.0c ESTABLISHED THAT NOTHING HERE WEAKENS

    cash settlement/payment date representable = 0 of 10 documented public
    TDCC surfaces

That is a schema-level absence across the whole tested registry, not fourteen
lookup misses. It is the strongest negative available short of an exhaustive
search of surfaces nobody has documented.

WHAT IS STILL NOT CLAIMED

    SETTLEMENT_DATE_DOES_NOT_EXIST          <- never asserted
    PUBLIC_TDCC_SETTLEMENT_DATE_SURFACE =
        NOT_IDENTIFIED_IN_TESTED_DOCUMENTED_PUBLIC_SURFACES   <- asserted

    python research/b0_8_holder_terms/adjudication_supplement_d7_0c.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402

D70C = os.path.join(HERE, "tdcc_public_access_feasibility_d7_0c.json")
D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_0c_tdcc_raw")
OUT = os.path.join(HERE, "adjudication_supplement_d7_0c.json")

SERVICE_WINDOW = "https://www.tdcc.com.tw/portal/zh/about/serviceWindow"
CITED_PDF = ("https://m.tdcc.com.tw/TDCCWEB/upload/"
             "402897958c90eab2018d115033b2008d.pdf")
UA = {"User-Agent": "Mozilla/5.0"}
RECORD_CLASS_NAME = "股款轉換價款支付一覽表"
FUNCTION_TEXT = "現金對價股份轉換"


def probe(url, save_as=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                    timeout=60) as r:
            body = r.read()
        if save_as:
            os.makedirs(RAW, exist_ok=True)
            with open(os.path.join(RAW, save_as), "wb") as fh:
                fh.write(body)
        return {"url": url, "reachable": True, "http_status": r.status,
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "text": body.decode("utf-8", "replace")}
    except Exception as exc:                                # noqa: BLE001
        return {"url": url, "reachable": False,
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:160])}


def main() -> int:
    d70c = json.load(open(D70C, encoding="utf-8"))
    d66 = json.load(open(D66, encoding="utf-8"))

    sw = probe(SERVICE_WINDOW, "ADJ_service_window.html")
    fn_present = sw.get("reachable") and FUNCTION_TEXT in sw.get("text", "")
    cls_in_sw = sw.get("reachable") and RECORD_CLASS_NAME in sw.get("text", "")
    pdf = probe(CITED_PDF)
    sw.pop("text", None)

    r8913 = [x for x in d66["results"] if x["security_id"] == "8913"][0]
    q = r8913["qualifying"][0]

    out = {
        "record": "B0_8_ADJUDICATION_SUPPLEMENT_TO_D7_0C",
        "b0_8_state": "WIP, UNSEALED",
        "supplements": {
            "artefact": os.path.relpath(D70C, REPO),
            "census_sha256": d70c["census_sha256"],
            "rewritten": False,
            "why_not_rewritten": (
                "D7.0c's independently_verified_by_d7_0c = false was true when "
                "recorded; back-filling evidence into a sealed-in-time record "
                "destroys the meaning of its provenance"),
        },

        # ---- tier 1 · the institutional record class -----------------------
        "TDCC_SETTLEMENT_RECORD_CLASS_ESTABLISHED": True,
        "record_class_evidence": {
            "operational_function_verified": bool(fn_present),
            "verified_from": SERVICE_WINDOW,
            "verified_text": ("股務部 · "
                              "現金對價股份轉換/合併銷帳、無實體退場作業"),
            "service_window_sha256": sw.get("sha256"),
            "named_record_class": RECORD_CLASS_NAME,
            "named_record_class_independently_verified": bool(cls_in_sw),
            "named_record_class_status": (
                "NOT_REACHED_BY_THIS_STAGE -- the cited procedure PDF returns "
                "404 from m.tdcc.com.tw and www.tdcc.com.tw on this network "
                "path, and a domain-scoped search does not surface the phrase"),
            "cited_pdf_probe": pdf,
            "reading": (
                "the FUNCTION is verified from TDCC first-party material; the "
                "NAMED document is carried from adjudication and is not "
                "independently confirmed here. The class-level conclusion "
                "stands on the verified function, not on the unverified name."),
        },

        # ---- tier 2 · public exposure of the value -------------------------
        "PUBLIC_SETTLEMENT_VALUE_EXPOSED_ON_TESTED_TDCC_SURFACES": False,
        "PUBLIC_TDCC_SETTLEMENT_DATE_SURFACE":
            "NOT_IDENTIFIED_IN_TESTED_DOCUMENTED_PUBLIC_SURFACES",
        "public_exposure_evidence": {
            "documented_surfaces_tested": len(d70c["surfaces"]),
            "surfaces_representing_a_cash_settlement_or_payment_date": 0,
            "basis": ("schema-level absence across the frozen registry, "
                      "assessed on field names before any event lookup"),
            "registry_sha256": d70c["n4_registry_sha256"],
        },
        "SETTLEMENT_DATE_DOES_NOT_EXIST": "NOT_ASSERTED",
        "why_not_asserted": (
            "absence from ten documented public surfaces is not absence from "
            "the world; undocumented surfaces, non-public channels and "
            "surfaces outside TDCC were not and could not be exhausted"),

        # ---- tier 3 · the event level, confined to what was tested ---------
        "EVENT_SPECIFIC_HISTORICAL_RECORD_EXISTENCE":
            "NOT_ESTABLISHED_BY_A_CURRENT_PROCEDURE_OR_DIRECTORY_DOCUMENT",
        "event_level_statement": {
            "population": d70c["population"]["count"],
            "EVENT_SPECIFIC_PUBLIC_AUTHORITATIVE_SETTLEMENT_VALUE_ACQUIRED":
                False,
            "for_all_events_in_the_population": True,
            "does_not_claim": (
                "that each of the 14 historical event-specific TDCC records has "
                "been shown to exist; what exists is proof of an institutional "
                "record class, not an inventory of 14 records"),
            "supersedes_the_wording_of": (
                "D7.0c's per-event "
                "AUTHORITATIVE_SETTLEMENT_RECORD_EXISTS_BUT_PUBLIC_VALUE_NOT_"
                "EXPOSED, at adjudication level only; the D7.0c artefact "
                "itself is unchanged"),
        },

        # ---- 8913, verified from preserved bytes ---------------------------
        "b8913_from_preserved_authoritative_bytes": {
            "document_number": q["document_number"],
            "static_url": q["static_url"],
            "body_sha256": q["body_sha256"],
            "payment_or_credit_date_present_on_the_body": q["field_presence"][
                "payment_or_credit_date"],
            "cash_consideration_present": q["field_presence"][
                "cash_consideration"],
            "holder_effective_or_conversion_date_present": q["field_presence"][
                "holder_effective_or_conversion_date"],
            "note": ("presence flags read from the D6.6 census, which assessed "
                     "the fetched official body; no value is materialised here"),
        },
        "critical_path_status": {
            "mops_company_body": "NOT_FEASIBLE (D7.0b-2)",
            "tpex_termination_body": "no payment/credit date (D6.6)",
            "tdcc_documented_public_surfaces":
                "no cash settlement/payment date field (D7.0c)",
            "frozen_semantics": ("§6.1.9 forbids discarding the fractional "
                                 "claim and forbids inventing a cash "
                                 "settlement; unreconstructable settlement "
                                 "semantics with exposure -> W-1 BLOCK "
                                 "(M-3 audit, verdict B)"),
            "consequence": ("on the frozen B0.8 source policy and schema, 8913 "
                            "remains NOT_RECONSTRUCTIBLE and the retrospective "
                            "replay remains blocked at 2020-01"),
            "this_is_a_data_boundary_not_a_retrieval_bug": True,
        },
        "third_party_mirrors_consulted": False,
        "noncanonical_value_known": False,
        "canonical_authoritative_value_acquired": False,

        # invariants
        "artefacts_rewritten": 0,
        "holder_terms_materialized": False,
        "values_extracted": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
    }
    out["supplement_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("service window reachable      :", sw.get("reachable"),
          "| function text present:", fn_present)
    print("named record class in that page:", cls_in_sw)
    print("cited procedure PDF           :",
          "reachable" if pdf.get("reachable") else pdf.get("error"))
    print("TDCC_SETTLEMENT_RECORD_CLASS_ESTABLISHED :",
          out["TDCC_SETTLEMENT_RECORD_CLASS_ESTABLISHED"])
    print("PUBLIC_SETTLEMENT_VALUE_EXPOSED          :",
          out["PUBLIC_SETTLEMENT_VALUE_EXPOSED_ON_TESTED_TDCC_SURFACES"])
    print("SETTLEMENT_DATE_DOES_NOT_EXIST           :",
          out["SETTLEMENT_DATE_DOES_NOT_EXIST"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
