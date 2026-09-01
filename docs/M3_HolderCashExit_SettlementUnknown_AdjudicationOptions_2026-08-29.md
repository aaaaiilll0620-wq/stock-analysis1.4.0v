# M-3 · 現金對價已確立、結算日未確立的 holder 消滅 — 裁決選項書

**狀態：`OPTIONS ONLY — NOT ADJUDICATED`**
本文件之外未變更任何 code、master prereg、data；未建立 run、未封存、未 stage、未 commit。
`data/b0/corporate_actions_ledger.csv` 與所有 sealed panel 位元組未動。

**標的：** `core/b0_corporate_actions.py:577` `handle_holder_side_reorganization_exit`
所生之 `NOT_RECONSTRUCTIBLE`，在 B0.8 已確立現金對價之後是否仍然成立。

**觸發：** B0.7 diagnostic replay 於 seq 67（2020-01）因
`8913|holder_side_reorganization_exit|2020-01-14` 中止，F-CA-B。
B0.8 的 D7.x 已把該事件的對價條款查實，但 D8.2 的結算日來源路線三處皆阻。

⚠ **撰稿者揭露（C-73 §21.6）：** 本選項書撰寫時，撰稿者已觀測 B0.1–B0.7
至 seq 66 的 `port_value` 序列。本裁決若被採納，將改變 141 期窗口的可完成性，
因而與績效有因果關聯。**四個選項的判準必須是條款層的，不得引用任何 NAV 數值**；
下方「尚待量測」節刻意只列非績效量。

---

## 0. 把裁決標的縮到最小：四個缺項裡，只剩一個

`handle_holder_side_reorganization_exit` 的 `NOT_RECONSTRUCTIBLE` 理由句列了四項缺失。
B0.8 逐項的現況（`research/b0_8_holder_terms/`）：

| 原判缺項 | B0.8 現況 | 來源 |
|---|---|---|
| successor security | **不存在後手證券**。全銓租賃（8913）→ 宏育管理顧問，`DOMESTIC_ENTITY_NO_PUBLIC_SECURITY` | `successor_side_history_and_presence_d7_2c.json` |
| conversion ratio | **NOT_APPLICABLE**（無股份對價） | `holder_consideration_semantics_d7_2_1.json` |
| cash consideration | **已確立**：「普通股 1 股，換發新臺幣 13.4 元現金」（108-12-03 股臨會決議）。原判 `MIXED_LEG_PRESENT` 經 D7.2.1 修正為 `CASH_ONLY` | 同上 |
| credit / settlement date | **仍未確立** | `extraction_readiness_freeze_d8_0.json` |

`required_field_dependency_closure_d8_1.json` 對 8913 的結論：

```
required_frozen_fields : [cash_consideration_per_old_share,
                          holder_effective_boundary, settlement_date]
missing                : [settlement_date]
readiness              : NOT_READY_SOURCE_ACQUISITION
```

**四個自由度收斂成一個：`settlement_date`。** 這才是裁決標的。

### 0.1 為何不能等取數

D8.2 三站皆阻，且阻因不是工作量：

```
d8_2a   GATE: NOT_ESTABLISHED_BEYOND_ISOLATED_CONTROL   BULK_STOCK_ACQUISITION: NO_GO
d8_2c   source_family_closure_verdict: CLOSURE_BLOCKED_BY_COVERAGE_OR_ACCESS
d8_2d   SUCCESSOR_RECORD_PRESENT_TRANSACTION_LINKAGE_NOT_ESTABLISHED
```

d8_2a 自己寫明 `no_go_does_not_establish_global_not_reconstructible = true`
——「取不到」不等於「不可重建」。**那句話正是本選項書存在的理由。**

---

## 1. 四條既有硬約束（每個選項都必須自證不違反）

1. **§6.1.4 · `CashReceivable` 必須帶 `cash_available_date`，且不得推論。**
   `core/b0_state.py:337-339`：「when it becomes spendable is not inferable from
   when it was created.」
