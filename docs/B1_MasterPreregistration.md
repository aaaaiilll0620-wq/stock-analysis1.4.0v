# B1 · Master Preregistration

**版本：** 0.1（草案，尚未生效）
**lineage id：** `B1`
**授權者：** `aaaai`
**授權依據：** 2026-09-03 於 session 之決定，並以
`_handoff/HANDOFF_2026-09-03_CA_blockers_and_seam.md` §0 之五項要求為據
**狀態：`DRAFT — B1 尚未登錄於 REGISTERED_L2_LINEAGES，Baseline Seal 尚未建立`**

---

## §0 · 本文件的範圍與繼承

B1 **以引用方式繼承** Frozen B0 之 master preregistration：

```
繼承基底 : docs/FrozenB0_MasterPreregistration.md
版本     : 1.37
sha256   : 7366517839357b664e07bb986d94df3d4596e8669f4bb47d95beb178d9a8975a
```

**繼承基底之位元組不得被修改。** B0.1–B0.7 之 diagnostic runner 將該 sha256
釘入其不可變 run 紀錄（`EXPECT["spec_sha256"]`），任何編輯都會使那些紀錄
指向一份不存在的文件。B1 的每一條差異一律寫在本文件，**絕不回頭改基底**。

**本文件只記載差異。** 未在此提及者，一律依繼承基底辦理。

⚠ **撰稿者揭露（依基底 C-73 §21.6）：** 撰稿者與授權者於起草時均已觀測
Frozen B0 `period_progress.jsonl` 之 `port_value`（含 seq 66）。
本文件之任何參數**不得以績效理由辯護**。

---

## §1 · 差異一 · 窗口 —— 無差異（原宣告已撤回）

| | Frozen B0 | B1 |
|---|---|---|
| `window_start` | 2014-07-31 | 2014-07-31（同） |
| `window_end` | 2026-03-31 | 2026-03-31（同） |
| `window_months` | 141 | 141（同） |

**B1 之窗口以引用繼承 Frozen B0，非以複製。**
`core/b0_master_prereg._WINDOW_INHERITS_FROZEN_B0` 含 `B1`，
`lineage_spec("B1", ...)` 委派給 `spec()`。三個數字因此仍只有一個家
—— 寫兩次的凍結參數會一直一致，直到不一致的那一天（C-55）。

### §1.1 · 撤回記錄 · 145 / 2026-07-31

本文件初稿宣告 B1 窗口為 **145 期、終於 2026-07-31**，
並稱「端點為導出量，非選擇」，依據是
`data/b0/trading_calendar.csv` 終於 2026-08-17。

⛔ **該依據不成立。交易日曆不是綁定語料。**⟨2026-09-03 實測⟩

每一張封章輸入面板都是照 B0 `window_end` 裁過的，
這是各 builder 自己的 receipt 寫的：

```
price_panel          date_max   2026-04-01   ← B0 最後一個執行日
valuation_panel      periods    141
financials_pit       window_end 2026-03-31   （剔除 2,954 列窗後發布）
monthly_revenue_pit  window_end 2026-03-31   （剔除 8,446 列）
market_side_state    periods    141
```

逐期核對 145 個月的結果：**2026-04 / 05 / 06 / 07 四個月皆無 as_of 價格、
無執行日價格、無估值。** 材料化會在 2026-04 fail loud
（每檔於缺 as_of 時 `continue` → rows 空 → `SystemExit`），
但**宣告引錯語料本身就是缺陷**，不因下游有閘門接住而不是。
它與「價格腿落後日曆」是同一個形狀，只是差四個月而非十一天。

原宣告因此撤回。因為撤回，**§1.1 原本與 v1.33 的區別論證也隨之失去標的**
—— B1 不再提出 145，v1.33 的觀感問題一併消失。本節不得被讀為
「145 曾經可受」：它從來不可受，只是理由不是當時寫的那個。

⚠ **繼承不是妥協，是 B1 的本質。** B1 的實質內容是三條
corporate-action 裁決（SD-SKIP、CA-1、HX-A/CASH），而非更長的窗口。

### §1.1b · 更正 · 市場側並非不受影響

本節初稿主張：三條裁決全在 `core/b0_corporate_actions.py` 走
`transition_portfolio`，屬投組側；市場側讀 `core/b0_share_unit_adjustment.py`，
故 B1 的 market-side state 應與 B0 逐位元相同。

⛔ **實測為假。**⟨2026-09-03⟩`build_market_side_state` 會將每筆事件的
`reconstructibility` 從 ledger 抄進被雜湊的 market state，所以一條重新分類
事件的裁決，即使從不在市場側被呼叫，也會到達市場側。

相同窗口、相同輸入重建後，**141 期中 129 期不同**，差異全部集中在一個欄位：

```
事件 (kind, date) 集合              完全相同，0 筆差異
reconstructibility 變動           795 筆
NOT_RECONSTRUCTIBLE -> NOT_APPLICABLE   795
其他任何方向                        0
```

