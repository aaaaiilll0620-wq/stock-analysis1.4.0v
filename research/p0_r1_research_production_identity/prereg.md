# P0-R1 Research / Production Identity 預註冊規格

**文件名稱：** `docs/prereg_P0_R1_ResearchProductionIdentity_2026-08-12.md`  
**研究代號：** `P0-R1`  
**研究名稱：** Research / Production Identity Audit  
**Author:** Codex（依使用者指示起草）  
**Date:** 2026-08-12  
**Status:** APPROVED / 已經使用者核准，scope 限 §17 記載範圍；Phase C 起仍需逐階段確認  
**前置研究：** `P0-U1`，commit `5f3f5d31`  
**相關文件：** `docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md`、`research/p0_u1_canonical_universe/report.md`、`docs/預註冊_Live設定驗證.md`  
**研究類型：** 唯讀結構稽核與差異歸因；不是策略修改、績效優化或 production migration

---

## Context

P0-U1 已證實，研究 H1–H5 引擎內 A、B 兩腿的 ranking universe 原本已近乎一致：255 個決策月的共同分母 assertion 全過，只有約 0.21% stock-month 的 B 腿缺值差異；baseline 與 U1 月度持股 Jaccard 中位數為 1.0，H1–H5 判定完全不變。因此，P0-U1 沒有解決其背景文字原先指出的 production 問題。

production 的正式月頻候選路徑目前概念上為：

```text
score_store.screen_by_composite_at(as_of)
    → A：production real_composite ranking

c2_fullpool_{as_of}.csv
    → B：production c2_score_full ranking

A Top20% ∩ B Top20%
    → app.py / scripts/l4a_decision.py 候選名單
```

研究 H1–H5 路徑則概念上為：

```text
high52_lab.Panel
    → tier_valid[ADV≥1,000,000]
    → research real_composite
    → research c2 四腳
    → dual_confirm_mask
```

已知證據包括：

- production/live 設定與研究設定的四日期診斷，dual100 名單 Jaccard 中位數曾為 0.640；
- live 設定其後已獨立通過既有 H1–H4，故低 Jaccard 本身不是「live 策略未經驗證」的證據；
- c2 fullpool 已改為輸出 ADV≥100 萬、無 L0/L2 的附加檔案，但 A 腿仍可能受 `score_store` 歷史、建置 symbols、`watchlist.txt`、共同日期及排名分母影響；
- 估值窗與籌碼來源差異已有已知診斷與 live-config 獨立驗證，不應在 R1 被偷偷修正；
- `app.py` 與 `scripts/l4a_decision.py` 各自含融合邏輯，仍需證明同輸入時結果一致。

R1 的目的不是先選定哪一條路徑「正確」，而是建立可重播的身份對帳，回答：

> 在相同決策日期下，研究與 production 從輸入母體到 L4a 候選 handoff，第一個差異出現在哪一層？每一層造成多少股票進出？所有差異能否被明確歸因？

---

## 2. 核心研究問題與裁決邊界

### 2.1 唯一研究問題

> 對所有可合法比較的共同決策月，研究 H1–H5 路徑與 production 候選路徑在 decision clock、universe、raw scores、percentile ranks、fusion membership 與 L4a handoff 上的 identity 程度及差異來源為何？

### 2.2 本研究的裁決

R1 只裁決：

1. 比較是否有效、可重播且未被共同 process 狀態污染；
2. 每一層是否 identical；
3. 非 identical 的差異是否 100% 被已命名原因覆蓋；
4. 哪一層是每個 `(date, ticker)` 的 first divergence；
5. production 的 `app.py` 與 `l4a_decision.py` 在相同凍結輸入下是否輸出相同候選集合。

R1 不裁決：

- research 或 production 哪一個應成為新 Champion；
- watchlist 是否應刪除或擴充；
- 估值窗應採 2004 或 2019；
- 籌碼應採 net flow 或 gross participation；
- 是否應部署 canonical universe；
- 是否應修改 ADV、權重、FUSION_PCT、TOP_N、成本或 L4a/L4b；
- 哪個版本績效較好。

