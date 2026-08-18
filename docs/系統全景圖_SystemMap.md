# 系統全景圖 — 上游資料 → 因子 → 篩選 → 投組（Mermaid）

> 建立日期：2026-08-11。**本文件不產生任何新結論**，只把當前程式碼的節點、條件、事件順序畫成圖。
> 所有數字皆由逐檔讀取程式碼取得（非讀 memory/舊 devlog 推測），附 `file:line`；
> 若程式碼日後變動，**以程式碼為準**，請重新掃描更新本文件，不要手動改數字。
>
> 與 `docs/專案完整流程地圖_PipelineOverview.md`（2026-07-19）的差異：該文件早於
> `c2_fullpool` 全池輸出、L4a/L4b 部署層、overlay α 內插三項變更，本文件為較新的快照。

## 圖例

| 標記 | 意思 |
|---|---|
| 實線 | 生產路徑上的資料流 |
| 虛線 | 條件性/退回/僅顯示，不影響計算 |
| 菱形 | 判定條件（附精確門檻） |
| `⛔` | fail-closed：條件不滿足即 **abort/raise**，不得靜默降級 |
| `❌停用` | 程式碼算得出來但不進分（A/B 未過閘門） |
| `⚖️豁免` | 研究否定，但使用者明文豁免採用 |

---

## D1 · 全景骨架（兩條管線，最後在交集合流）

```mermaid
flowchart TD
    subgraph UP["① 上游資料層"]
        TEJ["TEJ 種子庫 ~/tej_cache<br/>tej_importer.py 手動匯入 10 dataset<br/>2004-2026 全歷史"]
        SNAP["官方每日快照 ~/market_cache<br/>market_snapshot_collector.py<br/>平日 17:30 · 0 FinMind API"]
        FM["FinMind API<br/>僅本機資料過期時退回"]
    end

    TEJ --> DP["core/data_provider.py<br/>本機優先組裝 PIT StockData"]
    SNAP --> DP
    FM -. 退回 .-> DP

    TEJ --> SCR["scripts/universe_screen_daily.py<br/>全市場粗篩 · 0 API"]
    SNAP --> SCR

    DP --> PA["② 管線 A<br/>五維綜合分 real_composite<br/>逐檔計分"]
    SCR --> PB["③ 管線 B<br/>c2 四腳分數<br/>全市場橫斷面百分位"]

    PA --> SS["core/score_store.py<br/>Scores 快照<br/>母體 = watchlist.txt 958 檔"]
    PB --> C2F["c2_fullpool_date.csv<br/>母體 = listed_ok 且 ADV20 >= 100萬<br/>對齊 H1-H5 驗證定義"]
    PB --> SL["shortlist_date.csv<br/>五因子聯集 · 僅供瀏覽"]

    SS --> FUSE{"④ 雙確認交集<br/>composite 百分位 >= 80<br/>且 c2 百分位 >= 80"}
    C2F --> FUSE

    FUSE --> L4A["⑤ L4a 決策層<br/>scripts/l4a_decision.py<br/>OrderIntent 不可變"]
    L4A --> L4B["⑥ L4b 執行帳本<br/>scripts/l4b_execution.py<br/>T+1 open 成交回報"]
    L4B --> PORT["⑦ 實盤投組<br/>等權 · 月頻全換股 · 約 48 檔"]

    EXPO["core/regime_exposure.py<br/>C 層曝險 overlay<br/>alpha=0.25 → 75%-100%"] -.->|"⚖️豁免採用 調整部位大小"| PORT

    PA --> ADVR["core/advisor.py<br/>四級評級判定"]
    ADVR --> WEB["app.py 網頁 / main.py CLI<br/>個股分析與排行"]
    SL --> WEB
    SS --> WEB

    PA --> BT["core/backtest.py<br/>PIT 回測驗證"]

    classDef verified fill:#dff5e1,stroke:#2e7d32,color:#1b5e20
    classDef caution fill:#fff4d6,stroke:#b8860b,color:#5c4400
    class FUSE,L4A,L4B,PORT verified
    class EXPO,SS caution
```

**這張圖最重要的兩件事：**

1. **管線 A 與管線 B 的母體不同。** A 的母體是人工維護的 `watchlist.txt`（958 檔），
   B 的母體是逐日全市場 ADV 篩選。兩邊算出的百分位不在同一個分母上——這是**已知未修的落差**。
2. **下游有兩條完全不同的分岔。** 走 `FUSE → L4a → L4b` 的投組路徑才是通過 H1–H5 驗證的策略；
   走 `advisor → 四級評級` 的網頁路徑從未走過完整預註冊驗證。

---

## D2 · 上游資料層：來源優先序與新鮮度閘門

```mermaid
flowchart TD
    START(["請求某 dataset"]) --> LOCAL{"本機有資料？<br/>TEJ 種子 ∪ 官方快照<br/>重疊日以 TEJ 為準"}
    LOCAL -- 否 --> FMAPI["打 FinMind API"]
    LOCAL -- 是 --> FRESH{"新鮮度閘門<br/>逐 dataset 不同"}
    FRESH -- 過期 --> FMAPI
    FRESH -- 新鮮 --> USE["用本機資料<br/>0 API"]
    FMAPI --> CACHE["core/data_cache.py<br/>讀寫穿透 → ~/finmind_cache<br/>查過即落地重用"]
    CACHE --> USE

    subgraph GATE["新鮮度閘門明細 data_provider.py"]
        G1["日K + PER/PBR/殖利率：落後 > 7 天"]
        G2["法人買賣超毛額：覆蓋 < 40 筆或落後 > 7 天"]
        G3["融資餘額：覆蓋 < 30 筆或落後 > 8 天"]
        G4["流通股數/外資持股率：落後 > 10 天<br/>僅收集器，無 TEJ 種子"]
        G5["月營收：落後 > 70 天<br/>含 release_date 真實公告日"]
        G6["三大財報季：落後 > 175 天<br/>僅 TEJ 種子"]
        G7["產業別：本機 JSON 快取 30 天內視為新鮮"]
        G8["TAIEX 大盤位階：純 FinMind 無持久快取"]
    end

    FRESH -.-> GATE

    classDef gatebox fill:#f4f4f8,stroke:#666,color:#222
    class G1,G2,G3,G4,G5,G6,G7,G8 gatebox
```

