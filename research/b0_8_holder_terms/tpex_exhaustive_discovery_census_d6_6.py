# -*- coding: utf-8 -*-
"""B0.8 · D6.6 · TPEx exhaustive discovery completeness, all 59 events.

K0 · WHAT D6.6 IS, AND WHAT IT IS NOT

D6.5 is ACCEPTED as WIP evidence and is NOT rewritten. Its script, its router
freeze, its census JSON and its raw byte cache stay exactly as they are, and its
historical result stands on the record as

    UNIQUE = 38 · AMBIGUOUS = 1 · NONE = 20 · ERROR = 0

D6.6 repairs ONE defect in the D6.5 discovery algorithm: it enumerated only a
bounded prefix of the identity-fallback candidate pool. Nothing else moves.

K1 · THE D6.5 "NONE" POPULATION IS NOT HOMOGENEOUS

    DISCOVERY_UNRESOLVED_PROBE_CAP                             = 15
    DISCOVERY_NONE_WITHIN_FROZEN_WINDOW_AFTER_POOL_EXHAUSTION   = 5

The 15 terminated because BODY_FALLBACK_CAP = 150 was reached, at pool coverage
between 10.0% and 73.9%. A probe-cap termination is an ACQUISITION COMPLETENESS
LIMIT. It is not evidence that the official archive holds no document. Only the
5 exhausted cases carry that reading, and only within the frozen window.

K2 · SOLE REPAIR

    D6.5   probe = pool[:150]          bounded partial enumeration
    D6.6   probe = pool                complete enumeration

UNCHANGED, byte for byte, from the D6.5 router:

    frozen date window          [C - 30d, C + 40d]
    official TPEx surfaces      bulletin/announcement + annDetail + eb_data
    all-category routing        cate NEVER sent; category recovered after the
                                fact as diagnostic metadata only
    receiver parameter          NEVER sent
    security-code matching      D64.code_in_text, code-first
    body fallback               only subject-less / code-less index rows,
                                ordered 證櫃監字 first, then date, then number
    encoding detection          declared charset, then utf-8, big5, cp950
    event-linkage predicates    TERMINATION_MARKERS / REORG_MARKERS
    qualification rule          fetched body must BOTH name the security AND
                                establish a termination event
    UNIQUE / AMBIGUOUS rule     one qualifying document number vs more than one

No category, keyword, company name or transaction term is added. No window is
widened. This stage repairs partial enumeration and nothing else.

K2b · TRANSPORT CONCURRENCY IS NOT A SEMANTIC CHANGE

Exhaustive enumeration costs ~7.3k additional annDetail fetches. D6.5 fetched
sequentially at POLITE = 0.3s. D6.6 splits acquisition from adjudication:

    phase 1  PREFETCH    the SAME URL set, fetched concurrently to disk
    phase 2  ADJUDICATE  single-threaded, deterministic, reading ONLY disk

The URL set, the request construction, the decoding and every predicate are
identical; only wall-clock differs, and the adjudication order is fixed by the
frozen sort, not by completion order. Bytes already held by D6.5 are read from
the D6.5 cache read-only and are never re-fetched and never rewritten; new bytes
land in the D6.6 cache. The run is resumable: a killed prefetch resumes from
disk at zero cost.

K4 · DETERMINISTIC COMPLETENESS

Every event reports candidate rows in the frozen window, how many required the
body fallback, how many were actually inspected, and pool_exhausted. A final
NONE_WITHIN_FROZEN_WINDOW requires pool_exhausted = true. There is no cap left
to reach, so the only way to miss exhaustion is an unresolved transport or parse
failure on a candidate.

    pool_exhausted := every probed row was inspected to a decision

K4a · ONE CONSEQUENCE OF K4, RECORDED BECAUSE IT DIFFERS FROM D6.5

D6.5 classified an event with unresolved candidate errors and no qualifying body
as NONE. Under K4 that is no longer permissible: an uninspected candidate means
the pool was not exhausted, and an acquisition failure may not be reported as a
document absence -- the same defect class as D6.2's refusal page, D6.4's cate=4
filter and D6.5's Big5 mojibake. Such events now finish REQUEST_ERROR. This is
K4 being enforced, not a discovery-rule change: it can only move an event OUT of
NONE, never into UNIQUE or AMBIGUOUS.

K4b · WHY A CANDIDATE FAILED IS RECORDED SEPARATELY FROM WHETHER ONE EXISTED

D6.5 collapsed "no candidate was found" and "a candidate was found but did not
qualify" into one NONE. 5820 and 4947 each had one candidate and still scored
NONE. D6.6 records, per event, the funnel

    pool rows -> detail text names the code -> body fetched
              -> body names the code -> body establishes a termination event

and the failure reason of every non-qualifying candidate. Diagnostic only. It
does not alter the qualification rule.

K7 · THE FROZEN RECONSTRUCTION SCHEMA IS NOT TOUCHED

RECONSTRUCTIBLE_STOCK still requires the frozen successor/credit fields and
RECONSTRUCTIBLE_CASH still requires the frozen settlement fields. Field presence
being sparse is not authorization to relax a schema frozen before values were
seen. No reconstruction classification is computed here.

K8 · PRESENCE ONLY. No value is parsed, canonicalized or materialized.

K10 · INVARIANTS held for the whole stage: holder terms not materialized, zero
reconstruction classifications changed, CA ledger unchanged, canonical states
unchanged, replay not started, NAV not inspected, performance not inspected,
gates not evaluated, dual extraction not started, related-document acquisition
not started.

    python research/b0_8_holder_terms/tpex_exhaustive_discovery_census_d6_6.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

CENSUS_D61 = os.path.join(HERE, "document_discovery_census_d6_1.json")
CENSUS_D65 = os.path.join(HERE, "tpex_static_corpus_census_d6_5.json")
DIAG_D65 = os.path.join(HERE, "tpex_none_coverage_diagnostic_d6_5.json")
FREEZE = os.path.join(HERE, "tpex_static_router_freeze_d6_6.json")
OUT = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_6_tpex_raw")
RAW_D65 = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_5_tpex_raw")
STATE = os.path.join(RAW, "_progress.json")

TPEX = D64.TPEX
BULLETIN = D64.BULLETIN
ANN_DETAIL = D64.ANN_DETAIL
WINDOW_BACK_DAYS, WINDOW_FORWARD_DAYS = 30, 40
PAGING = {"paging-size": "500", "paging-offset": "0"}
# K2 · the D6.5 cap is removed, not raised. There is no bound.
BODY_FALLBACK_CAP = None
UNIT_PRIORITY = ("監", "審", "交", "視", "新", "債", "輔", "資")
CATEGORY_PROBE_ORDER = ("4", "1", "2", "15", "6", "8", "5", "17", "16", "9",
                        "10", "11", "12", "13", "14", "3", "7", "18", "19",
                        "20", "21", "22")
POLITE = 0.3
# K2b · transport only. Neither value can change any classification.
PREFETCH_WORKERS = 5
PREFETCH_POLITE = 0.25

STATIC_UNIQUE = "STATIC_EVENT_DOCUMENT_UNIQUE"
STATIC_NONE = "STATIC_EVENT_DOCUMENT_NONE_WITHIN_FROZEN_WINDOW"
STATIC_AMBIGUOUS = "STATIC_EVENT_DOCUMENT_AMBIGUOUS"
STATIC_ERROR = "STATIC_EVENT_DOCUMENT_REQUEST_ERROR"
CLASSES = (STATIC_UNIQUE, STATIC_NONE, STATIC_AMBIGUOUS, STATIC_ERROR)
D65_NONE = "STATIC_EVENT_DOCUMENT_NONE"

TERMINATION_MARKERS = ("終止", "停止櫃檯買賣", "停止買賣", "下櫃", "撤銷")
REORG_MARKERS = ("合併", "股份轉換", "股份交換", "概括讓與", "概括承受",
                 "控股公司", "存續公司", "消滅公司")

# K8 · presence markers only. No value is read out of any of these.
FIELD_PRESENCE_MARKERS = {
    "transaction_party": ("合併", "股份轉換", "存續公司", "消滅公司",
                          "控股公司", "概括讓與", "概括承受", "股份有限公司"),
    "stock_consideration": ("換股比例", "股份轉換比例", "轉換比例", "換發",
                            "每一股換發", "配發", "換發新股"),
    "cash_consideration": ("現金", "現金對價", "每股現金", "價款", "收購價格",
                           "現金補償"),
    "holder_effective_or_conversion_date": ("基準日", "合併基準日",
                                            "股份轉換基準日", "換股基準日",
                                            "停止櫃檯買賣", "最後交易日"),
    "payment_or_credit_date": ("發放", "撥付", "給付", "領取", "交付",
                               "開始換發", "換發日期", "上市買賣日"),
    "fractional_treatment": ("不足一股", "畸零股", "零股", "尾數", "現金補償"),
}

CODE4 = re.compile(r"\d{4}")
CHARSET = re.compile(rb"charset\s*=\s*[\"']?\s*([A-Za-z0-9_\-]+)", re.I)

FAIL_NO_DETAIL_ROUTE = "NO_DETAIL_ROUTE_ON_INDEX_ROW"
FAIL_DETAIL_ERROR = "DETAIL_FETCH_OR_PARSE_FAILED"
FAIL_DETAIL_NO_CODE = "DETAIL_TEXT_DOES_NOT_NAME_THE_SECURITY"
FAIL_BODY_FETCH = "OFFICIAL_BODY_FETCH_FAILED"
FAIL_BODY_NO_CODE = "BODY_DOES_NOT_NAME_THE_SECURITY"
FAIL_NO_TERMINATION = "BODY_ESTABLISHES_NO_TERMINATION_EVENT"
# The two that leave a candidate UNINSPECTED, and therefore break exhaustion.
UNINSPECTED = (FAIL_DETAIL_ERROR, FAIL_BODY_FETCH)


def decode_official(raw: bytes) -> str:
    """Honour the document's own declared charset. The archive is not utf-8."""
    m = CHARSET.search(raw[:2000])
    order = []
    if m:
        order.append(m.group(1).decode("ascii", "ignore").lower())
    order += ["utf-8", "big5", "cp950", "big5hkscs"]
    seen = set()
    for enc in order:
        enc = {"big5": "cp950"}.get(enc, enc)
        if not enc or enc in seen:
            continue
        seen.add(enc)
        try:
            return raw.decode(enc)
        except Exception:                                   # noqa: BLE001
            continue
    return raw.decode("utf-8", "replace")


