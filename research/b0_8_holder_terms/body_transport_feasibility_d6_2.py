# -*- coding: utf-8 -*-
"""B0.8 · D6.2 · authoritative body transport feasibility. Six-document design.

ONE QUESTION (F2): can an authoritative MOPS announcement body that is ALREADY
KNOWN TO EXIST be acquired through a deterministic official transport path?

Not extraction. Not reconstruction. Not a bulk retry. The D6.1 census, its
router and its counts are untouched -- UNIQUE 17 / AMBIGUOUS 25 / NONE 116
(= 7 NO_DOCUMENT_DISCOVERED + 109 DOCUMENT_DISCOVERED_BUT_LINKAGE_NOT_
ESTABLISHED) / ERROR 0 -- and nothing here can move them. Discovery existence,
linkage status and body availability are three separate dimensions and this
stage touches only the third.

F3 · THE SAMPLE IS FOUR DOCUMENTS, NOT SIX, AND THAT IS THE RULE WORKING

The three strata are taken from the preserved 781-document register:

    BODY_AVAILABLE                            146 documents
    BODY_REFUSED                              635 documents
    BODY_TRANSPORT_UNRESOLVED_OR_UNAVAILABLE    0 documents

The third stratum is EMPTY. TRANSPORT_UNRESOLVED is presently a property of
ROUTE R4, not of any document: every document in the register either has a
preserved body or carries an explicit official refusal naming its company.
F3 says a short stratum is used as-is and never topped up from another, so the
sample is 2 + 2 + 0 = 4.

Selection is `sha256(canonical_document_id)` ascending, first two per stratum.
It cannot see holdings, blocker status, 3299, 8913, consideration,
reconstructibility or performance -- the sort key is the identity string alone.

F4 · THE TRANSPORT PROTOCOL, FROZEN BEFORE THE FIRST REQUEST

Ordered, and using only state the authoritative MOPS flow itself supplies: its
cookies, its session, its referer, its signed URL, and the official request that
a user necessarily makes immediately before opening a detail view. No
third-party mirror, no cached copy, no TEJ, no search-engine cache, no archive.

    P0  SESSION_BOOTSTRAP    GET  mops.twse.com.tw/mops/           (cookie jar)
    P1  CONTEXT_LIST         POST /mops/api/t05st01                (the official
                             code-keyed list request that precedes a detail
                             click; establishes the row context)
    P2  SIGNED_URL           POST /mops/api/redirectToOld          (apiName
                             t05st01_detail + the row's own parameters)
    P3  FETCH_AS_ISSUED      GET  the signed URL exactly as issued (mopsov host)
    P4  FETCH_ON_APP_HOST    GET  the same signed blob on the app host
    P5  POST_ON_APP_HOST     POST the same signed blob as form data
    P6  REISSUE_AND_REFETCH  repeat P2 then P3 after a fixed delay, on the
                             assumption that the signed URL is ephemeral

The ladder stops at the first step that returns an actual announcement body.

F7 · CLASSIFICATION, AND THE TWO RULES THAT KEEP IT HONEST

    BODY_AVAILABLE          a real announcement body: the response carries the
                            MOPS template marker and no refusal or throttle text
    OFFICIAL_SOURCE_REFUSED the authoritative source RETURNED a refusal
    TRANSPORT_UNRESOLVED    no official response was obtained -- socket closed,
                            connection reset, or an empty body
    REQUEST_ERROR           the source answered, but about the request: a
                            throttle page or a parameter rejection

An HTTP 200 carrying a refusal or throttle page is never BODY_AVAILABLE, and a
socket failure is never OFFICIAL_SOURCE_REFUSED -- a refusal has to be something
the source actually said.

    python research/b0_8_holder_terms/body_transport_feasibility_d6_2.py
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import official_document_router_d6_1 as D61                # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

CENSUS_D61 = os.path.join(HERE, "document_discovery_census_d6_1.json")
SEALED_V14 = os.path.join(HERE, "d6_1_historical",
                          "document_discovery_census_v1_4.json")
OUT = os.path.join(HERE, "body_transport_feasibility_d6_2.json")
FREEZE = os.path.join(HERE, "transport_protocol_freeze_d6_2.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_2_transport_raw")
V2RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                     "document_census_raw", "v2_code_keyed")

APP = "https://mops.twse.com.tw"
API = APP + "/mops/api/"
LEGACY_DETAIL_PATH = "/mops/web/t05st01_detail"

BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
                   "Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": APP + "/",
}

BODY_AVAILABLE = "BODY_AVAILABLE"
OFFICIAL_SOURCE_REFUSED = "OFFICIAL_SOURCE_REFUSED"
TRANSPORT_UNRESOLVED = "TRANSPORT_UNRESOLVED"
REQUEST_ERROR = "REQUEST_ERROR"
CLASSES = (BODY_AVAILABLE, OFFICIAL_SOURCE_REFUSED, TRANSPORT_UNRESOLVED,
           REQUEST_ERROR)

STRATA = ("BODY_AVAILABLE", "BODY_REFUSED",
          "BODY_TRANSPORT_UNRESOLVED_OR_UNAVAILABLE")
PER_STRATUM = 2
REISSUE_DELAY_SECONDS = 8
POLITE = 1.0

PROTOCOL_STEPS = (
    ("P0", "SESSION_BOOTSTRAP", "GET", APP + "/mops/"),
    ("P1", "CONTEXT_LIST", "POST", API + "t05st01"),
    ("P2", "SIGNED_URL", "POST", API + "redirectToOld"),
    ("P3", "FETCH_AS_ISSUED", "GET", "<signed url as issued>"),
    ("P4", "FETCH_ON_APP_HOST", "GET", APP + LEGACY_DETAIL_PATH + "?parameters="),
    ("P5", "POST_ON_APP_HOST", "POST", APP + LEGACY_DETAIL_PATH),
    ("P6", "REISSUE_AND_REFETCH", "POST+GET", "<P2 then P3 after delay>"),
)
FORBIDDEN_TRANSPORT_SOURCES = ("third_party_mirror", "cached_copy", "tej",
                               "search_engine_cache", "archival_service")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path, raw: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_response(raw: bytes | None, err: str | None) -> tuple[str, str]:
    """F7. A refusal must be something the source actually said."""
    if raw is None:
        return TRANSPORT_UNRESOLVED, "no response obtained: %s" % err
    text = V14._plain(raw.decode("utf-8", "replace"))
    if not text.strip():
        return TRANSPORT_UNRESOLVED, "empty body (%d bytes)" % len(raw)
    if V14.is_rate_limited(text):
        return REQUEST_ERROR, "official throttle page"
    if any(m in text for m in V14.REFUSAL_MARKERS):
        return OFFICIAL_SOURCE_REFUSED, text[:160]
    if "傳入參數異常" in text or "參數錯誤" in text:
        return REQUEST_ERROR, text[:160]
    if V14.DOCUMENT_TEMPLATE_MARKER in text:
        return BODY_AVAILABLE, text[:160]
    return TRANSPORT_UNRESOLVED, "no template marker, no refusal: " + text[:140]


class Flow:
    """One official MOPS session. Nothing enters it from outside the flow."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.log = []

    def cookie_context(self):
        return [{"name": c.name, "domain": c.domain,
                 "value_sha256": _sha(c.value.encode())} for c in self.jar]

    def _do(self, step, method, url, data=None, headers=None, timeout=60):
        hdr = dict(BROWSER)
        hdr.update(headers or {})
        rec = {"step": step, "method": method, "url": url[:400],
               "issued_at": _now()}
        try:
            req = urllib.request.Request(url, data=data, headers=hdr,
                                         method=method)
            with self.opener.open(req, timeout=timeout) as r:
                raw = r.read()
                rec.update({"http_status": r.status, "bytes": len(raw),
                            "raw_sha256": _sha(raw)})
            self.log.append(rec)
            return raw, None
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:180])
            rec["error"] = err
            self.log.append(rec)
            return None, err

    def bootstrap(self):
        return self._do("P0", "GET", APP + "/mops/")

    def context_list(self, company_id, roc_year):
        payload = json.dumps({"companyId": company_id, "year": str(roc_year),
                              "month": "all", "firstDay": "",
                              "lastDay": ""}).encode()
        return self._do("P1", "POST", API + "t05st01", payload,
                        {"Content-Type": "application/json",
                         "Referer": APP + "/mops/"})

    def signed_url(self, params, step="P2"):
        payload = json.dumps({"apiName": "t05st01_detail",
                              "parameters": params}).encode()
        raw, err = self._do(step, "POST", API + "redirectToOld", payload,
                            {"Content-Type": "application/json",
                             "Referer": APP + "/mops/"})
        if raw is None:
            return None, raw, err
        try:
            js = json.loads(raw.decode("utf-8", "replace"))
            return (js.get("result") or {}).get("url"), raw, None
        except Exception as exc:                            # noqa: BLE001
            return None, raw, "unparseable redirect response: %s" % exc


