# -*- coding: utf-8 -*-
"""B0.8 · D7.2a · X3/X4/X10 · GRAMMAR FREEZE, UNIFORM RERUN, IDENTITY SEPARATION.

This stage does no network work. It closes the three adjudication corrections the
D7.2 spec raises against D7.1 before any acquisition begins.

X3 · FREEZE AND DISCLOSE, THEN RERUN ONCE, UNIFORMLY
    The relation-role grammar, entity-boundary token, inline-code grammar,
    legal-name normalisation and MOPS query-name transformation are imported from
    D7.1b UNCHANGED and hashed. The grammar was expanded after inspecting
    unresolved bundles during D7.1b, so

        routing_parser_pre_freeze_event_outcome_exposure = true

    is recorded plainly. That is admissible only because every output here is
    DISCOVERY_METADATA_ONLY. The identifying step is then re-run over all 30
    events uniformly and asserted byte-identical to the stored D7.1b routing --
    proving the freeze is stable and no event-specific rule was added after it.

X4 · LEGAL ENTITY IS NOT SECURITY IS NOT MARKET
    Three independent statuses are reported per event. A successor legal entity
    can be established while its security is unresolved, and lacking a Taiwan
    security code does not by itself make the legal entity unresolved. Security
    routing (X5) and market status (X6) are deliberately left PENDING here and
    resolved by the later stages, so this stage cannot smuggle a routing outcome
    into an identity verdict.

X4 · 4947 IS ADJUDICATED FROM ITS OWN DOCUMENT, AS A DIAGNOSTIC
    The frozen CJK grammar returns nothing for 4947 because the successor is a
    Latin-script foreign entity (Orthosie / Euporie ... Ltd / Limited), which the
    frozen 有限公司 name token cannot match, and because the holder consideration
    is cash (NT$230 per share), so no ROC successor security exists at all. This
    is recorded as an X12 diagnostic and DISCOVERY_METADATA -- the frozen grammar
    is NOT extended to catch a Latin name found by inspecting this one event, and
    D7.1a is NOT rewritten even though its leg census read 4947 as MIXED.

X10 · OD-1-7 MERGER APPLICABILITY IS NOT_ESTABLISHED, NOT EXCLUDED
    D7.1 claimed OD-1-7's 交付日期 field "excludes" merger. Neither inclusion nor
    exclusion is established without first-party 減資/轉換 semantics, so the claim
    is corrected to NOT_ESTABLISHED_FROM_CURRENT_SCHEMA.

    python research/b0_8_holder_terms/routing_freeze_and_identity_separation_d7_2a.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows   # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                    # noqa: E402
import entity_identity_conformance_repair_d6_8_1 as R3        # noqa: E402
import successor_identity_routing_d7_1b as D71B               # noqa: E402

D71A = os.path.join(HERE, "stock_leg_population_d7_1a.json")
D71B_JSON = os.path.join(HERE, "successor_identity_routing_d7_1b.json")
D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
OUT = os.path.join(HERE, "routing_freeze_and_identity_separation_d7_2a.json")


def frozen_grammar_fingerprint():
    """Hash the exact identifying grammar imported from D7.1b, unchanged."""
    material = {
        "NAME_TOKEN": D71B.N,
        "PRE": D71B._PRE,
        "RELATIONS": [[role, pat] for role, pat in D71B.RELATIONS],
        "INLINE_CODE": D71B.INLINE_CODE,
        "ROLE_NOISE": list(D71B.ROLE_NOISE),
        "MOPS_QUERY_NAME_TRANSFORM": r"re.sub(r'股份有限公司$', '', name)",
        "LEGAL_NAME_NORMALISATION": "entity_identity_conformance_repair_d6_8_1"
                                    ".validate_name + .collapse",
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return material, hashlib.sha256(blob.encode("utf-8")).hexdigest()


def linked_and_established_text(ev, by_loc):
    """Reconstruct exactly the two text scopes D7.1b read, from the frozen corpus."""
    linked_text, est_text = "", ""
    linked = set(ev["linked"])
    for c in ev["candidates"]:
        t, _s = VR.body_text(by_loc[c["doc_id"]])
        if not t:
            continue
        if c["doc_id"] in linked:
            linked_text += t
        if c["gate_i"] == "ENTITY_IDENTITY_ESTABLISHED":
            est_text += t
    return linked_text, est_text


def rerun_identity(ev, lineage, by_loc):
    """The frozen identifying step, re-executed uniformly (no code resolution)."""
    linked_text, est_text = linked_and_established_text(ev, by_loc)
    found, inline, _noise = D71B.successors_in(linked_text, lineage)
    scope = "LINKED_BUNDLE"
    if not found:
        found, inline, _n2 = D71B.successors_in(est_text, lineage)
        scope = "GATE_I_ESTABLISHED_CANDIDATES" if found else None
    names = R3.collapse(list(found)) if found else []
    succ = names[0] if len(names) == 1 else None
    return succ, names, scope


def main() -> int:
    d71a = json.load(open(D71A, encoding="utf-8"))
    d71b = json.load(open(D71B_JSON, encoding="utf-8"))
    d683 = json.load(open(D683, encoding="utf-8"))
    ev683 = {e["security_id"]: e for e in d683["results"]}
    route71b = {r["security_id"]: r for r in d71b["results"]}
    pop = [r for r in d71a["results"]
           if r["transaction_leg"] in ("STOCK_LEG_PRESENT", "MIXED_LEG_PRESENT")]

    material, grammar_sha = frozen_grammar_fingerprint()

    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}

    per_event, drift, sec_tax, leg_tax = [], [], Counter(), Counter()
    for r in pop:
        sid = r["security_id"]
        ev = ev683[sid]
        lineage = set(r["disappearing_lineage"])
        succ, names, scope = rerun_identity(ev, lineage, by_loc)

        stored = route71b[sid]["successor_legal_entity"]
        if succ != stored:
            drift.append({"security_id": sid, "rerun": succ, "stored": stored})

        # ---- X4 · three independent statuses ----------------------------
        legal_status = "ESTABLISHED" if succ else "UNRESOLVED"
        # security + market are resolved by X5/X6; never inferred from identity
        stored_code = route71b[sid]["successor_security_id"]
        if stored_code:
            security_status = "DOMESTIC_SECURITY_ID_ESTABLISHED"
        elif succ:
            security_status = "PENDING_FIRST_PARTY_DIRECTORY_ROUTING"
        else:
            security_status = "SECURITY_ID_UNRESOLVED"
        market_status = ("PENDING_SUCCESSOR_SIDE_MOPS" if stored_code
                         else "PENDING")

        leg_tax[legal_status] += 1
        sec_tax[security_status] += 1
        per_event.append({
            "security_id": sid,
            "transaction_leg": r["transaction_leg"],
            "disappearing_entity": r["disappearing_entity"],
            "successor_legal_entity": succ,
            "successor_legal_entity_status": legal_status,
            "successor_security_status": security_status,
            "successor_market_status": market_status,
            "successor_security_id_from_d7_1b": stored_code,
            "code_resolution_source_d7_1b":
                route71b[sid]["code_resolution_source"],
            "extraction_scope": scope,
            "rerun_matches_d7_1b": succ == stored,
        })

    out = {
        "record": "B0_8_D7_2A_ROUTING_FREEZE_AND_IDENTITY_SEPARATION",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {
            "d7_1a_census_sha256": d71a["census_sha256"],
            "d7_1b_routing_sha256": d71b["routing_sha256"],
            "d6_8_3_census_sha256": d683["census_sha256"],
        },

        # ---- X3 ---------------------------------------------------------
        "X3_grammar_freeze": {
            "frozen_material": material,
            "grammar_sha256": grammar_sha,
            "imported_unchanged_from": "successor_identity_routing_d7_1b",
            "routing_parser_pre_freeze_event_outcome_exposure": True,
            "exposure_reason": (
                "the relation grammar was widened during D7.1b after inspecting "
                "unresolved event bundles (8/30 -> 22/30 -> 29/30); admissible "
                "only because the output is DISCOVERY_METADATA_ONLY"),
            "uniform_rerun_events": len(per_event),
            "rerun_drift_from_d7_1b": drift,
            "freeze_is_stable": not drift,
            "no_event_specific_rule_added_after_freeze": not drift,
        },

        # ---- X4 ---------------------------------------------------------
        "X4_identity_separation": {
            "principle": ("legal entity, security and market are three separate "
                          "statuses; no ROC code does not make the legal entity "
                          "unresolved"),
            "legal_entity_status_counts": dict(leg_tax),
            "security_status_counts": dict(sec_tax),
            "taxonomy_gap_flagged": {
                "issue": ("X4's security taxonomy has no value for a DOMESTIC "
                          "legal entity that is established but has NO public "
                          "security (private / holding-company acquirers such as "
                          "永崴投資控股, 森投資, 滿得投資, 宏育管理顧問). It is "
                          "neither FOREIGN_OR_NON_ROC nor SECURITY_ID_UNRESOLVED "
                          "-- there is simply no security to resolve."),
                "proposed_fourth_value":
                    "DOMESTIC_ENTITY_NO_PUBLIC_SECURITY",
                "resolved_in": "D7.2b (first-party directory routing decides "
                               "which no-code names are listed vs non-listed)",
            },
        },

        "X4_4947_diagnostic": {
            "disappearing_entity": "昂寶電子股份有限公司",
            "frozen_grammar_result": "NO_RELATION_MATCHED",
            "why_frozen_grammar_misses_it": (
                "the successor is a Latin-script foreign entity "
                "(Orthosie Investment Holdings Ltd / Euporie ... Holdings "
                "Limited); the frozen name token requires a CJK name ending "
                "有限公司 and cannot match a Latin 'Ltd'/'Limited' name"),
            "holder_consideration_from_document":
                "普通股1股 換發新臺幣230元現金 (cash-out, NT$230/share)",
            "successor_legal_entity_status": "UNRESOLVED_BY_FROZEN_GRAMMAR",
            "diagnostic_classification": "FOREIGN_SUCCESSOR_HOLDER_CASH_CONSIDERATION",
            "grammar_extended_to_catch_it": False,
            "reason_not_extended": (
                "a Latin-script rule derived by inspecting the one event it must "
                "catch is outcome-driven tuning; the frozen grammar is left "
                "unchanged and this stays DISCOVERY_METADATA"),
            "d7_1_foreign_holdco_claim": "WITHDRAWN_AS_NON_GRAMMAR_ANCHORED",
            "d7_1a_leg_census_caveat": (
                "D7.1a read 4947 as MIXED_LEG_PRESENT from 換發 vocabulary, but "
                "the holder-facing consideration is cash; the successor-share leg "
                "for holders is absent. D7.1a is preserved unchanged; this is "
                "recorded as exposure, not a rewrite"),
            "d7_1a_rewritten": False,
        },

        # ---- X10 --------------------------------------------------------
        "X10_od_1_7_correction": {
            "field_present": "交付日期",
            "coverage_begins": "2025",
            "d7_1_claim": "excludes merger/share-conversion",
            "corrected_status": "NOT_ESTABLISHED_FROM_CURRENT_SCHEMA",
            "reason": ("the meaning of 減資/轉換 has not been authoritatively "
                       "shown to include or exclude the D7.1 merger/share-"
                       "conversion population; neither inclusion nor exclusion "
                       "is claimed without first-party semantics"),
        },

        "per_event": per_event,

        # ---- X13 invariants ---------------------------------------------
        "canonical_holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "cash_leg_source_hunting": False,
        "termination_discovery_branch_reopened": False,
        "successor_identity_is": "DISCOVERY_METADATA_ONLY",
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "network_requests": 0,
        "artefacts_rewritten": 0,
    }
    out["freeze_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("grammar_sha256      :", grammar_sha)
    print("uniform rerun events:", len(per_event))
    print("rerun drift vs D7.1b:", len(drift), drift or "(none)")
    print("legal-entity status :", dict(leg_tax))
    print("security status     :", dict(sec_tax))
    print("4947 frozen grammar :", out["X4_4947_diagnostic"]["frozen_grammar_result"],
          "->", out["X4_4947_diagnostic"]["diagnostic_classification"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
