# -*- coding: utf-8 -*-
"""equity_curve_lab.py — 雙確認/c2/大盤 含成本淨值曲線 + 風險指標 (0 API)
================================================================================
把 regime_switch_lab 的月度組合接成『資金曲線』,算實盤最該看的:
  CAGR / 年化波動 / 夏普 / 最大回撤 MDD / 水下(套牢)時間 / 勝率 / 最慘月。
成本 = 逐月週轉率 × 來回費 (元大6折:買0.0855%+賣0.3855%=0.47%)。

誠實邊界:proxy composite (非 app 精確)、close 未還原除權息、月度非重疊近似、
不含滑價/零股價差 → 實盤只會更差。回測 ≠ 未來。非投資建議。

輸出:stdout 指標表 + data/research_base/equity_curves.csv (三條淨值序列供畫圖)。
================================================================================
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, bisect
from lab_paths import OBS_ALPHA
from regime_switch_lab import build_regime

COST = 0.47          # 元大6折 來回 (%)
RF_ANNUAL = 1.0      # 無風險年利率假設 (%),算夏普用
TOP_PCT = 20


def build_factors():
    obs = pd.read_parquet(OBS_ALPHA)
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= 2e7)].copy().reset_index(drop=True)  # noqa: E712
    g = obs.groupby("as_of")
    def pct(s): return s.rank(pct=True) * 100
    obs["_f"] = g["revenue_yoy"].transform(pct); obs["_v"] = g["value_ind"].transform(pct)
    obs["_t"] = (g["high52_prox"].transform(pct) + g["bbp20"].transform(pct)) / 2
    obs["_m"] = g["momentum"].transform(pct); obs["_w"] = g["chip"].transform(pct)
    obs["composite"] = 0.31*obs["_f"]+0.08*obs["_v"]+0.19*obs["_t"]+0.27*obs["_m"]+0.15*obs["_w"]
    obs["c2"] = (obs["_v"]+obs["_f"]+g["high52_prox"].transform(pct)+(100-obs["_m"]))/4
    return obs


def monthly_returns(obs) -> pd.DataFrame:
    """逐月:雙確認/純c2 前20% 的淨報酬 (扣週轉成本) + 大盤(母體均值)。"""
    reg = build_regime(); rm = dict(zip(reg["date"], reg["bear"])); rd = sorted(rm)
    bf = lambda a: (rm[rd[bisect.bisect_right(rd, a)-1]] if bisect.bisect_right(rd, a)-1 >= 0 else False)  # noqa: E731
    prev_dc, prev_c2 = set(), set()
    rows = []
    for a, x in obs.groupby("as_of"):
        k = max(1, int(len(x) * TOP_PCT/100))
        ca = set(x.nlargest(k, "c2").index); co = set(x.nlargest(k, "composite").index)
        inter = ca & co
        if not inter:
            continue
        def net(idx, prev):
            ids = set(x.loc[list(idx), "stock_id"])
            turn = 1 - (len(ids & prev)/len(ids)) if prev else 1.0
            return x.loc[list(idx), "fwd"].mean() - turn*COST, ids
        dc, ids_dc = net(inter, prev_dc)
        c2r, ids_c2 = net(ca, prev_c2)
        prev_dc, prev_c2 = ids_dc, ids_c2
        rows.append({"as_of": a, "bear": bf(str(a)),
                     "dual": dc, "c2": c2r, "mkt": x["fwd"].mean(), "n": len(inter)})
    return pd.DataFrame(rows)


def stats(ret_pct: pd.Series, dates: pd.Series) -> dict:
    r = ret_pct.to_numpy() / 100.0
    eq = np.cumprod(1 + r)
    n = len(r)
    cagr = (eq[-1] ** (12.0/n) - 1) * 100
    vol = np.std(r, ddof=1) * np.sqrt(12) * 100
    sharpe = (cagr - RF_ANNUAL) / vol if vol > 0 else np.nan
    # 最大回撤
    peak = np.maximum.accumulate(eq); dd = eq/peak - 1
    mdd = dd.min() * 100
    # 水下時間 (最長連續 dd<0 的月數) + 到當前是否還在水下
    underwater = dd < -1e-9
    longest = cur = 0
    for u in underwater:
        cur = cur+1 if u else 0
        longest = max(longest, cur)
    return {"總報酬%": (eq[-1]-1)*100, "CAGR%": cagr, "年化波動%": vol, "夏普": sharpe,
            "最大回撤%": mdd, "最長水下(月)": longest, "勝率%": (r > 0).mean()*100,
            "最慘月%": r.min()*100, "最好月%": r.max()*100, "eq": eq}


def main():
    obs = build_factors()
    md = monthly_returns(obs)
    print(f"雙確認/c2/大盤 淨值回測 (2005-2026,{len(md)}月,proxy,含元大6折成本 {COST}%來回)\n")
    curves = {}
    print(f"{'策略':<10}{'總報酬%':>9}{'CAGR%':>8}{'年化波動%':>9}{'夏普':>7}"
          f"{'最大回撤%':>10}{'最長水下(月)':>12}{'勝率%':>7}{'最慘月%':>8}")
    for key, lab in [("dual", "雙確認20%"), ("c2", "純c2 20%"), ("mkt", "大盤(母體)")]:
        s = stats(md[key], md["as_of"]); curves[lab] = s.pop("eq")
        print(f"{lab:<10}{s['總報酬%']:>9.0f}{s['CAGR%']:>8.1f}{s['年化波動%']:>9.1f}{s['夏普']:>7.2f}"
              f"{s['最大回撤%']:>10.1f}{s['最長水下(月)']:>12.0f}{s['勝率%']:>7.0f}{s['最慘月%']:>8.1f}")

    # 分多空 CAGR
    print("\n分 regime 年化 (淨):")
    for key, lab in [("dual", "雙確認"), ("c2", "c2"), ("mkt", "大盤")]:
        bull = md[~md["bear"]][key].to_numpy()/100; bear = md[md["bear"]][key].to_numpy()/100
        ab = (np.prod(1+bull)**(12/len(bull))-1)*100; ar = (np.prod(1+bear)**(12/len(bear))-1)*100
        print(f"  {lab:<8} 多頭 {ab:+6.1f}%/年   空頭 {ar:+6.1f}%/年")

    out = pd.DataFrame({"as_of": md["as_of"], **{k: v for k, v in curves.items()}})
    p = OBS_ALPHA.parent / "equity_curves.csv"
    out.to_csv(p, index=False, encoding="utf-8-sig")
    print(f"\n淨值序列已寫 {p}")
    print("\n判讀:夏普看每單位風險的報酬 (越高越好);MDD/水下看『最壞要套牢多久』——"
          "這才是能不能撐住紀律的關鍵。proxy+未含滑價,實盤打折。")


if __name__ == "__main__":
    main()
