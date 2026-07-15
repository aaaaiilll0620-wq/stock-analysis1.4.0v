"""升級版 TEJ 粗篩層實驗:用新增的長視野因子 (mom60/120、52週高點接近度、
連續四季EPS、3月平滑營收YoY) 測試「更聰明的排除規則」。
母體 = L1 可投資性 (20日均額>=10M + 上市滿年)。指標同 funnel_test。"""
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

OBS = r"C:\Users\aaaai\AppData\Local\Temp\claude\C--Users-aaaai-OneDrive-Desktop-Project-1\b3b44244-0d70-4d10-a97b-ca40f0e07343\scratchpad\obs_dump_v2.parquet"
TEJ = Path.home() / "tej_cache"
PERIODS = ["2023-2025", "2022空頭", "2019-2021(樣本外)"]
ADV_FLOOR = 10_000_000

obs = pd.read_parquet(OBS)
con = duckdb.connect()
liq = con.execute(f"""
    SELECT stock_id, date,
           AVG(close * Trading_Volume) OVER (PARTITION BY stock_id ORDER BY date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
           MIN(date) OVER (PARTITION BY stock_id) AS first_date
    FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
""").df()
con.close()
liq["listed_ok"] = ((liq["first_date"] <= "2019-01-10") |
                     ((pd.to_datetime(liq["date"]) - pd.to_datetime(liq["first_date"])).dt.days >= 365))
obs = obs.merge(liq[["stock_id", "date", "adv20", "listed_ok"]],
                left_on=["stock_id", "as_of"], right_on=["stock_id", "date"], how="left")

def pctize(day):
    day = day.copy()
    for f in ("value", "momentum", "chip", "mom60", "mom120", "high52_prox"):
        day[f"{f}_pct"] = day[f].rank(pct=True) * 100.0
    return day

def stats(pools, full_days):
    ns, rec, ex, keeps = [], [], [], []
    for kept, full in zip(pools, full_days):
        ns.append(len(kept))
        winners = full["fwd"].rank(pct=True) > 0.9
        rec.append(winners[kept.index].sum() / max(winners.sum(), 1))
        ex.append(kept["fwd"].mean() - full["fwd"].mean())
    for a, b in zip(pools[:-1], pools[1:]):
        sa, sb = set(a["stock_id"]), set(b["stock_id"])
        if sa:
            keeps.append(len(sa & sb) / len(sa))
    return (f"{np.mean(ns):5.0f}檔 召回{np.mean(rec)*100:5.1f}% "
            f"超額{np.mean(ex):+.3f} 留存{np.mean(keeps)*100:5.1f}%")

nan = lambda s: s.isna()

# --- 排除規則 (True=排除)。NaN 原則:財報/營收類 NaN 放行 (金融股/新資料),價格類 NaN 放行 ---
EXCL = [
    ("L2 現行 (value>90 且 單月YoY<=0)",
     lambda d: (d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0)),
    ("E1 陷阱升級: value>90 且 3月YoY<=0",
     lambda d: (d["value_pct"] > 90) & ~(d["rev_yoy_3m"] > 0)),
    ("E2 長期虧損: 近4季EPS全<=0",
     lambda d: d["eps_pos_q4"] == 0),
    ("E3 深度破位: 距52週高 <50%",
     lambda d: d["high52_prox"] < 50),
    ("E4 破位且衰退: 距高<60% 且 3月YoY<=0",
     lambda d: (d["high52_prox"] < 60) & ~(d["rev_yoy_3m"] > 0)),
    ("E5 長動能崩壞: mom120 < -30%",
     lambda d: d["mom120"] < -30),
]

for p in PERIODS:
    full_days = [d for _, d in obs[obs["period"] == p].groupby("as_of") if len(d) >= 20]
    l1 = [pctize(d[(d["adv20"] >= ADV_FLOOR) & d["listed_ok"].fillna(False)]) for d in full_days]
    print(f"\n[{p}]  L1 基準: {stats(l1, full_days)}")
    for label, rule in EXCL:
        pools = [d[~rule(d).fillna(False)] for d in l1]
        print(f"  L1+{label:<34} {stats(pools, full_days)}")
    # 組合拳:現行L2 + 長期虧損 + 破位且衰退
    combo = lambda d: (((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0)) |
                        (d["eps_pos_q4"] == 0) |
                        ((d["high52_prox"] < 60) & ~(d["rev_yoy_3m"] > 0)))
    pools = [d[~combo(d).fillna(False)] for d in l1]
    print(f"  L1+組合拳 (L2+E2+E4){'':<18} {stats(pools, full_days)}")
