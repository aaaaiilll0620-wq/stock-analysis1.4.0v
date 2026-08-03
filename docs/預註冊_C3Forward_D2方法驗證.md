# D2 方法驗證協定(synthetic method-validation protocol)—— 草案,未凍結

**狀態**:🚧 **草案,未凍結**。**P1–P8 政策已凍結**(見 §2);**#2(main DGP 實際
係數)仍開啟,因此文件仍是草案**。**P7 code-check、P8 timing-pilot 均尚未執行,
只代表沒有執行結果,不代表 #5、#1 設計仍開啟**(#5、#1 設計均已關閉,見 §3)。
**P8 只凍結 timing-pilot 的設計規格本身——不代表方法 D 可行、不代表 72h 判定
已經跑過、不代表 timing pilot 已執行。**
本檔由 Codex 於 2026-08-03(經 `GPT answer.md` 轉達)指示建立,歷經多輪修正與使用者政策裁定。

**本檔不修改、不影響 Gate1 任何產物或既有裁定;不執行任何 calibration、validation、
c-sign preflight、timing pilot、synthetic 驗證、績效/OOS 或 prospective collection。
本檔已於 `aab856f`(P7 code-check)、`dfab623`(P8 timing-pilot)兩次 commit 中
追蹤、凍結;本輪(P8.1 amendment)寫入前為未 stage/commit 狀態,是否 stage/commit
依當輪授權範圍而定,不假設沿用先前輪次的狀態。**

---

## §0 強制聲明

> **這是 synthetic method-validation protocol,不是 C3 正式前瞻預註冊,也不授權任何績效/OOS。**

本檔驗證的是「用來判定 C3 是否合格的統計方法本身」的操作特性(型一誤差 size、檢定力 power、
可行性 feasibility),比照本專案既有先例 `scripts/gate1_delta_ic_maxt.py` 的 `synthetic_suite()`
(T1–T4)——用雜訊/已知效應量校準檢定程序,**不是**對 C3 candidate 本身下任何結論。

---

## §1 目的與範圍

驗證 D2 這一關要用的方法驗證協定(size / power / feasibility),決定哪一組 `(method, M)`
有資格被 D1(window selection)採用。D1 本身**仍暫停,等待 D2 通過**。本檔只處理 D2,
不涉及 D15(產業 PIT)、D16(anchor chain)、D5(MDD 護欄)——那三項**已有部分政策決策,
但仍各自有 blockers**,且不在本文件範圍內。

---

## §2 Policy Register(P1–P7,已凍結規格)

### P1 · 總量與分解

| 項目 | 值 |
|---|---|
| `N_outer` | **138** = main(126)+ partial-stat(6)+ code-check(6) |
| `K` | **516** = main K(504)+ partial-stat K(12);code-check 依規則不計入 `K` |

### P2 · 誤差率

| 項目 | 值 |
|---|---|
| `FWER_target` | **0.10**(只管 MC meta-test,與 Stage 2 power 判定的 95%/80% 是不同機制) |
| `alpha_test` | **0.05**(固定,C/D 各自的單尾 reject 門檻) |

### P3 · 方法 D 可行性上限(scope 已釐清)

**72 小時牆鐘時間 / 8 核心**;不得為了趕這個上限而降低 `R_MC`/`B_test`/grid 密度。

**Scope(2026-08-03 裁定,不得再擴張解讀)**:這條 72h/8-core cap **只約束方法 D 在
Stage1/Stage2 正式規模下的 timing-pilot 外推**。**不適用於**方法 C、calibration
search/validation,或 c-sign preflight——這三者的計算成本只作為 #2 的實作可行性參考資訊
(見 P5 末段的 static cost),**不拿 P3 判它們 pass/fail**,也**沒有**為它們另設時間上限;
若要設,須另請使用者作獨立政策決定。

### P4 · Failure 語義

任一數值計算或 bootstrap 失敗 → 該 `(method, M, DGP cell)` 記為 fail;**不得剔除該複製
另抽補上**;**不連坐**同一 method 的其他 M(各 M 獨立判定)。

---

### 2.A Stage 1(main / partial-stat / code-check)

**Main topology(7 個 primary DGP 情境)**:

| # | 情境 | 說明 |
|---|---|---|
| 1 | (a, d) | a = sharp-zero(訊號恰為零,屬 **H0 interior**,不是邊界),d = 對應雜訊/相依結構選項 |
| 2 | (b, d) | b = equal-positive boundary(兩方法訊號相等且為正的邊界) |
| 3 | (b, AR φ=.3) | 同 b,雜訊改一階自我迴歸、φ=.3 |
| 4 | (b, AR φ=.6) | 同 b,φ=.6 |
| 5 | (c, d) | c = C3-worse(C3 劣於 V0 的情境) |
| 6 | (c, AR φ=.3) | 同 c,φ=.3 |
| 7 | (c, AR φ=.6) | 同 c,φ=.6 |

具體生成式見 §2.B(P5)。

**Nuisance 參數網格**:`rho_pair = {0, .5, .9}`(3 值);`industry symmetric = {(0,0), (.5,.5)}`
(2 組);`M = {24, 36, 48}`(3 個窗長,月數)。

**Main 分支**:DGP cells = 7 × 3 × 2 = **126**。Main `K` = 126 × 2 methods(C、D)× 2 endpoints = **504**。

**Partial-stat 分支**:targets = `{(0, .020), (.020, 0)}`,每個 `M` 各跑一次 → 6 個 outer cells;
`K` = 6 × 2 methods = **12**。partial 校準容許誤差 **±.0005**;達不到即該 cell 直接 fail。

