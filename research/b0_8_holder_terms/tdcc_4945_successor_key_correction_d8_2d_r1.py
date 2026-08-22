# -*- coding: utf-8 -*-
"""B0.8 · D8.2D-R1 · SUCCESSOR-SECURITY QUERY-KEY CORRECTION.

D8.2D queried TDCC with the disappearing security's own code (4945), which
this instrument never trades or settles under post-conversion -- delivery of
successor shares posts under the SUCCESSOR's code (2436, 偉詮電子, per
D7.2b's frozen routing). This stage:

  1. verifies that mapping against the frozen discovery record,
  2. reinspects the OD-1-7 snapshot D8.2D already saved (no redownload)
     filtered on 2436,
  3. runs exactly one corrected PORTAL-QRYPS query (stockNo=2436), reusing
     D8.2D's fetch/evidence machinery,
  4. keeps D8.2D's own record file untouched -- this is a superseding
     correction, not an edit.

    python research/b0_8_holder_terms/tdcc_4945_successor_key_correction_d8_2d_r1.py
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402

D72B = os.path.join(HERE, "domestic_security_routing_d7_2b.json")
D82D = os.path.join(HERE, "tdcc_4945_single_event_test_d8_2d.json")
OD_CACHE = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d8_2d_tdcc_raw",
                        "OD-1-7_d8_2d.csv")
RAW_DIR = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d8_2d_r1_tdcc_raw")
OUT = os.path.join(HERE, "tdcc_4945_successor_key_correction_d8_2d_r1.json")

DISAPPEARING_SID = "4945"
SUCCESSOR_SID = "2436"
QRYPS_URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryPS"
UA = {"User-Agent": "Mozilla/5.0"}

CREDIT_STRICT = re.compile(
    r"帳簿劃撥|劃撥交付|劃撥配發|配發交付|交付新股|新股交付|發放新股|"
    r"新股發放|換發股份[^。]{0,4}?交付|股份交付")
# reason codes that DO NOT by themselves establish a merger/share-conversion
# holder credit -- they are shared/compound codes covering other actions too
AMBIGUOUS_REASON_CODES = ("減資", "認股", "配股", "上市", "上櫃")
MERGER_SPECIFIC_MARKERS = ("合併", "股份轉換", "概括承受")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fetch(url, data=None, headers=None, timeout=60):
    """Same curl-based fetch as D8.2D (full TLS verification, OS trust
    store; used because this interpreter's OpenSSL rejects tdcc.com.tw's
    chain on a strict SKI check that openssl s_client/curl both accept)."""
    h = dict(UA)
    h.update(headers or {})
    ts = now_iso()
    cmd = ["curl", "-sS", "-D", "-", "-o", "-", "--max-time", str(timeout)]
    for k, v in h.items():
        cmd += ["-H", "%s: %s" % (k, v)]
    if data is not None:
        cmd += ["--data-raw", data.decode("utf-8") if isinstance(data, bytes) else data]
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    except Exception as exc:                                  # noqa: BLE001
        return {"timestamp": ts, "status": None, "headers": {}, "body": b"",
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:200]),
                "tls_verification": "curl default (full verification, no -k)"}
    if proc.returncode != 0:
        return {"timestamp": ts, "status": None, "headers": {}, "body": b"",
                "error": "curl exit %d: %s" %
                (proc.returncode, proc.stderr.decode("utf-8", "replace")[:200]),
                "tls_verification": "curl default (full verification, no -k)"}
    raw = proc.stdout
    parts = raw.split(b"\r\n\r\n")
    header_blocks, body = parts[:-1], parts[-1]
    status, hdrs = None, {}
    for block in header_blocks:
        lines = block.decode("latin-1", "replace").split("\r\n")
        if lines and lines[0].startswith("HTTP/"):
            try:
                status = int(lines[0].split()[1])
            except Exception:                                 # noqa: BLE001
                pass
            hdrs = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    hdrs[k.strip()] = v.strip()
    return {"timestamp": ts, "status": status, "headers": hdrs, "body": body,
            "error": None, "tls_verification": "curl default (full verification, no -k)"}


def save_raw(name, body):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, name)
    with open(path, "wb") as fh:
        fh.write(body)
    return path


def main() -> int:
    d72b = json.load(open(D72B, encoding="utf-8"))
    d82d = json.load(open(D82D, encoding="utf-8"))

    # ---- 1. verify the query key -----------------------------------------
    rec = next((r for r in d72b["per_event"] if r["security_id"] == DISAPPEARING_SID), None)
    mapping = {
        "disappearing_security_id": DISAPPEARING_SID,
        "successor_security_id": rec["successor_security_id"] if rec else None,
        "stock_consideration_issuer": rec["successor_legal_entity"] if rec else None,
        "source": "domestic_security_routing_d7_2b.json (frozen D7.2b routing)",
        "successor_security_status": rec["successor_security_status"] if rec else None,
        "transaction_leg": rec["transaction_leg"] if rec else None,
    }
    mapping_confirmed = (rec is not None and rec["successor_security_id"] == SUCCESSOR_SID
                         and rec["successor_security_status"] == "DOMESTIC_SECURITY_ID_ESTABLISHED")
    if not mapping_confirmed:
        out = {"record": "B0_8_D8_2D_R1_SUCCESSOR_QUERY_KEY_CORRECTION",
              "STOPPED": True, "reason": "authoritative mapping unresolved or differs",
              "mapping": mapping}
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("MAPPING NOT CONFIRMED -- STOPPING. See", OUT)
        return 1
    print("mapping confirmed:", DISAPPEARING_SID, "->", SUCCESSOR_SID)

    # ---- 2. reinspect the cached OD-1-7 snapshot (no redownload) --------
    csv_text = open(OD_CACHE, encoding="utf-8-sig").read()
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    header = [c.strip() for c in lines[0].split(",")]
    matching_rows = []
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.split(",")]
        if cells and cells[0] == SUCCESSOR_SID:
            row = dict(zip(header, cells))
            reason = row.get("交付原因", "")
            merger_specific = any(m in reason for m in MERGER_SPECIFIC_MARKERS)
            ambiguous = any(a in reason for a in AMBIGUOUS_REASON_CODES)
            row["_linkage_assessment"] = {
                "reason_code": reason,
                "contains_merger_specific_marker": merger_specific,
                "contains_ambiguous_shared_code": ambiguous,
                "security_code_alone_sufficient": False,
                "same_transaction_established": merger_specific and not ambiguous,
            }
            matching_rows.append(row)

    od_route_result = (
        "SOURCE_SCHEMA_DOES_NOT_ENCODE_THIS_SEMANTIC" if not matching_rows else
        "VALID_SUCCESSOR_CREDIT_DATE_PRESENT" if any(
            r["_linkage_assessment"]["same_transaction_established"] for r in matching_rows) else
        "SUCCESSOR_RECORD_PRESENT_TRANSACTION_LINKAGE_NOT_ESTABLISHED"
    )
    # OD-1-7 has no per-security zero-record state distinct from "not in the
    # snapshot" -- absence from the cached rows is QUERY_SUCCEEDED_NO_
    # SUCCESSOR_SECURITY_RECORD, not a schema statement
    if not matching_rows:
        od_route_result = "QUERY_SUCCEEDED_NO_SUCCESSOR_SECURITY_RECORD"

    # ---- 3. corrected PORTAL-QRYPS query (1 token GET + 1 POST) -----------
    requests_log = []
    r_form = fetch(QRYPS_URL)
    path_form = save_raw("PORTAL-QRYPS_form_d8_2d_r1.html", r_form["body"]) \
        if r_form["body"] else None
    requests_log.append({
        "route": "PORTAL-QRYPS (form GET, token refresh)",
        "official_endpoint": QRYPS_URL,
        "retrieval_timestamp": r_form["timestamp"],
        "http_status": r_form["status"],
        "tls_verification": r_form["tls_verification"],
        "response_content_sha256": hashlib.sha256(r_form["body"]).hexdigest()
            if r_form["body"] else None,
        "raw_response_path": os.path.relpath(path_form, REPO) if path_form else None,
        "error": r_form["error"],
    })
    token_m = re.search(r'name="SYNCHRONIZER_TOKEN"[^>]*value="([^"]*)"',
                        r_form["body"].decode("utf-8", "replace")) if r_form["body"] else None
    uri_m = re.search(r'name="SYNCHRONIZER_URI"[^>]*value="([^"]*)"',
                      r_form["body"].decode("utf-8", "replace")) if r_form["body"] else None

    qryps_result = "ROUTE_ERROR_OR_ACCESS_LIMITATION"
    same_txn_established_qryps = False
    if token_m:
        time.sleep(1.0)
        body = urllib.parse.urlencode({
            "SYNCHRONIZER_TOKEN": token_m.group(1),
            "SYNCHRONIZER_URI": uri_m.group(1) if uri_m else "/portal/zh/smWeb/qryPS",
            "method": "submit", "sqlMethod": "StockNo",
            "stockNo": SUCCESSOR_SID, "stockName": "", "stockDate": ""}).encode()
        r_post = fetch(QRYPS_URL, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded", "Referer": QRYPS_URL})
        path_post = save_raw("PORTAL-QRYPS_result_2436_d8_2d_r1.html", r_post["body"]) \
            if r_post["body"] else None
        html = r_post["body"].decode("utf-8", "replace") if r_post["body"] else ""
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        has_sid = SUCCESSOR_SID in text
        has_no_data = "查無此資料" in text or "查無資料" in text
        credit_hits = [{"label": m.group(0),
                       "window": text[max(0, m.start()-60):m.end()+80]}
                      for m in CREDIT_STRICT.finditer(text)]
        # locate the row(s) actually keyed to 2436 in the rendered result
        # (distinct from static nav-menu occurrences of 帳簿劃撥)
        row_matches = re.findall(r"2436[^0-9]{0,80}?(20\d{6})[^0-9]{0,40}?(減資[^ ]{0,10}|"
                                 r"股份轉換[^ ]{0,10}|合併[^ ]{0,10}|[^\s]{0,10})", text)
        merger_marker_near_row = any(
            any(mk in rm[1] for mk in MERGER_SPECIFIC_MARKERS) for rm in row_matches)

        requests_log.append({
            "route": "PORTAL-QRYPS (StockNo=2436 POST)",
            "official_endpoint": QRYPS_URL,
            "retrieval_timestamp": r_post["timestamp"],
            "query_parameters": {"sqlMethod": "StockNo", "stockNo": SUCCESSOR_SID},
            "http_status": r_post["status"],
            "tls_verification": r_post["tls_verification"],
            "response_content_sha256": hashlib.sha256(r_post["body"]).hexdigest()
                if r_post["body"] else None,
            "raw_response_path": os.path.relpath(path_post, REPO) if path_post else None,
            "schema_field_names_returned": ["證券代號", "證券名稱", "交付日期", "交付原因"]
                if has_sid else [],
            "event_linkage_evidence": {
                "successor_security_id_present_in_response": has_sid,
                "no_data_marker_present": has_no_data,
                "row_matches_near_2436": row_matches,
                "merger_specific_marker_near_row": merger_marker_near_row,
                "credit_semantics_hits_site_wide": len(credit_hits),
            },
            "error": r_post["error"],
        })
        if r_post["error"] or r_post["status"] is None or r_post["status"] >= 400:
            qryps_result = "ROUTE_ERROR_OR_ACCESS_LIMITATION"
        elif has_no_data or not has_sid:
            qryps_result = "QUERY_SUCCEEDED_NO_SUCCESSOR_SECURITY_RECORD"
        elif merger_marker_near_row:
            qryps_result = "VALID_SUCCESSOR_CREDIT_DATE_PRESENT"
            same_txn_established_qryps = True
        else:
            qryps_result = "SUCCESSOR_RECORD_PRESENT_TRANSACTION_LINKAGE_NOT_ESTABLISHED"
    else:
        requests_log.append({
            "route": "PORTAL-QRYPS (StockNo=2436 POST)", "result_status": "NOT_ATTEMPTED_NO_TOKEN",
            "error": "no SYNCHRONIZER_TOKEN found on form page",
        })

    per_route_result = {"OD-1-7 (cached, reinspected)": od_route_result,
                        "PORTAL-QRYPS": qryps_result}
    valid_positive = "VALID_SUCCESSOR_CREDIT_DATE_PRESENT" in per_route_result.values()

    old_key_interpretation = {
        "4945_old_security_query": "NON_DIAGNOSTIC_FOR_SUCCESSOR_CREDIT_DATE",
        "reason": "delivery of successor shares posts under the SUCCESSOR's "
                  "own security code, not the disappearing security's code; "
                  "the D8.2D QUERY_SUCCEEDED_NO_EVENT_RECORD result under "
                  "4945 says nothing about whether a credit record exists -- "
                  "it was never the correct key",
        "d8_2d_result_not_reinterpreted_as_absence_evidence": True,
        "no_speculation_on_publication_timing": True,
    }

    out = {
        "record": "B0_8_D8_2D_R1_SUCCESSOR_QUERY_KEY_CORRECTION",
        "b0_8_state": "WIP, UNSEALED",
        "supersedes": "tdcc_4945_single_event_test_d8_2d.json (unmodified, "
                      "preserved as-is)",
        "inputs": {"d8_2d_closure_sha256": d82d.get("closure_sha256")},
        "mapping_verification": mapping,
        "mapping_confirmed": mapping_confirmed,
        "od_1_7_reinspection": {
            "source": "cached snapshot from D8.2D "
                      "(artifacts/b0_8_holder_terms/d8_2d_tdcc_raw/OD-1-7_d8_2d.csv), "
                      "no redownload",
            "filter_key": SUCCESSOR_SID,
            "matching_rows": matching_rows,
            "route_result": od_route_result,
        },
        "portal_qryps_correction": {
            "authorized_scope": "one POST using successor_security_id=2436, "
                                "plus one token/form GET (required -- D8.2D's "
                                "cached token was not reused/assumed valid)",
            "requests": requests_log,
            "route_result": qryps_result,
        },
        "per_route_result": per_route_result,
        "positive_semantics_required": ["successor security", "holder-inbound "
            "allotment/delivery", "explicit date", "same canonical 4945 "
            "transaction"],
        "excluded_as_substitutes": ["generic issuance", "employee allotment",
            "dividend", "capital increase", "listing date",
            "unrelated delivery record", "capital reduction share replacement"],
        "overall_result": ("VALID_SUCCESSOR_CREDIT_DATE_PRESENT" if valid_positive
                           else od_route_result if od_route_result == qryps_result
                           else "SUCCESSOR_RECORD_PRESENT_TRANSACTION_LINKAGE_NOT_ESTABLISHED"
                           if "SUCCESSOR_RECORD_PRESENT_TRANSACTION_LINKAGE_NOT_ESTABLISHED"
                           in per_route_result.values() else od_route_result),
        "old_key_interpretation_correction": old_key_interpretation,
        "TDCC_CURRENT_WINDOW": ("LIMITED_OR_CONDITIONAL_REPRESENTATION_ESTABLISHED"
                               if valid_positive else None),
        "od_redownloaded": False,
        "other_events_or_sources_queried": False,
        "bulk_acquisition": False,
        "d8_3_started": False,
        "canonical_schema_consumer_ledger_state_changed": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("OD-1-7 (cached) result:", od_route_result)
    print("matching rows for 2436:", matching_rows)
    print("PORTAL-QRYPS result:", qryps_result)
    print("overall:", out["overall_result"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
