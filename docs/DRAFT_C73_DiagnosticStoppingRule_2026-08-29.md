# DRAFT · C-73 · 診斷 replay 的停止規則與 outcome 遮蔽

> **STATUS: DRAFT — NOT NORMATIVE, NOT FROZEN.**
>
> 本檔**不是** Master Preregistration 的一部分。撰寫本檔**未**上版號、
> **未**修改 `research/b0_registry/master_prereg_freeze.json`、
> **未**修改任何 normative module、**未**改動任何 run artefact 的位元組、
> **未**改動任何 diagnostic runner。
>
> 目標版號 **v1.38**、closure 編號 **C-73**。經覆核與使用者批准後，
> 方由 §3 的擬議文字落入 `docs/FrozenB0_MasterPreregistration.md`。
> 若被否決，依 C-67 前例保留為 rejected history，版號與編號**不重用**。
>
> ⚠ **落地順序要求（因 C-72 前例）：** C-72 曾於覆核通過前以 `43943b5f` 落地，
> 判為 `LANDED_BEFORE_REQUIRED_REVIEW + REVISION_REQUIRED`，
> 已由 `git revert`（`54ddb1a`）完整回復。本裁決在覆核通過前**不得**落地，
> 且在落地前**不得**推進 B0.8 replay 超過 seq 67。

---

## §0 · 這份裁決在回答什麼

C-72（v1.37）關閉了 Frozen B0 的**正式 L2** 路徑：once-only observation 已消耗，
`official Frozen B0 L2 replay permitted = false` 自 v1.26 起成立，v1.37 補為
可執行閘門並設在真正的開封邊界。**那條路已經封死，本裁決不觸碰它。**

本裁決處理的是另一件事，而且是目前唯一還在動的關鍵路徑：

> B0.1 → B0.7 的 **retrospective diagnostic replay** lineage 是一個**迭代修復迴圈**。
> 每一輪跑到某期被阻塞、修復、再跑、跑得更遠。這個迴圈目前**沒有任何規則**規定
> 「什麼時候停」與「一次修復可以動什麼」，而它的 per-period 產出**帶著 NAV**。
>
> 一個「修到跑得完為止」的迴圈，加上「每一輪都看得到部分績效」，
> 在形式上與 in-sample 調參不可區分。

C-56/C-57/C-72 治理的是**一次 sealed observation 的會計**。本裁決治理的是
**通往那次 observation 之前的迭代過程本身**。兩者互不取代。

---

## §1 · 事實基礎

### §1.1 · 診斷 lineage 的迭代史

| lineage | run_id | periods_executed | 終局 |
|---|---|---|---|
| B0.1 | `B01DIAG-0121b3261805b826` | 2 | blocked |
| B0.2 | `B02DIAG-bc7ce018a97cfa0f` | 4 | blocked |
| B0.4 | `B04DIAG-d5f34a5164a0e309` | 4 | blocked |
| B0.5 | `B05DIAG-9943d2f7b4adb670` | 45 | blocked |
| B0.6 | `B06DIAG-055dbf317d3f67ac` | 66 | blocked（2020-01，O-B 價格缺口）|
| B0.7 | `B07DIAG-fb6b6b54381ec4f9` | 66 | blocked（seq 67，2020-01，`8913 / holder_side_reorganization_exit`，F-CA-B）|

六輪，每輪一次修復，2 → 4 → 4 → 45 → 66 → 66。B0.8（`research/b0_8_holder_terms`）
已關閉 holder-consideration 分母，預期可通過 seq 67。**這正是本裁決必須先於
該次推進落地的原因。**

### §1.2 · 洩漏的唯一出口

`research/b0_7_diagnostic/run_b0_7_diagnostic.py:784` —— `period_progress.jsonl`
的每一列帶 `port_value`。

範圍必須說準，因為它比直覺窄：

- `nav_series.json`（:844）、`performance.json` 與 gate 判定（:847-862）
  全部在迴圈**之後**。被阻塞的 run **不會**產生其中任何一個。
  `metrics is None` ⇒ `performance_computed=False`。**這部分的設計本來就是對的。**
