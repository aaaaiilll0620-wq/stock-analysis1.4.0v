# -*- coding: utf-8 -*-
"""B0.8 · D3 · the frozen CODE-FIRST official-document router.

FROZEN BEFORE ANY CORPUS REQUEST IS ISSUED.

WHY CODE-FIRST

The E1 census measured one thing: whether the MOPS autocomplete resolver can
turn an authoritative disappearing-company NAME into a current entity. 61 of
the 158 register events had no such name available, and that was reported as
AUTHORITATIVE_NAME_INPUT_UNAVAILABLE -- a label that reads like a statement
about authoritative sources in general when it is only a statement about E1's
input. D1 renames it accordingly and this router removes the dependency: the
primary key is the security's own CODE, which every event has by construction.

    PRIMARY INPUTS      security_id
                        canonical event / disappearance date  (C)
                        authoritative market lineage, itself derived code-first

    NEVER AN INPUT      the disappearing company's name
                        TEJ counterparty narrative or any vendor dataset
                        B0 holdings, claim exposure, price, NAV, performance
                        which event blocks the replay, and 8913's identity

D1 · WHAT `NO_TPEX_OPENAPI_DELISTED_DIRECTORY` DID AND DID NOT ESTABLISH

The feasibility stage enumerated 225 TPEx OpenAPI endpoints and found none for
terminated companies. That is true and it is narrow. TPEx publishes an
authoritative 終止上櫃公司 directory OUTSIDE the OpenAPI surface, on the
market-data site itself, and it is code-queryable:

    POST https://www.tpex.org.tw/www/zh-tw/company/deListed
         code=<security_id>  date=<year>  reason=-1

512 rows, ROC 84 (1995) through 115 (2026), carrying the official full company
name, the 終止上櫃日期 and the legal clause the termination was made under --
including the two reason groups this repair is about:

    0  被合併或參與股份轉換而終止上櫃之公司
    1  參與轉換設立金控而終止上櫃之公司

So NO_TPEX_OPENAPI_DELISTED_DIRECTORY must never be read as
NO_AUTHORITATIVE_TPEX_HISTORICAL_SOURCE. Both statements are preserved
separately in the census provenance.

THE THREE SURFACE FINDINGS THAT SHAPED THIS ROUTER

They were established with control queries against codes and dates, before the
census, and they are recorded because each of them could otherwise be mistaken
for an absence of documents:

  1. Every code-keyed MOPS announcement surface REFUSES this population.
     `ajax_t05st01` with co_id, `ajax_t05st03` with co_id and the eZsearch
     公告快易查 index all answer 「該 NNNN 公開發行公司不繼續公開發行！」 or
     「查無公司資料」 for a company that has ceased public offering -- which is
     every disappearing security here, by definition. A router that queried
     MOPS by code alone would report NONE corpus-wide and the reason would be
     the query, not the record.

  2. The DATE-keyed MOPS surface retains them. `ajax_t05st01` without co_id
     returns every company's material announcements for a date range, and a
     control day (109/01/13) carries rows for seven companies that have since
     been delisted. The document is there; only the code-keyed door is shut.
     So the router selects BY CODE inside a DATE-keyed response.

  3. The date-keyed surface accepts a RANGE, not only a single day. The
     feasibility stage recorded 「未指定公司代號時，僅能查詢單日重大訊息」 and
     concluded single-day-only. That was the response to full-date b_date /
     e_date values; with b_date and e_date as DAY-OF-MONTH inside a chosen
     year+month, a multi-day range is served. This is a correction of the
     earlier record, not a new surface.

  4. TYPEK=all is required. sii ∪ otc is NOT the whole market: on the control
     day 33 of 173 rows were filed under `pub` (公開發行), including rows from
     companies that were listed at the time. Partitioning by market lineage to
     halve the payload would have silently dropped documents.

WINDOW, FROZEN HERE (D3: "if a source requires a date window, freeze that
window before issuing corpus requests")

    W = [C - 30 days, C + 20 days]

C is the canonical disappearance date in the frozen register. The forward
半 of the window is not decoration: the authoritative exchange termination date
runs 5..13 days AFTER C for every one of the 156 events where a directory
supplies it, because C is the last trading day and the exchange terminates the
listing afterwards. The window is anchored on C rather than on the exchange
date so that it is defined identically for the events where no directory row
exists. It is a DISCOVERY window and it is deliberately not widened to reach
the board-resolution announcement that typically carries the exchange ratio --
that is extraction, which D5 forbids at this stage.

ROUTER CORRECTIONS, RECORDED RATHER THAN QUIETLY APPLIED (v1 -> v1.2)

Three defects in the frozen D6 predicates were found before any document from
the 158-event population was assessed -- (a) and (b) by reading the predicates
back, (c) from CONTROL documents drawn from companies that are NOT in the
register. No population document had been read, so none of these corrections
can have been shaped by an outcome:

  a. COUNTERPARTY EXTRACTION SWALLOWED THE PRECEDING CHARACTER. The name
     pattern is leftmost-first, so 「與台積電股份有限公司合併」 yielded the token
     "與台積電股份有限公司". Two documents naming the same counterparty through
     different connectives would then have looked like two different entities,
     i.e. AMBIGUOUS by punctuation. Leading connectives and quotation marks are
     now stripped.

  b. UNIQUENESS WAS TESTED ON THE WRONG SET. v1 asked whether the document
     mentions exactly one company other than the filer. Termination
     announcements routinely also name a 股務代理機構, a parent, or a subsidiary,
     so that test would have reported AMBIGUOUS for documents that name the
     merger counterparty perfectly clearly. D6 asks whether the document
     uniquely links the security, THE TRANSACTION and the event -- so a
     counterparty now counts only when it occurs within
     COUNTERPARTY_PROXIMITY_CHARS of a transaction marker, and AMBIGUOUS
     carries the reason it was ambiguous.

  d. THE CODE-KEYED DOOR IS SHUT ON THE DETAIL VIEW TOO, AND v1.2 READ THE
     REFUSAL AS IF IT WERE THE DOCUMENT. This one was found from the census
     output, after the first pass, and it is a DEFECT rather than a predicate
     preference: 550 of the 781 preserved bodies were MOPS's 2,528-byte
     「該 NNNN 公開發行公司不繼續公開發行！」 page. Finding 1 said the code-keyed
     LIST surface refuses this population; the step-2 DETAIL view is code-keyed
     as well, so it refuses them too. v1.2 fed that refusal into
     assess_document, where it read as a document containing no markers -- so
     an event whose announcement row plainly says 「公告櫃檯買賣中心核准本公司股
     票終止櫃檯買賣」 was scored on a page that says nothing.

     A refusal is an ANSWER, not a transport failure, so it does not become
     REQUEST_ERROR. The announcement ROW is itself authoritative published
     content -- it comes from the date-keyed response, it is hash-bound, and it
     carries the subject line -- so a refused document is assessed on its
     preserved row subject and flagged `body_retrieved: false`. What that costs
     is recorded rather than hidden: a subject line can establish discovery, and
     it cannot support the dual extraction D5 defers.

  e. MOPS ANSWERS 200 OK WITH A RATE-LIMIT PAGE, AND v1.3 KEPT IT AS THE
     DOCUMENT. 「Overrun - 查詢過於頻繁,請稍後再試!!」 is served with a normal
     status, so the retry logic never saw a failure: 106 of the 781 preserved
     bodies were that page, including the one document that states 3299's
     transaction outright. This is a transport failure wearing a 200, and it is
     now detected, retried with escalating backoff, and never cached.
     The 518 date-keyed block responses were checked for the same
     contamination and are clean -- smallest 110 KB, none empty, none errored --
     so WHICH events have announcements was never in doubt; only the bodies
     were.

  c. 「合併」 IS TWO DIFFERENT WORDS. In a control block, 136 of the
     announcements matching the v1 transaction markers were 合併財務報表 --
     CONSOLIDATED financial statements, an accounting term that shares the
     merger character. A quarterly-results announcement filed inside the
     window by a company that also happened to announce a delisting would have
     been counted as a transaction document. 合併 in the accounting sense is now
     excluded by the phrase that follows it, and the unambiguous merger tokens
     the MOPS templates actually use -- 存續公司 / 消滅公司 / 合併基準日 /
     股份轉換基準日 -- are matched in their own right.

     The same controls confirmed the shape this stage relies on: MOPS material
     announcements are numbered templates, and a reorganisation one states the
     counterparty in a fixed position (「本公司為消滅公司，○○股份有限公司為存續
     公司」). That is what makes a document-level linkage test possible at all.

REQUEST SEGMENTATION. MOPS ranges live inside one year+month, so W is cut into
fixed calendar day-blocks 01-10 / 11-20 / 21-EOM. The blocks are shared between
events, fetched once and hashed once.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

ROUTER = "B0_8_OFFICIAL_DOCUMENT_ROUTER"
ROUTER_VERSION = "1.4"

# --- primary authoritative surfaces ------------------------------------------

TWSE_TERMINATION_DIRECTORY = (
    "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml")
TPEX_TERMINATION_DIRECTORY = (
    "https://www.tpex.org.tw/www/zh-tw/company/deListed")
MOPS_ANNOUNCEMENTS = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"

# The E1 name resolver. Kept in the record as a FALLBACK corroborator only; this
# stage issues no E1 request at all.
MOPS_E1_NAME_RESOLVER = "https://mopsov.twse.com.tw/mops/web/ajax_autoComplete"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://mopsov.twse.com.tw/mops/web/t05st01",
}
TPEX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": ("https://www.tpex.org.tw/web/regular_emerging/deListed/"
                "de-listed_companies.php?l=zh-tw"),
}

FORBIDDEN_ROUTING_INPUTS: tuple[str, ...] = (
    "disappearing_company_name",
    "tej_counterparty_narrative",
    "third_party_dataset",
    "b0_holdings",
    "b0_claim_exposure",
    "price_or_nav",
    "eventual_performance",
    "whether_the_event_blocks_replay",
    "b0_7_blocker_identity",
)

WINDOW_BACK_DAYS = 30
WINDOW_FORWARD_DAYS = 20
DIRECTORY_MATCH_TOLERANCE_DAYS = 370

# --- lineage classes ---------------------------------------------------------

LINEAGE_TWSE = "TWSE"
LINEAGE_TPEX = "TPEX"
LINEAGE_BOTH = "AMBIGUOUS_BOTH_DIRECTORIES"
LINEAGE_NONE = "LINEAGE_UNRESOLVED"

# --- D5 discovery classes ----------------------------------------------------

DOC_UNIQUE = "OFFICIAL_EVENT_DOCUMENT_UNIQUE"
DOC_NONE = "OFFICIAL_EVENT_DOCUMENT_NONE"
DOC_AMBIGUOUS = "OFFICIAL_EVENT_DOCUMENT_AMBIGUOUS"
DOC_ERROR = "OFFICIAL_EVENT_DOCUMENT_REQUEST_ERROR"
DOC_CLASSES = (DOC_UNIQUE, DOC_NONE, DOC_AMBIGUOUS, DOC_ERROR)

# --- D6 · what makes a document a LINKING document ---------------------------
# Frozen textual predicates. D6 is explicit that a linking document need not
# already satisfy every frozen reconstruction field -- this is discovery, not
# R7 classification -- so the test is about IDENTIFICATION, not completeness.

EVENT_MARKERS: tuple[str, ...] = (
    "終止上市", "終止上櫃", "終止買賣", "停止買賣", "下市", "下櫃",
    "終止有價證券", "最後交易日",
)

# Merger / share-transfer tokens that cannot mean anything else. These are the
# labels the MOPS announcement templates themselves use.
TRANSACTION_MARKERS_SPECIFIC: tuple[str, ...] = (
    "存續公司", "消滅公司", "合併基準日", "合併解散基準日", "合併契約",
    "合併案", "合併換股", "簡易合併", "吸收合併", "新設合併",
    "股份轉換", "股份轉換基準日", "股份交換", "換股基準日", "換股比例",
    "概括讓與", "概括承受", "轉換設立", "金融控股公司", "投資控股公司",
)
# Tokens that carry the transaction sense only in context.
TRANSACTION_MARKERS_CONTEXTUAL: tuple[str, ...] = ("合併", "控股公司")
# 合併 in THIS company's accounting sense, not in the corporate-action sense.
ACCOUNTING_SENSE_SUFFIXES: tuple[str, ...] = (
    "財務報表", "財務報告", "財報", "報表", "營收", "營業收入", "損益",
    "資產負債", "現金流量", "個體", "財務資訊", "基礎", "範圍", "報表編製",
    "營業額", "毛利", "總損益", "自結",
)
# Kept as one flat tuple for the freeze record and for proximity scanning.
TRANSACTION_MARKERS: tuple[str, ...] = (
    TRANSACTION_MARKERS_SPECIFIC + TRANSACTION_MARKERS_CONTEXTUAL)

COMPANY_NAME = re.compile(r"[一-鿿（）A-Za-z0-9\-\.·]{2,30}?"
                          r"(?:股份有限公司|有限公司)")
# The leftmost-first match absorbs whatever readable characters precede the
# name, so the token is cut back to the last grammatical delimiter inside it.
NAME_DELIMITERS = "與及和暨或跟由向對為被以自從經至給之稱即是係讓予「」『』（）()，,、：:；;。 \t"
COUNTERPARTY_PROXIMITY_CHARS = 40

# The archive's answer when a code-keyed request names a company that has
# ceased public offering. It is an answer, not an error.
REFUSAL_MARKERS: tuple[str, ...] = ("不繼續公開發行", "查無公司資料",
                                    "查無所需資料", "查無資料")
DOCUMENT_TEMPLATE_MARKER = "本資料由"
BODY_WITHHELD = "DOCUMENT_BODY_WITHHELD_BY_SOURCE"

# Served with HTTP 200, so only the body distinguishes it from a document.
RATE_LIMIT_MARKERS: tuple[str, ...] = ("查詢過於頻繁", "Overrun",
                                       "系統忙碌", "請稍後再試")


def is_rate_limited(text: str) -> bool:
    """True when MOPS answered 200 OK with its throttle page."""
    return any(m in text for m in RATE_LIMIT_MARKERS)


def is_refusal(text: str) -> bool:
    """True when the detail view refused instead of serving the announcement."""
    return (any(m in text for m in REFUSAL_MARKERS)
            and DOCUMENT_TEMPLATE_MARKER not in text)


AMBIGUOUS_NO_COUNTERPARTY = "NO_TRANSACTION_COUNTERPARTY_IDENTIFIED"
AMBIGUOUS_MULTIPLE = "MULTIPLE_TRANSACTION_COUNTERPARTIES"


def transaction_marker_spans(text: str) -> list[tuple[int, int, str]]:
    """Where the document speaks of a reorganisation transaction.

    A contextual token is dropped when the words after it make it the
    accounting sense -- 合併財務報表 is a quarterly result, not a merger.
    """
    spans: list[tuple[int, int, str]] = []
    for marker in TRANSACTION_MARKERS_SPECIFIC:
        start = text.find(marker)
        while start != -1:
            spans.append((start, start + len(marker), marker))
            start = text.find(marker, start + 1)
    for marker in TRANSACTION_MARKERS_CONTEXTUAL:
        start = text.find(marker)
        while start != -1:
            tail = text[start + len(marker):start + len(marker) + 6]
            if not any(tail.startswith(x) for x in ACCOUNTING_SENSE_SUFFIXES):
                spans.append((start, start + len(marker), marker))
            start = text.find(marker, start + 1)
    return sorted(spans)


# --- D7 · consideration markers (DIAGNOSTIC ONLY) ----------------------------

STOCK_CONSIDERATION_MARKERS: tuple[str, ...] = (
    "換股比例", "股份轉換比例", "轉換比例", "換發", "換發新股", "配發",
    "每一股換發", "換股基準日",
)
CASH_CONSIDERATION_MARKERS: tuple[str, ...] = (
    "現金對價", "現金為對價", "每股現金", "以現金", "現金支付", "收購價格",
    "每股價格", "現金補償",
)

# --- D7 · apparent presence of the frozen outcome fields (DIAGNOSTIC ONLY) ---
# Keys are the frozen EXTRACTION_SCHEMA outcome-relevant field names from
# core/b0_holder_side_terms.py. These markers say only that the document
# APPEARS to speak to the field; they do not extract it and they do not decide
# reconstruction_status.

FIELD_MARKERS: dict[str, tuple[str, ...]] = {
    "successor_security_id": ("股票代號", "證券代號", "公司代號", "存續公司",
                              "新設公司", "控股公司"),
    "stock_conversion_ratio": ("換股比例", "股份轉換比例", "轉換比例",
                               "每一股換發", "換發"),
    "cash_consideration_per_old_share": CASH_CONSIDERATION_MARKERS,
    "holder_effective_boundary": ("合併基準日", "股份轉換基準日", "換股基準日",
                                  "終止上市", "終止上櫃", "最後交易日"),
    "settlement_date": ("價款", "給付", "撥付", "匯款", "領取"),
    "successor_credit_date": ("換發基準日", "撥發", "配發基準日", "交付",
                              "上市買賣日", "上櫃買賣日"),
    "successor_tradable_date": ("開始買賣", "上市買賣日", "上櫃買賣日",
                                "掛牌"),
    "fractional_share_treatment": ("不足一股", "畸零股", "零股", "現金補償"),
    "transaction_type": TRANSACTION_MARKERS_SPECIFIC,
    "old_security_id": ("股票代號", "證券代號", "公司代號"),
}


# --- deterministic helpers ---------------------------------------------------

def roc(d: date) -> tuple[str, str, str]:
    """(ROC year, zero-padded month, zero-padded day) as MOPS wants them."""
    return str(d.year - 1911), "%02d" % d.month, "%02d" % d.day


def roc_to_date(s: str) -> date:
    """'109/01/20' or '109-01-20' -> date(2020, 1, 20)."""
    y, m, d = s.replace("/", "-").split("-")
    return date(int(y) + 1911, int(m), int(d))


def window(c: date) -> tuple[date, date]:
    return c - timedelta(days=WINDOW_BACK_DAYS), c + timedelta(
        days=WINDOW_FORWARD_DAYS)


def _eom(y: int, m: int) -> int:
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day


def blocks(lo: date, hi: date) -> list[tuple[int, int, int, int]]:
    """W cut into fixed calendar day-blocks 01-10 / 11-20 / 21-EOM.

    Fixed edges, not a sliding 51-day cut, so that two events a few days apart
    share the identical request and the corpus is fetched once.
    """
    out, y, m = [], lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        last = _eom(y, m)
        for b, e in ((1, 10), (11, 20), (21, last)):
            if date(y, m, e) >= lo and date(y, m, b) <= hi:
                out.append((y, m, b, e))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
ONCLICK = re.compile(r"t05st01_fm\.(\w+)\.value='([^']*)'")
CODE = re.compile(r"\d{4,7}")
ROCDATE = re.compile(r"\d{2,3}/\d{2}/\d{2}")


def _plain(fragment: str) -> str:
    import html as _html
    t = _html.unescape(fragment)
    t = re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("\xa0", " ")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t)).strip()


@dataclass(frozen=True)
class AnnouncementRow:
    co_id: str
    company: str
    spoke_date: str          # 'YYYYMMDD' from the detail parameters
    spoke_date_roc: str      # '109/01/13' as published
    spoke_time: str
    seq_no: str
    typek: str
    subject: str
    raw_fragment: str

    @property
    def document_id(self) -> str:
        return "MOPS-T05ST01:%s:%s:%s:%s" % (
            self.co_id, self.spoke_date, self.spoke_time, self.seq_no)


def parse_announcement_rows(raw: bytes) -> list[AnnouncementRow]:
    """Every announcement row in a date-keyed MOPS response.

    The detail parameters are read out of the row's own onclick handler rather
    than reconstructed, so a document identity can never be manufactured for a
    row the response did not actually carry.
    """
    html_text = raw.decode("utf-8", "replace")
    out: list[AnnouncementRow] = []
    for frag in ROW.findall(html_text):
        cells = [_plain(c) for c in CELL.findall(frag)]
        anchor = None
        for i in range(max(0, len(cells) - 4)):
            if CODE.fullmatch(cells[i]) and ROCDATE.fullmatch(cells[i + 2]):
                anchor = i
                break
        if anchor is None:
            continue
        params = dict(ONCLICK.findall(frag))
        if not params.get("co_id"):
            continue
        out.append(AnnouncementRow(
            co_id=params["co_id"],
            company=cells[anchor + 1],
            spoke_date=params.get("spoke_date", ""),
            spoke_date_roc=cells[anchor + 2],
            spoke_time=params.get("spoke_time", ""),
            seq_no=params.get("seq_no", ""),
            typek=params.get("TYPEK", ""),
            subject=cells[anchor + 4] if len(cells) > anchor + 4 else "",
            raw_fragment=frag))
    return out


def detail_params(row: AnnouncementRow) -> dict:
    """The frozen step-2 instantiation. Code and the row's own coordinates."""
    return {"step": "2", "firstin": "true", "off": "1", "TYPEK": row.typek,
            "co_id": row.co_id, "spoke_date": row.spoke_date,
            "spoke_time": row.spoke_time, "seq_no": row.seq_no}


