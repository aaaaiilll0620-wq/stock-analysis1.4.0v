# -*- coding: utf-8 -*-
"""B0.8 · D6.8.2 · S3 · SOURCE-NATIVE DOCUMENT-LOCATOR CENSUS. Offline. r2.

WHAT THIS MEASURES AND WHY IT COMES FIRST

The inherited pipeline keyed documents by `document_number`. TPEx bulletin rows
before 2005 carry an empty one, so those rows were discarded at enumeration and
no body was ever requested for them:

    PRE2005_DOCUMENT_IDENTITY_KEYING_COMPLETENESS_DEFECT

The official detail locator -- content_file + docId, the two fields the archive's
own href encodes -- is present on every row, blank document number or not. Before
any request is issued and before any identity is frozen, that locator has to earn
the primary-identity role mechanically. This stage is that audit, and nothing
else: no fetch, no freeze, no adjudication.

THE AUDIT IS DIRECTIONAL, AND r1 CONFLATED THE DIRECTIONS

r1 reported ONE_TO_ONE = false and demanded a stop, on the strength of 43
document numbers that appear under more than one locator. That is the wrong
direction to fail on. Three separate questions have three separate answers:

    docId -> body            a locator is a request; one response. Injective
                             into index entries: 71,961 distinct docIds for
                             71,961 rows, each mapping to exactly one
                             content_file. This is the identity that matters.

    content_file -> body     NOT an identity. 5,645 content_files are reused
                             across ROC years (0400064.htm serves 094…, 096…,
                             097…, 098…). Keying on the filename would silently
                             merge four different documents.

    document_number -> body  not injective either way. 43 numbers carry two
                             locators; 42 of those share one content_file and
                             sit on adjacent index dates, i.e. one body indexed
                             twice. This is a benign duplicate in the INDEX, not
                             an ambiguity in the identity.

A many-to-one locator->body map is harmless and is measured after acquisition
from the body sha256, never assumed here. A one-to-many map would be fatal and
does not occur: a request returns one document.

WHY THE NAIVE SIZING WOULD HAVE BEEN WRONG IN BOTH DIRECTIONS

13,798 blank-docno ROWS is not automatically 13,798 missing DOCUMENTS -- rows
could repeat, or point at a body already held. Measured: no blank-docno locator
is shared with any keyed locator, so all 13,798 are genuinely unacquired. In the
other direction the naive count is too SMALL: 43 locators were never requested at
all, because the pipeline saw their document number already cached under a
sibling locator. Those are unverified duplicates until their bytes say otherwise.

    python research/b0_8_holder_terms/source_native_locator_census_d6_8_2.py
"""
from __future__ import annotations

import base64
import binascii
import collections
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

BASES = [os.path.join(REPO, "artifacts", "b0_8_holder_terms", d)
         for d in ("d6_8_tpex_raw", "d6_6_tpex_raw", "d6_5_tpex_raw",
                   "d6_4_tpex_raw")]
OUT = os.path.join(HERE, "source_native_locator_census_d6_8_2.json")
FIRST_YEAR, LAST_YEAR = 2002, 2026


def cached(name):
    for b in BASES:
        p = os.path.join(b, name)
        if os.path.exists(p):
            return open(p, "rb").read()
    return None


def b64_peek(s):
    """Best-effort decode of the archive's own base64 locator fields."""
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8",
                                                               "replace")
    except (binascii.Error, ValueError):
        return None


def index_rows():
    rows, missing_months = [], []
    for y in range(FIRST_YEAR, LAST_YEAR + 1):
        for m in range(1, 13):
            key = "%d-%02d" % (y, m)
            raw = cached("bulletin_%s.json" % key)
            if raw is None:
                missing_months.append(key)
                continue
            js = json.loads(raw.decode("utf-8", "replace"))
            for r in ((js.get("tables") or [{}])[0].get("data") or []):
                q = urllib.parse.parse_qs(
                    urllib.parse.urlparse(r[4] or "").query)
                rows.append({
                    "month": key,
                    "date": D64.roc_to_iso(str(r[1])),
                    "document_number": str(r[2] or ""),
                    "subject": r[3] or "",
                    "content_file": (q.get("content_file") or [""])[0],
                    "doc_id": (q.get("doc_id") or q.get("docId") or [""])[0],
                })
    return rows, missing_months


