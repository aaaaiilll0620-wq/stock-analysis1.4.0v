# B-09 Factor Architecture Closure — Phase 1

**狀態:`PHASE 1 COMPLETE — 待審`。這不是預註冊,不是 B 規格,不構成任何授權。**
**日期:** 2026-08-17
**授權依據:** 使用者 2026-08-17 指示「立即開始 B-09 Factor Architecture Closure Phase 1」。

## 0. Phase 1 合規聲明

**允許且實際使用的判定依據:** code / file:line 重驗、economic semantics、horizon 分類、standard external definition、PIT/data dependency。

**禁止且實際未使用:** 報酬、IC、Sharpe、CAGR/MDD、選股名單、A0–A3、任何 feature parameter sweep。

**本輪未執行任何回測、未計算任何績效或選股結果、未產生任何 A0–A3 產物。** 唯讀讀取程式碼。

> **⚠ 一項必須先講清楚的處理原則。** 現行程式碼的**註解裡本身就寫滿了 IC 與多空報酬數字**(例:`scoring_manager.py:40-53`、`regime.py:27-33`、`valuation.py:167-172`)。本文件**引用這些數字時,只作為「該參數是被結果擬合出來的」之證據**(見 §4 污染登記簿),**絕不**作為任何 keep/relocate/remove 裁決的理由。所有裁決理由限於 concept / horizon / standard definition / PIT —— 逐項可查。

**B-07 依使用者裁決正式標記 `SUBSUMED BY B-09`**(見 §5.3)。

---

## 1. 本輪 `[S]` → `[V]` 升級清單

下列先前僅引自 SystemMap(2026-08-11 快照)的項目,本輪已逐行讀原始碼確認,全部升為 `[V]`:

| 項目 | 驗證位置 |
|---|---|
| 技術面 8 個計分子項與配分 | `core/scoring_manager.py:94-153` |
| 技術面停用開關 `USE_BBP` / `USE_KD_FULL` | `core/scoring_manager.py:18-19`(值 `False`),消費點 `:138-152` |
| 動能面 A/A2/B/C 四塊、12 個子項 | `core/scoring_manager.py:204-289` |
| 動能面停用開關 `USE_OBV_TREND` | `core/scoring_manager.py:20`(值 `False`),消費點 `:285-286` |
| `USE_RS_OVERLAY` 啟用 | `core/scoring_manager.py:17`(值 `True`),消費點 `:236-244` |
| 籌碼面基底 + 7 個確認子項 | `core/scoring_manager.py:321-377` |
| `_HORIZON_WEIGHTS` / `_RATIO_TO_POINTS` | `core/scoring_manager.py:298-299` |
| TDCC 確認層恆為 0 | `core/scoring_manager.py:368-376`(邏輯存在,輸入 `big_holder_weekly_change` 恆 0) |
| 基本面四組權重與 hard filter | `core/fundamentals.py:30-64` |
| `USE_ASSET_TURNOVER` 啟用 | `core/fundamentals.py:26`(值 `True`) |
| 估值面三層退回鏈與 PEG/位階混比 | `core/valuation.py:81-190` |
| `REGIME_MULTIPLIERS` 三檔值 | `core/regime.py:24-34` |
| `composite_weights` 消費點 | `core/backtest.py:711`、`core/score_store.py:103,117`、`beat_0050/realbody/build_arm_panel.py:462` |
| c2 四腳與五因子聯集 | `scripts/universe_screen_daily.py:292-310` |
| `ORDER_ADV_CAP` / `FUSION_PCT` / `TOP_N` | `scripts/l4a_decision.py:43-54` |

**另有一項先前描述不精確,本輪更正:** 系統有**兩套權重**,不是一套 —— `MODES[mode]["weights"]`(三維:technical/momentum/whale,`scoring_manager.py:47`,供 `calculate_score` 的 `total_score`)與 `MODES[mode]["composite_weights"]`(五維,`:53`,供 `real_composite`)。`build_arm_panel.py:460` 的註解已標明此區別。**B 相關的是後者**,但前者仍在生產路徑上驅動 `total_score` → 四級評級。

---

## 2. 決定性結構發現:現行架構不是「五個等價的 alpha 維度」

