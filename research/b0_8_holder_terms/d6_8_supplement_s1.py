# -*- coding: utf-8 -*-
"""B0.8 · D6.8 SUPPLEMENT S1. Two findings. No artefact rewritten, no rule changed.

WHY A SUPPLEMENT

D6.8's JSON is the record of what the frozen router produced. It is not edited
here. Two things were found while verifying that record against controls, and
both belong at adjudication level rather than inside the artefact.

FINDING 1 · ARCHIVE COMPLETENESS -- five bodies the run never read

D6.8 reported bodies_scanned 58,115 of 58,120 distinct documents, with 5 lost to
HTTP 429 during the prefetch sweep. Every per-event `domain_exhausted` is
therefore false, because that flag is global: one unread body anywhere denies
the archive-complete claim to all 59 events. This stage retries exactly those 5
documents -- the same fetch the same router already attempted -- and scans them
for the 59 codes. No rule, window, gate or classification is touched.

FINDING 2 · GATE I REJECTS THE RIGHT DOCUMENT FOR TWO EVENTS

Gate I requires the TDCC authoritative security name to appear verbatim in the
body. TDCC 1-1 carries the SHORT name (證券簡稱); TPEx bulletins use the full
legal name. For most securities the short name is a prefix of the legal name and
the test holds. It fails on two forms:

    contraction   TDCC 華僑商銀     TPEx 華僑商業銀行股份有限公司
    punctuation   TDCC 大峽谷－KY   TPEx 大峽谷半導體照明系統(開曼)股份有限公司
                                         / 大峽谷-KY   (ASCII hyphen)

In both cases the body naming the code IS the event's own termination bulletin
and its labelled boundary date IS the canonical C:

    5818  證櫃監字第0960203373號  自本（96）年11月23日起停止在證券商營業處所買賣
    5281  證櫃監字第11200099021號 自112年10月25日起停止櫃檯買賣

The 39/39 positive control did not catch this because it could only be run on
events that already had a known-good D6.6 body -- exactly the population where
the short name happens to be contained in the legal name. The control was
censored by the same selection that D6.8 was built to remove.

WHY THIS STAGE DOES NOT FIX IT

The Q7 amendment states: if event-level results have already been inspected
beyond engineering cost/progress diagnostics, STOP and report exposure before
changing the linkage rule. They have been. Relaxing gate I now -- after seeing
which events it rejected -- would be outcome-driven rule tuning, which is the
exact defect D6.8 was authorised to eliminate. The exposure is reported with its
blast radius measured, and the corrected identity rule is left to adjudication.

    python research/b0_8_holder_terms/d6_8_supplement_s1.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import listing_spell_complete_discovery_d6_8 as D68        # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

D68_JSON = os.path.join(HERE, "listing_spell_complete_discovery_d6_8.json")
OUT = os.path.join(HERE, "d6_8_supplement_s1.json")


def main() -> int:
    d8 = json.load(open(D68_JSON, encoding="utf-8"))
    sids = [r["security_id"] for r in d8["results"]]
    unread = sorted({e["doc"] for e in d8["archive_errors"]})

    # ---- finding 1 · retry exactly the unread documents --------------------
    arc = D68.Archive()
    rows = {}
    for key in ("2006-02", "2006-03", "2006-04"):
        y, m = int(key[:4]), int(key[5:])
        for r in (arc.month_rows(y, m).get("rows") or []):
            if r["document_number"] in unread:
                rows[r["document_number"]] = r
    arc.prefetch(list(rows.values()))          # the same fetch, retried
    retried = []
    for num in unread:
        row = rows.get(num)
        if row is None:
            retried.append({"document_number": num, "resolved": False,
                            "error": "index row not located"})
            continue
        det = arc.ann_detail(row)
        if det is None or det.get("error"):
            retried.append({"document_number": num, "resolved": False,
                            "error": (det or {}).get("error", "no route")})
            continue
        text = det["text"]
        naming = [s for s in sids if D64.code_in_text(text, s)]
        retried.append({
            "document_number": num,
            "index_date": row["date"],
            "resolved": True,
            "detail_raw_sha256": det["detail_raw_sha256"],
            "subject": det.get("subject") or "",
            "names_any_of_the_59_securities": bool(naming),
            "securities_named": naming,
            "subject_empty_in_index": not (row["subject"] or "").strip(),
        })
    resolved = [x for x in retried if x["resolved"]]
    naming_any = [x for x in resolved if x["names_any_of_the_59_securities"]]

    # ---- finding 2 · gate I blast radius, measured on the frozen record ----
    affected = []
    for r in d8["results"]:
        ghosts = [c for c in r["candidates"]
                  if not c.get("gate_i_entity_identity")
                  and c.get("gate_ii_event")
                  and c.get("l1_boundary_equals_C")]
        if not ghosts:
            continue
        affected.append({
            "security_id": r["security_id"],
            "canonical_event_date": r["canonical_event_date"],
            "tdcc_short_name": r["tdcc_authoritative_name"],
            "d6_8_classification": r["classification"],
            "classification_if_gate_i_were_form_tolerant":
                D68.UNIQUE if len(ghosts) == 1 else D68.AMBIGUOUS,
            "documents": [{
                "document_number": g["document_number"],
                "index_date": g["index_date"],
                "body_sha256": g["body_sha256"],
                "subject": g["subject"],
                "labelled_boundary_date_equal_to_C": [
                    x for x in g["labelled_boundary_dates"]
                    if x["date"] == r["canonical_event_date"]],
                "field_presence": g["field_presence"],
            } for g in ghosts],
        })

    out = {
        "record": "B0_8_D6_8_SUPPLEMENT_S1",
        "b0_8_state": "WIP, UNSEALED",
        "supplements": {
            "artefact": os.path.relpath(D68_JSON, REPO),
            "census_sha256": d8["census_sha256"],
            "router_sha256": d8["router_sha256"],
            "rewritten": False,
            "router_changed": False,
            "reclassified_events": 0,
        },

        # ---- finding 1 -----------------------------------------------------
        "finding_1_archive_completeness": {
            "distinct_documents_in_domain": d8["distinct_documents_in_domain"],
            "bodies_scanned_by_d6_8": d8["bodies_scanned"],
            "unread_by_d6_8": len(unread),
            "unread_cause": "HTTP 429 during the concurrent prefetch sweep",
            "retried_here": len(unread),
            "now_resolved": len(resolved),
            "still_unresolved": len(unread) - len(resolved),
            "resolved_documents_naming_any_of_the_59": len(naming_any),
            "documents": retried,
            "d6_8_domain_exhausted_flag_is_global": True,
            "why_all_59_read_false": (
                "domain_exhausted = not rec.errors and not arc.errors; the "
                "second term is archive-global, so five 429s anywhere denied "
                "the flag to every event, including events whose own candidate "
                "pool was fully read"),
        },

        # ---- finding 2 -----------------------------------------------------
        "finding_2_gate_i_name_form": {
            "defect": "GATE_I_AUTHORITATIVE_NAME_FORM_MISMATCH",
            "gate_i_test_as_frozen":
                "TDCC 證券簡稱 as an exact substring of the body",
            "why_it_fails": (
                "TDCC 1-1 carries the short name; TPEx bulletins carry the "
                "full legal name. Containment holds only when the short name "
                "is a prefix of the legal name -- not for contractions "
                "(華僑商銀 / 華僑商業銀行) and not across punctuation width "
                "(大峽谷－KY / 大峽谷-KY)"),
            "positive_control_was_censored": (
                "the 39/39 control could only run on events that already had a "
                "known-good D6.6 body, which is exactly the sub-population "
                "where containment holds; it had no power over the 20 events "
                "D6.8 was built for"),
            "blast_radius_events": len(affected),
            "blast_radius_documents": sum(len(a["documents"])
                                          for a in affected),
            "events_that_would_change_class": affected,
            "events_currently_UNIQUE_that_would_become_AMBIGUOUS": 0,
            "rule_changed_here": False,
            "why_not_corrected_here": (
                "Q7 amendment: results have been inspected, so exposure is "
                "reported and the identity/linkage rule is left to "
                "adjudication. Relaxing a gate after seeing which events it "
                "rejected is outcome-driven tuning"),
            "not_an_argument_for_code_only_identity": (
                "any correction must still establish entity identity from a "
                "first-party name; this is a comparison-form defect, not "
                "evidence that code matching alone is sufficient"),
        },

        # ---- controls that did hold ----------------------------------------
        "controls": {
            "d6_6_unique_documents_still_linked": "39/39",
            "prior_unique_documents_displaced": 0,
            "prior_unique_to_ambiguous": 2,
            "prior_unique_to_ambiguous_are_additive": True,
        },

        # invariants
        "artefacts_rewritten": 0,
        "holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "successor_side_acquisition": False,
        "cash_settlement_acquisition": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
    }
    out["supplement_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("unread retried      : %d | resolved %d | still unresolved %d"
          % (len(unread), len(resolved), len(unread) - len(resolved)))
    for x in retried:
        print("   %s %s names_any=%s %s"
              % (x["document_number"], x.get("index_date", ""),
                 x.get("names_any_of_the_59_securities"),
                 (x.get("subject") or x.get("error", ""))[:80]))
    print("gate I blast radius : %d events / %d documents"
          % (len(affected), sum(len(a["documents"]) for a in affected)))
    for a in affected:
        print("   %s %s  %s -> %s"
              % (a["security_id"], a["tdcc_short_name"],
                 a["d6_8_classification"],
                 a["classification_if_gate_i_were_form_tolerant"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
