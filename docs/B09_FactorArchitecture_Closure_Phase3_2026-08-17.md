# B-09 Factor Architecture Closure — Phase 3

**狀態:`PHASE 3 COMPLETE` — feature graph 已凍結,L 已機械推導。三項待裁決。**
**日期:** 2026-08-17
**授權依據:** 使用者 2026-08-17「授權 Phase 3 僅進行資料可行性、隔離 candidate reference 建立、feature graph freeze 與 B-02 dependency/L 機械推導;不得執行任何績效、IC、選股或 A0–A3」。

## 0. 合規聲明

**四項授權工作全部完成,無一項越界。未執行任何績效、IC、Sharpe、CAGR/MDD、選股名單或 A0–A3。**

**寫入路徑僅限** `research/p0_b09_value_reference/`(3 個檔案)+ 本文件。
**未寫入** `~/tej_cache`、`~/market_cache`、`cloud_cache/`、`data/runtime_cache/` 或任何生產路徑。未 stage、未 commit。

---

## 1. 資料可行性(F-D 前提)—— **確認可行**

| 檢查 | 結果 |
|---|---|
| `~/tej_cache/price_valuation` 涵蓋 | **2004-01-02 → 2026-07-14**,9,009,907 列,**2,300 檔** |
| 欄位 | `PER_TSE`、`PER_TEJ`、`PBR_TSE`、`PBR_TEJ`、`dividend_yield_TSE`、OHLC、`Trading_Volume` |
| 產業分類 PIT 歷程 | `歷史產業類別.xlsx` 含 31 欄,其中 19 欄為變更歷程 |

**⇒ F-D 成立:2019 錨點確實只是相容性選擇,底層資料支持全歷史重建。**

---

## 2. PIT 產業時間軸(本輪新建,先前不存在)

### 2.1 為什麼必須新建

`~/tej_cache/industry_map.parquet` 是 **2,436 列、無 date 欄的靜態當期快照**。而實測:**1,203 檔(49.4%)至少換過一次 TSE 產業別**,2,760 個變更事件發生在 2004 之後。用靜態表回算歷史產業內估值,等於對**約一半的母體**引入產業 look-ahead。

### 2.2 變更欄語義(逐例驗證,非假設)

以 1316 上曜為例:`首次掛牌 M1300 塑膠(1992/10/15)` → `前三次 M1300(1992/10/15)` → `前二次 M1721 化學(2014/07/01)` → `前一次 M2500 建材(2019/07/01)` → 當期欄 `建材營造`。

**⇒ 每筆「前 N 次變更」記的是「變成哪個產業 + 生效日」,`前一次` 最近,且與當期欄一致。** 另以 1319 東陽、1229 聯華 交叉驗證,語義相同。

### 2.3 建置結果

| 項目 | 值 |
|---|---|
| 股票數 | 2,436 |
| 時間軸記錄數 | 4,782 |
| 有變更歷程者 | 1,203 |
| **當期欄與最新變更記錄一致** | **2,157** |
| **⚠ 不一致** | **92** |

**⚠ 待裁決項 A:那 92 檔。** 可能成因:(a) 變更次數超過 3 次而欄位只有 3 個槽位,當期反映的是未被記錄的第 4 次變更;(b) 原始資料不一致。**本輪未替它們補當期值** —— 補了等於用一個**沒有生效日**的產業覆蓋歷史,是 look-ahead。目前這 92 檔使用最新有日期的記錄。需裁決:排除、標記、或接受。

輸出:`research/p0_b09_value_reference/pit_industry_timeline.parquet`

---

## 3. 隔離 candidate B value reference

### 3.1 定義(依 F-E(a) 裁決,零自由參數)

```
value_ind_pct_b = (1 − 當期 TSE 產業內 PER_TSE 百分位) × 100      # 越高越便宜
  · 無 expanding self-history 窗        (移除 V3 式 path dependence)
  · 無 MIN_PCT_SAMPLES = 60 樣本門檻
  · 無 2019 anchor                      (F-D)
  · 產業指派為 point-in-time step function
  · 分組最小 2 檔                        (rank 有定義的數學下限,非調校值)
自由參數:0
```