---

## 3. Frozen identities / 比較對象

### 3.1 Research identity（R）

Research identity MUST 為 commit `5f3f5d31` 可重建的 frozen dual100 baseline，且 `canonical=False`：

```text
engine         = high52_lab.Panel + dual_confirm_mask
tier           = ADV20 >= 1,000,000 NTD and listed_ok
A raw score     = research real_composite
B raw score     = frozen research c2 formula
A threshold     = Top20%
B threshold     = Top20%
fusion          = A ∩ B
TOP_N           = None
frequency       = monthly
```

### 3.2 Production identity（P）

Production identity MUST 為凍結日實際候選管線，而非用文件描述重建的近似：

```text
A source        = score_store.screen_by_composite_at(as_of, mode="balanced")
B source        = c2_fullpool_{as_of}.csv
fusion path 1   = app.py 的雙確認精選邏輯
fusion path 2   = scripts/l4a_decision.py::compute_target_list(as_of, mode="balanced", fusion_pct=FUSION_PCT, top_n=TOP_N)
FUSION_PCT      = 20
TOP_N           = None
```

若 production 的實際 callable 與上述名稱不同，實作者 MUST 先提出 prereg 勘誤，經使用者核准後才能繼續；不得靜默改用近似函式。

`5f3f5d31` 僅為 repository baseline commit，MUST NOT 被視為單獨代表上述 production identity 在凍結當下的實際狀態；精確路徑、hash 與快照要求見 FR-33–FR-36。

#### 3.2.1 勘誤記錄（Errata）

| # | 日期 | 原文 | 修正後 | 依據 | 使用者核准 |
|---|---|---|---|---|---|
| E1 | 2026-08-12 | `fusion path 2 = scripts/l4a_decision.py::load_dual100_targets` | `fusion path 2 = scripts/l4a_decision.py::compute_target_list` | Phase B preflight 掃描 `scripts/l4a_decision.py` 未發現 `load_dual100_targets`；實際函式為 `compute_target_list(as_of, mode="balanced", fusion_pct=FUSION_PCT, top_n=TOP_N)`（該檔第 120 行），docstring 自陳「公式與資料源逐字相同」於 `app.py` 雙確認精選，讀取同一 `screen_by_composite_at` + `c2_fullpool_{as_of}.csv` + `FUSION_PCT=20` 交集邏輯 | 已核准（聊天記錄 2026-08-12） |

### 3.3 Live-config identity（L，參考層）

`liveconfig_scores_adv100w.parquet` MAY 作為 raw-score 設定歸因的參考層，但 MUST NOT 被冒充為 production score_store 的實際歷史輸出。L 只用來區分：

```text
score-definition difference
vs
score-store coverage / build-symbol difference
```

---

## Functional Requirements

### Frozen decision clock 與可比較月份

- FR-1: 系統 MUST 先列出 R、P-A、P-B 各自可用的 decision dates，不得先取交集後隱藏缺月。
- FR-2: `comparable_dates` MUST 定義為 R、P-A、P-B 都有完整凍結輸入的日期交集。
- FR-3: 缺月 MUST 逐月標記來源：`MISSING_R`、`MISSING_P_A`、`MISSING_P_B` 或複合狀態。
- FR-4: 主報告 MUST 同時回報 `n_dates_R`、`n_dates_P_A`、`n_dates_P_B`、`n_comparable_dates` 與日期範圍。
- FR-5: 不得把當日、日頻或非正式 rebalance date 混入月頻身份比較。
- FR-6: 若共同完整月份少於 24 個，R1 MUST 標記 `INSUFFICIENT_HISTORY`；仍可輸出診斷，但不得對長期 identity 作概括結論。

---

### Production 程式與輸入快照完整性（baseline 與實際比較對象的區分）