逐行讀完後,五個「維度」在 **concept / horizon / role** 三個軸上都不是同一種東西:

| 維度 | 內含 horizon | 內含 role | 是否單一概念 |
|---|---|---|---|
| 基本面 | 季(財報) | Selection | **是**(四個財務組,概念一致) |
| 估值 | 季 + 跨期位階 | Selection | **是** |
| 技術面 | 日~週(MA5/MA20/RSI/MACD/布林) | **Timing** | **是**,但角色被錯置成 Selection |
| 動能面 | **6M + 3M + 月營收 + 20D + 單日** | **Selection + Timing 混合** | **否 —— 至少三種 horizon、兩種 role 混在一個 bucket** |
| 籌碼 | 1/3/5/10/20 日 | **Confirmation** | 是(概念一致),但角色被錯置成 Selection |

**動能面是唯一「內部就不自洽」的維度**,而且不自洽是**設計上的**:
- (A) `mom_6m`/`mom_3m` = 中期價格動能 → Selection alpha,horizon 3–6 月
- (A2) `rs_6m`/`rs_3m` = 相對強弱 → 同 (A) 的 horizon,但基準不同(vs 0050)
- (B) `revenue_accel`/`cum_yoy`/`streak` = **營收成長** → 這是**基本面成長**概念,不是價格動能,horizon 月
- (C) `volume_spike`/`ma20_bias`/`volume_divergence`/`kd_j` = 短線價量狀態 → **Timing**,horizon 1–20 日

**(B) 與 (A) 之間沒有任何經濟學上的理由要放在同一個 bucket 並共用一個權重。** (B) 在標準因子分類裡屬 Growth/Quality,(A) 屬 Momentum。把它們平均後再乘一個權重,等於強制兩個不同因子共用同一個曝險係數。

**同一個問題也發生在跨管線層:** c2 的動能腿是 `100 - momentum20_pct`(`universe_screen_daily.py:308` 附近,**反向 20 日**),而 A 腿的動能是**正向 3–6 月**。這在標準文獻裡是兩個**互相獨立且方向相反**的公認效應(短期反轉 vs 中期動能),現行系統把它們分別放在兩條管線、各自叫「動能」,然後做硬交集。**這不是矛盾,是兩個因子被錯誤地共用一個名字。**

---

## 3. 逐子因子清單

欄位:概念 / horizon / 方向 / 角色 / 標準定義 / 現行實作 / 偏離 / PIT / 裁決候選。理由見各表後編號註。

### 3.1 技術面(`scoring_manager.py:94-153`,滿分 ≈98)

| # | 子因子 | 概念 | Horizon | 方向 | 角色 | 標準定義 | 現行實作 | 偏離 | PIT | 裁決候選 |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | 價>MA5 | 短期趨勢 | 5D | + | Timing | 價格 vs 短期均線 | 布林,+10 | 二元化(連續量→階梯) | ✅ 日價 | **Relocate → Timing** |
| T2 | MA5>MA20 | 均線排列 | 5/20D | + | Timing | 同上 | 布林,+10 | 同上 | ✅ | **Relocate → Timing** |
| T3 | 價>MA20 | 中短趨勢 | 20D | + | Timing | 同上 | 布林,+10 | 同上;**與 T1/T2 高度共線** | ✅ | **Relocate → Timing(與 T1/T2 合併為單一趨勢狀態)** |
| T4 | 價>週線MA20 | 中期趨勢 | ~20W | + | Timing | 週線均線 | 布林,+15 | 二元化 | ✅ | **Relocate → Timing** |
| T5 | RSI 位階 | 超買超賣 | 14D | 非單調 | Timing | Wilder RSI(14) | 6 段階梯 0/8/10/15/18/25 | **6 個切點**;非單調形狀為自訂 | ✅ | **Relocate → Timing** |
| T6 | MACD 狀態 | 趨勢動能 | 12/26/9 | + | Timing | 標準 MACD | 4 級 0/8/15/20 | 狀態字串化,3 個切點 | ✅ | **Relocate → Timing** |
| T7 | 布林狀態 | 波動壓縮 | 20D | 非方向 | Timing | Bollinger(20,2) | squeeze +8 / expand +5 | **壓縮給正分是自訂**,標準無方向主張 | ✅ | **Remove 候選**(見註 T-a) |
| T8 | MA20/60 交叉 | 中期趨勢轉折 | 20/60D | + | Timing | 均線交叉 | +6 / −8 | **不對稱**(死叉懲罰 > 金叉獎勵),無標準依據 | ✅ | **Relocate → Timing(對稱化)** |
| T9 | 布林 %B | 帶內位階 | 20D | 非單調 | Timing | Bollinger %B | **停用**(`USE_BBP=False`) | — | ✅ | **Remove**(已停用) |
| T10 | 完整 KD | 隨機指標 | 9D | 非單調 | Timing | Stochastic K/D | **停用**(`USE_KD_FULL=False`) | — | ✅ | **Remove**(已停用) |

