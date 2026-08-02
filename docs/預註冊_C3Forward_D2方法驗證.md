# D2 方法驗證協定(synthetic method-validation protocol)—— 草案,未凍結

**狀態**:🚧 **草案,未凍結**。Policy Register **P1–P6 的規格與政策值已凍結**(見 §2),
但 **#2(main DGP 實際係數)尚未執行校準/驗證,實際數值尚未寫死,故整份文件狀態仍是草案**。
本檔由 Codex 於 2026-08-03(經 `GPT answer.md` 轉達)指示建立,歷經多輪修正與使用者政策裁定。

**本檔不修改、不影響 Gate1 任何產物或既有裁定;不執行任何 calibration、validation、
c-sign preflight、timing pilot、synthetic 驗證、績效/OOS 或 prospective collection;
只修改此未追蹤檔案,未 `git add`/`stage`/`commit`。**

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

## §2 Policy Register(P1–P6,已凍結規格)

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

## §3 尚未關閉的項目

**#1 Timing-pilot 的設計要素**(cells/replicates/warm-up/計時邊界/平行化/重複次數/
外推公式/go-no-go 判定統計量)—— 見 §4 逐項列表,全數未定義。**與 P5/P6 的 calibration/
sign-preflight static cost 是不同範疇**(那批屬 #2 的可行性參考資訊,不受 P3 約束,
也不在本項 timing-pilot 的設計範圍內)。

**#2 Main DGP 實際係數**:**設計與政策已凍結(見 §2.B/§2.C 的 P5/P6);四個係數
(`a010_iid`/`a005_iid`/`a010_AR`/`a005_AR`)的 search/一次性 validation,以及 c-sign
preflight,尚未執行,因此實際係數尚未寫死,#2 仍開啟。**

**#5 code-check 的精確 PASS 門檻**(只知道 code-check 用 `targets=(0,−.020)/(−.020,0)`、
`R=2000`,但「怎樣算通過」的具體數字門檻未給,不能只寫「看起來正確」這種模糊語意)。

---

## §4 Timing-pilot 專項檢查(對應 §3 #1,逐要素列表)

| 要素 | 狀態 |
|---|---|
| pilot cells 數 | ❌ UNRESOLVED |
| replicates(每 cell 重複次數) | ❌ UNRESOLVED |
| warm-up(暖機/暖身期) | ❌ UNRESOLVED |
| 計時邊界定義 | ❌ UNRESOLVED |
| 平行化設定 | ❌ UNRESOLVED(是否與 P3 的「8 cores」規則直接對應未說明) |
| 外推公式(pilot → 全量) | ❌ UNRESOLVED |
| 重複次數(pilot 本身穩定性) | ❌ UNRESOLVED |
| go-no-go 判定統計量 | ❌ UNRESOLVED |

在這些要素被明定之前,不得執行任何 timing pilot(本 session 未執行任何此類動作)。

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

---

## §6 本文件的限制(逐條聲明)

- 不宣稱 D2 已通過任何驗證(§2 是規格,不是執行結果)。
- 不宣稱 #2 已關閉——四個係數的 search/validation 與 c-sign preflight 尚未執行。
- 不宣稱 #1/#5 已有可執行定義。
- 不宣稱 timing pilot 或 calibration/sign preflight 已可執行或已知可行。
- 不影響、不修改 Gate1 任何產物或既有裁定。
- 不構成 C3 正式前瞻預註冊,不解除 D1(window selection)的暫停狀態。
- **本檔目前是明列 blockers 的 auditable design checkpoint**;本 session 未
  stage/commit,**是否建立版本快照須由使用者另行授權**(凍結政策若一直只存在於
  untracked 檔案,反而缺乏版本稽核軌跡,但本輪仍不得自行 stage/commit)。
