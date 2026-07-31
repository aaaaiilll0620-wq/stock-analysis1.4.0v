# 架構分離 · 策略本體 / regime overlay / 三階基準

**建立**:2026-07-30。**觸發**:雙確認 @ADV≥100萬 六關全過(預註冊 §7.1)後,Codex 於
`GPT answer.md` 提出的架構關切 —— market regime 同時介入「選股」與「曝險」,使漂亮的
高夏普 / 低 MDD 無法歸因給選股本體。本文件把三件被混在一起的東西**在報告與驗證層分離**,
並列出還沒驗、需要另行預註冊的假設與順序。

**本文件不改任何程式碼**(遵 Codex 建議與研究紀律:先釐清架構再動手)。

---

## 1. 現在被混在一起的三件事

| 層 | 是什麼 | 程式入口 | 已驗證? |
|---|---|---|---|
| **A. 策略本體** | `real_composite` Top20% ∩ `c2` Top20%,等權、**固定 100% 曝險、無 regime** | `dual100_lab.py`(研究線)/ `scoring_manager` 真身分數 | ✅ **已驗**:H1–H5 全過 |
| **B. regime 選股介入** | 市場燈號改**五維權重**與**評級門檻**,改變選股排序本身 | `core/advisor.py` | ❌ 未拆出來單獨驗 |
| **C. regime 曝險 overlay** | 市場燈號調整**整體持倉曝險**(0→1 階梯),純風控 | `core/regime_exposure.py` | ❌ 未預註冊、未驗增益 |

> 關鍵誤導:實盤敘事裡「夏普 ~0.95 / MDD ~−25%」是 **A+B+C 疊起來的組合結果**,
> 而本案 H1–H5 驗的是**純 A**。純 A 的真實尾端是 **H4 全期 MDD −68.7% ~ −70.4%**(0.25–0.60% 滑價)。
> **不得把 A+B+C 的低 MDD 回稱為 A 的績效。**

---

## 2. 程式碼實證(Codex 關切已逐點查證)

### B — regime 介入選股(`core/advisor.py`)
- `:104-113` `advise()`:若 `current_regime` 有值,先套 `regime_multipliers(current_regime)`
  調整五大類權重(基本面/估值/技術/動能/籌碼),**再**做 per-stock 動態權重。
- `:507-509` `_decide_rating()`:bear 段另有評級閘門 —— regime 不只改排序權重,也改**評級門檻**。
- `current_regime` 由回測/計分迴圈逐 as_of 設定;預設 `None`(`:50`)→ 不調整。

### C — regime 曝險 overlay(`core/regime_exposure.py`,225 行)
- 等權全市場指數 vs MA50/100/200 → 曝險階梯 3/3、2/3、1/3、0;UP/DOWN 各 3 日遲滯確認。
- 已受 `docs/預註冊_ExposureRateLimit.md`(2026-07-29)約束:每交易日最大調整 0.20。
- 輸出 `exposure`(0~1),與選股正交 —— 是**在本體選股結果之上**再乘曝險。

### A 確為「無 regime」—— 已查證,不是假設
- `beat_0050/realbody/build_realbody_scores.py`:**無** `regime` / `current_regime` 參照;
  `score_row(..., MODE, ...)` 用固定 MODE,**從不設** `current_regime`。
- `core/scoring_manager.py`:**無** `current_regime` / `regime_multipliers` 參照。
- ⇒ `realbody_scores_adv100w.parquet` 的 `real_composite` 是在 `current_regime=None` 下算的,
  **不含 regime 調整**。dual100 的 H1–H5 因此是乾淨的策略本體檢定。**這正是 Codex 要的隔離,
  本案已天然滿足。**

---

## 3. 報告紀律(即刻生效,不需改碼)

凡引用本策略績效,一律標明處於哪一層,不得跨層借數字:

```text
A 策略本體(已驗):
  real_composite ∩ c2、等權、固定 100% 曝險、無 regime
  報 CAGR / 夏普 / MDD / 換手 —— 就是 dual100 §7.1 的數字
  本期成績:全期夏普 0.89、OOS(2010+)CAGR 22.79 / 夏普 1.20、H4 全期 MDD ≈ −70%

B+C regime(未驗):
  在 A 之上疊 regime 選股介入(B)與曝險 overlay(C)
  只能報「相對 A 的 CAGR / 夏普 / MDD 增減」,且須標「未預註冊」
  ❌ 不得把疊加後的低 MDD / 高夏普回稱為 A 的績效

基準(三階,已定案):
  ① 同池等權母體 → 選股能力    ② 持股數×換手對齊隨機 → 是否超越交易 footprint
  ③ 0050 → 機會成本
```

---

## 4. 還沒驗、需要另行預註冊的假設(建議順序)

> 全部遵單發射擊制:先凍結門檻與搜尋空間,再看樣本外數字。DSR 的 trial 數須把
> 「regime 參數也是先前工作挑的」計入,不得只報宣告空間內的 N。

