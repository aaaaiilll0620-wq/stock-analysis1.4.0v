"""
台股四維度決策系統 — 網頁介面 (Streamlit)
================================================================================
把原本的命令列工具變成「打開瀏覽器就能點」的網頁:輸入代號、選模式,
看到四維度評分、評級、買點提示,每個模式與評級旁都有白話說明 (tooltip)。

執行:
    pip install streamlit
    streamlit run app.py
瀏覽器會自動開 http://localhost:8501。

FinMind token:
  · 本機自用:在專案根目錄 .env 放 FINMIND_TOKEN 即可 (即時分頁沿用)。
  · 公開站 (多使用者):每個訪客在側欄貼『自己的』token,即時分頁用各自的 token 打 API、
    額度算訪客的、彼此隔離 (見下方 _loader_for / _api_lock);訪客不貼 token 也能用免 API 的
    『綜合分選股』分頁。伺服器端『不要』放你的私人 token,以免被訪客共用。

說明:本工具為研究/篩選輔助,不構成投資建議。評級是對『當前狀態』的分類,
      不是「立刻買進」指令 —— 進場價位請看每檔的『買點提示』。
================================================================================
"""
import os
import re
import sys
import time
from html import escape
from types import SimpleNamespace

import pandas as pd
import altair as alt
import streamlit as st

# 專案根目錄加入 path,直接重用既有引擎 (不重寫核心邏輯)
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from main import build_engines, analyze_stock          # 重用:引擎組裝 + 四維度分析
from core.data_provider import DataProvider
from core.scoring_manager import ScoringManager
from core import data_cache
from core import score_store                            # 綜合分快取:整個名單的跨股排名選股
from core import industry_flow                           # 法人資金流向產業 (想法2 B版,0 API)
from core.trade_plan import build_trade_plan, format_plan_lines   # 交易計畫 (與 main.py 同一套)

# ------------------------------------------------------------------ 實戰演練真實成本 (元大證券零股 6 折)
# memory: user-trading-constraints — 學生小資金、零股、元大 6 折。賣出 0.3855% 與 20 日期望
# +1.5% 同數量級,毛額記帳會系統性高估演練成績、污染 8/14 三方對帳 (工單 WP1)。
_FEE_BROKER_PCT = 0.0855 / 100.0   # 券商手續費 6 折 (原 0.1425% × 0.6);買賣皆適用,有 NT$1 地板
_FEE_TAX_PCT = 0.30 / 100.0        # 證券交易稅 (僅賣出課徵,無最低額)
_FEE_BUY_PCT = _FEE_BROKER_PCT                 # 買進總費率 0.0855%
_FEE_SELL_PCT = _FEE_BROKER_PCT + _FEE_TAX_PCT # 賣出總費率 0.3855% (含證交稅)
_FEE_MIN_TWD = 1.0                 # 元大單筆最低手續費地板 (小資金/零股專屬真實成本,只有 live 量得到)

# ------------------------------------------------------------------ 多使用者 token 隔離 (公開站 B 模式)
# 背景:DataProvider 是「類別層級單例」(_api / _logged_in 都在 class 上),而 Streamlit 一個程序服務
#       所有訪客。若直接對全域 _api 登入,並發訪客會互相蓋掉 token。做法:每個 token 建一個獨立、
#       已包本機快取的 loader;分析時在鎖內把 DataProvider._api 暫時換成該 loader、跑完還原。
#       因為 fetch_full_stock_data 開頭的 _ensure_login() 在 _logged_in=True 時直接 return,
#       換入時把 _logged_in 設 True → 絕不會 fallback 去讀伺服器 .env 的「你的」token。
import threading

_api_lock = threading.Lock()        # 序列化「換 loader → 抓資料 → 還原」臨界區 (跨並發訪客)
_loaders: dict = {}                 # token -> 已包快取的獨立 loader (程序內記憶體;空 token = 匿名)
_loaders_lock = threading.Lock()


def _loader_for(token: str):
    """為某個 FinMind token 取/建一個獨立、已包本機快取的 loader。空 token = 匿名 (額度低)。"""
    with _loaders_lock:
        if token not in _loaders:
            from FinMind.data import DataLoader
            dl = DataLoader()
            if token:
                try:
                    dl.login_by_token(api_token=token)
                except Exception:
                    pass                      # 無效 token → 退化為匿名,不讓整站崩
            _loaders[token] = data_cache.install(dl)   # 仍共用本機 Parquet 快取 (公開資料,共用有益)
        return _loaders[token]

st.set_page_config(page_title="台股四維度決策系統", page_icon="📊", layout="wide")

# ------------------------------------------------------------------ 說明文案 (= 使用指南的核心)
MODE_HELP = {
    "conservative": "保守｜重基本面品質與估值、門檻高。選出的少但扎實,適合長線/存股 (數季以上)。",
    "balanced": "平衡｜(推薦預設) 以基本面+技術為排序核心,動能/估值退居確認。適合中線波段/新手。",
    "aggressive": "積極｜重動能與籌碼點火、門檻低,抓正在噴的主流股。適合短線、且會主動停損的人。",
}
MODE_LABELS = {"conservative": "保守 (長線/存股)", "balanced": "平衡 (中線/新手·推薦)",
               "aggressive": "積極 (短線)"}

RATING_STYLE = {
    "強勢買進": ("#1B7A34", "#C6EFCE", "順勢動能軌:正在領漲的主流股 (多頭排列+動能強+法人吸籌),特赦估值。"),
    "強烈推薦": ("#375623", "#E2EFDA", "價值/品質軌:便宜或合理的好公司,基本面扎實、沒過熱。"),
    "觀望追蹤": ("#9C6500", "#FFF2CC", "訊號不足或有疑慮,先追蹤、不急著進場。"),
    "謹慎避開": ("#808080", "#F2F2F2", "基本面或技術面不佳,避開。"),
}


def rating_badge(rating: str) -> str:
    """評級徽章。**沒有評級就不要畫徽章** —— 全市場掃描的 Top-10 是粗篩層、本來就沒有四維評級,
    以前傳空字串進來會畫出一個空的淺灰方塊(#eee),在淺色主題下貼近白底看不出來,
    深色主題下就變成一顆突兀的白格子。"""
    rating = str(rating or "").strip()
    if not rating:
        return ""
    fg, bg, _ = RATING_STYLE.get(rating, ("#333", "#eee", ""))
    return (f"<span style='background:{bg};color:{fg};padding:4px 12px;border-radius:6px;"
            f"font-weight:700;font-size:1.05rem'>{rating}</span>")


# 去除圖示/emoji (保留 —、…、（）、%、「」等標點)
_ICON = re.compile(
    "[\U0001F000-\U0001FAFF"    # emoji / pictographs
    "\U00002600-\U000027BF"     # misc symbols + dingbats
    "⬀-⯿←-⇿"  # 符號與箭頭
    "ℹ️⃣]", flags=re.UNICODE)


def format_advice(text: str):
    """把系統建議切成多行 (主文 + 各條附註各自成行)、去圖示。回傳行字串清單。
    只在『(📈/💰/⚠️/ℹ️…』這種頂層附註前斷行,避免破壞內文的 (追高)、(-2%) 等內層括號。"""
    if not text:
        return []
    segs = re.split(r"[\(（](?=\s*[📈💰⚠️ℹ️🩺🔧🚀🐋🏢])", text)
    lines = []
    for i, s in enumerate(segs):
        s = s.strip()
        if i > 0 and (s.endswith(")") or s.endswith("）")):
            s = s[:-1].rstrip()               # 去掉這條附註最外層的收尾括號
        s = re.sub(r"\s{2,}", " ", _ICON.sub("", s)).strip()
        if s:
            lines.append(s)
    return lines


# ------------------------------------------------------------------ Top-10 推薦:理由 + 交易計畫 helper
_DIM_COLS = [("基本面", "fundamental"), ("估值", "valuation"), ("技術", "technical"),
             ("動能", "momentum"), ("籌碼", "whale")]


def _reason_line_screen(row) -> str:
    """綜合分選股的白話理由:五維最高 2 維 + 估值狀態 (規則產生,不呼叫 LLM)。"""
    dims = [(lab, float(row[key])) for lab, key in _DIM_COLS
            if key in row and pd.notna(row.get(key))]
    dims.sort(key=lambda x: x[1], reverse=True)
    top2 = "、".join(f"{lab}{v:.0f}" for lab, v in dims[:2])
    parts = [f"{top2} 主導"] if top2 else []
    vs = str(row.get("valuation_status", "") or "").strip()
    if vs:
        parts.append(f"估值{vs}")
    return " · ".join(parts)


def _nan_none(v):
    """parquet 讀回的缺值是 NaN;build_trade_plan 的 `x or default` 會把 NaN 當真值 →
    target1 之類顯示成 nan。統一把 NaN 還原成 None (與 main.py 的 StockData 同語義)。"""
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


# --- 法人淨買確認 (推薦閘門):whale 維是市值中性的淨參與率,薄量股 (如 1256) 會失真成高分,
#     不代表法人真的在買。用『原始』的法人占比 + 連買天數 + 淨流向做確認,擋掉「法人沒在買」的檔。
#     閾值集中在此供調整;缺欄 (舊 FinMind 快取無這些欄) → 無法判斷 → 不擋 (保守放行)。
_INST_MIN_PARTICIPATION = 30.0     # 法人近10日成交占比下限 (%):低於此=法人根本沒在這檔交易
_INST_MIN_STREAK = 3               # 外資或投信任一連買天數達此 → 視為持續吸籌
_INST_STRONG_PARTICIPATION = 50.0  # 法人占比達此 → 法人主導成交,視同確認 (免連買門檻)


def _inst_has_field(row) -> bool:
    return pd.notna(row.get("inst_participation"))


def _inst_buying(row) -> bool:
    """法人是否『真的在買』:占比夠 (法人有在交易) 且有淨買持續性 (連買達標,或土洋同步淨買)。
    缺欄無法判斷 → True (不擋,由完整名單自行判讀)。"""
    if not _inst_has_field(row):
        return True
    part = float(row.get("inst_participation") or 0.0)
    fd = float(row.get("foreign_buy_days") or 0.0)
    td = float(row.get("trust_buy_days") or 0.0)
    if part < _INST_MIN_PARTICIPATION:
        return False                                   # 法人幾乎不碰 → 非推薦標的
    # 需『持續吸籌』(外資或投信連買達標) 或『法人主導成交』(占比很高);
    # 僅『今日淨買為正』過寬 (薄量股 +1 張也算,如新紡外資僅+166張投信+89張) → 已剔除。
    return (fd >= _INST_MIN_STREAK) or (td >= _INST_MIN_STREAK) or (part >= _INST_STRONG_PARTICIPATION)


def _inst_note(row) -> str:
    """法人動向白話 (供推薦理由行);缺欄回空字串。"""
    if not _inst_has_field(row):
        return ""
    part = float(row.get("inst_participation") or 0.0)
    ff = float(row.get("foreign_flow") or 0.0)
    tf = float(row.get("trust_flow") or 0.0)
    who = []
    if ff > 0:
        who.append("外資")
    if tf > 0:
        who.append("投信")
    lead = ("＋".join(who) + "淨買") if who else "法人未淨買"
    return f"法人{lead}·占比{part:.0f}%"


def _trade_plan_lines_from_row(row) -> list:
    """把 scores 快取一列的價量結構欄位包成 stock-like，套用 main.py 同一套 build_trade_plan。
    欄位缺 (舊快取未含 / 個股算不出量價結構) → NaN 還原 None → build_trade_plan 自動降級。"""
    ns = SimpleNamespace(**{k: _nan_none(row.get(v)) for k, v in (
        ("current_price", "price"), ("atr", "atr"),
        ("value_area_low", "value_area_low"), ("value_area_high", "value_area_high"),
        ("cost_zone_poc", "cost_zone_poc"), ("cost_zone_support", "cost_zone_support"),
        ("cost_zone_resistance", "cost_zone_resistance"), ("ma20", "ma20"))})
    plan = build_trade_plan(ns, SimpleNamespace(rating=row.get("rating", "")))
    return format_plan_lines(plan)


