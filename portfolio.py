"""
投組觀察 / 追蹤驗證  portfolio.py
================================================================================
把 watchlist.txt 的自選股,變成一張『每天掃一眼就知道誰進到買點』的觀察表,
並把每次結果落地存檔,之後可回頭驗證系統的建議到底準不準、畫出累積報酬曲線。

用法:
  產生投組觀察表 (預設):   python portfolio.py            (等同 python portfolio.py watch)
  指定策略模式:            python portfolio.py watch --mode aggressive
  重抓最新資料再算:        python portfolio.py watch --refresh
  追蹤驗證 (含累積報酬圖):  python portfolio.py review
  只看近 30 天的紀錄:      python portfolio.py review --days 30

輸出:
  · 觀察表 CSV → outputs/portfolio/觀察表_<模式>_<時間>.csv
  · 每次 watch 會在 outputs/portfolio/tracking.csv 追加一筆快照 (同日同檔覆蓋)。
  · review 讀 tracking.csv → 比對最新價算後續報酬、勝率,並存累積報酬圖
    outputs/portfolio/累積報酬.png (需 matplotlib;沒裝也會照印文字統計)。

可重用函式 (app.py 的『我的投組』分頁直接呼叫,邏輯與 CLI 完全一致):
  load_tracking()  / review_stats()  / build_equity_curve()

⚠️ 本工具為個人研究/觀察輔助,所有評級與價位都是規則+模型的『參考』,不是投資建議。
================================================================================
"""
import os
import sys
import argparse
from datetime import datetime

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        return it

from core.trade_plan import build_trade_plan

PORT_DIR = os.path.join(_ROOT, "outputs", "portfolio")
TRACK_CSV = os.path.join(PORT_DIR, "tracking.csv")

# 事件研究用:視為『看多』的評級 (系統看多曲線只在這些評級時持有)
BULL_RATINGS = {"強勢買進", "強烈推薦"}
RATING_ORDER = ["強勢買進", "強烈推薦", "觀望追蹤", "謹慎避開"]
SNAPSHOT_COLS = ["觀察日", "模式", "代號", "名稱", "評級", "綜合分", "現價",
                 "進場下緣", "進場上緣", "停損", "目標1"]


def _ensure_dir():
    os.makedirs(PORT_DIR, exist_ok=True)


# ======================================================================
# watch:產生投組觀察表 + 落地快照
# ======================================================================
def cmd_watch(mode="balanced", refresh=False):
    import pandas as pd
    from build_cache import _load_pool
    from main import build_engines, analyze_stock, Config

    if refresh:
        try:
            from core import data_cache
            data_cache.FORCE_REFRESH = True
            print("(已啟用 --refresh:本次重抓最新資料)")
        except Exception:
            pass

    symbols = _load_pool()
    engines = build_engines(mode)
    score_manager, data_provider, fund_engine, val_engine, advisor = engines
    mode = Config.STRATEGY_MODE      # build_engines 會把模式正規化後寫回

    print(f"\n🔎 投組觀察表 — 模式 {mode}　｜　自選股 {len(symbols)} 檔")
    rows = []
    for sym in tqdm(symbols, desc="分析中"):
        try:
            stock = data_provider.fetch_full_stock_data(sym)
            if stock is None:
                continue
            _, _, res = analyze_stock(stock, fund_engine, val_engine, score_manager, advisor)
            plan = build_trade_plan(stock, res)
            rows.append({
                "觀察日": datetime.now().strftime("%Y-%m-%d"),
                "模式": mode,
                "代號": res.symbol,
                "名稱": res.name,
                "評級": res.rating,
                "綜合分": round(res.total_score, 1),
                "現價": round(float(getattr(stock, "current_price", 0) or 0), 2),
                "進場下緣": plan.entry_low,
                "進場上緣": plan.entry_high,
                "距買區%": plan.dist_to_buy_pct,
                "在買區": "是" if plan.in_buy_zone else "",
                "停損": plan.stop,
                "目標1": plan.target1,
                "目標2": plan.target2,
                "風報比": plan.rr,
                "資料信心%": round(float(getattr(res, "data_confidence", 0) or 0), 0),
                "買點提示": plan.note,
                "系統建議": res.actionable_advice,
            })
        except Exception as e:
            print(f"  ({sym} 略過:{e})")
            continue

    if not rows:
        print("⚠️ 沒有任何可用結果 (先跑 python build_cache.py 建本機快取,或檢查 FinMind Token)。")
        return

    df = pd.DataFrame(rows)
    df = sort_watch(df)

    show_cols = ["代號", "名稱", "評級", "綜合分", "現價", "進場下緣", "進場上緣", "距買區%", "停損", "目標1"]
    print("\n" + "=" * 100)
    print(df[show_cols].to_string(index=False))
    print("=" * 100)
    in_zone = df[df["在買區"] == "是"]
    if not in_zone.empty:
        print(f"✅ 目前已進入建議買區的有 {len(in_zone)} 檔:"
              + "、".join(f"{r['代號']}{r['名稱']}({r['評級']})" for _, r in in_zone.iterrows()))
    else:
        near = df.iloc[0]
        print(f"ℹ️ 目前沒有股票在買區;最接近的是 {near['代號']}{near['名稱']},距買區上緣 {near['距買區%']}%。")

    _ensure_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(PORT_DIR, f"觀察表_{mode}_{ts}.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n📂 觀察表已存:{out}")

    _append_snapshot(df, mode)
    print(f"🧾 已記錄今日快照到 {TRACK_CSV} (之後用 python portfolio.py review 驗證)。")


