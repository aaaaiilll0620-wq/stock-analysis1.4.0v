# B-19 Runtime Override Integrity — Closure

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17「直接開始 B-19 runtime override integrity」。
**合規:** 純 code / config / provenance 稽核。**未跑 B0 performance、IC、Sharpe、選股名單或 A0–A3。** 未修改 Frozen A。未 stage、未 commit。

**目標(窄化):** 證明任何 B0 production-reachable 的 runtime/config path,都**不能在 frozen preregistration 之外靜默覆寫** factor definition、data window、data semantics、feature enablement 或 execution policy。

**L1/L2 仍 BLOCKED** —— B-19 完成不構成提前開封資格。

---

## 1. Override Inventory(八類全掃)

### C1 · CLI arguments 覆寫 frozen config

| 參數 | 預設 | 覆寫了什麼 | 位置 |
|---|---|---|---|
| `--adv-floor` | `10,000,000` | 可投資性門檻 | `universe_screen_daily.py:111` |
| `--full-pool-adv-floor` | `1,000,000` | **投組實際吃到的**母體門檻 | `:122` |
| `--shortlist-union-pct` | `15.0` | 聯集門檻(→ >85) | `:114` |
| `--include-no-pe` | `False` | **翻轉 L0 閘門**(PE 有效性) | `:112` |
| `--out-dir` / `--expected-as-of` / `--force-overwrite` | — | 輸出位置與覆寫保護 | `:116-120` |

**⚠ 這些預設值本身就是「語義」。** 命令列傳一個不同的數字,就改了 frozen 定義,而且**不留任何痕跡**。

### C2 · Environment variables

| 變數 | 覆寫了什麼 | 位置 |
|---|---|---|
| **`TEJ_RUNTIME_OVERLAY`** | **整個 dataset 的合併疊加層**(`{dataset}.parquet`) | `data_provider.py:19-20`,消費點 `:316` |
| `TEJ_CACHE` | 主資料來源目錄 | `data_provider.py:16`、`tej_bundle.py:45`、另 9 處 |
| `MARKET_CACHE` | 快照/參考表來源 | `data_provider.py:24`、另 7 處 |
| `FINMIND_CACHE` | 第三來源 | `data_cache.py:30` |
| `FINMIND_TOKEN` | API 認證 | `config.py:10` |

**`TEJ_RUNTIME_OVERLAY` 是本類最嚴重的一項** —— 一個環境變數就能讓任何 dataset 被另一份 parquet 覆蓋,**不改任何程式碼、不留 commit**。P0-R3 已記錄它是「未 commit 的 merge layer」。

### C3 · Runtime defaults

argparse 的 `default=` 與模組層常數(`FUSION_PCT`、`TOP_N`、`ORDER_ADV_CAP`、`LOT_SIZE`、`_HORIZON_WEIGHTS`、`_RATIO_TO_POINTS`)構成「不傳參數時的語義」。**預設值 = 未宣告的規格。**

### C4 · Fallback / default branches(靜默降級)

| 分支 | 行為 | 位置 |
|---|---|---|
| `_flow_chip()` 回 `None` | **靜默保留 gross 語義**,無任何訊號 | `bt_bundle.py:35-41,63-65` |
| `_legacy_whale_score` | 無多天期資料 → 退回舊版計法 | `scoring_manager.py:322-324` |
| 估值三層退回鏈 | 不同股票用不同估值定義 | `valuation.py:93-190` |
| c2 `skipna` | 缺腳靜默退化成三因子平均 | `universe_screen_daily.py:59,238` |

**後三項在 Frozen B 已被 B-09/B-15/B-16 移除;第一項尚未被任何裁決涵蓋(見 §2.2)。**

### C5 · Cache / path selection → 資料版本改變

同 C2。**沒有任何機制記錄「這次跑用的是哪一份 cache」** —— 這正是 B-21 要解決的,也是 §4 為何把 L2 開封綁在 provenance 上。

### C6 · Feature flags

`USE_RS_OVERLAY=True`、`USE_KD_FULL=False`、`USE_BBP=False`、`USE_OBV_TREND=False`(`scoring_manager.py:17-20`)、`USE_ASSET_TURNOVER=True`(`fundamentals.py:26`)。**全部是 A/B 結果擬合出來的開關**(B-09 §4 污染登記簿已記),且**可在 runtime 被任意改寫**。

### C7 · Import-time mutable globals 🔴

| 項目 | 形式 | 位置 |
|---|---|---|
| `RESEARCH_ARM` | class/module 層可變全域,**五個模組各一份** | `advisor.py:25`、`backtest.py:134`、`fundamentals.py:21`、`scoring_manager.py:6`、`valuation.py:63` |
| **`_tb._PCT_HISTORY_START = "2004-01-01"`** | **模組層直接改寫「另一個模組」的全域** | `bt_bundle.py:27` |

