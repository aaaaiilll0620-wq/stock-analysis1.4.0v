# M-3 · L3 前瞻決策的 span 推導 — 裁決選項書

**狀態：`ADJUDICATED — DOCUMENT ONLY；IMPLEMENTATION NOT AUTHORIZED`**
裁決於 2026-08-27 作成（見下方「裁決」節）。本文件之外未變更任何 code、master prereg、data；
未建立 run、未封存、未 stage、未 commit。四個原始選項全部保留，未刪除。
標的：`research/b0_l3/l3_assemble.py` 的 `UNREGISTERED_SPAN_DERIVATIONS = ("price_span", "bonus_window")`（:224）。
兩者目前是無預設的必填參數（:717、:734），因為凍結規格只為 L2 的 141 期面板定義它們，而兩條規則都錨在 `window_start` 上，單一前瞻決策沒有 `window_start`。

**全案底線約束（每個選項都必須自證）**
> 不得以沿用 L2 常數（price span `("2013-01-01","2026-04-01")`、bonus window `("2013-06-29","2026-03-31")`）作為未說明的預設。
> L2 的值只能有兩種合法角色：(a) 某選項的公式獨立導出後，**事後對照**用的 parity 檢查點；(b) 裁決文書**明文寫出繼承理由**的宣告值（選項 D）。任何「因為 L2 是這樣所以照抄」都不成立。

---

## 0. 先把裁決標的縮到最小：四個端點裡，只有一個是真正的自由度

| 端點 | 是否已有註冊推導 | 對 `market_state_sha256` 的影響 | 結論 |
|---|---|---|---|
| `price_span[1]`（TO） | **有**。§6.5 的執行 session = 第一個 `> as_of` 的 session；`assemble` 已強制 `exec_date <= price_span[1]`（:748） | **無**。狀態只讀 `≤ as_of` 的資料；`spell_start(as_of)`／`unresolved_at(as_of)` 都以 as_of 上界（:421–428） | 非裁決標的，照 §6.5 導出 |
| `bonus_window[1]`（TO） | 可導出：`≥ as_of` 即可 | **無（可證明）**。已解析事件若 boundary 晚於整個 reach，C-50/R3 對 reach 內每個價格同倍數相除 → momentum 的比值與 sigma20d 的對數差皆抵消（`adjusted_closes` :325–336）；未解析 boundary 由 `unresolved_at(as_of)` 以 as_of 過濾 | 非裁決標的 |
| `bonus_window[0]`（FROM） | 可導出，且**存在充分性平台** | **有條件為零**：只要 FROM ≤ reach 的最早價格，再深都不動 hash（理由同上，抵消／過濾） | 需明文裁決「規則」，但不同深度不改變結果 |
| **`price_span[0]`（FLOOR）** | **無** | **有，且是直接的**：它就是 `spell_start`（hash 內欄位），並經 `n_in_spell` 決定 ADV20／sigma20d 是否轉 NA（:580–597），以及 O-G 的月底價 blanking（:555） | **唯一真正的裁決標的** |

**reach（一個決策實際讀到的最早價格）** = min(
`MONTH_ENDS_REQUIRED = series_requirements()["month_end_prices"] = 14` 個月底（:103，zero-margin 且 `INTENTIONAL_ZERO_MARGIN` 明文宣告）,
`SIGMA_SESSIONS + 1 = 21` 個 close（:98）,
`ADV_SESSIONS = 20` 個 session（:97，讀 raw，不受 bonus 影響）
) ⇒ 約 as_of 往回 14 個日曆月。

⚠ 這張表本身也需要被裁決承認：把 TO 與 bonus FROM 判為「已註冊／可證明中性」，是本選項書的主張，不是既有的凍結條文。若裁決不接受抵消論證，則四個端點全部落回 M-3。

---

## 選項 A · `AS_OF_ROLLING_MINIMAL`
把 L2 的面板規則逐字保留，只把 `window_start` 換成本次決策的 as_of。

