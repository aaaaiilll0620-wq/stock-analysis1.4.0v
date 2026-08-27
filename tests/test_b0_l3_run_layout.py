"""W7B5 · L3 run-scoped immutable storage."""

from __future__ import annotations

import hashlib
import os

import pytest

import core.b0_l3_run_layout as layout
from core.b0_l3_run_layout import (
    RunDirectoryExists,
    RunDirectoryMissing,
    artefact_path,
    assert_not_creating_run_dir,
    assert_run_dir_exists,
    create_run_dir,
    resolve_run_dir,
    run_dir,
)


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _snapshot(directory: str) -> dict[str, str]:
    out = {}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            out[name] = _sha(path)
    return out


def _rows(tag: str, kind: str, periods: int) -> bytes:
    raw = bytearray()
    for n in range(periods):
        raw.extend(f"{tag}-{kind}-{n}\n".encode())
    return bytes(raw)


def _line_count(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        return fh.read().count("\n")


def _write_run(directory: str, tag: str, periods: int) -> None:
    files = {
        "opening_record.json": (tag + "-opening\n").encode(),
        "period_progress.jsonl": _rows(tag, "period", periods),
        "portfolio_checkpoint.jsonl": _rows(tag, "checkpoint", periods),
        "final_result.json": (tag + "-terminal\n").encode(),
    }
    for name, raw in files.items():
        with open(os.path.join(directory, name), "wb") as fh:
            fh.write(raw)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "l3_run"
    monkeypatch.setattr(layout, "L3_RUN_ROOT", str(root))
    monkeypatch.setattr(layout, "RUNS_ROOT", str(root / "runs"))
    return str(root)


def test_run_dir_is_pure_and_always_below_runs_root(sandbox):
    path = run_dir("L3-aaaaaaaaaaaaaaaa")
    assert path == os.path.join(layout.RUNS_ROOT, "L3-aaaaaaaaaaaaaaaa")
    assert not os.path.exists(path)


def test_each_run_has_an_independent_directory(sandbox):
    a = create_run_dir("L3-aaaaaaaaaaaaaaaa")
    b = create_run_dir("L3-bbbbbbbbbbbbbbbb")
    assert os.path.realpath(a) != os.path.realpath(b)

    _write_run(a, "a", 3)
    _write_run(b, "b", 7)
    assert set(_snapshot(a)) == set(_snapshot(b))
    assert _snapshot(a) != _snapshot(b)


def test_writing_run_b_changes_no_byte_of_run_a(sandbox):
    a = create_run_dir("L3-aaaaaaaaaaaaaaaa")
    _write_run(a, "a", 3)
    before = _snapshot(a)

    b = create_run_dir("L3-bbbbbbbbbbbbbbbb")
    _write_run(b, "b", 7)

    assert _snapshot(a) == before


def test_run_b_checkpoint_does_not_append_to_run_a(sandbox):
    a = create_run_dir("L3-aaaaaaaaaaaaaaaa")
    _write_run(a, "a", 3)
    checkpoint = os.path.join(a, "portfolio_checkpoint.jsonl")
    before = _sha(checkpoint)

    b = create_run_dir("L3-bbbbbbbbbbbbbbbb")
    _write_run(b, "b", 7)

    assert _sha(checkpoint) == before
    assert _line_count(checkpoint) == 3
    assert _line_count(os.path.join(b, "portfolio_checkpoint.jsonl")) == 7


def test_reusing_run_id_fails_before_any_artefact_mutation(sandbox):
    directory = create_run_dir("L3-aaaaaaaaaaaaaaaa")
    _write_run(directory, "a", 3)
    before = _snapshot(directory)

    with pytest.raises(RunDirectoryExists, match="Nothing has been written"):
        create_run_dir("L3-aaaaaaaaaaaaaaaa")

    assert _snapshot(directory) == before


@pytest.mark.parametrize("bad", ("", ".", "..", "../peer", "a/b", "a\\b"))
def test_run_id_cannot_traverse_to_another_directory(sandbox, bad):
    with pytest.raises(ValueError):
        create_run_dir(bad)


@pytest.mark.parametrize("bad", ("", ".", "..", "../peer", "a/b", "a\\b"))
def test_artefact_name_cannot_escape_the_run(sandbox, bad):
    with pytest.raises(ValueError):
        artefact_path("L3-aaaaaaaaaaaaaaaa", bad)


def test_missing_run_never_falls_back_to_another_run(sandbox):
    create_run_dir("L3-existing")
    with pytest.raises(FileNotFoundError, match="must not fall back"):
        resolve_run_dir("L3-missing")


def test_generic_writer_cannot_create_a_run_directory(sandbox):
    missing = run_dir("L3-never-opened")
    with pytest.raises(RunDirectoryMissing, match="Only create_run_dir"):
        assert_not_creating_run_dir(missing)
    with pytest.raises(RunDirectoryMissing, match="may not create"):
        assert_run_dir_exists("L3-never-opened")
    assert not os.path.exists(missing)


def test_latest_is_explicitly_non_canonical():
    assert layout.CANONICAL_RUN_IDENTITY == "run_id"
    assert layout.LATEST_POINTER_IS_CANONICAL is False
