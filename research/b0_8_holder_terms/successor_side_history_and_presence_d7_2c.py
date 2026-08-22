# -*- coding: utf-8 -*-
"""B0.8 · D7.2c · X6/X7/X8 · SUCCESSOR-SIDE MOPS FULL HISTORY, LINKAGE, PRESENCE.

For every event whose successor has an established DOMESTIC security id (D7.2b),
this stage does three separable things and keeps them separable:

X6 · ENUMERATE THE FULL SUCCESSOR-SIDE MOPS HISTORICAL INDEX
    The MOPS 歷史重大訊息 index (ajax_t05st01) is queried per ROC year across ONE
    fixed range applied identically to every successor -- deliberately NOT a
    window centred on the event date. Every announcement row (date + subject +
    its own detail key) is enumerated; the full index size per successor is
    reported. Candidate discovery uses generic transaction vocabulary only.

X7 · ESTABLISH SAME-TRANSACTION LINKAGE SEPARATELY
    A successor-side announcement joins the event bundle ONLY when its own body
    names the disappearing issuer -- by full legal name, by a distinctive stem of
    that legal name, or by the disappearing security code. Same successor issuer,
    generic 新股/換股 wording, a nearby date or a plausible ratio are NOT
    sufficient on their own and never establish linkage here.

X8 · PRESENCE ONLY, NEVER VALUES
    For each linked successor-side body, report only whether the authoritative
    text CONTAINS each field: successor delivery/credit date, successor tradable/
    listing date, stock-conversion ratio, transaction effective date, fractional-
    share treatment. No value is materialised. The credit vs listing distinction
    is preserved: a listing/tradable field is never read as a credit field.

Runs against the live MOPS survivor surface (D7.0b-2's refusal was the delisted
disappearing issuer; the survivor is public). All raw responses are cached under
artifacts so a rerun performs no network and the evidence is preserved.

    python research/b0_8_holder_terms/successor_side_history_and_presence_d7_2c.py
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
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256          # noqa: E402

D72B = os.path.join(HERE, "domestic_security_routing_d7_2b.json")
D71A = os.path.join(HERE, "stock_leg_population_d7_1a.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_2c_mops_raw")
OUT = os.path.join(HERE, "successor_side_history_and_presence_d7_2c.json")

AJAX = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
H = {"User-Agent": "Mozilla/5.0",
     "Content-Type": "application/x-www-form-urlencoded",
     "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01"}
POLITE = 0.35

# ONE fixed enumeration range, applied identically to every successor.
YEARS = list(range(90, 114))                                  # ROC 90..113

# generic transaction vocabulary for candidate discovery (X6)
TXN_VOCAB = ("合併", "股份轉換", "概括承受", "受讓", "讓與", "收購",
             "存續", "消滅", "換股", "換發", "轉換股份")
# routine consolidated-accounting subjects also contain 合併 (合併營收/合併財報);
# they are never M&A announcements. Excluded from candidates to avoid fetching a
# company's entire monthly-revenue history -- this narrows fetches, never recall,
# because a genuine merger subject carries none of these accounting words.
ACCOUNTING_NOISE = ("營收", "營業收入", "財務報表", "合併報表", "財報",
                    "自結", "損益", "資產負債表", "現金流量", "個體",
                    "合併財務", "月營收")
# X8 presence label sets. THREE distinct date objects are kept strictly apart,
# because the same verb (撥付/帳簿劃撥) means "deliver new shares" in a share
# exchange but "pay cash consideration" in a public tender offer. Conflating them
# would promote a cash-leg disbursement date into the frozen stock-leg successor-
# share credit field -- the exact cross-object promotion X8/X9 forbid.
SHARE_DELIVERY_LABELS = ("帳簿劃撥", "配發交付", "劃撥配發", "配發基準日",
                         "換發基準日", "撥入", "交付新股", "新股配發")
CASH_DISBURSEMENT_LABELS = ("撥付", "對價", "匯入", "收購價款", "領取價款",
                            "現金對價")
LISTING_LABELS = ("上市日期", "上櫃日期", "上市(櫃)日期", "新股上市",
                  "開始買賣", "掛牌", "新股掛牌")
RATIO_LABELS = ("換股比例", "換票比率", "轉換比例", "股份轉換比例",
                "換發比例", "合併換股比例")
EFFECTIVE_LABELS = ("基準日", "轉換基準日", "合併基準日", "股份轉換基準日",
                    "事實發生日")
FRACTIONAL_LABELS = ("不足一股", "畸零股", "零股", "未滿一股", "不足壹股")

ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
SUBJ = re.compile(r"font size='3'>&nbsp;([^<]{2,80})</font>")
DATEC = re.compile(r"&nbsp;(\d\d/\d\d/\d\d)")
SEQ = re.compile(r"seq_no\.value='(\d+)'")
STIME = re.compile(r"spoke_time\.value='(\d+)'")
SDATE = re.compile(r"spoke_date\.value='(\d+)'")
TYPEK = re.compile(r"TYPEK\.value='(\w+)'")


def _cache_read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def _cache_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# MOPS refuses history for an issuer that later ceased public issuance / delisted
# -- the survivor-side analogue of D7.0b-2's disappearing-issuer refusal.
UNAVAILABLE_MARKERS = ("不繼續公開發行", "無此公司", "查無資料", "未公開發行",
                       "無資料")


def post(data, cache_path, tries=4):
    cached = _cache_read(cache_path)
    if cached is not None:
        return cached, True
    body = urllib.parse.urlencode(data).encode()
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(AJAX, data=body, headers=H)
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read().decode("utf-8", "replace")
            _cache_write(cache_path, raw)
            time.sleep(POLITE)
            return raw, False
        except Exception as exc:                              # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise last


def enum_year(co_id, year):
    """One year of the successor's historical announcement index (X6)."""
    cp = os.path.join(RAW, "idx_%s_%d.html" % (co_id, year))
    raw, hit = post({"encodeURIComponent": "1", "step": "1", "firstin": "true",
                     "off": "1", "TYPEK": "all", "co_id": co_id,
                     "year": str(year), "month": ""}, cp)
    if any(m in raw for m in UNAVAILABLE_MARKERS):
        return [], hit, False
    rows = []
    for block in ROW.findall(raw):
        s = SUBJ.search(block)
        if not s:
            continue
        d = DATEC.search(block)
        seq, st, sd, tk = (SEQ.search(block), STIME.search(block),
                           SDATE.search(block), TYPEK.search(block))
        rows.append({
            "subject": s.group(1).strip(),
            "date": d.group(1) if d else "",
            "seq_no": seq.group(1) if seq else None,
            "spoke_time": st.group(1) if st else None,
            "spoke_date": sd.group(1) if sd else None,
            "typek": tk.group(1) if tk else None,
        })
    return rows, hit, True