**PIT 三道防線**（`core/backtest.py`）：價格/PER/月營收只取 `date <= as_of`；
季報只用「公告日 + 45 天 <= as_of」；報酬量測允許看未來收盤價（那是結果不是輸入）。

---

## D3 · 管線 B：全市場粗篩漏斗（含 fail-closed 中止點）

```mermaid
flowchart TD
    ALL["全市場 約 1900+ 檔<br/>TEJ ∪ 官方快照 含已下市"] --> QUOTE{"今日有報價<br/>close 非空"}
    QUOTE -- 否 --> OUT0["出局<br/>下市股自然排除"]
    QUOTE -- 是 --> POOL["pool 全池<br/>已算好四腳原始值"]

    POOL --> L0{"L0 因子可評估<br/>value_pct 非空<br/>PE expanding 分位<br/>樣本 >= 60 且起算 2019-01-01"}
    L0 -- 否 --> OUT1["出局"]
    L0 -- 是 --> L1{"L1 可投資性<br/>adv20 >= 1000萬 NTD<br/>且 上市滿一年<br/>首見日 <= 2019-01-10 或 >= 365 天"}
    L1 -- 否 --> OUT2["出局"]
    L1 -- 是 --> L2{"L2 價值陷阱排除<br/>剔除 value_pct > 90<br/>且 最新月營收 YoY 非正<br/>含未知"}
    L2 -- 命中陷阱 --> OUT3["剔除"]
    L2 -- 通過 --> CAND["候選池 pool_date.csv<br/>約 700-810 檔"]

    CAND --> F5["計算五因子 + 池內百分位"]
    F5 --> UNION{"五因子聯集<br/>任一因子池內百分位 > 85<br/>門檻 = 100 - shortlist_union_pct 15"}
    UNION -- 是 --> SLOUT["shortlist_date.csv<br/>約 400-480 檔<br/>依 c2_score 排序"]
    UNION -- 否 --> OUT4["不入榜"]

    POOL --> FULLPOP{"全池 c2 母體<br/>adv20 >= 100萬 且 listed_ok<br/>不套 L0 不套 L2"}
    FULLPOP --> C2FULL["c2_fullpool_date.csv<br/>c2_score_full<br/>投組實際讀這個"]

    subgraph GUARD["⛔ fail-closed 守衛 寫檔前"]
        GA["industry_value_ref 查無當日列 → abort"]
        GB["value_ind 腳池內 NaN > 20% → abort"]
        GC["c2 任一腳覆蓋率 < 95% → abort"]
        GD["最新已知營收月落後 > 45 天 → WARN"]
    end

    F5 -.-> GUARD

    classDef stop fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    classDef good fill:#dff5e1,stroke:#2e7d32,color:#1b5e20
    class GA,GB,GC,GD stop
    class C2FULL good
```

### 五因子與 c2 的關係

```mermaid
flowchart LR
    subgraph FIVE["五因子 · 只負責圈人 聯集入 shortlist"]
        V["value_ind_pct<br/>產業內估值位階"]
        M["momentum20<br/>20 日報酬率"]
        C["chip20_turnover<br/>20日法人淨額 / 20日量"]
        H["high52_prox<br/>收盤 / 近240日最高收盤"]
        R["rev_accel<br/>最新月YoY - 近3月均YoY<br/>PIT 月底+10天才算已知"]
    end

    subgraph C2["c2_score · 負責排序 進投組的是它"]
        C2V["value_ind_pct 百分位"]
        C2R["revenue_yoy 百分位"]
        C2H["high52_prox 百分位"]
        C2M["100 - momentum20 百分位<br/>⚠️ 反向"]
    end

    V --> C2V
    H --> C2H
    M -- 取反向 --> C2M
    R -.->|"rev_accel 不進 c2 · c2 用的是 revenue_yoy"| C2R
    C -.->|"chip 腿不進 c2"| X["僅用於聯集圈人"]

    C2V --> AVG["等權平均 skipna"]
    C2R --> AVG
    C2H --> AVG
    C2M --> AVG
    AVG --> OUT["c2_score"]
```

> **注意兩個常見誤解**：①`chip20_turnover` 和 `rev_accel` 只參與「圈人」，**不進 c2 排序分**；
> c2 的營收腿用的是 `revenue_yoy` 不是 `rev_accel`。②動能腿在 c2 裡是**反向**的
> （`100 - momentum20_pct`），也就是 c2 偏好「短期沒漲、但便宜 + 營收成長 + 接近 52 週高」的股票。

---

## D4 · 管線 A：個股五維計分（子因子與配分）

