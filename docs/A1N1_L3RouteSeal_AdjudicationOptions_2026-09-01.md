# A-1 · L3 route seal 契約 ＋ N-1 · 日曆沒有權威腿 — 裁決選項書

**狀態（寫定於 2026-09-01，狀態行不隨時間變動）**

```
ADJUDICATED 2026-09-02 — DOCUMENT ONLY；IMPLEMENTATION NOT AUTHORIZED
裁決見 §9。四組原始選項全部保留，未刪除。
本文件之外未變更任何 code / master prereg / data。
未取 seal（write_route_seal() 未被呼叫）。
ROUTE_SEAL_CONTRACT_STATUS 未被改動，仍為 NOT_YET_RATIFIED —— 依 §9 的 N-1
裁決，這是刻意保留的，不是待辦。
route_closure.py 的 owed 清單未被改動。
未跑 --mode execute。
```

> 本文件把選項攤開，不作裁決，也不預先宣告傾向。
> 每個選項都自證代價；被量測否證的敘述以刪除線保留，不刪除。

**基底 commit**：`ea491a14`（主線）。
**⚠ 本文件引用的 `research/b0_l3_runner/l3_route_seal.py` 目前是 untracked**，
來自分支 `claude/l3-bline-execution-merge`，且該檔正在覆核中，行號可能變動。
引用前請自行複驗（`review-verification-discipline`：行號比對判基底）。

**本 session 實測** 的項目在下文標 ⟨M⟩；**繼承自任務指示或工作單** 的標 ⟨I⟩。

---

## 0 · 先把裁決標的縮到最小

### 0.1 不是自由度的（已成既定事實，裁決不必處理）

| 項目 | 為什麼不是選項 |
|---|---|
| seal 的**取得**受 `route_closure` 欠款清單擋著 | ⟨M⟩ `l3_route_seal.py:207` `assert_route_is_sealable()` 讀 `route_closure.seal_payload()`；實跑目前吐 4 項欠款。這是**鎖 A**，屬 A2 邊界，**不是 A-1** |
| seal 的**內容是內容定址的** | ⟨M⟩ `route_seal_id(payload)` = payload 的 `canonical_sha256`，payload 即身分。這一點兩邊模組沒有分歧 |
| capture 必須在 seal 之前 | ⟨M⟩ `core/b0_l3_lineage_capture.py:50-53` `BINDING_CHAIN` 單向，且 `:121-126` 明文拒絕 capture manifest 攜帶 `route_seal_id` |

### 0.2 **是**自由度，但任務指示原本判為「不是」——本文件更正

> ⚠ **更正**：任務指示 §5.2 稱「id 已經是內容定址（`L3SEAL-<64 hex>`、payload 即身分）——這不是選項，是既成事實」。
> ~~id 形式為 `L3SEAL-<64 hex>`，非裁決標的。~~
> **⟨M⟩ 2026-09-01 實測否證。** 兩個模組對「內容定址」的定義**不相容**，見 §2.1。
> 這是一個**真正的、且尚未被任何人列出的裁決標的**。

### 0.3 真正要裁的四項

| # | 標的 | 節 |
|---|---|---|
| **A-1a** | 兩個模組的 seal 身分形式不相容——以哪一邊為準 | §2.1 |
| **A-1b** | 兩份 placeholder 清單分歧——單一來源在哪 | §2.2 |
| **A-1c** | 45 檔的閉包定義 + glob 綁定，蓋下去就固定，接受嗎 | §3 |
| **N-1** | 決策時唯一決定「什麼時候」的家族是 SUPPLEMENTARY，route 可否被 seal | §5 |

---

## 1 · A-1 的鎖是哪一道（兩道鎖不要混為一談）

⟨M⟩ 逐項複驗：

| | 位置 | 擋什麼 | 現況 |
|---|---|---|---|
| **鎖 A** | `l3_route_seal.py:207` `assert_route_is_sealable()` | **取**不到 seal | 實跑吐 4 項欠款。其中 2 項（portfolio side、runner 呼叫 `run_decision`）已由 `claude/l3-bline-execution-merge` 供給、1 項（MASTER FREEZE 記 v1.32）是過期文字（實測 `master_prereg_freeze.json` = `1.37` / `NORMATIVE_FROZEN`）⇒ 實為 **1 項**：floor capture。**不是 A-1** |
| **鎖 B** | `core/b0_l3_lineage_capture.py:237-242` | **用**不了 seal（`PURPOSE_PRODUCTION` manifest 不受理） | **這才是 A-1** |

