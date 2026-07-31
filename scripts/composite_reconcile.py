# -*- coding: utf-8 -*-
"""composite_reconcile.py — real_composite 第二條路徑逐列對帳 + 缺值比例量測
================================================================================
回應 Codex 第一輪審查 §六-B(real_composite 血緣)與 §六-C(缺值語意)。

**做什麼**:抽樣 stock-month,把整條評分管線重跑一次,並用**第二套獨立寫的算術**
重算 composite,和面板存的 `real_composite` 逐列比對,再把差異**逐項歸因**到:

    regime 乘數 / dynamic weights / valuation 覆寫 / washout 覆寫 / 其餘未解釋

**⚠ 這是「獨立的合成算術重算」,不是研究紀律 §3 要求的「第二條獨立實作」**
(2026-07-31 Codex 第二輪審查指定的措辭)。預測器(`build_pit_stockdata` → 五個引擎)是同一套 ——
那是被測對象,換掉就不是對帳了。獨立的只有**合成層的算術**:`_indep_composite()` 自行依規格重寫
權重相乘、正規化、bucket 替換,不呼叫 `advisor.advise()`;判斷式(`_bull_stack` / `_detect_washout`)
**仍共用 advisor 的**。→ 可作為診斷證據,**不得**宣稱已滿足「第二條獨立實作逐月對帳」。

**⚠ 抽樣,不是全 panel**:預設 60 檔 / 7,369 stock-months,原始面板 263,928 列(抽樣率 2.79%)。
結論一律要帶上「在 N 檔等距抽樣、M stock-months 中」。

**不做什麼**:不寫任何面板、不改任何公式、不跑 OOS(Codex §六 禁止事項)。

用法:python scripts/composite_reconcile.py --stocks 40
      python scripts/composite_reconcile.py --stocks 120 --out <csv>
"""
from __future__ import annotations
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from lab_paths import resolve_realbody   # noqa: E402

MODE = "balanced"
FACE2KEY = {"f_fund": "fundamental", "f_val": "valuation", "f_tech": "technical",
            "f_mom": "momentum", "f_whale": "whale"}


def hr(t):
    print("\n" + "=" * 92 + f"\n{t}\n" + "=" * 92)


# ----------------------------------------------------------------------------
# 第二條路徑:合成層算術的獨立重寫(規格見 core/advisor.py:advise 第 84–120 行)
# ----------------------------------------------------------------------------
def _indep_composite(buckets: dict, base_w: dict, regime, dyn_on: bool) -> float:
    """獨立重算 composite。刻意不呼叫 advisor,只依規格:
       1) mw = base_w × regime_multipliers(regime)
       2) 若 dyn_on:valuation 砍 60%,其中 60% 給 momentum、40% 給 whale
       3) composite = Σ bucket·mw / Σ mw,四捨五入到小數 2 位
    """
    from core.regime import regime_multipliers
    mult = regime_multipliers(regime) if regime else {k: 1.0 for k in base_w}
    mw = {k: float(v) * float(mult.get(k, 1.0)) for k, v in base_w.items()}
    if dyn_on:
        cut = mw.get("valuation", 0.0) * 0.6
        mw["valuation"] = mw.get("valuation", 0.0) - cut
        mw["momentum"] = mw.get("momentum", 0.0) + cut * 0.6
        mw["whale"] = mw.get("whale", 0.0) + cut * 0.4
    wsum = sum(max(0.0, mw.get(k, 0.0)) for k in buckets)
    if wsum <= 0:
        return float("nan")
    return round(sum(buckets[k] * mw.get(k, 0.0) for k in buckets) / wsum, 2)


def _published_missing(df, as_of, lag_days: int) -> bool:
    """該 as_of 當下,這個財報資料集有沒有『已公告』的列(重寫 build_pit_stockdata 的 _published)。"""
    if df is None or "date" not in getattr(df, "columns", []):
        return True
    ok = df[pd.to_datetime(df["date"], errors="coerce") + pd.Timedelta(days=lag_days)
            <= pd.to_datetime(as_of)]
    return ok.empty


