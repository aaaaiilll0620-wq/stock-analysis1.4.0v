Phase D 執行完成 — 結果回報

依您的裁決（A 腳單獨評估，B 腳/最終 fusion membership = NOT EVALUATED），已完成可執行的部分。全程使用 Windows PowerShell + 真實 frozen snapshot，HEAD 與 staged diff 全程未變、未 stage、未 commit。

固定基準

- HEAD 全程 = 0b1af42224314d71e8d16121d356235ffa7aacf7（未變）
- staged diff 全程為空
- collector_schema.json／phase_b_design_freeze.md／errata_E2／prereg 逐一重新雜湊比對 approval_receipt.json，全部相符（前後一致）
- 既有 unrelated dirty state（~150 檔案，line-ending 重整）原封不動，未 stash/clean/reset

1. R-FWD A 腳 parity — 四項結果分開揭露

┌───────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│         項目          │                                                   結果                                                    │
├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Membership 255/255    │ FAIL — 169/255 exact，86 個月有 mismatch（common population 內比對）                                      │
│ exact-match           │                                                                                                           │
├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Raw-score tolerance   │ FAIL — max_abs_diff = 3.662109378410605e-06。根因已查明：high52_lab.Panel 的 mat() closure 預設用         │
│ 1e-12                 │ np.float32 存 real_composite，adapter 直讀 parquet 拿到的是原生 float64，精度差異約 1e-6，剛好解釋了為何  │
│                       │ mismatch 集中在每年 5/9/11 月（分數貼近 top20% 門檻邊界的月份）                                           │
├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Process isolation     │ PASS（oracle pid 9384 ≠ adapter pid 25584，兩個獨立 OS process）                                          │
├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Future-input-access   │ PASS（AST 靜態掃描 adapter 模組：0 個 forbidden import、0 個 forbidden 檔名出現在任何 call 參數；adapter  │
│ audit                 │ 全程只開過 realbody_scores_adv100w.parquet 一個檔）                                                       │
└───────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────┘

Durable qualification persistence = PENDING（無 Primary/Mirror root 可寫，且 raw-score 本身未過門檻）。qualification_status 明寫為 NOT_QUALIFIED_A_LEG_ONLY_SCOPE。255 月完整明細：research/p0_r2_identity_collector/a_leg_parity_result.json。

B 腳／最終 fusion membership：NOT_EVALUATED，reason code INSUFFICIENT_FROZEN_PIT_INPUTS（沒有用 obs_alpha 衍生欄位冒充）。

2. Capacity dry-run（P_ONLY_EVIDENCE，3 日期，全部真實資料）

┌────────────┬──────────┬──────────┬────────────┬────────────┬───────────────┬─────────────────────┐
│   as_of    │ P-A rows │ P-B rows │ app-fusion │ l4a-fusion │ payload bytes │ attempt_total_bytes │
├────────────┼──────────┼──────────┼────────────┼────────────┼───────────────┼─────────────────────┤
│ 2026-08-07 │ 885      │ 1670     │ 67         │ 67         │ 370,412       │ 517,528             │
├────────────┼──────────┼──────────┼────────────┼────────────┼───────────────┼─────────────────────┤
│ 2026-08-10 │ 881      │ 1667     │ 67         │ 67         │ 368,698       │ 515,814             │
├────────────┼──────────┼──────────┼────────────┼────────────┼───────────────┼─────────────────────┤
│ 2026-08-11 │ 882      │ 1674     │ 53         │ 53         │ 384,318       │ 531,434             │
└────────────┴──────────┴──────────┴────────────┴─────────────────────┘

bootstrap_bytes_per_run = ceil(1.5 × 531,434) = 797,1 或估算值代替。App-path 與真實 l4a-path（呼叫真正的l4a_decision.compute_target_list）在三個日期上 membership 完全一致，沒有觸發 ProductionInternalDivergence。Temp 目錄逐一
mkdtemp→量測→rmtree，跑後確認 OS temp 下無殘留。已寫 tity_collector/capacity_dry_run_report.json（schema驗證通過）。COMPARABLE_IDENTITY 容量：NOT_EVALUATED（同一個缺件原因）。

3. Tests

- 新增 tests/test_phase_d_a_leg_parity.py（11）+ test_phase_d_capacity_driver.py（4），合成 fixture，先寫測試（static_import_audit
第一版誤判 docstring 為違規，修正後重跑轉綠）。
- python -m pytest -q -p no:cacheprovider tests → 1136 passed, 2 skipped, 0 failed。
- Production 檔案（core/、beat_0050/、lab_paths.py、r：與任務開始前完全相同的既有 dirtydiff，本次沒有新增任何改動。

4. Gates

┌──────┬────────────────────────────────────────────────────────────────────────────────────────────┐
│ Gate │                                                               │
├──────┼────────────────────────────────────────────────────────────────────────────────────────────┤
│ H-D  │ 沿用 approval_receipt.json 的 PASS，僅重新驗                  │
├──────┼────────────────────────────────────────────────────────────────────────────────────────────┤
│ C-P  │ NOT PASS（P_ONLY 完成；COMPARABLE 未評估；ro                  │
├──────┼────────────────────────────────────────────────────────────────────────────────────────────┤
│ C-R  │ FAIL（announcement-date PIT blocker 未解除； 功不解除此判定） │
├──────┼────────────────────────────────────────────────────────────────────────────────────────────┤
│ C-S  │ NOT PASS（synthetic/regression 全綠；但真實  ）               │
├──────┼────────────────────────────────────────────────────────────────────────────────────────────┤
│ C-A  │ NOT EVALUATED                                                 │
└──────┴────────────────────────────────────────────────────────────────────────────────────────────┘

未宣稱 collector 已啟用、已具任何 qualified/COMPARABLmary/Mirror roots、R-FWD live collection、Task
Scheduler、production 寫入）完全未觸碰。

小型報告：research/p0_r2_identity_collector/phase_d_o全部檔案維持unstaged/uncommitted，本次到此停止，未進入 Phase E /