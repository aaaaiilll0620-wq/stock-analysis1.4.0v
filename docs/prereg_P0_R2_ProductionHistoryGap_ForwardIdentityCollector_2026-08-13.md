# P0-R2 Production History Gap Diagnosis / Forward Identity Collector 規格

**Author:** Codex（依使用者指示起草）  
**Date:** 2026-08-13  
**Status:** `APPROVED`（Stage 1 only — 2026-08-13）／Stage 1 授權範圍：Phase H 唯讀歷史缺口診斷、離線 tests、collector 離線實作與 dry-run、R-FWD parity adapter 離線實作與測試。Stage 2（Primary/Mirror evidence roots、R-FWD forward/live collection、Collector live writes、Task Scheduler、production 計算/狀態寫入）尚未核准，MUST NOT 執行；不得回填歷史、不得建立 live evidence roots、不得修改排程、不得改動任何 production 計算或狀態。見 §15。  
**研究代號:** `P0-R2`  
**前置研究:** P0-R1，commit `34861b29`  
**前置結論:** `NO_COMPARABLE_DATES / INSUFFICIENT_HISTORY`  
**建議文件路徑:** `docs/prereg_P0_R2_ProductionHistoryGap_ForwardIdentityCollector_2026-08-13.md`  
**工作類型:** 保存缺口診斷 + 前瞻證據蒐集工程；不是策略研究、歷史回填或 production 對齊

---

## Context

P0-R1 原定比較 frozen research dual100 與 production 候選管線的 decision clock、universe、raw score、rank、fusion 與 L4a handoff，但 Phase B 發現三方沒有任何共同決策日期。研究面板有 255 個月，範圍為 2005-01-31 至 2026-03-31；production A（`score_store`）當時只有 2026-07-08 起的日頻資料；production B（`c2_fullpool_*.csv`）只有 2026-08-07 起的三個日期。因此 `comparable_dates=0`，R1-P FAIL，後續 gates 均未評估。

目前程式碼提供兩項重要線索，但都不是完成的根因裁決：

1. `core/score_store.py` 宣稱每檔 Parquet 以 `(as_of, mode)` append、同鍵 keep-last；這表示現行資料模型具備保留多日的能力，不等於過去日期曾被實際產生。
2. `scripts/universe_screen_daily.py` 以日期命名 `c2_fullpool_{as_of}.csv`，既有同名檔預設不覆寫；但該輸出是 2026-08-10 前後才加入 production 流程，短歷史可能源於功能啟用時間，也可能涉及排程、清理、分支鏡像或保存位置。

所以本案先回答「歷史為何不存在」，再建立只能向前累積的 identity evidence collector。兩部分共用治理規則，但判定分開：歷史缺口診斷不得順手修復；collector 不得用回算資料冒充 contemporaneous production evidence。

---

## 1. Objectives and non-claims

### 1.1 Objective H — History gap diagnosis

對 P-A（Scores）、P-B（c2_fullpool）及其部署鏡像逐一裁定短歷史的證據類型：

```text
NOT_PRODUCED
PRODUCED_THEN_DELETED
PRODUCED_ELSEWHERE_NOT_SYNCED
OVERWRITTEN_OR_TRUNCATED
DATE_DISCOVERY_OR_FORMAT_BUG
UNRESOLVED
```

### 1.2 Objective C — Forward identity collector

從核准啟用日開始，以 contemporaneous inputs 建立不可覆寫、可重播、可驗證的前瞻 identity evidence，使未來能在相同 decision date 比較：

```text
P-A production composite universe and scores
P-B production c2 fullpool and scores
P-app fusion membership
P-L4a fusion membership
R-FWD frozen-research-semantics reference（僅在 parity gate 通過後）
```

### 1.3 Explicit non-claims

本案不宣稱：

- 已恢復 2026-07 以前的 production history；
- 由目前資料回算的結果等同當時 production 輸出；
- daily observations 可替代月頻 R1；
- collector 的 Jaccard 能直接決定部署或策略優劣；
- R-FWD 是新的研究 Champion；
- 保存機制建立後 R1 即自動 PASS。

---

## Functional Requirements

### 2. Phase H — 唯讀歷史保存缺口診斷

- FR-1: 診斷 MUST 分別建立 P-A、P-B、部署鏡像與排程執行的 evidence timeline，不得只依目前檔案最早日期推測原因。
- FR-2: timeline MUST 包含可取得的程式引入 commit、檔案首次/最後時間、job log、排程紀錄、部署 commit、保存路徑與清理規則；不可取得的證據 MUST 標記 `NOT_AVAILABLE`。
- FR-3: 診斷 MUST 區分「程式可 append」與「歷史曾被實際產生」。沒有生成紀錄時不得裁定為刪除。
- FR-4: 對每個 source/date range，primary cause MUST 使用 §1.1 的固定 enum；證據不足時只能使用 `UNRESOLVED`。
- FR-5: `PRODUCED_THEN_DELETED` MUST 至少由歷史 manifest、log、commit、備份清單或檔案系統證據之一支持；僅憑目前缺檔不得使用。
- FR-6: `PRODUCED_ELSEWHERE_NOT_SYNCED` MUST 記錄來源位置、目的位置與兩邊 hash/date inventory；若來源已不可得，標記 `UNRESOLVED`。
- FR-7: Phase H MUST NOT 重建、回填、搬移、刪除或修改任何 Scores、c2_fullpool、cloud_cache、排程或 production state。
- FR-8: Phase H MUST 產出 `history_gap_timeline.csv`、`history_gap_findings.json` 與 `history_gap_report.md`。
- FR-9: `history_gap_findings.json` MUST 明列布林欄位 `active_cleanup_or_pruning_affecting_evidence_roots`，判定 Phase H 是否發現任何已知或可預期的清理/保留政策會刪除或截斷 collector 預定 evidence roots 上的證據。此欄位為 `TRUE` 或因證據不足只能標為 `UNKNOWN` 時，Gate C-A（見 §10）MUST FAIL，先另立修復規格；只有明確判定為 `FALSE` 才不阻擋 Gate C-A。本條不要求整個 Gate H-D PASS——診斷其餘部分（如 P-A/P-B 根因仍有 `UNRESOLVED`）與 collector 證據存續無關時，不影響本條判定。

