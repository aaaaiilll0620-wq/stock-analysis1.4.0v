# N-1 解除條件 · 日曆的權威腿要怎麼補 — 裁決選項書

**狀態（寫定於 2026-09-02，狀態行不隨時間變動）**

```
PRE-RULING · OPTIONS ONLY
本文件之外未變更任何 code / master prereg / data。
未取 seal。ROUTE_SEAL_CONTRACT_STATUS 未動，仍為 NOT_YET_RATIFIED。
N1-1 的取得閘門未動。route_closure.py 未動。
```

> 本文件把選項攤開，不作裁決，也不預先宣告傾向。
> 每個選項自證代價。被量測否證的敘述以刪除線保留。

**前置裁決**：N-1 已於 2026-09-02 裁為 **N1-1（日曆權威腿缺失時不可 seal）**，
見 `docs/A1N1_L3RouteSeal_AdjudicationOptions_2026-09-01.md` §9.4。
本文件只處理**解除條件**：那條腿怎麼補。

**基底**：主線 `b253726d`。⟨M⟩ = 本 session 實測；⟨I⟩ = 繼承自他處。

---

## 0 · 先把裁決標的縮到最小

### 0.1 ⟨M⟩ 一條 TEJ 權威腿**已經存在**，而且逐日對得上

「日曆沒有權威腿」是**宣告**層的事實，不是**可得性**的事實。
由已宣告的 TEJ 價格來源導出 session 清單（`年月日` 的相異值），對比現行 LIVE 日曆
`~/market_cache/taiex_daily.parquet`：

| 資料來源 | 區間 | sessions | TEJ 有 / LIVE 無 | LIVE 有 / TEJ 無 | 一致 |
|---|---|---|---|---|---|
| `data/b0/price_panel.parquet` | 2013-01-02 … 2026-04-01 | **3,232** | 0 | 0 | ✅ |
| `股價2023-20260817.zip`（已宣告 consumed） | 2023-01-03 … 2026-08-17 | **873** | 0 | 0 | ✅ |
| 同上，只看 2026-04-02 之後 | 2026-04-02 … 2026-08-17 | **93** | 0 | 0 | ✅ |

**零差異，兩個方向都是。** 唯一的落差是**時效**：LIVE 多出末端 10 個 session
（2026-08-18 … 2026-09-01），因為 TEJ 匯出停在 08-17。

⇒ **「導不導得出」不是裁決標的。要裁的是它以什麼身分進入宣告，以及誰為時效負責。**

### 0.2 ⟨M⟩ 價格族兩條腿都已宣告 AUTHORITATIVE

`build_prices_leaf.py:224-225`（2019+ 封存）與 `:296-297`（2019 前
`~/tej_cache/price_valuation`）皆宣告 `source_family: "TEJ"` / `authority: "AUTHORITATIVE"`。
⇒ 由價格族導出的日曆，其權威性**繼承自已宣告的東西**，不是新主張。

### 0.3 ⟨M⟩ 現行日曆的生產者自陳「不驅動訊號」

`core/market_index.py` 檔頭：

> **定位：只供顯示，不驅動訊號。**
> 資料源：種子 = FinMind `TaiwanStockPrice(TAIEX)` 一次性回補；增量 = TWSE `MI_INDEX`。

而 L3 用它決定 §6.6 的 as_of 與 §6.5 的執行 session ——**「什麼時候」決定其餘一切**。
⇒ 這不只是家族標錯，是**一個自稱不驅動決策的產物正在驅動每一個決策的時點**。
任何選項都要回答這句話還算不算數。

### 0.4 不是自由度的

| 項目 | 為什麼 |
|---|---|
| N1-1 本身 | 已裁決。本文件只處理解除條件 |
| 「導得出 TEJ session 清單嗎」 | ⟨M⟩ 已證明可以，且零差異 |
| 閘門的機制 | `unauthoritative_floor_families()` 讀 `FLAT_FAMILIES` 的 `authority` 宣告。**衍生式**，任何選項只要讓宣告誠實地變成 AUTHORITATIVE，它就自己開 |

