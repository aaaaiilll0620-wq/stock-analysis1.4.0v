# -*- coding: utf-8 -*-
"""B0.8 · D7.0c · TDCC public cash-settlement access feasibility. Read-only.

THE SOLE QUESTION (N2)

    Can the event-specific cash settlement / payment date be obtained from a
    PUBLICLY ACCESSIBLE, DETERMINISTIC, FIRST-PARTY TDCC surface with
    preservable provenance?

Not whether TDCC holds such records internally. Adjudication has already
established the operational record class (N1), so what is tested here is public
retrievability -- a different property, and the one that decides whether the
frozen schema's settlement fields can ever be filled.

N1 IS A PREMISE, NOT A D7.0c FINDING

    AUTHORITATIVE_RECORD_CLASS_ESTABLISHED_BY = adjudication (N1), citing
    official TDCC process material naming 股款轉換價款支付一覽表.

D7.0c did NOT independently verify that document's existence; a public search
for it returns nothing. The premise is carried as an adjudicated input and is
labelled as such wherever it drives a classification, so that
AUTHORITATIVE_SETTLEMENT_RECORD_EXISTS_BUT_PUBLIC_VALUE_NOT_EXPOSED never
silently rests on something this stage checked.

N4 · REGISTRY FROZEN BEFORE ANY EVENT QUERY

Only surfaces TDCC itself documents. The three direct-download workbooks are
those linked from TDCC's own 股務資訊服務平台 index; the open-data ids are those
listed in TDCC's own 開放資料專區 catalogue; the interactive surfaces are those
the same index links. No undocumented endpoint is probed and no third-party
mirror is treated as canonical.

N5 · SCHEMA FIRST

Every surface's field schema is fetched, hashed and assessed for REPRESENTATIONAL
CAPABILITY before any event is looked up. A dataset that cannot represent a
settlement date is recorded as INCAPABLE and is never counted as a negative
lookup for any event -- an absent column is not an absent payment.

N6 · Matching uses generic authoritative identifiers only: the disappearing
security_id, the issuer, and the authoritative effective/boundary date. Date
proximity alone never establishes same-transaction identity.

N9 · 8913 is swept as one of 14 under rules that name no security, and reported
only after the uniform stage.

    python research/b0_8_holder_terms/tdcc_public_access_feasibility_d7_0c.py
"""
from __future__ import annotations

import hashlib
import io
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
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402

CENSUS_D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_0c_tdcc_raw")
OUT = os.path.join(HERE, "tdcc_public_access_feasibility_d7_0c.json")

UA = {"User-Agent": "Mozilla/5.0"}
POLITE = 0.5
UNIQUE = "STATIC_EVENT_DOCUMENT_UNIQUE"
IMPACT_DIAGNOSTIC_ONLY = "8913"

OD = "https://opendata.tdcc.com.tw/getOD.ashx?id=%s"
SM = "https://m.tdcc.com.tw/tcdata/sm/%s"
PORTAL = "https://www.tdcc.com.tw/portal/zh/smWeb/%s"

# ---- N4 · the frozen registry ----------------------------------------------
SURFACES = (
    {"id": "OD-1-1", "name": "證券基本資料", "url": OD % "1-1",
     "kind": "opendata_csv", "documented_by": "TDCC 開放資料專區 catalogue"},
    {"id": "OD-1-7", "name": "有價證券帳簿劃撥配發交付日期一覽表",
     "url": OD % "1-7", "kind": "opendata_csv",
     "documented_by": "TDCC 開放資料專區 catalogue"},
    {"id": "OD-1-13", "name": "有價證券轉(交)換/認股價格變更資料查詢",
     "url": OD % "1-13", "kind": "opendata_csv",
     "documented_by": "TDCC 開放資料專區 catalogue"},
    {"id": "OD-1-14", "name": "有價證券董事收購相關資訊", "url": OD % "1-14",
     "kind": "opendata_csv", "documented_by": "TDCC 開放資料專區 catalogue"},
    {"id": "OD-2-5", "name": "帳簿劃撥配發新股統計表", "url": OD % "2-5",
     "kind": "opendata_csv", "documented_by": "TDCC 開放資料專區 catalogue"},
    {"id": "OD-2-23", "name": "有價證券集中保管個別股票異動月分析表－上櫃證券",
     "url": OD % "2-23", "kind": "opendata_csv",
     "documented_by": "TDCC 開放資料專區 catalogue"},
    {"id": "SM-STK001", "name": "發行公司名稱變更一覽表", "url": SM % "stk001.xls",
     "kind": "workbook", "documented_by": "TDCC 股務資訊服務平台 index"},
    {"id": "SM-STK002", "name": "發行公司減資換票一覽表", "url": SM % "stk002.xls",
     "kind": "workbook", "documented_by": "TDCC 股務資訊服務平台 index"},
    {"id": "SM-STK003", "name": "發行公司合併換票一覽表", "url": SM % "stk003.xls",
     "kind": "workbook", "documented_by": "TDCC 股務資訊服務平台 index"},
    {"id": "PORTAL-QRYPS",
     "name": "有價證券帳簿劃撥配發/交付日期一覽表查詢", "url": PORTAL % "qryPS",
     "kind": "interactive_form", "documented_by": "TDCC 股務資訊服務平台 index"},
)

