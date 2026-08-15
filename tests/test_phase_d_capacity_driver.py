# -*- coding: utf-8 -*-
"""Phase D (2026-08-15) offline mechanism tests for the NEW real P_ONLY_EVIDENCE
capacity dry-run driver. Synthetic/light-weight where the underlying real
pipeline (score_store/l4a_decision/DuckDB) is too heavy to fixture here --
Phase C's existing test_identity_collector_capacity_and_ops.py already proves
capacity.py's own library functions against synthetic receipts; this file
only covers the NEW code added on top (capacity_driver.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from identity_collector import capacity_driver  # noqa: E402


def test_frozen_scores_store_glob_points_at_frozen_dir(tmp_path):
    scores_dir = tmp_path / "finmind_cache_scores"
    scores_dir.mkdir()
    store = capacity_driver.FrozenScoresStore(scores_dir)
    assert store.glob("Scores") == str(scores_dir / "*.parquet")
    with pytest.raises(AssertionError):
        store.glob("TaiwanStockPrice")


def test_frozen_scores_store_read_and_exists(tmp_path):
    scores_dir = tmp_path / "finmind_cache_scores"
    scores_dir.mkdir()
    df = pd.DataFrame({"as_of": ["2020-01-01"], "stock_id": ["1101"], "composite": [50.0]})
    df.to_parquet(scores_dir / "1101.parquet", index=False)
    store = capacity_driver.FrozenScoresStore(scores_dir)
    assert store.exists("Scores", "1101") is True
    assert store.exists("Scores", "9999") is False
    got = store.read("Scores", "1101")
    assert got is not None and got.iloc[0]["composite"] == 50.0
    assert store.read("Scores", "9999") is None


def test_build_code_hash_manifest_all_16_real_files_hashed():
    manifest = capacity_driver.build_code_hash_manifest()
    assert set(manifest) == set(capacity_driver.CODE_HASH_PATHS)
    for key, digest in manifest.items():
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), (key, digest)


def test_artifact_hash_manifest_shape():
    files = {"a.parquet": {"bytes": 10, "sha256": "0" * 64}}
    manifest = capacity_driver._artifact_hash_manifest(files)
    assert manifest["files"] == files
    assert len(manifest["aggregate_sha256"]) == 64
