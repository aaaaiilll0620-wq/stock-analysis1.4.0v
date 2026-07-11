"""
產業分類分流 (Sector Tagging) —— 漏洞三修正
================================================================================
用同一套權重衡量「大型權值成長股 (台積電)」與「景氣循環/籌碼波動股 (華邦電)」會失真。
本模組把每檔股票分流成兩類,交由 ScoringManager / InvestmentAdvisor 套用不同權重:

  類別 A【大型權值 / 成長股】:財報 (長期基本面) 50% · 技術面 30% · 短線籌碼 20%
  類別 B【景氣循環 / 籌碼波動股】:技術面 (ATR 波動調整) 40% · 大戶/散戶籌碼 40% · 落後財報 20%

分類優先序:
  1. 手動覆寫 (MANUAL_OVERRIDE) —— 最高優先,處理已知特例。
  2. 資料啟發式 —— 外資高持股 + 低波動 → A;否則 → B。
     (產業別無法區分同屬半導體的台積電 vs 華邦電,故改以「籌碼結構 + 波動度」判斷。)
  3. 預設 B (景氣循環/籌碼波動),對未知標的採較重視技術與籌碼的保守處理。
"""

from __future__ import annotations
from typing import Optional

CATEGORY_A = "A"   # 大型權值 / 成長股
CATEGORY_B = "B"   # 景氣循環 / 籌碼波動股

# ------------------------------------------------------------------------------
# 1) 手動覆寫:{stock_id: 'A' | 'B'}。實務上最可靠,可持續補充。
#    分類原則:
#      A = 財報/長期基本面主導股價 (成長/權值/穩定金融電信)。
#      B = 股價由「景氣循環 + 籌碼」主導、財報落後 (記憶體/面板/塑化/鋼鐵/航運/被動)。
#    注意:「大型」不等於 A。台塑四寶、中鋼、航運雖是大型權值,但屬景氣循環、
#          財報落後於景氣,套用 B 的「技術40/籌碼40/財報20」權重才合理。
# ------------------------------------------------------------------------------
MANUAL_OVERRIDE = {
    # === 類別 A:大型權值 / 成長股 (財報主導) ===
    # -- 半導體 / IC 設計成長 --
    "2330": CATEGORY_A,  # 台積電
    "2454": CATEGORY_A,  # 聯發科
    "3034": CATEGORY_A,  # 聯詠
    "2379": CATEGORY_A,  # 瑞昱
    "3443": CATEGORY_A,  # 創意 (GUC)
    "3661": CATEGORY_A,  # 世芯-KY (Alchip)
    # -- 電子權值 / 品牌組裝 --
    "2317": CATEGORY_A,  # 鴻海
    "2308": CATEGORY_A,  # 台達電
    "2382": CATEGORY_A,  # 廣達
    "2357": CATEGORY_A,  # 華碩
    "2301": CATEGORY_A,  # 光寶科
    "4938": CATEGORY_A,  # 和碩
    "3231": CATEGORY_A,  # 緯創
    # -- 金融 (官股) --
    "2886": CATEGORY_A,  # 兆豐金 (官股)
    "2892": CATEGORY_A,  # 第一金 (官股)
    "5880": CATEGORY_A,  # 合庫金 (官股)
    "2880": CATEGORY_A,  # 華南金 (官股)
    "2801": CATEGORY_A,  # 彰銀 (官股色彩)
    # -- 金融 (民營大型) --
    "2881": CATEGORY_A,  # 富邦金
    "2882": CATEGORY_A,  # 國泰金
    "2891": CATEGORY_A,  # 中信金
    "2884": CATEGORY_A,  # 玉山金
    "2885": CATEGORY_A,  # 元大金
    "2883": CATEGORY_A,  # 開發金
    "2890": CATEGORY_A,  # 永豐金
    # -- 電信 / 防禦 --
    "2412": CATEGORY_A,  # 中華電
    "3045": CATEGORY_A,  # 台灣大
    "4904": CATEGORY_A,  # 遠傳
    "1216": CATEGORY_A,  # 統一 (食品內需)

    # === 類別 B:景氣循環 / 籌碼波動股 (技術 + 籌碼主導) ===
    # -- 記憶體 / DRAM (主力洗籌碼強) --
    "2344": CATEGORY_B,  # 華邦電
    "2408": CATEGORY_B,  # 南亞科
    "3260": CATEGORY_B,  # 威剛
    "4967": CATEGORY_B,  # 十銓
    # -- 晶圓代工二線 / 循環 --
    "6770": CATEGORY_B,  # 力積電
    # 註:聯電(2303)、國巨(2327) 為市值大的指數權值股,改由市值判為 A,故不列入覆寫。
    # -- 面板 / 光電 --
    "2409": CATEGORY_B,  # 友達
    "3481": CATEGORY_B,  # 群創
    "6116": CATEGORY_B,  # 彩晶
    # -- 塑化 / 石化 (景氣循環,財報落後油價;如認為屬權值可自行移除) --
    "6505": CATEGORY_B,  # 台塑化
    # -- 航運 / 航空 (高波動循環) --
    "2603": CATEGORY_B,  # 長榮
    "2609": CATEGORY_B,  # 陽明
    "2615": CATEGORY_B,  # 萬海
    "2618": CATEGORY_B,  # 長榮航
    "2610": CATEGORY_B,  # 華航
}