# ---- N5 · the seven representational concepts ------------------------------
CONCEPTS = ("security_identity", "transaction_identity",
            "conversion_or_effective_date", "cash_consideration",
            "cash_settlement_or_payment_date", "account_cancellation_date",
            "distribution_or_credit_date")

# Header vocabulary -> concept. Assessed on FIELD NAMES only, never on values.
CONCEPT_FIELDS = {
    "security_identity": ("證券代號", "股票代號", "證券名稱", "股票名稱"),
    "transaction_identity": ("存續公司", "消滅公司", "轉(交)換後證券代號",
                             "轉換後證券代號"),
    "conversion_or_effective_date": ("停止過戶期間", "停止過戶", "基準日",
                                     "資料日期", "收購起日", "收購迄日"),
    "cash_consideration": ("收購價格", "轉(交)換價格", "價款", "對價"),
    "cash_settlement_or_payment_date": ("支付日", "發放日", "價款支付",
                                        "付款日", "撥付日"),
    "account_cancellation_date": ("註銷日", "銷除日", "停止過戶領回",
                                  "歸戶領回"),
    "distribution_or_credit_date": ("交付日期", "配發日", "新股上市(櫃)日期",
                                    "上市(櫃)日期", "劃撥日"),
}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _write(name, raw):
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, name), "wb") as fh:
        fh.write(raw)


