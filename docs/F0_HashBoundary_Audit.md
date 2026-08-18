# F-0 · Config / Spec Hash Boundary Audit

**日期:** 2026-08-18
**裁決:** 🔴 **Case C** —— Master 未定義 hash scope → 依 M-3 登記 `hash_scope_boundary` 為 **UNSPECIFIED**，**阻擋 final provenance seal**。**施工方不作 scope 選擇。**
**合規:** 未執行 `run_decision`、未開 L2、未計算 CAGR / Sharpe / MDD / IC / win rate、未檢視選股、未修改策略語義、未 stage / commit、未開始 final seal。

> 規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.12 §11 C-45 與 §12.2 F-0-1。機器可讀輸出在 `research/f0_hash_boundary/hash_boundary_map.json`。

---

## 0. ⚠ 先更正一個回報錯誤：`config_hash` 其實有變

HEAD 的 `config_hash` 是 **`40375c345c2d1604b67fdac981cd25ac119c79a6680e416fc79514792e9a012d`**。

上一輪報告裡的 `27fee343…d13f03` 是在 13 個 O-F/O-G key 加進 registry **之前**跑的 adapter 驗證留下的值，加完之後我沒有重測就沿用。

**機械證明（非宣稱）：** 從 HEAD registry 移除**且僅移除**那 13 個 key，重算得到

```
reconstructed v1.10 config_hash : 27fee343a3083e2aeba87eae960c01d5916b09a61819b7623486ec4bcfd13f03
reported during v1.11 work      : 27fee343a3083e2aeba87eae960c01d5916b09a61819b7623486ec4bcfd13f03
MATCH                           : True        (98 keys -> 111 keys)
```

**這是回報錯誤，不是 hash scope 洩漏。** 但你提的問題本身成立，以下是實查結果。

---

## 1. F0-1 · Producer lineage

| hash | producer | canonical serialization |
|---|---|---|
| `spec_sha256` | `research/b0_registry/freeze_master_prereg.py:75` → `core/b0_provenance.py:64 file_sha256` | **raw file bytes**，1MiB chunk，無正規化 |
| `config_hash` | `core/b0_route.py:129` → payload `core/b0_route.py:109 canonical_config()` | `core/b0_route.py:123 _hash()` = `json.dumps(_stable(p), sort_keys=True, ensure_ascii=False, separators=(',',':'))` |
| `state_hash` | `core/b0_route.py:267` → payload `core/b0_route.py:198 state_payload()` | 同上 `_hash()` |
| （另一個）`ConfigProvenance.config_sha256` | `core/b0_provenance.py:105` → `core/b0_provenance.py:57 _h()` | **不同函式**：無 `_stable()` 前處理，改用 `default=str` |

- **key selection：** `core/b0_master_prereg.py:634 specified_keys() = tuple(sorted(_spec_registry()))`；registry 本體在 `:380`
- **ordering：** 排序兩次（`specified_keys()` 一次、`json sort_keys` 一次），插入順序不可能洩漏 —— 已測
- **encoding：** `None` → JSON `null`（與字串 `"None"` 不同雜湊，已測）；`bool` → `true/false`（與 `0/1` 不同，已測）；`tuple` → array；float 不做四捨五入
- **`_stable` vs `_h` 目前結果相同，但未被證明等價** —— 已加測試釘住，兩者哪天分歧就是 failure 而不是兩份不同的 provenance

---

## 2. F0-2 · Key coverage map（111 keys，全部由 mutation 實測）

`research/f0_hash_boundary/hash_boundary_map.json`，每筆為
`master_key → included_in_config_hash → named_in_spec_document → looked_up_at_runtime → category`。

| category | keys | in config_hash | runtime `spec()` |
|---|---:|---:|---:|
| feature_formula | 20 | **20** | 1 |
| execution | 17 | **17** | 5 |
| eligibility | 12 | **12** | 1 |
| portfolio_construction | 12 | **12** | 5 |
| evidence_protocol | 10 | **10** | 0 |
| corporate_action | 9 | **9** | 0 |
| market_quantity（ADV20 / σ20D） | 7 | **7** | 0 |
| **o_f_gap_semantics** | 6 | **6** | 0 |
| **o_f_status_semantics** | 5 | **5** | 0 |
| **o_g_listing_spell** | 5 | **5** | 0 |
| cost | 4 | **4** | 0 |
| **o_e_1_availability** | 2 | **2** | 0 |
| provenance_contract | 2 | **2** | 0 |
| **合計** | **111** | **111** | **12** |

`UNCATEGORISED = []`。

**兩個關鍵事實：**

