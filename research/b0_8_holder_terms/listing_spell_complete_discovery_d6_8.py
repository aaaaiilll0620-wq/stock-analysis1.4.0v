# -*- coding: utf-8 -*-
"""B0.8 · D6.8 · TPEx archive-complete termination-document discovery, 59/59.

WHAT D6.8 REPLACES

D6.6 proved the discovery algorithm enumerated its candidate pool completely.
It could not prove the POOL was the right pool, because the pool was bounded by
a finite lookback of 30 days whose value nothing had justified. D6.7 then showed
the observed publication lags (-30..-3) cannot justify it either: that
population was selected BY the window, so its left tail is censored by
construction. D6.8 removes the parameter instead of retuning it.

    D6.6   [C - 30d, C + 40d]        an unjustified finite lookback
    D6.8   [archive inception, C+40d] the source's own complete domain

If an event still finishes NONE here, the claim is no longer "no document within
30 days" but "no document in the entire public TPEx bulletin archive".

THREE DECLARED DEVIATIONS FROM THE ORIGINAL Q3/Q4/Q7 TEXT

Each was forced by a specified input that does not exist in this corpus, and
each is strictly conservative -- widening the domain or tightening the gate,
never the reverse.

  1 · SEARCH_START is the archive inception, not the canonical listing spell.
      The B0 price-panel spell cannot express listing inception for this
      population: 13 of 59 securities never appear in the panel at all, and 37
      of the remaining 46 carry spell_start = 2013-01-02, which is the panel's
      own first observation date rather than a listing date. Taking Q4
      literally would classify almost every event as lineage-insufficient and
      make the stage vacuous. The archive inception is a SOURCE property, is a
      superset of any true spell, and is not derived from any miss.

  2 · The candidate corpus is EVERY distinct authoritative body in the domain.
      D6.6 routed primary-or-fallback: a subject naming the code suppressed the
      fallback pool entirely. Over 70 days that is an acceleration; over 24
      years it is a completeness defect, because 2002-2006 bulletins carry no
      subject at all while the same security may well have a later
      subject-bearing announcement. Routing on that would silently skip an
      event's own subject-less termination bulletin. primary / fallback are
      kept as retrieval PROVENANCE only and decide nothing.

  3 · Entity identity comes from the TDCC authoritative security master.
      Q7 names the TPEx delisted-company directory; the corpus has no such
      input -- E1 flags all 59 as `authoritative_name_input_unavailable` (its
      source is a TWSE endpoint that does not serve TPEx lineage), the event
      register's company_name is null for every one, and security_status.csv
      carries no name column. TDCC open dataset 1-1 證券基本資料 does cover all
      59, marks each 市場別 = 終止上市櫃, and its 證券名稱 appears verbatim in
      39 of 39 of the known-good D6.6 bodies -- a positive control with no
      false negatives, including 8913, whose entity was renamed twice.

THE FROZEN ADJUDICATION RULE (frozen before any D6.8 outcome was inspected)

    GATE I    AUTHORITATIVE_DISAPPEARING_ENTITY_IDENTITY_ESTABLISHED
              the body names the code code-first AND carries the TDCC
              authoritative security name for that code. A matching code alone
              is NOT sufficient over a 2002-2026 archive: code reuse cannot be
              excluded, and the listing-spell data that would have excluded it
              is unavailable.

    GATE II   BODY_ESTABLISHES_TERMINATION_OR_REORGANIZATION_EVENT
              unchanged from D6.6.

    GATE III  SAME_CANONICAL_EXIT_EVENT_LINKAGE, by either
              L1  a labelled boundary date in the body equals canonical C
              L2  within the corpus of the ESTABLISHED entity, this is the
                  unique document declaring a termination/reorganization event
                  compatible with the canonical exit reason

              L2 exists because C-equality cannot be the sole rule: the 18
              unresolved events have no independent C semantics. L2 does NOT
              bypass Gate II, and it requires reorganization compatibility --
              a capital-reduction re-issue that happens to be the only
              trading-stop notice under a code is not an exit document.

              Date proximity alone never establishes linkage.

DISCOVERY IS KEPT SEPARATE FROM LINKAGE. A document naming the same security is
a CANDIDATE. Only the three gates make it the event's document.

Parsed dates come from the corrected D6.7 parser and stay ADJUDICATION_ONLY;
none may become a holder-term reconstruction input.

    python research/b0_8_holder_terms/listing_spell_complete_discovery_d6_8.py
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
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import (        # noqa: E402
    REORG_MARKERS, TERMINATION_MARKERS, decode_official, field_presence)
from timing_anchor_sufficiency_d6_7 import extract_roles   # noqa: E402

CENSUS_D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
REGISTER = os.path.join(HERE, "event_register.json")
TDCC_MASTER = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                           "d7_0c_tdcc_raw", "OD-1-1.csv")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d6_8_tpex_raw")
OLD = [os.path.join(REPO, "artifacts", "b0_8_holder_terms", d)
       for d in ("d6_6_tpex_raw", "d6_5_tpex_raw", "d6_4_tpex_raw")]
FREEZE = os.path.join(HERE, "full_history_router_freeze_d6_8.json")
OUT = os.path.join(HERE, "listing_spell_complete_discovery_d6_8.json")
STATE = os.path.join(RAW, "_progress.json")

ARCHIVE_INCEPTION = date(2002, 1, 1)
WINDOW_FORWARD_DAYS = 40
PAGING = {"paging-size": "500", "paging-offset": "0"}
POLITE = 0.3
PREFETCH_WORKERS = 5
PREFETCH_POLITE = 0.25
CODE4 = re.compile(r"\d{4}")

UNIQUE = "FULL_HISTORY_EVENT_DOCUMENT_UNIQUE"
AMBIGUOUS = "FULL_HISTORY_EVENT_DOCUMENT_AMBIGUOUS"
NONE = "FULL_HISTORY_EVENT_DOCUMENT_NONE"
LINKAGE = "FULL_HISTORY_EVENT_LINKAGE_UNRESOLVED"
ERROR = "FULL_HISTORY_REQUEST_ERROR"
CLASSES = (UNIQUE, AMBIGUOUS, NONE, LINKAGE, ERROR)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _cached(name):
    for base in [RAW] + OLD:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return open(p, "rb").read(), os.path.basename(base)
    return None, None


def _write(name, raw):
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, name), "wb") as fh:
        fh.write(raw)


def detail_route(href):
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href or "").query)
    cf = (qs.get("content_file") or [""])[0]
    docid = (qs.get("docId") or [""])[0]
    return (cf, docid) if cf and docid else (None, None)


def tdcc_names():
    """First-party authoritative security master. Gate I's only input."""
    t = open(TDCC_MASTER, "rb").read()
    out, txt = {}, t.decode("utf-8-sig", "replace")
    for line in txt.splitlines()[1:]:
        c = [x.strip() for x in line.split(",")]
        if len(c) > 5 and c[0] and c[0] not in out:
            out[c[0]] = {"name": c[1], "market": c[2], "status": c[5]}
    return out, _sha(t)