def run(stocks_n: int, out_csv: str | None):
    from beat_0050.realbody.bt_bundle import bt_fetch_history
    from core.backtest import build_pit_stockdata, PUBLISH_LAG_DAYS
    from core.score_store import _engines, _regime_at
    from core.scoring_manager import ScoringManager

    panel_path = resolve_realbody(1e6)
    panel = pd.read_parquet(panel_path)
    panel["as_of"] = panel["as_of"].astype(str)
    panel["stock_id"] = panel["stock_id"].astype(str)
    base_w = dict(ScoringManager.MODES[MODE]["composite_weights"])

    # 抽樣:對 stock_id 排序後等距抽,避免只抽到大型股或某個號段
    ids = sorted(panel["stock_id"].unique())
    step = max(1, len(ids) // stocks_n)
    sample_ids = ids[::step][:stocks_n]
    sub = panel[panel["stock_id"].isin(sample_ids)]
    print(f"面板 {panel_path.name}:{len(panel):,} 列 / {len(ids)} 檔")
    print(f"抽樣 {len(sample_ids)} 檔 → {len(sub):,} stock-months(等距抽樣,非隨機)")

    fund, val, scorer, advisor = _engines(MODE)
    rows, t0 = [], time.time()
    for i, sid in enumerate(sample_ids, 1):
        try:
            bundle = bt_fetch_history(sid)
        except Exception as e:
            print(f"  [{i}/{len(sample_ids)}] {sid} bundle 失敗:{type(e).__name__}")
            continue
        asofs = sorted(sub[sub["stock_id"] == sid]["as_of"].unique())
        for a in asofs:
            stock = build_pit_stockdata(bundle, a)
            if stock is None:
                continue
            fund_res = fund.evaluate(vars(stock))
            val_res = val.evaluate(vars(stock))
            score = scorer.calculate_score(stock)

            # --- 面板存的五面(build_realbody_scores._score_stock 取哪幾個值)---
            f_fund = float(fund_res.get("total_score"))
            f_val_raw = float(val_res.get("valuation_score", 0.0))
            f_tech = float(score.technical_score)
            f_mom = float(score.momentum_score)
            f_whale_raw = float(score.whale_score)

            # --- advisor 合成時**實際使用**的 bucket(advise:84-102)---
            washout, _ = advisor._detect_washout(stock)
            chip_bucket = (min(100.0, max(f_whale_raw, 60.0) + 5.0) if washout else f_whale_raw)
            val_status = val_res.get("valuation_status", "")
            val_bucket = 50.0 if "資料不足" in val_status else f_val_raw
            buckets = {"fundamental": f_fund, "valuation": val_bucket,
                       "technical": f_tech, "momentum": f_mom, "whale": chip_bucket}

            regime = _regime_at(a)
            dyn_on = bool(advisor._bull_stack(stock)
                          and stock.ma20_bias >= advisor.trend_bias_min
                          and stock.rsi >= advisor.lead_rsi_min)

            comp_indep = _indep_composite(buckets, base_w, regime, dyn_on)

            # --- 生產路徑(呼叫 advisor 本體)---
            advisor.current_regime = regime
            advisor.advise(stock, fund_res, val_res, score)
            comp_prod = float(score.total_score)

            rows.append(dict(
                stock_id=sid, as_of=a,
                f_fund=f_fund, f_val=f_val_raw, f_tech=f_tech, f_mom=f_mom, f_whale=f_whale_raw,
                val_bucket=val_bucket, chip_bucket=chip_bucket,
                regime=regime or "neutral", dyn_on=dyn_on, washout=washout,
                val_override=("資料不足" in val_status),
                comp_indep=comp_indep, comp_prod=comp_prod,
                pe_missing=(stock.pe_ratio is None),
                is_missing=_published_missing(bundle.income, a, PUBLISH_LAG_DAYS),
                bs_missing=_published_missing(bundle.balance, a, PUBLISH_LAG_DAYS),
                cf_missing=_published_missing(bundle.cashflow, a, PUBLISH_LAG_DAYS),
            ))
        if i % 10 == 0:
            el = time.time() - t0
            print(f"  [{i}/{len(sample_ids)}] {len(rows):,} 列, {el:.0f}s "
                  f"(估剩 ~{(len(sample_ids)-i)/i*el/60:.1f} 分)", flush=True)

    d = pd.DataFrame(rows)
    if d.empty:
        print("❌ 抽樣沒有任何可評分的列")
        return
    d = d.merge(panel[["as_of", "stock_id", "real_composite"] + list(FACE2KEY)],
                on=["as_of", "stock_id"], how="inner", suffixes=("", "_panel"))
    print(f"\n與面板對得上的列:{len(d):,}")
    if out_csv:
        d.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"明細 → {out_csv}")
    report(d, base_w)


