# -*- coding: utf-8 -*-
"""B0.8 · D6.8.2 · S4/S6/S7 · SOURCE-NATIVE IDENTITY FREEZE AND ACQUISITION.

S4 · THE IDENTITY PRIMITIVE, FROZEN AFTER THE S3 AUDIT AND NOT BEFORE

    TPEX_BULLETIN_DOCUMENT_LOCATOR = {
        source        = "TPEX_BULLETIN"
        content_file  = the archive's own body-file field
        doc_id        = the archive's own index-entry field
    }
    locator_identity        = sha256(canonical_json(locator))
    official_document_number = OPTIONAL METADATA
    body_identity            = sha256(the raw official bytes)

The S3 audit is what earns this. doc_id is globally unique across all 71,961
index rows and functionally determines content_file, so the locator is one-to-one
with index entries. content_file alone is NOT an identity -- 5,645 filenames are
reused across ROC years -- and document_number is not one either, which is the
whole defect. No row number, no date and no ordinal is appended to force
uniqueness; none is needed.

The locator->body map is deliberately left as a measurement, not a claim. Two
locators may return one body (42 document numbers are indexed on two adjacent
dates). That is settled here by comparing body sha256 after the bytes exist,
never by assuming it beforehand.

S6 · WHAT IS ACQUIRED

    13,798  locators no stage has ever requested (blank document number)
        43  locators whose document number was already cached under a sibling
            locator, so the pipeline never requested them; unverified duplicates
    ------
    13,841  requests

No sampling. No filtering by security, exposure, envelope, consideration type or
usefulness. Nothing already held is re-fetched: the 58,120 acquired locators are
reused read-only.

WHAT IS NOT TOUCHED

Every D6.4..D6.8.1 artefact and every existing raw store is left exactly as it
is. New bytes land in their own store keyed by locator identity, so no old file
is overwritten and no old document identity is rewritten. The crosswalk from the
old document-number key to the new locator identity is emitted separately.

    python research/b0_8_holder_terms/pre2005_locator_acquisition_d6_8_2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import (          # noqa: E402
    cached, index_rows)
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402

S3_JSON = os.path.join(HERE, "source_native_locator_census_d6_8_2.json")
FREEZE = os.path.join(HERE, "locator_identity_freeze_d6_8_2.json")
OUT = os.path.join(HERE, "pre2005_locator_acquisition_d6_8_2.json")
XWALK = os.path.join(HERE, "locator_identity_crosswalk_d6_8_2.json")
STORE = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                     "d6_8_2_locator_raw")

WORKERS = 5
POLITE = 0.25


def locator_identity(content_file, doc_id):
    return canonical_sha256({"source": "TPEX_BULLETIN",
                             "content_file": content_file,
                             "doc_id": doc_id})


def main() -> int:
    s3 = json.load(open(S3_JSON, encoding="utf-8"))
    assert s3["identity_audit"]["verdict"] == "LOCATOR_IDENTITY_AUDIT_PASSED", \
        "S5: acquisition is not authorised while the identity audit fails"

    rows, missing_months = index_rows()
    # the only admissible gap is a contiguous tail of months later than every
    # month the archive actually served -- i.e. the future, not a hole
    latest_present = max(r["month"] for r in rows)
    assert all(k > latest_present for k in missing_months), (
        "month index cache has a hole, not a future tail: %s"
        % [k for k in missing_months if k <= latest_present])

    by_docid, by_num = {}, defaultdict(list)
    for r in rows:
        by_docid[r["doc_id"]] = r
        if r["document_number"]:
            by_num[r["document_number"]].append(r)

    # ---- S4 freeze -------------------------------------------------------
    freeze = {
        "record": "B0_8_D6_8_2_LOCATOR_IDENTITY_FREEZE",
        "frozen_after": {"stage": "S3", "census_sha256": s3["census_sha256"],
                         "verdict": s3["identity_audit"]["verdict"]},
        "primitive": {
            "source": "TPEX_BULLETIN",
            "fields": ["content_file", "doc_id"],
            "locator_identity": "sha256(canonical_json({source, content_file, "
                                "doc_id}))",
            "official_document_number": "OPTIONAL_METADATA",
            "body_identity": "sha256(raw official bytes)",
        },
        "audit_facts_relied_on": {
            "distinct_doc_ids": s3["identity_audit"]["distinct_doc_ids"],
            "doc_ids_duplicated": s3["identity_audit"][
                "doc_ids_appearing_on_more_than_one_row"],
            "doc_ids_mapping_to_many_content_files": s3["identity_audit"][
                "doc_ids_mapping_to_more_than_one_content_file"],
            "content_file_alone_is_an_identity": False,
        },
        "uniqueness_forced_by_appending": None,
        "locator_to_body_cardinality": "MEASURED_AFTER_ACQUISITION",
        "older_artefact_identities_rewritten": False,
        "crosswalk_emitted": os.path.relpath(XWALK, REPO),
    }
    freeze["freeze_sha256"] = canonical_sha256(freeze)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(freeze, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("locator identity frozen:", freeze["freeze_sha256"], flush=True)

    # ---- classify every locator -----------------------------------------
    todo, held = [], {}
    for did, r in by_docid.items():
        num = r["document_number"]
        raw = cached("annDetail_%s.json" % num) if num else None
        if raw is None:
            todo.append((did, "NEVER_REQUESTED"))
            continue
        sibs = sorted({x["doc_id"] for x in by_num[num]})
        if len(sibs) > 1 and did != sibs[0]:
            todo.append((did, "UNVERIFIED_DUPLICATE"))
        else:
            held[did] = {"document_number": num,
                         "body_sha256": hashlib.sha256(raw).hexdigest(),
                         "store": "inherited"}
    print("locators held %d | to request %d"
          % (len(held), len(todo)), flush=True)
    assert len(todo) == s3["acquisition_sizing"]["requests_required"]

    # ---- S6 acquisition --------------------------------------------------
    os.makedirs(STORE, exist_ok=True)
    got, errors = {}, []
    lock, done = threading.Lock(), [0]

    def pull(item):
        did, why = item
        r = by_docid[did]
        ident = locator_identity(r["content_file"], did)
        path = os.path.join(STORE, "%s.json" % ident)
        if os.path.exists(path):
            raw, err = open(path, "rb").read(), None
        else:
            raw, err = D64._req(D64.ANN_DETAIL,
                                {"content_file": r["content_file"],
                                 "docId": did})
            if raw is not None:
                with open(path, "wb") as fh:
                    fh.write(raw)
            time.sleep(POLITE)
        with lock:
            done[0] += 1
            if raw is None:
                errors.append({"doc_id": did, "reason": why,
                               "error": str(err)[:160]})
            else:
                rec = {"locator_identity": ident,
                       "content_file": r["content_file"], "doc_id": did,
                       "index_date": r["date"], "reason": why,
                       "body_sha256": hashlib.sha256(raw).hexdigest(),
                       "bytes": len(raw)}
                try:
                    d = (json.loads(decode_official(raw)).get("data") or {})
                    rec["official_document_number"] = d.get("number") or ""
                    rec["subject"] = d.get("subject") or ""
                    rec["parsed"] = True
                except Exception:                           # noqa: BLE001
                    rec["parsed"] = False
                got[did] = rec
            if done[0] % 1000 == 0 or done[0] == len(todo):
                print("   acquired %d/%d (errors %d)"
                      % (done[0], len(todo), len(errors)), flush=True)

    print("requesting %d official bodies" % len(todo), flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(pull, todo))

    # ---- retry once, sequentially, for transport errors ------------------
    retried = []
    if errors:
        print("retrying %d transport errors" % len(errors), flush=True)
        pending = [(e["doc_id"], e["reason"]) for e in errors]
        errors = []
        for item in pending:
            pull(item)
            retried.append(item[0])

    # ---- verify the 43 duplicates from bytes -----------------------------
    dupe_verified, dupe_differs = [], []
    for did, rec in got.items():
        if rec["reason"] != "UNVERIFIED_DUPLICATE":
            continue
        num = by_docid[did]["document_number"]
        sib = cached("annDetail_%s.json" % num)
        same = sib is not None and hashlib.sha256(
            sib).hexdigest() == rec["body_sha256"]
        (dupe_verified if same else dupe_differs).append({
            "doc_id": did, "document_number": num,
            "body_sha256": rec["body_sha256"],
            "sibling_body_sha256": hashlib.sha256(sib).hexdigest()
            if sib else None})

    # ---- locator -> body cardinality, measured ---------------------------
    bodies = defaultdict(list)
    for did, rec in held.items():
        bodies[rec["body_sha256"]].append(did)
    for did, rec in got.items():
        bodies[rec["body_sha256"]].append(did)
    shared = {k: v for k, v in bodies.items() if len(v) > 1}

    total = len(by_docid)
    acquired = len(held) + len(got)
    out = {
        "record": "B0_8_D6_8_2_PRE2005_LOCATOR_ACQUISITION",
        "b0_8_state": "WIP, UNSEALED",
        "defect_repaired": "PRE2005_DOCUMENT_IDENTITY_KEYING_COMPLETENESS_DEFECT",
        "locator_identity_freeze_sha256": freeze["freeze_sha256"],
        "s3_census_sha256": s3["census_sha256"],
        "store": os.path.relpath(STORE, REPO),

        "S7_acquisition_completeness": {
            "TOTAL_DISTINCT_OFFICIAL_LOCATORS": total,
            "ACQUIRED_DISTINCT_OFFICIAL_LOCATORS": acquired,
            "acquired_inherited_read_only": len(held),
            "acquired_by_this_stage": len(got),
            "UNRESOLVED_LOCATORS": total - acquired,
            "unresolved_detail": errors,
            "transport_errors_after_retry": len(errors),
            "locators_retried": len(retried),
            "ARCHIVE_COMPLETE": acquired == total,
            "completeness_is_measured_against":
                "the full S3 locator census, not against requests attempted",
        },

        "requested_population": {
            "never_requested": sum(1 for _, w in todo
                                   if w == "NEVER_REQUESTED"),
            "unverified_duplicates": sum(1 for _, w in todo
                                         if w == "UNVERIFIED_DUPLICATE"),
            "sampling_applied": False,
            "filtered_by_security_or_exposure": False,
        },

        "duplicate_verification": {
            "checked": len(dupe_verified) + len(dupe_differs),
            "byte_identical_to_sibling": len(dupe_verified),
            "differs_from_sibling": len(dupe_differs),
            "differing": dupe_differs,
            "reading": ("42 document numbers are indexed on two adjacent "
                        "dates; this settles from bytes whether the second "
                        "locator is the same document"),
        },

        "locator_to_body_cardinality": {
            "distinct_bodies": len(bodies),
            "bodies_reached_by_more_than_one_locator": len(shared),
            "extra_locators_over_bodies": total - len(bodies),
            "measured_not_assumed": True,
        },

        "parse_state": {
            "parsed": sum(1 for r in got.values() if r.get("parsed")),
            "unparseable": sum(1 for r in got.values()
                               if not r.get("parsed")),
        },
        "official_document_number_present_in_body": sum(
            1 for r in got.values() if r.get("official_document_number")),
        "blank_in_index_but_numbered_in_body": sum(
            1 for r in got.values()
            if r.get("official_document_number")
            and not by_docid[r["doc_id"]]["document_number"]),

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
        "older_document_identities_rewritten": False,
    }
    out["acquisition_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    xwalk = {"record": "B0_8_D6_8_2_LOCATOR_IDENTITY_CROSSWALK",
             "freeze_sha256": freeze["freeze_sha256"],
             "old_key": "official document number (D6.4..D6.8.1)",
             "new_key": "locator_identity",
             "deterministic_entries": {}, "acquired_here": {}}
    for did, rec in held.items():
        r = by_docid[did]
        xwalk["deterministic_entries"][rec["document_number"]] = {
            "locator_identity": locator_identity(r["content_file"], did),
            "content_file": r["content_file"], "doc_id": did,
            "body_sha256": rec["body_sha256"]}
    for did, rec in got.items():
        xwalk["acquired_here"][did] = {
            "locator_identity": rec["locator_identity"],
            "content_file": rec["content_file"],
            "index_date": rec["index_date"],
            "official_document_number": rec.get("official_document_number", ""),
            "body_sha256": rec["body_sha256"]}
    xwalk["crosswalk_sha256"] = canonical_sha256(
        {"n_old": len(xwalk["deterministic_entries"]),
         "n_new": len(xwalk["acquired_here"])})
    with open(XWALK, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(xwalk, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    s7 = out["S7_acquisition_completeness"]
    print("\nTOTAL locators      :", s7["TOTAL_DISTINCT_OFFICIAL_LOCATORS"])
    print("ACQUIRED            :", s7["ACQUIRED_DISTINCT_OFFICIAL_LOCATORS"])
    print("UNRESOLVED          :", s7["UNRESOLVED_LOCATORS"])
    print("ARCHIVE_COMPLETE    :", s7["ARCHIVE_COMPLETE"])
    print("duplicates verified :", out["duplicate_verification"])
    print("distinct bodies     :",
          out["locator_to_body_cardinality"]["distinct_bodies"])
    print("body-numbered rows blank in index:",
          out["blank_in_index_but_numbered_in_body"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