class Archive:
    def __init__(self):
        self.months, self.detail, self.errors = {}, {}, []
        self.new = Counter()
        self.reused = Counter()
        self._lock = threading.Lock()

    def month_rows(self, y, m):
        key = "%d-%02d" % (y, m)
        if key in self.months:
            return self.months[key]
        name = "bulletin_%s.json" % key
        raw, src = _cached(name)
        if raw is None:
            last = (date(y + (m == 12), m % 12 + 1, 1) -
                    timedelta(days=1)).day
            raw, err = D64._req(D64.BULLETIN, dict(
                startDate="%d/%02d/01" % (y, m),
                endDate="%d/%02d/%02d" % (y, m, last), **PAGING))
            if raw is None:
                self.errors.append({"month": key, "error": err})
                self.months[key] = {"error": err, "rows": []}
                return self.months[key]
            _write(name, raw)
            self.new["bulletin"] += 1
            time.sleep(POLITE)
        else:
            self.reused[src] += 1
        rows = []
        try:
            js = json.loads(raw.decode("utf-8", "replace"))
            for r in ((js.get("tables") or [{}])[0].get("data") or []):
                rows.append({"date": D64.roc_to_iso(str(r[1])),
                             "document_number": str(r[2] or ""),
                             "subject": r[3] or "", "href": r[4]})
        except Exception as exc:                            # noqa: BLE001
            self.errors.append({"month": key, "error": "unparseable %s" % exc})
        self.months[key] = {"rows": rows, "raw_sha256": _sha(raw),
                            "row_count": len(rows)}
        return self.months[key]

    def prefetch(self, rows):
        need = {}
        for r in rows:
            num = r["document_number"]
            if not num or num in need or num in self.detail:
                continue
            if _cached("annDetail_%s.json" % num)[0] is not None:
                continue
            cf, docid = detail_route(r["href"])
            if cf:
                need[num] = (cf, docid)
        todo = sorted(need.items())
        if not todo:
            return 0
        done = [0]

        def pull(item):
            num, (cf, docid) = item
            raw, err = D64._req(D64.ANN_DETAIL,
                                {"content_file": cf, "docId": docid})
            with self._lock:
                done[0] += 1
                if raw is None:
                    self.errors.append({"doc": num, "error": err})
                else:
                    _write("annDetail_%s.json" % num, raw)
                    self.new["annDetail"] += 1
                if done[0] % 1000 == 0 or done[0] == len(todo):
                    print("      prefetch %d/%d" % (done[0], len(todo)),
                          flush=True)
            time.sleep(PREFETCH_POLITE)

        print("   prefetching %d annDetail bodies" % len(todo), flush=True)
        with ThreadPoolExecutor(max_workers=PREFETCH_WORKERS) as pool:
            list(pool.map(pull, todo))
        return len(todo)

    def ann_detail(self, row):
        num = row["document_number"]
        if num in self.detail:
            return self.detail[num]
        cf, docid = detail_route(row["href"])
        if not cf:
            self.detail[num] = None
            return None
        raw, _src = _cached("annDetail_%s.json" % num)
        if raw is None:
            self.detail[num] = {"error": "body never acquired"}
            self.errors.append({"doc": num, "error": "body never acquired"})
            return self.detail[num]
        try:
            d = (json.loads(decode_official(raw)).get("data") or {})
        except Exception as exc:                            # noqa: BLE001
            self.detail[num] = {"error": "unparseable %s" % exc}
            self.errors.append({"doc": num, "error": "unparseable"})
            return self.detail[num]
        self.detail[num] = {
            "document_number": d.get("number") or num,
            "publication_date": d.get("date"),
            "subject": d.get("subject") or "",
            "text": V14._plain("%s %s %s" % (d.get("subject", ""),
                                             d.get("depend", ""),
                                             d.get("content", ""))),
            "static_path": d.get("downHtml"),
            "detail_raw_sha256": _sha(raw)}
        return self.detail[num]

    def static_body(self, det):
        path = det.get("static_path")
        if not path:
            return None, "annDetail returned no downHtml"
        name = "static_%s.html" % det["document_number"]
        raw, _src = _cached(name)
        if raw is None:
            raw, err = D64._req(D64.TPEX + path, None)
            if raw is None:
                self.errors.append({"doc": det["document_number"],
                                    "error": err})
                return None, err
            _write(name, raw)
            self.new["static"] += 1
            time.sleep(POLITE)
        return raw, None


