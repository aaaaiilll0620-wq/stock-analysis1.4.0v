# P-2 · Shared Route 與兩個 Adapter

**日期:** 2026-08-18
**狀態:** `BUILT / B-20 fixture parity PASS (bit-exact)`
**合規:** 純實作與接線。**未執行任何報酬 / IC / Sharpe / CAGR / MDD / 選股名單，未動 A0–A3，未讀真實價格母體。** Frozen A 內容未變。未 stage、未 commit。

> **規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.7（§8.5 / §8.7 / §11 C-37）。本文件為 rationale / audit trail。**

---

## 0. 結論

```
retrospective adapter ─┐
                        ├──> CanonicalDecisionInput ──> core.b0_route.run_decision
production adapter ─────┘                                  └─> 四層 canonical core

全庫 1753 passed / 2 skipped     (P-2 前 1714)
B-20 fixture parity              PASS,float_tol = 0.0
OPEN SPEC ITEMS                  0（本輪未新增）
UNMET BLOCKING                   ['price_universe_survivorship']（未動）
spec_sha256 (v1.7) = a359f8121fe2756b403383d74fac9bcb8863d1f13ac827e6ab573fa6c0647dbf
```

**本輪沒有出現任何無法由 Master v1.6 唯一推出的行為，因此未新增 UNSPECIFIED。**

---

## 1. 「只有一套 engine」是結構事實，不是宣稱

`core/b0_route.py::run_decision` 是**全庫唯一依序呼叫四層的地方**。adapter 只做：

```
source → PIT / provenance / schema 驗證 → CanonicalDecisionInput
```

三道機械檢查讓 adapter **無法**偷偷變成第二套 engine：

| 檢查 | 內容 |
|---|---|
| import 封鎖 | AST 檢查：adapter 不得 import `b0_features` / `b0_eligibility` / `b0_decision` / `b0_execution` |
| 呼叫封鎖 | AST 檢查：adapter 不得呼叫 24 個策略語義入口點（`build_feature_panel`、`score_eligible`、`target_shares`、`execute_session`、`child_order_cost` …） |
| 入口唯一 | 兩個 adapter 都必須且只能經由 `run_decision` 進入 core |

**要讓 adapter 重新實作任一語義，得先讓測試變紅。** 這比 parity 測試強：parity 只證明兩者「今天一致」，結構證明擋住「明天分岔」—— 正是 `b0_parity.py` 開頭那段設計立場（`rev_accel` 同名分岔的教訓）。

### 1.1 為什麼 panel 由 core 建而不是由 adapter 建

若 adapter 各自組 panel，**每個 adapter 都得決定「哪個成員用哪個函式算」** —— 那就是兩個 feature 層披著 adapter 的名字。因此 `build_feature_panel()` 放在 `b0_features`（§8.7 給該層的職責就是「PIT input → canonical feature values」），adapter 只交出 `SecurityPitInputs` 原始 PIT 序列。

---

## 2. 四個 parity contract 的實作方式

### P2-1 `as_of`

`resolve_as_of(decision_date, calendar)` 在 **route** 裡，不在 adapter 裡。兩邊不可能一邊用 month-end label、一邊用 prior close —— 沒有地方可以各自決定。

```
decision 2020-06-30 → as_of 2020-06-29（前一個已完成 session,§6.6）
```

`CanonicalDecisionInput.__post_init__` 另外硬性要求 `as_of < decision_date < execution_date`。測試 `test_a_month_end_label_used_as_as_of_fails_loud` 釘死 mismatch 會 fail-loud。

### P2-2 `config_hash`

**沒有 adapter config。** canonical config **就是** frozen spec registry：

```python
canonical_config() = {k: spec(k) for k in specified_keys()}
config_hash()      = sha256(canonical JSON)
```

adapter 想加旋鈕，得先在 master prereg 加一個 key —— 那是 §11 變更，而且 hash 會動。測試另外斷言兩個 sources dataclass **沒有** `config` / `overrides` / `params` / `arm` / `settings` 欄位。

### P2-3 canonical input state

`CanonicalDecisionInput` 固定 schema，涵蓋裁決點名的每一項：prices/marks、ADV20、sigma20d、財報狀態、月營收狀態、PIT 產業、corporate-action 轉換後持股、cash、pending_exit、證券/市場狀態、provenance attestation。

**兩個關鍵設計：**

- `state_payload()` **刻意排除 `route_kind`** —— 否則兩條 route 永遠不可能 hash 相同
- **NA 以 `None` 明確編碼，不折成 0 或空字串**（§4.1 對這個差別有動作）。測試 `test_na_is_distinguished_from_zero_in_the_state_hash` 釘死 `per_tse=None` 與 `per_tse=0.0` 的 hash 不同

### P2-4 inputs 先於 outputs

直接重用既有 `b0_parity.assert_parity`，它本來就先比 `as_of` / `config_hash` / `state_hash`，任一不符即 raise，**不會進到 output 比對**。

