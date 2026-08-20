# -*- coding: utf-8 -*-
"""B0.8 feasibility gate · can the survivor be discovered from authoritative
sources alone, starting only from what is permitted for a disappearing security?

ONE narrow stage. It extracts no conversion ratio, classifies no event, rebuilds
nothing, inspects no performance and starts no replay. If holder terms happen to
appear in a returned disclosure the raw bytes are preserved and hashed, and the
values are NOT materialised into B0.8 canonical data.

DETERMINISTIC SAMPLE RULE, declared before the selection was computed:

    partition the frozen 158-event register by whether the security's code
    appears in the TWSE authoritative delisting directory
    (openapi /company/suspendListingCsvAndHtml);
    sort each partition ascending by (effective_date, security_id);
    select the element at index floor(n/2) -- the temporal median.

It reads the register, an authoritative directory and an index. It cannot see
B0 holdings, the B0.7 blocker, 8913, survivor availability, ease of
reconstruction or performance.

FROZEN QUERY TEMPLATE, fixed before any request was issued:

  allowed inputs   authoritative disappearing-company name
                   authoritative disappearance date
                   fixed window [effective_date - 365d, effective_date + 30d]
                   fixed entity-neutral MOPS surfaces E1 / E2 below
  forbidden        survivor name or code, TEJ counterparty narrative,
                   holdings, price/NAV, later performance

  E1  POST https://mopsov.twse.com.tw/mops/web/ajax_autoComplete
      firstin=1 TYPEK=all step=1 co_id= funcName=t05st01
      searchtype= inpuType=keyword keyword=<NAME>
  E2  POST https://mopsov.twse.com.tw/mops/web/ajax_t05st01
      step=1 firstin=true off=1 TYPEK=all
      year=<ROC year of eff> month=<month of eff> b_date=e_date=<day of eff>

TEMPLATE CORRECTION, recorded rather than quietly applied. E2 was first
instantiated with b_date/e_date as full dates spanning the window. MOPS rejected
it -- 「年度欄位未輸入,請檢查」 -- so that was a malformed request, not an answer,
and reporting NOT_FEASIBLE from it would have been a claim about my own bug. Two
control queries then fixed the real surface:

    without co_id, MOPS answers 「未指定公司代號時，僅能查詢單日重大訊息」

so the entity-neutral announcement surface exists but is SINGLE-DAY, and
b_date/e_date are day-of-month selects inside a chosen year+month. The corrected
instantiation uses only allowed inputs: the authoritative disappearance date
supplies year, month and day. The window constant is retained in the record
because it defined the original template, but a single-day surface makes the
authoritative event date itself the query.

    python research/b0_8_holder_terms/feasibility_survivor_discovery.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

REGISTER = os.path.join(HERE, "event_register.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "feasibility_raw")
OUT = os.path.join(HERE, "feasibility_survivor_discovery.json")

TWSE_DIRECTORY = "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml"
E1 = "https://mopsov.twse.com.tw/mops/web/ajax_autoComplete"
E2 = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
HEADERS = {"User-Agent": "Mozilla/5.0",
           "Content-Type": "application/x-www-form-urlencoded",
           "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01"}
WINDOW_BACK_DAYS, WINDOW_FWD_DAYS = 365, 30
POLITE = 0.6

FORBIDDEN_QUERY_INPUTS = ("survivor_name", "survivor_code",
                          "tej_counterparty_narrative", "portfolio_holdings",
                          "price_or_nav", "later_performance")


def _post(url: str, params: dict, tag: str) -> tuple[bytes, str]:
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, tag + ".html")
    if os.path.exists(path):
        raw = open(path, "rb").read()
    else:
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(params).encode(), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
        with open(path, "wb") as fh:
            fh.write(raw)
        time.sleep(POLITE)
    return raw, hashlib.sha256(raw).hexdigest()


def _text(raw: bytes) -> str:
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _rows(raw: bytes):
    html = raw.decode("utf-8", "replace")
    out = []
    for tr in re.split(r"<tr", html, flags=re.I)[1:]:
        tds = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))
               .replace("\xa0", " ").replace("&nbsp;", " ").strip()
               for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if (len(tds) >= 5 and re.fullmatch(r"\d{2,7}", tds[0] or "")
                and re.fullmatch(r"\d{2,3}/\d{2}/\d{2}", tds[2] or "")):
            out.append(tds)
    return out


def select() -> tuple[list, dict]:
    reg = json.load(open(REGISTER, encoding="utf-8"))
    d = json.loads(urllib.request.urlopen(TWSE_DIRECTORY, timeout=30)
                   .read().decode("utf-8"))
    name = {str(r["Code"]): r["Company"] for r in d}
    ev = reg["events"]
    parts = {
        "twse_directory": sorted(
            [e for e in ev if e["security_id"] in name],
            key=lambda e: (e["effective_date"], e["security_id"])),
        "not_in_twse_directory": sorted(
            [e for e in ev if e["security_id"] not in name],
            key=lambda e: (e["effective_date"], e["security_id"])),
    }
    picked = []
    for tag, part in parts.items():
        i = len(part) // 2
        e = dict(part[i])
        e["partition"] = tag
        e["partition_size"] = len(part)
        e["selected_index"] = i
        e["authoritative_name"] = name.get(e["security_id"])
        e["authoritative_name_source"] = (
            "TWSE openapi /company/suspendListingCsvAndHtml"
            if e["authoritative_name"] else None)
        picked.append(e)
    return picked, reg


def window(effective: str) -> tuple[str, str]:
    d0 = date.fromisoformat(effective)
    return ((d0 - timedelta(days=WINDOW_BACK_DAYS)).isoformat(),
            (d0 + timedelta(days=WINDOW_FWD_DAYS)).isoformat())


def probe(ev: dict) -> dict:
    sid, eff, nm = ev["security_id"], ev["effective_date"], ev["authoritative_name"]
    wa, wb = window(eff)
    rec = {
        "event_id": ev["event_id"], "security_id": sid, "effective_date": eff,
        "partition": ev["partition"],
        "authoritative_name": nm,
        "authoritative_name_source": ev["authoritative_name_source"],
        "window": [wa, wb],
        "queries": [],
        "third_party_information_required": False,
    }
    if not nm:
        rec["survivor_discoverable"] = False
        rec["blocked_before_query"] = (
            "no authoritative disappearing-company NAME is obtainable for this "
            "security from any authoritative directory identified so far, so "
            "the frozen query template cannot be instantiated at all. The TWSE "
            "delisting directory does not carry it and no TPEx equivalent was "
            "reachable (openapi enumerated, 225 endpoints, none for terminated "
            "companies).")
        rec["survivor_identity_unique"] = None
        return rec

    p1 = dict(firstin="1", TYPEK="all", step="1", co_id="", funcName="t05st01",
              searchtype="", inpuType="keyword", keyword=nm)
    raw1, sha1 = _post(E1, p1, "%s_E1" % sid)
    t1 = _text(raw1)
    rec["queries"].append({
        "surface": "E1 ajax_autoComplete (entity-neutral directory resolution)",
        "params": p1, "raw_sha256": sha1, "bytes": len(raw1),
        "result_count": (0 if not t1 else len(re.findall(r"\d{4,7}", t1))),
        "directory_returned_a_company": bool(t1),
        "text_head": t1[:300]})

    d0 = date.fromisoformat(eff)
    p2 = dict(step="1", firstin="true", off="1", TYPEK="all",
              year=str(d0.year - 1911), month="%02d" % d0.month,
              b_date="%02d" % d0.day, e_date="%02d" % d0.day)
    raw2, sha2 = _post(E2, p2, "%s_E2_singleday" % sid)
    t2, rows = _text(raw2), _rows(raw2)
    rec["queries"].append({
        "surface": ("E2 ajax_t05st01 (entity-neutral, ALL companies, "
                    "single-day: the authoritative disappearance date)"),
        "params": p2, "raw_sha256": sha2, "bytes": len(raw2),
        "result_count": len(rows),
        "rows_head": [r[:5] for r in rows[:10]],
        "text_head": t2[:300]})

    # A result counts ONLY if a returned authoritative document names both the
    # disappearing entity and a surviving/acquiring entity. Merger-related
    # announcements existing is not success.
    linking = []
    for r in rows:
        subject = r[4]
        if nm and nm in subject and r[1] != nm:
            linking.append({"announcer_code": r[0], "announcer_name": r[1],
                            "spoke_date": r[2], "subject": subject})
    rec["linking_documents"] = linking
    survivors = sorted({(x["announcer_code"], x["announcer_name"])
                        for x in linking})
    rec["candidate_survivors"] = [list(s) for s in survivors]
    rec["survivor_discoverable"] = bool(linking)
    rec["survivor_identity_unique"] = (len(survivors) == 1) if linking else None
    return rec


def main() -> int:
    picked, reg = select()
    results = [probe(e) for e in picked]
    for r in results:
        print("  %-6s %s  %-22s discoverable=%s"
              % (r["security_id"], r["effective_date"],
                 r["authoritative_name"] or "(name NOT obtainable)",
                 r["survivor_discoverable"]), flush=True)

    yes = sum(1 for r in results if r["survivor_discoverable"])
    verdict = ("FEASIBLE" if yes == len(results)
               else "NOT_FEASIBLE" if yes == 0 else "PARTIALLY_FEASIBLE")
    out = {
        "record": "B0_8_AUTHORITATIVE_SURVIVOR_DISCOVERY_FEASIBILITY",
        "register_sha256": reg["register_sha256"],
        "sample_rule": ("partition the 158-event register by presence in the "
                        "TWSE authoritative delisting directory; sort each "
                        "partition ascending by (effective_date, security_id); "
                        "select index floor(n/2), the temporal median"),
        "sample_rule_independent_of": [
            "B0 holdings", "the B0.7 blocker identity", "8913",
            "known survivor availability", "ease of reconstruction",
            "eventual performance"],
        "frozen_query_template": {
            "allowed_inputs": ["authoritative disappearing-company name",
                               "authoritative disappearance date",
                               "fixed window [eff-365d, eff+30d]",
                               "fixed entity-neutral MOPS surfaces E1/E2"],
            "forbidden_inputs": list(FORBIDDEN_QUERY_INPUTS),
            "E1": E1, "E2": E2,
            "window_back_days": WINDOW_BACK_DAYS,
            "window_forward_days": WINDOW_FWD_DAYS,
        },
        "authoritative_endpoints_used": [TWSE_DIRECTORY, E1, E2],
        "results": results,
        "AUTHORITATIVE_SURVIVOR_DISCOVERY_SURFACE": verdict,
        "surface_capability_observed_outside_sample": {
            "note": ("Control queries, NOT sampled events, and deliberately "
                     "excluded from the verdict. The E1 directory returned "
                     "'上市金融保險業 2887 台新 新光金' for a name that "
                     "disappeared in 2025, i.e. it can carry an absorbed name "
                     "through to the surviving entity's current code, while it "
                     "returned nothing for a name that disappeared in 2013. A "
                     "wider stage would be needed to establish whether that is "
                     "a recency effect and how far back it reaches."),
            "listed_control_resolves": True,
            "recent_disappeared_name_resolves_to_survivor_code": True,
            "older_disappeared_name_resolves": False,
        },
        "canonical_values_materialized": False,
        "events_classified": 0,
        "ca_ledger_rebuilt": False,
        "states_rebuilt": False,
        "performance_inspected": False,
        "replay_started": False,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nAUTHORITATIVE_SURVIVOR_DISCOVERY_SURFACE = %s" % verdict)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
