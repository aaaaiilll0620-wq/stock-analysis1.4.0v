# B-06 / B-12 Ruling Implementation Check

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17 政策裁決 + 「只確認 code semantics、下游殘留門檻、`TOP_N`/`FUSION_PCT` 是否仍會生效、odd-lot/cap/cash 邏輯是否自洽」。
**合規:** 純程式碼檢查。**未產生績效 / IC / Sharpe / 選股名單 / 參數掃描。** 未改任何程式碼。未 stage、未 commit。

---

## 0. 凍結政策與機械推導(逐字記錄)

```
C_ref            = NT$2,000,000
w_max            = 5%
X_buy = X_sell   = 1% of ADV20
execution horizon= 1 trading day
odd-lot          = ENABLED
target breadth   = 20 names
ADV-cap shortfall= 留現金,不重分配
cost model       = B-14 liquidity-aware(不沿用舊 canonical constants)

單檔 target position = C_ref × w_max = 2,000,000 × 5%      = NT$100,000
investability floor  = position ÷ participation = 100,000 ÷ 1% = NT$10,000,000
```

**⇒ Frozen B0 investability gate = `ADV20 >= NT$10,000,000`**

> **⚠ 命名衝突警告(必須永久記錄)。** 這個 NT$10,000,000 **在數值上與現行 `scripts/universe_screen_daily.py` 的 `--adv-floor` 預設值 `1e7` 完全相同**。兩者來源完全無關:舊值是前作設定,新值是由 `C_ref × w_max ÷ participation rate` 事前機械推導。**任何文件、註解或 commit message 都不得把 B0 的門檻描述為「沿用 `--adv-floor=1e7`」** —— 那會把一個推導值重新污染成繼承值。程式碼實作時應以新常數名(例如 `B0_INVESTABILITY_FLOOR`)承載,並在同一處註記推導式,不得重用 `--adv-floor`。

---

## 1. 🔴 **決定性發現:舊的 `1e7` 作用在投組根本不讀的池子上**

| 事實 | 位置 |
|---|---|
| `--adv-floor`(1e7)套用於 **L1 候選池** `pool_{as_of}.csv` | `universe_screen_daily.py:220` |
| `--full-pool-adv-floor`(**1e6**)套用於 **`c2_fullpool_{as_of}.csv`** | `:344` |
| 兩者明文「**不共用**」 | `:123-124` |
| **投組實際讀的是 `c2_fullpool_{as_of}.csv`**,不是 `pool_*.csv`;讀不到即 `SystemExit`,且明文禁止退回 `pool_*.csv` 頂替 | `l4a_decision.py` `compute_target_list` |

**⇒ 現行 `1e7` 從未作用於投組路徑。投組路徑上真正生效的門檻是 `1e6`。**

**對實作的直接後果:把 B0 的 NT$10,000,000 設在 `--adv-floor` 的位置,不會生效。** 它必須設在投組實際讀取的母體產出點(現為 `--full-pool-adv-floor` 的位置),或設在 B-09 後取代該產出的新 canonical universe 產出點。

---

## 2. 🔴 **`C_ref` 的「ref」藏了一個未裁決的決定**

`compute_order_intent` 的部位大小是**動態**的:

```
port_value    = pos.cash + pos.holdings_value(...)      # 隨損益變動
target_weight = 1.0 / n
target_amount = target_weight × port_value
```
(`l4a_decision.py` `compute_order_intent`)

**但 investability floor 是用 `C_ref`(固定值)推導的。** 兩者不同步:

| port_value | 單檔部位(n=20) | 在 ADV = NT$10M 標的上的實際 participation |
|---|---|---|
| 2,000,000(= `C_ref`) | 100,000 | **1.00%** ✅ |
| 4,000,000 | 200,000 | **2.00%** ❌ 超出 X |
| 6,000,000 | 300,000 | **3.00%** ❌ |

**⇒ 「X = 1%」的保證只在 `port_value = C_ref` 的那一刻成立。** 需要裁決二選一:

- **(a) 固定門檻**:floor 永遠 = NT$10,000,000。則 X 隨組合成長而被突破,`X=1%` 應改述為「在 C_ref 時的 1%」。
- **(b) 浮動門檻**:floor = `port_value × w_max ÷ X`,逐期重算。則 X 恆為 1%,但**可投資母體會隨組合成長而縮小**,且門檻變成狀態相依(path-dependent),需揭露。

**本輪不自行決定。** 這一項先前未被識別,是本次檢查的產出。

---

