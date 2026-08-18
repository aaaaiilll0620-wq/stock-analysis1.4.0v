# 預註冊 · 技術指標負 IC 機制檢驗

**狀態:🔒 已凍結(2026-08-10)。凍結後不得改門檻、不得換母體、不得換報酬線、不得事後追加 arm/視野/因子。**
來源:使用者與 ChatGPT 討論後提出的研究規格(`GPT answer.md`,2026-08-10),
本檔是把該規格對齊本專案既有基礎設施、量測協定、研究紀律後的**可執行版本**。
§5 開放決策已由使用者於 2026-08-10 逐項確認,見各項「**凍結**」標記。

## 0. 待驗對象(定義凍結)

| 項 | 值 |
|---|---|
| 研究問題 | 法人賣轉買、KD、BB、MA 為何在本專案呈負 IC / 負前瞻報酬?是短期均值回歸、universe 條件、訊號滯後,還是單純無 alpha? |
| 產出 | 診斷報告,**不是**新策略、不是新總分、不接回 production |
| 隔離 | 新檔 `scripts/technical_mean_reversion_lab.py` + `research/technical_mean_reversion_lab/`;不改 `app.py`、`core/scoring_manager.py`、任何正式策略 lab |
| 報酬線 | `exec_ret.fwd_x`(主用,20 交易日)/ `exec_ret.fwd_x60`(60 交易日)/ `exec_ret.fwd_t1`(1 交易日,敏感度用)—— 见 §3-A,**只用這三條,理由见开放决策 1** |
| 母體 | Wide = ADV≥2000萬 流動池(`lab_paths.load_panel`預設);dual100 = 见 §3-D |
| 時代切分 | 沿用既有六時代(`inst_reversal_lab.ERAS` / `alpha_gate_lab` 同一套),不重新切 |
| Regime 切分 | **修正**:26 因子掃描(`DevLog:1192` bull 65期/bear 19期)實際用的是 `alpha_gate_lab.py::regime()` 的規則 ——「市場 60 日動能均值正負」(逐月對全 pool 的 `mom60` 取均值,>0=bull),**不是** `core/regime.py` 的週線分類器。本案沿用前者(逐字重現該規則),不新增 ADX,也不用 `core/regime.py`。 |

---

## 1. 現有證據(這些不是待驗證假說,是既有 repo 已得到的結果;本案不得推翻,只能解釋)

1. **法人「賣轉買」是反指標**:`scripts/inst_reversal_lab.py` 六時代全負、t ≈ −4.67
   (`docs/開發日誌_DevLog_135557.md:1625`、`docs/使用指南_USER_GUIDE.md:246`)。
2. **短窗籌碼比長窗更負**:chip5/chip10 比 chip20 更負(法人短線追價),chip60 才轉正
   (`DevLog:1198`)。「持續買」僅微弱邊際,已做進 `app.py` 的 `_INST_MIN_STREAK=3` 閘門。
3. **技術代理在寬池同向全負**:RSI14 / 布林%B / MA 偏離(超買=反指標),`DevLog:1196`。
4. **因子不可跨池移植**:20 日動能寬池 IC 全負,官方 45 檔優質池轉正,`DevLog:1197`。
5. **5F 等權綜合分寬池排序無資訊量**:`DevLog:1186`。本案禁止新增任何手工「總分/狙擊分數」。

## 2. 假設(在看到任何本案數字之前寫死)

### H1 — Horizon curve(短期均值回歸假說)
對法人賣轉買狀態、KD(若可測,見開放決策 2)、BB(`bbp20`)、MA(`ma_gap60`)四個訊號,
在**三個凍結可用視野**(T+1=`fwd_t1`、T+20=`fwd_x`、T+60=`fwd_x60`)輸出 mean/median fwd
excess、IC、IC t-stat、win rate、樣本數。
判讀:若 T+60 仍為負,不支持「純短期均值回歸」解釋。
> **不追加 T+2/T+5/T+10/T+40** —— 這些視野目前沒有被審計過的可執行報酬線(見開放決策 1)。

### H2 — 訊號滯後 / 已追高(event study)【本輪不執行,已凍結】
需要日頻價格路徑,本案不新建。**標記為「未執行」寫進 README**,不用月頻資料湊近似結論。

