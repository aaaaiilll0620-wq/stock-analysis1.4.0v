# -*- coding: utf-8 -*-
"""inst_reversal_lab.py — 「法人賣轉買 → 前瞻報酬」回測 (0 API)
================================================================================
回答使用者的問題:**法人『賣轉買』(淨賣超轉淨買超) 能不能當推薦/擇時參考?**

背景:app 的法人閘門目前用『連買天數 + 占比』確認吸籌持續性 (見 app._inst_buying);
「賣轉買」是不同構造 —— 一個『轉折/擇時』訊號 (長窗還在派發、短窗剛翻買)。這在本專案
從未被驗證過。方法學刻意對齊 alpha_gate_lab (同一份 obs_alpha 月度面板、同前瞻 20 日
報酬、同六時代切分),結果可與 C2 各腿直接比較;誠實邊界照 streak_return_lab 的規格。

資料基底:data/research_base/obs_alpha.parquet (2005-01~2026-05,257 月,2158 檔)
  · chip   = 法人 20 日淨買/量 (signed 淨參與率;正=買超)
  · chip5  = 法人  5 日淨買/量   ← 短窗 (近期態度)
  · chip60 = 法人 60 日淨買/量   ← 長窗 (季度態度)
  · fwd    = 前瞻 20 交易日報酬 (%)

訊號 (兩組定義都測):
  A) 短 chip5 vs 長 chip(20日):賣轉買 = 長<0 (曾派發) 且 短>0 (轉吸籌)
  B) 短 chip5 vs 長 chip60     :同上,長窗拉到季度
四態:賣轉買 / 持續買 / 持續賣 / 買轉賣 (依 sign(長), sign(短);剔除剛好 0 的中性)

量測 (去市場 beta):
  · fwd_excess = fwd − 同 as_of 流動池橫斷面均值 → 只留相對邊際。
  · 每態:n、excess 均值/中位、以『逐月態均值序列』算 t (月度面板 20 日前瞻≈非重疊)。
  · 六時代逐一看穩定性 (2022 空頭最關鍵);另附連續版 IC:(chip5 − chip20) 排序 vs fwd。
  · 關鍵對照:賣轉買 vs 持續買 —— 轉折有沒有比『本來就在買』多帶資訊?

誠實邊界:
  · 只在『流動池』(listed_ok 且 adv20 >= --adv-floor,預設 20M) 內測,避開薄量股失真
    (與 app 閘門處理 1256/新紡 同精神)。
  · fwd 未還原除權息 (與整條驗證鏈同口徑);去 beta 已抵銷大部分系統性偏誤。
  · 觀察性關聯非因果;不是投資建議。

用法:
  python scripts/inst_reversal_lab.py                    # 主結論 (adv 20M)
  python scripts/inst_reversal_lab.py --adv-floor 50000000
================================================================================
"""
from __future__ import annotations

import os
import sys
import argparse

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab_paths import OBS_ALPHA, check_base                       # noqa: E402

# 六時代 (與 alpha_gate_lab 完全一致:探索 3 段 + 封存 hold-out 3 段)
ERAS = [
    ("2005-2009(海嘯)", "2005-01-01", "2009-12-31"),
    ("2010-2014",       "2010-01-01", "2014-12-31"),
    ("2015-2018",       "2015-01-01", "2018-12-31"),
    ("2019-2021",       "2019-01-01", "2021-12-31"),
    ("2022空頭",        "2022-01-01", "2022-12-31"),
    ("2023-2026",       "2023-01-01", "2026-12-31"),
]

STATES = ["賣轉買", "持續買", "持續賣", "買轉賣"]


def classify(long_s: pd.Series, short_s: pd.Series) -> pd.Series:
    """依 (長窗, 短窗) 淨參與率的正負分四態;任一為 0 → 中性 (NaN,排除)。"""
    out = pd.Series(index=long_s.index, dtype=object)
    lp, ln = long_s > 0, long_s < 0
    sp, sn = short_s > 0, short_s < 0
    out[ln & sp] = "賣轉買"      # 長派發 → 短吸籌
    out[lp & sp] = "持續買"
    out[ln & sn] = "持續賣"
    out[lp & sn] = "買轉賣"      # 長吸籌 → 短派發
    return out


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def ic_series(df: pd.DataFrame, key: str) -> pd.Series:
    """逐 as_of 的 Spearman IC:key 排序 vs fwd 排序 (同 alpha_gate_lab.ic_series)。"""
    def _ic(g):
        m = g[key].notna() & g["fwd"].notna()
        if m.sum() < 20:
            return np.nan
        return g.loc[m, key].rank().corr(g.loc[m, "fwd"].rank())
    return df.groupby("as_of").apply(_ic).dropna()


def summarize(obs: pd.DataFrame, long_col: str, short_col: str, title: str, min_n: int):
    print(f"\n{'='*80}\n【{title}】長窗={long_col} 短窗={short_col}  (excess = 減同月流動池均值)\n{'='*80}")
    obs = obs.copy()
    obs["state"] = classify(obs[long_col], obs[short_col])
    obs = obs.dropna(subset=["state", "fwd_excess"])

    # 逐月態均值 → 每態一條跨月序列 (去 beta 後的相對邊際),t 以此序列算 (≈非重疊)
    cell = obs.groupby(["as_of", "state"])["fwd_excess"].mean().reset_index()
    print(f"{'狀態':<8}{'n(觀測)':>9}{'占比%':>7}{'excess均值%':>12}{'excess中位%':>13}{'月數':>6}{'t':>8}")
    n_all = len(obs)
    rows = {}
    for s in STATES:
        g = obs[obs["state"] == s]
        if g.empty:
            continue
        series = cell[cell["state"] == s]["fwd_excess"].to_numpy()
        t = tstat(series)
        flag = "" if len(series) >= min_n else " ⚠少樣本"
        print(f"{s:<8}{len(g):>9}{len(g)/n_all*100:>7.1f}{g['fwd_excess'].mean():>12.3f}"
              f"{g['fwd_excess'].median():>13.3f}{len(series):>6}{t:>8.2f}{flag}")
        rows[s] = {"n": len(g), "mean_excess": g["fwd_excess"].mean(),
                   "median_excess": g["fwd_excess"].median(), "t": t, "n_months": len(series)}

    # 關鍵對照:賣轉買 − 持續買 (轉折是否多帶資訊)
    if "賣轉買" in rows and "持續買" in rows:
        diff = rows["賣轉買"]["mean_excess"] - rows["持續買"]["mean_excess"]
        print(f"\n  ► 賣轉買 − 持續買 excess 差 = {diff:+.3f}%  "
              f"({'轉折加分' if diff > 0 else '轉折不如持續買'})")
    return obs, rows