---

## 1 · 任何選項都必須滿足的三個約束

1. **⟨M⟩ 日曆 leaf 恰好一個 consumed 來源。**
   `research/b0_l3/l3_snapshot.py:88-91`：
   > the calendar leaf declares %d consumed sources; **exactly one series defines the sessions**.
   ⇒ 任何「兩條腿並列 consumed」的做法**必須先改這道守衛**，那是獨立的變更與獨立的理由。
2. **時效必須覆蓋到執行 session。** 9/30 決策的執行 session 是 10/01
   ⇒ 日曆必須含 2026-10-01。TEJ 匯出停在 08-17 ⇒ **任何 TEJ 腿都需要一次重匯**。
3. **不得引入第二個「什麼時候」的定義。** 兩份不一致的 session 清單同時存在，
   就是本專案史上四次結論作廢的那個形狀（數字看起來正常但口徑換了）。

---

## 2 · 選項

### 選項 C-1 · 日曆改由 TEJ 價格族**導出**
sessions := 已宣告價格來源的 `年月日` 相異值。`taiex_daily.parquet` 退出決策路徑。

- **⟨M⟩ 可行性已證**：零差異，3,232 + 873 個 session。
- **權威性**：繼承 §0.2 的既有宣告，不是新主張。
- **代價一 · 日曆變成價格族的函數。** 價格重匯會移動日曆。
  ⇒ 需明文裁定「價格重匯是否構成新的 lineage 版本」——這與 M-3 選項 C 當年被指出的
  同一個問題同型（覆蓋下限變動是否開新 lineage）。
- **代價二 · 語意窄化。** 由價格導出的是「至少一檔證券有成交紀錄的日子」，
  不是「市場開市的日子」。全市場休市但有場外紀錄、或某日全數無量，兩者理論上會分歧；
  ⟨M⟩ 在 3,232 + 873 個 session 上沒有發生過，但**沒有發生過不等於定義相同**。
- **代價三 · §1.1 的守衛**：日曆 leaf 將沒有自己的 consumed 來源（它不再有自己的位元組）
  ⇒ 要嘛日曆不再是一個 family，要嘛它 consume 價格 leaf 的 payload hash。兩者都要改守衛。
- **對 N1-1 閘門**：`calendar` 若不再是 flat family，閘門的命中集合變空 ⇒ 自動開。
  ⚠ **這使「閘門開了」與「問題解決了」在程式上無法區分**，除非同時加一條
  「日曆的推導來源必須是 AUTHORITATIVE 家族」的正向檢查。

### 選項 C-2 · 保留 `taiex_daily` 供位元組，另加一條 TEJ **對帳**腿
LIVE 仍是 sessions 的來源；每次 build 對已宣告的 TEJ 價格來源做逐日對帳，不一致即 abort。

- **代價一 · §1.1 必須改**：兩個 consumed 來源，或把 TEJ 腿放進 `derived_dependencies`。
- **代價二 · 「權威」的語意被重新定義**為「被 TEJ 對帳過」而非「來自 TEJ」。
  R-W1-2 的原文是 **TEJ 為權威**；這算不算滿足，**需要明文裁定，不能默認**。
- **代價三 · 對帳只能覆蓋 TEJ 有的區間。** ⟨M⟩ 末端 10 個 session
  （2026-08-18 … 09-01）**沒有任何 TEJ 腿可對**，而那正是最新、最接近決策的一段。
  ⇒ 對帳通過不代表決策用的那幾天被對過。**這是本選項最尖銳的代價。**
- **對 N1-1 閘門**：`calendar` 仍是 flat family，宣告要改成什麼需一併裁定；
  若仍標 `LIVE / SUPPLEMENTARY`，閘門不會開，N1-1 仍擋著。

