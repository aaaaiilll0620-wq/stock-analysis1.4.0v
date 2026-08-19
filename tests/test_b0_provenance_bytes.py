"""R5 · provenance records must have platform-independent bytes.

`record_opening` wrote the L2 opening registry through a TEXT-mode handle. On
Windows that turns every `\\n` into `\\r\\n`, so the same logical opening produced
946 bytes here and 945 bytes on Linux — a different raw-byte identity for
identical content, in a file whose entire purpose is to be a provenance record.
`.gitattributes` already freezes LF as the repository's canonical representation
precisely because seals bind raw bytes; the writer simply did not honour it.

The fix is binary mode, not a `newline=` keyword: a keyword argument can be
dropped by the next edit, and the runner's own `_jsonl` proved the point by
carrying the keyword correctly while the registry writer did not.
"""

import hashlib
import io
import json
import os

import pytest

from core.b0_master_prereg import (
    L2_RUN_INVALID_CONFORMANCE,
    MasterPreregViolation,
    PROVENANCE_LINE_TERMINATOR,
    PROVENANCE_RECORD_ENCODING,
    L2Opening,
    append_provenance_record,
    canonical_record_bytes,
    record_opening,
    write_provenance_json,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _opening(**kw):
    base = dict(opened_at="2026-08-19T06:25:31.174494+00:00",
                spec_sha256="a" * 64, code_commit="d49222b1",
                data_manifest_sha256="b" * 64,
                outcome=L2_RUN_INVALID_CONFORMANCE)
    base.update(kw)
    return L2Opening(**base)


# --- no CRLF is emitted -------------------------------------------------------

def test_the_record_primitive_emits_no_crlf():
    blob = canonical_record_bytes({"a": 1, "b": "x"})
    assert b"\r" not in blob
    assert blob.endswith(b"\n")


def test_record_opening_emits_no_crlf(tmp_path):
    """The regression itself: on Windows the old writer produced b'\\r\\n' here."""
    path = str(tmp_path / "registry.jsonl")
    record_opening(_opening(), path)
    record_opening(_opening(opened_at="2026-10-01T00:00:00Z"), path)
    raw = io.open(path, "rb").read()
    assert b"\r\n" not in raw
    assert raw.count(b"\n") == 2


def test_written_bytes_are_exactly_the_declared_bytes(tmp_path):
    """Byte equality with the primitive is what makes the claim platform-free.

    `b'\\r\\n' not in raw` alone only proves the platform this ran on. Equality
    with a value computed in memory holds on any platform.
    """
    from dataclasses import asdict

    entry = _opening()
    path = str(tmp_path / "registry.jsonl")
    record_opening(entry, path)
    assert io.open(path, "rb").read() == canonical_record_bytes(asdict(entry))


def test_provenance_json_documents_are_lf_too(tmp_path):
    path = str(tmp_path / "opening_record.json")
    blob = write_provenance_json(path, {"z": 1, "a": [1, 2]})
    raw = io.open(path, "rb").read()
    assert raw == blob
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert json.loads(raw.decode(PROVENANCE_RECORD_ENCODING)) == {"z": 1, "a": [1, 2]}


# --- identical logical record -> identical bytes and hash ---------------------

def test_the_same_logical_record_hashes_identically():
    a = canonical_record_bytes({"beta": 2, "alpha": 1})
    b = canonical_record_bytes({"alpha": 1, "beta": 2})      # key order differs
    assert a == b
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_two_writes_of_one_record_are_byte_identical(tmp_path):
    one = append_provenance_record(str(tmp_path / "x.jsonl"), {"k": "v"})
    two = append_provenance_record(str(tmp_path / "y.jsonl"), {"k": "v"})
    assert one == two


def test_non_ascii_content_is_stable_and_utf8():
    blob = canonical_record_bytes({"note": "無償配股 — 除權"})
    assert blob.decode("utf-8")
    assert b"\r" not in blob


# --- behaviour does not depend on platform newline defaults -------------------

def test_the_terminator_is_declared_not_inherited():
    assert PROVENANCE_LINE_TERMINATOR == "\n"
    assert PROVENANCE_LINE_TERMINATOR != os.linesep or os.linesep == "\n"
    assert PROVENANCE_RECORD_ENCODING == "utf-8"


def test_os_linesep_does_not_leak_into_a_record(tmp_path):
    """os.linesep is '\\r\\n' on this platform; the record must not contain it."""
    path = str(tmp_path / "r.jsonl")
    record_opening(_opening(), path)
    raw = io.open(path, "rb").read()
    assert os.linesep.encode() not in raw or os.linesep == "\n"


def test_a_multiline_value_still_occupies_exactly_one_record():
    """One record is one line. A `detail` field with breaks must not split it."""
    blob = canonical_record_bytes({"detail": "line one\nline two\r\nthree"})
    assert blob.count(b"\n") == 1 and blob.endswith(b"\n")
    assert b"\r" not in blob
    assert json.loads(blob.decode("utf-8"))["detail"] == "line one\nline two\r\nthree"


def test_the_one_line_post_condition_is_enforced(monkeypatch):
    """If a future serialiser stops escaping breaks, this raises rather than
    silently corrupting the append-only file."""
    import core.b0_master_prereg as m
    monkeypatch.setattr(m.json, "dumps", lambda *a, **k: '{"a": "x\ny"}')
    with pytest.raises(MasterPreregViolation, match="exactly one line"):
        m.canonical_record_bytes({"a": "x"})


# --- the real artefacts, not only the primitive -------------------------------

L2_PROVENANCE_FILES = (
    "research/b0_registry/l2_opening_registry.jsonl",
    "research/b0_registry/l2_nonconsumption_ledger.jsonl",
    "artifacts/l2_run/period_progress.jsonl",
    "artifacts/l2_run/opening_record.json",
    "artifacts/l2_run/final_result.json",
    "artifacts/l2_run/nav_series.json",
)


@pytest.mark.parametrize("rel", L2_PROVENANCE_FILES)
def test_no_l2_provenance_artefact_carries_crlf(rel):
    """Covers writers this module does not own, including ad-hoc ones."""
    path = os.path.join(REPO, rel)
    if not os.path.exists(path):
        pytest.skip("%s not present" % rel)
    raw = io.open(path, "rb").read()
    assert b"\r\n" not in raw, (
        "%s carries CRLF; L2 provenance bytes must not depend on the platform "
        "that wrote them" % rel)
