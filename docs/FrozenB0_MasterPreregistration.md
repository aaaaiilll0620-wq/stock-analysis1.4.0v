# Frozen B0 — Master Preregistration

**版本:** 1.25（v1.0 凍結 2026-08-17；v1.1 = P-1a，關閉 O-A ~ O-D；v1.2 = O-E closure，關閉 O-E / O-E-1 並新增 D-1 blocking requirement；v1.3 = P-1b omission corrections C-16 ~ C-20；v1.4 = A/B/C resolutions C-21 ~ C-27；v1.5 = 7 個 D 項與 σ20D ddof：C-28 ~ C-35；v1.6 = C-36，canonical core 規格完備，OPEN SPEC ITEMS = 0；v1.7 = P-2 shared route 與兩個 adapter 建成，B-20 route pair 宣告：C-37；v1.8 = D-1 驗證跨來源強化與來源 quarantine：C-38；v1.9 = D-1 由 20260817 重新匯出關閉，C2 與 backstop 判準缺陷修正：C-39。新開 O-F；v1.10 = O-F 狀態來源改用 20260818 重新匯出並完成 PIT audit：C-40；v1.11 = O-F 以 incomplete-source / fail-loud 關閉、O-G listing spell 開立並關閉、暫停交易事件語義分類、S-3b 改為 enforcement 準則並 SATISFIED：C-41 ~ C-44；v1.12 = F-0 hash boundary audit：C-45；v1.13 = F0-R1 ~ F0-R7 正式裁決落地，hash scope 凍結、declaration conformance 機制建立、B-21 manifest 直綁七層、單一 hash primitive，F-0 CLOSED：C-46；**v1.14 = M-3 `pre_l2_seal_semantics` 裁決落地，provenance 分兩階段（B0 Baseline Seal / L2 Run Provenance），seal critical section 綁 repo identity，測試不得弄髒工作區，CRLF→LF 遷移帳本建立：C-47；**v1.15 = M-3 `value_pbr_lineage_2019plus` 裁決落地（R1~R7），官方 TWSE/TPEx 歷史 PBR 為 2019+ admissible lineage continuation，TPEx vintage limitation 與 2025+ coverage regime 具名揭露，新增 normative module `core/b0_valuation_source.py`，OPEN SPEC ITEMS 回到 0：C-48；**v1.16 = M-3 `value_per_lineage_2019plus` 以自身證據裁決落地，官方 TWSE/TPEx 歷史本益比為 2019+ `per_tse` 的 admissible continuation，0.0 sentinel 語義凍結，valuation panel 改綁 `resolve_as_of`，OPEN SPEC ITEMS 再回到 0：C-49；**v1.17 = M-3 `momentum_price_adjustment` 裁決落地（R1~R8），價格調整定為 share-unit 而非 total-return，新增 normative module `core/b0_share_unit_adjustment.py` 為唯一 producer，12 條必要測試落地：C-50**；**v1.18 = M-3 `stock_dividend_holder_multiplier_source` 裁決落地（R1~R6），官方交易所無償配股率為 canonical holder-multiplier 來源，`m = 1 + 每千股無償配股 / 1000`，pre-listing 事件判為 NOT_APPLICABLE 而非缺值，休市日排定除權日以 exact next observed session 正規化（非 ±N 日容忍），新增 normative module `core/b0_bonus_share_source.py` 與 sealed panel `data/b0/bonus_share_panel.parquet`，OPEN SPEC ITEMS 回到 0：C-51**；**v1.19 = 三項 pre-L2 收尾：Baseline Seal 本體改為 content-addressed 不可覆蓋歸檔（C-52）、開倉狀態日期接縫凍結為 period-1 邊界規則並雙綁兩個 hash（C-53）、C-50 補上專屬條文章節（僅文件整併，語義不變）**；**v1.20 = §6.1 全面改寫並新增 §6.1.1~§6.1.19 與 Annex CA-A：corporate action state transition 由「分類」升格為「狀態轉換」，凍結 owned / tradable / spendable 三分、五種 holder-affecting 事件的轉換表、receivable 到期語義、pending-exit 繼承、I-CA-01~I-CA-15 不變量與 F-CA-A/B/C 失敗分類法；`core.b0_corporate_actions` 取得 PortfolioState 轉換能力，`core.b0_state` 新增有到期日的 claim。舊 Baseline Seal 5fef4104 與 bound commit a0241f3d 標記 SUPERSEDED：C-54**；**v1.21 = sealed-input sufficiency closure：新增 §4.1a（輸入充分性與序列形狀）、擴充 M-2 L2 outcome 詞彙為 §6.1.14 已定義的兩個 exact names、monthly_revenue 13→18、財報與月營收改為 calendar-indexed 且缺期為顯式 None、新增 transitive dependency closure invariant。首次 sealed L2 run L2-2520c80aa980d681 以 RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE 記錄，provenance 永久保留；once-only observation 是否消耗依 M-3 `l2_reopening_after_run_invalid` 待裁，L2_opening 阻擋中：C-55**；**v1.22 = M-3 `l2_reopening_after_run_invalid` 裁決落地（R1~R5）：`RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE` 在**七項條件全部成立**時**不消耗** once-only effective observation（narrow rule，非「crash 一律不算」）；invalid run 永久保留於 provenance，不刪除、不覆蓋、不改標籤；M-2 新增 `ImplementationConformanceRepair` 與 DataRepair 並立，`assert_rerun_admissible` 依 outcome 分派 repair kind 而非誤分類；新增 `assert_reopening_admissible` 強制「新 Baseline Seal」與「具名新授權」；L2 provenance 位元組改由單一 primitive 以二進位 LF 寫出，修正 `record_opening` 依平台換行的缺陷；effective L2 observation count = 0，M-3 register 回到空：C-56**；**v1.23 = M-3 condition 2 語義裁決落地（R1~R6）：condition 2 的 `information` 未定義而留下兩種讀法，裁為 **strategy-dependent outcome information**；sealed opening economic state 的 deterministic restatement 不構成 strategy-outcome information；新增 R2 admissibility 八項、R3 negative boundary 七項、`verify_opening_state_restatement()` 對不可變 run artefact 的可執行驗證，condition 2 由 `attested` 升為 `attested_and_verified`，reopening gate 在 artefact 缺席或牴觸時一律失敗；四組 negative control 落地。既有 invalid run 之 `final_result.json` 與 `nav_series.json` 位元組完全未動：C-57**；**v1.24 = L2 run-scoped immutable provenance（R1~R6）：runner 原本只有一個全域輸出目錄，第二個 run 會 append 進第一個 run 的 `period_progress.jsonl` 並覆寫其 NAV 與 final result，**與第一個 run 成功或失敗無關**；新增 normative module `core/b0_l2_run_layout.py`（第 28 個），未來所有 run 一律寫入 `artifacts/l2_run/runs/<run_id>/`，目錄以 exclusive create 宣告、碰撞即在寫入任何位元組之前失敗；首次 invalid run 原地保留且四個 artefact 的 sha256 pin 進規範模組；所有 verifier / attestation / effective-observation / reopening gate 改以 run_id 綁定，`latest` 明文宣告為 non-canonical；新增跨 run 隔離測試，並同時對「invalid 前一個 run」與「一般已完成前一個 run」施測：C-58**；**v1.25 = L2 opener/runner protocol conformance repair（R1~R10）：正式 opening boundary 改為 `artifacts/l2_run/opening_claims/<baseline_seal>.json` 的排他建立（O_EXCL），非 run 目錄建立、亦非終局 registry 插入；`attempted_openings` 改由不可變 opening event 導出（legacy pinned + claims，依 run_id 去重），不再由終局 registry 列計算；新增 `execution_claim.json` 使同一 run 只能執行一次；runner 在第一個 period 寫入前驗證九項 opening provenance；run state 由不可變事件導出（OPENED / EXECUTION_CLAIMED / TERMINAL），無 mutable state 欄位；generic provenance writer 結構性地不可能成為第二個 run 目錄建立者；execution claim 存在但無 terminal result 之狀態顯式偵測並依 M-3 abort，不自創 rerun 規則：C-59**）
**凍結日:** 2026-08-17
**狀態:** `NORMATIVE — FROZEN`

---

## §0 效力、範圍與優先順序

### 0.1 這份文件是什麼

**本文件是 Frozen B0 的唯一規範性規格（sole normative specification）。**

B-01 ~ B-21、O-1、V-1 ~ V-6、W-1 ~ W-4 的各份 closure 文件**自本文件凍結之日起降級為 rationale / evidence / audit trail**。它們記錄「為什麼這樣裁決」與「當時看到什麼資料」，**不再定義 B0 是什麼**。

### 0.2 衝突時的優先順序（規範性）

```
Master Preregistration  >  closure prose  >  legacy code / comments
```

機械記錄於 `core/b0_master_prereg.py :: NORMATIVE_PRECEDENCE`。

### 0.3 本文件如何修改

**不得靜默覆蓋既有裁決。** 任何與既有 closure 相牴觸的條文，必須同時列入 **§11 Contradiction / Change Log**，寫明：被改的來源、原文、新條文、改動理由。**未列入 §11 的牴觸視為本文件的缺陷，不視為裁決變更。**

### 0.4 本文件不涵蓋的範圍

Frozen A（`l4b_execution.py`、`portfolio_simulator_lab.py`、`core/regime.py`、`core/backtest.py`、`bt_bundle.py`、`canonical_universe.py`、`tests/test_canonical_universe.py`）**不在本文件效力範圍內，且不得因本文件而被修改**。它是 audit trail，不是校準目標。

---

## §1 Evidence / Version Doctrine（規範性）

### 1.1 三層 epistemic status

| 層 | 名稱 | 證據來源 | 能證明 | **不能**證明 |
|---|---|---|---|---|
| **L1** | `Specification Valid` | 靜態：程式碼、不變量、PIT 依賴圖 | 規格自洽、零自由參數、不變量全綠 | 任何關於報酬的事 |
| **L2** | `Retrospectively Supported / Not Supported` | 141 月 sealed window，開封一次 | **可證偽** | **不可證實** |
| **L3** | `Prospectively Validated Edge` | 完整凍結後產生的新市場資料 | 真正 untouched evidence | —— |

### 1.2 L2 的證據力不對稱（支點條款）

> **L2 失敗是強證據；L2 成功是弱證據。**

該窗口每一個月都已被先前研究看過（H1–H5、high52 否決、TOP15 否決、overlay α 掃描、五維 11 arms、C3 過 Gate 1）。

**⇒ L2 的正式輸出永遠不得寫 `Validated` / `statistically proven` / `OOS edge confirmed` / `out-of-sample`。** 機械強制：`assert_l2_wording()`。

### 1.3 Frozen A / Frozen B0 分層

- **Frozen A** — 舊程式、舊資料、H1–H5 結果，保留為 audit trail。**不再修補、不作校準目標、不作勝負對手。**
- **Bridge Arms A0–A3** — 純歸因用途。**不得從中挑 winner，不得用其結果決定 B0 規格。**
- **Frozen B0** — 本文件。必須在看到 A0–A3 結果**之前**完整凍結。

### 1.4 No-Post-Hoc-Rescue（規範性）

> **L2 判定 `Not Supported` 之後，不得在同一窗口上調整規格重跑。**

任何開封後的規格變更 → 產生新版本（B1、B2…），且：
- 新版本**不得**以同一 141 月窗口作為 primary evidence（已被該版本的失敗結果污染）
- 新版本可將該窗口列為次要診斷，但**必須標註 post-hoc，非獨立證據**
- 新版本的 primary evidence **只能是 L3**

允許的例外唯二：**實作缺陷修復**、**資料修復**，且兩者都必須在**不看績效**的情況下獨立證明。詳見 §9.6。

### 1.5 **M-3 · No Specification-by-Code（本次凍結新增，規範性）**

> **本文件未定義的行為 = `UNSPECIFIED` → abort + 開 specification item。**
> **不得** resolve 為 developer 認為合理的預設值。

理由：目前最大的研究風險已不是因子選擇，而是 implementation 階段偷偷產生新自由度。一個「程式這樣寫比較方便」的決定，在數值上與一個未預註冊的參數沒有區別。

機械強制：
- `core/b0_master_prereg.py :: spec(key)` **刻意沒有 `default=` 參數**（有測試釘死簽名）
- 未定義的 key → `UnspecifiedBehaviour`
- `assert_specified(*keys)` 一次列出所有缺漏項
- 未定義的 pipeline stage、未定義的 L2 outcome、未定義的 repair scope 全部走同一條 abort 路徑

---

## §2 Canonical Data / PIT（規範性）

### 2.1 凍結窗口

```
Lookback L                    = 18 個月
綁定因子                       = revenue_accel（A 腿定義：近3月均 YoY − 前3月均 YoY）
資料邊界                       = monthly_revenue 真實公告日 2013-01
First eligible decision month  = 2013-01 + 18 = 2014-07
Retrospective sealed window    = 2014-07-31 .. 2026-03-31，141 個月
```

**解凍條件唯一：** 發現「已保留 feature 的 PIT dependency > 18」。**不得因績效修改。**

**該窗口不得稱為 untouched OOS / holdout / out-of-sample。** 不切 train/test：B0 在窗口內沒有需要 fitting 的參數，切分不產生新資訊，只會製造 untouched 的假象。

### 2.2 Publication semantics

- 月營收：讀**真實 `release_date`**，不得使用固定 lag 代理（舊 `REVENUE_LAG_DAYS = 10` 已 Remove）
- 財報：`financial_statements` 2005-12 起 100% 真實公告日
- 價格/估值：`price_valuation` 2004-01 起
- **任何以固定 lag 代替真實公告日的做法，在 B0 一律禁止。**

### 2.3 PIT 產業時間軸（規範性）

`industry_map.parquet` 是**靜態當期快照**，而 **1,203 檔（49.4%）至少換過一次 TSE 產業別**。用它回算歷史產業內估值 = 對約一半母體引入產業 look-ahead。

**B0 必須使用 PIT TSE 產業時間軸**（4,782 筆記錄，2,436 檔），產業指派為 point-in-time step function。

**92 檔當期欄與最新變更記錄不一致者：自最後一筆有日期記錄起，整段區間標記 `UNRESOLVED`。** 不用 current snapshot 回填、不假定舊分類永久有效。`UNRESOLVED` → 產業 = NA → Value = NA → 依 §4.1 complete-case 自然排除（窗口內中位每期排除 41 檔，佔 2.303%）。

**已揭露偏離：** 產業層級用 **TSE 產業**而非 TEJ 產業，因為變更歷程只涵蓋 TSE 產業與 TEJ 子產業，TEJ 產業層的 PIT 時間軸**在資料上不可重建**。

### 2.4 Corporate actions（W-1 ~ W-4，規範性）

**三態分類，逐事件：**

```
RECONSTRUCTIBLE       資料足夠，canonical handler 可算出我們的股數/現金變化
NOT_RECONSTRUCTIBLE   系統看到事件且知道自己重建不出來 —— 必須帶 reason
NOT_APPLICABLE        事件存在，但不改變「我們的」股數/現金/證券身分
```

**W-1** 缺資料 → 逐事件 `NOT_RECONSTRUCTIBLE`。**不插值、不設缺失率門檻。** 機械強制：`MISSING_DATA_RATE_THRESHOLD is None`、`INTERPOLATION_ALLOWED is False`。
**W-2** `credit_date == ex_right_date` 為合法 zero-day receivable；只有 `credit < ex` 才 fail。
**W-3** 所有改變持股/現金/身分的事件納入 canonical ledger，每類型有專屬 handler。未登記 handler 即 abort。
**W-4** `CASH_CAPITAL_INCREASE_SUBSCRIBE = False`，**永不主動認購，不可由策略狀態選擇**。

**Handler 覆蓋（6/6）：** stock_dividend、capital_reduction、merger、share_conversion、par_value_change、cash_capital_increase。
**判定為 NOT_APPLICABLE（發行人總股數變動，稀釋已在市價）：** 可轉債轉換、庫藏股註銷、員工分紅、受讓、其它。

**兩條 abort 規則（規範性）：**

1. **暴露閘** —— B0 實際持有某證券且持有區間涵蓋某 `NOT_RECONSTRUCTIBLE` 事件日 → **abort，不得產生 NAV**。存在但未持有不 abort。
2. **價格缺口守衛（O-B）** —— 見 §2.6。

守衛 2 是必要的而非補充：合併/股份轉換**只記在存續方**，語料 33 欄中不存在任何交易對手/換股比例欄位，因此持有「消滅方」時正向永遠對不上。最危險的失效不是「算錯換股比例」，而是**消失的持股被當成 price missing → zero/drop → NAV 靜默錯掉**。

**O-C · 無除權旗標的盈餘/公積增資（312 件，凍結）：** B0 **不為它們另建推導模型，也不以月底登記戳記猜除權日**。它們維持 `NOT_RECONSTRUCTIBLE`，暴露時 fail-loud。**final seal 不要求把所有歷史事件都變成 reconstructible。** 若未來取得 authoritative event source，走 §9.5 的 data repair protocol。

### 2.6 O-B · PIT 價格可觀測性（凍結）

**被否決的設計：** global `last_price_date` lookup（「這檔股票在資料庫裡最後一個交易日是哪天？」）。站在 2019-05-01 做 replay 時，那個問題只能用 2019-05-01 之後的資料回答 —— **look-ahead 編碼在名字本身**，因此該函式被移除而非修補。

**B0 需要的不是永久性，而是 `as_of` 當下的可解釋性：**

> 站在 `as_of`，持倉中是否存在一段「截至 `as_of` 為止的已知資訊無法解釋」的價格缺失？

**「永久消失」明文不是本規格的概念。** 一檔再也不交易的證券，在第一個缺價日看起來與明天就復牌的證券完全相同 —— 只有未來資料能分開兩者。B0 因此**永不判定「已永久消失」**，只判定「截至今日無法解釋」，而該判定會隨更多 session 被觀測到而改變。

**四個 PIT observable，全部以 `as_of` 為界：**

```
price_observed_through(t)     最後一個有觀測價格的 session，<= t
expected_trading_sessions(t)  截至 t 已知的交易日曆所預期的 session
known_security_status(t)      listed / suspended / delisted / halted，申報日 <= t
known_corporate_actions(t)    effective date <= t 的事件
```

**四態分類：**

| 分類 | 條件 | 可 mark |
|---|---|---|
| `CURRENT` | 最近一個預期 session 有價 | ✅ |
| `EXPLAINED_SUSPENSION` | 已知非交易狀態（日期 <= t） | ✅ **stale mark，必須打旗標並計數** |
| `EXPLAINED_CORPORATE_ACTION` | 已知 corporate action（生效日 <= t） | ✅ **stale mark，必須打旗標並計數** |
| `UNEXPLAINED_GAP` | 其餘 | ❌ **abort** |

**零自由參數：不存在「容忍 N 個 session」的旋鈕。** 任一預期 session 無價且無已知解釋 → **在觀測到的那一天 abort**。容忍度就是 W-1 已拒絕的那種門檻，而且會把一檔消失的持股以舊價 mark 上 N 天還稱之為「已解釋」。機械強制：`STALE_MARK_SESSION_TOLERANCE is None`。

**stale mark 是被迫而非被選：** 已知停牌的部位不可交易、無市場價格，最後觀測價是**唯一 PIT 可得的數字**（沒有窗口長度可選）。但它**必須打旗標、計 session 數並列入 §9.7 必報項**。

**從未有觀測價的持倉一律 `UNEXPLAINED_GAP`** —— 任何解釋都無法補上一個從未被觀測到的數字。

**`listed` 狀態不解釋任何缺口**，否則預設值會變成逃生門。

**機械強制 look-ahead：** `PitPriceObservation` 對每個帶日期的欄位（含交易日曆）檢查 `<= as_of`，超過即 `LookAheadError`。**交易日曆是最容易夾帶未來資訊的入口**，因此一併鎖住。

### 2.7 O-E · 市場狀態來源（凍結）

O-B 凍結了「怎麼判斷」，O-E 凍結「日曆與狀態從哪裡來，以及它們自身是否 PIT 正確」。**若狀態表本身是當期快照（如 `industry_map` 那樣，49.4% 股票換過產業），守衛會在輸入層被繞過，它自己所有的 PIT 檢查都失效。**

**1 · 交易日曆** —— 僅使用**已觀測 session**（`observed_sessions_only`）。「指數在 d 日有交易」在 d 日即可知，因此對 O-B 的 `<= as_of` 查詢是**建構上 PIT-safe**。**明文不使用預先公布的休市日程表** —— 那會讓站在 t 的 replay 斷言 t 之後的 session。

**機械強制：完整日曆不可達。** `TradingCalendar` 只公開 `sessions_through(as_of)`，沒有 `.sessions`。`as_of` 超出涵蓋範圍即 abort，不得靜默回傳全部。

**2 · 證券狀態來源** —— 必須帶歷史 effective date。**只知道最新狀態的來源標記 `NOT_PIT_SAFE`，不得進入 B0，且不予修補** —— 「把今天的狀態套到歷史」正是 `industry_map` 的缺陷本身。

**3 · 狀態語義（四態）：** `listed` / `suspended` / `delisted` / `unknown`。

> **`unknown` 不是 `listed`。** 無狀態紀錄者，`unknown` 是**紀錄的缺席**而非一種申報狀態（`StatusRecord` 拒絕以 `unknown` 建構）。**一旦出現價格缺口，缺席的紀錄什麼都不解釋 → abort。**

**4 · Provenance** —— 每個來源必須申報 importer version、schema hash、content hash、涵蓋範圍，並轉為 B-21 `DatasetProvenance`。**回傳未版本化狀態的 runtime API 不是合格來源。**

**O-E-1 · availability semantics（規範性）：**

> **一個狀態只能解釋「在它公開可得之後才開始」的缺價 session。**

```
explains_session(s)  ⟺  available_from < s  AND  effective_from <= s
```

**`effective_from <= s` 不足夠。** 盤後才申報的停牌仍然帶當天的日期，用它解釋當天的缺價是**穿著正確日期外衣的 look-ahead**。因此規則是**嚴格早於**。

`available_from` **無預設值** —— 把它預設為 `effective_from` 等於默默斷言了正需要被證明的那件事。

**已登錄的來源與 availability convention：**

| 來源 | 內容 | convention |
|---|---|---|
| `b0_trading_calendar` | 5,565 個已觀測 session，2004-01-02 .. 2026-08-17 | session 於當日可知 |
| `b0_security_status` | 3,700 筆 / 1,043 檔，來自 `暫停交易`（1,946 列，四欄 100% 非空，歷史 effective-date 表非快照） | `available_from = 年月日`，配合 O-E-1 只解釋**嚴格之後**的 session |

**該 convention 的實測後果（非推論）：** 1,940 筆可用列中 **1,529（78.8%）在 `年月日` 當天仍有價格**，嚴格規則在那裡零成本；其餘 411 筆以 `下市`/`違規` 為主，其首個缺價 session 就是 `年月日` 本身，**執行會正確 abort** —— 那是 §2.4 的不可重建身分轉換，不是應該被解釋掉的缺口。

### 2.8 ✅ D-1 · 價格母體存活者偏誤（**已於 v1.9 由重新匯出關閉**）

> **狀態：`price_universe_survivorship = SATISFIED`（2026-08-18）。** canonical price source 為 `b0_price_universe_20260817`，content sha `2646356f…d63549`，2,306 檔、2004-01-02 .. 2026-08-17。舊 corpus `aeda65b9…ea49c1` 維持 quarantined。
> 以下保留原始缺陷描述作為 audit trail；修復證據見 §2.8.3。

**逐年價格 export 的實測流失（純計數，非績效）：**

```
2012:14  2013:11  2014:16  2015:14  2016:20  2017:18     ← 正常汰換,無一交易到年末
2018:110  ← 其中 90 檔一路交易到 2018 最後一個 session
2019:0  2020:0  2021:0  2022:0  2023:0  2024:0           ← 六年零下市
```

**六年零下市不是市場事實，是一個母體過濾器。** 而在 export 當下套用的過濾器**知道哪些證券活了下來** —— 那是價格來源所能攜帶的最強形式的 look-ahead。

**獨立證據：那 90 檔中有 74 檔可證明在 2018 之後仍存在** —— 52 檔帶有 2019–2025 的下市型停牌（例如 `1701` 於 **2024-08-21** 併入控股公司下市，但其價格序列停在 2018-12-28，**遺漏約 5.6 年的真實交易**），57 檔在 `配股相關` 語料中有 2018 之後的事件（最晚 `3426` 至 2026-08-11）。對照組：300 檔仍在報價的證券中有 184 檔有 2018 後事件 —— **語料本身確實涵蓋 2018 後**，缺的只有這 90 檔。

**⇒ 2019+ 的 vintage 只含 export 當下仍上市的證券，使投資母體在 141 個窗口月中的 87 個月（62%）受存活者偏誤污染。**

**影響範圍：** 逐期 complete-case 母體數、eligibility 淘汰組成、**階梯第 ① 列等權母體基準**、以及任何回溯結果 —— **全部向上偏誤**，因為下市股通常表現最差。

**不得由存活者反推缺失名單。** 唯一補救是**重新匯出 2019–2026 價格並納入下市證券**，做法與 `配股相關` export 已經做到的一致。

**機械強制：** `BlockingDataRequirement(key="price_universe_survivorship")`，阻擋 `S-3`、`final_provenance_seal`、`L2_opening`。

#### 2.8.1 驗證方式（v1.8 強化，判準只增不減）

**獨立參照：** `基本資料/公司資料.xlsx` 帶 `TSE上市日` / `OTC上市日` / `下市日期`，可在**完全不讀價格檔**的情況下回答「哪些證券在年度 Y 曾上市」。

> **⚠ 該檔的 `上市別` 在下市時會被改寫**（90 檔全部變成 `UNPUB`/`PUB`），因此範圍**必須**取自歷史上市日欄位，不得取自當期標籤。這與 `industry_map` 是同一類缺陷，也是它**只能稽核、永不可作為 B0 runtime 來源**的理由（O-E 下 `is_current_snapshot=True` → `NOT_PIT_SAFE`）。

**兩個 gate，皆為 structural impossibility，無任何數量門檻：**

| Gate | 條件 | 為什麼與規模無關 |
|---|---|---|
| **C1** | 某年度獨立參照記錄有下市，而 corpus **完全沒有任何證券流出** | 證券離開了交易所，corpus 說沒有。**一年即矛盾**，多寡不影響 |
| **C2** | 某日 **≥2** 檔價格序列永久終止，而參照在該日**沒有任何下市** | 真實離場不會同步；export 邊界會 |

**規模（`unexplained_missing_though_listed`）只報告不設閘** —— 把它變成 gate 需要選一個「多少缺失可以接受」的數字，而那個數字沒有可辯護的來源。

**判準只增不減：** 原本的 source-only 驗證器 `verify_price_universe_churn()`（零流失年份、交易到年末卻消失）**完整保留為 backstop**，且新舊必須同時通過。本次沒有放寬任何條件。

**實測（本 corpus）：** 控制組 2012–2017 觀測流出 14/11/16/14/20/18 vs 參照預期 14/13/10/11/23/17 —— 真實汰換；2019–2025 觀測流出**全為 0**，參照預期 8–18。C1 於 2019–2025 全數觸發，C2 於 `2018-12-28`(90)、`2018-09-17`(6) 觸發。

#### 2.8.2 D1-6 · 來源可達性

```
PriceSourceContract.includes_delisted == False          → abort
content_sha256 ∈ quarantined                            → abort
非 synthetic 的 retrospective replay 未宣告 price_source → abort
```

**Quarantine 依 content hash 而非路徑** —— 改名或複製一份受污染的匯出不得使其洗白。受污染 corpus 的指紋 `aeda65b9…ea49c1` 已登錄。`TEJ_RUNTIME_OVERLAY_DIR` 仍在 B-19 `OVERRIDE_SYMBOLS` 且 `B0_REGISTERED_OVERRIDES = {}`，堵住由 overlay 重新引入的路徑。

**非 synthetic 的 retrospective replay 必須宣告 `price_source`**，否則 abort —— 未具名的來源無法被證明不是那份受污染的。

#### 2.8.3 修復與驗收（v1.9）

**Canonical source（vintage boundary，非 patch）：**

```
<= 2018   既有逐年匯出（從來不是缺陷所在；2012-2017 對照參照為正常汰換）
>= 2019   個股股價、本益比2004-20260817 的兩個 zip，整批取代
```

