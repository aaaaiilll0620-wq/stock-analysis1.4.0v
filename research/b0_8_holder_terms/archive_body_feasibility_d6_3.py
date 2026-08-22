# -*- coding: utf-8 -*-
"""B0.8 · D6.3 · alternative authoritative archive body feasibility.

D6.2 settled that the MOPS redirectToOld signed-body transport is
TRANSPORT_UNRESOLVED in this environment -- it failed identically for documents
whose genuine bodies are already preserved, so it says nothing about the
documents. That ladder is not retried here. The new question is whether the
SAME official announcement bodies are reachable through a FIRST-PARTY EXCHANGE
archival surface instead.

G2 · THE CORRECTED ACQUISITION-STATE CLASSIFIER

Generic, shape-based, no security-specific rule. It runs over the preserved
bytes only -- no network request is issued for the reclassification.

    REAL_ANNOUNCEMENT_BODY   carries the MOPS announcement template marker
    OFFICIAL_REFUSAL_PAGE    the site's refusal template 「該 <code> …！」 or a
                             查無… form. The frozen v1.4 markers knew only
                             不繼續公開發行 and 查無…; the 已下市 / 已下櫃
                             dialects went unrecognised, which is what made 90
                             refusals look like bodies
    OFFICIAL_THROTTLE_PAGE   查詢過於頻繁 / Overrun / 系統忙碌
    REQUEST_ERROR            the source answered about the request
    TRANSPORT_FAILURE        nothing preserved, or an empty body

G1 · HISTORY IS PRESERVED, NOT REWRITTEN. D6.1 keeps its originally reported
BODY_AVAILABLE = 146 and its counts (UNIQUE 17 / AMBIGUOUS 25 / NONE 116 = 7
NO_DOCUMENT_DISCOVERED + 109 DOCUMENT_DISCOVERED_BUT_LINKAGE_NOT_ESTABLISHED /
ERROR 0). The correction lives here, alongside it.

G3 · The 56 verified bodies stay admissible on their preserved provenance and
hashes. They are not re-downloaded for cosmetic reproducibility; their hashes
are re-verified in place.

G6 · THE FROZEN ARCHIVE ROUTER

  A1  TWSE_DAILY_MATERIAL_ANNOUNCEMENTS
      GET openapi.twse.com.tw/v1/opendata/t187ap04_L -- 上市公司每日重大訊息.
      First-party TWSE republication of the very rows this register holds, and
      it carries 說明, the full body. Identity keys: 公司代號 + 發言日期 +
      發言時間 + 主旨. Takes no parameters: it is a DAILY snapshot.

  A2  TPEX_DAILY_MATERIAL_ANNOUNCEMENTS
      GET www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O -- the TPEx equivalent,
      same fields, same daily-snapshot limitation.

  A3  TPEX_OFFICIAL_BULLETIN_ARCHIVE
      POST www.tpex.org.tw/www/zh-tw/bulletin/announcement -- 公告查詢, the
      exchange's OWN bulletins, keyed by 發文字號 and 資料日期, back to
      2001-10-12 per the form. startDate/endDate are AD YYYY/MM/DD (ROC is
      rejected with 日期參數錯誤). Frozen window: the calendar month of the
      document's publication date; cate=all and cate=4
      (變更交易方法、停止買賣、終止上櫃(股票)).
      A3 can never satisfy G7 for a company announcement: its identity keys are
      the exchange's own document number and date, not 公司代號 + 發言時間 +
      主旨. It is queried as SUPPLEMENTARY evidence about whether a related
      authoritative document exists, and is reported as identity FAIL by
      construction rather than being quietly counted as a hit.

  A4  TWSE_OFFICIAL_BULLETIN_ARCHIVE -- NOT FOUND.
      Bounded search, recorded so the absence is auditable: /zh/announcement/*
      enumerated (only notice.html resolves), the 143-endpoint TWSE OpenAPI
      catalogue contains no historical announcement query, and TWSE routes
      上市公司重大訊息 to MOPS rather than hosting an archive of its own.

G7 · A candidate counts as the SAME document only when deterministic
authoritative fields uniquely link it to the canonical row. Thematic similarity
is not linkage.

Forbidden throughout: third-party mirrors, TEJ, search-engine caches, web
archives, portfolio information, performance.

    python research/b0_8_holder_terms/archive_body_feasibility_d6_3.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import official_document_router_d6_1 as D61                # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

SEALED_V14 = os.path.join(HERE, "d6_1_historical",
                          "document_discovery_census_v1_4.json")
CENSUS_D61 = os.path.join(HERE, "document_discovery_census_d6_1.json")
FREEZE = os.path.join(HERE, "archive_router_freeze_d6_3.json")
OUT = os.path.join(HERE, "archive_body_feasibility_d6_3.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_3_archive_raw")

TWSE_DAILY = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
TPEX_DAILY = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"
TPEX_BULLETIN = "https://www.tpex.org.tw/www/zh-tw/bulletin/announcement"
TPEX_BULLETIN_CATEGORIES = ("all", "4")
TPEX_BULLETIN_ARCHIVE_START = "2001-10-12"

# --- G2 · the corrected classifier ------------------------------------------

REAL_ANNOUNCEMENT_BODY = "REAL_ANNOUNCEMENT_BODY"
OFFICIAL_REFUSAL_PAGE = "OFFICIAL_REFUSAL_PAGE"
OFFICIAL_THROTTLE_PAGE = "OFFICIAL_THROTTLE_PAGE"
TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
REQUEST_ERROR = "REQUEST_ERROR"
BODY_STATES = (REAL_ANNOUNCEMENT_BODY, OFFICIAL_REFUSAL_PAGE,
               OFFICIAL_THROTTLE_PAGE, TRANSPORT_FAILURE, REQUEST_ERROR)

TEMPLATE_MARKER = "本資料由"
THROTTLE_TOKENS = ("查詢過於頻繁", "Overrun", "系統忙碌", "請稍後再試")
REQUEST_ERROR_TOKENS = ("傳入參數異常", "參數錯誤", "日期參數錯誤",
                        "安全性考量", "無法呈現")
# The site's refusal template: 「該 <identifier> <clause>！」. Shape, not identity.
REFUSAL_SHAPE = re.compile(r"該\s*[0-9A-Za-z]{2,10}\s*[^!！。]{0,30}[!！]")
REFUSAL_TOKENS = ("查無", "不繼續公開發行", "已下市", "已下櫃", "已終止")


def classify_body(raw: bytes | None) -> tuple[str, str]:
    """Generic body-state classification from preserved bytes alone."""
    if raw is None or not raw.strip():
        return TRANSPORT_FAILURE, "no bytes preserved"
    text = V14._plain(raw.decode("utf-8", "replace"))
    if not text.strip():
        return TRANSPORT_FAILURE, "empty rendered body (%d bytes)" % len(raw)
    if any(t in text for t in THROTTLE_TOKENS):
        return OFFICIAL_THROTTLE_PAGE, text[:120]
    if TEMPLATE_MARKER in text:
        return REAL_ANNOUNCEMENT_BODY, text[:120]
    if any(t in text for t in REQUEST_ERROR_TOKENS):
        return REQUEST_ERROR, text[:120]
    m = REFUSAL_SHAPE.search(text)
    if m or any(t in text for t in REFUSAL_TOKENS):
        return OFFICIAL_REFUSAL_PAGE, (m.group(0) if m else text[:120])
    return TRANSPORT_FAILURE, "no template, no refusal: " + text[:100]


def normalized(text: str) -> str:
    """G8 · deterministic normalized content representation."""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\s　]+", "", t)
    return t


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path, raw: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def _get(url, timeout=120, retries=3):
    err = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), None
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:120])
            time.sleep(2.0 * (a + 1))
    return None, err


def _post(url, params, timeout=90, retries=3):
    err = None
    body = "&".join("%s=%s" % kv for kv in params.items()).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": ("https://www.tpex.org.tw/zh-tw/announce/market/"
                            "announce.html")})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), None
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:120])
            time.sleep(2.0 * (a + 1))
    return None, err


def main() -> int:
    v14 = json.load(open(SEALED_V14, encoding="utf-8"))
    d61 = json.load(open(CENSUS_D61, encoding="utf-8"))

    # ---- G2 · corrected census, cached bytes only --------------------------
    meta = {}
    for r in d61["results"]:
        for a in r["documents"]:
            legacy = a.get("legacy_document_id") or a["document_id"]
            meta[legacy] = {
                "canonical_document_id": a["document_id"],
                "security_id": r["security_id"],
                "market_lineage": r["market_lineage"],
                "publication_date": a["publication_date"],
                "subject": a["subject"], "event_id": r["event_id"]}
    corrected, per_market, evidence = Counter(), {}, {}
    for did, p in v14["document_provenance"].items():
        path = os.path.join(REPO, p["preserved_at"])
        raw = open(path, "rb").read() if os.path.exists(path) else None
        hash_ok = raw is not None and _sha(raw) == p.get("raw_sha256")
        state, why = classify_body(raw)
        corrected[state] += 1
        m = meta.get(did, {}).get("market_lineage", "UNKNOWN")
        per_market.setdefault(m, Counter())[state] += 1
        evidence[did] = {"state": state, "why": why, "hash_intact": hash_ok,
                         "bytes": len(raw) if raw else 0}
    print("corrected census :", dict(corrected), flush=True)

    # ---- G5 · deterministic sample -----------------------------------------
    # Stratum 2 is "no real body AND no explicit official refusal".
    strata = {}
    for did, e in evidence.items():
        m = meta.get(did, {}).get("market_lineage")
        if m not in ("TWSE", "TPEX"):
            continue
        if e["state"] == REAL_ANNOUNCEMENT_BODY:
            s = "verified_real_body"
        elif e["state"] == OFFICIAL_REFUSAL_PAGE:
            s = "official_refusal_historical_detail"
        else:
            s = "currently_unavailable_body"
        strata.setdefault((m, s), []).append(did)
    order = ("verified_real_body", "currently_unavailable_body",
             "official_refusal_historical_detail")
    selected = []
    for m in ("TWSE", "TPEX"):
        for s in order:
            pool = sorted(strata.get((m, s), []),
                          key=lambda d: _sha(meta[d]["canonical_document_id"]
                                             .encode()))
            if not pool:
                continue
            did = pool[0]
            selected.append({"market": m, "stratum": s, "legacy_id": did,
                             "document_id": meta[did][
                                 "canonical_document_id"],
                             "identity_sha256": _sha(
                                 meta[did]["canonical_document_id"].encode()),
                             "security_id": meta[did]["security_id"],
                             "publication_date": meta[did][
                                 "publication_date"],
                             "subject": meta[did]["subject"],
                             "previous_body_state": evidence[did]["state"]})

    router = {
        "record": "B0_8_D6_3_ARCHIVE_ROUTER",
        "frozen_before_any_request": True,
        "routes": [
            {"id": "A1", "agency": "TWSE", "surface": TWSE_DAILY,
             "content": "上市公司每日重大訊息 incl. 說明 (full body)",
             "parameters": "none -- daily snapshot",
             "identity_keys": ["公司代號", "發言日期", "發言時間", "主旨"]},
            {"id": "A2", "agency": "TPEx", "surface": TPEX_DAILY,
             "content": "上櫃公司每日重大訊息 incl. 說明 (full body)",
             "parameters": "none -- daily snapshot",
             "identity_keys": ["SecuritiesCompanyCode", "發言日期",
                               "發言時間", "主旨"]},
            {"id": "A3", "agency": "TPEx", "surface": TPEX_BULLETIN,
             "content": "本中心公告 (the exchange's own bulletins)",
             "parameters": "startDate/endDate as AD YYYY/MM/DD; cate",
             "frozen_window": "the calendar month of the publication date",
             "categories": list(TPEX_BULLETIN_CATEGORIES),
             "archive_start": TPEX_BULLETIN_ARCHIVE_START,
             "identity_keys": ["發文字號", "資料日期"],
             "g7_status": "cannot satisfy G7 for a company announcement -- "
                          "different identity keys; supplementary only"},
            {"id": "A4", "agency": "TWSE", "surface": None,
             "content": "no historical bulletin query surface found",
             "search_performed": ["/zh/announcement/* page enumeration",
                                  "TWSE OpenAPI catalogue (143 endpoints)",
                                  "TWSE routes 重大訊息 to MOPS"]},
        ],
        "allowed_routing_inputs": ["market lineage", "security_id",
                                   "publication date/time",
                                   "announcement subject",
                                   "canonical document identity"],
        "forbidden_sources": ["third_party_mirrors", "TEJ",
                              "search_engine_caches", "web_archives",
                              "portfolio_information", "performance"],
        "mops_r4_signed_detail_under_test": False,
        "identity_rule_g7": ("a candidate counts as the same document only if "
                             "deterministic authoritative fields uniquely link "
                             "it to the canonical row; thematic similarity is "
                             "not linkage"),
        "body_state_classifier": {
            "states": list(BODY_STATES),
            "template_marker": TEMPLATE_MARKER,
            "refusal_shape": REFUSAL_SHAPE.pattern,
            "refusal_tokens": list(REFUSAL_TOKENS),
            "throttle_tokens": list(THROTTLE_TOKENS),
            "request_error_tokens": list(REQUEST_ERROR_TOKENS),
            "security_specific_rules": False,
        },
        "corrected_population": dict(corrected),
        "corrected_population_by_market": {k: dict(v)
                                           for k, v in per_market.items()},
        "d6_1_history_preserved": {
            "originally_reported_body_available": 146,
            "counts": d61["counts"],
            "none_decomposition": d61["none_decomposition"],
            "census_sha256": d61["census_sha256"],
            "not_rewritten": True,
        },
        "selected": selected,
    }
    router["router_sha256"] = canonical_sha256(
        {k: v for k, v in router.items() if k != "selected"})
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(router, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("archive router frozen:", router["router_sha256"], flush=True)
    for s in selected:
        print("  %-6s %-36s %s" % (s["market"], s["stratum"],
                                   s["document_id"]), flush=True)

    # ---- execute ------------------------------------------------------------
    daily = {}
    for rid, url in (("A1", TWSE_DAILY), ("A2", TPEX_DAILY)):
        raw, err = _get(url)
        if raw is None:
            daily[rid] = {"error": err, "rows": []}
            continue
        _write(os.path.join(RAW, "%s_daily.json" % rid), raw)
        try:
            rows = json.loads(raw.decode("utf-8", "replace"))
        except Exception as exc:                            # noqa: BLE001
            daily[rid] = {"error": "unparseable: %s" % exc, "rows": []}
            continue
        daily[rid] = {"raw_sha256": _sha(raw), "bytes": len(raw),
                      "rows": rows, "row_count": len(rows),
                      "dates_present": sorted({
                          str(r.get("發言日期") or r.get("Date") or "")
                          for r in rows})[:6]}
        print("  %s rows=%d dates=%s" % (rid, len(rows),
                                         daily[rid]["dates_present"]),
              flush=True)

    results = []
    for s in selected:
        did = s["document_id"]
        co, dt, tm, _sq = did.split(":")[1:]
        roc_date = "%d%s%s" % (int(dt[:4]) - 1911, dt[4:6], dt[6:])
        rid = "A1" if s["market"] == "TWSE" else "A2"
        rec = {**s, "archive_routes_attempted": [rid], "attempts": []}

        rows = daily.get(rid, {}).get("rows") or []
        match = None
        for row in rows:
            code = str(row.get("公司代號") or
                       row.get("SecuritiesCompanyCode") or "")
            rdate = str(row.get("發言日期") or "")
            rtime = str(row.get("發言時間") or "")
            if code == co and rdate == roc_date and rtime.zfill(6) == tm:
                match = row
                break
        rec["attempts"].append({
            "route": rid, "surface": TWSE_DAILY if rid == "A1" else TPEX_DAILY,
            "rows_searched": len(rows),
            "matching_keys": {"公司代號": co, "發言日期": roc_date,
                              "發言時間": tm},
            "archive_document_found": bool(match),
            "identity_linkage": "PASS" if match else "FAIL",
            "reason": ("identity keys matched" if match else
                       "the snapshot contains only the current publication "
                       "day; this document's day is not in it"),
            "error": daily.get(rid, {}).get("error"),
            "response_sha256": daily.get(rid, {}).get("raw_sha256")})

        if s["market"] == "TPEX":
            rec["archive_routes_attempted"].append("A3")
            month_start = "%s/%s/01" % (dt[:4], dt[4:6])
            nxt = (int(dt[:4]) + 1, 1) if dt[4:6] == "12" else (int(dt[:4]),
                                                                int(dt[4:6]) + 1)
            month_end = "%s/%s/01" % (nxt[0], "%02d" % nxt[1])
            for cate in TPEX_BULLETIN_CATEGORIES:
                raw, err = _post(TPEX_BULLETIN, {
                    "startDate": month_start, "endDate": month_end,
                    "cate": cate, "txtKeyword": "", "receiver": ""})
                total, stat = None, None
                if raw is not None:
                    _write(os.path.join(RAW, "A3_%s_%s.json"
                                        % (did.replace(":", "_"), cate)), raw)
                    try:
                        j = json.loads(raw.decode("utf-8", "replace"))
                        stat = j.get("stat")
                        total = (j.get("tables") or [{}])[0].get("totalCount")
                    except Exception:                       # noqa: BLE001
                        stat = "unparseable"
                rec["attempts"].append({
                    "route": "A3", "surface": TPEX_BULLETIN,
                    "window": [month_start, month_end], "cate": cate,
                    "stat": stat, "rows_returned": total,
                    "archive_document_found": False,
                    "identity_linkage": "FAIL",
                    "reason": ("exchange bulletins are keyed by 發文字號 / "
                               "資料日期 and carry no 公司代號 + 發言時間 + "
                               "主旨, so they cannot uniquely link to a "
                               "company announcement row"),
                    "error": err,
                    "response_sha256": _sha(raw) if raw is not None else None})
                time.sleep(0.8)

        found = any(a["archive_document_found"] for a in rec["attempts"])
        rec.update({"archive_document_found": found,
                    "identity_linkage": "PASS" if found else "FAIL",
                    "body_acquired": found,
                    "body_sha256": None,
                    "verified_body_control_comparison": None})

        # ---- G8 control -----------------------------------------------------
        if s["stratum"] == "verified_real_body":
            p = v14["document_provenance"][s["legacy_id"]]
            preserved = open(os.path.join(REPO, p["preserved_at"]), "rb").read()
            rec["preserved_body_sha256"] = _sha(preserved)
            rec["preserved_body_hash_intact"] = (
                rec["preserved_body_sha256"] == p["raw_sha256"])
            rec["verified_body_control_comparison"] = (
                "NOT_APPLICABLE -- the archive route returned no matching "
                "document, so there is nothing to compare; the preserved "
                "authoritative body is untouched and its hash re-verifies"
                if not found else "PENDING")
        results.append(rec)
        print("  %s %s -> found=%s linkage=%s" % (
            s["market"], did, rec["archive_document_found"],
            rec["identity_linkage"]), flush=True)

    found_any = [r for r in results if r["archive_document_found"]]
    prev_missing = [r for r in results
                    if r["previous_body_state"] != REAL_ANNOUNCEMENT_BODY]
    gained = [r for r in prev_missing if r["body_acquired"]]
    transport = [r for r in results
                 if any(a.get("error") for a in r["attempts"])
                 and not r["archive_document_found"]]
    if gained and len(gained) == len(prev_missing):
        verdict = "FEASIBLE"
    elif gained:
        verdict = "PARTIALLY_FEASIBLE"
    elif len(transport) >= max(1, len(results) // 2):
        verdict = "TRANSPORT_UNRESOLVED"
    else:
        verdict = "NOT_FEASIBLE"

    out = {
        "record": "B0_8_D6_3_ALTERNATIVE_ARCHIVE_BODY_FEASIBILITY",
        "b0_8_state": "WIP, UNSEALED",
        "ALTERNATIVE_AUTHORITATIVE_BODY_ROUTE": verdict,
        "archive_router_sha256": router["router_sha256"],
        "archive_router_path": os.path.relpath(FREEZE, REPO),
        "corrected_781_body_state_census": dict(corrected),
        "corrected_by_market": {k: dict(v) for k, v in per_market.items()},
        "d6_1_history_preserved": router["d6_1_history_preserved"],
        "d6_2_correction_recorded": {
            "verified_real_body_available": corrected[REAL_ANNOUNCEMENT_BODY],
            "previously_misclassified_refusal_pages": 90,
            "dialects": {"上市公司已下市": 84, "上櫃公司已下櫃": 6},
        },
        "verified_bodies_hash_intact": sum(
            1 for did, e in evidence.items()
            if e["state"] == REAL_ANNOUNCEMENT_BODY and e["hash_intact"]),
        "sample_size": len(results),
        "sample_size_intended": 6,
        "empty_strata": [k for k in
                         [(m, s) for m in ("TWSE", "TPEX")
                          for s in order] if not strata.get(k)],
        "daily_snapshot_provenance": {
            k: {kk: vv for kk, vv in v.items() if kk != "rows"}
            for k, v in daily.items()},
        "results": results,
        "dual_extraction_performed": False,
        "reconstruction_classification_performed": False,
        "canonical_terms_materialized": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_computed": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "unruled_linkage_marker_added": False,
        "scaled_to_corpus": False,
    }
    out["record_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nALTERNATIVE_AUTHORITATIVE_BODY_ROUTE :", verdict)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
