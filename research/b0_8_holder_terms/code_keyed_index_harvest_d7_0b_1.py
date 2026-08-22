# -*- coding: utf-8 -*-
"""B0.8 · D7.0b-1 · MOPS v2 code-keyed index harvest, full history, 39/39.

WHAT WAS ASSERTED AND WHAT WAS ACTUALLY DEMONSTRATED

D6.1 recorded route R2 (POST /mops/api/t05st01) as SERVING this population, and
it does: 171 of 189 requests answered 200. But every one of D6.1's 781 document
records carries `discovered_by: date_keyed_sweep`. The code-keyed route was used
for a discovery-CONFORMANCE check and its rows were filtered to the frozen
[C-30d, C+40d] discovery window; its row yield as a HARVEST was never
demonstrated. The 39 UNIQUE securities hold 189 index rows between them --
4.8 rows per company -- which is plainly not a listed company's announcement
history. D7.0b-1 demonstrates the harvest.

NO WINDOW IS CHOSEN HERE

The sweep runs the full year range the source itself serves, per security, from
the source floor up to the year after the canonical boundary. That is not a
window decision: it is the complete source population for that company. The
point of D7.0b-1 is precisely to stop the corpus being shaped by a window, so
that D7.0b-3 can verify same-transaction membership against everything the
source has rather than against a slice.

    year = "all" is rejected by the API (code 500), so the sweep is per-year.
    Probed floor: ROC 85 -> 406, ROC 86+ -> 200. The floor is recorded, not
    assumed.

VOCABULARY IS DERIVED FROM THE HARVEST, NOT FROM WHAT WAS ALREADY SEEN

The seven document classes were frozen by adjudication BEFORE any subject line
was inspected. The Chinese vocabulary that maps onto them is a separate matter:
four settlement-class subjects were already visible in D7.0a's post-C listing,
so writing the vocabulary from memory of those four would be keyword-fitting.
Instead this stage harvests first, enumerates the whole corpus's subject
vocabulary second, and maps third -- and it emits the frequency-ranked
vocabulary alongside the mapping so the mapping can be audited against what the
corpus actually says rather than against four remembered examples.

8913 IS NOT A SELECTOR

It is swept as one of 39 under rules that mention no security. Its result
appears in a separated post-hoc impact diagnostic.

WHAT THIS STAGE MAY NOT DO

    * no body acquisition -- D7.0b-2 closed the MOPS body routes for this
      population, so only index rows exist to harvest
    * no same-transaction determination -- that is D7.0b-3, and date proximity
      may never establish it on its own
    * no value extraction, no schema change, no CA ledger write

    python research/b0_8_holder_terms/code_keyed_index_harvest_d7_0b_1.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402

CENSUS_D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_0b_v2_index")
RAW_D61 = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                       "document_census_raw", "v2_code_keyed")
OUT = os.path.join(HERE, "code_keyed_index_harvest_d7_0b_1.json")

API = "https://mops.twse.com.tw/mops/api/t05st01"
V2H = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
       "Referer": "https://mops.twse.com.tw/mops/"}
POLITE = 0.35
ROC_FLOOR = 86                      # probed: 85 -> 406, 86+ -> 200
UNIQUE = "STATIC_EVENT_DOCUMENT_UNIQUE"
IMPACT_DIAGNOSTIC_ONLY = "8913"

# Frozen by adjudication before any subject line was read. The mapping
# vocabulary below is provisional and is emitted with the corpus vocabulary so
# it can be audited; the CLASS SET is not provisional.
DOCUMENT_CLASSES = (
    "CASH_CONSIDERATION_PAYMENT",
    "SHARE_CONVERSION_SETTLEMENT",
    "SUCCESSOR_SHARE_ISSUANCE",
    "SUCCESSOR_SHARE_CREDIT",
    "NEW_SHARE_LISTING_OR_TRADING",
    "FRACTIONAL_CASH_IN_LIEU",
    "TRANSACTION_COMPLETION",
)

# Institutional vocabulary. Deliberately generic: none of these terms names a
# company, a counterparty, a transaction or a date.
CLASS_TERMS = {
    "CASH_CONSIDERATION_PAYMENT": ("對價款", "現金對價", "價款發放", "發放日",
                                   "收購價款", "現金給付", "價金給付",
                                   "對價發放"),
    "SHARE_CONVERSION_SETTLEMENT": ("股份轉換", "換股", "轉換基準日",
                                    "換發基準", "股份交換"),
    "SUCCESSOR_SHARE_ISSUANCE": ("發行新股", "換發新股", "配發新股",
                                 "增資發行新股", "新股發行"),
    "SUCCESSOR_SHARE_CREDIT": ("開始換發", "撥入", "帳簿劃撥", "存入集保",
                               "劃撥交付", "換發作業"),
    "NEW_SHARE_LISTING_OR_TRADING": ("開始櫃檯買賣", "開始上市買賣",
                                     "上市買賣日", "上櫃買賣日", "掛牌買賣",
                                     "開始買賣"),
    "FRACTIONAL_CASH_IN_LIEU": ("不足一股", "畸零股", "零股", "現金補償",
                                "按面額"),
    "TRANSACTION_COMPLETION": ("完成股份轉換", "完成合併", "合併完成",
                               "交易完成", "轉換案", "合併案"),
}

BIGRAM = re.compile(r"[一-鿿]{2,6}")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _write(path, raw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def fetch_year(sid, ad_year):
    """One (security, year) index page. D6.1's cache is reused read-only."""
    name = "%s_%d.json" % (sid, ad_year)
    for base in (RAW, RAW_D61):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return open(p, "rb").read(), "cache:%s" % os.path.basename(base)
    payload = {"companyId": sid, "year": str(ad_year - 1911), "month": "all",
               "firstDay": "", "lastDay": ""}
    err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                         headers=V2H)
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
            _write(os.path.join(RAW, name), raw)
            time.sleep(POLITE)
            return raw, "network"
        except Exception as exc:                            # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, str(exc)[:120])
            time.sleep(1.5 * (attempt + 1))
    return None, err


