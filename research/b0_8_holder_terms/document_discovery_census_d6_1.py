# -*- coding: utf-8 -*-
"""B0.8 · D6.1 · rerun classification under the frozen D6.1 router.

Order matters and is enforced here: the D6.1 freeze record is written BEFORE any
classification runs, and the v1.4 census is read from the sealed evidence copy
rather than from the live file, so the historical result cannot drift.

THREE THINGS HAPPEN, IN THIS ORDER

  1. DISCOVERY CONFORMANCE. The v1.4 corpus was discovered through the
     DATE-keyed sweep because every legacy code-keyed door refuses this
     population. The MOPS v2 list API does not refuse it, so the same window is
     now enumerated a second time, BY CODE, and the two corpora are compared.
     Agreement is evidence the D4 discovery was complete; a delta is reported
     per event and the union becomes the D6.1 corpus.

  2. BODY ACQUISITION. Every document still lacking a body gets an acquisition
     state from the source rather than an assumption. R3 is company-keyed -- the
     refusal names the company, not the document -- so it is attempted ONCE per
     security_id and the answer is recorded against that company's documents.

  3. CLASSIFICATION under D6.1: 「終止櫃檯買賣」 in the event vocabulary,
     linkage judged over the event's document BUNDLE, parties extracted by ROLE.

NOT AUTHORIZED AND NOT DONE: holder-term extraction, reconstruction
classification, CA rebuild, state rebuild, replay, NAV, performance, gates.

    python research/b0_8_holder_terms/document_discovery_census_d6_1.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import official_document_router_d6_1 as D                  # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

SEALED = os.path.join(HERE, "d6_1_historical",
                      "document_discovery_census_v1_4.json")
OUT = os.path.join(HERE, "document_discovery_census_d6_1.json")
FREEZE = os.path.join(HERE, "router_freeze_record_d6_1.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                   "document_census_raw")
V2RAW = os.path.join(RAW, "v2_code_keyed")
POLITE = 0.45


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path, raw: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def _v2(api: str, payload: dict, cache: str | None = None):
    if cache and os.path.exists(cache):
        raw = open(cache, "rb").read()
        return raw, json.loads(raw.decode("utf-8", "replace")), None
    body = json.dumps(payload).encode()
    err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "https://mops.twse.com.tw/mops/api/" + api, data=body,
                headers=D.V2_HEADERS)
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            time.sleep(POLITE)
            if cache:
                _write(cache, raw)
            return raw, json.loads(raw.decode("utf-8", "replace")), None
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:140])
            time.sleep(2.0 * (attempt + 1))
    return None, None, err


def main() -> int:
    v14 = json.load(open(SEALED, encoding="utf-8"))
    ident = D.router_identity()

    freeze = {
        "record": "B0_8_D6_1_ROUTER_FREEZE",
        "frozen_before_reclassification": True,
        "b0_8_state": "WIP, UNSEALED",
        "preserved_v1_4_census": {
            "path": os.path.relpath(SEALED, REPO),
            "sha256": _sha(open(SEALED, "rb").read()),
            "counts": v14["counts"],
            "router_sha256": v14["router_sha256"],
            "status": "HISTORICAL EVIDENCE -- not rewritten, not reclassified",
        },
        "audit_findings_recorded": {
            "discovery_under_inclusions": [
                "A: 「終止櫃檯買賣」 absent from the event-linkage vocabulary",
                "B: linkage tested per document while the corpus splits it "
                "across the filer's announcements in the same window",
                "C: transaction-party extraction positional rather than "
                "role-based, admitting market operators and filing recipients",
            ],
            "acquisition_state_conflation": (
                "OFFICIAL_EVENT_DOCUMENT_NONE conflated 'no document "
                "discovered' with 'documents discovered, bodies never "
                "acquired'; 635 of 781 v1.4 bodies were withheld by the source"),
        },
        "router_sha256": ident["router_sha256"],
        "router": ident["payload"],
    }
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(freeze, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("D6.1 frozen  :", ident["router_sha256"], flush=True)

    # ---- 1 · discovery conformance, by code ---------------------------------
    conformance, v2_rows_by_event, v2_prov = {}, {}, []
    for r in v14["results"]:
        sid = r["security_id"]
        lo, hi = (date.fromisoformat(x) for x in r["discovery_window"])
        found, errs = {}, []
        for yr in sorted({lo.year, hi.year}):
            cache = os.path.join(V2RAW, "%s_%d.json" % (sid, yr))
            raw, js, err = _v2("t05st01",
                               {"companyId": sid, "year": str(yr - 1911),
                                "month": "all", "firstDay": "", "lastDay": ""},
                               cache)
            if raw is None:
                errs.append({"year": yr, "error": err})
                continue
            v2_prov.append({"security_id": sid, "year": yr,
                            "raw_sha256": _sha(raw), "bytes": len(raw),
                            "code": js.get("code")})
            for row in ((js.get("result") or {}).get("data") or []):
                try:
                    co, _abbr, roc_d, tm, _subj, params = row[:6]
                except ValueError:
                    continue
                when = V14.roc_to_date(roc_d)
                if not (lo <= when <= hi) or co != sid:
                    continue
                p = params.get("parameters", {})
                did = D.document_id(
                    sid, "%04d%02d%02d" % (when.year, when.month, when.day),
                    tm.replace(":", ""), str(p.get("serialNumber", "")))
                found[did] = {"document_id": did, "subject": _subj,
                              "publication_date": when.isoformat(),
                              "market_kind": p.get("marketKind"),
                              "enter_date": p.get("enterDate"),
                              "serial_number": p.get("serialNumber")}
        v2_rows_by_event[r["event_id"]] = found
        swept = {D.canonicalize_document_id(a["document_id"])
                 for a in r["documents"]}
        conformance[r["event_id"]] = {
            "security_id": sid,
            "date_keyed_sweep": len(swept),
            "v2_code_keyed": len(found),
            "only_in_sweep": sorted(swept - set(found)),
            "only_in_v2": sorted(set(found) - swept),
            "v2_errors": errs,
            "agree": swept == set(found) and not errs,
        }
    agree = sum(1 for c in conformance.values() if c["agree"])
    print("conformance  : %d/%d events agree" % (agree, len(conformance)),
          flush=True)

    # ---- 2 · body acquisition ----------------------------------------------
    company_state, company_msg = {}, {}
    for r in v14["results"]:
        sid = r["security_id"]
        if sid in company_state:
            continue
        seen = {D.canonicalize_document_id(a["document_id"])
                for a in r["documents"]}
        need = [a for a in r["documents"] if not a.get("body_retrieved")]
        need += [d for k, d in v2_rows_by_event[r["event_id"]].items()
                 if k not in seen]
        if not need:
            company_state[sid] = D.BODY_RETRIEVED
            continue
        probe = need[0]
        did = probe["document_id"]
        _co, dt, tm, sq = did.split(":")[1:]
        cache = os.path.join(V2RAW, "detail_probe_%s.json" % sid)
        raw, js, err = _v2("t05st01_detail",
                           {"serialNumber": sq,
                            "enterDate": D.roc_compact(
                                date(int(dt[:4]), int(dt[4:6]), int(dt[6:]))),
                            "marketKind": probe.get("market_kind") or "pub",
                            "companyId": sid}, cache)
        if raw is None:
            company_state[sid] = D.BODY_UNREACHABLE_TRANSPORT
            company_msg[sid] = err
        elif js.get("code") == 200 and js.get("result"):
            company_state[sid] = D.BODY_RETRIEVED
            company_msg[sid] = "v2 detail served"
        else:
            company_state[sid] = D.BODY_WITHHELD_BY_SOURCE
            company_msg[sid] = js.get("message")
    print("acquisition  :", dict(Counter(company_state.values())), flush=True)

    # ---- 3 · classification -------------------------------------------------
    results, counts = [], Counter()
    acq_doc = Counter()
    for r in v14["results"]:
        sid, eid = r["security_id"], r["event_id"]
        prov = v14["document_provenance"]
        filer = tuple(x for x in (
            (r["authoritative_termination_record"] or {}).get("name"),
            *(a.get("company_short") for a in r["documents"])) if x)
        docs, assessed = [], []
        known = {D.canonicalize_document_id(a["document_id"])
                 for a in r["documents"]}
        merged = list(r["documents"]) + [
            d for k, d in v2_rows_by_event[eid].items() if k not in known]
        for a in merged:
            did = D.canonicalize_document_id(a["document_id"])
            p = prov.get(a["document_id"], {})
            body_ok = bool(p.get("body_retrieved"))
            text = a.get("subject", "")
            if body_ok and p.get("preserved_at"):
                path = os.path.join(REPO, p["preserved_at"])
                if os.path.exists(path):
                    text = V14._plain(
                        open(path, "rb").read().decode("utf-8", "replace"))
            state = (D.BODY_RETRIEVED if body_ok
                     else company_state.get(sid, D.BODY_WITHHELD_BY_SOURCE))
            acq_doc[state] += 1
            asmt = D.assess_document(text, filer)
            asmt.update({
                "document_id": did,
                "source_agency": "MOPS 公開資訊觀測站",
                "publication_date": a.get("publication_date"),
                "subject": a.get("subject"),
                "acquisition_state": state,
                "assessed_on": ("document_body" if body_ok
                                else "announcement_row_subject"),
                "raw_sha256": p.get("raw_sha256"),
                "preserved_at": p.get("preserved_at"),
                "discovered_by": ("date_keyed_sweep" if did in known
                                  else "v2_code_keyed_only"),
                "legacy_document_id": (a["document_id"]
                                       if a["document_id"] != did else None),
            })
            assessed.append(asmt)
            docs.append(did)
        verdict = D.classify_bundle(assessed)
        counts[verdict["classification"]] += 1
        results.append({
            "event_id": eid, "security_id": sid,
            "canonical_event_date": r["canonical_event_date"],
            "status_reason": r["status_reason"],
            "market_lineage": r["market_lineage"],
            "authoritative_termination_record":
                r["authoritative_termination_record"],
            "discovery_window": r["discovery_window"],
            "documents_found": len(assessed),
            "bodies_retrieved": sum(
                1 for a in assessed
                if a["acquisition_state"] == D.BODY_RETRIEVED),
            "company_acquisition_state": company_state.get(sid),
            "company_acquisition_message": company_msg.get(sid),
            "discovery_conformance": conformance[eid],
            "classification_v1_4": r["classification"],
            "classification": verdict["classification"],
            "discovery_state": verdict["discovery_state"],
            "none_reason": verdict.get("none_reason"),
            "ambiguity_reason": verdict.get("ambiguity_reason"),
            "linkage": verdict.get("linkage"),
            "transaction_parties": verdict["parties"],
            "documents": assessed,
        })

    moved = Counter((r["classification_v1_4"], r["classification"])
                    for r in results if r["classification_v1_4"]
                    != r["classification"])
    none_split = Counter(r["none_reason"] for r in results if r["none_reason"])
    linkage = Counter(r["linkage"] for r in results if r["linkage"])
    market = {}
    for r in results:
        market.setdefault(r["market_lineage"], Counter())[
            r["classification"]] += 1
    cons = Counter()
    for r in results:
        s = {a["apparent_consideration"] for a in r["documents"]
             if a["establishes_transaction"]}
        if not s:
            continue
        cons["mixed" if ("mixed" in s or s >= {"stock", "cash"}) else
             "stock" if s == {"stock"} else
             "cash" if s == {"cash"} else "none_apparent"] += 1

    out = {
        "record": "B0_8_D6_1_OFFICIAL_EVENT_DOCUMENT_DISCOVERY_CENSUS",
        "b0_8_state": "WIP, UNSEALED",
        "router_sha256": ident["router_sha256"],
        "supersedes_for_classification_only": v14["census_sha256"],
        "preserved_historical_census": {
            "path": os.path.relpath(SEALED, REPO),
            "counts": v14["counts"],
            "status": "unchanged historical evidence",
        },
        "total": len(results),
        "counts": {c: counts.get(c, 0) for c in V14.DOC_CLASSES},
        "counts_v1_4": v14["counts"],
        "reclassification_moves": {"%s -> %s" % k: v
                                   for k, v in sorted(moved.items())},
        "none_decomposition": dict(none_split),
        "linkage_basis": dict(linkage),
        "by_market_lineage_and_class": {k: dict(v) for k, v in market.items()},
        "events_by_apparent_consideration_of_transaction_documents": dict(cons),
        "discovery_conformance": {
            "events_where_code_keyed_and_date_keyed_agree": agree,
            "events_total": len(conformance),
            "documents_only_in_date_keyed_sweep": sum(
                len(c["only_in_sweep"]) for c in conformance.values()),
            "documents_only_in_v2_code_keyed": sum(
                len(c["only_in_v2"]) for c in conformance.values()),
            "events_with_v2_errors": sum(
                1 for c in conformance.values() if c["v2_errors"]),
        },
        "body_acquisition": {
            "documents_by_acquisition_state": dict(acq_doc),
            "companies_by_acquisition_state": dict(
                Counter(company_state.values())),
            "routes": list(D.ACQUISITION_ROUTES),
            "completeness_gap": (
                "R4 (v2 signed redirect to the legacy detail page) could not be "
                "tested end to end: the target endpoint closes the connection "
                "for a LIVE control company as well, so it is a transport "
                "block on this network path rather than a source refusal"),
        },
        "v2_provenance": v2_prov,
        "results": results,
        "holder_term_extraction_performed": False,
        "reconstruction_classification_performed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_computed": False,
        "performance_inspected": False,
        "gates_evaluated": False,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\ntotal                    : %d" % out["total"])
    for c in V14.DOC_CLASSES:
        print("  %-38s %d   (v1.4: %d)"
              % (c, out["counts"][c], v14["counts"][c]))
    print("moves                    : %s" % out["reclassification_moves"])
    print("NONE decomposition       : %s" % out["none_decomposition"])
    print("linkage basis            : %s" % out["linkage_basis"])
    print("conformance              : %s" % out["discovery_conformance"])
    print("acquisition (documents)  : %s"
          % out["body_acquisition"]["documents_by_acquisition_state"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
