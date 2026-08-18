# -*- coding: utf-8 -*-
"""Gate 1 provenance overlay `--check` 的 fail-closed 測試。

**要防的具體漏洞**(Codex 2026-08-02 指出):舊版 `--check` 只驗父 MANIFEST 本身
與 Gate 1 檔案,12 個 panel hash 只是從父檔**抄錄**,沒有重新計算 ——
面板被改寫仍會顯示通過。那正是「靜默毀掉結論」的形狀。

本檔用**暫存目錄的合成檔**驗真正上線的那段程式碼
(`build_check_items` / `verify_fingerprints` / `cross_check_parent`),
逐一改寫副本並要求 `--check` 失敗**且指名檔案**。

⚠ 不讀任何真實面板、不執行 permutation、不產生任何 candidate 統計量。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

OV = pytest.importorskip("build_gate1_provenance_overlay")

ARMS = ("A1", "A2", "A3", "A4", "C1", "C3", "B1", "B2", "B3", "B4", "B5", "C2")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))
    return p


@pytest.fixture()
def fixture(tmp_path: Path):
    """合成一整套 root / arm_dir / V0 / overlay / parent,全部指向暫存檔。

    檔案內容用短字串代替 parquet —— sha256 與內容型別無關,
    驗的是「有沒有逐檔重算」,不是 parquet 解析。
    """
    root = tmp_path / "repo"
    arm_dir = root / "arms"
    gate_dir = root / "gate1"

    panels, reports, audits = {}, {}, {}
    for a in ARMS:
        panels[a] = _write(arm_dir / f"arm_{a}_panel.parquet", f"PANEL-{a}")
        reports[a] = _write(arm_dir / f"arm_{a}_report.json", f"REPORT-{a}")
        audits[a] = _write(arm_dir / f"arm_{a}_audit.json", f"AUDIT-{a}")

    v0 = _write(root / "v0_panel.parquet", "V0-PANEL")
    patch = _write(gate_dir / "erratum.patch", "PATCH-BODY")
    runner = _write(root / "runner.py", "RUNNER-BODY")

    parent = {
        "arms": {a: {"panel": panels[a].name, "panel_sha256": _sha(panels[a]),
                     "report": reports[a].name, "report_sha256": _sha(reports[a]),
                     "audit": audits[a].name, "audit_sha256": _sha(audits[a])}
                 for a in ARMS},
        "v0_panel": {"path": v0.name, "sha256": _sha(v0)},
    }
    parent_path = _write(root / "MANIFEST.json",
                         json.dumps(parent, ensure_ascii=False, indent=2))

    ov = {
        "parent": {
            "sha256": _sha(parent_path),
            "panel_sha256": {a: _sha(panels[a]) for a in ARMS},
            "report_sha256": {a: _sha(reports[a]) for a in ARMS},
            "audit_sha256": {a: _sha(audits[a]) for a in ARMS},
            "v0_panel": {"path": "v0_panel.parquet", "sha256": _sha(v0)},
        },
        "files": {"runner": {"path": "runner.py", "sha256": _sha(runner)}},
        "erratum": {"frozen_impl_patch_path": "gate1/erratum.patch",
                    "frozen_impl_patch_sha256": _sha(patch)},
    }
    return {"root": root, "arm_dir": arm_dir, "v0": v0, "patch": patch,
            "runner": runner, "panels": panels, "reports": reports,
            "audits": audits, "parent": parent, "parent_path": parent_path, "ov": ov}


def _check(f) -> list[str]:
    items = OV.build_check_items(f["ov"], f["parent"], root=f["root"],
                                 arm_dir=f["arm_dir"], v0_path=f["v0"],
                                 parent_path=f["parent_path"])
    return OV.verify_fingerprints(items) + OV.cross_check_parent(f["ov"], f["parent"])


# ---------------------------------------------------------------------------
def test_clean_fixture_passes_and_covers_every_artifact(fixture):
    """乾淨狀態必須全過,且重算項目數必須涵蓋全部產物 —— 少驗東西也是漏洞。"""
    assert _check(fixture) == []
    items = OV.build_check_items(fixture["ov"], fixture["parent"],
                                 root=fixture["root"], arm_dir=fixture["arm_dir"],
                                 v0_path=fixture["v0"],
                                 parent_path=fixture["parent_path"])
    # 1 父檔 + 12 面板 + 12 report + 12 audit + 1 V0 + 1 Gate1 檔 + 1 patch
    assert len(items) == 1 + 12 + 12 + 12 + 1 + 1 + 1


@pytest.mark.parametrize("arm", ["A1", "C3", "C2"])
def test_rewritten_panel_copy_fails_and_names_the_file(fixture, arm):
    """**這就是 Codex 指出的漏洞**:改寫一份副本 panel,--check 必須失敗且指名。"""
    fixture["panels"][arm].write_bytes(b"TAMPERED")
    fails = _check(fixture)
    assert fails, f"改寫 {arm} 面板後仍然通過 —— 抄錄值沒被重算"
    assert any(f"arm {arm} 面板" in m for m in fails)
    assert any(fixture["panels"][arm].name in m for m in fails), "失敗訊息沒指名檔案"


def test_rewritten_v0_copy_fails_and_names_the_file(fixture):
    """改寫 V0 副本 —— Gate 1 實際讀的那份,必須失敗且指名。"""
    fixture["v0"].write_bytes(b"TAMPERED-V0")
    fails = _check(fixture)
    assert any("V0 面板" in m for m in fails), f"V0 被改寫卻通過:{fails}"
    assert any(fixture["v0"].name in m for m in fails)


def test_rewritten_report_or_audit_fails(fixture):
    fixture["reports"]["B3"].write_bytes(b"TAMPERED")
    fixture["audits"]["B4"].write_bytes(b"TAMPERED")
    fails = _check(fixture)
    assert any("arm B3 report" in m for m in fails)
    assert any("arm B4 audit" in m for m in fails)


def test_rewritten_patch_file_itself_fails(fixture):
    """patch 檔本身要重算,不可只驗它被記下來的值(Codex §4)。"""
    fixture["patch"].write_bytes(b"TAMPERED-PATCH")
    fails = _check(fixture)
    assert any("勘誤 patch" in m for m in fails)


def test_rewritten_parent_manifest_fails(fixture):
    fixture["parent_path"].write_bytes(b"{}")
    assert any("父 MANIFEST" in m for m in _check(fixture))


def test_missing_file_is_reported_not_skipped(fixture):
    """檔案不存在必須報錯,不得當成「沒東西可比 → 通過」。"""
    fixture["panels"]["A2"].unlink()
    fails = _check(fixture)
    assert any("檔案不存在" in m and "arm A2 面板" in m for m in fails)


def test_cross_check_catches_overlay_copy_diverging_from_parent(fixture):
    """只改父檔現值而檔案照舊 → 逐檔重算過得了,必須靠交叉核對攔下。

    這道防的是「改父檔 + 改 overlay 抄錄值」的對穿路徑。
    """
    fixture["parent"]["arms"]["B1"]["panel_sha256"] = "0" * 64
    fails = OV.cross_check_parent(fixture["ov"], fixture["parent"])
    assert any("arm B1 面板 hash" in m for m in fails)

    fixture["parent"]["v0_panel"]["sha256"] = "1" * 64
    fails = OV.cross_check_parent(fixture["ov"], fixture["parent"])
    assert any("V0 面板 hash" in m for m in fails)


def test_every_arm_is_actually_covered(fixture):
    """逐一改寫 12 個面板,每一個都必須被抓到 —— 不能只驗前幾個。"""
    for arm in ARMS:
        original = fixture["panels"][arm].read_bytes()
        fixture["panels"][arm].write_bytes(b"X")
        fails = _check(fixture)
        assert any(f"arm {arm} 面板" in m for m in fails), f"{arm} 沒被驗到"
        fixture["panels"][arm].write_bytes(original)
    assert _check(fixture) == []