2. **就地升級被明文禁止。** `core/b0_corporate_actions.py:582-585`：未來取得條款的修復
   「should emit a `holder_side_security_conversion`, **not quietly upgrade this one**」。
3. **`holder_side_security_conversion` 是「條款或無」。**
   同檔 :610 — 「Terms or nothing — and nothing means fail loud, not a guess.」
4. **reconstructibility 是封閉三態。** `RECONSTRUCTIBILITY_STATES` 窮舉，
   且模組標頭載明「Three states, never two」；W-1 明文
   「No interpolation. No missing-rate threshold anywhere in this module.」

**約束 1 與 4 是本案真正的張力所在：** 經濟內容已完全確立（13.4 元 × 股數，
生效邊界已知，無後手證券），唯一未知的是**何時可動用**。
而 §6.1.4 的 `owned ≠ tradable ≠ spendable` 三分**本來就是為了表達這種差異而凍結的**
（`core/b0_state.py:255-264`）。

---

## 選項 A · 維持 `NOT_RECONSTRUCTIBLE`

不裁決，等 D8.2 取數或永久阻塞。

- **成本：** 141 期窗口在 8913（2020-01）永久中止。Frozen B0 的 retrospective
  主證據線就此封頂在 66 期，L3 成為唯一前進路線。
- **正確性：** 無懈可擊。它只是拒絕回答。
- **但要誠實記一句：** 現況的 `NOT_RECONSTRUCTIBLE` 理由句已與事實不符 ——
  它說「未確立 successor security / ratio / cash consideration / credit date」，
  而前三項已由 B0.8 確立。**即使選 A，該理由句也必須改寫**，否則規範文字
  在陳述一件可被自身證據推翻的事。

## 選項 B · 明示 settlement convention（推定一個日期）

例如「結算日 = 消滅邊界後第 N 個交易日」或法定上限日。

- **直接違反約束 3 與 4。** 這正是 W-1 的 no-interpolation 所禁止的動作，
  且 `holder_side_security_conversion` 的「Terms or nothing」是同一句話的另一種寫法。
- **列出僅為完整性。事前意見：否決。** 一個推定的日期會讓策略在一個
  可能尚未收到的日子動用資金，而它在 receipt 上看起來與真實成交無異
  —— 正是 `docs/研究紀律_ResearchDiscipline.md` 所稱的靜默類缺陷。

## 選項 C · 新增第四態 `RECONSTRUCTIBLE_OWNED_NOT_SPENDABLE`

凍結：現金請求權自 `holder_effective_boundary` 起 **owned**、計入 NAV（金額由
授權欄位確立，無估計）；`cash_available_date` 未確立 ⇒ **永不 spendable**。

- **不發明任何日期。** 它把「未知」如實編碼為「不可動用」，而非推定一個值。
- **方向單一保守。** 低估可用資金 ⇒ 低估再投資 ⇒ 不會製造樂觀偏誤。
- **代價：打開封閉三態。** 約束 4 的「Three states, never two」是刻意的，
  第四態會波及每一個讀 `RECONSTRUCTIBILITY_STATES` 的消費者。
- **代價：被鎖現金單調累積**，且隨事件數增長（見「尚待量測 M2」）。

## 選項 D · 以 `holder_side_security_conversion` 發出，`cash_available_date` 帶明示 sentinel

與 C 的**經濟內容完全相同**，登錄位置不同：不動三態，改在 §6.1.4 讓
`CashReceivable` 接受一個明示的 `NEVER_ESTABLISHED` sentinel，
其語義為「owned、計入 NAV、永不到期、永不 spendable」。

- **符合約束 2**：正是「emit a `holder_side_security_conversion`」所指的路徑。
- **變更點更小更局部**：一個 dataclass 的欄位語義，而非全域狀態機。
- **但要正面回答約束 3**：sentinel 算不算「guess」？
  本選項書的主張是**不算** —— guess 是填一個可能為真的日期；
  sentinel 是宣告該日期未被任何權威來源確立，並據此拒絕動用資金。
  **這句話必須進裁決理由，否則 D 與 B 在事後讀起來會像同一件事。**