- 迴圈內的 stdout（:836-838）印的是 `seq / period / positions / ca_applied` 計數，
  **不印 port_value**。
- 正式 L2 runner `research/b0_l2/run_sealed_l2.py:396` 與 `:427`（stdout 印
  `port_value=%.2f`）同樣帶洩漏，但該路徑已由 C-72 封死，**不在本裁決範圍**，
  亦不因本裁決而取得任何可達性。

**所以待修的是 diagnostic runner 的一行。** 洩漏之窄，正是它至今未被發現的原因。

### §1.3 · 已存在的矛盾（本裁決的直接觸發點）

`core/b0_master_prereg.py:709-716`（規範模組，C-57 落地）已就此定性：

> `A NAV that moved is strategy-outcome information — constancy at some other
> value would be too.`

而 `research/b0_7_diagnostic/terminal_provenance/final_result.json` 同時記錄：

```
performance_computed    : false
performance_displayed   : false
preseal_performance_inspection : false
```

同一個 run 的 `period_progress.jsonl` 第 66 列：

```
port_value : 2208939.4237023285      （開倉 2,000,000，+10.4%）
```

**兩者不能同時為真。** 在 condition 2 的判準下，一條移動了的 NAV 序列
就是 strategy-outcome information；而它逐期寫在一個操作者每輪迭代都會讀的檔案裡。

這與 C-72 覆核所判四項缺陷之第四項**同類**：
「『績效未觀測』之事實層與治理層陳述互相矛盾」。C-72 以拆分兩句處理該次；
本案不能靠措辭拆分處理，因為**事實層本身就是假的** —— 績效確實被顯示了。

⚠ **附帶揭露（且是一個地雷）：** `STRATEGY_OUTCOME_ROW_KEYS`
（`core/b0_master_prereg.py:643-649`）**不含** `port_value` / `cash_after` / `nav`。
這三者在 condition 2 是由 `verify_opening_state_restatement` 的**獨立分支**處理
——允許其存在，但要求**恆等於開倉現金**（`:705-716`）。

該函式的執行順序是：先以 `STRATEGY_OUTCOME_ROW_KEYS` 逐 key 攔截並 raise
（`:699-704`），**之後**才進入等值分支。因此**若把 `port_value` 補進該 tuple，
legacy L2 run 的每一列（`port_value: 2000000.0`，等於開倉現金、condition 2 現為真）
會在到達等值分支之前就 raise**，`verify_opening_state_restatement` 對該 run
由 PASS 翻為 FAIL —— C-57 已登錄的 condition 2 機械驗證結果被無聲改寫。

**故本裁決必須另立常數，不得擴充該 tuple。** 這正是
`docs/研究紀律_ResearchDiscipline.md` 所稱「數字看起來很正常但對照組已經換了」
的那一類：補一個看似漏掉的欄位，代價是翻掉另一條裁決的證據。

### §1.4 · 修復不侷限在阻塞期（實測，B0.6 vs B0.7）

C-66 的敘事是「B0.6 於 2020-01 終止，B0.7 修復該處」。逐列比對兩個
`period_progress.jsonl` 的 66 列：

| 量 | 首次分歧 | 值 |
|---|---|---|
| `state_hash` | seq 1（2014-07）| 同期 `port_value` 與 `positions` **完全相同** |
| `post_state_hash` | seq 2（2014-08）| — |
| `port_value` | seq 12（2015-06）| 2,324,658.4594245376 → 2,324,673.362273299（+14.90）|
| `positions` | seq 49（2018-07）| 23 → 22 |

**一筆宣稱修復 2020-01 的變更，實際從 seq 12 就改了經濟軌跡、從 seq 49 改了持倉數。**

這不是指控。C-66 是 state-domain 修復（claim domain 併入 applicability），
軌跡位移是它的**必然**後果，且位移量（seq 12 相對值 +0.00064%）與
「修正一個一直存在的實作缺陷」相符。問題在於：

> **這個位移目前沒有被量測，也沒有被記錄。** 沒有任何 artefact 說得出
> 「B0.7 相對 B0.6 從第幾期開始不同」。一筆真正的調參與 C-66 在現有紀錄下
> **長得一模一樣**。

