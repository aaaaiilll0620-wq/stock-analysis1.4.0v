# 草案 · 預註冊規格 — 不可重建的持股人重組離場：規則 HX-A（邊界前價強制現金離場）

> ⛔ **本文件為草案，尚未凍結。** 使用者已於 2026-09-03 選定「方案 A」的**方向**，
> 但未裁示凍結，且 §2.0 指出它在 §6.1.12 改寫之前無處落地。
> 在取得凍結裁示之前，**本文件不具規範效力，不得被引用為已註冊的假設**。
> 凍結時應改名為 `docs/預註冊_*.md` 並填入實際註冊日。

**擬註冊日：2026-09-03（凍結時尚未跑任何使用本規則的 run）**

**性質：資料處置慣例，非 alpha 研究。** 本文件不提出任何策略假設，
只回答「當持股人重組離場的對價條款無法重建、而投組當時持有該證券時，程式該做什麼」。
採**單發射擊制**：下列規則一次凍結；跑完之後想改任何一條 =
開新一輪預註冊，**不得回頭改本文件**。

> ⚠ **本文件不授權任何 run。** 它不重開 FROZEN_B0（觀測額度已由
> `L2-af1b4d90c29b3b5f` 消耗，§9.6e-R5 使其不可達），也不指定本規則
> 要用在哪一條 lineage 上。那是另一次裁決。
>
> ⚠ **本規則改變策略語義（`strategy semantics changed = TRUE`）。**
> 這與 C-60 ~ C-66 六次 conformance repair 的性質不同：那些修的是實作，
> 本規則改的是投組在該事件上的**行為**。因此它**不能**作為 Frozen B0 的修補，
> 只能屬於一條新登錄的 lineage（B1…），這是 §1.4 no-post-hoc-rescue 的直接後果。

**凍結時的資料指紋**

```
data/b0/corporate_actions_ledger.csv
  sha256 = c838961f93599f9e63c9c98a556f3e721cc5994b53e89d109e17f625a9f7d6f2   bytes = 6,568,122
data/b0/security_status.csv
  sha256 = 2d216176877fb83506b7c99002f5e9e2c90cb54c0a400190ff8c31a5e9bb4bdd   bytes = 110,038
data/b0/price_panel.parquet
  sha256 = a0681dd7e50f5c5450c5f82fab0b1f007d84df4e8e7af822116103c94e2a3b77   bytes = 66,954,211
data/b0/trading_calendar.csv
  sha256 = 5859cf08835c7e7001d31cfacd4a49c7d1765493954591ffdea61470b7129dda   bytes = 66,789
```

---

## 1. 問題

`corporate_actions_ledger.csv` 有 **158** 筆 `holder_side_reorganization_exit`，
**全部 158 筆皆為 `NOT_RECONSTRUCTIBLE`**（B0.4 / C-63 起即如此，依設計）。
落在 141 期窗口（2014-07-31 … 2026-03-31）內的有 **90** 筆。

依 §6.1.12，`NOT_RECONSTRUCTIBLE` **且投組當時有 affected economic exposure**
→ **fail closed**。B0.7 就是這樣停在第 67 期的，其曝險約為 **新台幣 14 元**。

不可重建的原因已於 2026-09-02/03 逐項查證，**不是查得不夠**：

| 阻斷點 | 實測 |
|---|---|
| 消滅公司自身之公告本文 | MOPS 對已停止公開發行者一律拒絕（`該 XXXX 公開發行公司不繼續公開發行！`）。pass 1 抓 541 篇 detail，**本文取得 0 篇** |
| 對手方／存續公司之公告 | 可取得。本輪讀入 **1,175 篇**，內容止於條款與基準日 |
| 撥券日／價款發放日 | **該欄位不存在於任何公開揭露**。窗內 42 筆窄查詢，交付日取得 **0 筆** |

⇒ 對價條款與交付日**不可能**由公開來源補齊。這不是待辦事項，是已證實的邊界。

---

## 2. 規則 HX-A · 不可重建的離場 ⇒ 邊界前最後成交價強制現金離場

### 2.0 ⚠ 本規則與 §6.1.12 禁止清單正面相撞，且不得以解釋規避

§6.1.12 現行條文對 `NOT_RECONSTRUCTIBLE + 有曝險` 明列七項禁止行為：

> **不得**：偷偷排除該股票、提前賣掉以避開事件、忽略事件、以 adjusted price 補洞、
> **把 holding 設為 zero**、跳過該 period、carry old shares forward。
> 上述任何一項均會改寫 sealed strategy history。

HX-A 把部位轉為現金，**在字面上就是「把 holding 設為 zero」**。

