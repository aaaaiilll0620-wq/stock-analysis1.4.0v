# -*- coding: utf-8 -*-
"""build_v2_candidate.py — DataExport0806 → V2 隔離候選建置的 builder 骨架。

規格:`docs/預註冊_DataExport0806_V2隔離建置.md`(下稱「預註冊文件」)
§C.1(內容定址身分模型)、§C.4(隔離輸出根目錄 + path-identity 檢查)、
§C.5(receipt schema,本輪僅 environment-creation + 頂層身分欄位)、
§D(混合架構——本檔案是「新 builder/orchestrator 腳本」,不是
`tej_importer.py` 本體,兩者身分刻意分開,見 §D「混合架構」)。

**累計範圍(Phase A2a → A2b → A3a → A3c)**:builder 的純身分/路徑基礎
(canonical JSON/SHA-256 helper、身分鏈的純計算、candidate-path 守衛、
environment-creation/頂層身分 receipt 的 schema validator/builder)、安全
receipt writer(排他建立 JSON、environment-creation/頂層 build receipt 的
gate-then-write、receipt 檔名路徑守衛)、Phase A3a 凍結的 lock 產生策略
常數 + 對**注入合成文字**的獨立 strict parser/marker 選取/inventory-SHA
核對、Phase A3c 對**注入的合成 inventory**的純 bootstrap 分離/canonical
分割、lock-selected 唯一版本強化、完整對帳 helper + fail-closed gate,
**加上 Phase A3c 的 blocking-fix 修正**(Codex review 抓到的三個
fail-closed 繞過:對帳的 `equal`/`discrepancies` 邏輯不一致未擋、receipt
inventory 只做形狀檢查沒要求真的 canonical、對帳沒有正規化兩邊輸入導致
別名被誤判成 missing+unexpected)。**不**碰 `tej_importer.py`、**不**實作
獨立 verifier、**不**執行任何一次
真正的 Phase B 解析/建置、**不**呼叫 uv 或產生真正的
`requirements-v2-data-build.lock`、**不**呼叫
`importlib.metadata.distributions()`(那是另一個獨立、本輪不做的環境觀測
adapter 任務——這裡的每一筆 inventory 都是呼叫端注入的合成資料)。

狀態邊界(呼叫端必須遵守,本模組的 import 本身不觸碰檔案系統):
`PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED` / `BUILD_NOT_RUN` /
`PRODUCTION_NOT_APPROVED`。這個模組被 import 時不得有任何檔案系統副作用
——所有需要磁碟/git/套件環境觀測值的函式,一律以「注入參數」的形式接收,
不在模組內部呼叫。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from packaging.markers import (
    InvalidMarker,
    Marker,
    UndefinedComparison,
    UndefinedEnvironmentName,
)

# ----------------------------------------------------------------------------
# 1. Canonical JSON bytes + SHA-256 helpers
#    預註冊文件 §C.1「組合公式」/§C.1 marker_environment_v1 canonical 序列化/
#    §C.9 dedup_key_v1 canonical 序列化,三處共用同一套 JSON 編碼規則:
#    ensure_ascii=True, separators=(",", ":"),UTF-8 編碼,小寫十六進位輸出。
#    差異只在 sort_keys(物件用 True,陣列用 False——陣列順序本來就固定,
#    sort_keys 對陣列不生效,這裡仍顯式傳入以避免呼叫端誤用物件時漏設)。
# ----------------------------------------------------------------------------

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(obj, *, sort_keys: bool) -> bytes:
    """預註冊文件 §C.1/§C.9 共用的 canonical JSON 序列化規則。"""
    return json.dumps(
        obj, ensure_ascii=True, separators=(",", ":"), sort_keys=sort_keys
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError(f"payload must be bytes, got {type(payload).__name__}")
    return hashlib.sha256(payload).hexdigest()


def _require_str(name: str, value) -> str:
    """no fallback / no permissive parsing:缺席 (None)、非字串、空字串一律
    直接 raise,不猜測、不補預設值——見預註冊文件「設計限制」段。"""
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty str, got {value!r}")
    return value


def _require_sha256_hex(name: str, value) -> str:
    """身分鏈裡每一個 `..._identity` 欄位都是 SHA-256 輸出,依預註冊文件
    「雜湊值一律小寫十六進位」的慣例,固定 64 個小寫十六進位字元。"""
    _require_str(name, value)
    if not _HEX64_RE.match(value):
        raise ValueError(
            f"{name} must be exactly 64 lowercase hex characters, got {value!r}"
        )
    return value


# ----------------------------------------------------------------------------
# 2. File SHA-256 identity helper
#    跟 tej_importer._sha256_of(131-139 行)同一套 8 MiB 串流演算法——串流
#    分塊大小不影響 SHA-256 摘要本身(演算法本身是逐位元組決定性的),這裡
#    獨立實作而不 import tej_importer,避免本輪的純身分/路徑模組多背一層
#    對 tej_importer(以及它 import 的 openpyxl/pyarrow)的耦合。
# ----------------------------------------------------------------------------

_FILE_HASH_CHUNK_SIZE = 8 * 1024 * 1024


def sha256_of_file(path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_FILE_HASH_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------
# 3. Manifest pair validation
#    預註冊文件 §C.1:manifest_identity(manifest.csv 整檔雜湊)跟
#    manifest_sha256_file_identity(manifest.sha256 整檔雜湊)分開算,但兩份
#    檔案「內容」彼此還必須逐 relpath 交叉核對一致(這是 §C.2 提到、目前
#    tej_importer 完全沒做的「只讀 manifest.csv,完全不讀 manifest.sha256」
#    缺口)。這裡只驗證兩份注入路徑彼此是否一致,不碰真正的
#    tej_exports/DataExport0806_manifest.csv/.sha256,也不核對磁碟上的來源
#    檔案本身(那是 tej_importer._manifest_preflight 的既有職責)。
# ----------------------------------------------------------------------------

# scripts/build_data_manifest.py 的既有格式(csv 標頭 + `sha256sum -c` 相容
# 的 `.sha256`)——標準 sha256sum 格式是 `<64碼hex><固定一個space><mode
# char><relpath>`,mode char 是 ' '(文字模式)或 '*'(二進位模式),兩者
# 合計是 hash 後面固定兩個字元(scripts/build_data_manifest.py 66 行寫
# `f"{digest}  {rel}\n"`,兩個字面空格正是「固定分隔空格」+「文字模式
# mode char 剛好也是空格」的組合,不是「一個可有可無的分隔符」)。這裡的
# 解析邏輯是這份格式的獨立第二實作,不 import build_data_manifest.py。
_MANIFEST_CSV_FIELDNAMES = ["relpath", "size_bytes", "sha256", "mtime_utc"]
_SHA256_LINE_RE = re.compile(r"^([0-9a-fA-F]{64}) ([ *])(.+)$")


def parse_manifest_csv(path) -> dict:
    """獨立解析 manifest.csv,回傳 {relpath: sha256(小寫)}。fail-closed:
    標頭不符、relpath 空白/重複、sha256 格式不合法(非 64 碼小寫 hex)一律
    直接 raise。"""
    import csv

    path = Path(path)
    entries: dict = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: manifest.csv 是空檔案,缺標頭列")
        if header != _MANIFEST_CSV_FIELDNAMES:
            raise ValueError(
                f"{path}: manifest.csv 標頭不符,預期 {_MANIFEST_CSV_FIELDNAMES},"
                f" 實際 {header!r}"
            )
        for lineno, row in enumerate(reader, start=2):
            if len(row) != len(_MANIFEST_CSV_FIELDNAMES):
                raise ValueError(
                    f"{path}:第 {lineno} 列欄位數不符(預期"
                    f" {len(_MANIFEST_CSV_FIELDNAMES)},實際 {len(row)}):{row!r}"
                )
            relpath, _size_bytes, sha256_value, _mtime_utc = row
            if not relpath:
                raise ValueError(f"{path}:第 {lineno} 列 relpath 為空")
            if relpath in entries:
                raise ValueError(f"{path}:第 {lineno} 列 relpath 重複:{relpath!r}")
            if not _HEX64_RE.match(sha256_value):
                raise ValueError(
                    f"{path}:第 {lineno} 列 sha256 格式不合法(需 64 碼小寫"
                    f" hex):{sha256_value!r}"
                )
            entries[relpath] = sha256_value
    return entries


def parse_manifest_sha256(path) -> dict:
    """獨立解析 `sha256sum -c` 相容格式的 .sha256 檔案,回傳
    {relpath: sha256(小寫)}。fail-closed:空白列、格式不合法、relpath 空白/
    重複、hash 非小寫一律直接 raise。"""
    path = Path(path)
    entries: dict = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\r\n")
            if line == "":
                raise ValueError(f"{path}:第 {lineno} 列是空白列,不允許")
            m = _SHA256_LINE_RE.match(line)
            if not m:
                raise ValueError(f"{path}:第 {lineno} 列格式不合法:{line!r}")
            digest, _mode_char, relpath = m.group(1), m.group(2), m.group(3)
            if digest != digest.lower():
                raise ValueError(
                    f"{path}:第 {lineno} 列 hash 必須是小寫十六進位:{digest!r}"
                )
            if not relpath:
                raise ValueError(f"{path}:第 {lineno} 列 relpath 為空")
            if relpath in entries:
                raise ValueError(f"{path}:第 {lineno} 列 relpath 重複:{relpath!r}")
            entries[relpath] = digest
    return entries


def validate_manifest_pair(manifest_csv_path, manifest_sha256_path) -> dict:
    """交叉核對 manifest.csv 與 manifest.sha256 是否逐 relpath 完全一致
    (無缺、無多、hash 逐一相符)。全部一致才回傳 {relpath: sha256};任一項
    不符直接 raise,不做部分採信。"""
    csv_entries = parse_manifest_csv(manifest_csv_path)
    sha_entries = parse_manifest_sha256(manifest_sha256_path)

    csv_keys = set(csv_entries)
    sha_keys = set(sha_entries)
    only_in_csv = csv_keys - sha_keys
    only_in_sha256 = sha_keys - csv_keys
    if only_in_csv or only_in_sha256:
        raise ValueError(
            "manifest.csv 與 manifest.sha256 的 relpath 集合不一致:"
            f" 只在 csv={sorted(only_in_csv)} 只在 sha256={sorted(only_in_sha256)}"
        )

    mismatched = sorted(r for r in csv_keys if csv_entries[r] != sha_entries[r])
    if mismatched:
        raise ValueError(
            f"manifest.csv 與 manifest.sha256 對同一個 relpath 記錄了不同的"
            f" sha256:{mismatched}"
        )

    return dict(csv_entries)


# ----------------------------------------------------------------------------
# 4. 身分鏈的純計算——預註冊文件 §C.1「組合公式」跟兩份 canonical JSON 身分
#    (marker_environment_identity_v1 / runtime_environment_identity_v1)。
#    這裡只接受注入參數,不讀環境、不讀 git、不讀檔案——那些「取得值」的
#    動作是呼叫端(未來 Phase B 的 builder 主流程)的職責。
# ----------------------------------------------------------------------------

CANDIDATE_SCHEMA_VERSION = "dataexport0806_v2_candidate_schema_v1"


def source_data_identity(
    manifest_identity: str,
    manifest_sha256_file_identity: str,
    supplement_identity: str,
) -> str:
    """預註冊文件 §C.1「組合公式」第一層,逐位元組照抄。"""
    _require_sha256_hex("manifest_identity", manifest_identity)
    _require_sha256_hex(
        "manifest_sha256_file_identity", manifest_sha256_file_identity
    )
    _require_sha256_hex("supplement_identity", supplement_identity)
    payload = (
        f"manifest_sha256={manifest_identity}\n"
        f"manifest_sha256_file_sha256={manifest_sha256_file_identity}\n"
        f"supplement_receipt_sha256={supplement_identity}"
    )
    return sha256_hex(payload.encode("utf-8"))


def build_implementation_identity(
    importer_identity: str,
    extractor_identity: str,
    builder_identity: str,
    dependency_lock_identity: str,
    runtime_environment_identity_v1_value: str,
    preregistration_commit: str,
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION,
) -> str:
    """預註冊文件 §C.1「組合公式」第二層,逐位元組照抄(第 19 輪新增
    runtime_environment_identity_v1_value 這個輸入)。"""
    _require_sha256_hex("importer_identity", importer_identity)
    _require_sha256_hex("extractor_identity", extractor_identity)
    _require_sha256_hex("builder_identity", builder_identity)
    _require_sha256_hex("dependency_lock_identity", dependency_lock_identity)
    _require_sha256_hex(
        "runtime_environment_identity_v1", runtime_environment_identity_v1_value
    )
    _require_str("preregistration_commit", preregistration_commit)
    if candidate_schema_version != CANDIDATE_SCHEMA_VERSION:
        raise ValueError(
            "candidate_schema_version 是預註冊文件凍結的字面常數"
            f" {CANDIDATE_SCHEMA_VERSION!r},不能替換,收到"
            f" {candidate_schema_version!r}"
        )
    payload = (
        f"importer_sha256={importer_identity}\n"
        f"extraction_script_sha256={extractor_identity}\n"
        f"builder_sha256={builder_identity}\n"
        f"dependency_lock_sha256={dependency_lock_identity}\n"
        f"runtime_environment_identity_v1={runtime_environment_identity_v1_value}\n"
        f"preregistration_commit={preregistration_commit}\n"
        f"candidate_schema_version={candidate_schema_version}"
    )
    return sha256_hex(payload.encode("utf-8"))


def snapshot_id_v1(
    source_data_identity_value: str, build_implementation_identity_value: str
) -> str:
    """預註冊文件 §C.1「組合公式」第三層,逐位元組照抄。"""
    _require_sha256_hex(
        "source_data_identity", source_data_identity_value
    )
    _require_sha256_hex(
        "build_implementation_identity", build_implementation_identity_value
    )
    payload = (
        f"source_data_identity={source_data_identity_value}\n"
        f"build_implementation_identity={build_implementation_identity_value}"
    )
    return sha256_hex(payload.encode("utf-8"))


# marker_environment_v1 的鍵集合,逐一對應預註冊文件 §C.1 凍結的
# `packaging.markers.default_environment()` 11 個鍵(第 21 輪凍結)。
MARKER_ENVIRONMENT_KEYS = frozenset(
    {
        "implementation_name",
        "implementation_version",
        "os_name",
        "platform_machine",
        "platform_python_implementation",
        "platform_release",
        "platform_system",
        "platform_version",
        "python_full_version",
        "python_version",
        "sys_platform",
    }
)


def marker_environment_identity_v1(marker_environment_v1: dict) -> str:
    """預註冊文件 §C.1 marker_environment_v1 canonical 序列化 + 雜湊。
    鍵集合必須逐一對應、只能對應上面 11 個鍵;每個值必須是字串;缺鍵/多鍵/
    非字串一律直接 raise,不猜測或補預設值。"""
    if not isinstance(marker_environment_v1, dict):
        raise TypeError(
            f"marker_environment_v1 must be a dict, got {type(marker_environment_v1).__name__}"
        )
    keys = set(marker_environment_v1.keys())
    if keys != MARKER_ENVIRONMENT_KEYS:
        raise ValueError(
            "marker_environment_v1 鍵集合跟 packaging.markers.default_environment()"
            f" 凍結的 11 個鍵不符:缺 {sorted(MARKER_ENVIRONMENT_KEYS - keys)},"
            f" 多 {sorted(keys - MARKER_ENVIRONMENT_KEYS)}"
        )
    for key, value in marker_environment_v1.items():
        if not isinstance(value, str):
            raise ValueError(
                f"marker_environment_v1[{key!r}] 必須是字串,實際是"
                f" {type(value).__name__}:{value!r}"
            )
    return sha256_hex(canonical_json_bytes(marker_environment_v1, sort_keys=True))


# runtime_environment_source 的 schema/version tag,固定放陣列第一個元素
# (預註冊文件 §C.1「跟 §C.9 dedup_key 同一套 canonical 序列化紀律」段)。
RUNTIME_ENVIRONMENT_SCHEMA_TAG = "runtime_environment_identity_v1"
# 第 21 輪凍結的固定欄位順序(14 個元素,含開頭的 schema tag)。
RUNTIME_ENVIRONMENT_SOURCE_FIELDS = (
    "schema_tag",
    "python_implementation",
    "python_version_full",
    "os_system",
    "os_release",
    "machine_arch",
    "pandas_version",
    "numpy_version",
    "pyarrow_version",
    "openpyxl_version",
    "parquet_engine",
    "excel_engine",
    "dependency_lock_identity",
    "marker_environment_identity_v1",
)


def build_runtime_environment_source(
    *,
    python_implementation: str,
    python_version_full: str,
    os_system: str,
    os_release: str,
    machine_arch: str,
    pandas_version: str,
    numpy_version: str,
    pyarrow_version: str,
    openpyxl_version: str,
    dependency_lock_identity: str,
    marker_environment_identity_v1_value: str,
    parquet_engine: str = "pyarrow",
    excel_engine: str = "openpyxl",
) -> list:
    """依預註冊文件 §C.1 固定的 14 元素順序組裝 runtime_environment_source
    陣列(不含 schema tag 以外任何自行決定的順序)。`parquet_engine`/
    `excel_engine` 是文件凍結的字面常數,預設值即凍結值,呼叫端若傳入別的
    值視同刻意替換(用於「substitution 造成身分改變」的測試)。"""
    for name, value in [
        ("python_implementation", python_implementation),
        ("python_version_full", python_version_full),
        ("os_system", os_system),
        ("os_release", os_release),
        ("machine_arch", machine_arch),
        ("pandas_version", pandas_version),
        ("numpy_version", numpy_version),
        ("pyarrow_version", pyarrow_version),
        ("openpyxl_version", openpyxl_version),
        ("parquet_engine", parquet_engine),
        ("excel_engine", excel_engine),
    ]:
        _require_str(name, value)
    _require_sha256_hex("dependency_lock_identity", dependency_lock_identity)
    _require_sha256_hex(
        "marker_environment_identity_v1", marker_environment_identity_v1_value
    )
    return [
        RUNTIME_ENVIRONMENT_SCHEMA_TAG,
        python_implementation,
        python_version_full,
        os_system,
        os_release,
        machine_arch,
        pandas_version,
        numpy_version,
        pyarrow_version,
        openpyxl_version,
        parquet_engine,
        excel_engine,
        dependency_lock_identity,
        marker_environment_identity_v1_value,
    ]


def runtime_environment_identity_v1(runtime_environment_source: list) -> str:
    """預註冊文件 §C.1 runtime_environment_identity_v1 canonical 序列化 +
    雜湊。長度必須恰好 14、第一個元素必須是固定 schema tag、任何元素為
    `None` 直接 fail-closed(文件明講「這種情況本身要另外 fail-closed」,
    不是序列化成 JSON null 後放行)。"""
    if not isinstance(runtime_environment_source, list):
        raise TypeError(
            "runtime_environment_source must be a list, got"
            f" {type(runtime_environment_source).__name__}"
        )
    if len(runtime_environment_source) != len(RUNTIME_ENVIRONMENT_SOURCE_FIELDS):
        raise ValueError(
            "runtime_environment_source 必須恰好"
            f" {len(RUNTIME_ENVIRONMENT_SOURCE_FIELDS)} 個元素,實際"
            f" {len(runtime_environment_source)}"
        )
    if runtime_environment_source[0] != RUNTIME_ENVIRONMENT_SCHEMA_TAG:
        raise ValueError(
            f"runtime_environment_source[0] 必須是固定 schema tag"
            f" {RUNTIME_ENVIRONMENT_SCHEMA_TAG!r},實際"
            f" {runtime_environment_source[0]!r}"
        )
    for field_name, value in zip(
        RUNTIME_ENVIRONMENT_SOURCE_FIELDS, runtime_environment_source
    ):
        if value is None:
            raise ValueError(
                f"runtime_environment_source[{field_name}] 是 None——依預註冊"
                " 文件 §C.1,任何欄位真的無法取得時必須 fail-closed,不能"
                " 序列化成 JSON null 後繼續"
            )
    return sha256_hex(
        canonical_json_bytes(runtime_environment_source, sort_keys=False)
    )


def environment_creation_identity(environment_creation_receipt: dict) -> str:
    """預註冊文件 §C.5 `environment_creation_identity` 公式:對
    `environment_creation_receipt_v1` 的所有欄位做 canonical 序列化,**排除
    `environment_creation_identity` 這個欄位自己**(它在雜湊計算當下根本
    還不存在),`sort_keys=True`。呼叫端傳進來的 dict 若已經含有這個欄位
    (例如重算驗證時),這裡會先排除掉再算,不會遞迴污染。"""
    if not isinstance(environment_creation_receipt, dict):
        raise TypeError(
            "environment_creation_receipt must be a dict, got"
            f" {type(environment_creation_receipt).__name__}"
        )
    payload_obj = {
        k: v
        for k, v in environment_creation_receipt.items()
        if k != "environment_creation_identity"
    }
    return sha256_hex(canonical_json_bytes(payload_obj, sort_keys=True))


# ----------------------------------------------------------------------------
# 5. 嚴格的 candidate-path 身分守衛——預註冊文件 §C.4。
#    只接受注入的 candidate_base/snapshot_id_v1/run_id/protected_paths,
#    不讀 tej_importer.TEJ_CACHE_DIR 之類的模組層級全域值,也**不建立任何
#    目錄**(本輪只驗證、回傳解析過的路徑)。
# ----------------------------------------------------------------------------


def guard_candidate_output_dir(
    candidate_base,
    snapshot_id_v1_value: str,
    run_id: str,
    *,
    protected_paths=(),
) -> Path:
    """驗證 `<candidate_base>/<snapshot_id_v1>/<run_id>` 這個輸出路徑合法
    (預註冊文件 §C.4)。回傳解析過的絕對路徑,**不建立目錄**。

    Fail-closed 條件(逐一對應 §C.4):
    - `snapshot_id_v1_value` 不是完整 64 碼小寫十六進位(含截斷、大寫、
      非十六進位字元)。
    - `run_id` 是空字串、含路徑分隔符號、或是 `.`/`..`。
    - 解析後(跟隨符號連結/reparse point 之後)的真實路徑不等於
      `<候選 candidate_base 的真實路徑>/<snapshot_id_v1>/<run_id>`
      這個字面路徑——涵蓋任何一層symlink/reparse 逃逸、`..` 穿越。
    - 目標路徑已存在但不是目錄(既有非預期的路徑型別)。
    - 目標路徑跟任一個注入的 `protected_paths` 相等、是其子路徑,或反過來
      `protected_paths` 是目標路徑的子路徑(雙向重疊都擋)。
    """
    if not isinstance(snapshot_id_v1_value, str) or not _HEX64_RE.match(
        snapshot_id_v1_value
    ):
        raise ValueError(
            "snapshot_id_v1 必須是完整 64 碼小寫十六進位字串,不接受截斷/大寫/"
            f"非十六進位字元,收到 {snapshot_id_v1_value!r}"
        )
    if (
        not isinstance(run_id, str)
        or run_id == ""
        or run_id in (".", "..")
        or "/" in run_id
        or "\\" in run_id
        or "\x00" in run_id
    ):
        raise ValueError(f"run_id 不合法(空字串/路徑分隔符號/`.`/`..`):{run_id!r}")

    candidate_base = Path(candidate_base)
    if not candidate_base.is_dir():
        raise ValueError(
            f"candidate_base 不存在或不是目錄(必須是呼叫端已經準備好的隔離"
            f" 根目錄):{candidate_base}"
        )
    candidate_base_real = candidate_base.resolve(strict=True)

    target = candidate_base / snapshot_id_v1_value / run_id
    expected = candidate_base_real / snapshot_id_v1_value / run_id
    target_resolved = target.resolve(strict=False)

    if target_resolved != expected:
        raise ValueError(
            "candidate 輸出路徑解析後不等於預期的字面路徑——可能是 symlink/"
            f"reparse point 逃逸或 `..` 穿越:resolved={target_resolved}"
            f" expected={expected}"
        )
    # target_resolved == expected == candidate_base_real / snapshot / run_id
    # 這個等式本身已經保證 target_resolved 在 candidate_base_real 底下,
    # 不需要再另外呼叫一次 is_relative_to。
    if target_resolved.exists() and not target_resolved.is_dir():
        raise ValueError(
            f"candidate 輸出路徑已存在,但不是目錄(既有非預期路徑型別):"
            f" {target_resolved}"
        )

    for raw_protected in protected_paths:
        protected = Path(raw_protected).resolve(strict=False)
        if (
            target_resolved == protected
            or target_resolved.is_relative_to(protected)
            or protected.is_relative_to(target_resolved)
        ):
            raise ValueError(
                f"candidate 輸出路徑 {target_resolved} 跟保護路徑 {protected}"
                " 重疊(相等、是其子路徑,或反過來)"
            )

    return target_resolved


# ----------------------------------------------------------------------------
# 6. Receipt schema validators/builders——僅限 environment-creation +
#    頂層身分欄位(預註冊文件 §C.5)。全部回傳/接受記憶體內 dict,本輪不寫
#    檔、不建立 run 目錄。
# ----------------------------------------------------------------------------

TOP_LEVEL_IDENTITY_FIELDS = (
    "manifest_identity",
    "manifest_sha256_file_identity",
    "supplement_identity",
    "importer_identity",
    "extractor_identity",
    "builder_identity",
    "dependency_lock_identity",
    "runtime_environment_identity_v1",
    "preregistration_commit",
    "candidate_schema_version",
    "source_data_identity",
    "build_implementation_identity",
    "snapshot_id_v1",
)


def build_top_level_identity_fields(
    *,
    manifest_identity: str,
    manifest_sha256_file_identity: str,
    supplement_identity: str,
    importer_identity: str,
    extractor_identity: str,
    builder_identity: str,
    dependency_lock_identity: str,
    runtime_environment_identity_v1_value: str,
    preregistration_commit: str,
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION,
) -> dict:
    """組出彙總 build receipt 頂層要記的身分欄位(§C.1「PASS 證據」段:
    `snapshot_id_v1` 連同三層中間值 + 全部輸入雜湊一起記錄)。"""
    sdi = source_data_identity(
        manifest_identity, manifest_sha256_file_identity, supplement_identity
    )
    bii = build_implementation_identity(
        importer_identity,
        extractor_identity,
        builder_identity,
        dependency_lock_identity,
        runtime_environment_identity_v1_value,
        preregistration_commit,
        candidate_schema_version,
    )
    sid = snapshot_id_v1(sdi, bii)
    return {
        "manifest_identity": manifest_identity,
        "manifest_sha256_file_identity": manifest_sha256_file_identity,
        "supplement_identity": supplement_identity,
        "importer_identity": importer_identity,
        "extractor_identity": extractor_identity,
        "builder_identity": builder_identity,
        "dependency_lock_identity": dependency_lock_identity,
        "runtime_environment_identity_v1": runtime_environment_identity_v1_value,
        "preregistration_commit": preregistration_commit,
        "candidate_schema_version": candidate_schema_version,
        "source_data_identity": sdi,
        "build_implementation_identity": bii,
        "snapshot_id_v1": sid,
    }


def validate_top_level_identity_fields(fields: dict) -> None:
    """獨立重算 §C.1 三層組合公式,核對是否等於 `fields` 裡記錄的值。用於
    (未來)verifier 或本輪測試核對 `build_top_level_identity_fields` 的
    輸出內部自洽。鍵集合不符、任何欄位缺席/substituted 都直接 raise。"""
    if not isinstance(fields, dict):
        raise TypeError(f"fields must be a dict, got {type(fields).__name__}")
    keys = set(fields)
    expected_keys = set(TOP_LEVEL_IDENTITY_FIELDS)
    if keys != expected_keys:
        raise ValueError(
            "top-level identity fields 鍵集合不符:缺"
            f" {sorted(expected_keys - keys)},多 {sorted(keys - expected_keys)}"
        )
    recomputed_sdi = source_data_identity(
        fields["manifest_identity"],
        fields["manifest_sha256_file_identity"],
        fields["supplement_identity"],
    )
    if recomputed_sdi != fields["source_data_identity"]:
        raise ValueError(
            "source_data_identity 跟從其輸入重算的結果不符——"
            f"記錄值={fields['source_data_identity']!r} 重算值={recomputed_sdi!r}"
        )
    recomputed_bii = build_implementation_identity(
        fields["importer_identity"],
        fields["extractor_identity"],
        fields["builder_identity"],
        fields["dependency_lock_identity"],
        fields["runtime_environment_identity_v1"],
        fields["preregistration_commit"],
        fields["candidate_schema_version"],
    )
    if recomputed_bii != fields["build_implementation_identity"]:
        raise ValueError(
            "build_implementation_identity 跟從其輸入重算的結果不符——"
            f"記錄值={fields['build_implementation_identity']!r}"
            f" 重算值={recomputed_bii!r}"
        )
    recomputed_sid = snapshot_id_v1(recomputed_sdi, recomputed_bii)
    if recomputed_sid != fields["snapshot_id_v1"]:
        raise ValueError(
            "snapshot_id_v1 跟從其輸入重算的結果不符——"
            f"記錄值={fields['snapshot_id_v1']!r} 重算值={recomputed_sid!r}"
        )


# environment_creation_receipt_v1 精確 schema(預註冊文件 §C.5)。
ENVIRONMENT_CREATION_SCHEMA_TAG = "environment_creation_receipt_v1"
ENVIRONMENT_CREATION_RECEIPT_FIELDS = (
    "schema",
    "run_id",
    "preregistration_commit",
    "lock_path",
    "lock_sha256",
    "marker_environment_v1",
    "marker_environment_identity_v1",
    "installer_identity",
    "bootstrap_tool_inventory",
    "install_command",
    "start_timestamp_utc",
    "end_timestamp_utc",
    "exit_code",
    "installer_report_artifact_hashes",
    "stdout_log_sha256",
    "stderr_log_sha256",
    "lock_selected_inventory",
    "lock_selected_inventory_sha256",
    "installed_inventory",
    "installed_inventory_sha256",
    "equality_result",
)


def _require_name_value_pair_list(name: str, value) -> list:
    """§C.5 的 inventory 陣列(`bootstrap_tool_inventory`/
    `lock_selected_inventory`/`installed_inventory`)固定是
    `[[正規化套件名, 版本], ...]`——每個元素恰好是 2 個字串組成的
    list/tuple。拒絕扁平字串、錯誤長度的 pair、非字串成員(no silent
    coercion)。**這裡只做形狀檢查**——不驗證名稱是否已經正規化、清單是否
    已排序、名稱是否重複;那是 `_require_canonical_normalized_pair_list`
    (下面)的職責,Codex review 指出「只做形狀檢查」本身不足以擋住
    non-canonical/unsorted 的 receipt evidence,見那支函式的 docstring。"""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list, got {type(value).__name__}: {value!r}")
    for i, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(
                f"{name}[{i}] must be a 2-element [name, version] pair, got {item!r}"
            )
        pkg_name, pkg_version = item
        if not isinstance(pkg_name, str) or not isinstance(pkg_version, str):
            raise ValueError(f"{name}[{i}] pair members must both be str, got {item!r}")
    return value


def _require_canonical_normalized_pair_list(name: str, value) -> list:
    """**Phase A3c blocking-fix(Codex review)**:receipt evidence(`bootstrap_
    tool_inventory`/`lock_selected_inventory`/`installed_inventory`)宣稱
    自己已經是 canonical inventory——這支函式驗證它**真的是**,不是只驗證
    形狀。**不會**幫忙正規化、排序、去重——任何不合格直接 raise,不悄悄
    改寫已經被呈現為 canonical 的 receipt 內容(呼叫端要正規化/排序原始
    觀測值,請用 `canonicalize_and_partition_installed_inventory` 這種獨立
    的「raw-input canonicalizer」,那支函式才允許接受別名/任意來源順序)。

    Fail-closed 條件(在 `_require_name_value_pair_list` 的形狀檢查之上,
    逐一疊加):
    - 任何 `pkg_name`/`pkg_version` 是空字串。
    - `pkg_name` 不是**已經**正規化過的 PEP 503 字面值(`normalize_package_
      name(pkg_name) != pkg_name`)。
    - 同一個正規化名稱出現超過一列(一個名稱只能有一列)。
    - 整份清單沒有依 `(normalized_name, version)` 字典序排序。
    """
    _require_name_value_pair_list(name, value)
    seen_names = set()
    for i, (pkg_name, pkg_version) in enumerate(value):
        if pkg_name == "" or pkg_version == "":
            raise ValueError(
                f"{name}[{i}] must be a pair of two non-empty str, got"
                f" {[pkg_name, pkg_version]!r}"
            )
        if normalize_package_name(pkg_name) != pkg_name:
            raise ValueError(
                f"{name}[{i}] package name is not already PEP 503-normalized:"
                f" {pkg_name!r} (normalized form is"
                f" {normalize_package_name(pkg_name)!r}); receipt evidence must"
                " already be canonical, this function does not rewrite it"
            )
        if pkg_name in seen_names:
            raise ValueError(
                f"{name} contains more than one row for the normalized package"
                f" name {pkg_name!r} (row {i}); one name may have exactly one row"
            )
        seen_names.add(pkg_name)
    normalized_list = [list(item) for item in value]
    if normalized_list != sorted(normalized_list, key=lambda pair: (pair[0], pair[1])):
        raise ValueError(
            f"{name} is not sorted lexicographically by (normalized_name,"
            f" version): {value!r}"
        )
    return value


def _require_canonical_bootstrap_tool_inventory(value) -> list:
    """`bootstrap_tool_inventory` 額外規則(Codex review):在
    `_require_canonical_normalized_pair_list` 之上,每一列的正規化名稱都
    必須屬於 `BOOTSTRAP_TOOL_NORMALIZED_NAMES`(`pip`/`setuptools`/
    `wheel`)——present subset 允許(3 個都在、只有部分、甚至一個都沒有都
    合法),但**不允許任何不在這 3 個裡的名稱被藏進這個欄位**(那樣會讓
    這個名稱既不出現在 `installed_inventory` 也不出現在
    `bootstrap_tool_inventory` 該有的驗證裡,變相逃過對帳)。"""
    _require_canonical_normalized_pair_list("bootstrap_tool_inventory", value)
    for i, (pkg_name, _pkg_version) in enumerate(value):
        if pkg_name not in BOOTSTRAP_TOOL_NORMALIZED_NAMES:
            raise ValueError(
                f"bootstrap_tool_inventory[{i}] name {pkg_name!r} is not one of"
                f" the frozen bootstrap tools {sorted(BOOTSTRAP_TOOL_NORMALIZED_NAMES)}"
            )
    return value


def _require_canonical_installed_inventory(value) -> list:
    """`installed_inventory` 額外規則(Codex review):在
    `_require_canonical_normalized_pair_list` 之上,**不允許**任何一列的
    正規化名稱屬於 `BOOTSTRAP_TOOL_NORMALIZED_NAMES`——bootstrap 工具只能
    記在 `bootstrap_tool_inventory`,不能同時(或改成)藏在
    `installed_inventory` 裡,否則 lock-selected vs installed 的對帳範圍
    會被悄悄污染。"""
    _require_canonical_normalized_pair_list("installed_inventory", value)
    for i, (pkg_name, _pkg_version) in enumerate(value):
        if pkg_name in BOOTSTRAP_TOOL_NORMALIZED_NAMES:
            raise ValueError(
                f"installed_inventory[{i}] name {pkg_name!r} is a bootstrap tool"
                " and must not appear in installed_inventory (it belongs in"
                " bootstrap_tool_inventory instead)"
            )
    return value


def _require_installer_report_artifact_hashes(value):
    """§C.5:「若安裝工具的報告機制...有提供逐套件安裝檔案雜湊,原樣記錄;
    沒有這個機制就明確填 JSON null,不是省略欄位」——`None` 永遠合法。

    **byte-level ambiguity note(不是凍結公式,是本輪的最小合理 schema
    選擇)**:frozen 文件沒有把非 null 時每個項目的內部欄位順序/型別寫到
    位元組層級。這裡採用跟同一份 receipt 裡其他 inventory 陣列一致的
    `[[正規化套件名, sha256], ...]` pair 慣例,只用來擋住明顯錯誤的型別
    (裸字串/物件/非 hex 雜湊)——如果之後這個欄位有更精確的凍結定義,
    要以那個定義為準,不是這裡的選擇。"""
    if value is None:
        return value
    if not isinstance(value, list):
        raise ValueError(
            "installer_report_artifact_hashes must be JSON null or a list,"
            f" got {type(value).__name__}: {value!r}"
        )
    for i, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(
                f"installer_report_artifact_hashes[{i}] must be a 2-element"
                f" [package_name, sha256] pair, got {item!r}"
            )
        pkg_name, pkg_hash = item
        if not isinstance(pkg_name, str) or not isinstance(pkg_hash, str) or not _HEX64_RE.match(pkg_hash):
            raise ValueError(
                f"installer_report_artifact_hashes[{i}] must be"
                f" [str, 64-lowercase-hex-sha256], got {item!r}"
            )
    return value


# A3c 凍結的單筆 discrepancy 物件 shape(`reconcile_lock_selected_vs_
# installed_inventory` 的輸出格式)——`_require_equality_result` 用它逐筆
# 驗證,不再把 `discrepancies` 當成「任意內容的 list」放行。
_DISCREPANCY_TYPES = frozenset({"missing", "unexpected", "version_mismatch"})
_DISCREPANCY_OBJECT_KEYS = frozenset(
    {"type", "normalized_name", "expected_version", "actual_version"}
)


def _require_discrepancy_object(index: int, value) -> dict:
    """驗證 `equality_result['discrepancies']` 裡單一筆物件的 shape(Codex
    review 新增——原本 `_require_equality_result` 只驗證 `discrepancies` 是
    list,完全不檢查裡面每一項的內容,任意字串/物件都會被放行)。

    精確鍵集合恰好 `{type, normalized_name, expected_version,
    actual_version}`;`type` 只能是 `missing`/`unexpected`/
    `version_mismatch` 三者之一;`normalized_name` 必須是非空字串;
    `expected_version`/`actual_version` 的 `None`-ness 必須跟 `type` 對應
    (`missing` 沒有 `actual_version`、`unexpected` 沒有
    `expected_version`、`version_mismatch` 兩者都要有非空字串**且不相等**
    ——版本字串相等就不構成 mismatch,不該被記成一筆 discrepancy)。"""
    if not isinstance(value, dict) or set(value) != _DISCREPANCY_OBJECT_KEYS:
        raise ValueError(
            f"discrepancies[{index}] must be a dict with exactly the keys"
            f" {sorted(_DISCREPANCY_OBJECT_KEYS)}, got {value!r}"
        )
    if value["type"] not in _DISCREPANCY_TYPES:
        raise ValueError(
            f"discrepancies[{index}]['type'] must be one of"
            f" {sorted(_DISCREPANCY_TYPES)}, got {value['type']!r}"
        )
    normalized_name = value["normalized_name"]
    if not isinstance(normalized_name, str) or normalized_name == "":
        raise ValueError(
            f"discrepancies[{index}]['normalized_name'] must be a non-empty"
            f" str, got {normalized_name!r}"
        )
    expected_version = value["expected_version"]
    actual_version = value["actual_version"]
    disc_type = value["type"]
    if disc_type == "missing":
        ok = (
            isinstance(expected_version, str)
            and expected_version != ""
            and actual_version is None
        )
    elif disc_type == "unexpected":
        ok = (
            expected_version is None
            and isinstance(actual_version, str)
            and actual_version != ""
        )
    else:  # version_mismatch
        ok = (
            isinstance(expected_version, str)
            and expected_version != ""
            and isinstance(actual_version, str)
            and actual_version != ""
            and expected_version != actual_version
        )
    if not ok:
        raise ValueError(
            f"discrepancies[{index}] with type={disc_type!r} has an"
            " expected_version/actual_version combination inconsistent with"
            f" that type: {value!r}"
        )
    return value


def _require_equality_result(value) -> dict:
    """§C.5:`equality_result` 固定是 `{"equal": true_or_false,
    "discrepancies": [...]}`——鍵集合恰好這兩個,`equal` 必須是真正的
    `bool`(不接受 `"yes"`/`1`/`"true"` 這類 truthy 替代品——`isinstance(1,
    bool)` 是 `False`,`bool` 是 `int` 的子類別但反過來不成立,這裡刻意用
    `isinstance(..., bool)` 擋掉整數/字串偽裝),`discrepancies` 必須是
    list。

    **Phase A3c blocking-fix(Codex review 抓到的三個 fail-closed 繞過之
    一)**:原本這裡只驗證 `discrepancies` 是不是 list,完全不檢查內容,
    所以 `{"equal": True, "discrepancies": ["contradiction"]}` 這種
    「宣稱相符卻附上矛盾證據」的組合會被放行。現在額外強制:
    1. `discrepancies` 每一筆都必須符合 `_require_discrepancy_object` 的
       A3c 凍結 shape。
    2. 不能有重複的 `(type, normalized_name)` 身分(同一個名稱同一種矛盾
       類型只能出現一次)。
    3. 必須依 `(type, normalized_name)` 字典序排序。
    4. `equal is True` **若且唯若** `discrepancies == []`——`True` +
       非空清單、`False` + 空清單都直接 raise,兩者都是自相矛盾的證據。
    """
    if not isinstance(value, dict) or set(value) != {"equal", "discrepancies"}:
        raise ValueError(
            "equality_result must be a dict with exactly the keys"
            f" {{'equal', 'discrepancies'}}, got {value!r}"
        )
    if not isinstance(value["equal"], bool):
        raise ValueError(
            "equality_result['equal'] must be a real bool (True/False), not"
            f" {type(value['equal']).__name__}: {value['equal']!r}"
        )
    if not isinstance(value["discrepancies"], list):
        raise ValueError(
            "equality_result['discrepancies'] must be a list, got"
            f" {type(value['discrepancies']).__name__}: {value['discrepancies']!r}"
        )
    discrepancies = [
        _require_discrepancy_object(i, item)
        for i, item in enumerate(value["discrepancies"])
    ]
    identities = [(d["type"], d["normalized_name"]) for d in discrepancies]
    if len(set(identities)) != len(identities):
        raise ValueError(
            "equality_result['discrepancies'] has a duplicate (type,"
            f" normalized_name) identity, semantically ambiguous: {value!r}"
        )
    if identities != sorted(identities):
        raise ValueError(
            "equality_result['discrepancies'] must be sorted by (type,"
            f" normalized_name), got: {value!r}"
        )
    if value["equal"] is True and discrepancies:
        raise ValueError(
            "equality_result['equal'] is True but discrepancies is"
            " non-empty — self-contradictory (equal must be True iff"
            f" discrepancies == []): {value!r}"
        )
    if value["equal"] is False and not discrepancies:
        raise ValueError(
            "equality_result['equal'] is False but discrepancies is empty —"
            " self-contradictory (no evidence of any mismatch was given):"
            f" {value!r}"
        )
    return value


def _require_install_command(value) -> list:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"install_command must be a list of str, got {value!r}")
    return value


def _require_install_command_has_hash_verification_evidence(install_command: list) -> None:
    """§C.5 fail-closed 條件:「`install_command` 裡沒有出現 hash 校驗證據
    (例如 `--require-hashes` 或等價旗標)」——frozen 文件只給了
    `--require-hashes` 這一個具體例子,沒有窮舉「等價旗標」的清單,這裡只
    檢查這個明確給出的字面例子,不是自行發明其他等價寫法。"""
    if not any("--require-hashes" in arg for arg in install_command):
        raise ValueError(
            "install_command 必須含明確的 hash 校驗證據(例如"
            " --require-hashes),繼續往下解析候選資料之前必須 fail-closed;"
            f" 目前的 install_command={install_command!r}"
        )


def build_environment_creation_receipt(
    *,
    run_id: str,
    preregistration_commit: str,
    lock_path: str,
    lock_sha256: str,
    marker_environment_v1: dict,
    installer_identity: str,
    bootstrap_tool_inventory: list,
    install_command: list,
    start_timestamp_utc: str,
    end_timestamp_utc: str,
    exit_code: int,
    installer_report_artifact_hashes,
    stdout_log_sha256: str,
    stderr_log_sha256: str,
    lock_selected_inventory: list,
    lock_selected_inventory_sha256: str,
    installed_inventory: list,
    installed_inventory_sha256: str,
    equality_result: dict,
) -> dict:
    """組出 `environment_creation_receipt_v1`(預註冊文件 §C.5),回傳
    記憶體內 dict(含已計算好的 `environment_creation_identity`)。**不寫
    檔**——排他建立/寫入 JSON 是 Phase B 執行時才做的事,本輪不做。

    這支函式保證**結構/型別正確且自洽**(拒絕錯誤型別、malformed shape、
    非 canonical 的 inventory 陣列、inventory 陣列跟其宣稱雜湊不一致、
    `equality_result` 跟從 inventory 獨立重算的 reconcile 結果不一致)——
    它**允許**組出一份記錄「環境建立失敗」的合法診斷 receipt(例如
    `exit_code != 0` 或 `equality_result.equal is False`,只要
    `equality_result` **忠實**反映兩份 inventory 的實際內容,兩者都是
    `environment_creation_receipt_v1` schema 裡型別正確且自洽的合法值,
    不是 malformed)。§C.5「繼續往下解析候選資料之前」的 fail-closed 判定
    (`exit_code` 必須是 `0`、`equality_result.equal` 必須是 `True`、
    `install_command` 必須含 hash 校驗證據)是
    `validate_environment_creation_receipt()` 的職責,不是這支函式的職責
    ——那個判定必須在 Phase B 真的往下解析之前擋下來,而不是讓「不能組出
    失敗記錄」這件事本身變成一種變相的資料遺失。"""
    _require_str("run_id", run_id)
    _require_str("preregistration_commit", preregistration_commit)
    _require_str("lock_path", lock_path)
    _require_sha256_hex("lock_sha256", lock_sha256)
    marker_identity = marker_environment_identity_v1(marker_environment_v1)
    _require_str("installer_identity", installer_identity)
    _require_str("start_timestamp_utc", start_timestamp_utc)
    _require_str("end_timestamp_utc", end_timestamp_utc)
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise ValueError(f"exit_code must be an int, got {exit_code!r}")
    _require_sha256_hex("stdout_log_sha256", stdout_log_sha256)
    _require_sha256_hex("stderr_log_sha256", stderr_log_sha256)
    _require_sha256_hex(
        "lock_selected_inventory_sha256", lock_selected_inventory_sha256
    )
    _require_sha256_hex("installed_inventory_sha256", installed_inventory_sha256)
    _require_install_command(install_command)
    _require_canonical_bootstrap_tool_inventory(bootstrap_tool_inventory)
    _require_canonical_normalized_pair_list(
        "lock_selected_inventory", lock_selected_inventory
    )
    _require_canonical_installed_inventory(installed_inventory)
    _require_installer_report_artifact_hashes(installer_report_artifact_hashes)
    equality_result = _require_equality_result(equality_result)

    recomputed_lock_selected_sha256 = sha256_hex(
        canonical_json_bytes(lock_selected_inventory, sort_keys=False)
    )
    if recomputed_lock_selected_sha256 != lock_selected_inventory_sha256:
        raise ValueError(
            "lock_selected_inventory_sha256 跟從 lock_selected_inventory"
            f" canonical 序列化重算的結果不符:傳入值="
            f"{lock_selected_inventory_sha256!r} 重算值="
            f"{recomputed_lock_selected_sha256!r}"
        )
    recomputed_installed_sha256 = sha256_hex(
        canonical_json_bytes(installed_inventory, sort_keys=False)
    )
    if recomputed_installed_sha256 != installed_inventory_sha256:
        raise ValueError(
            "installed_inventory_sha256 跟從 installed_inventory canonical"
            f" 序列化重算的結果不符:傳入值={installed_inventory_sha256!r}"
            f" 重算值={recomputed_installed_sha256!r}"
        )

    # **Phase A3c blocking-fix(Codex review 抓到的第三個繞過)**:
    # `equality_result` 必須跟從這兩份 inventory 獨立重算的 reconcile 結果
    # 完全一致——不能是任意編造的值。這**不是**禁止記錄「環境建立失敗」
    # (`equal=False` 本身依然是合法的診斷值,見本函式 docstring),而是
    # 禁止記錄一個**不忠實**的 `equal`/`discrepancies`(例如兩份 inventory
    # 明明相符卻宣稱 `equal=False`,或反過來)。
    recomputed_equality_result = reconcile_lock_selected_vs_installed_inventory(
        lock_selected_inventory, installed_inventory
    )
    if recomputed_equality_result != equality_result:
        raise ValueError(
            "equality_result 跟從 lock_selected_inventory/installed_inventory"
            " 獨立重算 reconcile 的結果不符,不能記錄一份跟實際 inventory"
            f" 內容不一致的對帳證據:傳入值={equality_result!r} 重算值="
            f"{recomputed_equality_result!r}"
        )

    receipt = {
        "schema": ENVIRONMENT_CREATION_SCHEMA_TAG,
        "run_id": run_id,
        "preregistration_commit": preregistration_commit,
        "lock_path": lock_path,
        "lock_sha256": lock_sha256,
        "marker_environment_v1": marker_environment_v1,
        "marker_environment_identity_v1": marker_identity,
        "installer_identity": installer_identity,
        "bootstrap_tool_inventory": bootstrap_tool_inventory,
        "install_command": install_command,
        "start_timestamp_utc": start_timestamp_utc,
        "end_timestamp_utc": end_timestamp_utc,
        "exit_code": exit_code,
        "installer_report_artifact_hashes": installer_report_artifact_hashes,
        "stdout_log_sha256": stdout_log_sha256,
        "stderr_log_sha256": stderr_log_sha256,
        "lock_selected_inventory": lock_selected_inventory,
        "lock_selected_inventory_sha256": lock_selected_inventory_sha256,
        "installed_inventory": installed_inventory,
        "installed_inventory_sha256": installed_inventory_sha256,
        "equality_result": equality_result,
    }
    receipt["environment_creation_identity"] = environment_creation_identity(receipt)
    return receipt


def validate_environment_creation_receipt(receipt: dict) -> None:
    """驗證一份 `environment_creation_receipt_v1` dict——這是 §C.5「繼續
    往下解析候選資料之前」必須通過的 gate,**不是**單純的結構檢查函式。
    分兩段:

    1. 結構/自洽性重算:欄位集合必須恰好等於凍結 schema 加上
       `environment_creation_identity` 本身、`schema` 標籤必須正確、
       每個欄位的型別/shape 符合 §C.5(inventory 陣列必須已經是 canonical
       ——已正規化、已排序、無重複名稱,`bootstrap_tool_inventory`/
       `installed_inventory` 各自的名稱範圍規則,見
       `_require_canonical_bootstrap_tool_inventory`/`_require_canonical_
       installed_inventory`;`installer_report_artifact_hashes`、
       `equality_result` 的鍵集合、`equal` 必須是真正的
       `bool`、`discrepancies` 每一筆的 shape、`equal` 與 `discrepancies`
       的邏輯一致性,見 `_require_equality_result`)、
       `marker_environment_identity_v1`/`lock_selected_inventory_sha256`/
       `installed_inventory_sha256`/**`equality_result`(跟從
       `lock_selected_inventory`/`installed_inventory` 獨立重算的
       `reconcile_lock_selected_vs_installed_inventory` 結果比對,Phase
       A3c blocking-fix)**/`environment_creation_identity` 全部都必須跟
       獨立重算的結果一致。
    2. §C.5 fail-closed 條件(**這是原本這支函式漏掉的部分**——Codex 的
       probe 證實只做第 1 段不足以擋住「型別正確但語意上不該放行」的
       receipt,例如 `exit_code=1`/`equality_result.equal=False`/
       `install_command` 缺 `--require-hashes`):`exit_code` 必須是
       `0`、`equality_result.equal` 必須「是」`True`(不是 truthy,是
       `is True`)、`install_command` 必須含明確的 hash 校驗證據。任一項
       不成立就直接 raise,不放行。

    第 1 段允許的失敗態(型別正確、只是記錄了一次失敗的環境建立嘗試)在
    第 2 段一定會被擋下來——`build_environment_creation_receipt()` 的
    docstring 有講這個職責劃分。"""
    if not isinstance(receipt, dict):
        raise TypeError(f"receipt must be a dict, got {type(receipt).__name__}")
    expected_keys = set(ENVIRONMENT_CREATION_RECEIPT_FIELDS) | {
        "environment_creation_identity"
    }
    keys = set(receipt)
    if keys != expected_keys:
        raise ValueError(
            "environment_creation_receipt_v1 欄位集合不符:缺"
            f" {sorted(expected_keys - keys)},多 {sorted(keys - expected_keys)}"
        )
    if receipt["schema"] != ENVIRONMENT_CREATION_SCHEMA_TAG:
        raise ValueError(
            f"schema 必須是 {ENVIRONMENT_CREATION_SCHEMA_TAG!r},實際"
            f" {receipt['schema']!r}"
        )
    recomputed_marker_identity = marker_environment_identity_v1(
        receipt["marker_environment_v1"]
    )
    if recomputed_marker_identity != receipt["marker_environment_identity_v1"]:
        raise ValueError(
            "marker_environment_identity_v1 跟從 marker_environment_v1 重算的"
            f" 結果不符:記錄值={receipt['marker_environment_identity_v1']!r}"
            f" 重算值={recomputed_marker_identity!r}"
        )

    _require_canonical_bootstrap_tool_inventory(receipt["bootstrap_tool_inventory"])
    _require_canonical_normalized_pair_list(
        "lock_selected_inventory", receipt["lock_selected_inventory"]
    )
    _require_canonical_installed_inventory(receipt["installed_inventory"])
    _require_installer_report_artifact_hashes(
        receipt["installer_report_artifact_hashes"]
    )
    equality_result = _require_equality_result(receipt["equality_result"])
    install_command = _require_install_command(receipt["install_command"])
    if not isinstance(receipt["exit_code"], int) or isinstance(receipt["exit_code"], bool):
        raise ValueError(f"exit_code must be an int, got {receipt['exit_code']!r}")

    recomputed_lock_selected_sha256 = sha256_hex(
        canonical_json_bytes(receipt["lock_selected_inventory"], sort_keys=False)
    )
    if recomputed_lock_selected_sha256 != receipt["lock_selected_inventory_sha256"]:
        raise ValueError(
            "lock_selected_inventory_sha256 跟從 lock_selected_inventory"
            f" canonical 序列化重算的結果不符:記錄值="
            f"{receipt['lock_selected_inventory_sha256']!r} 重算值="
            f"{recomputed_lock_selected_sha256!r}"
        )
    recomputed_installed_sha256 = sha256_hex(
        canonical_json_bytes(receipt["installed_inventory"], sort_keys=False)
    )
    if recomputed_installed_sha256 != receipt["installed_inventory_sha256"]:
        raise ValueError(
            "installed_inventory_sha256 跟從 installed_inventory canonical"
            f" 序列化重算的結果不符:記錄值="
            f"{receipt['installed_inventory_sha256']!r} 重算值="
            f"{recomputed_installed_sha256!r}"
        )

    # **Phase A3c blocking-fix(Codex review)**:一份手造的 receipt 可以讓
    # inventory hash 自洽(hash 是照著竄改後的 inventory 重算的),但
    # `equality_result` 卻是編造的、跟這兩份 inventory 實際內容對不上——
    # 上面的 sha256 自洽性檢查完全不會抓到這種偽造,必須獨立重算 reconcile
    # 結果並逐一比對。
    recomputed_equality_result = reconcile_lock_selected_vs_installed_inventory(
        receipt["lock_selected_inventory"], receipt["installed_inventory"]
    )
    if recomputed_equality_result != equality_result:
        raise ValueError(
            "equality_result 跟從 lock_selected_inventory/installed_inventory"
            " 獨立重算 reconcile 的結果不符,這份 receipt 記錄了一個跟實際"
            f" inventory 內容不一致的對帳證據:記錄值={equality_result!r}"
            f" 重算值={recomputed_equality_result!r}"
        )

    recomputed_self_identity = environment_creation_identity(receipt)
    if recomputed_self_identity != receipt["environment_creation_identity"]:
        raise ValueError(
            "environment_creation_identity 跟重算結果不符(重算時已排除自身"
            f" 欄位):記錄值={receipt['environment_creation_identity']!r}"
            f" 重算值={recomputed_self_identity!r}"
        )

    # ---- §C.5 fail-closed gate:繼續往下解析候選資料之前必須擋住 ----
    if receipt["exit_code"] != 0:
        raise ValueError(
            "environment_creation_receipt_v1.exit_code 必須是 0 才能繼續"
            f" 往下解析候選資料,實際 {receipt['exit_code']!r}(§C.5"
            " fail-closed 條件)"
        )
    if equality_result["equal"] is not True:
        raise ValueError(
            "environment_creation_receipt_v1.equality_result.equal 必須"
            f" 是 True 才能繼續往下解析候選資料,實際"
            f" {equality_result['equal']!r}(§C.5 fail-closed 條件)"
        )
    _require_install_command_has_hash_verification_evidence(install_command)


# ----------------------------------------------------------------------------
# 7. 安全 receipt writer——預註冊文件 §C.5「receipt 一律排他建立,不可
#    覆寫既有檔案」。本輪(Phase A2b)只加「把已經在記憶體裡驗證過的
#    receipt dict 寫成檔案」這個原語,不做任何 timestamp/UUID/來源掃描/
#    git 指令/environment creation/`load_source()`/Phase B orchestration——
#    寫檔的目的地路徑、要寫的內容全部是呼叫端注入的。
# ----------------------------------------------------------------------------


def guard_receipt_filename(run_dir, filename: str) -> Path:
    """驗證一個 receipt 檔名在注入的 `run_dir`(必須已存在的目錄)底下合法,
    回傳解析過的絕對路徑。**不建立 `run_dir`、不建立檔案。**

    Fail-closed 條件(跟 `guard_candidate_output_dir` 同一套 §C.4 風格):
    - `filename` 是空字串、含 `/`、`\\`、NUL,或是 `.`/`..`。
    - `run_dir` 不存在或不是目錄。
    - 解析後(跟隨符號連結/reparse point 之後)的真實路徑不等於
      `<run_dir 的真實路徑>/<filename>` 這個字面路徑——擋任何一層 symlink/
      reparse 逃逸。
    """
    if (
        not isinstance(filename, str)
        or filename == ""
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise ValueError(
            f"receipt 檔名不合法(空字串/路徑分隔符號/`.`/`..`/NUL):{filename!r}"
        )

    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ValueError(f"run_dir 不存在或不是目錄(必須是呼叫端已經準備好的" f" run 目錄):{run_dir}")
    run_dir_real = run_dir.resolve(strict=True)

    target = run_dir / filename
    expected = run_dir_real / filename
    target_resolved = target.resolve(strict=False)
    if target_resolved != expected:
        raise ValueError(
            "receipt 路徑解析後不等於預期的字面路徑——可能是 symlink/reparse"
            f" point 逃逸:resolved={target_resolved} expected={expected}"
        )
    return target_resolved


def write_receipt_json_atomic(path, receipt: dict) -> tuple:
    """把 `receipt` dict 以 canonical JSON 位元組**排他建立**寫入 `path`
    (§C.5:receipt 一律 exclusive create,絕不覆寫既有檔案)。回傳
    `(絕對路徑, 寫入位元組的 SHA-256)`。

    前置條件(呼叫端必須先準備好,這裡**不**建立):
    - `path` 的父目錄必須已經存在且是目錄——注入路徑,不是這裡建立的。

    Fail-closed(**不留下 partial 最終檔案**):
    - `receipt` 不是 dict、或父目錄不存在/不是目錄 → 在任何 `os.open` 之前
      就直接 raise,完全不觸碰檔案系統。
    - canonical JSON 序列化本身失敗(例如內含 `json.dumps` 無法處理的
      物件)→ 一樣在任何檔案被建立之前就 raise。
    - `path` 已存在(不論是檔案還是目錄)→ `O_CREAT|O_EXCL` 排他開檔自然
      失敗,raise,**原有檔案/目錄完全不動**,不會被覆寫也不會被刪除。
    - 排他建立成功之後、寫入/`fsync`/關檔過程中發生任何例外 → 這個新檔案
      是這次呼叫自己剛排他建立出來的(不是任何既有檔案),於是刪掉它再
      重新拋出例外,確保不留下 partial 最終 receipt。
    """
    if not isinstance(receipt, dict):
        raise TypeError(f"receipt must be a dict, got {type(receipt).__name__}")

    path = Path(path)
    parent = path.parent
    if not parent.is_dir():
        raise ValueError(f"receipt 的父目錄必須已存在且是目錄(注入路徑,這裡" f" 不會建立):{parent}")

    payload = canonical_json_bytes(receipt, sort_keys=True)

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(path), flags, 0o644)
    except FileExistsError:
        raise ValueError(
            f"receipt 檔案已存在,拒絕覆寫(§C.5 排他建立):{path}"
        ) from None
    except PermissionError:
        # Windows 對已存在的「目錄」路徑做 O_CREAT|O_EXCL 開檔,拋的是
        # PermissionError 而不是 FileExistsError——這裡明確區分「路徑已被
        # 目錄佔用,拒絕覆寫」跟真正的權限不足,不吞掉後者。
        if path.exists():
            raise ValueError(
                "receipt 路徑已存在(被一個目錄或其他非一般檔案的項目佔用),"
                f"拒絕覆寫(§C.5 排他建立):{path}"
            ) from None
        raise

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise

    return path.resolve(strict=True), sha256_hex(payload)


def write_environment_creation_receipt(path, receipt: dict) -> tuple:
    """先跑 §C.5 fail-closed gate(`validate_environment_creation_receipt`),
    通過才排他寫入。**gate 沒過(`exit_code != 0`/`equality_result.equal`
    不是 `True`/`install_command` 缺 hash 校驗證據/結構不符)就直接
    raise,連 exclusive create 都不會嘗試——不留下任何檔案。**"""
    validate_environment_creation_receipt(receipt)
    return write_receipt_json_atomic(path, receipt)


# 本輪(Phase A2b)新增、任務書 §3 定義的「最小頂層 build receipt」——
# **不是**逐位元組凍結在預註冊文件裡的既有 schema 名稱,是這一輪任務書
# 明確列出欄位需求後的最小組裝:§C.1 凍結的 13 個頂層身分欄位,加上
# `run_id`/`authorized_verifier_identity`(注入值,這裡不計算或發明)/
# `overall_status`(只能是下面兩個值之一)/environment-creation receipt
# 的路徑、SHA-256、identity 三個欄位(全部是注入值)。跟
# `installer_report_artifact_hashes` 的內部 shape 一樣,這是本輪的最小
# 合理選擇,不是預註冊文件位元組層級凍結的公式。
TOP_LEVEL_BUILD_RECEIPT_SCHEMA_TAG = "top_level_build_receipt_v1"
OVERALL_STATUS_VALUES = (
    "BUILD_COMPLETE_AWAITING_VERIFICATION",
    "BUILD_FAILED_PARTIAL",
)
TOP_LEVEL_BUILD_RECEIPT_FIELDS = TOP_LEVEL_IDENTITY_FIELDS + (
    "schema",
    "run_id",
    "authorized_verifier_identity",
    "overall_status",
    "environment_creation_receipt_path",
    "environment_creation_receipt_sha256",
    "environment_creation_identity",
)


def build_top_level_build_receipt(
    *,
    manifest_identity: str,
    manifest_sha256_file_identity: str,
    supplement_identity: str,
    importer_identity: str,
    extractor_identity: str,
    builder_identity: str,
    dependency_lock_identity: str,
    runtime_environment_identity_v1_value: str,
    preregistration_commit: str,
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION,
    run_id: str,
    authorized_verifier_identity: str,
    overall_status: str,
    environment_creation_receipt_path: str,
    environment_creation_receipt_sha256: str,
    environment_creation_identity_value: str,
) -> dict:
    """組出最小頂層 build receipt(記憶體內 dict,含已重算過的三層身分
    欄位)。`authorized_verifier_identity` 是注入值,這支函式**不計算或
    發明**它。`overall_status` 只接受
    `BUILD_COMPLETE_AWAITING_VERIFICATION`/`BUILD_FAILED_PARTIAL` 兩者
    之一,其他值一律直接 raise。"""
    identity_fields = build_top_level_identity_fields(
        manifest_identity=manifest_identity,
        manifest_sha256_file_identity=manifest_sha256_file_identity,
        supplement_identity=supplement_identity,
        importer_identity=importer_identity,
        extractor_identity=extractor_identity,
        builder_identity=builder_identity,
        dependency_lock_identity=dependency_lock_identity,
        runtime_environment_identity_v1_value=runtime_environment_identity_v1_value,
        preregistration_commit=preregistration_commit,
        candidate_schema_version=candidate_schema_version,
    )
    _require_str("run_id", run_id)
    _require_str("authorized_verifier_identity", authorized_verifier_identity)
    if overall_status not in OVERALL_STATUS_VALUES:
        raise ValueError(
            f"overall_status 必須是 {OVERALL_STATUS_VALUES} 之一,收到"
            f" {overall_status!r}"
        )
    _require_str(
        "environment_creation_receipt_path", environment_creation_receipt_path
    )
    _require_sha256_hex(
        "environment_creation_receipt_sha256", environment_creation_receipt_sha256
    )
    _require_sha256_hex(
        "environment_creation_identity", environment_creation_identity_value
    )

    receipt = dict(identity_fields)
    receipt["schema"] = TOP_LEVEL_BUILD_RECEIPT_SCHEMA_TAG
    receipt["run_id"] = run_id
    receipt["authorized_verifier_identity"] = authorized_verifier_identity
    receipt["overall_status"] = overall_status
    receipt["environment_creation_receipt_path"] = environment_creation_receipt_path
    receipt["environment_creation_receipt_sha256"] = environment_creation_receipt_sha256
    receipt["environment_creation_identity"] = environment_creation_identity_value
    return receipt


def validate_top_level_build_receipt(receipt: dict) -> None:
    """獨立重算並核對一份 `build_top_level_build_receipt` 輸出的內部自洽性
    (含委派給 `validate_top_level_identity_fields` 的三層身分重算)。鍵
    集合不符、`schema` 標籤錯誤、`overall_status` 不在允許值集合、任何
    SHA-256 欄位格式不合法都直接 raise。"""
    if not isinstance(receipt, dict):
        raise TypeError(f"receipt must be a dict, got {type(receipt).__name__}")
    expected_keys = set(TOP_LEVEL_BUILD_RECEIPT_FIELDS)
    keys = set(receipt)
    if keys != expected_keys:
        raise ValueError(
            "top-level build receipt 欄位集合不符:缺"
            f" {sorted(expected_keys - keys)},多 {sorted(keys - expected_keys)}"
        )
    if receipt["schema"] != TOP_LEVEL_BUILD_RECEIPT_SCHEMA_TAG:
        raise ValueError(
            f"schema 必須是 {TOP_LEVEL_BUILD_RECEIPT_SCHEMA_TAG!r},實際"
            f" {receipt['schema']!r}"
        )
    identity_fields = {k: receipt[k] for k in TOP_LEVEL_IDENTITY_FIELDS}
    validate_top_level_identity_fields(identity_fields)

    _require_str("run_id", receipt["run_id"])
    _require_str("authorized_verifier_identity", receipt["authorized_verifier_identity"])
    if receipt["overall_status"] not in OVERALL_STATUS_VALUES:
        raise ValueError(
            f"overall_status 必須是 {OVERALL_STATUS_VALUES} 之一,實際"
            f" {receipt['overall_status']!r}"
        )
    _require_str(
        "environment_creation_receipt_path", receipt["environment_creation_receipt_path"]
    )
    _require_sha256_hex(
        "environment_creation_receipt_sha256",
        receipt["environment_creation_receipt_sha256"],
    )
    _require_sha256_hex(
        "environment_creation_identity", receipt["environment_creation_identity"]
    )


def write_top_level_build_receipt(path, receipt: dict) -> tuple:
    """先驗證(`validate_top_level_build_receipt`)才排他寫入
    (`write_receipt_json_atomic`)。驗證沒過就直接 raise,不寫檔。"""
    validate_top_level_build_receipt(receipt)
    return write_receipt_json_atomic(path, receipt)


# ----------------------------------------------------------------------------
# 8. Phase A3a/A3b——凍結的 lock 產生策略 + 獨立 synthetic parser。
#    這裡**不**呼叫 uv、**不**查詢已安裝的 uv 版本、**不**產生真正的
#    `requirements-v2-data-build.lock`——只針對「使用者已凍結的 uv 路線」
#    定義純規格常數,以及對**注入的合成文字**(不是真檔案)做純解析/純
#    marker 選取/純雜湊核對。
# ----------------------------------------------------------------------------

# 使用者凍結決策(見任務書「Frozen user decision」段,逐條對應;
# Phase A3b/Checkpoint 24 補上精確目標版本/平台):
# - lock 工具:`uv pip compile`
# - hash 產生旗標:`--generate-hashes`
# - 未來安裝驗證旗標:`--require-hashes`
# - 不使用 `--universal`——第一份 lock 只鎖定固定的 Windows x86-64 + 固定
#   Python 這一組環境,不是跨平台 universal lock。
# - 精確目標(Checkpoint 24,2026-08-09):**CPython 3.12.10、Windows
#   AMD64**——不是「目前這台開發機器剛好裝的版本」,是明確指定的固定值。
#   3.14.6(或任何未來版本)不是這個基準的可互換替代品,未來升級要建立
#   獨立的遷移候選(自己的 lock/runtime-environment identity),不能就地
#   覆寫或改標成這個基準——見預註冊文件 Checkpoint 24。
LOCK_INPUT_FILENAME = "requirements-v2-data-build.in"
LOCK_OUTPUT_FILENAME = "requirements-v2-data-build.lock"
LOCK_TOOL_FAMILY = "uv pip compile"
LOCK_GENERATE_HASHES_FLAG = "--generate-hashes"
INSTALL_REQUIRE_HASHES_FLAG = "--require-hashes"

# **執行環境身分的預期觀測值**(§C.1 `runtime_environment_source` 語意
# ——Phase B 實際執行時,`platform.python_implementation()`/`platform.
# machine()` 應該觀測到的精確字面值)。Codex review 修正:這兩個值
# **不是** uv 命令列慣用的正規化/小寫標籤(`cpython`/`x86_64`)——那是
# 下面 `LOCK_TARGET_UV_PYTHON_PLATFORM` 的獨立語意,兩者字面上不一樣,
# 混用會讓未來 receipt 記錄的 `runtime_environment_source` 跟這份 spec
# 對不上。這裡固定用 `platform.python_implementation()`/`platform.
# machine()` 在 CPython/這個凍結的 Windows x86-64 目標上預期回傳的精確
# 字面值。
LOCK_TARGET_PYTHON_IMPLEMENTATION = "CPython"
# **`LOCK_TARGET_PYTHON_VERSION` 是凍結的 uv/resolver 版本目標(`uv pip
# compile --python-version` 的引數值,§C.1 前置檢查要核對觀測到的直譯器
# 版本三元組恰好等於 `(3, 12, 10)`),不是 §C.1
# `runtime_environment_source.python_version_full` 那個欄位本身(第二輪
# Codex review 修正的重點)——`python_version_full` 依既有凍結定義是
# **完整觀測到的 `sys.version` 字串**(含編譯器/位元資訊,例如
# `"3.12.10 (tags/v3.12.10:...) [MSC v.1942 64 bit (AMD64)]"`),要等
# 正式的 uv 隔離環境真的建立、真的執行 Phase B 時才能觀測到,這裡**不**
# 假造或凍結那個完整字串——即使兩次觀測都同樣是 CPython 3.12.10,只要
# 完整 `sys.version` 位元組不同,`runtime_environment_identity_v1` 依然
# 必須不同。**這個 spec 常數本身也不是那個完整字串,呼叫端不能把它直接
# 塞進 `build_runtime_environment_source(python_version_full=...)`。**
LOCK_TARGET_PYTHON_VERSION = "3.12.10"
LOCK_TARGET_OS_SYSTEM = "Windows"
# 這個凍結的 Windows x86-64 目標預期回傳 `AMD64`——不是宣稱「Windows 底下
# 永遠是 AMD64」這種絕對敘述(Windows on ARM 存在,會回傳別的值,只是不在
# 這次凍結的目標範圍內)。
LOCK_TARGET_MACHINE_ARCH = "AMD64"
# **uv 解析引擎的目標平台字串**——跟上面的執行環境身分字面值是分開的
# 語意,不能混用:這是 uv 文件記載的 target-triple 寫法(`uv pip compile
# --python-platform` 接受的其中一種精確平台字串),uv 用它決定「幫哪個
# 平台解析套件相容性」,**不是**要求 `platform.machine()` 回傳這個字串
# 本身(這個凍結目標預期回傳 `AMD64`,不是 `x86_64-pc-windows-msvc`)。
LOCK_TARGET_UV_PYTHON_PLATFORM = "x86_64-pc-windows-msvc"

# `--python-version`/`--python-platform` 是 uv 文件記載的「精確版本/平台」
# 語意旗標(不是這裡發明的):`--python-version <version>` 把解析鎖定在
# 指定的 Python 版本,`--python-platform <target-triple>` 把解析鎖定在
# 指定平台——兩者搭配 `--generate-hashes`、且明確不加 `--universal`,
# 對應「固定 CPython 3.12.10 + Windows x86-64,不是跨平台/跨版本
# universal 解析」這個凍結決策。**這裡只是把這組 argv 片段記成惰性資料
# (tuple of str),不執行、不呼叫 uv、不查詢已安裝的 uv 版本**——真正產生
# lock 是另一個未授權的動作。
LOCK_TARGET_UV_COMPILE_ARGS = (
    "--python-version",
    LOCK_TARGET_PYTHON_VERSION,
    "--python-platform",
    LOCK_TARGET_UV_PYTHON_PLATFORM,
    LOCK_GENERATE_HASHES_FLAG,
)

# `future_install_command` 的確切子命令(`uv pip sync`)不是使用者凍結決策
# 逐字寫死的部分——凍結的只有「安裝時要帶 `--require-hashes`」這個旗標本身
# (任務書「Frozen user decision」第 3 條)。`uv pip sync --require-hashes
# <lock>` 是 uv 生態系裡「照 lock 精確安裝」的慣用子命令,這裡採用它作為
# 本輪的最小合理選擇——跟 `installer_report_artifact_hashes` 的 shape 選擇
# 同一類:如果之後 review 對確切子命令有不同決定,要以那個決定為準,不是
# 這裡的選擇。
LOCK_GENERATION_SPEC_V1 = {
    "schema": "lock_generation_spec_v1",
    "lock_input_filename": LOCK_INPUT_FILENAME,
    "lock_output_filename": LOCK_OUTPUT_FILENAME,
    "tool_family": LOCK_TOOL_FAMILY,
    "generate_hashes_flag": LOCK_GENERATE_HASHES_FLAG,
    "universal_target": False,
    "target_policy": "windows_x86_64_fixed_python_no_universal",
    "target_python_implementation": LOCK_TARGET_PYTHON_IMPLEMENTATION,
    "target_python_version": LOCK_TARGET_PYTHON_VERSION,
    "target_os_system": LOCK_TARGET_OS_SYSTEM,
    "target_machine_arch": LOCK_TARGET_MACHINE_ARCH,
    "target_uv_python_platform": LOCK_TARGET_UV_PYTHON_PLATFORM,
    "future_uv_compile_target_args": LOCK_TARGET_UV_COMPILE_ARGS,
    "future_install_command": (
        "uv",
        "pip",
        "sync",
        INSTALL_REQUIRE_HASHES_FLAG,
        LOCK_OUTPUT_FILENAME,
    ),
}


# ---- PEP 503 套件名稱正規化(用於 inventory 比對) ----

_PEP503_NORMALIZE_RE = re.compile(r"[-_.]+")


def normalize_package_name(name: str) -> str:
    """PEP 503 正規化:連續的 `-`/`_`/`.` 一律變成單一 `-`,再轉小寫。"""
    if not isinstance(name, str) or name == "":
        raise ValueError(f"package name must be a non-empty str, got {name!r}")
    return _PEP503_NORMALIZE_RE.sub("-", name).lower()


# ---- PEP 508 environment marker——用標準函式庫 `packaging.markers` 解析/
#      求值,不是私有文法子集(Codex review:原本手刻的單層 and 子集會
#      拒絕 `or`/括號這種合法的 PEP 508 語法,不符任務要求)。
#
# `packaging` 不是這一輪才引入的新依賴——預註冊文件 §C.1 本來就凍結
# `packaging.markers.default_environment()` 作為 `marker_environment_v1`
# 11 個鍵的來源(見上面 `MARKER_ENVIRONMENT_KEYS` 的註解,「第 21 輪凍
# 結」),`build_v2_candidate.py` 從 Phase A2a 開始就已經在用這個事實
# (雖然那時沒有直接 import,只是引用它的鍵集合)。這裡改成直接 import
# `packaging.markers.Marker` 求值(檔案最上方的 import 區塊),是同一個
# 已凍結函式庫的另一個 API,不是新的依賴決策。


def _require_full_marker_environment(marker_environment: dict) -> dict:
    """`_evaluate_pep508_marker` 的前置驗證:`marker_environment` 必須
    **恰好**是 §C.1 凍結的 `marker_environment_v1` 11 個鍵、每個值都是
    字串——理由見 `_evaluate_pep508_marker` 的 docstring(這是防止
    `packaging.markers.Marker.evaluate()` 偷偷讀到真機器環境值的必要
    條件,不是可有可無的額外檢查)。"""
    if not isinstance(marker_environment, dict):
        raise TypeError(
            f"marker_environment must be a dict, got {type(marker_environment).__name__}"
        )
    keys = set(marker_environment)
    if keys != MARKER_ENVIRONMENT_KEYS:
        raise ValueError(
            "marker_environment 必須恰好是 §C.1 凍結的 marker_environment_v1"
            f" 11 個鍵:缺 {sorted(MARKER_ENVIRONMENT_KEYS - keys)},多"
            f" {sorted(keys - MARKER_ENVIRONMENT_KEYS)}"
        )
    for key, value in marker_environment.items():
        if not isinstance(value, str):
            raise ValueError(
                f"marker_environment[{key!r}] 必須是字串,實際"
                f" {type(value).__name__}:{value!r}"
            )
    return marker_environment


def _evaluate_pep508_marker(marker_raw: str, marker_environment: dict) -> bool:
    """用標準函式庫 `packaging.markers.Marker` 對 `marker_raw`(完整 PEP
    508 語法——`and`/`or`/括號/引號字串/`in`/`not in`/版本比較全部支援,
    不是自訂子集)求值。

    **完全用注入的 `marker_environment` 覆蓋,不讀當前機器的環境**——這是
    實測驗證過的必要防線,不是理論上的謹慎:`Marker.evaluate(environment=
    ...)` 內部的實作是先呼叫**當前機器**的 `default_environment()` 當底,
    再用傳入的 `environment` dict 做 `.update()` 覆蓋。如果傳入的
    dict 沒有覆蓋到某個鍵,那個鍵會**悄悄**留著真機器的值(已經用
    `Marker('os_name == "nt"').evaluate({})` 在這台機器上實測驗證過:傳空
    dict 照樣求值成 `True`,因為真機器的 `os_name` 剛好是 `'nt'`)。所以
    這裡先用 `_require_full_marker_environment` 強制傳入值必須是完整的
    11 鍵集合,讓 `.update()` 對所有 11 個標準鍵都是逐一覆蓋,不會有任何
    一個標準鍵漏掉、悄悄讀到真機器值。

    `context="requirement"`(不是 `Marker.evaluate()` 預設的
    `"metadata"`)——`"metadata"` context 會把沒提供的 `extra` 悄悄預設成
    空字串,不是 fail-closed;`"requirement"` context 對缺席的 `extra`
    是直接 raise(這個 packaging 版本實測是 `KeyError`,不是文件寫的
    `UndefinedEnvironmentName`,這裡兩種例外型別都接住)。凍結的
    `marker_environment_v1` 本來就不含 `extra`,所以任何引用 `extra` 的
    marker 在這裡一律 fail-closed 拒絕,不是刻意支援它。

    Fail-closed:`marker_raw` 不是合法 PEP 508 語法(`InvalidMarker`)、
    marker 引用了 `marker_environment` 沒有的變數、或版本比較不合法
    (`UndefinedEnvironmentName`/`UndefinedComparison`/`KeyError`)一律
    直接 raise `ValueError`,不猜測、不吞掉。
    """
    validated_environment = _require_full_marker_environment(marker_environment)
    if not isinstance(marker_raw, str):
        raise TypeError(f"marker_raw must be a str, got {type(marker_raw).__name__}")
    try:
        marker = Marker(marker_raw)
    except InvalidMarker as exc:
        raise ValueError(
            f"marker 表達式不是合法的 PEP 508 語法:{marker_raw!r}:{exc}"
        ) from exc
    try:
        return marker.evaluate(dict(validated_environment), context="requirement")
    except (KeyError, UndefinedEnvironmentName, UndefinedComparison) as exc:
        raise ValueError(
            "marker 求值失敗(引用了注入環境沒有的變數,或版本比較不合法):"
            f" {marker_raw!r}:{type(exc).__name__}: {exc}"
        ) from exc


# ---- 合成 uv/pip-compile `--generate-hashes` 輸出格式的獨立 strict parser ----

SYNTHETIC_LOCK_PARSE_SCHEMA_TAG = "synthetic_lock_parse_v1"

_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_HASH_TOKEN_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})$")
_UNSUPPORTED_SPEC_PREFIXES = ("-e ", "-r ", "--", "git+")


def _join_continuation_lines(text: str) -> list:
    """把用行尾 `\\` 延續的實體列合併成邏輯列,回傳
    `[(起始列號, 合併後文字), ...]`。延續記號的合法形式**恰好**是
    `pip-compile --generate-hashes` 慣例輸出的格式:內容、一個空白字元、
    `\\`、行尾——不多不少。**不容忍任何模稜兩可的延續**:
    - `\\` 後面還有其他字元(含空白)——延續記號本身不在行尾,不算延續。
    - `\\` 前面不是恰好一個空白字元(0 個——緊貼內容;或 2 個以上)。
    - 延續列後面接空白列或 `#` 註解列(延續了卻沒有內容接續)。
    - 檔案在延續列之後直接結束(沒有下一列可以接續)。
    """
    physical = text.split("\n")
    logical_lines = []
    buffer = None
    buffer_start_lineno = None
    for lineno, raw_line in enumerate(physical, start=1):
        line = raw_line.rstrip("\r")
        rstripped_line = line.rstrip()
        looks_like_continuation = rstripped_line.endswith("\\")
        if looks_like_continuation and rstripped_line != line:
            raise ValueError(
                f"第 {lineno} 列:`\\` 後面不能有多餘空白,是不明確的延續:{raw_line!r}"
            )
        is_continuation = looks_like_continuation
        content = line[:-1] if is_continuation else line
        if is_continuation:
            if not content.endswith(" ") or content.endswith("  "):
                raise ValueError(
                    f"第 {lineno} 列:`\\` 前面必須恰好一個空白字元(pip-compile"
                    f" 慣例格式),是不明確的延續:{raw_line!r}"
                )
            content = content[:-1]

        if buffer is None:
            if is_continuation:
                if content.strip() == "":
                    raise ValueError(f"第 {lineno} 列:延續列不能是空白開頭,是不明確的延續")
                buffer = content.strip()
                buffer_start_lineno = lineno
            else:
                logical_lines.append((lineno, line))
        else:
            if line.strip() == "" or line.lstrip().startswith("#"):
                raise ValueError(
                    f"第 {lineno} 列:延續列(前一列以 `\\` 結尾)後面接空白列"
                    "或註解列,是不明確的延續"
                )
            if is_continuation:
                buffer += " " + content.strip()
            else:
                buffer += " " + line.strip()
                logical_lines.append((buffer_start_lineno, buffer))
                buffer = None

    if buffer is not None:
        raise ValueError(f"第 {buffer_start_lineno} 列:檔案在延續列(`\\`)之後結束,是不明確的延續")
    return logical_lines


def _parse_requirement_logical_line(lineno: int, line: str) -> dict:
    hash_idx = line.find(" --hash=")
    if hash_idx == -1:
        raise ValueError(f"第 {lineno} 列:缺少 --hash=sha256:...(必須至少一個 hash):{line!r}")
    spec_part = line[:hash_idx].strip()
    hashes_part = line[hash_idx:].strip()

    if spec_part.startswith(_UNSUPPORTED_SPEC_PREFIXES) or "://" in spec_part:
        raise ValueError(
            "第"
            f" {lineno} 列:不支援 URL/editable/git 形式的需求(本輪只接受精確"
            f" pin 的 name==version):{line!r}"
        )
    if spec_part.startswith("./") or spec_part.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", spec_part):
        raise ValueError(f"第 {lineno} 列:不支援本地目錄形式的需求:{line!r}")

    if ";" in spec_part:
        name_version_part, marker_raw = spec_part.split(";", 1)
        marker_raw = marker_raw.strip()
    else:
        name_version_part = spec_part
        marker_raw = None
    name_version_part = name_version_part.strip()

    if name_version_part.count("==") != 1:
        raise ValueError(
            f"第 {lineno} 列:必須是精確 pin 的 `name==version`(不接受"
            f" >=/<=/~=/未鎖定版本):{line!r}"
        )
    raw_name, raw_version = (part.strip() for part in name_version_part.split("=="))
    if not _PACKAGE_NAME_RE.match(raw_name):
        raise ValueError(f"第 {lineno} 列:套件名稱格式不合法:{raw_name!r}")
    if not _VERSION_RE.match(raw_version):
        raise ValueError(f"第 {lineno} 列:版本字串格式不合法:{raw_version!r}")

    hash_tokens = hashes_part.split()
    hashes = []
    for tok in hash_tokens:
        m = _HASH_TOKEN_RE.match(tok)
        if not m:
            raise ValueError(
                f"第 {lineno} 列:hash 格式不合法(必須是"
                f" --hash=sha256:<64碼小寫hex>):{tok!r}"
            )
        hashes.append(m.group(1))
    if len(set(hashes)) != len(hashes):
        raise ValueError(f"第 {lineno} 列:同一筆需求裡出現重複的 hash:{line!r}")

    if marker_raw is not None:
        # 解析階段就驗證 marker 是不是合法的 PEP 508 語法(用標準函式庫,
        # 不是自訂子集)——語法錯誤在這裡就直接擋,不用等到之後求值才發現。
        try:
            Marker(marker_raw)
        except InvalidMarker as exc:
            raise ValueError(
                f"第 {lineno} 列:marker 表達式不是合法的 PEP 508 語法:"
                f"{marker_raw!r}:{exc}"
            ) from exc

    normalized_name = normalize_package_name(raw_name)
    return {
        "raw_name": raw_name,
        "normalized_name": normalized_name,
        "version": raw_version,
        "marker_raw": marker_raw,
        "hashes": tuple(hashes),
        "lineno": lineno,
    }


def parse_synthetic_lock_text(text: str) -> dict:
    """對**注入的合成文字**(不是真檔案、不讀磁碟)做 strict 解析,回傳
    `{"schema", "records", "canonical_sha256"}`。**不是**在解析真正的
    `requirements-v2-data-build.lock`——這支函式本輪只吃呼叫端/測試組出
    的字串。

    每個 record 是 `{raw_name, normalized_name, version, marker_raw,
    hashes, lineno}`——`marker_raw` 保留完整原始 PEP 508 文字(合法性已經
    用 `packaging.markers.Marker` 驗證過,求值留給
    `select_locked_inventory_for_environment`)。`canonical_sha256` 是對
    `[[normalized_name, version, marker_raw, sorted(hashes)], ...]`(依原始
    檔案順序,不重新排序記錄本身——這是**這份 lock 檔案記錄集合本身**的
    身分,不是「選取後的 inventory」,兩者是不同的雜湊)做 canonical JSON
    序列化 + SHA-256。`lineno` 故意不計入(純除錯用,不是語意的一部分)。

    Fail-closed(逐一對應任務書要求):未精確 pin 的需求(`>=`/`~=`/無版本)、
    缺 hash、hash 格式不合法、URL/editable/git/本地目錄形式、不合法的
    PEP 508 marker 語法、重複的套件/版本/marker 記錄、模稜兩可的延續列——
    全部直接 raise。
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")

    logical_lines = _join_continuation_lines(text)
    records = []
    seen = set()
    for lineno, line in logical_lines:
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        record = _parse_requirement_logical_line(lineno, stripped)
        dup_key = (record["normalized_name"], record["version"], record["marker_raw"])
        if dup_key in seen:
            raise ValueError(f"第 {lineno} 列:重複的套件/版本/marker 記錄:{dup_key!r}")
        seen.add(dup_key)
        records.append(record)

    if not records:
        raise ValueError("synthetic lock text 沒有解析出任何需求記錄")

    canonical_array = [
        [r["normalized_name"], r["version"], r["marker_raw"], sorted(r["hashes"])]
        for r in records
    ]
    canonical_sha256 = sha256_hex(canonical_json_bytes(canonical_array, sort_keys=False))
    return {
        "schema": SYNTHETIC_LOCK_PARSE_SCHEMA_TAG,
        "records": records,
        "canonical_sha256": canonical_sha256,
    }