def by_era(obs: pd.DataFrame, long_col: str, short_col: str):
    print(f"\n── 六時代穩定性:『賣轉買』excess 均值 (t)  [長={long_col} 短={short_col}] ──")
    obs = obs.copy()
    obs["state"] = classify(obs[long_col], obs[short_col])
    print(f"{'時代':<18}{'賣轉買n':>8}{'excess均值%':>12}{'月數':>6}{'t':>8}{'  連續IC(chip5−20)':>18}")
    for name, s, e in ERAS:
        d = obs[(obs["as_of"] >= s) & (obs["as_of"] <= e)]
        rv = d[(d["state"] == "賣轉買")].dropna(subset=["fwd_excess"])
        if rv.empty:
            print(f"{name:<18}{'—':>8}"); continue
        cell = rv.groupby("as_of")["fwd_excess"].mean().to_numpy()
        # 連續版:每月 (chip5 − chip) 排序 vs fwd 的 IC 平均
        dd = d.dropna(subset=["chip5", "chip", "fwd"]).copy()
        dd["rev_score"] = dd["chip5"] - dd["chip"]
        ic = ic_series(dd, "rev_score")
        ic_mean = ic.mean() if len(ic) else float("nan")
        print(f"{name:<18}{len(rv):>8}{rv['fwd_excess'].mean():>12.3f}{len(cell):>6}"
              f"{tstat(cell):>8.2f}{ic_mean:>18.4f}")


def main():
    ap = argparse.ArgumentParser(description="法人賣轉買 → 前瞻報酬回測 (0 API)")
    ap.add_argument("--adv-floor", type=float, default=20_000_000, help="流動性下限 adv20 (NTD,預設20M)")
    ap.add_argument("--min-n", type=int, default=12, help="報 t 的最少月數 (預設 12)")
    args = ap.parse_args()

    if check_base(verbose=True) and not OBS_ALPHA.exists():
        print("缺 obs_alpha.parquet;請先跑 alpha_gate_lab.py --build (見 lab_paths 檔頭)。")
        return

    obs = pd.read_parquet(OBS_ALPHA, columns=[
        "as_of", "stock_id", "fwd", "chip", "chip5", "chip10", "chip60",
        "chip_accel", "adv20", "listed_ok"])
    n0 = len(obs)
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= args.adv_floor)].copy()  # noqa: E712
    # 去市場 beta:每月流動池橫斷面均值
    obs["fwd_excess"] = obs["fwd"] - obs.groupby("as_of")["fwd"].transform("mean")
    print(f"obs_alpha {n0} 列 → 流動池 (listed_ok & adv20>={args.adv_floor/1e6:.0f}M) {len(obs)} 列;"
          f"{obs['as_of'].nunique()} 月 ({obs['as_of'].min()} ~ {obs['as_of'].max()})")
    print(f"前瞻窗 = 20 交易日 (obs_alpha 內建 fwd);excess = 減同月流動池均值 (去 beta)")

    # 主結論:兩組長短窗定義
    summarize(obs, "chip", "chip5", "定義 A:短5日 vs 長20日", args.min_n)
    by_era(obs, "chip", "chip5")
    summarize(obs, "chip60", "chip5", "定義 B:短5日 vs 長60日", args.min_n)
    by_era(obs, "chip60", "chip5")

    # 落地摘要
    obs_a = obs.copy(); obs_a["state"] = classify(obs_a["chip"], obs_a["chip5"])
    rows = []
    for name, s, e in ERAS:
        d = obs_a[(obs_a["as_of"] >= s) & (obs_a["as_of"] <= e)]
        for st in STATES:
            g = d[(d["state"] == st)].dropna(subset=["fwd_excess"])
            if g.empty:
                continue
            cell = g.groupby("as_of")["fwd_excess"].mean().to_numpy()
            rows.append({"era": name, "state": st, "n": len(g),
                         "mean_excess": round(g["fwd_excess"].mean(), 3),
                         "median_excess": round(g["fwd_excess"].median(), 3),
                         "n_months": len(cell), "t": round(tstat(cell), 2)})
    out_f = OBS_ALPHA.parent / "inst_reversal_stats.csv"
    pd.DataFrame(rows).to_csv(out_f, index=False, encoding="utf-8-sig")
    print(f"\n分態×時代摘要已寫 {out_f}")
    print("\n判讀指引:『賣轉買』要能參考,需 (1) excess 均值為正且 |t|≥2、(2) 六時代不翻向"
          "(2022 空頭至少不明顯負)、(3) 賣轉買 − 持續買 > 0 (轉折比本來就在買多帶資訊)。"
          "三者有一不成立 → 當雜訊,別接進推薦邏輯 (比照 streak 結案)。")


if __name__ == "__main__":
    main()
