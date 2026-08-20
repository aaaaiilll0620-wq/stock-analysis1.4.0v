# -*- coding: utf-8 -*-
"""B0.8 / R6 · bounded feasibility probe of the admissible prose source.

Measures what an authoritative MOPS material-announcement query actually
returns for events in the register, BEFORE committing to a corpus-wide fetch.
Hammering a public authority 2,500 times to discover the documents are not
there would be neither careful nor polite.

The sample is SYSTEMATIC over the register's own date order (every k-th event),
not chosen. R11 forbids 8913 receiving different treatment, and a sample that
started from the blocker would be exactly that.

Read-only. Raw bytes are cached under artifacts/ and hash-bound; nothing is
extracted into a canonical value here and no term is interpreted.

    python research/b0_8_holder_terms/probe_source_yield.py [stride]
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

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

REGISTER = os.path.join(HERE, "event_register.json")
CACHE = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "raw")
OUT = os.path.join(HERE, "source_yield_probe.json")

ENDPOINT = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01",
}
POLITE_SECONDS = 0.5

# Subject-line signals that an announcement MIGHT carry holder terms. This is a
# retrieval filter, never a reading: whether the terms are actually established
# is decided later, from the document, by two independent extractions.
TERMS_SIGNALS = ("合併", "股份轉換", "換股", "存續", "消滅", "下市", "終止上市",
                 "轉換股份", "股份交換", "收購")


def roc_months(effective_date: str, back: int = 12, fwd: int = 1):
    y, m = int(effective_date[:4]), int(effective_date[5:7])
    out = []
    for delta in range(-back, fwd + 1):
        mm = m + delta
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        out.append(("%d" % (yy - 1911), "%02d" % mm))
    return out


def fetch(params: dict) -> bytes:
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def cached_fetch(key: str, params: dict) -> tuple[bytes, str, bool]:
    path = os.path.join(CACHE, key + ".html")
    if os.path.exists(path):
        raw = open(path, "rb").read()
        return raw, hashlib.sha256(raw).hexdigest(), True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = fetch(params)
    with open(path, "wb") as fh:
        fh.write(raw)
    time.sleep(POLITE_SECONDS)
    return raw, hashlib.sha256(raw).hexdigest(), False


def list_params(sid: str, roc_y: str, mm: str) -> dict:
    return dict(encodeURIComponent="1", step="1", firstin="1", off="1",
                queryName="co_id", inpuType="co_id", TYPEK="all",
                co_id=sid, year=roc_y, month=mm)


ROW = re.compile(
    r"<td[^>]*>\s*&nbsp;(\d{2,7})\s*</td>\s*<td[^>]*>\s*&nbsp;([^<]*)</td>\s*"
    r"<td[^>]*>\s*&nbsp;(\d{2,3}/\d{2}/\d{2})\s*</td>\s*<td[^>]*>\s*&nbsp;"
    r"(\d{2}:\d{2}:\d{2})\s*</td>\s*<td[^>]*>\s*&nbsp;([^<]*)</td>", re.S)


def parse_rows(raw: bytes):
    html = raw.decode("utf-8", "replace")
    out = []
    for code, name, d, t, subject in ROW.findall(html):
        out.append({"code": code.strip(), "name": name.strip(),
                    "spoke_date": d.strip(), "spoke_time": t.strip(),
                    "subject": re.sub(r"\s+", " ", subject).strip()})
    return out


def main() -> int:
    stride = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    reg = json.load(open(REGISTER, encoding="utf-8"))
    events = reg["events"]
    sample = events[::stride]

    results, fetched, from_cache = [], 0, 0
    for ev in sample:
        sid, eff = ev["security_id"], ev["effective_date"]
        months, rows_total, hits, errors = roc_months(eff), 0, [], 0
        for roc_y, mm in months:
            key = "%s/%s%s" % (sid, roc_y, mm)
            try:
                raw, sha, hit = cached_fetch(key, list_params(sid, roc_y, mm))
            except Exception as exc:                        # noqa: BLE001
                errors += 1
                continue
            fetched += 0 if hit else 1
            from_cache += 1 if hit else 0
            rows = parse_rows(raw)
            rows_total += len(rows)
            for r in rows:
                if any(sig in r["subject"] for sig in TERMS_SIGNALS):
                    hits.append({**r, "roc_month": roc_y + mm,
                                 "raw_sha256": sha})
        results.append({
            "event_id": ev["event_id"], "security_id": sid,
            "effective_date": eff, "status_reason": ev["status_reason"],
            "months_queried": len(months), "announcement_rows": rows_total,
            "candidate_terms_announcements": len(hits),
            "http_errors": errors,
            "candidates": hits[:8],
        })
        print("  %-6s %s  rows=%-4d candidates=%-3d errors=%d"
              % (sid, eff, rows_total, len(hits), errors), flush=True)

    probe = {
        "record": "B0_8_SOURCE_YIELD_PROBE",
        "purpose": ("measure what the admissible prose source returns before a "
                    "corpus-wide fetch; extracts nothing and interprets nothing"),
        "sampling": "systematic, every %d-th event in register date order" % stride,
        "sample_size": len(sample),
        "register_sha256": reg["register_sha256"],
        "endpoint": ENDPOINT,
        "source_class": "official_exchange_or_mops",
        "requests_made": fetched, "requests_served_from_cache": from_cache,
        "events_with_any_announcement": sum(
            1 for r in results if r["announcement_rows"]),
        "events_with_candidate_terms_announcement": sum(
            1 for r in results if r["candidate_terms_announcements"]),
        "results": results,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(probe, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("")
    print("sample size                       : %d" % probe["sample_size"])
    print("events with ANY announcement      : %d" % probe["events_with_any_announcement"])
    print("events with candidate terms doc   : %d"
          % probe["events_with_candidate_terms_announcement"])
    print("requests made / cached            : %d / %d" % (fetched, from_cache))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
