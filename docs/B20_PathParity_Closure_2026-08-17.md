# B-20 Production / Research Decision-Path Parity — Closure

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17「開始 B-20 production decision-path parity」。
**合規:** 純 code / 結構稽核 + 合成 fixture。**未跑 B0 performance / IC / Sharpe / 選股研究 / A0–A3。** Frozen A 未修改。未 stage、未 commit。

**目標:** 證明 Frozen B0 的 feature / eligibility / ranking-portfolio / execution / cost 五層語義,在 production-reachable path 與 research/preregistered path **完全一致**。

---

## 0. 🔴 先講一個必須先講的事實:B-20 的主張**目前無法成立**,而且不是因為不一致

**B0 的 production execution route 與 research route 都尚未實作。** 目前存在的 B0 模組只有 `core/b0_cost_model.py`(+ `research/p0_b09_value_reference/` 的候選 reference 建置器)。

**兩條都不存在的路徑,無法比較。** 因此本輪的誠實產出是:

1. **現行程式庫的重複實作清冊**(這才是真正的風險所在,且已發現既成漂移);
2. **收斂 vs 測試維持的分類**;
3. **parity harness 與 fail-loud invariant**(routes 存在時即生效);
4. **fixture parity 契約 + 一個用真實既存漂移做的 live negative control**。

**本文件不宣稱 B0 已達成 parity。** 它宣稱的是:**parity 不可能在未被量測的情況下被靜默宣告。**

---

## 1. 🔴 決定性發現:P0-U1 的 canonical universe **明文排除 production 路徑**

`core/canonical_universe.py` 的 docstring 原文:

> 「…**本次 U1 對象是 H1-H5 已驗證研究引擎(非 production `score_store`/`l4a_decision.py` 路徑)**…」

**⇒ P0-U1 對齊的是研究引擎內部的 A/B 分母,production 路徑從未被納入。** 先前把 U1 記為「P0 第一項已完成」時,**production/research 的母體 parity 其實從來沒有被建立過** —— 它被排除在該研究的範圍之外,而不是被驗證為一致。

**這一項單獨就足以說明 B-20 為何不能省略。**

**同時,`canonical_universe.py` 也是本專案已有的正確作法先例:** 它從 `high52_lab.dual_confirm_mask` 的內嵌 closure **逐位元原樣抽取**百分位排名原語,而**不是重寫一份**,並明文禁止「抽取時順便改演算法」。**B-20 的收斂策略應沿用這個模式。**

---

## 2. 五層 Parity Inventory 與重複實作清冊

### 2.1 Feature 層

| 定義 | 實作處 | 狀態 |
|---|---|---|
| **`rev_accel`** | `universe_screen_daily.py:286-290`(最新 − 3月均,需 3 個 YoY)vs `data_provider.py:1003-1006`(3月均 − 前3月均,需 6 個 YoY) | 🔴 **同名、已漂移**(B-09 F-B) |
| `value_ind_pct` / `pe_hist_pct` / `c2_score` | **15 個模組**觸及(`universe_screen_daily` / `universe_screen_backfill` / `build_industry_value_ref` / `factor_experiments` / `canonical_universe` / `identity_collector/*` / `l4a_decision` / `portfolio_simulator_lab` …) | 🔴 多份實作/鏡射 |
| 產業內估值位階 | `build_industry_value_ref.py` docstring:「**完全鏡射** `scripts/tej_universe_screen_validation.py` 的定義」 | 🔴 宣告式鏡射 |
| 基本面科目/公式 | `backtest.py:510,531`「與 `data_provider` **同一套**科目與公式」 | 🔴 宣告式鏡射 |
| 中期動能 | `data_provider.py:1370`「與回測 PIT **同一套**算法」 | 🔴 宣告式鏡射 |

### 2.2 Eligibility 層

| 定義 | 實作處 | 狀態 |
|---|---|---|
| 每日 L0/L1/L2 篩選 | `universe_screen_daily.py` | production |
| 回補版 | `universe_screen_backfill.py`(「生產同款 2019 錨點」) | 🔴 第二份 |
| 驗證版 | `tej_universe_screen_validation.py` | 🔴 第三份 |
| canonical 母體 | `core/canonical_universe.py` | 研究引擎專用(§1) |

