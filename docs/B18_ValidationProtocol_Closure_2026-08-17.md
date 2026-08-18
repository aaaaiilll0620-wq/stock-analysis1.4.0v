# B-18 Validation Protocol Closure

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17「開始 B-18 Validation Protocol Closure…本輪只做 protocol/spec」。
**合規:** **未執行任何 B0 retrospective performance、未產生 Sharpe / CAGR / MDD / 選股名單 / 參數比較、未動 A0–A3。** 未 stage、未 commit。

---

## 0. 三層 epistemic status(本輪的核心重寫)

| 層 | 名稱 | 證據來源 | 能證明什麼 | **不能**證明什麼 |
|---|---|---|---|---|
| **L1** | `Specification Valid` | 靜態:程式碼、不變量、PIT 依賴圖 | 規格自洽、零自由參數、不變量全綠、PIT 乾淨 | 任何關於報酬的事 |
| **L2** | `Retrospectively Supported / Not Supported` | 141 月 sealed window 開封一次 | **可證偽**:規格連被挖過的資料都撐不住 | **不可證實**:該段資料已被先前研究接觸 |
| **L3** | `Prospectively Validated Edge` | **完整 Frozen B 預註冊之後**的新市場資料 | 真正的 untouched evidence | —— |

### 0.1 L2 的證據力是**不對稱**的 —— 這是整份 protocol 的支點

> **L2 失敗是強證據;L2 成功是弱證據。**

失敗方向:若規格在**已被反覆挖掘過**的歷史上都無法成立,那是嚴重的負面訊號。
成功方向:同一段歷史已經產生過 H1–H5 通過、high52 否決、TOP15 否決、overlay α 掃描否決、五維 11 個 arm 否決、C3 過 Gate 1 —— **成功可能只是又一次在已挖過的礦裡找到礦**。

**因此 L2 的正式輸出只有 `Supported` / `Not Supported`,永遠不是 `Validated`。** `Validated` 一詞保留給 L3,任何文件不得在 L2 使用它。

---

## 1. 141 個月的定性(取代先前的 holdout 構想)

```
Retrospective sealed evaluation window = 2014-07-31 .. 2026-03-31,141 個月
```

**不得**稱為 untouched OOS、holdout、或 out-of-sample。

**不再人為切 train/test,兩個理由:**
1. **B0 在該窗口內沒有需要 fitting/tuning 的參數。** 選股層自由參數為 0(B-09/B-10)、成本參數在窗口外事前凍結(B-14)、eligibility 由政策推導(B-06)。**沒有東西需要用 train 段去學** —— 切分不會產生任何新資訊,只會縮小樣本。
2. **切了也不是 out-of-sample。** 該窗口每一個月都已被先前研究看過,把後半段改名叫 test 不會使它變得未被接觸。**切分只會製造 untouched 的假象**,那比不切更危險。

**先前 B-18 被標記的張力(窗口只有 141 個月、且全被觸碰過,holdout 切不出來)在此解消 —— 解法是放棄該宣稱,不是去找更多資料。**

**真正的 untouched evidence 只能來自完整 Frozen B 預註冊凍結之後產生的新市場資料。**

---

## 2. L1 · Primary Structural Criteria(本輪凍結)

L1 全綠是 L2 開封的**前置條件**。全部為非績效判準。

| # | 判準 | 驗證方式 |
|---|---|---|
| **S-1** | Selection 路徑自由參數 **= 0** | B-09/B-10 已凍結的 feature graph;人工切點清單為空 |
| **S-2** | 所有已宣告不變量全綠 | G1–G8(B-06/B-12)、G14-1–G14-4(B-14)、B-17;測試全過 |
| **S-3** | PIT 完整性:無任何保留 feature 的 lookback > 18;`first eligible = 2014-07` 由依賴圖**機械**推導 | B-09 Phase 3 |
| **S-4** | 每期 complete-case 母體規模、eligibility 淘汰組成**逐期報告** | 診斷輸出(非門檻,只要求揭露) |
| **S-5** | eligibility **嚴格早於** ranking | B-06/B-12 Spec §2 順序 + G2/G3 |
| **S-6** | 每張收據帶 explicit_fee / transaction_tax / impact **三欄分離** | B-14 `CostBreakdown` |
| **S-7** | B0 不可達 Frozen-A 成本常數與 regime 決策路徑 | G14-4、B-17 |
| **S-8** | Provenance 完整:資料 schema/version/hash、code commit、config | B-21(尚未關閉) |

**S-8 尚未關閉 ⇒ L1 目前不可能全綠 ⇒ L2 目前不得開封。**

