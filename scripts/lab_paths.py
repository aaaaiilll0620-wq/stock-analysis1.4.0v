# =====================================================================
#  lab_paths — 研究實驗室共用路徑常數 (工單_活體演練保護 WP4-2)
#
#  2026-07-19 起研究資料基底不再住 session 專屬 Temp scratchpad
#  (系統清理即滅失,且 obs_alpha 是四份預註冊文件共用的單一資料基底),
#  改住專案內 data/research_base/ (已在 .gitignore,不進 git;OneDrive 同步
#  順帶多一份雲端副本)。三支實驗室 (alpha_gate_lab / portfolio_simulator_lab /
#  basket_dispersion_lab) 一律引用本模組,不得再硬編碼 Temp 路徑。
#
#  2026-07-29 (L3):新增 load_real_panel() —— lab 的「綜合分」改吃生產真身分數
#  (realbody_scores.parquet),不再用 obs_alpha 原始因子重建替身。理由見該函式 docstring
#  與 docs/現況盤點_2026-07-29.md §L3。
#
#  2026-07-30:真身面板改為**分層多份**(2000萬 / 100萬 …)。原本 adv_floor<2000萬 一律
#  raise 的硬閘門,換成 resolve_realbody() —— 規則不變、只是從「單一門檻」放寬成
#  「面板門檻 F ≤ 需求門檻 R 才可用」。F>R 仍然 raise,不提供靜默縮池的路徑。
#  用途:驗證「雙確認 @ADV≥100萬」(docs/預註冊_雙確認ADV100萬.md)。
#
#  重生指令 (缺檔時):
#    python scripts/tej_universe_screen_validation.py --dump-obs \
#        --dump-start 2005-01-01 --dump-end 2026-12-31      # → obs_dump_full
#        (60 日視野加 --holding 60 → obs_dump_h60;預設區間只到 2019,務必帶起訖)
#    python scripts/alpha_gate_lab.py --build                # → obs_alpha
# =====================================================================
from pathlib import Path

RESEARCH_BASE = Path(__file__).resolve().parent.parent / "data" / "research_base"

# 面板主鍵。任何 (as_of, stock_id) 面板在 merge 前都要過 assert_unique() ——
# 見該函式 docstring。
PANEL_KEYS = ["as_of", "stock_id"]

# ---- 資料基底 (讀) ----------------------------------------------------
OBS_DUMP_FULL = RESEARCH_BASE / "obs_dump_full.parquet"   # 20d 前瞻原始 dump (2005-2026)
OBS_ALPHA = RESEARCH_BASE / "obs_alpha.parquet"           # alpha_gate_lab --build 產物
OBS_H60 = RESEARCH_BASE / "obs_dump_h60.parquet"          # 60d 前瞻 dump (籃內離散度用)
EXEC_RET = RESEARCH_BASE / "exec_ret.parquet"             # 可執行報酬線 (scripts/build_exec_ret.py)
REALBODY = RESEARCH_BASE / "realbody_scores.parquet"      # 真身五面分數 (beat_0050.realbody.build_realbody_scores)

RET_COL = "fwd_x"        # 20 交易日視野的可執行報酬欄
RET_COL_60 = "fwd_x60"   # 60 交易日視野

# ---- 真身分數 (生產 core/scoring_manager 算出來的那一份) --------------
REALBODY_ADV_FLOOR = 2e7   # realbody_scores.parquet(預設檔)的建置門檻
REAL_COMP_COL = "real_composite"
REAL_FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
C2_LEGS = ["value_ind", "revenue_yoy", "high52_prox", "momentum"]


def realbody_path_for(adv_floor: float) -> Path:
    """該 ADV 門檻**應該**住在哪個檔 —— 與 `build_realbody_scores.out_path_for()` 同一套命名。
    兩邊必須一致,否則 build 寫到 A、lab 讀 B,會靜默讀到過期或不存在的面板。"""
    if abs(adv_floor - REALBODY_ADV_FLOOR) < 1:
        return REALBODY
    return RESEARCH_BASE / f"realbody_scores_adv{int(adv_floor / 1e4)}w.parquet"


def available_realbody_panels() -> dict:
    """{建置門檻: 路徑} —— 掃 research_base 下實際存在的真身面板。"""
    out = {}
    if REALBODY.exists():
        out[REALBODY_ADV_FLOOR] = REALBODY
    for p in sorted(RESEARCH_BASE.glob("realbody_scores_adv*w.parquet")):
        try:
            floor = float(p.stem.split("adv")[-1].rstrip("w")) * 1e4
        except ValueError:
            continue
        out[floor] = p
    return out


