# 給 Codex 的覆核指示 · L3 v1.38（2026-08-31）

> 這份檔案是 prompt。把它整份交給 Codex，它應該不需要再問任何背景問題就能開工。

---

## 0 · 你這次的角色，以及為什麼是反過來的

`AGENTS.md` 平常定 Claude = 執行官、Codex = 審查官。**過去三輪是反的：**
L3 的 decision-intent / execution 拆分是**你**寫的，Claude 覆核並修正。理由是作者不能覆核自己，
且當時你已無額度。

**這一輪換回來，但標的是「Claude 對你的程式所做的覆核與修正」。**
也就是說：你不是在覆核自己原本的設計，你是在覆核**別人怎麼改它**。
你原本的核心拆分被判定為對的（見下方「已驗證」），被否決的是三個具體缺陷加七項 serious。

⚠ **C-72 前例仍然有效：** 覆核未過就落地會被判
`LANDED_BEFORE_REQUIRED_REVIEW + REVISION_REQUIRED` 並整包 revert。
所以下面的兩項任務，**都不包含落地**。

---

## 1 · 位置與狀態

```
worktree   C:\Users\aaaai\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\work\l3_formal_v138
branch     codex/l3-september-readiness
base       216d62db   Frozen B0 Master v1.37
HEAD       93e928e4
tree       clean
```

要覆核的六個 commit：

```
0ff279e6  R1   三個致命缺陷 + adapter 層的第二份認證
3b6e8bd4  R2   兩份新匯出的宣告、四道閘門、CA 洞、順序測試
e13c512e  R3a  S-1 S-2 S-4 S-5 S-6 A-4 S-7
5dbe47f2  R3b  S-8 S-9
9c63a5ba / 39218cda / 93e928e4   三份文件
```

先讀這兩份，它們是自足的：

```
docs/L3_v138_WorkList_2026-08-30.md            三輪的完整紀錄，含每項的 file:line
docs/L3_v138_AdjudicationOptions_2026-08-31.md 九項裁決選項
```

**未發生**：版本升級、freeze 變更、lineage capture、route seal、decision observation、任何績效量。
`ROUTE_SEAL_CONTRACT_STATUS` 仍是 `NOT_YET_RATIFIED`，`PRODUCTION_RUN` 仍被 pin 漂移擋著。

---

## 2 · 開工前必須知道的環境事實（不知道會浪費你半天）

1. **canonical 套件在這棵 worktree 不可能全綠，這不是缺陷。**
   實測 `3030 passed / 47 skipped / 14 failed`，**真實失敗 0 個**。13 個缺這棵樹沒有的未受版控
   fixture（`outputs/universe_pool/c2_fullpool_*.csv`、`beat_0050/data/benchmark/0050_tr.parquet`、
   `artifacts/` 只有 3 個子目錄），第 14 個 `test_repo_tree_cleanliness` 只是斷言那 13 個要過。
   **不要為了追它們改測試。**
2. **不要在這棵樹上跑會改動工作樹的 git 指令。** 8/31 有一個並行代理跑了 `git stash push -u`，
   把三份未 commit 的工作一起收走（損害為零，但那是運氣）。禁用：`stash` / `checkout --` /
   `restore` / `reset` / `clean`。要 pristine 副本一律 `git show HEAD:<path>` 導到樹外。
   `stash@{0}` 仍留在分支上，內容已被工作樹超越，未 drop。
3. **`git checkout --` 在這棵樹會把 CRLF 寫回檔案**，即使 `.gitattributes` 對 repo 與工作樹
   都宣告 LF（`core.autocrlf=true` 勝出）。這正是 C-47 遷移帳本在管的東西。
4. **首次 build 會多花約 22 秒**做 S-9 的 span 驗證（同行程後續 1.6 秒）。不是卡住。
5. 用 `PYTHONIOENCODING=utf-8`，主控台是 cp950。

---

## 3 · 任務一 · 覆核那 5,400 餘行修改

**這是「這些修正對不對」，不是「接下來怎麼走」。兩者不要混。**
（C-72 那次就是覆核意見與設計意見糾纏，導致重來。）

### 3.1 用這個標準

本專案最貴的 bug 不是會 crash 的那種，是**數字看起來正常但對照組已經換了**那種——
五次結論作廢全部沒有報錯。所以每個 hunk 都問：
**這個數字的對照組是什麼？報酬線是哪一條？母體有沒有被靜默砍過？**