def _disk(path):
    return open(path, "rb").read() if os.path.exists(path) else None


def _cached(name):
    """D6.6 cache first, then the D6.5 cache READ-ONLY. D6.5 is never written."""
    raw = _disk(os.path.join(RAW, name))
    if raw is not None:
        return raw, "d6_6"
    raw = _disk(os.path.join(RAW_D65, name))
    if raw is not None:
        return raw, "d6_5"
    return None, None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path, raw: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def unit_of(docnum: str) -> str:
    m = re.match(r"證櫃(\w)字", docnum or "")
    return m.group(1) if m else "?"


def unit_rank(docnum: str) -> int:
    u = unit_of(docnum)
    return UNIT_PRIORITY.index(u) if u in UNIT_PRIORITY else len(UNIT_PRIORITY)


def detail_route(row):
    qs = urllib.parse.parse_qs(
        urllib.parse.urlparse(row["detail_href"] or "").query)
    cf = (qs.get("content_file") or [""])[0]
    docid = (qs.get("docId") or [""])[0]
    return (cf, docid) if cf and docid else (None, None)


class Archive:
    """The frozen chain. Acquisition is concurrent; adjudication reads disk."""

    def __init__(self):
        self.months = {}
        self.detail = {}
        self.cate = {}
        self.errors = []
        self.reused_d65 = Counter()
        self.fetched_new = Counter()
        self._lock = threading.Lock()

    # ---- phase 1 : acquisition -------------------------------------------

    def month_rows(self, y, m):
        key = "%d-%02d" % (y, m)
        if key in self.months:
            return self.months[key]
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
        params = dict(startDate="%d/%02d/01" % (y, m),
                      endDate="%d/%02d/%02d" % (y, m, last), **PAGING)
        name = "bulletin_%s.json" % key
        raw, src = _cached(name)
        if raw is None:
            raw, err = D64._req(BULLETIN, params)
            if raw is None:
                self.errors.append({"month": key, "error": err})
                self.months[key] = {"error": err, "rows": [], "params": params}
                return self.months[key]
            _write(os.path.join(RAW, name), raw)
            self.fetched_new["bulletin"] += 1
            time.sleep(POLITE)
        elif src == "d6_5":
            self.reused_d65["bulletin"] += 1
        rows = []
        try:
            js = json.loads(raw.decode("utf-8", "replace"))
            for row in ((js.get("tables") or [{}])[0].get("data") or []):
                iso = D64.roc_to_iso(str(row[1]))
                rows.append({"date_roc": row[1], "date": iso,
                             "document_number": str(row[2] or ""),
                             "subject": row[3] or "", "detail_href": row[4]})
        except Exception as exc:                            # noqa: BLE001
            self.errors.append({"month": key, "error": "unparseable %s" % exc})
        self.months[key] = {"rows": rows, "raw_sha256": _sha(raw),
                            "bytes": len(raw), "params": params,
                            "row_count": len(rows)}
        return self.months[key]

    def prefetch_details(self, rows):
        """K2b · the same annDetail URL set D6.5 would have walked, in parallel.

        Writes bytes to the D6.6 cache and nothing else. Adjudication happens
        later, single-threaded, in the frozen order.
        """
        need = {}
        for r in rows:
            num = r["document_number"]
            if num in need or num in self.detail:
                continue
            cf, docid = detail_route(r)
            if not cf:
                continue
            raw, src = _cached("annDetail_%s.json" % num)
            if raw is None:
                need[num] = (cf, docid)
            elif src == "d6_5":
                self.reused_d65["annDetail"] += 1
        todo = sorted(need.items())
        if not todo:
            return 0
        done = [0]

        def pull(item):
            num, (cf, docid) = item
            raw, err = D64._req(ANN_DETAIL,
                                {"content_file": cf, "docId": docid})
            with self._lock:
                done[0] += 1
                if raw is None:
                    self.errors.append({"doc": num, "error": err})
                else:
                    _write(os.path.join(RAW, "annDetail_%s.json" % num), raw)
                    self.fetched_new["annDetail"] += 1
                if done[0] % 250 == 0 or done[0] == len(todo):
                    print("          prefetch %d/%d" % (done[0], len(todo)),
                          flush=True)
            time.sleep(PREFETCH_POLITE)

        print("          prefetching %d annDetail bodies" % len(todo),
              flush=True)
        with ThreadPoolExecutor(max_workers=PREFETCH_WORKERS) as pool:
            list(pool.map(pull, todo))
        return len(todo)

    # ---- phase 2 : adjudication ------------------------------------------

    def ann_detail(self, row):
        num = row["document_number"]
        if num in self.detail:
            return self.detail[num]
        cf, docid = detail_route(row)
        if not cf:
            self.detail[num] = None
            return None
        raw, src = _cached("annDetail_%s.json" % num)
        if raw is None:
            raw, err = D64._req(ANN_DETAIL,
                                {"content_file": cf, "docId": docid})
            if raw is None:
                self.errors.append({"doc": num, "error": err})
                self.detail[num] = {"error": err}
                return self.detail[num]
            _write(os.path.join(RAW, "annDetail_%s.json" % num), raw)
            self.fetched_new["annDetail"] += 1
            time.sleep(POLITE)
        try:
            d = (json.loads(decode_official(raw)).get("data") or {})
        except Exception as exc:                            # noqa: BLE001
            self.detail[num] = {"error": "unparseable %s" % exc}
            return self.detail[num]
        text = V14._plain("%s %s %s" % (d.get("subject", ""),
                                        d.get("depend", ""),
                                        d.get("content", "")))
        self.detail[num] = {
            "document_number": d.get("number") or num,
            "publication_date": d.get("date"),
            "subject": d.get("subject"), "text": text,
            "static_path": d.get("downHtml"),
            "detail_raw_sha256": _sha(raw),
            "detail_cache_source": src or "d6_6",
            "detail_request": {"surface": ANN_DETAIL, "content_file": cf,
                               "docId": docid}}
        return self.detail[num]

    def category_of(self, row):
        """Diagnostic metadata, recovered after the fact. Never a filter."""
        num, iso = row["document_number"], row["date"]
        if num in self.cate:
            return self.cate[num]
        if not iso:
            self.cate[num] = None
            return None
        y, m = int(iso[:4]), int(iso[5:7])
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
        for c in CATEGORY_PROBE_ORDER:
            key = "%d-%02d|%s" % (y, m, c)
            if key not in self.cate:
                name = "cate_%d-%02d_%s.json" % (y, m, c)
                raw, _src = _cached(name)
                if raw is None:
                    raw, _err = D64._req(BULLETIN,
                                         dict(startDate="%d/%02d/01" % (y, m),
                                              endDate="%d/%02d/%02d" % (y, m,
                                                                        last),
                                              cate=c, **PAGING))
                    if raw is not None:
                        _write(os.path.join(RAW, name), raw)
                    time.sleep(POLITE)
                nums = set()
                if raw is not None:
                    try:
                        js = json.loads(raw.decode("utf-8", "replace"))
                        nums = {str(r[2] or "") for r in
                                ((js.get("tables") or [{}])[0].get("data")
                                 or [])}
                    except Exception:                       # noqa: BLE001
                        pass
                self.cate[key] = nums
            if num in self.cate[key]:
                self.cate[num] = c
                return c
        self.cate[num] = "not_in_any_probed_category"
        return self.cate[num]

    def static_body(self, det):
        path = det.get("static_path")
        if not path:
            return None, "annDetail returned no downHtml"
        url = TPEX + path
        name = "static_%s.html" % det["document_number"]
        raw, _src = _cached(name)
        if raw is None:
            raw, err = D64._req(url, None)
            if raw is None:
                self.errors.append({"doc": det["document_number"],
                                    "error": err})
                return None, err
            _write(os.path.join(RAW, name), raw)
            self.fetched_new["static"] += 1
            time.sleep(POLITE)
        return (raw, url), None


