# 勘誤 · 「本體 A / V0 = 無 regime」描述有誤

**建立**:2026-08-09。**裁決來源**:使用者要求驗證「本體 A 是否真的無 regime」後,
以程式碼閱讀 + 實測發現原始查證方式有漏洞(見 §1)。

**本勘誤不改動任何門檻、樣本、seed、報酬線、Gate 1 的 12-arm 判定結果、或
`docs/預註冊_雙確認ADV100萬.md` 的 H1–H5 判定。** 被勘誤的只是「V0 是什麼」
這句**描述**,不是任何統計結論。

---

## 1. 被勘誤的說法與出處

`docs/架構分離_StrategyBodyVsOverlay.md`(2026-07-30 建立)§2「A 確為『無 regime』
——已查證,不是假設」原文:

> - `beat_0050/realbody/build_realbody_scores.py`:**無** `regime` / `current_regime` 參照;
>   `score_row(..., MODE, ...)` 用固定 MODE,**從不設** `current_regime`。
> - `core/scoring_manager.py`:**無** `current_regime` / `regime_multipliers` 參照。
> - ⇒ `realbody_scores_adv100w.parquet` 的 `real_composite` 是在 `current_regime=None`
>   下算的,**不含 regime 調整**。

**查證方式**:grep `build_realbody_scores.py` 與 `core/scoring_manager.py` 兩個檔案
有沒有出現 `current_regime` 字樣,兩邊都沒有 → 判定「無 regime」。

**漏洞**:`build_realbody_scores.py` 呼叫的是 `core/score_store.py` 的 `score_row()`
(見 [build_realbody_scores.py:121-134](../beat_0050/realbody/build_realbody_scores.py)),
而 `score_row()` 內部有這行,**無條件執行**:

```python
# core/score_store.py:206
advisor.current_regime = _regime_at(as_of)        # 與回測同步:空頭自動轉防守權重
```

原查證只檢查呼叫端(`build_realbody_scores.py`)有沒有**自己**設定 `current_regime`,
沒有檢查被呼叫的 `score_row()` **內部**會不會設定 —— 而後者才是實際生效的地方,
且**這行對研究建置與線上即時計分是同一份程式碼**。

---

## 2. 實測結果

### 2.1 `_regime_at()` 對 2019 年後的日期回傳真實分類,不是 `None`

```
2020-03-31 -> bear
2021-06-30 -> bull
2022-10-31 -> bear
2023-06-30 -> bull
2024-01-31 -> bull
```

`_regime_at()` 只有在 `load_benchmark("0050")` 失敗(或該日期早於 2019-01,`classify_regime`
判定資料不足回 `'neutral'`)時才不生效。2019 年起 0050 快取存在,`_regime_at()` 正常運作。

### 2.2 `regime_multipliers()` 對 composite 的實際影響(8 組股票×日期抽測)

方法:對同一個 `(stock_id, as_of)`,分別用「正常(帶 regime)」與「monkeypatch
`_regime_at` 強制回 `None`」跑兩次 `score_row()`,比較 `composite` 差多少。

| 股票 | 日期 | regime | 帶 regime | 無 regime | 差 |
|---|---|---|---|---|---|
| 2330 | 2020-03-31 | bear | 38.21 | 38.58 | −0.37 |
| 2317 | 2020-03-31 | bear | 23.02 | 22.35 | +0.67 |
| 1101 | 2022-10-31 | bear | 25.85 | 22.17 | **+3.68** |
| 2603 | 2022-10-31 | bear | 44.56 | 46.63 | **−2.07** |
| 2454 | 2021-06-30 | bull | 65.61 | 65.30 | +0.31 |
| 2308 | 2023-06-30 | bull | 51.30 | 50.74 | +0.56 |
| 2330 | 2022-10-31 | bear | 51.20 | 53.71 | **−2.51** |
| 1216 | 2020-03-31 | bear | 21.51 | 23.99 | **−2.48** |

