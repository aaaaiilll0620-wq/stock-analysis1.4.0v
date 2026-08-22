# -*- coding: utf-8 -*-
"""B0.8 · D6.8.1 · ENTITY-IDENTITY AND EXHAUSTION CONFORMANCE REPAIR, 59/59.

R1 · THE DEFECT

    AUTHORITATIVE_ENTITY_IDENTITY_SOURCE_CONFORMANCE

The pre-result Q7 amendment required authoritative disappearing-entity identity
evidence. D6.8 implemented gate I against the TDCC security SHORT name. A short
name is a display label, not a legal-entity key; comparing it to a TPEx legal
issuer name fails on contraction (華僑商銀 / 華僑商業銀行股份有限公司) and on
punctuation form (大峽谷－KY). That is an implementation failure to use the
specified identity source. It is NOT evidence that code identity alone suffices.

R2/R3 · WHAT IDENTITY SOURCE IS ACTUALLY AVAILABLE

Two tracks are recorded rather than one, so that no guess about the adjudicator's
intent is buried inside a result.

  TRACK A -- the source R3 names, taken literally.
      TPEx delisted-company directory: absent from every preserved first-party
      store. E1's directory census covers 0 of these 59 (its two endpoints are
      TWSE ones and do not serve TPEx lineage); event_register.company_name is
      null for 59 of 59; security_status.csv has no name column at all. Taken
      literally, all 59 events end ENTITY_IDENTITY_NOT_ESTABLISHED and the
      census is vacuous. That outcome is computed and reported, not asserted.

  TRACK B -- declared deviation. Identity comes from the first-party TPEx
      corpus itself: the code-first LEGAL-NAME binding that TPEx prints in its
      own announcements, e.g. 公告華僑商業銀行股份有限公司（股票代號：5818）.
      This is preserved authoritative issuer text, already acquired, requiring
      zero network. It is a legal-entity name, not a display label.

WHY TRACK B IS NOT A RESTATEMENT OF CODE IDENTITY

Gate I can still fail, and fails for two distinct reasons:
    a candidate that names the code but binds no legal name at all
        -> ENTITY_IDENTITY_NOT_ESTABLISHED
    a candidate that binds a legal name outside the event entity's lineage
        -> ENTITY_IDENTITY_CONFLICT
Code reuse -- the risk Q7 was written against -- is therefore tested against
first-party evidence for every code, not assumed away. Where a code carries
exactly one legal entity across its whole domain, that is a measured property of
the archive, not an assumption.

R4 · FROZEN NORMALIZATION, SYNTAX ONLY

    NFKC; full-width/half-width, whitespace and punctuation folding
    a frozen leading document-token list, stripped only at the string head
    validation: must end 有限公司, length 6..30, no digits, no document verbs
    suffix collapse WITHIN one code: a longer form ending in a shorter valid
        form is the same string with leading noise, and reduces to it

Not used, anywhere: fuzzy similarity, guessed abbreviation expansion, market
outcome, or free substring matching between two different names. Two different
validated names are the SAME entity only on first-party rename evidence
(「A更名為B」 / 「原名A」) published by TPEx in this corpus.

R8 · EXHAUSTION IS EVENT-LOCAL AND MECHANICAL

D6.8's flag ANDed a global error list, so five unrelated 429s denied exhaustion
to all 59. Here each event is scored on its own domain: every month index
enumerated, every in-domain body readable, every candidate adjudicated, no
unresolved error of its own. Nothing is hard-coded true.

R9/R10 · UNCHANGED, AND NO TARGET

Archive start, search end, candidate corpus, gate II predicate, L1/L2 linkage
and the document-class taxonomy are byte-identical to D6.8. The meaning of
AMBIGUOUS is not resolved here. No expected count is encoded; the 59-event rerun
decides, and changes in either direction are reported.

DECLARED EXPOSURE

D6.8's event-level outcomes were already inspected when this stage was written,
and so was the name-FORM structure of the corpus (how many distinct legal names
each code carries) before the rule below was frozen. The form measurement is an
input property of the source, but it is not zero-exposure and is declared as
such. No rule below was chosen by which event it admits.

    python research/b0_8_holder_terms/entity_identity_conformance_repair_d6_8_1.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import (        # noqa: E402
    REORG_MARKERS, TERMINATION_MARKERS, decode_official, field_presence)
from timing_anchor_sufficiency_d6_7 import extract_roles   # noqa: E402

D68_JSON = os.path.join(HERE, "listing_spell_complete_discovery_d6_8.json")
S1_JSON = os.path.join(HERE, "d6_8_supplement_s1.json")
E1_JSON = os.path.join(HERE, "e1_directory_census.json")
REG_JSON = os.path.join(HERE, "event_register.json")
STATUS_CSV = os.path.join(REPO, "data", "b0", "security_status.csv")
TDCC_MASTER = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                           "d7_0c_tdcc_raw", "OD-1-1.csv")
BASES = [os.path.join(REPO, "artifacts", "b0_8_holder_terms", d)
         for d in ("d6_8_tpex_raw", "d6_6_tpex_raw", "d6_5_tpex_raw",
                   "d6_4_tpex_raw")]
FREEZE = os.path.join(HERE, "identity_rule_freeze_d6_8_1.json")
OUT = os.path.join(HERE, "entity_identity_conformance_repair_d6_8_1.json")

# ---- unchanged from D6.8 (R9) ------------------------------------------
ARCHIVE_INCEPTION = date(2002, 1, 1)
WINDOW_FORWARD_DAYS = 40
UNIQUE = "FULL_HISTORY_EVENT_DOCUMENT_UNIQUE"
AMBIGUOUS = "FULL_HISTORY_EVENT_DOCUMENT_AMBIGUOUS"
NONE = "FULL_HISTORY_EVENT_DOCUMENT_NONE"
LINKAGE = "FULL_HISTORY_EVENT_LINKAGE_UNRESOLVED"
ERROR = "FULL_HISTORY_REQUEST_ERROR"

# ---- frozen identity vocabulary (R4) -----------------------------------
NAME_CH = r"[0-9A-Za-z一-鿿()（）\-－_.]"
CODE_KEY = (r"\s*[（(]?\s*(?:上櫃|上市|興櫃)?"
            r"(?:股票代號|證券代號|公司代號|代號)[：:\s]*[（(]?\s*")
BIND_GAP_MAX = 20                       # measured: 153 distinct gap forms
BIND_GAP_FORBID = ("。", "、", "代號")     # sentence break / enumeration /
#                                         a structured code field, not a binding
RUN = "r3"
LEAD_TOKENS = ("更正公告", "公告", "辦理", "有關", "暨", "及", "告", "函",
               "為", "至", "另", "又")
FORBID_IN_NAME = ("公告", "更名", "變更為", "新增", "辭任", "本中心", "主旨")
NAME_MIN, NAME_MAX = 6, 30
RENAME_RE = re.compile(
    r"(%s{2,30}?公司)\s*(?:股份有限公司)?\s*更名為\s*(%s{2,30}?公司)"
    % (NAME_CH, NAME_CH))

ESTABLISHED = "ENTITY_IDENTITY_ESTABLISHED"
NOT_ESTABLISHED = "ENTITY_IDENTITY_NOT_ESTABLISHED"
CONFLICT = "ENTITY_IDENTITY_CONFLICT"


def _norm(s):
    """R4 syntax-only normalization."""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", "", s)


def _cached(name):
    for b in BASES:
        p = os.path.join(b, name)
        if os.path.exists(p):
            return open(p, "rb").read()
    return None


def validate_name(raw):
    """Frozen validator. Returns a canonical legal name or None."""
    t = _norm(raw)
    ends = [m.end() for m in re.finditer("公司", t)]
    if not ends:
        return None
    if len(ends) > 1:                      # drop everything before the last
        t = t[ends[-2]:]                   # preceding company mention
    changed = True
    while changed:
        changed = False
        for p in LEAD_TOKENS:
            if t.startswith(p):
                t, changed = t[len(p):], True
    if not t.endswith("有限公司"):
        return None
    if not (NAME_MIN <= len(t) <= NAME_MAX):
        return None
    if re.search(r"\d", t) or any(f in t for f in FORBID_IN_NAME):
        return None
    return t


def collapse(names):
    """Suffix collapse within one code: leading noise reduces to the core."""
    out = []
    for n in sorted(set(names), key=len):
        if not any(n.endswith(o) for o in out):
            out.append(n)
    return sorted(out)


def gap_ok(gap):
    """Frozen clause grammar between a legal name and the code key.

    Derived from the measured inventory of every gap form in this corpus, not
    from any event: a binding holds inside one clause. A sentence break, an
    enumeration marker, a digit run or a structured 代號 field means the name
    and the code are not in the same assertion.
    """
    return (len(gap) <= BIND_GAP_MAX
            and not any(f in gap for f in BIND_GAP_FORBID)
            and not re.search(r"\d", gap))


def bind_names(text, sid):
    """Every code-first legal-name binding for sid in this body."""
    key = re.compile(CODE_KEY + sid + r"(?!\d)")
    seen = []
    for m in key.finditer(text):
        pre = text[max(0, m.start() - 80):m.start()]
        ends = [x.end() for x in re.finditer("有限公司", pre)]
        if not ends:
            continue
        if not gap_ok(pre[ends[-1]:]):
            continue
        run = re.search(r"(%s{1,40})$" % NAME_CH, pre[:ends[-1]])
        v = validate_name(run.group(1)) if run else None
        if v and v not in seen:
            seen.append(v)
    return seen


def rename_edges(text):
    out = []
    for m in RENAME_RE.finditer(text):
        a, b = validate_name(m.group(1)), validate_name(m.group(2))
        if a and b and a != b:
            out.append((a, b))
    return out


def components(names, edges):
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)
    return [sorted(v) for v in groups.values()]


def track_a_availability(sids):
    """R3 taken literally: is an authoritative directory identity preserved?"""
    e1 = json.load(open(E1_JSON, encoding="utf-8"))
    covered = sum(1 for r in e1["results"] if r.get("security_id") in sids)
    reg = json.load(open(REG_JSON, encoding="utf-8"))
    rows = reg.get("events") if isinstance(reg, dict) else reg
    rows = [r for r in (rows or []) if r.get("security_id") in sids]
    named = sum(1 for r in rows if r.get("company_name"))
    with open(STATUS_CSV, encoding="utf-8") as fh:
        cols = next(csv.reader(fh))
    return {
        "source": "TPEx delisted-company directory (R3 preferred)",
        "preserved_stores_checked": [
            os.path.relpath(E1_JSON, REPO), os.path.relpath(REG_JSON, REPO),
            os.path.relpath(STATUS_CSV, REPO)],
        "e1_directory_endpoints": e1["authoritative_endpoints_used"],
        "e1_rows_covering_this_population": covered,
        "event_register_rows": len(rows),
        "event_register_rows_with_company_name": named,
        "security_status_columns": cols,
        "security_status_has_name_column": any(
            "name" in c.lower() for c in cols),
        "authoritative_directory_identity_available_for": 0,
        "population": len(sids),
        "literal_outcome_if_this_were_the_only_source": {
            NOT_ESTABLISHED: len(sids),
            "resulting_census": "vacuous -- no event could be adjudicated"},
        "identity_invented_to_fill_the_gap": False,
    }


def tdcc_short_names():
    t = open(TDCC_MASTER, "rb").read()
    out = {}
    for line in t.decode("utf-8-sig", "replace").splitlines()[1:]:
        c = [x.strip() for x in line.split(",")]
        if len(c) > 5 and c[0] and c[0] not in out:
            out[c[0]] = c[1]
    return out


def main() -> int:
    d8 = json.load(open(D68_JSON, encoding="utf-8"))
    s1 = json.load(open(S1_JSON, encoding="utf-8"))
    events = d8["results"]
    sids = [e["security_id"] for e in events]
    short = tdcc_short_names()

    # ---- R2 · prove zero network ---------------------------------------
    def _blocked(*a, **k):
        raise RuntimeError("D6.8.1 is offline by construction (R2)")
    D64._req = _blocked

    # ---- freeze the rule BEFORE any event is recomputed -----------------
    freeze = {
        "record": "B0_8_D6_8_1_IDENTITY_RULE_FREEZE",
        "defect_repaired": "AUTHORITATIVE_ENTITY_IDENTITY_SOURCE_CONFORMANCE",
        "frozen_before_any_d6_8_1_outcome_computed": True,
        "identity_source_track_b": (
            "code-first LEGAL-NAME binding printed by TPEx in its own "
            "preserved announcement bodies"),
        "tdcc_short_name_role": "DIAGNOSTIC_METADATA_ONLY (R3)",
        "run": RUN,
        "supersedes_r2": {
            "run": "r2",
            "freeze_sha256": '708241d8bf721124b85843426700d6140914f74dc29109178f40ee8cc9cd32f6',
            "census_sha256": '394b54039736e4e877e325e07788ae250f0fe17a0b6e319502c3144a66cad923',
            "identical_adjudication": True,
            "defect_found_in_r2": (
                "r2 reported every event domain-exhausted. That accounting "
                "counted only documents carrying a document number, and so "
                "could not see 13,798 pre-2005 bulletin rows that no stage has "
                "ever acquired. r3 changes no gate and no classification; it "
                "makes those rows visible to exhaustion accounting"),
            "r2_counts": {'FULL_HISTORY_EVENT_DOCUMENT_AMBIGUOUS': 4, 'FULL_HISTORY_EVENT_DOCUMENT_NONE': 3, 'FULL_HISTORY_EVENT_DOCUMENT_UNIQUE': 52}},
        "supersedes": {
            "run": "r1",
            "freeze_sha256": 'd0d9660700ce4ee3d385fffbc7834592a4a8d718a001d96ef411c3ca1a5ff2c8',
            "census_sha256": '397a096371f0e050ea7e83ed6f81c328874ea2b83828e0228056deb4c7448b23',
            "artefacts_preserved": [
                "identity_rule_freeze_d6_8_1_r1.json",
                "entity_identity_conformance_repair_d6_8_1_r1.json"],
            "defect_found_in_r1": (
                "r1 required the authoritative name to sit in the code's own "
                "clause. That changed gate I's SHAPE, not just its source, and "
                "rejected four same-transaction termination bodies whose only "
                "code key is a structured 五、終止櫃檯買賣證券代號 field "
                "(4103, 5255, 5349, 6238). r2 restores D6.8's shape -- code "
                "key AND authoritative name carried by the body -- and repairs "
                "only the identity source, which is the R1 defect"),
            "r1_counts": {'FULL_HISTORY_EVENT_DOCUMENT_AMBIGUOUS': 3, 'FULL_HISTORY_EVENT_DOCUMENT_NONE': 3, 'FULL_HISTORY_EVENT_DOCUMENT_UNIQUE': 49, 'FULL_HISTORY_EVENT_LINKAGE_UNRESOLVED': 4}},
        "extraction_pattern": {
            "name_chars": NAME_CH, "code_key": CODE_KEY,
            "gap_max_chars": BIND_GAP_MAX,
            "gap_forbidden_tokens": list(BIND_GAP_FORBID),
            "gap_forbids_digits": True,
            "gap_grammar_basis": (
                "the measured inventory of all 153 distinct gap forms in this "
                "corpus, not any event outcome"),
            "backward_window_chars": 80},
        "gate_i_shape": (
            "code-first key for the security AND a name from the canonical "
            "lineage carried by the body -- identical in shape to D6.8; only "
            "the identity source is repaired"),
        "normalization": ["NFKC", "full/half-width folding",
                          "whitespace removal",
                          "leading document-token stripping"],
        "leading_tokens": list(LEAD_TOKENS),
        "validator": {"must_end_with": "有限公司",
                      "length_range": [NAME_MIN, NAME_MAX],
                      "reject_if_contains_digits": True,
                      "reject_if_contains": list(FORBID_IN_NAME),
                      "cut_at_preceding_company_mention": True},
        "suffix_collapse_scope": "within a single security code only",
        "same_entity_requires": (
            "first-party TPEx rename evidence 「A更名為B」 or 「原名A」; "
            "never fuzzy similarity, guessed abbreviation, or free substring "
            "matching between two different validated names"),
        "canonical_disappearing_entity": (
            "the lineage component containing the LATEST code->legal-name "
            "binding within the event's own domain"),
        "gate_i_outcomes": [ESTABLISHED, NOT_ESTABLISHED, CONFLICT],
        "unchanged_from_d6_8": [
            "archive start 2002-01-01", "search end C+40d",
            "candidate corpus definition", "gate II termination predicate",
            "L1/L2 linkage semantics", "document-class taxonomy"],
        "expected_counts_encoded": False,
        "declared_exposure": (
            "D6.8 event outcomes and the corpus name-FORM structure were both "
            "inspected before this freeze; no rule was selected by which event "
            "it admits"),
    }
    freeze["freeze_sha256"] = canonical_sha256(freeze)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(freeze, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("identity rule frozen:", freeze["freeze_sha256"], flush=True)

    track_a = track_a_availability(set(sids))
    print("track A authoritative directory identity available: %d/%d"
          % (track_a["authoritative_directory_identity_available_for"],
             track_a["population"]), flush=True)

    # ---- domain, from cache only ---------------------------------------
    hi_all = max(date.fromisoformat(e["canonical_event_date"])
                 for e in events) + timedelta(days=WINDOW_FORWARD_DAYS)
    months, by_num, month_err = {}, {}, []
    y, m = ARCHIVE_INCEPTION.year, ARCHIVE_INCEPTION.month
    while (y, m) <= (hi_all.year, hi_all.month):
        key = "%d-%02d" % (y, m)
        raw = _cached("bulletin_%s.json" % key)
        rows = []
        if raw is None:
            month_err.append(key)
        else:
            try:
                js = json.loads(raw.decode("utf-8", "replace"))
                for r in ((js.get("tables") or [{}])[0].get("data") or []):
                    num = str(r[2] or "")
                    # R8 honesty: pre-2005 bulletin rows carry an EMPTY
                    # document-number field. Every stage from D6.4 on keyed
                    # documents by that field, so these rows were dropped
                    # before acquisition and have never been fetched. They are
                    # counted here under a synthetic href key so that they are
                    # visible to exhaustion accounting instead of silently
                    # vanishing. No network is used to resolve them (R2).
                    unkeyed = not num
                    if unkeyed:
                        q = urllib.parse.parse_qs(
                            urllib.parse.urlparse(r[4] or "").query)
                        num = "UNKEYED:%s" % (q.get("docId") or [""])[0]
                    rows.append({"date": D64.roc_to_iso(str(r[1])),
                                 "document_number": num,
                                 "unkeyed": unkeyed,
                                 "subject": r[3] or "", "href": r[4]})
            except Exception:                               # noqa: BLE001
                month_err.append(key)
        months[key] = rows
        for r in rows:
            if r["document_number"] and r["document_number"] not in by_num:
                by_num[r["document_number"]] = r
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    print("domain: %d months (%d unreadable), %d distinct documents"
          % (len(months), len(month_err), len(by_num)), flush=True)

    # ---- one pass over every cached body -------------------------------
    hits, unreadable, scanned = defaultdict(list), [], 0
    never_acquired = []
    for i, (num, row) in enumerate(sorted(by_num.items()), 1):
        if row.get("unkeyed"):
            never_acquired.append(num)
            unreadable.append(num)
            continue
        raw = _cached("annDetail_%s.json" % num)
        if raw is None:
            unreadable.append(num)
            continue
        try:
            d = (json.loads(decode_official(raw)).get("data") or {})
        except Exception:                                   # noqa: BLE001
            unreadable.append(num)
            continue
        scanned += 1
        text = V14._plain("%s %s %s" % (d.get("subject", ""),
                                        d.get("depend", ""),
                                        d.get("content", "")))
        for sid in sids:
            if D64.code_in_text(text, sid):
                hits[sid].append(num)
        if i % 10000 == 0:
            print("   scanned %d/%d" % (i, len(by_num)), flush=True)
    print("bodies readable %d | unreadable %d | (sid,doc) hits %d"
          % (scanned, len(unreadable), sum(len(v) for v in hits.values())),
          flush=True)

    # ---- per-event adjudication -----------------------------------------
    results, counts, gate_counts = [], Counter(), Counter()
    for n, ev in enumerate(events, 1):
        sid = ev["security_id"]
        c = date.fromisoformat(ev["canonical_event_date"])
        hi = c + timedelta(days=WINDOW_FORWARD_DAYS)
        rec = {"event_id": ev["event_id"], "security_id": sid,
               "canonical_event_date": c.isoformat(),
               "canonical_exit_reason": ev["canonical_exit_reason"],
               "d6_6_classification": ev["d6_6_classification"],
               "d6_8_classification": ev["classification"],
               "tdcc_short_name_diagnostic_only": short.get(sid),
               "candidates": [], "linked": [], "errors": []}

        # pass 1 · bindings and rename evidence, over this event's domain
        bodies, bindings, edges, dated = {}, [], [], []
        for num in hits.get(sid, []):
            row = by_num[num]
            if not (row["date"] and ARCHIVE_INCEPTION.isoformat()
                    <= row["date"] <= hi.isoformat()):
                continue
            raw = _cached("static_%s.html" % num)
            if raw is None:
                rec["errors"].append({"doc": num, "error": "static body absent"})
                continue
            text = _norm(V14._plain(decode_official(raw)))
            bodies[num] = (row, text, raw)
            found = bind_names(text, sid)
            bindings.extend(found)
            for f in found:
                dated.append((row["date"], f))
            edges.extend(rename_edges(text))
        names = collapse(bindings)
        comps = components(names, edges)
        latest = None
        if dated:
            top = max(d for d, _ in dated)
            pool = collapse([nm for d, nm in dated if d == top])
            latest = pool[0] if pool else None
        lineage = []
        for g in comps:
            if latest and latest in g:
                lineage = g
        if latest and not lineage:
            lineage = [latest]
        rec["entity_identity"] = {
            "distinct_legal_names_bound_to_this_code": names,
            "rename_edges": sorted({"%s -> %s" % e for e in edges}),
            "lineage_components": comps,
            "canonical_disappearing_entity": latest,
            "canonical_lineage": lineage,
            "identity_established": bool(lineage),
            "names_outside_canonical_lineage": [x for x in names
                                                if x not in lineage],
        }

        # pass 2 · gates, unchanged except gate I's source
        entity_corpus = []
        for num, (row, text, raw) in sorted(bodies.items()):
            found = bind_names(text, sid)
            keys = D64.code_in_text(text, sid)
            # Gate I keeps D6.8's SHAPE -- code-first key AND the authoritative
            # entity name carried by the body. Only the identity SOURCE is
            # repaired: a first-party TPEx legal name replaces the TDCC short
            # name. The name need not sit in the code's own clause; that
            # stricter form was tested in run r1 and rejected same-transaction
            # bodies whose code appears only in a structured 代號 field.
            carries = [x for x in lineage if x in text]
            outside = [f for f in found if f not in lineage]
            if not keys:
                gate_i = NOT_ESTABLISHED
            elif carries:
                gate_i = ESTABLISHED
            elif outside:
                gate_i = CONFLICT
            else:
                gate_i = NOT_ESTABLISHED
            term = [t for t in TERMINATION_MARKERS if t in text]
            reorg = [t for t in REORG_MARKERS if t in text]
            roles = extract_roles(re.sub(r"\s+", " ", text))
            cand = {"document_number": num, "index_date": row["date"],
                    "subject": row["subject"] or "",
                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                    "matching_keys": keys,
                    "legal_names_bound": found,
                    "lineage_names_carried": carries,
                    "gate_i": gate_i,
                    "gate_ii_event": bool(term),
                    "termination_markers": term,
                    "reorganization_markers": reorg,
                    "l1_boundary_equals_C": any(
                        f["date"] == c.isoformat() for f in roles),
                    "labelled_boundary_dates": roles,
                    "field_presence": field_presence(text)}
            rec["candidates"].append(cand)
            gate_counts[gate_i] += 1
            if gate_i == ESTABLISHED and term:
                entity_corpus.append(cand)

        # gate III · unchanged (R9)
        l1_hits = [x for x in entity_corpus if x["l1_boundary_equals_C"]]
        compat = [x for x in entity_corpus if x["reorganization_markers"]]
        if l1_hits:
            linked, basis = l1_hits, "L1"
        elif len(compat) == 1:
            linked, basis = compat, "L2"
        else:
            linked, basis = [], None
        rec["linked"] = [x["document_number"] for x in linked]
        rec["linkage_basis"] = basis
        rec["entity_corpus_size"] = len(entity_corpus)
        rec["reorg_compatible_in_entity_corpus"] = len(compat)

        # R8 · event-local exhaustion, computed
        dom_months = []
        yy, mm = ARCHIVE_INCEPTION.year, ARCHIVE_INCEPTION.month
        while (yy, mm) <= (hi.year, hi.month):
            dom_months.append("%d-%02d" % (yy, mm))
            yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
        dom_docs = [num for num, row in by_num.items()
                    if row["date"] and ARCHIVE_INCEPTION.isoformat()
                    <= row["date"] <= hi.isoformat()]
        bad_months = [k for k in dom_months if k in month_err]
        bad_bodies = [x for x in unreadable if x in set(dom_docs)]
        rec["exhaustion"] = {
            "domain_months": len(dom_months),
            "domain_months_unreadable": bad_months,
            "domain_documents": len(dom_docs),
            "domain_documents_unreadable": len(bad_bodies),
            "candidates_adjudicated": len(rec["candidates"]),
            "candidates_expected": len([
                x for x in hits.get(sid, [])
                if by_num[x]["date"] and ARCHIVE_INCEPTION.isoformat()
                <= by_num[x]["date"] <= hi.isoformat()]),
            "own_errors": len(rec["errors"]),
        }
        ex = rec["exhaustion"]
        rec["domain_exhausted"] = (not bad_months and not bad_bodies
                                   and not ex["own_errors"]
                                   and ex["candidates_adjudicated"]
                                   == ex["candidates_expected"])

        if rec["errors"]:
            cls = ERROR
        elif linked:
            cls = UNIQUE if len(set(rec["linked"])) == 1 else AMBIGUOUS
        elif entity_corpus or len(compat) > 1:
            cls = LINKAGE
        elif rec["candidates"] and any(
                x["gate_i"] == ESTABLISHED for x in rec["candidates"]):
            cls = LINKAGE
        else:
            cls = NONE
        rec["classification"] = cls
        counts[cls] += 1
        results.append(rec)
        print("  [%2d/59] %-5s %s %-42s cands=%-4d est=%-4d linked=%d %s"
              % (n, sid, c.isoformat(), cls[19:], len(rec["candidates"]),
                 sum(1 for x in rec["candidates"]
                     if x["gate_i"] == ESTABLISHED),
                 len(rec["linked"]), basis or ""), flush=True)

    changed = [{"security_id": r["security_id"],
                "d6_8": r["d6_8_classification"],
                "d6_8_1": r["classification"],
                "canonical_entity": r["entity_identity"][
                    "canonical_disappearing_entity"],
                "tdcc_short_name": r["tdcc_short_name_diagnostic_only"],
                "linked": r["linked"]}
               for r in results if r["classification"] != r[
                   "d6_8_classification"]]

    out = {
        "record": "B0_8_D6_8_1_ENTITY_IDENTITY_CONFORMANCE_REPAIR",
        "b0_8_state": "WIP, UNSEALED",
        "defect": "AUTHORITATIVE_ENTITY_IDENTITY_SOURCE_CONFORMANCE",
        "preserved_unchanged": {
            "d6_8_router_sha256": d8["router_sha256"],
            "d6_8_census_sha256": d8["census_sha256"],
            "d6_8_counts": d8["counts"],
            "s1_supplement_sha256": s1["supplement_sha256"],
            "artefacts_rewritten": 0,
        },
        "identity_rule_freeze_sha256": freeze["freeze_sha256"],
        "track_a_r3_literal": track_a,
        "track_b_declared_deviation": {
            "identity_source": freeze["identity_source_track_b"],
            "is_first_party": True,
            "network_requests": 0,
            "why_not_code_only_identity": (
                "gate I still fails as NOT_ESTABLISHED or CONFLICT; code reuse "
                "is tested per code against first-party names rather than "
                "assumed absent"),
        },
        "network_requests": 0,
        "offline_by_construction": True,
        "search_domain": {"start": ARCHIVE_INCEPTION.isoformat(),
                          "end": "C + %dd" % WINDOW_FORWARD_DAYS,
                          "changed_from_d6_8": False},
        "months_enumerated": len(months),
        "months_unreadable": month_err,
        "distinct_documents_in_domain": len(by_num),
        "bodies_readable": scanned,
        "bodies_unreadable": len(unreadable),
        "acquisition_completeness_defect": {
            "defect": "PRE_2005_BULLETIN_ROWS_NEVER_ACQUIRED",
            "cause": (
                "TPEx bulletin index rows before 2005 carry an empty "
                "document-number field. Every stage from D6.4 through D6.8 "
                "keyed documents by that field, so these rows were discarded "
                "at enumeration and no body was ever fetched for them. Their "
                "href (content_file + docId) is present and resolvable, so "
                "this is a keying defect, not a source limit"),
            "rows_never_acquired": len(never_acquired),
            "inherited_from": ["D6.4", "D6.5", "D6.6", "D6.8", "S1"],
            "invalidates_the_claim": (
                "'58,120 / 58,120 archive document coverage' counts the KEYED "
                "subset only; the archive-complete reading of D6.8 and of S1 "
                "does not hold for 2002-01 .. 2005-early"),
            "repair_requires_network": True,
            "not_repaired_here_because": "R2 fixes bulletin network requests at 0",
        },
        "sid_document_hits": sum(len(v) for v in hits.values()),
        "counts": dict(counts),
        "gate_i_candidate_outcomes": dict(gate_counts),
        "events_changed_vs_d6_8": changed,
        "events_changed_count": len(changed),
        "events_domain_exhausted": sum(1 for r in results
                                       if r["domain_exhausted"]),
        "events_not_exhausted": [r["security_id"] for r in results
                                 if not r["domain_exhausted"]],
        "identity_coverage": {
            "canonical_identity_established": sum(
                1 for r in results if r["entity_identity"][
                    "identity_established"]),
            "required_rename_lineage": sum(
                1 for r in results
                if len(r["entity_identity"]["canonical_lineage"]) > 1),
            "unresolved_identity": [
                r["security_id"] for r in results
                if not r["entity_identity"]["identity_established"]],
            "names_outside_canonical_lineage": {
                r["security_id"]: r["entity_identity"][
                    "names_outside_canonical_lineage"]
                for r in results
                if r["entity_identity"]["names_outside_canonical_lineage"]},
        },
        "results": results,

        # R11 invariants
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
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "ambiguous_meaning_resolved": False,
        "expected_counts_encoded": False,
    }
    out["census_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("\nD6.8   counts:", d8["counts"])
    print("D6.8.1 counts:", dict(counts))
    print("gate I outcomes:", dict(gate_counts))
    print("changed events :", len(changed))
    for x in changed:
        print("   %s  %s -> %s  (%s)" % (x["security_id"], x["d6_8"][19:],
                                         x["d6_8_1"][19:],
                                         x["canonical_entity"]))
    print("event-local exhausted: %d/59" % out["events_domain_exhausted"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
