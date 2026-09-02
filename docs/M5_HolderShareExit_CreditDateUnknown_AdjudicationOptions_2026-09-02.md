# M-5 · 股份對價已確立、撥券日未確立的 holder 消滅 — 裁決選項書

**狀態：`OPTIONS ONLY — NOT ADJUDICATED`**
本文件之外未變更任何 code、master prereg、data；未建立 run、未封存、未 stage。
`data/b0/` 所有位元組未動。

**標的：** `core/b0_corporate_actions.py:577` `handle_holder_side_reorganization_exit`
所生之 `NOT_RECONSTRUCTIBLE`，在後手證券與換股比例皆已確立之後是否仍然成立。

**與 M-3 的關係：** M-3 處理**現金**對價已立、`settlement_date` 未立者。
本文處理**股份**對價已立、`successor_credit_date` 未立者。
兩者形狀對稱，但**經濟內容不對稱**（見 §2），故不併入 M-3 而另立。

> **撰稿者揭露：** 本 session **未**讀取任何 NAV、`port_value`、報酬、報表或 gate 輸出。
> 讀取的是 `data/b0/corporate_actions_ledger.csv`、`stock_dividend_pit.csv`、
> `security_status.csv`、`price_panel.parquet`（原始價格，非策略產物）
> 與外部採集的公告本文。下方所有數字均為條款層或資料層。

---

## 0 · 把裁決標的縮到最小：9 筆，缺一個欄位

外部採集（Part A pass 1 + Part D pass 2，`_handoff/*_FILLED.csv`）就 90 筆
`holder_side_reorganization_exit` 逐筆查證後，本文射程如下（⟨M⟩ 本 session 複驗）：

```
90 筆窗內事件
├─ 48  無任何官方文件                    → 不在射程（對價未確立）
├─  4  有文件但對價未確立                 → 不在射程
├─ 21  純現金對價已立,缺 settlement_date  → M-3 射程
├─  8  有換股比例但缺 successor_security_id → 不在射程（見 §0.1）
└─  9  ★ 後手證券 + 換股比例 + 基準日皆立,唯缺撥券日  ← 本文射程
```

⚠ **一筆重疊：`4429`（聚紡）是混合對價**（現金 5 元 + 換股比例 1.2，後手 4433），
同時落在 M-3 與本文射程。它需要**兩份裁決都通過**才可重建，
因為 `RECONSTRUCTIBLE_MIXED` 要求現金腿與股份腿的日期都齊備。
另一筆混合對價 `5466` 缺後手代號，僅落在 M-3 射程的現金腿，本文不處理。

`CLASS_REQUIRED_FIELDS[RECONSTRUCTIBLE_STOCK]`（`core/b0_corporate_actions.py:207`）
要求 `successor_security_id`、`stock_conversion_ratio`、`holder_effective_boundary`、
`successor_credit_date` 四項。這 9 筆前三項齊備，**自由度收斂成一個：`successor_credit_date`。**

| 舊代號 | 後手 | 基準日 | 後手價格涵蓋 |
|---|---|---|---|
| 1566 | 5392 | 2019-07-31 | 2013-01-02 … 2026-04-01 |
| 5317 | 2375 | 2019-09-30 | 2013-01-02 … 2026-04-01 |
| 4429 | 4433 | 2022-05-31 | 2013-02-18 … 2026-04-01 |
| 6594 | 6684 | 2023-04-01 | 2018-05-29 … 2026-04-01 |
| 5281 | 4972 | 2023-10-31 | 2013-01-02 … 2026-04-01 |
| 4944 | 6488 | 2023-11-01 | 2014-10-28 … 2026-04-01 |
| 8420 | 8938 | 2024-11-29 | 2013-01-02 … 2026-04-01 |
| 6457 | 2363 | 2025-01-01 | 2013-01-02 … 2026-04-01 |
| 4945 | 2436 | 2025-09-08 | 2013-01-02 … 2026-04-01 |

⟨M⟩ **9/9 的後手證券都在 `data/b0/price_panel.parquet` 內，且涵蓋期延伸至 2026-04。**
此點是 §2 與選項 D 可行性的前提，故先量。

### 0.1 · 為何 8 筆「有比例無後手代號」不在射程

那 8 筆的公告載明了換股比例卻未載後手證券代號。缺的是**身分**不是**時點**，
而身分未定者無從評價、無從撥入。它們與 §0 的 48 + 4 同屬「對價未確立」，
依 M-3 §M3 的既有裁定一律走選項 A。**本文不為它們提供任何處置。**

### 0.2 · 為何不能等取數

⟨M⟩ 四層來源已查證，皆不載交付日期：

```
TWSE TWT49U/TWT49UDetail、TPEx exDailyQ    價格與配股率,無日期欄
TWSE TWT48U 除權除息預告表                  無日期欄
TWSE OpenAPI t187ap45_L 股利分派情形        日期僅董事會擬議日與股東會日期
MOPS 依 companyId (t05st01)                下市公司一律 406
MOPS 依日期 (t05st02) 清單                  含下市公司,3,186 交易日約 104 萬列
MOPS 本文 (t05st02_detail)                 對停止公開發行者拒發:「不繼續公開發行！」
交易所終止買賣公告                           六款結構固定,不含付款日與撥券日
```

