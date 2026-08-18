# Claude 任務：V2 Phase 0 單檔基線 commit＋Phase 1 Preflight

本任務分成兩個硬檢查點。Checkpoint A 未完整成功時，立即停止，不得開始 Checkpoint B。

先讀：

- `AGENTS.md`
- `docs/研究紀律_ResearchDiscipline.md`
- `docs/規劃_推薦投組系統V2.md`

不得修改或寫入任何 Claude 任務檔、`GPT answer.md`、Gate 1／Gate 2／C3／D2產物、既有core/scripts/tests/results。不得執行績效、報酬、回測、訊號生成、OOS、calibration、timing、synthetic、Gate或push。

## Checkpoint A：補登U11並只commit Phase 0草案

唯一允許修改：

`docs/規劃_推薦投組系統V2.md`

### A1. 補登U11

在Decision Register的UNRESOLVED新增：

> **U11**：若母交易由`Z1-R`重新進場，後續加碼的「同原始模式」如何解釋：是否仍需另一個Z1-R、改以新`Z1-P/Z1-B`結構，或另訂re-entry trade的加碼資格。Phase 0不代為決定；Phase 2前須凍結。未解決前不得把「Z1-R母交易可依Z1-R加碼」寫成既定規則。

同步修正§7.2中把`Z1-P/Z1-B/Z1-R`一體列為「同原始模式加碼」的文字：

- Z1-P母交易：加碼候選仍須新Z1-P結構。
- Z1-B母交易：加碼候選仍須新Z1-B結構。
- Z1-R母交易：依U11，暂不定義加碼模式。

不得改其他政策值。

### A2. 單檔stage與commit

1. 修改前後記錄該檔SHA-256、長度與mtime。
2. 完整執行`git status --short`，確認其他髒檔均為既有內容；髒worktree不阻止精確單檔commit。
3. 只執行：

   ```text
   git add -- "docs/規劃_推薦投組系統V2.md"
   ```

   禁止`git add .`、`git add -A`或任何glob。
4. commit前必須以`git diff --cached --name-only`與`git diff --cached --stat`確認cached範圍只有這一檔；若多出任何檔案，fail-closed停止，不得commit。
5. commit message：

   ```text
   docs: baseline portfolio recommendation v2 phase 0
   ```

6. commit後回查：

   - 完整commit hash；
   - `git show --stat --oneline HEAD`；
   - `git diff HEAD^ HEAD --name-only`只能有目標檔；
   - `git show HEAD:"docs/規劃_推薦投組系統V2.md"`對應內容hash須與工作樹目標檔一致。

任何一步失敗即停止，不得開始Phase 1。

## Checkpoint B：Phase 1唯讀資料preflight

Checkpoint A通過後才開始。本輪Phase 1只允許：

- 讀取程式、schema、既有本地資料與metadata；
- 計算row count、欄位清單、資料型別、最早／最晚日期、PIT欄位存在性、缺值數／比例及鍵唯一性；
- 查核資料入口與血緣；
- 撰寫一份新的未追蹤報告。

唯一允許新增的Phase 1檔案：

`docs/盤點_推薦投組系統V2_Phase1_Preflight.md`

除該報告外不得寫入任何cache、CSV、JSON、parquet、results或暫存研究產物；若工具預設會寫cache，先停下，不得執行。

### B1. 盤點表格式

逐項列：

| 模組 | 必要資料 | 現有來源／路徑 | schema／鍵 | PIT時間欄位 | 覆蓋起訖 | 缺值／唯一性 | 狀態 | blocker／下一步 |
|---|---|---|---|---|---|---|---|---|

狀態只能用：`AVAILABLE / PARTIAL / MISSING / UNVERIFIED / BLOCKED`。

### B2. 必查模組

1. **L1選股本體**：PIT財務、估值、籌碼、技術及現有`real_composite`真身入口；只查schema與血緣，不重算分數。
2. **L2官方產業PIT**：是否存在歷史成員／分類變更日期、`effective_from/effective_to/as_of`；若只有今日分類，保持D3 blocker。
3. **題材標籤PIT**：現況是否存在；沒有就記MISSING，不臨時創建今日題材名單回填歷史。
4. **資料驅動相關群組**：確認日報酬／價格來源、可用起訖與鍵；不計算相關係數、不聚類。
5. **L3進場資料**：OHLC、ATR所需欄位、MA／POC候選來源、交易日曆；只查可用性，不生成Z1訊號。
6. **ReentryContext／L5**：現有資料能否重建trade id、實際退出成交、退出原因、P0/S0/R0、最後停損與交易歷史；不存在就列schema gap。
7. **L4b執行模擬**：open/high/low/close、成交量／成交值、漲跌停、交易單位／零股、除權息／拆併股、手續費／稅、部分成交所需欄位。
8. **L6a重大事件**：本repo內是否存在具有PIT可用時間的個股事件來源。使用者另有消息專案，但未授權跨專案讀取；只記external dependency，不自行存取。
9. **L6b市場狀態**：市場指數、廣度候選、交易日曆及現有regime介面；不得計算overlay績效。
10. **DecisionClock／Validation guard**：現有程式是否能保存`as_of/generated_at/valid_from/valid_until/source_snapshot_hash`；是否已有append-only access receipt能力。

### B3. 強制研究邊界

- 不得讀取或計算任何候選投組的未來報酬。
- 不得計算CAGR、Sharpe、MDD、勝率、IC、alpha或任何績效指標。
- 不得產生Top K、Z1／E1訊號、族群狀態、相關群組或投組建議。
- 不得把`obs_alpha.fwd`當報酬線；本輪甚至不需要讀報酬值。只記正式未來若進入驗證必須使用`exec_ret.fwd_x`。
- 不得解除Gate 2 preflight或宣稱C3可部署。
- 任一查核需要寫cache、繞過raise、使用非PIT替代物或跨專案存取時，標為BLOCKED並停止該項，不得繞過。

### B4. 報告結論限制

報告只能回答「資料是否存在、是否PIT、是否足以進入Phase 2規格設計」。不得回答任何策略是否有效。

報告末尾必須列：

- `Phase 1 preflight overall = PASS / PARTIAL / FAIL-CLOSED`；
- 各blocker對應到哪一層；
- U1–U11哪些可由資料盤點縮小選項、哪些仍需使用者政策決定；
- 明確聲明未執行任何績效／OOS／Gate。

## 回覆格式

只在對話回覆，不寫入任務檔：

1. Checkpoint A：commit hash、cached範圍證據、`git show --stat`。
2. Checkpoint B：報告路徑、overall狀態、AVAILABLE／PARTIAL／MISSING／BLOCKED數量。
3. 最重要的五個blocker或schema gap。
4. 本輪實際寫入路徑。
5. 完整`git status --short`摘要；若只顯示path-scoped輸出，必須明說。

不要貼完整報告內容。