### 3. Collector evidence clock

- FR-10: Collector MUST 只蒐集啟用後、實際存在且來源日期完全相同的 contemporaneous evidence；MUST NOT backfill。
- FR-11: 每次 run MUST 先列出 P-A 與 P-B 可用日期；只允許選擇 exact common `as_of`，不得 nearest-date、forward-fill 或沿用上一日。
- FR-12: Collector MAY 每個交易日執行，但每筆 evidence MUST 標記 `DAILY_DIAGNOSTIC` 或 `MONTHLY_ELIGIBLE`。
- FR-13: `MONTHLY_ELIGIBLE` MUST 定義為該月最後交易日的 after-close production evidence。不得用每月最後一次成功 run 自動冒充月底。
- FR-14: 月底資格在下一交易日才能確認時，Collector MUST append 一份 qualification receipt；不得改寫原 snapshot。
- FR-15: R1 只能使用 `MONTHLY_ELIGIBLE` 且 R-FWD/P-A/P-B 三方完整的日期。Daily evidence 不得混入正式 monthly identity 結論。
- FR-16: 在累積滿 24 個 comparable monthly dates 前，MUST 保持 `R1_REOPEN_NOT_ELIGIBLE`。6、12 個月 MAY 產出中期 diagnostic，但不得裁決 identity。

### 4. Production evidence capture

- FR-17: P-A snapshot MUST 保存該 `as_of`、`mode=balanced` 的全部原生 score rows，以及來源 Scores 檔清單、逐檔 hash、建置 universe、weights version 與 code/config hash。
- FR-18: P-B snapshot MUST 保存完整 `c2_fullpool_{as_of}.csv`、來源 hash、ADV floor、listed rule、c2 欄位 schema 與產生程式 hash。
- FR-19: Collector MUST 使用來源副本計算 P-app 與 P-L4a fusion，不得在計算途中重新讀會變動的 live files。
- FR-20: P-app 與 P-L4a 在相同 frozen input copies 上的 ticker set MUST exact match；不一致時 `identity_status = PRODUCTION_INTERNAL_DIVERGENCE`（見 §6a），但原始 evidence 仍須保存。
- FR-21: Collector MUST 在 `compute_order_intent` 之前停止；不得建立 OrderIntent、讀寫 PositionState 或呼叫 L4b。
- FR-22: Collector MUST 保存 raw score、native denominator、rank method、ties、threshold count、Top20 membership 與 final fusion membership，不得只保存最後名單。
- FR-23: `watchlist.txt` membership MUST 作 audit 欄位，但 Collector MUST NOT 修改 watchlist 或以其補齊任一 source。

### 5. R-FWD prospective reference

- FR-24: R-FWD MUST 使用 frozen research semantics。R-FWD 計算 process MUST 與 production evidence（P-A/P-B/P-app/P-L4a）擷取 process 完全隔離、不共用 import state（兩側各自獨立 process，不得在同一 process 內先後 import 兩邊模組）；擷取 production evidence 的那一側 process MUST NOT 載入 `beat_0050.realbody.bt_bundle` 或任何已知間接污染模組。
- FR-25: 在啟用 R-FWD 前，實作者 MUST 建立 reference adapter parity suite；對 frozen research 255 個月，final membership MUST 與 commit `5f3f5d31` 的 `canonical=False` baseline exact match。
- FR-26: parity suite 對共同 raw-score keys MUST value-equivalent；預設 tolerance `1e-12`。任何 tolerance 勘誤須在看 forward identity 結果前經使用者核准。
- FR-27: R-FWD MUST 寫入獨立 date-partitioned artifacts，不得 append 或覆寫 `obs_alpha.parquet`、`realbody_scores_adv100w.parquet`、`exec_ret.parquet` 或 P0-U1/P0-R1 產出。
- FR-28: R-FWD 只允許使用 decision time 當下可取得的 PIT inputs；不得讀未來報酬、`exec_ret.fwd_x` 或 decision date 之後發布的資料。
- FR-29: 若 frozen research semantics 無法在 forward date 不改定義地重建，run MUST 標記 `identity_status = R_FWD_UNAVAILABLE`（見 §6a）。P-only evidence可保存，但該日期不是 comparable date。
- FR-30: R-FWD adapter parity 未通過前，`identity_status` MUST 為 `P_ONLY_EVIDENCE`；不得標為 identity-capable。

### 6. Append-only and revision semantics

- FR-31: 每個 run identity MUST 為 `(as_of, collector_version, input_bundle_sha256)`，並有唯一 `run_id`。
- FR-32: 相同 run identity 重跑 MUST idempotent no-op，並回傳既有 receipt；不得產生重複 evidence。
- FR-33: 同一 `as_of` 若來源 bytes 改變，MUST 建立新 revision（新 run_id，`source_mutation = TRUE`、`revision_of` 指向舊 run_id，見 §6a）；不得覆寫舊 revision。
- FR-34: 每個 artifact MUST 先寫 temporary path、驗證 schema/hash，再 atomic rename；不完整 run 必須保存 failure receipt，不能留下看似成功的半套目錄。
- FR-35: ledger MUST append-only。更正只能追加 superseding record，不得編輯或刪除舊列。
- FR-36: evidence retention MUST 為無期限，除非使用者另行明確核准可稽核的 retention/cleanup 規格。

### 6a. Receipt status taxonomy