def _render_reco_card(rank: int, code: str, name: str, rating: str,
                      headline_extra: str, reason: str, plan_lines: list):
    """統一的 Top-10 推薦卡片 (兩個分頁共用):標題列 + 理由行 + 交易計畫多行。"""
    _badge = rating_badge(rating)
    _head = f"**{rank}. {escape(str(code))} {escape(str(name))}**"
    # 沒有評級時連分隔的全角空白一起省掉,不然標題後面會留一段莫名的空白
    st.markdown("　".join(x for x in (_head, _badge, headline_extra) if x),
                unsafe_allow_html=True)
    if reason:
        st.markdown(f"<div style='color:inherit;opacity:.82;margin:-2px 0 3px'>{escape(reason)}</div>",
                    unsafe_allow_html=True)
    for ln in plan_lines:
        st.markdown(f"<div style='color:inherit;opacity:.9;font-size:0.9rem;margin:1px 0 1px 8px'>· {escape(ln)}</div>",
                    unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def get_engines(mode: str):
    return build_engines(mode)


def analyze(symbol: str, mode: str, refresh: bool, token: str = ""):
    """
    回傳單檔分析結果 dict;None 表示抓不到資料。refresh=True 一律繞過 st.cache_data、
    真正重打 API——若沿用同一顆 cache,勾了『刷新最新資料』重複點兩次分析,
    第二次的 (symbol, mode, True, token) 跟第一次同鍵,還是會命中快取、不會真的再抓一次。
    """
    if refresh:
        data_cache.FORCE_REFRESH = True
        return _do_analyze(symbol, mode, token)
    return _analyze_cached(symbol, mode, token)


@st.cache_data(show_spinner=False, ttl=3600)
def _analyze_cached(symbol: str, mode: str, token: str = ""):
    """
    refresh=False 的快取路徑。token 進 cache key → 不同訪客各自快取、各用自己的 FinMind 額度。
    ttl=3600:雲端 st.cache_data 是跨所有訪客共用的伺服器端快取、預設無過期時間,
    沒有 ttl 會導致某訪客的即時分析結果被無限期快取、之後所有人(含本機以外的雲端訪客)
    都看到那個舊價格/舊分數,直到 app 容器重啟——與本機新啟動的開發伺服器現抓現算對不起來。
    """
    data_cache.FORCE_REFRESH = False
    return _do_analyze(symbol, mode, token)


def _do_analyze(symbol: str, mode: str, token: str):
    """實際抓資料 + 跑四維度評分,不快取 (快取與否由呼叫端決定)。
    在 _api_lock 內把 DataProvider._api 換成該 token 的獨立 loader,跑完還原 (並發安全)。"""
    sm, dp, fe, ve, adv = get_engines(mode)
    loader = _loader_for(token)
    with _api_lock:
        _saved_api, _saved_logged = DataProvider._api, DataProvider._logged_in
        DataProvider._api, DataProvider._logged_in = loader, True
        try:
            stock = dp.fetch_full_stock_data(symbol)
        finally:
            DataProvider._api, DataProvider._logged_in = _saved_api, _saved_logged
    if stock is None:
        return None
    fund_result, val_result, score = analyze_stock(stock, fe, ve, sm, adv)
    # 交易計畫:與 main.py CLI 同一套 build_trade_plan(stock, score) → 進場區間/停損/目標。
    # stock 已含 atr / value_area_* / cost_zone_* / ma20;算不出時降級為一句『資料不足』。
    try:
        plan_lines = format_plan_lines(build_trade_plan(stock, score))
    except Exception:
        plan_lines = []
    return {
        "symbol": stock.symbol, "name": stock.name,
        "price": stock.current_price, "rating": score.rating,
        "total": score.total_score,
        "plan_lines": plan_lines,
        "dims": {"基本面": float(fund_result.get("total_score", 0.0)),
                 "估值": float(score.valuation_score),
                 "技術": float(score.technical_score),
                 "動能": float(score.momentum_score),
                 "籌碼": float(score.whale_score)},
        "fundamental_label": getattr(score, "fundamental_label", ""),
        "trend_label": getattr(score, "trend_label", ""),
        "valuation_status": getattr(score, "valuation_status", ""),
        "quality_flag": getattr(score, "quality_flag", ""),
        "advice": getattr(score, "actionable_advice", "") or getattr(score, "advice_main", ""),
        "confidence": getattr(score, "data_confidence", 100.0),
        "sector": getattr(stock, "sector_category", ""),
    }


@st.cache_data(show_spinner=False)
def get_universe_info(mode: str):
    """scores 快取概況 (檔數/基準日/權重版本);None = 尚未建該模式的 scores。"""
    return score_store.universe_info(mode)


@st.cache_data(show_spinner=False)
def screen_universe(mode: str, min_composite: int, ratings: tuple, min_conf: int, top: int):
    """讀 scores 快取做跨股綜合分排名 (0 API)。ratings 以 tuple 傳入以利 cache 命中。"""
    df = score_store.screen_by_composite(
        mode=mode,
        min_composite=float(min_composite),
        ratings=list(ratings) or None,
        min_confidence=float(min_conf) if min_conf > 0 else None,
        top=int(top),
    )
    return df


@st.cache_data(show_spinner=False)
def get_as_of_dates(mode: str) -> list:
    """該模式 scores 快取內所有出現過的 as_of 日期 (由舊到新),供『日期回顧』選單。"""
    return score_store.as_of_dates(mode)


@st.cache_data(show_spinner=False)
def get_score_history(stock_id: str, mode: str, limit: int = 10):
    """單檔近 N 日綜合分＋五維走勢 (讀 scores 快取,0 API);不在每日名單 → 空表。"""
    return score_store.score_history(stock_id, mode=mode, limit=limit)


@st.cache_data(show_spinner="載入產業資金流向…")
def get_industry_flow(level: str):
    """各產業每日法人淨流入 (億元) 長格式 (讀 snapshot;本機無則即時算)。"""
    return industry_flow.load_flow(level)


@st.cache_data(show_spinner=False)
def get_industry_members(level: str, industry: str, date, start=None, end=None):
    """某產業的成分股法人淨流入 (下鑽用;date=None 則看 [start, end] 區間累計)。"""
    return industry_flow.load_members(level, industry, date=date, start=start, end=end)


@st.cache_data(show_spinner=False)
def get_members_range():
    """下鑽成分股資料實際涵蓋的日期範圍 (可能比主圖短) → (min, max)。"""
    return industry_flow.members_range()


@st.cache_data(show_spinner=False)
def screen_universe_at(as_of: str, mode: str, min_composite: int, ratings: tuple,
                       min_conf: int, top: int):
    """同 screen_universe,但鎖定某歷史 as_of 快照 (日期回顧用)。"""
    return score_store.screen_by_composite_at(
        as_of=as_of, mode=mode,
        min_composite=float(min_composite),
        ratings=list(ratings) or None,
        min_confidence=float(min_conf) if min_conf > 0 else None,
        top=int(top),
    )


@st.cache_data(show_spinner=False)
def tej_stock_names() -> dict:
    """代號→股名全市場對照 (TEJ 產業對照表靜態快照,含下市股 2,400+ 檔;
    本機與雲端皆讀 repo 內的 cloud_cache/stock_names.csv)。失敗回空 dict。"""
    path = os.path.join(_ROOT, "cloud_cache", "stock_names.csv")
    try:
        df = pd.read_csv(path, dtype=str)
        return dict(zip(df["stock_id"], df["name"]))
    except Exception:
        return {}


def watchlist_names():
    """從 watchlist.txt 解析 {代號: 股名}，供『綜合分選股』把快取內 name==代號 的
    舊資料回填成正確股名 (例 2330 → 台積電)。檔案不存在/解析失敗 → 回傳空 dict。
    格式:代號後第一個 token 當股名,可含 '#' 註解符 ('2330  台積電' 或 '2330  # 台積電')。"""
    path = os.path.join(_ROOT, "watchlist.txt")
    names: dict = {}
    if not os.path.exists(path):
        return names
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                code = parts[0].strip().upper()
                if not code or code.startswith("#"):
                    continue
                rest = line[len(parts[0]):].strip()
                if rest.startswith("#"):
                    rest = rest.lstrip("#").strip()
                if rest:
                    nm = rest.split()[0].strip()
                    if nm and not nm.startswith("#"):
                        names[code] = nm
    except Exception:
        pass
    return names


def parse_codes(raw: str):
    for sep in ("，", ",", "、", ";", "；", "\n"):
        raw = raw.replace(sep, " ")
    out = []
    for t in raw.split():
        t = t.strip().upper()
        if t and t not in out:
            out.append(t)
    return out


# ------------------------------------------------------------------ 側邊欄
st.sidebar.title("📊 台股四維度決策")
mode = st.sidebar.radio("策略模式", list(MODE_LABELS.keys()),
                        index=1, format_func=lambda m: MODE_LABELS[m])
st.sidebar.caption(MODE_HELP[mode] + f"  (門檻 min_score {ScoringManager.MODES[mode]['min_score']})")
refresh = st.sidebar.checkbox("刷新最新資料 (重抓 API)", value=False,
                              help="預設走本機快取省 API;要抓當日最新價再勾。")
st.sidebar.divider()
st.sidebar.subheader("🔑 FinMind 存取")
user_token = st.sidebar.text_input(
    "你的 FinMind API token", value="", type="password",
    help="即時『個股分析/多檔排行』會用『你自己的』token 打 FinMind,額度算你的、不共用、"
         "也不會寫入伺服器。留空=匿名 (每小時 300 次,且雲端為共用 IP、尖峰易被分光)。"
         "『綜合分選股』分頁免 token。")
if user_token:
    st.sidebar.caption("✅ 已使用你的 token (額度算你的)")
else:
    st.sidebar.caption("ℹ️ 未貼 token → 匿名模式;建議用『綜合分選股』分頁 (免 token)")
st.sidebar.divider()
st.sidebar.caption("⚠️ 研究/篩選輔助,非投資建議。評級是『狀態分類』,不是立刻買進;"
                   "進場價位請看每檔的『買點提示』。")

# ------------------------------------------------------------------ WP2-7 全域資料新鮮度告警
def _latest_shortlist_date() -> str | None:
    """最新 shortlist 凍結日 (本機 outputs 優先,雲端退回 cloud_cache 快照)。"""
    import glob as _g
    _base = os.path.dirname(os.path.abspath(__file__))
    for _d in (os.path.join(_base, "outputs", "universe_pool"),
               os.path.join(_base, "cloud_cache", "UniversePool")):
        _fs = sorted(_g.glob(os.path.join(_d, "shortlist_*.csv")))
        if _fs:
            _m = re.search(r"shortlist_(\d{4}-\d{2}-\d{2})\.csv", os.path.basename(_fs[-1]))
            if _m:
                return _m.group(1)
    return None


def _render_stale_banner():
    """最新 shortlist 距今 >1 交易日即紅字警示 (本機＋雲端),含最後成功日期。
    無台股假日日曆,以營業日 (Mon-Fri) 近似;>1 交易日容差已吸收單一國定假日與『今日尚未開跑』。"""
    _d = _latest_shortlist_date()
    if not _d:
        return
    try:
        _last = pd.Timestamp(_d)
    except Exception:
        return
    _today = pd.Timestamp.now().normalize()
    if _last >= _today:
        return
    _bdays = len(pd.bdate_range(_last + pd.Timedelta(days=1), _today))
    if _bdays > 1:
        st.error(
            f"⚠️ **資料可能過期**:最新 shortlist 為 **{_d}**,距今約 {_bdays} 個交易日未更新。"
            f"每日粗篩排程 (Market_SnapshotCollector) 疑似漏跑——本機請查 `outputs\\heartbeat\\` "
            f"心跳與 ALERT 檔;雲端請確認每日快照 commit 是否中斷。"
            f"下方『全市場掃描』與『實戰演練』數據皆以此日期為基準,解讀請留意時效。")


_render_stale_banner()

(tab_one, tab_rank, tab_screen, tab_univ, tab_fusion, tab_flow,
 tab_regime, tab_dca, tab_drill, tab_help) = st.tabs(
    ["🔎 個股分析", "🏆 多檔排行", "🎯 綜合分選股", "🌐 全市場掃描",
     "✨ 雙確認精選", "🏭 法人流向", "🚦 市場燈號", "💰 定期定額", "📋 實戰演練", "📖 使用說明"])


# ------------------------------------------------------------------ 法人資金流向產業 (想法2 B版)
with tab_flow:
    st.subheader("🏭 法人資金流向產業")
    st.caption(
        "全市場三大法人**每日淨買 × 收盤價 = 淨流入金額**,依 TEJ 產業別聚合。"
        "歷史來自本機 TEJ 種子(2004 起)、最新一段由證交所 T86＋櫃買 3insti 每日 17:30 自動接續"
        "(全程 0 FinMind API)。"
        "**這是資金流向的描述圖,非買賣訊號** —— 法人賣轉買在本專案實證是反指標。")

    _lv = st.radio("產業層級", list(industry_flow.LEVELS.keys()), index=0, horizontal=True,
                   help="子產業最細(散裝航運/貨櫃輪級,~250 類);產業/上市產業較粗。")
    _metric_map = {"外資+投信": "combined", "外資": "foreign", "投信": "trust"}
    _mlabel = st.radio("法人別", list(_metric_map.keys()), index=0, horizontal=True)
    _rawcol = _metric_map[_mlabel]

    _flow_all = get_industry_flow(_lv)
    if _flow_all is None or _flow_all.empty:
        st.warning(
            "目前沒有產業流向快取。請在專案根目錄執行:\n\n"
            "```\npython scripts/build_industry_flow.py\n```\n"
            "(需本機 `~/tej_cache` 種子或 `~/market_cache` 每日快照;跑完按 R 重整。)")
    else:
        _all_dates = sorted(_flow_all["date"].unique())

        # ---- 期間:全期可能上千個交易日,播放/累計都要先收斂範圍 ----
        _win_map = {"近 20 日": 20, "近 60 日": 60, "近 120 日": 120, "近 250 日": 250,
                    "全部": None}
        _wopts = [k for k, v in _win_map.items() if v is None or v <= len(_all_dates)] or ["全部"]
        _win = st.radio("期間", _wopts, index=0, horizontal=True,
                        help="決定『播放』的幀數與『期間累計』的區間。全部=快取內所有交易日。")
        _n_win = _win_map.get(_win)
        _dates = _all_dates[-_n_win:] if _n_win else _all_dates
        _flow = _flow_all[_flow_all["date"].isin(set(_dates))]
        _dmin, _dmax = _dates[0], _dates[-1]

        # ---- 量綱:金額會被權值股單日爆量壓垮 (晶圓代工單日 -1121 億),占比口徑天生同尺度 ----
        _has_turn = ("turnover" in _flow.columns
                     and float(_flow["turnover"].fillna(0).abs().sum()) > 0)
        _unit_opts = ["億元", "占成交額 %"] if _has_turn else ["億元"]
        _unit = st.radio("量綱", _unit_opts, index=0, horizontal=True,
                         help="億元=絕對金額,大產業恆常佔版面;占成交額%=淨流入÷該產業當日成交額,"
                              "把大小產業拉到同一把尺上比較。"
                         if _has_turn else "快取沒有成交額欄 → 重跑 build_industry_flow.py 解鎖占比口徑。")
        _pct = _unit == "占成交額 %"
        # 占比口徑下,成交額太小的產業會做出 ±100% 的假極端 → 設門檻剔除 (單日 5 億;累計按天數放大)
        _MIN_TURN = 5.0
        _unit_txt = "**%**（淨流入÷成交額）" if _pct else "**億元**"
        st.markdown(f"資料日 **{_dmin} ～ {_dmax}**（{len(_dates)} 個交易日，"
                    f"快取共 {len(_all_dates)} 日）　｜　單位：{_unit_txt}"
                    "（正=淨買進、負=淨賣出）")
        st.caption("長條圖的視覺語言：**顏色 = 方向**（紅買超／綠賣超，台股慣例）、**長度 = 數值**、"
                   "**透明度 = 金額大小**（小額淡出，壓掉中段短長條的干擾）、"
                   "**數字直接標在長條尾端**（不必對 X 軸或 hover）。"
                   "透明度用的是相對尺度（|值| 的 70 百分位以上全滿），"
                   "所以切換量綱／期間／層級都不用重調門檻。")

        _view = st.radio("檢視", ["單日掃描(可移動)", "期間累計", "產業地圖(Treemap)"],
                         index=0, horizontal=True,
                         help="前兩者用長條看『排名與數值』(位置/長度是判讀最準的通道);"
                              "產業地圖用面積+顏色看『整體版圖與資金分布』,兩者職責不同。")
        _topn = st.slider("顯示產業數 (各取淨買/淨賣前段)", 6, 20, 12)

        def _with_pct(_df, _min_turn=_MIN_TURN):
            """加上占成交額% 欄 (foreign_pct/trust_pct/combined_pct);占比模式下剔除薄量產業。"""
            _d = _df.copy()
            if "turnover" not in _d.columns:
                return _d
            _t = _d["turnover"].replace(0, float("nan"))
            for _c in ("foreign", "trust", "combined"):
                if _c in _d.columns:
                    _d[f"{_c}_pct"] = _d[_c] / _t * 100
            if _pct:
                _d = _d[_d["turnover"] >= _min_turn]
            return _d

        _mcol = f"{_rawcol}_pct" if _pct else _rawcol
        _fmt = ".2f" if _pct else ".1f"
        _unit_sfx = "%" if _pct else "億"
        _axis_title = f"{_mlabel} 淨流入 ({'占成交額 %' if _pct else '億元'})"

        # ---- 配色 ----------------------------------------------------------------
        # 台股慣例:**紅 = 漲/買超、綠 = 跌/賣超**(與歐美相反),故 pos=紅、neg=綠。
        # 核心法則:極端值亮如發光、中間值暗如背景。但「背景」是什麼色取決於主題 ——
        # 本 app 沒鎖 theme(無 .streamlit/config.toml)→ Streamlit 跟著瀏覽器深淺色模式走,
        # 兩種都會遇到。深色底是霓虹組;淺色底同原則,但零軸退向近白而非近黑(填近黑會讓
        # 中性小變動變成白底上最搶眼的方塊,效果完全相反)。
        # zero 不能貼齊頁面底色:深色底頁面是 #0E1117,零軸若也用同階,近零方塊會整片糊掉
        # 看不出邊界 → 零軸抬到 #3A4256 (仍遠暗於霓虹端點,不搶戲),另用 edge 畫出方塊間的溝縫。
        # txt_bar = 長條尾端數字的顏色。畫在圖的背景上(不是畫在方塊上),所以必須跟著主題走 ——
        # Vega 的 mark_text 預設是黑字,在深色底等於隱形。
        _PAL = {
            "淺色底（預設主題）": {"pos": "#D50000", "neg": "#00A152", "zero": "#E3E8EF",
                                   "edge": "#FFFFFF", "txt_bar": "#111111",
                                   "txt_hi": "#FFFFFF", "txt_lo": "#111111"},
            "深色底（霓虹）":     {"pos": "#FF1744", "neg": "#00E676", "zero": "#3A4256",
                                   "edge": "#0E1117", "txt_bar": "#E6EAF1",
                                   "txt_hi": "#FFFFFF", "txt_lo": "#FFFFFF"},
        }
        # 本 app 沒鎖 theme → Streamlit 跟著瀏覽器的 prefers-color-scheme 走,深淺兩種都會遇到。
        # st.context.theme 是 1.44+ 才有 (本機 1.59 有、雲端鎖 1.37 沒有) → 取不到就預設淺色。
        try:
            _th = getattr(getattr(st, "context", None), "theme", None)
            _pal_idx = 1 if str(getattr(_th, "type", "")).lower() == "dark" else 0
        except Exception:          # 1.37 有 st.context 但沒有 .theme;任何存取異常都退回淺色
            _pal_idx = 0
        _pal_name = st.radio("配色", list(_PAL.keys()), index=_pal_idx, horizontal=True,
                             help="配色要配合你的主題(跟著瀏覽器深淺色模式走,也可在右上角選單改)。"
                                  "深色底那組是霓虹色,在白底上對比不足;淺色底那組把零軸退向近白而非近黑。"
                                  "偵測不到主題時預設淺色,自己切即可。")
        _P = _PAL[_pal_name]

        # Vega/Streamlit 走 autosize:fit → properties(height) 是**含圖例與 X 軸的總高**,
        # 不是繪圖區高度 (與 treemap 同一個坑)。實測頂部圖例 + X 軸 + 軸標題共吃掉約 131px。
        # 舊寫法 26*n+40 在成分股少的產業直接爆掉:FCCL 只有 3 檔 → 總高 118 < 131,
        # 繪圖區被壓成負值、Vega 夾成一條細縫 → 長條超細、標籤疊成一團。
        _BAR_CHROME = 132

        def _bar_h(_n):
            """依列數算圖高:每列 28px 的繪圖區 + 固定 chrome。少列數也保證長條有正常厚度。"""
            return 28 * max(int(_n), 1) + _BAR_CHROME

        def _sign_col(_df, _col):
            """買/賣兩色(取代原本的紅黃綠連續色階) —— 大小交給長度與透明度,顏色只管方向。"""
            return ["買超" if (_v is not None and _v >= 0) else "賣超"
                    for _v in _df[_col].fillna(0)]

        def _alpha_scale(_vals):
            """
            透明度尺度:大額全滿、小額淡出 (壓掉中段短長條的彩度干擾)。

            定義域 = [|值| 的 25 百分位, 75 百分位] 並 clamp,**兩端都用分位數錨定**:
              · 不用固定的 10/50 億門檻 —— 量綱(億元/%)、期間(20 日/857 日)、產業層級
                都會讓絕對門檻失效,分位數三者通吃。
              · 不用 [0, max] 線性:法人流向是重尾分佈 (單日常見「一根 70 億、其餘 6~30 億」),
                線性會讓除了第一名以外全部糊在一起。
              · 也不用 pow 曲線壓:實測 exponent=2 會把第二名 (39 億,超過龍頭一半) 壓到 0.45,
                讀起來變成「只有冠軍看得見」,矯枉過正。
            結果:前 25% 全滿、後 25% 淡到 0.35、中間線性 —— 這才是原始建議想要的效果。
            """
            _a = _vals.abs().dropna()
            _lo = float(_a.quantile(0.25)) if len(_a) else 0.0
            _hi = float(_a.quantile(0.75)) if len(_a) else 0.0
            if not _hi > _lo:                      # 退化 (值幾乎相同) → 退回 [0, max]
                _lo, _hi = 0.0, (float(_a.max()) if len(_a) else 1.0) or 1.0
            return alt.Scale(domain=[_lo, _hi], range=[0.35, 1.0], clamp=True)

        def _flow_hbar(_df_show, _xcol, _xtitle, _xdomain=None):
            """產業淨流入橫向分歧長條。顏色=方向(紅買/綠賣,台股慣例)、長度=數值、透明度=金額大小
            (壓掉中段小長條的干擾)、尾端標數字(不必對 X 軸或 hover)。
            _xdomain=[lo,hi] → 固定 x 軸 (動畫逐幀比例一致,不跳動)。"""
            if _df_show is None or _df_show.empty:
                return alt.Chart(pd.DataFrame({"x": []})).mark_bar().properties(height=60)
            _d = _df_show.copy()
            _d["_dir"] = _sign_col(_d, _xcol)
            _d["_abs"] = _d[_xcol].abs()
            _d["_lab"] = [("" if pd.isna(_v) else f"{_v:+,.1f}{_unit_sfx}") for _v in _d[_xcol]]
            # 標籤貼在長條尾端;x 軸被固定時把標籤夾回軸內,否則超出範圍的標籤會被裁掉看不到
            _d["_lx"] = (_d[_xcol].clip(_xdomain[0], _xdomain[1]) if _xdomain else _d[_xcol])

            _xenc = (alt.X(f"{_xcol}:Q", title=_xtitle, scale=alt.Scale(domain=_xdomain))
                     if _xdomain else alt.X(f"{_xcol}:Q", title=_xtitle))
            # 排序在 Python 端算好,並**把它釘成 y 尺度的 domain**(最大正 → 中間 → 最大負)。
            # 這是 layer 圖 (長條 + 正值標籤 + 負值標籤三層各自資料子集),共用 y 軸時 Vega 會把
            # 三層的 domain 聯集:用 sort="-x" 三層各自排序會打架 (長條變超細、標籤擠成一團),
            # 就算改傳明確 sort 清單,聯集仍會把負值段的順序弄反。只有明寫 scale.domain
            # 才能完全蓋掉聯集行為。
            _order = _d.sort_values(_xcol, ascending=False)["industry"].tolist()
            _yenc = alt.Y("industry:N", title=None, scale=alt.Scale(domain=_order))
            _tt = ([alt.Tooltip("industry:N", title="產業")]
                   + [alt.Tooltip(f"{c}:Q", title=t, format=".1f")
                      for c, t in [("foreign", "外資(億)"), ("trust", "投信(億)"),
                                   ("combined", "合計(億)")]]
                   + ([alt.Tooltip("combined_pct:Q", title="合計占成交額%", format=".2f"),
                       alt.Tooltip("turnover:Q", title="成交額(億)", format=".0f")]
                      if _has_turn else [])
                   + [alt.Tooltip("n_stocks:Q", title="檔數")])
            _bar = alt.Chart(_d).mark_bar(clip=True).encode(
                x=_xenc, y=_yenc,
                color=alt.Color("_dir:N", title=None,
                                scale=alt.Scale(domain=["買超", "賣超"],
                                                range=[_P["pos"], _P["neg"]]),
                                legend=alt.Legend(orient="top", direction="horizontal")),
                opacity=alt.Opacity("_abs:Q", legend=None, scale=_alpha_scale(_d[_xcol])),
                tooltip=_tt)
            # 正值標右側、負值標左側 → 兩層 (mark 的 align 不能逐列變)
            _txt = []
            for _side, _al, _dx in (("買超", "left", 4), ("賣超", "right", -4)):
                _sub = _d[_d["_dir"] == _side]
                if _sub.empty:
                    continue
                _txt.append(alt.Chart(_sub).mark_text(align=_al, dx=_dx, fontSize=10,
                                                      baseline="middle", color=_P["txt_bar"])
                            .encode(x=alt.X("_lx:Q", title=_xtitle,
                                            scale=alt.Scale(domain=_xdomain) if _xdomain
                                            else alt.Undefined),
                                    y=_yenc, text="_lab:N", tooltip=_tt))
            return (alt.layer(_bar, *_txt)
                    .properties(height=_bar_h(len(_d)))
                    .resolve_scale(x="shared", y="shared"))

        def _day_show(_d):
            """某日淨買前 topn + 淨賣前 topn,合成一張分歧長條的資料。"""
            _day = _with_pct(_flow[_flow["date"] == _d])
            if _day.empty:
                return _day
            return pd.concat([_day.nlargest(_topn, _mcol),
                              _day.nsmallest(_topn, _mcol)]).drop_duplicates(subset=["industry"])

        def _cum_frame():
            """整段期間每個產業的累計淨流入 + 累計成交額。占比口徑要『先各自加總再相除』
            (Σ淨流入 ÷ Σ成交額),不是每日比率的平均 —— 後者會被薄量日的極端比率拉走。"""
            _c = (_flow.groupby("industry")
                       .agg(foreign=("foreign", "sum"), trust=("trust", "sum"),
                            combined=("combined", "sum"), turnover=("turnover", "sum"),
                            n_stocks=("n_stocks", "max"))
                       .reset_index())
            return _with_pct(_c, _MIN_TURN * len(_dates))

        # ---- Treemap:面積=成交額 (資金體量)、顏色=淨流入 (誰在買賣) —— Finviz 口徑 ----
        # Altair 沒有 treemap mark,squarified 版面自己算 (core/treemap.py),再用 mark_rect 畫,
        # 零新依賴 (雲端鎖 altair 5.3 / numpy 1.26,不值得為一張圖引 plotly)。
        # squarified 算出來的長寬比只有在「畫布長寬比 = 實際繪圖區長寬比」時才成立。
        # Streamlit 送給 Vega 的是 autosize:fit → properties(height) 是**含圖例的總高**,
        # 圖例會從繪圖區扣走。故標題改用 st.markdown 畫在圖外,並把實測的圖例高度加回
        # properties,讓繪圖區真的等於 _TM_W × _TM_H(實測底部橫向漸層圖例 = 106px)。
        # 註:這個常數估錯只會讓方塊被等比拉伸(長寬比略差),**不影響資料正確性** ——
        # x/y 都是線性尺度,面積之間的比例在任何均勻拉伸下都不變。
        _TM_W, _TM_H, _TM_LEGEND = 880, 430, 106

        def _treemap(_src, _tot_all):
            """_src 需含 industry/turnover/foreign/trust/combined(+_pct)/n_stocks。
            _tot_all = **未經任何過濾**的當期全產業成交額 —— 覆蓋率要對它算才誠實
            (占比模式的薄量門檻已先砍掉一批,拿砍完的當分母會永遠接近 100%)。
            回傳 (chart, 顯示用 df, 被丟掉的產業數)。"""
            from core.treemap import squarify
            _d = _src[_src["turnover"].fillna(0) > 0].copy()
            if _d.empty:
                return None, _d, 0
            _n_show = min(2 * _topn, len(_d))
            _dropped = len(_d) - _n_show
            _d = _d.nlargest(_n_show, "turnover").reset_index(drop=True)
            _d["cover"] = _d["turnover"] / _tot_all * 100 if _tot_all else 0.0

            _rects = squarify(_d["turnover"].tolist(), _TM_W, _TM_H)
            for _k in ("x", "y", "x2", "y2", "w", "h"):
                _d[_k] = [_r[_k] for _r in _rects]
            _d["cx"] = (_d["x"] + _d["x2"]) / 2
            _d["cy"] = (_d["y"] + _d["y2"]) / 2

            # 顏色域用 90 百分位的穩健對稱上界:單一極端產業不會把其他塊全洗成同一色
            _v = _d[_mcol].abs().dropna()
            _cmax = float(_v.quantile(0.90)) if len(_v) else 0.0
            _cmax = _cmax if _cmax > 0 else (float(_v.max()) if len(_v) else 1.0)
            _cmax = _cmax or 1.0
            # 三段式雙極色階:0 附近退到「背景色」(深色底=近黑、淺色底=近白),兩端拉滿飽和
            # → 中性小變動不搶注意力,極端大額像發光一樣浮出來
            # interpolate="rgb" 是必要的:Vega 對自訂 range 預設走 HCL,紅→暗→綠 會繞過
            # 紫色與青色 (實測跑出 rgb(116,49,117) 紫、rgb(0,114,140) 青),整張圖語意就毀了。
            # RGB 線性內插才會老老實實地「紅→暗紅→暗→暗綠→綠」。
            _cscale = alt.Scale(domain=[-_cmax, 0.0, _cmax], interpolate="rgb",
                                range=[_P["neg"], _P["zero"], _P["pos"]], clamp=True)
            # 文字色:塊夠飽和用 txt_hi,接近零軸(底色接近背景)用 txt_lo。
            # 深色底兩者都是純白;淺色底近零是近白底 → 必須用深色字,不能一律白字。
            _d["_txtc"] = [_P["txt_hi"] if abs(_x) >= 0.45 * _cmax else _P["txt_lo"]
                           for _x in _d[_mcol].fillna(0)]
            _d["_lab"] = _d["industry"]
            _d["_val"] = [("—" if pd.isna(_x) else (f"{_x:+.2f}%" if _pct else f"{_x:+,.0f}"))
                          for _x in _d[_mcol]]

            _base = alt.Chart(_d).encode(
                x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[0, _TM_W], nice=False)),
                x2="x2:Q",
                y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[0, _TM_H], nice=False)),
                y2="y2:Q")
            _tt = ([alt.Tooltip("industry:N", title="產業"),
                    alt.Tooltip("turnover:Q", title="成交額(億)", format=",.0f"),
                    alt.Tooltip("cover:Q", title="占顯示範圍成交額%", format=".1f")]
                   + [alt.Tooltip(f"{c}:Q", title=t, format=".1f")
                      for c, t in [("foreign", "外資(億)"), ("trust", "投信(億)"),
                                   ("combined", "合計(億)")]]
                   + ([alt.Tooltip("combined_pct:Q", title="合計占成交額%", format=".2f")]
                      if _has_turn else [])
                   + [alt.Tooltip("n_stocks:Q", title="檔數")])
            # 邊框用頁面底色畫出方塊間的溝縫 (不能用零軸色,那樣近零方塊會與邊框同色而糊成一片)
            _rect = _base.mark_rect(stroke=_P["edge"], strokeWidth=2).encode(
                color=alt.Color(f"{_mcol}:Q", title=_axis_title, scale=_cscale,
                                legend=alt.Legend(orient="bottom", direction="horizontal",
                                                  gradientLength=260)),
                tooltip=_tt)
            # 塊太小就不標字 (硬塞會疊成一團);數字只在夠高的塊才出現
            _big = _d[(_d["w"] >= 52) & (_d["h"] >= 24)]
            _bigger = _d[(_d["w"] >= 52) & (_d["h"] >= 42)]
            _name = (alt.Chart(_big).mark_text(fontSize=11, fontWeight="bold", dy=-6)
                     .encode(x=alt.X("cx:Q", axis=None, scale=alt.Scale(domain=[0, _TM_W], nice=False)),
                             y=alt.Y("cy:Q", axis=None, scale=alt.Scale(domain=[0, _TM_H], nice=False)),
                             text="_lab:N", color=alt.Color("_txtc:N", scale=None, legend=None),
                             tooltip=_tt))
            _num = (alt.Chart(_bigger).mark_text(fontSize=10, dy=9)
                    .encode(x=alt.X("cx:Q", axis=None, scale=alt.Scale(domain=[0, _TM_W], nice=False)),
                            y=alt.Y("cy:Q", axis=None, scale=alt.Scale(domain=[0, _TM_H], nice=False)),
                            text="_val:N", color=alt.Color("_txtc:N", scale=None, legend=None),
                            tooltip=_tt))
            _ch = ((_rect + _name + _num)
                   .properties(width=_TM_W, height=_TM_H + _TM_LEGEND)
                   .configure_view(strokeWidth=0))
            return _ch, _d, _dropped

        if _view == "單日掃描(可移動)":
            # 播放鈕:自動逐日推進 (bar-chart-race);滑桿:手動掃描單日
            _c1, _c2 = st.columns([1, 2])
            _play = _c1.button("▶ 播放連續天數", key="flow_play", use_container_width=True)
            _speed = _c2.select_slider("播放速度", options=["慢", "中", "快"], value="中")
            _delay = {"慢": 1.1, "中": 0.6, "快": 0.3}[_speed]
            _fix_axis = st.checkbox("固定 x 軸 (動畫不跳動)", value=True,
                                    help="以整段期間單日淨流入的最大絕對值,把 x 軸固定成對稱範圍;"
                                         "關閉則每日自動縮放 (單一極端值會壓縮其他天)。")
            # 固定範圍 = 各日最大絕對值的穩健上界:剔除 >3×中位數 的極端日 (如晶圓代工單日
            # -1121 億),避免單日爆量把其他天壓成細絲;極端長條 clip 在軸邊。
            # 各日最大 |值| 一定落在該日 top-n 買/賣其中一端,故直接對全表 groupby 取,不必逐日 nlargest。
            _fp = _with_pct(_flow)
            _daily_max = _fp.groupby("date")[_mcol].apply(lambda s: float(s.abs().max() or 0))
            _med = float(_daily_max.median() or 0)
            _kept = _daily_max[_daily_max <= 3 * _med] if _med > 0 else _daily_max
            _absmax = float(_kept.max() if len(_kept) else 0) * 1.10
            _clipped = _med > 0 and float(_daily_max.max()) > 3 * _med
            _xdom = [-_absmax, _absmax] if (_fix_axis and _absmax > 0) else None
            _pick = st.select_slider("交易日（拖動掃描）", options=_dates, value=_dmax)
            _ph = st.empty()
            _cap = st.empty()

            # 幀數上限:全期可能上千個交易日,逐日播放會把整個 app 卡住數分鐘 → 等距抽幀,
            # 並在字幕明講抽樣間隔 (不做無聲截斷)。
            _MAXF = 150
            _step = max(1, -(-len(_dates) // _MAXF))
            _frames = _dates[::_step]
            if _step > 1:
                st.caption(f"⏱️ 期間有 {len(_dates)} 個交易日 → 播放每 {_step} 日抽 1 幀"
                           f"(共 {len(_frames)} 幀);想逐日看請把期間縮到近 120 日以內。")

            if _play:
                # 逐日更新同一個 placeholder → 連續移動過程;結束停在最新日
                for _d in _frames:
                    _ph.altair_chart(
                        _flow_hbar(_day_show(_d), _mcol, f"{_axis_title} — {_d}", _xdom),
                        use_container_width=True)
                    _cap.caption(f"▶ 播放中… {_d}")
                    time.sleep(_delay)
                _pick = _frames[-1]
            _show = _day_show(_pick)
            _ph.altair_chart(_flow_hbar(_show, _mcol, f"{_axis_title} — {_pick}", _xdom),
                             use_container_width=True)
            _unit_s = "%" if _pct else "億"
            _cap.caption(f"📅 {_pick} 當日 {_mlabel}淨流入前 {_topn} 買 / 前 {_topn} 賣。"
                         "按『▶ 播放連續天數』看逐日移動,或拖滑桿手動掃描。"
                         + (f"　⚠️ x 軸固定在 ±{_absmax:.1f}{_unit_s};極端日的長條會 clip 在軸邊,"
                            "實際數字看長條 tooltip。" if _xdom and _clipped else "")
                         + (f"　成交額 < {_MIN_TURN:.0f} 億的薄量產業已剔除 (避免假極端)。"
                            if _pct else ""))
            _drill_date = _pick
        elif _view == "產業地圖(Treemap)":
            # 面積=成交額(資金體量,必為正)、顏色=淨流入(誰在買賣)。回答「版圖長怎樣」,
            # 精確排名仍看長條圖 —— 面積的判讀精度天生低於位置/長度。
            if not _has_turn:
                st.warning("快取沒有成交額欄,畫不出產業地圖。請重跑 "
                           "`python scripts/build_industry_flow.py` 後按 R 重整。")
                _show, _drill_date = pd.DataFrame(columns=["industry"]), None
            else:
                _tb = st.radio("地圖基準", ["單日", "期間累計"], index=1, horizontal=True,
                               help="單日=某一天的資金分布;期間累計=整段期間加總(版面較穩定)。")
                if _tb == "單日":
                    _tpick = st.select_slider("交易日（拖動掃描）", options=_dates, value=_dmax,
                                              key="tm_date")
                    _raw = _flow[_flow["date"] == _tpick]
                    _src = _with_pct(_raw)
                    _ttl = f"{_axis_title} — {_tpick}"
                    _drill_date = _tpick
                else:
                    _raw = _flow
                    _src = _cum_frame()
                    _ttl = (f"{_mlabel} 累計淨流入（{'占成交額 %' if _pct else '億元'}）"
                            f" — {_dmin}～{_dmax}")
                    _drill_date = None
                # 分母用未過濾的原始表:占比模式的薄量門檻已先砍掉一批產業,不能算進覆蓋率
                _tot_all = float(_raw["turnover"].fillna(0).sum())
                _n_all = int(_raw["industry"].nunique())
                _tmchart, _show, _cut = _treemap(_src, _tot_all)
                if _tmchart is None:
                    st.info("此條件下沒有成交額資料可畫。")
                else:
                    st.markdown(f"**{_ttl}**")   # 標題畫在圖外,不佔 Vega 繪圖區 (見 _TM_LEGEND)
                    st.altair_chart(_tmchart, use_container_width=False)
                    _cv = float(_show["cover"].sum())
                    _thin = _n_all - len(_show) - _cut         # 被薄量門檻剔除的產業數
                    _miss = ([f"成交額排名 {len(_show)} 名之後的 {_cut} 個" ] if _cut else []) \
                            + ([f"占比口徑薄量門檻剔除的 {_thin} 個"] if _pct and _thin > 0 else [])
                    st.caption(
                        f"**方塊面積 = 成交額**（資金體量）、**顏色 = {_mlabel}淨流入**"
                        f"（紅=買超、綠=賣超，{'占成交額 %' if _pct else '億元'}）。"
                        + (f"畫出 {len(_show)} 個產業，占{'該日' if _drill_date else '整段'}"
                           f"全部 {_n_all} 個產業成交額的 **{_cv:.0f}%**；未畫的是"
                           + "、".join(_miss) + "，要看完整排名請切「"
                           f"{'單日掃描' if _drill_date else '期間累計'}」長條圖。"
                           if _miss else
                           f"全部 {_n_all} 個產業都在圖上（占成交額 {_cv:.0f}%），沒有省略。")
                        + f"色階是**三段式**：0 附近退到接近背景色、兩端拉滿飽和 —— 中性小變動不搶注意力，"
                          f"極端大額才會「發光」浮出來。上下界取 |淨流入| 的 90 百分位（對稱），"
                          f"更極端的塊壓在端點（實際數字看 tooltip）。方塊太小時不標字，滑上去看 tooltip。")
        else:
            _drill_date = None  # 累計視圖 → 下鑽看整段累計
            _cum = _cum_frame()
            _show = pd.concat([_cum.nlargest(_topn, _mcol),
                               _cum.nsmallest(_topn, _mcol)]).drop_duplicates(subset=["industry"])
            st.altair_chart(_flow_hbar(_show, _mcol, f"{_mlabel} 累計淨流入 "
                                       f"({'占成交額 %' if _pct else '億元'})"),
                            use_container_width=True)

            # 前 5 淨買產業的累計流入趨勢線 (看資金持續流入還是單日爆量)
            _top5 = _cum.nlargest(5, _mcol)["industry"].tolist()
            _tl = _flow[_flow["industry"].isin(_top5)].copy().sort_values("date")
            if _pct:      # 累計占比 = 累計淨流入 ÷ 累計成交額 (同上,先加總再相除)
                _tl["_c"] = _tl.groupby("industry")[_rawcol].cumsum()
                _tl["_t"] = _tl.groupby("industry")["turnover"].cumsum()
                _tl["累計"] = _tl["_c"] / _tl["_t"].replace(0, float("nan")) * 100
            else:
                _tl["累計"] = _tl.groupby("industry")[_rawcol].cumsum()
            _line = (alt.Chart(_tl).mark_line().encode(
                        x=alt.X("date:T", title=None),
                        y=alt.Y("累計:Q", title=f"{_mlabel} 累計淨流入 "
                                               f"({'占成交額 %' if _pct else '億元'})"),
                        color=alt.Color("industry:N", legend=alt.Legend(title="產業", orient="top")),
                        tooltip=["date", "industry", alt.Tooltip("累計:Q", format=_fmt)])
                     .properties(height=300))
            st.markdown("**前 5 淨買產業 · 累計流入趨勢**")
            st.altair_chart(_line, use_container_width=True)
            st.caption(f"整段 {_dmin}～{_dmax}（{len(_dates)} 日）的 {_mlabel}累計淨流入"
                       f"前 {_topn} 買 / 前 {_topn} 賣;下圖看前 5 是持續吸金還是單日脈衝。"
                       + (f"　占比口徑=Σ淨流入÷Σ成交額,且剔除累計成交額 "
                          f"< {_MIN_TURN * len(_dates):.0f} 億的薄量產業。" if _pct else ""))

        # ---- 下鑽:點選產業展開成分股 (哪些個股在買/賣) ----
        st.divider()
        st.markdown("**🔍 展開產業看成分股**")
        _ind_opts = _show["industry"].tolist()   # 目前圖上的產業 (淨買+淨賣段),依 |流入| 排序
        # 成分股快取只留最近 N 日 (全歷史太大) → 下鑽區間要夾在成分股實際涵蓋範圍內,
        # 否則「累計」的主圖與下鑽會是不同期間,數字對不起來卻看不出來。
        _mrng0, _mrng1 = get_members_range()
        _dstart = max(_dmin, _mrng0) if _mrng0 else _dmin
        _dend = min(_dmax, _mrng1) if _mrng1 else _dmax
        _short = (not _drill_date) and _dstart > _dmin
        _when = f"{_drill_date} 當日" if _drill_date else f"{_dstart}～{_dend} 累計"
        _sel_ind = (st.selectbox(f"選一個產業展開成分股（{_when}）", _ind_opts, index=0,
                                 help="清單為上方圖表當前顯示的產業;展開看是哪些個股撐起這條資金流。")
                    if _ind_opts else None)
        if _short:
            st.info(f"成分股快取只留最近 {_mrng0}～{_mrng1};下鑽數字是這段區間的累計,"
                    f"比上方主圖的 {_dmin}～{_dmax} 短。要對齊請把期間縮短,"
                    "或用 `--member-days` 重建快照。")
        _mem = (get_industry_members(_lv, _sel_ind, _drill_date, _dstart, _dend)
                if _sel_ind else None)
        if _sel_ind is None:
            st.info("目前條件下沒有產業可展開（占比口徑的薄量門檻可能把整段都剔除了,"
                    "試著切回『億元』或拉長期間）。")
        elif _mem is None or _mem.empty:
            st.info("此產業當期無成分股法人資料。")
        else:
            _nmap = {**tej_stock_names(), **watchlist_names()}
            _mem = _with_pct(_mem, 0)      # 個股不套薄量門檻 (成分股本來就會有小型股)
            _mem["名稱"] = [_nmap.get(str(s), "") for s in _mem["stock_id"]]
            _mem["標籤"] = _mem["stock_id"] + " " + _mem["名稱"]
            _mem_show = pd.concat([_mem.nlargest(_topn, _mcol),
                                   _mem.nsmallest(_topn, _mcol)]).drop_duplicates(subset=["stock_id"])
            # 與上方主圖同一套視覺語言:顏色=方向、透明度=金額大小、尾端標數字
            _mem_show = _mem_show.copy()
            _mem_show["_dir"] = _sign_col(_mem_show, _mcol)
            _mem_show["_abs"] = _mem_show[_mcol].abs()
            _mem_show["_lab"] = [("" if pd.isna(_v) else f"{_v:+,.2f}{_unit_sfx}")
                                 for _v in _mem_show[_mcol]]
            # 同上:把排序釘成 scale.domain,不能只靠 sort (layer 圖的 domain 聯集會蓋掉它)
            _morder = _mem_show.sort_values(_mcol, ascending=False)["標籤"].tolist()
            _myenc = alt.Y("標籤:N", title=None, scale=alt.Scale(domain=_morder))
            _mtt = ([alt.Tooltip("標籤:N", title="個股")]
                    + [alt.Tooltip(f"{c}:Q", title=t, format=".2f")
                       for c, t in [("foreign", "外資(億)"), ("trust", "投信(億)"),
                                    ("combined", "合計(億)")]]
                    + ([alt.Tooltip("combined_pct:Q", title="合計占成交額%", format=".2f")]
                       if _has_turn else []))
            _mem_bar = alt.Chart(_mem_show).mark_bar().encode(
                x=alt.X(f"{_mcol}:Q", title=_axis_title), y=_myenc,
                color=alt.Color("_dir:N", title=None,
                                scale=alt.Scale(domain=["買超", "賣超"],
                                                range=[_P["pos"], _P["neg"]]),
                                legend=alt.Legend(orient="top", direction="horizontal")),
                opacity=alt.Opacity("_abs:Q", legend=None, scale=_alpha_scale(_mem_show[_mcol])),
                tooltip=_mtt)
            _mem_txt = [alt.Chart(_s).mark_text(align=_a, dx=_x, fontSize=10, baseline="middle",
                                                color=_P["txt_bar"])
                        .encode(x=alt.X(f"{_mcol}:Q", title=_axis_title), y=_myenc,
                                text="_lab:N", tooltip=_mtt)
                        for _s, _a, _x in
                        ((_mem_show[_mem_show["_dir"] == "買超"], "left", 4),
                         (_mem_show[_mem_show["_dir"] == "賣超"], "right", -4)) if not _s.empty]
            st.altair_chart(alt.layer(_mem_bar, *_mem_txt)
                            .properties(height=_bar_h(len(_mem_show))),
                            use_container_width=True)
            _cols = ["stock_id", "名稱", "foreign", "trust", "combined"]
            _ren = {"stock_id": "代號", "foreign": "外資", "trust": "投信", "combined": "合計"}
            if _has_turn and "combined_pct" in _mem.columns:
                _cols += ["turnover", "combined_pct"]
                _ren |= {"turnover": "成交額(億)", "combined_pct": "合計占成交額%"}
            st.dataframe(_mem[_cols].rename(columns=_ren).round(2),
                         use_container_width=True, hide_index=True)
            st.caption(f"**{_sel_ind}** 成分股（{_when}）{_mlabel}淨流入;"
                       "金額 = 法人淨買股數 × 收盤 ÷ 1e8（億元）,占比 = 該金額 ÷ 同期成交額。"
                       "貼代號到『個股分析』可看該檔四維度深評。")


# ------------------------------------------------------------------ 市場燈號 (曝險)
@st.cache_data(ttl=3600, show_spinner="計算市場燈號中…")
def _cached_exposure():
    from core.regime_exposure import get_exposure   # 本機即時算;雲端退回 cloud_cache 快照
    return get_exposure()


with tab_regime:
    st.subheader("🚦 市場燈號 — 現在該持有幾成")
    st.caption("反應式訊號:判斷『該承受多少風險』,**不是預測漲跌**。全循環(2005-2026)含息回測中,"
               "此訊號疊在價值+基本面選股上,夏普 0.83 > 0050 的 0.69、最大回撤 -24% 優於 0050 的 -54%。")
    try:
        _r = _cached_exposure()
    except Exception as e:
        st.error(f"燈號計算失敗(需本機 tej_cache/price_valuation):{e}")
    else:
        _expo, _n = _r["exposure"], _r["ladder_n"]
        _color = "🟢" if _n == 3 else ("🟡" if _n >= 1 else "🔴")
        _label = {3: "滿倉 risk-on", 2: "偏多", 1: "防禦減碼", 0: "空手 risk-off"}[_n]
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"<div style='font-size:64px;line-height:1'>{_color}</div>",
                        unsafe_allow_html=True)
            st.metric("建議曝險", f"{_expo*100:.0f}%", _label)
            st.caption(f"資料截至 {_r['as_of']}")
        with c2:
            st.markdown("**均線階梯**(全市場等權指數站上幾條 → 曝險 3/3、2/3、1/3、0)")
            for L in _r["lines"]:
                icon = "✅" if L["above"] else "❌"
                pend = "　⏳ 剛翻、遲滯確認中(需連 3 天)" if L["pending"] else ""
                st.write(f"{icon} **MA{L['ma']}**:{'站上' if L['above'] else '跌破'} "
                         f"{L['days']} 天　(距均線 {L['gap_pct']:+.1f}%){pend}")
            st.caption("空頭時逐階減碼→轉現金;遲滯(確認3d)濾掉碎波假訊號,避免賣低買高。")
        st.markdown("**近 120 日建議曝險**")
        st.area_chart(_r["hist"].set_index("date"), height=170)
        st.caption("⚠️ 反應式、非預測:它會**落後轉折點**,碎波盤可能小幅拉鋸。只告訴你『持有幾成』,"
                   "不告訴你買哪檔或漲跌方向。回測 ≠ 未來,非投資建議。")


# ------------------------------------------------------------------ 定期定額試算 (DCA)
@st.cache_data(ttl=86400)
def _dca_series():
    import os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    for _p in (_os.path.join("data", "research_base", "dca_series.parquet"),
               _os.path.join(_here, "cloud_cache", "dca_series.parquet")):   # 雲端退回快照
        if _os.path.exists(_p):
            return pd.read_parquet(_p)
    raise FileNotFoundError("dca_series.parquet 不在 data/ 或 cloud_cache/")


with tab_dca:
    st.subheader("💰 定期定額試算 — 你實際會拿到幾 %(MWRR)")
    st.caption("用 2005-2026 真實含息序列,模擬每月定期定額。策略 = 真身綜合分 top20% + 風控;"
               "0050 = 含息買進持有。**MWRR = 把你投入的時間與金額算進去的個人真實報酬。**")
    try:
        _s = _dca_series()
    except Exception as e:
        st.error(f"讀不到 DCA 序列(data/research_base/dca_series.parquet):{e}")
    else:
        _s = _s.sort_values("as_of").reset_index(drop=True)
        _yrs = sorted({a[:4] for a in _s["as_of"]})
        cc1, cc2 = st.columns(2)
        _amt = cc1.number_input("每月投入金額 (元)", min_value=1000, max_value=1_000_000,
                                value=5000, step=1000)
        _start = cc2.selectbox("起始年", _yrs, index=max(0, len(_yrs) - 12))
        _sub = _s[_s["as_of"] >= f"{_start}-01-01"].reset_index(drop=True)

        from core.dca_calc import simulate_dca, mwrr_annual
        _res = {}
        for _col, _lab in [("strat_ret", "策略"), ("bench_ret", "0050")]:
            _r = simulate_dca(_sub[_col].tolist(), _amt)
            _r["mwrr"] = mwrr_annual(_sub[_col].tolist(), _amt, _r["final"])
            _res[_lab] = _r

        st.markdown(f"**{_start} 起 · 每月 {_amt:,.0f} 元 · 共 {len(_sub)} 個月**")
        m1, m2 = st.columns(2)
        for _box, _lab in [(m1, "策略"), (m2, "0050")]:
            _r = _res[_lab]
            _box.markdown(f"### {_lab}")
            _box.metric("期末價值", f"{_r['final']:,.0f} 元",
                        f"{_r['final']/_r['invested']:.2f} 倍")
            _box.metric("個人年化報酬 MWRR", f"{_r['mwrr']:.1f}%")
            _box.caption(f"總投入 {_r['invested']:,.0f}｜過程最大回撤 {_r['mdd']:.0f}%")

        _chart = pd.DataFrame({
            "累計投入": [(i + 1) * _amt for i in range(len(_sub))],
            "策略": _res["策略"]["path"],
            "0050": _res["0050"]["path"],
        }, index=_sub["as_of"])
        st.line_chart(_chart, height=240)

        _win = "策略" if _res["策略"]["mwrr"] > _res["0050"]["mwrr"] else "0050"
        st.info(f"此區間 DCA:**{_win} 的個人報酬(MWRR)較高**。注意:策略空頭減碼會躲掉下跌、"
                "也躲掉『趁跌加碼』,近年強多頭常讓 0050 的 DCA 領先;策略通常勝在**回撤更小、坐得更穩**。"
                "起始年不同結論會變,自己拉拉看。")
        st.caption("⚠️ 歷史真實序列回測,proxy/近似補息、未含個股零股價差、回測 ≠ 未來。非投資建議。")

# ------------------------------------------------------------------ 個股分析
with tab_one:
    if not user_token:
        st.info("即時個股分析會打 FinMind API。請在左側貼上『你自己的 FinMind token』"
                "(額度算你的),或改用免 token 的『綜合分選股』分頁。未貼 token 會以匿名模式嘗試 "
                "(每小時 300 次、FinMind 以 IP 計;雲端部署為共用 IP,尖峰常被同 IP 流量分光而失敗)。")
    codes_raw = st.text_input("股票代號 (可多檔,空白/逗號分隔)", value="2330")
    if st.button("分析", type="primary"):
        codes = parse_codes(codes_raw)
        if not codes:
            st.warning("請輸入至少一個代號。")
        for code in codes:
            with st.spinner(f"分析 {code} …"):
                r = analyze(code, mode, refresh, user_token)
            if r is None:
                st.error(f"{code}:抓不到資料 (代碼錯誤或 FinMind 額度/Token 問題)。")
                continue
            st.markdown(f"### {r['symbol']} {r['name']}　{rating_badge(r['rating'])}",
                        unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("綜合評分", f"{r['total']:.1f}")
            c2.metric("現價", f"{r['price']:.2f}")
            c3.metric("資料信心", f"{r['confidence']:.0f}%")
            st.markdown(
                f"<div style='font-size:1rem;color:inherit;opacity:.82;margin:2px 0 10px'>"
                f"基本面:{escape(r['fundamental_label'])}　｜　趨勢:{escape(r['trend_label'])}　｜　"
                f"估值:{escape(r['valuation_status'])}　｜　獲利:{escape(r['quality_flag'])}　｜　"
                f"類別 {escape(r['sector'])}</div>", unsafe_allow_html=True)
            # 分項長條圖:X 軸標籤強制橫向 (labelAngle=0)
            dim_df = pd.DataFrame({"維度": list(r["dims"].keys()),
                                   "分數": [round(v, 1) for v in r["dims"].values()]})
            chart = (alt.Chart(dim_df).mark_bar(color="#4472C4")
                     .encode(x=alt.X("維度:N", sort=None,
                                     axis=alt.Axis(labelAngle=0, labelFontSize=15, title=None)),
                             y=alt.Y("分數:Q", scale=alt.Scale(domain=[0, 100]),
                                     axis=alt.Axis(title=None)),
                             tooltip=["維度", "分數"])
                     .properties(height=260))
            st.altair_chart(chart, use_container_width=True)
            # 系統建議:自動分行、放大字體、無圖示
            lines = format_advice(r["advice"])
            if lines:
                html = ("<div style='font-size:1.1rem;line-height:1.9'>"
                        + "".join(f"<p style='margin:8px 0'>{escape(l)}</p>" for l in lines)
                        + "</div>")
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.markdown("（無額外建議文字）")
            # 交易計畫:進場區間 / 停損 / 目標 (與 main.py CLI、其他分頁同一套規則換算)
            _plan = r.get("plan_lines") or []
            if _plan:
                st.markdown("**📐 交易計畫（進場區間・停損・目標;規則換算的價位參考,非投資建議）**")
                for _ln in _plan:
                    st.markdown(
                        f"<div style='font-size:1rem;color:inherit;opacity:.9;margin:2px 0 2px 8px'>· {escape(_ln)}</div>",
                        unsafe_allow_html=True)
            # 近日綜合分走勢 (讀 scores 快取,0 API;僅每日名單內的股票有歷史)
            _hist = get_score_history(r["symbol"], mode, limit=10)
            if _hist is not None and len(_hist) >= 2:
                st.markdown("**📈 近日綜合分走勢（每日名單快取・0 API・同權重版本才連線）**")
                # 綜合分主線 (較粗) + 五維分項細線,melt 成長格式一次畫;看『哪個維度在拉動綜合分』
                _dim_map = {"composite": "綜合分", "fundamental": "基本面", "valuation": "估值",
                            "technical": "技術面", "momentum": "動能", "whale": "籌碼"}
                _long = _hist.melt(id_vars="as_of",
                                   value_vars=[c for c in _dim_map if c in _hist.columns],
                                   var_name="_k", value_name="分數")
                _long["項目"] = _long["_k"].map(_dim_map)
                _order = [v for v in _dim_map.values()]
                _base = alt.Chart(_long).encode(
                    x=alt.X("as_of:O", axis=alt.Axis(title=None, labelAngle=-40)),
                    y=alt.Y("分數:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title=None)),
                    color=alt.Color("項目:N", sort=_order,
                                    scale=alt.Scale(domain=_order,
                                                    range=["#C00000", "#4472C4", "#70AD47",
                                                           "#ED7D31", "#7030A0", "#7F7F7F"]),
                                    legend=alt.Legend(title=None, orient="top")),
                    tooltip=["as_of", "項目", alt.Tooltip("分數:Q", format=".1f")])
                _comp = _long[_long["_k"] == "composite"]
                _trend = (
                    _base.mark_line(point=True).encode(
                        size=alt.condition("datum.項目 == '綜合分'", alt.value(3.0), alt.value(1.3)))
                    .properties(height=260)
                    + alt.Chart(_comp).mark_point(size=60, filled=True, color="#C00000")
                      .encode(x="as_of:O", y="分數:Q"))
                st.altair_chart(_trend, use_container_width=True)
                st.caption("走勢來自每日 0-API 名單快取（TEJ 五維，與即時 FinMind 綜合分近乎一致）；"
                           "僅涵蓋每日名單內個股，點數隨每日更新累積。")
            elif _hist is not None and len(_hist) == 1:
                st.caption("📈 此檔在每日名單內但目前只有 1 個歷史分數點，連續走勢待每日更新累積。")
            st.divider()

# ------------------------------------------------------------------ 多檔排行
with tab_rank:
    if not user_token:
        st.info("此頁逐檔即時打 FinMind API,建議先在左側貼上你自己的 token。"
                "若只是想看整個名單的排名,『綜合分選股』分頁免 token、而且更快。")
    rank_raw = st.text_area("輸入多檔代號 (排行用)", value="2330 2454 2317 2382 2308 3661")
    if st.button("跑排行", type="primary"):
        codes = parse_codes(rank_raw)
        rows = []
        prog = st.progress(0.0)
        for i, code in enumerate(codes):
            r = analyze(code, mode, refresh, user_token)
            if r:
                rows.append({"代號": r["symbol"], "名稱": r["name"], "評級": r["rating"],
                             "綜合分": round(r["total"], 1), "現價": round(r["price"], 2),
                             **{k: round(v) for k, v in r["dims"].items()}})
            prog.progress((i + 1) / len(codes))
        if rows:
            rows.sort(key=lambda x: x["綜合分"], reverse=True)
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.warning("沒有可用結果。")

# ------------------------------------------------------------------ 綜合分選股 (讀 scores 快取)
with tab_screen:
    st.caption(
        "從已建好的 **scores 快取**,對整個名單依五維綜合分跨股排名 —— 0 API、瞬間出。"
        "先在專案根目錄跑 `python build_cache.py --build-scores` 建/更新快取;"
        "排名依左側選的『策略模式』(三個模式各自一套分數)。")

    if st.button("↻ 重新載入快取",
                 help="剛在終端機跑完 --build-scores 後按這裡,讓網頁抓最新的 scores"):
        st.cache_data.clear()
        st.rerun()

    info = get_universe_info(mode)
    if info is None:
        st.warning(
            f"目前沒有「{MODE_LABELS[mode]}」模式的 scores 快取。\n\n"
            "請先在專案根目錄執行:\n\n"
            "```\n"
            "python build_cache.py --build-scores            # 建三個模式\n"
            f"python build_cache.py --build-scores --modes {mode}   # 只建這個模式\n"
            "```\n"
            "建好後回來按上面的「重新載入快取」。")
    else:
        st.markdown(
            f"名單共 **{info['stocks']}** 檔　｜　最新基準日 **{info['as_of']}**　｜　"
            f"權重版本 `{info['weights_version']}`　"
            "<span style='color:inherit;opacity:.65'>(排名只在此名單內相對比較)</span>",
            unsafe_allow_html=True)

        # 日期回顧:預設「最新」(每檔取各自最新一筆);選歷史某日則鎖定該 as_of 快照比對
        _screen_dates = get_as_of_dates(mode)
        _LATEST = "最新（每檔最新一筆）"
        _date_opts = [_LATEST] + _screen_dates[::-1] if _screen_dates else [_LATEST]
        _spick = st.selectbox("資料日(日期回顧)", _date_opts, index=0,
                              help="事後核對某一天的綜合分 Top 名單用;預設『最新』與過去慣用行為相同,"
                                   "可切到歷史某一交易日,與『雙確認精選/全市場掃描』同日對照。")

        f1, f2, f3 = st.columns(3)
        default_min = int(ScoringManager.MODES[mode]["min_score"])
        min_comp = f1.slider("綜合分下限", 0, 100, default_min,
                             help=f"預設 = 此模式門檻 min_score ({default_min})")
        min_conf = f2.slider("資料信心下限 (%)", 0, 100, 0)
        top = f3.slider("顯示檔數", 5, 100, 30)
        ratings = st.multiselect("限定評級 (不選 = 全部)", list(RATING_STYLE.keys()), default=[])

        if _spick == _LATEST:
            df = screen_universe(mode, min_comp, tuple(ratings), min_conf, top)
        else:
            df = screen_universe_at(_spick, mode, min_comp, tuple(ratings), min_conf, top)
            st.caption(f"📅 日期回顧:顯示 **{_spick}** 當日快照的排名 (非最新);"
                       "與『雙確認精選/全市場掃描』切到同一天即可三邊對照。")
        # 名稱回填:舊快取的 name 欄可能等於代號 → 先用 TEJ 全市場對照 (2,400+ 檔),
        # 再讓 watchlist.txt 的自訂股名覆蓋 (例 2330 → 台積電)。
        if df is not None and not df.empty and "stock_id" in df.columns and "name" in df.columns:
            _nmap = {**tej_stock_names(), **watchlist_names()}
            if _nmap:
                df = df.copy()
                df["name"] = [_nmap.get(str(sid), nm) for sid, nm in zip(df["stock_id"], df["name"])]
        if df is None or df.empty:
            st.info("沒有符合條件的個股 —— 放寬門檻或評級再試。")
        else:
            # ---- 整體推薦 Top 10:收斂視圖 (理由 + main.py 同款交易計畫) ----
            # 兩道推薦閘門 (完整名單不篩,下方表格照列):
            #   1. 可行動評級:只留『強勢買進 / 強烈推薦』——『觀望追蹤』是訊號不足/偏貴先看不買,
            #      不該當推薦第一名 (如豐祥昂貴、新紡動能弱皆為觀望追蹤)。
            #   2. 法人淨買確認:排除法人沒在買的檔 (whale 維市值中性、薄量股會失真,如 1256/新紡)。
            _ACTIONABLE = ("強勢買進", "強烈推薦")
            _inst_col = "inst_participation" in df.columns and df["inst_participation"].notna().any()
            _reco = df[df["rating"].isin(_ACTIONABLE)] if "rating" in df.columns else df
            _rating_held = len(df) - len(_reco)
            if _inst_col:
                _reco = _reco[_reco.apply(_inst_buying, axis=1)]
            _inst_held = len(df) - _rating_held - len(_reco)
            st.markdown("#### 🎯 整體推薦 Top 10（可行動評級＋法人淨買確認，含理由與價位參考）")
            _has_plan = "atr" in df.columns and df["atr"].notna().any()
            if not _has_plan:
                st.caption("ℹ️ 目前 scores 快取尚未含價量結構欄位 → 交易計畫顯示為『資料不足』。"
                           "請在專案根目錄重跑 `python build_cache.py --build-scores` 後按上方『重新載入快取』。")
            if _rating_held or (_inst_col and _inst_held):
                st.caption(f"🛡️ 已從推薦排除:{_rating_held} 檔非可行動評級 (觀望追蹤/謹慎避開)"
                           + (f"、{_inst_held} 檔法人沒在買 (占比 <{_INST_MIN_PARTICIPATION:.0f}% 或無吸籌持續性)"
                              if _inst_col else "")
                           + "。完整名單仍列於下方。")
            for _i, (_, _r) in enumerate(_reco.head(10).iterrows(), 1):
                _nm = _r.get("name", "") or _r.get("stock_id", "")
                _extra = (f"綜合分 <b>{float(_r['composite']):.1f}</b>"
                          f"（名單百分位 {float(_r.get('pct_rank', 0)):.0f}）")
                _reason = _reason_line_screen(_r)
                _inote = _inst_note(_r)
                if _inote:
                    _reason = f"{_reason}　🏦 {_inote}" if _reason else f"🏦 {_inote}"
                _render_reco_card(_i, _r.get("stock_id", ""), _nm, _r.get("rating", ""),
                                  _extra, _reason, _trade_plan_lines_from_row(_r))
                st.divider()
            st.caption("上表為『可行動評級 (強勢買進/強烈推薦) 且 法人淨買確認』中綜合分最高的前 10。"
                       "法人確認用原始法人占比/連買/淨流向 (非 whale 維,後者市值中性、薄量股會失真)；"
                       "交易計畫為規則換算的價位參考、非投資建議。")
            st.markdown("##### 完整名單")

            # 法人淨買標記 (供完整名單一眼辨識推薦是否被閘門擋下)
            if _inst_col:
                df = df.copy()
                df["法人淨買"] = ["✅" if _inst_buying(r) else "—" for _, r in df.iterrows()]
            # 缺漏資料欄:空 = 資料齊 (顯示 ✅),有值 = 缺哪些 (信心也已對應扣分)
            if "data_gaps" in df.columns:
                df["缺漏資料"] = ["✅ 齊" if not str(g or "").strip() else str(g)
                                  for g in df["data_gaps"]]
            disp = df.rename(columns={
                "stock_id": "代號", "name": "名稱", "as_of": "基準日",
                "composite": "綜合分", "pct_rank": "百分位",
                "rating": "評級", "fundamental": "基本面", "valuation": "估值",
                "technical": "技術", "momentum": "動能", "whale": "籌碼",
                "valuation_status": "估值狀態", "data_confidence": "信心",
                "dyn_weight": "動態權重",
                "inst_participation": "法人占比%", "foreign_flow": "外資淨買(張)",
                "trust_flow": "投信淨買(張)", "foreign_buy_days": "外資連買",
                "trust_buy_days": "投信連買",
            })
            for col in ("基本面", "估值", "技術", "動能", "籌碼", "法人占比%",
                        "外資淨買(張)", "投信淨買(張)"):
                if col in disp.columns:
                    disp[col] = disp[col].round(0)
            if "綜合分" in disp.columns:
                disp["綜合分"] = disp["綜合分"].round(1)
            order = ["代號", "名稱", "評級", "綜合分", "百分位",
                     "基本面", "估值", "技術", "動能", "籌碼",
                     "法人淨買", "法人占比%", "外資淨買(張)", "投信淨買(張)",
                     "外資連買", "投信連買",
                     "估值狀態", "信心", "缺漏資料", "動態權重", "基準日"]
            disp = disp[[c for c in order if c in disp.columns]]
            st.dataframe(disp, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ 下載結果 (CSV)",
                data=disp.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"screen_{mode}_{info['as_of']}.csv",
                mime="text/csv")
            st.caption("綜合分 = 五維加權;百分位 = 該檔綜合分在此名單內的橫斷面排名 (越高越前)。"
                       "信心 = 資料完整度 (原始資料集每缺一類 −8、估值鏡頭每缺一角 −5);"
                       "『缺漏資料』標出實際缺哪些 (齊全顯示 ✅)。此頁純讀快取。")

# ------------------------------------------------------------------ 全市場掃描
_UNIV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "universe_pool")
_ARMS = {"value_ind_pct_pool_pct": "便宜", "momentum20_pool_pct": "動能",
         "chip20_turnover_pool_pct": "籌碼", "high52_prox_pool_pct": "突破",
         "rev_accel_pool_pct": "營收加速"}


@st.cache_data(show_spinner=False)
def _univ_load(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"stock_id": str}).set_index("stock_id")


@st.cache_data(show_spinner=False)
def _univ_streaks(files: tuple) -> dict:
    sets = [set(_univ_load(f).index) for f in files]
    latest = sets[-1] if sets else set()
    out = {}
    for sid in latest:
        n = 0
        for s in reversed(sets):
            if sid in s:
                n += 1
            else:
                break
        out[sid] = n
    return out


# 本機價格快取路徑 (與『實戰演練』同源):有 → Top-10 現算完整交易計畫;無 (雲端) → 粗略讀。
_UNIV_TEJ = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
_UNIV_SNAP = os.path.join(os.path.expanduser("~"), "market_cache", "price_valuation_daily")


def _has_local_price_cache() -> bool:
    import glob as _g
    return (os.path.isdir(_UNIV_TEJ) and bool(_g.glob(os.path.join(_UNIV_TEJ, "*.parquet")))) or \
           (os.path.isdir(_UNIV_SNAP) and bool(_g.glob(os.path.join(_UNIV_SNAP, "*.parquet"))))


@st.cache_data(show_spinner=False)
def _univ_price_hist(sid: str, as_of: str) -> pd.DataFrame:
    """單檔日線 (TEJ 種子的全市場逐檔 parquet,date<=as_of)。0 API、冷門股也涵蓋。
    交易計畫只需價格衍生結構 (ATR/MA20/量價分布),故不必組完整 HistoryBundle。"""
    f = os.path.join(_UNIV_TEJ, f"{sid}.parquet")
    if not os.path.exists(f):
        return pd.DataFrame()
    try:
        cols = ["date", "open", "max", "min", "close", "Trading_Volume"]
        d = pd.read_parquet(f, columns=cols)
    except Exception:
        return pd.DataFrame()
    d = d[d["date"] <= as_of].sort_values("date")
    return d.rename(columns={"Trading_Volume": "volume"})


def _univ_trade_plans(sids: tuple, as_of: str, closes: tuple) -> dict:
    """本機:對 Top-10 從 TEJ 逐檔日線現算完整交易計畫 (0 API)。
    ATR/MA20/量價成本區用 core.technical_analysis (與 build_pit_stockdata 同一套);
    current_price 用 shortlist 當日收盤 (closes 對齊 sids)。抓不到歷史的檔回傳缺 → 面板退粗略讀。"""
    out: dict = {}
    try:
        from core.technical_analysis import TechnicalEngine as _TA
    except Exception:
        return out
    close_map = dict(zip(sids, closes))
    for sid in sids:
        h = _univ_price_hist(sid, as_of)
        if h.empty or len(h) < 30:
            continue
        try:
            vp = _TA.calculate_volume_profile(h.copy())
            atr = _TA.calculate_atr(h, 14)
            ma20 = pd.to_numeric(h["close"], errors="coerce").rolling(20).mean().iloc[-1]
            price = close_map.get(sid) or float(pd.to_numeric(h["close"]).iloc[-1])
            ns = SimpleNamespace(
                current_price=price, atr=(atr or None),
                value_area_low=vp.get("val"), value_area_high=vp.get("vah"),
                cost_zone_poc=vp.get("poc"), cost_zone_support=vp.get("support"),
                cost_zone_resistance=vp.get("resistance"),
                ma20=(float(ma20) if pd.notna(ma20) else None))
            out[sid] = format_plan_lines(build_trade_plan(ns))
        except Exception:
            continue
    return out


def _univ_reason(row) -> str:
    """全市場掃描的白話理由:掛哪些臂 + C2 成分讀值 (動能低是 C2 偏好,非缺點)。"""
    bits = []
    arms = str(row.get("來源臂", "") or "").strip()
    if arms:
        bits.append(f"臂：{arms}")
    detail = []
    _pairs = [("value_ind_pct", "產業內便宜位階 {:.0f}"), ("high52_prox", "距52週高 {:.0f}"),
              ("revenue_yoy", "營收YoY {:+.0f}%"), ("momentum20", "20日動能 {:+.0f}%")]
    for col, fmt in _pairs:
        v = row.get(col)
        if pd.notna(v):
            detail.append(fmt.format(float(v)))
    if detail:
        bits.append(" · ".join(detail))
    return "　".join(bits)


def _cheap_trap_flag(arms: str) -> str:
    """便宜臂旗標 (Part 4 實證:便宜臂整體 excess −2~−3%;久居便宜臂中位原地踏步)。
    僅便宜臂 → 最該警示;含便宜但另有強臂 → 次級提醒。"""
    parts = [a for a in str(arms).split("+") if a]
    if "便宜" not in parts:
        return ""
    return "僅便宜臂" if parts == ["便宜"] else "含便宜臂"


def _rc_label(rc: str) -> str:
    return "C2排序分" if rc == "c2_score" else "composite"


def _univ_coarse_note(row) -> str:
    """雲端 / 抓不到本機價格時的粗略位置判讀 (用 shortlist 現有欄,非精確價位)。"""
    h52 = row.get("high52_prox")
    vind = row.get("value_ind_pct")
    notes = []
    if pd.notna(h52):
        h = float(h52)
        if h >= 95:
            notes.append(f"貼近52週高（{h:.0f}）→ 追價風險大，等回檔")
        elif h >= 85:
            notes.append(f"距52週高 {h:.0f}，位置偏高")
        elif h <= 60:
            notes.append(f"距52週高僅 {h:.0f}，深跌區、留意接落刀")
        else:
            notes.append(f"距52週高 {h:.0f}，中段")
    if pd.notna(vind) and float(vind) > 85:
        notes.append("產業內偏便宜（便宜≠好，見使用說明）")
    base = "；".join(notes) if notes else "位置資料不足"
    return f"位置參考：{base}。精確進場/停損/目標請把代號貼到『個股分析』深評。"


with tab_univ:
    import glob as _glob
    _files = sorted(_glob.glob(os.path.join(_UNIV_DIR, "shortlist_*.csv")))
    if not _files:   # 雲端部署沒有 outputs/ → 退回 repo 內的 cloud_cache 快照
        _files = sorted(_glob.glob(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "cloud_cache", "UniversePool",
            "shortlist_*.csv")))
    if not _files:
        st.info("找不到 shortlist 檔案。此分頁讀本機每日粗篩產出 (`outputs/universe_pool/`),"
                "由排程 Market_SnapshotCollector 每早自動生成;歷史可用 "
                "`python scripts/universe_screen_backfill.py` 回補。")
    else:
        _dates = [os.path.basename(f)[10:-4] for f in _files]
        _pick = st.selectbox("資料日", _dates[::-1], index=0)
        _f = _files[_dates.index(_pick)]
        _df_raw = _univ_load(_f)
        _rc = "c2_score" if "c2_score" in _df_raw.columns else "composite"   # 舊檔無 c2_score 回退
        _df = _df_raw.sort_values(_rc, ascending=False)
        _streaks = _univ_streaks(tuple(_files[: _dates.index(_pick) + 1][-40:]))

        _data_dir = os.path.dirname(_f)
        _pool_f = os.path.join(_data_dir, f"pool_{_pick}.csv")
        if os.path.exists(_pool_f):
            _p1 = pd.read_csv(_pool_f, nrows=1)
            if "bear_regime" in _p1.columns and bool(_p1["bear_regime"].iloc[0]):
                st.warning("⚠️ 市場 regime:空頭 —— 歷史上此狀態 shortlist 超額為負,參考性降低"
                           " (詳見 DevLog §16-D)。")

        _df["來源臂"] = ["+".join(lbl for c, lbl in _ARMS.items()
                                   if c in _df.columns and pd.notna(_df.loc[i, c]) and _df.loc[i, c] > 85)
                         for i in _df.index]
        _df["連續在榜"] = [_streaks.get(i, 1) for i in _df.index]
        _prev_idx = _dates.index(_pick) - 1
        _new50 = set(_df.head(50).index)
        if _prev_idx >= 0:
            _prev_df = _univ_load(_files[_prev_idx])
            _prev_rc = "c2_score" if "c2_score" in _prev_df.columns else "composite"
            _new50 -= set(_prev_df.sort_values(_prev_rc, ascending=False).head(50).index)

        # 便宜臂旗 / 新進旗 (供表格與面板共用)
        _df["陷阱旗"] = [_cheap_trap_flag(a) for a in _df["來源臂"]]
        _df["新進"] = ["🆕" if i in _new50 else "" for i in _df.index]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("shortlist 檔數", len(_df))
        c2.metric("新進前 50", len(_new50))
        c3.metric("連續在榜 ≥5 天", int((_df["連續在榜"] >= 5).sum()))
        c4.metric("歷史資料天數", len(_files))

        # ---- 整體推薦 Top 10 (依 C2 排序分;理由 + 交易計畫) ----
        # 純便宜修正 (Part 4 實證『便宜單臂 −2~−3%』):Top-10 資格閘 —— 排除『僅便宜臂』,
        # 且要求一條確認腿 (營收未衰退 revenue_yoy>0,或掛 ≥2 條臂)。只篩推薦卡,完整表格不動。
        def _arm_count(a) -> int:
            return len([x for x in str(a or "").split("+") if x])
        _yoy = pd.to_numeric(_df["revenue_yoy"], errors="coerce") if "revenue_yoy" in _df.columns \
            else pd.Series(index=_df.index, dtype=float)
        _eligible = (_df["陷阱旗"] != "僅便宜臂") & (
            (_yoy > 0) | (_df["來源臂"].apply(_arm_count) >= 2))
        _held = int((~_eligible).sum())
        st.markdown(f"#### 🌐 整體推薦 Top 10（依 {'C2排序分' if _rc == 'c2_score' else 'composite'}，含理由與價位）")
        _top10 = _df[_eligible].head(10)
        if _held:
            st.caption(f"🛡️ 已從推薦排除 {_held} 檔『純便宜/無確認腿』候選（仍列於下方完整表格）："
                       "進榜需非僅便宜臂，且營收未衰退或另掛第二條臂。")
        _local = _has_local_price_cache()
        _plans = (_univ_trade_plans(tuple(_top10.index), _pick,
                                    tuple(_top10["close"] if "close" in _top10 else []))
                  if _local else {})
        if _local:
            st.caption(f"✅ 本機價格快取可用：Top-10 現算完整價位（0 API，量價結構來自 TEJ 日線；"
                       f"其中 {len(_plans)}/{len(_top10)} 檔有足量歷史，其餘退粗略讀）。")
        else:
            st.caption("ℹ️ 未偵測到本機價格快取（雲端）：Top-10 顯示粗略位置判讀；精確價位請把代號貼到"
                       "『個股分析』深評。")
        for _i, (_sid, _r) in enumerate(_top10.iterrows(), 1):
            _nm = _r.get("name", "")
            _tags = " ".join(t for t in (_r.get("新進", ""),
                                         ("⚠️" + _r["陷阱旗"] if _r.get("陷阱旗") else "")) if t)
            _extra = f"{_rc_label(_rc)} <b>{float(_r[_rc]):.1f}</b>　{_tags}"
            _plan_lines = _plans.get(_sid)
            if not _plan_lines:                       # 雲端 / 本機抓不到 → 粗略位置讀
                _plan_lines = [_univ_coarse_note(_r)]
            _render_reco_card(_i, _sid, _nm, "", _extra, _univ_reason(_r), _plan_lines)
            st.divider()
        st.caption("排序=C2排序分（產業內估值+營收YoY+52週高−動能，寬池六時代IC全正）；推薦已排除"
                   "『僅便宜臂且無確認腿』（Part 4 實證便宜單臂相對落後 −2~−3%）；⚠️含便宜臂=仍帶便宜腿但另有強臂；"
                   "🆕=今日新進。此頁為分流參考、非投組。")

        _arm_sel = st.multiselect("來源臂 (留空=全部)", list(_ARMS.values()), default=[])
        _c1, _c2 = st.columns(2)
        _streak_min = _c1.slider("連續在榜 ≥ N 天", 1, 20, 1)
        _ind_sel = _c2.multiselect("產業 (留空=全部)",
                                    sorted(_df["industry"].dropna().unique()) if "industry" in _df.columns else [])

        _v = _df
        if _arm_sel:
            _v = _v[_v["來源臂"].apply(lambda a: any(x in a for x in _arm_sel))]
        _v = _v[_v["連續在榜"] >= _streak_min]
        if _ind_sel and "industry" in _v.columns:
            _v = _v[_v["industry"].isin(_ind_sel)]

        _cols = [c for c in ("name", "industry", "close", _rc, "composite",
                              "新進", "來源臂", "陷阱旗", "連續在榜",
                              "value_ind_pct", "revenue_yoy", "high52_prox", "momentum20",
                              "chip20_turnover", "rev_accel", "adv20") if c in _v.columns]
        _disp = _v[_cols].sort_values(_rc, ascending=False).rename(columns={
            "name": "名稱", "industry": "產業", "close": "收盤",
            "c2_score": "C2排序分", "composite": "舊5F(對照)",
            "value_ind_pct": "產業內便宜", "revenue_yoy": "營收YoY",
            "momentum20": "20日動能%", "chip20_turnover": "法人流向",
            "high52_prox": "距52週高%", "rev_accel": "營收加速", "adv20": "20日均額"})
        st.dataframe(_disp.round(2), use_container_width=True, height=520)
        _new_rows = _df.loc[sorted(_new50)]
        if len(_new_rows):
            st.markdown(f"#### 🆕 今日新進 {'C2排序分' if _rc == 'c2_score' else 'composite'} 前 50")
            st.dataframe(_new_rows[_cols].rename(columns={
                "name": "名稱", "industry": "產業", "c2_score": "C2排序分",
                "composite": "舊5F(對照)"}).round(2),
                         use_container_width=True)
        _digest_f = os.path.join(_data_dir, f"digest_{_pick}.md")
        if os.path.exists(_digest_f):
            with st.expander("📄 當日文字摘要 (digest)"):
                st.markdown(open(_digest_f, encoding="utf-8").read())
        st.caption("資料=TWSE/TPEx 官方快照+TEJ 種子 (0 FinMind);L0-L2 粗篩後五因子聯集圈人,"
                   "排序=C2排序分 (產業內估值+營收YoY+52週高點−20日動能,寬池驗證六時代IC全正,"
                   "見 DevLog §19);舊5F(對照)為聯集用的召回因子平均,寬池排序力≈0僅供對照。"
                   "**分流參考,非投組**;個股請至『個股分析』深評。")
        st.caption("『連續在榜』是顯示用、**不是驗證過的訊號**:Part 4 回測 (streak_return_lab) 顯示"
                   "在榜天數對相對報酬幾乎無預測力 (excess t<1.4),越久≠越好也≠越差,排序請看 C2 而非榜齡。"
                   "詳見『使用說明 → 連續在榜越久越好嗎?』。")

