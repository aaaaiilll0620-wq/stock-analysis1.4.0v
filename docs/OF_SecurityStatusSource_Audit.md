# O-F · PIT Security Status Source Audit（20260818 vintage）

**日期:** 2026-08-18
**狀態:** 🔴 **O-F 仍 OPEN** —— 新的 `暫停交易` 匯出**沒有**關閉缺口；`事件+下市` **也不能**關閉它
**合規:** 未執行 L2、未計算 CAGR / Sharpe / MDD / IC / win rate、未產生或檢視選股名單、未比較 Frozen A、未使用 A0–A3、未修改 feature / eligibility / portfolio / execution / cost 規格。未 stage、未 commit。**未對 O-F 自行裁決。**

> 規範性內容在 `docs/FrozenB0_MasterPreregistration.md` v1.10 §12.2 與 C-40。本文件為 rationale 與稽核紀錄。

---

## 1. 盤點

`tej_exports/DataExport0806/暫停交易2004-20260818/` —— 七個 zip，兩種 schema。

| 檔案 | bytes | 列 | sha256（前 16） |
|---|---:|---:|---|
| `暫停交易2004-2007.zip` | 4,926 | 296 | `c53639d13babf8e0` |
| `暫停交易2008-2011.zip` | 5,134 | 302 | `c8d3a7e3368e2633` |
| `暫停交易2012-2015.zip` | 4,688 | 264 | `ab1b184366a1443d` |
| `暫停交易2016-2019.zip` | 10,664 | 489 | `618f3edb738ce7db` |
| `暫停交易2020-2023.zip` | 8,186 | 384 | `8e660a96dcca78a9` |
| `暫停交易2024-20260818.zip` | 6,181 | 215 | `67dd2f6efb9482e2` |
| `事件+下市.zip` | 41,226 | 2,440 | `571f67ac76b1a27e` |

UTF-16 TSV。六個 `暫停交易` zip 的 schema **完全一致**。

**暫停交易：** 4 欄 `證券代碼 / 年月日 / 恢復交易日 / 暫停交易原因`
`schema_sha256 = 8e58f979…4112633` · `content_sha256 = ca896a91…97ac8641`
**1,950 列 / 1,046 檔 / 2004-01-12 .. 2026-08-18** · 2004–2026 **每一年都有列，無缺年**
不可用：2 列無 `恢復交易日`、2 列無原因

**事件+下市：** 8 欄 `證券代碼 / 危機發生日 / 危機發生迄日 / 危機事件大類別(+說明) / 危機事件類別(+說明) / 下市日期`
`schema_sha256 = 6a3a…`（見 JSON）· **2,440 列 / 2,440 檔（每檔恰好一列）**

**舊 vintage：** `暫停交易2004-20260806` 已由使用者刪除。其 raw sha256 **從未被記錄**（當時由 xlsx 匯入，只對 derived artefact 指紋），因此**不要求舊檔重新存在**；其量測值保留於 `research/of_security_status/prior_of_diagnostic.json`。

---

## 2. `暫停交易` 語義實測（O-E 要求證明，不接受宣告）

對照 D-1 canonical 價格 corpus 的 session 級 presence index（新建，見 §3）。

| 檢驗 | 結果 |
|---|---|
| **E-1 `年月日` 是 effective date 還是公告日** | **1,658 / 1,950（85.0%）在該日仍有價** → 是 effective date，停牌自**次一** session 起算；**不含任何公告時點資訊** |
| **E-3 `恢復交易日` > `年月日`** | 1,947 / 1,948；1 筆相等；0 筆早於 |
| **A-1 availability 欄位** | **不存在**。`available_from` 只能用宣告，O-E-1 因此是唯一界限 |

**E-2 揭露了一個語義斷裂：**

| 原因分群 | 列數 | 宣告區間內完全有價 | 完全無價 |
|---|---:|---:|---:|
| **減資／現金減資／面額變更** | 1,148 | **1,135** | 10 |
| 下市／合併／併入／終止 | 190 | 34 | 123 |
| 其他停牌 | 612 | 64 | 156（另 386 筆區間長度為 0，屬盤中暫停） |

**58.9% 的列描述的是停止過戶期間，不是停牌。** `2412 中華電` 2007-12-21→2008-01-09「現金減資」區間內 11 個 session **全部有價**。

目前 importer 一律標 `suspended`，屬 **over-claim**；因為這些區間內根本沒有缺價，**實測無害**，但語義錯誤已登記於 C-40。**本輪未改推導規則**（那會是 specification-by-code）。

---

## 3. 量測代理的缺陷（前次 12 + 7 被上修為 289）

前次 O-F 診斷以 `price_observed_through = min(series_last, as_of)` 近似。這讓**任何在 as_of 之後仍有價的證券必然被判為 CURRENT**，唯一會被標記的是「最終價格日早於 as_of」—— 一個 as_of 之後才知道的事實。

改為 session 級 presence index：

```
data/b0/price_presence.parquet
9,130,763 列 / 2,306 檔 / 2004-01-02 .. 2026-08-17
與註冊價格來源同一 vintage boundary（<=2018 既有 cache，>=2019 20260817 重新匯出）
```

**同一 as_of、同一 production classifier：12 + 7 → 289。** 這是量測修正，不是資料變壞。

---

## 4. 三個 audit（皆為診斷，皆非 gate）

**A · as-of 快照 @ 2020-06-29**（2,103 檔）

| 分類 | 數 |
|---|---:|
| CURRENT | 1,811 |
| EXPLAINED_SUSPENSION | 3 |
| **UNEXPLAINED_GAP** | **289**（O-E-1 同日 122 / 無狀態紀錄 48 / 其他 119） |

**B · 全 corpus 終止缺口**