### §1.5 · `state_hash` 不能作為 no-tuning 判準

seq 1 的 `state_hash` 已經不同（`fe171f82…` vs `7a9c8ad4…`），
而該期 `port_value` 同為 2,000,000.0、`positions` 同為 20 —— 那是開倉狀態，
經濟上完全相同。差異來自 **hash scope 改變**（B0.7 的 state 納入 claim domain，
progress 列亦新增 `claim_only_securities` 欄位）。

**推論：** 「兩個 run 的 state_hash 序列必須相等」是一條會被合法修復
例行性違反的規則，不可作為判準。任何跨 run 的同一性檢查必須建立在
**hash scope 版本**與**經濟可觀測量**之上，不是 raw hash 相等。

---

## §2 · 問題的形狀

迭代迴圈有兩個自由度，**只有關掉第二個才能讓第一個安全**：

1. **什麼時候停？** —— 表面上的問題。
2. **一次修復可以動什麼？** —— 真正的問題。

若任何程式碼變更都可受理，則「修到 141 期跑得完為止」＋「每輪看得到 NAV」
＝ 以 conformance 為藉口的 in-sample 搜尋。反之，若每次修復都必須由
**一列不含 outcome 的 failure record** 唯一決定，則操作者已看過的 NAV
**無處施力** —— 他無法據以在多個可受理修復之間選擇，因為可受理修復只有一個形狀。

**這就是為什麼遮蔽是前置條件而不是主體。** 遮蔽讓「修復必須由失敗紀錄證成」
這句話變得可檢查；沒有遮蔽，失敗紀錄本身就可能帶著 outcome。

---

## §3 · 擬議條文 · §21 診斷 replay 迭代契約（規範性）

```
parent                                   Master v1.37 / C-72
scope                                    B0.n retrospective diagnostic replay lineage
不及於                                    正式 L2 路徑（C-72 已封閉，不因本節取得可達性）
```

### §21.1 · R1 · 兩個 stream（遮蔽）

診斷 runner 的 per-period 產出**必須**拆為兩個 append-only stream：

```
period_progress.jsonl     迭代期間可讀。conformance stream。
  seq, period, as_of, positions, holdings_hash, ca_applied,
  claim_only_securities, state_hash, post_state_hash,
  state_hash_scope_version

outcome_series.jsonl      迭代期間 write-only。outcome stream。
  seq, period, as_of, port_value, cash_after
```

- `outcome_series.jsonl` 由 runner 逐期寫出、其 sha256 計入 `final_result.json`，
  但在 §21.4 的停止條件成立**之前**不得被任何人或任何程式讀取。
- `port_value`、`cash_after`、`nav` **不得**出現在 `period_progress.jsonl`、
  `failure_record.jsonl`、`ca_transition_ledger.jsonl` 或任何 stdout。
- `STRATEGY_OUTCOME_ROW_KEYS` 補入 `port_value`、`cash_after`、`nav`，
  並新增 `assert_stream_blinded(path)` 對上述四個 artefact 逐列強制。

**為何 write-only 而非不寫：** 不寫會使 141/141 完成後需要重跑一次才拿得到 NAV，
而重跑等於引入一個「兩次執行是否同一軌跡」的新問題。逐期寫出但封存，
使完成即可開封，且封存內容的位元組同時是該 run 不可竄改的一部分。

### §21.2 · R2 · 可受理修復（宣告在先）

一次迭代（＝一個新的 B0.n lineage）**必須**在修改任何程式碼**之前**，
以排他建立（O_EXCL）寫出 `repair_claim.json`：

```
cites                   {run_id, seq, error_type | event_id}
                        前一個 run 的 failure_record 中恰好一列
hypothesized_root_cause str   具名的模組與機制。症狀所在不算根因。
falsifier               {file, test}
                        一個在 parent_commit 上必須 FAIL、修復後必須 PASS 的測試
declared_scope          [path, ...]   預期會改動的檔案
parent_commit           sha
declared_at             ISO8601
```