```mermaid
flowchart TD
    SD["StockData PIT 快照<br/>data_provider 組裝"] --> F["FundamentalEngine<br/>core/fundamentals.py"]
    SD --> VA["ValuationEngine<br/>core/valuation.py"]
    SD --> TE["TechnicalEngine<br/>core/technical_analysis.py<br/>算原始指標"]
    TE --> SM["ScoringManager<br/>core/scoring_manager.py"]
    SD --> SM

    F --> FB["基本面分 0-100<br/>獲利 0.30 / 成長 0.25<br/>安全 0.25 / 估值 0.20"]
    FB --> HARD{"硬門檻<br/>負債比 > 85%<br/>流動比 < 50%<br/>淨利率 < -10%<br/>cash_quality < 0.5"}
    HARD -- 任一命中 --> NOPASS["is_passed = False<br/>直接影響評級：謹慎避開"]

    VA --> VL1{"產業內估值位階可用？<br/>industry_value_ref 距查詢日 <= 10 天<br/>且產業樣本 >= 5 檔"}
    VL1 -- 是 --> VOUT["估值分 = 產業內位階 100%"]
    VL1 -- 否 --> VL2["退回 PEG 85% + 相對歷史位階 15%"]
    VL2 -- 再無值 --> VL3["退回絕對門檻<br/>PE 35 / PB 25 / PS 20 / 殖利率 20"]
    VOUT --> BUBBLE{"昂貴泡泡？<br/>pe_percentile >= 80<br/>且無法用 PEG<1.0 或 營收YoY>=15% 解釋"}
    BUBBLE -- 是 --> CAP["估值分封頂 30"]

    SM --> TS["技術面分"]
    SM --> MS["動能面分"]
    SM --> WS["籌碼面分"]

    subgraph TECH["技術面配分 最高約 98"]
        T1["短均線結構 價>MA5 / MA5>MA20 / 價>MA20 各 10 → 30"]
        T2["週線 MA20 → 15"]
        T3["RSI 位階 50-70 給 25 · 70-75 給 15 · >75 只給 8 · <30 給 0 → 25"]
        T4["MACD bullish_strong 20 / recovery 15 / neutral 8 → 20"]
        T5["布林 收斂 8 / 擴張 5"]
        T6["MA20/60 金叉 +6 · 死叉 -8"]
        T7["❌停用 布林 %B · 完整 KD"]
    end

    subgraph MOM["動能面 三塊 45+30+25"]
        M1["A 中期價格 mom_6m 最多 30 + mom_3m 最多 15<br/>衰竭抑制 6月>12% 但 3月<-5% 扣 8"]
        M2["A2 相對強弱 RS vs 0050 ±8<br/>✅ 唯一通過 A/B 的候選"]
        M3["B 營收動能 accel 14 + 累計YoY 10 + 連續成長月數 6"]
        M4["C 短線確認 量能 spike 10 + MA20 乖離 10<br/>量價背離 -5 · KD J>100 -3"]
        M5["❌停用 OBV 20 日趨勢"]
    end

    subgraph WHALE["籌碼面 v4.2 重構"]
        W1["基底 = 48 + 加權法人淨參與率 × 300<br/>天期權重 1日.10 / 3日.15 / 5日.25 / 10日.25 / 20日.25"]
        W2["土洋同步 +8"]
        W3["連續買賣超天數 各 cap 3 天 ±12<br/>已從基底降級為 bonus"]
        W4["確認層 ±15 大戶集中度/法人參與/流入加速/量能集中"]
        W5["❌停用 TDCC 大戶週變化 ±8 預設恆為 0"]
        W6["無多天期資料 → 退回舊版連買天數計法"]
    end

    TS -.-> TECH
    MS -.-> MOM
    WS -.-> WHALE

    classDef off fill:#eeeeee,stroke:#999,color:#666
    class T7,M5,W5 off
```

---

## D4a · 籌碼面「多天期法人淨參與率」完整算式

### 第一段：原始資料 → `net_ratio` 字典（`core/data_provider.py:1500-1574`）

```mermaid
flowchart TD
    CHIP["chip_df 法人買賣超<br/>TEJ institutional_gross ∪ 官方快照<br/>覆蓋 < 40 筆或落後 > 7 天才退回 FinMind"] --> COLS["自動偵測 buy / sell 欄名<br/>排除 buy_share_per / sell_share_per 比例欄"]
    COLS --> SPLIT{"依 name 欄分流"}
    SPLIT -->|"Investment_Trust · Investment Trust · 投信"| TRUST["trust_df 投信"]
    SPLIT -->|"Foreign_Investor + Foreign_Dealer_Self · 外資"| FOR["foreign_df 外資<br/>兩種名稱同日兩筆一起加總"]
    SPLIT -->|"Dealer 自營商"| DROP["⛔ 剔除<br/>避險雜訊不進籌碼分"]
    SPLIT -.->|"trust_df 或 foreign_df 為空"| WARN["logger.warning<br/>印出實際出現的 name 清單<br/>不中止"]

    CHIP --> DATES["dates_sorted = chip 日期去重排序"]
    DATES --> CUT["_cut n = dates_sorted 倒數第 n 個<br/>不足 n 天 → 退回 dates_sorted 第一個"]

    TRUST --> NUM["分子 _net_buy_lots<br/>Σ buy − sell 於 date >= cut_n<br/>股數 ÷ 1000 → 張<br/>正值買超 負值賣超"]
    FOR --> NUM
    CUT --> NUM

    PX["price_df Trading_Volume<br/>單位 = 股"] --> DEN["分母 _vn<br/>tail n 列加總 ÷ 1000 → 張"]

    NUM --> GUARD{"_vn > 0 ?"}
    DEN --> GUARD
    GUARD -- 否 --> MISS["該天期不寫入字典<br/>缺鍵 → 下游 fr.get n, 0.0 當 0 計"]
    GUARD -- 是 --> RATIO["net_ratio n = 分子 ÷ 分母<br/>signed · 市值中性 · 無因次"]
    RATIO --> DICT["foreign_net_ratio 與 trust_net_ratio<br/>n ∈ 1, 3, 5, 10, 20"]

    classDef stop fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    class DROP,MISS stop
```

