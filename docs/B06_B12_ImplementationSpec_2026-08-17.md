# B-06 / B-12 Implementation Spec(Frozen B0 Execution Semantics)

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17 R1/R2/R3 裁決 + 「做一份 Implementation Spec,不是改 code…逐項標明現有 code 哪裡需要 change / delete / rename / add guard」。
**合規:** **未修改任何程式碼、未回測、未產生名單、未做參數掃描。** 未 stage、未 commit。

**狀態:`CLOSED`(2026-08-17,使用者拍板 S1–S4 並追加 G7/G8 與 sell-first / no-leverage 規則)。**

---

## 1. Frozen B0 Execution Semantics(規範性陳述)

### 1.1 政策常數(frozen)

| 符號 | 值 | 性質 |
|---|---|---|
| `C_ref` | NT$2,000,000 | **initial / reference portfolio capital** —— 只定義起始規模,**不是**永久門檻的來源 |
| `w_target = w_max` | **5%** | 單檔目標權重,同時是上限 |
| `N_target` | **20** | 目標檔數 |
| `X_buy` | **1% of ADV20** | 永久 execution policy |
| `X_sell` | **1% of ADV20** | 永久 execution policy |
| **entry eligibility horizon** | **1 trading day** | 新建標準 5% 部位須具備「一日內以 ≤`X_buy` 建立」的容量。**這是 eligibility 判準,不適用於出場。** |
| **exit participation cap** | **1% ADV20 / 日** | 出場**不要求**一日完成;一日賣不完的殘額按日 carry forward 至歸零(見 §1.5) |
| odd-lot | **ENABLED** | 帳本以 **share** 為 canonical unit |
| ADV-cap shortfall | **留現金,不重分配** | |
| cost model | **B-14 liquidity-aware** | 不沿用舊 canonical constants |

### 1.2 衍生量(**dynamic,非 frozen parameter**)

```
ADV_floor(t) = port_value(t) × w_target ÷ X_buy
             = port_value(t) × 5% ÷ 1%
             = 5 × port_value(t)
```

| port_value | 單檔 5% 部位 | `ADV_floor(t)` |
|---:|---:|---:|
| 2,000,000 | 100,000 | 10,000,000 |
| 3,000,000 | 150,000 | 15,000,000 |
| 4,000,000 | 200,000 | 20,000,000 |
| 6,000,000 | 300,000 | 30,000,000 |

> **⚠ 永久記錄:`ADV_floor` 是每期衍生量,不是凍結參數。** NT$10,000,000 僅是 `port_value = C_ref` 時的派生值,**在數值上與現行 `--adv-floor=1e7` 相同純屬巧合,兩者來源無關**。程式碼**不得**重用 `--adv-floor`,須以新識別名承載並在同處註記推導式。任何文件不得將 B0 門檻描述為「沿用 1e7」。

### 1.3 真正被宣告的 policy(規範措辭)

> **每檔完整 target position 必須能在一個交易日內,以不超過 ADV20 的 1% participation 建立;出場同此上限。**

「ADV ≥ 1,000 萬」不是政策,只是 `port_value = C_ref` 時的推論。

### 1.4 Eligibility gate 與 order cap 是兩個不同角色(不得合併實作)

| 層 | 判定時點 | 判定對象 | 語意 |
|---|---|---|---|
| **Eligibility gate** | 建倉決策前 | `ADV20_i ≥ ADV_floor(t)` | 這檔股票**有沒有能力承載**一個標準 5% 部位 |
| **Order cap** | 送單時 | `單日買/賣金額 ≤ ADV20_i × 1%` | 這張**實際訂單**是否超量 |

兩者數值同為 1%,但作用於不同物件、不同時點,**必須是兩段獨立程式碼**。

### 1.5 Residual exit / sell-first / no-leverage(S3 裁決,規範性)

**出場不受「一日完成」約束。** 既然 `X_sell = 1% ADV20` 已宣告,就不得因為到了 rebalance 日而例外全出 —— 否則 1% cap 是假的。

