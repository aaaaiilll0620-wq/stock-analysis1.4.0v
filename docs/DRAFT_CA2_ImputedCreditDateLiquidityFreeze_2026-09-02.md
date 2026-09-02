# DRAFT · CA-2 · 無可觀察入帳日 ⇒ 流動性凍結窗口 59 個日曆天

> **STATUS: DRAFT — NOT NORMATIVE, NOT FROZEN.**
>
> 本檔**不是** Master Preregistration 的一部分。撰寫本檔**未**上版號、
> **未**修改 `research/b0_registry/master_prereg_freeze.json`、
> **未**翻轉 `INTERPOLATION_ALLOWED` 或 `MISSING_DATA_RATE_THRESHOLD`、
> **未**改動任何 run artefact 的位元組、**未**開任何 run。
>
> 目標版號 **v1.38**、closure 編號 **CA-2**。
> **落地順序：CA-1 先，CA-2 後**（預註冊 §6.3）。
>
> **規則本體已凍結於** `docs/預註冊_配股不可重建事件處置_2026-09-02.md` §3。
> 本檔不修改規則，只交付實作、測試、影響量測與條文修訂草稿。

---

## §0 · ⚠ 這一份與 C-47 至 C-72 都不同

C-47 至 C-72 每一個 closure 都宣告 **`strategy semantics changed = false`**。

**CA-2 是第一個 `= true`。**

它改變「股票何時可賣」。一筆配股在 65 個窗內事件上從「不可重建、持有即中止」
變成「可重建、59 天後可賣」，投組會因此在某些月份持有不同的可交易股數，
於是持倉、換手、NAV 都會移動。**這不是實作修正，是行為變更。**

任何沿用舊模板寫下 `= false` 的 CA-2 文書都是錯的。詳見 §5。

---

## §1 · 這條規則要對抗的不是缺值，是缺值的方向

65 筆窗內事件（全庫 160 筆）有除權日、有配發數量，但沒有
`股票股利上市日/發放日`。配股的股票確實會到手，只是語料沒記何時。

W-1 的現行答案是 `NOT_RECONSTRUCTIBLE` + 持有即中止。那是安全的，
但它把「不知道何時到手」處理成「不知道會不會到手」——後者不是事實。

CA-2 的答案是：**承認它會到手，並且刻意估得比實際晚。**

### §1.1 · 59 的來源（⟨M⟩ 本 session 複驗）

以「有觀測入帳日的可重建事件」量得的落差分布
`lag = actual_credit_tradable_date − ex_right_date`（日曆天）：

```
n    = 8,109
p50  = 44     p75 = 51     p90 = 59     p95 = 65      （nearest-rank）
```

**59 = p90**，與預註冊 §3 逐格相符。
⚠ 分位法必須是 **nearest-rank**：以 `statistics.quantiles(method="inclusive")`
計得 p95 = 64.6 而非 65。p90 兩法皆為 59，故本規則的數值不受影響，
但複驗者若得到 64.6 不是算錯。

### §1.2 · 為什麼不是 T+2，也不是 p50

⚠ **預註冊 §3 寫「實測落差 ≤ 2 天者佔 0.0%」。實測為 2 / 8,109 = 0.0247%，不是 0。**
四捨五入至一位小數為 0.0%，論證方向不變（T+2 在這個母體裡幾乎不存在），
但「零筆」與「兩筆」不是同一句話，此處據實記錄。

方向性論證：配股入帳是公司行為匯撥，中位數 44 天，不是買賣交割的 T+2。
以 T+2 填值等於讓投組提早約六週取得可賣股票——**可以賣掉還沒到手的股票**，
是對投組有利的前視偏誤。填補缺值的方向必須讓策略**吃虧**：
晚入帳的代價是「該賣時賣不掉」，方向正確。p50 無偏但仍有一半情況偏早，故取 p90。

### §1.3 · 這個數字為什麼可以出現在預註冊裡

59 是**資料屬性**：由「已知入帳日的事件」量得，與任何投組、NAV、報酬、
績效指標無關，故不觸犯 §9.6a-R2 條件 2。若它取自任何策略結果，本規則不成立。

---

## §2 · 實作：預設關閉

Patch：`_handoff/CA1_CA2_implementation.patch`（與 CA-1 共用，理由見 CA-1 草案 §2.3）。

### §2.1 · 為什麼預設關閉

CA-2 是 **W-1 明文禁止的插值**。W-1 有機械強制：