> **⚠️ 分子分母的窗不是同一把尺。** 分子的窗由 **chip 交易日**決定（`dates_sorted[-n]` 起、含當日往後全取），
> 分母是 **price_df 的最後 n 列**。兩邊日期覆蓋一致時等價；一旦 chip 天數不足 n
> （`_cut` 退回最早日），分子涵蓋的天數會**少於** n，分母仍取 n 天 → 該天期的比率被系統性稀釋。
> 這不是已量化過的偏誤，只是從程式碼讀出來的口徑落差，**列為待查項，不構成任何結論**。

### 第二段：`net_ratio` → 籌碼分（`core/scoring_manager.py:321-377`）

```mermaid
flowchart TD
    D["foreign_net_ratio + trust_net_ratio"] --> EMPTY{"兩個 dict 都空？<br/>live 未接線或無 chip 資料"}
    EMPTY -- 是 --> LEGACY["退回 _legacy_whale_score<br/>基底 = 連買天數 × 20<br/>大型股法人買賣交錯 → 天數恆 0 → 基底塌陷<br/>這正是 v4.2 重構要解決的病"]
    EMPTY -- 否 --> COMB["combined_ratio<br/>= Σ w_n × fr_n + tr_n<br/>w = 1日 .10 · 3日 .15 · 5日 .25 · 10日 .25 · 20日 .25"]

    COMB --> BASE["基底 score = 48 + combined_ratio × 300<br/>_RATIO_TO_POINTS = 300<br/>±0.1 淨參與率 ≈ ±30 分 · 中性 ≈ 48"]

    BASE --> SYNC{"土洋同步？<br/>fr5 > 0 且 tr5 > 0<br/>或 fr10 > 0 且 tr10 > 0"}
    SYNC -- 是 --> ADD8["+8"]
    SYNC -- 否 --> STREAK
    ADD8 --> STREAK["連續買賣超天數 bonus<br/>+ min 外資連買, 3 × 2<br/>+ min 投信連買, 3 × 2<br/>− min 外資連賣, 3 × 2<br/>− min 投信連賣, 3 × 2<br/>合計上下限 ±12"]

    STREAK --> ADJ["確認層 adj · 最後 clip 到 ±15"]
    ADJ --> A1["投信吸籌比 whale_concentration<br/>>= 1.0 → +8 · >= 0.3 → +4<br/>= 投信近20日淨買股數 ÷ 流通股數 × 100"]
    ADJ --> A2["法人成交占比 institutional_participation<br/>>= 40 → +4 · >= 25 → +2<br/>= 外資+投信近10日 買+賣 股數 ÷ 2 × 市場同期總量"]
    ADJ --> A3["流入加速 flow_acceleration<br/>combined_ratio > 0 且 >= 1.5 → +5<br/>= 近5日日均淨買 ÷ 近20日日均淨買<br/>由賣轉買一律記 2.0"]
    ADJ --> A4["量能集中度 volume_concentration<br/>>= 55 → +3 · 落在 0 到 45 → −3<br/>= 近20日上漲日成交量佔比"]

    A1 --> SUM
    A2 --> SUM
    A3 --> SUM
    A4 --> SUM["adj = clip −15 到 +15"]

    SUM --> TDCC["TDCC 大戶週變化 tdcc_adj<br/>週增 → +min 變化×4, 8<br/>週減 → −min 變化×4, 8<br/>週減但法人在買 → 再 −3 背離懲罰<br/>❌ 預設關閉 恆為 0"]

    TDCC --> RAW["raw = 基底 + 同步 + 天數 + adj + tdcc_adj"]
    RAW --> CLIP{"RESEARCH_ARM == B2 ?"}
    CLIP -- 是 --> NOCLIP["不 clip<br/>解除飽和實驗 已驗證否決 t −4.249 / −6.130"]
    CLIP -- 否 --> FINAL["clip 到 0 到 100<br/>→ whale bucket"]

    classDef off fill:#eeeeee,stroke:#999,color:#666
    classDef stop fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    class TDCC off
    class NOCLIP stop
```

**攤平成一行的話：**

```
whale = clip(
    48
  + 300 × Σ_{n∈{1,3,5,10,20}} w_n × ( fr_n + tr_n )        ← 基底，w = .10/.15/.25/.25/.25
  + 8·[土洋同步]                                            ← 確認
  + 2·min(外資連買,3) + 2·min(投信連買,3)
  − 2·min(外資連賣,3) − 2·min(投信連賣,3)                    ← ±12
  + clip(吸籌比 + 法人占比 + 流入加速 + 量能集中, −15, +15)
  + tdcc_adj                                                ← 恆為 0
, 0, 100)
```

**這張圖要一起帶的三個事實**（來自 `docs/血緣稽核_五維度_2026-07-31.md`，不是新結論）：
籌碼面真身 Rank IC **−0.0119 (t −2.20)**，方向為負；**15.75% 的樣本撞到 clip 邊界**；
解除飽和（B2）已驗證**否決**。也就是說這條精算過的算式，在排序上目前是負貢獻。