def list_params(y: int, m: int, b: int, e: int) -> dict:
    """The frozen date-keyed instantiation. TYPEK=all -- see finding 4."""
    return {"step": "1", "firstin": "true", "off": "1", "TYPEK": "all",
            "year": str(y - 1911), "month": "%02d" % m,
            "b_date": "%02d" % b, "e_date": "%02d" % e}


def _hits(text: str, markers: tuple[str, ...]) -> list[str]:
    return [m for m in markers if m in text]


def _normalize_name(tok: str) -> str:
    """Cut the token back to the last grammatical delimiter it contains."""
    cut = max((tok.rfind(ch) for ch in NAME_DELIMITERS), default=-1)
    return tok[cut + 1:].strip() if cut >= 0 else tok.strip()


def counterparties(text: str, filer_names: tuple[str, ...],
                   spans: list[tuple[int, int, str]]) -> tuple[
                       list[str], list[str]]:
    """(all counterparty names, those standing next to a transaction marker).

    Deliberately crude and deliberately visible: the second list decides
    AMBIGUOUS vs UNIQUE, so it must be readable from the preserved bytes alone,
    and both lists are reported so adjudication can see what was read.
    """
    allnames, txnames = [], []
    seen_a, seen_t = set(), set()
    for m in COMPANY_NAME.finditer(text):
        tok = _normalize_name(m.group(0))
        if len(tok) < 6:
            continue
        if any(f and (f in tok or tok in f) for f in filer_names if f):
            continue
        if tok not in seen_a:
            seen_a.add(tok)
            allnames.append(tok)
        lo = m.start() - COUNTERPARTY_PROXIMITY_CHARS
        hi = m.end() + COUNTERPARTY_PROXIMITY_CHARS
        if any(lo <= a and b <= hi for a, b, _ in spans) and tok not in seen_t:
            seen_t.add(tok)
            txnames.append(tok)
    return allnames, txnames


