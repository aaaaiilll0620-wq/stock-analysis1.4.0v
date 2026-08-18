# -*- coding: utf-8 -*-
"""scripts/build_v2_candidate_verifier.py 的 synthetic 測試(Phase A4)。

規格:`docs/預註冊_DataExport0806_V2隔離建置.md` §D(獨立驗證器)、§C.5 第
3 項(驗證 receipt schema)。

跟 `test_build_v2_candidate.py`/`test_build_v2_candidate_phase_a4.py` 同一套
紀律:只用本檔 synthetic fixture(寫在 `tmp_path` 底下),不讀取任何真實的
`tej_exports/DataExport0806*`/`~/tej_cache`/`tej_exports/inbox*`,不執行真正
的 Phase B。**額外規則(§D 架構隔離)**:這個檔案的測試**只 import**
`build_v2_candidate_verifier`(`v`)——不 import `build_v2_candidate`(`b`)
來做任何跨模組委派呼叫;唯一的例外是「用兩個獨立實作各自算出的身分鏈是否
彼此相符」這種**交叉驗證測試**(明確標記在函式名稱/docstring 裡),用來
確認兩份獨立實作真的算的是同一套公式,而不是讓 verifier 的測試依賴
builder 的程式碼路徑。
"""
from __future__ import annotations

import ast
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

v = pytest.importorskip("build_v2_candidate_verifier")

VALID_HASH_A = "a" * 64
VALID_HASH_B = "b" * 64
VALID_HASH_C = "c" * 64

VALID_MARKER_ENVIRONMENT = {
    "implementation_name": "cpython",
    "implementation_version": "3.12.10",
    "os_name": "nt",
    "platform_machine": "AMD64",
    "platform_python_implementation": "CPython",
    "platform_release": "11",
    "platform_system": "Windows",
    "platform_version": "10.0.26200",
    "python_full_version": "3.12.10",
    "python_version": "3.12",
    "sys_platform": "win32",
}


def _runtime_environment_source(marker_identity: str, dependency_lock_identity: str) -> list:
    return [
        "runtime_environment_identity_v1", "CPython", "3.12.10 (full)", "Windows",
        "10.0.26200", "AMD64", "2.2.2", "1.26.4", "16.1.0", "3.1.2", "pyarrow",
        "openpyxl", dependency_lock_identity, marker_identity,
    ]


# ----------------------------------------------------------------------------
# 0. 架構隔離(§D):verifier 不 import builder/tej_importer 的任何函式。
# ----------------------------------------------------------------------------


def test_verifier_module_does_not_import_builder_or_tej_importer():
    tree = ast.parse(
        (REPO_ROOT / "scripts" / "build_v2_candidate_verifier.py").read_text(encoding="utf-8")
    )
    forbidden = {"build_v2_candidate", "tej_importer"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    assert not (found & forbidden), (
        f"verifier 不得 import builder/tej_importer(§D 架構隔離),實際 import 到"
        f" {found & forbidden}"
    )


def test_verifier_module_passes_core_beat_0050_import_whitelist():
    """§C.6 的白名單規則同樣涵蓋這份檔案——借用 `build_v2_candidate.
    check_import_whitelist` 對它自己跑一次(這是唯一允許的跨模組呼叫:一支
    通用的靜態檢查工具,不是 verifier 依賴 builder 的任何業務邏輯)。"""
    b = pytest.importorskip("build_v2_candidate")
    b.check_import_whitelist(REPO_ROOT / "scripts" / "build_v2_candidate_verifier.py")


def test_verifier_import_has_no_filesystem_side_effect(tmp_path):
    import subprocess

    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate_verifier.py"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('build_v2_candidate_verifier', r{str(script_path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=work_dir, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert list(work_dir.iterdir()) == []


def test_verifier_cli_default_returns_nonzero_and_touches_nothing(tmp_path):
    assert v.main(None) == 1
    assert v.main([]) == v.main(["--anything"]) == 1


# ----------------------------------------------------------------------------
# 1. 獨立身分公式(§D:不 import builder,自己重新實作)
# ----------------------------------------------------------------------------


def test_source_data_identity_known_vector():
    result = v.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C)
    payload = (
        f"manifest_sha256={VALID_HASH_A}\n"
        f"manifest_sha256_file_sha256={VALID_HASH_B}\n"
        f"supplement_receipt_sha256={VALID_HASH_C}"
    )
    assert result == v.sha256_hex(payload.encode("utf-8"))


def test_dedup_key_v1_known_vector():
    key = v.dedup_key_v1("price_valuation", "a/b.xlsx", "sheet1", 5, "close")
    payload = b'["dedup_key_v1","price_valuation","a/b.xlsx","sheet1",5,"close"]'
    assert key == v.sha256_hex(payload)


def test_normalize_package_name_pep503():
    assert v.normalize_package_name("PyYAML") == "pyyaml"
    assert v.normalize_package_name("typing_extensions") == "typing-extensions"
    assert v.normalize_package_name("typing.extensions") == "typing-extensions"


def test_verifier_identity_chain_matches_builder_identity_chain_cross_check():
    """交叉驗證:兩份獨立實作的身分鏈公式,對同一組輸入必須算出同一個值
    ——這是驗證『verifier 真的實作了跟 builder 相同的凍結公式』,不是讓
    verifier 的正常測試依賴 builder。"""
    b = pytest.importorskip("build_v2_candidate")
    sdi_builder = b.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C)
    sdi_verifier = v.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C)
    assert sdi_builder == sdi_verifier

    marker_b = b.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    marker_v = v.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    assert marker_b == marker_v

    dedup_b = b.dedup_key_v1("d", "r", "m", 1, "t")
    dedup_v = v.dedup_key_v1("d", "r", "m", 1, "t")
    assert dedup_b == dedup_v


