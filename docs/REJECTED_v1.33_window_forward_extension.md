# 草案 v1.33 —— Window Forward Extension

# ⛔ 已否決 · `REJECT_AS_DRAFTED`（人審裁示 2026-08-26）

> **本文不得併入 `docs/FrozenB0_MasterPreregistration.md`。**
> 保留為否決紀錄與量測紀錄，**不具規範效力**。
> 權威來源自始至終是該文件現行的 §2.1：**141 個月 / 2026-03-31**。
>
> **程式已於 2026-08-26 回滾**至 141 / 2026-03-31，矛盾已消除。
> 回滾後查驗：`window_months = 141`、`window_end = 2026-03-31`、
> 141 期 composed 回到 `0b68f44e38716cf5…`、
> `spec_document_sha256` 與 B0.7 seal 相符、
> 31 個 normative module 對 B0.7 seal 的漂移由 2 降回 **1**
> （僅餘先前即存在的 `core/b0_corporate_actions.py`，見 §19.10 更正）。
> 測試 2473 passed / 3 skipped / 0 failed。

---

## 否決理由（裁示原文要旨）

### 1 · 支點前提被機械證偽

草案 §19.4 R2-5 以「決定延長的當下全 lineage 績效盲」為准入支點。
**該前提為假。** §9.6a-R2 條件 2 的界線比 `performance_computed` 嚴格得多：

> no strategy-dependent portfolio, NAV, return, performance metric,
> benchmark comparison, or other strategy-outcome information was
> **produced or viewed**

B0.7 的不可變紀錄
`artifacts/b0_7_diagnostic/runs/B07DIAG-fb6b6b54381ec4f9/period_progress.jsonl`
66 列全部帶有**非空持倉**與**變動 NAV**：

```
seq  1  2014-07  port_value 2000000.0            positions 20
seq  2  2014-08  port_value 2034205.681303583    positions 23
seq  3  2014-09  port_value 1995353.0315846663   positions 22
seq 66  2019-12  port_value 2208939.4237023285   positions 21
```

`performance_computed = false` 僅表示未計算彙總 CAGR／Sharpe，
**不等於未產生績效資訊**。§9.6a-R2 自身的警語已預先封死此讀法：
「一次已經在非空母體上算出橫斷面分數的 run，**已經看過**這個窗口，
之後拋什麼例外都不改變這件事。」

### 2 · R1 不認可追溯套用

§2.1 已寫「解凍條件唯一」，**通常讀法涵蓋凍結窗口終點**；
M-3 不能被用來事後創造一個新類別以繞過它。

`FORWARD_EXTENSION` 作為**治理規則**本身可保留，但只能用於
**未來版本、在其第一次 strategy route 執行之前預先凍結**。
**不得追溯套用於本案。**

### 3 · R2-5 的永久失效原則保留，觸發條件改寫，且本案已觸發

永久失效原則正確，但觸發條件不得只看 `performance_computed`。
正確界線是 §9.6a-R2 條件 2：**produced or viewed**。
依此界線，本 lineage 早在 B0.7 即已觸發。

### 4 · §19.5 部分認可

**認可：** 不是 L3、禁止 OOS 字眼、L3 仍自 2026-08 起算。

**不認可：** 直接併入正式 L2。正式 L2 身分綁定原先**一次開封**的 141 期
sealed window；事後追加**不能回寫成同一份 canonical L2 evidence**。
這四個月最高只能標成：

```
RETROSPECTIVE_SUPPORTING_ONLY  /  L2-class ceiling
```

亦**不得**對外稱「完全等同 141 期」，只能稱**證據力不高於 L2**。
（草案原文「與既有 141 個月同屬 L2 class」措辭過寬，已在此更正。）

---

## 對草案內文的兩項事實更正（裁示）

### O-H · 措辭更正

「in-window 缺列 defect」的說法**不成立**（草案 §19.9 已自行更正，此處確認）。
保留為 **lineage-hygiene open item** 即可。
`*.xlsx` glob 靜默忽略 `.csv` 的問題，
應在**未來窗口越過該資料邊界之前** fail loud，而非在越過之後才發現。

