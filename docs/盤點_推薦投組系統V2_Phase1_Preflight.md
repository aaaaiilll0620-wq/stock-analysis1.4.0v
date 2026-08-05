# 盤點 · 推薦投組系統 V2 · Phase 1 Preflight(唯讀資料可用性排查)

> **本文件狀態:Phase 1 Preflight,純唯讀盤點。**
> 依 `Claude_推薦投組系統V2_Phase0Commit_Phase1Preflight.md` Checkpoint B 指示產生,
> 先讀過 `AGENTS.md`、`docs/研究紀律_ResearchDiscipline.md`、`docs/規劃_推薦投組系統V2.md`
> (commit `d282e2f`)。
>
> **本輪未執行**:任何 fetch/build/API 呼叫、任何報酬/績效/OOS/calibration/timing/synthetic
> /Gate 計算、任何 Top K/Z1/E1 訊號生成、任何族群狀態/相關群組計算、任何 cache/CSV/JSON/
> parquet/暫存研究產物的新增寫入。全部發現皆來自:①閱讀原始碼(`Grep`/`Glob`/`Read`);
> ②對**已存在於磁碟**的檔案做唯讀 metadata 檢視(檔名/大小/mtime/schema/shape/首尾日期)。
> 若某項查核必須觸發抓取或寫檔才能完成,一律標記 `InspectionStatus = NOT_INSPECTED` 並
> 停止該項,不繞過(本輪實際上沒有任一項落到這個狀態,見 B4)。
>
> 排查範圍限定在本 repo(`C:\dev\Project 1`)及其程式碼中明確指向的本機/使用者快取目錄
> (`~/tej_cache`、`~/market_cache`、`~/finmind_cache`,皆由專案原始碼以環境變數指定為
> 唯一資料落地位置,非外部專案)。**未存取**使用者提及的另一個「消息」專案——依任務指示,
> 該來源只記為 external dependency,not accessed。
>
> **修訂記錄(2026-08-05,第二輪語義修正)**:依 `Claude_推薦投組系統V2_Phase1_Review1.md`,
> 把原本單一的「狀態」欄拆為 `InspectionStatus`(查核本身是否完成)與 `ResearchReadiness`
> (是否足以支撐正式規格/驗證)兩欄,不再使用 `AVAILABLE`/`CONFIRMED MISSING` 等混合值;
> 校正 L1 財務 PIT、L2 產業、題材標籤、L4b、L5/ReentryContext、L6a、交易日曆、Validation
> access guard 等項目的 readiness blocker(見 B4 Readiness Summary);新增 §B5 TEJ/本地
> 資料取得優先清單。本輪未重新掃描資料,只依既有盤點證據修正文義。

---

## 1. L1 選股本體

> **證據強度說明(第三輪修正,2026-08-05)**:本節多個項目原標 `READY`,但證據只到
> `SAMPLE_N=1`(單檔抽樣)或 `CODE_ONLY`(只讀程式碼)。這最多證明「介面/schema 存在」,
> 不能證明「全市場正式驗證所需的覆蓋率、鍵唯一性與缺值條件已就緒」,故拆成「介面」與
> 「全市場資料內容」兩列,分別給狀態,不使用混合值。

