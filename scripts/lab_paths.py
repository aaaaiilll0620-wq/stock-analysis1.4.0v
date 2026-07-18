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


RESEARCH_BASE.mkdir(parents=True, exist_ok=True)
check_base()
