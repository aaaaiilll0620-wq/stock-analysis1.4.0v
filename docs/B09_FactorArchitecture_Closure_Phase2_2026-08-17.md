# B-09 Factor Architecture Closure — Phase 2

**狀態:`PHASE 2 — 五項發現待裁決`。不是預註冊,不是 B 規格,不構成任何授權。**
**日期:** 2026-08-17
**授權依據:** 使用者 2026-08-17 Phase 2 八項裁決。

## 0. 合規聲明

判定依據限於 code / file:line、economic semantics、horizon、standard definition、PIT dependency。**未執行任何回測,未計算報酬 / IC / Sharpe / CAGR / MDD / 選股名單,未動 A0–A3。** 唯讀。

**本輪結果:使用者的八項裁決有五項在程式碼層面遇到與其前提不符的事實。** 三項影響裁決成立與否,兩項是新發現的重複/缺陷。**本輪不自行修改任何裁決** —— 逐項列出事實與可選處置,等裁決。

---

## 1. 五項發現

### F-A · `rev_cagr` 與 `eps_cagr` **都不是**多年 CAGR,名稱誤導

裁決文寫「Longer-term business growth:`rev_cagr`、`eps_cagr`」,並以「已經有多年 rev_cagr / eps_cagr」作為移除 `cum_yoy` 的理由之一。**程式碼不支持這個前提。**

| 欄位 | 實際計算 | 位置 |
|---|---|---|
| `rev_cagr` | **近 3 個月平均「單月營收 YoY」**;`_calc_rev_yoy_smoothed(rev_df, months=3)`。**若算不出則退回 `rev_growth`(單月 YoY)** | `core/data_provider.py:1022`(docstring)、`:1671`、`:1888` |
| `eps_cagr` | **`fundamental_data.get("eps_growth")`,即單期 EPS 年增率** | `core/data_provider.py:1890` |

佐證:`core/models.py:45` 對 `rev_cagr` 的註解是「月營收年增率」;`core/advisor.py:296` 是「近3月均月營收 YoY」。

**後果:**
1. **不存在任何「多年期營收/獲利成長」因子。** Growth 概念裡沒有長期腿。
2. **`rev_cagr` 與 `revenue_yoy` 是同一個概念的兩種平滑**(3 月平均 vs 單月),而且 `rev_cagr` 在資料不足時**直接退回等於 `revenue_yoy`**。這正是本次要消除的重複計分,裁決未捕捉到。
3. 移除 `cum_yoy` 的**結論**可能仍成立(它確實是 level 的第三種表達),但**所引用的理由(「已有多年 CAGR」)不成立,必須改寫**。

**可選處置(不自行決定):**
- (a) Growth = `revenue_yoy`(level)+ `revenue_accel`(acceleration)+ `eps_growth`(獲利 level)—— 移除 `rev_cagr` 作為 `revenue_yoy` 的重複
- (b) 保留 `rev_cagr` 取代 `revenue_yoy`(以平滑版為 level 的代表,單月版移除)
- (c) 真正建立多年期腿(需新定義,非現有欄位)

### F-B · `rev_accel` 有**兩個不同公式共用一個名字**,合併需要選一個

Phase 1 把 M5 與 Q6 標為「同一個因子」。逐行讀後,**它們的公式不同**:

| 管線 | 公式 | 需要 YoY 個數 | 位置 |
|---|---|---|---|
| B 腿 | `最新月 YoY − 近 3 月平均 YoY`(`s.tail(3)`,`s.iloc[-1] - s.mean()`) | **3** | `scripts/universe_screen_daily.py:286-290` |
| A 腿 | `近 3 月平均 YoY − 前 3 月平均 YoY`(`yoys[-3:]` 均值 − `yoys[-6:-3]` 均值) | **6** | `core/data_provider.py:1003-1006` |

兩者都叫「營收動能加速度」,但 A 腿是**兩個三月窗的差**,B 腿是**單月對三月窗的差**。**Phase 1 的「Q6 ≡ M5」描述不精確,本輪更正為「同名、同概念、不同定義」。**

**後果:** 合併必須選一個定義,而這個選擇**直接改變最深回看**(3 個 YoY → 15 個月 vs 6 個 YoY → 18 個月),因而改變 B-02 的 L。

**可選處置:** 依「standard definition first」原則,兩者皆無公認標準。若以「最少參數 + 最短依賴」為結構理由,B 腿定義較簡(單一窗比較),但這是結構論證不是績效論證,仍需裁決。

### F-C · **V1 才是 2019 斷裂,不是 V3** —— 移除 V3 沒有清掉斷裂

裁決以「V3 帶著 2019 structural break」為移除理由之一,並保留 V1。**實測:**

```
~/market_cache/industry_value_ref.parquet
  rows 2,397,392 · distinct dates 1,790
  min 2019-04-10 · max 2026-08-14
```

