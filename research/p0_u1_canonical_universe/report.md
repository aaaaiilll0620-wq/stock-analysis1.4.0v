# P0-U1 Canonical Universe Result

**狀態**：Single-shot 已完成，結果已凍結。本報告依 prereg §31 固定模板逐節寫出，不挑漂亮結果。

---

## 0. 範圍裁決（對話中已與使用者確認，記錄於此供稽核）

`docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md` 的背景文字（§1）描述的「A/B 母體不同」
指向 **production 部署路徑**（`core/score_store.py` + `scripts/l4a_decision.py` +
`c2_fullpool_*.csv`），但該路徑**從未走過 H1-H5 驗證**、也沒有全歷史批次回測迴圈。
prereg §18/§21 又明確要求 Phase D「必須使用現行 frozen H1-H5 validation framework」——
這個框架只存在於**研究引擎**（`beat_0050/strategies/dual100_lab.py` +
`high52_lab.dual_confirm_mask` + `honest_backtest.Engine`，吃真身 `realbody_scores*.parquet`）。

這兩件事對不上：production 路徑有 prereg 描述的 bug 但沒有 H1-H5；研究引擎有 H1-H5
但（本報告下面會證明）它原本就沒有 prereg §1 描述的那種「母體差了一個數量級」的 bug。
本研究執行前已與使用者對話核對並取得明確裁決：

> **U1 的對象是研究 H1-H5 已驗證引擎**，不是 production score_store/l4a_decision.py 路徑。

因此本報告中的 canonical universe，定義為：

```
C_t = tier_valid["100萬"] ∩ {real_composite 有效} ∩ {c2 四腳(value_ind/revenue_yoy/
      high52_prox/momentum)皆有效}
```

而不是 prereg 背景文字字面描述的「watchlist.txt 958 檔 vs 每日 ADV 全池」。這是本次執行
與 prereg 原始背景文字之間**唯一的實質偏離**，其餘所有條款（80/80 交集、TOP_N=None、
等權、月頻、ADV≥100萬、H1-H5 gate 定義、tie-handling、percentile 公式)全部逐字遵守。

---

## 1. Preregistration integrity

- **prereg 檔案**：`docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md`
  sha256 `b75154fff2834960d7b40dd54bd2506be58d1fa1db1b3311bc4a60902860912e`
- **git commit（HEAD，凍結時）**：`ef8a267e2a4040556e713f8378ade783422b368a`
  （分支 `claude/fix-stale-scoring-tests`；工作樹在凍結前已有非本研究產生的未 commit
  變更，故額外以逐檔 sha256 釘住依賴檔案，見 `manifest.json`）
- **關鍵程式碼 sha256**：`core/canonical_universe.py`、
  `beat_0050/strategies/high52_lab.py`、`beat_0050/strategies/dual100_lab.py`、
  `beat_0050/honest_backtest.py`、`core/scoring_manager.py` —— 全部列於 `manifest.json`
- **資料快照 sha256**：`obs_alpha.parquet` / `exec_ret.parquet` /
  `realbody_scores_adv100w.parquet`（263,928 列）/ `0050_tr.parquet` —— 全部列於
  `manifest.json`
- **與 prereg 的偏離**：
  1. 對象引擎由 production 改為研究 H1-H5 引擎（見上節，使用者已裁決）。
  2. `watchlist.txt` 母體問題不適用（研究引擎母體來自 `obs_alpha`，非 watchlist.txt）。
  3. §32 建議「盡量不要直接侵入兩個 scoring engine」——`core/canonical_universe.py`
     是新增的共用層，但為了讓 `dual_confirm_mask` 真正「呼叫或複用目前 production
     完全相同的 percentile ranking function」（§9），必須把該函式內嵌的 `pct()`/`topk()`
     closure 抽出到共用層、並讓原函式改為呼叫它——這觸碰了 `high52_lab.py`，但只新增
     一個預設 `False`（行為不變）的 `canonical` 參數，未改動任何演算法（見 §2 逐位元對帳）。
     同理對 `dual100_lab.py` 的 `tier_net`/`run_h1`~`run_h5`/`main()` 新增同名的
     pass-through 參數與 `--canonical` CLI 旗標，預設值全部保持 baseline 行為不變。
  4. §15 要求「每個 decision date 輸出 `canonical_universe_YYYY-MM-DD.csv`」——實際輸出
     255 個檔案於 `canonical_universe_by_date/`（逐日期分檔，符合字面要求）。這 255 個
     檔案（30MB）**不進版控**（2026-08-12 使用者裁決，比照 `.gitignore` 對
     `beat_0050/results/*.log` 的既有先例：可重生的執行輸出留在本機，只有彙總產物
     進 git）。要重新產生：`python research/p0_u1_canonical_universe/build_structural_audit.py`
     （輸入已由 `manifest.json` 的 sha256 凍結，重跑應得到逐位元相同的輸出）。

