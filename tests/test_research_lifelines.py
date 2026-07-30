# -*- coding: utf-8 -*-
"""test_research_lifelines.py — 研究生命線的迴歸測試(2026-07-30 靜態盤點第 7 點)

「生命線」= 一旦壞掉,回測數字仍然漂亮、但結論全錯的那幾件事。這裡只測四類:

  A. 主鍵唯一性     —— 面板 (as_of, stock_id) 重複 → 重複計權 / 灌高覆蓋率 / 矩陣後寫覆蓋
  B. 報酬線一致性   —— 全專案只准吃 exec_ret.fwd_x;obs_alpha.fwd 不得外流成報酬線
  C. 母體數量對帳   —— 真身面板 vs obs 母體的覆蓋率;缺一列就要有人喊
  D. 策略腿/基準腿同時鐘 —— 策略有月、0050 沒月 → CAGR 免費多算一段行情

需要 data/research_base/*.parquet;缺檔的環境自動 skip(CI 沒有研究基底也不該紅)。

    python -m pytest tests/test_research_lifelines.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJ = Path(__file__).resolve().parents[1]
for p in (PROJ, PROJ / "scripts", PROJ / "beat_0050", PROJ / "beat_0050" / "strategies"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import lab_paths                                     # noqa: E402
from lab_paths import PANEL_KEYS, assert_unique, assert_no_row_growth   # noqa: E402

REALBODY_PANELS = lab_paths.available_realbody_panels()
_HAVE_BASE = lab_paths.OBS_ALPHA.exists() and lab_paths.EXEC_RET.exists()
needs_base = pytest.mark.skipif(not _HAVE_BASE, reason="無研究基底 (obs_alpha / exec_ret)")


# ==============================================================================
# A. 主鍵唯一性
# ==============================================================================
def test_assert_unique_rejects_duplicate_keys():
    dup = pd.DataFrame({"as_of": ["2020-01-31", "2020-01-31"], "stock_id": ["2330", "2330"]})
    with pytest.raises(ValueError, match="不唯一"):
        assert_unique(dup, name="人造重複")


def test_assert_unique_reports_missing_key_column():
    with pytest.raises(KeyError):
        assert_unique(pd.DataFrame({"as_of": ["2020-01-31"]}), name="缺欄")


def test_assert_no_row_growth_rejects_merge_inflation():
    with pytest.raises(ValueError, match="膨脹"):
        assert_no_row_growth(100, 101, "人造膨脹")


@needs_base
@pytest.mark.parametrize("name", ["obs_alpha", "exec_ret"])
def test_base_panels_have_unique_keys(name):
    path = {"obs_alpha": lab_paths.OBS_ALPHA, "exec_ret": lab_paths.EXEC_RET}[name]
    df = pd.read_parquet(path, columns=PANEL_KEYS)
    df = df.astype(str)
    assert_unique(df, name=name)


@pytest.mark.skipif(not REALBODY_PANELS, reason="無真身面板")
@pytest.mark.parametrize("floor", sorted(REALBODY_PANELS))
def test_realbody_panels_have_unique_keys(floor):
    df = pd.read_parquet(REALBODY_PANELS[floor], columns=PANEL_KEYS).astype(str)
    assert_unique(df, name=f"realbody@{floor:,.0f}")


@needs_base
def test_panel_merge_does_not_grow_rows():
    """obs ⋈ exec_ret 必須是一對一 —— 列數不得增加。"""
    obs = pd.read_parquet(lab_paths.OBS_ALPHA, columns=PANEL_KEYS + ["listed_ok"])
    obs = obs[obs["listed_ok"] == True][PANEL_KEYS].astype(str)          # noqa: E712
    ex = pd.read_parquet(lab_paths.EXEC_RET, columns=PANEL_KEYS).astype(str)
    out = obs.merge(ex, on=PANEL_KEYS, how="left")
    assert_no_row_growth(len(obs), len(out), "obs ⋈ exec_ret")


# ==============================================================================
# B. 報酬線一致性
# ==============================================================================
@needs_base
def test_load_panel_never_exposes_obs_alpha_fwd():
    """load_panel 不得回傳 `fwd` 欄。那條線 close→close 不可執行、且固定 20 日窗會漏日,
    兩個偏誤方向相反、大小隨換手率變動 → 只能從源頭換線,不能事後修。
    刻意丟掉是為了讓漏改的 lab 直接 KeyError。"""
    df = lab_paths.load_panel(adv_floor=2e7)
    assert "fwd" not in df.columns
    assert lab_paths.RET_COL in df.columns
    assert df[lab_paths.RET_COL].notna().all()


@needs_base
def test_exec_ret_fwd_x_differs_from_close_to_close():
    """fwd_x(可執行,開盤對開盤、串接無漏日)與 fwd_cc(close→close 固定 20 日)
    必須是**不同**的兩條線。若哪天變成同一條,代表 build_exec_ret 退化了。"""
    ex = pd.read_parquet(lab_paths.EXEC_RET, columns=["fwd_x", "fwd_cc"]).dropna()
    assert len(ex) > 1000
    assert not np.allclose(ex["fwd_x"], ex["fwd_cc"])
    # 兩條線的全期平均差就是那個「無法事後修正」的淨誤差,量級應在 pp 級而非 0。
    assert abs(ex["fwd_x"].mean() - ex["fwd_cc"].mean()) > 1e-3


def test_return_column_constant_is_single_sourced():
    """RET_COL 只准有一個定義來源。三個模組各寫死字串就是下一次『兩條腿不同線』的伏筆。"""
    from honest_backtest import RET_COL as ENGINE_COL
    import high52_lab
    assert lab_paths.RET_COL == ENGINE_COL == high52_lab.RET_COL == "fwd_x"


# ==============================================================================
# C. 母體數量對帳
# ==============================================================================
@needs_base
@pytest.mark.skipif(not REALBODY_PANELS, reason="無真身面板")
@pytest.mark.parametrize("floor", sorted(REALBODY_PANELS))
def test_realbody_covers_its_declared_population(floor):
    """真身面板必須覆蓋『它宣稱的 ADV 門檻』母體 ≥99%。
    低於此代表 build 中途掉了 stock-month —— 數字會照樣算得出來,但母體已經被砍。"""
    obs = pd.read_parquet(lab_paths.OBS_ALPHA,
                          columns=PANEL_KEYS + ["adv20", "listed_ok"])
    obs = obs[(obs["listed_ok"] == True) & (obs["adv20"] >= floor)]       # noqa: E712
    obs[PANEL_KEYS] = obs[PANEL_KEYS].astype(str)
    ex = pd.read_parquet(lab_paths.EXEC_RET, columns=PANEL_KEYS + [lab_paths.RET_COL])
    ex[PANEL_KEYS] = ex[PANEL_KEYS].astype(str)
    pop = obs.merge(ex, on=PANEL_KEYS, how="left").dropna(subset=[lab_paths.RET_COL])
    rb = pd.read_parquet(REALBODY_PANELS[floor], columns=PANEL_KEYS + ["real_composite"])
    rb[PANEL_KEYS] = rb[PANEL_KEYS].astype(str)
    m = pop.merge(rb, on=PANEL_KEYS, how="left")
    cov = m["real_composite"].notna().mean()
    assert cov >= 0.99, f"ADV≥{floor:,.0f} 真身覆蓋率僅 {cov:.2%}(母體 {len(pop):,} 列)"


def test_resolve_realbody_refuses_higher_floor_panel(monkeypatch):
    """面板門檻 F > 需求 R 一律 raise —— 拿 2000萬 的面板跑 100萬 會靜默砍掉
    adv ∈ [100萬, 2000萬) 那一段,使『雙確認 @ADV≥100萬』偷偷變成『∩ 2000萬』。"""
    monkeypatch.setattr(lab_paths, "available_realbody_panels",
                        lambda: {2e7: lab_paths.REALBODY})
    with pytest.raises(FileNotFoundError, match="沒有能覆蓋"):
        lab_paths.resolve_realbody(1e6)
    assert lab_paths.resolve_realbody(2e7) == lab_paths.REALBODY


def test_missing_realbody_raises_at_use_not_silently_nan(monkeypatch):
    """真身面板缺檔:Panel 仍可建(scan / H1 / H3 不吃真身分數),但**取用 REAL_COMP 即 raise**。
    原本的 `except FileNotFoundError → 全 NaN` 會讓缺檔靜默通過建構子。"""
    import high52_lab
    monkeypatch.setattr(high52_lab, "resolve_realbody",
                        lambda f: (_ for _ in ()).throw(FileNotFoundError("測試:無面板")))
    P = object.__new__(high52_lab.Panel)          # 不跑 __init__(讀 300k 列太慢)
    P._real_comp = None
    P.realbody_err = "測試:無面板"
    with pytest.raises(FileNotFoundError, match="測試:無面板"):
        _ = P.REAL_COMP


# ==============================================================================
# D. 策略腿 / 基準腿同時鐘
# ==============================================================================
@needs_base
@pytest.mark.slow
def test_panel_strategy_and_benchmark_share_one_clock():
    """Panel 建完後,每一個月都必須同時有策略側報酬與 0050 基準。
    差一個月就足以讓 CAGR 虛高 ~0.5pp、夏普虛高 ~0.02(2026-07-30 實測)。"""
    from high52_lab import Panel, evaluate, winner_mask
    P = Panel(realbody_floor=2e7)
    assert np.isfinite(P.bench).all(), "Panel 月份中仍有無 0050 基準的月"
    assert P.RET.shape[0] == P.bench.shape[0] == P.T
    net = evaluate(winner_mask(P, "2000萬", 8), P.RET, P.SLIP)
    fs, fb = np.isfinite(net), np.isfinite(P.bench)
    assert int((fb & ~fs).sum()) == 0, "策略有空手月而基準有值 → met() 會跳過,兩腿不同時鐘"
    assert int((fs & ~fb).sum()) == 0


@needs_base
@pytest.mark.slow
def test_engine_strategy_and_benchmark_share_one_clock():
    """第二條路徑 (honest_backtest.Engine) 的同一條規則。"""
    from honest_backtest import Engine
    eng = Engine(adv_floor=2e7)
    assert set(eng.asofs) <= set(eng.bench), "self.asofs 有 0050 沒有基準的月份"
    m = eng.run(eng.universe_ew())["monthly"]
    assert m["bench"].notna().all(), "等權母體有月、0050 沒月 → ladder 的三階不同時鐘"


def test_met_vs_excludes_strategy_gap_months_from_both_legs():
    """met_vs 的硬性同時鐘保證(Codex 審查點 1):策略空手月(NaN)必須同時從
    策略腿與基準腿排除,不能只丟策略腿的 NaN 而讓基準多算那個月。
    這覆蓋 walk-forward 動態路徑,不只固定 winner。"""
    from high52_lab import met_vs
    n = 60
    strat = np.concatenate([np.full(6, np.nan), np.full(n - 6, 1.0)])   # 前 6 月空手
    bench = np.full(n, 0.5)                                             # 基準月月有值
    ms, mb, excluded = met_vs(strat, bench)
    assert excluded == 6, "空手月未被計入排除數"
    assert ms["n"] == mb["n"] == n - 6, "兩腿必須落在同一組共同月份上"


def test_met_vs_no_gap_is_identity():
    """無空手月時,met_vs 不改變任何一腿的月數(對固定 winner 策略零影響)。"""
    from high52_lab import met_vs
    strat = np.linspace(-2, 3, 40)
    bench = np.linspace(-1, 2, 40)
    ms, mb, excluded = met_vs(strat, bench)
    assert excluded == 0 and ms["n"] == mb["n"] == 40


def test_research_coverage_gates_default_to_100pct():
    """所有會產出研究結論的入口,覆蓋率門檻預設必須是 1.0(Codex 第三輪第 1 點:零靜默損失)。
    99% 只能是顯式探索。這裡用簽名內省鎖住預設,防有人把它調回 0.99。"""
    import inspect
    import lab_paths as LP
    import high52_lab as H
    import dual100_lab as D
    assert inspect.signature(LP.load_real_panel).parameters["min_coverage"].default == 1.0
    assert inspect.signature(H.dual_confirm_mask).parameters["min_cov"].default == 1.0
    assert D.COV_MIN == 1.0


def test_dual_confirm_mask_raises_below_full_coverage():
    """真身覆蓋率差一格(99.x%)就必須 raise —— 不得靜默把『雙確認 @tier』退化成『∩ 面板門檻』。"""
    import high52_lab as H

    class _FakeP:
        S = 100
        realbody_path = "fake"
        realbody_floor = 1e6
    fp = _FakeP()
    valid = np.zeros((3, 100), dtype=bool)
    valid[:, :50] = True                     # 每月 50 檔有效
    fp.tier_valid = {"100萬": valid}
    rc = np.where(valid, 1.0, np.nan)
    rc[0, 0] = np.nan                        # 有效母體裡挖一格 NaN → cov = 149/150 < 1.0
    fp._real_comp = rc
    fp.REAL_COMP = rc
    with pytest.raises(ValueError, match="覆蓋率"):
        H.dual_confirm_mask(fp, "100萬", top_pct=20, source="real")


def test_partial_build_cannot_target_canonical_name():
    """--year/--limit 局部跑即使明寫正規檔名也不得覆蓋完整面板(Codex 審查點 2)。"""
    from beat_0050.realbody.build_realbody_scores import _is_canonical_name
    from pathlib import Path as _P
    assert _is_canonical_name(_P("realbody_scores.parquet"))
    assert _is_canonical_name(_P("realbody_scores_adv100w.parquet"))
    assert _is_canonical_name(_P("/x/realbody_scores_adv2000w.parquet"))
    assert not _is_canonical_name(_P("realbody_scores_partial.parquet"))
    assert not _is_canonical_name(_P("rb_probe.parquet"))
    assert not _is_canonical_name(_P("realbody_scores_adv100w_partial.parquet"))
    # 非完美建置的隔離檔名(Codex 第四輪第 2 點)也必須是非正規的:
    assert not _is_canonical_name(_P("realbody_scores.INCOMPLETE.parquet"))
    assert not _is_canonical_name(_P("realbody_scores.EXPLORE.parquet"))
    assert not _is_canonical_name(_P("realbody_scores_adv100w.EXPLORE.parquet"))
    assert not _is_canonical_name(_P("realbody_scores_adv100w.INCOMPLETE.parquet"))


def test_build_input_population_uniqueness_guard():
    """建置入口在算 expected 前必須擋掉輸入母體的重複鍵(Codex 第五輪)。
    否則 sorted(set(as_of)) 靜默去重 → expected 低估 → 覆蓋率假性 100%。"""
    from beat_0050.realbody.build_realbody_scores import assert_obs_unique
    ok = pd.DataFrame({"stock_id": ["2330", "2330", "2454"],
                       "as_of": ["2020-01-31", "2020-02-29", "2020-01-31"]})
    assert_obs_unique(ok)                              # 無重複 → 不 raise
    dup = pd.DataFrame({"stock_id": ["2330", "2330"],
                        "as_of": ["2020-01-31", "2020-01-31"]})
    with pytest.raises(SystemExit, match="重複鍵"):
        assert_obs_unique(dup)


@needs_base
@pytest.mark.slow
def test_two_paths_agree_on_benchmark():
    """矩陣路徑與 Engine 路徑必須算出**同一條** 0050 序列。
    兩邊各自實作基準腿,是『對照組時位不一致』最容易復發的地方。"""
    from high52_lab import Panel
    from honest_backtest import Engine
    P = Panel(realbody_floor=2e7)
    eng = Engine(adv_floor=2e7)
    a = pd.Series({P.month_s[t]: P.bench[t] for t in range(P.T)}).dropna()
    b = pd.Series(eng.bench).dropna()
    common = a.index.intersection(b.index)
    assert len(common) > 200
    assert (a[common] - b[common]).abs().max() < 1e-6


@needs_base
@pytest.mark.slow
def test_both_paths_use_adj_open_when_present_and_match_independent_formula(monkeypatch):
    """Codex 審查點 4:證明 open/close 選擇是被測到的,不只是現有 close fallback 資料的比較。

    造一份含 adj_open(≠ adj_close)的合成 0050_tr,把兩路徑的 BENCH_TR 指過去,驗證:
      (1) Panel 與 Engine **都**改用 adj_open(而非 adj_close);
      (2) 兩路徑序列一致;
      (3) 序列等於一條**獨立**重算的基準(直接用 pandas 取『as_of 後的下一個交易日』開盤價,
          不經過被測程式碼)—— 避免『兩路徑一起錯』。

    暫存檔**不用 pytest tmp_path**(Codex 第三輪第 3 點:共享 worktree 下 basetemp 可能不可寫)。
    改寫到 lab 本來就在寫的 OUTDIR(beat_0050/results),用唯一名稱、finally 清掉。
    """
    import high52_lab as H
    import honest_backtest as HB
    import os

    real = pd.read_parquet(H.BENCH_TR)[["date", "adj_close"]].copy()
    # adj_open 故意與 adj_close 不同(否則測不出「有沒有真的改用 open」)。
    real["adj_open"] = real["adj_close"] * 0.987 + 0.13
    H.OUTDIR.mkdir(parents=True, exist_ok=True)
    fake = H.OUTDIR / f"_test_0050_tr_open_{os.getpid()}.parquet"
    real[["date", "adj_open", "adj_close"]].to_parquet(fake, index=False)
    monkeypatch.setattr(H, "BENCH_TR", fake)
    monkeypatch.setattr(HB, "BENCH_TR", fake)

    try:
        P = H.Panel(realbody_floor=2e7)
        eng = HB.Engine(adv_floor=2e7)
        assert P.bench_px_col == "adj_open", "Panel 未在 adj_open 存在時改用開盤錨"
        assert eng.bench_px_col == "adj_open", "Engine 未在 adj_open 存在時改用開盤錨"

        # (3) 獨立重算:對每個 month_s,取『嚴格大於 as_of 的第一個交易日』開盤價,串接算報酬。
        d = real.sort_values("date")
        dates = d["date"].astype(str).to_numpy()
        op = d["adj_open"].to_numpy(float)

        def nextday_open(asof):
            i = int(np.searchsorted(dates, asof, side="right"))
            return op[i] if i < len(op) else np.nan

        indep = {}
        for t in range(P.T - 1):
            p0, p1 = nextday_open(P.month_s[t]), nextday_open(P.month_s[t + 1])
            if np.isfinite(p0) and np.isfinite(p1) and p0 > 0:
                indep[P.month_s[t]] = (p1 / p0 - 1) * 100

        both = pd.Series({P.month_s[t]: P.bench[t] for t in range(P.T)}).dropna()
        common = both.index.intersection(pd.Index(list(indep)))
        assert len(common) > 200
        diff = (both[common] - pd.Series(indep)[common]).abs().max()
        assert diff < 1e-6, f"Panel 基準與獨立重算的開盤錨對不上,最大差 {diff}"
        # 同一條也要等於 Engine 的
        eb = pd.Series(eng.bench).dropna()
        c2 = both.index.intersection(eb.index)
        assert (both[c2] - eb[c2]).abs().max() < 1e-6
    finally:
        if fake.exists():
            fake.unlink()
