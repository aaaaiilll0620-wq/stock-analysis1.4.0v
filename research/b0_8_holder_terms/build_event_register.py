# -*- coding: utf-8 -*-
"""B0.8 / R3 · the repair universe, scoped independently of B0 and of replay.

Every canonical `holder_side_reorganization_exit` with
`reconstruction_status = NOT_RECONSTRUCTIBLE`, corpus-wide. NOT scoped to 8913,
to the price universe, to the 141-period window, to claim-only exposure, or to
what B0.7 happened to encounter -- those are impact diagnostics and are recorded
separately, clearly labelled, and used for nothing.

Nothing in this file reads a holding, a price, a NAV or a replay outcome.

    python research/b0_8_holder_terms/build_event_register.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core import b0_holder_side_terms as ht                    # noqa: E402
from core.b0_canonical_hash import canonical_sha256            # noqa: E402

LEDGER = os.path.join(REPO, "data", "b0", "corporate_actions_ledger.csv")
STATUS = os.path.join(REPO, "data", "b0", "security_status.csv")
OUT = os.path.join(HERE, "event_register.json")


def main() -> int:
    raw = open(LEDGER, "rb").read()
    rows = list(csv.DictReader(open(LEDGER, encoding="utf-8")))
    scope = [r for r in rows
             if r["kind"] == ht.REPAIRABLE_EVENT_KIND
             and r["reconstructibility"] == ht.NOT_RECONSTRUCTIBLE]

    status = {}
    for r in csv.DictReader(open(STATUS, encoding="utf-8")):
        if r.get("status") == "delisted":
            status.setdefault(str(r["stock_id"]), []).append(r)

    events = []
    for r in sorted(scope, key=lambda x: (x["ex_or_effective_date"], x["stock_id"])):
        sid = str(r["stock_id"])
        eff = r["ex_or_effective_date"]
        match = [s for s in status.get(sid, ())
                 if str(s.get("effective_from")) == eff]
        events.append({
            "event_id": "%s|%s|%s" % (sid, r["kind"], eff),
            "security_id": sid,
            "effective_date": eff,
            "source_field": r["source_field"],
            "status_reason": (match[0].get("reason") if match else None),
            "company_name": (match[0].get("name") if match
                             and match[0].get("name") else None),
            "old_reconstruction_status": ht.NOT_RECONSTRUCTIBLE,
            # every terms field is empty in the corpus; recorded so the "before"
            # state is a measurement rather than a recollection
            "terms_fields_present_in_corpus": sorted(
                k for k in ("credit_tradable_date", "new_shares_thousands",
                            "share_multiplier", "cash_per_share",
                            "cash_payment_date")
                if (r.get(k) or "").strip()),
        })

    by_reason = Counter(e["status_reason"] for e in events)
    by_year = Counter(e["effective_date"][:4] for e in events)

    register = {
        "record": "B0_8_HOLDER_SIDE_EVENT_REGISTER",
        "scope": ht.SCOPE,
        "repair_class": ht.REPAIR_CLASS,
        "parent": ht.PARENT,
        "selection": ("every canonical %s with reconstruction_status = %s, "
                      "corpus-wide" % (ht.REPAIRABLE_EVENT_KIND,
                                       ht.NOT_RECONSTRUCTIBLE)),
        "selection_independent_of": [
            "8913", "B0 holdings", "claim-only exposure", "the price universe",
            "the 141-period window", "what B0.7 encountered",
            "whether an event blocks replay", "strategy performance"],
        "ledger": "data/b0/corporate_actions_ledger.csv",
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "ledger_rows_total": len(rows),
        "events_in_scope": len(events),
        "distinct_securities": len({e["security_id"] for e in events}),
        "date_span": [events[0]["effective_date"], events[-1]["effective_date"]],
        "by_status_reason": dict(by_reason),
        "by_year": dict(sorted(by_year.items())),
        "events_with_any_terms_field_populated": sum(
            1 for e in events if e["terms_fields_present_in_corpus"]),
        "policy_schema_sha256": ht.schema_identity()["schema_sha256"],
        "policy_frozen_before_values_inspected": True,
        "events": events,
    }
    register["register_sha256"] = canonical_sha256(
        [e["event_id"] for e in register["events"]])

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(register, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("events in scope                : %d" % register["events_in_scope"])
    print("distinct securities            : %d" % register["distinct_securities"])
    print("date span                      : %s .. %s" % tuple(register["date_span"]))
    print("terms already in corpus        : %d"
          % register["events_with_any_terms_field_populated"])
    print("policy schema sha256           : %s" % register["policy_schema_sha256"])
    print("register sha256                : %s" % register["register_sha256"])
    print("by status reason:")
    for k, v in by_reason.most_common():
        print("   %3d  %s" % (v, k))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