強制四項：

1. `cites` 指向的列必須存在且唯一解析。沒有 failure record ⇒ 沒有可受理的修復；
   一個跑完 141 期的 run 之後**不存在**任何可受理的下一輪迭代。
2. `falsifier` 指名的測試必須在 `parent_commit` 上**實際觀測到失敗**，
   其輸出的 sha256 記入 claim。**修復前不失敗的測試不是 falsifier**，
   而該次變更就不是 conformance repair。
3. `git diff --name-only <parent_commit>..HEAD` ⊆
   `declared_scope` ∪ `tests/**` ∪ `docs/**`。
4. `repair_claim.json` 建立後不可修改。要擴大 `declared_scope`
   只能作廢本次迭代、另立新 claim，且被作廢者必須保留於紀錄。

**自由度是被「宣告在先」關掉的，不是被「只能改哪些檔案」關掉的**
—— 後者以實測否決，見 §4(d)。這是把 `docs/研究紀律_ResearchDiscipline.md` §2
的單發射擊制套用到 conformance repair：假設與範圍必須在看見修復後的軌跡之前凍結。

### §21.3 · R3 · 盲證

被指名的 failure_record 列，以及 `repair_claim.json` 本身，必須通過
§21.1 的 `assert_stream_blinded`。

一次修復若無法**僅憑**該列與該 claim 證成，它就不是 implementation
conformance repair，不論它實際上多麼正確。

⚠ **本條的 outcome key 集合必須是新的常數，不得擴充
`STRATEGY_OUTCOME_ROW_KEYS`。** 見 §1.3 附帶揭露與 §4(e)。

### §21.4 · R4 · 停止條件

迭代迴圈終止於**第一個**滿足下列全部者的 run：

1. `periods_executed == 141`；且
2. `failure_record.jsonl` 零列；且
3. 該 run 的 commit 相對 parent 通過 §21.2 與 §21.3。

此刻、且僅此刻，`outcome_series.jsonl` 得被開封，`nav_series.json`、
`performance.json` 與 gate 判定得被產生。

**停止條件不含任何 outcome 量，也不含任何主觀判斷。**
不是「看起來對了」，不是「已經夠遠了」。

### §21.5 · R5 · 軌跡位移揭露

每個 diagnostic run 的 `final_result.json` **必須**記錄相對 parent run 的位移，
且該計算**不得**讀取 `outcome_series.jsonl`：

```
trajectory_divergence_vs_parent: {
  parent_run_id                  : <run_id>
  state_hash_scope_changed       : bool     # scope version 不同時為 true
  first_positions_divergence_seq : int|null
  first_post_state_hash_divergence_seq : int|null
  compared_prefix_length         : int
}
```

`state_hash_scope_changed == true` 時，`post_state_hash` 的分歧 seq 記錄但
**明文標記為不可解釋**（見 §1.5），`positions` 分歧 seq 仍為有效證據。

B0.6 → B0.7 依本條會記為：
`scope_changed=true, post_state_hash@2, positions@49, holdings_hash=不可用, prefix=66`。

**本條不禁止位移。** 它使一筆宣稱侷限於某期的修復，若把持股從遠早於該期
之處推走，在開封任何 outcome 之前就已可見。

#### §21.5a · `holdings_hash` —— scope-stable 見證（實測後補入）

本條初版只有 `positions` 與 `post_state_hash` 兩個見證。把 R5 套到真實 lineage
之後，該組合被實測證明不足：

> C-66 的經濟軌跡在 **seq 12** 就分歧（`port_value` 2,324,658.46 →
> 2,324,673.36），但 `positions` 計數直到 **seq 49** 才變。
> `post_state_hash` 本會在 seq 2 亮，但該次修復同時擴大了 state domain，
> 依 §1.5 不可讀。**R5 因此對中間那 37 期完全盲目。**

故補入第三個見證：

```
holdings_hash = canonical_sha256({sid: shares})     零股數項目剔除後
```

三項性質：

1. **Scope-stable** —— 只涵蓋 `{sid: shares}`，不隨 state domain 擴張而變。
   這正是 `post_state_hash` 答不了 C-66 的原因。
