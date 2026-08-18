# -*- coding: utf-8 -*-
"""institutional_gross_trust_holding_pct_adjudication.py — 一次性、唯讀的證據溯源腳本
(Round 8B review 初版,Round 9 review 修正)。

**這不是新的容忍門檻搜尋,也不是遷移核准。** 完整規則見
docs/資料快照遷移_DataExport0806.md §10——本檔只是把那份文件凍結的規則實作出來,
規則本身不在這裡定義,任何調整都要先改文件再改這裡。

範圍:anchor receipt (tej_exports/diff_receipts/full_population_diff_20260807T093225Z.json)
記錄的 institutional_gross 這一個 dataset、140,544 個重疊 key、六個欄位。anchor
receipt 是舊版 `_full_population_diff.py` 產生的,**沒有 parquet 檔案雜湊**——執行時
一律先對「現在」磁碟上的 parquet 建立唯讀 manifest 並精確重現 anchor 的統計數字,
任何一項兜不起來就以 ANCHOR_INPUT_IDENTITY_UNVERIFIED 中止,不往下做原始檔分類、
不重新產生任何一份 cache。

Round 9 review 修正 (相對於 Round 8 版本):
  · 原始檔驗證原本只在 filter 成 needed_keys 之後的小子集上做,而且只擋「衝突」
    的重複鍵、完全重複的列會被靜默去重。現在 `_validate_raw_keys` 在 filter
    **之前**對整份原始檔驗證:stock_id/date 無效直接 raise;**任何**重複鍵
    (不論是否衝突) 都直接 raise,兩份原始檔都不去重。驗證失敗會寫一份
    `RAW_SOURCE_VALIDATION_FAILED` receipt,記錄來源/種類/筆數/代表性樣本,不會
    讓無效列在錯誤發生前就被悄悄濾掉。
  · 原本轉換失敗的儲存格 (例如文字 ".") 轉成 NaN 之後,原始文字就從資料裡消失
    了,只留一個「這是 unparseable」的旗標。現在 `_build_evidence_for_subset`
    對每個 (key, 欄位) 保留 `raw_token`(原始文字,None 代表儲存格本來就空白)、
    `parsed_value`、`is_blank`、`is_unparseable`、`unit_scale` 五個獨立欄位,不
    讓 "." 只以 NaN 的形式存在。
  · 統計原本只到 max/median,現在對每個數值不等的實例額外記錄
    `signed_diff_new_minus_old`/`abs_diff`,並且有 `(column, exact diff)` 的完整
    分布 (不分箱、不設容忍值),null/unparseable 另外分開計數。
  · 按股票的分布原本只留 Top 20,現在完整保留全部股票的計數 (`classification_
    counts_by_stock`),Top 20 只是額外方便閱讀用的欄位。
  · `RAW_SOURCES_DIFFER` 的每一筆額外記錄並驗證
    `old_raw_matches_old_parquet`/`new_raw_matches_new_parquet` 兩個旗標,邏輯
    不成立直接 raise (防呆,不能讓分類名稱跟實際證據對不上)。
  · 這次執行的 receipt 用新檔名 (排他建立),`supersedes_for_review` 欄位指向
    Round 8 的 receipt (路徑+SHA-256),明講「不刪除、不覆寫」——兩份都保留。

Round 10 review 修正 (相對於 Round 9 版本):
  · Round 9 違反了「只授權一次」的明文範圍,實際執行了兩次——這是真的違規,不是
    「有誠實記錄下來就沒事」。Round 10 是重新凍結、單次執行的修正版本。
  · receipt 新增 `mismatch_records`:**每一個**不一致實例各一筆完整紀錄 (不是
    抽樣),欄位涵蓋 (stock_id,date,column)、mismatch_kind、雙邊 parquet 值、
    雙邊 raw token/解析值/空白狀態/無法解析狀態、unit_scale、分類、
    signed_diff_new_minus_old/abs_diff、`RAW_SOURCES_DIFFER` 的兩個驗證旗標。
    `validate_mismatch_records()` 在寫出前檢查筆數、`(stock_id,date,column)`
    唯一性、每筆的必要欄位,任一項不符直接 raise。
  · 新增 `summarize_records()`:receipt 裡所有 `classification_counts_*`/
    `diff_distribution_by_column` 欄位的**唯一**產生方式,只吃 `mismatch_records`
    這個 list of dict,不是從別的中間結構分岔計算——保證這些摘要真的可以「只從
    mismatch_records 重建」。`classification_samples` 降級成純粹方便閱讀的附加
    視圖 (每類最多 5 筆),不再是唯一的逐筆證據來源。
  · 舊的 `supersedes_for_review` 欄位換成 `prior_receipts_provenance`,同時標記
    Round 8 (`diagnostic_superseded`)、Round 9 第一次
    (`diagnostic_invalid_accounting`)、Round 9 第二次
    (`diagnostic_post_deviation_unauthorized_rerun`) 三份 receipt 的路徑/SHA-256/
    狀態——全部不刪除不修改,只在新 receipt 裡記錄。
  · 新增獨立的唯讀驗證器
    `scripts/institutional_gross_adjudication_verifier.py`,只接受既有 receipt
    路徑、重新計算並比對、不寫任何檔案、不呼叫這支腳本的 `main()`。

用法:python scripts/institutional_gross_trust_holding_pct_adjudication.py
      (無參數,所有路徑都是凍結常數,對應 anchor receipt 記錄的路徑)
"""
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import tej_importer  # noqa: E402  (借用 _parse_dates/_sha256_of,見模組 docstring)