**因此 HX-A 不能作為現行條文下的一條實作規則。** 它需要 §6.1.12 本身在新 lineage
的預註冊裡被改寫。硬要主張「預註冊過的處置不算被禁止的那一項」，等於承認
任何處置都可以用同樣句型脫身，`fail closed` 從此形同虛設。

可以據以改寫的理由，只有一個，而且要寫在新 lineage 的規格裡：

> 該七項之所以被禁止，禁止句自己給了理由——**「均會改寫 sealed strategy history」**。
> 新 lineage 在其 window 封存**之前**即已載明此處置，該 lineage 沒有被改寫的既有歷史。
> Frozen B0 有，所以對 Frozen B0 這七項仍然絕對。

⇒ **落地順序被此條決定：先有 B1 規格（含改寫後的 §6.1.12），才談 HX-A 的實作。**
反過來做，會得到一份與 Master 現行條文直接牴觸的程式碼。

### 2.1 適用範圍（窮舉，不得擴張）

同時滿足下列**全部**條件時適用，其餘一律不適用：

1. `kind == "holder_side_reorganization_exit"`；且
2. `reconstructibility == "NOT_RECONSTRUCTIBLE"`；且
3. 該證券於事件生效點具有 §6.1.12 定義之 affected economic exposure。

**不適用於** `capital_reduction`、`stock_dividend`、或任何其他 kind ——
那些各有自己的處置（CA-1 / CA-2），本文件不碰。

### 2.2 處置

於 `ex_or_effective_date`（權威狀態來源之停止交易邊界）的日內順序中，
於 mark 之前，將該證券之**全部** affected exposure 一次轉為現金：

```
cash_proceeds = P_anchor × Q_total
Q_total       = 標的股數 + security receivable 股數
                + entitlement-bearing claim 股數 + unresolved pending-exit claim 股數
```

`Q_total` **不取整、不捨去零股**。B0.7 的阻斷點正是一筆 `int()` 永遠 credit 不了的
不足 1 股 claim；若本規則沿用取整，同一道牆會原地保留。

### 2.3 `P_anchor` 的唯一定義

> `P_anchor` = 封存價格語料中，該 `stock_id` **嚴格早於** `ex_or_effective_date`
> 的**最後一個 observed session** 之 `close`。

- 取 `close`，**不取** `open`，不取任何均價。
- 取**未經 share-unit 調整的原始成交價**（該日實際成交的價格）。
  share-unit 調整用於動能序列的可比性，不用於清算一筆真實部位。
- `post_event_prices` 為 §R8 禁止輸入；**事件前**之最後成交價不是 post-event，
  故本規則不牴觸 R8。

### 2.3a ⚠ 邊界用的是停止交易日，不是持股人邊界——這是一個具名假設

`ex_or_effective_date` 來自 `security_status.csv` 的停止交易日，
而 §3.3 已明載**停止交易日不必然等於持股人不再持有舊證券的那一天**
（基準日通常在其後數日至數週）。本規則不可重建的原因，正是那個基準日拿不到。

⇒ HX-A **以停止交易日代替持股人邊界**。這是一個假設，不是一項事實：

- 若真實基準日晚於停止交易日，HX-A 使持股人**提早**離場，
  區間內的後手股價格變動不會反映在投組上；
- 該區間長度不可觀測（若可觀測，事件就不會是不可重建的）。

此假設**必須**與 §3 的揭露一併報告，且**不得**以「通常只差幾天」為由省略。

### 2.4 陳舊上限（fail-closed，非容忍）

> 若 `ex_or_effective_date` 與 `P_anchor` 所在 session 之間，
> 依 `trading_calendar` 相隔 **超過 10 個 trading session**，
> 則**不得**套用本規則，run 依 §6.1.12 fail closed。

**10 這個數字的來源，以及它為什麼在看到任何結果之前就能定：**
凍結前對全部 158 筆量測邊界與前一個 observed session 的距離，
得到中位數 1 個日曆天、p90 3 天、**141 窗口內最大 5 天**。
10 個 session 對窗內全部 90 筆有充裕餘裕，同時會攔下語料 vintage 造成的假陳舊
（`4987@2026-05-21`、`3426@2026-06-02` 兩筆的最後 session 皆為語料終點 2026-04-01，
距離 50 與 62 天）。

⚠ 此參數取自**價格可得性分布**，不取自任何價格水準、報酬或投組結果。
它是 data-availability 參數，與 §19 的 lineage price floor 同性質。

### 2.5 現金的時點與可動用性

- 現金於 `ex_or_effective_date` 當期記入，
  其 spendable 時點依 §6.1 既有的 owned / tradable / spendable 三分規則決定，
  **本規則不另創時點語義**。
- 不產生 receivable，不產生後手證券部位，不建立任何 successor holding。
  規則的整個效果就是「部位變成現金」。

### 2.6 事實與假設不得混淆

套用本規則所產生的 `cash_proceeds`：