2. **比 `positions` 更盲，不是更不盲** —— 它是變更偵測器而非資訊通道：
   輸出一個 bit（同／不同），沒有人能從雜湊反推出選股名單；
   而 `positions` 是每期公布一個整數。**加入本欄位使 conformance stream
   的洩漏量下降，不是上升。**
3. **比 `positions` 更細** —— 20 檔換成另外 20 檔，計數不動，雜湊會動。

⚠ **不可回溯補算。** B0.1–B0.7 的 progress 列不帶持股明細，
`holdings_hash` 對既有 run 一律 `available=false`。R5 必須明文區分
「沒有分歧」與「這個見證該 run 沒帶」—— 兩者不是同一個答案。
`divergence_witness` 欄位據此記錄本次實際用的是哪一個。

若 C-66 的 `holdings_hash` 在 seq 12 **不**分歧，那 C-66 的正確描述是
「它改了估值，直到 seq 49 才回饋成決策差異」，而 R5 報 49 就是對的答案。
現有 artefact 答不了這個問題，**B0.8 起才量得到**。

### §21.6 · R6 · 已洩漏前綴的處置

截至本裁決撰寫時，B0.1–B0.7 已執行期數（最遠 66 期，且 seq 67 為 B0.7 之阻塞點）
的 `port_value` **已被操作者觀測**。此為既成事實，不可逆，**不得**以任何方式
主張其未發生。

（事實校準：磁碟上不存在任何超過 66 期的 diagnostic run。「跑到 67 期」指
B0.7 抵達 seq 67 並於該處被 `8913` 阻塞，該期未產生 progress 列。）

處置為**揭露，非淨化**：

- B0.8 及其後每個 diagnostic run 的 `final_result.json` 必須記錄
  `outcome_path_exposure_through_period: 67`（沿用 B0.7 既有的
  `preseal_path_exposure_through_period` 欄位格式與精神）。
- §21.1–§21.5 自 **seq 68 起**強制。
- 該前綴的 outcome 資訊**不因揭露而變得無害**；使其無法施力的是 §21.2，
  不是 §21.6。§21.6 只保證後人讀得到這件事發生過。

### §21.7 · R7 · `positions` 明文保留於 conformance stream

`positions` 弱帶 outcome 資訊（B0.6→B0.7 於 seq 49 由 23 變 22）。
本裁決**明文選擇保留其可見**，理由有二：

1. 它是主要的 conformance 訊號 —— `positions == 0` 直接指出決策層失效，
   而該資訊在阻塞診斷中不可替代。
2. 它是 §21.5 中唯一能表達「決策層死了」（`positions == 0`）的欄位；
   §21.5a 的 `holdings_hash` 在 scope 改變下更可靠也更細，但雜湊
   答不出「持倉為空」與「持倉不同」的差別。

此為**具名的權衡，非疏漏**。`final_result.json` 必須記錄
`positions_visible_in_conformance_stream: true`。

### §21.8 · R8 · 範圍限定

本節僅及於 **B0.n retrospective diagnostic replay**。
它**不**授權、**不**重開、**不**以任何方式影響 Frozen B0 的正式 L2 路徑
（C-72 / §9.6e）。一個通過 §21.4 停止條件的 diagnostic run 仍然是
`RETROSPECTIVE_SUPPORTING_ONLY`，`replaces_frozen_b0_l2 = false`，
`confirmatory_l2 = false`。

---

## §4 · 被否決的三個替代作法

**(a) 「state_hash 序列必須與 parent 相同」** —— §1.5 已證偽。合法修復例行性
改變 hash scope，該規則會在第一次真修復時就失效，然後被繞過或被廢棄。

**(b) 「操作者承諾不看 nav_series.json」** —— 承諾不是機械強制。
本 repo 已有前例：v1.26 起「official Frozen B0 L2 replay permitted = false」
在 `core/` 中**沒有任何對應常數**，直到 v1.37 才補為閘門（C-72 §5.1）。
文字宣告在此 repo 的紀錄中不成立。