1. **`config_hash` 不是 subset —— 是整個 registry。** 111/111 key 逐一 mutation 皆使雜湊改變。所以 **validation-only / provenance-only / reporting-only key 也在 config_hash 裡**（`sharpe_metric_name`、`l3_*`、`window_*`、`l2_outcomes` 皆已實測）。
2. **111 個 key 中只有 12 個**在 B0 import closure 裡被 `spec()` 讀取（`N_target`、`X_buy`、`X_sell`、`adv_floor_multiple`、`buy_priority`、`percentile_convention`、`reweight_when_under_target_breadth`、`selection_tie_break`、`share_rounding`、`target_drift_policy`、`w_max`、`w_target`）。**`config_hash` 是 declaration hash，不是 runtime-parameter hash。**

---

## 3. 問題 3 / 4 的直接回答

**哪些 normative key 進 `config_hash`？** —— **全部 111 個，無例外。**

**哪些只進 `spec_sha256` 不進 `config_hash`？** —— **從 key 的角度：沒有。** 但這個問題的前提需要修正：`spec_sha256` 不是 hash key，它 hash 的是**文件 bytes**。真正只被 `spec_sha256` 涵蓋的，是**文件裡有、但從未成為 registry key 的規範散文**；而真正**兩者都不涵蓋**的，是**規範性 core 模組的行為**（模組雜湊另存於 freeze record 的 `normative_modules`，**未併入 `spec_sha256`**）。

---

## 4. 問題 5 —— O-F / O-G 改了 state / route semantics，`config_hash` 為何可以不變？

實際上 v1.10→v1.11 它**變了**（§0）。但**機制上它確實可以不變**，這才是本次審計的真正發現：

**沒有任何機制要求一條 normative 行為必須擁有 registry key。**

O-F 的 guard 換 scope（`assert_no_unexplained_price_gap` → `assert_no_unexplained_gap_in_holdings`）與 O-G 的 route 接線，都是**程式碼**變更。那 13 個 key 是我**事後手寫補上的鏡像**，不是被任何檢查逼出來的。若我沒補，route 行為已改而 `config_hash` 原封不動。

**接縫還有第二層：** 13 個 key 裡

- **6 個的值直接讀自實作模組**（`status_event_semantics`、`status_by_event_semantics`、`price_lookback_sessions`、`spell_bridging_tolerance`、`unknown_event_semantics_fails_closed`、`book_closure_may_explain_absence`）→ 改行為即改雜湊 ✅
- **7 個是散文字面值**（`o_e_1_availability_rule`、`unexplained_gap_abort_scope`、`status_source_completeness_required`、`listing_spell_break_rule`、`price_lookback_reset_at_spell_start`、`reappearance_may_explain_earlier_gap`、`snapshot_delisting_fields_are_audit_only`）→ **無法追蹤它們所描述的程式碼** ⚠

把 `assert_no_unexplained_gap_in_holdings` 改成忽略持倉，`unexplained_gap_abort_scope` 仍會寫著 `"held_positions_only"`，`config_hash` 不動。

---

## 5. F0-3 · Mutation negative controls（`tests/test_b0_hash_boundary.py`，39 tests）

全部在 registry 的**隔離副本**上操作，未動 frozen master。

| 控制 | 結果 |
|---|---|
| 全部 111 key 逐一擾動 | **111/111 使 `config_hash` 改變**（`unmoved == []`） |
| strategy / runtime decision key（`N_target`、`w_max`、`X_buy`、`share_rounding`、`selection_tie_break`、`commission_rate`、`impact_k`、`adv_floor_multiple`） | 改變 ✅ |
| production-reachable state semantic key（`unexplained_gap_abort_scope`、`listing_spell_break_rule`、`price_lookback_sessions`、`spell_bridging_tolerance`、`status_by_event_semantics`、`o_e_1_availability_rule`） | 改變 ✅ |
| **reporting / validation-only key**（`sharpe_metric_name`、`l3_checkpoint_interval_months`、`l2_outcomes`、`window_months`） | **也改變** —— 設計上**沒有**排除它們。這條測試存在的理由是：「config_hash 是 runtime subset」這個自然假設在本專案是**錯的** |
| `None` vs 字串 `"None"` | 不同雜湊 ✅ |
| `True` vs `1` | 不同雜湊 ✅ |
| key 順序反轉 | **雜湊不變** ✅ |

---

## 6. F0-4 · B-20 三個 hash 的分工，以及 listing-spell 是否被捕捉

| hash | 捕捉什麼 | 不捕捉什麼 |
|---|---|---|
| `as_of` | **哪一天**的決策狀態 | 規則、輸入值 |
| `config_hash` | **在哪一套宣告下**執行 | 具體輸入值；**未成為 key 的程式碼行為** |
| `state_hash` | **餵進去的是哪一份 state**（含 listing spells） | 規則；`route_kind`（刻意排除） |