```
core/b0_corporate_actions.py:714   MISSING_DATA_RATE_THRESHOLD = None
core/b0_corporate_actions.py:715   INTERPOLATION_ALLOWED: bool = False
core/b0_corporate_actions.py:719   斷言：任一為真即 raise
core/b0_master_prereg.py:1467-1468 兩者綁進宣告登錄
```

（以上四處行號本 session 於主線 `25ba7440` 逐一複驗。）

若把 CA-2 直接寫成無條件生效，程式就會在一條**尚未被裁決**的例外上運轉，
而它的宣告登錄還在說自己不插值。因此實作引入：

```python
CA2_CREDIT_DATE_IMPUTATION_CALENDAR_DAYS: int = 59
CA2_CREDIT_DATE_IMPUTATION_ENABLED: bool = False
```

**關閉時，該分支的行為與 CA-2 存在之前逐字相同**（§3 有測試守著）。
旗標的存在讓規則可以被實作、測試、量測，而不改變任何現行 run 的結果。

⚠ **翻這個旗標不等於落地 CA-2。** 落地還需要同時翻 `INTERPOLATION_ALLOWED`、
修 Master §2.4、重生 freeze json。單獨翻 `CA2_..._ENABLED` 會讓程式與宣告登錄矛盾。
理想上這一點應有機械強制（見 §7）。

### §2.2 · session 正規化交給既有機制

凍結規則是 `next_trading_session(ex + 59)`，取第一個 **≥** 該日期的 session。

實作只算 `ex + 59` 的原始日期，**不做 session 步驟**：
`_first_session_on_or_after`（`:1035`）在 claim 建立時已對**每一個**入帳日
——觀測的與推估的——做同一件事。在分類器裡再做一次，等於同一個答案算兩遍；
而且分類器要做這件事就得拿到日曆，**一個能讀日曆的分類器也能讀別的東西**。

⟨M⟩ 已驗證兩者組合等於凍結公式：測試以 2020-10-04（星期日）為推估日，
claim 實際成熟於 2020-10-05。

### §2.3 · 標記推估值

事件帶 `diagnostics`：`credit_date_imputed=True`、`credit_date_observed=None`、
`imputation_calendar_days=59`，reason 以 `CA-2:` 開頭。
這是 §3 否證條款（「日後取得真實入帳日者一律以真實值為準，
落差須逐筆記錄，不得靜默取代」）能被執行的前提。

---

## §3 · 測試

`tests/test_b0_ca1_ca2_stock_dividend_conventions.py`，CA-2 有 10 條。

| 測試 | 守的是什麼 |
|---|---|
| `..._is_off_by_default_because_w1_forbids_it` | 旗標與 `INTERPOLATION_ALLOWED` 皆為 False |
| `..._default_behaviour_is_byte_for_byte_the_pre_ca2_behaviour` | 關閉時 reason 逐字相同、credit 仍為 None |
| `..._window_is_59_calendar_days_the_p90_of_the_observed_lag` | 數值本身 |
| `..._when_enabled_imputes_ex_right_plus_59_calendar_days` | 日曆天、自除權日起算（跨月，看得出 off-by-one） |
| `..._imputed_credit_is_never_a_zero_day_receivable` | W-2 不被破壞 |
| `..._marks_the_value_as_imputed_and_the_observation_as_absent` | 否證條款可執行 |
| `..._never_overrides_an_observed_credit_date` | **負控制**：只在缺值時生效 |
| `..._does_not_rescue_a_credit_date_that_precedes_ex_right` | **負控制**：`before_ex` 是矛盾不是缺值 |
| `..._imputed_claim_is_not_sellable_before_it_matures` | 選 p90 的經濟意義：股票不得提早可賣 |
| `..._imputed_credit_is_normalised_to_a_session_not_a_calendar_day` | §2.2 的組合等式 |

### §3.1 · Mutation 結果（⟨M⟩ 實測）

| 變異 | 結果 |
|---|---|
| M4 `59 -> 44`（p50） | **1 failed** |
| M5 imputation 無視旗標（無條件生效） | **1 failed** |
| M6 拿掉 `credit_date_imputed` 標記 | **1 failed** |
| M7 `59 -> 0`（等同 zero-day） | **1 failed** |

⚠ 同 CA-1 §3.1 的揭露：mutation 跑用了 `-x`，pass 數為部分計數。

---

## §4 · 影響量測（⟨M⟩ 實測）

方法與控制組同 CA-1 草案 §4（baseline 重建與封存檔逐位元組相同）。
`data/b0/` 未被寫入。

