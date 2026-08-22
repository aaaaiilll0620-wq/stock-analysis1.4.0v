# -*- coding: utf-8 -*-
"""B0.8 · D8.2A · SUCCESSOR CREDIT-DATE REPRESENTABILITY GATE (Go/No-Go).

One question, one field, a bounded stratified control set:

    is successor_credit_date -- explicit holder SHARE-DELIVERY semantics --
    reproducibly representable on first-party surfaces across vintages, or is
    8420 an isolated case?

This is a GATE, not an adjudication. A NO_GO does not make anything
NOT_RECONSTRUCTIBLE; it redirects the next stage from a 99-event bulk crawl to a
source-family coverage closure.

STRUCTURAL EXCLUSIONS CARRIED IN (C2, not re-litigated here)
    CASH_ONLY settlement acquisition  SUSPENDED -- the frozen consumer has no
                                      pure-cash transition path, so acquiring
                                      settlement_date cannot make those events
                                      reconstructible
    4152 elective MIXED               SCHEMA_OR_EVENT_CLASS_CONFLICT -- no
                                      election path exists in the consumer
    Neither the frozen schema nor the consumer is modified here.

SAMPLING IS BLIND TO THE OUTCOME BEING TESTED
    The control set is selected mechanically: eligible = confirmed holder stock
    consideration + public successor + a first-party route that exists. Within
    each (venue, vintage) stratum events are ordered by security_id and taken in
    order. No event is chosen because credit evidence seemed likely, and 8420 --
    the known positive -- is carried as a control but is NOT allowed to define
    the accepted semantics.

WHAT COUNTS, AND WHAT MAY NEVER SUBSTITUTE
    counts      帳簿劃撥 · 交付新股/新股交付 · 發放新股/新股發放 ·
                換發股份交付 · 配發交付 · 劃撥配發/劃撥交付
    never       新股上市日 · 開始買賣/掛牌 · 合併基準日 · 股份轉換基準日 ·
                any bare 基準日
    plus same-transaction linkage to the disappearing issuer is mandatory.

    python research/b0_8_holder_terms/credit_date_representability_gate_d8_2a.py
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

from core.b0_canonical_hash import canonical_sha256          # noqa: E402
import successor_identity_routing_d7_1b as D71B              # noqa: E402
import successor_side_history_and_presence_d7_2c as CR       # noqa: E402

REG = os.path.join(HERE, "event_register.json")
D80 = os.path.join(HERE, "extraction_readiness_freeze_d8_0.json")
D71A = os.path.join(HERE, "stock_leg_population_d7_1a.json")
D72B = os.path.join(HERE, "domestic_security_routing_d7_2b.json")
D74 = os.path.join(HERE, "residual_consideration_closure_d7_4.json")
D76 = os.path.join(HERE, "disappearing_party_edoc_consideration_d7_6.json")
C2 = os.path.join(HERE, "mixed_consumer_conformance_c2.json")
OUT = os.path.join(HERE, "credit_date_representability_gate_d8_2a.json")

BANDS = (("2004-2009", 2004, 2009), ("2010-2014", 2010, 2014),
         ("2015-2019", 2015, 2019), ("2020-2026", 2020, 2026))
TARGET = 16

# explicit holder share-delivery semantics ONLY
CREDIT_STRICT = re.compile(
    r"帳簿劃撥|劃撥交付|劃撥配發|配發交付|交付新股|新股交付|發放新股|"
    r"新股發放|換發股份[^。]{0,4}?交付|股份交付")
# these may never stand in for a credit date
NEVER = ("新股上市", "上市日期", "上櫃日期", "開始買賣", "掛牌",
         "合併基準日", "股份轉換基準日")

# A bare 帳簿劃撥 token is NOT a credit date. In this corpus it appears far more
# often in two contexts that mean the OPPOSITE or something else entirely:
#   tender deposit  應賣人 ... 以帳簿劃撥方式交存有價證券   (shares go OUT)
#   CB conversion   轉換公司債帳簿劃撥轉換/贖回/賣回申請書  (different action)
# so each match is scope-checked in its own window before it may count.
DISQUALIFY = ("應賣", "交存", "公開收購", "轉換公司債", "可轉債", "債權人",
              "贖回", "賣回", "收購說明書")
DELIVER_VERB = re.compile(r"換發|配發|交付|發放|撥入")
DELIVER_OBJ = re.compile(r"新股|普通股|股份|股票")
HOLDER_SIDE = re.compile(r"股東|持有人|原股東")
WINDOW = 140


def credit_hits(body):
    """Matches that really mean 'successor shares credited to the holder'."""
    out = []
    for m in CREDIT_STRICT.finditer(body):
        lo = max(0, m.start() - WINDOW)
        win = body[lo:m.end() + WINDOW]
        if any(d in win for d in DISQUALIFY):
            continue
        if not (DELIVER_VERB.search(win) and DELIVER_OBJ.search(win)
                and HOLDER_SIDE.search(win)):
            continue
        out.append({"label": m.group(0), "window": win[:180]})
    return out


def stk003_disappearing_names():
    """STK003 also names the DISAPPEARING side (證券名稱 / 消滅公司); D7.1b's
    reader only kept survivor columns, and TWSE linkage needs this one."""
    import shutil
    import tempfile
    import openpyxl
    src = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_0c_tdcc_raw",
                       "SM-STK003.xls")
    tmp = os.path.join(tempfile.gettempdir(), "d8_2a_stk003.xlsx")
    shutil.copyfile(src, tmp)
    ws = openpyxl.load_workbook(tmp, read_only=True, data_only=True).worksheets[0]
    out, header = {}, None
    for row in ws.iter_rows(values_only=True):
        v = ["" if x is None else str(x).strip() for x in row]
        if not header:
            if "證券代號" in v:
                header = {k: i for i, k in enumerate(v) if k}
            continue
        code = v[header["證券代號"]] if "證券代號" in header else ""
        if not re.fullmatch(r"\d{4}", code):
            continue
        full = v[header["消滅公司"]] if "消滅公司" in header else ""
        short = v[header["證券名稱"]] if "證券名稱" in header else ""
        out[code] = {"legal": full.strip(), "short": short.strip()}
    return out


def band_of(year):
    for name, lo, hi in BANDS:
        if lo <= year <= hi:
            return name
    return None


def main() -> int:
    reg = json.load(open(REG, encoding="utf-8"))
    d80 = json.load(open(D80, encoding="utf-8"))
    d71a = json.load(open(D71A, encoding="utf-8"))
    d72b = json.load(open(D72B, encoding="utf-8"))
    d74 = json.load(open(D74, encoding="utf-8"))
    d76 = json.load(open(D76, encoding="utf-8"))
    c2 = json.load(open(C2, encoding="utf-8"))

    eff = {e["security_id"]: e["effective_date"] for e in reg["events"]}
    sem = {e["security_id"]: e["consideration_semantics"]
           for e in d80["per_event"] if e["venue"] == "TPEX"}
    disp_name = {r["security_id"]: (r.get("disappearing_entity") or "")
                 for r in d71a["results"]}

    # successor codes: D7.2b routing + the later upgrades
    succ_code = {}
    for r in d72b["per_event"]:
        if r["successor_security_status"] == "DOMESTIC_SECURITY_ID_ESTABLISHED":
            succ_code[r["security_id"]] = r["successor_security_id"]
    for r in d74["per_event"]:
        if r.get("result") == "STOCK_ONLY_ESTABLISHED" and r.get("survivor_code"):
            succ_code[r["security_id"]] = r["survivor_code"]

    # ---- eligible pool, built mechanically -------------------------------
    pool = []
    for sid, s in sem.items():                       # TPEx stock-bearing
        if s not in ("STOCK_ONLY", "MIXED"):
            continue
        if sid == "4152":                            # C2 schema conflict
            continue
        code = succ_code.get(sid)
        if not code:
            continue
        y = int(eff[sid][:4])
        pool.append({"security_id": sid, "venue": "TPEX", "year": y,
                     "band": band_of(y), "successor_code": code,
                     "disappearing_name": disp_name.get(sid, ""),
                     "stock_basis": "D7.2.1/D7.3/D7.4/D7.6 consideration semantics"})
    stk = D71B.stk003_control()
    stk_names = stk003_disappearing_names()
    tpex_ids = set(sem)
    for e in reg["events"]:                          # TWSE via STK003
        sid = e["security_id"]
        if sid in tpex_ids:
            continue
        c = stk.get(sid)
        if not c or not c.get("survivor_code") or not (
                c.get("exchange_ratio") or "").strip():
            continue
        y = int(e["effective_date"][:4])
        pool.append({"security_id": sid, "venue": "TWSE", "year": y,
                     "band": band_of(y), "successor_code": c["survivor_code"],
                     "disappearing_name": stk_names.get(sid, {}).get("legal", ""),
                     "disappearing_short": stk_names.get(sid, {}).get("short", ""),
                     "stock_basis": "TDCC STK003 換票比率 + 存續公司代號"})
    pool = [p for p in pool if p["band"]]

    # ---- deterministic stratified selection ------------------------------
    strata = defaultdict(list)
    for p in pool:
        strata[(p["venue"], p["band"])].append(p)
    for k in strata:
        strata[k].sort(key=lambda x: x["security_id"])
    controls, i = [], 0
    keys = sorted(strata)
    while len(controls) < TARGET:
        added = False
        for k in keys:
            if i < len(strata[k]) and len(controls) < TARGET:
                controls.append(strata[k][i])
                added = True
        if not added:
            break
        i += 1
    # 8420 is carried as the known control if sampling did not draw it
    if not any(c["security_id"] == "8420" for c in controls):
        c8420 = next((p for p in pool if p["security_id"] == "8420"), None)
        if c8420:
            controls.append({**c8420, "carried_known_control": True})

    # ---- test each control ----------------------------------------------
    results, tax = [], Counter()
    for c in controls:
        sid, code = c["security_id"], c["successor_code"]
        dn = c["disappearing_name"] or ""
        stem = re.sub(r"股份有限公司$", "", dn) or c.get("disappearing_short", "")
        rows, avail_years, err = [], 0, None
        try:
            for y in CR.YEARS:
                yr, _hit, av = CR.enum_year(code, y)
                rows.extend(yr)
                avail_years += 1 if av else 0
        except Exception as exc:                              # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:100])
        if err:
            tax["ACQUISITION_ERROR"] += 1
            results.append({**c, "result": "ACQUISITION_ERROR", "error": err})
            continue
        if avail_years == 0:
            tax["APPLICABLE_SOURCE_ROUTE_EXHAUSTED_NO_CREDIT_FIELD"] += 1
            results.append({**c, "result":
                            "APPLICABLE_SOURCE_ROUTE_EXHAUSTED_NO_CREDIT_FIELD",
                            "note": "successor MOPS history unavailable "
                                    "(issuer no longer public)"})
            continue
        cands = [r for r in rows if any(v in r["subject"] for v in CR.TXN_VOCAB)
                 and not any(n in r["subject"] for n in CR.ACCOUNTING_NOISE)]
        linked, hits = 0, []
        for r in cands:
            body = CR.fetch_body(code, r)
            if not body:
                continue
            same = (dn and dn in body) or (stem and len(stem) >= 2
                                           and stem in body) or re.search(
                r"(?:代號|代碼)[：:\s]*" + re.escape(sid), body)
            if not same:
                continue
            linked += 1
            for h in credit_hits(body):
                hits.append({"subject": r["subject"][:56], "date": r["date"],
                             "label": h["label"], "window": h["window"],
                             "substitutes_rejected": [n for n in NEVER
                                                      if n in body]})
        if hits:
            res = "CREDIT_DATE_FIELD_PRESENT"
        elif linked:
            res = "EVENT_LINKED_DOCS_PRESENT_NO_CREDIT_FIELD"
        else:
            res = "APPLICABLE_SOURCE_ROUTE_EXHAUSTED_NO_CREDIT_FIELD"
        tax[res] += 1
        results.append({**c, "result": res, "index_rows": len(rows),
                        "candidates": len(cands), "linked_docs": linked,
                        "credit_hits": hits[:3]})
        print("  %-5s %-5s %-9s succ=%-5s -> %-46s linked=%d hits=%d"
              % (sid, c["venue"], c["band"], code, res, linked, len(hits)),
              flush=True)

    positives = [r for r in results if r["result"] == "CREDIT_DATE_FIELD_PRESENT"]
    pos_vintages = sorted({r["band"] for r in positives})
    pos_beyond_8420 = [r for r in positives if r["security_id"] != "8420"]
    go = len(pos_vintages) >= 2 and len(pos_beyond_8420) >= 2

    out = {
        "record": "B0_8_D8_2A_CREDIT_DATE_REPRESENTABILITY_GATE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"c2_conformance_sha256": c2["conformance_sha256"],
                   "d8_0_freeze_sha256": d80["freeze_sha256"]},
        "structural_exclusions_carried": {
            "CASH_ONLY_settlement_acquisition": "SUSPENDED",
            "reason": c2["beyond_C2_material_finding"]["finding"],
            "4152": "SCHEMA_OR_EVENT_CLASS_CONFLICT",
            "schema_or_consumer_modified": False,
        },
        "sole_question": "is successor_credit_date reproducibly representable "
                         "across vintages on first-party surfaces?",
        "sampling": {
            "eligible_pool": len(pool),
            "eligibility": ["confirmed holder stock consideration",
                            "public successor security",
                            "first-party historical route exists"],
            "stratification": [b[0] for b in BANDS],
            "selection_rule": "within each (venue, band) stratum order by "
                              "security_id and take in order; round-robin across "
                              "strata until the target size",
            "blind_to_expected_credit_availability": True,
            "8420_carried_as_known_control_not_semantics_definer": True,
            "controls_selected": len(controls),
            "by_stratum": {"%s|%s" % k: len(v) for k, v in sorted(strata.items())},
        },
        "credit_semantics": {
            "accepted_regex": CREDIT_STRICT.pattern,
            "scope_disqualifiers": list(DISQUALIFY),
            "requires_in_window": ["delivery verb", "share object", "holder side"],
            "why_scope_check": ("a bare 帳簿劃撥 is most often tender-deposit "
                                "(shares going OUT) or convertible-bond "
                                "conversion, neither of which is a successor "
                                "share credit"),
            "never_substituted": list(NEVER),
            "same_transaction_linkage_required": True,
        },
        "results_taxonomy": dict(tax),
        "positives": [{"security_id": r["security_id"], "venue": r["venue"],
                       "band": r["band"], "successor_code": r["successor_code"],
                       "hits": r.get("credit_hits")} for r in positives],
        "positive_vintages": pos_vintages,
        "positives_beyond_known_control": [r["security_id"]
                                           for r in pos_beyond_8420],
        "GATE": ("MULTI_VINTAGE_REPRESENTABILITY_ESTABLISHED" if go
                 else "NOT_ESTABLISHED_BEYOND_ISOLATED_CONTROL"),
        "BULK_STOCK_ACQUISITION": "GO" if go else "NO_GO",
        "no_go_does_not_establish_global_not_reconstructible": True,
        "next_stage_if_no_go": "source-family coverage/semantics closure for "
                               "successor_credit_date, NOT a 99-event bulk crawl",
        "per_control": results,

        # invariants
        "twse_99_bulk_acquisition_started": False,
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "schema_modified": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "dual_extraction_started": False,
    }
    out["gate_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\neligible pool      :", len(pool), "| controls:", len(controls))
    print("taxonomy           :", dict(tax))
    print("positive vintages  :", pos_vintages)
    print("positives beyond 8420:", out["positives_beyond_known_control"])
    print("GATE               :", out["GATE"])
    print("BULK_STOCK_ACQUISITION:", out["BULK_STOCK_ACQUISITION"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
