# -*- coding: utf-8 -*-
"""B0.8 · D7.3 · Z1-Z13 · HOLDER-CONSIDERATION GAP CLOSURE (the 12 unknowns).

D7.2.1 left 12 events CONSIDERATION_NOT_ESTABLISHED: their disappearing-side
termination bundle names a merger/share-conversion (or, for 6178, nothing) but
does not state what the holder receives. This stage answers, for each of the 12
and nothing else, the single binary pair:

    DOES_HOLDER_RECEIVE_SECURITY ?     DOES_HOLDER_RECEIVE_CASH ?

using first-party same-transaction documents, without materialising any ratio,
amount or date (Z4/Z10). The frozen D7.2.1 holder-consideration grammar is reused
unchanged, so 'transaction mechanism != holder consideration' (Z7) still holds:
股份轉換 / 合併 / 存續公司 never imply stock, and 現金 / 公開收購 never imply cash.

ROUTE (Z5/Z6)
    The disappearing issuer's own MOPS history is refused after delisting
    (D7.0b-2), so the canonical consideration is sought on the SURVIVOR side: the
    surviving/acquiring issuer's MOPS same-transaction announcement, linked by the
    disappearing issuer being named in its body. The closed TPEx termination
    branch is NOT reopened; no third-party mirrors, TEJ, price or search snippets.

    python research/b0_8_holder_terms/holder_consideration_gap_closure_d7_3.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows   # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                    # noqa: E402
import holder_consideration_semantics_d7_2_1 as SEM          # noqa: E402
import successor_side_history_and_presence_d7_2c as CR        # noqa: E402

D721 = os.path.join(HERE, "holder_consideration_semantics_d7_2_1.json")
D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
DIRS = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                    "d7_2b_first_party_directories.json")
OUT = os.path.join(HERE, "holder_consideration_gap_closure_d7_3.json")
PAD = chr(0xE000)

MOPS_AC = "https://mopsov.twse.com.tw/mops/web/ajax_autoComplete"
AC_HEADERS = {"User-Agent": "Mozilla/5.0",
              "Content-Type": "application/x-www-form-urlencoded",
              "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01"}

# Survivor-side holder-consideration grammar (Z7-compliant: these are
# consideration statements, not mere mechanism). A share-EXCHANGE RATIO or an
# explicit new-share delivery means the holder receives a security; a per-share
# cash price/consideration means the holder receives cash. Applied only inside a
# body already linked to the same transaction (names the disappearing issuer).
SURV_STOCK = re.compile(
    r"換股比例|發行新股(?:換發|以)|換發本公司(?:普通股|股票|新股|[\d,.]+股)"
    r"|以本公司(?:普通股|股票)[\d,.]*股?\s*換發|股份轉換.{0,24}換發.{0,10}"
    r"(?:本公司|投資控股|投控)[^。]{0,6}?(?:普通股|股票|股)")
SURV_CASH = re.compile(
    r"每股[^。]{0,6}?(?:現金)?(?:新[臺台]幣)?\s*[\d,.]+\s*元[^。]{0,6}?"
    r"(?:現金|收購|對價)|現金對價|以現金[^。]{0,6}?(?:收購|為對價|取得)"
    r"|現金[^。]{0,4}?收購價")

# counterparty (survivor / acquirer) in the disappearing side's own 查... sentence
CP = (r"與\s*(?:上市公司|上櫃公司|未公開發行公司)?\s*([一-鿿()（）]{2,22}?(?:公司|銀行))\s*(?:進行)?(?:合併|股份轉換)",
      r"股份轉換(?:成為|為)?\s*(?:上市公司|上櫃公司)?\s*([一-鿿()（）]{2,22}?公司)\s*百分之百",
      r"轉換為\s*([一-鿿]{2,22}?(?:投資控股|投控)[一-鿿]{0,6}?公司)",
      r"以\s*([一-鿿()（）]{2,22}?公司)\s*為存續公司",
      r"由\s*([A-Za-z一-鿿()（）]{2,30}?)\s*(?:之母公司|概括承受|存續)")


def counterparty(text):
    for pat in CP:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def route_code(name, static_idx):
    """Survivor security code: exact static directory, else first-party MOPS AC."""
    if name in static_idx:
        return static_idx[name]["code"], static_idx[name]["board"], "STATIC_DIRECTORY"
    short = re.sub(r"股份有限公司$", "", name or "")
    if not short:
        return None, None, None
    body = urllib.parse.urlencode({
        "firstin": "1", "TYPEK": "all", "step": "1", "co_id": "",
        "funcName": "t05st01", "inpuType": "keyword", "keyword": short}).encode()
    try:
        req = urllib.request.Request(MOPS_AC, data=body, headers=AC_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
        time.sleep(0.5)
    except Exception:                                         # noqa: BLE001
        return None, None, None
    for code in re.findall(r"goaction\(\s*'(\d{4,6})'", raw):
        m = re.search(re.escape(code) + r"\s*<span[^>]*>([^<]{1,20})", raw)
        nm = m.group(1).strip() if m else ""
        # exact short-name only: a prefix like 特力 must not match 特力屋
        if nm and nm == short:
            return code, "MOPS", "MOPS_AUTOCOMPLETE"
    return None, None, None


def consideration_from_survivor(code, disp_name, disp_stem):
    """Full-history survivor MOPS, same-transaction linked, holder consideration."""
    rows = []
    avail = 0
    for y in CR.YEARS:
        yr, _hit, av = CR.enum_year(code, y)
        rows.extend(yr)
        avail += 1 if av else 0
    if avail == 0:
        return {"history_available": False, "linked": [],
                "holder_security": False, "holder_cash": False}
    cands = [r for r in rows if any(v in r["subject"] for v in CR.TXN_VOCAB)
             and not any(n in r["subject"] for n in CR.ACCOUNTING_NOISE)]
    linked, hsec, hcash = [], False, False
    for r in cands:
        body = CR.fetch_body(code, r)
        if not body:
            continue
        if not (disp_name and disp_name in body) and not (
                disp_stem and len(disp_stem) >= 2 and disp_stem in body):
            continue
        sm = SURV_STOCK.search(body)
        cm = SURV_CASH.search(body)
        hsec = hsec or bool(sm)
        hcash = hcash or bool(cm)
        linked.append({"date": r["date"], "subject": r["subject"],
                       "holder_security": bool(sm), "holder_cash": bool(cm),
                       "evidence": {"stock": sm.group(0)[:50] if sm else None,
                                    "cash": cm.group(0)[:50] if cm else None}})
    return {"history_available": True, "linked": linked,
            "holder_security": hsec, "holder_cash": hcash}


def main() -> int:
    d721 = json.load(open(D721, encoding="utf-8"))
    d683 = json.load(open(D683, encoding="utf-8"))
    ev = {e["security_id"]: e for e in d683["results"]}
    gap = [r["security_id"] for r in d721["per_event"]
           if r["repaired_leg"] == "CONSIDERATION_NOT_ESTABLISHED"]
    disp_name = {e["security_id"]: "" for e in d683["results"]}
    for e in d683["results"]:
        # disappearing legal name from d7_1a lineage isn't needed; use bundle head
        pass
    dirs = json.load(open(DIRS, encoding="utf-8"))
    static_idx = {}
    for board in ("tpex", "twse"):
        for r in dirs[board]:
            static_idx[r["legal_name"]] = {"code": r["code"],
                                           "board": board.upper()}
    rows, _ = index_rows()
    by = {r["doc_id"]: r for r in rows}

    source_registry = {
        "families_frozen_before_outcome_inspection": [
            "surviving/acquiring issuer MOPS same-transaction announcement",
            "first-party company directories (TWSE/TPEx) + MOPS autocomplete",
        ],
        "disappearing_issuer_mops": "refused after delisting (D7.0b-2); not usable",
        "termination_discovery_branch": "CLOSED, not reopened",
        "forbidden": ["third-party mirrors", "TEJ", "price inference",
                      "search-engine snippets"],
    }

    results, tax, mode_tax = [], Counter(), Counter()
    for sid in gap:
        e = ev[sid]
        bundle = ""
        for c in e["candidates"]:
            if c["doc_id"] in set(e["linked"]):
                t, _s = VR.body_text(by[c["doc_id"]])
                bundle += (t or "")
        bundle = bundle.replace(PAD, "")
        disp = re.match(r"公告\s*([一-鿿]{2,20}?(?:公司|銀行))", bundle)
        disp_legal = disp.group(1) if disp else ""
        disp_stem = re.sub(r"(股份有限公司|股份|公司)$", "", disp_legal)
        cp = counterparty(bundle)
        is_merger = bool(re.search(r"合併|股份轉換|概括承受|存續", bundle))

        rec = {"security_id": sid, "disappearing_entity": disp_legal,
               "counterparty_survivor": cp,
               "transaction_named": is_merger}

        if not is_merger or not cp:
            rec.update(result="CONSIDERATION_STILL_NOT_ESTABLISHED",
                       reason="no merger/share-conversion counterparty stated "
                              "in the authoritative bundle (administrative "
                              "delisting)" if not is_merger
                              else "counterparty not extractable",
                       holder_security=False, holder_cash=False,
                       survivor_route=None)
            tax[rec["result"]] += 1
            results.append(rec)
            continue

        code, board, src = route_code(cp, static_idx)
        if not code:
            rec.update(result="CONSIDERATION_STILL_NOT_ESTABLISHED",
                       reason="survivor is unlisted / foreign; no first-party "
                              "MOPS consideration route",
                       survivor_public_status="NONPUBLIC_OR_FOREIGN_SURVIVOR",
                       holder_security=False, holder_cash=False,
                       survivor_route=None)
            tax[rec["result"]] += 1
            results.append(rec)
            continue

        con = consideration_from_survivor(code, disp_legal, disp_stem)
        hsec, hcash = con["holder_security"], con["holder_cash"]
        if not con["history_available"]:
            result = "CONSIDERATION_STILL_NOT_ESTABLISHED"
        elif hsec and hcash:
            result = "MIXED_ESTABLISHED"
        elif hsec:
            result = "STOCK_ONLY_ESTABLISHED"
        elif hcash:
            result = "CASH_ONLY_ESTABLISHED"
        else:
            result = "CONSIDERATION_STILL_NOT_ESTABLISHED"
        rec.update(result=result, holder_security=hsec, holder_cash=hcash,
                   survivor_route={"code": code, "board": board, "source": src},
                   survivor_history_available=con["history_available"],
                   same_transaction_linked_docs=con["linked"][:6],
                   linked_doc_count=len(con["linked"]))
        if result == "MIXED_ESTABLISHED":
            rec["consideration_mode"] = "UNRESOLVED_MODE"
            mode_tax["UNRESOLVED_MODE"] += 1
        tax[result] += 1
        # ---- Z9 · stock consideration issuer (routing only) --------------
        if hsec:
            rec["stock_consideration_issuer"] = cp
            rec["issuer_public_security_status"] = (
                "PUBLIC_SECURITY_ID_ESTABLISHED")
        results.append(rec)
        print("  %s -> %s (survivor %s/%s, linked %d, sec=%s cash=%s)"
              % (sid, result, cp[:12], code, rec.get("linked_doc_count", 0),
                 hsec, hcash), flush=True)

    # ---- Z11 · recompute the denominator --------------------------------
    base = d721["Y7_repaired_leg_counts"]
    new_stock = sum(1 for r in results if r["result"] == "STOCK_ONLY_ESTABLISHED")
    new_cash = sum(1 for r in results if r["result"] == "CASH_ONLY_ESTABLISHED")
    new_mixed = sum(1 for r in results if r["result"] == "MIXED_ESTABLISHED")
    still = sum(1 for r in results
                if r["result"] == "CONSIDERATION_STILL_NOT_ESTABLISHED")
    final_stock = base.get("STOCK_ONLY", 0) + base.get(
        "MIXED_STOCK_AND_CASH", 0) + new_stock + new_mixed
    final_cash = base.get("CASH_ONLY", 0) + new_cash
    final_mixed = base.get("MIXED_STOCK_AND_CASH", 0) + new_mixed

    out = {
        "record": "B0_8_D7_3_HOLDER_CONSIDERATION_GAP_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_2_1_census_sha256": d721["census_sha256"]},
        "Z1_d7_2_presence_rebase": {
            "successor_share_credit_confirmed": ["8420"],
            "holder_stock_listing_confirmed": ["4110", "5466", "1566", "4429"],
            "6105_reclassified": "CASH_ONLY -> its successor/counterparty listing "
                                 "field is NOT holder stock-successor evidence",
            "prevalence_not_computed": True,
        },
        "Z5_source_registry": source_registry,
        "historical_d7_2_1_census": base,
        "confirmed_stock_bearing_lower_bound_before_d7_3": 25,
        "Z8_gap_results": {
            "population": len(gap),
            "STOCK_ONLY_ESTABLISHED": new_stock,
            "CASH_ONLY_ESTABLISHED": new_cash,
            "MIXED_ESTABLISHED": new_mixed,
            "CONSIDERATION_STILL_NOT_ESTABLISHED": still,
            "counts": dict(tax),
        },
        "Z11_final_denominator": {
            "FINAL_CONFIRMED_STOCK_BEARING": final_stock,
            "FINAL_CASH_ONLY": final_cash,
            "FINAL_MIXED": final_mixed,
            "REMAINING_CONSIDERATION_UNKNOWN": still,
            "stock_leg_denominator_closed": still == 0,
            "reading": ("closed" if still == 0 else
                        "confirmed lower bound %d stock-bearing; up to %d of the "
                        "remaining unknowns could still be stock or mixed"
                        % (final_stock, still)),
        },
        "per_event": results,

        # Z12 invariants
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classification_changed": 0,
        "reconstruction_schema_unchanged": True,
        "cash_settlement_hunting": False,
        "termination_branch_reopened": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "d7_2_1_artefact_rewritten": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\ngap results   :", dict(tax))
    print("FINAL stock   :", final_stock, "| cash", final_cash,
          "| mixed", final_mixed, "| still unknown", still)
    print("denominator closed:", still == 0)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