def select_locked_inventory_for_environment(parsed_lock: dict, marker_environment: dict) -> list:
    """用注入的 `marker_environment` dict(**不讀當前機器**,見
    `_evaluate_pep508_marker`)對 `parse_synthetic_lock_text` 的輸出做
    marker 選取。

    回傳依 §C.5 凍結 schema 要求的 **canonical 排序**
    `[[normalized_name, version], ...]`——按 `(normalized_name, version)`
    字典序排序,**不是**原始 lock 檔案裡的記錄順序(Codex review:原始
    順序只在 `parsed_lock['records']` 裡當診斷 metadata 保留,不能定義這
    個回傳值的順序或它的 canonical SHA-256,否則同一組被選中的套件會因為
    lock 檔案文字順序不同而算出不同雜湊)。

    `marker_raw` 是 `None`(無條件依賴)的記錄一律入選;有 marker 的記錄
    用 `_evaluate_pep508_marker`(標準 PEP 508 語意)求值為 `True` 才入選。

    **唯一版本語意(Phase A3c 強化)**:marker 選取後,同一個
    `normalized_name` 只能對應一個版本——`selected_versions_by_name` 用
    名稱本身當 key,任何名稱第二次出現就直接 raise,不管第二次出現的版本
    跟第一次相不相同。這**涵蓋**原本只擋「同一個 `(normalized_name,
    version)` pair 被兩筆不同 marker 的記錄各自命中」的舊語意(pair 重複
    的前提是名稱也重複),**也額外擋住**「同一個名稱被兩筆不同 marker 的
    記錄各自選中、但版本不同」這個舊邏輯漏掉的情況——不悄悄產生語意不
    明確、順序依賴、或「一個套件同時要求兩個版本」的 inventory。"""
    if not isinstance(parsed_lock, dict) or "records" not in parsed_lock:
        raise TypeError("parsed_lock must be the dict returned by parse_synthetic_lock_text")
    if not isinstance(marker_environment, dict):
        raise TypeError(f"marker_environment must be a dict, got {type(marker_environment).__name__}")

    selected_versions_by_name = {}
    for record in parsed_lock["records"]:
        marker_raw = record["marker_raw"]
        included = (
            True
            if marker_raw is None
            else _evaluate_pep508_marker(marker_raw, marker_environment)
        )
        if not included:
            continue
        name = record["normalized_name"]
        version = record["version"]
        if name in selected_versions_by_name:
            raise ValueError(
                "marker 選取後,同一個正規化套件名稱被選取超過一次,語意不"
                "明確,拒絕悄悄合併或悄悄保留其中一筆(重複的原因可能是"
                f"完全相同的 (name, version) 記錄,也可能是同一個名稱同時"
                f"解析出兩個不同版本):{name!r} 先前已選中"
                f" {selected_versions_by_name[name]!r},又選中 {version!r}"
            )
        selected_versions_by_name[name] = version
    return [
        [name, version] for name, version in sorted(selected_versions_by_name.items())
    ]


