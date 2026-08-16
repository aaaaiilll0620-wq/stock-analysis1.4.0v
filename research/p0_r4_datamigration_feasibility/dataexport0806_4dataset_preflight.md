# DataExport0806 四資料集 Feasibility Preflight — R3-S/R3-P 解除可行性

**目的**：在投入完整 2.2GB candidate build 前，唯讀判斷 DataExport0806 是否足以解除 P0-R3 對 `monthly_revenue`/`financial_statements`/`institutional_gross`/`tdcc_weekly` 判定的 R3-S/R3-P 核心阻塞。
**執行日期**：2026-08-16　**repo HEAD**：`47d185231d49d87bfa7d37d9d3864a1d071513f0`
**方法**：`openpyxl`(`read_only=True`)直接讀取原始 `.xlsx`，只讀回答問題所需的欄位；**不呼叫** `tej_importer.py`/`build_v2_candidate.py`/verifier 任何函式；不建 candidate cache、不建 lock、不跑 parity/績效；每個資料集只讀最少代表性檔案(見各節「證據」)。**本輪唯二新增檔案**：本報告 + 同目錄 JSON。未 stage/commit、未修改 importer/cache/production/Scheduler。

**本輪(第三輪)修正說明**：三項狀態被下修/更正,理由都是「先前的措辭把『可行/有資料』跟『已經解除』混為一談,或樣本不足以宣告 PASS」：
- `financial_statements`:`PASS` → **`DATA_AVAILABLE_IMPLEMENTATION_REQUIRED`**——真實 release_date 存在是真的,但 production 的消費端(`core.tej_bundle._to_long`)並未讀它,R3-P **未解除**。
- `institutional_gross`:`PASS` → **`PARTIAL_FEASIBLE`**——16 份檔案只抽查了 4 份表頭 + 1 份內容,不足以宣告全 corpus PASS。
- `tdcc_weekly`:是否為 A-leg 必要輸入,從上輪的 `NOT_REQUIRED` **翻案為 `REQUIRED_BY_A_LEG_INDIRECTLY`**——上輪的全庫搜尋漏掉了 `beat_0050/realbody/`,本輪已獨立重新讀原始碼驗證出完整鏈路(見 §4c)。另外,`年月日` 只確認是良好的 as-of 觀察日,**真實對外可得性/lag 未經證明**,R3-P 對 `tdcc_weekly` 維持 `UNRESOLVED/FAIL`。
- `monthly_revenue` 的 2013+ 發現維持不變(上輪已確立)。`tdcc_weekly` 新語料的 2013+ 涵蓋(§4b)本輪唯讀重新核對過,數字跟使用者提供的完全吻合,維持不變。

**結論先講**：**沒有找到足以證明「完整 build 無法解除 R3-S/R3-P」的決定性 blocker**,但也**沒有任何一個資料集的 R3-P 已經真的解除**——全部停在「資料面可行」跟「code 面未實作/未證明」之間。**2013-01→2026-03 identity 窗口目前只是本輪對話中浮現的提案,尚未經過本研究自己的 prereg/erratum 正式核准機制,不構成範圍變更。**

---

## 1. monthly_revenue — **PARTIAL**

**唯一原始檔**：`月營收2004-202608/20260806091706.xlsx`(sha256 `237e13ab...`,manifest 確認,478,127 列)

