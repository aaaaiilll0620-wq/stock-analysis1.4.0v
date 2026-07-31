# -*- coding: utf-8 -*-
"""overlay_lab.py — P-Overlay-C:regime 曝險 overlay 的部署門檻驗證(HO1–HO4)。
================================================================================
**依 `docs/預註冊_ExposureOverlay.md`(2026-07-31 凍結,Codex 審查通過)實作。**

凍結後禁改:判定門檻(HO1–HO4)、報酬線(`exec_ret.fwd_x`)、HO3(相位對齊虛無)、
股利模型(§3-A-D-💰 均勻加性)、本體 A(dual100 月頻 ~48 檔)、overlay 參數、搜尋空間。
→ 本檔**不提供任何調門檻/掃參數的 CLI 旗標**;所有門檻為模組常數並由 `_assert_frozen()` 自檢。

  部署模擬主測 = 每日限速路徑(§3-A-D):MDD 在**日 NAV** 上量。
  比較組       = 月頻未限速路徑(§3-A-M,逐字對齊 regime_hysteresis_lab.apply_daily_expo)。

  HO1  部署門檻:OOS 日 NAV |MDD| ≤ 40% 且 扣成本 OOS CAGR ≥ 20%
  HO2  擇時 vs 純減碼(確定性,無 seed):dd_flat − dd_AC ≥ 5pp 且 CAGR_AC ≥ CAGR_flat − 1pp
  HO3  相位對齊虛無:固定 e_lim/成本,只旋轉 r_A(d);p=(1+#{dd*≤dd_real})/(B+1) < 0.05
  HO4a 硬門檻(滑價 0.60%):同 HO1 兩條 → 失敗即不可部署
  HO4b 描述性:六時代 ≥5/6 段 |MDD|≤40%,且 2008/2022 兩壓力段均達標

用法(凍結後、Codex 審查程式碼通過後才執行):
    python beat_0050/strategies/overlay_lab.py --part verify   # 對帳+揭露表,不判定
    python beat_0050/strategies/overlay_lab.py --part ho1
    python beat_0050/strategies/overlay_lab.py --part all

✅ (D1) **選股換手成本的日內落點 —— 已由 Codex 於 2026-07-31 裁定:`entry_day`。**
   凍結預註冊原本無明文(§0「成本」列只說「已含在 `r_A`」、§3-A-D 日報酬式無成本項、
   §8-1b 是月度加總的陳述),故本檔原先 `COST_PLACEMENT=None` fail-closed 拒跑。
   裁定與理由已寫入 **`docs/預註冊_ExposureOverlay_附錄D1.md`(2026-07-31 pre-run 凍結)**:
   成本於**每月新持股在 `open(訊號日+1)` 建倉的第一個 open→open 日段**扣除;
   **初始建倉(第一個月,turn=1.0)依同一規則**。
   該附錄聲明:**不改**月度 `r_A(t)`、門檻、報酬線、本體 A、overlay 參數,且**凍結時 A×C OOS
   數字尚未計算**。月度加性總量與落點無關;落點只以二階量影響日 NAV 路徑(故須 pre-run 凍結)。

⚠ 其餘實作決策(§3-A-D 未逐字規定,送 Codex 確認):
  (D2) **e_lim 起點**:依 §3-A-D「自 OOS 起點即套用」與 `e_lim(0)=1.0`,限速器於**受評窗起點**
       重置為 1.0(OOS 評估用 OOS 起點;HO4b 全期評估用全期起點)。
  (D3) **訊號日曆對齊**:body 日期若不在 regime 特徵日曆上,取 ≤ 該日的最後一個訊號值(bisect)。
================================================================================
"""
from __future__ import annotations
import argparse
import bisect
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parent.parent.parent
for _p in (PROJ, PROJ / "scripts", PROJ / "beat_0050" / "strategies"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from beat_0050.honest_backtest import RF_ANNUAL, ERAS                      # noqa: E402
from high52_lab import Panel, evaluate, dual_confirm_mask, FEE_RT          # noqa: E402
from regime_signal_lab import build_regime_features                        # noqa: E402
from regime_hysteresis_lab import ladder_expo_daily, DERISK_COST           # noqa: E402

# ==============================================================================
# 凍結常數(預註冊 §0/§2/§3/§4)—— 不得由 CLI / env 覆寫
# ==============================================================================
ADV_FLOOR   = 1e6          # 本體 A:ADV≥100萬 層
TOP_PCT     = 20           # 只測這一個值,不掃
TARGET_TIER = "100萬"
WF_MIN_TRAIN = 60          # OOS 起點 = 第 60 個月(與 dual100 H2 同段)

UP_CONFIRM = DOWN_CONFIRM = 3      # overlay 遲滯(繼承 regime_hysteresis_lab)
RATE_LIMIT_CAP = 0.20              # 每交易日最大曝險調整(繼承 預註冊_ExposureRateLimit)
R_CASH_D = RF_ANNUAL / 252.0       # 日現金腿(§3-A-D)
R_CASH_M = RF_ANNUAL / 12.0        # 月現金腿(§3-A-M)

MDD_GATE   = 40.0          # HO1/HO4a:|MDD| ≤ 40%
CAGR_GATE  = 20.0          # HO1/HO4a:扣成本 OOS CAGR ≥ 20%
HO2_DD_GAP = 5.0           # HO2:dd_flat − dd_AC ≥ 5.0pp
HO2_CAGR_TOL = 1.0         # HO2:CAGR_AC ≥ CAGR_flat − 1.0pp
HO3_SEED = 20260730        # HO3:固定 seed
HO3_B    = 1000            # HO3:reps(凍結,無 --reps 旗標)
HO3_ALPHA = 0.05
H4_SLIP  = 0.60            # HO4:來回滑價 %
HO4B_MIN_PASS = 5          # HO4b:≥5/6 段
HO4B_STRESS = ("2005-2009(海嘯)", "2022空頭")
RECON_TOL = 0.01           # 對帳容差(pp);超過即 fail-closed 中止

# ---- D1 已裁定(Codex 2026-07-31;見 docs/預註冊_ExposureOverlay_附錄D1.md,pre-run 凍結)----
#   "entry_day" —— 選股換手成本 turn·(FEE_RT+slip) 於**每月新持股在 open(訊號日+1) 建倉的
#                  第一個 open→open 日段**一次扣除;**初始建倉(第一個月,turn=1.0)同規則**。
#   (未採用的替代:"spread_uniform" 平均攤到該月 n 段 —— 附錄 D1 已否決,不得改回。)
#   兩者月度加性總量相同,但日 NAV 路徑不同 → 日 MDD 不同 → 故須 pre-run 凍結,不得看數字後再選。
COST_PLACEMENT: str = "entry_day"
_COST_PLACEMENT_OK = ("entry_day",)          # 附錄 D1 凍結後,唯一合法值

# ---- D1(補鎖,2026-07-31):成本「套用算術」---------------------------------------
#   "additive_return" = 對該日段的**報酬**做加性扣除:r_day := r_day − turn·(FEE_RT+slip)
#   **不採** NAV 乘法(nav *= (1 − cost/100))。
#   理由:與 frozen 官方月度 r_A(t) = gross − turnover_cost 的**加性**定義一致
#        (§8-1b 的加性分解對帳門檻正是建立在此)。乘法會引入 −cost×gross 的二階項,
#        使日路徑與官方月度定義不同調。**唯一合法值。**
COST_ARITHMETIC: str = "additive_return"
_COST_ARITHMETIC_OK = ("additive_return",)

TEJ_CACHE = Path(os.environ.get("TEJ_CACHE", str(Path.home() / "tej_cache")))
OUTDIR = PROJ / "beat_0050" / "results"


def _assert_frozen() -> None:
    """門檻鎖定:**所有判定關鍵常數**與預註冊不符即拒跑(防止事後放寬),
    並擋下尚未裁定的 D1(選股成本日內落點)。"""
    frozen = {
        # --- 待驗對象 / 母體(§0)---
        "ADV_FLOOR": (ADV_FLOOR, 1e6), "TOP_PCT": (TOP_PCT, 20),
        "TARGET_TIER": (TARGET_TIER, "100萬"), "WF_MIN_TRAIN": (WF_MIN_TRAIN, 60),
        # --- overlay 參數(繼承凍結,§0/§3-A)---
        "UP_CONFIRM": (UP_CONFIRM, 3), "DOWN_CONFIRM": (DOWN_CONFIRM, 3),
        "RATE_LIMIT_CAP": (RATE_LIMIT_CAP, 0.20), "DERISK_COST": (DERISK_COST, 0.285),
        # --- 成本 / 現金腿(§0/§3-A)---
        "FEE_RT": (FEE_RT, 0.47), "RF_ANNUAL": (RF_ANNUAL, 1.0),
        "R_CASH_D": (R_CASH_D, 1.0 / 252.0), "R_CASH_M": (R_CASH_M, 1.0 / 12.0),
        # --- HO1 / HO4a 門檻(§2/§4)---
        "MDD_GATE": (MDD_GATE, 40.0), "CAGR_GATE": (CAGR_GATE, 20.0),
        # --- HO2(§2)---
        "HO2_DD_GAP": (HO2_DD_GAP, 5.0), "HO2_CAGR_TOL": (HO2_CAGR_TOL, 1.0),
        # --- HO3 相位對齊虛無(§2)---
        "HO3_SEED": (HO3_SEED, 20260730), "HO3_B": (HO3_B, 1000),
        "HO3_ALPHA": (HO3_ALPHA, 0.05),
        # --- HO4(§2)---
        "H4_SLIP": (H4_SLIP, 0.60), "HO4B_MIN_PASS": (HO4B_MIN_PASS, 5),
        "HO4B_STRESS": (tuple(HO4B_STRESS), ("2005-2009(海嘯)", "2022空頭")),
        # --- 對帳紀律(§3-C)---
        "RECON_TOL": (RECON_TOL, 0.01),
        # --- D1 附錄(2026-07-31 pre-run 凍結):落點 + 套用算術 ---
        "COST_PLACEMENT": (COST_PLACEMENT, "entry_day"),
        "COST_ARITHMETIC": (COST_ARITHMETIC, "additive_return"),
        # --- 六時代(HO4b 依賴 honest_backtest.ERAS,防上游漂移)---
        "ERAS_names": (tuple(n for n, _, _ in ERAS),
                       ("2005-2009(海嘯)", "2010-2014", "2015-2018",
                        "2019-2021", "2022空頭", "2023-2026")),
    }
    bad = [f"{k}: {v[0]!r} ≠ 凍結值 {v[1]!r}" for k, v in frozen.items() if v[0] != v[1]]
    if bad:
        raise SystemExit("❌ 門檻鎖定失敗(預註冊 §2/§4 已凍結,不得修改):\n  " + "\n  ".join(bad))
    if not set(HO4B_STRESS) <= set(n for n, _, _ in ERAS):
        raise SystemExit("❌ HO4B_STRESS 不在 ERAS 名稱集合內 —— 壓力段判定會靜默失效。")
    for e in sorted(k for k in os.environ if k.startswith("OVERLAY_")):
        raise SystemExit(f"❌ 偵測到環境變數覆寫 {e} —— 凍結後不得由外部改參數。")

    # ---- D1 閘門:凍結預註冊無明文規定選股成本的日內落點 → 未裁定即拒跑 ----
    if COST_ARITHMETIC not in _COST_ARITHMETIC_OK:
        raise SystemExit(
            "⛔ D1 成本套用算術與凍結附錄不符,拒絕執行。\n"
            f"   合法值:{_COST_ARITHMETIC_OK};目前 COST_ARITHMETIC={COST_ARITHMETIC!r}。\n"
            "   附錄 D1 已鎖定 **additive_return**(r_day := r_day − turn·(FEE_RT+slip)),\n"
            "   **不採 NAV 乘法** —— 理由:與官方月度 r_A(t)=gross−turnover_cost 的加性定義一致。")

    if COST_PLACEMENT not in _COST_PLACEMENT_OK:
        raise SystemExit(
            "⛔ D1 未裁定,拒絕執行。\n"
            "   選股換手成本『落在月內哪一天』在凍結預註冊中**無明文**:\n"
            "     · §0 成本列只寫「已含在 r_A」(未定落點)\n"
            "     · §3-A-D 日報酬式 r_A(d)=Σ w_i·r_i(d) **無成本項**\n"
            "     · §8-1b 的 turn·(FEE_RT+slip) 是**月度加總**陳述\n"
            "   (對照:overlay 成本的期內落點 §2/§3-A-D **有**明文,選股成本沒有。)\n"
            f"   合法值:{_COST_PLACEMENT_OK};目前 COST_PLACEMENT={COST_PLACEMENT!r}。\n"
            "   月度總量在各落點下相同,但**日 NAV 路徑不同 → 日 MDD 不同 → 直接影響 HO1/HO4a**。\n"
            "   → 須先由使用者/Codex 裁定,寫入預註冊附錄並簽核後,才可設定本常數並執行。")

    print(f"[frozen] 預註冊_ExposureOverlay.md(2026-07-31 凍結)門檻自檢通過({len(frozen)} 項)"
          f" —— MDD≤{MDD_GATE}% / CAGR≥{CAGR_GATE}% / HO2 gap≥{HO2_DD_GAP}pp / "
          f"HO3 B={HO3_B} seed={HO3_SEED} α={HO3_ALPHA} / H4 滑價 {H4_SLIP}% / "
          f"D1={COST_PLACEMENT}+{COST_ARITHMETIC}")


# ==============================================================================
# 指標(日 NAV / 月 NAV 共用)
# ==============================================================================
def _apply_sel_cost(dr: np.ndarray, cost: float, sign: float = -1.0) -> None:
    """把該月選股換手成本套進日報酬序列(就地)。**本專案唯一的選股成本套用點**
    (`_build` / `with_slip` / `ledger_body_daily` 三處皆呼叫本函式 → 單一事實來源)。

    D1 凍結(`docs/預註冊_ExposureOverlay_附錄D1.md`):
      · 落點 `COST_PLACEMENT="entry_day"` —— 建倉日的第一個 open→open 日段。
      · 算術 `COST_ARITHMETIC="additive_return"` —— **對報酬加性扣除**
        `r_day := r_day − turn·(FEE_RT+slip)`,**不採 NAV 乘法**;與官方月度
        `r_A(t) = gross − turnover_cost` 的加性定義一致。
    兩者皆已由 `_assert_frozen()` 鎖定;此處再防禦一次(fail-closed)。"""
    if COST_PLACEMENT != "entry_day" or COST_ARITHMETIC != "additive_return":
        raise RuntimeError(
            f"D1 已凍結為 entry_day + additive_return,不得變更"
            f"(目前 COST_PLACEMENT={COST_PLACEMENT!r}, COST_ARITHMETIC={COST_ARITHMETIC!r})")
    dr[0] += sign * cost          # 加性:直接改該日段的報酬,非乘 NAV


def nav_of(r_pct: np.ndarray) -> np.ndarray:
    return np.cumprod(1.0 + np.asarray(r_pct, float) / 100.0)


def mdd_pct(nav: np.ndarray) -> float:
    """最大回撤(負 %)。|MDD| 用 abs()。"""
    a = np.asarray(nav, float)
    return float((a / np.maximum.accumulate(a) - 1.0).min() * 100.0)


def cagr_pct(nav: np.ndarray, periods_per_year: float) -> float:
    a = np.asarray(nav, float)
    n = len(a)
    return float((a[-1] ** (periods_per_year / n) - 1.0) * 100.0) if n else np.nan


def sharpe_of(r_pct: np.ndarray, ppy: float) -> float:
    r = np.asarray(r_pct, float) / 100.0
    if len(r) < 6 or r.std(ddof=1) == 0:
        return np.nan
    nav = np.cumprod(1 + r)
    cagr = (nav[-1] ** (ppy / len(r)) - 1) * 100
    vol = r.std(ddof=1) * np.sqrt(ppy) * 100
    return float((cagr - RF_ANNUAL) / vol)


# ==============================================================================
# 本體 A 的日報酬序列(§3-A-D:價格 open→open + 均勻加性股利 δ=dy12/n)
# ==============================================================================
class BodyDaily:
    """dual100 本體 A 的日報酬路徑。月選股、月內等權買進持有(權重漂移、不重配)。

    slip=None → 用面板實測 tick_slip(主測);給數值 → 常數滑價(HO4)。
    """

    def __init__(self, P: Panel, M: np.ndarray, slip: float | None = None):
        self.P, self.M = P, M
        cnt = M.sum(1)
        self.act = np.where(cnt > 0)[0]
        ca = cnt[self.act].astype(float)
        # 官方加性 gross(= evaluate 的 mean_held(fwd_x)),供對帳
        self.gross_off = np.einsum("ij,ij->i", M[self.act],
                                   np.nan_to_num(P.RET[self.act])) / ca
        slip_mat = P.SLIP if slip is None else np.full_like(P.SLIP, float(slip))
        slip_m = np.einsum("ij,ij->i", M[self.act], np.nan_to_num(slip_mat[self.act])) / ca
        inter = (M[self.act][1:] & M[self.act][:-1]).sum(1).astype(float)
        self.turn = np.concatenate([[1.0], 1.0 - inter / ca[1:]])
        self.cost = self.turn * (FEE_RT + slip_m)              # 每月選股換手成本(%)
        self.r_month_off = self.gross_off - self.cost          # = dual100 evaluate() 的 r_A(t)
        self._build()

    # -- 日價與 (as_of, stock) 的窗索引 ------------------------------------
    def _load_prices(self) -> None:
        import duckdb
        need = sorted({str(s) for ti in self.act for s in self.P.stocks[self.M[ti]]})
        con = duckdb.connect(); con.execute("PRAGMA threads=8")
        con.execute(f"""CREATE TEMP TABLE px AS
            SELECT stock_id, CAST(date AS VARCHAR) date, open, dividend_yield_TSE dy,
                   row_number() OVER (PARTITION BY stock_id ORDER BY date) i
            FROM read_parquet('{(TEJ_CACHE/"price_valuation").as_posix()}/*.parquet',
                              union_by_name=true)
            WHERE close > 0""")
        asofs = [str(self.P.month_s[ti])[:10] for ti in self.act]
        obs = pd.DataFrame([(a, s) for a in asofs for s in need],
                           columns=["as_of", "stock_id"])
        con.register("obs", obs)
        b = con.execute("""SELECT o.as_of, o.stock_id, p.i i0, p.dy FROM obs o
            ASOF JOIN px p ON o.stock_id=p.stock_id AND p.date <= o.as_of""").df()
        mm = np.array(sorted(b.as_of.unique())); tm = {m: k for k, m in enumerate(mm)}
        b["t"] = b.as_of.map(tm)
        b = b.sort_values(["stock_id", "t"])
        g = b.groupby("stock_id")
        # 出場 = 「緊鄰的下一個月」訊號日+1 開盤(與 build_exec_ret.fwd_x 同慣例)
        b["ix"] = np.where(g.t.shift(-1) == b.t + 1, g.i0.shift(-1), np.nan)
        b["dy12"] = np.clip(b.dy.fillna(0.0), 0, 15) / 12.0
        self.win = {(r.as_of, r.stock_id): (int(r.i0), r.ix, float(r.dy12))
                    for r in b.itertuples()}
        q = ",".join(repr(s) for s in need)
        pxdf = con.execute(f"SELECT stock_id,i,date,open FROM px WHERE stock_id IN ({q}) "
                           "ORDER BY stock_id,i").df()
        self.ser = {sid: (d["open"].to_numpy(float), d["date"].to_numpy())
                    for sid, d in pxdf.groupby("stock_id")}

    def _build(self) -> None:
        """逐月組出日報酬;同時保留每月的持股/單股日報酬(供第二路徑與揭露表)。"""
        self._load_prices()
        self.dates: list[str] = []
        self.r_daily: list[float] = []
        self.month_of_day: list[int] = []     # 每個日段所屬的 act-index
        self.month_slice: dict[int, tuple[int, int]] = {}
        self.per_month: dict[int, dict] = {}
        self.mon_addit: dict[int, float] = {}    # 加性分解 gross(對帳用)
        for k, ti in enumerate(self.act):
            asof = str(self.P.month_s[ti])[:10]
            segs, addit, win = {}, [], {}
            for sid in (str(s) for s in self.P.stocks[self.M[ti]]):
                rec = self.win.get((asof, sid))
                if rec is None or not np.isfinite(rec[1]):
                    continue
                i0, ix, dy12 = int(rec[0]), int(rec[1]), rec[2]
                o, dt = self.ser.get(sid, (None, None))
                if o is None or ix + 1 > len(o):
                    continue
                w = o[i0:ix + 1]
                if len(w) < 2 or not np.all(w > 0):
                    continue
                pr = (w[1:] / w[:-1] - 1.0) * 100.0          # n 個 open→open 日段
                n = len(pr)
                segs[sid] = (dt[i0:ix], pr, dy12 / n)         # 均勻加性股利 δ=dy12/n
                win[sid] = (i0, ix, dy12)                     # 供第二路徑獨立重算
                addit.append((np.prod(1 + pr / 100.0) - 1.0) * 100.0 + dy12)
            if not segs:
                continue
            alld = sorted({d for v in segs.values() for d in v[0]})
            di = {d: j for j, d in enumerate(alld)}
            L, N = len(alld), len(segs)
            cum = np.zeros((N, L))
            for r_, (dts, pr, dlt) in enumerate(segs.values()):
                col = np.array([di[d] for d in dts])
                row = np.zeros(L)
                row[col] = pr + dlt                            # 價格 + 均勻加性股利
                cum[r_] = np.cumprod(1.0 + row / 100.0)
            V = cum.mean(0)                                    # 等權買進持有的月內價值路徑
            dr = np.empty(L)
            dr[0] = (V[0] - 1.0) * 100.0
            dr[1:] = (V[1:] / V[:-1] - 1.0) * 100.0
            _apply_sel_cost(dr, self.cost[k])                  # (D1) 落點由 COST_PLACEMENT 決定
            s0 = len(self.dates)
            self.dates.extend(alld)
            self.r_daily.extend(dr.tolist())
            self.month_of_day.extend([ti] * L)
            self.month_slice[ti] = (s0, s0 + L)
            self.per_month[ti] = {"n_held": N, "dates": alld, "win": win}
            self.mon_addit[ti] = float(np.mean(addit))
        self.dates = np.array(self.dates)
        self.r_daily = np.array(self.r_daily, float)
        self.month_of_day = np.array(self.month_of_day)

    def oos_mask(self) -> np.ndarray:
        return self.month_of_day >= WF_MIN_TRAIN

    def with_slip(self, slip: float) -> "BodyDaily":
        """HO4:換常數滑價。**只有換手成本會變**(日毛報酬完全相同),故直接改建倉日那筆成本,
        不重建價格 —— 既精確又避免兩次建置產生分歧。"""
        import copy
        nb = copy.copy(self)
        cnt = self.M.sum(1); ca = cnt[self.act].astype(float)
        slip_m = np.einsum("ij,ij->i", self.M[self.act],
                           np.full_like(self.P.SLIP, float(slip))[self.act]) / ca
        nb.cost = self.turn * (FEE_RT + slip_m)
        nb.r_month_off = self.gross_off - nb.cost
        nb.r_daily = self.r_daily.copy()
        for k, ti in enumerate(self.act):                 # 依 D1 落點回沖舊成本、套上新成本
            if ti not in self.month_slice:
                continue
            s0, s1 = self.month_slice[ti]
            seg = nb.r_daily[s0:s1]                       # view,就地調整
            _apply_sel_cost(seg, self.cost[k], sign=+1.0)     # 加回舊
            _apply_sel_cost(seg, nb.cost[k], sign=-1.0)       # 扣新
        return nb


# ==============================================================================
# overlay 曝險:日訊號 → 延遲一日 → 限速(§3-A-D、§3-A-D-⏱)
# ==============================================================================
_SIG_CACHE: tuple | None = None


def _regime_signal() -> tuple[list[str], np.ndarray]:
    """(日期list, e_daily) —— 凍結參數 MA50/100/200 + debounce(3,3),整個 run 只建一次。"""
    global _SIG_CACHE
    if _SIG_CACHE is None:
        feat = build_regime_features()
        _SIG_CACHE = (feat["date"].astype(str).tolist(),
                      ladder_expo_daily(feat, UP_CONFIRM, DOWN_CONFIRM))
    return _SIG_CACHE


def daily_signal(dates: np.ndarray) -> np.ndarray:
    """把 regime 日訊號 e_daily 對齊到 body 的日期格點(D3:取 ≤ 該日的最後一個值)。"""
    fd, sig = _regime_signal()
    out = np.empty(len(dates))
    for j, d in enumerate(dates):
        i = bisect.bisect_right(fd, str(d)) - 1
        out[j] = float(sig[i]) if i >= 0 else 1.0      # 訊號日曆起點前視為滿倉
    return out


def rate_limited(sig: np.ndarray) -> np.ndarray:
    """§3-A-D:e_lim(d) = e_lim(d−1) + clip(sig(d−1) − e_lim(d−1), ∓cap);e_lim(0)=sig(0)=1.0。
    **用 sig(d−1) 不用 sig(d) → 無 look-ahead。** 回傳長度 D+1(含 e_lim(0))。"""
    D = len(sig)
    e = np.empty(D + 1)
    e[0] = 1.0
    prev_sig = 1.0                                     # sig(0)=1.0
    for d in range(1, D + 1):
        e[d] = e[d - 1] + np.clip(prev_sig - e[d - 1], -RATE_LIMIT_CAP, RATE_LIMIT_CAP)
        prev_sig = sig[d - 1]                          # 下一段用「本段起始日前一日收盤」的訊號
    return e


def overlay_returns(rA: np.ndarray, e_full: np.ndarray) -> np.ndarray:
    """§3-A-D:r_AC(d) = e(d)·r_A(d) + (1−e(d))·r_cash − |e(d)−e(d−1)|·DERISK_COST。"""
    e, e_prev = e_full[1:], e_full[:-1]
    return e * rA + (1.0 - e) * R_CASH_D - np.abs(e - e_prev) * DERISK_COST


# ==============================================================================
# 第二路徑:部位帳本(units × price + cash),與向量路徑獨立實作(§3-C 對帳)
# ==============================================================================
def ledger_body_daily(body: BodyDaily) -> np.ndarray:
    """**獨立**重算本體 A 的日報酬:用「持股單位數 × 開盤價 + 股利現金再投入」逐日結算,
    而非對報酬序列連乘 → 與 `BodyDaily._build()` 是兩套實作,供 §3-C 逐期對帳。

    每檔:`units(0)=(1/N)/px(0)`;每段 `div_cash = units·px(q−1)·δ/100`、
    `val = units·px(q) + div_cash`、`units = val/px(q)`(股利再投入)。
    → `val(q) = val(q−1)·(1 + (pr(q)+δ)/100)`,與規格語意一致但機制不同
    (單位數/價格/現金流 vs 報酬連乘),故能抓出視窗、對齊、股利、權重漂移類的實作錯誤。
    """
    out = np.full(len(body.r_daily), np.nan)
    for k, ti in enumerate(body.act):
        pm = body.per_month.get(ti)
        if pm is None:
            continue
        s0, s1 = body.month_slice[ti]
        grid = pm["dates"]
        gpos = {d: j for j, d in enumerate(grid)}
        L, N = len(grid), pm["n_held"]
        tot = np.zeros(L)
        for sid, (i0, ix, dy12) in pm["win"].items():
            o, dt = body.ser[sid]
            px = o[i0:int(ix) + 1]
            n = len(px) - 1
            if n < 1:
                continue
            delta = dy12 / n                              # 均勻加性股利
            units = (1.0 / N) / px[0]
            path = np.full(L, np.nan)
            for q in range(1, n + 1):
                div_cash = units * px[q - 1] * delta / 100.0
                val = units * px[q] + div_cash
                units = val / px[q]                       # 再投入 → 維持加性語意
                path[gpos[dt[i0 + q - 1]]] = val          # 以「段起始日」為標籤(同向量路徑)
            tot += pd.Series(path).ffill().fillna(1.0 / N).to_numpy()
        dr = np.empty(L)
        dr[0] = (tot[0] - 1.0) * 100.0
        dr[1:] = (tot[1:] / tot[:-1] - 1.0) * 100.0
        _apply_sel_cost(dr, body.cost[k])                 # (D1) 與向量路徑同一落點
        out[s0:s1] = dr
    return out


# ==============================================================================
# 主測序列組裝
# ==============================================================================
def build_series(body: BodyDaily, window: str = "oos") -> dict:
    m = body.oos_mask() if window == "oos" else np.ones(len(body.r_daily), bool)
    idx = np.where(m)[0]
    dates, rA = body.dates[idx], body.r_daily[idx]
    sig = daily_signal(dates)
    e_full = rate_limited(sig)                          # (D2) 受評窗起點 e_lim(0)=1.0
    r_ac = overlay_returns(rA, e_full)
    return {"idx": idx, "dates": dates, "rA": rA, "sig": sig, "e_full": e_full,
            "e": e_full[1:], "r_ac": r_ac, "nav": nav_of(r_ac)}


def show_daily(tag: str, r: np.ndarray) -> dict:
    nav = nav_of(r)
    d = {"cagr": cagr_pct(nav, 252.0), "mdd": mdd_pct(nav),
         "sharpe": sharpe_of(r, 252.0), "n": len(r)}
    print(f"{tag:<34}{d['cagr']:>9.2f}{d['sharpe']:>8.2f}{d['mdd']:>9.2f}{d['n']:>8}")
    return d


# ==============================================================================
# verify — 對帳與揭露(不做任何 HO 判定)
# ==============================================================================
def preflight(body: BodyDaily, S: dict) -> None:
    """**強制前置對帳(fail-closed)**:任一項超標即 `SystemExit`,不進入任何 HO 判定。
    由 `main()` 對**所有** `--part` 無條件執行 —— `ho1/ho2/ho3/ho4` 皆不可繞過(§3-C 紀律)。"""
    print("\n" + "=" * 92)
    print(f"preflight — 強制對帳(fail-closed,容差 {RECON_TOL}pp;超標即中止,不做 HO 判定)")
    print("=" * 92)
    fails: list[str] = []

    # P1 加性分解 vs 官方 gross(§3-A-D-💰(1) 凍結門檻,應精確)
    ti_all = [ti for ti in body.act if ti in body.mon_addit]
    k_of = {ti: int(np.where(body.act == ti)[0][0]) for ti in ti_all}
    d1 = np.array([abs(body.mon_addit[ti] - body.gross_off[k_of[ti]]) for ti in ti_all])
    ok1 = d1.max() <= RECON_TOL
    print(f"P1 加性分解(價格連乘+股利加總) vs 官方 gross:最大 {d1.max():.3g} pp"
          f"  超標 {(d1 > RECON_TOL).sum()}/{len(d1)}  {'✅' if ok1 else '❌'}")
    if not ok1:
        fails.append(f"P1 加性分解對帳最大差 {d1.max():.4g} pp > {RECON_TOL} pp(§8-1b 凍結門檻)")

    # P2 雙路徑對帳(§3-C):向量連乘 vs 部位帳本(units×price+股利現金)
    rb = ledger_body_daily(body)
    pair = np.isfinite(rb) & np.isfinite(body.r_daily)
    d2 = np.abs(rb[pair] - body.r_daily[pair])
    nav_b = nav_of(overlay_returns(rb[S["idx"]], S["e_full"]))
    rel = np.abs(S["nav"] / nav_b - 1.0) * 100.0
    ok2 = (d2.max() <= RECON_TOL) and (rel.max() <= RECON_TOL)
    print(f"P2 雙路徑對帳:本體日報酬最大 {d2.max():.3g} pp;A×C 淨值最大相對 {rel.max():.3g} pp"
          f"  {'✅' if ok2 else '❌'}")
    if not ok2:
        fails.append(f"P2 雙路徑對帳超標(body {d2.max():.4g} pp / NAV {rel.max():.4g} pp)")

    # P3 序列完整性(靜默污染防線)
    prob = []
    if len(S["sig"]) != len(S["rA"]):
        prob.append("sig/rA 長度不一致")
    if len(S["e_full"]) != len(S["rA"]) + 1:
        prob.append("e_full 長度應為 D+1")
    if not np.all(np.isfinite(S["r_ac"])):
        prob.append(f"r_ac 有 {int((~np.isfinite(S['r_ac'])).sum())} 個非有限值")
    if not np.all((S["e"] >= -1e-12) & (S["e"] <= 1 + 1e-12)):
        prob.append("e_lim 超出 [0,1]")
    if np.max(np.abs(np.diff(S["e_full"]))) > RATE_LIMIT_CAP + 1e-12:
        prob.append(f"單日曝險變動超過 cap={RATE_LIMIT_CAP}")
    ok3 = not prob
    print(f"P3 序列完整性(長度/有限值/e∈[0,1]/限速上限):{'✅' if ok3 else '❌ ' + '; '.join(prob)}")
    if not ok3:
        fails.append("P3 序列完整性:" + "; ".join(prob))

    if fails:
        raise SystemExit("\n❌ preflight 未通過 —— **中止,不做任何 HO 判定**(§3-C:"
                         "凡進判定的淨值序列須兩條路徑對得起來)。\n  - " + "\n  - ".join(fails))
    print("✅ preflight 全數通過 —— 允許進入 HO 判定。")


def run_verify(body: BodyDaily, S: dict) -> None:
    """揭露表(非門檻);門檻性對帳一律在 `preflight()`,已於本函式之前強制執行。"""
    print("\n" + "=" * 92)
    print("verify — 揭露表(§3-A-D-💰(2) 日 NAV 複利差 / §3-A-D-⏱ 無 look-ahead 抽查)")
    print("=" * 92)

    ti_all = [ti for ti in body.act if ti in body.mon_addit]
    k_of = {ti: int(np.where(body.act == ti)[0][0]) for ti in ti_all}
    diffs = []
    for ti in ti_all:
        s, e_ = body.month_slice[ti]
        mret = (np.prod(1 + body.r_daily[s:e_] / 100.0) - 1) * 100.0
        diffs.append(abs(mret - body.r_month_off[k_of[ti]]))
    d = np.array(diffs)
    print(f"\n[揭露 1] 實際日 NAV 複利 vs 官方月 r_A(t) —— **不等,非門檻**(§3-A-D-💰(2))")
    print(f"    最大月差 {d.max():.4g} pp   中位 {np.median(d):.3g}   "
          f">{RECON_TOL}pp: {(d > RECON_TOL).sum()}/{len(d)}")

    sig, e = S["sig"], S["e"]
    chg = np.where(np.diff(sig) != 0)[0]
    print(f"\n[揭露 2] 訊號變更日抽查(§3-A-D-⏱;共 {len(chg)} 次變更,列前 3 次)")
    for c in chg[:3]:
        if c + 2 < len(e):
            print(f"    close({str(S['dates'][c])}) sig {sig[c]:.3f}→{sig[c+1]:.3f}"
                  f"  →  e_lim(當日)={e[c]:.3f}(仍為舊)、"
                  f"e_lim({str(S['dates'][c+1])})={e[c+1]:.3f}(才開始走位)")
    print("    ↑ 訊號於 close(d) 確定 → 只影響 open(d+1) 起的曝險;當日報酬段不被回溯改權。")


# ==============================================================================
# HO1 / HO2 / HO3 / HO4
# ==============================================================================
def run_ho1(S: dict, body: BodyDaily) -> dict:
    print("\n" + "=" * 92)
    print("HO1 — 部署門檻(主假設;日限速路徑,MDD 在日 NAV 上量)")
    print("=" * 92)
    print(f"\nOOS {str(S['dates'][0])} ~ {str(S['dates'][-1])}({len(S['r_ac'])} 交易日)"
          f";平均曝險 ē={S['e'].mean():.4f}、切換次數 K={int((np.diff(S['e'])!=0).sum())}、"
          f"TV={np.abs(np.diff(S['e_full'])).sum():.2f}")
    print(f"\n{'':<34}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'日數':>8}")
    m_ac = show_daily("A×C(日限速,主測)", S["r_ac"])
    show_daily("  └ 本體 A(無 overlay,參考)", S["rA"])
    # 月頻未限速比較組(§3-A-M)
    mc = monthly_comparison(body)
    print(f"{'比較組:月頻未限速 A×C':<34}{mc['cagr']:>9.2f}{mc['sharpe']:>8.2f}"
          f"{mc['mdd']:>9.2f}{mc['n']:>8}")
    ok_mdd = abs(m_ac["mdd"]) <= MDD_GATE
    ok_cagr = m_ac["cagr"] >= CAGR_GATE
    ok = ok_mdd and ok_cagr
    print(f"\nHO1-a |MDD| {abs(m_ac['mdd']):.2f}% ≤ {MDD_GATE}%   → {'✅' if ok_mdd else '❌'}")
    print(f"HO1-b CAGR {m_ac['cagr']:.2f}% ≥ {CAGR_GATE}%       → {'✅' if ok_cagr else '❌'}")
    print(f"HO1 → {'✅通過' if ok else '❌否定'}"
          + ("" if ok else "  → 依 §4 出口 1/2:**不可正式部署**,不得在本案調 overlay 參數。"))
    return {"ho1": ok, "m_ac": m_ac, "monthly": mc}


def monthly_comparison(body: BodyDaily) -> dict:
    """§3-A-M 比較組:月頻、未限速、as_of 點取曝險(逐字對齊 apply_daily_expo)。"""
    fd, sig = _regime_signal()
    out, prev = [], 1.0
    for k, ti in enumerate(body.act):
        if ti < WF_MIN_TRAIN:
            continue
        asof = str(body.P.month_s[ti])[:10]
        i = bisect.bisect_right(fd, asof) - 1
        e = float(sig[i]) if i >= 0 else 1.0
        out.append(e * body.r_month_off[k] + (1 - e) * R_CASH_M - abs(e - prev) * DERISK_COST)
        prev = e
    r = np.array(out, float)
    nav = nav_of(r)
    return {"cagr": cagr_pct(nav, 12.0), "mdd": mdd_pct(nav),
            "sharpe": sharpe_of(r, 12.0), "n": len(r)}


def run_ho2(S: dict) -> dict:
    print("\n" + "=" * 92)
    print("HO2 — 擇時 vs 純減碼(同均曝常數對照;確定性,無 seed)")
    print("=" * 92)
    e_bar = float(S["e"].mean())
    D = len(S["rA"])
    e_flat_prev = np.concatenate([[1.0], np.full(D - 1, e_bar)])   # e_prev(1)=1.0
    r_flat = (e_bar * S["rA"] + (1 - e_bar) * R_CASH_D
              - np.abs(e_bar - e_flat_prev) * DERISK_COST)
    print(f"\n常數曝險 ē = {e_bar:.4f}(僅首日扣 |ē−1|·{DERISK_COST} = "
          f"{abs(e_bar-1)*DERISK_COST:.4f}%)")
    print(f"\n{'':<34}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'日數':>8}")
    m_ac = show_daily("A×C(實際擇時)", S["r_ac"])
    m_fl = show_daily(f"A×ē(常數 {e_bar:.3f},同均曝)", r_flat)
    dd_ac, dd_fl = abs(m_ac["mdd"]), abs(m_fl["mdd"])
    gap, dcagr = dd_fl - dd_ac, m_ac["cagr"] - m_fl["cagr"]
    ok_dd = gap >= HO2_DD_GAP
    ok_cg = dcagr >= -HO2_CAGR_TOL
    ok = ok_dd and ok_cg
    print(f"\nHO2-a dd_flat − dd_AC = {dd_fl:.2f} − {dd_ac:.2f} = {gap:+.2f}pp "
          f"≥ {HO2_DD_GAP}pp → {'✅' if ok_dd else '❌'}")
    print(f"HO2-b CAGR_AC − CAGR_flat = {dcagr:+.2f}pp ≥ −{HO2_CAGR_TOL}pp → "
          f"{'✅' if ok_cg else '❌'}")
    print(f"HO2 → {'✅通過' if ok else '❌否定'}"
          + ("" if ok else "  → §4 出口 3:MDD 改善無法與『純減碼』區分,不得宣稱相位對齊 alpha。"))
    return {"ho2": ok, "e_bar": e_bar, "gap": gap}


def run_ho3(S: dict) -> dict:
    print("\n" + "=" * 92)
    print(f"HO3 — 相位對齊虛無(固定 e_lim/成本,只旋轉 r_A;B={HO3_B}, seed={HO3_SEED})")
    print("=" * 92)
    rA, e_full = S["rA"], S["e_full"]
    D = len(rA)
    e, e_prev = e_full[1:], e_full[:-1]
    base = (1.0 - e) * R_CASH_D - np.abs(e - e_prev) * DERISK_COST   # 與 τ 無關(成本恆定)
    tv_cost = float(np.abs(e - e_prev).sum() * DERISK_COST)
    dd_real = abs(mdd_pct(nav_of(S["r_ac"])))
    rng = np.random.default_rng(HO3_SEED)
    taus = rng.integers(1, D, size=HO3_B)
    dd = np.empty(HO3_B)
    t0 = time.time()
    for b in range(HO3_B):
        rot = np.roll(rA, -int(taus[b]))          # r_A^τ(d) = r_A(((d−1+τ) mod D)+1)
        dd[b] = abs(mdd_pct(nav_of(e * rot + base)))
        if b % 250 == 0:
            print(f"  {b}/{HO3_B} ({time.time()-t0:.0f}s)", flush=True)
    p = float((1 + np.sum(dd <= dd_real)) / (HO3_B + 1))
    ok = p < HO3_ALPHA
    print(f"\n  不變量自檢:overlay 換手成本 Σ|Δe|·{DERISK_COST} = {tv_cost:.4f}%(對所有 τ 相同)")
    print(f"  虛無 |MDD| 分布:p5 {np.percentile(dd,5):.2f}  中位 {np.median(dd):.2f}  "
          f"p95 {np.percentile(dd,95):.2f}")
    print(f"  實際 |MDD| {dd_real:.2f}  → p = (1+{int(np.sum(dd<=dd_real))})/({HO3_B}+1) = {p:.4f}")
    print(f"HO3 → {'✅通過' if ok else '❌否定'}(門檻 p<{HO3_ALPHA})")
    print("  ⚠ 本檢定只檢定 e_lim 與 r_A 的**對齊相位**,不主張一般性隨機擇時。")
    return {"ho3": ok, "p": p, "dd_real": dd_real}


def run_ho4(body: BodyDaily) -> dict:
    print("\n" + "=" * 92)
    print(f"HO4 — 滑價({H4_SLIP}% 來回)與時代穩健;a=硬門檻、b=描述性")
    print("=" * 92)
    body4 = body.with_slip(H4_SLIP)
    S4 = build_series(body4, "oos")
    print(f"\n{'':<34}{'CAGR%':>9}{'夏普':>8}{'MDD%':>9}{'日數':>8}")
    m = show_daily(f"A×C @滑價 {H4_SLIP}%", S4["r_ac"])
    ok_a = (abs(m["mdd"]) <= MDD_GATE) and (m["cagr"] >= CAGR_GATE)
    print(f"\nHO4a |MDD| {abs(m['mdd']):.2f}% ≤ {MDD_GATE}% 且 CAGR {m['cagr']:.2f}% ≥ "
          f"{CAGR_GATE}% → {'✅通過' if ok_a else '❌否定(§4 出口 5:不可部署)'}")

    # HO4b:全期六時代(描述性;含 in-sample 段)
    Sf = build_series(body4, "full")
    print(f"\n六時代(全期日 NAV;描述性,不單獨否定)")
    print(f"{'時代':<20}{'MDD%':>9}{'≤40%':>8}")
    dts = np.array([str(x)[:10] for x in Sf["dates"]])
    npass, stress_ok = 0, {}
    for name, s, e_ in ERAS:
        sel = (dts >= s) & (dts <= e_)
        if sel.sum() < 20:
            print(f"{name:<20}{'—':>9}{'—':>8}")
            continue
        md = mdd_pct(nav_of(Sf["r_ac"][sel]))
        good = abs(md) <= MDD_GATE
        npass += bool(good)
        stress_ok[name] = good
        print(f"{name:<20}{md:>9.2f}{'✅' if good else '❌':>8}")
    ok_stress = all(stress_ok.get(k, False) for k in HO4B_STRESS)
    ok_b = (npass >= HO4B_MIN_PASS) and ok_stress
    print(f"\nHO4b 達標 {npass}/6(門檻 ≥{HO4B_MIN_PASS})、壓力段 "
          f"{'皆達標' if ok_stress else '未全達標'} → {'✅通過' if ok_b else '❌未過'}")
    if not ok_b:
        print("  → 記錄部署風險 + 須人為明示豁免(不單獨翻掉部署決定);壓力段未達標須在 §7 顯著標記。")
    return {"ho4a": ok_a, "ho4b": ok_b}


# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(
        description="P-Overlay-C runner(門檻已凍結,本檔不提供調參旗標)")
    ap.add_argument("--part", default="preflight",
                    choices=["preflight", "verify", "ho1", "ho2", "ho3", "ho4", "all"])
    a = ap.parse_args()
    _assert_frozen()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"建面板…(本體 A = dual100 月頻,真身面板涵蓋 ADV≥{ADV_FLOOR:,.0f})", flush=True)
    P = Panel(realbody_floor=ADV_FLOOR)
    M = dual_confirm_mask(P, TARGET_TIER, top_pct=TOP_PCT, source="real")
    body = BodyDaily(P, M)
    S = build_series(body, "oos")
    print(f"面板 {P.T} 月 × {P.S} 檔;本體日序列 {len(body.r_daily)} 日"
          f"(OOS {len(S['rA'])} 日) ({time.time()-t0:.0f}s)")

    preflight(body, S)          # ← fail-closed;所有 --part 無條件執行,不可繞過

    if a.part == "preflight":
        # 只做「接線與資料對得起來」的確認,**不輸出任何 A×C 結果、不做 HO 判定**。
        print("\n--part preflight 結束:未輸出任何 A×C 績效數字、未做 HO1–HO4 判定。")
        print(f"總耗時 {time.time()-t0:.0f}s")
        return

    res = {}
    if a.part in ("verify", "all"):
        run_verify(body, S)
    if a.part in ("ho1", "all"):
        res.update(run_ho1(S, body))
    if a.part in ("ho2", "all"):
        res.update(run_ho2(S))
    if a.part in ("ho3", "all"):
        res.update(run_ho3(S))
    if a.part in ("ho4", "all"):
        res.update(run_ho4(body))

    if a.part == "all":
        print("\n" + "=" * 92)
        print("預註冊 P-Overlay-C 判定總表")
        print("=" * 92)
        for k, lab in [("ho1", "HO1  部署門檻(主)"), ("ho2", "HO2  擇時 vs 純減碼"),
                       ("ho3", "HO3  相位對齊虛無"), ("ho4a", "HO4a 滑價0.60%(硬)"),
                       ("ho4b", "HO4b 六時代(描述性)")]:
            v = res.get(k)
            print(f"{lab:<28}{'✅通過' if v else '❌否定' if v is not None else '—'}")
        hard = bool(res.get("ho1")) and bool(res.get("ho4a"))
        print(f"\n**部署硬門檻(HO1 AND HO4a)** → {'✅通過' if hard else '❌未過'}")
        print("結果(不論正負)請寫入 docs/預註冊_ExposureOverlay.md §7 與 docs/開發日誌_DevLog.md。")
        print("⚠ 通過 ≠ 可上線:月頻 dual100 的 A/B 實盤 SOP 仍須另案預註冊,且須先小額活體演練。")
    print(f"\n總耗時 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
