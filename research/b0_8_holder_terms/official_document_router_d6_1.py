# -*- coding: utf-8 -*-
"""B0.8 · D6.1 · discovery conformance + body acquisition completeness.

FROZEN BEFORE THE D6.1 CLASSIFICATION RUN.

The completed D4-D10 v1.4 census is HISTORICAL EVIDENCE and is not rewritten.
Its counts (5 UNIQUE / 144 NONE / 9 AMBIGUOUS / 0 ERROR), its predicates and its
source are preserved byte-for-byte in d6_1_historical/ with sha256s in
SEALED_EVIDENCE_HASHES.json. This module is a SEPARATE router; v1.4's source is
never edited. B0.8 remains WIP and unsealed.

WHAT LATER AUDIT FOUND, RECORDED AS RULED

    three discovery under-inclusions
      A  the authoritative exchange termination phrase 「終止櫃檯買賣」 was not in
         the event-linkage vocabulary, so TPEx-lineage terminations announced in
         the exchange's own words did not register as event linkage
      B  linkage was tested per DOCUMENT, while the corpus routinely SPLITS it:
         the termination announcement names no counterparty and the
         share-transfer announcement names no termination
      C  transaction-party extraction was positional, not role-based, so any
         legal company name standing near a transaction marker became a
         candidate -- including 臺灣證券交易所股份有限公司, the exchange the
         filing was addressed to

    one acquisition-state conflation
      OFFICIAL_EVENT_DOCUMENT_NONE conflated two different states: an event for
      which no official document was DISCOVERED, and an event whose documents
      were discovered but whose BODIES were never ACQUIRED. 635 of 781 bodies
      were withheld by the source, so most of v1.4's NONE population was never
      a statement about the record -- it was a statement about acquisition.
      D6.1 separates discovery state from acquisition state and reports both.

CORRECTIONS ACCEPTED (A, B, C), APPLIED EXACTLY AS RULED

A is one phrase. The v1.4 sensitivity diagnostic also flagged 「核准本公司股票終
止」 in 7 documents; it was NOT ruled and is NOT added here.

B introduces AUTHORITATIVE_EVENT_DOCUMENT_BUNDLE: the official announcements of
ONE filer inside ONE frozen discovery window jointly establish event linkage.
The bundle is not a search -- its membership is exactly the documents the frozen
D4 window already discovered for that event, so it widens what those documents
can JOINTLY establish without widening what was acquired.

C makes party extraction role-based. A name is a transaction party only if a
ROLE pattern captures it -- 與X合併 / X為存續公司 / 存續公司：X / 轉換為X之股份 --
and it is discarded if it is a market operator, a filing recipient, a service
provider named in a service role, or page metadata. Being a 股份有限公司 standing
next to the word 合併 is no longer sufficient.

ACQUISITION ROUTES, ENUMERATED AND FROZEN (the completeness question)

  R1  legacy code-keyed detail   mopsov ajax_t05st01 step=2
      REFUSES this population. Verified on a deterministically chosen withheld
      document across TYPEK all/sii/otc/pub/rotc/empty: identical
      「該 NNNN 公開發行公司不繼續公開發行！」, 2,528 bytes each.

  R2  MOPS v2 code-keyed list    POST /mops/api/t05st01
      SERVES this population. This is new and it narrows v1.4's finding 1: it is
      the LEGACY code-keyed doors that are shut, not every code-keyed door. The
      v2 list returns a deregistered company's historical announcements by code
      with year+month, and its rows carry serialNumber / enterDate / marketKind,
      which reconstruct the same document identity the D4 sweep recorded. Used
      here for the DISCOVERY CONFORMANCE check.

  R3  MOPS v2 detail             POST /mops/api/t05st01_detail
      REFUSES, with the same message as R1.

DOCUMENT IDENTITY NORMALISATION (D6.1 -> D6.1.1)

The first D6.1 pass reported 17 events where the code-keyed and date-keyed
corpora disagreed, with a suspiciously symmetric 52 documents "only in the
sweep" and 52 "only in v2". They are the SAME 52 documents. The legacy onclick
hands back spoke_time unpadded (82847) while the v2 row publishes it as a clock
time (08:28:47 -> 082847), so one document acquired two identities and was
assessed twice. Identity is now normalised -- spoke_time zero-padded to six
digits -- before the two corpora are compared. This is an identity bug, not a
predicate change: it does not alter what any document says, only how many
documents there are.

  R4  MOPS v2 signed redirect    POST /mops/api/redirectToOld
      Returns a signed mopsov t05st01_detail URL. That endpoint is UNREACHABLE
      from this network path -- the connection is closed without a response for
      a LIVE control company as well as for this population, so it is a
      transport block, not a source refusal. R4 is therefore recorded as
      UNTESTED_END_TO_END rather than as a refusal, and body acquisition
      completeness is reported with that gap named.
"""
from __future__ import annotations