| 檢查項 | 結果 | 細節 |
|---|---|---|
| 2004/2005-2026 歷史涵蓋 | **PASS** | 單一檔案涵蓋 2004-01→2026-07,逐年列數皆 >0,遠超 255 個月目標範圍(2005-01→2026-03) |
| 真實公告/發布日期欄位(`營收發布日`)缺失率 | **PARTIAL** | 欄位本身逐列都「非空白」(0% blank),但**精確分類**(genuine 可解析日期 vs 文字佔位符 `.`)顯示硬性分界:**2004-2012(9整年,255 個月中的 96 個月)每一列都是 `.` 佔位符,不是真實日期**;2013 起~100% 是真實可解析日期(2022-2026 有零星 <0.1% 的 `.`)。這比先前 tej_cache 快照已知的「僅 2019+ 真實」是**實質進步**(往前延伸到 2013),但**仍非完整 255 個月**。 |
| 能否依既有正式公式重建 `revenue_yoy` | **PASS** | `revenue_yoy` 不需要從其他欄位「重建」——原始欄位 `單月營收成長率％`(即 DATASETS 既有映射的 `revenue_yoy_pct`)本身就是實際 B-leg 篩選程式(`scripts/tej_universe_screen_validation.py`)直接消費的那個數字,不經任何重算。此欄位 2004-2026 每年填值率 94.0%-99.5%(其餘同樣是 `.` 佔位符,推測是新上市/無去年同期比較基期造成,非涵蓋率崩潰)。**但這只確認「數值存在」,不等於「該數值在歷史上何時已知」(見上一列)——本研究非-claim 3 明文兩者不得混為一談。** |

**下一步**(若 Track B 另外獲授權)：`monthly_revenue` 必須拆成兩段獨立記錄——**2013-01→2026-07(genuine_evidence_fraction=1.0,可進入 Gate R4-P 考量)** 與 **2005-01→2012-12(genuine_evidence_fraction=0.0,依 Track A non-claim 1 必須宣告 `NOT_RECONSTRUCTIBLE`,不得用現值替代)**。`revenue_yoy` PIT 可用性的**完整 255 個月 exact identity 從這份原始來源本身不可行**;可行的是縮減後的 168/255 個月真實窗口。

---

## 2. financial_statements — **修正:`DATA_AVAILABLE_IMPLEMENTATION_REQUIRED`(不是 PASS)**

**本輪下修**：上輪把「資料 100% 真實」跟「R3-P 已解除」混在一起呈現。這是兩個獨立主張——資料充分性(下表仍是乾淨 PASS,未改)不等於 producing chain 真的在用它。`core.tej_bundle._to_long`(P0-R3 已存檔的既有發現)目前仍是固定 45 日 lag,**沒有**讀 `release_date`。依本研究自己的 AC-R4-10 規則(欄位存在不等於被消費),`financial_statements` 的 R3-P **未解除**,需要另一個未來、另外授權的實作步驟。

**主檔**：`財報2004~202606/20260806090633.xlsx`(sha256 `97574a08...`,manifest 確認,138,731 列,2005-2026);另有一份 596 列的 `202606 財報583家 8-10.xlsx` 補充批次(2026-08-10 匯出,疑似 Q2 2026 583 家公司的後補更正,本輪未深入,不影響下方結論)。

| 檢查項 | 結果 | 細節 |
|---|---|---|
| 2005-2026 歷史涵蓋 | **PASS** | 主檔逐年列數皆 >0,138,731 列,吻合 DATASETS 規格 `expected_date_min="2005-12-31"` |
| 真實公告日期欄位(`財報發布日`)缺失率 | **PASS(乾淨)** | 用跟 monthly_revenue 同一套嚴格 regex 分類法重新核對(正是這套方法抓到 monthly_revenue 的 `.` 佔位符問題)——**2005-2026 每一年 100.00% 都是真實可解析日期,零個 `.` 佔位符,零空白**(138,731/138,731) |
| Revision/vintage 表達方式 | **UNRESOLVED / 本題不適用** | 56 欄 schema 裡沒有任何「原始申報 vs 重編」旗標或同一 (股票,期間) 的第二筆值——單一目前快照,一列對應一個 (股票,季度),吻合既有 `V2_CANDIDATE_RESTATED_SNAPSHOT` 定性。這代表**無法**支持 Track A 首次公告值重建(本輪不在檢查範圍,另案),但**不影響**這裡要回答的 R3-P 問題(消費端 PIT 可用性——見下) |
| 能否取代固定 45 日 lag(不修改 production) | **技術上可行,未實作,R3-P 未解除** | 給定全範圍 100% 真實 release_date,技術上可行以此取代 `core.tej_bundle._to_long` 目前的固定 `PUBLISH_LAG_DAYS=45` 代理值。**本輪未讀取/修改任何 production 程式碼**,這只是資料充分性判斷。**明確澄清:這不代表 R3-P 已經解除**——`consumed_by_producing_chain` 目前是 `false`,production 今天實際用的仍是 45 日固定代理。 |

