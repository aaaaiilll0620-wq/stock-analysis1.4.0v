"""alpha_gate_lab.py — 新驗證量尺 (擴池+細分位) + 因子探索實驗室
================================================================================
背景 (DevLog §18-E):45 檔池 + q=1/3 的官方閘門量不出窄子集機制與小幅排序力差異。
本實驗室把量尺升級為:
  · 母體 = 全市場 L1 可投資池 (20日均成交額≥10M + 上市滿年,每期 ~700-900 檔)
  · 指標 = Rank IC (含 t 值)、十分位多空 (LS10)、五分位階梯單調性、top10−next15 細分位差
  · 期間 = 探索期 2019-2021 / 2022空頭 / 2023-2025;封存 hold-out 2005-2018 (只對倖存者跑一次)
資料 = obs_dump_full.parquet (tej_universe_screen_validation.py --dump-obs 產出,
2005-2026 月度截面) + tej_cache 增補 (產業/TDCC/質押/籌碼多窗/技術代理)。
0 API、純本機。scratch 實驗室,不動任何正式模組。

用法:
  python scripts/alpha_gate_lab.py --build       # 組裝增補後觀測 → obs_alpha.parquet
  python scripts/alpha_gate_lab.py --report      # 探索期:基線 + 全因子掃描 (含正交殘差)
  python scripts/alpha_gate_lab.py --regime      # 探索期:牛熊分段條件 IC
  python scripts/alpha_gate_lab.py --holdout f1,f2  # 封存段複驗 (只對過閘門因子)
================================================================================
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

SCRATCH = Path(r"C:\Users\aaaai\AppData\Local\Temp\claude"
               r"\C--Users-aaaai-OneDrive-Desktop-Project-1"
               r"\623b4372-467b-4a4c-83eb-ae0cc72a6d60\scratchpad")
TEJ = Path.home() / "tej_cache"
OBS_SRC = SCRATCH / "obs_dump_full.parquet"
OBS_OUT = SCRATCH / "obs_alpha.parquet"

ADV_FLOOR = 10_000_000
TDCC_LAG_DAYS = 4       # 集保資料日=週五,公布約次週初 (同 tej_orthogonal_lab.py)
PLEDGE_LAG_DAYS = 15    # 董監月報約次月中旬前公布

DISCOVERY_ERAS = [
    ("2019-2021", "2019-01-01", "2021-12-31"),
    ("2022空頭",  "2022-01-01", "2022-12-31"),
    ("2023-2025", "2023-01-01", "2025-12-31"),
]
HOLDOUT_ERAS = [
    ("2005-2009(海嘯)", "2005-01-01", "2009-12-31"),
    ("2010-2014",       "2010-01-01", "2014-12-31"),
    ("2015-2018",       "2015-01-01", "2018-12-31"),
]

# 生產 shortlist 5F (universe_screen_daily.py):等權 pool 百分位
BASELINE_5F = ["value_ind", "momentum", "chip", "high52_prox", "rev_accel"]

# 因子清單:(欄位, 說明, 類別)。方向不預設,IC 正負自己說話。
CANDIDATES = [
    # 基線成分
    ("value_ind",       "產業內估值位階(§15-G)",       "基線成分"),
    ("value",           "全市場PE歷史位階",             "基線成分"),
    ("momentum",        "20日動能",                     "基線成分"),
    ("chip",            "法人20日淨買/量",              "基線成分"),
    ("high52_prox",     "52週高點接近度",               "基線成分"),
    ("rev_accel",       "營收YoY加速度(YoY−3月均)",     "基線成分"),
    # 動能視野
    ("mom60",           "60日動能",                     "動能視野"),
    ("mom120",          "120日動能",                    "動能視野"),
    # 技術代理 (實驗A:對動能正交化)
    ("rsi14",           "RSI14",                        "技術代理"),
    ("bbp20",           "布林%B(20)",                   "技術代理"),
    ("ma_gap60",        "價/60日均線偏離",              "技術代理"),
    ("vol60",           "60日已實現波動",               "技術代理"),
    # 籌碼多窗 (實驗C)
    ("chip5",           "法人5日淨買/量",               "籌碼窗"),
    ("chip10",          "法人10日淨買/量",              "籌碼窗"),
    ("chip60",          "法人60日淨買/量",              "籌碼窗"),
    ("chip_accel",      "籌碼加速(5日−20日日均差)",     "籌碼窗"),
    # 新資料源 (實驗D,2019+)
    ("big_d4w",         "千張大戶比4週變化",            "TDCC"),
    ("big_d12w",        "千張大戶比12週變化",           "TDCC"),
    ("holders_chg12w",  "股東人數12週變化",             "TDCC"),
    ("ratio_1000up",    "千張大戶比水位",               "TDCC"),
    ("pledge_pct",      "董監質押比",                   "質押"),
    ("pledge_d3m",      "質押比3月變化",                "質押"),
    ("director_holding_pct", "董監持股比",              "質押"),
    ("revenue_yoy",     "營收YoY水位",                  "營收"),
    ("roe",             "ROE(單季)",                    "品質"),
    ("eps_pos_q4",      "近4季EPS>0季數",               "品質"),
]


# ------------------------------------------------------------------------------
# build:組裝增補觀測
# ------------------------------------------------------------------------------
def build():
    obs = pd.read_parquet(OBS_SRC)
    obs["_dt"] = pd.to_datetime(obs["as_of"])
    as_of_days = sorted(obs["as_of"].unique())
    print(f"obs 基底:{len(obs)} 列 / {obs['stock_id'].nunique()} 檔 / {len(as_of_days)} 期")

    con = duckdb.connect()

    # --- L1 可投資性:adv20 + 上市滿年 (同 tej_acceptance_2005_2018.py) ---
    liq = con.execute(f"""
        SELECT stock_id, date,
               AVG(close * Trading_Volume) OVER (PARTITION BY stock_id ORDER BY date
                   ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
               MIN(date) OVER (PARTITION BY stock_id) AS first_date
        FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
    """).df()
    liq = liq[liq["date"].isin(as_of_days)]
    liq["listed_ok"] = ((liq["first_date"] <= "2004-01-15") |
                        ((pd.to_datetime(liq["date"]) - pd.to_datetime(liq["first_date"])).dt.days >= 365))
    obs = obs.merge(liq[["stock_id", "date", "adv20", "listed_ok"]],
                    left_on=["stock_id", "as_of"], right_on=["stock_id", "date"],
                    how="left").drop(columns=["date"])

    # --- 產業內估值位階 (同 acceptance:分組<5 退回全市場) ---
    ind = pd.read_parquet(TEJ / "industry_map.parquet")[["stock_id", "tej_ind_name"]]
    obs = obs.merge(ind, on="stock_id", how="left")
    obs["rev_accel"] = obs["revenue_yoy"] - obs["rev_yoy_3m"]
    grp = obs.groupby(["as_of", "tej_ind_name"])["value"]
    vind = grp.rank(pct=True) * 100
    size = grp.transform("size")
    mkt = obs.groupby("as_of")["value"].rank(pct=True) * 100
    obs["value_ind"] = vind.where(size >= 5, mkt)

    # --- 技術代理 + 波動:從價量全歷史向量化計算,取 as_of 當日值 ---
    print("計算技術代理 (rsi14/bbp20/ma_gap60/vol60)…")
    px = con.execute(f"""
        SELECT stock_id, date, close, Trading_Volume
        FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    g = px.groupby("stock_id", sort=False)["close"]
    delta = g.diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    # Wilder 近似:14日簡單均 (橫斷面排名用,精度足夠)
    roll_up = up.groupby(px["stock_id"]).rolling(14, min_periods=14).mean().reset_index(level=0, drop=True)
    roll_dn = dn.groupby(px["stock_id"]).rolling(14, min_periods=14).mean().reset_index(level=0, drop=True)
    px["rsi14"] = 100.0 - 100.0 / (1.0 + roll_up / roll_dn.replace(0.0, np.nan))
    ma20 = g.transform(lambda s: s.rolling(20, min_periods=20).mean())
    sd20 = g.transform(lambda s: s.rolling(20, min_periods=20).std())
    px["bbp20"] = (px["close"] - (ma20 - 2 * sd20)) / (4 * sd20).replace(0.0, np.nan)
    ma60 = g.transform(lambda s: s.rolling(60, min_periods=60).mean())
    px["ma_gap60"] = px["close"] / ma60 - 1.0
    ret1 = g.pct_change()
    px["vol60"] = ret1.groupby(px["stock_id"]).rolling(60, min_periods=40).std().reset_index(level=0, drop=True)
    tech = px[px["date"].isin(as_of_days)][["stock_id", "date", "rsi14", "bbp20", "ma_gap60", "vol60"]]
    obs = obs.merge(tech, left_on=["stock_id", "as_of"], right_on=["stock_id", "date"],
                    how="left").drop(columns=["date"])

    # --- 籌碼多窗:淨買超 rolling 和 / 成交量 rolling 和 (同 validation turnover 模式) ---
    print("計算籌碼多窗 (chip5/10/60/accel)…")
    flow = con.execute(f"""
        SELECT stock_id, date, foreign_net + trust_net + dealer_net AS net_total
        FROM read_parquet('{TEJ}/institutional_flow/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    flow = flow.merge(px[["stock_id", "date", "Trading_Volume"]], on=["stock_id", "date"], how="left")
    fg = flow.groupby("stock_id", sort=False)
    for w in (5, 10, 20, 60):
        ns = fg["net_total"].rolling(w, min_periods=w).sum().reset_index(level=0, drop=True)
        vs = fg["Trading_Volume"].rolling(w, min_periods=w).sum().reset_index(level=0, drop=True)
        flow[f"chip{w}"] = ns / vs.replace(0.0, np.nan)
    flow["chip_accel"] = flow["chip5"] - flow["chip20"]
    chipw = flow[flow["date"].isin(as_of_days)][["stock_id", "date", "chip5", "chip10", "chip60", "chip_accel"]]
    obs = obs.merge(chipw, left_on=["stock_id", "as_of"], right_on=["stock_id", "date"],
                    how="left").drop(columns=["date"])

    # --- TDCC 週頻 (PIT lag 4d,同 tej_orthogonal_lab.py) ---
    print("合併 TDCC / 質押 (PIT asof)…")
    tdcc = con.execute(f"""
        SELECT stock_id, date, ratio_1000up, holders
        FROM read_parquet('{TEJ}/tdcc_weekly/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    tg = tdcc.groupby("stock_id")
    tdcc["big_d4w"] = tdcc["ratio_1000up"] - tg["ratio_1000up"].shift(4)
    tdcc["big_d12w"] = tdcc["ratio_1000up"] - tg["ratio_1000up"].shift(12)
    tdcc["holders_chg12w"] = tdcc["holders"] / tg["holders"].shift(12) - 1
    tdcc["known_date"] = pd.to_datetime(tdcc["date"]) + pd.Timedelta(days=TDCC_LAG_DAYS)
    tdcc = tdcc.sort_values("known_date")
    obs = obs.sort_values("_dt")
    obs = pd.merge_asof(obs, tdcc[["stock_id", "known_date", "ratio_1000up",
                                   "big_d4w", "big_d12w", "holders_chg12w"]],
                        left_on="_dt", right_on="known_date", by="stock_id",
                        direction="backward", tolerance=pd.Timedelta(days=60)
                        ).drop(columns=["known_date"])

    # --- 董監質押 (月頻,PIT lag 月底+15d) ---
    pledge = con.execute(f"""
        SELECT stock_id, date, pledge_pct, director_holding_pct
        FROM read_parquet('{TEJ}/director_pledge/*.parquet', union_by_name=true)
        ORDER BY stock_id, date
    """).df()
    pg = pledge.groupby("stock_id")
    pledge["pledge_d3m"] = pledge["pledge_pct"] - pg["pledge_pct"].shift(3)
    pledge["known_date"] = (pd.to_datetime(pledge["date"]) + pd.offsets.MonthEnd(0)
                            + pd.Timedelta(days=PLEDGE_LAG_DAYS))
    pledge = pledge.sort_values("known_date")
    obs = pd.merge_asof(obs, pledge[["stock_id", "known_date", "pledge_pct",
                                     "pledge_d3m", "director_holding_pct"]],
                        left_on="_dt", right_on="known_date", by="stock_id",
                        direction="backward", tolerance=pd.Timedelta(days=90)
                        ).drop(columns=["known_date"])
    con.close()

    obs = obs.drop(columns=["_dt"])
    obs.to_parquet(OBS_OUT, index=False)
    l1 = obs[(obs["adv20"] >= ADV_FLOOR) & obs["listed_ok"].fillna(False)]
    per_date = l1.groupby("as_of").size()
    print(f"已輸出 {OBS_OUT.name}:{len(obs)} 列;L1 後每期 {per_date.min()}~{per_date.max()} 檔 "
          f"(中位 {int(per_date.median())})")


# ------------------------------------------------------------------------------
# 量尺指標
# ------------------------------------------------------------------------------
def _per_date(df):
    return df.groupby("as_of", sort=False)


def ic_series(df, key):
    """每期 Spearman IC 序列。"""
    def one(g):
        x, y = g[key], g["fwd"]
        m = x.notna() & y.notna()
        if m.sum() < 30:
            return np.nan
        return x[m].rank().corr(y[m].rank())
    return _per_date(df).apply(one).dropna()


def ic_stats(df, key):
    s = ic_series(df, key)
    if len(s) < 3:
        return np.nan, np.nan, 0
    return float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s))), len(s)


