# D-1 · Price Universe — Repair Status

**日期:** 2026-08-18
**狀態:** 🔴 **`price_universe_survivorship` = UNMET（未關閉）** · 驗證器已強化並跨來源化 · 來源 quarantine 已上線
**合規:** 純資料稽核與驗證器。**未執行 L2、未計算 CAGR / Sharpe / MDD / IC / win rate、未產生或檢視選股名單、未比較 Frozen A、未使用 A0–A3、未修改 feature / eligibility / portfolio / execution / cost 規格。** 未 stage、未 commit。

> 規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.8 §2.8。本文件為 rationale 與稽核紀錄。

---

## 0. 先講最重要的

**D-1 沒有關閉，而且本輪無法關閉。**

D1-1（source completeness）要求的是一份**重新匯出、含歷史下市證券的 2019–2026 價格母體**。該檔案不存在 —— `tej_exports/DataExport0806/個股股價、本益比2004-20260806/` 仍是 2026-08-08 的同一份 vintage，repo 內也沒有其他含下市股的價格來源。

**我沒有、也不會用「把觀察到的 90 檔補回去」來讓 verifier 過。** 那正是被明文禁止的做法，而且會產生一個為錯誤理由通過的驗證器。

本輪交付的是 D1-2 ~ D1-7：把驗證器從自我參照升級為跨來源、threshold-free，並證明它抓得到我們實際遇到的污染。

---

## 1. 一個必須先更正的錯誤

我在建立獨立參照時，第一版用 `上市別 ∈ (TSE, OTC)` 篩選 `公司資料.xlsx`，得到「每年 missing = 0」的結論，差點據此宣稱 master 也被污染。

**那是錯的：已下市證券的 `上市別` 會被改寫。** 90 檔全部變成 `UNPUB`/`PUB`，所以該篩選正好排除掉稽核要找的對象。2,461 檔曾在交易所掛牌者中，**505 檔現在標為 UNPUB/PUB**。

正確做法是取**歷史上市日欄位**（`TSE上市日` / `OTC上市日`），它們不會被改寫。更正後 master 完全可用：90 檔全在裡面，且帶真實下市日（`1701` = 2024-09-02，與先前查到的 2024-08-21 停牌一致）。

**這與 `industry_map` 是同一類缺陷 —— 當期標籤套到歷史 —— 也是 `公司資料.xlsx` 只能稽核、永不可作為 B0 runtime 來源的理由。**

---

## 2. D1-2 · 年度母體 churn（跨來源）

| 年 | 參照預期母體 | corpus 觀測 | missing | (%) | 觀測流出 | 參照預期流出 |
|---|---:|---:|---:|---:|---:|---:|
| 2012 | 1,494 | 1,621 | 5 | 0.33 | 14 | 14 |
| 2013 | 1,539 | 1,650 | 4 | 0.26 | 11 | 13 |
| 2014 | 1,577 | 1,700 | 2 | 0.13 | 16 | 10 |
| 2015 | 1,621 | 1,735 | 4 | 0.25 | 14 | 11 |
| 2016 | 1,668 | 1,773 | 7 | 0.42 | 20 | 23 |
| 2017 | 1,686 | 1,795 | 4 | 0.24 | 18 | 17 |
| **2018** | 1,731 | 1,817 | 3 | 0.17 | **110** | 19 |
| **2019** | 1,747 | 1,734 | **92** | **5.27** | **0** | 15 |
| **2020** | 1,762 | 1,764 | **78** | **4.43** | **0** | 18 |
| **2021** | 1,773 | 1,808 | **62** | **3.50** | **0** | 15 |
| **2022** | 1,805 | 1,843 | **47** | **2.60** | **0** | 17 |
| **2023** | 1,821 | 1,886 | **30** | **1.65** | **0** | 8 |
| **2024** | 1,870 | 1,934 | **22** | **1.18** | **0** | 10 |
| **2025** | 1,933 | 1,951 | **12** | **0.62** | **0** | 8 |

**2012–2017 是乾淨的控制組** —— 觀測流出與參照預期同量級，missing 0.13–0.42%。

**2019–2025 觀測流出全為 0，而參照說每年有 8–18 檔下市。** 這是直接的跨來源矛盾，不需要任何人工門檻。

missing 由 92 遞減至 12 也正是存活者偏誤的簽名：2019 下市者只缺 2019；2024 下市者缺 2019–2024。

---

## 3. D1-3 · `2018-12-28` 群聚

| 日期 | corpus 終止檔數 | 參照該日下市數 |
|---|---:|---:|
| **2018-12-28** | **90** | **0** |
| 2018-09-17 | 6 | 0 |

**該群聚仍然存在**（新來源尚未產生，故無 regression 可驗）。參照把那 90 檔的下市歸屬於 2019–2024，**沒有一檔在 2018-12-28 下市** —— 群聚是逐年檔案邊界的假影。

修復後的驗收條件（**不是**「90 檔全部回來」）：C2 不再觸發，且 C1 在 2019–2025 不再觸發。

---

