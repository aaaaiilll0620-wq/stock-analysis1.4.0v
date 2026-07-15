"""但書2 三連測:①視野 20日 vs 60日 ②突破訊號(52週高接近度)當選股因子
③營收加速度當選股因子。母體 = L1+L2 候選池,聯集配方對決。
用法: python horizon_breakout_lab.py <dump路徑> <視野標籤>"""
import sys
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

DUMP = sys.argv[1]
LABEL = sys.argv[2] if len(sys.argv) > 2 else "?"
TEJ = Path.home() / "tej_cache"
MKT = Path.home() / "market_cache"
PERIODS = ["2023-2025", "2022空頭", "2019-2021(樣本外)"]
ADV_FLOOR = 10_000_000

obs = pd.read_parquet(DUMP)
ref = pd.read_parquet(MKT / "industry_value_ref.parquet",
                      columns=["stock_id", "date", "value_ind_pct"])
obs = obs.merge(ref.rename(columns={"date": "as_of"}), on=["stock_id", "as_of"], how="left")
# 營收加速度:最新單月 YoY − 近3月平均 YoY (二階導,轉正=加速)
obs["rev_accel"] = obs["revenue_yoy"] - obs["rev_yoy_3m"]

con = duckdb.connect()
liq = con.execute(f"""
    SELECT stock_id, date,
           AVG(close * Trading_Volume) OVER (PARTITION BY stock_id ORDER BY date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
           MIN(date) OVER (PARTITION BY stock_id) AS first_date
    FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
""").df()
liq["listed_ok"] = ((liq["first_date"] <= "2019-01-10") |
                     ((pd.to_datetime(liq["date"]) - pd.to_datetime(liq["first_date"])).dt.days >= 365))
obs = obs.merge(liq[["stock_id", "date", "adv20", "listed_ok"]],
                left_on=["stock_id", "as_of"], right_on=["stock_id", "date"], how="left")

FACTORS = ["value_ind_pct", "momentum", "chip", "high52_prox", "rev_accel"]


def build_l2(full_days):
    l2 = []
    for d in full_days:
        d = d[(d["adv20"] >= ADV_FLOOR) & d["listed_ok"].fillna(False)].copy()
        d["value_pct"] = d["value"].rank(pct=True) * 100
        d = d[~((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0))]
        for f in FACTORS:
            d[f"{f}_p"] = d[f].rank(pct=True) * 100
        l2.append(d)
    return l2


def stats(pools, full_days):
    ns, rec, ex, keeps = [], [], [], []
    for kept, full in zip(pools, full_days):
        ns.append(len(kept))
        w = full["fwd"].rank(pct=True) > 0.9
        rec.append(w[kept.index].sum() / max(w.sum(), 1))
        ex.append(kept["fwd"].mean() - full["fwd"].mean())
    for a, b in zip(pools[:-1], pools[1:]):
        sa, sb = set(a["stock_id"]), set(b["stock_id"])
        if sa:
            keeps.append(len(sa & sb) / len(sa))
    return (f"{np.mean(ns):4.0f}檔 召回{np.mean(rec)*100:5.1f}% "
            f"超額{np.mean(ex):+.3f} 留存{np.mean(keeps)*100:5.1f}%")


print(f"===== 視野 {LABEL} (超額單位 = %/{LABEL},跨視野比召回不比超額) =====")
for p in PERIODS:
    full_days = [d for _, d in obs[obs["period"] == p].groupby("as_of") if len(d) >= 20]
    l2 = build_l2(full_days)
    print(f"\n[{p}]  L2 池基準: {stats(l2, full_days)}")
    # ① 單因子前15% (選股力體檢)
    for f in FACTORS:
        pools = [d[d[f"{f}_p"] > 85] for d in l2]
        print(f"  單因子 {f:<16} {stats(pools, full_days)}")
    # ② 聯集配方對決
    u3 = lambda d: (d["value_ind_pct_p"] > 85) | (d["momentum_p"] > 85) | (d["chip_p"] > 85)
    recipes = [
        ("現行3F聯集", u3),
        ("3F+突破(高點接近)", lambda d: u3(d) | (d["high52_prox_p"] > 85)),
        ("3F+營收加速", lambda d: u3(d) | (d["rev_accel_p"] > 85)),
        ("5F全聯集", lambda d: u3(d) | (d["high52_prox_p"] > 85) | (d["rev_accel_p"] > 85)),
    ]
    for label, rule in recipes:
        pools = [d[rule(d)] for d in l2]
        print(f"  {label:<20} {stats(pools, full_days)}")