**理由註**
- **T-a(T7)**:布林帶收斂在標準定義裡是**波動率狀態**,不含方向主張;現行給 +8 正分等於斷言「壓縮 → 看多」,這在標準定義中不存在。依「不得偏離標準定義」原則,要嘛移除,要嘛改為僅供 Timing 的波動率狀態變數而不給方向分。
- **T-b(T1/T2/T3)**:三者由同一組價格與兩條均線推導,結構上高度共線(價>MA5 且 MA5>MA20 幾乎蘊含 價>MA20)。合併為單一「均線排列狀態」是**結構去重**,非績效判斷。
- **T-c(全表)**:技術面**整體**的角色是 Timing 不是 Selection —— 這是概念層事實(所有子項的 horizon 皆 ≤20 日或週線,且皆為價格狀態而非橫斷面優劣)。現行把它以 0.19 權重併入 selection composite,是角色錯置。

### 3.2 動能面(`scoring_manager.py:204-289`,滿分 100)

| # | 子因子 | 概念 | Horizon | 方向 | 角色 | 標準定義 | 現行實作 | 偏離 | PIT | 裁決候選 |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | `mom_6m` | 價格動能 | 6M | + | **Selection** | 學界標準為 **12-1**(skip 最近 1 月) | 5 段階梯 0/6/12/19/25/30 | **未 skip 最近 1 月**;窗口 6M ≠ 12M | ✅ 日價 | **Keep → Selection Alpha(改標準 12-1)** |
| M2 | `mom_3m` | 價格動能 | 3M | + | Selection | 同上 | 4 段階梯 0/3/7/11/15 | 同上,且與 M1 窗口重疊 | ✅ | **Merge into M1**(註 M-a) |
| M3 | 衰竭抑制 | 動能轉折 | 6M vs 3M | − | Timing | 無公認標準 | `m6>12 且 m3<−5 → −8` | **完全自訂**,2 個切點 | ✅ | **Remove**(註 M-b) |
| M4 | `rs_6m`/`rs_3m` | 相對強弱 | 6M/3M | + | Selection | 相對強度 vs 基準 | 5 段 ±8 | 基準為 0050 單檔;**與 M1 同 horizon 且共線** | ⚠ **需 0050 快取,2019 前曾缺**(2019 斷裂三處之一) | **Merge into M1 或 Remove**(註 M-c) |
| M5 | `revenue_accel` | **營收成長加速** | 月 | + | **Selection(Growth)** | 標準 Growth 因子 | 3 段 0/5/10/14 | **概念屬 Growth,非 Momentum** | ✅ 2013+ 真實公告日 | **Relocate → Selection Alpha / Growth** |
| M6 | `revenue_cum_yoy` | **累計營收成長** | 年至今 | + | **Selection(Growth)** | 標準 Growth 因子 | 3 段 0/4/7/10 | 同上 | ✅ 2013+ | **Relocate → Growth** |
| M7 | `revenue_growth_streak` | 成長持續性 | **無上界** | + | Selection(Growth) | 無公認標準 | 2 段 0/3/6 | **回看無上界**(B-04);自訂 | ✅ 2013+ | **Relocate → Growth + cap 24**(B-04) |
| M8 | `volume_spike` | 量能異常 | 20D | + | **Timing** | 量比 | 3 段,且 **gated by `volume>=500` 張** | 500 張門檻為**自訂規模閘門**,混入流動性語意 | ✅ | **Relocate → Timing;500 張閘門移交 B-06** |
| M9 | `ma20_bias` | 乖離 | 20D | **非單調** | **Timing / Anti-chase** | 標準乖離率 | 6 段,`b>15 → 僅 +1` | **這就是現行唯一的追高抑制**,但以「給少分」而非「扣分」實作 | ✅ | **Relocate → Anti-chase(B-07 subsumed)** |
| M10 | `volume_divergence` / `obv_rising` | 量價背離 | 短 | ∓ | Timing | OBV/量價 | −5 / +5 | 二元 | ✅ | **Relocate → Timing** |
| M11 | `kd_j>100` | 過熱 | 9D | − | Timing/Anti-chase | Stochastic J | −3 | 單一切點 | ✅ | **Relocate → Anti-chase 或 Remove** |
| M12 | OBV 20 日趨勢 | 量能趨勢 | 20D | + | Timing | OBV vs MA | **停用**(`USE_OBV_TREND=False`) | — | ✅ | **Remove**(已停用) |