### 2.3 Ranking / Portfolio 層

| 定義 | 實作處 | 狀態 |
|---|---|---|
| 雙確認交集目標名單 | `l4a_decision.py::compute_target_list` **自承**:「邏輯與 `app.py` 的『雙確認精選』分頁一致…**這裡獨立重寫一份**,不從 `app.py` import…但**公式與資料源逐字相同,不得各自漂移**」 | 🔴 **自我聲明的重複實作** |
| 評分 pipeline | `score_store.py:17`「與 `core.backtest._score_one` 是**同一套** pipeline」;`:94`「建一套與 `Backtester.__init__` **完全相同**的評分引擎」 | 🔴 宣告式鏡射 |
| 評級判定 | `backtest.py:762`「與 `advisor._decide_rating` **同一套**邏輯」 | 🔴 宣告式鏡射 |

**`compute_target_list` 的註解本身就是 B-20 存在的理由:「不得各自漂移」是一個**希望**,不是一個**機制**。**

### 2.4 Execution 層

單一實作(`l4b_execution.py`,Frozen A)。B0 尚未實作 → 無可比對象。

### 2.5 Cost 層

| 定義 | 實作處 | 狀態 |
|---|---|---|
| `BUY_COST` / `SELL_COST` | `l4b_execution.py:54-55` **與** `portfolio_simulator_lab.py:47-48`,兩份逐位元相同的常數 | 🔴 重複宣告(Frozen A) |
| B0 三分離成本 | `core/b0_cost_model.py`,**單一來源** | ✅ 已收斂 |

**B-14 的處置(新模組 + G14-4 不可達)使 cost 層成為五層中唯一已收斂者 —— 這是應被複製到其他四層的樣板。**

---

## 3. 分類:應收斂 vs 可用測試維持

**判準(結構性,非偏好):**

> **凡定義了「語義」者(因子公式、eligibility 規則、百分位原語、成本模型),一律收斂到 canonical shared engine。**
> **僅在結構上被迫不同者**(顯示格式化、批次 vs 逐檔的 I/O 外殼)才可保留兩份並以測試維持。

| 項目 | 分類 | 理由 |
|---|---|---|
| `rev_accel` 兩式 | **MUST CONVERGE** | 已漂移;B-09 F-B 已裁定採 A 腿定義 → 應只留一份 |
| 產業內估值位階 / `pe_hist_pct` | **MUST CONVERGE** | B0 已改純橫斷面 B/M;新定義**只應有一份實作** |
| eligibility 三份篩選 | **MUST CONVERGE** | B-06/B-12 已凍結單一 gate |
| `compute_target_list` vs `app.py` | **MUST CONVERGE** | 自承重複;B0 已退化為單一 `SelectionScore` 排序 |
| 百分位排名原語 | **MUST CONVERGE**,採 `canonical_universe.py` 的**逐位元抽取**模式 | 已有先例 |
| 成本 | ✅ 已收斂 | B-14 |
| I/O 外殼 / 顯示層 | 可測試維持 | 不定義語義 |

**⚠ 明確立場:對重複邏輯而言,parity 測試通過只證明兩份副本**今天**一致,不能阻止它們**明天**分歧。本專案已有 `rev_accel` 這個實例證明「不得各自漂移」的註解攔不住漂移。** 因此測試對**重複**程式碼的角色是**漂移偵測器與債務標記**,不是「維持兩份」的正當化理由。

---

## 4. Reachability Graph 與 Fail-Loud Invariant

### 4.1 Route registry

```
core/b0_parity.py
  PARITY_LAYERS  = feature / eligibility / ranking_portfolio / execution / cost
  PARITY_COLUMNS = eligible / score / rank / selected / orders / cash / cost
  B0_ROUTE_PAIRS = ()        ← 空:B0 兩條 route 皆未存在,故不得宣告 parity
```

### 4.2 Fail-loud 規則

> **宣告了 route pair 卻沒有對應 fixture parity 測試,本身即為失敗。**

理由寫在測試裡:**未經量測的 parity 宣告,讀起來像是「已檢查過」,比完全沒有宣告更危險。** 對應測試 `test_no_route_pair_declared_without_fixture` 明文要求:未來宣告 pair 時,必須以**真實 fixture 比對取代**此檢查,**不得以刪除檢查的方式讓它通過**。