**⚠ 明文不是 patch：** 2019+ 整個時代被**全量取代**並從頭重新驗證，過程中未查閱任何由舊 corpus 導出的缺失名單。

| 驗收項 | 舊 corpus | 新 canonical source |
|---|---|---|
| C1 零流出年份 | **FAIL** 2019–2025 七年 | **PASS** 流出 16/17/15/17/8/11/7（參照預期 15/18/15/17/8/10/8） |
| C2 無法解釋的終止群聚 | **FAIL** `2018-12-28` n=90、unexplained=54 | **PASS** 所有群聚 unexplained=0 |
| `2018-12-28` 群聚 | 存在 | **消失** |
| source-only backstop | **FAIL** 零流出年份 | **PASS** |
| security-level 無法解釋的提前終止 | 56 | **2**（`3291` 2016、`6159` 2009，皆 2019 前、間隔 10–16 天） |
| 每年 missing | 2019 年 92（5.27%） | 0–2（≤0.11%） |

**已知案例：** 參照下市日 ≥2019 者 98 檔，**98/98** 的價格序列延續到其實際離場（`1258` 2023-06-08→下市 06-09、`1701` 2024-08-30→下市 09-02、`1333` 2020-04-06 停牌→11-17 下市）。

> **通過條件不是「90 檔全部回來」** —— 該群聚只作 regression evidence。判定完全由 C1/C2/backstop 三者對資料計算得出。

### 2.5 股利處理（V-1a / V-1b，規範性）

**現金股利 —— receivable accounting：**

```
ex-date        : cash_dividend_receivable += shares × 每股現金股利
                 tradable_cash 不變
股息發放日      : cash += receivable ; receivable = 0
NAV            : 必須含 receivable
```

**⚠ 這不只是精確度改良，是補上一個已凍結規則的漏洞。** 若在 ex-date 就把股利記入可用現金，B0 就能用尚未收到的錢建倉 —— 那是 §6.4 no-leverage 規則的另一個破口，只是來源從賣出價金換成股利。

**股票股利 —— receivable → tradable shares：** ex-right 建 receivable；`max(股票股利上市日, 發放日)` 才轉 tradable shares；總 cost basis 不增加；receivable 入帳前不得賣出；NAV 須含 receivable。缺可交易日者依 §2.4 W-1 處理。

**配股率單位（由資料判定，非假設）：** `配股率 % = 新股數 ÷ 除權前股數 × 100`（中位比值 0.9992）。實作**直接用絕對股數**，配股率僅作交叉核對。**面額假設不需要。**

**基準股息：** 0050 與等權母體亦須含息，且與策略採**同一**股息處理。

---

## §3 Canonical Features（規範性）

### 3.1 Feature graph（凍結）

| Concept | 成員 |
|---|---|
| **Quality** | `roe`、`net_margin`、`gross_margin`、`debt_to_asset`、`current_ratio` |
| **Growth** | `revenue_yoy`、`revenue_accel`、`eps_growth` |
| **Value** | `value_ind_pct_b`、`PEG` |
| **Momentum** | 12-1 price momentum |

**計分方式（規範性）：** 每個成員為**連續橫斷面百分位**；concept 內等權；concept 間等權。

**百分位慣例（C-35，v1.5）：平手取平均名次（average rank）。**

```
相同 raw feature value → 必須得到相同 percentile
結果不得依賴 row order
```

**不提供 ordinal 選項。** ordinal 必須用某個東西打破平手，而可用的只有 row order 或 stock_id：前者使輸出隨 adapter 而變（直接擊穿 B-20 bit-exact parity），後者會把**組合層的 tie-break（C-33）回流到 feature 計分**，讓一檔證券因為代號小而獲得 alpha。

**機械強制：** `percentile_rank` 依 **value 分組**而非依 `(value, stock_id)` 排序 —— 兩者在數值上等價，但後者會使識別碼成為計算的一部分。

```
SelectionScore = mean(Quality, Growth, Value, Momentum)
```

**人工切點 = 0。Selection 層自由參數 = 0。**

### 3.2 Value 度量（Ruling B，凍結）

```
value_ind_pct_b = 當期 PIT TSE 產業內 B/M 橫斷面百分位（越高越便宜）
  B/M = 1 / PBR_TSE
  · 無 expanding self-history 窗（移除 path dependence）
  · 無 MIN_PCT_SAMPLES 樣本門檻
  · 無 2019 anchor
  · 分組最小 2 檔（rank 有定義的數學下限，非調校值）
自由參數：0
```

**選 B/M 而非 PE 的兩個獨立理由：**(1) standard-definition-first —— book-to-market 是 Fama-French HML 的 canonical value 定義；(2) 涵蓋率 —— PE 的缺口來自虧損公司（TEJ 對非正值回報 NULL），**缺口隨景氣變動**，在 complete-case 之下會造成條件性母體變動。窗口內 Value 涵蓋率由 72.6% 升至 91.9%（+19.3pp）。

**Lineage 認證等級：`LINEAGE_CONFIRMED_IN_AGGREGATE`。** 12 個獨立年度的 `(PBR/PER) / ROE_ttm` 中位比值落在 0.936–1.091，證明 `PER_TSE` 與 `PBR_TSE` 共用同一市值與股數基礎，故 `1/PBR_TSE` 即 canonical `BE/ME`。

> **必須隨結論帶走的限制：** 逐列離散度大（p10 ≈ 0.67–0.86、p90 ≈ 1.31–2.01），**只認證總體恆等，不認證逐列**。逐列認證需要 TEJ 對 `PER_TSE`/`PBR_TSE` 的定義文件 —— 與 TDCC lag 同屬本專案已知取不到的廠商文件依賴。**不得以任何非權威敘述頂替。**

### 3.3 非 Selection 層（不進 SelectionScore）

| 層 | 內容 | 角色 |
|---|---|---|
| **Confirmation** | C1 + Q5 合一，連續 state | **不進排名、不 veto、不 sizing**；語義固定為 **net**（O-1），gross 為 diagnostic-only 且不可 runtime 選擇 |
| **Timing** | T1–T8 去重、M8、M10、C7 | 僅報告 |
| **Risk / Eligibility** | F10 hard filters、V5、Anti-chase（M9+Q4+M11，連續 state，**不 hard exclude**） | 見 §4 |

### 3.5 成員方向與公式（v1.3 補回，規範性）

> **本節全部為 master omission correction。** 語義早在 B-09 各 Phase 或其援引的標準定義中確定，只是凍結時未抄進本文件。**不是新的策略裁決，不新增任何自由參數。**

**方向（C-19）—— 綁定於 feature 定義，不得由呼叫端選擇：**

| 成員 | 方向 | | 成員 | 方向 |
|---|---|---|---|---|
| `roe` | 越高越好 | | `revenue_yoy` | 越高越好 |
| `net_margin` | 越高越好 | | `revenue_accel` | 越高越好 |
| `gross_margin` | 越高越好 | | `eps_growth` | 越高越好 |
| `debt_to_asset` | **越低越好** | | `value_ind_pct_b`（B/M） | 越高越好 |
| `current_ratio` | 越高越好 | | `PEG` | **越低越好** |
| | | | 12-1 momentum | 越高越好 |

**機械強制：** 方向寫在 `FeatureDefinition.orientation`，計分入口 `feature_percentile()` **不接受方向參數**；`b0_decision` 被禁止呼叫帶 `ascending` 的底層 `percentile_rank`（AST 檢查）。方向若可由呼叫端指定，就是一個 runtime 自由度，而**方向錯誤不產生雜訊，是把整個 concept 反轉**，SelectionScore 仍為格式完好的數字。

**Quality — TTM 獲利三項（C-21）：**

```
roe    = ( Σ_{k=0..3} net_income_{q−k} ) / equity_q × 100        單位：百分點
         q      = 公告日 ≤ decision date 的最新一季（§2.2）
         分子   = 該季往前四季的淨利「總和」
         分母   = 同一季 q 的「期末權益」（非平均權益、非任何更晚的報表）
         equity_q ≤ 0 → NA

margin = ( Σ_{k=0..3} profit_{q−k} ) / ( Σ_{k=0..3} revenue_{q−k} ) × 100
         net_margin 取稅後淨利、gross_margin 取毛利
         Σrevenue ≤ 0 → NA
```

- **TTM 而非單季**：B-09 Phase 3 §5 將三者列於「Quality TTM」（回看 13）。legacy producer 實作單季並自注「近似 ROE(單季)」，**兩者衝突時依 §0.2 由 closure 勝**；此衝突已列入 §11 C-21，不予淡化。
- **期末權益而非平均權益**：closure 未指定，由 lineage 決定（`net_inc / equity`）。平均權益需要第二個報表日，其 PIT 可得性是 closure 從未開啟的另一個問題。
- **`equity ≤ 0 → NA`**：負分母會在數值完好的情況下翻轉符號 —— 帳面權益為負的獲利公司會被排成極度不獲利。與 C-17 對 PEG 的處置同一原則：**正值域是該度量的一部分，不是加在它上面的過濾器**。
- **margin 為「總和除以總和」，不是四個季比率的平均**。均值會讓淡季與旺季等權，且沒有人把那個統計量叫做 TTM margin。此為 §3.2 已援引的 standard-definition-first。
- **四季必須連續且齊備**，缺一季即 NA —— 跳過缺報的季會拿三季總和去比四季總和。

**Quality — 當期資產負債表兩項（C-22）：**

```
debt_to_asset = total_liabilities_q / total_assets_q × 100      分母 ≤ 0 → NA
current_ratio = current_assets_q / current_liabilities_q × 100  分母 ≤ 0 → NA
```

B-09 Phase 3 §5 將兩者單列為「Quality 當期(負債比/流動比)」，回看 4 —— **是時點存量比率，不是 TTM 流量**。「當期」指哪一份報表已由 §2.2 凍結：**公告日 ≤ decision date 的最新一份**，不得以固定 lag 代理。單位為百分點（`150.0` 表示 1.5 倍），沿用 legacy 量尺。

**`revenue_yoy`（C-23）：**

```
revenue_yoy_m = (revenue_m − revenue_{m−12}) / |revenue_{m−12}| × 100
```

**單月 YoY 不是偏好，是回看期唯一容許的讀法：** B-09 Phase 3 §5 給該成員 13 個月，而 `13 = 1 + 12`。三月均 YoY 需要 15 個月。（以三月均構成的成員是 `revenue_accel`，§2.1 因此給它 18。）單位與分母形式沿用 C-18，使 `revenue_accel`（兩個 YoY 均值之差）作用在同一量尺上。

**12-1 Momentum（C-24）：**

```
momentum = (P_{t−1} / P_{t−13} − 1) × 100
```

端點由回看 13 決定：自 t 取到 `P_{t−13}` 恰好需要 13 個月。

**價格報酬，非含息報酬。** §3.1 字面為 "12-1 **price** momentum"，且 Jegadeesh-Titman 的標準構造是價格相對量。**這也是 §2.5 含息要求唯一不延伸到的地方** —— 該條管的是 NAV 與基準構造（在那裡排除股利會低估兩者），而 momentum 是**排序訊號**，其凍結名稱已決定它是哪一種相對量。

**輸入價格序列必須已依 §2.4 調整股數事件** —— 未調整的序列會把一次分割顯示為 −50% 的動能讀數。調整不是本公式的選擇，是 corporate-action stage 已產生的輸入性質。

**`eps_growth`（C-18）：**

```
eps_growth_t = (EPS_t − EPS_{t−4}) / |EPS_{t−4}| × 100      單位：百分點
             = NA   若季數不足、EPS_{t−4} 缺值或為 0
```

- **horizon** 來自 B-09 Phase 3「季 YoY」；
- **分母取絕對值與 ×100** 來自逐行 lineage：`eps_cagr` 從來不是 CAGR，它是 `fundamental_data["eps_growth"]`，由 `core/data_provider.py::_yoy_growth` 產生，回傳 `(latest − prior) / abs(prior) × 100.0`；
- **以季序 t−4 取基期**，不沿用 legacy 的「距 365 天最近且在 ±60 天內」比對 —— **那個 ±60 天是容差參數**，落在 Selection 路徑上，與 §9.1 S-1 相斥，而 B0 有季別索引不需要它；
- **明文不沿用** legacy 的 `if eps_growth is None: eps_growth = net_income_growth`（`data_provider.py:656-657`）。**以另一條序列替代缺值就是插補，§4.1 已明文禁止**，該列依 complete-case 整筆排除。保留它同時會讓兩個不同的量共用一個名字 —— 正是 §11 C-8。

**`PEG`（C-17）：**

```
PEG = PER_TSE / eps_growth（百分點）
    定義域：PER_TSE > 0 且 eps_growth > 0
    否則 PEG = NA → 依 §4.1 complete-case 整筆排除
```

**正值定義域是 PEG 的語義，不是人為門檻。** 允許負值會讓 `PE = −10、growth = −20%` 得到 `PEG = +0.5` —— 一個排序上看起來「便宜又成長」、實際描述虧損且獲利萎縮的公司。**帶號 PEG 不是更嚴格的 PEG，是在某一象限意義相反的另一個量。**

**單位陷阱：** `eps_growth` 為百分點，故 PEG 直接相除。若供料方誤傳小數（0.20 代表 20%），PEG 會放大 100 倍。

**⚠ 隨此定義帶走的揭露：** PEG 會造成隨景氣變動的條件性母體缺失（空頭年更多公司成長為負而整列離開）。**§9.7 必報 PEG 涵蓋率**。它只被報告，**不得據以調整規格**。

### 3.4 已 Remove（不得復活）

`asset_turnover`、`rev_cagr`、`cum_yoy`、`streak`、V3/V4 估值定義、估值混比 0.85/0.15、expanding PE 分位、`MIN_PCT_SAMPLES`、`PE_HISTORY_START`、2019 anchor、L2 value trap 交互排除、`DATA_START_CUTOFF`、上市滿一年、`FUSION_PCT` 雙腿 80/80 交集、`TOP_N` 濃縮開關。

---

## §4 Eligibility（規範性）

### 4.1 Complete-case（B-15）

**required features 必須全部 PIT-available。** 任一缺失 → 該股該期整筆排除。**不得插補、不得部分計分。**

### 4.1a Input sufficiency and sequence shape（v1.21，規範性）

> **Status: NORMATIVE.** 本節由首次 sealed L2 run 的失敗導出。
> 該 run 執行完整 141 期、每一期 complete-case 排除 **100%** 母體，
> 原因是 `revenue_accel` 需要 18 個月的月營收而 materializer 供給 13，
> 而**沒有任何機制比對過這兩個數字**。141/141 可重現的 state hash 無法發現它 ——
> 相同的輸入不論長度是否足夠，都會 hash 成相同的位元組。

#### §4.1a-R1 · 消費者專屬的最小需求

每一個 §4.1 complete-case 成員都有 minimum input lookback。
canonical producer 供給的序列長度 **MUST ≥** 該成員的 minimum，
且該需求 **MUST 由凍結成員自身機械推導**，不得在 producer 中以 literal 重述。

```
monthly_revenue      required 18   supplied 18   margin 0   ← revenue_accel 決定
month_end_prices     required 14   supplied 14   margin 0   ← momentum_12_1 決定
quarterly sequences  required  5   supplied  8   margin 3   ← eps_growth 決定
```

**margin = 0 必須是明文決定，不得是巧合。** 已具名宣告於
`core.b0_features.INTENTIONAL_ZERO_MARGIN`。
**不得**為了「感覺安全」而加寬供給 —— 加寬只會把 dependency contract 模糊掉，
並讓未來公式加深時無法紅燈。

`lookback_L_months = 18` 的意義**明確**為：
**B0 最深的 monthly dependency horizon，由 `revenue_accel` 決定。**
它**不是**「所有 monthly array 都必須長 18」。

#### §4.1a-R2 · 序列形狀（calendar-indexed）

凍結成員以**位置**讀取序列（`series[-1]` vs `series[-13]`、`series[-1]` vs `series[-5]`），
因此輸入 **MUST** 為連續日曆索引序列：

```
財報季度序列   consecutive fiscal quarters
月營收序列     consecutive calendar months
月底價格序列   consecutive calendar months
缺期           explicit None
壓縮缺期       FORBIDDEN
```

壓縮缺期會使比較基期**靜默錯位**：實測 period 1，1,730 檔中 **177 檔（10.23%）**
最後 8 個已發布季度非日曆連續，其 `series[-5]` 並非四季前，
`eps_growth`／`PEG` 因此比錯基期、TTM 加總跨了五個日曆季。
月營收目前實測 0/1,647 受影響 —— 此處為**不變量而非修正**，
在最便宜的時點凍結，使 `revenue_yoy` 的 `t-12` 永遠真的是去年同月、
`revenue_accel` 的 recent 3M / prior 3M 永遠是固定日曆月份，
且未來換資料來源時不會因剛好少一個月而 silent shift。

**修 producer / input shape，不得修改凍結成員的財務定義。**

#### §4.1a-R3 · Dependency closure invariant

`required_feature_keys()` 回傳的**每一個**成員都必須參與遞移 lookback 閉包檢查；
新增凍結成員 **MUST** 自動納入。
任何 canonical producer 供給少於其凍結 consumer 需求者，
**seal MUST fail**。供給不足屬 §6.1.14 **F-CA-A** pre-open baseline defect，
必須在 Baseline Seal 前擋下，不得於 sealed run 期間發現後修補。

#### §4.1a-R4 · complete-case 可達性

若某一期**無任何**證券通過 §4.1 complete-case，該期不具評估意義。
此為 conformance failure 而非有效的 run。僅斷言**可達性** ——
不涉及數量、名單或分數。

---

### 4.2 Dynamic investability

```
ADV_floor(t) = port_value(t) × w_target ÷ X_buy = 5 × port_value(t)
Eligibility  : ADV20_i ≥ ADV_floor(t)
```

**規範措辭：** 每檔完整 target position 必須能在**一個交易日內**、以不超過 ADV20 的 1% participation 建立。

> **⚠ 永久記錄：`ADV_floor` 是每期衍生量，不是凍結參數。** NT$10,000,000 僅是 `port_value = C_ref` 時的派生值；**在數值上與已退休的 `--adv-floor=1e7` 相同純屬巧合，兩者來源無關**。程式碼**不得**重用 `--adv-floor` 識別名。任何文件**不得**將 B0 門檻描述為「沿用 1e7」。

**Eligibility gate 與 order cap 是兩個不同角色，必須是兩段獨立程式碼：**

| 層 | 時點 | 對象 | 語義 |
|---|---|---|---|
| Eligibility gate | 建倉決策前 | `ADV20_i ≥ ADV_floor(t)` | 這檔**有沒有能力承載**標準 5% 部位 |
| Order cap | 送單時 | `單日買/賣金額 ≤ ADV20_i × 1%` | 這張**實際訂單**是否超量 |

### 4.3 Unresolved states

- PIT 產業 `UNRESOLVED` → Value = NA → complete-case 排除（§2.3）
- Corporate action `NOT_RECONSTRUCTIBLE` **不影響 eligibility**；它在**持有時**觸發 abort（§2.4），不是排除規則

### 4.4 Risk eligibility（C-20，v1.3 補回，部分凍結）

solvency / 資料品質 hard filters。**Anti-chase 為連續 state，不得 hard exclude。**

**處置方式（規範性）：B-09 Phase 1 對 F10 的裁決是 `Relocate → Risk / Eligibility`，不是 Remove。** 因此 B0 **沿用既有 predicate，只改它所在層級**，不重新尋找「更好的」門檻。**這些是 frozen inherited constants，不是 runtime tunable parameters** —— 見 §9.1 S-1 的措辭。

**已凍結（唯一無條件的一腿）：**

```
net_margin < −10（百分點） → ineligible
```

**⚠ 逐行讀 legacy predicate 後的更正：F10 不是四個門檻。** `core/fundamentals.py:262-305` 實際為**六個常數 + 一個產業別豁免 + 一腿從未觸發**：

| legacy 條件 | 實況 |
|---|---|
| `net_margin < −10` | 無條件 → **已凍結** |
| `current_ratio < 50` | 失敗，**除非 `is_financial`** |
| `debt_to_asset > 85` | **條件式**：僅當 (`current_ratio < 100` 或 `net_margin < 0`) 或 `debt > 92` 才失敗；`is_financial` 一律豁免 |
| `cash_quality < 0.5` | **全庫無任何 producer 寫入 `cash_quality`**，該腿從未觸發 |

**v1.5 的處置（C-29 / C-30 / C-31）：**

| legacy 腿 | B0 的處置 |
|---|---|
| `net_margin < −10` | **保留**（C-20，無條件） |
| `is_financial` 豁免 | **移除**（C-29）—— `RISK_FINANCIAL_EXEMPTION = False`，B0 不新增任何 `is_financial` 特例路徑 |
| `debt_to_asset > 85` 條件樹（含 92 / 100 / 0） | **移除**（C-30）—— `debt_to_asset` **只保留為 Quality 中 lower-is-better 的連續 Selection feature**，不另作 debt hard exclusion |
| `cash_quality < 0.5` | **移除**（C-31）—— 且**不得 alias、不得改掛 `ocf_to_net_income`** |
| `current_ratio < 50` | **移除**（C-36）—— **且明文不因 C-29 移除豁免而升為全產業無條件規則** |

**C-29 的第二個理由（非僅裁決）：** 產業別豁免需要 decision date 當下的產業歸屬，而 §2.3 已證 `industry_map` 是當期快照且 49.4% 的股票換過 TSE 產業。**以今日產業表解析豁免，等於把 look-ahead 放進 eligibility 閘。** 機械強制：`assert_no_sector_exemption()`。

**C-31 為何不接受 alias：** `ocf_to_net_income` 是**另一個量** —— 淨利為 0 時無定義、為負時整個比值變號，`< 0.5` 在該區間語義相反。採用它是**定義一條新的 B0 filter，不是 relocate 舊的**。機械強制：`assert_no_cash_quality_alias()`。

**C-36 的明文否定（規範性）：不得把「移除豁免」重新詮釋為「該規則變成全產業無條件適用」。** 移除一個 carve-out 與保留它所 carve out 的規則是兩個不同的決定，本規格只做了第一個。`current_ratio` **只保留為 Quality 中 higher-is-better 的連續 Selection feature**。

**⇒ B0 最終的基本面 hard risk filter 只有一條：**

```
net_margin < −10（百分點,TTM 定義見 §3.5）  →  ineligible
```

legacy 的負債條件樹、cash_quality、current-ratio 下限、金融業豁免**全部移除**。

> **隨此條帶走的後果（揭露，非歧義）：** 該門檻的**輸入定義已由 C-21 改為 TTM**。legacy 的 `−10` 作用在單季淨利率上，B0 的作用在四季彙總淨利率上 —— 因為 B0 只有一個 `net_margin`（§3.5）。這是規格唯一決定的讀法，但**單季與 TTM 會剔除到不同的公司**，故明文記錄。

**兩個 balance-sheet 比率自此改由連續處理承接：** 高槓桿或低流動比的標的在 Quality 百分位上受懲罰，而非被切點剔除 —— 與 §3.1 把人工切點降為 0 的方向一致。

**機械強制：** `RISK_LAYER_COMPLETE = True`；`assert_no_removed_legacy_leg()` 攔截任何一條被移除的腿以 runtime filter 形式復活；`assert_no_sector_exemption()`、`assert_no_cash_quality_alias()` 各自守住 C-29 / C-31。

### 4.5 順序約束（規範性）

**Eligibility 與 risk eligibility 必須嚴格早於 ranking。** 若先排序再篩流動性，breadth 會變成不穩定殘量（Top20 剔掉 5 檔剩 15），違反「排除與排序分離」。

---

## §5 Selection / Portfolio（規範性）

```
N_target        = 20
w_target = w_max = 5%（每檔固定，不因檔數變動）
len(selected)   = min(20, len(eligible))
Σ w_actual      ≤ 100%（非滿倉要求）
```

**明文禁止 `1/n` 權重。** 若只有 15 檔 eligible → `15 × 5% = 75%` 股票 + 25% 現金，**不是** `1/15 = 6.67%`。否則 `w_max` 形同虛設，且組合會在標的最少（通常也是流動性最緊）時把單檔曝險推到最高。

**Shortfall 一律回 cash，永不重新正規化。** 合法的低於 100% 曝險成因：交易成本、ADV order cap、`pending_exit`、odd-lot 執行差異、可用現金、`eligible < 20`。

### 5.0 Ranking tie-break（C-33，v1.5，規範性）

```
canonical sort key = ( −SelectionScore , stock_id ascending )
```

`len(selected) = min(20, len(eligible))` 是精確的，因此橫跨第 20 名的平手必須由某個東西決定。**交給排序穩定性等於交給 row order，也就是交給 adapter** —— 兩個 adapter 列序不同就會在通過所有守衛的情況下產出不同組合，從內部擊穿 B-20。

**明文禁止以市值、ADV、其他 alpha 作為次級排序鍵。** 每一個都會讓第二個未登記的選股訊號從平手處進入：「平手時偏好較大的標的」是一個 size tilt，而且**因為看起來像排序細節，永遠不會出現在自由參數計數裡**。機械記錄：`FORBIDDEN_TIE_BREAK_KEYS`。

### 5.1 Target drift（C-16，v1.3 補回，規範性）

**每一個 decision date 都把仍在名單內的持股重設回 5% target。**

```
target_value_i(t)  = 0.05 × port_value(t)
order_delta_i      = target_shares_i − current_shares_i
```

受既有 execution 約束限制：sell-first、實際已實現現金、1% ADV cap、`pending_exit`（§6.4）。

**B0 不是 buy-and-hold-until-dropped。** 此條為 omission correction：B-06 / B-12 implementation spec 已將 `compute_order_intent` 定為固定 `w_target = 5%`，B-14 並明文把續留標的描述為漂移一個月後產生小額 delta rebalance。**本文件 v1.0 未抄錄，故補回。**

**機械強制：** `TARGET_DRIFT_POLICY = "rebalance_to_5pct_each_decision"`，且 `DRIFT_POLICIES` 只有這一個值 —— **另一種讀法不保留為可選分支**。不可達的替代方案是文件；可達的替代方案是等著被呼叫的自由參數。

**容量事實（凍結記錄，非績效）：** `port_value_max(t) = ADV20(第20大)(t) ÷ 5`；141 期實測最小 **NT$105,612,486**、中位 NT$314,103,312。**容量下界約 1.06 億，遠高於 `C_ref` 200 萬，在可預見規模內不是限制。**

---

## §6 Execution（規範性）

### 6.1.0 M-1 · Canonical pipeline order（v1.0 凍結，v1.20 移入 §6.1 之下）

```
pit_raw_state
   → corporate_action_transition      ← O-A: MANDATORY pre-mark stage
   → portfolio_mark
   → eligibility
   → features
   → selection_score
   → target_portfolio
   → order_intents
   → execution
   → costs
   → post_trade_nav
```

**順序不可調換。** stage 可以跳過（診斷跑不必下單），**但永遠不得重排** —— 順序就是這條款的全部內容。機械強制：`assert_stage_order()`、`assert_corporate_action_precedes_mark()`。

**三個關鍵前後關係：**
- **corporate_action_transition 必須早於 portfolio_mark。** 用除權前股數去 mark 是靜默的 NAV 錯誤。
- **portfolio_mark 必須早於 eligibility。** `ADV_floor = 5 × port_value` 由 mark 推導。
- **eligibility 必須早於 features / selection_score。** 排除與排序分離（§4.5）。

**O-A（凍結）：`corporate_action_transition` 是 pre-mark mandatory stage，不只是「排在前面」。**

```
CORPORATE_ACTION_STAGE_GUARDS = (
    assert_exposure_reconstructible,       # W-1 暴露閘
    assert_no_unexplained_price_gap,       # O-B 價格缺口守衛
)
```

兩個守衛**必須在任何持倉 valuation 與 order generation 之前生效**。**不得等到 execution 才發現昨天的持股其實已經發生 corporate action。**

此條款單獨檢查（`assert_corporate_action_precedes_mark`）而非僅由排序推導 —— 因為**完全跳過該 stage 的執行會 trivially 通過排序檢查**。任何下游 stage（mark / eligibility / features / selection_score / target_portfolio / order_intents / execution / costs / post_trade_nav）出現而該 stage 缺席 → abort。