**後者是本次稽核發現的最危險形式** —— 詳見 §2.1。

### C8 · Caller 傳入但 prereg 未登記的 kwargs

| 介面 | 可被覆寫的 frozen 值 |
|---|---|
| `compute_target_list(..., fusion_pct=, top_n=)` | 交集門檻與濃縮 |
| `compute_order_intent(..., order_adv_cap=)` | participation cap |
| `FundamentalEngine(weights=)` | **基本面四組權重 .30/.25/.25/.20** |
| `_calc_rev_yoy_smoothed(..., months=3)` | 平滑窗 |

---

## 2. 兩個已知 `bt_bundle` override 的分類(依指示不預設要刪)

### 2.1 修1 · 估值窗 `2019 → 2004` → **`FROZEN_A_ONLY_COMPATIBILITY`**(但形式仍須封鎖)

**機制:** `core/tej_bundle.py:93` 定義 `_PCT_HISTORY_START = "2019-01-01"`,`:106` 消費它;`bt_bundle.py:27` 在 **import 時**把它改成 `"2004-01-01"`。

**分類理由:** B-09 F-E(a) 已把 expanding PE 百分位**整個移除** —— V1 換成純當期橫斷面 B/M、V3 移除、2019 錨點解除。**`_PCT_HISTORY_START` 治理的那個機制在 B0 裡不存在。** 因此它既非「已被 Frozen B 吸收的合法規格」,也非 B0 的實質污染源 —— 它是 Frozen A 專用。

**⚠ 但形式本身必須封鎖,與其值無關。** `_tb._PCT_HISTORY_START = ...` 寫在模組層,意味著:

> **只要有任何程式碼 `import bt_bundle`,`core.tej_bundle` 的行為就被 process-wide 改掉 —— 對所有消費者生效,包括從未要求它的那些。而且沒有任何 call site 可供閱讀者察覺。**

這是 override 裡最難用讀程式碼發現的一種,因為**它沒有呼叫點**。已納入 §3 的專用偵測器。

### 2.2 修2 · 籌碼語義改淨額 → **`REAL_CONTAMINATION_IF_REACHABLE`(且暴露 B prereg 的缺口)** 🔴

**機制:** `bundle.chip` 由 `institutional_gross` 換成 `institutional_flow`(淨額),以 `buy = max(net,0)`、`sell = max(-net,0)` 偽裝成同構長格式。`bt_bundle.py` 自己的 docstring 承認 `participation(buy+sell)` 以 `|net|` 近似會**略低估**。

**分類理由:** B-09 裁決 Confirmation 層(C1+Q5 合一)雖**不進 B0 selection ranking**,但**仍會被計算並報告**(production display / prospective attribution)。C1 就是「多天期法人淨參與率」,其輸入正是 chip 資料 —— **gross 與 net 會給出不同的 C1。**

**⇒ 本輪發現的 prereg 缺口(新開放項 O-1):Frozen B 的 Confirmation 層從未指定 chip 語義是 gross 還是 net。** 只要未指定,任何一邊都是「未登記的語義選擇」,而 `bt_bundle` 恰好提供了一條靜默切換的路徑。

**⇒ 修2 不能簡單歸類為「A 專用」。它暴露的是 B 規格本身的一個未決條款,必須在完整 Frozen B preregistration 前補上。**

---

## 3. B0 Reachability Graph 與 Fail-Loud Invariant

### 3.1 靜態可達性(沿用 B-17 / G14-4 的同一機制)

`core/b0_invariants.py` 新增:

```
OVERRIDE_MODULES  = ("beat_0050.realbody.bt_bundle",)
OVERRIDE_SYMBOLS  = RESEARCH_ARM / TEJ_RUNTIME_OVERLAY_DIR / _PCT_HISTORY_START /
                    bt_fetch_history / USE_RS_OVERLAY / USE_KD_FULL / USE_BBP /
                    USE_OBV_TREND / USE_ASSET_TURNOVER
```

### 3.2 專用偵測器:import-time foreign mutation

```
find_import_time_foreign_mutations(entry_modules)
  → 模組層(module scope)對「另一個模組屬性」的指派
```

針對 §2.1 的形式。**這一類無法用「找呼叫點」的方式發現,必須用 AST 在模組層掃 `Assign` 到 `Attribute`。**

### 3.3 Fail-loud registry(核心規則)

> **任何 B0 runtime override 都必須能反向對應到 Frozen B prereg 的唯一條款/config key;找不到來源就 abort。**

