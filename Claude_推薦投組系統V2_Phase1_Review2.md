# Claude 任務：V2 Phase 1 Preflight 證據強度校正

只修改 `docs/盤點_推薦投組系統V2_Phase1_Preflight.md`。不得重新掃描／讀取資料、不得新增檔案、不得執行任何績效／報酬／訊號／OOS／Gate、不得stage/commit/push。只根據報告中已記錄的證據校正狀態。

## 問題

報告已正確拆出`InspectionStatus`與`ResearchReadiness`，但多個「只抽樣1檔／5檔、只看程式碼或只確認檔案存在」的項目被標成`READY`。這最多證明schema／介面可能可用，不能證明全市場正式驗證所需的覆蓋率、鍵唯一性與缺值條件。

## 必修1：新增EvidenceScope

每個盤點表新增`EvidenceScope`，只能用以下原子值：

- `FULL_CONTENT`：完整讀取並驗證該資料集。
- `SAMPLE_N=<整數>`：只抽樣N檔／N列；在備註說明抽樣單位。
- `CODE_ONLY`：只讀程式碼，未驗資料內容。
- `EXISTS_ONLY`：只確認路徑／檔案存在。
- `METADATA_ONLY`：只讀shape、schema、mtime、欄名等metadata。

不得把多個值用斜線混在同一欄；需要時拆列。

## 必修2：READY的最低語義

`ResearchReadiness=READY`只表示「依目前證據，該項已足以進入其聲稱範圍的正式驗證」。因此：

- 若聲稱全市場可用，但只`SAMPLE_N=1`或`SAMPLE_N=5`，改為`UNVERIFIED`或`PARTIAL`。
- 只`CODE_ONLY`不能證明資料內容READY；介面可另列一行READY，資料內容列UNVERIFIED/MISSING。
- 只`EXISTS_ONLY`不能標READY。
- 若完整檔案已讀取並驗證鍵／缺值，可保留READY，但要明寫驗證範圍。

不得在狀態欄加入括號說明或`READY/PARTIAL`混合值；每列只能有一個合法狀態，複合項目拆列。

## 必修3：至少修正以下項目

1. 估值、籌碼、技術OHLC、ATR、MA、POC：只抽樣單股，不能宣稱全市場READY；介面存在與全市場資料完整性拆開。
2. `obs_alpha/exec_ret`：僅讀shape/schema、未逐欄缺值與鍵驗證，資料內容不得標READY；唯一入口／正式欄位存在可另列。
3. 資料驅動相關群組主來源：僅抽樣5檔，維持PARTIAL/UNVERIFIED。
4. L4b的`OHLCV+成交值`：FinMind只有77檔，TEJ來源又缺成交值，不能標成全市場READY；改為PARTIAL，正式全市場執行仍BLOCKED。
5. `adv20`：只確認欄位存在，不等於全期全股coverage已驗證；欄位schema可READY，內容coverage須UNVERIFIED。
6. L6b等權指數：只讀程式介面、未驗底層全市場內容，不得把資料內容標READY；介面與資料拆列。
7. `real_composite`完整讀取、鍵唯一與指定欄位0 null已有明確全檔證據，可在該明確範圍保留READY；不得延伸成五維度定義已修好或V2已可驗證。

## 必修4：修正Readiness Summary

彙總表不能在同一格寫`READY(...)/PARTIAL(...)`。每層以最弱必要元件決定整體readiness，另在備註列出已ready子項。例如：

- L3原始技術欄位若只有單股抽樣，整體應為`UNVERIFIED`，不是READY。
- L4b因必要元件缺失，整體維持`BLOCKED`。
- L1因正式財務PIT blocker，整體維持`BLOCKED`；其他子項可在備註列出。

更新：

```text
PreflightExecution = PASS
ResearchReadiness = PARTIAL_WITH_BLOCKERS
```

這兩行可維持，但新增一句：目前沒有任何策略層因抽樣schema檢查而被宣稱為全面READY。

## 必修5：禁止新增推論

- 不新增任何未從既有報告證據得到的row count、coverage或缺值結論。
- 不重新讀取資料補證據。
- 不計算績效或訊號。
- 不關閉U1–U11。

## 回覆格式

只在對話回覆：修改行號、降級為UNVERIFIED/PARTIAL的項目、保留READY的完整證據項目、整體兩行狀態、本輪唯一寫入路徑與path-scoped status。不要貼全文。
