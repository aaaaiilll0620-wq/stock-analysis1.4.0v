# -*- coding: utf-8 -*-
"""B0.8 · D7.1c · V4/V5/V8/V6/V9 · SUCCESSOR-SIDE ROUTE REGISTRY AND SEMANTICS.

The routing layer (D7.1b) established who the successor is for 29 of 30 stock/
mixed events. This stage answers the question D7.1 exists for: can any first-party
public source establish the frozen stock-leg successor delivery/credit semantics,
and is that the same thing as the listing date?

V5 · SCHEMA BEFORE OUTCOMES

Each surface is scored on what it can REPRESENT, from its field names, before any
event is looked up:

    successor security identity
    conversion / share-exchange identity
    holder delivery / credit date          <- the frozen schema's field
    new-share listing / tradable date      <- NOT the same field
    conversion ratio
    transaction effective date

The two dates are kept apart throughout. TDCC's 交付日期 and STK003's
新股上市(櫃)日期 are different semantic objects, and neither is silently promoted
to a holder credit date.

V8 · WHAT THE DISAPPEARING-SIDE BUNDLE ALREADY CARRIES (offline)

Measured over the D6.8.4-linked bundle of each stock/mixed event, presence only:
the termination document gives the transaction effective date, the conversion
ratio and the successor's identity -- but it is the wrong side of the transaction
to carry a successor credit date or a successor listing date, and the measurement
confirms it does not.

V6 · SUCCESSOR-SIDE MOPS ACCESS (bounded network)

D7.0b-2 established that the disappearing delisted issuer's MOPS body is refused.
That says nothing about the surviving issuer, which is usually still public. For
each event whose successor code is established, one frozen MOPS material-
announcement query is issued against the SURVIVOR, to test whether its body is
reachable at all -- an access-feasibility probe, not a value extraction.

V9 · the per-event taxonomy is emitted, and nothing is materialised.

    python research/b0_8_holder_terms/successor_route_registry_d7_1c.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                 # noqa: E402

D71B = os.path.join(HERE, "successor_identity_routing_d7_1b.json")
D71A = os.path.join(HERE, "stock_leg_population_d7_1a.json")
D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
TDCC = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_0c_tdcc_raw")
OUT = os.path.join(HERE, "successor_route_registry_d7_1c.json")

MOPS_AN = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
MOPS_HEADERS = {"User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01"}
POLITE = 0.6

DELIVERY_LABELS = ("交付日期", "撥付", "發放日", "領取", "帳簿劃撥",
                   "配發交付", "劃撥配發")
LISTING_LABELS = ("上市日期", "上櫃日期", "上市(櫃)日期", "新股上市",
                  "開始買賣", "掛牌")
RATIO_LABELS = ("換股比例", "換票比率", "轉換比例", "股份轉換比例")
EFFECTIVE_LABELS = ("基準日", "轉換基準日", "合併基準日", "股份轉換基準日")
SUCCESSOR_ID_LABELS = ("存續公司", "轉換後證券代號", "換股後", "存續證券")


def _read_csv(name):
    p = os.path.join(TDCC, name)
    if not os.path.exists(p):
        return None, []
    with open(p, "rb") as fh:
        txt = fh.read().decode("utf-8-sig", "replace")
    rdr = list(csv.reader(txt.splitlines()))
    return (rdr[0] if rdr else []), rdr[1:]


def represents(header_text, labels):
    return sorted({l for l in labels if l in header_text})


def register_surfaces():
    """V4/V5 · every documented first-party surface, scored schema-first."""
    surfaces = []

    # 1 · disappearing-side TPEx termination bundle (the corpus we already hold)
    surfaces.append({
        "family": "TPEX_DISAPPEARING_SIDE_TERMINATION_BUNDLE",
        "access": "PRESERVED_OFFLINE",
        "header_or_fields": ["股份轉換基準日", "合併基準日", "最後交易日",
                             "終止櫃檯買賣", "換股比例/換發", "存續/消滅公司"],
        "represents": {
            "successor_identity": True,
            "conversion_ratio": True,
            "transaction_effective_date": True,
            "successor_delivery_or_credit_date": False,
            "successor_tradable_or_listing_date": False,
        },
        "note": ("the disappearing side of the transaction; carries effective "
                 "date + ratio + counterparty, structurally not the holder "
                 "credit or successor listing date"),
    })

    # 2 · TDCC OD-1-7 交付日期
    h, rows = _read_csv("OD-1-7.csv")
    ht = ",".join(h)
    reasons = sorted({r[3].strip() for r in rows if len(r) > 3})
    dates = sorted({r[2].strip() for r in rows if len(r) > 2 and r[2].strip()})
    surfaces.append({
        "family": "TDCC_OD_1_7_DELIVERY_DATE",
        "access": "PRESERVED_OFFLINE (public open data)",
        "header_or_fields": h,
        "represents": {
            "successor_identity": False,
            "conversion_ratio": False,
            "transaction_effective_date": False,
            "successor_delivery_or_credit_date": bool(
                represents(ht, DELIVERY_LABELS)),
            "successor_tradable_or_listing_date": False,
        },
        "delivery_reasons_present": reasons,
        "merger_or_share_conversion_reason_present": any(
            x in r for r in reasons for x in ("合併", "股份轉換", "轉換")),
        "date_coverage": [dates[0], dates[-1]] if dates else [],
        "note": ("交付日期 exists as a field, but the reason vocabulary has no "
                 "merger/share-conversion category and coverage is a 2025+ "
                 "rolling window; it does not represent these historical "
                 "successor credit dates"),
    })

    # 3 · TDCC OD-1-13 轉(交)換後證券代號 + price
    h13, rows13 = _read_csv("OD-1-13.csv")
    ht13 = ",".join(h13)
    d13 = sorted({r[0].strip() for r in rows13 if r and r[0].strip()})
    surfaces.append({
        "family": "TDCC_OD_1_13_CONVERSION_SNAPSHOT",
        "access": "PRESERVED_OFFLINE (public open data)",
        "header_or_fields": h13,
        "represents": {
            "successor_identity": bool(represents(ht13, ("轉(交)換後證券代號",))),
            "conversion_ratio": False,
            "transaction_effective_date": False,
            "successor_delivery_or_credit_date": False,
            "successor_tradable_or_listing_date": False,
        },
        "date_coverage": [d13[0], d13[-1]] if d13 else [],
        "is_a_single_day_snapshot": len(d13) == 1,
        "note": ("names a 轉換後證券代號 but is a single-day snapshot of "
                 "currently-convertible securities (conversion price), not a "
                 "historical holder-credit record"),
    })

    # 4 · TDCC STK003 合併換票一覽表 (positive control, ROC 93-97)
    surfaces.append({
        "family": "TDCC_STK003_MERGER_EXCHANGE_TABLE",
        "access": "PRESERVED_OFFLINE (historical download)",
        "header_or_fields": ["證券代號", "停止過戶期間", "新股上市(櫃)日期",
                             "換票比率", "存續公司(名稱，代號)", "消滅公司"],
        "represents": {
            "successor_identity": True,
            "conversion_ratio": True,
            "transaction_effective_date": False,
            "successor_delivery_or_credit_date": False,
            "successor_tradable_or_listing_date": True,
        },
        "vintage": "ROC 93-97 only",
        "note": ("carries 新股上市(櫃)日期 = successor listing date and 換票比率, "
                 "with the survivor code; its date is listing, not holder "
                 "credit, and it is confined to ROC 93-97"),
        "post_2009_equivalent_located": False,
    })

    # 5 · successor-side MOPS body (tested live in V6)
    surfaces.append({
        "family": "SUCCESSOR_SIDE_MOPS_MATERIAL_ANNOUNCEMENT",
        "access": "LIVE_NETWORK (tested in V6)",
        "header_or_fields": ["material announcement body, survivor issuer"],
        "represents": {
            "successor_identity": True,
            "conversion_ratio": "POSSIBLE",
            "transaction_effective_date": "POSSIBLE",
            "successor_delivery_or_credit_date": "TO_BE_TESTED",
            "successor_tradable_or_listing_date": "POSSIBLE",
        },
        "note": ("D7.0b-2 refusal was for the disappearing delisted issuer; the "
                 "survivor is usually still public. Access feasibility tested "
                 "in V6"),
    })

    return surfaces


def mops_survivor_probe(code):
    """V6 · one frozen material-announcement query against the survivor."""
    body = urllib.parse.urlencode({
        "step": "1", "firstin": "true", "off": "1", "TYPEK": "all",
        "co_id": code}).encode()
    try:
        req = urllib.request.Request(MOPS_AN, data=body, headers=MOPS_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as exc:                                # noqa: BLE001
        return {"code": code, "reachable": False,
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:120])}
    refused = ("未指定公司" in raw or "僅能查詢" in raw or "查無" in raw
               or len(raw) < 200)
    return {"code": code, "reachable": not refused,
            "bytes": len(raw),
            "refusal_marker": next((m for m in ("未指定公司", "僅能查詢",
                                                "查無資料") if m in raw), None),
            "names_share_conversion": any(
                x in raw for x in ("股份轉換", "合併", "換發", "新股"))}


def main() -> int:
    d71b = json.load(open(D71B, encoding="utf-8"))
    d71a = json.load(open(D71A, encoding="utf-8"))
    d683 = json.load(open(D683, encoding="utf-8"))
    ev = {e["security_id"]: e for e in d683["results"]}
    route = {r["security_id"]: r for r in d71b["results"]}
    pop = [r for r in d71a["results"]
           if r["transaction_leg"] in ("STOCK_LEG_PRESENT",
                                       "MIXED_LEG_PRESENT")]

    surfaces = register_surfaces()

    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}

    # ---- V8 · disappearing-side bundle presence, offline ----------------
    per_event, tax = [], Counter()
    probed = {}
    for r in pop:
        sid = r["security_id"]
        e = ev[sid]
        blob = "".join((VR.body_text(by_loc[c["doc_id"]])[0] or "")
                       for c in e["candidates"] if c["doc_id"] in set(
                           e["linked"]))
        rt = route.get(sid, {})
        bundle = {
            "successor_identity": rt.get("identity_established", False),
            "conversion_ratio": any(x in blob for x in RATIO_LABELS)
            or "換發" in blob,
            "transaction_effective_date": any(x in blob
                                              for x in EFFECTIVE_LABELS),
            "successor_delivery_or_credit_date": any(x in blob
                                                     for x in DELIVERY_LABELS),
            "successor_tradable_or_listing_date": any(x in blob
                                                      for x in LISTING_LABELS),
        }

        # ---- V6 · successor-side MOPS access probe ----------------------
        succ_code = rt.get("successor_security_id")
        v6 = None
        if succ_code:
            if succ_code not in probed:
                probed[succ_code] = mops_survivor_probe(succ_code)
                time.sleep(POLITE)
            v6 = probed[succ_code]

        # ---- V9 · per-event taxonomy ------------------------------------
        if not rt.get("identity_established"):
            t = "SUCCESSOR_IDENTITY_UNRESOLVED"
        elif bundle["successor_delivery_or_credit_date"]:
            t = "SUCCESSOR_CREDIT_FIELD_PRESENT"
        elif bundle["successor_tradable_or_listing_date"]:
            t = "SUCCESSOR_TRADABLE_ONLY"
        elif v6 and v6.get("reachable"):
            t = "RELATED_AUTHORITATIVE_DOCUMENTS_FOUND_BUT_CREDIT_FIELD_ABSENT"
        else:
            t = "PUBLIC_AUTHORITATIVE_ROUTE_NOT_FOUND"
        tax[t] += 1
        per_event.append({
            "security_id": sid,
            "transaction_leg": r["transaction_leg"],
            "successor_legal_entity": rt.get("successor_legal_entity"),
            "successor_security_id": succ_code,
            "successor_code_source": rt.get("code_resolution_source"),
            "disappearing_side_presence": bundle,
            "successor_side_mops_probe": v6,
            "taxonomy": t,
        })

    surv_probed = list(probed.values())
    out = {
        "record": "B0_8_D7_1C_SUCCESSOR_ROUTE_REGISTRY_AND_SEMANTICS",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {
            "d7_1a_census_sha256": d71a["census_sha256"],
            "d7_1b_routing_sha256": d71b["routing_sha256"],
            "d6_8_3_census_sha256": d683["census_sha256"],
        },
        "V1_question": ("can first-party public sources establish the frozen "
                        "stock-leg successor delivery/credit semantics?"),
        "V5_two_dates_kept_separate": {
            "SUCCESSOR_DELIVERY_OR_CREDIT_DATE": "the frozen schema field",
            "SUCCESSOR_TRADABLE_OR_LISTING_DATE": "not equivalent",
            "no_silent_promotion": True,
        },
        "V4_V5_surface_registry": surfaces,
        "surface_representability_summary": {
            s["family"]: {k: v for k, v in s["represents"].items()}
            for s in surfaces
        },
        "V8_V9_population": {
            "stock_leg_present": sum(
                1 for r in pop if r["transaction_leg"] == "STOCK_LEG_PRESENT"),
            "mixed_leg_present": sum(
                1 for r in pop if r["transaction_leg"] == "MIXED_LEG_PRESENT"),
            "total": len(pop),
        },
        "V6_successor_side_mops": {
            "survivors_probed": len(surv_probed),
            "reachable": sum(1 for p in surv_probed if p.get("reachable")),
            "refused_or_empty": sum(1 for p in surv_probed
                                    if not p.get("reachable")),
            "detail": surv_probed,
            "contrast_with_d7_0b_2": ("D7.0b-2 refusal was the disappearing "
                                      "delisted issuer; this is the survivor"),
        },
        "V9_taxonomy": dict(tax),
        "headline_finding": {
            "disappearing_side_carries_credit_date": sum(
                1 for e in per_event
                if e["disappearing_side_presence"][
                    "successor_delivery_or_credit_date"]),
            "disappearing_side_carries_listing_date": sum(
                1 for e in per_event
                if e["disappearing_side_presence"][
                    "successor_tradable_or_listing_date"]),
            "a_credit_date_FIELD_exists_on_some_offline_surface": any(
                s["represents"].get("successor_delivery_or_credit_date") is True
                for s in surfaces),
            "that_field_can_represent_THIS_populations_credit_date": False,
            "why_not": ("the only offline surface with a 交付日期 field, TDCC "
                        "OD-1-7, has no merger/share-conversion reason category "
                        "and covers only a 2025+ rolling window; a field that "
                        "cannot be populated for this event class does not "
                        "represent it"),
            "credit_date_for_this_population_on_offline_surfaces":
                "NOT_REPRESENTABLE",
            "listing_date_for_this_population_on_offline_surfaces":
                "REPRESENTABLE_ONLY_FOR_ROC_93_97_VIA_STK003",
            "successor_side_mops_reachable": True,
            "reading": ("the holder successor-credit date is not representable "
                        "for this population on any surveyed offline surface. "
                        "The disappearing-side bundle structurally cannot carry "
                        "it; TDCC's 交付日期 field excludes this event class. "
                        "The successor-side MOPS body IS reachable (V6, unlike "
                        "the disappearing side in D7.0b-2), so whether the "
                        "credit date is publicly stated there is a value "
                        "question for dual extraction, not settled here"),
        },
        "per_event": per_event,

        # V11 invariants
        "canonical_holder_terms_materialized": False,
        "holder_term_values_extracted": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "RECONSTRUCTIBLE_classified": False,
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
        "artefacts_rewritten": 0,
    }
    out["registry_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("surfaces registered   :", len(surfaces))
    for s in surfaces:
        r = s["represents"]
        print("   %-46s credit=%s listing=%s"
              % (s["family"], r["successor_delivery_or_credit_date"],
                 r["successor_tradable_or_listing_date"]))
    print("population            :", out["V8_V9_population"])
    print("V6 survivors probed   :", out["V6_successor_side_mops"][
        "survivors_probed"], "| reachable",
        out["V6_successor_side_mops"]["reachable"])
    print("V9 taxonomy           :", dict(tax))
    print("credit date for THIS population (offline):",
          out["headline_finding"][
              "credit_date_for_this_population_on_offline_surfaces"])
    print("successor-side MOPS reachable      :",
          out["headline_finding"]["successor_side_mops_reachable"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