def assess_document(text: str, filer_names: tuple[str, ...]) -> dict:
    """D6 linkage + D7 diagnostics for one preserved document."""
    ev = _hits(text, EVENT_MARKERS)
    spans = transaction_marker_spans(text)
    tx = sorted({m for _, _, m in spans})
    cps, tx_cps = counterparties(text, filer_names, spans)
    stock = _hits(text, STOCK_CONSIDERATION_MARKERS)
    cash = _hits(text, CASH_CONSIDERATION_MARKERS)
    if stock and cash:
        consideration = "mixed"
    elif stock:
        consideration = "stock"
    elif cash:
        consideration = "cash"
    else:
        consideration = "none_apparent"
    fields = {k: bool(_hits(text, v)) for k, v in FIELD_MARKERS.items()}
    return {
        "event_markers": ev,
        "transaction_markers": tx,
        "counterparties": cps,
        "counterparty_count": len(cps),
        "transaction_counterparties": tx_cps,
        "links_security_transaction_and_event": bool(ev and tx),
        "apparent_consideration": consideration,
        "stock_markers": stock,
        "cash_markers": cash,
        "apparent_fields_present": fields,
        "apparent_fields_absent": sorted(k for k, v in fields.items() if not v),
    }


def classify_event(assessments: list[dict], errored: bool) -> str:
    """D5 · the discovery class for one event.

    UNIQUE requires D6's uniqueness: at least one document that links the
    security, a transaction and the event, AND agreement across those documents
    on exactly one counterparty entity. A document that speaks of a merger
    without naming who with does not uniquely link a transaction, so it lands in
    AMBIGUOUS rather than being promoted or discarded.
    """
    if errored:
        return DOC_ERROR
    linking = [a for a in assessments
               if a["links_security_transaction_and_event"]]
    if not linking:
        return DOC_NONE
    named: set[str] = set()
    for a in linking:
        named.update(a["transaction_counterparties"])
    if len(named) == 1:
        return DOC_UNIQUE
    return DOC_AMBIGUOUS