`assert_route_seal_is_real()`（`:195`）依序跑三道**真檢查**，三道全過之後才到鎖 B：

1. 不是 placeholder（`PLACEHOLDER_ROUTE_SEAL_IDS`，`:89-92`，12 項）
2. 形式 `ROUTE_SEAL_ID_RE = ^L3SEAL-[0-9a-f]{64}$`（`:84`）
3. `file_sha256(artifact) == digest`——**檔案的位元組雜湊等於 id 裡那段摘要**

然後 `:237-242` 與輸入無關地 raise。docstring 自陳：

> The layers are written now so that **ratifying the contract is a deliberate edit here**
> rather than a silent widening somewhere else.

⟨M⟩ `ROUTE_SEAL_CONTRACT_STATUS` 全 repo 只出現 5 處：定義（`:83`）、錯誤訊息插值（`:242`）、
`b0_master_prereg.py:1413` 回報、`tests/test_b0_l3_lineage_capture.py:21,89` 斷言。
**沒有任何 `if` 讀它。** ⇒ 改那個字串不會有任何作用，只會讓人以為批准了。

---

## 2 · A-1 批准前必須先裁的兩件事（**鎖 B 目前正在掩蓋它們**）

> 這一節是本文件相對於任務指示新增的內容。
> 兩項缺陷今天都不會顯形，因為鎖 B 一律擋下；**鎖 B 一旦拿掉，兩者同時變成活的**，
> 而且活在「第一次真實 execute」那一次。

### 2.1 A-1a · 兩個模組對「內容定址」的定義不相容 ⟨M⟩

| | `l3_route_seal.py`（合併進來的） | `core/b0_l3_lineage_capture.py`（主線） |
|---|---|---|
| id 是什麼 | payload 物件的 `canonical_sha256` | 檔案位元組的 `file_sha256` |
| id 形式 | 裸 64-hex，無前綴 | `L3SEAL-<64 hex>` |
| 驗證方式 | `load_route_seal` 重算 `route_seal_id(seal)` 比對（`:296-313`） | `file_sha256(artifact) == digest`（`:226-236`） |

**實測**：以合成 payload 呼叫 `rs.route_seal_id(...)` 得
`'92ae762cc4df2206250c8125276d830ba52dc6bb45f17ffc5c0f05fff8ba356d'`，
長度 64、無 `L3SEAL-` 前綴、`ROUTE_SEAL_ID_RE.match(...)` 為 `False`。
`grep L3SEAL` 在 `l3_route_seal.py` 與 `tests/test_b0_l3_route_seal.py` 命中 **0 次**。

⚠ **前綴只是表層。**`write_route_seal()`（`:266-292`）寫出的檔案內容是
`payload + {"route_seal_id": ident}`，且以 `indent=1` 序列化 ⇒
**該檔的 `file_sha256` 依建構就不等於 `ident`**。
即使補上 `L3SEAL-` 前綴，core 的**第三層**仍會判否。
兩者各自內部自洽、互相不相容。

**要裁的**：

- **選項 A1a-1 · 以 core 為準**（seal id ＝ seal 檔位元組的雜湊，加 `L3SEAL-` 前綴）
  代價：`write_route_seal` 必須改成「先寫檔、再由檔算 id、再改名」的兩段式，
  而那會破壞現行的 O_EXCL 單次原子寫入（`:284-288` 那個「碰撞即代表此路由已封印」的性質會消失，
  因為檔名在寫入當下還不知道）。且 `assert_seal_binds_current_route` 的重算比對要一併改寫。
- **選項 A1a-2 · 以 B 線為準**（seal id ＝ payload 的 canonical hash；放寬 core 的第二、三層）
  代價：core `:196` 的整段理由「A real seal is a CONTENT-ADDRESSED artefact, **not a non-placeholder string**」
  要重寫——放寬第三層等於承認 core 無法獨立驗證那個 artefact，驗證責任全押在 `l3_route_seal.py` 這個
  **目前還 untracked、正在覆核中**的模組上。
