# DRAFT · CA-1 · 無除權旗標的資本額變動判為 NOT_APPLICABLE

> **STATUS: DRAFT — NOT NORMATIVE, NOT FROZEN.**
>
> 本檔**不是** Master Preregistration 的一部分。撰寫本檔**未**上版號、
> **未**修改 `research/b0_registry/master_prereg_freeze.json`、
> **未**修改任何 normative module（實作以 patch 形式附呈，工作樹已還原乾淨）、
> **未**改動任何 run artefact 的位元組、**未**開任何 run。
>
> 目標版號 **v1.38**、closure 編號 **CA-1**。經覆核與使用者批准後，
> 方由 §6 的擬議文字落入 `docs/FrozenB0_MasterPreregistration.md`。
> 若被否決，依 C-67 前例保留為 rejected history，版號與編號**不重用**。
>
> **規則本體已凍結於** `docs/預註冊_配股不可重建事件處置_2026-09-02.md` §2。
> 本檔不修改規則，只交付實作、測試、影響量測與條文修訂草稿。
> 實作與該 §2 若有任何一處不符，以 §2 為準，並回報而非改規則。

---

## §0 · 這份裁決在回答什麼

`stock_dividend_pit.csv` 有 851 筆（141 期窗口內 312 筆）事件，
其 reason 為 `capitalisation recorded without an ex-right flag`。
它們目前是 `NOT_RECONSTRUCTIBLE`，因此 B0 只要在事件日持有該證券，
§6.1.12 就會中止整個 run。

問題不是「怎麼把缺的補回來」，而是**這裡到底缺了什麼**。
CA-1 的主張是：**什麼都沒缺**。這些不是持股人事件，
`NOT_RECONSTRUCTIBLE` 從一開始就是分類錯置。

§2.4 的三態詞彙已經有正確的那一格：

> `NOT_APPLICABLE` 事件存在，但不改變「我們的」股數/現金/證券身分

---

## §1 · 事實基礎（⟨M⟩ 本 session 於主線 `25ba7440` 實測）

### §1.1 · 資料指紋

```
data/b0/stock_dividend_pit.csv
  sha256 = 783d7cc2785f9faeff637529e66138e69c70f9c3a1a4df1001a1b19b7a50a0ec
  列數   = 9,120
data/b0/corporate_actions_ledger.csv
  sha256 = c838961f93599f9e63c9c98a556f3e721cc5994b53e89d109e17f625a9f7d6f2
  列數   = 46,433
```

### §1.2 · 母體

```
NOT_RECONSTRUCTIBLE 全庫 1,011 = 851 (CA-1) + 160 (CA-2)
141 期窗口內              377 = 312 (CA-1) +  65 (CA-2)
```

與預註冊 §1 的表逐格相符。

### §1.3 · 三條證據，逐條複驗

| # | 主張 | 本 session 實測 |
|---|---|---|
| 1 | 官方零筆 | 312 筆全部在 `artifacts/stock_dividend_multiplier_audit/coverage.csv` 中有列（**312/312**，class 全部為 `LEDGER_NOT_RECONSTRUCTIBLE`），其中 `bonus_per_1000 > 0` 者 = **0** |
| 2 | 全部帶配發數量 | 312 筆 `distribution_ratio_or_new_shares` 非空 = **312**，且**全部為正數** |
| 3 | 程式本來就同意 | `core/b0_bonus_share_source.py:100-107` `FORBIDDEN_MULTIPLIER_SOURCES` 明列 `paid_capital_increase_shares` 與 `employee_bonus_shares`；`:126` 為其守衛 |

證據 1 的採集完整性：`coverage_report.txt` 記 `unresolved transport failures: 0`；
官方除權日 22,263 筆中 22,060 筆（99.09%）是凍結日曆的交易日。

⚠ **一處對帳揭露：** `coverage.csv` 的 `LEDGER_NOT_RECONSTRUCTIBLE` 是 **422** 筆，
不是 377。差額 45 筆的除權日落在 **2013-07-08 ~ 2014-07-24**，
即 coverage 的採集窗口早於 141 期窗口起點 2014-07-31。兩個數字口徑不同，不是矛盾。

### §1.4 · 三條證據合起來說的話

新股確實發行了（證據 2），但官方除權公告對這 312 筆**沒有任何一筆**登記正配股率
（證據 1）。若這些股票真按持股比例配給既有股東，官方公告會有比例——
那正是 C-51 已裁定的 canonical holder-multiplier 來源。它沒有，
所以那些股票流向認購人、轉換債權人或員工，
而 C-51 已明文**禁止**把這三種來源拿來導出 holder multiplier（證據 3）。

**⇒ 我們的股數不變。這不是資料缺口，是發行人側事實。**

---

## §2 · 實作

Patch：`_handoff/CA1_CA2_implementation.patch`（與 CA-2 合併於同一份，理由見 §2.3）。

### §2.1 · 分類點