---

## 3. L2 · Retrospective Sealed Evaluation Protocol

### 3.1 報酬線(⚠ B0 **不能**直接沿用 Frozen A 的)

研究紀律硬規則 1:「報酬線只能是 `exec_ret.fwd_x`」,入口 `lab_paths.load_panel()`;理由是 `obs_alpha.fwd` 有兩個反向偏誤、淨誤差隨換手率變動。

**該規則的「意圖」(絕不使用有偏的 `obs_alpha.fwd`)完全承接。但其「實作」不可直接沿用:**

- Frozen A 的 `fwd_x` 是**月頻面板**量;
- B0 是 **share-based ledger + odd-lot + 每日 child order + `pending_exit` 跨日**。

**⇒ B0 的報酬線必須由 share ledger 的實際現金流與部位重建,並對帳。** 沿用月頻 `fwd_x` 會系統性錯置 `pending_exit` 的多日執行與 odd-lot 的部分部位。

**凍結:** B0 報酬線 = **由 ledger 重建的日 NAV 序列**;必須附**兩層對帳**:(a) 逐筆現金流加總 vs NAV 變動;(b) 部位市值 vs 獨立 PIT 價格快照。對帳容差與結果隨開封一併報告。

**同理,硬規則 2(`real_composite` 真身)的意圖 —— 判定必須用生產計分碼而非替身 —— 承接;B0 的對應物是 `SelectionScore`,不得以任何簡化替身頂替。**

### 3.2 Benchmark(硬規則 3:三階階梯,不是單一 0050)

依 `beat_0050/honest_backtest.py:292-310` 的既有階梯結構,**B0 必須報四列**:

| 列 | 內容 | 回答的問題 |
|---|---|---|
| ◆ 策略 | B0 | —— |
| ① 等權母體(不選股) | B0 eligibility 通過的全母體等權 | **選股能力** = 策略 − 等權母體 |
| ② 對齊隨機(N 次中位) | 同檔數、同換手的隨機選股 | **扣掉交易 footprint** = 策略 − 對齊隨機,附虛無 p |
| ③ 0050 買進持有 | —— | **機會成本** = 策略 − 0050 |

**理由(既有,非新增):** 等權策略開場就欠 0050 約 5.77pp/年,拿單一 0050 當及格線會把「加權方式」誤判成「沒有 alpha」。

**⚠ 實作限制:** `honest_backtest.py` 屬 Frozen A 且自帶 `self.cost` 比例成本。**B0 的階梯不得重用它的成本** —— 否則違反 G14-4。B0 階梯必須以 `core/b0_cost_model.py` 計價,四列使用**同一成本模型**(否則列與列之間不可比)。

### 3.3 日期 / 成本 / 股息處理(凍結)

| 項目 | 凍結值 | 理由 |
|---|---|---|
| **決策日** | 凍結 141 月月底交易日 | 承 B-02/B-09 |
| **執行日** | `open(t+1)`;多日 exit 順延交易日 | B-06/B-12 |
| **成本** | `core/b0_cost_model.py` 三分離,逐筆(含每日 child order) | B-14 |
| **`σ20D`/`ADV20` 資料窗** | 嚴格早於執行日 | G14-1 |
| **股息** | **實際除權息現金流,入 ledger 現金** | 見下 |
| **基準股息** | 0050 與等權母體亦須含息,且與策略採**同一**股息處理 | 可比性 |

**股息處理的變更理由(結構性,非績效):** Frozen A 用「均勻每日加性 `δ = dy12/n`」,那是**月頻面板沒有股數帳本時的權宜作法**(預註冊_ExposureOverlay §3-A-D-💰 已載明它與日 NAV 複利不恆等,最大月差 0.055pp)。**B0 有 share-based ledger,且語料含 `除權息2004-20260806` 全歷史** —— 因此可以、也應該用實際除息日現金流。**這是「帳本能力提升後採用更精確定義」,不是為了任何結果而改。**

**⚠ 待裁決 V-1:** 實際除權息需處理**除權(股票股利)造成的股數變動**。B0 ledger 以 shares 計量,股票股利會改變持股股數與成本基礎。此處理規則本輪未凍結,需另行裁決。

### 3.4 Reporting schema(開封時必須全數輸出,不得選擇性報告)

