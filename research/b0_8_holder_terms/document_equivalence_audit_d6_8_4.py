# -*- coding: utf-8 -*-
"""B0.8 · D6.8.4 · U5/U6/U7 · IS BODY-HASH EQUALITY THE SAME AS DOCUMENT IDENTITY?

D6.8.3 collapsed two locators into one document when their normalized bodies were
identical. On 6157 that was right -- same content_file, same 發文字號, same
發文日期, one document indexed on two adjacent days. But "same bytes" is not a
definition of "same official document", and two genuinely distinct announcements
could in principle carry identical text. If that happens, hash-only dedup merges
two documents and an AMBIGUOUS event silently reads as UNIQUE.

So this stage audits the equivalence relation itself, mechanically, over every
group of bodies sharing a normalized substantive text, and asks what else the
members disagree about:

    source-native locator      expected to differ; that is what a group IS
    official document number   a disagreement means two documents
    publication date           a disagreement means two documents
    issuer / securities named  a disagreement means two documents
    subject                    reported, never decisive on its own

    DUPLICATE_INDEXING_OF_SAME_OFFICIAL_DOCUMENT
        vs
    DISTINCT_OFFICIAL_DOCUMENTS_WITH_IDENTICAL_BODY_TEXT

U6 · THE FROZEN RULE

Two locators collapse only when the bodies are identical AND their official
provenance does not conflict: document numbers equal or at most one present, and
publication dates equal or at most one present. Any conflict keeps them separate.
Body-hash equality alone is never sufficient.

U7 · BLAST RADIUS RATHER THAN A GRATUITOUS RERUN

The rule is then applied to the actual D6.8.3 candidate population and the
document multiplicity of every event is recomputed. If no event's multiplicity
moves, the zero blast radius is proved arithmetically and no rerun is owed.

    python research/b0_8_holder_terms/document_equivalence_audit_d6_8_4.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                 # noqa: E402

D683_JSON = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
OUT = os.path.join(HERE, "document_equivalence_audit_d6_8_4.json")

DOCNO = re.compile(r"發文字號[:：]\s*([^\s受附主說依公]{4,30})")
PUBDATE = re.compile(r"發文日期[:：]\s*(中華民國[^受附主說依公]{4,25}?日)")
SUBJECT = re.compile(r"主旨[:：]\s*([^依說公]{4,120})")
SAME, DISTINCT = ("DUPLICATE_INDEXING_OF_SAME_OFFICIAL_DOCUMENT",
                  "DISTINCT_OFFICIAL_DOCUMENTS_WITH_IDENTICAL_BODY_TEXT")


def provenance(row, text):
    """Official provenance of one body, from the index row and its own text."""
    num = row["document_number"]
    if not num:
        m = DOCNO.search(text)
        num = m.group(1) if m else ""
    m = PUBDATE.search(text)
    pub = m.group(1) if m else ""
    m = SUBJECT.search(text)
    subj = (row["subject"] or "").strip() or (m.group(1) if m else "")
    return {"official_document_number": num, "publication_date": pub,
            "subject": subj[:120]}


def conflict(members, field):
    vals = {m[field] for m in members if m[field]}
    return len(vals) > 1


def classify(members):
    if conflict(members, "official_document_number"):
        return DISTINCT
    if conflict(members, "publication_date"):
        return DISTINCT
    if conflict(members, "securities_named"):
        return DISTINCT
    return SAME


def main() -> int:
    d683 = json.load(open(D683_JSON, encoding="utf-8"))
    sids = [e["security_id"] for e in d683["results"]]
    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}

    # ---- corpus-wide grouping -------------------------------------------
    groups = defaultdict(list)
    readable = 0
    for i, (did, row) in enumerate(sorted(by_loc.items()), 1):
        text, _src = VR.body_text(row)
        if not text:
            continue
        readable += 1
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        groups[h].append(did)
        if i % 20000 == 0:
            print("   grouped %d/%d" % (i, len(by_loc)), flush=True)
    multi = {h: v for h, v in groups.items() if len(v) > 1}
    print("corpus bodies %d | distinct texts %d | shared-text groups %d"
          % (readable, len(groups), len(multi)), flush=True)

    detail, verdicts = [], Counter()
    for h, dids in sorted(multi.items()):
        members = []
        for did in dids:
            row = by_loc[did]
            text, _s = VR.body_text(row)
            p = provenance(row, text)
            p.update(doc_id=did, index_date=row["date"],
                     content_file=row["content_file"],
                     securities_named=",".join(
                         s for s in sids if VR.code_in_text_v2(text, s)))
            members.append(p)
        v = classify(members)
        verdicts[v] += 1
        detail.append({
            "body_sha256": h, "size": len(dids), "verdict": v,
            "locators_differ": len({m["doc_id"] for m in members}) > 1,
            "content_files_differ": len({m["content_file"]
                                         for m in members}) > 1,
            "document_numbers": sorted({m["official_document_number"]
                                        for m in members}),
            "publication_dates": sorted({m["publication_date"]
                                         for m in members}),
            "index_dates": sorted({m["index_date"] for m in members}),
            "securities_named": sorted({m["securities_named"]
                                        for m in members}),
            "subjects": sorted({m["subject"] for m in members})[:3],
        })

    # ---- U7 · the rule applied to the D6.8.3 candidate population -------
    changed, per_event = [], []
    for ev in d683["results"]:
        cands = ev["candidates"]
        linked = [c for c in cands if c["doc_id"] in ev["linked"]]
        hash_only = len({c["document_identity"] for c in linked})
        by_hash = defaultdict(list)
        for c in linked:
            by_hash[c["document_identity"]].append(c)
        strict = 0
        for h, grp in by_hash.items():
            members = []
            for c in grp:
                row = by_loc[c["doc_id"]]
                text, _s = VR.body_text(row)
                p = provenance(row, text)
                p["securities_named"] = ""
                members.append(p)
            strict += 1 if classify(members) == SAME else len(grp)
        per_event.append({"security_id": ev["security_id"],
                          "linked_locators": len(linked),
                          "documents_hash_only": hash_only,
                          "documents_under_frozen_rule": strict,
                          "classification": ev["classification"]})
        if strict != hash_only:
            changed.append(per_event[-1])

    out = {
        "record": "B0_8_D6_8_4_U5_DOCUMENT_EQUIVALENCE_AUDIT",
        "b0_8_state": "WIP, UNSEALED",
        "reader_changed": False, "linkage_changed": False,
        "network_requests": 0,

        "U6_frozen_document_equivalence_rule": {
            "body_hash_equality_alone_is_sufficient": False,
            "collapse_requires": [
                "identical normalized substantive body text",
                "official document numbers equal or at most one present",
                "publication dates equal or at most one present",
                "the set of securities named must not conflict"],
            "on_conflict": "the documents are retained separately",
        },

        "U5_collision_census": {
            "corpus_bodies_grouped": readable,
            "distinct_body_texts": len(groups),
            "groups_sharing_a_body_text": len(multi),
            "locators_inside_shared_groups": sum(len(v) for v in multi.values()),
            "verdicts": dict(verdicts),
            "DISTINCT_DOCUMENTS_WITH_IDENTICAL_TEXT_EXIST":
                verdicts.get(DISTINCT, 0) > 0,
            "groups": detail[:60],
            "groups_reported": min(60, len(detail)),
        },

        "U7_blast_radius": {
            "events_whose_document_multiplicity_changes": len(changed),
            "changed": changed,
            "per_event": per_event,
            "rerun_required": bool(changed),
            "zero_blast_radius_proved_arithmetically": not changed,
        },

        # invariants
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
        "gates_evaluated": False,
        "artefacts_rewritten": 0,
    }
    out["audit_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    u5, u7 = out["U5_collision_census"], out["U7_blast_radius"]
    print("\ndistinct body texts        :", u5["distinct_body_texts"])
    print("shared-text groups         :", u5["groups_sharing_a_body_text"])
    print("verdicts                   :", u5["verdicts"])
    print("distinct docs, same text?  :",
          u5["DISTINCT_DOCUMENTS_WITH_IDENTICAL_TEXT_EXIST"])
    print("events changing multiplicity:",
          u7["events_whose_document_multiplicity_changes"])
    print("zero blast radius proved   :",
          u7["zero_blast_radius_proved_arithmetically"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
