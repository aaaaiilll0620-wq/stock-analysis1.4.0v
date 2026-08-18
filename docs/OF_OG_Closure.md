# O-F / O-G Closure · Master Prereg v1.11（C-41 ~ C-44）

**日期:** 2026-08-18
**狀態:** ✅ **O-F CLOSED** · ✅ **O-G 開立並同版關閉** · ✅ **S-3b SATISFIED**
**合規:** 未執行 `run_decision`、未開 L2、未計算 CAGR / Sharpe / MDD / IC / win rate、未產生或檢視選股名單。未 stage、未 commit。

> 規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.11 §11 C-41 ~ C-44 與 §12.2。證據記錄在 `docs/OF_SecurityStatusSource_Audit.md`。

---

## 1. O-E-1 維持嚴格（裁決 1）

`available_from < first_missing_session` 原文一字未改。**同日事件未改判為 explained** —— 那正是選項矩陣中單獨可買到 293→102 的一項，未採用，因為沒有獨立的 availability 證據。

`spec("o_e_1_availability_rule")` → `"available_from < first_missing_session"`

---

## 2. O-F 關閉語義（裁決 2）

關閉的是**處理方式**，不是缺口。

| 情況 | 行為 |
|---|---|
| 有 PIT-safe 狀態 | `EXPLAINED` |
| 首個缺價 session 無 PIT-safe 狀態 | `UNEXPLAINED / UNKNOWN` |
| **B0 未持有** | **不 abort**（診斷） |
| **B0 在缺口發生時持有** | **fail-loud abort** |
| 當期快照 `下市日期` | **audit-only，runtime 不可達** |

**實作：** route 上的 `assert_no_unexplained_price_gap(as_of, all_observations)` 換成
`assert_no_unexplained_gap_in_holdings(as_of, observations, portfolio.held_securities)`。

舊寫法把所有 observation 交給 guard，於是「來源不完整」看起來像「路徑失敗」——**上一輪的真實資料驗證就踩過這個坑**，把全母體丟進 guard、再把 abort 讀成 route 缺陷。

**機械化的 audit-only 邊界：** `AUDIT_ONLY_MODULES` / `AUDIT_ONLY_SYMBOLS`，以 AST import-closure 檢查 `下市日期`、`公司資料`、`load_master`、`delisted_on` 從 **12 個 B0 entry module 全部不可達**（0 violations）。

**不要求 unexplained = 0。** 現況 293 / 352，且會一直如此。

---

## 3. 事件語義分類（裁決 4）

| 語義 | 可產生的 status | 列數 |
|---|---|---:|
| `LISTING_TERMINATION`（下市 / 終止 / 併入） | `delisted` | 167 |
| `BOOK_CLOSURE`（減資 / 面額變更 / 停止過戶） | **無** | 1,148 |
| `TRADING_SUSPENSION` | `suspended` | 605 |
| `UNKNOWN` | **無**（fail closed） | 30 |

順序有意義：`合併下市` 是終止，`現金減資` 是停止過戶。**fail closed = 不產生 StatusRecord，因此永遠不會解釋任何缺價。**

**收緊的實測後果（誠實揭露）：**

| 量 | 之前 | 之後 |
|---|---:|---:|
| status 紀錄 / 證券 | 3,708 / 1,046 | **1,375 / 566** |
| fail-closed 列 | — | **1,178**（BOOK_CLOSURE 1,148 + UNKNOWN 30） |
| audit B 無解釋終止 | 286 | **293** |
| D-1 security-level 無解釋終止 | 2 | **3**（新增 `3126`） |

**D-1 未受影響：** C1 / C2 / backstop 全過，`2018-12-28` 仍 ABSENT，known cases **98/98**，`price_universe_survivorship` 仍 SATISFIED。

importer `b0_market_state_importer@2` → `@3`。

---

## 4. O-G · canonical listing spell（裁決 3）

新模組 `core/b0_listing_spell.py`。

- 無法解釋的缺價 + 之後重新出現 → **於首個重新觀測到的 session** 開始新 spell
- **被解釋的缺口不切斷 spell**（停牌是一段上市之內的中斷）
- `ADV20` / `sigma20d` 於新 spell 重置；歷史不足 → **NA / complete-case**
- **不得以未來的重新出現回頭解釋原本的消失** —— `assert_disappearance_not_explained_by_return`
- **零自由參數：** `SPELL_BRIDGING_SESSION_TOLERANCE = None`