| 類別 | 必報項 |
|---|---|
| **階梯** | §3.2 四列 + 三個差額 + 虛無 p |
| **成本** | explicit_fee / transaction_tax / impact **三欄分別**的總額與逐期序列 |
| **執行現實** | 換手率;`pending_exit` 發生次數與跨日天數分佈;under-invested(eligible < 20)期數;`zero_sigma_fill` 次數;ADV-cap shortfall 金額 |
| **母體** | 逐期 complete-case 母體數、各 eligibility 層淘汰數 |
| **容量** | **實現的 `ADV_floor(t)` 路徑**(因其隨 `port_value` 動態,是結果不是設定)與合格檔數路徑 |
| **對帳** | §3.1 兩層對帳的容差與最大偏差 |
| **多重比較** | §4.3 的有效觀察次數計數 |

**任何一項缺漏 → 該次開封作廢。**

### 3.5 開封規則

1. **開封前提:** L1 全部 S-1..S-8 綠燈 **且** 完整 Frozen B 預註冊已凍結 **且** provenance 已記錄。
2. **開封一次。** 同一版規格對同一窗口只評估一次。
3. **開封前必須先凍結判定門檻。** 門檻寫入預註冊 §7 留白處,開封後不得修改。
4. **全量報告。** 依 §3.4,包含所有失敗項。
5. **開封事件入登記簿:** 日期、code commit、spec hash、資料 hash、判定結果。

---

## 4. No-Post-Hoc-Rescue / Versioning(凍結)

### 4.1 硬規則

> **L2 判定 `Not Supported` 之後,不得在同一窗口上調整規格重跑。**

任何開封後的規格變更 → **產生新版本(B1、B2…)**,且:

- **新版本不得以同一 141 月窗口作為 primary evidence。** 它已被該版本的失敗結果污染。
- 新版本可以把該窗口列為**次要診斷**,但必須標註「post-hoc,非獨立證據」。
- 新版本的 primary evidence 只能是 L3(新市場資料)。

### 4.2 允許的例外(唯二)

1. **實作缺陷修復** —— 規格未變、只是程式碼未忠實實作規格,且缺陷可在**不看績效**的情況下獨立證明(例如單位錯誤、對帳失敗、guard 觸發)。須記錄證明過程。
2. **資料修復** —— 輸入資料本身被證明有誤(例如 provenance 稽核發現錯誤匯入)。同樣須獨立於績效證明。

**兩者都必須在登記簿記載,且重跑計入 §4.3 的有效觀察次數。**

### 4.3 多重比較登記簿

> **DSR N=3 已知嚴重低估,明文禁止在 B0 沿用。**

必須維護一份**有效觀察次數**登記簿,計入:
- Frozen A 已知的所有評估(H1–H5、high52、TOP15、overlay α 掃描、五維 11 arms、C3…)
- B0 的每一次開封,含 §4.2 的合法重跑

**該計數必須隨任何 L2 結論一併報告。** 具體的多重比較校正方法本輪未凍結(見 §6 開放項)。

---

## 5. L3 · Prospective Validation Maturity —— **候選定義與限制(本輪不選)**

依指示**不自行選定月數**。以下為候選及其限制:

| 候選 | 定義 | 限制 |
|---|---|---|
| **M-a 固定期間** | 預先宣告 N 個月的前瞻期 | 簡單、無自由度爭議;但 N 的選擇本身無外部依據 |
| **M-b 固定再平衡次數** | 預先宣告 N 次決策 | 與月頻等價(12 次/年);同上 |
| **M-c 資訊量門檻** | 直到估計量的標準誤降到宣告水準以下 | 統計上最有依據;但**成熟時間不可預知**,且需先宣告一個效應量假設 |
| **M-d 事件涵蓋** | 直到樣本涵蓋至少一次宣告幅度的回撤/市場狀態 | 貼近實際風險關切;但**可能永遠不成熟**,且「宣告幅度」是一個新參數 |
| **M-e 預先指定序貫檢定** | 宣告型一/型二誤差率的序貫檢定 | 允許提早停止、誤差率受控;實作與紀律要求最高 |

### 5.1 三項必須一併帶走的限制

1. **頻率天花板:** B0 為月頻,一年僅 12 個觀察。**任何以夏普為基礎的判準都需要數年**才可能成熟。這是 L3 的固有成本,不是可以繞過的。
2. **L3 不因 L2 成功而縮短。** L2 的證據力不對稱(§0.1)意味著它**不能**用來降低 L3 的門檻。
3. **凍結時點:** L3 的 maturity 定義必須**與 Frozen B 預註冊同時凍結**,不得在前瞻期開始後才訂 —— 否則等於邊看邊定終點。

---

## 6. V-1 ~ V-4 裁決(使用者 2026-08-17)與實作驗證

### V-1 · Receivable accounting —— **原則採納,但資料驗證顯示範圍必須調整** 🔴

