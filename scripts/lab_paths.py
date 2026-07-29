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
#  重生指令 (缺檔時):
#    python scripts/tej_universe_screen_validation.py --dump-obs \
#        --dump-start 2005-01-01 --dump-end 2026-12-31      # → obs_dump_full
#        (60 日視野加 --holding 60 → obs_dump_h60;預設區間只到 2019,務必帶起訖)
#    python scripts/alpha_gate_lab.py --build                # → obs_alpha
# =====================================================================
from pathlib import Path

RESEARCH_BASE = Path(__file__).resolve().parent.parent / "data" / "research_base"

# ---- 資料基底 (讀) ----------------------------------------------------
OBS_DUMP_FULL = RESEARCH_BASE / "obs_dump_full.parquet"   # 20d 前瞻原始 dump (2005-2026)
OBS_ALPHA = RESEARCH_BASE / "obs_alpha.parquet"           # alpha_gate_lab --build 產物
OBS_H60 = RESEARCH_BASE / "obs_dump_h60.parquet"          # 60d 前瞻 dump (籃內離散度用)
EXEC_RET = RESEARCH_BASE / "exec_ret.parquet"             # 可執行報酬線 (scripts/build_exec_ret.py)
REALBODY = RESEARCH_BASE / "realbody_scores.parquet"      # 真身五面分數 (beat_0050.realbody.build_realbody_scores)

RET_COL = "fwd_x"        # 20 交易日視野的可執行報酬欄
RET_COL_60 = "fwd_x60"   # 60 交易日視野

# ---- 真身分數 (生產 core/scoring_manager 算出來的那一份) --------------
REALBODY_ADV_FLOOR = 2e7   # realbody_scores.parquet 的建置門檻;低於此**沒有資料**
REAL_COMP_COL = "real_composite"
REAL_FACES = ["f_fund", "f_val", "f_tech", "f_mom", "f_whale"]
C2_LEGS = ["value_ind", "revenue_yoy", "high52_prox", "momentum"]

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

    if not EXEC_RET.exists():
        raise FileNotFoundError(f"缺少 {EXEC_RET};請先跑 `python scripts/build_exec_ret.py`")
    src = {"20d": RET_COL, "60d": RET_COL_60}[horizon]

    obs = pd.read_parquet(OBS_ALPHA)
    if listed_only and "listed_ok" in obs.columns:
        obs = obs[obs["listed_ok"] == True]        # noqa: E712
    if adv_floor is not None:
        obs = obs[obs["adv20"] >= adv_floor]
    obs = obs.drop(columns=["fwd"], errors="ignore")

    ex = pd.read_parquet(EXEC_RET, columns=["as_of", "stock_id", src, "px_in", "tick_slip"])
    out = obs.merge(ex, on=["as_of", "stock_id"], how="left")
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
                    with_c2: bool = True, min_coverage: float = 0.99):
    """**真身**研究面板:obs_alpha ⋈ exec_ret ⋈ realbody_scores。

    這是 L3 的解 —— lab 的「綜合分」從此是生產 `core/scoring_manager` 實際算出來的
    `real_composite`(五面加權),不再是用 obs_alpha 原始因子重建的替身。
    兩者逐月橫斷面 Spearman 0.632、Top-20% 名單 Jaccard 僅 0.35;逐面看更糟 ——
    基本面 0.140、動能面 0.376(見 `docs/現況盤點_2026-07-29.md` §L3)。不是同一個東西。

    **刻意不回傳 `composite` 欄**(理由同 `load_panel` 之於 `fwd`):
    漏改的 lab 會直接 KeyError,不會靜默拿替身當真身跑。真身分數欄名是
    `real_composite`,五個面是 `f_fund` / `f_val` / `f_tech` / `f_mom` / `f_whale`。

    adv_floor 低於 `REALBODY_ADV_FLOOR` 會**直接 raise** —— realbody_scores 只建到
    ADV≥2000萬,低於此的 stock-month 一列都沒有。靜默 inner join 會讓「雙確認 @
    ADV≥100萬」這種問題退化成「雙確認 @ ADV≥2000萬」卻沒有任何警告。
    """
    import pandas as pd

    if not REALBODY.exists():
        raise FileNotFoundError(
            f"缺少真身分數面板 {REALBODY}。\n"
            "請先跑 `python -m beat_0050.realbody.build_realbody_scores`(全循環約數小時)。")
    if adv_floor < REALBODY_ADV_FLOOR:
        raise ValueError(
            f"realbody_scores 只建到 ADV≥{REALBODY_ADV_FLOOR:.0f}(2000萬),要求的 "
            f"{adv_floor:.0f} 更低 → 低於門檻的 stock-month 完全沒有真身分數。\n"
            "不提供靜默退回替身或靜默縮池的路徑。要跑更低的 ADV 請先重建面板:\n"
            "  改 beat_0050/realbody/build_realbody_scores.py 的 ADV_FLOOR 後重跑。")

    base = load_panel(adv_floor=adv_floor, listed_only=listed_only,
                      horizon=horizon, drop_na_ret=drop_na_ret)
    base["as_of"] = base["as_of"].astype(str)
    base["stock_id"] = base["stock_id"].astype(str)

    rb = pd.read_parquet(REALBODY, columns=["as_of", "stock_id", REAL_COMP_COL, "rating"] + REAL_FACES)
    rb["as_of"] = rb["as_of"].astype(str)
    rb["stock_id"] = rb["stock_id"].astype(str)

    n0 = len(base)
    out = base.merge(rb, on=["as_of", "stock_id"], how="inner")
    cov = len(out) / n0 if n0 else 0.0
    if cov < min_coverage:
        raise RuntimeError(
            f"真身分數覆蓋率僅 {cov:.1%}(obs {n0} 列 → 併出 {len(out)} 列),低於 {min_coverage:.0%}。\n"
            "面板可能過期或建到一半;母體被無聲砍掉會讓對 0050 的比較不再是同一個母體。\n"
            "請重跑 `python -m beat_0050.realbody.build_realbody_scores`。")

    if with_c2:
        out = add_c2(out)
    return out.reset_index(drop=True)


RESEARCH_BASE.mkdir(parents=True, exist_ok=True)
check_base()
