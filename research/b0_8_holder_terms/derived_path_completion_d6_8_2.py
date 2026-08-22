# -*- coding: utf-8 -*-
"""B0.8 · D6.8.2 · S6d · SIX BODIES WHOSE POINTER WAS BROKEN, AND THE PROOF.

After the static-body pass, seven pre-2005 locators were still unread:

    6  the annDetail pointer is unusable -- five carry an empty downHtml, one
       carries a path with a raw space (0292 .htm) that is not a valid URL
    1  the body resolves but is empty at source

The six are not source absences. Every other pointer in this archive has the
form /storage/eb_data/<ROC yyyymm>/<content_file>, and both components are
already in the index row. Deriving the path is nevertheless an INFERENCE, not a
source-provided locator, so it is not taken on trust: each fetched body must
carry its own 發文日期 in Chinese numerals matching the index row's date, or it
is rejected and stays unread. A derived path that returns the wrong document
fails that test loudly instead of contaminating the corpus quietly.

Every accepted body is marked `derived_path: true` in the record, so a reader can
always separate what the archive handed over from what was reconstructed.

    python research/b0_8_holder_terms/derived_path_completion_d6_8_2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import (          # noqa: E402
    b64_peek, index_rows)
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402

OUT = os.path.join(HERE, "derived_path_completion_d6_8_2.json")
CJK = "〇一二三四五六七八九"


def cjk_num(n):
    """1..99 in the form official ROC documents use."""
    if n < 10:
        return CJK[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + CJK[n % 10]
    return CJK[n // 10] + "十" + (CJK[n % 10] if n % 10 else "")


def expected_date(iso):
    y, m, d = int(iso[:4]) - 1911, int(iso[5:7]), int(iso[8:10])
    return "中華民國%s年%s月%s日" % (cjk_num(y), cjk_num(m), cjk_num(d))


def main() -> int:
    rows, _ = index_rows()
    todo = []
    for r in rows:
        if r["document_number"]:
            continue
        ident = locator_identity(r["content_file"], r["doc_id"])
        p = os.path.join(STORE, "static_%s.html" % ident)
        if os.path.exists(p):
            continue
        todo.append((r, ident))
    print("unread pre-2005 locators:", len(todo), flush=True)

    accepted, rejected = [], []
    for r, ident in todo:
        cf = b64_peek(r["content_file"]) or ""
        # prefer the pointer the source actually gave, merely URL-encoded: a
        # filename containing a raw space is a transport defect on our side,
        # not a missing locator. Derive only when downHtml is empty.
        src = ""
        ptr = os.path.join(STORE, "%s.json" % ident)
        if os.path.exists(ptr):
            try:
                src = (json.loads(decode_official(
                    open(ptr, "rb").read())).get("data") or {}).get(
                        "downHtml") or ""
            except Exception:                               # noqa: BLE001
                src = ""
        roc = "%d%s" % (int(r["date"][:4]) - 1911, r["date"][5:7])
        path = src or "/storage/eb_data/%s/%s" % (roc, cf)
        derived = not src
        raw, err = D64._req(D64.TPEX + urllib.parse.quote(path), None)
        time.sleep(0.25)
        rec = {"doc_id": r["doc_id"], "locator_identity": ident,
               "content_file": r["content_file"], "content_file_decoded": cf,
               "index_date": r["date"], "path": path,
               "derived_path": derived,
               "path_source": "source downHtml, URL-encoded" if not derived
               else "derived from index row",
               "expected_document_date": expected_date(r["date"])}
        if raw is None:
            rec["accepted"] = False
            rec["reason"] = "fetch failed: %s" % str(err)[:120]
            rejected.append(rec)
            continue
        text = V14._plain(decode_official(raw))
        flat = "".join(text.split())
        rec["bytes"] = len(raw)
        rec["text_length"] = len(text)
        rec["document_date_matches_index_row"] = rec[
            "expected_document_date"] in flat
        if not rec["document_date_matches_index_row"]:
            rec["accepted"] = False
            rec["reason"] = ("the body's own 發文日期 does not match the index "
                             "row; the derived path is not proven to be this "
                             "document")
            rejected.append(rec)
            continue
        with open(os.path.join(STORE, "static_%s.html" % ident), "wb") as fh:
            fh.write(raw)
        rec["accepted"] = True
        rec["body_sha256"] = hashlib.sha256(raw).hexdigest()
        rec["excerpt"] = text[:120]
        accepted.append(rec)
        print("   accepted %s %s" % (r["date"], cf), flush=True)

    out = {
        "record": "B0_8_D6_8_2_S6D_DERIVED_PATH_COMPLETION",
        "b0_8_state": "WIP, UNSEALED",
        "why_the_pointer_failed": {
            "empty_downHtml": sum(1 for r in accepted + rejected
                                  if " " not in (r["content_file_decoded"])),
            "path_containing_a_raw_space": sum(
                1 for r in accepted + rejected
                if " " in r["content_file_decoded"]),
        },
        "path_derivation": {
            "template": "/storage/eb_data/<ROC yyyymm>/<content_file>",
            "components_come_from": "the index row itself",
            "is_an_inference": True,
            "acceptance_test": ("the fetched body must carry its own 發文日期 "
                                "in Chinese numerals equal to the index row "
                                "date, otherwise it is rejected"),
        },
        "attempted": len(todo),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "accepted_bodies": accepted,
        "rejected_bodies": rejected,
        "accepted_via_source_pointer_url_encoded": sum(
            1 for r in accepted if not r["derived_path"]),
        "accepted_via_derived_path": sum(1 for r in accepted
                                         if r["derived_path"]),

        # invariants
        "holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "predicates_changed": False,
        "cash_settlement_acquisition": False,
        "successor_side_acquisition": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "artefacts_rewritten": 0,
    }
    out["completion_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nattempted %d | accepted %d | rejected %d"
          % (len(todo), len(accepted), len(rejected)))
    for r in rejected:
        print("   rejected %s %s: %s" % (r["index_date"],
                                         r["content_file_decoded"],
                                         r["reason"][:80]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