**V1(`value_ind_pct`,產業內估值位階)在 2019-04-10 之前完全不存在。** 佐證:`scripts/face_lineage_audit.py:218` 早已記載「`industry_value_ref.parquet` 起 **2019-04-10**」。

**後果:** 移除 V3 後,Value 概念 = V1 + V2。V1 佔 Value 的一半,而它在 2019-04 之前**沒有值**。依 B-15(complete cases)裁決,這會導致二選一:
- **窗口被壓到 2019-04 起**(約 84 個月),或
- **Value 概念在窗口中途換定義**(2019 前 = PEG only,2019 後 = PEG + 產業位階)—— 這正是 B-15 明文禁止的。

**⇒ 這一項若不處理,B-02 的 L 討論完全沒有意義,因為綁定約束不是月營收,是 V1。**

### F-D · 但 2019 那道牆是**刻意的相容性錨點,不是資料極限** —— 而該相容性的理由已被 Frozen A 廢除

`scripts/build_industry_value_ref.py:41-44` 原文:

> ```
> # v4.5 生產估值是用「2019 起的 expanding 窗」過閘門的;TEJ 補匯 2004-2018 歷史後,
> # 若不錨定起點,分位分佈會整批改變 → 預設鎖 2019,研究用途才改。
> PE_HISTORY_START = "2019-01-01"
> ```

**程式碼自己說明:TEJ 已補匯 2004-2018 歷史,2019 錨點是為了「不改變分位分佈、不打破 v4.5 已過閘門的生產估值」而刻意鎖的。**

**這正是「維持舊結果相容性」的理由 —— 而 Frozen A 架構已明文放棄該目標。** 在 B 之下,這個錨點失去它**唯一**的存在理由。

**後果(正向):** 若解除錨點,`industry_value_ref` 可依同一構造重建至 2004(輸入為 `tej_cache/price_valuation` 全歷史 + TEJ 產業分類,兩者皆有 2004+ 語料;`DataExport` 另有 `產業類別/歷史產業類別.xlsx`)。**V1 的 2019 斷裂在來源層消失,B-17 的三處斷裂去掉一處,窗口不再被 2019 綁死。**

**這是本輪最有價值的發現:F-C 看起來是致命阻塞,F-D 顯示它是可解除的自我加諸限制。**

**可選處置:** 解除錨點屬 **data fix**(重建參考表,不改因子定義),但它是 code + cache 變更,需另行授權,且必須先確認 `tej_cache/price_valuation` 的實際歷史涵蓋(本輪未驗,列 Phase 3)。

### F-E · V1 **內含**時序自比,所以「保 V1 移 V3 以去 path dependence」的理由不成立

裁決移除 V3 的理由之一是「V3 是時間序列的自己跟自己比…引入很強的 path dependence」,而保留 V1 因為它是「cross-sectional relative valuation」。**V1 的構造不是純橫斷面。**

`scripts/build_industry_value_ref.py:9-15` 原文構造:

> `pe_hist_pct`:個股**自身歷史 PE expanding 分位**(含當日、只取 >0、樣本 >= 60)
> `value = 100 − pe_hist_pct`
> `value_ind_pct`:`value` 在當日「TEJ 產業」內的百分位

**⇒ V1 = 「個股自身歷史 PE expanding 分位」再做產業內橫斷面排名。時序自比被包在裡面,path dependence 一併繼承**(expanding 窗使同一檔股票的分數取決於它已累積多少歷史)。

**後果:** 移除 V3 的**結論**可能仍成立(V3 與 V1 確實高度重疊),但**理由必須改寫**。若 path dependence 本身是要消除的目標,則需要一個**純橫斷面**的 value 定義(例如產業內原始 PE/PB 百分位,不經 expanding 窗)—— 該定義可由同一份資料直接算出,且**無 `MIN_PCT_SAMPLES=60` 的樣本門檻、無 expanding 路徑依賴、無 2019 錨點問題**。

**可選處置:**
- (a) Value = 純橫斷面產業內估值百分位 + PEG(消除 path dependence 與 60 樣本門檻)
- (b) 維持 V1 現構造 + 解除 2019 錨點(保留 path dependence,揭露之)
- (c) 其他

---

## 2. 依裁決更新後的 Selection Alpha 清單(含本輪待決缺口)

| Concept | 成員(裁決) | 本輪發現的缺口 |
|---|---|---|
| **Quality** | ROE、net_margin、gross_margin、asset_turnover、debt_to_asset、current_ratio | `USE_ASSET_TURNOVER` 原為 A/B 擬合開關,B 需改以結構理由決定其去留 |
| **Growth** | `revenue_yoy`、`revenue_accel`、`rev_cagr`、`eps_cagr` | **F-A**:`rev_cagr` ≈ `revenue_yoy` 重複;無長期腿。**F-B**:`revenue_accel` 兩個定義需擇一 |
| **Value** | V1、V2(取消 0.85/0.15 混比) | **F-C/F-D**:V1 僅 2019-04+,錨點可解除但需授權。**F-E**:V1 含時序自比 |
| **Momentum** | 12-1 price momentum | 需 13 個月價格歷史(非 PIT 瓶頸,已確認) |