## 3. `TOP_N` / `FUSION_PCT` 是否仍會生效 —— **會,而且與 breadth=20 直接衝突**

| 常數 | 現值 | 現行行為 | B0 下的狀態 |
|---|---|---|---|
| `FUSION_PCT` | `20` | `compute_target_list` 取 `pct_rank >= 80 且 c2_pct >= 80` 的**硬交集** | **必須退場** —— B-09 已把 A/B 兩腿的重複概念合一為單一 `SelectionScore`,「兩腿交集」在結構上不再存在 |
| `TOP_N` | `None` | 不濃縮,回傳完整交集(實測約 48 檔) | **必須改為 breadth=20 的實作載體** |

**衝突陳述:80/80 硬交集產出的是一個「隨市況變動的檔數」(約 48),而政策要求「20 檔」。兩者不可能同時成立。** 目前程式碼中**沒有任何機制實作 target breadth**,`TOP_N=None` 明確關閉了唯一的截斷路徑。

### ⚠ 必須一併揭露的相似性(避免未來被誤引用)

「依分數取前 N 檔」在數值形式上**與 `TOP_N=15` 濃縮相同**,而後者在 Frozen A 已被 **H4 滑價穩健性驗證否定**(`l4a_decision.py:47-53` 明文記載:CAGR −2.57pp、夏普 −0.20、MDD 惡化 3.0pp、損益兩平滑價僅 ≈0.26%)。

**B0 的 breadth=20 不是同一件事** —— 不同母體(canonical + ADV≥1e7 vs 舊 100 萬全池)、不同分數(單一 `SelectionScore` vs 雙腿交集)、不同成本模型(B-14 liquidity-aware vs 舊 canonical constants)、且 20 是**由 `C_ref`/`w_max` 政策推導**而非濃縮實驗。

**但兩個方向的誤引用都必須事前封死:**(i) 不得宣稱「取前 N 檔已被 H4 否定,所以 B0 不可行」;(ii) 更不得宣稱「TOP_N 早就測過了,沒問題」。**Frozen A 的 H4 結果對 B0 不具推論力,兩者都不得引用。**

---

## 4. odd-lot / cap / cash 邏輯自洽性

### 4.1 odd-lot = ENABLED → **執行帳本是整張制,需單位層重構(非設定變更)**

| 位置 | 現行 | 問題 |
|---|---|---|
| `l4a_decision.py` | `target_lots = floor(target_amount ÷ (price × LOT_SIZE))` | 整張無條件捨去 |
| `l4a_decision.py` | reject reason `資金不足一張` | odd-lot 下**不應存在** |
| `l4b_execution.py:69` | `filled_lots: int` | 帳本欄位以「張」為單位 |
| `l4b_execution.py:183` | `amount = lots × LOT_SIZE × open_price` | 金額由張數推導 |
| `l4b_execution.py:193-195` | `old_total_cost = h["lots"] × LOT_SIZE × h["avg_cost"]`;`avg_cost = (...) ÷ (new_lots × LOT_SIZE)` | **均價計算綁死張數**;`:192` 註解記載此處曾出過單位 bug |
| `l4b_execution.py:210` | `realized_pnl += (open − avg_cost) × lots × LOT_SIZE` | 同上 |

**⇒ 啟用 odd-lot 需要把整條帳本的計量單位從「張」改為「股」,涉及成本基礎、已實現損益、持倉狀態四處。這是實作工作,不是參數調整。** `:192` 的既有註解顯示這個區域對單位錯誤敏感,重構後必須有單位層測試。

**正向後果:** §4 先前識別的「`C/N ≥ LOT_SIZE × price` 高價股買不到一張」問題,在 odd-lot 下**結構性消失**。以 `C_ref/20 = 100,000` 計,現行整張制會讓所有股價 > 100 元的標的無法取得完整目標部位 —— odd-lot 移除此限制。

### 4.2 cap 邏輯 —— **語意衝突**

`ORDER_ADV_CAP = 0.03`(`l4a_decision.py:43`)vs 政策 `X = 1%`。**若不改,系統內同時存在兩個 participation rate。** 應改為 `0.01` 以求語意一致。

**但必須注意其實際效力:** 在 `port_value = C_ref` 時,eligibility gate 已保證 `部位 ÷ ADV ≤ 1%`,因此 1% 的**訂單層 cap 恰好在門檻處等號成立、在門檻以上永不觸發** —— 它是一個冗餘的 backstop。**它唯一會真正觸發的情境,正是 §2 的 port_value > C_ref。** 因此 §2 的裁決同時決定了 cap 是不是死碼。