**理由註**
- **M-a(M2)**:`mom_3m` 與 `mom_6m` 窗口重疊(3M ⊂ 6M),兩者相加等於對最近 3 個月加倍計權。這是**結構性重複計分**,不是兩個獨立訊號。標準做法是單一動能定義。
- **M-b(M3)**:「6 月強但 3 月弱 → 扣 8 分」在標準文獻中無對應定義,且它是用 M1 與 M2 兩個已計分變數再構造的第三個訊號 —— 概念上它想抓的是短期反轉,而短期反轉應由 Anti-chase 層以其標準定義(1M reversal)處理,不是在 momentum bucket 內用自訂交互項。
- **M-c(M4)**:RS 的 horizon 與 M1 相同、輸入亦為價格,兩者測的是同一件事的絕對版與相對版。若 Selection 層已對全母體做橫斷面百分位化(B-16),**相對強弱已內建於橫斷面排序中**,M4 成為冗餘。此外 M4 有 PIT 缺陷(需 0050 快取,2019 前缺)。
- **M-d(M5/M6/M7)**:三者輸入皆為 `monthly_revenue`,概念皆為**營收成長**。它們被放進「動能面」是命名沿襲,不是概念歸屬。標準因子分類中屬 Growth。
- **M-e(M9)**:現行 `ma20_bias` 對 `b>15`(過度追高)給 **+1 分**,仍是**正分**。也就是說系統目前對追高的處理是「少獎勵」而非「懲罰」。這與使用者觀察到的「推薦近日漲幅過大個股」直接一致 —— 是**結構事實**,不需任何績效數字即可確認。

### 3.3 籌碼面(`scoring_manager.py:321-377`)

| # | 子因子 | 概念 | Horizon | 方向 | 角色 | 標準定義 | 現行實作 | 偏離 | PIT | 裁決候選 |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 多天期淨參與率基底 | 法人淨流向 | 1/3/5/10/20D | + | **Confirmation** | 無單一學界標準;業界慣用淨買/成交量 | `48 + Σw_n(fr_n+tr_n) × 300` | **`300` 斜率與 5 個 horizon 權重皆自訂** | ⚠ 分子分母窗不同尺(P0-R4 待查項) | **Keep → Confirmation(重訂為無參數形式)** |
| C2 | 土洋同步 | 一致性確認 | 5/10D | + | Confirmation | 無標準 | `+8` | 自訂 | ✅ | **Remove 候選**(可由 C1 的加總涵蓋) |
| C3 | 連買/連賣天數 | 持續性 | ≤3D | ∓ | Confirmation | 無標準 | ±12,各 cap 3 | 自訂;程式碼註解自承舊版此項會「基底塌陷」 | ✅ | **Remove 候選**(註 C-a) |
| C4 | `whale_concentration` | 投信吸籌比 | 20D | + | Confirmation | 無標準 | +8 / +4 | 2 個切點;**分母為 TDCC 代理** | ❌ **TDCC 可得性未證明** | **Keep,分母改月營收流通在外股數(B-03 3a)** |
| C5 | `institutional_participation` | 法人成交占比 | 10D | + | Confirmation | 無標準 | +4 / +2 | 2 個切點 | ✅ | **Remove 候選**(註 C-b) |
| C6 | `flow_acceleration` | 流入加速 | 5D vs 20D | + | Confirmation | 無標準 | +5,`由賣轉買一律記 2.0` | **「由賣轉買記 2.0」是硬編碼特例** | ✅ | **Remove 候選**(註 C-c) |
| C7 | `volume_concentration` | 上漲日量佔比 | 20D | + | Timing | 無標準 | +3 / −3 | 2 個切點 | ✅ | **Relocate → Timing 或 Remove** |
| C8 | TDCC 大戶週變化 | 大戶持股變動 | 週 | + | Confirmation | TDCC 股權分散 | **恆為 0**(輸入未接線) | 邏輯存在但無效 | ❌ | **Remove**(已失效) |

