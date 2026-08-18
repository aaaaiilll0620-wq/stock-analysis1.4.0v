# W-1 ~ W-4 Corporate Action Closure

**日期:** 2026-08-17
**狀態:** Spec FROZEN / implementation PASSED (37 + 36 tests;全庫 1,465 passed) / route integration PENDING
**合規:** 純規格與資料驗證。**未計算任何報酬 / IC / Sharpe / CAGR / MDD / 選股名單,未動 A0–A3。** Frozen A 七個檔案全部未修改(已核對)。未 stage、未 commit。

---

## 0. 四項裁決的實作對照

| 裁決 | 實作位置 | 機械強制 |
|---|---|---|
| **W-1** 逐事件 `NOT_RECONSTRUCTIBLE`;不插值、不設缺失率門檻;持有時遇到即 abort | `core/b0_corporate_actions.py` · `handle_stock_dividend` / `assert_exposure_reconstructible` | `MISSING_DATA_RATE_THRESHOLD is None`、`INTERPOLATION_ALLOWED is False`,並由 `assert_no_threshold_policy()` 釘死 |
| **W-2** 允許 `credit_date == ex_right_date`,只有 `<` 才 fail | `classify_receivable_ordering()` | 四態 `ok / zero_day / missing / before_ex`;`zero_day` 進 `RECONSTRUCTIBLE` 且打旗標 |
| **W-3** 全部納入 ledger,逐事件類型驗證資料語義 | `EVENT_KINDS` + 六個 canonical handler + fail-loud registry | `assert_every_holder_affecting_kind_has_a_handler()` 未登記即 abort |
| **W-4** 永不主動認購,固定 `False` | `CASH_CAPITAL_INCREASE_SUBSCRIBE = False` | `assert_never_subscribes()`;傳 `subscribe=True` 直接 raise,不可由策略狀態選擇 |

---

## 1. 三態的意義(不是 pass/fail 的美化)

```
RECONSTRUCTIBLE       資料足夠,handler 可以算出我們的股數/現金變化
NOT_RECONSTRUCTIBLE   系統看到了事件,而且知道自己重建不出來 —— 必須帶 reason
NOT_APPLICABLE        事件存在,但不改變「我們的」股數/現金/證券身分
```

`NOT_RECONSTRUCTIBLE` **強制要求 `reason`**(`CorporateActionEvent.__post_init__` 會 raise)。沒有 reason 的缺口和「根本沒辨識到事件」在 final seal 時無法區分 —— 而那正是三態存在的唯一理由。

---

## 2. 資料語義逐類型驗證結果(窗口 2014-07-31 → 2026-03-31)

### 2.1 分類總表

| 事件類型 | RECONSTRUCTIBLE | NOT_RECONSTRUCTIBLE | NOT_APPLICABLE |
|---|---:|---:|---:|
| stock_dividend | **2,423** | **377** | — |
| capital_reduction | **646** | **27** | — |
| par_value_change | **22** | **1** | — |
| merger | — | **53** | — |
| share_conversion | — | **31** | — |
| cash_capital_increase | — | — | 3,295 |
| convertible_bond_conversion | — | — | 8,049 |
| treasury_cancellation | — | — | 1,374 |
| employee_bonus | — | — | 296 |
| transfer_in | — | — | 72 |
| other_share_change | — | — | 84 |
| **合計** | **3,091** | **489** | **13,170** |

窗口內 16,750 個事件;**會改變我們持股的只有 3,580 件(21.4%)**,其餘 13,170 件是發行人總股數變動,稀釋已在市價內。

### 2.2 `NOT_RECONSTRUCTIBLE` 的 489 件成因

| 件數 | 成因 | 性質 |
|---:|---|---|
| **312** | 配股(Y/N)='N' 的盈餘/公積增資:無配股率、無可交易日,`年月日` 是月底登記戳記 | **本輪新發現** |
| **84** | merger(53)+ share_conversion(31):語料無交易對手、無換股比例 | 結構性 |
| **65** | 配股缺 `股票股利上市日/發放日` | W-1 主體 |
| **16** | 減資有退還現金但無 `減資現金退款日` | 現金腿無法定位 |
| **11** | 減資無 `減資率 %` 且同列有其他股數變動,推導身分被污染 | 推導拒絕 |
| **1** | 面額變更 `7642 昶瑞機電`:推得除權前股數為 0,不是 rescale | 對帳失敗 |

