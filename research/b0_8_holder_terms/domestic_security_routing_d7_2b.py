# -*- coding: utf-8 -*-
"""B0.8 · D7.2b · X5 · CLOSE DOMESTIC SECURITY ROUTING BEFORE ANY ACQUISITION.

For every event whose successor legal entity is established (D7.2a) but whose
security code was not resolved in D7.1b, route the code using first-party
directories ONLY, matched on the FULL LEGAL NAME (exact), never fuzzily:

    1  TDCC STK003 survivor-code table (first-party, ROC 93-97 vintage)
    2  TWSE listed-company basic-information directory (openapi t187ap03_L)
    3  TPEx OTC-company basic-information directory (openapi t187ap03_O)

MOPS autocomplete failure in D7.1b is not evidence that no authoritative route
exists; these directories are the authoritative route, and they are exhausted
here before any successor-side document acquisition is attempted.

Forbidden, and not used: TEJ, price history, fuzzy name similarity, search-engine
snippets, market outcome.

A successor legal entity that resolves in none of the listed-security directories
is NOT automatically "unresolved": a private or holding-company acquirer has no
public security to resolve at all. That distinct state is reported as
DOMESTIC_ENTITY_NO_PUBLIC_SECURITY, separately from
SUCCESSOR_SECURITY_ROUTING_UNRESOLVED (a name that should be listed but is absent
from the current directory, typically because of a later rename or delisting --
which is recorded, never guessed around).

    python research/b0_8_holder_terms/domestic_security_routing_d7_2b.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
import successor_identity_routing_d7_1b as D71B               # noqa: E402

D72A = os.path.join(HERE, "routing_freeze_and_identity_separation_d7_2a.json")
CACHE = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                     "d7_2b_first_party_directories.json")
OUT = os.path.join(HERE, "domestic_security_routing_d7_2b.json")

TWSE = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
UA = {"User-Agent": "Mozilla/5.0"}
NON_ISSUER_FORMS = ("投資控股", "控股", "投資股份", "創業投資", "管理顧問",
                    "資產管理")


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def load_directories():
    """First-party listed-security directories, cached verbatim once fetched."""
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    tw = _get(TWSE)
    tp = _get(TPEX)
    dirs = {
        "twse": [{"code": r["公司代號"], "legal_name": r["公司名稱"],
                  "foreign_reg": r.get("外國企業註冊地國", "").strip()}
                 for r in tw],
        "tpex": [{"code": r["SecuritiesCompanyCode"],
                  "legal_name": r["CompanyName"],
                  "foreign_reg": (r.get("Registration") or "").strip()}
                 for r in tp],
        "twse_out_date": tw[0].get("出表日期"),
        "tpex_out_date": tp[0].get("Date"),
    }
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dirs, fh, ensure_ascii=False, sort_keys=True)
    return dirs


def build_index(dirs):
    """Exact full-legal-name -> record. Both boards; TWSE wins a rare tie."""
    idx = {}
    for board in ("tpex", "twse"):
        for r in dirs[board]:
            idx[r["legal_name"]] = {"code": r["code"], "board": board.upper(),
                                    "foreign_reg": r["foreign_reg"]}
    return idx


def main() -> int:
    d72a = json.load(open(D72A, encoding="utf-8"))
    dirs = load_directories()
    idx = build_index(dirs)
    is_foreign = lambda fr: bool(fr) and fr not in ("－", "-", "")

    stk = D71B.stk003_control()

    sec_tax, market_tax, per_event = Counter(), Counter(), []
    for ev in d72a["per_event"]:
        sid = ev["security_id"]
        name = ev["successor_legal_entity"]
        rec = {
            "security_id": sid,
            "transaction_leg": ev["transaction_leg"],
            "successor_legal_entity": name,
            "successor_legal_entity_status": ev["successor_legal_entity_status"],
            "prior_security_id": ev["successor_security_id_from_d7_1b"],
            "prior_source": ev["code_resolution_source_d7_1b"],
        }

        if ev["successor_legal_entity_status"] == "UNRESOLVED":
            # 4947 -- foreign successor + cash holder consideration (D7.2a)
            rec.update(successor_security_status="FOREIGN_OR_NON_ROC_SUCCESSOR",
                       successor_security_id=None, route_source="D7_2A_DIAGNOSTIC",
                       successor_market_status="FOREIGN_SUCCESSOR_ROUTE_REQUIRED")
        elif ev["successor_security_status"] == "DOMESTIC_SECURITY_ID_ESTABLISHED":
            # already resolved in D7.1b (TPEx corpus / in-doc / MOPS)
            rec.update(successor_security_status="DOMESTIC_SECURITY_ID_ESTABLISHED",
                       successor_security_id=ev["successor_security_id_from_d7_1b"],
                       route_source=ev["code_resolution_source_d7_1b"],
                       successor_market_status="DOMESTIC_LISTED_OR_OTC")
        else:
            # ---- X5 · first-party directory routing, exact legal name ----
            code, source, board, foreign = None, None, None, False
            hit = idx.get(name)
            if hit:
                code, source, board = hit["code"], "TWSE_TPEX_OPENAPI_DIRECTORY", \
                    hit["board"]
                foreign = is_foreign(hit["foreign_reg"])
            elif stk.get(sid) and stk[sid]["survivor_code"] and (
                    stk[sid]["survivor_name"] == name):
                code, source = stk[sid]["survivor_code"], "TDCC_STK003_SURVIVOR"

            if code and foreign:
                rec.update(
                    successor_security_status="FOREIGN_OR_NON_ROC_SUCCESSOR",
                    successor_security_id=code, route_source=source,
                    successor_market_status="FOREIGN_LISTED")
            elif code:
                rec.update(
                    successor_security_status="DOMESTIC_SECURITY_ID_ESTABLISHED",
                    successor_security_id=code, route_source=source,
                    successor_market_status="DOMESTIC_LISTED_OR_OTC")
            elif any(f in name for f in NON_ISSUER_FORMS):
                rec.update(
                    successor_security_status="DOMESTIC_ENTITY_NO_PUBLIC_SECURITY",
                    successor_security_id=None, route_source=None,
                    successor_market_status="NON_ISSUER_PRIVATE_OR_HOLDING",
                    entity_form_note=("legal name is an investment/holding/"
                                      "consulting form with no listed security "
                                      "in any first-party directory"))
            else:
                rec.update(
                    successor_security_status="SUCCESSOR_SECURITY_ROUTING_UNRESOLVED",
                    successor_security_id=None, route_source=None,
                    successor_market_status="ABSENT_FROM_CURRENT_DIRECTORY",
                    unresolved_note=("established legal name is absent from the "
                                     "current TWSE/TPEx directory; likely a later "
                                     "rename or delisting -- not guessed around"))

        sec_tax[rec["successor_security_status"]] += 1
        market_tax[rec["successor_market_status"]] += 1
        per_event.append(rec)

    established = [r for r in per_event
                  if r["successor_security_status"]
                  == "DOMESTIC_SECURITY_ID_ESTABLISHED"]
    out = {
        "record": "B0_8_D7_2B_DOMESTIC_SECURITY_ROUTING",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_2a_freeze_sha256": d72a["freeze_sha256"]},
        "X5_first_party_directories": {
            "sources_used": ["TDCC STK003 survivor table (ROC 93-97)",
                             "TWSE openapi t187ap03_L listed-company directory",
                             "TPEx openapi t187ap03_O OTC-company directory"],
            "match_rule": "exact full legal name; never fuzzy",
            "forbidden": ["TEJ", "price history", "fuzzy similarity",
                          "search-engine snippets", "market outcome"],
            "twse_directory_rows": len(dirs["twse"]),
            "tpex_directory_rows": len(dirs["tpex"]),
            "twse_out_date": dirs["twse_out_date"],
            "tpex_out_date": dirs["tpex_out_date"],
            "directory_is_current_snapshot_caveat": (
                "these are current directories; a successor that later renamed or "
                "delisted is absent and is reported "
                "SUCCESSOR_SECURITY_ROUTING_UNRESOLVED, not guessed"),
        },
        "security_status_counts": dict(sec_tax),
        "market_status_counts": dict(market_tax),
        "domestic_security_ids_established_total": len(established),
        "domestic_security_ids_established": sorted(
            (r["security_id"], r["successor_security_id"]) for r in established),
        "per_event": per_event,

        # X13 invariants
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
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "artefacts_rewritten": 0,
    }
    out["routing_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("security status  :", dict(sec_tax))
    print("market status    :", dict(market_tax))
    print("domestic codes   : %d established" % len(established))
    for r in per_event:
        if r["successor_security_status"] != "DOMESTIC_SECURITY_ID_ESTABLISHED":
            print("   %-6s %-38s -> %s" % (
                r["security_id"], r["successor_security_status"],
                r["successor_market_status"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
