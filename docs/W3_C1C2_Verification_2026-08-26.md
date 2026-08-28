# W3 · C1+C2 查證（2026-08-26）

純唯讀。未寫入 `data/b0/`、未重建任何 artefact、未改動任何 D 系列 JSON。
本文只記錄量測與結論，不具規範效力。

---

## C1 · D7.6 分母對帳：「5 件 unresolved」與「UNKNOWN 0」兩者都對，時點不同

### 量到的時間線（mtime + 各自宣告的 closure_sha256）

```
2026-08-21 23:25  D7.5   consideration_semantics_source_closure_d7_5      29cc8d4d…
                         22 CASH / 27 STOCK_ONLY / 3 MIXED / 7 UNKNOWN   total 59
2026-08-22 04:10  D7.6a  disappearing_party_edoc_consideration_d7_6       18c4d91e…
                         5384 / 5491 → STOCK_ONLY，UNKNOWN 7 → 5，denominator_closed = false
2026-08-22 16:38  D7.6R  bounded_residual_consideration_d7_6r             1eef1fae…
                         inputs = {d7_6: 18c4d91e}，UNKNOWN 5，denominator_closed = false
2026-08-23 04:45  D7.6b  deep_document_acquisition_d7_6                   c526ee22…
                         inputs = {d7_5: 29cc8d4d}
                         26 CASH / 30 STOCK_ONLY / 3 MIXED / 0 UNKNOWN   total 59
                         exact_stock_denominator_closed = true
```

### 對帳（機械，不是宣稱）

```
22 + 29 + 3 + 5 = 59      D7.6a／D7.6R／D8.0 的分母
26 + 30 + 3 + 0 = 59      D7.6b 的分母
差額 = 那 5 件，逐件有第一手決定性條款（AC8_decisive_clauses，含檔名與頁碼）
    3562  股份轉換 1:1 → 新普科技控股          STOCK_ONLY   202002_3713_B07.pdf p.1
    3582  NT$139.00 現金                        CASH_ONLY    2014_3582_20141024F05.pdf p.12
    5818  每股現金 11.8 元                      CASH_ONLY    2007_5818_20070615F13.doc
    8705  每股現金 41.05 元                     CASH_ONLY    2012_8705_20121002F13.pdf p.2
    6514  NTD53.80 現金                          CASH_ONLY    2024_6514_20240619F13.pdf p.34
→ CASH 22→26（+4）、STOCK_ONLY 29→30（+1）、MIXED 3→3、total 59 不變。完全相符。
```

**結論：兩個數字不矛盾。**「5 件 unresolved」是 2026-08-22 16:38 的事實；
「UNKNOWN 0」是 2026-08-23 04:45 的事實。中間隔著 D7.6b 的深度取件。
JSON 內的中文條款文字經檢查為正常 UTF-8（先前看到的亂碼是 Windows 主控台 cp950 顯示，非資料缺陷）。

### 但查證過程量到三個 lineage 缺陷（皆為新發現）

**L-1 · 下游三份 artefact 凍結在關閉前的分母，且無人回頭修正。**

```
D8.0  extraction_readiness_freeze_d8_0     16:43   TPEX_59_consideration_census UNKNOWN = 5
D8.2b-r2 …_family_coverage_d8_2b_r2        17:55   CONSIDERATION_UNKNOWN = 5
D8.2c …_family_coverage_d8_2c              18:03   UNIQUE_EVENTS CONSIDERATION_UNKNOWN = 5
                                                    EVENT_FAMILY NON_DIAGNOSTIC_CONSIDERATION_UNKNOWN = 8
```

D8.2b-r2 的 applicable population（49 件）實測分類為
`CONFIRMED_STOCK_BEARING 32 / CONFIRMED_NON_STOCK 11 / CONSIDERATION_UNKNOWN 5 /
SCHEMA_OR_EVENT_CLASS_CONFLICT 1`，而那 5 件正是 3562 / 3582 / 5818 / 8705 / 6514。
套用 D7.6b 的結論後應為 **33 / 15 / 0 / 1**。

→ **D8.2c 的 exact offline document audit 是在少一件 stock-bearing 事件的分母上做的。**
這不是措辭問題：3562 由 UNKNOWN 變成 CONFIRMED_STOCK_BEARING，會進入 successor
credit-date 的適用母體。

⚠ 這正是 D8.2b-r1 自己記錄過的失效模式：
「D8.2B cited D7.5's AB9 snapshot … as still current. D7.6 is a LATER stage …
and already resolved 2 of the 7」。**一個 stage 之後同型錯誤再度發生**，
只是這次上游是 D7.6b 而不是 D7.6a。

**L-2 · 關閉分母的那份 artefact 不宣告它取代了誰。**
D7.6b 的 `inputs` 只有 `d7_5_closure_sha256`，沒有 D7.6a(18c4d91e) 也沒有 D7.6R(1eef1fae)。
而 D7.6R 至今沒有任何 superseded 標記，檔內仍寫著
`D7_CONSIDERATION_DISCOVERY = "PERMANENTLY_CLOSED"` 與 `denominator_closed = false`，
且 `budget_enforced.excluded_by_instruction = ["6514"]` —— 6514 後來正是被 D7.6b 解掉的。
任何只讀 D7.6R 的人會得到相反結論。