# ----------------------------------------------------------------------------
# 2. verify_aggregate_receipt_identity_chain / verify_runtime_environment_identity
# ----------------------------------------------------------------------------


def _aggregate_receipt_fixture() -> dict:
    marker_identity = v.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    runtime_source = _runtime_environment_source(marker_identity, VALID_HASH_A)
    runtime_identity = v.runtime_environment_identity_v1(runtime_source)
    sdi = v.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C)
    bii = v.build_implementation_identity(
        VALID_HASH_A, VALID_HASH_B, VALID_HASH_C, VALID_HASH_A, runtime_identity, "deadbeef"
    )
    sid = v.snapshot_id_v1(sdi, bii)
    return {
        "manifest_identity": VALID_HASH_A,
        "manifest_sha256_file_identity": VALID_HASH_B,
        "supplement_identity": VALID_HASH_C,
        "importer_identity": VALID_HASH_A,
        "extractor_identity": VALID_HASH_B,
        "builder_identity": VALID_HASH_C,
        "dependency_lock_identity": VALID_HASH_A,
        "runtime_environment_identity_v1": runtime_identity,
        "preregistration_commit": "deadbeef",
        "candidate_schema_version": v.CANDIDATE_SCHEMA_VERSION,
        "source_data_identity": sdi,
        "build_implementation_identity": bii,
        "snapshot_id_v1": sid,
    }, runtime_source, marker_identity


def test_verify_aggregate_receipt_identity_chain_happy_path():
    receipt, _runtime_source, _marker_identity = _aggregate_receipt_fixture()
    checks = v.verify_aggregate_receipt_identity_chain(receipt)
    assert all(c["passed"] for c in checks)
    assert {c["check"] for c in checks} == {
        "source_data_identity", "build_implementation_identity", "snapshot_id_v1"
    }


def test_verify_aggregate_receipt_identity_chain_rejects_tampered_snapshot_id():
    receipt, _rs, _mi = _aggregate_receipt_fixture()
    receipt["snapshot_id_v1"] = "f" * 64
    with pytest.raises(v.IdentityVerificationError) as excinfo:
        v.verify_aggregate_receipt_identity_chain(receipt)
    assert any(c["check"] == "snapshot_id_v1" and not c["passed"] for c in excinfo.value.checks)


def test_verify_aggregate_receipt_identity_chain_rejects_tampered_source_data_identity():
    receipt, _rs, _mi = _aggregate_receipt_fixture()
    receipt["source_data_identity"] = "f" * 64
    with pytest.raises(v.IdentityVerificationError):
        v.verify_aggregate_receipt_identity_chain(receipt)


def test_verify_runtime_environment_identity_happy_path():
    receipt, runtime_source, marker_identity = _aggregate_receipt_fixture()
    checks = v.verify_runtime_environment_identity(
        runtime_environment_source=runtime_source,
        marker_environment_v1=VALID_MARKER_ENVIRONMENT,
        recorded_runtime_environment_identity_v1=receipt["runtime_environment_identity_v1"],
        recorded_marker_environment_identity_v1=marker_identity,
    )
    assert all(c["passed"] for c in checks)


def test_verify_runtime_environment_identity_rejects_tampered_marker_environment():
    receipt, runtime_source, marker_identity = _aggregate_receipt_fixture()
    tampered_marker = dict(VALID_MARKER_ENVIRONMENT, os_name="posix")
    with pytest.raises(v.IdentityVerificationError):
        v.verify_runtime_environment_identity(
            runtime_environment_source=runtime_source,
            marker_environment_v1=tampered_marker,
            recorded_runtime_environment_identity_v1=receipt["runtime_environment_identity_v1"],
            recorded_marker_environment_identity_v1=marker_identity,
        )


# ----------------------------------------------------------------------------
# 3. verify_environment_creation_receipt
# ----------------------------------------------------------------------------


def test_verify_environment_creation_receipt_happy_path():
    env_receipt = {"schema": "environment_creation_receipt_v1", "run_id": "run-1", "exit_code": 0}
    identity = v.environment_creation_identity(env_receipt)
    env_receipt_with_identity = dict(env_receipt, environment_creation_identity=identity)
    file_bytes = v.canonical_json_bytes(env_receipt_with_identity, sort_keys=True)
    file_sha = v.sha256_hex(file_bytes)

    checks = v.verify_environment_creation_receipt(
        environment_creation_receipt=env_receipt_with_identity,
        receipt_file_sha256=file_sha,
        recorded_environment_creation_receipt_sha256=file_sha,
        recorded_environment_creation_identity=identity,
    )
    assert all(c["passed"] for c in checks)


def test_verify_environment_creation_receipt_rejects_file_hash_mismatch():
    env_receipt = {"schema": "environment_creation_receipt_v1", "run_id": "run-1", "exit_code": 0}
    identity = v.environment_creation_identity(env_receipt)
    env_receipt_with_identity = dict(env_receipt, environment_creation_identity=identity)
    with pytest.raises(v.IdentityVerificationError):
        v.verify_environment_creation_receipt(
            environment_creation_receipt=env_receipt_with_identity,
            receipt_file_sha256=VALID_HASH_A,
            recorded_environment_creation_receipt_sha256=VALID_HASH_B,
            recorded_environment_creation_identity=identity,
        )