import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import official_document_router as V14      # noqa: E402  (v1.4, never edited)

ROUTER = "B0_8_OFFICIAL_DOCUMENT_ROUTER_D6_1"
ROUTER_VERSION = "D6.1.1"
PARENT_ROUTER_SHA256 = ("e04f411171a472a2e459aee61570afdb5cff7f4a"
                        "626b729dd992e00516dd059b")
PRESERVED_V14_CENSUS_SHA256 = ("f11abea08466d46988fd63500c507c0d3955eae7"
                               "109a54dac0865eced6ec8ddb")

# --- A · event vocabulary ----------------------------------------------------

EVENT_MARKERS: tuple[str, ...] = V14.EVENT_MARKERS + ("終止櫃檯買賣",)

# --- transaction vocabulary, unchanged from v1.4 -----------------------------

TRANSACTION_MARKERS_SPECIFIC = V14.TRANSACTION_MARKERS_SPECIFIC
TRANSACTION_MARKERS_CONTEXTUAL = V14.TRANSACTION_MARKERS_CONTEXTUAL
ACCOUNTING_SENSE_SUFFIXES = V14.ACCOUNTING_SENSE_SUFFIXES
transaction_marker_spans = V14.transaction_marker_spans

# --- C · role-based transaction-party extraction -----------------------------

_NAME = r"([一-鿿A-Za-z0-9（）()\-\.·]{2,30}?(?:股份有限公司|有限公司))"

# Each pattern names a ROLE the party plays in the transaction. A name that no
# role pattern captures is not a candidate, however close it stands to 合併.
ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("counterparty_to_the_transaction",
     r"與\s*" + _NAME + r"[^。；;]{0,20}?(?:簡易|吸收|新設)?"
     r"(?:合併|股份轉換|股份交換|概括讓與|概括承受)"),
    ("surviving_company", _NAME + r"\s*(?:為|係|擔任)\s*存續公司"),
    ("surviving_company", r"存續公司\s*[為：:]\s*" + _NAME),
    ("surviving_company", r"合併後(?:之)?存續公司\s*[為：:]?\s*" + _NAME),
    ("extinguished_company", r"消滅公司\s*[為：:]\s*" + _NAME),
    ("share_transfer_acquirer", r"轉換為\s*" + _NAME + r"\s*(?:之)?(?:普通股|股份)"),
    ("share_transfer_acquirer",
     _NAME + r"\s*(?:以|依)[^。；;]{0,20}?(?:股份轉換|換股)方式"),
    ("share_transfer_acquirer", r"(?:讓與|移轉)\s*(?:予|給|至)\s*" + _NAME),
    ("holding_company_formed",
     _NAME + r"\s*(?:之)?(?:100%|百分之百)?\s*(?:持股)?(?:金融)?控股(?:母)?公司"),
)
COMPILED_ROLE_PATTERNS = tuple((role, re.compile(rx))
                               for role, rx in ROLE_PATTERNS)

# Not transaction parties, whatever role pattern happens to catch them.
EXCLUDED_ENTITY_TOKENS: tuple[str, ...] = (
    "臺灣證券交易所", "台灣證券交易所", "證券櫃檯買賣中心", "櫃檯買賣中心",
    "臺灣集中保管結算所", "台灣集中保管結算所", "臺灣期貨交易所",
    "金融監督管理委員會", "證券期貨局", "經濟部", "公開資訊觀測站",
)
# Roles that are about FILING or SERVICING the transaction, not being party to
# it. Tested against the text immediately preceding the name.
SERVICE_ROLE_TOKENS: tuple[str, ...] = (
    "股務代理", "股務", "簽證會計師", "會計師事務所", "律師事務所", "承銷",
    "保管機構", "存託機構", "存託銀行", "受託", "財務顧問", "獨立專家",
    "評價機構", "代理機構", "簽證機構", "報導", "媒體",
)
SERVICE_ROLE_LOOKBACK_CHARS = 24

BUNDLE = "AUTHORITATIVE_EVENT_DOCUMENT_BUNDLE"

# --- the acquisition-state taxonomy (the conflation fix) ---------------------

BODY_RETRIEVED = "BODY_RETRIEVED"
BODY_WITHHELD_BY_SOURCE = "BODY_WITHHELD_BY_SOURCE"
BODY_UNREACHABLE_TRANSPORT = "BODY_UNREACHABLE_TRANSPORT"
ACQUISITION_STATES = (BODY_RETRIEVED, BODY_WITHHELD_BY_SOURCE,
                      BODY_UNREACHABLE_TRANSPORT)

