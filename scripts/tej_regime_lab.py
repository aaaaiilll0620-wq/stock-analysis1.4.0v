"""Regime 條件式配方驗證 (2005-2026,六個空頭 episode)
================================================================================
預註冊假設 (依據=動能崩潰文獻,非本樣本;2022 為設計樣本,其餘 episode 為一次性樣本外):
  「空頭月,五因子聯集移除動能臂 (→4F),池超額應不劣於 5F」
Regime 定義 (固定規則,不調參):全市場等權日報酬累積指數 < 其 200 日均線 → 空頭日;
  月底 rebalance 日處於空頭 → 該月為空頭月;相鄰空頭月 (間隔<=2月) 併為同一 episode。
輸出:episode 級 4F vs 5F 對照 + 空頭月合併統計 + 月度 block bootstrap 信賴區間。
用法: python regime_lab.py <obs_dump路徑>
"""
import sys
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

DUMP = sys.argv[1]
TEJ = Path.home() / "tej_cache"
ADV_FLOOR = 10_000_000
rng = np.random.default_rng(20260715)

con = duckdb.connect()

# ---- 1) 等權指數與空頭月標記 (固定規則) ----
idx = con.execute(f"""
    WITH r AS (
        SELECT date, close / LAG(close) OVER (PARTITION BY stock_id ORDER BY date) - 1 AS ret
        FROM read_parquet('{TEJ}/price_valuation/*.parquet', union_by_name=true)
        WHERE close IS NOT NULL AND close > 0
    )
    SELECT date, AVG(ret) AS mkt_ret, COUNT(*) AS n
    FROM r WHERE ret IS NOT NULL AND ABS(ret) < 0.5
    GROUP BY date ORDER BY date
""").df()
idx["index"] = (1 + idx["mkt_ret"]).cumprod()
idx["ma200"] = idx["index"].rolling(200).mean()
idx["bear"] = idx["index"] < idx["ma200"]
bear_by_date = dict(zip(idx["date"], idx["bear"]))

# ---- 2) 觀測 + L1/L2 + 五因子池內百分位 ----
obs = pd.read_parquet(DUMP)
ind = pd.read_parquet(TEJ / "industry_map.parquet")[["stock_id", "tej_ind_name"]]
obs = obs.merge(ind, on="stock_id", how="left")
obs["rev_accel"] = obs["revenue_yoy"] - obs["rev_yoy_3m"]
# 產業內 value (研究版:全歷史 expanding 的 value 在當日產業內排名,分組<5退回全市場)
grp = obs.groupby(["as_of", "tej_ind_name"])["value"]
vind = grp.rank(pct=True) * 100
size = grp.transform("size")
mkt = obs.groupby("as_of")["value"].rank(pct=True) * 100
obs["value_ind"] = vind.where(size >= 5, mkt)

liq = con.execute(f"""
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
rows = []
for as_of, d in obs.groupby("as_of"):
    if len(d) < 20:
        continue
    d = d[(d["adv20"] >= ADV_FLOOR) & d["listed_ok"].fillna(False)].copy()
    if len(d) < 50:
        continue
    d["value_pct"] = d["value"].rank(pct=True) * 100
    d = d[~((d["value_pct"] > 90) & ~(d["revenue_yoy"] > 0))]
    for f in FACTORS:
        d[f"{f}_p"] = d[f].rank(pct=True) * 100
    u5 = np.logical_or.reduce([(d[f"{f}_p"] > 85).to_numpy() for f in FACTORS])
    u4 = np.logical_or.reduce([(d[f"{f}_p"] > 85).to_numpy()
                                for f in FACTORS if f != "momentum"])
    mkt_fwd = d["fwd"].mean()
    rows.append({"as_of": as_of, "bear": bool(bear_by_date.get(as_of, False)),
                 "pool_n": len(d),
                 "ex5": d.loc[u5, "fwd"].mean() - mkt_fwd,
                 "ex4": d.loc[u4, "fwd"].mean() - mkt_fwd,
                 "n5": int(u5.sum()), "n4": int(u4.sum())})
m = pd.DataFrame(rows).sort_values("as_of").reset_index(drop=True)
print(f"月度觀測 {len(m)} 個月 ({m['as_of'].min()} ~ {m['as_of'].max()}),"
      f"其中空頭月 {m['bear'].sum()} 個")

# ---- 3) episode 切分與逐 episode 對照 ----
m["ym"] = m["as_of"].str[:7]
eps, cur = [], None
for _, r in m[m["bear"]].iterrows():
    ym = pd.Period(r["ym"], "M")
    if cur and (ym - cur["end"]).n <= 2:
        cur["end"] = ym
        cur["rows"].append(r)
    else:
        if cur:
            eps.append(cur)
        cur = {"start": ym, "end": ym, "rows": [r]}
if cur:
    eps.append(cur)

print(f"\n[預註冊測試] 空頭月:4F(無動能) vs 5F 池超額 (%/20日;+為4F較好)")
print(f"{'episode':<22}{'月數':>4}{'5F超額':>9}{'4F超額':>9}{'差(4F-5F)':>10}")
agree = 0
for e in eps:
    df = pd.DataFrame(e["rows"])
    d5, d4 = df["ex5"].mean(), df["ex4"].mean()
    mark = " ✓" if d4 >= d5 else " ✗"
    agree += d4 >= d5
    print(f"{str(e['start'])}~{str(e['end']):<12}{len(df):>4}{d5:>+9.3f}{d4:>+9.3f}{d4-d5:>+10.3f}{mark}")
bears = m[m["bear"]]
print(f"{'合併(全部空頭月)':<20}{len(bears):>4}{bears['ex5'].mean():>+9.3f}"
      f"{bears['ex4'].mean():>+9.3f}{(bears['ex4']-bears['ex5']).mean():>+10.3f}")
print(f"episode 方向一致性: {agree}/{len(eps)}")

# 對照:多頭月不可變差
bulls = m[~m["bear"]]
print(f"\n[對照] 多頭月 ({len(bulls)} 個月): 5F {bulls['ex5'].mean():+.3f}"
      f"  4F {bulls['ex4'].mean():+.3f}  差 {(bulls['ex4']-bulls['ex5']).mean():+.3f}")

# ---- 4) 月度 block bootstrap (空頭月重抽,差值信賴區間) ----
diffs = (bears["ex4"] - bears["ex5"]).to_numpy()
boot = [rng.choice(diffs, size=len(diffs), replace=True).mean() for _ in range(5000)]
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"\n[bootstrap] 空頭月 4F−5F 差值: 平均 {diffs.mean():+.3f},"
      f" 95% CI [{lo:+.3f}, {hi:+.3f}], P(差>0)={np.mean(np.array(boot)>0)*100:.1f}%")
