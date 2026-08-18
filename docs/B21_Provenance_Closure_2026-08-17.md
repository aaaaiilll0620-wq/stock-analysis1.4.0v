# B-21 Provenance / Reproducibility — Closure

**日期:** 2026-08-17
**授權:** 使用者 2026-08-17「開始 B-21 provenance / reproducibility closure」。
**合規:** 純 code / provenance 稽核與實作。**未跑 B0 performance / IC / Sharpe / 選股研究 / A0–A3。** Frozen A 未修改(全部 diff 為空)。未 stage、未 commit。

**這是 L1 的 S-8,也是 L2 開封的最後一道硬鎖。**

---

## 1. 六類 Provenance Manifest(`core/b0_provenance.py`)

| # | 類別 | 內容 |
|---|---|---|
| 1 | **code** | commit SHA、dirty 狀態、dirty diff hash、dependency lock hash |
| 2 | **config** | canonical 序列化 + hash、已登記 override(key → 凍結條款) |
| 3 | **data** | 逐 dataset 的 content hash / schema hash / date coverage / importer lineage |
| 4 | **derived** | PIT 產業時間軸、B/M reference、feature caches —— **各自 hash + 其 upstream hashes** |
| 5 | **execution** | initial portfolio state hash、decision date、逐 dataset 的 market-data as-of、route module/version |
| 6 | **output** | target / intent / receipt / NAV 的 artifact hashes |

**任一欄缺失即 abort。** `seal()` 逐節驗證後才回傳 manifest hash。

### 1.1 三個刻意的設計選擇

**(a) `sealed_input_sha256` 刻意排除 outputs。** 這樣才能表達「同樣的輸入是否重現同樣的輸出」—— 若把 output 混進輸入 hash,replay 檢查會變成恆真。已由測試釘死。

**(b) derived artifact 沒有 upstream hashes 即 abort。** 一個沒有輸入紀錄的衍生物不可重建;只記自己的 hash 等於記錄「它存在過」,不是「它怎麼來的」。

**(c) 登記為空字串的 override 直接 abort**(錯誤訊息用詞:*provenance theatre*)。形式上有登記、實質上沒有來源,比沒有登記更誤導。

---

## 2. 🔴 `TEJ_RUNTIME_OVERLAY`:**FAIL,不是記錄**

依裁決實作:

```
FORBIDDEN_ENV = ("TEJ_RUNTIME_OVERLAY",)
```

B0 sealed run 若該變數有值且**無凍結條款授權** → **直接 `ProvenanceError`**。

錯誤訊息寫明理由:**未登記的 overlay 就是另一個 dataset,該次 sealed run 不是它宣稱的那次 run,而不只是「附註過」。**

**允許的唯一例外:** 該 key 在 `registered_overrides` 中有非空的凍結條款(與 B-19 的 registry 同一條規則)。

### 2.1 環境變數的兩級處理

| 級別 | 變數 | 處理 |
|---|---|---|
| **allowlist** | `TEJ_CACHE` / `MARKET_CACHE` / `FINMIND_CACHE` | 允許逐機器不同 —— 它們只**搬移**輸入位置,而輸入**內容**已被逐 dataset 獨立 hash |
| **forbidden** | `TEJ_RUNTIME_OVERLAY` | 改變資料**語義**而非位置 → 未登記即 FAIL |

**判準是「改位置 vs 改語義」,不是「重不重要」。**

---

## 3. Dirty tree 規則

| 情境 | 處理 |
|---|---|
| `final_seal=True`(L2 資格用) | **dirty → FAIL**。理由:dirty tree 無法只憑 commit 還原 |
| `final_seal=False`(中間稽核) | dirty 允許,**但必須帶 `dirty_diff_sha256`**;只記 `dirty=True` 不足以使該次 run 可重建 |

---

## 4. Deterministic Replay Invariant

```
verify_replay(original, replay)
  sealed_input_sha256 不同  → "not a replay"(拒絕比較,而非判失敗)
  sealed_input_sha256 相同  → output hashes 必須 bit-exact
```

**沒有 tolerance 參數,而且有測試釘死這件事** —— `inspect.signature(verify_replay).parameters == {"original", "replay"}`。

**合法非決定性必須逐 artifact 宣告**(`declared_nondeterminism`),**不得用全域容差混過去**。已宣告的 artifact 可以不同;未宣告的 artifact 不同即 abort,錯誤訊息會點名是哪一個。

> 這與 B-20 對 parity 採 bit-exact 預設是同一條原則:**一個全域容差會讓真正的差異藏進捨去誤差裡。**

---

## 5. 測試

`tests/test_b0_provenance.py` —— **29 passed**。涵蓋:

| 群組 | 測項 |
|---|---|
| 契約 | 六節宣告;乾淨 manifest 可 seal;**sealed inputs 排除 outputs** |
| 缺漏 | code/config/execution/output 缺欄 abort;data/derived 空集合 abort;dataset 五個 identity 欄逐一必填 |
| code | dirty final seal FAIL;dirty 非 final 需 diff hash |
| config | 空條款 abort;config hash 與鍵序無關 |
| derived | 無 upstream abort |
| **overlay** | forbidden 已宣告;**未登記 overlay FAIL(不是記錄)**;有凍結條款才放行;allowlist 只搬位置 |
| **replay** | 相同輸入相同輸出通過;相同輸入不同輸出 abort;不同輸入拒絕視為 replay;**逐 artifact 宣告非決定性,非全域**;**無 tolerance 參數** |