```
當日最多賣 = X_sell × ADV20_i
未完成部分 → 標記 pending_exit,下一交易日在同一日 cap 下續賣,直到持股歸零
```

**Rebalance day 執行順序(不可調換):**

```
1. 產生 required sells
2. 在當日 sell capacity 內執行
3. 未完成 → pending_exit
4. 依「實際已實現」的可用現金執行新買單
```

**三條硬約束:**
- **不得用預期賣出收入預支新倉。** 未成交的 sell 不算變現。
- **B0 不借款、不允許負現金。**
- `pending_exit` 部位**仍屬持倉**:計入 `port_value`,share 數不得消失,未實現賣出價金不得計入 available cash。

**後果(是 execution reality,不是模型錯誤):** 若舊部位流動性惡化,新組合可能暫時 under-invested,並同時持有 residual old names。

---

## 2. Pipeline 順序(規範性,順序不可調換)

```
1. Canonical PIT universe
2. Data complete-case            (B-15;required features 全部 PIT-available)
3. Dynamic investability eligibility   ADV20_i ≥ 5 × port_value(t)
4. Risk eligibility                    (solvency / data quality)
5. SelectionScore ranking              (Quality/Growth/Value/Momentum 等權)
6. 取前 N_target = 20 檔
7. target weight = w_target = 5%
8. 實際訂單再受 order cap  ≤ ADV20_i × 1%（單日）
9. shortfall → cash（不重分配）
```

**步驟 3、4 必須在 5 之前。** 若先排序再篩流動性,breadth 會變成不穩定的殘量(Top20 裡剔掉 5 檔剩 15),違反 B-09 已定的「排除與排序分離」。

---

## 3. 逐項程式碼異動表

### 3.1 `scripts/universe_screen_daily.py`

| 位置 | 現況 | 動作 | 依據 |
|---|---|---|---|
| `:50` `MIN_PCT_SAMPLES = 60` | expanding PE 分位樣本門檻 | **DELETE** | B-09 移除 expanding PE 分位 |
| `:51` `PE_HISTORY_START = "2019-01-01"` | PE 分位錨點 | **DELETE** | F-D 錨點解除 |
| `:53` `DATA_START_CUTOFF = "2019-01-10"` | 新 IPO 判定基準日 | **DELETE** | R3 —— 由 PIT + B-02 window 取代 |
| `:54` `REVENUE_LAG_DAYS = 10` | 月營收固定 lag 代理 | **DELETE** | B-01 改讀真實 `release_date` |
| `:58-62` 三個 fail-loud 守衛 | 指向已退場的 c2 四腳 | **RE-POINT(保留,改指向)** | 是 fail-loud 守衛不是計分門檻;須改指向 B0 四 concept |
| `:111` `--adv-floor = 1e7` | L1 粗篩門檻 | **DELETE** | 作用於投組不讀的池;由 §1.2 動態 gate 取代 |
| `:114` `--shortlist-union-pct = 15` | 五因子聯集門檻 | **DELETE** | shortlist 聯集不屬 B0 |
| `:122` `--full-pool-adv-floor = 1e6` | **投組真正吃到的門檻** | **REPLACE** 為 §1.2 動態 gate | §1 決定性發現 |
| `:219` L0 `value_pct.notna()` | PE 有效性門檻 | **DELETE** | B-15 complete-case 接手;Value 已改 B/M |
| `:220` L1 `adv20 >= adv_floor & listed_ok` | 粗篩 + 上市滿一年 | **DELETE 兩者** | ADV 由動態 gate 取代;上市滿一年依 R3 由 complete-case 自然決定 |
| `:221` L2 價值陷阱 `value_pct>90 & ~(revenue_yoy>0)` | 人工交互排除 | **DELETE** | R2 —— 兩個人工切點 + 對 Value/Growth 重複計分 |

### 3.2 `scripts/l4a_decision.py`

