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


@st.cache_data(show_spinner=False)
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

tab_one, tab_rank, tab_screen, tab_univ, tab_help = st.tabs(
    ["🔎 個股分析", "🏆 多檔排行", "🎯 綜合分選股", "🌐 全市場掃描", "📖 使用說明"])

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
        # 名稱回填:舊快取的 name 欄可能等於代號,用 watchlist.txt 的股名覆蓋 (例 2330 → 台積電)。
        if df is not None and not df.empty and "stock_id" in df.columns and "name" in df.columns:
            _nmap = watchlist_names()
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
    if not _files:
        st.info("找不到 shortlist 檔案。此分頁讀本機每日粗篩產出 (`outputs/universe_pool/`),"
                "由排程 Market_SnapshotCollector 每早自動生成;歷史可用 "
                "`python scripts/universe_screen_backfill.py` 回補。")
    else:
        _dates = [os.path.basename(f)[10:-4] for f in _files]
        _pick = st.selectbox("資料日", _dates[::-1], index=0)
        _f = _files[_dates.index(_pick)]
        _df = _univ_load(_f).sort_values("composite", ascending=False)
        _streaks = _univ_streaks(tuple(_files[: _dates.index(_pick) + 1][-40:]))

        _pool_f = os.path.join(_UNIV_DIR, f"pool_{_pick}.csv")
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
            _new50 -= set(_univ_load(_files[_prev_idx]).sort_values(
                "composite", ascending=False).head(50).index)

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

        _cols = [c for c in ("name", "industry", "close", "composite", "來源臂", "連續在榜",
                              "value_ind_pct", "momentum20", "chip20_turnover",
                              "high52_prox", "rev_accel", "adv20") if c in _v.columns]
        _disp = _v[_cols].rename(columns={
            "name": "名稱", "industry": "產業", "close": "收盤", "composite": "綜合",
            "value_ind_pct": "產業內便宜", "momentum20": "20日動能%",
            "chip20_turnover": "法人流向", "high52_prox": "距52週高%",
            "rev_accel": "營收加速", "adv20": "20日均額"})
        st.dataframe(_disp.round(2), use_container_width=True, height=520)
        _new_rows = _df.loc[sorted(_new50)]
        if len(_new_rows):
            st.markdown("#### 🆕 今日新進 composite 前 50")
            st.dataframe(_new_rows[_cols].rename(columns={"name": "名稱", "industry": "產業"}).round(2),
                         use_container_width=True)
        _digest_f = os.path.join(_UNIV_DIR, f"digest_{_pick}.md")
        if os.path.exists(_digest_f):
            with st.expander("📄 當日文字摘要 (digest)"):
                st.markdown(open(_digest_f, encoding="utf-8").read())
        st.caption("資料=TWSE/TPEx 官方快照+TEJ 種子 (0 FinMind);L0-L2 粗篩後五因子聯集,"
                   "composite=五因子池內百分位平均。**分流參考,非投組**;個股請至『個股分析』深評。")

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