- FR-33: `5f3f5d31` MUST 僅視為 repository baseline commit，不得單獨代表 production identity（`score_store` 讀取路徑、`c2_fullpool_*.csv`、`app.py`、`scripts/l4a_decision.py` 及其 import 之模組）在凍結當下的實際狀態。
- FR-34: R1 freeze MUST 為所有被比較之 production 程式與輸入記錄：精確檔案路徑、SHA256，以及該路徑於執行當下相對 git 的狀態（`tracked-clean` / `tracked-modified` / `untracked`）。
- FR-35: 任一被比較的必要程式或輸入檔，其內容不屬於 commit `5f3f5d31`（即 `tracked-modified` 或 `untracked`）時，R1 freeze MUST 另外保存該檔案的唯讀 source snapshot（複本）或建立對應 Git blob（例如 `git hash-object -w`），並在 manifest 記錄該 blob/snapshot 的 hash 與保存位置。
- FR-36: 若任一必要比較程式或輸入無法被完整快照（snapshot 缺失、無法讀取、或 SHA256 與宣稱路徑不符），Gate R1-P MUST FAIL，且不得繼續執行 Phase E 完整 audit。

---

### Identity ladder / 六層對帳

每一層 MUST 保留上一層輸出，不得只輸出最終 Jaccard。

### Layer D0 — Decision clock

- FR-7: MUST 對帳 decision date、資料 as-of、排名日期及下一交易日 hint。
- FR-8: 日期字串與交易日正規化 MUST 明確記錄，不得用 nearest-date 靜默補值。

### Layer D1 — Universe eligibility

每月 MUST 產生以下集合：

```text
R_U       = research tier_valid universe
P_A_U     = production A score_store 有有效 composite 的集合
P_B_U     = production c2_fullpool 有有效 c2_score_full 的集合
P_C_U     = P_A_U ∩ P_B_U
```

- FR-9: MUST 回報每個集合的 N、交集、only-left、only-right 與 Jaccard。
- FR-10: 每個 universe exclusion MUST 只能使用已凍結 reason code，不得以自由文字代替。
- FR-11: watchlist membership MUST 作為 audit 欄位；R1 MUST NOT 修改 `watchlist.txt`。
- FR-12: ADV20、listed_ok、score coverage、c2 file membership MUST 分欄記錄，不得合成單一 `eligible` 後失去歸因。

### Layer D2 — Raw scores on common keys

在 `R_U ∩ P_C_U` 的共同 `(date, ticker)` 上：

- FR-13: MUST 比較 `real_composite_R`、`real_composite_P`，並在可用時加入 `real_composite_L`。
- FR-14: MUST 比較 research c2 與 production `c2_score_full`；四個原子輸入若可用 MUST 一併輸出。
- FR-15: float equality MUST 同時回報 exact equality 與預註冊 tolerance equality；預設 tolerance 為 `1e-12`，若現有序列化精度不足，修改 tolerance 必須先勘誤。
- FR-16: raw-score 缺值、無窮值、重複鍵 MUST fail closed，不得 dropna 後繼續。
- FR-17: R 與 P scoring 必須在隔離 process 建置；任何 `bt_bundle` 全域覆寫污染 production process 時 MUST abort。

### Layer D3 — Percentile/rank

- FR-18: MUST 保存各路徑實際 denominator N、rank method、tie handling、direction 與 threshold count。
- FR-19: MUST 比較「各路徑原生排名」；不得先強迫同 universe 再宣稱 identity。
- FR-20: MAY 另外輸出共同 universe counterfactual，但 MUST 清楚標為 `DIAGNOSTIC_COUNTERFACTUAL`，不得取代原生結果。
- FR-21: MUST 分別回報 A Top20%、B Top20% membership Jaccard 與 boundary crossers。

### Layer D4 — Fusion membership

- FR-22: MUST 比較 R dual100、P-app dual100、P-L4a dual100 三個集合。
- FR-23: P-app 與 P-L4a 在相同凍結輸入下 MUST exact-set identical；否則標記 `PRODUCTION_INTERNAL_DIVERGENCE` 並 fail closed。
- FR-24: MUST 回報每月 holdings N、pairwise Jaccard、ENTER/EXIT 與 first-divergence layer。
- FR-25: Jaccard 為描述指標，不是 R1 PASS/FAIL 門檻。