1. **P-Overlay-C(曝險 overlay 的增益)** — 最優先,因為它是低 MDD 的來源。
   - 對象:A 本體淨值 vs A×C(曝險 overlay)淨值,同期同時鐘。
   - 假設:C 在**不顯著犧牲 CAGR** 的前提下把 MDD 從 ~−70% 壓到某門檻(門檻先寫死)。
   - 關卡:MDD 改善須在 walk-forward OOS 成立(overlay 參數 MA 窗、遲滯天數、限速已在
     `預註冊_ExposureRateLimit` 部分凍結 → 引用,不得重挑)。
   - 陷阱:C 用「等權全市場 vs MA」當燈號,與 A 的選股池高度相關,增益可能是隱性擇時。

2. **P-Regime-B(regime 選股介入是否加分)** — 次之,爭議最大。
   - 對象:A(無 regime 本體)vs A+B(regime 改權重/評級),同池同期。
   - 假設:B 使**選股階(基準①)**在 OOS 提升且非過擬合(對齊隨機虛無 p<0.01)。
   - 難點:B 改的是評分排序,無法用現成 `real_composite` 面板測 —— 需另建「regime-on」真身面板
     (再跑一次 `build_realbody_scores`,設 `current_regime` 逐 as_of),成本數小時級。
   - **若 B 無法在 OOS 證明加分,應考慮把 regime 移出選股、只留 C 當純風控 overlay**
     —— 這會回答「到底是選股有效還是燈號避開下跌」。

3. **P-Pool-Dynamic(動態選池是否優於固定池)** — 低優先。
   - 現況:H2 走查 17/17 全挑 100萬,動態與固定同淨值 → 動態性**沒有**獨立證據。
   - 除非未來資料出現分歧,否則直接**採固定 100萬 池**,不主張動態選池(§4 出口 2 精神)。

---

## 5. 目標定義(使用者 2026-07-30 拍板,凍結為下一份預註冊的前提)

| # | 題 | **定案** |
|---|---|---|
| 1 | 「20–30%」量的是什麼 | **扣成本後的 walk-forward OOS CAGR**。全期 CAGR 只作描述,不作判定。20% 最低、30% 理想。 |
| 2 | 是否扣成本 | **是** —— 先扣目前預註冊的手續費 + 滑價(0.72% 來回)。零股實際撮合溢折價**另用小額活體演練**驗證,不併入回測門檻。 |
| 3 | 20 與 30 的關係 | **20% = pass/fail 硬門檻;30% = stretch goal**。正式驗證不要求每次達 30%。 |
| 4 | MDD 上限 | **策略本體 A 不因 MDD −70% 而否定**(A 的任務是產 alpha)。但**進正式部署**須驗證 **A + regime overlay** 後 MDD 達上限。**MDD ≥ −40% 為正式部署門檻(使用者 2026-07-30 確認,最終值,非暫定)**。 |
| 5 | ADV 池 | **固定 `ADV≥100萬` 作策略候選**。H2/H2b 證明「挑 100萬」可即時複製,但**不宣稱動態選池優於固定選池**。 |

### 依定案重新對齊已驗數字

- **主判定指標 = 扣成本 OOS CAGR**:本體 OOS(2010-01~2026-03)**22.79%**(H2 §7.1)。
  → **≥ 20% pass ✅**,距 30% stretch 尚有空間(未達,但依 #3 不要求)。全期 CAGR 20.80% 僅描述。
- **MDD**:本體 A 全期 −68.7%~−70.4%(H4)**不否定 A**(#4)。−40% 上限是**掛在 A+overlay(P-Overlay-C)
  的部署前置條件**,不是 A 自己的門檻 —— 這把 P-Overlay-C 從「加分項」升級為**上線必過項**。

### 對 §4 待預註冊順序的影響

- **P-Overlay-C 的通過門檻據此寫死**:A×overlay 的 walk-forward OOS **① MDD ≥ −40%(最終門檻)
  且 ② OOS CAGR 仍 ≥ 20%(overlay 不得把報酬壓到 pass 線下)**。兩者皆須在 OOS 成立。
  → **已凍結(2026-07-31,Codex 審查通過)**:`預註冊_ExposureOverlay.md`(HO1–HO4、§8-Z 凍結紀錄)。
    凍結範圍為 **overlay 研究預註冊**;月頻 dual100 的實盤執行 SOP 仍須另案預註冊,**通過≠可上線**。
- **P-Regime-B**、**P-Pool-Dynamic** 的目標語意同上(OOS、扣成本、20% 硬線)。

---

## 6. 一句話結論

> **選股本體(A)已走完完整預註冊、六關全過,是本專案第一個做到的策略;它有真實選股 alpha,
> 全期 CAGR 也落在 20–30% 區間 —— 但它的尾端風險(MDD ≈ −70%)很深,低 MDD 的漂亮數字來自
> 尚未驗證的 regime overlay(C)與 regime 選股介入(B)。下一步不是再調權重,而是分層把 C、B
> 各自預註冊驗一遍,並先請使用者把「20–30% / MDD 上限」的目標語意定死。**

相關:`預註冊_雙確認ADV100萬.md` §7.1、`基準階梯_BenchmarkLadder.md`、
`研究紀律_ResearchDiscipline.md`、`預註冊_ExposureRateLimit.md`、`開發日誌_DevLog.md` §12。
