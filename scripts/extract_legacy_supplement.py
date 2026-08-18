# -*- coding: utf-8 -*-
"""extract_legacy_supplement.py — 把 DataExport0806 沒有的舊欄位一次性凍結成 supplement parquet。

背景:DataExport0806 的財報/月營收寬版匯出比舊 tej_exports/inbox_fundamentals、
      inbox_revenue 豐富很多,但少了幾個舊欄位 (見
      docs/資料快照遷移_DataExport0806.md §5),來自**四個**舊來源檔:
        · roe_after_tax        (ROE(A)稅後)         ← inbox_fundamentals/2019-202603 EPS ROE OI.xlsx
                                                       (只有 2019-03+;舊 production 的
                                                       fundamentals_quarterly 本來就只有這段,
                                                       不是這裡新造成的縮水)
        · recurring_net_income (常續性稅後淨利)      ← inbox_fundamentals/三大財報2019~202603.xlsx
                                                       (2019-03+) **+**
                                                       tej_exports/inbox/2005-2018 三大財報+ROE
                                                       上下市.xlsx (2005-2018;跟
                                                       scripts/import_financials_2005_2018.py
                                                       讀同一份檔) —— 舊 production 的
                                                       financial_statements 這欄本來就是
                                                       2005 年起連續有值 (那支一次性補丁腳本
                                                       當年補的),只從 2019-202603 EPS ROE OI
                                                       這份補會製造出一個舊資料沒有的 2005-2018
                                                       缺口,所以這裡兩個舊來源都讀。
        · revenue_last_year / cum_revenue_last_year (去年單月/累計營收)
                                                      ← inbox_revenue/YoY 201901~202607.xlsx
                                                       (只有 2019+;TEJ 沒有更早的這欄匯出,
                                                       舊 production 本來就只有這段)

用法:python scripts/extract_legacy_supplement.py     # 只讀一次舊 inbox,寫死 supplement
      之後 tej_importer.py 讀的是這裡輸出的 tej_exports/legacy_supplement/*.parquet,
      不會在正常匯入流程裡再去碰 tej_exports/inbox*(這支腳本是唯一例外,職責跟
      scripts/import_financials_2005_2018.py 一樣:一次性把舊資料的獨有內容存起來,
      之後舊來源就可以真的刪除)。

安全 (Round 4 review 修正):
  · 每個來源在任何 dropna 之前先明確檢查 stock_id/date 有沒有空白/NaN/"nan" 字串
    這種無效值——str(NaN) 會變成字面上的 "nan" 字串,原本的 dropna 完全抓不到,
    抓到就直接 raise,不靜默丟掉。
  · 每個輸出欄位有凍結的預期 schema + 最低列數/股票數/最早日期門檻,`_profile`
    不再只是記錄數字,`_enforce_output_spec` 真的會 raise。
  · 發布邏輯拆成獨立、可單元測試的 `publish_staging()`:先寫到 staging 目錄、
    驗證通過才進入「commit point」(staging→out_dir 的 atomic rename)。commit
    point 之前任何失敗,out_dir 完全不動;commit point 之後 (新資料已經生效)
    若備份清理失敗,只印警告,不會回報整個操作失敗 (不能讓呼叫端誤以為新資料
    沒發布成功,結果其實已經生效了)。
  · receipt JSON (tej_exports/legacy_supplement/receipt.json) 記錄四個舊來源檔的
    相對路徑+SHA-256、三個輸出檔的 SHA-256/schema/列數/股票數/日期範圍/重複鍵與
    null 鍵數量、抽取腳本自身的 SHA-256、時間戳、整體狀態——tej_importer.py 在
    消費 supplement 前會驗證這份 receipt (見 tej_importer.py `_verify_supplement`)。

安全 (Round 6 review 修正):
  · 同 key 衝突檢查原本只在「投影成 supplement 欄位之後」才做——同一個 key 若
    目標欄位剛好相同、但來源檔其他欄位互相矛盾,投影後會看起來像「完全重複」被
    安全去重,矛盾永遠沒人看見。新增 `check_source_duplicates()`,在投影**之前**
    先對原始來源的完整列做一次檢查。
  · 去重次數與跨窗口 overlap 次數原本只 print 到 stderr,console 一關就沒了。
    現在 `_dedupe_or_raise` / `_combine_recurring_windows` 都回傳統計,寫進
    receipt 的 `outputs[<name>]["dedup"]`。

安全 (Round 5 review 修正):
  · 每個 extract_* 函式結尾原本直接 `drop_duplicates(keep="last")`,同鍵不同值
    時會悄悄選最後一列。改成 `_dedupe_or_raise`:完全重複 (含都是 NaN) 才安全
    去重且記錄次數,數值衝突一律 raise。
  · `recurring_net_income` 的 2005-2018 窗口跟 2019+ 窗口原本直接 concat 後
    `drop_duplicates(keep="last")` 讓新窗口優先。改成 `_combine_recurring_windows`
    明確比較重疊 key 的數值,只有相同才安全去重,不同就 raise。
  · `publish_staging` 開頭加 `_recover_or_clear_stale_backup`:上一次執行如果在
    commit 中途被強制中斷,backup_dir 可能是唯一僅存的舊資料,不能像原本那樣
    一進函式就無條件 `shutil.rmtree(backup_dir)`——只有 out_dir 也存在時才安全
    清掉,否則先還原。

輸出:
  tej_exports/legacy_supplement/roe_after_tax.parquet        (stock_id, date, roe_after_tax)
  tej_exports/legacy_supplement/recurring_net_income.parquet (stock_id, date, recurring_net_income)
  tej_exports/legacy_supplement/revenue_last_year.parquet    (stock_id, date, revenue_last_year, cum_revenue_last_year)
  tej_exports/legacy_supplement/receipt.json
================================================================================
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
INBOX_FUNDAMENTALS = PROJECT_ROOT / "tej_exports" / "inbox_fundamentals"
INBOX_REVENUE = PROJECT_ROOT / "tej_exports" / "inbox_revenue"
INBOX_ROOT = PROJECT_ROOT / "tej_exports" / "inbox"
OUT_DIR = PROJECT_ROOT / "tej_exports" / "legacy_supplement"
STAGING_DIR = PROJECT_ROOT / "tej_exports" / ".legacy_supplement.staging"
BACKUP_DIR = PROJECT_ROOT / "tej_exports" / ".legacy_supplement.rollback"

SOURCES = {
    "roe_after_tax": INBOX_FUNDAMENTALS / "2019-202603 EPS ROE OI.xlsx",
    "recurring_net_income_2019plus": INBOX_FUNDAMENTALS / "三大財報2019~202603.xlsx",
    "recurring_net_income_2005_2018": INBOX_ROOT / "2005-2018 三大財報+ROE 上下市.xlsx",
    "revenue_last_year": INBOX_REVENUE / "YoY 201901~202607.xlsx",
}

# 每個輸出檔凍結的預期 schema + 最低規模門檻 (取自已實測過、跟生產環境比對過的
# 數字打七折,只抓「明顯縮水/欄位跑掉」這種粗粒度問題,不是完整性證明)。
OUTPUT_SPECS = {
    "roe_after_tax": {
        "schema": ["stock_id", "date", "roe_after_tax"],
        "min_rows": 40_000, "min_stocks": 1500, "expected_date_min": "2019-03-31",
    },
    "recurring_net_income": {
        "schema": ["stock_id", "date", "recurring_net_income"],
        "min_rows": 100_000, "min_stocks": 1800, "expected_date_min": "2005-12-31",
    },
    "revenue_last_year": {
        "schema": ["stock_id", "date", "revenue_last_year", "cum_revenue_last_year"],
        "min_rows": 130_000, "min_stocks": 1500, "expected_date_min": "2019-01-31",
    },
}

_INVALID_ID_STRINGS = {"", "nan", "none", "nat", "null", "na"}


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _period_date(series: pd.Series) -> pd.Series:
    """"2026/03" 或 "202603" 兩種期間標籤格式都轉成該月第一天 (跟 tej_importer.py 的
    財報/月營收 date 欄同一套慣例,才能用 (stock_id, date) 對得上)。"""
    raw = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    dt = pd.to_datetime(raw, format="%Y/%m", errors="coerce")
    retry = dt.isna() & raw.str.match(r"^\d{6}$")
    if retry.any():
        dt.loc[retry] = pd.to_datetime(raw[retry], format="%Y%m", errors="coerce")
    return dt.dt.strftime("%Y-%m-%d")


def _duplicate_key_stats(df: pd.DataFrame, key_cols: list, source_name: str, stage: str) -> dict:
    """同 key 重複的核心判斷,回傳統計,遇到衝突就 raise。

      · 完全重複 (同 key,所有非 key 欄位值都相同,包含都是 NaN 的情況)——
        安全去重,但次數要記錄下來,不能無聲無息。
      · 衝突 (同 key,至少一個非 key 欄位值不同,含一邊有值一邊 NaN 這種不對稱)——
        直接 raise,不設任何容忍門檻,交給人去查是來源檔本身有問題還是抽取邏輯錯。

    跟 tej_importer._check_duplicate_key_conflicts 同一套判斷邏輯 (nunique(dropna=False)
    把「一邊 NaN 一邊有值」也算進「不只一種值」)。

    `stage` 只是給 receipt/錯誤訊息用的標籤:`raw_source`(投影前的完整原始列)
    或 `projected`(投影成 supplement 欄位之後)。"""
    value_cols = [c for c in df.columns if c not in key_cols]
    stats = {
        "stage": stage,
        "checked_columns": list(df.columns),
        "n_duplicate_key_rows": 0,
        "n_exact_duplicate_rows_removed": 0,
        "n_conflicting_keys": 0,
    }
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    if not dup_mask.any():
        return stats
    stats["n_duplicate_key_rows"] = int(dup_mask.sum())
    dup = df[dup_mask]
    n_exact_dup_rows = 0
    conflicting_keys = []
    for key, g in dup.groupby(key_cols):
        if g[value_cols].nunique(dropna=False).gt(1).any():
            conflicting_keys.append(key)
        else:
            n_exact_dup_rows += len(g) - 1
    stats["n_exact_duplicate_rows_removed"] = n_exact_dup_rows
    stats["n_conflicting_keys"] = len(conflicting_keys)
    if conflicting_keys:
        raise ValueError(
            f"{source_name} ({stage}):{len(conflicting_keys)} 個 key 在來源檔內部數值不一致"
            f" (例:{conflicting_keys[:5]};比對欄位:{value_cols})。不能用 keep='last'"
            f" 悄悄選一個,先去源頭查是哪幾列衝突。")
    if n_exact_dup_rows:
        print(f"{source_name} ({stage}):{n_exact_dup_rows} 列是完全重複的 key"
              f" (所有欄位值相同),已去重", file=sys.stderr)
    return stats


def check_source_duplicates(df: pd.DataFrame, key_cols: list, source_name: str) -> dict:
    """在投影成 supplement 欄位**之前**,對原始來源的完整列做同 key 衝突檢查
    (Round 6 review)。

    原本只在投影後 (只剩 stock_id/date/目標欄位) 才檢查衝突——同一個 key 若目標
    欄位剛好相同、但來源檔其他欄位互相矛盾 (例如同一季的 net_income 兩份不同),
    投影後看起來會像「完全重複」被安全去重,那個矛盾就永遠沒有人看見了。來源檔
    內部自相矛盾這件事本身就代表這份檔案的品質有問題,不能因為「我們要的那一欄
    剛好一致」就放行。

    這裡不去重,只檢查 + 回傳統計;實際去重仍由投影後的 `_dedupe_or_raise` 做。"""
    return _duplicate_key_stats(df, key_cols, source_name, stage="raw_source")


def _dedupe_or_raise(df: pd.DataFrame, key_cols: list, source_name: str):
    """投影成 supplement 欄位之後的第二層檢查 + 實際去重。
    回傳 `(deduped_df, stats)` —— stats 會被寫進 receipt (Round 6 review:原本
    只 print 到 stderr,console 訊息一關掉就消失,不算稽核紀錄)。"""
    stats = _duplicate_key_stats(df, key_cols, source_name, stage="projected")
    if stats["n_duplicate_key_rows"] == 0:
        return df.reset_index(drop=True), stats
    deduped = (df.drop_duplicates(subset=key_cols, keep="first")
                 .sort_values(key_cols).reset_index(drop=True))
    return deduped, stats


def check_source_keys(df: pd.DataFrame, source_name: str) -> None:
    """dropna 之前先明確檢查 stock_id/date 有沒有無效值,抓到就 raise。
    str(NaN) 會變成字面上的 "nan" 字串、str(None) 變成 "None",都不是真的 pandas
    null,原本的 dropna(subset=[...]) 完全抓不到,是個真的漏洞。"""
    id_norm = df["stock_id"].astype(str).str.strip().str.lower()
    bad_id = df["stock_id"].isna() | id_norm.isin(_INVALID_ID_STRINGS)
    bad_date = df["date"].isna()
    n_bad_id, n_bad_date = int(bad_id.sum()), int(bad_date.sum())
    if n_bad_id or n_bad_date:
        raise ValueError(f"{source_name}:{n_bad_id} 列 stock_id 無效 (空白/NaN/nan字串),"
                          f"{n_bad_date} 列 date 無法解析。這些列在被 dropna 悄悄丟掉之前"
                          f"要先被看見,先去源頭檔查是哪幾列。")


def extract_roe():
    df = pd.read_excel(SOURCES["roe_after_tax"])
    df.columns = ["stock_id", "stock_name", "period", "net_income", "eps", "roe_after_tax", "operating_income"]
    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    df["date"] = _period_date(df["period"])
    df["roe_after_tax"] = pd.to_numeric(df["roe_after_tax"], errors="coerce")
    check_source_keys(df, "roe_after_tax")
    raw_stats = check_source_duplicates(df, ["stock_id", "date"], "roe_after_tax")
    out = df[["stock_id", "date", "roe_after_tax"]]
    out, proj_stats = _dedupe_or_raise(out, ["stock_id", "date"], "roe_after_tax")
    return out, {"sources": {"roe_after_tax": [raw_stats, proj_stats]}}


def _extract_recurring_2019plus():
    df = pd.read_excel(SOURCES["recurring_net_income_2019plus"])
    df.columns = ["combined_id", "period", "quarter", "revenue", "gross_profit", "operating_income",
                  "net_income", "eps", "recurring_net_income", "total_assets", "total_liabilities",
                  "current_assets", "current_liabilities", "equity", "operating_cash_flow", "capex"]
    parts = df["combined_id"].astype(str).str.strip().str.split(n=1, expand=True)
    df["stock_id"] = parts[0].str.strip()
    df["date"] = _period_date(df["period"])
    df["recurring_net_income"] = pd.to_numeric(df["recurring_net_income"], errors="coerce") * 1000  # 千元→元
    check_source_keys(df, "recurring_net_income_2019plus")
    raw_stats = check_source_duplicates(df, ["stock_id", "date"], "recurring_net_income_2019plus")
    out = df[["stock_id", "date", "recurring_net_income"]]
    out, proj_stats = _dedupe_or_raise(out, ["stock_id", "date"], "recurring_net_income_2019plus")
    return out, [raw_stats, proj_stats]


def _extract_recurring_2005_2018():
    """跟 scripts/import_financials_2005_2018.py 讀同一份舊檔,只取常續性稅後淨利這欄。
    舊 production 的 financial_statements.recurring_net_income 是那支一次性補丁腳本
    當年補進去的,2005-2018 本來就有值 —— 只從 2019+ 那份補會製造出這裡沒有的缺口。"""
    df = pd.read_excel(SOURCES["recurring_net_income_2005_2018"])
    df.columns = ["stock_id", "stock_name", "period", "quarter", "revenue", "gross_profit",
                  "operating_income", "net_income", "eps", "recurring_net_income", "total_assets",
                  "total_liabilities", "current_assets", "current_liabilities", "equity",
                  "operating_cash_flow", "capex", "roe"]
    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    df["date"] = _period_date(df["period"])
    df["recurring_net_income"] = pd.to_numeric(df["recurring_net_income"], errors="coerce") * 1000  # 千元→元
    check_source_keys(df, "recurring_net_income_2005_2018")
    raw_stats = check_source_duplicates(df, ["stock_id", "date"], "recurring_net_income_2005_2018")
    out = df[["stock_id", "date", "recurring_net_income"]]
    out, proj_stats = _dedupe_or_raise(out, ["stock_id", "date"], "recurring_net_income_2005_2018")
    return out, [raw_stats, proj_stats]


def _combine_recurring_windows(old_window: pd.DataFrame, new_window: pd.DataFrame) -> pd.DataFrame:
    """合併 2005-2018 窗口跟 2019+ 窗口 (Round 5 review:原本直接 concat 後
    `drop_duplicates(keep="last")`,萬一兩個窗口在邊界真的重疊,會讓新窗口不由
    分說地優先,沒有人比對過重疊的那幾個 key 數值是否一致)。

    兩份來源理論上日期區間不重疊,但這裡明確比較重疊的 key:
      · 重疊 key 兩邊數值相同 (含都是 NaN)——安全去重,次數要印出來。
      · 重疊 key 兩邊數值不同——直接 raise,不能用 keep='last' 讓新窗口悄悄贏,
        交給人去查是哪個窗口的資料有問題。
    """
    key_cols = ["stock_id", "date"]
    overlap_keys = old_window[key_cols].merge(new_window[key_cols], on=key_cols, how="inner")
    overlap_stats = {
        "n_overlap_keys": int(len(overlap_keys)),
        "n_overlap_identical": 0,
        "n_overlap_conflicting": 0,
    }
    if len(overlap_keys):
        merged = overlap_keys.merge(old_window, on=key_cols, how="left").merge(
            new_window, on=key_cols, how="left", suffixes=("_old2005", "_new2019"))
        o = merged["recurring_net_income_old2005"]
        n = merged["recurring_net_income_new2019"]
        both_null = o.isna() & n.isna()
        equal = both_null | (o == n)
        n_conflict = int((~equal).sum())
        overlap_stats["n_overlap_identical"] = int(equal.sum())
        overlap_stats["n_overlap_conflicting"] = n_conflict
        if n_conflict:
            sample = merged.loc[~equal, key_cols].head(5).to_dict("records")
            raise ValueError(
                f"recurring_net_income:2005-2018 窗口跟 2019+ 窗口在 {n_conflict} 個"
                f" (stock_id, date) 重疊且數值不同 (例:{sample})。不能用 keep='last'"
                f" 讓 2019+ 窗口悄悄優先,先去源頭查是哪個窗口的資料有問題。")
        if overlap_stats["n_overlap_identical"]:
            print(f"recurring_net_income:{overlap_stats['n_overlap_identical']} 個重疊 key"
                  f" 兩個窗口數值相同,已去重", file=sys.stderr)

    df = pd.concat([old_window, new_window], ignore_index=True)
    out = df.drop_duplicates(subset=key_cols, keep="last").sort_values(key_cols)
    return out.reset_index(drop=True), overlap_stats


def extract_recurring_net_income():
    old_window, old_stats = _extract_recurring_2005_2018()      # 2005-2018
    new_window, new_stats = _extract_recurring_2019plus()        # 2019-03+
    combined, overlap_stats = _combine_recurring_windows(old_window, new_window)
    return combined, {
        "sources": {
            "recurring_net_income_2005_2018": old_stats,
            "recurring_net_income_2019plus": new_stats,
        },
        "cross_window_overlap": overlap_stats,
    }


def extract_revenue_last_year():
    df = pd.read_excel(SOURCES["revenue_last_year"])
    df.columns = ["combined_id", "period", "release_date", "yoy_pct", "revenue",
                  "revenue_last_year", "cum_revenue", "cum_revenue_last_year"]
    parts = df["combined_id"].astype(str).str.strip().str.split(n=1, expand=True)
    df["stock_id"] = parts[0].str.strip()
    df["date"] = _period_date(df["period"])
    df["revenue_last_year"] = pd.to_numeric(df["revenue_last_year"], errors="coerce") * 1000       # 千元→元
    df["cum_revenue_last_year"] = pd.to_numeric(df["cum_revenue_last_year"], errors="coerce") * 1000
    check_source_keys(df, "revenue_last_year")
    raw_stats = check_source_duplicates(df, ["stock_id", "date"], "revenue_last_year")
    out = df[["stock_id", "date", "revenue_last_year", "cum_revenue_last_year"]]
    out, proj_stats = _dedupe_or_raise(out, ["stock_id", "date"], "revenue_last_year")
    return out, {"sources": {"revenue_last_year": [raw_stats, proj_stats]}}


EXTRACTORS = {
    "roe_after_tax": extract_roe,
    "recurring_net_income": extract_recurring_net_income,
    "revenue_last_year": extract_revenue_last_year,
}


def _profile(df: pd.DataFrame, key_cols: list) -> dict:
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    null_key_count = int(df[key_cols].isna().any(axis=1).sum())
    return {
        "schema": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "row_count": int(len(df)),
        "stock_count": int(df["stock_id"].nunique()),
        "date_min": str(df["date"].min()) if "date" in df.columns and len(df) else None,
        "date_max": str(df["date"].max()) if "date" in df.columns and len(df) else None,
        "duplicate_key_row_count": int(dup_mask.sum()),
        "null_key_row_count": null_key_count,
    }


def enforce_output_spec(df: pd.DataFrame, name: str, profile: dict) -> None:
    """凍結的 schema + 最低規模門檻真的會擋——不是只記錄數字讓人事後看。"""
    spec = OUTPUT_SPECS[name]
    if list(df.columns) != spec["schema"]:
        raise ValueError(f"{name}: schema {list(df.columns)} 跟凍結的預期 {spec['schema']} 不符")
    if profile["duplicate_key_row_count"] > 0:
        raise ValueError(f"{name}:抽取結果有 {profile['duplicate_key_row_count']} 列"
                          f"重複 (stock_id, date),不發布")
    if profile["null_key_row_count"] > 0:
        raise ValueError(f"{name}:抽取結果有 {profile['null_key_row_count']} 列"
                          f"stock_id/date 是 null,不發布")
    if profile["row_count"] < spec["min_rows"]:
        raise ValueError(f"{name}: 只有 {profile['row_count']} 列,低於預期下限 {spec['min_rows']}")
    if profile["stock_count"] < spec["min_stocks"]:
        raise ValueError(f"{name}: 只有 {profile['stock_count']} 檔,低於預期下限 {spec['min_stocks']}")
    if profile["date_min"] and profile["date_min"] > spec["expected_date_min"]:
        raise ValueError(f"{name}: 最早日期 {profile['date_min']} 比預期下限"
                          f" {spec['expected_date_min']} 還晚")


def _recover_or_clear_stale_backup(out_dir: Path, backup_dir: Path, label: str) -> None:
    """發布流程最開頭要先做的檢查 (Round 5 review)。

    正常情況下 backup_dir 只在「commit 進行中」短暫存在,commit 成功後收尾就會
    清掉。但如果上一次執行在 `out_dir.rename(backup_dir)` 之後、
    `staging_dir.rename(out_dir)` 完成之前被強制中斷,下次呼叫會看到「backup_dir
    存在、out_dir 不存在」的殘留狀態——這時 backup_dir 是**唯一僅存**的舊資料,
    絕對不能盲目刪掉。

    規則:
      · backup_dir 不存在 → 沒有殘留,直接返回。
      · backup_dir 存在但 out_dir 不存在 → 先還原成 out_dir (rename 本身失敗就讓
        例外往外傳,不吞掉,backup_dir 保持原狀不遺失資料,呼叫端可以之後重試)。
      · 兩者都存在 → 這才是真正「清得掉」的殘留 backup,安全地整個刪掉。
    """
    if not backup_dir.exists():
        return
    if not out_dir.exists():
        backup_dir.rename(out_dir)
        return
    shutil.rmtree(backup_dir)


def publish_staging(staging_dir: Path, out_dir: Path, backup_dir: Path) -> None:
    """把 staging_dir 換成 out_dir,atomic + rollback-safe,獨立於抽取邏輯,可單獨測試。

    commit point 精確定義:`staging_dir.rename(out_dir)` 執行成功的那一刻就是
    「已發布」。在那之前任何失敗 (含 rename 本身失敗),out_dir 會被還原成
    呼叫前的內容,呼叫端應該視為「發布失敗,舊資料還在原地」。commit point 之後
    只剩 backup_dir 清理這個收尾動作——清理失敗不代表發布失敗,只印警告,不
    raise,不能讓呼叫端誤以為新資料沒生效 (它已經生效了)。

    函式最開頭先跑 `_recover_or_clear_stale_backup` (Round 5 review):處理上一次
    執行在 commit 中途被強制中斷、backup_dir 是唯一僅存舊資料的殘留情況。這一步
    之後,backup_dir 保證不存在。
    """
    _recover_or_clear_stale_backup(out_dir, backup_dir, "legacy_supplement")
    moved_old = False
    if out_dir.exists():
        out_dir.rename(backup_dir)
        moved_old = True
    try:
        staging_dir.rename(out_dir)
    except Exception:
        if moved_old and backup_dir.exists() and not out_dir.exists():
            backup_dir.rename(out_dir)      # commit 失敗,把舊資料還原
        raise
    # ---- commit point 之後:out_dir 已經是新資料,以下純粹是收尾 ----
    if backup_dir.exists():
        try:
            shutil.rmtree(backup_dir)
        except Exception as e:
            print(f"⚠ 發布成功,但清理舊備份 {backup_dir} 失敗:{e}"
                  f" (不影響 {out_dir} 內容,下次執行會自動清掉)", file=sys.stderr)


def main():
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True)

    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_relpath": SCRIPT_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "script_sha256": _sha256_of(SCRIPT_PATH),
        "sources": {},
        "outputs": {},
        "overall_status": "PENDING",
    }

    try:
        for name, src_path in SOURCES.items():
            if not src_path.exists():
                raise FileNotFoundError(f"找不到來源檔:{src_path}")
            receipt["sources"][name] = {
                "relpath": src_path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": _sha256_of(src_path),
            }

        for name, extractor in EXTRACTORS.items():
            df, dedup_stats = extractor()
            staged_path = STAGING_DIR / f"{name}.parquet"
            df.to_parquet(staged_path, index=False)
            profile = _profile(df, key_cols=["stock_id", "date"])
            enforce_output_spec(df, name, profile)
            receipt["outputs"][name] = {
                "sha256": _sha256_of(staged_path),
                **profile,
                # Round 6 review:去重/重疊統計要留在 receipt 裡,不能只是 stderr
                # 上一閃而過的 console 訊息——那不算稽核紀錄。
                "dedup": dedup_stats,
            }
            print(f"{name}: {profile['row_count']} 列,{profile['stock_count']} 檔,"
                  f"{profile['date_min']} ~ {profile['date_max']}")

        receipt["overall_status"] = "PASS"
    except Exception as e:
        receipt["overall_status"] = "FAIL"
        receipt["error"] = str(e)
        with open(STAGING_DIR / "receipt.json", "w", encoding="utf-8") as f:
            json.dump(receipt, f, ensure_ascii=False, indent=2, default=str)
        print(f"FAIL:{e}", file=sys.stderr)
        print(f"staging 保留在 {STAGING_DIR} 供檢查,正式目錄 {OUT_DIR} 未變動", file=sys.stderr)
        sys.exit(1)

    with open(STAGING_DIR / "receipt.json", "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2, default=str)

    publish_staging(STAGING_DIR, OUT_DIR, BACKUP_DIR)
    print(f"\n已發布至 {OUT_DIR},receipt: {OUT_DIR / 'receipt.json'}")


if __name__ == "__main__":
    main()
