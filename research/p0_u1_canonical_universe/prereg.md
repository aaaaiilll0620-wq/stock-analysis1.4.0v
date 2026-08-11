# P0-U1 Canonical Universe 預註冊修改規格

**文件名稱建議：**

`docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md`

**研究代號：** `P0-U1`

**研究名稱：** Canonical Ranking Universe Alignment

**狀態：** PRE-REGISTERED / 尚未查看修改後完整績效

**基準策略：** 現行 `dual100`

**修改類型：** 結構一致性修正 / Ranking Universe Alignment

**禁止性質：** 本研究不是權重最佳化、因子新增、門檻搜尋、集中持股測試或流動性優化。

---

## 1. 研究背景

依 2026-08-11 系統全景圖，目前程式碼的正式投組由兩條管線產生：

- 管線 A：`real_composite`
- 管線 B：`c2_score_full`

最後使用兩者百分位的雙確認交集產生投組。

該全景圖為逐檔讀取當前程式碼建立的最新靜態快照，而非依據舊文件或記憶推測；若程式碼後續變更，應重新掃描程式碼，而非手動修改流程圖。fileciteturn0file0L4-L8

現行已知結構落差為：

> 管線 A 母體為人工維護的 `watchlist.txt`，約 958 檔；  
> 管線 B 母體則是逐日全市場 ADV 篩選結果。

因此兩邊 percentile 的分母不同，文件已明確標示為「已知未修的落差」。fileciteturn0file0L72-L76

現行 B 投組實際使用的不是粗篩後 `pool_date.csv`，而是：

> `c2_fullpool_date.csv`

其母體條件為：

> `ADV20 >= 1,000,000 NTD AND listed_ok`

且不套用 L0、L2；該 fullpool 才是實際進入投組的 c2 排名來源。fileciteturn0file0L167-L172

---

# 2. 核心研究問題

本次研究**只回答一個問題**：

> 當 `real_composite` 與 `c2_score_full` 改為在完全相同的橫斷面股票集合內計算 percentile 時，現行 dual100 策略的選股結果與既有 H1–H5 驗證結果會如何改變？

本次研究**不回答**：

- 哪一個 universe 比較好；
- ADV100萬是否過低；
- watchlist 是否應淘汰；
- 是否應改成全市場；
- 是否應改五維權重；
- 技術、動能、籌碼是否有效；
- 80/80 是否為最佳門檻；
- 是否應改 Top N；
- 如何解決低流動性；
- 如何解決追高。

上述問題全部留待後續研究。

---

# 3. 研究假說

## H-U1-Structural

若目前 A/B percentile 分母不同確實造成結構性不一致，則在使用共同 ranking universe 後：

> `real_composite_pct` 與 `c2_pct`

應可保證在每個決策日使用**完全相同的 ticker set 與 denominator N**。

此為本研究的主要結構假說。

---

## H-U1-Portfolio

共同排名母體可能改變：

- A/B Top20% 成員；
- A/B overlap；
- 最終持股數；
- 股票排序邊界；
- portfolio turnover；
- portfolio composition。

但**不預註冊其改善方向**。

也就是：

> 不假設 Sharpe 一定提高；
>
> 不假設 CAGR 一定提高；
>
> 不假設持股一定減少；
>
> 不假設低流動性股票一定減少。

避免在結果出現後倒推故事。

---

# 4. Frozen Baseline

Baseline 必須固定為目前正式策略：

### Strategy

`dual100`

### Fusion

```text
real_composite percentile >= 80
AND
c2_score_full percentile >= 80
```

即：

```text
FUSION_PCT = 20
```

### Portfolio size

```text
TOP_N = None
```

不得恢復已被否決的 TOP15。

### Weighting

```text
Equal Weight
```

### Frequency

```text
Monthly rebalance
```

### Execution timing

```text
Decision: close(t)
Execution: open(t+1)
```

### L4a / L4b

完全沿用現行實作：

- `LOT_SIZE = 1000`
- `ORDER_ADV_CAP = 3%`
- 成本模型不變
- ADV cap 不重分配
- OrderIntent / PositionState 邏輯不變。