**架構約束（規範性）：** execution engine **不得**自行散落判斷 `if dividend / if capital_reduction / if merger`。固定為：

```
portfolio state → corporate_action_engine → validated transformed state → execution / valuation
```

只有 `core.b0_corporate_actions` 可以 dispatch on event kind；其餘 stage 一律消費**已轉換且已驗證**的 state。機械強制：`assert_no_scattered_dispatch()`，並對實際 `core/b0_*.py` 模組做 AST 檢查。

**日內更細的事件順序若日後需要，由 execution spec 另定 —— 但不得等到回測時才決定（§1.5）。**

---

### 6.1 Corporate Action State Transition

> **Status: NORMATIVE / FROZEN AFTER SEAL.**
> 本節定義 canonical portfolio pipeline 中 holder-affecting corporate actions 的
> **唯一合法狀態轉換語義**。一旦進入 Baseline Seal，不得於 sealed run、L2 opening、
> execution、valuation 或 result interpretation 階段修改、補充、例外化，
> 或以 runner-local logic 替代。

#### §6.1.1 Governing principle

Corporate action **不得**只被視為分類資訊、價格調整資訊或 execution-time 特例。

任何會改變投資組合所擁有之 tradable shares、non-tradable security entitlement、
available cash、cash entitlement、security identity、pending exit obligation 之
corporate action，**MUST** 在 portfolio valuation、decision 與 execution 之前完成
state transition。

Canonical causal chain：

```
PortfolioState[t-1]
    ↓ release matured pre-existing receivables
    ↓ corporate_action_engine
validated transformed PortfolioState[t]
    ↓ mark_portfolio → decision → execution
post-execution PortfolioState[t]
```

**禁止**：old PortfolioState → mark / decision / execution → 事後才發現 corporate action。
亦禁止以除權、減資、換股或合併前之持股數量，去 mark 已發生 corporate action 後的價格。
此行為屬 **silent NAV error**，不得產生任何可解讀之 performance result。

#### §6.1.2 Sole authority and architecture

dispatch authority 唯一屬於 `core.b0_corporate_actions`。任何 runner / execution /
valuation / portfolio / backtest loop / special-case patch **MUST NOT** dispatch on kind。
`assert_no_scattered_dispatch` 維持為 blocking invariant。

模組必須具備**兩個**概念層次：

```
normalize / classify   raw event      → CorporateActionEvent
state transition       PortfolioState + CorporateActionEvent
                                      → CorporateActionTransitionResult
                                      → transformed PortfolioState
```

**只有 `classify()` / `handle_*()` 而只回傳 `CorporateActionEvent`、未改變 portfolio
state，不構成符合本節的 engine implementation。** 任何
`changes_our_shares == True` 或 `changes_our_cash == True` 的 EventKind，
若其 handler 最終可走到 no-op state transition，即為 **conformance failure**（I-CA-14）。

#### §6.1.3 Holder-affecting event scope

凍結五種：`stock_dividend`、`capital_reduction`、`merger`、`share_conversion`、
`par_value_change`。五種皆 `changes_our_shares = True`；
`capital_reduction` / `merger` / `share_conversion` 的 `changes_our_cash` 由 event terms 決定。
本節**不**重新裁定 ordinary cash dividend 或其他已凍結語義；未列於上述五種之事件
不得因本節而新增 state semantics。

#### §6.1.4 Canonical PortfolioState

MUST 能表示六者：`tradable_positions`、`available_cash`、`security_receivables`、
`cash_receivables`、`pending_exits`、`applied_corporate_action_event_ids`。

**Critical distinction —— 三者不得混為一談：**

```
owned      經濟上擁有          → 計入 NAV
tradable   execution 可賣出    → 計入 shares
spendable  execution 可用以買進 → 計入 cash
```

配股 receivable 可以是 `owned=True, tradable=False`；減資退款可以是
`owned=True, spendable=False`。在轉為 tradable / spendable 之前：
security receivable **MUST NOT** 被 execution 賣出、cash receivable **MUST NOT**
被 execution 使用；兩者若可合法 mark，**MUST** 納入 NAV。

#### §6.1.5 Canonical dates and PIT semantics

每個影響 PortfolioState 的 normalized event MUST 能提供或明確推導：
`knowledge_ts`、`effective_date`、`credit_tradable_date`（若有 security entitlement）、
`cash_available_date`（若有 cash entitlement）。

- `knowledge_ts` 晚於當期 cutoff 者不得用於 retroactive transition（I-CA-06）。
- `effective_date` 為 economic claim 改變之日。
- `credit_tradable_date` 為 security receivable 首次成為 executable tradable position 之日。
  **股票權利在 ex-right date 出現，不代表立即成為 tradable shares。**
- `cash_available_date` 為 cash receivable 首次可供 execution 使用之日。
- `zero_day_receivable = True` 僅當 canonical source 明確證明
  `effective_date == credit_tradable_date` 且該 security 於 canonical execution point
  已可合法交易。**不得因缺 credit date 而自行推定 zero-day。**

#### §6.1.6 Intra-period transition order

每一 canonical period 於 mark / decision / execution 之前 MUST 依序：

```
1 release 先前 periods 建立、今日成熟之 receivables
2 apply 今日 effective 的 holder-affecting events
3 release 本步建立且 zero_day 之 claims
4 transform / reconcile pending_exits
5 run reconstructibility 與 state invariants
6 produce validated transformed state
7 mark_portfolio → 8 decision → 9 execution
```

日期落於非 canonical trading session 者，release point 為
**first eligible portfolio-state timestamp on or after the stated date**。

#### §6.1.7 Transition table

**A. stock_dividend** — 設 `Q` = 轉換前 entitlement-bearing shares、`r` = 每股新股數。
於 `effective_date`：tradable 維持 `Q`，另建立 `Q × r` 之 **non-tradable security receivable**。
新配股**不得**於 ex-right date 自動塞入 tradable position；直至 `credit_tradable_date`
才 `security_receivable → tradable_positions`。`zero_day_receivable == True` 時
仍須依序 ledger（create receivable → same-day release），**不得略過 receivable state**。
`zero_day == False` 且 credit-tradable 語義不可重建 → 有 exposure 時 W-1 block。

**B. capital_reduction** — 設 `Q`、`m` = 每股存續股數、`c` = 每股退款。
於 `effective_date`：`post shares = Q × m`，原股數立即停止作為 exposure。
若有退款：`cash_receivable += Q × c`，**立即屬於 NAV economic claim，但 available_cash 不得增加**；
僅於 `cash_available_date` 才轉入 available cash。
**禁止：減資 effective date → 立即把未收到的退款拿去買股票。**
宣告 `changes_our_cash=True` 但金額或到期日不可 PIT 重建者，有 exposure 時 MUST block。

**C. merger** — identity transition。設 `Q`、`S_old`、`S_new`、`r`、`c`（optional）。
`tradable_position[S_old] = 0`，建立 `security_receivable[S_new] += Q × r`，
若適用另建 `cash_receivable += Q × c`。
`S_old` 與 `S_new` **MUST** 視為不同 identity：禁止 price-series splice、
禁止以 adjustment factor 假裝延續 —— 與 C-50/R5 一致：
**價格序列不得因換股而人工續接；portfolio claim 必須透過 state transition 轉移。**
successor 僅於 `credit_tradable_date` 後成為 tradable，cash 僅於 `cash_available_date` 後可用。

**D. share_conversion** — 與 merger 相同的 identity-transition 架構。
必要條款至少：old identity、successor identity、conversion ratio、`effective_date`、
`credit_tradable_date`、`knowledge_ts`。任一不可唯一重建且有 exposure → MUST block。
**不得**以 price adjustment 或 security-id alias 取代 state transition。

**E. par_value_change** — identity 未變者：`share multiplier = P_old / P_new`，
`Q_new = Q × P_old / P_new`，於 effective date 更新。
**不得因「總經濟價值應差不多」而留下原股數不動。**
若同時伴隨 identity change，MUST 改走 share_conversion semantics。
`old par` / `new par` / `effective date` 任一不可重建且有 exposure → MUST block。

#### §6.1.8 Receivable valuation

engine 顯式處理股數後，valuation **MUST** 使用 canonical raw / unadjusted price；
不得同時調整股數又使用 corporate-action-adjusted price（**double adjustment**，I-CA-15）。

security receivable 的合法 valuation 僅允許：(1) 該 receivable security 自身之
canonical PIT market mark；(2) 交易所／發行人官方公布且 PIT-known 之 corporate-action
reference mark。**不得**使用 future price、backfilled successor price、model-imputed price、
old-security splice、post-hoc optimization。
successor receivable 若無合法 mark 亦無 official PIT-known reference value，
則為 **UNMARKABLE**，有 exposure 時 MUST fail closed。
cash receivable 以 **face value** 計入 NAV，但在 `cash_available_date` 前不得進入 available cash。

#### §6.1.9 Fractional entitlement and rounding

所有 corporate-action arithmetic **MUST** 使用 deterministic high-precision arithmetic。
state transition 階段**禁止** `round()` / `int()` / lot rounding / nearest-share approximation
導致權利憑空消失。`economic units` 與 `executable units` 必須分開。

小於 canonical executable unit 之 fractional entitlement **MUST 保留為 non-tradable
entitlement**，直到官方 settlement semantics 可重建。若官方規則要求 cash-in-lieu，
則 `fractional security claim → cash receivable`。
若 fractional settlement 會影響 exposed holding 之 NAV / cash / exit 而 settlement semantics
無法 reconstruct → **W-1 BLOCK**。不得以 floor-and-discard / ceil / round-to-nearest 讓 run 繼續。

#### §6.1.10 Pending-exit semantics

corporate action **MUST NOT** 使既存退出意圖因 identity 或 share count 改變而消失，
亦不得把 pre-event absolute order quantity 原封不動送進 execution。

> pending exit 表示 **portfolio target obligation**，而非受 corporate action 凍結前的
> stale share order。

transition 後 execution quantity MUST 重新由 transformed state 推導。
same-security share transformation（`capital_reduction` / `par_value_change`）之
pending exit MUST 依相同 multiplier 轉換。
stock dividend 下若 position 已存在 full-exit obligation，新 receivable MUST 繼承該義務；
尚不可交易時 exit remains pending，於首次 tradable canonical execution opportunity 執行 ——
**不得因 credit delay 而使原本 zero-target position 重新成為永久持倉。**
merger / share_conversion 下 pending exit MUST 跟隨 economic claim 移轉至 successor。
任何引用 pre-event identity 或 pre-event quantity 之 live/stale order MUST 被 invalidated 後重建。
**禁止 synthetic fill。**

#### §6.1.11 Multiple / chained corporate actions

每個 event MUST 有 deterministic stable `event_id`；PortfolioState MUST 保存
`applied_ca_event_ids`。同一事件 **MUST apply exactly once**，不得因 rerun / reload /
valuation retry 而重複套用（I-CA-01）。

同一 security 同一天存在多個 non-commutative holder-affecting actions 時，
僅以下兩種情形可繼續：(A) source 明確提供 causal `event_sequence`；
(B) engine 可證明 transitions commute。否則 **NOT_RECONSTRUCTIBLE**，有 exposure 時 W-1 block。
**不得**以 alphabetical kind、event_id 或 database row order 決定經濟因果順序。
chained identity change（`A → B → C`）必須逐次 security-receivable transition，
**禁止 A 直接 splice 到 C**。

#### §6.1.12 Reconstructibility and W-1 exposure gate

`NOT_RECONSTRUCTIBLE` event **不自動**使整個 141-period run 失效。真正的 blocking condition 為：

```
NOT_RECONSTRUCTIBLE  AND  portfolio has affected economic exposure
```

affected economic exposure 包含 tradable position、security receivable、
entitlement-bearing claim、unresolved pending-exit claim。

- `NOT_RECONSTRUCTIBLE + zero exposure` → log as irrelevant → continue
- `NOT_RECONSTRUCTIBLE + nonzero exposure` → **fail closed**

**不得**：偷偷排除該股票、提前賣掉以避開事件、忽略事件、以 adjusted price 補洞、
把 holding 設為 zero、跳過該 period、carry old shares forward。
上述任何一項均會改寫 sealed strategy history。

#### §6.1.13 Mandatory invariants

每次 transition 後、`mark_portfolio` 前 MUST 全數驗證：

| # | 不變量 |
|---|---|
| I-CA-01 | Exactly once —— `event_id` 不得重複 apply |
| I-CA-02 | No stale exposure —— 事件生效後不得留下未轉換之 pre-event shares |
| I-CA-03 | No free shares —— 新增股數必須可追溯到 event_id / ratio / pre-event entitlement |
| I-CA-04 | No free cash —— 新增 cash / cash receivable 同上 |
| I-CA-05 | Receivable separation —— `security_receivable != tradable_position`、`cash_receivable != available_cash` |
| I-CA-06 | No look-ahead —— 不得依賴 `knowledge_ts` 晚於當期 cutoff 之資料 |
| I-CA-07 | Identity integrity —— merger / share_conversion 不得延續 old identity 或 old price series |
| I-CA-08 | Mark completeness —— 每一非零 tradable asset / security receivable / cash receivable 必須能合法 mark，否則不得計算 NAV |
| I-CA-09 | Execution eligibility —— non-tradable entitlement 不得形成 sell fill；non-available cash 不得形成 buy funding |
| I-CA-10 | Pending-exit continuity —— corporate action 不得無故刪除既存退出義務 |
| I-CA-11 | No scattered dispatch —— 只有 `core.b0_corporate_actions` 可依 EventKind 決定 transition |
| I-CA-12 | Determinism —— 相同 pre-state / events / cutoff / calendar 必須產生 byte-equivalent state hash |
| I-CA-13 | Atomicity —— 一個事件 either fully validates and commits, or commits nothing |
| I-CA-14 | Flag conformance —— 宣告 `changes_our_shares` / `changes_our_cash` 者，exposed transition 必須產生可驗證之對應效果，不得 no-op |
| I-CA-15 | No adjusted-price double counting —— 已顯式轉換股數/現金者，valuation 不得再用會重複補償該事件的 adjusted price |

#### §6.1.14 Failure semantics

三種**完全不同**的 failure：

**F-CA-A — PRE-OPEN BASELINE DEFECT.** 例如：mandatory state-transition engine 不存在、
handler 只有 classification 而無 PortfolioState transition、`changes_our_shares` handler 可 no-op、
canonical architecture 與 Master 不一致、mandatory conformance test failure。
分類為 **M-3 / §1.5 baseline implementation defect**。處置：
**MUST NOT** establish L2 opening record、**MUST NOT** set `l2_opened = true`、
**MUST NOT** run decision、**MUST NOT** compute performance、
**MUST NOT** 分類為 `NOT EVALUABLE — DATA RECONSTRUCTION BLOCK`。
必須 stop → revise Master / implementation → new Baseline Seal → fresh authorization。

**F-CA-B — LEGITIMATE RUNTIME DATA RECONSTRUCTION BLOCK.** 前提：baseline implementation
conforming、L2 legitimately opened、canonical decision path 產生了實際 exposure；
之後遇到 `NOT_RECONSTRUCTIBLE + affected exposure > 0`。正式結果為
**`NOT EVALUABLE — CORPORATE ACTION RECONSTRUCTION BLOCK`**，且 MUST 記錄至少：
`run_id`、period、`security_id`、`event_id`、`event_kind`、`effective_date`、
exposure quantity/type、missing/ambiguous required fields、source lineage、
`pre_state_hash`、`last_valid_state_hash`。
**不得** retry、替換資料源、改 handler、改 universe 或跳過事件後繼續同一次 sealed run。

**F-CA-C — IMPLEMENTATION / INVARIANT FAILURE AFTER OPEN.** 進入 valid run 後出現
impossible state、double application、negative unexplained shares、untraceable cash、
handler no-op、identity splice、non-deterministic transition、atomicity failure 等，
**不得**標為 data reconstruction block，而應標為
**`RUN INVALID — IMPLEMENTATION CONFORMANCE FAILURE`**。該 run MUST NOT 產生可解讀之
performance、MUST NOT 被 tune、MUST NOT 作為 L2 evidence；Baseline Seal 視為未能證明
implementation conformance。重新開封須先 fix → 必要時新 Master revision → new commit →
new Baseline Seal → fresh explicit authorization。**本條不自行授予 retry 權。**

#### §6.1.15 Valuation at terminal boundary

window 結束時若存在合法且 reconstructible 之 security / cash receivable，
**不得**為了讓回測「結清」而使用 window 之後的資料提前 settlement。
Terminal NAV MUST 包含 tradable positions + markable security receivables +
cash receivables at face value + available cash。
terminal receivable 若無法在 terminal cutoff 下合法 mark →
`NOT EVALUABLE — CORPORATE ACTION RECONSTRUCTION BLOCK`。**不得**以 window 之後價格補值。

#### §6.1.16 Taxes, fees, withholding

本節不建立新的 corporate-action 稅負模型；cash consideration 之 tax / withholding / fees
由既有 frozen canonical cost/tax semantics 處理，engine **不得**自行新增 ad-hoc tax approximation。
若 mandatory withholding 會 materially 改變 available cash，而既有 frozen semantics 無法表示
且 PIT data 亦不足 → 該 event 對 exposed holdings 成為 `NOT_RECONSTRUCTIBLE`。

#### §6.1.17 Required audit ledger

每次 holder-affecting transition MUST 產生 immutable audit record，欄位至少：
period、event_id、event_kind、security_id、successor_security_id、
knowledge_ts、effective_date、credit_tradable_date、cash_available_date、
pre/post tradable shares、created/released security receivables、
created cash receivables、released cash、pending-exit before/after、
reconstructibility status、blocking reason、`pre_state_hash`、`post_state_hash`、
`event_source_hash`。
相同 baseline/input MUST 重現完全相同的 transition ledger 與 `post_state_hash`。
**此 ledger 為 L2 provenance 的一部分，不得只留 log text。**

#### §6.1.18 Implementation conformance requirements

Master v1.20 僅在下列全部 PASS 後才能重新建立 Baseline Seal。
`core.b0_corporate_actions` MUST accept `PortfolioState`、apply 全部五種 holder-affecting
EventKinds、return transformed `PortfolioState` / `TransitionResult`。

必須具備 deterministic tests：stock dividend normal credit、stock dividend zero-day credit、
capital reduction shares-only、capital reduction + cash refund、merger share-only、
merger cash-only、merger mixed consideration、share conversion、par value increase/decrease、
pending full exit across each share-changing event、same-day receivable maturity、
multiple ordered events、unheld NOT_RECONSTRUCTIBLE event、held NOT_RECONSTRUCTIBLE event、
fractional entitlement、duplicate event_id、handler atomic rollback、
successor security unmarkable、late/non-PIT event information。
並須驗證 **I-CA-01 … I-CA-15 全部 PASS**。

#### §6.1.19 Seal and L2 reauthorization

Master v1.20 與 conforming implementation 完成後，舊的
`Master v1.19` / `bound commit a0241f3d` / `Baseline Seal 5fef4104`
**不再具備下一次 L2 opening 的授權效力**，MUST 保留作 provenance 並標記 **SUPERSEDED**，
不得刪除、覆寫或假裝未存在。

新程序必須重新完成：Master v1.20 freeze → implementation conformance →
all baseline verification → 0 OPEN SPEC ITEMS → 0 OPEN FINALIZATION ITEMS →
clean worktree → new bound commit → new spec hash → new Baseline Seal →
141/141 market-side state reproducibility → corporate-action conformance preflight →
**explicit fresh L2 opening authorization**。

在新的 opening record 真正建立以前 `l2_opened` **MUST remain false**。
**不得因修復 corporate-action engine 而視為已消耗原先未使用之 L2 opening。**

#### Annex CA-A — Normative transition matrix

| Event | effective-date state | 非交易 claim | 何時可交易/可用 | identity | 無法 reconstruct 且有 exposure |
|---|---|---|---|---|---|
| `stock_dividend` | 原股保持 `Q` | `Q × r` security receivable | `credit_tradable_date` | same | W-1 block |
| `capital_reduction` | `Q → Q × m` | cash receivable `Q × c`（若適用） | `cash_available_date` | same | W-1 block |
| `merger` | old shares → 0 | successor security 與／或 cash receivable | 各自 release date | **changes** | W-1 block |
| `share_conversion` | old shares → 0 | successor security 與／或 cash receivable | 各自 release date | **changes** | W-1 block |
| `par_value_change` | `Q → Q × P_old/P_new` | 通常無（僅小數餘額） | 即時（餘額保留為 claim） | same | W-1 block |

> 使用者原文之 Annex 表格在 `par_value_change` 一列於傳輸中截斷；此處的該列內容
> 依 §6.1.7E 正文（`Q × P_old/P_new`、identity 不變、不可重建且有 exposure 時 W-1 block）
> 補完，未新增正文以外的語義。

---

### 6.2 Portfolio mark（G7）

```
port_value(t) = cash(t) + Σ_i shares(i,t) × mark_price(i,t)
```

`mark_price` **不得**來自 target list、**不得**依 `SelectionScore` / eligibility 決定，須由 decision date 的 **PIT 全市場價格來源獨立取得**。

**既有持倉在 as-of 無可用 mark price 時，不得因「它不在候選池」而視為 0** —— 須 fail-loud。**selection 不得決定 portfolio valuation。**

### 6.3 Share ledger

- **canonical unit = share**；odd-lot **ENABLED**
- lot 僅為顯示分組，**不得參與部位或成本運算**
- 帳本中不得殘留任何 `× LOT_SIZE` 的部位/成本運算（G4；該處曾出過單位 bug）

### 6.4 訂單與現金（規範性）

**Rebalance day 執行順序（不可調換）：**

```
1. 產生 required sells
2. 在當日 sell capacity 內執行（X_sell = 1% ADV20）
3. 未完成 → pending_exit
4. 依「實際已實現」的可用現金執行新買單
```

**三條硬約束：**
- **不得用預期賣出收入預支新倉。** 未成交的 sell 不算變現。
- **B0 不借款、不允許負現金。**
- `pending_exit` 部位**仍屬持倉**：計入 `port_value`，share 數不得消失，未實現賣出價金不得計入 available cash（G8）。

**現金不足時的買單順序（C-32，v1.5，規範性）：**

```
sell 完成後 → 以「實際已實現」的可用現金
           → 買單按 Selection rank 由高到低處理
           → 每檔實際買入 = min( target shortfall , 1% ADV20 cap , available cash )
           → cash 用盡即停止
```

**不得借款、不得 proportional scaling。** 等比例縮放會把現金不足**悄悄轉成一個權重決定**：20 檔各 4% 與 16 檔各 5% + 現金是兩個不同的組合，而 §5 已經決定了 B0 是哪一個。

> **實作讀法（揭露）：** 買單依 rank 逐檔處理，某檔因現金不足而完全買不到時**跳過該檔繼續往下**，而非中止整個迴圈。差異僅出現在「較高 rank 的標的買不起、較低 rank 的較便宜標的仍買得起」的情形。

**股數取整（C-34，v1.5，規範性）：**

```
target_shares = floor( target_value / reference_price )
```

odd-lot enabled，故最小單位為 **1 股**。**`w_max = 5%` 是對「已執行部位」的 hard cap，不只是對 target** —— 這正是只能用 `floor` 的原因：nearest 可能讓高價股超過 5% 上限達半股價值。**取整餘額留 cash**（與 §5 對其他 shortfall 的處置一致）。

**Entry / exit horizon 不對稱（必須分別陳述）：**
- **Entry eligibility horizon = 1 個交易日**（這是 eligibility 判準）
- **Exit 不要求一日完成** —— 每日 1% ADV20 cap，殘額按日 carry forward 至歸零

**後果（是 execution reality，不是模型錯誤）：** 若舊部位流動性惡化，新組合可能暫時 under-invested，並同時持有 residual old names。

**`pending_exit` 殘量的 cap 基準（C-27，v1.4 補回）：** 殘量**每個交易日各自對「該 session 自己的 ADV20」重新設 cap**，該 ADV20 以當日前一收盤為準。此條並非新規則，只是把兩條既凍條文並排陳述：§6.4 規定每日 cap 為 ADV20 的 1% 且殘額按日 carry forward，§7.3 規定多日執行每日各自使用當日 pre-execution 的 `σ20D`/`ADV20`。**若把 cap 固定在首日的 ADV20，一檔流動性已崩壞的標的仍會以舊容量繼續賣出。** 機械記錄：`PENDING_EXIT_CAP_BASIS`。

### 6.5 執行日

`open(t+1)`；多日 exit 順延交易日。

### 6.6 O-D · 日內順序（凍結）

月頻 decision date 可能落在 corporate-action date 上。若日內順序未固定，**同一天可以產生不同的 NAV** —— 那是一個穿著實作細節外衣的自由參數。

```
start_of_trading_day
  → apply_known_effective_corporate_actions
  → establish_tradable_holdings
  → obtain_permitted_execution_price
  → execute_child_orders
  → apply_costs
  → end_of_day_state
```

**順序不可調換。** 機械強制：`assert_intraday_order()`；未定義的步驟走 M-3 abort。

**兩條配套規則（規範性）：**

```
DECISION_STATE_SOURCE       = prior_completed_trading_session
CASH_DIVIDEND_CREDIT_EVENT  = payment_date
STOCK_DIVIDEND_CREDIT_EVENT = max(股票股利上市日, 股票股利發放日)
```

**所有 decision state 使用前一個已完成交易日的資料。** 這與 G14-1 對 `σ20D`/`ADV20` 已經套用的規則相同，此處把它從逐欄位規則提升為對每一個 decision input 都成立的通則。機械強制：`assert_decision_inputs_are_prior_session()`。

**現金於 `payment_date` 當日才進 available cash** —— 與 §2.5「不得預支股利」及 §6.4 no-leverage 一致。

**執行價格語義不在此重新創造** —— 沿用 §6.5 既有的 `open(t+1)`。O-D 只固定「同一天內各效果的先後」，不新增價格規則。

---

## §7 Cost（規範性）

### 7.1 模型

```
per strategy child order, value V, side, instrument i, execution day t:

  explicit_fee    = max(MIN_FEE, V × COMMISSION_RATE)
  transaction_tax = V × TAX_RATE            if side == "sell" else 0
  impact          = V × IMPACT_K × σ20D × sqrt(V / ADV20)
  total           = explicit_fee + transaction_tax + impact
```

### 7.1.1 `ADV20` 與 `σ20D` 的定義（C-25 / C-26，v1.4 補回，規範性）

兩者各自同時撐著三個條文（§4.2 eligibility 閘、§6.4 1% order cap、§7.1 impact），因此**只能有一個定義**。

```
ADV20(i,t) = mean( close_s × volume_s )  取「最近 20 個已觀測 session」
             已觀測 session 不足 20 → NA

σ20D(i,t)  = 「trailing 20 交易日 log return 標準差，PIT、未年化」   ← B-14 P3 原文
             需要 21 個連續已觀測收盤價；任一收盤價 ≤ 0 → NA
```

**ADV20 用「已觀測 session」而非日曆日**（C-25）：停牌期間該檔只貢獻它實際交易的 session，與 O-E 對交易日曆的處置一致，也與 legacy producer 一致（`universe_screen_daily.py:165`，`dollar_vol.tail(20).mean()`）。**不足 20 個 session 回 NA 而非改用較短窗** —— 縮窗會恰好對 §4.2 要剔除的低流動性與新上市標的偷偷換掉度量，而 §4.2 已裁定「缺流動性觀測是證據不足，不是合格證據」。

**σ20D 未年化，這不是細節**（C-26）：它線性乘進 impact（§7.1），年化與否**相差約 15.9 倍**；而 §7.6 禁止宣稱成本模型偏誤的方向，因此這種錯誤連「偏保守」都稱不上。

**標準差自由度（C-28，v1.5）：`ddof = 1`，樣本標準差。**

B-14 P3 定死了 σ20D 的其他一切，唯獨未指定自由度。此處補上的是 **explicit specification completion，不是 runtime tunable** —— `SIGMA20D_DDOF` 是常數，沒有任何呼叫端可以改它。與 ddof = 0 相差 `√(20/19) ≈ 1.026` 倍，直接乘在 impact 上，故具名記錄以便日後改動是一個 diff 而非考古。

### 7.1.2 常數