全文所有 receipt/health 狀態代碼 MUST 分別落在下列五個獨立欄位，不得混放：

| 欄位 | 允許值 | 用途 |
|---|---|---|
| `persistence_status` | `COMMITTED` \| `PENDING_MIRROR` \| `FAILED` | 這個 run 的證據有沒有安全落地（primary+mirror 雙驗證） |
| `identity_status` | `P_ONLY_EVIDENCE` \| `COMPARABLE_IDENTITY` \| `PRODUCTION_INTERNAL_DIVERGENCE` \| `R_FWD_UNAVAILABLE` | 這個 run 的證據能不能拿來做 identity 比對，以及比對本身的內部一致性 |
| `monthly_status` | `DAILY_DIAGNOSTIC` \| `QUALIFICATION_PENDING` \| `MONTHLY_ELIGIBLE` | 這個 as_of 對月頻 R1 重開門檻的資格 |
| `failure_code` | `MISSING_P_A` \| `MISSING_P_B` \| `DATE_MISMATCH` \| `SOURCE_DATE_CONFLICT` \| `HASH_MISMATCH` \| `SCHEMA_FAILURE` \| `LOW_DISK` \| `LOCK_HELD` \| `PARTIAL_WRITE` | `persistence_status == FAILED` 時，指出具體失敗原因；其餘狀態下必為 null |
| `source_mutation` | boolean（+ `revision_of` run_id 參照） | 標記同一 `as_of` 的來源 bytes 是否較前一 revision 改變 |

其中 `persistence_status`/`identity_status`/`monthly_status`/`source_mutation`/`revision_of` 為 `run_receipt.json` 欄位（見 Data Models）；`failure_code` 同時出現於 `run_receipt.json`（該次 run 自身的失敗原因）與 `health_summary.json`（`last_failure_code`，最近一次失敗 run 的原因快照）。任何實作或文件不得把上述代碼寫進錯誤的欄位（例如把 `DATE_MISMATCH` 寫進 `identity_status`，或把 `P_ONLY_EVIDENCE` 寫進 `persistence_status`）。

### 7. Durable storage and mirroring

- FR-37: Collector Activation 前 MUST 設定兩個彼此獨立的 storage roots：primary evidence root 與 mirror evidence root；不得以 hard link 或同一實體目錄的兩個路徑冒充雙副本。
- FR-38: 一個 run 只有在 primary 與 mirror 都完成 hash verification 後才能標記 `persistence_status = COMMITTED`。
- FR-39: mirror 不可用時 MUST 保存本地 `persistence_status = PENDING_MIRROR` 的 receipt 並非零退出；恢復後可補 mirror，但不得重算或改寫原 evidence。
- FR-40: 大型 evidence stores MUST gitignore；Git 只保存規格、collector code/tests、schema、small manifests、health summaries 與 aggregate hashes。
- FR-41: primary/mirror 的實際絕對路徑與可用空間門檻 MUST 在核准欄填入。任一路徑未核准時不得啟用排程。
- FR-42: 每次成功 run MUST 依 NFR-7 當時適用的 estimate（bootstrap 或 P95 切換後）驗證剩餘空間；所需剩餘空間固定為 `estimate_bytes_per_run × 90 × 2`（90 為排定 run 次數之近似、2 為安全係數）。不足時 fail closed，不得自動刪舊檔。

### 8. Scheduling and operational boundary

- FR-43: Collector MUST 在當日 P-A 與 P-B producers 成功後執行；MUST NOT 主動呼叫、重跑或修復 producers。
- FR-44: Producer 任一缺失時 MUST 產生 `persistence_status = FAILED`、`failure_code` 為 `MISSING_P_A`、`MISSING_P_B` 或 `DATE_MISMATCH`（見 §6a）的 failure receipt，且不得用 cloud/local fallback 混搭成假 common date。
- FR-45: 排程 MUST 使用互斥鎖，防止同日平行 run。互斥鎖規則：
  a. Lock lease 固定為 120 分鐘，不可由 config 或執行參數覆寫。
  b. 一把鎖只有在同時滿足「lock age > 120 分鐘」與「lock 記錄的原 PID 已不存在於系統」兩個條件時，才能被判定為 `STALE`；缺其一律不得標記 stale（PID 仍存活即使已超過 120 分鐘、或 PID 已死但未滿 120 分鐘，皆不算 stale）。
  c. Collector MUST NOT 自動接管或刪除 stale lock；偵測到 stale lock 時只能寫入 `LOCK_STALE_DETECTED` 診斷紀錄並拒絕啟動新 run，等待人工處理。
  d. 人工解除 stale lock MUST 透過明確 CLI 子命令執行（例如 `identity_collector.py unlock --run-id <expected_run_id> --reason <operator_reason>`）；CLI MUST 要求同時提供 expected run-id 與 operator reason，缺一律拒絕執行。
  e. 每次人工解除 MUST 追加一份 `unlock_receipt`（run-id、operator、reason、解除時間 Asia/Taipei + UTC）至 `collector_ledger.jsonl`；不得編輯或刪除原 lock 記錄本身。
- FR-46: Collector failure MUST NOT 阻止既有 production scoring、UI deployment 或 L4a；但不得把 collector failure 隱藏成 success。
- FR-47: 排程安裝、修改、啟用與停用 MUST 分別獲得使用者明確授權；規格核准本身不等於授權變更 Windows Task Scheduler。
- FR-48: Collector MUST 提供 read-only health command，其輸出 MUST 符合固定 schema（見 Data Models `health_summary.json`），至少包含 `last_success_run_id`、`last_success_at`、`last_failure_run_id`、`last_failure_at`、`last_failure_code`（見 §6a receipt taxonomy 的 `failure_code`）、`pending_mirror_count`、`monthly_eligible_count`、`comparable_identity_count`、`source_mutation_count`、`current_lock_state`（`FREE`/`HELD`/`STALE_DETECTED`）與 `current_lock_holder_pid`（nullable）。任一欄位缺漏或型別不符 MUST 視為該次 health command 失敗，不得回傳部分內容當作成功。