**「O-G 改變 listing-spell segmentation 而 `config_hash` 不變，是否一定由 `state_hash` 捕捉？」** —— 由測試證明，**是**：

- spell `start` 改動 → `state_hash` 改變 ✅
- `opened_by` 由 `first_observation` 改為 `reappearance` → 改變 ✅
- 少宣告一檔的 spell → 改變 ✅
- 完全不宣告 spell → 改變 ✅
- **spell 順序反轉 → 不變** ✅（兩個 adapter 可用不同順序建同一組）
- 只有 state 改變時 → `config_hash` **不變** ✅
- `route_kind` 不同、其餘相同 → `state_hash` 相同 ✅

**前提：spell 必須被宣告。** 這由 O-G 的 `assert_spells_declared` 在兩個 adapter 上對非 synthetic 來源強制（v1.11 C-43）。

---

## 7. F0-5 · B-21 manifest 的 binding 缺口

`ProvenanceManifest.sealed_input_sha256` 綁：**code**（`commit_sha` / dirty / lock）、**config**（`config_sha256` + overrides）、**data**、**derived**、**initial_state**、decision_date、market_data_as_of、route module/version。

**缺 `spec_sha256`。** sealed run 不指名自己遵守的是哪一版 master preregistration —— 只在 clean tree 下由 `commit_sha` **遞移**涵蓋。

**對照組：** `core/b0_master_prereg.py:314 L2Opening` **要求** `spec_sha256` + `code_commit` + `data_manifest_sha256`。**同一專案的兩個登記簿綁定集不同**，這使 manifest 的沉默成為一個邊界問題，而不是全案疏漏。

**列為 finalization blocker 的候選之一**（登記項的選項 C），本文件不作選擇。

---

## 8. 裁決：Case C

| 案別 | 是否成立 | 理由 |
|---|---|---|
| **Case A**（設計本來就是 spec=全規格 / config=runtime subset / state=state） | ❌ | 兩處不符：`spec_sha256` **不是**全規格（規範模組未併入）；`config_hash` **不是** subset（111/111，且只有 12 個在 runtime 被讀）。且 Master 未載明任何一者 |
| **Case B**（曾宣稱 config_hash = 整個 registry，實作卻漏掉 key） | ❌ | 實作與該宣稱**完全一致**；沒有 key 被漏掉。缺的是「行為必須成為 key」的義務 |
| **Case C**（沒有清楚定義 hash scope） | ✅ | Master §8.5 只把三者列為 parity 輸入、§13.2 只說本文件雜湊另存。**`config_hash` 的 scope 只寫在 `core/b0_route.py:104` 的註解裡** —— 依 M-3「no specification-by-code」，註解不是規格 |

**依 Case C 執行：**

```python
>>> from core.b0_finalization_items import summary
>>> summary()
{'total': 1, 'keys': ['hash_scope_boundary'],
 'by_stage': {'final_provenance_seal': 1, 'L2_opening': 0}}

>>> from core.b0_provenance import seal
>>> seal(manifest, final_seal=True)
FinalizationBlocked: M-3: final_provenance_seal is blocked by 1 undefined
specification scope(s) — hash_scope_boundary: ... The implementer must not
pick the scope; a ruling has to.
```

登記項載明四個候選方案（A 加「覆蓋義務 + key 值必須由實作模組導出」／B 拆成 runtime subset + declaration hash／C 把 `spec_sha256` 與模組雜湊併入 manifest／D 其他），**本輪不選**。

新增登記簿刻意**不放進 `core/b0_open_items.py`** —— 那是 P-1b canonical-core layer 的登記簿，S-1 讀它來判定「Selection path 是否規格完備」。把 provenance 缺口放進去會讓 S-1 誤紅。`OPEN SPEC ITEMS` 仍為 **0**，`OPEN FINALIZATION ITEMS` 為 **1**。

---

## 9. 回歸

```
tests                     1898 passed, 2 skipped, 0 failed   (was 1857, +41)
  test_b0_hash_boundary   39 passed (新)
unmet_blocking_requirements()   []
OPEN SPEC ITEMS                 0
OPEN FINALIZATION ITEMS         ['hash_scope_boundary']
config_hash (HEAD)              40375c345c2d1604b67fdac981cd25ac119c79a6680e416fc79514792e9a012d
spec_sha256 (v1.12)             5a87e445923efea77c361960e38d4cd814edba746762aff8791af4a9373b798b
Frozen A                        七檔未修改;本輪 scripts/ 零檔案異動
staged / committed              0 / 0（HEAD 仍為 d8f34fd）
```

三個既有 seal 整合測試因新閘門而改寫（在隔離副本上清空 finalization register 以續測資料層），並新增兩個測試：**final seal 被 F-0 擋住**、**非 final 的 seal 不受影響**。