### H3 — 法人 flow lifecycle(比「賣轉買」更細的分態)【本輪不新定義分態,已凍結】
本輪**不新定義**「賣超縮小 / 接近 0」門檻(留待另案預註冊)。本輪只使用 repo 既有、
已審計的 `inst_reversal_lab.classify()` 4 態(依 sign(長窗 `chip`)/sign(短窗 `chip5`))——
這 4 態的結論已經是 §1 現有證據第 1 條(賣轉買=反指標,六時代全負 t≈−4.67)。
本案對 H3 的處理方式:**在 H1 的 horizon curve 裡把「法人賣轉買」狀態當作四個受測訊號之一**
(與 KD 家族的 `rsi14`、`bbp20`、`ma_gap60` 並列),只是延伸既有 4 態結論到 T+1/T+60 兩個
額外視野,**不產生新的分箱定義**。細緻 lifecycle(7 態)不在本案範圍。

### H4 — Wide pool vs dual100(universe conditioning)
KD/BB/MA 用**完全相同的訊號定義**,分別在 Wide universe(ADV≥2000萬)與 dual100 品質池
上測 IC,跨 §0 三個凍結視野比較。**不得為 dual100 重新調參**。
判讀:Wide− dual100+ → universe conditioning;Wide− dual100− → 品質池不能翻正;
dual100≈0 → 可能只是篩掉垃圾股,仍無 alpha。**判定僅依 primary(§3-D 選項 A,~48 檔實際
持股)**;selection B(ADV≥100萬 population)只作 secondary sensitivity 附註,不影響判定。

### H5 — 正向 vs 反向不能互相蘊含
同時測 trend interpretation(KD強/BB上軌強/MA強勢→做多)與 mean-reversion interpretation
(KD過熱/BB延伸/MA偏離過高→反向)。禁止看到結果後才決定門檻——用 §3-A 既有連續因子值
的 rank IC(正負號本身即答案),不額外切 threshold。**正向失效不代表反向乘 −1 就有 alpha**,
須額外看反向那組樣本內的 IC 是否穩定為正、六時代不翻向。

### H6 — Interaction(RSI14×BB×MA 共振;KD 不測,見開放決策 2)
單因子 IC 全負,共振狀態(RSI14∩BB / RSI14∩MA / BB∩MA / RSI14∩BB∩MA)是否有不同的
conditional IC/fwd return。只做 bucket 對照,不做人工加權。
**分桶規則(先寫死,零自由參數)**:每個 as_of 橫斷面內,依該因子值高於/低於當月 Wide 池
中位數,分「高／低」兩桶(median split;不用固定分位數門檻,避免產生可調參數)。
只在 Wide pool 跑(dual100 每月僅 ~48 檔,四因子交叉分桶後每格樣本過少,不具統計力,
故 H6 不對 dual100 重複)。

### H7 — Era stability
所有 H1/H3/H4/H5/H6 的重要結果,逐既有六時代重跑一次(IC/t/樣本數)。
**不接受「全期正、各era正負正負」就宣稱穩定**——穩定性優先於 full-period point estimate。

### H8 — Regime interaction(exploratory,非 confirmatory)
規則沿用 `alpha_gate_lab.py::regime()`:逐月對 Wide 池的 `mom60` 取橫斷面均值,
均值 >0 → 該月 bull,否則 bear(原腳本只在探索期 2019-2025 印過;本案套用同一條規則到
全樣本 2005-2026,規則不變,只是套用範圍延伸——這是延伸應用不是新定義)。
測 RSI14/BB/MA 三因子的符號是否隨 bull/bear 改變。**只回答符號會不會變,不搜尋 ADX 或
任何新門檻參數。** 結果放 Post-hoc Hypotheses 區,不進 confirmatory 判定。

## 3. 量測協定(跑之前定死)

### 3-A 報酬線與視野
- 唯一入口 `lab_paths.load_panel(horizon=...)`;20d→`fwd_x`、60d→`fwd_x60`。**主判定用這兩者。**
- `fwd_t1`(T+1)直接讀 `exec_ret.parquet` 併入(非 `lab_paths` 包過的欄,merge 後跑
  `assert_no_row_growth` 比照 `lab_paths` 內部寫法)。
- `fwd_t2` 只做敏感度對照,不進任何判定門檻。
- **禁止使用 `obs_alpha.fwd` / `fwd_cc`**(close-close 對帳用,已知反向偏誤,同研究紀律 §1 規則1)。

### 3-B 訊號定義(全部用 obs_alpha 既有欄,不重算;不新增 KD)
| 訊號 | 欄位 | 备注 |
|---|---|---|
| BB(布林%B) | `bbp20` | 26 因子掃描已用過此欄,寬池 IC 已知為負 |
| MA 偏離 | `ma_gap60` | 同上 |
| RSI14 | `rsi14` | 作為 KD 的同族超買超賣代理(KD 本身不測,開放決策 2 已凍結) |
| 法人賣轉買 | `chip`(20日) / `chip5` | 依 `inst_reversal_lab.classify()` 4 態分類,沿用既有函式 |
| 法人短窗 | `chip5` / `chip10` / `chip60` | 既有欄,H1 horizon curve 用 |