### 9. Version epochs

- FR-49: 下列任一變更 MUST 開啟新 `identity_epoch`，不得跨 epoch 直接計算 identity：score formula、weights version、watchlist/build universe policy、c2 formula、ADV/listed rule、rank method、FUSION_PCT、collector schema、R-FWD semantics。
- FR-50: 純 code refactor只有在 parity regression exact match 後 MAY 延續原 epoch；證據與 code hash仍須記錄。
- FR-51: epoch transition MUST 追加 transition receipt，列出 before/after hashes、原因與使用者授權；不得重寫舊 evidence。
- FR-52: 未滿 24 個 monthly comparable dates 的 epoch 不得與其他 epoch 拼接湊足門檻，除非另立並核准 bridging prereg。

---

## Non-Functional Requirements

- NFR-1（零 production side effect）: 除新 evidence roots、small versioned summaries 與經另行核准的排程外，實作 MUST 對 production files/state 為唯讀。
- NFR-2（可重播）: 使用單一 run 的 frozen inputs、code snapshots 與 manifest，離線 replay MUST 產生相同 canonical output hashes。
- NFR-3（決定性）: 同一 run identity 的兩次 dry replay，CSV/Parquet canonicalized content hashes MUST exact match。
- NFR-4（完整性）: 每個成功 run MUST 有 source、code、config、schema、output 與 mirror hashes；缺一即不算成功。
- NFR-5（可靠性）: duplicate key、NaN required score、schema drift、date mismatch、partial copy、hash mismatch MUST fail closed。
- NFR-6（資料安全）: artifacts MUST NOT 包含 API keys、cookies、credentials、broker account data、PositionState 或可執行訂單。
- NFR-7（容量）: 每 run MUST 記錄 bytes/files/elapsed time。容量估計採冷啟動 bootstrap + 動態切換兩階段，MUST NOT 在無估計基準時放行任何容量檢查：
  a. **Bootstrap 量測（Activation 前，Gate C-P 範圍）**：Collector 啟用前 MUST 對現有三個 exact P-B 日期 `2026-08-07`、`2026-08-10`、`2026-08-11` 各完成一次離線 dry-run，量測完整 output bytes；若當時要啟用 `COMPARABLE_IDENTITY` mode，三次 dry-run MUST 包含對應 R-FWD artifacts，僅 P-only 的量測不得替代。`bootstrap_bytes_per_run = ceil(1.5 × 三次 dry-run 中最大的 output bytes)`。三次 dry-run 任一無法完成，Gate C-P MUST FAIL，不得以少於三次的量測頂替。
  b. **前 20 次成功 live runs**：容量估計 MUST 使用 `bootstrap_bytes_per_run`。
  c. **滿 20 次成功 live runs 後**：容量估計 MUST 改用 `max(bootstrap_bytes_per_run, P95(最近 20 個成功 runs 的 bytes))`——即 bootstrap 值作為只降不升的下限，不得因近期 run 變小而低於它。
- NFR-8（可觀測性）: 每次 run MUST 有 machine-readable receipt 與 human-readable one-line status；不得只留 stdout。
- NFR-9（恢復）: primary 或 mirror 單邊遺失後，restore MUST 從另一邊 byte-copy 並逐檔驗 hash；不得重新計算冒充原 evidence。
- NFR-10（相容性）: collector 未啟用或失敗時，現有 `score_store`、`universe_screen_daily.py`、`app.py`、`l4a_decision.py` 行為 MUST bitwise/value-equivalent 不變。

---

## Acceptance Criteria

### AC-1: History timeline complete (FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-8)

Given P-A、P-B、部署鏡像與排程證據已盤點  
When Phase H 報告完成  
Then 每個 source/date range 都有固定 cause code、evidence refs 與 confidence  
And 無證據的原因標為 `UNRESOLVED`，不得推測為刪除。

### AC-2: Diagnosis is non-mutating (FR-7, NFR-1)

Given 診斷前已記錄 protected paths 的 hashes/status  
When Phase H 結束  
Then protected paths 的內容 hashes 不變  
And 沒有建立 backfill、修改排程或清理任何 cache。

### AC-3: Exact-date collection (FR-10, FR-11, FR-43, FR-44)

Given P-A 與 P-B 最新 dates 不同  
When Collector 執行  
Then 產生 `persistence_status = FAILED`、`failure_code = DATE_MISMATCH` 的 failure receipt  
And 不產生成功 evidence、不 nearest-fill、不觸發 producers。

### AC-4: Monthly qualification (FR-12, FR-13, FR-14, FR-15)

Given 某日 snapshot 已成功且後續交易日證實它是當月最後交易日  
When qualification job 執行  
Then append 一份 `MONTHLY_ELIGIBLE` receipt 指向原 snapshot  
And 原 snapshot bytes/hash 不變。

### AC-5: Production source capture (FR-17, FR-18, FR-19, FR-22, FR-23, NFR-4)

Given 同日 P-A/P-B inputs 已 frozen-copy  
When production evidence 建立  
Then raw rows、denominators、rank semantics、Top20 與 fusion 均可由 artifacts 重建  
And source/code/config hashes 全部存在。

### AC-6: App/L4a internal identity (FR-19, FR-20, FR-21)

Given app 與 L4a 使用同一 frozen input copies  
When 計算兩條 fusion path  
Then ticker sets exact match，否則 `identity_status = PRODUCTION_INTERNAL_DIVERGENCE`  
And 無 OrderIntent、PositionState 或 L4b side effect。

### AC-7: Research forward parity (FR-24, FR-25, FR-26, FR-27, FR-30)

