"""四層排除式初篩漏斗實測 (算力夠版:第3層=砍 composite 後40%)。
L1 可投資性: 20日均成交金額 >= 門檻 且 上市滿一年
L2 陷阱排除: value_pct>90 且 營收YoY<=0(含NaN)   [百分位在 L1 後的存活母體重算]
L3 砍 composite 後 40%                            [同上母體]
L4 池內排序: composite (value cap 80 摺返) — 非過濾,只驗排序力
指標: 每月平均池檔數 / 贏家召回率(未來報酬前10%) / 池超額(%/月 vs 全市場=L0)。"""
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

OBS = r"C:\Users\aaaai\AppData\Local\Temp\claude\C--Users-aaaai-OneDrive-Desktop-Project-1\b3b44244-0d70-4d10-a97b-ca40f0e07343\scratchpad\obs_dump.parquet"
TEJ = Path.home() / "tej_cache"
PERIODS = ["2023-2025", "2022空頭", "2019-2021(樣本外)"]
ADV_FLOOR = 10_000_000   # 20日均成交金額下限 (NTD)
MIN_LISTED_DAYS = 365

obs = pd.read_parquet(OBS)

# 20日均成交金額 + 每檔資料起始日 (上市滿一年的代理;2019 前就存在者以資料起點計,只擋新IPO)
con = duckdb.connect()
liq = con.execute(f"""
    SELECT stock_id, date,
           AVG(close * Trading_Volume) OVER (
               PARTITION BY stock_id ORDER BY date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
           MIN(date) OVER (PARTITION BY stock_id) AS first_date
    FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
""").df()
con.close()
liq["days_listed"] = (pd.to_datetime(liq["date"]) - pd.to_datetime(liq["first_date"])).dt.days
# 資料起點 (2019-01) 就存在的股票不是新 IPO,上市滿一年規則只套用在起點之後才出現的股票
data_start_cutoff = "2019-01-10"
liq["listed_ok"] = (liq["first_date"] <= data_start_cutoff) | (liq["days_listed"] >= MIN_LISTED_DAYS)
obs = obs.merge(liq[["stock_id", "date", "adv20", "listed_ok"]],
                left_on=["stock_id", "as_of"], right_on=["stock_id", "date"], how="left")

def pctize(day):
    day = day.copy()
    for f in ("value", "momentum", "chip"):
        day[f"{f}_pct"] = day[f].rank(pct=True) * 100.0
    day["composite"] = day[["value_pct", "momentum_pct", "chip_pct"]].mean(axis=1)
    vc = day["value_pct"].where(day["value_pct"] <= 80, 160 - day["value_pct"])
    day["composite_cap"] = (vc + day["momentum_pct"] + day["chip_pct"]) / 3
    return day

def stats(kept_days, full_days):
    ns, rec, ex = [], [], []
    for kept, full in zip(kept_days, full_days):
        ns.append(len(kept))
        winners = full["fwd"].rank(pct=True) > 0.9
        rec.append(winners[kept.index].sum() / max(winners.sum(), 1))
        ex.append(kept["fwd"].mean() - full["fwd"].mean())
    return f"{np.mean(ns):6.0f}檔  召回{np.mean(rec)*100:5.1f}%  超額{np.mean(ex):+.3f}"

print(f"L1 門檻: 20日均成交金額 >= {ADV_FLOOR/1e6:.0f}M NTD 且 上市滿 {MIN_LISTED_DAYS} 天\n")
for p in PERIODS:
    full_days = [d for _, d in obs[obs["period"] == p].groupby("as_of") if len(d) >= 20]
    l1 = [d[(d["adv20"] >= ADV_FLOOR) & d["listed_ok"].fillna(False)] for d in full_days]
    l1 = [pctize(d) for d in l1]   # 百分位/composite 在 L1 存活母體上重算
    l2 = [d[~((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0))] for d in l1]
    l3 = [d[d["composite"].rank(pct=True) > 0.40] for d in l2]
    print(f"[{p}]  全市場平均 {np.mean([len(d) for d in full_days]):.0f} 檔/月")
    print(f"  L1 可投資性      {stats(l1, full_days)}")
    print(f"  L2 +陷阱排除     {stats(l2, full_days)}")
    print(f"  L3 +砍comp後40%  {stats(l3, full_days)}")
    # L4: 最終池內 composite_cap 排序力 — 池內前1/3 vs 後1/3 的超額差
    diffs = []
    for d in l3:
        if len(d) < 30:
            continue
        k = len(d) // 3
        s = d.sort_values("composite_cap")
        diffs.append(s.tail(k)["fwd"].mean() - s.head(k)["fwd"].mean())
    print(f"  L4 池內排序力(cap80 composite 前1/3-後1/3): {np.mean(diffs):+.3f}%/月\n")

# 敏感度:L1 門檻換 5M / 20M 對最終池的影響
for floor in (5_000_000, 20_000_000):
    print(f"敏感度 L1={floor/1e6:.0f}M:", end="")
    for p in PERIODS:
        full_days = [d for _, d in obs[obs["period"] == p].groupby("as_of") if len(d) >= 20]
        l1 = [pctize(d[(d["adv20"] >= floor) & d["listed_ok"].fillna(False)]) for d in full_days]
        l2 = [d[~((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0))] for d in l1]
        l3 = [d[d["composite"].rank(pct=True) > 0.40] for d in l2]
        print(f"  [{p}] {stats(l3, full_days)}", end="")
    print()