| 模組/欄位 | 現有來源/路徑 | schema/鍵 | PIT 時間欄位 | 覆蓋起訖 | 缺值/唯一性 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|---|---|---|---|
| 三個唯一入口(`load_panel`/`load_real_panel`/`resolve_realbody`) | `scripts/lab_paths.py`(第72、153、210行) | `(as_of, stock_id)`;`load_panel` 刻意不回傳 `fwd`,回傳 `fwd_x`;`load_real_panel` 刻意不回傳 `composite`,回傳 `real_composite` | `as_of` | — | `assert_unique()`/`assert_no_row_growth()` 硬檢查存在(程式碼層) | CODE_ONLY | INSPECTED | READY | 這是介面/入口函式本身的存在與設計確認,非資料內容;未呼叫執行 |
| `report_ladder`(三階基準) | `beat_0050/honest_backtest.py::Engine.report_ladder()`(第84、292行) | — | — | — | — | CODE_ONLY | INSPECTED | READY | 介面本身確認,未呼叫執行 |
| PIT 財務資料 | `core/backtest.py::build_pit_stockdata`(第346行)+ TEJ `~/tej_cache/financial_statements/*.parquet` | `stock_id,date,quarter,eps,revenue,...`(抽樣 1101.parquet:79列×17欄) | **無真實公告日欄**——固定假設 `PUBLISH_LAG_DAYS=45`(第58行) | 抽樣 2005-06 起 | 未全查 | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **BLOCKED** | PIT 落後天數是假設值非實測公告日,**在取得真實公告日資料、或凍結並證明安全的保守可用規則之前,正式財務驗證視為 BLOCKED** |
| 估值資料——介面 | `core/valuation.py` | `date`(直接 `date<=as_of` 切片邏輯) | `date` | — | — | CODE_ONLY | INSPECTED | READY | PIT 切片機制的程式邏輯本身無已知缺陷 |
| 估值資料——全市場內容 | TEJ `price_valuation/*.parquet`(抽樣 1101.parquet:5541列) | `stock_id,date,PER_TSE/TEJ,PBR_TSE/TEJ,dividend_yield_TSE` | `date` | 2004-01-02 起(僅該檔抽樣) | 未查(僅抽樣 1 檔,未做全市場缺值/唯一性驗證) | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 僅驗證單一股票,不能宣稱全市場覆蓋率/唯一性已就緒 |
| 籌碼/法人流向——介面 | TEJ `institutional_flow`/`margin_balance`/`tdcc_weekly`/`director_pledge` 讀取邏輯 | `stock_id,date,foreign_net,trust_net,dealer_net` 等(schema 定義) | `date` | — | — | CODE_ONLY | INSPECTED | READY | 讀取邏輯與 schema 定義本身存在 |
| 籌碼/法人流向——全市場內容 | `~/tej_cache/`(抽樣 5541 列,1101) | 同上 | `date` | 抽樣 1101 檔 | 未查(僅抽樣 1 檔) | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 僅驗證單一股票,全市場覆蓋率/唯一性未驗證 |
| Repo 內建 TDCC 快取 | `data/tdcc/`(**確認為空目錄**) | — | — | — | — | EXISTS_ONLY | INSPECTED | MISSING | `core/tdcc_provider.py` 目標路徑目前無資料,實際資料靠 TEJ cache(使用者家目錄,非 repo 內);若要讓 repo 自身可離線運作,需另行落地 |
| 技術面資料——介面 | `core/technical_analysis.py` 讀取邏輯 | `date,stock_id,open,max,min,close,Trading_Volume,...`(schema 定義) | `date` | — | — | CODE_ONLY | INSPECTED | READY | 讀取邏輯與 schema 定義本身存在 |
| 技術面資料——全市場內容 | FinMind `~/finmind_cache/TaiwanStockPrice/*.parquet`(抽樣 2330.parquet) | 同上 | `date` | 抽樣 2330:2019-01-02~2026-07-21 | 未查(僅抽樣 1 檔) | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 僅驗證單一股票,全市場覆蓋率/唯一性未驗證 |
| 真身 `real_composite`(研究面板,V0 frozen baseline) | `data/research_base/realbody_scores.parquet`(ADV≥2000萬)、`realbody_scores_adv100w.parquet`(ADV≥100萬) | `(as_of,stock_id)`;欄位 `real_composite,rating,f_tech,f_mom,f_whale,f_fund,f_val` | `as_of` | **2005-01-31 ~ 2026-05-29**(兩檔一致) | **實測 0 重複、全欄 0 null**;`adv100w` 檔 263,928 列 = 2,139 檔×257 月不重複鍵 | FULL_CONTENT | INSPECTED | READY | **明確範圍**:僅指「這兩份檔案本身的鍵唯一性、指定欄位缺值率、shape、日期範圍」已用完整檔案驗證。**不得延伸解讀成**「五維度評分定義已修好」或「V2 已可驗證」——`real_composite` 本身仍是 `docs/五維度修正工作計畫_2026-07-31.md` 標示的 frozen baseline,結構性問題(regime 混入等)未修,本次也未重算分數 |
| 真身 composite(生產即時快取,非研究面板) | `cloud_cache/Scores/*.parquet`(946 檔) | `(as_of,stock_id,mode)`,33 欄含 `regime,dyn_weight,data_gaps` 等 | `as_of` | 抽樣 2330.parquet:**僅 2026-07-08~2026-08-04(19 個交易日)** | 未全查(僅抽樣 1 檔) | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | PARTIAL | 歷史深度極短,**不可當 PIT 歷史研究面板使用**;L1 研究應仍用 `realbody_scores*.parquet` |
| `exec_ret.fwd_x` 正式報酬線欄位存在 | `data/research_base/exec_ret.parquet` | `as_of,stock_id,fwd_x,fwd_x60,...` | `as_of` | 2005-01-31 ~ 2026-05-29(shape 讀取) | — | METADATA_ONLY | PARTIALLY_INSPECTED | READY | 僅確認欄位存在與 shape(301,328×9),此為「唯一入口/正式欄位存在」的確認,非資料內容驗證 |
| `obs_alpha`/`exec_ret` 資料內容(缺值/鍵驗證) | `data/research_base/obs_alpha.parquet`(301,328×37)、`exec_ret.parquet`(301,328×9) | 同上;`obs_alpha` 含 `adv20,listed_ok` 等 | `as_of` | 2005-01-31 ~ 2026-05-29(shape 讀取) | **未逐欄缺值統計、未驗證鍵唯一性** | METADATA_ONLY | PARTIALLY_INSPECTED | **UNVERIFIED** | 僅讀 shape/schema,未做內容級的缺值/鍵驗證,資料內容不得標 READY;本輪未讀取任何報酬數值 |

---

## 2. L2 官方產業 PIT

| 模組/欄位 | 現有來源/路徑 | schema/鍵 | PIT 時間欄位 | 覆蓋起訖 | 缺值/唯一性 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|---|---|---|---|
| 產業對照原始檔 | `tej_exports/inbox_industry/Industry.xlsx` | 2,436 列×12 欄(TSE/TEJ 產業別與子產業) | **無任何日期/區間欄位** | 檔案 mtime 2025-07-15(僅落地時間,非分類生效時間) | 未全逐列核對 | METADATA_ONLY | PARTIALLY_INSPECTED | **BLOCKED** | 唯一產業分類來源,純快照,無版本化歷史;依 D3 裁定,任何依賴產業成員/集中度的**正式**歷史結論一律 BLOCKED |
| 快取層(`industry_map.parquet`/`.json`) | `~/tej_cache/industry_map.parquet`、`data/industry_map.json` | `{stock_id: industry_category}` 平面字典 | 無(僅 30 天快取新鮮度,非歷史版本) | — | — | METADATA_ONLY | INSPECTED | **BLOCKED** | `core/data_provider.py::_ensure_industry_map()`(第1147-1266行)無 `as_of` 參數,任何呼叫都拿「現在」的分類 |
| 消費端(backtest/PIT 路徑) | `core/backtest.py:634-643`、`core/data_provider.py:1588-1599` | 呼叫 `_ensure_industry_map().get(stock_id)`,忽略傳入的 `as_of` | 無 | — | — | CODE_ONLY | INSPECTED | **BLOCKED** | 程式碼已證實今天的分類被套用到 2005 年以來所有回測列,與 `docs/五維度修正工作計畫_2026-07-31.md` D8、本檔 D3 blocker 一致 |
| `core/sector.py`(A/B 權重分流) | 同上 | `classify(stock_id,industry,...)→'A'/'B'` | 無 `as_of` | — | — | CODE_ONLY | INSPECTED | **BLOCKED** | 非獨立資料源,是套在非 PIT 產業表上的二次分流,繼承同一問題 |
| 產業內估值位階(f_val 時間序列本身) | `~/market_cache/industry_value_ref.parquet`(44.5MB,mtime 2026-08-04);`core/industry_value.py::industry_value_pct(symbol,as_of)` | `stock_id,date,value_ind_pct` | **有** `date`,PIT 切片 | 文件宣稱 2019-04 起、1,952 檔(**UNVERIFIED**,未逐列驗證) | 未查 | METADATA_ONLY | PARTIALLY_INSPECTED | PARTIAL | 時間序列本身的 date≤as_of 切片機制無已知缺陷,但覆蓋率宣稱值未逐列驗證(僅確認檔案存在與大小/mtime) |
| 上述估值位階所依賴的產業分組(membership) | 同本節上方各列 | — | 無 | — | — | CODE_ONLY | INSPECTED | **BLOCKED** | 排名時間序列本身有 PIT,不代表其**產業分組**有——分組仍是同一份非 PIT 對照表,兩者不可混報 |