- **由 as_of 推導的精確公式**
  `floor = "%d-01-01" % (as_of − lookback_L_months).year`，`lookback_L_months = 18`（frozen spec）；
  `TO = 第一個 > as_of 的 session`。
  as_of `2026-03-30` → **`("2024-01-01", "2026-03-31")`**。
- **price / listing spell 語意**：`spell_start = max(真實首次觀測, 2024-01-02)`。地板逐月滾動（跨年時一次跳一整年），同一檔證券的 `spell_start` 會**每月往前移動**；`spell_starts_at_price_coverage_floor` 預期接近全體。O-G 的 `opened_by` 仍只能寫 `first_observation`（無第三值），語意落差最大。
- **bonus 調整基準**：`FROM = as_of 之月往回 13 個月的月底 session 之次日`（L2 原句的 as_of 版），`TO = as_of`。基準仍是 `SHARE_UNIT_ADJUSTED`（core/b0_share_unit_adjustment.py），不變。
- **資料補登是否改寫既有 run**：不會靜默改寫——manifest 已 pin 每個來源的 `raw_sha256`（`l3_snapshot.plan` / `source_ownership_manifest`），補登後重跑舊月份會 fail-loud。但**風險在可讀性**：地板本來就逐月漂移，補登造成的 `spell_start` 位移與地板漂移在外觀上無法區分。
- **hash 影響**：與 L2 sealed 2026-03 的 `3a95d77e…` **不同**（1,437 檔的 `spell_start` 由 `2013-01-02` 變 `2024-01-02`）→ **主動放棄目前唯一可用的 parity 錨**（2026-03 是結構上唯一能對照的期，見 valuation 的 `board_date_payload_key`）。
- **首次 L3 與後續月份如何延伸**：每月獨立計算，floor 與 TO 都隨 as_of 移動。
- **fail-loud 條件**：floor > reach 最早所需價格 → 中止；`exec_date > price_span[1]` → 中止（既有）；`n_in_spell < 20`／月底價不足 → NA（既有，非中止）。
- **L2 常數**：完全不使用；由 as_of + 凍結的 `lookback_L_months` 導出。

---

## 選項 B · `LINEAGE_INCEPTION_ANCHORED`
L2 規則逐字保留，`window_start := 本 L3 lineage 的首次決策月`，封存後不再變。

- **公式**：`floor = "%d-01-01" % (inception_month_end − 18mo).year`；`TO = 第一個 > as_of 的 session`。
  inception `2026-03`、as_of `2026-03-30` → **`("2024-01-01", "2026-03-31")`**；2026-04 的 run 仍是 `2024-01-01`。
- **spell 語意**：地板固定 → **跨月完全穩定，不漂移**；但首次 run 的 corpus-edge 比例與 A 相同（同樣淺）。
- **bonus 基準**：`FROM` 依 inception 同法固定（inception 的 P_{t-13} 月底次日），`TO = as_of`；因充分性平台，與 A 的 hash 相同。
- **補登**：manifest 保護同 A；且因 floor 固定，**跨月的 hash 差異只可能來自資料本身**——補登的可見度是四個選項裡最高的。
- **hash 影響**：首次 run 與 A 相同，**不等於** L2 sealed 值；同樣失去 parity 錨。
- **延伸**：`inception` 成為 lineage 常數，寫入 manifest 並隨 receipt 封存；之後每月只延伸 TO。
- **fail-loud**：manifest 的 `inception` 與 receipt 不符 → 中止；不同 lineage 重用同一 inception → 中止；其餘同 A。
- **L2 常數**：不使用。但這是**規則沿用（rule reuse）而非常數沿用**——裁決文書必須明文承認「L2 的面板規則可重新繫結到 L3 的 inception」，否則它仍是 specification-by-code。

---