def main() -> int:
    d66 = json.load(open(CENSUS_D66, encoding="utf-8"))
    reg = json.load(open(REGISTER, encoding="utf-8"))
    reason = {e["security_id"]: e["status_reason"] for e in reg["events"]}
    master, master_sha = tdcc_names()
    events = sorted(d66["results"], key=lambda r: r["canonical_event_date"])
    assert len(events) == 59, len(events)

    router = {
        "record": "B0_8_D6_8_FULL_HISTORY_ROUTER",
        "frozen_before_any_d6_8_outcome_inspected": True,
        "supersedes_for_discovery_only": d66["router_sha256"],
        "d6_6_preserved_historically": True,
        "d6_6_counts_not_rewritten": d66["counts"],
        "search_domain": {
            "start": ARCHIVE_INCEPTION.isoformat(),
            "start_basis": "authoritative TPEx bulletin archive inception",
            "end": "C + %dd" % WINDOW_FORWARD_DAYS,
            "finite_backward_lookback_parameter": None,
            "window_tuning_performed": False,
        },
        "candidate_corpus": ("every distinct authoritative bulletin body in "
                             "the domain; primary/fallback retained as "
                             "retrieval provenance only"),
        "declared_deviations": [
            {"clause": "Q3/Q4 listing spell",
             "deviation": "SEARCH_START = archive inception",
             "reason": ("13/59 absent from the B0 price panel; 37/46 carry "
                        "spell_start = 2013-01-02, the panel's own first "
                        "observation date"),
             "direction": "strictly conservative superset"},
            {"clause": "Q5 primary/fallback routing",
             "deviation": "corpus = all distinct bodies in the domain",
             "reason": ("primary-or-fallback routing skips an event's own "
                        "subject-less 2002-2006 termination bulletin whenever "
                        "the security has any later subject-bearing notice"),
             "direction": "strictly conservative superset"},
            {"clause": "Q7 identity source",
             "deviation": "TDCC 證券基本資料 (OD-1-1) instead of a TPEx "
                          "delisted-company directory",
             "reason": ("E1 flags all 59 authoritative_name_input_unavailable; "
                        "event_register.company_name is null for all; "
                        "security_status.csv has no name column"),
             "positive_control": "39/39 known-good D6.6 bodies carry the TDCC "
                                 "name verbatim, including twice-renamed 8913",
             "direction": "adds a gate that did not previously exist"},
        ],
        "gates": {
            "I_entity_identity": ("code-first code match AND the TDCC "
                                  "authoritative security name present in the "
                                  "body; a matching code alone is insufficient "
                                  "because code reuse cannot be excluded"),
            "II_event": "termination/reorganization markers, unchanged",
            "III_linkage": {
                "L1": "a labelled boundary date in the body equals canonical C",
                "L2": ("within the established entity's corpus, the unique "
                       "document declaring a termination/reorganization event "
                       "compatible with the canonical exit reason"),
                "L2_does_not_bypass_gate_II": True,
                "date_proximity_alone": "never sufficient",
            },
        },
        "tdcc_master_sha256": master_sha,
        "d6_7_parser_reused_for": "event-linkage diagnostics only",
        "parsed_dates_provenance": "ADJUDICATION_ONLY",
        "population": "59/59, no sampling",
        "selection_blind_to": ["B0 exposure", "claim state",
                               "engineering envelope", "8913",
                               "replay usefulness", "reconstructibility",
                               "performance"],
    }
    router["router_sha256"] = canonical_sha256(router)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(router, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("D6.8 router frozen:", router["router_sha256"], flush=True)

    arc = Archive()
    # ---- one shared domain enumeration ------------------------------------
    hi_all = max(date.fromisoformat(r["canonical_event_date"]) for r in events)
    hi_all += timedelta(days=WINDOW_FORWARD_DAYS)
    all_rows, y, m = [], ARCHIVE_INCEPTION.year, ARCHIVE_INCEPTION.month
    while (y, m) <= (hi_all.year, hi_all.month):
        got = arc.month_rows(y, m)
        all_rows.extend(got.get("rows") or [])
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    by_num = {}
    for r in all_rows:
        if r["document_number"] and r["document_number"] not in by_num:
            by_num[r["document_number"]] = r
    print("domain: %d months, %d rows, %d distinct documents"
          % (len(arc.months), len(all_rows), len(by_num)), flush=True)

    arc.prefetch(list(by_num.values()))

    # ---- one pass: which documents name which of the 59 -------------------
    sids = [r["security_id"] for r in events]
    hits = defaultdict(list)
    scanned = unreadable = 0
    for i, (num, row) in enumerate(sorted(by_num.items()), 1):
        det = arc.ann_detail(row)
        if det is None:
            continue
        if det.get("error"):
            unreadable += 1
            continue
        scanned += 1
        text = det["text"]
        for sid in sids:
            if D64.code_in_text(text, sid):
                hits[sid].append(num)
        if i % 10000 == 0:
            print("   scanned %d/%d" % (i, len(by_num)), flush=True)
    print("bodies scanned %d | unreadable %d | (sid,doc) hits %d"
          % (scanned, unreadable, sum(len(v) for v in hits.values())),
          flush=True)

    # ---- adjudication, per event ------------------------------------------
    results, counts = [], Counter()
    for i, ev in enumerate(events, 1):
        sid = ev["security_id"]
        c = date.fromisoformat(ev["canonical_event_date"])
        hi = c + timedelta(days=WINDOW_FORWARD_DAYS)
        mst = master.get(sid) or {}
        ent = mst.get("name") or ""
        rec = {"event_id": ev["event_id"], "security_id": sid,
               "canonical_event_date": c.isoformat(),
               "canonical_exit_reason": reason.get(sid),
               "d6_6_classification": ev["classification"],
               "domain": [ARCHIVE_INCEPTION.isoformat(), hi.isoformat()],
               "tdcc_authoritative_name": ent,
               "tdcc_market": mst.get("market"),
               "candidates": [], "gate_i_passed": [], "linked": [],
               "errors": []}
        entity_corpus = []
        for num in hits.get(sid, []):
            row = by_num[num]
            if not (row["date"] and ARCHIVE_INCEPTION.isoformat()
                    <= row["date"] <= hi.isoformat()):
                continue
            det = arc.ann_detail(row)
            raw, err = arc.static_body(det)
            if raw is None:
                rec["errors"].append({"doc": num, "error": err})
                rec["candidates"].append({"document_number": num,
                                          "body_fetched": False,
                                          "fetch_error": err})
                continue
            text = V14._plain(decode_official(raw))
            keys = D64.code_in_text(text, sid)
            identity = bool(keys) and bool(ent) and ent in re.sub(r"\s+", "",
                                                                  text)
            term = [t for t in TERMINATION_MARKERS if t in text]
            reorg = [t for t in REORG_MARKERS if t in text]
            roles = extract_roles(re.sub(r"\s+", " ", text))
            l1 = any(f["date"] == c.isoformat() for f in roles)
            cand = {"document_number": num,
                    "publication_date": det.get("publication_date"),
                    "index_date": row["date"], "subject": det.get("subject"),
                    "body_fetched": True, "body_sha256": _sha(raw),
                    "gate_i_entity_identity": identity,
                    "matching_keys": keys,
                    "gate_ii_event": bool(term),
                    "termination_markers": term,
                    "reorganization_markers": reorg,
                    "l1_boundary_equals_C": l1,
                    "labelled_boundary_dates": roles,
                    "field_presence": field_presence(text)}
            rec["candidates"].append(cand)
            if identity:
                rec["gate_i_passed"].append(num)
                if term:
                    entity_corpus.append(cand)
        # Gate III
        l1_hits = [x for x in entity_corpus if x["l1_boundary_equals_C"]]
        compat = [x for x in entity_corpus if x["reorganization_markers"]]
        if l1_hits:
            linked, basis = l1_hits, "L1"
        elif len(compat) == 1:
            linked, basis = compat, "L2"
        else:
            linked, basis = [], None
        rec["linked"] = [x["document_number"] for x in linked]
        rec["linkage_basis"] = basis
        rec["entity_corpus_size"] = len(entity_corpus)
        rec["reorg_compatible_in_entity_corpus"] = len(compat)
        rec["domain_exhausted"] = not rec["errors"] and not arc.errors

        if rec["errors"]:
            cls = ERROR
        elif linked:
            cls = UNIQUE if len({x["document_number"] for x in linked}) == 1 \
                else AMBIGUOUS
        elif entity_corpus or len(compat) > 1:
            cls = LINKAGE
        elif rec["candidates"] and rec["gate_i_passed"]:
            cls = LINKAGE
        else:
            cls = NONE
        rec["classification"] = cls
        counts[cls] += 1
        results.append(rec)
        print("  [%2d/59] %-5s %s %-42s cands=%-3d gateI=%-3d linked=%d %s"
              % (i, sid, c.isoformat(), cls, len(rec["candidates"]),
                 len(rec["gate_i_passed"]), len(linked), basis or ""),
              flush=True)
        _write("_progress.json", json.dumps({"done": i}).encode())

    moves = Counter()
    for r in results:
        moves["%s -> %s" % (r["d6_6_classification"], r["classification"])] += 1
    prior_none = [r for r in results
                  if r["d6_6_classification"].endswith("NONE_WITHIN_"
                                                       "FROZEN_WINDOW")]
    prior_unique = [r for r in results
                    if r["d6_6_classification"].endswith("DOCUMENT_UNIQUE")]
    prior_amb = [r for r in results
                 if r["d6_6_classification"].endswith("AMBIGUOUS")]

    out = {
        "record": "B0_8_D6_8_FULL_HISTORY_DISCOVERY_CENSUS",
        "b0_8_state": "WIP, UNSEALED",
        "router_sha256": router["router_sha256"],
        "d6_6_preserved": {"census_sha256": d66["census_sha256"],
                           "counts": d66["counts"], "artefacts_rewritten": 0},
        "search_domain": router["search_domain"],
        "declared_deviations": router["declared_deviations"],
        "gates": router["gates"],
        "months_enumerated": len(arc.months),
        "bulletin_rows_enumerated": len(all_rows),
        "distinct_documents_in_domain": len(by_num),
        "bodies_scanned": scanned,
        "bodies_unreadable": unreadable,
        "sid_document_hits": sum(len(v) for v in hits.values()),
        "cache_reused": dict(arc.reused),
        "newly_fetched": dict(arc.new),
        "fetch_errors": len(arc.errors),
        "maximum_per_event_candidate_pool": max(
            (len(r["candidates"]) for r in results), default=0),
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "transitions": dict(moves),
        "prior_none_outcomes": dict(Counter(r["classification"]
                                            for r in prior_none)),
        "prior_unique_outcomes": dict(Counter(r["classification"]
                                              for r in prior_unique)),
        "prior_ambiguous_outcomes": dict(Counter(r["classification"]
                                                 for r in prior_amb)),
        "engineering_diagnostic_only": {
            s: next((r["classification"] for r in results
                     if r["security_id"] == s), None)
            for s in ("4947", "6247", "5281")},
        "archive_errors": arc.errors[:200],
        "results": results,
        # Q12
        "holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "cash_settlement_acquisition": False,
        "successor_side_acquisition": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "8913_cash_leg_adjudication_unchanged": True,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nD6.6 counts:", d66["counts"])
    print("D6.8 counts:", dict(counts))
    print("prior NONE  :", out["prior_none_outcomes"])
    print("prior UNIQUE:", out["prior_unique_outcomes"])
    print("prior AMBIG :", out["prior_ambiguous_outcomes"])
    print("newly fetched:", dict(arc.new), "| errors", len(arc.errors))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