### 3-C 時代與 regime(已凍結)
- 六時代:`inst_reversal_lab.ERAS`(2005-2009 / 2010-2014 / 2015-2018 / 2019-2021 /
  2022空頭 / 2023-2026),原樣 import,不重切、不重打。
- Regime:見 §2 H8 —— `alpha_gate_lab.regime()` 的「Wide 池 `mom60` 橫斷面均值正負」規則,
  逐字重現,不用 `core/regime.py`。

### 3-D dual100 品質池(已凍結)
- **Primary(判定用)**:`beat_0050/strategies/high52_lab.dual_confirm_mask(P, tier="100萬",
  source="real")` 產出的月度 ~48 檔實際持股遮罩(real_composite Top20% ∩ c2 Top20%,
  ADV≥100萬),經 `dual100_lab.mask_to_holdings()` 同款邏輯轉成 {as_of: [stock_id]},
  逐月精確重現 `dual100_lab.py` 的池定義。**H4/H8 的通過/不通過判定只依這個池。**
- **Secondary(sensitivity,不影響判定)**:`lab_paths.load_real_panel(adv_floor=1e6)`
  覆蓋的整個 ADV≥100萬 母體(不套 Top20%∩Top20% 篩選)。若容易取得則附帶輸出對照,
  結果只放 README 附註,**不進 §4 判定門檻**。

### 3-E 訊號值凍結時點
所有訊號值(bbp20/ma_gap60/rsi14/chip 系列)一律用 `as_of` 當月面板值,不做任何前視或
事後平滑;與 `lab_paths.load_panel` 的既有 PIT 保證一致。

## 4. 判定門檻與失敗處置(先寫死)

| 假設 | 通過 / 有效判讀 | 若不成立 |
|---|---|---|
| H1 | T+60 仍負 → 拒絕「純短期均值回歸」;T+60 轉正/趨近0 → 支持 | 兩者都不成立 → 寫「無法判定」,不得硬講故事 |
| H2 | 本輪不執行,README 標記「未執行」 | — |
| H3 | 本輪不新測(用既有 4 態結論,見 §1) | — |
| H4 | dual100(primary,~48檔)IC 顯著轉正(|t|≥2)且六時代不翻向 → universe conditioning 成立 | dual100 仍負或接近0 → 明確結案「品質池不能救這組技術代理」,**不得再測第三個池**;secondary population 池結果僅供參考,不得取代 primary 判定 |
| H5 | 反向那組的 IC 六時代同號且 full-period |t|≥2 → 反向可能有效;否則 → 「正向失效≠反向有效」成立,兩者皆不進下一輪預註冊 | — |
| H6 | 共振 bucket 的 conditional IC 與單因子平均值有系統性差異(非隨機噪音,需 bootstrap 或 bucket 間 t 檢定)→ 值得記錄;否則視為噪音 | — |
| H7 | 適用於以上所有假說的最終判讀依據,不單獨判定 | — |
| H8 | 僅描述性,不判定通過/失敗 | — |

### 事前宣告的出口
1. **H1+H4 都支持「universe conditioning + 非短期噪音」** → 值得寫入下一輪
   「KD/BB/MA on dual100」預註冊(獨立於本案,需另行凍結門檻)。
2. **H4 不支持(dual100 仍負)** → 結案,技術代理反指標是本專案的既定事實,
   不再嘗試用更小的池救它。
3. **結果不足以區分機制**(比如 H1/H3 都是雜訊等級)→ README 明確寫「目前無法判定」,
   本案本身即是產出(反面知識,同高52_prox 先例),不得因為看起來不夠精彩而不寫。

## 5. 開放決策(2026-08-10 使用者已逐項確認,已凍結)

1. **視野範圍 → 凍結為 T+1/T+20/T+60 三點主判定,T+2 僅敏感度**。不新建
   `build_exec_ret.py` 管線,T+5/T+10/T+40 不在本案範圍。
2. **KD → 凍結為不測**。用 `rsi14` 作為短線超買超賣振盪器代表,不新增 KD 欄位。
3. **H2 event study → 凍結為本輪不執行**,不新增日頻資料路徑,README 明寫「未執行」。
4. **法人 7 態 lifecycle → 凍結為本輪不新定義分箱**,留待另案預註冊;本輪只用既有
   已審計的 4 態結論(§1 現有證據第 1 條),延伸到 §3-A 三個視野(見 H3 段落)。
5. **dual100 池定義 → 凍結為 §3-D primary(選項 A,~48 檔實際持股遮罩)判定**;
   secondary population 池(選項 B)若容易取得則附帶輸出,僅供 sensitivity 參考,
   不影響 H4/H8 判定。

