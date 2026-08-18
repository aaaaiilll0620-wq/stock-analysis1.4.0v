# -*- coding: utf-8 -*-
"""A test run must never dirty the tracked working tree (M-3 ruling §3).

`seal(final_seal=True)` forbids a dirty tree. Before this ruling,
`tests/test_gate2_c3_preflight.py` drove a runner that rewrote a TRACKED file
with a fresh `generated_at` on every run — so "the canonical suite passed" and
"the tree is clean" could not both be true, and the seal was unreachable for a
second, quieter reason than the missing run.

The regression the ruling asks for is end-to-end:

    clean tree -> full canonical pytest suite -> clean tree

so it is executed that way, in a child process, rather than asserted about one
known offender. A narrower check would pass again the next time some unrelated
test learns to write into the repository.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Set in the child so the suite-inside-a-suite terminates.
CHILD_MARKER = "B0_TREE_GUARD_CHILD"


def _porcelain() -> str:
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(f"git unavailable: {proc.stderr.strip()}")
    return proc.stdout.strip()


pytestmark = pytest.mark.skipif(
    os.environ.get(CHILD_MARKER) == "1",
    reason="child run of the tree-cleanliness guard; would recurse")


def test_the_canonical_suite_leaves_the_working_tree_clean():
    before = _porcelain()
    if before:
        pytest.skip(
            "工作區在測試開始前就不乾淨(開發中狀態);本回歸只在 "
            f"clean tree 起點下有意義。目前:{before.splitlines()[:3]}")

    env = dict(os.environ, **{CHILD_MARKER: "1"})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT, capture_output=True, text=True, env=env)

    after = _porcelain()
    if after:
        raise AssertionError(
            "canonical 測試套件弄髒了受版控的工作區 —— final seal 因此永遠不可達。\n"
            "產物必須寫進 gitignore 的產物根目錄或隔離的 tmp 路徑。\n"
            f"變動:\n{after}")

    assert proc.returncode == 0, (
        "子行程套件失敗(非樹狀污染問題):\n" + proc.stdout[-3000:])