def fetch_body(co_id, row):
    """One announcement body (X7/X8 input)."""
    if not (row["seq_no"] and row["spoke_date"] and row["typek"]):
        return None
    cp = os.path.join(RAW, "body_%s_%s_%s.html" % (
        co_id, row["spoke_date"], row["seq_no"]))
    raw, _hit = post({"step": "2", "firstin": "true", "TYPEK": row["typek"],
                      "co_id": co_id, "seq_no": row["seq_no"],
                      "spoke_date": row["spoke_date"],
                      "spoke_time": row["spoke_time"] or ""}, cp)
    txt = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", txt).replace("", "")


def linkage(body, disp_code, disp_name, disp_stem):
    """X7 · authoritative same-transaction evidence: the disappearing issuer
    named by legal name, distinctive stem, or security code."""
    ev = []
    if disp_name and disp_name in body:
        ev.append("DISAPPEARING_LEGAL_NAME")
    elif disp_stem and len(disp_stem) >= 2 and disp_stem in body:
        ev.append("DISAPPEARING_NAME_STEM")
    if re.search(r"(?:代號|代碼)[：:\s]*" + re.escape(disp_code), body):
        ev.append("DISAPPEARING_SECURITY_CODE")
    return ev


def presence(body):
    has = lambda labels: sorted({l for l in labels if l in body})
    is_tender = "公開收購" in body
    is_share_exchange = any(x in body for x in
                            ("股份轉換", "合併", "換股", "換發新股", "換發"))
    share_lab = has(SHARE_DELIVERY_LABELS)
    cash_lab = has(CASH_DISBURSEMENT_LABELS)
    # successor-SHARE credit only in a share-exchange context that is not a tender
    share_credit = bool(share_lab) and is_share_exchange and not is_tender
    # cash disbursement only in a tender-offer context (a cash-leg object)
    cash_disb = bool(cash_lab) and is_tender
    return {
        # the frozen stock-leg field
        "SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD": share_credit,
        "SUCCESSOR_TRADABLE_OR_LISTING_DATE_FIELD": bool(has(LISTING_LABELS)),
        "STOCK_CONVERSION_RATIO_FIELD": bool(has(RATIO_LABELS)),
        "TRANSACTION_EFFECTIVE_DATE_FIELD": bool(has(EFFECTIVE_LABELS)),
        "FRACTIONAL_SHARE_TREATMENT_FIELD": bool(has(FRACTIONAL_LABELS)),
        # reported separately, NEVER counted as stock-leg successor credit
        "CASH_CONSIDERATION_DISBURSEMENT_FIELD_cash_leg": cash_disb,
        "_doc_type": ("TENDER_OFFER" if is_tender
                      else "SHARE_EXCHANGE" if is_share_exchange else "OTHER"),
        "_labels_seen": {"share_delivery": share_lab, "cash_disbursement":
                         cash_lab, "listing": has(LISTING_LABELS),
                         "ratio": has(RATIO_LABELS),
                         "effective": has(EFFECTIVE_LABELS),
                         "fractional": has(FRACTIONAL_LABELS)},
    }