**Area 2 結論**:全 repo 僅一份產業成員/分類表,無任何版本化歷史表並存跡象,程式碼證實 `_ensure_industry_map()` 不接受 `as_of`。**維持 D3 裁定,ResearchReadiness = BLOCKED**(不是單純的 MISSING——這不只是「資料還沒補」,而是「用現有資料跑正式歷史結論會產生錯誤」)。

---

## 3. 題材標籤 PIT

| 模組/欄位 | 現有來源/路徑 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|
| 題材標籤系統 | 全 repo grep「題材/theme/tag」(股票分組語意) | CODE_ONLY | INSPECTED | MISSING | 5 個命中檔案全部是文件/註解(`docs/規劃_推薦投組系統V2.md` 明文「不存在,待新建」;`tests/run_backtest.py`、`watchlist.txt` 僅為中文分節註解),**未發現任何 tag/theme 資料結構或部分實作** |
| 相關 class/module 搜尋(`ThemeTag`/`theme_label`/`stock_tags` 等) | 全 repo grep | CODE_ONLY | INSPECTED | MISSING | 零命中 |

**未自行建立任何題材名單**,僅回報存在/缺席狀態,符合「今天整理的名單不得回填歷史」的禁止事項。**若正式策略要求題材層,該層驗證因此 BLOCKED**(見 B4 Readiness Summary);題材層在 MVP 階段可明確禁用,不影響其他層繼續設計。

---

## 4. 資料驅動相關群組(僅確認資料源,未計算相關性/聚類)

| 模組/欄位 | 現有來源/路徑 | schema/鍵 | PIT 時間欄位 | 覆蓋起訖 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|---|---|---|
| 候選來源①(主要,最完整) | `~/tej_cache/price_valuation/*.parquet`,共 **2,300 檔** | `stock_id,date,close,...` | 隱含(逐日) | 抽樣 5 檔:**2004-01-02 → 2026-07-14**(依個股上市早晚起點不同,終點一致) | SAMPLE_N=5(檔) | PARTIALLY_INSPECTED | PARTIAL | 僅抽樣 5 檔,維持 PARTIAL;未做去重複/缺值統計;未計算任何報酬/相關係數/聚類 |
| 候選來源②(增量延伸) | `~/market_cache/price_valuation_daily/*.parquet`,16 檔 | 同上(未逐檔核對) | 隱含(檔名即日期) | 檔名範圍 **2026-07-14 → 2026-08-04**(僅由檔名判讀) | METADATA_ONLY | PARTIALLY_INSPECTED | PARTIAL | 與來源①合併後理論覆蓋至 2026-08-04,但**合併後零缺口未驗證** |
| 候選來源③(次要,覆蓋小) | `~/finmind_cache/TaiwanStockPrice/*.parquet`,僅 **77 檔** | `date,stock_id,close,...` | 隱含 | 抽樣 0050:2019-01-02~2026-07-22 | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | PARTIAL | 覆蓋股數遠小於①,不建議作全市場聚類主來源 |
| 產業對照鍵(僅供聚類結果比對用) | 同 §2 | — | 無 PIT | — | CODE_ONLY | INSPECTED | **BLOCKED** | 若未來聚類要與官方產業比較,需注意該對照同樣非 PIT,見 §2 |

**結論**:日頻價格資料存在,最佳候選是 `~/tej_cache/price_valuation/*.parquet`(2,300 檔、2004 起、鍵 `stock_id+date`)。**未執行任何讀取以外的操作**。此層在 MVP 階段可明確禁用(先用官方產業或題材層替代),不影響其他層繼續設計。

---

## 5. L3 進場資料(僅資料可用性,未生成任何 Z1 訊號)

> **證據強度說明**:下表的 OHLC/ATR/MA/POC 皆源自同一份**單股抽樣**(2330.parquet),原標
> `READY` 過度延伸為全市場結論。拆為「計算邏輯介面」(READY)與「全市場資料內容」
> (UNVERIFIED)兩列。

| 模組/欄位 | 現有來源/路徑 | schema/鍵 | PIT 時間欄位 | 覆蓋起訖 | 缺值/唯一性 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|---|---|---|---|
| OHLC 日K——讀取介面 | `core/data_provider.py::_read_local_price_valuation` | `stock_id,date,open,max,min,close,Trading_Volume`(schema 定義) | `date` | — | — | CODE_ONLY | INSPECTED | READY | 讀取邏輯(TEJ 種子 ∪ market_cache 每日增量)本身存在 |
| OHLC 日K——全市場內容 | 同上實際檔案(TEJ 種子 ∪ market_cache 每日增量) | 同上 | `date` | 抽樣 2330:2004-01-02→2026-07-14(種子)+ 增量至 2026-08-04 | 抽樣 2330:0 缺值、`date` 無重複(5541列) | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 僅驗證單股(2330),非全 2,300 檔;不能宣稱全市場覆蓋已就緒 |
| ATR 所需 high/low/close——計算邏輯 | `core/technical_analysis.py::calculate_atr`(第203-220行) | 相容 `high/low` 或 `max/min` 命名 | — | — | — | CODE_ONLY | INSPECTED | READY | 計算邏輯本身存在,未計算 ATR 數值 |
| ATR 所需 high/low/close——全市場內容 | 同 OHLC 全市場內容列 | 同上 | 同上 | 同上 | 同上 | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 與 OHLC 全市場內容同一份資料,結論同上 |
| MA/乖離率候選——計算邏輯 | `TechnicalEngine.calculate_ma/calculate_bias/calculate_ma_cross`(第167-289行) | 僅需 `close` | — | — | — | CODE_ONLY | INSPECTED | READY | 計算邏輯本身存在 |
| MA/乖離率候選——全市場內容 | 同 OHLC 全市場內容列 | 同上 | 同上 | 同上 | 同上 | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 同上 |
| POC/Volume Profile 候選——計算邏輯 | `TechnicalEngine.calculate_volume_profile`(第417行起) | 需 `close`+`Trading_Volume` | — | — | — | CODE_ONLY | INSPECTED | READY | 邏輯與輸入欄位定義皆存在,未執行計算 |
| POC/Volume Profile 候選——全市場內容 | 同 OHLC 全市場內容列 | 同上 | 同上 | 同上 | 同上 | SAMPLE_N=1(檔) | PARTIALLY_INSPECTED | **UNVERIFIED** | 同上 |
| 交易日曆 | **無獨立模組**;各腳本自行由「當日收盤檔數門檻」推導(`scripts/shortlist_ledger.py::trading_calendar()`、`scripts/portfolio_simulator_lab.py::trading_calendar()`) | `list[str]`,依 `MIN_STOCKS_PER_DAY` 閾值過濾 | `date` | 依價格來源而定 | 未查(依賴閾值,非官方日曆) | CODE_ONLY | INSPECTED | PARTIAL | 程式碼已確認目前是「衍生」而非「權威」交易日曆;涉及停牌/國定假日/颱風假的**正式執行模擬** BLOCKED(見 B4),但一般月/週頻排序可先用此衍生日曆 |
| 大盤指數(參考顯示用) | `core/market_index.py`(`~/market_cache/taiex_daily.parquet`) | `date,close,chg_pct,turnover,adv,dec,unch` | `date` | 實測 2004-01-02~2026-08-04(5556列) | `adv/dec/unch` 種子期系統性缺值(程式註解自陳) | METADATA_ONLY | INSPECTED | READY | 僅供顯示,不驅動訊號;單一指數檔案(非跨股抽樣) |

