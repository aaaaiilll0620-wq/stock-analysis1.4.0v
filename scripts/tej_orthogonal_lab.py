"""正交資料驗證實驗室:產業中性化 / TDCC 集保大戶 / 董監質押 三軌。
資料:obs_dump_v2 + tej_cache 的 industry_map / tdcc_weekly / director_pledge。
A 軌用全市場母體對照原始 value decile 10 基準 (-0.452/-0.163/-0.464);
B/C 軌用 L1 母體測排除規則 (對照現行 L2)。"""
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

SCRATCH = Path(r"C:\Users\aaaai\AppData\Local\Temp\claude\C--Users-aaaai-OneDrive-Desktop-Project-1\b3b44244-0d70-4d10-a97b-ca40f0e07343\scratchpad")
TEJ = Path.home() / "tej_cache"
PERIODS = ["2023-2025", "2022空頭", "2019-2021(樣本外)"]
ADV_FLOOR = 10_000_000
TDCC_LAG_DAYS = 4      # 集保資料日=週五,公布約次週初
PLEDGE_LAG_DAYS = 15   # 董監月報約次月中旬前公布

obs = pd.read_parquet(SCRATCH / "obs_dump_v2.parquet")
obs["_dt"] = pd.to_datetime(obs["as_of"])

# ---- 產業對照 (靜態 join) ----
ind = pd.read_parquet(TEJ / "industry_map.parquet")
obs = obs.merge(ind[["stock_id", "tse_ind_name", "tej_ind_name", "tej_subind_name"]],
                on="stock_id", how="left")

# ---- TDCC 週頻:大戶比率水位與 4/12 週變化,PIT 對齊 ----
con = duckdb.connect()
tdcc = con.execute(f"""
    SELECT stock_id, date, ratio_1000up, ratio_le1, holders
    FROM read_parquet('{TEJ}/tdcc_weekly/*.parquet', union_by_name=true)
    ORDER BY stock_id, date
""").df()
pledge = con.execute(f"""
    SELECT stock_id, date, pledge_pct, director_holding_pct
    FROM read_parquet('{TEJ}/director_pledge/*.parquet', union_by_name=true)
    ORDER BY stock_id, date
""").df()
con.close()

g = tdcc.groupby("stock_id")
tdcc["big_d4w"] = tdcc["ratio_1000up"] - g["ratio_1000up"].shift(4)
tdcc["big_d12w"] = tdcc["ratio_1000up"] - g["ratio_1000up"].shift(12)
tdcc["holders_chg12w"] = tdcc["holders"] / g["holders"].shift(12) - 1
tdcc["known_date"] = pd.to_datetime(tdcc["date"]) + pd.Timedelta(days=TDCC_LAG_DAYS)
tdcc = tdcc.sort_values("known_date")
obs = obs.sort_values("_dt")
obs = pd.merge_asof(obs, tdcc[["stock_id", "known_date", "ratio_1000up",
                                "big_d4w", "big_d12w", "holders_chg12w"]],
                    left_on="_dt", right_on="known_date", by="stock_id",
                    direction="backward", tolerance=pd.Timedelta(days=60))
obs = obs.drop(columns=["known_date"])

pledge["known_date"] = (pd.to_datetime(pledge["date"]) + pd.offsets.MonthEnd(0)
                         + pd.Timedelta(days=PLEDGE_LAG_DAYS))
pledge = pledge.sort_values("known_date")
obs = pd.merge_asof(obs, pledge[["stock_id", "known_date", "pledge_pct",
                                  "director_holding_pct"]],
                    left_on="_dt", right_on="known_date", by="stock_id",
                    direction="backward", tolerance=pd.Timedelta(days=90))
obs = obs.drop(columns=["known_date"])

print("合併後覆蓋率:")
for c in ("tej_ind_name", "ratio_1000up", "big_d12w", "pledge_pct"):
    print(f"  {c}: 非空 {obs[c].notna().mean()*100:.1f}%")