Given frozen research 255 月 baseline  
When R-FWD adapter parity suite 執行  
Then 255 個月 final membership exact match  
And common raw scores 在 `1e-12` tolerance 內 value-equivalent  
And R-FWD 與 production evidence 擷取分別在隔離 process 執行、process import 清單不重疊，擷取 production evidence 的 process 未載入 `beat_0050.realbody.bt_bundle`（FR-24）  
And 任一失敗使 collector 保持 `P_ONLY_EVIDENCE`。

### AC-8: No future leakage (FR-28, NFR-6)

Given 一個 forward decision date  
When R-FWD evidence 建立  
Then process file-access manifest 不含 `exec_ret` 或 decision date 後資料  
And 測試注入未來資料不會改變輸出。

### AC-9: Idempotent and mutation-safe (FR-31, FR-32, FR-33, FR-35)

Given 同一 run identity 已存在  
When 相同 inputs 重跑  
Then 回傳既有 receipt 且不新增 evidence  
And 同日不同 bytes 會建立新 run（`source_mutation = TRUE`、`revision_of` 指向舊 run_id），舊 revision 的 receipt 與 bytes 不變。

### AC-10: Atomic failure (FR-34, NFR-5)

Given 寫入中途被中斷或 schema/hash 驗證失敗  
When run 結束  
Then 沒有成功標記的半套 evidence  
And failure receipt 的 `persistence_status = FAILED`、`failure_code` 明列具體原因（見 §6a），並記錄 temp cleanup 狀態。

### AC-11: Dual-copy durability (FR-37, FR-38, FR-39, FR-41, FR-42, NFR-9)

Given primary 與 mirror roots 已由使用者核准  
When 一個 run 完成  
Then 兩邊逐檔與 aggregate hash一致後才標記 `persistence_status = COMMITTED`  
And mirror 失敗時 `persistence_status = PENDING_MIRROR`、非零退出且不刪 primary。

### AC-12: Retention and Git scope (FR-36, FR-40)

Given evidence 已保存  
When 執行 Git staging dry-run 或 cleanup simulation  
Then 大型 evidence未被 staged、舊 evidence未被刪除  
And small manifests/health summaries仍可版本控制。

### AC-13: Epoch isolation (FR-49, FR-50, FR-51, FR-52)

Given 任一 identity-defining input/version 發生變更  
When 下一次 Collector 執行  
Then 開啟新 epoch或在 parity exact match 後明文延續  
And 不跨 epoch 拼接 24 個 monthly dates。

### AC-14: R1 reopening threshold (FR-16, FR-29, FR-30)

Given collector 已累積 observations  
When 計算 eligibility  
Then 只有同一 epoch 內 24 個 `MONTHLY_ELIGIBLE` 且 R-FWD/P-A/P-B 完整日期才標記 `R1_REOPEN_ELIGIBLE`  
And P-only、daily、missing-R 或跨 epoch 日期不計入。

### AC-15: Existing behavior unchanged (FR-46, NFR-10)

Given collector 被停用或故意失敗  
When 執行既有 production regression suite  
Then scores、universe outputs、UI targets 與 L4a targets 保持既有結果  
And collector failure 有獨立非成功狀態但不阻斷 production。

### AC-16: Scheduling lock, authorization and health (FR-45, FR-47, FR-48, NFR-8)

Given 尚未取得 Task Scheduler 的另行明確授權  
When implementation 與 dry run 完成  
Then 不得安裝、修改、啟用或停用任何排程  
And 兩個同日 collector processes 競爭時只能一個取得互斥鎖，敗者 MUST 立即以非零退出結束、不得等待或重試搶鎖  
And 一把 lock 只有在「age > 120 分鐘」且「原 PID 已不存在」同時成立時才可標記 `STALE`，collector MUST NOT 自動接管或刪除該 lock；人工解除 MUST 透過帶 `--run-id`/`--reason` 的明確 CLI 並留下 `unlock_receipt`  
And read-only health command 的輸出 MUST 符合 `health_summary.json` 固定 schema，機械回報 last success、last failure（含 failure_code）、pending mirror、monthly eligible、comparable identity 與 source mutation 計數；缺欄位或型別不符即視為該次 health command 失敗。

---

## Edge Cases

- EC-1: P-A 有同日 rows，但不同股票的 latest `as_of` 不一致 → run fail，不能以多數日期代表整體。
- EC-2: P-B 檔名日期與內容日期不同 → `SOURCE_DATE_CONFLICT`，不得收集。
- EC-3: 同一 `(as_of, stock_id, mode)` 重複 → abort，不得 keep-last 後隱藏問題。
- EC-4: Collector 在 P-A 寫入尚未完成時讀取 → 來源 hash 前後不一致，retry 只能重新開始 frozen copy。
- EC-5: 月底遇休市或颱風假 → 以核准的市場交易日曆判定，不以自然月最後一天判定。
- EC-6: 下一交易日資料遲到，月底資格未能確認 → 保持 `QUALIFICATION_PENDING`，不得猜測。
- EC-7: P-app/P-L4a 任一函式需 import Streamlit side effect → 必須先抽取純函式並通過 parity；若會改 public behavior，停止修訂規格。
- EC-8: R-FWD 某日期 PIT input 不足 → `R_FWD_UNAVAILABLE`，保留 P evidence但不列 comparable。
- EC-9: primary 成功、mirror hash mismatch → run 非 `COMMITTED`，保留雙方供調查，不自動覆蓋。
- EC-10: 磁碟不足 → fail closed，禁止自動 prune。
- EC-11: 同日 producer重跑改變 source bytes → 新 revision + mutation alert，不覆蓋先前 evidence。
- EC-12: collector code更新但 semantics相同 → 必須先跑 parity；沒有證據即新 epoch。
- EC-13: daylight/timezone 差異 → receipts一律同時保存 Asia/Taipei local time 與 UTC。
- EC-14: mirror root與primary經 resolved path 或 filesystem identity判定相同 → Activation Gate FAIL。
- EC-15: history gap log不存在 → `NOT_AVAILABLE`，不得以 log 缺失證明從未產生。