### 3.2 兩處被迫且已揭露的偏離

**D1 · 產業層級用 TSE 產業,不是舊 ref 的 TEJ 產業。**
原因:`歷史產業類別.xlsx` 的變更歷程**只涵蓋 TSE產業 與 TEJ子產業**,**沒有** `前N次TEJ產業變更` 欄。TEJ 產業層的 PIT 時間軸**在資料上不可重建**。TSE 產業另有一項優勢:它是交易所官方分類(外部標準),非廠商專有。

**D2 · 產業指派為 PIT,不是當期快照。** 理由見 §2.1。

### 3.3 建置結果(255 個凍結決策日全跑)

| 項目 | 值 |
|---|---|
| 輸出列數 | **295,001** |
| 決策日 | 255(2005-01-31 → 2026-03-31) |
| 每日計分檔數 | min 766 / median 1,198 / max 1,474 |
| 每日產業組數 | median **33** |
| 輸出 NaN | **0**;值域 0.0–99.8 |

輸出:`research/p0_b09_value_reference/b_value_reference_candidate.parquet`

### 3.4 涵蓋率診斷(非績效)

| 損失來源 | 中位數 | 佔比 |
|---|---|---|
| 報價檔數 | 1,705 | — |
| **PIT 產業查無** | **2** | **0.1%** |
| **`PER_TSE <= 0`(虧損)** | **486** | **28.5%** |
| 實際計分 | 1,198 | 70.4% |

**PIT 產業時間軸幾乎零損失(99.9% 涵蓋)—— §2 的方法有效。**

### 3.5 ✅ **2019 斷裂已消失**(本輪主要目標達成)

| 年代 | 涵蓋率中位數 |
|---|---|
| 200x | 0.691 |
| 201x | 0.700 |
| 202x | 0.734 |

**平坦,無 2019 不連續。** 對照舊 `industry_value_ref` 在 2019-04-10 之前**完全無值**。

**B-17 的三處 2019 斷裂,至此全部有解:**(1) `value_ind` 表 → 本輪解除;(2) RS 需 0050 快取 → M4 已 Remove;(3) regime 乘數 → B-17 裁決移除。

### 3.6 ⚠ 待裁決項 B:估值度量該用 PE 還是 B/M

裁決文寫「純當期產業內橫斷面估值 percentile」,**未指定度量**。本輪用 `PER_TSE` —— 這是**最貼近被退休的舊定義**的選擇(舊 ref 也用 PER_TSE)。但這個選擇與 B 的「standard definition first」原則有張力:

| 度量 | 中位涵蓋率 | 最低 | 外部標準地位 |
|---|---|---|---|
| `PER_TSE > 0` | **0.705** | 0.547 | 業界常用,但非學界 canonical |
| `PBR_TSE > 0` | **0.918** | 0.348 | **book-to-market 是 Fama-French HML 的 canonical value 定義** |

**兩個獨立論點都指向 B/M:**(1) **standard definition first** —— 學界 canonical value factor 是 book-to-market,不是 earnings yield;(2) **涵蓋率** —— PE 的 28.5% 缺口來自虧損公司(負 PE 在定義上不是「便宜」),B/M 對虧損公司仍有定義,中位涵蓋率高 21pp。

**但 B/M 的單日最低涵蓋率 0.348 比 PE 的 0.547 差**,成因本輪未查(疑為早期 PBR 稀疏)。**不自行決定,列為待裁決。**

**這一項為何重要:** 在 B-15 complete-cases 之下,Value 缺值會直接把該股整個剔除。以 PE 計,**中位 28.5% 的母體因此消失,且缺口在 2009–2010 升到約 45%** —— 即**空頭時期母體縮得更多**,這是條件性母體變動,不是隨機缺值。

---

## 4. Feature Graph 凍結

依使用者 Phase 2 全部裁決 + F-A/F-B/F-E 的最終選擇:

| Concept | 成員 | 定義 |
|---|---|---|
| **Quality** | `roe`、`net_margin`、`gross_margin`、`debt_to_asset`、`current_ratio` | 連續橫斷面百分位,concept 內等權(`asset_turnover` **已 Remove**) |
| **Growth** | `revenue_yoy`、`revenue_accel`、`eps_growth` | 同上(`rev_cagr`/`cum_yoy`/`streak` **已 Remove**;`eps_cagr` 更名 `eps_growth`) |
| **Value** | `value_ind_pct_b`、`PEG` | 同上(V3/V4 **已 Remove**;混比 0.85/0.15 **已取消**) |
| **Momentum** | 12-1 price momentum | 同上 |

`SelectionScore = mean(Quality, Growth, Value, Momentum)` —— concept 間等權。
**人工切點:0。Selection 層自由參數:0。**

**非 Selection 層:** Confirmation(C1+Q5 合一,連續 state,不進 B0 排名/不 veto/不 sizing)· Timing(T1–T8 去重、M8、M10、C7)· Risk/Eligibility(F10 hard filters、V5、Anti-chase = M9+Q4+M11 連續 state 不 hard exclude、流動性 B-06、資料品質 B-01/B-15)。

---

## 5. B-02:L 與 first eligible month(機械推導)

| 保留因子 | 最深回看(決策月) |
|---|---|
| **`revenue_accel`(A 腿定義:近3月均 YoY − 前3月均 YoY)** | **18** ← 綁定 |
| `eps_growth`(季 YoY) | 16 |
| Value: PEG | 16 |
| Momentum 12-1 | 13 |
| `revenue_yoy` | 13 |
| Quality TTM | 13 |
| Quality 當期(負債比/流動比) | 4 |
| **Value: `value_ind_pct_b`** | **0** ← F-E(a) 的收穫 |

**L = 18**,綁定因子 = `revenue_accel`(A 腿定義,依 F-B 裁決採用)。

資料邊界:`monthly_revenue` 真實公告日 **2013-01**(P0-R5 Phase A 實測);`financial_statements` 2005-12 起 100% 真實;`price_valuation` 2004-01。**綁定邊界為 monthly_revenue 的 2013-01。**

**First eligible decision month = 2013-01 + 18 = `2014-07`**
**窗口 = 141 個月(`2014-07-31` → `2026-03-31`)**

### 對照

| 情境 | 窗口 |
|---|---|
| 若 2019 錨點未解除(Phase 2 情境 S1) | **84 個月**(2019-04 起) |
| Phase 2 早期估計(L≈25,含 `cum_yoy`) | ~134 個月(2015-02 起) |
| **本輪凍結結果** | **141 個月(2014-07 起)** |

**⇒ 本輪裁決(移除 `cum_yoy`/`streak`、解除 2019 錨點、Value 改純橫斷面)合計回收 57 個月。**

**⚠ 待裁決項 C:** 若 §3.6 裁定 Value 改用 B/M,PEG 仍需 16 個月,**L 不變(18)、窗口不變(141)**。若未來 `revenue_accel` 改用 B 腿定義,L 降為 16 → 窗口 143 個月。**本輪不動 F-B 裁決。**

---

## 6. 三項待裁決

- **A** — PIT 產業時間軸 92 檔當期/歷程不一致:排除、標記、或接受現行處置(用最新有日期的記錄)
- **B** — Value 度量:維持 `PER_TSE`,或依 standard-definition-first 改 book-to-market
- **C** — 確認 L=18 / 窗口 141 個月(2014-07 → 2026-03)作為 B 的凍結窗口

裁決後即可寫 B 預註冊(其餘 closure 項目 B-06/B-12/B-14/B-17/B-18 仍待各自關閉)。

---

## 7. 本輪產出

| 檔案 | 內容 |
|---|---|
| `research/p0_b09_value_reference/build_b_value_reference.py` | 建置器(唯讀輸入,隔離輸出) |
| `research/p0_b09_value_reference/pit_industry_timeline.parquet` | PIT TSE 產業時間軸,4,782 筆 |
| `research/p0_b09_value_reference/b_value_reference_candidate.parquet` | 候選 value reference,295,001 列 |
| `research/p0_b09_value_reference/build_report.json` | 建置報告 + 逐日診斷 |
| 本文件 | Phase 3 報告 |

**未執行績效/IC/選股/A0–A3。未 stage、未 commit。**
