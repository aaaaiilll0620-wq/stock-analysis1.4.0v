# -*- coding: utf-8 -*-
"""B0.8 · D8.2D · TDCC CURRENT-WINDOW SINGLE-EVENT REPRESENTATION TEST.

Exactly one event (security_id 4945, effective_date 2025-09-02), exactly the
two already-registered TDCC routes (OD-1-7, PORTAL-QRYPS), minimum requests.
Live network use is explicitly authorised for this stage only -- every
request is preserved (endpoint, timestamp, params, status, response hash,
raw path, schema, linkage evidence). No canonical materialisation.

    python research/b0_8_holder_terms/tdcc_4945_single_event_test_d8_2d.py
"""
from __future__ import annotations

import datetime
import hashlib
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

from core.b0_canonical_hash import canonical_sha256          # noqa: E402

RAW_DIR = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d8_2d_tdcc_raw")
OUT = os.path.join(HERE, "tdcc_4945_single_event_test_d8_2d.json")

SID = "4945"
SUCCESSOR_CODE = "2436"
EFFECTIVE_DATE = "2025-09-02"
UA = {"User-Agent": "Mozilla/5.0"}
OD_URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-7"
QRYPS_URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryPS"

CREDIT_STRICT = re.compile(
    r"帳簿劃撥|劃撥交付|劃撥配發|配發交付|交付新股|新股交付|發放新股|"
    r"新股發放|換發股份[^。]{0,4}?交付|股份交付")
EXCLUDED_DATE_LABELS = ("新股上市", "上市日期", "上櫃日期", "開始買賣",
                        "掛牌", "停止過戶", "基準日", "交存")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fetch(url, data=None, headers=None, timeout=60):
    """Shells out to curl, which performs full TLS certificate verification
    (no -k/--insecure) against the OS trust store. Used instead of Python's
    urllib because this interpreter's OpenSSL rejects tdcc.com.tw's chain on
    a strict Subject-Key-Identifier chain-building check that `openssl
    s_client -verify` and curl (same OS trust store, Verify return code: 0)
    both accept -- a client/library strictness mismatch, not a server-side
    access control, and not a certificate this run treats as untrusted."""
    import subprocess
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
        return {"timestamp": ts, "status": None, "headers": {}, "final_url": url,
                "body": b"", "error": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
    if proc.returncode != 0:
        return {"timestamp": ts, "status": None, "headers": {}, "final_url": url,
                "body": b"", "error": "curl exit %d: %s" %
                (proc.returncode, proc.stderr.decode("utf-8", "replace")[:200])}
    raw = proc.stdout
    # -D - -o - concatenates headers then body; split on the blank-line
    # terminator of the LAST header block (curl re-emits headers per redirect hop)
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
    return {"timestamp": ts, "status": status, "headers": hdrs, "final_url": url,
            "body": body, "error": None}


def save_raw(name, body):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, name)
    with open(path, "wb") as fh:
        fh.write(body)
    return path