**裁決原則:** ex-right 建 receivable;實際入帳日才轉 tradable shares;總 cost basis 不增加;receivable 入帳前不得賣出;NAV 須含 receivable(否則 ex-right 價格調整會造成資產憑空消失)。

**本輪唯讀驗證 `tej_exports/DataExport0806/除權息2004-20260806/`(6 個期間檔,schema 三期抽驗一致):**

```
證券代碼 | 年月日 | 盈餘分派_迄日 | 息值(元) | 除息(權)參考價(元)
        | 現金股利(元)_盈餘 | 現金股利(元)_公積 | 股息發放日
        | 除息公告日 | 融券最後回補日 | 最後過戶日
```

| 發現 | 後果 |
|---|---|
| **無任何股票股利欄位**(無配股率、無股票股利發放日)。檔名為「除權息」,**schema 實為除息(現金)專用** | **V-1 所裁決的「股票股利 receivable → 入帳日轉 shares」以現行語料不可實作** |
| **`股息發放日` 存在**,且實測落後 ex-date 約 29 日(樣本:ex 2026-08-06 → 發放 2026-09-04 / 09-09) | **現金股利的 receivable 處理可實作,且是 rule-critical 的那一個** |

#### V-1a · 現金股利 receivable(**凍結,可實作**)

```
ex-date (年月日)      : cash_dividend_receivable += shares × 每股現金股利
                        tradable_cash 不變
股息發放日             : cash += receivable ; receivable = 0
NAV                   : 含 receivable
```

**🔴 這一項與 B-06/B-12 已凍結的規則直接相扣。** S3 裁決明訂「不得用預期賣出收入預支新倉;B0 不借款、不允許負現金」。**若在 ex-date 就把現金股利記入可用現金,B0 就能用尚未收到的錢建倉 —— 那是同一條 no-leverage 規則的另一個破口,只是來源從賣出價金換成股利。** 現行 Frozen A 的加性 `dy12/n` 模型完全沒有這個概念。

**⇒ V-1a 不只是精確度改良,是補上一個已凍結規則的漏洞。**

#### V-1b · 股票股利(**BLOCKED,記為資料缺口**)

裁決原則**保留不變**,但**現行語料無法支持**。三條可行路徑,本輪不自行選擇:
1. 向 TEJ 另行匯出含配股率與股票股利發放日的資料集;
2. 由 `除息(權)參考價` 與前收盤、現金股利**反推**配股率 —— 這是**推論不是資料欄位**,須先獨立驗證後才可採用;
3. 明文宣告 B0 窗口內不處理股票股利,並揭露其影響範圍。

**在 V-1b 解決之前,L1 的 S-3(PIT 完整性)不得記為綠燈。**

### V-2 · Single-primary-hypothesis design(**凍結**)

- **L2 只設一個正式 primary economic comparison**(見 V-4)。formal family size = **1**。
- 其餘全部指標(CAGR、Sharpe、MDD、Calmar、turnover、cost drag、cash%、等權母體、對齊隨機、Frozen A…)**強制完整報告**,但標記為 **secondary / descriptive**,**不各自產生 pass/fail hypothesis**。
- **因此不需要 multiplicity correction** —— 這不是迴避多重檢定,而是**事前消除「看一堆指標挑最好看的那個」**。
- **禁止**為 B0 硬湊一個 DSR `N`。DSR 可保留為 **audit diagnostic**,**不得**作為 L2 primary gate。
- **Trial registry 永久保存**(§4.3 的登記簿保留,但其角色從「校正輸入」改為「污染紀錄」)。
- 歷史研究污染的處置方式不是用一個假的 `N` 洗乾淨,而是:登記簿永存 + L2 永不稱 Validated + L2 成功證據強度降級 + primary validation 留給 L3。

> **一項必須寫明的澄清:** V-4 的三個條件以 **AND** 結合,在統計上是**單一複合假設(交集)**,**不是三次檢定**。AND 只會使通過更難(type-I error 更低),**不會**膨脹。因此 family size = 1 的主張成立,不得被日後解讀為「你做了三個檢定」。

### V-3 · L3 maturity(**凍結**)

```
Maturity = max( 36 完整 prospective monthly rebalances , 36 calendar months )
```

雙重寫死是為了防止資料缺月時「36 observations ≠ 3 years」。

- **禁止提前畢業。** 即使第 8/18/24 個月看起來極佳,仍不得升 L3。**第一次正式 L3 判定 = Month 36。** 目的是消除 optional stopping。
- **36 不代表統計上足夠。** 它是**第一次允許正式 L3 maturity assessment 的最低期限**,不是「三年到了就叫 validated」。
- 36 個月後證據不足 → **`NOT YET VALIDATED`**(**不是 `FAIL`**,也不得改門檻),繼續累積。