**全部 B0 測試套件合計:`tests/test_b0_*.py` — 110 passed。**

---

## 6. P-1 / P-2 裁決紀錄(`DECIDED, IMPLEMENTATION PENDING`)

### P-1 · B0 新 canonical core 收斂,**不修改 Frozen A**

> **語義只實作一次;research / production 都只是同一 canonical core 的 caller。**

收斂順序(固定):**Feature primitives → Eligibility → Selection/portfolio decision → Execution ledger → Cost**。Cost 已完成(`core/b0_cost_model.py`),實際待建為前四層。職責邊界須在 prereg 中固定。

模組骨架(檔名由實作決定,職責不可變):`b0_features` / `b0_eligibility` / `b0_decision` / `b0_execution` / `b0_cost_model`(已有)。

**方法:從已裁決定義「逐字/逐位元抽取」primitives**(沿用 `canonical_universe.py` 的既有模式),**不修改 Frozen A 的 research implementation** —— Frozen A 繼續保留歷史可重現性。

**明文禁止:** research 一份 Growth、advisor 再「完全鏡射」一份 Growth。`rev_accel` 已證明這種鏡射真的會漂。

### P-2 · 不另立 production-universe 補驗;B0 route 一次做對

> **production 與 retrospective evaluator 必須直接消費同一個 B0 canonical universe/eligibility engine。**

closure 條件 = **By construction parity + fixture verification**:
- **第一道防線:** 架構上共用同一函式;
- **第二道防線:** B-20 harness 以 fixture 證明 `same as_of + same config + same state → same universe/hash/output`。

**不採**「production 算一份、research 算另一份、每次比較兩份」—— 那只是永久維護兩份程式。

---

## 7. 順序調整(依使用者指正)

先前把「完整 prereg + commit/hash」寫在 production route 之前。**更正:最終 commit/hash 必須包含真正的 B0 route。**

```
B-21 provenance closure                     ← 本文件
  → 關 O-1 / V-1b / V-5 / V-6
  → freeze specification / prereg TEXT       ← 文字先凍
  → 建 B0 canonical route(P-1 四層)
  → route 加入 B0_ENTRY_MODULES
  → B-17 / G14-4 / B-19 自動 enforcement
  → B-20 真實 fixture parity
  → L1 全綠(S-1..S-8)
  → FINAL PROVENANCE SEAL(含 route,clean tree)   ← 真正的封存
  → 才能開 L2 一次
```

**prospective clock 起點與 L2 資格所依賴的是 FINAL PROVENANCE SEAL,不是 prereg 文字凍結。**

---

## 8. 現況與限制

```
B-21 manifest schema        : IMPLEMENTED(六類)
B-21 overlay fail-loud      : IMPLEMENTED
B-21 replay invariant       : IMPLEMENTED(bit-exact,無全域容差)
B-21 實際 sealed run        : PENDING B0 route
S-8                         : 機制就緒,但尚無可封存的 run
L1 / L2                     : 仍 BLOCKED
```

**三項限制:**

1. **本輪建立的是機制,不是一份已完成的 provenance。** B0 route 不存在 → 沒有可 seal 的 run。**本文件不宣稱 S-8 已滿足**,只宣稱 S-8 現在**可被機械驗證**。
2. **`file_sha256()` 已提供,但實際的 dataset/artifact hash 蒐集器尚未接線** —— 那要與 B0 route 一起實作。
3. **manifest 無法防止「填入錯誤的 hash」** —— 它保證欄位齊全、規則一致、replay 可驗,但誠實填寫仍是前提。這是所有 provenance 系統的共同邊界,不宜宣稱超出。

---

## 9. 未關項總表

| # | 事項 | 阻擋什麼 |
|---|---|---|
| **O-1** | Confirmation 層 chip 語義(gross / net) | Frozen B prereg |
| **V-1b** | 股票股利處理(語料無該欄位) | L1 的 S-3 |
| **V-5** | 36 月後的後續檢查點(避免 optional stopping) | L3 protocol |
| **V-6** | Sharpe 的 rf 慣例 | L2 gate 判定 |
| **P-1** | 四層 canonical core 實作 | B0 route |
| **P-2** | 共用 engine 落地 + fixture 驗證 | B-20 真實 parity |

**四項 O/V 須在完整 Frozen B preregistration 前一併關閉。**

---

## 10. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_provenance.py` | 六類 manifest、`seal()`、`assert_no_unregistered_sources()`、`verify_replay()`、`file_sha256()` |
| `tests/test_b0_provenance.py` | 29 項 |
| 本文件 | B-21 closure + P-1/P-2 裁決紀錄 + 順序更正 |

**Frozen A 驗證:`l4b_execution.py` / `portfolio_simulator_lab.py` / `test_canonical_universe.py` / `regime.py` / `backtest.py` / `bt_bundle.py` / `canonical_universe.py` 全部 diff 為空。**
