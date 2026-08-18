# B-17 Closure — Regime 不得回流決策(可機械驗證的不變量)

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17「B-17 的目標非常窄:不是重新研究 regime,而是證明 **Frozen B0 的 ranking、eligibility、weight、cost 任一 production-reachable path 都不存在 regime-dependent alpha multiplier / threshold / branch**。如果只是 reporting label 或事後 attribution,可以存在,但絕不能回流決策。」
**合規:** 靜態程式碼分析 + 測試。**未執行回測、未產生績效 / IC / Sharpe / 選股名單、未做參數掃描。** 未修改 Frozen A。未 stage、未 commit。

---

## 0. 命題形式的轉變(這是本輪最重要的一件事)

B-17 在 Manifest 裡原本是一個**研究問題**(「哪一套 regime 定義比較好」),而該問題被標為 `⚠ D-不可 ex-ante` —— 無法在不看結果的情況下回答。

**使用者本輪把它改寫成一個不變量(invariant):**

> **B0 的 production-reachable graph 中,ranking / eligibility / weight / cost 任一路徑皆不得含 regime-dependent 的 alpha multiplier、threshold 或 branch。**

**這個命題可以在零績效資訊下被機械證明。** 它與 G14-4 同型 —— 兩者都是「某物是否可達」的靜態圖性質,而不是「某物是否有效」的統計主張。**B-17 因此從不可 ex-ante 決定的項目,轉為可驗證的項目。**

**允許存在的:** regime 作為 reporting label 或事後 attribution。
**禁止的:** 它以任何形式回流進決策。

---

## 1. 全庫 regime 觸點盤點 `[V]`

### 1.1 會改變決策的(B0 不得可達)

| 觸點 | 位置 | 影響層 |
|---|---|---|
| `REGIME_MULTIPLIERS` 三檔權重乘數 | `core/regime.py:24-34` | **weight**(composite 權重) |
| `regime_multipliers(self.current_regime)` | `core/advisor.py:108-110` | **ranking**(套用上述乘數) |
| `regime_rating_gates(...)` | `core/advisor.py:517-518` | **threshold**(評級門檻) |
| `advisor.current_regime = self._regime_at(as_of)` | `core/backtest.py:757`、`:1384`、`:1494` | **注入點**(三處) |
| `use_regime = True`(**預設開啟**) | `core/backtest.py:716-717` | **branch** |
| `_regime_at()` / `classify_regime()` | `core/backtest.py:721-736` | 標籤產生 |
| `OVERLAY_ALPHA` C 層曝險 overlay | `core/regime_exposure.py` | **部位大小** |

**⚠ 最危險的一項是 `core/backtest.py:716` 的 `use_regime = True`** —— regime 是**預設開啟**的。任何 B0 路徑若重用 `core/backtest.py`,regime 會**隨附帶入**,不需要任何人明確啟用。這使「明確關閉」成為不足夠的防線;**唯一足夠的防線是「不可達」**。

### 1.2 僅供顯示的(允許存在)

| 觸點 | 位置 | 依據 |
|---|---|---|
| 市場燈號 | `core/market_index.py:4` | 自身 docstring:「**只供顯示,不驅動訊號**」 |
| `_ensure_market_regime()` | `core/data_provider.py:1100-1131` | 回傳描述字串 |
| `bear_regime` | `scripts/universe_screen_daily.py` | 僅顯示警示,不回饋任何篩選/排序 |

**這些不在禁止清單內** —— 符合使用者裁決的「reporting label 可以存在」。

---

## 2. 不變量的實作

### 2.1 共用機制:`core/b0_invariants.py`

B-17 與 G14-4 是同一種檢查,故可達性機制只實作一次:

```
B0_ENTRY_MODULES          B0 生產圖的進入點(目前僅 core.b0_cost_model)
REGIME_DECISION_MODULES   core.regime / core.regime_exposure
REGIME_DECISION_SYMBOLS   REGIME_MULTIPLIERS / regime_multipliers /
                          regime_rating_gates / classify_regime /
                          current_regime / use_regime / _regime_at / OVERLAY_ALPHA
local_import_closure()    專案內 import 的遞移閉包
referenced_names()        AST Name/Attribute —— 字串字面值刻意不算引用
find_violations()         回傳 (module, reason)
```

### 2.2 🔴 一個實作層的重要決定:**靜態解析,絕不 import**

第一版用 `importlib.import_module()` 走訪。**實測失敗**:import `core.advisor` / `core.backtest` 會產生破壞性副作用,連 pytest 的輸出捕捉都被弄壞(`ValueError: I/O operation on closed file`)。根因是專案既有缺陷 —— `core/data_provider.py:23` 在 class body 實例化 `DataLoader()`,transitive import 即觸發網路登入(已載於 `ISSUE_data_provider_import_login.md`)。