**下一步**：若 Track B 另外獲授權,`financial_statements` 的 `PitEvidenceRecord` 應記 `cutoff_semantics.kind='genuine_field'`、`consumed_by_producing_chain=false`——依本研究自己的 AC-R4-10 規則,Gate R4-P 要求「實際被消費」而非只是「欄位存在」。**在那個未來、需另外授權的實作步驟完成之前,`financial_statements` 的正式狀態是 `DATA_AVAILABLE_IMPLEMENTATION_REQUIRED`,不是已解除。**

---

## 3. institutional_gross — **修正:`PARTIAL_FEASIBLE`(不是 PASS)**

**本輪下修**：16 份原始檔中,本輪只核對了 4 份的表頭 + 1 份(2004)的前 5 萬列內容——這是正面、有方向性的樣本結果,但依本研究自己的 AC-R4-14 規則(必須全 corpus,不是抽樣;抽樣結果最多記 `NOT_FULLY_EVALUATED`,不能記 `SUFFICIENT`),不能宣告全 corpus PASS。下表內容不變,結論措辭改為誠實反映樣本性質。

**代表性檔案**(16 份 `法人回測2004-20260806/` 檔案中取 4 份,涵蓋首/尾/兩個中間年段)：2004、2012、2019-2020、2025-20260806(各自 sha256 見 JSON)。

| 檢查項 | 結果 | 細節 |
|---|---|---|
| 所需 6 個欄位 + 2005-2026 涵蓋 | **PASS** | `外資買進張數`/`外資賣出張數`/`投信買進張數`/`投信賣出張數`/`外資總投資股率%`/`投信持股率%` 六個必要欄位,在 4 份代表性檔案(2004/2012/2019-2020/2025-2026)**表頭全部存在**——這 16 份檔案正是 P0-R3 已經判定 `institutional_flow` SUFFICIENT 的同一批來源 |
| 欄位是否真的有值(不只是表頭) | **PASS** | 鑑於 monthly_revenue 的 `.` 佔位符教訓,本輪**沒有只信表頭存在**——對 2004 檔案前 50,000 列的全部 6 個必要欄位做逐列分類:**100.0% 是真實數值,0 個 `.`,0 個空白** |
| 既有 tej_cache 缺口是 importer/mapping 問題,還是原始匯出本身缺失 | **可能是 importer/mapping 問題(尚未全 corpus 確認)** | P0-R3 先前發現 tej_cache 上 `institutional_gross` 只有 2026-04-01→2026-07-16(255/255 個月缺席),看似跟 `tej_importer.py` 自己文件字串宣稱的 2004-01-02+ 涵蓋矛盾。本輪抽樣證據**支持**文件字串的 2004+ 宣稱相對這份原始匯出是正確的假設——但這是「樣本支持某個假設」,不是「已經證實的事實」;未開啟的 12 份檔案理論上仍可能藏著這份樣本沒抓到的缺口。 |

**下一步**：若 Track B 另外獲授權,在 `institutional_gross` 能被記為 `SUFFICIENT`/`PASS` 之前,依本研究自己的 AC-R4-14 全 corpus 規則,必須先對全部 16 份檔案做完整(或至少全 corpus 的唯讀掃描,不必到真正 build)核對。本輪只用 4/16 份檔案核對表頭 + 1/16 核對內容,中間 12 份未開啟(依「最少代表性原始檔」效率規則),**在那之前,誠實的狀態是 `PARTIAL_FEASIBLE`,不是 `PASS`**。

---