- **選項 A1a-3 · 雙欄位**（payload hash 與 file hash 都寫進 seal，id 用其中一個、另一個作交叉檢查）
  代價：兩個雜湊會有一個是「沒人真的用它做決定」的欄位，而本專案已有前例
  （`route_closure.py` 的 owed 清單長期帶著一句被 `master_prereg_freeze.json` 推翻的過期文字）。
  新增未被任何 `if` 讀取的欄位，與 `ROUTE_SEAL_CONTRACT_STATUS` 的處境同型。
- **選項 A1a-4 · 不裁，維持鎖 B**
  代價：A-1 不動，`--mode execute` 永久不可達，L3 前瞻線不產出任何投組。
  但這是**唯一不會誤綁的選項**，見 §6 順序風險。

### 2.2 A-1b · 兩份 placeholder 清單，內容不一致 ⟨M⟩

`core:89-92` `PLACEHOLDER_ROUTE_SEAL_IDS` 12 項（含 `""`、`"TODO"`、`"0"`）；
`l3_route_seal.py:63-65` `PLACEHOLDER_SEAL_IDS` 8 項。實跑：

```
'TODO'    -> ACCEPTED by l3_route_seal   （core 拒收）
'0'       -> ACCEPTED by l3_route_seal   （core 拒收）
'PENDING' -> refused
```

`l3_route_seal.py:352-355` 的 docstring 自稱
「Refusing placeholders is therefore **this module's job**, not the manifest's」，
但 core 也在做同一件事、用不同清單，且沒有任何測試把兩者綁在一起。

**要裁的**：單一來源放哪一邊（core 匯出、B 線 import？還是相反？），
或明文裁定「兩層各自獨立、清單容許分歧」並寫出為什麼分歧是可接受的。
代價：若選「容許分歧」，必須說明為何較寬的那一層不是實際生效的那一層——
而現行呼叫順序上，`l3_route_seal` 的檢查發生在 core 之前。

---

## 3 · A-1c · 這 45 個檔就是「生產路線」嗎

⟨M⟩ 實跑 `rs.sealed_file_set()` → **45**；`rs.assert_no_producer_is_unbound(files)` → **7**。

| 目錄 | 檔數 |
|---|---|
| `core` | 30 |
| `research/b0_materializer` | 7 |
| `research/b0_l3` | 4 |
| `research/b0_checkpoint` | 2 |
| `research/b0_l3_runner` | 2 |
| **合計** | **45**（另 7 個 source producer） |

payload（`:229-251`）另含 `contract_version`（實測 `b0_l3_route_seal@1`）、`closure_kind`、
`entry_points`、`core_decision_closure`、`required_dataset_floor`、
`route_closure_code_closure_size`、`source_producers`、`file_count`，
以及 `files`：**每個檔的 sha256**。

`write_route_seal()` docstring：

> Taking the first L3 route seal **fixes what "the production route" means for every
> prospective observation afterwards**; it is a separately-authorised act, not a side
> effect of running a period.

### 3.1 閉包邊界

- `MODULE_ROOTS`（`:69`）：`""`、`research/b0_l3`、`research/b0_l3_runner`、
  `research/b0_checkpoint`、`research/b0_materializer`、`research/b0_l2`
- `ENTRY_POINTS`（`:79`）：`run_l3_prospective.py` ＋ `portfolio_side.py`
- 落在 roots 之外的模組**被回報而非靜默綁定**

**要裁的**：這個閉包蓋下去就固定。有沒有該進而沒進的？
（本文件不主張答案；但裁決時應注意 `research/b0_l2` 在 roots 內，
而 L2 是已封印的回顧線——把它綁進前瞻路由的身分裡，代價是 L2 的任何維護都會改變 seal。）

### 3.2 producer 用 glob 綁，不是清單

`SOURCE_PRODUCER_GLOBS`（`:90-94`）綁 `build_*_leaf.py`、`build_flat_leaves.py`、
`source_ownership_manifest.py`。程式碼裡的理由：

> Declared as a GLOB rather than a list... because **a hand-written list is how the
> provisional `REQUIRED_DATASETS` floor lost two families.**

