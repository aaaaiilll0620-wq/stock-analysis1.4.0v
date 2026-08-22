# -*- coding: utf-8 -*-
"""B0.8 · D6.8.2 · S6c · IS THE PRE-2005 CORPUS REACHABLE AT ALL? Measurement.

THE QUESTION THIS SETTLES, AND THE ONE IT REFUSES TO

Pre-2005 official text writes security codes and ROC dates in Chinese numerals.
The inherited predicates read Arabic. So a NONE verdict over that corpus could be
saying either of two completely different things:

    the archive has no document about this security      <- a finding
    the reader cannot see documents of this vintage      <- an artefact

Nothing in the census distinguishes them, so this stage measures the difference
directly, over all 13,798 newly acquired pre-2005 bodies, through four
independent probes per security:

    ARABIC_CODE_KEYED     the inherited predicate, unchanged
    CJK_CODE_KEYED        the same code-first construction, Chinese numerals
    CJK_CODE_BARE         the numeral sequence anywhere in the body
    LEGAL_NAME            the canonical entity name established by D6.8.1 r3,
                          which is script-independent and needs no numerals

The name probe is the decisive one. If a security's own legal name never appears
in 13,798 documents, no numeral repair can conjure a document about it. If it
does appear, the NONE verdicts over this vintage are a reader artefact and must
not stand.

NO PREDICATE IS CHANGED HERE

This writes a measurement, not a census. Gate I, Gate II, L1/L2, the termination
predicate and the taxonomy are untouched, and no event is reclassified. Whether
to extend the code predicate and the ROC-date extractor to Chinese numerals is a
decision about what the whole 71,961-document corpus means, and belongs to
adjudication rather than to the stage that happened to notice.

    python research/b0_8_holder_terms/pre2005_script_reachability_d6_8_2.py
"""
from __future__ import annotations

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
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402

R3_JSON = os.path.join(HERE, "entity_identity_conformance_repair_d6_8_1.json")
OUT = os.path.join(HERE, "pre2005_script_reachability_d6_8_2.json")

CJK_DIGIT = {"0": "[〇○零]", "1": "一", "2": "二", "3": "三", "4": "四",
             "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
KEY = r"(?:上櫃|上市|興櫃)?(?:股票代號|證券代號|公司代號|代號)[：:\s]*[（(]?\s*"


def cjk_code(sid):
    return "".join(CJK_DIGIT[c] for c in sid)


def main() -> int:
    r3 = json.load(open(R3_JSON, encoding="utf-8"))
    short = R3.tdcc_short_names()
    events = r3["results"]

    probes = {}
    for e in events:
        sid = e["security_id"]
        probes[sid] = {
            "canonical_entity": e["entity_identity"][
                "canonical_disappearing_entity"],
            "lineage": e["entity_identity"]["canonical_lineage"],
            "tdcc_short_name": short.get(sid),
            "arabic": re.compile(KEY + sid + r"(?!\d)"),
            "cjk_keyed": re.compile(KEY + cjk_code(sid)),
            "cjk_bare": re.compile(cjk_code(sid)),
        }

    rows, _ = index_rows()
    pending = [r for r in rows if not r["document_number"]]
    hits = defaultdict(Counter)
    evidence = defaultdict(list)
    scanned, unreadable = 0, 0

    for i, r in enumerate(pending, 1):
        ident = locator_identity(r["content_file"], r["doc_id"])
        p = os.path.join(STORE, "static_%s.html" % ident)
        if not os.path.exists(p):
            unreadable += 1
            continue
        raw = open(p, "rb").read()
        text = R3._norm(V14._plain(decode_official(raw)))
        if not text:
            unreadable += 1
            continue
        scanned += 1
        for sid, pr in probes.items():
            found = []
            if D64.code_in_text(text, sid):
                found.append("ARABIC_CODE_KEYED")
            if pr["cjk_keyed"].search(text):
                found.append("CJK_CODE_KEYED")
            elif pr["cjk_bare"].search(text):
                found.append("CJK_CODE_BARE")
            names = [n for n in pr["lineage"] if n and n in text]
            if names:
                found.append("LEGAL_NAME")
            if pr["tdcc_short_name"] and pr["tdcc_short_name"] in text:
                found.append("TDCC_SHORT_NAME")
            if found:
                for f in found:
                    hits[sid][f] += 1
                if len(evidence[sid]) < 4:
                    m = (pr["cjk_keyed"].search(text)
                         or pr["arabic"].search(text)
                         or pr["cjk_bare"].search(text))
                    if m:
                        at = m.start()
                    elif names:
                        at = text.find(names[0])
                    elif pr["tdcc_short_name"]:
                        at = text.find(pr["tdcc_short_name"])
                    else:
                        at = 0
                    evidence[sid].append({
                        "doc_id": r["doc_id"], "index_date": r["date"],
                        "locator_identity": ident, "probes": found,
                        "excerpt": text[max(0, at - 60):at + 90]})
        if i % 2000 == 0:
            print("   scanned %d/%d" % (i, len(pending)), flush=True)

    reached = {sid: dict(c) for sid, c in hits.items() if c}
    by_probe = Counter()
    for c in hits.values():
        for k in c:
            by_probe[k] += 1

    three = ["6157", "4110", "6017"]
    three_state = {}
    for sid in three:
        c = hits.get(sid, Counter())
        three_state[sid] = {
            "tdcc_short_name": probes[sid]["tdcc_short_name"],
            "canonical_entity_known": probes[sid]["canonical_entity"],
            "probe_hits": dict(c),
            "reached_by_any_probe": bool(c),
            "evidence": evidence.get(sid, []),
        }

    out = {
        "record": "B0_8_D6_8_2_S6C_PRE2005_SCRIPT_REACHABILITY",
        "b0_8_state": "WIP, UNSEALED",
        "purpose": ("separate 'the archive has no such document' from 'the "
                    "reader cannot see documents of this vintage'"),
        "corpus": {
            "pre_2005_bodies": len(pending),
            "scanned": scanned,
            "unreadable_or_absent": unreadable,
        },
        "probes": ["ARABIC_CODE_KEYED", "CJK_CODE_KEYED", "CJK_CODE_BARE",
                   "LEGAL_NAME", "TDCC_SHORT_NAME"],
        "securities_reached_by_any_probe": len(reached),
        "securities_reached": reached,
        "documents_hit_per_probe_kind": dict(by_probe),
        "the_three_none_events": three_state,
        "READER_IS_BLIND_TO_THIS_VINTAGE": (
            by_probe.get("CJK_CODE_KEYED", 0) + by_probe.get("CJK_CODE_BARE", 0)
            > by_probe.get("ARABIC_CODE_KEYED", 0)),
        "predicates_changed_here": False,
        "events_reclassified_here": 0,

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
    out["measurement_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\npre-2005 bodies scanned      :", scanned, "| unreadable",
          unreadable)
    print("securities reached by a probe:", len(reached), "/ 59")
    print("documents per probe kind     :", dict(by_probe))
    for sid in three:
        s = three_state[sid]
        print("  %s %-8s reached=%s %s" % (sid, s["tdcc_short_name"],
                                           s["reached_by_any_probe"],
                                           s["probe_hits"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