## 4. tdcc_weekly — **修正:`COVERAGE_FEASIBLE_R3_S`,但 `PIT_UNRESOLVED_R3_P`,且 `REQUIRED_BY_A_LEG_INDIRECTLY`(翻案)**

### 4a. 舊語料(本 repo 內):`tej_exports/DataExport0806/集保大戶2019-20260806/` + `tej_exports/inbox_tdcc/` — 維持 **CONFIRMED_TRUE,僅 2019+**

本輪重新核對一次(額外排除 `core/tdcc_provider.py`——即時週抓爬蟲,無歷史回補能力——與空的 `data/tdcc/` 作為替代歷史來源的可能性)。兩個 repo 內位置都只有 `TDCC2019.xlsx`~`TDCC2026-0709.xlsx`,不存在 `TDCC2004`~`TDCC2018`。**這項發現不刪除、不覆寫,作為獨立的舊語料觀察繼續有效。**

### 4b. 新語料(repo 外,使用者提供路徑):`C:\TejPro\TejPro\DataExport\集保大戶2005-20260806\` — **CONFIRMED 2013+,2005-2012 確認為空**

不同的 TEJ 匯出產品(「集保比率」,7 份 zip,各含一份 UTF-16、Tab 分隔的 .csv,50 欄)。**本輪唯讀逐檔重新計算列數與日期範圍(不採信使用者提供的數字,獨立算出來核對),結果完全吻合**：

| 檔案 | 資料列數 | 日期範圍 | SHA256(前 12 碼) |
|---|---|---|---|
| `2005-2007集保比率.zip` | **0**(僅表頭) | — | `70f1be9f43fc` |
| `2008~2010集保比率.zip` | **0**(僅表頭) | — | `c669508183e8` |
| `2011-2013集保比率.zip` | 19,017 | **2013-01-02 → 2013-12-02**(檔名含 2011-2012,但那兩年在檔案內容裡同樣沒有任何一列) | `e109caa9367e` |
| `2014-2017集保比率.zip` | 262,304 | 2014-01-02 → 2017-12-29 | `1e48e956ee06` |
| `2018-2021集保比率.zip` | 352,545 | 2018-01-05 → 2021-12-30 | `b5db93c835f8` |
| `2022-2025集保比率.zip` | 369,402 | 2022-01-07 → 2025-12-26 | `68f9298cb80d` |
| `20260814.zip` | 60,362 | 2026-01-02 → 2026-08-14 | `8e3adf544801` |

**2005-2012 獨立確認為真的空——不是假設、不是靜默視為涵蓋。**

**建置前品質關卡(依指示,candidate build 前先做)**——對 2011-2013(全檔 19,017 列)+ 20260814(全檔 60,362 列)+ 2014-2017/2018-2021/2022-2025 各前 4 萬列(共 159,379 列)：

| 檢查項 | 結果 |
|---|---|
| 日期唯一性(每個 `(證券代碼,年月日)` 是否唯一) | **PASS** — 0 筆重複 key |
| 股票代碼格式 | **PASS** — 0 筆格式異常 |
| 15 個持股級距比率合計是否約等於 100 | **PASS** — 159,379 列中只有 3 列偏差 >1.0(最大單列偏差 4.17),吻合 15 個桶位各自四捨五入到小數點後兩位的正常誤差,不是結構性缺陷 |
| `集保總張數(千股)` 與 15 個級距 `(千股)` 加總(+股數調整項)是否一致 | **PASS** — 0 筆偏差超過 1% |
| `集保總人數` 與 15 個級距 `(人數)` 加總是否一致 | **PASS** — 0 筆偏差超過 1% |

**Candidate schema / identity adapter 決定**(本輪僅記錄決策,未動任何程式碼)：新來源固定 50 欄——candidate schema **保留全部 50 欄**;但 identity adapter 目前**只消費既有 `DATASETS['tdcc_weekly']` 已映射的 6 個欄位**(`holders`/`total_lots_thousand`/`ratio_1000up`/`ratio_le1`/`ratio_1to5`/`ratio_5to10`),其餘約 44 欄(各級距人數/千股明細、10-15 到 800-1000 張等額外比率桶位)暫不映射,留待未來另外決定。