**理由註**
- **C-a(C3)**:`cap 3` 使此項最多 ±12,而 C1 的基底已經以 1/3/5 日 horizon 涵蓋同一段淨流向 —— 兩者輸入相同、窗口重疊,屬重複計分。
- **C-b(C5)**:法人成交占比測的是**參與程度**不是**方向**;它與 C1(有向淨額)概念不同但被加在同一個 ±15 confirmation 池裡,使方向訊號與強度訊號混合。
- **C-c(C6)**:`由賣轉買一律記 2.0` 是為了避免除以零的硬編碼,但它讓「上期淨賣、本期淨買」的股票**一律**觸發 `>=1.5` 的 +5 加分,與「加速」的原意不符。這是**實作缺陷**,不是因子設計。
- **C-d(全表)**:籌碼面**整體**角色是 Confirmation(它描述的是「誰在買」,不是「這家公司值不值得持有」)。以 0.15 權重併入 selection composite 是角色錯置。

### 3.4 基本面(`fundamentals.py:30-64`)

| # | 子因子 | 概念 | Horizon | 方向 | 角色 | 標準定義 | 現行實作 | 偏離 | PIT | 裁決候選 |
|---|---|---|---|---|---|---|---|---|---|---|
| F1 | `roe` | 獲利能力 | 季/TTM | + | **Selection(Quality)** | 標準 | bounds 5→20 線性 | 上下界自訂 | ⚠ **B-01:現用 45 日固定 lag** | **Keep → Selection Alpha** |
| F2 | `net_margin` | 獲利能力 | 季 | + | Selection(Quality) | 標準 | 0→15 | 同上 | ⚠ B-01 | **Keep** |
| F3 | `gross_margin` | 護城河 | 季 | + | Selection(Quality) | 標準 | 10→30 | 同上 | ⚠ B-01 | **Keep** |
| F4 | `asset_turnover` | 資產效率 | 季年化 | + | Selection(Quality) | 標準 | 0.5→3.0,**金融股豁免** | `USE_ASSET_TURNOVER=True` 為 A/B 擬合開關 | ⚠ B-01 | **Keep(但開關須改為結構決定)** |
| F5 | `rev_cagr` | 成長 | 多期 | + | Selection(Growth) | 標準 | −5→15 | 同上 | ⚠ B-01 | **Keep → 與 M5/M6/M7 併入同一 Growth 層** |
| F6 | `eps_cagr` | 成長 | 多期 | + | Selection(Growth) | 標準 | 0→20 | 同上 | ⚠ B-01 | **Keep → Growth** |
| F7 | `debt_to_asset` | 安全 | 季 | − | Selection(Quality) | 標準 | 60→30(反向) | 同上 | ⚠ B-01 | **Keep** |
| F8 | `current_ratio` | 安全 | 季 | + | Selection(Quality) | 標準 | 100→250 | 同上 | ⚠ B-01 | **Keep** |
| F9 | `pe_vs_industry` | 估值 | 季 | − | **Selection(Value)** | 標準 | 30→10(反向) | **與估值面重複** | ⚠ B-01 | **Remove(註 F-a)** |
| F10 | hard filters ×4 | 排除 | 季 | — | **Risk / Eligibility** | 無標準 | 負債>85 / 流動<50 / 淨利率<−10 / cash_quality<0.5 | 4 個切點 | ⚠ B-01 | **Relocate → Risk/Eligibility 層** |