測試 `test_agreement_on_names_alone_is_not_parity` 明確構造「兩邊選到同樣股票但 state_hash 不同」的情形，確認仍然 abort。

### P2-5 deterministic output parity

`ROUTE_PARITY_COLUMNS` = 11 個執行/成本欄 + 11 個 feature 成員 = **22 欄逐檔比對**，`float_tol = 0.0`。

**沒有設任何非零 tolerance，也沒有 global 逃生門。** `b0_parity.PARITY_COLUMNS`（原七欄契約）未被修改 —— route 傳的是 superset。

---

## 3. Fixture 的實際輸出（synthetic，非證據）

```
stages        11 個全跑,順序 = PIPELINE_STAGES
universe 4 → eligible 4 → selected 4（20% 投資,80% cash）
scores        0.3875 / 0.4903 / 0.5097 / 0.6125（無平手）
receipts      4 筆 buy,含 1101 的 drift rebalance（持 1000 → target 12550 → 買 11550）
cost          explicit_fee 1416.19 / tax 0 / impact 443.28,三欄分離
```

**這些數字全部來自編造的 fixture，不是任何證券的證據。** 它的作用是讓 parity 有東西可比：如果 fixture 讓所有標的都被 complete-case 剔除，parity 會在「兩邊都空」的情況下通過，那是假綠燈。

`1101` 的 drift rebalance 同時驗證了 C-16 在 route 上真的生效。

---

## 4. S-3b：守衛第一次被 NAV 路徑呼叫

在 P-2 之前，corporate-action 與 PIT 可觀測性守衛**存在且有單元測試，但沒有任何會產生 NAV 的東西呼叫它們** —— §11 C-3 拆 S-3a / S-3b 就是為了不讓「資料到位」被誤讀成「已強制執行」。

`run_decision` 現在在 `corporate_action_transition` stage 呼叫兩個守衛，且該 stage 由 O-A 強制為 pre-mark mandatory。三個測試從另一側證明它們真的擋得住：

| 測試 | 驗證 |
|---|---|
| `test_an_exposed_unreconstructible_action_aborts_the_whole_route` | 持有期間涵蓋 `NOT_RECONSTRUCTIBLE` 事件 → 整條 route abort,不產生 NAV |
| `test_an_event_we_never_held_does_not_abort` | 未持有則不 abort（逐事件規則因此可負擔） |
| `test_an_unexplained_price_gap_aborts_before_a_portfolio_exists` | 缺價且無解釋 → 在組合存在之前 abort |
| `test_a_suspension_known_before_the_gap_is_explained_and_marked_stale` | 已解釋 → stale mark,打旗標並計數 |

**⚠ S-3b 未記為全綠。** 守衛已接入並經測試，但**真實資料端到端仍被 D-1 擋住**，所以 §9.1 記為「守衛已接入並經測試 / 真實資料 BLOCKED by D-1」。把兩者合併成一個綠燈正是 C-3 的錯誤。

---

## 5. D-1 沒有被繞過

三層都擋：

1. `run_decision` → `assert_price_state_admissible(attestation, for_sealed_run=)`
2. **retrospective adapter 另有一道自己的檢查**，並在錯誤訊息裡點名 replay 的特定風險（141 個窗口月中 87 個受污染）
3. fixture 一律 `synthetic=True`，而 synthetic **不得** feed sealed run

`test_d1_still_blocks_the_real_retrospective_route` 對 live registry 查詢，不是複製結論：D-1 修好那天，這個測試會自動走另一條分支。

---

## 6. 不變量結果

| 項目 | 結果 |
|---|---|
| B-17 regime 不可達 | ✅ 10 passed（route + 兩個 adapter 已納入 `B0_ENTRY_MODULES`） |
| B-19 override integrity | ✅ 14 passed |
| G14-4 legacy cost path 不可達 | ✅ 37 passed（`test_b0_cost_model`） |
| M-1 stage order / CA transition | ✅ 59 passed（`test_b0_master_prereg`）+ route 層 19 passed |
| S-3b 守衛接線 | ✅ 已接入並測試（真實資料待 D-1） |
| B-20 fixture parity | ✅ 20 passed,bit-exact |

`B0_ENTRY_MODULES` 已加入 `core.b0_route` 與兩個 adapter —— **五個不變量因此自動對新 route 生效，測試不需改動**（§8.4 的設計目的）。

---

## 7. 下一步

```
D-1 重新匯出 2019-2026 含下市     ← 現在是唯一實質 blocker
  ↓
B-20 real-data parity（fixture 已就緒,換掉 attestation 即可）
S-3b 真實資料 end-to-end
S-8 clean tree + provenance seal
  ↓
L1 全綠 → FINAL SEAL → 才有資格開 L2 一次
```

**工程上，B0 現在只差資料。**
