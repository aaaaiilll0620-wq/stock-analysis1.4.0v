# Seal critical section — runbook

**依據：** M-3 裁決（2026-08-18）「Seal race condition」；master preregistration v1.14（C-47）
**適用：** 取 B0 Baseline Seal，以及日後取 L2 Run Provenance

---

## 1. 問題

本倉庫存在**自動排程 commit 機制**。實測證據：commit `5397e28e`
（作者 `aaaaiilll0620-wq`，2026-08-18 19:21）在 finalization 進行中自行落地，
內容為 `cloud_cache/` 的 scores 快照，由 `deploy_scores.py` 的 `git add cloud_cache` 產生。

因此下列兩句話**不是同一個主張**：

> 「我檢查的時候工作區是乾淨的」
> 「封存的那一刻工作區是乾淨的」

`seal(final_seal=True)` 綁 `commit_sha` 並宣告 clean tree。若排程工作在
preflight 與寫入 seal 之間 commit，該 seal 綁的是一棵已經不存在的樹 ——
**它什麼都沒綁**。

---

## 2. 兩道防線

### 2.1 程式內：`RepoIdentityGuard`（自動，不可略過）

`core/b0_provenance.py`：

```python
guard = RepoIdentityGuard.snapshot(repo_root=REPO)   # preflight 之前快照
...                                                   # 組 manifest、驗證各 section
seal(manifest, final_seal=True, guard=guard)          # 回傳 hash 前的最後一步重驗
```

`recheck()` 重驗四項，任一改變即 `SealRaceError` abort：

| 檢查 | 為什麼 |
|---|---|
| `HEAD` 未移動 | 有人 commit 了 |
| 工作區乾淨度未改變 | 有人寫入了檔案 |
| 全部 normative module hashes 未變 | 實作在封存中途被改 |
| `assert_declarations_conform()` 通過 | 宣告與行為在封存中途脫鉤 |

重點是**位置**：`guard.recheck()` 是 `seal()` 回傳 hash **之前的最後一個語句**。
放在前面就只是另一次 preflight。

### 2.2 作業面：封存期間讓排程工作靜止

**不得永久刪除排程工作** —— 它是正常營運機制，不是 finalization 的清理對象。
只在 critical section 內停用，事後還原。

```bash
SCH=/mnt/c/Windows/System32/schtasks.exe

# 1) 停用（可逆，不需系統管理員權限）
"$SCH" /change /tn "\FinMind_DailyUpdate"       /disable
"$SCH" /change /tn "\Market_SnapshotCollector"  /disable

# 2) 確認兩者皆為「已停用」
"$SCH" /query /tn "\FinMind_DailyUpdate"      /fo LIST /v | grep -i 排程工作狀態
"$SCH" /query /tn "\Market_SnapshotCollector" /fo LIST /v | grep -i 排程工作狀態

# 3) 取封存
python scripts/b0_baseline_seal.py

# 4) 還原（**必做**）
"$SCH" /change /tn "\FinMind_DailyUpdate"       /enable
"$SCH" /change /tn "\Market_SnapshotCollector"  /enable
```

會動到本倉庫的排程工作**只有這兩個**（其餘為 OneDrive / Google / Windows 自身）。

---

## 3. 為什麼兩道都要

停用排程工作是**作業約定**，會被忘記、會被新工作繞過、在別台機器上不成立。
`RepoIdentityGuard` 是**機械保證**，忘了停用時仍會 abort。

反過來，只有 guard 也不夠：它會讓封存**失敗**，但不會讓封存**成功**——
在排程工作活躍的時段反覆重試只是反覆撞上同一個 race。

⇒ 作業面降低發生率，程式面保證不會被靜默接受。

---

## 4. 執行紀錄

見 `docs/SealCriticalSection_Runbook_Evidence.md`（每次封存追加一筆）。