def resolve_realbody(adv_floor: float) -> Path:
    """要跑 ADV≥`adv_floor` 的真身研究,該讀哪個面板。

    **可用性規則:面板門檻 F 覆蓋得了需求 R,若且唯若 F ≤ R。**
    F ≤ R 時該面板是需求母體的超集,inner join 後一列不少(覆蓋率檢查會複驗)。
    F > R 則會**靜默砍掉** adv ∈ [R, F) 的那一段 —— 這正是「雙確認 @ADV≥100萬」
    偷偷退化成「@ADV≥2000萬 ∩ 100萬層」的機制,不提供這條路徑。
    多個可用面板時取**最大的 F**(仍完整,但檔案最小)。
    """
    panels = available_realbody_panels()
    usable = {f: p for f, p in panels.items() if f <= adv_floor + 1}
    if not usable:
        have = ", ".join(f"ADV≥{f:,.0f}" for f in sorted(panels)) or "(一份都沒有)"
        raise FileNotFoundError(
            f"沒有能覆蓋 ADV≥{adv_floor:,.0f} 的真身面板。現有:{have}。\n"
            f"更高門檻的面板不能用來跑更低門檻 —— 那會靜默砍掉母體的一段,\n"
            f"讓「@ADV≥{adv_floor/1e4:.0f}萬」偷偷變成「∩ 既有門檻」卻沒有任何警告。\n"
            f"請先重建:\n"
            f"  python -m beat_0050.realbody.build_realbody_scores --adv-floor {adv_floor:.0f}\n"
            f"  (→ {realbody_path_for(adv_floor).name};全循環數小時)")
    return usable[max(usable)]

# ---- 實驗輸出 (寫;歷史結案件已自 Temp 遷入) ---------------------------
PORTFOLIO_SIM_STATS = RESEARCH_BASE / "portfolio_sim_stats.parquet"
BASKET_DISPERSION_STATS = RESEARCH_BASE / "basket_dispersion_stats.parquet"

_CORE = {"obs_dump_full": OBS_DUMP_FULL, "obs_alpha": OBS_ALPHA, "obs_h60": OBS_H60}


def check_base(verbose: bool = True) -> list:
    """回傳缺少的核心基底檔清單;預設順帶印 friendly 提示 (不 raise —
    alpha_gate_lab --build 本來就要在 obs_alpha 缺檔時能跑)。"""
    missing = [k for k, p in _CORE.items() if not p.exists()]
    if missing and verbose:
        print(f"[lab_paths] 研究基底缺檔: {', '.join(missing)} (於 {RESEARCH_BASE})")
        print("[lab_paths] 重生指令見 scripts/lab_paths.py 檔頭註解")
    return missing


def ensure_base(verbose: bool = False) -> list:
    """建目錄 + 回報缺檔。**這是唯一會做 I/O 的入口** —— 2026-07-30 起本模組
    匯入時不再自己 mkdir / stat / print(匯入常數不該有副作用,也讓 import 可測)。
    要寫 RESEARCH_BASE 的腳本自己在 main() 開頭呼叫一次。"""
    RESEARCH_BASE.mkdir(parents=True, exist_ok=True)
    return check_base(verbose=verbose)


def assert_unique(df, keys=None, name: str = "面板") -> None:
    """(as_of, stock_id) 必須唯一,否則 raise。

    為什麼是硬檢查而不是 `drop_duplicates()`:重複鍵在下游有三種**不同**的壞法,
    而且三種都不會報錯:
      (a) DataFrame 路徑(load_panel / Engine.pool / universe_ew):重複列直接
          **重複計權**,等權組合裡一支股佔兩份權重,橫斷面百分位的分母也被灌大。
      (b) 矩陣路徑(high52_lab.Panel):`a[r, c] = values` 是 scatter,重複鍵**後寫覆蓋前寫**,
          不會膨脹列數 —— 但「留下哪一筆」取決於列序,結果不可重現。
      (c) 覆蓋率閘門(load_real_panel 的 cov、dual_confirm_mask 的 cov):
          分子被重複列灌大,cov 可以 >1 而順利過關,面板已經爛掉卻報「覆蓋 100%」。
    自動去重會把 (c) 藏起來 —— 重複鍵代表上游 build 有問題,要修上游。
    """
    keys = list(keys or PANEL_KEYS)
    miss = [k for k in keys if k not in df.columns]
    if miss:
        raise KeyError(f"{name} 缺主鍵欄 {miss};實際欄位 {list(df.columns)[:12]}…")
    dup = df.duplicated(subset=keys, keep=False)
    if dup.any():
        sample = df.loc[dup, keys].head(6).to_dict("records")
        raise ValueError(
            f"{name} 的 {tuple(keys)} 不唯一:{int(dup.sum())} / {len(df)} 列重複。\n"
            f"範例:{sample}\n"
            f"重複鍵會重複計權、灌高覆蓋率、並讓矩陣路徑『後寫覆蓋』不可重現 —— "
            f"請修產生這份面板的 build 腳本,不要在下游 drop_duplicates。")


