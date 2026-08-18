# Seal critical section — 執行紀錄

每次封存追加一筆。程序見 `docs/SealCriticalSection_Runbook.md`。

---

## 2026-08-18 · B0 BASELINE SEAL（第一次）

### 封存結果

```
BASELINE SEAL          bdc69c320b09b1a79c0de35b2f9fc471a8231ab51c8b5c3721beab7819397362
sealed_input_sha256    4952c35b28c2ecdf25128bc02cb8499224102e116ebe8bdfaa1b9cc71ab53a16
stage                  B0_BASELINE_SEAL
commit_sha             4101df91a292e33aa8f6398d08083003be07e6b6
clean_tree             True
spec                   docs/FrozenB0_MasterPreregistration.md v1.14
spec_sha256            9d4fde9f8576f9f6cc0f3b6e0e37355a2584cb44e995069f819d40b05424f98a
config_hash            fad64b65148d9d7f550aaf0d2c38ad27dcb47f399b237ed8d3a07181398f5567 (122 keys)
canonical_hash_version b0_canonical_hash@1
normative modules      23 / 23
datasets               3  (b0_price_universe_20260817 / b0_trading_calendar / b0_security_status)
derived artefacts      10 (皆附 upstream lineage)
opening state hash     74aa7acc49220570339598bd4c66e7f2cee8b950a92376e95fef15f537e0cd4b
route                  core.b0_route @ b0_canonical_hash@1
execution.status       NOT_EXECUTED_PRE_L2
output.status          NOT_PRODUCED_PRE_L2
記錄檔                 artifacts/baseline_seal/b0_baseline_seal.json
記錄檔 sha256          557ecec6e453a45309ade47b7d38c4c0951fafd4df664bedbd464b6d4eb62622
```

> **`config_hash` 與 v1.13 完全相同**（`fad64b65…398f5567`）。
> 這是 C-47 未觸碰任何策略語義的機械證據 —— 若 Selection / Eligibility /
> Portfolio / Execution / Cost 有任何一項被改動，122 個 key 的 registry hash 必變。

### 排程工作靜止（作業面）

| 時點 | `\FinMind_DailyUpdate` | `\Market_SnapshotCollector` |
|---|---|---|
| 封存前（停用） | 已停用 | 已停用 |
| **封存期間** | **已停用** | **已停用** |
| 封存後（還原） | 已啟用，下次 2026/8/19 18:00 | 已啟用，下次 2026/8/19 17:30 |

指令與回應：

```
schtasks /change /tn "\FinMind_DailyUpdate"      /disable → 成功
schtasks /change /tn "\Market_SnapshotCollector" /disable → 成功
   (查詢確認：兩者「排程工作狀態: 已停用」)
python scripts/b0_baseline_seal.py                        → BASELINE SEAL 取得
schtasks /change /tn "\FinMind_DailyUpdate"      /enable  → 成功
schtasks /change /tn "\Market_SnapshotCollector" /enable  → 成功
   (查詢確認：兩者「排程工作狀態: 已啟用」，下次執行時間如上表)
```

**兩個排程工作皆已還原，未被刪除。**

### 程式面保證（`RepoIdentityGuard`）

- preflight 前快照 HEAD `4101df91…`、clean tree `True`、23 個 normative hashes
- `seal()` 回傳 hash 前的最後一步重驗四項，全部未變動 → 未觸發 `SealRaceError`
- 封存前後 HEAD 均為 `4101df91a292e33aa8f6398d08083003be07e6b6`，工作區 0 entries

### 封存當下的狀態

```
OPEN SPEC ITEMS           0
OPEN FINALIZATION ITEMS   0
declaration conformance   17 declarations (7 derived / 10 behavioural), 0 failures
unmet blocking            []
canonical 測試套件        1961 passed, 2 skipped
clean tree → 套件 → clean tree   通過（tests/test_repo_tree_cleanliness.py）
```

### 未進行（明文）

- **L2 未開封。** `l2_opened: false`
- 未執行任何 B0 decision route；`run_decision` 未被匯入或呼叫
- `performance_computed: false`、`selection_computed: false`
- 未計算 CAGR / Sharpe / MDD / IC / win rate；未產生 target / intent / receipt / NAV
- 未檢視任何 B0 選股名單或投組

開封 L2 需使用者明示授權，且需另行建立 L2 Run Provenance 引用
`baseline_seal_sha256 = bdc69c32…`。