def check_selected_inventory_matches_declared_sha256(
    selected_inventory: list, lock_selected_inventory_sha256: str
) -> None:
    """嚴格核對 `selected_inventory` 的 canonical SHA-256(跟
    `build_environment_creation_receipt` 對 `lock_selected_inventory_sha256`
    用的同一套 canonical 序列化規則:`canonical_json_bytes(..., sort_keys
    =False)`)是否等於注入的 `lock_selected_inventory_sha256`。**這裡不計算
    也不寫任何 receipt**——純粹是一個核對函式,不符合就直接 raise。

    **Phase A3c blocking-fix**:`selected_inventory` 本身必須已經是
    canonical(`_require_canonical_normalized_pair_list`)——這是 hash-check
    路徑,Codex review 指出它原本也只做形狀檢查,一個 non-canonical(未
    排序/未正規化/重複名稱)的清單照樣能通過雜湊比對,悄悄把非 canonical
    的內容當成合法證據放行。"""
    _require_canonical_normalized_pair_list("selected_inventory", selected_inventory)
    _require_sha256_hex("lock_selected_inventory_sha256", lock_selected_inventory_sha256)
    actual = sha256_hex(canonical_json_bytes(selected_inventory, sort_keys=False))
    if actual != lock_selected_inventory_sha256:
        raise ValueError(
            "selected inventory 的 canonical SHA-256 跟注入的"
            f" lock_selected_inventory_sha256 不符:實際={actual!r}"
            f" 注入值={lock_selected_inventory_sha256!r}"
        )


