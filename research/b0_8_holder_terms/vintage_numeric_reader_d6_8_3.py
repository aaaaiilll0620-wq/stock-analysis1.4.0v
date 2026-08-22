# -*- coding: utf-8 -*-
"""B0.8 · D6.8.3 · T5/T6 · THE VINTAGE-NUMERIC READER. Lexical repair only.

    PRE2005_NUMERIC_REPRESENTATION_READER_CONFORMANCE_DEFECT

Two semantic objects the rules already read -- a security code and an ROC
calendar date -- have a second authoritative written form this reader could not
see. 「證券代號:六一五七」 and 「證券代號:6157」 are the same identifier in the
same labelled slot; 「九十二年十二月五日」 and 「92年12月5日」 are the same date in
the same declaration. Teaching the reader both forms is not a rule change.

WHAT IS EXTENDED, AND WHAT IS UNTOUCHABLE

    extended    the TOKEN accepted inside an already-authorised code label
    extended    the TOKEN accepted in a Y年M月D日 declaration
    untouched   which constructs are authorised at all
    untouched   sentence-boundary constraints, label vocabulary, forward and
                backward binding, role taxonomy, proximity
    untouched   Gate I, Gate II, L1/L2, rename lineage, the taxonomy

D6.7's extract_roles is not edited, not copied and not re-implemented. It is
called verbatim on text whose CJK date expressions have been rewritten into the
Arabic form it already reads, and each rewrite is padded back to the ORIGINAL
character length so every distance and gap the binding rules measure is
unchanged. Padding uses U+E000, which occurs in no official text and is in none
of D6.7's whitelists, so any gap containing it fails the binding test rather
than passing it: the transformation can only ever bind less, never more.

TWO DECODERS, DELIBERATELY SEPARATE (T5/T6)

    security code   POSITIONAL. 六一五七 -> 6157, digit by digit, and the result
                    must satisfy the same four-digit shape the Arabic predicate
                    requires. Value-style numbers are NOT accepted as codes.
                    The corpus inventory searched for them: of 6,057 CJK code
                    slots, every well-formed one is positional, and no
                    四位value-style code (六千一百五十七) occurs anywhere.
    calendar        VALUE. 九十二 -> 92, 二十五 -> 25, 一百 -> 100, with the
                    digit-style variant 一○一 -> 101 the corpus also uses.
                    Bounded to 10..999 for the year, exactly as the Arabic
                    pattern's (\\d{2,3}) already bounds it, so a body writing an
                    AD year 二○○五 is rejected here just as 2005 is rejected
                    there.

Sharing one "Chinese number to int" helper between the two would silently make
六千一百五十七 a legal security code. They stay separate functions.

    grammar frozen from: general Chinese numeral syntax + the corpus-wide
    inventory in vintage_numeric_inventory_d6_8_3.json, never from the three
    securities already seen (T3)
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import official_document_router as V14                     # noqa: E402
import tpex_static_archive_d6_4 as D64                     # noqa: E402
from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from tpex_exhaustive_discovery_census_d6_6 import decode_official  # noqa: E402
from pre2005_locator_acquisition_d6_8_2 import (           # noqa: E402
    STORE, locator_identity)
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402
import timing_anchor_sufficiency_d6_7 as D67               # noqa: E402

FREEZE = os.path.join(HERE, "vintage_reader_freeze_d6_8_3.json")

# ---- frozen lexis -------------------------------------------------------
ZERO = "〇○零"
UNIT_DIGITS = "一二三四五六七八九"
POSITIONAL = {c: str(i + 1) for i, c in enumerate(UNIT_DIGITS)}
POSITIONAL.update({c: "0" for c in ZERO})
VALUE_DIGITS = {c: i + 1 for i, c in enumerate(UNIT_DIGITS)}
VALUE_DIGITS.update({c: 0 for c in ZERO})
PAD = ""

CODE_LABEL = R3.CODE_KEY                       # the authorised construct, as-is
CODE_SHAPE = re.compile(r"\d{4}$")             # the Arabic predicate's shape
CJK_ANY = ZERO + UNIT_DIGITS + "十百"
DATE_EXPR = re.compile(r"([%s]{1,6})年([%s]{1,3})月([%s]{1,4})日"
                       % (CJK_ANY, CJK_ANY, CJK_ANY))


def cjk_code_to_digits(token):
    """T5 · POSITIONAL decoder. Security codes only. Never value-style."""
    out = []
    for ch in token:
        if ch not in POSITIONAL:
            return None
        out.append(POSITIONAL[ch])
    s = "".join(out)
    return s if CODE_SHAPE.match(s) else None


def cjk_calendar_int(token):
    """T6 · VALUE decoder, bounded. Calendar numbers only. Never codes."""
    if not token:
        return None
    if any(ch in "十百" for ch in token):        # value style
        total, cur, seen = 0, None, False
        i = 0
        while i < len(token):
            ch = token[i]
            if ch in VALUE_DIGITS:
                if cur is not None:
                    return None
                cur = VALUE_DIGITS[ch]
                seen = True
            elif ch == "十":
                total += (cur if cur is not None else 1) * 10
                cur, seen = None, True
            elif ch == "百":
                total += (cur if cur is not None else 1) * 100
                cur, seen = None, True
            else:
                return None
            i += 1
        if cur is not None:
            total += cur
        return total if seen else None
    digits = []                                  # digit style: 一○一 -> 101
    for ch in token:
        if ch not in VALUE_DIGITS:
            return None
        digits.append(str(VALUE_DIGITS[ch]))
    return int("".join(digits))


def cjk_code_regex(sid):
    """The same authorised label, with the positional form of this code."""
    body = "".join("[%s]" % ZERO if c == "0" else UNIT_DIGITS[int(c) - 1]
                   for c in sid)
    return re.compile(CODE_LABEL + body + r"(?![%s])" % CJK_ANY)


def code_in_text_v2(text, sid):
    """D6.4's predicate, plus the positional representation of the same code.

    The parenthesised bare-code key is NOT extended: a bare CJK numeral run is
    diagnostic only (T5), so only the labelled construct gains the second form.
    """
    keys = list(D64.code_in_text(text, sid))
    if cjk_code_regex(sid).search(text):
        keys.append("CJK代號=%s" % sid)
    return keys


def normalize_vintage_dates(text):
    """Rewrite CJK date declarations into the Arabic form D6.7 already reads.

    Length-preserving: every rewrite is padded back to the original width with
    U+E000, so PROXIMITY, char_distance and every gap test see the geometry they
    saw before. A rewrite that would GROW the text is skipped instead.
    """
    if not text:
        return text, 0
    out, last, n = [], 0, 0
    for m in DATE_EXPR.finditer(text):
        y = cjk_calendar_int(m.group(1))
        mo = cjk_calendar_int(m.group(2))
        d = cjk_calendar_int(m.group(3))
        if y is None or mo is None or d is None:
            continue
        if not (10 <= y <= 999):                 # the Arabic pattern's \d{2,3}
            continue
        rep = "%d年%d月%d日" % (y, mo, d)
        if len(rep) > len(m.group(0)):
            continue
        out.append(text[last:m.start()])
        out.append(rep + PAD * (len(m.group(0)) - len(rep)))
        last = m.end()
        n += 1
    out.append(text[last:])
    return "".join(out), n


def extract_roles_v2(text):
    """D6.7's extractor, verbatim, over vintage-normalized text."""
    norm, _ = normalize_vintage_dates(text)
    return D67.extract_roles(norm)


