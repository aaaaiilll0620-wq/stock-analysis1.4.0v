# =====================================================================
#  lab_paths — 研究實驗室共用路徑常數 (工單_活體演練保護 WP4-2)
#
#  2026-07-19 起研究資料基底不再住 session 專屬 Temp scratchpad
#  (系統清理即滅失,且 obs_alpha 是四份預註冊文件共用的單一資料基底),
#  改住專案內 data/research_base/ (已在 .gitignore,不進 git;OneDrive 同步
#  順帶多一份雲端副本)。三支實驗室 (alpha_gate_lab / portfolio_simulator_lab /
#  basket_dispersion_lab) 一律引用本模組,不得再硬編碼 Temp 路徑。
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

RET_COL = "fwd_x"        # 20 交易日視野的可執行報酬欄
RET_COL_60 = "fwd_x60"   # 60 交易日視野

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


RESEARCH_BASE.mkdir(parents=True, exist_ok=True)
check_base()
