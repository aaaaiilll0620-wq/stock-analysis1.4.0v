Reading Codex's review and the task file — Codex flagged 7 substantive design issues plus rulings on the four open gaps. I'll fix the draft accordingly, staying within the "只新增一個未追蹤草案" constraint (editing the same file, not touching anything else).

Now fixing E0's definition and the Z1-R/E1-R duplication (points 3 & 4):

Now fixing §8's oversimplified web state mapping (point 5):

Now restructuring the roadmap into 7 explicit phases (point 6) and fixing the TOC:

Now updating §5's PIT note and the Decision Register (point 7 — missing CAGR/Sharpe/MDD, and the four rulings):

A few residual inconsistencies to clean up — a leftover "Phase 1–6" reference and a phase-numbering slip in §7.1:

Confirmed: only `docs/規劃_推薦投組系統V2.md` was touched; the pre-existing modified/untracked files are unchanged by this edit.

## 修正摘要(依 Codex 審查逐項處理)

1. **七層不是單向管線** — 新增 §2.0「主線層 vs 旁路限制層」,L6 改為可隨時作用於 L4/L5 的旁路控制層,不再是第六個下游步驟。
2. **族群狀態不應改寫進場訊號** — L3 現在只吃 L1 排序 + 個股價格結構,`Z1-*` 不再吃 L2 族群狀態;L2 只能在 L4 限制曝險/現金/集中度。
3. **E0 定義錯誤** — 修正為「仍可能因結構、排名、基本面、重大事件退出,差異只在不用固定停利/trailing」。
4. **Z1-R 與 E1-R 重複** — `Z1-R` 明定為 L3 產生的重新進場訊號;`E1-R` 改為「E1 退出政策 + Z1-R 重新進場政策」的組合,不再是獨立收復訊號生成器,§8 收復候選一併修正。
5. **網頁狀態映射過度簡化** — 「值得持有」加上 L1 評分、資料完整性、基本面、事件旗標等條件;「不追價」新增「上升但族群過熱」情境。
6. **研究路線凍結漏洞** — Phase 3 改為「必須精確實作 Phase 2 凍結參數」;Validation 與 walk-forward 拆成獨立的 Phase 5 / Phase 6,路線圖改為 Phase 1–7。
7. **Decision Register 不完整** — 補上 F14–F16(CAGR/Sharpe/MDD -30%),並新增「已裁定」小節記錄 Codex 對 MDD -30%/-40% 範疇區分、產業 PIT 化 blocker、Z1/E1 全新模組定位、L1 與 L2–L5 並行順序四項裁決。

`git status --short` 確認本輪仍只有 [docs/規劃_推薦投組系統V2.md](Project 1/docs/規劃_推薦投組系統V2.md) 被異動(仍為 untracked),其餘既有變更未被觸碰,未 stage、commit 或 push。