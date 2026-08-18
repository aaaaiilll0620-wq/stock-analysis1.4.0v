# -*- coding: utf-8 -*-
"""一次性稽核腳本 (非常設,不進 tej_importer.py 正常路徑):對遷移結果做全量、
exact-diff 比對,不抽樣、不套用未凍結的容忍門檻。用完即丟。

⚠ Round 3 執行時違反了當輪審查明文的「Do not ... rerun the 2.2 GB full audit
yet」限制 (見 docs/資料快照遷移_DataExport0806.md §0 的記錄)。這是本腳本第二次
被修正,但**這一輪 (Round 4) 一樣不對真實資料重跑**,只修程式本身,用
tests/test_tej_data_migration.py 的 synthetic fixture 驗證邏輯正確。

Round 4 review 修正 (相對於 Round 3 版本):
  · `industry_map` (靜態、key=stock_id) 原本被排除在主框架外、只在 main() 裡簡陋
    地比對代號集合。現在納入同一套 DATASET_SPECS 框架,一樣做缺欄/缺鍵/重複鍵/
    exact-diff 比對。
  · merge 前先個別檢查 old/new 兩邊的 key 有沒有重複——重複鍵不去重就直接 merge
    會被 pandas 悄悄做 cross join (同一個 key 配對出多列),把所有統計數字弄假。
    重複鍵一律算 structural FAIL,直接跳過數值比對 (不能建立在被污染的 merge 上)。
  · 拆成 `structural_status` (缺欄/缺鍵/重複鍵) 跟 `value_status` (exact-diff 有沒有
    差異) 兩個獨立欄位。只有兩邊都乾淨才是 `EXACT_PASS`;只要有任何數值或 null
    不一致就是 `DIFF_UNRESOLVED`,dataset 的 `overall_status` 是 `REVIEW_REQUIRED`
    (不是 PASS——Round 3 版本把「key 完整」跟「數值完全一致」都混講成 PASS,誤導)。
  · 新增 `n_both_null` (兩邊都是 null,語意上视为相等,但要有明確的計數,不能讓
    它憑空消失在 n_compared 裡對不上帳)。
  · receipt 檔名加微秒時間戳 + uuid 後綴,用 `open(..., "x")` 排他建立 (檔案已存在
    就直接炸掉,不會靜默覆寫)。receipt 內含每個 dataset 實際讀到的全部 parquet
    檔案清單跟各自 SHA-256,審查者不用重新掃就能核對「到底比了哪些檔案」。

Round 5 review 修正:
  · 新增 dtype drift 偵測——欄位一邊是數值 dtype、另一邊不是時,不再落入非數值
    分支用字串化比較掩蓋過去 (`10.0` 字串化跟字串 `"10.0"` 可能誤判相等),整欄
    直接標記 `dtype_status=INCOMPATIBLE` 並算 mismatch。每欄結果新增
    `dtype_status`/`old_dtype`/`new_dtype`。

用法:python scripts/_full_population_diff.py <scratch_cache_dir>
"""
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
OLD_ROOT = Path.home() / "tej_cache"
RECEIPT_DIR = PROJECT_ROOT / "tej_exports" / "diff_receipts"

_STATUS_RANK = {"EXACT_PASS": 0, "REVIEW_REQUIRED": 1, "FAIL": 2}