# ------------------------------------------------------------------ 雙確認精選 (c2 ∩ 綜合分)
_FUSION_PCT = 20   # 各取前 N%%;回測甜蜜點 (regime_switch_lab):全期 excess +1.04%/月 t5.3、~25檔、2022不翻車
with tab_fusion:
    st.markdown("### ✨ 雙確認精選（全市場掃描 c2 × 綜合分 同時看好）")
    st.caption(
        f"同時落在『c2 前 {_FUSION_PCT}%』且『綜合分前 {_FUSION_PCT}%』的股 —— 兩套**幾乎獨立**(排序相關 +0.18、"
        f"名單重疊僅 12%) 的視角一致認可。回測 (2005-2026,proxy):全期 excess **+1.04%/月 (t5.3)**、"
        f"多頭 +1.36%;因 c2 認可自動濾掉純動能股,**2022 空頭不像純綜合分翻車**。"
        f"⚠️ 集中約 20-30 檔、高信心高波動;**分流參考、非投資建議**。")
    import glob as _gf
    _pf = sorted(_gf.glob(os.path.join(_UNIV_DIR, "pool_*.csv"))) or \
        sorted(_gf.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "cloud_cache", "UniversePool", "pool_*.csv")))
    _pool_dates = [os.path.basename(f)[5:-4] for f in _pf]           # pool_{date}.csv
    _score_dates = set(score_store.as_of_dates(mode))
    _fusion_dates = [d for d in _pool_dates if d in _score_dates]     # 兩邊當天都有資料才能比對

    if not _pf:
        st.info("找不到 pool_*.csv (c2 來源)。由每日粗篩產出,可用 universe_screen_backfill.py 回補。")
    elif not _fusion_dates:
        st.info("找不到『pool 快照』與『綜合分 scores』同一天都有資料的日期,無法比對。"
                "先跑 `python build_cache.py --build-scores` 補齊綜合分快取。")
    else:
        _fpick = st.selectbox("資料日(日期回顧)", _fusion_dates[::-1], index=0,
                              help="事後核對某一天的雙確認名單用;預設為最新一天,可切回過去任一天比對。")
        _dfc = score_store.screen_by_composite_at(_fpick, mode=mode, top=3000)  # 綜合分排名 (該日 pool,含 pct_rank)
        _pool = pd.read_csv(_pf[_pool_dates.index(_fpick)], dtype={"stock_id": str})
        if _dfc is None or _dfc.empty:
            st.info("該日綜合分快取為空,無法比對。")
        elif "c2_score" not in _pool.columns:
            st.info("pool 檔無 c2_score (舊格式);請重跑 scripts/universe_screen_daily.py。")
        else:
            _pool["c2_pct"] = _pool["c2_score"].rank(pct=True) * 100.0
            _dfc = _dfc.copy()
            _dfc["c2_pct"] = _dfc["stock_id"].map(dict(zip(_pool["stock_id"], _pool["c2_pct"])))
            _thr = 100.0 - _FUSION_PCT
            _fus = _dfc[(_dfc["pct_rank"] >= _thr) & (_dfc["c2_pct"] >= _thr)].copy()
            _fus = _fus.sort_values("composite", ascending=False)
            _nmap = {**tej_stock_names(), **watchlist_names()}
            if _nmap and "name" in _fus.columns:
                _fus["name"] = [_nmap.get(str(s), n) for s, n in zip(_fus["stock_id"], _fus["name"])]
            # 閘門:可行動評級 + 法人淨買 (與綜合分頁一致)
            _ACT = ("強勢買進", "強烈推薦")
            _inst_ok = "inst_participation" in _fus.columns and _fus["inst_participation"].notna().any()
            _reco = _fus[_fus["rating"].isin(_ACT)] if "rating" in _fus.columns else _fus
            if _inst_ok:
                _reco = _reco[_reco.apply(_inst_buying, axis=1)]
            st.markdown(f"雙確認共 **{len(_fus)}** 檔（c2 前 {_FUSION_PCT}% ∩ 綜合分前 {_FUSION_PCT}%）；"
                        f"再套可行動評級+法人淨買 → **{len(_reco)}** 檔可行動。")
            if _reco.empty:
                st.info("目前沒有『雙確認 + 可行動 + 法人在買』的個股 —— 空頭時常見(綜合分前段縮水),"
                        "這時回歸『🌐 全市場掃描 c2』較穩。")
            else:
                for _i, (_, _r) in enumerate(_reco.head(15).iterrows(), 1):
                    _nm = _r.get("name", "") or _r.get("stock_id", "")
                    _extra = (f"綜合分 <b>{float(_r['composite']):.1f}</b>（前{100 - float(_r['pct_rank']):.0f}%）"
                              f"　c2 前 {100 - float(_r['c2_pct']):.0f}%　🔁雙確認")
                    _reason = _reason_line_screen(_r)
                    _in = _inst_note(_r)
                    if _in:
                        _reason = f"{_reason}　🏦 {_in}" if _reason else f"🏦 {_in}"
                    _render_reco_card(_i, _r.get("stock_id", ""), _nm, _r.get("rating", ""),
                                      _extra, _reason, _trade_plan_lines_from_row(_r))
                    st.divider()
            # 完整雙確認名單
            st.markdown("##### 完整雙確認名單")
            _fus["c2前%"] = (100.0 - _fus["c2_pct"]).round(0)
            _fus["綜合前%"] = (100.0 - _fus["pct_rank"]).round(0)
            if "data_gaps" in _fus.columns:
                _fus["缺漏"] = ["✅" if not str(g or "").strip() else str(g) for g in _fus["data_gaps"]]
            _fd = _fus.rename(columns={
                "stock_id": "代號", "name": "名稱", "composite": "綜合分", "rating": "評級",
                "fundamental": "基本面", "valuation": "估值", "technical": "技術",
                "momentum": "動能", "whale": "籌碼", "valuation_status": "估值狀態",
                "data_confidence": "信心", "inst_participation": "法人占比%"})
            for _c in ("綜合分", "基本面", "估值", "技術", "動能", "籌碼", "法人占比%"):
                if _c in _fd.columns:
                    _fd[_c] = _fd[_c].round(0 if _c != "綜合分" else 1)
            _ford = ["代號", "名稱", "評級", "綜合分", "綜合前%", "c2前%",
                     "基本面", "估值", "技術", "動能", "籌碼", "法人占比%",
                     "估值狀態", "信心", "缺漏"]
            _fd = _fd[[c for c in _ford if c in _fd.columns]]
            st.dataframe(_fd, use_container_width=True, hide_index=True)
            st.caption("雙確認 = c2(反動能/價值·全天候) 與 綜合分(順動能/品質·多頭強) 兩套獨立排序都進前段。"
                       "回測甜蜜點取各前 20%(t 最穩、約 25 檔、2022 不翻車)。空頭時此名單會自然縮水 → "
                       "回歸全市場掃描 c2。**非投資建議,個股請至『個股分析』深評。**")