---

## 2. Structural validation

- **A/B set equality**：`assert_canonical_invariants()` 對全部 255 個決策月驗證
  `isfinite(real_composite) & C_t == C_t` 且 `isfinite(c2_U1) & C_t == C_t`，兩次執行
  （Phase B 乾跑 + Phase D 單發回測內建 assertion）均**未觸發任何 raise**。
- **denominator equality**：由建構方式保證 —— `real_composite_pct_U1` 與 `c2_pct_U1`
  在每個決策月都是在同一個 `C_t` 內排名，`n_A_rank(t) == n_B_rank(t) == n_canonical(t)`
  對全部 255 月成立（非僅平均值相同，見 `canonical_universe_audit.csv` 逐月數字）。
- **raw score equality**：`test_real_composite_unchanged` / `test_c2_score_unchanged`
  （`tests/test_canonical_universe.py`）證明 `canonical=True` 呼叫前後 `P.REAL_COMP`
  與四條 c2 原始腿逐位元不變（未被就地修改）。
- **canonical=False 逐位元回歸**：`test_canonical_false_bitwise_identical_to_pre_refactor`
  用重構前的原始 inline 演算法重算一次，與重構後 `canonical=False` 輸出逐位元相同；
  另外 baseline 全量 H1-H5 重跑後 H2 數字為 **CAGR 22.79% / Sharpe 1.20**，與
  `docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md` §4 及
  `docs/預註冊_雙確認ADV100萬.md` 已發布數字**完全一致**，獨立確認重構未污染 baseline。
- **missingness**：`composite` 在 `tier_valid["100萬"]` 內缺值率 **0.0000%**（由
  `min_cov=1.0` 硬性 gate 保證）；`c2_baseline`（各腳各算分母的舊算法）缺值率
  **0.2079%**——這就是 prereg §1 想修的那個落差在本引擎裡的**實際大小**：不是「958檔
  vs 全市場」那種數量級,而是每 1,000 個 stock-month 裡約 2 個因為單一腳缺值而在 A/B
  分母上不對齊。`c2_u1`（U1 canonical 算法)在 `C_t` 內缺值率**恰為 0.0000%**（定義上
  保證)。
- **assertion 結果**：全部通過，19 條迴歸測試（`tests/test_canonical_universe.py`）+
  25 條既有 `test_research_lifelines.py` + 1,063 條全專案既有測試（`-m "not slow"`）
  全數通過，無迴歸。

**Gate U1-S：PASS。**

---

## 3. Universe statistics（255 個決策月，2005-01-31 ~ 2026-03-31）

| 指標 | mean | std | min | P25 | median | P75 | max |
|---|---|---|---|---|---|---|---|
| n_A_original | 1013.1 | 178.5 | 662 | 875 | 1028 | 1148.5 | 1363 |
| n_B_original（baseline 算法） | 1011.0 | 179.5 | 661 | 873 | 1025 | 1148 | 1362 |
| n_overlap | 1011.0 | 179.5 | 661 | 873 | 1025 | 1148 | 1362 |
| n_canonical (=C_t) | 1011.0 | 179.5 | 661 | 873 | 1025 | 1148 | 1362 |

`n_overlap == n_B_original == n_canonical` 對全部 255 月恆成立——因為 A（真身 composite）
在 `min_cov=1.0` 保證下已 100% 覆蓋 `tier_valid`，所以 B（c2 四腳交集）才是真正縮小分母
的一方，而 `C_t` 的建構方式使它與 B 的既有母體完全重合。這代表**在本引擎裡，U1 的
canonical universe 修正幾乎不改變母體大小**（詳見 §4）。完整逐月數字見
`canonical_universe_audit.csv` / `universe_audit.csv`。

---

## 4. Portfolio impact