### §4.1 · 逐筆 diff（CA-1 + CA-2 同時開啟）

```
列數        baseline 46,433 == variant 46,433
鍵集合      完全相同
狀態改變     1,011 列
  stock_dividend  NOT_RECONSTRUCTIBLE -> NOT_APPLICABLE     全庫 851   窗內 312
  stock_dividend  NOT_RECONSTRUCTIBLE -> RECONSTRUCTIBLE    全庫 160   窗內  65
非 stock_dividend 被影響的列數  0
```

**只有 §1 那兩族改變**，數字與預註冊 §4 逐格相符。

### §4.2 · 對窗內阻塞的效果

```
窗內 NOT_RECONSTRUCTIBLE   baseline 495  ->  CA-1 183  ->  CA-1+CA-2 118
  其中 stock_dividend      baseline 377  ->  CA-1  65  ->  CA-1+CA-2   0
```

配股類的窗內阻塞歸零，與預註冊 §4 相符。
剩下的 118 筆全部不是配股：

```
holder_side_reorganization_exit  90
capital_reduction                27
par_value_change                  1
```

⚠ 預註冊 §4 已註明「剩餘阻塞 0」只對這兩個 reason 而言。
上表是那句話的量化版本：**兩條規則落地後，回測仍會被上列三族擋住。**

---

## §5 · 變更判定

| 項目 | 判定 |
|---|---|
| 新增自由參數 | **1**：`CA2_CREDIT_DATE_IMPUTATION_CALENDAR_DAYS = 59` |
| `strategy semantics changed` | **TRUE** |
| 資料改變 | CA ledger 160 列由不可重建轉為可重建，並獲得一個製造出來的入帳日 |
| 條文衝突 | **直接牴觸 W-1**（「不插值」），需 Master §2.4 修訂 |
| 前例 | **無**。C-47 至 C-72 全部 `= false` |

### §5.1 · 為什麼是 true

CA-2 改變「股票何時可賣」。65 個窗內事件從「持有即中止」變成
「59 天後獲得可交易股數」。可交易股數改變 ⇒ 可賣量改變 ⇒
再平衡的成交量與現金流改變 ⇒ NAV 序列改變。

CA-1 可以誠實地說 `= false`，因為它主張那些事件**本來就不動我方股數**，
並有三條證據。CA-2 沒有這種主張可用：它明知資料缺失，
仍決定放一個數字進去。**這是決策，不是修正。**

### §5.2 · 自由參數 59 的兩個誠實限制

1. **它只在缺值時生效，但缺值不是隨機的。** 65 筆缺入帳日的事件未必與
   8,109 筆有入帳日的事件來自同一分布。以後者的 p90 估前者，
   是一個**未經檢驗的可交換性假設**。預註冊 §3 未討論此點；此處揭露，不改規則。
2. **保守的方向是相對於「賣出」而言。** 若某個持倉的最適動作是續抱，
   晚入帳不構成成本；若是賣出，晚入帳是成本。因此「一律吃虧」的說法嚴格來說是
   「在需要賣出時吃虧、其餘情形無差別」。方向仍然正確，但不是一致嚴格保守。

---

## §6 · ⚠ 本 session 查得的一個落地缺陷：推估值會偽裝成觀測值

**這是本草案最重要的發現，預註冊與任務指示皆未涵蓋。**

`build_corporate_action_ledger` 把入帳日寫進 `stock_dividend_pit.csv` 的欄位
`actual_credit_tradable_date`（`research/p0_v1b_stock_dividend/build_corporate_action_ledger.py:242,253`）。
CA-2 開啟後，160 筆推估值**寫進了一個名字裡有 `actual` 的欄位**。

⟨M⟩ 兩項實測後果：

1. **59 天的間距不足以辨識推估列。** 重建後 `credit − ex == 59` 的列共 **250** 筆，
   其中只有 160 筆是推估的；另外 90 筆本來就觀測到 59 天。
   唯一可靠的辨識鍵是 `reason` 欄是否以 `CA-2:` 開頭（實測 160/160 皆有）。
2. **59 這個數字會自我確認。** 用同一支腳本、同一個欄位重算落差分位：

   ```
   baseline    n = 8,109   p50/p75/p90/p95 = 44 / 51 / 59 / 65
   CA-2 之後   n = 8,269   p50/p75/p90/p95 = 44 / 52 / 59 / 64
   ```

   母體從 8,109 漲到 8,269——**160 筆推估值靜默混入了它自己的來源統計**，
   而 p90 仍是 59。任何日後「重新複驗 59 是否仍是 p90」的動作，
   若未排除推估列，得到的會是一個由自己造出來的確認。

