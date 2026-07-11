"""
organize.py — 一次性整理:把散落在專案根目錄的『輸出 / 文件 / 備份』歸位到子資料夾。

安全設計:只搬「已知的輸出/文件/備份」類型,**絕不動** .py 原始碼與 core/tests/utils/data 等資料夾。
搬移後,程式未來產生的新輸出也會自動存進這些資料夾 (已在 main.py / backtest.py / run_backtest.py 設定)。

用法:
  python organize.py          # 實際搬移
  python organize.py --dry    # 只預覽會搬什麼,不動任何檔案

歸位規則:
  outputs/excel   ← 排行結果_*.xlsx/.csv、回測排行_*.xlsx
  outputs/charts  ← equity_curve*.png、market_neutral_curve*.png
  outputs/logs    ← *.log
  docs            ← REFACTOR_NOTES.md、開發日誌_DevLog.md
  backups         ← *.bak
"""
import os
import sys
import glob
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv or "-n" in sys.argv

RULES = [
    ("outputs/excel",  ["排行結果_*.xlsx", "排行結果_*.csv", "回測排行_*.xlsx"]),
    ("outputs/charts", ["equity_curve*.png", "market_neutral_curve*.png"]),
    ("outputs/logs",   ["*.log"]),
    ("docs",           ["REFACTOR_NOTES.md", "REFACTOR_NOTES.docx",
                        "開發日誌_DevLog.md", "開發日誌_DevLog.docx"]),
]
# .bak 備份檔改用『全專案遞迴』收集 (含 core/ tests/ 內的),集中到 backups/
# 保護名單:即使符合樣式也絕不搬移
PROTECT = {"main.py", "run_backtest.py", "organize.py", "CLAUDE.md"}


def _unique_dest(dst_dir, name):
    dst = os.path.join(dst_dir, name)
    if not os.path.exists(dst):
        return dst
    base, ext = os.path.splitext(name)
    return os.path.join(dst_dir, f"{base}_{datetime.now().strftime('%H%M%S')}{ext}")


def main():
    print("=" * 56)
    print("📁 專案整理 " + ("(預覽模式,不會實際搬移)" if DRY else "(實際搬移)"))
    print("=" * 56)
    moved = 0
    for subdir, patterns in RULES:
        dst_dir = os.path.join(ROOT, subdir)
        for pat in patterns:
            for src in sorted(glob.glob(os.path.join(ROOT, pat))):
                name = os.path.basename(src)
                if not os.path.isfile(src) or name in PROTECT:
                    continue
                os.makedirs(dst_dir, exist_ok=True)
                dst = _unique_dest(dst_dir, name)
                print(f"  {'[預覽] ' if DRY else '✓ '}{name}  →  {subdir}/")
                if not DRY:
                    try:
                        shutil.move(src, dst)
                    except Exception as e:
                        print(f"    ⚠️ 搬移失敗 ({e}) — 可能檔案開啟中,請關閉後重試。")
                        continue
                moved += 1

    # .bak 遞迴收集 (含子資料夾),但略過已在 backups/ 內者
    bak_dir = os.path.join(ROOT, "backups")
    for src in sorted(glob.glob(os.path.join(ROOT, "**", "*.bak"), recursive=True)):
        if not os.path.isfile(src) or os.path.dirname(src) == bak_dir:
            continue
        os.makedirs(bak_dir, exist_ok=True)
        rel = os.path.relpath(src, ROOT).replace(os.sep, "_")   # 保留來源路徑避免同名衝突
        dst = _unique_dest(bak_dir, rel)
        print(f"  {'[預覽] ' if DRY else '✓ '}{os.path.relpath(src, ROOT)}  →  backups/")
        if not DRY:
            try:
                shutil.move(src, dst)
            except Exception as e:
                print(f"    ⚠️ 搬移失敗 ({e})")
                continue
        moved += 1

    print("-" * 56)
    if moved == 0:
        print("根目錄已經很乾淨,沒有需要搬移的輸出/文件/備份檔。")
    else:
        print(f"{'將搬移' if DRY else '已搬移'} {moved} 個檔案。"
              + ("  (拿掉 --dry 即實際執行)" if DRY else ""))
    print("未來新產生的 Excel / 圖表 / log 會自動存進 outputs/ 子資料夾。")


if __name__ == "__main__":
    main()