def sort_watch(df):
    """觀察表排序:已在買區的排最前,其次離買區最近的 (距買區% 由小到大)。"""
    d = df.copy()
    d["_in"] = d["在買區"].map(lambda x: 0 if x == "是" else 1)
    d["_d"] = d["距買區%"].fillna(9999)
    return d.sort_values(["_in", "_d"]).drop(columns=["_in", "_d"]).reset_index(drop=True)


def _append_snapshot(df, mode):
    """把本次結果的關鍵欄位追加進 tracking.csv (同日同模式同檔覆蓋,一天一筆)。"""
    import pandas as pd
    d = df.copy()
    if "觀察日" not in d.columns:
        d["觀察日"] = datetime.now().strftime("%Y-%m-%d")
    if "模式" not in d.columns:
        d["模式"] = mode
    snap = d[[c for c in SNAPSHOT_COLS if c in d.columns]].copy()
    _ensure_dir()
    if os.path.exists(TRACK_CSV):
        old = pd.read_csv(TRACK_CSV, dtype={"代號": str})
        today = str(snap["觀察日"].iloc[0])
        mask = ~((old["觀察日"].astype(str) == today) & (old["模式"] == mode)
                 & (old["代號"].isin(snap["代號"])))
        merged = pd.concat([old[mask], snap], ignore_index=True)
    else:
        merged = snap
    merged.to_csv(TRACK_CSV, index=False, encoding="utf-8-sig")


# ======================================================================
# 可重用分析:讀快照 → 驗證統計 / 累積報酬曲線 (CLI 與 app 共用)
# ======================================================================
def load_tracking(track_csv=TRACK_CSV):
    """讀 tracking.csv → DataFrame (觀察日 轉 datetime、代號 轉 str)。無檔回 None。"""
    import pandas as pd
    if not os.path.exists(track_csv):
        return None
    df = pd.read_csv(track_csv, dtype={"代號": str})
    df["觀察日"] = pd.to_datetime(df["觀察日"], errors="coerce")
    df = df.dropna(subset=["觀察日", "現價"])
    return df if not df.empty else None


def review_stats(df, days=None):
    """比對每檔最新價,算各評級的後續報酬/勝率/持有天數。
    回傳 dict(by_rating, overall, per_stock, hist) 或 None(歷史不足)。"""
    import pandas as pd
    if df is None or df.empty:
        return None
    latest = (df.sort_values("觀察日").groupby("代號").tail(1)[["代號", "觀察日", "現價"]]
              .rename(columns={"觀察日": "最新日", "現價": "最新價"}))
    m = df.merge(latest, on="代號", how="left")
    hist = m[m["觀察日"] < m["最新日"]].copy()
    if days:
        cutoff = m["最新日"].max() - pd.Timedelta(days=int(days))
        hist = hist[hist["觀察日"] >= cutoff]
    if hist.empty:
        return None

    hist["後續報酬%"] = (hist["最新價"] / hist["現價"] - 1.0) * 100.0
    hist["持有天數"] = (hist["最新日"] - hist["觀察日"]).dt.days

    def _agg(g):
        return pd.Series({
            "樣本數": len(g),
            "平均後續報酬%": round(g["後續報酬%"].mean(), 2),
            "中位數%": round(g["後續報酬%"].median(), 2),
            "勝率%": round((g["後續報酬%"] > 0).mean() * 100, 1),
            "平均持有天數": round(g["持有天數"].mean(), 1),
        })

    by_rating = hist.groupby("評級", group_keys=False).apply(_agg)
    by_rating = by_rating.reindex([r for r in RATING_ORDER if r in by_rating.index])
    overall = _agg(hist)
    per_stock = (hist.sort_values("觀察日").groupby("代號").tail(1)
                 [["代號", "名稱", "評級", "後續報酬%", "持有天數"]]
                 .sort_values("後續報酬%", ascending=False).reset_index(drop=True))
    return {"by_rating": by_rating, "overall": overall, "per_stock": per_stock, "hist": hist}