| 位置 | 現況 | 動作 | 依據 |
|---|---|---|---|
| `:43` `ORDER_ADV_CAP = 0.03` | 買進單筆上限 3% | **CHANGE → `0.01`** | `X_buy = 1%` |
| `:44` `FUSION_PCT = 20` | 80/80 雙腿硬交集 | **DELETE** | B-09 兩腿合一,交集在結構上不存在 |
| `:46` `LOT_SIZE = 1000` | 部位計量單位 | **RENAME / RESCOPE** → 僅供 execution/display 層的整張分組,**不得再參與部位或成本運算** | odd-lot |
| `:54` `TOP_N = None` | 濃縮開關(預設關) | **REPLACE → `N_TARGET = 20`** | breadth 政策 |
| `compute_target_list` 全函式 | 讀 A 腿 composite + B 腿 `c2_fullpool`,80/80 交集 | **REWRITE** —— 單一 `SelectionScore`,依 §2 順序,eligibility 先於 ranking | B-09 + B-12 |
| `compute_order_intent` `target_weight = 1.0 / n` | 依實際檔數等分 | **CHANGE → 固定 `w_target = 5%`** | §4-S2 |
| `compute_order_intent` `port_value` 計算位置 | 在 `target_list` 之後,且用 target list 的價格表 | **MOVE —— 必須在 eligibility 之前計算** | §4-S1 |
| 剔除持倉區塊(`order_lots = 全部持倉`、`adv_capped=False`、`adv20=None`) | 賣出無任何 ADV 檢查 | **ADD `X_sell` cap** | 政策 |
| reject reason `資金不足一張` | 整張制產物 | **DELETE** | odd-lot |
| `target_lots = floor(target_amount ÷ (price × LOT_SIZE))` | 整張捨去 | **REWRITE → shares** | odd-lot |

### 3.3 `scripts/l4b_execution.py`

| 位置 | 現況 | 動作 | 依據 |
|---|---|---|---|
| `:48-54` 成本凍結註記 | 明文「不得引入新成本假設而不重新對照 H4」 | **REWRITE** —— 該註記是 Frozen A 的相容性約束,B 已廢除該目標;不改會留下自相矛盾的凍結宣告 | 政策 |
| `:55-56` `BUY_COST` / `SELL_COST` | 0.001585 / 0.004585 | **DELETE** —— 移交 B-14 | 政策 |
| `:69` `filled_lots: int` | 帳本以張計 | **RENAME → `filled_shares`** | odd-lot |
| `:183` `amount = lots × LOT_SIZE × open_price` | 金額由張數推導 | **REWRITE → `amount = shares × open_price`** | odd-lot |
| `:193-195` `avg_cost` 以 `lots × LOT_SIZE` 推導 | 成本基礎綁死張數 | **REWRITE → `avg_cost = total_cost ÷ shares`** | odd-lot;`:192` 註解記載此區曾出過單位 bug |
| `:210` `realized_pnl` 以 `lots × LOT_SIZE` 計 | 同上 | **REWRITE → 以 shares 計** | odd-lot |
| `:311` 顯示 `{filled_lots}張` | 顯示層 | **KEEP,改為由 shares 換算的顯示分組** | odd-lot |

### 3.4 需新增的 guards

| # | Guard | 防止的失效 |
|---|---|---|
| **G1** | `port_value(t)` 必須在 eligibility 之前算出,且**不得**依賴 target list 的價格表 | §4-S1 的順序違反 |
| **G2** | 每檔入選標的須滿足 `w_target × port_value(t) ≤ X_buy × ADV20_i`,否則 abort | eligibility 與部位大小脫節 |
| **G3** | `len(eligible) < N_target` 時走明文的 under-invested 路徑,**不得**改用 `1/n` 抬高權重 | §4-S2 |
| **G4** | 帳本中不得殘留任何 `× LOT_SIZE` 的部位/成本運算 | odd-lot 單位 bug 復發(`:192` 前例) |
| **G5** | legacy 雙腿路徑(`FUSION_PCT` / `c2_fullpool` 讀取)必須不可達,誤觸即 abort | 舊路徑靜默復活 |
| **G6** | 賣出訂單須套 `X_sell`,且 `adv20` 不得為 `None` | 現行賣出無檢查 |
| **G7** | **Pre-trade valuation independence** —— `port_value(t)` 的 mark price 必須在 target/ranking 建立前取得;**禁止**從 target-list-specific lookup 反推 portfolio value | selection 反向決定 portfolio valuation(回測樂觀偏誤,難察覺) |
| **G8** | **Residual exit integrity** —— `pending_exit` 部位:每交易日必須套 `X_sell`;未成交 shares 不得消失;未成交價值仍計入 `port_value`;未實現賣出價金不得計入 available cash | 殘餘部位靜默蒸發 / 用未變現資金建新倉(回測樂觀偏誤,難察覺) |

