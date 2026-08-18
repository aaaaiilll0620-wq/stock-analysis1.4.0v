# Claude 任務：推薦投組系統 V2 · Phase 0 第二輪修正

## 範圍

只修改：

`docs/規劃_推薦投組系統V2.md`

不得修改本指令檔、`Claude_推薦投組系統V2_Phase0.md`、`GPT answer.md` 或任何其他檔案；不得執行 Phase 1、資料盤點、回測、績效、OOS、Gate、stage、commit、push。

注意：上一輪 `Claude_推薦投組系統V2_Phase0.md` 原本是任務文件，後來被覆寫為回覆內容。兩檔皆為 untracked，因此 `git status` 無法證明它沒有被修改。本輪不要再把回覆寫入任何任務檔；完成摘要只在對話中回覆。

## 使用者正式確認（2026-08-05）

使用者已明確採納 D1–D5，可在 Decision Register 保留為正式裁定，日期改為 2026-08-05：

- D1：舊 A+overlay 的 MDD `-40%` 只屬舊研究，不回溯修改。
- D2：V2 正式合格門檻為 MDD 不得低於 `-30%`。
- D3：官方產業 PIT 化為 Phase 1 blocker；未解決前不得產生依賴產業成員／集中度的正式歷史結論。
- D4：`Z1-*`、`E0/E1/E1-R` 是全新研究模組；可重用資料工具，不繼承舊 backtest 停損語義。
- D5：L1 與 L2–L5 可並行做架構／資料／介面工作；L2–L5 正式績效驗證須等五維度本體與七層介面凍結。

U1–U3 仍保持 UNRESOLVED，不得自行決定數值。

## 必修 1：修正主線資料流

目前的 `L1 → L3 → L4 → L5 → L7` 仍錯誤。L4 必須是整合器，在同一決策時點統整候選進場、既有部位退出與旁路限制：

```text
L1 選股資格／排序 → L3 原始進場候選 ┐
L5 既有部位的退出／續抱提案         ├→ L4 投組統整 → L7 呈現
L2 族群限制＋L6 市場／事件限制       ┘
```

- L4 輸出最終目標持股、交易動作、權重與現金。
- L5 不得排在 L4 之後才決定退出。
- `Z1-R` 仍由 L3 產生。
- L5 只產生既有部位的 `hold/exit/pending_exit` 等提案。
- `E1-R` 是實驗政策組合名稱（`E1 + Z1-R`），不是 L5 輸出的第三種訊號或狀態轉移器。清理 §2、§6.2、§6.3、§8 所有殘留矛盾。

## 必修 2：拆開 L6 的兩種權限

保留七層名稱，但把 L6 明確拆成兩個互不越權的子介面：

### L6a StockEventAux

- 輸入：具 PIT 時間戳的個股重大事件與其嚴重度。
- 只允許向 L5 發送個股 `forced_exit_flag` 或 `block_reentry_flag`。
- 事件等級、來源、可用時間與失敗語義仍為 CANDIDATE／UNRESOLVED，不得自行定門檻。

### L6b MarketRiskOverlay

- 輸入：市場狀態資料。
- 只能向 L4輸出總曝險上限、現金下限、新倉／加碼限制。
- 不得向 L5 發送個股退出旗標，不得改寫 L1、L3、TrendState 或 PositionState。

異常價格、初始停損、trailing、跳空與 pending exit 屬 L5，不屬於 L6b。同步修正 §2、§3.1、§6、§9與Decision Register。

## 必修 3：避免 L2 與 L1 循環污染

族群狀態的 breadth、RS、新高比例、成交、波動、相關性等，應以當期 PIT 可交易母體及 PIT 群組成員計算，不以 L1 Top K／排名結果作為族群狀態母體。

- L2 可讀取 L1 的「資料資格／可交易資格」介面，但不得以 L1 高分股集合定義族群熱度。
- L1 排名只在 L4 用來挑選同族群內個股。
- 若未來要研究「高分股在族群內的擴散」，須列為另一個獨立候選輸入，不得默認混入基礎 GroupState。

## 必修 4：區分 VALID_FAIL 與 INVALID

修正 Phase 4–6 的 fail-closed 語義：

### VALID_FAIL

- 實作、資料血緣、PIT及第二實作對帳全部有效，但未達凍結績效門檻。
- 這是有效的否定結論，必須保存並停止該候選。
- 不得寫成「結果作廢」、不得回到 Phase 2 後使用同一 Validation／walk-forward 重新測試。

### INVALID

- 資料洩漏、非 PIT、runner 與凍結規格不符、第二實作對帳失敗、必要欄位缺失等完整性問題。
- 此時不得下科學結論，結果無效；依根因退回 Phase 1、2或3。
- 修正後仍不得任意重用已揭露的 Validation／walk-forward；後續處置必須在預註冊中事先定義。

Validation 與 walk-forward 都要套用以上區分。

## 必修 5：補上 Train → Validation 的封存點

Phase 2 不一定能同時凍結「搜尋空間」與「最後選中的參數」。請明確支援兩種合法路徑：

1. **Policy-fixed**：Phase 2 直接凍結唯一參數，Train 只做診斷。
2. **Train-selected**：Phase 2 凍結有限候選 grid、搜尋數、選擇準則、tie rule、seed 與樣本切點；Phase 4 只能依該規則在 Train 選出唯一規格。

Train-selected 路徑必須在開啟 Validation 前產生不可變的 `TRAIN_SELECTION_MANIFEST`，至少記錄：

- 選中規格與全部參數；
- 候選全集與選擇規則；
- Train資料截止日；
- 程式／設定／資料快照 hash；
- 產生時間與成功／失敗狀態。

Validation preflight 必須檢查 manifest 完整且時間早於 Validation 首次讀取；缺失即 fail-closed。Phase 3 runner/tests需精確實作 Phase 2 的唯一參數，或完整 grid＋決定性選擇規則，不能自行補值。

## 必修 6：PIT與題材標籤

- D3 的 PIT blocker 不只涵蓋官方產業表，也要說明人工／半人工題材標籤若參與歷史判定，必須有 `effective_from/effective_to/as_of` 或版本化快照。
- 今日整理出的題材名單不得回填歷史全期。
- 資料驅動相關群組必須只使用決策日前資料；窗長、聚類法、重估頻率、最小樣本與門檻維持 UNRESOLVED。
- 「高度相關股票視為一個證據單位」改成待預註冊的群聚推論候選（例如 cluster-aware inference），不得在 Phase 0 直接宣稱簡單合併成一筆觀測就是正確方法。

## 完成前自查

1. D1–D5日期為使用者確認的 `2026-08-05`，不是Codex單方裁定。
2. U1–U3未被關閉，新增未決項也完整進UNRESOLVED。
3. L4是唯一最終投組統整器；L5不再位於L4之後。
4. 市場狀態不能觸發個股退出；只有PIT個股重大事件可發 forced-exit旗標。
5. E1-R只是一個政策組合標籤。
6. Validation／walk-forward未達門檻記為VALID_FAIL，不是INVALID或「作廢」。
7. Train-selected路徑在Validation前有不可變manifest與preflight。
8. 本輪只修改`docs/規劃_推薦投組系統V2.md`，不執行任何Phase 1工作。

## 回覆格式

只在對話中回覆：

- 修改章節與行號；
- 上述8項自查的PASS／FAIL表；
- 新增或仍存在的UNRESOLVED；
- `git status --short`，並明確承認untracked檔案僅靠status無法證明未被修改，因此另列本輪實際寫入路徑。

不要重貼全文。