`core/b0_corporate_actions.py:480` 的 `if not is_ex_right_event:` 分支，
回傳狀態由 `NOT_RECONSTRUCTIBLE` 改為 `NOT_APPLICABLE`，
reason 於原文之後追加「為何不影響持股人」那一句。
`new_shares_thousands` **繼續帶著**——它是證據 2 的本體，丟掉它等於丟掉論據。

### §2.2 · ⚠ 第二處改動：transition loop 必須跳過 NOT_APPLICABLE

**這一點預註冊 §2 沒有寫，因為它是實作路徑上的事實，不是規則。**

只改分類點是不夠的，而且**失敗的樣子會很像成功**：
`stock_dividend` 屬於 `holder_affecting_kinds()`，事件仍通過
`transition_portfolio` 的候選過濾（`:1443`）；`NOT_APPLICABLE` 不被 §6.1.12 閘門攔下
（`:1466`）；於是它落到 `assert_transition_fields_present`（`:967`），
而 `REQUIRED_FIELDS["stock_dividend"]` 要 `stock_ratio` 與 `credit_tradable_date`
——這兩個欄位這種事件永遠不會有。

**結果是 abort 換了個門牌**：§6.1.12 變成 §6.1.7，run 一樣停在同一個位置。

因此在 §6.1.12 閘門**之前**新增一段：`NOT_APPLICABLE` 事件記入 `skipped`、`continue`。
這不是為 CA-1 開的特例——它就是 §2.4 對 `NOT_APPLICABLE` 的定義
（「不改變我們的股數/現金/身分」）第一次被機械執行。

⚠ 這段程式碼的危險變異是**把 `NOT_RECONSTRUCTIBLE` 一起跳過**，
那會讓所有公司行為缺口靜默消失。§3 有一條測試專門守它。

### §2.3 · 與 CA-2 共用一份 patch 的理由

兩條規則改在同一個函式的相鄰分支，分成兩份 patch 會互相衝突，覆核者更難讀。
**CA-2 的程式碼在該 patch 中預設為關閉**（見 CA-2 草案 §2），
所以「只採納 CA-1」是可執行的：套用整份 patch 而不翻 CA-2 的旗標，
行為即等同只有 CA-1。§4 分別量測了這兩種狀態。

---

## §3 · 測試

新增 `tests/test_b0_ca1_ca2_stock_dividend_conventions.py`（副本在 `_handoff/`）。
CA-1 有 7 條，每條的 docstring 都寫明「拿掉哪個守衛會殺死它」。

| 測試 | 守的是什麼 |
|---|---|
| `..._classifies_as_not_applicable` | 狀態本身 |
| `..._still_records_the_quantity_it_knows` | 證據 2 不被實作丟掉 |
| `..._reason_states_why_the_holder_is_unaffected` | 不說理由的 NOT_APPLICABLE 與靜默丟棄無法區分 |
| `..._a_flagged_dividend_is_untouched_by_the_rule` | **負控制**：規則不得擴張到 配股(Y/N)='Y' |
| `..._an_exposed_unflagged_event_no_longer_aborts_the_run` | 行為層主張，非標籤層 |
| `..._an_exposed_unflagged_event_changes_no_share_count` | §2 的「multiplier 1.0、不產生 receivable」 |
| `..._does_not_disarm_the_exposure_gate_for_real_gaps` | **負控制**：真缺口仍須 abort |

同時修改既有測試 `tests/test_b0_corporate_actions.py:146`
`test_unflagged_capitalisation_is_not_treated_as_an_ex_right_event`：
它斷言的**命題**（「不得當成除權事件」）未變，只有狀態值由
`NOT_RECONSTRUCTIBLE` 改為 `NOT_APPLICABLE`，最後一行的
`"registration stamp" in e.reason` 原樣保留。**此處修改了既有測試，特此揭露。**

### §3.1 · Mutation 結果（⟨M⟩ 實測，非宣稱）

每個變異單獨套用後跑該測試檔：

| 變異 | 結果 |
|---|---|
| M1 分類點回到 `NOT_RECONSTRUCTIBLE` | **1 failed** |
| M2 移除 `NOT_APPLICABLE` skip | **1 failed** |
| M3 skip 擴大到含 `NOT_RECONSTRUCTIBLE` | **1 failed** |

三個變異各殺死測試。**沒有使用 AST 存在性斷言**
（記憶 `review-verification-discipline`：那種測試對刪除型變異會給假綠燈）。

⚠ 揭露：mutation 跑用了 `-x`（first-failure stop），上表的 pass 數是部分計數。
「守衛被拿掉會有測試死」這件事不受影響，但不能從該表讀出「恰好只死一條」。

---

## §4 · 影響量測（⟨M⟩ 實測）

方法：以樹外 driver 覆寫 `build_corporate_action_ledger` 的輸出路徑，
在 scratch 目錄重建三份 ledger。**`data/b0/` 未被寫入**
（事後複驗 `stock_dividend_pit.csv` 的 sha256 仍為 `783d7cc2…`）。

### §4.1 · 控制組：baseline 重建與封存檔逐位元組相同

```
stock_dividend_pit.csv        sealed == rebuild  ✓ (783d7cc2…)
corporate_actions_ledger.csv  sealed == rebuild  ✓ (c838961f…)
```