### Layer D5 — L4a handoff boundary

- FR-26: MUST 驗證傳入 portfolio construction 前的 ticker set、as_of、score/rank 欄位與排序鍵。
- FR-27: R1 MUST 在 sizing、持倉狀態、整張換算、ADV order cap 或 OrderIntent 建立之前停止。
- FR-28: R1 MUST NOT 呼叫 L4b、寫入 PositionState、建立真實訂單或修改 production state。

---

### Difference taxonomy / 固定歸因碼

每個不一致 `(date, ticker)` MUST 至少有一個 primary reason，且只能從下列 enum 選取：

```text
DATE_NOT_COMMON
UNIVERSE_RESEARCH_ADV_OR_LISTED
UNIVERSE_P_A_SCORESTORE_ABSENT
UNIVERSE_P_A_WATCHLIST_BUILD_SCOPE
UNIVERSE_P_A_SCORE_MISSING
UNIVERSE_P_B_FULLPOOL_ABSENT
UNIVERSE_P_B_SCORE_MISSING
A_SCORE_DEFINITION_VALUATION_WINDOW
A_SCORE_DEFINITION_CHIP_SOURCE
A_SCORE_OTHER_KNOWN_COMPONENT
A_SCORE_UNEXPLAINED
B_SCORE_INPUT_DIFFERENCE
B_SCORE_FORMULA_DIFFERENCE
B_SCORE_UNEXPLAINED
A_RANK_DENOMINATOR
B_RANK_DENOMINATOR
RANK_METHOD_OR_TIE
THRESHOLD_BOUNDARY
FUSION_IMPLEMENTATION
L4A_HANDOFF
UNKNOWN
```

- FR-29: `UNKNOWN` 與 `*_UNEXPLAINED` MUST 計入 unexplained rate，不能視為已歸因。
- FR-30: 同一列有多個原因時 MUST 記錄 primary reason 與 ordered contributing reasons。
- FR-31: first-divergence layer MUST 依 D0→D5 決定；後續衍生差異不得倒灌成上游原因。
- FR-32: 估值窗與籌碼源只有在原子或既有 reconciliation 證據支持時才能指派；不得僅憑總分不同猜測。

---

## Non-Functional Requirements

- NFR-1（唯讀）: 執行 MUST NOT 修改 `score_store`、`watchlist.txt`、`c2_fullpool_*`、TEJ cache、PositionState、OrderIntent 或既有研究面板。
- NFR-2（隔離）: research 與 production raw-score 建置 MUST 使用獨立 process；process module manifest MUST 隨結果保存。
- NFR-3（決定性）: 相同 commit、manifest 與輸入重跑兩次，所有摘要 CSV 與 JSON 的內容 hash MUST 相同；允許 stdout 時間戳不同。
- NFR-4（可稽核）: 每個摘要數字 MUST 可回溯到逐列差異檔，且逐列檔有 schema version。
- NFR-5（fail closed）: duplicate key、日期非唯一、必要欄缺失、production 內部融合分歧或 process contamination MUST 使 run non-zero exit。
- NFR-6（效能）: 不預設牆鐘時間門檻；實際 elapsed time 與 peak memory SHOULD 被記錄，但不得為了加速改變比較母體或抽樣。
- NFR-7（資料安全）: 產出 MUST NOT 包含 API key、cookie、憑證、完整外部原始資料或未核准的 production state。
- NFR-8（版本控制）: 大型可重建逐月/逐列明細 SHOULD gitignore；summary、manifest、hash、重建命令與報告 MUST 進版控。

---

## Acceptance Criteria

### AC-1: 凍結件完整 (FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-33, FR-34, FR-35, FR-36, NFR-4)

Given R、P-A、P-B 的輸入路徑已解析  
When 執行 preflight  
Then manifest 列出各來源、hash、日期範圍與日期數  
And comparable dates 由三方完整日期交集機械產生  
And 缺月沒有被靜默排除  
And 每個被比較之 production 程式/輸入檔均記錄精確路徑、SHA256 與 tracked/untracked/modified 狀態  
And 任何不屬於 `5f3f5d31` 的必要檔案均有對應唯讀 snapshot 或 Git blob，否則 Gate R1-P FAIL。