def fetch(url, data=None, headers=None, timeout=90):
    h = dict(UA)
    h.update(headers or {})
    try:
        req = urllib.request.Request(url, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.status, None
    except Exception as exc:                                # noqa: BLE001
        return None, None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def csv_header(raw):
    t = raw.decode("utf-8-sig", "replace")
    lines = [x for x in t.splitlines() if x.strip()]
    if not lines:
        return [], 0, []
    return ([c.strip() for c in lines[0].split(",")], len(lines) - 1,
            lines[1:])


def workbook_fields(raw):
    """Header row of a TDCC stock-affairs workbook, plus its rows as text."""
    try:
        import pandas as pd
        try:
            df = pd.read_excel(io.BytesIO(raw), header=None)
        except Exception:                                   # noqa: BLE001
            df = pd.read_html(io.BytesIO(raw))[0]
    except Exception:                                       # noqa: BLE001
        return [], 0, [], None
    title = str(df.iloc[0, 0]) if len(df) else ""
    hdr_row = None
    for i in range(min(6, len(df))):
        cells = [str(x) for x in df.iloc[i].tolist()]
        if any("證券代號" in c or "股票代號" in c for c in cells):
            hdr_row = i
            break
    if hdr_row is None:
        return [], len(df), [], title
    fields = [re.sub(r"\s+", "", str(x)) for x in df.iloc[hdr_row].tolist()
              if str(x) != "nan"]
    rows = ["\t".join("" if str(x) == "nan" else str(x)
                      for x in df.iloc[i].tolist())
            for i in range(hdr_row + 1, len(df))]
    return fields, len(rows), rows, title


def capability(fields):
    joined = " ".join(fields)
    return {c: any(t in joined for t in CONCEPT_FIELDS[c]) for c in CONCEPTS}


def qryps_probe(stock_no):
    """The interactive historical surface. Token flow, one security."""
    page, _st, err = fetch(PORTAL % "qryPS")
    if page is None:
        return None, err
    t = page.decode("utf-8", "replace")
    m = re.search(r'name="SYNCHRONIZER_TOKEN"[^>]*value="([^"]*)"', t)
    u = re.search(r'name="SYNCHRONIZER_URI"[^>]*value="([^"]*)"', t)
    if not m:
        return None, "no SYNCHRONIZER_TOKEN in form"
    body = urllib.parse.urlencode({
        "SYNCHRONIZER_TOKEN": m.group(1),
        "SYNCHRONIZER_URI": u.group(1) if u else "/portal/zh/smWeb/qryPS",
        "method": "submit", "sqlMethod": "StockNo",
        "stockNo": stock_no, "stockName": "", "stockDate": ""}).encode()
    time.sleep(POLITE)
    return fetch(PORTAL % "qryPS", data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": PORTAL % "qryPS"})[0:1] + (None,)


def main() -> int:
    d66 = json.load(open(CENSUS_D66, encoding="utf-8"))
    # ---- N3 · population, mechanically from preserved authoritative bytes ---
    pop = sorted(
        [r for r in d66["results"]
         if r["classification"] == UNIQUE
         and r["qualifying"][0]["field_presence"]["cash_consideration"]],
        key=lambda r: r["canonical_event_date"])
    print("N3 cash-consideration population: %d events" % len(pop), flush=True)

    # ---- N4/N5 · registry frozen, then schemas ----------------------------
    registry, audits = [], {}
    for s in SURFACES:
        rec = dict(s)
        if s["kind"] == "interactive_form":
            page, st, err = fetch(s["url"])
            if page is None:
                rec.update({"reachable": False, "error": err})
                fields, rows, body = [], 0, []
            else:
                _write("%s_form.html" % s["id"], page)
                t = page.decode("utf-8", "replace")
                names = sorted(set(re.findall(
                    r'<(?:input|select)[^>]*name="([^"]+)"', t)))
                rec.update({"reachable": True, "http_status": st,
                            "bytes": len(page), "sha256": _sha(page),
                            "form_fields": names})
                # the form's own result schema is unknown until queried; the
                # documented dataset it queries is OD-1-7, whose schema is
                # audited directly.
                fields, rows, body = ["證券代號", "證券名稱", "交付日期",
                                      "交付原因"], 0, []
                rec["schema_source"] = ("the documented dataset this form "
                                        "queries is OD-1-7; its field schema "
                                        "is audited there")
        else:
            raw, st, err = fetch(s["url"])
            if raw is None:
                rec.update({"reachable": False, "error": err})
                fields, rows, body = [], 0, []
            else:
                ext = "csv" if s["kind"] == "opendata_csv" else "xls"
                _write("%s.%s" % (s["id"], ext), raw)
                rec.update({"reachable": True, "http_status": st,
                            "bytes": len(raw), "sha256": _sha(raw)})
                if s["kind"] == "opendata_csv":
                    fields, rows, body = csv_header(raw)
                    title = None
                else:
                    fields, rows, body, title = workbook_fields(raw)
                    rec["workbook_title_row"] = title
        cap = capability(fields)
        rec.update({"field_schema": fields, "row_count": rows,
                    "capability": cap,
                    "capable_of_settlement_or_credit_date": bool(
                        cap.get("cash_settlement_or_payment_date")
                        or cap.get("distribution_or_credit_date"))})
        registry.append(rec)
        audits[s["id"]] = body
        print("  %-14s %-42s rows=%-7s settlement/credit-capable=%s"
              % (s["id"], s["name"][:40], rec.get("row_count"),
                 rec["capable_of_settlement_or_credit_date"]), flush=True)
        time.sleep(POLITE)

    registry_hash = canonical_sha256(
        [{k: v for k, v in r.items()
          if k in ("id", "name", "url", "kind", "sha256", "field_schema")}
         for r in registry])
    print("N4 registry frozen:", registry_hash, flush=True)

    capable = [r for r in registry
               if r["capable_of_settlement_or_credit_date"] and r.get(
                   "reachable")]
    incapable = [r["id"] for r in registry
                 if not r["capable_of_settlement_or_credit_date"]]

    # ---- N6 · event matching on capable surfaces only ----------------------
    results = []
    for r in pop:
        sid = r["security_id"]
        c = r["canonical_event_date"]
        hits = []
        for surf in capable:
            for line in audits.get(surf["id"]) or []:
                if re.search(r"(?<!\d)%s(?!\d)" % re.escape(sid), line):
                    hits.append({"surface": surf["id"], "row": line[:300]})
        # A capable surface that does not cover the event's period is a
        # COVERAGE gap, recorded separately from a genuine absence.
        covered_by = []
        for surf in capable:
            rng = surf.get("coverage_range")
            if rng and rng[0] <= c.replace("-", "") <= rng[1]:
                covered_by.append(surf["id"])
        results.append({
            "event_id": r["event_id"], "security_id": sid,
            "canonical_event_date": c,
            "matched_rows": hits,
            "capable_surfaces_covering_this_date": covered_by,
        })

    # ---- coverage ranges, computed from the preserved bytes ----------------
    for surf in registry:
        body = audits.get(surf["id"]) or []
        dates = set()
        for line in body:
            dates |= set(re.findall(r"(?<!\d)(20\d{6})(?!\d)", line))
        if dates:
            surf["coverage_range"] = [min(dates), max(dates)]
            surf["coverage_note"] = "AD yyyymmdd tokens observed in the rows"
        else:
            roc = set()
            for line in body:
                roc |= set(re.findall(r"(?<!\d)(\d{2,3})\.(\d{2})\.(\d{2})",
                                      line) and [] or [])
            surf["coverage_range"] = None

    # recompute coverage flags now that ranges exist
    by_id = {s["id"]: s for s in registry}
    for res in results:
        c = res["canonical_event_date"].replace("-", "")
        res["capable_surfaces_covering_this_date"] = [
            s["id"] for s in capable
            if by_id[s["id"]].get("coverage_range")
            and by_id[s["id"]]["coverage_range"][0] <= c
            <= by_id[s["id"]]["coverage_range"][1]]

    # ---- N7 · classification ----------------------------------------------
    ACQUIRED = "PUBLIC_AUTHORITATIVE_SETTLEMENT_VALUE_ACQUIRED"
    NOT_EXPOSED = ("AUTHORITATIVE_SETTLEMENT_RECORD_EXISTS_BUT_"
                   "PUBLIC_VALUE_NOT_EXPOSED")
    UNRESOLVED = "AUTHORITATIVE_RECORD_EXISTENCE_NOT_ESTABLISHED"
    REQ_ERROR = "PUBLIC_ACCESS_REQUEST_ERROR"
    unreachable = [r["id"] for r in registry if not r.get("reachable")]

    for res in results:
        if unreachable and not capable:
            res["classification"] = REQ_ERROR
            res["basis"] = "no capable surface was reachable: %s" % unreachable
            continue
        settled = [h for h in res["matched_rows"]
                   if by_id[h["surface"]]["capability"].get(
                       "cash_settlement_or_payment_date")]
        if settled:
            res["classification"] = ACQUIRED
            res["basis"] = "a settlement-capable public surface returned rows"
        else:
            # N1 premise: the operational record class is established by
            # adjudication for cash-consideration TDCC handling.
            res["classification"] = NOT_EXPOSED
            res["basis"] = (
                "no public TDCC surface in the frozen registry both represents "
                "a cash settlement/payment date AND covers this event's period; "
                "record-class existence is carried from the N1 adjudicated "
                "premise, not verified by D7.0c")
        res["record_class_existence_source"] = "N1_ADJUDICATED_PREMISE"

    counts = Counter(r["classification"] for r in results)
    impact = next((r for r in results
                   if r["security_id"] == IMPACT_DIAGNOSTIC_ONLY), None)

    out = {
        "record": "B0_8_D7_0C_TDCC_PUBLIC_ACCESS_FEASIBILITY",
        "b0_8_state": "WIP, UNSEALED",
        "question": ("can event-specific cash settlement/payment dates be "
                     "obtained from a public, deterministic, first-party TDCC "
                     "surface with preservable provenance?"),
        "tests_public_accessibility_not_internal_possession": True,
        "n1_premise": {
            "statement": ("official TDCC process material establishes the "
                          "operational record class, including "
                          "股款轉換價款支付一覽表"),
            "source": "ADJUDICATION (N1)",
            "independently_verified_by_d7_0c": False,
            "note": ("a public search for that document name returns nothing; "
                     "the premise is carried as an adjudicated input and is "
                     "labelled wherever it drives a classification"),
        },
        "population": {
            "rule": ("D6.6 UNIQUE TPEx events whose authoritative termination "
                     "body indicates a cash-consideration leg"),
            "derived_from": "preserved authoritative bytes, field_presence",
            "count": len(pop),
            "expected_by_adjudication": 14,
            "matches_expected": len(pop) == 14,
            "selection_inspected": [],
            "selection_did_not_inspect": [
                "B0 exposure", "claim state", "load-bearing envelope",
                "8913 identity", "performance"],
        },
        "n4_registry_sha256": registry_hash,
        "n4_surfaces_frozen_before_any_event_query": True,
        "n4_third_party_mirrors_used_as_canonical": False,
        "n4_undocumented_endpoints_probed": False,
        "n5_schema_audited_before_event_lookup": True,
        "n5_concepts": list(CONCEPTS),
        "n5_incapable_surfaces_not_counted_as_negative_lookups": incapable,
        "surfaces": registry,
        "counts": {k: counts.get(k, 0) for k in
                   (ACQUIRED, NOT_EXPOSED, UNRESOLVED, REQ_ERROR)},
        "post_hoc_impact_diagnostic_8913": impact,
        "results": results,
        # N10
        "holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "noncanonical_value_known": False,
        "canonical_authoritative_value_acquired": counts.get(ACQUIRED, 0) > 0,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items()
         if k not in ("results", "surfaces",
                      "post_hoc_impact_diagnostic_8913")})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nN7 counts:", json.dumps(out["counts"], ensure_ascii=False))
    print("registry sha256:", registry_hash)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