**改為純靜態路徑解析(`_module_path()`),完全不執行任何模組。**

這不只是繞過問題,而是**本來就正確**的做法:可達性是**靜態**性質。用 import 走訪還有一個隱患 —— import 失敗會被 `except: continue` 吞掉,**反而可能遮蔽真正的違規**。靜態解析沒有這個失效模式。

### 2.3 測試:`tests/test_b0_regime_invariant.py`

| 測項 | 內容 |
|---|---|
| `test_B17_no_regime_dependent_decision_reachable_from_B0` | **不變量本身** |
| `test_B17_detector_is_not_inert` | **反向控制** —— 對 `core.advisor` 必須觸發 |
| `test_B17_known_frozen_A_carriers_are_flagged` | `core.advisor` 與 `core.backtest` 兩個已知載體皆須被偵測到 |
| `test_G14_4_*` | G14-4 及其反向控制(共用同一機制) |
| `test_string_literals_do_not_count_as_references` | 守衛模組以字串字面值宣告禁用符號,不得因此自我觸發 |
| `test_b0_invariants_module_does_not_trip_itself` | 守衛模組本身不得違規 |

**結果:`tests/test_b0_regime_invariant.py` 10 passed;與 `tests/test_b0_cost_model.py` 合計 47 passed。**

**反向控制的意義:** 若只測「B0 沒有違規」,一個永遠回傳空清單的壞偵測器也會通過。反向控制證明偵測器對**真正的**違規會失敗 —— 這是本專案「fail-loud 而非靜默通過」原則在測試層的落實。

---

## 3. 現況與生效條件

```
B-17 invariant           : DECLARED + ENFORCED
B-17 current scope       : B0_ENTRY_MODULES = ("core.b0_cost_model",)
B-17 full enforcement    : PENDING B0 execution route
```

**與 G14-4 完全相同的生效機制:B0 execution route 組裝完成時,其進入模組加入 `B0_ENTRY_MODULES`,B-17 與 G14-4 即自動對它機械執行,測試碼一行都不用改。**

**現階段能證明的:** B0 目前已存在的生產模組(成本模型)不可達任何 regime 決策路徑。
**現階段不能證明的:** 尚不存在的 B0 execution route 亦然 —— 那要等它存在。**本文件不宣稱已證明後者。**

---

## 4. 與先前裁決的關係

- 使用者 Phase 2 裁決「**移除 regime 對 alpha score 的動態乘數**」是**規格層**的決定;B-17 是它的**執行層防護**。兩者不重複:前者說「不要這樣設計」,後者說「就算有人這樣寫了,測試會擋下」。
- Frozen A 的 regime 程式碼**一律保留、未修改**(`core/regime.py`、`core/advisor.py`、`core/backtest.py` 皆未動)。B-17 禁止的是**可達性**,不是**存在性** —— 這與 B-14 對 legacy 成本常數採取的處置一致(保留舊常數、確保 B0 不可達),也保住了 Frozen A 的 audit trail。

---

## 5. 未涵蓋 / 誠實限制

1. **靜態分析涵蓋 import 與識別名引用,不涵蓋動態存取**(`getattr(mod, "regime_" + x)`、`importlib` 動態載入、設定檔驅動的 dispatch)。B0 若引入此類寫法,本 guard 不保證偵測得到。
2. `REGIME_DECISION_SYMBOLS` 是**列舉式**清單 —— 未來若新增其他 regime 決策符號,須同步加入,否則不在保護範圍。
3. 本不變量證明的是**「regime 不回流決策」**,**不是**「B0 的 regime 處置在投資上是對的」。後者是績效問題,不在 B-17 範圍,且依現行規則不得在此討論。

---

## 6. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_invariants.py` | 可達性機制 + B-17 / G14-4 兩組禁用清單 |
| `tests/test_b0_regime_invariant.py` | B-17 不變量、G14-4、兩組反向控制、機制自檢(10 tests) |
| 本文件 | B-17 closure |

**Frozen A 驗證:`git diff --stat core/regime.py core/backtest.py scripts/l4b_execution.py scripts/portfolio_simulator_lab.py tests/test_canonical_universe.py` 為空。**
(`core/advisor.py` 有 4 行差異,為本 session 開始前即存在的未提交變更,非本輪產生。)

---

**本輪未執行回測、未產生績效 / IC / Sharpe / 選股名單、未做參數掃描。未 stage、未 commit。**
