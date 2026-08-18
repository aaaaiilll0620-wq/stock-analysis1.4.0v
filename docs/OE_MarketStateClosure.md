# O-E · Market-State Source Closure（含 O-E-1）

**日期:** 2026-08-18
**狀態:** O-E `CLOSED` / O-E-1 `FROZEN` / **🔴 新增 D-1 blocking data requirement**
**合規:** 純規格與資料稽核。**未執行任何報酬 / IC / Sharpe / CAGR / MDD / 選股名單，未動 A0–A3。** Frozen A 七檔未修改（已核對）。未 stage、未 commit。

> **規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.2 §2.7 / §2.8。本文件為 rationale 與稽核紀錄。**

---

## 0. 先講結論

**O-E 的四件事都關掉了，而且來源是真實存在的。** 但稽核來源的過程中查出一件比 O-E 本身嚴重得多的事：

> **價格 export 在 2019 年之後只包含匯出當下仍上市的證券。141 個窗口月中有 87 個月（62%）的投資母體受存活者偏誤污染。**

這已登記為 **D-1 blocking data requirement**，阻擋 `S-3a`、`final_provenance_seal` 與 `L2_opening`。

**這正是先關 O-E 再開工的價值：** O-B 的守衛在 runtime 也會抓到（90 個無法解釋的缺口），但那會發生在 seal 之後。在資料層先抓到，代價差了一個數量級。

---

## 1. O-E 的四件事

### 1.1 交易日曆 —— `taiex_daily`，5,565 個已觀測 session

**只使用已觀測 session。**「指數在 d 日有交易」在 d 日即可知，因此對 O-B 的 `<= as_of` 查詢是**建構上 PIT-safe**。

**明文不使用預先公布的休市日程表。** 那正是讓站在 t 的 replay 斷言「未來本來就知道會休市」的入口。

**機械強制：完整日曆不可達。** `TradingCalendar` 沒有 `.sessions`，只有 `sessions_through(as_of)`；`as_of` 超出涵蓋即 abort，不靜默回傳全部。

### 1.2 停牌 / 交易狀態 —— `暫停交易`，1,946 列

| 檢查 | 結果 |
|---|---|
| 是否為當期快照 | ❌ **不是** —— 是歷史 effective-date 表 |
| 欄位 | `證券代碼` / `年月日` / `恢復交易日` / `暫停交易原因`，**四欄 100% 非空** |
| 涵蓋 | 2004-01-12 .. 2026-08-10 |
| 匯入後 | **3,700 筆 / 1,043 檔**（suspended 1,756、delisted 190、listed/復牌 1,754） |

**只知道最新狀態的來源標記 `NOT_PIT_SAFE`，不得進入 B0，且不予修補** —— 「把今天的狀態套到歷史」正是 `industry_map` 的缺陷（49.4% 股票換過產業）。機械強制：`SourceContract.assert_pit_safe()`。

### 1.3 狀態語義 —— 四態，`unknown` 不是 `listed`

`listed` / `suspended` / `delisted` / `unknown`。

**`unknown` 是紀錄的缺席，不是一種申報狀態** —— `StatusRecord` 拒絕以 `unknown` 建構。缺席在沒有東西要解釋時無害；**一旦出現價格缺口，缺席的紀錄什麼都不解釋 → abort**（`assert_unknown_is_not_normal`）。

`恢復交易日` 另外寫成一筆 `listed` 紀錄，讓復牌可以**取消**先前的停牌，而不是讓停牌永遠解釋下去。

### 1.4 Provenance

每個來源申報 importer version、schema hash、content hash、涵蓋範圍，並轉為 B-21 `DatasetProvenance`。**回傳未版本化狀態的 runtime API 不是合格來源** —— 缺任一欄即 abort。

---

## 2. O-E-1 · availability semantics

```
explains_session(s)  ⟺  available_from < s  AND  effective_from <= s
```

**`effective_from <= s` 不足夠。** 盤後才申報的停牌仍然帶當天的日期；用它解釋當天的缺價是**穿著正確日期外衣的 look-ahead**。因此是**嚴格早於**。

**`available_from` 無預設值。** 把它預設為 `effective_from` 等於默默斷言了正需要被證明的那件事。

### 這條規則對 `暫停交易` 的實測後果（非推論）

`available_from = 年月日`，配合嚴格規則只解釋**之後**的 session。代價實測：

| 情形 | 件數 | 後果 |
|---|---|---|
| `年月日` 當天**仍有價格** | **1,529（78.8%）** | 嚴格規則零成本 —— 那天本來就沒有缺口要解釋 |
| `年月日` 當天**無價格** | 411（21.2%） | 首個缺價 session 就是 `年月日`，**執行會 abort** |

那 411 筆依原因拆解，以 `併入控股公司下市`(85)、`違規財報`(83)、`合併下市`(71)、`違規退票`(21) 為主，而 `減資`(740 有價/18 無價)、`現金減資`(355/4) 幾乎都有價。

**⇒ abort 集中在下市與違規案例，那正是 §2.4 的不可重建身分轉換。** 在那裡 abort 是正確行為，不是誤報。

---

## 3. 🔴 D-1 · 稽核來源時查出的存活者偏誤

### 3.1 觸發線索

O-B 的缺口涵蓋率測試顯示：窗口內 166 個 terminal gap，**只有 63 個能被停牌表解釋，103 個不能**。而且不能解釋的那些呈現群聚 —— 大量證券的價格序列停在**同一天 2018-12-28**。