**⇒ 落地必須包含下列其中一項**（本 patch 未擅自選定，屬裁決範圍）：

- (a) 於 pit view 增加 `credit_date_source ∈ {observed, ca2_imputed}` 欄，且
  分位計算一律 `WHERE credit_date_source = 'observed'`；或
- (b) 推估值不寫入 `actual_credit_tradable_date`，另闢 `imputed_credit_tradable_date` 欄。

(a) 較小，(b) 較誠實。兩者都需要改 `build_corporate_action_ledger`，
而該檔的輸出綁在 baseline seal 上。

---

## §7 · 對條文的具體修改建議

### §7.1 · Master §2.4，W-1 改寫（規範性）

> **W-1** 缺資料 → 逐事件 `NOT_RECONSTRUCTIBLE`。**不插值、不設缺失率門檻。**
> 機械強制：`MISSING_DATA_RATE_THRESHOLD is None`。
> **唯一例外見 W-1c。缺失率門檻無例外，永遠不存在。**
>
> **W-1c（CA-2）** 配股事件之入帳日缺失（且僅此一種缺失）時，
> 以 `next_trading_session(ex_right_date + 59 calendar days)` 補值，
> 59 為可重建事件實際落差之 p90（n = 8,109，nearest-rank）。
> 該值須逐事件標記為推估（`credit_date_source = ca2_imputed`），
> 日後取得真實入帳日者一律以真實值為準，落差逐筆記錄，不得靜默取代。
> 推估值**不得**進入任何用以推導本窗口長度的統計。
> 機械強制：`INTERPOLATION_ALLOWED is True` 且
> `CA2_CREDIT_DATE_IMPUTATION_CALENDAR_DAYS == 59`。

⚠ **`MISSING_DATA_RATE_THRESHOLD` 必須保持 `None`。** CA-2 是逐事件補值，
不是「缺失率低於 X% 就放行」。兩者被 W-1 寫在同一句話裡，
但只有前者被本裁決開了例外。混淆這兩件事會讓 W-1 整條失效。

### §7.2 · 宣告登錄

`core/b0_master_prereg.py:1468` `"interpolation_allowed": ca.INTERPOLATION_ALLOWED`
會由 False 變 True ⇒ `spec_sha256` 移動 ⇒ `master_prereg_freeze.json` 重生。
建議同時把 `CA2_CREDIT_DATE_IMPUTATION_CALENDAR_DAYS` 綁進登錄，
否則 59 可以被改成別的數字而不動 hash。

### §7.3 · 機械強制（尚未實作，揭露）

現行 patch **沒有**任何機制阻止有人只翻 `CA2_..._ENABLED` 而不翻
`INTERPOLATION_ALLOWED`。落地時應在 `assert_no_threshold_policy` 加上一條
反向斷言：`CA2_..._ENABLED` 為真時 `INTERPOLATION_ALLOWED` 必須為真，否則 raise。
本草案未實作，因為它斷言的是一個尚未被批准的條文。

---

## §8 · 若批准之落地清單

1. 先完成 CA-1 closure（預註冊 §6.3 的順序）
2. 套用 patch 並翻 `CA2_CREDIT_DATE_IMPUTATION_ENABLED = True`
3. 翻 `INTERPOLATION_ALLOWED = True`（**這一步是裁決，不是實作**）
4. 實作 §7.3 的反向斷言
5. 依 §6 選定 (a) 或 (b) 並改 `build_corporate_action_ledger`
6. Master §2.4 落入 §7.1 的 W-1c
7. 重生 `master_prereg_freeze.json`（第 5 步，**不是本任務的步驟**）
8. 重建 `data/b0/`（⚠ 已 gitignore，覆蓋不可 revert）

---

## §9 · 本草案沒有做的事

- 沒有翻任何旗標（`CA2_..._ENABLED` 與 `INTERPOLATION_ALLOWED` 皆仍為 False）
- 沒有跑回測、沒有開 L2、沒有碰 `scripts/b0_open_l2.py`（連 `--dry-run` 都沒有）
- 沒有估算本規則對報酬的影響——那要跑完才知道，而跑完才知道正是先凍結規則的理由
- 沒有裁決跑在哪一條 lineage 上
- 交付後工作樹已還原乾淨，實作僅以 patch 形式存在