def assert_no_row_growth(before: int, after: int, name: str) -> None:
    """left/inner join 後列數不得增加(增加 = 右表鍵不唯一,已被 assert_unique 擋掉的漏網情況)。"""
    if after > before:
        raise ValueError(
            f"{name}:merge 後列數由 {before:,} 膨脹到 {after:,} —— 右表 (as_of, stock_id) 不唯一。")


def load_panel(adv_floor: float | None = None, listed_only: bool = True,
               horizon: str = "20d", drop_na_ret: bool = True):
    """研究面板的**唯一**入口:obs_alpha ⋈ exec_ret。

    回傳的 DataFrame **不含 `fwd` 欄** —— 那條線有兩個方向相反的偏誤:
      (a) close(T)→close(T+20) 不可執行(訊號在 T 收盤才算得出來);
      (b) 固定 20 交易日的窗串接會漏日,而基準腿不漏 → 兩條腿不同時鐘。
    兩者部分抵銷,淨誤差的**大小與正負都隨換手率變動**,無法事後修正。
    刻意丟掉 `fwd` 是為了讓任何漏改的 lab **直接 KeyError**,而不是靜默用錯的線。

    horizon: "20d" → `fwd_x`(≈1 個月,主用);"60d" → `fwd_x60`(≈3 個月)。
             兩者對外的欄名都是 `fwd_x`,呼叫端不必分支。
    """
    import pandas as pd

    ensure_base()
    if not EXEC_RET.exists():
        raise FileNotFoundError(f"缺少 {EXEC_RET};請先跑 `python scripts/build_exec_ret.py`")
    src = {"20d": RET_COL, "60d": RET_COL_60}[horizon]

    obs = pd.read_parquet(OBS_ALPHA)
    if listed_only and "listed_ok" in obs.columns:
        obs = obs[obs["listed_ok"] == True]        # noqa: E712
    if adv_floor is not None:
        obs = obs[obs["adv20"] >= adv_floor]
    obs = obs.drop(columns=["fwd"], errors="ignore")
    assert_unique(obs, name="obs_alpha(過濾後)")

    ex = pd.read_parquet(EXEC_RET, columns=["as_of", "stock_id", src, "px_in", "tick_slip"])
    assert_unique(ex, name="exec_ret")
    n_obs = len(obs)
    out = obs.merge(ex, on=["as_of", "stock_id"], how="left")
    assert_no_row_growth(n_obs, len(out), "load_panel: obs_alpha ⋈ exec_ret")
    if src != RET_COL:
        out = out.rename(columns={src: RET_COL})
    if drop_na_ret:
        out = out.dropna(subset=[RET_COL])
    return out.reset_index(drop=True)


def add_c2(df):
    """在面板上加 `c2` 欄 —— 生產 `universe_screen_daily.c2_score` 的研究版。

    定義對齊 `scripts/universe_screen_daily.py:299`:
        mean(產業內估值%, 營收YoY%, 距52週高%, 100 − 動能%)
    **殘留落差(已知,非本次要修)**:生產在當日 ~400 檔粗篩池內取百分位,
    這裡在整個 ADV 流動池內取 → 同一支股的 c2 百分位不會完全相同。
    c2 這一腿本來就是原始因子算的,生產與研究用同一套定義,不像綜合分那樣有真身/替身之分。
    """
    g = df.groupby("as_of")
    def pct(col):
        return g[col].transform(lambda s: s.rank(pct=True) * 100)
    df["c2"] = (pct("value_ind") + pct("revenue_yoy") + pct("high52_prox")
                + (100 - pct("momentum"))) / 4.0
    return df