---

## 交叉比較

| | A 維持 | B 推定日期 | C 第四態 | D sentinel |
|---|---|---|---|---|
| 違反 W-1 no-interpolation | 否 | **是** | 否 | 否 |
| 發明條款 | 否 | **是** | 否 | 否 |
| 偏誤方向 | 無 | **不明（雙向）** | 保守 | 保守 |
| 動到封閉三態 | 否 | 否 | **是** | 否 |
| 141 期可完成 | **否** | 是 | 是 | 是 |
| 變更幅度 | 僅理由句 | 中 | 大 | 小 |

**撰稿者事前意見（量測前）：D > C > A > B。** D 與 C 經濟內容相同而 D 的變更面小；
A 是安全但代價明確的退路；B 應明文否決並保留為 rejected history。

---

## 尚待量測（**必須以非績效方式**，裁決前完成）

- **M1 · 母體。** D7.6 的 `AC12_denominator` 給出 `FINAL_CASH_ONLY = 26`
  （另 `FINAL_STOCK_ONLY 30 / FINAL_MIXED 3 / FINAL_SEMANTIC_UNKNOWN 0`）。
  其中「對價已確立但結算日未確立」的**確切子集數**尚未點算 —— 本裁決的實際射程。
- **M2 · 被鎖現金上限（可在不跑 replay 的情況下推導）。**
  §4.2 的 `w_target = 5%`，故單一事件至多鎖住當期組合的 5%。
  上限 = M1 子集數 × 5%，**不需要任何 NAV 數值**。
  若該上限已高到會實質改變組合行為，D／C 的「保守」就不再是小修正，
  必須在裁決文書中明白承載。
- **M3 · 是否有事件連 `cash_consideration` 都未確立** —— 那類無論如何都走 A，
  不在本裁決射程內。

⚠ **M2 是本案唯一可能翻盤的量測，且它刻意設計成不看績效即可算。**

---

## 本選項書**未**主張的事

- 未主張 8913 之外任何事件的分類。
- 未主張 D8.2 應停止取數 —— 取得真實結算日在任何選項下都優於 sentinel，
  且可在事後以 `holder_side_security_conversion` 正常路徑取代。
- 未主張本裁決可回溯改寫 B0.1–B0.7 任何 run 的位元組（C-57 不動）。
- 未主張 Frozen B0 的正式 L2 路徑因此重開（C-72 已封閉，本案不觸及）。

---

# Evidence appendix · M1 / M2（2026-08-29，非績效量測）

來源：`research/b0_8_holder_terms/required_field_dependency_closure_d8_1.json`
（`per_event`，n=158）與 `extraction_readiness_freeze_d8_0.json`（effective_date）。
本節未讀取任何 NAV、report、gate 或 `port_value`。

## M1 · 本裁決的確切射程 = **19 事件**

158 筆 holder-side 事件依 `semantics × missing` 分佈：

| semantics | missing | n |
|---|---|---|
| **UNKNOWN** | consideration semantics | **104** |
| **CASH_ONLY** | **settlement_date** | **19** ← 本裁決射程 |
| STOCK_ONLY | successor_credit_date | 15 |
| STOCK_ONLY | successor_credit_date, successor_security_id | 5 |
| STOCK_ONLY | holder_effective_boundary, successor_credit_date | 3 |
| STOCK_ONLY | holder_effective_boundary, stock_conversion_ratio, successor_credit_date | 3 |
| STOCK_ONLY | stock_conversion_ratio, successor_credit_date | 2 |
| MIXED | settlement_date, successor_credit_date | 1 |
| MIXED | settlement_date, successor_credit_date, successor_security_id | 1 |
| MIXED | successor_credit_date | 1 |
| CASH_ONLY | holder_effective_boundary | 1 |
| CASH_ONLY | holder_effective_boundary, settlement_date | 1 |
| CASH_ONLY | （無） | 1 |
| STOCK_ONLY | （無） | 1 |