# dataset -> {cols, key_cols, static}。cols 是必須兩邊都存在的欄位;static=True
# 代表單一 <root>/<dataset>.parquet,不是 <root>/<dataset>/*.parquet 目錄。
DATASET_SPECS = {
    "price_valuation": {"cols": ["open", "max", "min", "close", "Trading_Volume"],
                         "key_cols": ["stock_id", "date"]},
    "institutional_flow": {"cols": ["foreign_net", "trust_net", "dealer_net"],
                            "key_cols": ["stock_id", "date"]},
    "institutional_gross": {"cols": ["foreign_buy", "foreign_sell", "trust_buy", "trust_sell",
                                      "foreign_holding_pct", "trust_holding_pct"],
                             "key_cols": ["stock_id", "date"]},
    "fundamentals_quarterly": {"cols": ["net_income", "eps", "operating_income", "roe_after_tax"],
                                "key_cols": ["stock_id", "date"]},
    "financial_statements": {"cols": ["revenue", "gross_profit", "operating_income", "net_income",
                                       "eps", "total_assets", "total_liabilities", "current_assets",
                                       "current_liabilities", "equity", "operating_cash_flow", "capex",
                                       "recurring_net_income"],
                              "key_cols": ["stock_id", "date"]},
    "revenue_growth": {"cols": ["revenue_yoy_pct"], "key_cols": ["stock_id", "date"]},
    "monthly_revenue": {"cols": ["revenue_yoy_pct", "revenue", "cum_revenue",
                                  "revenue_last_year", "cum_revenue_last_year"],
                         "key_cols": ["stock_id", "date"]},
    "margin_balance": {"cols": ["margin_balance", "short_balance"], "key_cols": ["stock_id", "date"]},
    "tdcc_weekly": {"cols": ["ratio_1000up", "ratio_le1", "ratio_1to5", "ratio_5to10",
                              "holders", "total_lots_thousand"],
                     "key_cols": ["stock_id", "date"]},
    "director_pledge": {"cols": ["pledge_pct", "director_holding_pct"], "key_cols": ["stock_id", "date"]},
    "industry_map": {"cols": ["tse_ind_code", "tse_ind_name", "tej_ind_code", "tej_ind_name",
                               "tej_subind_code", "tej_subind_name"],
                      "key_cols": ["stock_id"], "static": True},
}


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_all(root: Path, dataset: str, static: bool = False):
    """回傳 (df, file_list)。static=True 讀單一 <root>/<dataset>.parquet;
    否則讀 <root>/<dataset>/*.parquet 整個目錄。file_list 是實際讀到的檔案,
    供 receipt 記錄 manifest+hash 用。"""
    if static:
        p = root / f"{dataset}.parquet"
        if not p.exists():
            return pd.DataFrame(columns=["stock_id"]), []
        return pd.read_parquet(p), [p]
    files = sorted((root / dataset).glob("*.parquet"))
    frames = [pd.read_parquet(f) for f in files]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["stock_id", "date"])
    return df, files


def _duplicated_keys(df: pd.DataFrame, key_cols: list) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=key_cols)
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    return df.loc[dup_mask, key_cols].drop_duplicates()