### 4.3 cash 邏輯 —— **與政策一致**

「ADV-cap shortfall 留現金、不重分配」與現行 `l4a_decision.py` 行為一致(下修不重分配,殘額留現金,規格 §5.1)。**無須變更。**

**但依 §4.2,在 `port_value = C_ref` 時此路徑永不觸發** —— 該政策在 B0 起始狀態下是空條款,僅在 §2 選 (a) 且組合成長後才生效。

### 4.4 execution horizon = 1 trading day —— **與現行一致**

`_next_trading_day_hint(as_of)` 產生 `execution_date_hint`,`l4b_execution` 以 `open(t+1)` 成交。**符合,無須變更。**

---

## 5. 下游殘留門檻總表

| 門檻 | 位置 | B0 狀態 |
|---|---|---|
| `MIN_PCT_SAMPLES = 60` | `universe_screen_daily.py:50` | **RETIRED** — B-09 移除 expanding PE 分位 |
| `PE_HISTORY_START = 2019-01-01` | `:51` | **RETIRED** — F-D 錨點解除 |
| `--adv-floor = 1e7` | `:111` | **REPLACED** — 由推導門檻取代,且位置錯誤(見 §1) |
| `--full-pool-adv-floor = 1e6` | `:122` | **REPLACED** — 這是真正生效的位置 |
| `--shortlist-union-pct = 15`(→ >85) | `:114` | **RETIRED** — shortlist 聯集不屬 B0 |
| L0 `value_pct.notna()` | `:219` | **RETIRED** — B-15 complete-case 接手,且 Value 已改 B/M |
| **L2 價值陷阱 `value_pct > 90 且 ~(revenue_yoy > 0)`** | `:221` | **🔴 仍作用,未被任何裁決涵蓋** — 2 個人工切點、無標準定義。它位於篩選腳本而非計分引擎,**B-09 的去切點裁決沒有掃到它**。需明確裁決(候選:Remove,理由為無標準定義且與 B-09「去人工切點」一致) |
| `DATA_START_CUTOFF = 2019-01-10` / 上市滿一年 | `:53`、`listed_ok` | **🔴 仍作用,需裁決** — 屬 eligibility 規則,B-06 未涵蓋 |
| `REVENUE_LAG_DAYS = 10` | `:54` | **RETIRED** — B-01 改讀真實 `release_date`,固定 lag 代理退場 |
| `VALUE_IND_MAX_NAN_PCT = 20` / `LEG_MIN_COVERAGE_PCT = 95` / `REVENUE_STALE_WARN_DAYS = 45` | `:58-62` | **KEEP,需重新指向** — 是 fail-loud 守衛不是計分門檻,但目前指向已退場的 c2 四腳,須改指向 B0 的四個 concept |
| `BUY_COST` / `SELL_COST` | `l4b_execution.py:55-56` | **RETIRED** — 政策已裁定改用 B-14。**注意 `:48-54` 的凍結註記明文寫「不得引入新成本假設而不重新對照 H4」,那是 Frozen A 的約束,B 已明文廢除該相容性目標;實作時必須連同該註記一併更新,否則會留下自相矛盾的凍結宣告** |

---

## 6. 阻擋性實作缺口(全部是新程式碼,不是設定變更)

1. **賣出容量上限 `X_sell = 1%` 完全未實作** —— 現行剔除路徑 `order_lots = 全部持倉`、`adv_capped=False`、`adv20=None`,**無任何 ADV 檢查**。
2. **target breadth = 20 未實作** —— 無任何機制,`TOP_N=None` 關閉了唯一截斷路徑。
3. **odd-lot 需帳本單位層重構**(§4.1,四處)。
4. **investability gate 需新增於投組實際讀取的母體產出點**(§1),且以新常數名承載推導式。
5. **`ORDER_ADV_CAP` 0.03 → 0.01**(§4.2),其存廢取決於 §2。

---

## 7. 需要裁決(本輪不自行決定)

| # | 事項 |
|---|---|
| **R1** | §2 —— investability floor 固定於 `C_ref` 推導值,或隨 `port_value` 浮動 |
| **R2** | §5 —— L2 價值陷阱(2 個人工切點)去留 |
| **R3** | §5 —— `DATA_START_CUTOFF` / 上市滿一年 eligibility 規則去留 |

R1 同時決定 `ORDER_ADV_CAP` 與「shortfall 留現金」是否為死碼。

---

**本輪未產生績效 / IC / Sharpe / 選股名單 / 參數掃描,未修改任何程式碼。未 stage、未 commit。**
