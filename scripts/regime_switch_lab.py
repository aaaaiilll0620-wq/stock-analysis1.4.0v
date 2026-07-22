# -*- coding: utf-8 -*-
"""regime_switch_lab.py — 綜合分 vs c2、以及「分多空切換」值不值得 (0 API)
================================================================================
回答使用者:多頭看綜合分、空頭看 c2 —— 這樣切換有沒有比『永遠 c2』好?

背景:綜合分 (balanced) 權重 momentum=0.27 (正,追漲) vs c2 = …−momentum (反向,避漲多)。
兩者對動能下相反賭注 → 多頭綜合分『看起來強』很可能只是動能上行的當下錯覺。本專案
已『預註冊 regime 切換配方』且樣本外否決 (universe_screen §16),故此處嚴格用即時 regime
旗回測,看切換是否真能贏過已驗證全天候的 c2。

方法 (對齊 alpha_gate_lab / inst_reversal_lab):
  · 基底 obs_alpha (2005-2026,257月,流動池 adv20≥20M,前瞻20日,去市場 beta)。
  · 綜合分『proxy』= 五維橫斷面百分位依 balanced 權重加權 (0.31 基本面/0.08 估值/0.19 技術/
    0.27 動能/0.15 籌碼);因子覆蓋所限,基本面以 revenue_yoy 代理、技術以 52週高+BBP 代理
    —— 為近似,但精準捕捉『動能傾斜』這個與 c2 的核心差異 (誠實邊界,非 app 精確 composite)。
  · c2 proxy = mean(產業內估值, 營收YoY, 52週高, 100−動能) 百分位。
  · 即時 regime 旗:TEJ 全市場等權指數 vs MA200 (與 universe_screen §16-E 同定義,無未來函數)。
  · 量測:各排序器逐月 IC (Spearman vs fwd);前十分位組合的 excess 報酬;
    三策略 (永遠c2 / 多頭綜合分+空頭c2 / 永遠綜合分) 的 excess,總體+分多空+六時代。

判讀:切換要值得,需『多頭綜合分+空頭c2』的 excess 明顯 > 永遠 c2,且六時代穩。
      若打不贏永遠 c2 → 印證專案既有結論『別切換』,答案是 c2 為主、綜合分當多頭確認。

用法:
  python scripts/regime_switch_lab.py
  python scripts/regime_switch_lab.py --adv-floor 50000000 --top-pct 10
================================================================================
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab_paths import OBS_ALPHA, check_base                        # noqa: E402

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))

ERAS = [
    ("2005-2009(海嘯)", "2005-01-01", "2009-12-31"),
    ("2010-2014",       "2010-01-01", "2014-12-31"),
    ("2015-2018",       "2015-01-01", "2018-12-31"),
    ("2019-2021",       "2019-01-01", "2021-12-31"),
    ("2022空頭",        "2022-01-01", "2022-12-31"),
    ("2023-2026",       "2023-01-01", "2026-12-31"),
]

# balanced 綜合分權重 (core.scoring_manager.MODES['balanced'])
W = {"fund": 0.31, "val": 0.08, "tech": 0.19, "mom": 0.27, "whale": 0.15}


def tstat(x) -> float:
    x = np.asarray(x, dtype=float); x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def build_regime() -> pd.DataFrame:
    """TEJ 全市場等權指數 vs MA200 → 每交易日 bear 旗 (即時,無未來函數)。回 df[date,bear]。"""
    import duckdb
    con = duckdb.connect()
    px = con.execute(f"""
        SELECT stock_id, date, close FROM
        read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true)
        WHERE close > 0 ORDER BY stock_id, date
    """).df()
    px["ret"] = px.groupby("stock_id")["close"].pct_change()
    daily = (px[(px["ret"].notna()) & (px["ret"].abs() < 0.5)]
             .groupby("date")["ret"].mean().sort_index())
    ew = (1 + daily).cumprod()
    ma200 = ew.rolling(200, min_periods=200).mean()
    reg = pd.DataFrame({"date": ew.index, "bear": (ew < ma200).values})
    reg["date"] = reg["date"].astype(str)
    return reg.dropna()


def pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) * 100.0


def main():
    ap = argparse.ArgumentParser(description="綜合分 vs c2 + regime 切換回測 (0 API)")
    ap.add_argument("--adv-floor", type=float, default=20_000_000)
    ap.add_argument("--top-pct", type=float, default=10.0, help="前 N%% 分位組合 (預設10)")
    args = ap.parse_args()

    if check_base(verbose=True) and not OBS_ALPHA.exists():
        print("缺 obs_alpha.parquet;先跑 alpha_gate_lab.py --build。"); return

    obs = pd.read_parquet(OBS_ALPHA)
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= args.adv_floor)].copy()  # noqa: E712

    # --- 五維 proxy (逐月橫斷面百分位) ---
    g = obs.groupby("as_of")
    obs["_fund"] = g["revenue_yoy"].transform(pct)                       # 基本面代理:營收YoY
    obs["_val"] = g["value_ind"].transform(pct)                          # 估值:產業內位階 (高=便宜)
    obs["_tech"] = (g["high52_prox"].transform(pct) + g["bbp20"].transform(pct)) / 2
    obs["_mom"] = g["momentum"].transform(pct)                           # 動能 (高=漲多)
    obs["_whale"] = g["chip"].transform(pct)                            # 籌碼:法人20日淨買
    obs["composite"] = (W["fund"]*obs["_fund"] + W["val"]*obs["_val"] + W["tech"]*obs["_tech"]
                        + W["mom"]*obs["_mom"] + W["whale"]*obs["_whale"])
    # c2 proxy = mean(估值, 營收YoY, 52週高, 100−動能)
    obs["c2"] = (obs["_val"] + obs["_fund"] + g["high52_prox"].transform(pct)
                 + (100 - obs["_mom"])) / 4.0
    obs["fwd_excess"] = obs["fwd"] - g["fwd"].transform("mean")

    # --- 即時 regime 旗 join 到 as_of ---
    reg = build_regime()
    reg_map = dict(zip(reg["date"], reg["bear"]))
    asof_days = sorted(obs["as_of"].astype(str).unique())
    reg_dates = sorted(reg_map)
    # 每個 as_of 取『當日或之前最近交易日』的 bear 旗 (即時)
    import bisect
    bear_at = {}
    for a in asof_days:
        i = bisect.bisect_right(reg_dates, a) - 1
        bear_at[a] = reg_map[reg_dates[i]] if i >= 0 else False
    obs["bear"] = obs["as_of"].astype(str).map(bear_at)
    n_bull = sum(1 for a in asof_days if not bear_at[a])
    n_bear = len(asof_days) - n_bull
    print(f"流動池 {len(obs)} 列;{len(asof_days)} 月 (多頭 {n_bull} / 空頭 {n_bear})；前瞻20日、去beta\n")

    # ---- 逐月 IC ----
    def ic_by(df, key):
        def _i(x):
            m = x[key].notna() & x["fwd"].notna()
            return x.loc[m, key].rank().corr(x.loc[m, "fwd"].rank()) if m.sum() >= 20 else np.nan
        return df.groupby("as_of").apply(_i).dropna()

    print("="*76)
    print("【A. 排序力 IC:綜合分 proxy vs c2 proxy,分多空/六時代】(IC>0=前段跑贏後段)")
    print("="*76)
    print(f"{'區段':<16}{'月':>5}{'綜合分IC':>10}{'(t)':>7}{'c2 IC':>9}{'(t)':>7}{'贏家':>8}")
    def _seg(df, name):
        ic_c = ic_by(df, "composite"); ic_2 = ic_by(df, "c2")
        win = "綜合分" if ic_c.mean() > ic_2.mean() else "c2"
        print(f"{name:<16}{df['as_of'].nunique():>5}{ic_c.mean():>10.4f}{tstat(ic_c.values):>7.1f}"
              f"{ic_2.mean():>9.4f}{tstat(ic_2.values):>7.1f}{win:>8}")
    _seg(obs, "全期")
    _seg(obs[~obs["bear"]], "  多頭月")
    _seg(obs[obs["bear"]], "  空頭月")
    for nm, s, e in ERAS:
        d = obs[(obs["as_of"] >= s) & (obs["as_of"] <= e)]
        if len(d): _seg(d, nm)

    # ---- 前十分位組合 excess:三策略 ----
    top_q = 1 - args.top_pct/100.0
    def top_excess(df, key):
        """每月取 key 前 top-pct 的 fwd_excess 均值 → 回傳逐月序列。"""
        def _t(x):
            x = x.dropna(subset=[key, "fwd_excess"])
            if len(x) < 10: return np.nan
            thr = x[key].quantile(top_q)
            return x[x[key] >= thr]["fwd_excess"].mean()
        return df.groupby("as_of").apply(_t).dropna()

    # 逐月:依當月 regime 選 ranker
    monthly = []
    for a, x in obs.groupby("as_of"):
        bear = bool(x["bear"].iloc[0])
        def te(key):
            xx = x.dropna(subset=[key, "fwd_excess"])
            if len(xx) < 10: return np.nan
            thr = xx[key].quantile(top_q)
            return xx[xx[key] >= thr]["fwd_excess"].mean()
        monthly.append({"as_of": a, "bear": bear,
                        "always_c2": te("c2"), "always_comp": te("composite"),
                        "switch": te("c2") if bear else te("composite")})
    md = pd.DataFrame(monthly).dropna(subset=["always_c2", "always_comp", "switch"])

    print("\n" + "="*76)
    print(f"【B. 前 {args.top_pct:.0f}% 組合 excess 報酬 (月均%,去beta) — 三策略對決】")
    print("="*76)
    def report(frame, name):
        print(f"{name:<14}"
              + f"永遠c2 {frame['always_c2'].mean():+.3f}(t{tstat(frame['always_c2'].values):.1f})   "
              + f"切換 {frame['switch'].mean():+.3f}(t{tstat(frame['switch'].values):.1f})   "
              + f"永遠綜合分 {frame['always_comp'].mean():+.3f}(t{tstat(frame['always_comp'].values):.1f})")
    report(md, "全期")
    report(md[~md["bear"]], "  多頭月")
    report(md[md["bear"]], "  空頭月")
    print("\n分六時代 (excess 月均%):")
    for nm, s, e in ERAS:
        d = md[(md["as_of"] >= s) & (md["as_of"] <= e)]
        if len(d): report(d, "  " + nm)

    # ---- 判讀 ----
    sw, c2 = md["switch"].mean(), md["always_c2"].mean()
    sw_bear = md[md["bear"]]["switch"].mean(); c2_bear = md[md["bear"]]["always_c2"].mean()
    comp_bear = md[md["bear"]]["always_comp"].mean()
    print("\n" + "="*76)
    print(f"【判讀】切換 {sw:+.3f}% vs 永遠c2 {c2:+.3f}%  → "
          + ("切換勝出" if sw > c2 + 0.02 else "切換未明顯贏過永遠c2 (印證『別切換』)"))
    print(f"       空頭月:永遠綜合分 {comp_bear:+.3f}% vs c2 {c2_bear:+.3f}% → "
          + ("綜合分空頭確實較差" if comp_bear < c2_bear else "空頭差異不明顯"))
    print("="*76)

    out = OBS_ALPHA.parent / "regime_switch_stats.csv"
    md.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n逐月三策略明細已寫 {out}")


if __name__ == "__main__":
    main()