代價：**符合樣式的新檔一出現，seal 的內容就變。**

⟨M⟩ 這個代價**現在就有一個實例**：`tests/test_b0_l3_route_seal.py:96-107`
`test_the_producer_set_is_read_from_disk_not_hand_listed` 會往真實 repo 寫
`research/b0_materializer/build_zzz_probe_leaf.py`（清理只在 `finally`）。
該檔正中 glob ⇒ 進 `source_producer_files()` ⇒ 改變 `route_seal_id`。
**要裁的是綁法本身**；該測試的寫法是另一件事（已在覆核清單裡）。

⚠ 兩條綁定路徑要分開講，不要混為一談：
producer 的 **CODE** 由 import 到不了，靠 glob 綁；
它們的 **OUTPUT** 靠 leaf payload hash → aggregate payload hash → attestation 傳遞。

---

## 4 · N-2 · seal 綁程式碼，但 leaf hash 相依於 seal 外的資料

⟨I⟩ 工作單 §3 N-2（`docs/L3_v138_WorkList_2026-08-30.md`，分支 `codex/l3-september-readiness`）：

> leaf payload 現在還相依於兩個「資料」檔：`data/b0/trading_calendar.csv`（經 `panel_end_session`）
> 與 `research/d1_price_universe/price_source_contract.json`。兩者都不在 `FLOOR_CAPTURE_CODE_CLOSURE`
> （那是**程式**閉包）⇒ 跨 clone 比對 leaf hash 的人必須知道 leaf 已不再只是 archive 的函數。

**要裁的**：

- **選項 N2-1 · seal 一併綁這兩個資料檔**
  代價：seal 從「程式路由的身分」變成「程式＋部分資料的身分」，
  而 `closure_kind` 目前明文是 `PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE`。
  且 `trading_calendar.csv` 是**每個交易日都會變**的檔（見 §5）⇒ seal 會每日失效。
- **選項 N2-2 · 明文揭露「seal 只綁程式碼」**
  代價：跨 clone 比對 leaf hash 的人若不讀這行揭露，會得到「同樣的程式、不同的 hash」而無法歸因。
  本專案史上四次結論作廢**全部沒有報錯**——這正是那個形狀。
- **選項 N2-3 · 把兩個檔升格為 declared dataset family**（走 leaf/aggregate 既有機制，而非塞進 seal）
  代價：`REQUIRED_DATASET_FLOOR` 變動會連動 `route_closure` 與 capture inventory
  （`FLOOR_CAPTURE_REQUIRED_DATASETS`），是跨三個模組的變更，且 C-71 的 inventory 是 FIXED 的。

---

## 5 · N-1 · 日曆沒有權威腿（**可能讓整條線在九月不成立的那一個**）

⟨I⟩ 工作單 §4 N-1 原文：

> **日曆沒有權威來源。** A-4 修好之後，calendar leaf 正確讀作 `LIVE / SUPPLEMENTARY` ——
> R-W1-2 把權威給 TEJ，而日曆的位元組不是 TEJ，所以**沒有 TEJ 腿可以對帳**。日曆決定「什麼時候」。
> **L3 route 可否在「決策時輸入的唯一家族是 SUPPLEMENTARY」下被 seal，無人裁過。**
> 舊的假標籤沒有解決這件事，只是把它藏起來。

### 5.1 ⟨M⟩ 主線現況比工作單描述的**更差**：假標籤還在

`research/b0_materializer/build_flat_leaves.py:197-198` 對**每一個 flat family 的每一筆 entry**
無條件寫死：

```python
"source_family": "TEJ",
"authority": "AUTHORITATIVE",
```

而 `calendar` family 的 landing 是 `os.path.join(os.path.expanduser("~"), "market_cache")`（`:90`），
消費的是 `taiex_daily.parquet` —— **那不是 TEJ 的位元組**。
`source_ownership_manifest.py:102-108` 對 R-W1-2 的註解明講家族歸屬「is part of its identity, not context」。

⇒ **在基底 `ea491a14` 上，A-4 尚未落地。** 今天若取 seal，它會綁定一份
**把日曆誤宣告為 TEJ / AUTHORITATIVE** 的 manifest 形狀。
這比工作單描述的「未裁決」狀態更嚴重：不是沒人裁，是**帳面上看起來已經有權威腿**。