**L-3 · 命名碰撞。** 兩份內容不同的 artefact 同標 D7.6
（`disappearing_party_edoc_consideration_d7_6` 與 `deep_document_acquisition_d7_6`），
且都宣告 `inputs = d7_5`，形成兩條並行分支而非一條鏈。

### 建議（本 W3 不實作）

1. 出一份 **D7.6-C 對帳記錄**，明文寫「D7.6R 已被 D7.6b 取代」與逐件差額，
   而不是就地改寫 D7.6R（改寫既有 artefact 是本專案禁止的動作）。
2. D8.0 / D8.2b-r2 / D8.2c 依同樣方式補 supersession 記錄，並重算 D8.2 的適用母體
   33 / 15 / 0 / 1；在重算前，任何引用 D8.2c 覆蓋率結論的敘述都要標「分母少一件」。
3. artefact 的 `inputs` 應強制宣告**同 stage 的前一份**，否則分支無法被機械偵測。

---

## C2 · `core/b0_corporate_actions.py` 對 B0.7 seal 的漂移

### 實測（獨立重算，不採信既有敘述）

現行 seal = `c973cff3dfae7003…`（lineage seq 19，CURRENT，master v1.32，
bound commit `271b1106`，`clean_tree = true`）。

```
31 個 normative module vs seal        漂移 1
    core/b0_corporate_actions.py      3c735ebd44d1… → c78b4a956f9f…
spec document sha256                  相符（d9212c8f1a678170…）
seal 的 20 份 derived data artefact    20 / 20 逐位元相符
    （含 data/b0/bonus_share_panel.parquet：mtime 是今天，但內容與 seal 相同）
```

→ 回滾後的狀態確認：**唯一漂移就是 `b0_corporate_actions.py`，來源 commit `cfbc19d1`（B0.8 WIP），
與 v1.33 窗口變更無關。**

### 漂移內容 —— 語義中性，這是量出來的不是說出來的

```
git diff 271b1106..HEAD -- core/b0_corporate_actions.py
    僅刪除 line 839 起的 REQUIRED_FIELDS 定義（10 行）

sealed 版本中 REQUIRED_FIELDS 定義兩次：line 839 與 line 967
    兩個 block 逐字相同（diff 無輸出）
    唯一消費點 line 984 讀 module global → import 後生效的一直是 line 967 那份
    被刪的 839 那份是死碼

AST 比對：module-level 綁定 old 69 → new 68，差異只有多出來的那一次
          REQUIRED_FIELDS 綁定；其餘完全相同
```

→ import 後的模組狀態與 sealed 版本**完全一致**。漂移對行為的影響為零。

### 「如何記入新 seal」—— 現況是：只會被隱式記錄

`scripts/b0_baseline_seal.py` 取新 seal 時：

```
record["normative_module_sha256"]   會帶新的 c78b4a95…（自動，因為是重算的）
record_lineage() 寫入的欄位          seq / baseline_seal_sha256 / master_version /
                                     commit_sha / state / archive_path / supersedes /
                                     l2_opened / historical_hash_recorded /
                                     canonical_body_available
```

**沒有任何欄位記錄「哪些 module 相對前一枚 seal 改變了」、「為什麼」、
「是否已驗證語義中性」。** 前後兩枚 seal body 都不可變且已封存
（`artifacts/baseline_seal/seals/<sha>.json`），所以漂移**可被還原**——
但必須有人自己去 diff 兩份 body 才看得到，文件本身不說。

同時實測：

```
RepoIdentityGuard                只在 seal critical section 內比對（HEAD／clean／module hash
                                 在組裝期間不得移動），不比對「當前 tree vs 現行 seal」
tests/                           無任何測試把 module hash 釘到現行 seal
                                 （test_b0_baseline_seal.py 的 22 個測試全部用臨時 manifest）
```

→ 所以 REJECTED v1.33 §19.10 講的「seal 已失效但無人量測」是**機制性的**，不是疏忽：
**目前沒有任何東西會量它。**

### 建議（本 W3 不實作，屬 B13）

1. 新 seal 的 record 增設 `drift_from_predecessor` 區塊：
   `{module: {from, to, source_commit, semantic_diff: "AST_IDENTICAL" | "CHANGED", note}}`，
   由取 seal 時自動重算前一枚 seal body 得出，**不得手填**。
   本次應記為：`core/b0_corporate_actions.py`，`cfbc19d1`，`AST_IDENTICAL`（僅刪重複定義）。
2. 加一支 `scripts/b0_seal_drift.py`（或一個測試）比對「當前 checkout vs lineage 中 CURRENT 的 seal」，
   讓「目前 checkout 不再符合該 seal」變成可被 CI 量到的事實，而不是要等下一次動工才發現。
3. 措辭沿用裁示更正：不是「舊 seal 已失效」，而是
   **「目前 checkout 不再符合該 seal；該 seal 對新的 opening 不再適用／已 superseded」**。