# ------------------------------------------------------------------ 實戰演練
_HOME = os.path.expanduser("~")
_PLAN_TEJ = os.path.join(_HOME, "tej_cache", "price_valuation")
_PLAN_SNAP = os.path.join(_HOME, "market_cache", "price_valuation_daily")
_PLAN_0050 = os.path.join(_HOME, "finmind_cache", "TaiwanStockPrice", "0050.parquet")


@st.cache_data(show_spinner=False, ttl=3600)
def _plan_prices(sids: tuple, start: str) -> pd.DataFrame:
    """演練標的日線 (TEJ 種子 ∪ 官方快照,0 API)。"""
    import glob as _g
    frames = []
    for sid in sids:
        f = os.path.join(_PLAN_TEJ, f"{sid}.parquet")
        if os.path.exists(f):
            d = pd.read_parquet(f, columns=["stock_id", "date", "open", "close"])
            frames.append(d[d["date"] >= start])
    tej_max = max((f["date"].max() for f in frames if len(f)), default="")
    for sf in sorted(_g.glob(os.path.join(_PLAN_SNAP, "*.parquet"))):
        _d = os.path.basename(sf)[:-8]
        if _d > tej_max and _d >= start:
            d = pd.read_parquet(sf, columns=["stock_id", "date", "open", "close"])
            frames.append(d[d["stock_id"].isin(sids)])
    if not frames:
        return pd.DataFrame()
    px = pd.concat(frames, ignore_index=True).drop_duplicates(["stock_id", "date"])
    return px.sort_values(["stock_id", "date"])