### AC-2: 隔離無污染 (FR-17, NFR-2, NFR-5)

Given research 與 production scorer 在兩個乾淨 process 執行  
When production process module manifest 被檢查  
Then 不得含 `beat_0050.realbody.bt_bundle` 及已知間接污染模組  
And 若出現則 run 必須 abort 且不得輸出 PASS。

### AC-3: Universe 可完整重建 (FR-7, FR-8, FR-9, FR-10, FR-11, FR-12)

Given 任一 comparable date  
When D1 audit 完成  
Then R_U、P_A_U、P_B_U、P_C_U 的 ticker 明細與 N 可由逐列檔重算  
And only-left/only-right 計數與集合運算 exact match  
And exclusion 欄只使用固定 reason code。

### AC-4: Raw score 對帳 fail closed (FR-13, FR-14, FR-15, FR-16, FR-17, NFR-5)

Given common keys  
When D2 對帳完成  
Then exact/tolerance equality、missingness 與最大絕對差均有輸出  
And duplicate、NaN 或 infinite 必要分數會使 run abort  
And 不得因 dropna 改變 denominator。

### AC-5: 排名語意可重現 (FR-18, FR-19, FR-20, FR-21)

Given 每條路徑的 raw score 與原生 universe  
When D3 排名重建  
Then denominator、rank method、ties、direction、Top20% count 與原生輸出一致  
And 任一 counterfactual 都帶 `DIAGNOSTIC_COUNTERFACTUAL` 標記。

### AC-6: Production 內部 identity (FR-22, FR-23, FR-24, NFR-5)

Given app 與 L4a 使用相同凍結 A/B 輸入  
When 兩者產生 fusion membership  
Then ticker set 必須 exact identical  
And 若不同，run 標記 `PRODUCTION_INTERNAL_DIVERGENCE` 並停止在 D4。

### AC-7: 逐列 first-divergence 歸因 (FR-29, FR-30, FR-31, FR-32)

Given 任一 R/P 最終 membership 不一致列  
When attribution 執行  
Then 該列有唯一 first-divergence layer、primary reason 與可選 contributing reasons  
And primary reason 必須來自固定 enum  
And沒有證據時只能標為 `UNKNOWN` 或 `*_UNEXPLAINED`。

### AC-8: 結構裁決 (FR-29, NFR-4)

Given 全部 comparable dates 已完成 D0–D5  
When 計算歸因覆蓋率  
Then `explained_rate = explained_differences / all_differences`  
And只有 explained_rate 等於 100%、unknown/unexplained 等於 0、且所有 hard assertions 通過時，Gate R1-A 才可 PASS。

### AC-9: 低 Jaccard 不觸發模型修改 (FR-25, NFR-1)

Given 任一層 Jaccard 低於 0.95  
When 產生 R1 報告  
Then 該數字只作差異幅度描述  
And不得自動修改 universe、score、threshold 或 production。

### AC-10: 重播一致 (NFR-3)

Given 相同 commit、config 與輸入 manifest  
When 完整 R1 執行兩次  
Then 所有 canonical summary CSV/JSON 的內容 hash exact match  
And若不同，Gate R1-R 為 FAIL。

### AC-11: 安全停止於 L4a 邊界 (FR-26, FR-27, FR-28, NFR-1)

Given D4 fusion 已完成  
When 建立 handoff audit  
Then 只輸出候選 ticker/rank/score schema  
And不建立訂單、不修改部位、不呼叫 L4b。

---

## Edge Cases