### §19.10 · 「失效」為錯誤用語

content-addressed seal 對其 **bound commit** 而言**仍是不可變且有效的歷史證據**。
正確說法是：

```
✗ 舊 seal 已失效
✓ 目前 checkout 不再符合該 seal；
  該 seal 對新的 opening 不再適用／已 superseded
```

另：**會改變 HEAD 的排程工作，應在最終狀態檢查與 commit 之前暫停，
而非之後。** 草案 §19.10 的順序寫反了。

---

## 目前 disposition

```
v1.33 草案                    REJECT_AS_DRAFTED
程式中的 145 / 2026-07-31     已回滾（2026-08-26）
2026-04 ~ 07 artefact         另存為非 canonical retrospective diagnostic 範圍
                              /mnt/c/dev/b0_ext145_noncanonical_20260826/
commit / 排程 / seal          全部未執行
```

---
---

# 以下為原草案全文，保留作為否決紀錄與量測紀錄，不具規範效力

---

---

## §19 Frozen B0 —— Window Forward Extension（v1.33，規範性）

```
parent                                   Frozen B0.7（v1.32）
reason                                   window forward extension，使用者指示
                                         2026-08-26
kind                                     frozen-parameter amendment
                                         （不是 implementation repair，
                                           也不是 data repair）
strategy semantics changed               false
既有 141 期 state bytes changed          false
period-1 full-input hash changed         false
新證據產生                                none —— replay 仍終止於 67 期
official Frozen B0 L2 replay permitted   false
```

> **既有 141 期的 raw 證據永遠不變。** B0.7 run_id `B07DIAG-fb6b6b54381ec4f9`、
> terminal `DIAGNOSTIC_NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK`
> at seq 67、`performance_computed = false`、`gates_evaluated = false`
> —— 全部不可重寫。本節不追溯改寫任何既有 run 的 periods_required。

---

### §19.1 誠實命名：這不是修復

§9.6 允許的例外只有兩種：**implementation 缺陷修復**與**資料修復**，
且兩者都必須在不看績效的情況下獨立證明。

本變更**兩者皆非**。它是對一個凍結參數（`window_end`）的**修改**，
動機是「上游資料已經長到 2026-08，想把回測拉到完整的 7 月」。

把它包裝成「資料修復」會是不誠實的：沒有任何資料是錯的，
既有 141 期也沒有任何一期缺料。因此本節不主張例外，
而是走 §1.5 M-3 的正規路徑——**未定義的行為必須裁決，不得以開發者認為
合理的預設值 resolve**。

---

### §19.2 §2.1 的解凍條款未涵蓋本變更（M-3 裁決點）

§2.1 現行文字：

```
解凍條件唯一：發現「已保留 feature 的 PIT dependency > 18」。不得因績效修改。
```

該句治理「解凍」，但**文件從未定義「解凍」是否包含「向前追加期數」**。
兩種讀法都成立：

- **讀法 A：** `window_end` 是凍結參數，任何改動都需要那個唯一條件。
  → 本變更不被允許。
- **讀法 B：** 「解凍」指的是重新開封已觀測窗口以再分析；
  在尾端追加尚未進入任何分析的月份不是開封。
  → 本變更是另一類動作，需要自己的條款。

M-3 禁止我用偏好去選一個。以下為裁決。

#### R1（規範）· 區分「解凍」與「forward extension」

```
UNFREEZE（解凍）
    = 改動窗口起點、lookback，或既有任何一期的身分或內容
      —— 包含既有期的 decision_month / decision_date / as_of /
         execution_date，或既有期的 market_state 內容
    → 仍然只受 §2.1 的唯一條件約束，不因本節放寬

FORWARD_EXTENSION（向前延長）
    = 僅在窗口尾端追加 decision months，
      且既有每一期逐位元不變
    → 受 §19.4 的准入條件約束
```