def bind_names_v2(text, sid):
    """R3's binding, with the code label accepting both representations."""
    seen = []
    for key in (re.compile(CODE_LABEL + sid + r"(?!\d)"), cjk_code_regex(sid)):
        for m in key.finditer(text):
            pre = text[max(0, m.start() - 80):m.start()]
            ends = [x.end() for x in re.finditer("有限公司", pre)]
            if not ends:
                continue
            if not R3.gap_ok(pre[ends[-1]:]):
                continue
            run = re.search(r"(%s{1,40})$" % R3.NAME_CH, pre[:ends[-1]])
            v = R3.validate_name(run.group(1)) if run else None
            if v and v not in seen:
                seen.append(v)
    return seen


def body_text(row):
    """The authoritative body: annDetail text, or the static body behind it."""
    ident = locator_identity(row["content_file"], row["doc_id"])
    num = row["document_number"]
    p = os.path.join(STORE, "%s.json" % ident)
    raw = open(p, "rb").read() if os.path.exists(p) else (
        R3._cached("annDetail_%s.json" % num) if num else None)
    if raw is not None:
        try:
            d = (json.loads(decode_official(raw)).get("data") or {})
            t = V14._plain("%s %s %s" % (d.get("subject", ""),
                                         d.get("depend", ""),
                                         d.get("content", "")))
            if t.strip():
                return re.sub(r"\s+", "", t), "annDetail"
        except Exception:                                   # noqa: BLE001
            pass
    p = os.path.join(STORE, "static_%s.html" % ident)
    if os.path.exists(p):
        return re.sub(r"\s+", "", V14._plain(
            decode_official(open(p, "rb").read()))), "static_d6_8_2"
    if num:
        raw = R3._cached("static_%s.html" % num)
        if raw is not None:
            return re.sub(r"\s+", "", V14._plain(
                decode_official(raw))), "static_inherited"
    return None, None


