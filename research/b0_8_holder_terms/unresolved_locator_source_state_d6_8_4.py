# -*- coding: utf-8 -*-
"""B0.8 · D6.8.4 · U2/U3 · WHAT KIND OF NOTHING IS 24866.htm?

One locator in 71,961 still has no readable substantive body. Two source states
would produce that symptom and they mean opposite things for exhaustion:

    OFFICIAL_BODY_RETRIEVAL_UNRESOLVED   a document we cannot reach; its
                                         content could still be anything, so no
                                         event whose domain contains it can be
                                         called exhausted
    OFFICIAL_EMPTY_BODY                  the first-party source deterministically
                                         serves the referenced object and its
                                         substantive content is genuinely empty;
                                         the official record HAS been inspected
                                         and contains no event evidence

Only evidence separates them, so this stage collects it rather than reasoning
about it: the index row, the annDetail pointer, and repeated direct requests for
the static object, each with status, headers, byte length and sha256 preserved.

U3 · THE BAR FOR CALLING IT EMPTY

    the source-provided locator resolves               not a guessed URL
    the response is a success status                   not 404, not 5xx
    the bytes are stable across repeated requests      not a transient
    the bytes decode                                   not a decoding failure
    the decoded document carries no substantive text   genuinely empty

A transport failure, a malformed derived path, a decode failure or a missing
response is NOT an empty official body, and this stage returns
OFFICIAL_BODY_RETRIEVAL_UNRESOLVED in every one of those cases.

CONTROL

The same probe runs against a locator of the same vintage that IS readable, so
that "success status, stable bytes, empty text" is shown to be a property of
this object rather than of the probe.

    python research/b0_8_holder_terms/unresolved_locator_source_state_d6_8_4.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import (          # noqa: E402
    b64_peek, index_rows)
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402

OUT = os.path.join(HERE, "unresolved_locator_source_state_d6_8_4.json")
TARGET_CF = "24866.htm"
REPEATS = 5
UA = {"User-Agent": "Mozilla/5.0"}

EMPTY = "OFFICIAL_EMPTY_BODY"
UNRESOLVED = "OFFICIAL_BODY_RETRIEVAL_UNRESOLVED"
REFUSED = "OFFICIAL_BODY_REFUSED"
ERROR = "REQUEST_ERROR"


SCRIPT = re.compile(rb"<script[\s\S]*?</script>", re.I)


def substantive_bytes(body):
    """The official object with CDN-injected scripting removed.

    The archive sits behind a CDN that injects a beacon and a challenge script
    into every response, with a fresh token each time. Hashing raw bytes
    therefore measures the CDN, not the document. What must be stable is the
    ARCHIVED OBJECT: the Word-97-exported shell TPEx generated, stripped of
    anything the edge added on the way out.
    """
    return b" ".join(SCRIPT.sub(b"", body).split())


def probe(url):
    """One request, with everything a later reader would need to re-judge."""
    rec = {"url": url}
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=60) as r:
            body = r.read()
            sub = substantive_bytes(body)
            rec.update(status=r.status, headers=dict(r.headers),
                       bytes=len(body),
                       sha256=hashlib.sha256(body).hexdigest(),
                       substantive_bytes=len(sub),
                       substantive_sha256=hashlib.sha256(sub).hexdigest(),
                       cdn_injected_bytes=len(body) - len(sub),
                       last_modified=r.headers.get("Last-Modified"),
                       official_shell_present=(
                           b"Microsoft Word" in body
                           or b"<BODY" in body.upper()))
    except urllib.error.HTTPError as exc:
        rec.update(status=exc.code, error="HTTPError", headers=dict(
            exc.headers or {}))
        return rec, None
    except Exception as exc:                                # noqa: BLE001
        rec.update(status=None, error="%s: %s" % (type(exc).__name__,
                                                  str(exc)[:160]))
        return rec, None
    try:
        text = V14._plain(decode_official(body))
        rec["decoded"] = True
        rec["text_length"] = len(text.strip())
        rec["text_excerpt"] = text.strip()[:200]
    except Exception as exc:                                # noqa: BLE001
        rec["decoded"] = False
        rec["decode_error"] = str(exc)[:120]
    return rec, body


def source_state(probes):
    if not probes or any(p.get("status") is None for p in probes):
        return ERROR
    if all(p["status"] in (401, 403) for p in probes):
        return REFUSED
    if any(p["status"] != 200 for p in probes):
        return UNRESOLVED
    if any(not p.get("decoded") for p in probes):
        return UNRESOLVED
    if len({p["substantive_sha256"] for p in probes}) != 1:
        return UNRESOLVED
    if not all(p.get("official_shell_present") for p in probes):
        return UNRESOLVED
    lm = {p.get("last_modified") for p in probes}
    if len(lm) != 1 or None in lm:
        return UNRESOLVED
    if all(p.get("text_length") == 0 for p in probes):
        return EMPTY
    return UNRESOLVED


def audit(row, label):
    ident = locator_identity(row["content_file"], row["doc_id"])
    cf = b64_peek(row["content_file"])
    rec = {"label": label, "doc_id": row["doc_id"],
           "doc_id_decoded": b64_peek(row["doc_id"]),
           "locator_identity": ident,
           "content_file": row["content_file"], "content_file_decoded": cf,
           "index_date": row["date"],
           "index_subject": row["subject"],
           "index_document_number": row["document_number"],
           "index_subject_empty": not (row["subject"] or "").strip()}

    # the pointer, from preserved bytes
    p = os.path.join(STORE, "%s.json" % ident)
    ptr = None
    if os.path.exists(p):
        raw = open(p, "rb").read()
        rec["annDetail_sha256"] = hashlib.sha256(raw).hexdigest()
        d = (json.loads(decode_official(raw)).get("data") or {})
        ptr = d.get("downHtml")
        rec["annDetail_fields"] = {k: (v if k != "content" else len(v or ""))
                                   for k, v in d.items() if k != "files"}
    rec["source_provided_locator"] = ptr
    rec["locator_is_source_provided"] = bool(ptr)

    probes = []
    if ptr:
        for _ in range(REPEATS):
            pr, _b = probe(D64.TPEX + ptr)
            probes.append(pr)
            time.sleep(0.3)
    rec["probes"] = probes
    rec["verdict"] = source_state(probes) if ptr else UNRESOLVED
    rec["raw_bytes_stable"] = bool(probes) and len(
        {p.get("sha256") for p in probes}) == 1
    rec["substantive_bytes_stable"] = bool(probes) and len(
        {p.get("substantive_sha256") for p in probes}) == 1
    rec["last_modified"] = sorted({p.get("last_modified")
                                   for p in probes}) if probes else []
    lm_one = probes[0].get("last_modified") if probes else None
    try:
        lm_date = parsedate_to_datetime(lm_one).date().isoformat()
    except Exception:                                   # noqa: BLE001
        lm_date = None
    rec["archived_object_last_modified_date"] = lm_date
    rec["last_modified_matches_index_row"] = (
        lm_date == rec["index_date"])
    rec["raw_instability_is_cdn_injection"] = (
        bool(probes) and not rec["raw_bytes_stable"]
        and rec["substantive_bytes_stable"])
    return rec


def main() -> int:
    rows, _ = index_rows()
    target = [r for r in rows
              if b64_peek(r["content_file"]) == TARGET_CF
              and r["date"] == "2004-08-27"]
    assert len(target) == 1, "expected exactly one 24866.htm row on 2004-08-27"

    # a same-vintage control: the readable locator nearest in the same month
    same_month = [r for r in rows
                  if (r["date"] or "").startswith("2004-08")
                  and r["doc_id"] != target[0]["doc_id"]]
    ctrl = None
    for r in sorted(same_month, key=lambda x: x["date"]):
        p = os.path.join(STORE, "static_%s.html" % locator_identity(
            r["content_file"], r["doc_id"]))
        if os.path.exists(p):
            t = V14._plain(decode_official(open(p, "rb").read()))
            if t.strip():
                ctrl = r
                break

    subject = audit(target[0], "TARGET_24866")
    control = audit(ctrl, "SAME_VINTAGE_CONTROL") if ctrl else None

    verdict = subject["verdict"]
    control_ok = bool(control) and control["verdict"] != EMPTY
    out = {
        "record": "B0_8_D6_8_4_U2_UNRESOLVED_LOCATOR_SOURCE_STATE",
        "b0_8_state": "WIP, UNSEALED",
        "reader_changed": False, "linkage_changed": False,
        "inferred_from_event_outcomes": False,
        "criterion": {
            "locator_must_be_source_provided": True,
            "status_must_be_success": True,
            "substantive_bytes_must_be_stable_across_repeats": REPEATS,
            "stability_measured_after_removing_cdn_injected_scripts": True,
            "archived_object_last_modified_must_be_present_and_stable": True,
            "why": ("the archive sits behind a CDN that injects a fresh "
                    "beacon/challenge token per response; raw-byte hashing "
                    "measures the edge, not the archived document"),
            "response_must_decode": True,
            "substantive_text_must_be_empty": True,
            "transport_or_decode_failure_is_not_an_empty_body": True,
        },
        "target": subject,
        "same_vintage_control": control,
        "control_shows_the_probe_can_read_this_vintage": control_ok,
        "VERDICT": verdict,
        "verdict_meaning": {
            EMPTY: ("the first-party source deterministically serves this "
                    "object and it carries no substantive content; the "
                    "official record is inspected and holds no event evidence"),
            UNRESOLVED: ("the object could not be established as served-and-"
                         "empty; its content remains unknown"),
        }[verdict] if verdict in (EMPTY, UNRESOLVED) else verdict,

        # invariants
        "holder_term_values_extracted": False,
        "canonical_holder_terms_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "cash_settlement_acquisition": False,
        "successor_side_acquisition": False,
        "third_party_mirrors_consulted": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "artefacts_rewritten": 0,
    }
    out["audit_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("target locator      :", subject["content_file_decoded"],
          subject["index_date"])
    print("source-provided path:", subject["source_provided_locator"])
    for p in subject["probes"]:
        print("   status %s bytes %s sha %s text_len %s"
              % (p.get("status"), p.get("bytes"),
                 (p.get("sha256") or "")[:12], p.get("text_length")))
    print("raw bytes stable      :", subject["raw_bytes_stable"],
          "| substantive stable:", subject["substantive_bytes_stable"],
          "| instability is CDN:", subject["raw_instability_is_cdn_injection"])
    print("Last-Modified         :", subject["last_modified"],
          "| matches index year:", subject["last_modified_matches_index_row"])
    print("substantive object    :",
          subject["probes"][0].get("substantive_bytes"), "bytes,",
          subject["probes"][0].get("cdn_injected_bytes"), "bytes injected")
    if control:
        print("control %s          : status %s text_len %s -> %s"
              % (control["content_file_decoded"],
                 control["probes"][0].get("status") if control["probes"]
                 else None,
                 control["probes"][0].get("text_length") if control["probes"]
                 else None, control["verdict"]))
    print("VERDICT             :", verdict)
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
