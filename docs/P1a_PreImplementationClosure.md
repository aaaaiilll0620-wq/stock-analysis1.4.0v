# P-1a · Pre-Implementation Closure（O-A ~ O-D）

**日期:** 2026-08-17
**狀態:** `CLOSED` — 四項全關，master prereg 升 v1.1
**合規:** 純規格。**未執行任何報酬 / IC / Sharpe / CAGR / MDD / 選股名單，未動 A0–A3。** Frozen A 七檔未修改（已核對）。未 stage、未 commit。

> **本文件為 rationale / audit trail。規範內容在 `docs/FrozenB0_MasterPreregistration.md` v1.1（§0.1 優先序）。**

---

## 為什麼要有 P-1a

M-3（No specification-by-code）在 v1.0 凍結的那一刻就生效。而 O-B 與 O-D **會直接決定 execution / NAV 語義** —— 先寫 core 再從實作反推規格，正好是 M-3 禁止的那件事。**所以四個 open item 必須先關。**

---

## O-A · corporate-action 守衛接線點 → FROZEN

`corporate_action_transition` 是 **pre-mark mandatory stage**，攜帶兩個守衛：

```
assert_exposure_reconstructible      (W-1 暴露閘)
assert_no_unexplained_price_gap      (O-B 價格缺口守衛)
```

**升級點：** v1.0 只要求「transition 早於 mark」。但**完全跳過該 stage 的執行會 trivially 通過排序檢查** —— 排序擋得住「順序錯了」，擋不住「根本沒做」。v1.1 改為：下游任一 stage（mark / eligibility / features / selection_score / target_portfolio / order_intents / execution / costs / post_trade_nav）出現而 transition 缺席 → abort。

同時把 pipeline 由 9 stage 細分為 11 stage，使其與 §8.7 四層模組責任一對一對應。v1.0 的所有順序約束完整保留為子序列。

---

## O-B · PIT 價格可觀測性 → FROZEN（本輪最重要的一項）

### 被否決的東西

```python
assert_no_unexplained_disappearance(held, last_price_date, explained)
```

`last_price_date` 是 global lookup。站在 2019-05-01 問「這檔股票最後一個交易日是哪天」，**只能用 2019-05-01 之後的資料回答**。

**look-ahead 編碼在簽章本身，所以函式被移除而非修補** —— 留著修補會留下同一個入口。

### 同時放棄的宣稱

**「永久消失」不再是本規格的概念。**

一檔再也不交易的證券，在**第一個缺價日**看起來與明天就復牌的證券完全相同。只有未來資料能分開兩者。B0 因此永不判定「已永久消失」，只判定**「截至今日無法解釋」**，而該判定會隨更多 session 被觀測到而改變。

### 換上的東西

四個 PIT observable，全部以 `as_of` 為界；四態分類：

| 分類 | 可 mark |
|---|---|
| `CURRENT` | ✅ |
| `EXPLAINED_SUSPENSION` | ✅ stale mark，**必須打旗標並計 session 數** |
| `EXPLAINED_CORPORATE_ACTION` | ✅ stale mark，同上 |
| `UNEXPLAINED_GAP` | ❌ **abort** |

**零自由參數。** `STALE_MARK_SESSION_TOLERANCE is None` —— 容忍度就是 W-1 已拒絕的門檻，而且會把一檔消失的持股以舊價 mark 上 N 天還稱之為「已解釋」。**第一個無法解釋的 session 就 abort。**

### 三個設計細節，都是為了堵逃生門

1. **交易日曆也被鎖在 `<= as_of`。** 它是未來可知的，是最容易把未來資訊夾帶進 PIT 計算的入口。
2. **`listed` 不解釋任何缺口。** 否則預設狀態會變成逃生門。
3. **從未有觀測價的持倉一律 `UNEXPLAINED_GAP`。** 任何解釋都無法補上一個從未被觀測到的數字。

### stale mark 是被迫，不是被選

已知停牌的部位不可交易、無市場價格，**最後觀測價是唯一 PIT 可得的數字**（沒有窗口長度可選）。它進 `port_value`（排除它會讓 NAV 往另一個方向錯），但**必須打旗標、計 session 數、列入開封必報項**。

---

## O-C · 312 件無旗標增資 → FROZEN（維持現狀）

**不建推導模型，不以月底登記戳記猜除權日。** 維持 `NOT_RECONSTRUCTIBLE`，暴露時 fail-loud。

理由：已有乾淨處置 —— **事件被辨識到 + 語義不足 + 暴露時 fail-loud = 不會產生錯誤 NAV**。**final seal 不要求把所有歷史事件都變成 reconstructible。** 未來若取得 authoritative source，走 M-2 data repair protocol（獨立來源、不看績效、整類或整來源修）。

---

## O-D · 日內順序 → FROZEN

月頻 decision date 可能落在 corporate-action date 上。**未固定順序時，同一天可以產生不同的 NAV** —— 那是一個穿著實作細節外衣的自由參數。

```
start_of_trading_day
  → apply_known_effective_corporate_actions
  → establish_tradable_holdings
  → obtain_permitted_execution_price
  → execute_child_orders
  → apply_costs
  → end_of_day_state
```

配套兩條：

```
DECISION_STATE_SOURCE       = prior_completed_trading_session
CASH_DIVIDEND_CREDIT_EVENT  = payment_date
```

第一條把 G14-1 對 `σ20D`/`ADV20` 已套用的規則，從逐欄位提升為**對每一個 decision input 都成立的通則**。第二條與「不得預支股利」及 no-leverage 一致。

**執行價格語義不重新創造** —— 沿用既有 `open(t+1)`。O-D 只固定同一天內各效果的先後。

---

## 🔴 本輪產生的新 open item：O-E

**O-B 凍結的是「怎麼判斷」，沒有凍結「狀態與日曆從哪裡來」。**

`known_security_status` 與 `expected_trading_sessions` 目前**沒有資料來源，也沒有驗證過它們自身是否 PIT 正確**。停牌狀態表若本身是當期快照（就像 `industry_map` 那樣），守衛會在不知情的情況下吃進 look-ahead。

**⇒ 在 O-E 關閉前，`assert_no_unexplained_price_gap` 可以被呼叫但沒有真實輸入。** 這不阻擋 P-1b 開工（介面已定），但阻擋 S-3b 轉綠。

---

## 產出與驗證

| 檔案 | 內容 |
|---|---|
| `core/b0_pit_observability.py` | O-B 全部語義 |
| `core/b0_master_prereg.py` | pipeline 細分（O-A）、`INTRADAY_SEQUENCE`（O-D）、新增 9 個 spec key |
| `core/b0_corporate_actions.py` | 移除 `assert_no_unexplained_disappearance`，改指 `HOLDER_SIDE_DETECTOR` |
| `tests/test_b0_pit_observability.py` | 24 項 |
| `tests/test_b0_master_prereg.py` | 59 項（原 39 + O-A/O-D 20） |
| `docs/FrozenB0_MasterPreregistration.md` | v1.1，新增 §2.6 / §6.6，改寫 §2.4 / §6.1 / §8.7 / §12 / §13 |

**變更全部登錄於 master prereg §11：C-9 ~ C-13。**

```
全庫 1546 passed, 2 skipped   (P-1a 前 1504)
Frozen A 七檔 git status 全空
spec_sha256 (v1.1) = ee2b7974ab386082efb46d1a65362e46d5579f2a94b489a2fca454cd7bfdb0c3
```

**下一步：O-E（資料來源）→ P-1b（四層 canonical core）。**