def freeze_record(inventory_sha):
    rec = {
        "record": "B0_8_D6_8_3_VINTAGE_READER_FREEZE",
        "defect": "PRE2005_NUMERIC_REPRESENTATION_READER_CONFORMANCE_DEFECT",
        "class": "LEXICAL_REPRESENTATION_REPAIR",
        "frozen_before_any_59_event_recomputation": True,
        "grammar_derived_from": {
            "general_chinese_numeral_syntax": True,
            "corpus_inventory_sha256": inventory_sha,
            "target_event_outcomes": False,
        },
        "outcome_exposure": {
            "pre_repair_outcome_exposure": True,
            "exposed_event_ids": ["6157", "4110", "6017"],
            "rule_designed_around_them": False,
        },
        "security_code_decoder": {
            "style": "POSITIONAL_ONLY",
            "accepted_characters": ZERO + UNIT_DIGITS,
            "required_shape": "exactly four decimal digits, the Arabic "
                              "predicate's own shape",
            "value_style_accepted": False,
            "value_style_searched_for_in_corpus": True,
            "value_style_found": False,
            "authorised_construct": "the existing code label only",
            "bare_cjk_numeral_runs": "DIAGNOSTIC_ONLY, never identity evidence",
            "parenthesised_bare_code_key_extended": False,
        },
        "calendar_decoder": {
            "style": "VALUE_WITH_DIGIT_STYLE_VARIANT",
            "accepted_characters": ZERO + UNIT_DIGITS + "十百",
            "value_forms": ["十X", "X十", "X十Y", "X百", "X百零Y", "X百Y十Z"],
            "digit_style_forms": ["一○一 -> 101", "九二 -> 92"],
            "year_bounds": [10, 999],
            "year_bounds_reason": "identical to the Arabic pattern's (\\d{2,3})",
            "shares_code_decoder": False,
        },
        "d6_7_binding_semantics": {
            "function_edited": False,
            "function_copied": False,
            "called_verbatim": True,
            "text_transformation": "CJK date expressions rewritten to Arabic",
            "length_preserving": True,
            "padding_codepoint": "U+E000",
            "padding_is_in_any_whitelist": False,
            "direction_of_error": "can only bind less, never more",
            "sentence_boundary_rules_changed": False,
            "label_vocabulary_changed": False,
            "role_taxonomy_changed": False,
            "parsed_dates_remain": "ADJUDICATION_ONLY",
        },
        "identity_semantics": {
            "gate_i_changed": False, "gate_ii_changed": False,
            "l1_l2_changed": False, "rename_lineage_changed": False,
            "note": ("the code label inside bind_names gains the same second "
                     "representation; the requirement that an authoritative "
                     "legal name be carried is untouched"),
        },
    }
    rec["freeze_sha256"] = canonical_sha256(rec)
    with open(FREEZE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    return rec


if __name__ == "__main__":
    inv = json.load(open(os.path.join(
        HERE, "vintage_numeric_inventory_d6_8_3.json"), encoding="utf-8"))
    r = freeze_record(inv["inventory_sha256"])
    print("vintage reader frozen:", r["freeze_sha256"])
    for t, want in (("六一五七", "6157"), ("四一一○", "4110"),
                    ("八○一七", "8017"), ("六千一百五十七", None),
                    ("五七二", None)):
        print("  code %-8s -> %s" % (t, cjk_code_to_digits(t)),
              "OK" if cjk_code_to_digits(t) == want else "MISMATCH")
    for t, want in (("九十二", 92), ("一○一", 101), ("二十五", 25),
                    ("一百", 100), ("十二", 12), ("三十一", 31), ("九十", 90),
                    ("二○○五", 2005), ("七二十一", None)):
        got = cjk_calendar_int(t)
        print("  date %-6s -> %s" % (t, got),
              "OK" if got == want else "MISMATCH")