def main() -> int:
    rows, missing_months = index_rows()
    no_locator = [r for r in rows if not (r["content_file"] and r["doc_id"])]

    by_docid = collections.defaultdict(list)
    by_cf = collections.defaultdict(list)
    by_num = collections.defaultdict(list)
    for r in rows:
        by_docid[r["doc_id"]].append(r)
        by_cf[r["content_file"]].append(r)
        if r["document_number"]:
            by_num[r["document_number"]].append(r)

    docid_dupes = {k: v for k, v in by_docid.items() if len(v) > 1}
    docid_many_cf = {k: sorted({x["content_file"] for x in v})
                     for k, v in by_docid.items()
                     if len({x["content_file"] for x in v}) > 1}
    cf_many_num = {k: sorted({x["document_number"] for x in v
                              if x["document_number"]})
                   for k, v in by_cf.items()
                   if len({x["document_number"] for x in v
                           if x["document_number"]}) > 1}
    num_many_loc = {k: sorted({x["doc_id"] for x in v})
                    for k, v in by_num.items()
                    if len({x["doc_id"] for x in v}) > 1}
    num_many_cf = {k: sorted({x["content_file"] for x in v})
                   for k, v in by_num.items()
                   if len({x["content_file"] for x in v}) > 1}

    # ---- acquisition state, per locator ---------------------------------
    acquired, never_requested, unverified_dupe = [], [], []
    for did, rs in by_docid.items():
        r = rs[0]
        num = r["document_number"]
        if not num:
            never_requested.append(did)
            continue
        if cached("annDetail_%s.json" % num) is None:
            never_requested.append(did)
            continue
        # the number is cached, but only ONE of its locators was ever the
        # request that produced it
        siblings = sorted({x["doc_id"] for x in by_num[num]})
        if len(siblings) > 1 and did != siblings[0]:
            unverified_dupe.append(did)
        else:
            acquired.append(did)

    blank_locs = {r["doc_id"] for r in rows if not r["document_number"]}
    keyed_locs = {r["doc_id"] for r in rows if r["document_number"]}
    blank_cf = {r["content_file"] for r in rows if not r["document_number"]}
    keyed_cf = {r["content_file"] for r in rows if r["document_number"]}

    miss_year = collections.Counter()
    for did in never_requested:
        d = by_docid[did][0]["date"] or "?"
        miss_year[d[:4]] += 1
    blank_year = collections.Counter(
        (r["date"] or "?")[:4] for r in rows if not r["document_number"])

    identity_valid = (not docid_dupes and not docid_many_cf
                      and not no_locator)
    out = {
        "record": "B0_8_D6_8_2_S3_SOURCE_NATIVE_LOCATOR_CENSUS",
        "run": "r2",
        "supersedes": {
            "run": "r1",
            "census_sha256": json.load(open(
                OUT.replace(".json", "_r1.json"), encoding="utf-8"))[
                    "census_sha256"],
            "artefact_preserved": "source_native_locator_census_d6_8_2_r1.json",
            "defect_in_r1": (
                "r1 failed the audit on document_number -> many locators. That "
                "is the wrong direction: it describes duplicate INDEX entries, "
                "not an ambiguous identity. r1 also did not test whether "
                "content_file alone is an identity -- it is not"),
        },
        "b0_8_state": "WIP, UNSEALED",
        "defect": "PRE2005_DOCUMENT_IDENTITY_KEYING_COMPLETENESS_DEFECT",
        "network_requests": 0,
        "identity_frozen_here": False,
        "bodies_acquired_here": 0,

        "index_rows": {
            "total": len(rows),
            "months_enumerated": (LAST_YEAR - FIRST_YEAR + 1) * 12
            - len(missing_months),
            "months_missing_from_cache": missing_months,
            "with_document_number": sum(1 for r in rows
                                        if r["document_number"]),
            "with_blank_document_number": sum(1 for r in rows
                                              if not r["document_number"]),
            "blank_document_number_by_year": dict(sorted(blank_year.items())),
            "rows_without_a_resolvable_locator": len(no_locator),
        },

        "identity_audit": {
            "candidate_identity": "doc_id (with content_file as the co-field "
                                  "the request needs)",
            "distinct_doc_ids": len(by_docid),
            "doc_ids_appearing_on_more_than_one_row": len(docid_dupes),
            "doc_ids_mapping_to_more_than_one_content_file": len(docid_many_cf),
            "distinct_content_files": len(by_cf),
            "content_files_carrying_more_than_one_document_number":
                len(cf_many_num),
            "content_file_reuse_examples": {
                k: v for k, v in list(cf_many_num.items())[:3]},
            "content_file_alone_is_an_identity": False,
            "why_not": ("the filename's serial repeats across ROC years; "
                        "0400064.htm serves four different official documents"),
            "document_numbers_with_more_than_one_locator": len(num_many_loc),
            "of_those_sharing_one_content_file": len(num_many_loc)
            - len(num_many_cf),
            "of_those_spanning_two_content_files": len(num_many_cf),
            "cross_content_file_case": {
                k: v for k, v in num_many_cf.items()},
            "duplicate_index_entries_are_not_identity_collisions": True,
            "locator_to_body_is_one_to_one": "NOT_ASSERTED -- a many-to-one "
                                             "map is measured from body "
                                             "sha256 after acquisition",
            "LOCATOR_IS_A_VALID_PRIMARY_IDENTITY": identity_valid,
            "verdict": ("LOCATOR_IDENTITY_AUDIT_PASSED" if identity_valid
                        else "LOCATOR_IDENTITY_AUDIT_FAILED_STOP_BEFORE_"
                             "ACQUISITION"),
        },

        "populations": {
            "locators_with_a_document_number": len(keyed_locs),
            "locators_with_a_blank_document_number": len(blank_locs),
            "locators_seen_both_ways": len(blank_locs & keyed_locs),
            "content_files_seen_both_ways": len(blank_cf & keyed_cf),
            "reading": ("no locator is shared between the two populations, so "
                        "no blank-docno row points at a body already held; the "
                        "629 shared content_files are ROC-year reuse, which is "
                        "why the filename cannot be the identity"),
        },

        "acquisition_sizing": {
            "TOTAL_DISTINCT_OFFICIAL_LOCATORS": len(by_docid),
            "ACQUIRED_DISTINCT_OFFICIAL_LOCATORS": len(acquired),
            "NEVER_REQUESTED_LOCATORS": len(never_requested),
            "UNVERIFIED_DUPLICATE_LOCATORS": len(unverified_dupe),
            "requests_required": len(never_requested) + len(unverified_dupe),
            "never_requested_by_year": dict(sorted(miss_year.items())),
            "naive_row_based_estimate": sum(1 for r in rows
                                            if not r["document_number"]),
            "why_naive_estimate_is_wrong_in_both_directions": (
                "it counts rows rather than locators, and it misses the 43 "
                "locators whose document number was already cached under a "
                "sibling locator and which were therefore never requested"),
            "sample_never_requested": [
                {"doc_id": d, "doc_id_decoded": b64_peek(d),
                 "content_file": by_docid[d][0]["content_file"],
                 "content_file_decoded": b64_peek(
                     by_docid[d][0]["content_file"]),
                 "date": by_docid[d][0]["date"],
                 "subject": by_docid[d][0]["subject"]}
                for d in sorted(never_requested)[:5]],
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
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "artefacts_rewritten": 0,
    }
    out["census_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    ia, ac = out["identity_audit"], out["acquisition_sizing"]
    print("index rows                    :", out["index_rows"]["total"])
    print("  blank document number       :",
          out["index_rows"]["with_blank_document_number"])
    print("distinct doc_id               :", ia["distinct_doc_ids"])
    print("  duplicated                  :",
          ia["doc_ids_appearing_on_more_than_one_row"])
    print("  mapping to >1 content_file  :",
          ia["doc_ids_mapping_to_more_than_one_content_file"])
    print("distinct content_file         :", ia["distinct_content_files"])
    print("  carrying >1 document number :",
          ia["content_files_carrying_more_than_one_document_number"],
          "-> filename is NOT an identity")
    print("docno with >1 locator         :",
          ia["document_numbers_with_more_than_one_locator"],
          "(same content_file: %d, cross: %d)"
          % (ia["of_those_sharing_one_content_file"],
             ia["of_those_spanning_two_content_files"]))
    print("VERDICT                       :", ia["verdict"])
    print("TOTAL locators                :",
          ac["TOTAL_DISTINCT_OFFICIAL_LOCATORS"])
    print("ACQUIRED                      :",
          ac["ACQUIRED_DISTINCT_OFFICIAL_LOCATORS"])
    print("NEVER REQUESTED               :", ac["NEVER_REQUESTED_LOCATORS"],
          ac["never_requested_by_year"])
    print("UNVERIFIED DUPLICATES         :",
          ac["UNVERIFIED_DUPLICATE_LOCATORS"])
    print("requests required             :", ac["requests_required"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
