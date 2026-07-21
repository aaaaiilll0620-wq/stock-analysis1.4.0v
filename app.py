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
from html import escape

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


@st.cache_resource(show_spinner=False)
def get_engines(mode: str):
    return build_engines(mode)


@st.cache_data(show_spinner=False)
def analyze(symbol: str, mode: str, refresh: bool, token: str = ""):
    """
    回傳單檔分析結果 dict;None 表示抓不到資料。
    token 進 cache key → 不同訪客各自快取、各用自己的 FinMind 額度。
    在 _api_lock 內把 DataProvider._api 換成該 token 的獨立 loader,跑完還原 (並發安全)。
    """
    data_cache.FORCE_REFRESH = refresh
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
    return {
        "symbol": stock.symbol, "name": stock.name,
        "price": stock.current_price, "rating": score.rating,
        "total": score.total_score,
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

tab_one, tab_rank, tab_screen, tab_univ, tab_drill, tab_help = st.tabs(
    ["🔎 個股分析", "🏆 多檔排行", "🎯 綜合分選股", "🌐 全市場掃描", "📋 實戰演練", "📖 使用說明"])

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
                f"<div style='font-size:1rem;color:#444;margin:2px 0 10px'>"
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
            f"名單共 **{info['stocks']}** 檔　｜　基準日 **{info['as_of']}**　｜　"
            f"權重版本 `{info['weights_version']}`　"
            "<span style='color:#888'>(排名只在此名單內相對比較)</span>",
            unsafe_allow_html=True)

        f1, f2, f3 = st.columns(3)
        default_min = int(ScoringManager.MODES[mode]["min_score"])
        min_comp = f1.slider("綜合分下限", 0, 100, default_min,
                             help=f"預設 = 此模式門檻 min_score ({default_min})")
        min_conf = f2.slider("資料信心下限 (%)", 0, 100, 0)
        top = f3.slider("顯示檔數", 5, 100, 30)
        ratings = st.multiselect("限定評級 (不選 = 全部)", list(RATING_STYLE.keys()), default=[])

        df = screen_universe(mode, min_comp, tuple(ratings), min_conf, top)
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
            disp = df.rename(columns={
                "stock_id": "代號", "name": "名稱", "as_of": "基準日",
                "composite": "綜合分", "pct_rank": "百分位",
                "rating": "評級", "fundamental": "基本面", "valuation": "估值",
                "technical": "技術", "momentum": "動能", "whale": "籌碼",
                "valuation_status": "估值狀態", "data_confidence": "信心",
                "dyn_weight": "動態權重",
            })
            for col in ("基本面", "估值", "技術", "動能", "籌碼"):
                if col in disp.columns:
                    disp[col] = disp[col].round(0)
            if "綜合分" in disp.columns:
                disp["綜合分"] = disp["綜合分"].round(1)
            order = ["代號", "名稱", "評級", "綜合分", "百分位",
                     "基本面", "估值", "技術", "動能", "籌碼",
                     "估值狀態", "信心", "動態權重", "基準日"]
            disp = disp[[c for c in order if c in disp.columns]]
            st.dataframe(disp, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ 下載結果 (CSV)",
                data=disp.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"screen_{mode}_{info['as_of']}.csv",
                mime="text/csv")
            st.caption("綜合分 = 五維加權;百分位 = 該檔綜合分在此名單內的橫斷面排名 (越高越前)。"
                       "此頁純讀快取,不受側欄『刷新最新資料』影響。")

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

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("shortlist 檔數", len(_df))
        c2.metric("新進前 50", len(_new50))
        c3.metric("連續在榜 ≥5 天", int((_df["連續在榜"] >= 5).sum()))
        c4.metric("歷史資料天數", len(_files))

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

        _cols = [c for c in ("name", "industry", "close", _rc, "composite", "來源臂", "連續在榜",
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
    st.caption("完整版見專案 docs/使用指南_USER_GUIDE.md。本工具為研究輔助,不構成投資建議。")