def classify(subject):
    hits = [c for c in DOCUMENT_CLASSES
            if any(t in subject for t in CLASS_TERMS[c])]
    return hits


def main() -> int:
    d66 = json.load(open(CENSUS_D66, encoding="utf-8"))
    uniq = [r for r in d66["results"] if r["classification"] == UNIQUE]
    assert len(uniq) == 39, len(uniq)

    rows_by_sid = defaultdict(dict)
    year_log, errors = [], []
    for i, r in enumerate(sorted(uniq, key=lambda x: x["canonical_event_date"]),
                          1):
        sid = r["security_id"]
        c = date.fromisoformat(r["canonical_event_date"])
        years = list(range(ROC_FLOOR + 1911, c.year + 2))
        got = 0
        for y in years:
            raw, how = fetch_year(sid, y)
            if raw is None:
                errors.append({"security_id": sid, "year": y, "error": how})
                continue
            try:
                js = json.loads(raw.decode("utf-8", "replace"))
            except Exception as exc:                        # noqa: BLE001
                errors.append({"security_id": sid, "year": y,
                               "error": "unparseable %s" % exc})
                continue
            data = (js.get("result") or {}).get("data") or []
            year_log.append({"security_id": sid, "year": y,
                             "code": js.get("code"), "rows": len(data),
                             "source": how, "raw_sha256": _sha(raw)})
            for row in data:
                try:
                    co, _abbr, roc_d, tm, subj, params = row[:6]
                except ValueError:
                    continue
                if str(co) != sid:
                    continue
                m = re.match(r"(\d{2,3})/(\d{2})/(\d{2})", str(roc_d))
                if not m:
                    continue
                when = date(int(m.group(1)) + 1911, int(m.group(2)),
                            int(m.group(3)))
                p = (params or {}).get("parameters", {})
                key = "%s|%s|%s|%s" % (sid, when.isoformat(),
                                       str(tm).replace(":", ""),
                                       p.get("serialNumber", ""))
                rows_by_sid[sid][key] = {
                    "publication_date": when.isoformat(),
                    "days_from_canonical_event_date": (when - c).days,
                    "subject": subj or "",
                    "market_kind": p.get("marketKind"),
                    "enter_date": p.get("enterDate"),
                    "serial_number": p.get("serialNumber"),
                    "document_classes": classify(subj or ""),
                }
                got += 1
        print("  [%2d/39] %-5s C=%s years=%d rows=%d"
              % (i, sid, c.isoformat(), len(years), len(rows_by_sid[sid])),
              flush=True)

    # ---- corpus vocabulary, enumerated from the harvest ---------------------
    vocab = Counter()
    for sid, rows in rows_by_sid.items():
        for rec in rows.values():
            vocab.update(set(BIGRAM.findall(rec["subject"])))

    per_event, class_counts, class_lags = [], Counter(), defaultdict(list)
    for r in sorted(uniq, key=lambda x: x["canonical_event_date"]):
        sid = r["security_id"]
        rows = sorted(rows_by_sid[sid].values(),
                      key=lambda x: x["publication_date"])
        classed = [x for x in rows if x["document_classes"]]
        for x in classed:
            for c in x["document_classes"]:
                class_counts[c] += 1
                class_lags[c].append(x["days_from_canonical_event_date"])
        per_event.append({
            "event_id": r["event_id"], "security_id": sid,
            "canonical_event_date": r["canonical_event_date"],
            "index_rows_harvested": len(rows),
            "rows_matching_a_frozen_class": len(classed),
            "classes_present": sorted({c for x in classed
                                       for c in x["document_classes"]}),
            "class_matched_rows": classed,
        })

    d61_rows = 189
    harvested = sum(len(v) for v in rows_by_sid.values())
    events_with_class = sum(1 for e in per_event
                            if e["rows_matching_a_frozen_class"])
    impact = next((e for e in per_event
                   if e["security_id"] == IMPACT_DIAGNOSTIC_ONLY), None)

    out = {
        "record": "B0_8_D7_0B_1_CODE_KEYED_INDEX_HARVEST",
        "b0_8_state": "WIP, UNSEALED",
        "population": "39/39 D6.6 UNIQUE events, uniform, no sampling",
        "route": "R2 POST /mops/api/t05st01, code-keyed, per year",
        "year_all_rejected_by_api": True,
        "roc_floor_probed": {"roc_85": 406, "roc_86_and_above": 200},
        "sweep_rule": ("ROC floor .. year after the canonical boundary, per "
                       "security; the complete source population, not a window"),
        "window_defined_or_changed": False,
        "d6_1_code_keyed_rows_for_these_39": d61_rows,
        "d7_0b_1_rows_harvested": harvested,
        "harvest_multiple_vs_d6_1": round(harvested / max(d61_rows, 1), 1),
        "year_requests": len(year_log),
        "year_request_errors": len(errors),
        "events_with_at_least_one_frozen_class_row": events_with_class,
        "frozen_class_row_counts": {c: class_counts.get(c, 0)
                                    for c in DOCUMENT_CLASSES},
        "frozen_class_lag_summary": {
            c: {"n": len(v), "min": min(v), "median": sorted(v)[len(v) // 2],
                "max": max(v),
                "after_C": sum(1 for x in v if x > 0)}
            for c, v in sorted(class_lags.items()) if v},
        "document_classes_frozen_before_any_subject_was_read": list(
            DOCUMENT_CLASSES),
        "class_terms_provisional": {c: list(v)
                                    for c, v in CLASS_TERMS.items()},
        "class_terms_are_provisional_note": (
            "the CLASS SET is frozen; the Chinese terms are provisional and are "
            "published here beside the corpus vocabulary so the mapping can be "
            "audited against what the corpus says rather than against the four "
            "subjects already visible in D7.0a"),
        "corpus_subject_vocabulary_top_120": vocab.most_common(120),
        "body_acquisition_attempted": False,
        "body_routes_closed_by": "D7.0b-2 "
                                 "MOPS_BODY_ROUTES_CLOSED_FOR_THIS_POPULATION",
        "same_transaction_determined": False,
        "post_hoc_impact_diagnostic_8913": impact,
        "year_log": year_log,
        "errors": errors,
        "results": per_event,
        # invariants
        "values_extracted": False,
        "holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "dual_extraction_started": False,
    }
    out["harvest_sha256"] = canonical_sha256(
        {k: v for k, v in out.items()
         if k not in ("results", "year_log", "post_hoc_impact_diagnostic_8913")})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nD6.1 code-keyed rows for these 39 :", d61_rows)
    print("D7.0b-1 rows harvested            :", harvested,
          "(x%.1f)" % out["harvest_multiple_vs_d6_1"])
    print("year requests / errors            : %d / %d"
          % (len(year_log), len(errors)))
    print("events with a frozen-class row    : %d / 39" % events_with_class)
    print("class row counts                  :",
          json.dumps(out["frozen_class_row_counts"], ensure_ascii=False))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
