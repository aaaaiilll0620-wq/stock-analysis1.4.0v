# -*- coding: utf-8 -*-
"""B0.8 · D7.6 · AC1-AC15 · DEEP FIRST-PARTY DOCUMENT ACQUISITION / FINAL
HOLDER-CONSIDERATION CLOSURE.

D7.5 left seven events semantically UNKNOWN and called one of them (6514) a
GLOBAL_PUBLIC_AUTHORITATIVE_BOUNDARY.  AC1 corrected that adjudication.  D7.6
tested the family D7.5 had never actually driven, and it turned out to close
every one of the seven:

    THE FAMILY D7.5 MISSED
    D7.0b-2 established that the *material-announcement* surface
    (mops.twse.com.tw 重大訊息) refuses a delisted issuer, and every later stage
    carried that forward as "the disappearing issuer has no first-party route".
    That generalisation was wrong.  The MOPS **electronic document system**
    (doc.twse.com.tw/server-java/t57sb01) is a different surface, and it still
    serves the full document history of delisted issuers -- 華僑銀行 (1996),
    東隆五金 (2012), 凌耀 (2014), 芮特-KY (2024) all answer with their complete
    公開說明書 / 股東會 filing sets.  The share-conversion 公開說明書 that D7.5
    reported as "empty on this flow" is served by that system too; it simply has
    to be reached through the step=1 (list) -> step=9 (fetch) form flow rather
    than a guessed direct PDF URL, exactly as AC4 requires.

    HOLDCO FAMILY (AC4) -- 5384, 5491, 3562
        Each new holding company filed a 股份轉換設立投資控股公司申請上櫃用
        公開說明書 (dtype B07) in its formation month.  All three were acquired
        and all three are natively text-extractable; each states that the
        holder's sole consideration is newly issued holdco stock.

    NONPUBLIC-SURVIVOR FAMILY (AC5) -- 5818, 8705, 3582
        A survivor that is unlisted does not make the transaction undocumented:
        the *disappearing* issuer is the one that had to convene a shareholder
        meeting and publish the merger contract.  All three circulars were
        acquired from the disappearing issuer's own MOPS filings, and all three
        state a per-share cash merger consideration.  3582 additionally carries
        the full English Agreement and Plan of Merger inside its 議事錄.

    FOREIGN-SUCCESSOR FAMILY (AC6) -- 6514
        The successor is authoritatively identified by the issuer's own filing,
        not by a third-party database: UMT Holdings (Samoa) Limited, acting
        through its wholly owned Cayman merger sub UMT Holdings (Cayman)
        Limited, in a 反式三角合併 approved at the 2024-06-19 shareholder
        meeting.  The bilingual merger agreement annexed to that circular states
        the per-share consideration in cash.  No foreign registry or foreign
        securities-regulator route was needed, because an applicable *Taiwan*
        first-party family -- the one D7.5 declared exhausted -- answered.  6514
        is therefore NOT a public-authoritative boundary.

    OCR
        Not required anywhere.  Every decisive clause was read from native
        embedded text (pypdf for PDF, UTF-16LE piece text for the 2007 .doc
        attachments).  Some acquired documents are only partly extractable
        (202002_3713_B07 image pages, 2014_3582_20141024F02 CID-mapped pages),
        but in every such document the decisive clause itself is on a natively
        readable page, so AC8's OCR-verification clause never engages.

Values (ratios, cash amounts, dates) appear below only to fix the instrument
class and the same-transaction linkage.  Nothing here is written into canonical
B0.8 holder terms (AC13), no grammar changed (AC3/AC14), no replay or gate ran.

Run under the Windows interpreter (pypdf lives there):
    python research/b0_8_holder_terms/deep_document_acquisition_d7_6.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256              # noqa: E402

D75 = os.path.join(HERE, "consideration_semantics_source_closure_d7_5.json")
OUT = os.path.join(HERE, "deep_document_acquisition_d7_6.json")
RAW = os.path.join(REPO, "artifacts", "b0_8_holder_terms", "d7_6_docs_raw")

STARTING_UNKNOWN = ["5384", "5491", "3562", "5818", "8705", "3582", "6514"]

# ---------------------------------------------------------------- source families
FAMILIES = [
    "HOLDCO_SHARE_CONVERSION_PROSPECTUS",        # MOPS t57sb01 mtype=B dtype=B07
    "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT",       # MOPS t57sb01 mtype=F dtype=F04/F11
    "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",  # MOPS t57sb01 mtype=F F13/F02/F05
    "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",     # SEC EDGAR acquirer filings
    "FOREIGN_CORPORATE_REGISTRY",                # Samoa / Cayman registries
    "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL",     # FSC / banking bureau
]

# ------------------------------------------------------- acquired document corpus
# Every entry was retrieved live in D7.6; raw bytes are preserved under RAW
# (artifacts/ is gitignored, so the sha256 recorded here is the binding record).
DOCS = [
    # --- holdco share-conversion prospectuses (AC4)
    {"event": "5384", "family": "HOLDCO_SHARE_CONVERSION_PROSPECTUS",
     "file": "201709_3709_B07.pdf", "filer": "3709 鑫聯大投資控股",
     "doc_kind": "公開說明書 · 初次申請上市、櫃(興櫃)或TDR用 · 股份轉換設立投資控股公司申請上櫃用",
     "locator": "https://doc.twse.com.tw/server-java/t57sb01 step=1 co_id=3709 year=106 mtype=B"
                " -> step=9 kind=B filename=201709_3709_B07.pdf",
     "decisive": True},
    {"event": "5491", "family": "HOLDCO_SHARE_CONVERSION_PROSPECTUS",
     "file": "201712_3710_B07.pdf", "filer": "3710 連展投資控股",
     "doc_kind": "公開說明書 · 股份轉換設立投資控股公司申請上櫃用",
     "locator": "https://doc.twse.com.tw/server-java/t57sb01 step=1 co_id=3710 year=106 mtype=B"
                " -> step=9 kind=B filename=201712_3710_B07.pdf",
     "decisive": True},
    {"event": "3562", "family": "HOLDCO_SHARE_CONVERSION_PROSPECTUS",
     "file": "202002_3713_B07.pdf", "filer": "3713 新晶投資控股",
     "doc_kind": "公開說明書 · 股份轉換設立投資控股公司申請上櫃用",
     "locator": "https://doc.twse.com.tw/server-java/t57sb01 step=1 co_id=3713 year=109 mtype=B"
                " -> step=9 kind=B filename=202002_3713_B07.pdf",
     "decisive": True},

    # --- disappearing-issuer shareholder circulars (AC5 / AC6)
    {"event": "5818", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2007_5818_20070615F13.doc", "filer": "5818 華僑商業銀行",
     "doc_kind": "96年股東常會各項議案參考資料 (F13)",
     "locator": "https://doc.twse.com.tw/server-java/t57sb01 step=1 co_id=5818 year=96 mtype=F"
                " -> step=9 kind=F filename=2007_5818_20070615F13.doc (inline body)",
     "decisive": True},
    {"event": "5818", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2007_5818_20070615F02.doc", "filer": "5818 華僑商業銀行",
     "doc_kind": "96年股東常會議事手冊及會議補充資料 (F02)",
     "locator": "t57sb01 step=9 kind=F co_id=5818 filename=2007_5818_20070615F02.doc",
     "decisive": False},
    {"event": "5818", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2007_5818_20070615F05.doc", "filer": "5818 華僑商業銀行",
     "doc_kind": "96年股東常會議事錄 (F05)",
     "locator": "t57sb01 step=9 kind=F co_id=5818 filename=2007_5818_20070615F05.doc",
     "decisive": False},
    {"event": "5818", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2007_5818_20070615F14.doc", "filer": "5818 華僑商業銀行",
     "doc_kind": "取得或處分資產處理程序 (F14)",
     "locator": "t57sb01 step=9 kind=F co_id=5818 filename=2007_5818_20070615F14.doc",
     "decisive": False},

    {"event": "8705", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2012_8705_20121002F13.pdf", "filer": "8705 東隆五金工業",
     "doc_kind": "101年股東臨時會議案參考資料 (F13)",
     "locator": "t57sb01 step=1 co_id=8705 year=101 mtype=F -> step=9 kind=F"
                " filename=2012_8705_20121002F13.pdf",
     "decisive": True},
    {"event": "8705", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2012_8705_20121002F02.pdf", "filer": "8705 東隆五金工業",
     "doc_kind": "101年股東臨時會議事手冊 (F02, 含合併契約及獨立專家意見書)",
     "locator": "t57sb01 step=9 kind=F co_id=8705 filename=2012_8705_20121002F02.pdf",
     "decisive": True},
    {"event": "8705", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2012_8705_20121002F05.pdf", "filer": "8705 東隆五金工業",
     "doc_kind": "101年股東臨時會議事錄 (F05)",
     "locator": "t57sb01 step=9 kind=F co_id=8705 filename=2012_8705_20121002F05.pdf",
     "decisive": False},
    {"event": "8705", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2012_8705_20121002F01.pdf", "filer": "8705 東隆五金工業",
     "doc_kind": "101年股東臨時會開會通知 (F01)",
     "locator": "t57sb01 step=9 kind=F co_id=8705 filename=2012_8705_20121002F01.pdf",
     "decisive": False},

    {"event": "3582", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2014_3582_20141024F13.pdf", "filer": "3582 凌耀科技",
     "doc_kind": "103年第一次股東臨時會各項議案參考資料 (F13)",
     "locator": "t57sb01 step=1 co_id=3582 year=103 mtype=F -> step=9 kind=F"
                " filename=2014_3582_20141024F13.pdf",
     "decisive": True},
    {"event": "3582", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2014_3582_20141024F05.pdf", "filer": "3582 凌耀科技",
     "doc_kind": "103年第一次股東臨時會議事錄 (F05, 附 Agreement and Plan of Merger)",
     "locator": "t57sb01 step=9 kind=F co_id=3582 filename=2014_3582_20141024F05.pdf",
     "decisive": True},
    {"event": "3582", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2014_3582_20141024F02.pdf", "filer": "3582 凌耀科技",
     "doc_kind": "103年第一次股東臨時會議事手冊 (F02)",
     "locator": "t57sb01 step=9 kind=F co_id=3582 filename=2014_3582_20141024F02.pdf",
     "decisive": False},
    {"event": "3582", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2014_3582_20141024F01.pdf", "filer": "3582 凌耀科技",
     "doc_kind": "103年第一次股東臨時會開會通知 (F01)",
     "locator": "t57sb01 step=9 kind=F co_id=3582 filename=2014_3582_20141024F01.pdf",
     "decisive": False},

    {"event": "6514", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2024_6514_20240619F13.pdf", "filer": "6514 芮特-KY",
     "doc_kind": "2024年股東常會各項議案參考資料 (F13, 含合併契約暨合併計畫稿本)",
     "locator": "t57sb01 step=1 co_id=6514 year=113 mtype=F -> step=9 kind=F"
                " filename=2024_6514_20240619F13.pdf",
     "decisive": True},
    {"event": "6514", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2024_6514_20240619F02.pdf", "filer": "6514 芮特-KY",
     "doc_kind": "2024年股東常會議事手冊 (F02; byte-identical to F13)",
     "locator": "t57sb01 step=9 kind=F co_id=6514 filename=2024_6514_20240619F02.pdf",
     "decisive": False},
    {"event": "6514", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2024_6514_20240619F05.pdf", "filer": "6514 芮特-KY",
     "doc_kind": "2024年股東常會議事錄 (F05)",
     "locator": "t57sb01 step=9 kind=F co_id=6514 filename=2024_6514_20240619F05.pdf",
     "decisive": False},
    {"event": "6514", "family": "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR",
     "file": "2024_6514_20240619F01.pdf", "filer": "6514 芮特-KY",
     "doc_kind": "2024年股東常會開會通知 (F01)",
     "locator": "t57sb01 step=9 kind=F co_id=6514 filename=2024_6514_20240619F01.pdf",
     "decisive": False},

    # --- foreign securities-regulator family (AC5)
    {"event": "3582", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_3582_0000103730-14-000061_exhibit99-1.htm",
     "filer": "Vishay Intertechnology, Inc. (CIK 0000103730)",
     "doc_kind": "Form 8-K Exhibit 99.1, 2014-12-31 — completion of the Capella merger",
     "locator": "https://www.sec.gov/Archives/edgar/data/103730/000010373014000061/exhibit99-1.htm",
     "decisive": True},
    {"event": "3582", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_3582_0000103730-14-000033_exhibit99-1.htm",
     "filer": "Vishay Intertechnology, Inc.",
     "doc_kind": "Form 8-K Exhibit 99.1, 2014-07-11 — tender offer / merger agreement announcement",
     "locator": "https://www.sec.gov/Archives/edgar/data/103730/000010373014000033/exhibit99-1.htm",
     "decisive": False},
    {"event": "3582", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_3582_0000103730-14-000034_exhibit99-1.htm",
     "filer": "Vishay Intertechnology, Inc.",
     "doc_kind": "Form 8-K Exhibit 99.1, 2014-07-17",
     "locator": "https://www.sec.gov/Archives/edgar/data/103730/000010373014000034/exhibit99-1.htm",
     "decisive": False},
    {"event": "3582", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_3582_0001140361-14-035051_exhibit99-1.htm",
     "filer": "Vishay Intertechnology, Inc.",
     "doc_kind": "Form 8-K Exhibit 99.1, 2014-09-09 — tender offer settlement",
     "locator": "https://www.sec.gov/Archives/edgar/data/103730/000114036114035051/exhibit99-1.htm",
     "decisive": False},
    {"event": "8705", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_8705_0000950142-12-001953_eh1201089_ex9901.htm",
     "filer": "Spectrum Brands Holdings, Inc. (CIK 0001487730)",
     "doc_kind": "Form 8-K Exhibit 99.1, 2012-10-09 — HHI acquisition from Stanley Black & Decker",
     "locator": "https://www.sec.gov/Archives/edgar/data/1487730/000095014212001953/eh1201089_ex9901.htm",
     "decisive": False, "ac9_linkage": "EXCLUDED"},
    {"event": "8705", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_8705_0000950142-12-001953_eh1201089_ex9902.htm",
     "filer": "Spectrum Brands Holdings, Inc.",
     "doc_kind": "Form 8-K Exhibit 99.2, 2012-10-09 — investor presentation",
     "locator": "https://www.sec.gov/Archives/edgar/data/1487730/000095014212001953/eh1201089_ex9902.htm",
     "decisive": False, "ac9_linkage": "EXCLUDED"},
    {"event": "8705", "family": "SURVIVOR_FOREIGN_SECURITIES_REGULATOR",
     "file": "EDGAR_8705_0000950142-12-002420_eh1201312_ex9901.htm",
     "filer": "Spectrum Brands Holdings, Inc.",
     "doc_kind": "Form 8-K Exhibit 99.1, 2012-12-21 — HHI closing",
     "locator": "https://www.sec.gov/Archives/edgar/data/1487730/000095014212002420/eh1201312_ex9901.htm",
     "decisive": False, "ac9_linkage": "EXCLUDED"},
]

# ------------------------------------------------- decisive clauses (AC8 evidence)
# page = 1-based page index in the acquired file; reading = native embedded text.
CLAUSES = {
    "5384": [
        {"file": "201709_3709_B07.pdf", "page": 39, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "三、本次受讓他公司股份發行新股應記載事項：(一)受讓股份名稱…捷元股份有限公司"
                   "普通股79,569,450股。3.受讓對象：股份轉換基準日(民國106年9月1日)…之普通股股東。"
                   "(三)股份交換比例之計算方式及依據：捷元股份有限公司普通股1股換發鑫聯大投資控股"
                   "股份有限公司普通股1股。"},
        {"file": "201709_3709_B07.pdf", "page": 22, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "捷元股份有限公司於民國106年6月15日股東常會通過股份轉換案，將依企業併購法有關"
                   "股份轉換之規定，以1:1之換股比例將全部已發行之普通股股份讓與新設公司鑫聯大投資"
                   "控股股份有限公司作為對價…"},
    ],
    "5491": [
        {"file": "201712_3710_B07.pdf", "page": 25, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "連展科技於民國106年6月13日股東常會通過股份轉換案，將依企業併購法有關股份轉換"
                   "之規定，以1：1之換股比例將全部已發行之普通股股份讓與新設公司連展投控公司，並由"
                   "連展投控公司發行新股予連展科技股東作為對價…"},
        {"file": "201712_3710_B07.pdf", "page": 293, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "…擬以股份轉換方式被新設之「連展投資控股股份有限公司」…收購，成為連展投控公司"
                   "百分之百持股之子公司，換股比例為本公司普通股1股換發連展投控公司之普通股1股…"},
    ],
    "3562": [
        {"file": "202002_3713_B07.pdf", "page": 1, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "本公開說明書編印目的：股份轉換設立投資控股公司申請上櫃用（一）新股來源：股份轉換。"
                   "（二）新股種類：記名式普通股…（五）發行條件：頂晶科技股份有限公司股票1股換發本"
                   "公司股票1股，共計應發行78,090,000股，全額發行。"},
    ],
    "5818": [
        {"file": "2007_5818_20070615F13.doc", "page": None, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "二、合併後，花旗之子銀行為存續公司，本行為消滅公司，原本行全體股東將就其全部持股"
                   "獲配現金合併對價。…四、依合併合約書約定，合併價格如下：…每股原則以新臺幣11.8元"
                   "為合併價格…前述本行股份之每股現金收購價格，應屬公允合理。",
         "note": "Word 97 .doc: text recovered from the UTF-16LE piece text of the OLE container."},
    ],
    "8705": [
        {"file": "2012_8705_20121002F13.pdf", "page": 2, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "本公司擬與臺灣史丹利安防系統股份有限公司合併…史丹利安防為存續公司，本公司為"
                   "消滅公司…3、本公司每一股普通股股份史丹利安防應換給現金新臺幣41.05元，不滿一元"
                   "則四捨五入。"},
        {"file": "2012_8705_20121002F02.pdf", "page": 8, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "(same resolution text inside the meeting handbook, with 合併契約 at 附件三 pp.30-38"
                   " and the independent-expert opinion on 合併對價 at 附件二 pp.12-29)"},
    ],
    "3582": [
        {"file": "2014_3582_20141024F05.pdf", "page": 12, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "Each Share issued and outstanding immediately prior to the Merger Effective Date"
                   " (other than … Dissenting Shares) shall thereupon be converted automatically into"
                   " and shall thereafter represent the right to receive NT$139.00 in cash (the"
                   " \"Offer Price\"), without interest … (the \"Merger Consideration\")."},
        {"file": "2014_3582_20141024F13.pdf", "page": 1, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "第一案…本公司與台灣威世光電股份有限公司合併案…本次合併完成後，台灣威世光電為"
                   "存續公司，本公司為消滅公司。…辦理應賣有價證券交割及收購對價支付事宜。"},
        {"file": "EDGAR_3582_0000103730-14-000061_exhibit99-1.htm", "page": 1,
         "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "Vishay Intertechnology … today acquired all of the remaining outstanding shares of"
                   " Taiwan based Capella Microsystems Inc. (GreTai Securities Market: 3582) for"
                   " approximately NT$668.2 million or US$21.0 million, pursuant to the terms of its"
                   " previously announced merger agreement with Capella."},
    ],
    "6514": [
        {"file": "2024_6514_20240619F13.pdf", "page": 34, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "2.5.1(i) … every Company Ordinary Share issued and outstanding immediately prior"
                   " to the Effective Time shall be cancelled and cease to exist in consideration and"
                   " exchange for the right to receive … NTD53.80 in cash, without interest, per share"
                   " (the \"Per-Share Merger Consideration\"). / 標的公司…每一股已發行並流通在外的"
                   "普通股…應予以註銷並不再存續，並無息換得收取每股現金新臺幣53.80元…之權利"},
        {"file": "2024_6514_20240619F13.pdf", "page": 8, "reading_mode": "NATIVE_EMBEDDED_TEXT",
         "clause": "擬與UMT Holdings (Cayman) Limited（係一依英屬開曼群島法律組織設立、由 UMT"
                   " Holdings (Samoa) Limited…全資持有之子公司）進行反式三角合併…由合併子公司作為"
                   "消滅公司，本公司作為存續公司…本合併案將由UMT按每一股本公司普通股股份新台幣"
                   "53.80元支付合併對價"},
    ],
}

# -------------------------------------------------- per-event adjudication (AC11)
EVENTS = {
    "5384": {
        "disappearing": "捷元股份有限公司 (5384)", "effective_date": "2017-08-22",
        "successor": "鑫聯大投資控股股份有限公司 (3709)",
        "transaction": "企業併購法 股份轉換 · 設立投資控股公司",
        "semantics": "STOCK_ONLY", "status": "ESTABLISHED",
        "holder_security": True, "holder_cash": False,
        "linkage": "prospectus names 捷元 as the transferred issuer, 鑫聯大投控 as the新設"
                   "holding company, 股份轉換基準日 106/09/01, and the 106/06/15 shareholder"
                   " resolution that approved it",
    },
    "5491": {
        "disappearing": "連展科技股份有限公司 (5491)", "effective_date": "2017-12-19",
        "successor": "連展投資控股股份有限公司 (3710)",
        "transaction": "企業併購法 股份轉換 · 設立投資控股公司",
        "semantics": "STOCK_ONLY", "status": "ESTABLISHED",
        "holder_security": True, "holder_cash": False,
        "linkage": "prospectus names 連展科技, 連展投控, 轉換基準日 106/12/29 and the"
                   " 106/06/13 shareholder resolution",
    },
    "3562": {
        "disappearing": "頂晶科技股份有限公司 (3562)", "effective_date": "2020-02-17",
        "successor": "新晶投資控股股份有限公司 (3713)",
        "transaction": "企業併購法 股份轉換 · 設立投資控股公司",
        "semantics": "STOCK_ONLY", "status": "ESTABLISHED",
        "holder_security": True, "holder_cash": False,
        "linkage": "prospectus cover states 新股來源：股份轉換 and names 頂晶科技 as the"
                   " exchanged issuer; 刊印日 109/02/27, 股票代號 3713",
    },
    "5818": {
        "disappearing": "華僑商業銀行股份有限公司 (5818)", "effective_date": "2007-11-23",
        "successor": "花旗(台灣)商業銀行股份有限公司 (unlisted)",
        "transaction": "金融機構合併法 第8條 吸收合併 (Citibank Overseas Investment Corporation"
                       " Master Agreement + Merger Agreement)",
        "semantics": "CASH_ONLY", "status": "ESTABLISHED",
        "holder_security": False, "holder_cash": True,
        "linkage": "the circular is 華僑商業銀行's own 96年股東常會 agenda; it names 花旗之子銀行"
                   " as 存續公司 and 本行 as 消滅公司 under 金融機構合併法",
    },
    "8705": {
        "disappearing": "東隆五金工業股份有限公司 (8705)", "effective_date": "2012-12-26",
        "successor": "臺灣史丹利安防系統股份有限公司 (unlisted)",
        "transaction": "企業併購法 合併 (關係企業合併)",
        "semantics": "CASH_ONLY", "status": "ESTABLISHED",
        "holder_security": False, "holder_cash": True,
        "linkage": "東隆五金's own 101/10/02 股東臨時會 second resolution names 史丹利安防 as"
                   " 存續公司, 本公司 as 消滅公司, 終止櫃檯買賣, 合併基準日暫訂 101/12/17",
    },
    "3582": {
        "disappearing": "凌耀科技股份有限公司 (3582)", "effective_date": "2014-12-25",
        "successor": "台灣威世光電股份有限公司 (unlisted; Vishay Intertechnology group)",
        "transaction": "公開收購 followed by 企業併購法 合併 (Agreement and Plan of Merger)",
        "semantics": "CASH_ONLY", "status": "ESTABLISHED",
        "holder_security": False, "holder_cash": True,
        "linkage": "凌耀's own 103/10/24 股東臨時會 minutes carry the executed Agreement and Plan"
                   " of Merger; Vishay's 8-K of 2014-12-31 names GreTai code 3582 and the same"
                   " merger agreement",
    },
    "6514": {
        "disappearing": "芮特科技股份有限公司 芮特-KY (6514)", "effective_date": "2024-10-09",
        "successor": "UMT Holdings (Samoa) Limited (Samoa), via wholly owned merger sub"
                     " UMT Holdings (Cayman) Limited (British Cayman Islands)",
        "transaction": "反式三角合併 (reverse triangular merger); 6514 is the SURVIVING company"
                       " and becomes UMT's wholly owned subsidiary; 私有化 / 終止櫃檯買賣",
        "semantics": "CASH_ONLY", "status": "ESTABLISHED",
        "holder_security": False, "holder_cash": True,
        "linkage": "the issuer's own 2024/06/19 股東常會 circular and the annexed bilingual"
                   " 合併契約暨合併計畫 name both UMT entities, the Cayman merger sub as 消滅公司,"
                   " 芮特-KY as 存續公司, 合併基準日暫訂 113/10/18, and TDCC as the cancelling agent",
    },
}

# ----------------------------------------------- per-event x family matrix (AC10)
MATRIX = {
    "5384": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "CONSIDERATION_ESTABLISHED",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "NOT_REACHED_RESOLVED_EARLIER",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "NOT_REACHED_RESOLVED_EARLIER",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "COVERAGE_NOT_APPLICABLE",
             "FOREIGN_CORPORATE_REGISTRY": "COVERAGE_NOT_APPLICABLE",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "COVERAGE_NOT_APPLICABLE"},
    "5491": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "CONSIDERATION_ESTABLISHED",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "NOT_REACHED_RESOLVED_EARLIER",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "NOT_REACHED_RESOLVED_EARLIER",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "COVERAGE_NOT_APPLICABLE",
             "FOREIGN_CORPORATE_REGISTRY": "COVERAGE_NOT_APPLICABLE",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "COVERAGE_NOT_APPLICABLE"},
    "3562": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "CONSIDERATION_ESTABLISHED",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "NOT_REACHED_RESOLVED_EARLIER",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "NOT_REACHED_RESOLVED_EARLIER",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "COVERAGE_NOT_APPLICABLE",
             "FOREIGN_CORPORATE_REGISTRY": "COVERAGE_NOT_APPLICABLE",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "COVERAGE_NOT_APPLICABLE"},
    "5818": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "COVERAGE_NOT_APPLICABLE",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "COVERAGE_NOT_APPLICABLE",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "CONSIDERATION_ESTABLISHED",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "NOT_REACHED_RESOLVED_EARLIER",
             "FOREIGN_CORPORATE_REGISTRY": "COVERAGE_NOT_APPLICABLE",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "NOT_REACHED_RESOLVED_EARLIER"},
    "8705": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "COVERAGE_NOT_APPLICABLE",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "COVERAGE_NOT_APPLICABLE",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "CONSIDERATION_ESTABLISHED",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "TESTED_NO_CONSIDERATION_STATEMENT",
             "FOREIGN_CORPORATE_REGISTRY": "COVERAGE_NOT_APPLICABLE",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "COVERAGE_NOT_APPLICABLE"},
    "3582": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "COVERAGE_NOT_APPLICABLE",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "COVERAGE_NOT_APPLICABLE",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "CONSIDERATION_ESTABLISHED",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "CONSIDERATION_ESTABLISHED",
             "FOREIGN_CORPORATE_REGISTRY": "COVERAGE_NOT_APPLICABLE",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "COVERAGE_NOT_APPLICABLE"},
    "6514": {"HOLDCO_SHARE_CONVERSION_PROSPECTUS": "COVERAGE_NOT_APPLICABLE",
             "HOLDCO_FORMATION_YEAR_ANNUAL_REPORT": "COVERAGE_NOT_APPLICABLE",
             "DISAPPEARING_ISSUER_SHAREHOLDER_CIRCULAR": "CONSIDERATION_ESTABLISHED",
             "SURVIVOR_FOREIGN_SECURITIES_REGULATOR": "NOT_REACHED_RESOLVED_EARLIER",
             "FOREIGN_CORPORATE_REGISTRY": "NOT_REACHED_RESOLVED_EARLIER",
             "DOMESTIC_FINANCIAL_REGULATOR_APPROVAL": "COVERAGE_NOT_APPLICABLE"},
}

TERMINAL_BLOCKING = {"RETRIEVAL_UNRESOLVED", "ACQUISITION_ERROR", "UNTESTED"}


def inventory():
    """Recompute the acquired-corpus record from the preserved raw bytes."""
    out = []
    for d in DOCS:
        p = os.path.join(RAW, d["file"])
        rec = dict(d)
        rec["stored"] = p
        if not os.path.exists(p):
            rec["acquisition_state"] = "RAW_BYTES_ABSENT"
            out.append(rec); continue
        b = open(p, "rb").read()
        rec["acquisition_state"] = "ACQUIRED"
        rec["bytes"] = len(b)
        rec["sha256"] = hashlib.sha256(b).hexdigest()
        if p.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                rd = PdfReader(p)
                pages = [(pg.extract_text() or "") for pg in rd.pages]
                rec["page_count"] = len(pages)
                rec["pages_with_native_text"] = sum(1 for t in pages if len(t.strip()) > 20)
                rec["native_text_chars"] = sum(len(t) for t in pages)
                rec["text_extractability"] = (
                    "FULL" if rec["pages_with_native_text"] >= rec["page_count"] - 2
                    else "PARTIAL" if rec["pages_with_native_text"] else "NONE")
            except Exception as e:                                   # pragma: no cover
                rec["page_count"] = None
                rec["text_extractability"] = "UNREADABLE"
                rec["extract_error"] = "%s:%s" % (type(e).__name__, e)
        elif p.lower().endswith(".doc"):
            import legacy_doc_text_extraction_d7_6 as LDOC
            runs = LDOC.extract(p)
            rec["page_count"] = None            # OLE .doc has no page structure in the stream
            rec["native_text_chars"] = sum(len(r) for r in runs)
            rec["text_extractability"] = "FULL" if rec["native_text_chars"] > 2000 else "PARTIAL"
        else:                                    # EDGAR html
            rec["page_count"] = 1
            rec["native_text_chars"] = len(b)
            rec["text_extractability"] = "FULL"
        rec["ocr_used"] = False
        rec["authoritative_source"] = "official document"
        rec["reading_assist"] = None
        out.append(rec)
    return out


def main() -> int:
    d75 = json.load(open(D75, encoding="utf-8"))
    assert set(STARTING_UNKNOWN) == set(EVENTS) == set(MATRIX) == set(CLAUSES)

    docs = inventory()
    absent = [d["file"] for d in docs if d["acquisition_state"] != "ACQUIRED"]

    # AC10: no boundary adjudication while any applicable family is unresolved
    blocking = sorted({(e, f) for e, row in MATRIX.items()
                       for f, s in row.items() if s in TERMINAL_BLOCKING})

    newly_stock = [e for e, v in EVENTS.items() if v["semantics"] == "STOCK_ONLY"]
    newly_cash = [e for e, v in EVENTS.items() if v["semantics"] == "CASH_ONLY"]
    newly_mixed = [e for e, v in EVENTS.items() if v["semantics"] == "MIXED"]
    still_unknown = [e for e, v in EVENTS.items() if v["semantics"] == "UNKNOWN"]
    boundary = [e for e, v in EVENTS.items()
                if v["status"] == "PUBLIC_AUTHORITATIVE_BOUNDARY"]
    unfinished = [e for e, v in EVENTS.items()
                  if v["status"] == "SOURCE_FAMILY_NOT_EXHAUSTED"]

    base = d75["AB1_starting_census"]
    final_stock_only = base["STOCK_ONLY"] + len(newly_stock)
    final_mixed = base["MIXED"] + len(newly_mixed)
    final_cash = base["CASH_ONLY"] + len(newly_cash)
    final_unknown = len(still_unknown)
    stock_bearing = final_stock_only + final_mixed

    native = [d for d in docs if d.get("text_extractability") in ("FULL", "PARTIAL")]
    ocr_assisted = [d for d in docs if d.get("ocr_used")]

    payload = {
        "record": "B0_8_D7_6_DEEP_FIRST_PARTY_DOCUMENT_ACQUISITION",
        "b0_8_state": "WIP, UNSEALED",
        "inputs": {"d7_5_closure_sha256": d75["closure_sha256"]},

        "AC1_6514_adjudication_correction": {
            "d7_5_status": "PUBLIC_AUTHORITATIVE_BOUNDARY",
            "d7_6_status": "ESTABLISHED",
            "why_the_boundary_was_wrong":
                "D7.5 treated 'applicable Taiwan-side first-party routes are exhausted' as a"
                " finding, but the exhaustion claim rested on the delisted-issuer refusal of the"
                " MOPS 重大訊息 surface (D7.0b-2). The MOPS electronic document system"
                " (doc.twse.com.tw t57sb01) is a different first-party surface, it still serves"
                " 芮特-KY's complete filing history, and the 2024 shareholder circular it serves"
                " carries the executed merger agreement with the holder consideration. No foreign"
                " successor / registry route was needed.",
            "foreign_family_status": "NOT_REACHED_RESOLVED_EARLIER",
        },

        "AC2_population": {"processed": STARTING_UNKNOWN,
                           "already_established_events_reopened": 0,
                           "prioritization_applied": False},

        "AC4_AC5_AC6_families": FAMILIES,
        "AC7_document_corpus": docs,
        "AC7_raw_bytes_absent": absent,
        "AC8_decisive_clauses": CLAUSES,
        "AC8_ocr_dependent_classifications": 0,
        "AC9_linkage_excluded_documents": [
            {"file": d["file"], "event": d["event"],
             "reason": "Spectrum Brands' purchase of Stanley Black & Decker's HHI business"
                       " (including certain Tong Lung ASSETS) is a different transaction from the"
                       " 8705 shareholder-level merger into 臺灣史丹利安防系統; excluded under AC9"}
            for d in DOCS if d.get("ac9_linkage") == "EXCLUDED"],
        "AC10_family_matrix": MATRIX,
        "AC10_blocking_states": blocking,
        "AC11_two_axis_results": EVENTS,

        "AC12_denominator": {
            "FINAL_STOCK_ONLY": final_stock_only,
            "FINAL_MIXED": final_mixed,
            "FINAL_CASH_ONLY": final_cash,
            "FINAL_CONFIRMED_STOCK_BEARING": stock_bearing,
            "FINAL_SEMANTIC_UNKNOWN": final_unknown,
            "unknown_due_to_boundary": len(boundary),
            "unknown_due_to_unfinished_acquisition": len(unfinished),
            "stock_bearing_lower_bound": stock_bearing,
            "stock_bearing_upper_bound": stock_bearing + final_unknown,
            "exact_stock_denominator_closed": final_unknown == 0,
            "acquisition_workflow_closed": not blocking and not unfinished and not absent,
        },
        "population_reconciliation": {
            "STOCK_ONLY": final_stock_only, "MIXED": final_mixed,
            "CASH_ONLY": final_cash, "SEMANTIC_UNKNOWN": final_unknown,
            "total": final_stock_only + final_mixed + final_cash + final_unknown,
        },
        "reading_mode_counts": {
            "documents_acquired": len(docs),
            "native_text_readable": len(native),
            "ocr_assisted": len(ocr_assisted),
            "decisive_clauses_read_natively": sum(len(v) for v in CLAUSES.values()),
            "decisive_clauses_read_via_ocr": 0,
        },

        # AC14 invariants
        "consideration_grammar_changed": False,
        "canonical_holder_term_values_materialized": False,
        "reconstruction_classifications_changed": 0,
        "reconstruction_schema_unchanged": True,
        "termination_branch_reopened": False,
        "cash_settlement_hunting": False,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "replay_started": False,
        "gates_evaluated": False,
        "dual_extraction_started": False,
        "third_party_mirrors_consulted": False,
        "prior_artefacts_rewritten": 0,
    }
    payload["closure_sha256"] = canonical_sha256(payload)

    with open(OUT, "w", encoding="utf-8", newline="
") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)

    den = payload["AC12_denominator"]
    print("D7.6 acquired %d documents; ocr-assisted %d" % (len(docs), len(ocr_assisted)))
    print("newly STOCK %s | newly CASH %s | newly MIXED %s | still UNKNOWN %s"
          % (newly_stock, newly_cash, newly_mixed, still_unknown))
    print("FINAL stock_only=%d mixed=%d cash_only=%d unknown=%d stock_bearing=%d"
          % (den["FINAL_STOCK_ONLY"], den["FINAL_MIXED"], den["FINAL_CASH_ONLY"],
             den["FINAL_SEMANTIC_UNKNOWN"], den["FINAL_CONFIRMED_STOCK_BEARING"]))
    print("exact denominator closed=%s | acquisition workflow closed=%s"
          % (den["exact_stock_denominator_closed"], den["acquisition_workflow_closed"]))
    print("closure_sha256", payload["closure_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