### 5.2 ⟨M⟩ 日曆同時是會逐日變動的檔

`~/market_cache/taiex_daily.parquet` 實測末筆為 **2026-09-01**（即今日），共 5,575 列。
`build_flat_leaves.py:99-104` 自己的 notes 記載 W1 當時量到該快取在 `2026-08-26`、
canonical 日曆止於 `2026-08-17`——落差正在擴大。
（本 session 另發現 `tests/test_b0_l3_snapshot.py` 兩處硬編日期因此腐化，已改為由日曆導出。）

### 5.3 要裁的

- **選項 N1-1 · 判「不可 seal」**（決策時輸入的唯一時間家族是 SUPPLEMENTARY ⇒ route 不得封印）
  **後果必須寫足，這是使用者最需要的一格：**
  - 9/30 的 Month 1 **不會發生**。U-2 已釘死 decision `2026-09-30` / execution `2026-10-01`
    且明文「不得事後補記」⇒ 順延即意味著 Month 1 改期，而改期本身要另一次裁決。
  - 要解除，必須先補日曆的權威腿。**本文件不估工期**——補法本身有數個分支
    （向 TEJ 取日曆匯出？以 TEJ 價格資料的實際 session 反推？認定日曆為 derived-not-sourced？），
    每個分支的成本不同，且其中至少一個會回頭改動 `REQUIRED_DATASET_FLOOR`（連動 §4 N2-3）。
  - 這是**唯一不會產生「看起來已綁定、實際綁不上」的路由**的選項。
- **選項 N1-2 · 判「可 seal，但 seal 明文記載日曆為 SUPPLEMENTARY」**
  前置：必須先落地 A-4（讓 `build_flat_leaves.py` 停止把日曆標成 TEJ/AUTHORITATIVE），
  否則記載的內容與 manifest 相矛盾。
  代價：承認「決定什麼時候的那個家族沒有對帳腿」寫進封印，往後每一次前瞻觀測都繼承這個承認。
- **選項 N1-3 · 判日曆為 derived artefact，不適用來源家族分類**
  理由基礎：`build_flat_leaves.py:86-89` 自己的註解已指出日曆是
  `build_market_state.py:53` 從 `taiex_daily.parquet` **產出** `data/b0/trading_calendar.csv`，
  「Sharing a producer file is not sharing a source, and the first declaration here conflated the two」。
  代價：那就必須說明「產它的那個 parquet」本身歸誰對帳；問題被移動一層，不必然被消除。
- **選項 N1-4 · 先落地 A-4、量到誠實標籤之後再裁**
  代價：把裁決往後推，而 9/30 的日曆是固定的（見 §6）。

---

## 6 · 順序風險（必讀，這一節不是選項）

⟨M⟩ `BINDING_CHAIN`（`core:50-53`）：

```
capture_authority → lineage_price_floor_capture_record → final_route_seal → period_receipt
```

`core:20-21` 明講反向會死鎖。⇒ **floor capture（A-2）必須發生在 seal 之前。**

**風險**：A-2 在 A-1 之前執行，但 **A-1 若裁不過，A-2 等於白做**。
且 A-2 有兩個額外前置（⟨M⟩ 實測）：

1. `assert_repo_identity`（`core:346-355`）要求 **tracked 與 untracked 都乾淨**
   ⇒ 必須先 commit `claude/l3-bline-execution-merge` 的 7 檔 ⇒ 必須先過覆核。
2. `capture_lineage_floor()`（`core:741`）在 core 有，但**沒有任何腳本驅動它**（A-2 本體）。

⇒ 完整串行鏈：

```
覆核 7 檔 → commit → 樹乾淨 → 寫 capture runner → floor capture(A-2)
   → 取 seal(需鎖 A 清空) → 用 seal(需 A-1 裁決) → production run
```

**A-1 排在第三段。先裁它買不到進度；但不先裁它就做 A-2，可能白做。**
這個兩難本身也是裁決的一部分：是否接受「A-2 先做、承擔白做風險」以換取時程。

---

## 7 · 本文件明確**沒有**做的事

