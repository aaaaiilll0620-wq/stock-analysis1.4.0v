# -*- coding: utf-8 -*-
"""B0.8 · D6.7 · TPEx termination-document timing / anchor sufficiency.

THE SOLE QUESTION (P1)

    Is canonical event date C an appropriate and semantically CONSISTENT anchor
    for TPEx termination/reorganization-document discovery?

This is a timing and semantics study. It is NOT a recovery search for the 18
unresolved events, and it may not design a window. Whether a D6.8 window repair
is even admissible depends on what this stage finds: if C means the same legal
thing everywhere and the documents cluster, a universal window is a coherent
object; if C means different things in different events, then the defect is the
single-C-anchored router itself and widening it would be repairing the wrong
layer.

P2 · ZERO NETWORK REQUESTS

Every byte read here was fetched and hash-bound by D6.4/D6.5/D6.6. Nothing is
retrieved, and no event is probed.

WHY THE EARLIER LAG NUMBER WAS NOT ENOUGH

An incidental diagnostic already showed publication lags of -30..-3 days. That
observation has a defect this stage exists to remove: it was measured on a
population SELECTED BY the window, so its minimum is pinned to the window's own
edge and cannot testify about anything outside it. The lag distribution is
therefore reported here as a CENSORED observation, explicitly, and the load is
carried instead by the semantic audit -- which is not censored, because it reads
what each document says about its own dates rather than where the document sat.

P5 · WHAT MAY BE PARSED, AND WHAT THE PARSED VALUES MAY BE USED FOR

Explicitly labelled boundary dates only. No consideration value, no ratio, no
successor quantity, no settlement amount.

    every date parsed here is stamped ADJUDICATION_ONLY

The frozen B0.8 schema's settlement/credit fields are themselves dates. A date
parsed by a single path in a timing study must never become a reconstruction
input by inheritance -- if one is ever needed for reconstruction it has to be
re-extracted under the dual-extraction protocol. This stage marks that boundary
in the data rather than leaving it to memory.

P11 · STOP after reporting. D6.8 is not created here.

    python research/b0_8_holder_terms/timing_anchor_sufficiency_d6_7.py
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import official_document_router as V14                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import (        # noqa: E402
    WINDOW_BACK_DAYS, WINDOW_FORWARD_DAYS, decode_official)

CENSUS_D66 = os.path.join(HERE, "tpex_exhaustive_discovery_census_d6_6.json")
CACHES = [os.path.join(REPO, "artifacts", "b0_8_holder_terms", d)
          for d in ("d6_6_tpex_raw", "d6_5_tpex_raw", "d6_4_tpex_raw")]
OUT = os.path.join(HERE, "timing_anchor_sufficiency_d6_7.json")

UNIQUE = "STATIC_EVENT_DOCUMENT_UNIQUE"
AMBIGUOUS = "STATIC_EVENT_DOCUMENT_AMBIGUOUS"
NONE_W = "STATIC_EVENT_DOCUMENT_NONE_WITHIN_FROZEN_WINDOW"
ENGINEERING_DIAGNOSTIC_ONLY = ("4947", "6247", "5281")

# Role labels as the official bodies actually write them. Longest first, so a
# label that contains another is matched as itself.
# These bulletins do not use one fixed spelling. The corpus writes the same
# boundary as 停止櫃檯買賣 / 停止股票櫃檯買賣 / 停止在證券商營業處所買賣 /
# 停止該公司之有價證券櫃檯買賣, and at least one document carries a typo
# (有價證櫃檯). Literal labels therefore under-read the corpus and manufacture a
# false C_ROLE_NOT_ESTABLISHED population -- 5384 and 2921 both state a
# stop-trading date equal to C and both were missed. Roles are matched as
# clause-bounded patterns instead, so a spelling variant cannot look like a
# semantic inconsistency.
ROLE_LABELS = (
    ("CONVERSION_EFFECTIVE", r"股份轉換基準日|股份交換基準日|轉換基準日"),
    ("MERGER_EFFECTIVE", r"合併基準日"),
    ("DELISTING", r"終止[^。;；]{0,14}?買賣|終止上櫃"),
    ("STOP_TRADING", r"停止[^。;；]{0,14}?買賣"),
    ("TRANSFER_SUSPENSION", r"停止股東名簿記載(?:之)?變更|暫停股票過戶|停止過戶"),
    ("MARGIN_SUSPENSION", r"暫停融資融券"),
    ("LAST_TRADING", r"最後交易日"),
)
# 「本(98)年12月24日」 and 「本年12月31日」 both occur. A bare 本年 inherits the
# ROC year already established earlier in the same document.
ROC_DATE = re.compile(
    r"(?:民國)?本?[（(]?(\d{2,3})[）)]?\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
ROC_THIS_YEAR = re.compile(r"本年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
PROXIMITY = 40          # characters either side of a label
C_ROLE_CLASSES = {
    "STOP_TRADING": "C_MATCHES_STOP_TRADING_DATE",
    "DELISTING": "C_MATCHES_DELISTING_DATE",
    "CONVERSION_EFFECTIVE": "C_MATCHES_CONVERSION_EFFECTIVE_DATE",
    "MERGER_EFFECTIVE": "C_MATCHES_MERGER_EFFECTIVE_DATE",
}
OTHER = "C_MATCHES_OTHER_EXPLICIT_BOUNDARY"
MULTI = "C_MATCHES_MULTIPLE_ROLES"
UNSET = "C_ROLE_NOT_ESTABLISHED"


def body_text(document_number):
    name = "static_%s.html" % document_number
    for c in CACHES:
        p = os.path.join(c, name)
        if os.path.exists(p):
            return re.sub(r"\s+", " ",
                          V14._plain(decode_official(open(p, "rb").read())))
    return None


def roc_to_date(y, m, d):
    try:
        return date(int(y) + 1911, int(m), int(d))
    except ValueError:
        return None


def extract_roles(text, doc_roc_year=None):
    """Every explicitly labelled boundary date, with the distance that bound it.

    A label takes the nearest date within PROXIMITY characters, never across a
    clause boundary, and only takes a PRECEDING date through the 自…起
    construction. The distance and the rule are recorded so a reader can see how
    tight each binding was rather than having to trust it.
    """
    dates = []
    inherited = doc_roc_year
    for m in ROC_DATE.finditer(text):
        dt = roc_to_date(*m.groups())
        if dt:
            inherited = int(m.group(1))
            dates.append((m.start(), m.end(), dt))
    for m in ROC_THIS_YEAR.finditer(text):
        if inherited is None:
            continue
        dt = roc_to_date(inherited, m.group(1), m.group(2))
        if dt:
            dates.append((m.start(), m.end(), dt))
    dates.sort()

    found = []
    for role, pattern in ROLE_LABELS:
        for m in re.finditer(pattern, text):
            ls, le = m.start(), m.end()
            best, bestd = None, None
            for ds, de, dt in dates:
                forward = ds >= le
                dist = ds - le if forward else ls - de
                if dist < 0 or dist > PROXIMITY:
                    continue
                gap = text[le:ds] if forward else text[de:ls]
                if any(x in gap for x in "。;；"):
                    continue
                # A label binds a date only inside a DATE-ASSERTING
                # construction. The corpus has exactly two:
                #     自 DATE 起 LABEL          (date precedes)
                #     LABEL …日期[:：] DATE      (date follows)
                # Without this, a bare RULE REFERENCE such as
                # 「應予終止有價證券櫃檯買賣之情事」 picks up whatever date sits
                # nearby and manufactures a second role on the stop-trading
                # date -- which is what put 6178, 4987 and five others into
                # C_MATCHES_MULTIPLE_ROLES.
                if not forward:
                    if not re.fullmatch(r"[起,，、\s]{0,3}", gap):
                        continue
                elif not (any(x in gap for x in ":：") or len(gap) <= 3):
                    continue
                if bestd is None or dist < bestd or (
                        dist == bestd and forward):
                    best, bestd = dt, dist
            if best:
                found.append({"role": role, "label": m.group(0),
                              "date": best.isoformat(),
                              "char_distance": bestd,
                              "binding_rule": ("clause-bounded; preceding only "
                                               "via 自…起; forward wins ties"),
                              "provenance": "ADJUDICATION_ONLY"})
    seen, out = set(), []
    for f in sorted(found, key=lambda x: (x["role"], x["date"])):
        k = (f["role"], f["date"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def pubdate(qualifying):
    m = re.search(r"民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})",
                  str(qualifying.get("publication_date") or ""))
    if m:
        return roc_to_date(*m.groups())
    s = str(qualifying.get("index_row", {}).get("date") or "")
    return date.fromisoformat(s[:10]) if re.match(r"\d{4}-\d{2}-\d{2}", s) \
        else None


def quantiles(v):
    if len(v) < 2:
        only = v[0] if v else None
        return {"n": len(v), "min": only, "max": only, "mean": only,
                "median": only, "P10": only, "P25": only, "P75": only,
                "P90": only,
                "before_C": sum(1 for x in v if x < 0),
                "on_C": sum(1 for x in v if x == 0),
                "after_C": sum(1 for x in v if x > 0)}
    q4 = statistics.quantiles(v, n=4)
    q10 = statistics.quantiles(v, n=10)
    return {"n": len(v), "min": min(v), "max": max(v),
            "mean": round(statistics.mean(v), 2),
            "median": statistics.median(v),
            "P10": round(q10[0], 1), "P25": round(q4[0], 1),
            "P75": round(q4[2], 1), "P90": round(q10[8], 1),
            "before_C": sum(1 for x in v if x < 0),
            "on_C": sum(1 for x in v if x == 0),
            "after_C": sum(1 for x in v if x > 0)}


def main() -> int:
    d66 = json.load(open(CENSUS_D66, encoding="utf-8"))
    uniq = sorted([r for r in d66["results"] if r["classification"] == UNIQUE],
                  key=lambda r: r["canonical_event_date"])
    amb = sorted([r for r in d66["results"]
                  if r["classification"] == AMBIGUOUS],
                 key=lambda r: r["canonical_event_date"])
    unresolved = sorted([r for r in d66["results"]
                         if r["classification"] == NONE_W],
                        key=lambda r: r["canonical_event_date"])
    assert len(uniq) == 39 and len(amb) == 2, (len(uniq), len(amb))

    results, lags, unreadable = [], [], []
    for r in uniq:
        c = date.fromisoformat(r["canonical_event_date"])
        q = r["qualifying"][0]
        text = body_text(q["document_number"])
        if text is None:
            unreadable.append(r["security_id"])
            continue
        p_pre = pubdate(q)
        roles = extract_roles(
            text, (p_pre.year - 1911) if p_pre else None)
        p = p_pre
        lag = (p - c).days if p else None
        if lag is not None:
            lags.append(lag)
        matching = sorted({f["role"] for f in roles
                           if f["date"] == c.isoformat()})
        if not matching:
            cls = UNSET
        elif len(matching) > 1:
            cls = MULTI
        else:
            cls = C_ROLE_CLASSES.get(matching[0], OTHER)
        results.append({
            "event_id": r["event_id"], "security_id": r["security_id"],
            "canonical_event_date": c.isoformat(),
            "document_number": q["document_number"],
            "body_sha256": q["body_sha256"],
            "publication_date": p.isoformat() if p else None,
            "publication_lag_days": lag,
            "labelled_boundary_dates": roles,
            "roles_matching_C": matching,
            "c_role_class": cls,
            "distinct_boundary_dates_in_document": sorted(
                {f["date"] for f in roles}),
        })

    # ---- P4 ---------------------------------------------------------------
    p4 = quantiles(lags)
    p4["censoring_warning"] = (
        "this population was SELECTED by the frozen window, so min cannot fall "
        "below -%d and max cannot exceed +%d by construction; the distribution "
        "is censored and must not be read as the true timing profile"
        % (WINDOW_BACK_DAYS, WINDOW_FORWARD_DAYS))

    # ---- P5 ---------------------------------------------------------------
    role_counts = Counter(r["c_role_class"] for r in results)

    # ---- P6 ---------------------------------------------------------------
    by_role = defaultdict(list)
    for r in results:
        if r["publication_lag_days"] is not None:
            by_role[r["c_role_class"]].append(r["publication_lag_days"])
    p6 = {k: quantiles(v) for k, v in sorted(by_role.items()) if v}

    established = {k: v for k, v in role_counts.items() if k != UNSET}
    dominant = max(established.values()) if established else 0
    share = dominant / max(len(results), 1)
    spans = [v["max"] - v["min"] for v in p6.values() if v["n"] >= 3]
    if role_counts.get(UNSET, 0) > len(results) * 0.25:
        regime = "INSUFFICIENT_SEMANTIC_ALIGNMENT"
    elif len(established) == 1 or share >= 0.8:
        regime = "ONE_STABLE_TIMING_REGIME"
    else:
        regime = "MULTIPLE_TIMING_REGIMES"
    p6_conclusion = {
        "classification": regime,
        "c_role_classes_established": len(established),
        "dominant_class_share": round(share, 3),
        "per_class_lag_spans_days": spans,
        "must_not_define_a_window": True,
    }

    # ---- P7 ---------------------------------------------------------------
    lo, hi = -WINDOW_BACK_DAYS, WINDOW_FORWARD_DAYS
    inside = [x for x in lags if lo < x < hi]
    at_lower = [x for x in lags if x == lo]
    at_upper = [x for x in lags if x == hi]
    outside = [x for x in lags if x < lo or x > hi]
    p7 = {
        "frozen_window": [lo, hi],
        "documents_inside_strictly": len(inside),
        "documents_exactly_at_lower_boundary": len(at_lower),
        "documents_exactly_at_upper_boundary": len(at_upper),
        "documents_outside": len(outside),
        "distances_outside": sorted(outside),
        "replacement_window_derived_here": False,
        "note": ("a document sitting exactly on the lower boundary is the "
                 "signature of censoring, not of a comfortable fit"),
    }

    # ---- P8 ---------------------------------------------------------------
    p8 = [{"security_id": r["security_id"],
           "canonical_event_date": r["canonical_event_date"],
           "lineage": "TPEX",
           "status": NONE_W,
           "pool_exhausted": r["pool_exhausted"],
           "candidates_found": len(r["candidates"]),
           "non_qualifying": [n["reason"] for n in r["non_qualifying"]],
           "canonical_C_semantic_information_known": (
               "none -- no authoritative body for this event, so C's role "
               "cannot be read from a document"),
           "document_absence_asserted": False}
          for r in unresolved]

    # ---- P9 ---------------------------------------------------------------
    p9 = {sid: next(({"canonical_event_date": e["canonical_event_date"],
                      "status": e["status"],
                      "pool_exhausted": e["pool_exhausted"],
                      "candidates_found": e["candidates_found"]}
                     for e in p8 if e["security_id"] == sid),
                    {"in_unresolved_population": False})
          for sid in ENGINEERING_DIAGNOSTIC_ONLY}

    out = {
        "record": "B0_8_D6_7_TIMING_ANCHOR_SUFFICIENCY",
        "b0_8_state": "WIP, UNSEALED",
        "network_requests": 0,
        "reads_only_bytes_preserved_by": ["D6.4", "D6.5", "D6.6"],
        "d6_6_census_sha256": d66["census_sha256"],
        "p0_cash_leg_branch_status": {
            "8913": ("NOT_RECONSTRUCTIBLE under the current frozen schema and "
                     "the established public-authoritative source environment"),
            "official_replay": "blocked at 2020-01",
            "wording": "PUBLIC_AUTHORITATIVE_SETTLEMENT_DATE_NOT_CURRENTLY_"
                       "ACQUIRABLE",
            "not_asserted": "SETTLEMENT_DATE_DOES_NOT_EXIST",
            "further_cash_settlement_source_hunting_in_d6_7": False,
            "third_party_mirrors_consulted": False,
        },
        "population": {"unique": len(uniq), "ambiguous_kept_separate": len(amb),
                       "unreadable_bodies": unreadable,
                       "ambiguous_documents_not_chosen_between": True},
        "p4_publication_lag": p4,
        "p5_c_role_counts": {k: role_counts.get(k, 0) for k in
                             list(C_ROLE_CLASSES.values()) + [OTHER, MULTI,
                                                              UNSET]},
        "p6_lag_by_c_role": p6,
        "p6_timing_regime": p6_conclusion,
        "p7_current_window": p7,
        "p8_unresolved_events": p8,
        "p9_engineering_diagnostic_only": p9,
        "parsed_dates_provenance": "ADJUDICATION_ONLY",
        "parsed_dates_may_become_reconstruction_inputs": False,
        "parsed_date_reuse_rule": (
            "the frozen schema's settlement/credit fields are dates; a date "
            "parsed by this single-path timing study may not be inherited as a "
            "reconstruction input and must be re-extracted under the dual-"
            "extraction protocol if ever required"),
        # P10
        "window_expanded": False,
        "d6_8_created": False,
        "holder_term_extraction": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "successor_side_acquisition": False,
        "cash_settlement_acquisition": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "results": results,
    }
    out["census_sha256"] = canonical_sha256(
        {k: v for k, v in out.items() if k != "results"})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("P4 lag :", json.dumps({k: v for k, v in p4.items()
                                  if k != "censoring_warning"},
                                 ensure_ascii=False))
    print("P5 C role counts:")
    for k, v in out["p5_c_role_counts"].items():
        if v:
            print("   %-40s %d" % (k, v))
    print("P6 regime:", regime, "| dominant share %.2f" % share)
    for k, v in p6.items():
        print("   %-40s n=%2d  min %+d  median %+.0f  max %+d"
              % (k, v["n"], v["min"], v["median"], v["max"]))
    print("P7 window:", json.dumps(
        {k: v for k, v in p7.items() if k != "note"}, ensure_ascii=False))
    print("P8 unresolved:", len(p8))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