## 6. 執行順序

1. ✅ 使用者已於 2026-08-10 對 §5 五項開放決策逐一確認。
2. ✅ 本檔已補完 §3-D、§3-C,狀態已改為「已凍結」。
3. 寫 `scripts/technical_mean_reversion_lab.py`,只實作 §2/§3/§4 寫死的內容
   (H2、H3 新分態不實作;KD 不實作)。
4. 先跑 H1(最便宜、零新資料)驗證管線正確,再跑 H4(Wide vs dual100,本案核心問題)。
5. H5(反向)、H6(interaction)、H7(era)、H8(regime,exploratory)依序執行。
6. 所有結果寫 `research/technical_mean_reversion_lab/{summary.csv, horizon_curve.csv,
   pool_comparison.csv, interaction_results.csv, era_results.csv, README.md}`
   (不產生 `institutional_flow_lifecycle.csv`——H3 新分態本輪不執行)。
   README 回答:(1) 法人賣轉買為何負,目前證據支不支持新機制;(2) RSI14/BB/MA 的負號是
   短期均值回歸、universe effect,還是單純無 alpha;(3) dual100 是否翻正;
   (4) 反向使用是否穩定成立;(5) 是否值得進下一輪預註冊。若證據不足以區分機制,
   明確寫「目前無法判定」。

## 7. 結果(2026-08-10 執行)

執行腳本:`scripts/technical_mean_reversion_lab.py`。完整輸出:
`research/technical_mean_reversion_lab/{summary.csv, horizon_curve.csv, pool_comparison.csv,
interaction_results.csv, era_results.csv, README.md}`。以下摘要對齊 §4 判定門檻。

- **H1(horizon curve)—— 混合結果**:布林%B、MA偏離的 Wide IC 從 T+1/T+20 顯著負
  (t −3.5~−3.7)衰減到 T+60 趨近0/翻正(t −0.89 / +0.43),**支持短期均值回歸**;
  但**法人賣轉買 rev_score 的負向在 T+60 反而最顯著**(t −2.63)——**不支持**純短期解釋,
  §1 現有證據「賣轉買=反指標」延伸到 T+1/T+60 後依然成立且不衰減。
- **H2 / H3 — 未執行**(依 §5 凍結)。
- **H4(Wide vs dual100)—— 不支持 universe conditioning**:四個訊號在 dual100 primary
  (~48 檔,T+20)沒有一個 |t|≥2 顯著轉正(RSI14 t−0.26、布林%B t+0.65、MA偏離 t−0.47、
  賣轉買rev t+1.88 僅一點之差)。**依出口 2 結案:品質池不能救這組技術代理。**
  Post-hoc(非判定):MA偏離在 dual100 的 LS10 三視野皆顯著正(t +2.41~+3.52,IC 卻不顯著);
  法人賣轉買rev 在 dual100 T+1/T+20 近顯著轉正(t 1.88~1.92)但 T+60 不持續。
- **H5(反向穩定性)—— 反向方向的 IC 符號六時代全部一致**(RSI14/布林%B/MA偏離/賣轉買rev
  皆 6/6 同號),RSI14/布林%B/MA偏離的 T+20 full-period |t|≥3.17;**但正向失效≠反向可交易**,
  H6 顯示反向的量級被市場整體報酬淹沒(見下)。
- **H6(interaction)—— 方法論不足以回答**:median-split bucket 用的是未去 beta 的
  raw 平均前瞻報酬,各 bucket 在 T+20 全部落在 0.89%~1.11% 窄幅內,無法從中分離出交互作用
  的邊際訊息。這是誠實的方法缺口,不是「沒有共振效果」的結論。
- **H7 — 併入 H5/H8 判讀**,底層資料見 `era_results.csv`。
- **H8(regime,exploratory)—— 符號不隨牛熊翻轉,空頭段效果量放大 2~6 倍**
  (如 MA偏離 t −1.66→−4.34)。不進 confirmatory 判定。

**是否值得進下一輪預註冊**:原始問題「KD/BB/MA on dual100」**不值得**——四訊號在凍結門檻
下沒有一個翻正,§1 現有證據被重新驗證且未被推翻。但衍生出三個更窄的候選(需個別另立
預註冊,不得沿用本案數字直接當結論):(1) MA偏離「短打後動能延續」的 T+60 型態;
(2) 法人賣轉買 rev_score 在 dual100 的近顯著轉正,值得擴大樣本重測;(3) H2 event study
仍是「賣轉買為何負」機制問題的最大空白,但那是先要建日頻資料管線的基礎設施工單。
完整判讀見 `research/technical_mean_reversion_lab/README.md`。