---

## 3. 本輪的四個實質發現

### 3.1 🔴 新發現:312 件「無除權旗標的增資」—— 上一輪的 2,488 低估了暴露面

上一輪用 `配股(Y/N)=='Y'` 定義事件,窗口內 2,488 件。但**窗口內另有 312 列 `盈餘增資+公積增資 > 0` 而旗標為 'N'**,兩者 **(代號, 日期) 完全不重疊**(核對 = 0)。

這些列的特徵一致:**無配股率、無上市日/發放日、`年月日` 是月底**(20171031、20171130),證券多為興櫃/新上市。它們是登記時點的盈餘轉增資,不是交易所意義的除權事件。

**把它們當除權配股會憑空發明一個除權日。** 故一律 `NOT_RECONSTRUCTIBLE`,理由明文寫入 ledger,持有時 abort。

**⇒ 窗口內配股類的真實暴露面是 2,800 件,不是 2,488;不可重建的是 377 件(13.5%),不是 65 件(2.61%)。**

### 3.2 🔴 合併與股份轉換在持有人這一側**結構性不可觀測**

語料 33 欄中**不存在**任何 `換股`/`被`/`存續`/`消滅`/`對象`/`標的` 欄位(已窮舉核對)。而所有 84 列都記在**存續/發行方**:

- `3710 連展投控` 合併 207,291 仟股 == 總股數 207,291(新設投控,全額發行)
- 合併 52/53、股份轉換 29/31 的證券在事件後仍有後續列 → 記在**活下來的那一方**

所以：**我們持有「消失的那一方」時,語料裡永遠不會有一列對得上我們。** 用這份語料做暴露偵測必然漏掉。

**⇒ 因此另建獨立守衛 `assert_no_unexplained_disappearance()`**：持有中的證券若**價格序列早於我們停止持有就中斷**,且無 handler 解釋,即 abort。這是持有人側唯一可靠的偵測器,不是補充而是必要條件。

### 3.3 ✅ 減資率可由股數恆等式推導,但只在未被污染時

`減資 ÷ (總股數 + 減資) × 100` 對 642 個有標示減資率的事件比對:**中位數 1.0000、p10 = p90 = 1.0000**,93.77% 落在 ±1%。這是**算術恆等式,不是模型** —— 與被拒絕的「由除權參考價反推配股率」性質不同(後者要假設定價行為)。

但 importer 只在**同列沒有其他股數變動欄位非零**時才推導,否則恆等式被污染。32 件缺率中因此救回 21 件,剩 11 件維持 `NOT_RECONSTRUCTIBLE`。

### 3.4 ✅ 面額變更 22/23 可對帳

以前一列的面額為舊面額,`除權前股數 × (舊面額/新面額)` 對上事後總股數:**22 件誤差 < 0.1%**(如 `2327 國巨` 10→2.5 得 4 倍、`8070 長華` 10→1 得 10 倍)。唯一失敗的 `7642 昶瑞機電` 前一列面額為 1000,推得除權前股數 0。

**handler 強制對帳才給 `RECONSTRUCTIBLE`** —— 直接採信比率會讓一個壞面額把部位放大 100 倍。

---

## 4. 暴露才 abort,存在不 abort

```python
assert_exposure_reconstructible(events, exposures)   # 只在 held 且 covers(event_date) 時 raise
```

這是 W-1 能夠「不設門檻」而仍然可負擔的原因：489 件不可重建事件裡,B0 實際持有的可能是 0 件。**沒持有的缺口不是這次執行的瑕疵**;持有的缺口則一件都不能過。

`Exposure` 是逐日區間比對,不是只比代號 —— 事件日在持有區間外不觸發(有測試釘死)。

---

## 5. V-1b 狀態變更

| 項目 | 之前 | 現在 |
|---|---|---|
| `BlockingDataRequirement.verify().satisfied` | `False`(來源不存在) | **`True`** |
| `unmet_blocking_requirements()` | `[stock_dividend_pit_source]` | **`[]`** |
| `final_provenance_seal` | BLOCKED | **UNBLOCKED** |
| `S-3` | BLOCKED | **UNBLOCKED** |

驗證器輸出(全歷史 9,120 列):`bad_ex_right_date=0`、`receivable_ordering={ok: 8107, missing: 1011, zero_day: 2}`、`reconstructibility={RECONSTRUCTIBLE: 8109, NOT_RECONSTRUCTIBLE: 1011}`。

