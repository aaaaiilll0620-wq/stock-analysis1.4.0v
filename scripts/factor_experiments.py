"""
v4.4 因子實驗 — 未來優化藍圖 7 (RS)、9 (估值重修/降權)、10 (新訊號接線) 的 A/B 篩選
================================================================================
做法:PIT StockData 只 precompute 一次 (最貴的部分),之後對每個「訊號開關組合」與
「估值變體」便宜地重算五維分數,量測:
  · 受影響維度的 Rank IC / 單因子多空 (該訊號有沒有讓維度更會排序)
  · 綜合分 Rank IC / 市場中性多空 (加進綜合後是幫忙還是拖累)
  · 留一邊際貢獻 (現行權重下抽掉該維度的差)
全部同時看「2023–2025 全期」與「2022 空頭段」,避免只配適多頭。

0 API (讀本機快取)。用法:
  python scripts/factor_experiments.py            # 全部實驗
  python scripts/factor_experiments.py --signals   # 只跑訊號開關 A/B (項7、10)
  python scripts/factor_experiments.py --valuation # 只跑估值變體 (項9)
================================================================================
"""
from __future__ import annotations

import os
import sys
import argparse
from collections import defaultdict

import numpy as np
import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
logging.basicConfig(level=logging.ERROR)

from core.backtest import Backtester, cached_fetch_history, build_pit_stockdata
from core.scoring_manager import ScoringManager
from core.fundamentals import FundamentalEngine
from core.valuation import ValuationEngine
from tests.run_backtest import DIVERSIFIED_POOL

PERIODS = [
    ("2023-2025", "2023-01-01", "2025-12-31"),
    ("2022空頭",  "2022-01-01", "2022-12-31"),
]
DIMS = ["fundamental", "valuation", "technical", "momentum", "whale"]
CW = dict(ScoringManager.MODES["balanced"]["composite_weights"])   # 靜態 balanced 權重 (同 --attribution)

# 訊號開關 → (作用引擎, 屬性名, 受影響維度)
SIGNALS = {
    "RS 相對強弱(項7)":      (ScoringManager, "USE_RS_OVERLAY", "momentum"),
    "完整KD(項10)":          (ScoringManager, "USE_KD_FULL", "technical"),
    "布林%B(項10)":          (ScoringManager, "USE_BBP", "technical"),
    "OBV趨勢(項10)":         (ScoringManager, "USE_OBV_TREND", "momentum"),
    "資產週轉率(項10)":      (FundamentalEngine, "USE_ASSET_TURNOVER", "fundamental"),
}


# ------------------------------------------------------------------------------
# 指標 (與 core.backtest.factor_attribution / validate_scores 同一套定義)
# ------------------------------------------------------------------------------
def rank_ic(rows, key):
    """每期 key 分數 vs fwd 的 Spearman 均值。rows: [{as_of, <dims>, fwd}]"""
    by = defaultdict(list)
    for r in rows:
        by[r["as_of"]].append((r[key], r["fwd"]))
    ics = []
    for _, items in by.items():
        if len(items) < 4:
            continue
        xs = pd.Series([x for x, _ in items]).rank()
        ys = pd.Series([y for _, y in items]).rank()
        if xs.std() == 0 or ys.std() == 0:
            continue
        ics.append(float(xs.corr(ys)))
    return float(np.mean(ics)) if ics else float("nan")


def spread(rows, key, q=1 / 3, min_per_side=2):
    """同日前1/3−後1/3 後續報酬差,逐期平均 (市場中性)。"""
    by = defaultdict(list)
    for r in rows:
        by[r["as_of"]].append((r[key], r["fwd"]))
    sps = []
    for _, items in by.items():
        k = int(len(items) * q)
        if k < min_per_side:
            continue
        items.sort(key=lambda x: x[0])
        sps.append(float(np.mean([f for _, f in items[-k:]]) - np.mean([f for _, f in items[:k]])))
    return float(np.mean(sps)) if len(sps) >= 3 else float("nan")


def add_composite(rows, weights=None, val_key="valuation", out_key="composite"):
    w = dict(weights or CW)
    wsum = sum(max(0.0, w.get(k, 0.0)) for k in DIMS) or 1.0
    for r in rows:
        r[out_key] = sum(
            (r[val_key] if k == "valuation" else r[k]) * float(w.get(k, 0.0)) for k in DIMS
        ) / wsum
    return rows


def loo_spread(rows, drop_dim):
    """留一:抽掉 drop_dim 後的綜合多空。"""
    w = {k: v for k, v in CW.items() if k != drop_dim}
    add_composite(rows, weights=w, out_key="_loo")
    return spread(rows, "_loo")