**理由註**
- **F-a(F9)**:`pe_vs_industry` 佔基本面權重 0.20,而**估值面本身**(`valuation.py`)又以產業內位階為主計分,並在 composite 另佔 0.08。**同一個估值概念被計了兩次**,且兩次的實作不同(F9 用原始 PE 對 30/10 線性映射;估值面用產業內百分位)。這是純結構性重複計分,不需任何績效數字即可判定。
- **F-b(F10)**:hard filter 的作用是**排除**不是**排序**,把它放在計分引擎內使「排除」與「打分」混在同一層。標準做法是先過 eligibility 再排序。

### 3.5 估值面(`valuation.py:81-190`)

| # | 子因子 | 概念 | Horizon | 方向 | 角色 | 標準定義 | 現行實作 | 偏離 | PIT | 裁決候選 |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 | 產業內估值位階 | 相對估值 | 季 | − | **Selection(Value)** | 標準 | **100% 權重**(若可得) | — | ⚠ **`industry_value_ref` 表僅 2019+**(2019 斷裂三處之一) | **Keep → Selection Alpha / Value** |
| V2 | PEG | 成長調整估值 | 季 | − | Selection(Value) | 標準 PEG | 退回路徑,權重 **0.85** | 0.85/0.15 混比為結果擬合(§4) | ⚠ B-01 | **Keep(混比須改為無參數)** |
| V3 | 相對歷史位階(PE/PB/殖利率) | 時序估值 | 跨期 | − | Selection(Value) | 標準 | 退回路徑,權重 **0.15** | 同上 | ⚠ `PE_HISTORY_START=2019-01-01`(2019 斷裂) | **Keep 或 Remove(註 V-a)** |
| V4 | 絕對門檻退回 | 估值 | 季 | − | Selection(Value) | 無標準 | PE35/PB25/PS20/殖利率20 | 4 個切點,第三層退回 | ⚠ B-01 | **Remove(註 V-b)** |
| V5 | 昂貴泡泡封頂 | 估值上限 | 季 | − | Risk | 無標準 | `pe_percentile>=80` 且無 PEG/營收解釋 → **封頂 30** | 自訂交互規則 | ⚠ | **Relocate → Risk 或 Remove** |

**理由註**
- **V-a(V3)**:PE 歷史 expanding 分位起算日固定 2019-01-01(`universe_screen_daily.py:51`),使 2019 前後基期不同 —— 這是 B-17 的 2019 斷裂來源之一,且**無法靠移動窗口起點消除**(B-02 後起點約 2014–2015,仍跨越 2019)。若保留 V3,B 必須處理該斷裂。
- **V-b(V4)**:三層退回鏈(產業位階 → PEG+位階 → 絕對門檻)使**不同股票在同一個排序裡用不同的估值定義計分**。這與 B-15(complete cases)的裁決精神直接衝突:B-15 已裁定「不同因子組成的分數不可比」,同一原則適用於「不同估值定義的分數不可比」。

### 3.6 c2 四腳(B 腿,`universe_screen_daily.py:292-310`)

| # | 腿 | 概念 | Horizon | 方向 | 角色 | 現行實作 | 與 A 腿的關係 | PIT | 裁決候選 |
|---|---|---|---|---|---|---|---|---|---|
| Q1 | `value_ind_pct` | 產業內估值 | 季 | − | Selection(Value) | 池內百分位 | **與 V1 同概念** | ⚠ 2019+ | **與 V1 合併為單一 Value 因子** |
| Q2 | `revenue_yoy` | 營收成長 | 月 | + | Selection(Growth) | 池內百分位,直接讀 `revenue_yoy_pct` | **與 M5/M6 同概念、不同定義** | ✅ 2013+ | **與 M5/M6/F5 合併為單一 Growth 層** |
| Q3 | `high52_prox` | 距 52 週高 | 52W | + | Selection(Momentum) | 池內百分位 | **與 M1 同概念**(52 週高鄰近度是動能的代理) | ✅ | **與 M1 合併** |
| Q4 | `100 − momentum20_pct` | **短期反轉** | 20D | **−(反向)** | **Anti-chase** | 池內百分位取反 | **與 M1 方向相反、horizon 不同** | ✅ | **Relocate → Anti-chase(與 M9 合併)** |
| Q5 | `chip20_turnover` | 法人淨額/量 | 20D | + | Confirmation | **僅入聯集圈人,不進 c2 排序** | 與 C1 同概念 | ✅ | **與 C1 合併** |
| Q6 | `rev_accel` | 營收加速 | 月 | + | Selection(Growth) | **僅入聯集,不進 c2 排序** | **與 M5 同一個因子** | ✅ 2013+ | **與 M5 合併** |