**重要來源歸屬提醒**：這個新位置在本 repo 之外,不在 `DataExport0806_manifest.csv` 涵蓋範圍內。它底下其實鏡射了跟本 repo `tej_exports/DataExport0806/` 相同的 11 個資料集子目錄結構——**本輪沒有拿 `monthly_revenue`/`financial_statements`/`institutional_gross` 去跟這個新位置核對**,那個位置是否取代/僅是重複 repo 內既有的 DataExport0806 語料,是一個本輪未調查的開放問題。

### 4c. 是否為 A-leg/B-leg/decision-time universe/final membership 的必要輸入 — **翻案:`REQUIRED_BY_A_LEG_INDIRECTLY`**

**上輪的 `NOT_REQUIRED` 結論是錯的**——上輪的全庫搜尋涵蓋了 `high52_lab.py`/`canonical_universe.py`/`tej_universe_screen_validation.py`,但**完全沒搜尋 `beat_0050/realbody/`**,而那裡確實存在一條真實、可獨立驗證的依賴鏈。本輪**沒有直接採信這個修正指示,而是自己重新逐段讀原始碼驗證過**,四個環節逐一確認:

1. `beat_0050/realbody/build_realbody_scores.py` 第 120 行(計分 worker 內):`from beat_0050.realbody.bt_bundle import bt_fetch_history`,第 124 行呼叫 `bt_fetch_history(sid)`。
2. `beat_0050/realbody/bt_bundle.py` 第 61-63 行:`def bt_fetch_history(...): b = _tb.tej_fetch_history(symbol, name)`,其中 `_tb`(第 23 行)是 `import core.tej_bundle as _tb`。這個檔案自己的 docstring 講明它只覆寫兩個特定行為,**不含** `shareholding`。
3. `core/tej_bundle.py` 第 221-236 行,`tej_fetch_history()`:無條件建構並回傳 `HistoryBundle(..., shareholding=_tej_shareholding(symbol))`——`shareholding` 不是 `bt_bundle.py` 覆寫的那兩項之一,所以這一段呼叫沒有被繞過。
4. `core/tej_bundle.py::_tej_shareholding()`(上輪已確認)讀 `tdcc_weekly.total_lots_thousand` 當流通股數代理。

**完整鏈**:`build_realbody_scores.py → bt_bundle.bt_fetch_history → core.tej_bundle.tej_fetch_history → _tej_shareholding → tdcc_weekly`。

**誠實的限制**:這證實了一條真實的 production/backtest 程式路徑(不只是研究/診斷腳本)間接依賴 `tdcc_weekly`;但**沒有**進一步確認「realbody 計分」跟 P0-R3 文件定義的 decision-time universe(`Panel.tier_valid`)是同一個東西還是平行的另一條管線——這是翻案之後仍然沒有解決的問題。

### 4d. `年月日` 是否代表真實對外可得日期,還是只是 as-of 觀察日期 — **`UNRESOLVED_AVAILABILITY_NOT_PROVEN`**

§4b 的品質關卡只證明 `年月日` 是一個**內部自洽、格式良好的 as-of 快照日期**——不證明「這個快照在當時真的什麼時候才對外公開/可得」(這是本研究非-claim 3 明講的兩件不同事)。跟 `financial_statements`/`monthly_revenue` 不同,這份原始匯出**完全沒有另一個獨立的「發布日」欄位可看**——`年月日` 是唯一的日期欄。`core/tdcc_provider.py` 的 docstring 提到 TDCC 官方開放資料「每週五傍晚更新...先天有最多約一週 lag」,但那是**另一個機制**(即時週抓爬蟲)的說明文字,不是這份 TEJ Pro 匯出本身可得時機的證據,本輪只引用作背景,不當作證據採信。