def taxonomy(sec_status, linked_docs, history_available=True, error=None):
    if sec_status == "FOREIGN_OR_NON_ROC_SUCCESSOR":
        return "FOREIGN_SUCCESSOR_ROUTE_REQUIRED"
    if sec_status == "DOMESTIC_ENTITY_NO_PUBLIC_SECURITY":
        return "DOMESTIC_NON_ISSUER_NO_SUCCESSOR_SIDE_SECURITY_ROUTE"
    if sec_status == "SUCCESSOR_SECURITY_ROUTING_UNRESOLVED":
        return "SUCCESSOR_SECURITY_ROUTING_UNRESOLVED"
    if error:
        return "ACQUISITION_ERROR"
    if not history_available:
        return "SUCCESSOR_SIDE_MOPS_HISTORY_UNAVAILABLE_ISSUER_NO_LONGER_PUBLIC"
    if not linked_docs:
        return "EVENT_LINKED_SUCCESSOR_DOCS_NOT_FOUND_ON_TESTED_AUTHORITATIVE_ROUTE"
    credit = any(d["presence"]["SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD"]
                 for d in linked_docs)
    listing = any(d["presence"]["SUCCESSOR_TRADABLE_OR_LISTING_DATE_FIELD"]
                  for d in linked_docs)
    if credit and listing:
        return "BOTH_CREDIT_AND_TRADABLE_FIELDS_PRESENT"
    if credit:
        return "SUCCESSOR_CREDIT_FIELD_PRESENT"
    if listing:
        return "SUCCESSOR_TRADABLE_FIELD_PRESENT_ONLY"
    return "EVENT_LINKED_SUCCESSOR_DOCS_PRESENT_NO_RELEVANT_DATE_FIELD"