---

## 6. `ReentryContext` / L5(規劃中介面,U10)

| 模組/欄位 | 現有來源/路徑 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|
| `trade_id` | 全庫搜尋無任何結果 | CODE_ONLY | INSPECTED | MISSING | 概念不存在,需 Phase 2 依 U10 定義後新建 |
| L4b ExecutionLedger(成交確認/receipt) | `core/backtest.py::_simulate_exit`(第849-913行)僅為**回測模擬**用出場函式,非持久化執行帳本,不含 `trade_id`、無訂單撮合概念 | CODE_ONLY | INSPECTED | MISSING | `docs/規劃_推薦投組系統V2.md` §9/C13 本身已標記撮合演算法為 UNRESOLVED |
| 退出原因(持久化版) | `_simulate_exit` 有 4 種模擬退出原因(`dynamic_support`/`vol_trailing`/`chase_cap`/`time_stop`),但僅存於回測模擬輸出,不落地 | CODE_ONLY | INSPECTED | PARTIAL | 回測模擬層有概念,無持久化;需另建真實/回放成交後的退出原因記錄機制 |
| 前次 `P0/S0/R0` | 無持久化欄位;`core/trade_plan.py::TradePlan` 只即時計算「現在該怎麼進場」,不回溯保存「當初」的值 | CODE_ONLY | INSPECTED | MISSING | 需新建持久化交易記錄表,且需先有 `trade_id`/ExecutionLedger |
| 最後有效停損 | 無持久化欄位;`core/backtest.py` 動態停損僅在回測模擬迴圈當下逐步更新,不落地 | CODE_ONLY | INSPECTED | MISSING | 同上,需一併納入新建交易記錄表 |
| Position/trade history(`PositionState`) | 全庫搜尋 `PositionState`/`position_history` 無任何結果 | CODE_ONLY | INSPECTED | MISSING | 規劃文件本身標示 `PositionState` 為唯一只能由 L4b 改寫的規劃中狀態物件,目前完全未實作 |
| 相近但非執行帳本的既有檔案(供對照) | `outputs/portfolio/tracking.csv`(觀察清單快照,無 `trade_id`/退出欄位,僅見至 2026-07-10);`outputs/universe_pool/fills_2026-07-17.csv`(單日模擬進場,僅 7 檔,`shares` 欄目測全空) | METADATA_ONLY | INSPECTED | PARTIAL | 零星研究快照,不可直接復用;若要作 `ReentryContext` 資料源基礎,需擴充為持續維護、含出場欄位、含 `trade_id` 的正式帳本 |

**結論**:除規劃文件本身已誠實列為 UNRESOLVED U10/C13 外,程式碼庫中**沒有任何模組**能直接供應 `ReentryContext` 所需欄位——此為 Phase 0 規劃文件本身已承認的 schema 缺口(ResearchReadiness = MISSING,查核本身已完整執行,不是查核失敗)。**`Z1-R`/`E1-R` 的正式驗證因此 BLOCKED**(見 B4);MVP 階段可先禁用 `Z1-R`/`E1-R`,只驗證 `Z1-P`/`Z1-B` + `E0`/`E1`,其餘層不受影響。

---

## 7. L4b 執行模擬

| 模組/欄位 | 現有來源/路徑 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|
| OHLCV+成交值 | FinMind `TaiwanStockPrice`(含 `Trading_money`,快取僅 77 檔) | METADATA_ONLY | PARTIALLY_INSPECTED | **PARTIAL** | **修正**:FinMind 只有 77 檔快取(遠不足全市場),TEJ `price_valuation` 又缺 `Trading_money`(只有成交量,無成交值),兩來源皆不完整,**不能標成全市場 READY**;需混用兩來源仍有缺口,**正式全市場執行仍 BLOCKED**(見 B4) |
| 漲跌停 | 全 `core/*.py` 搜尋「漲跌停/price_limit/limit_up/limit_down」**無命中** | CODE_ONLY | INSPECTED | MISSING | 現有 OHLC 皆無漲跌停旗標/理論價;`spread` 可反推但無現成邏輯 |
| 交易單位/零股 | `core/data_provider.py` 僅有股→張的**顯示換算**,非零股撮合建模 | CODE_ONLY | INSPECTED | MISSING | 無零股 vs 整股分開建模邏輯 |
| 除權息/拆併股調整 | `core/backtest.py::_back_adjust`(第90行),偵測 `close[i]/close[i-1]` 跳空(&lt;0.7 或 &gt;1.5)接平 | CODE_ONLY | INSPECTED | PARTIAL | 啟發式跳空偵測非精確複權;含息報酬用殖利率均攤(`scripts/build_exec_ret.py`),非真實除息事件重建(`docs/現況盤點_2026-07-29.md` §L2 已載明此邊界) |
| 手續費/交易稅——既有常數存在 | `beat_0050/honest_backtest.py`:`COST_RT=0.47`、`SLIPPAGE_RT=0.25` | FULL_CONTENT(常數值本身已完整讀取) | INSPECTED | READY | **明確範圍**:只證明研究腳本中存在這兩個常數及其目前值;不是 TEJ 資料缺口,也不代表費率適用於 V2 |
| 手續費/交易稅——V2 政策正確性 | 尚無 V2 正式成本設定;現有常數位於研究腳本,非 `core/config.py` | FULL_CONTENT(僅完整讀取現有常數) | PARTIALLY_INSPECTED | **UNVERIFIED** | 尚未確認費率單位、買賣方向、折扣、最低手續費、交易稅適用範圍及是否符合研究執行時點;正式採用前須凍結政策並遷移至正式模組 |
| Partial-fill/執行帳本 | `core/backtest.py` 單部位出場模擬(假設 100% 全部成交,無流動性限制) | CODE_ONLY | INSPECTED | MISSING | `docs/規劃_推薦投組系統V2.md`(commit `d282e2f`)自身已列 `OrderIntent` 狀態鏈與 L4b 為 Phase 2+ 待新建;C13 撮合演算法為 open item |
| `obs_alpha.adv20`——欄位 schema | `data/research_base/obs_alpha.parquet` | METADATA_ONLY | PARTIALLY_INSPECTED | READY | 僅確認欄位存在於 schema 中,可供後續限制邏輯使用 |
| `obs_alpha.adv20`——全期全股 coverage | 同上 | METADATA_ONLY | PARTIALLY_INSPECTED | **UNVERIFIED** | 只確認欄位存在,**不等於全期全股 coverage 已驗證**;coverage 需另行檢查 |
| 0.1% ADV20 限制邏輯(執行層實作) | 全 repo 搜尋無對應實作 | CODE_ONLY | INSPECTED | MISSING | 「單筆 ≤0.1% ADV20」限制本身未實作 |