**關鍵結構事實(不需任何績效數字):** Q1≡V1、Q2≈M5/M6/F5、Q3≈M1、Q5≡C1、Q6≡M5。**A 腿與 B 腿共有 5 對同概念因子,以不同定義、在不同母體上、各自計分,然後做硬交集。** 這正是使用者診斷的「重複計分 + 母體不同 + 非線性交集」的機制層證據。

---

## 4. 污染登記簿 —— 現行參數有多少是被結果擬合出來的

**此節僅記錄「該參數由結果決定」這一事實,不引用其數值作為任何裁決理由。**

程式碼**註解本身**即為證據,逐條可查:

| 參數 | 位置 | 程式碼註解的自述 |
|---|---|---|
| `composite_weights` 五維 `.31/.08/.19/.27/.15` | `scoring_manager.py:40-53` | 「依『因子歸因』(2023–2025, Rank IC) 校準」;並自行標注 **「⚠ 這是 in-sample 歸因,須經 --validate(train/test)+ --cycle(2021–22 空頭) 複驗才留」** —— **該複驗未見於任何已存檔產物** |
| `weights` 三維 `.32/.38/.30` | `scoring_manager.py:47` | 同上批次調整 |
| `USE_RS_OVERLAY=True` | `scoring_manager.py:8-17` | 列出 A/B 報酬「+2.78%/−0.44% ✅ 過…→ 預設開」 |
| `USE_KD_FULL/USE_BBP/USE_OBV_TREND=False` | `scoring_manager.py:11-20` | 同一批 A/B,列出各自報酬「❌」→ 關 |
| `USE_ASSET_TURNOVER=True` | `fundamentals.py:22-26` | 「綜合多空全期 +2.63→+2.93% ✅ 通過 → 預設開啟」 |
| `REGIME_MULTIPLIERS['bear']` | `regime.py:27-33` | 依 **2022 單一年度**歸因;且明列 **v1、v2 兩組舊值「已證偽,勿回退」** → **同一年資料上的第三次迭代** |
| 估值 PEG/位階混比 `0.85/0.15` | `valuation.py:167-172` | 「拖累源是歷史位階成分…→ 加重 PEG 至 0.85」「純 PEG 全期最好但 2022 綜合 −1.34% 明顯變差,故不取」 |
| `_RATIO_TO_POINTS = 300.0` | `scoring_manager.py:299` | 「可調,改後需 `--attribution` 複驗」 |
| `_HORIZON_WEIGHTS` | `scoring_manager.py:298` | 自訂 |
| 各子因子階梯切點 | 全表 | 依 §3 逐項清點,**合計約 60 個切點**,均無標準定義來源 |

**結論(結構性,非績效判斷):B-10 的「舊權重污染」範圍遠大於五個權重。** 實際受污染的是:**2 組權重向量 + 5 個布林開關 + 1 組 regime 乘數(單年三次迭代)+ 1 組估值混比 + 2 個籌碼標度常數 + 約 60 個階梯切點。**

**這對 B-10 的直接後果:** 使用者裁決「同級 bucket 等權,或取消五維權重概念」只清掉第一項。**若 §3 的階梯切點原封不動搬進 B,污染就從權重層轉移到切點層,總量幾乎不變。** 因此 B-09 的裁決必須連帶決定:子因子是否改為**無切點的連續形式**(例如橫斷面百分位,與 B-16 一致)。這是 B-09 與 B-16 的耦合點,先前未識別。

---

## 5. 依上述得出的架構候選

### 5.1 四層架構(對應使用者 2026-08-16 的分層構想)