# ----------------------------------------------------------------------------
# 9. Phase A3c —— 純、注入資料的完整 inventory 對帳。
#    這裡全部是純函式,只吃呼叫端注入的 `[[name, version], ...]` list——
#    **不**呼叫 `importlib.metadata.distributions()` 觀測真正的已安裝套件
#    (那是另一個獨立、本輪不做的環境觀測 adapter 任務)、不讀檔、不寫檔、
#    不計算或寫入任何 receipt。
# ----------------------------------------------------------------------------

# §C.5 `bootstrap_tool_inventory` 的固定範圍——PEP 503 正規化後的名稱,
# 逐一對應 pip 自舉安裝時一定存在、但不屬於使用者鎖定依賴的三個工具。
BOOTSTRAP_TOOL_NORMALIZED_NAMES = frozenset({"pip", "setuptools", "wheel"})


def _canonicalize_pairs_to_name_version_dict(field_label: str, pairs) -> dict:
    """**共用的 raw-input 正規化 helper**(不是 receipt evidence 驗證器
    ——見 `_require_canonical_normalized_pair_list` 那支才是「拒絕非
    canonical 輸入」的嚴格版本)。接受呼叫端注入的
    `[[raw_name, version], ...]`,PEP 503 正規化每個名稱、保留版本字串
    原樣,回傳 `{normalized_name: version}`。**允許**別名/任意來源順序
    (呼叫端本來就可能傳進 `Py_YAML`/`py-yaml` 這種字面上不同、正規化後
    相同的名稱)——這正是它跟 `_require_canonical_normalized_pair_list`
    的差異:這支函式**做**正規化,那支只**驗證**已經正規化過。

    Fail-closed:`pairs` 不是 list、任何元素不是恰好 2 個元素的
    list/tuple、任何成員不是非空字串、或正規化後出現重複的
    `normalized_name`(不論是完全相同的重複列,還是同一個名稱的兩個不同
    版本,還是兩個字面不同但正規化後相同的別名)——一律直接 raise,不
    悄悄保留其中一筆、不悄悄合併。"""
    if not isinstance(pairs, list):
        raise TypeError(
            f"{field_label} must be a list, got {type(pairs).__name__}: {pairs!r}"
        )
    result = {}
    seen_at_index = {}
    for i, item in enumerate(pairs):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(
                f"{field_label}[{i}] must be a 2-element [name, version] pair,"
                f" got {item!r}"
            )
        raw_name, raw_version = item
        if (
            not isinstance(raw_name, str)
            or raw_name == ""
            or not isinstance(raw_version, str)
            or raw_version == ""
        ):
            raise ValueError(
                f"{field_label}[{i}] must be a pair of two non-empty str,"
                f" got {item!r}"
            )
        normalized_name = normalize_package_name(raw_name)
        if normalized_name in seen_at_index:
            raise ValueError(
                f"{field_label} 出現重複的正規化套件名稱 {normalized_name!r}"
                f"(第 {seen_at_index[normalized_name]} 筆與第 {i} 筆),拒絕在"
                "對帳/canonicalize 前靜默去重(不論兩筆是完全相同的重複列、"
                "同一個名稱的兩個不同版本,還是正規化後相同的別名)"
            )
        seen_at_index[normalized_name] = i
        result[normalized_name] = raw_version
    return result


