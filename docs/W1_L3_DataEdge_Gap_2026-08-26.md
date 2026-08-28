# W1 · L3 資料邊界盤點與 `data/b0/` 寫入裁決點（2026-08-26）

**本次未寫入 `data/b0/` 任何一個位元組。** 交易日曆延伸已做**乾跑**（輸出只落在 scratchpad），
價格／月營收／估值三項已量測上游可得性，兩族來源的重疊區已逐位元對帳（§6）。

> ## 裁決（使用者，2026-08-26）
>
> **R-W1-1 · `data/b0/` 就地凍結，L3 走 run 目錄。**
> 141 期 / 2026-03-31 的 sealed 狀態不動；L3 每期資料改由 W6 的 L3 materializer +
> W7 的 run-scoped layout 產出不可變快照。
> **⇒ W1 的 `data/b0/` 獨占寫入權不予行使**，本工作改為替 L3 供給來源側的事實與契約。
>
> **R-W1-2 · 兩族並存，TEJ 為權威。** live FinMind 供即時，TEJ 供權威與對帳。
> 衝突解析規則與 receipt 如何同時綁兩族來源，形狀對齊 A3 的 `SOURCE_OWNERSHIP`（W5）。

---

## 1 · 現況：canonical 與現行 seal 逐位元相符

```
seal            c973cff3dfae7003…   lineage seq 19 CURRENT，master v1.32，commit 271b1106
derived data    20 / 20 逐位元相符   （含 bonus_share_panel.parquet：mtime 是今天，內容未變）
normative code  31 中漂移 1          core/b0_corporate_actions.py（見 W3-C2，語義中性）
spec document   相符
```

**這是一個乾淨的可封狀態。** 任何對 `data/b0/` 的寫入都會讓 20/20 變成 19/20 以下，
而且 `data/b0/` 是 gitignored、無 git 還原路徑（備份：`/mnt/c/dev/b0_sealed_backup_v1.32_20260826`）。

---

## 2 · 四項資料的邊界（實測）

### 2.1 現行 canonical 面板的邊界

```
trading_calendar.csv        5,565 sessions   2004-01-02 .. 2026-08-17
security_status.csv         1,375 rows       .. 2026-08-14
price_panel.parquet         5,808,812 rows   2013-01-02 .. 2026-04-01
financials_pit.parquet      136,372 rows     release_date .. 2026-03-31
monthly_revenue_pit.parquet 301,801 rows     release_date .. 2026-03-16（資料月 .. 2026-02）
valuation_panel.parquet     241,687 rows     decision_month 2014-07 .. 2026-03（141 期）
industry_pit.parquet        4,782 rows       effective_from .. 2026-06-17
```

決策相關的四張面板都切在凍結窗口（2026-03-31）；日曆與 status 是來源側，走得比較前面。

### 2.2 L3 Month 1 需要什麼

```
decision_month   2026-08
decision_date    2026-08-31（月底）
as_of            §6.6：嚴格早於 decision_date 的最後一個 session  → 2026-08-28（預期）
execution        decision_date 之後的第一個 session               → 2026-09-01（預期）
```

→ **as_of 尚未發生（今天 2026-08-26）。L3 Month 1 現在本來就跑不了，只能先把管線備妥。**

### 2.3 逐項缺口

| 項目 | 上游現況 | 對 L3 M1 是否夠 | 缺什麼 |
|---|---|---|---|
| 交易日曆 | `~/market_cache/taiex_daily.parquet` 已到 **2026-08-26**（今天 18:02 更新） | ❌ 差 2026-08-28 / 09-01 | 只差時間，來源已自動更新 |
| 價格 | TEJ `股價2023-20260817.zip` 止於 **2026-08-17**；`~/market_cache/price_valuation_daily/` 每日檔已到 2026-08-26（僅 32 個滾動日檔） | ❌ | 新的 TEJ 匯出（只有使用者能做），或裁決改用 live 來源 |
| 月營收 | TEJ `月營收2004-202608/20260806091706.xlsx`，匯出日 **2026-08-06** → 不含 7 月營收（約 8/10 公告）；`~/market_cache/monthly_revenue/2026-07.parquet` 有 | ❌ | 同上 |
| 估值 PBR/PER | `harvest_official_pbr.py` 直接向 TWSE/TPEx 取，任一 session 皆可取 | ⚠️ 可取但被日曆擋住 | 先延日曆（該腳本讀 `data/b0/trading_calendar.csv` 決定 session） |
| 財報 | `財報2004~202606/2026 0826 2385家.csv`（UTF-16LE / TAB，發布日 .. 2026-08-25） | ✅ 資料在 | 讀不到 —— builder 只 glob `*.xlsx`（O-H），**W5/B3 的工作** |