### 4.3 三個既有 invariant 必須同時套用

依使用者指示,任何新 B0 entry route 加入 `B0_ENTRY_MODULES` 時,**B-17(regime 不回流)、G14-4(不可達 legacy cost)、B-19(無未登記 override)自動一併生效** —— 三者已共用 `core/b0_invariants.py` 的同一套可達性機制,無需改測試碼。

---

## 5. Deterministic Fixture Parity Test

### 5.1 契約

```
同一 (PIT snapshot, portfolio state, config)
  → production route 與 research route 各產出 DecisionSnapshot
  → 逐欄比對 7 欄:eligible / score / rank / selected / orders / cash / cost
```

**輸入先於輸出被比對:** `as_of`、`config_hash`、`state_hash` 任一不符即 **abort**,不進入輸出比較 —— 兩條路徑吃不同輸入時,parity 在定義上無意義。

**浮點預設 `float_tol = 0.0`(bit-exact)。** 非零容差必須逐欄在呼叫點說明理由;一個全域容差會讓真正的定義差異藏進捨去誤差裡。

**`NaN == NaN` 視為一致** —— 兩邊都缺值是「同意」,不是「分歧」。

### 5.2 Live negative control(用真實既存漂移,非人造案例)

`rev_accel` 的兩份實作被**逐字抽取**進 harness 作為對照:

| 輸入 `yoys = [10, 12, 15, 20, 18, 25]` | 結果 |
|---|---|
| A 腿(3月均 − 前3月均) | 兩者**數值不同** |
| B 腿(最新 − 3月均) | 同上 |
| 輸入僅 5 個 YoY | A 腿 `NaN`(需 6)、B 腿有值(需 3)→ **差異是結構性的,不只是數值** |

**這證明 harness 對真實漂移會觸發,不是空轉。**

### 5.3 測試結果

`tests/test_b0_parity.py` —— **20 passed**。涵蓋:7 欄各自的分歧偵測、row-presence 分歧、缺欄不得略過、bit-exact 預設、NaN 一致、三種輸入不符 abort、未量測 pair 禁止、以及 §5.2 的 live negative control。

**全部 B0 測試套件合計:`tests/test_b0_*.py` — 81 passed。**

---

## 6. 現況與限制

```
B-20 parity inventory        : COMPLETE(五層)
B-20 duplicate classification: COMPLETE(MUST CONVERGE ×5,已收斂 ×1)
B-20 harness + invariant     : IMPLEMENTED(B0_ROUTE_PAIRS 空 = 零宣告)
B-20 fixture parity          : PENDING B0 routes
B-20 parity 主張本身          : NOT YET ASSERTABLE(兩條 route 皆未實作)
```

**三項限制:**

1. **本輪未證明任何 B0 parity** —— 只證明了它無法被靜默宣告,並清點出現行程式庫的重複實作。
2. **§2 的重複實作清冊屬 Frozen A**;它們不會自動消失。B0 若重用其中任何一份,§3 的 MUST CONVERGE 就是待辦而非建議。
3. **`compute_target_list` 與 `app.py` 的漂移風險目前只有註解在防守。** B0 應直接消除該重複,不是再加一個測試。

---

## 7. 新開放項

| # | 事項 |
|---|---|
| **P-1** | §3 五項 MUST CONVERGE 的收斂順序與目標模組,須在 B0 route 實作前定案 |
| **P-2** | production/research 母體 parity 從未建立(§1),須決定由 B0 route 一次做對,或另立補驗 |

**既有未關項:** O-1(chip 語義)、V-1b(股票股利)、V-5(36 月後檢查點)、V-6(Sharpe rf)。

`L1/L2 仍 BLOCKED`。

---

## 8. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_parity.py` | 五層/七欄契約、`DecisionSnapshot`、`compare_decisions`、`assert_parity`、route registry、兩份 `rev_accel` 逐字抽取 |
| `tests/test_b0_parity.py` | 20 項:分歧偵測全類、輸入先驗、未量測宣告禁止、live negative control |
| 本文件 | 五層 inventory + 收斂分類 + invariant |