def ls_spread(df, key, q=0.1):
    """十分位多空:同日 top q − bottom q 的 fwd 差,逐期平均。"""
    def one(g):
        g = g.dropna(subset=[key, "fwd"])
        k = int(len(g) * q)
        if k < 5:
            return np.nan
        g = g.sort_values(key)
        return g["fwd"].tail(k).mean() - g["fwd"].head(k).mean()
    s = _per_date(df).apply(one).dropna()
    return float(s.mean()) if len(s) >= 3 else np.nan


def quintile_mono(df, key):
    """五分位階梯單調性:Q1..Q5 平均 fwd 對 1..5 的 Spearman (1=完美單調)。"""
    def one(g):
        g = g.dropna(subset=[key, "fwd"])
        if len(g) < 50:
            return None
        g = g.copy()
        g["_q"] = pd.qcut(g[key].rank(method="first"), 5, labels=False)
        return g.groupby("_q")["fwd"].mean()
    ladders = [r for _, gr in _per_date(df) if (r := one(gr)) is not None]
    if len(ladders) < 3:
        return np.nan
    ladder = pd.concat(ladders, axis=1).mean(axis=1)
    return float(pd.Series(ladder.values).rank().corr(pd.Series(range(5), dtype=float)))


def top_slice(df, key, n_top=10, n_next=15):
    """細分位:top-N 平均 fwd − next-N 平均 fwd (§18-E 要的窄子集量測)。"""
    def one(g):
        g = g.dropna(subset=[key, "fwd"]).sort_values(key, ascending=False)
        if len(g) < n_top + n_next:
            return np.nan
        return g["fwd"].head(n_top).mean() - g["fwd"].iloc[n_top:n_top + n_next].mean()
    s = _per_date(df).apply(one).dropna()
    return float(s.mean()) if len(s) >= 3 else np.nan