| 常數 | 值 | 性質 |
|---|---|---|
| `COMMISSION_RATE` | 0.001425 | B0 reference commission rate，d = 1.0，不假設折扣 |
| `MIN_FEE` | 20.0 | **券商政策，非法定最低**；整張與零股同 |
| `TAX_RATE` | 0.003 | 證交稅，賣方 |
| `IMPACT_K` | 1.0 | **order-one external-prior reference，不是台股實證估計** |

### 7.2 三分離不得塌回單一比例（規範性）

三個成分的不確定性來源不同（宣告的券商政策 / 外部稅法 / 外部先驗估計）。塌成單一比例會讓「成本假設錯了」與「策略錯了」變得不可區分。

機械強制：`CostBreakdown.effective_rate` **刻意 raise AttributeError**。

### 7.3 Child order 語義（G14-2）

**`MIN_FEE` 按 strategy child order 收取，不是按每筆 fill。** 必須先 `aggregate_fills()` 再計費，否則一張拆成 5 筆成交會付 5 × `MIN_FEE`。

多日執行（`pending_exit`）**每交易日呼叫一次**，各自用當日的 pre-execution `σ20D`/`ADV20` 與實際成交金額。**不引入 decay 參數。**

### 7.4 Look-ahead（G14-1）

`σ20D` / `ADV20` 的資料窗必須**嚴格早於執行日**。多日 child order 的「當日」意為 **as of prior close**，永不含執行日自身的成交量或報酬。

### 7.5 Tradability 與定價分離（G14-3）

**成本模型定價，不決定訂單能否成交。** `execution_confirmed` 為 keyword-only 且**無預設值**。`σ20D == 0` 或 `ADV20 > 0` **不是**可交易性的證據 —— 停牌或漲跌停鎖死的標的兩者都可能成立。正確答案是 "execution infeasible"，不是「以零衝擊成交」。

`σ20D == 0` 的成交打 `zero_sigma_fill` 旗標上收據，可稽核，不得靜默吸收。

### 7.6 Disclosure（D14-1，必須隨任何引用 B0 成本數字的結論帶走）

> B0 只建模平方根市場衝擊 proxy。**買賣價差、tick size 效應、日內執行效應皆未分別建模。**
> 因此該欄位**不得**讀作完整的隱性交易成本，**且不得宣稱其偏誤方向** —— `IMPACT_K = 1.0` 是 order-one 外部先驗參考值，proxy 可能高估也可能低估。
> **不得**將建模數字描述為任一方向的 bound。

### 7.7 不提供可調參數入口

刻意不提供 tunable-parameter override entry point：此處的旋鈕會變成第二個 `composite_weights`。

---

## §8 Integrity / Production（規範性）

### 8.1 B-17 · Regime 不可達

**B0 production-reachable 路徑中，ranking / eligibility / weight / cost 任一環節不得包含 regime-dependent 的 alpha 乘數、門檻或分支。**

禁止符號：`REGIME_MULTIPLIERS`、`regime_multipliers`、`regime_rating_gates`、`classify_regime`、`current_regime`、`use_regime`、`_regime_at`、`OVERLAY_ALPHA`。
禁止模組：`core.regime`、`core.regime_exposure`。

**Reporting-only 的 regime 標籤不在此限。**

### 8.2 B-19 · Override integrity

```
B0_REGISTERED_OVERRIDES = {}          # 空 = 零授權
```

禁止符號：`RESEARCH_ARM`、`TEJ_RUNTIME_OVERLAY_DIR`、`_PCT_HISTORY_START`、`bt_fetch_history`、`USE_RS_OVERLAY`、`USE_KD_FULL`、`USE_BBP`、`USE_OBV_TREND`、`USE_ASSET_TURNOVER`。

**未登記即 abort，無 default fallback。** import-time 跨模組全域改寫（`bt_bundle.py:27` 式）另有專屬偵測器。

### 8.3 G14-4 · Frozen-A 成本路徑不可達

`BUY_COST` / `SELL_COST`、`l4b_execution`、`portfolio_simulator_lab` **不得出現在 B0 import closure 中**。

### 8.4 可達性的執行方式（規範性）

**靜態 AST import closure，絕不 import 執行模組。** 理由有二：(1) 可達性本來就是靜態性質；(2) `core/data_provider.py:23` 在 class body 實例化 `DataLoader()` 會觸發網路登入等破壞性副作用，而 import 失敗會被 `except: continue` 吞掉，反而遮蔽違規。

`B0_ENTRY_MODULES` 為所有不變量的共同入口；route 建成後其 entry module **必須**加入，五個不變量隨即自動生效。

### 8.5 B-20 · Path parity

**production 與 research 必須共用同一 engine。** parity 比對五層（feature / eligibility / ranking_portfolio / execution / cost）、七欄（eligible / score / rank / selected / orders / cash / cost）。

- **輸入（as_of / config_hash / state_hash）先於輸出比對**，不符即 abort（比對不同輸入的輸出不是 parity）
- **`float_tol = 0.0`，bit-exact 預設**
- `B0_ROUTE_PAIRS` 空 = **不得宣告 parity**；**v1.7 已宣告一組**（C-37）：
  `("core.b0_adapter_production", "core.b0_adapter_retrospective")`，並附 deterministic fixture（`tests/test_b0_adapter_parity.py`）
- **比對的是 adapter 邊界，不是兩套演算法** —— 兩個 adapter 都只透過 `core.b0_route.run_decision` 進入 core，**AST 檢查禁止 adapter import 任何 canonical layer**

### 8.6 B-21 · Provenance

六類 manifest：code / config / data / derived / execution / output。

- `sealed_input_sha256` **刻意排除 outputs**
- **deterministic replay invariant：** 相同 sealed inputs 必須產生相同 outputs，**bit-exact**
- 合法的非決定性來源必須**逐項列舉**；`verify_replay()` **無 tolerance 參數**（有測試釘死簽名）—— 全域容差會讓真實差異藏在四捨五入裡
- **未登記的來源 fail loud，不是記錄下來就算數。** 記錄一個未登記的 dataset overlay 不會讓 run 變得可重現，只是記錄了它不可重現
- `final_seal=True` 額外禁止 dirty working tree
- 允許清單 env（`TEJ_CACHE`/`MARKET_CACHE`/`FINMIND_CACHE`）只搬位置；`TEJ_RUNTIME_OVERLAY` 改語義 → FAIL

### 8.7 Canonical shared core（P-1b / P-2，**PENDING IMPLEMENTATION**）

**四層 canonical core 的責任邊界（規範性）：**

| 模組 | 只負責 | **不得知道 / 不得重做** |
|---|---|---|
| `b0_features` | PIT input → canonical feature values | Top20、5%、cash、execution |
| `b0_eligibility` | PIT universe + complete-case + risk + dynamic investability → eligible set | 不得自行計算 `SelectionScore` |
| `b0_decision` | eligible names + canonical features + portfolio state → `SelectionScore` → rank → Top20 → 5% targets | 不得重新實作 feature 公式 |
| `b0_execution` | validated pre-trade state + target state → sell-first → pending_exit → buy → 1% ADV caps → share ledger → `b0_cost_model` → receipts | corporate action engine **必須是它的 upstream，不得藏在裡面成為各種 `if event_type`** |

**P-2 的正確形狀（規範性）：** 最終**不應**是兩個完整 engine 再做 parity，而是

```
                  ┌─ retrospective adapter
PIT → B0 core ────┤
                  └─ production adapter
```

**⇒ 真正需要 parity 的不是兩套演算法，而是兩個 adapter 是否向 canonical core 提供相同的 state / config / as_of，並正確消費輸出。** B-20 的 fixture 因此比對 adapter 邊界，而非重跑兩份完整計算。

**✅ v1.7 已實作。** 四層 + `core/b0_state.py`（輸入契約）+ `core/b0_route.py`（唯一入口）+ 兩個 adapter。

**「只有一套 engine」是結構事實而非宣稱：** `run_decision` 是全庫唯一依序呼叫四層的地方；adapter 只做 `source → PIT/provenance/schema 驗證 → canonical state`，且 **AST 檢查禁止它們 import `b0_features` / `b0_eligibility` / `b0_decision` / `b0_execution`，也禁止呼叫任何策略語義入口點**。adapter 要變成第二套 engine，得先讓測試變紅。

---

## §9 Validation Protocol（規範性）

### 9.1 L1 · Primary Structural Criteria（L2 開封的前置條件，全為非績效判準）

| # | 判準 | 狀態 |
|---|---|---|
| **S-1** | Selection 路徑 **runtime tunable 自由參數 = 0**（見下方措辭澄清） | ✅ **FROZEN**（v1.6；機械強制 `assert_selection_path_is_fully_specified`） |
| **S-2** | 所有已宣告不變量全綠（G1–G8、G14-1~4、B-17、M-1~M-3） | ⏳ **route-dependent 部分已綠**（v1.7：B-17 / B-19 / G14-4 / M-1 對 route + 兩個 adapter 生效）；其餘待逐項確認 |
| **S-3a** | PIT 完整性 —— **資料語義** | ✅ **SATISFIED**（v1.9：配股語義 + 價格母體皆已關閉） |
| **S-3b** | PIT 完整性 —— **end-to-end enforcement** | ✅ **SATISFIED**（v1.11 C-44：四個 enforcement 性質由 verifier 在真實證券上實跑 production guard 證得。**斷言 guard 兩側都正確動作，不斷言母體無缺口**）|
| **S-4** | 每期 complete-case 母體規模、eligibility 淘汰組成逐期報告 | 揭露要求，非門檻 |
| **S-5** | eligibility 嚴格早於 ranking | ✅ FROZEN（§4.5、M-1） |
| **S-6** | 每張收據帶 explicit_fee / transaction_tax / impact 三欄分離 | ✅ FROZEN |
| **S-7** | B0 不可達 Frozen-A 成本常數與 regime 決策路徑 | ✅ FROZEN |
| **S-8** | Provenance 完整 | ⏳ PENDING clean tree（route 已存在） |

> **S-1 措辭澄清（C-20，規範性）：** S-1 宣稱的是**沒有 runtime 可調參數、沒有人工切點、沒有由本專案自行挑選的門檻**。它**不是**宣稱「B0 不存在任何數值常數」—— §7.1 的成本常數、§4.4 relocate 自 F10 的門檻、§5 的 20 與 5% 都是**frozen inherited / declared constants**，逐一具名、逐一有來源、且不可於執行期改變。**兩者混為一談會使 S-1 在字面上永遠為假，或誘使施工方為了維持綠燈而隱藏常數。**
>
> **S-1 於 v1.6 轉綠，並且是可檢查的（C-36）。** `assert_selection_path_is_fully_specified()` 檢查四件事：canonical core 無任何 UNSPECIFIED 登記項；風險層自陳完備；feature graph 每個成員都有凍結公式與方向；C-32 ~ C-35 的四個慣例各自**只容許一個值**（有可選替代方案的慣例就是 runtime tunable parameter，不論文件怎麼稱呼它）。
>
> **⚠ 它證明的是「規格完備」，不是「路徑遵守規格」。** 後者是 S-2 與 S-3b，兩者在 route 建成前仍為 PENDING。**把這兩件事合併成一個綠燈，正是 §11 C-3 記錄的錯誤。**

### 9.2 報酬線（規範性）

**B0 不得直接沿用 Frozen A 的 `exec_ret.fwd_x`。** 該規則的**意圖**（絕不使用有偏的 `obs_alpha.fwd`）完全承接，但其**實作**不可沿用：Frozen A 的 `fwd_x` 是月頻面板量，而 B0 是 share-based ledger + odd-lot + 每日 child order + 跨日 `pending_exit`。

```
B0 報酬線 = 由 share ledger 的實際現金流與部位重建的日 NAV 序列
```

**必須附兩層對帳：**(a) 逐筆現金流加總 vs NAV 變動；(b) 部位市值 vs 獨立 PIT 價格快照。**容差與結果隨開封一併報告。**

同理，「判定必須用生產計分碼而非替身」的意圖承接：B0 的對應物是 `SelectionScore`，**不得以任何簡化替身頂替**。

### 9.3 Benchmark ladder（四列，規範性）

| 列 | 內容 | 回答 |
|---|---|---|
| ◆ | B0 策略 | —— |
| ① | B0 eligibility 通過的全母體等權 | **選股能力** = ◆ − ① |
| ② | 同檔數、同換手的隨機選股（N 次中位） | **扣掉交易 footprint** = ◆ − ②，附虛無 p |
| ③ | 0050 買進持有 | **機會成本** = ◆ − ③ |

**理由：** 等權策略開場就欠 0050 約 5.77pp/年，拿單一 0050 當及格線會把「加權方式」誤判成「沒有 alpha」。

**⚠ 四列必須使用同一成本模型（`core/b0_cost_model.py`）**，否則列與列之間不可比。**不得重用 `honest_backtest.py` 的比例成本**（違反 G14-4）。**但不得把 B0 的 trading impact 強行套給 buy-and-hold 基準** —— 成本依各自真實交易事件計算。

### 9.4 L2 primary gate（V-4，凍結）

**`Supported` = 三條 AND：**

1. **net cumulative wealth > 0050 買進持有**（事前凍結，開封後不得更換）
2. **net CAGR > 0**
3. **net `Sharpe_0rf` > 0**

條件 2、3 **不是 alpha 門檻**，只排除荒謬情形（策略虧錢卻因基準更慘而被稱為 Supported）。

**Sharpe 慣例（V-6，凍結）：** `Sharpe_0rf`，`rf = 0`，`CASH_EARNS_INTEREST = False`（保持 NAV 與 Sharpe 經濟一致）。**任何文件不得寫裸的 "Sharpe"** —— 機械強制 `assert_sharpe_named_explicitly()`。

**明文排除：「勝過 Frozen A」不進 gate。** Frozen A 是 historical benchmark / audit comparator，不是勝負對手。B0 夏普 < A 但勝 market 且結構有效 → 仍可 `Supported`（報告須誠實寫出未勝 A）；B0 勝 A 但 < market benchmark → **不得**因此算 Supported。

### 9.5 **M-2 · L2 termination taxonomy（本次凍結新增，規範性）**

```
SUPPORTED
NOT_SUPPORTED
NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK
```

> **資料／重建缺口造成的 deterministic abort，不得判為 `Not Supported`。**

**理由：策略本身沒有失敗，是我們無法知道正確的 NAV。** 判成 `Not Supported` 會記下一個該次執行從未產生的策略判決，並隨即觸發 §1.4 no-post-hoc-rescue —— **等於為了一個資料缺口永久燒掉整個窗口**。

**但：** 這次開封**仍必須記入 opening registry**，不得當作什麼都沒發生。它碰過 sealed window，就算一次有效觀察。

**重跑許可（規範性）：**

| 前次 outcome | 可否同窗重跑 | 合格修復種類（v1.22 R3） | 是否消耗有效觀察 |
|---|---|---|---|
| `SUPPORTED` / `NOT_SUPPORTED` | **永不可** → 新版本 B1/B2，primary evidence 只能是 L3 | — | 是 |
| `NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK` | **僅在合格修復下可以** | `DataRepair` | **是** |
| `NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK` | **僅在合格修復下可以** | `DataRepair` | **是** |
| `RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE` | **僅在合格修復下可以** | `ImplementationConformanceRepair` | **七項條件全部成立時：否**（§9.6a） |

> **兩種 repair 不可互換（v1.22 R3）。** 用 `DataRepair` 去關一個 implementation
> conformance failure，等於把實作缺陷記錄成資料缺陷 —— 正是 §6.1.14 要禁止的替換；
> 而用 `ImplementationConformanceRepair` 去關一個 reconstruction block，
> 等於用改程式碼把缺少的資料來源「補掉」。
> `assert_rerun_admissible` 依前次 outcome **分派 kind**，不接受另一種。

**合格修復的三個條件（全部必要）：**
1. 修復來自**獨立資料來源**，且明確指名
2. **修復方法不看 strategy performance**
3. **修復範圍為整類事件或整個來源，不得依 B0 的暴露挑著修**

> **不得**在發現 B0 剛好持有某檔之後才說「那我們把這檔 corporate action 補一下」—— 那是用組合來選資料。

機械強制：`classify_l2_termination()`、`assert_rerun_admissible()`、`assert_repair_admissible()`、`DataRepair`（五個欄位皆無預設值，不能靠省略宣告為合格）。
**未分類的終止模式不得預設為 `NOT_SUPPORTED`** —— 走 M-3 abort。

### 9.6 開封規則

1. **開封前提：** L1 全部 S-1..S-8 綠燈 **且** 本文件已凍結 **且** provenance 已封存
2. **開封一次。** 同一版規格對同一窗口只評估一次
3. **判定門檻在開封前已凍結**（§9.4），開封後不得修改
4. **全量報告**（§9.7），包含所有失敗項
5. **開封事件入登記簿：** 日期、code commit、spec hash、資料 manifest hash、判定結果

**允許的重跑例外唯二：實作缺陷修復、資料修復**，兩者都必須在不看績效的情況下獨立證明，且**都計入有效觀察次數**。

> **v1.22 修正（R1/R2）。** 上一句的「都計入有效觀察次數」在一個窄情形下被 §9.6a 取代：一次 `RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE`，若七項條件全部成立，**不計入**。這不是放寬重跑條件 —— 重跑仍需合格修復、新 Baseline Seal 與具名新授權；改變的只是**這一次未產生任何策略觀察的嘗試是否要佔掉窗口**。原句對「實作缺陷修復後的重跑本身計入」仍然成立。

### 9.7 Reporting schema（開封時必須全數輸出，缺一項即該次開封作廢）

| 類別 | 必報項 |
|---|---|
| 階梯 | §9.3 四列 + 三個差額 + 虛無 p |
| 成本 | explicit_fee / transaction_tax / impact **三欄分別**的總額與逐期序列 |
| 執行現實 | 換手率；`pending_exit` 次數與跨日天數分佈；under-invested 期數；`zero_sigma_fill` 次數；ADV-cap shortfall 金額 |
| 母體 | 逐期 complete-case 母體數、各 eligibility 層淘汰數 |
| **Corporate action** | 三態逐類型計數；**實際暴露到的 `NOT_RECONSTRUCTIBLE` 事件清單**（即使為空） |
| 容量 | 實現的 `ADV_floor(t)` 路徑與合格檔數路徑 |
| 對帳 | §9.2 兩層對帳的容差與最大偏差 |
| 多重比較 | 有效觀察次數計數 |

### 9.8 Single primary hypothesis（V-2，凍結）

- **formal family size = 1。** 其餘所有指標強制完整報告，但標記 secondary / descriptive，**不各自產生 pass/fail hypothesis**
- **因此不需要 multiplicity correction** —— 這不是迴避多重檢定，而是事前消除「看一堆指標挑最好看的那個」
- **禁止**為 B0 硬湊 DSR `N`。**DSR N=3 已知嚴重低估，明文禁止沿用。** DSR 可作 audit diagnostic，不得作 L2 primary gate
- **Trial registry 永久保存**，角色為「污染紀錄」而非「校正輸入」

> **澄清（不得被日後誤讀）：** V-4 三條以 **AND** 結合，統計上是**單一複合假設（交集）**，不是三次檢定。AND 只會使通過更難（type-I error 更低），不會膨脹。

### 9.9 L3 maturity（V-3 / V-5，凍結）

```
Maturity      = max(36 完整 prospective monthly rebalances, 36 calendar months)
Checkpoints   = 36, 60, 84, 108, 132, ...   (首次 36，其後每 24 個月)
```

- **禁止提前畢業。** 第一次正式 L3 判定 = Month 36
- 證據不足 → **`NOT YET VALIDATED`**（不是 `FAIL`），**不得改門檻**，於下一個凍結 checkpoint 再評
- **checkpoint 之外的月份是 peek，不是 test。** 機械強制 `assert_l3_assessment_allowed()`
- 24 個月間隔**不帶統計意義** —— 它是刻意稀疏而簡單的 stopping policy，用來避免把 optional stopping 從後門放回來
- **L3 不因 L2 成功而縮短**（證據力不對稱）
- **頻率天花板：** B0 月頻，一年僅 12 個觀察，任何以夏普為基礎的判準都需要數年。這是 L3 的固有成本

**Prospective clock 起點（凍結）：** 本文件 + production route + provenance 全部封存後的**第一個 eligible decision date**。**不是「今天開始」。**

---

## §10 機械強制對照表

| 條文 | 強制位置 |
|---|---|
| M-1 pipeline 順序 | `b0_master_prereg.assert_stage_order` / `assert_corporate_action_precedes_mark` / `assert_no_scattered_dispatch` |
| O-A pre-mark mandatory stage | `assert_corporate_action_precedes_mark`（下游任一 stage 出現而該 stage 缺席即 abort） |
| O-B PIT 可觀測性 | `b0_pit_observability`：`PitPriceObservation`（每個日期欄位 `<= as_of`）/ `classify_price_gap` / `assert_no_unexplained_price_gap` / `assert_no_tolerance_policy` |
| O-D 日內順序 | `assert_intraday_order` / `assert_decision_inputs_are_prior_session` |
| O-E 來源合格性 | `b0_market_state`：`SourceContract.assert_pit_safe`（快照即 `NOT_PIT_SAFE`）/ `TradingCalendar.sessions_through`（完整日曆不可達）/ `assert_unknown_is_not_normal` / `market_state_provenance` |
| O-E-1 availability | `StatusRecord.explains_session`（`available_from` 無預設值）/ `classify_price_gap` 的 `_available_before` |
| D-1 存活者偏誤 | `BlockingDataRequirement("price_universe_survivorship")` / `verify_price_universe_churn` |
| M-2 L2 taxonomy | `classify_l2_termination` / `assert_rerun_admissible` / `assert_repair_admissible` / `L2Opening` / `record_opening` |
| M-3 no spec-by-code | `spec()`（無 `default=`）/ `assert_specified` |
| L2 措辭 | `assert_l2_wording` |
| W-1 無門檻無插值 | `MISSING_DATA_RATE_THRESHOLD is None` / `INTERPOLATION_ALLOWED is False` / `assert_no_threshold_policy` |
| W-1 暴露才 abort | `assert_exposure_reconstructible` |
| W-3 handler 覆蓋 | `assert_every_holder_affecting_kind_has_a_handler` |
| W-3 消失守衛 | `assert_no_unexplained_disappearance` |
| W-4 永不認購 | `assert_never_subscribes` |
| O-1 chip 語義 | `assert_chip_semantics` |
| V-5 checkpoint | `assert_l3_assessment_allowed` |
| V-6 Sharpe 命名 | `assert_sharpe_named_explicitly` |
| B-17 / B-19 / G14-4 | `b0_invariants`（靜態 AST，`B0_ENTRY_MODULES`） |
| B-20 parity | `b0_parity`（`float_tol=0.0`，輸入先於輸出） |
| B-21 provenance | `b0_provenance.seal` / `verify_replay`（無 tolerance） |
| G14-1/2/3 | `b0_cost_model`（`execution_confirmed` 無預設值） |

---

## §11 Contradiction / Change Log

**本文件與既有 closure 牴觸之處，逐項列明。未列於此的牴觸視為本文件缺陷。**

### C-1 · Pipeline 順序新增 corporate-action stage
- **來源：** `B06_B12_ImplementationSpec §2`，九步 pipeline 由「Canonical PIT universe」起，**無 corporate-action 階段**
- **變更：** §6.1 插入 `corporate_action_transition`，位於 `portfolio_mark` **之前**
- **理由：** 原 pipeline 成文時 W-1~W-4 尚未裁決，股數變動事件不在模型內。用除權前股數 mark 是靜默 NAV 錯誤
- **相容性：** 原 spec 的所有順序約束（eligibility 早於 ranking、mark 早於 eligibility）在新順序中**完整保留為子序列**，無一被推翻

### C-2 · L2 outcome 由二態擴為三態
- **來源：** `B18_ValidationProtocol_Closure §3.5 / §4.1`，只有 `Supported` / `Not Supported`
- **變更：** §9.5 新增 `NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK`，並規定資料/重建缺口造成的 deterministic abort **必須**判為此態
- **理由：** 二態下，資料 abort 只能被記為 `Not Supported`，隨即觸發 no-post-hoc-rescue，等於為資料缺口永久燒掉窗口 —— 而策略從未被評估過
- **未變更：** `Not Supported` 的 no-post-hoc-rescue 規則本身完全不動

### C-3 · S-3 拆為 S-3a / S-3b
- **來源：** `B18 §6 V-1b`：「在 V-1b 解決之前，L1 的 S-3 不得記為綠燈」
- **變更：** §9.1 拆為 **S-3a 資料語義（SATISFIED）** 與 **S-3b end-to-end enforcement（PENDING B0 route）**
- **理由：** V-1b 的資料/語義 blocker 已由 W-1~W-4 與 `配股相關` 語料關閉，但守衛尚未被任何 NAV 產生路徑呼叫。合併成單一綠燈會把「資料到位」誤讀為「已強制執行」

### C-4 · V-1b 驗證器的「滿足」定義改變
- **來源：** `B18 §6 V-1b`，原意為來源必須完整
- **變更：** §2.4 W-1 下，來源的合格條件為**語義充分且逐列自我分類**，**不是無缺口**；缺口在**暴露時**才 fail
- **理由：** 見 §11 C-5 的門檻教訓
- **未放寬的部分：** 缺欄位、除權日不可解析、可交易日早於除權日**仍然**在來源層 fail

### C-5 · 撤回「以缺失率門檻處理資料缺口」的構想
- **來源：** `V1b_StockDividend_Verification §4`，曾列選項 (a) 比照 AC-R5-1b 訂全窗口/單期門檻
- **變更：** §2.4 明文不存在 `MISSING_DATA_RATE_THRESHOLD`
- **理由（實例證據）：** 初盤點缺可交易日為 65/2,488 = **2.61%**；完整語義盤點後，配股類不可重建為 377/2,800 = **13.5%**。若當初訂了「< 3% 即忽略」，第一輪會「合法通過」，完整資料一到立刻破線。**這是門檻在資料結構未知時的危險實例。**

### C-6 · 撤回 B-14 的「下界」主張
- **來源：** `B14_CostModel_Closure_Phase1 D14-1` 初稿曾稱建模成本為下界
- **變更：** §7.6 明文**不得宣稱偏誤方向**
- **理由：** `IMPACT_K = 1.0` 是 order-one 外部先驗，proxy 可能高估也可能低估；「少建模幾項摩擦」推不出「總和必然偏低」

### C-7 · 撤回 B-14 Phase 1 的制度性敘述
- **來源：** 初稿引用非權威來源，稱 0.1425% 為法定上限、NT$20 為法定最低
- **變更：** §7.1 標註 `MIN_FEE` 為**券商政策非法定**；`COMMISSION_RATE` 為 B0 reference rate
- **理由：** 現行 TWSE 規則下券商可自訂費率。**方法層教訓：非權威來源不得用於決定性結論。**

### C-8 · `rev_accel` 的同名不同式已更正
- **來源：** `B09 Phase 1` 曾標為「Q6 ≡ M5 同一因子」
- **變更：** §2.1 綁定因子明確為 **A 腿定義**（需 6 個 YoY，L=18）
- **理由：** Phase 2 逐行讀後確認為同名、同概念、**不同公式**（B 腿需 3 個 YoY，L 會降為 16）

---

**以下為 v1.1（P-1a Pre-Implementation Closure）新增。**

### C-9 · Pipeline stage 由 9 個細分為 11 個（P-1a）
- **來源：** 本文件 v1.0 §6.1，`pit_market_state / corporate_action_transition / portfolio_mark / eligibility / ranking / orders / execution / costs / nav`
- **變更：** `ranking` 拆為 `features` + `selection_score` + `target_portfolio`；`orders` 更名 `order_intents`；`pit_market_state`→`pit_raw_state`；`nav`→`post_trade_nav`
- **理由：** 使 stage 清單與 §8.7 四層模組責任一對一對應。`b0_features` 不得知道 Top20，`b0_decision` 不得重做 feature 公式 —— 若 stage 停在單一 `ranking`，這條邊界在 stage 層無法檢查
- **相容性：** v1.0 的所有順序約束**完整保留為子序列**，無一被推翻

### C-10 · O-A 由「排序推論」升級為「獨立必要條件」
- **來源：** 本文件 v1.0 §6.1，只要求 transition 早於 mark
- **變更：** §6.1 規定任一下游 stage 出現而 transition 缺席即 abort
- **理由：** **完全跳過該 stage 的執行會 trivially 通過排序檢查。** 原條文擋得住「順序錯了」，擋不住「根本沒做」

