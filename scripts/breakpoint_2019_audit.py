# -*- coding: utf-8 -*-
"""breakpoint_2019_audit.py — 「2019 三個定義斷裂點」的**獨立覆核**(Codex 第一輪審查 §六-A)

覆核四件事,每件都用「同一段程式碼、只換輸入」的方式證明因果,不用推論:

  A1  classify_regime() 在 2019 前是否真的全部回傳 neutral(生產實際走的資料源)
  A2  0050 歷史缺口是否為**唯一**原因 —— 換成 repo 內 2003 起的 0050,同一個函式會不會變
  A3  f_val 在 2019 前後是否真的走不同路徑(逐列查 industry_value_pct 可得性)
  A4  f_mom 的 RS 從哪一個 as_of 開始有效
  A5  這些差異落在 H5 的六個時代的哪幾段

**本檔唯讀,不寫任何面板、不改任何公式。**

================================================================================
⚠ 2026-07-31 已知缺陷 —— **A2 印出的「2019 起一致率」不可引用**
================================================================================
下面的 `a1_a2()` 把 `0050_raw.parquet` **直接**丟進 `classify_regime()`,
**沒有套 `core.backtest._back_adjust()`**;而生產路徑(`load_benchmark`)**是有跳空回補的**。
2025 年 0050 分割在未回補的序列上是一天 **−75%** 的人造崩盤 → 強制判 bear。

後果:本檔印出的「2019 起一致率 **87.6%**」中,11 個不一致月份**有 7 個落在 2025**,
是這個 artifact 造成的,不是真實的資料差異。
**兩邊都 back-adjust 之後,一致率是 95.4%,4 個不一致月份全部落在 2019-01/02/06/07。**

同時,由此衍生的「兩條路徑讀不同的 0050」**這個機制描述也是錯的** ——
兩份序列在重疊的 1,827 列上 `close` 逐列相同(max|Δ|=0.0),RS 與 regime 讀的是
**同一個** `TaiwanStockPrice/0050`。`0050_raw.parquet` 是同一條序列的**歷史延長**。

**不變的結論**:2019 前 168 個月全 neutral 的唯一原因就是資料缺口
(`classify_regime` 在 < 140 列時強制回 neutral)。A1/A3/A4/A5 不受影響。

**本檔的計算刻意保持原樣**(它是當時實際跑出那些數字的紀錄,改了就對不上文件)。
正確版的量測在 → **`scripts/a1a2_isolation_check.py`**,請用那一支。
================================================================================

用法:python scripts/breakpoint_2019_audit.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from lab_paths import resolve_realbody   # noqa: E402

# H5 的六個時代(取自 docs/預註冊_雙確認ADV100萬.md §2 H5)
ERAS = [("05-09", "2005", "2009"), ("10-14", "2010", "2014"), ("15-18", "2015", "2018"),
        ("19-21", "2019", "2021"), ("2022", "2022", "2022"), ("23-26", "2023", "2026")]

FULL_0050 = Path(_ROOT) / "beat_0050" / "data" / "benchmark" / "0050_raw.parquet"


def hr(t):
    print("\n" + "=" * 92 + f"\n{t}\n" + "=" * 92)


def panel_asofs() -> list:
    p = resolve_realbody(1e6)
    d = pd.read_parquet(p, columns=["as_of"])
    return sorted(d["as_of"].astype(str).unique()), p


def a1_a2(asofs):
    from core.backtest import load_benchmark
    from core.regime import classify_regime

    hr("A1 —— 生產實際走的資料源:core.backtest.load_benchmark('0050')")
    b = load_benchmark("0050")
    prod = None if (b is None or getattr(b, "price", None) is None) else b.price
    if prod is None or prod.empty:
        print("❌ 生產基準完全載不到 —— regime 全期都會是 neutral")
        return None, None
    print(f"  列數 {len(prod):,}  區間 {prod['date'].min()} → {prod['date'].max()}")
    s_prod = pd.Series({a: classify_regime(prod, a) for a in asofs})
    pre = s_prod[s_prod.index < "2019"]
    print(f"  全期分布      : {s_prod.value_counts().to_dict()}")
    print(f"  2019 前 {len(pre)} 個月: {pre.value_counts().to_dict()}")
    print(f"  → 2019 前全部 neutral?  **{'是' if set(pre.unique()) == {'neutral'} else '否'}**")

    hr("A2 —— 只換輸入:repo 內 2003 起的完整 0050(beat_0050/data/benchmark/0050_raw.parquet)")
    if not FULL_0050.exists():
        print(f"❌ 找不到 {FULL_0050}")
        return s_prod, None
    full = pd.read_parquet(FULL_0050)
    print(f"  列數 {len(full):,}  區間 {full['date'].min()} → {full['date'].max()}")
    s_full = pd.Series({a: classify_regime(full, a) for a in asofs})
    pre_f = s_full[s_full.index < "2019"]
    print(f"  全期分布      : {s_full.value_counts().to_dict()}")
    print(f"  2019 前 {len(pre_f)} 個月: {pre_f.value_counts().to_dict()}")
    print(f"  → 2019 前全部 neutral?  **{'是' if set(pre_f.unique()) == {'neutral'} else '否'}**")

    agree = (s_prod == s_full)
    print(f"\n兩個輸入的一致率:全期 {agree.mean()*100:.1f}%  /  "
          f"2019 起 {agree[agree.index >= '2019'].mean()*100:.1f}%  /  "
          f"2019 前 {agree[agree.index < '2019'].mean()*100:.1f}%")
    print("\n判讀:同一個 classify_regime()、同一組 as_of,**只換基準價格序列**。")
    print("      若 A2 在 2019 前產生大量 bull/bear,則 A1 的『全 neutral』**唯一原因就是資料缺口**,")
    print("      不是市場真的中性,也不是 hysteresis 造成的。")
    return s_prod, s_full


def a3(asofs, panel_path):
    hr("A3 —— f_val:2019 前後是否真的走不同路徑")
    print("機制:ValuationEngine.evaluate() 第一件事就是取 industry_value_percentile,")
    print("      有值 → 路徑①『產業內位階』直接 return;None → 往下退到路徑②(PEG 0.85 + 歷史位階 0.15)。")
    print("      所以『路徑①覆蓋率』= industry_value_pct() 有值的比例,可逐列直接量。\n")
    from core.industry_value import industry_value_pct, REF_PATH, MAX_STALE_DAYS
    print(f"  參考表 {REF_PATH}  存在={REF_PATH.exists()}  MAX_STALE_DAYS={MAX_STALE_DAYS}")
    if REF_PATH.exists():
        ref = pd.read_parquet(REF_PATH, columns=["stock_id", "date"])
        print(f"  參考表 {len(ref):,} 列 / {ref['stock_id'].nunique()} 檔 / "
              f"{ref['date'].min()} → {ref['date'].max()}")

    d = pd.read_parquet(panel_path, columns=["as_of", "stock_id"])
    d["as_of"] = d["as_of"].astype(str)
    d["stock_id"] = d["stock_id"].astype(str)
    d["has_ind"] = [industry_value_pct(s, a) is not None
                    for s, a in zip(d["stock_id"], d["as_of"])]
    by_year = d.groupby(d["as_of"].str[:4])["has_ind"].agg(["mean", "size"])
    print(f"\n{'年':<6}{'路徑①(產業內位階)覆蓋率':>26}{'列數':>10}")
    for y, r in by_year.iterrows():
        print(f"{y:<6}{r['mean']*100:>25.2f}%{int(r['size']):>10,}")
    pre = d[d["as_of"] < "2019-04"]["has_ind"].mean()
    post = d[d["as_of"] >= "2019-05"]["has_ind"].mean()
    print(f"\n  2019-04 之前:{pre*100:.2f}%   2019-05 之後:{post*100:.2f}%")
    print(f"  → f_val 走不同路徑?  **{'是' if pre < 0.01 and post > 0.9 else '需人工判讀'}**")


def a4(asofs):
    hr("A4 —— f_mom 的 RS 從哪一個 as_of 開始有效")
    from core.backtest import benchmark_trailing_return, _RS_BENCHMARK
    from core import data_cache
    src = data_cache.read_cached("TaiwanStockPrice", _RS_BENCHMARK)
    if src is None or src.empty:
        print(f"❌ RS 基準快取 TaiwanStockPrice/{_RS_BENCHMARK} 不存在 → rs_3m/rs_6m 全期皆 None")
        return None
    print(f"  RS 基準源(與 regime 不同源!):data_cache TaiwanStockPrice/{_RS_BENCHMARK}")
    print(f"  列數 {len(src):,}  區間 {src['date'].min()} → {src['date'].max()}")
    first6 = first3 = None
    for a in asofs:
        if first3 is None and benchmark_trailing_return(a, 60) is not None:
            first3 = a
        if first6 is None and benchmark_trailing_return(a, 120) is not None:
            first6 = a
        if first3 and first6:
            break
    n_no6 = sum(1 for a in asofs if a < (first6 or "9999"))
    print(f"  rs_3m(60日)第一個有值的 as_of:{first3}")
    print(f"  rs_6m(120日)第一個有值的 as_of:{first6}")
    print(f"  → 面板 {len(asofs)} 個月裡有 **{n_no6}** 個月 rs_6m=None(A2 相對強弱 ±8 整段不計分)")
    return first6


def a5(s_prod, first_rs, panel_path):
    hr("A5 —— 三個斷裂點落在 H5 六個時代的哪幾段")
    d = pd.read_parquet(panel_path, columns=["as_of"])
    a = d["as_of"].astype(str)
    print(f"{'時代':<8}{'月數':>6}{'regime 生效':>12}{'RS 生效':>10}{'f_val 路徑①':>14}")
    from core.industry_value import industry_value_pct  # noqa: F401  (覆蓋率已在 A3 量過)
    for name, y0, y1 in ERAS:
        m = a[(a.str[:4] >= y0) & (a.str[:4] <= y1)]
        n = m.nunique()
        reg_on = "✅ 部分" if (s_prod is not None and
                              (s_prod[(s_prod.index >= y0) & (s_prod.index <= y1 + "-12-31")]
                               != "neutral").any()) else "❌ 全 neutral"
        rs_on = "✅" if (first_rs and y1 >= first_rs[:4]) else "❌"
        val_on = "✅" if y1 >= "2019" else "❌"
        print(f"{name:<8}{n:>6}{reg_on:>12}{rs_on:>10}{val_on:>14}")
    print("\n**H5 的判定結果不改寫**(凍結後跑、門檻未動)。要改的是解釋:")
    print("  「跨時代穩健」不能讀成『同一套定義在六個時代都成立』——")
    print("  前三段用的是「無 RS、regime 從未生效、f_val 走 PEG 路徑」的版本,")
    print("  後三段才是完整版。**跨時代期間並非完全使用同一套資料可得性與評分定義。**")


def main():
    asofs, panel = panel_asofs()
    print(f"面板:{panel}\n as_of {len(asofs)} 個月:{asofs[0]} → {asofs[-1]}")
    s_prod, _ = a1_a2(asofs)
    a3(asofs, panel)
    first_rs = a4(asofs)
    a5(s_prod, first_rs, panel)


if __name__ == "__main__":
    main()