理由：§2.1 那句話所防的是**用後見之明重寫已看過的窗口**。
向前追加尚未被任何期消費過的月份，不觸及該風險——
但它會引入另一個風險（見 §19.5、§19.6），所以不是無條件放行。

---

### §19.3 本次確實是 suffix —— 機械量測，非宣稱

R1 把「既有期逐位元不變」提升為准入條件，所以它必須被**量**，不能被**說**。
2026-08-26 實測：

```
既有 141 期中 state hash 改變者          0 / 141
前 141 期 composed market-state sha      0b68f44e38716cf5dc0ab29ac8dccb64
                                         5c203d748102ac27f33831186653e405
                                         （= B0.6 值，未動）
period-1 full-decision-input sha         7a9c8ad46adb2858ccbec44c7a3e111b
                                         8f7a91d852f1845cb1e3f4a33c6de55b
                                         （未動）
price_panel ≤ 2026-04-01 切片            逐位元相同（5,808,812 列）
financials_pit release_date ≤ 2026-03-31 逐位元相同（136,372 列）
既有 87 個 valuation route session        全部重現一致
既有 141 期的 as_of / decision_date /     全部未動
  execution_date / securities
```

追加的四期：

```
decision_month  as_of        execution_date  securities
2026-04         2026-04-29   2026-05-04      1958
2026-05         2026-05-29   2026-06-01      1957
2026-06         2026-06-29   2026-07-01      1955
2026-07         2026-07-30   2026-08-03      1954
```

新的 145 期 composed market-state sha：

```
3b00fdf0ec9f54fc5b030b113ae5d91c9b2dad792b9a16e13c0b41fdc090880a
```

上游 lineage **未更換**：price panel 的 declared source fingerprint
仍為 `b0_price_universe_20260817` / `2646356f406a585c`，
同一批 zip、同一支 importer，只放寬了日期濾網。

---

### §19.4 FORWARD_EXTENSION 的准入條件（規範）

#### R2 · 六項，全部成立才得延長

```
1. window_start 與 lookback_L_months 不變
2. 既有每一期的 (decision_month, decision_date, as_of, execution_date) 不變
3. 既有每一期的 market_state_sha256 不變，
   且前 N 期的 composed hash 與延長前相同
4. 追加期所用的上游必須是既有 declared lineage 的同一份
   （同 fingerprint），僅放寬日期濾網；
   更換來源、改版 importer、或引入新 vintage 一律不是 forward extension
5. 決定延長的當下，整條 lineage 上
   performance_computed 與 gates_evaluated 皆為 false
6. 追加期的證據等級依 §19.5 顯式標定，不得預設繼承
```

第 5 項是本節的**支點**，理由見 §19.6。它不是形式要件：
一旦任何績效數字被算出來過，後續的任何窗口延長都無法與
「因為看到結果而延長」區分，此後 FORWARD_EXTENSION 條款**永久失效**，
只剩 §2.1 的唯一條件與 L3。

---

### §19.5 追加四個月的證據等級（規範）

#### R3 · 這四個月**不是** L3，也不是 untouched OOS

```
Master v1.0 凍結日                        2026-08-17
2026-04 ~ 2026-07 的市場資料存在時點       早於凍結日
L3 定義（§1.1）                           完整凍結後產生的新市場資料
⇒ 這四個月不滿足 L3
```

它們與既有 141 個月**同屬 L2 class**，並同受 §1.2 的證據力不對稱：
**L2 失敗是強證據；L2 成功是弱證據。**

**明文禁止：** 這四個月不得被稱為 `out-of-sample` / `holdout` /
`untouched` / `OOS edge` / `prospective`。`assert_l2_wording()` 的適用範圍
擴及全部 145 期，不因期數落在原窗口之外而放寬。

可以誠實陳述的是：這四個月未被 H1–H5、high52、TOP15、overlay α 掃描、
五維 11 arms、C3 Gate 1 消費過——那些研究的時鐘一律止於 2026-03。
**但「未被看過」沒有機械保證**：資料在當時可取得，沒有任何 artefact
證明沒有人看過。故不得據此升級，仍降級為 L2。