- **月度 Jaccard(baseline holdings, U1 holdings)**：mean **0.9957**，median **1.0000**，
  min **0.9200**，P25/P75 皆為 1.0000（見 `U1_vs_baseline_jaccard_monthly.csv`）。
  即：**超過一半的月份，baseline 與 U1 選出完全相同的持股**；最壞的月份重疊度仍達 92%。
- **持股數**：baseline 平均 48.19 檔（活躍月中位數 46）；U1 平均 48.18 檔（中位數 46）。
  OOS 窗口（第 60 月起）平均皆為 53.47 檔。
- **Enter/Exit 統計**：`U1_vs_baseline_portfolio_diff.csv`（12,310 列，255 月 × 每月
  union 持股）逐檔記錄 `UNCHANGED` / `ENTER_U1` / `EXIT_U1`；由 Jaccard 分布可推斷
  `ENTER_U1`/`EXIT_U1` 合計僅占極少數月度持股變動。
- 此指標僅描述 U1 改變 portfolio 的幅度，**不作為成功/失敗門檻**（§16）。

---

## 5. Portfolio diagnostics

### Holdings count
見 §4（baseline/U1 幾乎相同，全期平均 48.2 檔、OOS 窗平均 53.5 檔）。

### Liquidity（選中股 ADV20）
| | median | P10 | min | % ADV20<1000萬 | % ADV20<500萬 |
|---|---|---|---|---|---|
| baseline | 4,318 萬/日 | 383 萬/日 | 100 萬/日 | 23.5% | 13.4% |
| U1 canonical | 4,306 萬/日 | 384 萬/日 | 100 萬/日 | 23.5% | 13.3% |

兩者幾乎無差異，與 §3/§4 的母體幾乎不變一致。這只是 diagnostic，**不因此把 ADV floor
改成漂亮數字**（§17 明文禁止）。

### Recent-return profile（近日漲幅代理指標）
Panel 只提供 `momentum`（≈20 日動能）、`mom60`、`mom120` 三種既有窗長的因子，沒有現成的
`ret_5d`/`ret_20d`/`ret_60d` 報酬序列可直接讀取。依 prereg §17「沒有現成資料則不得為
U1 額外開發新模型，只可略過並註記」，這裡改用 `momentum`（≈20 日）作為代理，**不代表
嚴格的 ret_20d 定義，僅供參考**：

| | median | P75 | P90 | max |
|---|---|---|---|---|
| baseline | 1.46 | 6.08 | 12.34 | 304.41 |
| U1 canonical | 1.45 | 6.07 | 12.33 | 304.41 |

同樣幾乎無差異。`ret_5d`/`ret_60d` 略過，已如實註記。

### Concentration
Panel 不含產業別/市值分組欄位，依 §17「沒有現成資料則略過並註記」——**本項略過**。

---

## 6. H1-H5（見 `h1_h5_results.csv` 完整表）

| Gate | Baseline | U1 canonical | 判定門檻 |
|---|---|---|---|
| H1 前置閘 | Sharpe 0.89, 選股階 +9.30pp | Sharpe 0.88, 選股階 +9.17pp | Sharpe>0.68 且選股階>0 |
| H2 walk-forward(主) | CAGR 22.79% / Sharpe 1.20 | CAGR 22.67% / Sharpe 1.19 | 勝 0050 同窗(16.52%/0.86) |
| H2b 固定層 OOS | CAGR 22.79% / Sharpe 1.20 | CAGR 22.67% / Sharpe 1.19 | 勝 0050 同窗 |
| H3 虛無對照(三組+DSR) | 全過（p=0.000/0.000/DSR p=0.0002） | 全過（p=0.000/0.000/DSR p=0.0002） | 各自 <0.01/<0.01/<0.05 |
| H4 滑價穩健 | 0.6%時 Sharpe 0.73 | 0.6%時 Sharpe 0.72 | >0.68 |
| H5 六時代穩健 | 勝等權 6/6，勝0050夏普 4/6 | 勝等權 6/6，勝0050夏普 4/6 | ≥4/6，≥3/6 |

**H1-H5 全部通過，baseline 與 U1 兩邊逐項判定完全一致（無一項翻盤）。**

---

## 7. Performance

（H2 walk-forward OOS 為主假設代表數字；195 個月，2010-01-29 ~ 2026-03-31）

| | CAGR% | Sharpe | MDD% | 月換手% | 來回成本% |
|---|---|---|---|---|---|
| Baseline dual100 @ADV≥100萬 | 22.79 | 1.20 | -28.5 | 71.1 | 0.72 |
| U1 canonical | 22.67 | 1.19 | -28.9 | 71.1 | 0.72 |
| 0050（同窗) | 16.52 | 0.86 | -29.4 | 0.0 | — |

