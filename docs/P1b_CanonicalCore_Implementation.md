# P-1b · 四層 Canonical Core 實作

**日期:** 2026-08-18
**狀態:** `CORE IMPLEMENTED / Master v1.6 / OPEN SPEC ITEMS = 0`
**合規:** 純實作與規格補抄。**未執行任何報酬 / IC / Sharpe / CAGR / MDD / 選股名單，未動 A0–A3，未讀價格母體。** Frozen A 內容未變。未 stage、未 commit。

> **規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.6。本文件為 rationale / audit trail。**

---

## 0. 五輪的結論

**第一輪：** 四層照 §8.7 建好，登記出 17 項 UNSPECIFIED（structural 4）。

**第二輪：** 依裁決把其中 5 項落進 Master v1.3 —— **五項全部是 omission correction，不是新策略裁決**。同時 `risk_hard_filters` 的 lineage 查核推翻了「四個門檻」這個前提，該項被拆成三個更窄的問題。

**第三輪（本輪）：** 授權補入全部 A/B/C resolution（C-21 ~ C-27）。**十一個 feature 成員現在全部有凍結公式**，`_FORMULA_ITEM` 為空。

**第四輪（本輪）：** 最後 7 個 D 項 + σ20D ddof 依裁決落地（C-28 ~ C-35）。**其中一項裁決未覆蓋到的 legacy 腿，依 M-3 新登記為 open item。**

**第五輪（本輪）：** C-36 移除 current-ratio 下限。**canonical core 規格完備，S-1 轉綠且可檢查。**

```
17 → −5(v1.3) → +3 → 15 → −8(v1.4) → 7 → −7(v1.5) → +1(M-3) → 1 → −1(v1.6) → 0

全庫 1714 passed / 2 skipped
spec_sha256 (v1.6) = 433cf25dec57da9f63c9e74783261207d8e51cabe5c81d091af3da33b6b4cc5a
specified keys = 98（v1.2 為 52）
OPEN SPEC ITEMS = 0
```

**C-16 ~ C-27（13 項）是 master omission，關閉未新增自由參數。**
**C-28 ~ C-35（8 項）是真正的裁決，且每一項都以「移除選項」落地** —— 被否決的替代方案（pro_rata、nearest rounding、ordinal percentile、hold-until-dropped）一律**從程式碼移除**，而非保留為可選分支。不可達的替代方案是文件；可達的是等著被呼叫的旋鈕。

---

## 1. 五項裁決的落地方式（C-16 ~ C-20）

| # | 裁決 | 機械強制 |
|---|---|---|
| C-16 | target drift = **每個 decision date 重設回 5%** | `TARGET_DRIFT_POLICY`；`DRIFT_POLICIES` **只有這一個值**，另一種讀法不保留為可選分支 |
| C-17 | PEG = `PER_TSE / eps_growth(百分點)`，定義域 `PE>0 ∧ growth>0` | `compute_peg()` 回 None；`peg_availability_report()` 供 §9.7 必報 |
| C-18 | eps_growth = `(EPS_t − EPS_{t−4}) / \|EPS_{t−4}\| × 100` | `compute_eps_growth()`；`spec("eps_growth_net_income_fallback") is False` |
| C-19 | 方向綁定 feature 定義 | `feature_percentile()` **無方向參數**；`b0_decision` 被 AST 禁止呼叫帶 `ascending` 的底層 primitive |
| C-20 | F10 **relocate 不重選**；S-1 措辭更正 | `net_margin < −10` 已凍；`RISK_LAYER_COMPLETE = False`；`frozen_risk_filters(allow_incomplete=)` 無預設值 |

### 1.1 `eps_growth` 的 lineage 查核結果（你要求的那一項）

**查到了，而且答案比文件更明確。** 產生點是 `core/data_provider.py::_yoy_growth`：

```python
return float((latest['value'] - prev_val) / abs(prev_val) * 100.0)
```

三件事因此確定：**分母取絕對值**、**單位是百分點**、**`eps_cagr` 從來不是 CAGR**。

但同一段程式碼帶出兩個**不予沿用**的東西，兩者都不是風格問題：

**(a) `±60 天` 比對窗** —— legacy 以「距 latest−365 天最近、且在 ±60 天內」挑基期。**那是一個容差參數，而且落在 Selection 路徑上。** B0 有季別索引，直接取 t−4，不需要它。沿用等於在 S-1 宣稱的路徑上放進一個門檻。

