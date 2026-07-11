import sys
from pathlib import Path
import logging
from datetime import datetime
from dataclasses import fields as dc_fields
try:
    from tqdm import tqdm
except ImportError:  # 未安裝 tqdm 時以無進度條的簡單迭代器代替,不影響功能
    def tqdm(iterable, **kwargs):
        return iterable
import io

# 強制調整終端機輸出編碼為 UTF-8,徹底根除 Windows cp950 錯誤
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.abspath(__file__))


def output_path(subdir, filename):
    """統一輸出路徑:<專案根>/outputs/<subdir>/<filename>,資料夾不存在自動建立。"""
    d = _os.path.join(_PROJECT_ROOT, "outputs", subdir)
    _os.makedirs(d, exist_ok=True)
    return _os.path.join(d, filename)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(output_path("logs", "system.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.scoring_manager import ScoringManager
from core.data_provider import DataProvider
from core.fundamentals import FundamentalEngine
from core.valuation import ValuationEngine
from core.advisor import InvestmentAdvisor


class Config:
    STRATEGY_MODE = "balanced"  # 可選 conservative, balanced, aggressive (預設 balanced:因子歸因最支持的權重)
    # 以下 TARGET_STOCKS / CONFIRM_SYMBOL 皆為「預設值」:
    #   直接執行 (python main.py) 會進入互動輸入,可自行輸入代號;
    #   互動時直接按 Enter 才會套用這裡的預設。也可用命令列:python main.py 2330 2454
    TARGET_STOCKS = ["3481", "2303", "2344", "6768", "2317"]
    FINMIND_TOKEN = ""            # 若留空,data_provider 會自動改讀 .env 的 FINMIND_TOKEN
    TOP_N_RESULTS = 5             # 預設顯示前 N 名

    # 【完整功能確認模式】填入單一代碼 (如 "2330") 即進入:
    #   會抓取並印出「所有核心數據」原始清單 + 完整四維度決策報告。
    #   留空字串 "" 則跑上方 TARGET_STOCKS 的多檔排行模式。
    CONFIRM_SYMBOL = "2330"

    # 【TDCC 集保股權分散 · 千張大戶】週更資料 (需本機網路,獨立於 FinMind)。
    #   False (預設) → 純參考,只顯示於確認模式,不影響分數。
    #   True          → 大戶佔比「週變化」以 ±8 有界進入籌碼分 (含背離警示)。
    USE_TDCC_CHIP = False


# ----------------------------------------------------------------------
# 核心數據分組 (供完整功能確認模式逐項印出,附中文標籤)
# ----------------------------------------------------------------------
FIELD_LABELS = {
    # 基本資料
    "symbol": "股票代號", "name": "股票名稱", "current_price": "當前價格",
    "volume": "成交量(張)", "change_percent": "漲跌幅(%)",
    "sector_category": "產業分類(A權值/B循環)",
    # 估值面
    "pe_ratio": "本益比 P/E", "pb_ratio": "股價淨值比 P/B",
    "price_to_sales": "股價營收比 P/S", "dividend_yield": "殖利率(%)",
    "pe_vs_industry": "評分用 PE",
    "pe_percentile": "本益比歷史位階(%)", "pb_percentile": "淨值比歷史位階(%)",
    "dividend_yield_percentile": "殖利率歷史位階(%)", "valuation_basis": "估值基準(相對/絕對)",
    "market_regime": "當前大盤位階",
    # 獲利 / 成長
    "roe": "股東權益報酬率 ROE(%)", "net_margin": "淨利率(%)", "gross_margin": "毛利率(%)",
    "gross_margin_trend": "毛利率季度趨勢(百分點)",
    "rev_cagr": "營收年增趨勢(近3月均%)", "revenue_growth": "最新月營收年增(%)",
    "eps_cagr": "EPS 年增率(%)", "net_income_growth": "淨利年增率(%)",
    "revenue_mom": "月營收月增率(%)", "revenue_cum_yoy": "累計營收年增(%)",
    "revenue_accel": "營收動能加速度(百分點)", "revenue_growth_streak": "連續成長月數",
    "revenue_asof": "月營收資料月份",
    # 財務健康 / 現金流
    "debt_to_asset": "負債比(%)", "current_ratio": "流動比率(%)",
    "operating_cash_flow": "營業現金流(千元)", "free_cash_flow": "自由現金流(千元)",
    "capex": "資本支出(千元)", "net_income": "稅後淨利(千元)",
    "ocf_to_net_income": "現金含金量 OCF/NI",
    "operating_income": "營業利益(千元)", "operating_profit_ratio": "本業獲利占比(營益/淨利)",
    "financials_asof": "財報資料截止日",
    # 籌碼面
    "institutional_buy_days": "投信連買(天)", "institutional_sell_days": "投信連賣(天)",
    "foreign_buy_days": "外資連買(天)", "foreign_sell_days": "外資連賣(天)",
    "large_holder_activity": "主力動態(外資+投信5日淨買超張)",
    "foreign_flow": "外資10日淨買超(張)", "trust_flow": "投信10日淨買超(張)",
    "flow_acceleration": "買超力道放大(倍)", "whale_concentration": "投信吸籌比(佔流通股%)",
    "institutional_participation": "法人成交占比(%)",
    "volume_concentration": "成交量集中度(上漲日量佔比%)",
    "big_holder_ratio": "千張大戶佔比(%)", "big_holder_weekly_change": "大戶佔比週變化(百分點)",
    "margin_balance": "融資餘額(張)", "margin_change_pct": "融資10日變化(%)",
    # 技術面
    "ma5": "5日均線", "ma20": "20日均線", "weekly_ma20": "週線MA20",
    "ma5_bias": "5日乖離率(%)", "ma20_bias": "20日乖離率(%)", "volume_spike": "量能爆發(倍)",
    "rsi": "RSI", "macd": "MACD值", "macd_status": "MACD狀態",
    "macd_golden_cross": "MACD黃金交叉", "bb_status": "布林狀態",
    "kd_j": "KD J值", "ma_cross_status": "MA20/60交叉", "obv_rising": "OBV量能上升",
    "volume_divergence": "量價背離",
    "cost_zone_poc": "大戶成本區 POC", "value_area_low": "價值區下緣(支撐)",
    "value_area_high": "價值區上緣(壓力)", "price_vs_poc_pct": "現價距成本區(%)",
    "cost_zone_status": "現價相對成本區",
    "cost_zone_support": "最近量能支撐", "cost_zone_resistance": "最近量能壓力",
    "bollinger_band_upper": "布林上軌", "bollinger_band_lower": "布林下軌",
    "atr": "ATR(14)", "atr_pct": "ATR波動度(%)",
    # 資料治理
    "data_confidence": "資料信心(%)", "missing_fields": "缺漏欄位",
}

GROUP_ORDER = [
    ("📌 基本資料", ["symbol", "name", "current_price", "volume", "change_percent", "sector_category"]),
    ("💰 估值面", ["pe_ratio", "pb_ratio", "price_to_sales", "dividend_yield", "pe_vs_industry",
                "pe_percentile", "pb_percentile", "dividend_yield_percentile",
                "valuation_basis", "market_regime"]),
    ("📈 獲利 / 成長", ["roe", "net_margin", "gross_margin", "gross_margin_trend",
                    "rev_cagr", "revenue_growth",
                    "revenue_mom", "revenue_cum_yoy", "revenue_accel", "revenue_growth_streak",
                    "revenue_asof", "eps_cagr", "net_income_growth"]),
    ("🏦 財務健康 / 現金流", ["debt_to_asset", "current_ratio", "operating_cash_flow",
                        "free_cash_flow", "capex", "net_income", "ocf_to_net_income",
                        "operating_income", "operating_profit_ratio", "financials_asof"]),
    ("🐋 籌碼面", ["institutional_buy_days", "institutional_sell_days", "foreign_buy_days",
                "foreign_sell_days", "large_holder_activity", "foreign_flow", "trust_flow",
                "flow_acceleration", "whale_concentration", "institutional_participation",
                "volume_concentration", "big_holder_ratio", "big_holder_weekly_change",
                "margin_balance", "margin_change_pct"]),
    ("📊 技術面", ["ma5", "ma20", "weekly_ma20", "ma5_bias", "ma20_bias", "volume_spike",
                "rsi", "macd", "macd_status", "macd_golden_cross", "bb_status",
                "kd_j", "ma_cross_status", "obv_rising", "volume_divergence",
                "cost_zone_poc", "value_area_low", "value_area_high",
                "price_vs_poc_pct", "cost_zone_status", "cost_zone_support", "cost_zone_resistance",
                "bollinger_band_upper", "bollinger_band_lower", "atr", "atr_pct"]),
    ("🧾 資料治理", ["data_confidence", "missing_fields"]),
]


def _fmt(v):
    if v is None:
        return "數據缺失"
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, list):
        return "、".join(str(x) for x in v) if v else "(無)"
    return str(v)


# ----------------------------------------------------------------------
# CJK 寬度感知的欄位對齊 (中文字/全形符號算 2 格,確保表格不歪斜)
# ----------------------------------------------------------------------
import unicodedata

def _disp_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(s))