---

## API Contracts

本案沒有 HTTP API。API Contracts：**N/A — 離線 collector 與 CLI。** `GET /identity-collector/*` 為明確禁止的介面，MUST NOT 實作；此處不是 endpoint 定義，而是負面契約。CLI contract如下：

```text
python scripts/identity_collector.py diagnose-history --config <path>
python scripts/identity_collector.py collect --as-of YYYY-MM-DD --config <path>
python scripts/identity_collector.py qualify-month --month YYYY-MM --config <path>
python scripts/identity_collector.py replay --run-id <id> --offline
python scripts/identity_collector.py health --config <path>
```

所有 mutating collector commands MUST 支援 `--dry-run`；`diagnose-history`、`replay`、`health` 對 production sources永遠唯讀。

---

## Data Models

### `run_receipt.json`

| Field | Type | Constraints |
|---|---|---|
| schema_version | string | required |
| run_id | string | immutable, unique |
| as_of | date | exact source date |
| identity_epoch | string | required |
| collector_version | string | code/config hash derived |
| persistence_status | enum | `COMMITTED` / `PENDING_MIRROR` / `FAILED`（見 §6a receipt taxonomy） |
| identity_status | enum | `P_ONLY_EVIDENCE` / `COMPARABLE_IDENTITY` / `PRODUCTION_INTERNAL_DIVERGENCE` / `R_FWD_UNAVAILABLE`（見 §6a） |
| monthly_status | enum | `DAILY_DIAGNOSTIC` / `QUALIFICATION_PENDING` / `MONTHLY_ELIGIBLE`（見 §6a） |
| failure_code | enum/null | `persistence_status == FAILED` 時必填，見 §6a；否則 null |
| source_mutation | boolean | `TRUE` 時 `revision_of` 必填 |
| revision_of | string/null | 指向被取代 run 的 `run_id`；僅 `source_mutation == TRUE` 時非 null |
| started_at_utc | datetime | immutable |
| completed_at_utc | datetime/NA | required for terminal states |
| source_hashes | object | P-A/P-B/R-FWD hashes |
| output_hashes | object | per artifact + aggregate |
| primary_root | string | approved resolved path |
| mirror_root | string | approved resolved path |

### `collector_ledger.jsonl`

| Field | Type | Constraints |
|---|---|---|
| sequence | integer | strictly increasing |
| event_type | enum | run/qualification/revision/epoch/failure/mirror |
| run_id | string | references receipt |
| prior_event_hash | string | hash-chain; null only first record |
| event_hash | string | canonical record hash |
| payload | object | immutable event data |

### `health_summary.json`

| Field | Type | Constraints |
|---|---|---|
| schema_version | string | required |
| generated_at_utc | datetime | required |
| last_success_run_id | string/null | null 表示尚無成功 run |
| last_success_at_utc | datetime/null | required with last_success_run_id |
| last_failure_run_id | string/null | null 表示尚無失敗 run |
| last_failure_at_utc | datetime/null | required with last_failure_run_id |
| last_failure_code | enum/null | 見 §6a receipt taxonomy `failure_code` |
| pending_mirror_count | integer | >= 0 |
| monthly_eligible_count | integer | >= 0，同一 epoch 內計數 |
| comparable_identity_count | integer | >= 0 |
| source_mutation_count | integer | >= 0 |
| current_lock_state | enum | `FREE` / `HELD` / `STALE_DETECTED` |
| current_lock_holder_pid | integer/null | 僅 `HELD` 時非 null |

### Per-run artifacts

```text
<evidence_root>/<identity_epoch>/<as_of>/<run_id>/
    run_receipt.json
    source_manifest.json
    code_config_manifest.json
    p_a_scores.parquet
    p_b_fullpool.parquet
    p_app_fusion.csv
    p_l4a_fusion.csv
    r_fwd_scores.parquet          # only when available
    r_fwd_fusion.csv              # only when available
    rank_audit.csv
    process_import_manifest.json
    replay_manifest.json
```

### Versioned small artifacts

```text
research/p0_r2_identity_collector/
    prereg.md
    approval_receipt.json
    history_gap_timeline.csv
    history_gap_findings.json
    history_gap_report.md
    collector_schema.json
    activation_manifest.json
    health_summary.json
    report.md
```

---

## 10. Gates and decisions

### Gate H-D — History diagnosis validity

PASS requires：固定 cause taxonomy、evidence refs、protected inputs unchanged、所有未知明列。  
FAIL 時不得用推測原因設計修復，但可繼續設計不依賴根因的 forward collector。

### Gate C-P — Collector preflight

PASS requires：spec approved、primary/mirror roots approved且獨立、容量足夠（NFR-7 三次 bootstrap dry-run 皆已完成且 `bootstrap_bytes_per_run` 已量得；三次 dry-run 未全部完成視為容量條件未滿足）、schemas/config/hashes frozen、protected paths與schedule scope明確。  
FAIL 時不得寫 collector code或改排程。

### Gate C-R — Research-forward parity

PASS requires：255 月 final membership exact match、raw-score tolerance checks pass、無 future-return access、process isolation pass。  
FAIL 時 collector最多只能以 `P_ONLY_EVIDENCE` 啟用；不得稱為 forward identity collector completed。

### Gate C-S — Synthetic / regression safety

PASS requires：AC-3 至 AC-13 的 synthetic/regression tests 全過，現有 production outputs unchanged。  
FAIL 時不得啟用真實排程。

### Gate C-A — Activation