**結論**:漲跌停、零股、partial-fill、持久化 ExecutionLedger、精確公司行動(除權息/減資/分割合併)資料**與全市場 OHLCV+成交值覆蓋**合計不足,**正式可執行回測 BLOCKED**(見 B4);Phase 2 仍可先設計 T+1/滑價/成本規則與 `OrderIntent` 狀態鏈的 schema,不受此 BLOCKED 影響。

---

## 8. L6a 重大事件(個股層級,僅本 repo 內查核)

| 模組/欄位 | 現有來源/路徑 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|
| 個股重大事件旗標——匯入路徑 | `tej_exports/inbox_events/`(**確認不存在**)、`docs/預註冊_EventFlagLab.md`(F1-F3,2026-07-18 凍結)、`scripts/event_flag_lab.py`(**確認不存在**) | EXISTS_ONLY | INSPECTED | MISSING | 需使用者從 TEJ Pro 匯出 `tej_exports/inbox_events/`;**使用者另有「消息」專案可能持有相關資料,但未獲授權跨專案讀取,本次只記為 external dependency, not accessed** |
| 個股重大事件旗標——匯入程式 | `tej_importer.py`(無 events handler) | CODE_ONLY | INSPECTED | MISSING | 即使未來取得資料,匯入程式本身也需新建 handler |

**結論**:L6a 資料在本 repo 內完全不存在,屬 Phase 0 preflight 預期發現(ResearchReadiness = MISSING,查核本身已完整,非異常)。**若啟用重大事件強制退出,正式驗證 BLOCKED**(見 B4);MVP 階段可先禁用 L6a,只用 L6b 市場層風控,其餘層不受影響。

---

## 9. L6b 市場狀態

> **證據強度說明**:等權全市場指數(regime 實際驅動來源)原標 `READY`,但只讀了計算函式
> 程式碼,未讀取底層任一價格檔案的實際內容。拆為「計算介面」(READY)與「底層全市場價格
> 內容」(UNVERIFIED)兩列。

| 模組/欄位 | 現有來源/路徑 | schema/鍵 | PIT 時間欄位 | 覆蓋起訖 | 缺值/唯一性 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|---|---|---|---|
| 加權指數/量能(顯示參考層) | `core/market_index.py`(`~/market_cache/taiex_daily.parquet`,219KB,mtime 2026-08-04) | `date,close,chg_pct,turnover,adv,dec,unch` | `date` | 未讀取內容(僅確認檔案存在) | `adv/dec/unch` 種子段系統性缺值(程式註解自陳) | EXISTS_ONLY | PARTIALLY_INSPECTED | PARTIAL | breadth 若用 adv/dec,需先確認種子段缺值範圍 |
| 等權全市場指數——計算介面 | `core/regime_exposure.py::_ew_index()` | `stock_id,date,close`→等權指數+MA50/100/200(函式邏輯定義) | `date` | — | — | CODE_ONLY | INSPECTED | READY | 計算函式邏輯本身存在 |
| 等權全市場指數——底層全市場價格內容 | 函式讀取 TEJ+market_cache 的實際檔案(本輪未開啟任一檔案內容) | 同上 | `date` | 未讀取任何內容 | — | CODE_ONLY | PARTIALLY_INSPECTED | **UNVERIFIED** | 只讀程式介面,未驗底層全市場內容;不得把資料內容標 READY |
| Regime 曝險快照(已落地) | `cloud_cache/regime_exposure.json`(8KB,mtime 2026-08-04) | `exposure,target_exposure,as_of,hist,...` | `as_of="2026-08-04"` | **hist 陣列:2026-01-30 → 2026-08-04** | 單一快照,非逐股表 | FULL_CONTENT(單一小型 JSON,已讀取實際內容) | INSPECTED | READY | 無 |
| Regime 分類介面 | `core/regime.py::classify_regime(bench_price_df, as_of)` | 純函式,PIT-clean(`_confirmed_regime_series` 逐日切片) | 函式保證 date≤as_of | — | — | CODE_ONLY | INSPECTED | READY | 這是函式邏輯保證的確認(介面性質),非資料內容 |
| 市場情緒/籌碼分析模組 | `core/market_sentiment.py` | 程式自陳(第6行)「**目前尚未被 main.py 主流程引用,屬獨立/實驗性工具**」,且底層 API 呼叫可能不存在於 FinMind SDK | — | — | — | CODE_ONLY | INSPECTED | PARTIAL | 實驗性,若要當 L6b 正式輸入,需先修正資料源呼叫並接線驗證 |
| 廣度候選(新高比例/相關性等,adv/dec 以外) | 無獨立模組,僅見於 `docs/規劃_推薦投組系統V2.md` §4 設計候選 | — | — | — | — | CODE_ONLY | INSPECTED | MISSING | 屬 Phase 2 規格設計範圍,非本次盤點缺口 |
| 交易日曆(權威版) | 無獨立資料集;`core/crawler.py` 用「抓不到=隱含休市」推斷,且該模組標記 DEPRECATED | — | — | — | — | CODE_ONLY | INSPECTED | MISSING | 若需精確交易日曆(國定假日/颱風假等),需另建來源;與 §5 交易日曆同一議題,涉及 T+1/停牌處理的**正式執行模擬 BLOCKED**(見 B4) |

