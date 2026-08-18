# Claude 任務：推薦投組系統 V2 · Phase 0 最終介面修正

只修改 `docs/規劃_推薦投組系統V2.md`；不得修改其他檔案、不得執行 Phase 1／回測／績效／OOS／Gate／stage／commit／push。

## 問題 1：Z1-R 缺少必要輸入

§2.2 現在把 L3 輸入寫成「L1排名＋價格結構」，但 `Z1-R` 不可能只靠這些資料判定；它必須知道前次交易是否真的因 E1 成交退出、退出時間與舊交易風險結構。

將 L3 介面拆成：

- `Z1-P/Z1-B`：L1有效資格／排名＋PIT個股價格結構。
- `Z1-R`：以上資料＋只讀的 `ReentryContext`。

`ReentryContext` 至少列候選欄位：

- 前次 `trade_id`、退出政策與退出原因；
- L4b實際退出成交時間／價格／execution receipt；
- 舊交易 `P0/S0/R0` 與最後有效停損；
- 當前`PositionState`及是否仍在重進觀察期；
- 未解除的個股事件禁止旗標。

只有「前次退出已由L4b確認成交」且退出原因符合凍結的Z1-R資格，才能建立`ReentryContext`。排名淘汰、基本面惡化、重大事件強制退出是否永久／限期禁止重進，留給U6／Z1-R預註冊，不得在Phase 0自行決定。

具體欄位schema、可接受退出原因、觀察期限與失效條件新增為`UNRESOLVED U10`。

## 問題 2：block_reentry_flag 路由錯誤

目前L6a把`block_reentry_flag`送到L5，但L5只處理既有部位的退出提案，無法阻止L3候選經L4a重新進場。

修正權限：

- `L6a forced_exit_flag → L5`：使既有部位產生強制退出提案。
- `L6a block_entry_or_reentry_flag → L4a`：作為個股層級的硬資格否決，阻止任何新倉／重進`OrderIntent`。
- L6a仍不得改寫L1評分、L3原始訊號、`TrendState`或`PositionState`。
- 為保持訊號增益可分離，L3仍可產生原始Z1-R候選；L4a必須明確記錄「因事件旗標否決」，不得靜默刪除。
- L6b市場overlay權限不變，仍只能控制總曝險／現金／新倉與加碼，不得觸發個股退出。

同步修正§2.1、§2.2、§3.3、§6.1、§6.3、§8、§11 F18/F24及相關表格。

## 問題 3：E1-R組態資格

明確寫出：

- `E1-R`仍只是實驗組態標籤。
- 它不表示所有E1退出都必然允許Z1-R。
- Z1-R是否合格由凍結的`ReentryContext`資格規則判定；L6a禁止旗標可在L4a否決重進。

## 自查

1. L3的Z1-R輸入包含已成交的前次交易脈絡，不再只靠價格。
2. `block_entry_or_reentry_flag`實際到達L4a，且是可稽核的硬否決。
3. `forced_exit_flag`仍只經L5產生退出提案，再由L4a產生不可否決的OrderIntent、L4b模擬成交。
4. L3原始訊號未被L6a改寫，事件限制與訊號本體仍可分開驗證。
5. 新增U10，U1–U9不關閉。
6. 未執行Phase 1，只修改指定草案。

完成後只在對話回覆修改行號、6項PASS/FAIL、U1–U10狀態、完整status摘要與實際寫入路徑；不要貼全文。