### 3.2 優先看這五個地方（它們是設計決定，不是機械修正）

| # | 標的 | 要問什麼 |
|---|---|---|
| 1 | **S-2 的基準來源** `run_l3_prospective.py` | 基準是「前一次 run 自己的 manifest」，由 `--prior-source-manifest` **明示指定**而非自動發現，理由是「猜出來的基準可以被猜成通過」。首跑須明示 `--no-prior-source-manifest` 且**限 GENESIS**。這個設計對不對？操作者提供基準，單次 run 內無法分辨「錯得合理」的前身——工作單 N-4 已記錄，綁到 `--producer-run-id` 可關閉但那是裁決。你同意這個切法嗎？ |
| 2 | **S-8 的 allowance 機制** `build_prices_leaf.py` | allowance 鍵為 `(locator, contract.content_sha256)` 而非合約名稱；`condition` 取自單一成員封閉詞彙，**每次 build 對當下 panel end 重驗**。`panel_span()` 的尾端因此被移進 leaf 模組以免新增 capture closure 外的相依。這個移動合理嗎？有沒有更小的做法？ |
| 3 | **A-4 的詞彙套用** `build_flat_leaves.py` | 沿用引擎既有的 `SOURCE_FAMILIES` / `AUTHORITY_LEVELS`，calendar 改標 `LIVE/SUPPLEMENTARY`。**這暴露了 N-1：日曆沒有權威腿。** 修正本身有沒有做出任何未經裁決的新決定？ |
| 4 | **A-9 的 CA 延遲** `core/b0_corporate_actions.py`（pinned 規範模組） | `_first_session_on_or_after` 宣稱逐位元未動、延遲需明示宣告且該宣告會被對照日曆檢查。請獨立驗證這兩點，並確認一般（非 intent）路徑真的沒被移動。 |
| 5 | **B1 的 COMPARED / RECORDED 切分** `run_l3_prospective.py` | 17 個比較欄位、`market_state_sha256` 移入 recorded。逐欄位重新審一次「依構造相位不變」——原覆核已列出一張表，請不要照抄，請自己重推。`commit_sha` / `harness_sha256` 被判「非相位不變但 fail-closed 且有補救」而保留在比較集合，這個判斷你同意嗎？ |

### 3.3 我方已知的弱點（請優先攻擊這些，不要客氣）

- **`decision_cutoff_state_sha256` 的相位不變性尚未在真實九族 fixture 上量過**，目前是程式碼推理
  + 合成資料。工作單 §5 明列「route 被 seal 之前必須補一組真實 intent→execute 配對」。
- **S-9 是 span 檢查不是完整性檢查**：span 內部缺 session、roster 缺口、錯的 `leg`、任何數值皆抓不到。
- **N-2**：prices leaf payload 現在還相依於 `data/b0/trading_calendar.csv` 與
  `price_source_contract.json` 兩個**資料**檔，兩者都不在 `FLOOR_CAPTURE_CODE_CLOSURE`（那是程式閉包）。
- **N-3**：`build_price_panel.main()` 本體從未被執行（它會寫 `data/b0/`）。
- **N-5**：`build_period(cohort_id="")` + GENESIS 會跳過 checkpoint 的 cohort 檢查；
  `main()` 一律具名，但 `tests/test_b0_l3_runner_end_to_end.py` 正是直接呼叫。
- **五個以上 pinned 規範模組相對 v1.37 漂移**。這是升版進行中的預期狀態，但請確認漂移範圍與宣稱一致。

### 3.4 突變檢驗

各輪宣稱做了突變檢驗（改壞就紅）。**請抽驗至少三個**，自己動手改壞再跑，確認測試真的會抓到。
特別建議抽：S-8 的 allowance 缺失分支、S-2 的逐 family 呼叫、B1 的負向參數化案例。

### 3.5 任務一的產出

```
VERDICT            APPROVE / APPROVE_WITH_CONDITIONS / REVISION_REQUIRED / REJECT
逐項                 對 3.2 五個標的各給結論
新發現的缺陷          severity | file:line | 一句話 | 具體失效情境（輸入 → 錯誤輸出）
被我方誤判的          我方判為已修但其實沒修、或修錯方向的
突變抽驗結果          你改了什麼、紅了沒有
```