---

## 4. 缺口與裁決結果(S1–S4 **全部已拍板 2026-08-17**)

### S1 · `port_value` 的計算順序與現行相反 🔴

現行 `compute_order_intent` 的 `port_value = pos.cash + pos.holdings_value(combined_lookup)`,而 `combined_lookup` 是由 **`target_list` 的價格表**加上持倉價格表組成 —— **即 `port_value` 在 `target_list` 之後才算得出來**。

但 §1.2 的 `ADV_floor(t) = 5 × port_value(t)` 要求 `port_value` 在 **eligibility 之前**就已知,而 eligibility 又在 target list 之前。**順序完全相反。**

**✅ 裁決(APPROVED):** 定義

```
port_value(t) = cash(t) + Σ_i  shares(i,t) × mark_price(i,t)
```

`mark_price` **不得**來自 target list,**不得**依 `SelectionScore` / eligibility 決定,須由 decision date 的 **PIT 全市場價格來源獨立取得**。

**規範順序:** `PIT market prices → pre-trade portfolio value → ADV_floor → eligibility → ranking → target list`

**既有持倉在 as-of 無可用 mark price 時,不得因「它不在候選池」而視為 0** —— 須 fail-loud 或依既定 PIT mark policy 處理。**selection 不得決定 portfolio valuation。**(guard:G7)

### S2 · `eligible < 20` 時的權重規則未定義 🔴

現行 `target_weight = 1.0 / n`。若某期合格標的只有 15 檔,現行會給 **1/15 = 6.67%**,**直接違反 `w_max = 5%`**。

**✅ 裁決(APPROVED):**

```
target_weight_i = 5%   for every selected eligible name
len(selected)   = min(20, len(eligible))
未使用權重 → cash,不重新正規化
```

例:僅 15 檔 eligible → `15 × 5% = 75%` 股票 + 25% 現金。**不是** `1/15 = 6.67%`。

**⚠ 明文禁止 `1/n`**,否則 `w_max` 形同虛設,且組合會在標的最少(通常也是流動性最緊)的時候把單檔曝險推到最高。(guard:G3)

### S3 · 賣出 shortfall 無處置規則 🔴

買進 shortfall → cash 已明文。但月頻全換股 + `X_sell = 1%` + 1 日 horizon 的組合下,**一個部位可能無法在一日內出清**(例如持有期間該檔 ADV 萎縮,或部位因漲價而超過原規模)。

現行程式碼賣出**無任何上限**,所以這個情境不存在;加了 `X_sell` 之後就會出現。

**✅ 裁決(APPROVED):`daily residual exit carry-forward` + `sell-first` + `cash-only buys`。完整規則見 §1.5,guard 見 G8。** 同時修正 horizon 措辭(§1.1):**entry eligibility 是一日;exit 不是。**

### S4 · `20 × 5% = 100%` 不留成本與 shortfall 的餘裕

**✅ 裁決(APPROVED):明文 `Σ w_actual ≤ 100%`,不是 `= 100%`。**

`5%` 是每檔的 target weight **兼** maximum target weight;`20 × 5% = 100%` 只是 **nominal maximum target exposure**,**不構成 fully-invested requirement**。實際股票曝險低於 100% 的合法成因:交易成本、ADV order cap、`pending_exit`、odd-lot 執行差異、可用現金、`eligible < 20`。**shortfall 一律回 cash,永不重新正規化。**

---

## 5. 容量事實(R1 動態化的直接推論,凍結記錄)