def ortho_ic(df, key, base="composite"):
    """對 base 正交化後的殘差 IC (每期橫斷面 OLS 取殘差)。"""
    def one(g):
        m = g[key].notna() & g[base].notna() & g["fwd"].notna()
        if m.sum() < 30:
            return np.nan
        x = g.loc[m, base].rank()
        y = g.loc[m, key].rank()
        beta = np.polyfit(x, y, 1)
        resid = y - np.polyval(beta, x)
        return pd.Series(resid).rank().corr(g.loc[m, "fwd"].rank())
    s = _per_date(df).apply(one).dropna()
    if len(s) < 3:
        return np.nan, np.nan
    return float(s.mean()), float(s.mean() / s.std() * np.sqrt(len(s)))


def add_baseline(df):
    """生產 5F 等權 composite (universe 內百分位)。"""
    pcts = []
    for f in BASELINE_5F:
        pcts.append(df.groupby("as_of")[f].rank(pct=True) * 100)
    df["composite"] = pd.concat(pcts, axis=1).mean(axis=1, skipna=True)
    return df


def load_l1(eras):
    obs = pd.read_parquet(OBS_OUT)
    obs = obs[(obs["adv20"] >= ADV_FLOOR) & obs["listed_ok"].fillna(False)].copy()
    lo = min(s for _, s, _ in eras)
    hi = max(e for _, _, e in eras)
    obs = obs[(obs["as_of"] >= lo) & (obs["as_of"] <= hi)]
    return add_baseline(obs)