# ------------------------------------------------------------------------------
# precompute:PIT StockData + fwd + (基線) fund/val 結果
# ------------------------------------------------------------------------------
def precompute(bt, start, end, rebalance="M", holding=20):
    obs = []
    fund = FundamentalEngine()
    val = ValuationEngine()
    for as_of in bt._rebalance_dates(start, end, rebalance):
        for sym, b in bt.bundles.items():
            stock = build_pit_stockdata(b, as_of)
            if stock is None:
                continue
            fwd = bt._forward_return(b, as_of, holding)
            if fwd is None:
                continue
            try:
                fr = fund.evaluate(vars(stock))
                vr = val.evaluate(vars(stock))
            except Exception:
                continue
            obs.append({"as_of": as_of, "stock": stock, "fwd": float(fwd),
                        "fund_res": fr, "val_res": vr})
    return obs


def score_dims(obs, at_fund_cache=None):
    """用目前的類別開關重算五維,回傳 rows。fund 分數若非 AT 實驗直接用 precompute 基線。"""
    scorer = ScoringManager("balanced")
    rows = []
    for o in obs:
        st = o["stock"]
        if at_fund_cache is not None:
            f = at_fund_cache[id(o)]
        else:
            f = float(o["fund_res"].get("total_score", 50.0))
        vstat = o["val_res"].get("valuation_status", "")
        v = 50.0 if "資料不足" in vstat else float(o["val_res"].get("valuation_score", 0.0))
        rows.append({
            "as_of": o["as_of"], "fwd": o["fwd"],
            "fundamental": f, "valuation": v,
            "technical": float(scorer._get_technical_score(st)),
            "momentum": float(scorer._get_momentum_score(st)),
            "whale": float(scorer._get_whale_score(st)),
        })
    return add_composite(rows)


def set_flags(**kv):
    """設定訊號開關;回傳還原用的舊值。"""
    old = {}
    for label, (cls, attr, _dim) in SIGNALS.items():
        old[attr] = getattr(cls, attr)
    for attr, v in kv.items():
        for label, (cls, a, _d) in SIGNALS.items():
            if a == attr:
                setattr(cls, a, v)
    return old


def restore_flags(old):
    for label, (cls, attr, _dim) in SIGNALS.items():
        setattr(cls, attr, old[attr])


# ------------------------------------------------------------------------------
# 實驗 1:訊號開關 A/B (項 7、10)
# ------------------------------------------------------------------------------
def run_signal_ab(obs_by_period):
    print("\n" + "=" * 96)
    print("實驗 1 — 候選訊號逐一 A/B (基線 = 全關;每列只開一個訊號)")
    print("=" * 96)

    # 基線
    base = {}
    old = set_flags()
    for pname, obs in obs_by_period.items():
        base[pname] = score_dims(obs)
    restore_flags(old)

    hdr = (f"{'訊號':<18}{'維度':<12}"
           f"{'維IC全':>8}{'維IC22':>8}{'維多空全':>9}{'維多空22':>9}"
           f"{'綜IC全':>8}{'綜IC22':>8}{'綜多空全':>9}{'綜多空22':>9}")
    print(hdr)
    print("-" * 96)

    def fmt(x, pct=False):
        if np.isnan(x):
            return "n/a"
        return f"{x:+.2f}%" if pct else f"{x:+.3f}"

    # 基線列
    b_full, b_22 = base["2023-2025"], base["2022空頭"]
    print(f"{'(基線·全關)':<18}{'—':<12}"
          f"{'':>8}{'':>8}{'':>9}{'':>9}"
          f"{fmt(rank_ic(b_full, 'composite')):>8}{fmt(rank_ic(b_22, 'composite')):>8}"
          f"{fmt(spread(b_full, 'composite'), 1):>9}{fmt(spread(b_22, 'composite'), 1):>9}")
    base_dim_stats = {}
    for d in DIMS:
        base_dim_stats[d] = (rank_ic(b_full, d), rank_ic(b_22, d),
                             spread(b_full, d), spread(b_22, d))

    results = {}
    for label, (cls, attr, dim) in SIGNALS.items():
        old = set_flags(**{attr: True})
        # 資產週轉率要重算 fund
        at_cache = None
        if attr == "USE_ASSET_TURNOVER":
            fund = FundamentalEngine()
            at_cache_by = {}
            for pname, obs in obs_by_period.items():
                for o in obs:
                    at_cache_by[id(o)] = float(fund.evaluate(vars(o["stock"])).get("total_score", 50.0))
            at_cache = at_cache_by
        rows_by = {p: score_dims(obs, at_fund_cache=at_cache) for p, obs in obs_by_period.items()}
        restore_flags(old)

        rf, r22 = rows_by["2023-2025"], rows_by["2022空頭"]
        stats = dict(
            dic_full=rank_ic(rf, dim), dic_22=rank_ic(r22, dim),
            dsp_full=spread(rf, dim), dsp_22=spread(r22, dim),
            cic_full=rank_ic(rf, "composite"), cic_22=rank_ic(r22, "composite"),
            csp_full=spread(rf, "composite"), csp_22=spread(r22, "composite"),
        )
        results[label] = (dim, stats)
        bd = base_dim_stats[dim]
        print(f"{label:<18}{dim:<12}"
              f"{fmt(stats['dic_full']):>8}{fmt(stats['dic_22']):>8}"
              f"{fmt(stats['dsp_full'], 1):>9}{fmt(stats['dsp_22'], 1):>9}"
              f"{fmt(stats['cic_full']):>8}{fmt(stats['cic_22']):>8}"
              f"{fmt(stats['csp_full'], 1):>9}{fmt(stats['csp_22'], 1):>9}")
        print(f"{'  └ 基線該維度':<18}{'':<12}"
              f"{fmt(bd[0]):>8}{fmt(bd[1]):>8}{fmt(bd[2], 1):>9}{fmt(bd[3], 1):>9}")

    print("\n判讀:訊號通過 = 該維度 IC/多空 不劣於基線、且綜合 IC/多空 (尤其全期) 有改善或至少不變差;")
    print("     2022 段明顯變差者,即使全期小幅改善也應保守 (regime 濾網只調權重,不救訊號本身)。")
    return results