## 選項 C · `CORPUS_COVERAGE_FLOOR`
地板不由日期算式導出，而由**已宣告來源的實際覆蓋**導出。

- **公式**：`floor = price_coverage_floor(px)`（:227，= 已宣告 price 來源實際最早的 session，資料的函數）；`TO = 第一個 > as_of 的 session`。與 as_of 的關係僅在 TO；FLOOR 對 as_of 不變。
- **spell 語意**：**唯一讓 `spell_start` 逼近「真實上市／reappearance」的選項**；corpus-edge 比例最小，且只要來源集合不變就跨月穩定。最貼近 O-G 對 `opened_by` 的原意。
- **bonus 基準**：`FROM` 取 bonus 來源的覆蓋下限（或 exactly-sufficient——因中性平台兩者 hash 相同，差別只在 manifest 面積與讀取成本）。
- **補登**：**風險最高、但也最需要一併裁決**。地板是資料的函數，補一筆更早的價格會移動地板。舊 run 仍受 manifest sha 保護（重跑 → fail-loud），但**新月份會用新的地板**，於是同一 lineage 內不同月份的 `spell_start` 語意不一致。⇒ 本選項必須附帶一條規則：**「覆蓋下限變動是否開新 lineage 版本」**。
- **hash 影響**：~~可能重現 L2 sealed 2026-03 的 `3a95d77e…`——若且唯若兩條 price legs 合併後的覆蓋下限恰為 `2013-01-01`。~~
  **已由 M1 否證（2026-08-27）**：覆蓋下限是 `2004-01-02`，選取列數相差 3,140,015（row-set 不等價），故 **C 不繼承 L2 的 sealed hash**。此選項仍被採用（見「裁決 — C-LF」），理由是狀態語意，不是 parity。
- **延伸**：每月由資料重新導出，正常情況不變。
- **fail-loud**：覆蓋下限 > reach 需求 → 中止；只宣告 2019+ leg（曾使 1,706/1,958 檔的 spell start 變成 `2019-01-02`）→ `assert_both_price_legs_are_declared`（:234）已在；`px` 為空 → `AssemblyError`（:230）。
- **L2 常數**：不使用；與 L2 相同只能作為量測結果報告。

---

## 選項 D · `DECLARED_LINEAGE_CONSTANT`
不推導。span 是 lineage 層級的**宣告值**，寫入 manifest、隨 receipt 封存、可被審查。

- **公式**：無 as_of 公式（FLOOR 對 as_of 為常數）；`TO` 仍由 §6.5 導出。
- **理據**：M-3 的正解本來就是「補一條規格」，而不是讓 code 挑值。若裁決認為**任何**算式都無法為前瞻決策證成，就把它降格為一個被明文記錄的常數，並讓 `assemble` 維持現在的拒絕預設行為。
- **spell 語意**：`spell_start` 的語意明確定義為「本 lineage 宣告的語料深度」；`SPELL_FLOOR_SEMANTICS`（:195）已有欄位可報告落在地板上的檔數。
- **bonus 基準**：同法宣告，並要求宣告值 ≤ reach 最早價格。
- **補登**：**完全不改寫既有 run**（宣告值與資料無關）——不可改寫性最強。代價是補登不會反映在地板上，語料深度與實際覆蓋可能脫節（需在 receipt 中同時記錄 `price_coverage_floor` 供對照）。
- **hash 影響**：由宣告值決定。若宣告值取 L2 的兩個 span，2026-03 會重現 sealed hash——**這正是「以 L2 常數為預設」的形狀，只有在裁決文書寫明繼承理由（例如：本 lineage 明示繼承 L2 的語料深度以維持與 L2 的可比性）時才允許**；不得以「反正對得上」為由採用。
- **延伸**：後續月份沿用同一宣告；變更宣告值 = 新 lineage 版本。
- **fail-loud**：manifest 未宣告 → 現況即中止（required args）；宣告值與 receipt 不符 → 中止；宣告值不足以覆蓋 reach → 中止。

