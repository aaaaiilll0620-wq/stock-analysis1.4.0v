# L3 v1.38 · Month 1 價格語料阻塞 · 選項書（2026-08-31）

**狀態：`OPTIONS ONLY — NOT ADJUDICATED`**

本文件之外未變更任何 code、master prereg、data；未建立 run、未封存、未取 seal、未 stage。
所有選項全部保留，不刪除。**「建議」是建議，不是裁決。**

前置：`docs/L3_v138_AdjudicationOptions_2026-08-31.md`（九項選項書）、
`d9fda6af` 的 P1-9（S-8 allowance 改發給具名 consumer）。本項是 P1-9 修復後掉出來、
當時明文記為 **FINDING, not fixed** 的那一個。

## 0 · 撰稿者揭露

本文件的撰稿者本輪未觀測任何 L3 決策、名單、NAV、報酬或基準比較。
下列判準全部是條款層與涵蓋區間層的，未引用任何績效數值。

## 1 · 事實

**本 session 讀碼所得：**

- 權威價格語料由 `build_prices_leaf.CONSUMED_ARCHIVE_DECLARATIONS` 宣告，共三個 2019+ archive，
  最後一個是 `股價0817-0828.zip`，`covers = (2026-08-18, 2026-08-28)`，
  `roster_basis = ROSTER_BASIS_CURRENT_SNAPSHOT`。加上 pre-2019 parquet 腿，
  **權威語料在 2026-08-28 結束**（撤回該 archive 則為 2026-08-17）。
- sealed contract `b0_price_universe_20260817` 的 `date_max` 是 2026-08-17，
  故該 archive 站在 D-1 已驗證、B-21 已封存的範圍之外，靠 allowance 存在。
- allowance 條件詞彙是封閉的，只有一項：`PANEL_END_IS_STRICTLY_BEFORE_THE_ARCHIVES_FIRST_COVERED_SESSION`。
  它是**關於某個 reader 的讀取終點**的述語。
- L2 panel 的讀取終點可在 leaf-build 時導出（frozen `window_end` 之後第一個 session，2026-04-01），
  L3 route 的不能（§19.2 的執行 session，屬於本模組不知道的 run）。
- 因此 allowance 只發給 `L2_COMPOSED_PRICE_PANEL`，並把 `L3_PROSPECTIVE_ROUTE` 具名列為未授予；
  `run_l3_prospective.assert_declared_sources_admit_this_route`（:864，於 :1278 被呼叫）讀到自己的名字即中止。
- 且這不是本期意外：`_assert_intent_claim_is_today` 強制 prospective 決策日為今日，
  §19.2 把讀取終點放在其後的執行 session，故 `read_end < covers[0]` 在 L3 路線上
  **對任何已發生 session 的 archive 永久不可滿足**。

## 2 · 這不是這一個 archive 的問題

Month 1 的決策日是 2026-09-30、執行 session 2026-10-01。權威語料止於 2026-08-28。
**撤不撤回這個 archive，Month 1 都缺 2026-08-29 之後的權威價格。**
prices leaf 只有兩條腿（pre-2019 parquet、2019+ archive），**沒有 live 腿**；
補足到決策日一定是一次新的 TEJ 匯出，而任何這樣的匯出都會落在
`b0_price_universe_20260817` 的 `date_max` 之外 —— 撞上完全相同的那面牆。

⇒ 真正待裁的不是「這個 zip 怎麼辦」，而是
**「權威語料每月延伸一次，而 sealed contract 與 `data/b0/` 由 R-W1-1 凍結」這個結構怎麼辦。**

## 3 · 選項

**甲 · 撤回 `股價0817-0828.zip` 的宣告。**
從 `CONSUMED_ARCHIVE_DECLARATIONS` 移除，L3 的 refusal 隨之消失（不再有未授予的 consumer）。
- 後果：S-8 這一個閘門過。
- 代價：丟掉 9 個 session 的真實資料，且 **Month 1 仍然無價可標**。它把停止點從一個
  有閘門、會具名中止的地方，移到一個**目前可能沒有閘門**的地方（見 §5）。

**乙 · 重組語料並重新註冊 price source contract，涵蓋到決策日。**
- 後果：一次解決本 archive 與所有未來月度匯出，roster basis 問題一併重驗。
- 代價：regenerate `data/b0/price_2019plus_new.parquet` 與 D-1 稽核產物，
  而 `data/b0/` 由 **R-W1-1 凍結** ⇒ 需要先解凍或裁決一個具名例外。這是本選項的全部困難。

**丙 · 擴充 allowance 條件詞彙，讓 L3 有可能被授予。**
clip 條件對 L3 永久不可滿足，所以要的是一個**不是 clip** 的條件。候選：
`ARCHIVE_ROSTER_BASIS_IS_BULK_HISTORICAL` —— archive 若非 snapshot 衍生，
其超出 sealed contract 的部分可由 L3 讀取。
- 後果：未來以 bulk historical 匯出的正常月度 archive 可合法進入 L3，不必每月重註冊。
- **對本 archive 無效**：它正是 `ROSTER_BASIS_CURRENT_SNAPSHOT`。丙解未來、不解現在。
- 風險：它放寬的是「sealed contract 之外的資料不得進決策輸入」這條線。放寬哪一半必須明文寫出來：
  放寬的是「範圍外」，不是「未驗證 roster」。

