# L3 v1.38 · 覆核復驗與交接（2026-08-31）

**狀態：`COMMITTED — NOTHING SEALED, NOTHING RATIFIED`**

分支 `codex/l3-september-readiness`。未取 seal、未建立 run、未改 prereg 或 `data/`。

⚠ **修訂 2（2026-08-31，回應外部覆核第二輪）。**
本文件初版寫於變更尚未提交時，狀態欄寫 `UNCOMMITTED WORKING TREE`、基底 `8d727bdd`。
外部覆核正確指出**那已是歷史快照，不是當時的工作樹狀態**。
初版所述變更現已提交（見 §6），且本次修訂另有兩項新增，亦見 §6。
**§1 的「十二項中十一項已關」是相對 `93e928e4` 而言的判定，該判定不受本次修訂影響。**

## 0 · 撰稿者揭露

本 session 未觀測任何 L3 決策、名單、NAV、報酬或基準比較。
所有數字均為條款層、涵蓋區間層或測試層的量測。無績效數值。

## 1 · 那份 P1 清單的基底判定

外部覆核提出的 P1/P2 清單，**寫在 `93e928e4`（九項選項書那個 commit）之上，不是新一輪發現**。
判定依據（本 session 實測，逐一比對三個 commit 的同一行號）：

| 清單引用 | 在 `93e928e4` | 在 HEAD `8d727bdd` |
|---|---|---|
| `source_ownership_manifest.py:489` | `def assemble_aggregate(...)` ✔ | ZIP member 錯誤訊息 |
| `l3_route_seal.py:162` | `def assert_route_seal_contract_ratified()` ✔ | `# --- P1-8 ...` 修正說明 |
| `l3_readers.py:116` | `def _verified_path(landing, entry)` ✔ | `# never had a caller ...` |
| `l3_assemble.py:258` | `def assert_both_price_legs_are_declared()` ✔ | `# §2.8.3 · the two halves ...` |

四個行號在 `93e928e4` 全部精準命中所描述的構造，在 HEAD 一個都不對。
十二項裡十一項已由 `d9fda6af`（P1-1..P1-6, P1-9）與 `8d727bdd`（P1-7, P1-8, P2-11）關閉。

**三處「已關但做法與清單建議不同」，交接時需一併轉述：**
- **P1-2**：清單建議把 `assert_landing_dir_matches` 接到一般 reader，實測**接不上**
  （calendar 的 landing 是共用快取根、valuation 是 542 檔中具名取 2）。改寫為 per-landing-group
  檢查，並在碼中明列三個仍抓不到的情況。
- **P1-4**：`covers` / `leg` / `roster_basis` 已進 S-2 比較集合，**`members` 刻意排除** ——
  它由 bytes 導出，比它等於把「builder 改了」報成「來源改了」。四項只給三項，是有理由的否決。
- **P2-11**：單檔原子發佈與**單一 aggregate barrier**（`run_l3_prospective.py:1876`）兩半都已落地，
  清單收尾段「O_EXCL 只防覆寫、無交易式 publication」對 HEAD 已不成立。

## 2 · P1-7 / P1-8 / P2-11 的 mutation 復驗

`8d727bdd` 自陳作者被 usage limit 切斷、無 author-supplied mutation evidence，
只補兩個 spot mutation，並要求下一次覆核以較薄的標準看待。故本 session 重跑。

基線：321 passed / 16 skipped（七個目標測試檔）。

| # | Mutation | 類型 | 結果 |
|---|---|---|---|
| M1 | `load_route_seal` 刪 ratification | 刪除 | 紅 3 |
| M2 | runner 執行邊界刪 ratification | 刪除 | 紅 2 |
| M3 | 保留呼叫且仍為第一敘述，吞掉 refusal | 抽效力 | 紅 1 |
| M4 | 新增一個不問閘門的 seal 讀取門 | 新增 | **綠** |
| M5 | 刪 gate 的 floor 交叉檢查 | 刪除 | 紅 1（僅 AST 存在性） |
| M6 | 保留呼叫，改拿 seal 自己的 floor 比自己 | 抽效力 | **綠** |
| M7 | 兩個 floor 呼叫點都自比 | 抽效力 | **綠** |
| M8b | 還原成 claim-then-write 且不清理半成品 | 還原缺陷 | 紅 2 |
| M9 | no-replace rename 換成會覆寫的 rename | 抽效力 | **綠** |