DISCOVERY_NO_DOCUMENT = "NO_OFFICIAL_DOCUMENT_DISCOVERED_IN_WINDOW"
DISCOVERY_DOCUMENTS_PRESENT = "OFFICIAL_DOCUMENTS_DISCOVERED"

NONE_NO_DOCUMENTS = "NONE_NO_DOCUMENT_DISCOVERED"
NONE_LINKAGE_NOT_ESTABLISHED = "NONE_DISCOVERED_BUT_LINKAGE_NOT_ESTABLISHED"

# --- acquisition routes ------------------------------------------------------

MOPS_V2_LIST = "https://mops.twse.com.tw/mops/api/t05st01"
MOPS_V2_DETAIL = "https://mops.twse.com.tw/mops/api/t05st01_detail"
MOPS_V2_REDIRECT = "https://mops.twse.com.tw/mops/api/redirectToOld"
V2_HEADERS = {"User-Agent": "Mozilla/5.0",
              "Content-Type": "application/json",
              "Referer": "https://mops.twse.com.tw/mops/"}

ACQUISITION_ROUTES = (
    {"id": "R1", "endpoint": V14.MOPS_ANNOUNCEMENTS + " (step=2)",
     "serves_this_population": False,
     "evidence": "identical 2,528-byte 不繼續公開發行 refusal across TYPEK "
                 "all/sii/otc/pub/rotc/empty on a deterministically chosen "
                 "withheld document"},
    {"id": "R2", "endpoint": MOPS_V2_LIST, "serves_this_population": True,
     "evidence": "returns historical announcements by code for 8913, 3299, "
                 "2888 and 1262; used for the discovery conformance check"},
    {"id": "R3", "endpoint": MOPS_V2_DETAIL, "serves_this_population": False,
     "evidence": "same 不繼續公開發行 refusal as R1"},
    {"id": "R4", "endpoint": MOPS_V2_REDIRECT + " -> mopsov t05st01_detail",
     "serves_this_population": "UNTESTED_END_TO_END",
     "evidence": "the signed URL is issued, but the target endpoint closes the "
                 "connection without a response for a LIVE control company as "
                 "well, so the block is transport, not refusal"},
)


def roc_compact(d) -> str:
    """date -> '1090116', the enterDate the v2 API uses."""
    return "%d%02d%02d" % (d.year - 1911, d.month, d.day)


def document_id(co_id: str, spoke_date: str, spoke_time: str,
                seq_no: str) -> str:
    """Canonical document identity, comparable across both surfaces.

    spoke_time is zero-padded because the legacy surface drops the leading zero
    and the v2 surface does not; without this the same announcement acquires two
    identities and is assessed twice.
    """
    return "MOPS-T05ST01:%s:%s:%s:%s" % (
        co_id, spoke_date, str(spoke_time).zfill(6), str(seq_no))


def canonicalize_document_id(did: str) -> str:
    """Normalise a v1.4-era identity to the canonical form."""
    parts = did.split(":")
    if len(parts) != 5:
        return did
    return document_id(parts[1], parts[2], parts[3], parts[4])


def transaction_parties(text: str, filer_names: tuple[str, ...]) -> list[dict]:
    """C · names captured in a transaction ROLE, minus operators and servicers."""
    out, seen = [], set()
    for role, rx in COMPILED_ROLE_PATTERNS:
        for m in rx.finditer(text):
            name = m.group(1).strip()
            if any(tok in name for tok in EXCLUDED_ENTITY_TOKENS):
                continue
            if any(f and (f in name or name in f) for f in filer_names if f):
                continue
            lo = max(0, m.start(1) - SERVICE_ROLE_LOOKBACK_CHARS)
            if any(tok in text[lo:m.start(1)] for tok in SERVICE_ROLE_TOKENS):
                continue
            if name in seen:
                continue
            seen.add(name)
            out.append({"name": name, "role": role})
    return out


def assess_document(text: str, filer_names: tuple[str, ...]) -> dict:
    """D6.1 assessment of ONE document. Bundle logic is at event level."""
    ev = [m for m in EVENT_MARKERS if m in text]
    spans = transaction_marker_spans(text)
    tx = sorted({m for _, _, m in spans})
    parties = transaction_parties(text, filer_names)
    stock = [m for m in V14.STOCK_CONSIDERATION_MARKERS if m in text]
    cash = [m for m in V14.CASH_CONSIDERATION_MARKERS if m in text]
    consideration = ("mixed" if stock and cash else "stock" if stock
                     else "cash" if cash else "none_apparent")
    fields = {k: any(x in text for x in v)
              for k, v in V14.FIELD_MARKERS.items()}
    return {
        "event_markers": ev,
        "transaction_markers": tx,
        "transaction_parties": parties,
        "establishes_event": bool(ev),
        "establishes_transaction": bool(tx),
        "links_alone": bool(ev and tx),
        "apparent_consideration": consideration,
        "stock_markers": stock,
        "cash_markers": cash,
        "apparent_fields_present": fields,
        "apparent_fields_absent": sorted(k for k, v in fields.items() if not v),
    }