---

## D5 · 五維合成：兩層權重調整（引擎最容易被忽略的一段）

```mermaid
flowchart TD
    B1["基本面 bucket"] --> MW
    B2["估值 bucket<br/>資料不足 → 以中性 50 計"] --> MW
    B3["技術 bucket"] --> MW
    B4["動能 bucket"] --> MW
    B5["籌碼 bucket"] --> WASH{"洗盤尾聲偵測<br/>回檔 + 法人賣超<br/>+ 融資10日減 <= -8%"}
    WASH -- 命中 --> B5B["籌碼分不給極低分<br/>max 60 再 +5"] --> MW
    WASH -- 未命中 --> MW["mode_weights<br/>balanced<br/>fund .31 / val .08 / tech .19<br/>mom .27 / whale .15"]

    MW --> RG{"current_regime 有設定？<br/>core/regime.py<br/>0050 + MA120 + 斜率<br/>+ 週線確認 + 深跌破 7% 快速通道"}
    RG -- None --> DYN
    RG -- bull --> RGB["乘數 tech 1.05 · mom 1.10"]
    RG -- neutral --> RGN["乘數全部 1.00"]
    RG -- bear --> RGD["乘數 fund 1.00 · val 0.60<br/>tech 0.30 · mom 1.50 · whale 0.30<br/>v3 版：2022 實測動能有效、籌碼是毒藥"]
    RGB --> DYN
    RGN --> DYN
    RGD --> DYN

    DYN{"個股動態權重<br/>強勢多頭排列？"} -- 是 --> DYNON["估值權重砍 60%<br/>轉給動能與籌碼"]
    DYN -- 否 --> NORM
    DYNON --> NORM["重新正規化 wsum"]

    NORM --> COMP["composite = Σ bucket × w / Σw<br/>= real_composite"]
    COMP --> STORE["score_store 落地<br/>每列附 weights_version 雜湊<br/>權重改版可辨識該重算的歷史列"]
    COMP --> RATE["四級評級判定"]

    classDef bearbox fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    class RGD bearbox
```

> **⚠️ 兩套「大盤多空」不是同一個節點，畫圖時務必分開：**
>
> | | `core/regime.py` | `universe_screen_daily.py::bear_regime` |
> |---|---|---|
> | 基準 | 0050 單檔 | 自建全市場等權指數 |
> | 均線 | MA120 + 斜率 + 週線確認 + 不對稱冷卻 | MA200 |
> | 效果 | **實際改變**評分權重與評級門檻 | **僅顯示警示**，不回饋任何篩選/排序 |
>
> `classify_regime()` 在 2005-2018 的 168 個月一律回 `neutral` → regime 乘數從未生效；
> **2019 年後才真正生效**（B 層）。所以「本體 A 無 regime」是錯誤描述。

### 四級評級判定順序（網頁/CLI 路徑，非投組路徑）

```mermaid
flowchart TD
    S1{"1 硬性致命<br/>is_passed=False 或 現金流 high_risk<br/>或 RSI<30 且 動能分<20"} -- 是 --> R1["謹慎避開<br/>除非止跌翻多+籌碼流入 → 救回觀望"]
    S1 -- 否 --> S2{"2 強勢買進 順勢動能軌<br/>基本面未破 + 非昂貴泡泡 + 站上月線/週線<br/>+ 動能/技術/營收三選一夠熱<br/>+ 籌碼有實質流入 + 非量價背離"}
    S2 -- 是 --> R2["強勢買進<br/>特赦估值過高/RSI過熱/乖離過大"]
    S2 -- 否 --> S3{"3 估值型軟避開<br/>估值偏高 且 total_score < 50"}
    S3 -- 是 --> R3["謹慎避開"]
    S3 -- 否 --> S4{"4 主力洗盤尾聲"}
    S4 -- 是 --> R4["觀望追蹤"]
    S4 -- 否 --> S5{"5 強烈推薦 兩軌擇一<br/>A 價值品質軌：現金流健康+估值偏低/合理+籌碼夠+分數達標+未過熱<br/>B 順勢動能軌：門檻放寬 min_score - 5"}
    S5 -- 是 --> R5["強烈推薦"]
    S5 -- 否 --> R6["觀望追蹤"]
```

門檻依模式浮動（balanced 示例）：`min_score=54`、mom_hot 46 / whale_hot 42 / rev_hot 12 / tech_hot 65；
rsi_overbought 72 / rsi_extreme 78 / bias_chase 15 / chip_min 30。bear 段再由 `regime_rating_gates` 墊高。

---

## D6 · 交集 → L4a → L4b：投組生成的事件時序

```mermaid
sequenceDiagram
    autonumber
    participant SS as score_store<br/>composite
    participant C2 as c2_fullpool
    participant L4A as L4a 決策層
    participant U as 使用者
    participant MKT as 市場 T+1
    participant L4B as L4b 執行帳本
    participant PS as PositionState

    Note over SS,C2: 決策日 t 收盤後 close(t) 算訊號
    L4A->>SS: 讀 composite 並算 pct_rank
    L4A->>C2: 讀 c2_score_full 並算 c2_pct
    L4A->>L4A: 交集 pct_rank >= 80 且 c2_pct >= 80<br/>FUSION_PCT = 20
    Note right of L4A: TOP_N = None 完整交集<br/>TOP15 濃縮已驗證否定並撤銷
    L4A->>L4A: 等權切資金 → 換算張數 LOT_SIZE = 1000
    L4A->>L4A: ADV 上限 單筆訂單 <= ADV20 × 3%
    L4A-->>U: 產出 OrderIntent 不可變快照<br/>ok / rejected 附理由
    Note over L4A,PS: ⛔ L4a 不得改動 PositionState

    U->>MKT: 執行日 t+1 開盤 open(t+1) 下單
    MKT-->>L4B: 成交回報 含未成交
    L4B->>L4B: 買進成本 0.1585% · 賣出成本 0.4585% 含證交稅
    L4B->>PS: 唯一可寫入持倉/現金/成本的節點
    Note over L4B: 零股尚未實作<br/>薄量股部分成交處理待補
```