PASS requires：C-P PASS、C-S PASS、使用者另行明確授權 schedule install/enable、且 `active_cleanup_or_pruning_affecting_evidence_roots == FALSE`（FR-9）；若要 `COMPARABLE_IDENTITY` mode，另需 C-R PASS。  
`active_cleanup_or_pruning_affecting_evidence_roots` 為 `TRUE` 或因證據不足只能標為 `UNKNOWN` 時，Gate C-A MUST FAIL，即使 C-P/C-S/C-R 各自 PASS。本條只要求「collector 預定 evidence roots 不受已知/可預期清理政策威脅」這一項判定明確為 `FALSE`，不要求整個 Gate H-D PASS——Phase H 對 P-A/P-B 其餘根因（如仍有 `UNRESOLVED`）若與 collector 未來 evidence roots 無關，不影響本條。  
Activation 後第一筆有效日期即鎖定 epoch start；不得回填更早日期。

### Gate C-24 — R1 reopening eligibility

同一 epoch 累積 24 個合格 monthly comparable dates才 PASS。PASS 只代表可以另立新版 R1，不代表 identity 本身 PASS。

---

## 11. Test requirements

至少建立：

```text
test_history_gap_requires_evidence_for_deleted
test_history_diagnosis_does_not_mutate_sources
test_exact_date_only_no_nearest_fill
test_daily_not_counted_as_monthly
test_month_end_qualification_is_append_only
test_pa_snapshot_captures_full_native_universe
test_pb_snapshot_captures_fullpool_and_metadata
test_app_l4a_same_frozen_inputs_exact_set
test_no_orderintent_positionstate_or_l4b_access
test_r_fwd_255_month_membership_parity
test_r_fwd_raw_score_tolerance
test_r_fwd_cannot_read_exec_ret_or_future_inputs
test_identical_run_is_idempotent
test_same_date_changed_source_creates_revision
test_partial_write_never_committed
test_ledger_hash_chain
test_primary_mirror_must_be_independent
test_commit_requires_two_verified_copies
test_low_disk_never_prunes
test_capacity_bootstrap_requires_three_dry_runs
test_capacity_uses_bootstrap_for_first_20_runs
test_capacity_switches_to_p95_floor_after_20_runs
test_concurrent_run_single_mutex_winner
test_live_pid_never_treated_as_stale
test_dead_pid_before_120_minutes_not_stale
test_stale_lock_requires_manual_unlock_receipt
test_health_command_schema_and_counts
test_epoch_change_on_identity_definition_change
test_no_cross_epoch_month_counting
test_collector_failure_does_not_change_production_outputs
```

所有 tests 在 implementation 前由核准規格產生；不得先寫 collector再補 spec。

---

## 12. Execution protocol

### Phase A — Approval

核准分兩個 stage，見 §15 說明：

**Stage 1**（開放 Phase H + 離線 tests/implementation）只需填妥 §15 中 User approval、Approved scope、Approved repository baseline commit、Approved draft SHA256 四項並將 Status 改為 `APPROVED`。此四項填妥、Status 改為 `APPROVED` 前，不得執行 Phase H、寫 tests/code、建立 evidence roots或更動排程。

**Stage 2**（開放 live writes/R-FWD forward collection/排程）待 Gate C-P/C-R/C-S 結果揭露後，須另行核准 §15 其餘六項（Primary/Mirror evidence root、R-FWD forward/live collection authorized、Collector live writes authorized、Task Scheduler install/modify authorized、Production calculation/state writes authorized）才可推進 Phase E 之後的啟用動作；Stage 1 核准時這六項維持 `PENDING`/`NO`，不構成 Stage 1 核准或 Phase H/離線 tests 的阻塞條件。「R-FWD forward/live collection authorized」只管制 Phase F 的 forward/live 蒐集；R-FWD parity adapter 本身的離線實作與測試（Phase B/C/D，僅用 synthetic 與 frozen R1/P0-U1 snapshots）屬於 Stage 1 授權範圍。

### Phase H — Read-only diagnosis

只蒐集 timeline/evidence並產出根因分類。不修復、不backfill。

### Phase B — Collector design freeze

凍結：source callables、schema、rank semantics、R-FWD adapter、storage roots、capacity、epoch identity、collector config與 code hashes。

R-FWD adapter 的 parity oracle MUST 明定為：

```text
beat_0050.strategies.high52_lab.Panel
dual_confirm_mask(P, "100萬", top_pct=20, source="real", canonical=False)
```

由 `dual100_lab.py` 的 frozen baseline constants（`ADV_TIERS` 中 `"100萬"` 對應的門檻、`TOP_PCT`、`COV_MIN` 等）與對應 code hashes（`beat_0050/strategies/high52_lab.py`、`beat_0050/strategies/dual100_lab.py`、`core/canonical_universe.py`、`scripts/lab_paths.py` 的 sha256）固定，記錄格式比照 P0-R1 `preflight.json.resolved_callables`。此 oracle 只作為 R-FWD adapter 的 parity 對照基準，**不代表**把 frozen research 用的 `Panel`/`dual_confirm_mask` 直接當成 forward-looking evaluator 使用——R-FWD 仍須依 FR-28 只用 decision time 當下可取得的 PIT inputs 重新計算；parity suite 只驗證兩者在歷史重疊月份上的語意等價。

### Phase C — Tests and implementation

先生成 failing tests，再做最小實作。不得更動 production calculation semantics。

### Phase D — Dry run and parity

只用 synthetic與 frozen R1/P0-U1 snapshots。不得寫 live evidence roots或改排程。

### Phase E — Activation approval

回報 Gate H-D/C-P/C-R/C-S。使用者另行核准排程與兩個 storage roots後才可啟用。

### Phase F — Forward collection

只向前蒐集。每次run按 append-only、dual-copy、receipt流程執行。