def test_verify_environment_creation_receipt_rejects_tampered_content():
    env_receipt = {"schema": "environment_creation_receipt_v1", "run_id": "run-1", "exit_code": 0}
    identity = v.environment_creation_identity(env_receipt)
    tampered = dict(env_receipt, environment_creation_identity=identity, run_id="run-2")
    file_bytes = v.canonical_json_bytes(tampered, sort_keys=True)
    file_sha = v.sha256_hex(file_bytes)
    with pytest.raises(v.IdentityVerificationError, match="environment_creation_identity"):
        v.verify_environment_creation_receipt(
            environment_creation_receipt=tampered,
            receipt_file_sha256=file_sha,
            recorded_environment_creation_receipt_sha256=file_sha,
            recorded_environment_creation_identity=identity,  # 舊 identity，跟竄改後內容不符
        )


# ----------------------------------------------------------------------------
# 4. quality sidecar 獨立重建/核對
# ----------------------------------------------------------------------------


def _sidecar_record(**overrides) -> dict:
    record = {
        "dataset": "price_valuation", "source_relpath": "a.xlsx",
        "source_file_sha256": VALID_HASH_A, "source_container_member": "sheet1",
        "source_row_number": 5, "stock_id": "2330", "date": "2020-01-02",
        "source_column": "收盤價", "target_column": "close", "raw_token": None,
        "is_blank": True, "is_unparseable": False, "parser": "pd.to_numeric",
        "unit_scale_applied": 1.0, "resulting_value": None, "dedup_key": None,
    }
    record.update(overrides)
    if record["dedup_key"] is None:
        record["dedup_key"] = v.dedup_key_v1(
            record["dataset"], record["source_relpath"], record["source_container_member"],
            record["source_row_number"], record["target_column"],
        )
    return record


def test_verify_sidecar_records_happy_path():
    sidecar = {"dataset": "price_valuation", "records": [_sidecar_record()]}
    checks = v.verify_sidecar_records(sidecar)
    assert all(c["passed"] for c in checks)


def test_verify_sidecar_records_rejects_tampered_dedup_key():
    record = _sidecar_record()
    record["dedup_key"] = "f" * 64
    sidecar = {"dataset": "price_valuation", "records": [record]}
    with pytest.raises(v.IdentityVerificationError, match="dedup_key"):
        v.verify_sidecar_records(sidecar)


def test_verify_sidecar_records_rejects_blank_unparseable_not_exclusive():
    record = _sidecar_record(is_blank=True, is_unparseable=True)
    sidecar = {"dataset": "price_valuation", "records": [record]}
    with pytest.raises(v.IdentityVerificationError):
        v.verify_sidecar_records(sidecar)


def test_verify_stage_one_and_sidecar_accounting_happy_path():
    counts = [
        {"counts": [{"blank_cell_count": 2, "unparseable_cell_count": 3}]},
        {"counts": [{"blank_cell_count": 1, "unparseable_cell_count": 0}]},
    ]
    checks = v.verify_stage_one_and_sidecar_accounting(
        per_file_stage_one_counts=counts, sidecar_record_count=6
    )
    assert checks[0]["passed"] is True


def test_verify_stage_one_and_sidecar_accounting_rejects_mismatch():
    counts = [{"counts": [{"blank_cell_count": 2, "unparseable_cell_count": 3}]}]
    with pytest.raises(v.IdentityVerificationError):
        v.verify_stage_one_and_sidecar_accounting(
            per_file_stage_one_counts=counts, sidecar_record_count=999
        )


def test_verify_final_null_causes_accounting_happy_path():
    causes = {"close": {"RETAINED_BLANK": 1, "RETAINED_UNPARSEABLE": 2}}
    checks = v.verify_final_null_causes_accounting(
        final_null_causes=causes, final_null_counts_from_output={"close": 3}
    )
    assert all(c["passed"] for c in checks)


def test_verify_final_null_causes_accounting_rejects_mismatch():
    causes = {"close": {"RETAINED_BLANK": 1, "RETAINED_UNPARSEABLE": 2}}
    with pytest.raises(v.IdentityVerificationError):
        v.verify_final_null_causes_accounting(
            final_null_causes=causes, final_null_counts_from_output={"close": 4}
        )


def test_classify_raw_cell_blank():
    assert v.classify_raw_cell(None) == {
        "is_blank": True, "is_unparseable": False, "raw_token": None, "parsed_value": None,
    }
    assert v.classify_raw_cell("   ") == {
        "is_blank": True, "is_unparseable": False, "raw_token": None, "parsed_value": None,
    }


def test_classify_raw_cell_unparseable():
    result = v.classify_raw_cell(".")
    assert result["is_blank"] is False
    assert result["is_unparseable"] is True
    assert result["raw_token"] == "."
    assert result["parsed_value"] is None


def test_classify_raw_cell_parsed():
    result = v.classify_raw_cell("123.45")
    assert result["is_blank"] is False
    assert result["is_unparseable"] is False
    assert result["parsed_value"] == 123.45


@pytest.mark.parametrize("token", ["nan", "NaN", "NAN", "  nan  "])
def test_classify_raw_cell_literal_nan_is_unparseable_not_parsed(token):
    """Codex review P1 修正:`float("nan")` 不拋例外,但 `tej_importer` 的
    `pd.to_numeric(...).isna()` 判斷把字面 `nan`(不論大小寫)歸類成
    unparseable——這裡必須跟 importer 對齊,不能誤判成『成功解析出一個
    數字』。"""
    result = v.classify_raw_cell(token)
    assert result["is_blank"] is False
    assert result["is_unparseable"] is True
    assert result["parsed_value"] is None


@pytest.mark.parametrize("token,expected_sign", [("inf", 1), ("-inf", -1), ("Infinity", 1)])
def test_classify_raw_cell_infinity_remains_parsed(token, expected_sign):
    """無窮大跟 importer 一致,維持解析成功(不受 nan 修正影響)。"""
    result = v.classify_raw_cell(token)
    assert result["is_blank"] is False
    assert result["is_unparseable"] is False
    assert result["parsed_value"] == float(token)
    assert (result["parsed_value"] > 0) == (expected_sign > 0)