### C-11 · O-B 移除 `assert_no_unexplained_disappearance`，改為 PIT 可觀測性守衛
- **來源：** `W1_W4_CorporateAction_Closure §3.2` 與本文件 v1.0 §2.4 守衛 2，簽章為 `(held, last_price_date, explained)`
- **變更：** §2.6 全新語義；舊函式**移除而非修補**，`core.b0_corporate_actions.HOLDER_SIDE_DETECTOR` 改指向 `core.b0_pit_observability.assert_no_unexplained_price_gap`
- **理由：** `last_price_date` 是 global lookup —— 站在 2019-05-01 問「這檔最後交易日是哪天」，只能用 2019-05-01 之後的資料回答。**look-ahead 編碼在簽章本身**，修補會留下同樣的入口
- **同時放棄的宣稱：** 「永久消失」不再是本規格的概念。B0 只判定「截至今日無法解釋」，該判定可隨更多 session 改變
- **未變更：** 守衛要防的失效完全相同 —— 消失的持股被當成 price missing → zero/drop → NAV 靜默錯掉

### C-12 · O-D 日內順序由 UNSPECIFIED 轉為凍結
- **來源：** 本文件 v1.0 §12 O-D，列為 open item
- **變更：** §6.6 凍結七步日內序列 + `DECISION_STATE_SOURCE` + 兩個 credit event
- **理由：** 月頻 decision date 可能落在 corporate-action date；未固定順序時同一天可產生不同 NAV
- **未新增：** 執行價格語義沿用 §6.5 `open(t+1)`，O-D **不重新創造**一套 timestamp 規則

### C-14 · O-B 欄位改名並套用 O-E-1 嚴格性（v1.2）
- **來源：** v1.1 §2.6，欄位為 `known_status_as_of` / `corporate_action_effective`，且只要求 `<= as_of`
- **變更：** 改名為 `status_available_from` / `corporate_action_available_from`；解釋條件收緊為 `available_from < first_missing_session`
- **理由：** O-E-1。原欄名描述的是「生效日」，而需要的是「可得日」；盤後申報的狀態帶當天日期，用它解釋當天缺價是 look-ahead
- **後果：** 原本會被判 `EXPLAINED_SUSPENSION` 的邊界情形改判 `UNEXPLAINED_GAP`（更容易 abort，方向為 fail-safe）

### C-15 · 新增 D-1 blocking data requirement（v1.2）
- **來源：** v1.1 §9.1 記 S-3a = SATISFIED
- **變更：** §2.8 新增 D-1；S-3a 改為 **BLOCKED by D-1**；`final_provenance_seal` 與 `L2_opening` 一併阻擋
- **理由：** O-E 的來源稽核發現價格 export 在 2019+ 只含存活證券（六年零下市；90 檔中 74 檔有 2018 後獨立存在證據）。這不是 O-E 的範圍，是 §2 canonical data 的缺陷
- **未變更：** V-1b 自身仍為 CLOSED。**兩者是不同的 requirement，不得合併敘述為「資料 blocker 已全解」**

---

**以下為 v1.3（P-1b canonical core 實作）新增。五項全部是 master omission correction —— 語義既有，本文件漏抄。**

### C-16 · Target drift policy 補回（v1.3）
- **來源：** 本文件 v1.0 §5 只寫 `w_target = w_max = 5%（每檔固定）`，未說 5% 是每期重設的目標還是建倉上限
- **變更：** §5.1 明定每個 decision date 以 `order_delta = target_shares − current_shares` 重設回 5%
- **理由：** B-06 / B-12 implementation spec 已將 `compute_order_intent` 定為固定 `w_target = 5%`；B-14 明文把續留標的描述為漂移後產生小額 delta rebalance。**兩種讀法是兩個不同策略共用一份規格**，而換手率、整條成本線與階梯第 ② 列都由它決定
- **未變更：** 所有 execution 約束（sell-first、no-leverage、1% ADV、pending_exit）原樣適用

### C-17 · PEG 定義補回（v1.3）
- **來源：** 本文件 v1.0 §3.1 只列 `PEG` 為 Value 成員，無公式、無定義域
- **變更：** §3.5 定為 `PER_TSE / eps_growth(百分點)`，定義域 `PE > 0 ∧ growth > 0`，否則 NA
- **理由：** B-09 保留的是 standard PEG（方向為負）。正值定義域是該量的語義而非門檻：允許負值會讓 `PE=−10, growth=−20%` 產生 `PEG=+0.5`，在排序上偽裝成便宜的成長股
- **隨附揭露：** 造成隨景氣變動的條件性母體缺失，§9.7 必報涵蓋率，**不得據以調規格**

### C-18 · eps_growth 定義補回（v1.3，含 lineage 查核）
- **來源：** B-09 將 `eps_cagr` 更名 `eps_growth`，公式未帶進本文件
- **變更：** §3.5 定為 `(EPS_t − EPS_{t−4}) / |EPS_{t−4}| × 100`，單位百分點
- **理由：** horizon 來自 B-09 Phase 3「季 YoY」；分母絕對值與 ×100 來自逐行 lineage —— `eps_cagr` 從來不是 CAGR，其產生點為 `core/data_provider.py::_yoy_growth`
- **明文不沿用的兩項：**（a）legacy 的「距 365 天最近且 ±60 天內」比對 —— **±60 天是落在 Selection 路徑上的容差參數**，與 S-1 相斥，而 B0 有季別索引；（b）`if eps_growth is None: eps_growth = net_income_growth` —— **以另一序列替代缺值即插補，§4.1 已禁止**，且會讓兩個量共用一個名字（§11 C-8）

### C-19 · Feature 方向補回（v1.3）
- **來源：** 本文件 v1.0 §3.1 未載任一成員的方向
- **變更：** §3.5 補上十一個成員的方向；`debt_to_asset` 與 `PEG` 為「越低越好」
- **理由：** B-09 Phase 1 的 `方向` 欄早已明定（F7 `−`、F8 `+`、V2 `−`、Q2 `+`），凍結時未抄。**方向錯誤不產生雜訊，是把整個 concept 反轉**，且下游無法偵測
- **附帶收緊：** 方向綁定於 feature 定義，計分入口不接受方向參數 —— 可由呼叫端指定的方向就是一個 runtime 自由度

### C-20 · F10 relocate 與 S-1 措辭更正（v1.3）
- **來源：** 本文件 v1.0 §4.4 僅寫「solvency / 資料品質 hard filters」；§9.1 S-1 記為 `✅ FROZEN`
- **變更：**（a）§4.4 明定處置為 **relocate 既有 predicate、不重新選門檻**，並凍結唯一無條件的一腿 `net_margin < −10`；（b）其餘三腿列為 §12.2 open item；（c）S-1 措辭改為「runtime tunable 自由參數 = 0」並降為 `PENDING`
- **理由：** B-09 Phase 1 對 F10 的裁決是 `Relocate`，不是 Remove，故門檻是**繼承**而非**挑選**。但逐行讀 legacy predicate 發現它不是四個門檻，而是**六個常數 + `is_financial` 豁免 + 一腿無 producer**（`cash_quality` 全庫無任何寫入點，從未觸發）。**照摘要凍結會凍進一個與實際 predicate 不同的東西**
- **S-1 的更正理由：** 原措辭若讀成「不存在任何數值常數」則永遠為假（§7.1 成本常數即是），並會誘使施工方為維持綠燈而隱藏常數。改為區分 **frozen inherited constants** 與 **runtime tunable parameters**

---

**以下為 v1.4（A/B/C resolutions）新增。七項同樣全部是 omission correction，無一為新的策略選擇。**

### C-21 · Quality TTM 三項公式補回（v1.4，含來源衝突揭露）
- **來源：** 本文件 v1.0 §3.1 只列 `roe` / `net_margin` / `gross_margin` 為 Quality 成員，無公式
- **變更：** §3.5 定為 TTM；ROE = 四季淨利總和 / 期末權益 × 100；margin = 四季利潤總和 / 四季營收總和 × 100
- **🔴 來源衝突（本輪唯一一個）：** B-09 Phase 3 §5 列「Quality TTM」回看 13，但 legacy producer `core/data_provider.py:628-636` 實作單季，其自身註解寫「近似 ROE(單季)」。**依 §0.2 precedence（closure prose > legacy code），採 TTM。** 衝突逐項記錄於此而非淡化
- **closure 未指定而由 lineage 決定者：** 期末權益分母、百分點單位
- **標準定義決定者：** margin 為「總和除以總和」而非四個季比率的平均 —— 後者沒有人稱之為 TTM margin
- **與 C-17 同一原則：** `equity ≤ 0 → NA`

### C-22 · 當期資產負債表兩項補回（v1.4）
- **來源：** v1.0 §3.1 未指定 `debt_to_asset` / `current_ratio` 取哪一期
- **變更：** §3.5 定為時點存量比率，取**公告日 ≤ decision date 的最新一份報表**
- **理由：** B-09 Phase 3 §5 單列為「Quality 當期(負債比/流動比)」回看 4，與 TTM 三項分開；「當期」指哪一份已由 §2.2（真實公告日、禁止固定 lag）決定

### C-23 · revenue_yoy 定為單月 YoY（v1.4）
- **來源：** v1.0 §3.1 只列成員名
- **變更：** §3.5 定為單月 YoY
- **理由：** **回看期本身即為決定性證據** —— B-09 Phase 3 §5 給 13 個月，`13 = 1 + 12`；三月均需 15。以三月均構成的成員是 `revenue_accel`（§2.1 給 18）

### C-24 · 12-1 momentum 定為價格報酬（v1.4）
- **來源：** v1.0 §3.1 寫 "12-1 price momentum"，未定端點與是否含息
- **變更：** §3.5 定為 `(P_{t−1}/P_{t−13} − 1) × 100`，價格報酬，輸入須已依 §2.4 調整股數事件
- **理由：** 成員的凍結名稱即含 "price"；標準構造為價格相對量。**§2.5 的含息要求管的是 NAV 與基準構造，不延伸到排序訊號** —— 該條的理由是「排除股利會低估 NAV 與基準」，對 feature 不成立

### C-25 · ADV20 定義補回（v1.4，lineage）
- **來源：** v1.0 §4.2 / §6.4 / §7.1 三處使用 `ADV20`，均未定義
- **變更：** §7.1.1 定為「最近 20 個**已觀測** session 的成交金額均值」，不足 20 → NA
- **理由：** lineage —— `universe_screen_daily.py:165` 與 `universe_screen_backfill.py:58` 皆為 20 日成交金額均值。「已觀測」而非日曆日與 O-E 的交易日曆處置一致
- **為何不縮窗：** 縮窗會恰對 §4.2 要剔除的標的偷換度量；§4.2 已裁定缺流動性觀測為證據不足

### C-26 · σ20D 定義補回（v1.4）
- **來源：** v1.0 §7.1 使用 `σ20D` 卻未抄它的定義
- **變更：** §7.1.1 照 **B-14 P3 原文**補回：「trailing 20 交易日 log return 標準差，PIT、未年化」
- **理由：** B-14 §3.2 的凍結參數表早已定案並明載「P3」。**這是本文件漏抄，不是未裁決**
- **唯一新增的揭露：** B-14 P3 未指定標準差自由度；本文件採 ddof = 1 並具名於 `SIGMA20D_DDOF`，與 ddof = 0 相差 `√(20/19) ≈ 1.026` 倍

### C-27 · pending_exit cap 基準補回（v1.4）
- **來源：** v1.0 §6.4 只寫「每日 1% ADV20 cap、殘額按日 carry forward」，未說殘量對哪一天的 ADV20 設 cap
- **變更：** §6.4 明定為**執行當日自身的 ADV20**（以前一收盤為準）
- **理由：** 由 §6.4 與 §7.3 並排即可推出（§7.3 已規定每日各自用當日 pre-execution 輸入）。固定在首日 ADV20 會讓流動性崩壞的標的以舊容量繼續賣出

---

**以下為 v1.5（最後 7 個 D 項 + σ20D ddof）新增。與 C-16 ~ C-27 不同，這批是真正的裁決，不是漏抄補回。**

### C-28 · σ20D 標準差自由度 = 1（v1.5）
- **來源：** B-14 P3 定義 σ20D 為「trailing 20 交易日 log return 標準差，PIT、未年化」，未指定自由度
- **變更：** §7.1.1 補上 `ddof = 1`（樣本標準差）
- **性質：explicit specification completion，不是 runtime tunable。** `SIGMA20D_DDOF` 為常數，無呼叫端可改
- **量級：** 與 ddof = 0 相差 `√(20/19) ≈ 1.026` 倍，線性作用於 impact

### C-29 · 移除金融業豁免（v1.5）
- **來源：** legacy `core/fundamentals.py:279-293` 讓 `is_financial` 同時豁免流動比下限與負債上限
- **變更：** §4.4 `RISK_FINANCIAL_EXEMPTION = False`，B0 不新增任何 `is_financial` 特例路徑
- **第二個理由（非僅裁決）：** 豁免需要 decision date 當下的產業歸屬，而 §2.3 已證 `industry_map` 為當期快照、49.4% 股票換過產業。**以今日產業表解析豁免會把 look-ahead 放進 eligibility 閘**
- **機械強制：** `assert_no_sector_exemption()`

### C-30 · 移除 legacy 負債 hard-filter 條件樹（v1.5）
- **來源：** legacy `debt_to_asset > 85` 條件樹，含 `92` / `current_ratio < 100` / `net_margin < 0`
- **變更：** §4.4 不保留該 predicate 的任何部分；`debt_to_asset` **只保留為 Quality 中 lower-is-better 的連續 Selection feature**（C-19），不另作 debt hard exclusion
- **後果（已揭露）：** 高槓桿但獲利的標的不再被硬性剔除，改為在 Quality 百分位上受懲罰。這是連續處理取代離散門檻，與 §3.1「人工切點 = 0」一致

### C-31 · 移除 cash_quality 腿，且不得 alias（v1.5）
- **來源：** legacy `cash_quality < 0.5`；lineage 查核確認**全庫無任何 producer**，該腿從未觸發
- **變更：** §4.4 移除；**明文不得 alias、不得改掛 `ocf_to_net_income`**
- **理由：** `ocf_to_net_income` 是另一個量 —— 淨利為 0 時無定義、為負時變號，`< 0.5` 在該區間語義相反。採用它是定義新 filter 而非 relocate
- **機械強制：** `assert_no_cash_quality_alias()`

### C-32 · 現金不足時買單依 Selection rank 填滿（v1.5）
- **來源：** §6.4 禁止預支未成交價金且禁止負現金，保證現金不足會發生，但未定順序
- **變更：** §6.4 買單按 Selection rank 由高到低，每檔受 target shortfall / 1% ADV cap / available cash 三者限制；**不得 proportional scaling**
- **理由：** 等比例縮放會把現金不足悄悄轉成權重決定 —— 20 檔各 4% 與 16 檔各 5% + 現金是兩個不同組合，§5 已決定 B0 是哪一個
- **已揭露的實作讀法：** 某檔完全買不起時跳過續往下，而非中止迴圈

### C-33 · SelectionScore 平手以 stock_id ascending 決定（v1.5）
- **來源：** §5 `len(selected) = min(20, ...)` 精確，但未定平手規則
- **變更：** §5.0 canonical sort key = `(−SelectionScore, stock_id ascending)`
- **明文禁止：** 市值、ADV、其他 alpha 作為次級鍵 —— 每一個都是第二個未登記的選股訊號，且**因為看起來像排序細節而永遠不會出現在自由參數計數裡**
- **機械記錄：** `FORBIDDEN_TIE_BREAK_KEYS`

### C-34 · 股數取整 = floor 至 1 股，5% 為 hard cap（v1.5）
- **來源：** §6.3 定 canonical unit 為股、odd-lot enabled，但未定取整方式
- **變更：** §6.4 `target_shares = floor(target_value / reference_price)`；**`w_max = 5%` 為對已執行部位的 hard cap**；取整餘額留 cash
- **理由：** nearest 可能讓高價股超過 5% 上限達半股價值。這同時回答了 v1.3 留下的問題「w_max 是對 target 還是對已執行部位」—— **是後者**

### C-35 · Feature 百分位平手取平均名次（v1.5）
- **來源：** §3.1 只寫「連續橫斷面百分位」
- **變更：** §3.1 補上 average rank；相同 raw value 得相同 percentile；結果不依賴 row order
- **理由：** ordinal 必須以 row order 或 stock_id 打破平手 —— 前者使輸出隨 adapter 而變（擊穿 B-20），**後者會把 C-33 的組合層 tie-break 回流到 feature 計分**，讓證券因代號小而獲得 alpha
- **機械強制：** 依 value 分組而非依 `(value, stock_id)` 排序

### C-36 · 移除 current-ratio 下限，風險層定案（v1.6）
- **來源：** v1.5 §12.2 將 `current_ratio < 50` 登記為 UNSPECIFIED（C-29 移除了守著它的豁免，但無任何條文說該下限本身存廢）
- **變更：** §4.4 移除該下限；`current_ratio` **只保留為 Quality 中 higher-is-better 的連續 Selection feature**
- **明文否定的推論：** **不得把「移除金融業豁免」重新詮釋為「legacy `<50` 規則變成全產業無條件適用」。** 移除一個 carve-out 與保留它所 carve out 的規則是兩個不同的決定，本規格只做了第一個
- **後果：** B0 最終的基本面 hard risk filter 只有 `net_margin < −10` 一條。兩個 balance-sheet 比率改由 Quality 百分位連續承接 —— 與 §3.1 把人工切點降為 0 的方向一致
- **隨附揭露（非歧義）：** 該門檻的輸入已由 C-21 改為 **TTM** 淨利率；legacy 的 `−10` 作用在單季上。B0 只有一個 `net_margin`（§3.5），故讀法唯一，但**單季與 TTM 剔除到的公司不同**
- **機械強制：** `RISK_LAYER_COMPLETE = True`；`assert_no_removed_legacy_leg()`；S-1 轉綠並由 `assert_selection_path_is_fully_specified()` 檢查

---

### C-37 · 宣告 B-20 route pair，§8.7 由 pending 轉為已實作（v1.7）
- **來源：** v1.0 §8.5 記 `B0_ROUTE_PAIRS = ()` 且「空 = 不得宣告 parity」；§8.7 記「⚠ 尚未實作」
- **變更：** 宣告 `("core.b0_adapter_production", "core.b0_adapter_retrospective")` 並附 deterministic fixture；§8.7 改為已實作
- **性質：狀態變更，非語義變更。** 沒有任何策略條文被改動；四層的責任邊界原文照舊
- **附帶收緊：** §8.7 的「不得重新實作」由散文升級為機械檢查 —— adapter **不得 import 任何 canonical layer**，且不得呼叫任何策略語義入口點（AST，`tests/test_b0_adapter_parity.py`）
- **未變更：** 「宣告 pair 卻無 fixture 即失敗」的規則保留，且 `tests/test_b0_parity.py` 的對應測試已改為**要求 fixture 存在**而非要求 pair 為空

---

### C-38 · D-1 驗證改為跨來源，判準只增不減（v1.8）
- **來源：** v1.2 §2.8，驗證器僅有 source-only 的 `verify_price_universe_churn()`
- **變更：** §2.8.1 新增獨立參照（公司資料的歷史上市日欄位）與兩個 structural-impossibility gate（C1/C2）；§2.8.2 新增 quarantine 與 `includes_delisted` 閘
- **理由：** 原驗證是自我參照的 —— 用 corpus 自己的 churn pattern 判斷 corpus。它偵測得到污染，但**無法定量**，也無法在不讀污染資料的情況下說出缺了什麼
- **⚠ 沒有放寬任何條件：** 原 source-only 驗證器完整保留為 backstop，新舊**必須同時通過**。本 corpus 在新舊兩套下都 FAIL
- **未變更：** D-1 仍為 UNMET，S-3a 仍 BLOCKED。`公司資料` 為 audit-only，永不進 B0 runtime

### C-39 · D-1 關閉；C2 與 backstop 兩處判準缺陷修正（v1.9）
- **來源：** v1.8 §2.8.1，C2 = 「群聚日當天參照無下市」；`verify_price_universe_churn` 的第二條 = 「交易到年末後消失 > 0 即 FAIL」
- **變更：** C2 改為「群聚中 **無法解釋** 的終止 ≥2」；backstop 第二條降為報告項，只保留 structural 的「零流出年份」為 gate
- **理由（兩者皆為判準缺陷，非為新資料放寬）：**
  - C2：下市日在定義上**晚於**最後交易日（常為隔日，長期停牌後可達數月），所以「當天無下市」是乾淨資料的**常態**。實測誤報：`2018-09-17` 六檔最後交易日 09-17、`delisted` 狀態 09-18 生效、正式下市 2018-10-01 —— 完全自洽卻被判 FAIL。舊資料當時也誤報，只是被 `2018-12-28` 的真陽性掩蓋
  - backstop：`dropped_but_traded_to_year_end` 在任何真實 corpus 上每年必然 ≥1（交易到 12/31、隔年 1 月初下市者）。實測 16 筆**全部**有參照下市日落在其下一個 session 上或數日內。`>0 → FAIL` 不是 gate 而是永久封鎖
- **⚠ 修正後仍失敗於舊 corpus：** C2 於 `2018-12-28`（unexplained=54）觸發；backstop 於 2019–2025 七個零流出年份觸發。**沒有任何條件被放寬到讓舊資料通過**
- **未變更：** C1、quarantine、`includes_delisted`、規模只報告不設閘

### C-40 · O-F 狀態來源改版與 PIT audit；O-F 仍 OPEN（v1.10）
- **來源：** v1.9 §12.2 O-F，證據為「as-of 2020-06-29 全母體掃描 12 + 7」
- **來源更換：** `暫停交易2004-20260806`（xlsx，已由使用者刪除）→ `暫停交易2004-20260818`（六個分期 zip，UTF-16 TSV，1,950 列 / 1,046 檔 / 2004-01-12 .. 2026-08-18）+ 同資料夾的 `事件+下市.zip`（2,440 檔，含 `危機發生日` 與 `下市日期`）。importer 版本 `b0_market_state_importer@2`。舊 vintage 的 raw hash 從未記錄，**不要求舊檔重新存在**；其 derived artefact 的量測值保留為 audit trail
- **⚠ 前次證據被上修，原因是量測代理有缺陷：** 舊診斷以 `price_observed_through = min(series_last, as_of)` 近似，這讓任何在 as_of 之後仍有價的證券**必然**被判為 CURRENT，而唯一會被標記的只有「最終價格日早於 as_of」—— 一個 as_of 之後才知道的事實。O-F 改為讀 session 級 presence index（`data/b0/price_presence.parquet`，9,130,763 列 / 2,306 檔，與註冊價格來源同一 vintage boundary）。**12 + 7 → 289**（同一 as_of、同一 production classifier）。這是量測修正，不是資料變壞
- **三個 audit（皆非 gate，皆為診斷）：** A as-of 快照（2020-06-29，UNEXPLAINED 289）；B 全 corpus 終止缺口（352 中 286 無解釋）；C 內部缺口（119 段中 115 無解釋，涉 96 檔）
- **`暫停交易` 語義實測（O-E 要求證明而非宣告）：**
  - `年月日` 是 **effective date 而非公告日**：1,658/1,950（85.0%）在該日仍有價
  - `恢復交易日` > `年月日`：1,947/1,948；1 筆相等
  - **58.9% 的列（減資／現金減資／面額變更，1,148 列）其宣告區間內 1,135 筆完全有價** —— 這些列描述的是停止過戶期間，**不是停牌**。目前 importer 一律標 `suspended`，屬 over-claim；因區間內無缺價，實測**無害**，但語義錯誤已登記
  - **無任何 availability 欄位**：`available_from` 只能用宣告，O-E-1 因此是唯一的界限
- **`事件+下市` PIT 判定（供裁決用，未提升為 runtime source）：**
  - 形狀為**每檔一列、無 record-level effective date** → SHAPE 是當期快照
  - 匯出日 2026-08-18 之後仍有 2 筆 `下市日期`（`2867` 2026-09-01、`5371` 2026-09-03）→ **證明 TEJ 在事件前就已建檔**，但表中不含前置時間長度
  - `下市日期` 相對首個缺價 session：**之前 4 / 同日 94 / 之後 188**。作為 `available_from` 在最需要它的地方失效
  - `危機發生日` 嚴格早於首個缺價 session：58/286；118 檔根本沒有危機日
- **內部缺口的二分（P-6，audit C 的 115 段）：** **27 段是離場後再上市**（母表 `listed_from` 晚於缺口起點，例：`8102` 2005-08-31 斷、2023-10-27 重新上市），期間交易所本來就不預期它有價；**88 段是真正的在市中缺口**（長度 2 .. 842 個 session），這才是 O-B 在持倉存續期間會遇到的情形
- **⚠ `事件+下市` 與 `公司資料` 對「再上市」證券的歷史抹除：** 27 檔再上市證券中，**只有 2 檔**在事件表留有 `下市日期`，其餘 25 檔的 `下市日期` 與母表 `delisted_on` **皆為空**。兩表都是每檔一列的當期快照，證券回來後前一段上市歷程被覆寫 —— 與 `上市別`、`industry_map` 同一類缺陷。**這些早期離場只有價格 corpus 記得，任何已註冊來源都不記得（PIT 與回溯皆然）**。D-1 未被推翻：D-1 只檢查終止日，內部缺口不在其視野內
- **裁決選項矩陣（實測殘留，非建議）：** 現況 286；只放寬 O-E-1 同日 → 100；只採 `危機發生日` → 228；只採 `下市日期 ≤ 首個缺價日` → 188；O-E-1 + 危機日 → 74；三者全開 → 2
- **未變更：** O-E-1 原文、O-B 分類器、`暫停交易` 的 status 推導規則、D-1 判準。**O-F 未裁決，仍 OPEN，仍擋 S-3b**

---

### C-41 · O-E-1 維持嚴格；O-F 以 incomplete-source / fail-loud 關閉（v1.11）
- **來源：** v1.10 §12.2 O-F 為 OPEN，且擋住 S-3b
- **O-E-1 不變：** `available_from < first_missing_session` 原文保留。**同日事件在沒有獨立 availability 證據前不得改判為 explained** —— 這正是 C-40 選項矩陣中「只放寬同日規則」可買到 286→100 的那一項，**未採用**
- **O-F 關閉語義（不是「缺口被補上」，是「缺口被正確處理」）：**
  - 有 PIT-safe 狀態 → `EXPLAINED`
  - 首個缺價 session 無 PIT-safe 狀態 → `UNEXPLAINED / UNKNOWN`
  - **B0 未持有該證券 → 單憑此事不 abort 組合路徑**
  - **B0 在缺口發生時持有 → fail-loud**
  - 當期快照的 `下市日期` 維持 **audit-only 且 runtime 不可達**
  - 不得插補、不得由未來下市反推、不得因涵蓋率放寬判準
  - **O-F 的關閉不要求 unexplained 計數為 0**
- **實作變更：** `assert_no_unexplained_gap_in_holdings` 取代 route 上直接呼叫的 `assert_no_unexplained_price_gap`。舊寫法把所有 observation 都交給 guard，於是「來源不完整」看起來像「路徑失敗」—— 前一輪的真實資料驗證就踩過這個，把全母體丟給 guard 後把 abort 讀成 route 缺陷
- **機械化：** `AUDIT_ONLY_MODULES` / `AUDIT_ONLY_SYMBOLS` 以 AST import-closure 檢查 `下市日期`、`公司資料`、`load_master`、`delisted_on` 從 12 個 B0 entry module **不可達**
- **未變更：** O-B 四態分類、O-E-1、W-1 暴露閘、D-1 判準

---

### C-42 · 暫停交易事件語義分類；未知語義 fail closed（v1.11）
- **來源：** v1.10 C-40 實測 —— 1,148 列減資／面額變更中 **1,135 列的宣告區間內完全有價**，那是停止過戶期間不是停牌；importer 卻一律標 `suspended`
- **規範對照表（normative；`core.b0_market_state` 為實作，本表為規格）：**