**接線：** `CanonicalDecisionInput.listing_spells` 進 `state_payload`；`assert_price_lookbacks_reset` 在 route、`assert_spells_declared` 在兩個 adapter（非 synthetic 才要求）。

**真實資料驗證 —— 兩個互不相干的來源給出同一個日期：**

| 證券 | 價格導出的 spell 起點 | 母表 `listed_from` |
|---|---|---|
| `8102` | 2023-10-27 | 2023-10-27 |
| `3135` | 2021-11-22 | 2021-11-22 |
| `8089` | 2018-08-31 | 2018-08-31 |
| `6606` | 2020-01-09 | 2020-01-09 |
| `4749` | 2022-02-15 | 2022-02-15 |

27 檔離場再上市證券**全部**導出 `reappearance` spell。2020-06-29 的 20 檔持倉中**已有 1 檔**是 `reappearance` spell —— 這不是只發生在病理案例上。

**`state_hash` 變更：** `56d42ca0…81f13be` → `d7017180…7fef204`（spell 進入 state）。`config_hash 27fee343…d13f03` 不變。

---

## 5. S-3b = enforcement（裁決 5）

新 blocking requirement `security_status_guard_enforcement`（blocks `S-3b`）。**verifier 實際執行 production guard**，不讀任何 flag、不接受任何 attestation。

| 性質 | 真實證券 | 結果 |
|---|---|---|
| `pit_safe_status_explains` | `4762`（`delisted`，2017-02-20 可得） | `EXPLAINED_SUSPENSION` ✅ |
| `held_unexplained_gap_aborts` | `1107`，持有 | abort ✅ |
| `unheld_unexplained_gap_does_not_abort` | **同一個 observation**，未持有 | 不 abort ✅ |
| `all_routes_invoke_the_guard` | AST | route 呼叫 exposure-scoped guard；**無任何 route module 直接呼叫**未 scoped 版本 ✅ |

fixture `data/b0/s3b_guard_fixture.csv` 由 O-F audit 挑名（非人工 pass list），**不含價格水準、不含選股、不含績效**。

**S-3b 斷言的是「guard 兩側都正確動作」，不是「母體無缺口」，也不是 L2 或 final seal 的許可。**

---

## 6. 回歸

```
unmet_blocking_requirements()   []      (3 requirements, all SATISFIED)
OPEN SPEC ITEMS                 0
specified keys                  98 -> 111
tests                           1857 passed, 2 skipped, 0 failed   (was 1794)
route invariants                G14-4 0 / B-17 0 / B-19 0 / audit-only 0
import-time foreign mutations   0
Frozen A                        七檔未修改;本輪 scripts/ 零檔案異動
spec_sha256 (v1.11)             cd850c001346fe4ff117343c125529556ad1aa4483432b94a026b8430a73b869
```

---

## 7. 產出

| 檔案 | 內容 |
|---|---|
| `core/b0_listing_spell.py` | **新** —— O-G |
| `core/b0_market_state.py` | 事件語義分類表（C-42） |
| `core/b0_pit_observability.py` | `assert_no_unexplained_gap_in_holdings` · `universe_gap_diagnostic` |
| `core/b0_route.py` | exposure-scoped guard · `listing_spells` 入 state · O-G 回看閘 |
| `core/b0_adapter_*.py` | `listing_spells` 欄位 + 非 synthetic 的宣告義務 |
| `core/b0_invariants.py` | `AUDIT_ONLY_*` + entry module 12 |
| `core/b0_frozen_spec.py` | S-3b enforcement requirement + verifier |
| `core/b0_master_prereg.py` | 11 個新 spec key |
| `tests/test_b0_listing_spell.py` | **新** —— 29 tests |
| `tests/test_b0_status_semantics.py` | **新** —— 34 tests |
| `research/of_security_status/build_s3b_fixture.py` | **新** —— 真實資料 fixture 產生器 |
| `data/b0/s3b_guard_fixture.csv` | S-3b fixture |
