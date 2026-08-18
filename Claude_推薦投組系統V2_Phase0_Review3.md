# Claude 任務：推薦投組系統 V2 · Phase 0 收尾修正

只修改 `docs/規劃_推薦投組系統V2.md`。不得修改任何任務檔或其他檔案；不得執行 Phase 1、回測、績效、OOS、Gate、stage、commit、push。完成後只在對話回覆。

上一輪六項修正大致正確，但尚有以下會直接改變交易結果的缺口。

## 1. L4裁決不等於成交

目前 §2.0／§2.2 寫成 L4 裁決後正式觸發 `PositionState`，但 §3.3 又正確寫著部位狀態由成交回報驅動，兩者矛盾。

在不增加第八層的前提下，將 L4 明確拆成兩個子介面：

- `L4a PortfolioDecisionEngine`：統整 L3候選、L5提案、L2/L6限制，產生 `OrderIntent`／目標權重；不能改寫 `PositionState`。
- `L4b ExecutionLedger`：依凍結的 T+1、價格區間、跳空、滑價、交易成本、零股限制、部分成交／未成交規則模擬執行；只有成交或可驗證的 execution receipt 才能更新 `PositionState`、成本、現金與持股。

至少區分：

```text
candidate/proposal → OrderIntent → submitted/pending → partial/filled/cancelled/rejected
```

- `pending_exit` 是執行狀態，不應與 L5 的 `exit proposal` 混為同一層。
- 強制退出可突破換手上限，但 L4a 不得因換手、產業上限或「沒有替代股」否決賣出；若無法成交，只能由 L4b 記為 pending／partial 並保留風險。
- 無券商 API 不代表可以省略 execution ledger；V2回測仍需要它。

同步修正 §2、§3.3、§6.3、§7、§8、§9、§10與Decision Register。

## 2. 補齊L5輸入並清理E1-R殘留

E0明定可能因排名、基本面、結構與重大事件退出，但目前L5輸入表只有部位／趨勢／L6a，資料流不完整。L5至少要接收：

- 當期有效的L1資格／排名狀態；
- PIT基本面惡化旗標；
- 個股價格結構與停損狀態；
- L6a重大事件旗標；
- 現有部位與交易歷史。

並清除以下語義：

- 不要再稱「`E0/E1/E1-R`都是L5產生提案的政策」。
- L5只有E0或E1退出政策；E1-R純粹是實驗組態標籤`E1 exit + Z1-R re-entry`。
- `Z1-R`由L3產生，重進仍經L4a裁決及L4b成交。

## 3. 新增決策時鐘與訊號有效期（UNRESOLVED）

目前只有「月頻選股、週頻複核、日頻進出場」一句話，尚不足以讓L4重現某一天的決策。新增一節 `DecisionClock`，先列介面與未決項，不自行定參數：

- 月頻：何時凍結正式候選池／排名、有效到何時。
- 週頻：哪些欄位重算；能否正常換股，或只能調整風險／觀察狀態。
- 日頻：進場區間、停損、重大事件、pending order何時更新。
- 每個訊號必須有 `as_of`、`generated_at`、`valid_from`、`valid_until`、`source_snapshot_hash`。
- L4a同一決策時點遇到月／週／日訊號衝突時的優先序。
- T收盤訊號最早T+1執行；不得讓月頻排名被日後資料回填。

將具體重算時點、有效期與衝突規則新增為 `UNRESOLVED U7`，Phase 2前必須凍結。

## 4. 補上既定加碼預備金語義

草案只寫總預備金10%，漏掉已討論的個股隔離語義。補登：

- 不得對虧損部位攤平。
- `+1R`只開啟資格，不自動保本。
- 加碼須同原始進場模式的新結構、價格高於原平均成本、共同停損下計畫淨損益不低於0。
- 10%預備金按合格持股分配為每檔獨立額度，股票間不得挪用；每檔每月最多一次。

但「分母N取月初目標持股數、實際持股數或其他定義」尚未明確，新增 `UNRESOLVED U8`，不得自行選擇。

另明確說明：90%股票部位是目標上限而非必須填滿。若N太少、單股35%或產業50%限制使90%無法配置，剩餘維持現金，不得突破硬上限或塞入不合格股票。

## 5. 強化Validation首次存取證據

`TRAIN_SELECTION_MANIFEST` 的時間早於Validation首次讀取，只能檢查已記錄的讀取，不能單獨證明資料從未提前被看過。Phase 0不要宣稱它能完全證明盲性。

補列Phase 2／4／5候選要求：

- Validation資料入口必須由guard控制，runner不得繞過。
- 第一次開啟時留下append-only access receipt，包含manifest hash、程式hash、資料snapshot hash、時間與操作者／run id。
- preflight同時核對selection manifest與first-access receipt。
- 人工或其他未受控路徑曾提前讀取Validation時，fail-closed；處置須事前定義。
- 以上schema與實際封存機制列為 `UNRESOLVED U9`，不得在Phase 0宣稱已完成。

## 6. 修正git狀態與血緣措辭

Claude上一輪回覆標示為`git status --short`，但內容不是完整worktree狀態；實際完整狀態仍含多個`core/`、`beat_0050/`、scripts、tests與results既有變更。

本輪回覆必須：

- 說明執行的是完整或限定路徑的status，不得把限定路徑輸出標成完整`git status --short`。
- untracked檔無基準diff，status無法證明「只修改一檔」。
- 另列本輪實際寫入路徑與目標檔修改後mtime；不得宣稱mtime本身是內容未變的密碼學證據。

## 完成自查

1. L4a決策與L4b成交分開，PositionState只因fill／receipt更新。
2. 強制退出不會被投組限制否決；未成交會留下pending風險。
3. L5輸入足以支援E0的排名／基本面／結構／事件退出。
4. E1-R不再被稱為L5政策或訊號。
5. 新增U7決策時鐘、U8加碼N定義、U9 Validation access guard。
6. 90%無法合法配置時保留現金。
7. 未執行Phase 1或任何績效工作。
8. 只修改指定草案，回覆清楚區分完整status與path-scoped status。

完成後只回：修改行號、8項PASS/FAIL、新增UNRESOLVED、完整status摘要、實際寫入路徑。不要貼全文。