# ------------------------------------------------------------------------------
# 實驗 2:估值變體 (項 9) — 判斷「訊號品質 vs 因子本質」
# ------------------------------------------------------------------------------
def valuation_variants(obs):
    """對每筆 obs 算各種估值變體分數 (皆 0-100,越高=越便宜)。"""
    rows = []
    # 先收集每期的 PE/PBR 供橫斷面百分位
    pe_by_date = defaultdict(list)
    for o in obs:
        pe = getattr(o["stock"], "pe_ratio", None)
        if pe is not None and not pd.isna(pe) and pe > 0:
            pe_by_date[o["as_of"]].append(float(pe))

    val_engine = ValuationEngine()
    for o in obs:
        st = o["stock"]
        vr = o["val_res"]
        vstat = vr.get("valuation_status", "")
        v_cur = 50.0 if "資料不足" in vstat else float(vr.get("valuation_score", 0.0))

        # 變體 A:純歷史位階 (河流圖) — 拿掉 PEG 成分
        pe_pct, pb_pct, y_pct = st.pe_percentile, st.pb_percentile, st.dividend_yield_percentile
        parts, w = {}, {"pe": 0.45, "pb": 0.30, "dy": 0.25}
        if pe_pct is not None:
            parts["pe"] = 100.0 - float(pe_pct)
        if pb_pct is not None:
            parts["pb"] = 100.0 - float(pb_pct)
        if y_pct is not None:
            parts["dy"] = float(y_pct)
        if parts:
            ws = sum(w[k] for k in parts)
            v_rel = sum(parts[k] * w[k] / ws for k in parts)
        else:
            v_rel = 50.0

        # 變體 B:純 PEG (成長調整)
        v_peg = 50.0
        pe = st.pe_ratio
        growth = None
        for k in ("eps_cagr", "net_income_growth", "revenue_cum_yoy", "rev_cagr"):
            g = getattr(st, k, None)
            if g is not None and not pd.isna(g) and float(g) > 0:
                growth = float(g)
                break
        if pe is not None and not pd.isna(pe) and pe > 0 and growth:
            v_peg = val_engine._peg_to_score(pe / growth)

        # 變體 C:橫斷面 PE 便宜度 (池內同日相對估值,產業相對的近似)
        v_xsec = 50.0
        pe_list = pe_by_date.get(o["as_of"], [])
        if pe is not None and not pd.isna(pe) and pe > 0 and len(pe_list) >= 8:
            v_xsec = 100.0 * (1.0 - pd.Series(pe_list).lt(float(pe)).mean())

        rows.append({"as_of": o["as_of"], "fwd": o["fwd"],
                     "v_cur": v_cur, "v_rel": v_rel, "v_peg": v_peg, "v_xsec": v_xsec,
                     "fundamental": float(o["fund_res"].get("total_score", 50.0))})
    return rows