## 4. D1-4 · Known-case validation

以參照的 `下市日期` 驅動，**非固定名單**：

| 證券 | 參照下市日 | corpus 最後價格 | 遺漏 |
|---|---|---|---|
| `1704` | 2019-01-30 | 2018-12-28 | ~1 個月 |
| `1566` | 2019-07-31 | 2018-12-28 | ~7 個月 |
| `1262` | 2019-10-14 | 2018-12-28 | ~10 個月 |
| `1902` | 2020-06-01 | 2018-12-28 | ~1.4 年 |
| `1724` | 2021-11-01 | 2018-12-28 | ~2.8 年 |
| `1507` | 2022-04-21 | 2018-12-28 | ~3.3 年 |
| `1258` | 2023-06-09 | 2018-12-28 | ~4.4 年 |
| `2358` | 2024-11-19 | 2018-12-28 | ~5.9 年 |
| `1701` | 2024-09-02 | 2018-12-28 | ~5.7 年 |

**348 檔序列提早終止者，全部（348/348）在 master 中帶有 `下市日期`。** 沒有一檔是「master 也不知道的證券」。

---

## 5. D1-5 · 舊污染來源的反向控制

```
tests/test_b0_price_universe.py::test_D1_5_the_real_contaminated_audit_fails   PASSED
tests/test_b0_price_universe.py::test_D1_5_a_clean_audit_passes                PASSED
```

**真實的污染稽核餵進 verifier → FAIL**，且 C1 明確指名 2019–2022；**合成的乾淨稽核 → PASS**；兩者走**同一個函式**，沒有只給舊資料跑的 strict mode。

---

## 6. D1-6 · 來源可達性

```
includes_delisted == False                                  → abort
content_sha256 ∈ quarantined                                → abort
非 synthetic 的 retrospective replay 未宣告 price_source     → abort
```

**Quarantine 依 content hash，不依路徑** —— 改名或複製受污染的匯出不得使其洗白（有測試釘死）。受污染 corpus 指紋 `aeda65b99ec9d4b4e02f96e20e3d915c5519329d010415f2be3e4cb667ea49c1`（2,300 檔 / 9,009,907 列 / 2004-01-02 .. 2026-07-14）已登錄。

`core.b0_price_universe` 已加入 `B0_ENTRY_MODULES`，故 B-17 / B-19 / G14-4 不變量一併適用。`TEJ_RUNTIME_OVERLAY_DIR` 仍在 B-19 `OVERRIDE_SYMBOLS` 且 `B0_REGISTERED_OVERRIDES = {}`，堵住由 overlay 重新引入的路徑。

---

## 7. D1-7 · Provenance

`PriceSourceContract` 要求 importer version / schema hash / content hash / coverage / securities / **audit hash** / lineage，缺任一即 abort，並轉為 B-21 `DatasetProvenance`。有測試明文釘住「**寫在 closure 文件裡的 hash 不算 provenance**」。

新來源落地時，`master_prereg_freeze.json` 會一併記錄其 hash 與 audit hash。

---

## 8. 判準只增不減（必須明說）

原 source-only 驗證器 `verify_price_universe_churn()` **完整保留為 backstop**，新舊**必須同時通過**。本輪新增的是跨來源 C1/C2，**沒有放寬任何條件**。本 corpus 在新舊兩套下都 FAIL。

規模（`unexplained_missing_though_listed`：2019 年 75，遞減至 4）**只報告不設閘** —— 把它變成 gate 需要選一個「多少缺失可以接受」的數字，而那個數字沒有可辯護的來源。

---

## 9. 要什麼才能關 D-1

**重新匯出 2019–2026 個股日價格與本益比，勾選包含歷史下市 / 併購 / 終止交易的證券**（與 `配股相關` 及 `2005-2018 三大財報+ROE 上下市.xlsx` 已經做到的一致）。

驗收由資料本身判定：

1. `exits_observed > 0` 於 2019–2025 每一年（C1 不觸發）
2. `2018-12-28` 群聚消失（C2 不觸發）
3. source-only backstop 同時通過
4. `PriceSourceContract.includes_delisted = True` 且 content hash 不在 quarantine

**不需要「90 檔全部回來」** —— 那只是 regression evidence，不是 pass condition。

---

## 10. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_price_universe.py` | C1/C2 gate、quarantine、`PriceSourceContract` |
| `core/b0_frozen_spec.py` | D-1 改讀跨來源稽核，backstop 並行 |
| `core/b0_adapter_retrospective.py` | 非 synthetic replay 必須宣告且通過來源閘 |
| `core/b0_invariants.py` | `B0_ENTRY_MODULES += core.b0_price_universe` |
| `tests/test_b0_price_universe.py` | 35 項（含 D1-5 反向控制） |
| `research/d1_price_universe/` | 稽核 / 指紋 3 個腳本 + 2 份 JSON |
| `data/b0/price_universe_audit.csv` · `price_universe_clusters.csv` | verifier 讀的稽核產物 |

**變更登錄於 master prereg §11：C-38。**