ANCHOR_RECEIPT_PATH = PROJECT_ROOT / "tej_exports" / "diff_receipts" / \
    "full_population_diff_20260807T093225Z.json"
OLD_PARQUET_ROOT = Path(r"C:\Users\aaaai\tej_cache") / "institutional_gross"
NEW_PARQUET_ROOT = (Path(r"C:\Users\aaaai\AppData\Local\Temp\claude\C--dev"
                          r"\b2a9ba0e-e9a0-4c69-9808-b8aaa37c08de\scratchpad"
                          r"\tej_cache_round3") / "institutional_gross")
OLD_RAW_XLSX = PROJECT_ROOT / "tej_exports" / "inbox_chip_gross" / "法人毛額+持股率20260404-0716.xlsx"
NEW_RAW_XLSX = (PROJECT_ROOT / "tej_exports" / "DataExport0806" / "法人回測2004-20260806"
                 / "2025-20260806 法人.xlsx")
RECEIPT_DIR = PROJECT_ROOT / "tej_exports" / "diff_receipts"

# 之前三份 receipt 的出處標記 (Round 10 review):不刪除、不覆寫任何一份,只在
# 新 receipt 裡記錄它們的路徑/雜湊/明確的狀態標籤。Round 9 執行了兩次違反了
# 當輪「只授權一次」的明文範圍——這是真的違規,不是「有誠實記錄就沒事」;
# 兩份 Round 9 receipt 都只能當診斷用途,不能被當成正式有效的裁定結果。
PRIOR_RECEIPTS_PROVENANCE = {
    "round8": {
        "path": RECEIPT_DIR / "institutional_gross_adjudication_20260807T145805155908_921a469b.json",
        "status": "diagnostic_superseded",
    },
    "round9_first": {
        "path": RECEIPT_DIR / "institutional_gross_adjudication_20260807T152618418716_47c9e5b7.json",
        "status": "diagnostic_invalid_accounting",
    },
    "round9_second": {
        "path": RECEIPT_DIR / "institutional_gross_adjudication_20260807T153206693051_1d59726c.json",
        "status": "diagnostic_post_deviation_unauthorized_rerun",
    },
}

KEY_COLS = ["stock_id", "date"]
SIX_COLUMNS = ["foreign_buy", "foreign_sell", "trust_buy", "trust_sell",
               "foreign_holding_pct", "trust_holding_pct"]
LOT_TO_SHARE_COLUMNS = {"foreign_buy", "foreign_sell", "trust_buy", "trust_sell"}
PCT_COLUMNS = set(SIX_COLUMNS) - LOT_TO_SHARE_COLUMNS

# docs/資料快照遷移_DataExport0806.md §10.4 凍結的八個互斥分類。
CLASSIFICATIONS = (
    "RAW_KEY_MISSING", "UNRESOLVED_SCHEMA_OR_UNIT",
    "BOTH_RAW_MATCH_OLD", "BOTH_RAW_MATCH_NEW",
    "NEITHER_MATCH", "RAW_SOURCES_DIFFER",
    "OLD_RAW_ONLY_MATCH", "NEW_RAW_ONLY_MATCH",
)

# 舊/新原始檔的目標六欄中文欄名完全相同 (§10.3 表格),千股/張→股統一 ×1000,
# 持股率百分比原樣、不換算——跟 tej_importer.DATASETS["institutional_gross"] 目前
# 對新原始檔的 rename/thousand_cols 定義完全一致。
RAW_COLUMN_RENAME = {
    "外資買進張數": "foreign_buy", "外資賣出張數": "foreign_sell",
    "投信買進張數": "trust_buy", "投信賣出張數": "trust_sell",
    "外資總投資股率%": "foreign_holding_pct", "投信持股率%": "trust_holding_pct",
}

_INVALID_ID_STRINGS = {"", "nan", "none", "nat", "null", "na"}
_BLANK_TOKENS = {"", "nan", "none", "nat"}


def _sha256_of(path: Path) -> str:
    return tej_importer._sha256_of(path)


def build_manifest(root: Path) -> list:
    """對 parquet 目錄建立唯讀 manifest:relpath/size_bytes/sha256,依 relpath 排序。
    anchor receipt 沒有這個 (§10.5),這裡誠實地對「現在」的檔案建一份。"""
    if not root.exists():
        return []
    files = sorted(root.glob("*.parquet"))
    return [
        {"relpath": f.name, "size_bytes": f.stat().st_size, "sha256": _sha256_of(f)}
        for f in files
    ]


