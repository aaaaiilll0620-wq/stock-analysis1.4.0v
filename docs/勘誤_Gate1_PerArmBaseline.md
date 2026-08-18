# 勘誤 · Gate 1 的 per-arm baseline · **草案(待 Codex 審查)**

> **狀態**:草案。**未執行正式 Gate 1**,未產生任何 candidate 的 ΔIC / t / T\* / p-value。
> **裁決來源**:Codex 2026-08-02 —— 「採用 per-arm baseline 的執行規格勘誤:
> 第一批 A1–A4/C1/C3 對 V0;第二批 B1–B5/C2 對 V0-C3;12 arms 仍是同一個 joint max-t
> family,共用 I(t)、M\*、每次置換索引、N_PERM=2000、seed=20260731。」
> **本勘誤不改動任何門檻、樣本、seed、α、min_n、EPS_SD、報酬線或 arm 清單。**

---

## 1. 被勘誤的問題

三條已凍結條款無法同時滿足:

| # | 出處 | 條款 |
|---|---|---|
| P1 | 第一批 §5-2 表 | `ΔIC(t) = IC_arm(t) − IC_V0(t)` —— **全族單一 baseline = V0** |
| P2 | 第二批 §0-1 | 「第二批所有 arm 的對照組是 `V0-C3`」 |
| P3 | 第二批 §7 | `T*` 的置換族系是 **12 個 arm 一起算**,不得分批降低懲罰 |
| P4 | 第一批 §5-2 | 「arm runner **必須 import 這兩個函式,不得另寫一份**」 |

凍結實作 `delta_ic_t()` 算的是 `_t_of(ica - ic0[:, None])`,`ic0` 為 `(T,)` 向量廣播給
全部 K 個 arm → **實作層只表達得出單一 baseline**。P1+P4 與 P2+P3 因此互斥。

**這是預註冊層的缺口,不是實作疏忽。** 第一批 §5-2 凍結時第二批的 V0-C3 baseline
尚未寫入(第二批 §0-1 是後來凍結的),兩份文件各自自洽但合起來超出實作的表達能力。

## 2. 裁決與勘誤內容

**採 per-arm baseline。** 以下三條為勘誤正文,編號 E1–E3。

### E1 —— `ΔIC` 的配對基準改為逐 arm 宣告

`ΔIC_k(t) = IC_k(t) − IC_{base(k)}(t)`,其中 `base(k)` 由**凍結的宣告表**給定:

| arm | base(k) | 出處 |
|---|---|---|
| A1 A2 A3 A4 C1 C3 | **V0** | 第一批 §5-2 |
| B1 B2 B3 B4 B5 C2 | **V0-C3**(= 族內 C3 那一欄的分數) | 第二批 §0-1 |

宣告表**在看到任何 candidate 統計量之前寫死**,不得因結果調整。
`C3` 本身是第一批成員,**它自己仍對 V0 配對**,不對自己配對。

### E2 —— 配對與置換的共用範圍不變

`base(k)` 是 V0 或族內另一個 arm,兩種情形都在**同一組 `M*`、同一組 `I(t)`、
同一次置換的同一組打散報酬**上相減。`I(t)` 的定義完全不動:
「`fwd_x` **與** V0 分數 **與全部 12 個 arm 分數**都非缺的交集」——
C3 既是 arm 也是第二批的 baseline,本來就已在交集條件內,**共同樣本不因本勘誤改變**。

**G1-c(產業內中性化)下的 baseline 腿**(Codex 2026-08-02 §3 要求明寫):

> `neutral_by` 給定時,**V0 腿與 C3 腿都取產業內中性化後的 rank score**,
> 與各 candidate arm 走**完全相同**的前處理 —— 逐 as_of 在 `I(t)` 內取 rank、
> 減去該股所屬產業的 rank 平均、再 z 標準化。
> 實作見 `build_month_blocks()`:`r0s`(V0 腿)與 `Rs`(全部 12 個 arm 腿,**含 C3**)
> 在同一個 `if neutral_by is not None:` 分支內以同一式中性化,之後才進 `_z()`。
> 因此 G1-c 的 `ΔIC` 是「中性化分數之間」的差,不會出現
> 「中性化的 arm 減未中性化的 baseline」這種混用。
> **報酬腿一律不中性化**(中性化的對象是分數,不是報酬),此點與勘誤前相同。