⚠ **D7.6 的 `30/3/26/0` 是 TPEX_59 子集，不是全母體。** 全母體 158 筆的
semantics 分佈為 `UNKNOWN 104 / STOCK_ONLY 29 / CASH_ONLY 22 / MIXED 3`。
引用時務必分清兩個母體。

### M1 的第一個後果：本裁決**不保證** 141 期可完成

**104 筆事件的對價語義至今未確立**，它們在任何選項下都維持
`NOT_RECONSTRUCTIBLE`。只要 B0 在窗口內持有其中任何一檔並走到其消滅邊界，
replay 一樣中止。**「裁決 19 筆」與「141 期跑得完」是兩件事**，
文書不得暗示前者蘊含後者。

## M2 · 被鎖現金上限

19 筆中，effective_date 落在 141 期窗口（2014-07-30 ~ 2026-03-31）內者 **17 筆**
（2026-05-21 的 4987 與 2026-06-02 的 3426 在窗外）：

```
2016: 8079 8266 3658      2017: 6022 6105      2018: 6554 4103
2019: 5480 1787           2020: 8913 4947      2021: 2928 3144
2022: 8406 5102           2023: 6247           2025: 6747
```

全部 19 筆皆為 **TPEX**。

**理論上限：** `w_target = 5%`（§4.2），故

```
被鎖現金上限 = 17 x 5% = 85% of 組合
```

**這推翻了選項書正文「保守 = 小修正」的事前假設。** 若 B0 恰好持有全部 17 檔，
選項 C／D 會把 85% 的資金永久凍結，策略本身即失去可量測性 ——
一個「保守」到摧毀待測對象的處置，不是保守，是換了一個問題。

### M2 的反向證據：實測暴露率遠低於上限

上限假設 B0 持有全部 17 檔。B0.1–B0.7 的 replay 史提供了一個**非績效**的實測：

- replay 走到 2020-01（seq 67）才中止；
- 在 8913 之前，窗口內已有 **9 筆** 同類事件（8079 … 1787）；
- replay **一筆都沒有因它們中止** ⇒ B0 對那 9 筆**皆無暴露**。

**觀測到的暴露率：1 / 10。** 據此外推，17 筆的期望暴露約 1.7 筆，
對應約 8.5% 資金鎖定 —— 與 85% 的上限相差一個數量級。

⚠ **但 n=1 的外推不是證據。** 真實數字只有把 replay 跑完才知道，
而那正是本裁決要授權的事。**裁決文書必須同時載明 85% 的上限與 1/10 的實測暴露率，
不得只引用有利的那一個。**

## M3 · 連對價都未確立者

`CASH_ONLY / missing: holder_effective_boundary`（1 筆）與
`CASH_ONLY / missing: holder_effective_boundary, settlement_date`（1 筆）
不在射程內：邊界未確立者無論如何走選項 A。
104 筆 `UNKNOWN` 同理。

---

# Evidence appendix · M4 · 104 筆 UNKNOWN 的可關閉性與「D 買到哪裡」

同一組非績效來源。本節未讀取任何 NAV、report、gate 或 `port_value`。

## M4.1 · 窗口內母體與已走過的部分

141 期窗口（2014-07-30 ~ 2026-03-31）內的 holder-side exit 事件共 **90 筆**：

```
8913 及之前（replay 已走過）  48 筆   其中僅 1 筆造成中止（8913 本身）
8913 之後（前方風險）         42 筆
```

**觀測暴露率 = 1/48 ≈ 2%。** 這是一個 conformance 事實（哪些事件導致 abort），
不是績效量。它把選項書正文 M2 的 `1/10` 修正為 `1/48` —— 母體算錯了，
先前只數了 CASH_ONLY 一類，未計入同樣走過而未中止的 UNKNOWN 與 STOCK_ONLY。

## M4.2 · 104 筆 UNKNOWN 的結構

