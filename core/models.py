from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class StockData:
    """
    統一的核心數據模型,所有來源的數據最終在此封裝。
    規則:無預設值欄位在前、有預設值欄位在後 (dataclass 限制)。

    本版新增四大維度所需欄位:
      - 獲利品質:net_income_growth (淨利年增率,供與營收年增率做一致性比對)
      - 財務健康:operating_cash_flow / free_cash_flow / capex / ocf_to_net_income
      - 估值:price_to_sales (P/S,由 PE × 淨利率推導,不額外耗用 API)
      - 動態動能:ma5_bias / ma20_bias (乖離率) / volume_spike (量能爆發倍數)
      - 資料治理:data_confidence (0-100) / missing_fields (缺漏欄位清單)
    """
    # 1. 核心必填欄位 (無預設值,必須放最前)
    symbol: str                 # 代號 (例如: "2330")
    name: str                   # 股票名稱
    current_price: float        # 當前價格
    volume: int                 # 成交量 (單位:張 = 股數/1000)

    # 2. 衍生/擴充欄位 (全部設定預設值,放後面)
    change_percent: float = 0.0 # 漲跌幅 (%)

    # --- 基本面數據屬性 ---
    pe_ratio: Optional[float] = None         # 本益比
    pb_ratio: Optional[float] = None         # 股價淨值比
    price_to_sales: Optional[float] = None   # 股價營收比 P/S (由 PE × 淨利率推導) <- 新增
    dividend_yield: float = 0.0              # 殖利率
    # --- 相對估值 (河流圖分位;個股相對自身歷史,牛熊皆適用) ---
    pe_percentile: Optional[float] = None         # 本益比歷史分位 (0-100,越低越便宜)
    pb_percentile: Optional[float] = None         # 股價淨值比歷史分位 (0-100,越低越便宜)
    dividend_yield_percentile: Optional[float] = None  # 殖利率歷史分位 (0-100,越高越便宜)
    valuation_basis: str = "絕對"                 # 估值基準:相對(有歷史分位) / 絕對(歷史不足)
    market_regime: str = ""                       # 當前大盤位階 (多頭/中性/空頭 + 位階)
    roe: float = 0.0                         # 股東權益報酬率
    net_margin: float = 0.0                  # 淨利率
    gross_margin: float = 0.0                # 毛利率
    debt_to_asset: float = 0.0               # 負債比率
    current_ratio: float = 0.0               # 流動比率
    asset_turnover: Optional[float] = None   # 總資產週轉率 (年化季營收/總資產;None=財報缺) <- v4.4
    rev_cagr: float = 0.0                    # 月營收年增率
    eps_cagr: float = 0.0                    # EPS 年增率
    net_income_growth: float = 0.0           # 淨利年增率 (YoY) <- 新增:獲利品質一致性檢查
    pe_vs_industry: float = 10.0             # 本益比 (餵入原始 PE,由 fundamentals 評分)

    # --- 財務健康 / 現金流 (單位:千元,同 FinMind 財報) ---
    operating_cash_flow: Optional[float] = None  # 營業活動現金流 (OCF) <- 新增
    free_cash_flow: Optional[float] = None       # 自由現金流 (FCF = OCF - CapEx) <- 新增
    capex: Optional[float] = None                # 資本支出 (取得不動產廠房設備,通常為負) <- 新增
    net_income: Optional[float] = None           # 稅後淨利 (千元,供 OCF/NI 現金含金量比對) <- 新增
    ocf_to_net_income: Optional[float] = None    # 營業現金流 / 淨利 (現金含金量倍數) <- 新增
    operating_income: Optional[float] = None      # 營業利益 (本業獲利,供營運槓桿判斷) <- 新增
    operating_profit_ratio: Optional[float] = None  # 營業利益 / 稅後淨利 (本業獲利占比) <- 新增
    gross_margin_trend: Optional[float] = None    # 毛利率季度趨勢 (最新季 − 前數季均,百分點;+升 −降)
    financials_asof: Optional[str] = None         # 財報資料截止日 (季報),供「動能領先財報」時間差判斷
    # --- 月營收即時動能 (每月10號更新,台股最即時成長領先指標) ---
    revenue_mom: Optional[float] = None           # 月營收月增率 (%)
    revenue_cum_yoy: Optional[float] = None        # 累計營收年增率 (YTD YoY, %)
    revenue_accel: Optional[float] = None          # 營收動能加速度 (近3月均YoY − 前3月均YoY, 百分點)
    revenue_growth_streak: int = 0                 # 連續 YoY 正成長月數
    revenue_asof: Optional[str] = None             # 最新月營收所屬年月 (YYYY-MM)

    # --- 籌碼面與技術面修正指標 ---
    volume_concentration: float = 0.0    # 成交量集中度
    institutional_buy_days: int = 0      # 投信連續買超天數
    institutional_sell_days: int = 0     # 投信連續賣超天數
    foreign_buy_days: int = 0            # 外資連續買超天數
    foreign_sell_days: int = 0           # 外資連續賣超天數
    revenue_growth: float = 0.0          # 月營收成長率
    weekly_ma20: float = 0.0             # 週線 MA20

    # --- 技術指標屬性 ---
    ma5: float = 0.0
    ma20: float = 0.0
    ma5_bias: float = 0.0                # 5 日乖離率 (%) = (price - ma5)/ma5*100 <- 新增
    ma20_bias: float = 0.0               # 20 日乖離率 (%) = (price - ma20)/ma20*100 <- 新增
    volume_spike: float = 1.0            # 量能爆發倍數 = 當日量 / 20 日均量 <- 新增
    mom_3m: float = 0.0                  # 近3個月報酬% (中期價格動能;因子歸因後動能面新核心) <- 新增
    mom_6m: float = 0.0                  # 近6個月報酬% (中期價格動能,正向因子主體) <- 新增
    # --- 相對強弱 RS (v4.4 候選):個股中期報酬 − 大盤 (0050) 同期報酬;None=無基準資料不計分 ---
    rs_3m: Optional[float] = None        # 近3月相對大盤報酬 (百分點)
    rs_6m: Optional[float] = None        # 近6月相對大盤報酬 (百分點)
    rsi: float = 0.0
    macd: float = 0.0
    macd_status: str = "neutral"             # MACD 狀態 (bullish_strong / bullish_recovery / bearish / neutral)
    macd_golden_cross: bool = False          # 是否剛出現黃金交叉
    # --- 新接入的技術訊號 (預設中性,不影響既有評分) ---
    kd_j: float = 50.0                        # KD 的 J 值 (>100 超買, <0 超賣;50 中性)
    kd_k: float = 50.0                        # KD 的 K 值 (完整 KD 訊號用;50 中性) <- v4.4
    kd_d: float = 50.0                        # KD 的 D 值 (K>D 偏多、K<D 偏空;50 中性) <- v4.4
    ma_cross_status: str = "neutral"          # MA20/60 交叉:golden_cross / death_cross / neutral
    obv_rising: Optional[bool] = None         # OBV 是否上升 (量能動能);None=無資料不計分
    obv_above_ma20: Optional[bool] = None     # OBV 是否站上自身20日均 (量能趨勢,較單日穩) <- v4.4
    volume_divergence: bool = False           # 量價背離 (價漲量縮),True 為追高警訊
    # --- 籌碼成本區 (Volume Profile):大戶成本區 / 買進區間 ---
    cost_zone_poc: Optional[float] = None      # 主要成本區中心價 (POC,成交量最密集價位)
    value_area_low: Optional[float] = None     # 價值區間下緣 VAL (支撐帶)
    value_area_high: Optional[float] = None    # 價值區間上緣 VAH (壓力帶)
    price_vs_poc_pct: Optional[float] = None    # 現價相對 POC 的% (負=在成本區下方,相對便宜)
    cost_zone_status: str = ""                 # 現價位置:下方/成本區內/上方
    cost_zone_support: Optional[float] = None   # 離現價最近的下方量能支撐
    cost_zone_resistance: Optional[float] = None  # 離現價最近的上方量能壓力
    cost_zone_confidence: Optional[float] = None  # 成本區可信度 (0-100)
    cost_zone_hvn_levels: List[float] = field(default_factory=list)  # 高量節點 (HVN)
    cost_zone_lvn_levels: List[float] = field(default_factory=list)   # 低量節點 (LVN)
    bb_status: str = ""                       # 布林帶狀態 (squeezing / expanding)
    bb_percent_b: Optional[float] = None      # 布林 %B = (收盤−下軌)/(上軌−下軌);None=無資料 <- v4.4
    bollinger_band_upper: float = 0.0
    bollinger_band_lower: float = 0.0

    # --- 籌碼數據屬性 (Whale/Flow) ---
    # 重新定義 (v3):剔除自營商雜訊、改短天期、以中小型股適用的訊號為主
    whale_concentration: float = 0.0         # 投信吸籌比 (投信近20日淨買超 ÷ 流通股數 %),中小型股籌碼集中訊號
    large_holder_activity: float = 0.0       # 主力動態:(外資+投信) 近5日淨買超 (張),剔除自營商
    foreign_flow: float = 0.0                # 外資近10日淨買超 (張)
    trust_flow: float = 0.0                  # 投信近10日淨買超 (張)
    institutional_participation: float = 0.0 # 法人成交占比 (外資+投信近10日買+賣量 ÷ 總量 %)
    flow_acceleration: float = 1.0           # 買超力道放大倍數 (近5日日均淨買 ÷ 近20日日均淨買)
    # --- 多天期法人淨參與率 (v4.2 whale 重構基底):{天期: (外資/投信)淨買超 ÷ 同期總成交量} ---
    #   signed、市值中性、幾乎不為 0 → 取代脆弱的「連續買超天數」當 whale 主體。天期 = 1/3/5/10/20 日。
    foreign_net_ratio: dict = field(default_factory=dict)  # 外資 {1,3,5,10,20} 日淨買超 ÷ 同期成交量
    trust_net_ratio: dict = field(default_factory=dict)    # 投信 {1,3,5,10,20} 日淨買超 ÷ 同期成交量
    # --- TDCC 集保股權分散 (週更;預設純參考,由 Config.USE_TDCC_CHIP 決定是否影響分數) ---
    big_holder_ratio: float = 0.0            # 千張大戶佔比 (%)
    big_holder_weekly_change: float = 0.0    # 大戶佔比週變化 (百分點;正=回補,負=調節/出貨)

    # --- 波動度 / 融資融券 / 產業分類 (漏洞二、三修正) ---
    atr: float = 0.0                         # 平均真實區間 (Average True Range,14 日)
    atr_pct: float = 0.0                     # ATR / 收盤價 (%),波動度,供類別B防守區間
    margin_balance: float = 0.0              # 融資今日餘額 (張)
    margin_change_pct: float = 0.0           # 融資餘額近10日變化率 (%);大減=散戶退場
    sector_category: str = "B"               # 產業分類:A=大型權值/成長股, B=景氣循環/籌碼波動股
    industry: str = ""                        # 產業別 (TaiwanStockInfo)
    is_financial: bool = False               # 金融股 (銀行/保險/證券):現金流/毛利等工業指標結構性 N/A

    # --- 資料治理 (缺漏欄位不讓系統崩潰,而是降低信心分數) ---
    data_confidence: float = 100.0           # 資料完整度信心 (0-100) <- 新增
    missing_fields: List[str] = field(default_factory=list)  # 缺漏欄位清單 <- 新增