**L4a 的四種 rejected 理由**：`無參考價`、`ADV20 缺失`、`資金不足一張`、以及 `adv_capped` 下修標記。

---

## D6a · L4a 張數換算與 ADV 上限（`scripts/l4a_decision.py:185-284`）

### 第一段：可投入資本怎麼算（這裡出過一個系統性低估的 bug）

```mermaid
flowchart TD
    IN["build_intents 進場"] --> N{"目標名單 n == 0 ?"}
    N -- 是 --> ABORT["⛔ SystemExit 整批中止<br/>規格 §7：不產生任何 OrderIntent"]
    N -- 否 --> W["target_weight = 1 / n<br/>等權，無其他配重規則"]

    W --> LOOKUP["combined_lookup 價格表<br/>① 先鋪 holdings_price_lookup 全池價格<br/>② 再用 target_list 的價格覆蓋<br/>目標名單的價格優先，那是本次決策當下算的"]
    LOOKUP --> MISS{"有持倉在計分母體查無價格？"}
    MISS -- 有 --> MWARN["⚠️ 印出清單並繼續<br/>port_value 會低估這幾檔<br/>視為單檔資料缺口，不整批中止"]
    MISS -- 無 --> PV
    MWARN --> PV["port_value = pos.cash + holdings_value combined_lookup"]

    PV --> NOTE["🐛 2026-08-10 修過的 bug：<br/>舊版只用目標名單價格估持倉市值<br/>→ 這次被剔除的舊持倉市值直接漏算<br/>→ 月頻全換股下每個月都系統性低估可投入資本"]

    classDef stop fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    classDef fixed fill:#e8eaf6,stroke:#3949ab,color:#1a237e
    class ABORT stop
    class NOTE fixed
```

> **資金唯一來源是 `pos.cash` + 持倉市值。** 曾經有過 `available_capital` 參數但函式體從未讀它，
> 是死參數、容易被誤讀成「資金從這裡流入」，2026-08-10 已移除。首次執行的起始資金是
> `PositionState.empty()` 之後由 `--init-empty` 分支手動設 `pos.cash`。

### 第二段：逐檔換算張數 → OrderIntent

```mermaid
flowchart TD
    LOOP["逐檔處理"] --> KILL{"這檔在持倉但不在目標名單？"}
    KILL -- 是 --> SELLALL["direction = sell · status = ok<br/>order_lots = 全部持倉<br/>reference_price = None<br/>不檢查 ADV 上限"]
    KILL -- 否 --> P{"price 有效？<br/>非 None 且 > 0"}

    P -- 否 --> RJ1["❌ rejected：無參考價<br/>target_lots = current_lots · order_lots = 0"]
    P -- 是 --> A{"adv20 有效？<br/>非 None 且 > 0"}
    A -- 否 --> RJ2["❌ rejected：ADV20 缺失<br/>target_lots = current_lots · order_lots = 0"]

    A -- 是 --> TA["target_amount = target_weight × port_value"]
    TA --> TL["target_lots = floor 除法<br/>target_amount ÷ price × 1000<br/>LOT_SIZE = 1000 · 整張無條件捨去"]

    TL --> CAPC["cap_amount = adv20 × 0.03<br/>ORDER_ADV_CAP"]
    CAPC --> CAPL["cap_lots = floor 除法<br/>cap_amount ÷ price × 1000"]
    CAPL --> CAPQ{"target_lots > cap_lots ?"}
    CAPQ -- 是 --> CAPPED["target_lots ← cap_lots<br/>adv_capped = True<br/>⛔ 差額不得分配給其他股票<br/>規格 §5.1"]
    CAPQ -- 否 --> DELTA
    CAPPED --> DELTA["delta = target_lots − current_lots"]

    DELTA --> DZ{"delta == 0 ?"}
    DZ -- 是 --> NONE{"target_lots == 0 且 current_lots == 0 ?"}
    NONE -- 是 --> NOTE1["direction = none · status = ok<br/>note = 資金不足一張<br/>target_amount 除以股價買不到 1 張"]
    NONE -- 否 --> NOTE2["direction = none · status = ok<br/>現有持倉已等於目標<br/>仍留紀錄，不從稽核軌跡消失"]
    DZ -- 否 --> ORDER["direction = buy 若 delta > 0 否則 sell<br/>order_lots = abs delta<br/>status = ok"]

    SELLALL --> OUT["OrderIntent 不可變快照<br/>append-only 落地"]
    RJ1 --> OUT
    RJ2 --> OUT
    NOTE1 --> OUT
    NOTE2 --> OUT
    ORDER --> OUT

    OUT --> FIN["⛔ L4a 到此為止<br/>不得改動 PositionState<br/>持倉/現金/成本只有 L4b 收到成交回報才更新"]

    classDef stop fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    class RJ1,RJ2,CAPPED,FIN stop
```