def canonicalize_and_partition_installed_inventory(observed_pairs: list) -> dict:
    """對呼叫端**注入的**已安裝套件觀測值(`[[name, version], ...]`)做
    canonicalize + 依 `BOOTSTRAP_TOOL_NORMALIZED_NAMES` 分割,回傳
    `{"bootstrap_tool_inventory": [...], "installed_inventory": [...]}`,
    兩個陣列各自都是按 `(normalized_name, version)` 字典序排序的 canonical
    `[[normalized_name, version], ...]`(跟 §C.5 既有 inventory 陣列同一種
    shape)。正規化 + 重複偵測委派給共用的
    `_canonicalize_pairs_to_name_version_dict`(見該函式的 fail-closed
    條件)。

    這支函式本身**不**判斷「這個名稱是不是本來就該在這份觀測值裡」——它
    只負責 canonicalize + 分割,`observed_pairs` 的真實性/完整性是呼叫端
    (未來的環境觀測 adapter)的職責。"""
    by_name = _canonicalize_pairs_to_name_version_dict("observed_pairs", observed_pairs)

    bootstrap_tool_inventory = []
    installed_inventory = []
    for normalized_name, version in sorted(by_name.items()):
        bucket = (
            bootstrap_tool_inventory
            if normalized_name in BOOTSTRAP_TOOL_NORMALIZED_NAMES
            else installed_inventory
        )
        bucket.append([normalized_name, version])

    return {
        "bootstrap_tool_inventory": bootstrap_tool_inventory,
        "installed_inventory": installed_inventory,
    }