| 成因 | 數 |
|---|---:|
| 至 corpus 末仍在交易 | 1,954 |
| **由 `暫停交易` 解釋** | **66** |
| 卡在 O-E-1 同日規則 | 186 |
| 完全無狀態紀錄 | 45 |
| 其他 | 55 |
| **無解釋合計** | **286 / 352** |

年代分布橫跨 2004–2026（2005 年 31 檔最多），**不是單一時代的問題**。

**C · 內部缺口** —— 119 段，115 段無解釋，涉 96 檔。經 P-6 二分後見 §6。

**前次 15 個具名案例：15 個全部仍無解釋，0 個被新來源解決。**（僅作報告，非 pass list。）

---

## 5. `事件+下市` 的 PIT 判定

| 檢驗 | 結果 |
|---|---|
| **P-1 形狀** | 每檔一列、**無 record-level effective date** → SHAPE 是當期快照 |
| **P-2 前瞻內容** | 匯出日之後仍有 2 筆 `下市日期`（`2867` 2026-09-01、`5371` 2026-09-03）→ **證明 TEJ 在事件前即建檔**，但表中不含前置時間長度 |
| **辨識涵蓋率** | **286 / 286（100%）** —— 每一檔無解釋的終止在事件表都有 `下市日期` |
| **P-3 `下市日期` vs 首個缺價 session** | **之前 4 / 同日 94 / 之後 188** |
| **P-4 `危機發生日` 嚴格早於首個缺價 session** | 58 / 286（118 檔根本沒有危機日） |

**結論：`下市日期` 指得出「誰」離場，指不出「何時可知」。** 作為 `available_from` 在最需要它的 282/286 個案例上失效。**未提升為 runtime source。**

**最佳情況上界（假設兩欄都在自身日期即可得，而 P-3 已否證其一）：286 → 227 仍無解釋。**

---

## 6. P-6 · 內部缺口二分，以及第二個當期快照缺陷

| 類型 | 段數 |
|---|---:|
| **離場後再上市**（母表 `listed_from` 晚於缺口起點） | **27** |
| **真正的在市中缺口**（長度 2 .. 842 session） | **88** |

離場再上市範例：

| 證券 | 缺口起點 | 長度(session) | 母表 `listed_from` |
|---|---|---:|---|
| `8102 傑霖科技` | 2005-08-31 | 4,474 | 2023-10-27 |
| `3135 凌航` | 2005-11-04 | 3,961 | 2021-11-22 |
| `8089 康全電訊` | 2005-05-03 | 3,303 | 2018-08-31 |
| `6606 建德工業` | 2009-09-04 | 2,555 | 2020-01-09 |

**⚠ 27 檔中只有 2 檔在事件表留有 `下市日期`**，其餘 25 檔的 `下市日期` 與母表 `delisted_on` **皆為空**。兩表都是每檔一列的當期快照，證券回來後前一段上市歷程被覆寫 —— 與 `上市別`、`industry_map` **同一類缺陷**。

**這些早期離場只有價格 corpus 記得，任何已註冊來源都不記得（PIT 與回溯皆然）。**

**D-1 未被推翻：** D-1 只檢查終止日；再上市證券的終止日就是 corpus 末日，內部缺口從來不在其視野內。D-1 重跑結果逐項不變（§8）。

---

## 7. 裁決選項矩陣（實測殘留，非建議）

| 放寬項 | 殘留無解釋 |
|---|---:|
| 現況 | **286** |
| 只放寬 O-E-1 同日規則 | 100 |
| 只採 `危機發生日` 為 `available_from` | 228 |
| 只採 `下市日期 ≤ 首個缺價日` | 188 |
| O-E-1 + 危機日 | 74 |
| 三者全開 | 2 |

**⚠ 第三列是最容易被伸手去拿、卻正是 P-3 證明不成立的那一項** —— 它讓一個在缺價當日才成立的日期去解釋當日缺價，正是 O-E-1 禁止的事。

**本輪不裁決。**

---

## 8. 回歸

| 項目 | 結果 |
|---|---|
| D-1 驗證器 | 逐項不變：security-level 2 檔、`2018-12-28` ABSENT、known cases **98/98**、2019–2025 流出 16/17/15/17/8/11/7 |
| `unmet_blocking_requirements()` | `[]` |
| OPEN SPEC ITEMS | 0 |
| adapter 驗證 | `config_hash 27fee343…d13f03`、`state_hash 56d42ca0…81f13be` —— **與換源前逐位元相同**（持倉集合經實測為同一 20 檔） |
| route invariants | G14-4 / B-17 / B-19 各 0；foreign mutations 0；overrides 0 |
| 測試 | `tests/` **1794 passed, 2 skipped, 0 failed** |
| Frozen A | 七檔未修改（`scripts/l4b_execution.py` 仍為既有未追蹤狀態） |

`spec_sha256` (v1.10) = `93f40c28e00dd8d1b853dee48139d78c0a07b4fe006a02613e28e3692acad347`

---

## 9. 產出

| 檔案 | 內容 |
|---|---|
| `research/of_security_status/ingest_status_export.py` | 盤點 + hash + schema + 語義驗證 |
| `research/of_security_status/build_price_presence.py` | session 級 presence index |
| `research/of_security_status/audit_status_coverage.py` | audit A / B / C |
| `research/of_security_status/audit_event_table.py` | `事件+下市` P-1 .. P-6 + 選項矩陣 |
| `research/of_security_status/prior_of_diagnostic.json` | 被取代的前次診斷（audit trail） |
| `data/b0/price_presence.parquet` · `security_status.csv` | 衍生資料 |
| `research/p1a_o_e_market_state/build_market_state.py` | importer 升版 `@2`，改讀 zip |