**不要落地任何修正。** 發現缺陷就報，由使用者決定誰修。

---

## 4 · 任務二 · 九項裁決建議

讀 `docs/L3_v138_AdjudicationOptions_2026-08-31.md`。九項是
A-1 A-2 A-3 A-5 A-6 A-7 A-8 A-9 N-1。

### 4.1 規則

- **判準必須是條款層的。不得引用任何績效數值。** 該文件 §0 有撰稿者揭露，請比照辦理：
  若你在覆核過程中觀測到任何 NAV / 報酬 / 名單，請在產出中揭露。
- 選項全部保留，不要刪。你可以**新增**選項——原作者不一定窮舉了。
- 對每一項給：你選哪個、**為什麼另外幾個不行**、以及採納後**最先會壞的地方**。

### 4.2 特別要你回答的三題

1. **§0.1 的根因判斷對不對？** 文件主張 A-8 / N-1 / A-3 是同一件事：九族混了「有 vintage 的
   匯出」與「每日改寫的即時快取」，而日曆屬於後者卻決定 `as_of` 與執行 session。
   若你認為這個歸納錯了，請說錯在哪——**後面的裁決順序建議整個建立在它上面。**
2. **A-1-丙 與 N-1-甲 被標為「看起來保守、實則實質放棄」。** 你同意這個標示嗎？
   特別是 A-1-丙：L2 已結案且額度消耗，若 L3 永不封印，Frozen B0 是否真的沒有證據線了？
3. **A-9 被明文標為「不應在量測前拍板」**（偏好解取決於 `portfolio_side_payload` 含不含 snap 後的
   釋放時點，該事實未量）。**請你直接把它量掉**，然後再給裁決建議。這是本文件唯一要求你動手量的。

### 4.3 任務二的產出

```
根因判斷            同意 / 不同意 + 理由
逐項                 選項 | 理由 | 被否決的選項為何不行 | 採納後最先壞的地方
A-9                 你的量測結果，以及據此的建議
新增選項            若有
裁決順序            同意文件 §10 的順序，或提出你的
```

---

## 5 · 兩件明確不在範圍內

1. **不要升版號、不要動 `research/b0_registry/master_prereg_freeze.json`、不要取 seal、
   不要建 lineage、不要跑 production run。** 那些要等這兩份覆核都過，且使用者另行授權。
2. **U-5（未來以自動抓取為主、手動為輔）不在本次範圍。** 它與 R-W1-2 方向相反，
   前置是 W1-b + A-6 + A-7 + N-1，見工作單 §6。如果你在覆核時有意見，記在產出末尾即可。

---

## 6 · 已驗證、不需要你重做的

省你的時間。這些是實測結果，附證據位置：

- **你的核心拆分是對的。** `build_decision_intent()` 確實是唯一的計分／排序／選股路徑
  （全樹 grep 過所有可能的第二實作），`run_decision()` 沒有重算任何東西。
- **2026-03 決策路徑逐位元 parity 已獨立重現**：把 `core/` 影子回 `216d62db` 跑同一 fixture，
  `rows_sha 86557d7b…`、`state_hash 70203722…` 相符。
  **但 run 寫出的 artefact 不 parity**（receipt 增欄），兩者要分開講。
- **月營收接上後的實測**：`read_revenue` 回 202607 共 2,002 檔、`3003 = 657,875,000`
  （archive 的修訂值贏過 workbook 的 658,000）——所有權宣告確實在決定勝負，不是 concat 順序。
- **C-71 條款的逐檔比對**（2026-08-31）：價格腿 `41ef1cce…` / `049881046…` 與 A01 **完全相同**；
  日曆腿 `93191aab…` → `0a487260…` **已變**。
- **CA ledger 非交易日 credit date**：46,433 列中，日曆區間內 `credit_tradable_date` 23 筆、
  `cash_payment_date` 1 筆。

## 7 · 一份已作廢的東西

`work/l3_p0_probes/L3_P1_DRY_RUN_20260830.md` 裡那三個 payload sha256 **不是證據**：
來自帶 tempdir 路徑的 validation leaf（不可跨 run／clone 比對），且 staging 樹已被當時的
`finally: rmtree` 刪除、無法回溯到檔案。**引用該 dry run 的任何數字前先讀工作單 §9。**
（那個 `finally` 已在 R2 修掉，失敗現在會保全證據。）
