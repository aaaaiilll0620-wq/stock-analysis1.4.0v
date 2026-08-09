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
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DATASET = "Scores"
SNAPSHOT_DIR = REPO_ROOT / "cloud_cache" / DATASET

# Streamlit Community Cloud 綁定的部署分支 (見 DEPLOY_streamlit_cloud.md 步驟 4)。
# 快照推到別的分支 = 雲端看不到,而且腳本仍會回報成功 —— 2026-08-03~08-07 就是這樣
# 靜默停更了 5 天。所以這裡改成 fail-closed:不在部署分支上就不做事、不 commit。
DEPLOY_BRANCH = "main"


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


def _run(cmd: list, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """執行指令,輸出直接顯示。cwd 預設 repo 根目錄(鏡像流程會指到 worktree)。"""
    print(f"→ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(cwd or REPO_ROOT), check=check)


def _git_output(cmd: list, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=str(cwd or REPO_ROOT),
                          capture_output=True, text=True).stdout.strip()


# ------------------------------------------------------------------------------
def _mirror_to_deploy_branch(deploy_branch: str, msg: str) -> int:
    """把目前工作區的 cloud_cache/ 鏡像到部署分支並 push。

    用 `git worktree` 在暫存目錄檢出部署分支,**完全不動目前工作區** ——
    不切分支、不碰未提交的研究修改。這樣在功能分支上做研究的同時,
    雲端快照仍然會每天更新。

    註:快照同時被 commit 在目前分支與部署分支。日後功能分支併回部署分支時,
    cloud_cache 底下的 parquet 會有 binary conflict —— 那是預期的,取任一邊即可
    (兩邊都是同一天的快照)。
    """
    print(f"\n== 鏡像 cloud_cache 到部署分支 `{deploy_branch}` ==")
    if _git_output(["git", "rev-parse", "--verify", "--quiet", deploy_branch]) == "":
        print(f"[ERROR] 本機沒有分支 `{deploy_branch}`。請先 git fetch origin {deploy_branch}"
              f" && git branch {deploy_branch} origin/{deploy_branch}")
        return 1

    tmp_parent = tempfile.mkdtemp(prefix="deploy_mirror_")
    wt = Path(tmp_parent) / "wt"          # 葉節點必須不存在,worktree add 才會建立
    try:
        _run(["git", "fetch", "origin", deploy_branch])
        try:
            _run(["git", "worktree", "add", str(wt), deploy_branch])
        except subprocess.CalledProcessError:
            print(f"[ERROR] 無法檢出 `{deploy_branch}` 到暫存 worktree —— "
                  f"通常是該分支已在別處被檢出。請先切離該分支再重跑。")
            return 1

        # 部署分支必須與遠端一致才 push,否則會 non-fast-forward 失敗
        try:
            _run(["git", "merge", "--ff-only", f"origin/{deploy_branch}"], cwd=wt)
        except subprocess.CalledProcessError:
            print(f"[ERROR] `{deploy_branch}` 與 origin/{deploy_branch} 已分岔,無法 fast-forward。"
                  f"請手動處理後再重跑(本次沒有推送任何東西)。")
            return 1

        src = REPO_ROOT / "cloud_cache"
        dst = wt / "cloud_cache"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

        _run(["git", "add", "cloud_cache"], cwd=wt)
        if subprocess.run(["git", "diff", "--cached", "--quiet", "--", "cloud_cache"],
                          cwd=str(wt)).returncode == 0:
            print(f"  部署分支的 cloud_cache 已經是最新的,不需 commit/push。")
            return 0

        _run(["git", "commit", "-m", msg], cwd=wt)
        _run(["git", "push", "origin", deploy_branch], cwd=wt)
        print(f"  已推送到 origin/{deploy_branch} —— Streamlit Cloud 會自動重新部署。")
        return 0
    finally:
        # 無論成敗都要拆掉 worktree,否則會在 .git/worktrees 留下孤兒紀錄
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                       cwd=str(REPO_ROOT), capture_output=True)
        shutil.rmtree(tmp_parent, ignore_errors=True)


# ------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="更新雲端 scores 快照 → commit → push")
    ap.add_argument("--rebuild-scores", action="store_true",
                    help="先用本機原始快取重算 scores (0 API) 再同步")
    ap.add_argument("--update-all", action="store_true",
                    help="先跑 build_cache.py (原始資料增量 + scores;會用 API) 再同步")
    ap.add_argument("--no-push", action="store_true", help="只同步 + commit,不 push")
    ap.add_argument("--message", default=None, help="自訂 commit 訊息")
    ap.add_argument("--deploy-branch", default=DEPLOY_BRANCH,
                    help=f"Streamlit Cloud 綁定的部署分支 (預設 {DEPLOY_BRANCH})")
    ap.add_argument("--no-mirror", action="store_true",
                    help="⚠ 不在部署分支時,不要鏡像過去 (快照不會出現在雲端網頁上)")
    args = ap.parse_args()

    py = sys.executable

    # 0) 確認是 git repo
    if not (REPO_ROOT / ".git").exists():
        print("❌ 這裡不是 git repo。請先 git init / git remote add origin … (見 DEPLOY_streamlit_cloud.md 步驟 3)。")
        return 1

    # 0b) 確認部署分支。舊版在這裡用 rev-parse HEAD 當 push 目標,結果 2026-08-03~08-07
    #     的快照全 commit 到功能分支,雲端停在 07-30 而腳本天天回報成功。
    #     現在不在部署分支時**不是失敗**:快照照樣 commit 在目前分支(維持工作區乾淨),
    #     另外用 git worktree 把同一份 cloud_cache 鏡像到部署分支並 push。
    #     這一段刻意不用 emoji —— 直接執行(沒有 bat 的 PYTHONIOENCODING=utf-8)時,
    #     cp950 主控台會讓 print 本身丟 UnicodeEncodeError,蓋掉最該被讀到的訊息。
    current = _git_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    need_mirror = (current != args.deploy_branch) and not args.no_mirror
    if current != args.deploy_branch:
        if args.no_mirror:
            print(f"\n[WARN] 目前在 `{current}` 且指定了 --no-mirror:"
                  f"這份快照**不會**出現在雲端(部署分支是 `{args.deploy_branch}`)。")
        else:
            print(f"\n[INFO] 目前在 `{current}`,不是部署分支 `{args.deploy_branch}`。"
                  f"快照會先 commit 在本分支,再自動鏡像到部署分支。")

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
    msg = args.message or f"chore: update scores snapshot ({datetime.now():%Y-%m-%d %H:%M})"
    if staged.returncode == 0:
        print("\nℹ️ cloud_cache 相對本分支沒有變化,不需 commit。")
        # 但部署分支可能仍落後 (例如本分支昨天就 commit 過、main 卻沒跟上),
        # 所以鏡像照跑 —— 它自己會判斷部署分支那邊有沒有差異。
        if need_mirror and not args.no_push:
            return _mirror_to_deploy_branch(args.deploy_branch, msg)
        return 0
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
    # 用 0b 已驗證過的分支,不重新從 HEAD 推導 —— 重推導正是舊版靜默推到功能分支的原因。
    branch = current or args.deploy_branch
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

    # 5) 不在部署分支時,把同一份快照鏡像過去 —— 沒有這一步,雲端永遠看不到。
    if need_mirror:
        rc = _mirror_to_deploy_branch(args.deploy_branch, msg)
        if rc != 0:
            print("\n❌ 快照已 commit 到目前分支,但鏡像到部署分支失敗 —— **雲端還是舊的**。")
            return rc

    print("\n🎉 完成!Streamlit Community Cloud 會自動重新部署,稍等幾分鐘選股分頁就是新的基準日。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