目前正式流程是在決策日收盤後計算 composite 與 c2 percentile，以 80/80 交集產生目標，接著等權換算、ADV 3% 限制，並於 T+1 open 執行。fileciteturn0file0L515-L539

---

# 5. U1 唯一允許修改的變數

本實驗的**唯一自變項**為：

> **A/B percentile calculation universe**

除此之外，一律 frozen。

---

# 6. Canonical Universe 精確定義

對每個 portfolio decision date `t`：

定義：

```text
A_t =
當期在 score_store 中
具有有效 real_composite 的股票集合
```

定義：

```text
B_t =
當期 c2_fullpool_date.csv 中
具有有效 c2_score_full 的股票集合
```

其中 B 原本已受現行：

```text
listed_ok == True
ADV20 >= 1,000,000 NTD
```

限制。

本研究不新增、不移除 B 的 eligibility 條件。

---

## Canonical Ranking Universe

定義：

```text
C_t = A_t ∩ B_t
```

並要求：

```text
real_composite != NaN
AND
c2_score_full != NaN
```

因此：

```text
N_A_rank(t)
=
N_B_rank(t)
=
|C_t|
```

---

# 7. 為什麼 U1 使用交集，而不是直接改成全市場

這是本次預註冊最重要的控制條件。

目前 final FUSE 本來就要求一檔股票：

> 同時有 A score 與 B score。

因此只有：

```text
A_t ∩ B_t
```

中的股票有可能成為最終持股。

所以 U1 使用該交集作共同排名母體：

> **不改變「哪些股票理論上有資格被 FUSE 選中」這件事。**

只改變：

> **這些股票彼此比較時所使用的 percentile denominator。**

反之，如果直接將 A 從 958 檔擴充至全部 B 股票，會同時改變：

1. A 的 denominator；
2. A 的 coverage；
3. final candidate set；
4. 可進入 portfolio 的股票種類；
5. 可能的 liquidity / market-cap distribution。

這不再是單一變數實驗，因此禁止在 U1 執行。

---

# 8. U1 排名流程

Baseline 現況概念上為：

```text
A_pct = rank(real_composite within A_t)

B_pct = rank(c2_score_full within B_t)

SELECT =
A_pct >= 80
AND
B_pct >= 80
```

U1 改為：

```text
C_t = inner_join(A_t, B_t)

A_pct_U1 =
rank(real_composite within C_t)

B_pct_U1 =
rank(c2_score_full within C_t)

SELECT_U1 =
A_pct_U1 >= 80
AND
B_pct_U1 >= 80
```

除此以外不得改動。

---

# 9. Ranking function 必須 frozen

不得因為本次研究順便改：

- percentile method；
- tie handling；
- ascending / descending；
- `rank(method=...)`；
- rounding；
- missing-value handling；
- Top20% 邊界定義。

必須呼叫或複用**目前 production 完全相同的 percentile ranking function**。

如果目前 ranking implementation 沒有獨立函式，允許抽取成共用函式，但：

> refactor 前後同一 input 必須產生 bit-for-bit / value-equivalent 相同結果。

不得藉 refactor 改演算法。

---

# 10. 原始分數必須完全不變

對所有 `(date, ticker)` 同時存在於 Baseline 與 U1 的資料：

必須驗證：

```text
real_composite_baseline
==
real_composite_U1
```

以及：

```text
c2_score_full_baseline
==
c2_score_full_U1
```

允許改變的只有：

```text
real_composite_pct
c2_pct
fusion_membership
```

如果 raw score 發生任何變化：

> 本次 run 判定為 implementation contamination。

該績效不得解讀。

---

# 11. 明確禁止修改項目

U1 執行期間以下全部禁止修改。

### Universe / liquidity

不得修改：

```text
ADV20 >= 1,000,000
```

不得改成 300萬、500萬、1000萬或其他值。

不得新增：

- market cap filter；
- turnover filter；
- 成交值 percentile；
- 成交量門檻；
- popularity filter。

---

### 管線 B

不得修改：