### 3.2 第一層排除：不是我們的 importer

原始 TEJ export 逐年檔實測：這些證券在 `2018DataExport.xlsx` 中完整存在到 2018-12-28，在 `2019DataExport.xlsx` 中**完全不存在**（不是部分年度資料，是整檔缺席）。**所以不是快取或匯入的問題。**

同時也說明 `2018-12-28` 這個共同日期是**逐年檔案 + 整年缺席**的假影 —— 一檔證券只要整個 2019 年缺席，它的「最後日期」就必然是 2018 的最後一個 session，與它實際何時離開無關。

### 3.3 決定性測試：逐年流失率

```
2012:14  2013:11  2014:16  2015:14  2016:20  2017:18     ← 正常汰換,無一交易到年末
2018:110  ← 其中 90 檔一路交易到 2018 最後一個 session
2019:0  2020:0  2021:0  2022:0  2023:0  2024:0           ← 六年零下市
```

**六年零下市不是市場事實。** 而且 90 檔 ÷ 7.5 年 ≈ 12/年，**與 2018 之前的正常汰換率（11–20/年）完全吻合** —— 這 90 檔就是 2019–2026 期間陸續下市、而被 2019+ vintage 整批排除的那些。

### 3.4 獨立證據：74/90 可證明在 2018 之後仍存在

| 測試 | 結果 |
|---|---|
| **T1** 在 `配股相關` 語料中有 2018 之後的事件 | **57/90**（最晚 `3426` 至 2026-08-11） |
| **T2** 有下市型停牌紀錄且日期在 2018 之後 | **52/90**（全部 52 筆都在 2018 之後） |
| **聯集** | **74/90** |
| 對照組：300 檔仍在報價的證券有 2018 後事件 | 184 —— **語料本身確實涵蓋 2018 後** |

最刺眼的例子：**`1701` 於 2024-08-21 併入控股公司下市，但其價格序列停在 2018-12-28 —— 遺漏約 5.6 年的真實交易。**

### 3.5 影響

**2019+ 的 vintage 只含 export 當下仍上市的證券。** 在 141 個窗口月中，2019-01 之後的 **87 個月（62%）** 投資母體受污染。

受影響者：逐期 complete-case 母體數、eligibility 淘汰組成、**階梯第 ① 列「等權母體」基準**、以及任何回溯結果 —— **全部向上偏誤**，因為下市股通常表現最差。第 ① 列同時是「選股能力」那一格的分母，所以偏誤不會在相減時抵消。

### 3.6 處置

**不得由存活者反推缺失名單。** 唯一補救是**重新匯出 2019–2026 價格並納入下市證券**，做法與 `配股相關` export 已經做到的一致（那份就涵蓋上下市）。

已登記為 blocking data requirement，機制與 V-1b 完全相同：

```python
BlockingDataRequirement(key="price_universe_survivorship",
                        blocks=("S-3", "final_provenance_seal", "L2_opening"))
```

驗證器 `verify_price_universe_churn()` 對兩種型態各自 fail：**零流失年份**、**交易到年末卻整個消失**。

> **⚠ V-1b CLOSED 不等於「資料 blocker 已全解」。** 目前 `unmet_blocking_requirements()` 回傳 `['price_universe_survivorship']`，且已寫入 `master_prereg_freeze.json`，讓讀者不會把「規格已凍結」誤讀為「可以 seal」。

---

## 4. 產出與驗證

| 檔案 | 內容 |
|---|---|
| `core/b0_market_state.py` | SourceContract / TradingCalendar / SecurityStatusTable / O-E-1 |
| `core/b0_pit_observability.py` | 欄位改名 + O-E-1 嚴格性 |
| `core/b0_frozen_spec.py` | D-1 requirement + `verify_price_universe_churn` |
| `core/b0_master_prereg.py` | +5 個 O-E spec key |
| `tests/test_b0_market_state.py` | 28 項（`test_b0_pit_observability.py` 同步增至 27） |
| `research/p1a_o_e_market_state/` | 4 個探查/匯入腳本 + 4 份 JSON |
| `data/b0/trading_calendar.csv` · `security_status.csv` · `price_universe_churn.csv` | 匯入產物 |

**變更登錄於 master prereg §11：C-14（O-E-1 收緊）、C-15（新增 D-1）。**

```
全庫 1580 passed, 2 skipped     (排除一個既有的時間相依測試,見下)
Frozen A 七檔 git status 全空
spec_sha256 (v1.2) = fe4bd3b38cab219e3b77571988dd31862b9ee2dbcd5c3113ea123898488e8483
UNMET BLOCKING = ['price_universe_survivorship']
```

**與本輪無關的既有失敗：** `tests/test_dataexport_runtime_overlay.py::test_runtime_overlay_date_normalization_keeps_daily_union_sortable` 使用寫死的 fixture 日期（最新 2026-08-10），而 `core/data_provider.py` 有 7 天新鮮度閘門，日曆一跨過就必然回 `None`。**與 O-E 無關，是既有的時間相依測試脆弱性。** 未修改（不在本輪範圍）。

---

## 5. 下一步

```
D-1  重新匯出 2019-2026 價格並納入下市證券   ← 阻擋 seal 與 L2,不擋 P-1b
P-1b 四層 canonical core                     ← 可以開工
```

**D-1 與 P-1b 正交**，可以並行：core 邏輯不依賴價格母體的完整性，但 final seal 依賴。