差異：CAGR **-0.12pp**、Sharpe **-0.01**、MDD **-0.4pp**（U1 略差，但差距在雜訊等級,
且未改變任何 H1-H5 pass/fail 判定)。平均持股 baseline 48.19 檔 vs U1 48.18 檔;中位數
皆為 46 檔;月換手率兩者皆 71.1%,交易成本模型未變(來回 0.72% = 手續費 0.47% + 滑價
0.25%)。

---

## 8. Decision

- **U1-S（Structural Validity）：PASS**
- **U1-V（Existing Validation）：PASS**（H1-H5 六項判定,baseline 與 U1 兩邊逐項一致)

依 prereg §29 決策樹 **Case A**：

> Structural PASS + H1-H5 PASS → canonical ranking universe 修正可保留為候選,
> **暫不直接取代現行 Champion**,下一步排入 `P0-R1 Research / Live Identity`。

---

## 9. Interpretation（只解釋，不修改模型）

1. **prereg §1 描述的「A/B 母體不同」bug，在本次選定的研究引擎裡真實存在，但規模遠小於
   prereg 背景文字暗示的量級。** 背景文字引用的「watchlist.txt 958 檔 vs 每日 ADV 全池」
   落差是 **production 部署路徑**的問題；本引擎（H1-H5 已驗證的
   `dual_confirm_mask`）原本就在同一個 `tier_valid["100萬"]` 母體起點上算 A 和 B，
   真正的分母落差只來自「A 因 `min_cov=1.0` 保證 100% 覆蓋，B 的 c2 四腳等權平均只要
   任一腳缺值就整檔剔除」——量出來的規模是 **0.21% 的 stock-month**（§2）。
2. **這解釋了為什麼 baseline 與 U1 的績效幾乎相同（§7）**：月度 Jaccard 中位數
   1.0（§4），代表半數以上月份的持股組合逐檔相同；H1-H5 六項判定無一項翻盤。這不是
   「U1 沒有效果所以隨便做做」——而是這個特定 site 的結構性落差確實很小，是一個**誠實
   的否定式強化**（confirmatory null-ish result）：對齊分母幾乎不改變結果，說明
   H1-H5 已驗證的 Sharpe 1.20/CAGR 22.79% **不是靠這 0.21% 的分母不對齊撐起來的**。
3. **prereg 原本想回答的問題（production 路徑 watchlist.txt vs 每日 ADV 全池的對齊）
   仍未回答。** 這是本次執行與原始 prereg 背景文字之間唯一的實質落差(§0/§1 已說明)，
   需要另開一個新的預註冊(暫定 P0-U2 或併入下方 P0-R1)專門處理 production 部署路徑,
   而且會先需要一個「批次回測 l4a_decision.py + l4b_execution.py 全歷史」的新框架
   （本次盤點確認目前不存在,見對話中的探勘結果)。
4. **U1 只解決 A/B percentile ranking universe 不一致(在本次選定的研究引擎範圍內)。**
   即使 U1 PASS,下列問題仍存在(prereg §30 清單原樣列出,無一項因本次 PASS 而解決):
   watchlist 人工母體、ADV 100萬過寬的疑慮、`c2_fullpool` 不套 L0/L2、低流動性股票、
   近日漲幅過大、約 48 檔持股、c2 skipna、短期 reversal/中期 momentum 衝突、
   technical horizon、chip horizon、sell side 無 ADV cap、整張限制、
   research/live identity、2019 definition breaks。**不得把本次 PASS 宣稱為「整套系統
   已修好」。**

---

## 10. Next action

按 prereg §29 Case A 與 §35：`P0-R1 Research / Live Identity`——把「production 路徑
真正存在的 watchlist.txt vs 每日 ADV 全池落差」納入一個新的、獨立的預註冊研究,並先確認
是否需要為 `l4a_decision.py`/`l4b_execution.py` 建立全歷史批次回測框架(本次盤點顯示
目前不存在)。本次 U1 產物(`core/canonical_universe.py`、`--canonical` 開關、全部稽核
CSV)保留封存於 `research/p0_u1_canonical_universe/`,可作為 P0-R1 的起點,但不直接取代
`scripts/l4a_decision.py` 現行邏輯。
