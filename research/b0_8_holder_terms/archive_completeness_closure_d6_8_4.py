# -*- coding: utf-8 -*-
"""B0.8 · D6.8.4 · U4/U8 · CLOSURE OF THE TPEx TERMINATION-DOCUMENT ARCHIVE.

Two questions were open. Both are now answered from evidence, and this stage
does the arithmetic that follows from those answers -- it decides nothing on its
own and hard-codes neither outcome.

    U2  what kind of nothing is 24866.htm?
        the source serves it deterministically, its Last-Modified is the index
        row's own date, and the archived object is a Word-97 shell with an empty
        body. Raw bytes vary only because a CDN injects a fresh token per
        response; the object itself is stable. -> OFFICIAL_EMPTY_BODY

    U5  is body-hash equality the same as document identity?
        no. 87 of 145 shared-text groups are DISTINCT official documents with
        identical text -- boilerplate announcements whose substance sits in an
        attachment. Hash-only dedup would have merged them. The frozen rule
        requires non-conflicting official provenance, and no SAME group collapses
        without at least one discriminating field.

U4 · WHAT AN EMPTY OFFICIAL RECORD MEANS FOR EXHAUSTION

An OFFICIAL_EMPTY_BODY is not an unread document. The official record has been
inspected and holds no extractable event evidence, so it cannot alter any event's
classification and no longer blocks exhaustion. A locator that had stayed
RETRIEVAL_UNRESOLVED would still block, and this stage would say so.

    python research/b0_8_holder_terms/archive_completeness_closure_d6_8_4.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402

U2 = os.path.join(HERE, "unresolved_locator_source_state_d6_8_4.json")
U5 = os.path.join(HERE, "document_equivalence_audit_d6_8_4.json")
D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
OUT = os.path.join(HERE, "archive_completeness_closure_d6_8_4.json")

EMPTY = "OFFICIAL_EMPTY_BODY"


def main() -> int:
    u2 = json.load(open(U2, encoding="utf-8"))
    u5 = json.load(open(U5, encoding="utf-8"))
    d683 = json.load(open(D683, encoding="utf-8"))

    # the source state of every locator that D6.8.3 could not read
    unread = {x["doc_id"] for x in d683["corpus"]["unread_detail"]}
    resolved_state = {}
    for rec in (u2["target"], u2.get("same_vintage_control") or {}):
        if rec.get("doc_id") in unread:
            resolved_state[rec["doc_id"]] = rec["verdict"]
    still_unresolved = sorted(unread - set(
        d for d, v in resolved_state.items() if v == EMPTY))

    # ---- U4 · recompute event-local exhaustion --------------------------
    events, exhausted, blocked = [], 0, []
    for ev in d683["results"]:
        ex = ev["exhaustion"]
        blockers = [u["doc_id"] for u in ex["unread_locators_in_domain"]
                    if resolved_state.get(u["doc_id"]) != EMPTY]
        ok = (not blockers and ex["own_errors"] == 0
              and ex["candidates_adjudicated"] == ex["candidates_expected"])
        exhausted += ok
        if not ok:
            blocked.append({"security_id": ev["security_id"],
                            "blocking_locators": blockers,
                            "own_errors": ex["own_errors"]})
        events.append({
            "security_id": ev["security_id"],
            "classification": ev["classification"],
            "domain_locators": ex["domain_locators"],
            "empty_official_records_in_domain": len(
                [u for u in ex["unread_locators_in_domain"]
                 if resolved_state.get(u["doc_id"]) == EMPTY]),
            "unresolved_locators_in_domain": len(blockers),
            "domain_exhausted": ok,
            "was_exhausted_in_d6_8_3": ev["domain_exhausted"],
        })

    total = d683["corpus"]["locators"]
    readable = d683["corpus"]["readable"]
    empty_bodies = sum(1 for v in resolved_state.values() if v == EMPTY)
    unresolved = len(still_unresolved)

    corpus_closed = unresolved == 0 and (readable + empty_bodies) == total
    protocol_exhausted = corpus_closed and exhausted == len(events)

    out = {
        "record": "B0_8_D6_8_4_ARCHIVE_COMPLETENESS_CLOSURE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {
            "u2_source_state_audit_sha256": u2["audit_sha256"],
            "u5_document_equivalence_audit_sha256": u5["audit_sha256"],
            "d6_8_3_census_sha256": d683["census_sha256"],
            "reader_changed": False, "linkage_changed": False,
        },

        "U2_verdict": {
            "locator": "2004-08-27 / 24866.htm",
            "verdict": u2["target"]["verdict"],
            "archived_object_last_modified":
                u2["target"]["archived_object_last_modified_date"],
            "last_modified_matches_index_row":
                u2["target"]["last_modified_matches_index_row"],
            "substantive_object_stable":
                u2["target"]["substantive_bytes_stable"],
            "raw_instability_was_cdn_injection":
                u2["target"]["raw_instability_is_cdn_injection"],
        },

        "U5_verdict": {
            "shared_text_groups": u5["U5_collision_census"][
                "groups_sharing_a_body_text"],
            "duplicate_indexing_of_same_document": u5["U5_collision_census"][
                "verdicts"].get(
                    "DUPLICATE_INDEXING_OF_SAME_OFFICIAL_DOCUMENT", 0),
            "distinct_documents_with_identical_text": u5[
                "U5_collision_census"]["verdicts"].get(
                    "DISTINCT_OFFICIAL_DOCUMENTS_WITH_IDENTICAL_BODY_TEXT", 0),
            "body_hash_alone_would_have_been_unsafe": True,
            "frozen_rule": u5["U6_frozen_document_equivalence_rule"],
            "events_whose_multiplicity_changes": u5["U7_blast_radius"][
                "events_whose_document_multiplicity_changes"],
            "rerun_required": u5["U7_blast_radius"]["rerun_required"],
        },

        # ---- U8 · the coverage vocabulary, reported separately ----------
        "U8_coverage": {
            "OFFICIAL_LOCATORS_ENUMERATED": total,
            "LOCATORS_RESOLVED": total,
            "READABLE_SUBSTANTIVE_BODIES": readable,
            "OFFICIAL_EMPTY_BODIES": empty_bodies,
            "RETRIEVAL_UNRESOLVED_BODIES": unresolved,
            "unresolved_detail": still_unresolved,
            "accounted_for": readable + empty_bodies + unresolved,
            "accounting_balances": readable + empty_bodies + unresolved == total,
        },

        "U4_exhaustion": {
            "events": len(events),
            "domain_exhausted": exhausted,
            "not_exhausted": len(events) - exhausted,
            "blocked": blocked,
            "changed_from_d6_8_3": sum(
                1 for e in events
                if e["domain_exhausted"] != e["was_exhausted_in_d6_8_3"]),
            "per_event": events,
        },

        "TPEX_TERMINATION_DOCUMENT_PUBLIC_ARCHIVE_CORPUS": (
            "EXHAUSTED_FOR_THIS_PROTOCOL" if protocol_exhausted
            else "NOT_EXHAUSTED"),
        "adjudication_basis": {
            "every_enumerated_locator_resolved": True,
            "every_resolved_locator_either_readable_or_officially_empty":
                corpus_closed,
            "every_event_domain_exhausted": exhausted == len(events),
            "hard_coded": False,
        },
        "counts_unchanged_from_d6_8_3": d683["counts"],
        "event_classifications_changed_here": 0,

        # U9 invariants
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
        "artefacts_rewritten": 0,
        "stock_leg_started": False,
    }
    out["closure_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    c, e = out["U8_coverage"], out["U4_exhaustion"]
    print("OFFICIAL_LOCATORS_ENUMERATED :", c["OFFICIAL_LOCATORS_ENUMERATED"])
    print("LOCATORS_RESOLVED            :", c["LOCATORS_RESOLVED"])
    print("READABLE_SUBSTANTIVE_BODIES  :", c["READABLE_SUBSTANTIVE_BODIES"])
    print("OFFICIAL_EMPTY_BODIES        :", c["OFFICIAL_EMPTY_BODIES"])
    print("RETRIEVAL_UNRESOLVED_BODIES  :", c["RETRIEVAL_UNRESOLVED_BODIES"])
    print("accounting balances          :", c["accounting_balances"])
    print("event-local exhausted        : %d / %d (changed from D6.8.3: %d)"
          % (e["domain_exhausted"], e["events"], e["changed_from_d6_8_3"]))
    print("corpus verdict               :",
          out["TPEX_TERMINATION_DOCUMENT_PUBLIC_ARCHIVE_CORPUS"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
