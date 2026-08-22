# -*- coding: utf-8 -*-
"""B0.8 · D8.0 · A1-A12 · 158-EVENT CANONICAL EXTRACTION READINESS FREEZE.

The phase gate. Not more archaeology: for every one of the frozen 158 holder-side
reorganization exits it answers only two questions --

    which reconstruction fields does THIS event require, given its holder-
    consideration semantics and event class?
    is the authoritative document bundle for each such field already frozen
    enough that dual extraction could start?

No canonical value is extracted or materialised. Field presence is measured
mechanically over the ALREADY-PRESERVED documents, never asserted by hand.

THE STRUCTURAL FACT THAT DOMINATES THIS CENSUS
    The entire D6/D7 discovery arc covered the TPEx subset only: the 59 events
    whose consideration semantics are established are a strict SUBSET of the 158.
    The other 99 (TWSE-listed 合併下市 / 併入控股公司下市) have had NO holder-
    consideration discovery and NO document bundle acquired at all. Readiness is
    therefore reported TPEx vs non-TPEx, and the non-TPEx 99 are uniformly
    NOT_READY_SOURCE_ACQUISITION -- an acquisition gap, not a boundary.

REQUIRED-FIELD MODEL (A2/A3), derived from leg semantics, nothing invented
    STOCK_ONLY        successor issuer/security, conversion ratio, holder
                      effective date, successor credit/delivery date,
                      tradable/listing date, fractional treatment
    CASH_ONLY         cash consideration, holder effective date,
                      payment/settlement date, fractional/cash handling
    MIXED_COMPOSITE   the stock set + the cash set (cash AND stock)
    MIXED_ELECTIVE    the stock set + the cash set + election rule +
                      default-election semantics (cash OR stock is a different
                      state transition and is modelled as such)

    python research/b0_8_holder_terms/extraction_readiness_freeze_d8_0.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows   # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                    # noqa: E402

REG = os.path.join(HERE, "event_register.json")
D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
D721 = os.path.join(HERE, "holder_consideration_semantics_d7_2_1.json")
D72C = os.path.join(HERE, "successor_side_history_and_presence_d7_2c.json")
D72B = os.path.join(HERE, "domestic_security_routing_d7_2b.json")
D76R = os.path.join(HERE, "bounded_residual_consideration_d7_6r.json")
OUT = os.path.join(HERE, "extraction_readiness_freeze_d8_0.json")
PAD = chr(0xE000)

# ---- final TPEx-59 consideration semantics (D7.2.1 -> D7.6R) -------------
STOCK_UPGRADES = {"3298": "D7.3", "3389": "D7.3", "6178": "D7.4", "2921": "D7.4",
                  "6008": "D7.4", "5384": "D7.6", "5491": "D7.6"}
UNKNOWN_FINAL = {"3562", "5818", "8705", "3582", "6514"}
MIXED_MODE = {"4429": "COMPOSITE", "5466": "COMPOSITE", "4152": "ELECTIVE"}

PRESENT = "AUTHORITATIVE_FIELD_PRESENT"
ABSENT = "AUTHORITATIVE_FIELD_ABSENT"
NOT_EXH = "SOURCE_FAMILY_NOT_EXHAUSTED"
BOUNDARY = "PUBLIC_AUTHORITATIVE_BOUNDARY"
NA = "NOT_APPLICABLE"

EFFECTIVE = ("基準日", "轉換基準日", "合併基準日", "股份轉換基準日", "事實發生日")
FRACTION = ("不足一股", "畸零股", "零股", "未滿一股", "不足壹股", "不滿一股")
CASHPAY = ("交付日期", "撥付", "發放日", "領取", "帳簿劃撥", "配發交付",
           "劃撥配發", "給付")


def required_fields(sem, mode):
    stock = ["successor_issuer_security", "conversion_ratio",
             "holder_effective_date", "successor_credit_delivery_date",
             "tradable_listing_date", "fractional_treatment"]
    cash = ["cash_consideration", "holder_effective_date",
            "cash_payment_settlement_date", "fractional_cash_handling"]
    if sem == "STOCK_ONLY":
        return stock
    if sem == "CASH_ONLY":
        return cash
    if sem == "MIXED":
        base = sorted(set(stock) | set(cash))
        if mode == "ELECTIVE":
            return base + ["election_rule", "default_election_semantics"]
        return base
    return []                       # UNKNOWN -> requirements undetermined


def main() -> int:
    reg = json.load(open(REG, encoding="utf-8"))
    d683 = json.load(open(D683, encoding="utf-8"))
    d721 = json.load(open(D721, encoding="utf-8"))
    d72c = json.load(open(D72C, encoding="utf-8"))
    d72b = json.load(open(D72B, encoding="utf-8"))
    d76r = json.load(open(D76R, encoding="utf-8"))

    ev683 = {e["security_id"]: e for e in d683["results"]}
    base_sem = {r["security_id"]: r["repaired_leg"] for r in d721["per_event"]}
    succ72c = {e["security_id"]: e for e in d72c["per_event"]}
    route = {r["security_id"]: r for r in d72b["per_event"]}
    rows, _ = index_rows()
    by = {r["doc_id"]: r for r in rows}

    # ---- evidence for events resolved after D7.2.1, read from its artefact --
    RATIO_NUM = re.compile(r"[\d.]+\s*股|每\s*[\d.]+|[\d.]+\s*元")
    upgrade_evidence = {}
    d73 = json.load(open(os.path.join(HERE,
                                      "holder_consideration_gap_closure_d7_3.json"),
                         encoding="utf-8"))
    for r in d73["per_event"]:
        if r["result"] != "STOCK_ONLY_ESTABLISHED":
            continue
        ld = (r.get("same_transaction_linked_docs") or [{}])[0]
        txt = str((ld.get("evidence") or {}).get("stock") or ld.get("subject") or "")
        upgrade_evidence[r["security_id"]] = {
            "doc": ld.get("subject", "survivor MOPS same-transaction announcement"),
            "family": "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT",
            "linkage": "D7.3 survivor-side same-transaction (disappearing issuer "
                       "named in body)",
            "text": txt, "ratio_present": bool(RATIO_NUM.search(txt))}
    d74 = json.load(open(os.path.join(HERE,
                                      "residual_consideration_closure_d7_4.json"),
                         encoding="utf-8"))
    for r in d74["per_event"]:
        if r["result"] != "STOCK_ONLY_ESTABLISHED":
            continue
        txt = str(r.get("evidence") or "")
        upgrade_evidence[r["security_id"]] = {
            "doc": r.get("evidence_family", "first-party record"),
            "family": r.get("evidence_family", "TDCC_STK003_MERGER_EXCHANGE_TABLE"),
            "linkage": "D7.4 first-party record / authoritative rename lineage",
            "text": txt, "ratio_present": bool(RATIO_NUM.search(txt))}
    d76 = json.load(open(os.path.join(
        HERE, "disappearing_party_edoc_consideration_d7_6.json"), encoding="utf-8"))
    for sid, r in d76["per_event"].items():
        if r.get("result") != "STOCK_ONLY_ESTABLISHED":
            continue
        txt = " ".join((r.get("evidence") or {}).get("security") or [])
        upgrade_evidence[sid] = {
            "doc": r.get("linked_doc", ""),
            "family": "DISAPPEARING_PARTY_MOPS_EDOC_ARCHIVE",
            "linkage": "D7.6 disappearing party's own filed document",
            "text": txt, "ratio_present": bool(RATIO_NUM.search(txt))}

    # ---- final semantics per TPEx event ------------------------------------
    sem_final = {}
    for sid, leg in base_sem.items():
        if sid in UNKNOWN_FINAL:
            sem_final[sid] = "UNKNOWN"
        elif sid in STOCK_UPGRADES:
            sem_final[sid] = "STOCK_ONLY"
        elif leg == "MIXED_STOCK_AND_CASH":
            sem_final[sid] = "MIXED"
        elif leg == "CONSIDERATION_NOT_ESTABLISHED":
            sem_final[sid] = "UNKNOWN"
        else:
            sem_final[sid] = leg
    tpex = set(sem_final)

    per_event, ready_tax, field_tax = [], Counter(), Counter()
    coverage = defaultdict(Counter)
    for e in reg["events"]:
        sid = e["security_id"]
        rec = {"event_id": e["event_id"], "security_id": sid,
               "effective_date": e["effective_date"],
               "status_reason": e["status_reason"],
               "old_reconstruction_status": e["old_reconstruction_status"]}

        # ---- non-TPEx 99: no discovery, no bundle ------------------------
        if sid not in tpex:
            rec.update(venue="NON_TPEX", consideration_semantics="UNKNOWN",
                       consideration_mode=None, required_fields=[],
                       field_readiness={},
                       source_bundle=[],
                       readiness="NOT_READY_SOURCE_ACQUISITION",
                       readiness_reason=("no holder-consideration discovery and no "
                                         "authoritative document bundle acquired "
                                         "for this event; the D6/D7 arc covered the "
                                         "TPEx subset only"))
            ready_tax["NOT_READY_SOURCE_ACQUISITION"] += 1
            per_event.append(rec)
            continue

        # ---- TPEx 59: measure over the preserved bundle -------------------
        sem = sem_final[sid]
        mode = MIXED_MODE.get(sid) if sem == "MIXED" else None
        req = required_fields(sem, mode)

        evd = ev683[sid]
        bundle, docs = "", []
        for c in evd["candidates"]:
            if c["doc_id"] in set(evd["linked"]):
                t, _s = VR.body_text(by[c["doc_id"]])
                t = (t or "")
                bundle += t
                row = by[c["doc_id"]]
                docs.append({
                    "doc_id": c["doc_id"],
                    "content_file": row.get("content_file"),
                    "index_date": row.get("date"),
                    "source_family": "TPEX_DISAPPEARING_SIDE_TERMINATION_BUNDLE",
                    "body_sha256": hashlib.sha256(
                        t.encode("utf-8")).hexdigest() if t else None,
                    "linkage_provenance": "D6.8.3 Gate-I entity identity + "
                                          "code-in-text binding (frozen)",
                    "supports_fields": ["holder_effective_date",
                                        "conversion_ratio/cash_consideration",
                                        "fractional_treatment"],
                })
        bare = bundle.replace(PAD, "")

        has_eff = any(x in bare for x in EFFECTIVE)
        has_frac = any(x in bare for x in FRACTION)
        has_paylabel = any(x in bare for x in CASHPAY)
        d721rec = next(r for r in d721["per_event"] if r["security_id"] == sid)
        has_ratio = bool(d721rec["evidence"].get("security"))
        has_cash = bool(d721rec["evidence"].get("cash"))
        # events resolved AFTER D7.2.1 carry their consideration evidence in the
        # later artefact (STK003 / survivor MOPS / disappearing-party e-doc), so
        # read it from there instead of mis-reporting a D7.2.1 blank as a gap.
        up = upgrade_evidence.get(sid)
        if up:
            has_ratio = has_ratio or up["ratio_present"]
            docs.append({"doc_id": up["doc"], "source_family": up["family"],
                         "body_sha256": up.get("sha"),
                         "linkage_provenance": up["linkage"],
                         "evidence": up["text"],
                         "supports_fields": ["conversion_ratio",
                                             "successor_issuer_security"]})
        s72 = succ72c.get(sid, {})
        succ_docs = s72.get("same_transaction_linked_docs", []) or []
        succ_credit = any(d["presence"]["SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD"]
                          for d in succ_docs)
        succ_listing = any(d["presence"]["SUCCESSOR_TRADABLE_OR_LISTING_DATE_FIELD"]
                           for d in succ_docs)
        for d in succ_docs:
            docs.append({
                "doc_id": "%s|%s" % (d.get("spoke_date"), d.get("seq_no")),
                "subject": d.get("subject"),
                "source_family": "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT",
                "body_sha256": d.get("body_sha256"),
                "linkage_provenance": "D7.2c X7 same-transaction: %s"
                                      % ",".join(d.get("linkage_evidence", [])),
                "supports_fields": ["successor_credit_delivery_date",
                                    "tradable_listing_date"],
            })
        issuer_ok = (route.get(sid, {}).get("successor_security_status")
                     == "DOMESTIC_SECURITY_ID_ESTABLISHED"
                     or sid in STOCK_UPGRADES)

        fr = {}
        for f in req:
            if f == "successor_issuer_security":
                fr[f] = PRESENT if issuer_ok else NOT_EXH
            elif f == "conversion_ratio":
                fr[f] = PRESENT if has_ratio else NOT_EXH
            elif f == "cash_consideration":
                fr[f] = PRESENT if has_cash else NOT_EXH
            elif f == "holder_effective_date":
                fr[f] = PRESENT if has_eff else ABSENT
            elif f == "successor_credit_delivery_date":
                fr[f] = PRESENT if succ_credit else (
                    NOT_EXH if succ_docs else NOT_EXH)
            elif f == "tradable_listing_date":
                fr[f] = PRESENT if succ_listing else NOT_EXH
            elif f == "fractional_treatment" or f == "fractional_cash_handling":
                fr[f] = PRESENT if has_frac else ABSENT
            elif f == "cash_payment_settlement_date":
                fr[f] = PRESENT if has_paylabel else ABSENT
            elif f in ("election_rule", "default_election_semantics"):
                fr[f] = NOT_EXH
            else:
                fr[f] = NOT_EXH
            field_tax[fr[f]] += 1
            coverage[sem][fr[f]] += 1

        if sem == "UNKNOWN":
            readiness = "NOT_READY_SOURCE_ACQUISITION"
            reason = ("holder-consideration instrument not established (D7.6R "
                      "terminal UNKNOWN); required-field set undetermined")
        elif all(v == PRESENT for v in fr.values()):
            readiness = "READY_FOR_DUAL_EXTRACTION"
            reason = "every required field has a frozen authoritative source"
        else:
            readiness = "NOT_READY_SOURCE_ACQUISITION"
            miss = [k for k, v in fr.items() if v != PRESENT]
            reason = "missing authoritative source for: %s" % ", ".join(miss)
        ready_tax[readiness] += 1
        rec.update(venue="TPEX", consideration_semantics=sem,
                   consideration_mode=mode, required_fields=req,
                   field_readiness=fr, source_bundle=docs,
                   linked_documents=len(docs),
                   readiness=readiness, readiness_reason=reason)
        per_event.append(rec)

    # ---- blockers ---------------------------------------------------------
    blockers = defaultdict(list)
    for r in per_event:
        for f, v in (r.get("field_readiness") or {}).items():
            if v != PRESENT:
                blockers[f].append(r["security_id"])

    # ---- diagnostic: the gap is a LAYER, not a set of events ---------------
    TERMS_LAYER = {"successor_issuer_security", "conversion_ratio",
                   "cash_consideration", "holder_effective_date"}
    SETTLE_LAYER = {"successor_credit_delivery_date", "tradable_listing_date",
                    "cash_payment_settlement_date", "fractional_treatment",
                    "fractional_cash_handling"}
    terms_ready, settle_ready = [], []
    for r in per_event:
        fr = r.get("field_readiness") or {}
        if not fr:
            continue
        t = [f for f in fr if f in TERMS_LAYER]
        s = [f for f in fr if f in SETTLE_LAYER]
        if t and all(fr[f] == PRESENT for f in t):
            terms_ready.append(r["security_id"])
        if s and all(fr[f] == PRESENT for f in s):
            settle_ready.append(r["security_id"])

    # ---- possible schema conflict: a required field no source ever states --
    frac_cells = [(r["security_id"], f, v) for r in per_event
                  for f, v in (r.get("field_readiness") or {}).items()
                  if f in ("fractional_treatment", "fractional_cash_handling")]
    frac_present = [x for x in frac_cells if x[2] == PRESENT]

    out = {
        "record": "B0_8_D8_0_EXTRACTION_READINESS_FREEZE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {
            "event_register_sha256": reg["register_sha256"],
            "d7_2_1_census_sha256": d721["census_sha256"],
            "d7_2c_presence_sha256": d72c["presence_sha256"],
            "d7_6r_closure_sha256": d76r["closure_sha256"],
        },
        "A1_scope": {"events": len(reg["events"]),
                     "tpex_with_consideration_semantics": len(tpex),
                     "non_tpex_never_discovered": len(reg["events"]) - len(tpex),
                     "subset_relation": "the TPEx 59 are a strict subset of the 158"},
        "A3_required_field_model": {
            "STOCK_ONLY": required_fields("STOCK_ONLY", None),
            "CASH_ONLY": required_fields("CASH_ONLY", None),
            "MIXED_COMPOSITE": required_fields("MIXED", "COMPOSITE"),
            "MIXED_ELECTIVE": required_fields("MIXED", "ELECTIVE"),
            "elective_modelled_separately": True,
        },
        "TPEX_59_consideration_census": {
            "STOCK_ONLY": sum(1 for v in sem_final.values() if v == "STOCK_ONLY"),
            "MIXED": sum(1 for v in sem_final.values() if v == "MIXED"),
            "CASH_ONLY": sum(1 for v in sem_final.values() if v == "CASH_ONLY"),
            "UNKNOWN": sum(1 for v in sem_final.values() if v == "UNKNOWN"),
            "mixed_modes": MIXED_MODE,
        },
        "A10_readiness": dict(ready_tax),
        "A4_field_readiness_totals": dict(field_tax),
        "coverage_by_leg": {k: dict(v) for k, v in coverage.items()},
        "known_blockers": {k: {"count": len(v), "events": sorted(v)[:40]}
                           for k, v in sorted(blockers.items(),
                                              key=lambda x: -len(x[1]))},
        "tpex_vs_non_tpex_readiness": {
            "TPEX": Counter(r["readiness"] for r in per_event
                            if r["venue"] == "TPEX"),
            "NON_TPEX": Counter(r["readiness"] for r in per_event
                                if r["venue"] == "NON_TPEX"),
        },
        "layer_diagnostic": {
            "note": ("diagnostic only, NOT an A10 taxonomy class: readiness "
                     "separates cleanly into a TERMS layer and a SETTLEMENT layer"),
            "terms_layer_fields": sorted(TERMS_LAYER),
            "settlement_layer_fields": sorted(SETTLE_LAYER),
            "events_with_full_TERMS_layer": len(terms_ready),
            "events_with_full_SETTLEMENT_layer": len(settle_ready),
            "terms_ready_events": sorted(terms_ready),
            "reading": ("the discovery arc succeeded at the terms layer and the "
                        "corpus-wide gap is the settlement layer; the blocker is "
                        "a FIELD CLASS, not a set of awkward events"),
        },
        "flagged_possible_schema_conflict": {
            "field": "fractional_treatment / fractional_cash_handling",
            "cells_required": len(frac_cells),
            "cells_present": len(frac_present),
            "observation": ("no preserved authoritative document in this corpus "
                            "states fractional-entitlement handling for ANY event; "
                            "a required field that no first-party source ever "
                            "expresses may be a schema-vs-source-reality conflict "
                            "rather than 158 individual acquisition gaps"),
            "action_taken": "flagged only; no event reclassified, schema unchanged",
        },
        "A6_endpoint_vs_family_rule_preserved": (
            "one endpoint's refusal is not source-family exhaustion; no readiness "
            "cell here is a boundary verdict derived from a single endpoint"),
        "per_event": per_event,

        # A11 invariants
        "canonical_holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "prior_artefacts_rewritten": 0,
    }
    out["tpex_vs_non_tpex_readiness"] = {
        k: dict(v) for k, v in out["tpex_vs_non_tpex_readiness"].items()}
    out["freeze_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("158 events | TPEx %d | non-TPEx %d"
          % (len(tpex), len(reg["events"]) - len(tpex)))
    print("consideration census:", out["TPEX_59_consideration_census"])
    print("readiness           :", dict(ready_tax))
    print("field readiness     :", dict(field_tax))
    print("top blockers        :")
    for k, v in list(out["known_blockers"].items())[:8]:
        print("   %-34s %d" % (k, v["count"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
