# -*- coding: utf-8 -*-
"""regime_signal_lab.py — 救專案 A 的收尾:regime 訊號的穩健度 + 分級 vs 二元 頭對頭。
================================================================================
兩個問題一次回答:
  (1) 穩健度:簡單二元 MA200 減碼(bear→30%曝險,預註冊規則)是不是**每個時代都贏 0050**,
      還是靠某一段灌出來的? → 逐時代 Sharpe 對照。
  (2) 分級值不值得:把二元升級成連續分級訊號(距離/多軸階梯/波動目標),頭對頭比,
      看「漸進」到底有沒有比「鈍的二元」好,還是徒增複雜度。

所有 regime 訊號都是**反應式、無未來函數**(均線/波動皆 trailing;as_of 當下已知)。
曝險 ∈ [0,1],bear 資產 = 現金(RF)。曝險變動收單邊成本 0.285%。個股報酬含息(引擎內建)。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import bisect
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from beat_0050.honest_backtest import Engine, RF_ANNUAL, TEJ_CACHE, ERAS
from existing_composite import build_factors, holdings_for

DERISK_COST = 0.285
BEAR_EXPO = 0.30          # 預註冊:二元 MA200 bear 時的曝險
VOL_TARGET = 15.0         # 波動目標 (%,年化),預設常數非事後調


# ---- regime 特徵:等權市場指數 + 多均線 + 波動 (日頻,trailing) ----
def build_regime_features() -> pd.DataFrame:
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
    f = pd.DataFrame({"date": ew.index.astype(str), "ew": ew.values,
                      "dret": daily.values})
    f["ma50"] = f["ew"].rolling(50, min_periods=50).mean()
    f["ma100"] = f["ew"].rolling(100, min_periods=100).mean()
    f["ma200"] = f["ew"].rolling(200, min_periods=200).mean()
    f["dist200"] = f["ew"] / f["ma200"] - 1.0
    f["vol60"] = f["dret"].rolling(60, min_periods=60).std() * np.sqrt(252) * 100
    return f.dropna(subset=["ma200"]).reset_index(drop=True)


# ---- 各 regime 規則:features → 曝險∈[0,1] ----
def expo_binary(r) -> float:
    return 1.0 if r["ew"] >= r["ma200"] else BEAR_EXPO

def expo_graded(r) -> float:                     # 距離分級:破 MA200 後隨深度線性降到 0(-20%觸底)
    if r["dist200"] >= 0:
        return 1.0
    return float(np.clip(1.0 + r["dist200"] / 0.20, 0.0, 1.0))

def expo_ladder(r) -> float:                     # 多軸階梯:站上幾條 MA / 3
    c = (r["ew"] >= r["ma50"]) + (r["ew"] >= r["ma100"]) + (r["ew"] >= r["ma200"])
    return c / 3.0

def expo_voltarget(r) -> float:                  # 波動目標:vol 超標就縮,不加槓桿
    if not r["vol60"] or r["vol60"] <= 0:
        return 1.0
    return float(np.clip(VOL_TARGET / r["vol60"], 0.0, 1.0))

RULES = {"二元MA200(30%)": expo_binary, "距離分級": expo_graded,
         "多軸階梯": expo_ladder, "波動目標": expo_voltarget}


# ---- 把曝險套到雙確認月報酬 (bear→現金),含變動成本 ----
def apply_expo(dual: pd.DataFrame, feat_at, rule) -> np.ndarray:
    cash = RF_ANNUAL / 12.0
    out, prev_e = [], 1.0
    for _, row in dual.iterrows():
        fr = feat_at(str(row["as_of"]))
        e = 1.0 if fr is None else float(rule(fr))
        r = e * row["ret"] + (1 - e) * cash - abs(e - prev_e) * DERISK_COST
        prev_e = e
        out.append(r)
    return np.array(out, float)


def metrics(ret_pct) -> dict:
    r = np.asarray(ret_pct, float) / 100.0
    r = r[~np.isnan(r)]
    if len(r) < 6:
        return {}
    eq = np.cumprod(1 + r); n = len(r)
    cagr = (eq[-1] ** (12 / n) - 1) * 100
    vol = r.std(ddof=1) * np.sqrt(12) * 100
    downside = r[r < 0].std(ddof=1) * np.sqrt(12) * 100 if (r < 0).any() else np.nan
    sharpe = (cagr - RF_ANNUAL) / vol if vol else np.nan
    sortino = (cagr - RF_ANNUAL) / downside if downside and downside > 0 else np.nan
    dd = eq / np.maximum.accumulate(eq) - 1; mdd = dd.min() * 100
    calmar = cagr / abs(mdd) if mdd else np.nan
    uw = dd < -1e-9; L = c = 0
    for u in uw:
        c = c + 1 if u else 0; L = max(L, c)
    return {"CAGR": cagr, "波動": vol, "夏普": sharpe, "Sortino": sortino,
            "Calmar": calmar, "MDD": mdd, "水下": L}


def era_sharpe(as_ofs, rets):
    df = pd.DataFrame({"a": [str(x) for x in as_ofs], "r": rets})
    out = {}
    for name, s, e in ERAS:
        sub = df[(df["a"] >= s) & (df["a"] <= e)]
        m = metrics(sub["r"].values)
        out[name] = m.get("夏普", np.nan)
    out["全期"] = metrics(df["r"].values).get("夏普", np.nan)
    return out


if __name__ == "__main__":
    eng = Engine()
    obs = build_factors()
    dual = eng.run(holdings_for(obs, "dual"))["monthly"].reset_index(drop=True)

    feat = build_regime_features()
    fd = feat["date"].tolist()
    frecs = feat.to_dict("records")
    def feat_at(a):
        i = bisect.bisect_right(fd, a) - 1
        return frecs[i] if i >= 0 else None

    # 預先算各規則的月報酬序列
    series = {"雙確認(原始)": dual["ret"].values}
    for name, rule in RULES.items():
        series[name] = apply_expo(dual, feat_at, rule)
    bench = dual["bench"].values

    # ===== (1) 穩健度:二元 MA200 逐時代 vs 0050 =====
    print("=" * 74)
    print("(1) 穩健度 — 逐時代夏普:預註冊二元MA200(30%) 是不是每個時代都贏 0050?")
    print("=" * 74)
    es_base = era_sharpe(dual["as_of"], series["雙確認(原始)"])
    es_bin = era_sharpe(dual["as_of"], series["二元MA200(30%)"])
    es_b = era_sharpe(dual["as_of"], bench)
    print(f"{'時代':<16}{'原始':>9}{'二元MA200':>11}{'0050':>9}{'二元勝?':>9}")
    for name, _, _ in ERAS:
        win = "✅" if (es_bin[name] > es_b[name]) else "❌"
        print(f"{name:<16}{es_base[name]:>9.2f}{es_bin[name]:>11.2f}{es_b[name]:>9.2f}{win:>8}")
    win = "✅" if es_bin['全期'] > es_b['全期'] else "❌"
    print(f"{'全期':<16}{es_base['全期']:>9.2f}{es_bin['全期']:>11.2f}{es_b['全期']:>9.2f}{win:>8}")
    nwin = sum(1 for n, _, _ in ERAS if es_bin[n] > es_b[n])
    print(f"\n→ 二元MA200 在 {nwin}/{len(ERAS)} 個時代夏普勝 0050。")

    # ===== (2) 分級 vs 二元:全循環頭對頭 =====
    print("\n" + "=" * 74)
    print("(2) 分級 vs 二元 — 全循環指標頭對頭 (漸進值不值得複雜度?)")
    print("=" * 74)
    cols = ["CAGR", "波動", "夏普", "Sortino", "Calmar", "MDD", "水下"]
    print(f"{'配置':<16}" + "".join(f"{c:>9}" for c in cols))
    print("-" * 79)
    for name in ["雙確認(原始)", *RULES.keys()]:
        m = metrics(series[name])
        print(f"{name:<16}" + "".join(f"{m.get(c, float('nan')):>9.2f}" for c in cols))
    mb = metrics(bench)
    print(f"{'0050買進持有':<16}" + "".join(f"{mb.get(c, float('nan')):>9.2f}" for c in cols))

    # ===== (3) 分級變體逐時代夏普 (一致性) =====
    print("\n" + "=" * 74)
    print("(3) 各分級變體逐時代夏普 — 誰最一致 (不靠單一時代)")
    print("=" * 74)
    variants = list(RULES.keys())
    print(f"{'時代':<16}" + "".join(f"{v:>11}" for v in variants) + f"{'0050':>9}")
    for name, _, _ in ERAS:
        row = f"{name:<16}"
        for v in variants:
            row += f"{era_sharpe(dual['as_of'], series[v])[name]:>11.2f}"
        row += f"{es_b[name]:>9.2f}"
        print(row)
    row = f"{'全期':<16}"
    for v in variants:
        row += f"{era_sharpe(dual['as_of'], series[v])['全期']:>11.2f}"
    print(row + f"{es_b['全期']:>9.2f}")
