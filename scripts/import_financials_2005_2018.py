# -*- coding: utf-8 -*-
"""import_financials_2005_2018.py — 把 TEJ 2005-2018 合併季財報併入 tej_cache/financial_statements。
================================================================================
來源:tej_exports/inbox/2005-2018 三大財報+ROE.xlsx (合併報表,金額=千元)
目標:~/tej_cache/financial_statements/<股號>.parquet (現有僅2019+,金額=元)

處理:
  · 金額欄 ×1000 (千元→元,對齊現有2019+口徑;已用2330/2317跨界真實值驗證)
  · 年/月「2018/12」→ date「2018-12-01」(季末月-01,對齊現有)
  · 丟棄 ROE 欄 (現有schema無;build_pit由淨利/權益自算)
  · 有現有檔→前綴2005-2018後去重排序;無現有檔(下市股)→新建 (避免存活者偏誤)

安全:預設 DRY-RUN 只報告 + 交界連續性檢查;--commit 才寫入,且先備份整個資料夾。
用法:python scripts/import_financials_2005_2018.py            # dry-run
      python scripts/import_financials_2005_2018.py --commit   # 實際寫入
================================================================================
"""
from __future__ import annotations
import sys
import shutil
from pathlib import Path
import pandas as pd

SRC = Path("tej_exports/inbox/2005-2018 三大財報+ROE 上下市.xlsx")
FS_DIR = Path.home() / "tej_cache" / "financial_statements"
BACKUP = Path.home() / "tej_cache" / "financial_statements_backup_pre2005merge"

COLS = ["stock_id", "name", "ym", "quarter", "revenue", "gross_profit", "operating_income",
        "net_income", "eps", "recurring_net_income", "total_assets", "total_liabilities",
        "current_assets", "current_liabilities", "equity", "operating_cash_flow", "capex", "roe"]
MONEY = ["revenue", "gross_profit", "operating_income", "net_income", "recurring_net_income",
         "total_assets", "total_liabilities", "current_assets", "current_liabilities",
         "equity", "operating_cash_flow", "capex"]
# 現有 schema 欄序
TARGET = ["stock_id", "date", "quarter", "eps", "stock_name", "revenue", "gross_profit",
          "operating_income", "net_income", "recurring_net_income", "total_assets",
          "total_liabilities", "current_assets", "current_liabilities", "equity",
          "operating_cash_flow", "capex"]


def load_new() -> pd.DataFrame:
    df = pd.read_excel(SRC)
    df.columns = COLS
    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    df = df[df["stock_id"].str.match(r"^\d{4}$")]                      # 只留4位數股號
    df["date"] = pd.to_datetime(df["ym"].astype(str).str.replace("/", "-") + "-01",
                                errors="coerce").dt.strftime("%Y-%m-%d")
    for c in MONEY:
        df[c] = pd.to_numeric(df[c], errors="coerce") * 1000.0        # 千元 → 元
    df["eps"] = pd.to_numeric(df["eps"], errors="coerce")
    df["quarter"] = pd.to_numeric(df["quarter"], errors="coerce").astype("Int64")
    df = df.rename(columns={"name": "stock_name"})
    df = df.dropna(subset=["date"])
    return df[TARGET]


def main(commit: bool):
    if not SRC.exists():
        print(f"❌ 找不到來源:{SRC}"); sys.exit(1)
    new = load_new()
    stocks = sorted(new["stock_id"].unique())
    print(f"來源:{len(new)} 列, {len(stocks)} 檔, {new['date'].min()} ~ {new['date'].max()}\n")

    extended, created, boundary_checks = 0, 0, []
    for sid in stocks:
        n = new[new["stock_id"] == sid].sort_values("date")
        exf = FS_DIR / f"{sid}.parquet"
        if exf.exists():
            ex = pd.read_parquet(exf)
            ex["date"] = ex["date"].astype(str)
            merged = (pd.concat([n, ex], ignore_index=True)
                      .drop_duplicates("date", keep="last")            # 交界重疊以現有為準
                      .sort_values("date").reset_index(drop=True))
            extended += 1
            # 交界連續性:新檔最後季 vs 現有最早季 的營收量級比 (抓單位/口徑斷裂)
            if sid in ("1101", "2330", "2317", "2454", "2603"):
                last_new = n[n["date"] <= "2018-12-01"]["revenue"].dropna()
                first_ex = ex.sort_values("date")["revenue"].dropna()
                if len(last_new) and len(first_ex):
                    boundary_checks.append((sid, last_new.iloc[-1], first_ex.iloc[0]))
        else:
            merged = n.reset_index(drop=True)
            created += 1
        if commit:
            merged.to_parquet(exf, index=False)

    print(f"{'✅ 已寫入' if commit else '🔍 DRY-RUN (未寫入)'}:")
    print(f"  延伸現有檔 (接2019+): {extended}")
    print(f"  新建下市股檔 (僅2005-2018): {created}")
    print(f"\n交界連續性檢查 (新檔2018末季營收 vs 現有2019首季營收,量級應相近):")
    print(f"  {'股號':<8}{'新檔2018末(億)':>16}{'現有2019初(億)':>16}{'比值':>8}")
    for sid, ln, fe in boundary_checks:
        print(f"  {sid:<8}{ln/1e8:>16.1f}{fe/1e8:>16.1f}{fe/ln:>8.2f}")
    print("\n→ 比值應落在 0.5~1.5 (季節性);若~1000 或~0.001 表單位沒對齊。")
    if not commit:
        print(f"\n確認無誤後執行:python scripts/import_financials_2005_2018.py --commit")
        print(f"(--commit 會先備份到 {BACKUP.name} 再寫入)")


if __name__ == "__main__":
    commit = "--commit" in sys.argv
    if commit and not BACKUP.exists():
        print(f"備份 {FS_DIR.name} → {BACKUP.name} ...")
        shutil.copytree(FS_DIR, BACKUP)
        print("備份完成。\n")
    main(commit)
