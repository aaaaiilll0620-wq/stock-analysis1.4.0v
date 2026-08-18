# F-0 Ruling Closure · F0-R1 ~ F0-R7（Master v1.13 / C-46）

**日期:** 2026-08-18
**狀態:** ✅ **F-0 = CLOSED** · `OPEN SPEC ITEMS = 0` · `OPEN FINALIZATION ITEMS = 0`
**合規:** 未 stage / commit、未 final seal、未開 L2、未執行 `run_decision`、未計算 CAGR / Sharpe / MDD / IC / win rate、未檢視選股、未修改策略語義。

---

## 落地對照

| # | 裁決 | 落地位置 | 驗證 |
|---|---|---|---|
| **F0-R1** | `config_hash` = 完整 declaration registry，非 runtime 子集 | `spec("config_hash_scope")`、`spec("config_hash_is_runtime_subset")=False` | **122/122 key** 逐一 mutation 皆改變雜湊 |
| **F0-R2** | `spec_sha256` = 凍結 Master 文件 raw-byte identity | `b0_master_prereg.spec_document_sha256()` | 走 `file_sha256`，**刻意不經 canonicalise**（空白變動必須改雜湊） |
| **F0-R3** | implementation identity = commit SHA + 明列 normative-module hashes | `NORMATIVE_MODULES`（**23 個**，移入 `core/b0_master_prereg.py`）、`CodeProvenance.normative_module_sha256` | final seal 缺任一模組雜湊即 abort；竄改單一模組雜湊使 `sealed_input_sha256` 改變 |
| **F0-R4** | production-reachable declaration 必須 implementation-derived 或有可執行行為 conformance | **新** `core/b0_declaration_conformance.py` | **17 宣告 / 7 derived / 10 behavioural / 0 failures**；`seal(final_seal=True)` 呼叫 `assert_declarations_conform()` |
| **F0-R5** | `state_hash` = canonical concrete input-state identity，非 implementation hash | `spec("state_hash_scope")`、`spec("state_hash_is_an_implementation_hash")=False` | listing-spell 變動 → 改變；spell 順序 → 不變；`route_kind` → 不入雜湊 |
| **F0-R6** | B-21 manifest **直接**綁七層 | 新 `SpecificationProvenance`；`PROVENANCE_SECTIONS` 6 → **7** | `sealed_input_sha256` 直列 `specification` + `normative_modules`；缺 `spec_sha256` 即 abort |
| **F0-R7** | route 與 provenance 共用單一 serialization / hash primitive | **新** `core/b0_canonical_hash.py`（`b0_canonical_hash@1`） | `b0_route._hash` 與 `b0_provenance._h` 皆為別名；測試斷言 core 內**不得再有第二個 `json.dumps`** |

---

## 雜湊實測

```
v1.11  config_hash                       40375c345c2d1604b67fdac981cd25ac119c79a6680e416fc79514792e9a012d
F0-R7 統一 primitive 之後                40375c345c2d1604b67fdac981cd25ac119c79a6680e416fc79514792e9a012d   ← 未變
v1.13（+11 個 hash-boundary key）        fad64b65148d9d7f550aaf0d2c38ad27dcb47f399b237ed8d3a07181398f5567
spec_sha256 (v1.13)                      932a8c8189b23904c8817584837d9d175b64e58665c6d69360fc808f04ab692c
```

**F0-R7 的統一是行為保持的**，並由重建證明：從 v1.13 registry 移除且僅移除那 11 個 hash-boundary key，重算得 `40375c34…` **逐位元相同**。雜湊改變**只**來自新增宣告，不來自序列化器更換。

---

## F0-R4：兩種 binding 各自擋得住什麼

**IMPLEMENTATION_DERIVED（7）** —— registry 值**就是**模組常數。改行為 → `config_hash` **自動**移動。
其 `check` **不是** drift 偵測器（兩邊讀同一常數，這點已寫進模組文件並由測試釘住）；它擋的是**把導出換成今天的字面值副本**，也就是 derived binding 悄悄不再是 derived 的那種失效。

**BEHAVIORAL_CONFORMANCE（10）** —— 值是常數載不動的散文，改由**可執行檢查跑那句話描述的行為**。三個負向控制證明它們真的會抓到（且此時 registry 句子與 `config_hash` **完全不動**）：

| 破壞 | 被抓到的宣告 |
|---|---|
| guard 改成忽略持倉 | `unexplained_gap_abort_scope` |
| `_available_before` 放寬為「有值就算」 | `o_e_1_availability_rule` |
| 未解釋缺口不再切斷 spell | `listing_spell_break_rule` |

**檢查放在 core 而非測試檔**：只存在於 pytest 下的檢查對 `seal()` 不可用。

---

## 回歸

```
tests                     1932 passed, 2 skipped, 0 failed   (was 1898, +34)
  test_b0_declaration_conformance   28 passed (新)
unmet_blocking_requirements()   []
OPEN SPEC ITEMS                 0
OPEN FINALIZATION ITEMS         0
declaration conformance         17 declarations, 0 failures
normative modules               23
registry keys                   111 -> 122
Frozen A                        七檔未修改;本輪 scripts/ 零檔案異動
staged / committed              0 / 0（HEAD 仍為 d8f34fd）
```

因裁決而改寫的既有測試：`PROVENANCE_SECTIONS` 六 → 七、manifest fixture 補 `specification` 與 normative-module 雜湊、F-0 阻擋測試改為「register 已空 + 機制仍會在有項目時觸發」的負向控制。

---

## 仍待

**final provenance seal** 與 **repo finalization**。兩者本輪皆未進行。`seal(final_seal=True)` 現在會依序檢查：finalization register → declaration conformance → blocking data requirements → dirty tree。