**(b) `if eps_growth is None: eps_growth = net_income_growth`（`data_provider.py:656-657`）** —— **以另一條序列替代缺值就是插補，§4.1 明文禁止**；而且它會讓兩個不同的量共用一個名字，正是 §11 C-8。B0 讓該列依 complete-case 整筆離開。

### 1.2 方向：從「可傳參數」變成「傳不了」

C-19 不只是把 `−` 寫進表格。原本 `member_percentiles` 是這樣呼叫的：

```python
percentile_rank(raw, convention=..., ascending=(orientation(key) == "+"))
```

即使值取自定義，**方向仍是一個呼叫端可以傳的東西**。現在計分入口是 `feature_percentile(key, values, convention=)`，**簽名裡沒有方向**，而 `percentile_rank` 被列入 `b0_decision` 的 AST 禁用清單。要把 `debt_to_asset` 反過來計分，得先改 feature 定義 —— 那會是一個 diff，不是一個 call。

---

## 2. 🔴 `risk_hard_filters` 的 lineage 查核推翻了前提

裁決文的假設是「沿用原 F10 四個 hard filters，不重新選數字」。**逐行讀 `core/fundamentals.py:262-305` 之後，這個前提不成立。**

| 裁決文寫的 | 程式碼實際做的 |
|---|---|
| `debt_to_asset > 85 → ineligible` | **條件式**：`is_financial` 一律豁免；否則僅當 (`current_ratio < 100` **或** `net_margin < 0`) **或** `debt > 92` 才失敗。高槓桿但流動性健康且獲利 → **放行** |
| `current_ratio < 50 → ineligible` | 失敗，**除非 `is_financial`** |
| `net_margin < -10 → ineligible` | 無條件 ✅ **與裁決文一致** |
| `cash_quality < 0.5 → ineligible` | **全庫沒有任何地方寫入 `cash_quality`** |

**所以「四個門檻」實際上是六個常數（85 / 92 / 100 / 0 / 50 / −10）+ 一個產業別豁免 + 一腿從未觸發。**

**照裁決文的摘要凍結，會凍進一個與 legacy predicate 不同的東西** —— 而且方向不是「更保守」：把條件式收成無條件 `>85` 會剔掉一整群高槓桿但健康的標的，那是策略變更，不是搬家。

### 2.1 `cash_quality` — 你要求的 lineage guard 回報：**負向**

`core/fundamentals.py:64` 有門檻 `min_cash_quality: 0.5`，:255 與 :301 讀 `data.get("cash_quality")`，**但全庫 grep 找不到任何寫入點**。

**⇒ 這條 filter 從未在任何一次執行中觸發過，它的門檻從未被驗證。** B-01 也沒有封住它。

最接近的既有量是 `ocf_to_net_income`（`= ocf / net_inc`），但那是**另一個數**：淨利為 0 時無定義、淨利為負時整個比值變號，`< 0.5` 在該區間的語義與原意相反。**採用它是定義一條新的 B0 filter，不是 relocate 舊的。**

依你的指示，該腿標為 open，未硬塞進 B0。

### 2.2 落地結果

**已凍：** `net_margin < −10`（唯一無條件的一腿）。
**已開（3 項）：** `risk_filter_is_financial_exemption`、`risk_filter_debt_conditional_structure`、`risk_filter_cash_quality`。

**機械強制：** `frozen_risk_filters(allow_incomplete=False)` abort。**部分套用的風險層不是比較保守的完整風險層**，所以不得以這個狀態產生任何證據。

### 2.3 S-1 措辭已依裁決修正

§9.1 S-1 改為 **「runtime tunable 自由參數 = 0」**，並加了一段規範性澄清：§7.1 成本常數、§4.4 relocate 自 F10 的門檻、§5 的 20 與 5%，都是 **frozen inherited / declared constants**，逐一具名、逐一有來源、執行期不可改。

**同時把 S-1 由 `✅ FROZEN` 降為 `⏳ PENDING`** —— 不是它被違反，而是風險層三腿未定之前，「這條路徑上的門檻都是繼承來的」這句話**還無法被檢查**。這與 §11 C-3 的教訓一致（不要把「資料到位」記成「已強制執行」）。

---

## 3. C-36 · 風險層定案

**裁決：`current_ratio < 50` 移除。** 且明文否定一個推論：

> **不得把「移除金融業豁免」重新詮釋為「legacy `<50` 規則變成全產業無條件適用」。**

移除一個 carve-out 與保留它所 carve out 的規則是兩個不同的決定，本規格只做了第一個。這正是我上一輪列為讀法 (i) 的那個推論，現已被明文擋掉。

### 3.1 B0 最終的基本面 hard risk filter