- 沒有裁決任何一項。四組選項全部保留。
- 沒有改 `ROUTE_SEAL_CONTRACT_STATUS`、沒有動 `:237-242` 的 raise。
- 沒有呼叫 `write_route_seal()`。沒有取 seal。
- 沒有改 `route_closure.py` 的 owed 清單。
- 沒有跑 `--mode execute`。
- 沒有估算 N1-1 的補救工期（§5.3 明列理由）。

## 8 · 落檔的一個已知副作用

新增本 untracked 檔會讓工作樹變髒，而
`tests/test_b0_c72_observation_accounting.py::test_the_read_only_seal_audit_survives_the_closure`
斷言唯讀 seal 稽核成功，其前置條件是乾淨工作樹（C-47）。
⇒ 本檔存在期間該測試會紅，**那是前置條件失敗，不是程式碼失敗**。
處置：commit 本文件，或在回報時明文標註為預期內的 precondition 失敗。

---

## 9 · 裁決（2026-09-02）

> 裁決人：使用者。記錄人：本 session。
> **本節是裁決本體，不是筆記。** 四組選項全部保留於上，未刪除。
> 裁決確立「是什麼」，**不授權實作**——每一項的落地各自需要另一次授權。

### 9.1 A-1a · 採 payload canonical hash 語義，統一 `L3SEAL-` 前綴

即 §2.1 選項 **A1a-2 的語義 ＋ A1a-1 的形式**：
seal id = payload 的 `canonical_sha256`，並冠上 `L3SEAL-` 前綴。

**落地時必須做的事，以及各自的代價**

| 動作 | 位置 | 代價 |
|---|---|---|
| `route_seal_id()` 回傳值加 `L3SEAL-` 前綴 | `l3_route_seal.py:253-256` | 小。但 `seal_path()`（`:259`）以 id 為檔名，前綴會進檔名 |
| **放寬 core 的第三層** | `core/b0_l3_lineage_capture.py:226-236` | ⚠ **最大的一項**。第三層現為 `file_sha256(artifact) == digest`；採 payload hash 語義後這條**依建構永遠為假**（seal 檔內容 = payload ＋ `route_seal_id` 欄位，且 `indent=1` 序列化）。必須改成「載入該檔、剔除 `route_seal_id` 欄位、重算 canonical hash 後比對」 |
| core 第二層 | 同檔 `:216-220` `ROUTE_SEAL_ID_RE` | **無需變更**——加了前綴後即相符。這是本裁決選擇統一前綴的直接收益 |

⚠ **第三層的修改落在 `assert_route_seal_is_real()` 函式體內**，與 §1 那個 `:237-242` 的
終端 raise 同一個函式。原任務指示 §2 明文禁止動該函式。
⇒ **此項落地需要一次明確的、單獨的授權**，且授權時應明說「只改第三層驗證方式，不動終端 raise」。

⚠ 本裁決**不**解除鎖 B。見 §9.4。

### 9.2 A-1b · 採 core 的完整 placeholder 清單，設為唯一來源

`core.b0_l3_lineage_capture.PLACEHOLDER_ROUTE_SEAL_IDS`（12 項）為唯一來源；
`l3_route_seal.PLACEHOLDER_SEAL_IDS`（8 項）改為自 core import，不再自行維護。

- **消除的實測缺口**：`'TODO'`、`'0'` 目前被 `l3_route_seal` 放行而被 core 拒收。
- **代價**：`research/b0_l3_runner` 因此對 `core` 產生一條新的 import。
  該 import 會被 `route_closure_files()` 的推導看見 ⇒ **seal 的檔案閉包內容會變**。
  落地時須重新量 `sealed_file_set()`，不可沿用本文件 §3 的 45 這個數字。
- **落地順序**：必須在任何 seal 被取得**之前**完成，否則第一枚 seal 綁的是舊閉包。

### 9.3 A-1c · 暫緩；先裁定 `research/b0_l2` 是否屬於 L3 route

**⟨M⟩ 2026-09-02 實測，供該次裁決使用：**

```
sealed_file_set()                      = 45
其中來自 research/b0_l2                = 0
把 research/b0_l2 移出 MODULE_ROOTS 後 = 45，且逐檔相同（identical: True）
```

