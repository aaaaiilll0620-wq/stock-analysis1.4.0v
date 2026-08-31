# L3 v1.38 · 第十項 · ZIP 單一 member 契約 · 選項書（2026-08-31）

**狀態：`OPTIONS ONLY — NOT ADJUDICATED`**

本文件之外未變更任何 code、master prereg、data。所有選項全部保留。
**「建議」是建議，不是裁決。**

⚠ **本項不屬於九項選項書**（`docs/L3_v138_AdjudicationOptions_2026-08-31.md`），
不得併入該書的 A-1..A-9 / N-1 序列，**也不得被當成已解決**。
它是 `d9fda6af` 在修 P1-6 的過程中做出的**來源格式契約決定**，
該 commit 自陳：「Recorded, not resolved: the single-member ruling is a contract
decision made during repair and has not been adjudicated; it goes to the options
set rather than standing silently.」本文件就是那個 options set。

## 0 · 撰稿者揭露

未觀測任何 L3 決策、名單、NAV、報酬或基準比較。判準全部是條款層與來源格式層的。

## 1 · 事實

- P1-6 之前：producer（`build_price_panel`）讀 `namelist()[0]`、丟掉其餘 member；
  reader（`l3_readers.read_prices`）要求恰好一個。**同一份雙 member 語料，
  producer 靜默少算、reader 直接拒絕。**
- P1-6 之後（HEAD）：`ARCHIVE_MEMBERS_EXPECTED = 1` 與 `sole_archive_member()`
  （`research/b0_materializer/build_price_panel.py:331-348`），producer 與 reader 一致，
  雙 member 兩端都具名中止。**實作已一致，條款未裁決。**
- 支撐 single-member 的理由（現行碼中所述）：宣告詞彙是 **per archive** ——
  `leg`、`roster_basis`、`declared_properties` 每個 zip 宣告一次，而
  `DECLARED_SPAN_VERIFICATION["does_not_catch"]` 明載 `leg` 與 `roster_basis`
  **無法從列資料導出**。故第二個 member 會在一個沒有任何東西量測過的 basis 下被採納 ——
  例如一份 current-roster 快照繼承 `ROSTER_BASIS_BULK_HISTORICAL`，正是 D1-6 禁止的引用形狀。
- 並存的另一條規則：`build_prices_leaf.observed_archive_span` **串流每一個 member**。
  兩者不衝突 ——「量測涵蓋所有 member，採納恰好一個」。
  該偵測的盲點已記錄：完全落在宣告 span 之內的第二個 member 不會移動任何一端。

## 2 · 選項

**甲 · 維持 single-member 為規範，並補一條明文條款。**
內容即現狀，但寫成「一個宣告 archive 恰含一個 member」的規範條款，
並把理由（宣告詞彙在 archive 層、`leg`/`roster_basis` 不可從列導出）一併入條。
- 後果：無 code 變更。把一個修復副產物升格為有來源的規則。
- 風險：若 TEJ 日後改以多 member 匯出，每次匯出都要先拆檔再宣告，
  而拆檔是我們對來源做的加工 —— 需在條款中明說該加工不改變位元組內容。

**乙 · 允許多 member，宣告詞彙下移到 member 層。**
`leg`、`roster_basis`、`covers`、`declared_properties` 改為每個 member 各自宣告，
`raw_sha256` 仍在 archive 層、另加 per-member 的 size/crc32（`_assert_archive_inventory` 已有）。
- 後果：多 member 匯出可合法採納，且每個 member 的 roster basis 都有具名宣告，
  不會繼承一個沒量測過的 basis。
- 風險：宣告面積變大，且 `covers` 的再量測要改成 per-member；
  是本項唯一需要實作的選項。

**丙 · 允許多 member，沿用 archive 層宣告，member 繼承。**
- **應標示為不可採**：這正是 D1-6 禁止的形狀 —— 一個 member 在它自己未被量測的
  roster basis 下進入決策輸入。它也要求刪掉 reader 現有的中止，
  而那是目前語料中唯一會在這件事上失敗的斷言。

## 3 · 建議

**甲**，並在條文中明寫乙被考慮過而未採的理由是「目前每一份 TEJ 匯出都是單 member，
乙的宣告面積在沒有多 member 語料時是純成本」。
**同時把乙列為預備路徑**：若 TEJ 匯出格式改為多 member，乙是唯一不繼承未量測 basis 的走法，
屆時不必重新設計。丙應明文標示為不可採，以免日後被當成「最省」選項。

## 4 · 本文件未涵蓋

- 拆檔（把多 member 匯出拆成多個單 member archive）是否算對來源的加工，
  以及該加工需要什麼樣的可對帳紀錄。採甲則此問必答。
- `observed_archive_span` 的已知盲點（完全落在宣告 span 內的第二個 member）
  在採乙之後是否仍然存在。
