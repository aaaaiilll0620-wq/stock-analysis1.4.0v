# -*- coding: utf-8 -*-
"""B0.8 · D7.6R · FINAL bounded residual consideration pass (4 events).

This is the LAST D7 consideration-acquisition stage. It runs under a hard
engineering budget and stops permanently afterwards, whatever the outcome --
UNKNOWN is an allowed terminal state here, because D8.0's readiness taxonomy can
carry it.

BUDGET (enforced in code, not merely intended)
    population            3562, 5818, 8705, 3582   (6514 deliberately untouched)
    surface               disappearing-party MOPS electronic-document archive only
    documents inspected   <= 10 per event, final vintage first
    transport retries     <= 3 per request, fresh session state per request
    history crawl         none
    grammar               frozen D7.2.1, unchanged
    OCR                   only for an already-identified same-transaction
                          candidate whose decisive page is image-only

THE RULE THAT MATTERS MOST
    An empty listing, a rate limit, a timeout or an exhausted retry budget is an
    ACQUISITION_ERROR or NOT_READY_SOURCE_ACQUISITION -- never a
    public-authoritative-boundary verdict. Infrastructure failure is not evidence
    about the world.

    python research/b0_8_holder_terms/bounded_residual_consideration_d7_6r.py
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import pypdf                                                  # noqa: E402
from core.b0_canonical_hash import canonical_sha256          # noqa: E402
import holder_consideration_semantics_d7_2_1 as SEM          # noqa: E402

D76 = os.path.join(HERE, "disappearing_party_edoc_consideration_d7_6.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_6_edoc_raw")
OUT = os.path.join(HERE, "bounded_residual_consideration_d7_6r.json")

BASE = "https://doc.twse.com.tw/server-java/t57sb01"
H = {"User-Agent": "Mozilla/5.0", "Referer": BASE}
FORM = {**H, "Content-Type": "application/x-www-form-urlencoded"}

MAX_DOCS = 10
MAX_RETRY = 3
PACE = 1.5

POP = {
    "3562": ("頂晶", "新晶"),
    "5818": ("華僑商業銀行", "花旗"),
    "8705": ("東隆五金", "史丹利"),
    "3582": ("凌耀", "威世"),
}


def req(data, tries=MAX_RETRY):
    """One request with a FRESH session; bounded retries; ('' , False) on failure."""
    for i in range(tries):
        try:
            op = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor())
            r = urllib.request.Request(
                BASE, data=urllib.parse.urlencode(data).encode(), headers=FORM)
            raw = op.open(r, timeout=60).read().decode("utf-8", "replace")
            return raw, op
        except Exception:                                     # noqa: BLE001
            time.sleep(2.0 * (i + 1))
    return "", None


def list_docs(co):
    """(files, transport_ok). transport_ok=False means infrastructure failure."""
    files, ok = [], False
    for mtype in ("F", "A"):
        raw, _ = req({"step": "1", "colorchg": "1", "mtype": mtype,
                      "co_id": co, "year": ""})
        if not raw:
            continue
        ok = True
        for fn in re.findall(r"(\d{4}_%s_\w+\.pdf)" % co, raw):
            files.append((fn, mtype))
        time.sleep(PACE)
    return sorted(set(files)), ok


def fetch(co, fn, kind):
    cp = os.path.join(RAW, "%s_%s" % (co, fn))
    if os.path.exists(cp):
        return open(cp, "rb").read()
    raw, op = req({"step": "9", "kind": kind, "co_id": co, "filename": fn})
    if not raw or op is None:
        return None
    m = re.search(r"href='(/pdf/[^']+\.pdf)'", raw)
    if not m:
        return None
    for i in range(MAX_RETRY):
        try:
            data = op.open(urllib.request.Request(
                "https://doc.twse.com.tw" + m.group(1), headers=H),
                timeout=120).read()
            os.makedirs(os.path.dirname(cp), exist_ok=True)
            open(cp, "wb").write(data)
            time.sleep(PACE)
            return data
        except Exception:                                     # noqa: BLE001
            time.sleep(2.0 * (i + 1))
    return None


def text_of(data):
    try:
        rd = pypdf.PdfReader(io.BytesIO(data))
        return "".join(p.extract_text() or "" for p in rd.pages), len(rd.pages)
    except Exception:                                         # noqa: BLE001
        return "", 0


def pick(docs):
    """Final vintage first, then the previous one; hard cap MAX_DOCS."""
    years = sorted({fn.split("_")[0] for fn, _ in docs})
    ordered = []
    for y in reversed(years[-2:]):
        ordered += [(fn, k) for fn, k in docs if fn.split("_")[0] == y]
    return ordered[:MAX_DOCS], years


def run(co, disp, cp_stem):
    docs, ok = list_docs(co)
    if not ok:
        return {"result": "ACQUISITION_ERROR", "semantics": "UNKNOWN",
                "reason": "listing transport failed within retry budget "
                          "(rate-limit/timeout) -- NOT evidence of absence",
                "docs_listed": None, "docs_inspected": 0,
                "holder_security": False, "holder_cash": False}
    if not docs:
        return {"result": "NOT_READY_SOURCE_ACQUISITION", "semantics": "UNKNOWN",
                "reason": "no documents returned for this issuer on the e-doc "
                          "surface within budget",
                "docs_listed": 0, "docs_inspected": 0,
                "holder_security": False, "holder_cash": False}
    cand, years = pick(docs)
    hsec = hcash = False
    inspected, image_only, linked, evidence = 0, [], None, None
    for fn, kind in cand:
        data = fetch(co, fn, kind)
        if not data:
            continue
        txt, pages = text_of(data)
        inspected += 1
        same_txn = (cp_stem in txt) or ("股份轉換" in txt) or ("合併" in txt)
        if not txt.strip() and pages:
            image_only.append(fn)          # OCR candidate only if same-transaction
            continue
        if not same_txn:
            continue
        cls = SEM.classify_bundle(txt)     # frozen grammar
        if cls["holder_receives_security"] or cls["holder_receives_cash"]:
            if not linked:
                linked, evidence = fn, cls["evidence"]
            hsec = hsec or cls["holder_receives_security"]
            hcash = hcash or cls["holder_receives_cash"]
    sem = ("MIXED" if hsec and hcash else "STOCK_ONLY" if hsec
           else "CASH_ONLY" if hcash else "UNKNOWN")
    res = {"MIXED": "MIXED_ESTABLISHED", "STOCK_ONLY": "STOCK_ONLY_ESTABLISHED",
           "CASH_ONLY": "CASH_ONLY_ESTABLISHED",
           "UNKNOWN": "NOT_READY_SOURCE_ACQUISITION"}[sem]
    return {"result": res, "semantics": sem, "docs_listed": len(docs),
            "vintages": years[-2:], "docs_inspected": inspected,
            "image_only_candidates": image_only,
            "holder_security": hsec, "holder_cash": hcash,
            "linked_doc": linked, "evidence": evidence,
            "reason": None if sem != "UNKNOWN" else
            "budgeted document set inspected; no same-transaction holder-"
            "consideration statement extracted (not a boundary claim)"}


def main() -> int:
    d76 = json.load(open(D76, encoding="utf-8"))
    prior = d76["per_event"]

    results = {}
    for co, (disp, cp) in POP.items():
        r = run(co, disp, cp)
        results[co] = {"disappearing": disp, "counterparty_stem": cp, **r}
        print("%-5s %-12s -> %-30s sec=%s cash=%s listed=%s inspected=%s doc=%s"
              % (co, disp, r["result"], r["holder_security"], r["holder_cash"],
                 r.get("docs_listed"), r.get("docs_inspected"),
                 r.get("linked_doc")), flush=True)
        time.sleep(4.0)

    # ---- updated TPEx-59 census (D7.6 base: 29/3/22, unknown 5) ----------
    add_stock = sum(1 for v in results.values() if v["semantics"] == "STOCK_ONLY")
    add_cash = sum(1 for v in results.values() if v["semantics"] == "CASH_ONLY")
    add_mixed = sum(1 for v in results.values() if v["semantics"] == "MIXED")
    stock = 29 + add_stock
    mixed = 3 + add_mixed
    cash = 22 + add_cash
    unknown = 59 - stock - mixed - cash

    unresolved = {c: results[c]["result"] for c in results
                  if results[c]["semantics"] == "UNKNOWN"}
    unresolved["6514"] = "UNKNOWN_CARRIED_TO_D8_0_READINESS"

    out = {
        "record": "B0_8_D7_6R_BOUNDED_RESIDUAL_CONSIDERATION",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_6_closure_sha256": d76["closure_sha256"]},
        "budget_enforced": {
            "population": list(POP), "excluded_by_instruction": ["6514"],
            "surface": "disappearing-party MOPS e-document archive only",
            "max_documents_per_event": MAX_DOCS, "max_transport_retries": MAX_RETRY,
            "fresh_session_per_request": True, "full_history_crawl": False,
            "grammar_modified": False,
            "ocr_used": False,
            "ocr_policy": "permitted only for an identified same-transaction "
                          "candidate with an image-only decisive page",
        },
        "infrastructure_failure_is_not_absence": True,
        "boundary_verdicts_issued": 0,
        "per_event": results,
        "TPEX_59_census": {
            "STOCK_ONLY": stock, "MIXED": mixed, "CASH_ONLY": cash,
            "UNKNOWN": unknown,
            "CONFIRMED_STOCK_BEARING": stock + mixed,
            "denominator_closed": unknown == 0,
            "unknown_detail": unresolved,
            "reconciliation_total": stock + mixed + cash + unknown,
        },
        "D7_CONSIDERATION_DISCOVERY": "PERMANENTLY_CLOSED",
        "next_stage": "D8.0 158-event canonical extraction readiness freeze",

        # invariants
        "consideration_grammar_changed": False,
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
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

    c = out["TPEX_59_census"]
    print("\nTPEX_59: STOCK %d | MIXED %d | CASH %d | UNKNOWN %d"
          % (c["STOCK_ONLY"], c["MIXED"], c["CASH_ONLY"], c["UNKNOWN"]))
    print("confirmed stock-bearing:", c["CONFIRMED_STOCK_BEARING"],
          "| denominator closed:", c["denominator_closed"])
    print("reconciliation:", c["reconciliation_total"])
    print("D7 consideration discovery: PERMANENTLY_CLOSED")
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