⇒ **此項今日為 hash-neutral。** 要裁的不是任何現存檔案，而是一扇門：
`research/b0_l2` 留在 `MODULE_ROOTS`（`l3_route_seal.py:69`）代表**將來**任何一條
從 L3 進入 L2 的 import 會**自動**把已封印的回顧線拉進前瞻路由的身分裡，
使 L2 的任何維護都改變 route seal。移出則該 import 會被 `assert_no_producer_is_unbound`
一類的邊界回報而非靜默綁定。

⚠ 因此本項雖「暫緩」，仍**必須在第一枚 seal 之前裁決**——seal 一旦取得，roots 的形狀就固定了。

### 9.4 N-1 · 採 N1-1：日曆權威腿缺失時，route 不可 seal

**這一項決定了其餘所有項目的時程。**

- `ROUTE_SEAL_CONTRACT_STATUS` **維持 `NOT_YET_RATIFIED`**。
  §9.1 與 §9.2 確立的是 seal 的**形式**，不是取得 seal 的**許可**。
  鎖 B（`core:237-242`）**刻意保留**，它現在正是執行本裁決的機制。
- **Month 1（decision 2026-09-30 / execution 2026-10-01）在日曆權威腿補上之前不會發生。**
  U-2 明文「不得事後補記」⇒ 改期本身需要另一次裁決。
- **解除條件**：日曆取得可對帳的權威腿。補法尚未裁定（§5.3 列出至少三個分支），
  其中至少一個會回頭改動 `REQUIRED_DATASET_FLOOR`。
- **附帶要求（本裁決的前提事實）**：§5.1 實測 `build_flat_leaves.py:197-198`
  仍把**每一個** flat family 無條件標成 `TEJ / AUTHORITATIVE`，包含 landing 在
  `~/market_cache` 的 `calendar`。**A-4 尚未落地。**
  在假標籤還在的情況下，連「日曆缺權威腿」這件事本身在 manifest 上都看不出來。
  ⇒ A-4 是本裁決可被稽核的前提，應優先於解除條件處理。

### 9.5 N-2 · 不把每日變動的日曆綁進 route seal；明文揭露 ＋ 由 dataset/leaf lineage 綁定

即 §4 選項 **N2-2 ＋ N2-3 的組合**，明確否決 N2-1。

- **否決 N2-1 的理由（本裁決採用）**：`data/b0/trading_calendar.csv` 每個交易日都變
  （⟨M⟩ `~/market_cache/taiex_daily.parquet` 末筆 2026-09-01，5,575 列，逐日增長）
  ⇒ 綁進 seal 會使 seal 每日失效，與 `closure_kind =
  PRODUCTION_ROUTE_COMPLETE_REPLAYABLE_CLOSURE` 的語意相衝突。
- **採用的兩半**：
  1. **明文揭露**「route seal 只綁程式碼」——揭露必須落在讀得到的地方
     （seal payload 自身的欄位，而非只在 docstring），否則就是 N2-2 自陳的那個代價。
  2. `data/b0/trading_calendar.csv` 與
     `research/d1_price_universe/price_source_contract.json` 改由 **dataset / leaf
     lineage** 承載綁定。
- **代價（N2-3 原列，裁決承受）**：這會動到 `REQUIRED_DATASET_FLOOR`，
  連動 `route_closure` 與 `FLOOR_CAPTURE_REQUIRED_DATASETS`（C-71 的 inventory 是 FIXED 的）。

### 9.6 由本裁決產生的順序約束

```
A-4（誠實的 source_family / authority 標籤）
  → N-2 落地（兩個資料檔改由 leaf lineage 綁定；REQUIRED_DATASET_FLOOR 變動）
    → A-1b 落地（placeholder 單一來源；重新量 sealed_file_set）
      → A-1c 裁決（b0_l2 是否留在 MODULE_ROOTS）
        → A-1a 落地（前綴 ＋ core 第三層改為 payload hash 比對）
          → A-2 floor capture
            → 取 seal ── 仍受 N-1 解除條件擋著
```

⚠ **A-2（floor capture）不應早於 N-2 落地。**
capture record 綁 `aggregate_manifest_payload_sha256`；N-2 會改變 aggregate 的形狀
⇒ 先做的 capture 會被作廢。這一點修正了本文件 §6 原本「A-2 只受 A-1 影響」的說法。
