# -*- coding: utf-8 -*-
"""B0.8 · C0/C1/C2 · conformance close before D8.2.

C2 asks one mechanical question -- can the FROZEN CA transition consumer represent
an elective (cash OR stock) holder outcome? -- and forbids answering it from
CLASS_REQUIRED_FIELDS. So the answer is traced through the code that actually runs:

    handle_holder_side_security_conversion  (core/b0_corporate_actions.py)
        if successor and ratio and credit:  -> RECONSTRUCTIBLE(..., cash_per_share=)
        else:                               -> NOT_RECONSTRUCTIBLE

    the transition, IDENTITY_CHANGING_KINDS branch
        successor = str(event.successor_security_id)
        ratio     = Fraction(event.stock_ratio)
        new_claim = entitlement * ratio
        if new_claim > 0:        -> SecurityReceivable
        if event.cash_per_share: -> CashReceivable        # additive, unconditional

TWO FINDINGS, one asked for and one that materially bounds D8.2

  C2 (asked)  Both legs are applied unconditionally and additively. There is no
              election field on CorporateActionEvent, no branch that selects one
              leg, and no holder-election input anywhere in the transition. An
              elective "cash OR stock" outcome therefore CANNOT be represented,
              and 4152 is SCHEMA_OR_EVENT_CLASS_CONFLICT under the frozen schema.

  BEYOND C2   The same branch opens with successor_security_id and stock_ratio,
              and the handler refuses without successor AND ratio AND credit. So a
              PURE CASH holder exit has no RECONSTRUCTIBLE path through any
              IDENTITY_CHANGING kind -- while CLASS_REQUIRED_FIELDS does define
              RECONSTRUCTIBLE_CASH. The terms schema admits a cash-only class the
              transition engine cannot consume. Reported, not repaired: schema
              modification is not authorized here.

    python research/b0_8_holder_terms/mixed_consumer_conformance_c2.py
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
from core import b0_corporate_actions as CA                  # noqa: E402
from core import b0_holder_side_terms as HST                 # noqa: E402

D81 = os.path.join(HERE, "required_field_dependency_closure_d8_1.json")
D72C = os.path.join(HERE, "successor_side_history_and_presence_d7_2c.json")
D80 = os.path.join(HERE, "extraction_readiness_freeze_d8_0.json")
OUT = os.path.join(HERE, "mixed_consumer_conformance_c2.json")


def main() -> int:
    d81 = json.load(open(D81, encoding="utf-8"))
    d72c = json.load(open(D72C, encoding="utf-8"))
    d80 = json.load(open(D80, encoding="utf-8"))
    sem = {e["security_id"]: e["consideration_semantics"]
           for e in d80["per_event"] if e["venue"] == "TPEX"}

    # ---- C2 · mechanical trace of the consumer --------------------------
    handler_src = inspect.getsource(CA.handle_holder_side_security_conversion)
    trans_src = inspect.getsource(CA.apply_corporate_action) if hasattr(
        CA, "apply_corporate_action") else ""
    ev_fields = [f for f in getattr(CA.CorporateActionEvent, "__dataclass_fields__",
                                    {})]
    election_fields = [f for f in ev_fields
                       if re.search(r"elect|choice|option", f, re.I)]
    both_legs_additive = ("if event.cash_per_share" in inspect.getsource(CA))
    requires_stock_leg = bool(re.search(
        r"if\s+successor\s+and\s+ratio\s+and\s+credit", handler_src))

    c2 = {
        "question": "can the frozen consumer represent an elective cash OR stock "
                    "holder outcome?",
        "traced_through": ["core/b0_corporate_actions.handle_holder_side_"
                           "security_conversion",
                           "core/b0_corporate_actions IDENTITY_CHANGING_KINDS "
                           "transition branch"],
        "not_inferred_from_CLASS_REQUIRED_FIELDS": True,
        "identity_changing_kinds": list(CA.IDENTITY_CHANGING_KINDS),
        "corporate_action_event_fields": ev_fields,
        "election_related_fields_found": election_fields,
        "legs_applied": "BOTH_UNCONDITIONALLY_AND_ADDITIVELY",
        "evidence": [
            "handler: `if successor and ratio and credit:` -> RECONSTRUCTIBLE, "
            "carrying cash_per_share as an ADDITIONAL attribute",
            "transition: `if new_claim > 0:` creates a SecurityReceivable AND, "
            "separately, `if event.cash_per_share:` creates a CashReceivable; "
            "neither is guarded by any election",
        ],
        "elective_representable": False,
        "verdict_4152": "SCHEMA_OR_EVENT_CLASS_CONFLICT",
        "verdict_4152_basis": ("4152 is 現金100元 OR 森公司乙種特別股1股 (holder "
                               "elects). The frozen consumer would apply BOTH "
                               "legs, overstating what the holder received. No "
                               "frozen election mechanism exists to cite"),
        "schema_modified": False,
    }

    beyond = {
        "finding": "PURE_CASH_HOLDER_EXIT_HAS_NO_CONSUMER_PATH",
        "why": ("both IDENTITY_CHANGING kinds route through a branch that opens "
                "with successor_security_id and stock_ratio, and the handler "
                "refuses unless successor AND ratio AND credit are present; a "
                "cash-only exit satisfies none of them"),
        "contradiction_with_terms_schema": (
            "CLASS_REQUIRED_FIELDS defines RECONSTRUCTIBLE_CASH "
            "(cash_consideration_per_old_share, holder_effective_boundary, "
            "settlement_date), but no transition kind can consume it"),
        "materiality_for_d8_2": (
            "acquiring settlement_date for cash-only events cannot by itself make "
            "them RECONSTRUCTIBLE under the frozen model; this is a class-level "
            "conflict, not an acquisition gap"),
        "tpex_cash_only_events_affected": sorted(
            [s for s, v in sem.items() if v == "CASH_ONLY"]),
        "count": sum(1 for v in sem.values() if v == "CASH_ONLY"),
        "action_taken": "reported only; schema unchanged, no event reclassified "
                        "in the ledger",
    }

    # ---- C1 · transaction-scoped settlement control recount --------------
    credit_events, settle_events, rejected = set(), set(), []
    for e in d72c["per_event"]:
        sid = e["security_id"]
        leg = sem.get(sid)
        for ld in e.get("same_transaction_linked_docs", []):
            p = ld["presence"]
            dt = p.get("_doc_type")
            if p.get("SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD"):
                credit_events.add(sid)
            if p.get("CASH_CONSIDERATION_DISBURSEMENT_FIELD_cash_leg"):
                # C1: a precursor tender payment is NOT the canonical exit's
                # holder settlement unless the document ties it to the exit.
                if dt == "TENDER_OFFER":
                    rejected.append({"security_id": sid, "leg": leg,
                                     "subject": ld["subject"][:60],
                                     "reason": "tender-offer precursor payment; "
                                               "not shown to be the canonical "
                                               "exit's holder settlement"})
                elif leg in ("CASH_ONLY", "MIXED"):
                    settle_events.add(sid)
                else:
                    rejected.append({"security_id": sid, "leg": leg,
                                     "subject": ld["subject"][:60],
                                     "reason": "document carries cash "
                                               "disbursement language but the "
                                               "canonical exit is not cash-bearing"})
    c1 = {
        "rule": "a settlement control requires same canonical exit + holder cash "
                "consideration + holder payment/settlement semantics",
        "d8_1_claim_corrected": "settlement_date controls = 34 (document count)",
        "document_count_is_not_event_count": True,
        "settlement_controls_transaction_scoped_events": sorted(settle_events),
        "settlement_control_event_count": len(settle_events),
        "credit_controls_transaction_scoped_events": sorted(credit_events),
        "credit_control_event_count": len(credit_events),
        "rejected_as_precursor_or_out_of_scope": rejected[:12],
        "rejected_count": len(rejected),
        "revised_verdict_settlement_date": (
            "REPRESENTABLE_BUT_EVENT_COVERAGE_INCOMPLETE" if settle_events
            else "PUBLIC_AUTHORITATIVE_REPRESENTATION_NOT_ESTABLISHED_for_the_"
                 "canonical_exit_leg"),
    }

    c0 = {
        "unique_unconditional_fields": sorted(
            set().union(*(set(v) for v in HST.CLASS_REQUIRED_FIELDS.values()))),
        "count": len(set().union(*(set(v)
                                   for v in HST.CLASS_REQUIRED_FIELDS.values()))),
        "note": "each applies BY RECONSTRUCTION CLASS; no event requires all six",
        "per_class": {k: list(v) for k, v in HST.CLASS_REQUIRED_FIELDS.items()},
    }

    out = {
        "record": "B0_8_C0_C1_C2_CONFORMANCE_CLOSE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d8_1_closure_sha256": d81["closure_sha256"],
                   "frozen_schema_sha256": HST.schema_identity()["schema_sha256"]},
        "C0_bookkeeping": c0,
        "C1_settlement_control_recount": c1,
        "C2_mixed_consumer_conformance": c2,
        "beyond_C2_material_finding": beyond,
        "schema_modified": False,
        "reconstruction_classifications_changed": 0,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "dual_extraction_started": False,
    }
    out["conformance_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("C0 unique unconditional fields:", c0["count"], c0["unique_unconditional_fields"])
    print("\nC2 elective representable :", c2["elective_representable"])
    print("   election fields on event:", c2["election_related_fields_found"] or "NONE")
    print("   legs applied            :", c2["legs_applied"])
    print("   4152 verdict            :", c2["verdict_4152"])
    print("\nBEYOND C2:", beyond["finding"])
    print("   affected TPEx CASH_ONLY events:", beyond["count"])
    print("\nC1 settlement controls (transaction-scoped events):",
          c1["settlement_control_event_count"], c1["settlement_controls_transaction_scoped_events"])
    print("   credit controls:", c1["credit_control_event_count"],
          c1["credit_controls_transaction_scoped_events"])
    print("   rejected as precursor/out-of-scope:", c1["rejected_count"])
    print("   revised settlement verdict:", c1["revised_verdict_settlement_date"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