---

## 交叉比較

| 維度 | A 滾動最小 | B inception 錨定 | C 覆蓋下限 | D 宣告常數 |
|---|---|---|---|---|
| 2026-03 是否重現 L2 `3a95d77e…` | 否 | 否 | **可能（待 M1）** | 取決於宣告值 |
| spell 語意貼近真實上市 | 最差 | 最差 | **最佳** | 由宣告決定 |
| 跨月穩定性 | 差（逐月漂移） | **佳** | 佳（除非來源變動） | **最佳** |
| 補登改寫既有 run | 否（manifest 保護） | 否 | 否，但新月份地板會變 | **完全免疫** |
| 補登可見度 | 低 | **高** | 中 | 低（需另記 coverage floor） |
| 需附帶裁決條款 | 無 | 「規則可重新繫結」 | 「地板變動＝新 lineage？」 | 「繼承理由」明文 |
| 讀取／manifest 面積 | 最小 | 最小 | 最大 | 由宣告決定 |

---

## 尚待量測（撰稿時列出；**M1–M3 已於 2026-08-27 完成，結果見下方 Evidence appendix**）

- **M1** 兩條 price legs（`~/tej_cache/price_valuation` 前 2019 leg + 2019+ 兩個 archive，且 D-1 quarantine 於讀取時生效）合併後的**實際覆蓋下限**。決定選項 C 是否重現 L2 hash。
- **M2** 各選項下 `spell_starts_at_price_coverage_floor` 的實際檔數（A/B 預期接近 1,958/1,958）。
- **M3** A/B 的淺地板下，因 `n_in_spell < 20` 而使 ADV20／sigma20d 轉 NA 的**新增**檔數——這會經 §4.2 影響可投資宇宙，且 §4.2 對**缺失**的 adv20 是中止而非拒絕（B0.5 的教訓）。

---

## 一句話意見（2026-08-27 量測前的事前意見，**已被下方裁決取代**，保留備查）

~~若 M1 落在 `2013-01-01`，**選項 C** 同時取得最強的 spell 語意與一個真正的 parity 錨；若 M1 使 C 的地板與 L2 不同，則 **選項 B** 是次佳。~~
此意見的前提（C 的地板可能等於 L2 的 `2013-01-01`）已被 M1 否證（floor = `2004-01-02`），其「否則選 B」的退路亦被 M2/M3 否證（B 的 corpus edge 升至 96.6%，且 M3 量不到任何補償利益）。

---

# 裁決 — `C-LF`（2026-08-27）

## `INCEPTION_CAPTURED_CORPUS_COVERAGE_FLOOR`（即「C ＋ lineage 凍結」）

1. **首次導出**：首個 L3 lineage 透過**完整、hash-bound 的價格 leaf**，在 D-1 quarantine 之後導出最早 admissible session。
2. **凍結**：該結果寫成 `lineage_price_floor`，於同一 lineage 內**永久固定**，不再逐月推導。
3. **每期另記 `observed_price_coverage_floor`**，並依三種關係處置：
   - **晚於** `lineage_price_floor` → 缺少必要歷史，**abort**。
   - **等於** → 正常。
   - **早於** → 同 lineage 仍截在既有 floor；若要採用新增歷史，**必須開新 lineage version**（既有 lineage 不得漂移）。
4. **`2004-01-02` 目前只是 diagnostic expected value。** 首次經 L3 manifests 驗證若不是此值，**停止封存並回報**，不得靜默採用。
5. **另外三個端點接受既有推導**（見第 0 節的論證）：
   - `price_span[1] = execution_date`
   - `bonus_window[1] = as_of`
   - `bonus_window[0] = 最早必要月末價格的次日`

## 選項處置