def main() -> int:
    d61 = json.load(open(CENSUS_D61, encoding="utf-8"))
    v14 = json.load(open(SEALED_V14, encoding="utf-8"))

    # ---- F3 · strata and deterministic selection ---------------------------
    docs = {}
    for r in d61["results"]:
        for a in r["documents"]:
            docs[a["document_id"]] = dict(
                a, security_id=r["security_id"], event_id=r["event_id"])
    buckets = {s: [] for s in STRATA}
    for did, a in docs.items():
        state = a["acquisition_state"]
        if state == D61.BODY_RETRIEVED:
            buckets["BODY_AVAILABLE"].append(did)
        elif state == D61.BODY_WITHHELD_BY_SOURCE:
            buckets["BODY_REFUSED"].append(did)
        else:
            buckets["BODY_TRANSPORT_UNRESOLVED_OR_UNAVAILABLE"].append(did)
    selection, sel_detail = [], []
    for s in STRATA:
        ranked = sorted(buckets[s], key=lambda d: _sha(d.encode()))
        for did in ranked[:PER_STRATUM]:
            selection.append(did)
            sel_detail.append({"stratum": s, "document_id": did,
                               "identity_sha256": _sha(did.encode()),
                               "previous_body_status": docs[did][
                                   "acquisition_state"],
                               "security_id": docs[did]["security_id"],
                               "publication_date": docs[did][
                                   "publication_date"],
                               "subject": docs[did]["subject"]})

    protocol = {
        "record": "B0_8_D6_2_TRANSPORT_PROTOCOL",
        "frozen_before_any_request": True,
        "purpose": ("can an authoritative MOPS announcement body already known "
                    "to exist be acquired through a deterministic official "
                    "transport path"),
        "steps": [{"id": i, "name": n, "method": m, "target": t}
                  for i, n, m, t in PROTOCOL_STEPS],
        "state_permitted": ["official MOPS cookies", "official session",
                            "referer", "redirect state", "official signed URL",
                            "immediately preceding official request context"],
        "state_forbidden": list(FORBIDDEN_TRANSPORT_SOURCES),
        "stop_rule": "first step returning an actual announcement body",
        "reissue_delay_seconds": REISSUE_DELAY_SECONDS,
        "signed_url_treated_as_ephemeral": True,
        "classification": {
            BODY_AVAILABLE: "template marker present, no refusal, no throttle",
            OFFICIAL_SOURCE_REFUSED: "the source returned a refusal",
            TRANSPORT_UNRESOLVED: "no official response, or an empty body",
            REQUEST_ERROR: "the source answered about the request: throttle or "
                           "parameter rejection",
        },
        "http_200_with_refusal_or_throttle_is_not_body_available": True,
        "socket_failure_is_not_official_refusal": True,
        "strata_populations": {s: len(buckets[s]) for s in STRATA},
        "per_stratum": PER_STRATUM,
        "short_stratum_rule": "use all available, never top up from another",
        "selection_rule": "sha256(canonical_document_id) ascending",
        "selection_blind_to": ["security holdings", "B0 blocker status", "8913",
                               "3299", "transaction consideration",
                               "apparent reconstructibility", "performance"],
        "selected": sel_detail,
        "d6_1_preserved": {
            "census_sha256": d61["census_sha256"],
            "router_sha256": d61["router_sha256"],
            "counts": d61["counts"],
            "none_decomposition": d61["none_decomposition"],
        },
        "not_authorized": ["dual extraction", "holder-term materialization",
                           "RECONSTRUCTIBLE classification", "CA rebuild",
                           "state rebuild", "replay", "NAV", "performance",
                           "gates", "bulk retry of all 781 documents"],
    }
    protocol["protocol_sha256"] = canonical_sha256(
        {k: v for k, v in protocol.items() if k != "selected"})
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(protocol, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("protocol frozen :", protocol["protocol_sha256"], flush=True)
    print("strata          :", protocol["strata_populations"], flush=True)
    for s in sel_detail:
        print("  %-42s %s %s" % (s["document_id"], s["stratum"],
                                 s["identity_sha256"][:12]), flush=True)

    # marketKind comes from the official v2 rows already preserved at D6.1.
    market_kind = {}
    for fn in sorted(os.listdir(V2RAW)) if os.path.isdir(V2RAW) else []:
        if not fn.endswith(".json") or fn.startswith("detail_probe"):
            continue
        try:
            js = json.loads(open(os.path.join(V2RAW, fn), "rb").read()
                            .decode("utf-8", "replace"))
        except Exception:                                   # noqa: BLE001
            continue
        for row in ((js.get("result") or {}).get("data") or []):
            try:
                co, _a, roc_d, tm, _s, params = row[:6]
            except ValueError:
                continue
            p = params.get("parameters", {})
            when = V14.roc_to_date(roc_d)
            did = D61.document_id(
                co, "%04d%02d%02d" % (when.year, when.month, when.day),
                tm.replace(":", ""), str(p.get("serialNumber", "")))
            market_kind[did] = p.get("marketKind") or "pub"

    # ---- execute the frozen ladder -----------------------------------------
    results = []
    for sel in sel_detail:
        did = sel["document_id"]
        co, dt, tm, sq = did.split(":")[1:]
        params = {"serialNumber": sq,
                  "enterDate": "%d%s%s" % (int(dt[:4]) - 1911, dt[4:6], dt[6:]),
                  "marketKind": market_kind.get(did, "pub"),
                  "companyId": co}
        flow = Flow()
        rec = {**sel, "detail_parameters": params, "transport_attempted": True,
               "attempts": [], "signed_urls": []}
        flow.bootstrap()
        time.sleep(POLITE)
        flow.context_list(co, int(dt[:4]) - 1911)
        time.sleep(POLITE)

        final_state, final_evidence, final_hash, body_path = None, None, None, None
        url, redirect_raw, err = flow.signed_url(params)
        if redirect_raw is not None:
            p = os.path.join(RAW, did.replace(":", "_") + ".P2_redirect.json")
            _write(p, redirect_raw)
            rec["signed_urls"].append({
                "step": "P2", "issued_at": _now(), "url": url,
                "redirect_raw_sha256": _sha(redirect_raw),
                "preserved_at": os.path.relpath(p, REPO)})
        blob = url.split("parameters=")[1] if url and "parameters=" in url else None

        ladder = []
        if url:
            ladder.append(("P3", "GET", url, None))
        if blob:
            ladder.append(("P4", "GET",
                           APP + LEGACY_DETAIL_PATH + "?parameters=" + blob,
                           None))
            ladder.append(("P5", "POST", APP + LEGACY_DETAIL_PATH,
                           ("parameters=" + blob).encode()))
        for step, method, u, data in ladder:
            hdr = ({"Content-Type": "application/x-www-form-urlencoded"}
                   if data else {})
            raw, e = flow._do(step, method, u, data, hdr)
            state, evidence = classify_response(raw, e)
            entry = {"step": step, "method": method, "url": u[:200],
                     "state": state, "evidence": evidence,
                     "response_sha256": _sha(raw) if raw is not None else None,
                     "bytes": len(raw) if raw is not None else None}
            rec["attempts"].append(entry)
            if raw is not None:
                pth = os.path.join(RAW, "%s.%s.html"
                                   % (did.replace(":", "_"), step))
                _write(pth, raw)
                entry["preserved_at"] = os.path.relpath(pth, REPO)
            final_state, final_evidence = state, entry["response_sha256"]
            final_hash = entry["response_sha256"]
            body_path = entry.get("preserved_at")
            if state == BODY_AVAILABLE:
                break
            time.sleep(POLITE)

        if final_state != BODY_AVAILABLE:
            time.sleep(REISSUE_DELAY_SECONDS)
            url2, rr2, _e2 = flow.signed_url(params, step="P6")
            if rr2 is not None:
                p = os.path.join(RAW, did.replace(":", "_")
                                 + ".P6_redirect.json")
                _write(p, rr2)
                rec["signed_urls"].append({
                    "step": "P6", "issued_at": _now(), "url": url2,
                    "redirect_raw_sha256": _sha(rr2),
                    "preserved_at": os.path.relpath(p, REPO),
                    "url_identical_to_P2": url2 == url})
            if url2:
                raw, e = flow._do("P6", "GET", url2)
                state, evidence = classify_response(raw, e)
                entry = {"step": "P6", "method": "GET", "url": url2[:200],
                         "state": state, "evidence": evidence,
                         "response_sha256": (_sha(raw) if raw is not None
                                             else None),
                         "bytes": len(raw) if raw is not None else None}
                if raw is not None:
                    pth = os.path.join(RAW, "%s.P6.html"
                                       % did.replace(":", "_"))
                    _write(pth, raw)
                    entry["preserved_at"] = os.path.relpath(pth, REPO)
                rec["attempts"].append(entry)
                final_state, final_hash = state, entry["response_sha256"]
                body_path = entry.get("preserved_at")

        rec.update({"resulting_body_status": final_state,
                    "resulting_response_sha256": final_hash,
                    "resulting_body_preserved_at": body_path,
                    "session_context": flow.cookie_context(),
                    "flow_log": flow.log})
        results.append(rec)
        print("  %s  %-24s -> %s" % (did, sel["previous_body_status"],
                                     final_state), flush=True)

    # ---- F6 controls / F10 verdict -----------------------------------------
    by_prev = {}
    for r in results:
        by_prev.setdefault(r["previous_body_status"], Counter())[
            r["resulting_body_status"]] += 1
    prev_avail = [r for r in results
                  if r["previous_body_status"] == D61.BODY_RETRIEVED]
    prev_ref = [r for r in results
                if r["previous_body_status"] == D61.BODY_WITHHELD_BY_SOURCE]
    preserves = all(r["resulting_body_status"] == BODY_AVAILABLE
                    for r in prev_avail) if prev_avail else None
    gained = [r for r in prev_ref
              if r["resulting_body_status"] == BODY_AVAILABLE]
    refused = [r for r in prev_ref
               if r["resulting_body_status"] == OFFICIAL_SOURCE_REFUSED]
    unresolved = [r for r in results
                  if r["resulting_body_status"] == TRANSPORT_UNRESOLVED]

    if prev_ref and len(gained) == len(prev_ref) and preserves:
        verdict = "FEASIBLE"
    elif gained:
        verdict = "PARTIALLY_FEASIBLE"
    elif len(unresolved) >= max(1, len(results) // 2):
        verdict = "TRANSPORT_UNRESOLVED"
    elif refused:
        verdict = "NOT_FEASIBLE"
    else:
        verdict = "TRANSPORT_UNRESOLVED"

    out = {
        "record": "B0_8_D6_2_AUTHORITATIVE_BODY_TRANSPORT_FEASIBILITY",
        "b0_8_state": "WIP, UNSEALED",
        "protocol_sha256": protocol["protocol_sha256"],
        "protocol_path": os.path.relpath(FREEZE, REPO),
        "d6_1_preserved_unchanged": protocol["d6_1_preserved"],
        "strata_populations": protocol["strata_populations"],
        "sample_size": len(results),
        "sample_size_intended": PER_STRATUM * len(STRATA),
        "sample_shortfall_reason": (
            "BODY_TRANSPORT_UNRESOLVED_OR_UNAVAILABLE is empty: "
            "TRANSPORT_UNRESOLVED is a property of route R4, not of any "
            "document in the register. F3 forbids topping up from another "
            "stratum."),
        "OFFICIAL_BODY_TRANSPORT": verdict,
        "controls": {
            "route_preserves_known_good_content": preserves,
            "previously_available_tested": len(prev_avail),
            "previously_refused_tested": len(prev_ref),
            "previously_unresolved_tested": 0,
            "bodies_newly_obtained": len(gained),
            "explicit_official_refusals": len(refused),
            "transport_failures": len(unresolved),
            "outcome_by_previous_status": {k: dict(v)
                                           for k, v in by_prev.items()},
        },
        "results": results,
        "semantic_expansion_performed": False,
        "event_classifications_changed": False,
        "dual_extraction_performed": False,
        "holder_terms_materialized": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_computed": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "bulk_retry_performed": False,
    }
    out["record_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nOFFICIAL_BODY_TRANSPORT :", verdict)
    print("controls                :", json.dumps(out["controls"],
                                                  ensure_ascii=False))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