- EC-1: P-A 有日期但 P-B 無同日檔案 → 標記 `MISSING_P_B`，不採 nearest date。
- EC-2: score_store 同一 `(as_of, stock_id, mode)` 重複 → abort，不得 keep-last。
- EC-3: c2 fullpool 同一 `(date, stock_id)` 重複 → abort。
- EC-4: ticker 格式不同（例如字串/數字、尾碼）→ 只允許預註冊 normalization；原值與正規值都要保存。
- EC-5: float 序列化使 exact inequality 但 tolerance equality → 同時回報，不得只報 PASS。
- EC-6: ties 跨 Top20% 邊界 → 沿用各路徑原生行為並明列 boundary members。
- EC-7: 任一路徑 fusion 為空集合 → Jaccard 記為 NA 並回報空集合原因，不得定義為 1。
- EC-8: production scorer process 被 bt_bundle 污染 → abort。
- EC-9: 原子因子不足以區分估值窗與籌碼源 → 標記 unexplained，不得猜測。
- EC-10: comparable dates <24 → `INSUFFICIENT_HISTORY`，不得宣稱全歷史 identity。
- EC-11: app UI wrapper 無法在無 Streamlit session 下直接呼叫 → 抽取純函式前必須先證明同輸入回歸一致；若需改 public behavior，停止並修訂 prereg。
- EC-12: 讀取 production state 需要寫入或 migration → 停止；R1 不授權任何寫入。

---

## API Contracts

R1 沒有 HTTP API。API Contracts：**N/A — 本研究為離線唯讀稽核。** 以下為必要 artifact contract。

## Data Models

### 10.1 `identity_monthly.csv`

| Field | Type | Constraints |
|---|---|---|
| date | string | `YYYY-MM-DD`，unique |
| n_R_U | int | ≥0 |
| n_P_A_U | int | ≥0 |
| n_P_B_U | int | ≥0 |
| n_P_C_U | int | ≥0 |
| jaccard_universe_R_PC | float/NA | [0,1] |
| jaccard_A_top20 | float/NA | [0,1] |
| jaccard_B_top20 | float/NA | [0,1] |
| jaccard_fusion_R_P | float/NA | [0,1] |
| n_membership_diff | int | ≥0 |
| n_unexplained | int | ≥0 |
| app_l4a_exact | bool | MUST be true for valid run |

### 10.2 `identity_row_diff.csv`

| Field | Type | Constraints |
|---|---|---|
| date | string | decision date |
| ticker_raw_R | string/NA | preserved raw ID |
| ticker_raw_P | string/NA | preserved raw ID |
| ticker | string | normalized audit key |
| in_R_U/in_P_A_U/in_P_B_U/in_P_C_U | bool | required |
| A_score_R/A_score_P/A_score_L | float/NA | raw scores |
| B_score_R/B_score_P | float/NA | raw scores |
| A_rank_R/A_rank_P/B_rank_R/B_rank_P | float/NA | native ranks |
| selected_R/selected_P_app/selected_P_l4a | bool | required |
| first_divergence_layer | enum | D0–D5/IDENTICAL |
| primary_reason | enum | §6 taxonomy |
| contributing_reasons | JSON array | ordered, may be empty |
| evidence_ref | string | source row/file/function reference |

### 10.3 `manifest.json`

MUST 包含：

```text
git commit / dirty-path inventory
approved prereg draft sha256（核准當下之草稿版本，非最終文件自我雜湊；見 §17）
config sha256
input paths, sha256, and git status (tracked-clean / tracked-modified / untracked)
code paths, sha256, and git status (tracked-clean / tracked-modified / untracked)
snapshot / git-blob hash and storage location for any compared file not part of commit 5f3f5d31（FR-35）
Python and dependency versions
process module manifests
decision-date inventory
normalization rules
rank semantics
output hashes
rerun command
```

### 10.4 其他固定產出

```text
research/p0_r1_research_production_identity/
    prereg.md
    manifest.json
    preflight.json
    identity_monthly.csv
    identity_row_diff.csv
    reason_summary.csv
    app_vs_l4a.csv
    metrics.json
    report.md
    invalid_runs.log          # 若有 invalid run
    approval_receipt.json     # 記錄最終核准文件之 git blob/commit identity，MAY 與 manifest.json 合併
```

