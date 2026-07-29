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
  · 個股月度報酬 = exec_ret.fwd_x = open(本月訊號日+1) → open(下月訊號日+1),已含息。
    **不用 obs_alpha.fwd** —— 那條線同時有兩個方向相反的偏誤 (2026-07-29 查出):
      (a) close(T)→close(T+20) 不可執行。訊號在 T 收盤才算得出來,實務最快隔日開盤成交。
          對高換手 arm 高估約 5pp/年。
      (b) 固定 20 交易日的窗串接會**漏日**。月底相隔約 21 個交易日,每月漏約 1 天;
          21 年下來漏掉近一整年行情,約 −3pp/年。而基準腿 (close(T)→close(T')) 沒有漏,
          於是策略腿與基準腿跑在不同時鐘上。
    兩者部分抵銷,淨誤差的**大小與正負都隨換手率變動** → 無法用經驗係數事後修正,
    只能從源頭換線。面板由 `scripts/build_exec_ret.py` 產生。
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
EXEC_RET = Path(__file__).resolve().parent.parent / "data" / "research_base" / "exec_ret.parquet"
RET_COL = "fwd_x"       # 可執行報酬欄;beat_0050/* 一律由此引用,不要各自寫死字串

COST_RT = 0.47          # 元大6折 來回 (%):買 0.1425%×0.6 + 賣 0.1425%×0.6 + 證交稅 0.3%
                        # 盤中零股電子單低消 NT$1 → 綁定門檻僅 1/0.0855% ≈ 1,170 元/筆,
                        # 10 萬本金 ÷ 25 檔 = 4,000 元/筆,遠在門檻上 → 費率制生效,低消不咬人。
SLIPPAGE_RT = 0.25      # 滑價估計 來回 (%)。2026-07-29 由 0.10 上修:
                        # 實測近 2 年持股 344 檔,中位股價 64.5 元,依台股最小跳動單位算出
                        # 「1 跳價差」的來回成本等權平均已達 0.217% —— 舊值 0.10% **低於
                        # 理論下限**,是錯的而非保守。0.25% 取 1 跳下限再留一點餘裕;
                        # 零股實際價差常寬於 1 跳、量不足需追價,故這仍偏樂觀。
                        # 敏感度:滑價 0.3% 時季換手已輸 0050,月換手要到 ~1.0% 才輸。
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
        self._adv_floor = adv_floor
        self._tr_map = None
        self._pool = None
        self.tr = self._build_tr_panel(adv_floor)          # 個股月度總報酬面板
        self.asofs = sorted(self.tr["as_of"].unique())
        self.bench = self._build_benchmark()               # {as_of: 0050 月總報酬%}

    # ---- 個股總報酬面板 (可執行線,已含息) ----
    def _build_tr_panel(self, adv_floor) -> pd.DataFrame:
        if not EXEC_RET.exists():
            raise FileNotFoundError(
                f"缺少可執行報酬面板 {EXEC_RET}。\n"
                "請先跑 `python scripts/build_exec_ret.py`。\n"
                "不提供退回 obs_alpha.fwd 的後備路徑 —— 那條線同時有執行偏誤與漏日偏誤,"
                "兩者方向相反且大小隨換手率變動,靜默退回會讓結果無法判讀。")
        obs = pd.read_parquet(OBS_ALPHA, columns=["as_of", "stock_id", "fwd", "adv20", "listed_ok"])
        obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= adv_floor)].copy()  # noqa: E712
        ex = pd.read_parquet(EXEC_RET, columns=["as_of", "stock_id", "fwd_x"])
        obs = obs.merge(ex, on=["as_of", "stock_id"], how="left")
        obs["tr"] = obs["fwd_x"]          # fwd_x 已內含 dividend_yield_TSE/12
        return obs[["as_of", "stock_id", "tr", "fwd"]].dropna(subset=["tr"])

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
            # 取 as_of 的**隔一個交易日**收盤,與策略腿的 open(T+1) 進場同相位。
            # 串接後仍是買進持有(整條序列只是平移一天),但兩條腿不再差半個月的相位。
            i = bisect.bisect_right(bd, d)
            return bp[bd[i]] if i < len(bd) else None
        out = {}
        for i, a in enumerate(self.asofs):
            nxt = self.asofs[i + 1] if i + 1 < len(self.asofs) else None
            p0, p1 = px(str(a)), (px(str(nxt)) if nxt else None)
            if p0 and p1:
                out[a] = (p1 / p0 - 1) * 100 + yield_addon
        return out

    # ---- 報酬查表 (快取:ladder 會跑上百次 run,每次重建太貴) ----
    @property
    def tr_map(self) -> dict:
        if getattr(self, "_tr_map", None) is None:
            self._tr_map = {(r.as_of, r.stock_id): r.tr for r in self.tr.itertuples()}
        return self._tr_map

    @property
    def pool(self) -> dict:
        """{as_of: [stock_id]} —— 該月**有報酬可算**的全部個股 = 這個 Engine 的機會集合。"""
        if getattr(self, "_pool", None) is None:
            self._pool = {a: g["stock_id"].to_numpy()
                          for a, g in self.tr.dropna(subset=["tr"]).groupby("as_of")}
        return self._pool

    # ---- 執行:holdings {as_of: [stock_id]} → 淨值 + 指標 ----
    def run(self, holdings: dict, weights: dict | None = None) -> dict:
        tr_map = self.tr_map
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

    # ==================================================================
    # 基準階梯 (2026-07-30) —— 一個基準回答不了三個問題
    # ------------------------------------------------------------------
    # 「輸 0050」這句判定把三件事綁在一起,以致於長期給出錯的結論:
    #   (1) 選股能力   —— 對照『等權母體』(同 ADV 池、不選股)
    #   (2) 加權方式   —— 0050 市值加權 vs 策略等權。實測 2005-2026 市值加權
    #                     贏「平均流動股」約 5.8pp/年(六時代有五代為正),
    #                     等權策略開場就欠這一段,那不是選股層的錯。
    #   (3) 集中度/成本 —— 對照『換手率與持股數都對齊的隨機組合』
    #
    # 特別注意 (2026-07-29 的教訓):隨機虛無**必須對齊換手率**。
    # 每月重抽的隨機 25 檔 = 100% 換手,一年吃掉約 8.6pp 成本 —— 那在量成本,
    # 不是在量「沒有選股能力」,拿來當虛無對照會把任何低換手策略捧成天才。
    # ==================================================================
    def _realized(self, holdings: dict) -> dict:
        """{as_of: (實際持股數, 實際換手率)} —— 以 run() 的同一套過濾為準。"""
        out = {}; prev = set()
        for a in self.asofs:
            ids = [s for s in holdings.get(a, []) if (a, s) in self.tr_map]
            if not ids:
                continue
            cur = set(ids)
            out[a] = (len(ids), 1 - len(cur & prev) / len(cur) if prev else 1.0)
            prev = cur
        return out

    def matched_random(self, targets: dict, rng) -> dict:
        """持股數與換手率**都對齊** targets 的隨機組合(無選股訊號)。"""
        hold = {}; prev = []
        for a in self.asofs:
            if a not in targets:
                continue
            n, turn = targets[a]
            pool = self.pool.get(a)
            if pool is None or len(pool) == 0:
                continue
            n = min(n, len(pool))
            prev_ok = [s for s in prev if (a, s) in self.tr_map]
            keep_n = min(int(round(n * (1 - turn))), len(prev_ok), n)
            keep = list(rng.choice(prev_ok, keep_n, replace=False)) if keep_n > 0 else []
            rest = np.setdiff1d(pool, np.asarray(keep, dtype=pool.dtype)) if keep else pool
            need = min(n - len(keep), len(rest))
            new = list(rng.choice(rest, need, replace=False)) if need > 0 else []
            ids = keep + new
            if ids:
                hold[a] = ids
                prev = ids
        return hold

    def universe_ew(self) -> dict:
        """等權母體:每月持有機會集合裡的全部個股(這個 Engine 的 adv_floor 決定池)。"""
        return {a: list(v) for a, v in self.pool.items()}

    def ladder(self, holdings: dict, reps: int = 50, seed: int = 20260730) -> dict:
        """回傳 {rung: {指標}};rung ∈ 策略 / 等權母體 / 對齊隨機 / 0050。"""
        strat = self.run(holdings)["monthly"]
        targets = self._realized(holdings)
        ew = self.run(self.universe_ew())["monthly"]
        rng = np.random.default_rng(seed)
        draws = [self._metrics(self.run(self.matched_random(targets, rng))["monthly"]["ret"].values)
                 for _ in range(reps)]
        rand = {k: float(np.median([d[k] for d in draws if k in d]))
                for k in ("CAGR%", "夏普", "MDD%", "波動%")}
        # 虛無檢定:策略夏普落在「同持股數、同換手率的隨機組合」分布的哪個百分位。
        # 這是 H3a 那種對照的正確版本 —— 對齊 footprint 後,剩下的才是訊號。
        sh = np.array([d["夏普"] for d in draws if "夏普" in d], float)
        s_sh = self._metrics(strat["ret"].values).get("夏普", np.nan)
        rand["p_null"] = float((sh >= s_sh).mean()) if len(sh) else np.nan
        rand["null_p95"] = float(np.percentile(sh, 95)) if len(sh) else np.nan
        n_avg = float(np.mean([n for n, _ in targets.values()]))
        t_avg = float(np.mean([t for _, t in targets.values()]))
        return {"策略": {**self._metrics(strat["ret"].values), "n": n_avg, "turn": t_avg},
                "等權母體": {**self._metrics(ew["ret"].values),
                             "n": float(np.mean([len(v) for v in self.pool.values()])), "turn": np.nan},
                "對齊隨機": {**rand, "n": n_avg, "turn": t_avg, "reps": reps},
                "0050": {**self._metrics(strat.dropna(subset=["bench"])["bench"].values),
                         "n": 50.0, "turn": 0.0}}

    def report_ladder(self, holdings: dict, name: str = "策略", reps: int = 50) -> dict:
        L = self.ladder(holdings, reps=reps)
        print(f"\n{'='*84}\n【{name}】基準階梯 (含息含成本,來回 {self.cost:.2f}%;ADV池 ≥ {self._adv_floor:.0f})\n{'='*84}")
        print(f"{'':<26}{'檔數':>6}{'月換手%':>8}{'CAGR%':>8}{'波動%':>7}{'夏普':>7}{'MDD%':>8}")
        for k in ("策略", "等權母體", "對齊隨機", "0050"):
            m = L[k]
            lab = {"等權母體": "① 等權母體(不選股)", "對齊隨機": f"② 對齊隨機({L['對齊隨機']['reps']}次中位)",
                   "0050": "③ 0050 買進持有", "策略": f"◆ {name}"}[k]
            print(f"{lab:<26}{m['n']:>6.0f}{m['turn']*100 if m['turn']==m['turn'] else 0:>8.1f}"
                  f"{m.get('CAGR%',np.nan):>8.2f}{m.get('波動%',np.nan):>7.1f}"
                  f"{m.get('夏普',np.nan):>7.2f}{m.get('MDD%',np.nan):>8.1f}")
        s, ew, rd, b = L["策略"], L["等權母體"], L["對齊隨機"], L["0050"]
        print(f"\n(1) 選股能力  策略 − 等權母體 : {s['CAGR%']-ew['CAGR%']:+7.2f} pp/年   "
              f"夏普 {s['夏普']-ew['夏普']:+.2f}   → {'✅有' if s['CAGR%']>ew['CAGR%'] else '❌無'}")
        print(f"(2) 扣掉交易footprint  策略 − 對齊隨機 : {s['CAGR%']-rd['CAGR%']:+7.2f} pp/年   "
              f"夏普 {s['夏普']-rd['夏普']:+.2f}   "
              f"虛無 p={rd['p_null']:.3f} (隨機 p95 夏普 {rd['null_p95']:.2f})   "
              f"→ {'✅過' if rd['p_null'] < 0.05 else '❌未過'}")
        print(f"(3) 機會成本  策略 − 0050 : {s['CAGR%']-b['CAGR%']:+7.2f} pp/年   "
              f"夏普 {s['夏普']-b['夏普']:+.2f}   → {'✅值得' if s['夏普']>b['夏普'] else '❌不如買ETF'}")
        print(f"    參考:0050 − 等權母體 = {b['CAGR%']-ew['CAGR%']:+.2f} pp/年 "
              f"(市值加權的結構性優勢,不是選股層造成的)")
        return L

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