**bear 段差 2~4 分(0–100 分制),bull 段差 <1 分**——這個量級足以在 Top-20% 交集的
邊界翻動股票的進出,不是雜訊。bear 乘數(`fundamental 1.00 / valuation 0.60 /
technical 0.30 / momentum 1.50 / whale 0.30`)本身就不是小擾動。

---

## 3. 正確的描述

| 期間 | 狀態 |
|---|---|
| **2005-01 ~ 2018-12** | 真的無 regime 效應。`classify_regime()` 因缺 0050 歷史資料回 `'neutral'`,`REGIME_MULTIPLIERS['neutral']` 全為 1.0,等於沒作用。(`docs/血緣稽核_五維度_2026-07-31.md` 已記載此段,描述正確,不需更正) |
| **2019-01 之後**(含 Gate 1 全部 OOS 窗 2019-08~2026-03、H2 用的 OOS(2010+) 窗的後半段) | **`real_composite` 實際包含 regime 對五面加權比重的自動調整**,不是「無 regime」 |

**H1–H5 驗證的「本體 A」,準確描述是**:2005-2018 段無 regime,2019 年後**含**
regime 對排序權重的自動調整(即架構分離文件定義的「層 B」)。「固定曝險」這句仍然
成立(regime 沒有調整持股比例,只調整五面合成的權重),但「無 regime」不成立。

---

## 4. 不需要重新評估的部分(說明理由)

### 4.1 Gate 1 的 12-arm 判定不需要重跑

`beat_0050/realbody/build_arm_panel.py` 的設計本身**已經知道** `score_row()` 會設定
`current_regime`,且刻意處理:

- **11 個 arm(A1、A3、A4、C1 除外的其餘、C2、C3、B1–B5)刻意讓 `current_regime`
  與 V0 同步**——程式碼註解逐字寫著「regime 消費端維持復位 → 逐月讀生產快取 →
  current_regime **與 V0 相同**」([build_arm_panel.py:202](../beat_0050/realbody/build_arm_panel.py))。
  這些 arm 與 V0 在同一個 `as_of` 上吃同一個 `current_regime` 值,配對 ΔIC 相減時
  regime 這部分大致互相抵銷,比較的是「合成方式」的差異,不是被 regime 混進雜訊。
- **C1 的凍結規格就是 `advisor.current_regime` 一律 `None`**
  (`docs/預註冊_FaceRedesignV2_草案.md` §4-2b),**這正是「V0 拿掉 regime」的直接檢定**,
  已經在 Gate 1 的同一次單發射擊裡跑過:

  > G1-a t = −1.613,G1-c t = −2.113 —— **拿掉 regime,排序力沒有變好,方向為負(不顯著)**。

**因此**:C1 已經正面回答了「V0 移除 regime 會不會更好」這個問題。再測一次 12 個 arm
是拿同一個問題重新擲骰子,違反單發射擊制;沒有新證據支持原判定有誤,不重跑。

### 4.2 H1–H5(dual100)的判定數字不需要重算

H1–H5 驗證的就是「`real_composite` 實際算出來的樣子」,包含上述 regime 效應。
這**是**已驗證的東西,只是它的敘述(「無 regime」)錯了,數字本身沒有錯。

---

## 5. 需要更正的文件(僅描述性文字,不涉及任何門檻/數字)

| 文件 | 位置 | 處置 |
|---|---|---|
| `docs/架構分離_StrategyBodyVsOverlay.md` | §2「A 確為『無 regime』」整段 | 直接修正(此檔非凍結預註冊,是分析文件) |
| `docs/現況總表_2026-08-09.md` | §1.1、§2.1、§2.6、附錄名詞對照 | 直接修正(本檔本來就是持續更新的總表) |
| `docs/預註冊_雙確認ADV100萬.md` | §「策略本體」定義處 | **凍結預註冊,不改內文**,加頂部指向本勘誤的提示 |
| `docs/預註冊_ExposureOverlay.md` | §「策略本體 A」定義處 | 同上,加提示 |
| `docs/血緣稽核_五維度_2026-07-31.md` | :307 | **不需改**——該處明確限定「前三段」(2005-2018),描述本來就正確 |

`app.py`(部署層文字)另案處理,見同日對話後續。