def diff_dataset(dataset: str, spec: dict, old_root: Path, new_root: Path) -> dict:
    key_cols = spec["key_cols"]
    cols = spec["cols"]
    static = spec.get("static", False)

    old, old_files = load_all(old_root, dataset, static)
    new, new_files = load_all(new_root, dataset, static)

    result = {"dataset": dataset, "key_cols": key_cols}
    result["input_files"] = {
        "old": [{"path": str(p), "sha256": _sha256_of(p)} for p in old_files],
        "new": [{"path": str(p), "sha256": _sha256_of(p)} for p in new_files],
    }

    missing_cols_old = [c for c in cols if c not in old.columns]
    missing_cols_new = [c for c in cols if c not in new.columns]
    result["missing_columns_old"] = missing_cols_old
    result["missing_columns_new"] = missing_cols_new

    # merge 前先各自查重複鍵——重複鍵不擋下來就直接 merge 會被 pandas 悄悄
    # cross join,统计数字全部失真,所以查到重複鍵一律先擋,不准往下比数值。
    old_dup = _duplicated_keys(old, key_cols)
    new_dup = _duplicated_keys(new, key_cols)
    result["old_duplicate_key_count"] = len(old_dup)
    result["new_duplicate_key_count"] = len(new_dup)
    result["old_duplicate_key_sample"] = old_dup.head(10).to_dict("records")
    result["new_duplicate_key_sample"] = new_dup.head(10).to_dict("records")

    fail_reasons = []
    if missing_cols_old:
        fail_reasons.append("missing_columns_old")
    if missing_cols_new:
        fail_reasons.append("missing_columns_new")
    if len(old_dup):
        fail_reasons.append("old_duplicate_keys")
    if len(new_dup):
        fail_reasons.append("new_duplicate_keys")

    old_keys = old[key_cols].drop_duplicates() if not old.empty else pd.DataFrame(columns=key_cols)
    new_keys = new[key_cols].drop_duplicates() if not new.empty else pd.DataFrame(columns=key_cols)
    outer = old_keys.merge(new_keys, on=key_cols, how="outer", indicator=True)
    missing_keys = outer[outer["_merge"] == "left_only"]      # 舊有、新沒有
    extra_keys = outer[outer["_merge"] == "right_only"]       # 新有、舊沒有 (擴大範圍,非失敗訊號)
    both_keys = outer[outer["_merge"] == "both"]
    result["old_key_count"] = len(old_keys)
    result["new_key_count"] = len(new_keys)
    result["missing_keys_count"] = len(missing_keys)
    result["missing_keys_sample"] = missing_keys[key_cols].head(20).to_dict("records")
    result["extra_keys_count"] = len(extra_keys)
    result["overlap_key_count"] = len(both_keys)
    if len(missing_keys) > 0:
        fail_reasons.append("missing_keys")

    result["structural_status"] = "FAIL" if fail_reasons else "PASS"
    result["structural_fail_reasons"] = fail_reasons

    col_results = {}
    if result["structural_status"] == "FAIL":
        # 有重複鍵或缺欄/缺鍵時完全不做數值 merge——不能建立在已知會被污染的
        # (可能 cross-join 的) 合併結果上。
        value_status = "SKIPPED_DUE_TO_STRUCTURAL_FAIL"
    else:
        common_cols = [c for c in cols if c not in missing_cols_old and c not in missing_cols_new]
        if not common_cols or both_keys.empty:
            value_status = "EXACT_PASS"      # 沒有可比的欄位/沒有重疊 key,沒發現差異
        else:
            m = old[key_cols + common_cols].merge(
                new[key_cols + common_cols], on=key_cols, suffixes=("_old", "_new"))
            any_mismatch = False
            for c in common_cols:
                o, n = m[f"{c}_old"], m[f"{c}_new"]
                o_null, n_null = o.isna(), n.isna()
                both_null = o_null & n_null
                null_mismatch = o_null != n_null
                both_present = (~o_null) & (~n_null)
                o_is_numeric = pd.api.types.is_numeric_dtype(o)
                n_is_numeric = pd.api.types.is_numeric_dtype(n)
                if o_is_numeric != n_is_numeric:
                    # dtype 不相容 (一邊數值一邊非數值,如舊版 float 新版被讀成
                    # object/字串):不能靠字串化比較掩蓋過去——Round 5 review 指出
                    # 「10.0」跟字串 "10.0" 這種情況下字串比對會誤判相等,把真正的
                    # schema/dtype drift 藏起來。整欄直接算 mismatch,不做值比對。
                    n_val_mismatch = int(both_present.sum())
                    n_null_mismatch = int(null_mismatch.sum())
                    any_mismatch = True
                    col_results[c] = {
                        "n_compared": int(len(m)),
                        "n_both_null": int(both_null.sum()),
                        "n_null_mismatch": n_null_mismatch,
                        "n_exact_equal": 0,
                        "n_value_mismatch": n_val_mismatch,
                        "max_abs_diff": None,
                        "median_abs_diff": None,
                        "dtype_status": "INCOMPATIBLE",
                        "old_dtype": str(o.dtype),
                        "new_dtype": str(n.dtype),
                    }
                    continue
                is_numeric = o_is_numeric and n_is_numeric
                if is_numeric:
                    diff = (o - n).abs()
                    exact_equal_mask = both_present & (diff == 0)
                    value_mismatch_mask = both_present & (diff != 0)
                    max_diff = float(diff[value_mismatch_mask].max()) if value_mismatch_mask.any() else 0.0
                    median_diff = float(diff[value_mismatch_mask].median()) if value_mismatch_mask.any() else 0.0
                else:
                    # 非數值欄 (如產業代碼字串),兩邊 dtype 相容 (都不是數值):
                    # diff 沒有意義,只能比對「相不相等」。
                    eq = o.astype(str) == n.astype(str)
                    exact_equal_mask = both_present & eq
                    value_mismatch_mask = both_present & ~eq
                    max_diff = None
                    median_diff = None
                n_val_mismatch = int(value_mismatch_mask.sum())
                n_null_mismatch = int(null_mismatch.sum())
                if n_val_mismatch or n_null_mismatch:
                    any_mismatch = True
                col_results[c] = {
                    "n_compared": int(len(m)),
                    "n_both_null": int(both_null.sum()),
                    "n_null_mismatch": n_null_mismatch,
                    "n_exact_equal": int(exact_equal_mask.sum()),
                    "n_value_mismatch": n_val_mismatch,
                    "max_abs_diff": max_diff,
                    "median_abs_diff": median_diff,
                    "dtype_status": "OK",
                    "old_dtype": str(o.dtype),
                    "new_dtype": str(n.dtype),
                }
            value_status = "DIFF_UNRESOLVED" if any_mismatch else "EXACT_PASS"

    result["value_status"] = value_status
    result["columns"] = col_results

    if result["structural_status"] == "FAIL":
        result["overall_status"] = "FAIL"
    elif value_status == "DIFF_UNRESOLVED":
        result["overall_status"] = "REVIEW_REQUIRED"
    else:
        result["overall_status"] = "EXACT_PASS"
    return result