def reconcile_lock_selected_vs_installed_inventory(
    lock_selected_inventory: list, installed_inventory: list
) -> dict:
    """比對 `lock_selected_inventory`(`select_locked_inventory_for_
    environment` 的輸出)與**已排除 bootstrap 工具**的 `installed_
    inventory`(`canonicalize_and_partition_installed_inventory` 輸出的
    `installed_inventory` 那一半),回傳跟既有 receipt schema 相容的
    `equality_result`(見 `_require_equality_result`:恰好
    `{"equal": bool, "discrepancies": [...]}`,可以直接原樣傳給
    `build_environment_creation_receipt(equality_result=...)`)。

    **本函式自己正規化兩邊輸入(Phase A3c blocking-fix,Codex review)**:
    委派給 `_canonicalize_pairs_to_name_version_dict`——不能假設呼叫端
    傳進來的兩邊都已經是 PEP 503 正規化過的字面值,例如 `Py_YAML==6.0`
    對比 `py-yaml==6.0` 這兩個字面上不同的原始名稱,正規化後其實是同一個
    套件,對帳語意上必須視為相同套件相符,**不能**被誤判成「lock 選中但
    沒觀測到」+「觀測到但 lock 沒選中」兩筆各自獨立的 discrepancy。

    比對規則是**精確**的正規化名稱 + 精確版本相等——**沒有任何容忍值、
    子集允許、或白名單放行**:
    - `missing`:`lock_selected_inventory` 選中,但 `installed_inventory`
      沒觀測到。
    - `unexpected`:`installed_inventory` 觀測到,但不在
      `lock_selected_inventory` 裡。
    - `version_mismatch`:兩邊都有這個名稱,但版本字串不完全相等。

    三種分類彼此互斥(`missing`/`unexpected` 只碰兩邊名稱集合的差集,
    `version_mismatch` 只碰交集),`discrepancies` 本身再依
    `(type, normalized_name)` 字典序排序——回傳值**只由兩個輸入 inventory
    的內容決定,跟輸入 list 本身的元素順序無關**,同一組內容不論傳入順序
    為何,重覆呼叫都得到位元組相同的結果(供 canonical JSON/雜湊使用)。

    Fail-closed:任一輸入不是合法的 `[[name, version], ...]` shape、任一
    成員是空字串、或任一輸入自己內部就有重複的正規化名稱(拒絕在對帳前先
    靜默去重或悄悄合併別名),一律直接 raise。
    """
    lock_by_name = _canonicalize_pairs_to_name_version_dict(
        "lock_selected_inventory", lock_selected_inventory
    )
    installed_by_name = _canonicalize_pairs_to_name_version_dict(
        "installed_inventory", installed_inventory
    )

    lock_names = set(lock_by_name)
    installed_names = set(installed_by_name)

    discrepancies = []
    for name in lock_names - installed_names:
        discrepancies.append(
            {
                "type": "missing",
                "normalized_name": name,
                "expected_version": lock_by_name[name],
                "actual_version": None,
            }
        )
    for name in installed_names - lock_names:
        discrepancies.append(
            {
                "type": "unexpected",
                "normalized_name": name,
                "expected_version": None,
                "actual_version": installed_by_name[name],
            }
        )
    for name in lock_names & installed_names:
        if lock_by_name[name] != installed_by_name[name]:
            discrepancies.append(
                {
                    "type": "version_mismatch",
                    "normalized_name": name,
                    "expected_version": lock_by_name[name],
                    "actual_version": installed_by_name[name],
                }
            )
    discrepancies.sort(key=lambda d: (d["type"], d["normalized_name"]))

    return {"equal": len(discrepancies) == 0, "discrepancies": discrepancies}


def guard_inventory_reconciliation_equal(equality_result: dict) -> None:
    """§C.5「繼續往下建構 runtime/snapshot identity 之前」必須通過的
    fail-closed gate:`equality_result["equal"] is not True` 一律直接
    raise。這裡**只做這一個判斷**——不計算對帳結果(那是
    `reconcile_lock_selected_vs_installed_inventory` 的職責)、**不計算或
    寫入任何 receipt**(本輪任務書明講不做)。

    重用 `_require_equality_result` 驗證 shape/型別(鍵集合恰好
    `{"equal", "discrepancies"}`、`equal` 必須是真正的 `bool`,不接受
    truthy 替代品),驗證通過後才檢查 `is not True`(不是單純 falsy 檢查,
    語意跟 `validate_environment_creation_receipt` 對同一個欄位的既有
    fail-closed 判斷一致)。"""
    equality_result = _require_equality_result(equality_result)
    if equality_result["equal"] is not True:
        raise ValueError(
            "inventory reconciliation 的 equality_result.equal 必須是 True"
            " 才能繼續往下建構 runtime/snapshot identity,實際"
            f" {equality_result['equal']!r};discrepancies="
            f"{equality_result['discrepancies']!r}"
        )


# ----------------------------------------------------------------------------
# 11. 品質證據 sidecar(§C.9)——把 tej_importer.py 在記憶體內算好的
#     cell_records(blank/unparseable 的 locator 證據,含 dedup_key_v1)包裝
#     成一份逐 dataset、排他建立的 sidecar 檔案。cell 分類是 tej_importer.py
#     的職責(§D);這裡只**重新驗證**已經產生的紀錄本身的 shape/自洽性
#     (獨立重算 dedup_key,不信任宣稱值——跟
#     `build_environment_creation_receipt` 對 inventory SHA 的態度一致),
#     然後負責寫檔。
# ----------------------------------------------------------------------------

QUALITY_SIDECAR_SCHEMA_TAG = "quality_sidecar_v1"

# §C.9 強化後 locator 契約的精確欄位集合,逐一對應 tej_importer.py
# `_classify_numeric_cells` 產生的 cell_records 每一筆物件。
CELL_RECORD_FIELDS = frozenset(
    {
        "dataset",
        "source_relpath",
        "source_file_sha256",
        "source_container_member",
        "source_row_number",
        "stock_id",
        "date",
        "source_column",
        "target_column",
        "raw_token",
        "is_blank",
        "is_unparseable",
        "parser",
        "unit_scale_applied",
        "resulting_value",
        "dedup_key",
    }
)


def dedup_key_v1(
    dataset: str,
    source_relpath: str,
    source_container_member,
    source_row_number: int,
    target_column: str,
) -> str:
    """§C.9 `dedup_key` 的 canonical JSON 陣列序列化(第 18 輪凍結公式)。
    獨立實作,不 import `tej_importer`——建置器用這支函式**驗證**
    importer 宣稱的 `dedup_key`,不是信任它;跟 `tej_importer._dedup_key_v1`
    逐位元組同一套公式,是刻意的重複(§D 的兩層各自獨立計算同一件事,不是
    互相委派)。"""
    if not isinstance(source_row_number, int) or isinstance(source_row_number, bool):
        raise ValueError(
            f"source_row_number must be a plain int, got {source_row_number!r}"
        )
    canonical_array = [
        "dedup_key_v1",
        dataset,
        source_relpath,
        source_container_member,
        source_row_number,
        target_column,
    ]
    return sha256_hex(canonical_json_bytes(canonical_array, sort_keys=False))


def _require_cell_record(index: int, record, *, dataset: str) -> dict:
    """§C.9 強化 locator 契約的逐筆結構/自洽驗證(不信任呼叫端已經驗證過,
    每次組 sidecar 都重新做一次)。"""
    if not isinstance(record, dict) or set(record) != CELL_RECORD_FIELDS:
        got = sorted(record.keys()) if isinstance(record, dict) else record
        raise ValueError(
            f"quality sidecar record[{index}] 欄位集合跟 §C.9 locator 契約不符"
            f"(預期 {sorted(CELL_RECORD_FIELDS)}),實際 {got!r}"
        )
    if record["dataset"] != dataset:
        raise ValueError(
            f"quality sidecar record[{index}]['dataset']={record['dataset']!r}"
            f" 跟 sidecar 本身的 dataset={dataset!r} 不符"
        )
    is_blank, is_unparseable = record["is_blank"], record["is_unparseable"]
    if not isinstance(is_blank, bool) or not isinstance(is_unparseable, bool):
        raise ValueError(
            f"quality sidecar record[{index}] is_blank/is_unparseable 必須是 bool"
        )
    if is_blank == is_unparseable:
        raise ValueError(
            f"quality sidecar record[{index}] is_blank/is_unparseable 必須恰好"
            f" 一個為 True(§C.9 兩者互斥,sidecar 只收這兩類):is_blank="
            f"{is_blank} is_unparseable={is_unparseable}"
        )
    raw_token = record["raw_token"]
    if is_blank and raw_token is not None:
        raise ValueError(
            f"quality sidecar record[{index}] is_blank=True 但 raw_token 不是"
            " null——§C.9 定義 raw_token 為 null 只保留給真正空白的儲存格"
        )
    if is_unparseable and (not isinstance(raw_token, str) or raw_token == ""):
        raise ValueError(
            f"quality sidecar record[{index}] is_unparseable=True 但 raw_token"
            f" 不是非空字串:{raw_token!r}"
        )
    if record["resulting_value"] is not None:
        raise ValueError(
            f"quality sidecar record[{index}] resulting_value 必須是 null"
            "(is_blank/is_unparseable 情況下最終寫進候選 parquet 的值必為"
            f" null),實際 {record['resulting_value']!r}"
        )
    if record["parser"] != "pd.to_numeric":
        raise ValueError(
            f"quality sidecar record[{index}] parser 必須是固定字面值"
            f" 'pd.to_numeric',實際 {record['parser']!r}"
        )
    source_row_number = record["source_row_number"]
    if not isinstance(source_row_number, int) or isinstance(source_row_number, bool):
        raise ValueError(
            f"quality sidecar record[{index}] source_row_number 必須是 int,"
            f" 實際 {source_row_number!r}"
        )
    recomputed = dedup_key_v1(
        record["dataset"],
        record["source_relpath"],
        record["source_container_member"],
        source_row_number,
        record["target_column"],
    )
    if recomputed != record["dedup_key"]:
        raise ValueError(
            f"quality sidecar record[{index}] dedup_key 跟從其自身 locator"
            f" 欄位獨立重算的結果不符——宣稱值={record['dedup_key']!r} 重算值="
            f"{recomputed!r}(builder 不信任 importer 宣稱的 dedup_key,必須"
            " 獨立重算核對)"
        )
    return record


def build_quality_sidecar(*, dataset: str, cell_records: list) -> dict:
    """組出一份 dataset 的 §C.9 quality sidecar(記憶體內 dict)。**不寫檔**。
    `cell_records` 是 `tej_importer.load_source(dataset, return_evidence=True)`
    回傳的 `evidence_bundle['cell_records']`(僅 blank/unparseable 兩類,已經
    附帶 `dedup_key`)——這裡逐筆重新驗證 shape/self-consistency,並獨立重算
    每一筆的 `dedup_key` 核對,不是照單全收。"""
    _require_str("dataset", dataset)
    if not isinstance(cell_records, list):
        raise ValueError(
            f"cell_records must be a list, got {type(cell_records).__name__}"
        )
    validated = [
        _require_cell_record(i, r, dataset=dataset) for i, r in enumerate(cell_records)
    ]
    return {
        "schema": QUALITY_SIDECAR_SCHEMA_TAG,
        "dataset": dataset,
        "record_count": len(validated),
        "records": validated,
    }


def validate_quality_sidecar(sidecar: dict) -> None:
    if not isinstance(sidecar, dict) or set(sidecar) != {
        "schema",
        "dataset",
        "record_count",
        "records",
    }:
        raise ValueError(f"quality sidecar 欄位集合不符,實際 {sidecar!r}")
    if sidecar["schema"] != QUALITY_SIDECAR_SCHEMA_TAG:
        raise ValueError(
            f"quality sidecar schema 必須是 {QUALITY_SIDECAR_SCHEMA_TAG!r},"
            f" 實際 {sidecar['schema']!r}"
        )
    dataset = _require_str("dataset", sidecar["dataset"])
    records = sidecar["records"]
    if not isinstance(records, list):
        raise ValueError("quality sidecar records must be a list")
    for i, r in enumerate(records):
        _require_cell_record(i, r, dataset=dataset)
    if sidecar["record_count"] != len(records):
        raise ValueError(
            f"quality sidecar record_count={sidecar['record_count']!r} 跟"
            f" records 實際長度 {len(records)} 不符"
        )


def write_quality_sidecar(path, sidecar: dict) -> tuple:
    """先驗證才排他寫入(`write_receipt_json_atomic`)。驗證沒過就不留下任何
    檔案。"""
    validate_quality_sidecar(sidecar)
    return write_receipt_json_atomic(path, sidecar)


# ----------------------------------------------------------------------------
# 12. supplement_provenance 巢狀物件(§C.10)——由呼叫端(orchestrator)嵌進
#     受影響 dataset(#3/#5/#6)各自的逐 dataset build receipt 裡,不是獨立
#     檔案。這裡只組裝/驗證,不寫檔。
# ----------------------------------------------------------------------------

SUPPLEMENT_PROVENANCE_SOURCE_CLASS = "LEGACY_DERIVED_SUPPLEMENT"


def build_supplement_provenance(
    *,
    supplement_receipt_path: str,
    supplement_receipt_sha256: str,
    supplement_identity_value: str,
    affected_columns: list,
    merge_profile: dict,
    rows_with_supplement_value: int,
) -> dict:
    """組出 §C.10 `supplement_provenance` 巢狀物件(記憶體內 dict)。**不寫
    檔**。`merge_profile` 是 `tej_importer._profile_supplement_merge()` 的
    輸出(§C.10 `row_counts`/`non_overlap_assertion` 統計的來源)。
    `rows_with_supplement_value` 是呼叫端從合併後的 `combined` DataFrame
    算出、注入的值(至少一個 supplement 欄位非 null 的列數)——這支函式本身
    不接觸 DataFrame。"""
    _require_str("supplement_receipt_path", supplement_receipt_path)
    _require_sha256_hex("supplement_receipt_sha256", supplement_receipt_sha256)
    _require_sha256_hex("supplement_identity", supplement_identity_value)
    if supplement_receipt_sha256 != supplement_identity_value:
        raise ValueError(
            "supplement_provenance.supplement_receipt_sha256 必須等於 §C.1 的"
            f" supplement_identity:receipt_sha256={supplement_receipt_sha256!r}"
            f" supplement_identity={supplement_identity_value!r}"
        )
    if (
        not isinstance(affected_columns, list)
        or not affected_columns
        or not all(isinstance(c, str) and c for c in affected_columns)
    ):
        raise ValueError(
            f"affected_columns must be a non-empty list of non-empty str,"
            f" got {affected_columns!r}"
        )
    if affected_columns != sorted(affected_columns):
        raise ValueError(f"affected_columns must be sorted, got {affected_columns!r}")

    required_profile_keys = {
        "pre_merge_row_count",
        "post_merge_row_count",
        "native_columns",
        "supplement_columns",
        "rows_supplement_key_not_covered",
    }
    missing = required_profile_keys - set(merge_profile or {})
    if missing:
        raise ValueError(f"merge_profile 缺少必要欄位:{sorted(missing)}")

    pre_merge_rows = merge_profile["pre_merge_row_count"]
    post_merge_rows = merge_profile["post_merge_row_count"]
    if not isinstance(pre_merge_rows, int) or isinstance(pre_merge_rows, bool):
        raise ValueError("merge_profile['pre_merge_row_count'] 必須是 int")
    if not isinstance(post_merge_rows, int) or isinstance(post_merge_rows, bool):
        raise ValueError("merge_profile['post_merge_row_count'] 必須是 int")
    if post_merge_rows != pre_merge_rows:
        raise ValueError(
            f"post_merge_rows={post_merge_rows} 必須等於 pre_merge_rows="
            f"{pre_merge_rows}(§C.10:merge 不能造成列數膨脹)"
        )

    key_cols = {"stock_id", "date"}
    native_columns = [c for c in merge_profile["native_columns"] if c not in key_cols]
    supplement_columns = list(merge_profile["supplement_columns"])
    overlap = sorted(set(native_columns) & set(supplement_columns))
    if overlap:
        raise ValueError(
            f"native_columns/supplement_columns 有欄名重疊:{overlap}"
            "(§C.10:supplement 只能新增原生欄位,不能覆寫)"
        )

    rows_supplement_key_not_covered = merge_profile["rows_supplement_key_not_covered"]
    if not isinstance(rows_supplement_key_not_covered, int) or isinstance(
        rows_supplement_key_not_covered, bool
    ):
        raise ValueError(
            "merge_profile['rows_supplement_key_not_covered'] 必須是 int"
        )
    if not isinstance(rows_with_supplement_value, int) or isinstance(
        rows_with_supplement_value, bool
    ) or rows_with_supplement_value < 0:
        raise ValueError(
            f"rows_with_supplement_value must be a non-negative int, got"
            f" {rows_with_supplement_value!r}"
        )
    if rows_with_supplement_value + rows_supplement_key_not_covered != post_merge_rows:
        raise ValueError(
            "rows_with_supplement_value + rows_supplement_key_not_covered 必須"
            f" 等於 post_merge_rows:{rows_with_supplement_value} +"
            f" {rows_supplement_key_not_covered} != {post_merge_rows}"
        )

    return {
        "supplement_provenance": {
            "source_class": SUPPLEMENT_PROVENANCE_SOURCE_CLASS,
            "supplement_receipt_path": supplement_receipt_path,
            "supplement_receipt_sha256": supplement_receipt_sha256,
            "is_pit": False,
            "affected_columns": list(affected_columns),
            "non_overlap_assertion": {
                "checked": True,
                "native_columns": native_columns,
                "supplement_columns": supplement_columns,
                "overlap": [],
            },
            "row_counts": {
                "pre_merge_rows": pre_merge_rows,
                "post_merge_rows": post_merge_rows,
                "rows_with_supplement_value": rows_with_supplement_value,
                "rows_supplement_key_not_covered": rows_supplement_key_not_covered,
            },
        }
    }