def fmt(x, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:+.2f}" if pct else f"{x:+.3f}"


def era_slice(obs, s, e):
    return obs[(obs["as_of"] >= s) & (obs["as_of"] <= e)]


# ------------------------------------------------------------------------------
# report:基線 + 因子掃描
# ------------------------------------------------------------------------------
def report():
    obs = load_l1(DISCOVERY_ERAS)
    print(f"\nL1 母體觀測:{len(obs)} 列 / {obs['as_of'].nunique()} 期")

    print("\n" + "=" * 100)
    print("基線 — 生產 5F 等權 composite 過新量尺")
    print("=" * 100)
    print(f"{'期間':<12}{'IC':>8}{'t(IC)':>8}{'LS10%':>8}{'階梯單調':>9}{'top10−next15%':>14}{'期數':>6}")
    print("-" * 100)
    for name, s, e in DISCOVERY_ERAS:
        d = era_slice(obs, s, e)
        ic, t, n = ic_stats(d, "composite")
        print(f"{name:<12}{fmt(ic):>8}{fmt(t):>8}{fmt(ls_spread(d, 'composite'), 1):>8}"
              f"{fmt(quintile_mono(d, 'composite')):>9}{fmt(top_slice(d, 'composite'), 1):>14}{n:>6}")

    print("\n" + "=" * 100)
    print("因子掃描 — 每期 L1 母體橫斷面;殘差IC = 對 5F composite 正交化後")
    print("=" * 100)
    for era_name, s, e in DISCOVERY_ERAS:
        d = era_slice(obs, s, e)
        print(f"\n--- {era_name} ---")
        print(f"{'因子':<22}{'類別':<10}{'IC':>8}{'t(IC)':>8}{'LS10%':>8}{'單調':>7}"
              f"{'t10−n15%':>10}{'殘差IC':>8}{'t(殘)':>8}")
        print("-" * 100)
        for col, desc, cat in CANDIDATES:
            if col not in d.columns or d[col].notna().sum() < 1000:
                print(f"{desc:<22}{cat:<10}{'—— 資料不足 ——':>20}")
                continue
            ic, t, _ = ic_stats(d, col)
            oic, ot = ortho_ic(d, col)
            print(f"{desc:<22}{cat:<10}{fmt(ic):>8}{fmt(t):>8}{fmt(ls_spread(d, col), 1):>8}"
                  f"{fmt(quintile_mono(d, col)):>7}{fmt(top_slice(d, col), 1):>10}"
                  f"{fmt(oic):>8}{fmt(ot):>8}")

    print("\n判讀:候選要活著 = 殘差IC 的 |t|≥2.5 且三期不翻向 (2022 至少不明顯負);")
    print("     只有 IC 高但殘差IC≈0 的 = 換皮因子,不加。")