def _make_synthetic_xlsx(path, *, header, rows, extra_sheets=None):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(header)
    for row in rows:
        ws.append(row)
    for sheet_name, sheet_header, sheet_rows in extra_sheets or []:
        extra_ws = wb.create_sheet(sheet_name)
        extra_ws.append(sheet_header)
        for row in sheet_rows:
            extra_ws.append(row)
    wb.save(str(path))


def _make_synthetic_tej_zip(path, *, header, rows, member_name="data.csv", extra_members=None):
    """依 `tej_importer._read_zip_csv_raw` 記錄的真實 TEJ 外部格式契約
    (UTF-16 編碼、Tab 分隔)組一份 synthetic zip——跟這份驗證器獨立實作
    要凍結的格式假設完全一致(Codex review P0 修正)。"""
    lines = ["\t".join(header)]
    lines.extend(
        "\t".join("" if c is None else str(c) for c in row) for row in rows
    )
    text = "\r\n".join(lines) + "\r\n"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(member_name, text.encode("utf-16"))
        for name, content in (extra_members or {}).items():
            zf.writestr(name, content)


def test_independent_read_xlsx_rows_real_file(tmp_path):
    """§D 第 18 輪核心職責的真正回歸測試:用 openpyxl 寫一份 synthetic
    .xlsx,再用這份驗證器**獨立**的讀取路徑讀回來,確認實體列號/表頭/儲存
    格值都正確——不透過 tej_importer 的任何函式。"""
    path = tmp_path / "synthetic.xlsx"
    _make_synthetic_xlsx(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", 600.5], ["2317 鴻海", "."], ["2454 聯發科", None]],
    )
    rows = v.independent_read_xlsx_rows(path)
    assert len(rows) == 3
    assert rows[0]["sheet_name"] == "Sheet"
    assert rows[0]["source_row_number"] == 2  # 表頭是實體第 1 列
    assert rows[0]["cells"]["收盤價"] == 600.5
    assert rows[1]["source_row_number"] == 3
    assert rows[1]["cells"]["收盤價"] == "."
    assert rows[2]["source_row_number"] == 4
    assert rows[2]["cells"]["收盤價"] is None


def test_independent_read_xlsx_rows_only_reads_first_worksheet(tmp_path):
    """Codex review P0 修正:真實 TEJ 匯出的 .xlsx 只有第一個工作表是
    資料——跟 `tej_importer._read_xlsx_raw`(只讀 `wb.sheetnames[0]`)
    對齊,不能讀全部工作表(否則多工作表檔案會產生假 mismatch)。"""
    path = tmp_path / "synthetic.xlsx"
    _make_synthetic_xlsx(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", "."]],
        extra_sheets=[("PhantomSheet", ["股票代號 股票名稱", "收盤價"], [["9999 幽靈公司", "."]])],
    )
    rows = v.independent_read_xlsx_rows(path)
    assert {r["sheet_name"] for r in rows} == {"Sheet"}
    assert not any("幽靈" in str(cells) for cells in (r["cells"] for r in rows))


def test_independent_read_xlsx_rows_rejects_completely_empty_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "empty.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Sheet"
    wb.save(str(path))
    with pytest.raises(ValueError, match="連表頭都沒有"):
        v.independent_read_xlsx_rows(path)


def test_independent_read_zip_csv_rows_real_file(tmp_path):
    """真實 TEJ 格式(UTF-16 + Tab 分隔)的回歸測試——不是驗證器自己能讀
    的合成格式(Codex review P0 修正)。"""
    path = tmp_path / "synthetic.zip"
    _make_synthetic_tej_zip(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", 600.5], ["2317 鴻海", "."]],
    )
    rows = v.independent_read_zip_csv_rows(path)
    assert len(rows) == 2
    assert rows[0]["sheet_name"] == "data.csv"
    assert rows[0]["source_row_number"] == 2
    assert rows[0]["cells"]["收盤價"] == "600.5"
    assert rows[1]["cells"]["收盤價"] == "."


def test_independent_read_zip_csv_rows_only_reads_first_csv_member(tmp_path):
    """Codex review P0 修正的延伸:跟 `tej_importer._read_zip_csv_raw`
    (`csv_names[0]`)對齊,只讀 `zf.namelist()` 裡第一個 `.csv` 成員,不是
    全部。"""
    path = tmp_path / "synthetic.zip"
    _make_synthetic_tej_zip(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", "."]],
        member_name="a_data.csv",
        extra_members={
            "z_phantom.csv": (
                "股票代號 股票名稱\t收盤價\r\n9999 幽靈公司\t.\r\n"
            ).encode("utf-16")
        },
    )
    rows = v.independent_read_zip_csv_rows(path)
    assert {r["sheet_name"] for r in rows} == {"a_data.csv"}


def test_independent_read_zip_csv_rows_pads_short_rows_and_rejects_long_rows(tmp_path):
    """跟 `tej_importer._read_zip_csv_raw` 對齊的外部格式契約:短列補齊
    空字串;長列 fail-closed。"""
    path = tmp_path / "short.zip"
    with zipfile.ZipFile(path, "w") as zf:
        text = "col_a\tcol_b\tcol_c\r\nx\r\n"
        zf.writestr("data.csv", text.encode("utf-16"))
    rows = v.independent_read_zip_csv_rows(path)
    assert rows[0]["cells"] == {"col_a": "x", "col_b": "", "col_c": ""}

    path2 = tmp_path / "long.zip"
    with zipfile.ZipFile(path2, "w") as zf:
        text = "col_a\tcol_b\r\nx\ty\tz\r\n"
        zf.writestr("data.csv", text.encode("utf-16"))
    with pytest.raises(ValueError, match="格式異常"):
        v.independent_read_zip_csv_rows(path2)