### 2.4 交易日曆延伸 —— 乾跑結果（未寫入）

依 `research/p1a_o_e_market_state/build_market_state.py:93 build_calendar()` 的同一規則重算：

```
canonical  5,565 sessions   .. 2026-08-17   sha256 5859cf08835c7e70…
乾跑重算   5,572 sessions   .. 2026-08-26   sha256 375540d9ca448c80…
新增 7 個  2026-08-18 / 19 / 20 / 21 / 24 / 25 / 26
移除       0
前 5,565 個 session 逐項相同（純 suffix）
乾跑檔     只寫到 scratchpad，未進 repo
```

→ 延伸本身是**純 suffix、零風險**，但它會改掉 `trading_calendar.csv` 的 sha256，
連帶改掉 seal 的 `b0_trading_calendar` dataset（`date_max` 2026-08-17 → 2026-08-26）與
`sealed_input_sha256`。

---

## 3 · 裁決前的兩個問題（已裁，原文保留為裁決依據）

### 3.1 M-3 · L3 的來源家族未定義

`core/b0_adapter_production.py` 只定義 `ProductionSources` 的**形狀**，
不定義**誰去填**。B6（L3 runner）才組裝它。目前規格沒有任何一句話說：

1. L3 的價格／月營收走哪一族？
   - **A：續用 TEJ 匯出** —— 與 L2 同族、可對帳，但每個月要使用者手動匯出一次，
     且 L3 Month 1 現在就缺（最新匯出止於 08-17／08-06）。
   - **B：改用 live FinMind 快取**（`~/market_cache/*_daily/`，今天已到 2026-08-26）——
     自動、無人工，但**換來源**。O-E 已經裁過「只知道最新狀態的來源是 `NOT_PIT_SAFE`」，
     而那些 daily 目錄只有 29~32 個滾動日檔、沒有歷史；要當 PIT 來源必須改成
     **逐日累積、永不覆寫**，並宣告 availability convention。
   - **C：兩者並存**（TEJ 為權威、live 為即時），則要先定「誰在衝突時勝出」。
2. L3 的面板落在哪裡？**`data/b0/`（就地更新）還是 W7 的 L3 run-scoped layout（每期不可變快照）？**
   後者才與 A2「完整可重播」和 B4「每期不可變 receipt」一致。
   若是後者，**`data/b0/` 應維持凍結，W1 的獨占寫入權其實不該被行使。**

依 §1.5 M-3，這三題我不得取預設值。

### 3.2 順序 · 資料變更要在 B13 之前，不是之後

REJECTED v1.33 對 §19.10 的更正已經立了原則：
「會改變 HEAD 的排程工作，應在最終狀態檢查與 commit **之前**暫停，而非之後。」
同一邏輯適用於資料：**若 `data/b0/` 終究要被更新，就必須在 B13 取新 seal 之前更新完，
否則新 seal 當天就過期。** 現在動、或 B13 前動，是可以的；B13 之後動是最糟的順序。

---

## 4 · 裁決之後 W1 剩下什麼

`data/b0/` 不動 ⇒ §2.4 的日曆乾跑**不落地**，保留為量測記錄。
W1 的產出改為三件，全部要等 A3 的 `SOURCE_OWNERSHIP` 形狀定案才實作：

```
W1-a  L3 來源 adapter：把 TEJ（權威）與 live FinMind（即時）餵成 ProductionSources
      —— 與 W6/W7 合流，不得自行決定面板落點
W1-b  live 家族的 PIT 累積器：~/market_cache/*_daily 目前只有 29~32 個滾動日檔，
      要當 PIT 來源必須改成逐日累積、永不覆寫，並宣告 availability convention
      （O-E 已裁「只知道最新狀態的來源 NOT_PIT_SAFE」）
W1-c  兩族衝突解析規則：依 §6 的實測結果起草，TEJ 勝出的邊界要寫死而不是預設
```

**仍然缺、且只有使用者能補的：** 一份止於最新交易日的 TEJ 股價匯出，
與一份含 2026-07 的月營收匯出。沒有這兩份，L3 Month 1 的**權威**腿是空的
（即時腿有，但依 R-W1-2 它不是權威）。

---

## 5 · 順手量到的（W4/B10 的材料，未實作）

六支 builder 全部以 glob 列舉來源，任何不符 pattern 的檔案都被**靜默**忽略：