@dataclass
class ScoreResult:
    """
    用來封裝個股評分決策與建議結果的資料模型。
    本版新增智慧決策導航所需的四個報表欄位。
    """
    symbol: str          # 股票代號
    name: str            # 股票名稱
    total_score: float   # 綜合決策總分
    technical_score: float
    momentum_score: float
    whale_score: float   # 雙法人籌碼得分
    summary: str         # 決策建議評語

    # --- 智慧決策導航 (advisor 產出) ---
    valuation_score: float = 0.0                      # 估值得分 (0-100) <- 新增
    rating: str = "觀望追蹤"                           # 評級:強烈推薦 / 觀望追蹤 / 謹慎避開 <- 新增
    quality_flag: str = "數據不足"                     # 獲利/財務健康狀態旗標 <- 新增
    valuation_status: str = "估值中性"                 # 估值高低判定 <- 新增
    valuation_label: str = ""                         # 成長溢價／昂貴泡泡標籤 (本益比歷史高檔時的交叉驗證結果)
    valuation_basis: str = "絕對"                      # 估值基準 (成長PEG/歷史位階/絕對)
    peg_ratio: Optional[float] = None                 # PEG 本益成長比 (advisor 由估值結果帶入)
    actionable_advice: str = ""                       # 自動產生的可執行決策建議 <- 新增
    fundamental_label: str = "資料不足"                # 基本面濃縮評語 (優異/極佳/優良/普通...) <- 新增
    trend_label: str = "整理"                          # 動態趨勢濃縮評語 (強勁/健康/過熱/弱勢...) <- 新增
    data_confidence: float = 100.0                    # 帶入資料信心,報表可標註 <- 新增

    fund_info: dict = field(default_factory=dict)     # 基本面硬指標檢查結果