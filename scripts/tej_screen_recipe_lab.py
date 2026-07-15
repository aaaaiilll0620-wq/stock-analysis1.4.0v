"""初篩配方實驗:用 obs_dump.parquet 比較「composite 定義 × 極端便宜端處理 × 池子大小」
的三期入池表現。指標 = 入池股票的市場中性超額報酬 (池平均 fwd - 同日全市場平均 fwd,
市場基準固定用全市場,跨配方可比)。"""
import sys
import numpy as np
import pandas as pd

OBS_PATH = sys.argv[1] if len(sys.argv) > 1 else "obs_dump.parquet"
PERIODS = ["2023-2025", "2022空頭", "2019-2021(樣本外)"]
POOL_QS = [0.10, 0.20, 0.30]

df = pd.read_parquet(OBS_PATH)

# 每 (期間, 日) 橫斷面先算好三因子百分位,後面各配方重複使用
def prep(day: pd.DataFrame) -> pd.DataFrame:
    day = day.copy()
    for f in ("value", "momentum", "chip"):
        day[f"{f}_pct"] = day[f].rank(pct=True) * 100.0
    return day


def fold(vp: pd.Series, cap: float) -> pd.Series:
    return vp.where(vp <= cap, 2 * cap - vp)


# 各配方回傳 (composite Series, eligible 布林遮罩)。市場平均永遠用全 day 算。
def recipe_base(day):
    comp = day[["value_pct", "momentum_pct", "chip_pct"]].mean(axis=1)
    return comp, pd.Series(True, index=day.index)

def recipe_cap(cap):
    def r(day):
        comp = (fold(day["value_pct"], cap) + day["momentum_pct"] + day["chip_pct"]) / 3
        return comp, pd.Series(True, index=day.index)
    return r

def recipe_excl90(day):
    comp = day[["value_pct", "momentum_pct", "chip_pct"]].mean(axis=1)
    return comp, day["value_pct"] <= 90

def recipe_cond(day):
    # 條件性排除:極端便宜 (value_pct>90) 且 營收YoY<=0 (含NaN,保守) 不得入池
    comp = day[["value_pct", "momentum_pct", "chip_pct"]].mean(axis=1)
    bad = (day["value_pct"] > 90) & ~(day["revenue_yoy"] > 0)
    return comp, ~bad

def recipe_cap80_cond(day):
    comp = (fold(day["value_pct"], 80) + day["momentum_pct"] + day["chip_pct"]) / 3
    bad = (day["value_pct"] > 90) & ~(day["revenue_yoy"] > 0)
    return comp, ~bad

RECIPES = [
    ("等權三因子 (基準)", recipe_base),
    ("value cap 70", recipe_cap(70)),
    ("value cap 80", recipe_cap(80)),
    ("value cap 90", recipe_cap(90)),
    ("硬排除 value_pct>90", recipe_excl90),
    ("條件排除 >90且YoY<=0", recipe_cond),
    ("cap80 + 條件排除", recipe_cap80_cond),
]

days_by_period = {p: [prep(day) for _, day in df[df["period"] == p].groupby("as_of")
                       if len(day) >= 20] for p in PERIODS}

for q in POOL_QS:
    print(f"\n=== 池子 = composite 前 {q*100:.0f}% (每月再平衡,超額% vs 全市場) ===")
    print(f"  {'配方':<28}" + "".join(f"{p:>16}" for p in PERIODS) + f"{'三期最小':>10}")
    for name, fn in RECIPES:
        cells, mins = [], []
        for p in PERIODS:
            excesses = []
            for day in days_by_period[p]:
                comp, ok = fn(day)
                elig = day[ok].assign(_c=comp[ok])
                k = max(int(len(day) * q), 5)
                pool = elig.nlargest(k, "_c")
                excesses.append(pool["fwd"].mean() - day["fwd"].mean())
            m = float(np.mean(excesses))
            mins.append(m)
            cells.append(f"{m:+13.3f}   ")
        print(f"  {name:<28}" + "".join(cells) + f"{min(mins):+9.3f}")
