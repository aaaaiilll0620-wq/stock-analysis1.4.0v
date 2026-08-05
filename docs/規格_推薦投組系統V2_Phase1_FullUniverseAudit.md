# 規格 · 推薦投組系統 V2 · Phase 1 Full-Universe Audit

> **本文件狀態:規格凍結文件(實作前先寫,依研究紀律§2 單發射擊制)。**
> 依 `GPT answer.md`「給 Claude:Phase 1 Full-Universe Audit 實作」checkpoint 指示產生,
> 先讀過 `AGENTS.md`、`docs/研究紀律_ResearchDiscipline.md`、`docs/規劃_推薦投組系統V2.md`、
> 已 commit 的 `docs/盤點_推薦投組系統V2_Phase1_Preflight.md`(commit `8a5c385`)。
>
> **本檔只凍結「全市場資料結構稽核」本身的範圍/欄位/狀態/fail-closed 語義,
> 不凍結、不涉及任何選股/訊號/投組/績效邏輯**(那些屬 `docs/規劃_推薦投組系統V2.md`
> §6–§7,尚未到 Phase 2)。
>
> **本輪(本 checkpoint)不執行真實全市場 audit**——本檔與對應程式碼只是把 Phase 1
> Preflight(單股抽樣)升級為「可重複執行的全市場結構稽核工具」的**規格與骨架**,
> 真正對 `~/tej_cache`、`~/finmind_cache`、`data/research_base/` 跑一次全市場掃描
> 是下一個 checkpoint 的事,需使用者另外下指令啟動(見 §6)。

---

## 目錄