| 語義 | 判定關鍵字（依序） | 可產生的 status | 20260818 vintage 列數 |
|---|---|---|---:|
| `LISTING_TERMINATION` | 下市 / 終止 / 併入 | `delisted` | 167 |
| `BOOK_CLOSURE` | 減資 / 面額變更 / 停止過戶 | **無**（不得解釋缺價） | 1,148 |
| `TRADING_SUSPENSION` | 暫停・停止交易・停止買賣・櫃檯買賣・違規・重整・緊急處分・禁止轉讓・重大訊息・重大事項・重大消息・股價敏感・待公布・待公佈・之查證・停工・內部控制・內控・營業細則・章則・業務規則・25%・自行申請・輔導・股務代理・股務・法院裁定・營運資金 | `suspended` | 605 |
| `UNKNOWN` | 以上皆非 | **無**（fail closed） | 30 |

- **順序有意義：** `合併下市` 是終止不是停牌；`現金減資` 是停止過戶不是停牌
- **fail closed 的意思：** 不產生 StatusRecord，因此**永遠不會解釋任何缺價**。**不得**因為它出現在「暫停交易」匯出裡就升格為 `suspended`
- **實測後果（誠實揭露，方向是收緊）：** status 表 3,708 筆 / 1,046 檔 → **1,375 筆 / 566 檔**；1,178 列 fail closed。audit B 無解釋終止 286 → **293**；D-1 security-level 無解釋終止 2 → **3**（`3126`，原本由一列現已判為非停牌的紀錄解釋）。D-1 的 C1／C2／backstop 與 known-case 98/98 **全部不變**，`price_universe_survivorship` 仍 SATISFIED
- **importer 升版：** `b0_market_state_importer@2` → `@3`

---

### C-43 · O-G · canonical listing spell（v1.11 開立並關閉）
- **來源：** v1.10 C-40 P-6 —— 27 檔證券離場後再上市，其中 25 檔的先前離場在事件表與母表**皆已被抹除**，只有價格 corpus 記得
- **不變式：**
  - 無法解釋的缺價 + 之後重新出現 → 於**首個重新觀測到的 session** 開始新的 canonical listing spell
  - **被解釋的缺口不切斷 spell**（停牌是一段上市之內的中斷）
  - 由價格導出的歷史**不得跨 spell 銜接**
  - `ADV20` / `sigma20d` / 動能等價格回看**於新 spell 重置**；新 spell 歷史不足 → **NA / complete-case**（§3.3 既有路徑）
  - 原消失日若當時無 PIT-safe 狀態且策略持有 → **既有暴露閘照樣 abort**
  - **不得以未來的重新出現回頭解釋原本的消失**（`assert_disappearance_not_explained_by_return`）
- **零自由參數：** `SPELL_BRIDGING_SESSION_TOLERANCE = None`。「缺口短於 N 個 session 仍算同一段上市」就是 O-B 拒絕過的 stale-mark 容忍度換一個模組住
- **route 接線：** `CanonicalDecisionInput.listing_spells` 進入 `state_payload`（兩個 route 對 spell 起點不一致就不是同一個 state）；`assert_price_lookbacks_reset` 在 route 上、`assert_spells_declared` 在兩個 adapter 上（非 synthetic 才要求）
- **真實資料驗證：** 27 檔全部導出 `reappearance` spell，起點與母表 `listed_from` **完全一致**（`8102` 2023-10-27、`3135` 2021-11-22、`8089` 2018-08-31、`6606` 2020-01-09、`4749` 2022-02-15）—— 兩個互不相干的來源給出同一個日期。2020-06-29 的 20 檔持倉中亦有 **1 檔**已是 `reappearance` spell
- **`state_hash` 變更：** `56d42ca0…81f13be` → `d7017180…7fef204`。`config_hash 27fee343…d13f03` 不變

---

### C-44 · S-3b 準則改為 enforcement，並判定 SATISFIED（v1.11）
- **來源：** v1.0 §10 S-3b「PENDING（真實資料 E2E）」，隱含準則是來源完整
- **變更：** S-3b = **enforcement**，不是 universal source completeness。新增 blocking requirement `security_status_guard_enforcement`（blocks `S-3b`）
- **理由：** 來源不完整是 O-F 已裁決的既成事實（293/352 無 PIT 解釋，且唯一認得它們的表是會改寫自身歷史的當期快照）。要求 0 等於要求一個永遠達不到的條件，而達不到的條件會被略過不讀
- **四個性質，全部由 verifier 實際執行 production guard 得出，不讀任何 flag：**
  1. `pit_safe_status_explains` —— 真實證券 `4762`，`delisted` 於 2017-02-20 可得 → `EXPLAINED_SUSPENSION`
  2. `held_unexplained_gap_aborts` —— 真實證券 `1107`，持有 → abort
  3. `unheld_unexplained_gap_does_not_abort` —— **同一個 observation**，未持有 → 不 abort
  4. `all_routes_invoke_the_guard` —— AST：route 呼叫 exposure-scoped guard，且**沒有任何 route module 直接呼叫**未 scoped 的版本
- **fixture：** `data/b0/s3b_guard_fixture.csv`，由 O-F audit 挑名（非人工 pass list），不含任何價格水準、不含選股、不含績效
- **⚠ 判定範圍：** S-3b 現在斷言的是「guard 在兩側都正確動作」。它**不**斷言母體無缺口，也**不**等於 L2 或 final seal 的許可
- **未變更：** S-3a、D-1、final seal 條件、L2 開封條件

---

### C-45 · F-0 · Config / Spec hash boundary audit（v1.12；scope 仍 UNSPECIFIED）
- **觸發：** v1.11 回報的 `config_hash = 27fee343…` 與 v1.10 相同，但 O-F / O-G 改了 production-reachable 行為
- **⚠ 首先更正一個回報錯誤：`config_hash` 其實有變。** HEAD 為 **`40375c34…2e9a012d`**。`27fee343…` 是在 13 個 O-F/O-G key 加進 registry **之前**跑的驗證留下的值，事後未重測。**機械證明：** 從 HEAD registry 移除且僅移除那 13 個 key，重算得到 `27fee343…` 逐位元相同（`research/f0_hash_boundary/`）。這是回報錯誤，不是 hash scope 洩漏
- **實測 scope（全部由量測得出，非閱讀程式碼得出）：**

| hash | producer | 實際涵蓋 | 不涵蓋 |
|---|---|---|---|
| `spec_sha256` | `freeze_master_prereg.py:75` → `file_sha256` | **本文件的 bytes** | 規範性 core 模組（另存為 `normative_modules`，未併入）、registry 的解析值 |
| `config_hash` | `b0_route.py:129` → `canonical_config()` | **整個 frozen spec registry，111/111 key 經 mutation 證明皆 load-bearing** | 任何未成為 key 的行為 |
| `state_hash` | `b0_route.py:267` → `state_payload()` | canonical input state，**含 listing spells** | `route_kind`（刻意排除） |

- **`config_hash` 不是 runtime subset：** 111 個 key 中只有 **12 個**在 B0 import closure 裡被 `spec()` 讀取。它是一個 **declaration hash**
- **本文件從未定義任何一個 scope：** §8.5 只把三者列為 parity 的輸入、§13.2 只說本文件自身的雜湊另存。`config_hash` 的 scope **只存在於 `core/b0_route.py:104` 的註解裡** —— 依 M-3「no specification-by-code」，註解不是規格
- **declaration / behaviour 接縫：** 13 個 O-F/O-G key 中 **6 個**的值直接讀自實作模組（改行為即改雜湊），**7 個是散文字面值**（`o_e_1_availability_rule`、`unexplained_gap_abort_scope`、`status_source_completeness_required`、`listing_spell_break_rule`、`price_lookback_reset_at_spell_start`、`reappearance_may_explain_earlier_gap`、`snapshot_delisting_fields_are_audit_only`），**無法追蹤它們所描述的程式碼**
- **B-21 binding 缺口：** manifest 綁 code / config / data / derived / execution / output，**不綁 `spec_sha256`**；而 L2 opening registry **有綁**。sealed run 因此不指名自己遵守的是哪一版 master（僅由 clean-tree 的 `commit_sha` 遞移涵蓋）
- **另有一條潛在接縫：** `b0_route._hash` 與 `b0_provenance._h` 是兩個不同的序列化函式，在目前 registry 上結果相同，但**未被證明等價**（已加測試釘住）
- **裁決：Case C。** master 未定義 hash scope → 依 M-3 登記 `hash_scope_boundary` 為 UNSPECIFIED，**阻擋 final provenance seal**（`core/b0_finalization_items.py`，`seal(final_seal=True)` 實測會 abort）。**施工方不得自行挑 scope**，四個候選方案已列於登記項，本文件不作選擇
- **未變更：** 任何 hash 的行為、任何策略語義、O-E-1 / O-F / O-G / D-1 / S-3b 判準

---

### C-46 · F0-R1 ~ F0-R7 · hash boundary 正式裁決（v1.13；F-0 CLOSED）
- **來源：** v1.12 §12.2 `F-0-1`（M-3 UNSPECIFIED，阻擋 final seal）
- **本條為 normative ruling 的落地紀錄。scope 由裁決給定，非施工方選擇。**

#### 七條裁決與落地位置

| # | 裁決 | 落地 |
|---|---|---|
| **F0-R1** | `config_hash` = **完整的 machine-readable declaration registry**，非 runtime-only 子集 | `spec("config_hash_scope")` / `spec("config_hash_is_runtime_subset") = False`；122/122 key 經 mutation 證明 load-bearing |
| **F0-R2** | `spec_sha256` = 凍結 Master 文件的 **raw-byte identity** | `spec("spec_sha256_scope")`；`core.b0_master_prereg.spec_document_sha256()`，**刻意不經 canonicalise** |
| **F0-R3** | implementation identity = **commit SHA + 明列的 normative-module hashes** | `NORMATIVE_MODULES`（23 個，移入 `core/b0_master_prereg.py`，不再只存在於 freeze 腳本）；`CodeProvenance.normative_module_sha256`，final seal 缺任一即 abort |
| **F0-R4** | production-reachable declaration **必須 implementation-derived，或由可執行的行為 conformance 覆蓋** | **新模組 `core/b0_declaration_conformance.py`**：17 個宣告，**7 個 derived / 10 個 behavioural**；`seal(final_seal=True)` 呼叫 `assert_declarations_conform()` |
| **F0-R5** | `state_hash` = **canonical concrete input-state identity**，不是 implementation hash | `spec("state_hash_scope")` / `spec("state_hash_is_an_implementation_hash") = False` |
| **F0-R6** | B-21 final manifest **直接綁** spec_sha256、config_hash、normative-module hashes、code commit、datasets/artifacts、initial state | 新增 `SpecificationProvenance` section；`PROVENANCE_SECTIONS` 由 6 → **7**；`sealed_input_sha256` 直列 `specification` 與 `normative_modules` |
| **F0-R7** | route 與 provenance **共用單一 canonical serialization / hash primitive** | **新模組 `core/b0_canonical_hash.py`**（`b0_canonical_hash@1`）；`b0_route._hash` 與 `b0_provenance._h` 皆為其別名；測試斷言 core 內**不得再出現第二個 `json.dumps`** |

#### F0-R4 的兩種 binding，以及各自實際擋得住什麼
- **IMPLEMENTATION_DERIVED（7）：** registry 值**就是**模組常數。改行為 → `config_hash` **自動**改變，沒有人需要記得去改句子。其 `check` **不是** drift 偵測器（兩邊讀同一個常數）；它擋的是「把導出改成今天的字面值副本」——derived binding 悄悄不再是 derived 的那種失效
- **BEHAVIORAL_CONFORMANCE（10）：** 值是常數載不動的散文，改由**可執行檢查跑那句話所描述的行為**，而不是把句子讀回來。負向控制已釘死：把 guard 改成忽略持倉 / 放寬 O-E-1 / 讓未解釋缺口不切斷 spell，三者皆被對應的 conformance 檢查抓到，而 registry 句子與 `config_hash` **完全不動**
- **檢查放在 core 而非測試檔：** 只存在於 pytest 下的檢查對 `seal()` 不可用，「某台機器上測試曾經通過」不是 provenance 紀錄

#### 雜湊實測值
- `config_hash`：`40375c34…2e9a012d`（v1.11）→ **`fad64b65…398f5567`**（v1.13，因新增 11 個 hash-boundary declaration key）
- **F0-R7 的 primitive 統一本身未改變任何雜湊** —— 換用共用 primitive 後 `config_hash` 仍為 `40375c34…`，實測確認為行為保持
- `spec_sha256` 隨本文件變更而更新，記於 `research/b0_registry/master_prereg_freeze.json`

#### 狀態
```
F-0                      CLOSED
OPEN SPEC ITEMS          0
OPEN FINALIZATION ITEMS  0
declaration conformance  17 declarations, 0 failures
```

- **未變更：** 任何策略語義、O-E-1 / O-F / O-G / D-1 / S-3b 判準、`state_payload` 的內容定義
- **仍待：** final provenance seal 與 repo finalization（本輪未進行）

---

### C-47 · M-3 `pre_l2_seal_semantics` —— provenance 分兩階段（v1.14）

#### 問題

§13.3 要求 **FINAL PROVENANCE SEAL → 才有資格開 L2 一次**，但 `seal()` 拒絕任何空 section，
而 `execution.decision_date` 與 `output.artifacts`（target / intent / receipt / NAV）
**只能由跑 B0 route 產生** —— 那正是這道 seal 存在的目的所在的下一步。

⇒ **seal 在規格上不可達。** 唯一的出路都是不可接受的：跑 route（等於提前開 L2）、
或填入捏造值（等於 specification-by-code）。B-21 closure 文件早已自陳
「本輪建立的是機制，不是一份已完成的 provenance」。

依 M-3 登記為 UNSPECIFIED，**施工方不得自選預設**。四個候選讀法：
(a) 綁一次 production adapter decision、(b) 與 L2 run 同時封存、
(c) 另立 repo-only seal、(d) 放寬 `PROVENANCE_SECTIONS`。

#### 裁決（2026-08-18）：兩階段 provenance，不採上述任一字面

| 階段 | 綁什麼 | 狀態欄位 |
|---|---|---|
| **B0 Baseline Seal（pre-L2）** | `spec_sha256`、完整 registry `config_hash`、canonical hash schema/version、commit SHA、clean-tree identity、全部 normative-module hashes、dataset hashes/schema/coverage/importer lineage、derived 輸入與 upstream lineage、**期初 state hash**、route identity、**L2 opening protocol** | `execution.status = NOT_EXECUTED_PRE_L2`<br>`output.status = NOT_PRODUCED_PRE_L2` |
| **L2 Run Provenance（post-execution）** | 引用 `baseline_seal_sha256`，再綁具體 execution / output hashes | `EXECUTED` / `PRODUCED` |

**關鍵語義：`NOT_EXECUTED_PRE_L2` 是 provenance，不是缺 provenance。**
它斷言「封存當下不存在任何 decision」；空白欄位則什麼都沒說 —— 那正是本項要消除的歧義。

#### 硬性禁止（皆有測試釘死）

- Baseline Seal **不得**要求或捏造 selection output / target hashes / intent / receipt / NAV / 績效
- **不得**為了滿足 Baseline Seal 而跑任何 B0 decision route
- 帶著 output hashes 的 baseline → **abort**（`did not happen`）
- 帶著 `decision_date` 的 baseline → **abort**（`fabricates a run`）
- L2 run 未指名 `baseline_seal_sha256` → **abort**
- L2 run **不得** mutate 或取代 Baseline Seal（`assert_baseline_not_mutated`）

#### seal critical section 綁 repo identity

本倉庫存在**自動排程 commit 機制**（`FinMind_DailyUpdate` / `Market_SnapshotCollector`），
故「檢查時乾淨」不等於「封存時乾淨」。`RepoIdentityGuard` 於 preflight 快照、
於**回傳 seal hash 之前的最後一步**重驗：HEAD、工作區乾淨度、normative hashes、
declaration conformance。任一改變 → `SealRaceError` abort。

#### 測試不得弄髒受版控的工作區

`gate2_c3_runner` 原本每次都改寫受版控的 `gate2_preflight.json`，使
「套件通過」與「工作區乾淨」無法同時成立。產物改寫入 gitignore 的 `artifacts/`，
其 sha256 由 Baseline Seal 綁定；並新增
`clean tree → canonical suite → clean tree` 的端到端回歸。

#### CRLF → LF 遷移帳本

`.gitattributes` 將 LF 定為正規表示法後，3 份 Frozen A 時期紀錄的 9 個 hash 欄位
成為歷史 CRLF 指紋。**不得靜默覆寫**：並列保存於
`research/b0_registry/lf_migration_ledger.json`（`transformation = CRLF_TO_LF_ONLY`、
`substantive_change = false`，且每筆皆經機械驗證），
明示修訂見 `docs/AuditAmendment_LF_Migration_2026-08-18.md`。
9 個路徑皆非 B0 消耗性輸入或 normative 模組，**不阻擋 Baseline Seal**。

#### 狀態

```
M-3 pre_l2_seal_semantics   CLOSED（本裁決）
OPEN SPEC ITEMS             0
OPEN FINALIZATION ITEMS     0
```

- **未變更：** 任何 Selection / Eligibility / Portfolio / Execution / Cost 策略語義
- **v1.13 保留為歷史 lineage**；本裁決明文要求**不得**為了保住 v1.13 雜湊而繞開登記機制

---

### C-48 · M-3 `value_pbr_lineage_2019plus` —— 官方交易所 PBR 為 2019+ admissible continuation（v1.15）

#### 問題

B-09 把 Value 凍在 **TSE 交易所 PBR series**，但**沒有定義 2019+ 的 admissible 來源**。
實測發現：帶 `股價淨值比-TSE` 的只有逐年 xlsx vintage，而 2019+ 那一段正是 D-1 quarantine
的 corpus（`aeda65b9…ea49c1`）；取代它的兩個 zip 只帶 `股價淨值比-TEJ`。
⇒ 每一條可達路徑都撞到某條已凍結的規則，**141 個窗口月中的 87 個（62%）無來源**。
依 M-3 登記為 UNSPECIFIED，施工方不得自選預設。

#### 裁決（2026-08-18）：R1 ~ R7

| # | 裁決 | 落地位置 |
|---|---|---|
| **R1** | 官方歷史交易所 PBR 為 B-09 lineage 的 **2019+ admissible continuation**：TWSE→上市、TPEx→上櫃。**Value 語義不變**，仍是 `B/M = 1 / PBR` 的產業相對百分位。**不得**代以 `PBR_TEJ` | `core/b0_valuation_source.py`：`VALUATION_LINEAGE`、`TEJ_SUBSTITUTION_ALLOWED = False`；`spec("value_pbr_lineage")` |
| **R2** | TPEx 於來源開始揭露 statement vintage 之前的觀測：**「官方當期每日 PBR 可採」可主張，「該筆分母用的是哪一期財報」不可主張**。屬 disclosed source-lineage limitation，**不是 M-3 blocker**；且**不得**推導或合成缺失的 vintage 欄位 | `TPEX_PRE_VINTAGE_ADMISSIBLE_CLAIM` / `…_INADMISSIBLE_CLAIM`（逐字）、`TPEX_VINTAGE_MAY_BE_INFERRED = False` |
| **R3** | 無官方 PBR 者（興櫃／從未在任一板／交易所印 `-`／無有意義比值）一律 `pbr_tse = NA` → §4.1 complete-case。**禁止** TEJ fallback、imputation、跨板回填、以帳面淨值÷股數另造 B/M | `MISSING_VALUE_POLICY`、`FORBIDDEN_GAP_REPAIRS`（四項具名） |
| **R4** | 板別歸屬只能取自**當時**的 TWSE/TPEx 來源或其他已核准的 PIT board source；**當期 `上市別` 永不得用於歷史分類** | `BOARD_ATTRIBUTION_SOURCE`、`CURRENT_LISTING_LABEL_ALLOWED = False` |
| **R5** | **L2 不得即時打 TWSE/TPEx**。須先物化為 canonical derived valuation source，並帶 raw payload sha256／來源識別／trading session／importer version／parser version／schema hash／content hash／coverage／NA 處理／upstream lineage | `ValuationSourceContract` + `assert_valuation_source_admissible`；`RUNTIME_FETCH_ALLOWED = False` |
| **R6** | 2025 後 coverage 由 ~94–95% 升至最高 98.42%，**具名記為 coverage-regime observation**。不得據以更動 B0 語義、eligibility 或缺值政策；單靠無法解釋的 coverage 位移**不重開 B-09**，除非出現 valuation-semantic break 的證據 | `limitation_record()["coverage_regime_2025"]` |
| **R7** | `value_pbr_lineage_2019plus = CLOSED`，並依既有治理機制重新凍結 Master／machine declaration。**這是 source-lineage closure，不是策略因子變更** | 本條 + `core/b0_open_items.py` 移除該項 → `OPEN SPEC ITEMS = 0` |

#### 裁決所依據的機械證據（不是「官方比較可信」）

同證券、同 trading session，對 2016-2018 全部 36 個月底逐筆比對：

```
TWSE 上市   32,284 筆   100.00% 完全相同   max |Δ| = 0.00
TPEx 上櫃   26,419 筆    99.96% 完全相同   max |Δ| = 0.09
            11 筆差異全部落在 2016-01 / 2016-02，兩板 signed median 皆 0.00
official_only = 0        官方序列從不比 frozen lineage 多出一檔 → 採用不會擴大母體
同 session 對齊          收盤價交叉驗證 18,963 / 18,963 完全相同
87/87 affected months    兩家交易所皆實際取得，unresolved transport failure = 0
```

**這是 lineage continuity（同股同日同值），不是欄位同名的推測。**
完整證據見 `research/b0_valuation_lineage_audit/FINDINGS_full_harvest.md`。

#### 兩項必須隨此序列一起流通的揭露

- **TPEx vintage：** 實測 2024-12-31 無 `財報年/季` 欄、2025-01-02 起有 → **87 個決策月中有 72 個月沒有上櫃 vintage 揭露**。行為證據（`BVPS = 收盤價 / 官方 PBR` 的區間步進掃描，四組共 3,684 檔**無一檔**呈單一固定淨值）強烈否定「今天重算後回填」，但**不能**證明個別分母的財報期別。
- **TWSE 對照：** 官網明文 `為計算當時公開資訊觀測站已公告申報格式化之資料，而非同期即時資訊，且不作回溯計算`，且 `股利年度及財報年/季資訊自民國106年4月12日起提供`。

#### 與 §2.8.3 的關係

era 邊界**沿用 §2.8.3 已為價格凍結的同一條**（`<= 2018` 逐年匯出 / `>= 2019` 取代 vintage），
不另立第二條時間軸。差別只在 2019+ 那一側：價格取兩個 zip，估值取官方交易所。
**逐年可選的來源會是自由參數；單一邊界不是。**

#### 狀態

```
M-3 value_pbr_lineage_2019plus   CLOSED（本裁決）
OPEN SPEC ITEMS                  0
OPEN FINALIZATION ITEMS          0
NORMATIVE_MODULES                23 → 24（新增 core/b0_valuation_source.py）
```

- **未變更：** B-09 Value 定義、§4.1 complete-case、§2.3 產業 PIT、D-1 判準與 quarantine、任何 Selection / Eligibility / Portfolio / Execution / Cost 策略語義
- **仍待：** L2 sealed-input materializer（141 期）、新的 B0 Baseline Seal。**本裁決不開 L2**

---

### C-49 · M-3 `value_per_lineage_2019plus` —— 官方本益比為 2019+ `per_tse` 的 admissible continuation（v1.16）

#### 問題

C-48 落地後**物化 sealed panel 時**才發現：`PEG` 是 Value 的凍結成員（C-17：`PEG = PER_TSE / eps_growth_pct`），
所以 `per_tse` 與 `pbr_tse` **同樣**在 Selection path 上、**同樣**是那 87 個月、**同樣**只存在於
quarantined 的逐年 vintage（取代它的 zip 表頭實測只有 `本益比-TEJ`）。

**C-48 沒有裁這一項** —— R1 只談 PBR。「同理可推」正是 M-3 要擋的動作，且類比並不精確：
PE 有定義域（EPS 非正即無比值），B/M 沒有，兩者的 NA 母體本來就不同。故依 M-3 登記、停工、上報。

#### 先做 PE-specific reconciliation，且判準先於結果凍結

使用者於裁決書中**先**寫死四條 admissibility 條件，才允許看數字；不得事後挑門檻，不得自創數值通過線。
比對窗口、證券、session 與 PBR reconciliation 完全相同（2016-2018 的 36 個月底），
**全部使用既有 cache，未對交易所發出任何新請求**（`new_exchange_requests = 0`）。

| | 比對數 | 完全相同 | max \|Δ\| | 相對差 p99 | signed median |
|---|---|---|---|---|---|
| **TWSE 上市** | 26,062 | 26,061（**99.9962%**） | **0.01** | 0.0 | 0.0 |
| **TPEx 上櫃** | 18,815 | 18,815（**100.00%**） | **0.00** | 0.0 | 0.0 |

唯一一筆差異：`4733` 於 2016-02-26，官方 12.24 vs lineage 12.25 —— **一個 tick、相對 0.08%**，
即公布精度捨入。

#### 關鍵發現：逐年匯出用 `0.0` 當「無比值」的哨兵值

實測：`本益比-TSE` 有 **4,927** 列恰為 `0.0`（**無一為負、無一為空白**），`股價淨值比-TSE` 有 **7** 列，
且每一列都對應交易所印 `-` / `N/A` 的同一證券同一 session。

**`0.0` 是一個數字。** 當成資料讀就會得到 `PEG = 0/g` —— 一檔根本沒有本益比的證券，拿到**最便宜的排名**。
凍結語義（C-17 `PE > 0`、§3.2 `PBR > 0`）在下游本來就會拒絕它，因此在來源邊界正規化為 NA
**不改變任何 B0 行為**，只是讓哨兵值不再以資料的身分流通。已凍結為
`SENTINEL_ZERO_IS_UNDEFINED` / `SENTINEL_ZERO_ERAS`。

把哨兵值讀成「缺值」之後，**兩邊對每一筆缺值都一致**：

```
TWSE  both_present 26,062 · both_na 6,231 · official_only 0 · lineage_only 0
TPEx  both_present 18,815 · both_na 7,610 · official_only 0 · lineage_only 0
```

#### 四條先驗條件的判定

| # | 條件 | 判定 |
|---|---|---|
| 1 | 同 session 值一致，差異只能由公布精度/捨入解釋 | ✅ 44,877 筆中 1 筆差 1 tick |
| 2 | 缺值差異可歸因於 PE 定義域／官方 NA 表示法 | ✅ 解碼哨兵值後**零**缺值不一致 |
| 3 | 無系統性水準或符號偏移 | ✅ signed median 0.0、mean ≈ 0、僅 1 筆非零 |
| 4 | 無證據顯示官方序列是回溯重算的替代序列 | ✅ 見下 |

**條件 4 的量測（隱含 EPS 步進掃描，與 PBR 同一估計器，公布精度以區間承接）：**

| run | 證券數 | 單一固定分母 | 步進/證券年 | 與揭露 vintage 一致率 | recall |
|---|---|---|---|---|---|
| PE · TWSE 2019+ | 1,030 | **0** | 2.724 | **99.46%** | 98.51% |
| PE · TPEx 2019+ | 846 | **0** | 2.447 | **99.66%** | 99.17% |
| PE · TWSE 2016-2018 | 843 | **0** | 3.287 | 99.10% | 97.45% |
| PE · TPEx 2016-2018 | 642 | 1 / 642 | 3.157 | —（無揭露） | — |

步進月份集中於 03 / 05 / 08 / 11，即法定公告日曆。**3,361 檔中僅 1 檔**呈單一固定分母
⇒ 「今天重算後回填」被否定。

#### 裁決

`PEG` 定義與定義域**完全不變**（`PEG = PER_TSE / eps_growth_pct`，`PE > 0 且 eps_growth_pct > 0`，否則 NA）。
2019+ 的 `per_tse` lineage：**TWSE 官方本益比 → 上市；TPEx 官方本益比 → 上櫃**。
`PER_TEJ`、quarantined corpus、自行重算 PE **一律禁止**；**不得**把 2019+ PEG 整段設為 NA。
PBR 已凍結的來源治理規則**逐條同樣適用**：PIT 板別歸屬、禁用當期 `上市別`、官方 `-`/`null`/未定義 → NA、
無 fallback、無 imputation、L2 不得 live fetch、raw payload／parser／importer／schema／content hash 全部封存。
TPEx 於未揭露 vintage 的期間，**沿用與 PBR 逐字相同的 limitation**，不得合成 vintage。