def _pad(s: str, width: int, align: str = "left") -> str:
    s = str(s)
    gap = max(0, width - _disp_width(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def _wrap_cjk(text: str, width: int = 58, indent: str = "") -> str:
    """CJK 寬度感知的自動換行:超過 width 顯示寬度就換行,後續行加 indent 縮排。"""
    out_lines, cur, cur_w = [], "", 0
    for ch in str(text):
        if ch == "\n":
            out_lines.append(cur)
            cur, cur_w = "", 0
            continue
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if cur_w + w > width and cur:
            out_lines.append(cur)
            cur, cur_w = "", 0
        cur += ch
        cur_w += w
    if cur:
        out_lines.append(cur)
    return ("\n" + indent).join(out_lines)


MODE_ALIASES = {
    "c": "conservative", "conservative": "conservative", "保守": "conservative",
    "b": "balanced", "balanced": "balanced", "平衡": "balanced",
    "a": "aggressive", "aggressive": "aggressive", "積極": "aggressive",
}
# 門檻文字直接讀 ScoringManager 實際 min_score,避免與程式碼漂移 (先前寫死 65/60 已過時)。
MODE_DESC = {
    "conservative": f"保守 (重穩定趨勢與品質,門檻高 min_score {ScoringManager.MODES['conservative']['min_score']})",
    "balanced": f"平衡 (基本面+技術為排序核心,估值/動能退居確認 min_score {ScoringManager.MODES['balanced']['min_score']})",
    "aggressive": f"積極 (重籌碼與突破,門檻低 min_score {ScoringManager.MODES['aggressive']['min_score']})",
}


def normalize_mode(raw: str, default: str = "balanced") -> str:
    """把使用者輸入的模式字串正規化;無法辨識則回傳 default。"""
    if not raw:
        return default
    return MODE_ALIASES.get(str(raw).strip().lower(), default)


def build_engines(mode: str = None):
    """一次建立所有引擎;advisor 的評級門檻與當前策略模式對齊。"""
    mode = mode or Config.STRATEGY_MODE
    if mode not in ScoringManager.MODES:
        mode = "balanced"
    Config.STRATEGY_MODE = mode          # 同步當前模式,讓報表標題與門檻一致
    score_manager = ScoringManager(mode=mode)
    data_provider = DataProvider()
    fund_engine = FundamentalEngine()
    val_engine = ValuationEngine()
    min_score = ScoringManager.MODES[mode]["min_score"]
    advisor = InvestmentAdvisor(min_score=min_score,
                                mode_weights=ScoringManager.MODES[mode]["composite_weights"],
                                mode_name=mode)
    if Config.FINMIND_TOKEN:
        data_provider.login(Config.FINMIND_TOKEN)
    return score_manager, data_provider, fund_engine, val_engine, advisor


def analyze_stock(stock, fund_engine, val_engine, score_manager, advisor):
    """四維度整合:基本面 → 估值 → 技術/動能/籌碼 → 智慧決策建議。"""
    stock_dict = vars(stock)
    fund_result = fund_engine.evaluate(stock_dict)
    val_result = val_engine.evaluate(stock_dict)
    score_result = score_manager.calculate_score(stock)
    score_result.fund_info = fund_result
    score_result.raw_stock = stock
    advisor.advise(stock, fund_result, val_result, score_result)
    return fund_result, val_result, score_result


# 保留機制:若未來新增暫不列入確認清單的欄位可加入此集合 (目前無)
LEGACY_HIDDEN_FIELDS: set = set()


def print_full_data_dump(stock):
    """完整功能確認模式:印出所有核心數據原始清單 (依維度分組)。"""
    all_names = [f.name for f in dc_fields(stock) if f.name not in LEGACY_HIDDEN_FIELDS]
    print("\n" + "=" * 70)
    print(f"🔬 【完整功能確認模式】{stock.symbol} {stock.name} — 全部 {len(all_names)} 項核心數據原始清單")
    print("=" * 70)

    # 依所有將顯示的標籤,計算對齊寬度 (CJK 寬度感知,中文算 2 格)
    label_w = max((_disp_width(FIELD_LABELS.get(n, n)) for n in all_names), default=20) + 1

    # 金融保險業:這些工業指標結構性不適用,顯示「金融業不適用」而非「數據缺失」
    FIN_NA_FIELDS = {"operating_cash_flow", "free_cash_flow", "capex", "operating_income",
                     "operating_profit_ratio", "ocf_to_net_income", "gross_margin",
                     "gross_margin_trend", "price_to_sales"}
    is_fin = getattr(stock, "is_financial", False)

    def _fmt_field(k):
        v = getattr(stock, k)
        if is_fin and k in FIN_NA_FIELDS and v is None:
            return "—（金融業不適用）"
        if k == "obv_rising":
            return "資料不足" if v is None else ("是（量能上升）" if v else "否（量能轉弱）")
        if k == "volume_divergence":
            return "是（價漲量縮,追高警訊）" if v else "否"
        return _fmt(v)

    shown = set()
    for group_title, keys in GROUP_ORDER:
        print(f"\n{group_title}")
        print("-" * 70)
        for k in keys:
            if not hasattr(stock, k):
                continue
            label = FIELD_LABELS.get(k, k)
            print(f"  {_pad(label, label_w)}: {_fmt_field(k)}")
            shown.add(k)
    # 保險:若模型新增了未分組欄位,一併補印,確保「所有」數據都出現
    leftover = [n for n in all_names if n not in shown]
    if leftover:
        print("\n🔧 其他欄位")
        print("-" * 70)
        for k in leftover:
            print(f"  {_pad(FIELD_LABELS.get(k, k), label_w)}: {_fmt_field(k)}")


def print_decision_report(res):
    """印出單檔的智慧決策報告 (統一中文標籤、建議分行、CJK 對齊)。"""
    W = 68
    print("\n" + "═" * W)
    print(f"  🧭 智慧決策報告　{res.symbol} {res.name}")
    print("═" * W)
    print(f"  綜合評分：{res.total_score:<6}評級：{res.rating}")
    print(f"  分項得分：技術 {res.technical_score:.0f}｜動能 {res.momentum_score:.0f}｜"
          f"籌碼 {res.whale_score:.0f}｜估值 {res.valuation_score:.0f}")
    print("─" * W)
    print(f"  獲利財務：{res.quality_flag}")
    stock = getattr(res, "raw_stock", None)
    basis = getattr(res, "valuation_basis", None) or getattr(stock, "valuation_basis", "絕對")
    label_txt = f"｜{res.valuation_label}" if getattr(res, "valuation_label", "") else ""
    val_line = f"  估值狀態：{res.valuation_status}{label_txt}（基準：{basis}）"
    peg = getattr(res, "peg_ratio", None)
    if peg is not None:
        val_line += f"　PEG {peg}（<1 便宜｜成長調整）"
    print(val_line)
    pe_pct = getattr(stock, "pe_percentile", None)
    if pe_pct is not None:
        print(f"  　　　　　本益比位階 {pe_pct:.0f}%（近3年,越低越便宜）")
    regime = getattr(stock, "market_regime", "") or "資料不足"
    print(f"  市場位階：{regime}")
    print(f"  資料信心：{res.data_confidence}%")
    print("─" * W)
    print("  系統建議")
    main = getattr(res, "advice_main", None) or res.actionable_advice
    print("    " + _wrap_cjk(main, 58, "    "))
    for n in getattr(res, "advice_notes", []) or []:
        print("    ・" + _wrap_cjk(n, 56, "      "))
    # 交易計畫:把價量結構換算成明確的進場/停損/目標價位 (價位參考,非投資建議)
    if stock is not None:
        try:
            from core.trade_plan import build_trade_plan, format_plan_lines
            plan = build_trade_plan(stock, res)
            print("─" * W)
            print("  📐 交易計畫 (價位參考,非投資建議)")
            for ln in format_plan_lines(plan):
                print("    " + _wrap_cjk(ln, 58, "    "))
        except Exception as _e:
            logger.warning(f"交易計畫計算略過:{_e}")
    if not res.fund_info.get("is_passed", True):
        print("─" * W)
        print(f"  ⚠️ 基本面未過關：{res.fund_info.get('reasons')}")
    print("═" * W)


# ----------------------------------------------------------------------
# 模式一:完整功能確認 (單一代碼)
# ----------------------------------------------------------------------
def run_confirm_mode(symbol, engines):
    score_manager, data_provider, fund_engine, val_engine, advisor = engines
    logger.info(f"🔬 進入完整功能確認模式,分析單一標的: {symbol}")
    stock = data_provider.fetch_full_stock_data(symbol)
    if stock is None:
        print(f"❌ 無法取得 {symbol} 的數據,請確認代碼或 FinMind Token/額度。")
        return

    print_full_data_dump(stock)
    _, _, res = analyze_stock(stock, fund_engine, val_engine, score_manager, advisor)
    print_decision_report(res)


# ----------------------------------------------------------------------
# 模式二:多檔排行
# ----------------------------------------------------------------------
def run_ranking_mode(engines, symbols=None):
    score_manager, data_provider, fund_engine, val_engine, advisor = engines
    raw_stocks = data_provider.get_all_data(symbols)
    final_list = []

    print("\n開始進行四維度策略核心評估...")
    for stock in tqdm(raw_stocks, desc="深度分析中"):
        try:
            fund_result, val_result, score_result = analyze_stock(
                stock, fund_engine, val_engine, score_manager, advisor
            )
            # 第一層濾網:未過基本面硬門檻者不進入排行 (但仍已產生「謹慎避開」建議可供查閱)
            if not fund_result["is_passed"]:
                logger.warning(f"⚠️ 股票 {stock.symbol} 因基本面未過關遭排除。原因: {fund_result['reasons']}")
                continue
            final_list.append(score_result)
        except Exception as e:
            logger.error(f"分析股票 {getattr(stock, 'symbol', '未知')} 時發生異常: {e}")
            continue

    final_list.sort(key=lambda x: x.total_score, reverse=True)

    print("\n" + "=" * 92)
    regime = getattr(getattr(final_list[0], "raw_stock", None), "market_regime", "") if final_list else ""
    banner = f"🏆 【個股四維度決策總表】 (模式: {Config.STRATEGY_MODE})"
    if regime:
        banner += f"　｜　當前大盤位階:{regime}"
    print(banner)
    print("=" * 92)
    if not final_list:
        print("沒有任何股票通過基本面安全篩選門檻。")
        return []

    # 表頭 (代碼 | 綜合評分 | 基本面評價 | 動態趨勢 | 評級);買點提示因為是完整句子,另起縮排行呈現
    cols = [("代碼", 12, "left"), ("綜合評分", 8, "right"),
            ("基本面評價", 20, "left"), ("動態趨勢", 20, "left"), ("評級", 10, "left")]
    header = " │ ".join(_pad(t, w, a) for t, w, a in cols)
    print(header)
    print("─" * _disp_width(header))

    for i, res in enumerate(final_list[:Config.TOP_N_RESULTS], 1):
        code_cell = f"{i:02d}. {res.symbol} {res.name}"
        row = " │ ".join([
            _pad(code_cell, 12, "left"),
            _pad(f"{res.total_score:.1f}", 8, "right"),
            _pad(res.fundamental_label, 20, "left"),
            _pad(res.trend_label, 20, "left"),
            _pad(res.rating, 10, "left"),
        ])
        print(row)
        print(f"    └ 系統建議與買點提示:{res.actionable_advice}")
        cat = getattr(getattr(res, "raw_stock", None), "sector_category", "B")
        w = ScoringManager.MODES[Config.STRATEGY_MODE]["composite_weights"]
        mode_txt = (f"模式{Config.STRATEGY_MODE}(基本面{w['fundamental']*100:.0f}·估值{w['valuation']*100:.0f}·"
                    f"技術{w['technical']*100:.0f}·動能{w['momentum']*100:.0f}·籌碼{w['whale']*100:.0f})")
        label_txt = f"·{res.valuation_label}" if getattr(res, "valuation_label", "") else ""
        print(f"      (類別 {cat}類｜{mode_txt}｜分項 技術{res.technical_score:.0f}·動能"
              f"{res.momentum_score:.0f}·籌碼{res.whale_score:.0f}·估值{res.valuation_score:.0f}"
              f"｜{res.valuation_status}{label_txt}｜信心 {res.data_confidence:.0f}%)")
        print("─" * 92)

    return final_list


# ----------------------------------------------------------------------
# 匯出排行結果:CSV / Excel
# ----------------------------------------------------------------------
def _result_rows(final_list):
    """把 ScoreResult 清單攤平成可匯出的 dict 列 (含完整分項與建議)。"""
    rows = []
    for i, res in enumerate(final_list, 1):
        stock = getattr(res, "raw_stock", None)
        rows.append({
            "排名": i,
            "代號": res.symbol,
            "名稱": res.name,
            "綜合評分": round(res.total_score, 1),
            "評級": res.rating,
            "產業類別": getattr(stock, "sector_category", ""),
            "基本面評價": res.fundamental_label,
            "動態趨勢": res.trend_label,
            "估值狀態": res.valuation_status,
            "估值標籤": getattr(res, "valuation_label", ""),
            "技術分": round(res.technical_score, 1),
            "動能分": round(res.momentum_score, 1),
            "籌碼分": round(res.whale_score, 1),
            "估值分": round(res.valuation_score, 1),
            "資料信心%": round(res.data_confidence, 1),
            "系統建議與買點提示": res.actionable_advice,
        })
    return rows


def _open_file(path):
    """用系統預設程式開啟檔案 (跨平台);失敗僅提示,不中斷流程。"""
    try:
        if sys.platform == "win32":
            os.startfile(os.path.abspath(path))          # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", path], check=False)
        else:
            import subprocess
            subprocess.run(["xdg-open", path], check=False)
        print(f"📂 已自動開啟:{path}")
    except Exception as e:
        print(f"(檔案已存檔,但自動開啟失敗:{e})")


def export_ranking(final_list, fmt="csv", path=None, auto_open=True):
    """
    把排行結果一鍵匯出成 CSV 或 Excel,並自動以系統預設程式開啟。
      fmt: 'csv' 或 'xlsx';path 省略時自動以時間戳命名;auto_open=False 可關閉自動開啟。
    回傳實際寫出的檔案路徑;失敗回傳 None。CSV 用 utf-8-sig 讓 Excel 開中文不亂碼。
    """
    if not final_list:
        print("⚠️ 無排行結果可匯出。")
        return None
    try:
        import pandas as pd
    except ImportError:
        print("⚠️ 需要 pandas 才能匯出。")
        return None

    df = pd.DataFrame(_result_rows(final_list))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = (fmt or "csv").lower()

    if fmt in ("xlsx", "excel", "xls"):
        path = path or output_path("excel", f"排行結果_{Config.STRATEGY_MODE}_{ts}.xlsx")
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="排行結果")
                ws = writer.sheets["排行結果"]
                for col_idx, col in enumerate(df.columns, 1):
                    max_len = max([len(str(col))] + [len(str(v)) for v in df[col]])
                    ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = \
                        min(60, max_len + 4)
            print(f"✅ 已匯出 Excel:{path}")
            if auto_open:
                _open_file(path)
            return path
        except Exception as e:
            print(f"⚠️ Excel 匯出失敗 ({e}),改存 CSV。")
            fmt = "csv"

    # CSV (預設 / fallback)
    path = path if (path and path.lower().endswith(".csv")) \
        else output_path("excel", f"排行結果_{Config.STRATEGY_MODE}_{ts}.csv")
    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"✅ 已匯出 CSV:{path}")
        if auto_open:
            _open_file(path)
        return path
    except Exception as e:
        print(f"⚠️ CSV 匯出失敗:{e}")
        return None


