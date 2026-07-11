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
         "也不會寫入伺服器。留空=匿名 (每日額度極低,可能查不到)。『綜合分選股』分頁免 token。")
if user_token:
    st.sidebar.caption("✅ 已使用你的 token (額度算你的)")
else:
    st.sidebar.caption("ℹ️ 未貼 token → 匿名模式;建議用『綜合分選股』分頁 (免 token)")
st.sidebar.divider()
st.sidebar.caption("⚠️ 研究/篩選輔助,非投資建議。評級是『狀態分類』,不是立刻買進;"
                   "進場價位請看每檔的『買點提示』。")

tab_one, tab_rank, tab_screen, tab_help = st.tabs(
    ["🔎 個股分析", "🏆 多檔排行", "🎯 綜合分選股", "📖 使用說明"])

# ------------------------------------------------------------------ 個股分析
with tab_one:
    if not user_token:
        st.info("即時個股分析會打 FinMind API。請在左側貼上『你自己的 FinMind token』"
                "(額度算你的),或改用免 token 的『綜合分選股』分頁。未貼 token 將以匿名模式嘗試,"
                "額度極低、常會失敗。")
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

# ------------------------------------------------------------------ 使用說明
with tab_help:
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
    st.caption("完整版見專案 docs/使用指南_USER_GUIDE.md。本工具為研究輔助,不構成投資建議。")