def test_independent_raw_cell_reconstruction_xlsx_returns_only_blank_and_unparseable(tmp_path):
    path = tmp_path / "synthetic.xlsx"
    _make_synthetic_xlsx(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", 600.5], ["2317 鴻海", "."], ["2454 聯發科", None]],
    )
    records = v.independent_raw_cell_reconstruction(path, target_columns={"收盤價": "close"})
    # 只有 2 筆(unparseable + blank)——parsed 那一列(600.5)不進結果。
    assert len(records) == 2
    by_row = {r["source_row_number"]: r for r in records}
    assert by_row[3]["is_unparseable"] is True
    assert by_row[3]["raw_token"] == "."
    assert by_row[4]["is_blank"] is True
    assert by_row[4]["raw_token"] is None
    for r in records:
        assert r["source_container_member"] == "Sheet"
        assert r["source_column"] == "收盤價"
        assert r["target_column"] == "close"


def test_independent_raw_cell_reconstruction_zip_returns_only_blank_and_unparseable(tmp_path):
    path = tmp_path / "synthetic.zip"
    _make_synthetic_tej_zip(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", 600.5], ["2317 鴻海", "."], ["2454 聯發科", None]],
    )
    records = v.independent_raw_cell_reconstruction(path, target_columns={"收盤價": "close"})
    assert len(records) == 2
    by_row = {r["source_row_number"]: r for r in records}
    assert by_row[3]["is_unparseable"] is True
    assert by_row[3]["raw_token"] == "."
    assert by_row[4]["is_blank"] is True


def test_independent_raw_cell_reconstruction_rejects_unsupported_suffix(tmp_path):
    path = tmp_path / "synthetic.txt"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\.xlsx/\.zip"):
        v.independent_raw_cell_reconstruction(path, target_columns={"a": "b"})


def test_independent_raw_cell_reconstruction_does_not_reference_tej_importer_identifier():
    """靜態確認:這支函式的**可執行程式碼**裡沒有任何對 `tej_importer`
    這個識別字的使用(跟 test_verifier_module_does_not_import_builder_or_
    tej_importer 的 import 層級檢查互補——這裡額外確認函式體本身沒有透過
    屬性存取的方式繞過 import 檢查去呼叫 tej_importer 的東西,例如
    `sys.modules['tej_importer']`)。用 AST 只看真正的識別字節點
    (`ast.Name`),不誤判 docstring 裡「不跟 tej_importer 共用程式碼」這種
    純文字說明。"""
    import inspect

    source = inspect.getsource(v.independent_raw_cell_reconstruction)
    tree = ast.parse(source)
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "tej_importer" not in referenced_names


def test_cross_check_reconstruction_against_sidecar_happy_path():
    reconstructed = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    sidecar = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    checks = v.cross_check_reconstruction_against_sidecar(
        reconstructed_records=reconstructed, sidecar_records=sidecar
    )
    assert all(c["passed"] for c in checks)


def test_cross_check_reconstruction_against_sidecar_rejects_extra_sidecar_entry():
    reconstructed = []
    sidecar = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    with pytest.raises(v.IdentityVerificationError, match="不完全相同"):
        v.cross_check_reconstruction_against_sidecar(
            reconstructed_records=reconstructed, sidecar_records=sidecar
        )


def test_cross_check_reconstruction_against_sidecar_rejects_mismatched_raw_token():
    reconstructed = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    sidecar = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "N/A"},
    ]
    with pytest.raises(v.IdentityVerificationError, match="不符"):
        v.cross_check_reconstruction_against_sidecar(
            reconstructed_records=reconstructed, sidecar_records=sidecar
        )


def test_cross_check_reconstruction_against_sidecar_rejects_duplicate_key_in_sidecar():
    """Codex review P1 修正:sidecar 出現兩筆相同 locator key 但內容矛盾
    (raw_token 不同)的記錄——舊版本用 dict comprehension 建 lookup,
    last-write-wins 會讓其中一筆靜默消失,矛盾證據永遠不會被看到。修正後
    必須在建 lookup 的階段就直接 fail-closed。"""
    reconstructed = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    sidecar = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "N/A"},
    ]
    with pytest.raises(v.IdentityVerificationError, match="重複"):
        v.cross_check_reconstruction_against_sidecar(
            reconstructed_records=reconstructed, sidecar_records=sidecar
        )


def test_cross_check_reconstruction_against_sidecar_rejects_duplicate_key_in_reconstruction():
    reconstructed = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    sidecar = [
        {"source_container_member": "Sheet", "source_row_number": 3,
         "target_column": "close", "is_blank": False, "is_unparseable": True, "raw_token": "."},
    ]
    with pytest.raises(v.IdentityVerificationError, match="重複"):
        v.cross_check_reconstruction_against_sidecar(
            reconstructed_records=reconstructed, sidecar_records=sidecar
        )


def test_independent_raw_cell_reconstruction_end_to_end_matches_sidecar(tmp_path):
    """端到端:寫一份 synthetic .xlsx，獨立重建它的 blank/unparseable
    儲存格，包成跟 builder sidecar 記錄相容的最小形狀，確認能通過交叉核對
    ——這是『驗證器真的能拿獨立重建結果去核對 sidecar』的完整路徑測試。"""
    path = tmp_path / "synthetic.xlsx"
    _make_synthetic_xlsx(
        path,
        header=["股票代號 股票名稱", "收盤價"],
        rows=[["2330 台積電", 600.5], ["2317 鴻海", "."]],
    )
    reconstructed = v.independent_raw_cell_reconstruction(
        path, target_columns={"收盤價": "close"}
    )
    # 模擬 builder sidecar 對同一份檔案、同一格記錄了一致的分類。
    sidecar_records = [
        {
            "source_container_member": r["source_container_member"],
            "source_row_number": r["source_row_number"],
            "target_column": r["target_column"],
            "is_blank": r["is_blank"],
            "is_unparseable": r["is_unparseable"],
            "raw_token": r["raw_token"],
        }
        for r in reconstructed
    ]
    checks = v.cross_check_reconstruction_against_sidecar(
        reconstructed_records=reconstructed, sidecar_records=sidecar_records
    )
    assert all(c["passed"] for c in checks)