Part D 針對存續方那一側再查一輪：命中交付語彙的主旨 364 篇、取得本文 185 篇，
**42 列中無一列補上任何交付日期**。唯一新查得的日期是 4429 的
「增資發行新股**權利證書**上櫃日期 111/5/31」，而文件未說明它等於撥券日或可賣日，
依 §D2 未填入任何 schema 欄。

⇒ 「取不到」已非未經檢驗的假設。

---

## 1 · 四條既有硬約束（每個選項都必須自證不違反）

沿用 M-3 §1，行號本 session 複驗：

1. **§6.1.4 · 三分是刻意的。** `core/b0_state.py:258-266`：
   `owned != tradable != spendable`，並明文「Collapsing either pair lets execution
   sell shares nobody holds yet」。
2. **就地升級被明文禁止。** `core/b0_corporate_actions.py:582-585`。
3. **`holder_side_security_conversion` 是「條款或無」。** 同檔 `:610`
   「Terms or nothing — and nothing means fail loud, not a guess.」
4. **reconstructibility 是封閉三態**，且 W-1 禁插值、禁缺失率門檻
   （`:714-715`、`:719` 斷言，並綁進 `core/b0_master_prereg.py:1467-1468`）。

**本案的張力所在：** 經濟內容已完全確立（後手證券、換股比例、生效邊界皆由官方公告載明），
唯一未知的是**何時可賣**。而 `SecurityReceivable`（`core/b0_state.py:269`）的 docstring
第一行就是「a security claim that is **owned but not yet tradable**」——
**這個結構本來就是為了表達這種差異而存在的。**

---

## 2 · ⚠ 與 M-3 的不對稱：股份會漂移，現金不會

**這是本文件不能併入 M-3 的唯一理由，也是選項比較的關鍵。**

M-3 的選項 C／D 把未知結算日的現金編碼為「owned、計入 NAV、永不可動用」。
被鎖住的現金**金額固定**，其 NAV 貢獻是常數，代價單調且可上界。

股份不是。一筆 owned-but-never-tradable 的後手股：

- 必須被評價 —— `core/b0_state.py:250-253` 明文：
  「A holding absent from the price source is **not worth 0** and must not be dropped —
  abort and resolve the input.」
- 而評價基準已凍結：`ca_valuation_basis = "RAW_OBSERVED"`
  （`core/b0_master_prereg.py:1303`）。
- ⇒ 它的 NAV 貢獻**隨後手股價逐日變動，且永遠不會結束**。

於是產生一個 M-3 沒有的問題：

> 一個永遠不能賣的部位，會把後手證券**整條價格路徑**帶進投組淨值，
> 而投組對它**完全無法行動**。窗口愈長，這個不可控暴露愈大。

⚠ 這不是反對意見，是**選項 D 必須正面回答的代價**。§3「尚待量測」列出量它的方法，
且該量測必須以非績效方式進行。

---

## 選項 A · 維持 `NOT_RECONSTRUCTIBLE`

不裁決，等取數或永久阻塞。

- **成本：** 這 9 筆事件只要 B0 在基準日持有該證券即中止 run。
  ⟨M⟩ 90 筆 `holder_side_reorganization_exit` 全部通過暴露性檢驗
  （事件日前 60 天內皆有價格），故**每一筆都是真實的阻塞風險**，
  與 CA-2 那 40 筆「不可能持有」的情形不同。
- **正確性：** 無懈可擊。它只是拒絕回答。
- **但要誠實記一句：** 現行 `NOT_RECONSTRUCTIBLE` 的理由句宣稱
  「未確立 successor security / ratio / cash consideration / credit date」，
  而**前兩項已由官方公告確立**。**即使選 A，該理由句也必須改寫**，
  否則規範文字在陳述一件可被自身證據推翻的事。（與 M-3 §選項 A 同型。）

## 選項 B · 明示撥券 convention（推定一個日期）

例如「撥券日 = 基準日後第 N 個交易日」。

- **直接違反約束 3 與 4。** 這正是 W-1 的 no-interpolation 所禁止的動作。
- 且股份版比現金版**更危險**：一個推定的撥券日會讓投組在一個可能尚未持有的日子
  **賣出後手股**，而它在成交回報上與真實賣出無異。
- **列出僅為完整性。事前意見：否決**，並保留為 rejected history。

## 選項 C · 新增第四態 `RECONSTRUCTIBLE_OWNED_NOT_TRADABLE`

- 與 M-3 選項 C 同型，代價相同：**打開封閉三態**，波及每一個讀
  `RECONSTRUCTIBILITY_STATES` 的消費者。
- 若 M-3 已選 D，本文再選 C 會造成兩條同型裁決走不同機制，**不建議**。

## 選項 D · 發出 `SecurityReceivable`，`credit_tradable_date` 帶明示 sentinel