#### R4 · L3 的起點不因本次延長而改變

```
L3 第一個決策月 = 月底嚴格晚於 Master 凍結日的第一個決策月
                = 2026-08（月底 2026-08-31 > 2026-08-17）
```

L3 仍須走 production route（`core/b0_adapter_production.py`），
並受 V-5 checkpoints（36 / 60 / 84 …，36 個月前不得評估）約束。
**把 2026-04~07 併進 L2 窗口，不會、也不得縮短 L3 的時鐘。**

---

### §19.6 §1.4 No-Post-Hoc-Rescue 未被觸發，以及真正的理由

§1.4 的觸發條件是「**L2 判定 `Not Supported` 之後**，不得在同一窗口上
調整規格重跑」。

字面上它未被觸發：**L2 從未產生過任何判定。**

```
Frozen B0 L2      L2-af1b4d90c29b3b5f  period 2 F-CA-B    無判定
B0.1 diagnostic   2/141                                    無判定
B0.2 diagnostic   5/141                                    無判定
B0.4 diagnostic   4/141                                    無判定
B0.5 diagnostic   45/141                                   無判定
B0.6 diagnostic   66/141                                   無判定
B0.7 diagnostic   67/141  F-CA-B                           無判定
全 lineage        performance_computed = false
                  gates_evaluated      = false
```

**但「技術上未觸發」不是本變更的辯護理由，也不該是。**
§1.4 真正要防的是**因為看到績效而改規格**。這裡唯一有效的保護是：

> **至今沒有任何績效數字被計算過。**
> 不是「我沒去看」，而是每一次 run 的 provenance 都機械記錄了
> `performance_computed = false`，且 B0.2~B0.7 的 harness 刻意從不
> **列印** `port_value`。

延長是在**績效盲**的狀態下決定的，這是唯一可辯護的理由。
所以 §19.4 R2-5 把它從「當下的事實」提升為「條款的條件」——
它一旦不成立，本條款就不再適用。

---

### §19.7 本變更不解鎖任何東西（規範）

#### R5 · 延長不產生證據

```
B0.7 replay 終止於 seq 67（2026-08-26 時的最新狀態）
blocker  8913 | holder_side_reorganization_exit | 2020-01-14
         NOT_RECONSTRUCTIBLE，B0 於該期持有
⇒ 期 68 ~ 145 全部不可達
⇒ 追加的四期在 blocker 解除前，不曾被執行過一次
```

**明文禁止：** 不得因「窗口已延長至 2026-07」而宣稱任何新的涵蓋範圍、
新的樣本數、或任何形式的新證據。窗口的長度不是證據，**走完的期數才是**。

在 8913 的 holder outcome 被第一手文件關閉之前
（B0.8 canonical value extraction，尚未開始），
本次延長的實際效果是：**零**。這一點必須寫在任何引用 145 期的文件裡。

---

### §19.8 機械強制

```
tests/test_b0_valuation_panel_sessions.py
  test_the_extension_is_a_suffix_and_re_dates_nothing
      前 141 期必須與 route_as_of_sessions("2014-07","2026-03") 完全相同
  test_the_month_end_convention_is_a_different_answer
      85/141 → 88/145（2026-05-31 為週日，2026-05 兩種慣例一致）

tests/test_b0_market_side_state.py
  test_all_market_side_states_are_materialized
      前 141 期 composed hash 釘死為 0b68f44e…
      —— 該斷言是「被主張的事」，不是可刷新的 pin。
         它若失敗，代表重建改寫了歷史，
         所有引用 141-state composition 的封存結果全部失效。

tests/test_b0_master_prereg.py
  test_the_execution_and_selection_policy_is_pinned
      window_months == 145 == len(period_range(window_start, window_end))
```

