# -*- coding: utf-8 -*-
"""B0.8 · D6.8.2 · S8/S9 · 59-EVENT RERUN OVER THE REPAIRED LOCATOR CORPUS.

WHAT CHANGES AND WHAT DOES NOT

Only document enumeration and acquisition were defective. This stage reruns all
59 events over the repaired corpus using the D6.8.1 r3 adjudication verbatim --
its corrected authoritative-identity Gate I, its Gate II termination predicate,
its L1/L2 linkage, its entity normalization and rename-lineage rules, its archive
start and search end. Nothing semantic is touched (S11). The functions are
imported from the r3 module rather than restated, so drift is impossible.

    corpus before   58,120 locators, keyed by official document number
    corpus after    71,961 locators, keyed by source-native locator identity

The 13,798 pre-2005 bodies that no stage had ever requested are now in the
corpus, so for the first time an event can be scored against the archive rather
than against the subset the old key happened to admit.

S9 · EXHAUSTION

An event is exhausted only if every archive row in its domain was enumerated,
every potentially relevant body inspected, and no unresolved inaccessible
document could still carry evidence material to it. An unread early body is NOT
assumed irrelevant because its index row carries no subject or no code -- those
rows are precisely the ones whose index metadata says nothing at all, which is
why they must be read rather than reasoned about.

    python research/b0_8_holder_terms/full_locator_corpus_rerun_d6_8_2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import (        # noqa: E402
    REORG_MARKERS, TERMINATION_MARKERS, decode_official, field_presence)
from timing_anchor_sufficiency_d6_7 import extract_roles   # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE as NEW_STORE, locator_identity)
# the r3 adjudication, imported verbatim (S11)
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402

S3_JSON = os.path.join(HERE, "source_native_locator_census_d6_8_2.json")
ACQ_JSON = os.path.join(HERE, "pre2005_locator_acquisition_d6_8_2.json")
R3_JSON = os.path.join(HERE, "entity_identity_conformance_repair_d6_8_1.json")
OUT = os.path.join(HERE, "full_locator_corpus_rerun_d6_8_2.json")

ARCHIVE_INCEPTION = R3.ARCHIVE_INCEPTION
WINDOW_FORWARD_DAYS = R3.WINDOW_FORWARD_DAYS
UNIQUE, AMBIGUOUS = R3.UNIQUE, R3.AMBIGUOUS
NONE, LINKAGE, ERROR = R3.NONE, R3.LINKAGE, R3.ERROR
ESTABLISHED, NOT_ESTABLISHED = R3.ESTABLISHED, R3.NOT_ESTABLISHED
CONFLICT = R3.CONFLICT
WORKERS, POLITE = 5, 0.25


def _ident(row):
    return locator_identity(row["content_file"], row["doc_id"])


def detail_bytes(row):
    """The official body for one locator, from whichever store holds it."""
    # the exact locator wins over the document-number cache: for the 43
    # sibling-indexed locators the inherited file holds the SIBLING's response,
    # which differs in index metadata (date, storage path) even when the
    # document is the same
    p = os.path.join(NEW_STORE, "%s.json" % _ident(row))
    if os.path.exists(p):
        return open(p, "rb").read(), "d6_8_2"
    num = row["document_number"]
    if num:
        raw = R3._cached("annDetail_%s.json" % num)
        if raw is not None:
            return raw, "inherited"
    return None, None


def parse_detail(raw):
    try:
        d = (json.loads(decode_official(raw)).get("data") or {})
    except Exception:                                       # noqa: BLE001
        return None
    return {"document_number": d.get("number") or "",
            "publication_date": d.get("date"),
            "subject": d.get("subject") or "",
            "text": V14._plain("%s %s %s" % (d.get("subject", ""),
                                             d.get("depend", ""),
                                             d.get("content", ""))),
            "static_path": d.get("downHtml")}


def main() -> int:
    s3 = json.load(open(S3_JSON, encoding="utf-8"))
    acq = json.load(open(ACQ_JSON, encoding="utf-8"))
    r3 = json.load(open(R3_JSON, encoding="utf-8"))
    s7 = acq["S7_acquisition_completeness"]
    assert s7["ARCHIVE_COMPLETE"], (
        "S7: the locator corpus is not complete; %d unresolved"
        % s7["UNRESOLVED_LOCATORS"])

    events = r3["results"]
    sids = [e["security_id"] for e in events]
    short = R3.tdcc_short_names()

    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}
    print("corpus: %d locators (%d inherited, %d acquired by D6.8.2)"
          % (len(by_loc), s7["acquired_inherited_read_only"],
             s7["acquired_by_this_stage"]), flush=True)

    # ---- one pass over every body in the repaired corpus ----------------
    hits, unreadable, scanned, detail = defaultdict(list), [], 0, {}
    for i, (did, row) in enumerate(sorted(by_loc.items()), 1):
        raw, store = detail_bytes(row)
        if raw is None:
            unreadable.append(did)
            continue
        det = parse_detail(raw)
        if det is None:
            unreadable.append(did)
            continue
        scanned += 1
        detail[did] = det
        for sid in sids:
            if D64.code_in_text(det["text"], sid):
                hits[sid].append(did)
        if i % 10000 == 0:
            print("   scanned %d/%d" % (i, len(by_loc)), flush=True)
    print("bodies readable %d | unreadable %d | (sid,locator) hits %d"
          % (scanned, len(unreadable), sum(len(v) for v in hits.values())),
          flush=True)

    # ---- static bodies for candidates only, as D6.8 did ------------------
    need = sorted({did for v in hits.values() for did in v})
    static, st_err = {}, []
    lock, done = threading.Lock(), [0]

    def static_of(did):
        row, det = by_loc[did], detail[did]
        num = row["document_number"]
        if num:
            raw = R3._cached("static_%s.html" % num)
            if raw is not None:
                return raw, None
        p = os.path.join(NEW_STORE, "static_%s.html" % _ident(row))
        if os.path.exists(p):
            return open(p, "rb").read(), None
        if not det["static_path"]:
            return None, "annDetail returned no downHtml"
        raw, err = D64._req(D64.TPEX + det["static_path"], None)
        if raw is None:
            return None, err
        os.makedirs(NEW_STORE, exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(raw)
        time.sleep(POLITE)
        return raw, None

    def pull(did):
        raw, err = static_of(did)
        with lock:
            done[0] += 1
            if raw is None:
                st_err.append({"doc_id": did, "error": str(err)[:160]})
            else:
                static[did] = raw
            if done[0] % 200 == 0 or done[0] == len(need):
                print("   static %d/%d (errors %d)"
                      % (done[0], len(need), len(st_err)), flush=True)

    print("static bodies needed: %d" % len(need), flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(pull, need))
    if st_err:
        print("retrying %d static errors" % len(st_err), flush=True)
        again = [e["doc_id"] for e in st_err]
        st_err = []
        for did in again:
            pull(did)

    # ---- per-event adjudication, r3 rules verbatim -----------------------
    results, counts, gate_counts = [], Counter(), Counter()
    for n, ev in enumerate(events, 1):
        sid = ev["security_id"]
        c = date.fromisoformat(ev["canonical_event_date"])
        hi = c + timedelta(days=WINDOW_FORWARD_DAYS)
        rec = {"event_id": ev["event_id"], "security_id": sid,
               "canonical_event_date": c.isoformat(),
               "canonical_exit_reason": ev["canonical_exit_reason"],
               "d6_6_classification": ev["d6_6_classification"],
               "d6_8_classification": ev["d6_8_classification"],
               "d6_8_1_classification": ev["classification"],
               "tdcc_short_name_diagnostic_only": short.get(sid),
               "candidates": [], "linked": [], "errors": []}

        in_domain = [did for did in hits.get(sid, [])
                     if by_loc[did]["date"]
                     and ARCHIVE_INCEPTION.isoformat() <= by_loc[did]["date"]
                     <= hi.isoformat()]

        bodies, bindings, edges, dated = {}, [], [], []
        for did in in_domain:
            raw = static.get(did)
            if raw is None:
                rec["errors"].append({"doc_id": did,
                                      "error": "static body unavailable"})
                continue
            text = R3._norm(V14._plain(decode_official(raw)))
            bodies[did] = (by_loc[did], text, raw)
            found = R3.bind_names(text, sid)
            bindings.extend(found)
            for f in found:
                dated.append((by_loc[did]["date"], f))
            edges.extend(R3.rename_edges(text))
        names = R3.collapse(bindings)
        comps = R3.components(names, edges)
        latest = None
        if dated:
            top = max(d for d, _ in dated)
            pool_n = R3.collapse([nm for d, nm in dated if d == top])
            latest = pool_n[0] if pool_n else None
        lineage = []
        for g in comps:
            if latest and latest in g:
                lineage = g
        if latest and not lineage:
            lineage = [latest]
        rec["entity_identity"] = {
            "distinct_legal_names_bound_to_this_code": names,
            "rename_edges": sorted({"%s -> %s" % e for e in edges}),
            "lineage_components": comps,
            "canonical_disappearing_entity": latest,
            "canonical_lineage": lineage,
            "identity_established": bool(lineage),
            "names_outside_canonical_lineage": [x for x in names
                                                if x not in lineage],
        }

        entity_corpus = []
        for did, (row, text, raw) in sorted(bodies.items()):
            found = R3.bind_names(text, sid)
            keys = D64.code_in_text(text, sid)
            carries = [x for x in lineage if x in text]
            outside = [f for f in found if f not in lineage]
            if not keys:
                gate_i = NOT_ESTABLISHED
            elif carries:
                gate_i = ESTABLISHED
            elif outside:
                gate_i = CONFLICT
            else:
                gate_i = NOT_ESTABLISHED
            term = [t for t in TERMINATION_MARKERS if t in text]
            reorg = [t for t in REORG_MARKERS if t in text]
            roles = extract_roles(re.sub(r"\s+", " ", text))
            cand = {"doc_id": did,
                    "locator_identity": _ident(row),
                    "content_file": row["content_file"],
                    "official_document_number": row["document_number"]
                    or detail[did]["document_number"],
                    "index_date": row["date"],
                    "subject": row["subject"] or detail[did]["subject"],
                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                    "matching_keys": keys,
                    "legal_names_bound": found,
                    "lineage_names_carried": carries,
                    "gate_i": gate_i,
                    "gate_ii_event": bool(term),
                    "termination_markers": term,
                    "reorganization_markers": reorg,
                    "l1_boundary_equals_C": any(
                        f["date"] == c.isoformat() for f in roles),
                    "labelled_boundary_dates": roles,
                    "field_presence": field_presence(text)}
            rec["candidates"].append(cand)
            gate_counts[gate_i] += 1
            if gate_i == ESTABLISHED and term:
                entity_corpus.append(cand)

        l1_hits = [x for x in entity_corpus if x["l1_boundary_equals_C"]]
        compat = [x for x in entity_corpus if x["reorganization_markers"]]
        if l1_hits:
            linked, basis = l1_hits, "L1"
        elif len(compat) == 1:
            linked, basis = compat, "L2"
        else:
            linked, basis = [], None
        rec["linked"] = [x["doc_id"] for x in linked]
        rec["linked_document_numbers"] = [x["official_document_number"]
                                          for x in linked]
        rec["linkage_basis"] = basis
        rec["entity_corpus_size"] = len(entity_corpus)
        rec["reorg_compatible_in_entity_corpus"] = len(compat)

        # ---- S9 exhaustion ----------------------------------------------
        dom = [did for did, row in by_loc.items()
               if row["date"] and ARCHIVE_INCEPTION.isoformat()
               <= row["date"] <= hi.isoformat()]
        dom_set = set(dom)
        unread = [x for x in unreadable if x in dom_set]
        rec["exhaustion"] = {
            "domain_locators": len(dom),
            "domain_locators_unread": len(unread),
            "candidates_adjudicated": len(rec["candidates"]),
            "candidates_expected": len(in_domain),
            "own_errors": len(rec["errors"]),
            "unread_body_assumed_irrelevant": False,
        }
        ex = rec["exhaustion"]
        rec["domain_exhausted"] = (not unread and not ex["own_errors"]
                                   and ex["candidates_adjudicated"]
                                   == ex["candidates_expected"])

        if rec["errors"]:
            cls = ERROR
        elif linked:
            cls = UNIQUE if len(set(rec["linked"])) == 1 else AMBIGUOUS
        elif entity_corpus or len(compat) > 1:
            cls = LINKAGE
        elif rec["candidates"] and any(x["gate_i"] == ESTABLISHED
                                       for x in rec["candidates"]):
            cls = LINKAGE
        else:
            cls = NONE
        rec["classification"] = cls
        counts[cls] += 1
        results.append(rec)
        print("  [%2d/59] %-5s %s %-42s cands=%-4d est=%-4d linked=%d %s exh=%s"
              % (n, sid, c.isoformat(), cls[19:], len(rec["candidates"]),
                 sum(1 for x in rec["candidates"]
                     if x["gate_i"] == ESTABLISHED),
                 len(rec["linked"]), basis or "-", rec["domain_exhausted"]),
              flush=True)

    changed = [{"security_id": r["security_id"],
                "d6_8_1": r["d6_8_1_classification"],
                "d6_8_2": r["classification"],
                "canonical_entity": r["entity_identity"][
                    "canonical_disappearing_entity"],
                "linked_document_numbers": r["linked_document_numbers"]}
               for r in results
               if r["classification"] != r["d6_8_1_classification"]]

    out = {
        "record": "B0_8_D6_8_2_FULL_LOCATOR_CORPUS_RERUN",
        "b0_8_state": "WIP, UNSEALED",
        "preserved_unchanged": {
            "d6_8_census_sha256": None,
            "d6_8_1_r3_census_sha256": r3["census_sha256"],
            "d6_8_1_r3_counts": r3["counts"],
            "artefacts_rewritten": 0,
        },
        "s3_census_sha256": s3["census_sha256"],
        "locator_identity_freeze_sha256": acq[
            "locator_identity_freeze_sha256"],
        "acquisition_sha256": acq["acquisition_sha256"],
        "adjudication_imported_verbatim_from": {
            "module": "entity_identity_conformance_repair_d6_8_1",
            "freeze_sha256": r3["identity_rule_freeze_sha256"],
            "semantics_changed": False,
            "changed_here": ["document enumeration key", "corpus membership"],
        },
        "corpus": {
            "locators": len(by_loc),
            "bodies_readable": scanned,
            "bodies_unreadable": len(unreadable),
            "static_bodies_fetched_or_reused": len(static),
            "static_errors": st_err,
        },
        "counts": dict(counts),
        "gate_i_candidate_outcomes": dict(gate_counts),
        "events_changed_vs_d6_8_1": changed,
        "events_changed_count": len(changed),
        "events_domain_exhausted": sum(1 for r in results
                                       if r["domain_exhausted"]),
        "events_not_exhausted": [r["security_id"] for r in results
                                 if not r["domain_exhausted"]],
        "identity_coverage": {
            "canonical_identity_established": sum(
                1 for r in results
                if r["entity_identity"]["identity_established"]),
            "required_rename_lineage": sum(
                1 for r in results
                if len(r["entity_identity"]["canonical_lineage"]) > 1),
            "unresolved_identity": [
                r["security_id"] for r in results
                if not r["entity_identity"]["identity_established"]],
        },
        "results": results,

        # S12 invariants
        "holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "cash_settlement_acquisition": False,
        "successor_side_acquisition": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "linkage_semantics_changed": False,
        "patched_only_the_three_none_events": False,
    }
    out["census_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nD6.8.1 r3 counts:", r3["counts"])
    print("D6.8.2    counts:", dict(counts))
    print("changed events  :", len(changed))
    for x in changed:
        print("   %s  %s -> %s" % (x["security_id"], x["d6_8_1"][19:],
                                   x["d6_8_2"][19:]))
    print("event-local exhausted: %d/59" % out["events_domain_exhausted"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