大型可重建逐月明細 MAY 放在 gitignored 子目錄；manifest MUST 保存檔數、總大小、整批 hash 與重建命令。

---

## 11. Gates and decision rules

### Gate R1-P — Preflight validity

PASS 必須全部成立：

```text
spec status == APPROVED
all input paths resolved
hashes recorded
date inventory recorded
all compared production code/input files have SHA256 + git tracked/untracked/modified status recorded (FR-34)
any compared file not part of commit 5f3f5d31 has a read-only snapshot or Git blob saved, with hash and location recorded (FR-35)
no prohibited module contamination
no writes to protected inputs
normalization and rank semantics frozen
```

否則：`R1-P FAIL`，不得進完整對帳。

### Gate R1-I — Production internal identity

```text
P-app fusion set == P-L4a fusion set
```

須在所有 comparable dates exact match。任一失敗：`R1-I FAIL`；不得用其中一條冒充 production identity。

### Gate R1-A — Attribution completeness

```text
explained_rate == 100%
UNKNOWN == 0
A_SCORE_UNEXPLAINED == 0
B_SCORE_UNEXPLAINED == 0
hard assertions all pass
```

未達成則：`R1-A FAIL`。這不是策略失敗，而是身份差異尚未解釋完成。

### Gate R1-R — Reproducibility

兩次完整重跑的 canonical summaries 與 metrics hash MUST exact match。否則：`R1-R FAIL`。

### 最終 Case

```text
Case A: R1-P PASS + R1-I PASS + R1-A PASS + R1-R PASS
        → 身份差異已完整量測與歸因；可另立 R2 對齊候選規格。

Case B: Preflight PASS，但 R1-I FAIL
        → production 內部 app/L4a 不一致；另立 focused fix，R1 不代修。

Case C: R1-A FAIL
        → 保存 UNKNOWN/UNEXPLAINED 證據；不得提出 production 對齊方案。

Case D: 結果顯示 R 與 P 已 identical
        → 記錄 null result；不得為了產生工作而修改任何路徑。
```

**沒有 Jaccard 最低通過門檻。** Jaccard 0.64、0.95 或 1.0 都只是量測結果。

---

## 12. Execution protocol

### Phase A — Spec approval

使用者將本文件狀態改為 `APPROVED` 前，MUST NOT 寫程式、抽取 production 函式或執行歷史 audit。

### Phase B — Preflight only

允許查看：路徑、schema、hash、日期範圍、缺月、module import graph、dirty path inventory。  
禁止查看或修改：績效、未來報酬、production state。

### Phase C — Unit/synthetic validation

至少建立：

```text
test_date_intersection_no_nearest_fill
test_universe_set_accounting
test_reason_enum_closed
test_first_divergence_order
test_duplicate_key_aborts
test_nan_score_aborts
test_bt_bundle_contamination_aborts
test_native_rank_semantics_preserved
test_counterfactual_is_labeled
test_app_l4a_same_input_exact_set
test_no_l4b_or_state_write
test_output_replay_hash_stable
```

### Phase D — Freeze

記錄 commit、prereg/config/input/code hashes、dirty path inventory、日期範圍與重跑命令。不得把既有 unrelated dirty state 納入本任務。

### Phase E — Full identity reveal

一次完整產出 D0–D5 與固定 artifacts。因 R1 不使用未來報酬，不消耗新的 alpha OOS；但差異 taxonomy、normalization、tolerance 與 gate 在 reveal 後仍不得修改以粉飾結果。

### Phase F — Independent replay

使用同 manifest 重跑一次，只比較 canonical output hashes。重播不得變更輸入或設定。

---

## 13. Invalid runs

只有下列情況可宣告 INVALID 並重跑：

- implementation 不符合已核准 prereg；
- duplicate/missing/schema/process contamination assertion 失敗；
- 輸入檔在執行中改變；
- app/L4a 抽取造成已證實的機械性 bug；
- output 寫入中斷或 hash 不完整。

`invalid_runs.log` MUST 記錄 run id、原因、受影響檔案、修正前後 commit/hash。以下不是 invalid 理由：