def ambiguity_reason(assessments: list[dict]) -> str | None:
    """Why an AMBIGUOUS event was ambiguous -- reported, never acted on."""
    named: set[str] = set()
    for a in assessments:
        if a["links_security_transaction_and_event"]:
            named.update(a["transaction_counterparties"])
    if not named:
        return AMBIGUOUS_NO_COUNTERPARTY
    if len(named) > 1:
        return AMBIGUOUS_MULTIPLE
    return None


def router_identity() -> dict:
    """A hashable statement of the router, for the pre-census freeze record."""
    from core.b0_canonical_hash import canonical_sha256

    payload = {
        "router": ROUTER,
        "version": ROUTER_VERSION,
        "primary_inputs": ["security_id", "canonical_event_date",
                           "authoritative_market_lineage"],
        "forbidden_routing_inputs": list(FORBIDDEN_ROUTING_INPUTS),
        "primary_surfaces": [TWSE_TERMINATION_DIRECTORY,
                             TPEX_TERMINATION_DIRECTORY, MOPS_ANNOUNCEMENTS],
        "fallback_surfaces": [MOPS_E1_NAME_RESOLVER],
        "window_back_days": WINDOW_BACK_DAYS,
        "window_forward_days": WINDOW_FORWARD_DAYS,
        "directory_match_tolerance_days": DIRECTORY_MATCH_TOLERANCE_DAYS,
        "segmentation": "calendar day-blocks 01-10 / 11-20 / 21-EOM",
        "typek": "all",
        "event_markers": list(EVENT_MARKERS),
        "transaction_markers": list(TRANSACTION_MARKERS),
        "stock_consideration_markers": list(STOCK_CONSIDERATION_MARKERS),
        "cash_consideration_markers": list(CASH_CONSIDERATION_MARKERS),
        "field_markers": {k: list(v) for k, v in sorted(FIELD_MARKERS.items())},
        "transaction_markers_specific": list(TRANSACTION_MARKERS_SPECIFIC),
        "transaction_markers_contextual": list(TRANSACTION_MARKERS_CONTEXTUAL),
        "accounting_sense_suffixes": list(ACCOUNTING_SENSE_SUFFIXES),
        "name_delimiters": NAME_DELIMITERS,
        "counterparty_proximity_chars": COUNTERPARTY_PROXIMITY_CHARS,
        "refusal_markers": list(REFUSAL_MARKERS),
        "rate_limit_markers": list(RATE_LIMIT_MARKERS),
        "refused_body_is_assessed_on": "preserved announcement row subject",
        "uniqueness_test": ("exactly one distinct counterparty entity standing "
                            "within COUNTERPARTY_PROXIMITY_CHARS of a "
                            "transaction marker, across the event's linking "
                            "documents"),
        "discovery_classes": list(DOC_CLASSES),
        "lineage_classes": [LINEAGE_TWSE, LINEAGE_TPEX, LINEAGE_BOTH,
                            LINEAGE_NONE],
    }
    return {"payload": payload, "router_sha256": canonical_sha256(payload)}
