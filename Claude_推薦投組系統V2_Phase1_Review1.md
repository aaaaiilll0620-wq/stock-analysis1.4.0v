# Claude 任務：V2 Phase 1 Preflight 報告語義修正

只修改：

`docs/盤點_推薦投組系統V2_Phase1_Preflight.md`

不得新增其他檔案、不得重新掃描資料、不得執行fetch/build/API、績效、報酬、IC、Top K、Z1/E1、OOS或Gate；不得stage/commit/push。使用現有盤點證據修正文義即可。

## 1. 拆開兩種狀態

目前報告寫「沒有任何項目BLOCKED」，但同時存在官方產業PIT、真實公告日、L4b帳本等正式研究blocker。這兩者不是同一概念。

每項改成兩欄：

1. `InspectionStatus`：本次是否能完成唯讀查核，只能用：
   - `INSPECTED`
   - `PARTIALLY_INSPECTED`
   - `NOT_INSPECTED`

2. `ResearchReadiness`：是否足以進入正式規格／驗證，只能用：
   - `READY`
   - `PARTIAL`
   - `MISSING`
   - `BLOCKED`
   - `UNVERIFIED`

不得再使用`CONFIRMED MISSING`、`AVAILABLE/PARTIAL`等混合狀態值。報告結論需明說：

> 本次preflight查核本身沒有被技術阻擋，不代表各研究層沒有readiness blocker。

## 2. 校正主要readiness blocker

依現有證據至少標記：

- L1財務：固定`PUBLISH_LAG_DAYS=45`不是實際公告日PIT；在取得公告日或凍結並證明安全的保守可用規則前，正式財務驗證為`BLOCKED`，不能只寫一般PARTIAL。
- L2官方產業：無有效日期／歷史版本，依D3為`BLOCKED`。
- 題材標籤：完全不存在，為`MISSING`；若正式策略要求題材層，該層驗證因此`BLOCKED`。
- ReentryContext/L5：trade id、receipt、P0/S0/R0、最後停損與position history缺失，為`MISSING`；Z1-R／E1-R正式驗證`BLOCKED`。
- L4b：漲跌停、零股、partial fill、持久化ExecutionLedger與精確公司行動資料不足，正式可執行回測`BLOCKED`。
- L6a：個股事件資料源不存在，為`MISSING`；若啟用重大事件強制退出，正式驗證`BLOCKED`。
- 權威交易日曆：不存在，為`MISSING`；涉及T+1、停牌／颱風假的正式執行模擬`BLOCKED`。
- Validation access guard：只有manifest先例，沒有append-only receipt，為`PARTIAL`；進Validation前`BLOCKED`，但不阻擋Phase 2設計。

若某模組可在MVP明確禁用，必須寫成「禁用後其他層可繼續設計」，不得把缺失模組假裝READY。

## 3. 新增Readiness Summary

在結論加入：

| 層／能力 | InspectionStatus | ResearchReadiness | 是否阻擋Phase 2設計 | 是否阻擋正式Validation | 解鎖條件 |
|---|---|---|---|---|---|

明確區分：

- Phase 2可以先設計schema／政策的項目；
- 必須取得資料後才能凍結或驗證的項目；
- 可暫時禁用以形成MVP的項目。

`overall=PARTIAL`可以保留，但需附：

```text
PreflightExecution = PASS
ResearchReadiness = PARTIAL_WITH_BLOCKERS
```

## 4. 新增TEJ／本地資料取得清單

只依語意列必要欄位，不得捏造未核對的TEJ正式欄位名稱：

| 優先級 | 資料集語意 | 必要鍵 | 必要PIT時間欄位 | 必要內容 | 解鎖模組 | 可否以現有資料替代 |
|---|---|---|---|---|---|---|

至少包含：

1. 財報實際公告／可得日期。
2. 股票產業分類歷史與分類生效／失效日期。
3. 處置、注意、全額交割、停止交易等個股事件及市場可得時間。
4. 官方交易日曆、停牌／恢復交易資訊。
5. 每日漲跌停理論價或可重建欄位。
6. 股票交易單位與變更歷史、零股可交易資訊。
7. 除權息、減資、分割／合併及生效日。
8. 手續費／交易稅屬政策常數，不要誤列為必須由TEJ提供。

使用者另有消息專案仍只列external dependency，不得跨專案讀取。

## 5. 報告限制

- 不因資料存在而宣稱策略有效。
- 不因資料缺失而修改U1–U11政策值。
- 不計算任何報酬或訊號。
- 不解除Gate 2或C3限制。

## 回覆格式

只在對話回覆：修改行號、`PreflightExecution`、`ResearchReadiness`、readiness blocker數量、最高優先取得的三類資料、本輪實際寫入路徑與path-scoped status。不要貼全文。