- `value_ind_pct`
- `revenue_yoy`
- `high52_prox`
- `momentum20`
- `100 - momentum20_pct`
- c2 等權；
- `skipna` 行為；
- L0；
- L1；
- L2；
- shortlist；
- c2 formula。

---

### 管線 A

不得修改：

- Fundamental；
- Valuation；
- Technical；
- Momentum；
- Whale；
- 所有子因子；
- clip；
- bonus；
- regime multiplier；
- balanced weights。

目前 balanced composite 仍固定為：

```text
Fundamental 0.31
Valuation   0.08
Technical   0.19
Momentum    0.27
Whale       0.15
```

不得調整。

---

### FUSE

禁止測：

```text
75/75
80/85
85/80
85/85
90/90
```

只能使用現行：

```text
80 / 80
```

---

### Portfolio construction

禁止：

- TOP10；
- TOP15；
- TOP20；
- dynamic N；
- volatility weighting；
- score weighting；
- sector cap；
- liquidity weighting；
- rank weighting。

維持：

```text
TOP_N=None
equal weight
```

---

### Timing / overextension

不得新增：

- RSI overbought filter；
- 20D漲幅上限；
- 60D漲幅上限；
- MA bias filter；
- gap filter；
- 追高限制。

即使結果仍有追高股票，也留給後續 P0/P1。

---

# 12. Watchlist 在 U1 的處理

`watchlist.txt` **暫時禁止修改**。

包括：

- 不增股票；
- 不刪股票；
- 不改歷史內容；
- 不以目前全市場取代。

原因不是認為 watchlist 正確。

而是：

> U1 的研究問題只有 ranking denominator alignment。

「watchlist 是否應該作為 A universe」是另一個獨立研究問題。

應另開：

```text
P0-U2
```

或其他預註冊實驗。

不得混入 U1。

---

# 13. PIT 與資料時間規則

所有資料時間規則完全沿用 baseline。

尤其：

- 價格；
- PER/PBR；
- 月營收；
- 財報；
- 法人資料；
- 產業估值；
- RS；
- regime

不得因 U1 更動 release lag 或 PIT 邏輯。

現行 backtest 已規定價格/PER/月營收只取 `date <= as_of`，季報使用公告日加既定延遲，未來價格只能作為結果量測、不可作為訊號輸入。fileciteturn0file0L114-L115

---

# 14. Implementation invariants

程式必須建立以下自動化 assertions。

每個 rebalance date：

```text
set(A_rank_tickers)
==
set(B_rank_tickers)
==
set(C_t)
```

以及：

```text
len(A_rank_tickers)
==
len(B_rank_tickers)
==
len(C_t)
```

再驗證：

```text
real_composite.notna().all()
c2_score_full.notna().all()
```

並要求：

```text
ticker uniqueness == True
date uniqueness within ticker == True
```

若任一 assertion 失敗：

```text
raise / abort
```

禁止 silently fallback 到原本 A/B 各算各的 percentile。

---

# 15. 建議新增 audit artifact

每個 decision date 必須輸出：

```text
canonical_universe_YYYY-MM-DD.csv
```

至少包含：

```text
date
ticker
in_A_original
in_B_original
real_composite
c2_score_full
real_composite_pct_U1
c2_pct_U1
a_top20
b_top20
fusion_selected
```

另建：

```text
canonical_universe_audit.csv
```

包含：

```text
date
n_A_original
n_B_original
n_overlap
n_canonical
n_A_top20
n_B_top20
n_fusion
```

目的不是新增策略訊號，而是確保研究可稽核。

---

# 16. Baseline comparison artifact

必須產生：

```text
U1_vs_baseline_portfolio_diff.csv
```

欄位至少：

```text
date
ticker
baseline_selected
u1_selected
change_type
```

`change_type`：

```text
UNCHANGED
ENTER_U1
EXIT_U1
```

並計算每月：

```text
Jaccard(Baseline, U1)
```

此指標僅描述 U1 改變 portfolio 的幅度。

不作為成功/失敗門檻。

---

# 17. Portfolio quality diagnostics