**單向、單一方向，沒有意外 —— 這就是 CA-1。**
故 B1 之封章輸入確實是它自己的，其 Baseline Seal 並非重述 B0。
**共用窗口正是讓這件事可量測的原因**：同一窗口、同一語料，
才能把三條裁決孤立成唯一的變項。

⚠ **順帶查出：`data/b0/` 工作樹已內部不一致。**
`corporate_actions_ledger.csv`、`stock_dividend_pit.csv`、`bonus_share_panel.parquet`
三份的現行位元組已與 B0 freeze registry 不符，
而 `data/b0/market_state/` 仍停留在 2026-08-20 的舊 ledger。
**B0 已封存之識別未受損** —— archived seal 不可變且載有真值
（`865b2028...` 於 2026-08-19 統封）；漂移的是工作樹，不是記錄。
上述 B0/B1 差異因此不是「B1 vs B0」，而是「現行 ledger vs B0 states 當時所據之 ledger」；
B1 的 states 才是對應現行 ledger 的那一份。

### §1.1a · 2026-04 至 2026-07 的去處

這四個月**不是被放棄**，而是回到它們本來的位置：
**L3 前瞻路線**。`core/b0_l3_price_span.py` 定義
`price_span[1] = execution_date`，L3 無固定窗口終點，逐月往前走。
它們是真正的樣本外月份；塞進 L2 回測窗口等於把樣本外變成樣本內。
基底 §9.6a 自己的語句：a changed specification is a new version
(B1, B2 ...) whose primary evidence must be **L3, not this window**。

⚠ **代價須明載：**B1 花掉它那一次 once-only 觀察額度時，綁的是 141 期。
日後若要將 2026-04–07 納入 L2 窗口，**不得修改 B1**（no-post-hoc-rescue），
只能另開 lineage 並燒掉它自己的觀察額度。若要避免這個代價，
唯一時機是在 B1 執行**之前**重新設定窗口，而那需要先重建六張上游面板。

⛔ `C:/dev/b0_ext145_noncanonical_20260826` 之既有 145 期產物**不得用於 B1**。
其建於 B0 之識別下，且對應 SD-SKIP 之前的 corporate-action ledger。

### §1.2 · 產物隔離

B1 之 market-side state 寫入 `data/b1/`，**不得**寫入 `data/b0/`。
該禁止由 `research/b0_materializer/build_market_side_state.py`
之 `assert_not_writing_into_frozen_b0()` 以 resolved absolute path 強制，
於 `main()` 起點與每一寫入點呼叫。**是守衛，不是慣例。**

---

## §2 · 差異二 · §6.1.12 之處置清單

### §2.1 · 基底原文與其唯一理由

基底 §6.1.12 之 blocking condition 為

```
NOT_RECONSTRUCTIBLE  AND  portfolio has affected economic exposure
```

其後之禁止清單為「不得以下列手法規避該 block」：

> **不得**：偷偷排除該股票、提前賣掉以避開事件、忽略事件、以 adjusted price
> 補洞、把 holding 設為 zero、跳過該 period、carry old shares forward。
> 上述任何一項均會改寫 **sealed** strategy history。

**該清單給出的理由只有一個：改寫已封存之 strategy history。**

### §2.2 · B1 之改寫

⚠ **「B1 無既有 sealed history」不足以整條廢除清單。** 清單同時防止的是
靜默的高估與低估，該危害與是否已封存無關。故 B1 **保留清單**，改為：

> **B1 §6.1.12（本文件凍結）：** 上列處置一律禁止，**除非**該處置
> **(a)** 於 B1 首次 strategy-route 執行**之前**於本文件具名凍結，
> **(b)** 於本文件明載其偏誤方向，且
> **(c)** 該方向為單向、或已以**非績效**方式量測。
>
> 事後新增之例外一律不生效（v1.33 先例）。例外之射程以本文件所列者為限，
> 不得類推適用於未具名之事件類別。

### §2.3 · 三條規則之逐條裁決

**(1) CA-1 —— 相容，非例外。**

`core/b0_corporate_actions.py:handle_stock_dividend`，commit `29e03778`。
無除權旗標之資本額變動判為 `NOT_APPLICABLE`：`holder_multiplier = 1.0`、
既有持股數不變、不產生 SecurityReceivable。

**不觸及禁止清單**，因其主張該事件**從來不是** holder 事件：

- 312 筆窗內列全部比對官方 TWSE/TPEx 除權採集（transport failures 0），
  **帶正配股比例者 = 0**；
- 312 筆全部帶配發數量 ⇒ 新股流向認購人、轉換之債權人或員工；
- 基底 C-51 之 `FORBIDDEN_MULTIPLIER_SOURCES` 已明列
  `paid_capital_increase_shares` 與 `employee_bonus_shares` 不得導出 multiplier。

**沒有事件被忽略，只有分類被更正。** 偏誤：無。

**否證條件**：任一「無除權旗標」事件於官方公告中帶正配股比例 ⇒ 本條對該筆
失效，且整條規則重新檢視，不打補丁。

**(2) SD-SKIP —— 具名例外（依 §2.2）。**