```
venue        NON_TPEX(TWSE) 99   TPEX 5
窗口內        49            窗口外 55（多為 2004–2013）
8913 之後     23            其中 NON_TPEX 21 / TPEX 2
```

**那 99 筆 NON_TPEX 正是 `d8_2a` 的 `twse_99`**，而該閘門已判：

```
BULK_STOCK_ACQUISITION : NO_GO
next_stage_if_no_go    : source-family coverage/semantics closure for
                         successor_credit_date, NOT a 99-event bulk crawl
```

**⇒ 104 筆 UNKNOWN 的主體（99/104）落在一條已被判定不可用 bulk 方式關閉的路線上。**
它們不是「還沒做」，是「已經評估過且否決了現有作法」。

## M4.3 · D 的實際射程

前方 42 筆依語義分佈，以及 D 是否解得掉：

| semantics | n | D 解得掉？ |
|---|---|---|
| UNKNOWN | 23 | ✗（21 筆卡在 TWSE 99 NO_GO） |
| CASH_ONLY · 只缺 `settlement_date` | **7** | **✓** |
| CASH_ONLY · 缺 `holder_effective_boundary` | 2 | ✗（邊界未確立，走選項 A） |
| STOCK_ONLY | 8 | ✗（其中 1 筆 8420 已無缺項） |
| MIXED | 2 | ✗ |

**D 直接解 8 筆：8913 本身 + 前方 7 筆。前方仍有 35 筆 D 解不掉。**

前方第一道牆：**2020-02-17 的 3562（TPEX, UNKNOWN）**，距 8913 僅一個月。
**最壞情況 D 只買到 1 期。**

## M4.4 · 完成機率（粗估，須標明為粗估）

以 M4.1 的 `p = 1/48` 逐事件獨立為假設：

| 情境 | 前方未解 | P(141 期跑完) |
|---|---|---|
| **不採納 D** | — | **0%**（現在就卡在 8913） |
| 採納 D | 35 | ~48% |
| D ＋ STOCK_ONLY 姊妹裁決 | 31 | ~52% |
| D ＋ 姊妹裁決 ＋ 關閉 21 筆 TWSE UNKNOWN | 10 | ~81% |

⚠ **這張表是粗估，不得當作結論句引用。** 三個弱點必須同時載明：
(1) `p` 由 **n=1** 的觀測導出；
(2) 假設逐事件獨立，而 B0 的選股有集中性，消滅類個股在 value/momentum 母體中
未必均勻分佈；
(3) 採納 D 之後軌跡會改變，前方暴露不再與已觀測前綴同分佈。

## M4.5 · 結論：D 是必要但遠不充分

- **必要**：不採納 D，141 期的完成機率是 **0**，現在就停在 seq 67。
- **不充分**：D 把完成機率從 0 推到約五成，**主要槓桿不在 D**，
  而在那 21 筆前方 TWSE UNKNOWN。把它們關掉才會把機率推到八成。
- **姊妹裁決的邊際效益很小**（+4 個百分點）。`STOCK_ONLY` 只缺
  `successor_credit_date` 者可用與 D 同構的
  「owned、計入 NAV、永不 tradable」處理，但前方只有 4 筆，
  且後手證券若無公開報價則連 mark 都做不到 —— **與 D 不對稱，不應假設可比照辦理**。

### 對裁決的直接建議

D 的成本（M2：最壞 85% 資金鎖定）與 D 的收益（完成機率 0 → ~48%）
應當**一起**呈現。若治理層認為 ~48% 不足以承擔 M2 的最壞情況，
理性順序是**先攻 21 筆 TWSE UNKNOWN 的 source-family closure**（d8_2a 自己指的
`next_stage`），再回頭裁 D —— 屆時 D 的邊際收益會從 +48pp 變成把 ~81% 推向接近 100%，
而 M2 的風險不變。

**本節不建議跳過 D，只指出 D 單獨執行的期望值低於先做 TWSE closure 再執行 D。**