在**正式 single-shot backtest 完成後**，一次性輸出：

### Holdings count

- mean
- median
- P10
- P90
- min
- max

---

### Liquidity

每月持股：

- median ADV20；
- P10 ADV20；
- minimum ADV20；
- `% holdings ADV20 < 10M`；
- `% holdings ADV20 < 5M`。

注意：

> 這些只是 diagnostic。

不得看到結果後立即把 ADV floor 改成某個漂亮數字。

---

### Recent-return profile

每月入選股票記錄：

```text
ret_5d
ret_20d
ret_60d
```

至少輸出：

- median；
- P75；
- P90；
- maximum。

目的：

> 檢查 U1 是否意外改變「近期已大漲」股票比例。

不作為 U1 的 primary acceptance criterion。

---

### Concentration

若目前已有資料，輸出：

- industry count；
- top industry weight；
- HHI；
- market-cap distribution。

沒有現成資料則不得為 U1 額外開發新模型，只可略過並註記。

---

# 18. Performance evaluation

正式 backtest 必須使用**現行 frozen H1–H5 validation framework**。

不得因 U1 修改：

- OOS period；
- benchmark；
- transaction costs；
- slippage；
- rebalance dates；
- execution timing；
- H1–H5 gate；
- pass/fail definition。

目前文件記錄 baseline dual100：

```text
OOS Sharpe = 1.20
CAGR       = 22.79%
```

對照 0050：

```text
Sharpe = 0.86
CAGR   = 16.52%
```

同時現行 live / research 還存在其他定義落差，月度持股 Jaccard 中位數僅 0.640；這些問題不應混入本次 U1 修改。fileciteturn0file0L752-L770

---

# 19. U1 必須回報的績效項目

至少包含既有 H1–H5 所需全部項目。

另外固定輸出：

```text
CAGR
Sharpe
MDD
Calmar / GCAR（若現有框架已有）
annualized volatility
turnover
transaction cost
slippage impact
average holdings
median holdings
```

如果目前 framework 沒有某項：

> 不得為了 U1 改動績效定義。

可以新增「純報表計算」，但不得影響策略。

---

# 20. U1 Pass / Fail 定義

本研究分為兩層判定。

## Gate U1-S：Structural Validity

必須全部成立：

```text
A ranking ticker set == B ranking ticker set
A denominator == B denominator
raw real_composite unchanged
raw c2_score_full unchanged
80/80 unchanged
portfolio engine unchanged
execution engine unchanged
PIT rules unchanged
```

任一失敗：

> **U1-S FAIL**

績效結果作廢。

只允許修 implementation bug 後重新執行。

---

# 21. Gate U1-V：Existing Validation

Structural Gate 通過後：

> U1 必須重新接受**完全相同的既有 H1–H5 validation**。

不得創造新的較寬鬆標準讓 U1 過關。

### 若：

```text
H1-H5 全過
```

則：

> **U1-V PASS**

U1 有資格成為後續研究的 Challenger / Candidate Baseline。

---

### 若：

```text
任何既有硬性 Gate 失敗
```

則：

> **U1-V FAIL**

不得：

- 微調 80 → 78；
- 改 ADV；
- 改某個 factor；
- 改權重；
- 改 Top N；
- 挑較漂亮期間重跑。

U1 原封不動封存為否決結果。

---

# 22. U1 不設定「Sharpe 必須提高」這種新門檻

本研究主要是：

> structural correction experiment。

所以不另行預註冊：

```text
Sharpe must > 1.20
CAGR must > 22.79%
MDD must improve
```

原因是這些都是**方向性 alpha 假設**，而本研究並沒有提出 alpha modification。

真正的策略有效性裁決：

> 沿用既有 H1–H5。

這樣可以避免看到：

> Sharpe 1.18

就主觀說差，

或者看到：

> Sharpe 1.23

就主觀說成功。

---

# 23. Single-shot protocol

這部分要嚴格執行。

## Phase A — Implementation

允許：

- 寫程式；
- unit test；
- synthetic data；
- universe set equality；
- raw score equality；
- denominator equality；
- CSV schema validation。