def _write_receipt(receipt: dict) -> Path:
    """genuinely non-overwriting:微秒時間戳 + uuid 後綴組檔名,`open(...,"x")`
    排他建立——萬一真的撞名 (機率極低),直接炸掉,不會靜默覆寫掉舊 receipt。"""
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    suffix = uuid.uuid4().hex[:8]
    path = RECEIPT_DIR / f"full_population_diff_{ts}_{suffix}.json"
    with open(path, "x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2, default=str)
    return path


def main():
    if len(sys.argv) != 2:
        print("用法:python scripts/_full_population_diff.py <scratch_cache_dir>", file=sys.stderr)
        sys.exit(2)
    new_root = Path(sys.argv[1])

    datasets_result = {ds: diff_dataset(ds, spec, OLD_ROOT, new_root) for ds, spec in DATASET_SPECS.items()}

    for ds, r in datasets_result.items():
        print(f"\n=== {ds} === overall={r['overall_status']} "
              f"(structural={r['structural_status']}, value={r['value_status']})")
        print(f"  keys: old={r['old_key_count']} new={r['new_key_count']} "
              f"overlap={r['overlap_key_count']} missing_from_new={r['missing_keys_count']} "
              f"extra_in_new={r['extra_keys_count']}")
        if r["structural_fail_reasons"]:
            print(f"  STRUCTURAL FAIL: {r['structural_fail_reasons']} "
                  f"(old_dup={r['old_duplicate_key_count']} new_dup={r['new_duplicate_key_count']})")
        for c, cr in r["columns"].items():
            if cr["n_value_mismatch"] or cr["n_null_mismatch"]:
                print(f"  {c}: n_compared={cr['n_compared']} both_null={cr['n_both_null']} "
                      f"exact_equal={cr['n_exact_equal']} value_mismatch={cr['n_value_mismatch']} "
                      f"null_mismatch={cr['n_null_mismatch']} max_abs_diff={cr['max_abs_diff']}")

    worst = max((_STATUS_RANK[r["overall_status"]] for r in datasets_result.values()
                 if r["overall_status"] in _STATUS_RANK), default=2)
    overall_status = next(k for k, v in _STATUS_RANK.items() if v == worst)
    if any(r["overall_status"] not in _STATUS_RANK for r in datasets_result.values()):
        overall_status = "FAIL"   # SKIPPED_* 等非預期狀態一律當最壞情況處理

    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_relpath": SCRIPT_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "script_sha256": _sha256_of(SCRIPT_PATH),
        "old_root": str(OLD_ROOT),
        "new_root": str(new_root),
        "overall_status": overall_status,
        "note": ("value_status=DIFF_UNRESOLVED on a dataset means at least one column has a nonzero "
                 "value or null mismatch; no per-column tolerance has been frozen with unit+rationale, "
                 "so DIFF_UNRESOLVED is not auto-resolved to PASS/FAIL by this script — a human must "
                 "review the per-column stats. Any narrative about *why* values differ (e.g. "
                 "'TEJ revision') is INFERENCE_UNCONFIRMED unless backed by independent raw-to-raw "
                 "evidence from TEJ."),
        "datasets": datasets_result,
    }
    receipt_path = _write_receipt(receipt)

    print(f"\noverall_status={overall_status}")
    print(f"receipt written to {receipt_path}")


if __name__ == "__main__":
    main()