# ------------------------------------------------------------------------------
# 2) 啟發式門檻 (可調)
# ------------------------------------------------------------------------------
FOREIGN_RATIO_A = 35.0     # 外資持股比率 >= 35% 傾向大型權值股
LARGE_CAP_A = 1.0e11       # 市值 >= 1000 億 → 大型權值股 (A)
MID_CAP_MIN = 3.0e10       # 市值 < 300 億視為中小型 (B);300~1000 億依產業/波動再判
ATR_PCT_A_MAX = 4.0        # 日波動 (ATR/價) < 4% 傾向穩定大型股
ATR_PCT_B_MIN = 6.0        # 日波動 >= 6% 明顯屬高波動籌碼股

# 產業別傾向 (以「包含關鍵字」比對 TaiwanStockInfo 的 industry_category)
#   注意:半導體同時有台積電(A)與華邦電(B),故「半導體」不列入任一側,交由外資持股+波動度判斷。
INDUSTRY_A_KEYWORDS = ("金融", "保險", "銀行", "電信", "通信網路", "食品", "電腦及週邊")
INDUSTRY_B_KEYWORDS = ("鋼鐵", "水泥", "塑膠", "橡膠", "造紙", "紡織", "航運", "玻璃",
                       "光電", "面板", "營建", "化學", "油電", "生技", "觀光")


class SectorClassifier:
    @classmethod
    def classify(cls, stock_id: str, industry: Optional[str] = None,
                 foreign_ratio: Optional[float] = None,
                 atr_pct: Optional[float] = None,
                 market_cap: Optional[float] = None) -> str:
        """
        回傳 'A'(大型權值/成長) 或 'B'(中小型/景氣循環/籌碼波動)。
        優先序:手動覆寫 > 金融保險硬規則(A) > 市值主判 > 外資持股/波動/產業別加權 > 預設 B。
        """
        # 1) 手動覆寫優先
        sid = str(stock_id).strip()
        if sid in MANUAL_OVERRIDE:
            return MANUAL_OVERRIDE[sid]

        # 2) 金融保險一律 A (獲利由利差/資產品質主導)
        if industry and any(k in industry for k in ("金融", "保險", "銀行", "證券")):
            return CATEGORY_A

        # 3) 市值主判 (權值股 = 市值權重大)。市值 = 股價 × 流通股數。
        if market_cap and market_cap > 0:
            if market_cap >= LARGE_CAP_A:
                return CATEGORY_A                      # 千億以上一律大型權值 (含大型循環股)
            if market_cap < MID_CAP_MIN:
                return CATEGORY_B                      # 300 億以下視為中小型
            # 中型 (300~1000 億):明確景氣循環或高波動 → B,否則 A
            if industry and any(k in industry for k in INDUSTRY_B_KEYWORDS):
                return CATEGORY_B
            if atr_pct is not None and atr_pct >= ATR_PCT_B_MIN:
                return CATEGORY_B
            return CATEGORY_A

        # 4) 無市值資料時的後備:外資持股 + 波動度 + 產業別加權
        score_a = 0
        fr, ap = foreign_ratio, atr_pct
        if fr is not None:
            score_a += 2 if fr >= FOREIGN_RATIO_A else (1 if fr >= 20.0 else 0)
        if ap is not None:
            if ap < 3.0:
                score_a += 2
            elif ap < ATR_PCT_A_MAX:
                score_a += 1
            elif ap >= ATR_PCT_B_MIN:
                score_a -= 2
        if industry:
            if any(k in industry for k in INDUSTRY_A_KEYWORDS):
                score_a += 1
            elif any(k in industry for k in INDUSTRY_B_KEYWORDS):
                score_a -= 2
        return CATEGORY_A if score_a >= 2 else CATEGORY_B

    @staticmethod
    def label(category: str) -> str:
        return "大型權值/成長股" if category == CATEGORY_A else "景氣循環/籌碼波動股"