def field_presence(text: str) -> dict:
    return {k: any(x in text for x in v)
            for k, v in FIELD_PRESENCE_MARKERS.items()}


def build_router(d65, capped_keys, exhausted_keys) -> dict:
    router = {
        "record": "B0_8_D6_6_TPEX_EXHAUSTIVE_DISCOVERY_ROUTER",
        "frozen_before_corpus_requests": True,
        "supersedes_for_discovery_only": d65["router_sha256"],
        "d6_5_preserved_historically": True,
        "d6_5_counts_not_rewritten": d65["counts"],
        "k1_none_population_reinterpreted": {
            "DISCOVERY_UNRESOLVED_PROBE_CAP": len(capped_keys),
            "DISCOVERY_NONE_WITHIN_FROZEN_WINDOW_AFTER_POOL_EXHAUSTION":
                len(exhausted_keys),
            "reading": ("a probe-cap termination is an acquisition "
                        "completeness limit, not evidence of document "
                        "absence"),
        },
        "k2_sole_repair": {
            "d6_5": "probe = pool[:150] -- bounded partial enumeration",
            "d6_6": "probe = pool -- complete enumeration",
            "body_fallback_cap": None,
        },
        "k2_unchanged": [
            "frozen date window [C-30d, C+40d]",
            "official TPEx surfaces",
            "all-category routing -- cate never sent",
            "receiver never sent",
            "security-code matching",
            "body fallback eligibility and ordering",
            "encoding detection",
            "event-linkage predicates",
            "UNIQUE / AMBIGUOUS rule",
        ],
        "k2b_transport_concurrency": {
            "same_url_set": True,
            "prefetch_workers": PREFETCH_WORKERS,
            "adjudication": "single-threaded, frozen order, disk only",
            "d6_5_cache": "read-only reuse, never rewritten",
            "semantic_change": False,
        },
        "k4a_error_is_not_absence": (
            "an event with an uninspected candidate cannot be exhausted, so it "
            "finishes REQUEST_ERROR rather than NONE; this can only move an "
            "event out of NONE, never into UNIQUE or AMBIGUOUS"),
        "surface": BULLETIN,
        "detail_surface": ANN_DETAIL,
        "static_root": TPEX + "/storage/eb_data/",
        "receiver_parameter": "never sent",
        "category_filter": "never sent -- all categories searched",
        "category_role": "diagnostic metadata only, recovered after matching",
        "date_format": "AD YYYY/MM/DD",
        "window_back_days": WINDOW_BACK_DAYS,
        "window_forward_days": WINDOW_FORWARD_DAYS,
        "window_tuning_in_d6_6": "FORBIDDEN -- K6",
        "keywords_categories_added_from_d6_5_misses": [],
        "identity_primary": "security code present in the official index subject",
        "identity_fallback": ("official body bytes, for rows whose subject is "
                              "empty or carries no code at all; ordered by "
                              "issuing unit 證櫃監字 first, then date and "
                              "document number; NO CAP"),
        "fallback_inputs_forbidden": ["TEJ narrative", "company-name inference",
                                      "counterparty name", "holder terms"],
        "unique_rule": ("the FETCHED body must establish the security and a "
                        "termination/reorganization event; two qualifying "
                        "bodies with different document numbers make the event "
                        "AMBIGUOUS"),
        "classes": list(CLASSES),
        "none_emission_precondition": "pool_exhausted == true",
        "population": "all 59 TPEx-lineage register events, no sampling",
        "rerun_scope": "59/59, not only the 15 capped failures",
        "event_specific_branches": [],
        "selection_blind_to": ["B0 holdings", "claim exposure", "8913", "3299",
                               "expected terms", "consideration type",
                               "replay usefulness", "performance"],
        "field_presence_markers": {k: list(v)
                                   for k, v in FIELD_PRESENCE_MARKERS.items()},
        "field_presence_is_metadata_only": True,
        "k7_reconstruction_schema": "FROZEN, UNCHANGED, NOT RELAXED",
        "prohibited": ["value extraction", "canonicalization",
                       "RECONSTRUCTIBLE classification", "CA rebuild",
                       "state rebuild", "replay", "NAV", "performance",
                       "gates", "dual extraction", "window widening",
                       "related-document acquisition"],
    }
    router["router_sha256"] = canonical_sha256(router)
    return router