---

## 10. `DecisionClock` / Validation Guard 現有能力

| 欄位 | 現有來源/路徑 | EvidenceScope | InspectionStatus | ResearchReadiness | blocker/下一步 |
|---|---|---|---|---|---|
| `as_of` | 廣泛存在:`core/score_store.py`(`score_row()`、`_DEDUP_KEYS`、`as_of_dates()`)、`core/regime.py`、`core/regime_exposure.py`、`core/market_index.py` | CODE_ONLY | INSPECTED | READY | 已是既有慣例(程式碼層確認),可直接沿用 |
| `generated_at` | 僅見於 provenance manifest 工具(`scripts/build_provenance_manifest.py`、`beat_0050/results/gate1/gate1_preflight.json` 的 `run_started_at`),**不存在於** `score_row()` 逐列輸出 | CODE_ONLY | INSPECTED | PARTIAL | 需把此欄位加進訊號記錄 schema(目前只在 build 工具層) |
| `valid_from`/`valid_until` | 全程式碼**未找到**,僅出現在規劃文件作為 CANDIDATE 待決欄位 | CODE_ONLY | INSPECTED | MISSING | 屬 U7 DecisionClock 待凍結項 |
| `source_snapshot_hash` | 未找到完全同名欄位。最接近:`score_store.py::_weights_version()`(雜湊**評分權重/設定**,非資料快照)、`build_provenance_manifest.py`(對**原始碼**與**已產出面板**算 sha256) | CODE_ONLY | INSPECTED | PARTIAL | 雜湊技術能力已具備,但雜湊對象不是「產生訊號當下的輸入資料快照」,需新增對準此概念的欄位/函式 |
| Append-only access receipt | 未找到持續性 access-log。最接近:`build_provenance_manifest.py` 產出 `data/research_base/arms/provenance/MANIFEST.json`、`beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json`/`gate1_preflight.json`(含多組 sha256、git commit),但這些是**手動觸發、單次快照式**,不是「每次讀取自動 append 一筆」的機制 | CODE_ONLY | INSPECTED | PARTIAL | 技術基礎(雜湊鏈/manifest)與研究紀律精神高度一致,可在此基礎上擴建;**進入正式 Validation 前 BLOCKED,但不阻擋 Phase 2 設計**(見 B4) |
| `OrderIntent`/`Signal` 訊號記錄 schema | `core/models.py` 僅有 `StockData`、`ScoreResult`,無对应 dataclass;全 `core/`、`beat_0050/**` 搜尋 `class Signal\|OrderIntent` 無結果 | CODE_ONLY | INSPECTED | MISSING | Phase 2 規格設計範圍 |

> 排查邊界說明:為確認 `core/market_index.py`/`core/regime_exposure.py` 引用的快取檔**確實存在**,對 `~/market_cache`、`~/tej_cache` 做過一次檔名/大小/mtime 的目錄列表(無讀取內容),此為專案自身指定的資料落地位置(非外部「消息」專案),視為排查範圍內合理操作。

---

## B3 強制研究邊界:合規聲明

- **不因資料存在而宣稱策略有效**——本報告的 `READY` 類判斷只描述「資料可用於下一步規格設計或驗證」,不等於策略本身有效或已驗證。
- **不因資料缺失而修改 U1–U11 政策值**——本輪對 U1–U11 只回答「資料盤點是否縮小選項」,未替使用者關閉或改動任何一項政策決定(見 B4 U1–U11 狀態表)。
- 未讀取或計算任何候選投組的未來報酬。
- 未計算 CAGR、Sharpe、MDD、勝率、IC、alpha 或任何績效指標。
- 未產生 Top K、Z1/E1 訊號、族群狀態、相關群組或投組建議。
- 未把 `obs_alpha.fwd` 當報酬線;本輪未讀取任何報酬數值。已確認 `exec_ret.fwd_x` 為正式報酬線入口(schema 存在),供未來驗證階段使用。
- 未解除 Gate 2 preflight,未宣稱 C3 可部署。
- 唯一涉及「外部」路徑的操作(`~/market_cache`、`~/tej_cache` 目錄列表)屬專案自身資料落地位置,非跨專案存取;「消息」專案完全未被存取,僅記為 external dependency。
- 除本檔外,本輪未新增任何 cache、CSV、JSON、parquet、results 或暫存研究產物。

---

## B4 結論

> **兩種狀態不是同一件事(第二輪修正,2026-08-05)**:上一版報告寫「沒有任何項目被標記 BLOCKED」,
> 但同時列出官方產業 PIT、財務真實公告日、L4b 執行帳本等一系列正式研究層級的 blocker——
> 這是把**「本次唯讀查核有沒有被技術卡住」**與**「這些資料是否足以支撐正式研究/驗證」**
> 兩個不同概念混在一起。本版把每一項拆成兩欄:
>
> - **`InspectionStatus`**:本次唯讀查核本身有沒有完成(`INSPECTED`/`PARTIALLY_INSPECTED`/`NOT_INSPECTED`)。
> - **`ResearchReadiness`**:這份資料是否足以支撐正式規格凍結或正式驗證(`READY`/`PARTIAL`/`MISSING`/`BLOCKED`/`UNVERIFIED`)。
>
> **本次 preflight 查核本身沒有被技術阻擋,不代表各研究層沒有 readiness blocker。**
> 上一版報告「沒有任何項目 BLOCKED」的措辭僅適用於 `InspectionStatus`(查核執行面),
> 不適用於 `ResearchReadiness`(研究就緒面)——後者有多項 `BLOCKED`,詳見下方 Readiness Summary。

### Phase 1 結論狀態

```text
PreflightExecution = PASS
ResearchReadiness  = PARTIAL_WITH_BLOCKERS
```

**目前沒有任何策略層因抽樣/schema 檢查而被宣稱為全面 `READY`**(第三輪修正,2026-08-05)——
下方 Readiness Summary 十層中沒有一層的整體 `ResearchReadiness` 是 `READY`;凡原先因單股
抽樣、只讀程式碼或只確認檔案存在而標記 `READY` 的資料內容項目,均已降級為 `UNVERIFIED`
或 `PARTIAL`,只有計算邏輯/介面本身、政策常數,或**已用完整檔案驗證鍵唯一性與缺值**的
`real_composite` 面板(見 §1,範圍已明寫)才保留 `READY`。

