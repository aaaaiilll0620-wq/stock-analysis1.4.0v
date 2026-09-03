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

## §1 · 差異一 · 窗口

| | Frozen B0 | B1 |
|---|---|---|
| `window_start` | 2014-07-31 | 2014-07-31（同） |
| `window_end` | 2026-03-31 | **2026-07-31** |
| `window_months` | 141 | **145** |

**端點為導出量，非選擇。** ⟨2026-09-03 實測⟩
`data/b0/trading_calendar.csv` 終於 **2026-08-17**；2026-07-31 為其中最後一個
月底 session；其執行 session 為 2026-08-03。`2026-08-31` 不在該日曆中，
其執行日 `2026-09-01` 亦不在。

⚠ **2026-08 之月底決策無法作成。** B1 回溯腿與 L3 前瞻腿之間存在一個
**具名缺口**，成因為語料邊界，非窗口設定。本文件不得被讀為兩腿連續。

### §1.1 · 145 與 v1.33 之區別

基底之 v1.33（`docs/REJECTED_v1.33_window_forward_extension.md`）曾提出
141 → 145 並遭 **REJECT_AS_DRAFTED**。B1 之窗口在期數上與之相同，
**但動作不同**：

| | v1.33 | B1 |
|---|---|---|
| 動作 | **延長**既有窗口 | **首次設定** |
| lineage 狀態 | 已 performance-sighted（`period_progress` 66 列、NAV 已動；§9.6a-R2 條件 2 不成立） | 無 run、無 NAV、無 `period_progress` |
| §2.1 | 治理**已凍結窗口之解凍**，唯一條件未滿足 | 首次定義不經該條 |

**可受性之來源是「宣告」與「登錄」之分離**：B1 之窗口已於
`core/b0_master_prereg._LINEAGE_WINDOWS` 凍結，而 `REGISTERED_L2_LINEAGES`
**仍不含 B1**。窗口因此是在 B1 能夠執行**之前**凍結的 —— 這正是 v1.33
所欠缺者。若兩者不可分離，本條即不成立。

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

射程：窗內 65 筆（B0 窗口計）。⚠ B1 窗口為 145 期，該數字須於 B1 之
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
- 未主張 B1 可跑完 145 期 —— 158 筆 holder-side 事件中 **104 筆**之對價語義
  至今未確立，於任何處置下皆維持 `NOT_RECONSTRUCTIBLE`。
- 未提出 `capital_reduction` / `par_value_change` 之處置。