# ------------------------------------------------------------------------------
# regime:牛熊分段條件 IC
# ------------------------------------------------------------------------------
def regime():
    obs = load_l1(DISCOVERY_ERAS)
    mkt = obs.groupby("as_of")["mom60"].mean()
    bull_dates = set(mkt[mkt > 0].index)
    obs["_regime"] = np.where(obs["as_of"].isin(bull_dates), "bull", "bear")
    nb = obs[obs["_regime"] == "bull"]["as_of"].nunique()
    ns = obs["as_of"].nunique() - nb
    print(f"\nregime 分段 (市場 60 日動能均值正負):bull {nb} 期 / bear {ns} 期 (2019-2025)")
    print(f"{'因子':<22}{'IC(bull)':>10}{'t':>7}{'IC(bear)':>10}{'t':>7}{'殘差IC(bull)':>13}{'殘差IC(bear)':>13}")
    print("-" * 92)
    bull_d = obs[obs["_regime"] == "bull"]
    bear_d = obs[obs["_regime"] == "bear"]
    for col, desc, cat in CANDIDATES:
        if col not in obs.columns or obs[col].notna().sum() < 1000:
            continue
        ib, tb, _ = ic_stats(bull_d, col)
        ie, te, _ = ic_stats(bear_d, col)
        ob, _ = ortho_ic(bull_d, col)
        oe, _ = ortho_ic(bear_d, col)
        print(f"{desc:<22}{fmt(ib):>10}{fmt(tb):>7}{fmt(ie):>10}{fmt(te):>7}{fmt(ob):>13}{fmt(oe):>13}")