1. [目的與邊界](#1-目的與邊界)
2. [稽核範圍(Dataset Registry)](#2-稽核範圍dataset-registry)
3. [每筆檔案的檢查項目](#3-每筆檔案的檢查項目)
4. [狀態定義(States)](#4-狀態定義states)
5. [Fail-Closed 語義(結構條件 PASS/FAIL 判定表)](#5-fail-closed-語義結構條件-passfail-判定表)
6. [Runner 安全機制](#6-runner-安全機制)
7. [輸出 Schema](#7-輸出-schema)
8. [明確禁止事項](#8-明確禁止事項)
9. [Tests 規格](#9-tests-規格)
10. [未決項(本檔不代為決定)](#10-未決項本檔不代為決定)

---

## 1. 目的與邊界

**目的**:把 `docs/盤點_推薦投組系統V2_Phase1_Preflight.md` 中標記 `SAMPLE_N=1`/
`UNVERIFIED` 的「全市場資料內容」項目,升級成可對**全部檔案**執行、**可重複、
deterministic** 的結構稽核工具,產出機器可讀的稽核報告。

**這個 audit 回答的問題只有一種**:「這份資料的**結構**(schema、鍵、日期可解析性、
檔名與內容是否一致、讀檔是否成功)有沒有問題」。

**這個 audit 不回答**(見 §8 明確禁止清單):資料好不好用、覆蓋率夠不夠、策略會不會賺錢。

## 2. 稽核範圍(Dataset Registry)

範圍限定為「TEJ/FinMind 價格、估值、籌碼資料」+「`obs_alpha`/`exec_ret`」+
「frozen `realbody_scores*.parquet`」,共三類、**6 個 A 類 dataset + `obs_alpha` +
`exec_ret` + 1 個 frozen 面板群組**(修正:先前版本誤寫成「共 7 個具名 dataset」,
把 B 類兩個檔案與 C 類 1 個群組全部併入同一個計數,不精確)。**財報
(`financial_statements`/`monthly_revenue`)、產業對照表、事件旗標、`institutional_flow`
(已被 `institutional_gross` 取代的舊淨額版)不在本輪範圍內**——原因見 §10。

### 2.1 類別 A:TEJ/FinMind 原始價格/估值/籌碼(逐股檔案)

所有 dataset 皆為「一檔股票一個 parquet」,路徑 `<root>/<dataset>/<stock_id>.parquet`,
`root` 由環境變數決定(與生產程式碼同一套慣例,見下表證據欄)。

| dataset id | 類別 | root 環境變數(預設) | 子目錄 | 必要欄位(證據來源) | date 欄 | 檔案內主鍵 |
|---|---|---|---|---|---|---|
| `tej_price_valuation` | 價格+估值 | `TEJ_CACHE`(`~/tej_cache`) | `price_valuation` | `stock_id,date,open,max,min,close,Trading_Volume,PER_TSE,PER_TEJ,PBR_TSE,PBR_TEJ,dividend_yield_TSE`(`tej_importer.py::DATASETS['price_valuation']`;消費端 `core/data_provider.py::_read_local_price_valuation`) | `date` | `date` |
| `tej_institutional_gross` | 籌碼 | `TEJ_CACHE` | `institutional_gross` | `stock_id,date,foreign_buy,foreign_sell,trust_buy,trust_sell,foreign_holding_pct,trust_holding_pct`(`tej_importer.py::DATASETS['institutional_gross']`;消費端 `core/data_provider.py::_read_local_chip`) | `date` | `date` |
| `tej_margin_balance` | 籌碼 | `TEJ_CACHE` | `margin_balance` | `stock_id,date,margin_balance,short_balance`(`tej_importer.py::DATASETS['margin_balance']`;消費端 `core/data_provider.py::_read_local_margin`) | `date` | `date` |
| `tej_tdcc_weekly` | 籌碼/股權分散 | `TEJ_CACHE` | `tdcc_weekly` | `stock_id,date,ratio_1000up,ratio_le1,ratio_1to5,ratio_5to10,holders,total_lots_thousand`(`tej_importer.py::DATASETS['tdcc_weekly']`;消費端 `core/tej_bundle.py` 第189行) | `date` | `date` |
| `tej_director_pledge` | 籌碼/公司治理 | `TEJ_CACHE` | `director_pledge` | `stock_id,date,pledge_pct,director_holding_pct,group_name`(`tej_importer.py::DATASETS['director_pledge']`;消費端 `scripts/alpha_gate_lab.py` 第192-195行) | `date` | `date` |
| `finmind_price` | 價格(次要來源) | `FINMIND_CACHE`(`~/finmind_cache`) | `TaiwanStockPrice` | `date,stock_id,open,max,min,close,Trading_Volume`(`CLAUDE.md`「Core Data Conventions」) | `date` | `date` |

> **證據強度聲明**:上表必要欄位是從匯入程式 `tej_importer.py` 的 `column_map`/
> `thousand_cols` 轉換後**應該**產生的欄位、加上消費端程式碼讀取欄位交叉確認,
> **不是**對真實快取檔案內容做過驗證(那正是本 checkpoint 刻意不做的「真實全市場
> audit」)。第一次真實執行若 schema 不符,**視為正常發現、不是 bug**——代表匯入版本
> 與本檔假設不同步,應更新本表並記錄差異,不得放寬檢查繞過。

### 2.2 類別 B:研究基底面板(單一合併檔)

| dataset id | 路徑 | 必要欄位 | 主鍵 |
|---|---|---|---|
| `obs_alpha` | `data/research_base/obs_alpha.parquet`(`scripts/lab_paths.py::OBS_ALPHA`) | `as_of,stock_id,adv20,listed_ok` | `(as_of,stock_id)` |
| `exec_ret` | `data/research_base/exec_ret.parquet`(`scripts/lab_paths.py::EXEC_RET`) | `as_of,stock_id,fwd_x,px_in,tick_slip` | `(as_of,stock_id)` |

> **`obs_alpha.fwd` 明確排除**:本 audit **不檢查、不讀取** `obs_alpha` 的 `fwd` 欄位
> (若存在),不將其列入必要欄位、不對其做任何缺值/非有限值/schema 檢查。理由:
> `docs/研究紀律_ResearchDiscipline.md` §1 明定 `fwd` 是有雙重反向偏誤、淨誤差
> 正負隨換手率變動、無法事後修正的欄位,`scripts/lab_paths.py::load_panel()`
> 讀入後立即 `drop`。本工具連「確認它存不存在」都不做,避免任何未來讀者誤讀
> 成「這欄位被驗證過所以能用」。

### 2.3 類別 C:Frozen 真身面板(1 個群組)

| dataset id glob | 路徑 | 必要欄位 | 主鍵 |
|---|---|---|---|
| `realbody_scores*` | `data/research_base/realbody_scores*.parquet`(`scripts/lab_paths.py::REALBODY`/`available_realbody_panels()`) | `as_of,stock_id,real_composite,rating,f_fund,f_val,f_tech,f_mom,f_whale`(`scripts/lab_paths.py::REAL_COMP_COL`/`REAL_FACES`) | `(as_of,stock_id)` |

此類別**只讀 hash/schema/鍵完整性**(見 §3),不檢查缺值/非有限值,不重算任何分數,
不修改檔案(唯讀開啟)。這是**一個群組**(glob 命中 0 至多個檔案),群組本身也有
獨立的 `MISSING`/`EMPTY`/`PASS`/`FAIL` 狀態(見 §4.2b)——不是每個檔名各自算一個
獨立 dataset。

---

## 3. 每筆檔案的檢查項目

| 檢查項 | 適用類別 | 說明 |
|---|---|---|
| **檔案可讀** | A/B/C | 讀取分兩步:①先讀 parquet **schema metadata**(欄名、列數,`pyarrow.parquet.ParquetFile`,不觸碰任何列資料);②只用 `pd.read_parquet(path, columns=<允許欄位 ∩ schema>)` 投影讀取——**任何路徑都不會整檔載入**,也不會讀到允許清單以外的欄位(見下方「投影讀取」說明)。例外訊息完整記錄,不吞例外 |
| **投影讀取(哪些欄位允許被讀進記憶體)** | A/B/C | 每個 dataset 的「必要欄位」(§2 各表)同時就是**允許讀取的投影上限**——`obs_alpha` 的必要欄位不含 `fwd`,所以 `fwd` 欄**不會出現在傳給 `pd.read_parquet` 的 `columns=` 參數裡**,不是事後才把它從輸出裡濾掉 |
| **Schema(必要欄位是否齊全)** | A/B/C | 缺少 §2 表列的任一必要欄位 → 記錄缺漏清單(由 schema metadata 判定,不需要讀列資料) |
| **零列檔案(`empty_file`)** | A/B/C | schema 合法但列數為 0(由 metadata 的 `num_rows` 判定)→ 獨立欄位 `empty_file=true`,fail-closed(見 §5) |
| **主鍵重複** | A/B/C | 依 §2 表列主鍵做 `duplicated(keep=False)`;A 類主鍵僅 `date`(單股檔),B/C 類為 `(as_of,stock_id)` |
| **主鍵欄缺值** | A/B/C | 主鍵欄本身若含 null/NaT,視為主鍵不完整 |
| **日期可解析性** | A/B | date 欄以 `pd.to_datetime(errors="coerce")` 解析,任何列產生 `NaT` 記為「壞日期」 |
| **檔名與 `stock_id` 一致性** | A(全部 6 個 dataset,含 `finmind_price`) | 檔名 stem(去除副檔名)須等於檔案內 `stock_id` 欄(轉字串比較)之**全部**唯一值;有任一列不符 → 記錄不符列數與樣本 |
| **覆蓋起訖(min/max date)** | A/B | 僅記錄,不判定及格與否(見 §4 `MEASURED_NOT_JUDGED`) |
| **缺值/非有限值/轉型失敗計數** | A(數值欄,見 §2 各 dataset 定義)、B(**僅 `exec_ret.fwd_x`**) | 三個計數是**互斥的異常分類**(同一列同一欄只落入其中一種,不重複計),**但不加總覆蓋該欄全部列**——其餘列是可正常解析的 finite 值,不落在任何一個計數裡(修正:先前版本誤寫成「加總覆蓋全部列」,不正確):`null_counts`(原始值本來就是缺值)、`non_finite_counts`(轉數值後是 `inf`/`-inf`)、`coercion_failure_counts`(原始值非缺值,但 `pd.to_numeric(errors="coerce")` 轉換失敗,例如字串 `"abc"`——沒有這欄,這種雜訊會既不算 null 也不算 non-finite 而在計數上消失)。全部只記錄,不判定及格 |
| **key-set 對齊(僅 `obs_alpha` vs `exec_ret`)** | B | 兩檔 `(as_of,stock_id)` 集合的交集/僅左/僅右數量,只記錄不判定;新增獨立的 `keyset_status ∈ {PASS, NOT_MEASURED, FAIL}`(見 §4.3a)標示「這次量測本身有沒有成功」,與量出來的差異數量分開;key-set 本身的讀取也走同一套「schema metadata 先行 + 只投影主鍵欄」流程 |
| **檔案 sha256** | C(必做)、A/B(選配,預設關閉,避免全市場逐檔雜湊拖慢例行稽核) | `hashlib.sha256` 分塊讀取計算 |

---

## 4. 狀態定義(States)

沿用 Phase 1 Preflight 已驗證好用的雙欄設計(`InspectionStatus` / 結論欄位),
但本工具是機器執行,狀態機更精簡:

### 4.1 檔案層級 `FileFinding.status`

| 狀態 | 意義 |
|---|---|
| `PASS` | §3 所有「可判定」檢查項(可讀、schema、零列檔案、主鍵重複、主鍵缺值、日期可解析、檔名一致性)全部通過 |
| `FAIL` | 上述任一「可判定」檢查項失敗(見 §5 判定表) |

`FileFinding` 額外帶一個獨立布林欄位 `empty_file`(見 §7)——0 列的合法 schema
檔案會讓 `status=FAIL` 且 `empty_file=true`,與「缺欄」「主鍵重複」等其他 FAIL
原因分開標示,方便下游快速判斷是哪一種結構問題。

`覆蓋起訖`、`缺值/非有限值計數`、`key-set 對齊`**不影響** `status`——這些欄位
一律記錄在 `measured`(見 §7),標記為 `MEASURED_NOT_JUDGED`,因為「多少缺值/多短的
覆蓋率算不合格」是**尚未凍結的政策門檻**(研究紀律:預註冊凍結前不得自訂及格線)。

### 4.2 Dataset 層級 `DatasetReport.status`

| 狀態 | 意義 |
|---|---|
| `MISSING` | root 目錄不存在(例如 `~/tej_cache/director_pledge/` 從未建立) |
| `EMPTY` | root 目錄存在但無任何 `*.parquet` 檔 |
| `PASS` | 目錄存在,所有檔案 `FileFinding.status == PASS` |
| `FAIL` | 目錄存在,至少一個檔案 `FileFinding.status == FAIL`(含讀檔失敗) |

`MISSING`/`EMPTY` **不是** `FAIL`——這對應 Preflight 已用過的「資料缺席」與「資料存在但
壞掉」是兩種不同性質的發現,不得合併回報,避免讀者把「還沒建置」誤讀成「建置壞了」。

### 4.2b Frozen 面板群組層級 `FrozenPanelsReport.status`(修正必修6新增)

`realbody_scores*` 是**一個 glob 群組**,不是逐股拆檔的 dataset,但同樣需要
群組層級的狀態,理由與 §4.2 相同,狀態集合也相同:

| 狀態 | 意義 |
|---|---|
| `MISSING` | `research_base` 目錄本身不存在 |
| `EMPTY` | `research_base` 目錄存在,但 glob 不到任何 `realbody_scores*.parquet` |
| `PASS` | glob 命中至少一個檔案,且全部 `FileFinding.status == PASS` |
| `FAIL` | glob 命中至少一個檔案,且至少一個 `FileFinding.status == FAIL` |

**修正必修6的問題**:先前版本 `frozen_panels` 直接是「檔名 → 結果」的扁平字典,
一份面板都沒有時就是空字典 `{}`,`run_audit()` 沒有任何邏輯去檢查這個空字典
本身代表「MISSING/EMPTY」,導致其他資料全 PASS 時會**誤報整體 `PASS`**
(該報的 `PASS_WITH_GAPS`沒報出來)。現在 `frozen_panels` 是
`{"status": ..., "files": {...}}` 的群組結構,`status` 一定會被 §4.3 的
`overall_status` 判定式讀到。

### 4.3a `keyset_status`(修正必修1,第二輪 review 新增)

key-set 對齊(§3)是一個**量測動作**,量測本身「有沒有成功執行」跟「量出來的
差異數量是多少」是兩件事——後者屬 `MEASURED_NOT_JUDGED`(見 §5),前者則必須
fail-closed,不能靜靜寫進 `measured.error` 就被上層當沒事發生(先前版本正是
這個漏洞:兩檔都在、但第二次投影讀取途中丟例外,只留在 `measured.error`,
`overall_status` 完全不受影響,可能誤報 `PASS`)。

| `keyset_status` | 觸發條件 |
|---|---|
| `PASS` | `obs_alpha`/`exec_ret` 兩檔都存在,key-set 量測成功完成 |
| `NOT_MEASURED` | 任一檔缺席——這個 gap 已經由 `obs_alpha_status`/`exec_ret_status == MISSING` 反映,不重複計入 gap 判定 |
| `FAIL` | 兩檔都存在,但量測本身(投影讀取/集合運算)丟例外 |

### 4.3 整份報告 `AuditReport.overall_status`

```text
overall_status = FAIL
    若任一 DatasetReport.status == FAIL
    或 FrozenPanelsReport.status == FAIL
    或 obs_alpha_status == FAIL 或 exec_ret_status == FAIL
    或 keyset_status == FAIL

overall_status = PASS_WITH_GAPS   （無 FAIL,但符合以下任一者）
    任一 DatasetReport.status ∈ {MISSING, EMPTY}
    或 obs_alpha_status == MISSING 或 exec_ret_status == MISSING
    或 FrozenPanelsReport.status ∈ {MISSING, EMPTY}

overall_status = PASS   若上述 FAIL/PASS_WITH_GAPS 條件皆不成立
```

`keyset_status == NOT_MEASURED` 不單獨觸發 `PASS_WITH_GAPS`——它必然伴隨
`obs_alpha_status`/`exec_ret_status == MISSING` 其中之一,gap 已經被算過一次,
不重複疊加。

`PASS`/`PASS_WITH_GAPS` **皆不等於**「資料已足以支撐正式研究結論」——那是
`docs/盤點_...Preflight.md` 的 `ResearchReadiness` 欄位管的事,本工具的 `overall_status`
只回答結構稽核本身有沒有抓到壞資料。

---

## 5. Fail-Closed 語義(結構條件 PASS/FAIL 判定表)

依 checkpoint 指示第 4 點,以下條件**必須** fail-closed(寧可誤報也不得漏報):

| 條件 | 判定 |
|---|---|
| 必要欄位缺漏(缺欄) | `FAIL` |
| **零列檔案(schema 合法但 `num_rows == 0`)** | `FAIL`(獨立欄位 `empty_file=true`,修正必修2——先前版本這種檔案會誤判 `PASS`) |
| 主鍵重複 | `FAIL` |
| 主鍵欄含缺值 | `FAIL` |
| date 欄解析出 `NaT`(壞日期) | `FAIL` |
| 檔名與 `stock_id` 內容不一致 | `FAIL` |
| 讀檔失敗(例外、損毀、無法解析 schema) | `FAIL`(記錄例外訊息,**不靜默跳過**,繼續處理下一檔) |

以下條件**明確不判定**(`MEASURED_NOT_JUDGED`),因為容忍值尚未凍結,自行訂門檻
即違反研究紀律§2:

| 條件 | 只記錄的內容 |
|---|---|
| 資料覆蓋起訖是否夠長 | min/max date |
| 缺值/非有限值比例是否可接受 | 各欄 null 數、inf 數、總列數 |
| `obs_alpha`/`exec_ret` key-set 是否需要 100% 對齊 | 交集數、僅左數、僅右數 |
| 全市場檔案數是否等於「應有股數」 | 實際檔案數(無凍結的母體清單可比對,見 §10) |

---

## 6. Runner 安全機制

1. **預設不得意外跑真實資料**:CLI 進入點 `main()` 兩道旗標都沒帶時,只印出
   可用 dataset 清單與用法說明並以 **exit code `0`** 結束,**不掃描任何真實目錄**,
   也**不呼叫 `run_audit()`**。
2. **真實全市場稽核**需同時滿足:
   - 顯式旗標 `--execute`
   - 顯式旗標 `--i-understand-this-reads-real-cache`(雙重確認,避免 CI 或誤觸的
     `--execute` 意外掃過使用者家目錄下的真實快取)
   - **只給其中一道旗標視為誤用**(修正必修4)——印出缺少哪一道旗標到 stderr,
     以 **exit code `2`** 結束,同樣不呼叫 `run_audit()`。
   - 兩道旗標都給,CLI 才會呼叫 `_real_dataset_roots()`/`_real_research_base()`
     組出真實路徑,再傳給 `run_audit()`;成功執行後 exit code 依 `overall_status`
     決定(`FAIL` → `1`,否則 → `0`)。

   | 情境 | exit code |
   |---|---|
   | 兩道旗標都沒給 | `0`(只印用法) |
   | 只給 `--execute` 或只給 `--i-understand-this-reads-real-cache` | `2`(誤用) |
   | 兩道旗標都給,`overall_status != FAIL` | `0` |
   | 兩道旗標都給,`overall_status == FAIL` | `1` |

3. **`run_audit()` 本身不提供任何真實路徑預設值**(修正必修3)——
   `dataset_roots`(`dict`)與 `research_base`(`Path`)是**必要參數,沒有預設值**,
   省略任一個直接 `TypeError`;`dataset_roots` 還必須覆蓋 `DATASET_SPECS` 的
   **全部** key,缺一即 `ValueError`,不得靜默用某個 dataset 的預設路徑補上缺漏。
   這讓測試/CLI 之外的任何呼叫端都不可能「不小心」掃到真實快取——唯一能組出
   真實路徑的地方是 CLI 內、且只在雙旗標都通過之後才執行的
   `_real_dataset_roots()`/`_real_research_base()`。
4. **讀檔一律先讀 schema metadata、再投影允許欄位**(修正必修1,細節見 §3):
   `read_projected_parquet()` 是全模組唯一讀取資料值的入口,`audit_file()`/
   `audit_obs_exec_pair()` 的 key-set 對齊皆透過它讀檔,不會有任何路徑繞過投影
   直接 `pd.read_parquet(path)` 整檔載入。
5. **唯讀**:全程只呼叫 `pd.read_parquet`(投影)/`pyarrow.parquet.ParquetFile`
   (schema metadata)/`os.stat`/`glob`,不寫入、不修改、不刪除任何被稽核的檔案。
   `sha256_file()` 以串流分塊讀取,不整檔載入記憶體。
6. **逐檔失敗不中斷**:單一檔案讀取例外只記錄該檔的 `FAIL`,`run_audit()`
   繼續處理該 dataset 剩餘檔案與其他 dataset,直到全部跑完才回傳報告。
7. **輸出 deterministic 且不含時間戳**(修正必修5):CLI 輸出的 JSON **不含**
   `generated_at` 或任何其他非決定性欄位——同一份輸入資料、同樣的旗標,兩次執行
   `main()` 寫出的位元組必須完全相同。檔案列表排序後才迭代、JSON 以
   `sort_keys=True` 序列化。先前版本每次執行都塞入即時 `generated_at`,已移除。

---

## 7. 輸出 Schema

```jsonc
{
  "spec_version": "1.0",
  "overall_status": "PASS | PASS_WITH_GAPS | FAIL",
  // 註:輸出刻意不含 generated_at 或任何時間戳欄位 —— 修正必修5,
  // 同一份輸入資料的兩次輸出必須逐位元組相同。
  "datasets": {
    "<dataset_id>": {
      "status": "MISSING | EMPTY | PASS | FAIL",
      "root": "<掃描到的目錄路徑>",
      "file_count": 0,
      "files": [
        {
          "path": "<相對檔名>",
          "status": "PASS | FAIL",
          "read_ok": true,
          "read_error": null,
          "missing_columns": [],
          "empty_file": false,
          "duplicate_key_rows": 0,
          "key_column_nulls": 0,
          "bad_date_rows": 0,
          "filename_stock_id_mismatch_rows": 0,
          "measured": {
            "date_min": "...", "date_max": "...",
            "null_counts": {"<col>": 0},
            "non_finite_counts": {"<col>": 0},
            "coercion_failure_counts": {"<col>": 0},
            "row_count": 0
          },
          "sha256": null
        }
      ]
    }
  },
  "obs_exec_keyset": {
    "obs_alpha_status": "MISSING | PASS | FAIL",
    "exec_ret_status": "MISSING | PASS | FAIL",
    "keyset_status": "PASS | NOT_MEASURED | FAIL",
    "obs_alpha": "<...同 files[] 元素結構,或 null(檔案不存在時)>",
    "exec_ret": "<...同上>",
    "measured": {"only_in_obs_alpha": 0, "only_in_exec_ret": 0, "in_both": 0}
  },
  "frozen_panels": {
    "status": "MISSING | EMPTY | PASS | FAIL",
    "files": { "<filename>": { "...同 files[] 元素結構,含 sha256" } }
  }
}
```

---

## 8. 明確禁止事項

逐字沿用 checkpoint 指示第 5 點,程式碼與測試皆不得違反:

- 禁止計算或輸出報酬分布、均值、IC、CAGR、Sharpe、MDD、Top K、勝率、alpha。
- 禁止產生任何訊號(`Z1-*`/`E0`/`E1`)、投組建議、OOS/Gate 判定。
- 禁止讀取或修改 Gate 1 / Gate 2 / C3 產物。
- 禁止讀取 `obs_alpha.fwd`(見 §2.2)。
- 禁止對 `realbody_scores*.parquet` 做任何寫入或分數重算(唯讀開啟)。
- 本 checkpoint 完成後**不得** stage/commit/push 任何檔案,也不得對真實資料執行
  `--execute` 全市場稽核。

---

## 9. Tests 規格

`tests/test_portfolio_v2_phase1_audit.py` 只用 `tmp_path` 產生的 synthetic parquet
fixture,**不得**指向或讀取任何 `~/tej_cache`、`~/finmind_cache`、
`data/research_base/` 下的真實檔案。至少覆蓋:

| case | 建構方式 | 預期 |
|---|---|---|
| 正常檔案 | 齊全欄位、鍵唯一、日期可解析、檔名與 `stock_id` 一致 | dataset `status=PASS`,該檔 `status=PASS` |
| 缺欄 | 拿掉一個必要欄位 | 該檔 `FAIL`,`missing_columns` 含該欄 |
| **零列檔案** | schema 合法但 0 列 | 該檔 `FAIL`,`empty_file=true`,`missing_columns=[]` |
| 主鍵重複 | 同一 `date`(或 `(as_of,stock_id)`)出現兩列 | 該檔 `FAIL`,`duplicate_key_rows>0` |
| `stock_id` 與檔名不符 | 檔名 `1101.parquet` 但欄位值為 `2330` | 該檔 `FAIL`,`filename_stock_id_mismatch_rows>0` |
| 壞日期 | date 欄放入不可解析字串 | 該檔 `FAIL`,`bad_date_rows>0` |
| 讀檔失敗 | 寫入非 parquet 的假檔(或截斷損毀的位元組) | 該檔 `FAIL`,`read_error` 非空,**其餘檔案仍被處理**(驗證不中斷) |
| 未裁定 coverage | 齊全但故意日期範圍很短、含若干 null 數值欄 | 檔案仍可 `PASS`(結構乾淨),`measured` 內 `date_min/max`、`null_counts` 如實記錄,不因短覆蓋率而 `FAIL` |
| **字串轉數值失敗** | 數值欄放入無法解析的字串(如 `"abc"`) | 該檔仍 `PASS`(結構乾淨),`measured.coercion_failure_counts` 記到該欄,`null_counts`/`non_finite_counts` 該欄皆為 0 |
| **投影讀取不含 `fwd`(spy test)** | monkeypatch `pd.read_parquet` 攔截呼叫,對含 `fwd` 欄的 obs_alpha 稽核 | 每次攔截到的 `columns=` 皆不含 `"fwd"`,且 `columns` 一定顯式給出(非 `None`) |
| `obs_alpha`/`exec_ret` key-set 對齊 | 兩檔各故意留一把只存在單邊的鍵 | `obs_exec_keyset.measured` 正確回報 `only_in_obs_alpha`/`only_in_exec_ret`,`keyset_status=PASS`,不影響 `overall_status` |
| **key-set 量測本身失敗** | monkeypatch `read_projected_parquet`,讓兩檔各自的個別稽核成功,但 key-set 階段的第二次投影讀取丟例外 | `keyset_status=FAIL`,`obs_alpha_status`/`exec_ret_status` 仍是各自的 `PASS`;`run_audit().overall_status=FAIL` |
| **`run_audit()` 省略參數** | 直接呼叫 `run_audit()` 不帶任何參數 | `TypeError`(無真實路徑預設值,修正必修3) |
| **`dataset_roots` 缺 key** | 傳入的 dict 少一個 `DATASET_SPECS` key | `ValueError` |
| **只有 frozen 面板缺席** | 6 個 A dataset + obs_alpha/exec_ret 全 PASS,但不寫任何 `realbody_scores*.parquet` | `overall_status=PASS_WITH_GAPS`,`frozen_panels.status` 為 `MISSING`/`EMPTY`(修正必修6) |
| CLI 兩道旗標都沒給 | 呼叫 `main([])` | 不觸碰任何真實路徑、不呼叫 `run_audit()`,exit code `0` |
| **CLI 只給一道旗標** | 呼叫 `main(["--execute"])` 或 `main(["--i-understand-this-reads-real-cache"])` | 不呼叫 `run_audit()`,exit code `2`(修正必修4) |
| **CLI 輸出 byte-identical** | 兩次呼叫 `main()` 寫到不同檔案 | 兩份輸出位元組完全相同,且皆不含 `"generated_at"`(修正必修5) |

執行:

```bash
python -m pytest tests/test_portfolio_v2_phase1_audit.py -q -p no:cacheprovider
```

---

## 10. 未決項(本檔不代為決定)

- **母體清單**(全市場「應該有幾檔股票」)尚未凍結,故「實際檔案數 vs 應有股數」
  這項只能留在 `measured`,不能判定 PASS/FAIL(呼應 §5)。
- **財報/產業對照表/事件旗標未列入本輪 dataset registry**——`financial_statements`
  已被 Preflight 標記 `BLOCKED`(真實公告日缺口,非結構問題);產業對照表/題材
  標籤已被 D3 裁定 `BLOCKED`(非 PIT);兩者的「結構」稽核(schema/鍵)若未來需要,
  應另立 checkpoint 擴充 dataset registry,不在本輪未經使用者確認下擴大範圍。
- **是否需要對 A 類全部檔案預設計算 sha256** 留待下一個真正執行 `--execute` 的
  checkpoint 依效能實測決定(全市場 ~2,300 檔 × 6 個 dataset 逐檔雜湊的耗時未知)。
