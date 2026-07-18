"""basket_dispersion_lab.py — 籃內離散度與持股規則實驗 (風險結構研究,非 alpha 研究)
================================================================================
預註冊規格:docs/預註冊_BasketDispersionLab.md (2026-07-18 凍結,單發射擊制)。
回答三個問題:
  Q1 從 C2 top-30 籃隨機挑 K 檔等權持有一季,相對整籃的離散度多大?
  Q2 產業上限 / 籃內低波排除能在不犧牲期望報酬下壓低多少離散度?
  Q3 K 從 5→20 的邊際分散效益曲線,合理最小持股數在哪?
資料 = obs_alpha.parquet (alpha_gate_lab --build 產物) join 60 日前瞻報酬
(obs_dump_h60.parquet,tej_universe_screen_validation --holding 60 重生)。
0 API、純本機。scratch 實驗室,不動任何正式模組。

用法:
  python scripts/basket_dispersion_lab.py --run          # 主分析 (六時代+全期+閘門判定)
  python scripts/basket_dispersion_lab.py --sensitivity  # S1 生產忠實籃 / S2 月度重疊 / S3 2026YTD
================================================================================
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpha_gate_lab as agl  # noqa: E402  (只用 build_candidate 做 C2 複算一致性檢查)

import lab_paths  # noqa: E402  2026-07-19 遷出 Temp scratchpad (工單 WP4)

OBS_ALPHA = lab_paths.OBS_ALPHA
OBS_H60 = lab_paths.OBS_H60
STATS_OUT = lab_paths.BASKET_DISPERSION_STATS

# ---- 預註冊凍結參數 (§3/§4/§6) ------------------------------------------------
SEED = 20260718
N_DRAWS = 1000
BASKET_N = 30
K_GRID = [5, 8, 10, 12, 15, 20]
K_ANCHOR = 8
IND_CAP, IND_CAP_RELAX = 2, 3
VOL_DROP_N = BASKET_N // 3          # 30 檔剔除 vol60 最高 10 檔
RULES = ["R0", "R1", "R2", "R3"]
N_BOOT = 2000
BOOT_P = 0.25                        # stationary bootstrap 平均 block 長度 4 期
GATE_D_RED = 0.10                    # 條1:全期 D 降幅 ≥10%
GATE_ERA_CONSIST = 5                 # 條1:六時代 ≥5 個方向一致
GATE_M_POINT = -0.20                 # 條2:ΔM 點估 > −0.20%/季
GATE_M_CI = -0.40                    # 條2:95% CI 下界 > −0.40%/季
GATE_BEAR = -0.20                    # 條3:2022 段 ΔM ≥ −0.20%/季
C2_POS = ["value_ind", "revenue_yoy", "high52_prox"]
C2_NEG = ["momentum"]

ERAS = [
    ("2005-2009(海嘯)", "2005-01-01", "2009-12-31"),
    ("2010-2014",       "2010-01-01", "2014-12-31"),
    ("2015-2018",       "2015-01-01", "2018-12-31"),
    ("2019-2021",       "2019-01-01", "2021-12-31"),
    ("2022空頭",        "2022-01-01", "2022-12-31"),
    ("2023-2025",       "2023-01-01", "2025-12-31"),
]
FULL = ("全期2005-2025", "2005-01-01", "2025-12-31")
YTD26 = ("2026YTD健檢", "2026-01-01", "2026-12-31")


# ------------------------------------------------------------------------------
# 資料載入與前置一致性檢查 (§9)
# ------------------------------------------------------------------------------
def load_obs():
    obs = pd.read_parquet(OBS_ALPHA)
    obs = obs[(obs["adv20"] >= agl.ADV_FLOOR) & obs["listed_ok"].fillna(False)].copy()

    h60 = pd.read_parquet(OBS_H60)[["stock_id", "as_of", "fwd"]].rename(columns={"fwd": "fwd60"})
    h60_dates = set(h60["as_of"].unique())
    obs = obs.merge(h60, on=["stock_id", "as_of"], how="left")

    # C2:當期 L1 池內百分位,同 alpha_gate_lab build_candidate
    parts = [obs.groupby("as_of")[f].rank(pct=True) * 100 for f in C2_POS]
    parts += [100 - obs.groupby("as_of")[f].rank(pct=True) * 100 for f in C2_NEG]
    obs["c2"] = pd.concat(parts, axis=1).mean(axis=1, skipna=True)

    # --- 檢查(a):與 alpha_gate_lab 版 C2 複算一致 (相關=1.0) ---
    agl.build_candidate(obs, C2_POS, C2_NEG, "_c2_ref")
    m = obs["c2"].notna() & obs["_c2_ref"].notna()
    corr = obs.loc[m, "c2"].corr(obs.loc[m, "_c2_ref"])
    diff = (obs.loc[m, "c2"] - obs.loc[m, "_c2_ref"]).abs().max()
    assert corr > 0.999999 and diff < 1e-9, f"C2 複算不一致:corr={corr}, maxdiff={diff}"
    obs = obs.drop(columns=["_c2_ref"])

    # --- 檢查(b):h60 涵蓋 as_of 內 join 率 ≥99% ---
    in_range = obs[obs["as_of"].isin(h60_dates)]
    join_rate = in_range["fwd60"].notna().mean()
    assert join_rate >= 0.99, f"h60 join 率 {join_rate:.4f} < 0.99"
    print(f"前置檢查通過:C2 複算 corr={corr:.8f} maxdiff={diff:.2e};h60 join 率 {join_rate:.4f}")
    return obs


def usable_dates(obs, min_fwd=300):
    """fwd60 有效檔數 ≥min_fwd 的 as_of (尾端無未來資料的期自然消失)。"""
    cnt = obs.groupby("as_of")["fwd60"].count()
    return sorted(cnt[cnt >= min_fwd].index)


def quarterly_grid(dates):
    """每 3 期取 1 的月度 as_of (≈季度,fwd60 不重疊),起點=第一期。"""
    return dates[::3]


# ------------------------------------------------------------------------------
# 籃子建構 (§3)
# ------------------------------------------------------------------------------
def basket_at(g):
    """單期觀測 → (籃子df, 因缺fwd被排除的真top30檔數)。tie-break 以 stock_id 固定。"""
    ranked = g.sort_values(["c2", "stock_id"], ascending=[False, True])
    true_top = ranked.head(BASKET_N)
    excluded = int(true_top["fwd60"].isna().sum())
    basket = ranked[ranked["fwd60"].notna()].head(BASKET_N)
    return basket, excluded


def basket_arrays(basket):
    """fwd / 產業碼 (缺產業=各自獨立組) / 低波合格索引。"""
    fwd = basket["fwd60"].to_numpy(dtype=float)
    codes = pd.factorize(basket["tej_ind_name"])[0]
    codes = np.where(codes < 0, -(np.arange(len(codes)) + 2), codes)  # NaN → 唯一負碼
    vol = basket["vol60"].to_numpy(dtype=float)
    vol = np.where(np.isnan(vol), np.inf, vol)                        # vol60 缺值視同高波動
    keep = np.argsort(vol, kind="stable")[: len(basket) - VOL_DROP_N]
    ind_known = float(basket["tej_ind_name"].notna().mean())
    return fwd, codes, np.sort(keep), ind_known


# ------------------------------------------------------------------------------
# 抽樣規則 (§3,凍結)
# ------------------------------------------------------------------------------
def uniform_draws(rng, n_pool, k, n_draws):
    """無放回均勻抽樣 n_draws 組 (向量化)。"""
    return np.argsort(rng.random((n_draws, n_pool)), axis=1)[:, :k]


def capped_pick(rng, groups, k):
    """隨機順序逐一抽,同組達 cap 跳過;抽不滿依 2→3→無上限放寬。"""
    n = len(groups)
    order = rng.permutation(n)
    picked = np.zeros(n, dtype=bool)
    count: dict = {}
    total = 0
    for cap in (IND_CAP, IND_CAP_RELAX, n + 1):
        for i in order:
            if total >= k:
                break
            if picked[i] or count.get(groups[i], 0) >= cap:
                continue
            picked[i] = True
            count[groups[i]] = count.get(groups[i], 0) + 1
            total += 1
        if total >= k:
            break
    return np.flatnonzero(picked)


def rule_draws(rule, rng, fwd, codes, keep, k):
    """回傳 n_draws × k 的索引矩陣 (相對籃內位置)。"""
    n = len(fwd)
    if rule == "R0":
        return uniform_draws(rng, n, k, N_DRAWS)
    if rule == "R2":
        kk = min(k, len(keep))
        return keep[uniform_draws(rng, len(keep), kk, N_DRAWS)]
    if rule == "R1":
        return np.stack([capped_pick(rng, codes, k) for _ in range(N_DRAWS)])
    if rule == "R3":
        sub_codes = codes[keep]
        kk = min(k, len(keep))
        return np.stack([keep[capped_pick(rng, sub_codes, kk)] for _ in range(N_DRAWS)])
    raise ValueError(rule)


# ------------------------------------------------------------------------------
# 逐期模擬 → per-period 統計
# ------------------------------------------------------------------------------
def simulate(obs, grid, k_grid=K_GRID, rules=RULES, tag="main"):
    rows = []
    by_date = dict(tuple(obs[obs["as_of"].isin(grid)].groupby("as_of")))
    for t_idx, t in enumerate(grid):
        g = by_date.get(t)
        if g is None:
            continue
        basket, excluded = basket_at(g)
        if len(basket) < BASKET_N:
            print(f"  [警告] {t} 籃子僅 {len(basket)} 檔,跳過")
            continue
        assert basket["stock_id"].is_unique and basket["fwd60"].notna().all()  # 檢查(c)
        fwd, codes, keep, ind_known = basket_arrays(basket)
        rb = fwd.mean()
        for k in k_grid:
            for rule_idx, rule in enumerate(rules):
                rng = np.random.default_rng([SEED, t_idx, k, rule_idx])
                idx = rule_draws(rule, rng, fwd, codes, keep, k)
                r = fwd[idx].mean(axis=1) - rb
                rows.append({"tag": tag, "as_of": t, "K": k, "rule": rule,
                             "D": float(r.std(ddof=1)), "M": float(r.mean()),
                             "P2": float((r < -2.0).mean()), "P5": float((r < -5.0).mean()),
                             "RB": float(rb), "excluded": excluded, "ind_known": ind_known})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------
# 推論:stationary bootstrap (§4)
# ------------------------------------------------------------------------------
def stationary_boot_idx(rng, n):
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    for i in range(1, n):
        idx[i] = rng.integers(n) if rng.random() < BOOT_P else (idx[i - 1] + 1) % n
    return idx


def boot_rule_vs_r0(stats, rule, k=K_ANCHOR, era=FULL):
    """全期 D 降幅與 ΔM 的點估+95% CI (對期重抽)。"""
    _, s, e = era
    base = stats[(stats["K"] == k) & (stats["as_of"] >= s) & (stats["as_of"] <= e)]
    piv_d = base.pivot_table(index="as_of", columns="rule", values="D")
    piv_m = base.pivot_table(index="as_of", columns="rule", values="M")
    d0, dx = piv_d["R0"].to_numpy(), piv_d[rule].to_numpy()
    m0, mx = piv_m["R0"].to_numpy(), piv_m[rule].to_numpy()
    n = len(d0)
    dred_pt = 1.0 - dx.mean() / d0.mean()
    dm_pt = mx.mean() - m0.mean()
    rng = np.random.default_rng([SEED, 999])
    dreds, dms = np.empty(N_BOOT), np.empty(N_BOOT)
    for b in range(N_BOOT):
        i = stationary_boot_idx(rng, n)
        dreds[b] = 1.0 - dx[i].mean() / d0[i].mean()
        dms[b] = mx[i].mean() - m0[i].mean()
    return (dred_pt, np.percentile(dreds, [2.5, 97.5]),
            dm_pt, np.percentile(dms, [2.5, 97.5]), n)


# ------------------------------------------------------------------------------
# 報表
# ------------------------------------------------------------------------------
def era_table(stats, k, metric, eras):
    out = {}
    for name, s, e in eras:
        d = stats[(stats["K"] == k) & (stats["as_of"] >= s) & (stats["as_of"] <= e)]
        if d.empty:
            continue
        out[name] = d.groupby("rule")[metric].mean()
    return pd.DataFrame(out).T


def run_main(obs):
    grid = quarterly_grid(usable_dates(obs))
    print(f"\n季度網格:{len(grid)} 期 ({grid[0]} ~ {grid[-1]})")
    stats = simulate(obs, grid)
    stats.to_parquet(STATS_OUT, index=False)
    gate_stats = stats[(stats["as_of"] >= FULL[1]) & (stats["as_of"] <= FULL[2])]

    # 透明度:缺 fwd 排除 / 產業覆蓋
    per = stats[(stats["K"] == K_ANCHOR) & (stats["rule"] == "R0")]
    print(f"真top30因缺fwd60被替補:平均 {per['excluded'].mean():.2f} 檔/期 "
          f"(最大 {per['excluded'].max()});籃內產業覆蓋率平均 {per['ind_known'].mean():.1%}")
    for name, s, e in ERAS:
        d = per[(per["as_of"] >= s) & (per["as_of"] <= e)]
        if len(d) and d["ind_known"].mean() < 0.80:
            print(f"  [低信度] {name} 產業覆蓋 {d['ind_known'].mean():.1%} <80%,產業規則結果標記低信度")

    # H1 + K 曲線 (Q1/Q3)
    print("\n" + "=" * 78)
    print(f"Q1/Q3 — R0 均勻隨機:單季離散度 D (%) by K (全期 {FULL[0]})")
    print("=" * 78)
    d0 = gate_stats[gate_stats["rule"] == "R0"].groupby("K")["D"].mean()
    print("  " + "  ".join(f"K={k}:{d0[k]:.2f}" for k in K_GRID))
    print(f"  H1 檢核:K={K_ANCHOR} D={d0[K_ANCHOR]:.2f}%(預測 4~7%)")
    rec = None
    for a, b in zip(K_GRID, K_GRID[1:]):
        imp = 1 - d0[b] / d0[a]
        mark = ""
        if rec is None and imp < 0.10:
            rec, mark = a, "  ← 邊際降幅 <10%,K 建議值"
        print(f"  K {a}→{b}:D 相對降幅 {imp:+.1%}{mark}")

    # 六時代 × 規則 全指標
    for metric, label in [("D", "離散度 D%"), ("M", "期望代價 M%"),
                          ("P2", "P(落後>2%)"), ("P5", "P(落後>5%)")]:
        print(f"\n--- {label} @K={K_ANCHOR} ---")
        print(era_table(stats, K_ANCHOR, metric, ERAS + [FULL, YTD26])
              .to_string(float_format=lambda x: f"{x:.3f}"))

    # Q2 — 閘門判定 (§6)
    print("\n" + "=" * 78)
    print(f"Q2 — 採用判準 @K={K_ANCHOR} (規則 vs R0,全期 bootstrap {N_BOOT} 次)")
    print("=" * 78)
    era_d = era_table(gate_stats, K_ANCHOR, "D", ERAS)
    bear_m = era_table(stats, K_ANCHOR, "M", [ERAS[4]])
    verdicts = {}
    for rule in ["R1", "R2", "R3"]:
        dred, dred_ci, dm, dm_ci, n = boot_rule_vs_r0(gate_stats, rule)
        consist = int((era_d["R0"] > era_d[rule]).sum())
        dbear = bear_m[rule].iloc[0] - bear_m["R0"].iloc[0]
        g1 = dred >= GATE_D_RED and consist >= GATE_ERA_CONSIST
        g2 = dm > GATE_M_POINT and dm_ci[0] > GATE_M_CI
        g3 = dbear >= GATE_BEAR
        verdicts[rule] = (g1, g2, g3)
        print(f"\n{rule}(n={n}期): D降幅 {dred:+.1%} CI[{dred_ci[0]:+.1%},{dred_ci[1]:+.1%}]"
              f" 時代一致 {consist}/6 → 條1 {'✓' if g1 else '✗'}")
        print(f"        ΔM {dm:+.3f}%/季 CI[{dm_ci[0]:+.3f},{dm_ci[1]:+.3f}]"
              f" → 條2 {'✓' if g2 else '✗'};2022 ΔM {dbear:+.3f} → 條3 {'✓' if g3 else '✗'}")
        print(f"        判定:{'採用' if all((g1, g2, g3)) else '不採用'}")
    if all(verdicts["R3"]) and not (all(verdicts["R1"]) or all(verdicts["R2"])):
        print("\n[判讀] R3 通過但 R1/R2 皆未單獨通過 → 依 §6 視為偶然交互作用,不採用 R3。")
    print(f"\nper-period 統計已存 {STATS_OUT}")


# ------------------------------------------------------------------------------
# 敏感度 (§7,不計判準)
# ------------------------------------------------------------------------------
def add_union_flag(obs):
    """生產 shortlist 圈人:5F 各 L1 內前 15% 聯集。"""
    pcts = pd.concat([obs.groupby("as_of")[f].rank(pct=True) * 100
                      for f in agl.BASELINE_5F], axis=1)
    obs["_union"] = (pcts >= 85).any(axis=1)
    return obs


def run_sensitivity(obs):
    dates = usable_dates(obs)
    grid = quarterly_grid(dates)

    # S1 生產忠實籃 (2019-2025,聯集圈人 → C2 排序 top-30)
    print("\n" + "=" * 78)
    print("S1 — 生產忠實籃 (5F聯集圈人→C2排序) vs 主分析純C2籃,2019-2025 @K=8")
    print("=" * 78)
    obs = add_union_flag(obs)
    sub = obs[(obs["as_of"] >= "2019-01-01") & (obs["as_of"] <= "2025-12-31") & obs["_union"]]
    g19 = [t for t in grid if "2019-01-01" <= t <= "2025-12-31"]
    s1 = simulate(sub, g19, k_grid=[K_ANCHOR], tag="S1")
    main19 = simulate(obs[(obs["as_of"] >= "2019-01-01") & (obs["as_of"] <= "2025-12-31")],
                      g19, k_grid=[K_ANCHOR], tag="main19")
    for name, df in [("生產忠實籃", s1), ("純C2籃(對照)", main19)]:
        t = df.groupby("rule")[["D", "M"]].mean()
        d0 = t.loc["R0", "D"]
        print(f"\n{name}:")
        for rule in RULES:
            print(f"  {rule}: D={t.loc[rule, 'D']:.2f}%"
                  f" (降幅 {1 - t.loc[rule, 'D'] / d0:+.1%})  M={t.loc[rule, 'M']:+.3f}%")

    # S2 月度重疊網格 (方向一致性 only)
    print("\n" + "=" * 78)
    print("S2 — 月度重疊網格 (全期,方向一致性 only) @K=8")
    print("=" * 78)
    s2 = simulate(obs, [t for t in dates if t <= FULL[2]], k_grid=[K_ANCHOR], tag="S2")
    t = s2.groupby("rule")["D"].mean()
    for rule in ["R1", "R2", "R3"]:
        print(f"  {rule}: D降幅 {1 - t[rule] / t['R0']:+.1%} (季度主分析方向{'一致' if t[rule] < t['R0'] else '不一致'})")

    # S3 2026 YTD 健檢
    print("\n" + "=" * 78)
    print("S3 — 2026 YTD 健檢 @K=8 (樣本不足,不評判準)")
    print("=" * 78)
    g26 = [t for t in grid if t >= "2026-01-01"]
    if not g26:
        print("  無可用期 (fwd60 需 60 交易日未來資料)")
    else:
        s3 = simulate(obs, g26, k_grid=[K_ANCHOR], tag="S3")
        print(f"  期數 {s3['as_of'].nunique()}")
        print(s3.groupby("rule")[["D", "M", "P2", "P5"]].mean()
              .to_string(float_format=lambda x: f"{x:.3f}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--sensitivity", action="store_true")
    args = ap.parse_args()
    if not (args.run or args.sensitivity):
        ap.print_help()
        return
    obs = load_obs()
    if args.run:
        run_main(obs)
    if args.sensitivity:
        run_sensitivity(obs)


if __name__ == "__main__":
    main()