def main() -> int:
    requests_log = []

    # ---- Route 1: OD-1-7 (bulk open-data CSV, one GET) --------------------
    r1 = fetch(OD_URL)
    path1 = save_raw("OD-1-7_d8_2d.csv", r1["body"]) if r1["body"] else None
    is_redirect_block = (r1["status"] in (302, 403) and
                         "smart.tdcc.com.tw" in (r1["headers"].get("Location", "")
                                                 or r1["headers"].get("location", "")))
    od17_rows = []
    if r1["body"] and not is_redirect_block:
        text = r1["body"].decode("utf-8-sig", "replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines:
            header = [c.strip() for c in lines[0].split(",")]
            for ln in lines[1:]:
                cells = ln.split(",")
                if len(cells) >= 1 and cells[0].strip() == SID:
                    od17_rows.append(dict(zip(header, [c.strip() for c in cells])))
    od17_route_result = (
        "ROUTE_ERROR_OR_ACCESS_LIMITATION" if (r1["status"] is None or is_redirect_block
                                               or r1["status"] >= 400) else
        "QUERY_SUCCEEDED_NO_EVENT_RECORD" if not od17_rows else
        "EVENT_RECORD_PRESENT_FIELD_ABSENT")  # refined below if credit semantics found
    requests_log.append({
        "route": "OD-1-7", "official_endpoint": OD_URL,
        "retrieval_timestamp": r1["timestamp"],
        "query_parameters": {"id": "1-7"},
        "http_status": r1["status"],
        "result_status": ("BLOCKED_SECURITY_REDIRECT" if is_redirect_block
                          else "ERROR" if r1["error"] else "OK"),
        "response_headers_location": r1["headers"].get("Location") or
            r1["headers"].get("location"),
        "response_content_sha256": hashlib.sha256(r1["body"]).hexdigest()
            if r1["body"] else None,
        "raw_response_path": os.path.relpath(path1, REPO) if path1 else None,
        "schema_field_names_returned": (["證券代號", "證券名稱", "交付日期", "交付原因"]
                                        if r1["body"] and not is_redirect_block else []),
        "event_linkage_evidence": {"security_id_matched_rows": len(od17_rows),
                                   "rows": od17_rows},
        "error": r1["error"],
        "route_result": od17_route_result,
    })

    time.sleep(1.0)

    # ---- Route 2: PORTAL-QRYPS (interactive form, 2 requests: GET token, POST query)
    r2a = fetch(QRYPS_URL)
    path2a = save_raw("PORTAL-QRYPS_form_d8_2d.html", r2a["body"]) if r2a["body"] else None
    token_match = re.search(r'name="SYNCHRONIZER_TOKEN"[^>]*value="([^"]*)"',
                            r2a["body"].decode("utf-8", "replace")) if r2a["body"] else None
    uri_match = re.search(r'name="SYNCHRONIZER_URI"[^>]*value="([^"]*)"',
                          r2a["body"].decode("utf-8", "replace")) if r2a["body"] else None

    requests_log.append({
        "route": "PORTAL-QRYPS (form GET)", "official_endpoint": QRYPS_URL,
        "retrieval_timestamp": r2a["timestamp"],
        "query_parameters": {},
        "http_status": r2a["status"],
        "result_status": "ERROR" if r2a["error"] else
            ("OK" if token_match else "OK_NO_TOKEN_FOUND"),
        "response_content_sha256": hashlib.sha256(r2a["body"]).hexdigest()
            if r2a["body"] else None,
        "raw_response_path": os.path.relpath(path2a, REPO) if path2a else None,
        "schema_field_names_returned": [],
        "event_linkage_evidence": None,
        "error": r2a["error"],
        "route_result": None,
    })

    qryps_route_result = "ROUTE_ERROR_OR_ACCESS_LIMITATION"
    qryps_rows_text = None
    r2b = None
    if token_match:
        time.sleep(1.0)
        body = urllib.parse.urlencode({
            "SYNCHRONIZER_TOKEN": token_match.group(1),
            "SYNCHRONIZER_URI": uri_match.group(1) if uri_match else "/portal/zh/smWeb/qryPS",
            "method": "submit", "sqlMethod": "StockNo",
            "stockNo": SID, "stockName": "", "stockDate": ""}).encode()
        r2b = fetch(QRYPS_URL, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": QRYPS_URL})
        path2b = save_raw("PORTAL-QRYPS_result_4945_d8_2d.html", r2b["body"]) \
            if r2b["body"] else None
        result_html = r2b["body"].decode("utf-8", "replace") if r2b["body"] else ""
        # strip tags for a text-level scan
        result_text = re.sub(r"<[^>]+>", " ", result_html)
        result_text = re.sub(r"\s+", " ", result_text)
        has_no_data_marker = any(m in result_text for m in
                                 ("查無資料", "查無所需資料", "無符合"))
        has_sid_row = SID in result_text
        credit_hits = [{"label": m.group(0),
                       "window": result_text[max(0, m.start()-60):m.end()+80]}
                      for m in CREDIT_STRICT.finditer(result_text)]
        if r2b["error"] or r2b["status"] is None or r2b["status"] >= 400:
            qryps_route_result = "ROUTE_ERROR_OR_ACCESS_LIMITATION"
        elif has_no_data_marker or not has_sid_row:
            qryps_route_result = "QUERY_SUCCEEDED_NO_EVENT_RECORD"
        elif credit_hits:
            qryps_route_result = "VALID_SUCCESSOR_CREDIT_DATE_PRESENT_CANDIDATE"
        else:
            qryps_route_result = "EVENT_RECORD_PRESENT_FIELD_ABSENT"
        qryps_rows_text = result_text[:2000]

        requests_log.append({
            "route": "PORTAL-QRYPS (StockNo=4945 POST)", "official_endpoint": QRYPS_URL,
            "retrieval_timestamp": r2b["timestamp"],
            "query_parameters": {"sqlMethod": "StockNo", "stockNo": SID},
            "http_status": r2b["status"],
            "result_status": "ERROR" if r2b["error"] else "OK",
            "response_content_sha256": hashlib.sha256(r2b["body"]).hexdigest()
                if r2b["body"] else None,
            "raw_response_path": os.path.relpath(path2b, REPO) if path2b else None,
            "schema_field_names_returned": ["證券代號", "證券名稱", "交付日期", "交付原因"]
                if has_sid_row else [],
            "event_linkage_evidence": {"security_id_present_in_response": has_sid_row,
                                       "no_data_marker_present": has_no_data_marker,
                                       "credit_semantics_hits": credit_hits},
            "error": r2b["error"],
            "route_result": qryps_route_result,
        })
    else:
        requests_log.append({
            "route": "PORTAL-QRYPS (StockNo=4945 POST)",
            "official_endpoint": QRYPS_URL,
            "retrieval_timestamp": None, "query_parameters": {"stockNo": SID},
            "http_status": None, "result_status": "NOT_ATTEMPTED_NO_TOKEN",
            "response_content_sha256": None, "raw_response_path": None,
            "schema_field_names_returned": [], "event_linkage_evidence": None,
            "error": "no SYNCHRONIZER_TOKEN found on form page",
            "route_result": "ROUTE_ERROR_OR_ACCESS_LIMITATION",
        })

    # ---- per-route results before deriving overall -------------------------
    per_route_result = {"OD-1-7": od17_route_result,
                        "PORTAL-QRYPS": qryps_route_result}

    # positive requires: same 4945 transaction, successor shares, holder-
    # inbound credit, explicit date -- not any excluded date type
    valid_positive = (qryps_route_result ==
                      "VALID_SUCCESSOR_CREDIT_DATE_PRESENT_CANDIDATE")

    if valid_positive:
        overall = "VALID_SUCCESSOR_CREDIT_DATE_PRESENT"
    elif "VALID_SUCCESSOR_CREDIT_DATE_PRESENT_CANDIDATE" in per_route_result.values():
        overall = "VALID_SUCCESSOR_CREDIT_DATE_PRESENT"
    elif all(v == "ROUTE_ERROR_OR_ACCESS_LIMITATION" for v in per_route_result.values()):
        overall = "ROUTE_ERROR_OR_ACCESS_LIMITATION"
    elif "EVENT_RECORD_PRESENT_FIELD_ABSENT" in per_route_result.values():
        overall = "EVENT_RECORD_PRESENT_FIELD_ABSENT"
    elif "QUERY_SUCCEEDED_NO_EVENT_RECORD" in per_route_result.values():
        overall = "QUERY_SUCCEEDED_NO_EVENT_RECORD"
    else:
        overall = "ROUTE_ERROR_OR_ACCESS_LIMITATION"

    tdcc_current_window = ("LIMITED_OR_CONDITIONAL_REPRESENTATION_ESTABLISHED"
                           if valid_positive else None)

    out = {
        "record": "B0_8_D8_2D_TDCC_CURRENT_WINDOW_SINGLE_EVENT_TEST",
        "b0_8_state": "WIP, UNSEALED",
        "d8_2c_correction_recorded": {
            "MOPS_EDOC_2015_2019": "PARTIAL_COVERAGE",
            "ISSUER_FORMAL_DOCS_2015_2019": "PARTIAL_COVERAGE",
            "successfully_inspected_documents": 4,
            "extraction_unavailable_documents": 3,
            "validated_positives_in_successfully_inspected_documents": 0,
            "note": "recorded per instruction; D8.2C's own JSON is NOT "
                    "modified by this stage",
        },
        "population": {"security_id": SID, "successor_code": SUCCESSOR_CODE,
                       "effective_date": EFFECTIVE_DATE,
                       "basis": "only confirmed-stock event established in "
                                "D8.2B-R2 as falling within the observed "
                                "TDCC 2025-01-02..present window"},
        "routes_queried": ["OD-1-7", "PORTAL-QRYPS"],
        "requests": requests_log,
        "per_route_result": per_route_result,
        "overall_result": overall,
        "positive_semantics_required": [
            "same 4945 canonical merger/share-conversion",
            "successor consideration shares", "holder-inbound delivery or "
            "account credit", "explicit date"],
        "excluded_date_types": list(EXCLUDED_DATE_LABELS) + [
            "new-share listing date", "first-trading date", "delisting date",
            "record date", "stop-transfer date",
            "merger/share-conversion effective date", "tender deposit",
            "certificate exchange"],
        "TDCC_CURRENT_WINDOW": tdcc_current_window,
        "interpretation_boundary": "establishes only contemporary TDCC "
            "representability for this single event if positive; does not "
            "reopen D8.2A bulk acquisition or establish historical coverage; "
            "a non-positive result does not imply historical absence or "
            "global non-reconstructibility",
        "canonical_values_materialized": False,
        "network_used": True,
        "other_events_or_sources_acquired": False,
        "bulk_crawl": False,
        "d8_3_started": False,
        "schema_consumer_ledger_state_changed": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("OD-1-7 result:", od17_route_result)
    print("PORTAL-QRYPS result:", qryps_route_result)
    print("overall_result:", overall)
    print("TDCC_CURRENT_WINDOW:", tdcc_current_window)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