| 層 | 成員(依 §3 裁決候選) | 角色定義 |
|---|---|---|
| **Selection Alpha** | **Value**: V1+Q1(合一)、V2 · **Quality**: F1–F4、F7、F8 · **Growth**: F5、F6、M5+Q6、M6、M7(cap) 、Q2 · **Momentum**: M1+Q3(合一,標準 12-1) | 決定「哪些標的值得持有」 |
| **Confirmation** | C1+Q5(合一) | 不改變 selection 排名,僅作為持有/放棄的確認訊號 |
| **Timing** | T1–T8(去重後)、M8、M10、C7 | 不進 selection 排名 |
| **Risk / Eligibility** | F10 hard filters、V5、**Anti-chase: M9+Q4+M11 合一**、流動性(B-06)、資料品質(B-01/B-15) | 排除,不排序 |
| **Remove** | T7、T9、T10、M2、M3、M4、C2、C3、C5、C6、C8、F9、V3?、V4 | 見各註 |

### 5.2 這個架構解掉的結構問題(逐條對應 §2)

1. 動能 bucket 內的三種 horizon / 兩種 role 被拆開 → M5/M6/M7 歸 Growth、M8/M10 歸 Timing、M9 歸 Anti-chase、M1 留 Momentum。
2. A/B 腿 5 對同概念因子合一 → 重複計分消除。
3. 技術面整體改為 Timing → 不再以 0.19 權重污染 selection。
4. 籌碼面改為 Confirmation → 同上,0.15 權重取消。
5. F9 與估值面的雙重計分消除。
6. hard filter 移出計分引擎 → 排除與排序分離。

### 5.3 B-07 正式處置

**`B-07 SUBSUMED BY B-09`。** 追高抑制不再是獨立項,而是 Risk/Eligibility 層的 **Anti-chase** 成員(M9 + Q4 + M11 合一)。其標準定義取 **1-month reversal**(公認短期反轉 horizon),以橫斷面連續量表達,**不設門檻** —— 因此 B-07 先前殘留的「Top 5/10/20%」自由參數**歸零**,不是被推遲。

---

## 6. 對下游的機械後果(B-04 / B-02)

依 §3 裁決候選,若 Growth 層保留 M5(`revenue_accel`)、M6(`cum_yoy`)、M7(`streak`),則 `monthly_revenue` 的最深回看**不變**,B-02 的 L 維持約 25 個決策月(由 `cum_yoy` 撐起)。

**但若 M6 被移除或改以 Q2(`revenue_yoy_pct`,直接讀取、僅需 1 個月)取代**,則最深有界回看降為 M5 的 `accel`(18 個月)或 M7 的 cap(24),**L 隨之改變、first eligible month 前移**。

**⇒ 確認 §3 的 Growth 層成員,是 B-02 能否機械關閉的前置條件。** 這與先前識別的 dependency chain 一致,本輪未自行決定,列為 Phase 2 待裁決。

**B-04:** `streak` cap=24 的 ex-ante 理由在本輪維持成立(對齊 `cum_yoy` 已需的回看,不新增尺度)。**但若 M6 `cum_yoy` 被移除,cap=24 的錨點隨之消失,理由需要重寫** —— 屆時不得改用「24 效果最好」。此耦合先前未識別。

---

## 7. Phase 2 待裁決(本輪不決定)

1. **Growth 層成員定案**(決定 B-02 的 L 與 B-04 的 cap 錨點)。
2. **切點 vs 連續形式**(§4 結論:若保留約 60 個階梯切點,B-10 的去污染無效)。這是 B-09 × B-16 耦合。
3. **V3 保留與否**(牽動 B-17 的 2019 斷裂)。
4. **Confirmation 層如何影響最終決策** —— 若不進 selection 排名,它到底改變什麼?現行是加權進 composite;新架構下需明文定義,否則 C1 變成無作用的裝飾。
5. **標記 `Remove 候選` 的 14 項逐項確認** —— 本輪給的是理由,不是裁決。

---

**本文件為 Phase 1 唯讀結構分析。未執行回測、未計算績效/IC/選股名單、未產生 A0–A3 產物。未 stage、未 commit。**