def main() -> int:
    d72b = json.load(open(D72B, encoding="utf-8"))
    d71a = json.load(open(D71A, encoding="utf-8"))
    disp = {r["security_id"]: (r.get("disappearing_entity") or "")
            for r in d71a["results"]}

    per_event, tax = [], Counter()
    idx_cache = {}                       # co_id -> full index rows (shared survivors)
    total_index, total_bodies, net = 0, 0, 0
    for rec in d72b["per_event"]:
        sid = rec["security_id"]
        sec_status = rec["successor_security_status"]
        succ_code = rec.get("successor_security_id")
        disp_name = disp.get(sid, "")
        disp_stem = re.sub(r"股份有限公司$", "", disp_name)

        if sec_status != "DOMESTIC_SECURITY_ID_ESTABLISHED" or not succ_code:
            t = taxonomy(sec_status, [])
            tax[t] += 1
            per_event.append({
                "security_id": sid, "successor_security_id": succ_code,
                "successor_legal_entity": rec["successor_legal_entity"],
                "successor_security_status": sec_status,
                "mops_full_history_index_rows": 0,
                "transaction_vocab_candidates": 0,
                "same_transaction_linked_docs": [],
                "taxonomy": t, "route_tested": False})
            continue

        # ---- X6 · full-history index (cached; shared survivors reused) ----
        if succ_code not in idx_cache:
            rows, years_hit, avail_years, err = [], 0, 0, None
            try:
                for y in YEARS:
                    yr, hit, avail = enum_year(succ_code, y)
                    rows.extend(yr)
                    years_hit += hit
                    avail_years += 1 if avail else 0
                    if not hit:
                        net += 1
            except Exception as exc:                          # noqa: BLE001
                err = "%s: %s" % (type(exc).__name__, str(exc)[:140])
            idx_cache[succ_code] = {"rows": rows, "available": avail_years > 0,
                                    "avail_years": avail_years, "error": err}
            print("  %s index: %d rows, %d/%d yrs available%s"
                  % (succ_code, len(rows), avail_years, len(YEARS),
                     " ERROR" if err else ""), flush=True)
        entry = idx_cache[succ_code]
        index_rows, available, err = (entry["rows"], entry["available"],
                                      entry["error"])
        total_index += len(index_rows)

        # ---- candidate discovery (generic vocab) --------------------------
        cands = [r for r in index_rows
                 if any(v in r["subject"] for v in TXN_VOCAB)
                 and not any(n in r["subject"] for n in ACCOUNTING_NOISE)]

        # ---- X7 · linkage + X8 · presence, on candidate bodies -----------
        linked = []
        if available and not err:
            for r in cands:
                try:
                    body = fetch_body(succ_code, r)
                except Exception as exc:                      # noqa: BLE001
                    err = "%s: %s" % (type(exc).__name__, str(exc)[:140])
                    break
                total_bodies += 1
                if not body:
                    continue
                ev = linkage(body, sid, disp_name, disp_stem)
                if not ev:
                    continue
                linked.append({
                    "date": r["date"], "subject": r["subject"],
                    "spoke_date": r["spoke_date"], "seq_no": r["seq_no"],
                    "linkage_evidence": ev,
                    "body_sha256":
                        hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    "presence": presence(body),
                })

        cash_tender = any(
            ld["presence"].get("CASH_CONSIDERATION_DISBURSEMENT_FIELD_cash_leg")
            for ld in linked)
        t = taxonomy(sec_status, linked, available, err)
        tax[t] += 1
        per_event.append({
            "security_id": sid, "successor_security_id": succ_code,
            "successor_legal_entity": rec["successor_legal_entity"],
            "disappearing_entity": disp_name,
            "successor_security_status": sec_status,
            "successor_side_mops_history_available": available,
            "acquisition_error": err,
            "mops_full_history_index_rows": len(index_rows),
            "transaction_vocab_candidates": len(cands),
            "candidate_bodies_fetched": len(cands) if (available and not err)
            else 0,
            "same_transaction_linked_docs": linked,
            "linked_doc_count": len(linked),
            "holder_consideration_appears_cash_tender": cash_tender,
            "taxonomy": t, "route_tested": bool(available and not err)})
        print("  event %s -> %s (index %d, cand %d, linked %d)"
              % (sid, t, len(index_rows), len(cands), len(linked)), flush=True)

    tested = [e for e in per_event if e["route_tested"]]
    unavailable = [e["security_id"] for e in per_event
                   if e["successor_security_status"]
                   == "DOMESTIC_SECURITY_ID_ESTABLISHED"
                   and not e["successor_side_mops_history_available"]]
    out = {
        "record": "B0_8_D7_2C_SUCCESSOR_SIDE_HISTORY_LINKAGE_PRESENCE",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_2b_routing_sha256": d72b["routing_sha256"]},
        "X6_enumeration": {
            "surface": "MOPS 歷史重大訊息 ajax_t05st01 (survivor issuer)",
            "roc_year_range": [YEARS[0], YEARS[-1]],
            "range_is_uniform_not_windowed_on_event_date": True,
            "candidate_vocabulary": list(TXN_VOCAB),
            "distinct_survivors_enumerated": len(idx_cache),
            "total_index_rows_enumerated": total_index,
            "no_silent_cap": "every candidate body was fetched; none dropped",
            "events_with_route_actually_tested": len(tested),
            "domestic_coded_but_history_unavailable": unavailable,
            "history_unavailable_reason": (
                "survivor later ceased public issuance / delisted; MOPS returns "
                "不繼續公開發行, the survivor-side analogue of D7.0b-2's "
                "disappearing-issuer refusal"),
        },
        "X7_linkage_rule": {
            "sufficient": ["disappearing issuer full legal name in body",
                           "distinctive stem of disappearing legal name in body",
                           "disappearing security code labelled in body"],
            "insufficient_alone": ["same successor issuer", "generic 新股/換股",
                                   "nearby date", "plausible ratio",
                                   "market outcome"],
        },
        "X8_presence_rule": {
            "fields": ["SUCCESSOR_DELIVERY_OR_CREDIT_DATE_FIELD",
                       "SUCCESSOR_TRADABLE_OR_LISTING_DATE_FIELD",
                       "STOCK_CONVERSION_RATIO_FIELD",
                       "TRANSACTION_EFFECTIVE_DATE_FIELD",
                       "FRACTIONAL_SHARE_TREATMENT_FIELD"],
            "credit_vs_listing_kept_separate": True,
            "values_materialised": False,
        },
        "network_requests_made": net + total_bodies,
        "total_candidate_bodies_fetched": total_bodies,
        "taxonomy_counts": dict(tax),
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
    out["presence_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nsurvivors enumerated :", len(idx_cache))
    print("index rows total     :", total_index)
    print("candidate bodies     :", total_bodies)
    print("taxonomy             :", dict(tax))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