# ----------------------------------------------------------------------------
# 5. run 層級單發 `.claim` 鎖機制(§D 單發驗證規則)
# ----------------------------------------------------------------------------


def test_claim_filename_format():
    assert v.claim_filename("run-abc-123") == "run-abc-123.binding_verification.claim"


@pytest.mark.parametrize("bad_run_id", ["", ".", "..", "a/b", "a\\b", "a\x00b"])
def test_claim_filename_rejects_unsafe_run_id(bad_run_id):
    with pytest.raises(ValueError):
        v.claim_filename(bad_run_id)


def test_claim_binding_verification_rejects_identity_mismatch_without_creating_file(tmp_path):
    with pytest.raises(ValueError, match="verifier_identity"):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_B, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
        )
    assert list(tmp_path.iterdir()) == []


def test_claim_binding_verification_happy_path_creates_claim_file(tmp_path):
    claim_path, content = v.claim_binding_verification(
        run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
        authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
    )
    assert claim_path.exists()
    assert claim_path.name == "run-1.binding_verification.claim"
    assert content["run_id"] == "run-1"
    assert content["authorized_verifier_identity"] == VALID_HASH_A


def test_claim_binding_verification_second_attempt_for_same_run_id_fails(tmp_path):
    v.claim_binding_verification(
        run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
        authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
    )
    # 即使第二次是「另一個、身分核對也通過」的驗證器嘗試，run_id 層級的鎖檔
    # 結構上就是只用 run_id 命名，第二次一律失敗（§D 第 18 輪修正的核心）。
    with pytest.raises(ValueError, match="已經用掉"):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t1",
        )


def test_claim_binding_verification_different_run_ids_are_independent(tmp_path):
    v.claim_binding_verification(
        run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
        authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
    )
    # 不同 run_id：不受第一個 run 的鎖檔影響。
    claim_path, _content = v.claim_binding_verification(
        run_dir=tmp_path, run_id="run-2", verifier_identity=VALID_HASH_A,
        authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
    )
    assert claim_path.exists()


def test_is_claim_write_failed_marker():
    assert v.is_claim_write_failed_marker(
        {"status": "CLAIM_WRITE_FAILED", "error_type": "OSError", "error_message": "x"}
    ) is True
    assert v.is_claim_write_failed_marker({"run_id": "run-1"}) is False
    assert v.is_claim_write_failed_marker(None) is False
    assert v.is_claim_write_failed_marker("not a dict") is False


def test_claim_binding_verification_fsync_failure_leaves_persistent_failure_marker_not_deleted(
    tmp_path, monkeypatch
):
    """Codex review 修正(REQUEST CHANGES 第 2 項):`.claim` 排他建立成功
    後,`os.fsync` 失敗——**不得**刪除已建立的鎖檔,必須留下可持久辨識的
    失敗標記。"""

    def failing_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(v.os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="simulated fsync failure"):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
        )

    claim_path = tmp_path / "run-1.binding_verification.claim"
    assert claim_path.exists()  # 沒有被刪除
    content = json.loads(claim_path.read_text(encoding="utf-8"))
    assert v.is_claim_write_failed_marker(content)
    assert content["error_type"] == "OSError"
    assert "simulated fsync failure" in content["error_message"]


def test_claim_binding_verification_write_failure_leaves_persistent_failure_marker_not_deleted(
    tmp_path, monkeypatch
):
    """同上,但注入點是寫入本身(`os.fdopen`)失敗,不是 `fsync`——涵蓋
    「寫入/`fsync` 失敗」要求裡的另一半。"""

    def failing_fdopen(fd, mode):
        os.close(fd)
        raise OSError("simulated write failure")

    monkeypatch.setattr(v.os, "fdopen", failing_fdopen)

    with pytest.raises(OSError, match="simulated write failure"):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
        )

    claim_path = tmp_path / "run-1.binding_verification.claim"
    assert claim_path.exists()
    content = json.loads(claim_path.read_text(encoding="utf-8"))
    assert v.is_claim_write_failed_marker(content)


def test_claim_binding_verification_after_write_or_fsync_failure_permanently_blocks_retry(
    tmp_path, monkeypatch
):
    """核心不變量:即使後續重試時 `fsync` 已經恢復正常，這個 `run_id` 的
    鎖檔已經因為前一次失敗而永久存在,**任何**後續 claim 嘗試都必須失敗
    ——不得因為「這次環境正常了」就恢復驗證機會。"""

    def failing_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(v.os, "fsync", failing_fsync)
    with pytest.raises(OSError):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
        )

    monkeypatch.undo()  # 恢復真正的 os.fsync

    with pytest.raises(ValueError, match="已經用掉"):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t1",
        )