| 選項 | 處置 | 理由 |
|---|---|---|
| A `AS_OF_ROLLING_MINIMAL` | **拒絕** | spell 地板會逐月漂移 |
| B `LINEAGE_INCEPTION_ANCHORED` | **拒絕** | corpus edge 升至 96.6%，且 M3 未量出任何補償利益 |
| C `CORPUS_COVERAGE_FLOOR` | **以 C-LF 形式採用** | 見上 |
| D `DECLARED_LINEAGE_CONSTANT` | **不採用** | 已有可證成的推導規則，無須任意宣告常數 |

## 裁決理由中必須留存的一句

**M3 的零增量不表示 span 不重要。** 三個地板在本期產出相同的決策特徵（adv20／sigma20d／月底價的 NA 與 blanking 增量皆為 0），但 `spell_start` 本身仍進入 state hash。C-LF 選的是**較忠於來源歷史的狀態語意**，而不是一個對決策無影響的自由參數。

## 本裁決**未**授權的事項

改 code、改 master prereg、建立 run、封存、stage、commit。實作授權須另行取得。

## 登錄層級裁決（2026-08-27，後續裁決）

| 欄位 | 值 |
|---|---|
| `registration_layer` | **`SPEC`**（不是 route 層） |
| 預定 Master 版本 | **`v1.34`**（不回收被否決的 v1.33） |
| closure 編號 | **`C-68`**（不使用 C-67） |
| 正式章節 | **`§19`** |
| `master_registration_status` | **`PENDING_IMPLEMENTATION_AUTHORIZATION`** |

**理由**：C-LF 不是某次 run 的一般輸入，而是所有 L3 lineage 如何決定 `price_span[0]` 的規則，且會改變 `spell_start` 與 state hash。若只放在 route／receipt，未來修改它可能不觸發 Master 版本變更，等於讓決策語意藏在實作裡。`l3_assemble`／`l3_snapshot` 是 **enforcement**，不是語意權威來源。

**編號說明（唯讀查證，2026-08-27）**：Master 現行為 v1.32（Frozen B0.7 / C-66），最後一節為 §18。被否決並完整回滾的 window 141→145 延伸草案佔用了 **v1.33 與 C-67**（`docs/REJECTED_v1.33_window_forward_extension.md`），版本號與 closure 編號一併保留作為 rejected history，故跳至 v1.34 / C-68。該草案的 §19 只存在於否決文件內、從未併入 Master，因此 Master 的 §19 仍是文件內的下一節，不留章節缺號。

**凍結邊界**：
- L2 的既有 spans、sealed hashes 與歷史 run **完全不變**；C-LF 只約束 L3 prospective route。
- 正式註冊的是 **C-LF 推導規則**，不是把 `2004-01-02` 寫成永久常數。
- `2004-01-02` 仍只是 diagnostic expected value；經完整 hash-bound price leaf 驗證後，實際結果才成為該 lineage 的 `lineage_price_floor`。
- 同 lineage 不得改變 floor；採用更早歷史需開新 lineage version。**若改的是推導規則本身，才需要再次升 Master 版本。**
- 每期 receipt 同時綁定 frozen `lineage_price_floor` 與本期 `observed_price_coverage_floor`。

## 落地順序（完整 closure transaction，**尚未授權**）

1. Master 升為 v1.34，新增 §19／C-68。
2. 新增 C-LF normative producer 與 machine-readable declarations。
3. `l3_assemble`／`l3_snapshot` 落實 enforcement 與測試。
4. 確認沒有 unrelated bound artefact drift。
5. **最後**才重新產生 `research/b0_registry/master_prereg_freeze.json`。

⚠ **不得先改 Master 再單獨執行 freeze script。** `freeze_master_prereg.py` 不只是更新 pin：它會一併重新綁定 normative modules、derived artefacts、upstream ZIP、specified keys、open/finalization registers 與 declaration conformance，並直接標記 `NORMATIVE_FROZEN`（`research/b0_registry/freeze_master_prereg.py:96`）。在 normative producer、machine declaration 與 enforcement 落地之前產生 freeze record，會得到「文件已凍結、機械規格尚未包含新規則」的中間狀態，步驟 2 完成後還得覆寫一次。