def classify_bundle(assessments: list[dict]) -> dict:
    """B · the event's own documents, judged jointly.

    Linkage is established when the bundle contains a document establishing the
    event and a document establishing the transaction -- the same document or
    two of them. Uniqueness is then decided on the role-based parties named
    ANYWHERE in the bundle.
    """
    if not assessments:
        return {"classification": V14.DOC_NONE,
                "discovery_state": DISCOVERY_NO_DOCUMENT,
                "none_reason": NONE_NO_DOCUMENTS, "linkage": None,
                "parties": [], "bundle_size": 0}
    ev_docs = [a for a in assessments if a["establishes_event"]]
    tx_docs = [a for a in assessments if a["establishes_transaction"]]
    single = [a for a in assessments if a["links_alone"]]
    if not (ev_docs and tx_docs):
        return {"classification": V14.DOC_NONE,
                "discovery_state": DISCOVERY_DOCUMENTS_PRESENT,
                "none_reason": NONE_LINKAGE_NOT_ESTABLISHED,
                "linkage": None, "parties": [],
                "bundle_size": len(assessments)}
    parties, seen = [], set()
    for a in (single or assessments):
        for p in a["transaction_parties"]:
            if p["name"] not in seen:
                seen.add(p["name"])
                parties.append(p)
    linkage = "SINGLE_DOCUMENT" if single else BUNDLE
    if len(parties) == 1:
        cls = V14.DOC_UNIQUE
        reason = None
    else:
        cls = V14.DOC_AMBIGUOUS
        reason = (V14.AMBIGUOUS_NO_COUNTERPARTY if not parties
                  else V14.AMBIGUOUS_MULTIPLE)
    return {"classification": cls,
            "discovery_state": DISCOVERY_DOCUMENTS_PRESENT,
            "none_reason": None, "ambiguity_reason": reason,
            "linkage": linkage, "parties": parties,
            "bundle_size": len(assessments),
            "event_documents": len(ev_docs),
            "transaction_documents": len(tx_docs)}


def router_identity() -> dict:
    from core.b0_canonical_hash import canonical_sha256

    payload = {
        "router": ROUTER,
        "version": ROUTER_VERSION,
        "parent_router_sha256": PARENT_ROUTER_SHA256,
        "preserved_v1_4_census_sha256": PRESERVED_V14_CENSUS_SHA256,
        "b0_8_state": "WIP, UNSEALED",
        "correction_A_event_markers_added": ["終止櫃檯買賣"],
        "correction_A_flagged_but_not_ruled_not_added": ["核准本公司股票終止"],
        "correction_B_bundle": {
            "name": BUNDLE,
            "membership": "the documents the frozen D4 window already "
                          "discovered for that event/filer",
            "rule": "linkage holds when the bundle contains a document "
                    "establishing the event and a document establishing the "
                    "transaction; uniqueness is decided on the role-based "
                    "parties named anywhere in the bundle",
        },
        "correction_C_role_based": {
            "role_patterns": [[r, rx] for r, rx in ROLE_PATTERNS],
            "excluded_entity_tokens": list(EXCLUDED_ENTITY_TOKENS),
            "service_role_tokens": list(SERVICE_ROLE_TOKENS),
            "service_role_lookback_chars": SERVICE_ROLE_LOOKBACK_CHARS,
        },
        "acquisition_state_taxonomy": list(ACQUISITION_STATES),
        "none_decomposition": [NONE_NO_DOCUMENTS, NONE_LINKAGE_NOT_ESTABLISHED],
        "acquisition_routes": list(ACQUISITION_ROUTES),
        "event_markers": list(EVENT_MARKERS),
        "transaction_markers_specific": list(TRANSACTION_MARKERS_SPECIFIC),
        "transaction_markers_contextual": list(TRANSACTION_MARKERS_CONTEXTUAL),
        "discovery_window_unchanged": True,
        "document_identity_normalisation": (
            "spoke_time zero-padded to six digits so the legacy and v2 "
            "surfaces name the same announcement identically"),
        "not_authorized_in_this_stage": [
            "holder-term extraction", "reconstruction classification",
            "CA rebuild", "state rebuild", "replay", "NAV", "performance",
            "gates",
        ],
    }
    return {"payload": payload, "router_sha256": canonical_sha256(payload)}
