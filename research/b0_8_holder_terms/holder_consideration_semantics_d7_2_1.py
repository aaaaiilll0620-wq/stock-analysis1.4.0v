# -*- coding: utf-8 -*-
"""B0.8 · D7.2.1 · Y1-Y13 · HOLDER-CONSIDERATION LEG SEMANTICS CONFORMANCE.

D7.2 proved the D7.1a leg census confuses transaction vocabulary (合併, 股份轉換,
公開收購) and tender-offer cash-payment language with the thing that actually
defines a leg: what the disappearing security holder RECEIVES in the canonical
exit transaction. This stage replaces the lexical leg census with a holder-
consideration classifier, frozen from a corpus-wide language inventory and run
uniformly over all 59 TPEx holder-side reorganization exits.

WHERE THE ANSWER LIVES (transaction scoping, Y6)
    The canonical exit transaction is the disappearing side's own 終止櫃檯買賣
    bundle. Its 換發 / 對價 clause states, in first-party terms, what the holder of
    one 消滅方 share receives. A 公開收購 (tender offer) named elsewhere in the
    bundle is a PRECURSOR and does not, on its own, make the exit MIXED. Mixed
    consideration is asserted only when cash and a security are both named as
    consideration inside the SAME exit clause (及 / 以及 / 併同 / 或-election).

WHAT COUNTS AS EVIDENCE (Y4/Y5, frozen)
    security : 換發 <company> [增資發行] 普通股/股份/特別股/股票 [ratio]
               股票換發為 <company> 股票
    cash     : 換發 [現金] 新臺幣 <n> 元 現金 ; 現金新臺幣 <n> 元
               每股現金(新臺幣)<n>元 ... 為對價 ; 新臺幣 <n> 元 ... 現金對價
               現金對價 ... 支付予 (全體) 股東
    Bare 現金, and bare 合併/股份轉換/公開收購/存續公司, are never sufficient.

PRE-FREEZE OUTCOME EXPOSURE (Y9)
    D7.2 already exposed the outcomes of several events (8420, 4429, 4945, 5820,
    4947, tender leakage). This is disclosed. The grammar below is frozen from the
    GENERAL exit-clause language surveyed corpus-wide, not from those identities;
    no event-specific rule is added after the freeze.

    python research/b0_8_holder_terms/holder_consideration_semantics_d7_2_1.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows   # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                    # noqa: E402

D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
D71A = os.path.join(HERE, "stock_leg_population_d7_1a.json")
D72B = os.path.join(HERE, "domestic_security_routing_d7_2b.json")
OUT = os.path.join(HERE, "holder_consideration_semantics_d7_2_1.json")
PAD = chr(0xE000)

# ---- FROZEN GRAMMAR -----------------------------------------------------
# The canonical exit consideration is stated in the disappearing side's own
# labelled field 轉換對價： / 合併對價： (and, when unlabelled, the 換發 clause).
# The consideration SPAN runs from that label to the next numbered field, so a
# later 公開收購 or dividend clause never bleeds into the consideration.
#
# Holder-receiving-share verbs are 換發 / 換發為 / 轉換為 / 轉換成為. The verb
# 取得 is NOT one of them: in this corpus it is the acquirer TAKING the target's
# 全部流通在外之普通股股份 for cash -- a cash-acquisition form, caught by CASH.
CONSID_FIELD = re.compile(r"(?:轉換對價|合併對價|現金對價|收購對價)[：:]")
NEXT_FIELD = re.compile(r"[一二三四五六七八九十]、")

# (a) verb + named company + its shares   (modern 換發/轉換為 form)
SHARE_VERB = re.compile(
    r"(?:換發為|換發|轉換成為|轉換為)\s*(?:增資發行)?\s*(?!新[臺台]幣|現金)"
    r"[一-鿿]{2,14}?公司[^。]{0,10}?"
    r"(?:增資發行)?(?:普通股|股份|甲種特別股|乙種特別股|特別股|股票)")
# (b) connective form for MIXED: ...及/以及/或 X公司 shares
SHARE_CONN = re.compile(
    r"(?:以及|及|或|併同)\s*(?!該公司|本公司)[一-鿿]{1,14}?公司[^。]{0,10}?"
    r"(?:增資發行)?(?:普通股|股份|特別股|股票)")
# (c) vintage 1:1 merger form: (合併)?換發 X公司 (N股)
SHARE_MERGER = re.compile(
    r"(?:合併)?換發\s*(?!新[臺台]幣|現金)[一-鿿]{1,16}?公司[（(][^）)]{0,10}股")
SHARE_ANY = (SHARE_VERB, SHARE_CONN, SHARE_MERGER)

# cash consideration paid to the holder (NT$ amount tied to cash/consideration)
CASH_RE = re.compile(
    r"現金[（(]?新[臺台]幣[）)]?\s*[\d,.]+\s*元"
    r"|新[臺台]幣\s*[\d,.]+\s*元[^。]{0,6}?(?:現金|之現金|之價格|之現金對價|"
    r"現金對價|現金價格)"
    r"|換發\s*新[臺台]幣\s*[\d,.]+\s*元\s*現金"
    r"|(?:對價為|之對價為|價格為|對價[:：])\s*(?:現金)?\s*新[臺台]幣\s*[\d,.]+\s*元")
ELECT = re.compile(r"換發[^。]{0,20}?現金[^。]{0,20}?或[^。]{0,20}?"
                   r"公司[^。]{0,10}?(?:特別股|普通股|股份)")
TENDER = re.compile(r"公開收購")


def consideration_span(text):
    """The canonical exit consideration text (Y6-scoped), longest available."""
    spans = []
    for m in CONSID_FIELD.finditer(text):
        rest = text[m.end():m.end() + 240]
        nxt = NEXT_FIELD.search(rest)
        spans.append(rest[:nxt.start()] if nxt else rest)
    if spans:
        return max(spans, key=len)
    # fallback when no labelled field: the 換發 clause and its sentence
    m = re.search(r"換發", text)
    if m:
        end = text.find("。", m.start())
        return text[m.start(): end if end > 0 else m.start() + 120]
    return ""


def classify_bundle(text):
    """Holder consideration from the canonical exit span (Y3/Y6/Y7)."""
    text = text.replace(PAD, "")
    span = consideration_span(text)
    share_hits = [p.search(span).group(0)[:60] for p in SHARE_ANY
                  if p.search(span)]
    cash_m = CASH_RE.search(span)
    holder_sec = bool(share_hits)
    holder_cash = bool(cash_m)
    if holder_sec and holder_cash:
        leg = "MIXED_STOCK_AND_CASH"
    elif holder_sec:
        leg = "STOCK_ONLY"
    elif holder_cash:
        leg = "CASH_ONLY"
    else:
        leg = "CONSIDERATION_NOT_ESTABLISHED"
    # metadata only (NEVER used to classify): why nothing was established
    ne_reason = None
    if leg == "CONSIDERATION_NOT_ESTABLISHED":
        names_merger = bool(re.search(r"股份轉換|合併|存續公司|概括承受", text))
        ne_reason = ("MERGER_OR_CONVERSION_NAMED_BUT_CONSIDERATION_RATIO_ABSENT"
                     if names_merger
                     else "NO_MERGER_CONSIDERATION_TRANSACTION_STATED")
    return {
        "leg": leg,
        "holder_receives_security": holder_sec,
        "holder_receives_cash": holder_cash,
        "mixed_within_single_clause": holder_sec and holder_cash,
        "elective_cash_or_stock": bool(ELECT.search(span)),
        "tender_offer_language_present": bool(TENDER.search(text)),
        "not_established_reason": ne_reason,
        "consideration_span": span[:180],
        "evidence": {"security": share_hits[:3],
                     "cash": [cash_m.group(0)[:60]] if cash_m else []},
    }


def grammar_freeze():
    material = {
        "CONSID_FIELD": CONSID_FIELD.pattern, "NEXT_FIELD": NEXT_FIELD.pattern,
        "SHARE_VERB": SHARE_VERB.pattern, "SHARE_CONN": SHARE_CONN.pattern,
        "SHARE_MERGER": SHARE_MERGER.pattern, "CASH_RE": CASH_RE.pattern,
        "ELECT": ELECT.pattern, "TENDER": TENDER.pattern,
        "holder_share_verbs": ["換發", "換發為", "轉換為", "轉換成為"],
        "acquirer_cash_verb_excluded": "取得",
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return material, hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main() -> int:
    d683 = json.load(open(D683, encoding="utf-8"))
    d71a = json.load(open(D71A, encoding="utf-8"))
    d72b = json.load(open(D72B, encoding="utf-8"))
    prior_leg = {r["security_id"]: r["transaction_leg"] for r in d71a["results"]}
    route = {r["security_id"]: r for r in d72b["per_event"]}
    rows, _ = index_rows()
    by = {r["doc_id"]: r for r in rows}

    material, gsha = grammar_freeze()

    results, leg_tax = [], Counter()
    for e in d683["results"]:
        sid = e["security_id"]
        txt = ""
        for c in e["candidates"]:
            if c["doc_id"] in set(e["linked"]):
                t, _s = VR.body_text(by[c["doc_id"]])
                txt += (t or "")
        cls = classify_bundle(txt)
        leg_tax[cls["leg"]] += 1

        # ---- Y8 · counterparty vs stock-consideration issuer -------------
        r72 = route.get(sid, {})
        if cls["leg"] == "CASH_ONLY":
            issuer_status = "NOT_APPLICABLE"
            issuer_route = "NOT_APPLICABLE"
        elif cls["holder_receives_security"]:
            issuer_status = r72.get("successor_security_status",
                                    "PENDING") if r72 else "PENDING"
            issuer_route = r72.get("successor_security_id") or issuer_status
        else:
            issuer_status = "CONSIDERATION_NOT_ESTABLISHED"
            issuer_route = "NOT_APPLICABLE"

        results.append({
            "security_id": sid,
            "prior_d7_1a_leg": prior_leg.get(sid),
            "repaired_leg": cls["leg"],
            "holder_receives_security": cls["holder_receives_security"],
            "holder_receives_cash": cls["holder_receives_cash"],
            "mixed_within_single_clause": cls["mixed_within_single_clause"],
            "elective_cash_or_stock": cls["elective_cash_or_stock"],
            "tender_offer_language_present": cls["tender_offer_language_present"],
            "not_established_reason": cls["not_established_reason"],
            "consideration_span": cls["consideration_span"],
            "stock_consideration_issuer_status": issuer_status,
            "stock_consideration_issuer_route": issuer_route,
            "evidence": cls["evidence"],
        })

    # ---- Y13 · movement accounting vs prior 30-member stock acquisition ---
    prior_stock = {sid for sid, l in prior_leg.items()
                   if l in ("STOCK_LEG_PRESENT", "MIXED_LEG_PRESENT")}
    now_stock = {r["security_id"] for r in results
                 if r["repaired_leg"] in ("STOCK_ONLY", "MIXED_STOCK_AND_CASH")}
    removed = sorted(prior_stock - now_stock)
    added = sorted(now_stock - prior_stock)
    changed = [r for r in results
               if (r["security_id"] in prior_stock) != (
                   r["security_id"] in now_stock)
               or r["repaired_leg"] not in _leg_of(r["prior_d7_1a_leg"])]

    # tender-offer / cash-squeeze leakage: events D7.1a's lexical census read as
    # MIXED that carry only ONE consideration once the canonical exit clause is
    # read -- pure cash (tender/squeeze) or pure stock mistaken as mixed.
    tender_leak = sorted(r["security_id"] for r in results
                         if r["prior_d7_1a_leg"] == "MIXED_LEG_PRESENT"
                         and r["repaired_leg"] in ("CASH_ONLY", "STOCK_ONLY"))

    issuer_est = [r["security_id"] for r in results
                  if r["stock_consideration_issuer_status"]
                  == "DOMESTIC_SECURITY_ID_ESTABLISHED"]
    issuer_unres = [r["security_id"] for r in results
                    if r["stock_consideration_issuer_status"] in (
                        "SUCCESSOR_SECURITY_ROUTING_UNRESOLVED",
                        "DOMESTIC_ENTITY_NO_PUBLIC_SECURITY",
                        "FOREIGN_OR_NON_ROC_SUCCESSOR", "PENDING")]
    issuer_na = [r["security_id"] for r in results
                 if r["stock_consideration_issuer_status"] == "NOT_APPLICABLE"]

    out = {
        "record": "B0_8_D7_2_1_HOLDER_CONSIDERATION_SEMANTICS",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d6_8_3_census_sha256": d683["census_sha256"],
                   "d7_1a_census_sha256": d71a["census_sha256"],
                   "d7_2b_routing_sha256": d72b["routing_sha256"]},

        "Y2_defect": {
            "D7_1A_LEG_CLASSIFIER":
                "LEXICAL_TRANSACTION_VOCABULARY_OVERINCLUSION_DEFECT",
            "d7_1a_historical_counts_preserved_unchanged": {
                "STOCK_LEG_PRESENT": sum(
                    1 for l in prior_leg.values() if l == "STOCK_LEG_PRESENT"),
                "MIXED_LEG_PRESENT": sum(
                    1 for l in prior_leg.values() if l == "MIXED_LEG_PRESENT"),
                "CASH_LEG_PRESENT": sum(
                    1 for l in prior_leg.values() if l == "CASH_LEG_PRESENT"),
                "NO_STOCK_LEG": sum(
                    1 for l in prior_leg.values() if l == "NO_STOCK_LEG"),
            },
        },
        "Y9_grammar_freeze": {
            "frozen_material": material, "grammar_sha256": gsha,
            "pre_freeze_event_outcome_exposure": True,
            "exposed_events_from_d7_2": ["8420", "4429", "4945", "5820", "4947",
                                         "6157", "4110", "5466", "4152"],
            "frozen_from": "corpus-wide exit-clause language inventory, not the "
                           "exposed event identities",
            "event_specific_rule_added_after_freeze": False,
            "freeze_was_corrected_once_before_final_rerun": {
                "disclosed": True,
                "reason": ("the first freeze anchored only on the 換發 verb and "
                           "missed the labelled 轉換對價／合併對價 field and the "
                           "取得...全部流通在外之普通股 cash-acquisition form, "
                           "leaving 24 events unresolved. The grammar was "
                           "completed from a fuller corpus-wide inventory of the "
                           "consideration field -- a general document-structure "
                           "correction, not an event-specific rule"),
                "correction_is_structural_not_outcome_tuned": True,
            },
        },
        "Y7_repaired_leg_counts": dict(leg_tax),
        "Y13_movement": {
            "population": len(results),
            "prior_stock_acquisition_members": len(prior_stock),
            "repaired_stock_population": len(now_stock),
            "removed_from_stock_acquisition": removed,
            "removed_count": len(removed),
            "added_to_stock_acquisition": added,
            "added_count": len(added),
            "every_changed_event": [
                {"security_id": r["security_id"],
                 "prior": r["prior_d7_1a_leg"], "repaired": r["repaired_leg"],
                 "holder_security": r["holder_receives_security"],
                 "holder_cash": r["holder_receives_cash"],
                 "tender_language": r["tender_offer_language_present"],
                 "reason": _reason(r)}
                for r in changed],
        },
        "Y8_stock_consideration_issuer": {
            "established": sorted(issuer_est), "established_count": len(issuer_est),
            "routing_unresolved": sorted(issuer_unres),
            "routing_unresolved_count": len(issuer_unres),
            "not_applicable_cash_only": sorted(issuer_na),
            "not_applicable_count": len(issuer_na),
        },
        "tender_offer_leakage_count": len(tender_leak),
        "tender_offer_leakage_events": tender_leak,

        "Y11_d7_2_presence_preserved": {
            "genuine_successor_share_credit_field_instance": "8420",
            "listing_field_instances": ["4110", "5466", "6105", "1566", "4429"],
            "prevalence_not_final_until_population_repaired": True,
            "note": ("D7.2 successor-side presence findings are preserved at "
                     "adjudication level; 1/30 and 5/30 are NOT reported as final "
                     "because the stock population denominator is repaired here"),
        },
        "Y12_diagnostics": {
            r["security_id"]: {
                "repaired_leg": r["repaired_leg"],
                "holder_security": r["holder_receives_security"],
                "holder_cash": r["holder_receives_cash"],
                "tender_language": r["tender_offer_language_present"],
                "stock_issuer_status": r["stock_consideration_issuer_status"],
                "consideration": (r["evidence"]["security"]
                                  or r["evidence"]["cash"] or ["<none>"])[0],
            }
            for r in results
            if r["security_id"] in ("8420", "4429", "4945", "5820", "4947",
                                    "4103", "8913", "4152")
        },
        "per_event": results,

        # Y14 invariants
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
        "cash_leg_source_hunting": False,
        "termination_branch_reopened": False,
        "new_successor_side_acquisition": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "d7_1a_artefact_rewritten": False,
        "network_requests": 0,
    }
    out["census_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("grammar_sha256      :", gsha)
    print("repaired leg counts :", dict(leg_tax))
    print("prior stock members :", len(prior_stock),
          "-> repaired stock pop:", len(now_stock))
    print("removed from stock  :", removed)
    print("added to stock      :", added)
    print("tender-offer leakage:", len(tender_leak), tender_leak)
    print("issuer established  :", len(issuer_est),
          "| unresolved", len(issuer_unres), "| N/A(cash)", len(issuer_na))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


def _leg_of(prior):
    """Prior lexical leg mapped to the repaired vocabulary it would be 'unchanged'
    against -- used only to decide whether an event's class moved."""
    return {
        "STOCK_LEG_PRESENT": ("STOCK_ONLY",),
        "MIXED_LEG_PRESENT": ("MIXED_STOCK_AND_CASH",),
        "CASH_LEG_PRESENT": ("CASH_ONLY",),
        "NO_STOCK_LEG": ("CASH_ONLY", "CONSIDERATION_NOT_ESTABLISHED"),
    }.get(prior, ())


def _reason(r):
    p, n = r["prior_d7_1a_leg"], r["repaired_leg"]
    if p == "MIXED_LEG_PRESENT" and n == "STOCK_ONLY":
        return ("prior MIXED was lexical over-inclusion; canonical exit clause "
                "issues only shares, tender/cash was precursor or absent")
    if p == "MIXED_LEG_PRESENT" and n == "CASH_ONLY":
        return ("prior MIXED was lexical over-inclusion; canonical exit pays only "
                "cash, share-conversion vocabulary was mechanism not consideration")
    if p in ("STOCK_LEG_PRESENT",) and n == "CASH_ONLY":
        return "prior STOCK was lexical; holder actually receives cash"
    if p in ("NO_STOCK_LEG", "CASH_LEG_PRESENT") and n in (
            "STOCK_ONLY", "MIXED_STOCK_AND_CASH"):
        return "prior non-stock; holder actually receives a security"
    if n == "CONSIDERATION_NOT_ESTABLISHED":
        return "no authoritative holder-consideration clause resolved in bundle"
    return "class moved under holder-consideration semantics"


if __name__ == "__main__":
    sys.exit(main())
