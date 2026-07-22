# -*- coding: utf-8 -*-
"""honest_backtest.py — 誠實計分板:含息 + 含成本 + 對 0050 的策略回測引擎 (0 API)
================================================================================
定位:這是「新計畫」的地基。任何選股策略只要產出『每月持有哪些股』(holdings),
本引擎就回你**含股息、扣實際成本、以 0050 為基準**的績效。目的是杜絕上一輪的翻車
(用等權除息母體當大盤 → 自我感覺良好)。

鐵律 (對照 benchmark-correction-0050 教訓):
  1. 含息:總報酬 ≈ 價格報酬 + dividend_yield_TSE/12 (標準近似;close 未還原,殖利率補回)。
  2. 含成本:逐月週轉率 × 來回費 (元大6折 買0.0855%+賣0.3855%=0.47%);可加滑價。
  3. 對 0050:不是贏『等權平均股』,是贏『買進持有 0050 (市值加權+含息)』。
  4. 樣本外:era 切分沿用 alpha_gate (探索 2019-2021/2022/2023-2026 + 封存 2005-2018)。
  5. 風險優先:報 Sharpe/Sortino/MDD/水下,不只看 CAGR。

資料:
  · 個股月度報酬 = obs_alpha.fwd (20日價格報酬) + 殖利率補息 (duckdb ASOF join price_valuation)。
  · 0050 基準:首選 data/benchmark/0050_tr.parquet (TEJ 還原收盤價,含息,2005-01+,全循環涵蓋)
    → build_benchmark.py 由 8 個 TEJ xlsx 固化而來;後備才用 finmind (未還原,2019+,補概略殖利率)。

誠實邊界:proxy/近似補息、月度非重疊、未含零股價差、回測≠未來。非投資建議。

用法 (當模組):
  from honest_backtest import Engine
  eng = Engine()                                  # 建 TR 面板 + 0050 基準
  result = eng.run(holdings_by_asof)              # {as_of: [stock_id,...]} → 績效 dict
  eng.report(result, "我的策略")                   # 印指標表 + 對 0050
================================================================================
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
import pandas as pd

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
BENCH_TR = Path(__file__).resolve().parent / "data" / "benchmark" / "0050_tr.parquet"  # TEJ 還原價(含息)2005+
FINMIND_0050 = Path.home() / "finmind_cache" / "TaiwanStockPrice" / "0050.parquet"      # 後備:僅 2019+ 未還原
OBS_ALPHA = Path(__file__).resolve().parent.parent / "data" / "research_base" / "obs_alpha.parquet"

COST_RT = 0.47          # 元大6折 來回 (%)
SLIPPAGE_RT = 0.10      # 滑價估計 來回 (%),保守
RF_ANNUAL = 1.0
BENCH_YIELD = 3.5       # 0050 概略年殖利率 (%);僅後備路徑(finmind 未還原價)才用,TEJ 還原價已含息

ERAS = [
    ("2005-2009(海嘯)", "2005-01-01", "2009-12-31"),
    ("2010-2014",       "2010-01-01", "2014-12-31"),
    ("2015-2018",       "2015-01-01", "2018-12-31"),
    ("2019-2021",       "2019-01-01", "2021-12-31"),
    ("2022空頭",        "2022-01-01", "2022-12-31"),
    ("2023-2026",       "2023-01-01", "2026-12-31"),
]


class Engine:
    def __init__(self, adv_floor: float = 2e7, cost_rt: float = COST_RT + SLIPPAGE_RT):
        self.cost = cost_rt
        self.tr = self._build_tr_panel(adv_floor)          # 個股月度總報酬面板
        self.asofs = sorted(self.tr["as_of"].unique())
        self.bench = self._build_benchmark()               # {as_of: 0050 月總報酬%}

    # ---- 個股總報酬面板 (價格報酬 + 殖利率補息) ----
    def _build_tr_panel(self, adv_floor) -> pd.DataFrame:
        import duckdb
        obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "fwd", "adv20", "listed_ok"])
        obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= adv_floor)].copy()  # noqa: E712
        con = duckdb.connect()
        con.register("obs", obs[["as_of", "stock_id"]])
        # ASOF join:每個 (stock_id, as_of) 取 date<=as_of 最近一筆的殖利率
        yq = con.execute(f"""
            SELECT o.as_of, o.stock_id, p.dividend_yield_TSE AS dy
            FROM obs o ASOF LEFT JOIN
                 read_parquet('{TEJ_CACHE}/price_valuation/*.parquet', union_by_name=true) p
            ON o.stock_id = p.stock_id AND p.date <= o.as_of
        """).df()
        obs = obs.merge(yq, on=["as_of", "stock_id"], how="left")
        obs["dy"] = pd.to_numeric(obs["dy"], errors="coerce").fillna(0.0).clip(0, 15)
        # 總報酬 = 價格報酬 + 殖利率/12 (20交易日≈1/12年;補回除息跳空)
        obs["tr"] = obs["fwd"] + obs["dy"] / 12.0
        return obs[["as_of", "stock_id", "tr", "fwd"]]

    # ---- 0050 基準:首選 TEJ 還原價(含息,2005+);後備 finmind(未還原,2019+,補概略殖利率) ----
    def _build_benchmark(self) -> dict:
        import bisect
        if BENCH_TR.exists():
            # TEJ 還原收盤價已內含股息再投入 → 直接算總報酬,不補 BENCH_YIELD
            b = pd.read_parquet(BENCH_TR)[["date", "adj_close"]].sort_values("date").reset_index(drop=True)
            b["date"] = b["date"].astype(str)
            col, yield_addon = "adj_close", 0.0
        elif FINMIND_0050.exists():
            # 後備:未還原價,需分割還原 + 概略殖利率補息
            b = pd.read_parquet(FINMIND_0050)[["date", "close"]].sort_values("date").reset_index(drop=True)
            r = b["close"].pct_change()
            for i in b.index[r < -0.5]:
                ratio = round(b.loc[i - 1, "close"] / b.loc[i, "close"])
                if ratio >= 2:
                    b.loc[:i - 1, "close"] /= ratio
            b["date"] = b["date"].astype(str)
            col, yield_addon = "close", BENCH_YIELD / 12.0
        else:
            return {}
        bp = dict(zip(b["date"], b[col])); bd = sorted(bp)
        def px(d):
            i = bisect.bisect_right(bd, d) - 1
            return bp[bd[i]] if i >= 0 else None
        out = {}
        for i, a in enumerate(self.asofs):
            nxt = self.asofs[i + 1] if i + 1 < len(self.asofs) else None
            p0, p1 = px(str(a)), (px(str(nxt)) if nxt else None)
            if p0 and p1:
                out[a] = (p1 / p0 - 1) * 100 + yield_addon
        return out

    # ---- 執行:holdings {as_of: [stock_id]} → 淨值 + 指標 ----
    def run(self, holdings: dict, weights: dict | None = None) -> dict:
        tr_map = {(r.as_of, r.stock_id): r.tr for r in self.tr.itertuples()}
        prev = set(); rows = []
        for a in self.asofs:
            ids = [s for s in holdings.get(a, []) if (a, s) in tr_map]
            if not ids:
                continue
            w = weights.get(a) if weights else None
            ws = None
            if w:
                _w = np.array([w.get(s, 0) for s in ids], float)
                ws = _w / _w.sum() if _w.sum() else None
            gross = np.average([tr_map[(a, s)] for s in ids], weights=ws) if ids else np.nan
            cur = set(ids); turn = 1 - len(cur & prev) / len(cur) if prev else 1.0
            prev = cur
            rows.append({"as_of": a, "ret": gross - turn * self.cost,
                         "gross": gross, "turn": turn, "n": len(ids),
                         "bench": self.bench.get(a, np.nan)})
        return {"monthly": pd.DataFrame(rows)}

    # ---- 指標 ----
    @staticmethod
    def _metrics(ret_pct: np.ndarray) -> dict:
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
        uw = dd < -1e-9; L = c = 0
        for u in uw:
            c = c + 1 if u else 0; L = max(L, c)
        return {"總報酬%": (eq[-1] - 1) * 100, "CAGR%": cagr, "波動%": vol, "夏普": sharpe,
                "Sortino": sortino, "MDD%": mdd, "水下(月)": L, "勝率%": (r > 0).mean() * 100}

    def report(self, result: dict, name: str = "策略"):
        m = result["monthly"].dropna(subset=["ret"])
        has_b = m["bench"].notna()
        mb = m[has_b]
        print(f"\n{'='*70}\n【{name}】含息+含成本 (來回 {self.cost:.2f}%)  對 0050 (本機基準僅 {mb['as_of'].min() if len(mb) else '-'}+)\n{'='*70}")
        s = self._metrics(m["ret"].values); b = self._metrics(mb["bench"].values)
        ss = self._metrics(mb["ret"].values)   # 同窗策略 (與0050可比)
        print(f"{'':<16}{'CAGR%':>8}{'夏普':>7}{'Sortino':>9}{'MDD%':>8}{'水下(月)':>9}{'勝率%':>7}")
        print(f"{name+'(全期)':<16}{s.get('CAGR%',0):>8.1f}{s.get('夏普',0):>7.2f}"
              f"{s.get('Sortino',0):>9.2f}{s.get('MDD%',0):>8.1f}{s.get('水下(月)',0):>9.0f}{s.get('勝率%',0):>7.0f}")
        if b:
            print(f"{name+'(0050同窗)':<16}{ss.get('CAGR%',0):>8.1f}{ss.get('夏普',0):>7.2f}"
                  f"{ss.get('Sortino',0):>9.2f}{ss.get('MDD%',0):>8.1f}{ss.get('水下(月)',0):>9.0f}{ss.get('勝率%',0):>7.0f}")
            print(f"{'0050 買進持有':<16}{b.get('CAGR%',0):>8.1f}{b.get('夏普',0):>7.2f}"
                  f"{b.get('Sortino',0):>9.2f}{b.get('MDD%',0):>8.1f}{b.get('水下(月)',0):>9.0f}{b.get('勝率%',0):>7.0f}")
            win = "✅贏" if ss.get('夏普',0) > b.get('夏普',0) else "❌輸"
            print(f"\n判定 (同窗夏普):策略 {ss.get('夏普',0):.2f} vs 0050 {b.get('夏普',0):.2f} → {win}")
        else:
            print("(無本機 0050 基準;請提供 0050 含息序列以完成對照)")
        return {"strategy": s, "bench": b, "strategy_benchwin": ss}


if __name__ == "__main__":
    print("honest_backtest 是模組。示範:把 dual-confirm 餵進來複驗 (含息+對0050)。")
    eng = Engine()
    print(f"TR 面板:{len(eng.tr)} 列, {len(eng.asofs)} 月;0050 基準涵蓋 {len(eng.bench)} 月")
