# -*- coding: utf-8 -*-
"""B0.8 · D6.2 addendum · the F6 known-good control, run against real bodies.

WHY THIS EXISTS

F6 requires the transport route to be tested against previously AVAILABLE
documents. The primary D6.2 sample drew its BODY_AVAILABLE stratum from the
register's recorded acquisition states -- and the control itself proved those
states wrong. Of the 146 documents recorded as BODY_RETRIEVED, only 56 are real
announcement bodies:

     84   該 NNNN 上市公司已下市！
      6   該 NNNN 上櫃公司已下櫃！
     56   real announcement body (carries the MOPS template marker)

Those are REFUSALS in two dialects the frozen REFUSAL_MARKERS never matched --
it knew 不繼續公開發行 and 查無…, not 已下市 / 已下櫃. Both sampled "available"
documents belong to 9101 and are 已下市 refusals, so the F6 known-good control
was never actually exercised: nothing known-good was in the sample.

This addendum re-runs the SAME frozen protocol (hash below) against the two
documents with the lowest identity hash among the 56 that genuinely carry a
body. It is a control, not a retry: the primary four-document record stands
unchanged, no classification moves, and the 781 are not swept.

D6.1 remains preserved exactly: UNIQUE 17 / AMBIGUOUS 25 / NONE 116
(7 NO_DOCUMENT_DISCOVERED + 109 DOCUMENT_DISCOVERED_BUT_LINKAGE_NOT_ESTABLISHED)
/ ERROR 0. The dialect finding is REPORTED for adjudication and applied to
nothing.

    python research/b0_8_holder_terms/body_transport_control_addendum_d6_2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
import body_transport_feasibility_d6_2 as D62              # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402

SEALED_V14 = os.path.join(HERE, "d6_1_historical",
                          "document_discovery_census_v1_4.json")
PRIMARY = os.path.join(HERE, "body_transport_feasibility_d6_2.json")
FREEZE = os.path.join(HERE, "transport_protocol_freeze_d6_2.json")
OUT = os.path.join(HERE, "body_transport_control_addendum_d6_2.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                   "d6_2_transport_raw", "addendum")

# The dialects the frozen detector missed, named here as a finding only.
UNRECOGNISED_REFUSAL_DIALECTS = ("已下市", "已下櫃")


def main() -> int:
    v14 = json.load(open(SEALED_V14, encoding="utf-8"))
    primary = json.load(open(PRIMARY, encoding="utf-8"))
    protocol = json.load(open(FREEZE, encoding="utf-8"))

    # Recount body availability from the preserved bytes themselves.
    real, dialect = {}, {}
    for did, p in v14["document_provenance"].items():
        if not p.get("body_retrieved"):
            continue
        text = V14._plain(open(os.path.join(REPO, p["preserved_at"]), "rb")
                          .read().decode("utf-8", "replace"))
        if V14.DOCUMENT_TEMPLATE_MARKER in text:
            real[did] = p
        else:
            hit = next((d for d in UNRECOGNISED_REFUSAL_DIALECTS
                        if d in text), "other")
            dialect[did] = hit

    ranked = sorted(real, key=lambda d: hashlib.sha256(d.encode()).hexdigest())
    selected = ranked[:2]
    print("true bodies in register : %d of %d recorded"
          % (len(real), len(real) + len(dialect)))
    for did in selected:
        print("  control:", did,
              hashlib.sha256(did.encode()).hexdigest()[:12], flush=True)

    results = []
    for did in selected:
        co, dt, tm, sq = did.split(":")[1:]
        params = {"serialNumber": sq,
                  "enterDate": "%d%s%s" % (int(dt[:4]) - 1911, dt[4:6], dt[6:]),
                  "marketKind": "sii", "companyId": co}
        flow = D62.Flow()
        flow.bootstrap()
        time.sleep(D62.POLITE)
        flow.context_list(co, int(dt[:4]) - 1911)
        time.sleep(D62.POLITE)
        url, redirect_raw, _err = flow.signed_url(params)
        rec = {"document_id": did, "stratum": "TRUE_BODY_AVAILABLE",
               "previous_body_status": "BODY_AVAILABLE (verified real body)",
               "detail_parameters": params, "transport_attempted": True,
               "signed_url_issued": bool(url), "attempts": []}
        if redirect_raw is not None:
            p = os.path.join(RAW, did.replace(":", "_") + ".P2_redirect.json")
            D62._write(p, redirect_raw)
            rec["redirect_raw_sha256"] = D62._sha(redirect_raw)
            rec["redirect_preserved_at"] = os.path.relpath(p, REPO)
        blob = (url.split("parameters=")[1]
                if url and "parameters=" in url else None)
        ladder = []
        if url:
            ladder.append(("P3", "GET", url, None))
        if blob:
            ladder.append(("P4", "GET", D62.APP + D62.LEGACY_DETAIL_PATH
                           + "?parameters=" + blob, None))
            ladder.append(("P5", "POST", D62.APP + D62.LEGACY_DETAIL_PATH,
                           ("parameters=" + blob).encode()))
        final = None
        for step, method, u, data in ladder:
            hdr = ({"Content-Type": "application/x-www-form-urlencoded"}
                   if data else {})
            raw, e = flow._do(step, method, u, data, hdr)
            state, evidence = D62.classify_response(raw, e)
            entry = {"step": step, "method": method, "state": state,
                     "evidence": evidence,
                     "response_sha256": D62._sha(raw) if raw is not None
                     else None,
                     "bytes": len(raw) if raw is not None else None}
            if raw is not None:
                pth = os.path.join(RAW, "%s.%s.html"
                                   % (did.replace(":", "_"), step))
                D62._write(pth, raw)
                entry["preserved_at"] = os.path.relpath(pth, REPO)
            rec["attempts"].append(entry)
            final = state
            if state == D62.BODY_AVAILABLE:
                break
            time.sleep(D62.POLITE)
        rec["resulting_body_status"] = final
        rec["preserved_original_still_intact"] = (
            D62._sha(open(os.path.join(
                REPO, v14["document_provenance"][did]["preserved_at"]),
                "rb").read())
            == v14["document_provenance"][did]["raw_sha256"])
        results.append(rec)
        print("  %s -> %s" % (did, final), flush=True)

    preserved_ok = all(r["resulting_body_status"] == D62.BODY_AVAILABLE
                       for r in results)
    out = {
        "record": "B0_8_D6_2_F6_KNOWN_GOOD_CONTROL_ADDENDUM",
        "b0_8_state": "WIP, UNSEALED",
        "protocol_sha256": protocol["protocol_sha256"],
        "primary_record_sha256": primary["record_sha256"],
        "primary_record_unchanged": True,
        "finding_unrecognised_refusal_dialects": {
            "documents_recorded_as_body_retrieved": len(real) + len(dialect),
            "verified_real_announcement_bodies": len(real),
            "refusals_recorded_as_bodies": len(dialect),
            "dialects": {d: sum(1 for v in dialect.values() if v == d)
                         for d in set(dialect.values())},
            "frozen_markers_that_missed_them": list(V14.REFUSAL_MARKERS),
            "securities_affected": len({d.split(":")[1]
                                        for d in dialect}),
            "status": "REPORTED ONLY -- no classification changed, no "
                      "predicate re-frozen, D6.1 counts untouched",
            "consequence_for_adjudication": (
                "true body availability across the 781-document register is "
                "%d, not %d; every count that rested on 146 overstates what "
                "was actually acquired" % (len(real), len(real) + len(dialect))),
        },
        "control_documents": selected,
        "control_route_preserves_known_good_content": preserved_ok,
        "results": results,
        "event_classifications_changed": False,
        "dual_extraction_performed": False,
        "bulk_retry_performed": False,
    }
    out["record_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nroute preserves known-good content:", preserved_ok)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
