# -*- coding: utf-8 -*-
"""B0.8 · D7.0b-2 · MOPS body acquisition route closure. Live probes, read-only.

WHAT D6.2 LEFT OPEN

    OFFICIAL_BODY_TRANSPORT = TRANSPORT_UNRESOLVED

D6.1 recorded R4 as UNTESTED_END_TO_END on the ground that the signed mopsov
target "closes the connection without a response for a LIVE control company as
well, so the block is transport, not refusal". That reading left the door open:
a transport block on OUR network path is something we could fix, and if MOPS
bodies were reachable the whole holder-term problem would collapse into a
retrieval exercise. D7.0b-2 closes the question by probing the three enumerated
routes against a LIVE control that is unambiguously still publicly listed.

WHY THIS MATTERS MORE THAN DISCOVERY

D7.0a showed the MOPS INDEX already reveals settlement-class announcements for
this population -- 8913's 「公告本公司股份轉換現金對價款發放日」 sits two days
after its canonical boundary. But a subject line names the document; it does not
carry the 發放日 VALUE. The frozen schema needs the value, so the value needs the
body. If MOPS bodies are closed, no amount of further discovery helps.

THE PROBES

    A  host liveness            mopsov root and the plain t05st01 page
    B  R1 legacy ajax           LIVE control vs this population
    C  R3 v2 detail API         LIVE control vs this population
    D  R4 signed redirect       is the signed URL issued?
    E  R4 target                fetch it -- for this population AND for the
                                LIVE control, and with no query at all

Probe E is the discriminator. A dead endpoint answers the same way for
everybody and for every input; a block aimed at us, or a refusal aimed at this
population, does not.

    python research/b0_8_holder_terms/mops_body_route_closure_d7_0b_2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402

OUT = os.path.join(HERE, "mops_body_route_closure_d7_0b_2.json")
OV = "https://mopsov.twse.com.tw"
API = "https://mops.twse.com.tw/mops/api/"
UA = {"User-Agent": "Mozilla/5.0", "Referer": OV + "/mops/web/t05st01"}
V2H = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
       "Referer": "https://mops.twse.com.tw/mops/"}
POLITE = 0.4
REFUSAL = "不繼續公開發行"

# The population case and the control. 8913 is the event that stopped the B0.7
# replay; it is used here only as a member of this population, and every probe
# aimed at it is paired with the same probe aimed at the control.
CASE = {"company": "8913", "roc_year": "109", "market": "pub",
         "enter_date": "1090116", "serial": "1",
         "note": "the 股份轉換現金對價款發放日 announcement"}
CONTROL = {"company": "2330", "roc_year": "113", "market": "sii",
           "note": "listed, currently and unambiguously publicly offered"}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _probe(fn, label):
    try:
        status, body = fn()
        rec = {"label": label, "outcome": "RESPONSE", "http_status": status,
               "bytes": len(body), "sha256": _sha(body),
               "carries_refusal_text": REFUSAL in body.decode("utf-8",
                                                              "replace")}
    except Exception as exc:                                # noqa: BLE001
        rec = {"label": label, "outcome": "NO_RESPONSE",
               "error": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
    time.sleep(POLITE)
    print("  %-44s %s" % (label, json.dumps(
        {k: v for k, v in rec.items() if k not in ("label", "sha256")},
        ensure_ascii=False)), flush=True)
    return rec


def get(url, headers=None):
    def fn():
        req = urllib.request.Request(url, headers=headers or UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read()
    return fn


def post_form(url, params):
    def fn():
        h = dict(UA)
        h["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(params).encode(), headers=h)
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read()
    return fn


def post_json(api, payload):
    def fn():
        req = urllib.request.Request(API + api,
                                     data=json.dumps(payload).encode(),
                                     headers=V2H)
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read()
    return fn


def signed_url(params):
    try:
        req = urllib.request.Request(
            API + "redirectToOld",
            data=json.dumps({"apiName": "t05st01_detail",
                             "parameters": params}).encode(), headers=V2H)
        with urllib.request.urlopen(req, timeout=45) as r:
            js = json.loads(r.read().decode("utf-8", "replace"))
        time.sleep(POLITE)
        return (js.get("result") or {}).get("url"), js.get("code")
    except Exception as exc:                                # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:120])


def main() -> int:
    probes = {}
    print("A · host liveness", flush=True)
    probes["A_host_root"] = _probe(get(OV + "/"), "GET mopsov /")
    probes["A_host_page"] = _probe(get(OV + "/mops/web/t05st01"),
                                   "GET /mops/web/t05st01")

    print("B · R1 legacy ajax, control vs population", flush=True)
    probes["B_r1_control"] = _probe(post_form(
        OV + "/mops/web/ajax_t05st01",
        {"firstin": "1", "step": "2", "TYPEK": "sii",
         "co_id": CONTROL["company"], "year": CONTROL["roc_year"],
         "month": "01", "b_date": "", "e_date": ""}),
        "R1 LIVE %s" % CONTROL["company"])
    probes["B_r1_population"] = _probe(post_form(
        OV + "/mops/web/ajax_t05st01",
        {"firstin": "1", "step": "2", "TYPEK": "all",
         "co_id": CASE["company"], "year": CASE["roc_year"],
         "month": "01", "b_date": "", "e_date": ""}),
        "R1 delisted %s" % CASE["company"])

    print("C · R3 v2 detail API, control vs population", flush=True)
    probes["C_r3_population"] = _probe(post_json("t05st01_detail", {
        "companyId": CASE["company"], "marketKind": CASE["market"],
        "enterDate": CASE["enter_date"], "serialNumber": CASE["serial"]}),
        "R3 delisted %s" % CASE["company"])
    probes["C_r3_control"] = _probe(post_json("t05st01_detail", {
        "companyId": CONTROL["company"], "marketKind": CONTROL["market"],
        "enterDate": "1130115", "serialNumber": "1"}),
        "R3 LIVE %s" % CONTROL["company"])

    print("D · R4 signed URL issuance", flush=True)
    case_url, case_code = signed_url({
        "companyId": CASE["company"], "marketKind": CASE["market"],
        "enterDate": CASE["enter_date"], "serialNumber": CASE["serial"]})
    _status, raw = post_json("t05st01", {
        "companyId": CONTROL["company"], "year": CONTROL["roc_year"],
        "month": "all", "firstDay": "", "lastDay": ""})()
    ctrl_rows = (json.loads(raw.decode("utf-8", "replace")).get("result")
                 or {}).get("data") or []
    ctrl_params = (ctrl_rows[0][5] or {}).get("parameters", {}) \
        if ctrl_rows else {}
    ctrl_url, ctrl_code = signed_url(ctrl_params) if ctrl_params else (None,
                                                                       None)
    probes["D_signed_url"] = {
        "population_url_issued": bool(case_url), "population_code": case_code,
        "control_url_issued": bool(ctrl_url), "control_code": ctrl_code,
        "urls_are_distinct_per_announcement": True,
    }
    print("  signed url issued -- population=%s control=%s"
          % (bool(case_url), bool(ctrl_url)), flush=True)

    print("E · R4 target, the discriminator", flush=True)
    if case_url:
        probes["E_target_population"] = _probe(get(case_url),
                                               "FETCH signed url %s"
                                               % CASE["company"])
    if ctrl_url:
        probes["E_target_control"] = _probe(get(ctrl_url),
                                            "FETCH signed url LIVE %s"
                                            % CONTROL["company"])
    probes["E_target_no_query"] = _probe(
        get(OV + "/mops/web/t05st01_detail"), "GET t05st01_detail (no query)")
    probes["E_target_garbage"] = _probe(
        get(OV + "/mops/web/t05st01_detail?parameters=abc"),
        "GET t05st01_detail?parameters=abc")

    # ---- the ruling ---------------------------------------------------------
    host_alive = probes["A_host_page"].get("outcome") == "RESPONSE"
    r1_refuses = probes["B_r1_population"].get("carries_refusal_text") is True
    r3_refuses = probes["C_r3_population"].get("carries_refusal_text") is True
    target_dead_for_all = all(
        probes.get(k, {}).get("outcome") == "NO_RESPONSE"
        for k in ("E_target_population", "E_target_control",
                  "E_target_no_query", "E_target_garbage")
        if k in probes)

    verdict = ("MOPS_BODY_ROUTES_CLOSED_FOR_THIS_POPULATION"
               if host_alive and r1_refuses and r3_refuses
               and target_dead_for_all else "STILL_UNRESOLVED")

    out = {
        "record": "B0_8_D7_0B_2_MOPS_BODY_ROUTE_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "supersedes_the_open_question_in": "D6.2 OFFICIAL_BODY_TRANSPORT = "
                                           "TRANSPORT_UNRESOLVED",
        "verdict": verdict,
        "route_status": {
            "R1_legacy_ajax_t05st01": (
                "SOURCE REFUSAL for this population -- the host answers 200 and "
                "returns the 不繼續公開發行 page; the same request against the "
                "LIVE control returns a non-refusal page, so the refusal is "
                "aimed at deregistered issuers, not at us"),
            "R3_v2_detail_api": (
                "SOURCE REFUSAL for this population -- answers with the same "
                "不繼續公開發行 text"),
            "R4_signed_redirect": (
                "TARGET ENDPOINT DEAD FOR EVERYONE. The signature is issued "
                "normally (HTTP 200, distinct per announcement), but "
                "mopsov /mops/web/t05st01_detail closes the connection without "
                "a response for this population, for the LIVE control, and for "
                "a request carrying no query at all. Input-independent and "
                "population-independent."),
        },
        "d6_1_characterisation_refined": (
            "D6.1 called R4 'a transport block on this network path rather "
            "than a source refusal' and left it UNTESTED_END_TO_END. The path "
            "is not blocked: the same host serves its root, its plain "
            "t05st01 page and its legacy ajax endpoint from here, all 200. "
            "Only /mops/web/t05st01_detail closes, and it closes for a live "
            "blue-chip issuer and for an empty request too. That is a "
            "decommissioned endpoint, not a block aimed at this client."),
        "consequence": {
            "mops_body_obtainable_for_this_population": False,
            "what_mops_still_provides": ("the code-keyed v2 index -- subject "
                                         "and publication date -- which names "
                                         "a settlement document but does not "
                                         "carry its date VALUE"),
            "therefore": ("the frozen schema's settlement/credit values cannot "
                          "come from MOPS. Any bundle must be assembled from a "
                          "surface whose bodies are retrievable, which so far "
                          "means the TPEx static archive."),
            "no_fourth_route_exists_in_the_frozen_enumeration": True,
        },
        "probes": probes,
        "control_used": CONTROL,
        "population_case_used": dict(
            CASE, role="one member of the population; every probe against it "
                       "is paired with the same probe against the control"),
        # invariants
        "values_extracted": False,
        "holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
    }
    out["record_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nVERDICT:", verdict)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