**已依裁決確定移除(15 項):** T7、T9、T10、M2、M3、M4、M6、M7、M12、C2、C3、C5、C6、C8、F9、V3、V4。
**Relocate:** T1–T8(去重後)→ Timing;M8、M10 → Timing;C7 → Timing diagnostic;M9+Q4+M11 → Anti-chase **連續 state,B0 不 hard exclude**;F10 hard filters、V5 → Risk/Eligibility。
**Confirmation:** C1+Q5 合一,連續 state,**不進 B0 selection ranking、不 veto、不 sizing**。
**B-04:** **RETIRED**(`streak` 移除,無界特徵消失)。理由記為 `feature removed`,非 `cap adopted`。
**B-07:** `SUBSUMED BY B-09`,自由參數歸零(連續 state,無門檻)。

---

## 3. 依賴圖與 L(機械推導,分情境;**不含**確切 first eligible month)

依裁決要求「所有保留因子一起計算 max lookback,不能只盯 monthly revenue」。單位為**決策月**,含公告落後。

| 保留因子 | 資料源 | 最深回看(決策月) | 備註 |
|---|---|---|---|
| Momentum 12-1 | 日價 | **~13** | 12 個月 + skip 1;價格 2004+ 無 PIT 瓶頸 |
| `revenue_yoy` | monthly_revenue | **~14** | 需 m−1 與 m−13 兩個營收月 |
| `rev_cagr`(3M 均 YoY) | monthly_revenue | **~16** | 需 3 個 YoY |
| `revenue_accel` **B 腿定義** | monthly_revenue | **~16** | 需 3 個 YoY |
| `revenue_accel` **A 腿定義** | monthly_revenue | **~19** | 需 6 個 YoY |
| `eps_cagr` / Quality(TTM 類) | financial_statements | **~15–18** | 4 季 + 公告落後;確切值待 B-01 改讀真實 `release_date` 後機械算 |
| Value V1(現構造) | industry_value_ref | **不適用** | expanding 窗 + `MIN_PCT_SAMPLES=60`,**且 2019-04 前無值** |
| Value V1(純橫斷面版,F-E(a)) | price_valuation + 產業分類 | **~1** | 無 expanding、無樣本門檻 |
| Value V2 PEG | financials + 成長 | ~15–18 | 同 Quality |

**兩個情境:**

| 情境 | 綁定約束 | L |
|---|---|---|
| **S1 · V1 維持現構造且維持 2019 錨點** | **V1 的 2019-04 硬牆** | 窗口起點被壓到 **2019-04**,L 無意義 |
| **S2 · 2019 錨點解除(F-D)** | `revenue_accel` A 腿定義(~19)或 `eps_cagr`/Quality(~15–18) | **L ≈ 18–19**(若採 B 腿 accel 定義則 L ≈ 16–18) |

**⇒ 移除 `cum_yoy` + `streak` 確實把 L 從約 25 降到約 16–19,但真正決定窗口的是 2019 錨點是否解除,不是月營收。** 這在裁決當下無法預見,因為 V1 的 2019 限制先前只被記為「B-17 的斷裂之一」,未被辨識為**窗口的硬約束**。

**依指示,本輪不手算確切 first eligible month。** 待 Phase 3 凍結 feature list(含 F-A/F-B/F-C/F-E 的裁決)後,再以程式從凍結的依賴圖機械推導。

---

## 4. 本輪關閉 / 仍開放

**已關閉(裁決 + 本輪驗證,無殘留自由參數):**
- Selection Alpha 全面連續橫斷面百分位、concept 內等權、concept 間等權 → **約 60 個人工切點歸零**
- 非單調 Timing/Risk 變數不轉 alpha percentile → 角色分離
- B-04 retired;B-07 subsumed 且門檻歸零
- Confirmation 不進 B0 → 不引入 threshold/sizing 參數
- 15 項 Remove 確定

**仍開放(本輪新增,均因程式碼事實與裁決前提不符):**
1. **F-A**:`rev_cagr` 與 `revenue_yoy` 的重複如何處置;是否真的需要長期腿
2. **F-B**:`revenue_accel` 採 A 腿或 B 腿定義
3. **F-C/F-D**:是否授權解除 2019 錨點並重建 `industry_value_ref` 至 2004
4. **F-E**:Value 是否改採純橫斷面定義以消除 path dependence
5. `USE_ASSET_TURNOVER` 的去留需改以結構理由決定

---

## 5. Phase 3 待辦(需授權)

- 唯讀確認 `tej_cache/price_valuation` 的實際歷史涵蓋(F-D 可行性前提)
- 上列五項裁決後,凍結 feature list
- 以凍結的依賴圖**機械**推導 B-02 的 L 與 first eligible month

---

**本文件為 Phase 2 唯讀結構分析。未執行回測、未計算績效/IC/選股名單、未產生 A0–A3 產物。未 stage、未 commit。**
