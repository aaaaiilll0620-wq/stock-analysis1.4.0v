# -*- coding: utf-8 -*-
"""B0.8 · D4-D8 · the 158-event official-document DISCOVERY census.

Runs the frozen code-first router (official_document_router.py) over EVERY
holder_side_reorganization_exit / NOT_RECONSTRUCTIBLE event in the frozen
register. No sampling, no prioritisation, no ordering by holdings, exposure,
the B0.7 blocker, 8913, ease of reconstruction, market value or performance:
the population is the register sorted by (effective_date, security_id) and the
loop does not know anything else about an event.

D9 · NOTHING CANONICAL MOVES HERE. This stage writes one research record and a
directory of preserved bytes. It does not materialise a single holder term into
the CA ledger, does not re-classify any reconstruction_status, does not touch
the 141 states, starts no replay, computes no NAV and inspects no performance.
Finding terms inside a document is NOT a reconstruction, and D5 says so.

    python research/b0_8_holder_terms/document_discovery_census.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as R          # noqa: E402
from core.b0_canonical_hash import canonical_sha256   # noqa: E402

REGISTER = os.path.join(HERE, "event_register.json")
OUT = os.path.join(HERE, "document_discovery_census.json")
FREEZE = os.path.join(HERE, "router_freeze_record.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                   "document_census_raw")
STATE = os.path.join(RAW, "_progress.json")

POLITE = 0.35
POLITE_DETAIL = 1.1
RATE_LIMIT_BACKOFF = (6, 20, 45, 90)
RETRIES = 3
TPEX_DIRECTORY_YEARS = range(1994, 2027)


# --- transport ---------------------------------------------------------------

def _fetch(url, data=None, headers=None, timeout=180, polite=None):
    """MOPS throttles with a 200 OK page, so the body has to be inspected."""
    err = None
    for attempt in range(RETRIES + len(RATE_LIMIT_BACKOFF)):
        try:
            req = urllib.request.Request(
                url, data=(urllib.parse.urlencode(data).encode()
                           if data is not None else None),
                headers=headers or R.HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            if len(raw) < 20000 and R.is_rate_limited(
                    raw.decode("utf-8", "replace")):
                err = "RateLimited: MOPS served its throttle page (HTTP 200)"
                time.sleep(RATE_LIMIT_BACKOFF[
                    min(attempt, len(RATE_LIMIT_BACKOFF) - 1)])
                continue
            time.sleep(POLITE if polite is None else polite)
            return raw, None
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:160])
            time.sleep(1.5 * (attempt + 1))
    return None, err


def _cached(path):
    """Preserved bytes are the record; a re-run must read them, not re-ask.

    A throttle page is not a record, so it is never served from cache.
    """
    if not os.path.exists(path):
        return None
    raw = open(path, "rb").read()
    if len(raw) < 20000 and R.is_rate_limited(raw.decode("utf-8", "replace")):
        os.remove(path)
        return None
    return raw


def _write(path, raw: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --- stage L · authoritative directories, code-first matching ----------------

def load_directories():
    """Both authoritative termination directories, preserved and hashed.

    D1: the TPEx one is NOT an OpenAPI endpoint. Its absence from the 225
    enumerated OpenAPI endpoints is what NO_TPEX_OPENAPI_DELISTED_DIRECTORY
    recorded, and it says nothing about this surface.
    """
    prov = []
    path = os.path.join(RAW, "directories", "twse_termination.json")
    raw = _cached(path)
    if raw is None:
        raw, err = _fetch(R.TWSE_TERMINATION_DIRECTORY, headers={
            "User-Agent": "Mozilla/5.0"}, timeout=90)
        if raw is None:
            raise SystemExit("TWSE termination directory unavailable: %s" % err)
        _write(path, raw)
    prov.append({"agency": "TWSE", "endpoint": R.TWSE_TERMINATION_DIRECTORY,
                 "raw_sha256": _sha(raw), "bytes": len(raw)})
    twse = {}
    for row in json.loads(raw.decode("utf-8")):
        twse.setdefault(str(row["Code"]), []).append(
            {"date": R.roc_to_date(row["DelistingDate"]).isoformat(),
             "name": row["Company"], "agency": "TWSE",
             "record": "終止上市公司"})

    tpex = {}
    for year in TPEX_DIRECTORY_YEARS:
        path = os.path.join(RAW, "directories", "tpex_%d.json" % year)
        raw = _cached(path)
        if raw is None:
            raw, err = _fetch(R.TPEX_TERMINATION_DIRECTORY,
                              {"code": "", "date": str(year), "reason": "-1",
                               "paging-size": "500", "paging-offset": "0"},
                              headers=R.TPEX_HEADERS, timeout=90)
            if raw is None:
                prov.append({"agency": "TPEx", "endpoint":
                             R.TPEX_TERMINATION_DIRECTORY, "year": year,
                             "error": err})
                continue
            _write(path, raw)
        prov.append({"agency": "TPEx", "endpoint":
                     R.TPEX_TERMINATION_DIRECTORY, "year": year,
                     "raw_sha256": _sha(raw), "bytes": len(raw)})
        for row in json.loads(raw.decode("utf-8"))["tables"][0]["data"]:
            code, name, when, reason = row[0], row[1], row[2], row[3]
            rec = {"date": R.roc_to_date(when).isoformat(), "name": name,
                   "agency": "TPEx", "record": "終止上櫃公司",
                   "legal_basis": reason}
            if rec not in tpex.setdefault(code, []):
                tpex[code].append(rec)
    return twse, tpex, prov


def lineage_for(sid, c, twse, tpex, code_query):
    """Code-first lineage. Name is never consulted, in either direction."""
    def nearest(rows):
        cands = [(abs((date.fromisoformat(r["date"]) - c).days), r)
                 for r in rows]
        cands = [x for x in cands
                 if x[0] <= R.DIRECTORY_MATCH_TOLERANCE_DAYS]
        return sorted(cands, key=lambda x: x[0])[0][1] if cands else None

    a = nearest(twse.get(sid, []))
    b = nearest(tpex.get(sid, []))
    if a and b:
        return R.LINEAGE_BOTH, a, b
    if a:
        return R.LINEAGE_TWSE, a, None
    if b:
        return R.LINEAGE_TPEX, None, b
    return R.LINEAGE_NONE, None, None


# --- main --------------------------------------------------------------------

def main() -> int:
    reg = json.load(open(REGISTER, encoding="utf-8"))
    events = sorted(reg["events"],
                    key=lambda e: (e["effective_date"], e["security_id"]))
    assert len(events) == 158, len(events)

    ident = R.router_identity()
    freeze = {
        "record": "B0_8_OFFICIAL_DOCUMENT_ROUTER_FREEZE",
        "frozen_before_any_corpus_request": True,
        "register_sha256": reg["register_sha256"],
        "policy_schema_sha256": reg["policy_schema_sha256"],
        "router_sha256": ident["router_sha256"],
        "router": ident["payload"],
        # The router was frozen at v1 BEFORE any corpus request. v1.1 and v1.2
        # corrected the post-retrieval D6 predicates only -- the name-token cut,
        # the uniqueness set, and 合併-as-consolidation -- after control
        # documents drawn from companies OUTSIDE the register exposed them, and
        # before any document from the population had been assessed. No
        # correction changed a single request: the surfaces, the window, the
        # segmentation and the query parameters are byte-identical across v1,
        # v1.1 and v1.2, so the acquired corpus is the one v1 asked for.
        "router_version_history": [
            {"version": "1",
             "router_sha256": "13fccc4e008163bfdf07d2577f901878614dee55"
                              "00fb863a0261bc9fba3ea287",
             "state": "frozen before any corpus request; corpus acquired "
                      "under this version"},
            {"version": "1.1",
             "router_sha256": "54b761ec434a6e29862ef06d8a54c4a57fe3b6d8"
                              "dd1f944589bba02bdecfa84c",
             "state": "counterparty token cut back to the last delimiter; "
                      "uniqueness tested on transaction-adjacent names"},
            {"version": "1.2",
             "router_sha256": "51c179102f1e52ee337ac07f0570f5f92282da7e"
                              "77d06e8d52df2f05ebd33d7e",
             "state": "合併 in the accounting sense excluded; MOPS template "
                      "tokens matched in their own right; first full census "
                      "pass ran under this version and returned 1 UNIQUE / "
                      "153 NONE / 4 AMBIGUOUS / 0 ERROR"},
            {"version": "1.4",
             "router_sha256": "e04f411171a472a2e459aee61570afdb5cff7f4a6"
                              "26b729dd992e00516dd059b",
             "state": "MOPS throttle pages (HTTP 200 with 「查詢過於頻繁」) "
                      "detected, retried with backoff and never cached; 106 "
                      "of the 781 v1.3 bodies were that page. The 518 "
                      "date-keyed block responses were verified clean, so the "
                      "discovery layer was never affected. Census reported "
                      "under this version"},
            {"version": "1.3",
             "router_sha256": "e3f32fac0d137677a59c576bad58d5633f2b444e"
                              "ab7f0458f26bb1ad41e305aa",
             "state": "MOPS refusal pages no longer read as document content. "
                      "Found FROM the v1.2 output -- 550 of 781 preserved "
                      "bodies were the refusal page -- so this correction was "
                      "made after an outcome was visible and is disclosed as "
                      "such. It is a defect fix, not a predicate preference: "
                      "v1.2 scored announcements on a page that said nothing. "
                      "Census reported under this version"},
        ],
        "corrections_changed_any_request": False,
        "correction_1_3_made_after_seeing_an_outcome": True,
        "correction_1_3_justification": (
            "reading a source's refusal page as though it were the document it "
            "refused to serve is wrong whichever way it moves the count; the "
            "v1.2 result is preserved in this history so the effect of the fix "
            "is visible"),
        # D2, disclosed here rather than discovered later.
        "adjudication_source_preobservation": True,
        "preobserved_event_ids": [3299, 8913],
        "performance_inspection": False,
        "preobservation_effect_on_routing": (
            "none; both codes enter the loop in register order and the router "
            "has no branch that can see them"),
        "no_tpex_openapi_delisted_directory_means": (
            "no TERMINATED-COMPANY endpoint among the 225 enumerated TPEx "
            "OpenAPI endpoints"),
        "no_tpex_openapi_delisted_directory_does_not_mean": (
            "NO_AUTHORITATIVE_TPEX_HISTORICAL_SOURCE -- the authoritative TPEx "
            "終止上櫃公司 directory exists outside OpenAPI and is used here as "
            "a primary surface"),
    }
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(freeze, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("router frozen  :", ident["router_sha256"])

    twse, tpex, dir_prov = load_directories()
    print("directories    : TWSE %d codes / TPEx %d codes"
          % (len(twse), len(tpex)))

    # Per-event code-keyed TPEx query. Uniform, issued for every event, so no
    # event is treated specially by having been looked up "extra".
    code_query = {}
    for e in events:
        sid = e["security_id"]
        year = e["effective_date"][:4]
        path = os.path.join(RAW, "tpex_code_query", "%s_%s.json" % (sid, year))
        raw = _cached(path)
        if raw is None:
            raw, err = _fetch(R.TPEX_TERMINATION_DIRECTORY,
                              {"code": sid, "date": year, "reason": "-1",
                               "paging-size": "500", "paging-offset": "0"},
                              headers=R.TPEX_HEADERS, timeout=60)
            if raw is None:
                code_query[sid] = {"error": err}
                continue
            _write(path, raw)
        rows = json.loads(raw.decode("utf-8"))["tables"][0]["data"]
        code_query[sid] = {"raw_sha256": _sha(raw), "rows": rows,
                           "params": {"code": sid, "date": year,
                                      "reason": "-1"}}
    print("tpex code query: %d issued" % len(code_query))

    # Which blocks each event needs; blocks fetched once, shared.
    need = {}
    for e in events:
        c = date.fromisoformat(e["effective_date"])
        lo, hi = R.window(c)
        for blk in R.blocks(lo, hi):
            need.setdefault(blk, []).append((e["security_id"], lo, hi,
                                             e["event_id"]))
    order = sorted(need)
    print("mops blocks    : %d distinct" % len(order))

    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) \
        else {"blocks": {}, "rows": {}}
    hits = {e["event_id"]: [] for e in events}
    errors = {e["event_id"]: [] for e in events}
    for k, v in state["rows"].items():
        if k in hits:
            hits[k] = v

    for i, blk in enumerate(order, 1):
        key = "%d-%02d-%02d-%02d" % blk
        if key in state["blocks"]:
            continue
        y, m, b, e_ = blk
        raw, err = _fetch(R.MOPS_ANNOUNCEMENTS, R.list_params(y, m, b, e_))
        if raw is None:
            state["blocks"][key] = {"error": err}
            for sid, lo, hi, eid in need[blk]:
                errors[eid].append({"block": key, "error": err})
        else:
            rows = R.parse_announcement_rows(raw)
            state["blocks"][key] = {"raw_sha256": _sha(raw), "bytes": len(raw),
                                    "rows_parsed": len(rows),
                                    "params": R.list_params(y, m, b, e_)}
            by_code = {}
            for row in rows:
                by_code.setdefault(row.co_id, []).append(row)
            for sid, lo, hi, eid in need[blk]:
                for row in by_code.get(sid, []):
                    when = R.roc_to_date(row.spoke_date_roc)
                    if lo <= when <= hi:
                        hits[eid].append({
                            "document_id": row.document_id,
                            "co_id": row.co_id, "company_short": row.company,
                            "publication_date": when.isoformat(),
                            "spoke_time": row.spoke_time,
                            "seq_no": row.seq_no, "typek": row.typek,
                            "subject": row.subject,
                            "discovery_block": key,
                            "discovery_params": R.list_params(y, m, b, e_),
                            "row_fragment_sha256": _sha(
                                row.raw_fragment.encode("utf-8")),
                            "detail_params": R.detail_params(row)})
        state["rows"] = {k: v for k, v in hits.items() if v}
        if i % 10 == 0 or i == len(order):
            _write(STATE, json.dumps(state, ensure_ascii=False).encode("utf-8"))
            print("  blocks %d/%d  hits so far %d"
                  % (i, len(order), sum(len(v) for v in hits.values())),
                  flush=True)
    _write(STATE, json.dumps(state, ensure_ascii=False).encode("utf-8"))

    # Detail documents, deduplicated by document identity.
    docs = {}
    for eid, rows in hits.items():
        for row in rows:
            docs.setdefault(row["document_id"], row)
    print("detail docs    : %d distinct" % len(docs))
    texts, doc_prov = {}, {}
    for n, (did, row) in enumerate(sorted(docs.items()), 1):
        safe = did.replace(":", "_")
        path = os.path.join(RAW, "documents", safe + ".html")
        raw = _cached(path)
        if raw is None:
            raw, err = _fetch(R.MOPS_ANNOUNCEMENTS, row["detail_params"],
                              timeout=90, polite=POLITE_DETAIL)
            if raw is None:
                doc_prov[did] = {"error": err}
                continue
            _write(path, raw)
        body = R._plain(raw.decode("utf-8", "replace"))
        refused = R.is_refusal(body)
        # A refused body is not content. The announcement ROW is, so that is
        # what gets assessed, and the substitution is recorded per document.
        texts[did] = row["subject"] if refused else body
        doc_prov[did] = {"raw_sha256": _sha(raw), "bytes": len(raw),
                         "preserved_at": os.path.relpath(path, REPO),
                         "body_retrieved": not refused,
                         "assessed_on": ("announcement_row_subject" if refused
                                         else "document_body")}
        if refused:
            doc_prov[did]["source_answer"] = R.BODY_WITHHELD
        if n % 100 == 0:
            print("  details %d/%d" % (n, len(docs)), flush=True)

    # Assessment and D5 classification.
    results, counts = [], Counter()
    for e in events:
        eid, sid = e["event_id"], e["security_id"]
        c = date.fromisoformat(e["effective_date"])
        lin, twrow, tprow = lineage_for(sid, c, twse, tpex, code_query)
        authoritative = twrow or tprow
        filer = tuple(x for x in (
            (twrow or {}).get("name"), (tprow or {}).get("name"),
            *(r.get("company_short") for r in hits[eid])) if x)
        assessed = []
        for row in hits[eid]:
            did = row["document_id"]
            if did not in texts:
                continue
            a = R.assess_document(texts[did], filer)
            a.update({"document_id": did,
                      "body_retrieved": doc_prov.get(did, {}).get(
                          "body_retrieved"),
                      "assessed_on": doc_prov.get(did, {}).get("assessed_on"),
                      "source_agency": "MOPS 公開資訊觀測站 (%s)" % row["typek"],
                      "publication_date": row["publication_date"],
                      "subject": row["subject"],
                      "raw_sha256": doc_prov.get(did, {}).get("raw_sha256"),
                      "preserved_at": doc_prov.get(did, {}).get("preserved_at"),
                      "discovery_query": row["discovery_params"]})
            assessed.append(a)
        errored = bool(errors[eid]) or any(
            "error" in doc_prov.get(r["document_id"], {}) for r in hits[eid])
        cls = R.classify_event(assessed, errored)
        counts[cls] += 1
        linking = [a for a in assessed
                   if a["links_security_transaction_and_event"]]
        results.append({
            "event_id": eid, "security_id": sid,
            "canonical_event_date": e["effective_date"],
            "status_reason": e["status_reason"],
            "market_lineage": lin,
            "authoritative_termination_record": authoritative,
            "authoritative_termination_date": (authoritative or {}).get("date"),
            "tpex_code_query": {k: v for k, v in
                                code_query.get(sid, {}).items() if k != "rows"},
            "tpex_code_query_row_count": len(
                code_query.get(sid, {}).get("rows", [])),
            "discovery_window": [R.window(c)[0].isoformat(),
                                 R.window(c)[1].isoformat()],
            "documents_found": len(assessed),
            "linking_documents": len(linking),
            "classification": cls,
            "ambiguity_reason": (R.ambiguity_reason(assessed)
                                 if cls == R.DOC_AMBIGUOUS else None),
            "transaction_counterparties": sorted({
                n for a in assessed
                if a["links_security_transaction_and_event"]
                for n in a["transaction_counterparties"]}),
            "block_errors": errors[eid],
            "documents": assessed,
        "bodies_retrieved": sum(1 for a in assessed if a.get("body_retrieved")),
        "linking_evidence_is_subject_line_only": bool(linking) and not any(
            a.get("body_retrieved") for a in linking),
        })

    # D7 reporting.
    by_market = Counter(r["market_lineage"] for r in results)
    market_class = {}
    for r in results:
        market_class.setdefault(r["market_lineage"], Counter())[
            r["classification"]] += 1
    consideration = Counter()
    docs_missing_fields = 0
    total_docs = 0
    for r in results:
        for a in r["documents"]:
            total_docs += 1
            consideration[a["apparent_consideration"]] += 1
            if a["apparent_fields_absent"]:
                docs_missing_fields += 1
    linking_consideration = Counter()
    for r in results:
        cons = {a["apparent_consideration"] for a in r["documents"]
                if a["links_security_transaction_and_event"]}
        if not cons:
            continue
        if "mixed" in cons or cons == {"stock", "cash"}:
            linking_consideration["mixed"] += 1
        elif cons == {"stock"}:
            linking_consideration["stock"] += 1
        elif cons == {"cash"}:
            linking_consideration["cash"] += 1
        else:
            linking_consideration["none_apparent"] += 1

    audit = {}
    for sid in ("3299", "8913"):
        row = [r for r in results if r["security_id"] == sid]
        audit[sid] = ({"document_discovered":
                       row[0]["classification"] == R.DOC_UNIQUE,
                       "classification": row[0]["classification"],
                       "documents_found": row[0]["documents_found"],
                       "linking_documents": row[0]["linking_documents"],
                       "market_lineage": row[0]["market_lineage"],
                       "found_by_generic_router": True,
                       "special_request_issued": False}
                      if row else {"in_population": False})

    out = {
        "record": "B0_8_OFFICIAL_EVENT_DOCUMENT_DISCOVERY_CENSUS",
        "stage": "D4-D8 document discovery only",
        "register_sha256": reg["register_sha256"],
        "policy_schema_sha256": reg["policy_schema_sha256"],
        "router_sha256": ident["router_sha256"],
        "population_rule": ("all 158 frozen holder_side_reorganization_exit / "
                           "NOT_RECONSTRUCTIBLE events; no sampling, no "
                           "prioritisation"),
        "total": len(results),
        "counts": {c: counts.get(c, 0) for c in R.DOC_CLASSES},
        "by_market_lineage": dict(by_market),
        "by_market_lineage_and_class": {k: dict(v) for k, v in
                                        market_class.items()},
        "documents_discovered_total": total_docs,
        "documents_by_apparent_consideration": dict(consideration),
        "events_by_apparent_consideration_of_linking_documents":
            dict(linking_consideration),
        "documents_apparently_lacking_one_or_more_frozen_outcome_fields":
            docs_missing_fields,
        "diagnostic_only": ("the consideration and missing-field counts are "
                            "DIAGNOSTIC; no canonical reconstruction outcome "
                            "is classified in this stage"),
        "document_bodies_retrieved": sum(
            1 for v in doc_prov.values() if v.get("body_retrieved")),
        "document_bodies_withheld_by_source": sum(
            1 for v in doc_prov.values() if v.get("body_retrieved") is False),
        "body_withholding_note": (
            "the code-keyed MOPS detail view refuses companies that have "
            "ceased public offering, which is every security in this "
            "population; a withheld body is assessed on its preserved "
            "announcement row subject and is NOT a request error"),
        "events_classified_on_subject_line_only": None,
        "ambiguity_reasons": dict(Counter(
            r["ambiguity_reason"] for r in results if r["ambiguity_reason"])),
        "audit_3299_8913": audit,
        "directory_provenance": dir_prov,
        "block_manifest": state["blocks"],
        "document_provenance": doc_prov,
        "results": results,
        # D9
        "canonical_values_materialized": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "reconstruction_classifications_unchanged": True,
        "dual_extraction_performed": False,
        "events_classified_reconstructible": 0,
        "replay_started": False,
        "nav_computed": False,
        "performance_inspected": False,
        "gates_evaluated": False,
    }
    out["events_classified_on_subject_line_only"] = sum(
        1 for r in results if r["linking_evidence_is_subject_line_only"])
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\ntotal                    : %d" % out["total"])
    for c in R.DOC_CLASSES:
        print("  %-38s %d" % (c, out["counts"][c]))
    print("by market lineage        : %s" % dict(by_market))
    print("documents discovered     : %d" % total_docs)
    print("consideration (documents): %s" % dict(consideration))
    print("3299 / 8913              : %s"
          % {k: v.get("classification") for k, v in audit.items()})
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
