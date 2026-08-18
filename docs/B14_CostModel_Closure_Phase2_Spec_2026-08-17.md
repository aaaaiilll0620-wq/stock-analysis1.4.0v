# B-14 Cost Model — Phase 2 Implementation Spec

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17「B-14 Phase 1 APPROVED…可以授權 Phase 2 做成本程式實作與測試,但仍不得執行 B0 回測」。
**前置:** B-14 Phase 1 `APPROVED`(P1–P6 凍結)、B-06/B-12 `CLOSED`。

---

## 0. ⚠ 實作位置:**不得就地修改 `l4b_execution.py`**

Phase 1 §7 原列的待辦是「刪除 `l4b_execution.py:54-55` 的 `BUY_COST`/`SELL_COST`」。**本輪撤回該項的就地修改形式**,理由是架構層的:

> **`scripts/l4b_execution.py` 是 Frozen A 的一部分。** 依既定架構,Frozen A「保留目前舊程式、舊資料與 H1–H5 結果,只作歷史 benchmark / audit trail,不再修補」。就地刪改它的成本常數會**變更 Frozen A 的可重現性**,使那條 audit trail 失效。

**因此:B0 成本模型實作於新模組 `core/b0_cost_model.py`,`l4b_execution.py` 與 `portfolio_simulator_lab.py` 一律不動。** 釘死舊常數的 `tests/test_canonical_universe.py:301-302` 同理保留 —— 它保護的是 Frozen A,不是 B0。

B0 執行層日後接線時,改為 import 新模組;舊常數在 B0 路徑上**不可達**(未來以 guard 確保),而非被刪除。

---

## 1. 凍結的成本模型(承 Phase 1 P1–P6)

```
每一筆 strategy child order(金額 V、方向 side、標的 i、執行日 t):

  explicit_fee    = max( MIN_FEE , V × COMMISSION_RATE )
  transaction_tax = V × TAX_RATE            if side == "sell" else 0
  impact          = V × IMPACT_K × σ20D(i)  × sqrt( V / ADV20(i) )

  total = explicit_fee + transaction_tax + impact
```

| 常數 | 值 | 性質 |
|---|---|---|
| `COMMISSION_RATE` | `0.001425` | B0 reference commission rate,`d = 1.0`,不假設折扣 |
| `MIN_FEE` | `20.0` | **B0 reference broker policy,非法規**;整股與零股一致 |
| `TAX_RATE` | `0.003` | 證券交易稅,僅賣出 |
| `IMPACT_K` | `1.0` | **order-one external-prior reference,不宣稱為台股估計值** |
| `σ20D` | trailing 20 交易日 log return 標準差,PIT、未年化 | |
| `ADV20` | trailing 20 交易日 dollar volume 均值 | |

**三者必須分欄記帳,不得合併。**

---

## 2. 本輪新增的 guards 與 disclosure

### G14-1 · No execution-day look-ahead

> **`σ20D` 與 `ADV20` 的資料窗必須完全早於 execution timestamp。**

**這一條同時澄清 P5 的措辭。** P5 原文「逐日使用**當日** `σ20D`、`ADV20`」中的「當日」,**必須讀作「as-of 前一交易日收盤」**,不得包含執行日自身的成交量或報酬 —— 否則多日 `pending_exit` 的每一個 child order 都會用到執行當下尚不可知的資訊。

**實作:** 成本函式強制接受 `data_as_of` 與 `execution_date` 兩個日期,並斷言 `data_as_of < execution_date`;違反即 raise,不得靜默放行。

**現況相容性:** 單日 entry(decision `t` → 執行 `open(t+1)`)本就滿足。**風險完全落在多日 `pending_exit` 的第 2 日起** —— 該路徑是 B-06/B-12 新增的,尚無實作,故此 guard 必須在實作前就位。

### G14-2 · Minimum fee 以 **strategy child order** 為單位

> **`MIN_FEE` 按 strategy child order 收取,不按 individual fill。同一 child order 的多筆 fills 必須先 aggregate 成單一金額,再計算 explicit fee。**

**未加此 guard 的失效:** 一筆 child order 若被拆成 5 筆 fills,逐 fill 收 `MIN_FEE` 會產生 5 × NT$20 = NT$100,**系統性高估**顯性成本。與 §4 的低估風險方向相反,但同樣是模型形式錯誤。

**實作:** 提供 `aggregate_fills()`,成本 API 只接受**已 aggregate 的 child order 金額**;傳入 fill 明細時強制先聚合。

### D14-1 · Impact proxy 的涵蓋範圍(**第二版更正**,必須隨結論帶走)

> **B0 僅建模 square-root market-impact proxy;bid-ask spread、tick-size、intraday execution effects 等其他 implicit frictions 未單獨建模。因此此欄位不得被解讀為完整 implicit trading cost,亦不得宣稱其偏誤方向必然向下。**

**⚠ 第一版錯誤更正:** 第一版寫「B0 的 implicit 成本估計是**下界**」。**該結論不成立且已撤回。** 理由:`IMPACT_K = 1.0` 本身只是 order-one external-prior reference、**不是**台股實證估計,因此 proxy **可能高估也可能低估**真實 impact。「少建模了幾項摩擦」**推不出**「總和必然偏低」—— 兩者是獨立的。任何引用 B0 成本數字者,**不得**把它描述成任一方向的 bound。

### G14-3 · Cost model 不決定可成交性

> **cost model 只對已被 execution layer 判定可成交的 child order 計算成本。`σ20D = 0` 或 `ADV20 > 0` **不是**成交可行性的證據;無成交則不得產生虛構的 zero-impact fill。**