**(c) 「跑完 141 期後重跑一次驗確定性」** —— 引入「兩次執行是否同一軌跡」
的新問題，而回答它需要的正是 §1.5 已證偽的 hash 相等。
§21.1 的 write-only 封存以更低成本達成同一目的。

**(d) 「diff 必須 ⊆ failure traceback 的檔案集合」** —— 本草稿的**初版即為此**，
以 B0.6 → B0.7 實測否決。

B0.6 終局 traceback 的 frame set：

```
research/b0_6_diagnostic/run_b0_6_diagnostic.py : 640
core/b0_route.py                                : 381
core/b0_pit_observability.py                    : 274, 247   ← 例外在此拋出
```

C-66 的實際修復（commit `271b1106`）改的是：

```
core/b0_corporate_actions.py   +265      ← 不在 frame set
core/b0_state.py                +70      ← 不在 frame set
core/b0_route.py                 +6
core/b0_pit_observability.py      0      ← 拋出例外者，一行未改
```

**該規則會否決本 lineage 至今最實質的一次修復，而放行的是實際上不該動的檔案。**
症狀位置與根因位置在本專案系統性地不同 —— C-66 自身的 R2 依賴稽核，
正是機械證偽了「CA event transport 失敗」這個由症狀直接外推的假設根因。
一條會誤殺真修復的規則不會被遵守，只會被繞過，然後留下一個沒人相信的閘門。

**(e) 「把 `port_value` 補進 `STRATEGY_OUTCOME_ROW_KEYS`」** —— 見 §1.3。
它會把 legacy L2 run 的 condition 2 由 PASS 翻成 FAIL，
無聲改寫 C-57 已登錄的機械驗證結果。必須另立常數。

---

## §5 · 機械強制（**尚未實作**）

若批准，下列為必要落地項，**皆尚未撰寫**：

| 項目 | 位置 |
|---|---|
| `DIAGNOSTIC_OUTCOME_ROW_KEYS`（**新常數**，不動 `STRATEGY_OUTCOME_ROW_KEYS`）、`assert_stream_blinded()` | 新 normative module `core/b0_diagnostic_iteration.py` |
| `create_repair_claim()` / `read_repair_claim()`（O_EXCL）、`assert_repair_admissible()`（R2/R3）| 同上 |
| `assert_stop_condition()`（R4）、`compute_trajectory_divergence()`（R5）、`holdings_fingerprint()`（R5a）、`assert_outcome_release_permitted()` | 同上 |
| runner 拆 stream、outcome 封存、`final_result` 新欄位 | `research/b0_8_holder_terms/run_b0_8_diagnostic.py`（尚未建立）|
| declaration binding：`diagnostic_streams_are_blinded`、`diagnostic_stop_condition_is_mechanical` | `core/b0_master_prereg.py` |
| 測試（含 negative control：帶 port_value 的 progress 列必須被拒）| `tests/test_b0_c73_diagnostic_stopping_rule.py` |

## §6 · 變更判定

```
runtime semantics changed              false
strategy semantics changed             false
data / state / outcome rules changed   false
sealed artefacts changed               false
run artefact bytes changed             false   （B0.1–B0.7 既有紀錄一律不動）
governance enforcement strengthened    true
```

**B0.1–B0.7 的既有 artefact 位元組不得因本裁決而改動一個 byte**，
包含其中已寫入的 `port_value`。依 C-57 之精神：不刪除、不覆蓋、不改標籤。
本裁決只約束**未來**的 run。

## §7 · 對 B0.8 的即時效果

1. B0.8 replay **不得**推進超過 seq 67，直到本裁決落地。
2. B0.8 的 replay runner **尚未建立**（`research/b0_8_holder_terms/` 下無
   `run_b0_8_diagnostic.py`，僅有 D6/D7/D8 的 holder-terms 取證程式）——
   這是最好的時機：它可以**生下來就是**雙 stream 的，不需要遷移，
   也不會產生「舊 run 要不要回溯遮蔽」的問題（依 §6，不回溯）。
3. B0.7 已抵達之 seq 67 依 §21.6 揭露，不作廢。
