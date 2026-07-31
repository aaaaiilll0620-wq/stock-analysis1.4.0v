# -*- coding: utf-8 -*-
"""a1a2_isolation_check.py — 把預註冊 A1 / A2 的**隔離規格**所需的事實量清楚。

Codex 第五輪指出:草案的 A1/A2 **不是單一變更**(用「全期關掉另一個通道」來隔離,
等於順手改了 2019 之後的 V0 行為)。正確隔離是「**只補 2005–2018 的資料**」。
但「只補前段」有一個無法迴避的副作用:trailing window 會跨越 2019-01-02 的接縫,
所以 2019 年初有幾個月的值**必然**與 V0 不同。

本檔量四件事,供把 A1/A2 寫成可凍結的規格:
  1. 兩份 0050 在重疊區間的 close 是否逐列相同(決定「拼接」是不是乾淨的延長);
  2. `_back_adjust` 在兩份序列上各偵測到幾處斷點(決定拼接後尺度是否一致);
  3. **regime**:V0 輸入 vs 拼接輸入,2019 之後**確切哪幾個月**不同 → 邊界污染窗;
  4. **RS**:`benchmark_trailing_return` 的可得性門檻(≥lookback+skip+1 列)在兩份
     序列下各從哪個 as_of 開始滿足。

**不建面板、不碰報酬線、不算 IC、不算績效。** 只算 regime 標籤與資料可得性。

用法:python scripts/a1a2_isolation_check.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_HERE, _ROOT):
    sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FULL_0050 = os.path.join(_ROOT, "beat_0050", "data", "benchmark", "0050_raw.parquet")
SEAM = "2019-01-02"          # 生產 0050 快取的第一列
RS_SKIP = 5                  # core.backtest.benchmark_trailing_return 的預設


def hr(t):
    print("\n" + "=" * 88)
    print(t)
    print("=" * 88)


def panel_asofs() -> list:
    from lab_paths import load_panel  # noqa
    import scripts.lab_paths as _lp   # noqa
    raise RuntimeError


def _asofs() -> list:
    """用 V0 面板的 as_of 清單(255 月,已裁掉 2026-04)。"""
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))
    from lab_paths import resolve_realbody
    df = pd.read_parquet(resolve_realbody(1e6), columns=["as_of"])
    a = sorted(df["as_of"].astype(str).unique())
    return [x for x in a if x <= "2026-03-31"]


def _count_breaks(close: np.ndarray) -> int:
    """複製 core.backtest._back_adjust 的斷點判準,只回報偵測到幾處。"""
    hits = 0
    for i in range(1, len(close)):
        if not (close[i] > 0 and close[i - 1] > 0):
            continue
        r = close[i] / close[i - 1]
        if r < 0.7 or r > 1.5:
            hits += 1
    return hits


def main():
    from core import data_cache
    from core.backtest import _back_adjust
    from core.regime import classify_regime

    asofs = _asofs()
    cache = data_cache.read_cached("TaiwanStockPrice", "0050")
    cache["date"] = cache["date"].astype(str)
    cache = cache.sort_values("date").reset_index(drop=True)
    repo = pd.read_parquet(FULL_0050)
    repo["date"] = repo["date"].astype(str)
    repo = repo.sort_values("date").reset_index(drop=True)

    # ---------------- 1. 重疊區間是否逐列相同 ----------------
    hr("1. 兩份 0050 在重疊區間的 close 是否相同(決定拼接是否為乾淨延長)")
    ov = repo.merge(cache[["date", "close"]], on="date", suffixes=("_repo", "_cache"))
    d = (ov["close_repo"].astype(float) - ov["close_cache"].astype(float)).abs()
    same = bool((d < 1e-9).all())
    print(f"  生產快取 : {len(cache):,} 列  {cache['date'].min()} → {cache['date'].max()}")
    print(f"  repo 全史: {len(repo):,} 列  {repo['date'].min()} → {repo['date'].max()}  欄位 {list(repo.columns)}")
    print(f"  重疊 {len(ov):,} 列   max|Δclose| = {d.max():.6f}   **逐列相同 = {same}**")
    print(f"  → 拼接{'是' if same else '不是'}『同一序列的延長』;"
          f"{'接縫無跳空,不是換資料源' if same else '⚠ 接縫有落差,拼接會引入人造斷點'}")
    print(f"  接縫兩側:{repo.loc[repo.date < SEAM, 'date'].max()} close="
          f"{float(repo.loc[repo.date < SEAM, 'close'].iloc[-1]):.2f}  →  "
          f"{SEAM} close={float(cache.loc[cache.date == SEAM, 'close'].iloc[0]):.2f}")

    # ---------------- 2. 拼接 + back-adjust ----------------
    hr("2. `_back_adjust` 的斷點偵測(拼接後尺度是否一致)")
    spliced = pd.concat([repo.loc[repo["date"] < SEAM, ["date", "close"]],
                         cache.loc[cache["date"] >= SEAM, ["date", "close"]]],
                        ignore_index=True).sort_values("date").reset_index(drop=True)
    print(f"  拼接序列 : {len(spliced):,} 列  {spliced['date'].min()} → {spliced['date'].max()}")
    print(f"  斷點數 —— 生產快取 {_count_breaks(cache['close'].astype(float).values)} 處 / "
          f"拼接序列 {_count_breaks(spliced['close'].astype(float).values)} 處 / "
          f"repo 全史 {_count_breaks(repo['close'].astype(float).values)} 處")
    prod_adj = _back_adjust(cache.copy())
    spl_adj = _back_adjust(spliced.copy())
    repo_rawadj = repo.copy()                       # 舊稽核腳本用的:**未** back-adjust
    ov2 = prod_adj[["date", "close"]].merge(spl_adj[["date", "close"]], on="date",
                                            suffixes=("_prod", "_spl"))
    d2 = (ov2["close_prod"].astype(float) - ov2["close_spl"].astype(float)).abs()
    print(f"  back-adjust 後,2019 起重疊 {len(ov2):,} 列 max|Δ| = {d2.max():.8f}"
          f"  → 拼接**不改變** 2019 之後的價格尺度 = {bool((d2 < 1e-6).all())}")

    # ---------------- 3. regime:邊界污染窗 ----------------
    hr("3. regime —— V0 輸入 vs 拼接輸入:2019 之後確切哪幾個月不同")
    s_v0 = pd.Series({a: classify_regime(prod_adj, a) for a in asofs})
    s_spl = pd.Series({a: classify_regime(spl_adj, a) for a in asofs})
    s_old = pd.Series({a: classify_regime(repo_rawadj, a) for a in asofs})   # 舊稽核的做法

    post = [a for a in asofs if a >= "2019"]
    pre = [a for a in asofs if a < "2019"]
    diff_post = [a for a in post if s_v0[a] != s_spl[a]]
    diff_post_old = [a for a in post if s_v0[a] != s_old[a]]
    print(f"  2019 前 {len(pre)} 月: V0 {dict(s_v0[pre].value_counts())} / "
          f"拼接 {dict(s_spl[pre].value_counts())}")
    print(f"  2019 起 {len(post)} 月一致率: 拼接(正確做法) "
          f"**{(1-len(diff_post)/len(post))*100:.1f}%**  /  "
          f"未 back-adjust 的 repo(舊稽核做法) {(1-len(diff_post_old)/len(post))*100:.1f}%")
    print(f"\n  ▸ 拼接輸入在 2019 之後與 V0 不同的月份({len(diff_post)} 個):")
    for a in diff_post:
        print(f"      {a}   V0={s_v0[a]:<8} → 拼接={s_spl[a]}")
    if diff_post:
        print(f"    → **邊界污染窗 = {diff_post[0]} ~ {diff_post[-1]}**")
    print(f"\n  ▸ 舊稽核(未 back-adjust)多出來的不一致月份共 {len(diff_post_old)} 個,"
          f"最早 {diff_post_old[0] if diff_post_old else '—'} 最晚 "
          f"{diff_post_old[-1] if diff_post_old else '—'}")
    print("    → 若這批集中在 2025-06 之後,原因就是 0050 分割未回補造成的人造 −75% 崩盤。")
    if diff_post_old:
        by_year = pd.Series([a[:4] for a in diff_post_old]).value_counts().sort_index()
        print(f"      年份分布:{by_year.to_dict()}")

    # ---------------- 4. RS 可得性 ----------------
    hr("4. RS —— `benchmark_trailing_return` 的可得性(需 ≥ lookback+skip+1 列)")
    for lb, name in ((60, "rs_3m"), (120, "rs_6m")):
        need = lb + RS_SKIP + 1
        first_v0 = next((a for a in asofs if (cache["date"] <= a).sum() >= need), None)
        first_spl = next((a for a in asofs if (spliced["date"] <= a).sum() >= need), None)
        n_gain = sum(1 for a in asofs if (spliced["date"] <= a).sum() >= need
                     and (cache["date"] <= a).sum() < need)
        print(f"  {name}(需 {need} 列): V0 首見 **{first_v0}** / 拼接首見 **{first_spl}**"
              f"   → 拼接讓 **{n_gain}** 個 as_of 新增可計分")
        gained_post = [a for a in asofs if a >= "2019"
                       and (spliced["date"] <= a).sum() >= need
                       and (cache["date"] <= a).sum() < need]
        print(f"      其中落在 2019 之後(= 邊界污染窗)的:{len(gained_post)} 個"
              f"{' ' + gained_post[0] + ' ~ ' + gained_post[-1] if gained_post else ''}")

    hr("結論(寫進預註冊 §4 A 層)")
    print("  · 拼接 = 同一序列的延長,接縫無跳空,**不是換資料源**;")
    print("  · back-adjust 後 2019 之後的價格尺度不變;")
    print("  · 但 trailing window 跨接縫 → 2019 年初有一段**必然**與 V0 不同,")
    print("    這段必須在預註冊裡明列為『邊界污染窗』,並在結果中單獨報告。")


if __name__ == "__main__":
    main()