# ------------------------------------------------------------------------------
# composite:候選綜合分 (依探索期倖存因子預先註冊,見 --report 判讀)
#   正向因子取 universe 內百分位,反向因子取 (100−百分位),等權平均後即候選分數。
# ------------------------------------------------------------------------------
COMPOSITES = {
    # C1 全天候核心 (hold-out 可測:成分 2005+ 皆有):估值產業位階 + 營收水位 + 短反轉
    "C1_全天候核心": (["value_ind", "revenue_yoy"], ["momentum"]),
    # C2 = C1 + 52週高點 (bull 傾斜,2005+ 可測)
    "C2_核心+52W高點": (["value_ind", "revenue_yoy", "high52_prox"], ["momentum"]),
    # C3 探索全配 (含 2019+ 新資料源:品質 ROE、大戶集中、低波)
    "C3_探索全配": (["value_ind", "revenue_yoy", "roe", "high52_prox"],
                    ["momentum", "holders_chg12w", "vol60"]),
    # C4 regime 切換:bull=C3,bear=全天候價值塊 (value_ind+rev_yoy+roe)
    "C4_regime切換": None,   # 特殊處理
}


def build_candidate(df, pos, neg, out):
    parts = []
    for f in pos:
        parts.append(df.groupby("as_of")[f].rank(pct=True) * 100)
    for f in neg:
        parts.append(100 - df.groupby("as_of")[f].rank(pct=True) * 100)
    df[out] = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    return df