另：`build_market_side_state.py`、`harvest_official_pbr.py` 中三處重述的
窗口字面值已移除，全部改讀 `frozen_spec`。重述一個凍結參數等同於為它
建立第二個真相來源，這正是 C-55 的形狀——它會一直同意，直到某一天不同意。

---

### §19.9 OPEN ITEMS（本變更新開）

#### O-H · `financials` 上游目錄在 repo 之外被改動

```
消失   tej_exports/DataExport0806/財報2004~202606/202606 財報583家 8-10.xlsx
       595 列，sha256 d0b9ef3b31efd32549d5153c7124d8b2e97a559a822d4aea98f9d1f923d54418
       僅存在於延長前的 financials_pit_receipt.json 之 sources 清單
新增   同目錄 2026 0826 2385家.csv（2026-08-26 00:55，UTF-16，1,879 列，
       期別全為 202606，財報發布日 2026-07-17 .. 2026-08-25）
```

**已查證，對本窗口無影響：**
`release_date ≤ 2026-03-31` 的 financials 逐位元不變；
期別 2026-06-01 在面板中有 94 列（發布日 2026-07-17 .. 07-31），
而該 CSV 中發布日 ≤ 2026-07-30 的 73 檔**全數已在面板內**——
存續的 `20260806090633.xlsx` 已經帶到。**沒有任何 in-window 列缺失。**

**但仍為 OPEN：**
1. 一個 declared source 檔案在 repo 之外被刪除，其存在僅由舊 receipt 記錄。
   D-1 的來源 quarantine 機制假設 declared upstream 是穩定的。
2. `build_financials_pit.py:92` 只 glob `*.xlsx`，**永遠不會讀到 `.csv`**，
   且不會抱怨。窗口下次若越過 2026-08，該 CSV 的列會**靜默缺席**。
   這與 D6.5 的 Big5 解碼、D6.4 的空 `receiver=` 同一類：
   來源答了，客戶端沒聽見。
   → 建議：glob 擴及 `.csv` 並宣告編碼，或在 receipt 中對
     「目錄內存在但未被 glob 命中的檔案」fail loud。

#### O-I · `preflight_141_receipt.json` 檔名保留

內容的 `periods_required` 已改為由 `frozen_spec` 導出（現為 145），
但**檔名保留 141**：b0_2 / b0_4 / b0_5 / b0_6 / b0_7 五支歷史 harness
以檔名開啟它，改名等同於修改它們的輸入。名稱中的數字自此為 legacy label。
**後果（刻意）：** 重跑上述任何一支 harness 會在 preflight 失敗——
145 期窗口的 run 不是它們記錄的那個 run。其 terminal provenance 位元組不變。

---

### §19.10 B0.7 Baseline Seal 的既有失效（先於本變更，非本變更造成）

```
seal        c973cff3dfae700323c092551fd666f0b004def9be19bfd51233df0f797a1798
bound commit 271b1106
31 個 normative module 中漂移者：2

core/b0_corporate_actions.py  3c735ebd… → c78b4a95…
    來源 commit cfbc19d1（B0.8 work in progress），非本次變更
    內容：刪除 line ~836 處一份與 line 954 逐字相同的重複
          REQUIRED_FIELDS 定義；語義中性，但改動了 normative module 位元組
core/b0_master_prereg.py      9e4607d9… → 046707d5…
    來源：本次窗口變更
```

**即在本次動工之前，B0.7 的 seal 已因 B0.8 的 WIP 而失效，只是無人量測。**
新的 Baseline Seal 必須在本文併入之後產生，且必須：

- 先暫停那個會自行 commit `cloud_cache/` 快照的 Windows 排程工作
  （seal 要求 `clean_tree = true`，否則綁定的 commit 會在封印過程中改變）
- 一併記錄上述兩項 module 漂移，而非只記錄本次的那一項

---

## C-67 · Window forward extension 141 → 145（v1.33）

