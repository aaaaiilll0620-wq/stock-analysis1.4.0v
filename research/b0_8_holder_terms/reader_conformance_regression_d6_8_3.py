# -*- coding: utf-8 -*-
"""B0.8 · D6.8.3 · T7/T8 · ARABIC REGRESSION AND UNIFORM CORPUS APPLICATION.

T7 IS THE GATE THIS STAGE EXISTS FOR

A lexical repair earns its name only if it changes nothing for text that was
already readable. So the repaired reader and the inherited one are both run over
every readable authoritative body in the corpus, and two things must hold:

    on a body with no vintage representation at all,
        new code keys  == old code keys        exactly
        new date roles == old date roles       exactly
    on every body, without exception,
        old output is a SUBSET of new output   nothing previously read is lost

Either failing is a conformance failure for this stage, not a finding, and the
59-event rerun does not run.

T8 · UNIFORM APPLICATION

The repaired reader is applied to all 71,960 readable bodies -- not to pre-2005,
not to the three exposed securities, not to the current NONE events. The hit
counts below are reported by publication year so the reader's reach is visible
across the whole archive rather than asserted for one vintage.

    python research/b0_8_holder_terms/reader_conformance_regression_d6_8_3.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
import timing_anchor_sufficiency_d6_7 as D67               # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                 # noqa: E402

R3_JSON = os.path.join(HERE, "entity_identity_conformance_repair_d6_8_1.json")
FREEZE = os.path.join(HERE, "vintage_reader_freeze_d6_8_3.json")
OUT = os.path.join(HERE, "reader_conformance_regression_d6_8_3.json")


def roles_key(roles):
    return sorted((r["role"], r["date"], r["label"], r["char_distance"])
                  for r in roles)


def main() -> int:
    freeze = json.load(open(FREEZE, encoding="utf-8"))
    sids = [e["security_id"] for e in
            json.load(open(R3_JSON, encoding="utf-8"))["results"]]
    rows, _ = index_rows()

    readable = 0
    arabic_only = 0
    code_mismatch, role_mismatch, subset_violation = [], [], []
    cjk_code_bodies = Counter()
    cjk_date_bodies = Counter()
    cjk_code_hits = Counter()
    cjk_date_rewrites = 0
    arabic_code_bodies = Counter()

    for i, r in enumerate(rows, 1):
        text, _src = VR.body_text(r)
        if not text:
            continue
        readable += 1
        yr = (r["date"] or "?")[:4]
        flat = re.sub(r"\s+", " ", text)

        old_codes, new_codes, cjk_here = {}, {}, False
        for sid in sids:
            o = list(D64.code_in_text(text, sid))
            n = VR.code_in_text_v2(text, sid)
            if o:
                old_codes[sid] = o
                arabic_code_bodies[yr] += 0
            if n:
                new_codes[sid] = n
            if len(n) > len(o):
                cjk_here = True
                cjk_code_hits[sid] += 1
        if old_codes:
            arabic_code_bodies[yr] += 1
        if cjk_here:
            cjk_code_bodies[yr] += 1

        norm, nrw = VR.normalize_vintage_dates(flat)
        cjk_date_rewrites += nrw
        if nrw:
            cjk_date_bodies[yr] += 1

        old_roles = roles_key(D67.extract_roles(flat))
        new_roles = roles_key(D67.extract_roles(norm))

        # subset invariant, every body
        for sid, o in old_codes.items():
            if not set(o) <= set(new_codes.get(sid, [])):
                subset_violation.append({"doc_id": r["doc_id"], "sid": sid,
                                         "old": o,
                                         "new": new_codes.get(sid, [])})
        if not set(map(tuple, old_roles)) <= set(map(tuple, new_roles)):
            subset_violation.append({"doc_id": r["doc_id"], "kind": "roles",
                                     "lost": [x for x in old_roles
                                              if x not in new_roles][:4]})

        # T7 equality, vintage-free bodies only
        if not cjk_here and nrw == 0:
            arabic_only += 1
            if old_codes != {k: v for k, v in new_codes.items()}:
                code_mismatch.append({"doc_id": r["doc_id"],
                                      "old": old_codes, "new": new_codes})
            if old_roles != new_roles:
                role_mismatch.append({"doc_id": r["doc_id"],
                                      "old": old_roles[:4],
                                      "new": new_roles[:4]})
        if i % 10000 == 0:
            print("   %d/%d  arabic-only %d  mismatches %d"
                  % (i, len(rows), arabic_only,
                     len(code_mismatch) + len(role_mismatch)), flush=True)

    passed = not code_mismatch and not role_mismatch and not subset_violation
    out = {
        "record": "B0_8_D6_8_3_T7_T8_READER_CONFORMANCE_REGRESSION",
        "b0_8_state": "WIP, UNSEALED",
        "vintage_reader_freeze_sha256": freeze["freeze_sha256"],
        "network_requests": 0,

        "T7_arabic_regression": {
            "bodies_compared": readable,
            "bodies_with_no_vintage_representation": arabic_only,
            "code_output_mismatches": len(code_mismatch),
            "date_role_output_mismatches": len(role_mismatch),
            "old_output_not_a_subset_of_new": len(subset_violation),
            "examples": (code_mismatch[:3] + role_mismatch[:3]
                         + subset_violation[:3]),
            "BIT_EQUIVALENT_ON_ARABIC_ONLY_BODIES": not code_mismatch
            and not role_mismatch,
            "NOTHING_PREVIOUSLY_READ_WAS_LOST": not subset_violation,
            "PASSED": passed,
        },

        "T8_uniform_application": {
            "applied_to": "all readable authoritative bodies",
            "restricted_to_pre_2005": False,
            "restricted_to_exposed_securities": False,
            "bodies_gaining_a_cjk_code_key_by_year": dict(sorted(
                cjk_code_bodies.items())),
            "bodies_with_a_rewritten_cjk_date_by_year": dict(sorted(
                cjk_date_bodies.items())),
            "bodies_with_an_arabic_code_key_by_year": dict(sorted(
                arabic_code_bodies.items())),
            "total_bodies_gaining_a_cjk_code_key": sum(
                cjk_code_bodies.values()),
            "total_bodies_with_a_rewritten_cjk_date": sum(
                cjk_date_bodies.values()),
            "total_cjk_date_expressions_rewritten": cjk_date_rewrites,
            "cjk_code_hits_per_security": dict(cjk_code_hits.most_common()),
            "securities_gaining_at_least_one_cjk_code_hit": len(cjk_code_hits),
        },

        # invariants
        "holder_term_values_extracted": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "linkage_semantics_changed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "events_reclassified_here": 0,
        "artefacts_rewritten": 0,
    }
    out["regression_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    t7, t8 = out["T7_arabic_regression"], out["T8_uniform_application"]
    print("\nbodies compared              :", t7["bodies_compared"])
    print("vintage-free bodies          :",
          t7["bodies_with_no_vintage_representation"])
    print("code mismatches              :", t7["code_output_mismatches"])
    print("date-role mismatches         :", t7["date_role_output_mismatches"])
    print("subset violations            :", t7["old_output_not_a_subset_of_new"])
    print("T7 PASSED                    :", t7["PASSED"])
    print("bodies gaining a CJK code key:",
          t8["total_bodies_gaining_a_cjk_code_key"])
    print("bodies with a CJK date       :",
          t8["total_bodies_with_a_rewritten_cjk_date"],
          "| expressions", t8["total_cjk_date_expressions_rewritten"])
    print("securities gaining a CJK hit :",
          t8["securities_gaining_at_least_one_cjk_code_hit"], "/ 59")
    print("wrote", os.path.relpath(OUT, REPO))
    return 0 if t7["PASSED"] else 1


if __name__ == "__main__":
    sys.exit(main())
