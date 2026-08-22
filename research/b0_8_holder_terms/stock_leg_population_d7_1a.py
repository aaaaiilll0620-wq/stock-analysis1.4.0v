# -*- coding: utf-8 -*-
"""B0.8 · D7.1a · V2/V3 · STOCK-LEG POPULATION AND ROUTING-ONLY SUCCESSOR IDENTITY.

The termination branch is closed. This stage opens the stock leg by answering
two questions that need no new source at all, and it answers them offline from
evidence already sealed.

V2 · WHICH EVENTS HAVE A STOCK LEG

The population is defined by what the corporate action IS, from the presence-only
reader running unchanged over the authoritative document bundle D6.8.4 left
behind. It is not defined by B0 holdings, claim exposure, the load-bearing
envelope, the replay blocker or performance -- none of those is read here.

For the five events with more than one established-linked document the union of
the whole bundle is used. No preferred document is chosen, and the open question
of what AMBIGUOUS means is not touched.

V3 · SUCCESSOR IDENTITY IS ROUTING METADATA, NOT A HOLDER TERM

To ask a successor-side source anything, one must know who the successor is. The
name is taken from the authoritative transaction document itself: the validated
legal entities it names, minus the disappearing entity's own established lineage.
The security code is then resolved ONLY through first-party code-to-legal-name
bindings that TPEx prints in its own announcements -- the same lexical machinery
D6.8.1 froze, generalised over every code rather than one.

    not used: TEJ, price history, who ended up owning the company, fuzzy name
              similarity, or any inference from market outcome

Everything produced here is stamped DISCOVERY_METADATA_ONLY. No conversion ratio,
no quantity, no credit date, nothing canonical. Where identity cannot be
established authoritatively the event is classified as unresolved rather than
guessed.

    python research/b0_8_holder_terms/stock_leg_population_d7_1a.py
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
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import (        # noqa: E402
    FIELD_PRESENCE_MARKERS, decode_official, field_presence)
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                 # noqa: E402

D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
CLOSURE = os.path.join(HERE, "archive_completeness_closure_d6_8_4.json")
OUT = os.path.join(HERE, "stock_leg_population_d7_1a.json")

STOCK = "STOCK_LEG_PRESENT"
CASH = "CASH_LEG_PRESENT"
MIXED = "MIXED_LEG_PRESENT"
NOSTOCK = "NO_STOCK_LEG_EVIDENCE"

# role markers that mark WHICH side of the transaction a named entity is on
SURVIVOR_ROLE = ("存續公司", "存續之公司", "控股公司", "母公司", "受讓公司")
DISAPPEARING_ROLE = ("消滅公司", "被合併公司", "讓與公司")

ANY_CODE_LABEL = re.compile(
    VR.CODE_LABEL + r"(\d{4}(?!\d)|[%s]{4}(?![%s]))"
    % (VR.ZERO + VR.UNIT_DIGITS, VR.CJK_ANY))


def bind_any(text):
    """Every code -> legal-name binding in one body, for any code.

    Same frozen construction as D6.8.1's bind_names: an authorised code label,
    a clause-bounded gap, and a validated legal name immediately before it.
    Generalised over the code rather than parameterised by one security.
    """
    out = []
    for m in ANY_CODE_LABEL.finditer(text):
        tok = m.group(1)
        code = tok if tok.isdigit() else VR.cjk_code_to_digits(tok)
        if not code:
            continue
        pre = text[max(0, m.start() - 80):m.start()]
        ends = [x.end() for x in re.finditer("有限公司", pre)]
        if not ends or not R3.gap_ok(pre[ends[-1]:]):
            continue
        run = re.search(r"(%s{1,40})$" % R3.NAME_CH, pre[:ends[-1]])
        name = R3.validate_name(run.group(1)) if run else None
        if name:
            out.append((code, name))
    return out


def all_legal_names(text):
    seen = []
    for m in re.finditer(r"%s{1,40}?有限公司" % R3.NAME_CH, text):
        v = R3.validate_name(m.group(0))
        if v and v not in seen:
            seen.append(v)
    return seen


def role_of(text, name):
    """Which side the document puts this entity on, from adjacent role words."""
    roles = set()
    for m in re.finditer(re.escape(name), text):
        window = text[m.start():m.end() + 40]
        for r in SURVIVOR_ROLE:
            if r in window:
                roles.add("SURVIVOR")
        for r in DISAPPEARING_ROLE:
            if r in window:
                roles.add("DISAPPEARING")
    return sorted(roles)


def main() -> int:
    d683 = json.load(open(D683, encoding="utf-8"))
    closure = json.load(open(CLOSURE, encoding="utf-8"))
    assert closure["TPEX_TERMINATION_DOCUMENT_PUBLIC_ARCHIVE_CORPUS"] == \
        "EXHAUSTED_FOR_THIS_PROTOCOL"

    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}

    # ---- first-party code -> legal-name index, whole archive -------------
    code_names = defaultdict(Counter)
    for i, (did, row) in enumerate(sorted(by_loc.items()), 1):
        text, _s = VR.body_text(row)
        if not text:
            continue
        for code, name in bind_any(text):
            code_names[code][name] += 1
        if i % 20000 == 0:
            print("   indexed %d/%d" % (i, len(by_loc)), flush=True)
    index = {c: R3.collapse(list(n)) for c, n in code_names.items()}
    name_to_codes = defaultdict(set)
    for c, names in index.items():
        for n in names:
            name_to_codes[n].add(c)
    print("code->legal-name index: %d codes, %d distinct names"
          % (len(index), len(name_to_codes)), flush=True)

    # ---- V2 · leg presence over the established bundle -------------------
    results, legs = [], Counter()
    for ev in d683["results"]:
        sid = ev["security_id"]
        linked = [c for c in ev["candidates"] if c["doc_id"] in ev["linked"]]
        union = {k: False for k in FIELD_PRESENCE_MARKERS}
        texts = []
        for c in linked:
            for k, v in c["field_presence"].items():
                union[k] = union[k] or v
            t, _s = VR.body_text(by_loc[c["doc_id"]])
            if t:
                texts.append(t)
        blob = "".join(texts)
        leg = (MIXED if union["stock_consideration"]
               and union["cash_consideration"]
               else STOCK if union["stock_consideration"]
               else CASH if union["cash_consideration"] else NOSTOCK)
        legs[leg] += 1

        rec = {"security_id": sid, "event_id": ev["event_id"],
               "canonical_event_date": ev["canonical_event_date"],
               "canonical_exit_reason": ev["canonical_exit_reason"],
               "classification": ev["classification"],
               "linked_documents": len(linked),
               "bundle_is_a_union_over_all_linked_documents": len(linked) > 1,
               "presence_union": union,
               "transaction_leg": leg,
               "disappearing_entity": ev["entity_identity"][
                   "canonical_disappearing_entity"],
               "disappearing_lineage": ev["entity_identity"][
                   "canonical_lineage"]}

        # ---- V3 · routing-only successor identity ------------------------
        lineage = set(rec["disappearing_lineage"])
        others = [n for n in all_legal_names(blob) if n not in lineage]
        roled = {n: role_of(blob, n) for n in others}
        survivors = [n for n, r in roled.items() if "SURVIVOR" in r]
        bound = {n: sorted(name_to_codes.get(n, [])) for n in others}
        if len(survivors) == 1:
            succ, basis = survivors[0], "NAMED_SURVIVOR_ROLE_IN_DOCUMENT"
        elif len(others) == 1:
            succ, basis = others[0], "SOLE_OTHER_LEGAL_ENTITY_IN_BUNDLE"
        else:
            succ, basis = None, None
        codes = sorted(name_to_codes.get(succ, [])) if succ else []
        rec["successor"] = {
            "provenance": "DISCOVERY_METADATA_ONLY",
            "not_canonical_holder_term_extraction": True,
            "candidate_entities_in_bundle": others,
            "role_markers": {k: v for k, v in roled.items() if v},
            "successor_legal_entity": succ,
            "identity_basis": basis,
            "successor_security_id": codes[0] if len(codes) == 1 else None,
            "successor_security_id_candidates": codes,
            "successor_market": "TPEX_CORPUS_BINDING" if codes else None,
            "code_resolution_source": ("first-party TPEx code-to-legal-name "
                                       "bindings in the preserved archive"),
            "identity_established": bool(succ),
            "security_id_established": len(codes) == 1,
            "entity_codes_seen": {n: v for n, v in bound.items() if v},
        }
        results.append(rec)

    pop = [r for r in results if r["transaction_leg"] in (STOCK, MIXED)]
    ident = Counter("ESTABLISHED" if r["successor"]["identity_established"]
                    else "UNRESOLVED" for r in pop)
    sec = Counter("ESTABLISHED" if r["successor"]["security_id_established"]
                  else "UNRESOLVED" for r in pop)

    # marker-specificity diagnostic: the cash flag can fire on bare 現金
    weak_cash = sum(1 for r in results
                    if r["presence_union"]["cash_consideration"]
                    and r["transaction_leg"] in (CASH, MIXED))

    out = {
        "record": "B0_8_D7_1A_STOCK_LEG_POPULATION_AND_SUCCESSOR_ROUTING",
        "b0_8_state": "WIP, UNSEALED",
        "network_requests": 0,
        "inputs": {
            "d6_8_3_census_sha256": d683["census_sha256"],
            "d6_8_4_closure_sha256": closure["closure_sha256"],
            "termination_branch": "CLOSED, not reopened",
        },
        "population_rule": {
            "defined_by": "the corporate-action type read by the unchanged "
                          "presence-only reader",
            "not_defined_by": ["B0 holdings", "claim exposure",
                               "load-bearing envelope", "replay blocker",
                               "performance", "8913"],
            "sampling": False,
            "ambiguous_events_use_union_of_all_linked_documents": True,
            "preferred_document_chosen": False,
            "presence_reader_changed": False,
        },
        "V2_leg_census": dict(legs),
        "acquisition_population": {
            "stock_leg_present": legs[STOCK],
            "mixed_leg_present": legs[MIXED],
            "total": legs[STOCK] + legs[MIXED],
            "cash_leg_present": legs[CASH],
            "no_stock_leg_evidence": legs[NOSTOCK],
            "security_ids": sorted(r["security_id"] for r in pop),
        },
        "V3_successor_routing": {
            "identity": dict(ident),
            "security_id": dict(sec),
            "unresolved_identity": sorted(
                r["security_id"] for r in pop
                if not r["successor"]["identity_established"]),
            "identity_but_no_security_id": sorted(
                r["security_id"] for r in pop
                if r["successor"]["identity_established"]
                and not r["successor"]["security_id_established"]),
            "code_to_legal_name_index_size": len(index),
            "all_marked": "DISCOVERY_METADATA_ONLY",
        },
        "marker_specificity_diagnostic": {
            "note": ("the frozen cash marker set includes the bare token 現金, "
                     "which can fire on unrelated cash-related wording; it is "
                     "reported, not changed"),
            "events_whose_leg_depends_on_the_cash_flag": weak_cash,
        },
        "results": results,

        # V11 invariants
        "canonical_holder_terms_materialized": False,
        "holder_term_values_extracted": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "cash_leg_source_hunting": False,
        "termination_discovery_branch_reopened": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "artefacts_rewritten": 0,
    }
    out["census_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nleg census        :", dict(legs))
    print("acquisition pop   :", out["acquisition_population"]["total"],
          "(stock %d + mixed %d)" % (legs[STOCK], legs[MIXED]))
    print("successor identity:", dict(ident), "| security_id:", dict(sec))
    print("unresolved        :", out["V3_successor_routing"][
        "unresolved_identity"])
    print("id but no code    :", out["V3_successor_routing"][
        "identity_but_no_security_id"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