**baseline mapping 在 G1-a 與 G1-c 之間完全相同** —— 中性化只改分數的前處理,
不改「誰對誰配對」。兩版共用同一份 `baseline_idx`。

### E3 —— `max` 的範圍不變:跨全族 12 個 arm

每次置換取的 `max` 一律跨全部 12 個 `t`,**不因 baseline 不同而分組**。
分組取 max 等於分批降低多重比較懲罰,第二批 §7 明文禁止。

## 3. 凍結函式的最小 per-arm-baseline 設計

**設計原則:省略新參數時,行為與勘誤前逐位元相同。** 既有 11 項測試一字未改。

`scripts/gate1_delta_ic_maxt.py` 只動三處,新增 47 行、修改 3 行:

```python
V0_BASELINE = -1                      # 宣告表中代表「對 V0」

def _check_baseline_idx(baseline_idx, K) -> np.ndarray:
    # 長度須為 K;值須為 -1 或 0..K-1;不得自我指涉(ΔIC 恆 0 = 恆等式非檢定)

def _delta_ic_matrix(ica, ic0, baseline_idx=None) -> np.ndarray:
    if baseline_idx is None:
        return ica - ic0[:, None]                    # ← 勘誤前的原式,原封不動
    b = _check_baseline_idx(baseline_idx, ica.shape[1])
    base = np.where(b[None, :] == V0_BASELINE, ic0[:, None], ica[:, np.clip(b, 0, None)])
    return ica - base

def delta_ic_t(blocks, baseline_idx=None):           # ← 新增選用參數
    ica, ic0 = _ic_row(blocks)
    return _t_of(_delta_ic_matrix(ica, ic0, baseline_idx))

def joint_maxt_null(blocks, n_perm=N_PERM, seed=SEED, alpha=ALPHA, baseline_idx=None):
    if baseline_idx is not None:
        _check_baseline_idx(baseline_idx, K)         # fail fast:不跑完 2000 次才發現宣告錯
    ...
        t = _t_of(_delta_ic_matrix(ica, ic0, baseline_idx))   # ← 迴圈內唯一改動
```

**沒有動到的東西**(逐項列出,供審查核對):

- `build_month_blocks()` —— 共同月份 / 共同股票集 / 缺值規則 / `neutral_by` 全部原封不動
- `_ic_row()`、`_z()`、`assert_same_months()` —— 未修改
- `_t_of()` 與 `EPS_SD` 守衛 —— 未修改,見 §4 的語意說明
- 置換機制 —— `rng = default_rng(seed)`、逐 block `rng.permutation(y)`、
  呼叫順序與次數完全不變 → **相同 seed 在 `baseline_idx=None` 下產生相同虛無分布**
- `T*` 的取法(`percentile(maxt, 100(1−α))`)、`rho_hat` 的估計與退化回報
- 全部凍結參數:`MIN_N=30` / `N_PERM=2000` / `SEED=20260731` / `ALPHA=0.05` /
  `EPS_SD=1e-12` / `N_ARMS=12` / 主時鐘 / 報酬線 / AND 判定

## 4. 兩個語意問題的處理(**請 Codex 明確裁示**)

裁決文只點名了 max 的範圍(已寫入 E3)。以下兩點會影響數值且事後補不回來,
本草案先採保守處理,但需要你明確確認:

### 4-1 `EPS_SD` 退化守衛的層級

`_t_of` 的守衛是「`sd(ΔIC) < EPS_SD` → `t` 記 0」。在 per-arm baseline 下,
B 系列的 `ΔIC` 是 `ica[:,k] − ica[:,j]`(兩個都是估計量),
而非「對固定的 V0」。**本草案的處理:守衛層級不變,直接套在 per-arm 的 `ΔIC` 上。**