### 選項 C-3 · 判日曆為 derived artefact，不適用來源家族分類
基礎：`build_flat_leaves.py` 自己的註解已指出日曆是 `build_market_state.py` 從
`taiex_daily.parquet` **產出** `data/b0/trading_calendar.csv`，
「Sharing a producer file is not sharing a source, and the first declaration here conflated the two」。

- **代價一 · 問題被移動一層，不必然被消除**：那就必須說明「產它的那個 parquet」歸誰對帳。
  §0.3 的自陳（只供顯示）在這一層會變得更難迴避。
- **代價二 · 閘門失去標的** ⇒ 與 C-1 的「代價三」同型：開了不等於解決了。
- **好處**：不必動 §1.1 的守衛，也不必重匯。**是唯一不需要新資料的選項。**

### 選項 C-4 · 向 TEJ 取一份真正的日曆／交易日匯出
- **⟨I⟩ 可得性未知。** 本文件**未查證** TEJ 是否提供此產品，也未估工期。
  裁決若傾向此項，第一步是查證而非實作。
- **代價**：新增一個 dataset family ⇒ 動 `REQUIRED_DATASET_FLOOR` ⇒ 連動 `route_closure`
  與 C-71 的 `FLOOR_CAPTURE_REQUIRED_DATASETS`（FIXED inventory）。
  這是四個選項裡**唯一必然跨 A2 邊界**的。
- **好處**：唯一讓「日曆」有自己的、非導出的權威來源的選項；語意最乾淨
  （market calendar 就是 market calendar，不是「有人成交的日子」）。

---

## 3 · 時效：四個選項共通、且與 9/30 直接衝突

⟨M⟩ TEJ 價格匯出止於 **2026-08-17**；LIVE 日曆已到 **2026-09-01**；
9/30 決策需要的執行 session 是 **2026-10-01**。

⇒ C-1、C-2、C-4 都需要**一次 TEJ 重匯**才可能覆蓋到 10/01。
⟨I⟩ 該重匯**本來就排在 9/29-30**（含歷史下市／併購／終止交易證券），
所以時效不是新工作——但它使**日曆的解除條件與價格重匯綁在同一天**，
而那一天也是決策日。**任一環節延誤，Month 1 就順延。**

C-3 不需要重匯，因此是唯一**不受 9/29-30 那次匯出成敗影響**的選項。

---

## 4 · 每個選項如何讓 N1-1 閘門開（這是機制，不是形式）

閘門是 `l3_route_seal.unauthoritative_floor_families()`，讀
`build_flat_leaves.FLAT_FAMILIES[ds]["authority"]`，非 `AUTHORITATIVE` 即擋。

| 選項 | 閘門怎麼開 | ⚠ |
|---|---|---|
| C-1 | calendar 不再是 flat family ⇒ 命中集合變空 | **開了 ≠ 解決了**，需另加正向檢查 |
| C-2 | 需一併裁定 calendar 的宣告改成什麼；不改就不會開 | 對帳不覆蓋末端 10 天 |
| C-3 | 同 C-1 | 同 C-1 |
| C-4 | calendar 宣告為 `TEJ / AUTHORITATIVE`，且是真的 | 唯一「開」與「解決」同義的選項 |

⚠ **三個選項裡有兩個會讓閘門因為標的消失而開啟。** 那不是本裁決的意圖，
裁決若採 C-1 或 C-3，**應同時要求一條正向檢查**（日曆的推導來源必須出自 AUTHORITATIVE 家族），
否則 N1-1 會以「無人可擋」的方式被解除。

---

## 5 · 本文件沒有做的事

- 沒有裁決。四個選項全部保留。
- 沒有查證 C-4 的 TEJ 產品可得性（明列為該選項的第一步）。
- 沒有改任何程式碼、宣告、閘門或 owed 清單。
- 沒有估算任何選項的工期。
- 沒有處理「若 9/29-30 重匯失敗，Month 1 如何順延」——那是 U-2 的範圍，另案。