**兩個關鍵設計選擇，重新檢視時值得停下來看：**

1. **ADV 上限是「下修」不是「重分配」。** 一檔薄量股被 3% 上限砍掉的額度，
   **不會**攤到其他股票 → 實際部位總和會低於 100%，殘額留在現金。
   這是刻意的：重分配等於偷偷改變等權定義，而等權是 H1–H5 驗過的那個配置。
2. **`target_lots = 0` 有兩種完全不同的原因**，程式碼刻意分開記：
   (a) 資金 ÷ n 檔後買不到一張（小資金 + 高價股）；(b) 現有持倉已等於目標。
   前者就是 `TOP_N=15` 濃縮想解決卻被 H4 滑價否決的那個真問題 ——
   **問題還在，只是「取固定前 15 檔」這個解法被否定了**，目前沒有驗證過的替代解。

> 零股仍未實作。以現行規則，**資金不足一張的部位就是落空**，
> 這也是 §5.7 要求先小額活體演練的原因之一。

---

## D7 · C 層曝險 overlay（⚖️ 研究否定 + 使用者豁免採用）

```mermaid
flowchart LR
    IDX["自建等權全市場指數 日頻<br/>tej_cache ∪ market_cache"] --> MA["對照 MA50 / MA100 / MA200"]
    MA --> LAD{"站上幾條均線？"}
    LAD -- 3 條 --> S3["原始階梯 3/3 → 100%"]
    LAD -- 2 條 --> S2["原始階梯 2/3"]
    LAD -- 1 條 --> S1["原始階梯 1/3"]
    LAD -- 0 條 --> S0["原始階梯 0"]

    S3 --> ALPHA["α 內插壓縮<br/>target = 1 − α ×「1 − raw_ladder」<br/>OVERLAY_ALPHA = 0.25"]
    S2 --> ALPHA
    S1 --> ALPHA
    S0 --> ALPHA

    ALPHA --> FINAL["實際曝險階梯<br/>100% / 91.7% / 83.3% / 75%<br/>永不空手"]
    FINAL --> RL["每日限速器<br/>訊號 close d-1 → 執行 open d<br/>e_lim d ← sig d-1"]
    RL --> SIZE["調整部位大小"]

    classDef exempt fill:#fff4d6,stroke:#b8860b,color:#5c4400
    class ALPHA,FINAL exempt
```

**引用這一項時三個但書必須一起帶：**
① 價值集中在 2008，而該段對訊號是 in-sample；
② **2022 型陰跌幫不上忙**（MDD 僅 +1.27pp、CAGR 反而 −2.17pp）；
③ HO2 失敗 → **不得宣稱擇時 alpha**，只能說是有效減碼（MDD 改善主要來自平均只持 67.4% 曝險）。
即使套用，全期回撤仍約 −62.7%，**部位大小仍是主要風控**。

---

## D8 · 每日自動化排程事件流

```mermaid
sequenceDiagram
    autonumber
    participant TPEX as TPEx / TWSE 官方端點
    participant T1 as 排程1 · 平日 1730<br/>Market_SnapshotCollector
    participant T2 as 排程2 · 平日 1800<br/>FinMind_DailyUpdate
    participant GIT as cloud_cache / main 分支
    participant WEB as Streamlit 雲端

    Note over TPEX: 目標交易日由 TPEx openapi 決定 當天 14-16 點翻日<br/>未發布最多重試 8 次 × 600 秒
    T1->>TPEX: collect 價格/PE · collect_chip 三大法人<br/>collect_margin 融資 · collect_shareholding 股數<br/>collect_monthly_revenue PIT 只追加
    TPEX-->>T1: 寫入 ~/market_cache/*_daily/
    T1->>T1: build_industry_value_ref 全量重建 約 2-4 分鐘
    T1->>T1: universe_screen_daily → pool / shortlist / c2_fullpool
    T1->>T1: universe_digest 每日摘要

    Note over T1,T2: 30 分鐘緩衝 確保籌碼/融資快照已落地

    T2->>T2: build_cache 增量建庫 + 刷新 scores<br/>本機優先讀 17:30 的快照
    T2->>GIT: deploy_scores 同步 cloud_cache<br/>fail-closed 鏡像：不在部署分支時用 git worktree 推到 main
    GIT-->>WEB: 雲端讀新快照
    Note over T2: 失敗即中止 不推壞快照上雲
```

兩個工作皆以 `wscript.exe //B //Nologo run_hidden.vbs` 隱藏執行，設定 `-StartWhenAvailable -WakeToRun`。

---

## D9 · 驗證狀態總覽（哪一段是「驗過的」）