def test_claim_binding_verification_marker_rewrite_failure_does_not_mask_original_exception(
    tmp_path, monkeypatch
):
    """`_mark_claim_write_failed` 本身是 best-effort——即使補寫失敗標記
    這件事自己也失敗(例如磁碟真的滿到連標記都寫不進去),往外拋的必須是
    **原始**例外(fsync 失敗的根因),不能被補寫失敗的次要例外蓋掉。"""

    def failing_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(v.os, "fsync", failing_fsync)

    real_open = open

    def failing_open(path, mode="r", *args, **kwargs):
        if str(path).endswith(".claim") and "wb" in mode:
            raise OSError("simulated marker rewrite failure too")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", failing_open)

    with pytest.raises(OSError, match="simulated fsync failure"):
        v.claim_binding_verification(
            run_dir=tmp_path, run_id="run-1", verifier_identity=VALID_HASH_A,
            authorized_verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_C, start_timestamp_utc="t0",
        )
    # 即使補寫標記也失敗，排他建立出來的檔案本身還是留在磁碟上（內容可能是
    # 空的），一樣結構性阻擋後續 claim。
    claim_path = tmp_path / "run-1.binding_verification.claim"
    assert claim_path.exists()


# ----------------------------------------------------------------------------
# 6. 驗證 receipt builder/validator/writer
# ----------------------------------------------------------------------------


def _passing_checks() -> list:
    return [{"check": "x", "passed": True}]


def _failing_checks() -> list:
    return [{"check": "x", "passed": False}]


def test_build_verification_receipt_validated_round_trips():
    receipt = v.build_verification_receipt(
        run_id="run-1", verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_B,
        verifier_runtime_environment_identity_v1_value=VALID_HASH_C,
        checks=_passing_checks(), overall_status=v.BUILD_VALIDATED,
        verified_at_utc="t0",
    )
    v.validate_verification_receipt(receipt)
    assert receipt["binding"] is True


def test_build_verification_receipt_rejects_validated_with_failed_check():
    with pytest.raises(ValueError, match="BUILD_VALIDATED"):
        v.build_verification_receipt(
            run_id="run-1", verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_B,
            verifier_runtime_environment_identity_v1_value=VALID_HASH_C,
            checks=_failing_checks(), overall_status=v.BUILD_VALIDATED,
            verified_at_utc="t0",
        )


def test_build_verification_receipt_rejects_failed_status_with_no_failed_check():
    with pytest.raises(ValueError, match="BUILD_VERIFICATION_FAILED"):
        v.build_verification_receipt(
            run_id="run-1", verifier_identity=VALID_HASH_A, build_receipt_path="p",
            build_receipt_sha256=VALID_HASH_B,
            verifier_runtime_environment_identity_v1_value=VALID_HASH_C,
            checks=_passing_checks(), overall_status=v.BUILD_VERIFICATION_FAILED,
            verified_at_utc="t0",
        )


def test_build_verification_receipt_allows_failed_status_with_failed_check():
    receipt = v.build_verification_receipt(
        run_id="run-1", verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_B,
        verifier_runtime_environment_identity_v1_value=VALID_HASH_C,
        checks=_failing_checks(), overall_status=v.BUILD_VERIFICATION_FAILED,
        verified_at_utc="t0",
    )
    v.validate_verification_receipt(receipt)


def test_write_verification_receipt_exclusive_create(tmp_path):
    receipt = v.build_verification_receipt(
        run_id="run-1", verifier_identity=VALID_HASH_A, build_receipt_path="p",
        build_receipt_sha256=VALID_HASH_B,
        verifier_runtime_environment_identity_v1_value=VALID_HASH_C,
        checks=_passing_checks(), overall_status=v.BUILD_VALIDATED,
        verified_at_utc="t0",
    )
    path = tmp_path / "verification.json"
    abs_path, digest = v.write_verification_receipt_json_atomic(path, receipt)
    assert abs_path.exists()
    assert digest == v.sha256_hex(abs_path.read_bytes())
    with pytest.raises(ValueError, match="已存在"):
        v.write_verification_receipt_json_atomic(path, receipt)


# ----------------------------------------------------------------------------
# 7. 正式狀態判定規則(§D 三選一)
# ----------------------------------------------------------------------------


def test_determine_official_run_status_no_claim_reflects_aggregate_status():
    assert v.determine_official_run_status(
        claim_exists=False, binding_verification_receipt=None,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_A,
    ) == "BUILD_COMPLETE_AWAITING_VERIFICATION"

    assert v.determine_official_run_status(
        claim_exists=False, binding_verification_receipt=None,
        aggregate_build_receipt_overall_status="BUILD_FAILED_PARTIAL",
        aggregate_build_receipt_sha256=VALID_HASH_A,
    ) == "BUILD_FAILED_PARTIAL"


def test_determine_official_run_status_claim_without_receipt_is_verification_failed_crash_persistence():
    """§D crash 持久性規則:`.claim` 存在但沒有對應 receipt——一律
    `BUILD_VERIFICATION_FAILED`,絕不回退成『還在等驗證』。"""
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=None,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_A,
    ) == "BUILD_VERIFICATION_FAILED"


def test_determine_official_run_status_partial_aggregate_can_never_become_validated():
    """Codex review P0 反例(第二輪,已重現):`aggregate_build_receipt_
    overall_status=BUILD_FAILED_PARTIAL`,但 claim/receipt/現在重新雜湊的
    三方雜湊全部一致,且驗證 receipt 自己宣稱 `BUILD_VALIDATED`——舊邏輯
    完全沒有核對彙總 receipt 自己的 overall_status,會誤判成
    `BUILD_VALIDATED`,直接違反預註冊文件「`BUILD_FAILED_PARTIAL` 永遠不能
    變成 `BUILD_VALIDATED`」(§D)。修正後必須是 `BUILD_VERIFICATION_
    FAILED`。"""
    claim_content = {
        "run_id": "run-1", "authorized_verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B,
    }
    receipt = {
        "run_id": "run-1", "verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=receipt,
        aggregate_build_receipt_overall_status="BUILD_FAILED_PARTIAL",
        aggregate_build_receipt_sha256=VALID_HASH_B,
        claim_content=claim_content,
    ) == "BUILD_VERIFICATION_FAILED"