嚴格分開兩個問題:**「能不能成交?」**(execution layer)與**「若成交,成本多少?」**(cost model)。停牌或漲跌停鎖死的標的可以同時具備 `σ20D = 0` 與 `ADV20 > 0`,而正確答案是 **execution infeasible**,不是「以零衝擊成交」。

**實作:** `child_order_cost()` 新增 **keyword-only 且無預設值**的 `execution_confirmed` 參數,非 `True` 即 raise。無預設值是刻意的 —— 任何呼叫端都無法在未確立成交的情況下計價。`σ20D = 0` 時 `CostBreakdown.zero_sigma_fill = True`,寫在收據上供稽核,不靜默吸收。

### G14-4 · B0 不得可達 Frozen-A 的比例成本路徑

> **B0 execution / import graph 不得引用 Frozen-A 的 `BUY_COST`、`SELL_COST` 或任何 legacy proportional-cost path;B0 收據必須由 `core/b0_cost_model.py` 產生三分離成本。**

**實作:** `core/b0_cost_model.py` 宣告 `B0_ENTRY_MODULES` / `LEGACY_COST_MODULES` / `LEGACY_COST_SYMBOLS`;測試以 AST 走訪 B0 進入點的**專案內 import 遞移閉包**,檢查是否 import legacy 模組或**在程式碼中引用**(非字串字面值)legacy 常數名。

**現況:** B0 execution route 尚未組裝,故 `B0_ENTRY_MODULES` 目前僅含 `core.b0_cost_model`。**該路由完成時,其進入模組必須加入此清單,測試即自動對它機械執行 G14-4。** 另附**反向控制測試**(對確實觸及 legacy 的 graph 必須失敗),確保偵測器不是空轉。

---

## 3. 模組介面(`core/b0_cost_model.py`)

```
CostBreakdown(explicit_fee, transaction_tax, impact)  # 三欄分離,total 為衍生屬性
aggregate_fills(fills) -> float                       # G14-2
child_order_cost(value, side, sigma20d, adv20,
                 data_as_of, execution_date)          # G14-1 斷言在內
```

**約束:**
- 純函式,無 I/O、不讀快取、不依賴任何 production state
- `adv20 <= 0` 或 `value <= 0` → **raise**,不得靜默回 0
- `sigma20d < 0` 或非有限值 → **raise**;`sigma20d == 0` 合法(停牌等),impact 為 0,屬模型定義結果並揭露
- 不提供任何可調參數的覆寫入口(避免成為第二個 `composite_weights`)

---

## 4. 測試要求(`tests/test_b0_cost_model.py`)

| # | 測項 |
|---|---|
| T1 | 完整部位 `V=100,000` → `explicit_fee = 142.5`(比例段) |
| T2 | 小額 `V=2,000` → `explicit_fee = 20.0`,有效費率 1.0%(最低收費段) |
| T3 | 臨界點 `V* = 20 / 0.001425 ≈ 14,035.09` 兩側行為正確 |
| T4 | `transaction_tax` 僅賣方;買方為 0 |
| T5 | impact 公式與 `V × k × σ × sqrt(V/ADV)` 逐位元相符 |
| T6 | cap 處 `V/ADV = 1%` → impact rate `= 0.1 × σ`(政策封頂) |
| T7 | **G14-2**:2 筆 fills(各 1,000)聚合為 1 筆 child order → **只收一次 `MIN_FEE`**,非兩次 |
| T8 | **G14-1**:`execution_date <= data_as_of` → raise |
| T9 | 三欄分離:`total == explicit_fee + transaction_tax + impact`,且三者各自可讀 |
| T10 | `adv20 <= 0` / `value <= 0` / `sigma` 非有限 → raise |

---

## 4b. 測試結果(2026-08-17)

`tests/test_b0_cost_model.py` —— **40 passed**。涵蓋 T1–T10 全部,外加:

| 新增測項 | 內容 |
|---|---|
| T11 | **G14-3** —— `execution_confirmed` 無預設值且 keyword-only(位置傳入被擋);非 `True` 一律 raise;`from_fills` 同受約束 |
| T11c | `σ = 0` → `impact = 0` 且 `zero_sigma_fill = True`(可稽核,非靜默) |
| T12 | **G14-4** —— B0 import 遞移閉包不得觸及 legacy cost path;`B0_ENTRY_MODULES` 非空 |
| T12c | **反向控制** —— 對確實觸及 legacy 的 graph,偵測器必須失敗(防止空轉) |
| — | Frozen A 常數未動之斷言(`BUY_COST == 0.001585`) |

**Frozen A 驗證:`git diff --stat scripts/l4b_execution.py scripts/portfolio_simulator_lab.py tests/test_canonical_universe.py` 為空。**

---

## 5. 範圍界線

**狀態(使用者 2026-08-17 裁定):**

```
B-14 Cost Model Spec        : FROZEN
B-14 standalone implementation : PASSED   (40 tests)
B-14 end-to-end integration    : PENDING B0 execution route  (G14-4 機械驗證)
```

**不再開新的成本參數討論,不做 Phase 3 研究。** 成本模型本身視為關閉;integration guard 於 B0 execution 組裝時由 T12 自動執行。

**本 Phase 授權:** 新模組實作 + 測試。
**本 Phase 不授權:** 任何 B0 回測、任何績效 / IC / Sharpe / 選股名單、修改 Frozen A(`l4b_execution.py`、`portfolio_simulator_lab.py`、`tests/test_canonical_universe.py`)、B0 執行層接線。
