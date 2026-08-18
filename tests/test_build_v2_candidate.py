# -*- coding: utf-8 -*-
"""scripts/build_v2_candidate.py 的 synthetic 測試(Phase A2a)。

規格:`docs/預註冊_DataExport0806_V2隔離建置.md` §C.1/§C.4/§C.5/§D。

**只用本檔 synthetic fixture(寫在 `tmp_path` 底下)**——不讀取任何真實的
`tej_exports/DataExport0806_manifest.csv`/`.sha256`、`~/tej_cache`、
`tej_exports/inbox*`,也不 import/呼叫任何獨立 verifier(本輪尚未實作)。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

b = pytest.importorskip("build_v2_candidate")

VALID_HASH_A = "a" * 64
VALID_HASH_B = "b" * 64
VALID_HASH_C = "c" * 64
VALID_SNAPSHOT_ID = "a" * 64

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


# ----------------------------------------------------------------------------
# 1. Canonical JSON / SHA-256 helpers
# ----------------------------------------------------------------------------


def test_canonical_json_bytes_is_compact_ascii_and_key_order_independent():
    payload_a = b.canonical_json_bytes({"b": 1, "a": 2}, sort_keys=True)
    payload_b = b.canonical_json_bytes({"a": 2, "b": 1}, sort_keys=True)
    assert payload_a == payload_b
    assert payload_a == b'{"a":2,"b":1}'


def test_canonical_json_bytes_escapes_non_ascii():
    payload = b.canonical_json_bytes(["中文"], sort_keys=False)
    assert b"\\u" in payload
    assert "中".encode("utf-8") not in payload


def test_sha256_hex_matches_hashlib_directly():
    import hashlib

    payload = b"hello world"
    assert b.sha256_hex(payload) == hashlib.sha256(payload).hexdigest()


def test_sha256_hex_rejects_non_bytes():
    with pytest.raises(TypeError):
        b.sha256_hex("not bytes")


# ----------------------------------------------------------------------------
# 2. File SHA-256 identity helper
# ----------------------------------------------------------------------------


def test_sha256_of_file_matches_hashlib(tmp_path):
    import hashlib

    p = tmp_path / "some_file.bin"
    p.write_bytes(b"a" * (9 * 1024 * 1024) + b"tail-bytes")  # cross the 8 MiB chunk boundary
    assert b.sha256_of_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_sha256_of_file_one_byte_change_alters_hash(tmp_path):
    p1 = tmp_path / "a.bin"
    p2 = tmp_path / "b.bin"
    p1.write_bytes(b"identical-except-one-byte-X")
    p2.write_bytes(b"identical-except-one-byte-Y")
    assert b.sha256_of_file(p1) != b.sha256_of_file(p2)


# ----------------------------------------------------------------------------
# 3. Manifest pair validation
# ----------------------------------------------------------------------------


def _write_manifest_csv(path: Path, rows, header=("relpath", "size_bytes", "sha256", "mtime_utc")):
    lines = [",".join(header)]
    for relpath, sha in rows:
        lines.append(f"{relpath},123,{sha},2026-08-06T00:00:00+00:00")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_manifest_sha256(path: Path, rows):
    lines = [f"{sha}  {relpath}" for relpath, sha in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")


@pytest.fixture
def manifest_pair(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    rows = [("dir/a.xlsx", VALID_HASH_A), ("dir/b.xlsx", VALID_HASH_B)]
    _write_manifest_csv(csv_path, rows)
    _write_manifest_sha256(sha_path, rows)
    return csv_path, sha_path, rows


def test_validate_manifest_pair_happy_path(manifest_pair):
    csv_path, sha_path, rows = manifest_pair
    result = b.validate_manifest_pair(csv_path, sha_path)
    assert result == {relpath: sha for relpath, sha in rows}


def test_validate_manifest_pair_missing_in_sha256(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A), ("dir/b.xlsx", VALID_HASH_B)])
    _write_manifest_sha256(sha_path, [("dir/a.xlsx", VALID_HASH_A)])
    with pytest.raises(ValueError, match="relpath 集合不一致"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_extra_in_sha256(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A)])
    _write_manifest_sha256(
        sha_path, [("dir/a.xlsx", VALID_HASH_A), ("dir/extra.xlsx", VALID_HASH_B)]
    )
    with pytest.raises(ValueError, match="relpath 集合不一致"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_duplicate_relpath_in_csv(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(
        csv_path, [("dir/a.xlsx", VALID_HASH_A), ("dir/a.xlsx", VALID_HASH_B)]
    )
    _write_manifest_sha256(sha_path, [("dir/a.xlsx", VALID_HASH_A)])
    with pytest.raises(ValueError, match="relpath 重複"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_duplicate_relpath_in_sha256(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A)])
    _write_manifest_sha256(
        sha_path, [("dir/a.xlsx", VALID_HASH_A), ("dir/a.xlsx", VALID_HASH_A)]
    )
    with pytest.raises(ValueError, match="relpath 重複"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_malformed_csv_header(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A)], header=("relpath", "sha256"))
    _write_manifest_sha256(sha_path, [("dir/a.xlsx", VALID_HASH_A)])
    with pytest.raises(ValueError, match="標頭不符"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_malformed_csv_hash(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", "not-a-valid-hash")])
    _write_manifest_sha256(sha_path, [("dir/a.xlsx", VALID_HASH_A)])
    with pytest.raises(ValueError, match="sha256 格式不合法"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_malformed_sha256_line(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A)])
    sha_path.write_text("this is not a valid sha256sum line\n", encoding="utf-8")
    with pytest.raises(ValueError, match="格式不合法"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_uppercase_hash_in_sha256_rejected(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A)])
    sha_path.write_text(f"{VALID_HASH_A.upper()}  dir/a.xlsx\n", encoding="utf-8")
    with pytest.raises(ValueError, match="小寫"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_hash_mismatch(tmp_path):
    csv_path = tmp_path / "manifest.csv"
    sha_path = tmp_path / "manifest.sha256"
    _write_manifest_csv(csv_path, [("dir/a.xlsx", VALID_HASH_A)])
    _write_manifest_sha256(sha_path, [("dir/a.xlsx", VALID_HASH_B)])
    with pytest.raises(ValueError, match="記錄了不同的"):
        b.validate_manifest_pair(csv_path, sha_path)


def test_validate_manifest_pair_does_not_touch_real_manifest(tmp_path, manifest_pair, monkeypatch):
    # 確認這支函式完全不依賴任何模組層級的真實路徑常數——把 cwd 換到一個
    # 空的 tmp_path,一樣能透過注入路徑正常運作。
    monkeypatch.chdir(tmp_path)
    csv_path, sha_path, rows = manifest_pair
    result = b.validate_manifest_pair(csv_path, sha_path)
    assert result == {relpath: sha for relpath, sha in rows}


# ----------------------------------------------------------------------------
# 4. 身分鏈純計算 —— known-answer vectors + 敏感度 + fail-closed
# ----------------------------------------------------------------------------


def test_source_data_identity_known_vector():
    result = b.source_data_identity(VALID_HASH_A, "b" * 64, "c" * 64)
    assert result == "3f10a42558f1dd4e149475fd806d082300c70a005a9942aca5fbbe4f5063fb7a"
    assert len(result) == 64


def test_build_implementation_identity_known_vector():
    result = b.build_implementation_identity(
        "d" * 64, "e" * 64, "f" * 64, "1" * 64, "2" * 64, "deadbeef" * 5
    )
    assert result == "11d3e7637b494baf4cb5a51654efc5f0772163e6ff50f259b7056b81d8bb8014"
    assert len(result) == 64


def test_snapshot_id_v1_known_vector():
    sdi = b.source_data_identity(VALID_HASH_A, "b" * 64, "c" * 64)
    bii = b.build_implementation_identity(
        "d" * 64, "e" * 64, "f" * 64, "1" * 64, "2" * 64, "deadbeef" * 5
    )
    result = b.snapshot_id_v1(sdi, bii)
    assert result == "6663401439cd267223dba84e600343e9d82e01bc3ecc72e640469a65e50156e1"
    assert len(result) == 64


def test_marker_environment_identity_v1_known_vector():
    result = b.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    assert result == "59fb7173dbf9d0bfc200d96dccf2cd56002f55f005c0443d66a30b5bf32e0fbb"
    assert len(result) == 64


def test_runtime_environment_identity_v1_known_vector():
    marker_id = b.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    source = b.build_runtime_environment_source(
        python_implementation="CPython",
        python_version_full="3.12.10 (main, ...)",
        os_system="Windows",
        os_release="11",
        machine_arch="AMD64",
        pandas_version="2.2.2",
        numpy_version="1.26.4",
        pyarrow_version="16.1.0",
        openpyxl_version="3.1.2",
        dependency_lock_identity="1" * 64,
        marker_environment_identity_v1_value=marker_id,
    )
    result = b.runtime_environment_identity_v1(source)
    assert result == "af6bd5c69b9983b9c0bd57ca06454b976056d3ee78774dcc81f5fd09908751b3"
    assert len(result) == 64


def test_source_data_identity_canonicalization_matches_frozen_string_formula():
    # §C.1「組合公式」是逐位元組固定的 f-string,不是 JSON——直接比對字面
    # payload 的雜湊,避免實作偷偷換成別的序列化規則還測不出來。
    expected_payload = (
        f"manifest_sha256={VALID_HASH_A}\n"
        f"manifest_sha256_file_sha256={VALID_HASH_B}\n"
        f"supplement_receipt_sha256={VALID_HASH_C}"
    ).encode("utf-8")
    import hashlib

    expected = hashlib.sha256(expected_payload).hexdigest()
    assert b.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C) == expected


@pytest.mark.parametrize("field_index", [0, 1, 2])
def test_source_data_identity_one_byte_change_alters_identity(field_index):
    baseline = [VALID_HASH_A, VALID_HASH_B, VALID_HASH_C]
    mutated = list(baseline)
    mutated[field_index] = "a" * 63 + "9"  # one hex character changed, still 64 lowercase hex
    assert b.source_data_identity(*baseline) != b.source_data_identity(*mutated)


def test_source_data_identity_field_omission_raises():
    with pytest.raises(TypeError):
        b.source_data_identity(VALID_HASH_A, VALID_HASH_B)  # missing supplement_identity


@pytest.mark.parametrize(
    "bad_value",
    [None, "", "not-hex", "a" * 63, "a" * 65, "A" * 64, "g" * 64],
)
def test_source_data_identity_rejects_malformed_fields(bad_value):
    with pytest.raises((ValueError, TypeError)):
        b.source_data_identity(bad_value, VALID_HASH_B, VALID_HASH_C)


def test_build_implementation_identity_field_substitution_changes_identity():
    baseline = b.build_implementation_identity(
        "d" * 64, "e" * 64, "f" * 64, "1" * 64, "2" * 64, "deadbeef" * 5
    )
    substituted = b.build_implementation_identity(
        "d" * 63 + "9", "e" * 64, "f" * 64, "1" * 64, "2" * 64, "deadbeef" * 5
    )
    assert baseline != substituted


def test_build_implementation_identity_rejects_wrong_candidate_schema_version():
    with pytest.raises(ValueError, match="candidate_schema_version"):
        b.build_implementation_identity(
            "d" * 64,
            "e" * 64,
            "f" * 64,
            "1" * 64,
            "2" * 64,
            "deadbeef" * 5,
            candidate_schema_version="some_other_schema_v2",
        )


def test_build_implementation_identity_rejects_empty_preregistration_commit():
    with pytest.raises(ValueError):
        b.build_implementation_identity(
            "d" * 64, "e" * 64, "f" * 64, "1" * 64, "2" * 64, ""
        )


def test_snapshot_id_v1_field_substitution_changes_identity():
    sdi = b.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C)
    bii = b.build_implementation_identity(
        "d" * 64, "e" * 64, "f" * 64, "1" * 64, "2" * 64, "deadbeef" * 5
    )
    baseline = b.snapshot_id_v1(sdi, bii)
    substituted = b.snapshot_id_v1(sdi, "0" * 64)
    assert baseline != substituted


def test_snapshot_id_v1_full_64_char_lowercase_output():
    sdi = b.source_data_identity(VALID_HASH_A, VALID_HASH_B, VALID_HASH_C)
    bii = b.build_implementation_identity(
        "d" * 64, "e" * 64, "f" * 64, "1" * 64, "2" * 64, "deadbeef" * 5
    )
    result = b.snapshot_id_v1(sdi, bii)
    assert len(result) == 64
    assert result == result.lower()
    assert all(c in "0123456789abcdef" for c in result)


# ----------------------------------------------------------------------------
# 5. marker_environment_identity_v1 —— 鍵集合/型別 fail-closed + 插入順序無關
# ----------------------------------------------------------------------------


def test_marker_environment_identity_v1_insertion_order_independent():
    reordered = dict(reversed(list(VALID_MARKER_ENVIRONMENT.items())))
    assert list(reordered.keys()) != list(VALID_MARKER_ENVIRONMENT.keys())
    assert b.marker_environment_identity_v1(
        VALID_MARKER_ENVIRONMENT
    ) == b.marker_environment_identity_v1(reordered)


def test_marker_environment_identity_v1_missing_key_fails_closed():
    incomplete = dict(VALID_MARKER_ENVIRONMENT)
    del incomplete["sys_platform"]
    with pytest.raises(ValueError, match="鍵集合"):
        b.marker_environment_identity_v1(incomplete)


def test_marker_environment_identity_v1_extra_key_fails_closed():
    extra = dict(VALID_MARKER_ENVIRONMENT)
    extra["unexpected_field"] = "x"
    with pytest.raises(ValueError, match="鍵集合"):
        b.marker_environment_identity_v1(extra)


def test_marker_environment_identity_v1_non_string_value_fails_closed():
    bad = dict(VALID_MARKER_ENVIRONMENT)
    bad["python_version"] = 3.12
    with pytest.raises(ValueError, match="必須是字串"):
        b.marker_environment_identity_v1(bad)


def test_marker_environment_identity_v1_one_value_change_alters_identity():
    changed = dict(VALID_MARKER_ENVIRONMENT)
    changed["python_version"] = "3.11"
    assert b.marker_environment_identity_v1(changed) != b.marker_environment_identity_v1(
        VALID_MARKER_ENVIRONMENT
    )


# ----------------------------------------------------------------------------
# 6. runtime_environment_identity_v1 —— 長度/schema tag/None fail-closed
# ----------------------------------------------------------------------------


def _valid_runtime_source():
    marker_id = b.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    return b.build_runtime_environment_source(
        python_implementation="CPython",
        python_version_full="3.12.10",
        os_system="Windows",
        os_release="11",
        machine_arch="AMD64",
        pandas_version="2.2.2",
        numpy_version="1.26.4",
        pyarrow_version="16.1.0",
        openpyxl_version="3.1.2",
        dependency_lock_identity="1" * 64,
        marker_environment_identity_v1_value=marker_id,
    )


def test_runtime_environment_identity_v1_wrong_length_fails_closed():
    source = _valid_runtime_source()[:-1]
    with pytest.raises(ValueError, match="14 個元素"):
        b.runtime_environment_identity_v1(source)


def test_runtime_environment_identity_v1_wrong_schema_tag_fails_closed():
    source = _valid_runtime_source()
    source[0] = "wrong_tag"
    with pytest.raises(ValueError, match="schema tag"):
        b.runtime_environment_identity_v1(source)


def test_runtime_environment_identity_v1_none_field_fails_closed():
    source = _valid_runtime_source()
    source[5] = None
    with pytest.raises(ValueError, match="None"):
        b.runtime_environment_identity_v1(source)


def test_runtime_environment_identity_v1_one_field_substitution_changes_identity():
    baseline = _valid_runtime_source()
    substituted = _valid_runtime_source()
    substituted[6] = "9.9.9"  # pandas_version changed
    assert b.runtime_environment_identity_v1(
        baseline
    ) != b.runtime_environment_identity_v1(substituted)


def test_build_runtime_environment_source_rejects_malformed_dependency_lock_identity():
    marker_id = b.marker_environment_identity_v1(VALID_MARKER_ENVIRONMENT)
    with pytest.raises(ValueError):
        b.build_runtime_environment_source(
            python_implementation="CPython",
            python_version_full="3.12.10",
            os_system="Windows",
            os_release="11",
            machine_arch="AMD64",
            pandas_version="2.2.2",
            numpy_version="1.26.4",
            pyarrow_version="16.1.0",
            openpyxl_version="3.1.2",
            dependency_lock_identity="not-a-hash",
            marker_environment_identity_v1_value=marker_id,
        )


# ----------------------------------------------------------------------------
# 7. environment_creation_identity —— self-field exclusion
# ----------------------------------------------------------------------------


def _default_environment_creation_kwargs():
    # lock_selected_inventory/installed_inventory 的 sha256 是「canonical
    # 序列化後的雜湊」(§C.5),不是任意字面值——用實際的 canonical_json_bytes
    # 算出來,這樣預設 fixture 才是一份真正自洽、能通過 validator 的 receipt。
    lock_selected_inventory = [["pandas", "2.2.2"]]
    installed_inventory = [["pandas", "2.2.2"]]
    return dict(
        run_id="run-0001",
        preregistration_commit="deadbeef" * 5,
        lock_path="requirements-v2-data-build.lock",
        lock_sha256="1" * 64,
        marker_environment_v1=VALID_MARKER_ENVIRONMENT,
        installer_identity="pip==24.0",
        bootstrap_tool_inventory=[["pip", "24.0"], ["setuptools", "70.0"], ["wheel", "0.43.0"]],
        install_command=["pip", "install", "--require-hashes", "-r", "requirements-v2-data-build.lock"],
        start_timestamp_utc="2026-08-08T00:00:00+00:00",
        end_timestamp_utc="2026-08-08T00:05:00+00:00",
        exit_code=0,
        installer_report_artifact_hashes=None,
        stdout_log_sha256="2" * 64,
        stderr_log_sha256="3" * 64,
        lock_selected_inventory=lock_selected_inventory,
        lock_selected_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes(lock_selected_inventory, sort_keys=False)
        ),
        installed_inventory=installed_inventory,
        installed_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes(installed_inventory, sort_keys=False)
        ),
        equality_result={"equal": True, "discrepancies": []},
    )


def _build_valid_environment_creation_receipt(**overrides):
    kwargs = _default_environment_creation_kwargs()
    kwargs.update(overrides)
    return b.build_environment_creation_receipt(**kwargs)


def _mismatched_inventory_receipt_kwargs():
    # pandas 版本不同——lock 選了 2.2.2,實際觀測到 2.3.0,是「真的對不上」
    # 的一組 inventory;equality_result 用真正的 reconcile() 算出來,不是
    # 任意編造的字串(Phase A3c blocking-fix 之後,build_environment_
    # creation_receipt 要求 equality_result 必須跟獨立重算的 reconcile
    # 結果一致,即使記錄的是「失敗」也必須忠實)。
    lock_selected_inventory = [["pandas", "2.2.2"]]
    installed_inventory = [["pandas", "2.3.0"]]
    equality_result = b.reconcile_lock_selected_vs_installed_inventory(
        lock_selected_inventory, installed_inventory
    )
    return dict(
        lock_selected_inventory=lock_selected_inventory,
        lock_selected_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes(lock_selected_inventory, sort_keys=False)
        ),
        installed_inventory=installed_inventory,
        installed_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes(installed_inventory, sort_keys=False)
        ),
        equality_result=equality_result,
    )


def test_build_environment_creation_receipt_round_trips_through_validator():
    receipt = _build_valid_environment_creation_receipt()
    assert set(receipt) == set(b.ENVIRONMENT_CREATION_RECEIPT_FIELDS) | {
        "environment_creation_identity"
    }
    b.validate_environment_creation_receipt(receipt)  # must not raise


def test_environment_creation_identity_excludes_self_field():
    receipt = _build_valid_environment_creation_receipt()
    correct_identity = receipt["environment_creation_identity"]

    tampered = dict(receipt)
    tampered["environment_creation_identity"] = "0" * 64  # deliberately wrong stored value

    # 純函式重算時本來就會先排除自身欄位,所以不管 tampered 裡放什麼值,
    # 重算結果都跟原本一致——這就是「排除自身欄位」的直接證據。
    assert b.environment_creation_identity(tampered) == correct_identity
    assert b.environment_creation_identity(receipt) == correct_identity

    # 但 validator 比對的是「recompute vs 目前存的值」,tampered 版本存的
    # 值本身是錯的,所以驗證必須失敗。
    with pytest.raises(ValueError, match="environment_creation_identity"):
        b.validate_environment_creation_receipt(tampered)


def test_environment_creation_identity_one_field_change_alters_identity():
    receipt = _build_valid_environment_creation_receipt()
    mutated_inputs = dict(receipt)
    del mutated_inputs["environment_creation_identity"]
    mutated_inputs["exit_code"] = 1
    assert b.environment_creation_identity(mutated_inputs) != receipt["environment_creation_identity"]


def test_validate_environment_creation_receipt_rejects_missing_field():
    receipt = _build_valid_environment_creation_receipt()
    del receipt["exit_code"]
    with pytest.raises(ValueError, match="欄位集合不符"):
        b.validate_environment_creation_receipt(receipt)


def test_validate_environment_creation_receipt_rejects_wrong_schema_tag():
    receipt = _build_valid_environment_creation_receipt()
    receipt["schema"] = "some_other_schema"
    with pytest.raises(ValueError, match="schema"):
        b.validate_environment_creation_receipt(receipt)


def test_validate_environment_creation_receipt_rejects_marker_identity_mismatch():
    receipt = _build_valid_environment_creation_receipt()
    receipt["marker_environment_identity_v1"] = "0" * 64
    with pytest.raises(ValueError, match="marker_environment_identity_v1"):
        b.validate_environment_creation_receipt(receipt)


def test_build_environment_creation_receipt_rejects_malformed_lock_sha256():
    with pytest.raises(ValueError):
        _build_valid_environment_creation_receipt(lock_sha256="not-a-hash")


# ---- Codex review (Phase A2a narrow fix): §C.5 fail-closed receipt gate ----
#
# 分兩層測:(a) 型別/shape 錯誤——builder 就要擋(malformed,不管成敗狀態
# 都不該存在);(b) 型別正確但語意上代表「這次環境建立失敗/不合格」——
# builder 允許組出來當診斷證據,但 validate_environment_creation_receipt()
# (§C.5「繼續往下解析候選資料之前」的 gate)必須擋下來。


def test_build_environment_creation_receipt_allows_recording_a_failed_exit_code():
    # exit_code=1 型別正確(是 int),代表「環境建立失敗」的合法診斷值——
    # builder 不擋這個,是 gate 的職責。
    receipt = _build_valid_environment_creation_receipt(exit_code=1)
    assert receipt["exit_code"] == 1


def test_validate_environment_creation_receipt_rejects_nonzero_exit_code():
    receipt = _build_valid_environment_creation_receipt(exit_code=1)
    with pytest.raises(ValueError, match="exit_code"):
        b.validate_environment_creation_receipt(receipt)


def test_build_environment_creation_receipt_rejects_non_bool_equal_string():
    with pytest.raises(ValueError, match="equality_result"):
        _build_valid_environment_creation_receipt(
            equality_result={"equal": "yes", "discrepancies": []}
        )


def test_build_environment_creation_receipt_rejects_non_bool_equal_int():
    # isinstance(1, bool) is False,但 1 是 truthy——這正是 Codex 要擋的
    # 「truthy 數字冒充布林值」個案。
    with pytest.raises(ValueError, match="equality_result"):
        _build_valid_environment_creation_receipt(
            equality_result={"equal": 1, "discrepancies": []}
        )


def test_build_environment_creation_receipt_rejects_equality_result_missing_discrepancies():
    with pytest.raises(ValueError, match="equality_result"):
        _build_valid_environment_creation_receipt(equality_result={"equal": True})


def test_build_environment_creation_receipt_rejects_malformed_discrepancies_type():
    with pytest.raises(ValueError, match="discrepancies"):
        _build_valid_environment_creation_receipt(
            equality_result={"equal": True, "discrepancies": "not-a-list"}
        )


def test_build_environment_creation_receipt_allows_recording_a_genuine_mismatch():
    # equal=False 型別正確,且必須忠實反映兩份 inventory 真的對不上——
    # builder 允許組出這種診斷 receipt,但(Phase A3c blocking-fix)
    # equality_result 必須是從 lock_selected_inventory/installed_inventory
    # 獨立重算 reconcile 的結果,不是任意編造的 False + 不相關字串。
    receipt = _build_valid_environment_creation_receipt(
        **_mismatched_inventory_receipt_kwargs()
    )
    assert receipt["equality_result"]["equal"] is False


def test_build_environment_creation_receipt_rejects_forged_equal_false_not_matching_inventories():
    # Codex review 的核心修正之一:equal=False 型別正確,但
    # discrepancies 的內容(甚至不是合法的 discrepancy shape)跟實際
    # inventory 沒有任何關係——這種不忠實的證據必須在 builder 這一關就被
    # 擋下來,不能留到 validate 才發現。
    with pytest.raises(ValueError, match="discrepancies"):
        _build_valid_environment_creation_receipt(
            equality_result={
                "equal": False,
                "discrepancies": ["pandas version mismatch"],
            }
        )


def test_validate_environment_creation_receipt_rejects_equal_false():
    # §C.5 fail-closed gate:即使 equal=False 忠實反映了真正的 inventory
    # 差異(用 reconcile() 算出來的,不是編造的),仍然不能繼續往下解析
    # 候選資料——「equal 必須是 True 才能往下走」是獨立於「證據是否忠實」
    # 的另一道 gate。
    receipt = _build_valid_environment_creation_receipt(
        **_mismatched_inventory_receipt_kwargs()
    )
    with pytest.raises(ValueError, match="equality_result"):
        b.validate_environment_creation_receipt(receipt)


def test_build_environment_creation_receipt_allows_install_command_missing_hash_flag():
    # install_command 型別正確(list of str),只是剛好沒有 --require-hashes
    # ——builder 不擋這個,是 gate 的職責(§C.5 fail-closed 條件明講「繼續
    # 往下解析候選資料之前」才擋,不是 receipt 本身不能被組出來)。
    receipt = _build_valid_environment_creation_receipt(
        install_command=["pip", "install", "-r", "requirements-v2-data-build.lock"]
    )
    assert "--require-hashes" not in receipt["install_command"]


def test_validate_environment_creation_receipt_rejects_missing_hash_verification_evidence():
    receipt = _build_valid_environment_creation_receipt(
        install_command=["pip", "install", "-r", "requirements-v2-data-build.lock"]
    )
    with pytest.raises(ValueError, match="install_command"):
        b.validate_environment_creation_receipt(receipt)


def test_build_environment_creation_receipt_rejects_wrong_type_artifact_hashes():
    # Codex 的 probe 個案:一個裸字串完全不是 §C.5 允許的兩種形狀
    # (JSON null 或 [[package, sha256], ...] 陣列)。
    with pytest.raises(ValueError, match="installer_report_artifact_hashes"):
        _build_valid_environment_creation_receipt(installer_report_artifact_hashes="bad")


def test_build_environment_creation_receipt_allows_null_artifact_hashes():
    receipt = _build_valid_environment_creation_receipt(installer_report_artifact_hashes=None)
    assert receipt["installer_report_artifact_hashes"] is None


def test_build_environment_creation_receipt_allows_valid_artifact_hashes_list():
    receipt = _build_valid_environment_creation_receipt(
        installer_report_artifact_hashes=[["pandas", "5" * 64]]
    )
    assert receipt["installer_report_artifact_hashes"] == [["pandas", "5" * 64]]


def test_build_environment_creation_receipt_rejects_artifact_hashes_with_non_hex_hash():
    with pytest.raises(ValueError, match="installer_report_artifact_hashes"):
        _build_valid_environment_creation_receipt(
            installer_report_artifact_hashes=[["pandas", "not-a-hash"]]
        )


@pytest.mark.parametrize(
    "field",
    ["bootstrap_tool_inventory", "lock_selected_inventory", "installed_inventory"],
)
def test_build_environment_creation_receipt_rejects_flat_string_inventory(field):
    # 扁平字串清單(例如 ["pip"])不是凍結的 [[name, version], ...] pair 形狀。
    overrides = {field: ["pip", "setuptools"]}
    if field == "lock_selected_inventory":
        overrides["lock_selected_inventory_sha256"] = b.sha256_hex(
            b.canonical_json_bytes(["pip", "setuptools"], sort_keys=False)
        )
    if field == "installed_inventory":
        overrides["installed_inventory_sha256"] = b.sha256_hex(
            b.canonical_json_bytes(["pip", "setuptools"], sort_keys=False)
        )
    with pytest.raises(ValueError, match=field):
        _build_valid_environment_creation_receipt(**overrides)


def test_build_environment_creation_receipt_rejects_inventory_sha256_mismatch():
    with pytest.raises(ValueError, match="lock_selected_inventory_sha256"):
        _build_valid_environment_creation_receipt(
            lock_selected_inventory=[["pandas", "2.2.2"]],
            lock_selected_inventory_sha256="9" * 64,  # deliberately wrong
        )


def test_validate_environment_creation_receipt_rejects_hand_crafted_inventory_sha256_mismatch():
    # 繞過 builder,直接手造一份型別正確但 inventory/hash 不自洽的 receipt,
    # 確認 validator 自己也會重算、抓到不一致(不是只信 builder 曾經算對)。
    receipt = _build_valid_environment_creation_receipt()
    tampered = dict(receipt)
    tampered["installed_inventory"] = [["numpy", "1.26.4"]]  # 內容換了,雜湊沒跟著換
    with pytest.raises(ValueError, match="installed_inventory_sha256"):
        b.validate_environment_creation_receipt(tampered)


# ----------------------------------------------------------------------------
# 8. 頂層身分欄位 receipt builder/validator
# ----------------------------------------------------------------------------


def _valid_top_level_kwargs():
    return dict(
        manifest_identity=VALID_HASH_A,
        manifest_sha256_file_identity=VALID_HASH_B,
        supplement_identity=VALID_HASH_C,
        importer_identity="d" * 64,
        extractor_identity="e" * 64,
        builder_identity="f" * 64,
        dependency_lock_identity="1" * 64,
        runtime_environment_identity_v1_value="2" * 64,
        preregistration_commit="deadbeef" * 5,
    )


def test_build_top_level_identity_fields_round_trips_through_validator():
    fields = b.build_top_level_identity_fields(**_valid_top_level_kwargs())
    assert set(fields) == set(b.TOP_LEVEL_IDENTITY_FIELDS)
    b.validate_top_level_identity_fields(fields)  # must not raise


def test_validate_top_level_identity_fields_rejects_missing_key():
    fields = b.build_top_level_identity_fields(**_valid_top_level_kwargs())
    del fields["snapshot_id_v1"]
    with pytest.raises(ValueError, match="鍵集合不符"):
        b.validate_top_level_identity_fields(fields)


def test_validate_top_level_identity_fields_rejects_extra_key():
    fields = b.build_top_level_identity_fields(**_valid_top_level_kwargs())
    fields["unexpected"] = "x"
    with pytest.raises(ValueError, match="鍵集合不符"):
        b.validate_top_level_identity_fields(fields)


def test_validate_top_level_identity_fields_rejects_substituted_input_without_recompute():
    fields = b.build_top_level_identity_fields(**_valid_top_level_kwargs())
    # 只改動輸入欄位,不重算三層——validator 必須抓到 build_implementation_identity 不再對得上。
    fields["importer_identity"] = "9" * 64
    with pytest.raises(ValueError, match="build_implementation_identity"):
        b.validate_top_level_identity_fields(fields)


def test_validate_top_level_identity_fields_rejects_tampered_snapshot_id():
    fields = b.build_top_level_identity_fields(**_valid_top_level_kwargs())
    fields["snapshot_id_v1"] = "9" * 64  # 三層中間值都沒動,只竄改最終值
    with pytest.raises(ValueError, match="snapshot_id_v1"):
        b.validate_top_level_identity_fields(fields)


def test_build_top_level_identity_fields_field_omission_raises():
    kwargs = _valid_top_level_kwargs()
    del kwargs["supplement_identity"]
    with pytest.raises(TypeError):
        b.build_top_level_identity_fields(**kwargs)


# ----------------------------------------------------------------------------
# 9. guard_candidate_output_dir —— §C.4 path-identity 守衛
# ----------------------------------------------------------------------------


@pytest.fixture
def candidate_base(tmp_path):
    base = tmp_path / "candidate_base"
    base.mkdir()
    return base


def test_guard_accepts_valid_path(candidate_base):
    result = b.guard_candidate_output_dir(candidate_base, VALID_SNAPSHOT_ID, "run-0001")
    assert result == (candidate_base.resolve() / VALID_SNAPSHOT_ID / "run-0001")


@pytest.mark.parametrize(
    "bad_snapshot_id",
    [
        "a" * 63,  # shortened
        "a" * 65,  # too long
        "A" * 64,  # uppercase
        "a" * 63 + "G",  # non-hex character
        "",
        "a" * 12,  # old truncated-prefix convention, explicitly rejected by §C.4 第19輪
    ],
)
def test_guard_rejects_malformed_snapshot_id(candidate_base, bad_snapshot_id):
    with pytest.raises(ValueError, match="64 碼小寫十六進位"):
        b.guard_candidate_output_dir(candidate_base, bad_snapshot_id, "run-0001")


@pytest.mark.parametrize("bad_run_id", ["", ".", "..", "a/b", "a\\b", "../escape"])
def test_guard_rejects_invalid_run_id(candidate_base, bad_run_id):
    with pytest.raises(ValueError, match="run_id"):
        b.guard_candidate_output_dir(candidate_base, VALID_SNAPSHOT_ID, bad_run_id)


def test_guard_rejects_existing_unexpected_path_type(candidate_base):
    snapshot_dir = candidate_base / VALID_SNAPSHOT_ID
    snapshot_dir.mkdir()
    (snapshot_dir / "run-0001").write_text("this is a file, not a directory")
    with pytest.raises(ValueError, match="不是目錄"):
        b.guard_candidate_output_dir(candidate_base, VALID_SNAPSHOT_ID, "run-0001")


def test_guard_allows_sibling_prefix_directory_without_false_positive(tmp_path):
    candidate_base = tmp_path / "candidate"
    candidate_base.mkdir()
    sibling = tmp_path / "candidate_other"
    sibling.mkdir()
    # 字面上 "candidate_other" 是 "candidate" 的字串前綴延伸,但不是子目錄
    # ——guard 必須用真正的路徑語意判斷,不能誤判成重疊。
    result = b.guard_candidate_output_dir(
        candidate_base, VALID_SNAPSHOT_ID, "run-0001", protected_paths=[sibling]
    )
    assert result == candidate_base.resolve() / VALID_SNAPSHOT_ID / "run-0001"


def test_guard_rejects_protected_path_ancestor_overlap(tmp_path):
    # candidate_base 本身不小心被放進受保護路徑的子樹底下。
    protected = tmp_path
    candidate_base = tmp_path / "candidate_base"
    candidate_base.mkdir()
    with pytest.raises(ValueError, match="重疊"):
        b.guard_candidate_output_dir(
            candidate_base, VALID_SNAPSHOT_ID, "run-0001", protected_paths=[protected]
        )


def test_guard_rejects_protected_path_nested_inside_target(candidate_base):
    target = candidate_base / VALID_SNAPSHOT_ID / "run-0001"
    protected_inside_target = target / "inner"
    with pytest.raises(ValueError, match="重疊"):
        b.guard_candidate_output_dir(
            candidate_base,
            VALID_SNAPSHOT_ID,
            "run-0001",
            protected_paths=[protected_inside_target],
        )


def test_guard_rejects_exact_protected_path_equality(candidate_base):
    target = candidate_base.resolve() / VALID_SNAPSHOT_ID / "run-0001"
    with pytest.raises(ValueError, match="重疊"):
        b.guard_candidate_output_dir(
            candidate_base, VALID_SNAPSHOT_ID, "run-0001", protected_paths=[target]
        )


def test_guard_rejects_symlink_escape(tmp_path, candidate_base):
    outside = tmp_path / "outside"
    outside.mkdir()
    snapshot_dir = candidate_base / VALID_SNAPSHOT_ID
    try:
        snapshot_dir.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"這個環境不允許建立 symlink(需要權限/Developer Mode):{exc}")
    with pytest.raises(ValueError, match="symlink"):
        b.guard_candidate_output_dir(candidate_base, VALID_SNAPSHOT_ID, "run-0001")


def test_guard_rejects_missing_candidate_base(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="不存在或不是目錄"):
        b.guard_candidate_output_dir(missing, VALID_SNAPSHOT_ID, "run-0001")


def test_guard_rejects_candidate_base_that_is_a_file(tmp_path):
    not_a_dir = tmp_path / "candidate_base_file"
    not_a_dir.write_text("x")
    with pytest.raises(ValueError, match="不存在或不是目錄"):
        b.guard_candidate_output_dir(not_a_dir, VALID_SNAPSHOT_ID, "run-0001")


def test_guard_does_not_create_any_directory(candidate_base):
    target = b.guard_candidate_output_dir(candidate_base, VALID_SNAPSHOT_ID, "run-0001")
    assert not target.exists()
    assert not (candidate_base / VALID_SNAPSHOT_ID).exists()


# ----------------------------------------------------------------------------
# 10. Phase A2b —— 安全 receipt writer(§C.5 排他建立)
# ----------------------------------------------------------------------------


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run-0001"
    d.mkdir()
    return d


# ---- 10.1 guard_receipt_filename ----


def test_guard_receipt_filename_accepts_valid_name(run_dir):
    result = b.guard_receipt_filename(run_dir, "environment_creation_receipt.json")
    assert result == run_dir.resolve() / "environment_creation_receipt.json"


@pytest.mark.parametrize(
    "bad_filename", ["", ".", "..", "a/b", "a\\b", "../escape.json", "/abs.json"]
)
def test_guard_receipt_filename_rejects_bad_names(run_dir, bad_filename):
    with pytest.raises(ValueError):
        b.guard_receipt_filename(run_dir, bad_filename)


def test_guard_receipt_filename_rejects_missing_run_dir(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="不存在或不是目錄"):
        b.guard_receipt_filename(missing, "x.json")


def test_guard_receipt_filename_rejects_run_dir_that_is_a_file(tmp_path):
    not_a_dir = tmp_path / "run_dir_file"
    not_a_dir.write_text("x")
    with pytest.raises(ValueError, match="不存在或不是目錄"):
        b.guard_receipt_filename(not_a_dir, "x.json")


def test_guard_receipt_filename_rejects_symlink_escape(tmp_path, run_dir):
    outside = tmp_path / "outside"
    outside.mkdir()
    target_name = "escape.json"
    link = run_dir / target_name
    try:
        link.symlink_to(outside / target_name)
    except OSError as exc:
        pytest.skip(f"這個環境不允許建立 symlink(需要權限/Developer Mode):{exc}")
    with pytest.raises(ValueError, match="symlink"):
        b.guard_receipt_filename(run_dir, target_name)


def test_guard_receipt_filename_does_not_create_anything(run_dir):
    result = b.guard_receipt_filename(run_dir, "x.json")
    assert not result.exists()


# ---- 10.2 write_receipt_json_atomic ----


def test_write_receipt_json_atomic_writes_deterministic_bytes_and_returns_matching_sha256(run_dir):
    receipt = {"b": 1, "a": 2}
    path = run_dir / "generic_receipt.json"
    written_path, digest = b.write_receipt_json_atomic(path, receipt)

    expected_bytes = b.canonical_json_bytes(receipt, sort_keys=True)
    assert written_path.read_bytes() == expected_bytes
    assert digest == b.sha256_hex(expected_bytes)
    assert written_path == path.resolve()


def test_write_receipt_json_atomic_is_byte_for_byte_deterministic_across_calls(tmp_path):
    receipt = {"z": [1, 2, 3], "a": "中文"}
    p1 = tmp_path / "r1.json"
    p2 = tmp_path / "r2.json"
    _, digest1 = b.write_receipt_json_atomic(p1, receipt)
    _, digest2 = b.write_receipt_json_atomic(p2, receipt)
    assert digest1 == digest2
    assert p1.read_bytes() == p2.read_bytes()


def test_write_receipt_json_atomic_rejects_existing_file_and_leaves_it_unchanged(run_dir):
    path = run_dir / "receipt.json"
    path.write_text("pre-existing content", encoding="utf-8")

    with pytest.raises(ValueError, match="已存在"):
        b.write_receipt_json_atomic(path, {"a": 1})

    assert path.read_text(encoding="utf-8") == "pre-existing content"


def test_write_receipt_json_atomic_rejects_existing_directory_and_leaves_it_unchanged(run_dir):
    path = run_dir / "receipt_dir"
    path.mkdir()
    (path / "inner.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError):
        b.write_receipt_json_atomic(path, {"a": 1})

    assert path.is_dir()
    assert (path / "inner.txt").read_text(encoding="utf-8") == "keep me"


def test_write_receipt_json_atomic_rejects_missing_parent_directory(tmp_path):
    path = tmp_path / "does_not_exist" / "receipt.json"
    with pytest.raises(ValueError, match="父目錄"):
        b.write_receipt_json_atomic(path, {"a": 1})
    assert not path.exists()


def test_write_receipt_json_atomic_rejects_non_dict_receipt(run_dir):
    with pytest.raises(TypeError):
        b.write_receipt_json_atomic(run_dir / "x.json", ["not", "a", "dict"])
    assert list(run_dir.iterdir()) == []


def test_write_receipt_json_atomic_rejects_non_serializable_payload_and_creates_no_file(run_dir):
    path = run_dir / "receipt.json"
    with pytest.raises(TypeError):
        b.write_receipt_json_atomic(path, {"bad": {1, 2, 3}})  # a set isn't JSON-serializable
    assert not path.exists()


def test_write_receipt_json_atomic_cleans_up_partial_file_on_write_failure(run_dir, monkeypatch):
    import os

    path = run_dir / "receipt.json"

    class ExplodingFileObj:
        def write(self, data):
            raise OSError("simulated disk failure mid-write")

        def flush(self):
            pass

        def fileno(self):
            return 0

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def fake_fdopen(fd, mode):
        os.close(fd)
        return ExplodingFileObj()

    monkeypatch.setattr(os, "fdopen", fake_fdopen)

    with pytest.raises(OSError, match="simulated disk failure"):
        b.write_receipt_json_atomic(path, {"a": 1})

    assert not path.exists()
    assert list(run_dir.iterdir()) == []


# ---- 10.3 write_environment_creation_receipt ----


def test_write_environment_creation_receipt_writes_valid_receipt(run_dir):
    receipt = _build_valid_environment_creation_receipt()
    path = run_dir / "environment_creation_receipt.json"
    written_path, digest = b.write_environment_creation_receipt(path, receipt)
    assert written_path.read_bytes() == b.canonical_json_bytes(receipt, sort_keys=True)
    assert digest == b.sha256_hex(written_path.read_bytes())


@pytest.mark.parametrize(
    "overrides",
    [
        {"exit_code": 1},
        _mismatched_inventory_receipt_kwargs(),
        {"install_command": ["pip", "install", "-r", "requirements-v2-data-build.lock"]},
    ],
)
def test_write_environment_creation_receipt_rejects_gate_failure_before_any_file_appears(run_dir, overrides):
    receipt = _build_valid_environment_creation_receipt(**overrides)
    path = run_dir / "environment_creation_receipt.json"
    with pytest.raises(ValueError):
        b.write_environment_creation_receipt(path, receipt)
    assert not path.exists()
    assert list(run_dir.iterdir()) == []


def test_write_environment_creation_receipt_rejects_malformed_receipt_before_any_file_appears(run_dir):
    receipt = _build_valid_environment_creation_receipt()
    receipt["equality_result"] = {"equal": "yes", "discrepancies": []}
    path = run_dir / "environment_creation_receipt.json"
    with pytest.raises(ValueError):
        b.write_environment_creation_receipt(path, receipt)
    assert not path.exists()


# ---- 10.4 build/validate/write_top_level_build_receipt ----


def _valid_top_level_build_receipt_kwargs():
    kwargs = dict(_valid_top_level_kwargs())
    kwargs.update(
        run_id="run-0001",
        authorized_verifier_identity="verifier@example",
        overall_status="BUILD_COMPLETE_AWAITING_VERIFICATION",
        environment_creation_receipt_path="run-0001/environment_creation_receipt.json",
        environment_creation_receipt_sha256="4" * 64,
        environment_creation_identity_value="5" * 64,
    )
    return kwargs


def test_build_top_level_build_receipt_round_trips_through_validator():
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    assert set(receipt) == set(b.TOP_LEVEL_BUILD_RECEIPT_FIELDS)
    b.validate_top_level_build_receipt(receipt)  # must not raise


def test_build_top_level_build_receipt_does_not_invent_authorized_verifier_identity():
    kwargs = _valid_top_level_build_receipt_kwargs()
    kwargs["authorized_verifier_identity"] = "some-specific-injected-verifier-id"
    receipt = b.build_top_level_build_receipt(**kwargs)
    assert receipt["authorized_verifier_identity"] == "some-specific-injected-verifier-id"


@pytest.mark.parametrize(
    "bad_status", ["BUILD_COMPLETE", "build_complete_awaiting_verification", "", "SUCCESS"]
)
def test_build_top_level_build_receipt_rejects_invalid_overall_status(bad_status):
    kwargs = _valid_top_level_build_receipt_kwargs()
    kwargs["overall_status"] = bad_status
    with pytest.raises(ValueError, match="overall_status"):
        b.build_top_level_build_receipt(**kwargs)


def test_validate_top_level_build_receipt_rejects_missing_key():
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    del receipt["run_id"]
    with pytest.raises(ValueError, match="欄位集合不符"):
        b.validate_top_level_build_receipt(receipt)


def test_validate_top_level_build_receipt_rejects_extra_key():
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    receipt["unexpected"] = "x"
    with pytest.raises(ValueError, match="欄位集合不符"):
        b.validate_top_level_build_receipt(receipt)


def test_validate_top_level_build_receipt_rejects_wrong_schema_tag():
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    receipt["schema"] = "wrong_schema"
    with pytest.raises(ValueError, match="schema"):
        b.validate_top_level_build_receipt(receipt)


def test_validate_top_level_build_receipt_rejects_tampered_identity_subfield():
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    receipt["snapshot_id_v1"] = "9" * 64
    with pytest.raises(ValueError, match="snapshot_id_v1"):
        b.validate_top_level_build_receipt(receipt)


def test_validate_top_level_build_receipt_rejects_malformed_environment_creation_receipt_sha256():
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    receipt["environment_creation_receipt_sha256"] = "not-a-hash"
    with pytest.raises(ValueError):
        b.validate_top_level_build_receipt(receipt)


def test_write_top_level_build_receipt_round_trip(run_dir):
    receipt = b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs())
    path = run_dir / "top_level_build_receipt.json"
    written_path, digest = b.write_top_level_build_receipt(path, receipt)
    assert written_path.read_bytes() == b.canonical_json_bytes(receipt, sort_keys=True)
    assert digest == b.sha256_hex(written_path.read_bytes())


def test_write_top_level_build_receipt_rejects_invalid_status_before_any_file_appears(run_dir):
    kwargs = _valid_top_level_build_receipt_kwargs()
    kwargs["overall_status"] = "NOT_A_REAL_STATUS"
    # 直接構造一個「validator 會抓到但沒有先經過 build_top_level_build_receipt
    # 檢查」的 dict,證明 writer 本身(不是只有 builder)也會 fail-closed。
    receipt = dict(b.build_top_level_build_receipt(**_valid_top_level_build_receipt_kwargs()))
    receipt["overall_status"] = "NOT_A_REAL_STATUS"
    path = run_dir / "top_level_build_receipt.json"
    with pytest.raises(ValueError):
        b.write_top_level_build_receipt(path, receipt)
    assert not path.exists()
    assert list(run_dir.iterdir()) == []


# ---- 10.5 完整合成 round-trip:環境 receipt → 頂層 receipt,獨立雜湊核對 ----


def test_full_synthetic_receipt_round_trip_with_independent_hash_check(run_dir):
    env_receipt = _build_valid_environment_creation_receipt()
    env_path = run_dir / "environment_creation_receipt.json"
    written_env_path, env_sha256 = b.write_environment_creation_receipt(env_path, env_receipt)

    # 獨立第二次計算 SHA-256(不透過 writer 回傳值),核對彼此一致。
    independent_env_sha256 = b.sha256_of_file(written_env_path)
    assert independent_env_sha256 == env_sha256

    top_kwargs = _valid_top_level_build_receipt_kwargs()
    top_kwargs.update(
        environment_creation_receipt_path=str(written_env_path),
        environment_creation_receipt_sha256=env_sha256,
        environment_creation_identity_value=env_receipt["environment_creation_identity"],
    )
    top_receipt = b.build_top_level_build_receipt(**top_kwargs)
    top_path = run_dir / "top_level_build_receipt.json"
    written_top_path, top_sha256 = b.write_top_level_build_receipt(top_path, top_receipt)

    assert b.sha256_of_file(written_top_path) == top_sha256
    # 兩份 receipt 各自都在 run_dir 底下,run_dir 沒有出現任何其他檔案。
    assert set(p.name for p in run_dir.iterdir()) == {
        "environment_creation_receipt.json",
        "top_level_build_receipt.json",
    }


# ---- 10.6 import / subprocess:writer 呼叫本身不碰任何正式路徑 ----


def test_writers_with_synthetic_tmp_paths_touch_only_the_intended_file(tmp_path):
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    isolated_run_dir = tmp_path / "isolated_run"
    isolated_run_dir.mkdir()

    receipt = {"synthetic": True}
    path = isolated_run_dir / "generic_receipt.json"
    written_path, _digest = b.write_receipt_json_atomic(path, receipt)

    assert list(work_dir.iterdir()) == []
    assert list(isolated_run_dir.iterdir()) == [written_path]


def test_import_and_call_writer_in_subprocess_touches_only_synthetic_path(tmp_path):
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate.py"
    target = work_dir / "receipt.json"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('build_v2_candidate', r{str(script_path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"mod.write_receipt_json_atomic(r{str(target)!r}, {{'a': 1}})\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert [p.name for p in work_dir.iterdir()] == ["receipt.json"]


# ----------------------------------------------------------------------------
# 11. Phase A3a —— 凍結 lock 產生策略 + 獨立 synthetic parser
# ----------------------------------------------------------------------------


def _hash_line(hexdigits: str, n: int = 64) -> str:
    return "--hash=sha256:" + (hexdigits * n)[:n]


HASH_A = _hash_line("a")
HASH_B = _hash_line("b")
HASH_C = _hash_line("c")


def _windows_marker_environment(**overrides):
    env = dict.fromkeys(b.MARKER_ENVIRONMENT_KEYS, "unset")
    env.update(
        {
            "sys_platform": "win32",
            "os_name": "nt",
            "platform_system": "Windows",
            "python_version": "3.12",
            "python_full_version": "3.12.10",
        }
    )
    env.update(overrides)
    return env


# ---- 11.1 LOCK_GENERATION_SPEC_V1 ----


def test_lock_generation_spec_records_frozen_user_decisions():
    spec = b.LOCK_GENERATION_SPEC_V1
    assert spec["tool_family"] == "uv pip compile"
    assert spec["generate_hashes_flag"] == "--generate-hashes"
    assert spec["universal_target"] is False
    assert b.INSTALL_REQUIRE_HASHES_FLAG in spec["future_install_command"]
    assert spec["lock_input_filename"] == b.LOCK_INPUT_FILENAME
    assert spec["lock_output_filename"] == b.LOCK_OUTPUT_FILENAME


def test_lock_generation_spec_does_not_reference_installed_uv_version():
    # 任務書明講:不查詢已安裝的 uv 版本,不能把它當凍結值——這裡只擋
    # 「uv 這個工具自己的版本」,不擋 `target_python_version`(那是凍結的
    # *目標* Python 版本,是 Checkpoint 24 的使用者決策,不是本機觀測值)。
    assert "uv_version" not in b.LOCK_GENERATION_SPEC_V1
    assert "installed_uv_version" not in b.LOCK_GENERATION_SPEC_V1
    assert not any("uv" in key and "version" in key for key in b.LOCK_GENERATION_SPEC_V1)


# ---- 11.1b Phase A3b: 精確目標版本/平台凍結(Checkpoint 24) ----


def test_lock_generation_spec_freezes_exact_runtime_identity_literals():
    # Codex review:必須是 `platform.python_implementation()`/`platform.
    # machine()` 在目標機器上實際回傳的精確字面值(`CPython`/`AMD64`),
    # 不是 uv 命令列慣用的正規化小寫標籤(`cpython`/`x86_64`)——後者是
    # 下面測試核對的、獨立的 uv 專屬欄位。
    spec = b.LOCK_GENERATION_SPEC_V1
    assert spec["target_python_implementation"] == "CPython"
    assert spec["target_python_version"] == "3.12.10"
    assert spec["target_os_system"] == "Windows"
    assert spec["target_machine_arch"] == "AMD64"


def test_lock_generation_spec_keeps_uv_target_platform_separate_from_runtime_literals():
    spec = b.LOCK_GENERATION_SPEC_V1
    # uv 的 target-triple 跟 runtime_environment_source 要觀測的字面值是
    # 兩個不同的字串,不能互相替代或混用。
    assert spec["target_uv_python_platform"] == "x86_64-pc-windows-msvc"
    assert spec["target_uv_python_platform"] != spec["target_machine_arch"]
    assert "AMD64" not in spec["target_uv_python_platform"]
    assert "x86_64" not in spec["target_machine_arch"]
    assert "CPython" not in spec["target_uv_python_platform"]


def test_lock_generation_spec_universal_target_stays_false_with_exact_target():
    assert b.LOCK_GENERATION_SPEC_V1["universal_target"] is False
    assert "--universal" not in b.LOCK_GENERATION_SPEC_V1["future_uv_compile_target_args"]
    assert "--universal" not in b.LOCK_GENERATION_SPEC_V1["future_install_command"]


def test_lock_generation_spec_target_args_carry_generate_hashes_as_inert_data():
    args = b.LOCK_GENERATION_SPEC_V1["future_uv_compile_target_args"]
    assert isinstance(args, tuple)
    assert all(isinstance(a, str) for a in args)
    assert "--generate-hashes" in args
    assert "--python-version" in args
    assert args[args.index("--python-version") + 1] == "3.12.10"
    assert "--python-platform" in args


def test_lock_generation_spec_target_python_version_is_resolver_target_not_python_version_full():
    # 第二輪 Codex review 的核心修正:`target_python_version` 是凍結的
    # uv/resolver 版本目標(§C.1 前置檢查要核對的三元組),**不是** §C.1
    # `runtime_environment_source.python_version_full` 那個欄位本身——
    # 後者依既有凍結定義是完整觀測到的 `sys.version` 字串,這個 spec
    # 常數不應該被誤當成、也不能直接塞進那個欄位。
    spec = b.LOCK_GENERATION_SPEC_V1
    assert spec["target_python_version"] == "3.12.10"
    # `python_version_full` 的既有凍結定義要求「完整 sys.version 字串」
    # ——一個只有三段版本號的字串本身就不符合那個格式,證明兩者不是同一
    # 語意的值,不能互相替代。
    assert "(" not in spec["target_python_version"]
    assert "[" not in spec["target_python_version"]


def test_lock_generation_spec_future_install_command_still_carries_require_hashes():
    assert b.INSTALL_REQUIRE_HASHES_FLAG in b.LOCK_GENERATION_SPEC_V1["future_install_command"]


def test_lock_generation_spec_target_args_are_never_executed_by_importing_module(tmp_path):
    # spec 常數只是 tuple[str, ...] 資料——import 這個模組本身不能因為
    # 這些新欄位而多出任何檔案系統/子行程副作用。
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate.py"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('build_v2_candidate', r{str(script_path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "assert mod.LOCK_GENERATION_SPEC_V1['target_python_version'] == '3.12.10'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert list(work_dir.iterdir()) == []


def test_python_3_14_6_is_not_the_frozen_target():
    assert b.LOCK_GENERATION_SPEC_V1["target_python_version"] != "3.14.6"


# 完整、寫實的 `sys.version` 字串(含編譯器/位元資訊),不是裸版本號——
# 對應 §C.1 對 `python_version_full` 的既有凍結定義。兩個字串描述的都是
# CPython 3.12.10,只是編譯器/建置細節不同(模擬「同一個版本號,但不同
# 一次實際 build/observe」的情境)。
FULL_SYS_VERSION_312_A = (
    '3.12.10 (tags/v3.12.10:0181aa3, Apr  8 2025, 12:53:16) '
    '[MSC v.1942 64 bit (AMD64)]'
)
FULL_SYS_VERSION_312_B = (
    '3.12.10 (tags/v3.12.10:0181aa3, Apr  8 2025, 09:10:02) '
    '[MSC v.1941 64 bit (AMD64)]'
)
FULL_SYS_VERSION_314 = (
    '3.14.6 (tags/v3.14.6:abcdef0, Jul  1 2026, 08:00:00) '
    '[MSC v.1944 64 bit (AMD64)]'
)


def _runtime_source_base_kwargs():
    return dict(
        python_implementation="CPython",
        os_system="Windows",
        os_release="11",
        machine_arch="AMD64",
        pandas_version="2.2.2",
        numpy_version="1.26.4",
        pyarrow_version="16.1.0",
        openpyxl_version="3.1.5",
        dependency_lock_identity="1" * 64,
        marker_environment_identity_v1_value="2" * 64,
    )


def test_complete_injected_sys_version_string_is_preserved_in_runtime_environment_source():
    # `python_version_full` 必須原樣保留注入的完整 sys.version 字串,不
    # 被截斷、不被改寫成短版本號。
    source = b.build_runtime_environment_source(
        python_version_full=FULL_SYS_VERSION_312_A, **_runtime_source_base_kwargs()
    )
    idx = b.RUNTIME_ENVIRONMENT_SOURCE_FIELDS.index("python_version_full")
    assert source[idx] == FULL_SYS_VERSION_312_A
    assert "MSC v.1942" in source[idx]


def test_two_different_complete_sys_version_strings_for_same_3_12_10_produce_different_identity():
    # Codex review 的核心要求:即使兩次觀測都同樣是 CPython 3.12.10,只要
    # 完整 sys.version 字串不同位元組(編譯器/建置時間不同),
    # runtime_environment_identity_v1 依然必須不同——不能因為「版本號三段
    # 式相同」就被當成同一個身分。
    kwargs = _runtime_source_base_kwargs()
    source_a = b.build_runtime_environment_source(
        python_version_full=FULL_SYS_VERSION_312_A, **kwargs
    )
    source_b = b.build_runtime_environment_source(
        python_version_full=FULL_SYS_VERSION_312_B, **kwargs
    )
    identity_a = b.runtime_environment_identity_v1(source_a)
    identity_b = b.runtime_environment_identity_v1(source_b)
    assert identity_a != identity_b


def test_changing_injected_python_full_version_changes_runtime_environment_identity():
    # 3.12.10 vs 3.14.6(完整 sys.version 字串)必須產生不同的
    # runtime_environment_identity_v1——證明「換版本」永遠是不同身分,不會
    # 被當成同一個基準的可互換替代品(§C.1 既有身分公式,這裡沒有改)。
    base_kwargs = _runtime_source_base_kwargs()
    source_312 = b.build_runtime_environment_source(
        python_version_full=FULL_SYS_VERSION_312_A, **base_kwargs
    )
    source_314 = b.build_runtime_environment_source(
        python_version_full=FULL_SYS_VERSION_314, **base_kwargs
    )
    identity_312 = b.runtime_environment_identity_v1(source_312)
    identity_314 = b.runtime_environment_identity_v1(source_314)
    assert identity_312 != identity_314


def test_3_14_6_cannot_be_substituted_for_3_12_10_in_the_frozen_spec():
    # spec 常數本身就是「Checkpoint 24 凍結的目標」,不是可以被呼叫端隨意
    # 覆寫、拿 3.14.6 冒充成同一個基準的東西——這裡直接核對常數值,證明
    # 沒有任何程式碼路徑把兩者當成互換。
    spec = b.LOCK_GENERATION_SPEC_V1
    assert spec["target_python_version"] == "3.12.10"
    assert "3.14" not in spec["target_python_version"]
    assert "3.14.6" not in spec["future_uv_compile_target_args"]


# ---- 11.2 normalize_package_name (PEP 503) ----


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Pandas", "pandas"),
        ("py_arrow", "py-arrow"),
        ("Foo.Bar", "foo-bar"),
        ("foo--bar", "foo-bar"),
        ("foo___bar", "foo-bar"),
        ("A.B_C-D", "a-b-c-d"),
    ],
)
def test_normalize_package_name_pep503(raw, expected):
    assert b.normalize_package_name(raw) == expected


def test_normalize_package_name_rejects_empty():
    with pytest.raises(ValueError):
        b.normalize_package_name("")


# ---- 11.3 parse_synthetic_lock_text —— happy paths ----


def test_parse_synthetic_lock_text_unconditional_dependency():
    text = f"numpy==1.26.4 \\\n    {HASH_A}\n"
    parsed = b.parse_synthetic_lock_text(text)
    assert parsed["schema"] == b.SYNTHETIC_LOCK_PARSE_SCHEMA_TAG
    assert len(parsed["records"]) == 1
    record = parsed["records"][0]
    assert record["normalized_name"] == "numpy"
    assert record["version"] == "1.26.4"
    assert record["marker_raw"] is None
    assert record["hashes"] == ("a" * 64,)


def test_parse_synthetic_lock_text_hash_alternatives_preserved():
    text = f"pandas==2.2.2 \\\n    {HASH_A} \\\n    {HASH_B}\n"
    parsed = b.parse_synthetic_lock_text(text)
    record = parsed["records"][0]
    assert set(record["hashes"]) == {"a" * 64, "b" * 64}


def test_parse_synthetic_lock_text_preserves_marker_without_evaluating():
    text = f'pandas==2.2.2 ; sys_platform == "win32" \\\n    {HASH_A}\n'
    parsed = b.parse_synthetic_lock_text(text)
    record = parsed["records"][0]
    assert record["marker_raw"] == 'sys_platform == "win32"'


def test_parse_synthetic_lock_text_preserves_full_pep508_marker_including_or_and_parens():
    # 解析階段只保留原始文字、驗證語法合不合法,不求值——所以 or/括號這種
    # 完整 PEP 508 語法在這裡本來就該被接受(不是 Codex review 前那個手刻
    # 子集才會拒絕的東西)。
    marker_text = 'python_version < "3.13" or (sys_platform == "win32" and os_name == "nt")'
    text = f"pandas==2.2.2 ; {marker_text} \\\n    {HASH_A}\n"
    parsed = b.parse_synthetic_lock_text(text)
    assert parsed["records"][0]["marker_raw"] == marker_text


def test_parse_synthetic_lock_text_normalizes_name_for_records():
    text = f"Py_Arrow==14.0.1 \\\n    {HASH_A}\n"
    parsed = b.parse_synthetic_lock_text(text)
    assert parsed["records"][0]["normalized_name"] == "py-arrow"
    assert parsed["records"][0]["raw_name"] == "Py_Arrow"


def test_parse_synthetic_lock_text_is_deterministic_and_returns_canonical_sha256():
    text = f"numpy==1.26.4 \\\n    {HASH_A}\npandas==2.2.2 \\\n    {HASH_B}\n"
    parsed_1 = b.parse_synthetic_lock_text(text)
    parsed_2 = b.parse_synthetic_lock_text(text)
    assert parsed_1["canonical_sha256"] == parsed_2["canonical_sha256"]


def test_parse_synthetic_lock_text_one_byte_change_alters_canonical_sha256():
    text_a = f"numpy==1.26.4 \\\n    {HASH_A}\n"
    text_b = f"numpy==1.26.5 \\\n    {HASH_A}\n"  # 只改版本最後一碼
    parsed_a = b.parse_synthetic_lock_text(text_a)
    parsed_b = b.parse_synthetic_lock_text(text_b)
    assert parsed_a["canonical_sha256"] != parsed_b["canonical_sha256"]


def test_parse_synthetic_lock_text_hash_order_does_not_change_canonical_sha256():
    text_a = f"pandas==2.2.2 \\\n    {HASH_A} \\\n    {HASH_B}\n"
    text_b = f"pandas==2.2.2 \\\n    {HASH_B} \\\n    {HASH_A}\n"
    parsed_a = b.parse_synthetic_lock_text(text_a)
    parsed_b = b.parse_synthetic_lock_text(text_b)
    assert parsed_a["canonical_sha256"] == parsed_b["canonical_sha256"]


def test_parse_synthetic_lock_text_ignores_blank_lines_and_comments():
    text = f"# top comment\n\nnumpy==1.26.4 \\\n    {HASH_A}\n\n# trailing comment\n"
    parsed = b.parse_synthetic_lock_text(text)
    assert len(parsed["records"]) == 1


# ---- 11.4 parse_synthetic_lock_text —— fail-closed rejections ----


def test_parse_synthetic_lock_text_rejects_non_str():
    with pytest.raises(TypeError):
        b.parse_synthetic_lock_text(b"not a str")


def test_parse_synthetic_lock_text_rejects_empty_result():
    with pytest.raises(ValueError):
        b.parse_synthetic_lock_text("# only a comment\n")


@pytest.mark.parametrize(
    "bad_line",
    [
        f"pandas>=2.2.2 {HASH_A}",  # unpinned (range)
        f"pandas~=2.2.2 {HASH_A}",  # unpinned (compatible release)
        f"pandas {HASH_A}",  # no version at all
        "pandas==2.2.2",  # missing hash entirely
        "pandas==2.2.2 --hash=sha256:not-hex",  # malformed hash (non-hex)
        f"pandas==2.2.2 --hash=sha256:{'a' * 63}",  # malformed hash (too short)
        f"pandas==2.2.2 --hash=md5:{'a' * 32}",  # unsupported hash algorithm
        f"pandas @ https://example.com/pandas.whl {HASH_A}",  # URL form
        f"-e ./local_pkg {HASH_A}",  # editable
        f"git+https://example.com/repo.git#egg=pandas {HASH_A}",  # git
        f"./vendor/pandas==1.0 {HASH_A}",  # local relative directory
        f"/abs/vendor/pandas==1.0 {HASH_A}",  # local absolute directory
    ],
)
def test_parse_synthetic_lock_text_rejects_malformed_or_unsupported_lines(bad_line):
    with pytest.raises(ValueError):
        b.parse_synthetic_lock_text(bad_line + "\n")


def test_parse_synthetic_lock_text_rejects_syntactically_invalid_marker():
    text = f'pandas==2.2.2 ; this is not a valid marker expression {HASH_A}\n'
    with pytest.raises(ValueError, match="PEP 508"):
        b.parse_synthetic_lock_text(text)


def test_parse_synthetic_lock_text_rejects_duplicate_package_version_marker():
    text = f"pandas==2.2.2 {HASH_A}\npandas==2.2.2 {HASH_B}\n"
    with pytest.raises(ValueError, match="重複"):
        b.parse_synthetic_lock_text(text)


def test_parse_synthetic_lock_text_allows_same_package_version_with_different_markers():
    # 同一個套件/版本,但 marker 不同(例如分別鎖 win32/linux)不是重複記錄。
    text = (
        f'pandas==2.2.2 ; sys_platform == "win32" {HASH_A}\n'
        f'pandas==2.2.2 ; sys_platform == "linux" {HASH_B}\n'
    )
    parsed = b.parse_synthetic_lock_text(text)
    assert len(parsed["records"]) == 2


@pytest.mark.parametrize(
    "bad_text",
    [
        "pandas==2.2.2 \\  \n    " + HASH_A + "\n",  # 反斜線後面有多餘空白
        "pandas==2.2.2  \\\n    " + HASH_A + "\n",  # 反斜線前面有多餘空白
        "pandas==2.2.2 \\\n\n    " + HASH_A + "\n",  # 延續列後接空白列
        "pandas==2.2.2 \\\n# comment\n    " + HASH_A + "\n",  # 延續列後接註解列
        "pandas==2.2.2 \\\n",  # 檔案在延續列之後直接結束
        "\\\n    " + HASH_A + "\n",  # 延續列本身是空白開頭
    ],
)
def test_parse_synthetic_lock_text_rejects_ambiguous_continuation_lines(bad_text):
    with pytest.raises(ValueError):
        b.parse_synthetic_lock_text(bad_text)


# ---- 11.5 marker 解析/求值細節(用標準函式庫 packaging.markers,不是私有子集) ----


def test_marker_eval_supports_and():
    env = _windows_marker_environment(sys_platform="win32", python_version="3.12")
    assert b._evaluate_pep508_marker('sys_platform == "win32" and python_version >= "3.9"', env) is True
    assert b._evaluate_pep508_marker('sys_platform == "win32" and python_version >= "3.99"', env) is False


def test_marker_eval_supports_or():
    env = _windows_marker_environment(sys_platform="linux", python_version="3.5")
    # 兩個子句各自都是 False,但 or 讓一個真的子句救回整體 True。
    assert (
        b._evaluate_pep508_marker(
            'sys_platform == "win32" or python_version >= "3.0"', env
        )
        is True
    )
    assert (
        b._evaluate_pep508_marker(
            'sys_platform == "win32" or python_version >= "9.9"', env
        )
        is False
    )


def test_marker_eval_supports_parentheses():
    env = _windows_marker_environment(sys_platform="win32", os_name="nt", python_version="3.12")
    marker = 'python_version < "3.13" or (sys_platform == "win32" and os_name == "nt")'
    assert b._evaluate_pep508_marker(marker, env) is True

    env_no_match = _windows_marker_environment(sys_platform="linux", os_name="posix", python_version="4.0")
    assert b._evaluate_pep508_marker(marker, env_no_match) is False


def test_marker_eval_supports_quoted_values_with_either_quote_style():
    env = _windows_marker_environment(sys_platform="win32")
    assert b._evaluate_pep508_marker("sys_platform == 'win32'", env) is True
    assert b._evaluate_pep508_marker('sys_platform == "win32"', env) is True


def test_marker_eval_supports_in_and_not_in():
    env = _windows_marker_environment(platform_machine="AMD64")
    assert b._evaluate_pep508_marker('"AMD" in platform_machine', env) is True
    assert b._evaluate_pep508_marker('"ARM" not in platform_machine', env) is True
    assert b._evaluate_pep508_marker('"ARM" in platform_machine', env) is False


def test_marker_eval_supports_version_comparisons():
    env_new = _windows_marker_environment(python_version="3.12")
    env_old = _windows_marker_environment(python_version="3.8")
    assert b._evaluate_pep508_marker('python_version >= "3.9"', env_new) is True
    assert b._evaluate_pep508_marker('python_version >= "3.9"', env_old) is False
    assert b._evaluate_pep508_marker('python_version < "3.9"', env_old) is True


def test_marker_eval_windows_selection():
    env = _windows_marker_environment(sys_platform="win32")
    assert b._evaluate_pep508_marker('sys_platform == "win32"', env) is True


def test_marker_eval_linux_exclusion():
    env = _windows_marker_environment(sys_platform="linux")
    assert b._evaluate_pep508_marker('sys_platform == "win32"', env) is False


def test_marker_eval_rejects_malformed_expression():
    env = _windows_marker_environment()
    with pytest.raises(ValueError, match="PEP 508"):
        b._evaluate_pep508_marker("this is not === a marker", env)


def test_marker_eval_rejects_missing_marker_variable_in_injected_environment():
    # marker_environment 缺一個標準鍵 —— 必須整體被拒絕(不能悄悄放行,
    # 更不能悄悄讀到目前這台機器的真實值)。
    incomplete_env = {k: v for k, v in _windows_marker_environment().items() if k != "os_name"}
    with pytest.raises(ValueError, match="marker_environment_v1"):
        b._evaluate_pep508_marker('os_name == "nt"', incomplete_env)


def test_marker_eval_never_leaks_real_machine_environment():
    # 用一個「一定為真」的真機器條件(這個環境目前是 Windows)但注入一個
    # 完整、刻意設成別的值的 marker_environment——如果實作偷偷 fallback 回
    # 真機器環境,這裡就會意外算成 True。
    fake_env = _windows_marker_environment(sys_platform="linux", os_name="posix")
    assert b._evaluate_pep508_marker('sys_platform == "win32"', fake_env) is False
    assert b._evaluate_pep508_marker('os_name == "nt"', fake_env) is False


def test_marker_eval_rejects_extra_variable_not_in_frozen_environment():
    # 凍結的 marker_environment_v1 沒有 `extra` 這個鍵——引用它的 marker
    # 必須直接 raise,不能悄悄當成空字串處理。
    env = _windows_marker_environment()
    with pytest.raises(ValueError):
        b._evaluate_pep508_marker('extra == "test"', env)


def test_marker_eval_rejects_non_str_marker_raw():
    with pytest.raises(TypeError):
        b._evaluate_pep508_marker(None, _windows_marker_environment())


# ---- 11.6 _require_full_marker_environment ----


def test_require_full_marker_environment_accepts_exact_11_keys():
    env = _windows_marker_environment()
    assert b._require_full_marker_environment(env) == env


def test_require_full_marker_environment_rejects_missing_key():
    env = {k: v for k, v in _windows_marker_environment().items() if k != "sys_platform"}
    with pytest.raises(ValueError, match="marker_environment_v1"):
        b._require_full_marker_environment(env)


def test_require_full_marker_environment_rejects_extra_key():
    env = dict(_windows_marker_environment())
    env["extra"] = "x"
    with pytest.raises(ValueError, match="marker_environment_v1"):
        b._require_full_marker_environment(env)


def test_require_full_marker_environment_rejects_non_str_value():
    env = dict(_windows_marker_environment())
    env["python_version"] = 312
    with pytest.raises(ValueError):
        b._require_full_marker_environment(env)


def test_require_full_marker_environment_rejects_non_dict():
    with pytest.raises(TypeError):
        b._require_full_marker_environment(["not", "a", "dict"])


# ---- 11.7 select_locked_inventory_for_environment —— canonical sorted selection ----


def test_select_inventory_windows_only_marker_included_on_win32():
    text = f'pywin32==306 ; sys_platform == "win32" \\\n    {HASH_A}\n'
    parsed = b.parse_synthetic_lock_text(text)
    selected = b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())
    assert selected == [["pywin32", "306"]]


def test_select_inventory_windows_only_marker_excluded_on_non_windows():
    text = f'pywin32==306 ; sys_platform == "win32" \\\n    {HASH_A}\n'
    parsed = b.parse_synthetic_lock_text(text)
    selected = b.select_locked_inventory_for_environment(
        parsed, _windows_marker_environment(sys_platform="linux")
    )
    assert selected == []


def test_select_inventory_unconditional_dependency_always_included():
    text = f"numpy==1.26.4 \\\n    {HASH_A}\n"
    parsed = b.parse_synthetic_lock_text(text)
    selected_win = b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())
    selected_other = b.select_locked_inventory_for_environment(
        parsed, _windows_marker_environment(sys_platform="linux")
    )
    assert selected_win == selected_other == [["numpy", "1.26.4"]]


def test_select_inventory_returns_canonical_sorted_order_not_source_order():
    # Codex review 的核心修正:回傳順序必須是 (normalized_name, version)
    # 字典序,不是 lock 檔案裡的原始文字順序(這裡故意用反向字母順序寫
    # source text,確認回傳值仍然是排序過的)。
    text = f"zeta==1.0 \\\n    {HASH_A}\nalpha==2.0 \\\n    {HASH_B}\n"
    parsed = b.parse_synthetic_lock_text(text)
    selected = b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())
    assert selected == [["alpha", "2.0"], ["zeta", "1.0"]]


def test_select_inventory_canonical_sha256_is_independent_of_source_order():
    text_a = f"zeta==1.0 \\\n    {HASH_A}\nalpha==2.0 \\\n    {HASH_B}\n"
    text_b = f"alpha==2.0 \\\n    {HASH_B}\nzeta==1.0 \\\n    {HASH_A}\n"
    env = _windows_marker_environment()
    selected_a = b.select_locked_inventory_for_environment(b.parse_synthetic_lock_text(text_a), env)
    selected_b = b.select_locked_inventory_for_environment(b.parse_synthetic_lock_text(text_b), env)
    assert selected_a == selected_b
    sha_a = b.sha256_hex(b.canonical_json_bytes(selected_a, sort_keys=False))
    sha_b = b.sha256_hex(b.canonical_json_bytes(selected_b, sort_keys=False))
    assert sha_a == sha_b


def test_select_inventory_raw_record_order_is_diagnostic_only():
    # parsed_lock['records'] 仍然保留原始檔案順序(當診斷 metadata),但
    # 這個順序不能滲透進 select_locked_inventory_for_environment 的回傳值。
    text = f"zeta==1.0 \\\n    {HASH_A}\nalpha==2.0 \\\n    {HASH_B}\n"
    parsed = b.parse_synthetic_lock_text(text)
    assert [r["normalized_name"] for r in parsed["records"]] == ["zeta", "alpha"]
    selected = b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())
    assert [pair[0] for pair in selected] == ["alpha", "zeta"]


def test_select_inventory_rejects_duplicate_selected_pair_after_marker_evaluation():
    # 同一個 (normalized_name, version) 被兩筆不同 marker 的記錄各自選中
    # ——語意不明確,必須直接 raise,不能悄悄合併或悄悄保留其中一筆。
    text = (
        f'pkg==1.0 ; sys_platform == "win32" \\\n    {HASH_A}\n'
        f'pkg==1.0 ; python_version >= "3.0" \\\n    {HASH_B}\n'
    )
    parsed = b.parse_synthetic_lock_text(text)
    with pytest.raises(ValueError, match="重複"):
        b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())


def test_select_inventory_rejects_unknown_marker_variable_at_evaluation_time():
    # 建構一個直接指向注入環境沒有的變數的 marker——證明求值端本身也
    # fail-closed,不是只靠解析端擋。
    parsed = {
        "schema": b.SYNTHETIC_LOCK_PARSE_SCHEMA_TAG,
        "records": [
            {
                "raw_name": "x",
                "normalized_name": "x",
                "version": "1.0",
                "marker_raw": 'os_name == "nt"',
                "hashes": ("a" * 64,),
                "lineno": 1,
            }
        ],
        "canonical_sha256": "0" * 64,
    }
    incomplete_env = {k: v for k, v in _windows_marker_environment().items() if k != "os_name"}
    with pytest.raises(ValueError, match="marker_environment_v1"):
        b.select_locked_inventory_for_environment(parsed, incomplete_env)


def test_select_inventory_supports_version_range_comparison_via_packaging():
    text = f'pandas==2.2.2 ; python_version >= "3.9" \\\n    {HASH_A}\n'
    parsed = b.parse_synthetic_lock_text(text)
    selected_new = b.select_locked_inventory_for_environment(
        parsed, _windows_marker_environment(python_version="3.12")
    )
    selected_old = b.select_locked_inventory_for_environment(
        parsed, _windows_marker_environment(python_version="3.8")
    )
    assert selected_new == [["pandas", "2.2.2"]]
    assert selected_old == []


def test_select_inventory_rejects_non_dict_parsed_lock():
    with pytest.raises(TypeError):
        b.select_locked_inventory_for_environment(["not", "a", "dict"], _windows_marker_environment())


def test_select_inventory_rejects_non_dict_marker_environment():
    text = f"numpy==1.26.4 \\\n    {HASH_A}\n"
    parsed = b.parse_synthetic_lock_text(text)
    with pytest.raises(TypeError):
        b.select_locked_inventory_for_environment(parsed, ["not", "a", "dict"])


# ---- 11.8 check_selected_inventory_matches_declared_sha256 ----


def test_check_selected_inventory_matches_declared_sha256_accepts_correct_hash():
    selected = [["numpy", "1.26.4"], ["pandas", "2.2.2"]]
    correct = b.sha256_hex(b.canonical_json_bytes(selected, sort_keys=False))
    b.check_selected_inventory_matches_declared_sha256(selected, correct)  # must not raise


def test_check_selected_inventory_matches_declared_sha256_rejects_wrong_hash():
    selected = [["numpy", "1.26.4"]]
    wrong = "0" * 64
    with pytest.raises(ValueError, match="不符"):
        b.check_selected_inventory_matches_declared_sha256(selected, wrong)


def test_check_selected_inventory_matches_declared_sha256_sensitive_to_order():
    selected_a = [["numpy", "1.26.4"], ["pandas", "2.2.2"]]
    selected_b = [["pandas", "2.2.2"], ["numpy", "1.26.4"]]
    hash_a = b.sha256_hex(b.canonical_json_bytes(selected_a, sort_keys=False))
    with pytest.raises(ValueError):
        b.check_selected_inventory_matches_declared_sha256(selected_b, hash_a)


def test_check_selected_inventory_matches_declared_sha256_rejects_malformed_pair_shape():
    with pytest.raises(ValueError):
        b.check_selected_inventory_matches_declared_sha256(["numpy"], "0" * 64)


def test_check_selected_inventory_matches_declared_sha256_does_not_write_anything(tmp_path):
    # 沒有檔案路徑參數可傳——這個測試是文件性的:確認呼叫這支函式不會
    # 意外在 tmp_path 底下留下任何東西。
    before = list(tmp_path.iterdir())
    selected = [["numpy", "1.26.4"]]
    correct = b.sha256_hex(b.canonical_json_bytes(selected, sort_keys=False))
    b.check_selected_inventory_matches_declared_sha256(selected, correct)
    assert list(tmp_path.iterdir()) == before


# ---- 11.9 full synthetic round trip: parse -> select -> check ----


def test_full_synthetic_lock_round_trip_parse_select_check():
    text = (
        f'pandas==2.2.2 ; sys_platform == "win32" \\\n    {HASH_A} \\\n    {HASH_B}\n'
        f"numpy==1.26.4 \\\n    {HASH_C}\n"
        f'linux-only==9.9.9 ; sys_platform == "linux" \\\n    {HASH_A}\n'
    )
    parsed = b.parse_synthetic_lock_text(text)
    assert len(parsed["records"]) == 3

    selected = b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())
    # canonical sorted order:(normalized_name, version) 字典序,"numpy" < "pandas"。
    assert selected == [["numpy", "1.26.4"], ["pandas", "2.2.2"]]

    correct_sha256 = b.sha256_hex(b.canonical_json_bytes(selected, sort_keys=False))
    b.check_selected_inventory_matches_declared_sha256(selected, correct_sha256)  # must not raise

    with pytest.raises(ValueError):
        b.check_selected_inventory_matches_declared_sha256(selected, "0" * 64)


# ---- 11.10 import safety: 本節新函式不觸碰檔案系統/不呼叫 uv ----


def test_lock_parser_module_import_still_has_no_filesystem_side_effect(tmp_path):
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate.py"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('build_v2_candidate', r{str(script_path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "assert mod.LOCK_GENERATION_SPEC_V1['tool_family'] == 'uv pip compile'\n"
        "text = 'numpy==1.26.4 \\\\\\n    --hash=sha256:' + 'a' * 64 + '\\n'\n"
        "parsed = mod.parse_synthetic_lock_text(text)\n"
        "assert len(parsed['records']) == 1\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert list(work_dir.iterdir()) == []


# ----------------------------------------------------------------------------
# 11.11 Phase A3c — canonicalize_and_partition_installed_inventory
# ----------------------------------------------------------------------------


def test_bootstrap_tool_normalized_names_is_exactly_pip_setuptools_wheel():
    assert b.BOOTSTRAP_TOOL_NORMALIZED_NAMES == frozenset({"pip", "setuptools", "wheel"})


def test_canonicalize_and_partition_pep503_aliases_normalize_to_same_name():
    result = b.canonicalize_and_partition_installed_inventory([["Py_YAML", "6.0"]])
    assert result["installed_inventory"] == [["py-yaml", "6.0"]]


def test_canonicalize_and_partition_deterministic_sorting_independent_of_source_order():
    forward = b.canonicalize_and_partition_installed_inventory(
        [["zeta", "1.0"], ["alpha", "2.0"], ["mu", "3.0"]]
    )
    reversed_order = b.canonicalize_and_partition_installed_inventory(
        [["mu", "3.0"], ["alpha", "2.0"], ["zeta", "1.0"]]
    )
    assert forward == reversed_order
    assert forward["installed_inventory"] == [
        ["alpha", "2.0"],
        ["mu", "3.0"],
        ["zeta", "1.0"],
    ]


def test_canonicalize_and_partition_exact_bootstrap_separation():
    result = b.canonicalize_and_partition_installed_inventory(
        [["pip", "24.0"], ["setuptools", "70.0"], ["wheel", "0.43.0"], ["pandas", "2.2.2"]]
    )
    assert result["bootstrap_tool_inventory"] == [
        ["pip", "24.0"],
        ["setuptools", "70.0"],
        ["wheel", "0.43.0"],
    ]
    assert result["installed_inventory"] == [["pandas", "2.2.2"]]


def test_canonicalize_and_partition_absence_of_one_bootstrap_tool():
    result = b.canonicalize_and_partition_installed_inventory(
        [["pip", "24.0"], ["wheel", "0.43.0"], ["pandas", "2.2.2"]]
    )
    assert result["bootstrap_tool_inventory"] == [["pip", "24.0"], ["wheel", "0.43.0"]]
    assert result["installed_inventory"] == [["pandas", "2.2.2"]]


def test_canonicalize_and_partition_absence_of_all_bootstrap_tools():
    result = b.canonicalize_and_partition_installed_inventory([["pandas", "2.2.2"]])
    assert result["bootstrap_tool_inventory"] == []
    assert result["installed_inventory"] == [["pandas", "2.2.2"]]


def test_canonicalize_and_partition_unknown_tool_is_not_treated_as_bootstrap():
    # "piper" 不是 pip/setuptools/wheel 的其中之一,即使名稱看起來相似,
    # 也不能被誤判成 bootstrap 工具。
    result = b.canonicalize_and_partition_installed_inventory([["piper", "1.0"]])
    assert result["bootstrap_tool_inventory"] == []
    assert result["installed_inventory"] == [["piper", "1.0"]]


def test_canonicalize_and_partition_rejects_duplicate_identical_rows():
    with pytest.raises(ValueError, match="重複"):
        b.canonicalize_and_partition_installed_inventory(
            [["pandas", "2.2.2"], ["pandas", "2.2.2"]]
        )


def test_canonicalize_and_partition_rejects_two_versions_of_one_normalized_name():
    with pytest.raises(ValueError, match="重複"):
        b.canonicalize_and_partition_installed_inventory(
            [["pandas", "2.2.2"], ["pandas", "2.3.0"]]
        )


def test_canonicalize_and_partition_rejects_two_versions_after_pep503_normalization():
    # 兩筆字面上不同的原始名稱,正規化後其實是同一個套件——一樣要被抓到。
    with pytest.raises(ValueError, match="重複"):
        b.canonicalize_and_partition_installed_inventory(
            [["Py_YAML", "6.0"], ["py-yaml", "6.0.1"]]
        )


def test_canonicalize_and_partition_rejects_non_list_input():
    with pytest.raises(TypeError):
        b.canonicalize_and_partition_installed_inventory("not-a-list")


@pytest.mark.parametrize(
    "bad_item",
    [
        ["pandas"],  # too short
        ["pandas", "2.2.2", "extra"],  # too long
        "pandas==2.2.2",  # flat string
        [123, "2.2.2"],  # non-str name
        ["pandas", 222],  # non-str version
        ["", "2.2.2"],  # empty name
        ["pandas", ""],  # empty version
    ],
)
def test_canonicalize_and_partition_rejects_malformed_pair(bad_item):
    with pytest.raises(ValueError):
        b.canonicalize_and_partition_installed_inventory([bad_item])


# ----------------------------------------------------------------------------
# 11.12 select_locked_inventory_for_environment — 唯一版本強化(Phase A3c)
# ----------------------------------------------------------------------------


def test_select_inventory_rejects_two_different_versions_of_one_normalized_name():
    # 同一個正規化名稱被兩筆不同 marker 的記錄各自選中,但版本不同——
    # Phase A3c 強化前的舊邏輯只擋 pair 級重複,不擋這個。
    text = (
        f'pkg==1.0 ; sys_platform == "win32" \\\n    {HASH_A}\n'
        f'pkg==2.0 ; python_version >= "3.0" \\\n    {HASH_B}\n'
    )
    parsed = b.parse_synthetic_lock_text(text)
    with pytest.raises(ValueError, match="重複"):
        b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())


def test_select_inventory_still_rejects_identical_duplicate_pair():
    # 舊語意(同一個 (name, version) pair 被兩筆不同 marker 記錄各自選中)
    # 必須繼續被擋住——強化不能弱化既有覆蓋範圍。
    text = (
        f'pkg==1.0 ; sys_platform == "win32" \\\n    {HASH_A}\n'
        f'pkg==1.0 ; python_version >= "3.0" \\\n    {HASH_B}\n'
    )
    parsed = b.parse_synthetic_lock_text(text)
    with pytest.raises(ValueError, match="重複"):
        b.select_locked_inventory_for_environment(parsed, _windows_marker_environment())


# ----------------------------------------------------------------------------
# 11.13 reconcile_lock_selected_vs_installed_inventory(Phase A3c)
# ----------------------------------------------------------------------------


def test_reconcile_exact_match_is_equal_with_no_discrepancies():
    lock_selected = [["numpy", "1.26.4"], ["pandas", "2.2.2"]]
    installed = [["numpy", "1.26.4"], ["pandas", "2.2.2"]]
    result = b.reconcile_lock_selected_vs_installed_inventory(lock_selected, installed)
    assert result == {"equal": True, "discrepancies": []}


def test_reconcile_detects_missing_package():
    lock_selected = [["numpy", "1.26.4"], ["pandas", "2.2.2"]]
    installed = [["numpy", "1.26.4"]]
    result = b.reconcile_lock_selected_vs_installed_inventory(lock_selected, installed)
    assert result["equal"] is False
    assert result["discrepancies"] == [
        {
            "type": "missing",
            "normalized_name": "pandas",
            "expected_version": "2.2.2",
            "actual_version": None,
        }
    ]


def test_reconcile_detects_unexpected_package():
    lock_selected = [["numpy", "1.26.4"]]
    installed = [["numpy", "1.26.4"], ["pandas", "2.2.2"]]
    result = b.reconcile_lock_selected_vs_installed_inventory(lock_selected, installed)
    assert result["equal"] is False
    assert result["discrepancies"] == [
        {
            "type": "unexpected",
            "normalized_name": "pandas",
            "expected_version": None,
            "actual_version": "2.2.2",
        }
    ]


def test_reconcile_detects_version_mismatch():
    lock_selected = [["pandas", "2.2.2"]]
    installed = [["pandas", "2.3.0"]]
    result = b.reconcile_lock_selected_vs_installed_inventory(lock_selected, installed)
    assert result["equal"] is False
    assert result["discrepancies"] == [
        {
            "type": "version_mismatch",
            "normalized_name": "pandas",
            "expected_version": "2.2.2",
            "actual_version": "2.3.0",
        }
    ]


def test_reconcile_combined_discrepancies_sorted_deterministically():
    lock_selected = [["missing-pkg", "1.0"], ["pandas", "2.2.2"]]
    installed = [["pandas", "2.3.0"], ["unexpected-pkg", "9.9"]]
    result = b.reconcile_lock_selected_vs_installed_inventory(lock_selected, installed)
    assert result["equal"] is False
    assert result["discrepancies"] == [
        {
            "type": "missing",
            "normalized_name": "missing-pkg",
            "expected_version": "1.0",
            "actual_version": None,
        },
        {
            "type": "unexpected",
            "normalized_name": "unexpected-pkg",
            "expected_version": None,
            "actual_version": "9.9",
        },
        {
            "type": "version_mismatch",
            "normalized_name": "pandas",
            "expected_version": "2.2.2",
            "actual_version": "2.3.0",
        },
    ]


def test_reconcile_evidence_is_order_independent():
    lock_selected_a = [["missing-pkg", "1.0"], ["pandas", "2.2.2"]]
    lock_selected_b = [["pandas", "2.2.2"], ["missing-pkg", "1.0"]]
    installed_a = [["pandas", "2.3.0"], ["unexpected-pkg", "9.9"]]
    installed_b = [["unexpected-pkg", "9.9"], ["pandas", "2.3.0"]]
    result_a = b.reconcile_lock_selected_vs_installed_inventory(lock_selected_a, installed_a)
    result_b = b.reconcile_lock_selected_vs_installed_inventory(lock_selected_b, installed_b)
    assert result_a == result_b
    # 同一組內容也必須位元組相同(供 canonical JSON/雜湊使用)。
    assert b.canonical_json_bytes(result_a, sort_keys=True) == b.canonical_json_bytes(
        result_b, sort_keys=True
    )


def test_reconcile_no_tolerance_for_near_match_version_strings():
    # 沒有容忍值——即使字串上「看起來很接近」,只要不是逐字相等就是 mismatch。
    lock_selected = [["pandas", "2.2.2"]]
    installed = [["pandas", "2.2.20"]]
    result = b.reconcile_lock_selected_vs_installed_inventory(lock_selected, installed)
    assert result["equal"] is False
    assert result["discrepancies"][0]["type"] == "version_mismatch"


def test_reconcile_rejects_duplicate_normalized_name_within_lock_selected():
    with pytest.raises(ValueError, match="lock_selected_inventory"):
        b.reconcile_lock_selected_vs_installed_inventory(
            [["pandas", "2.2.2"], ["pandas", "2.3.0"]], [["pandas", "2.2.2"]]
        )


def test_reconcile_rejects_duplicate_normalized_name_within_installed():
    with pytest.raises(ValueError, match="installed_inventory"):
        b.reconcile_lock_selected_vs_installed_inventory(
            [["pandas", "2.2.2"]], [["pandas", "2.2.2"], ["pandas", "2.3.0"]]
        )


def test_reconcile_rejects_malformed_shape():
    with pytest.raises(ValueError):
        b.reconcile_lock_selected_vs_installed_inventory(["pandas"], [["pandas", "2.2.2"]])


def test_reconcile_result_is_compatible_with_existing_equality_result_schema():
    # 這個回傳值必須能直接原樣塞進 build_environment_creation_receipt。
    lock_selected_inventory = [["pandas", "2.2.2"]]
    installed_inventory = [["pandas", "2.2.2"]]
    equality_result = b.reconcile_lock_selected_vs_installed_inventory(
        lock_selected_inventory, installed_inventory
    )
    receipt = _build_valid_environment_creation_receipt(
        lock_selected_inventory=lock_selected_inventory,
        lock_selected_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes(lock_selected_inventory, sort_keys=False)
        ),
        installed_inventory=installed_inventory,
        installed_inventory_sha256=b.sha256_hex(
            b.canonical_json_bytes(installed_inventory, sort_keys=False)
        ),
        equality_result=equality_result,
    )
    b.validate_environment_creation_receipt(receipt)  # must not raise


# ----------------------------------------------------------------------------
# 11.14 guard_inventory_reconciliation_equal(Phase A3c)
# ----------------------------------------------------------------------------


def test_guard_inventory_reconciliation_equal_allows_true():
    b.guard_inventory_reconciliation_equal({"equal": True, "discrepancies": []})  # must not raise


def test_guard_inventory_reconciliation_equal_rejects_false():
    equality_result = {
        "equal": False,
        "discrepancies": [
            {
                "type": "version_mismatch",
                "normalized_name": "pandas",
                "expected_version": "2.2.2",
                "actual_version": "2.3.0",
            }
        ],
    }
    with pytest.raises(ValueError, match="equal"):
        b.guard_inventory_reconciliation_equal(equality_result)


def test_guard_inventory_reconciliation_equal_rejects_truthy_non_bool():
    # isinstance(1, bool) is False——truthy 數字冒充布林值一樣要被擋。
    with pytest.raises(ValueError):
        b.guard_inventory_reconciliation_equal({"equal": 1, "discrepancies": []})


def test_guard_inventory_reconciliation_equal_rejects_malformed_shape():
    with pytest.raises(ValueError, match="equality_result"):
        b.guard_inventory_reconciliation_equal({"equal": True})


def test_guard_inventory_reconciliation_equal_with_real_reconcile_output():
    equality_result = b.reconcile_lock_selected_vs_installed_inventory(
        [["pandas", "2.2.2"]], [["pandas", "2.2.2"]]
    )
    b.guard_inventory_reconciliation_equal(equality_result)  # must not raise

    mismatched_result = b.reconcile_lock_selected_vs_installed_inventory(
        [["pandas", "2.2.2"]], [["pandas", "2.3.0"]]
    )
    with pytest.raises(ValueError):
        b.guard_inventory_reconciliation_equal(mismatched_result)


# ----------------------------------------------------------------------------
# 11.15 Phase A3c — import/call 安全性:不觸碰檔案系統、不呼叫 subprocess
# ----------------------------------------------------------------------------


def test_phase_a3c_functions_produce_no_filesystem_or_subprocess_side_effects(tmp_path):
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate.py"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('build_v2_candidate', r{str(script_path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "partitioned = mod.canonicalize_and_partition_installed_inventory(\n"
        "    [['pip', '24.0'], ['pandas', '2.2.2']]\n"
        ")\n"
        "assert partitioned['bootstrap_tool_inventory'] == [['pip', '24.0']]\n"
        "equality = mod.reconcile_lock_selected_vs_installed_inventory(\n"
        "    [['pandas', '2.2.2']], partitioned['installed_inventory']\n"
        ")\n"
        "mod.guard_inventory_reconciliation_equal(equality)\n"
        "assert equality['equal'] is True\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert list(work_dir.iterdir()) == []


# ----------------------------------------------------------------------------
# 11.16 Phase A3c blocking-fix — regression coverage (Codex review)
# ----------------------------------------------------------------------------


# ---- alias equality / duplicate aliases in reconciliation ----


def test_reconcile_pep503_alias_names_are_treated_as_same_package():
    # Py_YAML vs py-yaml 是同一個 PEP 503 套件——對帳前這裡自己會正規化
    # 兩邊,不能被誤判成「lock 選中但沒觀測到」+「觀測到但 lock 沒選中」。
    result = b.reconcile_lock_selected_vs_installed_inventory(
        [["Py_YAML", "6.0"]], [["py-yaml", "6.0"]]
    )
    assert result == {"equal": True, "discrepancies": []}


def test_reconcile_alias_names_with_different_versions_is_a_version_mismatch():
    result = b.reconcile_lock_selected_vs_installed_inventory(
        [["Py_YAML", "6.0"]], [["py-yaml", "6.0.1"]]
    )
    assert result == {
        "equal": False,
        "discrepancies": [
            {
                "type": "version_mismatch",
                "normalized_name": "py-yaml",
                "expected_version": "6.0",
                "actual_version": "6.0.1",
            }
        ],
    }


def test_reconcile_rejects_duplicate_aliases_after_normalization_on_lock_side():
    with pytest.raises(ValueError, match="lock_selected_inventory"):
        b.reconcile_lock_selected_vs_installed_inventory(
            [["Py_YAML", "6.0"], ["py-yaml", "6.0.1"]], [["py-yaml", "6.0"]]
        )


def test_reconcile_rejects_duplicate_aliases_after_normalization_on_installed_side():
    with pytest.raises(ValueError, match="installed_inventory"):
        b.reconcile_lock_selected_vs_installed_inventory(
            [["py-yaml", "6.0"]], [["Py_YAML", "6.0"], ["py-yaml", "6.0.1"]]
        )


# ---- receipt inventories must actually be canonical, not just shaped right ----


def test_build_environment_creation_receipt_rejects_unsorted_installed_inventory():
    with pytest.raises(ValueError, match="sorted"):
        _build_valid_environment_creation_receipt(
            installed_inventory=[["zeta", "1.0"], ["alpha", "2.0"]],
            installed_inventory_sha256=b.sha256_hex(
                b.canonical_json_bytes(
                    [["zeta", "1.0"], ["alpha", "2.0"]], sort_keys=False
                )
            ),
        )


def test_build_environment_creation_receipt_rejects_non_normalized_name_in_installed_inventory():
    with pytest.raises(ValueError, match="normalized"):
        _build_valid_environment_creation_receipt(
            installed_inventory=[["Py_YAML", "6.0"]],
            installed_inventory_sha256=b.sha256_hex(
                b.canonical_json_bytes([["Py_YAML", "6.0"]], sort_keys=False)
            ),
        )


def test_build_environment_creation_receipt_rejects_empty_value_in_lock_selected_inventory():
    with pytest.raises(ValueError):
        _build_valid_environment_creation_receipt(
            lock_selected_inventory=[["pandas", ""]],
            lock_selected_inventory_sha256=b.sha256_hex(
                b.canonical_json_bytes([["pandas", ""]], sort_keys=False)
            ),
        )


def test_build_environment_creation_receipt_rejects_duplicate_name_in_lock_selected_inventory():
    with pytest.raises(ValueError, match="lock_selected_inventory"):
        _build_valid_environment_creation_receipt(
            lock_selected_inventory=[["pandas", "2.2.2"], ["pandas", "2.3.0"]],
            lock_selected_inventory_sha256=b.sha256_hex(
                b.canonical_json_bytes(
                    [["pandas", "2.2.2"], ["pandas", "2.3.0"]], sort_keys=False
                )
            ),
        )


def test_validate_environment_creation_receipt_rejects_unsorted_bootstrap_tool_inventory():
    receipt = _build_valid_environment_creation_receipt()
    tampered = dict(receipt)
    tampered["bootstrap_tool_inventory"] = [["wheel", "0.43.0"], ["pip", "24.0"]]
    with pytest.raises(ValueError, match="sorted"):
        b.validate_environment_creation_receipt(tampered)


def test_build_environment_creation_receipt_rejects_bootstrap_name_inside_installed_inventory():
    with pytest.raises(ValueError, match="bootstrap"):
        _build_valid_environment_creation_receipt(
            installed_inventory=[["pandas", "2.2.2"], ["pip", "24.0"]],
            installed_inventory_sha256=b.sha256_hex(
                b.canonical_json_bytes(
                    [["pandas", "2.2.2"], ["pip", "24.0"]], sort_keys=False
                )
            ),
        )


def test_build_environment_creation_receipt_rejects_unknown_name_inside_bootstrap_tool_inventory():
    with pytest.raises(ValueError, match="bootstrap"):
        _build_valid_environment_creation_receipt(
            bootstrap_tool_inventory=[
                ["pip", "24.0"],
                ["setuptools", "70.0"],
                ["wheel", "0.43.0"],
                ["not-a-bootstrap-tool", "1.0"],
            ]
        )


def test_validate_environment_creation_receipt_rejects_bootstrap_name_inside_installed_inventory():
    receipt = _build_valid_environment_creation_receipt()
    tampered = dict(receipt)
    tampered["installed_inventory"] = [["pandas", "2.2.2"], ["pip", "24.0"]]
    with pytest.raises(ValueError, match="bootstrap"):
        b.validate_environment_creation_receipt(tampered)


def test_validate_environment_creation_receipt_rejects_unknown_name_inside_bootstrap_tool_inventory():
    receipt = _build_valid_environment_creation_receipt()
    tampered = dict(receipt)
    tampered["bootstrap_tool_inventory"] = [["pip", "24.0"], ["not-bootstrap", "1.0"]]
    with pytest.raises(ValueError, match="bootstrap"):
        b.validate_environment_creation_receipt(tampered)


def test_check_selected_inventory_matches_declared_sha256_rejects_unsorted_inventory():
    unsorted = [["zeta", "1.0"], ["alpha", "2.0"]]
    correct_hash = b.sha256_hex(b.canonical_json_bytes(unsorted, sort_keys=False))
    with pytest.raises(ValueError, match="sorted"):
        b.check_selected_inventory_matches_declared_sha256(unsorted, correct_hash)


# ---- equal/discrepancies internal-consistency contradictions ----


def test_require_equality_result_rejects_true_with_non_empty_discrepancies():
    with pytest.raises(ValueError, match="non-empty"):
        b.guard_inventory_reconciliation_equal(
            {
                "equal": True,
                "discrepancies": [
                    {
                        "type": "version_mismatch",
                        "normalized_name": "pandas",
                        "expected_version": "2.2.2",
                        "actual_version": "2.3.0",
                    }
                ],
            }
        )


def test_require_equality_result_rejects_false_with_empty_discrepancies():
    with pytest.raises(ValueError, match="empty"):
        b.guard_inventory_reconciliation_equal({"equal": False, "discrepancies": []})


def test_build_environment_creation_receipt_rejects_true_with_non_empty_discrepancies():
    with pytest.raises(ValueError):
        _build_valid_environment_creation_receipt(
            equality_result={
                "equal": True,
                "discrepancies": [
                    {
                        "type": "version_mismatch",
                        "normalized_name": "pandas",
                        "expected_version": "2.2.2",
                        "actual_version": "2.3.0",
                    }
                ],
            }
        )


# ---- malformed / wrongly ordered / duplicate discrepancy objects ----


def test_require_equality_result_rejects_discrepancy_with_extra_key():
    with pytest.raises(ValueError, match="discrepancies"):
        b.guard_inventory_reconciliation_equal(
            {
                "equal": False,
                "discrepancies": [
                    {
                        "type": "missing",
                        "normalized_name": "pandas",
                        "expected_version": "2.2.2",
                        "actual_version": None,
                        "extra": "x",
                    }
                ],
            }
        )


def test_require_equality_result_rejects_discrepancy_with_unknown_type():
    with pytest.raises(ValueError, match="type"):
        b.guard_inventory_reconciliation_equal(
            {
                "equal": False,
                "discrepancies": [
                    {
                        "type": "not-a-real-type",
                        "normalized_name": "pandas",
                        "expected_version": "2.2.2",
                        "actual_version": None,
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "bad_discrepancy",
    [
        # missing must have actual_version=None
        {
            "type": "missing",
            "normalized_name": "pandas",
            "expected_version": "2.2.2",
            "actual_version": "2.2.2",
        },
        # unexpected must have expected_version=None
        {
            "type": "unexpected",
            "normalized_name": "pandas",
            "expected_version": "2.2.2",
            "actual_version": "2.2.2",
        },
        # version_mismatch with equal versions is not a real mismatch
        {
            "type": "version_mismatch",
            "normalized_name": "pandas",
            "expected_version": "2.2.2",
            "actual_version": "2.2.2",
        },
    ],
)
def test_require_equality_result_rejects_nullability_inconsistent_with_type(bad_discrepancy):
    with pytest.raises(ValueError):
        b.guard_inventory_reconciliation_equal(
            {"equal": False, "discrepancies": [bad_discrepancy]}
        )


def test_require_equality_result_rejects_wrongly_ordered_discrepancies():
    with pytest.raises(ValueError, match="sorted"):
        b.guard_inventory_reconciliation_equal(
            {
                "equal": False,
                "discrepancies": [
                    {
                        "type": "unexpected",
                        "normalized_name": "zeta",
                        "expected_version": None,
                        "actual_version": "1.0",
                    },
                    {
                        "type": "missing",
                        "normalized_name": "alpha",
                        "expected_version": "1.0",
                        "actual_version": None,
                    },
                ],
            }
        )


def test_require_equality_result_rejects_duplicate_discrepancy_identity():
    with pytest.raises(ValueError, match="duplicate"):
        b.guard_inventory_reconciliation_equal(
            {
                "equal": False,
                "discrepancies": [
                    {
                        "type": "missing",
                        "normalized_name": "pandas",
                        "expected_version": "2.2.2",
                        "actual_version": None,
                    },
                    {
                        "type": "missing",
                        "normalized_name": "pandas",
                        "expected_version": "2.3.0",
                        "actual_version": None,
                    },
                ],
            }
        )


# ---- forged receipt: hashes recomputed to match forged (mismatched) inventories ----


def test_validate_environment_creation_receipt_rejects_forged_equal_true_with_self_consistent_hashes():
    # 手造一份「inventory hash 自己對得起來(竄改 installed_inventory 的
    # 同時把它的 sha256 一起改成對得上的值),但兩份 inventory 內容其實
    # 不一樣、equality_result 卻還留著原本(相符時)的 equal=True/
    # discrepancies=[]」的 receipt——sha256 自洽性檢查本身不會抓到這個,
    # 必須靠獨立重算 reconcile 才抓得到。
    receipt = _build_valid_environment_creation_receipt()
    forged_installed_inventory = [["pandas", "2.3.0"]]  # 原本是 2.2.2
    tampered = dict(receipt)
    tampered["installed_inventory"] = forged_installed_inventory
    tampered["installed_inventory_sha256"] = b.sha256_hex(
        b.canonical_json_bytes(forged_installed_inventory, sort_keys=False)
    )
    tampered["environment_creation_identity"] = b.environment_creation_identity(tampered)
    with pytest.raises(ValueError, match="equality_result"):
        b.validate_environment_creation_receipt(tampered)


def test_validate_environment_creation_receipt_rejects_hand_forged_equality_result():
    # 繞過 builder 的內部一致性檢查,直接手造一份型別正確、雜湊自洽,但
    # equality_result 是編造的 True/[] 的 receipt(builder 本身已經會擋
    # 這個,這裡驗證 validate() 自己重算時也獨立抓到,不是只信 builder)。
    receipt = _build_valid_environment_creation_receipt(
        **_mismatched_inventory_receipt_kwargs()
    )
    tampered = dict(receipt)
    tampered["equality_result"] = {"equal": True, "discrepancies": []}
    tampered["environment_creation_identity"] = b.environment_creation_identity(tampered)
    with pytest.raises(ValueError, match="equality_result"):
        b.validate_environment_creation_receipt(tampered)


# ---- valid canonical receipt round trip remains accepted ----


def test_valid_canonical_receipt_with_bootstrap_tools_round_trips_through_validator():
    receipt = _build_valid_environment_creation_receipt()
    assert receipt["bootstrap_tool_inventory"] == [
        ["pip", "24.0"],
        ["setuptools", "70.0"],
        ["wheel", "0.43.0"],
    ]
    b.validate_environment_creation_receipt(receipt)  # must not raise


# ----------------------------------------------------------------------------
# 12. CLI 安全邊界
# ----------------------------------------------------------------------------


def test_import_has_no_filesystem_side_effect(tmp_path):
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate.py"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('build_v2_candidate', r{str(script_path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert list(work_dir.iterdir()) == []


def test_default_cli_cannot_read_sentinel_or_create_output(tmp_path, monkeypatch):
    sentinel = tmp_path / "sentinel_source.txt"
    sentinel.write_text("do-not-read", encoding="utf-8")
    would_be_output = tmp_path / "would_be_output"

    opened_paths = []
    real_open = open

    def spy_open(file, *args, **kwargs):
        opened_paths.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", spy_open)

    rc = b.main(["--dataset", "anything", "--authorize-phase-b", "--cache-dir", str(would_be_output)])

    assert rc != 0
    assert opened_paths == []
    assert not would_be_output.exists()
    assert sentinel.read_text(encoding="utf-8") == "do-not-read"


def test_default_cli_ignores_argv_entirely():
    assert b.main(None) == b.main([]) == b.main(["--anything", "-x"]) == 1


def test_cli_subprocess_default_invocation_exits_nonzero_without_writes(tmp_path):
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    script_path = REPO_ROOT / "scripts" / "build_v2_candidate.py"
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert list(work_dir.iterdir()) == []