@st.cache_data(show_spinner=False, ttl=3600)
def _plan_bench(start: str) -> pd.DataFrame:
    """0050 基準 (自動還原分割,同 portfolio_simulator_lab)。"""
    if not os.path.exists(_PLAN_0050):
        return pd.DataFrame()
    d = pd.read_parquet(_PLAN_0050)[["date", "close"]].sort_values("date").reset_index(drop=True)
    r = d["close"].pct_change()
    for i in d.index[r < -0.5]:
        ratio = round(d.loc[i - 1, "close"] / d.loc[i, "close"])
        if ratio >= 2:
            d.loc[:i - 1, "close"] /= ratio
    return d[d["date"] >= start]


with tab_drill:
    import glob as _glob
    st.markdown("#### 📋 30 天實戰演練 — plan 操作卡 × 實際成交對帳")
    _plan_files = sorted(_glob.glob(os.path.join(_UNIV_DIR, "plan_*.csv")))
    if not _plan_files:
        st.info("找不到 plan 操作卡。先執行 `python scripts/portfolio_simulator_lab.py --plan` "
                "產生 `outputs/universe_pool/plan_{date}.csv`。")
    else:
        _pdates = [os.path.basename(f)[5:-4] for f in _plan_files]
        _ppick = st.selectbox("操作卡 (凍結日)", _pdates[::-1], index=0)
        _plan = pd.read_csv(_plan_files[_pdates.index(_ppick)], dtype={"stock_id": str})
        st.caption(f"規則 (DevLog §22 判定):**T+1 開盤整批買進** (預估 {_plan['entry_date_est'].iloc[0]})"
                   f" → 持有至**季度再平衡** ({_plan['exit_window'].iloc[0]});"
                   "買進區間=凍結收盤×歷史隔夜跳空 p10~p90,開盤落帶外屬正常,不建議等價錯過進場。")

        # --- 成交紀錄回填 (存 fills_{date}.csv;WP1-1 schema 含買進側＋賣出側) ---
        # schema 定案:買賣同表 (單一 editor、原子儲存),不拆獨立 sells_{date}.csv。
        _fills_f = os.path.join(_UNIV_DIR, f"fills_{_ppick}.csv")
        _SELL_COLS = {"sell_date": "", "sell_price": float("nan"), "sell_reason": ""}
        if os.path.exists(_fills_f):
            _fills = pd.read_csv(_fills_f, dtype={"stock_id": str})
        else:
            _fills = _plan[["stock_id", "name", "frozen_close",
                            "buy_low", "buy_ref", "buy_high"]].copy()
            _fills["fill_date"] = ""
            _fills["fill_price"] = float("nan")
            _fills["shares"] = float("nan")
        for _c, _default in _SELL_COLS.items():     # 舊檔 (賣出側前) 向後相容:缺欄補上
            if _c not in _fills.columns:
                _fills[_c] = _default
        # WP1-2 DateColumn 需 date/datetime 型別:磁碟載入的日期是字串、新檔初值是 ""——
        # 皆為 STRING kind,直接餵 DateColumn 會 StreamlitAPIException。先 coerce 成
        # datetime64 (空值→NaT),元件才收得下;儲存時再格式化回乾淨 YYYY-MM-DD 字串。
        for _c in ("fill_date", "sell_date"):
            _fills[_c] = pd.to_datetime(_fills[_c], errors="coerce")
        st.markdown("##### ① 回填實際成交 (買進填 fill_date / fill_price,股數選填;賣出時填 sell_*)")
        _edited = st.data_editor(
            _fills, num_rows="fixed", use_container_width=True, key=f"fills_{_ppick}",
            disabled=["stock_id", "name", "frozen_close", "buy_low", "buy_ref", "buy_high"],
            column_config={
                # WP1-2 輸入硬化:日期改 DateColumn — TextColumn 下格式 typo 會被 len>=8 靜默踢出追蹤,
                # 對帳樣本缺損不可察覺;DateColumn 由元件層強制合法日期。
                "fill_date": st.column_config.DateColumn("fill_date", format="YYYY-MM-DD"),
                "fill_price": st.column_config.NumberColumn("fill_price", format="%.2f"),
                "shares": st.column_config.NumberColumn("shares (選填)"),
                "sell_date": st.column_config.DateColumn("sell_date", format="YYYY-MM-DD"),
                "sell_price": st.column_config.NumberColumn("sell_price", format="%.2f"),
                "sell_reason": st.column_config.TextColumn("sell_reason (季度再平衡/掉出top8/停損)")})
        if st.button("💾 儲存成交紀錄"):
            _save = _edited.copy()
            for _c in ("fill_date", "sell_date"):    # datetime64 → 乾淨 YYYY-MM-DD / 空字串,維持磁碟格式穩定
                _save[_c] = pd.to_datetime(_save[_c], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
            _save.to_csv(_fills_f, index=False, encoding="utf-8-sig")
            st.success(f"已存 {_fills_f}")

        # --- WP1-3 追蹤來源改「磁碟 fills_{date}.csv 優先」 ---
        # 消除 _edited 即時態「未存檔也追蹤、重整即遺失」歧義:追蹤/對帳一律讀已落地的磁碟檔,
        # 未按儲存的編輯不進追蹤 (對帳證據鏈只認存檔事實)。
        if os.path.exists(_fills_f):
            _track = pd.read_csv(_fills_f, dtype={"stock_id": str})
            for _c, _default in _SELL_COLS.items():
                if _c not in _track.columns:
                    _track[_c] = _default
            st.caption("ℹ️ 追蹤與對帳以**磁碟 fills 檔**為準 (上方編輯需按『儲存』後才納入)。")
        else:
            _track = _edited.copy()
            st.caption("ℹ️ 尚未儲存 fills 檔:以下追蹤暫用當前編輯內容,請按上方『儲存』落地以免重整遺失。")

        # WP1-2 日期改 datetime 型別 (取代 len>=8 字串長度啟發);coerce 後 notna 才算有效成交
        _track["_fill_dt"] = pd.to_datetime(_track["fill_date"], errors="coerce")
        _track["_sell_dt"] = pd.to_datetime(_track["sell_date"], errors="coerce")

        # WP1-2 fill_price sanity check:核對「成交日當天實際市價」而非凍結收盤。
        # 凍結收盤帶在除權息日會系統性誤判——T+1 若除權息,開盤參考價重設,合法成交會遠低於
        # 凍結收盤 (例:378 → 除權後 ~261),舊版誤報「疑似輸入錯誤」。真正要抓的是打錯價
        # (漏小數點/貼錯欄/貼錯股),其唯一可靠 oracle 是成交日當天的實際成交價區間:除權息後的
        # 實際開/收盤已是重設後價位,合法成交自然吻合,只有 typo 才會偏離。市價未入快取才退回凍結帶。
        _px = _plan_prices(tuple(_plan["stock_id"]), _ppick)
        _filled = _track[_track["fill_price"] > 0].copy()
        if not _filled.empty:
            _MKT_MARGIN = 0.15                       # 當日 open/close 區間再放寬 ±15% (吸收盤中波動/漲跌停)
            _pxi = _px.set_index(["stock_id", "date"]) if not _px.empty else None
            _bad_mkt, _bad_frozen = [], []
            for _, r in _filled.iterrows():
                _sid, _fp = str(r["stock_id"]), float(r["fill_price"])
                _fs = r["_fill_dt"].strftime("%Y-%m-%d") if pd.notna(r["_fill_dt"]) else None
                _oc = None
                if _pxi is not None and _fs is not None and (_sid, _fs) in _pxi.index:
                    _mrow = _pxi.loc[(_sid, _fs)]
                    _o, _c = float(_mrow["open"]), float(_mrow["close"])
                    _oc = (min(_o, _c), max(_o, _c))
                if _oc is not None:                  # 有當日市價 → 除權息-proof 比對
                    if _fp < _oc[0] * (1 - _MKT_MARGIN) or _fp > _oc[1] * (1 + _MKT_MARGIN):
                        _bad_mkt.append((r, _oc))
                else:                                # 當日市價未快取 (今日剛成交/假日) → 退回凍結帶,軟提示
                    _bw = abs(float(r["buy_high"]) - float(r["buy_low"]))
                    if _fp < r["buy_low"] - 2 * _bw or _fp > r["buy_high"] + 2 * _bw:
                        _bad_frozen.append(r)
            if _bad_mkt:
                _lst = "、".join(f"{r['stock_id']} {r['name']} 成交{r['fill_price']:.2f}"
                                 f"(當日實際 {oc[0]:.2f}~{oc[1]:.2f})" for r, oc in _bad_mkt)
                st.error(f"⚠️ fill_price 疑似輸入錯誤 (偏離**成交日當天實際市價**逾 ±{_MKT_MARGIN*100:.0f}%):"
                         f"{_lst}。請確認非漏小數點/貼錯欄/貼錯股——錯價會污染滑價與淨額對帳。"
                         f"(已對照當日實際成交價,除權息日的合法成交不會被誤報。)")
            if _bad_frozen:
                _lst = "、".join(f"{r['stock_id']} {r['name']} 成交{r['fill_price']:.2f}"
                                 f"(凍結收盤{r['frozen_close']:.2f})" for r in _bad_frozen)
                st.warning(f"ℹ️ fill_price 偏離凍結收盤逾兩個帶寬,但**當日實際市價尚未入快取,無法核對**:"
                           f"{_lst}。若當日除權息屬正常;待快照更新後會自動改以實際市價複核,"
                           f"或請自行確認非打錯。")

        # --- 追蹤與對帳 ---
        _done = _track[(_track["fill_price"] > 0) & _track["_fill_dt"].notna()].copy()
        if _done.empty:
            st.info("尚未回填任何成交 → 上表填入後按儲存,即開始每日追蹤。")
        else:
            _done["_fill_str"] = _done["_fill_dt"].dt.strftime("%Y-%m-%d")
            if _px.empty:
                st.warning("讀不到本機價格快取 (tej_cache/market_cache),此分頁需在本機執行。")
            else:
                _days = sorted(_px["date"].unique())
                _tdays = [d for d in _days if d > _ppick]      # 凍結日後的交易日
                _n_td = len(_tdays)
                _last = _days[-1]
                _close = _px[_px["date"] == _last].set_index("stock_id")["close"]

                # 進場品質:成交 vs 區間帶 vs 理論 T+1 開盤
                _theo = (_px[_px["date"] == _tdays[0]].set_index("stock_id")["open"]
                         if _tdays else pd.Series(dtype=float))
                _t = _done.set_index("stock_id")
                _t["最新收盤"] = _close.reindex(_t.index)
                # 已實現 (賣出) 者以 sell_price 作為出場價,未賣者用最新收盤
                _sold = _t["sell_price"] > 0
                _t["出場價"] = _t["最新收盤"].where(~_sold, _t["sell_price"])
                _t["狀態"] = _sold.map({True: "已賣出", False: "持有中"})
                _t["帶內"] = ((_t["fill_price"] >= _t["buy_low"])
                              & (_t["fill_price"] <= _t["buy_high"])).map({True: "✓", False: "帶外"})
                _t["滑價vs理論開盤%"] = (_t["fill_price"] / _theo.reindex(_t.index) - 1) * 100

                # WP1-4 記帳改淨額:元大零股 6 折費率;有 shares 走 TWD 精算 (含 NT$1 手續費地板),
                # 無 shares 退回百分比近似 (含買賣總費率)。毛/淨並列,避免系統性高估演練成績。
                _t["毛報酬%"] = (_t["出場價"] / _t["fill_price"] - 1) * 100
                _gross_net_pct = ((_t["出場價"] * (1 - _FEE_SELL_PCT))
                                  / (_t["fill_price"] * (1 + _FEE_BUY_PCT)) - 1) * 100
                _sh = pd.to_numeric(_t["shares"], errors="coerce")
                _buy_amt = _t["fill_price"] * _sh
                _buy_fee = (_buy_amt * _FEE_BROKER_PCT).clip(lower=_FEE_MIN_TWD)
                _exit_amt = _t["出場價"] * _sh
                _sell_fee = (_exit_amt * _FEE_BROKER_PCT).clip(lower=_FEE_MIN_TWD) + _exit_amt * _FEE_TAX_PCT
                _net_twd = (_exit_amt - _sell_fee) - (_buy_amt + _buy_fee)
                _net_ret_twd = _net_twd / (_buy_amt + _buy_fee) * 100
                _has_sh = _sh.notna() & (_sh > 0)
                _t["淨報酬%"] = _net_ret_twd.where(_has_sh, _gross_net_pct)
                _t["實際損益TWD"] = _net_twd.where(_has_sh)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("已進場", f"{len(_t)}/{len(_plan)} 檔")
                c2.metric("凍結日後交易日", f"{_n_td} 天")
                c3.metric("組合報酬 (淨,等權)", f"{_t['淨報酬%'].mean():+.2f}%",
                          delta=f"毛 {_t['毛報酬%'].mean():+.2f}%", delta_color="off")
                _b = _plan_bench(_done["_fill_str"].min())
                if len(_b) > 1:
                    _b_ret = (_b["close"].iloc[-1] / _b["close"].iloc[0] - 1) * 100
                    c4.metric("同期 0050", f"{_b_ret:+.2f}%")

                st.markdown("##### ② 持股追蹤 (淨額含元大零股 6 折實收費用)")
                st.dataframe(_t[["name", "狀態", "fill_date", "fill_price", "帶內", "滑價vs理論開盤%",
                                  "出場價", "毛報酬%", "淨報酬%", "實際損益TWD"]].rename(columns={
                    "name": "名稱", "fill_date": "成交日", "fill_price": "成交價"}).round(2),
                    use_container_width=True)
                st.caption(f"淨額費率:買 {_FEE_BUY_PCT*100:.4f}% / 賣 {_FEE_SELL_PCT*100:.4f}% (含證交稅"
                           f" {_FEE_TAX_PCT*100:.2f}%),單筆手續費地板 NT${_FEE_MIN_TWD:.0f}。"
                           "填 shares 走 TWD 精算 (含地板真實成本),否則走百分比近似。")

                # 淨值曲線 (各股自成交日起,等權;0050 自最早成交日)
                _curves = {}
                for sid, r in _t.iterrows():
                    s = _px[_px["stock_id"] == sid].set_index("date")["close"]
                    s = s[s.index >= str(r["_fill_str"])]
                    if len(s):
                        _curves[sid] = s / r["fill_price"]
                if _curves:
                    _eq = pd.DataFrame(_curves).ffill()
                    _chart = pd.DataFrame({"投組 (等權)": _eq.mean(axis=1)})
                    if len(_b) > 1:
                        _chart["0050"] = _b.set_index("date")["close"] / _b["close"].iloc[0]
                    st.line_chart(_chart)

                # 20 交易日三方對帳
                st.markdown("##### ③ 20 交易日對帳點")
                if _n_td < 20:
                    st.caption(f"再 {20 - _n_td} 個交易日成熟 (預估與 shortlist_ledger 首次 live 對帳同步)。"
                               "屆時此處自動顯示:執行滑價統計、實際 vs 理論 T+1 組合報酬 (毛/淨並列)、vs 回測期望。")
                else:
                    _d20 = _tdays[19]
                    _c20 = _px[_px["date"] == _d20].set_index("stock_id")["close"]
                    _theo_ret = ((_c20.reindex(_t.index) / _theo.reindex(_t.index) - 1) * 100).mean()
                    _act_gross = ((_c20.reindex(_t.index) / _t["fill_price"] - 1) * 100).mean()
                    _act_net = (((_c20.reindex(_t.index) * (1 - _FEE_SELL_PCT))
                                 / (_t["fill_price"] * (1 + _FEE_BUY_PCT)) - 1) * 100).mean()
                    st.markdown(
                        f"- 執行滑價 (成交 vs 理論 T+1 開盤):平均 **{_t['滑價vs理論開盤%'].mean():+.2f}%**\n"
                        f"- 20 日組合報酬:實際毛 **{_act_gross:+.2f}%** / 實際淨 **{_act_net:+.2f}%**"
                        f" vs 理論 T+1 (毛) **{_theo_ret:+.2f}%**\n"
                        f"- 回測期望 (§22):新進榜 20 日均值約 **+1.5%**,8 檔組合標準差約 **±4%**"
                        f" —— 單一 cohort 落在 ±4% 內都屬雜訊範圍,別過度解讀單次結果。")
                st.caption("⚠️ 收盤價未還原除權息,除息日報酬會低估;本分頁為演練追蹤,非投資建議。"
                           "演練考驗的是執行品質與紀律,alpha 的證明靠 ledger 逐月累積 (DevLog §21)。")

# ------------------------------------------------------------------ 使用說明
with tab_help:
    st.subheader("🧭 這個工具是什麼 + 10 個分頁總覽")
    st.markdown(
        "這是一套**選股研究 / 紀律輔助**工具,幫你對台股做多維度評分與排名。**它不預測漲跌、"
        "不是印鈔機**;定位是『幫你有系統地篩、有紀律地追蹤』。十個分頁分三類:\n\n"
        "**A. 即時查單檔(需自己的 FinMind token)**\n"
        "- 🔎 **個股分析**:單檔四維度深評 + 精確買點,即時抓最新資料。\n"
        "- 🏆 **多檔排行**:多檔並排即時比較。\n\n"
        "**B. 讀本機分數快照(0 API、免 token、瞬間出)**\n"
        "- 🎯 **綜合分選股**:整份名單依五維綜合分排名,先海選一輪。\n"
        "- 🌐 **全市場掃描**:C2 排序 + 五來源臂 shortlist,看整體 Top 10。\n"
        "- ✨ **雙確認精選**:同時進 c2 前 20% 與 綜合分前 20% 的交集(附誠實回測)。\n\n"
        "**C. 風控與試算工具(0 API)**\n"
        "- 🏭 **法人流向**:各產業每日法人淨流入(億元 / 占成交額%),可播放、可下鑽成分股。"
        "**描述圖,不是買賣訊號**。\n"
        "- 🚦 **市場燈號**:現在該持有幾成(反應式風控,非預測方向)。\n"
        "- 💰 **定期定額**:試算你 DCA 的真實個人報酬(MWRR),對比 0050。\n"
        "- 📋 **實戰演練**:30 天 plan 操作卡 × 實際成交對帳,練執行紀律。\n"
        "- 📖 **使用說明**:本頁。\n\n"
        "**最重要的一句先講**(細節在最下方『務實用法』):**大盤 0050 很難贏。** 本工具的價值是"
        "『在你能承受的小部分資金上,有紀律地選股與控風險』,不是取代 0050。")
    st.divider()

    st.subheader("🔑 如何取得 FinMind API token（即時分頁必備）")
    st.markdown(
        "『個股分析』與『多檔排行』分頁會即時向 **FinMind**（台股開源金融資料 API）抓最新資料，"
        "需要一組**你自己的** token。免費、用 Email 註冊就有，一組 token 一分鐘內就能拿到:\n\n"
        "1. 開啟 FinMind 官網 👉 **https://finmindtrade.com/**\n"
        "2. 點右上角 **登入 / 註冊**,用 Email + 密碼**註冊帳號**,到信箱點驗證信完成啟用。\n"
        "3. 登入後進入**會員中心** 👉 **https://finmindtrade.com/analysis/#/account/user**\n"
        "4. 在頁面上找到 **API Token（api_token 金鑰）**,按複製把整串字複製起來。\n"
        "5. 回到本網站,貼到**左側欄的『你的 FinMind API token』**輸入框即可,下方會顯示「✅ 已使用你的 token」。\n\n"
        "貼上後 token 只存在你這次的瀏覽階段、**算你自己的額度、不會共用、也不會寫入伺服器**。")
    with st.expander("額度限制與常見問題"):
        st.markdown(
            "**各身分的 API 額度(大致)**\n"
            "- **不貼 token(匿名)**:每小時 **300 次**(FinMind 以 IP 計算)。雲端部署對外是"
            "**共用 IP**,這 300 次是整台伺服器共用、會被同 IP 的其他流量一起吃掉,尖峰時很容易"
            "抓不到資料 → 建議貼自己的 token,或改用免 token 的『綜合分選股』分頁。\n"
            "- **免費註冊會員**:每小時約 **600 次**請求,以帳號計算、跟 IP 無關,不會被別人分掉,個人研究用綽綽有餘。\n"
            "- **贊助 / Sponsor 方案**:每小時上限更高,適合大量掃描;詳見官網贊助方案。\n\n"
            "**常見問題**\n"
            "- *貼了 token 還是抓不到?* 先確認 token 有沒有整串複製到、帳號 Email 是否已完成驗證;"
            "短時間查太多檔可能撞到每小時上限,等一小時額度會重置。\n"
            "- *代碼要怎麼填?* 直接填台股代號(例:台積電 `2330`、聯發科 `2454`),多檔用空白或逗號隔開。\n"
            "- *完全不想註冊?* 用『綜合分選股』分頁 —— 它讀本機已建好的 scores 快取、**0 API、免 token**,"
            "只是資料是上次建快取的基準日、不是當下即時價。\n\n"
            "官網:https://finmindtrade.com/　｜　登入說明:https://finmind.github.io/login/")
    st.divider()

    st.subheader("🔢 每檔會用掉多少 API?一次搜幾檔剛好?")
    st.markdown(
        "『個股分析 / 多檔排行』**每分析一檔全新股票**,大約會向 FinMind 送出 **9 支請求**"
        "(股價、法人買賣超、流通股數、融資融券、月營收、本益比河流圖、損益表、資產負債表、現金流量表)。\n\n"
        "不過本系統有**本機快取**:同一檔股票**當天再查幾乎不再耗 API**(直接讀快取),"
        "只有第一次抓、或你勾了左側『刷新最新資料』時才會實際打 API。所以真正會消耗額度的是"
        "**「這一小時內第一次分析的股票檔數」**。\n\n"
        "以**免費註冊會員每小時約 600 次**估算:600 ÷ 9 ≈ **一小時內可全新分析約 60 檔**。據此建議:\n"
        "- **個股分析**:一次輸入 **1～5 檔**最順手,想深入看單檔就直接查。\n"
        "- **多檔排行**:此頁逐檔即時打 API,建議**一次 20 檔以內**、單次盡量**不要超過 30 檔**,"
        "以免逼近每小時上限(30 檔全新 ≈ 270 次)。\n"
        "- **想一次掃描上百檔** → 改用『🎯 綜合分選股』分頁:它讀本機已建好的 scores 快取,"
        "**0 API、免 token、瞬間出結果**,最適合大範圍選股。\n\n"
        "小提醒:若短時間內連續分析大量『沒查過的』新股票而跳出抓不到資料,通常就是撞到每小時上限,"
        "**等一小時額度重置**即可,或先用『綜合分選股』頂著。")
    st.divider()

    st.subheader("三種模式怎麼選")
    st.markdown(
        "- **平衡**(推薦預設):以基本面+技術為核心,最穩、最不被單一雜訊帶走。新手、中線波段。\n"
        "- **保守**:重基本面品質與估值、門檻高;選出的少但扎實,適合長線/存股。\n"
        "- **積極**:重動能與籌碼、門檻低,抓正在噴的股;雜訊與成本最高,適合會停損的短線客。\n\n"
        "模式不設定持有天數 —— 它決定『分數由哪些訊號主導』:動能/籌碼衰退得快 (短線),"
        "基本面/估值走得慢 (長線)。挑跟你實際持有時間相符的模式。")
    st.subheader("四個評級的意思")
    st.markdown(
        "系統有**兩條並行的買進軌道**,不是強弱之分:\n"
        "- **強勢買進 = 順勢動能軌**:正在領漲的主流股 (多頭排列+動能強+法人吸籌),特赦『太貴/過熱』。\n"
        "- **強烈推薦 = 價值/品質軌**:便宜或合理的好公司,基本面扎實、沒過熱、沒追高。\n"
        "- **觀望追蹤**:訊號不足或有疑慮,先追蹤。\n"
        "- **謹慎避開**:基本面或技術面不佳,避開。\n\n"
        "⚠️ **評級不是「現在就買」的指令**,而是對這檔『當前狀態』的分類。"
        "很多『強勢買進』的股票,買點提示會寫『追高、回檔守穩支撐再進』—— "
        "**評級看值不值得擁有,買點提示看該在什麼價位進場**,兩段一起讀。")

    st.divider()
    st.subheader("🎯 『綜合分選股』分頁怎麼用")
    st.markdown(
        "這頁跟『個股分析 / 多檔排行』最大的差別:那兩頁是**即時抓最新資料、一檔一檔算**;"
        "這頁是讀一份**事先算好的分數快照**,把**整份追蹤名單**一次拿來比高下、由高到低排名。"
        "所以它 **0 API、免 token、瞬間出結果**,最適合『先海選一輪』。\n\n"
        "**操作三步驟**\n"
        "1. 左側選好**策略模式**(三個模式各一套權重、各一套分數,換模式排名就會變)。\n"
        "2. 設四個篩選條件:**綜合分下限**(預設=該模式門檻)、**資料信心下限**、**顯示檔數**、"
        "**限定評級**(不選=全部)。\n"
        "3. 看排名表,右下角可**下載 CSV**。想深入某幾檔,再把代號貼到『個股分析』看即時細節。\n\n"
        "**欄位怎麼看**\n"
        "- **綜合分**:五個維度(基本面、估值、技術、動能、籌碼)加權後的總分;權重依模式不同。\n"
        "- **百分位**:這檔的綜合分在**這份名單裡**的橫斷面排名(0～100,越高代表在名單中越前面)。\n"
        "- **五維分數 / 估值狀態 / 信心**:各面向細分與資料完整度(信心低=部分資料缺漏,分數參考性打折)。\n"
        "- **基準日**:這批分數是「哪一天」算出來的 —— 它是**快照、不是當下即時價**。\n\n"
        "**重要:資料是快照,不是即時**　名單概況會顯示「共 N 檔｜基準日 X｜權重版本」。"
        "排名只在這份名單內相對比較(名單來源是專案的 `watchlist.txt` 自選股池)。"
        "想要最新即時的單檔狀態,還是要回『個股分析』用你的 token 重抓。\n\n"
        "**多久更新一次?**　部署站的分數由維護者定期重算後上傳,你只要選條件檢視、不需自己建。"
        "(若你是自架/本機執行:先在專案根目錄跑 `python build_cache.py --build-scores` 建/更新快取,"
        "再按分頁上的『↻ 重新載入快取』即可。)")

    st.divider()
    st.subheader("🌐 『全市場掃描』& 來源臂到底哪個好")
    st.markdown(
        "**先講結論:沒有『哪個來源臂最好』。** 五個來源臂(便宜/動能/籌碼/突破/營收加速)只是"
        "**召回網**——某檔在池內某因子百分位>85 就掛上該臂,用來『把可能有戲的股撈進 shortlist』,"
        "**它們單獨都不會選股**。\n\n"
        "真正有樣本外報酬證據的,是把幾個因子**組合**起來的 **C2 排序分**:\n"
        "> C2 = 產業內便宜 ＋ 營收 YoY ＋ 接近 52 週高 **－ 動能**\n\n"
        "(動能是**反向**的:C2 偏好『便宜又剛轉強、但還沒噴上去』的,不追已經漲多的。這條在寬池、"
        "六個時代的樣本外 IC 全正,見 DevLog §19。)\n\n"
        "**為什麼『便宜也不代表好』——這是資料結論,不是感覺:**\n"
        "- Part 4 回測(`scripts/streak_return_lab.py`):**便宜臂整體相對落後**,去掉大盤漲跌後的超額"
        "(excess)每一個在榜天數桶都是 **−2%~−3%**(新進與 5–9 天桶統計上顯著)。\n"
        "- TEJ Phase 2 研究更早就發現:極端便宜的排名本身**附著價值陷阱(接落刀)**。\n"
        "- 直白說:便宜是『撈進來看一眼』的理由,**不是買進理由**。要便宜**加上**營收在成長、"
        "且股價已站上結構(接近 52 週高、不是還在破底),才是 C2 真正獎勵的組合。\n\n"
        "**所以要怎麼用這一頁?**\n"
        "1. 直接看最上面的 **🌐 整體推薦 Top 10**(已依 C2 排序,附理由與價位),不要自己在大表裡大海撈針。\n"
        "2. **多臂交集**的股(來源臂欄有 2~3 個)通常比單臂更值得先看;看到 **⚠️僅便宜臂** 要特別保守。\n"
        "3. 想買哪一檔,把代號貼到『個股分析』做四維度深評 + 精確買點,再決定。")

    st.divider()
    st.subheader("✨ 『雙確認精選』的實測證據 —— 對『含息 0050』誠實對照")
    st.markdown(
        "『雙確認精選』= 同時落在 **c2 前 20%(價值/反動能)** 且 **綜合分前 20%(品質/順動能)** 的交集。"
        "以下是 **2005–2026、257 個月、含股息、扣元大 6 折成本**的回測,**基準是可投資的『含息 0050 買進持有』**"
        "(不是等權除息母體——那個嚴重低估、會讓人自我感覺良好):")
    st.markdown(
        "| 配置 | 年化 CAGR | 夏普 | 最大回撤 |\n"
        "|---|---|---|---|\n"
        "| 雙確認 20%(無風控) | +16.1% | 0.64 | −69% |\n"
        "| **雙確認 + 🚦 市場燈號風控** | +14.4% | **0.83** | **−27%** |\n"
        "| **含息 0050 買進持有** | +14.7% | 0.69 | −54% |")
    st.markdown(
        "**誠實的三句話:**\n"
        "1. **選股是有 alpha 的**,但沒有風控時回撤 −69%、夏普 0.64 **反而輸 0050**——問題不在選股,在回撤。\n"
        "2. **加上『市場燈號』風控後才真正淨贏 0050**:夏普 0.83 > 0.69、回撤 −27% 遠優於 −54%。"
        "但**純比賺錢(CAGR)只是打平**,贏的是**風險調整後**、坐得更穩。\n"
        "3. 這是用 **app 精確綜合分**(2005-2018 財報已補齊)複驗的結果、不是近似,可信度比舊版高。\n\n"
        "**能不能用它,取決於你能不能照燈號的紀律動**(空頭減碼、別追高)。多數人做不到——"
        "『數字漂亮的策略』實盤賺不到,通常是紀律在最痛時斷掉,不是策略錯。")
    st.info(
        "**打折因素(實盤只會更差):** ①close 未還原除權息、零股有價差滑價;②**回測 ≠ 未來**。\n\n"
        "**定位:** 這是**衛星部位**——只放你能承受回撤的小部分資金,搭『🚦 市場燈號』控風險,"
        "每檔仍到『個股分析』深評,**不機械照單全買**。核心資金的擺法見最下方『務實用法』。**非投資建議。**")

    st.divider()
    st.subheader("⏳ 連續在榜越久越好嗎?有沒有推薦的在榜區間?")
    st.markdown(
        "**短答:沒有推薦區間;越久既不代表越好、也不代表越差——榜齡根本不是訊號。**\n\n"
        "『連續在榜』本來就只是**顯示**『這檔被 shortlist 圈中幾天了』,從來沒被當成選股訊號驗證過。"
        "Part 4 專門補了這個回測(`streak_return_lab.py`,130 天歷史、20 交易日前瞻):\n"
        "- 把在榜天數分成 1(新進)/2–4/5–9/10–19/20–39/40+ 桶,量各桶未來 20 日報酬。\n"
        "- 去掉大盤 beta 後,**各桶的相對超額只在 −0.6%~+0.4% 之間跳、t 全部 <1.4** → 純雜訊。"
        "**把『在榜越久』當加分或擇時,是沒有根據的。** 排序請看 C2、不看榜齡。\n\n"
        "**那你看到的『>40 天股價很平穩、看不懂好處』是什麼?** 你的直覺抓到真東西了,只是它藏在"
        "**便宜臂**裡:\n"
        "- 便宜臂的股票,在榜 5–39 天那幾桶的**中位數報酬是 0 到 −0.4%**(原地踏步、甚至微跌),"
        "但**平均**卻是正的——因為少數幾檔暴力反彈把平均拉高了。\n"
        "- 這正是**價值陷阱的長相:大部分是死錢,偶爾一檔樂透式反彈**。所以一檔『又便宜、又在榜很久、"
        "股價卻不動』的股,通常就是那個『不動的多數』,不是還沒發動的璞玉。\n\n"
        "**實務建議:**\n"
        "- 榜齡當**參考資訊**看就好,不要當買賣依據。\n"
        "- 看到 **⚠️僅便宜臂 + 在榜很久**,把它當『死錢機率高』的提醒,別當穩健核心。\n"
        "- 組合層的證據(§22)是**季度換手、買 C2 前段**——重點在**排名**與**紀律**,不在『抱著等它變老』。")

    st.divider()
    st.subheader("🚦 『市場燈號』怎麼用")
    st.markdown(
        "它回答一個問題:**現在該持有幾成?**(0 / 33% / 67% / 100%),**不預測漲跌**。\n\n"
        "**背後邏輯**:全市場等權指數站上幾條均線(MA50 / MA100 / MA200)→ 對應曝險 3/3、2/3、1/3、0。"
        "加一層**『確認 3 天』遲滯**:均線要**連續 3 天**穿越才改判,濾掉一兩天的碎波假訊號(避免賣低買高)。\n\n"
        "**怎麼看**:🟢=滿倉、🟡=偏多/防禦、🔴=空手;下面列出三條均線目前站上或跌破幾天、距均線多少 %。"
        "看到『⏳ 剛翻、遲滯確認中』表示剛穿越、還在等連 3 天確認。\n\n"
        "**怎麼用**:給**衛星部位**當減碼依據——燈轉黃/紅就把主動選股的部位往下降。資料每天自動追最新交易日。\n\n"
        "⚠️ **反應式、會落後轉折點**,碎波盤可能小幅拉鋸。它救的是『不接刀、不在崩盤全額硬扛』,不是抓頂抄底。")

    st.divider()
    st.subheader("💰 『定期定額』怎麼用")
    st.markdown(
        "輸入**每月投入金額**與**起始年**,它用 2005-2026 真實含息序列,算你 DCA 的**個人真實報酬 MWRR**"
        "(資金加權報酬率,把你何時、投多少都算進去),並排比較『策略』與『0050』。\n\n"
        "**先講結論(誠實)**:**DCA 下,純 0050 在每個起始年都賺得比策略多**(例:2015 起 MWRR 26.9% vs 18.9%),"
        "策略只勝在**回撤約一半**。原因:策略空頭減碼會躲掉下跌,但也躲掉了 DCA『趁跌買便宜』的好處,"
        "而 0050 會自我修復、跌了照樣值得買。\n\n"
        "**用途**:幫你**看清『定存的錢該擺 0050』**,別被『策略贏 0050』的說法誤導成把定存錢也拿去玩策略。")

    st.divider()
    st.subheader("📋 『實戰演練』怎麼用")
    st.markdown(
        "把某天的 plan 選股做成**操作卡**(凍結日),你**回填實際成交價**,系統自動**對帳**:"
        "毛/淨報酬(含元大零股 6 折實收費用)、滑價、持股追蹤。\n\n"
        "**目的不是看它賺多少,是練『執行紀律』**——你有沒有照規則在 T+1 整批進場、有沒有照『市場燈號』"
        "在空頭縮手。整套策略最脆弱的一環是**人性**,這頁就是讓你在**真錢之前**先驗證自己做不做得到。")

    st.divider()
    st.subheader("🧠 務實用法 —— 這工具在你的資金裡該擺哪")
    st.markdown(
        "把錢分兩桶,是全部研究驗證出來的結論:\n\n"
        "**桶 1 · 核心(每月定存的錢)→ 純 0050 DCA,穿越多空都不停。**\n"
        "讓 DCA 自己買低、0050 自己自我修復(成分股衰退會被換掉)。這桶**不要加任何開關**——DCA 的魔力就是空頭撿便宜。\n\n"
        "**桶 2 · 衛星(賠得起的一小部分)→ 主動選股 + 🚦 市場燈號控風險。**\n"
        "多頭用本工具選股(價值+基本面是真引擎)、空頭照燈號減碼轉現金。這桶是**練功 + 扛回撤經驗**,"
        "報酬不保證贏 0050,但風險調整後與坐得穩上有優勢。\n\n"
        "**關於單押龍頭(台積電/聯發科這種)**:實測 DCA,押對(台積)2005 起 24 倍電爆 0050;但『一樣安全』的"
        "聯發科同期只有 6 倍、還套牢 6.4 年。**『倒不了』≠『會贏』**——單股沒有 0050 的自癒,你是在賭『這一家續強』,"
        "所以只能當衛星、用賠得起的部位。\n\n"
        "**一句話**:本工具讓你在**小部分資金**上有紀律地選股與控風險;**核心請交給 0050**。")

    st.divider()
    st.caption("完整版見專案 docs/使用指南_USER_GUIDE.md。本工具為研究輔助,不構成投資建議;回測 ≠ 未來。")