def composite_lab():
    obs = load_l1(DISCOVERY_ERAS)
    for name, spec in COMPOSITES.items():
        if spec is None:
            continue
        build_candidate(obs, spec[0], spec[1], name)
    # C4:regime 切換 (bull=C3;bear=價值塊)
    mkt = obs.groupby("as_of")["mom60"].mean()
    bull_dates = set(mkt[mkt > 0].index)
    build_candidate(obs, ["value_ind", "revenue_yoy", "roe"], [], "_val_block")
    obs["C4_regime切換"] = np.where(obs["as_of"].isin(bull_dates),
                                    obs["C3_探索全配"], obs["_val_block"])

    names = ["composite"] + [n for n in COMPOSITES]
    labels = {"composite": "基線 5F (對照)"}
    print("\n" + "=" * 100)
    print("候選綜合分 vs 基線 5F — 新量尺全指標")
    print("=" * 100)
    for era_name, s, e in DISCOVERY_ERAS + [("2019-2025 全期", "2019-01-01", "2025-12-31")]:
        d = era_slice(obs, s, e)
        print(f"\n--- {era_name} ---")
        print(f"{'候選':<18}{'IC':>8}{'t(IC)':>8}{'LS10%':>8}{'單調':>7}{'t10−n15%':>10}")
        print("-" * 70)
        for nm in names:
            ic, t, _ = ic_stats(d, nm)
            print(f"{labels.get(nm, nm):<18}{fmt(ic):>8}{fmt(t):>8}{fmt(ls_spread(d, nm), 1):>8}"
                  f"{fmt(quintile_mono(d, nm)):>7}{fmt(top_slice(d, nm), 1):>10}")


# ------------------------------------------------------------------------------
# holdout:封存段複驗
# ------------------------------------------------------------------------------
def holdout(factors):
    obs = load_l1(HOLDOUT_ERAS)
    # 封存段可測的候選綜合分 (成分 2005+ 皆有;C3h = C3 拿掉 roe/holders 的可測變體)
    build_candidate(obs, ["value_ind", "revenue_yoy"], ["momentum"], "C1_全天候核心")
    build_candidate(obs, ["value_ind", "revenue_yoy", "high52_prox"], ["momentum"], "C2_核心+52W高點")
    build_candidate(obs, ["value_ind", "revenue_yoy", "high52_prox"], ["momentum", "vol60"], "C3h_可測變體")
    factors = ["C1_全天候核心", "C2_核心+52W高點", "C3h_可測變體"] + factors
    print(f"\n[封存段複驗] 只對過探索閘門的因子跑一次:{factors}")
    for era_name, s, e in HOLDOUT_ERAS:
        d = era_slice(obs, s, e)
        print(f"\n--- {era_name} ({d['as_of'].nunique()} 期,每期中位 "
              f"{int(d.groupby('as_of').size().median())} 檔) ---")
        print(f"{'因子':<18}{'IC':>8}{'t(IC)':>8}{'LS10%':>8}{'單調':>7}{'殘差IC':>8}{'t(殘)':>8}")
        print("-" * 70)
        for col in factors:
            if col not in d.columns or d[col].notna().sum() < 1000:
                print(f"{col:<18}{'—— 資料不足 ——':>20}")
                continue
            ic, t, _ = ic_stats(d, col)
            oic, ot = ortho_ic(d, col)
            print(f"{col:<18}{fmt(ic):>8}{fmt(t):>8}{fmt(ls_spread(d, col), 1):>8}"
                  f"{fmt(quintile_mono(d, col)):>7}{fmt(oic):>8}{fmt(ot):>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--regime", action="store_true")
    ap.add_argument("--composite", action="store_true")
    ap.add_argument("--holdout", default=None, metavar="f1,f2")
    args = ap.parse_args()
    if args.build:
        build()
    if args.report:
        report()
    if args.regime:
        regime()
    if args.composite:
        composite_lab()
    if args.holdout:
        holdout([f.strip() for f in args.holdout.split(",") if f.strip()])
    if not any([args.build, args.report, args.regime, args.composite, args.holdout]):
        ap.print_help()


if __name__ == "__main__":
    main()