禁止查看：

```text
U1 CAGR
U1 Sharpe
U1 MDD
U1 return curve
U1 yearly return
```

---

# 24. Phase B — Structural Dry Run

允許在歷史資料跑完整 universe alignment，但只能看：

```text
n_A
n_B
n_overlap
denominator equality
missingness
assertion results
```

不得查看未來報酬。

不得檢查：

> 哪種改法 Sharpe 比較高。

---

# 25. Phase C — Freeze

在首次完整績效執行前記錄：

```text
git commit hash
prereg file hash
config hash
watchlist hash
data snapshot/version
weights_version
FUSION_PCT
TOP_N
ADV floor
cost settings
```

輸出例如：

```text
research/p0_u1_canonical_universe/
    prereg.md
    manifest.json
```

---

# 26. Phase D — Single Reveal

Freeze 後進行：

> 一次完整 U1 backtest。

一次性產生：

```text
metrics.json
h1_h5_results.csv
portfolio_monthly.csv
universe_audit.csv
portfolio_diff.csv
report.md
```

此時才允許查看：

- CAGR；
- Sharpe；
- MDD；
- holdings；
- liquidity；
- recent-return distribution。

---

# 27. 什麼情況允許重跑

只有以下情況：

### Implementation invalid

例如：

- percentile 算錯；
- ticker duplicate；
- date merge 錯；
- raw score 被意外改變；
- pipeline crash；
- PIT bug；
- 程式沒有照 prereg 執行。

此時：

> 前一次 run 宣告 INVALID。

修復後可重跑。

但必須在：

```text
invalid_runs.log
```

記錄：

```text
run id
bug
why invalid
files changed
commit before
commit after
```

---

# 28. 不允許以「結果不好」當成 bug

以下不是合法 rerun 理由：

```text
Sharpe 下降
CAGR 下降
MDD 變差
持股更多
冷門股沒有改善
追高問題仍存在
```

這些都是有效研究結果。

不得因此修改 U1。

---

# 29. U1 完成後的 Decision Tree

### Case A

```text
Structural PASS
H1-H5 PASS
```

結論：

> Canonical ranking universe 修正可保留。

但**暫不直接取代 live production**。

下一步進：

> `P0-R1 Research / Live Identity`

把研究與實盤定義對齊。

---

### Case B

```text
Structural PASS
H1-H5 FAIL
```

結論：

> 「同分母排名」本身沒有通過既有策略驗證。

不得調參救援。

保留現行 Champion。

U1 封存。

再研究：

> 為什麼不同 denominator 反而是 baseline 報酬來源的一部分？

這很可能揭露原策略具有 hidden selection effect。

---

### Case C

```text
Structural FAIL
```

結論：

> 沒有得到研究結果。

修 implementation。

不解讀 performance。

---

# 30. U1 明確不解決的問題

最終報告必須明文寫：

> **P0-U1 只解決 A/B percentile ranking universe 不一致。**

即使 U1 PASS，下列問題仍存在：

```text
watchlist 人工母體
ADV 100萬過寬的疑慮
c2_fullpool 不套 L0/L2
低流動性股票
近日漲幅過大
48檔左右持股
c2 skipna
短期 reversal / 中期 momentum 衝突
technical horizon
chip horizon
sell side 無 ADV cap
整張限制
research/live identity
2019 definition breaks
```

不得把 U1 PASS 宣稱為：

> 「整套系統已修好」。

---

# 31. U1 最終報告固定模板

最終 `report.md` 必須按照以下順序，不得先挑漂亮結果。

```text
# P0-U1 Canonical Universe Result

## 1. Preregistration integrity
- commit
- config
- hashes
- deviations from prereg

## 2. Structural validation
- A/B set equality
- denominator equality
- raw score equality
- missingness
- assertion results

## 3. Universe statistics
- n_A
- n_B
- n_overlap
- n_canonical

## 4. Portfolio impact
- holdings count
- Jaccard vs baseline
- enter / exit counts

## 5. Portfolio diagnostics
- ADV distribution
- recent return distribution
- industry / size if available

## 6. H1-H5
- exact existing validation results

## 7. Performance
- CAGR
- Sharpe
- MDD
- turnover
- costs

## 8. Decision
- U1-S PASS / FAIL
- U1-V PASS / FAIL

## 9. Interpretation
只解釋，不修改模型

## 10. Next action
P0-R1 / archive
```