def run_valuation_lab(obs_by_period):
    print("\n" + "=" * 96)
    print("實驗 2 — 估值面變體 (項9):現行混合 vs 純歷史位階 vs 純 PEG vs 橫斷面PE (訊號品質診斷)")
    print("=" * 96)

    # 基線 dims (全關) 供綜合替換測試
    old = set_flags()
    dims_by = {p: score_dims(obs) for p, obs in obs_by_period.items()}
    restore_flags(old)

    variants = [("現行混合(PEG+位階)", "v_cur"), ("純歷史位階", "v_rel"),
                ("純PEG", "v_peg"), ("橫斷面PE便宜度", "v_xsec")]

    print(f"{'估值變體':<20}{'IC全':>8}{'IC22':>8}{'多空全':>9}{'多空22':>9}"
          f"{'綜多空全(替換)':>14}{'綜多空22(替換)':>14}")
    print("-" * 96)

    def fmt(x, pct=False):
        if np.isnan(x):
            return "n/a"
        return f"{x:+.2f}%" if pct else f"{x:+.3f}"

    vrows_by = {p: valuation_variants(obs) for p, obs in obs_by_period.items()}

    for label, key in variants:
        ic_f = rank_ic(vrows_by["2023-2025"], key)
        ic_22 = rank_ic(vrows_by["2022空頭"], key)
        sp_f = spread(vrows_by["2023-2025"], key)
        sp_22 = spread(vrows_by["2022空頭"], key)
        # 綜合替換:把 dims 的 valuation 換成該變體
        csp = {}
        for pname in ("2023-2025", "2022空頭"):
            drows = dims_by[pname]
            vmap = {(r["as_of"], i): r[key] for i, r in enumerate(vrows_by[pname])}
            # dims 與 vrows 同序 (同一 obs 迴圈),直接 zip
            merged = []
            for dr, vr in zip(drows, vrows_by[pname]):
                m = dict(dr)
                m["valuation"] = vr[key]
                merged.append(m)
            add_composite(merged)
            csp[pname] = spread(merged, "composite")
        print(f"{label:<20}{fmt(ic_f):>8}{fmt(ic_22):>8}{fmt(sp_f, 1):>9}{fmt(sp_22, 1):>9}"
              f"{fmt(csp['2023-2025'], 1):>14}{fmt(csp['2022空頭'], 1):>14}")

    # 降權情境:估值權重 0.08 → 0.04 / 0.00 (轉給基本面)
    print("\n估值『再降權』情境 (權重轉給基本面):")
    print(f"{'情境':<20}{'綜IC全':>8}{'綜IC22':>8}{'綜多空全':>9}{'綜多空22':>9}")
    print("-" * 60)
    for label, vw in [("現行 val=0.08", 0.08), ("再降 val=0.04", 0.04), ("砍零 val=0.00", 0.0)]:
        w = dict(CW)
        w["fundamental"] = w["fundamental"] + (CW["valuation"] - vw)
        w["valuation"] = vw
        stats = []
        for pname in ("2023-2025", "2022空頭"):
            rows = [dict(r) for r in dims_by[pname]]
            add_composite(rows, weights=w)
            stats.append((rank_ic(rows, "composite"), spread(rows, "composite")))
        print(f"{label:<20}{fmt(stats[0][0]):>8}{fmt(stats[1][0]):>8}"
              f"{fmt(stats[0][1], 1):>9}{fmt(stats[1][1], 1):>9}")

    print("\n判讀:若『所有』變體 IC/多空皆 ≤ 0 → 因子本質問題 (此池估值無排序力) → 走降權;")
    print("     若某變體明顯優於現行 → 訊號品質問題 → 用該變體重修估值引擎。")


# ------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="v4.4 因子實驗 (項7/9/10;0 API)")
    ap.add_argument("--signals", action="store_true", help="只跑訊號開關 A/B")
    ap.add_argument("--valuation", action="store_true", help="只跑估值變體")
    args = ap.parse_args()
    do_sig = args.signals or not args.valuation
    do_val = args.valuation or not args.signals

    print(f"載入 {len(DIVERSIFIED_POOL)} 檔本機快取 (0 API)…")
    bt = Backtester(symbols=list(DIVERSIFIED_POOL), mode="balanced")
    bt.load(fetcher=lambda s: cached_fetch_history(s, refresh=False))

    obs_by_period = {}
    for pname, s, e in PERIODS:
        print(f"precompute PIT 特徵:{pname} ({s} ~ {e})…")
        obs_by_period[pname] = precompute(bt, s, e)
        print(f"  {len(obs_by_period[pname])} 筆觀測")

    if do_sig:
        run_signal_ab(obs_by_period)
    if do_val:
        run_valuation_lab(obs_by_period)


if __name__ == "__main__":
    main()
