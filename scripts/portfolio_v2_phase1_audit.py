"""
Phase 1 Full-Universe Audit —— 全市場資料結構稽核
================================================================================
規格:docs/規格_推薦投組系統V2_Phase1_FullUniverseAudit.md(先讀,行為分歧以該檔為準)。

只做結構稽核:檔案可讀性、schema(必要欄位)、主鍵重複/缺值、日期可解析性、
檔名與 stock_id 一致性、零列檔案;缺值/非有限值/字串轉數值失敗數與覆蓋起訖只記錄,
不判定及格。

讀檔安全(Codex review 修正必修1):一律先讀 parquet schema/row-count metadata
(不觸碰任何列資料),再只投影(`pd.read_parquet(..., columns=[...])`)本次允許
讀取的欄位集合 —— `obs_alpha` 的投影集合明確排除 `fwd`(研究紀律禁止使用的反向
偏誤欄位),不會有任何路徑把它整檔載入。見 `read_projected_parquet()`。

明確不做(規格 §8):不計算報酬分布/均值/IC/CAGR/Sharpe/MDD/Top K/勝率/alpha,
不產生任何 Z1/E0/E1 訊號或投組建議,不讀取/修改 Gate 1/Gate 2/C3 產物,
不讀取 obs_alpha.fwd,不修改任何被稽核檔案(全程唯讀)。

CLI 預設不掃描任何真實資料 —— 見 main() 與規格 §6 兩道旗標。
`run_audit()` 本身也不提供任何真實路徑預設值(Codex review 修正必修3)——
`dataset_roots`/`research_base` 必須由呼叫端顯式傳入,省略即 TypeError。
================================================================================
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


# =============================================================================
# Dataset registry —— 規格 §2.1(類別 A:6 個逐股 TEJ/FinMind 原始檔)
# =============================================================================

@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    root_env: str
    default_root: Path
    subdir: str
    required_columns: tuple
    date_column: str
    key_columns: tuple
    filename_is_stock_id: bool
    numeric_check_columns: tuple = ()

    def root_dir(self) -> Path:
        override = os.environ.get(self.root_env)
        base = Path(override) if override else self.default_root
        return base / self.subdir


def _default_dataset_specs() -> dict:
    tej_root = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
    finmind_root = Path(os.environ.get("FINMIND_CACHE", str(Path.home() / "finmind_cache")))
    specs = [
        DatasetSpec(
            dataset_id="tej_price_valuation", root_env="TEJ_CACHE", default_root=tej_root,
            subdir="price_valuation",
            required_columns=("stock_id", "date", "open", "max", "min", "close",
                               "Trading_Volume", "PER_TSE", "PER_TEJ", "PBR_TSE",
                               "PBR_TEJ", "dividend_yield_TSE"),
            date_column="date", key_columns=("date",), filename_is_stock_id=True,
            numeric_check_columns=("open", "max", "min", "close", "Trading_Volume",
                                    "PER_TSE", "PER_TEJ", "PBR_TSE", "PBR_TEJ",
                                    "dividend_yield_TSE"),
        ),
        DatasetSpec(
            dataset_id="tej_institutional_gross", root_env="TEJ_CACHE", default_root=tej_root,
            subdir="institutional_gross",
            required_columns=("stock_id", "date", "foreign_buy", "foreign_sell",
                               "trust_buy", "trust_sell", "foreign_holding_pct",
                               "trust_holding_pct"),
            date_column="date", key_columns=("date",), filename_is_stock_id=True,
            numeric_check_columns=("foreign_buy", "foreign_sell", "trust_buy",
                                    "trust_sell", "foreign_holding_pct", "trust_holding_pct"),
        ),
        DatasetSpec(
            dataset_id="tej_margin_balance", root_env="TEJ_CACHE", default_root=tej_root,
            subdir="margin_balance",
            required_columns=("stock_id", "date", "margin_balance", "short_balance"),
            date_column="date", key_columns=("date",), filename_is_stock_id=True,
            numeric_check_columns=("margin_balance", "short_balance"),
        ),
        DatasetSpec(
            dataset_id="tej_tdcc_weekly", root_env="TEJ_CACHE", default_root=tej_root,
            subdir="tdcc_weekly",
            required_columns=("stock_id", "date", "ratio_1000up", "ratio_le1",
                               "ratio_1to5", "ratio_5to10", "holders", "total_lots_thousand"),
            date_column="date", key_columns=("date",), filename_is_stock_id=True,
            numeric_check_columns=("ratio_1000up", "ratio_le1", "ratio_1to5",
                                    "ratio_5to10", "holders", "total_lots_thousand"),
        ),
        DatasetSpec(
            dataset_id="tej_director_pledge", root_env="TEJ_CACHE", default_root=tej_root,
            subdir="director_pledge",
            required_columns=("stock_id", "date", "pledge_pct", "director_holding_pct",
                               "group_name"),
            date_column="date", key_columns=("date",), filename_is_stock_id=True,
            numeric_check_columns=("pledge_pct", "director_holding_pct"),
        ),
        DatasetSpec(
            dataset_id="finmind_price", root_env="FINMIND_CACHE", default_root=finmind_root,
            subdir="TaiwanStockPrice",
            required_columns=("date", "stock_id", "open", "max", "min", "close",
                               "Trading_Volume"),
            date_column="date", key_columns=("date",), filename_is_stock_id=True,
            numeric_check_columns=("open", "max", "min", "close", "Trading_Volume"),
        ),
    ]
    return {s.dataset_id: s for s in specs}


DATASET_SPECS = _default_dataset_specs()

# 規格 §2.2 —— obs_alpha 刻意不含 `fwd`(研究紀律禁止使用的反向偏誤欄位)。
# 這份清單同時是「允許讀取的投影欄位集合」的上限:audit_file()/read_projected_parquet()
# 只會用 `columns=<這份清單 ∩ 實際 schema>` 讀取,schema 裡任何不在清單內的欄位
# (例如 obs_alpha 若真的存在 `fwd`)永遠不會出現在傳給 pd.read_parquet 的 columns 參數裡。
OBS_ALPHA_REQUIRED_COLUMNS = ("as_of", "stock_id", "adv20", "listed_ok")
OBS_ALPHA_KEY_COLUMNS = ("as_of", "stock_id")
EXEC_RET_REQUIRED_COLUMNS = ("as_of", "stock_id", "fwd_x", "px_in", "tick_slip")
EXEC_RET_KEY_COLUMNS = ("as_of", "stock_id")
EXEC_RET_NUMERIC_CHECK_COLUMNS = ("fwd_x",)  # 規格明定:僅 fwd_x 做缺值/非有限值檢查

# 規格 §2.3 —— frozen 真身面板(1 個群組,glob `realbody_scores*.parquet`),
# 只讀 hash/schema/鍵完整性。
REALBODY_REQUIRED_COLUMNS = ("as_of", "stock_id", "real_composite", "rating",
                              "f_fund", "f_val", "f_tech", "f_mom", "f_whale")
REALBODY_KEY_COLUMNS = ("as_of", "stock_id")


# =============================================================================
# 基礎工具
# =============================================================================

def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _parquet_metadata(path: Path) -> tuple:
    """只讀 parquet schema 與列數(footer metadata),不觸碰任何一個儲存格的實際值。"""
    pf = pq.ParquetFile(path)
    columns = list(pf.schema_arrow.names)
    num_rows = pf.metadata.num_rows
    return columns, num_rows


def read_projected_parquet(path: Path, allowed_columns: tuple) -> tuple:
    """讀取資料值的唯一入口(Codex review 修正必修1)。

    步驟:①先讀 schema metadata(不讀列資料)判斷哪些 `allowed_columns` 真的存在;
    ②只用 `columns=` 投影**存在於 schema 且在 `allowed_columns` 內**的欄位;
    ③schema 裡任何不在 `allowed_columns` 的欄位一律不會出現在傳給
    `pd.read_parquet` 的 `columns=` 參數裡,因此永遠不會被讀入記憶體
    —— 這是 `obs_alpha.fwd` 被排除的實際落地機制,不只是事後不列入輸出。

    回傳 `(df, missing_columns, num_rows)`。
    """
    schema_columns, num_rows = _parquet_metadata(path)
    missing_columns = [c for c in allowed_columns if c not in schema_columns]
    projection = [c for c in allowed_columns if c in schema_columns]
    if projection:
        df = pd.read_parquet(path, columns=projection)
    else:
        df = pd.DataFrame(index=pd.RangeIndex(num_rows))
    return df, missing_columns, num_rows


def _null_nonfinite_and_coercion_counts(df: pd.DataFrame, columns: tuple) -> tuple:
    """只記錄,不判定及格 —— 規格 §5。

    三個計數是**互斥的異常分類**(同一列在同一欄只會落入其中一種,不會重複計),
    但**不加總覆蓋該欄全部列**——其餘列是可正常解析的 finite 值,不落在任何一個
    計數裡(Codex review 第二輪修正必修2:先前的 docstring 誤寫成「加總覆蓋全部
    列」,並不正確):
      `null_counts`             —— 原始值本來就是缺值(NaN/None)
      `non_finite_counts`       —— 轉數值後是 +-inf(原始值非缺值)
      `coercion_failure_counts` —— 原始值非缺值,但轉數值失敗變成 NaN(例如字串 "abc")

    Codex review 第一輪修正必修7:先前版本會讓字串型雜訊「既不算 null 也不算
    non-finite」而在計數上消失,`coercion_failure_counts` 補上這個缺口。
    """
    null_counts, non_finite_counts, coercion_failure_counts = {}, {}, {}
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col]
        raw_null = s.isna()
        null_counts[col] = int(raw_null.sum())
        numeric = pd.to_numeric(s, errors="coerce")
        numeric_arr = numeric.to_numpy(dtype="float64")
        finite = np.isfinite(numeric_arr)
        is_nan_after = np.isnan(numeric_arr)
        non_finite_counts[col] = int((~finite & ~is_nan_after).sum())
        coercion_failure_counts[col] = int((is_nan_after & ~raw_null.to_numpy()).sum())
    return null_counts, non_finite_counts, coercion_failure_counts


# =============================================================================
# 檔案層級稽核 —— 規格 §3、§4.1
# =============================================================================

@dataclass
class FileFinding:
    path: str
    status: str
    read_ok: bool
    read_error: Optional[str]
    missing_columns: list
    empty_file: bool
    duplicate_key_rows: int
    key_column_nulls: int
    bad_date_rows: int
    filename_stock_id_mismatch_rows: int
    measured: dict
    sha256: Optional[str]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "status": self.status,
            "read_ok": self.read_ok,
            "read_error": self.read_error,
            "missing_columns": self.missing_columns,
            "empty_file": self.empty_file,
            "duplicate_key_rows": self.duplicate_key_rows,
            "key_column_nulls": self.key_column_nulls,
            "bad_date_rows": self.bad_date_rows,
            "filename_stock_id_mismatch_rows": self.filename_stock_id_mismatch_rows,
            "measured": self.measured,
            "sha256": self.sha256,
        }


def _fail_finding(name: str, error: str, sha: Optional[str]) -> FileFinding:
    return FileFinding(
        path=name, status="FAIL", read_ok=False, read_error=error,
        missing_columns=[], empty_file=False, duplicate_key_rows=0, key_column_nulls=0,
        bad_date_rows=0, filename_stock_id_mismatch_rows=0, measured={}, sha256=sha,
    )


def audit_file(path, required_columns: tuple, key_columns: tuple,
                date_column: Optional[str] = None, filename_is_stock_id: bool = False,
                numeric_check_columns: tuple = (), compute_hash: bool = False) -> FileFinding:
    """單一 parquet 檔的結構稽核。唯讀,且只投影 `required_columns`
    (見 `read_projected_parquet`)—— 這是規格 §2.2 obs_alpha 排除 `fwd` 的實際機制。

    讀檔失敗(含 sha256 讀取失敗、schema metadata 讀取失敗)一律回傳 FAIL 且記錄
    例外訊息,不吞例外、不讓例外往上炸掉整個 run_audit()(本函式本身不對外拋出
    例外,由呼叫端逐檔取回傳值)。0 列的合法 schema 檔案視為 `empty_file`,
    fail-closed(規格 §4.1/§5 修正必修2)。
    """
    path = Path(path)

    sha = None
    if compute_hash:
        try:
            sha = sha256_file(path)
        except Exception as e:  # noqa: BLE001 - 讀檔失敗必須被記錄,不得靜默跳過
            return _fail_finding(path.name, f"sha256 讀取失敗 {type(e).__name__}: {e}", None)

    try:
        df, missing_columns, num_rows = read_projected_parquet(path, required_columns)
    except Exception as e:  # noqa: BLE001 - 同上
        return _fail_finding(path.name, f"{type(e).__name__}: {e}", sha)

    empty_file = (num_rows == 0)

    dup_rows = 0
    key_nulls = 0
    if all(k in df.columns for k in key_columns):
        key_nulls = int(df[list(key_columns)].isna().any(axis=1).sum())
        dup_rows = int(df.duplicated(subset=list(key_columns), keep=False).sum())

    bad_dates = 0
    date_min = date_max = None
    if date_column and date_column in df.columns:
        parsed = pd.to_datetime(df[date_column], errors="coerce")
        bad_dates = int(parsed.isna().sum())
        if parsed.notna().any():
            date_min, date_max = str(parsed.min()), str(parsed.max())

    mismatch_rows = 0
    if filename_is_stock_id and "stock_id" in df.columns:
        stem = path.stem
        mismatch_rows = int((df["stock_id"].astype(str) != stem).sum())

    null_counts, non_finite_counts, coercion_failure_counts = \
        _null_nonfinite_and_coercion_counts(df, numeric_check_columns)

    status = "FAIL" if (missing_columns or empty_file or dup_rows > 0 or key_nulls > 0
                        or bad_dates > 0 or mismatch_rows > 0) else "PASS"

    return FileFinding(
        path=path.name, status=status, read_ok=True, read_error=None,
        missing_columns=missing_columns, empty_file=empty_file,
        duplicate_key_rows=dup_rows, key_column_nulls=key_nulls, bad_date_rows=bad_dates,
        filename_stock_id_mismatch_rows=mismatch_rows,
        measured={
            "date_min": date_min, "date_max": date_max,
            "null_counts": null_counts, "non_finite_counts": non_finite_counts,
            "coercion_failure_counts": coercion_failure_counts,
            "row_count": int(num_rows),
        },
        sha256=sha,
    )


# =============================================================================
# Dataset / frozen-group 層級稽核 —— 規格 §4.2
# =============================================================================

def audit_dataset(spec: DatasetSpec, root: Path) -> dict:
    """`root` 為必要參數(不再有預設值)—— 呼叫端必須顯式決定要掃哪個目錄。"""
    root = Path(root)
    if not root.exists():
        return {"status": "MISSING", "root": str(root), "file_count": 0, "files": []}
    files = sorted(root.glob("*.parquet"))
    if not files:
        return {"status": "EMPTY", "root": str(root), "file_count": 0, "files": []}
    findings = [
        audit_file(p, spec.required_columns, spec.key_columns, spec.date_column,
                   spec.filename_is_stock_id, spec.numeric_check_columns)
        for p in files
    ]
    status = "FAIL" if any(f.status == "FAIL" for f in findings) else "PASS"
    return {
        "status": status, "root": str(root), "file_count": len(files),
        "files": [f.to_dict() for f in findings],
    }


def audit_obs_exec_pair(obs_alpha_path, exec_ret_path) -> dict:
    """obs_alpha/exec_ret 各自的結構稽核 + key-set 對齊(只記錄數量,不判定及格與否,
    規格 §2.2/§5)。

    `keyset_status`(Codex review 第二輪修正必修1)—— key-set 對齊**本身**這個量測
    動作是否成功,與「兩邊鍵集合有沒有差異」是兩件事:量測失敗(例如檔案在兩次
    read 之間被搬走、schema 異常導致投影讀取炸掉)不得只靜靜寫進 `measured.error`
    然後被上層當作「沒事」——那會讓 `overall_status` 誤報 `PASS`。

      - `PASS`         —— 兩檔都存在,key-set 量測成功
      - `NOT_MEASURED` —— 任一檔缺席(這個 gap 已經由 `obs_alpha_status`/
                          `exec_ret_status == MISSING` 反映,不必重複算兩次)
      - `FAIL`         —— 兩檔都存在,但量測本身丟例外;`run_audit()` 會把這個
                          `FAIL` 併入 `overall_status`(見 §4.3)
    """
    obs_alpha_path, exec_ret_path = Path(obs_alpha_path), Path(exec_ret_path)
    result = {
        "obs_alpha_status": "MISSING", "exec_ret_status": "MISSING",
        "obs_alpha": None, "exec_ret": None,
        "keyset_status": "NOT_MEASURED",
        "measured": {"only_in_obs_alpha": None, "only_in_exec_ret": None, "in_both": None},
    }

    if obs_alpha_path.exists():
        f = audit_file(obs_alpha_path, OBS_ALPHA_REQUIRED_COLUMNS, OBS_ALPHA_KEY_COLUMNS,
                        date_column="as_of")
        result["obs_alpha_status"] = f.status
        result["obs_alpha"] = f.to_dict()

    if exec_ret_path.exists():
        f = audit_file(exec_ret_path, EXEC_RET_REQUIRED_COLUMNS, EXEC_RET_KEY_COLUMNS,
                        date_column="as_of", numeric_check_columns=EXEC_RET_NUMERIC_CHECK_COLUMNS)
        result["exec_ret_status"] = f.status
        result["exec_ret"] = f.to_dict()

    if obs_alpha_path.exists() and exec_ret_path.exists():
        try:
            obs_keys, _, _ = read_projected_parquet(obs_alpha_path, OBS_ALPHA_KEY_COLUMNS)
            exec_keys, _, _ = read_projected_parquet(exec_ret_path, EXEC_RET_KEY_COLUMNS)
            obs_set = set(map(tuple, obs_keys.astype(str).to_numpy().tolist()))
            exec_set = set(map(tuple, exec_keys.astype(str).to_numpy().tolist()))
            result["keyset_status"] = "PASS"
            result["measured"] = {
                "only_in_obs_alpha": len(obs_set - exec_set),
                "only_in_exec_ret": len(exec_set - obs_set),
                "in_both": len(obs_set & exec_set),
            }
        except Exception as e:  # noqa: BLE001 - key-set 對齊本身失敗必須 fail-closed,不得吞例外
            result["keyset_status"] = "FAIL"
            result["measured"] = {"error": f"{type(e).__name__}: {e}"}

    return result


def audit_frozen_panels(paths, research_base_exists: bool) -> dict:
    """frozen realbody_scores*.parquet —— 只讀 hash/schema/鍵完整性,不修改(規格 §2.3)。

    Codex review 修正必修6:回傳值改為「群組」結構(`status` + `files`),
    讓 `run_audit()` 能把「一份 frozen 面板都沒有」計入 `has_gap`,
    不會被空字典靜默吃掉而誤報整體 PASS。
    """
    files = {}
    for p in sorted(Path(x) for x in paths):
        f = audit_file(p, REALBODY_REQUIRED_COLUMNS, REALBODY_KEY_COLUMNS,
                        date_column=None, filename_is_stock_id=False,
                        numeric_check_columns=(), compute_hash=True)
        files[p.name] = f.to_dict()

    if not research_base_exists:
        status = "MISSING"
    elif not files:
        status = "EMPTY"
    else:
        status = "FAIL" if any(v["status"] == "FAIL" for v in files.values()) else "PASS"

    return {"status": status, "files": files}


# =============================================================================
# 整份報告 —— 規格 §4.3、§7
# =============================================================================

def run_audit(dataset_roots: dict, research_base: Path) -> dict:
    """核心稽核入口。

    Codex review 修正必修3:**不提供任何真實路徑預設值**——`dataset_roots`/
    `research_base` 必須由呼叫端顯式傳入,省略即 `TypeError`(Python 層級的
    fail-closed)。`dataset_roots` 還必須覆蓋 `DATASET_SPECS` 的全部 key,
    缺一即 `ValueError`,不得靜默略過某個 dataset。

    這是測試唯一該呼叫、也是唯一不觸發 CLI 安全閘門的入口(規格 §6.3)——
    CLI 的 `main()` 只有在 `--execute` 與 `--i-understand-...` 都成立後,
    才會自己組出真實路徑呼叫這裡(見 `_real_dataset_roots`/`_real_research_base`)。
    """
    missing_keys = set(DATASET_SPECS) - set(dataset_roots)
    if missing_keys:
        raise ValueError(
            f"dataset_roots 缺少 {sorted(missing_keys)} 的顯式路徑;"
            f"run_audit() 不提供真實路徑預設值,必須逐一傳入(規格 §6.3)。")

    research_base = Path(research_base)

    datasets = {}
    for dataset_id, spec in sorted(DATASET_SPECS.items()):
        datasets[dataset_id] = audit_dataset(spec, dataset_roots[dataset_id])

    obs_exec = audit_obs_exec_pair(research_base / "obs_alpha.parquet",
                                    research_base / "exec_ret.parquet")

    research_base_exists = research_base.exists()
    panel_paths = (sorted(research_base.glob("realbody_scores*.parquet"))
                   if research_base_exists else [])
    frozen = audit_frozen_panels(panel_paths, research_base_exists)

    dataset_statuses = [d["status"] for d in datasets.values()]
    obs_exec_has_fail = (obs_exec["obs_alpha_status"] == "FAIL"
                         or obs_exec["exec_ret_status"] == "FAIL"
                         or obs_exec["keyset_status"] == "FAIL")
    has_gap = (any(s in ("MISSING", "EMPTY") for s in dataset_statuses)
               or obs_exec["obs_alpha_status"] == "MISSING"
               or obs_exec["exec_ret_status"] == "MISSING"
               or frozen["status"] in ("MISSING", "EMPTY"))

    if (any(s == "FAIL" for s in dataset_statuses) or frozen["status"] == "FAIL"
            or obs_exec_has_fail):
        overall = "FAIL"
    elif has_gap:
        overall = "PASS_WITH_GAPS"
    else:
        overall = "PASS"

    return {
        "spec_version": "1.0",
        "overall_status": overall,
        "datasets": datasets,
        "obs_exec_keyset": obs_exec,
        "frozen_panels": frozen,
    }


# =============================================================================
# CLI —— 規格 §6:預設不掃描真實資料,需雙旗標;單一旗標視為誤用(exit 2)
# =============================================================================

def _known_dataset_ids() -> list:
    return sorted(DATASET_SPECS) + ["obs_alpha", "exec_ret", "realbody_scores*(frozen group)"]


def _real_dataset_roots() -> dict:
    """只組路徑字串(讀環境變數),不做任何檔案 I/O —— 真正的讀取發生在 run_audit() 內。"""
    return {dsid: spec.root_dir() for dsid, spec in DATASET_SPECS.items()}


def _real_research_base() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "research_base"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 1 Full-Universe Audit —— 全市場資料結構稽核(唯讀)。"
                     "詳見 docs/規格_推薦投組系統V2_Phase1_FullUniverseAudit.md")
    parser.add_argument("--execute", action="store_true",
                         help="實際掃描真實快取目錄(規格 §6);不帶此旗標只印用法,不觸碰任何檔案")
    parser.add_argument("--i-understand-this-reads-real-cache", action="store_true",
                         dest="confirmed", help="雙重確認旗標,必須與 --execute 同時使用")
    parser.add_argument("--output", type=str, default=None,
                         help="將 JSON 報告寫到此路徑(預設印到 stdout)")
    args = parser.parse_args(argv)

    if not args.execute and not args.confirmed:
        print("本工具預設不掃描任何真實資料。")
        print("已知 dataset:", ", ".join(_known_dataset_ids()))
        print("要對真實 ~/tej_cache、~/finmind_cache、data/research_base 執行全市場稽核,")
        print("需同時帶 --execute --i-understand-this-reads-real-cache")
        return 0

    if not (args.execute and args.confirmed):
        missing = "--i-understand-this-reads-real-cache" if args.execute else "--execute"
        print(f"錯誤:只給了其中一道安全旗標,缺 {missing}。"
              f"兩者必須同時帶入才會掃描真實資料,單獨給任一道視為誤用,拒絕執行。",
              file=sys.stderr)
        return 2

    report = run_audit(dataset_roots=_real_dataset_roots(), research_base=_real_research_base())
    text = json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if report["overall_status"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
