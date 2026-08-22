# -*- coding: utf-8 -*-
"""B0.8 · D6.4 · TPEx static official archive discovery feasibility.

D6.3's verdict is narrowed as ruled: TESTED_D6_3_ROUTES_A1_TO_A4 = NOT_FEASIBLE,
which is NOT the claim that no alternative authoritative archive exists. One
does, and this stage tests whether it is reachable DETERMINISTICALLY from the
frozen event identifiers alone.

H1 · THE CHAIN UNDER TEST, and the two propositions kept apart

    security_id + canonical event date + TPEx lineage
      -> TPEx 公告查詢 row            (official document number 發文字號)
      -> bulletin/annDetail          (docId -> downHtml)
      -> /storage/eb_data/<ROC yyymm>/<document number>.html   (official body)

DISCOVERABILITY is whether the first two arrows can be walked from the frozen
identifiers. FETCHABILITY is whether the last one yields bytes. They are
reported separately and never merged.

THE SURFACE, AND THE PARAMETER THAT HID IT

D6.3 recorded A3 as returning 0 rows for every historical window. That was a
CLIENT DEFECT, not an empty archive. The query takes AD dates (`2018/11/01`;
ROC is rejected with 日期參數錯誤) -- but sending an EMPTY `receiver=` silently
zeroes the result set while still answering `stat: ok`. Dropping `receiver`
entirely, the same window returns 148 rows, and the archive reaches back to at
least 2004. A parameter that empties a result set without erroring is exactly
the kind of thing that reads as "the record does not exist".

    cate=4  =  變更交易方法、停止買賣、終止上櫃(股票)

FROZEN BEFORE REQUESTS

    window W = [C - 30 days, C + 40 days], C = canonical disappearance date.
    The exchange's termination date runs 5..13 days after C (measured at D3),
    and the bulletin announcing it precedes that date, so W brackets both.
    W is expanded to the calendar months intersecting it; one query per month.

    Row match, code-first: the row's 主旨 names the security by code
    (股票代號 / 證券代號 / 代號 followed by the id, or the id in parentheses).
    OLDER ROWS CARRY AN EMPTY 主旨 -- 2005 bulletins publish only 發文字號 and
    date -- so when no subject matches, every cate=4 row in the window has its
    body fetched and is matched on the body text instead. The fallback is part
    of the frozen protocol, not a reaction to a result.

H5 · Success requires the OFFICIAL BODY ITSELF to identify the disappearing
security and the event -- not the index row that led to it.

H4 · The sample is the four lowest event-id hashes among TPEx-lineage register
events EXCLUDING 3299 and 8913, so preobserved URLs cannot make the test
self-fulfilling. H6 · those two are then run as disclosed positive controls,
through the identical protocol, and the protocol is not altered if they fail.

H2 · No MOPS body work: redirectToOld, signed MOPS URLs and the A1/A2
current-day feeds are closed for this stage. H3 · no search engine is part of
the router. H8 · no extraction, no reconstruction, no rebuild, no replay, no
NAV, no performance, no gates.

    python research/b0_8_holder_terms/tpex_static_archive_d6_4.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

CENSUS_D61 = os.path.join(HERE, "document_discovery_census_d6_1.json")
FREEZE = os.path.join(HERE, "tpex_static_router_freeze_d6_4.json")
OUT = os.path.join(HERE, "tpex_static_archive_d6_4.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_4_tpex_raw")

TPEX = "https://www.tpex.org.tw"
BULLETIN = TPEX + "/www/zh-tw/bulletin/announcement"
ANN_DETAIL = TPEX + "/www/zh-tw/bulletin/annDetail"
CATE_DELISTING = "4"
WINDOW_BACK_DAYS, WINDOW_FORWARD_DAYS = 30, 40
PAGING = {"paging-size": "500", "paging-offset": "0"}
PRIMARY_SAMPLE_SIZE = 4
PREOBSERVED_CONTROLS = ("3299", "8913")
POLITE = 0.5
BODY_FALLBACK_CAP = 60

HEAD = {"User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": TPEX + "/zh-tw/announce/market/announce.html"}

EVENT_MARKERS = ("終止", "停止", "下櫃", "櫃檯買賣")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path, raw: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def _req(url, params=None, timeout=90, retries=3):
    err = None
    data = None
    if params is not None:
        # `receiver` is deliberately never sent: an empty one silently
        # zeroes the result set while still answering stat: ok.
        data = "&".join("%s=%s" % (k, urllib.parse.quote(str(v)))
                        for k, v in params.items()).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=HEAD)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), None
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:130])
            time.sleep(1.8 * (a + 1))
    return None, err


def months(lo: date, hi: date):
    y, m, out = lo.year, lo.month, []
    while (y, m) <= (hi.year, hi.month):
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
        out.append((y, m, last))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def code_in_text(text: str, sid: str) -> list[str]:
    """Code-first identity match. Returns the matching keys actually seen."""
    keys = []
    if re.search(r"(?:股票代號|證券代號|代號)[：:\s]*[（(]?\s*" + sid + r"(?!\d)",
                 text):
        keys.append("股票代號=%s" % sid)
    if re.search(r"[（(]\s*" + sid + r"\s*[）)]", text):
        keys.append("(%s)" % sid)
    return keys


def roc_to_iso(s: str) -> str | None:
    m = re.match(r"(\d{2,3})/(\d{2})/(\d{2})", s or "")
    if not m:
        return None
    return "%04d-%s-%s" % (int(m.group(1)) + 1911, m.group(2), m.group(3))


def discover(sid: str, c: date, tag: str) -> dict:
    """The frozen chain, run for one event."""
    lo, hi = c - timedelta(days=WINDOW_BACK_DAYS), c + timedelta(
        days=WINDOW_FORWARD_DAYS)
    rec = {"security_id": sid, "canonical_event_date": c.isoformat(),
           "window": [lo.isoformat(), hi.isoformat()], "queries": [],
           "rows_in_window": 0, "subject_matches": [], "body_matches": [],
           "errors": []}
    rows = []
    for y, m, last in months(lo, hi):
        params = dict(startDate="%d/%02d/01" % (y, m),
                      endDate="%d/%02d/%02d" % (y, m, last),
                      cate=CATE_DELISTING, **PAGING)
        raw, err = _req(BULLETIN, params)
        q = {"surface": BULLETIN, "params": params}
        if raw is None:
            q["error"] = err
            rec["errors"].append(err)
            rec["queries"].append(q)
            continue
        _write(os.path.join(RAW, "%s_bulletin_%d%02d.json" % (tag, y, m)), raw)
        q["raw_sha256"] = _sha(raw)
        try:
            js = json.loads(raw.decode("utf-8", "replace"))
            table = (js.get("tables") or [{}])[0]
            data = table.get("data") or []
            q["stat"] = js.get("stat")
            q["rows"] = len(data)
        except Exception as exc:                            # noqa: BLE001
            q["error"] = "unparseable: %s" % exc
            rec["queries"].append(q)
            continue
        rec["queries"].append(q)
        for row in data:
            iso = roc_to_iso(str(row[1]))
            if iso and lo.isoformat() <= iso <= hi.isoformat():
                rows.append({"date_roc": row[1], "date": iso,
                             "document_number": row[2], "subject": row[3],
                             "detail_href": row[4]})
        time.sleep(POLITE)
    rec["rows_in_window"] = len(rows)

    candidates = [r for r in rows if code_in_text(r["subject"] or "", sid)]
    for r in candidates:
        r["matching_keys"] = code_in_text(r["subject"], sid)
    rec["subject_matches"] = [r["document_number"] for r in candidates]
    fallback = not candidates
    rec["subject_match_used"] = not fallback
    probe = candidates if candidates else rows[:BODY_FALLBACK_CAP]
    rec["body_fallback_used"] = fallback
    rec["body_fallback_rows_probed"] = len(probe) if fallback else 0

    found = []
    for r in probe:
        href = r["detail_href"] or ""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        cf = (qs.get("content_file") or [""])[0]
        docid = (qs.get("docId") or [""])[0]
        if not cf or not docid:
            continue
        raw, err = _req(ANN_DETAIL, {"content_file": cf, "docId": docid})
        if raw is None:
            rec["errors"].append("annDetail %s: %s" % (r["document_number"],
                                                       err))
            continue
        try:
            js = json.loads(raw.decode("utf-8", "replace"))
            d = js.get("data") or {}
        except Exception:                                   # noqa: BLE001
            continue
        down = d.get("downHtml")
        detail_text = V14._plain(
            ("%s %s %s" % (d.get("subject", ""), d.get("depend", ""),
                           d.get("content", ""))))
        keys = code_in_text(detail_text, sid) or r.get("matching_keys") or []
        entry = {"document_number": d.get("number") or r["document_number"],
                 "publication_date": d.get("date"), "subject": d.get("subject"),
                 "static_url": (TPEX + down) if down else None,
                 "detail_raw_sha256": _sha(raw),
                 "detail_request": {"surface": ANN_DETAIL,
                                    "content_file": cf, "docId": docid,
                                    "docId_decoded": base64.b64decode(
                                        docid + "==").decode("utf-8", "replace")},
                 "matching_keys": keys,
                 "identifies_security_in_body": bool(keys),
                 "event_markers_in_body": [m for m in EVENT_MARKERS
                                           if m in detail_text]}
        _write(os.path.join(RAW, "%s_annDetail_%s.json"
                            % (tag, entry["document_number"])), raw)
        if keys:
            found.append(entry)
        time.sleep(POLITE)
    rec["body_matches"] = found
    rec["FIRST_PARTY_DOCUMENT_ID_DISCOVERED"] = "YES" if found else "NO"

    fetched = []
    for e in found:
        if not e["static_url"]:
            continue
        raw, err = _req(e["static_url"], None)
        if raw is None:
            e["static_fetch_error"] = err
            continue
        _write(os.path.join(RAW, "%s_static_%s.html"
                            % (tag, e["document_number"])), raw)
        text = V14._plain(raw.decode("utf-8", "replace"))
        e.update({"body_sha256": _sha(raw), "body_bytes": len(raw),
                  "body_identifies_security": bool(code_in_text(text, sid)),
                  "body_event_markers": [m for m in EVENT_MARKERS
                                         if m in text],
                  "body_head": text[:220]})
        if e["body_identifies_security"]:
            fetched.append(e)
        time.sleep(POLITE)
    rec["STATIC_BODY_FETCHED"] = "YES" if fetched else "NO"
    rec["fetched"] = fetched
    return rec


def main() -> int:
    d61 = json.load(open(CENSUS_D61, encoding="utf-8"))
    tpex_events = [r for r in d61["results"]
                   if r["market_lineage"] == "TPEX"]
    pool = sorted([r for r in tpex_events
                   if r["security_id"] not in PREOBSERVED_CONTROLS],
                  key=lambda r: _sha(r["event_id"].encode()))
    primary = pool[:PRIMARY_SAMPLE_SIZE]
    controls = [r for r in tpex_events
                if r["security_id"] in PREOBSERVED_CONTROLS]

    router = {
        "record": "B0_8_D6_4_TPEX_STATIC_ARCHIVE_ROUTER",
        "frozen_before_any_request": True,
        "narrowing": {
            "TESTED_D6_3_ROUTES_A1_TO_A4": "NOT_FEASIBLE",
            "must_not_be_generalised_to":
                "NO_ALTERNATIVE_AUTHORITATIVE_ARCHIVE_EXISTS",
        },
        "adjudication_static_archive_preobservation": True,
        "preobserved_event_ids": [3299, 8913],
        "performance_inspection": False,
        "preobserved_excluded_from_primary_sample": True,
        "chain": ["security_id + canonical date + TPEx lineage",
                  "TPEx 公告查詢 bulletin/announcement (cate=4)",
                  "bulletin/annDetail -> downHtml",
                  "/storage/eb_data/<ROC yyymm>/<document number>.html"],
        "surfaces": {"bulletin": BULLETIN, "detail": ANN_DETAIL,
                     "static_root": TPEX + "/storage/eb_data/"},
        "date_format": "AD YYYY/MM/DD (ROC is rejected: 日期參數錯誤)",
        "receiver_parameter": ("never sent -- an empty receiver= silently "
                               "zeroes the result set while answering stat: ok, "
                               "which is what made D6.3's A3 look empty"),
        "cate": {CATE_DELISTING: "變更交易方法、停止買賣、終止上櫃(股票)"},
        "window_back_days": WINDOW_BACK_DAYS,
        "window_forward_days": WINDOW_FORWARD_DAYS,
        "window_expansion": "calendar months intersecting the window",
        "row_match": "code-first: 股票代號/證券代號/代號 + id, or (id)",
        "body_fallback": ("older bulletins publish an empty 主旨, so when no "
                          "subject matches, every cate=4 row in the window is "
                          "body-checked; cap %d" % BODY_FALLBACK_CAP),
        "success_criterion_h5": ("the official body itself must identify the "
                                 "disappearing security and the event"),
        "allowed_routing_inputs": ["security_id", "TPEx lineage",
                                   "canonical event date",
                                   "fixed predeclared window"],
        "forbidden_routing_inputs": ["holder consideration", "counterparty name",
                                     "TEJ narrative", "B0 exposure",
                                     "8913-specific knowledge", "performance",
                                     "public search engine"],
        "mops_body_routes_closed_this_stage": ["redirectToOld",
                                               "signed MOPS body URLs",
                                               "A1/A2 current-day feeds"],
        "primary_sample": [{"event_id": r["event_id"],
                            "security_id": r["security_id"],
                            "canonical_event_date": r["canonical_event_date"],
                            "event_id_sha256": _sha(r["event_id"].encode())}
                           for r in primary],
        "disclosed_controls": [r["security_id"] for r in controls],
        "prohibited": ["dual extraction", "holder-term materialization",
                       "reconstruction classification", "CA rebuild",
                       "state rebuild", "replay", "NAV", "performance",
                       "gates", "scaling to all TPEx events"],
    }
    router["router_sha256"] = canonical_sha256(router)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(router, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("router frozen :", router["router_sha256"], flush=True)
    for r in primary:
        print("  primary %-6s %s  %s" % (r["security_id"],
                                         r["canonical_event_date"],
                                         _sha(r["event_id"].encode())[:12]),
              flush=True)

    results = []
    for r in primary:
        rec = discover(r["security_id"],
                       date.fromisoformat(r["canonical_event_date"]),
                       "primary_%s" % r["security_id"])
        rec.update({"event_id": r["event_id"], "role": "primary"})
        results.append(rec)
        print("  %-6s discovery=%s fetch=%s rows=%d" % (
            r["security_id"], rec["FIRST_PARTY_DOCUMENT_ID_DISCOVERED"],
            rec["STATIC_BODY_FETCHED"], rec["rows_in_window"]), flush=True)

    control_results = []
    for r in controls:
        rec = discover(r["security_id"],
                       date.fromisoformat(r["canonical_event_date"]),
                       "control_%s" % r["security_id"])
        rec.update({"event_id": r["event_id"], "role": "disclosed_control"})
        control_results.append(rec)
        print("  control %-6s discovery=%s fetch=%s" % (
            r["security_id"], rec["FIRST_PARTY_DOCUMENT_ID_DISCOVERED"],
            rec["STATIC_BODY_FETCHED"]), flush=True)

    disc = sum(1 for r in results
               if r["FIRST_PARTY_DOCUMENT_ID_DISCOVERED"] == "YES")
    fet = sum(1 for r in results if r["STATIC_BODY_FETCHED"] == "YES")
    n = len(results)
    discovery_verdict = ("FEASIBLE" if disc == n else
                         "PARTIALLY_FEASIBLE" if disc else "NOT_FEASIBLE")
    if fet == disc and disc:
        fetch_verdict = "FEASIBLE"
    elif fet:
        fetch_verdict = "PARTIALLY_FEASIBLE"
    elif any(r["errors"] for r in results):
        fetch_verdict = "TRANSPORT_UNRESOLVED"
    else:
        fetch_verdict = "NOT_FEASIBLE"

    out = {
        "record": "B0_8_D6_4_TPEX_STATIC_ARCHIVE_FEASIBILITY",
        "b0_8_state": "WIP, UNSEALED",
        "TPEX_STATIC_ARCHIVE_DISCOVERY": discovery_verdict,
        "TPEX_STATIC_ARCHIVE_FETCH": fetch_verdict,
        "TESTED_D6_3_ROUTES_A1_TO_A4": "NOT_FEASIBLE",
        "d6_3_verdict_not_generalised": True,
        "router_sha256": router["router_sha256"],
        "router_path": os.path.relpath(FREEZE, REPO),
        "primary_sample_size": n,
        "primary_discovered": disc,
        "primary_fetched": fet,
        "results": results,
        "disclosed_controls": control_results,
        "control_note": ("3299 and 8913 were excluded from the primary sample "
                         "and run afterwards through the identical protocol; "
                         "the protocol was not altered for them"),
        "adjudication_static_archive_preobservation": True,
        "preobserved_event_ids": [3299, 8913],
        "performance_inspection": False,
        "holder_terms_extracted": False,
        "reconstruction_classification_performed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_computed": False,
        "gates_evaluated": False,
        "scaled_to_all_tpex_events": False,
    }
    out["record_sha256"] = canonical_sha256(
        {k: v for k, v in out.items()
         if k not in ("results", "disclosed_controls")})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nTPEX_STATIC_ARCHIVE_DISCOVERY :", discovery_verdict)
    print("TPEX_STATIC_ARCHIVE_FETCH     :", fetch_verdict)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