**因此:`tdcc_weekly` 的 R3-S(涵蓋可行性)本輪有正面證據支持,但 R3-P(真實逐列 PIT 可得性)維持 `UNRESOLVED/FAIL`**——而且鑑於 §4c 剛確認它確實間接餵進一條真實計分路徑,這個缺口不是學術性的,是有實際下游影響的。

---

## 5. 總結與裁決(本輪修正)

**依指示,整體裁決改成三個獨立、明確命名的狀態,不再用單一「PASS/沒有 blocker」概括:**

### `COVERAGE_BUILD_FEASIBLE_FOR_PROPOSED_2013_PLUS_WINDOW`
在**提案中(尚未核准)** 的 2013-01→2026-03 窗口內,四個資料集都有唯讀證據支持涵蓋可行:`monthly_revenue`(完整)、`financial_statements`(完整,範圍比需要的更寬)、`institutional_gross`(`PARTIAL_FEASIBLE`——樣本支持,非全 corpus 確認)、`tdcc_weekly`(2013+ 在新的 repo 外 TEJ Pro 匯出裡確認,品質關卡通過)。

### `PIT_REMEDIATION_STILL_REQUIRED`
涵蓋可行性 **不等於** R3-P 已解除,四個資料集目前**沒有一個**的 R3-P 是真的已解除:
- `financial_statements`:真實 `release_date` 存在,但 production 消費端未讀它(仍是 45 日固定代理)——`DATA_AVAILABLE_IMPLEMENTATION_REQUIRED`。
- `monthly_revenue`:真實 `release_date` 只到 2013+,且同樣沒有任何 code 被改去消費它。
- `institutional_gross`:本輪的 4 個問題本來就沒涵蓋它的 PIT 語意,未檢查。
- `tdcc_weekly`:`UNRESOLVED_AVAILABILITY_NOT_PROVEN`——`年月日` 只是良好的 as-of 觀察日,不是已證明的真實可得日期;且本輪翻案確認它**間接**是一條真實計分路徑(`build_realbody_scores.py → bt_bundle.bt_fetch_history → core.tej_bundle.tej_fetch_history → _tej_shareholding → tdcc_weekly`)的輸入,這個缺口有實際下游影響。

### `FORMAL_WINDOW_CHANGE_NOT_YET_APPROVED`
2013-01→2026-03 這個 identity 窗口,目前只是**本輪對話中浮現的提案**,**沒有經過本研究自己的 prereg/erratum 正式核准機制**——不構成對 P0-R4/R3-S/R3-P 範圍的實際變更,任何未來階段都不能把它當「已核准的新窗口」處理。`financial_statements`(2005-2026 全真實)、`institutional_gross`(涵蓋範圍更寬,但只到 `PARTIAL_FEASIBLE` 確認度)本身涵蓋都比 2013+ 更寬——2013 這個提案起點是被 `monthly_revenue`/`tdcc_weekly` 兩者的真實下限決定的約束,不是四個資料集共同的自然瓶頸,這個不對稱本輪只記錄,不解決。

**建議**:不要因為本 preflight 就投入 candidate build 或任何 code 變更。若要正式採用 2013-01→2026-03 窗口,需要走本研究自己的 prereg/erratum 正式核准流程,不能靠這輪對話默認生效。無論窗口如何決定:`financial_statements`/`monthly_revenue` 都需要未來、另外授權的實作步驟才能讓 producing chain 真的消費 `release_date`;`institutional_gross` 需要全 corpus(非抽樣)核對才能記 `SUFFICIENT`;`tdcc_weekly` 需要全 corpus 核對**加上**有名有據的真實可得性/lag 證據才能讓 R3-S/R3-P 任一項真正解除,且它新確認的間接 A-leg 依賴代表這不是低風險缺口。**本 preflight(含本次修正)本身不構成任何 Track B/Phase B 執行、candidate build、搬檔、importer 修改的授權**——純粹是唯讀可行性發現,等待審查與後續明確指示。
