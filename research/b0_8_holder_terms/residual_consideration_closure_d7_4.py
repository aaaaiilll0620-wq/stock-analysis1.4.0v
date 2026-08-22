# -*- coding: utf-8 -*-
"""B0.8 · D7.4 · AA1-AA13 · RESIDUAL CONSIDERATION / EVENT-CLASS CLOSURE.

D7.3 left 10 residual events labelled CONSIDERATION_STILL_NOT_ESTABLISHED and
loosely called a public-authoritative boundary. That was premature: D7.3 tested
essentially one first-party family (successor-side MOPS 重大訊息). This stage does
what AA5/AA6/AA10 require -- test every APPLICABLE first-party family per event and
only call a boundary when the applicable families are genuinely exhausted -- and
audits event-class applicability (AA2/AA3) before searching for consideration.

WHAT ACTUALLY MOVED, and why (all first-party, no new grammar, no inference)

    6178  the sparse termination notice named no counterparty, so D7.3 treated it
          as possibly non-reorganization. TDCC STK003 (an already-held first-party
          family never applied to the residuals) records it as a share exchange
          into 詮鼎科技(6159): 每1.33股振遠 -> 1股詮鼎. STOCK. Not a membership
          conflict -- it is a genuine share-conversion merger.
    2921  STK003 records 轉換為特力屋 (a 未上市 issuer). Holder receives a security
          of a non-public issuer. STOCK, issuer NONPUBLIC.
    6008  survivor 中華開發金控 is absent from the current directory because it
          renamed. MOPS basic-info (t05st03) authoritatively records code 2883's
          前名稱 = 中華開發金融控股股份有限公司 -- first-party rename lineage
          (AA4). 2883's own same-transaction filings give the canonical exit:
          股份轉換, 每1股凱基證券換發本公司1.2股 (STOCK); the earlier 公開收購
          (每股10元現金) was a precursor tender, not the exit consideration.

    The rest remain unresolved but are NOT one common data boundary: they split
    into event-class N/A checks (none survived), source-families-not-exhausted
    (the 投控 prospectus family; unlisted-survivor formal filings), and a single
    genuine foreign-successor boundary (6514).

    python research/b0_8_holder_terms/residual_consideration_closure_d7_4.py
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
import successor_identity_routing_d7_1b as D71B              # noqa: E402

D73 = os.path.join(HERE, "holder_consideration_gap_closure_d7_3.json")
OUT = os.path.join(HERE, "residual_consideration_closure_d7_4.json")

# Frozen first-party source families (AA5)
FAMILIES = ["TDCC_STK003_MERGER_EXCHANGE_TABLE",
            "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT",
            "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE",
            "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT",
            "FOREIGN_ISSUER_PUBLIC_DISCLOSURE"]

# Per-event adjudication, each cell carries a first-party test outcome (AA6).
# Evidence strings are the authoritative source text located during D7.4; values
# (ratios/amounts) are quoted only to fix the INSTRUMENT CLASS, never canonicalised.
ADJUDICATION = {
    "6178": {
        "disappearing": "振遠科技", "survivor": "詮鼎科技", "survivor_code": "6159",
        "result": "STOCK_ONLY_ESTABLISHED", "holder_security": True,
        "holder_cash": False,
        "issuer_status": "PUBLIC_SECURITY_ID_ESTABLISHED",
        "evidence_family": "TDCC_STK003_MERGER_EXCHANGE_TABLE",
        "evidence": "STK003 換票比率: 股份轉換為詮鼎科技，每1.33股振遠換詮鼎1股",
        "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
        "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "APPLICABLE_AND_TESTED",
                   "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "NOT_REACHED_RESOLVED_EARLIER",
                   "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "APPLICABLE_AND_TESTED",
                   "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "NOT_APPLICABLE",
                   "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},
    "2921": {
        "disappearing": "特力和樂", "survivor": "特力屋", "survivor_code": None,
        "result": "STOCK_ONLY_ESTABLISHED", "holder_security": True,
        "holder_cash": False,
        "issuer_status": "NONPUBLIC_SECURITY_ISSUER",
        "evidence_family": "TDCC_STK003_MERGER_EXCHANGE_TABLE",
        "evidence": "STK003 換票比率: 轉換為特力屋 (未上市興櫃公司); "
                    "listing_date NOT_APPLICABLE, holder still receives a security",
        "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
        "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "APPLICABLE_AND_TESTED",
                   "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "NOT_APPLICABLE",
                   "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "APPLICABLE_AND_TESTED",
                   "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "NOT_APPLICABLE",
                   "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},
    "6008": {
        "disappearing": "凱基證券", "survivor": "中華開發金控→凱基金控",
        "survivor_code": "2883",
        "result": "STOCK_ONLY_ESTABLISHED", "holder_security": True,
        "holder_cash": False,
        "issuer_status": "PUBLIC_SECURITY_ID_ESTABLISHED_VIA_RENAME_LINEAGE",
        "evidence_family": "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT",
        "evidence": "MOPS t05st03 前名稱=中華開發金融控股 (code 2883); 2883 filing: "
                    "股份轉換 每1股凱基證券換發本公司1.2股 (STOCK). Precursor 公開收購 "
                    "每股10元現金 is a tender, not the exit consideration",
        "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
        "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                   "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "APPLICABLE_AND_TESTED",
                   "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "APPLICABLE_AND_TESTED",
                   "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "NOT_REACHED_RESOLVED_EARLIER",
                   "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},

    # ---- 投控 reorganizations: successor 重大訊息 exhausted; prospectus untested
    "5384": {"disappearing": "捷元", "survivor": "鑫聯大投控", "survivor_code": "3709",
             "result": "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "successor 重大訊息 tested: only post-formation admin "
                         "notices, no 換股比例; op-co MOPS refused; prospectus/"
                         "annual-report family applicable but untested (PDF)",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "APPLICABLE_AND_TESTED",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "APPLICABLE_AND_TESTED",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "APPLICABLE_NOT_YET_TESTED",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},
    "5491": {"disappearing": "連展", "survivor": "連展投控", "survivor_code": "3710",
             "result": "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "successor 重大訊息 tested (only setup/admin notices); "
                         "prospectus/annual-report family applicable but untested",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "APPLICABLE_AND_TESTED",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "APPLICABLE_AND_TESTED",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "APPLICABLE_NOT_YET_TESTED",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},
    "3562": {"disappearing": "頂晶", "survivor": "新晶投控", "survivor_code": "3713",
             "result": "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "successor 重大訊息 tested (only setup/admin notices); "
                         "prospectus/annual-report family applicable but untested",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "APPLICABLE_AND_TESTED",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "APPLICABLE_AND_TESTED",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "APPLICABLE_NOT_YET_TESTED",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},

    # ---- unlisted domestic survivors: no successor MOPS; formal-filing untested
    "5818": {"disappearing": "華僑商業銀行", "survivor": "花旗(台灣)商業銀行",
             "survivor_code": None,
             "result": "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "survivor unlisted (Citibank Taiwan); successor MOPS "
                         "N/A; STK003 does not cover this bank merger; banking-"
                         "regulator/formal-filing family untested",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_GAP_WITHIN_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "NOT_APPLICABLE",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "ROUTING_UNRESOLVED",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "APPLICABLE_NOT_YET_TESTED",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},
    "8705": {"disappearing": "東隆五金", "survivor": "台灣史丹利安防系統",
             "survivor_code": None,
             "result": "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "survivor unlisted; successor MOPS N/A; STK003 outside "
                         "vintage; surviving-issuer formal-filing family untested",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "NOT_APPLICABLE",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "ROUTING_UNRESOLVED",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "APPLICABLE_NOT_YET_TESTED",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},
    "3582": {"disappearing": "凌耀科技", "survivor": "台灣威世光電",
             "survivor_code": None,
             "result": "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "survivor unlisted; successor MOPS N/A; STK003 outside "
                         "vintage; surviving-issuer formal-filing family untested",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "NOT_APPLICABLE",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "ROUTING_UNRESOLVED",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "APPLICABLE_NOT_YET_TESTED",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "NOT_APPLICABLE"}},

    # ---- genuine foreign-successor boundary
    "6514": {"disappearing": "芮特-KY", "survivor": "UMT Holdings (Samoa)",
             "survivor_code": None,
             "result": "CONSIDERATION_PUBLIC_AUTHORITATIVE_BOUNDARY",
             "holder_security": None, "holder_cash": None,
             "event_class": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
             "evidence": "survivor is a foreign (Samoa/Cayman) holding company; "
                         "every applicable TW first-party family is NOT_APPLICABLE "
                         "or unavailable (op-co -KY MOPS refused; STK003 outside "
                         "vintage; no domestic successor; foreign disclosure not "
                         "publicly authoritative on any accessible TW surface)",
             "matrix": {"TDCC_STK003_MERGER_EXCHANGE_TABLE": "COVERAGE_OUTSIDE_EVENT_VINTAGE",
                        "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT": "NOT_APPLICABLE",
                        "TWSE_TPEX_DIRECTORY_AND_RENAME_LINEAGE": "NOT_APPLICABLE",
                        "SUCCESSOR_PROSPECTUS_OR_ANNUAL_REPORT": "NOT_APPLICABLE",
                        "FOREIGN_ISSUER_PUBLIC_DISCLOSURE": "SOURCE_PUBLICLY_UNAVAILABLE"}},
}


def main() -> int:
    d73 = json.load(open(D73, encoding="utf-8"))
    residual = [r["security_id"] for r in d73["per_event"]
                if r["result"] == "CONSIDERATION_STILL_NOT_ESTABLISHED"]
    assert set(residual) == set(ADJUDICATION), (residual, list(ADJUDICATION))

    # ---- confirm the STK003-based resolutions from the held first-party file
    stk = D71B.stk003_control()
    stk003_check = {}
    for sid in ("6178", "2921"):
        c = stk.get(sid)
        stk003_check[sid] = {"in_stk003": bool(c),
                             "survivor_raw": c["survivor_raw"] if c else None,
                             "exchange_ratio": c["exchange_ratio"] if c else None}

    per_event, tax = [], {}
    for sid in residual:
        a = ADJUDICATION[sid]
        tax[a["result"]] = tax.get(a["result"], 0) + 1
        per_event.append({"security_id": sid, **a})

    newly_stock = [s for s in residual
                   if ADJUDICATION[s]["result"] == "STOCK_ONLY_ESTABLISHED"]
    newly_cash = [s for s in residual
                  if ADJUDICATION[s]["result"] == "CASH_ONLY_ESTABLISHED"]
    newly_mixed = [s for s in residual
                   if ADJUDICATION[s]["result"] == "MIXED_ESTABLISHED"]
    not_applicable = [s for s in residual
                      if ADJUDICATION[s]["result"] == "CONSIDERATION_NOT_APPLICABLE"]
    boundary = [s for s in residual
                if ADJUDICATION[s]["result"]
                == "CONSIDERATION_PUBLIC_AUTHORITATIVE_BOUNDARY"]
    not_exhausted = [s for s in residual
                     if ADJUDICATION[s]["result"]
                     == "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED"]
    membership = [s for s in residual
                  if ADJUDICATION[s]["result"] == "EVENT_CLASS_MEMBERSHIP_UNRESOLVED"]

    # ---- AA11 · final denominator (from the D7.2.1 base + D7.3 + D7.4) ----
    base_stock_only = 24     # D7.2.1 STOCK_ONLY 22 + D7.3 new 2
    base_mixed = 3
    base_cash = 22
    final_stock_only = base_stock_only + len(newly_stock)
    final_mixed = base_mixed + len(newly_mixed)
    final_cash = base_cash + len(newly_cash)
    final_stock_bearing = final_stock_only + final_mixed
    remaining_true_unknown = len(not_exhausted) + len(membership)
    # boundary and N/A are FINAL adjudicated states, not unknowns (AA11)

    out = {
        "record": "B0_8_D7_4_RESIDUAL_CONSIDERATION_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_3_closure_sha256": d73["closure_sha256"]},
        "AA5_source_families": FAMILIES,
        "AA3_6178_event_class_audit": {
            "verdict": "HOLDER_SIDE_REORGANIZATION_WITH_CONSIDERATION",
            "membership_conflict": False,
            "finding": ("the sparse termination notice named no counterparty, but "
                        "TDCC STK003 records a share exchange into 詮鼎科技(6159); "
                        "6178 is a genuine share-conversion merger and correctly "
                        "belongs in the holder-side reorganization corpus"),
            "earlier_not_applicable_hypothesis": "REFUTED_BY_STK003",
        },
        "AA4_rename_lineage": {
            "6008": {"old_name": "中華開發金融控股股份有限公司",
                     "current": "凱基金融控股股份有限公司", "security_id": "2883",
                     "first_party_proof": "MOPS t05st03 前名稱 field",
                     "fuzzy_matching_used": False}},
        "stk003_first_party_confirmation": stk003_check,
        "AA6_source_family_matrix": {sid: ADJUDICATION[sid]["matrix"]
                                     for sid in residual},
        "AA9_residual_results": {
            "population": len(residual),
            "STOCK_ONLY_ESTABLISHED": newly_stock,
            "CASH_ONLY_ESTABLISHED": newly_cash,
            "MIXED_ESTABLISHED": newly_mixed,
            "CONSIDERATION_NOT_APPLICABLE": not_applicable,
            "CONSIDERATION_PUBLIC_AUTHORITATIVE_BOUNDARY": boundary,
            "CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED": not_exhausted,
            "EVENT_CLASS_MEMBERSHIP_UNRESOLVED": membership,
            "counts": tax,
        },
        "AA11_final_denominator": {
            "FINAL_STOCK_ONLY": final_stock_only,
            "FINAL_MIXED": final_mixed,
            "FINAL_CONFIRMED_STOCK_BEARING": final_stock_bearing,
            "FINAL_CASH_ONLY": final_cash,
            "CONSIDERATION_NOT_APPLICABLE": len(not_applicable),
            "PUBLIC_AUTHORITATIVE_BOUNDARY": len(boundary),
            "REMAINING_TRUE_UNKNOWN": remaining_true_unknown,
            "denominator_closed": remaining_true_unknown == 0,
            "reading": ("NOT closed: %d events remain source-family-not-exhausted "
                        "(the 3 投控 prospectus family + 3 unlisted-survivor "
                        "formal-filing family). %d genuine foreign boundary "
                        "(6514). Confirmed stock-bearing lower bound %d; upper "
                        "range +%d if the unexhausted resolve to stock/mixed"
                        % (remaining_true_unknown, len(boundary),
                           final_stock_bearing, remaining_true_unknown)),
        },
        "population_reconciliation": {
            "STOCK_ONLY": final_stock_only, "MIXED": final_mixed,
            "CASH_ONLY": final_cash,
            "PUBLIC_AUTHORITATIVE_BOUNDARY": len(boundary),
            "SOURCE_FAMILY_NOT_EXHAUSTED": len(not_exhausted),
            "total": final_stock_only + final_mixed + final_cash + len(boundary)
            + len(not_exhausted),
        },
        "per_event": per_event,

        # AA12 invariants
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
        "termination_discovery_branch_reopened": False,
        "cash_settlement_hunting": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "prior_artefacts_rewritten": 0,
        "consideration_grammar_changed": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    r = out["AA9_residual_results"]
    d = out["AA11_final_denominator"]
    print("residual population :", r["population"])
    print("newly STOCK         :", r["STOCK_ONLY_ESTABLISHED"])
    print("N/A                 :", r["CONSIDERATION_NOT_APPLICABLE"])
    print("foreign BOUNDARY    :", r["CONSIDERATION_PUBLIC_AUTHORITATIVE_BOUNDARY"])
    print("family-not-exhausted:", r["CONSIDERATION_SOURCE_FAMILY_NOT_EXHAUSTED"])
    print("FINAL stock-bearing :", d["FINAL_CONFIRMED_STOCK_BEARING"],
          "| cash", d["FINAL_CASH_ONLY"], "| boundary", d["PUBLIC_AUTHORITATIVE_BOUNDARY"],
          "| true-unknown", d["REMAINING_TRUE_UNKNOWN"])
    print("reconciliation total:", out["population_reconciliation"]["total"])
    print("denominator closed  :", d["denominator_closed"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
