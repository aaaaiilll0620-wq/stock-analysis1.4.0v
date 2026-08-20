# -*- coding: utf-8 -*-
"""B0.8 · C1-C10 · MOPS E1 directory resolver coverage census.

ONE corpus-wide census over the 97-event population whose disappearing-company
name is supplied by the TWSE authoritative delisted-company directory. It
measures ONLY what the MOPS name resolver returns. It does not reconstruct
holder terms, does not query merger announcements, does not classify any event
RECONSTRUCTIBLE and does not touch the CA ledger or the canonical states.

The other 61 register events are reported separately as
AUTHORITATIVE_NAME_INPUT_UNAVAILABLE. They are NOT queried and NOT counted as
E1 failures: the frozen template requires an authoritative name and there is
none, so there is no query to fail. Local TEJ narrative is not used to
manufacture one.

WHAT E1_UNIQUE_RESOLUTION MEANS, AND WHAT IT DOES NOT

It means the authoritative MOPS directory resolves the old official name to
exactly one current entity/code. It does NOT mean the survivor is proven, that
the holder terms are reconstructible, or that the event is RECONSTRUCTIBLE.
Those require the transaction document, which this stage does not fetch.

RESPONSE SHAPE, read from the markup rather than assumed. Each suggestion row
carries `autoDiv-N` (the value) and `autoType-N` (an undocumented category). An
ENTITY row is one whose value has the shape of a Taiwan equity code -- four
digits -- and that test is used INSTEAD of autoType.

The first version of this census filtered on `autoType == '1'`, which looked
right because every clean single-company answer carries it. It was wrong: 合庫
returns 5880 as type 1 AND its own 5854 as type 2, and 中化 returns a third
candidate 4182 as type 2. Trusting an undocumented category code would have
reported those as UNIQUE when the directory actually returned several entities,
which is the difference between a resolver that answers and one that offers.
Non-equity rows are excluded by shape instead: the ones observed (032804,
032807, 000102) are six digits and cannot collide with a company code.

    python research/b0_8_holder_terms/e1_directory_census.py
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
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

REGISTER = os.path.join(HERE, "event_register.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "e1_census_raw")
OUT = os.path.join(HERE, "e1_directory_census.json")

TWSE_DIRECTORY = "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml"
E1 = "https://mopsov.twse.com.tw/mops/web/ajax_autoComplete"
HEADERS = {"User-Agent": "Mozilla/5.0",
           "Content-Type": "application/x-www-form-urlencoded",
           "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01"}
POLITE = 0.6

E1_UNIQUE_RESOLUTION = "E1_UNIQUE_RESOLUTION"
E1_EMPTY = "E1_EMPTY"
E1_AMBIGUOUS = "E1_AMBIGUOUS"
E1_REQUEST_INVALID_OR_ERROR = "E1_REQUEST_INVALID_OR_ERROR"
CLASSES = (E1_UNIQUE_RESOLUTION, E1_EMPTY, E1_AMBIGUOUS,
           E1_REQUEST_INVALID_OR_ERROR)

# Fixed historical cohorts, declared here rather than chosen after seeing the
# result, so that "coverage by cohort" cannot become a boundary drawn where the
# answer changes.
COHORTS = (("2004-2008", "2004", "2008"), ("2009-2013", "2009", "2013"),
           ("2014-2018", "2014", "2018"), ("2019-2023", "2019", "2023"),
           ("2024-2026", "2024", "2026"))

ENTITY = re.compile(r"name='autoDiv-(\d+)'[^>]*value='([^']*)'")
EQUITY_CODE = re.compile(r"\d{4}")


def parse_entities(raw: bytes):
    """Entity rows by CODE SHAPE, not by the undocumented autoType."""
    html = raw.decode("utf-8", "replace")
    out = []
    for ordinal, value in ENTITY.findall(html):
        v = value.strip()
        if EQUITY_CODE.fullmatch(v):
            out.append((v, int(ordinal)))
    return out


def display_names(raw: bytes):
    html = raw.decode("utf-8", "replace")
    names = []
    for body in re.findall(r"id='autoCompilete-dbody\d+'[^>]*>(.*?)<input",
                           html, re.S):
        t = re.sub(r"<[^>]+>", "", body)
        names.append(re.sub(r"\s+", " ", t).strip())
    return names


def query(name: str, sid: str):
    path = os.path.join(RAW, "%s.html" % sid)
    os.makedirs(RAW, exist_ok=True)
    if os.path.exists(path):
        return open(path, "rb").read(), None
    params = dict(firstin="1", TYPEK="all", step="1", co_id="",
                  funcName="t05st01", searchtype="", inpuType="keyword",
                  keyword=name)
    try:
        req = urllib.request.Request(
            E1, data=urllib.parse.urlencode(params).encode(), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
    except Exception as exc:                                # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])
    with open(path, "wb") as fh:
        fh.write(raw)
    time.sleep(POLITE)
    return raw, None


def main() -> int:
    reg = json.load(open(REGISTER, encoding="utf-8"))
    d = json.loads(urllib.request.urlopen(TWSE_DIRECTORY, timeout=30)
                   .read().decode("utf-8"))
    name_of = {str(r["Code"]): r["Company"] for r in d}

    population = [e for e in reg["events"] if e["security_id"] in name_of]
    unavailable = [e for e in reg["events"] if e["security_id"] not in name_of]
    population.sort(key=lambda e: (e["effective_date"], e["security_id"]))

    results = []
    for e in population:
        sid, nm = e["security_id"], name_of[e["security_id"]]
        raw, err = query(nm, sid)
        if raw is None:
            results.append({
                "event_id": e["event_id"], "security_id": sid,
                "effective_date": e["effective_date"],
                "authoritative_name": nm, "classification":
                    E1_REQUEST_INVALID_OR_ERROR, "error": err,
                "resolved_codes": [], "raw_sha256": None, "bytes": 0})
            continue
        ents = parse_entities(raw)
        codes = sorted({c for c, _ in ents})
        cls = (E1_EMPTY if not codes else
               E1_UNIQUE_RESOLUTION if len(codes) == 1 else E1_AMBIGUOUS)
        results.append({
            "event_id": e["event_id"], "security_id": sid,
            "effective_date": e["effective_date"], "authoritative_name": nm,
            "classification": cls,
            "resolved_codes": codes,
            "candidate_count": len(codes),
            "resolved_display_names": display_names(raw)[:5],
            # Recorded, deliberately, without being acted on: a resolution to
            # the security's OWN code is not a survivor, and C5 forbids going
            # further to find out what it is.
            "resolved_code_equals_disappearing_code": (
                codes == [sid] if codes else None),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw)})

    counts = Counter(r["classification"] for r in results)
    by_year, by_cohort = {}, {}
    for r in results:
        y = r["effective_date"][:4]
        by_year.setdefault(y, Counter())[r["classification"]] += 1
        for label, lo, hi in COHORTS:
            if lo <= y <= hi:
                by_cohort.setdefault(label, Counter())[r["classification"]] += 1
                break

    pos = [r for r in results if r["classification"] == E1_UNIQUE_RESOLUTION]
    neg = [r for r in results if r["classification"] == E1_EMPTY]
    pos_dates = sorted(r["effective_date"] for r in pos)
    neg_dates = sorted(r["effective_date"] for r in neg)
    interleaved = bool(pos_dates and neg_dates
                       and min(pos_dates) < max(neg_dates))

    out = {
        "record": "B0_8_E1_DIRECTORY_COVERAGE_CENSUS",
        "purpose": ("measure the historical coverage of the MOPS E1 directory "
                    "resolver for authoritative disappearing-company names"),
        "register_sha256": reg["register_sha256"],
        "authoritative_endpoints_used": [TWSE_DIRECTORY, E1],
        "population_rule": ("every B0.8 register event whose disappearing-"
                            "company name is supplied by the TWSE authoritative "
                            "delisted-company directory; no sampling, no "
                            "filtering"),
        "total_queried": len(results),
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "unique_resolution_rate": (
            round(counts.get(E1_UNIQUE_RESOLUTION, 0) / len(results), 4)
            if results else None),
        "by_year": {y: dict(c) for y, c in sorted(by_year.items())},
        "by_cohort": {k: dict(v) for k, v in by_cohort.items()},
        "earliest_positive_event": (pos_dates[0] if pos_dates else None),
        "latest_negative_event": (neg_dates[-1] if neg_dates else None),
        "positive_negative_form_a_temporal_cutoff": (
            not interleaved if (pos_dates and neg_dates) else None),
        "positive_negative_interleave": interleaved,
        "authoritative_name_input_unavailable": len(unavailable),
        "authoritative_name_input_unavailable_ids": sorted(
            e["event_id"] for e in unavailable),
        "results": results,
        # C9
        "canonical_values_materialized": False,
        "events_classified_reconstructible": 0,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "performance_inspected": False,
        "replay_started": False,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("total queried            : %d" % out["total_queried"])
    for c in CLASSES:
        print("  %-30s %d" % (c, out["counts"][c]))
    print("unique-resolution rate   : %s" % out["unique_resolution_rate"])
    print("earliest positive        : %s" % out["earliest_positive_event"])
    print("latest negative          : %s" % out["latest_negative_event"])
    print("interleaved              : %s" % out["positive_negative_interleave"])
    print("name-input unavailable   : %d (not queried)"
          % out["authoritative_name_input_unavailable"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