def load_parquet_dir(root: Path) -> pd.DataFrame:
    files = sorted(root.glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=KEY_COLS + SIX_COLUMNS)
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def compute_structural_stats(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    """跟 anchor receipt institutional_gross 條目同一組欄位名稱/語意 (§10.5 要求
    逐項精確重現)。"""
    old_keys = set(zip(old["stock_id"], old["date"]))
    new_keys = set(zip(new["stock_id"], new["date"]))
    old_stocks = set(old["stock_id"].unique())
    new_stocks = set(new["stock_id"].unique())
    missing_stock_ids = sorted(old_stocks - new_stocks)
    missing_keys = sorted(old_keys - new_keys)
    return {
        "missing_columns_old": [c for c in SIX_COLUMNS if c not in old.columns],
        "missing_columns_new": [c for c in SIX_COLUMNS if c not in new.columns],
        "old_stock_count": len(old_stocks),
        "new_stock_count": len(new_stocks),
        "missing_stock_ids_count": len(missing_stock_ids),
        "old_key_count": len(old_keys),
        "new_key_count": len(new_keys),
        "missing_keys_count": len(missing_keys),
        "extra_keys_count": len(new_keys - old_keys),
        "overlap_key_count": len(old_keys & new_keys),
    }


_ANCHOR_STRUCTURAL_FIELDS = (
    "missing_columns_old", "missing_columns_new", "old_stock_count", "new_stock_count",
    "missing_stock_ids_count", "old_key_count", "new_key_count", "missing_keys_count",
    "extra_keys_count", "overlap_key_count",
)
_ANCHOR_COLUMN_FIELDS = ("n_compared", "n_null_mismatch", "n_exact_equal",
                          "n_value_mismatch", "max_abs_diff", "median_abs_diff")


def compute_six_column_stats(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    """跟 anchor receipt institutional_gross.columns 同一組統計欄位/語意 (inner
    merge on key,兩邊都非 null 的列才比 abs diff;max/median 只算在有數值不等的
    子集上)——這套語意在 scripts/_full_population_diff.py 現行版本的數值分支
    裡也是同一套算法,是本專案從 Round 3 就沿用至今、沒有改過的核心比對邏輯。"""
    m = old[KEY_COLS + SIX_COLUMNS].merge(new[KEY_COLS + SIX_COLUMNS], on=KEY_COLS,
                                           suffixes=("_old", "_new"))
    out = {}
    for c in SIX_COLUMNS:
        o, n = m[f"{c}_old"], m[f"{c}_new"]
        o_null, n_null = o.isna(), n.isna()
        both_present = (~o_null) & (~n_null)
        diff = (o - n).abs()
        value_mismatch_mask = both_present & (diff != 0)
        exact_equal_mask = both_present & (diff == 0)
        out[c] = {
            "n_compared": int(len(m)),
            "n_null_mismatch": int((o_null != n_null).sum()),
            "n_exact_equal": int(exact_equal_mask.sum()),
            "n_value_mismatch": int(value_mismatch_mask.sum()),
            "max_abs_diff": float(diff[value_mismatch_mask].max()) if value_mismatch_mask.any() else 0.0,
            "median_abs_diff": float(diff[value_mismatch_mask].median()) if value_mismatch_mask.any() else 0.0,
        }
    return out, m


def compare_structural_to_anchor(reproduced: dict, anchor_ig: dict) -> list:
    mismatches = []
    for field in _ANCHOR_STRUCTURAL_FIELDS:
        if reproduced.get(field) != anchor_ig.get(field):
            mismatches.append({"field": field, "anchor": anchor_ig.get(field),
                                "reproduced": reproduced.get(field)})
    return mismatches


def compare_columns_to_anchor(reproduced_cols: dict, anchor_cols: dict) -> list:
    mismatches = []
    for c in SIX_COLUMNS:
        anchor_c = anchor_cols.get(c, {})
        repro_c = reproduced_cols.get(c, {})
        for field in _ANCHOR_COLUMN_FIELDS:
            if repro_c.get(field) != anchor_c.get(field):
                mismatches.append({"column": c, "field": field,
                                    "anchor": anchor_c.get(field), "reproduced": repro_c.get(field)})
    return mismatches


def enumerate_mismatch_instances(merged: pd.DataFrame) -> pd.DataFrame:
    """從 compute_six_column_stats 回傳的 merged 表,展開成「每個 (key, 欄位)
    不一致實例各一列」的長表,供逐一分類用。"""
    rows = []
    for c in SIX_COLUMNS:
        o, n = merged[f"{c}_old"], merged[f"{c}_new"]
        o_null, n_null = o.isna(), n.isna()
        both_present = (~o_null) & (~n_null)
        diff = (o - n).abs()
        null_mismatch = o_null != n_null
        value_mismatch = both_present & (diff != 0)
        mismatch = null_mismatch | value_mismatch
        if not mismatch.any():
            continue
        sub = merged.loc[mismatch, KEY_COLS + [f"{c}_old", f"{c}_new"]].copy()
        sub = sub.rename(columns={f"{c}_old": "old_p", f"{c}_new": "new_p"})
        sub["column"] = c
        sub["mismatch_kind"] = np.where(null_mismatch[mismatch], "null_mismatch", "value_mismatch")
        rows.append(sub)
    if not rows:
        return pd.DataFrame(columns=KEY_COLS + ["column", "old_p", "new_p", "mismatch_kind"])
    return pd.concat(rows, ignore_index=True)


class RawSchemaError(ValueError):
    """原始檔驗證失敗 (無效 stock_id/date、或任何重複鍵) fail-closed 用。攜帶
    結構化細節 (來源/種類/筆數/代表性樣本),讓呼叫端可以把完整診斷寫進失敗
    receipt,不是只留一句 exception message (Round 9 review)。"""

    def __init__(self, message, *, source, kind, count, samples):
        super().__init__(message)
        self.source = source
        self.kind = kind          # "invalid_keys" | "duplicate_keys"
        self.count = count
        self.samples = samples    # list[dict],JSON-safe


def _validate_raw_keys(df: pd.DataFrame, source_name: str) -> None:
    """Round 9 review:在 filter 成 needed_keys **之前**,對整份原始檔驗證:

      · stock_id 不能是空白/NaN/"nan"/"None" 之類的無效字串。
      · date 不能是解析失敗的 NaT。
      · (stock_id, date) 不能重複——**不分是否衝突,完全重複的列也要 raise,
        兩份原始檔都不去重**(Round 8 版本會把值完全相同的重複列安全去重,
        Round 9 review 認為這裡不該由診斷腳本自己決定要保留哪一列;原始檔
        本身如果有重複鍵,代表這份原始檔或它的匯出過程有問題,要先被看見)。

    任一項不符,raise `RawSchemaError`,呼叫端據此寫進失敗 receipt。驗證發生在
    needed_keys 過濾之前,不會讓範圍外的無效/重複列在錯誤浮現前就被悄悄濾掉。"""
    id_norm = df["stock_id"].astype(str).str.strip().str.lower()
    bad_id_mask = df["stock_id"].isna() | id_norm.isin(_INVALID_ID_STRINGS)
    bad_date_mask = df["date"].isna()
    bad_mask = bad_id_mask | bad_date_mask
    if bad_mask.any():
        bad = df.loc[bad_mask, ["stock_id", "date"]].astype(str).head(10)
        raise RawSchemaError(
            f"{source_name}:{int(bad_mask.sum())} 列 stock_id 無效或 date 無法解析"
            f" (在 filter 成 needed_keys 之前的全量檢查,不能靜默漏掉)。",
            source=source_name, kind="invalid_keys", count=int(bad_mask.sum()),
            samples=bad.to_dict("records"))

    dup_mask = df.duplicated(subset=KEY_COLS, keep=False)
    if dup_mask.any():
        dup_keys = sorted(set(zip(df.loc[dup_mask, "stock_id"], df.loc[dup_mask, "date"])))
        raise RawSchemaError(
            f"{source_name}:{len(dup_keys)} 個 (stock_id, date) 在原始檔內部重複"
            f" (不論數值是否一致,一律 raise,不去重,不猜哪一列對)。",
            source=source_name, kind="duplicate_keys", count=len(dup_keys),
            samples=[{"stock_id": k[0], "date": k[1]} for k in dup_keys[:10]])


def _build_evidence_for_subset(df: pd.DataFrame, columns) -> dict:
    """對已經 filter 成 needed_keys 子集的 df 建立逐欄逐 key 的證據字典
    (Round 9 review):`{column: {(stock_id, date): {raw_token, parsed_value,
    is_blank, is_unparseable, unit_scale}}}`。

    `raw_token` 保留原始儲存格的文字/值 (`None` 代表儲存格本來就空白)——不能讓
    像文字 "." 這種轉換失敗的內容只以 `parsed_value=NaN` 的形式存在,那樣審查者
    看 receipt 時完全看不出「原始檔裡到底寫了什麼」。"""
    evidence = {c: {} for c in columns}
    keys = list(zip(df["stock_id"], df["date"]))
    for c in columns:
        raw = df[c]
        raw_str_norm = raw.astype(str).str.strip().str.lower()
        was_blank = raw.isna() | raw_str_norm.isin(_BLANK_TOKENS)
        numeric = pd.to_numeric(raw, errors="coerce")
        is_unparseable = numeric.isna() & ~was_blank
        unit_scale = "x1000" if c in LOT_TO_SHARE_COLUMNS else "none"
        scaled = numeric * 1000 if c in LOT_TO_SHARE_COLUMNS else numeric
        raw_list = raw.tolist()
        blank_list = was_blank.tolist()
        unparse_list = is_unparseable.tolist()
        scaled_list = scaled.tolist()
        for key, token, blank, unparse, val in zip(keys, raw_list, blank_list, unparse_list, scaled_list):
            evidence[c][key] = {
                "raw_token": None if blank else str(token),
                "parsed_value": None if (val is None or (isinstance(val, float) and np.isnan(val))) else float(val),
                "is_blank": bool(blank),
                "is_unparseable": bool(unparse),
                "unit_scale": unit_scale,
            }
    return evidence


def parse_old_raw(path: Path, needed_keys: set = None) -> dict:
    """舊原始檔:代號/名稱分兩欄,年月日是斜線格式字串。§10.3 凍結的對應。
    先對**整份**原始檔驗證 (Round 9 review),再 filter 成 needed_keys 建證據。"""
    source_name = "old_raw(法人毛額+持股率20260404-0716.xlsx)"
    usecols = ["代號", "名稱", "年月日"] + list(RAW_COLUMN_RENAME)
    df = pd.read_excel(path, usecols=usecols)
    df["stock_id"] = df["代號"].astype(str).str.strip()
    df["date"] = tej_importer._parse_dates(df["年月日"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns=RAW_COLUMN_RENAME)
    _validate_raw_keys(df, source_name)
    if needed_keys is not None:
        mask = [k in needed_keys for k in zip(df["stock_id"], df["date"])]
        df = df[mask]
    return _build_evidence_for_subset(df, SIX_COLUMNS)


def parse_new_raw(path: Path, needed_keys: set = None) -> dict:
    """新原始檔:證券代碼是「代號 名稱」合併格式,年月日是純數字 int64。§10.3
    凍結的對應。先對**整份**原始檔驗證 (Round 9 review),再 filter 成
    needed_keys 建證據。"""
    source_name = "new_raw(2025-20260806 法人.xlsx)"
    usecols = ["證券代碼", "年月日"] + list(RAW_COLUMN_RENAME)
    df = pd.read_excel(path, usecols=usecols)
    parts = df["證券代碼"].astype(str).str.strip().str.split(n=1, expand=True)
    df["stock_id"] = parts[0].str.strip()
    df["date"] = tej_importer._parse_dates(df["年月日"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns=RAW_COLUMN_RENAME)
    _validate_raw_keys(df, source_name)
    if needed_keys is not None:
        mask = [k in needed_keys for k in zip(df["stock_id"], df["date"])]
        df = df[mask]
    return _build_evidence_for_subset(df, SIX_COLUMNS)


def _equal(a, b) -> bool:
    a_null = a is None or (isinstance(a, float) and np.isnan(a))
    b_null = b is None or (isinstance(b, float) and np.isnan(b))
    if a_null and b_null:
        return True
    if a_null or b_null:
        return False
    return a == b


def classify_instance(old_r, new_r, old_p, new_p) -> str:
    """docs/資料快照遷移_DataExport0806.md §10.4 凍結的決策樹。old_r/new_r 是
    `None` 代表這個 key 在該原始檔完全找不到 (RAW_KEY_MISSING 由呼叫端在這之前
    判斷,這個函式假設兩邊都至少「找得到列」;純值缺失用 NaN 表示,不是 None)。"""
    raw_agree = _equal(old_r, new_r)
    if raw_agree:
        if _equal(old_r, old_p):
            return "BOTH_RAW_MATCH_OLD"
        if _equal(old_r, new_p):
            return "BOTH_RAW_MATCH_NEW"
        return "NEITHER_MATCH"
    old_matches_own = _equal(old_r, old_p)
    new_matches_own = _equal(new_r, new_p)
    if old_matches_own and new_matches_own:
        return "RAW_SOURCES_DIFFER"
    if old_matches_own:
        return "OLD_RAW_ONLY_MATCH"
    if new_matches_own:
        return "NEW_RAW_ONLY_MATCH"
    return "NEITHER_MATCH"


def classify_all(mismatches: pd.DataFrame, old_evidence: dict, new_evidence: dict) -> pd.DataFrame:
    """回傳的每一列都帶完整證據 (Round 9 review):raw_token/parsed/blank/
    unparseable/unit_scale (雙邊)、parquet 值、分類、數值不等的
    signed_diff_new_minus_old/abs_diff、`RAW_SOURCES_DIFFER` 專屬的兩個驗證旗標。
    """
    records = []
    for row in mismatches.itertuples(index=False):
        key = (row.stock_id, row.date)
        col = row.column
        old_ev = old_evidence.get(col, {}).get(key)
        new_ev = new_evidence.get(col, {}).get(key)

        if old_ev is None or new_ev is None:
            classification = "RAW_KEY_MISSING"
            old_r = new_r = None
        elif old_ev["is_unparseable"] or new_ev["is_unparseable"]:
            # 原始檔裡這一格有值,但不是空白、也轉換不成數字 (例如文字 ".")——
            # 跟合法空白分開,不能被 classify_instance 當作「相等的 null」處理。
            classification = "UNRESOLVED_SCHEMA_OR_UNIT"
            old_r, new_r = old_ev["parsed_value"], new_ev["parsed_value"]
        else:
            old_r, new_r = old_ev["parsed_value"], new_ev["parsed_value"]
            classification = classify_instance(old_r, new_r, row.old_p, row.new_p)

        old_ev = old_ev or {}
        new_ev = new_ev or {}
        record = {
            "stock_id": row.stock_id, "date": row.date, "column": col,
            "mismatch_kind": row.mismatch_kind,
            "old_parquet": row.old_p, "new_parquet": row.new_p,
            "old_raw_token": old_ev.get("raw_token"), "new_raw_token": new_ev.get("raw_token"),
            "old_raw_parsed": old_r, "new_raw_parsed": new_r,
            "old_raw_is_blank": old_ev.get("is_blank"), "new_raw_is_blank": new_ev.get("is_blank"),
            "old_raw_is_unparseable": old_ev.get("is_unparseable"),
            "new_raw_is_unparseable": new_ev.get("is_unparseable"),
            "unit_scale": old_ev.get("unit_scale") or new_ev.get("unit_scale"),
            "classification": classification,
        }

        if row.mismatch_kind == "value_mismatch" and pd.notna(row.old_p) and pd.notna(row.new_p):
            signed = float(row.new_p) - float(row.old_p)
            record["signed_diff_new_minus_old"] = signed
            record["abs_diff"] = abs(signed)
        else:
            record["signed_diff_new_minus_old"] = None
            record["abs_diff"] = None

        if classification == "RAW_SOURCES_DIFFER":
            old_match = _equal(old_r, row.old_p)
            new_match = _equal(new_r, row.new_p)
            if not (old_match and new_match):
                raise RuntimeError(
                    f"RAW_SOURCES_DIFFER 但 old_raw_matches_old_parquet={old_match},"
                    f" new_raw_matches_new_parquet={new_match} (key={key}, column={col})"
                    f" —— classify_instance 邏輯出錯,不能放行。")
            record["old_raw_matches_old_parquet"] = old_match
            record["new_raw_matches_new_parquet"] = new_match
        else:
            record["old_raw_matches_old_parquet"] = None
            record["new_raw_matches_new_parquet"] = None

        records.append(record)
    return pd.DataFrame.from_records(records)


_NO_CLEAN_EVIDENCE_CLASSIFICATIONS = ("RAW_KEY_MISSING", "UNRESOLVED_SCHEMA_OR_UNIT")


def build_diff_distribution(classified: pd.DataFrame) -> dict:
    """每欄「精確 diff 值 → 筆數」的完整分布,不分箱、不設容忍值,每一列只落進
    唯一一個桶、互斥、加總等於該欄筆數 (Round 9 review)。

    **修正**(這是實作過程中自己發現的 bug,不是審查指出的):第一版把
    `mismatch_kind=="null_mismatch"` 跟 `classification=="UNRESOLVED_SCHEMA_OR_
    UNIT"` 當成兩個獨立計數的欄位分開累加,但這兩者不是互斥的維度——同一列可能
    同時是「parquet 層級的 null 不對稱」又是「raw 層級無法解析」(這正是真實資料
    裡那 26 筆 `foreign_holding_pct` 的實際狀況:parquet 因為讀不到值而是
    null_mismatch,raw 因為文字 "." 而是 unparseable),分開累加會被重複計數兩次,
    導致加總對不上 `total_mismatch_instances`。改成明確的優先順序,每列只進一個桶:

      1. `classification` 是 `RAW_KEY_MISSING`/`UNRESOLVED_SCHEMA_OR_UNIT`
         (拿不到乾淨的 raw 證據)→ 各自獨立的桶,不再看 `mismatch_kind`。
      2. 否則 `mismatch_kind == "null_mismatch"`(parquet 層級 null 不對稱,但
         raw 證據是乾淨的)→ `"null_mismatch"` 桶。
      3. 否則 (數值不等,raw 證據乾淨) → 該欄實際 diff 值的精確桶。
    """
    dist = {}
    for col in SIX_COLUMNS:
        col_df = classified[classified["column"] == col]
        col_dist = {}
        for cls in _NO_CLEAN_EVIDENCE_CLASSIFICATIONS:
            n = int((col_df["classification"] == cls).sum())
            if n:
                col_dist[cls] = n
        remainder = col_df[~col_df["classification"].isin(_NO_CLEAN_EVIDENCE_CLASSIFICATIONS)]
        col_dist["null_mismatch"] = int((remainder["mismatch_kind"] == "null_mismatch").sum())
        value_rows = remainder[remainder["mismatch_kind"] == "value_mismatch"]
        for diff, cnt in value_rows["signed_diff_new_minus_old"].value_counts().items():
            col_dist[repr(diff)] = int(cnt)
        dist[col] = col_dist
    return dist


REQUIRED_RECORD_FIELDS = (
    "stock_id", "date", "column", "mismatch_kind", "old_parquet", "new_parquet",
    "old_raw_token", "new_raw_token", "old_raw_parsed", "new_raw_parsed",
    "old_raw_is_blank", "new_raw_is_blank", "old_raw_is_unparseable", "new_raw_is_unparseable",
    "unit_scale", "classification", "signed_diff_new_minus_old", "abs_diff",
    "old_raw_matches_old_parquet", "new_raw_matches_new_parquet",
)


def summarize_records(records: list) -> dict:
    """從 `mismatch_records` (list of dict) 重建全部摘要統計 (Round 10 review)。

    這是 receipt 裡所有 `classification_counts_*`/`diff_distribution_by_column`
    欄位的**唯一**產生方式——不能有另一條「直接從 DataFrame 算」的路徑跟這裡
    分岔,那樣就沒辦法保證「這些摘要只從 mismatch_records 就能重建」。
    `institutional_gross_adjudication_verifier.py` 呼叫同一支函式重新從 receipt
    的 `mismatch_records` 重建一次,逐項比對兩邊一致。"""
    df = pd.DataFrame.from_records(records)
    counts_overall = df["classification"].value_counts().to_dict()
    counts_by_column = (df.groupby(["column", "classification"]).size()
                          .unstack(fill_value=0).to_dict(orient="index"))
    counts_by_stock = df.groupby("stock_id").size().to_dict()
    counts_by_stock_top20_display = (df.groupby("stock_id").size()
                                        .sort_values(ascending=False).head(20).to_dict())
    counts_by_date = df.groupby("date").size().to_dict()
    diff_distribution = build_diff_distribution(df)
    return {
        "classification_counts_overall": counts_overall,
        "classification_counts_by_column": counts_by_column,
        "classification_counts_by_stock": counts_by_stock,
        "classification_counts_by_stock_top20_display": counts_by_stock_top20_display,
        "classification_counts_by_date": counts_by_date,
        "diff_distribution_by_column": diff_distribution,
    }


def validate_mismatch_records(records: list, expected_total: int) -> None:
    """`mismatch_records` 本身的完整性檢查 (Round 10 review):筆數要對、
    `(stock_id, date, column)` 不能重複、每筆要有完整的必要欄位。任一項不符就
    raise——這是 receipt 寫出之前的最後一道防線,也是
    `institutional_gross_adjudication_verifier.py` 獨立驗證時會重做一次的同一套
    檢查 (兩邊各自實作、互不信任對方)。"""
    if len(records) != expected_total:
        raise AssertionError(
            f"mismatch_records 筆數 {len(records)} 跟 total_mismatch_instances="
            f"{expected_total} 對不上,有實例被憑空增減。")
    seen = set()
    for rec in records:
        key = (rec.get("stock_id"), rec.get("date"), rec.get("column"))
        if key in seen:
            raise AssertionError(f"mismatch_records 出現重複的 (stock_id, date, column) 鍵:{key}")
        seen.add(key)
        missing = [f for f in REQUIRED_RECORD_FIELDS if f not in rec]
        if missing:
            raise AssertionError(f"mismatch_records 的 {key} 缺少必要欄位 {missing}")


def _write_receipt(receipt: dict) -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    suffix = uuid.uuid4().hex[:8]
    path = RECEIPT_DIR / f"institutional_gross_adjudication_{ts}_{suffix}.json"
    with open(path, "x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2, default=str)
    return path


def main():
    started_at = datetime.now(timezone.utc).isoformat()

    receipt = {
        "generated_at_utc": started_at,
        "script_relpath": SCRIPT_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "script_sha256": _sha256_of(SCRIPT_PATH),
        "anchor_receipt_path": str(ANCHOR_RECEIPT_PATH),
        "note": ("Read-only provenance adjudication for institutional_gross's six columns, "
                 "primarily trust_holding_pct. Not a new tolerance search, not migration "
                 "approval. Classification describes evidence shape only; it does not pick "
                 "an authoritative version. See docs/資料快照遷移_DataExport0806.md §10. "
                 "This is the Round 10 frozen single-shot execution; see "
                 "prior_receipts_provenance for the status of earlier receipts."),
        "prior_receipts_provenance": {
            name: {
                "path": str(info["path"]),
                "sha256": _sha256_of(info["path"]) if info["path"].exists() else None,
                "status": info["status"],
            }
            for name, info in PRIOR_RECEIPTS_PROVENANCE.items()
        },
    }

    if not ANCHOR_RECEIPT_PATH.exists():
        receipt["overall_status"] = "ANCHOR_INPUT_IDENTITY_UNVERIFIED"
        receipt["reason"] = f"anchor receipt not found at {ANCHOR_RECEIPT_PATH}"
        path = _write_receipt(receipt)
        print(f"ANCHOR_INPUT_IDENTITY_UNVERIFIED: {receipt['reason']}")
        print(f"receipt written to {path}")
        sys.exit(1)

    receipt["anchor_receipt_sha256"] = _sha256_of(ANCHOR_RECEIPT_PATH)
    with open(ANCHOR_RECEIPT_PATH, encoding="utf-8") as f:
        anchor = json.load(f)
    anchor_ig = anchor.get("datasets", {}).get("institutional_gross")
    if anchor_ig is None:
        receipt["overall_status"] = "ANCHOR_INPUT_IDENTITY_UNVERIFIED"
        receipt["reason"] = "anchor receipt has no datasets.institutional_gross entry"
        path = _write_receipt(receipt)
        print(f"ANCHOR_INPUT_IDENTITY_UNVERIFIED: {receipt['reason']}")
        print(f"receipt written to {path}")
        sys.exit(1)

    anchor_old_root = Path(anchor["old_root"]) / "institutional_gross"
    anchor_new_root = Path(anchor["new_root"]) / "institutional_gross"
    root_mismatches = []
    if anchor_old_root.resolve() != OLD_PARQUET_ROOT.resolve():
        root_mismatches.append({"which": "old_root", "anchor": str(anchor_old_root),
                                 "expected": str(OLD_PARQUET_ROOT)})
    if anchor_new_root.resolve() != NEW_PARQUET_ROOT.resolve():
        root_mismatches.append({"which": "new_root", "anchor": str(anchor_new_root),
                                 "expected": str(NEW_PARQUET_ROOT)})
    receipt["anchor_roots"] = {"old_root": str(anchor_old_root), "new_root": str(anchor_new_root)}
    receipt["configured_roots"] = {"old_root": str(OLD_PARQUET_ROOT), "new_root": str(NEW_PARQUET_ROOT)}

    if root_mismatches or not OLD_PARQUET_ROOT.exists() or not NEW_PARQUET_ROOT.exists():
        receipt["overall_status"] = "ANCHOR_INPUT_IDENTITY_UNVERIFIED"
        receipt["root_mismatches"] = root_mismatches
        receipt["old_root_exists"] = OLD_PARQUET_ROOT.exists()
        receipt["new_root_exists"] = NEW_PARQUET_ROOT.exists()
        path = _write_receipt(receipt)
        print("ANCHOR_INPUT_IDENTITY_UNVERIFIED: root path/existence check failed")
        print(f"receipt written to {path}")
        sys.exit(1)

    # ---- 唯讀 manifest (anchor 沒有,這裡誠實地對「現在」的檔案建一份) ----
    old_manifest = build_manifest(OLD_PARQUET_ROOT)
    new_manifest = build_manifest(NEW_PARQUET_ROOT)
    receipt["parquet_manifests"] = {"old": old_manifest, "new": new_manifest}
    receipt["raw_source_files"] = {
        "old_raw": {"path": str(OLD_RAW_XLSX), "sha256": _sha256_of(OLD_RAW_XLSX)
                    if OLD_RAW_XLSX.exists() else None, "exists": OLD_RAW_XLSX.exists()},
        "new_raw": {"path": str(NEW_RAW_XLSX), "sha256": _sha256_of(NEW_RAW_XLSX)
                    if NEW_RAW_XLSX.exists() else None, "exists": NEW_RAW_XLSX.exists()},
    }
    if not OLD_RAW_XLSX.exists() or not NEW_RAW_XLSX.exists():
        receipt["overall_status"] = "ANCHOR_INPUT_IDENTITY_UNVERIFIED"
        receipt["reason"] = "raw source xlsx missing"
        path = _write_receipt(receipt)
        print("ANCHOR_INPUT_IDENTITY_UNVERIFIED: raw source xlsx missing")
        print(f"receipt written to {path}")
        sys.exit(1)

    # ---- 精確重現 anchor 的結構統計 + 六欄統計 ----
    old = load_parquet_dir(OLD_PARQUET_ROOT)
    new = load_parquet_dir(NEW_PARQUET_ROOT)
    reproduced_structural = compute_structural_stats(old, new)
    reproduced_columns, merged = compute_six_column_stats(old, new)

    structural_mismatches = compare_structural_to_anchor(reproduced_structural, anchor_ig)
    column_mismatches = compare_columns_to_anchor(reproduced_columns, anchor_ig.get("columns", {}))
    receipt["anchor_reproduction"] = {
        "reproduced_structural": reproduced_structural,
        "reproduced_columns": reproduced_columns,
        "structural_mismatches_vs_anchor": structural_mismatches,
        "column_mismatches_vs_anchor": column_mismatches,
    }

    if structural_mismatches or column_mismatches:
        receipt["overall_status"] = "ANCHOR_INPUT_IDENTITY_UNVERIFIED"
        path = _write_receipt(receipt)
        print("ANCHOR_INPUT_IDENTITY_UNVERIFIED: reproduced counts differ from anchor")
        print(json.dumps({"structural_mismatches": structural_mismatches,
                           "column_mismatches": column_mismatches}, ensure_ascii=False, indent=2))
        print(f"receipt written to {path}")
        sys.exit(1)

    print("Anchor reproduction: EXACT MATCH on all structural + six-column stats.")

    # ---- 只重建需要的原始檔子集 (驗證在全量上做),分類每一個不一致實例 ----
    mismatches = enumerate_mismatch_instances(merged)
    needed_keys = set(zip(mismatches["stock_id"], mismatches["date"]))

    try:
        old_evidence = parse_old_raw(OLD_RAW_XLSX, needed_keys)
        new_evidence = parse_new_raw(NEW_RAW_XLSX, needed_keys)
    except RawSchemaError as e:
        receipt["overall_status"] = "RAW_SOURCE_VALIDATION_FAILED"
        receipt["raw_validation_failure"] = {
            "source": e.source, "kind": e.kind, "count": e.count,
            "samples": e.samples, "message": str(e),
        }
        path = _write_receipt(receipt)
        print(f"RAW_SOURCE_VALIDATION_FAILED: {e}")
        print(f"receipt written to {path}")
        sys.exit(1)

    classified = classify_all(mismatches, old_evidence, new_evidence)
    assert len(classified) == len(mismatches), (
        f"分類後的列數 {len(classified)} 跟輸入的不一致實例數 {len(mismatches)} 對不上,"
        f"有實例在分類過程中被憑空增減。")
    total_mismatch_instances = int(len(classified))

    # ---- Round 10 review:receipt 的唯一權威證據是 mismatch_records (每一筆不
    # 一致實例各一列的完整資料),不是抽樣。expected count 來自實際重現的輸入
    # (len(classified)),不是寫死的數字。----
    mismatch_records = classified.to_dict("records")
    validate_mismatch_records(mismatch_records, total_mismatch_instances)

    # 所有摘要統計都只從 mismatch_records 重建 (summarize_records 是唯一產生
    # 這些欄位的地方),不是另一條從 DataFrame 直接算的分岔路徑。
    summaries = summarize_records(mismatch_records)
    assert sum(summaries["classification_counts_overall"].values()) == total_mismatch_instances, (
        f"從 mismatch_records 重建的分類計數總和跟 total_mismatch_instances="
        f"{total_mismatch_instances} 對不上。")

    # classification_samples 只是方便閱讀的附加視圖,不是唯一的逐筆證據來源
    # (那是 mismatch_records 的責任)——維持小份量即可。
    classified_by_cls = classified.groupby("classification")
    samples = {cls: classified_by_cls.get_group(cls).head(5).to_dict("records")
               for cls in CLASSIFICATIONS if cls in classified_by_cls.groups}

    receipt["mismatch_scope"] = {
        "total_mismatch_instances": total_mismatch_instances,
        "distinct_keys_needing_raw_lookup": len(needed_keys),
    }
    receipt["column_key_date_unit_mapping"] = {
        "old_raw": {"stock_id": "代號 (separate column)", "date": "年月日 (slash format, %Y/%m/%d)",
                    "columns": RAW_COLUMN_RENAME, "lot_to_share_columns": sorted(LOT_TO_SHARE_COLUMNS)},
        "new_raw": {"stock_id": "證券代碼 (combined \"id name\", split on first space)",
                    "date": "年月日 (numeric %Y%m%d)",
                    "columns": RAW_COLUMN_RENAME, "lot_to_share_columns": sorted(LOT_TO_SHARE_COLUMNS)},
    }
    receipt["mismatch_records"] = mismatch_records
    receipt.update(summaries)
    receipt["classification_samples"] = samples
    receipt["overall_status"] = "REVIEW_REQUIRED"
    receipt["policy_note"] = ("This script does not approve migration and does not choose an "
                               "authoritative version. All counts above are diagnostic. Human/Codex "
                               "review of policy consequence is required separately.")

    path = _write_receipt(receipt)
    print(f"Classified {total_mismatch_instances} mismatch instances across {len(needed_keys)} distinct keys.")
    print(json.dumps(summaries["classification_counts_overall"], ensure_ascii=False, indent=2))
    print("overall_status=REVIEW_REQUIRED")
    print(f"receipt written to {path}")


if __name__ == "__main__":
    main()