def load_real_panel(adv_floor: float = REALBODY_ADV_FLOOR, listed_only: bool = True,
                    horizon: str = "20d", drop_na_ret: bool = True,
                    with_c2: bool = True, min_coverage: float = 1.0):
    # min_coverage 預設 1.0(零靜默損失,Codex 第三輪第 1 點:研究結論入口都該零缺;
    # 與 build_realbody_scores 的 --min-coverage 預設、dual100_lab.COV_MIN 一致)。
    # 已知合法缺口的探索面板才顯式放寬,並在結論處標記為探索性。
    """**真身**研究面板:obs_alpha ⋈ exec_ret ⋈ realbody_scores。

    這是 L3 的解 —— lab 的「綜合分」從此是生產 `core/scoring_manager` 實際算出來的
    `real_composite`(五面加權),不再是用 obs_alpha 原始因子重建的替身。
    兩者逐月橫斷面 Spearman 0.632、Top-20% 名單 Jaccard 僅 0.35;逐面看更糟 ——
    基本面 0.140、動能面 0.376(見 `docs/現況盤點_2026-07-29.md` §L3)。不是同一個東西。

    **刻意不回傳 `composite` 欄**(理由同 `load_panel` 之於 `fwd`):
    漏改的 lab 會直接 KeyError,不會靜默拿替身當真身跑。真身分數欄名是
    `real_composite`,五個面是 `f_fund` / `f_val` / `f_tech` / `f_mom` / `f_whale`。

    面板由 `resolve_realbody()` 挑 —— **只接受建置門檻 ≤ 要求門檻的面板**。
    拿 2000萬 的面板去跑 100萬 會靜默砍掉 adv ∈ [100萬, 2000萬) 那一段,
    使「雙確認 @ADV≥100萬」退化成「@ADV≥2000萬」卻沒有任何警告 —— 那條路徑不存在,
    缺面板一律 raise 並附重建指令。挑中哪一份記在回傳值的 `df.attrs["realbody_path"]`。
    """
    import pandas as pd

    rb_path = resolve_realbody(adv_floor)

    base = load_panel(adv_floor=adv_floor, listed_only=listed_only,
                      horizon=horizon, drop_na_ret=drop_na_ret)
    base["as_of"] = base["as_of"].astype(str)
    base["stock_id"] = base["stock_id"].astype(str)

    rb = pd.read_parquet(rb_path, columns=["as_of", "stock_id", REAL_COMP_COL, "rating"] + REAL_FACES)
    rb["as_of"] = rb["as_of"].astype(str)
    rb["stock_id"] = rb["stock_id"].astype(str)
    assert_unique(base, name="load_real_panel: base(obs ⋈ exec_ret)")
    assert_unique(rb, name=f"真身面板 {rb_path.name}")

    n0 = len(base)
    out = base.merge(rb, on=["as_of", "stock_id"], how="inner")
    assert_no_row_growth(n0, len(out), f"load_real_panel: base ⋈ {rb_path.name}")
    # 覆蓋率的分子改數**唯一鍵**而非列數 —— 分子若含重複列,cov 可以 >1 而過關。
    # (上面兩道 assert_unique 已擋掉,這裡是第二層保險,順便讓 cov 語意精確。)
    cov = out[PANEL_KEYS].drop_duplicates().shape[0] / n0 if n0 else 0.0
    if cov < min_coverage:
        raise RuntimeError(
            f"真身分數覆蓋率僅 {cov:.1%}(obs {n0} 列 → 併出 {len(out)} 列),低於 {min_coverage:.0%}。\n"
            f"面板 {rb_path.name} 可能過期或建到一半;母體被無聲砍掉會讓對 0050 的比較\n"
            f"不再是同一個母體。請重跑:\n"
            f"  python -m beat_0050.realbody.build_realbody_scores --adv-floor {adv_floor:.0f}")

    if with_c2:
        out = add_c2(out)
    out = out.reset_index(drop=True)
    out.attrs["realbody_path"] = str(rb_path)
    out.attrs["adv_floor"] = adv_floor
    return out


# 2026-07-30:此處原本有 `RESEARCH_BASE.mkdir(...)` 與 `check_base()`,匯入本模組即
# 建目錄 + stat 三個檔 + 印字。已移除 —— 路徑常數模組不該有匯入副作用(見 ensure_base())。
# 要寫 RESEARCH_BASE 的腳本請在 main() 開頭呼叫 `lab_paths.ensure_base()`;
# load_panel / load_real_panel 已內建呼叫。