**結論：**
- **P1-8 站得住**，且證據比自陳的強（M3 證明守住它的是斷言訊息內容的行為測試，不只 AST 排序）。
  **但 `8d727bdd` 的一句宣稱不成立**：`RATIFICATION_GATED_BOUNDARIES`
  （`l3_route_seal.py:210`）是手維護的字面 tuple，M4 加進一個新的未設防讀取門，全綠。
  「a future unguarded boundary fails too」應改為「列舉是手動維護的」。
- **P1-7 原本不可簽**：整條 binding 只有一個 AST 存在性斷言在守，M6/M7 保留呼叫、
  把引數換成 seal 自己的 floor（等同無條件接受任何 `--lineage-price-floor`），全綠。
- **P2-11 原本只有一半**：真正的 claim-then-write 會紅，但把 no-replace rename
  換成會覆寫的版本全綠 —— 而碼中自陳「早期 lexists 檢查不是保證，rename 才是」。

## 3 · 補上的三個測試（本 session 唯一的 code 變更）

| 測試 | 檔案 | 殺掉 |
|---|---|---|
| `test_the_gate_passes_the_CALLERS_floor_to_the_cross_check` | `tests/test_b0_l3_route_seal.py` | M6, M7 |
| `test_a_receipt_binding_refuses_a_floor_the_seal_did_not_capture` | 同上 | M7 |
| `test_the_publication_refuses_a_final_path_that_appeared_mid_write` | `tests/test_b0_l3_lineage_capture.py` | M9 |

復驗：M6 → 紅 1、M7 → 紅 2、M9 → 紅 1。三個先前全綠的 mutation 全數被抓。
全域：**324 passed / 16 skipped**（基線 321 + 新增 3）。

**一個必須一併交接的事實**：樹中**沒有任何測試能模擬「契約已批准」**，
每個 gate 測試斷言的都是未批准時的拒絕；`assert_route_execution_admissible`
在抵達 floor 交叉檢查前就先因 ratification 中止。
**所以 P1-7 只有 AST 測試不是疏漏，是 fail-closed 的必然結果。** 因此：
- gate 那一側釘的是**接線**（交叉檢查的第二個引數必須是 gate 自己的 `lineage_price_floor`
  參數，不得是從 seal 讀回的值）—— A-1 批准前這是能拿到的最強形式；
- 真正的行為測試放在 `route_seal_binding`：以既有 `_hand_crafted_seal` fixture 加模擬批准即可抵達，
  跑的是同一個交叉檢查、同兩個值。
- **A-1 批准後**，gate 那一側應補上真正的端對端行為測試，屆時 AST 接線測試可保留為輔。

## 4 · Month 1 價格阻塞

見 `docs/L3_v138_Month1PriceBlocker_AdjudicationOptions_2026-08-31.md`（本 session 新增，未提交）。

重點：**這不是 `股價0817-0828.zip` 一個 archive 的問題。** 權威語料止於 2026-08-28，
Month 1 決策日 2026-09-30，prices leaf 只有兩條腿、**無 live 腿** ——
撤不撤回都缺價；任何補足用的新 TEJ 匯出都會落在 `b0_price_universe_20260817`
的 `date_max`（2026-08-17）之外，撞同一面牆。真正待裁的是
「語料每月延伸 vs sealed contract 與 `data/b0/` 由 R-W1-1 凍結」這個結構。
四個選項與建議（丙立規則 + 乙本期執行一次；丁實質不可採）在該文件內。

## 5 · Case B 規模量測與一次定性修正

`build_rows` 的 `i = ss.pos.get(as_of); if i is None: continue`
（`l3_assemble.py:631-633`）會把在 as_of 沒有價格列的證券**靜默丟棄**。

合成量測（本 session）確認行為：全面缺席回傳 0 列（隨後由 `_assemble` 的
`if not rows:` 中止，訊息不指名成因）；部分缺席靜默丟棄，不 raise、不警告、不計數。

**規模量測（本 session，真實宣告語料，3,488,213 列 / 2,050 檔 / 92 個月末）：**
每期丟棄 median 1、max 4；其中前 20 session 完整（adv20 本可算出、屬真候選）者
median 0、max 1、**7.7 年合計 9 檔**；92 個月末有 28 個為零。丟棄率約 0.05%。

⚠ **定性修正**：本 session 稍早把它判為「新的 P1 候選，比 S-8 嚴重」。
**規模量測推翻了這個定性。** 機制為真（沒有任何欄位記錄它），但這是**記帳缺口**，
不是母體污染，不應與 S-8 或 A-5 並列。建議降級為「補一個計數欄位，
與涵蓋起點已有的 `observed_price_coverage_floor` / `floor_disposition` /
`spell_starts_at_price_coverage_floor` 三欄對稱」的小項。