def build_equity_curve(df):
    """由快照建累積報酬 (長格式:日期/系列/指數,起始=100)。
      · 全清單(等權):每段期間等權持有所有當時有價的自選股。
      · 系統看多:每段期間只持有『上一次』評為強勢買進/強烈推薦的股票 (否則持現金)。
    資料少於 2 個觀察日回空表。"""
    import pandas as pd
    if df is None or df.empty:
        return pd.DataFrame(columns=["日期", "系列", "指數"])
    d = df.dropna(subset=["觀察日", "現價", "代號"]).copy()
    d = d.sort_values("觀察日").drop_duplicates(["觀察日", "代號"], keep="last")
    price = d.pivot(index="觀察日", columns="代號", values="現價").sort_index()
    rating = d.pivot(index="觀察日", columns="代號", values="評級").sort_index()
    dates = list(price.index)
    if len(dates) < 2:
        return pd.DataFrame(columns=["日期", "系列", "指數"])

    idx_all, idx_bull = [100.0], [100.0]
    for k in range(1, len(dates)):
        p0, p1 = price.loc[dates[k - 1]], price.loc[dates[k]]
        both = p0.notna() & p1.notna() & (p0 > 0)
        rets = (p1[both] / p0[both] - 1.0)
        r_all = float(rets.mean()) if len(rets) else 0.0
        r0 = rating.loc[dates[k - 1]]
        bmask = both & r0.isin(BULL_RATINGS)
        r_bull = float((p1[bmask] / p0[bmask] - 1.0).mean()) if int(bmask.sum()) else 0.0
        idx_all.append(idx_all[-1] * (1 + r_all))
        idx_bull.append(idx_bull[-1] * (1 + r_bull))

    out = []
    for dt, a, b in zip(dates, idx_all, idx_bull):
        out.append({"日期": dt, "系列": "全清單(等權)", "指數": round(a, 2)})
        out.append({"日期": dt, "系列": "系統看多(強勢買進+強烈推薦)", "指數": round(b, 2)})
    return pd.DataFrame(out)


def _save_equity_png(ec):
    """把累積報酬曲線存成 PNG (需 matplotlib);回傳路徑或 None。"""
    if ec is None or ec.empty:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        for f in ["Microsoft JhengHei", "Microsoft YaHei", "PingFang TC",
                  "Noto Sans CJK TC", "SimHei"]:
            matplotlib.rcParams["font.sans-serif"] = [f]
            break
        matplotlib.rcParams["axes.unicode_minus"] = False
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for name, g in ec.groupby("系列"):
            ax.plot(g["日期"], g["指數"], marker="o", label=name)
        ax.axhline(100, color="#999", lw=0.8, ls="--")
        ax.set_title("投組累積報酬 (起始=100)")
        ax.set_ylabel("指數")
        ax.legend()
        fig.autofmt_xdate()
        _ensure_dir()
        png = os.path.join(PORT_DIR, "累積報酬.png")
        fig.savefig(png, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return png
    except Exception as e:
        print(f"(略過存圖:{e};pip install matplotlib 可產生累積報酬圖)")
        return None


# ======================================================================
# review:CLI 版 (文字統計 + 存 PNG)
# ======================================================================
def cmd_review(days=None):
    df = load_tracking()
    if df is None:
        print("尚無任何追蹤紀錄。先跑幾次 python portfolio.py watch 累積快照後再回來 review。")
        return
    stats = review_stats(df, days=days)
    if stats is None:
        n_days = df["觀察日"].dt.date.nunique()
        print(f"目前只有 {n_days} 個觀察日的紀錄,還沒有『事後』資料可比對。"
              "\n明天起繼續跑 watch,累積 2 天以上就能看到各評級的後續表現了。")
        return

    print("\n" + "=" * 78)
    print("📈 追蹤驗證 — 當系統給出某評級後,到最新一筆的後續表現")
    print("=" * 78)
    print("\n【依評級彙總】(理想上:強勢買進 / 強烈推薦 的平均報酬與勝率應高於觀望/避開)")
    print(stats["by_rating"].to_string())
    ov = stats["overall"]
    print(f"\n【整體】樣本 {int(ov['樣本數'])} 筆　平均後續報酬 {ov['平均後續報酬%']}%　"
          f"勝率 {ov['勝率%']}%　平均持有 {ov['平均持有天數']} 天")

    ps = stats["per_stock"]
    print("\n【表現最好 5 檔】")
    print(ps.head(5).to_string(index=False))
    print("\n【表現最弱 5 檔】")
    print(ps.tail(5).to_string(index=False))

    png = _save_equity_png(build_equity_curve(df))
    if png:
        print(f"\n🖼️ 累積報酬圖已存:{png}")
    print("\n（樣本數少時僅供參考;連續累積越多天,統計越可信。本工具非投資建議。）")


def main():
    ap = argparse.ArgumentParser(description="投組觀察 / 追蹤驗證")
    ap.add_argument("cmd", nargs="?", default="watch", choices=["watch", "review"],
                    help="watch=產生觀察表(預設);review=驗證歷史建議")
    ap.add_argument("-m", "--mode", default="balanced",
                    help="策略模式 conservative/balanced/aggressive (或 c/b/a)")
    ap.add_argument("--refresh", action="store_true", help="watch 時重抓最新資料")
    ap.add_argument("--days", type=int, default=None, help="review 時只看近 N 天的紀錄")
    args = ap.parse_args()

    if args.cmd == "review":
        cmd_review(days=args.days)
    else:
        from main import normalize_mode
        cmd_watch(mode=normalize_mode(args.mode, "balanced"), refresh=args.refresh)


if __name__ == "__main__":
    main()