# ----------------------------------------------------------------------------
# 13. 逐 dataset build receipt(§C.5 第 1 項)。
# ----------------------------------------------------------------------------

PER_DATASET_RECEIPT_SCHEMA_TAG = "per_dataset_build_receipt_v1"
DATASET_BUILD_SUCCEEDED = "DATASET_BUILD_SUCCEEDED"
DATASET_BUILD_FAILED = "DATASET_BUILD_FAILED"
_DATASET_BUILD_STATUSES = (DATASET_BUILD_SUCCEEDED, DATASET_BUILD_FAILED)

FINAL_NULL_CAUSE_KEYS = frozenset(
    {
        "RETAINED_BLANK",
        "RETAINED_UNPARSEABLE",
        "SOURCE_COLUMN_ABSENT",
        "SUPPLEMENT_KEY_NOT_COVERED",
        "OTHER_UNEXPLAINED",
    }
)

PER_DATASET_RECEIPT_FIELDS = (
    "schema",
    "snapshot_id_v1",
    "run_id",
    "dataset",
    "status",
    "start_timestamp_utc",
    "end_timestamp_utc",
    "exit_code",
    "source_files",
    "row_count",
    "stock_count",
    "date_min",
    "date_max",
    "schema_metadata",
    "coverage_matrix",
    "duplicate_mapping",
    "final_null_causes",
    "sidecar_path",
    "sidecar_sha256",
    "sidecar_record_count",
    "per_file_stage_one_counts",
    "supplement_provenance",
    "error",
)


def _require_source_files(value) -> list:
    if not isinstance(value, list) or not value:
        raise ValueError(f"source_files must be a non-empty list, got {value!r}")
    for i, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(
                f"source_files[{i}] must be a [relpath, sha256] pair, got {item!r}"
            )
        relpath, digest = item
        _require_str(f"source_files[{i}][0]", relpath)
        _require_sha256_hex(f"source_files[{i}][1]", digest)
    normalized = [list(item) for item in value]
    if normalized != sorted(normalized, key=lambda pair: pair[0]):
        raise ValueError(f"source_files must be sorted by relpath, got {value!r}")
    names = [item[0] for item in normalized]
    if len(set(names)) != len(names):
        raise ValueError(f"source_files has a duplicate relpath: {value!r}")
    return normalized


def _cross_check_sidecar_record_count(
    per_file_stage_one_counts: list, sidecar_record_count: int
) -> None:
    """§C.9:「sidecar 列數因此只跟階段一的 `blank_cell_count` +
    `unparseable_cell_count` 加總對帳」。"""
    total = 0
    for entry in per_file_stage_one_counts:
        for c in entry.get("counts", []):
            total += int(c.get("blank_cell_count", 0)) + int(
                c.get("unparseable_cell_count", 0)
            )
    if total != sidecar_record_count:
        raise ValueError(
            f"sidecar_record_count={sidecar_record_count} 跟"
            f" per_file_stage_one_counts 的 blank_cell_count+unparseable_cell_count"
            f" 加總 {total} 不符(§C.9 accounting 對帳失敗)"
        )


def _cross_check_final_null_causes(
    final_null_causes: dict, final_null_counts_from_output: dict
) -> None:
    """§C.9 階段二等式:五個分類加總必須等於該欄位在最終輸出 parquet 裡的
    null 總數(呼叫端從實際寫出的候選 parquet/DataFrame 注入計算好的
    `final_null_counts_from_output`,這裡不接觸 DataFrame 本身)。"""
    if set(final_null_causes) != set(final_null_counts_from_output):
        raise ValueError(
            "final_null_causes 跟 final_null_counts_from_output 的欄位集合不符:"
            f" {sorted(final_null_causes)} vs {sorted(final_null_counts_from_output)}"
        )
    for col, causes in final_null_causes.items():
        total = sum(int(v) for v in causes.values())
        expected = int(final_null_counts_from_output[col])
        if total != expected:
            raise ValueError(
                f"final_null_causes[{col!r}] 加總 {total} 跟輸出 parquet 實際"
                f" null 數 {expected} 不符(§C.9 階段二 accounting 對帳失敗)"
            )


def build_per_dataset_receipt_success(
    *,
    snapshot_id_v1_value: str,
    run_id: str,
    dataset: str,
    start_timestamp_utc: str,
    end_timestamp_utc: str,
    source_files: list,
    row_count: int,
    stock_count: int,
    date_min,
    date_max,
    schema_metadata: dict,
    coverage_matrix: list,
    duplicate_mapping: list,
    final_null_causes: dict,
    final_null_counts_from_output: dict,
    sidecar_path: str,
    sidecar_sha256: str,
    sidecar_record_count: int,
    per_file_stage_one_counts: list,
    supplement_provenance=None,
) -> dict:
    """組出一份成功完成的逐 dataset build receipt(§C.5 第 1 項)。**不寫
    檔**;內部交叉核對 §C.9 兩組 accounting 等式,任一項不成立直接 raise,
    不產生一份跟自己宣稱數字對不起來的 receipt。"""
    _require_sha256_hex("snapshot_id_v1", snapshot_id_v1_value)
    _require_str("run_id", run_id)
    _require_str("dataset", dataset)
    _require_str("start_timestamp_utc", start_timestamp_utc)
    _require_str("end_timestamp_utc", end_timestamp_utc)
    source_files = _require_source_files(source_files)
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise ValueError(f"row_count must be a non-negative int, got {row_count!r}")
    if (
        not isinstance(stock_count, int)
        or isinstance(stock_count, bool)
        or stock_count < 0
    ):
        raise ValueError(f"stock_count must be a non-negative int, got {stock_count!r}")
    if date_min is not None and not isinstance(date_min, str):
        raise ValueError(f"date_min must be str or None, got {date_min!r}")
    if date_max is not None and not isinstance(date_max, str):
        raise ValueError(f"date_max must be str or None, got {date_max!r}")
    if not isinstance(schema_metadata, dict) or set(schema_metadata) != {
        "logical_types",
        "actual_dtypes",
        "arrow_types",
    }:
        raise ValueError(f"schema_metadata 欄位集合不符,實際 {schema_metadata!r}")
    if not isinstance(coverage_matrix, list):
        raise ValueError("coverage_matrix must be a list")
    if not isinstance(duplicate_mapping, list):
        raise ValueError("duplicate_mapping must be a list")
    if not isinstance(final_null_causes, dict):
        raise ValueError("final_null_causes must be a dict")
    for col, causes in final_null_causes.items():
        if not isinstance(causes, dict) or set(causes) != FINAL_NULL_CAUSE_KEYS:
            raise ValueError(
                f"final_null_causes[{col!r}] 分類鍵集合不符,實際"
                f" {sorted(causes) if isinstance(causes, dict) else causes!r}"
            )
    _require_str("sidecar_path", sidecar_path)
    _require_sha256_hex("sidecar_sha256", sidecar_sha256)
    if (
        not isinstance(sidecar_record_count, int)
        or isinstance(sidecar_record_count, bool)
        or sidecar_record_count < 0
    ):
        raise ValueError(
            f"sidecar_record_count must be a non-negative int, got"
            f" {sidecar_record_count!r}"
        )
    if not isinstance(per_file_stage_one_counts, list):
        raise ValueError("per_file_stage_one_counts must be a list")

    _cross_check_sidecar_record_count(per_file_stage_one_counts, sidecar_record_count)
    _cross_check_final_null_causes(final_null_causes, final_null_counts_from_output)

    if supplement_provenance is not None:
        if not isinstance(supplement_provenance, dict) or set(
            supplement_provenance
        ) != {"supplement_provenance"}:
            raise ValueError(
                f"supplement_provenance wrapper 欄位不符,實際"
                f" {supplement_provenance!r}"
            )

    return {
        "schema": PER_DATASET_RECEIPT_SCHEMA_TAG,
        "snapshot_id_v1": snapshot_id_v1_value,
        "run_id": run_id,
        "dataset": dataset,
        "status": DATASET_BUILD_SUCCEEDED,
        "start_timestamp_utc": start_timestamp_utc,
        "end_timestamp_utc": end_timestamp_utc,
        "exit_code": 0,
        "source_files": source_files,
        "row_count": row_count,
        "stock_count": stock_count,
        "date_min": date_min,
        "date_max": date_max,
        "schema_metadata": schema_metadata,
        "coverage_matrix": coverage_matrix,
        "duplicate_mapping": duplicate_mapping,
        "final_null_causes": final_null_causes,
        "sidecar_path": sidecar_path,
        "sidecar_sha256": sidecar_sha256,
        "sidecar_record_count": sidecar_record_count,
        "per_file_stage_one_counts": per_file_stage_one_counts,
        "supplement_provenance": supplement_provenance,
        "error": None,
    }


def build_per_dataset_receipt_failure(
    *,
    snapshot_id_v1_value: str,
    run_id: str,
    dataset: str,
    start_timestamp_utc: str,
    end_timestamp_utc: str,
    exit_code: int,
    error_type: str,
    error_message: str,
) -> dict:
    """§D stop-on-first-failure:某個 dataset 解析失敗時,記錄一份帶錯誤
    證據的逐 dataset receipt(狀態 `DATASET_BUILD_FAILED`),其餘欄位明確
    填 null/空集合——解析從沒完成,不能假裝有 row/schema 資料。"""
    _require_sha256_hex("snapshot_id_v1", snapshot_id_v1_value)
    _require_str("run_id", run_id)
    _require_str("dataset", dataset)
    _require_str("start_timestamp_utc", start_timestamp_utc)
    _require_str("end_timestamp_utc", end_timestamp_utc)
    if (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code == 0
    ):
        raise ValueError(
            f"failure receipt 的 exit_code 必須是非 0 的 int,收到 {exit_code!r}"
        )
    _require_str("error_type", error_type)
    _require_str("error_message", error_message)
    return {
        "schema": PER_DATASET_RECEIPT_SCHEMA_TAG,
        "snapshot_id_v1": snapshot_id_v1_value,
        "run_id": run_id,
        "dataset": dataset,
        "status": DATASET_BUILD_FAILED,
        "start_timestamp_utc": start_timestamp_utc,
        "end_timestamp_utc": end_timestamp_utc,
        "exit_code": exit_code,
        "source_files": [],
        "row_count": None,
        "stock_count": None,
        "date_min": None,
        "date_max": None,
        "schema_metadata": None,
        "coverage_matrix": [],
        "duplicate_mapping": [],
        "final_null_causes": {},
        "sidecar_path": None,
        "sidecar_sha256": None,
        "sidecar_record_count": None,
        "per_file_stage_one_counts": [],
        "supplement_provenance": None,
        "error": {"error_type": error_type, "error_message": error_message},
    }


def validate_per_dataset_receipt(receipt: dict) -> None:
    if not isinstance(receipt, dict) or set(receipt) != set(PER_DATASET_RECEIPT_FIELDS):
        raise ValueError(f"per-dataset receipt 欄位集合不符,實際 {receipt!r}")
    if receipt["schema"] != PER_DATASET_RECEIPT_SCHEMA_TAG:
        raise ValueError(
            f"schema 必須是 {PER_DATASET_RECEIPT_SCHEMA_TAG!r},實際"
            f" {receipt['schema']!r}"
        )
    if receipt["status"] not in _DATASET_BUILD_STATUSES:
        raise ValueError(
            f"status 必須是 {_DATASET_BUILD_STATUSES} 之一,實際 {receipt['status']!r}"
        )
    if receipt["status"] == DATASET_BUILD_SUCCEEDED:
        if receipt["exit_code"] != 0:
            raise ValueError("status=DATASET_BUILD_SUCCEEDED 但 exit_code 非 0")
        if receipt["error"] is not None:
            raise ValueError("status=DATASET_BUILD_SUCCEEDED 但 error 不是 null")
        _cross_check_sidecar_record_count(
            receipt["per_file_stage_one_counts"], receipt["sidecar_record_count"]
        )
    else:
        if receipt["exit_code"] == 0:
            raise ValueError("status=DATASET_BUILD_FAILED 但 exit_code 是 0")
        if not isinstance(receipt["error"], dict) or set(receipt["error"]) != {
            "error_type",
            "error_message",
        }:
            raise ValueError(
                f"status=DATASET_BUILD_FAILED 但 error 欄位不合法:{receipt['error']!r}"
            )


def write_per_dataset_receipt(path, receipt: dict) -> tuple:
    validate_per_dataset_receipt(receipt)
    return write_receipt_json_atomic(path, receipt)


# ----------------------------------------------------------------------------
# 14. 彙總 build receipt 完整版(§C.5 第 2 項)——延伸 (不取代)
#     `build_top_level_build_receipt`(那支函式仍是舊有、已測試的最小子集,
#     保留原樣不動)。這裡加上 11-dataset 逐 dataset receipt 引用清單,以及
#     §C.1「完整鎖定/安裝相符性契約」段要求彙總 receipt 額外記錄的
#     `lock_selected_inventory`/`installed_inventory`/`bootstrap_tool_
#     inventory` 三份清單(先前只寫進 `environment_creation_receipt_v1`,
#     這裡在彙總層級再記一次)。
# ----------------------------------------------------------------------------

AGGREGATE_BUILD_RECEIPT_SCHEMA_TAG = "aggregate_build_receipt_v1"
AGGREGATE_BUILD_RECEIPT_FIELDS = TOP_LEVEL_BUILD_RECEIPT_FIELDS + (
    "per_dataset_receipts",
    "lock_selected_inventory",
    "lock_selected_inventory_sha256",
    "installed_inventory",
    "installed_inventory_sha256",
    "bootstrap_tool_inventory",
)


def _require_per_dataset_receipts(value) -> list:
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"per_dataset_receipts must be a non-empty list, got {value!r}"
        )
    seen = set()
    for i, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"dataset", "path", "sha256"}:
            raise ValueError(f"per_dataset_receipts[{i}] 欄位不符,實際 {item!r}")
        _require_str(f"per_dataset_receipts[{i}]['dataset']", item["dataset"])
        _require_str(f"per_dataset_receipts[{i}]['path']", item["path"])
        _require_sha256_hex(f"per_dataset_receipts[{i}]['sha256']", item["sha256"])
        if item["dataset"] in seen:
            raise ValueError(
                f"per_dataset_receipts 有重複的 dataset:{item['dataset']!r}"
            )
        seen.add(item["dataset"])
    return value


def build_aggregate_build_receipt(
    *,
    manifest_identity,
    manifest_sha256_file_identity,
    supplement_identity,
    importer_identity,
    extractor_identity,
    builder_identity,
    dependency_lock_identity,
    runtime_environment_identity_v1_value,
    preregistration_commit,
    candidate_schema_version=CANDIDATE_SCHEMA_VERSION,
    run_id: str,
    authorized_verifier_identity: str,
    overall_status: str,
    environment_creation_receipt_path: str,
    environment_creation_receipt_sha256: str,
    environment_creation_identity_value: str,
    per_dataset_receipts: list,
    lock_selected_inventory: list,
    lock_selected_inventory_sha256: str,
    installed_inventory: list,
    installed_inventory_sha256: str,
    bootstrap_tool_inventory: list,
    expected_dataset_order,
) -> dict:
    """§C.5 完整彙總 build receipt。內部先組出既有的 13 個身分欄位 +
    environment-creation 三欄(委派給 `build_top_level_build_receipt`,不
    重寫它的驗證邏輯),再疊加 11-dataset 逐 dataset receipt 引用清單跟完整
    鎖定/安裝相符性的三份 inventory。"""
    base = build_top_level_build_receipt(
        manifest_identity=manifest_identity,
        manifest_sha256_file_identity=manifest_sha256_file_identity,
        supplement_identity=supplement_identity,
        importer_identity=importer_identity,
        extractor_identity=extractor_identity,
        builder_identity=builder_identity,
        dependency_lock_identity=dependency_lock_identity,
        runtime_environment_identity_v1_value=runtime_environment_identity_v1_value,
        preregistration_commit=preregistration_commit,
        candidate_schema_version=candidate_schema_version,
        run_id=run_id,
        authorized_verifier_identity=authorized_verifier_identity,
        overall_status=overall_status,
        environment_creation_receipt_path=environment_creation_receipt_path,
        environment_creation_receipt_sha256=environment_creation_receipt_sha256,
        environment_creation_identity_value=environment_creation_identity_value,
    )
    per_dataset_receipts = _require_per_dataset_receipts(per_dataset_receipts)
    seen_datasets = {item["dataset"] for item in per_dataset_receipts}
    expected_dataset_order = tuple(expected_dataset_order)
    if not expected_dataset_order:
        raise ValueError("expected_dataset_order must be non-empty")
    if seen_datasets - set(expected_dataset_order):
        raise ValueError(
            "per_dataset_receipts 出現不在凍結順序裡的 dataset:"
            f" {sorted(seen_datasets - set(expected_dataset_order))}"
        )
    if overall_status == "BUILD_COMPLETE_AWAITING_VERIFICATION":
        if seen_datasets != set(expected_dataset_order):
            raise ValueError(
                "overall_status=BUILD_COMPLETE_AWAITING_VERIFICATION 要求"
                " per_dataset_receipts 涵蓋全部 dataset,缺"
                f" {sorted(set(expected_dataset_order) - seen_datasets)}"
            )
    else:  # BUILD_FAILED_PARTIAL
        if seen_datasets == set(expected_dataset_order):
            raise ValueError(
                "overall_status=BUILD_FAILED_PARTIAL 但 per_dataset_receipts"
                " 涵蓋了全部 dataset——失敗的 run 不應該有完整的成功清單"
            )

    _require_canonical_bootstrap_tool_inventory(bootstrap_tool_inventory)
    _require_canonical_normalized_pair_list(
        "lock_selected_inventory", lock_selected_inventory
    )
    _require_canonical_installed_inventory(installed_inventory)
    _require_sha256_hex(
        "lock_selected_inventory_sha256", lock_selected_inventory_sha256
    )
    _require_sha256_hex("installed_inventory_sha256", installed_inventory_sha256)
    recomputed_lock_sha = sha256_hex(
        canonical_json_bytes(lock_selected_inventory, sort_keys=False)
    )
    if recomputed_lock_sha != lock_selected_inventory_sha256:
        raise ValueError(
            "lock_selected_inventory_sha256 跟從 lock_selected_inventory"
            f" canonical 序列化重算的結果不符:傳入值={lock_selected_inventory_sha256!r}"
            f" 重算值={recomputed_lock_sha!r}"
        )
    recomputed_installed_sha = sha256_hex(
        canonical_json_bytes(installed_inventory, sort_keys=False)
    )
    if recomputed_installed_sha != installed_inventory_sha256:
        raise ValueError(
            "installed_inventory_sha256 跟從 installed_inventory canonical"
            f" 序列化重算的結果不符:傳入值={installed_inventory_sha256!r}"
            f" 重算值={recomputed_installed_sha!r}"
        )

    receipt = dict(base)
    receipt["schema"] = AGGREGATE_BUILD_RECEIPT_SCHEMA_TAG
    receipt["per_dataset_receipts"] = per_dataset_receipts
    receipt["lock_selected_inventory"] = lock_selected_inventory
    receipt["lock_selected_inventory_sha256"] = lock_selected_inventory_sha256
    receipt["installed_inventory"] = installed_inventory
    receipt["installed_inventory_sha256"] = installed_inventory_sha256
    receipt["bootstrap_tool_inventory"] = bootstrap_tool_inventory
    return receipt