#### 另一項 execution correctness 修正（非策略變更）

sealed panel 的 as-of session **必須**取自 `b0_route.resolve_as_of`（§6.6：嚴格早於 decision date 的
最後一個已完成 session），**不得**沿用 audit 的「月底當天或之前」慣例 —— 兩者在
**141 個決策月中有 85 個不同**。builder 於建檔時逐期對 route 重新推導，並有回歸測試釘死。

#### 狀態

```
M-3 value_per_lineage_2019plus   CLOSED（本裁決）
OPEN SPEC ITEMS                  0
parser version                   official_pbr_parser_v1 → v2（同一列同時帶兩個比值）
canonical valuation panel        pbr_tse + per_tse 同一份，四份 contract（2 era × 2 ratio）
```

- **未變更：** PEG 定義與定義域、B-09 Value、§4.1 complete-case、D-1 判準、任何策略語義
- **仍待：** L2 sealed-input materializer（141 期）、新的 B0 Baseline Seal。**本裁決不開 L2**

---

### C-51 · M-3 `stock_dividend_holder_multiplier_source` —— 官方交易所無償配股率為 canonical holder multiplier（v1.18）

#### 問題

C-50 裁完「調整是什麼」之後，剩下一個**輸入**問題：R2 已定配股是合格的 holder-level 事件、
R4 已定以 market-effective session 為界，**規則沒有問題，缺的是 `m` 的來源**。
9,120 筆配股**全部沒有** `share_multiplier`；登記語料帶的是**新股股數**
（8,109 筆 RECONSTRUCTIBLE 的 p50=6,692 / p95=203,088 / max=2,837,327，僅 4.6% ≤1,000），
而 `m = 1 + 新股/流通在外股數` 的分母在 ≤2018 沒有任何已註冊 PIT-safe 來源。
依 C-50/R8 登記而非自行選擇：NA 分支代價已實測為每期 8.08%~20.34% 的計價母體（中位 10.56%），
對照 §2.3 已接受的產業 UNRESOLVED 排除中位 2.303%。

#### 兩輪來源稽核

**第一輪：`除權息2004-20260806` —— 否決。** 六個檔案同一 schema、28,012 列、2004-01-13 … 2026-08-06、
2,164 檔，**全部是現金股利欄位**（`息值` / `現金股利_盈餘` / `現金股利_公積`），
以 `配股 / 股票股利 / 無償 / 每千股 / 比率 / 換股` 全字掃欄名**零命中**。
決定性證據是加總測試：落在已註冊配股除權日的 6,708 筆中，
`息值 = 現金_盈餘 + 現金_公積` **100.00% 成立**，兩個分項恰好把總額用完，
故該總額整筆是現金、裡面沒有殘留的股票腿。coverage 亦僅 73.54%。

**第二輪：官方交易所 —— 採用。** 關鍵發現是**兩個交易所都直接公布 holder-level 比率**，
且交易所自己的欄位切分正好等同 C-50/R2 已裁的 eligible / ineligible：

```
TWSE  除權除息計算結果表明細 TWT49UDetail?STK_NO=&T1=
      A. 按普通股股東持股比例每千股無償配股   <- 合格
      B. 員工紅利轉增資                        <- 不合格（R2）
      C. (有償) 現金增資                       <- 不合格（R2）
TPEx  除權除息 exDailyQ?startDate=&endDate=（ROC 日期）
      每仟股無償配股                           <- 合格，範圍表直接帶
```

**除權除息預告表（TWT48U）另行測試後否決為歷史來源**：它確實帶 `無償配股率`，
但 `date` / `startDate/endDate` / `strDate` 全被忽略，永遠回同一個未來窗（測時 162 列、
2026-08-17 … 2026-10-07）。它是預告表，沒有歷史。

#### 單位語義以量測決定，非依欄名

以交易所**自身**公布的參考價恆等式檢驗，只用交易所自身公布的分量：

```
參考價 = (前收 − 現金股利 + 認購價 × 認購率) / (1 + 無償配股率 + 認購率)
```

這不是「由價格反推 `m`」——`m` 本來就已公布；這是問哪一種單位讀法滿足發布者自己的算式，而只有一種滿足：

| 讀法 | TPEx max\|Δ\| (n=1,106) | TWSE max\|Δ\| (n=1,253 純配股) | 落在 0.01 內 |
|---|---|---|---|
| **每 1,000 股配發** | **0.0050** | **0.0999** | **100.00% / 97.92%** |
| 十進位比率 | 2095.11 | 1527.98 | 0% / 0% |
| 百分比 | 953.18 | 1035.86 | 0% / 0% |

超標的 14 筆全部同時有現金增資（該腿 R2 本就不合格，不會進 `m`，屬查核算式的極限而非欄位的極限）；
純配股超標的 26 筆中 25 筆落在 0.013~0.026、皆為高價股，與公布配股率只取一位小數一致；
餘 1 筆（`2723` / 2018-06-21，0.0999）未獲解釋，具名記錄不掩蓋。

#### R1 ~ R6

- **R1 · canonical source 與 canonical conversion。** 採官方交易所無償配股欄位為 C-50 配股調整的
  canonical holder-level 來源，凍結轉換為 `holder_multiplier = 1 + bonus_shares_per_1000 / 1000`。
  具名禁止：`新股/流通在外股數`、current shares outstanding、參考價反推、現金股利語料、
  員工紅利轉增資、有償現金增資。禁止項是**具名拒絕**而非僅未使用。
- **R2 · pre-listing 殘差。** 事件發生時該證券尚未出現在任一 PIT 交易板別者，
  disposition = `NOT_APPLICABLE_TO_B0_MARKET_HISTORY`：**不要求建立 pre-listing 調整鏈，
  也不視為 B0 缺值**，listing spell 仍從真正上市後的 canonical history 起算。
  判定只用當期交易所出現紀錄，**不得使用 current 板別狀態**。
- **R3 · 休市日排定除權日。** 新增 event-date normalization：若官方排定除權日**不是** observed
  trading session，而 canonical ledger 的 `ex_or_effective_date` **恰等於**該排定日之後的
  **第一個** observed trading session，則兩者視為同一 market-effective event。
  **這不是 ±N 日容忍**：`NEAREST_DATE_MATCHING_ALLOWED = False`、`DATE_TOLERANCE_DAYS = 0`，
  只有 exact next observed session 可採。實測 13 個非 session 的官方日期全為休市日，
  且 canonical 日期在每一例都正好是其後第一個開盤日（2013-08-21、2014-07-23、2015-07-10、
  2016-07-08、2016-09-28、2019-08-09、2019-09-30、2023-08-03、2024-07-24、2024-07-25）。
- **R4 · 其餘未對上者。** 不屬於官方比率、不屬於 NOT_APPLICABLE、不屬於 exact normalization 者
  一律 `UNRESOLVED`：**不得推論 multiplier**，維持 C-50/R8 的 fail-loud / NA / complete-case，
  若既有規格無法唯一決定則再開 M-3。
- **R5 · sealed-source contract。** L2 期間**不得**對 TWSE/TPEx 發出任何 live request
  （`live_fetch=True` 直接不 admissible）。綁定：endpoint identity、全部 raw payload SHA256、
  parser/importer 版本、schema hash、stock_id、官方排定除權日、canonical market-effective session、
  PIT board/source identity、`bonus_shares_per_1000`、derived `holder_multiplier`、
  content hash、coverage 統計、upstream manifest hash。parser 版本改變即改變 source identity。
- **R6 · 關閉登記項**，並落地八條 negative control。

#### 落地結果

```
raw payloads          1,383（twse_range 52 · tpex_range 52 · twse_detail 1,279）
upstream manifest     870a8f3a71e5251172816e6fd41a93e8389651ac178f326ab6bb741305492d1b
sealed panel          data/b0/bonus_share_panel.parquet
content sha256        3b311238f121247572d84e5d1eb915d5b3538972509581fcedaffdfaa17155bb
transport failures    0
```

窗口為 141 期 `momentum_12_1` / `sigma20d` lookback 的聯集 `2013-06-29 … 2026-03-31`
（首個決策月 2014-07 的 `P_{t-13}` 是 2013-06 月底 session 2013-06-28；落在其上或之前的事件
會同時整除兩個動能錨點，不改變比值），內含 3,215 筆 canonical 配股事件、996 檔：

| disposition | 事件數 | 佔比 |
|---|---|---|
| `OFFICIAL_BONUS_RATE` | **2,399** | **74.62%** |
| `NOT_APPLICABLE_TO_B0_MARKET_HISTORY` | 784 | 24.39% |
| `UNRESOLVED` | 32 | 1.00% |

其中 2,399 筆按當期板別為 TWSE 1,279 / TPEx 1,120，經 R3 正規化者 23 筆。
`NOT_APPLICABLE` 的 784 筆由 381 筆真正 pre-listing 與 403 筆 ledger 自身判為
`NOT_RECONSTRUCTIBLE`（登記戳記）組成；`UNRESOLVED` 的 32 筆為 13 + 19。
兩者的組成以 `ledger_reconstructibility` 欄與 receipt cross-tab 揭露，**不折進 disposition**。

**每期未解決曝險：中位由 10.56% 降至 1.41%（min 0.20% / max 2.97%），已低於
§2.3 已接受的產業 UNRESOLVED 排除中位 2.303%。**

- **未變更：** C-50 的 R1~R8、B-09 選股語義、§3.1 price relative、§4.1 complete-case、
  ADV20 / marks / execution / NAV 讀 raw、Frozen A
- **仍待：** 141 期 market-side materialization、新的 B0 Baseline Seal。**本裁決不開 L2**

---

### C-50 · M-3 `momentum_price_adjustment` —— 價格調整定為 share-unit（v1.17；v1.19 補立章節）

> **本節於 v1.19 補立。** 裁決本身於 v1.17 落地並生效，當時只記在版本行與 §12 表格中；
> 本節是**文件整併**，不更動任何語義、不新增任何自由參數。

#### 問題

`compute_momentum_12_1` 要求輸入序列「已依 §2.4 股數事件調整」，並明言調整不是它自己的選擇；
但**沒有任何條文說那個調整是什麼**。故依 M-3 登記 `momentum_price_adjustment`。

#### 裁決所繫的區分

```
調整的對象是「既有持有人所持股數的確定性轉換」
—— 不是公司流通在外股數的變動
```

因此 **`share_multiplier != 1` 不構成資格**。可轉債轉換、員工配股、現金增資、庫藏股註銷
都會移動流通在外股數卻不乘上任何人的既有部位，為它們調整價格等於**從稀釋中製造出報酬**；
而配股、分割、反分割、減資換股確實會乘上既有部位，不調整則會把一次分割報成 −50% 的動能。

#### R1 ~ R8

- **R1 · 基準。** `ADJUSTMENT_BASIS = SHARE_UNIT_ADJUSTED`，**不是** `TOTAL_RETURN_ADJUSTED`。
  現金股利、退還現金、認購價、認購權值、再投資一律不得進入因子（`EXCLUDED_FROM_FACTOR`）。
  §3.1 凍結的是**價格相對**，總報酬序列會用同一個名字回答不同的問題。
- **R2 · 資格。** eligible = `stock_dividend` / `capital_reduction` / `par_value_change`；
  ineligible（移動流通股數但不轉換既有部位）= `cash_capital_increase` /
  `convertible_bond_conversion` / `employee_bonus` / `treasury_cancellation` /
  `other_share_change`。未分類的 kind **不得**默默當作 ineligible —— 那與猜因子同形。
- **R3 · 公式。** 界線之前 `adjusted = raw / m`，多個界線以乘法複合；界線當日與其後維持原值，
  故序列最新端恆為原始報價。
- **R4 · 界線。** `ex_or_effective_date` 解析到的 **market-effective session**；
  **永不**使用 `credit_tradable_date`（那管的是配發股份何時可交易，是另一個問題）。
- **R5 · 身分。** `merger` / `share_conversion` / `transfer_in` 為 identity change：
  **不得跨證券接續價格歷史**，後繼證券使用自己的 canonical history 與自己的 listing spell。
- **R6 · 消費者切分。**
  ```
  讀 adjusted : momentum_12_1 · sigma20d
  讀 raw      : marks · execution_prices · nav · portfolio_market_value
                order_notional · fees_tax · adv20
  ```
  後者都是「實際付出或實際成交的金錢數量」；調整後價格是可比性工具，沒有任何交易發生在那個價位。
  ADV20 尤其必須留在 raw —— §4.2 是絕對新台幣門檻。
- **R7 · 單一 producer。** `core/b0_share_unit_adjustment.py` 是唯一產生調整因子的模組，
  raw panel 維持不可變。
- **R8 · fail-loud。** 合格事件而 multiplier 缺失或歧義、界線無法重建、同一性無法確立者
  一律 raise，由呼叫端依既凍結的 complete-case 語義轉為 NA；**不得代入看似合理的因子**。
  若既有規則無法唯一決定處置，則另開 M-3 項。

#### 與 C-51 的關係

R8 的 fail-loud 路徑正是暴露出 `stock_dividend_holder_multiplier_source` 的地方：
規則完整，缺的是配股 `m` 的來源。該來源問題由 **C-51** 以官方交易所無償配股率裁決關閉，
其 canonical 轉換 `m = 1 + bonus_shares_per_1000 / 1000` 供給的正是本節 R2 的 `stock_dividend` 分支；
R2 的 eligible / ineligible 切分與交易所欄位 A（無償配股）/ B（員工紅利轉增資）/ C（有償現金增資）
的切分一致，此一致性是 C-51 採用該來源的理由之一。

- **未變更：** §3.1 price relative、§2.4、B-09 選股語義、Frozen A
- **落地：** 12 條必要測試（parametrise 後 32 條），9 個 registry key，
  normative module `core/b0_share_unit_adjustment.py`

---

### C-52 · Baseline Seal 本體改為 content-addressed 不可覆蓋歸檔（v1.19）

#### 問題

seal script 原本寫死單一路徑 `artifacts/baseline_seal/b0_baseline_seal.json`，
而 `artifacts/` 在 gitignore 內、從未進版控。因此**每取一次新 seal 就就地覆蓋前一份本體**。
實際後果已經發生：`bdc69c32…`（v1.14）與 `292ae484…`（v1.18）兩份本體皆已滅失。

#### R1

- canonical 歸檔路徑為 **content-addressed 且不可覆蓋**：
  ```
  artifacts/baseline_seal/seals/<seal_sha256>.json
  ```
- 該路徑已存在時**寫入必須 abort**（`SealOverwrite`）。同一 hash 即同一 seal，無可寫；
  不同 seal 不得冒用同一身分。
- 寫入後必須**重新開檔驗證**：payload 的 `baseline_seal_sha256` 必須重現檔名所宣稱的身分。
- `b0_baseline_seal.json` 可續存為 latest pointer / 便利複本，**但它不是 canonical 歸檔身分**。
- lineage ledger（`research/b0_registry/baseline_seal_lineage.jsonl`）記錄
  predecessor / supersession 關係，append-only，既有條目不重寫。
- **不得重建 `bdc69c32…` 已滅失的本體。** 該條目據實記為
  `historical_hash_recorded = true` / `canonical_body_available = false` /
  `reason = previous single-path seal was overwritten before immutable archival was implemented`。
  缺失的 provenance 不得捏造。

---

### C-53 · 開倉狀態日期接縫（v1.19）

#### 問題

兩個日期描述同一個時刻而不是同一個日期：

```
registered opening state    window_start                    2014-07-31（決策日）
canonical decision input    resolve_as_of(window_start)     2014-07-30（前一完成交易日,§6.6）
```

無持股時兩者是同一個經濟狀態，但**不是同一個 hash 物件**。
retrospective adapter 明文拒絕替 portfolio 改日期（「adapter 不重新標定 portfolio 的日期，
它回報不一致」）—— 這是對的：被默默移到另一個 session 的 portfolio，等於宣稱它在一個
未被觀察的日子有某個價值。

#### R2

- 上述區分予以**凍結**。
- **僅 period 1** 的 registered opening state 正規化到 canonical as-of session，
  且**不改變任何經濟狀態**。
- 兩個 hash **同時保留並綁定**：`registered_opening_state_sha256` 與
  `canonical_opening_state_sha256`。
- 新增可執行不變量：除明文允許的日期／as-of metadata 欄位外，
  `cash`、持股、pending exit、應收應付、以及一切其他 portfolio 經濟欄位**必須完全相同**
  （相同，不是「等價」、不是「在容差內」）；並要求 canonical as-of **嚴格早於** registered 日期。
- 這是**開倉狀態邊界規則**。**不得**建立可對任意 portfolio 改寫日期的通用機制：
  `assert_not_a_generic_redater` 對非開倉狀態的任何改期一律 raise。

---

### C-13 · O-C 由 open item 轉為凍結政策
- **來源：** 本文件 v1.0 §12 O-C，列為待決（是否另尋來源）
- **變更：** §2.4 凍結為「不建推導模型、不猜除權日、維持 `NOT_RECONSTRUCTIBLE`」
- **理由：** 已有乾淨處置（辨識到 + 語義不足 + 暴露時 fail-loud）就不會產生錯誤 NAV。**final seal 不要求所有歷史事件都 reconstructible。** 未來若取得 authoritative source，走 §9.5 data repair protocol

---

## §12 Open Items（`UNSPECIFIED` → 必須 abort，見 §1.5）

### 12.1 已於 P-1a 關閉（v1.1）

| # | 項目 | 結果 |
|---|---|---|
| **O-A** | corporate-action 守衛接線點 | ✅ **FROZEN** §6.1 —— pre-mark mandatory stage，下游任一 stage 缺席即 abort |
| **O-B** | 價格消失的 PIT 語義 | ✅ **FROZEN** §2.6 —— 四個 PIT observable + 四態分類；`last_price_date` 移除；「永久消失」不再是概念 |
| **O-C** | 312 件無旗標增資 | ✅ **FROZEN** §2.4 —— 不建推導模型，維持 `NOT_RECONSTRUCTIBLE` |
| **O-D** | 日內事件順序 | ✅ **FROZEN** §6.6 —— 七步序列 + prior-session decision state + payment-date cash credit |

**⇒ 影響 core 語義的 open item 已全數關閉。** 後續 canonical core 只照規格施工，不需再做策略裁決。

### 12.2 仍為 `UNSPECIFIED` / PENDING

| # | 項目 | 性質 | 阻塞什麼 |
|---|---|---|---|
| ~~**O-F**~~ | ~~證券狀態來源的下市涵蓋缺口~~ —— **已於 v1.11 以 incomplete-source / fail-loud 關閉**（C-41）。來源永遠不完整是既成事實，不是待修項；閘門改在**暴露**上 | ~~DATA~~ | ✅ **已關閉** |
| ~~**F-0-1**~~ | ~~hash scope 未定義~~ —— **已於 v1.13 由 F0-R1 ~ F0-R7 裁決關閉**（C-46）。`OPEN FINALIZATION ITEMS = 0` | ~~SPEC / PROVENANCE~~ | ✅ **已關閉** |
| ~~**O-G**~~ | ~~listing spell 不變式~~ —— **v1.11 開立並同版關閉**（C-43）。無法解釋的缺價後又重新出現 → 於**首個重新觀測到的 session** 開始新的 canonical listing spell；價格回看視窗於新 spell 重置，長度不足即 NA | ~~SPEC~~ | ✅ **已關閉** |
| ~~D-1~~ | ~~價格母體存活者偏誤~~ —— **已於 v1.9 關閉**（§2.8.3） | ~~DATA / BLOCKING~~ | ~~S-3a、`final_provenance_seal`、`L2_opening`** |
| ~~**P-2**~~ | ~~兩個 adapter 向同一 core 供料~~ | ✅ **DONE（v1.7）** | —— |
| ~~**`value_pbr_lineage_2019plus`**~~ | ~~2019+ 的 `pbr_tse` 無 admissible 來源~~ —— **v1.14 之後登記、v1.15 由 R1~R7 關閉**（C-48）。官方 TWSE/TPEx 歷史 PBR 為 admissible continuation，證據為 overlap 期逐筆同值 | ~~SPEC / BLOCKING~~ | ✅ **已關閉**（曾擋住 L2 sealed-input materializer） |

| ~~**`value_per_lineage_2019plus`**~~ | ~~2019+ 的 `per_tse` 無 admissible 來源~~ —— **v1.15 之後登記、v1.16 由 C-49 關閉**。官方本益比為 admissible continuation，先做 PE-specific reconciliation 才裁，未以「同理可推」擴張 C-48 | ~~SPEC / BLOCKING~~ | ✅ **已關閉** |

| ~~**`momentum_price_adjustment`**~~ | ~~momentum 月底價序列的調整規則~~ —— **v1.17 由 C-50 (R1~R8) 關閉**。定為 share-unit adjustment：只調整「既有持有人股數的確定性轉換」，**不以流通在外股數為準**，`share_multiplier != 1` 不構成資格；現金股利不調整；只有 momentum_12_1 與 sigma20d 讀調整後序列 | ~~SPEC / BLOCKING~~ | ✅ **已關閉** |
| ~~**`stock_dividend_holder_multiplier_source`**~~ | ~~配股的 holder multiplier 取自哪個 admissible 來源~~ —— **v1.18 由 C-51 (R1~R6) 關閉**。官方交易所無償配股欄位（TWSE `A. 按普通股股東持股比例每千股無償配股`、TPEx `每仟股無償配股`）為 canonical holder-level 來源，`m = 1 + bonus_shares_per_1000 / 1000`，單位以交易所自身參考價恆等式量測確認；**未重建流通在外股數分母**。pre-listing 事件判為 `NOT_APPLICABLE_TO_B0_MARKET_HISTORY`、休市日排定除權日以 exact next observed session 正規化（非 ±N 日容忍）、其餘 32 筆維持 `UNRESOLVED` 走 C-50/R8。每期未解決曝險中位 10.56% → **1.41%** | ~~SPEC / BLOCKING~~ | ✅ **已關閉** |

**✅ P-1b-U 已於 v1.6 關閉：canonical core 的 UNSPECIFIED 項目為 0。**
**該計數在 v1.14 之後曾短暫回到 1**（`value_pbr_lineage_2019plus`，materializer 施工時撞到），
**於 v1.15 由 C-48 裁決關回 0**；**隨即因 `value_per_lineage_2019plus` 再回到 1**，**再於 v1.16 由 C-49 關回 0**。
**其後 materializer 施工又撞到 `momentum_price_adjustment`，計數再回到 1，並於 v1.17 由 C-50 關閉；同一裁決的 R8 fail-loud 路徑暴露出 `stock_dividend_holder_multiplier_source`，計數仍為 1，並於 v1.18 由 C-51 關回 0。**
登記簿兩次承接了施工時新發現的未定行為，這正是它存在的理由 —— 期間 S-1 為紅是機制正常運作，不是回歸缺陷。

```python
>>> from core.b0_open_items import summary
>>> summary()["total"]
0
```

**登記簿本身保留。** 機制不是因為清單空了就不再需要 —— 下一個被發現的未定行為必須落在那裡，而不是落在某個預設值裡；`raise_unspecified` 對未登記的 key 刻意拋 `KeyError`，就是為了強制這件事。

> **累計：v1.3 關 5 項、v1.4 關 8 項、v1.5 關 7 項並新登記 1 項、v1.6 關 1 項 → 0。**
> **C-16 ~ C-27（13 項）是 master omission**，關閉未新增任何自由參數。
> **C-28 ~ C-36（9 項）是真正的裁決**，且每一項都以「移除選項」而非「新增旋鈕」的方式落地 —— 被否決的替代方案（`pro_rata`、`nearest` rounding、`ordinal` percentile、hold-until-dropped、四條 legacy 風險腿）**一律從程式碼移除**，而非保留為可選分支。**不可達的替代方案是文件；可達的是等著被呼叫的旋鈕。**

**P-1b 實作本身（四層 + state + canonical core 測試）已完成**，見 `docs/P1b_CanonicalCore_Implementation.md`。

**D-1 已於 v1.9 關閉**（§2.8.3）。`unmet_blocking_requirements()` 現在回傳 `[]`。

> **⚠ 敘述紀律：三個 blocking data requirement 都關閉，不等於可以 seal 或開 L2。** O-F / O-G / S-3b 已於 v1.11 關閉，仍待：**final provenance seal**、**repo finalization**。L2 開封另有其條件，且未在本輪執行。

---

## §13 Freeze Record

### 13.1 狀態總表

```
Research design / specification    ≈ COMPLETE
Master preregistration              FROZEN v1.9
External data blockers              V-1b CLOSED / D-1 CLOSED  ✅
Remaining data item                 none — O-F closed v1.11 (C-41)        ✅
Corporate-action semantics          FROZEN
Market-state semantics (O-E)        FROZEN

B-09 / B-06 / B-12 / B-14 / B-17 / B-19 / B-21    FROZEN
B-18 protocol                                      FROZEN
W-1 ~ W-4 corporate-action semantics               FROZEN
O-1 / V-1a / V-2 / V-3 / V-4 / V-5 / V-6           FROZEN
M-1 / M-2 / M-3                                    FROZEN（v1.0 新增）
O-A / O-B / O-C / O-D                              FROZEN（v1.1，P-1a）
O-E / O-E-1 market state                           FROZEN（v1.2）

V-1b stock-dividend source                         CLOSED
D-1 price-universe survivorship                    ✅ SATISFIED（v1.9）
O-F status-source delisting coverage               ✅ CLOSED — fail-loud on exposure (C-41)
Corporate-action specification                     FROZEN
Corporate-action standalone test                   PASSED
Corporate-action route integration                 PENDING P-1b
S-1 selection free parameters                      ✅ FROZEN（規格完備,非路徑遵守）
S-3a data semantics                                ✅ SATISFIED
S-3b end-to-end enforcement                        ✅ SATISFIED（enforcement 準則，C-44）

O-A / O-B / O-C / O-D                              FROZEN（v1.1，P-1a）
C-16 ~ C-20 omission corrections                   FROZEN（v1.3，P-1b）
  · target drift = rebalance to 5% each decision
  · PEG / eps_growth definitions
  · feature orientations（方向綁定定義，非呼叫端選項）
  · F10 relocate：net_margin 腿已凍，其餘三腿 OPEN
C-21 ~ C-27 A/B/C resolutions                      FROZEN（v1.4）
  · Quality TTM 三項 + 當期兩項（含 closure/legacy 衝突揭露）
  · revenue_yoy 單月 · 12-1 price momentum
  · ADV20（已觀測 20 session）· σ20D（B-14 P3,未年化）
  · pending_exit cap = 執行當日自身 ADV20
  ⇒ 十一個 feature 成員全部有凍結公式
C-28 ~ C-35 final D rulings                        FROZEN（v1.5）
  · σ20D ddof=1（specification completion,非 tunable）
  · 風險層:金融業豁免/負債條件樹/cash_quality 全部移除
  · 現金不足買單依 Selection rank · 平手 stock_id ascending
  · 股數 floor 至 1 股,5% 為已執行部位的 hard cap
  · feature 百分位平手取平均名次,不依賴 row order
C-36 risk layer 定案                               FROZEN（v1.6）
  · 最終基本面 hard filter 只有 net_margin < −10
  · 負債樹/cash_quality/current-ratio 下限/金融業豁免 全部移除
  · 移除豁免 ≠ 該規則變成無條件(明文否定)
  ⇒ OPEN SPEC ITEMS = 0,S-1 轉綠且可檢查
C-37 P-2 shared route + 兩個 adapter               BUILT（v1.7）
  · core/b0_route.py = 全庫唯一依序呼叫四層的地方
  · adapter 只做 source→驗證→canonical state
  · AST 禁止 adapter import 任何 canonical layer
  · B-20 route pair 已宣告並附 deterministic fixture
  · S-3b 守衛已接入 NAV 路徑,並在真實證券上證得 enforcement(C-44)

Remaining:
D-1 re-export 2019-2026 incl. delisted             DATA / BLOCKING
P-1b-U canonical core specification                ✅ CLOSED（0 open items）
P-1b canonical core code                           IMPLEMENTED（四層 + state）
P-2 shared engine                                  ✅ BUILT（v1.7）
B-20 fixture parity                                ✅ PASS（bit-exact,float_tol=0）
B-20 real-data parity                              BLOCKED by D-1
S-3b route enforcement                             ✅ SATISFIED (C-44)
value_pbr 2019+ lineage                            ✅ CLOSED（v1.15,C-48）
value_per 2019+ lineage                            ✅ CLOSED（v1.16,C-49）
L2 sealed-input materializer (141 期)              ✅ 141/141 market-side states sealed
momentum 價格調整規則 (C-50)                        ✅ CLOSED（v1.17,R1~R8 + 12 條測試）
配股 holder multiplier 來源 (C-51)                  ✅ CLOSED（v1.18,R1~R6 + 8 條 negative control）
Baseline Seal 不可覆蓋歸檔 (C-52)                   ✅ CLOSED（v1.19,content-addressed）
開倉狀態日期接縫 (C-53)                             ✅ CLOSED（v1.19,period-1 邊界規則）
  industry PIT / price panel / valuation panel      ✅ SEALED（三份 receipt 皆已綁 hash）
  bonus share panel                                 ✅ SEALED（1,383 payload,0 transport failure）
B0 Baseline Seal (pre-L2)                          FINALIZATION — v1.14 起可達(C-47)
L2 Run Provenance                                  待使用者明示開封 L2 後才存在

L2                                                 STILL SEALED
```