⛔ **在上述 closure 完成之前，不得執行首次 L3 strategy route。**

## 本次文件更新的性質

本節僅為**文件記錄**。**Master preregistration、`master_prereg_freeze.json`、`core/`、`l3_assemble`／`l3_snapshot` 及任何 leaf／manifest 均未改動**，未建立 run、未封存、未 stage、未 commit。
**這次更新不是、也不得被描述為 Master freeze。**

---

# Evidence appendix · M1–M3

⚠ **M1–M3 全部為 `DIAGNOSTIC EVIDENCE`，非 `SEAL-READY EVIDENCE`。**
價格側未經 `read_prices` 的 `_verified_path`／manifest sha 驗證（那需要 run_dir，等於建 run），
而是 import readers 自身常數後複製其語意；calendar 與 status 取自 L2 的 `data/b0/`
（`trading_calendar.csv` 5,565 sessions、`security_status.csv` 1,375 rows），未經 L3 leaf 的 hash 驗證。
升級為 seal-ready 必須經由已宣告、hash-bound 的 source manifest 重跑——這正是裁決第 1、4 點的內容。
量測皆為唯讀：未組裝完整 state、未計 state hash、未建立 run、未計算績效。

## M1 · 覆蓋下限與 row-set equivalence（2026-08-27）

| 量測 | 值 |
|---|---|
| leg 1（pre-2019 cache）原始跨度 | `2004-01-02 .. 2026-07-14` |
| leg 1，D-1 quarantine 後 | `2004-01-02 .. 2018-12-28`，5,660,136 rows；丟棄 ≥`2019-01-01` **3,349,771** rows |
| leg 1 檔案 | 2,300 枚舉，2,064 具可採用 rows（236 枚全屬被隔離的 2019+ era） |
| leg 2（兩個 2019+ archives） | `2019-01-02 .. 2026-08-17`，3,470,627 rows；dated <`2019-01-01` = 0 |
| **合併 post-quarantine 最早 session** | **`2004-01-02`** |

選取比較（同一上界 `2026-03-31`）：

| 選取 | count | key-set digest | content digest |
|---|---|---|---|
| `[2004-01-02 .. 2026-03-31]` | 8,946,869 | `e502bce1…6195492f` | `c95220f9…8678e50e` |
| `[2013-01-01 .. 2026-03-31]` | 5,806,854 | `3cae160f…a16cc201` | `445a57a6…915d8524` |
| 差 | **3,140,015 rows（35%）** | 不同 | 不同 |

⇒ **row-set equivalence 為 FALSE**（判準是 row set，不是日期字串）。故 C 的地板**不可能**繼承 L2 sealed 2026-03 的 `market_state_sha256`；「C 恰好等於 2013-01-01 因而免費取得 parity 錨」的前提不成立。
digest 定義：multiset digest（每列 sha256 取 mod 2²⁵⁶ 相加，與順序無關），key = `stock_id|date`，content = `stock_id|date|repr(open)|repr(close)|repr(volume_shares)`。

## M2 · 三個地板下的 active spell start（as_of `2026-03-30`）

以 `l3_assemble` 的 `spell_starts` / `status_index` / `known_status_at` 原件計算，`expected` 依 `build_series` 取 `cal[first..last]`，gap 是否 explained 依 O-E-1 查該 gap **首個缺失 session** 的 known status；active spell = `bisect_right(spells, as_of) - 1`。**未**以「每檔歷史最早價格」代替。

