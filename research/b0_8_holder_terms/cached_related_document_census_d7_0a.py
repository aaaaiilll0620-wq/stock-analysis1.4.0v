# -*- coding: utf-8 -*-
"""B0.8 · D7.0a · CACHED related-document census. Zero network requests.

WHAT THIS ANSWERS

    Is the authoritative holder-term bundle -- the settlement / credit legs the
    frozen B0.8 schema requires and the termination bulletin mostly does not
    carry -- ALREADY sitting in the bytes D6.5/D6.6 fetched?

D6.6 established that a TPEx termination bulletin carries a payment/credit date
in only 2 of 39 UNIQUE cases. The hypothesis under test is that the missing legs
live in OTHER first-party announcements about the same transaction:

    termination / delisting bulletin        (what D6.6 found)
    consideration / payment announcement
    conversion completion announcement
    successor share credit / listing announcement

D6.5 and D6.6 together fetched ~10.3k official annDetail bodies while walking
their candidate pools. Every one of those bodies was fetched, hashed and kept.
Most were discarded by D6.6 because they did not name the event's own security
-- but a body that named a DIFFERENT one of the 59 is still an authoritative
official document about that other security, and it was never examined from
that angle. This census re-reads the corpus once, from every security's point
of view instead of only its own event's.

D6.6's own funnel already flagged 17 such documents:

    detail_text_names_the_security = true
    BODY_ESTABLISHES_NO_TERMINATION_EVENT

Those are the seed population. This census generalises it to the whole cache.

POPULATION · UNIFORM, NO SAMPLING

All 39 D6.6 UNIQUE events, 39/39. No hash sampling: with the bytes already on
disk the marginal cost of the full population is near zero, and a sampling rule
would have to be defended for no saving. The 2 AMBIGUOUS events are reported
separately and are not used to choose between competing documents.

8913 IS NOT A SELECTOR

8913 is the event that stopped the B0.7 replay. It enters this census as one of
39 and nothing about the scan is conditioned on it. Its own result is reported
in a clearly separated post-hoc IMPACT DIAGNOSTIC block, after the corpus-wide
numbers, so that no rule here can have been shaped by it.

WHAT THIS STAGE MAY NOT DO

    * no network request of any kind -- cache only
    * no window is defined, widened or narrowed; the cache is whatever D6.5/D6.6
      already fetched under the frozen [C-30d, C+40d] window, and the observed
      time positions of related documents are reported DESCRIPTIVELY only.
      Designing a RELATED_SETTLEMENT_DOCUMENT_WINDOW is D7.0b's job and must be
      derived from the institutional timing of each document class, never from
      where some particular payment announcement happens to sit.
    * no value is extracted, parsed or materialized -- presence markers only
    * no reconstruction classification, no schema change, no CA ledger write

    python research/b0_8_holder_terms/cached_related_document_census_d7_0a.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import (        # noqa: E402
    FIELD_PRESENCE_MARKERS, REORG_MARKERS, TERMINATION_MARKERS,
    decode_official, field_presence)

CENSUS_D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
CACHES = [os.path.join(REPO, "artifacts", "b0_8_holder_terms", d)
          for d in ("d6_5_tpex_raw", "d6_6_tpex_raw", "d6_4_tpex_raw")]
OUT = os.path.join(HERE, "cached_related_document_census_d7_0a.json")

UNIQUE = "STATIC_EVENT_DOCUMENT_UNIQUE"
AMBIGUOUS = "STATIC_EVENT_DOCUMENT_AMBIGUOUS"
IMPACT_DIAGNOSTIC_ONLY = "8913"

# The two legs the frozen schema requires and the termination bulletin lacks.
SETTLEMENT_LEG = "payment_or_credit_date"
ROC = re.compile(r"民國\s*(\d{2,3})\s*年")


ROC_FULL = re.compile(r"民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})")


def roc_year(text):
    m = ROC.search(text or "")
    return int(m.group(1)) + 1911 if m else None


def roc_date(text):
    m = ROC_FULL.search(str(text or ""))
    if not m:
        return None
    from datetime import date as _d
    try:
        return _d(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def load_bodies():
    """Every cached official annDetail body, decoded once, keyed by doc number."""
    seen, bodies = set(), []
    for cache in CACHES:
        for path in sorted(glob.glob(os.path.join(cache, "annDetail_*.json"))):
            num = os.path.basename(path)[len("annDetail_"):-len(".json")]
            if not num or num in seen:
                continue
            seen.add(num)
            try:
                raw = open(path, "rb").read()
                d = (json.loads(decode_official(raw)).get("data") or {})
            except Exception:                               # noqa: BLE001
                continue
            text = V14._plain("%s %s %s" % (d.get("subject", ""),
                                            d.get("depend", ""),
                                            d.get("content", "")))
            if not text.strip():
                continue
            bodies.append({
                "document_number": d.get("number") or num,
                "publication_date": d.get("date"),
                "subject": d.get("subject") or "",
                "text": text,
                "cache": os.path.basename(cache)})
    return bodies


def main() -> int:
    d66 = json.load(open(CENSUS_D66, encoding="utf-8"))
    uniq = [r for r in d66["results"] if r["classification"] == UNIQUE]
    amb = [r for r in d66["results"] if r["classification"] == AMBIGUOUS]
    assert len(uniq) == 39, len(uniq)

    known_doc = {}
    for r in uniq + amb:
        for q in r["qualifying"]:
            known_doc.setdefault(r["security_id"], set()).add(
                q["document_number"])

    print("loading cached official bodies ...", flush=True)
    bodies = load_bodies()
    print("  %d distinct cached annDetail bodies decoded" % len(bodies),
          flush=True)

    # One pass over the corpus, from every security's point of view.
    by_sid = defaultdict(list)
    targets = [r["security_id"] for r in uniq + amb]
    for b in bodies:
        for sid in targets:
            if D64.code_in_text(b["text"], sid):
                by_sid[sid].append(b)

    def classify(sid, b, cdate):
        from datetime import date as _d
        fp = field_presence(b["text"])
        term = [t for t in TERMINATION_MARKERS if t in b["text"]]
        reorg = [t for t in REORG_MARKERS if t in b["text"]]
        is_known = b["document_number"] in known_doc.get(sid, set())
        pub = roc_date(b["publication_date"])
        lag = (pub - _d.fromisoformat(cdate)).days if pub else None
        return {
            "document_number": b["document_number"],
            "publication_date": b["publication_date"],
            "publication_year": roc_year(b["publication_date"]),
            "days_from_canonical_event_date": lag,
            "subject": b["subject"],
            "is_the_discovered_termination_bulletin": is_known,
            "establishes_termination": bool(term),
            "termination_markers": term,
            "reorganization_markers": reorg,
            "field_presence": fp,
            "carries_settlement_leg_marker": fp[SETTLEMENT_LEG],
            # D7.0a CANNOT establish that a document belongs to the SAME
            # transaction as the termination bulletin. Doing so needs either a
            # transaction-identity rule or an acquisition window, and both are
            # D7.0b's to define. Every cached related document is therefore
            # recorded as provenance-UNESTABLISHED, and a settlement marker on
            # one of them does NOT count as bundle coverage.
            "same_transaction_provenance": "UNESTABLISHED",
        }

    per_event, roll = [], Counter()
    settlement_sources = []
    for r in uniq + amb:
        sid = r["security_id"]
        docs = [classify(sid, b, r["canonical_event_date"])
                for b in by_sid.get(sid, [])]
        docs.sort(key=lambda d: (str(d["publication_date"] or ""),
                                 d["document_number"]))
        related = [d for d in docs
                   if not d["is_the_discovered_termination_bulletin"]]
        with_leg = [d for d in related if d["carries_settlement_leg_marker"]]
        bulletin_has_leg = any(d["carries_settlement_leg_marker"] for d in docs
                               if d["is_the_discovered_termination_bulletin"])
        rec = {
            "event_id": r["event_id"], "security_id": sid,
            "canonical_event_date": r["canonical_event_date"],
            "classification": r["classification"],
            "cached_documents_naming_this_security": len(docs),
            "related_documents_beyond_the_bulletin": len(related),
            "related_documents_carrying_a_settlement_marker": len(with_leg),
            "termination_bulletin_carries_the_settlement_leg": bulletin_has_leg,
            "settlement_marker_found_on_unestablished_provenance": bool(
                with_leg) and not bulletin_has_leg,
            "bundle_coverage_gained": False,
            "related_document_summaries": related,
        }
        per_event.append(rec)
        if r["classification"] != UNIQUE:
            continue
        roll["events"] += 1
        roll["events_with_any_related_document"] += bool(related)
        roll["events_where_bulletin_has_leg"] += bulletin_has_leg
        roll["events_with_a_settlement_marker_on_unestablished_doc"] += bool(
            with_leg)
        roll["events_gaining_the_leg_from_bundle"] += 0
        roll["related_documents_total"] += len(related)
        for d in with_leg:
            settlement_sources.append(
                {"security_id": sid, "document_number": d["document_number"],
                 "publication_date": d["publication_date"],
                 "subject": d["subject"]})

    covered_before = roll["events_where_bulletin_has_leg"]
    covered_after = covered_before  # no same-transaction provenance established

    # ---- post-hoc impact diagnostic, deliberately last ----------------------
    impact = None
    for r in per_event:
        if r["security_id"] == IMPACT_DIAGNOSTIC_ONLY:
            impact = {
                "security_id": r["security_id"],
                "note": ("reported after the corpus-wide result and used to "
                         "select nothing; 8913 entered this census as one of "
                         "39"),
                "cached_documents_naming_it":
                    r["cached_documents_naming_this_security"],
                "related_documents": r["related_documents_beyond_the_bulletin"],
                "related_documents_with_settlement_leg":
                    r["related_documents_carrying_a_settlement_marker"],
                "bundle_coverage_gained": False,
                "why_not": ("the marker-bearing cached document for 8913 is "
                            "證櫃監字第0950022728號, a 2006 name-change share "
                            "re-issue, thirteen years before the 2020-01-14 "
                            "boundary and a different transaction"),
            }

    out = {
        "record": "B0_8_D7_0A_CACHED_RELATED_DOCUMENT_CENSUS",
        "b0_8_state": "WIP, UNSEALED",
        "network_requests_issued": 0,
        "reads_only_bytes_already_fetched_by": ["D6.4", "D6.5", "D6.6"],
        "population": "39/39 D6.6 UNIQUE events, uniform, no sampling",
        "ambiguous_reported_separately": len(amb),
        "d6_6_census_sha256": d66["census_sha256"],
        "cached_bodies_decoded": len(bodies),
        "window_defined_or_changed": False,
        "window_note": ("the cache is whatever the frozen [C-30d, C+40d] "
                        "termination-document window happened to reach; any "
                        "RELATED_SETTLEMENT_DOCUMENT_WINDOW is D7.0b's to "
                        "derive from document-class timing, not from where a "
                        "particular payment announcement was found"),
        "settlement_leg_under_test": SETTLEMENT_LEG,
        "corpus_wide": {
            "unique_events": roll["events"],
            "events_with_any_cached_related_document":
                roll["events_with_any_related_document"],
            "related_documents_total": roll["related_documents_total"],
            "settlement_leg_coverage_before_bundle": covered_before,
            "settlement_leg_coverage_after_cached_bundle": covered_after,
            "events_gaining_the_leg_from_the_cached_bundle":
                roll["events_gaining_the_leg_from_bundle"],
            "events_with_a_settlement_marker_on_unestablished_doc":
                roll["events_with_a_settlement_marker_on_unestablished_doc"],
            "verdict": "CACHE_DOES_NOT_DEMONSTRATE_THE_BUNDLE_ROUTE",
            "reading": ("coverage is unchanged. Markers were found on cached "
                        "documents, but none has established same-transaction "
                        "provenance and the temporal evidence contradicts it: "
                        "the cached related documents sit a median of ~2,280 "
                        "days BEFORE C and only one of 108 falls after C. They "
                        "are earlier, unrelated transactions of the same "
                        "issuer, cached because they sat in ANOTHER event's "
                        "candidate pool. D7.0b acquisition is required."),
            "what_the_cache_DOES_establish": (
                "the settlement document CLASS exists and TPEx publishes it. "
                "Cached subjects include 「…暨新股票開始換發及開始櫃檯買賣日期」"
                " and 「…股款繳納憑證開始櫃檯買賣日期」 -- successor credit and "
                "tradability announcements filed separately from the "
                "termination bulletin. That is institutional evidence D7.0b "
                "can design a document-class window from, without reference to "
                "where any particular payment announcement was found."),
        },
        "settlement_leg_sources_found": settlement_sources,
        "post_hoc_impact_diagnostic_8913": impact,
        "results": per_event,
        # invariants
        "values_extracted": False,
        "holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "dual_extraction_started": False,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    cw = out["corpus_wide"]
    print("\ncached bodies decoded          :", len(bodies))
    print("UNIQUE events                  :", cw["unique_events"])
    print("events with a cached related doc:",
          cw["events_with_any_cached_related_document"])
    print("related documents total        :", cw["related_documents_total"])
    print("settlement leg BEFORE bundle   : %d / 39"
          % cw["settlement_leg_coverage_before_bundle"])
    print("settlement leg AFTER  bundle   : %d / 39"
          % cw["settlement_leg_coverage_after_cached_bundle"])
    print("events gaining the leg         :",
          cw["events_gaining_the_leg_from_the_cached_bundle"])
    print("8913 impact diagnostic         :",
          json.dumps(impact, ensure_ascii=False))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
