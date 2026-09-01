# N-7 · portfolio-side receipt 在 `run_decision` 之前寫出 — 選項書

**狀態（寫定於 2026-09-01）**

```
PRE-RULING · OPTIONS ONLY · 未變更 run_l3_prospective.py 的 receipt 寫出行為
```

基底 `ea491a14`；標的檔 `research/b0_l3_runner/run_l3_prospective.py`（untracked，
來自 `claude/l3-bline-execution-merge`，覆核中，行號請自行複驗）。

---

## 1 · 事實（⟨M⟩ 2026-09-01 本 session 實測）

`write_period_receipts()`（`:709`）在 `main()` 的 **assemble / execute 分岔之前**被呼叫
（呼叫點在分岔上方；execute 分支起於 `# --- execute ---`），並寫死兩個欄位（`:757-759`）：

```python
"decision_layer_invoked": False,
"performance_computed": False,
"evidence_class": "NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED",
```

`l3_snapshot.build_receipt` 的 docstring（`:176-178`）說明 receipt 以 `O_EXCL` 寫出——
「a period is observed once」——⇒ **事後無法更新**。

在一次通過閘門的 execute run 裡：

- 通過 `assert_route_execution_admissible` 依定義代表**確有一枚 seal 內容綁定該路由**；
- 但 `l3_portfolio_side_receipt.json` 仍宣稱 `NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED`；
- 而稍後寫出的 `final_result.json` 記 `decision_layer_invoked: True`。

⇒ **同一次 run 的兩份不可變 artefact，在該 receipt 唯一存在理由的那個問題上互相矛盾。**

### 1.1 兩個減輕因子（也是本文件不逕行修改的理由）

- ⟨M⟩ `evidence_class` 是**字面字串**，無具名常數；全 repo **沒有任何消費者程式化讀取**
  portfolio receipt 的 `evidence_class` 或 `decision_layer_invoked`。
- ⟨M⟩ `portfolio_side_sha256` 雜湊的是 `built["portfolio_side_payload"]`（`:745`），
  **不含**這兩個欄位 ⇒ 改動它們不會移動該雜湊。
- 目前 execute 不可達（A-1 鎖 B），所以此缺陷**尚未發生過**，且將在**第一次真實 execute** 發生。

---

## 2 · 選項

### 選項 7-1 · 由閘門結果導出，不寫死
execute 時把通過閘門的 seal id 記進 receipt，`evidence_class` 依此導出。
- **代價**：receipt 仍在 `run_decision` **之前**寫出 ⇒ `decision_layer_invoked` 只能是
  前瞻宣告（「即將呼叫」），而前瞻宣告正是本專案在 `ROUTE_SEAL_CONTRACT_STATUS` 上踩過的形狀
  （一個沒有任何 `if` 讀它、只用來讓人以為狀態已知的欄位）。
- **需新增一個 evidence_class 值** ⇒ 是契約決定，不是實作細節。

### 選項 7-2 · 兩個欄位移出 portfolio receipt
它們描述的是**整次 run 的結局**，而結局由 `final_result.json` 承載，且該檔在決策之後寫出、
已經帶有這兩個欄位。
- **代價**：`PORTFOLIO_SIDE_CONTRACT_VERSION` 要升 `@1` → `@2`；
  任何以這兩欄位讀 receipt 的人（目前 ⟨M⟩ 為零）須改讀 `final_result.json`。
- **好處**：不新增任何字串值，且讓「哪一份 artefact 回答哪個問題」變成互斥的。

### 選項 7-3 · execute 模式改為在 `run_decision` 之後才寫 receipt
- **代價（最重）**：receipt 目前的 `O_EXCL` 寫出**就是「本期已被觀測」的宣告**。
  移到決策之後，代表 `run_decision` 中途崩潰時**不會留下 receipt**，該期可被重跑——
  這改變 §6.5「a period is observed once」的語意，**是裁決不是修正**。

### 選項 7-4 · 維持現狀，改為明文限定語意
在 receipt 與 docstring 明寫這兩個欄位只描述**portfolio 半邊在寫出當下**的狀態。
- **代價**：矛盾仍在檔案裡，只是附了說明。跨 clone 讀 artefact 的人若不讀 docstring，
  仍會讀到兩份互相矛盾的不可變紀錄——本專案史上四次結論作廢全部沒有報錯，正是這個形狀。

---

## 3 · 本文件沒有做的事

未改 `write_period_receipts`、未改 `PORTFOLIO_SIDE_CONTRACT_VERSION`、
未改任何 receipt 欄位、未跑 `--mode execute`。