> **🔴 新發現(需裁決,V-5):`NOT YET VALIDATED` 之後的下一個檢查點未定義,這會從後門把 optional stopping 放回來。** 若在 36 個月不足後改為「每月再看一次」,實質上就是未受控的序貫檢定 —— 而序貫檢定正是本裁決刻意排除的。**必須事前指定後續檢查點**(例如僅在 60、84 月各檢一次),或明文宣告後續檢查如何處置。**本輪不自行選定。**

### V-4 · L2 primary gate(**凍結**)

**`Supported` 定義為三條 AND:**

1. **net cumulative wealth > frozen primary market benchmark**(= 階梯第 ③ 列 **0050 買進持有**,於本文件事前凍結,開封後不得更換)
2. **net CAGR > 0**
3. **net Sharpe > 0**

**條件 2、3 不是 alpha 門檻**,只是排除荒謬情形(策略虧錢或風險調整報酬為負,卻因基準更慘而被稱為 Supported)。

**成本可比性規則:** B0 與基準必須採同一 calendar window、同一股息處理、同一起始資本慣例、同一 NAV 方法論。**但不得把 B0 的 trading impact 強行套給 buy-and-hold 基準** —— 成本依各自真實交易事件計算(0050 買進持有僅期初一次進場成本;等權母體有實際月頻換手,須以同一 `b0_cost_model` 計價)。

**明文排除:** 「勝過 Frozen A」**不進 gate**。Frozen A 是 historical benchmark / audit comparator,不是 B0 的勝負對手。因此:
- B0 夏普 < A,但 B0 > market、net positive、結構有效 → **仍可 `Supported`**,但報告必須誠實寫出未勝 A;
- B0 勝 A,但 B0 < market benchmark → **不得**因「贏舊系統」而算 Supported。

**通過三條仍只寫 `Supported`。永遠不得寫 `Validated` / `statistically proven` / `OOS edge confirmed`。**

> **🔴 新發現(需裁決,V-6):`net Sharpe > 0` 的無風險利率慣例未凍結。** Sharpe 以超額報酬計算時,rf 的選擇會改變判定。須指定(沿用既有 `honest_backtest` 慣例、或明文宣告 `rf = 0`、或指定外部利率序列)。**本輪不自行選定。**

---

## 7. 執行順序(使用者 2026-08-17 定案)

```
B-18 protocol 封 V1–V4          ← 本文件
  → B-19 runtime override integrity
  → B-20 production decision-path parity
  → B-21 provenance / reproducibility
  → L1 全綠(S-1..S-8)
  → 完整 Frozen B preregistration + commit / hash 封存
  → 才有資格開 L2 一次
```

**S-8 不是行政收尾。** 若 B0 結果出來後無法精確回答「哪個 code commit / 哪版資料 / 哪份 schema / 哪個 config / 哪個 feature reference artifact」,**「只開封一次」就沒有意義** —— 因為無法證明第二次跑的是同一個東西。

### 7.1 Prospective clock 的起點(凍結)

**不是「今天開始」。**

> **起點 = 完整 Frozen B0 preregistration + production route + provenance 全部封存後的第一個 eligible decision date。**

如此才能在數年後指著 commit 說:**該日之後的資料未參與 B0 的任何設計。**

---

## 8. 現況

```
B-18 protocol          : CLOSED(本文件)
B-18 L1 判準           : FROZEN(S-1..S-8)
B-18 L2 protocol       : FROZEN(報酬線/基準/日期/成本/schema/開封規則)
B-18 V-1a 現金股利      : FROZEN(receivable,可實作)
B-18 V-1b 股票股利      : BLOCKED(語料無此欄位,三條路徑待選)
B-18 V-2 multiplicity  : FROZEN(single primary hypothesis,無校正)
B-18 V-3 L3 maturity   : FROZEN(36/36,禁提前畢業)
B-18 V-4 L2 gate       : FROZEN(三條 AND,相對基準)
B-18 no-post-hoc rule  : FROZEN
新開放項                : V-5(36 月後的後續檢查點)、V-6(Sharpe 的 rf 慣例)
L2 開封資格            : BLOCKED —— S-8(B-21)未關閉、V-1b 未解決
```

---

**本輪未執行任何 B0 retrospective performance、未產生 Sharpe / CAGR / MDD / 選股名單 / 參數比較、未動 A0–A3。未 stage、未 commit。**