**Code-check 分支**:targets = `{(0, −.020), (−.020, 0)}`,每個 `M` 各一次 → 6 個 outer cells;
`R = 2000` 單批,**不進 `K`**。**精確 PASS 門檻仍 UNRESOLVED(見 §3 #5)。**

**`R_MC = 20000`,分兩個獨立 batch。**

```
alpha_batch = sqrt(FWER_target / K)                     # = sqrt(.10 / 516)
c = min{ k : P[Bin(R_MC, .05) >= k] <= alpha_batch }     # exact binomial
```

**binding cell 的 size-fail 判準**:兩個獨立 batch 的 rejection count **都** ≥ `c`,才判該 cell
size fail;任一 P4 的 failure 語義情境發生 → 直接 fail,不須等兩個 batch 都跑完。

**方法角色**:A = sharp-zero diagnostic;B = iid diagnostic(僅供診斷,不得用於任何 confirmatory
判定)。**confirmatory 只允許 C 與 D。**

### 2.A.1 方法 C —— Bartlett NW(lag=12)HAC 檢定

```
γ(j) = (1/M) Σ_{t=j+1}^{M} (x_t − x̄)(x_{t−j} − x̄),  j = 0, ..., 12
V     = γ(0) + 2 Σ_{j=1}^{12} (1 − j/13) γ(j)     # Bartlett kernel, lag=12
t     = mean(x) / sqrt(V / M)
p     = 1 − Φ(t)                                   # 單尾
reject if p ≤ .05
V ≤ 0 或 V 為 NaN → **立即使所在 (method, M, DGP component cell) fail**(不是只讓該次判定 fail)
```

### 2.A.2 方法 D —— centered circular-block bootstrap(非 studentized)

```
L = 12(block 長度);B_test = 1999(bootstrap 次數)
x̄     = mean(x)
T_obs = x̄                              # 原始未中心化序列,不得先 center 再取 mean
x0_t  = x_t − x̄                        # 只有 bootstrap 抽樣來源做中心化
每次獨立抽 ceil(M/L) 個 start,start 均勻取自 {0, ..., M−1},取 circular block,串接後截成長度 M
T_b = mean(resampled x0)
p = (1 + #{T_b ≥ T_obs}) / (B_test + 1)            # = /2000
reject if p ≤ .05
SeedSequence.spawn() 為每個 outer replicate 產生獨立、可重現的子種子
bootstrap 失敗 / NaN / 拒絕判定缺失 → **立即使所在 (method, M, DGP component cell) fail**
```

### 2.A.3 Stage 2

- `R_power = 10000`,單批,獨立 seed namespace(與 Stage 1 不共用)。
- nuisance 沿用 Stage 1 的 3 個 `rho_pair` × 2 個 `industry symmetric` 組合(共 6 組)。
- **9 組 effect pair**:**binding**(進合格判定):`(.002,.002)`、`(.002,.005)`、`(.005,.002)`;
  **descriptive**(僅描述):`(.001,.001)`、`(.005,.005)`、`(.010,.010)`、`(.020,.020)`、
  `(.001,.005)`、`(.005,.001)`。
- `N_outer_power = 9 × 6 × 3 = 162`;C、D 兩方法共用同一組抽樣(draw)以配對比較。
- 每個 `(method, M)` 有 **18 個 binding cells**(3 個 binding pairs × 6 個 rho×industry 組合)。
- **判定規則**:Bonferroni simultaneous one-sided lower bounds,family coverage ≥ 95%,
  全部 18 格各自 power 下界 ≥ 80% 才算通過。底層公式為 **one-sided Clopper–Pearson**:
  ```
  n = R_power = 10000
  r = 該 binding cell 的 joint-AND rejection count
  alpha_cell = 0.05 / 18
  若 r = 0:  L = 0
  否則:     L = Beta^{-1}(alpha_cell; r, n − r + 1)     # scipy.stats.beta.ppf(alpha_cell, r, n-r+1)
  ```
- **C vs D tie rule**:`abs(min_lower_bound_C − min_lower_bound_D) < 1pp → 選 C；否則選較高者。`
- **qualification**:以 `(method, M)` 為單位——該 `M` 底下 Stage 1 的 main 與 partial cells
  **全部**通過,才合格,才有資格進 Stage 2 power 判定。
- **D 的淘汰規則**:若 method D 的 timing 超過 72h(P3)→ **同時移除 `(D,24)`、`(D,36)`、`(D,48)`**,
  不是只移除觸發超時的那一個 `M`。
- **M 選擇順序**:24 → 36 → 48 依序嘗試,選「最短、且合格、且 power 通過」的 `M`。
- **整體 fail-closed**:無合格 `(method,M)`,或試到 `M=48` 仍不通過 → 整個 D2 fail-closed,
  **不得開始任何前瞻研究(C3 prospective collection)**。

### 2.A.4 Root seeds 與 seed 階層(Stage1/Stage2/TimingPilot)

**三個 root seed(128-bit,取自 UTF-8 namespace 字串之 SHA256 前 16 bytes,big-endian;
以 `np.random.SeedSequence(int(hex,16))` 使用)**:

| Namespace | Root seed(hex) |
|---|---|
| Stage1 | `0xd8262df3d547bfa6df93cfa3148e1701` |
| Stage2 | `0x4e11b62641787fd8cfff76c57a32ac19` |
| TimingPilot | `0xb95ec2b993477c0216990dc8fcc61322` |

**Stage1、Stage2、TimingPilot 三個 root 不可互用 seed,也不可與 P5/P6 的 search/validation/
sign root 混用。**

**Canonical cell 順序**:
- Stage 1 · main(126):`topology(表 2.A 順序 1~7) → rho_pair(0,.5,.9) → industry_symmetric((0,0),(.5,.5)) → M(24,36,48)`;
  `cell = ((topology_idx×3+rho_idx)×2+ind_idx)×3+M_idx`,`cell=0..125`。
- Stage 1 · partial-stat(6):`target((0,.020),(.020,0)) → M(24,36,48)`;`cell=target_idx×3+M_idx`,`0..5`。
- Stage 1 · code-check(6):`target((0,−.020),(−.020,0)) → M(24,36,48)`;`cell=target_idx×3+M_idx`,`0..5`。
- Stage 2(162):`pair(binding三組→descriptive六組,共9組) → rho_pair(0,.5,.9) → industry_symmetric((0,0),(.5,.5)) → M(24,36,48)`;
  單一 `(method,M)` 的 18 個 binding cells = 固定該 `M`、只取 binding 三組 pair 的
  `pair_idx(0..2)×rho_idx(0..2)×ind_idx(0..1)` 子集。

**Seed spawn 階層**:
1. **Stage1 root 一次性 `spawn(138)`**,`main=0..125`、`partial-stat=126..131`、
   `code-check=132..137`(**禁止三分支各自從 `spawn(0)` 重建**,避免 collision)。
   Stage2 root 獨立 `spawn(162)`,`global_cell=0..161`。
2. 每個 cell seed → 依 batch 順序 spawn **batch seed**(main/partial 各兩個獨立 batch;
   code-check、Stage2 皆單批)。
3. 每個 batch seed → 依 `replicate index 0..R−1`(main/partial `R_MC`=20000;code-check
   `R`=2000;Stage2 `R_power`=10000)spawn **outer seed**。
4. 每個 outer seed → 固定 spawn `[DGP seed, D-raw bootstrap seed, D-ind bootstrap seed]`。

C、D 兩方法與 raw/ind 兩變體**共用同一個 DGP seed 產生的 draw**;**worker 排程不得改變
上述 seed 映射**。

---

### 2.B P5 · DGP Reference Calibration(2026-08-03 正式凍結)

#### 2.B.1 Main DGP 生成式

**規模**:`N = 1200` 檔/月;`G = 10` 組等組(每組 120 檔)——僅用於隔離產業中性化機制,
不代表任何真實母體規模。

**產業指派(確切演算法)**:每個 outer replicate,用該 replicate 的 DGP seed 對
`{0,...,1199}` 做一次 **permutation**,依序切成 10 組、每組連續 120 個(permutation 後的)
索引;**跨該 replicate 的全部 M 個月固定**,只在跨 replicate 間重抽。

**AR(φ) vs iid 拓撲的適用範圍**:同一 cell 內,`common_idio_{i,t}`(逐股!非全市場單一
scalar——單一 scalar 加進每檔股票的 score 只是整體平移,不改變排名,對 Spearman IC 無作用)、
`V0-idio`(`ξ_V0_{i,t}`)、`C3-idio`(`ξ_C3_{i,t}`)、產業 shock `g_{k,t}` **四者**,
在 AR 拓撲下**一律**用同一個 φ 的 stationary AR(1):
```
u_0 ~ N(0,1);  u_t = φ·u_{t-1} + sqrt(1-φ²)·z_t,  z_t ~ N(0,1) i.i.d.
```
在 `d`(iid)拓撲下,四者**全部**改成單純 i.i.d. `N(0,1)`。**`fwd_x_{i,t}` 本身在 AR 與 iid
兩種拓撲下永遠是 i.i.d. `N(0,1)`**,AR/iid 的區別從不作用在 `fwd_x`。`fwd_x` 僅稱
**synthetic latent rank outcome,不賦予投資報酬或績效意義**。

**`rho_pair`(加 industry 前的量)**:
```
η_V0_idio_{i,t} = √ρ_pair · common_idio_{i,t} + √(1-ρ_pair) · ξ_V0_{i,t}
η_C3_idio_{i,t} = √ρ_pair · common_idio_{i,t} + √(1-ρ_pair) · ξ_C3_{i,t}
```
`ρ_pair` 是 industry shock 混入**之前**,`η_V0_idio` 與 `η_C3_idio` 的同期相關係數。

**Industry shock 混入(在 `rho_pair` 之後,V0/C3 用同一個 `g`、同一個 `ρ_ind`)**:
```
η_V0_{i,t} := √(1-ρ_ind)·η_V0_idio_{i,t} + √ρ_ind·g_{k(i),t}
η_C3_{i,t} := √(1-ρ_ind)·η_C3_idio_{i,t} + √ρ_ind·g_{k(i),t}
```

**θ / h / 負載(僅 AR 拓撲的 b/c 變體使用;`(b,d)`/`(c,d)` 用常數負載,不涉及 θ)**:
```
θ_0 ~ N(0,1);  θ_t = φ·θ_{t-1} + sqrt(1-φ²)·z_t,  z_t ~ N(0,1) i.i.d.     # 同一 cell 同一 φ
h(θ) = Φ(θ)                                                                # 標準常態 CDF
b_C3(t) = a_C · h(θ_t)
b_V0(t) = a_V · h(−θ_t)
```
`(b,d)`/`(c,d)`(iid 拓撲):`b_C3(t)=a_C`、`b_V0(t)=a_V`(常數,無 θ)。

```
score_V0_{i,t} = b_V0(t)·fwd_x_{i,t} + η_V0_{i,t}
score_C3_{i,t} = b_C3(t)·fwd_x_{i,t} + η_C3_{i,t}
IC_V0(t) = Pearson( zscore_ddof0(rank(score_V0(·,t))), zscore_ddof0(rank(fwd_x(·,t))) )   # raw,neutral_by=None
IC_C3(t) = Pearson( zscore_ddof0(rank(score_C3(·,t))), zscore_ddof0(rank(fwd_x(·,t))) )   # raw,neutral_by=None
x_t(餵給方法 C/D) = IC_C3(t) − IC_V0(t)
```
(`ind` readout 的對應定義另見 P6 §2.C——`score` 那一腿改用 `neutral_by=industry` 去均值,
`fwd_x` 那一腿不中性化。)

**三情境**:

- **a(sharp-zero)**:`a_V=a_C=0`。**`E[finite-N monthly sample IC]=0`;每月實際 sample IC
  仍是隨機量、會波動,不是每月恆等於 0。** 無自由參數,**跳過係數搜尋**,狀態為 **N/A**,
  不得寫成「校準已通過」。
- **b(equal-positive boundary)**:AR 拓撲 `a_C=a_V=a010_AR`;iid 拓撲 `a_C=a_V=a010_iid`。
  **`E[finite-N monthly sample ΔIC]=0`,分布對 0 對稱**——AR 拓撲下由 `θ↔−θ` 交換對稱保證
  (`{θ_t}` 在全域負號下與自身同分布,`a_C=a_V` 時交換 `θ` 恰好交換 `b_C3↔b_V0` 的角色,
  兩者聯合分布不變);iid 拓撲下 `η_V0_idio/η_C3_idio` 本已可交換,不需要 θ 機制。
  **這是分布層級的結構保證,不是「`ΔIC` 逐月恆為 0」**——每月 sample `ΔIC` 仍波動,
  在所有 `(rho_pair, rho_ind, M)` cell 都成立,與 φ/ρ_pair/ρ_ind 取值無關。
- **c(C3-worse)**:AR 拓撲 `a_V=a010_AR`、`a_C=a005_AR`;iid 拓撲 `a_V=a010_iid`、`a_C=a005_iid`
  (`a_V≠a_C`,`θ↔−θ` 對稱不適用,不會被強制拉回 0)。**只要求所有正式 raw/ind nuisance
  cells 的 `expected ΔIC < 0`**(符號要求,不要求精確等於任何特定值),由 **P6 sign
  preflight** 驗證。

#### 2.B.2 Reference-cell calibration

**Reference**:`rho_pair=0`、`rho_ind=0`、`N=1200`,**raw** endpoint。Target 是
**`E[finite-N monthly sample Spearman IC]`**,不是漸近 population 點值。`.010`/`.005`
**只在 reference raw endpoint 定義訊號尺度,是事前 synthetic policy targets**——
**不引用任何歷史 V0/Gate1 IC 數字作為支持依據**。凍結後,**同一組係數套用到所有
`rho_pair`、`rho_ind`、`M`、raw/ind 組合,禁止逐 cell 或逐 endpoint 重新校準**。

**四個係數(只需四個,不按 φ 分別重校準——stationary AR(.3)/AR(.6) 單月邊際分布相同)**:

| 係數 | 用途 |
|---|---|
| `a010_iid` | 情境 b(iid)兩臂共用;情境 c(iid)V0 臂 |
| `a005_iid` | 情境 c(iid)C3 臂 |
| `a010_AR` | 情境 b(AR)兩臂共用;情境 c(AR)V0 臂 |
| `a005_AR` | 情境 c(AR)C3 臂 |

**校準用的 IC 計算語義(修正:reference 是 raw endpoint,不涉及產業中性化)**:
```
score/outcome 各自 rank → z-score(ddof=0) → Pearson 相關      # neutral_by=None
```
連續資料、無 tie 時,rank 後 z-score 再算 Pearson 與 sample Spearman **數值等價**
(沿用本 repo 既有慣例,`gate1_delta_ic_maxt.py::_z()` 的 docstring 明寫「rank 之後
標準化 → Pearson 等於 Spearman」)。**`neutral_by=industry`(產業內去均值中性化)只用於
P6 的 `ind` readout,以及 Stage1/Stage2 正式的 `ind` endpoint——不用於 P5 reference
calibration 本身,因為已凍結的 reference target 明確是 raw endpoint;即使 `rho_ind=0`,
`ind` 轉換在有限樣本仍可能改變 IC,因此 `ind` 結果仍有定義,只是不作為四個係數的校準
目標,而由 P6 獨立檢查。上一版寫「正式係數須用 `neutral_by` 校準」是矛盾,已撤回。**

**Pearson→Spearman 公式僅供搜尋 grid 的初始參考**(`IC≈(6/π)arcsin(ρ/2)`,`ρ=a/√(a²+1)`),
**不得**直接當成凍結係數——正式係數須用上述凍結的 raw IC 計算語義獨立校準,並在
Stage1/Stage2 開跑前寫死,**正式 cell 內禁止調參**。

#### 2.B.3 校準精度政策(2026-08-03 正式凍結,不再稱 proposed)

```
calibration_alpha_family   = 0.05
alpha_per_coef (Bonferroni)= 0.05 / 4 = 0.0125          # 4 個係數同時保護
T_search = T_validate      = 84,000
```
`T` 推導(規劃半寬 ≤.00025,留出中心偏差空間,不用剛好等於最終 ±.0005 容許誤差):
```
σ_IC ≈ 1/√(N−1) = 1/√1199 ≈ 0.02888            # 漸近公式,population correlation≈0 時
T ≥ ceil( (z_{0.99375}·σ_IC/.00025)² ) = ceil( (2.50×0.02888/.00025)² ) = 83,403 → 84,000(進位)
```

**搜尋 grid(14 點,bracket `[0,1]`,固定不迭代加密)**:
```
{0, 1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 1e-1, 2e-1, 5e-1, 1.0}
```

**完整搜尋規格**:
1. 用同一批 `T_search=84,000` 個 CRN 抽樣,依序算出 14 個 grid 點的 `g(a_k)`。
2. **由小到大掃描**相鄰對,用 `(target−g(a_k))×(target−g(a_{k+1})) ≤ 0` 判定是否 bracket
   target(方向無關,不受非單調影響);**取索引最低的第一個滿足此式的相鄰對**。
3. 在該相鄰對做**一次**線性內插求出 `a*`。
4. **用同一批 `T_search` CRN 抽樣,在 `a*` 上實際重新計算一次 `g(a*)`**(不得只信內插值)。
5. **Search acceptance threshold:`|g(a*) − target| ≤ .00025`**。
6. 未達門檻 → **直接 search fail**,不得臨時加密 grid、不得迭代、不得改 bracket。
7. target 落在已算 grid 範圍之外 → 同樣 search fail,不得外插超出 `[0,1]`。

**Validation(僅一次,不可回頭)**:
```
CI = x̄ ± t_{T_validate−1, 1−alpha_per_coef/2} · s / √T_validate
```
用**獨立、已凍結**的 validation seed 抽**全新** `T_validate` 筆;**CI half-width 須 ≤.00025,
且整個 CI 必須落在 target±.0005 內才 accept**,只看點估計不算數。**看過 validation 結果後,
不得重搜、不得換 seed。失敗代表 DGP calibration 未完成,預註冊維持 blocked,
不是 Stage1 component-cell 的個別 fail(層級不同)。**

**Calibration seeds(128-bit,不得與 Stage1/Stage2/TimingPilot/P6 root 混用)**:

| 用途 | seed |
|---|---|
| search | `0x1917a59d5bf16293b618130185cd344f` |
| validation | `0x4570b0bb18ed1e52fb7962738754fefd` |

**Seed 階層**:
```
search_root.spawn(4)      → [a010_iid, a005_iid, a010_AR, a005_AR]
validation_root.spawn(4)  → 同一順序
每個 coefficient child → 一次性 spawn(84000) → draw 0..83999
```
**每個 draw 的 latent component spawn 順序(iid 型)**:
```
draw_seed.spawn(2) → [fwd_x_seed, noise_seed]
fwd_x_seed → 1200 個 i.i.d. N(0,1) → fwd_x_i
noise_seed → 1200 個 i.i.d. N(0,1) → ξ_i
score_i = a · fwd_x_i + ξ_i
sample_IC = Pearson( zscore_ddof0(rank(score)), zscore_ddof0(rank(fwd_x)) )   # neutral_by=None,見上
```
**每個 draw 的 latent component spawn 順序(AR 型)**:
```
draw_seed.spawn(3) → [fwd_x_seed, noise_seed, theta_seed]
fwd_x_seed → 1200 個 i.i.d. N(0,1) → fwd_x_i
noise_seed → 1200 個 i.i.d. N(0,1) → ξ_i
theta_seed → 1 個 N(0,1) → θ                     # 該次獨立 draw 的單一純量,非逐股
                                                  # (AR calibration draw 不模擬跨月遞迴,
                                                  #  但每個獨立 draw 仍須抽一次 θ 並套用
                                                  #  h(θ)=Φ(θ),這正是與 iid 型的差異所在)
loading = a · Φ(θ)
score_i = loading · fwd_x_i + ξ_i
sample_IC = Pearson( zscore_ddof0(rank(score)), zscore_ddof0(rank(fwd_x)) )   # neutral_by=None,見上
```

**Static cost(feasibility 參考資訊,歸於 #2,不受 P3 的 72h/8-core 約束,未另設時間上限)**:
```
Search      = 4 × (14+1) × 84,000 × 1,200 = 6.048e9    # 14 grid 點 + 1 次 a* 複算
Validation  = 4 × 84,000 × 1,200           = 0.4032e9
(Sign preflight base DGP rows,見 P6)       = 1.8144e9
合計 base/candidate row-scale             = 8.2656e9
```
**這只是 row-scale 計數,不是牆鐘時間估計**——未計入兩臂 score 計算、raw/ind rank/
neutralization 各自的常數倍成本。**P3 的 72h/8-core 只約束方法 D 的 timing-pilot 外推,
不適用於此處;是否要為 calibration/sign 另設時間上限,需要另一次獨立的使用者政策決定。**

---

### 2.C P6 · C-sign Preflight(2026-08-03 正式凍結)

**獨立 root,不與 Stage1/Stage2/TimingPilot/P5 root 共用**:
```
namespace = "C3Forward-D2-DGPSignPreflight-v1"
root      = 0xa9d4d1cc8db508038233f014ceb404f7
```

**18 個 DGP cells(不是 36)**:`topology(c,d / c,AR φ=.3 / c,AR φ=.6) → rho_pair(0,.5,.9)
→ industry(0,.5)`;`cell = (topology_idx×3+rho_idx)×2+ind_idx`,`cell=0..17`。`M` 不列入
(結構理由:stationary marginal 的 expected monthly `ΔIC` 不依賴 `M`)。

**endpoint 不是獨立 DGP 維度**:每個 DGP draw 只生成**一份**資料,`raw` 與 `ind` 是對
**同一份**資料套用兩種凍結轉換,因此 `18 cells × 2 readouts = 36 個 inferential
components`,底層只有 18 條獨立隨機性來源。**`raw`/`ind` 使用同一份 DGP draw、
相同股票、相同產業標籤**,只差在轉換方式:

```
raw:  score_V0/score_C3 與 outcome(fwd_x) 各自 rank → z-score(ddof=0) → Pearson
      (neutral_by=None,同 §2.B.2 校準用的語意)

ind:  score_V0/score_C3 先取全體 rank,各自減去「該股所屬產業組的 rank 平均」,
      再 z-score(ddof=0);outcome(fwd_x) 那一腿**不做產業中性化**
      (與 gate1_delta_ic_maxt.py 既有定義「報酬那一腿不中性化,中性化的對象是分數」
      逐字一致);兩者再算 Pearson。
```
`common_idio`、`ξ_V0`、`ξ_C3` 均為**各 1200 個逐股 draw**(非全市場單一 scalar,
理由見 §2.B.1)。

**AR φ=.3/.6 的說明**:每個 sign replicate 是**單一 stationary 月**,不跑跨月遞迴,
`θ~N(0,1)` 單次抽樣、`φ` 不進生成式,故 AR(.3)與 AR(.6)生成式相同。**保留兩個 formal
label 只作重複 implementation audit 用。此 preflight 只驗 marginal sign,不驗 AR
temporal recursion 本身;若要驗證 recursion,須另定 path length(多月合成序列)的
獨立檢定,不得與此混稱。**

**Seed 階層**:
```
sign_root.spawn(18)      → 依 canonical 順序(topology→rho_pair→industry)得 18 個 cell seed
每個 cell seed.spawn(R_sign=84,000) → replicate seed 0..83,999
每個 replicate seed.spawn(7),固定順序(不論該 cell 用不用得到全部都要 spawn):
  [1] outcome_seed         → outcome_i ~ N(0,1), i=1..1200      # = fwd_x,一律使用
  [2] common_idio_seed     → common_idio_i ~ N(0,1)             # 一律抽,套 rho_pair 混合
  [3] V0_idio_seed         → ξ_V0_i ~ N(0,1)                     # 一律使用
  [4] C3_idio_seed         → ξ_C3_i ~ N(0,1)                     # 一律使用
  [5] industry_shock_seed  → g_k ~ N(0,1), k=1..10               # 只在 industry=.5 混入採用;
                                                                    industry=0 時抽出但丟棄
  [6] industry_perm_seed   → permutation({0..1199}) → 10 組       # industry=0 與 .5 都必須
                                                                    採用——raw/ind 共享同一組
                                                                    固定產業標籤,ind endpoint
                                                                    即使 industry loading=0
                                                                    仍要依此標籤做中性化
  [7] theta_seed           → θ ~ N(0,1)                           # 只在 AR 拓撲採用;
                                                                    topology=(c,d) 時抽出但丟棄
```
同一 replicate 內,這組 permutation 跨 `raw`/`ind` 共用。套用已凍結的 P5 係數:
`(c,d)` 用 `a010_iid`/`a005_iid`;`(c,AR φ=.3/.6)` 用 `a010_AR`/`a005_AR`(不按 φ 分別校準)。

**判定規則**:
```
alpha_sign_family  = 0.05
alpha_sign_percell = 0.05 / 36                                      # Bonferroni,36 個 component
UpperCI(component) = mean_ΔIC + t_{R_sign−1, 1−alpha_sign_percell} · s_ΔIC / √R_sign
```
**通過條件**:36 個 `UpperCI` **全部 < 0**。**任一未過 → DGP preflight fail,不得啟動
Stage1,且不計入正式 `K`/`FWER_target`**——這是 DGP 設計本身的前置檢查,失敗代表整個
協定尚不能開跑,不是某個 Stage1 component-cell 的個別 fail。

---

### 2.D P7 · Code-check(2026-08-03 正式凍結)

**已凍結政策值**:

| 項目 | 值 |
|---|---|
| target tuple 定義 | `(mu_raw, mu_ind)` —— 分別指定 raw 序列與 ind 序列各自的注入均值 |
| `targets` | `{(0, −.020), (−.020, 0)}`(2 組,互為 raw/ind 位置互換的重複稽核) |
| `sigma_code` | `.020` |
| `rho_code` | `.5` |
| `R` | `2000`(單批,不進 `K`/`FWER_target`) |
| `alpha_codecheck_family` | `.05` |
| `alpha_component` | `.05 / 24` |
| negative threshold | `.05` |

**枚舉**:`6 個 DGP cells = 2 targets × 3 M`;C、D 共用同一份 draw,形成
`12 個 method-evaluation cells`(6 DGP cells × 2 methods);每個 method-evaluation cell
各有 raw、ind 兩項 assertion,共 **24 個 endpoint assertions**——target1 貢獻 6 個
raw-zero + 6 個 ind-negative;target2 貢獻 6 個 raw-negative + 6 個 ind-zero;合計
**12 個 zero assertion + 12 個 negative assertion**。

**Direct-series DGP(不重複 P5/P6 的橫斷面/中性化測試,純檢查 C/D 方向、p-value 與
AND wiring)**:
```
z_common_t, z_raw_t, z_ind_t ~ N(0,1) i.i.d.,  t = 1..M,三者互相獨立
x_raw_t = mu_raw + sigma_code · ( √rho_code · z_common_t + √(1−rho_code) · z_raw_t )
x_ind_t = mu_ind + sigma_code · ( √rho_code · z_common_t + √(1−rho_code) · z_ind_t )
```
方法 C、D 各自直接吃 `x_raw`(得 `reject_raw`)與 `x_ind`(得 `reject_ind`)。

**Zero assertion(exact equal-tail Binomial,已解出具體邊界)**:
```
r = 該 assertion 觀測到的拒絕次數,X ~ Binom(n=2000, p=.05)
PASS iff  binom.cdf(r, 2000, .05)   > alpha_component/2
     AND  binom.sf(r-1, 2000, .05)  > alpha_component/2
```
**已解出的具體邊界**:`PASS iff 71 ≤ r ≤ 131`(嚴格不等式,避免 off-by-one;`cdf`/`sf`
公式與此數值邊界同時保留於文件,供日後重算核對)。

**Negative assertion(one-sided Clopper–Pearson upper bound,已解出具體邊界)**:
```
r = 該 assertion 觀測到的「錯誤正向拒絕」次數
U = 1                                        若 r = 2000
U = Beta.ppf(1 − alpha_component, r+1, 2000−r)   否則
PASS iff  U ≤ .05
```
**已解出的具體邊界**:等價於 `r ≤ 72`(`r=72` 時 `U≈.049596≤.05`;`r=73` 時
`U≈.050173>.05`,邊界已核對)。`.05` 取自 `alpha_test` 本身,由正向檢定的單調性
推導,不改為 `.01`。

**Joint-AND(不另設統計門檻,只做兩項確定性斷言,抓 wiring bug 不是抓統計問題)**:
```
逐 replicate assert:  reject_joint == (reject_raw AND reject_ind)
逐 cell assert:       r_joint ≤ min(r_raw, r_ind)
```
不需要對 `r_joint` 另建統計門檻——`AND` 邏輯保證 `r_joint ≤ r_negative_component`,
CP upper bound 對 `r` 單調遞增,negative assertion 通過已自動蘊含 joint 錯誤拒絕率
可控。上述兩條純粹是防呆(抓 `AND` 這行程式碼寫錯的 bug)。

**Alpha 語義(分開寫,不得籠統稱全部只控制 meta false-fail)**:
- **Zero assertions** 控制的是「**正確的 size 實作被本檢查誤判為 fail**」的機率——
  若程式真的正確(拒絕率恰為 `.05`),觀測值落在 `[71,131]` 之外(因而被誤判 fail)的
  機率受 `alpha_component` 限制。
- **Negative assertions** 控制的是「**錯誤(有 bug)的實作被本檢查誤判為 pass**」的
  機率——要求以 `1−alpha_component` 信心上界確認真實錯誤拒絕率 `≤.05`,才允許通過。

**Seed(不新增 root,沿用已凍結 Stage1 global cells 132..137)**:
```
canonical 順序沿用既有 target → M(§2.A.4 code-check 的 cell=0..5 不變)
既有 outer seed → [DGP seed, D-raw bootstrap seed, D-ind bootstrap seed] 不變
DGP seed → 固定 spawn [z_common_seed, z_raw_seed, z_ind_seed]
```

**Fail-closed(沿用 P4)**:任一 cell 數值計算失敗或缺失 → 該 cell 直接 fail,不得補抽
或剔除。

**P7 overall 判定**:
```
P7 overall PASS iff
  - 24 個 endpoint assertions 全部 PASS;
  - 每個 replicate 的 AND 布林恒等式(reject_joint == (reject_raw AND reject_ind))全部成立;
  - 12 個 method-evaluation cells 的 count invariant(r_joint ≤ min(r_raw, r_ind))全部成立;
  - 零數值失敗、NaN 或缺失。
```
**任一條失敗 → `P7 overall FAIL`,Stage1/Stage2 不得啟動。不得只刪除失敗的
method、M 或 target 後繼續,也不得補抽。**

---

### 2.E P8 · Timing-pilot 完整規格(2026-08-03 正式凍結)

**範圍聲明**:本節凍結的是方法 D timing-pilot 的**設計規格**——cells/replicates/
warm-up/計時邊界/平行化/重複次數/外推公式/go-no-go 判定統計量全部要素(對應
§3 #1、§4)。**本節不執行任何 timing、不產生任何計時數字、不代表方法 D 可行、
不代表 72h 判定已經跑過**——那些仍待 runner 實作、單元測試、獨立 Codex 審查、
protocol commit 全部完成後的首次執行。

**Binding 範圍**:與 §4 既有聲明一致,timing-pilot 只對方法 D 具約束力,對應 P3
的 72h/8-core 可行性上限。若同一次 pilot 過程中順便記錄方法 C 的耗時,只能是
nonbinding diagnostic。

**P7 是否併入 binding 總額**:**併入**——`N_M`(每個 M 的正式規模 outer-seed
總數,涵蓋 P7+Stage1+Stage2)= **2,304,000**;三個 M 合計 outer-seed 總數 =
**6,912,000**(= 5,280,000 + 12,000 + 1,620,000,見 2.E.4)。

#### 2.E.1 Observation boundary

boundary = `global_seed_setup`(見 2.E.5)計時開始的那一刻**之前**。boundary 前
須完成:環境 precheck、`x_fixed_root`/`pilot_input_root` 全樹生成、runner 自檢。
boundary 之後,任一 startup/outer_seed_setup/aggregation/warmup/timed/close 階段
失敗、背景負載異常、repeat 缺失、或 CI 不可計算(含 `E_j` 非有限或非正)→
**方法 D 直接判不可行,不得重跑**。boundary 前的 precheck 失敗可修正後視為首次
執行,不算重跑。

#### 2.E.2 Dispatch topology

**Production**:單一長生命週期 8-worker pool(`multiprocessing.get_context('spawn').Pool(
processes=8, initializer=<僅做環境初始化,不預載 x>)`),恰為 **3 條正式 phase
stream**:`P7 → Stage1 → Stage2`,依序執行,含正式的 phase-level fail-closed gate
(P7 fail → Stage1/Stage2 不得啟動;Stage2 qualification 依 §2.A.3 以 Stage1 各 M
是否通過為前提)。每個 task 的 key 必含 `(phase, M, cell, batch, outer)`;不得每個
cell/batch 各自重啟 pool,也不得另開 stream。

**Pilot(每個 repeat)**:**與 production 的 3 條 stream 不是同一件事**——每個
repeat 依序跑 **6 條 measurement stream**:先 3 條 phase-matched warm-up stream
(P7/Stage1/Stage2 各一條,分配見 2.E.4 表),再 3 條 M-specific timed stream
(M24/M36/M48 各一條)。**這 6 條都只是計時用的量測 stream,不是正式 stream 的
縮小版重放**——warm-up 的 200 筆樣本只是量測 surrogate,**不得執行任何需要正式
樣本數(`R_MC`/`R_power`/`R`)才有統計意義的 P7/Stage1/Stage2 判定 gate**(如
P7 的 24 個 endpoint assertion、Stage1 的 rejection-count size 判定、Stage2 的
Clopper–Pearson power 判定)——這些 gate 在 200 或 1,000 樣本下不具統計效力,
pilot 只跑計算路徑本身、不下任何統計結論。

**production 與 pilot 共用的部分**:task unit = 固定 chunk,`outer_per_task=25`;
API 層 `pool.imap_unordered(worker_chunk, chunk_iterator, chunksize=1)`;每個
outer payload = `(outer_index, M, x_raw_copy, x_ind_copy, outer_seed)`——parent
傳已成形的 x(每個 outer 各自獨立 array copy,避免序列化時因物件 identity 被
重複利用而使序列化成本失真),不用 pool initializer 預載 x;raw、ind 在同一個
worker task 內完成。

#### 2.E.3 固定輸入

每個 M 各自一對固定、非退化 float64 陣列 `x_raw_fixed(M)`、`x_ind_fixed(M)`,
純政策型 paired Gaussian,`mu_raw=mu_ind=0`、`sigma=.020`、`rho=.5`(鏡射 P7 §2.D
的 `sigma_code`/`rho_code`,但不引用任何實際 C3/Gate1 資料):
```
x_raw_fixed_t = .020 · ( √.5·z_common_t + √.5·z_raw_t )
x_ind_fixed_t = .020 · ( √.5·z_common_t + √.5·z_ind_t )        t = 1..M
```
在 observation boundary 前生成一次,此後三個 M 各自的全部 warm-up/timed outer
重複使用同一對陣列(逐 outer 各自持有獨立 copy,見 2.E.2)。

#### 2.E.4 Canonical seed tree

```
TimingPilot_root (0xb95ec2b993477c0216990dc8fcc61322)
  .spawn(3) → [x_fixed_root, pilot_input_root, repeats_root]

══════════ PRE-BOUNDARY(輸入準備,不計時)══════════

x_fixed_root.spawn(3) → [x_seed_M24, x_seed_M36, x_seed_M48]
  每個 x_seed_M.spawn(3) → [z_common_seed, z_raw_seed, z_ind_seed]
    → x_raw_fixed(M)、x_ind_fixed(M)(見 2.E.3)
    → 該 M 所需 1,200 個 outer(200 warmup+1,000 timed)各自獨立 array copy

pilot_input_root.spawn(5) → [repeat_input_root_0..4]
  每個 .spawn(6) → [warmup_P7, warmup_Stage1, warmup_Stage2, timed_M24, timed_M36, timed_M48]
    warmup_P7.spawn(200)      → [0:75)→M24,[75:150)→M36,[150:200)→M48
    warmup_Stage1.spawn(200)  → [0:50)→M24,[50:125)→M36,[125:200)→M48
    warmup_Stage2.spawn(200)  → [0:75)→M24,[75:125)→M36,[125:200)→M48
    timed_M24.spawn(1000)、timed_M36.spawn(1000)、timed_M48.spawn(1000)

  全部在 boundary 前建好,與正式規模 outer-seed cascade(下方)完全分離的獨立
  root,避免 pilot 自身量測所需的 seed 建立重複計入 outer_seed_setup_j。

══════════ OBSERVATION BOUNDARY ══════════

repeats_root.spawn(5) → global_seed_setup(計時,只一次)→ [repeat_seed_0..4]

每個 repeat_seed.spawn(2) → [dummy_Stage1_root, dummy_Stage2_root]
  (TimingPilot 專屬 dummy,非正式 Stage1 root 0xd8262df3d547bfa6df93cfa3148e1701、
   非正式 Stage2 root 0x4e11b62641787fd8cfff76c57a32ac19)

【outer_seed_setup_j 計時範圍 —— 完整正式 cascade,逐層皆計入同一項】
  dummy_Stage1_root.spawn(138)                                        # 1 次
  132 次 cell.spawn(2)   (cells 0..131,main+partial)
  6 次   cell.spawn(1)   (cells 132..137,code-check)
  dummy_Stage2_root.spawn(162)                                        # 1 次
  162 次 cell.spawn(1)
  共 432 次 batch.spawn(R)(R=20,000/2,000/10,000)→ 6,912,000 個 outer seed 物件
  root 級、cell 級、batch 級各層 list/object,依正式 lifecycle 建立後釋放
  (含丟棄與 refcount 歸零的釋放動作,全程在計時窗內;不強制 gc.collect(),
   除非確認正式 runner 執行路徑本身固定會呼叫)

  **dummy cascade 只建立並釋放這 6,912,000 個 outer seed 物件本身,不得對其呼叫
  `.spawn(3)`**——worker 端 spawn(3) 的成本已經由 `rate_jM × (N_M−200)` 外推
  涵蓋,dummy 若也執行等同重複計時。

每個 outer(僅限 pilot 自身 warmup/timed payload,真正進 worker 執行 D 的那些):
  outer_seed.spawn(3) → [x-DGP placeholder(未消耗)、D-raw bootstrap seed、
  D-ind bootstrap seed]
  在 worker 內、該 outer 所屬計時窗(warmup_time_j_phase 或對應 M 的 timed-1000
  stream)內執行,每個 outer 只計一次。
```

phase-matched warm-up 分配表(逐 phase 各 200、逐 M 合計各 200):

| phase | M=24 | M=36 | M=48 | phase 合計 |
|---|---|---|---|---|
| P7 | 75 | 75 | 50 | 200 |
| Stage1 | 50 | 75 | 75 | 200 |
| Stage2 | 75 | 50 | 75 | 200 |
| 每 M 合計 | 200 | 200 | 200 | 600 |

#### 2.E.5 E_j / U_total 公式

```
j = 0..4(5 個獨立 timing repeat,即 2.E.4 的 repeat_seed_0..4)

E_j = global_seed_setup + startup_j + outer_seed_setup_j + aggregation_bookkeeping_j + close_j
      + Σ_{phase∈{P7,Stage1,Stage2}} warmup_time_j_phase
      + Σ_{M∈{24,36,48}} (N_M − 200) × rate_jM

rate_jM = (T800_jM − T200_jM) / 600
          # timed-1000 stream 內,第 200、第 800 個完成結果的累積時間;第 800 筆
          # 完成時仍有 200 筆在 queue/in-flight,保證此區間 pipeline 全飽和,
          # 不含 fill 也不含 tail drain。最後 200 筆仍須完整跑完並納入完整性
          # 檢查,但不進 rate。

U_total = mean(E_j) + tcrit × sd(E_j, ddof=1) / √5
tcrit   = 2.131846786326649        # 已由 Codex 獨立 df=4 t-density 數值積分核對
                                      (CDF=.95、one-tail=.05);runner 正式執行時
                                      直接使用此硬編碼常數,不動態呼叫 SciPy
                                      (repo 現無此依賴)

alpha_timing = .05                  # 獨立 operational 政策值,與 alpha_test 無關

PASS iff  U_total/3600 ≤ 72(等號算 PASS)
```

`startup_j`、`close_j`:repeat j 的 pool 啟閉時間(`repeat_seed.spawn(2)` 等粗
粒度 spawn 歸 `startup_j`)。`global_seed_setup`:`repeats_root.spawn(5)` 一次性
成本,同一值加到全部 5 個 `E_j`(平移 mean、不改變 sd)。`outer_seed_setup_j`、
`aggregation_bookkeeping_j`:見 2.E.4、2.E.6。

#### 2.E.6 Aggregation checks

**① 逐筆**(每個 result 抵達,計入 `warmup_time_j_phase` 或對應 M 的 timed-1000
stream 計時窗):key/index bounds 驗證;`written[index]` duplicate 檢查;raw、ind
各自的 p 值與 reject 判定寫入;`fail_flag` 判斷與 failure side-record 處理。

**pilot 自身的小型 aggregation 容器**(裝 2.E.2 六條 measurement stream 各自的
200/1,000 筆結果):**配置在該 stream 的計時器啟動前**;**全部結果到齊後的 pilot
完整性 final scan,在該 stream 計時器停止後執行**——這個 scan 用來驗證這次
量測本身有沒有齊全(缺漏/重複/failure)。**此 scan 的執行成本不納入 `E_j`,
避免與 `aggregation_bookkeeping_j` 重複計時;但其驗證結果是 binding。任何
missing、duplicate、failure 或非有限值,均依 §2.E.1 在 observation boundary 後
fail-closed,方法 D 判不可行且不得重跑。**原因(成本不納入 `E_j` 的部分):正式
規模的 array allocation/final scan 已經完整計入 `aggregation_bookkeeping_j`
(見下②③),pilot 小容器若在 warm-up/timed stream 計時窗內重複做一次同類型的
allocation/scan,會把同一種成本算兩次。

**② 正式規模 batch-level final scan**(432 個 batch 各一次,計入
`aggregation_bookkeeping_j`,與上述 pilot 自身容器無關):
```python
np.all(written)
np.any(fail_flag)
np.isfinite(p_raw).all() and np.isfinite(p_ind).all()
(reject_raw == (p_raw <= .05)).all()
(reject_ind == (p_ind <= .05)).all()
```
missing/duplicate/failure 任一發生 → scan 輸出完整識別資訊 `(phase, M, cell,
batch, outer)`,不得只回布林值。

**Benchmark 特有規則**:`aggregation_bookkeeping_j` 的 dry-run 未真正執行
bootstrap,故 final scan **前**須人工批次將 `written` 設 `True`(確保量到「掃描
真正完整陣列」的成本);**此人工填值本身不計時**——逐筆寫入的真實成本已由
`rate_jM` 涵蓋。array allocation、全部 final scan、array release 三者皆計入
`aggregation_bookkeeping_j`。

容器:NumPy structured array,dtype 含 `outer_index`(i8)、`reject_raw`(?)、
`reject_ind`(?)、`p_raw`(f8)、`p_ind`(f8)、`fail_flag`(?)、`written`(?);一個
batch 一個陣列,大小 = 該 batch 的 `R`;432 個 batch(264+6+162)各一次 final
scan。

**③ phase-level aggregation/gate evaluation**(恰 3 次:P7、Stage1、Stage2 各
一次,同樣計入 `aggregation_bookkeeping_j`):每個 phase 全部 batch 完成後,把
該 phase 的判定邏輯(P7 的 24 個 endpoint assertion 與 joint-AND 檢查、Stage1
的 rejection-count size 判定、Stage2 的 Clopper–Pearson power 判定)實際跑一次,
量測其計算成本。**dry-run 使用固定的 PASS fixture**(結構合法但非真實抽樣所得
的資料),確保三個 phase 的判定邏輯都被量測到;**不得真的執行方法驗證,也不得
產生任何科學結果**。

**Failure side-record schema(固定)**:`(phase, M, cell, batch, outer, endpoint,
reason, intermediates)`。正常 pilot 執行下應為空;寫入此路徑的程式碼須有獨立
單元測試(人工注入失敗情境驗證)。

#### 2.E.7 Go/no-go 與淘汰規則

`U_total/3600 ≤ 72` → D 保留(`M=24/36/48` 一起,後續仍依 §2.A.3 的統計判定與
「M 選擇順序 24→36→48」逐關驗證)。否則,或 boundary 後任一失敗條件觸發(見
2.E.1)→ 同時移除 `(D,24)`、`(D,36)`、`(D,48)`,不得只移除觸發的那個 M,不得
重跑。不得為了通過 72h 而降低 `R_MC`/`R_power`/`B_test`、刪 grid、減 endpoint,
不得挑較好的 repeat。

#### 2.E.8 執行前要求

runner 實作、單元測試(含 `tcrit` 獨立驗證、failure side-record 路徑測試)、
獨立 Codex 審查、protocol commit 全部完成後,才能執行第一次 timing。截至本次
修訂,本節只凍結設計本身,尚未執行任何 timing、未產生任何 `E_j`/`U_total` 數值。

### 2.E.9 P8.1 Amendment(timing-pilot 實作精確化,2026-08-03)

**定位聲明**:本節是對已凍結 P8(§2.E.1–2.E.8,commit `dfab623`)的**實作
精確化修正**,由 luna_worker readiness review 發現的實作歧義觸發,**不改寫、
不重新開放 2.E.1–2.E.8 已凍結的文字**——本節補充精確定義與新增的機器可
判定門檻,凡與 2.E.1–2.E.8 字面有出入之處,以本節(2.E.9)為準。與 P8 本身
相同,**本節只凍結設計,不代表已執行、不代表方法 D 可行**。

#### 2.E.9.1 Chunk envelope + checkpoint(精確化 `rate_jM` 的量測邊界)

```
timed stream:40 個 chunk(chunk_index=0..39,每 chunk 25 outers);
warmup stream:8 個 chunk(chunk_index=0..7)。

chunk envelope:
  pilot chunk key       = (repeat, stream_kind, stream_id, M, chunk_index)
  production chunk key  = (phase, M, cell, batch, chunk_index)
每個 chunk payload = { chunk_key, records: [25 筆,各帶完整 outer key(見
2.E key schema)] }。worker 原樣回傳 chunk_key 與逐筆 outer key;parent 逐項
核對,不符 → 依 §2.E.1 fail-closed。

stream_start_ns < T200_jM < T800_jM < T1000_jM <= stream_stop_ns
T200_jM/T800_jM/T1000_jM 分別在第 8/32/40 個 chunk **完成逐筆 checks/writes
後**取得(不是 chunk 剛從 worker 回傳的當下)。duration component(如
T800−T200 本身)須 finite 且 >=0;由其導出的 rate_jM 須嚴格 >0。

rate_jM = (T800_jM − T200_jM) / 600
```

#### 2.E.9.2 Binding back-pressure(修正 `imap_unordered` 預取假設)

```
max_inflight_chunks = 16        # = 2×8 workers;imap_unordered 本身不保證
                                   只預取 8 個,不得假設 8

機制:threading.BoundedSemaphore(16);chunk iterator 每 yield 一個 chunk 前
acquire 一個 token;parent 完成該 chunk 全部 key 核對/逐筆 check/寫回後才
release token。不變式:任一時刻 (submitted_chunks − fully_processed_chunks)
∈ [0,16],違反 → fail-closed。worker/pool 失敗時直接終止整個 pilot run,
不得靠額外 submission 解除 deadlock。
```

#### 2.E.9.3 Worker health(限定 ready-barrier 範圍)

```
pool 完成「ready barrier」(全部 8 個 worker 完成一次 no-op 往返)後,凍結
該時刻的 8 個 worker PID 為 frozen_pid_set。從 ready barrier 完成到 close
開始這段穩態窗內,PID 集合與存活數必須恆為 frozen_pid_set / 8,任一時刻
不符 → fail-closed。startup(pool 建立→ready barrier)與 close(close 開始
→完全關閉)這兩段過渡期**不適用**此「恆為 8」的不變式。
```

#### 2.E.9.4 CPU affinity(全 process tree 共用同一組 ≤8 核,不多用一核)

```
eligible_cpus = 由 parent 啟動時實際可用的 affinity 集合取得
                (Windows:psutil.Process().cpu_affinity())
len(eligible_cpus) < 8 → precheck fail
selected_cpus = sorted(eligible_cpus)[:8]        # 排序後取前 8 個,固定可重現
parent 與全部 8 個 worker 啟動後,全部設定 affinity = selected_cpus
(共用同一組最多 8 核的 affinity mask,由 OS 排程器在其內調度,不是每個
process 各自獨佔一核,也不額外多用第 9 核——P3 的「8-core」上限涵蓋整個
process tree)。
```

#### 2.E.9.5 計時時鐘

```
一律使用 time.perf_counter_ns()(整數奈秒,不受長時間運行後 float 精度漂移
影響)。time.perf_counter()(float 秒)與 perf_counter_ns() 共用同一底層
高解析度時鐘來源、解析度相同——選 perf_counter_ns() 的理由是精度不隨數值
變大而漂移,不是「perf_counter() 只有秒解析度」(此為先前版本的錯誤說法,
已撤回)。
```

#### 2.E.9.6 單一 `rate_jM` 的 phase-invariance 前提(明文化)

```
「單一 rate_jM 適用於 P7/Stage1/Stage2」這個假設,成立的前提是:worker 端
執行的 D-only code path,在三個 phase 之間逐字元相同(同一函式、無 phase
分支);DGP 生成(nonbinding)與 phase-level gate 成本(計入
aggregation_bookkeeping_j)均不在 rate 內。若 runner 實作時三個 phase 的
worker 端 D-only code path 出現任何差異——立即 fail-closed,不得沿用既有
rate_jM 假裝仍然有效,須回頭重新設計(可能需要逐 phase 分開量測)。
```

#### 2.E.9.7 Background-load(兩層,精確 Windows psutil 欄位定義)

```
Windows psutil.cpu_times(percpu=True) → scputimes(user, system, idle,
interrupt, dpc)。對每個 selected core、每個欄位先各自算 delta 並下限 0:
  delta_user_i = max(0, user_i(after)−user_i(before));delta_system_i、
  delta_interrupt_i、delta_dpc_i 同理。
  busy_delta = Σ_{core∈selected_cpus} (delta_user_i+delta_system_i+delta_interrupt_i+delta_dpc_i)
  (不得先加總 busy_before/busy_after 兩個總和再相減——逐欄位 clamp 後才加總,
  避免遺漏個別欄位的非單調異常)

Windows psutil.Process(pid).cpu_times() → pcputimes(user, system)(無
children 欄位)。對 parent 與 8 個 worker 的 (user,system) 逐欄位同法算
delta 並加總,得 runner_tree_cpu_delta。

A. Boundary 前(precheck):只檢查 selected_cpus,連續 5 個 1 秒樣本。
   PASS iff 5×8 樣本整體平均 busy ≤5%,且任一 (core,sample) 組合 busy ≤25%。

B. Boundary 後(只在 ready-barrier→close-開始 的穩態窗內量測):對每條
   warmup/timed stream 及整個 repeat 各自取前後 snapshot。
   wall_delta = t_after − t_before(perf_counter() 秒,僅用於正規化)
   background = max(0, busy_delta − runner_tree_cpu_delta) / (wall_delta × 8)
   threshold = 5%(固定);background > threshold → 依 §2.E.1 fail-closed。
   短於 1 秒的 component 不單獨判定,但仍涵蓋在整個 repeat 的穩態窗量測內。
   **`global_seed_setup`/`startup_j`/`close_j` 完全不做 background 判定**
   (不論單獨或透過 repeat 穩態窗——這三項結構上就在穩態窗之外),但其
   wall time 仍完整計入 E_j。
   telemetry invalid(視為量測本身不可信,直接 fail-closed):
     - runner_tree_cpu_delta − busy_delta > 0.02 × (wall_delta×8)
     - 任一 PID 的 cpu_times 讀取失敗
     - psutil 呼叫本身丟出例外或回傳非數值
```

#### 2.E.9.8 Memory precheck(disposable pool 自我量測,不用猜測常數)

```
1. 建立獨立、可丟棄的 precheck pool(test-only root,與 TimingPilot_root
   完全分離)。

2. 在此 pool 內,量測 sum(worker_baseline_rss[0..7])——8 個 worker 各自
   實測的 psutil.Process(pid).memory_info().rss 直接加總(不是量一個值
   再乘以 8)。

3. **由 parent 自己執行**(不得讓 worker 代跑)完整 432 批(264+6+162)
   test-only seed 建立→釋放循環,鏡射 §2.E.4 的正式 cascade 結構。**取樣
   方式**:parent 每次 `batch_seed.spawn(R)` 完成、該批 outer-seed list
   仍存活且尚未 release 時,**立即同步讀取**整個 process-tree(parent+8
   worker)的 RSS——432 批逐批取樣,取其中最大值減去測試開始前的 RSS,得
   `seed_peak_delta_432`。**不得只靠背景輪詢**(定時器式取樣可能漏掉批次
   間的短暫峰值,必須在「list 剛建完、尚未釋放」這個已知的高峰時間點同步
   讀取)。鏡射完整 432 批(不是量單一 batch)是為了捕捉 Python allocator
   在大量重複配置/釋放後可能出現的累積效應。

4. **D scratch 改為實際並行量測**(不再用單一 worker 乘以 8 估計):
   disposable precheck pool **同時**派送 8 個 test-only D task(M=48、
   B=1,999),每個 worker 恰好一個,全部同時執行(不輸出/不記錄任何 p 值
   或 reject 結果);量測整個 process-tree 在這 8 個並行任務執行期間的
   peak RSS,減去任務派送前的 RSS,得 `D_concurrent_peak_delta`——此值
   直接取代原本的「單一 worker 量測 × 8」,因為並行執行下的真實記憶體
   峰值不保證等於單一量測值的線性倍數。

5. Inflight peak 實測(不用 pickle.dumps 長度估計,且新增 ready-counter
   同步機制避免競態):以 **spawn context 的 multiprocessing.Event**(**不得
   用 threading.Event**——後者無法跨 process 同步),在 Pool 建立時透過
   `initializer`/`initargs` 傳入每個 worker,連同一個 **spawn-context 的
   Queue** 作為 ready 訊號通道;實際提交 16 個 M48、25-outer 的 test-only
   chunk。每個 worker 完成該 chunk 的反序列化後,**先把自己的 frozen PID
   放進 ready Queue**,再於共享 Event 上等待(暫停,尚未真正執行 D 運算)。
   parent 必須收到 **8 個不同的 frozen worker PID** 的 ready 訊號後,才
   讀取整個 process-tree 的 RSS 峰值——此時恰好 8 個 chunk 已反序列化並
   held 在 worker 端,另外 8 個(合計 16,受 `max_inflight_chunks` 的
   back-pressure/queue 約束)仍在等待被 worker 領取。PID 重複、收到的
   distinct PID 少於 8、或等待逾時 → precheck fail。量測完成後,量測值
   減去提交前的 RSS,得 `inflight_peak_delta_measured`;量畢後 set 該
   Event 釋放全部 worker、清空 test-only 資料。

6. 量測完成後,**關閉並銷毀此 precheck pool**。銷毀後,重新執行 §2.E.9.7
   A 層(selected-core 5×1 秒 idle precheck)——確保量到的是拆掉 precheck
   pool 之後的真實環境閒置狀態。

7. observation boundary 之後,**每一個 repeat(含 repeat 0)都各自從零
   建立全新 pool**,`startup_j` 從零完整計時。**禁止把 precheck pool
   挪用為 repeat 0**——那樣 repeat 0 會因 pool 已經暖過而失去與其餘
   repeat 的可比性。

required_future_bytes = sum(worker_baseline_rss[0..7])      # 步驟 2,未來 5
                                                                個 repeat 各自
                                                                新建 pool 的
                                                                8 個 worker
                       + seed_peak_delta_432                  # 步驟 3
                       + D_concurrent_peak_delta               # 步驟 4(取代
                                                                  8×worker_D_scratch_peak_delta)
                       + agg_bytes                             # R_max×AGG_DTYPE.itemsize,
                                                                  未來才配置
                       + inflight_peak_delta_measured          # 步驟 5

**`x_fixed`/`pilot_input_root` 的陣列與 seed、以及 parent 自身既有 RSS,
在 precheck 測 `available_bytes` 當下已經反映在裡面(已被扣掉),不得再
額外加進 `required_future_bytes`**——那是已經花掉的成本,不是未來才發生
的成本。

PASS iff available_after_precheck_pool_closed >= 1.5 × required_future_bytes
```

#### 2.E.9.9 psutil binding dependency(已鎖定)

```
platform = Windows AMD64
Python   = 3.12.x
package  = psutil==7.2.2
wheel    = psutil-7.2.2-cp37-abi3-win_amd64.whl
SHA256   = eb7e81434c8d223ec4a219b5fc1c47d0417b12be7ea866e24fb5ad6e84b3d988
```
鎖定於獨立的 `requirements-d2-timing.txt`(專案根目錄),**不併入既有
Streamlit `requirements.txt`**——後者是既有生產 app 的依賴清單,與本研究
timing-pilot 無關,不應為此新增依賴。runner 啟動時,若實際安裝版本與上述
鎖定版本不符,或 import 失敗 → precheck fail。Windows 專屬欄位(`cpu_times`
的 `interrupt`/`dpc`、`Process.cpu_affinity()`、`Process.memory_info().rss`)
須有平台整合測試,實際在目標環境驗證可用。**Codex 已於 2026-08-03 透過
官方 PyPI 核對**:`psutil-7.2.2-cp37-abi3-win_amd64.whl`,
`SHA256=eb7e81434c8d223ec4a219b5fc1c47d0417b12be7ea866e24fb5ad6e84b3d988`;
標籤為 CPython 3.7+/Windows x86-64,涵蓋本研究 Python 3.12.10 AMD64 環境
(此項核對由 Codex 執行並轉達,本 session 未自行連網重複驗證)。
本機現況(已於前一輪獨立核實):`python -c "import psutil"` → `ModuleNotFoundError`;
`requirements.txt` 未列出 psutil。

#### 2.E.9.10 已接受的政策值(彙總)

| 政策值 | 數值 |
|---|---|
| `max_inflight_chunks` | 16 |
| Background A 層(boundary 前) | 5×1 秒樣本,整體平均 ≤5%、單核單樣本 ≤25% |
| Background B 層(boundary 後) | `threshold=5%` |
| Telemetry invalid 容忍度 | `2%` |
| Memory 安全係數 | `1.5×` |
| psutil 版本/wheel/hash | 見 2.E.9.9 |

以上數值已由使用者正式接受,但**runner 尚未實作、單元測試尚未撰寫、獨立
Codex 審查與 protocol commit 均尚未完成前,仍不得執行任何 timing**(沿用
§2.E.8 執行前要求)。

---

## §3 項目狀態(#2 仍開啟;#1、#5 設計已關閉)

**#1 Timing-pilot 的設計要素**:**設計已關閉(見 §2.E 的 P8:observation boundary、
dispatch topology、固定輸入、canonical seed tree、E_j/U_total 公式、aggregation
checks、go/no-go 與淘汰規則均已定義並凍結),尚未執行任何 timing**(未產生任何
`E_j`/`U_total` 觀測值,**不代表方法 D 可行、不代表 72h 判定已經跑過**)。與
P5/P6 的 calibration/sign-preflight static cost 仍是不同範疇(那批屬 #2 的可行性
參考資訊,不受 P3 約束,也不在 P8 的設計範圍內)。

**#2 Main DGP 實際係數**:**設計與政策已凍結(見 §2.B/§2.C 的 P5/P6);四個係數
(`a010_iid`/`a005_iid`/`a010_AR`/`a005_AR`)的 search/一次性 validation,以及 c-sign
preflight,尚未執行,因此實際係數尚未寫死,#2 仍開啟。**

**#5 code-check 的精確 PASS 門檻**:**設計已關閉(見 §2.D 的 P7:24 個 endpoint
assertion、`[71,131]`/`r≤72` 具體邊界、joint-AND 防呆斷言、alpha 語義區分均已定義並
凍結),尚未執行 code-check**(未跑過任何 `x_raw`/`x_ind` 抽樣、未產生任何 `r` 觀測值)。

---

## §4 Timing-pilot 專項檢查(對應 §3 #1,逐要素列表)

| 要素 | 狀態 |
|---|---|
| pilot cells/streams 數 | ✅ 已定義(見 §2.E.2/2.E.4:每個 timing repeat 共 **6 條 measurement stream**——3 條 phase-matched warm-up + 3 條 M-specific timed) |
| 每 stream 樣本數 | ✅ 已定義(見 §2.E.4:warm-up=200/phase;timed=1,000/M) |
| timing repeats(pilot 本身穩定性) | ✅ 已定義(見 §2.E.5:`j=0..4`,共 5 次獨立 timing repeat;因 72h 判定已改為單一 U_total,不再需要對 M 做 Bonferroni;**不是「每 cell 重複次數」,不得混用**) |
| warm-up(暖機/暖身期) | ✅ 已定義(見 §2.E.4 分配表:每 phase 200 outer、每 M 合計 200) |
| 計時邊界定義 | ✅ 已定義(見 §2.E.1 observation boundary) |
| 平行化設定 | ✅ 已定義(見 §2.E.2:production 為單一 8-worker pool、3 條依序正式 phase stream;pilot 另跑 6 條 measurement stream,對應 P3 的「8 cores」) |
| 外推公式(pilot → 全量) | ✅ 已定義(見 §2.E.5 E_j/U_total 公式) |
| go-no-go 判定統計量 | ✅ 已定義(見 §2.E.7) |

以上要素已於 P8(§2.E)定義並凍結。**設計凍結不代表已執行**——runner 實作、
單元測試、獨立 Codex 審查、protocol commit 全部完成前,仍不得執行任何 timing
pilot(本 session 未執行任何此類動作)。

**Binding 範圍(修正含糊措辭)**:本表的 timing-pilot **只對方法 D 具有約束力**,
對應 P3 的 `72h/8-core` 可行性上限,是唯一的 go/no-go 依據。**若在同一次 pilot 過程中
順便記錄方法 C 的耗時,那只能是 nonbinding diagnostic**——不得用來決定方法 D 的
go/no-go,也不得據此主張擴張 P3 的適用範圍到方法 C。**此表不涵蓋 P5/P6 的
calibration/sign-preflight 成本(那屬 #2 的可行性資訊,見 §2.B 末段,同樣不受 P3 約束)。**

---

## §5 轉寫範圍聲明

§2 的內容多數是 Codex 提供的 authoritative frozen block 的忠實轉寫,部分(P5/P6 的搜尋
規格、seed 階層細節)是本 session 依 Codex 逐輪審查意見設計並經多次修正。**本 session
未對這套統計設計的正確性做獨立數值驗證**(未實際跑過任何 search/validation/sign
preflight)——這是 #2 尚未關閉的原因。§2 內部可交叉核對的算術(`K=516=504+12`、
`126=7×3×2×3`、`162=9×6×3`、`18=3×6`、`T=83,403→84,000`、
`static cost=8.2656e9`)已核對一致,列在文中供後續讀者覆核。

P8(2.E)同樣是本 session 依 Codex 逐輪審查意見設計、經多輪修正後的結果——過程中
修正過三個實質 bug(rate 計算誤把固定成本乘入斜率、`T1000−T200` 仍含 tail drain、
`outer_seed_setup_j` 一度漏算/一度重複計算 outer-seed 建立成本)。可交叉核對的算術
(`6,912,000=5,280,000+12,000+1,620,000`、`432=264+6+162`、phase-matched warm-up
分配表逐 phase 與逐 M 皆恰為 200)已核對一致。`tcrit=2.131846786326649` 已由
Codex 獨立 df=4 t-density 數值積分核對,其餘統計設計本身**尚未經本 session 獨立
數值驗證**,與 #2 相同的限制同樣適用。

---

## §6 本文件的限制(逐條聲明)

- 不宣稱 D2 已通過任何驗證(§2 是規格,不是執行結果)。
- 不宣稱 #2 已關閉——四個係數的 search/validation 與 c-sign preflight 尚未執行。
- 不宣稱 #1(P8)、#5(P7)的設計凍結等同已驗證、已執行,或已知可行——兩者都只是
  把設計本身寫死,尚未產生任何一次真實觀測。
- 不宣稱 timing pilot 或 calibration/sign preflight 已可執行或已知可行。
- 不影響、不修改 Gate1 任何產物或既有裁定。
- 不構成 C3 正式前瞻預註冊,不解除 D1(window selection)的暫停狀態。
- **本檔是明列 blockers 的 auditable design checkpoint**;P7、P8 政策已分別
  於 `aab856f`、`dfab623` 兩次 commit 中留下版本稽核軌跡。本輪(P8.1
  amendment)寫入時的 stage/commit 狀態,依當輪 `GPT answer.md` 授權範圍
  而定,不得未經明確授權逕自 stage/commit,也不得假設沿用先前輪次「未
  stage/commit」的敘述。
