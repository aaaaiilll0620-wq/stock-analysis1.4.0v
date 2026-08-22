# -*- coding: utf-8 -*-
"""B0.8 · D7.5 · AB1-AB11 · FINAL CONSIDERATION SEMANTICS / SOURCE-FAMILY CLOSURE.

Governance correction adopted (AB2): consideration_semantics and acquisition_status
are separate axes. A public-authoritative data boundary explains WHY consideration
is unknown; it does not make the event non-stock. So 6514 is folded back into the
semantic-unknown set, and every residual carries both axes independently.

What D7.5 actually tested (the families D7.4 had left UNTESTED), and the outcome:

    holdco prospectus / annual-report family (5384, 5491, 3562)
        MOPS doc system (doc.twse.com.tw t57sb01) was driven end-to-end for
        3710: the annual-report PDFs are retrievable and pypdf-text-extractable
        (F02 = 70pp / 23,887 chars of real text, not an image). That PROVES the
        first-party document universe for these issuers is OPEN -- they are NOT
        data boundaries. But the specific same-transaction holder-consideration
        statement lives in the 股份轉換 公開說明書, whose retrieval returned an
        empty body on the flow used here; the annual-report/meeting files
        searched carried only generic governance boilerplate, not the 連展→連展
        投控 consideration. => family ACCESSIBLE, NOT exhausted (needs the
        prospectus doc-flow / OCR). acquisition_status = SOURCE_FAMILY_NOT_EXHAUSTED.

    nonpublic-survivor formal-filing family (5818, 8705, 3582)
        surviving/acquiring entities are unlisted (Citibank Taiwan, Stanley
        安防, Vishay 威世光電); their formal merger disclosures / regulatory
        approvals / shareholder circulars are not exposed on the programmatic
        first-party surfaces reachable here (MOPS/TWSE/TPEx openapi). Applicable
        but not yet retrieved. => SOURCE_FAMILY_NOT_EXHAUSTED. 2921 (D7.4) remains
        the positive control that a nonpublic successor is NOT automatically cash.

    foreign-successor family (6514)
        op-co 芮特-KY MOPS refused (delisted); no domestic successor; the foreign
        successor UMT Holdings (Samoa/Cayman) is a private holding company with no
        publicly-authoritative disclosure reachable on any TW first-party surface.
        Every applicable family is inapplicable or unavailable. => the one genuine
        acquisition_status = PUBLIC_AUTHORITATIVE_BOUNDARY.

No consideration grammar changed; no value materialised; PDF text was read only to
look for the holder-instrument class and same-transaction linkage.

    python research/b0_8_holder_terms/consideration_semantics_source_closure_d7_5.py
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

D74 = os.path.join(HERE, "residual_consideration_closure_d7_4.json")
OUT = os.path.join(HERE, "consideration_semantics_source_closure_d7_5.py".replace(".py", ".json"))

# starting semantic-unknown population (AB1): the D7.4 boundary(6514) folded back
STARTING_UNKNOWN = ["5384", "5491", "3562", "5818", "8705", "3582", "6514"]

# two-axis adjudication after D7.5 family testing (AB2/AB8)
RESID = {
    "5384": {"semantics": "UNKNOWN", "status": "SOURCE_FAMILY_NOT_EXHAUSTED",
             "survivor": "鑫聯大投控(3709)",
             "family_tested": "holdco annual-report retrievable & text-extractable "
                              "(not a boundary); 股份轉換 公開說明書 not yet retrieved",
             "untested_family": "SUCCESSOR_PROSPECTUS(股份轉換公開說明書)/OCR"},
    "5491": {"semantics": "UNKNOWN", "status": "SOURCE_FAMILY_NOT_EXHAUSTED",
             "survivor": "連展投控(3710)",
             "family_tested": "MOPS t57sb01 driven end-to-end: annual-report PDFs "
                              "retrievable, pypdf text OK (F02 70pp/23887 chars); "
                              "specific consideration in 公開說明書 (empty on this flow)",
             "untested_family": "SUCCESSOR_PROSPECTUS(股份轉換公開說明書)/OCR"},
    "3562": {"semantics": "UNKNOWN", "status": "SOURCE_FAMILY_NOT_EXHAUSTED",
             "survivor": "新晶投控(3713)",
             "family_tested": "holdco annual-report family accessible (not a boundary)",
             "untested_family": "SUCCESSOR_PROSPECTUS(股份轉換公開說明書)/OCR"},
    "5818": {"semantics": "UNKNOWN", "status": "SOURCE_FAMILY_NOT_EXHAUSTED",
             "survivor": "花旗(台灣)商業銀行(unlisted)",
             "family_tested": "successor MOPS N/A (unlisted); STK003 no coverage",
             "untested_family": "banking-regulator merger approval / formal filing"},
    "8705": {"semantics": "UNKNOWN", "status": "SOURCE_FAMILY_NOT_EXHAUSTED",
             "survivor": "台灣史丹利安防系統(unlisted)",
             "family_tested": "successor MOPS N/A (unlisted)",
             "untested_family": "surviving-entity formal disclosure / merger circular"},
    "3582": {"semantics": "UNKNOWN", "status": "SOURCE_FAMILY_NOT_EXHAUSTED",
             "survivor": "台灣威世光電(unlisted)",
             "family_tested": "successor MOPS N/A (unlisted)",
             "untested_family": "surviving-entity formal disclosure / merger circular"},
    "6514": {"semantics": "UNKNOWN", "status": "PUBLIC_AUTHORITATIVE_BOUNDARY",
             "survivor": "UMT Holdings (Samoa/Cayman, foreign private)",
             "family_tested": "op-co -KY MOPS refused; domestic families inapplicable; "
                              "foreign successor has no publicly-authoritative TW-"
                              "accessible disclosure (foreign family SOURCE_PUBLICLY_"
                              "UNAVAILABLE)",
             "untested_family": None},
}


def main() -> int:
    d74 = json.load(open(D74, encoding="utf-8"))
    assert set(STARTING_UNKNOWN) == set(RESID)

    newly_stock = [s for s in RESID if RESID[s]["semantics"] == "STOCK_ONLY"]
    newly_cash = [s for s in RESID if RESID[s]["semantics"] == "CASH_ONLY"]
    newly_mixed = [s for s in RESID if RESID[s]["semantics"] == "MIXED"]
    still_unknown = [s for s in RESID if RESID[s]["semantics"] == "UNKNOWN"]
    unknown_boundary = [s for s in still_unknown
                        if RESID[s]["status"] == "PUBLIC_AUTHORITATIVE_BOUNDARY"]
    unknown_not_exhausted = [s for s in still_unknown
                             if RESID[s]["status"] == "SOURCE_FAMILY_NOT_EXHAUSTED"]

    # AB1 base: STOCK_ONLY 27, MIXED 3, CASH_ONLY 22 (unchanged by D7.5)
    final_stock_only = 27 + len(newly_stock)
    final_mixed = 3 + len(newly_mixed)
    final_cash = 22 + len(newly_cash)
    stock_bearing_lower = final_stock_only + final_mixed
    stock_bearing_upper = stock_bearing_lower + len(still_unknown)

    out = {
        "record": "B0_8_D7_5_CONSIDERATION_SEMANTICS_SOURCE_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_4_closure_sha256": d74["closure_sha256"]},
        "AB1_starting_census": {
            "STOCK_ONLY": 27, "MIXED": 3, "CASH_ONLY": 22,
            "CONFIRMED_STOCK_BEARING": 30,
            "semantic_unknown_population": STARTING_UNKNOWN,
            "stock_bearing_lower_bound": 30, "stock_bearing_upper_bound": 37,
            "note": "6514 folded back into semantic-unknown (AB1/AB3): a boundary "
                    "is an acquisition_status, not a non-stock semantic verdict",
        },
        "AB2_two_axis_results": {
            s: {"consideration_semantics": RESID[s]["semantics"],
                "acquisition_status": RESID[s]["status"],
                "survivor": RESID[s]["survivor"],
                "family_tested_in_d7_5": RESID[s]["family_tested"],
                "remaining_untested_family": RESID[s]["untested_family"]}
            for s in STARTING_UNKNOWN},
        "AB8_boundary_audit": {
            "boundary_events": unknown_boundary,
            "criterion": "every applicable frozen first-party family tested-and-"
                         "absent/unavailable OR proven inapplicable; none left "
                         "UNTESTED or ROUTING_UNRESOLVED",
            "6514_qualifies": True,
            "holdco_and_nonpublic_do_NOT_qualify_reason": (
                "an applicable first-party family (holdco 股份轉換 公開說明書; "
                "unlisted-survivor formal/regulatory filing) remains retrievable "
                "in principle but not yet exhausted -- these are NOT boundaries"),
        },
        "AB9_denominator": {
            "FINAL_STOCK_ONLY": final_stock_only,
            "FINAL_MIXED": final_mixed,
            "FINAL_CONFIRMED_STOCK_BEARING": stock_bearing_lower,
            "FINAL_CONFIRMED_CASH_ONLY": final_cash,
            "FINAL_CONSIDERATION_SEMANTICS_UNKNOWN": len(still_unknown),
            "UNKNOWN_DUE_TO_PUBLIC_AUTHORITATIVE_BOUNDARY": len(unknown_boundary),
            "UNKNOWN_DUE_TO_SOURCE_FAMILY_NOT_EXHAUSTED": len(unknown_not_exhausted),
            "stock_bearing_lower_bound": stock_bearing_lower,
            "stock_bearing_upper_bound": stock_bearing_upper,
            "acquisition_workflow_closed": len(unknown_not_exhausted) == 0,
            "exact_stock_denominator_closed": len(still_unknown) == 0,
            "reading": ("exact stock denominator NOT closed: %d semantic-unknown "
                        "remain (%d source-family-not-exhausted + %d foreign "
                        "boundary). Acquisition workflow NOT closed while %d "
                        "families remain testable. Confirmed stock-bearing %d; "
                        "upper %d" % (len(still_unknown), len(unknown_not_exhausted),
                                      len(unknown_boundary), len(unknown_not_exhausted),
                                      stock_bearing_lower, stock_bearing_upper)),
        },
        "population_reconciliation": {
            "STOCK_ONLY": final_stock_only, "MIXED": final_mixed,
            "CASH_ONLY": final_cash, "SEMANTIC_UNKNOWN": len(still_unknown),
            "total": final_stock_only + final_mixed + final_cash + len(still_unknown),
        },

        # AB10 invariants
        "consideration_grammar_changed": False,
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
        "termination_branch_reopened": False,
        "cash_settlement_hunting": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "prior_artefacts_rewritten": 0,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    d = out["AB9_denominator"]
    print("newly stock/cash/mixed:", newly_stock, newly_cash, newly_mixed)
    print("still semantic-unknown :", len(still_unknown),
          "= boundary", len(unknown_boundary), "+ not-exhausted",
          len(unknown_not_exhausted))
    print("stock-bearing          : lower", d["stock_bearing_lower_bound"],
          "upper", d["stock_bearing_upper_bound"])
    print("acquisition closed?    :", d["acquisition_workflow_closed"])
    print("stock denominator closed?:", d["exact_stock_denominator_closed"])
    print("reconciliation total   :", out["population_reconciliation"]["total"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
