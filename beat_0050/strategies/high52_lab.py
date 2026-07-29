# -*- coding: utf-8 -*-
"""high52_lab.py — high52_prox 選股層的確認性檢定 (預註冊 docs/預註冊_High52Lab.md)
================================================================================
背景:`high52_prox / 高 / N=8 / ADV>=100萬` 是**在全樣本上、從 864 個 arm 裡挑出來的**。
它的全期數字不是預測,是後見之明的最大值。本腳本執行預註冊的三組確認性檢定:

  H1  walk-forward   —— 檢定「每年重跑一次掃描、挑當下最好 arm」這個**協定**的樣本外表現
  H2  配對 t 檢定    —— 對現行雙確認逐月配對,並拆解「因子 vs 放寬 ADV」的貢獻
  H3  虛無對照       —— 隨機選股 / 報酬置換 / **掃 864 次的最大值**(選擇性偏誤校正)

報酬線一律用 `data/research_base/exec_ret.parquet` 的 `fwd_t1`
= open(T+1) → open(T+21) 含息,即「訊號當日收盤算出、隔日開盤下單」的可執行線。
不使用 obs_alpha.fwd(close→close,不可執行,對高換手 arm 高估 5.6pp/年)。

用法:
    python beat_0050/strategies/high52_lab.py --part scan   # 全 arm 掃描 (可執行線)
    python beat_0050/strategies/high52_lab.py --part h1
    python beat_0050/strategies/high52_lab.py --part h2
    python beat_0050/strategies/high52_lab.py --part h3a
    python beat_0050/strategies/high52_lab.py --part h3c --reps 200
    python beat_0050/strategies/high52_lab.py --part all
================================================================================
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = Path(__file__).resolve().parents[2]
TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
OBS_ALPHA = PROJ / "data" / "research_base" / "obs_alpha.parquet"
EXEC_RET = PROJ / "data" / "research_base" / "exec_ret.parquet"
BENCH_TR = PROJ / "beat_0050" / "data" / "benchmark" / "0050_tr.parquet"
OUTDIR = PROJ / "beat_0050" / "results"

# ---- 預註冊 §2 共同設定 ----
FEE_RT = 0.47          # 手續費 + 證交稅,來回 %
RF = 1.0               # 無風險利率 %
RET_COL = "fwd_x"      # 可執行報酬線:open(本月訊號日+1) → open(下月訊號日+1)
SEED = 20260729
MIN_MONTHS = 100       # arm 納入掃描排名的最少月數
WF_MIN_TRAIN = 60      # H1 最短訓練期(月)
WF_MIN_ARM = 36        # H1 arm 在訓練窗內的最少月數
WF_STEP = 12           # H1 每 12 個月重選一次

ADV_TIERS = [("2000萬", 2e7), ("500萬", 5e6), ("100萬", 1e6), ("無門檻", 0.0)]
MODES = [("top20%", "pct", 0.20), ("top10%", "pct", 0.10), ("top5%", "pct", 0.05),
         ("N=25", "fix", 25), ("N=15", "fix", 15), ("N=8", "fix", 8)]
FACTORS = [
    "value", "value_ind", "momentum", "mom60", "mom120", "chip", "chip5", "chip10",
    "chip60", "chip_accel", "eps", "roe", "revenue_yoy", "rev_yoy_3m", "rev_accel",
    "op_income", "net_income", "eps_pos_q4", "high52_prox", "rsi14", "bbp20",
    "ma_gap60", "vol60", "ratio_1000up", "big_d4w", "big_d12w", "holders_chg12w",
    "pledge_pct", "pledge_d3m", "director_holding_pct",
]
WINNER = ("high52_prox", "高", "N=8", "100萬")   # 待檢定的贏家 arm


# ==============================================================================
# 面板 → 矩陣
# ==============================================================================
class Panel:
    """把 obs_alpha × exec_ret 攤成 (月 × 股) 矩陣,讓 arm 評估變成純向量運算。"""

    def __init__(self) -> None:
        obs = pd.read_parquet(OBS_ALPHA)
        obs = obs[obs["listed_ok"] == True].copy()  # noqa: E712
        ex = pd.read_parquet(EXEC_RET)
        obs = obs.merge(ex, on=["as_of", "stock_id"], how="left")
        obs = obs.dropna(subset=[RET_COL, "adv20"])

        self.months = np.array(sorted(obs["as_of"].unique()))
        self.month_s = np.array([str(m)[:10] for m in self.months])
        stocks = np.array(sorted(obs["stock_id"].unique()))
        self.stocks = stocks
        mi = {m: i for i, m in enumerate(self.months)}
        si = {s: j for j, s in enumerate(stocks)}
        r = obs["as_of"].map(mi).to_numpy()
        c = obs["stock_id"].map(si).to_numpy()
        self.T, self.S = len(self.months), len(stocks)
        shape = (self.T, self.S)

        def mat(col, dtype=np.float32):
            a = np.full(shape, np.nan, dtype=dtype)
            a[r, c] = obs[col].to_numpy(dtype=np.float64)
            return a

        self.RET = mat(RET_COL)
        self.RET2 = mat("fwd_t2")
        self.RETCC = mat("fwd_cc")
        self.SLIP = mat("tick_slip")
        self.ADV = mat("adv20", np.float64)
        self.F = {f: mat(f) for f in FACTORS if f in obs.columns}
        self.HAS_RET = np.isfinite(self.RET)
        # ADV 分層的有效遮罩
        self.tier_valid = {name: (self.HAS_RET & (self.ADV >= thr)) for name, thr in ADV_TIERS}
        self._rank_cache: dict[tuple, np.ndarray] = {}
        self.bench = self._benchmark()

    # ---- 0050 含息基準,對齊同一個執行窗:open(本月訊號日+1) → open(下月訊號日+1) ----
    # 串接後正好等於「買進持有」,無缺口無重疊,與策略序列完全可比。
    def _benchmark(self) -> np.ndarray:
        b = pd.read_parquet(BENCH_TR).sort_values("date").reset_index(drop=True)
        d = b["date"].astype(str).to_numpy()
        px = pd.to_numeric(b["adj_close"], errors="coerce").to_numpy(float)
        base = np.array([int(np.searchsorted(d, m, side="right")) - 1 for m in self.month_s])
        out = np.full(self.T, np.nan)
        for t in range(self.T - 1):
            i, j = base[t] + 1, base[t + 1] + 1
            if i < 0 or j >= len(px):
                continue
            if px[i] > 0 and px[j] > 0:
                out[t] = (px[j] / px[i] - 1) * 100
        return out

    # ---- 排名 (1 = 最好);無效值排到最後 ----
    def ranks(self, factor: str, asc: bool, tier: str) -> np.ndarray:
        key = (factor, asc, tier)
        if key in self._rank_cache:
            return self._rank_cache[key]
        v = self.F[factor]
        valid = self.tier_valid[tier] & np.isfinite(v)
        x = np.where(valid, v, np.inf if asc else -np.inf).astype(np.float64)
        order = np.argsort(x if asc else -x, axis=1, kind="stable")
        rk = np.empty(order.shape, dtype=np.int16)
        np.put_along_axis(rk, order, np.arange(1, self.S + 1, dtype=np.int16)[None, :], axis=1)
        rk = np.where(valid, rk, np.int16(32767)).astype(np.int16)
        self._rank_cache[key] = rk
        return rk

    def mask(self, factor: str, asc: bool, tier: str, kind: str, k) -> np.ndarray:
        rk = self.ranks(factor, asc, tier)
        nv = (self.tier_valid[tier] & np.isfinite(self.F[factor])).sum(1)
        if kind == "pct":
            kk = np.maximum(1, (nv * k).astype(int))
        else:
            kk = np.minimum(np.full(self.T, int(k)), np.maximum(nv, 1))
        return (rk <= kk[:, None]) & (rk != 32767)


# ==============================================================================
# arm 評估
# ==============================================================================
def evaluate(M: np.ndarray, RET: np.ndarray, SLIP: np.ndarray) -> np.ndarray:
    """遮罩 → 月度淨報酬 (%),未持有的月份為 NaN。成本 = 換手 × (手續費 + 當月平均滑價)。"""
    cnt = M.sum(1)
    act = np.where(cnt > 0)[0]
    out = np.full(M.shape[0], np.nan)
    if len(act) == 0:
        return out
    Ma = M[act]
    ca = cnt[act].astype(float)
    gross = np.einsum("ij,ij->i", Ma, np.nan_to_num(RET[act])) / ca
    slip = np.einsum("ij,ij->i", Ma, np.nan_to_num(SLIP[act])) / ca
    # 交集必須先 & 再 sum:np.einsum 對 bool×bool 會以 bool 累加、飽和成 0/1,
    # 換手率會被釘在 1−1/k 附近(2026-07-29 對帳查出)。
    inter = (Ma[1:] & Ma[:-1]).sum(1).astype(float)
    turn = np.concatenate([[1.0], 1.0 - inter / ca[1:]])
    out[act] = gross - turn * (FEE_RT + slip)
    return out


def turnover(M: np.ndarray) -> float:
    cnt = M.sum(1)
    act = np.where(cnt > 0)[0]
    if len(act) < 2:
        return np.nan
    Ma, ca = M[act], cnt[act].astype(float)
    inter = (Ma[1:] & Ma[:-1]).sum(1).astype(float)
    return float(np.mean(np.concatenate([[1.0], 1.0 - inter / ca[1:]])))


def met(r: np.ndarray) -> dict:
    r = np.asarray(r, float)
    r = r[np.isfinite(r)] / 100.0
    if len(r) < 6:
        return {}
    eq = np.cumprod(1 + r)
    n = len(r)
    cagr = (eq[-1] ** (12 / n) - 1) * 100
    vol = r.std(ddof=1) * np.sqrt(12) * 100
    dd = eq / np.maximum.accumulate(eq) - 1
    return {"cagr": cagr, "sharpe": (cagr - RF) / vol if vol else np.nan,
            "mdd": dd.min() * 100, "n": n}


def sharpe_only(r: np.ndarray) -> float:
    r = r[np.isfinite(r)] / 100.0
    if len(r) < 6:
        return np.nan
    eq = np.cumprod(1 + r)
    n = len(r)
    cagr = (eq[-1] ** (12 / n) - 1) * 100
    vol = r.std(ddof=1) * np.sqrt(12) * 100
    return (cagr - RF) / vol if vol else np.nan


# ==============================================================================
# 全 arm 掃描 (可執行線)
# ==============================================================================
def full_scan(P: Panel, RET: np.ndarray | None = None, verbose: bool = True,
              with_turnover: bool = False):
    """回 (keys, NET[, TURN]) —— NET.shape = (n_arm, T)。"""
    RET = P.RET if RET is None else RET
    keys, series, turns = [], [], []
    t0 = time.time()
    for tier, _ in ADV_TIERS:
        for f in FACTORS:
            if f not in P.F or np.isfinite(P.F[f]).sum() < 20000:
                continue
            for dname, asc in [("高", False), ("低", True)]:
                for mname, kind, k in MODES:
                    M = P.mask(f, asc, tier, kind, k)
                    net = evaluate(M, RET, P.SLIP)
                    if np.isfinite(net).sum() < MIN_MONTHS:
                        continue
                    keys.append((f, dname, mname, tier))
                    series.append(net)
                    if with_turnover:
                        turns.append(turnover(M))
        if verbose:
            print(f"  [ADV {tier}] 累計 {len(keys)} arm  ({time.time()-t0:.0f}s)", flush=True)
    NET = np.vstack(series)
    return (keys, NET, np.array(turns)) if with_turnover else (keys, NET)


# ==============================================================================
# 雙確認 (現行選股層) — 定義沿用 beat_0050/strategies/existing_composite.py
# ==============================================================================
def dual_confirm_mask(P: Panel, tier: str, top_pct: int = 20) -> np.ndarray:
    valid = P.tier_valid[tier]

    def pct(name):
        v = P.F[name]
        ok = valid & np.isfinite(v)
        x = np.where(ok, v, -np.inf).astype(np.float64)
        order = np.argsort(-x, axis=1, kind="stable")
        rk = np.empty(order.shape, dtype=np.float64)
        np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.float64)[None, :], axis=1)
        nv = ok.sum(1).astype(float)[:, None]
        out = np.where(ok, 100.0 * (1.0 - (rk - 1) / np.maximum(nv, 1)), np.nan)
        return out

    f, v = pct("revenue_yoy"), pct("value_ind")
    t = (pct("high52_prox") + pct("bbp20")) / 2
    m, w = pct("momentum"), pct("chip")
    composite = 0.31 * f + 0.08 * v + 0.19 * t + 0.27 * m + 0.15 * w
    c2 = (v + f + pct("high52_prox") + (100 - m)) / 4

    def topk(score):
        ok = valid & np.isfinite(score)
        x = np.where(ok, score, -np.inf)
        order = np.argsort(-x, axis=1, kind="stable")
        rk = np.empty(order.shape, dtype=np.int32)
        np.put_along_axis(rk, order, np.arange(1, P.S + 1, dtype=np.int32)[None, :], axis=1)
        kk = np.maximum(1, (ok.sum(1) * top_pct // 100).astype(int))
        return (rk <= kk[:, None]) & ok

    return topk(composite) & topk(c2)


def winner_mask(P: Panel, tier: str = "100萬", n: int = 8) -> np.ndarray:
    return P.mask("high52_prox", False, tier, "fix", n)


# ==============================================================================
# H1 — walk-forward
# ==============================================================================
def run_h1(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H1  walk-forward:檢定「每年重跑掃描、挑當下最好 arm」這個協定的樣本外表現")
    print("=" * 92)
    keys, NET, turns = full_scan(P, with_turnover=True)
    print(f"候選網格 {len(keys)} arm × {P.T} 月")

    picks, oos = [], np.full(P.T, np.nan)
    t = WF_MIN_TRAIN
    while t < P.T:
        end = min(t + WF_STEP, P.T)
        tr = NET[:, :t]
        n_ok = np.isfinite(tr).sum(1)
        sh = np.array([sharpe_only(tr[i]) if n_ok[i] >= WF_MIN_ARM else np.nan
                       for i in range(len(keys))])
        if np.all(~np.isfinite(sh)):
            t = end
            continue
        best = np.nanmax(sh)
        cand = np.where(np.isfinite(sh) & (sh >= best - 1e-12))[0]
        i = cand[np.argmin(turns[cand])] if len(cand) > 1 else cand[0]
        oos[t:end] = NET[i, t:end]
        picks.append({"from": P.month_s[t], "to": P.month_s[end - 1],
                      "arm": " / ".join(keys[i]), "train_sharpe": sh[i],
                      "train_months": int(n_ok[i]),
                      "oos_ret": float(np.nansum(NET[i, t:end]))})
        t = end

    span = slice(WF_MIN_TRAIN, P.T)
    m_oos = met(oos[span])
    m_bh = met(P.bench[span])
    wm = evaluate(winner_mask(P), P.RET, P.SLIP)
    m_fix = met(wm[span])

    print(f"\nOOS 期間 {P.month_s[WF_MIN_TRAIN]} ~ {P.month_s[-1]}  "
          f"({m_oos.get('n', 0)} 個月, {len(picks)} 次重選)\n")
    print(f"{'重選期間':<22}{'選中的 arm':<42}{'訓練夏普':>10}{'訓練月數':>10}")
    for p in picks:
        print(f"{p['from'][:7]}~{p['to'][:7]:<14}{p['arm']:<42}{p['train_sharpe']:>10.2f}{p['train_months']:>10}")

    n_h52 = sum(1 for p in picks if p["arm"].startswith("high52_prox"))
    print(f"\n{'':<24}{'CAGR%':>10}{'夏普':>9}{'MDD%':>9}{'月數':>7}")
    for lab, m in [("H1a 協定 walk-forward", m_oos), ("H1b 固定贏家 arm", m_fix),
                   ("     0050 含息買進持有", m_bh)]:
        print(f"{lab:<24}{m.get('cagr', np.nan):>10.2f}{m.get('sharpe', np.nan):>9.2f}"
              f"{m.get('mdd', np.nan):>9.1f}{m.get('n', 0):>7}")

    h1a = (m_oos.get("sharpe", -9) > m_bh.get("sharpe", 9)) and \
          (m_oos.get("cagr", -9) > m_bh.get("cagr", 9))
    h1b = (m_fix.get("sharpe", -9) > m_bh.get("sharpe", 9)) and \
          (m_fix.get("cagr", -9) > m_bh.get("cagr", 9))
    h1c = n_h52 / max(len(picks), 1) >= 0.5
    print(f"\nH1a 協定 OOS 優於 0050 (夏普且 CAGR)      → {'✅通過' if h1a else '❌否定'}")
    print(f"H1b 固定贏家 arm 於同段 OOS 優於 0050      → {'✅通過' if h1b else '❌否定'}")
    print(f"H1c high52_prox 被選中 {n_h52}/{len(picks)} 年 (門檻 ≥50%) → {'✅通過' if h1c else '❌否定'}")
    return {"h1a": h1a, "h1b": h1b, "h1c": h1c, "picks": picks,
            "m_oos": m_oos, "m_fix": m_fix, "m_bh": m_bh, "oos": oos}


# ==============================================================================
# H2 — 對雙確認的配對 t 檢定
# ==============================================================================
def paired(a: np.ndarray, b: np.ndarray, rng, block: int = 6, nboot: int = 5000) -> dict:
    ok = np.isfinite(a) & np.isfinite(b)
    d = (a - b)[ok]
    n = len(d)
    t = d.mean() / (d.std(ddof=1) / np.sqrt(n))
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, max(n - block, 1), size=(nboot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(nboot, -1)[:, :n]
    means = d[np.clip(idx, 0, n - 1)].mean(1)
    return {"n": n, "mean": d.mean(), "t": t,
            "boot_lo": np.percentile(means, 2.5), "boot_hi": np.percentile(means, 97.5),
            "p_boot": float(np.mean(means <= 0))}


def run_h2(P: Panel) -> dict:
    print("\n" + "=" * 92)
    print("H2  配對 t 檢定:high52 vs 現行雙確認(同月、同報酬線、同成本模型)")
    print("=" * 92)
    rng = np.random.default_rng(SEED)
    series = {
        "high52 N=8 ADV≥100萬": evaluate(winner_mask(P, "100萬", 8), P.RET, P.SLIP),
        "high52 N=8 ADV≥2000萬": evaluate(winner_mask(P, "2000萬", 8), P.RET, P.SLIP),
        "雙確認 ADV≥2000萬(現行)": evaluate(dual_confirm_mask(P, "2000萬"), P.RET, P.SLIP),
        "雙確認 ADV≥100萬": evaluate(dual_confirm_mask(P, "100萬"), P.RET, P.SLIP),
    }
    print(f"\n{'策略':<26}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'月數':>7}{'月換手%':>10}")
    tmask = {"high52 N=8 ADV≥100萬": winner_mask(P, "100萬", 8),
             "high52 N=8 ADV≥2000萬": winner_mask(P, "2000萬", 8),
             "雙確認 ADV≥2000萬(現行)": dual_confirm_mask(P, "2000萬"),
             "雙確認 ADV≥100萬": dual_confirm_mask(P, "100萬")}
    for k, v in series.items():
        m = met(v)
        print(f"{k:<26}{m.get('cagr', np.nan):>9.2f}{m.get('sharpe', np.nan):>8.2f}"
              f"{m.get('mdd', np.nan):>9.1f}{m.get('n', 0):>7}{turnover(tmask[k])*100:>10.1f}")
    mb = met(P.bench)
    print(f"{'0050 含息買進持有':<26}{mb['cagr']:>9.2f}{mb['sharpe']:>8.2f}{mb['mdd']:>9.1f}{mb['n']:>7}{0.0:>10.1f}")

    tests = [
        ("H2a", "high52 N=8 ADV≥100萬", "雙確認 ADV≥2000萬(現行)"),
        ("H2b", "high52 N=8 ADV≥100萬", "雙確認 ADV≥100萬"),
        ("H2c", "high52 N=8 ADV≥2000萬", "雙確認 ADV≥2000萬(現行)"),
    ]
    print(f"\n{'假設':<6}{'比較':<50}{'月數':>6}{'平均月差pp':>12}{'配對t':>8}{'bootstrap 95%CI':>22}{'判定':>8}")
    res = {}
    for tag, x, y in tests:
        r = paired(series[x], series[y], rng)
        ok = r["t"] > 2.0 and r["mean"] > 0
        res[tag.lower()] = ok
        res[tag.lower() + "_stat"] = r
        print(f"{tag:<6}{x + ' − ' + y:<50}{r['n']:>6}{r['mean']:>12.3f}{r['t']:>8.2f}"
              f"{'[' + format(r['boot_lo'], '.3f') + ', ' + format(r['boot_hi'], '.3f') + ']':>22}"
              f"{'✅' if ok else '❌':>8}")
    # 額外對照:對 0050 的配對
    r0 = paired(series["high52 N=8 ADV≥100萬"], P.bench, rng)
    print(f"{'(參考)':<6}{'high52 N=8 ADV≥100萬 − 0050含息':<50}{r0['n']:>6}{r0['mean']:>12.3f}{r0['t']:>8.2f}")
    return res


# ==============================================================================
# H3 — 虛無對照
# ==============================================================================
def _random_masks(P: Panel, tier: str, k: int, reps: int, rng):
    """每次抽樣:每月從該層有效母體隨機取 k 檔。yield 遮罩。"""
    valid = P.tier_valid[tier]
    for _ in range(reps):
        u = rng.random((P.T, P.S))
        x = np.where(valid, u, np.inf)
        part = np.argpartition(x, k - 1, axis=1)[:, :k]
        M = np.zeros((P.T, P.S), dtype=bool)
        np.put_along_axis(M, part, True, axis=1)
        M &= valid
        yield M


def run_h3ab(P: Panel, reps: int = 2000) -> dict:
    print("\n" + "=" * 92)
    print(f"H3a/H3b 虛無對照(各 {reps} 次抽樣;門檻 = 觀測值 ≥ 虛無分布 99 百分位)")
    print("=" * 92)
    rng = np.random.default_rng(SEED)
    Mw = winner_mask(P, "100萬", 8)
    obs = met(evaluate(Mw, P.RET, P.SLIP))
    print(f"觀測:high52 N=8 ADV≥100萬  CAGR {obs['cagr']:.2f}%  夏普 {obs['sharpe']:.2f}")

    # H3a 隨機選 8 檔(同母體、同 N、同成本)
    t0 = time.time()
    sa, ca = np.empty(reps), np.empty(reps)
    for i, M in enumerate(_random_masks(P, "100萬", 8, reps, rng)):
        m = met(evaluate(M, P.RET, P.SLIP))
        sa[i], ca[i] = m.get("sharpe", np.nan), m.get("cagr", np.nan)
        if i % 500 == 0:
            print(f"  H3a {i}/{reps}  ({time.time()-t0:.0f}s)", flush=True)
    # H3b 報酬逐月置換(保留 arm 真實選股 → 換手/滑價結構不變,只打斷報酬對應)
    rng2 = np.random.default_rng(SEED + 1)
    valid = P.tier_valid["100萬"]
    sb = np.empty(reps)
    cb = np.empty(reps)
    for i in range(reps):
        RP = P.RET.copy()
        for t in range(P.T):
            j = np.where(valid[t])[0]
            if len(j) > 1:
                RP[t, j] = P.RET[t, rng2.permutation(j)]
        m = met(evaluate(Mw, RP, P.SLIP))
        sb[i], cb[i] = m.get("sharpe", np.nan), m.get("cagr", np.nan)
        if i % 200 == 0:
            print(f"  H3b {i}/{reps}  ({time.time()-t0:.0f}s)", flush=True)

    out = {}
    print(f"\n{'虛無':<26}{'夏普 p50':>10}{'p95':>8}{'p99':>8}{'觀測百分位':>12}{'判定':>7}")
    for tag, s, lab in [("h3a", sa, "隨機選 8 檔"), ("h3b", sb, "報酬逐月置換")]:
        s = s[np.isfinite(s)]
        pctile = float(np.mean(s < obs["sharpe"]) * 100)
        ok = pctile >= 99.0
        out[tag] = ok
        out[tag + "_pct"] = pctile
        print(f"{lab:<26}{np.percentile(s, 50):>10.2f}{np.percentile(s, 95):>8.2f}"
              f"{np.percentile(s, 99):>8.2f}{pctile:>11.1f}%{'✅' if ok else '❌':>7}")
    for tag, c, lab in [("h3a", ca, "隨機選 8 檔"), ("h3b", cb, "報酬逐月置換")]:
        c = c[np.isfinite(c)]
        print(f"  ({lab} CAGR p50 {np.percentile(c,50):.2f}%  p99 {np.percentile(c,99):.2f}%  "
              f"觀測 {obs['cagr']:.2f}% → 百分位 {np.mean(c < obs['cagr'])*100:.1f}%)")
    out["obs"] = obs
    np.savez(OUTDIR / "high52_h3ab.npz", sa=sa, sb=sb, ca=ca, cb=cb)
    return out


def run_h3c(P: Panel, reps: int = 200) -> dict:
    """掃 864 次的最大值虛無 + 解析式 DSR。"""
    print("\n" + "=" * 92)
    print(f"H3c 選擇性偏誤:掃 864 個 arm 的『最大夏普』虛無分布 (R={reps} 次置換掃描)")
    print("=" * 92)
    keys, NET = full_scan(P)
    sh_obs = np.array([sharpe_only(NET[i]) for i in range(len(keys))])
    wi = keys.index(WINNER)
    print(f"觀測掃描:{len(keys)} arm,最大夏普 {np.nanmax(sh_obs):.3f} "
          f"({' / '.join(keys[int(np.nanargmax(sh_obs))])})")
    print(f"          待檢定 arm {' / '.join(WINNER)} 夏普 {sh_obs[wi]:.3f} "
          f"(排名 {int(np.sum(sh_obs > sh_obs[wi])) + 1})")

    rng = np.random.default_rng(SEED + 2)
    valid_any = P.HAS_RET
    maxes = np.empty(reps)
    t0 = time.time()
    for r in range(reps):
        RP = P.RET.copy()
        for t in range(P.T):
            j = np.where(valid_any[t])[0]
            if len(j) > 1:
                RP[t, j] = P.RET[t, rng.permutation(j)]
        _, NP = full_scan(P, RP, verbose=False)
        s = np.array([sharpe_only(NP[i]) for i in range(NP.shape[0])])
        maxes[r] = np.nanmax(s)
        if r % 10 == 0:
            print(f"  {r}/{reps}  目前 max 分布中位 {np.median(maxes[:r+1]):.3f}  "
                  f"({time.time()-t0:.0f}s)", flush=True)

    p95 = float(np.percentile(maxes, 95))
    pctile = float(np.mean(maxes < sh_obs[wi]) * 100)
    ok_perm = sh_obs[wi] > p95

    # 解析式 Deflated Sharpe Ratio (Bailey & López de Prado 2014)
    from math import erf, log, sqrt
    N = int(np.isfinite(sh_obs).sum())
    var_sh = float(np.nanvar(sh_obs, ddof=1))
    gamma = 0.5772156649
    e = np.e
    z = sqrt(2 * log(N)) if N > 1 else 0.0
    exp_max = sqrt(var_sh) * ((1 - gamma) * (z if z else 1e-9) +
                              gamma * (sqrt(2 * log(N / e)) if N > e else 0.0))
    nobs = int(np.isfinite(NET[wi]).sum())
    rets = NET[wi][np.isfinite(NET[wi])] / 100.0
    sr_m = rets.mean() / rets.std(ddof=1)          # 月頻夏普(未年化,DSR 用)
    sk = float(pd.Series(rets).skew())
    ku = float(pd.Series(rets).kurtosis()) + 3.0
    sr0 = exp_max / np.sqrt(12)                     # 年化 → 月頻
    denom = sqrt(max(1 - sk * sr_m + (ku - 1) / 4 * sr_m ** 2, 1e-9))
    zstat = (sr_m - sr0) * sqrt(nobs - 1) / denom
    dsr = 0.5 * (1 + erf(zstat / sqrt(2)))
    ok_dsr = (1 - dsr) < 0.05

    print(f"\n置換掃描 max-夏普分布:p50 {np.percentile(maxes,50):.3f}  "
          f"p95 {p95:.3f}  p99 {np.percentile(maxes,99):.3f}  max {maxes.max():.3f}")
    print(f"觀測 arm 夏普 {sh_obs[wi]:.3f} → 百分位 {pctile:.1f}%   "
          f"門檻 >p95 ({p95:.3f}) → {'✅通過' if ok_perm else '❌否定'}")
    print(f"解析式 DSR:N={N} trials, Var(SR)={var_sh:.4f}, "
          f"E[max SR]年化≈{exp_max:.3f}, 偏態 {sk:+.2f}, 峰態 {ku:.2f}")
    print(f"           DSR = {dsr:.4f}  → p = {1-dsr:.4f}  "
          f"{'✅通過' if ok_dsr else '❌否定'} (門檻 p<0.05)")
    ok = ok_perm and ok_dsr
    print(f"\nH3c(兩項皆須通過) → {'✅通過' if ok else '❌否定'}")
    np.savez(OUTDIR / "high52_h3c.npz", maxes=maxes, sh_obs=sh_obs,
             keys=np.array([" / ".join(k) for k in keys]))
    return {"h3c": ok, "h3c_perm": ok_perm, "h3c_dsr": ok_dsr, "dsr_p": 1 - dsr,
            "obs_sharpe": float(sh_obs[wi]), "null_p95": p95, "pctile": pctile}


# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="all",
                    choices=["scan", "h1", "h2", "h3a", "h3c", "all"])
    ap.add_argument("--reps", type=int, default=0)
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"建面板… (報酬線 = {RET_COL})", flush=True)
    P = Panel()
    print(f"面板 {P.T} 月 × {P.S} 檔  ({time.time()-t0:.0f}s)")
    mb = met(P.bench)
    print(f"0050 含息買進持有 (同持有窗): CAGR {mb['cagr']:.2f}%  夏普 {mb['sharpe']:.2f}  "
          f"MDD {mb['mdd']:.1f}%  {mb['n']} 月")

    if a.part in ("scan", "all"):
        keys, NET = full_scan(P)
        sh = np.array([sharpe_only(NET[i]) for i in range(len(keys))])
        cg = np.array([met(NET[i]).get("cagr", np.nan) for i in range(len(keys))])
        df = pd.DataFrame([{"factor": k[0], "dir": k[1], "mode": k[2], "adv": k[3],
                            "sharpe": sh[i], "cagr": cg[i],
                            "months": int(np.isfinite(NET[i]).sum())}
                           for i, k in enumerate(keys)])
        df.to_csv(OUTDIR / "high52_scan_exec.csv", index=False, encoding="utf-8-sig")
        print(f"\n可執行線掃描 {len(df)} arm → {OUTDIR / 'high52_scan_exec.csv'}")
        print("\n夏普前 12 名:")
        print(df.nlargest(12, "sharpe").to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    if a.part in ("h1", "all"):
        run_h1(P)
    if a.part in ("h2", "all"):
        run_h2(P)
    if a.part in ("h3a", "all"):
        run_h3ab(P, a.reps or 2000)
    if a.part in ("h3c", "all"):
        run_h3c(P, a.reps or 200)
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
