# -*- coding: utf-8 -*-
"""B0.8 · a DIAGNOSTIC over the census, for adjudication. Changes nothing.

The census classified 158 events under the frozen D6 predicates. Reading its
output back shows three places where those predicates may be under-inclusive.
This record quantifies each one WITHOUT applying it, because the predicates were
frozen before values were inspected and re-tuning them now -- with the counts
already visible -- is exactly the move the B0.8 policy exists to prevent. The
decision to re-freeze is adjudication's, not this stage's.

    RELAXATION A   the frozen EVENT_MARKERS do not include 終止櫃檯買賣, which
                   is the phrase TPEx-lineage announcements actually use
                   (「公告櫃檯買賣中心核准本公司股票終止櫃檯買賣」).

    RELAXATION B   D6 is applied per DOCUMENT: one document must carry the
                   security, the transaction and the event. In this corpus the
                   linkage is routinely SPLIT -- the termination announcement
                   names no counterparty and the share-transfer announcement
                   names no termination -- across two announcements by the same
                   filer inside the same frozen window.

    RELAXATION C   the exchange itself (臺灣證券交易所股份有限公司, 財團法人中華
                   民國證券櫃檯買賣中心) is matched as a counterparty, because
                   it is a 股份有限公司 standing next to a transaction marker.
                   That is what makes 2 of the 8 AMBIGUOUS events ambiguous.

It reads only preserved bytes. No request is issued.

    python research/b0_8_holder_terms/discovery_sensitivity_diagnostic.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as R          # noqa: E402

CENSUS = os.path.join(HERE, "document_discovery_census.json")
OUT = os.path.join(HERE, "discovery_sensitivity_diagnostic.json")
DOCS = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                    "document_census_raw", "documents")

EXTRA_EVENT_MARKERS = ("終止櫃檯買賣", "終止有價證券櫃檯買賣",
                       "終止在證券商營業處所買賣", "核准本公司股票終止",
                       "終止其股票上市", "終止其股票櫃檯買賣")
MARKET_OPERATORS = ("臺灣證券交易所", "台灣證券交易所", "證券櫃檯買賣中心",
                    "臺灣集中保管結算所", "台灣集中保管結算所")


def main() -> int:
    census = json.load(open(CENSUS, encoding="utf-8"))
    rows = []
    for r in census["results"]:
        for a in r["documents"]:
            path = os.path.join(DOCS, a["document_id"].replace(":", "_")
                                + ".html")
            body = R._plain(open(path, "rb").read().decode("utf-8", "replace"))
            text = a["subject"] if not a.get("body_retrieved") else body
            rows.append((r, a, text))

    ev_a = Counter()
    per_event = {}
    for r, a, text in rows:
        e = per_event.setdefault(r["event_id"], {
            "security_id": r["security_id"],
            "classification": r["classification"],
            "market_lineage": r["market_lineage"],
            "documents": 0, "frozen_event": 0, "extended_event": 0,
            "transaction": 0, "frozen_linking": 0,
            "counterparties_non_operator": set()})
        e["documents"] += 1
        has_ev = bool(a["event_markers"])
        has_extra = any(k in text for k in EXTRA_EVENT_MARKERS)
        has_tx = bool(a["transaction_markers"])
        e["frozen_event"] += has_ev
        e["extended_event"] += (has_ev or has_extra)
        e["transaction"] += has_tx
        e["frozen_linking"] += a["links_security_transaction_and_event"]
        for name in a["transaction_counterparties"]:
            if not any(op in name for op in MARKET_OPERATORS):
                e["counterparties_non_operator"].add(name)
        if has_extra and not has_ev:
            for k in EXTRA_EVENT_MARKERS:
                if k in text:
                    ev_a[k] += 1

    frozen_linking = sum(1 for e in per_event.values() if e["frozen_linking"])
    a_only = sum(1 for e in per_event.values()
                 if not e["frozen_linking"] and e["extended_event"]
                 and e["transaction"] and not e["frozen_event"])
    split = sum(1 for e in per_event.values()
                if not e["frozen_linking"] and e["frozen_event"]
                and e["transaction"])
    split_ext = sum(1 for e in per_event.values()
                    if not e["frozen_linking"] and e["extended_event"]
                    and e["transaction"])
    operator_only = [k for k, e in per_event.items()
                     if e["classification"] == R.DOC_AMBIGUOUS
                     and len(e["counterparties_non_operator"]) == 1]

    out = {
        "record": "B0_8_DISCOVERY_SENSITIVITY_DIAGNOSTIC",
        "status": "DIAGNOSTIC ONLY -- no classification, no census, no data",
        "applies_to_census_sha256": census["census_sha256"],
        "router_sha256": census["router_sha256"],
        "frozen_result": census["counts"],
        "relaxation_A_extended_event_markers": {
            "markers": list(EXTRA_EVENT_MARKERS),
            "documents_the_frozen_set_missed": dict(ev_a),
            "events_that_would_gain_a_linking_document_from_A_alone": a_only,
        },
        "relaxation_B_split_linkage_across_documents": {
            "rule_today": ("one document must carry the security, the "
                           "transaction and the event"),
            "events_with_an_event_document_and_a_transaction_document_but_"
            "no_single_document_carrying_both": split,
            "same_with_extended_event_markers": split_ext,
        },
        "relaxation_C_market_operator_as_counterparty": {
            "operators_matched_as_counterparties": list(MARKET_OPERATORS),
            "ambiguous_events_left_with_exactly_one_non_operator_"
            "counterparty": len(operator_only),
            "event_ids": sorted(operator_only),
        },
        "events_with_a_linking_document_under_the_frozen_rule": frozen_linking,
        "body_availability": {
            "bodies_retrieved": census["document_bodies_retrieved"],
            "bodies_withheld_by_source":
                census["document_bodies_withheld_by_source"],
            "note": ("a withheld body is a refusal, not a transport error; the "
                     "announcement row it belongs to is still preserved and "
                     "hash-bound, but a subject line cannot support the dual "
                     "extraction a later stage would need"),
        },
        "what_this_record_does_not_do": [
            "it does not reclassify any event",
            "it does not re-freeze any predicate",
            "it does not touch the CA ledger, the states or any status",
        ],
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print(json.dumps(out, ensure_ascii=False, indent=1)[:2600])
    print("\nwrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