def test_determine_official_run_status_rejects_illegal_aggregate_status_even_with_claim():
    """`aggregate_build_receipt_overall_status` 的合法性檢查現在對兩個
    分支(有無 `.claim`)都適用,不再只在無 `.claim` 分支裡驗證。"""
    with pytest.raises(ValueError, match="aggregate_build_receipt_overall_status"):
        v.determine_official_run_status(
            claim_exists=True, binding_verification_receipt=None,
            aggregate_build_receipt_overall_status="NOT_A_REAL_STATUS",
            aggregate_build_receipt_sha256=VALID_HASH_A,
        )


def test_determine_official_run_status_claim_with_valid_matching_receipt_uses_its_status():
    claim_content = {
        "run_id": "run-1", "authorized_verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B,
    }
    receipt = {
        "run_id": "run-1", "verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=receipt,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_B, claim_content=claim_content,
    ) == "BUILD_VALIDATED"


def test_determine_official_run_status_requires_claim_content_when_receipt_present():
    """Codex review 修正(REQUEST CHANGES 第 1 項的前置要求):存在 binding
    驗證 receipt 時,呼叫端**必須**提供 `claim_content`(不能假設鎖檔存在
    就等於內容可信/可省略)——缺席直接 raise,不是靜默當成 mismatch。"""
    receipt = {
        "run_id": "run-1", "verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    with pytest.raises(ValueError, match="claim_content"):
        v.determine_official_run_status(
            claim_exists=True, binding_verification_receipt=receipt,
            aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
            aggregate_build_receipt_sha256=VALID_HASH_B, claim_content=None,
        )


def test_determine_official_run_status_claim_without_receipt_still_does_not_require_claim_content():
    """crash 持久性分支(沒有對應 receipt)不需要 `claim_content` 就能判定
    ——`.claim` 存在但驗證器 crash 沒寫出任何 receipt 時,呼叫端可能連
    `.claim` 內容本身都還沒讀,這個分支必須維持能直接判定
    `BUILD_VERIFICATION_FAILED`。"""
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=None,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_A, claim_content=None,
    ) == "BUILD_VERIFICATION_FAILED"


def test_determine_official_run_status_receipt_run_id_mismatch_is_verification_failed():
    claim_content = {
        "run_id": "run-1", "authorized_verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B,
    }
    receipt = {
        "run_id": "run-WRONG", "verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=receipt,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_B, claim_content=claim_content,
    ) == "BUILD_VERIFICATION_FAILED"


def test_determine_official_run_status_receipt_stale_build_receipt_hash_is_verification_failed():
    """驗證 receipt 記錄的 `build_receipt_sha256` 必須等於**現在**重新雜湊
    彙總 build receipt 的結果——如果彙總 receipt 檔案在驗證之後被動過手腳
    (現在的雜湊已經不同),正式狀態必須是 `BUILD_VERIFICATION_FAILED`。
    這裡 claim 跟 receipt 兩者互相一致(都是 B),只有『現在』重新雜湊出
    的彙總 receipt(C)是離群的那一個。"""
    claim_content = {
        "run_id": "run-1", "authorized_verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B,
    }
    receipt = {
        "run_id": "run-1", "verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=receipt,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_C,  # 現在重新雜湊出的值不同
        claim_content=claim_content,
    ) == "BUILD_VERIFICATION_FAILED"


def test_determine_official_run_status_claim_sha_mismatch_receipt_and_aggregate_agree_is_verification_failed():
    """Codex review 反例(REQUEST CHANGES 第 1 項指定的精確反例):
    `claim.build_receipt_sha256=A`、`verification_receipt.build_receipt_
    sha256=B`、**現在**重新雜湊的彙總 receipt 也是 `B`——receipt 跟『現在』
    的彙總 receipt 兩者互相一致,但都跟 `.claim` 當初拍下的快照(A)不同。
    修正前的邏輯只核對 receipt vs 現在雜湊兩者是否相符,會誤判成通過;
    修正後的三方雜湊等式必須判定 `BUILD_VERIFICATION_FAILED`。"""
    claim_content = {
        "run_id": "run-1", "authorized_verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_A,
    }
    receipt = {
        "run_id": "run-1", "verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=receipt,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_B,
        claim_content=claim_content,
    ) == "BUILD_VERIFICATION_FAILED"


def test_determine_official_run_status_never_picks_a_pass_among_multiple_attempts():
    """規則裡不存在『只要有任何一份 PASS 就採計』這個選項——結構上一個
    run_id 只可能有一份 binding receipt(claim 鎖檔本身保證),這裡驗證
    呼叫端就算誤傳了一份『看起來過的』receipt,只要跟 claim 記錄的
    run_id/verifier_identity 對不上,也不會被誤採計成 BUILD_VALIDATED。"""
    claim_content = {
        "run_id": "run-1", "authorized_verifier_identity": VALID_HASH_A,
        "build_receipt_sha256": VALID_HASH_B,
    }
    forged_receipt = {
        "run_id": "run-1", "verifier_identity": VALID_HASH_B,  # 不是 claim 記錄的那個
        "build_receipt_sha256": VALID_HASH_B, "overall_status": "BUILD_VALIDATED",
    }
    assert v.determine_official_run_status(
        claim_exists=True, binding_verification_receipt=forged_receipt,
        aggregate_build_receipt_overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        aggregate_build_receipt_sha256=VALID_HASH_B, claim_content=claim_content,
    ) == "BUILD_VERIFICATION_FAILED"