def report(d: pd.DataFrame, base_w: dict):
    # ---------------- B1 五面是原始分還是 bucket ----------------
    hr("B1 —— 面板的 f_* 欄位是原始分數,還是合成前的 bucket?")
    same_val = np.isclose(d["f_val"], d["f_val_panel"], atol=1e-6)
    same_whale = np.isclose(d["f_whale"], d["f_whale_panel"], atol=1e-6)
    print(f"  重跑的原始 f_val  == 面板 f_val :{same_val.mean()*100:.2f}%")
    print(f"  重跑的原始 f_whale== 面板 f_whale:{same_whale.mean()*100:.2f}%")
    n_vd = int((~np.isclose(d["val_bucket"], d["f_val"], atol=1e-6)).sum())
    n_wd = int((~np.isclose(d["chip_bucket"], d["f_whale"], atol=1e-6)).sum())
    print(f"\n  → 面板存的是**原始分數**,不是 bucket。實測 bucket ≠ 原始分的列:")
    print(f"     valuation 覆寫(資料不足→50):{n_vd:,} 列 ({n_vd/len(d)*100:.2f}%)")
    print(f"     washout 覆寫(→max(whale,60)+5):{n_wd:,} 列 ({n_wd/len(d)*100:.2f}%)")

    # ---------------- B2 合成算術重算對帳 ----------------
    hr(f"B2 —— 合成算術重算對帳(**抽樣 {len(d):,} 列,非全 panel**):獨立算術 vs 生產 advisor vs 面板")
    e_ip = (d["comp_indep"] - d["comp_prod"]).abs()
    e_pp = (d["comp_prod"] - d["real_composite"]).abs()
    e_ir = (d["comp_indep"] - d["real_composite"]).abs()
    for name, e in [("獨立算術 vs 生產 advisor(同一次執行)", e_ip),
                    ("生產 advisor 重跑 vs 面板 real_composite", e_pp),
                    ("獨立算術 vs 面板 real_composite", e_ir)]:
        print(f"  {name:<42} |Δ|≤0.01: {(e <= 0.01).mean()*100:6.2f}%   "
              f"中位 {e.median():.4f}  max {e.max():.4f}")
    print("\n  判讀:第 1 列是**合成層算術**的對帳(應該 100%);第 2、3 列若掉下來,")
    print("        代表面板與現在重跑不同 —— 那是面板過期或環境差異,不是算術問題。")

    # ---------------- B3 殘差歸因 ----------------
    hr("B3 —— 殘差逐項歸因(靜態權重 Σw·f_panel 為基準)")
    from core.regime import regime_multipliers
    faces = list(FACE2KEY)
    w0 = np.array([base_w[FACE2KEY[c]] for c in faces])
    F = d[[c + "_panel" for c in faces]].to_numpy(float)
    static = F @ w0 / w0.sum()
    total = d["real_composite"].to_numpy(float) - static

    # 逐列建 mw(regime → dyn),並逐步替換 bucket,量每一步的邊際貢獻
    steps = np.zeros((len(d), 4))
    B_raw = d[[c + "_panel" for c in faces]].to_numpy(float)
    B_val = B_raw.copy(); B_val[:, faces.index("f_val")] = d["val_bucket"].to_numpy(float)
    B_all = B_val.copy(); B_all[:, faces.index("f_whale")] = d["chip_bucket"].to_numpy(float)
    for i, (reg, dyn) in enumerate(zip(d["regime"], d["dyn_on"])):
        mult = regime_multipliers(reg)
        w_reg = np.array([base_w[FACE2KEY[c]] * mult[FACE2KEY[c]] for c in faces])
        w_dyn = w_reg.copy()
        if dyn:
            j_v, j_m, j_w = faces.index("f_val"), faces.index("f_mom"), faces.index("f_whale")
            cut = w_dyn[j_v] * 0.6
            w_dyn[j_v] -= cut; w_dyn[j_m] += cut * 0.6; w_dyn[j_w] += cut * 0.4
        base = B_raw[i] @ w0 / w0.sum()
        s1 = B_raw[i] @ w_reg / w_reg.sum()          # +regime
        s2 = B_raw[i] @ w_dyn / w_dyn.sum()          # +dyn
        s3 = B_val[i] @ w_dyn / w_dyn.sum()          # +valuation 覆寫
        s4 = B_all[i] @ w_dyn / w_dyn.sum()          # +washout 覆寫
        steps[i] = [s1 - base, s2 - s1, s3 - s2, s4 - s3]
    explained = steps.sum(axis=1)
    unexplained = total - explained

    print(f"  {'來源':<26}{'平均貢獻':>10}{'|貢獻| 中位':>12}{'|貢獻|>0.01 的列%':>18}")
    for j, name in enumerate(["regime 乘數", "dynamic weights", "valuation 覆寫", "washout 覆寫"]):
        s = steps[:, j]
        print(f"  {name:<26}{s.mean():>+10.3f}{np.median(np.abs(s)):>12.3f}"
              f"{(np.abs(s) > 0.01).mean()*100:>17.2f}%")
    print(f"  {'—— 四項合計(explained)':<26}{explained.mean():>+10.3f}"
          f"{np.median(np.abs(explained)):>12.3f}{(np.abs(explained) > 0.01).mean()*100:>17.2f}%")
    print(f"  {'殘差總量(面板−靜態)':<26}{total.mean():>+10.3f}{np.median(np.abs(total)):>12.3f}"
          f"{(np.abs(total) > 0.01).mean()*100:>17.2f}%")
    print(f"\n  **未解釋殘差**:|≤0.01| {(np.abs(unexplained) <= 0.01).mean()*100:.2f}%   "
          f"中位 {np.median(unexplained):+.4f}  "
          f"p99 {np.percentile(np.abs(unexplained), 99):.4f}  max {np.abs(unexplained).max():.4f}")
    print("  → 未解釋比例若接近 0,代表 40% 對不上的部分**已被這四項完全解釋**,沒有第五個來源。")

    # ---------------- B4 狀態旗標分布 ----------------
    hr("B4 —— 面板沒存、但真的有在動的四個狀態")
    print(f"  regime 分布      : {d['regime'].value_counts(normalize=True).round(4).to_dict()}")
    print(f"  dynamic weights 啟用: {d['dyn_on'].mean()*100:.2f}%")
    print(f"  washout 觸發     : {d['washout'].mean()*100:.2f}%")
    print(f"  valuation 覆寫   : {d['val_override'].mean()*100:.2f}%")

    # ---------------- C 缺值比例 ----------------
    hr("C —— 缺值比例(Codex §六-C;只報分布與影響,不修公式)")
    n = len(d)
    items = [("PE 缺失(stock.pe_ratio is None)", d["pe_missing"]),
             ("損益表缺失(as_of 當下無已公告列)", d["is_missing"]),
             ("資產負債表缺失", d["bs_missing"]),
             ("現金流量表缺失", d["cf_missing"]),
             ("三大財報同時缺失", d["is_missing"] & d["bs_missing"] & d["cf_missing"]),
             ("valuation 面板值 ≠ 合成用值", ~np.isclose(d["val_bucket"], d["f_val"], atol=1e-6)),
             ("whale 面板值 ≠ 合成用值(washout)", ~np.isclose(d["chip_bucket"], d["f_whale"], atol=1e-6))]
    print(f"  {'情況':<40}{'列數':>10}{'比例':>10}")
    for name, m in items:
        print(f"  {name:<40}{int(m.sum()):>10,}{m.mean()*100:>9.2f}%")

    print("\n  逐年(三大財報同時缺失 / PE 缺失):")
    d2 = d.copy(); d2["y"] = d2["as_of"].str[:4]
    d2["all3"] = d2["is_missing"] & d2["bs_missing"] & d2["cf_missing"]
    g = d2.groupby("y")[["all3", "pe_missing", "bs_missing"]].mean() * 100
    g["n"] = d2.groupby("y").size()
    print(g.round(2).to_string())

    hr("C2 —— 缺財報那批列的 f_fund 長什麼樣(§5-3 的『兩個錯互相抵銷』實證)")
    m = d["is_missing"] & d["bs_missing"]
    if m.sum() >= 10:
        print(f"  缺損益表+資產負債表 {int(m.sum()):,} 列:f_fund 中位 {d.loc[m,'f_fund'].median():.1f}  "
              f"p10 {d.loc[m,'f_fund'].quantile(.1):.1f}  p90 {d.loc[m,'f_fund'].quantile(.9):.1f}")
        print(f"  其餘 {int((~m).sum()):,} 列:            f_fund 中位 {d.loc[~m,'f_fund'].median():.1f}  "
              f"p10 {d.loc[~m,'f_fund'].quantile(.1):.1f}  p90 {d.loc[~m,'f_fund'].quantile(.9):.1f}")
        print("  → 若兩者中位接近,證實『缺資料的列在分布上不露馬腳』。")
    else:
        print(f"  缺損益表+資產負債表的列只有 {int(m.sum())} 列,樣本不足以比較。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks", type=int, default=40)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    run(args.stocks, args.out)


if __name__ == "__main__":
    main()