`overall = PARTIAL`(沿用)僅描述 `ResearchReadiness` 的整體分布,不代表查核執行本身有缺口——
`PreflightExecution = PASS` 才是回答「本次唯讀查核有沒有被技術卡住」,兩者需分開讀。

**修正(第三輪,2026-08-05)**:資料版圖不是「多數 READY、少數 BLOCKED」的兩極——上一版把
單股抽樣/純程式碼確認的項目也計入「相對完整」,證據強度不足以支撐。校正後的實況是:
**計算邏輯/介面層**(唯一入口、`report_ladder`、估值/籌碼/技術計算邏輯、ATR/MA/POC 邏輯、
`regime` 分類介面、`as_of` 慣例等)與**少數已用完整檔案驗證的資料**(`real_composite` 面板、
`regime_exposure.json` 快照)確認 `READY`;但**全市場資料內容**(估值/籌碼/技術的全市場覆蓋、
L3 OHLC 全市場覆蓋、L6b 等權指數底層價格、`obs_alpha`/`exec_ret` 缺值與鍵驗證)因僅
`SAMPLE_N=1` 或 `CODE_ONLY` 而降級為 `UNVERIFIED`;**L1 財務 PIT、L2 產業 PIT、題材標籤、
L4b 執行帳本、L6a 個股事件、ReentryContext/L5、DecisionClock 的 `valid_from`/`valid_until`
等,`ResearchReadiness` 為 `BLOCKED` 或 `MISSING`**。這些正是 V2 架構中「規劃但尚未實作」、
「現有假設不足以支撐正式驗證」或「只驗證過小樣本、不能外推全市場」的部分,與
`docs/規劃_推薦投組系統V2.md` 自身的 Decision Register(CANDIDATE/UNRESOLVED 項目)完全
對應——**沒有查到任何超出預期的驚喜缺口**,`InspectionStatus` 也沒有任何一項卡在無法完成
查核的狀態(即 `NOT_INSPECTED` 未出現)。

### Readiness Summary(依層/能力彙總)

> **第三輪修正(2026-08-05)**:每層的 `ResearchReadiness` 改為**該層必要元件中最弱者**決定
> 整體狀態,不再於同一格寫 `READY(...)/PARTIAL(...)` 這類複合值;已就緒的子項改記在
> 「已 READY 子項(備註)」欄。**目前沒有任何策略層因抽樣/schema 檢查而被宣稱為全面
> `READY`**——下表沒有任何一列的 `ResearchReadiness` 是 `READY`。

| 層/能力 | InspectionStatus(該層代表值) | ResearchReadiness(該層最弱必要元件) | 狀態依據/已 READY 子項(備註,不代表整層) | 是否阻擋 Phase 2 設計 | 是否阻擋正式 Validation | 解鎖條件 |
|---|---|---|---|---|---|---|
| L1 選股本體 | PARTIALLY_INSPECTED | **BLOCKED** | 財務 PIT 為必要元件且 BLOCKED;已 READY:唯一入口/`report_ladder`/估值介面/籌碼介面/技術介面/`real_composite`(明確範圍內,見 §1)/`exec_ret.fwd_x` 欄位存在 | 否——可先設計 schema/介面,財務 PIT 議題不影響 Phase 2 討論 | **是**——僅限使用財務資料的正式驗證;`real_composite` 在其明確驗證範圍內不受影響 | 取得財報實際公告/可得日期,或凍結並記錄一個可證明安全的保守 `PUBLISH_LAG` 規則 |
| L2 官方產業 | PARTIALLY_INSPECTED | **BLOCKED** | 各子項查核程度見 §2;無 READY 子項,全部為 BLOCKED 或 PARTIAL | 否——可先設計介面/schema(假設未來有 `effective_from/to`) | **是**——任何依賴產業成員/集中度的正式歷史結論 | 取得產業分類歷史版本表(含生效/失效日) |
| 題材標籤 | INSPECTED | MISSING | 無 | 否 | **是**(若正式策略啟用題材層);**可 MVP 禁用題材層,不影響其他層設計/驗證** | 建立題材標籤來源+版本化快照機制(`effective_from/to/as_of`) |
| 資料驅動相關群組 | PARTIALLY_INSPECTED | PARTIAL | 無 | 否 | **是**(若正式策略啟用此群組層);**可 MVP 禁用,先用官方產業或題材層替代** | 決定窗長/聚類法/重估頻率/最小樣本(U5),並驗證資料合併後無缺口 |
| L3 進場資料 | PARTIALLY_INSPECTED | **UNVERIFIED** | 全市場內容僅單股抽樣;OHLC/ATR/MA/POC 全市場內容皆為 `SAMPLE_N=1`,交易日曆另為 PARTIAL;已 READY:計算邏輯介面(`CODE_ONLY`)、大盤指數 | 否 | **是**(全市場覆蓋內容未驗證前,不進入正式驗證);交易日曆另涉及 T+1/停牌的正式執行模擬 BLOCKED | 對全市場(而非單股)OHLC 資料做覆蓋率/缺值/唯一性驗證;建立官方/權威交易日曆 |
| L5 / `ReentryContext` | INSPECTED | MISSING | 無 | 否——可依 U10 先設計 schema | **是**——`Z1-R`/`E1-R` 正式驗證;**可 MVP 先禁用,只驗證 `Z1-P`/`Z1-B` + `E0`/`E1`** | 建立 `trade_id`/execution ledger/持久化交易記錄表 |
| L4b 執行模擬 | PARTIALLY_INSPECTED | **BLOCKED** | 各子項查核程度見 §7;漲跌停/零股/partial-fill/ExecutionLedger 皆 MISSING,OHLCV+成交值為 PARTIAL;已 READY:手續費/交易稅**常數存在**(`FULL_CONTENT`)、`adv20` 欄位 schema,但 V2 成本政策正確性仍 UNVERIFIED | 否——可先設計 T+1/滑價/成本規則與 `OrderIntent` 狀態鏈 schema | **是**——正式可執行回測 | 取得漲跌停理論價、交易單位變更歷史、精確除權息/減資/分割合併事件資料、全市場 OHLCV+成交值覆蓋,確認並凍結 V2 成本政策,並實作 partial-fill 撮合邏輯 |
| L6a 個股重大事件 | INSPECTED | MISSING | 無 | 否——可依 U6 先設計 schema | **是**(若啟用重大事件強制退出);**可 MVP 先禁用 L6a,只用 L6b 市場層風控** | 取得 TEJ 事件匯出,或使用者另一「消息」專案的資料(需另行授權,本輪未存取) |
| L6b 市場狀態 | PARTIALLY_INSPECTED | **UNVERIFIED** | 等權指數底層內容、加權指數量能皆未讀取;已 READY:Regime 分類介面(`CODE_ONLY`)、Regime 曝險快照(`FULL_CONTENT`,已落地小型 JSON)、等權指數計算介面 | 否 | **是**(regime 實際依賴的底層價格內容未驗證前不宜視為就緒);另涉及精確交易日曆或 `market_sentiment` 的子功能 | 對等權指數所依賴的全市場價格資料做實際內容驗證(非僅讀程式介面);同 L3 交易日曆;修正 `market_sentiment.py` |
| `DecisionClock`/Validation Guard | INSPECTED | MISSING | `valid_from`/`valid_until`、`OrderIntent` schema 為必要元件且 MISSING;已 READY:`as_of` | 否——欄位定義本身是 Phase 2 的工作內容 | **是**——access receipt 缺口須在正式 Validation 開始前補上(U9) | Phase 2 內設計 `DecisionClock` 五欄位 schema;新增 append-only access receipt 機制 |