- Jaccard 太低或太高；
- production 與 research 差異比預期多；
- 無法達到 100% explained；
- 結果顯示 watchlist 不是主要原因；
- 結果不支持後續對齊。

---

## Out of Scope

- OS-1: 修改或重建 `watchlist.txt` — R1 只量測其 membership 影響。
- OS-2: 啟用 P0-U1 `--canonical` — U1 已封存且預設 False。
- OS-3: 將 research 2004 估值窗部署到 production — 需另立 R2/migration 規格。
- OS-4: 將 institutional net/gross 任一方改成另一方 — 已有 live-config 獨立驗證，本案不選邊。
- OS-5: DataExport0806 遷移或寫入 `tej_cache` — 尚未取得 migration 授權。
- OS-6: 修改 c2、ADV100萬、FUSION_PCT=20、TOP_N=None 或 equal weight。
- OS-7: 重跑或重新裁決 H1–H5 — R1 不使用績效作 identity gate。
- OS-8: L4a sizing、L4b execution、OrderIntent/PositionState 或真實交易。
- OS-9: Streamlit UI 改版或顯示新增。
- OS-10: 把 identity 差異自動解讀成 alpha、bug 或 deployment blocker。

---

## 15. Final report template

```text
# P0-R1 Research / Production Identity Result

## 0. Scope and non-claims
## 1. Preregistration integrity
## 2. Input and date inventory
## 3. D0 decision-clock identity
## 4. D1 universe identity
## 5. D2 raw-score identity
## 6. D3 rank/percentile identity
## 7. D4 fusion identity
## 8. D5 L4a handoff boundary
## 9. First-divergence attribution
## 10. Production app vs L4a identity
## 11. Gate results: R1-P / R1-I / R1-A / R1-R
## 12. Limitations
## 13. Decision
## 14. Next action
```

報告 MUST 先列 scope、assertions、未知項與 gate，再列 Jaccard。不得以「live 也通過 H1–H4」掩蓋 identity 差異，也不得以 identity 差異否定已完成的 live-config validation。

---

## 16. 對執行代理的強制指令

> 本任務是 P0-R1 Research / Production Identity 的唯讀差異歸因，不是修復或部署任務。不得修改 watchlist、score formula、估值窗、籌碼源、ADV、c2、FUSION_PCT、TOP_N、成本、L4a/L4b 或 production state。不得用共同 universe counterfactual 取代兩條路徑的原生比較。若發現差異，只能使用預註冊 reason code 歸因；沒有證據時必須標記 UNKNOWN/UNEXPLAINED。若 app 與 L4a 在相同輸入下不一致，停止並回報，不得在本任務順手修正。任何對齊方案都必須另立 P0-R2 規格並取得使用者核准。

---

## 17. 核准欄

```text
User approval: APPROVED
Approved scope: P0-R1 read-only identity audit only
Approved commit（repository baseline only，非 production identity 的完整代表；見 FR-33）: 5f3f5d31
Approved draft SHA256（本 prereg 草稿版本識別，非最終文件自我雜湊）: 18fbd7f37735166c8bb0e5835b440b99e0686edaaf7aa9d5047e54334298be69
Final approved document identity: 不寫回本文件；由核准後的 Git blob／commit 記錄，並保存於 approval_receipt.json 或 manifest.json（見 §10.3、§10.4）
Implementation authorized: YES（scope 限 Phase B 唯讀 preflight；Phase C 起需另行確認）
Performance reveal authorized: N/A (future returns prohibited)
Production writes authorized: NO
```

本文件已由使用者核准，狀態由 `IN REVIEW` 改為 `APPROVED`；核准後的最終文件版本 hash 不寫回本文件自身，改記錄於 git blob/commit 與 `approval_receipt.json` / `manifest.json`。Implementation authorized 目前僅涵蓋 Phase B 唯讀 preflight；Gate R1-P 通過後，Phase C（unit/synthetic validation）起仍需使用者逐階段確認方可繼續，不視為本次核准已一併涵蓋。
