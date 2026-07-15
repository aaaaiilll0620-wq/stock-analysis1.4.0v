"""
一鍵更新雲端 scores 快照 → commit → push
================================================================================
把本機 finmind_cache 的 `Scores` 快取,同步成 repo 內的 `cloud_cache/Scores` 快照,
然後 git add / commit / push。之後 Streamlit Community Cloud 會自動重部署,
「綜合分選股」分頁就會是最新的基準日。

用法 (在專案根目錄):
  python deploy_scores.py                 # 只同步『目前的』scores → commit → push
  python deploy_scores.py --rebuild-scores# 先用本機原始快取重算 scores (0 API) 再同步
  python deploy_scores.py --update-all     # 先跑 build_cache (原始資料增量 + scores;會用 API) 再同步
  python deploy_scores.py --no-push        # 只同步 + commit,不 push (自己檢查後再手動 push)
  python deploy_scores.py --message "xxx"  # 自訂 commit 訊息

Windows 可直接雙擊 update_and_push.bat (它會呼叫這支)。
================================================================================
"""
from __future__ import annotations

import os
import sys
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DATASET = "Scores"
SNAPSHOT_DIR = REPO_ROOT / "cloud_cache" / DATASET


# ------------------------------------------------------------------------------
def _cache_scores_dir() -> Path:
    """本機 Scores 快取來源目錄 (優先用 data_cache.CACHE_DIR,失敗退回同一套預設邏輯)。"""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from core import data_cache
        return Path(data_cache.CACHE_DIR) / DATASET
    except Exception:
        base = os.environ.get("FINMIND_CACHE", str(Path.home() / "finmind_cache"))
        return Path(base) / DATASET


def _run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """在 repo 根目錄執行指令,輸出直接顯示。"""
    print(f"→ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(REPO_ROOT), check=check)


def _git_output(cmd: list) -> str:
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True).stdout.strip()


# ------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="更新雲端 scores 快照 → commit → push")
    ap.add_argument("--rebuild-scores", action="store_true",
                    help="先用本機原始快取重算 scores (0 API) 再同步")
    ap.add_argument("--update-all", action="store_true",
                    help="先跑 build_cache.py (原始資料增量 + scores;會用 API) 再同步")
    ap.add_argument("--no-push", action="store_true", help="只同步 + commit,不 push")
    ap.add_argument("--message", default=None, help="自訂 commit 訊息")
    args = ap.parse_args()

    py = sys.executable

    # 0) 確認是 git repo
    if not (REPO_ROOT / ".git").exists():
        print("❌ 這裡不是 git repo。請先 git init / git remote add origin … (見 DEPLOY_streamlit_cloud.md 步驟 3)。")
        return 1

    # 1) (選用) 先重建 scores
    if args.update_all:
        print("\n== 先跑 build_cache.py (原始資料增量 + scores;會用 API) ==")
        _run([py, "build_cache.py"])
    elif args.rebuild_scores:
        print("\n== 先重算 scores (0 API,讀本機原始快取) ==")
        _run([py, "build_cache.py", "--build-scores"])

    # 2) 同步本機 Scores → repo/cloud_cache/Scores
    src = _cache_scores_dir()
    print(f"\n== 同步 scores 快照 ==\n  來源:{src}\n  目標:{SNAPSHOT_DIR}")
    if not src.exists() or not any(src.glob("*.parquet")):
        print(f"❌ 找不到 scores 快取 ({src})。請先 python build_cache.py --build-scores"
              f" (或加 --rebuild-scores 讓本腳本代跑)。")
        return 1
    if SNAPSHOT_DIR.exists():
        shutil.rmtree(SNAPSHOT_DIR)          # 清掉舊快照 (含已下市/移除的檔),確保與來源一致
    shutil.copytree(src, SNAPSHOT_DIR)
    n = len(list(SNAPSHOT_DIR.glob("*.parquet")))
    print(f"  ✅ 已複製 {n} 個 parquet 到 cloud_cache/Scores")

    # 2b) 同步全市場掃描名單 (最近 N 個交易日 shortlist + 最新 pool/digest)
    #     → cloud_cache/UniversePool,供雲端版「🌐 全市場掃描」分頁 (app.py 有 fallback)。
    univ_src = REPO_ROOT / "outputs" / "universe_pool"
    univ_snap = REPO_ROOT / "cloud_cache" / "UniversePool"
    keep = 40   # 連續在榜回看窗
    sls = sorted(univ_src.glob("shortlist_*.csv"))[-keep:] if univ_src.exists() else []
    if sls:
        if univ_snap.exists():
            shutil.rmtree(univ_snap)
        univ_snap.mkdir(parents=True)
        latest_date = sls[-1].stem.replace("shortlist_", "")
        for f in [*sls, univ_src / f"pool_{latest_date}.csv", univ_src / f"digest_{latest_date}.md"]:
            if f.exists():
                shutil.copy2(f, univ_snap / f.name)
        print(f"  ✅ 已同步 {len(sls)} 天 shortlist + 最新 pool/digest 到 cloud_cache/UniversePool")

    # 3) git add / 判斷有無變化 / commit
    _run(["git", "add", "cloud_cache"])
    staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", "cloud_cache"],
                            cwd=str(REPO_ROOT))
    if staged.returncode == 0:
        print("\nℹ️ cloud_cache 沒有變化 (scores 與上次快照相同),不需 commit/push。")
        return 0
    msg = args.message or f"chore: update scores snapshot ({datetime.now():%Y-%m-%d %H:%M})"
    _run(["git", "commit", "-m", msg])

    # 提醒:若還有其他未提交的變更 (例如改了程式),本腳本只提交了 cloud_cache
    other = _git_output(["git", "status", "--porcelain"])
    if other:
        print("ℹ️ 注意:仍有其他未提交變更 (本腳本只提交 cloud_cache):")
        print(other)

    # 4) push
    if args.no_push:
        print("\n✅ 已 commit,未 push (--no-push)。確認後自行 git push。")
        return 0
    branch = _git_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "main"
    print(f"\n== push 到 origin/{branch} ==")
    try:
        _run(["git", "push", "origin", branch])
    except subprocess.CalledProcessError:
        print("⚠️ push 失敗。可能是尚未設 upstream —— 嘗試 git push -u …")
        try:
            _run(["git", "push", "-u", "origin", branch])
        except subprocess.CalledProcessError:
            print("❌ push 仍失敗。請檢查:git remote -v 是否設好、GitHub 登入/權限是否正常。")
            return 1

    print("\n🎉 完成!Streamlit Community Cloud 會自動重新部署,稍等幾分鐘選股分頁就是新的基準日。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