### U1–U11 狀態:資料盤點縮小 vs. 仍需使用者政策決定

| # | 資料盤點是否縮小選項 | 說明 |
|---|---|---|
| U1(產業35%警示) | 否 | 純政策數值,與資料可用性無關 |
| U2(題材上限) | 否 | 純政策數值;且題材系統本身 MISSING,尚無法操作化 |
| U3(相關性門檻) | 部分 | 資料源已確認(TEJ price_valuation),但門檻本身仍是政策/研究決定 |
| U4(題材PIT快照格式) | **是** | 題材系統確認完全不存在(MISSING),排除「沿用/擴充既有系統」選項,確定須從零設計 |
| U5(相關群組窗長/聚類法等) | **是** | 資料最早只能從 2004-01-02 起(TEJ 種子),為窗長選擇劃出明確邊界;方法本身仍需決定 |
| U6(L6a事件語義) | 否 | 資料源完全 MISSING,語義仍需使用者政策決定,且需先解決資料取得 |
| U7(DecisionClock) | 部分 | `as_of` 已有慣例可沿用,但衝突優先序/有效期規則需全新設計,非資料盤點可縮小 |
| U8(加碼N定義) | 否 | 純政策決定,不受資料盤點影響 |
| U9(Validation access guard) | **是** | 已有 sha256/manifest 技術先例(`build_provenance_manifest.py`、Gate 1 provenance json),縮小為「擴建現有機制」而非「從零做雜湊」;schema/封存細節仍需設計決定 |
| U10(ReentryContext schema) | **是** | 確認全部欄位 MISSING,縮小為「須整個新建」;退出原因清單/觀察期限仍需政策決定 |
| U11(Z1-R母交易加碼模式) | 否 | 純政策決定,資料盤點未涉及 |

---

## B5 TEJ / 本地資料取得清單

> 以下**只依語意列出必要欄位**,不捏造未核對的 TEJ 正式欄位名稱(本輪未查證 TEJ Pro
> 實際匯出介面的確切欄名)。使用者另有「消息」專案,仍只列為 external dependency,
> **不得跨專案讀取**。

| 優先級 | 資料集語意 | 必要鍵 | 必要 PIT 時間欄位 | 必要內容 | 解鎖模組 | 可否以現有資料替代 |
|---|---|---|---|---|---|---|
| 高 | 財報實際公告/可得日期 | `stock_id`、財報期別 | 公告日/可得日 | 每筆財報(季/年)實際對外公告或可取得的日期 | L1 財務 PIT 驗證(解除 BLOCKED) | **否**——目前只有固定 45 天假設,無法用現有資料推算真實公告日 |
| 高 | 股票產業分類歷史 | `stock_id`、分類版本/生效區間 | `effective_from`/`effective_to`(或至少分類變更日) | 每次產業歸類變更的起訖日與新舊分類 | L2(解除 D3 BLOCKED)、集中度計算、族群狀態母體 | **否**——現有 `Industry.xlsx`/`industry_map.*` 僅單一今日快照 |
| 高 | 個股重大事件(處置/注意股票/全額交割/停止交易) | `stock_id`、事件類型 | 事件生效日、市場可得(公告)時間 | 事件類型、起訖日、嚴重度 | L6a(解除 MISSING)、強制退出功能 | **否**——repo 內無此資料,`docs/預註冊_EventFlagLab.md` 已有規格但無資料落地;使用者另有消息專案,本次未存取,需使用者自行決定是否授權 |
| 中 | 官方交易日曆、停牌/恢復交易資訊 | 日期 | 是否交易日、停牌起訖 | 完整交易日清單+個股停牌事件 | L3/L6b(交易日曆權威化)、T+1 執行 | **部分**——目前用「當日收盤檔數門檻」推導可作暫時替代,但無法處理個股停牌 |
| 中 | 每日漲跌停理論價或可重建欄位 | `stock_id`、`date` | `date` | 當日漲跌停價,或計算所需的前收盤+漲跌幅規則 | L4b(解除 MISSING) | **部分**——`spread` 欄可能可反推,但無現成邏輯,未驗證 |
| 中 | 股票交易單位與變更歷史、零股可交易資訊 | `stock_id`、生效日 | 生效日 | 每股交易單位(股/張)及變更日、零股是否可交易的規則 | L4b(零股撮合) | **否**——現有資料僅有股→張的顯示換算,無變更歷史 |
| 中 | 除權息、減資、分割/合併及生效日 | `stock_id`、`date` | 生效日 | 事件類型、調整比例、生效日 | L4b(精確複權)、L1 估值 | **部分**——`core/backtest.py::_back_adjust` 有啟發式跳空偵測可作暫時替代,但非精確複權 |
| 低(政策常數,非資料缺口) | 手續費/交易稅率 | — | — | 現行費率、稅率 | L4b | **是**——這是政策常數,**不應誤列為必須由 TEJ 提供**;現有 `beat_0050/honest_backtest.py::COST_RT/SLIPPAGE_RT` 已有數值,僅需遷移至正式模組並由使用者/研究者確認費率是否符合現況 |

### 明確聲明

**本輪未執行任何績效、回測、OOS、calibration、timing、synthetic 或 Gate 相關計算或操作。** 本報告只回答「資料是否存在、是否 PIT、是否足以進入 Phase 2 規格設計」,不對任何策略有效性做出判斷。
