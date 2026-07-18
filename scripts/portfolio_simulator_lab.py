# -*- coding: utf-8 -*-
"""portfolio_simulator_lab.py — 組合層兩步走・第二步:偽前瞻組合模擬器 (0 API)
================================================================================
預註冊規格:docs/預註冊_PortfolioSimulatorLab.md (2026-07-18 凍結,單發射擊制)。
回答三個組合層問題:
  Q1 節奏與成本:月度 vs 季度再平衡,扣除真實周轉成本(買0.1585%/賣0.4585%)淨報酬與回撤誰勝?
  Q2 執行落後代價:alpha 驗證用 T 收盤理想化排序;散戶只能 T+1 開盤進場,落後吃掉多少 edge?
  Q3 分批進場:新進榜部位整批買 vs 拆 2~3 批,能否降特異時機風險而不犧牲期望報酬?
資料 = obs_alpha.parquet (top-8 C2 籃,L1 池) + TEJ/快照 open 價格線 + 0050 基準 (finmind_cache)。
0 API、純本機。scratch 實驗室,不動任何正式模組。

用法:
  python scripts/portfolio_simulator_lab.py --cadence
  python scripts/portfolio_simulator_lab.py --lag
  python scripts/portfolio_simulator_lab.py --batching
  python scripts/portfolio_simulator_lab.py --sensitivity
  python scripts/portfolio_simulator_lab.py --all
================================================================================
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpha_gate_lab as agl  # noqa: E402  (只用 ADV_FLOOR/build_candidate 做 C2 複算檢查)

import lab_paths  # noqa: E402  2026-07-19 遷出 Temp scratchpad (工單 WP4)

SCRATCH_NEW = lab_paths.RESEARCH_BASE          # q1_*/q3_* 實驗輸出落點
TEJ_CACHE = Path.home() / "tej_cache"
MARKET_CACHE = Path.home() / "market_cache"
FINMIND_CACHE = Path.home() / "finmind_cache"
SNAP_DIR = MARKET_CACHE / "price_valuation_daily"
OBS_ALPHA = lab_paths.OBS_ALPHA
BENCH_0050 = FINMIND_CACHE / "TaiwanStockPrice" / "0050.parquet"
STATS_OUT = lab_paths.PORTFOLIO_SIM_STATS

# ---- 預註冊凍結參數 (docs/預註冊_PortfolioSimulatorLab.md) --------------------
SEED = 20260718
K = 8
BUY_COST = 0.001585
SELL_COST = 0.001585 + 0.003          # 0.004585
HOLD_DAYS = 20                        # Q2/Q3 固定評估窗 (對齊 alpha gate 20d 量尺)
BATCH_OFFSETS = {"lump": [1], "batch2": [1, 4], "batch3": [1, 4, 7]}  # T+n 交易日
MIN_STOCKS_PER_DAY = 500
N_BOOT = 2000
BOOT_P = 0.25
C2_POS = ["value_ind", "revenue_yoy", "high52_prox"]
C2_NEG = ["momentum"]

ERAS = [
    ("2019-2021",  "2019-01-01", "2021-12-31"),
    ("2022空頭",   "2022-01-01", "2022-12-31"),
    ("2023-2025",  "2023-01-01", "2025-12-31"),
]
FULL = ("全期2019-2025", "2019-01-01", "2025-12-31")
YTD26 = ("2026YTD健檢", "2026-01-01", "2026-12-31")

# ---- Q1 判準 (§9) --------------------------------------------------------
Q1_BEAR_DD_TOL = 3.0     # 2022 段回撤差距容忍 (百分點)
# ---- Q2 警戒線 (§9) -------------------------------------------------------
Q2_RETENTION_WARN = 0.50
# ---- Q3 判準 (§9,同 basket_dispersion 三條結構) --------------------------
Q3_D_RED_GATE = 0.10
Q3_ERA_CONSIST = 2       # 三個已知時代 ≥2 個方向一致
Q3_M_POINT = -0.15
Q3_M_CI = -0.30
Q3_BEAR_GATE = -0.15


# ------------------------------------------------------------------------------
# 資料載入
# ------------------------------------------------------------------------------
def load_l1_c2():
    """L1 池 + C2 分數 (複算與 alpha_gate_lab 一致),限 2019+。"""
    obs = pd.read_parquet(OBS_ALPHA)
    obs = obs[(obs["adv20"] >= agl.ADV_FLOOR) & obs["listed_ok"].fillna(False)].copy()
    obs = obs[obs["as_of"] >= "2019-01-01"]
    parts = [obs.groupby("as_of")[f].rank(pct=True) * 100 for f in C2_POS]
    parts += [100 - obs.groupby("as_of")[f].rank(pct=True) * 100 for f in C2_NEG]
    obs["c2"] = pd.concat(parts, axis=1).mean(axis=1, skipna=True)

    agl.build_candidate(obs, C2_POS, C2_NEG, "_c2_ref")
    m = obs["c2"].notna() & obs["_c2_ref"].notna()
    corr = obs.loc[m, "c2"].corr(obs.loc[m, "_c2_ref"])
    diff = (obs.loc[m, "c2"] - obs.loc[m, "_c2_ref"]).abs().max()
    assert corr > 0.999999 and diff < 1e-9, f"C2 複算不一致:corr={corr}, maxdiff={diff}"
    obs = obs.drop(columns=["_c2_ref"])
    print(f"前置檢查(a):C2 複算 corr={corr:.8f} maxdiff={diff:.2e} ✓")
    return obs


def load_open_prices():
    """TEJ 種子 ∪ 官方快照 open/close (同 universe_screen_daily/shortlist_ledger 接縫)。"""
    con = duckdb.connect()
    tej_max = con.execute(f"""
        SELECT MAX(date) FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
    """).fetchone()[0]
    has_snap = SNAP_DIR.exists() and any(SNAP_DIR.glob("*.parquet"))
    snap_sql = f"""
        UNION ALL BY NAME
        SELECT stock_id, date, open, close
        FROM read_parquet('{SNAP_DIR}/*.parquet', union_by_name=true)
        WHERE date > '{tej_max}'""" if has_snap else ""
    px = con.execute(f"""
        SELECT stock_id, date, open, close
        FROM read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        {snap_sql}
    """).df()
    con.close()
    px["open"] = pd.to_numeric(px["open"], errors="coerce")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    return px.dropna(subset=["open", "close"], how="all")


def trading_calendar(px):
    cnt = px.groupby("date").size()
    return sorted(cnt[cnt >= MIN_STOCKS_PER_DAY].index)


def load_0050():
    if not BENCH_0050.exists():
        print("[警告] 0050 快取不存在,vs 0050 對照將略過")
        return None
    df = pd.read_parquet(BENCH_0050)[["date", "open", "close"]].sort_values("date")
    df = df.reset_index(drop=True)
    # 股票分割還原:FinMind 快取為未還原股價 (0050 於 2025-06-18 1拆4,單日 -74.8%)。
    # 偵測單日跌幅 >50% 視為分割,以前收/當收湊整為分割比,回溯除以該比。
    ret = df["close"].pct_change()
    for i in df.index[ret < -0.5]:
        ratio = round(df.loc[i - 1, "close"] / df.loc[i, "close"])
        if ratio >= 2:
            df.loc[:i - 1, ["open", "close"]] /= ratio
            print(f"[0050 分割還原] {df.loc[i, 'date']} 偵測 1拆{ratio},"
                  f"{df.loc[i - 1, 'date']} (含) 以前價格已除以 {ratio}")
    last = pd.to_datetime(df["date"]).max()
    age = (pd.Timestamp.today().normalize() - last).days
    if age > 7:
        print(f"[前置檢查(c)] 0050 快取截至 {last.date()},已 {age} 天未更新;"
              f"三個判準時代 (2019-2025) 完整涵蓋,僅 2026YTD 健檢可能略短 (S2)")
    else:
        print(f"[前置檢查(c)] 0050 快取新鮮 (截至 {last.date()}) ✓")
    return df


# ------------------------------------------------------------------------------
# 籃子序列
# ------------------------------------------------------------------------------
def top_k_basket(g, k=K):
    ranked = g.sort_values(["c2", "stock_id"], ascending=[False, True])
    return ranked.head(k)


def basket_sequence(obs, grid, k=K):
    """每期 top-k C2 籃 (確定性排序,tie-break stock_id 升冪)。"""
    seqs = []
    for t, g in obs[obs["as_of"].isin(grid)].groupby("as_of"):
        top = top_k_basket(g, k)
        if len(top) < k:
            print(f"  [警告] {t} 籃子僅 {len(top)} 檔 (<{k}),跳過")
            continue
        seqs.append((t, top))
    return sorted(seqs, key=lambda x: x[0])


def monthly_grid(obs):
    return sorted(obs["as_of"].unique())


def quarterly_grid(dates):
    return dates[::3]


def era_slice(rows, s, e, col="as_of"):
    return rows[(rows[col] >= s) & (rows[col] <= e)]


# ------------------------------------------------------------------------------
# 價格錨點 (T+offset 開盤 或 T 收盤)
# ------------------------------------------------------------------------------
def px_by_date_index(px):
    return {d: g.set_index("stock_id") for d, g in px.groupby("date")}


def anchor(px_idx, cal, cal_idx, as_of, field, offset):
    """回傳 (執行日期, DataFrame[stock_id, price]) 或 (None, None)。"""
    i0 = cal_idx.get(as_of)
    if i0 is None or i0 + offset >= len(cal) or i0 + offset < 0:
        return None, None
    d = cal[i0 + offset]
    df = px_idx.get(d)
    if df is None:
        return d, None
    return d, df[[field]].rename(columns={field: "price"})


# ------------------------------------------------------------------------------
# Q1 — 節奏與成本
# ------------------------------------------------------------------------------
def simulate_cadence(seqs, px_idx, cal, cal_idx, field="open", offset=1):
    """逐期 T+offset(field) 進出場,continuing 免成本,只對 entering/exiting 收費。"""
    rows = []
    for i in range(len(seqs) - 1):
        t_i, basket_i = seqs[i]
        t_next, basket_next = seqs[i + 1]
        _, p_in = anchor(px_idx, cal, cal_idx, t_i, field, offset)
        _, p_out = anchor(px_idx, cal, cal_idx, t_next, field, offset)
        if p_in is None or p_out is None:
            continue
        ids_i = set(basket_i["stock_id"])
        ids_next = set(basket_next["stock_id"])
        prev_ids = set(seqs[i - 1][1]["stock_id"]) if i > 0 else set()
        entering = len(ids_i - prev_ids)
        exiting = len(ids_i - ids_next)

        merged = basket_i[["stock_id"]].merge(p_in, on="stock_id", how="left") \
                                        .merge(p_out, on="stock_id", how="left",
                                              suffixes=("_in", "_out"))
        merged = merged.dropna()
        missing = K - len(merged)
        if len(merged) < K * 0.5:
            continue
        ret = (merged["price_out"] / merged["price_in"] - 1.0)
        gross = float(ret.mean())
        cost = (entering * BUY_COST + exiting * SELL_COST) / K
        rows.append({"as_of": t_i, "next": t_next, "gross": gross, "cost": cost,
                     "net": gross - cost, "entering": entering, "exiting": exiting,
                     "missing": missing, "n": len(merged)})
    return pd.DataFrame(rows)


def equity_stats(rows, ret_col, periods_per_year):
    if rows.empty:
        return {}
    eq = (1.0 + rows[ret_col]).cumprod()
    peak = eq.cummax()
    dd = (eq / peak - 1.0).min() * 100.0
    total = eq.iloc[-1] - 1.0
    years = len(rows) / periods_per_year
    cagr = ((1.0 + total) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else np.nan
    ann_mean = rows[ret_col].mean() * periods_per_year * 100.0
    ann_vol = rows[ret_col].std(ddof=1) * np.sqrt(periods_per_year) * 100.0
    sharpe = ann_mean / ann_vol if ann_vol else np.nan
    return {"total_ret": total * 100.0, "cagr": cagr, "max_dd": dd, "sharpe": sharpe,
            "ann_mean": ann_mean, "n_periods": len(rows)}


def bench_0050_stats(df0050, start, end, periods_per_year):
    if df0050 is None:
        return {}
    d = df0050[(df0050["date"] >= start) & (df0050["date"] <= end)].copy()
    if len(d) < 20:
        return {}
    d["ret"] = d["close"].pct_change()
    d = d.dropna()
    eq = (1.0 + d["ret"]).cumprod()
    eq.iloc[0] *= (1.0 - BUY_COST)          # 期初一次性買入手續費
    peak = eq.cummax()
    dd = (eq / peak - 1.0).min() * 100.0
    total = eq.iloc[-1] - 1.0
    years = len(d) / 252.0
    cagr = ((1.0 + total) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else np.nan
    return {"total_ret": total * 100.0, "cagr": cagr, "max_dd": dd, "n_days": len(d)}


def periods_per_year_est(seqs, cal_idx):
    gaps = [cal_idx[seqs[i + 1][0]] - cal_idx[seqs[i][0]] for i in range(len(seqs) - 1)
            if seqs[i][0] in cal_idx and seqs[i + 1][0] in cal_idx]
    return 252.0 / np.median(gaps) if gaps else np.nan


def stationary_boot_idx(rng, n):
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    for i in range(1, n):
        idx[i] = rng.integers(n) if rng.random() < BOOT_P else (idx[i - 1] + 1) % n
    return idx


def boot_diff(a, b, seed_tag):
    """全期淨報酬差 (季度-月度) 點估 + 95% CI,對「期」重抽 (需先對齊索引)。"""
    n = min(len(a), len(b))
    rng = np.random.default_rng([SEED, seed_tag])
    diffs = np.empty(N_BOOT)
    a, b = a[:n], b[:n]
    for i in range(N_BOOT):
        idx = stationary_boot_idx(rng, n)
        diffs[i] = a[idx].mean() - b[idx].mean()
    pt = a.mean() - b.mean()
    return pt, np.percentile(diffs, [2.5, 97.5])


def run_q1(obs, px, cal, cal_idx, df0050):
    print("\n" + "=" * 78)
    print("Q1 — 再平衡節奏:月度 vs 季度 (K=8,T+1開盤執行,含真實周轉成本)")
    print("=" * 78)
    px_idx = px_by_date_index(px)
    m_dates = monthly_grid(obs)
    q_dates = quarterly_grid(m_dates)
    m_seqs = basket_sequence(obs, m_dates)
    q_seqs = basket_sequence(obs, q_dates)

    m_rows = simulate_cadence(m_seqs, px_idx, cal, cal_idx)
    q_rows = simulate_cadence(q_seqs, px_idx, cal, cal_idx)
    m_rows.to_parquet(SCRATCH_NEW / "q1_monthly.parquet", index=False)
    q_rows.to_parquet(SCRATCH_NEW / "q1_quarterly.parquet", index=False)

    ppy_m = periods_per_year_est(m_seqs, cal_idx)
    ppy_q = periods_per_year_est(q_seqs, cal_idx)
    print(f"月度:{len(m_rows)} 期完整 (約 {ppy_m:.1f} 期/年);"
          f"季度:{len(q_rows)} 期完整 (約 {ppy_q:.1f} 期/年)")
    print(f"缺值:月度平均 {m_rows['missing'].mean():.2f} 檔/期,季度平均 {q_rows['missing'].mean():.2f} 檔/期")

    for name, s, e in ERAS + [FULL, YTD26]:
        mm = era_slice(m_rows, s, e)
        qq = era_slice(q_rows, s, e)
        if mm.empty or qq.empty:
            continue
        print(f"\n--- {name} ---")
        for label, rows, ppy in [("月度", mm, ppy_m), ("季度", qq, ppy_q)]:
            st = equity_stats(rows, "net", ppy)
            gst = equity_stats(rows, "gross", ppy)
            print(f"  {label}:毛年化 {gst.get('ann_mean', np.nan):+.2f}%  淨年化 {st.get('ann_mean', np.nan):+.2f}%"
                  f"  年化成本drag {gst.get('ann_mean',0)-st.get('ann_mean',0):.2f}pp"
                  f"  MDD {st.get('max_dd', np.nan):.1f}%  Sharpe {st.get('sharpe', np.nan):.2f}"
                  f"  平均周轉 {rows['entering'].mean()+rows['exiting'].mean():.1f}檔/期")
        b = bench_0050_stats(df0050, s, e, 252.0)
        if b:
            print(f"  0050  :總報酬 {b['total_ret']:+.1f}%  CAGR {b['cagr']:+.2f}%  MDD {b['max_dd']:.1f}%")

    # 判準 (§9):全期 bootstrap
    print("\n--- Q1 判準 (全期 2019-2025,對「期」bootstrap) ---")
    mm = era_slice(m_rows, *FULL[1:])
    qq = era_slice(q_rows, *FULL[1:])
    pt, ci = boot_diff(qq["net"].to_numpy(), mm["net"].to_numpy(), seed_tag=1)
    print(f"季度淨報酬 − 月度淨報酬 (每期):{pt:+.4%} CI[{ci[0]:+.4%},{ci[1]:+.4%}]")
    m_bear = equity_stats(era_slice(m_rows, *ERAS[1][1:]), "net", ppy_m)
    q_bear = equity_stats(era_slice(q_rows, *ERAS[1][1:]), "net", ppy_q)
    m_dd, q_dd = m_bear.get("max_dd", np.nan), q_bear.get("max_dd", np.nan)
    if ci[0] > 0:
        winner = "季度(統計顯著勝出)"
    elif ci[1] < 0:
        winner = "月度(統計顯著勝出)"
    else:
        winner = "季度(CI含0,依預註冊平手規則採低周轉)"
    # 條2:勝出節奏的 2022 回撤不得比另一節奏深 >3pp (MDD 為負,越小越深)
    print(f"2022空頭 MDD:月度 {m_dd:.1f}% vs 季度 {q_dd:.1f}%")
    if winner.startswith("季度") and (m_dd - q_dd) > Q1_BEAR_DD_TOL:
        winner = f"月度(季度依條1勝出,但2022回撤深 {m_dd - q_dd:.1f}pp >3pp容忍 → 條2改採防禦較佳者)"
    elif winner.startswith("月度") and (q_dd - m_dd) > Q1_BEAR_DD_TOL:
        winner = f"季度(月度依條1勝出,但2022回撤深 {q_dd - m_dd:.1f}pp >3pp容忍 → 條2改採防禦較佳者)"
    print(f"判定:{winner}")
    return m_rows, q_rows


# ------------------------------------------------------------------------------
# Q2 — 執行落後代價
# ------------------------------------------------------------------------------
def excess_series(obs, seqs, px_idx, cal, cal_idx, field, offset, hold_days):
    """top-8 籃 vs 當期 L1 池均值的 20 日超額報酬 (固定窗,idealized 用 close/offset0,realistic 用 open/offset1)。"""
    rows = []
    obs_by_date = dict(tuple(obs.groupby("as_of")))
    for t, basket in seqs:
        _, p_in = anchor(px_idx, cal, cal_idx, t, field, offset)
        if p_in is None:
            continue
        i0 = cal_idx.get(t)
        if i0 is None or i0 + offset + hold_days >= len(cal):
            continue
        exit_date = cal[i0 + offset + hold_days]
        p_out = px_idx.get(exit_date)
        if p_out is None:
            continue
        p_out = p_out[[field]].rename(columns={field: "price"})

        pool = obs_by_date[t][["stock_id"]]
        pm = pool.merge(p_in, on="stock_id", how="left").merge(
            p_out, on="stock_id", how="left", suffixes=("_in", "_out")).dropna()
        if len(pm) < 100:
            continue
        pool_ret = (pm["price_out"] / pm["price_in"] - 1.0).mean()

        bm = basket[["stock_id"]].merge(p_in, on="stock_id", how="left").merge(
            p_out, on="stock_id", how="left", suffixes=("_in", "_out")).dropna()
        if len(bm) < K * 0.5:
            continue
        basket_ret = (bm["price_out"] / bm["price_in"] - 1.0).mean()
        rows.append({"as_of": t, "basket_ret": basket_ret, "pool_ret": pool_ret,
                     "excess": basket_ret - pool_ret})
    return pd.DataFrame(rows)


def run_q2(obs, px, cal, cal_idx):
    print("\n" + "=" * 78)
    print(f"Q2 — 執行落後代價:理想化(T收盤) vs 實際(T+1開盤),固定 {HOLD_DAYS} 交易日窗")
    print("=" * 78)
    px_idx = px_by_date_index(px)
    m_dates = monthly_grid(obs)
    seqs = basket_sequence(obs, m_dates)

    ideal = excess_series(obs, seqs, px_idx, cal, cal_idx, "close", 0, HOLD_DAYS)
    real = excess_series(obs, seqs, px_idx, cal, cal_idx, "open", 1, HOLD_DAYS)
    join_rate = len(real) / len(seqs) if seqs else 0
    print(f"前置檢查(b):T+1 開盤 join 率 {join_rate:.1%} ({len(real)}/{len(seqs)} 期)")

    for name, s, e in ERAS + [FULL]:
        di = era_slice(ideal, s, e)
        dr = era_slice(real, s, e)
        if di.empty or dr.empty:
            continue
        ei, er = di["excess"].mean(), dr["excess"].mean()
        retention = er / ei if ei else np.nan
        flag = "" if retention >= Q2_RETENTION_WARN else " ⚠ <50%,建議升高盤中即時優先序"
        print(f"  {name}:理想化超額 {ei:+.3%}  實際超額 {er:+.3%}  edge保留率 {retention:+.1%}{flag}")

    return ideal, real


# ------------------------------------------------------------------------------
# Q3 — 分批進場
# ------------------------------------------------------------------------------
def batched_entry_price(px_idx, cal, cal_idx, as_of, schedule):
    prices = []
    for off in schedule:
        _, p = anchor(px_idx, cal, cal_idx, as_of, "open", off)
        if p is None:
            return None
        prices.append(p.rename(columns={"price": f"p{off}"}))
    merged = prices[0]
    for p in prices[1:]:
        merged = merged.join(p, how="outer")
    merged = merged.dropna()
    merged["blended"] = merged[[c for c in merged.columns]].mean(axis=1)
    return merged[["blended"]]


def entering_events(seqs):
    events = []
    for i in range(1, len(seqs)):
        t_i, basket_i = seqs[i]
        prev_ids = set(seqs[i - 1][1]["stock_id"])
        new = basket_i[~basket_i["stock_id"].isin(prev_ids)]
        for sid in new["stock_id"]:
            events.append((t_i, sid))
    return events


def run_q3(obs, px, cal, cal_idx):
    print("\n" + "=" * 78)
    print(f"Q3 — 分批進場:lump/batch2/batch3 (僅新進榜部位,固定 {HOLD_DAYS} 交易日出場)")
    print("=" * 78)
    px_idx = px_by_date_index(px)
    m_dates = monthly_grid(obs)
    seqs = basket_sequence(obs, m_dates)
    events = entering_events(seqs)
    print(f"新進榜事件總數:{len(events)} (跨 {len(seqs)-1} 個再平衡期)")

    rows = []
    for t, sid in events:
        i0 = cal_idx.get(t)
        if i0 is None or i0 + 1 + HOLD_DAYS >= len(cal):
            continue
        exit_date = cal[i0 + 1 + HOLD_DAYS]
        exit_df = px_idx.get(exit_date)
        if exit_df is None or sid not in exit_df.index:
            continue
        exit_px = exit_df.loc[sid, "open"]
        rec = {"as_of": t, "stock_id": sid}
        ok = True
        for name, sched in BATCH_OFFSETS.items():
            blended = batched_entry_price(px_idx, cal, cal_idx, t, sched)
            if blended is None or sid not in blended.index:
                ok = False
                break
            entry_px = blended.loc[sid, "blended"]
            rec[f"ret_{name}"] = exit_px / entry_px - 1.0
        if ok:
            rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(SCRATCH_NEW / "q3_events.parquet", index=False)
    print(f"可評估事件:{len(df)} ({len(df)/max(len(events),1):.1%} 覆蓋)")

    for name, s, e in ERAS + [FULL]:
        d = era_slice(df, s, e)
        if len(d) < 20:
            continue
        print(f"\n--- {name} (n={len(d)}) ---")
        for sched in BATCH_OFFSETS:
            col = f"ret_{sched}"
            print(f"  {sched:<8} D={d[col].std(ddof=1)*100:.2f}%  M={d[col].mean()*100:+.3f}%")

    print("\n--- Q3 判準 @全期 (bootstrap 對「期」重抽) ---")
    full = era_slice(df, *FULL[1:])
    bear = era_slice(df, *ERAS[1][1:])
    for sched in ["batch2", "batch3"]:
        col, base = f"ret_{sched}", "ret_lump"
        piv = full.groupby("as_of").apply(
            lambda g: pd.Series({"D_x": g[col].std(ddof=0), "D_0": g[base].std(ddof=0),
                                 "M_x": g[col].mean(), "M_0": g[base].mean()}),
            include_groups=False)
        piv = piv.dropna()
        n = len(piv)
        dred_pt = 1.0 - piv["D_x"].mean() / piv["D_0"].mean()
        dm_pt = piv["M_x"].mean() - piv["M_0"].mean()
        rng = np.random.default_rng([SEED, 777, hash(sched) % 1000])
        dreds, dms = np.empty(N_BOOT), np.empty(N_BOOT)
        for b in range(N_BOOT):
            idx = stationary_boot_idx(rng, n)
            dreds[b] = 1.0 - piv["D_x"].to_numpy()[idx].mean() / piv["D_0"].to_numpy()[idx].mean()
            dms[b] = piv["M_x"].to_numpy()[idx].mean() - piv["M_0"].to_numpy()[idx].mean()
        dred_ci = np.percentile(dreds, [2.5, 97.5])
        dm_ci = np.percentile(dms, [2.5, 97.5]) * 100
        era_dir = [era_slice(df, s, e).groupby("as_of").apply(
                    lambda g: g[col].std(ddof=0) < g[base].std(ddof=0), include_groups=False).mean() > 0.5
                  for _, s, e in ERAS if len(era_slice(df, s, e)) >= 20]
        consist = sum(era_dir)
        bear_dm = (bear[col].mean() - bear[base].mean()) * 100 if len(bear) >= 20 else np.nan

        g1 = dred_pt >= Q3_D_RED_GATE and consist >= Q3_ERA_CONSIST
        g2 = dm_pt * 100 > Q3_M_POINT and dm_ci[0] > Q3_M_CI
        g3 = (bear_dm >= Q3_BEAR_GATE) if not np.isnan(bear_dm) else True
        print(f"\n{sched}(n={n}期): D降幅 {dred_pt:+.1%} CI[{dred_ci[0]:+.1%},{dred_ci[1]:+.1%}]"
              f" 時代一致 {consist}/3 → 條1 {'✓' if g1 else '✗'}")
        print(f"        ΔM {dm_pt*100:+.3f}% CI[{dm_ci[0]:+.3f},{dm_ci[1]:+.3f}]"
              f" → 條2 {'✓' if g2 else '✗'};2022 ΔM {bear_dm:+.3f} → 條3 {'✓' if g3 else '✗'}")
        print(f"        判定:{'採用批次進場' if all((g1,g2,g3)) else '維持整批(lump)為預設'}")
    return df


# ------------------------------------------------------------------------------
# 敏感度
# ------------------------------------------------------------------------------
def run_sensitivity(obs, px, cal, cal_idx, df0050):
    print("\n" + "=" * 78)
    print("S1 — K=10/K=12 重跑 Q1 全期淨報酬 (驗證節奏結論不因錨點翻轉)")
    print("=" * 78)
    px_idx = px_by_date_index(px)
    m_dates = monthly_grid(obs)
    q_dates = quarterly_grid(m_dates)
    for k in (10, 12):
        m_seqs = basket_sequence(obs, m_dates, k=k)
        q_seqs = basket_sequence(obs, q_dates, k=k)
        m_rows = simulate_cadence(m_seqs, px_idx, cal, cal_idx)
        q_rows = simulate_cadence(q_seqs, px_idx, cal, cal_idx)
        ppy_m, ppy_q = periods_per_year_est(m_seqs, cal_idx), periods_per_year_est(q_seqs, cal_idx)
        mf, qf = era_slice(m_rows, *FULL[1:]), era_slice(q_rows, *FULL[1:])
        sm, sq = equity_stats(mf, "net", ppy_m), equity_stats(qf, "net", ppy_q)
        print(f"  K={k}: 月度淨年化 {sm.get('ann_mean',np.nan):+.2f}% (MDD {sm.get('max_dd',np.nan):.1f}%)"
              f"  季度淨年化 {sq.get('ann_mean',np.nan):+.2f}% (MDD {sq.get('max_dd',np.nan):.1f}%)")

    print("\n" + "=" * 78)
    print("S3 — 2026 YTD 健檢 (K=8,樣本不足不評判準)")
    print("=" * 78)
    m_seqs = basket_sequence(obs, m_dates)
    m_rows = simulate_cadence(m_seqs, px_idx, cal, cal_idx)
    ytd = era_slice(m_rows, *YTD26[1:])
    if len(ytd):
        print(f"  期數 {len(ytd)}, 淨報酬均值 {ytd['net'].mean()*100:+.2f}%/期")
    else:
        print("  無可用期")


# ------------------------------------------------------------------------------
# --plan:實盤操作卡 (套用已判定規則,非新假設;預註冊 §9 判定結果的報告層)
# ------------------------------------------------------------------------------
POOL_DIR = Path(__file__).resolve().parent.parent / "outputs" / "universe_pool"


def overnight_gap_band(obs, px_idx, cal, cal_idx):
    """歷史 top-8 的隔夜跳空 (T收盤→T+1開盤) 分布 → 買進價格區間帶寬。"""
    seqs = basket_sequence(obs, monthly_grid(obs))
    gaps = []
    for t, basket in seqs:
        _, pc = anchor(px_idx, cal, cal_idx, t, "close", 0)
        _, po = anchor(px_idx, cal, cal_idx, t, "open", 1)
        if pc is None or po is None:
            continue
        m = basket[["stock_id"]].merge(pc, on="stock_id", how="left") \
                                 .merge(po, on="stock_id", how="left",
                                        suffixes=("_c", "_o")).dropna()
        gaps.extend((m["price_o"] / m["price_c"] - 1.0).tolist())
    g = np.asarray(gaps)
    return np.percentile(g, [10, 50, 90]), len(g)


def latest_frozen_cohort():
    """最新含 c2_score 的凍結名單:pool 優先 (全池),退 shortlist (圈人子集)。"""
    for f in sorted(POOL_DIR.glob("pool_*.csv"), reverse=True):
        df = pd.read_csv(f, encoding="utf-8-sig", dtype={"stock_id": str})
        date = f.stem.replace("pool_", "")
        if "c2_score" in df.columns:
            return date, df, "pool(全池)"
        sf = POOL_DIR / f"shortlist_{date}.csv"
        if sf.exists():
            sl = pd.read_csv(sf, encoding="utf-8-sig", dtype={"stock_id": str})
            if "c2_score" in sl.columns:
                return date, sl, "shortlist(圈人子集,7/20 起 pool 檔將含 c2 改用全池)"
    return None, None, None


def run_plan(obs, px, cal, cal_idx):
    print("\n" + "=" * 78)
    print("實盤操作卡 (套用本輪判定:季度再平衡・整批進場・T+1 開盤執行)")
    print("=" * 78)
    px_idx = px_by_date_index(px)
    (p10, p50, p90), n_gap = overnight_gap_band(obs, px_idx, cal, cal_idx)
    print(f"買進區間帶寬 = 歷史 top-8 隔夜跳空 p10~p90 (n={n_gap}):"
          f" {p10:+.2%} ~ {p50:+.2%} ~ {p90:+.2%}")

    date, df, src = latest_frozen_cohort()
    if df is None:
        print("找不到含 c2_score 的凍結名單")
        return
    top = df.nlargest(K, "c2_score")
    entry_est = (pd.Timestamp(date) + pd.tseries.offsets.BDay(1)).date()
    exit_lo = (pd.Timestamp(date) + pd.tseries.offsets.BDay(59)).date()
    exit_hi = (pd.Timestamp(date) + pd.tseries.offsets.BDay(64)).date()
    print(f"\n名單凍結日:{date} (來源:{src})")
    print(f"買進時間:下一交易日開盤 (約 {entry_est},整批,不分批 — Q3 判定)")
    print(f"賣出時間區間:進場後約 60 交易日 (約 {exit_lo} ~ {exit_hi}) 的季度再平衡 —")
    print(f"  屆時以最新 C2 排名複核:續留 top-{K} 者不賣 (零成本延續),掉出者於次日開盤賣出")
    print(f"\n{'#':<3}{'代號':<7}{'名稱':<8}{'凍結收盤':>9}{'買進下緣':>9}{'買進參考':>9}{'買進上緣':>9}  c2")
    rows = []
    for i, (_, r) in enumerate(top.iterrows(), 1):
        c = float(r["close"])
        lo, ref, hi = c * (1 + p10), c * (1 + p50), c * (1 + p90)
        print(f"{i:<3}{r['stock_id']:<7}{str(r.get('name', '')):<8}"
              f"{c:>9.2f}{lo:>9.2f}{ref:>9.2f}{hi:>9.2f}  {r['c2_score']:.1f}")
        rows.append({"rank": i, "stock_id": r["stock_id"], "name": r.get("name", ""),
                     "frozen_close": c, "buy_low": round(lo, 2), "buy_ref": round(ref, 2),
                     "buy_high": round(hi, 2), "c2_score": r["c2_score"],
                     "entry_date_est": str(entry_est), "exit_window": f"{exit_lo}~{exit_hi}",
                     "frozen_date": date})
    out = POOL_DIR / f"plan_{date}.csv"
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n注意:買進區間為歷史跳空分布的統計帶,開盤價落帶外 (約 1/5 機率) 屬正常,"
          f"\n      Q2 已證 T+1 開盤市價執行不損 edge (全期保留率 143%),不建議因等待帶內價而錯過進場。")
    print(f"操作卡已寫 {out}")


# ------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cadence", action="store_true")
    ap.add_argument("--lag", action="store_true")
    ap.add_argument("--batching", action="store_true")
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--plan", action="store_true",
                    help="實盤操作卡:買進時間/價格區間/賣出時間區間 (套用已判定規則)")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if not any([args.cadence, args.lag, args.batching, args.sensitivity, args.plan, args.all]):
        ap.print_help()
        return

    obs = load_l1_c2()
    px = load_open_prices()
    cal = trading_calendar(px)
    cal_idx = {d: i for i, d in enumerate(cal)}
    df0050 = load_0050()
    print(f"L1+C2 觀測:{len(obs)} 列 / {obs['as_of'].nunique()} 期 (2019-01 起);"
          f"價格資料 {len(cal)} 交易日,截至 {cal[-1]}")

    if args.cadence or args.all:
        run_q1(obs, px, cal, cal_idx, df0050)
    if args.lag or args.all:
        run_q2(obs, px, cal, cal_idx)
    if args.batching or args.all:
        run_q3(obs, px, cal, cal_idx)
    if args.sensitivity or args.all:
        run_sensitivity(obs, px, cal, cal_idx, df0050)
    if args.plan or args.all:
        run_plan(obs, px, cal, cal_idx)


if __name__ == "__main__":
    main()