### 13.2 凍結時的產物雜湊

| 產物 | sha256 | bytes |
|---|---|---|
| `data/b0/corporate_actions_ledger.csv` | `f426dbc659c68bd7f1cce0db0cff3254b1d517025cf1cff2f2cd89f9d4c1f06c` | 5,267,513 |
| `data/b0/stock_dividend_pit.csv` | `783d7cc2785f9faeff637529e66138e69c70f9c3a1a4df1001a1b19b7a50a0ec` | 645,524 |

上游 `配股相關` 七個 zip 的雜湊見 `research/p0_v1b_stock_dividend/corporate_action_provenance.json`。

**本文件自身的 `spec_sha256` 於凍結時另行計算並記入 `research/b0_registry/master_prereg_freeze.json`**（文件無法包含自身雜湊）。

### 13.3 下一步

```
Master prereg FROZEN v1.2（本文件）
  → D-1：重新匯出 2019-2026 價格並納入下市證券（阻擋 seal 與 L2，不擋 P-1b）
  → P-1b 建四層 canonical core（責任邊界見 §8.7）
      · corporate_action_transition stage 接上兩個守衛（§6.1）
      · 日內序列接上 assert_intraday_order（§6.6）
  → B0_ENTRY_MODULES 加入 route entry → 全部不變量自動生效
  → P-2：retrospective / production 兩個 adapter 供料同一 core
  → B-20 真實 fixture parity（比對 adapter 邊界，非兩套演算法）
  → L1 全綠（S-1..S-8）
  → B0 BASELINE SEAL（含 route、clean tree、L2 opening protocol；execution/output 明記 NOT_*_PRE_L2）
  → 才有資格開 L2 一次
  → L2 RUN PROVENANCE（引用 baseline_seal_sha256，補上 execution/output）
```

**此後階段由「研究規格設計」切換為「照規格施工 B0 canonical engine」。§1.5 自此生效：施工階段不得創造規格。**

---

### M-2 · L2 outcome vocabulary（v1.21）

> **v1.21 · M-2 outcome vocabulary。** §6.1.14 於 v1.20 以文字定義了兩個正式結果，
> 但機器詞彙未同步擴充，致首次 sealed L2 run **無法記錄自身的終局結果**。
> 現將 §6.1.14 已定義的**兩個 exact names 原樣**加入：
>
> ```
> NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK   §6.1.14 F-CA-B
> RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE        §6.1.14 F-CA-C
> ```
>
> **不改名、不泛化。** 刻意**不**建立 `RUN_INVALID_*` 家族 ——
> 一旦建立就必須另裁哪些 defect 算 INVALID、哪些算 NOT_EVALUABLE、
> 哪些消耗 once-only observation、哪些允許重新 seal／rerun、precedence 如何排序，
> 而這五個問題目前都不在爭議中，泛化只會無謂擴大 governance surface。
>
> 三個原有 outcome 的拼寫完全不變。


---

### 9.6a Non-consumption of the once-only observation（v1.22，規範性）

> **Status: NORMATIVE.** 由 M-3 `l2_reopening_after_run_invalid` 的裁決導出。
> 首次 sealed L2 run `L2-2520c80aa980d681` 走完 141 期，**每一期 complete-case
> 排除 100% 母體**：從未在非空集合上形成 SelectionScore、沒有 target 或 executed
> portfolio、沒有任何持倉、未計算或檢視任何 CAGR／Sharpe／MDD／benchmark。

#### §9.6a-R1 · 裁決

該 run **未消耗** once-only L2 effective observation。
它仍然是一次 **attempted L2 execution**，
**永久保留於 provenance —— 不刪除、不覆蓋、不改標籤**，
但依 B-18 §4.3 **不是**一次 effective observation。

#### §9.6a-R2 · 這條規則是窄的

`RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE` 之**不消耗**，
**僅在以下七項全部成立時**方為真：

```
1  zero effective strategy decision observations
2  no strategy-dependent portfolio, NAV, return, performance metric,
   benchmark comparison, or other strategy-outcome information was
   produced or viewed                                （定義見 §9.6a-R2a）
3  the defect is an implementation / input-conformance failure against
   semantics that were ALREADY FROZEN before the invalid run
4  repair does not depend on observed strategy performance
5  the invalid run remains immutable
6  a new Baseline Seal is taken
7  fresh explicit user authorization is required
```

> **不得**泛化為「crashed runs never count」。
> 一次已經在非空母體上算出橫斷面分數的 run，**已經看過**這個窗口，
> 之後拋什麼例外都不改變這件事。
> 其餘四個 outcome **永遠**消耗；`NOT_EVALUABLE_*` 兩者雖然同樣
> non-evidential（對策略不構成證據），**仍然計入有效觀察次數** ——
> **non-evidential 與 non-consuming 是兩個不同性質**。

**七項條件依「哪個機制真的能檢查它」分工，全部必要：**

| 條件 | 強制點 | 強制種類 |
|---|---|---|
| 1、3、4、5 | `NonConsumptionAttestation` + `assert_non_consumption_admissible` | `attested` |
| **2** | 同上，**再加** `verify_opening_state_restatement()` 直接讀 invalid run 的不可變 artefact | **`attested_and_verified`** |
| 6 ~ 7 | `assert_reopening_admissible`（**比對兩個 seal identity**，並要求具名 authorization） | 呼叫點強制 |

> 條件 6 寫成「我已取得新 seal」的 boolean 毫無價值 —— 它在新 seal 存在之前就會被寫下，
> 那是承諾偽裝成觀察。**比對兩個 seal hash 才是檢查。**

#### §9.6a-R2a · condition 2 的定義（v1.23，規範性）

> **為什麼需要這一節。** v1.22 的 condition 2 寫的是
> 「no portfolio / NAV / performance **information** produced or viewed」，
> 而 `information` **從未被定義**。這在手上這個 run 就已經產生兩種相反的讀法：
> `artifacts/l2_run/nav_series.json` **確實存在**、確實有 141 列 —— 字面讀法下
> condition 2 為假；但那 141 列**每一列都是 sealed opening cash、零部位**，
> 沒有任何「必須先做出有效 B0 決策才可能知道」的量 —— strategy-dependent 讀法下為真。
> **裁為後者。** 一個名為 `nav_series.json` 的檔案存在，本身不構成一次
> effective L2 observation。

**規範定義：**

```
No strategy-dependent portfolio, NAV, return, performance metric,
benchmark comparison, or other strategy-outcome information was
produced or viewed.

A deterministic restatement of the sealed opening economic state,
produced before any effective strategy decision, is not
strategy-outcome information.
```

**§9.6a-R2a-i · restatement 的 admissibility（八項全部必要）**

opening-state restatement 僅在**所記錄的每一列**在經濟上與 sealed opening state
完全相同時方為 admissible：

```
same cash                              no executed portfolio
zero positions                         no strategy-generated return
no pending strategy-generated holdings no benchmark-relative quantity
no target portfolio                    no performance metric
```

**時間戳／日期推進本身不使紀錄成為 strategy-dependent。**

**§9.6a-R2a-ii · negative boundary（任一成立則 condition 2 為假）**

```
any non-empty strategy portfolio
any NAV change caused by B0 decisions / execution
any strategy return
any target / execution result
any performance metric
any benchmark comparison
any other quantity that could only be known after an effective B0 decision
```

> **不得**泛化為「NAV 是常數就等於不消耗」。
> 一條**平**在某個「策略交易出來的水位」上的 NAV 仍然是 strategy-outcome information。
> 因此判準是**與 sealed opening cash 相等**，而不是「是否為常數」——
> `tests/test_b0_condition_two.py` 有一條專門的 negative control 打這個誤讀。

**§9.6a-R2a-iii · 機器強制（R5）**

condition 2 **不得**只留一個未被檢查的 attestation boolean。
`core.b0_master_prereg.verify_opening_state_restatement()` 直接讀 invalid run 的
不可變 artefact（`nav_series.json`、`period_progress.jsonl`、`final_result.json`），
逐列檢查上述兩組清單，**牴觸即 raise `ConditionTwoContradicted`**。

```
attestation      可以「摘要」結論
artefact         決定結論
兩者相左          以 artefact 為準，且 reopening gate MUST fail
artefact 缺席     在 reopening gate MUST fail
                 —— 「我無法檢查」不等於「我檢查過了」
```

必要 negative control（全部落地於 `tests/test_b0_condition_two.py`）：
opening-state-only 141 列 restatement → non-consuming；
任一非零部位 → consuming；
任一 strategy-dependent NAV 變動 → consuming；
任一 strategy return／performance／benchmark 結果 → consuming。

**§9.6a-R2a-iv · 既有 invalid run 的機械驗證結果**

```
rows checked                              282  （141 nav + 141 period_progress）
distinct port_value / cash_after 值        {2000000.0}  = sealed opening cash
distinct position counts                   {0}
strategy-outcome row keys found            []
final_result.performance_computed          false
final_result.receipts_total                0
final_result.positions_held_any_period     0
```

**因此 condition 2 = SATISFIED**，
`attempted_openings = 1`、`effective_observation_count = 0` 予以保留。

**§9.6a-R2a-v · provenance（R6）**

`artifacts/l2_run/final_result.json` 與 `artifacts/l2_run/nav_series.json`
**位元組完全未動**。前者至今仍寫著 `l2_opening_consumed: true`。
本裁決**透過既有 attestation／governance lineage 取代**該保守判讀，
**不改寫歷史** —— 去改它會消滅「兩者曾經不一致」這件事本身的證據。

#### §9.6a-R3 · 記在旁邊，不寫進原紀錄

non-consumption 判定以 **`NonConsumptionAttestation`** 追加至
`research/b0_registry/l2_nonconsumption_ledger.jsonl`，
**opening registry 的原始列保持位元組不變**。

> invalid run 的 `final_result.json` 至今仍寫著 `l2_opening_consumed: true` ——
> 那是 runner 終止當下的保守預設值。**本裁決取代該欄位，而該 artefact 未被修改。**
> 去改它會消滅「兩者曾經不一致」這件事本身的證據。

`effective_observation_count()` = registry 列數 −
（**列自身 outcome 也在 `NON_CONSUMING_OUTCOMES` 內**的已具結列）。
錯置的 attestation 因此無法讓一個已判決的窗口退場。

#### §9.6a-R4 · 關閉此項不等於授權

M-3 `l2_reopening_after_run_invalid` 以 **NOT_CONSUMED** 結案，
`L2_opening` 因此**在機械上**解除阻擋。
**本裁決不自行授予任何 opening。** §6.1.14 的要求原封不動：
必要的 conformance repair、**新的有效 Baseline Seal**、**全新明示授權**。

---

### 9.6b Deterministic provenance bytes（v1.22，規範性）

> **Status: NORMATIVE.** 由本次發現的 provenance 缺陷導出。

`record_opening` 以**文字模式** handle 寫入 L2 opening registry，
於 Windows 將每個 `\n` 轉為 `\r\n`：**同一份邏輯紀錄在不同平台產生不同位元組、
因而不同 hash**，而這個檔案的全部用途就是當 provenance 紀錄。
`.gitattributes` 早已把 LF 凍結為 repository canonical representation
（正因為 seal 綁的是 raw bytes），寫入端只是沒有遵守。

```
所有 L2 opening / run provenance 紀錄 MUST 以 canonical LF bytes 寫出
單一 primitive：core.b0_master_prereg.append_provenance_record / write_provenance_json
寫入模式：BINARY（"ab" / "wb"）
編碼：utf-8            行尾：PROVENANCE_LINE_TERMINATOR = LF
一筆紀錄 = 剛好一行，且只有一個行尾
```

**用 binary 模式而非 `newline=` 參數**，理由是實測的：runner 的 `_jsonl`
當時**帶對了** `newline` 參數，registry 寫入端沒帶 —— 一個每個呼叫端各自重新實作的
位元組規則，就是一個遲早有呼叫端會寫錯的規則。**bytes payload 無法被靜默轉換。**

必要測試（`tests/test_b0_provenance_bytes.py`）：
不得產生 CRLF；相同邏輯紀錄 → 相同位元組與相同 sha256；
**寫出的位元組等於在記憶體中算出的 canonical 位元組**（這一條才是與平台無關的證明，
`b"\r\n" not in raw` 只證明跑這次的那台機器）；
以及對實際 artefact 的掃描，涵蓋本模組不擁有的寫入端。

> 既有的 `l2_opening_registry.jsonl` 工作區檔案已還原為 **HEAD 已存的 LF 位元組**。
> 這不是改紀錄：還原前已逐位元組驗證
> `working.replace(CRLF, LF) == HEAD`，內容完全相同，只有行尾不同。

---

### C-56 · M-3 `l2_reopening_after_run_invalid` 裁決落地（v1.22）

- **來源：** run `L2-2520c80aa980d681` 以 §6.1.14 F-CA-C 終止。§6.1.14 寫了
  re-opening **路徑**，但沒說 invalid run 是否消耗 once-only observation；
  而 M-2 的 `assert_rerun_admissible` **完全無法表達**這個案例 ——
  它只在附帶 `DataRepair` 時允許重跑，而 `DataRepair` 的 admissible scope 是**資料**，
  這次缺陷是 producer / input-shape，**沒有資料可修**。
- **變更：**
  1. §9.6a：NOT CONSUMED，七項條件的 narrow rule，attestation ledger，
     `effective_observation_count()`。
  2. §9.5 重跑表擴充為四列並標明 repair kind 與是否消耗；
     §9.6「都計入有效觀察次數」在該窄情形下由 §9.6a 取代。
  3. M-2 新增 `ImplementationConformanceRepair`（六欄位、無預設值）與
     `assert_conformance_repair_admissible`；`assert_rerun_admissible` 依 outcome
     **分派** repair kind；新增 `assert_reopening_admissible` 強制條件 6、7。
  4. §9.6b：L2 provenance 位元組規則，單一 binary LF primitive。
  5. M-3 finalization register 回到空。
- **理由：** 消耗與否若由實作者決定，就是實作者在決定「這個窗口可以看幾次」——
  M-3 存在的理由。裁決之後，**留下的不是判斷，是機制**。
- **相容性：** 未更動任何 factor 定義、權重、門檻、portfolio construction、
  execution、成本、universe 規則或 corporate-action 語義。
  三個原有 outcome 拼寫不變；`NOT_EVALUABLE_*` 的消耗語義不變。
  141-state composed hash 不因本次裁決改變（本次不動 sealed input 內容）。


---

### C-57 · M-3 condition 2 語義裁決落地（v1.23）

- **來源：** v1.22 §9.6a-R2 condition 2 只寫 `information` 且未定義，
  兩種讀法對同一個 run 給出相反結論。機器層更弱：condition 2 只是一個
  `bool`，`assert_non_consumption_admissible` 只檢查它為真，
  **完全沒有實作這個條件的語義**。
- **變更：**
  1. §9.6a-R2a：condition 2 的規範定義、restatement admissibility 八項、
     negative boundary 七項。
  2. `verify_opening_state_restatement()` 與 `ConditionTwoContradicted`；
     condition 2 由 `attested` 升為 `attested_and_verified`。
  3. `effective_observation_count()` 在 artefact 可讀時驗證，牴觸即 raise；
     `assert_reopening_admissible()` **要求** artefact 在場並通過。
  4. 四組 negative control + 「常數 NAV 但水位錯」的專屬反例。
- **理由：** 一個未定義的名詞在 governance 文件裡不是模糊，是**自由參數**——
  它讓實作者可以事後選一種讀法。定義寫死之後，**留下的不是判斷，是機制**。
- **相容性：** 未更動任何 factor 定義、權重、門檻、portfolio construction、
  execution、成本、universe 規則或 corporate-action 語義。
  七項條件的**編號與數量不變**；condition 2 的**識別名不變**
  （`no_portfolio_nav_or_performance_produced_or_viewed`），
  因此既有 attestation 帳本列可原樣讀回。
  141-state composed hash 不因本次裁決改變。


---

### 9.6c L2 run-scoped immutable provenance（v1.24，規範性）

> **Status: NORMATIVE.** 由 pre-open STOP 導出。該次 STOP 是正確的：
> **未建立任何 opening record**，因此
> `attempted_openings` 不變、`effective_observation_count` 維持 0、
> **once-only opening opportunity 未被消耗**。

#### §9.6c-R0 · 缺陷是儲存模型，不是這次事件

runner 只有一個可變的全域輸出目錄 `artifacts/l2_run/`。第二個 run 會：

```
append  period_progress.jsonl   ← 新列混入前一個 run 的列
覆寫    nav_series.json
覆寫    final_result.json
覆寫    opening_record.json
```

**這與第一個 run 成功或失敗完全無關。** invalid run 只是把它暴露出來的那一個。
最嚴重的後果是：`verify_opening_state_restatement` 會讀**整個** progress 檔，
第二個 run 只要持有一個部位，第一個 run 的 condition 2 立刻變成假 ——
**`effective_observation_count == 0` 的機械證據會被「再跑一次」這個動作本身銷毀。**

#### §9.6c-R1 · 首次 invalid run 原地保留

```
artifacts/l2_run/opening_record.json      af0fcf7d…  1011 bytes
artifacts/l2_run/period_progress.jsonl    ec1a8a3e… 44730 bytes
artifacts/l2_run/nav_series.json          8df67336… 17768 bytes
artifacts/l2_run/final_result.json        2e7f11fd…  2666 bytes
```

**不得** move / rename / rewrite / normalize / copy-over / truncate。
保留於**根目錄原地**，因為搬動會使 Master、attestation ledger 與治理文字中
已記載的每一個路徑失效。
四個 sha256 **pin 進 normative module**，因此 seal 直接綁住它們：
第一次 invalid run 的位元組再也無法在不改變規格自身 identity 的情況下漂移。

#### §9.6c-R2 · 未來 run 的版面

```
artifacts/l2_run/runs/<run_id>/
    opening_record.json      period_progress.jsonl
    nav_series.json          final_result.json
    receipts                 post-run provenance
```

任何未來的 run **不得** append 或覆寫 legacy root artefact，
亦**不得**碰另一個 run 的目錄。

#### §9.6c-R3 · run identity 是排他的

`<run_id>` 精確對應一個不可變目錄。目錄建立**必須是排他操作**
（`os.makedirs` 不帶 `exist_ok` —— 檢查與宣告是同一個動作，
兩個 writer 不可能同時判定目錄是空的）。
若目標目錄已存在：

```
STOP BEFORE WRITING
```

不得 reuse / clear / overwrite / merge / append across runs。
新 run 亦**不得**宣稱 legacy run 的 identity。

#### §9.6c-R4 · reader 綁定被裁決的那一個 run

verifier、attestation 邏輯、effective-observation 計算與 reopening gate
**必須**檢查**被裁決的那個 run 自己的** artefact。
首次 invalid run 的 condition 2 **永遠**綁在它自己的不可變 artefact 與 hash 上，
**不得**以最新／當前 run 替代。

provenance 以三者明示綁定：

```
run_id                canonical identity
artefact identity/path
artefact hashes
```

**`latest` 指標即使存在也是 non-canonical，不得決定治理 identity。**
`verify_opening_state_restatement()` 在未指名 run 時**拒絕執行**而非取用預設。

#### §9.6c-R5 · 跨 run 隔離測試

必要測試（`tests/test_b0_l2_run_layout.py`）：

```
snapshot run A hashes → create/write run B → run A 每一位元組不變
run B progress 不 append 進 run A
run B NAV 不取代 run A NAV
run B final result 不取代 run A result
run_id 碰撞 → 在任何 artefact 變動之前失敗
```

**每一項都同時對兩種 prior run 施測：invalid prior run 與
一般已完成 prior run（持有部位、有報酬）。**
只保護 invalid run 的修法會通過前者、在後者失敗 ——
那正是「修好儲存模型」與「替這次事件打補丁」的分界。

---

### C-58 · L2 run-scoped immutable provenance（v1.24）

- **來源：** 正式 L2 授權下的 pre-open verification 23/23 全過，
  但在建立 opening record **之前**發現：照現況執行會覆寫並污染
  第一次 invalid run 的不可變 provenance，
  而修它會弄髒工作區、破壞綁定 commit 與 Baseline Seal。
  授權明文禁止「repair and continue within the same authorization」，故 STOP。
- **變更：** 新增第 28 個 normative module `core/b0_l2_run_layout.py`；
  runner 移除全域 `OUT`，改為 `run_id` 必填（無 `latest` 預設）；
  新增 `scripts/b0_open_l2.py` 使開倉可重現且目錄以排他方式宣告；
  condition-2 verifier 與 reopening gate 改為 run-aware 並回報 artefact hash。
- **理由：** 「第二個 run 不覆蓋 invalid run」是症狀測試；
  **一個 run 一個不可變目錄**才是規則。
- **相容性：** 未更動任何 factor 定義、權重、門檻、portfolio construction、
  execution、成本、universe 規則、PIT 或 corporate-action 語義。
  141-state composed hash 不因本次裁決改變。
  `attempted_openings` 與 `effective_observation_count` 皆不變。


---

### 9.6d L2 opening / execution protocol（v1.25，規範性）

> **Status: NORMATIVE.** 由 pre-authorization read-only review 導出。
> 該次 review 的 STOP 是正確的且無成本：**未建立任何 opening**，
> `attempted_openings` 不變、`effective_observation_count` 維持 0、
> once-only opening opportunity 未被消耗、performance exposure 為零。

> **C-58 修好了儲存模型，沒有修好交接。** run 各自有目錄之後，
> opener → runner 這道交接**本身仍然不是一個受檢查的協定**：
> 目錄可以存在而什麼都沒有正式開過；`attempted_openings` 由**終局** registry 列計算，
> 所以一次 process 中途死掉的 opening **對它自己剛花掉的預算是隱形的**；
> runner 用同一個 run_id 再跑一次會從 period 1 重來、append 第二段 progress、覆寫 NAV。

#### §9.6d-R1 · 正式 opening 是一個事件

```
artifacts/l2_run/opening_claims/<baseline_seal_sha256>.json
```

**L2 formal opening boundary = 這個 canonical opening claim 建立成功。**
不是 run 目錄建立，也不是終局 registry 插入。
以 `O_CREAT|O_EXCL` 建立 —— **檢查與宣告是同一個 syscall**，
因此兩個帶不同 run_id 的 opener 併發時，**只有一個能正式開窗**。

claim 至少綁定：

```
run_id                          baseline_seal_sha256
opening_record_sha256           spec_sha256
commit_sha                      141-state composed hash
period-1 full-input hash        authorization identity
opened_at
```

**同一個 Baseline Seal → 至多一個 opening claim。**

#### §9.6d-R2 · opening record 與 pre-opening orphan

opener 仍是 `artifacts/l2_run/runs/<run_id>/` 的**唯一**建立者。
順序為：**排他建立目錄 → 寫 opening_record → 取其 canonical hash →
排他建立 opening claim 並把該 hash pin 進去**。

> **有 run 目錄或 opening record、但沒有 canonical opening claim 者 = pre-opening orphan。**
> 它**不計入** attempted opening，runner **拒絕執行**它。

#### §9.6d-R3 · attempted opening 的計算

**不得**以終局 outcome registry 列定義 attempted openings。
identity 由**實際發生的不可變 opening 事件**導出：

```
legacy pinned attempt（首次 invalid run，早於本協定，無 claim 檔）
+ 所有 valid canonical opening claims
依 run_id 去重
```

必要行為：

```
opener 成功建立 canonical opening claim
runner 從未啟動 / process 死亡
→ attempted_openings 已經 +1
```

**不得要求終局結果存在。**
首次 invalid attempt 以 pinned legacy attempt 保留，**不重寫、不捏造**其歷史 artefact。

#### §9.6d-R4 · 結構性單一建立者

generic provenance writer **不得**具備隱式建立 `runs/<run_id>/` 的能力。
run-scoped writer **必須**要求目錄已存在。

> 先前「只有 opener 會建立」為真，**只因為 `resolve_run_dir` 剛好先 raise**。
> 呼叫順序不是結構。現在檢查落在**寫入點本身**，無論從哪條路徑到達都成立。

#### §9.6d-R5 · runner admission

在**任何 execution period 寫入之前**，runner 必須驗證：

```
run_id                     opening_record hash（與 claim pin 的值相符）
Baseline Seal identity     spec identity
bound commit / HEAD        clean repo identity
141-state composed         period-1 full-input identity
opening / reopening governance admissibility
```

missing / malformed / foreign-run / hash-mismatched / seal-mismatched /
spec-mismatched / commit-mismatched **一律在 period 1 之前失敗**。
**不得** fallback 到 latest 或其他 run。

#### §9.6d-R6 · 一次性執行

```
artifacts/l2_run/runs/<run_id>/execution_claim.json
```

admission 通過之後、**任何 period／execution 輸出之前**，以排他方式建立。
已存在則：

```
STOP BEFORE ANY NEW EXECUTION WRITE
```

同一 run_id **永不**得靜默地從 period 1 重啟、append 第二段 progress、
覆寫 NAV 或執行兩次。**不引入任何自動 resume / retry 語義。**

> **execution claim 存在而 terminal result 不存在**（process 中斷）：
> 顯式偵測，並以 **M-3 abort**。
> 規格**未唯一決定**這種 run 是否消耗 observation、是否可續跑、從哪一期續 ——
> 在這裡自創 rerun 規則，等於實作者在決定這個窗口可以被看幾次。
> 機械強制：`UnresolvedExecutionClaim`。

#### §9.6d-R7 · state 由事件導出

**不得**以可變 `state` 欄位作為 canonical execution state。

```
canonical opening claim 存在   → OPENED
execution claim 存在           → EXECUTION_CLAIMED
不可變 terminal result 存在     → TERMINAL
```

轉移為單調。opening record 裡即使被寫入 `state` 欄位也**不被採用**。

---

### C-59 · L2 opener/runner protocol conformance repair（v1.25）

- **來源：** 授權前 read-only review 在建立任何 opening **之前**發現三個缺陷：
  runner admission 只比對 `run_id`（seal / commit / spec / opening state 全無驗證）；
  `record_opening` **在整個 repo 沒有任何非測試呼叫者**，
  因此 `attempted_openings` 永遠不會因一次 opening 而變動；
  同一 run_id 重跑會 append + 覆寫 + 從 period 1 重來。
- **變更：** 見 §9.6d-R1 ~ R7。`core/b0_l2_run_layout.py` 取得
  opening claim / execution claim / admission / derived state；
  opener 改以 claim 為 opening boundary；
  runner 取得 admission、execution claim 與不可變 terminal result（並在終止時寫入 registry 列）；
  seal 的 `attempted_openings_recorded` 改由事件計算。
- **理由：** 這是一次 `ImplementationConformanceRepair` ——
  被 conform 的語義（once-only、immutable provenance、no post-hoc rescue）
  在缺陷發生**之前**就已凍結，缺的是機制。
- **相容性：** 未更動 factor 定義、feature 輸入、權重、門檻、eligibility、ranking、
  universe、portfolio construction、order execution 語義、成本、PIT、
  corporate actions、benchmark 或 performance gate。
  141-state composed hash 不變；legacy invalid run 四個 artefact 位元組不變；
  `attempted_openings = 1`、`effective_observation_count = 0` 不變。