凍結：後手股請求權自 `holder_effective_boundary` 起 **owned**、計入 NAV
（股數 = 舊股數 × 換股比例，精確 `Fraction`，不四捨五入，依 §6.1.9）；
`credit_tradable_date` 未確立 ⇒ 帶 `NEVER_ESTABLISHED` sentinel，語義為
**「owned、計入 NAV、永不到期、永不 tradable」**。

- **不發明任何日期。** 與 M-3 選項 D 同一句論證：sentinel 不是 guess ——
  guess 是填一個可能為真的日期；sentinel 是宣告該日期未被任何權威來源確立，
  並據此拒絕賣出。**這句話必須進裁決理由，否則 D 與 B 在事後讀起來會像同一件事。**
- **符合約束 1**：`SecurityReceivable` 的定義本來就是 owned-not-tradable。
- **符合約束 2**：日後取得真實撥券日者，依 `:582-585` 另發事件，不就地升級。
- **變更點小而局部**：一個 dataclass 欄位的語義，與 M-3 選項 D 同一處機制。
- ⚠ **但它把 §2 的漂移問題吃下來了。** 被鎖股份的 NAV 貢獻隨後手股價變動，
  且沒有終點。這一點必須在裁決理由中明說，不得省略。

## 選項 E · 同 D，但**凍結評價**於基準日（股份版特有）

與 D 的持有語義相同，差別只在評價：該請求權以**基準日當日的後手股價**計價並固定，
不隨後續價格變動。

- **好處：** 消除 §2 的無限漂移，被鎖部位的 NAV 貢獻變成常數，與 M-3 的現金版對稱。
- **代價：直接牴觸已凍結的宣告** `ca_valuation_basis = "RAW_OBSERVED"`
  （`core/b0_master_prereg.py:1303`）。凍結一個不再被觀察的價格是
  **編造一個市場沒有給出的數字**，其性質更接近選項 B 而非 D。
- **事前意見：否決**，理由如上。列出是因為「讓被鎖部位不漂移」是個合理的直覺，
  而該直覺與 `RAW_OBSERVED` 的衝突必須被明文記錄一次，否則它會反覆出現。

---

## 交叉比較

| | A 維持 | B 推定日期 | C 第四態 | D sentinel | E 凍結評價 |
|---|---|---|---|---|---|
| 違反 W-1 no-interpolation | 否 | **是** | 否 | 否 | 否 |
| 發明市場未給出的數字 | 否 | **是** | 否 | 否 | **是** |
| 牴觸 `RAW_OBSERVED` 宣告 | 否 | 否 | 否 | 否 | **是** |
| 偏誤方向 | 無 | **不明（雙向）** | 保守 | 保守 | 不明 |
| 動到封閉三態 | 否 | 否 | **是** | 否 | 否 |
| 被鎖部位是否漂移 | — | — | **是** | **是** | 否 |
| 這 9 筆可完成 | **否** | 是 | 是 | 是 | 是 |
| 與 M-3 機制一致 | — | — | 否 | **是** | 否 |
| 變更幅度 | 僅理由句 | 中 | 大 | 小 | 小 |

**撰稿者事前意見（量測前）：D > A > C > E > B。**
D 與 M-3 選項 D 共用同一機制，是兩份裁決一致性的最短路徑；
A 是安全但代價明確的退路；B 與 E 應明文否決並保留為 rejected history。

⚠ **本意見的前提是 M-3 選 D。** 若 M-3 選了 A 或 C，本文的排序必須重算 ——
兩份對稱裁決走不同機制，會製造一個沒有人能記住的例外。

---

## 3 · 尚待量測（**必須以非績效方式**，裁決前完成）

1. **NAV 路徑是否真的評價 `security_receivables`。** ⟨M⟩ 本 session 未能在
   `core/` 內找到 NAV 彙總函式；`security_receivables` 是宣告登錄中的 state dimension
   （`core/b0_master_prereg.py:1298-1301`），但「被宣告」不等於「被計入淨值」。
   **選項 D 與 E 的差別在這個答案未知之前都是空談。**
2. **被鎖部位的規模上界。** 以舊股數 × 換股比例 × 後手股價，逐月計算這 9 筆
   在窗口內各月的名目金額。**不得引用任何投組實際持股或 NAV** ——
   以「若全額持有」的上界計算即可。
3. **這 9 筆的實際暴露月數。** B0 是否真的在基準日持有該證券，是暴露的前提。
   此項需讀取投組狀態，**因此必須在裁決之後、或以不可見於撰稿者的方式進行**。

---

## 4 · 本選項書**未**主張的事

- 未主張這 9 筆應被完成。選項 A 仍然在桌上。
- 未處理 §0 的 48 + 4 + 8 = 60 筆對價未確立者，依 M-3 §M3 一律走 A。
- 未處理 M-3 射程內的 21 + 1 筆現金族。
- 未主張 M-3 應選哪個選項。
- 未授權任何 run，未指定 lineage（FROZEN_B0 不可重開，B1 尚未登錄）。
- 未估算任何選項對報酬的影響 —— 那要跑完才知道，而跑完才知道正是先凍結規則的理由。