語意上這是自洽的 —— 守衛問的是「這個 arm 與**它自己宣告的** baseline 有沒有數值差異」,
B arm 若逐列等於 C3,`ΔIC ≡ 0`,記 `t = 0` 正是應有的結論(已由
`test_arm_equal_to_its_baseline_arm_gives_zero_t` 覆蓋)。

⚠ 但要注意一個**不對稱**:對 V0 的 arm,baseline 是固定量;對 C3 的 arm,
baseline 自身有抽樣變異,所以 `sd(ΔIC)` 的分母意義略有不同,
B 系列的 `ΔIC` 變異一般會**大於**同等效果量的第一批 arm。
這會讓 B 系列在同一個 `T*` 下較難通過。**本勘誤不做任何補償** ——
補償等於改統計定義。此為事前揭露,不是事後解釋。

### 4-2 `rho_hat` 的解讀

`allt` 現在混了兩種 baseline 的 t。`rho_hat`(arm 間相關)仍照原式估計,
但它的意義從「共同 V0 腿造成的相關」變成「共同 V0 腿 **+** 共同 C3 腿造成的相關」。
**本草案不改估計方式**,只要求在結果報告中改述為
「族內 t 的平均兩兩相關(混合基準)」,不再解讀成單一來源。

## 5. 測試

新增 `tests/test_gate1_per_arm_baseline.py`(11 項),既有
`tests/test_gate1_delta_ic.py`(11 項)**一字未改**。

| # | 測試 | 驗什麼 |
|---|---|---|
| 1 | `default_is_bitwise_identical_to_all_v0` | 省略參數 vs 顯式全 V0 → `t` / `maxt` / `allt` 逐位元相同 |
| 2 | `per_arm_baseline_matches_manual_pairing` | per-arm ΔIC = 手算逐月配對相減(atol=0) |
| 3 | `c3_itself_still_paired_against_v0` | 扮演 C3 的 arm 自己仍對 V0(E1) |
| 4 | `arm_equal_to_its_baseline_arm_gives_zero_t` | 退化守衛在 per-arm 下的語意(§4-1) |
| 5 | `maxt_is_taken_across_the_whole_family` | max 跨全族 12 個(E3) |
| 6 | `shared_permutation_across_mixed_baselines` | baseline 腿與 arm 腿共用同一組打散(E2) |
| 7 | `same_seed_reproduces_with_per_arm_baseline` | 可重現性 |
| 8–11 | `self_referential` / `out_of_range` / `wrong_length` / `null_validates_before_permuting` | 宣告表的 fail-closed |
| 12 | `declaration_rejects_silent_coercion`(10 個參數化案例) | 拒絕浮點 / bool / 二維 / 巢狀 / 純量 / 字串,**不做靜默轉型** |
| 13 | `numpy_int_array_is_accepted` | 正確型別(list / int32 / int64 ndarray)結果一致,不過度嚴格 |

第 6 項是關鍵:兩個完全相同、baseline 同為 C3 的 arm,每次置換的 `t` 必須逐位元相同。
若 baseline 那一腿各自重抽,這裡會失敗。

第 12 項對應 Codex §3:`np.asarray(x, dtype=int)` 會把 `2.0`→`2`、`True`→`1`、
把二維壓平。宣告表是凍結研究設定,型別出錯必須 raise 讓人看見,
否則「宣告表寫錯」會變成「跑出一組看起來正常的數字」。

## 6. 尚未執行

本勘誤**只改實作與測試**。正式 Gate 1(`--part gate`)仍 fail-closed,
待本草案通過 Codex 審查後才解除。屆時 `scripts/gate1_assemble_12arm.py` 會以
`baseline_idx = [-1]*6(A1 A2 A3 A4 C1 C3) + [idx_C3]*6(B1..B5 C2)` 呼叫凍結函式。
