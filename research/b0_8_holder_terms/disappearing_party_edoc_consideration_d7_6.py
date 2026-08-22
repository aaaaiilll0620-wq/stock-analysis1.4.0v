# -*- coding: utf-8 -*-
"""B0.8 · D7.6 · disappearing-party ELECTRONIC-DOCUMENT consideration acquisition.

The methodological correction that makes this stage possible: a refusal on the
MOPS material-announcement endpoint (ajax_t05st01, D7.0b-2) is NOT a refusal of
the MOPS electronic-document archive (doc.twse.com.tw/server-java/t57sb01). The
archive retains a delisted issuer's own filed annual reports, prospectuses and
shareholder-meeting notices -- and those state, in the disappearing party's own
first-party words, what the holder receives in the exit.

So for the D7.5 residuals we go to the DISAPPEARING company's own electronic
documents (not the survivor's), fetch its final-vintage filings, and classify the
holder consideration instrument with the FROZEN D7.2.1 grammar (unchanged). Same-
transaction linkage is the disappearing party's own document naming the merger /
share-conversion with its counterparty.

    6514 (芮特-KY) has zero documents on this surface -> it remains a genuine
    foreign public-authoritative boundary; this stage does not manufacture one.

Values (ratios/amounts/dates) are read only to fix the instrument class; none is
materialised into canonical holder terms.

    python research/b0_8_holder_terms/disappearing_party_edoc_consideration_d7_6.py
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

D75 = os.path.join(HERE, "consideration_semantics_source_closure_d7_5.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_6_edoc_raw")
OUT = os.path.join(HERE, "disappearing_party_edoc_consideration_d7_6.json")

BASE = "https://doc.twse.com.tw/server-java/t57sb01"
H = {"User-Agent": "Mozilla/5.0", "Referer": BASE}
FORM = {**H, "Content-Type": "application/x-www-form-urlencoded"}

# D7.5 residuals -> (disappearing name, counterparty/survivor name)
RESID = {
    "5384": ("捷元", "鑫聯大投資控股"),
    "5491": ("連展", "連展投資控股"),
    "3562": ("頂晶", "新晶投資控股"),
    "5818": ("華僑商業銀行", "花旗"),
    "8705": ("東隆五金", "史丹利"),
    "3582": ("凌耀", "威世光電"),
    "6514": ("芮特", "UMT"),
}


def _post(data, tries=4):
    """Fresh opener per call; retry so a transient empty/timeout is not read as
    'no documents' (which would fabricate a boundary)."""
    last = ""
    for i in range(tries):
        try:
            op = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor())
            req = urllib.request.Request(
                BASE, data=urllib.parse.urlencode(data).encode(), headers=FORM)
            raw = op.open(req, timeout=60).read().decode("utf-8", "replace")
            return raw, op
        except Exception as exc:                              # noqa: BLE001
            last = "%s" % exc
            time.sleep(1.2 * (i + 1))
    return "ERR:" + last, None


def list_docs(co, tries=4):
    """(files, listing_ok). listing_ok distinguishes genuine-empty from failure."""
    files, ok = [], False
    for mtype in ("F", "A"):
        got = False
        for i in range(tries):
            raw, _ = _post({"step": "1", "colorchg": "1", "mtype": mtype,
                            "co_id": co, "year": ""})
            if not raw.startswith("ERR") and "t57sb01" in raw.lower() or (
                    isinstance(raw, str) and "readfile2" in raw):
                got = True
                for fn in re.findall(r"(\d{4}_%s_\w+\.pdf)" % co, raw):
                    files.append((fn, mtype))
                break
            time.sleep(1.0 * (i + 1))
        ok = ok or got
    return sorted(set(files)), ok


def fetch_pdf(co, fn, kind):
    cp = os.path.join(RAW, "%s_%s" % (co, fn))
    if os.path.exists(cp):
        return open(cp, "rb").read()
    raw, op = _post({"step": "9", "kind": kind, "co_id": co, "filename": fn})
    if op is None:
        return None
    m = re.search(r"href='(/pdf/[^']+\.pdf)'", raw)
    if not m:
        return None
    try:
        data = op.open(urllib.request.Request(
            "https://doc.twse.com.tw" + m.group(1), headers=H), timeout=120).read()
    except Exception:                                         # noqa: BLE001
        return None
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    open(cp, "wb").write(data)
    time.sleep(0.8)
    return data


def pdf_text(data):
    try:
        rd = pypdf.PdfReader(io.BytesIO(data))
        return "".join(p.extract_text() or "" for p in rd.pages)
    except Exception:                                         # noqa: BLE001
        return ""


def classify(co, disp, cp_name):
    docs, ok = list_docs(co)
    if not ok:
        return {"docs_on_edoc_surface": None, "listing_ok": False,
                "result": "ROUTING_OR_ACQUISITION_ERROR", "semantics": "UNKNOWN",
                "holder_security": False, "holder_cash": False,
                "evidence": None, "linked_doc": None}
    if not docs:
        return {"docs_on_edoc_surface": 0, "listing_ok": True,
                "result": "PUBLIC_AUTHORITATIVE_BOUNDARY", "semantics": "UNKNOWN",
                "holder_security": False, "holder_cash": False,
                "evidence": None, "linked_doc": None}
    years = sorted({fn.split("_")[0] for fn, _ in docs})
    late = years[-1:]                     # only the final (delisting) vintage
    cp_stem = re.sub(r"股份有限公司$", "", cp_name)
    hsec = hcash = False
    evidence, linked_doc, scanned = None, None, 0
    todo = [(fn, k) for fn, k in docs if fn.split("_")[0] in late][:14]
    for fn, kind in todo:
        data = fetch_pdf(co, fn, kind)
        if not data:
            continue
        txt = pdf_text(data)
        if not txt:
            continue
        scanned += 1
        # same-transaction linkage: counterparty named, or a merger/conversion doc
        if cp_stem not in txt and "股份轉換" not in txt and "合併" not in txt:
            continue
        cls = SEM.classify_bundle(txt)
        if cls["holder_receives_security"] or cls["holder_receives_cash"]:
            if not linked_doc:
                linked_doc, evidence = fn, cls["evidence"]
            hsec = hsec or cls["holder_receives_security"]
            hcash = hcash or cls["holder_receives_cash"]
    sem = ("MIXED" if hsec and hcash else "STOCK_ONLY" if hsec
           else "CASH_ONLY" if hcash else "UNKNOWN")
    result = ("STOCK_ONLY_ESTABLISHED" if sem == "STOCK_ONLY"
              else "CASH_ONLY_ESTABLISHED" if sem == "CASH_ONLY"
              else "MIXED_ESTABLISHED" if sem == "MIXED"
              else "SOURCE_FAMILY_NOT_EXHAUSTED")
    return {"docs_on_edoc_surface": len(docs), "listing_ok": True,
            "docs_scanned": scanned, "years": years[-3:], "result": result,
            "semantics": sem, "holder_security": hsec, "holder_cash": hcash,
            "evidence": evidence, "linked_doc": linked_doc}


DONE = ("STOCK_ONLY_ESTABLISHED", "CASH_ONLY_ESTABLISHED", "MIXED_ESTABLISHED",
        "PUBLIC_AUTHORITATIVE_BOUNDARY")


def main() -> int:
    prior = {}
    if os.path.exists(OUT):
        prior = json.load(open(OUT, encoding="utf-8")).get("per_event", {})
    per_event = {}
    for sid, (disp, cp) in RESID.items():
        if prior.get(sid, {}).get("result") in DONE:
            per_event[sid] = prior[sid]                       # keep resolved
            print("%-5s %-14s -> %-30s (kept)" % (sid, disp,
                                                  prior[sid]["result"]), flush=True)
            continue
        r = classify(sid, disp, cp)
        per_event[sid] = {"disappearing": disp, "counterparty": cp, **r}
        print("%-5s %-14s -> %-30s sec=%s cash=%s doc=%s"
              % (sid, disp, r["result"], r["holder_security"],
                 r["holder_cash"], r.get("linked_doc")), flush=True)
        time.sleep(6.0)                                       # ease throttling

    newly_stock = [s for s in per_event
                   if per_event[s]["semantics"] == "STOCK_ONLY"]
    newly_cash = [s for s in per_event if per_event[s]["semantics"] == "CASH_ONLY"]
    newly_mixed = [s for s in per_event if per_event[s]["semantics"] == "MIXED"]
    boundary = [s for s in per_event
                if per_event[s]["result"] == "PUBLIC_AUTHORITATIVE_BOUNDARY"]
    still = [s for s in per_event
             if per_event[s]["result"] in ("SOURCE_FAMILY_NOT_EXHAUSTED",
                                           "ROUTING_OR_ACQUISITION_ERROR")]

    final_stock_only = 27 + len(newly_stock)
    final_mixed = 3 + len(newly_mixed)
    final_cash = 22 + len(newly_cash)
    stock_bearing = final_stock_only + final_mixed

    out = {
        "record": "B0_8_D7_6_DISAPPEARING_PARTY_EDOC_CONSIDERATION",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_5_closure_sha256": json.load(
            open(D75, encoding="utf-8"))["closure_sha256"]},
        "method": {
            "surface": "MOPS electronic-document archive (doc.twse.com.tw t57sb01)",
            "distinct_from": "MOPS material-announcement endpoint (refused for "
                             "delisted issuers, D7.0b-2)",
            "party": "the DISAPPEARING company's own filed documents",
            "grammar": "frozen D7.2.1 holder-consideration grammar, unchanged",
            "values_materialised": False,
        },
        "per_event": per_event,
        "newly_stock": newly_stock, "newly_cash": newly_cash,
        "newly_mixed": newly_mixed,
        "still_unknown_boundary": boundary,
        "still_unknown_not_exhausted": still,
        "TPEX_59_final": {
            "STOCK_ONLY": final_stock_only, "MIXED": final_mixed,
            "CASH_ONLY": final_cash,
            "UNKNOWN": len(boundary) + len(still),
            "CONFIRMED_STOCK_BEARING": stock_bearing,
            "consideration_acquisition_boundary": len(boundary),
            "source_family_not_exhausted": len(still),
            "TPEX_59_HOLDER_CONSIDERATION_DENOMINATOR_CLOSED":
                (len(boundary) + len(still)) == 0,
            "reconciliation_total": final_stock_only + final_mixed + final_cash
            + len(boundary) + len(still),
        },
        # invariants
        "consideration_grammar_changed": False,
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
        "termination_branch_reopened": False,
        "cash_settlement_hunting": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "dual_extraction_started": False,
        "prior_artefacts_rewritten": 0,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    t = out["TPEX_59_final"]
    print("\nnewly stock/cash/mixed:", newly_stock, newly_cash, newly_mixed)
    print("boundary/not-exhausted:", boundary, still)
    print("TPEX_59: STOCK", t["STOCK_ONLY"], "MIXED", t["MIXED"],
          "CASH", t["CASH_ONLY"], "UNKNOWN", t["UNKNOWN"])
    print("stock-bearing:", t["CONFIRMED_STOCK_BEARING"],
          "| denominator closed:",
          t["TPEX_59_HOLDER_CONSIDERATION_DENOMINATOR_CLOSED"])
    print("reconciliation:", t["reconciliation_total"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