**丁 · 把 Month 1 的決策日改到語料涵蓋得到的日期（as_of ≤ 2026-08-28）。**
- **實質不可採，應如此標示**：`_assert_intent_claim_is_today` 要求 prospective intent 的
  決策日必須是今日。要走丁就得改該規則，而改它等於允許回溯宣告 intent ——
  那是這條 lineage 存在理由的反面。

## 4 · 建議

**丙（立規則）+ 乙（本期執行一次重註冊）。**
乙是正解但被 R-W1-1 擋著，所以 R-W1-1 的具名例外本身要單獨裁；
丙是唯一讓這條路線長期可持續、不必每月重註冊的機制修改。
**甲單獨採用不解決 Month 1**，只是把停止點移到一個閘門狀態未經量測的地方。
丁應明文標示為實質不可採，以免被當成「最省」選項。

## 5 · 量測結果（2026-08-31，本 session 合成量測）

方法：以真實的 `l3_assemble.build_series` / `build_rows`，日曆涵蓋 2026-08-03 .. 2026-10-02，
`as_of = 2026-09-30`，價格語料止於 2026-08-28。未動 code、未跑 run。

**Case A · 全面缺席**（三檔全部止於 2026-08-28）：`build_rows` **不 raise**，回傳 0 列。
`_assemble` 隨後在 `if not rows:` 中止，訊息是
`abort: 2026-09 produced no market-side state`。
⇒ **它會停 —— 但訊息不指名價格語料、不指名涵蓋終點、也不說來源比決策日早了一個月。**

**Case B · 部分缺席**（兩檔涵蓋到 `as_of`、一檔止於 2026-08-28）：回傳 2 列，
第三檔**被靜默丟棄**：不 raise、不警告、不計數。
成因是 `build_rows` 的 `i = ss.pos.get(as_of)` / `if i is None: continue`
（`research/b0_l3/l3_assemble.py:631-633`）。

### 這對選項的意義

- **對「甲」**：撤回 archive 後 Month 1 **不會**靜默決策，它會停。
  但停在一個不指名成因的訊息上，操作者無法從那句話知道原因是語料早結束一個月。
  形狀與 P1-5 修掉的那個同類（缺席落進通用錯誤），只是換一個維度。
  甲因此不是「危險」，而是「停得沒有資訊」。
- **與甲乙丙丁都無關的既有缺口**：組裝對涵蓋**起點**記錄三個欄位
  （`observed_price_coverage_floor`、`floor_disposition`、`spell_starts_at_price_coverage_floor`），
  對涵蓋**終點**一個都沒有。部分缺席因此無法與「母體本來就這麼大」區分 ——
  正是研究紀律 §1 列為五次結論作廢成因的「母體有沒有被靜默砍過」。
  ⚠ 初判為「獨立 P1 候選」，但**該定性已被下面的規模量測推翻**，見 §5.1。

## 5.1 · Case B 的規模（2026-08-31 實測，真實宣告語料）

方法：以 `build_price_panel.zip_leg`（與 `l3_readers.read_prices` 的 archive 分支逐欄同一套解析：
同樣的 UTF-16/TAB、同樣的欄位、同樣只對 date 做 `notna`）讀三個已宣告 archive，
驗章通過，3,488,213 列 / 2,050 檔 / 1,859 個 session，2019-01-02 .. 2026-08-28。
對 2019-01 .. 2026-08 的每個月末 session 取：
`alive` = 前 20 個 session 內有列的證券；`present` = 在 as_of 當天有列的證券；
`dropped = alive - present`（即 `build_rows` 會靜默丟掉的那些）。

| 統計（92 個月末） | min | median | max | 合計 |
|---|---|---|---|---|
| 每期靜默丟棄數 | 0 | **1** | **4** | 108 |
| 其中前 20 session 完整者（adv20 本可算出，屬真候選） | 0 | **0** | **1** | **9** |

92 個月末裡有 28 個是零。母體約 1,800–1,960 檔，故丟棄率約 **0.05%**。

⇒ **定性修正：機制為真（沒有任何欄位記錄它），但規模不是母體被砍。**
7.7 年裡真正可能影響候選集的合計 9 檔。這是**記帳缺口**，不是母體污染，
**不應與 S-8 或 A-5 並列**，也不足以單獨成為 P1。
建議降級為「補一個計數欄位」的小項，與涵蓋起點已有的三個欄位對稱即可。

⚠ 界限：本量測只涵蓋 2019+ archive 腿與月末決策日；§4.2 資格會再篩掉其中一部分，
故 9 是**影響決策的上界**，不是實際影響數。

## 6 · 仍待量測

1. 若採乙：D-1 稽核與 B-21 seal 需重跑的確切範圍。
2. 若採丙：新條件是否與 §7 / A-8 的再裁決條款相容。
3. §5 的 Case B 在真實九族語料上的規模（有多少證券在任一決策日沒有 `as_of` 列）。