`core/b0_corporate_actions.py:handle_stock_dividend`，commit `01ef64e5`。
缺 `股票股利上市日/發放日` 之配股事件，其配股腿**丟棄**，事件判 `NOT_APPLICABLE`。

⚠ **與禁止清單正面相撞**：它丟棄一條**真實的** holder 腿並跳過該事件，
字面即「忽略事件」。故依 §2.2 具名列為例外。

- **(a) 凍結時點**：本文件；B1 尚未執行任何 strategy route。
- **(b) 偏誤方向**：**單向低估**。持股人承受除權價格稀釋而未取得股票，
  故本規則只能使 B1 之股數與 NAV 被低估，不能美化。
- **(c) 判準**：無參數可錯 —— 不推估日期，是 receivable 根本不發。
  基底 W-1 之兩個常數（`MISSING_DATA_RATE_THRESHOLD is None`、
  `INTERPOLATION_ALLOWED is False`）未更動；被推翻者為 W-1 之**處置句**。

射程：窗內 65 筆。B1 窗口繼承 B0（141 期），故該數字直接適用，不須於 B1 之
ledger 重建後重新點算，本文件不得被引為 B1 之射程。

**(3) HX-A/CASH —— 具名例外，**已凍結並已實作**（2026-09-03）。**

規則本體：`_handoff/HXA_CASH_FreezableRule_2026-09-03.md`。
實作：`core/b0_corporate_actions.py`（`HXA_CASH_SCOPE`、`hxa_cash_quantity`、
`_hxa_cash_exit`、`transition_portfolio(hxa_anchor=...)`），commit `73b6502f`。

不可重建之 holder-side exit ＋ 有曝險 ＋ **對價語義經 B0.8 確立為 `CASH_ONLY`**
⇒ 於停止交易日、mark 之前，全部曝險以邊界前最後一個 observed session 之
`close` 轉現金。`Q_total` 精確不取整。

⚠ **與禁止清單正面相撞**：字面即「把 holding 設為 zero」。故依 §2.2 具名為例外。

- **(a) 凍結時點**：✅ 本文件，且 B1 尚未執行任何 strategy route。
- **(b) 偏誤方向**：✅ **單向低估，已量測。**
  射程內現金腿 n=19，`UNDERSTATES 19 / FLATTERS 0`，
  ratio `min 1.0008 / median 1.0052 / max 1.0075`。
  非績效量測：只比對每股價格與每股文件對價。
  成因有經濟解釋 —— 現金併購宣告後市價以套利價差小幅折價交易。
- **(c) 判準**：✅ 方向單向。

**射程限縮的理由 —— 股票腿量測失敗：** n=8，`UNDERSTATES 6 / FLATTERS 2`，
其一實質美化（4944，ratio 0.7974）。⇒ `STOCK_ONLY` / `MIXED` / `UNKNOWN`
**不在射程，且不得實作**，一律依 §6.1.12 fail closed。

**射程 22 筆中 20 筆可套用**：`3426`（gap 40）與 `4987`（gap 32）觸及 10-session
陳舊上限而 fail closed。二者之 anchor 皆為價格語料終點 2026-04-01，屬**語料
vintage 造成的假陳舊**，上限存在即為攔下它們。

**兩筆明文排除，皆為偽陰性（安全方向）：**
`4152` —— d7_1a 判 MIXED 且 d7_2_1 從未修復，與 pass-2 抽取表矛盾，未經裁決；
`6514` —— d7_2_1 將其**向下修復**為 `CONSIDERATION_NOT_ESTABLISHED`。

⚠ **實際解除之阻塞：1 筆（8913）。** 依 B0.7 CA ledger，窗內 holder-side 事件中
證券曾被 B0 觸及者僅 `8913`（殘餘 1.076 股）與 `6514`（殘餘 0.348 股），
後者不在射程。本條**不得**被讀為 holder-side 阻塞已解決。

⚠ **§2.3a 的時點假設未被消除**：規則以停止交易日代替持股人基準日，
該區間長度依定義不可觀測。上述量測**只涵蓋對價落差，不涵蓋時點落差**。
每一次套用皆須逐筆揭露。

### §2.4 · 未涵蓋者

`capital_reduction`（B0 窗內 27 筆）與 `par_value_change`（1 筆）
**無任何處置規則**，本文件亦不提出。二者於 B1 仍依基底 §6.1.12
fail closed。

---

## §3 · 本文件**未**主張的事

- 未登錄 B1（`REGISTERED_L2_LINEAGES` 仍不含之）；未建立 Baseline Seal；
  未授權任何 run。
- 未重開 Frozen B0。基底 C-72 之封閉（兩個獨立理由）不受影響。
- 未修改繼承基底之任何位元組。
- 未主張 B1 可跑完 141 期 —— 158 筆 holder-side 事件中 **104 筆**之對價語義
  至今未確立，於任何處置下皆維持 `NOT_RECONSTRUCTIBLE`。
- 未提出 `capital_reduction` / `par_value_change` 之處置。