**這一條是本節其餘數字的效力來源。** 沒有它，下面的 diff 只能證明兩次跑不一樣，
不能證明差異來自本改動。

### §4.2 · 逐筆 diff（CA-1 only）

```
列數        baseline 46,433 == variant 46,433
鍵集合      完全相同（stock_id, kind, ex_or_effective_date, source_field）
狀態改變     851 列
  stock_dividend  NOT_RECONSTRUCTIBLE -> NOT_APPLICABLE   全庫 851   窗內 312
非 stock_dividend 被影響的列數  0
```

**只有 §1.2 那一族改變，數字與預註冊 §4 逐格相符。**

### §4.3 · 對窗內阻塞的效果

```
窗內 NOT_RECONSTRUCTIBLE   baseline 495  ->  CA-1 後 183
  其中 stock_dividend      baseline 377  ->  CA-1 後  65（= CA-2 那一族）
```

---

## §5 · 變更判定

| 項目 | 判定 |
|---|---|
| 新增自由參數 | **0**。CA-1 未引入任何可調數值 |
| `strategy semantics changed` | **false** |
| 資料改變 | CA ledger 851 列的狀態欄與 reason 欄 |
| 條文衝突 | 無。CA-1 不是插值，不觸 W-1 |
| 前例 | C-51（v1.18）「pre-listing 事件判為 NOT_APPLICABLE 而非缺值」——同一個形狀 |

`= false` 的論據：CA-1 主張這些事件**本來就不改變持股**，三條證據（§1.3）支持該主張。
它改變的是系統對一類事件的**認識**，不是系統對持股的**處理**。
持股數在改動前後相同——§3 的第六條測試直接斷言
`result.state.shares` 不變且 `security_receivables` 為空。

⚠ **這句話成立的前提是 §2.2 的 skip 存在。** 若只落地分類點而不落地 skip，
run 會改在 §6.1.7 停下，那時 `= false` 就是假的。**兩處必須同時落地。**

---

## §6 · 對條文的具體修改建議

### §6.1 · Master §2.4，W-1 之後新增（規範性）

> **W-1a（CA-1）** 資本額變動之來源列未帶除權旗標（配股(Y/N)='N'）者，
> 判為 `NOT_APPLICABLE` 而非 `NOT_RECONSTRUCTIBLE`：官方除權公告對該族
> 無任何正配股率，配發數量流向認購人／轉換債權人／員工，
> 不按持股比例配給既有股東，故我方股數不變。
> 機械強制：`unflagged_capitalisation_policy == "NOT_APPLICABLE_issuer_side"`。
>
> **W-1b** `NOT_APPLICABLE` 事件不進入 transition：記為 skipped，
> 不套用 multiplier、不產生 receivable、不因缺欄位而 block。

### §6.2 · ⚠ 宣告登錄必須同步（本 session 新查得，預註冊 §6.2 未提）

`core/b0_master_prereg.py:1486` 現有一行：

```python
"unflagged_capitalisation_policy": "NOT_RECONSTRUCTIBLE_no_derivation",
```

**CA-1 的現行政策本身就是宣告登錄的一員。** 因此 CA-1 **也會移動 `spec_sha256`**，
`master_prereg_freeze.json` 同樣必須重生。

預註冊 §6.2 說 CA-1「較輕，但仍需封閉」，這句話成立；
但它把成本描述為「改變 CA ledger」，**漏了這一行**。
依任務指示「發現預註冊有問題 → 回報，不要改」，此處回報，未改該文件。

落地時該行應改為：

```python
"unflagged_capitalisation_policy": "NOT_APPLICABLE_issuer_side",
```

**本 patch 未包含這一行的修改**：改它而不重生 freeze json 會讓
declaration-conformance 測試變紅，那是噪音不是訊號。它屬於五步封閉交易的第 5 步。

---

## §7 · 若批准之落地清單

1. 套用 `_handoff/CA1_CA2_implementation.patch`（**不翻** CA-2 旗標）
2. 加入 `tests/test_b0_ca1_ca2_stock_dividend_conventions.py`
3. `core/b0_master_prereg.py:1486` 改為 `"NOT_APPLICABLE_issuer_side"`
4. Master §2.4 落入 §6.1 的 W-1a / W-1b
5. 重生 `master_prereg_freeze.json`（第 5 步，**不是本任務的步驟**）
6. 重建 `data/b0/` 兩份 artefact（⚠ `data/b0/` 已 gitignore，覆蓋不可 revert，
   動之前先複製整個目錄）

---

## §8 · 本草案沒有做的事

- 沒有跑任何回測、沒有開 L2、沒有碰 `scripts/b0_open_l2.py`（連 `--dry-run` 都沒有）
- 沒有改預註冊、沒有改 Master、沒有跑 `freeze_master_prereg.py`
- 沒有覆寫 `data/b0/` 任何一格
- 沒有裁決這兩條規則要跑在哪一條 lineage 上（FROZEN_B0 不可重開，B1 尚未登錄）
- 交付後工作樹已還原乾淨，實作僅以 patch 形式存在
