# -*- coding: utf-8 -*-
"""B0.8 · D7.1b · V3 · ROUTING-ONLY SUCCESSOR IDENTITY, PROPERLY EXTRACTED.

WHY THIS SUPERSEDES D7.1a's V3 BLOCK

D7.1a took "every validated legal entity in the bundle, minus the disappearing
entity's lineage" and hoped one name would be left. It never is. An official
merger announcement also names the share registrar, the central depository and
four securities-finance companies, and the extractor's own leading-noise problem
turned the real answer into strings like

    三六股)合併換發華新科技股份有限公司

which match nothing. Result: 15 of 30 identities, 4 of 30 codes -- a measurement
of the extractor, not of the archive. D7.1a's V2 leg census is unaffected and
stands; only its V3 block is superseded.

THE RELATION IS WHAT IDENTIFIES A SUCCESSOR, NOT ABSENCE FROM A LINEAGE

A successor is the entity an authoritative document places on the other side of
the transaction, through the document's own vocabulary:

    與X合併        被X吸收合併      合併換發X股票
    X為存續公司     存續公司X        與X進行股份轉換
    股份轉換為X     由X概括承受      讓與X

Each pattern anchors the name immediately after the relation word, so the name
boundary comes from the construction rather than from a guess. A registrar named
as 股務代理人 is never in one of these positions, which is why role noise
disappears by construction rather than by a blocklist -- one is kept anyway, and
reported, as a check.

CODE RESOLUTION USES FIRST-PARTY DIRECTORIES ONLY

    1  the code-to-legal-name bindings TPEx prints in its own announcements
    2  the MOPS company directory (ajax_autoComplete), the same first-party
       surface E1 used

    never: TEJ, price history, who ended up owning the company, fuzzy name
           similarity, market outcome

V10 · POSITIVE CONTROL

TDCC's historical 發行公司合併換票一覽表 (STK003) covers ROC 93-97 and names the
存續公司 with its code. It is used here ONLY to check the extraction against an
independent first-party record for the vintage it covers. It is not the source
of identity, and nothing is inferred from it about post-2009 availability.

Everything emitted is DISCOVERY_METADATA_ONLY.

    python research/b0_8_holder_terms/successor_identity_routing_d7_1b.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402
from source_native_locator_census_d6_8_2 import index_rows  # noqa: E402
import entity_identity_conformance_repair_d6_8_1 as R3     # noqa: E402
import vintage_numeric_reader_d6_8_3 as VR                 # noqa: E402
from stock_leg_population_d7_1a import bind_any            # noqa: E402

D71A = os.path.join(HERE, "stock_leg_population_d7_1a.json")
D683 = os.path.join(HERE, "repaired_reader_rerun_d6_8_3.json")
STK003 = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                      "d7_0c_tdcc_raw", "SM-STK003.xls")
INDEX_OUT = os.path.join(REPO, "artifacts", "b0_8_holder_terms",
                         "d7_1b_code_name_index.json")
OUT = os.path.join(HERE, "successor_identity_routing_d7_1b.json")

MOPS = "https://mopsov.twse.com.tw/mops/web/ajax_autoComplete"
MOPS_HEADERS = {"User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01"}
POLITE = 0.6

N = r"(%s{2,30}?有限公司)" % R3.NAME_CH
_PRE = r"(?:上市公司|上櫃公司|興櫃公司)?\s*"
# Frozen from the standard legal phrasings TPEx uses in 終止上櫃 announcements
# for merger and share-conversion, measured over the linked bundles and gated
# on the STK003 cross-vintage control (2004 rows) matching 2016-2023 events.
RELATIONS = (
    ("SHARES_EXCHANGED_FOR", r"(?:合併)?換發\s*" + N + r"(?:增資發行)?"
     r"(?:普通股|股票|新股)"),
    # 成為 X : X is the acquirer in a share conversion. The 子公司 tail sits
    # far past the successor's own inline code label, so the name is anchored on
    # 成為 alone; an anaphoric 成為其…子公司 carries no name and fails validation.
    ("BECOMES", r"成為\s*" + _PRE + N),
    ("RECEIVES_SHARES", r"由\s*" + _PRE + N + r"[^。]{0,40}?受讓"),
    ("ABSORBED_BY", r"被\s*" + _PRE + N),
    ("MERGED_WITH", r"與\s*" + _PRE + N + r"[^。]{0,30}?合併"),
    ("SHARE_CONVERSION_WITH", r"與\s*" + _PRE + N +
     r"[^。]{0,30}?(?:股份轉換|轉換成為)"),
    ("SHARE_CONVERSION_BY", r"由\s*" + _PRE + N +
     r"[^。]{0,30}?(?:股份轉換|概括承受|合併)"),
    ("SURVIVOR_NAMED", N + r"為存續公司"),
    ("SURVIVOR_NAMED", r"存續公司[為:：]?\s*" + N),
    ("SHARE_CONVERSION", r"股份轉換[為給予]\s*" + N),
    ("TRANSFERRED_TO", r"讓與\s*" + N),
)
# a successor named with its code in the same clause -> first-party code, in-doc
INLINE_CODE = r"\s*[（(][^）)]{0,12}?(?:股票代號|證券代號|代號)[：:\s]*(\d{4})"
ROLE_NOISE = ("股務代理", "證券金融", "證券集中保管", "期貨交易所",
              "櫃檯買賣中心", "證券交易所", "存託", "簽證")


def successors_in(text, lineage):
    """Every entity an authoritative relation puts on the other side.

    When the successor's name is immediately followed by its own code label in
    the same clause, that in-document code is captured as first-party evidence.
    """
    found = defaultdict(set)
    inline = defaultdict(set)
    noise = []
    for role, pat in RELATIONS:
        for m in re.finditer(pat, text):
            name = R3.validate_name(m.group(1))
            if not name or name in lineage:
                continue
            if any(x in name for x in ROLE_NOISE):
                noise.append(name)
                continue
            found[name].add(role)
            tail = re.match(INLINE_CODE, text[m.end(1):m.end(1) + 24])
            if tail:
                inline[name].add(tail.group(1))
    return ({k: sorted(v) for k, v in found.items()},
            {k: sorted(v) for k, v in inline.items()},
            sorted(set(noise)))


def mops_directory(name):
    """First-party company directory lookup.

    The autoComplete surface resolves on the SHORT name, not the full legal
    name, and carries the code inside goaction('CODE') plus "CODE <span>short".
    The legal name is stripped of its corporate suffix before querying.
    """
    short = re.sub(r"股份有限公司$", "", name)
    body = urllib.parse.urlencode({
        "firstin": "1", "TYPEK": "all", "step": "1", "co_id": "",
        "funcName": "t05st01", "searchtype": "", "inpuType": "keyword",
        "keyword": short}).encode()
    try:
        req = urllib.request.Request(MOPS, data=body, headers=MOPS_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as exc:                                # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:120]), short
    hits = []
    for code in re.findall(r"goaction\(\s*'(\d{4,6})'", raw):
        m = re.search(re.escape(code) + r"\s*<span[^>]*>([^<]{1,20})", raw)
        hits.append({"code": code, "name": m.group(1).strip() if m else None})
    return hits, None, short


def stk003_control():
    """TDCC 發行公司合併換票一覽表, ROC 93-97. Positive control only."""
    import shutil
    import tempfile
    import openpyxl
    tmp = os.path.join(tempfile.gettempdir(), "d7_1b_stk003.xlsx")
    shutil.copyfile(STK003, tmp)
    wb = openpyxl.load_workbook(tmp, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    out, header = {}, None
    for row in ws.iter_rows(values_only=True):
        v = ["" if x is None else str(x).strip() for x in row]
        if not header:
            if "證券代號" in v:
                header = {k: i for i, k in enumerate(v) if k}
            continue
        code = v[header["證券代號"]] if "證券代號" in header else ""
        if not re.fullmatch(r"\d{4}", code):
            continue
        surv = v[header.get("存續公司\n(名稱， 代號)", -1)] if header.get(
            "存續公司\n(名稱， 代號)") is not None else ""
        m = re.match(r"(\d{4})\s*(.+)", surv)
        out[code] = {
            "survivor_raw": surv,
            "survivor_code": m.group(1) if m else None,
            "survivor_name": m.group(2).strip() if m else surv or None,
            "new_share_listing_date": v[header["新股上市(櫃)日期"]]
            if "新股上市(櫃)日期" in header else "",
            "exchange_ratio": v[header["換票比率"]]
            if "換票比率" in header else "",
        }
    return out


def main() -> int:
    d71a = json.load(open(D71A, encoding="utf-8"))
    d683 = json.load(open(D683, encoding="utf-8"))
    ev683 = {e["security_id"]: e for e in d683["results"]}
    pop = [r for r in d71a["results"]
           if r["transaction_leg"] in ("STOCK_LEG_PRESENT",
                                       "MIXED_LEG_PRESENT")]
    print("population: %d stock/mixed events" % len(pop), flush=True)

    rows, _ = index_rows()
    by_loc = {r["doc_id"]: r for r in rows}

    if os.path.exists(INDEX_OUT):
        index = json.load(open(INDEX_OUT, encoding="utf-8"))
        print("code->name index reused: %d codes" % len(index), flush=True)
    else:
        cn = defaultdict(Counter)
        for i, (did, row) in enumerate(sorted(by_loc.items()), 1):
            text, _s = VR.body_text(row)
            if not text:
                continue
            for code, name in bind_any(text):
                cn[code][name] += 1
            if i % 20000 == 0:
                print("   indexed %d/%d" % (i, len(by_loc)), flush=True)
        index = {c: R3.collapse(list(n)) for c, n in cn.items()}
        os.makedirs(os.path.dirname(INDEX_OUT), exist_ok=True)
        with open(INDEX_OUT, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(index, fh, ensure_ascii=False, sort_keys=True)
        print("code->name index built: %d codes" % len(index), flush=True)
    name_codes = defaultdict(set)
    for c, names in index.items():
        for n in names:
            name_codes[n].add(c)

    control = stk003_control()
    print("STK003 control rows: %d" % len(control), flush=True)

    results, ident, secid, mops_used = [], Counter(), Counter(), 0
    for r in pop:
        sid = r["security_id"]
        ev = ev683[sid]
        lineage = set(r["disappearing_lineage"])
        linked_text, est_text = "", ""
        for c in ev["candidates"]:
            t, _s = VR.body_text(by_loc[c["doc_id"]])
            if not t:
                continue
            if c["doc_id"] in ev["linked"]:
                linked_text += t
            if c["gate_i"] == "ENTITY_IDENTITY_ESTABLISHED":
                est_text += t

        found, inline, noise = successors_in(linked_text, lineage)
        scope = "LINKED_BUNDLE"
        if not found:
            found, inline, noise2 = successors_in(est_text, lineage)
            noise += noise2
            scope = "GATE_I_ESTABLISHED_CANDIDATES" if found else None
        names = R3.collapse(list(found)) if found else []

        succ = names[0] if len(names) == 1 else None
        # strongest evidence: the successor's code printed in the same clause
        codes, source = [], None
        if succ and inline.get(succ):
            codes = inline[succ]
            source = "IN_DOCUMENT_CODE_LABEL"
        elif succ:
            codes = sorted(name_codes.get(succ, []))
            source = "TPEX_CORPUS_BINDING" if codes else None
        mops_hits, mops_err = None, None
        if succ and not codes:
            mops_hits, mops_err, short = mops_directory(succ)
            mops_used += 1
            time.sleep(POLITE)
            if mops_hits:
                exact = [h for h in mops_hits
                         if h["name"] and (h["name"] == short
                                           or short.startswith(h["name"])
                                           or h["name"] in succ)]
                if len({h["code"] for h in exact}) == 1:
                    codes = [exact[0]["code"]]
                    source = "MOPS_COMPANY_DIRECTORY"

        ctrl = control.get(sid)
        agree = None
        if ctrl and succ:
            agree = bool(ctrl["survivor_name"]
                         and (ctrl["survivor_name"] in succ
                              or succ.startswith(ctrl["survivor_name"])))
        ident["ESTABLISHED" if succ else "UNRESOLVED"] += 1
        secid["ESTABLISHED" if len(codes) == 1 else "UNRESOLVED"] += 1
        results.append({
            "security_id": sid,
            "transaction_leg": r["transaction_leg"],
            "disappearing_entity": r["disappearing_entity"],
            "relations_found": found,
            "in_document_successor_codes": inline.get(succ, []) if succ else [],
            "extraction_scope": scope,
            "role_noise_rejected": noise,
            "successor_legal_entity": succ,
            "successor_candidates": names,
            "successor_security_id": codes[0] if len(codes) == 1 else None,
            "successor_security_id_candidates": codes,
            "code_resolution_source": source,
            "mops_directory_hits": mops_hits,
            "mops_directory_error": mops_err,
            "identity_established": bool(succ),
            "security_id_established": len(codes) == 1,
            "stk003_control": ctrl,
            "stk003_agrees": agree,
            "provenance": "DISCOVERY_METADATA_ONLY",
        })

    checked = [x for x in results if x["stk003_agrees"] is not None]
    out = {
        "record": "B0_8_D7_1B_SUCCESSOR_IDENTITY_ROUTING",
        "b0_8_state": "WIP, UNSEALED",
        "supersedes": {
            "artefact": "stock_leg_population_d7_1a.json",
            "block": "V3_successor_routing only",
            "v2_leg_census_unaffected": True,
            "d7_1a_census_sha256": d71a["census_sha256"],
            "defect_in_d7_1a": (
                "successor was taken as 'all validated entities minus the "
                "disappearing lineage', which returns registrars, the central "
                "depository and securities-finance companies, and inherited "
                "the leading-noise problem of open-ended name extraction"),
        },
        "extraction_rule": {
            "anchored_on": "the document's own transaction-relation vocabulary",
            "relations": sorted({r for r, _ in RELATIONS}),
            "name_boundary_from": "the relation construction, not a guess",
            "role_noise_blocklist": list(ROLE_NOISE),
            "scope_order": ["LINKED_BUNDLE",
                            "GATE_I_ESTABLISHED_CANDIDATES"],
            "linkage_semantics_changed": False,
        },
        "code_resolution": {
            "directories": ["first-party TPEx code-to-legal-name bindings",
                            "MOPS company directory (ajax_autoComplete)"],
            "forbidden": ["TEJ", "price history", "market outcome",
                          "fuzzy name similarity"],
            "mops_lookups_performed": mops_used,
            "tpex_index_codes": len(index),
        },
        "V10_positive_control": {
            "source": "TDCC 發行公司合併換票一覽表 (SM-STK003), ROC 93-97",
            "rows": len(control),
            "population_events_covered": len(checked),
            "agreements": sum(1 for x in checked if x["stk003_agrees"]),
            "disagreements": [x["security_id"] for x in checked
                              if not x["stk003_agrees"]],
            "used_as_identity_source": False,
            "post_2009_equivalent_inferred": False,
            "its_date_field_is": "新股上市(櫃)日期 -> "
                                 "SUCCESSOR_TRADABLE_OR_LISTING_DATE",
            "is_not": "SUCCESSOR_DELIVERY_OR_CREDIT_DATE",
        },
        "summary": {
            "population": len(pop),
            "identity": dict(ident),
            "security_id": dict(secid),
            "unresolved_identity": sorted(x["security_id"] for x in results
                                          if not x["identity_established"]),
            "identity_but_no_code": sorted(
                x["security_id"] for x in results
                if x["identity_established"]
                and not x["security_id_established"]),
        },
        "results": results,

        # V11 invariants
        "canonical_holder_terms_materialized": False,
        "holder_term_values_extracted": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_relaxed": False,
        "cash_leg_source_hunting": False,
        "termination_discovery_branch_reopened": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "nav_inspected": False,
        "performance_inspected": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "artefacts_rewritten": 0,
    }
    out["routing_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    s, c = out["summary"], out["V10_positive_control"]
    print("\nidentity      :", s["identity"])
    print("security_id   :", s["security_id"])
    print("unresolved    :", s["unresolved_identity"])
    print("id but no code:", s["identity_but_no_code"])
    print("STK003 control: %d events covered, %d agree, disagree %s"
          % (c["population_events_covered"], c["agreements"],
             c["disagreements"]))
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
