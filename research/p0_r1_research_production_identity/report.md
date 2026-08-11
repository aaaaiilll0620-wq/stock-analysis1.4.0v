# P0-R1 Research / Production Identity Result

**狀態：Phase B（唯讀 preflight）結果，Phase C–F 未執行。**

**Result: `NO_COMPARABLE_DATES / INSUFFICIENT_HISTORY`**（2026-08-12 使用者結案修正後定稿）

**Gate R1-P: FAIL**　Gate R1-I / R1-A / R1-R: **NOT EVALUATED**

本結果**不宣稱** null identity、**不宣稱** research 與 production identity 相同、**不宣稱**任何差異已完成歸因。在目前凍結的輸入下，兩條路徑之間沒有任何共同決策日期可供比對，因此不存在可供下任何「相同」或「不同」判斷的比對列——這是「無法比較」，不是「比較後發現一致」。

## 0. Scope and non-claims

本報告只涵蓋 prereg §12 Execution protocol 的 Phase B（唯讀 preflight）。不涉及績效、未來報酬、production state 修改。不裁決 research 或 production 何者應為 Champion。Phase C（unit/synthetic validation）、Phase D（freeze）、Phase E（full identity reveal）、Phase F（replay）均未執行。

## 1. Preregistration integrity

- Prereg：`docs/prereg_P0_R1_ResearchProductionIdentity_2026-08-12.md`，Status = APPROVED（2026-08-12 使用者核准）。
- Approved draft SHA256：`18fbd7f37735166c8bb0e5835b440b99e0686edaaf7aa9d5047e54334298be69`
- 核准後依 §3.2.1 走過一次勘誤（E1）：§3.2 fusion path 2 由 `load_dual100_targets` 更正為實際存在的 `scripts/l4a_decision.py::compute_target_list`，使用者已核准。
- 核准與勘誤記錄見 `approval_receipt.json`（未寫回 prereg 文件自身的最終文件 identity，改記錄 git blob：`974e71c5a0e7f6351bbd5f454b1e9d3b5ffdf557`）。

## 2. Input and date inventory

| | 來源 | 筆數 | 範圍 | 頻率 |
|---|---|---|---|---|
| R | `high52_lab.Panel(realbody_floor=1e6)` | 255 個月 | 2005-01-31 ~ 2026-03-31 | 月頻（月底） |
| P-A | `score_store.as_of_dates("balanced")` | 24 天 | 2026-07-08 ~ 2026-08-11 | 日頻快照 |
| P-B | `outputs/universe_pool/c2_fullpool_*.csv` | 3 天 | 2026-08-07 ~ 2026-08-11 | 日頻快照 |

`comparable_dates`（FR-2 三方完整日期交集）= **0**。

缺月標記（FR-3）：R 的全部 255 個月皆為 `MISSING_P_A` 且 `MISSING_P_B`；P-A 的 24 天、P-B 的 3 天皆為 `MISSING_R`。

完整路徑、SHA256、git 狀態（tracked-clean / tracked-modified / untracked）與快照紀錄見 `preflight.json`、`scores_cache_blob_manifest.csv`。

## 3–8. D0–D5 逐層對帳

**未執行。** `comparable_dates` 為空集合，無任何 `(date, ticker)` 可供 D0（decision clock）以下各層對帳。

## 9. First-divergence attribution

不適用——無比對列可供歸因。

## 10. Production app vs L4a identity

不適用——本輪未凍結任何共同輸入日期，AC-6/Gate R1-I 無法在本次執行中檢驗。

## 11. Gate results

| Gate | 結果 |
|---|---|
| R1-P（Preflight validity） | **FAIL**——preflight checklist 上的個別項目（路徑、hash、污染、寫入、正規化）逐項可打勾，但 Gate R1-P 存在的目的是授權進入完整對帳（prereg §11：「否則 R1-P FAIL，不得進完整對帳」）；`comparable_dates = 0` 使這個目的無法達成，故整體宣告 FAIL，不以「機械打勾」名義迴避 |
| R1-I（Production internal identity） | **NOT EVALUATED**（無共同輸入可測，非「通過」也非「失敗」） |
| R1-A（Attribution completeness） | **NOT EVALUATED**（無差異列可歸因） |
| R1-R（Reproducibility） | **NOT EVALUATED**（Phase F 未跑） |

## 12. Limitations

- `score_store`／`c2_fullpool_*.csv` 為何只有約 1 個月歷史（2026-07-08 起 / 2026-08-07 起）未被調查——這超出 R1「唯讀身份稽核」範圍，依 §Out of Scope 精神不在本研究內處理。
- FR-34/35：全部 979 個資料輸入檔（4 份研究 parquet、3 份 c2_fullpool CSV、972 檔 `~/finmind_cache/Scores/*.parquet`）已有唯讀、非 hard-link 的獨立複本存於 gitignored 的 `data_snapshot/`（不進 commit，manifest 見 `data_snapshot_manifest.json`），逐檔已重新雜湊核對與原記錄一致（0 mismatch）。第一輪的 `git hash-object -w` blob 仍留在 `.git/objects`，但已明文標註為非長期保存手段（unreferenced loose object 可被 `git gc` 清除），以 `data_snapshot/` 為準。AC-2 要求的完整隔離 process runtime module manifest 檢查仍未執行（僅靜態 grep）。
- 本次未涵蓋 `conservative`／`aggressive` 模式的完整比對，僅記錄其 `as_of_dates` 供對照（見 preflight.json）。

## 13. Decision

**Result: `NO_COMPARABLE_DATES / INSUFFICIENT_HISTORY`**

**Gate R1-P: FAIL**　**Gate R1-I: NOT EVALUATED**　**Gate R1-A: NOT EVALUATED**　**Gate R1-R: NOT EVALUATED**

在目前凍結的輸入下，研究與 production 之間沒有任何共同決策日期可供 D0–D5 identity 比對——`comparable_dates`（FR-2 三方交集）= 0。R 的研究基準線止於 2026-03-31，production 的兩個母體（score_store、c2_fullpool）現有資料只從 2026-07 / 2026-08 才開始，兩者在任何粒度下都沒有重疊，遠低於 FR-6 的 24 個月門檻（EC-10 `INSUFFICIENT_HISTORY`）。

**本結果明確不宣稱以下任何一項**：
- 不宣稱 null identity（沒有測到「一致」，因為根本沒有比對發生）；
- 不宣稱 research 與 production identity 相同或不同（無比對列，無法對「相同/不同」做出任何判斷）；
- 不宣稱任何差異已完成歸因（沒有差異列可歸因，`explained_rate` 未定義，AC-7/AC-8 未評估）。

依 §13 Invalid runs 規則，這不構成 invalid run（不是資料中途變動、不是 schema 失敗、不是 process 污染）。但也不比照 Case D（「R 與 P 已 identical」）處理——Case D 的前提是走完比對後發現一致，本次是根本無法比對。這是一個獨立於 §11 四個 Case 之外的結構性阻斷結果：preflight 有效但比對母體為空，Gate R1-P 因此 FAIL，不得進完整對帳。不得為了產生工作量而修改任何路徑、放寬比對單位或延伸母體。

## 14. Next action

未經使用者核准前不自動進行。可能方向（僅供使用者選擇，非本報告建議採納順序）：

1. 另立範圍外任務調查 `score_store`／`c2_fullpool_*.csv` 歷史深度不足的原因（是否曾有更長歷史、是否為新機制）。
2. 待歷史資料條件改變後（例如 production 累積更多月頻快照）重跑本 prereg 的 Phase B 起。
3. 維持現狀，不再推進 R1。
