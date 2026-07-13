# -*- coding: utf-8 -*-
"""
Regime 偵測診斷:逐日跑 classify_regime() 走過 2021-01-01 ~ 2025-12-31,
列出每次 regime 切換的時間點與當時價格/MA120 狀態,並與大盤實際走勢對照,
用來判斷 classify_regime 是「切太慢(滯後)」還是「切太頻繁(被騙/whipsaw)」。
"""
import sys
import pandas as pd

sys.path.insert(0, ".")
from core.backtest import load_benchmark
from core.regime import classify_regime

MA_LONG = 120
SLOPE_LOOKBACK = 20
DEEP_BREAK = 0.93

b = load_benchmark("0050")
df = b.price[["date", "close"]].dropna().sort_values("date").reset_index(drop=True)
df["date"] = df["date"].astype(str)

start, end = "2021-01-01", "2025-12-31"
dates = df[(df["date"] >= start) & (df["date"] <= end)]["date"].tolist()

records = []
for d in dates:
    regime = classify_regime(df, d, ma_long=MA_LONG, slope_lookback=SLOPE_LOOKBACK, deep_break=DEEP_BREAK)
    close = float(df[df["date"] == d]["close"].iloc[0])
    records.append((d, regime, close))

rdf = pd.DataFrame(records, columns=["date", "regime", "close"])

# 找出切換點
switches = []
prev = None
for _, row in rdf.iterrows():
    if row["regime"] != prev:
        switches.append((row["date"], prev, row["regime"], row["close"]))
        prev = row["regime"]

print(f"共 {len(dates)} 個交易日,regime 切換 {len(switches)} 次\n")
print(f"{'日期':<12}{'前一狀態':<10}{'新狀態':<10}{'收盤價':>10}")
print("-" * 45)
for d, prev_r, new_r, close in switches:
    print(f"{d:<12}{str(prev_r):<10}{new_r:<10}{close:>10.2f}")

# 統計各 regime 持續天數分佈,抓出「切換後幾天內又切回去」的可疑 whipsaw
print("\n--- Whipsaw 檢查(切換後 <= 10 個交易日內又切回原狀態) ---")
idx_map = {d: i for i, d in enumerate(rdf["date"])}
whip = 0
for i in range(1, len(switches) - 1):
    d, prev_r, new_r, _ = switches[i]
    nd, nprev_r, nnew_r, _ = switches[i + 1]
    gap = idx_map[nd] - idx_map[d]
    if nnew_r == prev_r and gap <= 10:
        whip += 1
        print(f"  {d} {prev_r}->{new_r} 後,僅 {gap} 個交易日 ({nd}) 又切回 {nnew_r}")
print(f"疑似 whipsaw 次數: {whip}")

# 各 regime 佔比
print("\n--- 各 regime 佔比 (2021-2025) ---")
print(rdf["regime"].value_counts(normalize=True).mul(100).round(1))

# 存檔供進一步比對
out_path = "scripts/regime_daily_2021_2025.csv"
rdf.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"\n逐日結果已存至 {out_path}")