# ================================================================ A 軌:產業中性化
def decile10(sub, key):
    outs = []
    for _, day in sub.groupby("as_of"):
        if len(day) < 20:
            continue
        excess = day["fwd"] - day["fwd"].mean()
        r = day[key].rank(pct=True)
        outs.append(excess[r > 0.9].mean())
    return float(np.nanmean(outs))

print("\n[A] 產業中性化 value:decile 10 (最便宜10%) 三期對照 (全市場母體)")
print(f"  {'排名方式':<26}" + "".join(f"{p:>16}" for p in PERIODS))
rows = {"原始全市場排名 (基準)": "value"}
for level in ("tse_ind_name", "tej_ind_name", "tej_subind_name"):
    col = f"vind_{level}"
    grp = obs.groupby(["as_of", level])["value"]
    vind = grp.rank(pct=True) * 100
    size = grp.transform("size")
    mkt = obs.groupby("as_of")["value"].rank(pct=True) * 100
    obs[col] = vind.where(size >= 5, mkt)   # 小產業 (<5檔) 退回全市場排名
    rows[f"產業內排名 ({level})"] = col
for label, key in rows.items():
    cells = [f"{decile10(obs[obs['period']==p], key):>+13.3f}   " for p in PERIODS]
    print(f"  {label:<26}" + "".join(cells))

print("\n  原始 decile 10 的產業組成 (2023-2025,TEJ產業,前8名):")
d10 = []
for _, day in obs[obs["period"]=="2023-2025"].groupby("as_of"):
    if len(day) < 20: continue
    d10.append(day[day["value"].rank(pct=True) > 0.9])
d10 = pd.concat(d10)
mkt_share = obs[obs["period"]=="2023-2025"]["tej_ind_name"].value_counts(normalize=True)
for name, share in d10["tej_ind_name"].value_counts(normalize=True).head(8).items():
    print(f"    {name:<14} decile10占比 {share*100:5.1f}%  (全市場占比 {mkt_share.get(name,0)*100:4.1f}%)")

# ================================================================ B/C 軌:排除規則 (L1 母體)
liq = duckdb.connect().execute(f"""
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

def pctize(day):
    day = day.copy()
    for f in ("value", "momentum", "chip"):
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

EXCL = [
    ("L2 現行 (value>90 且 YoY<=0)",
     lambda d: (d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0)),
    ("T1 大戶撤退陷阱: value>90 且 big_d12w<0",
     lambda d: (d["value_pct"] > 90) & (d["big_d12w"] < 0)),
    ("T2 大戶大幅撤退: big_d12w < -3pp",
     lambda d: d["big_d12w"] < -3),
    ("T3 籌碼渙散: holders 12週增 >15%",
     lambda d: d["holders_chg12w"] > 0.15),
    ("P1 高質押: pledge > 80%",
     lambda d: d["pledge_pct"] > 80),
    ("P2 高質押低持股: pledge>50 且 持股<10%",
     lambda d: (d["pledge_pct"] > 50) & (d["director_holding_pct"] < 10)),
    ("P3 質押陷阱: value>90 且 pledge>50",
     lambda d: (d["value_pct"] > 90) & (d["pledge_pct"] > 50)),
    ("組合 L2+T1+P1",
     lambda d: ((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0)) |
               ((d["value_pct"] > 90) & (d["big_d12w"] < 0)) |
               (d["pledge_pct"] > 80)),
]

print("\n[B/C] 排除規則對決 (L1 母體;NaN 一律放行)")
for p in PERIODS:
    full_days = [d for _, d in obs[obs["period"] == p].groupby("as_of") if len(d) >= 20]
    l1 = [pctize(d[(d["adv20"] >= ADV_FLOOR) & d["listed_ok"].fillna(False)]) for d in full_days]
    print(f"\n[{p}]  L1 基準: {stats(l1, full_days)}")
    for label, rule in EXCL:
        pools = [d[~rule(d).fillna(False)] for d in l1]
        print(f"  L1+{label:<36} {stats(pools, full_days)}")