| 地板 | 實際 coverage floor | 於 as_of 有報價 | `spell_start ≤ floor`（corpus edge） |
|---|---|---|---|
| C `2004-01-02` | `2004-01-02` | 1,958 | **984（50.3%）** |
| L2 `2013-01-01` | `2013-01-02` | 1,958 | **1,437（73.4%）** |
| B `2024-01-01` | `2024-01-02` | 1,958 | **1,891（96.6%）** |

族群不隨地板改變：三者都是同一批 1,958 檔，沒有 only-in-X。L2 地板重現 sealed 2026-03 狀態的 1,437/1,958，是本複製的保真度檢核。

兩兩變動：C vs L2 **1,442（73.6%）**；C vs B **1,890（96.5%）**；L2 vs B **1,890（96.5%）**。

spell_start 年份分組：
- **C**：2004:1089, 2005:25, 2006:34, 2007:44, 2008:29, 2009:41, 2010:66, 2011:59, 2012:55, 2013:41, 2014:56, 2015:43, 2016:46, 2017:40, 2018:41, 2019:29, 2020:31, 2021:43, 2022:34, 2023:44, 2024:48, 2025:19, 2026:1
- **L2**：2013:1479, 2014:57, 2015:43, 2016:46, 2017:40, 2018:41, 2019:29, 2020:32, 2021:44, 2022:35, 2023:44, 2024:48, 2025:19, 2026:1
- **B**：2024:1938, 2025:19, 2026:1

### corpus-edge transition matrix（n=1,958）

**L2 → C**

| | → edge | → real |
|---|---|---|
| **edge →** | 981（日期全部改變） | **456** |
| **real →** | **3** | 518（其中 2 檔日期改變） |

**⚠ 更正**：本文件早期口述的「974 檔由 edge 轉為真實日期」為誤。正確數字為
**edge→real 456、real→edge 3、淨改善 453**（＝ 1,437 − 984）。淨值不可由兩個總數直接推出，須以此矩陣為準。
那 3 檔 real→edge 是**分類效果**（在 C 之下其首次觀測正好落在語料地板而被歸為 edge），非語意退步。

**L2 → B**

| | → edge | → real |
|---|---|---|
| **edge →** | 1,437（日期全部改變） | 0 |
| **real →** | **454**（其中 453 檔日期改變） | 67（日期未變） |

**C → B**

| | → edge | → real |
|---|---|---|
| **edge →** | 984（日期全部改變） | 0 |
| **real →** | **907**（其中 906 檔日期改變） | 67 |

B 沒有任何 `edge→real`——相對 L2 是純粹的語意損失，沒有補償。這是選項 B 被拒絕的直接證據。

## M3 · 地板對 NA／blanking 的增量（as_of `2026-03-30`，月底視窗 `2025-02 .. 2026-03`）

| 地板 | n | adv20 NA（`n_in_spell < 20`） | sigma20d NA（`< 21`） | 月底價因 `date < spell_start` blank | 無觀測 cells |
|---|---|---|---|---|---|
| C `2004-01-02` | 1,958 | **0** | **0** | 證券 0 / cells 0 | 59 |
| L2 `2013-01-01` | 1,958 | **0** | **0** | 證券 0 / cells 0 | 59 |
| B `2024-01-01` | 1,958 | **0** | **0** | 證券 0 / cells 0 | 59 |

三個地板**兩兩增量全為 0**，受影響名單為空。

原因是結構性的，不是本期巧合：三個地板都在 as_of 前 20 個 session 以上，`n_in_spell` 只有在 active spell 本身開始於最近 20 個 session 內時才會不足——那是真實的新上市／reappearance，與地板無關。同理 14 個月底視窗起於 `2025-02`，只有 spell start 落在該視窗內才會被 O-G blank。59 個無觀測 cells 是最近一年內才有價的證券，三個地板完全相同。

**範圍外（未量測，須另案）**：`not isfinite(adv)`（成交量缺失造成，不隨地板變動）；C-50/R8 未解析 boundary 造成的 NA（需 bonus panel，本次未讀取）。
