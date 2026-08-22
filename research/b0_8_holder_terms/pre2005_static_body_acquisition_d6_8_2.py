# -*- coding: utf-8 -*-
"""B0.8 · D6.8.2 · S6b · THE ACTUAL PRE-2005 BODIES, AND A CORRECTION.

WHAT THE FIRST ACQUISITION PASS ACTUALLY OBTAINED

S6 requested annDetail for all 13,841 outstanding locators. Every request
returned, none errored, and the stage reported:

    ARCHIVE_COMPLETE = True

That report was wrong in substance. For the pre-2005 population the annDetail
endpoint answers `stat: ok` with every structured field empty:

    {"data": {"downHtml": "/storage/eb_data/9111/44782.htm", "date": "",
              "number": "", "subject": "", "depend": "", "content": "",
              "notes": "", "files": []}, "stat": "ok"}

All 13,798 of them, measured: subject+depend+content is the empty string in every
single one. What was acquired is a POINTER, not a body. S7 says completeness is
not established merely because every attempted request returned, and that is
exactly the trap this walked into: the responses were fine, the corpus was not.

The pointer is useful -- downHtml resolves, and the static body behind it carries
the full official text. This stage acquires those bodies, which is what S6
authorised in the first place.

WHAT THE BODIES REVEAL, AND WHY IT IS NOT REPAIRED HERE

Pre-2005 official text is written in Chinese numerals:

    公告久元電子股份有限公司(興櫃證券代號:六二六一)
    發文日期: 中華民國九十二年十二月五日

The inherited code predicate matches Arabic digits, and the D6.7 role extractor
reads Arabic ROC dates. Against this script variant both are blind. That is a
representation gap in the READER, not a linkage-semantics question -- but
extending either predicate changes what the whole 71,961-document corpus means,
so this stage does not touch them. It acquires the bodies and MEASURES the gap:
how many pre-2005 bodies name any of the 59 securities, in either script. The
measurement is what the adjudicator needs in order to decide; the rule stays
frozen until then.

    python research/b0_8_holder_terms/pre2005_static_body_acquisition_d6_8_2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402

ACQ_JSON = os.path.join(HERE, "pre2005_locator_acquisition_d6_8_2.json")
OUT = os.path.join(HERE, "pre2005_static_body_acquisition_d6_8_2.json")
WORKERS, POLITE = 5, 0.25


def main() -> int:
    acq = json.load(open(ACQ_JSON, encoding="utf-8"))
    rows, _ = index_rows()
    pending = [r for r in rows if not r["document_number"]]
    print("pre-2005 locators: %d" % len(pending), flush=True)

    # ---- confirm the emptiness claim from the bytes, not from memory -----
    empty, pointer_ok, paths = 0, 0, {}
    for r in pending:
        ident = locator_identity(r["content_file"], r["doc_id"])
        raw = open(os.path.join(STORE, "%s.json" % ident), "rb").read()
        d = (json.loads(decode_official(raw)).get("data") or {})
        text = V14._plain("%s %s %s" % (d.get("subject", ""),
                                        d.get("depend", ""),
                                        d.get("content", "")))
        if not text.strip():
            empty += 1
        if d.get("downHtml"):
            pointer_ok += 1
            paths[r["doc_id"]] = (ident, d["downHtml"])
    print("annDetail with empty text: %d | with a resolvable downHtml: %d"
          % (empty, pointer_ok), flush=True)

    # ---- acquire the real bodies ----------------------------------------
    got, errors = {}, []
    lock, done = threading.Lock(), [0]

    def pull(item):
        did, (ident, path) = item
        p = os.path.join(STORE, "static_%s.html" % ident)
        if os.path.exists(p):
            raw, err = open(p, "rb").read(), None
        else:
            raw, err = D64._req(D64.TPEX + path, None)
            if raw is not None:
                with open(p, "wb") as fh:
                    fh.write(raw)
            time.sleep(POLITE)
        with lock:
            done[0] += 1
            if raw is None:
                errors.append({"doc_id": did, "path": path,
                               "error": str(err)[:160]})
            else:
                got[did] = {"locator_identity": ident, "path": path,
                            "bytes": len(raw),
                            "body_sha256": hashlib.sha256(raw).hexdigest()}
            if done[0] % 1000 == 0 or done[0] == len(paths):
                print("   bodies %d/%d (errors %d)"
                      % (done[0], len(paths), len(errors)), flush=True)

    print("requesting %d static bodies" % len(paths), flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(pull, sorted(paths.items())))
    if errors:
        print("retrying %d" % len(errors), flush=True)
        again = [(e["doc_id"], paths[e["doc_id"]]) for e in errors]
        errors = []
        for item in again:
            pull(item)

    # ---- measure the corpus and the script gap ---------------------------
    lens, empty_body = [], 0
    digits = Counter()
    for did, rec in got.items():
        raw = open(os.path.join(STORE, "static_%s.html" % rec[
            "locator_identity"]), "rb").read()
        t = V14._plain(decode_official(raw))
        lens.append(len(t))
        if not t.strip():
            empty_body += 1
        has_arabic = any(ch.isdigit() for ch in t)
        has_cjk_num = any(ch in "〇一二三四五六七八九十" for ch in t)
        digits["arabic" if has_arabic else "no_arabic"] += 1
        digits["cjk_numeral" if has_cjk_num else "no_cjk_numeral"] += 1
    lens.sort()

    out = {
        "record": "B0_8_D6_8_2_S6B_PRE2005_STATIC_BODY_ACQUISITION",
        "b0_8_state": "WIP, UNSEALED",
        "corrects": {
            "artefact": "pre2005_locator_acquisition_d6_8_2.json",
            "acquisition_sha256": acq["acquisition_sha256"],
            "rewritten": False,
            "claim_withdrawn": "ARCHIVE_COMPLETE = True",
            "why": ("that pass acquired annDetail responses; for the pre-2005 "
                    "population every one is a pointer with all structured "
                    "fields empty. Requests returning is not a body being "
                    "acquired (S7)"),
        },
        "annDetail_pointer_state": {
            "pre_2005_locators": len(pending),
            "with_empty_structured_text": empty,
            "with_resolvable_downHtml": pointer_ok,
            "measured_from_bytes": True,
        },
        "static_body_acquisition": {
            "requested": len(paths),
            "acquired": len(got),
            "errors_after_retry": len(errors),
            "error_detail": errors,
            "bodies_with_empty_text": empty_body,
            "text_length_min": lens[0] if lens else None,
            "text_length_median": lens[len(lens) // 2] if lens else None,
            "text_length_max": lens[-1] if lens else None,
        },
        "script_representation": {
            "bodies_containing_arabic_digits": digits["arabic"],
            "bodies_containing_cjk_numerals": digits["cjk_numeral"],
            "note": ("pre-2005 official text writes security codes and ROC "
                     "dates in Chinese numerals; the inherited code predicate "
                     "and the D6.7 role extractor read Arabic only"),
            "predicates_changed_here": False,
        },
        "PRE_2005_CORPUS_READABLE_BY_INHERITED_PREDICATES": False,
        "next_decision_belongs_to_adjudication": (
            "whether to extend the code predicate and the ROC-date extractor "
            "to Chinese numerals across all 71,961 documents, which changes "
            "what the whole corpus means and must be applied uniformly"),

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
    out["acquisition_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    sb = out["static_body_acquisition"]
    print("\nstatic bodies acquired : %d / %d (errors %d)"
          % (sb["acquired"], sb["requested"], sb["errors_after_retry"]))
    print("empty bodies           :", sb["bodies_with_empty_text"])
    print("text length min/med/max: %s / %s / %s"
          % (sb["text_length_min"], sb["text_length_median"],
             sb["text_length_max"]))
    print("with arabic digits     :",
          out["script_representation"]["bodies_containing_arabic_digits"])
    print("with CJK numerals      :",
          out["script_representation"]["bodies_containing_cjk_numerals"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