### Phase G — Periodic health

每月只更新health summary；6/12月可出 diagnostic，24月後只發出 `R1_REOPEN_ELIGIBLE`，不得自動執行R1。

---

## Out of Scope

- OS-1: 回算或補造 2026-07 前 P-A/P-B history。
- OS-2: 從 research panel 反推 production snapshots。
- OS-3: 修改 Scores dedup、score formula、weights或build universe。
- OS-4: 修改 c2 formula、ADV floor、listed rule或fullpool selection。
- OS-5: 修改 app/L4a fusion、FUSION_PCT、TOP_N、portfolio construction。
- OS-6: 寫入 OrderIntent、PositionState、L4b或broker。
- OS-7: DataExport0806 migration或寫入 `tej_cache`。
- OS-8: 自動刪除舊 evidence、壓縮歷史或 retention optimization。
- OS-9: 用daily observations提前重開R1。
- OS-10: 以 collector evidence做績效、未來報酬或alpha研究。
- OS-11: 規格核准即自動修改Windows Task Scheduler。
- OS-12: 將大型 evidence提交Git或推送部署分支。

---

## 13. Final report template

```text
# P0-R2 History Gap / Forward Identity Collector Result

## 0. Scope and non-claims
## 1. Preregistration integrity
## 2. History-gap evidence timeline
## 3. Cause adjudication by source
## 4. Collector architecture and protected boundaries
## 5. R-FWD parity results
## 6. Synthetic/regression results
## 7. Storage durability and capacity
## 8. Scheduling authorization status
## 9. Gates H-D / C-P / C-R / C-S / C-A
## 10. Activation epoch and first eligible date
## 11. Limitations
## 12. Decision and next action
```

---

## 14. Mandatory instruction to implementation agent

> 本任務先診斷 production 歷史保存缺口，再建立只向前累積的 identity evidence collector。不得回填、不得用回算資料冒充 contemporaneous production evidence、不得更改任何策略或 production 計算語意。Collector 只能讀已成功產生且 exact-date 相同的 P-A/P-B inputs；缺資料時寫 failure receipt，不得自行重跑 producer。R-FWD 必須先對 255 月 frozen research baseline 通過 parity，否則只能保存 P-only evidence。所有 evidence append-only、同日來源變更另開 revision、primary與mirror雙副本驗 hash後才算成功。規格核准不等於排程授權；更動 Task Scheduler 前必須再次取得使用者明確核准。

---

## 15. Approval fields

核准分兩個 stage，兩者獨立生效：

```text
--- Stage 1（Phase H + 離線 tests/implementation 授權 — APPROVED 2026-08-13）---
User approval: APPROVED
Approved scope:
  1. Phase H 唯讀歷史缺口診斷（history gap diagnosis, read-only）
  2. 離線 tests（Phase C failing-tests-first）
  3. Collector 離線實作與 dry-run（Phase C 最小實作 + Phase D synthetic/frozen-snapshot dry run；不建立 live evidence roots、不寫排程）
  4. R-FWD parity adapter 的離線實作與測試（Phase B/C 的 adapter 程式碼與 parity suite，僅限離線；R-FWD forward/live collection 仍屬 Stage 2）
  不含：Primary/Mirror evidence roots 建立、R-FWD forward/live collection、Task Scheduler 安裝/修改、任何 production 計算或狀態寫入（見下方 Stage 2）。
Approved repository baseline commit: 0337af0c
Approved draft SHA256: f609b12fb7410cc1123ac8bc35976aeac0102c92212d636c0ae4da20707f92d4（此為使用者實質核准時審閱的 pre-stamp 版本雜湊，非本文件蓋章後的最終雜湊——見下方說明）

--- Stage 2（live evidence roots / R-FWD forward/live collection / Task Scheduler / production 授權，待 Gate C-P/C-R/C-S 結果揭露後另行核准 — 尚未核准）---
Primary evidence root (absolute path): PENDING（延後 Stage 2，不阻塞 Stage 1）
Mirror evidence root (absolute path): PENDING（延後 Stage 2，不阻塞 Stage 1）
R-FWD forward/live collection authorized: NO
Collector live writes authorized: NO
Task Scheduler install/modify authorized: NO
Production calculation/state writes authorized: NO
```

兩階段規則：

1. **Stage 1**（已核准，2026-08-13）只需要「User approval / Approved scope / Approved repository baseline commit / Approved draft SHA256」四項有值、Status 改為 `APPROVED`，即可授權 Phase H（唯讀診斷）與 Phase C 的離線 tests/implementation（含 R-FWD parity adapter 的離線實作與測試）；Stage 2 六項欄位維持 `PENDING`/`NO` 不構成 Stage 1 的阻塞條件，也不因 Stage 1 核准而自動變更。
2. **Stage 2** 的 live evidence roots、R-FWD forward/live collection 及 Task Scheduler 安裝/修改，必須在 Gate C-P/C-R/C-S 結果揭露後另行核准，且各自獨立生效（例如 Primary/Mirror root 核准不代表 Task Scheduler 已授權）。完成 Phase H 及離線 tests/implementation 後，MUST 先揭露 Gate H-D、C-P、C-R、C-S，再由使用者另行決定 Stage 2。

「Approved draft SHA256」記錄的是使用者核准當下審閱的 pre-stamp 草稿雜湊（`f609b12f...`），這是一個固定、非自我指涉的既有值，可安全寫入本文件。但本文件經本次蓋章（Status/User approval 等欄位）後產生的**最終文件自身雜湊**不得自我寫回——寫入當下無法預先知道蓋章後的雜湊值，強行寫入會造成自我指涉的無限迴圈。該最終雜湊與對應 Git blob/commit 一律只記錄於核准後的外部 `research/p0_r2_identity_collector/approval_receipt.json`，不在本文件內出現。
