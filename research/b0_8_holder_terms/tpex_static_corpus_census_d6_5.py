# -*- coding: utf-8 -*-
"""B0.8 · D6.5 · TPEx static archive corpus discovery census, all 59 events.

J1 · FACTUAL CORRECTION, RECORDED FIRST

My D6.4 report said the TPEx termination bulletin "does not carry holder terms".
That is WITHDRAWN: the authoritative control bodies falsify it. 3299's
證櫃監字第10702101681號 carries stock conversion consideration and 8913's
證櫃監字第10800136464號 carries cash consideration. The honest state of knowledge
is therefore

    TPEX_TERMINATION_BULLETIN_HOLDER_TERM_COVERAGE = UNKNOWN_CORPUS_WIDE

and D6.5 measures only PRESENCE, never values.

J2 · THE D6.4 ROUTER DEFECTS, RECORDED AND NOT REWRITTEN

    receiver="" returning zero rows      CLIENT_REQUEST_CONFORMANCE_DEFECT
    cate=4 as a mandatory filter         UNDERINCLUSIVE

The 6514 diagnostic is generic: its bulletin exists, sits in the window, names
the code and states the canonical stop date, and TPEx simply did not file it
under cate=4. D6.4's router and hash stay exactly as they are; this is a new
router with a new hash.

J3 · THE D6.5 ROUTER

    POST /www/zh-tw/bulletin/announcement
      startDate / endDate   AD YYYY/MM/DD (ROC is rejected)
      paging-size 500
      receiver              NEVER SENT
      cate                  NEVER SENT -- all categories are searched
    Category is recovered afterwards, per matched document, as DIAGNOSTIC
    METADATA ONLY. It never filters discovery.

    Window W = [C - 30d, C + 40d], expanded to intersecting calendar months and
    cached, so events sharing a month share one request.

J4 · IDENTITY MATCHING

    PRIMARY   the security's code appears in the official index subject
              (股票代號 / 證券代號 / 代號 + id, or the id parenthesised).
    FALLBACK  only where the subject is empty or carries no code at all. A
              subject naming a DIFFERENT code is not a candidate. Pre-2006
              bulletins publish no subject at all -- a 2005 control window held
              731 rows, every one of them subject-less -- so the fallback is
              what reaches that era. Candidates are ordered by the issuing unit
              in the document number, 證櫃監字 first, because that is the unit
              that issued all four confirmed termination bulletins, then by
              date and document number, and capped.

    The fallback reads ONLY official TPEx body bytes fetched through the frozen
    chain. No TEJ text, no company-name inference, decides any match.

J6 · UNIQUE requires the FETCHED body -- not the index row -- to establish the
security and a termination/reorganization event. Two qualifying bodies with
different document numbers make the event AMBIGUOUS and both are reported;
bundling them is adjudication's call, not this stage's.

J-CORRECTION · THE STATIC ARCHIVE IS NOT ALL UTF-8 (D6.5 -> D6.5.1)

The first D6.5 pass scored every pre-2015 event NONE. The cause was mine, not
the archive's: older /storage/eb_data documents are served as **Big5**
(`charset=big5`, and the older ones end in `.htm`, not `.html`). Decoding them
as UTF-8 produced mojibake, so neither the security code nor any termination
marker could match, and a real fetched official body registered as no evidence
at all.

6008 is the proof. Its bulletin 證櫃監字第10100311763號 was found, its subject
reads 「…（股票代號：6008）…自102年1月8日起停止櫃檯買賣…暨自102年1月18日起終止櫃檯
買賣」, its body WAS fetched -- and the event still scored NONE. Same class of
defect as D6.2's refusal page and throttle page: reading the source wrongly and
calling the result absence. Decoding now honours the document's declared
charset and falls back utf-8 -> big5 -> cp950.

J8 · presence/absence of labelled holder-term information on UNIQUE bodies.
No value is parsed, nothing is canonicalized, nothing is classified
RECONSTRUCTIBLE.

    python research/b0_8_holder_terms/tpex_static_corpus_census_d6_5.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

CENSUS_D61 = os.path.join(HERE, "document_discovery_census_d6_1.json")
FREEZE = os.path.join(HERE, "tpex_static_router_freeze_d6_5.json")
OUT = os.path.join(HERE, "tpex_static_corpus_census_d6_5.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_5_tpex_raw")
STATE = os.path.join(RAW, "_progress.json")

TPEX = D64.TPEX
BULLETIN = D64.BULLETIN
ANN_DETAIL = D64.ANN_DETAIL
WINDOW_BACK_DAYS, WINDOW_FORWARD_DAYS = 30, 40
PAGING = {"paging-size": "500", "paging-offset": "0"}
BODY_FALLBACK_CAP = 150
UNIT_PRIORITY = ("監", "審", "交", "視", "新", "債", "輔", "資")
CATEGORY_PROBE_ORDER = ("4", "1", "2", "15", "6", "8", "5", "17", "16", "9",
                        "10", "11", "12", "13", "14", "3", "7", "18", "19",
                        "20", "21", "22")
POLITE = 0.3

STATIC_UNIQUE = "STATIC_EVENT_DOCUMENT_UNIQUE"
STATIC_NONE = "STATIC_EVENT_DOCUMENT_NONE"
STATIC_AMBIGUOUS = "STATIC_EVENT_DOCUMENT_AMBIGUOUS"
STATIC_ERROR = "STATIC_EVENT_DOCUMENT_REQUEST_ERROR"
CLASSES = (STATIC_UNIQUE, STATIC_NONE, STATIC_AMBIGUOUS, STATIC_ERROR)

TERMINATION_MARKERS = ("終止", "停止櫃檯買賣", "停止買賣", "下櫃", "撤銷")
REORG_MARKERS = ("合併", "股份轉換", "股份交換", "概括讓與", "概括承受",
                 "控股公司", "存續公司", "消滅公司")

# J8 · presence markers only. No value is read out of any of these.
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


class Archive:
    """The frozen chain, with month-level caching shared across events."""

    def __init__(self):
        self.months = {}
        self.detail = {}
        self.cate = {}
        self.errors = []

    def month_rows(self, y, m):
        key = "%d-%02d" % (y, m)
        if key in self.months:
            return self.months[key]
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
        params = dict(startDate="%d/%02d/01" % (y, m),
                      endDate="%d/%02d/%02d" % (y, m, last), **PAGING)
        path = os.path.join(RAW, "bulletin_%s.json" % key)
        raw = _disk(path)
        if raw is None:
            raw, err = D64._req(BULLETIN, params)
            if raw is None:
                self.errors.append({"month": key, "error": err})
                self.months[key] = {"error": err, "rows": [], "params": params}
                return self.months[key]
            _write(path, raw)
            time.sleep(POLITE)
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

    def ann_detail(self, row):
        num = row["document_number"]
        if num in self.detail:
            return self.detail[num]
        qs = urllib.parse.parse_qs(
            urllib.parse.urlparse(row["detail_href"] or "").query)
        cf = (qs.get("content_file") or [""])[0]
        docid = (qs.get("docId") or [""])[0]
        if not cf or not docid:
            self.detail[num] = None
            return None
        dpath = os.path.join(RAW, "annDetail_%s.json" % num)
        raw = _disk(dpath)
        cached = raw is not None
        if raw is None:
            raw, err = D64._req(ANN_DETAIL,
                                {"content_file": cf, "docId": docid})
            if raw is None:
                self.errors.append({"doc": num, "error": err})
                self.detail[num] = {"error": err}
                return self.detail[num]
        try:
            d = (json.loads(decode_official(raw)).get("data") or {})
        except Exception as exc:                            # noqa: BLE001
            self.detail[num] = {"error": "unparseable %s" % exc}
            return self.detail[num]
        if not cached:
            _write(dpath, raw)
            time.sleep(POLITE)
        text = V14._plain("%s %s %s" % (d.get("subject", ""),
                                        d.get("depend", ""),
                                        d.get("content", "")))
        self.detail[num] = {
            "document_number": d.get("number") or num,
            "publication_date": d.get("date"),
            "subject": d.get("subject"), "text": text,
            "static_path": d.get("downHtml"),
            "detail_raw_sha256": _sha(raw),
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
                params = dict(startDate="%d/%02d/01" % (y, m),
                              endDate="%d/%02d/%02d" % (y, m, last),
                              cate=c, **PAGING)
                raw, err = D64._req(BULLETIN, params)
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
                time.sleep(POLITE)
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
        spath = os.path.join(RAW, "static_%s.html" % det["document_number"])
        raw = _disk(spath)
        if raw is None:
            raw, err = D64._req(url, None)
            if raw is None:
                self.errors.append({"doc": det["document_number"],
                                    "error": err})
                return None, err
            _write(spath, raw)
            time.sleep(POLITE)
        return (raw, url), None


def field_presence(text: str) -> dict:
    return {k: any(x in text for x in v)
            for k, v in FIELD_PRESENCE_MARKERS.items()}


def main() -> int:
    d61 = json.load(open(CENSUS_D61, encoding="utf-8"))
    events = sorted([r for r in d61["results"]
                     if r["market_lineage"] == "TPEX"],
                    key=lambda r: (r["canonical_event_date"],
                                   r["security_id"]))
    assert len(events) == 59, len(events)

    router = {
        "record": "B0_8_D6_5_TPEX_STATIC_ARCHIVE_ROUTER",
        "frozen_before_corpus_requests": True,
        "supersedes_for_discovery_only": D64.__doc__ and
        "f6fccd7e82085b931e87188bc8e414d88ae522cdd95258671c909540649a83ca",
        "d6_4_router_preserved_historically": True,
        "j1_correction": {
            "withdrawn": "TPEx termination bulletins do not carry holder terms",
            "falsified_by": {
                "3299": "證櫃監字第10702101681號 -- stock conversion "
                        "consideration",
                "8913": "證櫃監字第10800136464號 -- cash consideration"},
            "recorded": "TPEX_TERMINATION_BULLETIN_HOLDER_TERM_COVERAGE = "
                        "UNKNOWN_CORPUS_WIDE",
            "holder_values_materialized_in_d6_5": False,
        },
        "j2_d6_4_defects": {
            "receiver_empty_returns_zero_rows":
                "CLIENT_REQUEST_CONFORMANCE_DEFECT",
            "cate_4_as_mandatory_discovery_filter": "UNDERINCLUSIVE",
            "evidence": "6514 -- bulletin exists in window, names the code, "
                        "states the canonical stop date, not filed under cate=4",
        },
        "surface": BULLETIN,
        "detail_surface": ANN_DETAIL,
        "static_root": TPEX + "/storage/eb_data/",
        "receiver_parameter": "never sent",
        "category_filter": "never sent -- all categories searched",
        "category_role": "diagnostic metadata only, recovered after matching",
        "date_format": "AD YYYY/MM/DD",
        "window_back_days": WINDOW_BACK_DAYS,
        "window_forward_days": WINDOW_FORWARD_DAYS,
        "identity_primary": "security code present in the official index subject",
        "official_body_decoding": ("declared charset first, then utf-8, big5, "
                                   "cp950 -- older eb_data documents are Big5 "
                                   "and .htm; decoding them as utf-8 made real "
                                   "bodies unmatchable and scored them NONE"),
        "identity_fallback": ("official body bytes, for rows whose subject is "
                              "empty or carries no code at all; ordered by "
                              "issuing unit 證櫃監字 first, then date and "
                              "document number; cap %d" % BODY_FALLBACK_CAP),
        "fallback_inputs_forbidden": ["TEJ narrative", "company-name inference",
                                      "counterparty name", "holder terms"],
        "unique_rule": ("the FETCHED body must establish the security and a "
                        "termination/reorganization event; two qualifying "
                        "bodies with different document numbers make the event "
                        "AMBIGUOUS"),
        "classes": list(CLASSES),
        "population": "all 59 TPEx-lineage register events, no sampling",
        "selection_blind_to": ["B0 holdings", "claim exposure", "8913", "3299",
                               "expected terms", "consideration type",
                               "replay usefulness", "performance"],
        "field_presence_markers": {k: list(v)
                                   for k, v in FIELD_PRESENCE_MARKERS.items()},
        "field_presence_is_metadata_only": True,
        "prohibited": ["value extraction", "canonicalization",
                       "RECONSTRUCTIBLE classification", "CA rebuild",
                       "state rebuild", "replay", "NAV", "performance",
                       "gates", "dual extraction"],
    }
    router["router_sha256"] = canonical_sha256(router)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(router, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("D6.5 router frozen:", router["router_sha256"], flush=True)

    arc = Archive()
    results, counts = [], Counter()
    for i, ev in enumerate(events, 1):
        sid = ev["security_id"]
        c = date.fromisoformat(ev["canonical_event_date"])
        lo, hi = c - timedelta(days=WINDOW_BACK_DAYS), c + timedelta(
            days=WINDOW_FORWARD_DAYS)
        rec = {"event_id": ev["event_id"], "security_id": sid,
               "canonical_event_date": c.isoformat(),
               "status_reason": ev["status_reason"],
               "window": [lo.isoformat(), hi.isoformat()],
               "months_queried": [], "rows_in_window": 0,
               "errors": [], "candidates": [], "qualifying": []}
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
            probe = pool[:BODY_FALLBACK_CAP]
            rec["identity_route"] = "BODY_FALLBACK"
            rec["fallback_pool"] = len(pool)
            rec["fallback_probed"] = len(probe)

        for r in probe:
            det = arc.ann_detail(r)
            if not det or det.get("error"):
                if det and det.get("error"):
                    rec["errors"].append({"doc": r["document_number"],
                                          "error": det["error"]})
                continue
            if not D64.code_in_text(det["text"], sid) and not primary:
                continue
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
                cand.update({"body_fetched": False, "fetch_error": err})
                rec["errors"].append({"doc": det["document_number"],
                                      "error": err})
                rec["candidates"].append(cand)
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
            rec["candidates"].append(cand)
            if keys and term:
                rec["qualifying"].append(cand)

        if month_err or (rec["errors"] and not rec["qualifying"]):
            cls = STATIC_ERROR if month_err else STATIC_NONE
        else:
            cls = (STATIC_NONE if not rec["qualifying"]
                   else STATIC_UNIQUE if len({q["document_number"]
                                              for q in rec["qualifying"]}) == 1
                   else STATIC_AMBIGUOUS)
        rec["classification"] = cls
        counts[cls] += 1
        results.append(rec)
        print("  [%2d/59] %-6s %s %-34s cands=%d qual=%d"
              % (i, sid, ev["canonical_event_date"], cls, len(rec["candidates"]),
                 len(rec["qualifying"])), flush=True)
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

    audit = {}
    for sid in ("3553", "6514", "3299", "8913"):
        row = [r for r in results if r["security_id"] == sid]
        if not row:
            audit[sid] = {"in_population": False}
            continue
        r = row[0]
        audit[sid] = {"classification": r["classification"],
                      "identity_route": r["identity_route"],
                      "candidates": len(r["candidates"]),
                      "qualifying": len(r["qualifying"]),
                      "document_numbers": [q["document_number"]
                                           for q in r["qualifying"]],
                      "d6_4_outcome": ("MISS" if sid in ("3553", "6514")
                                       else "CONTROL_HIT"),
                      "resolved_by_all_category_router": (
                          r["classification"] == STATIC_UNIQUE
                          if sid in ("3553", "6514") else None)}

    out = {
        "record": "B0_8_D6_5_TPEX_STATIC_ARCHIVE_CORPUS_CENSUS",
        "b0_8_state": "WIP, UNSEALED",
        "router_sha256": router["router_sha256"],
        "TPEX_TERMINATION_BULLETIN_HOLDER_TERM_COVERAGE": "UNKNOWN_CORPUS_WIDE",
        "j1_withdrawn_statement": "TPEx termination bulletins do not carry "
                                  "holder terms -- WITHDRAWN, falsified",
        "j2_d6_4_defects": router["j2_d6_4_defects"],
        "total": len(results),
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "body_fetches_succeeded": fetch_ok,
        "body_fetches_failed": fetch_fail,
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
        # J10
        "holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\ntotal 59 :", dict(counts))
    print("fetches  : ok %d / fail %d" % (fetch_ok, fetch_fail))
    print("presence :", dict(presence))
    print("audit    :", json.dumps(audit, ensure_ascii=False))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