```
build_monthly_revenue_pit.py:70   CORPUS/*.xlsx     ← 與 O-H 同型；該目錄目前只有 1 個 xlsx
build_price_panel.py:159          OLD_CACHE/*.parquet
build_price_panel.py:195          ZIP_DIR/*.zip     ← 同目錄還有 24 個 .xlsx（刻意排除）
                                                      但新丟一個 .zip 會被**靜默納入**
build_bonus_share_panel.py:81     RAW/<pattern>
build_market_state.py:117         SUSP_DIR/暫停交易*.zip
ingest_status_export.py:103       SRC_DIR/<pattern>
```

`build_price_panel.py:195` 的方向比 O-H 更危險：O-H 是「該讀的沒讀到」，
這裡是「不該讀的會被讀進去」，而且一樣不會抱怨。
A3 的 `SOURCE_OWNERSHIP` 宣告形狀定案後，這六處都要照抄。

---

## 6 · 兩族來源重疊區的逐位元對帳（R-W1-2 的實證基礎）

重疊區 = TEJ `股價2023-20260817.zip` ∩ `~/market_cache/price_valuation_daily/`
= **2026-07-14 .. 2026-08-17，25 個 session**。

```
共同 (stock_id, date) 列            48,079
收盤價不一致                          1     最大差 37.0（2026-07-14，單一標的）
開盤價不一致                          1     最大差 37.0（同上）
成交量不一致                     47,047     最大差 999 股      ← 97.9%
只在 TEJ                            781     每 session 22 ~ 47
只在 FinMind                        722     每 session 27 ~ 31
```

### 6.1 價格：兩族實質相同，但那唯一 1 列是 sentinel zero

48,079 列中只有 1 列收盤價不同，且開盤價的那 1 列是同一列：

```
2026-07-14   5906 台南-KY    TEJ  open 37.0  close 37.0
                             FinMind  open 0.0   close 0.0
```

FinMind 用 **0.0 當「當日未成交」的哨兵值**，TEJ 則帶最後有效價。
全 32 個日檔 62,445 列中 `close == 0` 只有這 1 列 —— 罕見，但它是最貴的那一類：
**一個被持有的部位若以 0 標價，NAV 會靜默歸零而不報錯。**
本專案已經對估值比率裁過同型問題（spec key `valuation_sentinel_zero_is_undefined`），
價格腿必須比照：**live 家族的 0 價要當 undefined 處理並 fail loud，不得當價格用。**

→ 除去這一列，價格值本身不是衝突軸。

### 6.2 成交量：97.9% 不一致，但那是單位精度不是衝突

TEJ 發布 `成交量(千股)`，`build_price_panel.py` 乘 1,000 還原，
所以 TEJ 的股數**恆為 1,000 的倍數**；FinMind 給實際股數。
差額恆 < 1,000 股 —— 是**捨入**，不是兩個來源對同一件事有不同說法。

⚠ **但它不是無害的**：C-25 把 adv20 釘在 `dollar_vol = close × Trading_Volume`，
而 adv20 直接餵 §4.2 的 ADV floor（絕對 NTD 門檻）。
每列最多 999 股的捨入，在 100 元的標的上就是每日約 10 萬元的 adv 誤差。
**若 L3 的即時腿用 FinMind 的股數、回測腿用 TEJ 的千股，同一檔在門檻邊緣會兩邊判不同。**
→ R-W1-2 的「TEJ 為權威」必須明文涵蓋**單位與精度**，不只涵蓋值。

### 6.3 母體：這才是真正的衝突軸

以 2026-08-17 為例：

```
只在 TEJ（26 檔）    6 檔 DR（911622 / 910322 / 910861 / 911608 / 911868 / 912000）
                     20 檔一般 4 碼（永冠-KY、瑞儀、振宇五金、偉康科技 …）
                     推定：當日無成交的標的 FinMind 不出列，TEJ 仍帶價
只在 FinMind（31 檔） 全部 4 碼，集中在 6xxx / 7xxx（6534 6645 6771 6908 …
                     7610 7631 7730 7740 7803 7823 7827 7835 7855 …）
                     推定：TEJ 匯出範圍或 vintage 落後於新上市／興櫃
```

**依 R-W1-2「TEJ 為權威」，每個 session 會有約 30 檔 FinMind 看得到、TEJ 沒有的標的被排除。**
這正是研究紀律 §1 講的「母體有沒有被靜默砍過」——
所以它必須是**被宣告的排除**，不是 join 的副作用：
L3 的 receipt 要記錄每期 `only_live` 與 `only_authoritative` 的清單與筆數，
差異超過宣告門檻時 fail loud。

（本節全部為唯讀量測，未寫入 `data/b0/`，未產生任何 portfolio / NAV / 績效量。）