---

# 32. 建議實作位置

盡量不要直接侵入兩個 scoring engine。

比較乾淨的設計是新增一個共用層，例如：

```text
core/canonical_universe.py
```

提供：

```python
build_canonical_ranking_universe(...)
```

與：

```python
rank_fusion_inputs(...)
```

概念：

```python
def build_canonical_ranking_universe(a_df, b_df):
    merged = a_df.merge(
        b_df,
        on=["date", "ticker"],
        how="inner",
        validate="one_to_one",
    )

    merged = merged[
        merged["real_composite"].notna()
        & merged["c2_score_full"].notna()
    ].copy()

    return merged
```

然後：

```python
canonical["composite_pct"] = existing_pct_rank(
    canonical["real_composite"]
)

canonical["c2_pct"] = existing_pct_rank(
    canonical["c2_score_full"]
)

canonical["selected"] = (
    (canonical["composite_pct"] >= 80)
    & (canonical["c2_pct"] >= 80)
)
```

這只是 pseudo-code。

**實際實作必須沿用目前 production 的 rank direction 與 pct 定義，不可照這段示意重新發明。**

---

# 33. 強制 regression tests

至少寫以下 tests：

```text
test_canonical_contains_only_overlap
test_a_b_rank_universe_identical
test_rank_denominator_identical
test_real_composite_unchanged
test_c2_score_unchanged
test_no_duplicate_ticker_date
test_no_missing_score_in_canonical
test_fusion_threshold_unchanged
test_top_n_remains_none
test_order_adv_cap_unchanged
test_lot_size_unchanged
test_execution_t_plus_1_unchanged
```

另外最好加入：

```text
test_no_watchlist_expansion
test_no_new_liquidity_filter
```

防止 Claudecode「順手優化」。

---

# 34. 對 Claudecode 的禁止指令

這段我建議直接原文放進任務：

> 本任務不是要求改善績效，而是執行 P0-U1 Canonical Ranking Universe Alignment。不要根據回測結果自行優化任何因子、權重、ADV 門檻、FUSION_PCT、TOP_N、成本、技術條件、籌碼條件或 portfolio construction。不要為了讓 Sharpe/CAGR 變好而做任何額外修改。若發現其他問題，只能記錄為 observation，不得在本任務修復，除非該問題使 U1 無法按照本預註冊規格正確執行。

這句非常重要。

---

# 35. 本次最終裁決原則

整個 P0-U1 最重要的精神可以濃縮成：

> **先讓兩個裁判站在同一個考場，再討論誰的分數比較有用。**

現在 baseline 是：

```text
A 在 A universe 排
B 在 B universe 排
→ 再拿兩個 percentile 比
```

U1 只改成：

```text
A、B 都在同一個 C universe 排
→ 仍然使用原本 80/80
```

**其他東西一律不准碰。**

而且我現在反而建議你把原本的 P0 再拆細一點：

```text
P0-U1  共同比較母體
   ↓
P0-R1  Research / Live identity
   ↓
P0-I1  Investability Gate
   ↓
P1-M1  Momentum horizon autopsy
   ↓
P1-T1  Technical role / horizon
   ↓
P1-C1  Chip atomic-factor autopsy
```

尤其 **ADV100萬 → 1000萬不要現在改**。你目前文件很清楚：粗篩 L1 本來是 ADV1000萬，但正式投組使用的 `c2_fullpool` 卻是 ADV100萬，這個衝突很值得處理；只是應該留到 **P0-I1**，不要污染 U1。fileciteturn0file0L145-L170

如果照這份規格執行，**U1 跑完無論 Sharpe 變 1.3、1.1 還是 0.9，都會是一個有解釋力的結果**。這才真正保住你想維持的單發射擊制。