def parse_symbols(raw: str):
    """把使用者輸入解析成乾淨的代號清單:支援逗號、空白、全形逗號分隔。"""
    if not raw:
        return []
    for sep in ("，", ",", "、", ";", "；"):
        raw = raw.replace(sep, " ")
    out = []
    for tok in raw.split():
        tok = tok.strip().upper()          # 保留字母 (ETF/KY股),去空白
        if tok and tok not in out:
            out.append(tok)
    return out


def dispatch(symbols, engines):
    """依代號數量決定模式:1 檔 → 完整確認;多檔 → 排行。排行會回傳結果清單供匯出。"""
    if len(symbols) == 1:
        run_confirm_mode(symbols[0], engines)
        return None
    logger.info(f"多檔排行模式,共 {len(symbols)} 檔: {', '.join(symbols)}")
    return run_ranking_mode(engines, symbols)


def _maybe_export_interactive(final_list):
    """排行後詢問是否匯出。"""
    if not final_list:
        return
    ans = input("要匯出這份排行嗎? (csv / xlsx / n) ▶ ").strip().lower()
    if ans in ("csv", "c"):
        export_ranking(final_list, "csv")
    elif ans in ("xlsx", "excel", "x", "e"):
        export_ranking(final_list, "xlsx")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="台股四維度決策系統", add_help=True)
    parser.add_argument("symbols", nargs="*", help="股票代號 (多檔用空白分隔);省略則進入互動模式")
    parser.add_argument("-m", "--mode", default=None,
                        help="策略模式:conservative/balanced/aggressive (或 c/b/a)")
    parser.add_argument("-e", "--export", default=None, choices=["csv", "xlsx"],
                        help="排行結果匯出格式 (僅多檔排行有效)")
    parser.add_argument("--no-open", action="store_true",
                        help="匯出後不要自動開啟檔案")
    parser.add_argument("--refresh", action="store_true",
                        help="強制刷新本機快取 (重抓最新資料;預設會自動用/補快取,不必每次加)")
    args, _ = parser.parse_known_args()

    # 快取:個股分析預設也走讀寫穿透快取 (查過就落地、之後重用)。--refresh 強制重抓刷新。
    if args.refresh:
        try:
            from core import data_cache
            data_cache.FORCE_REFRESH = True
            logger.info("已啟用快取強制刷新 (--refresh):本次查詢會重抓最新資料。")
        except Exception:
            pass

    mode = normalize_mode(args.mode, Config.STRATEGY_MODE)
    logger.info(f"🚀 啟動個股完整分析決策系統 - 模式: {mode} ({MODE_DESC[mode]})")
    logger.info("四維度:基本面 · 估值 · 動能 · 智慧決策(含產業分流雙權重)\n")

    try:
        engines = build_engines(mode)
    except Exception as e:
        logger.error(f"初始化模組時發生錯誤: {e}")
        return

    # 模式一:命令列參數 → 一次性分析後結束
    #   例:python main.py 2330
    #       python main.py 2330 2454 2317 --mode balanced --export xlsx
    cli_syms = parse_symbols(" ".join(args.symbols)) if args.symbols else []
    if cli_syms:
        result = dispatch(cli_syms, engines)
        if args.export and result:
            export_ranking(result, args.export, auto_open=not args.no_open)
        return

    # 模式二:互動輸入 (可連續查詢;可隨時切換模式;排行後可匯出)
    print("\n" + "=" * 64)
    print("📈 台股四維度決策系統 — 互動模式")
    print(f"   目前策略模式:{mode} ({MODE_DESC[mode]})")
    print("   · 單一代號 (如 2330)      → 完整功能確認模式")
    print("   · 多個代號 (2330 2454 …)  → 多檔排行模式 (空白或逗號分隔)")
    print("   · 輸入 mode                → 切換策略模式 (保守/平衡/積極)")
    print("   · 直接 Enter              → 使用預設清單")
    print("   · 輸入 q                   → 離開")
    print("=" * 64)

    while True:
        try:
            raw = input(f"\n[{Config.STRATEGY_MODE}] 請輸入代號 ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已離開。")
            break

        if raw.lower() in ("q", "quit", "exit"):
            print("已離開。")
            break

        # 切換策略模式
        if raw.lower() in ("mode", "m", "模式"):
            print("  可選:1) conservative 保守  2) balanced 平衡  3) aggressive 積極")
            sel = input("  請輸入模式 (名稱或 c/b/a) ▶ ").strip()
            new_mode = normalize_mode(sel, Config.STRATEGY_MODE)
            engines = build_engines(new_mode)
            print(f"  ✅ 已切換為:{new_mode} ({MODE_DESC[new_mode]})")
            continue

        if not raw:
            if Config.CONFIRM_SYMBOL:
                dispatch([Config.CONFIRM_SYMBOL.strip()], engines)
            else:
                result = run_ranking_mode(engines, Config.TARGET_STOCKS)
                _maybe_export_interactive(result)
        else:
            syms = parse_symbols(raw)
            if not syms:
                print("⚠️ 未讀到有效代號,請重新輸入。")
                continue
            result = dispatch(syms, engines)
            _maybe_export_interactive(result)

        print("\n(可繼續輸入下一組代號 / mode 切換模式 / q 離開)")


if __name__ == "__main__":
    main()