def main() -> int:
    d61 = json.load(open(CENSUS_D61, encoding="utf-8"))
    events = sorted([r for r in d61["results"]
                     if r["market_lineage"] == "TPEX"],
                    key=lambda r: (r["canonical_event_date"],
                                   r["security_id"]))
    assert len(events) == 59, len(events)

    d65 = json.load(open(CENSUS_D65, encoding="utf-8"))
    d65_by_event = {r["event_id"]: r for r in d65["results"]}
    diag = json.load(open(DIAG_D65, encoding="utf-8"))
    capped_keys = {(e["security_id"], e["date"])
                   for e in diag["cap_limited_coverage_incomplete"]["events"]}
    exhausted_keys = {(e["security_id"], e["date"])
                      for e in
                      diag["pool_exhausted_within_frozen_window"]["events"]}

    router = build_router(d65, capped_keys, exhausted_keys)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(router, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("D6.6 router frozen:", router["router_sha256"], flush=True)
    print("K1  probe-cap unresolved = %d · pool-exhausted NONE = %d"
          % (len(capped_keys), len(exhausted_keys)), flush=True)

    arc = Archive()
    results, counts = [], Counter()
    for i, ev in enumerate(events, 1):
        sid = ev["security_id"]
        c = date.fromisoformat(ev["canonical_event_date"])
        lo, hi = c - timedelta(days=WINDOW_BACK_DAYS), c + timedelta(
            days=WINDOW_FORWARD_DAYS)
        key = (sid, ev["canonical_event_date"])
        prior = d65_by_event.get(ev["event_id"], {})
        rec = {"event_id": ev["event_id"], "security_id": sid,
               "canonical_event_date": c.isoformat(),
               "status_reason": ev["status_reason"],
               "window": [lo.isoformat(), hi.isoformat()],
               "d6_5_classification": prior.get("classification"),
               "d6_5_probe_cap_limited": key in capped_keys,
               "d6_5_pool_exhausted": key in exhausted_keys,
               "months_queried": [], "rows_in_window": 0,
               "errors": [], "candidates": [], "qualifying": [],
               "non_qualifying": []}
        rows, month_err = [], False
        y, m = lo.year, lo.month
        while (y, m) <= (hi.year, hi.month):
            got = arc.month_rows(y, m)
            rec["months_queried"].append({
                "month": "%d-%02d" % (y, m),
                "rows": got.get("row_count"),
                "raw_sha256": got.get("raw_sha256"),
                "error": got.get("error")})
            if got.get("error"):
                month_err = True
            for r in got["rows"]:
                if r["date"] and lo.isoformat() <= r["date"] <= hi.isoformat():
                    rows.append(r)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        rec["rows_in_window"] = len(rows)

        primary = [r for r in rows if D64.code_in_text(r["subject"], sid)]
        rec["identity_route"] = "PRIMARY_SUBJECT" if primary else None
        probe = primary
        if not primary:
            pool = [r for r in rows if not CODE4.search(r["subject"] or "")]
            pool.sort(key=lambda r: (unit_rank(r["document_number"]),
                                     r["date"] or "", r["document_number"]))
            probe = pool                                    # K2 · no cap
            rec["identity_route"] = "BODY_FALLBACK"
            rec["fallback_pool"] = len(pool)
            rec["fallback_probed"] = len(probe)
            rec["d6_5_fallback_probed"] = prior.get("fallback_probed")

        # K4 · deterministic completeness accounting
        rec["candidate_rows_in_frozen_window"] = len(rows)
        rec["candidate_bodies_requiring_fallback"] = (
            len(probe) if rec["identity_route"] == "BODY_FALLBACK" else 0)
        rec["candidate_bodies_actually_inspected"] = len(probe)

        print("  [%2d/59] %-6s %s route=%-14s probe=%d"
              % (i, sid, ev["canonical_event_date"], rec["identity_route"],
                 len(probe)), flush=True)
        arc.prefetch_details(probe)

        funnel = Counter()
        uninspected = 0
        for r in probe:
            det = arc.ann_detail(r)
            if det is None:
                funnel[FAIL_NO_DETAIL_ROUTE] += 1
                continue
            if det.get("error"):
                funnel[FAIL_DETAIL_ERROR] += 1
                uninspected += 1
                rec["errors"].append({"doc": r["document_number"],
                                      "error": det["error"],
                                      "leaves_candidate_uninspected": True})
                continue
            if not D64.code_in_text(det["text"], sid) and not primary:
                funnel[FAIL_DETAIL_NO_CODE] += 1
                continue
            funnel["detail_text_names_the_security"] += 1
            fetched, err = arc.static_body(det)
            cand = {"document_number": det["document_number"],
                    "publication_date": det["publication_date"],
                    "subject": det["subject"],
                    "issuing_unit": unit_of(det["document_number"]),
                    "detail_request": det["detail_request"],
                    "detail_raw_sha256": det["detail_raw_sha256"],
                    "static_url": (TPEX + det["static_path"]
                                   if det.get("static_path") else None),
                    "index_row": {"date": r["date"],
                                  "document_number": r["document_number"],
                                  "subject": r["subject"]}}
            if fetched is None:
                cand.update({"body_fetched": False, "fetch_error": err,
                             "qualification_failure": FAIL_BODY_FETCH})
                funnel[FAIL_BODY_FETCH] += 1
                uninspected += 1
                rec["errors"].append({"doc": det["document_number"],
                                      "error": err,
                                      "leaves_candidate_uninspected": True})
                rec["candidates"].append(cand)
                rec["non_qualifying"].append(
                    {"document_number": cand["document_number"],
                     "reason": FAIL_BODY_FETCH})
                continue
            raw, url = fetched
            text = V14._plain(decode_official(raw))
            keys = D64.code_in_text(text, sid)
            term = [t for t in TERMINATION_MARKERS if t in text]
            reorg = [t for t in REORG_MARKERS if t in text]
            cand.update({
                "body_fetched": True, "body_sha256": _sha(raw),
                "body_bytes": len(raw), "static_url": url,
                "matching_keys": keys,
                "body_identifies_security": bool(keys),
                "termination_markers": term, "reorganization_markers": reorg,
                "establishes_event": bool(term),
                "bulletin_category": arc.category_of(r),
                "field_presence": field_presence(text)})
            if keys and term:
                cand["qualification_failure"] = None
                rec["qualifying"].append(cand)
                funnel["qualifying"] += 1
            else:
                why = FAIL_BODY_NO_CODE if not keys else FAIL_NO_TERMINATION
                cand["qualification_failure"] = why
                funnel[why] += 1
                rec["non_qualifying"].append(
                    {"document_number": cand["document_number"],
                     "reason": why,
                     "body_identifies_security": bool(keys),
                     "reorganization_markers": reorg})
            rec["candidates"].append(cand)

        rec["funnel"] = dict(funnel)
        rec["uninspected_candidates"] = uninspected
        # K4 · exhaustion is a fact about inspection, not about outcome.
        rec["pool_exhausted"] = (not month_err) and uninspected == 0

        if month_err or not rec["pool_exhausted"]:
            # K4a · an acquisition failure is never reported as an absence.
            cls = (STATIC_UNIQUE if len({q["document_number"]
                                         for q in rec["qualifying"]}) == 1
                   else STATIC_AMBIGUOUS if rec["qualifying"]
                   else STATIC_ERROR)
        else:
            cls = (STATIC_NONE if not rec["qualifying"]
                   else STATIC_UNIQUE if len({q["document_number"]
                                              for q in rec["qualifying"]}) == 1
                   else STATIC_AMBIGUOUS)
        if cls == STATIC_NONE:
            assert rec["pool_exhausted"], rec["event_id"]
        rec["classification"] = cls
        counts[cls] += 1
        results.append(rec)
        print("          -> %-48s cands=%d qual=%d nonqual=%d exh=%s"
              % (cls, len(rec["candidates"]), len(rec["qualifying"]),
                 len(rec["non_qualifying"]), rec["pool_exhausted"]),
              flush=True)
        _write(STATE, json.dumps({"done": i}, ensure_ascii=False).encode())

    uniq = [r for r in results if r["classification"] == STATIC_UNIQUE]
    by_year, by_cat = Counter(), Counter()
    fetch_ok = fetch_fail = 0
    presence = Counter()
    for r in results:
        by_year[(r["canonical_event_date"][:4], r["classification"])] += 1
        for cand in r["candidates"]:
            if cand.get("body_fetched"):
                fetch_ok += 1
            else:
                fetch_fail += 1
    for r in uniq:
        q = r["qualifying"][0]
        by_cat[str(q.get("bulletin_category"))] += 1
        fp = q["field_presence"]
        for k, v in fp.items():
            if v:
                presence[k] += 1
        if fp["stock_consideration"] and fp["cash_consideration"]:
            presence["mixed_consideration"] += 1

    # K11 · what the removal of the cap actually bought
    capped_now = Counter(r["classification"] for r in results
                         if r["d6_5_probe_cap_limited"])
    exhausted_now = Counter(r["classification"] for r in results
                            if r["d6_5_pool_exhausted"])
    same = {D65_NONE: STATIC_NONE}
    changed = [{"security_id": r["security_id"],
                "canonical_event_date": r["canonical_event_date"],
                "d6_5": r["d6_5_classification"], "d6_6": r["classification"],
                "d6_5_probed": r.get("d6_5_fallback_probed"),
                "d6_6_probed": r.get("fallback_probed"),
                "qualifying_document_numbers": [q["document_number"]
                                                for q in r["qualifying"]]}
               for r in results
               if same.get(r["d6_5_classification"],
                           r["d6_5_classification"]) != r["classification"]]

    audit = {}
    for sid in ("3553", "6514", "3299", "8913"):
        row = [r for r in results if r["security_id"] == sid]
        if not row:
            audit[sid] = {"in_population": False}
            continue
        r = row[0]
        audit[sid] = {"d6_5_classification": r["d6_5_classification"],
                      "d6_6_classification": r["classification"],
                      "identity_route": r["identity_route"],
                      "d6_5_probed": r.get("d6_5_fallback_probed"),
                      "d6_6_probed": r.get("fallback_probed"),
                      "pool_exhausted": r["pool_exhausted"],
                      "candidates": len(r["candidates"]),
                      "qualifying": len(r["qualifying"]),
                      "non_qualifying": len(r["non_qualifying"]),
                      "document_numbers": [q["document_number"]
                                           for q in r["qualifying"]],
                      "special_handling": "none -- ordinary corpus outcome"}

    nonqual = Counter()
    for r in results:
        for nq in r["non_qualifying"]:
            nonqual[nq["reason"]] += 1
    funnel_total = Counter()
    for r in results:
        funnel_total.update(r["funnel"])

    out = {
        "record": "B0_8_D6_6_TPEX_EXHAUSTIVE_DISCOVERY_COMPLETENESS_CENSUS",
        "b0_8_state": "WIP, UNSEALED",
        "router_sha256": router["router_sha256"],
        "TPEX_TERMINATION_BULLETIN_HOLDER_TERM_COVERAGE": "UNKNOWN_CORPUS_WIDE",
        "d6_5_preserved": {
            "census_sha256": d65["census_sha256"],
            "router_sha256": d65["router_sha256"],
            "counts_not_rewritten": d65["counts"],
            "artefacts_rewritten": 0,
        },
        "k1_none_population_reinterpreted": router[
            "k1_none_population_reinterpreted"],
        "k2_sole_repair": router["k2_sole_repair"],
        "total": len(results),
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "k11_capped_cases_after_exhaustive_enumeration": dict(capped_now),
        "k11_already_exhausted_cases_after_rerun": dict(exhausted_now),
        "k11_classification_changes_vs_d6_5": changed,
        "final_genuinely_exhausted_none": counts.get(STATIC_NONE, 0),
        "candidate_bodies_inspected_total": sum(
            r["candidate_bodies_actually_inspected"] for r in results),
        "maximum_candidate_pool_size": max(
            (r.get("fallback_pool", 0) for r in results), default=0),
        "events_not_exhausted": [r["security_id"] for r in results
                                 if not r["pool_exhausted"]],
        "body_fetches_succeeded": fetch_ok,
        "body_fetches_failed": fetch_fail,
        "annDetail_reused_from_d6_5_cache": arc.reused_d65["annDetail"],
        "newly_fetched": dict(arc.fetched_new),
        "k4b_discovery_funnel_totals": dict(funnel_total),
        "k4b_non_qualifying_reason_counts": dict(nonqual),
        "by_event_year_and_class": {"%s|%s" % k: v
                                    for k, v in sorted(by_year.items())},
        "unique_by_bulletin_category": dict(by_cat),
        "field_presence_counts_on_unique_bodies": dict(presence),
        "unique_total_for_presence_denominator": len(uniq),
        "identity_route_counts": dict(Counter(r["identity_route"]
                                              for r in results)),
        "audit_3553_6514_3299_8913": audit,
        "archive_errors": arc.errors,
        "results": results,
        # K6
        "window_widened": False,
        "categories_or_keywords_added": False,
        "event_specific_branches": 0,
        # K7
        "reconstruction_schema_relaxed": False,
        # K10
        "holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "related_document_acquisition_started": False,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nD6.5 counts (preserved):", d65["counts"])
    print("D6.6 counts            :", dict(counts))
    print("capped-15 now          :", dict(capped_now))
    print("exhausted-5 now        :", dict(exhausted_now))
    print("bodies inspected       :", out["candidate_bodies_inspected_total"])
    print("max pool               :", out["maximum_candidate_pool_size"])
    print("reused from D6.5 cache :", out["annDetail_reused_from_d6_5_cache"])
    print("newly fetched          :", out["newly_fetched"])
    print("presence               :", dict(presence))
    print("non-qualifying reasons :", dict(nonqual))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