```
B0_REGISTERED_OVERRIDES : dict[key -> 授權條款]      # 目前為空 = B0 不授權任何 override
assert_override_registered(key) -> clause | raise OverrideNotRegistered
```

**`assert_override_registered` 刻意沒有 default 分支。** 「未登記」是**停止**,不是**退回預設** —— 一個 fallback 在這裡會重新引入這個 guard 存在的理由本身。

### 3.4 測試(`tests/test_b0_override_integrity.py`,14 項)

| 類別 | 測項 |
|---|---|
| 不變量 | B0 可達圖無 override 來源;無 import-time foreign mutation |
| **反向控制** | 偵測器對 `bt_bundle` 必須觸發;**必須抓到 `_PCT_HISTORY_START` 的 import-time 改寫** |
| 已知載體 | `scoring_manager` / `valuation` / `fundamentals` / `data_provider` / `tej_bundle` 五個全部須被標記 |
| Registry | 目前為空;未登記 key 一律 abort;**無 default fallback 路徑**;已登記者回傳條款;登記值不得空白 |

**結果:14 passed。與 B-14 / B-17 合計 `tests/test_b0_*` **61 passed**。**

**「登記值不得空白」這一項的用意:** 允許以空字串登記,等於允許 provenance theatre —— 形式上有登記、實質上沒有來源。

---

## 4. 分類總表

| Override | 分類 | 處置 |
|---|---|---|
| 修1 估值窗 2019→2004 | `FROZEN_A_ONLY_COMPATIBILITY` | 保留於 Frozen A;B0 不可達(已測);**其 import-time 形式另行封鎖** |
| 修2 籌碼 gross→net | `REAL_CONTAMINATION_IF_REACHABLE` | B0 不可達(已測);**但暴露 O-1,須補 prereg 條款** |
| `TEJ_RUNTIME_OVERLAY` | `REAL_CONTAMINATION_IF_REACHABLE` | B0 不可達(已測);B-21 須記錄實際使用狀態 |
| `RESEARCH_ARM` ×5 | `FROZEN_A_ONLY_COMPATIBILITY` | 同上 |
| 5 個 feature flags | `FROZEN_A_ONLY`(且為結果擬合值) | B0 已由 B-09 移除對應因子 |
| CLI / kwargs / cache env | **未分類 —— 待 B0 execution route 存在後才能判定** | 見 §5 |

---

## 5. 現況與限制(誠實)

```
B-19 override inventory      : COMPLETE(八類)
B-19 B0 reachability graph   : ENFORCED(B0_ENTRY_MODULES = core.b0_cost_model)
B-19 fail-loud invariant     : IMPLEMENTED(registry 空 = 零授權)
B-19 兩個 bt_bundle override : CLASSIFIED
新開放項                      : O-1(Confirmation 層 chip 語義未指定)
```

**三項必須講清楚的限制:**

1. **現階段證明的範圍極窄。** `B0_ENTRY_MODULES` 目前只有 `core.b0_cost_model`。**「B0 不可達 override」目前只對成本模型成立。** B0 execution route 組裝後加入清單,三個不變量(B-17、G14-4、B-19)才會真正對整條路徑生效。**本文件不宣稱已證明整個 B0。**
2. **C1(CLI)、C5(cache path)、C8(kwargs)無法在 route 存在前判定** —— 它們是否構成 override,取決於 B0 route 如何呼叫。
3. **靜態分析不涵蓋動態存取**(`setattr`、`globals()`、字串拼接的屬性名)。與 B-17 同一限制。

---

## 6. 新開放項

| # | 事項 |
|---|---|
| **O-1** | **Frozen B 的 Confirmation 層必須明文指定 chip 語義(gross 或 net)**,否則 §2.2 的未登記語義選擇仍然存在。須在完整 Frozen B preregistration 前關閉。 |

**既有未關項:** V-1b(股票股利)、V-5(36 月後檢查點)、V-6(Sharpe rf 慣例)。依使用者指示,**最遲須在完整 Frozen B preregistration 前一併關掉。**

---

## 7. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_invariants.py`(擴充) | `OVERRIDE_MODULES` / `OVERRIDE_SYMBOLS` / `B0_REGISTERED_OVERRIDES` / `assert_override_registered()` / `find_import_time_foreign_mutations()` |
| `tests/test_b0_override_integrity.py` | 14 項:不變量、反向控制、五個已知載體、registry fail-loud |
| 本文件 | Override inventory + 分類 + 不變量 |

**Frozen A 未修改。未跑 B0 performance / IC / Sharpe / 選股名單 / A0–A3。未 stage、未 commit。**
