# -*- coding: utf-8 -*-
"""B0.8 · D6.8.3 · T9/T10/T11 · 59-EVENT RERUN WITH THE REPAIRED READER.

Everything that decides an outcome is D6.8.1 r3's, imported rather than
restated: Gate I's authoritative-identity requirement, Gate II's termination
predicate, L1/L2 linkage, the rename-lineage rules, the entity normalization,
the taxonomy, the archive start and the search end. The only difference is that
the reader can now see a security code written 六一五七 inside the same
authorised label, and a date written 九十二年十二月五日 inside the same
declaration.

T10 · A READABLE CODE IS NOT AN IDENTITY

Gate I still demands that the body carry an authoritative legal name from the
canonical lineage. A pre-2005 document that becomes readable, establishes a
termination and whose labelled boundary equals C still fails Gate I if no
authoritative entity identity is established, and the event lands in
LINKAGE_UNRESOLVED. Nothing here forces a NONE to become UNIQUE, and an existing
UNIQUE that acquires a second qualifying document becomes AMBIGUOUS.

T11 · THE ONE BODY NOBODY CAN READ

    2004-08-27  24866.htm   resolves, and is empty at source

Its index row carries no subject and no code, so nothing in the index can
exclude it from any event. Under T11 that is not a licence to assume
irrelevance: every event whose domain contains it is NOT exhausted, and the
count says so rather than rounding up.

    python research/b0_8_holder_terms/repaired_reader_rerun_d6_8_3.py
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
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                 # noqa: E402

R3_JSON = os.path.join(HERE, "entity_identity_conformance_repair_d6_8_1.json")
REG_JSON = os.path.join(HERE, "reader_conformance_regression_d6_8_3.json")
FREEZE = os.path.join(HERE, "vintage_reader_freeze_d6_8_3.json")
OUT = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")

ARCHIVE_INCEPTION = R3.ARCHIVE_INCEPTION
FWD = R3.WINDOW_FORWARD_DAYS
UNIQUE, AMBIGUOUS, NONE = R3.UNIQUE, R3.AMBIGUOUS, R3.NONE
LINKAGE, ERROR = R3.LINKAGE, R3.ERROR
ESTABLISHED, NOT_ESTABLISHED = R3.ESTABLISHED, R3.NOT_ESTABLISHED
CONFLICT = R3.CONFLICT
WORKERS, POLITE = 5, 0.25


def _ident(row):
    return locator_identity(row["content_file"], row["doc_id"])


def static_bytes(row):
    """The body r3 adjudicates on: the static official document."""
    p = os.path.join(STORE, "static_%s.html" % _ident(row))
    if os.path.exists(p):
        return open(p, "rb").read(), None
    num = row["document_number"]
    if num:
        raw = R3._cached("static_%s.html" % num)
        if raw is not None:
            return raw, None
    src = None
    q = os.path.join(STORE, "%s.json" % _ident(row))
    raw = open(q, "rb").read() if os.path.exists(q) else (
        R3._cached("annDetail_%s.json" % num) if num else None)
    if raw is not None:
        try:
            src = (json.loads(decode_official(raw)).get("data") or {}).get(
                "downHtml")
        except Exception:                                   # noqa: BLE001
            src = None
    if not src:
        return None, "no static path"
    body, err = D64._req(D64.TPEX + src, None)
    if body is None:
        return None, str(err)[:120]
    with open(p, "wb") as fh:
        fh.write(body)
    time.sleep(POLITE)
    return body, None


def main() -> int:
    reg = json.load(open(REG_JSON, encoding="utf-8"))
    assert reg["T7_arabic_regression"]["PASSED"], (
        "T7 conformance failed; the rerun is not authorised")
    freeze = json.load(open(FREEZE, encoding="utf-8"))
    r3 = json.load(open(R3_JSON, encoding="utf-8"))
    events = r3["results"]
    sids = [e["security_id"] for e in events]
    short = R3.tdcc_short_names()

    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}

    # ---- one pass with the repaired reader ------------------------------
    hits, unread = defaultdict(list), []
    scanned = 0
    for i, (did, row) in enumerate(sorted(by_loc.items()), 1):
        text, _src = VR.body_text(row)
        if not text:
            unread.append(did)
            continue
        scanned += 1
        for sid in sids:
            if VR.code_in_text_v2(text, sid):
                hits[sid].append(did)
        if i % 10000 == 0:
            print("   scanned %d/%d" % (i, len(by_loc)), flush=True)
    print("readable %d | unread %d | (sid,locator) hits %d"
          % (scanned, len(unread), sum(len(v) for v in hits.values())),
          flush=True)

    # ---- static bodies for candidates -----------------------------------
    need = sorted({d for v in hits.values() for d in v})
    static, st_err = {}, []
    lock, done = threading.Lock(), [0]

    def pull(did):
        raw, err = static_bytes(by_loc[did])
        with lock:
            done[0] += 1
            if raw is None:
                st_err.append({"doc_id": did, "error": err})
            else:
                static[did] = raw
            if done[0] % 250 == 0 or done[0] == len(need):
                print("   static %d/%d (errors %d)"
                      % (done[0], len(need), len(st_err)), flush=True)

    print("static bodies needed: %d" % len(need), flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(pull, need))
    if st_err:
        again = [e["doc_id"] for e in st_err]
        st_err = []
        for d in again:
            pull(d)

    results, counts, gate_counts = [], Counter(), Counter()
    for n, ev in enumerate(events, 1):
        sid = ev["security_id"]
        c = date.fromisoformat(ev["canonical_event_date"])
        hi = c + timedelta(days=FWD)
        rec = {"event_id": ev["event_id"], "security_id": sid,
               "canonical_event_date": c.isoformat(),
               "canonical_exit_reason": ev["canonical_exit_reason"],
               "d6_8_classification": ev["d6_8_classification"],
               "d6_8_1_classification": ev["classification"],
               "tdcc_short_name_diagnostic_only": short.get(sid),
               "candidates": [], "linked": [], "errors": []}

        in_domain = [d for d in hits.get(sid, [])
                     if by_loc[d]["date"]
                     and ARCHIVE_INCEPTION.isoformat() <= by_loc[d]["date"]
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
            found = VR.bind_names_v2(text, sid)
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
            found = VR.bind_names_v2(text, sid)
            keys = VR.code_in_text_v2(text, sid)
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
            roles = VR.extract_roles_v2(re.sub(r"\s+", " ", text))
            cand = {"doc_id": did, "locator_identity": _ident(row),
                    # r3 counted uniqueness over official DOCUMENT numbers.
                    # Keying candidates by locator silently changed that to
                    # index entries, and one document indexed on two adjacent
                    # dates then read as two documents. The authoritative
                    # document is its normalized official text.
                    "document_identity": hashlib.sha256(
                        text.encode("utf-8")).hexdigest(),
                    "official_document_number": row["document_number"],
                    "index_date": row["date"],
                    "vintage_code_key": any(k.startswith("CJK")
                                            for k in keys),
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
        rec["linked_document_identities"] = sorted(
            {x["document_identity"] for x in linked})
        rec["linked_document_numbers"] = [x["official_document_number"]
                                          for x in linked]
        rec["linkage_basis"] = basis
        rec["entity_corpus_size"] = len(entity_corpus)
        rec["reorg_compatible_in_entity_corpus"] = len(compat)

        # ---- T11 exhaustion ---------------------------------------------
        dom = {d for d, row in by_loc.items()
               if row["date"] and ARCHIVE_INCEPTION.isoformat()
               <= row["date"] <= hi.isoformat()}
        blockers = [d for d in unread if d in dom]
        rec["exhaustion"] = {
            "domain_locators": len(dom),
            "unread_locators_in_domain": [
                {"doc_id": d, "index_date": by_loc[d]["date"],
                 "index_subject_empty": not (by_loc[d]["subject"] or "").strip(),
                 "index_names_this_security": False,
                 "relevance_excludable_from_index_alone": False}
                for d in blockers],
            "candidates_adjudicated": len(rec["candidates"]),
            "candidates_expected": len(in_domain),
            "own_errors": len(rec["errors"]),
        }
        rec["domain_exhausted"] = (not blockers and not rec["errors"]
                                   and len(rec["candidates"]) == len(in_domain))

        if rec["errors"]:
            cls = ERROR
        elif linked:
            cls = (UNIQUE if len(rec["linked_document_identities"]) == 1
                   else AMBIGUOUS)
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
        print("  [%2d/59] %-5s %s %-40s cands=%-4d est=%-4d linked=%d %s"
              % (n, sid, c.isoformat(), cls[19:], len(rec["candidates"]),
                 sum(1 for x in rec["candidates"]
                     if x["gate_i"] == ESTABLISHED),
                 len(rec["linked"]), basis or "-"), flush=True)

    changed = []
    for r in results:
        if r["classification"] == r["d6_8_1_classification"]:
            continue
        vintage = [x for x in r["candidates"] if x["vintage_code_key"]]
        changed.append({
            "security_id": r["security_id"],
            "d6_8_1": r["d6_8_1_classification"],
            "d6_8_3": r["classification"],
            "canonical_entity": r["entity_identity"][
                "canonical_disappearing_entity"],
            "identity_established": r["entity_identity"][
                "identity_established"],
            "linked_document_numbers": r["linked_document_numbers"],
            "candidates_reached_only_by_the_vintage_reader": len(vintage),
            "vintage_candidates_passing_gate_i": sum(
                1 for x in vintage if x["gate_i"] == ESTABLISHED),
            "vintage_candidates_with_l1": sum(
                1 for x in vintage if x["l1_boundary_equals_C"]),
        })

    out = {
        "record": "B0_8_D6_8_3_REPAIRED_READER_RERUN",
        "b0_8_state": "WIP, UNSEALED",
        "vintage_reader_freeze_sha256": freeze["freeze_sha256"],
        "regression_sha256": reg["regression_sha256"],
        "supersedes": {
            "run": "r1",
            "artefact_preserved": "repaired_reader_rerun_d6_8_3_r1.json",
            "defect_in_r1": (
                "r1 decided UNIQUE vs AMBIGUOUS over distinct LOCATORS. D6.8.1 "
                "r3 decided it over distinct official DOCUMENT numbers; the "
                "locator key silently changed the granularity, so one document "
                "indexed on two adjacent dates read as two. Uniqueness is "
                "restored to the document level, keyed on the normalized "
                "official text. Measured blast radius: 1 event"),
            "affected_events": ["6157"]},
        "adjudication_imported_verbatim_from": {
            "module": "entity_identity_conformance_repair_d6_8_1",
            "freeze_sha256": r3["identity_rule_freeze_sha256"],
            "changed_here": ["security-code token representation",
                             "ROC-date token representation"],
            "semantics_changed": False,
        },
        "corpus": {
            "locators": len(by_loc), "readable": scanned,
            "unread": len(unread),
            "unread_detail": [
                {"doc_id": d, "index_date": by_loc[d]["date"],
                 "content_file": by_loc[d]["content_file"]} for d in unread],
            "static_errors": st_err,
        },
        "coverage_statement": {
            "OFFICIAL_LOCATORS_ENUMERATED": "%d / %d" % (len(by_loc),
                                                         len(by_loc)),
            "LOCATOR_ACQUISITION_RESOLVED": "%d / %d" % (len(by_loc),
                                                         len(by_loc)),
            "READABLE_AUTHORITATIVE_BODIES": "%d / %d" % (scanned,
                                                          len(by_loc)),
            "LOCATOR_COVERAGE_COMPLETE": True,
            "READABLE_BODY_COVERAGE_COMPLETE": scanned == len(by_loc),
            "ARCHIVE_COMPLETE": "NOT_ASSERTED",
        },
        "d6_8_1_r3_counts": r3["counts"],
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

        # T13 invariants
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
        "expected_counts_encoded": False,
        "unread_locator_repaired": False,
    }
    out["census_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nD6.8.1 r3 counts:", r3["counts"])
    print("D6.8.3    counts:", dict(counts))
    print("changed events  :", len(changed))
    for x in changed:
        print("   %s %s -> %s | identity=%s vintage_cands=%d gateI=%d L1=%d"
              % (x["security_id"], x["d6_8_1"][19:], x["d6_8_3"][19:],
                 x["identity_established"],
                 x["candidates_reached_only_by_the_vintage_reader"],
                 x["vintage_candidates_passing_gate_i"],
                 x["vintage_candidates_with_l1"]))
    print("exhausted: %d/59" % out["events_domain_exhausted"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
