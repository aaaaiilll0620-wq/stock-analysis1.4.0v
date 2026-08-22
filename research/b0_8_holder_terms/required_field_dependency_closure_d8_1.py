# -*- coding: utf-8 -*-
"""B0.8 · D8.1 · B1-B7 · REQUIRED-FIELD DEPENDENCY / SETTLEMENT FEASIBILITY.

D8.0 answered "what is present?" but derived its required-field model from its own
implementation. B1 forbids exactly that, and the audit shows why: D8.0 invented
requirements the frozen specification does not contain, and then reported the
resulting phantom gaps as blockers.

B1 · GROUND TRUTH IS core/b0_holder_side_terms.CLASS_REQUIRED_FIELDS
    RECONSTRUCTIBLE_STOCK  successor_security_id, stock_conversion_ratio,
                           holder_effective_boundary, successor_credit_date
    RECONSTRUCTIBLE_CASH   cash_consideration_per_old_share,
                           holder_effective_boundary, settlement_date
    RECONSTRUCTIBLE_MIXED  the union of both

    Anything in EXTRACTION_SCHEMA but NOT in CLASS_REQUIRED_FIELDS is extractable
    and (if extracted) must survive R6 dual agreement -- but its absence does not
    make an event NOT_RECONSTRUCTIBLE. successor_tradable_date and
    fractional_share_treatment are both in that category. And
    fractional_cash_handling / election_rule / default_election_semantics are not
    in the frozen schema AT ALL: D8.0 invented them.

B2 · FRACTIONAL, per frozen §6.1.9 (quoted, not paraphrased)
    "小於 canonical executable unit 之 fractional entitlement MUST 保留為
     non-tradable entitlement,直到官方 settlement semantics 可重建"
    "若 fractional settlement 會影響 exposed holding 之 NAV / cash / exit 而
     settlement semantics 無法 reconstruct -> W-1 BLOCK"
    The default behaviour (persist the claim) is fully defined WITHOUT the field.
    The field is therefore exposure-conditional at settlement time, not an
    unconditional per-event acquisition requirement.

B3/B5 · SETTLEMENT REPRESENTABILITY, and the absence trap D8.0 fell into
    D8.0 measured settlement fields over the DISAPPEARING-SIDE TERMINATION BUNDLE
    only -- a document class that structurally cannot carry them -- and reported
    0/25. Re-measured over the successor/acquirer-side first-party documents
    already preserved in D7.2c, both settlement fields ARE expressed:
        successor_credit_date  8420 (帳簿劃撥, 股份轉換 after 基準日)
        settlement_date        3553 / 5820 / 4429 (撥付, 匯入, 現金對價)
    So neither field is a public-authoritative representation boundary. Coverage
    is incomplete; representability is established. One positive control proves
    representability, never universal coverage (B5, both directions).

    python research/b0_8_holder_terms/required_field_dependency_closure_d8_1.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
from core import b0_holder_side_terms as HST                 # noqa: E402

D80 = os.path.join(HERE, "extraction_readiness_freeze_d8_0.json")
D72C = os.path.join(HERE, "successor_side_history_and_presence_d7_2c.json")
OUT = os.path.join(HERE, "required_field_dependency_closure_d8_1.json")

UNCOND = "UNCONDITIONALLY_REQUIRED"
COND = "CONDITIONALLY_REQUIRED"
DIAG = "DIAGNOSTIC_ONLY"
NOTREQ = "NOT_REQUIRED"
NOTSCHEMA = "NOT_IN_FROZEN_SCHEMA_INVENTED_BY_D8_0"

# D8.0's field names -> frozen schema field names
D80_TO_FROZEN = {
    "successor_issuer_security": "successor_security_id",
    "conversion_ratio": "stock_conversion_ratio",
    "cash_consideration": "cash_consideration_per_old_share",
    "holder_effective_date": "holder_effective_boundary",
    "successor_credit_delivery_date": "successor_credit_date",
    "tradable_listing_date": "successor_tradable_date",
    "fractional_treatment": "fractional_share_treatment",
    "fractional_cash_handling": None,
    "cash_payment_settlement_date": "settlement_date",
    "election_rule": None,
    "default_election_semantics": None,
}

FROZEN_CLASS = {
    "STOCK_ONLY": HST.CLASS_REQUIRED_FIELDS[HST.RECONSTRUCTIBLE_STOCK],
    "CASH_ONLY": HST.CLASS_REQUIRED_FIELDS[HST.RECONSTRUCTIBLE_CASH],
    "MIXED": HST.CLASS_REQUIRED_FIELDS[HST.RECONSTRUCTIBLE_MIXED],
}
ALL_REQUIRED = set().union(*(set(v) for v in FROZEN_CLASS.values()))


def dependency(frozen_name):
    """B1 · classify one frozen-schema field against the CA consumer."""
    if frozen_name is None:
        return NOTSCHEMA, "not present anywhere in EXTRACTION_SCHEMA"
    if frozen_name in ALL_REQUIRED:
        cls = [k for k, v in FROZEN_CLASS.items() if frozen_name in v]
        return UNCOND, ("required by CLASS_REQUIRED_FIELDS for %s; its absence "
                        "makes the event NOT_RECONSTRUCTIBLE" % "/".join(cls))
    spec = next((f for f in HST.EXTRACTION_SCHEMA if f.name == frozen_name), None)
    if spec is None:
        return NOTSCHEMA, "not in EXTRACTION_SCHEMA"
    if frozen_name == "fractional_share_treatment":
        return COND, ("§6.1.9: a fractional entitlement PERSISTS as a non-tradable "
                      "entitlement by default; the field is needed only where "
                      "fractional settlement affects exposed NAV/cash/exit and "
                      "would otherwise force a W-1 BLOCK. Not in "
                      "CLASS_REQUIRED_FIELDS, so it never decides the class")
    return (DIAG, "in EXTRACTION_SCHEMA and outcome-relevant for R6 agreement IF "
                  "extracted, but absent from CLASS_REQUIRED_FIELDS, so it does "
                  "not gate reconstruction")


def main() -> int:
    d80 = json.load(open(D80, encoding="utf-8"))
    d72c = json.load(open(D72C, encoding="utf-8"))
    succ = {e["security_id"]: e for e in d72c["per_event"]}

    # ---- B1 ------------------------------------------------------------
    deps = {}
    for d80f, frozen in D80_TO_FROZEN.items():
        cls, why = dependency(frozen)
        deps[d80f] = {"frozen_field": frozen, "dependency": cls, "basis": why}
    removed = [f for f, v in deps.items()
               if v["dependency"] in (DIAG, COND, NOTREQ, NOTSCHEMA)]

    # ---- B3/B4 · field-level settlement feasibility ----------------------
    credit_ctrl, settle_ctrl = [], []
    for sid, e in succ.items():
        for ld in e.get("same_transaction_linked_docs", []):
            p = ld["presence"]
            if p.get("SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD"):
                credit_ctrl.append({"security_id": sid, "subject": ld["subject"][:60],
                                    "labels": p["_labels_seen"]["share_delivery"],
                                    "body_sha256": ld.get("body_sha256")})
            if p.get("CASH_CONSIDERATION_DISBURSEMENT_FIELD_cash_leg"):
                settle_ctrl.append({"security_id": sid,
                                    "subject": ld["subject"][:60],
                                    "labels": p["_labels_seen"]["cash_disbursement"],
                                    "body_sha256": ld.get("body_sha256")})
    field_verdict = {
        "successor_credit_date": {
            "dependency": UNCOND,
            "verdict": "REPRESENTABLE_BUT_EVENT_COVERAGE_INCOMPLETE",
            "source_class": "official_exchange_or_mops (successor-side material "
                            "announcement)",
            "positive_controls": credit_ctrl[:5],
            "control_count": len(credit_ctrl),
            "note": "representability established by control; coverage across the "
                    "corpus is NOT established by it (B5)",
        },
        "settlement_date": {
            "dependency": UNCOND,
            "verdict": "REPRESENTABLE_BUT_EVENT_COVERAGE_INCOMPLETE",
            "source_class": "official_exchange_or_mops (acquirer-side tender / "
                            "share-conversion announcement)",
            "positive_controls": settle_ctrl[:5],
            "control_count": len(settle_ctrl),
            "note": "D8.0's 0/25 measured the disappearing-side termination "
                    "bundle only -- a class that structurally cannot carry a "
                    "settlement date. Re-measured on acquirer-side first-party "
                    "documents the field class IS expressed",
        },
        "successor_tradable_date": {
            "dependency": DIAG, "verdict": "NOT_REQUIRED",
            "note": "absent from CLASS_REQUIRED_FIELDS; never gates the class"},
        "fractional_share_treatment": {
            "dependency": COND, "verdict": "CONDITIONAL_ONLY",
            "note": "§6.1.9 default is persist-as-claim; only exposure-affecting "
                    "unreconstructable fractional settlement triggers W-1 BLOCK"},
        "fractional_cash_handling": {
            "dependency": NOTSCHEMA, "verdict": "NOT_REQUIRED",
            "note": "invented by D8.0; no such frozen field"},
        "election_rule": {
            "dependency": NOTSCHEMA, "verdict": "NOT_REQUIRED",
            "note": "invented by D8.0; MIXED/ELECTIVE remains discovery metadata, "
                    "the frozen CA model does not consume an election field"},
        "default_election_semantics": {
            "dependency": NOTSCHEMA, "verdict": "NOT_REQUIRED", "note": "as above"},
    }

    # ---- B6 · rebase readiness using ONLY frozen required fields ---------
    rebased, tax = [], Counter()
    for r in d80["per_event"]:
        sem = r["consideration_semantics"]
        if r["venue"] == "NON_TPEX" or sem == "UNKNOWN":
            tax["NOT_READY_SOURCE_ACQUISITION"] += 1
            rebased.append({"security_id": r["security_id"], "venue": r["venue"],
                            "semantics": sem,
                            "readiness": "NOT_READY_SOURCE_ACQUISITION",
                            "missing": ["consideration semantics"]
                            if sem == "UNKNOWN" else ["all (never acquired)"]})
            continue
        fr = r["field_readiness"]
        got = {}
        for d80f, frozen in D80_TO_FROZEN.items():
            if frozen and d80f in fr:
                got[frozen] = fr[d80f] == "AUTHORITATIVE_FIELD_PRESENT"
        # settlement/credit re-measured on the successor-side surface
        s = succ.get(r["security_id"])
        if s:
            docs = s.get("same_transaction_linked_docs", [])
            got["successor_credit_date"] = any(
                d["presence"]["SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD"]
                for d in docs)
            got["settlement_date"] = any(
                d["presence"].get("CASH_CONSIDERATION_DISBURSEMENT_FIELD_cash_leg")
                for d in docs)
        req = FROZEN_CLASS[sem]
        missing = [f for f in req if not got.get(f)]
        readiness = ("READY_FOR_DUAL_EXTRACTION" if not missing
                     else "NOT_READY_SOURCE_ACQUISITION")
        tax[readiness] += 1
        rebased.append({"security_id": r["security_id"], "venue": r["venue"],
                        "semantics": sem, "required_frozen_fields": list(req),
                        "missing": missing, "readiness": readiness})

    miss_counter = Counter()
    for r in rebased:
        if r["venue"] == "TPEX" and r["semantics"] != "UNKNOWN":
            for m in r["missing"]:
                miss_counter[m] += 1

    out = {
        "record": "B0_8_D8_1_REQUIRED_FIELD_DEPENDENCY_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d8_0_freeze_sha256": d80["freeze_sha256"],
                   "frozen_schema_sha256": HST.schema_identity()["schema_sha256"],
                   "d7_2c_presence_sha256": d72c["presence_sha256"]},
        "B1_authority": {
            "traced_to": "core/b0_holder_side_terms.py :: CLASS_REQUIRED_FIELDS "
                         "(the canonical CA consumer, classify_reconstruction)",
            "not_traced_to": "D8.0 implementation (explicitly forbidden by B1)",
            "frozen_class_required_fields": {k: list(v)
                                             for k, v in FROZEN_CLASS.items()},
        },
        "B1_field_dependencies": deps,
        "B1_fields_removed_from_readiness_requirement": removed,
        "B2_fractional_semantics": {
            "frozen_text_6_1_9": (
                "小於 canonical executable unit 之 fractional entitlement MUST "
                "保留為 non-tradable entitlement,直到官方 settlement semantics "
                "可重建;若 fractional settlement 會影響 exposed holding 之 "
                "NAV/cash/exit 而 settlement semantics 無法 reconstruct -> W-1 BLOCK"),
            "classification": COND,
            "required_for_every_event": False,
            "required_when": "a fractional entitlement actually arises AND its "
                             "settlement would affect exposed NAV/cash/exit",
            "default_without_the_field": "persist as non-tradable entitlement "
                                         "(fully defined; no acquisition needed)",
            "schema_modified": False,
        },
        "B4_field_level_results": field_verdict,
        "B5_absence_discipline": {
            "d8_0_claim_corrected": "cash settlement 0/25 ABSENT",
            "why_it_was_wrong": "measured only the disappearing-side termination "
                                "bundle, which structurally cannot carry it",
            "one_control_proves": "representability, not coverage",
            "zero_observations_prove": "nothing about first-party existence",
        },
        "B6_rebased_readiness": {
            "counts": dict(tax),
            "tpex_ready": [r["security_id"] for r in rebased
                           if r["readiness"] == "READY_FOR_DUAL_EXTRACTION"],
            "remaining_blockers_by_frozen_field": dict(miss_counter),
            "d8_0_artefact_preserved_unchanged": True,
        },
        "per_event": rebased,

        # invariants
        "schema_modified": False,
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "twse_99_acquisition_started": False,
        "dual_extraction_started": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "gates_evaluated": False,
        "prior_artefacts_rewritten": 0,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("frozen schema sha256:", out["inputs"]["frozen_schema_sha256"])
    print("\nB1 dependency classification:")
    for f, v in deps.items():
        print("   %-32s %-42s <- %s" % (f, v["dependency"], v["frozen_field"]))
    print("\nfields REMOVED from readiness requirement:", removed)
    print("\nB4 settlement feasibility:")
    for f in ("successor_credit_date", "settlement_date"):
        v = field_verdict[f]
        print("   %-24s %s (controls=%d)" % (f, v["verdict"], v["control_count"]))
    print("\nB6 rebased readiness:", dict(tax))
    print("   ready:", out["B6_rebased_readiness"]["tpex_ready"])
    print("   blockers by frozen field:", dict(miss_counter))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
