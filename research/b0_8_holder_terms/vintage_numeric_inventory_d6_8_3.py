# -*- coding: utf-8 -*-
"""B0.8 · D6.8.3 · T4 · VINTAGE NUMERIC REPRESENTATION INVENTORY. Offline.

WHY THIS RUNS BEFORE THE GRAMMAR IS WRITTEN

The reader has to learn a second way of writing two things it already
understands -- a security code and an ROC calendar date. The grammar for that
must come from general Chinese numeral syntax plus what this archive actually
contains, never from the three securities whose documents were already seen
(T3: pre_repair_outcome_exposure = true, exposed_event_ids = 6157, 4110, 6017).

So this stage writes down, over every readable authoritative body in the corpus:

    what follows an already-authorised security-code label, by script
    every distinct numeral string that appears in a 年/月/日 slot
    the full character inventory of those slots
    whether digit-style years (一○九) occur alongside value-style (九十二)

Nothing is frozen here and no event is touched. The output is the evidence the
grammar is allowed to be built from.

THE CORPUS THIS READS

    annDetail text where it is non-empty            post-2005
    the static body where annDetail is a pointer    pre-2005
    = 71,960 readable bodies of 71,961 locators

    python research/b0_8_holder_terms/vintage_numeric_inventory_d6_8_3.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402

OUT = os.path.join(HERE, "vintage_numeric_inventory_d6_8_3.json")

CODE_LABEL = r"(?:上櫃|上市|興櫃)?(?:股票代號|證券代號|公司代號|代號)[：:\s]*[（(]?\s*"
CJK_NUM_CH = "〇○零一二三四五六七八九十百千萬兩"
DATE_SLOT = re.compile(r"([%s]{1,6})年([%s]{1,3})月([%s]{1,4})日"
                       % (CJK_NUM_CH, CJK_NUM_CH, CJK_NUM_CH))
AFTER_LABEL = re.compile(CODE_LABEL + r"([0-9%s]{1,8})" % CJK_NUM_CH)


def body_text(row):
    """The authoritative body: annDetail text, or the static body behind it."""
    ident = locator_identity(row["content_file"], row["doc_id"])
    num = row["document_number"]
    raw = None
    p = os.path.join(STORE, "%s.json" % ident)
    if os.path.exists(p):
        raw = open(p, "rb").read()
    elif num:
        raw = R3._cached("annDetail_%s.json" % num)
    if raw is not None:
        try:
            d = (json.loads(decode_official(raw)).get("data") or {})
            t = V14._plain("%s %s %s" % (d.get("subject", ""),
                                         d.get("depend", ""),
                                         d.get("content", "")))
            if t.strip():
                return re.sub(r"\s+", "", t)
        except Exception:                                   # noqa: BLE001
            pass
    for cand in (os.path.join(STORE, "static_%s.html" % ident),):
        if os.path.exists(cand):
            return re.sub(r"\s+", "",
                          V14._plain(decode_official(open(cand, "rb").read())))
    if num:
        raw = R3._cached("static_%s.html" % num)
        if raw is not None:
            return re.sub(r"\s+", "", V14._plain(decode_official(raw)))
    return None


def main() -> int:
    rows, _ = index_rows()
    after_label = Counter()
    label_script = Counter()
    years, months, days = Counter(), Counter(), Counter()
    slot_chars = Counter()
    by_year_cjk_date = Counter()
    by_year_cjk_code = Counter()
    readable, unreadable = 0, []

    for i, r in enumerate(rows, 1):
        t = body_text(r)
        if not t:
            unreadable.append(r["doc_id"])
            continue
        readable += 1
        yr = (r["date"] or "?")[:4]

        seen_code = False
        for m in AFTER_LABEL.finditer(t):
            tok = m.group(1)
            after_label[tok] += 1
            if re.fullmatch(r"\d+", tok):
                label_script["arabic"] += 1
            elif all(c in CJK_NUM_CH for c in tok):
                label_script["cjk"] += 1
                seen_code = True
            else:
                label_script["mixed"] += 1
        if seen_code:
            by_year_cjk_code[yr] += 1

        hit = False
        for m in DATE_SLOT.finditer(t):
            years[m.group(1)] += 1
            months[m.group(2)] += 1
            days[m.group(3)] += 1
            for g in m.groups():
                for ch in g:
                    slot_chars[ch] += 1
            hit = True
        if hit:
            by_year_cjk_date[yr] += 1
        if i % 10000 == 0:
            print("   scanned %d/%d" % (i, len(rows)), flush=True)

    cjk4 = {k: v for k, v in after_label.items()
            if len(k) == 4 and all(c in "〇○零一二三四五六七八九" for c in k)}
    cjk_other = {k: v for k, v in after_label.items()
                 if not re.fullmatch(r"\d+", k) and k not in cjk4}
    digit_style_year = {k: v for k, v in years.items()
                        if all(c in "〇○零一二三四五六七八九" for c in k)
                        and len(k) > 1}
    value_style_year = {k: v for k, v in years.items()
                        if k not in digit_style_year}

    out = {
        "record": "B0_8_D6_8_3_T4_VINTAGE_NUMERIC_INVENTORY",
        "b0_8_state": "WIP, UNSEALED",
        "network_requests": 0,
        "grammar_frozen_here": False,
        "events_touched": 0,
        "outcome_exposure": {
            "pre_repair_outcome_exposure": True,
            "exposed_event_ids": ["6157", "4110", "6017"],
            "no_rule_may_be_designed_around_them": True,
        },
        "corpus": {"locators": len(rows), "readable_bodies": readable,
                   "unreadable": len(unreadable)},

        "security_code_slot": {
            "definition": "the token following an already-authorised code label",
            "by_script": dict(label_script),
            "distinct_tokens": len(after_label),
            "cjk_four_digit_forms": len(cjk4),
            "cjk_four_digit_top": dict(Counter(cjk4).most_common(12)),
            "non_arabic_non_four_digit_forms": len(cjk_other),
            "non_arabic_non_four_digit_top": dict(
                Counter(cjk_other).most_common(20)),
            "value_style_code_observed": any(
                any(c in "十百千萬兩" for c in k) for k in cjk_other),
        },

        "calendar_slot": {
            "pattern": "X年Y月Z日 with CJK numerals",
            "distinct_year_forms": len(years),
            "distinct_month_forms": len(months),
            "distinct_day_forms": len(days),
            "year_forms_top": dict(years.most_common(25)),
            "month_forms": dict(months.most_common(20)),
            "day_forms_top": dict(days.most_common(35)),
            "digit_style_years": dict(Counter(digit_style_year).most_common(12)),
            "value_style_years": dict(Counter(value_style_year).most_common(12)),
            "character_inventory": dict(slot_chars.most_common()),
        },

        "distribution": {
            "bodies_with_a_cjk_code_slot_by_year": dict(sorted(
                by_year_cjk_code.items())),
            "bodies_with_a_cjk_date_by_year": dict(sorted(
                by_year_cjk_date.items())),
        },

        # invariants
        "holder_term_values_extracted": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "predicates_changed": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "artefacts_rewritten": 0,
    }
    out["inventory_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    cs, cal = out["security_code_slot"], out["calendar_slot"]
    print("\nreadable bodies            :", readable, "| unreadable",
          len(unreadable))
    print("code slot by script        :", cs["by_script"])
    print("CJK four-digit code forms  :", cs["cjk_four_digit_forms"])
    print("non-arabic other forms     :", cs["non_arabic_non_four_digit_forms"])
    print("value-style code observed  :", cs["value_style_code_observed"])
    print("  top other forms          :",
          list(cs["non_arabic_non_four_digit_top"].items())[:8])
    print("date year forms            :", cal["distinct_year_forms"],
          "| month", cal["distinct_month_forms"],
          "| day", cal["distinct_day_forms"])
    print("digit-style years          :", list(cal["digit_style_years"])[:8])
    print("slot characters            :", "".join(cal["character_inventory"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