- **不得**寫入任何名稱含 `actual` 的欄位；
- **必須**帶 `reason` 前綴 `HX-A:`（比照 CA-2 的 `CA-2:` 慣例，
  該慣例已被實測為唯一可靠的辨識鍵）；
- **不得**混入任何以「觀測到的離場對價」為母體的統計。

---

## 3. 揭露（強制，且不設門檻）

任何使用本規則的 run，其 §9.7 強制報告**必須**額外包含：

1. 實際套用 HX-A 的事件清單（`stock_id`、`ex_or_effective_date`、`P_anchor`、
   `P_anchor` session、相隔 session 數、`Q_total`、`cash_proceeds`）——**即使為空**；
2. `cash_proceeds` 總額佔該期 NAV 之比例，與全期最大值；
3. 因 §2.4 陳舊上限而 fail closed 的事件清單。

⚠ **上述為揭露，不是閘門。** 本文件**不**設「影響低於 X% 才算數」之條款：
一旦影響大小可以改變行為，`b0_claim_size` 就從後門回到了推論輸入裡，
而它是 R8 明文禁止的八項之一。

---

## 4. 可證偽性與被取代

- 日後若以合格來源取得任一事件之真實對價與交付日（§R4 三類來源之一，
  且滿足 R6 兩次獨立抽取一致），**真實值一律取代 HX-A 的推估值**，
  該事件回到 `RECONSTRUCTIBLE`。
- 取代不需重開本文件，因為本文件從一開始就宣告自己是後備而非事實。
- 反之，**不得**因為某個 HX-A 結果不好看而回頭改本規則。

---

## 5. 預期影響（凍結時記錄，供日後逐項覆核）

```
holder_side_reorganization_exit 總數                     158
  141 期窗口內                                            90
  窗口外                                                  68

P_anchor 可得性（凍結時實測）
  窗口內 90 筆        有邊界前 observed session          90  (100%)
  窗口外 68 筆        有                                   8
                      無任何價格（皆早於價格語料起點）      60

邊界 − 最後 observed session 之距離（158 筆中有價的 98 筆）
  中位數 1 日曆天 · p90 3 天 · 窗口內最大 5 天 · 全體最大 62 天
  §2.4 上限 10 sessions 會攔下的：2 筆（皆為 2026-04 之後、語料 vintage 所致）
```

⇒ **窗口內 90 筆全部可套用，無一觸及陳舊上限，不需要 fallback。**

⚠ 「可套用」不等於「run 會跑完」。§6.1.12 的中止另有其他觸發路徑
（配股 A-9、CA-1/CA-2 未落地、以及本文件不涵蓋的 kind），本文件不涵蓋它們。

---

## 6. 本文件**沒有**做的事

- 沒有授權任何 run，沒有指定 lineage，沒有登錄 B1。
- 沒有重開 FROZEN_B0，沒有改 `REGISTERED_L2_LINEAGES`，沒有動 §9.6e-R5。
- 沒有改任何程式碼——實作是另一次工作，且必須與本文件逐字相符。
- 沒有處理 `capital_reduction` 與 `stock_dividend`（見 CA-1 / CA-2）。
- 沒有估算本規則對報酬的影響——**那要跑完才知道，而跑完才知道正是本文件先凍結的理由。**

---

## 7 · ⚠ 落地障礙（凍結時已知，一併記錄）

### 7.1 本規則不能用在 Frozen B0

`strategy semantics changed = TRUE`（見文首）。Frozen B0 的 141 個
market-side state hash 與既有 run 不得因此改變，且其 L2 額度已消耗。
本規則的唯一去處是新登錄的 lineage。

### 7.2 價格語料比交易日曆少四個半月

```
price_panel.parquet  最後 session = 2026-04-01
trading_calendar.csv 最後一列     = 2026-08-17
```

若新 lineage 的 window 延伸至 2026-08-31（以銜接 L3 之 2026-09 起跑），
**2026-04-02 之後無任何價格可用**，且該區間的 2 筆 exit
（`4987@2026-05-21`、`3426@2026-06-02`）會直接觸及 §2.4 而 fail closed。

⇒ 該區間需要**重新匯出價格語料**。這與本規則無關，是獨立的前置條件，
但它與 §2.4 交互作用，故記錄於此。

### 7.3 §6.1.12 需先被改寫

見 §2.0。這是三項障礙裡**唯一必須先於實作**的一項。

### 7.4 本文件不解決 §6.1.12 的其他觸發路徑

CA-1 / CA-2 於 `docs/預註冊_配股不可重建事件處置_2026-09-02.md` 凍結，
其 §6 明載兩條規則都需要 Master 封閉交易才能落地。
HX-A 與它們**互相獨立**，但一次 run 要跑完，三者都要到位。