- **來源：** 使用者於 2026-08-26 指示將回測延伸至 2026-07；
  上游 TEJ 匯出（`DataExport0806`，含 20260817/20260818 重新匯出）
  與 TWSE/TPEx 官方 PBR/PER 皆已覆蓋至該日之後。
- **變更：** `window_months` 141 → 145，`window_end` 2026-03-31 → 2026-07-31。
  新增 §19（R1 ~ R5）。§2.1 凍結窗口字句改寫，見下。
- **理由：** §2.1 的解凍條款未定義「向前追加期數」是否屬於解凍，
  §1.5 M-3 因此要求裁決而非預設。R1 區分 UNFREEZE 與 FORWARD_EXTENSION，
  R2 為後者立六項准入條件，其中第 5 項（全 lineage 績效盲）是支點。
- **相容性：** strategy semantics diff = none。
  **既有 141 期 state hash 全部不變**，前 141 期 composed 仍為 `0b68f44e…`，
  period-1 full-input 仍為 `7a9c8ad4…`。
  Frozen B0 ~ B0.7 的 seal、run、adjudication、diagnostic terminal
  全部位元組不變。
- **不解鎖：** replay 仍終止於 67 期；追加四期不可達（R5）。
- **測試：** 2474 passed / 3 skipped / 0 failed。

---

## §2.1 凍結窗口 —— 改寫後全文（草案）

```
Lookback L                    = 18 個月
綁定因子                       = revenue_accel（A 腿定義：近3月均 YoY − 前3月均 YoY）
資料邊界                       = monthly_revenue 真實公告日 2013-01
First eligible decision month  = 2013-01 + 18 = 2014-07
Retrospective sealed window    = 2014-07-31 .. 2026-07-31，145 個月
  原始凍結區段（v1.0 ~ v1.32）   = 2014-07-31 .. 2026-03-31，141 個月
  forward extension（v1.33）    = 2026-04-30 .. 2026-07-31，4 個月
```

**窗口起點與 lookback 不得修改。解凍條件唯一：** 發現「已保留 feature 的
PIT dependency > 18」。**不得因績效修改。**

**窗口終點的向前延長**另受 §19.4 R2 六項條件約束，
且延長所得月份的證據等級依 §19.5 R3 標定為 L2，
**不得**稱為 untouched OOS / holdout / out-of-sample / L3。

**該窗口整體不得稱為 untouched OOS / holdout / out-of-sample。**
不切 train/test：B0 在窗口內沒有需要 fitting 的參數，
切分不產生新資訊，只會製造 untouched 的假象。

---

## 版本標頭追加句（草案）

> **v1.33 = Window forward extension 141 → 145：`window_end` 2026-03-31 →
> 2026-07-31。§2.1 的解凍條款從未定義「向前追加期數」是否屬於解凍，
> 依 §1.5 M-3 裁決而非預設：R1 區分 UNFREEZE（改動起點、lookback 或任何
> 既有期的身分與內容）與 FORWARD_EXTENSION（僅在尾端追加，既有期逐位元不變），
> 前者仍受 §2.1 唯一條件約束，後者受 §19.4 R2 六項准入條件約束，
> 其中支點為「決定延長的當下全 lineage `performance_computed = false`」。
> 實測為純 suffix：既有 141 期 state hash **0 期改變**，
> 前 141 期 composed 仍 `0b68f44e…`，period-1 full-input 仍 `7a9c8ad4…`，
> price panel 既有切片逐位元相同，上游 lineage 未更換。
> 追加的 2026-04~07 **不是 L3**（其資料早於 2026-08-17 凍結日即存在），
> 與既有 141 個月同屬 L2 class，明文禁止稱為 OOS；L3 起點仍為 2026-08。
> **本變更不解鎖任何東西**：replay 仍終止於 67 期，追加四期不可達（R5）。
> 新開 O-H（financials 上游目錄在 repo 之外被改動，已查證對本窗口無影響）
> 與 O-I（preflight receipt 檔名保留）。
> 一併記錄：B0.7 baseline seal 在本次動工**之前**已因 cfbc19d1 而失效：C-67**