`ADV_floor(t) = 5 × port_value(t)` 意味著組合規模有一個**結構性上限**:當第 20 大 ADV20 的標的都無法承載 5% 部位時,breadth = 20 即不可行。

```
port_value_max(t) = ADV20(第 20 大)(t) ÷ 5
```

凍結窗口 141 期實測(純資料,非績效):

| 統計 | `port_value_max` (NTD) |
|---|---|
| 最小 | **105,612,486** |
| p10 | 134,039,230 |
| 中位 | 314,103,312 |
| 最大 | 1,770,137,900 |

**⇒ 本策略在既定政策下的容量下界約 NT$1.06 億,遠高於 `C_ref` 的 200 萬。** 容量在可預見規模內不是限制。

合格檔數(中位 / 最小):

| port_value | `ADV_floor` | 合格檔數(中位) | (最小) |
|---:|---:|---:|---:|
| 2,000,000 | 10,000,000 | **865** | 582 |
| 10,000,000 | 50,000,000 | 453 | 273 |
| 20,000,000 | 100,000,000 | 303 | 173 |

**⇒ `N_target = 20` 在 `port_value` 達 NT$2,000 萬時仍有 173–303 檔可選,breadth 可行性充裕。** S2 的 under-invested 路徑在可預見規模內是罕見分支,但仍必須明文定義。

---

## 6. 一致性檢查

| 檢查 | 結果 |
|---|---|
| `w_target × N_target = 5% × 20 = 100%` | ✅ 自洽(餘裕見 S4) |
| `ADV_floor = w_target/X × port_value` 與「一日內可建立完整部位」等價 | ✅ 定義即等價 |
| Eligibility(1%)與 order cap(1%)數值相同但角色不同 | ✅ §1.4 已分離;order cap 在 `port_value` 成長時恢復實質效力 |
| `X_sell = X_buy` 與月頻全換股相容 | ✅ S3 —— exit 改 daily carry-forward,horizon 措辭已分離 entry/exit |
| odd-lot 與「資金不足一張」拒單理由 | ✅ 後者刪除後自洽 |
| R2/R3 刪除項與 B-09 去切點原則 | ✅ 一致 |
| 動態 floor 與 `port_value` 計算順序 | ✅ S1 —— 改用獨立 PIT 全市場價格快照 |
| `eligible < 20` 時的權重 | ✅ S2 —— 固定 5%,不重新正規化 |
| `Σ w_actual` 語意 | ✅ S4 —— `≤ 100%`,非滿倉要求 |

**全部轉綠。**

---

## 7. CLOSED

**B-06 / B-12 於 2026-08-17 正式 `CLOSED`。** 最終 execution semantics:

```
C_ref              = NT$2,000,000        (initial / reference scale only)
N_target           = 20
w_target = w_max   = 5%
X_buy = X_sell     = 1% ADV20
ADV_floor(t)       = 5 × pre-trade port_value(t)      [dynamic, not frozen]
entry eligibility horizon = 1 trading day
exit                      = daily 1% cap, residual carry-forward
pipeline           = complete-case → investability → risk eligibility
                     → SelectionScore → Top20 → 5% target → order cap
ledger unit        = shares (odd-lot); lot 僅為顯示分組
eligible < 20      → under-invested,不重新正規化
buy shortfall      → cash
sell shortfall     → pending_exit(每日續賣)
sells first;new buys 只用已實現現金;no leverage;no negative cash
retired            = FUSION_PCT / TOP_N / c2 雙腿投組路徑、value trap、
                     DATA_START_CUTOFF、上市滿一年、舊 BUY_COST/SELL_COST
```

**下一步:B-14 Closure。** 第一項要求(使用者指定):把成本拆成**顯性交易成本**與**市場衝擊 / slippage** 兩塊分別處理 —— 至此 participation、ADV、entry horizon、odd-lot、pending exits 全部鎖定,成本模型才有乾淨的 execution context 可用。

---

**本輪未修改任何程式碼、未回測、未產生名單、未做參數掃描。未 stage、未 commit。**