def validate_aggregate_build_receipt(receipt: dict, *, expected_dataset_order) -> None:
    if not isinstance(receipt, dict):
        raise TypeError(f"receipt must be a dict, got {type(receipt).__name__}")
    expected_keys = set(AGGREGATE_BUILD_RECEIPT_FIELDS)
    keys = set(receipt)
    if keys != expected_keys:
        raise ValueError(
            "aggregate build receipt 欄位集合不符:缺"
            f" {sorted(expected_keys - keys)},多 {sorted(keys - expected_keys)}"
        )
    if receipt["schema"] != AGGREGATE_BUILD_RECEIPT_SCHEMA_TAG:
        raise ValueError(
            f"schema 必須是 {AGGREGATE_BUILD_RECEIPT_SCHEMA_TAG!r},實際"
            f" {receipt['schema']!r}"
        )
    identity_fields = {k: receipt[k] for k in TOP_LEVEL_IDENTITY_FIELDS}
    validate_top_level_identity_fields(identity_fields)
    if receipt["overall_status"] not in OVERALL_STATUS_VALUES:
        raise ValueError(
            f"overall_status 必須是 {OVERALL_STATUS_VALUES} 之一,實際"
            f" {receipt['overall_status']!r}"
        )
    _require_sha256_hex(
        "environment_creation_receipt_sha256",
        receipt["environment_creation_receipt_sha256"],
    )
    _require_sha256_hex(
        "environment_creation_identity", receipt["environment_creation_identity"]
    )
    per_dataset_receipts = _require_per_dataset_receipts(receipt["per_dataset_receipts"])
    seen = {i["dataset"] for i in per_dataset_receipts}
    expected_dataset_order = tuple(expected_dataset_order)
    if seen - set(expected_dataset_order):
        raise ValueError(
            "per_dataset_receipts 出現不在凍結順序裡的 dataset:"
            f" {sorted(seen - set(expected_dataset_order))}"
        )
    if receipt["overall_status"] == "BUILD_COMPLETE_AWAITING_VERIFICATION":
        if seen != set(expected_dataset_order):
            raise ValueError(
                "overall_status=BUILD_COMPLETE_AWAITING_VERIFICATION 但"
                " per_dataset_receipts 沒有涵蓋全部 dataset"
            )
    _require_canonical_bootstrap_tool_inventory(receipt["bootstrap_tool_inventory"])
    _require_canonical_normalized_pair_list(
        "lock_selected_inventory", receipt["lock_selected_inventory"]
    )
    _require_canonical_installed_inventory(receipt["installed_inventory"])
    recomputed_lock_sha = sha256_hex(
        canonical_json_bytes(receipt["lock_selected_inventory"], sort_keys=False)
    )
    if recomputed_lock_sha != receipt["lock_selected_inventory_sha256"]:
        raise ValueError("lock_selected_inventory_sha256 跟重算結果不符")
    recomputed_installed_sha = sha256_hex(
        canonical_json_bytes(receipt["installed_inventory"], sort_keys=False)
    )
    if recomputed_installed_sha != receipt["installed_inventory_sha256"]:
        raise ValueError("installed_inventory_sha256 跟重算結果不符")


def write_aggregate_build_receipt(path, receipt: dict, *, expected_dataset_order) -> tuple:
    validate_aggregate_build_receipt(receipt, expected_dataset_order=expected_dataset_order)
    return write_receipt_json_atomic(path, receipt)


# ----------------------------------------------------------------------------
# 15. 11-dataset stop-on-first-failure 協調(§D Phase B / builder 職責)。
#     只接受注入的 `dataset_order`/`load_dataset_fn` 等 callable,不 import
#     `tej_importer`、不觸碰真實 `tej_cache`/`DataExport0806`——把這些
#     callable 接到 `tej_importer.load_source()` 跟真正的候選 parquet
#     寫入,是另一個、本輪不做的 Phase B 執行入口該做的事(`main()` 依然
#     只印 Phase B 未授權訊息、回傳非 0,見下方 CLI 章節)。
# ----------------------------------------------------------------------------

_COMBINED_DF_SUMMARY_FIELDS = frozenset(
    {"source_files", "row_count", "stock_count", "date_min", "date_max", "final_null_counts"}
)


def _require_combined_df_summary(value) -> dict:
    if not isinstance(value, dict) or set(value) != _COMBINED_DF_SUMMARY_FIELDS:
        raise ValueError(f"combined_df_summary 欄位集合不符,實際 {value!r}")
    return value


def _best_effort_discard_staging(discard_staged_dataset_fn, dataset: str, staging_token) -> None:
    """清除 `dataset` 的 staging 輸出——best-effort:清除本身失敗不能蓋掉
    真正造成這個 dataset 失敗的原始例外(呼叫端已經在 `except` 區塊裡,原始
    例外才是要往外拋的那個)。"""
    try:
        discard_staged_dataset_fn(dataset, staging_token)
    except Exception:  # noqa: BLE001 -- best-effort cleanup,不重新拋出
        pass


def _best_effort_unlink(path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def run_build_stop_on_first_failure(
    *,
    dataset_order,
    load_dataset_fn,
    stage_dataset_fn,
    publish_staged_dataset_fn,
    discard_staged_dataset_fn,
    snapshot_id_v1_value: str,
    run_id: str,
    per_dataset_receipt_dir,
    quality_sidecar_dir,
    make_receipt_filename_fn,
    make_sidecar_filename_fn,
    now_fn,
) -> dict:
    """依 `dataset_order` 凍結順序逐一處理每個 dataset,任一個失敗立刻停止
    (§D Phase B 執行協定:「第一個失敗的 dataset 之後,整個 Phase B 立刻
    停止,不繼續嘗試剩下的 dataset」)。

    **Codex review 修正(REQUEST CHANGES 第 3 項)**:原本的版本在
    accounting/sidecar/receipt 這些**後段驗證步驟完成之前**就已經呼叫
    `persist_dataset_fn` 把候選資料「發布」進 `cache/<dataset>/`——如果
    accounting 交叉核對(`build_per_dataset_receipt_success`)或 sidecar/
    receipt 寫入之後才失敗,那個已經發布的候選資料完全沒有被回滾,造成
    「N 的 candidate parquet 已經發布,但 N 的正式狀態是 DATASET_BUILD_
    FAILED」這種不一致狀態。現在改成**dataset-level staging + atomic
    publish**:

    - `stage_dataset_fn(dataset: str, combined_df_summary: dict) ->
      staging_token`——呼叫端注入,只把候選資料寫進**暫存**位置(不是
      `cache/<dataset>/` 本身),回傳一個不透明的 `staging_token`(原樣
      傳給 `publish_staged_dataset_fn`/`discard_staged_dataset_fn`,這個
      模組不檢查它的內容)。
    - `publish_staged_dataset_fn(dataset: str, staging_token) -> None`——
      **只有在** sidecar 寫入成功、accounting 交叉核對通過(`build_
      per_dataset_receipt_success` 沒有 raise)、per-dataset receipt 也
      成功寫入之後,才會被呼叫——這是唯一讓 dataset 的候選資料真正變成
      `cache/<dataset>/` 底下可見內容的時機點(呼叫端應該用一次atomic
      rename/等價機制實作,不是逐檔案慢慢搬)。
    - `discard_staged_dataset_fn(dataset: str, staging_token) -> None`——
      dataset 處理過程**任何一步**失敗(load/stage/sidecar 建構或寫入/
      accounting/receipt 建構或寫入/publish 本身)都會被呼叫,清除這個
      dataset 的 staging 輸出;呼叫本身是 best-effort(清除失敗不會蓋掉
      原始例外)。**已發布(1..N-1)的 dataset 完全不受影響**——publish 是
      單向、只在完整驗證通過後才發生的動作。
    - 如果 sidecar 已經成功寫入磁碟,但**之後**(accounting/receipt 寫入/
      publish)才失敗,這份已經寫出的 sidecar 檔案也會被刪除(best-effort)
      ——不留下一份「品質證據看起來自洽,但這個 dataset 的正式狀態是
      FAILED」的孤兒 sidecar。per-dataset receipt 最終只會有一份:成功時
      是 `DATASET_BUILD_SUCCEEDED`,任何步驟失敗則是
      `DATASET_BUILD_FAILED`,不會兩者都留下。

    - `load_dataset_fn(dataset: str) -> (combined_df_summary: dict,
      evidence_bundle: dict)`——呼叫端注入,對應真正的
      `tej_importer.load_source(dataset, return_evidence=True)`;這裡不
      import/呼叫 `tej_importer` 本身。`combined_df_summary` 是呼叫端已經
      算好的一組摘要值(不是完整 DataFrame——本模組不處理 pandas 物件),固定
      鍵集合見 `_require_combined_df_summary`;`evidence_bundle` 沿用
      `tej_importer._build_evidence_bundle` 的鍵,額外允許一個可選的
      `supplement_provenance` 鍵(`build_supplement_provenance` 的輸出,
      3/11 個 dataset 才有,其餘為 `None`/缺席)。

    回傳 `{"overall_status": ..., "per_dataset_receipts": [...],
    "failed_dataset": str | None, "succeeded_datasets": [...]}`,供呼叫端
    餵給 `build_aggregate_build_receipt`。"""
    dataset_order = tuple(dataset_order)
    if not dataset_order:
        raise ValueError("dataset_order must be non-empty")
    if len(set(dataset_order)) != len(dataset_order):
        raise ValueError(f"dataset_order 有重複項:{dataset_order!r}")

    per_dataset_receipts = []
    succeeded_datasets = []
    failed_dataset = None

    for dataset in dataset_order:
        start_ts = now_fn()
        staging_token = None
        staging_staged = False
        sidecar_written_path = None
        receipt_written_path = None
        try:
            combined_df_summary, evidence_bundle = load_dataset_fn(dataset)
            combined_df_summary = _require_combined_df_summary(combined_df_summary)

            staging_token = stage_dataset_fn(dataset, combined_df_summary)
            staging_staged = True

            sidecar = build_quality_sidecar(
                dataset=dataset, cell_records=evidence_bundle["cell_records"]
            )
            sidecar_filename = make_sidecar_filename_fn(dataset)
            sidecar_target = guard_receipt_filename(quality_sidecar_dir, sidecar_filename)
            sidecar_abs_path, sidecar_sha256 = write_quality_sidecar(
                sidecar_target, sidecar
            )
            sidecar_written_path = sidecar_abs_path

            supplement_provenance = evidence_bundle.get("supplement_provenance")

            # accounting 交叉核對發生在這裡(§C.9 兩組等式)——任一項不成立
            # 直接 raise,此時 staging 輸出跟已經寫出的 sidecar 都還沒有被
            # publish/視為正式,下面的 except 會把兩者一起清掉。
            receipt = build_per_dataset_receipt_success(
                snapshot_id_v1_value=snapshot_id_v1_value,
                run_id=run_id,
                dataset=dataset,
                start_timestamp_utc=start_ts,
                end_timestamp_utc=now_fn(),
                source_files=combined_df_summary["source_files"],
                row_count=combined_df_summary["row_count"],
                stock_count=combined_df_summary["stock_count"],
                date_min=combined_df_summary["date_min"],
                date_max=combined_df_summary["date_max"],
                schema_metadata=evidence_bundle["schema"],
                coverage_matrix=evidence_bundle["coverage_matrix"],
                duplicate_mapping=evidence_bundle["duplicate_mapping"],
                final_null_causes=evidence_bundle["final_null_causes"],
                final_null_counts_from_output=combined_df_summary["final_null_counts"],
                sidecar_path=str(sidecar_abs_path),
                sidecar_sha256=sidecar_sha256,
                sidecar_record_count=sidecar["record_count"],
                per_file_stage_one_counts=evidence_bundle["per_file_stage_one_counts"],
                supplement_provenance=supplement_provenance,
            )
            receipt_filename = make_receipt_filename_fn(dataset)
            receipt_target = guard_receipt_filename(per_dataset_receipt_dir, receipt_filename)
            receipt_abs_path, receipt_sha256 = write_per_dataset_receipt(
                receipt_target, receipt
            )
            receipt_written_path = receipt_abs_path

            # **只有在這裡**(sidecar 寫入成功 + accounting 通過 + receipt
            # 寫入成功之後)才真正 publish——這是修正的核心:發布時機點
            # 移到全部後段驗證完成之後,不是 stage 完就發布。
            publish_staged_dataset_fn(dataset, staging_token)

            per_dataset_receipts.append(
                {"dataset": dataset, "path": str(receipt_abs_path), "sha256": receipt_sha256}
            )
            succeeded_datasets.append(dataset)
        except Exception as exc:  # noqa: BLE001 -- stop-on-first-failure 必須攔截任何例外類型
            if staging_staged:
                _best_effort_discard_staging(discard_staged_dataset_fn, dataset, staging_token)
            if sidecar_written_path is not None:
                _best_effort_unlink(sidecar_written_path)
            if receipt_written_path is not None:
                # 這是一份還沒被視為正式(尚未 append 進 per_dataset_receipts)
                # 就失敗的成功 receipt——不能跟接下來要寫的失敗 receipt 並存
                # (兩者用同一個檔名),先清掉。
                _best_effort_unlink(receipt_written_path)

            failure_receipt = build_per_dataset_receipt_failure(
                snapshot_id_v1_value=snapshot_id_v1_value,
                run_id=run_id,
                dataset=dataset,
                start_timestamp_utc=start_ts,
                end_timestamp_utc=now_fn(),
                exit_code=1,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            receipt_filename = make_receipt_filename_fn(dataset)
            receipt_target = guard_receipt_filename(per_dataset_receipt_dir, receipt_filename)
            receipt_abs_path, receipt_sha256 = write_per_dataset_receipt(
                receipt_target, failure_receipt
            )
            per_dataset_receipts.append(
                {"dataset": dataset, "path": str(receipt_abs_path), "sha256": receipt_sha256}
            )
            failed_dataset = dataset
            break

    overall_status = (
        "BUILD_FAILED_PARTIAL"
        if failed_dataset is not None
        else "BUILD_COMPLETE_AWAITING_VERIFICATION"
    )
    return {
        "overall_status": overall_status,
        "per_dataset_receipts": per_dataset_receipts,
        "failed_dataset": failed_dataset,
        "succeeded_datasets": succeeded_datasets,
    }


# ----------------------------------------------------------------------------
# 16. Import 白名單靜態檢查(§C.6)——涵蓋 `tej_importer.py` 跟這個 builder
#     腳本自己兩份。純 `ast.parse` 解析,不 `exec`/`import` 目標檔案本身
#     (避免觸發它的檔案系統/套件相依副作用)。
# ----------------------------------------------------------------------------

_FORBIDDEN_IMPORT_TOP_MODULES = frozenset({"core", "beat_0050"})


def _is_forbidden_import(module_name: str) -> bool:
    if not module_name:
        return False
    top = module_name.split(".")[0]
    return top in _FORBIDDEN_IMPORT_TOP_MODULES


def check_import_whitelist(path) -> None:
    """靜態解析 `path` 這份 `.py` 檔案的 import 清單,任何 `core`/
    `beat_0050`(或其子模組)一律 fail-closed raise——§C.6:「這條檢查應該
    同時涵蓋 tej_importer.py 跟新 builder 腳本兩份檔案」,呼叫端對兩份檔案
    都要各呼叫一次這支函式。"""
    import ast

    path = Path(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_import(alias.name):
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and _is_forbidden_import(module):
                violations.append(module)
    if violations:
        raise ValueError(
            f"{path}:出現不在白名單裡的 import(core/beat_0050 家族,§C.6"
            f" 禁止績效/OOS/Gate 相關 import 混進確定性解析/建置程式碼):"
            f" {sorted(set(violations))}"
        )


# ----------------------------------------------------------------------------
# 17. CLI 安全邊界
#    Import 這個模組本身完全不得有檔案系統副作用(上面每一個函式都是純
#    函式或只接受注入路徑,模組層級沒有任何常數指向真實的
#    tej_exports/DataExport0806、~/tej_cache 等路徑)。
#    這一輪**不核准 Phase B**,CLI 預設(也是唯一)行為是印一則說明訊息、
#    回傳非 0——不解析 argv 旗標(所以不存在任何旗標組合能悄悄跑 Phase
#    B),不讀任何來源檔案,不建立任何目錄。
# ----------------------------------------------------------------------------


def main(argv=None) -> int:
    """預設(也是唯一)行為:印出 Phase B 未授權的說明、回傳非 0。刻意不
    解析 `argv`(內容被忽略)——這樣不存在任何旗標組合可以繞過這個邊界。"""
    del argv  # 刻意忽略:不提供任何可以觸發 Phase B 的旗標路徑。
    print(
        "build_v2_candidate: Phase B 尚未獲得授權"
        "(docs/預註冊_DataExport0806_V2隔離建置.md 現況"
        " PREREG_READY_IMPLEMENTATION_NOT_AUTHORIZED / BUILD_NOT_RUN)。"
        " 這個 CLI 入口本輪只是佔位——不讀任何來源檔案、不建立任何輸出目錄。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
