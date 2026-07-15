"""全系統 2005-2018 樣本外總驗收 (0 API)
================================================================================
整套 L0-L2 粗篩 + 五因子 shortlist 設計於 2019-2026;本腳本在 2005-2018 純樣本外
(含 2008 海嘯、2011、2015-16、2018Q4,母體含下市股) 驗收三個問題:
  Q1 產業中性化在 2008 等年代是否成立 (value decile10:全市場排名 vs 產業內排名)
  Q2 L2 陷阱排除是否依然「只賺不賠」(L1 → L1+L2 的超額/召回變化)
  Q3 五因子聯集 shortlist 的召回/超額/留存衰減幅度
"""
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

SCRATCH = Path(r"C:\Users\aaaai\AppData\Local\Temp\claude\C--Users-aaaai-OneDrive-Desktop-Project-1\b3b44244-0d70-4d10-a97b-ca40f0e07343\scratchpad")
TEJ = Path.home() / "tej_cache"
ADV_FLOOR = 10_000_000
ERAS = [
    ("2005-2009 樣本外(含海嘯)", "2005-01-01", "2009-12-31"),
    ("2010-2014 樣本外", "2010-01-01", "2014-12-31"),
    ("2015-2018 樣本外", "2015-01-01", "2018-12-31"),
    ("2019-2026 設計期(對照)", "2019-01-01", "2026-05-31"),
]

obs = pd.read_parquet(SCRATCH / "obs_dump_full.parquet")
ind = pd.read_parquet(TEJ / "industry_map.parquet")[["stock_id", "tej_ind_name"]]
obs = obs.merge(ind, on="stock_id", how="left")
obs["rev_accel"] = obs["revenue_yoy"] - obs["rev_yoy_3m"]

# 產業內 value (研究版全歷史;分組<5 退回全市場)
grp = obs.groupby(["as_of", "tej_ind_name"])["value"]
vind = grp.rank(pct=True) * 100
size = grp.transform("size")
mkt = obs.groupby("as_of")["value"].rank(pct=True) * 100
obs["value_ind"] = vind.where(size >= 5, mkt)
obs["value_mkt"] = mkt

liq = duckdb.connect().execute(f"""
    SELECT stock_id, date,
           AVG(close * Trading_Volume) OVER (PARTITION BY stock_id ORDER BY date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
           MIN(date) OVER (PARTITION BY stock_id) AS first_date
    FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
""").df()
liq["listed_ok"] = ((liq["first_date"] <= "2004-01-15") |
                     ((pd.to_datetime(liq["date"]) - pd.to_datetime(liq["first_date"])).dt.days >= 365))
obs = obs.merge(liq[["stock_id", "date", "adv20", "listed_ok"]],
                left_on=["stock_id", "as_of"], right_on=["stock_id", "date"], how="left")

FACTORS = ["value_ind", "momentum", "chip", "high52_prox", "rev_accel"]


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
    return (f"{np.mean(ns):5.0f}檔 召回{np.mean(rec)*100:5.1f}% "
            f"超額{np.nanmean(ex):+.3f} 留存{np.mean(keeps)*100:5.1f}%")


for era, start, end in ERAS:
    sub = obs[(obs["as_of"] >= start) & (obs["as_of"] <= end)]
    full_days = [d for _, d in sub.groupby("as_of") if len(d) >= 20]
    if not full_days:
        continue
    print("\n" + "=" * 78)
    print(f"【{era}】 全市場平均 {np.mean([len(d) for d in full_days]):.0f} 檔/月")

    # ---- Q1: value decile 10 — 全市場排名 vs 產業內排名 (全市場母體) ----
    d10 = {"value_mkt": [], "value_ind": []}
    for d in full_days:
        excess = d["fwd"] - d["fwd"].mean()
        for k in d10:
            r = d[k].rank(pct=True)
            d10[k].append(excess[r > 0.9].mean())
    print(f"  Q1 decile10 (最便宜10%): 全市場排名 {np.nanmean(d10['value_mkt']):+.3f}"
          f"  產業內排名 {np.nanmean(d10['value_ind']):+.3f}"
          f"  (產業中性化改善 {np.nanmean(d10['value_ind'])-np.nanmean(d10['value_mkt']):+.3f})")

    # ---- Q2: L1 → L1+L2 ----
    l1 = []
    for d in full_days:
        d = d[(d["adv20"] >= ADV_FLOOR) & d["listed_ok"].fillna(False)].copy()
        d["value_pct"] = d["value"].rank(pct=True) * 100
        l1.append(d)
    l2 = [d[~((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0))] for d in l1]
    ntrap = np.mean([len(a) - len(b) for a, b in zip(l1, l2)])
    print(f"  Q2 L1 基準:      {stats(l1, full_days)}")
    print(f"     L1+L2 陷阱排除: {stats(l2, full_days)}  (每月排除 {ntrap:.0f} 檔)")

    # ---- Q3: 五因子聯集 shortlist ----
    l2f = []
    for d in l2:
        d = d.copy()
        for f in FACTORS:
            d[f"{f}_p"] = d[f].rank(pct=True) * 100
        l2f.append(d)
    pools = [d[np.logical_or.reduce([(d[f"{f}_p"] > 85).to_numpy() for f in FACTORS])]
             for d in l2f]
    print(f"  Q3 5F聯集 shortlist: {stats(pools, full_days)}")