```mermaid
flowchart TD
    subgraph OK["✅ 已通過完整預註冊 H1-H5"]
        A1["本體 A = dual100<br/>real_composite Top20% ∩ c2 Top20% @ADV>=100萬<br/>等權 · 月頻 · 固定曝險"]
        A2["OOS 夏普 1.20 · CAGR 22.79%<br/>vs 0050 0.86 / 16.52%"]
        A3["live 設定 2019窗 + institutional_gross<br/>獨立跑 H1-H4 全過"]
    end

    subgraph NO["❌ 已驗證否決"]
        N1["TOP_N = 15 濃縮<br/>H4 滑價穩健否定 已撤銷"]
        N2["P-Overlay-C 滿血 α=1<br/>CAGR 15.61% < 20% 硬線"]
        N3["overlay α 掃描 0.25/0.50/0.75<br/>HOα-4a 滑價否定"]
        N4["high52_prox 單因子策略"]
        N5["五維度修正 B1-B5 / C1 / C2 十一個 arm"]
        N6["USE_KD_FULL / USE_BBP / USE_OBV_TREND"]
    end

    subgraph FZ["🔒 有效但封存 · ⚖️ 豁免"]
        F1["C3 五面層內百分位化<br/>Gate 1 唯一過關 但走查協定無稽核產物 → 降級封存"]
        F2["⚖️ α=0.25 壓縮版曝險<br/>研究否定 + 使用者明文豁免"]
        F3["季度 8 檔版本<br/>保留為另一未驗證策略"]
    end

    subgraph WARN["⚠️ 已知未修的結構落差"]
        U1["管線 A 母體 = watchlist.txt 958 檔<br/>非逐日 ADV 全池"]
        U2["估值窗 live 2019 vs 研究 2004<br/>裁決：只揭露不修"]
        U3["籌碼源 institutional_flow 淨額<br/>vs institutional_participation<br/>裁決：只揭露不修"]
        U4["2019 定義斷裂三處<br/>value_ind 表 / RS 需 0050 快取 / regime 乘數"]
        U5["live 與研究逐月持股<br/>Jaccard 重疊中位數僅 0.640"]
        U6["零股撮合無法回測<br/>薄量股滑價假設恐低估"]
    end

    A1 --> A2
    A1 -.-> U1
    A1 -.-> U5

    classDef okc fill:#dff5e1,stroke:#2e7d32,color:#1b5e20
    classDef noc fill:#fde8e8,stroke:#c62828,color:#7f1d1d
    classDef fzc fill:#e8eaf6,stroke:#3949ab,color:#1a237e
    classDef wc fill:#fff4d6,stroke:#b8860b,color:#5c4400
    class A1,A2,A3 okc
    class N1,N2,N3,N4,N5,N6 noc
    class F1,F2,F3 fzc
    class U1,U2,U3,U4,U5,U6 wc
```

---

## 附錄 · 關鍵常數速查（附 file:line）

| 常數 | 值 | 位置 |
|---|---|---|
| `MIN_PCT_SAMPLES` | 60 | `scripts/universe_screen_daily.py:50` |
| `PE_HISTORY_START` | 2019-01-01 | 同上 :51 |
| `DATA_START_CUTOFF` | 2019-01-10 | 同上 :53 |
| `REVENUE_LAG_DAYS` | 10 | 同上 :54 |
| `VALUE_IND_MAX_NAN_PCT` | 20.0（超過即 abort） | 同上 :58 |
| `LEG_MIN_COVERAGE_PCT` | 95.0（低於即 abort） | 同上 :61 |
| `REVENUE_STALE_WARN_DAYS` | 45 | 同上 :62 |
| `--adv-floor` | 10,000,000（粗篩池） | 同上 :111 |
| `--shortlist-union-pct` | 15.0（→ 門檻 >85） | 同上 :114 |
| `--full-pool-adv-floor` | 1,000,000（對齊 H1-H5） | 同上 :122 |
| balanced `composite_weights` | .31/.08/.19/.27/.15 | `core/scoring_manager.py:53` |
| balanced `min_score` | 54 | 同上 :55 |
| `_HORIZON_WEIGHTS` | 1:.10 3:.15 5:.25 10:.25 20:.25 | 同上 :298 |
| `_RATIO_TO_POINTS` | 300.0 | 同上 :299 |
| `USE_RS_OVERLAY` | True | 同上 :17 |
| `USE_KD_FULL` / `USE_BBP` / `USE_OBV_TREND` | False | 同上 :18-20 |
| `REGIME_MULTIPLIERS` bear | fund 1.00 / val .60 / tech .30 / mom 1.50 / whale .30 | `core/regime.py:33` |
| 基本面分組權重 | 獲利 .30 / 成長 .25 / 安全 .25 / 估值 .20 | `core/fundamentals.py:30-33` |
| 基本面硬門檻 | 流動比 50 / 淨利率 -10 / cash_quality 0.5 | 同上 :62-64 |
| `OVERLAY_ALPHA` | 0.25 | `core/regime_exposure.py:79` |
| `FUSION_PCT` | 20 | `scripts/l4a_decision.py:45` |
| `TOP_N` | None（濃縮已撤銷） | 同上 :56 |
| `ORDER_ADV_CAP` | 0.03 | 同上 :43 |
| `LOT_SIZE` | 1000 | 同上 :46 |
| `BUY_COST` / `SELL_COST` | 0.001585 / 0.004585 | `scripts/l4b_execution.py:54-55` |
| 淨參與率分子 | Σ(buy−sell) 於 `date >= _cut(n)`，÷1000 → 張 | `core/data_provider.py:1052-1066` |
| 淨參與率分母 | `price_df.Trading_Volume.tail(n).sum() / 1000` | 同上 :1567-1574 |
| 自營商 | **剔除**，不進籌碼分 | 同上 :1528 |
| `flow_acceleration` | 近5日日均淨買 ÷ 近20日日均淨買；由賣轉買記 2.0 | 同上 :1544-1554 |
| `institutional_participation` | 外資+投信近10日(買+賣)股數 ÷ (2 × 市場同期總量) × 100 | 同上 :1556-1561 |
| `whale_concentration` | 投信近20日淨買股數 ÷ 流通股數 × 100 | 同上 :1590 |

---

*本文件為程式碼現況的靜態快照（2026-08-11）。若之後改動評分邏輯/篩選參數/部署層，
請重新掃描程式碼更新本文件，不要手動修改數字。*