## 6 · 交接清單

**已提交（`work/l3_formal_v138`，分支 `codex/l3-september-readiness`，未 push）：**

| commit | 內容 |
|---|---|
| `3742ad08` | 三個接線測試，+91 行，全在 `tests/`。production code 未改 |
| `b52c5660` | Month 1 選項書 + 本交接文件（初版） |
| 本次修訂 | P1-8 註解修正（`l3_route_seal.py`）、第十項選項書、本文件修訂 2 |

**簽字建議（含外部覆核第二輪的 disposition）：**
- P1-8 **可簽** —— 文案已於本次修訂落地，見 §7。
- P1-7、P2-11 **在目前 fail-closed 範圍內可簽**（`3742ad08` 的三個測試）；
  **A-1 批准後補真正的端對端行為測試仍是明確待還事項**，AST 接線測試屆時保留為輔。
- Month 1 **維持阻塞**：不得回溯決策日期，不得建立 production evidence。
- 第十項（single-member ZIP）**維持 `OPTIONS ONLY`**，見下。

**仍然開著：**
- 九項裁決本身（A-1..A-9, N-1）—— 選項書仍是 `OPTIONS ONLY`。
  外部覆核的建議與選項書自身建議在九項上一致，唯一分歧 A-9 丁→乙已驗證為正確
  （釋放時點經 `_state_hash` 進入 COMPARED 的 `portfolio_side_sha256`，丁不可採）。
- Month 1 阻塞的裁決（含 R-W1-1 具名例外）。
- **第十項待裁**：single-member ZIP。選項書已補：
  `docs/L3_v138_SingleMemberArchive_AdjudicationOptions_2026-08-31.md`。
  它是 `d9fda6af` 修復過程中做出的**來源格式契約決定**，producer 與 reader 現已一致
  （`build_price_panel.py:331-348`），但**實作一致不等於條款已裁**。
  不得併入九項序列，也不得標成已解決。
- N-2 / N-3 / N-5 / S-9 / 真實九族 intent→execute phase-invariance。
- Case B 的計數欄位（已降級，見 §5）。

## 7 · 外部覆核第二輪的回應（2026-08-31）

**接受並已落地：**
1. **metadata 過期** —— 已於本次修訂改正，並保留初版狀態作為歷史說明（見文首）。
2. **P1-8 文案** —— 需要修正的那句
   （"the test that pins it enumerates the boundaries rather than naming one, so a
   future unguarded boundary fails too"）**在 `8d727bdd` 的 commit message 裡，
   不在程式碼裡**，而 commit message 不可改。故改在樹裡對應處說明：
   `research/b0_l3_runner/l3_route_seal.py` 的 `RATIFICATION_GATED_BOUNDARIES`
   上方現已明寫該半句不成立、量測依據、以及為何仍維持手動維護
   （導出式列舉的錯誤方向是**默許**一個邊界而非失敗，風險更大）。
3. **第十項** —— 已建立獨立選項書，維持 `OPTIONS ONLY`，並在 §6 標明不得併入九項序列。

**測試結果的差異，據實記錄而非彌合：**

覆核方回報 route-seal 單檔 40 passed / 1 skipped / **7 failures，全為 `PermissionError`**
（Windows 禁止寫入 target tree 或 pytest temp），並表示七檔合併掃描過久、
**無法獨立重現本文件 §3 的 `324 passed / 16 skipped`**。

本文件的 324/16 是撰稿環境的量測，**至此仍未被獨立重現**，應如此看待。

而那些 `PermissionError` **不是純環境噪音，它指向一個真實的測試衛生缺陷**：

    tests/test_b0_l3_route_seal.py:95  test_the_producer_set_is_read_from_disk_not_hand_listed
    → 寫入 research/b0_materializer/build_zzz_probe_leaf.py（REPO 樹內），
      再於 finally 刪除。

在**這個**專案裡這不是小事：該路徑落在 `sealed_file_set()` 量測的 route closure 之內，
而 `assert_seal_binds_current_route` 對「閉包現在觸及、但 seal 從未綁定的檔案」是會拒絕的。
`finally` 擋得住例外，擋不住 SIGKILL、斷電或沙箱拒絕刪除 ——
**一次被中斷的測試執行會在樹裡留下一個多出來的 producer 檔案，使 seal 失效。**

⚠ **本項僅記錄，未修。** 它不在覆核方列出的 disposition 內，
且修法（把 producer glob 根目錄 monkeypatch 到 tmp_path，不寫 REPO）
是測試行為的變更，應由裁決者決定是否納入，而非在交接途中順手改掉。