```
net_margin < −10（百分點）  →  ineligible
```

**就這一條。** 四條 legacy 腿全部移除：負債條件樹（C-30）、cash_quality（C-31）、current-ratio 下限（C-36）、金融業豁免（C-29）。

兩個 balance-sheet 比率改由**連續處理**承接：高槓桿或低流動比的標的在 Quality 百分位上受懲罰，而非被切點剔除。**這與 §3.1 把人工切點降為 0 的方向一致** —— 風險層從六個常數收斂到一個。

**機械強制：** `assert_no_removed_legacy_leg()` 攔截任何一條被移除的腿以 runtime filter 形式復活（含 `min_current_ratio` / `max_debt_to_asset` / `min_cash_quality` 等別名）。

### 3.2 ⚠ 一項隨此條帶走的後果（揭露，非歧義）

**該門檻的輸入定義已由 C-21 改為 TTM。** legacy 的 `−10` 作用在**單季**淨利率上；B0 的作用在**四季彙總**淨利率上，因為 B0 只有一個 `net_margin`（§3.5）。

**讀法是唯一的**（規格裡沒有第二個 `net_margin`），所以不是 ambiguity、未登記為 open item。但**單季與 TTM 會剔除到不同的公司** —— 一家單季重虧但全年小虧的公司在 legacy 下被剔除、在 B0 下留下。已寫入 §4.4 與 §11 C-36 的揭露段。

若你認為門檻值應隨輸入定義改變而重新檢視，那是一個新的裁決，不是本輪的一部分。

### 3.3 S-1 轉綠，且是可檢查的

`assert_selection_path_is_fully_specified()` 檢查四件事：

1. canonical core 無任何 UNSPECIFIED 登記項
2. 風險層自陳完備（且與登記簿一致）
3. feature graph 每個成員都有凍結公式與方向
4. C-32 ~ C-35 的四個慣例**各自只容許一個值**

第 4 項是關鍵：**有可選替代方案的慣例就是 runtime tunable parameter，不論文件怎麼稱呼它。** 所以這個檢查會在有人把 `pro_rata` 或 `nearest` 加回 tuple 的那一刻失敗。

> **⚠ 它證明的是「規格完備」，不是「路徑遵守規格」。** 後者是 S-2 與 S-3b，兩者在 route 建成前仍為 PENDING。**把這兩件事合併成一個綠燈，正是 §11 C-3 記錄的錯誤**，所以 §9.1 的 S-1 列已明寫這條界線。

測試 `test_s1_fails_loud_again_if_any_behaviour_reopens` 釘死了它不是一個常數：只要有一個 open item 回來，S-1 立刻回到 PENDING。

---

## 4. 稽核

```
Frozen A 七檔：內容未變（三檔顯示 M 但 --ignore-cr-at-eol 為空 = 純 CRLF）
全庫 1714 passed, 2 skipped
不變量 61 項綠（四層 + state 已掛進 B0_ENTRY_MODULES）
spec_sha256 (v1.6) = 433cf25dec57da9f63c9e74783261207d8e51cabe5c81d091af3da33b6b4cc5a
specified keys = 98（v1.2 為 52）
UNMET BLOCKING = ['price_universe_survivorship']   (D-1,未動)
OPEN SPEC ITEMS = 0
```

`master_prereg_freeze.json` 新增 `open_specification_items` 欄位 —— **帶著 open items 的凍結不是完整的凍結**，這個數字應該跟著 freeze record 走，而不是只存在於文件裡。

### 4.1 沿用上輪、仍未處理的三件事

1. **working tree 311 個 dirty 條目**（171 檔純行尾差異）→ §8.6 禁止 dirty tree seal，建議走 `.gitattributes`
2. **整個 B0 程式層未被 git 追蹤**（`git ls-files | grep b0_` = 0），`scripts/l4b_execution.py` 亦然 —— 後者是 Frozen A 七檔之一，一份從未進版控的 audit trail 只能靠檔案系統擔保
3. **`test_dataexport_runtime_overlay.py` 目前 PASS**，但仍 wall-clock 相依，留在 finalization checklist

---

## 5. 下一步

```
D-1 重新匯出 2019-2026 含下市        ← 現在是唯一的 blocker(seal 與 L2)
P-2 兩個 adapter 供料同一 core       ← 規格已完備,可以直接開工
B-20 真實 fixture parity(比對 adapter 邊界)
S-3b route enforcement → S-2 / S-8
```

**canonical core 的規格階段到此結束。** 之後每一步都是「接線」與「驗證」，不再有策略裁決。
