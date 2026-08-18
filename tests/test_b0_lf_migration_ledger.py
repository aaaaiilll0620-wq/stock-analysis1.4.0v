# -*- coding: utf-8 -*-
"""The CRLF→LF provenance migration ledger must stay true (M-3 ruling §4).

The ruling forbids silently overwriting historical hashes. The ledger keeps both
values and claims the difference between them is line endings and nothing else.
That claim is checkable, so it is checked: for every entry, re-deriving the CRLF
byte-form of the current file must reproduce the recorded historical hash.

If someone later edits one of these files substantively, the historical value
stops being the CRLF form of the current bytes and this test goes red — which is
the point. `substantive_change: false` must not survive a substantive change.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO_ROOT, "research", "b0_registry", "lf_migration_ledger.json")

EXPECTED_ENTRIES = 9


@pytest.fixture(scope="module")
def ledger() -> dict:
    assert os.path.isfile(LEDGER), (
        "缺 LF/CRLF migration ledger;執行 "
        "python research/b0_registry/build_lf_migration_ledger.py")
    with open(LEDGER, encoding="utf-8") as fh:
        return json.load(fh)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_ledger_covers_all_nine_attributed_cases(ledger):
    assert ledger["entry_count"] == EXPECTED_ENTRIES
    assert len(ledger["entries"]) == EXPECTED_ENTRIES


def test_every_entry_declares_the_transformation(ledger):
    for e in ledger["entries"]:
        assert e["transformation"] == "CRLF_TO_LF_ONLY"
        assert e["substantive_change"] is False
        assert len(e["historical_crlf_sha256"]) == 64
        assert len(e["current_canonical_lf_sha256"]) == 64
        assert e["historical_crlf_sha256"] != e["current_canonical_lf_sha256"]


def test_current_hashes_match_the_files_on_disk(ledger):
    for e in ledger["entries"]:
        path = os.path.join(REPO_ROOT, e["path"])
        assert os.path.isfile(path), f"{e['path']} 不存在,帳本無法驗證"
        assert _sha(open(path, "rb").read()) == e["current_canonical_lf_sha256"], (
            f"{e['path']}:現行 hash 與帳本不符")


def test_historical_hash_is_provably_the_crlf_form_of_the_same_content(ledger):
    """This is the whole claim: line endings differ, content does not."""
    for e in ledger["entries"]:
        path = os.path.join(REPO_ROOT, e["path"])
        lf = open(path, "rb").read()
        assert b"\r\n" not in lf, f"{e['path']} 仍含 CRLF,倉庫表示法不正規"
        assert _sha(lf.replace(b"\n", b"\r\n")) == e["historical_crlf_sha256"], (
            f"{e['path']}:歷史值不是現行內容的 CRLF 形式 —— "
            f"差異不只行尾,substantive_change=false 已不成立")


def test_no_affected_path_is_a_b0_normative_module_or_consumed_input(ledger):
    """The exemption is conditional; this is the condition."""
    from core.b0_master_prereg import NORMATIVE_MODULES

    affected = {e["path"] for e in ledger["entries"]}
    assert not (affected & set(NORMATIVE_MODULES)), (
        "受影響路徑成為 normative module,§4 豁免失效")
    assert ledger["blocks_b0_baseline_seal"] is False


def test_records_needing_an_audit_amendment_are_named(ledger):
    named = set(ledger["records_requiring_audit_amendment"])
    assert named == {e["record"] for e in ledger["entries"]}
    amendment = os.path.join(REPO_ROOT, "docs",
                             "AuditAmendment_LF_Migration_2026-08-18.md")
    assert os.path.isfile(amendment), "缺明示稽核修訂文件"
    text = open(amendment, encoding="utf-8").read()
    for record in named:
        assert os.path.basename(record) in text, f"修訂文件未涵蓋 {record}"