**「滿足」的定義隨 W-1 改變了,而且必須明說:** 現在是「語義充分且逐列自我分類」,**不是「無缺口」**。驗證器仍會 fail 的是無法靠暴露測試補救的缺陷 —— 缺欄位、除權日不可解析、可交易日早於除權日。

**守衛沒有被拆掉:** `test_V1b_verifier_still_blocks_when_the_source_goes_missing` 與 `test_V1b_final_seal_blocks_again_if_the_source_disappears` 把來源指向不存在的路徑,兩者都必須重新擋住 —— 這證明它是因為資料到位而放行,不是因為被繳械。

---

## 6. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_corporate_actions.py` | 三態、事件分類、六個 canonical handler、fail-loud registry、暴露閘、消失守衛 |
| `core/b0_frozen_spec.py` | V-1b 驗證器改為 W-1/W-2 語義;`source_path` 指向產出 |
| `core/b0_invariants.py` | `B0_ENTRY_MODULES` 加入 `core.b0_corporate_actions` |
| `tests/test_b0_corporate_actions.py` | 37 項,每個守衛都有反向控制 |
| `tests/test_b0_frozen_spec.py` | V-1b 區塊依 W-1/W-2 重寫(10 個舊 pin 被裁決推翻) |
| `research/p0_v1b_stock_dividend/build_corporate_action_ledger.py` | importer:TEJ 欄名只出現在這裡 |
| `research/p0_v1b_stock_dividend/verify_corporate_actions.py` | 資料語義探查 |
| `data/b0/corporate_actions_ledger.csv` | 46,275 事件全歷史 ledger |
| `data/b0/stock_dividend_pit.csv` | V-1b 驗證器讀的配股視圖 |

**注意 `data/` 在 `.gitignore` 內**,ledger 是 derived artifact,必須以 B-21 §4 `DerivedArtifactProvenance` 掛上游雜湊入 manifest:

```
corporate_actions_ledger.csv  f426dbc659c68bd7f1cce0db0cff3254b1d517025cf1cff2f2cd89f9d4c1f06c  (5,267,513 B)
stock_dividend_pit.csv        783d7cc2785f9faeff637529e66138e69c70f9c3a1a4df1001a1b19b7a50a0ec  (645,524 B)
```
上游七個 zip 的雜湊見 `research/p0_v1b_stock_dividend/corporate_action_provenance.json`。

---

## 7. 完成條件對照

> 所有會改變 B0 實際 holdings / cash / security identity 的 corporate action,都必須有 canonical handler;若事件資料不足,必須在 portfolio 真正暴露於該事件時 fail-loud,絕不能靜默產生 NAV。

| 條件 | 狀態 |
|---|---|
| 每個 holder-affecting kind 有 canonical handler | ✅ 6/6,registry 未登記即 abort |
| 資料不足 → 三態標記 + reason | ✅ 489 件全部帶 reason |
| 暴露時 fail-loud,不靜默產生 NAV | ✅ `assert_exposure_reconstructible` |
| 持有人側不可觀測事件也能攔 | ✅ `assert_no_unexplained_disappearance` |
| 無門檻、無插值 | ✅ 常數為 `None`/`False` 並被測試釘死 |
| **接進實際 NAV 產生路徑** | ⏳ **PENDING** —— B0 canonical route 尚未存在(P-1) |

**最後一列是唯一未完成的。** 閘門已經寫好且可證明會擋,但目前沒有任何程式碼呼叫它 —— 因為 `b0_execution` 還不存在。這必須在 route 建好時接上,否則守衛只是宣告。

---

## 8. 未決事項

1. **312 件無旗標增資的處置**:目前一律 `NOT_RECONSTRUCTIBLE`。若這些證券在 B0 母體內且 B0 會持有,實務上會頻繁 abort。是否要另尋來源(如公開資訊觀測站的增資基準日)是新的資料決策,不在 W-1~W-4 範圍內。
2. **`assert_exposure_reconstructible` 的接線點**:應在 NAV 產生前、持股展開後呼叫,屬 P-1 canonical route 的一部分。
3. **`assert_no_unexplained_disappearance` 需要價格序列末日**:資料來源與 `last_price_date` 的 PIT 語義尚未定義。
