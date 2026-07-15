"""離線價值陷阱過濾實驗室:讀 obs_dump.parquet,重現 tej_universe_screen_validation.py
的 decile 管線後,秒級迭代各種品質過濾,聚焦 decile 10 (最便宜10%) 三期表現。"""
import sys
import numpy as np
import pandas as pd

OBS_PATH = sys.argv[1] if len(sys.argv) > 1 else "obs_dump.parquet"
PERIODS = ["2023-2025", "2022空頭", "2019-2021(樣本外)"]
BASELINE = {"2023-2025": -0.452, "2022空頭": -0.163, "2019-2021(樣本外)": -0.464}

df = pd.read_parquet(OBS_PATH)


def decile_returns(sub: pd.DataFrame, n=10) -> dict:
    """同驗證腳本 decile_returns:每期日橫斷面依 value 排序切 n 等分,
    市場中性超額報酬 (扣同日全體平均),逐日算完再平均。"""
    buckets = {b: [] for b in range(1, n + 1)}
    for _, day in sub.groupby("as_of"):
        if len(day) < n * 2:
            continue
        fwd = day["fwd"].to_numpy()
        excess = fwd - fwd.mean()
        order = np.argsort(day["value"].to_numpy(), kind="stable")
        edges = np.linspace(0, len(day), n + 1).astype(int)
        for b in range(n):
            chunk = excess[order[edges[b]:edges[b + 1]]]
            if len(chunk):
                buckets[b + 1].append(chunk.mean())
    return {b: float(np.mean(v)) for b, v in buckets.items() if v}


def run_filter(name: str, mask_fn) -> None:
    """mask_fn(df) -> 保留列的布林遮罩。印三期 decile 10 與過濾掉的比例。"""
    cells = []
    for p in PERIODS:
        sub = df[df["period"] == p]
        keep = mask_fn(sub)
        d = decile_returns(sub[keep])
        cells.append(f"{d.get(10, float('nan')):+.3f} (濾{(~keep).mean()*100:4.1f}%)")
    print(f"  {name:<42}" + "  ".join(cells))


nan = lambda s: s.isna()

print("decile 10 三期市場中性超額報酬 (基準應重現 -0.452 / -0.163 / -0.464):")
print(f"  {'過濾':<42}" + "  ".join(f"{p:<16}" for p in PERIODS))
run_filter("baseline (不濾)", lambda s: pd.Series(True, index=s.index))
run_filter("eps>0 (對照:應近 -.498/-.233/-.521)", lambda s: s["eps"] > 0)
run_filter("排除 eps>0 且 op<=0 (旗標A對照)",
           lambda s: ~((s["eps"] > 0) & (s["op_income"] <= 0)))
run_filter("旗標B: 排除 net>0 且 op/net<0.5",
           lambda s: ~((s["net_income"] > 0) & (s["op_income"] / s["net_income"] < 0.5)
                        & ~nan(s["op_income"])))
run_filter("ROE gate: roe>0 (NaN 濾掉)", lambda s: s["roe"] > 0)
run_filter("ROE gate: roe>2 (單季)", lambda s: s["roe"] > 2)
run_filter("營收趨勢: yoy>0 (NaN 放行)",
           lambda s: nan(s["revenue_yoy"]) | (s["revenue_yoy"] > 0))
run_filter("營收趨勢: yoy>-10 (NaN 放行)",
           lambda s: nan(s["revenue_yoy"]) | (s["revenue_yoy"] > -10))
run_filter("組合: roe>0 且 yoy>-10",
           lambda s: (s["roe"] > 0) & (nan(s["revenue_yoy"]) | (s["revenue_yoy"] > -10)))

# ------------------------------------------------------------------ 特徵側寫
print("\ndecile 10 vs 全市場 特徵側寫 (中位數;op/net 僅 net>0 者):")
rows = []
for p in PERIODS:
    sub = df[df["period"] == p].copy()
    # 重建 decile 標籤 (同 decile_returns 的切法)
    sub["decile"] = np.nan
    for d_, day in sub.groupby("as_of"):
        if len(day) < 20:
            continue
        order = day["value"].rank(method="first")
        sub.loc[day.index, "decile"] = np.ceil(order / len(day) * 10)
    opnet = lambda x: (x["op_income"] / x["net_income"]).where(x["net_income"] > 0)
    for label, grp in [("decile10", sub[sub["decile"] == 10]), ("全市場", sub)]:
        rows.append({
            "期間": p, "組": label, "n": len(grp),
            "ROE中位": grp["roe"].median(),
            "營收YoY中位": grp["revenue_yoy"].median(),
            "op/net中位": opnet(grp).median(),
            "eps<=0比%": ((grp["eps"] <= 0).mean() * 100),
            "op<=0&eps>0比%": (((grp["op_income"] <= 0) & (grp["eps"] > 0)).mean() * 100),
            "動能中位%": grp["momentum"].median(),
            "fwd中位%": grp["fwd"].median(),
        })
prof = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(prof.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
