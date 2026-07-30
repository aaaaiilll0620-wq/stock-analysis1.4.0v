"""build_research_base.py — 研究面板 obs_alpha.parquet 的唯一權威建置入口 (可重現 + 可稽核)
================================================================================
為什麼有這支:
  `data/research_base/obs_alpha.parquet` 是 beat_0050 引擎與全部 scripts/*_lab.py 的
  單一資料源頭,但它的建置指令長期只散落在 `scripts/lab_paths.py` 的檔頭註解,
  而且被拆成兩支腳本、兩道 CLI、四個非預設參數。2026-07-29 的 High52Lab 確認性檢定
  因此無法稽核 `fwd` 以外的欄位有沒有未來函數 (見 docs/預註冊_High52Lab.md §244)。

  本檔把那條指令鏈固化成單一入口,並附上 37 欄的完整欄位字典與未來函數稽核結論。
  **本檔不重寫任何因子計算**:stage1/stage2 都是直接 import 既有腳本的函式,
  確保「重建 = 原始產物」逐欄 bitwise 相同 (--verify 會實測這件事)。

--------------------------------------------------------------------------------
建置鏈 (兩階段)
--------------------------------------------------------------------------------
  stage1  scripts/tej_universe_screen_validation.py :: build_observations()
          讀 ~/tej_cache (price_valuation / institutional_flow /
          fundamentals_quarterly / revenue_growth) → obs_dump_full.parquet
          月度 rebalance 日 (每月最後交易日) × 全市場個股,17 欄。

  stage2  scripts/alpha_gate_lab.py :: build()
          讀 obs_dump_full.parquet + ~/tej_cache (price_valuation /
          industry_map / institutional_flow / tdcc_weekly / director_pledge)
          → obs_alpha.parquet,增補 20 欄,共 37 欄。

  等價的原始手動指令 (lab_paths.py 檔頭記載者):
    python scripts/tej_universe_screen_validation.py --dump-obs <path> \
        --dump-start 2005-01-01 --dump-end 2026-12-31
    python scripts/alpha_gate_lab.py --build

--------------------------------------------------------------------------------
凍結參數 (現行 obs_alpha.parquet 2026-07-19 產物即此組;改動請改這裡並重跑全鏈)
--------------------------------------------------------------------------------
  DUMP_START/END      2005-01-01 / 2026-12-31    實得 2005-01-31 ~ 2026-05-29,257 期
  HOLDING_DAYS        20 交易日                   fwd 的前瞻窗
  MOMENTUM_WINDOW     20 交易日
  CHIP_WINDOW         20 交易日
  CHIP_MODE           turnover                    淨買超 ÷ 同期成交量 (市值中性化)
  QUARTERLY_LAG       45 天  (季報公告延遲)        tej_universe_screen_validation.py:57
  MONTHLY_LAG         10 天  (月營收公告延遲)      tej_universe_screen_validation.py:58
  TDCC_LAG            4 天   (集保公布延遲)        alpha_gate_lab.py:37
  PLEDGE_LAG          15 天  (董監月報公布延遲)    alpha_gate_lab.py:38
  ADV_FLOOR           10,000,000 (L1 池門檻,只在讀取端過濾,不影響本檔輸出列數)

--------------------------------------------------------------------------------
欄位字典 —— 37 欄 (S1 = stage1 產出, S2 = stage2 增補)
「窗口」欄的 T 表示 trailing (只用 as_of 當日與更早的資料);F 表示前瞻 (未來資料)。
--------------------------------------------------------------------------------
 #  欄位                  階段  窗口  定義與來源
--  --------------------  ----  ----  --------------------------------------------
 1  as_of                 S1    —     評估日 = 該月最後一個交易日 (rebalance_dates)
 2  stock_id              S1    —     TEJ 股票代號
 3  value                 S1    T     100 − PE 歷史分位。分位 = 自資料起點至 as_of 的
                                      expanding window 內 PER_TEJ<現值 的比例 ×100;
                                      排除 PE<=0,樣本<60 日整列丟棄。愈高=愈便宜。
 4  momentum              S1    T     (close[i0] / close[i0−20] − 1) × 100
 5  chip                  S1    T     近 20 交易日 (外資+投信+自營) 淨買超合計
                                      ÷ 同期成交量合計 (turnover 模式)
 6  fwd                   S1    **F** (close[i0+20] / close[i0] − 1) × 100
                                      ★ 唯一且刻意的前瞻欄 = 被解釋變數 (label)。
                                      ★ close→close,不可執行;對高換手 arm 高估
                                        約 5.6pp/年 → 見 docs/預註冊_High52Lab.md。
                                        報酬評估請改用 exec_ret 的 open→open 線。
 7  eps                   S1    T     單季 EPS。PIT: known_date = 季末月底+45d,
                                      merge_asof(direction="backward")。2019 前無資料。
 8  roe                   S1    T     單季稅後 ROE,同上 PIT 機制。2019 前無資料。
 9  revenue_yoy           S1    T     月營收 YoY %。PIT: known_date = 當月月底+10d,
                                      merge_asof(backward)。2005+ 覆蓋率 >99%。
10  op_income             S1    T     單季營業利益,同 eps 的 PIT。2019 前無資料。
11  net_income            S1    T     單季稅後淨利,同 eps 的 PIT。2019 前無資料。
12  mom60                 S1    T     (close[i0] / close[i0−60] − 1) × 100
13  mom120                S1    T     (close[i0] / close[i0−120] − 1) × 100
14  high52_prox           S1    T     close[i0] / rolling(240, min_periods=120).max()
                                      × 100。pandas rolling 窗口以當列為右端點,
                                      故含當日、不含未來 → 值域上限恰為 100。
15  eps_pos_q4            S1    T     最近 4 個「已公佈」單季中 EPS>0 的季數 (0-4)。
                                      rolling(4) 跑在依 known_date 排序的財報序列上。
16  rev_yoy_3m            S1    T     最近 3 個「已公佈」月份 revenue_yoy 的均值。
                                      rolling(3) 跑在依 known_date 排序的營收序列上。
17  period                S1    —     dump 區間標籤;本組全量重建一律為 "custom"。
18  adv20                 S2    T     AVG(close×Trading_Volume) OVER (
                                        ORDER BY date ROWS BETWEEN 19 PRECEDING
                                        AND CURRENT ROW) —— DuckDB 視窗,明確 trailing。
19  listed_ok             S2    T     上市滿一年旗標。first_date = MIN(date) OVER
                                      (PARTITION BY stock_id);min 必 ≤ as_of,非前瞻。
20  tej_ind_name          S2    ~     TEJ 產業別,來自 industry_map.parquet。
                                      ⚠ 這是「當前」快照、無歷史版本,等於把今日的
                                        產業分類套回全歷史。產業重分類的個股會有輕微
                                        時代錯置 (非典型未來函數,但非嚴格 PIT)。
21  rev_accel             S2    T     revenue_yoy − rev_yoy_3m (兩者皆 trailing)
22  value_ind             S2    T     value 在 (as_of × 產業) 內的百分位 ×100;
                                      該產業當期樣本<5 檔則退回全市場百分位。
                                      純同日橫斷面運算,不跨期 → 無前瞻。
23  rsi14                 S2    T     RSI14 (Wilder 近似:14 日簡單均);rolling(14)
24  bbp20                 S2    T     布林 %B:(close−(ma20−2sd20)) / (4sd20);rolling(20)
25  ma_gap60              S2    T     close / rolling(60).mean() − 1
26  vol60                 S2    T     日報酬 rolling(60, min_periods=40).std()
27  chip5                 S2    T     近 5 日淨買超和 ÷ 近 5 日成交量和
28  chip10                S2    T     近 10 日,同上
29  chip60                S2    T     近 60 日,同上
30  chip_accel            S2    T     chip5 − chip20 (chip20 為中間量,未輸出)
31  ratio_1000up          S2    T     千張大戶持股比。PIT: known_date = 集保資料日+4d,
                                      merge_asof(backward, tolerance=60d)。2019 起有值。
32  big_d4w               S2    T     ratio_1000up − shift(4 週),同上 PIT
33  big_d12w              S2    T     ratio_1000up − shift(12 週),同上 PIT
34  holders_chg12w        S2    T     holders / shift(12 週) − 1,同上 PIT
35  pledge_pct            S2    T     董監質押比。PIT: known_date = 月底+15d,
                                      merge_asof(backward, tolerance=90d)。2019 起有值。
36  pledge_d3m            S2    T     pledge_pct − shift(3 月),同上 PIT
37  director_holding_pct  S2    T     董監持股比,同上 PIT

--------------------------------------------------------------------------------
未來函數稽核結論 (2026-07-29)
--------------------------------------------------------------------------------
  · 36/37 欄為 trailing。唯一前瞻欄是 `fwd`,且它是刻意的被解釋變數,不是特徵。
  · 所有低頻資料 (季報/月營收/集保/質押) 一律先換算 known_date = 期間結束 + 公告
    延遲,再以 merge_asof(direction="backward") 對齊 → 結構上不可能取到未公佈值。
  · 所有價量衍生欄一律用 pandas/DuckDB 的 trailing rolling 視窗 (右端點 = 當列),
    無 center=True、無負向 shift。
  · value 用 expanding 到 i0 (含當日) 的自身 PE 歷史,不用全期分位 → 無前瞻。
  · value_ind 為同日橫斷面排名,不跨期 → 無前瞻。
  · ⚠ 唯一發現的真實瑕疵 —— 季報 45 天固定延遲對 Q4 過於樂觀:
      QUARTERLY_ANNOUNCE_LAG_DAYS 是單一常數 45,套到四個季別的結果是
        Q1 期末3/31 → 5/15 ✔ (法定期限 5/15)
        Q2 期末6/30 → 8/14 ✔ (法定期限 8/14)
        Q3 期末9/30 → 11/14 ✔ (法定期限 11/14)
        Q4 期末12/31 → **2/14** ✘ (台灣年報法定期限為隔年 **3/31**)
      → 每年 2/14~3/30 之間的 as_of 會掛上「當時可能尚未公告」的 Q4 財報。
      影響欄位:eps / roe / op_income / net_income / eps_pos_q4 (皆 2019+ 才有值)。
      影響幅度 (實測):8 個 as_of (2020-02-27, 2021-02-26, 2022-02-25, 2023-02-24,
      2024-02-29, 2024-03-29, 2025-02-27, 2026-02-26),11,053 列 = 全panel 3.67%。
      不影響 value / value_ind / momentum / high52_prox / revenue_yoy / adv20 / fwd
      —— 亦即不影響生產 5F、C1、C2;只影響用到 roe 的 C3/C4。
      ★ 注意:--pit-test 抓不到這一項。截斷測試比對的是「同一套延遲假設」下的
        兩次計算,假設本身錯了兩邊會一起錯。這是讀 code 讀出來的,不是跑出來的。

  · 已知非前瞻但需記錄的限制:
      (a) tej_ind_name 是當前產業快照套回全歷史 (見 #20)。
      (b) eps/roe/op_income/net_income/eps_pos_q4 在 2019 前全為 NaN
          (~61% 整體缺值),因 tej_cache/fundamentals_quarterly 只從 2019 起。
          2005-2018 財報在 tej_cache/financial_statements/,本鏈並未讀取。
          → 任何用到 roe 的組合分在 hold-out 2005-2018 不可測 (alpha_gate_lab
            的 C3h「可測變體」已因此刻意拿掉 roe)。
      (c) 母體只含 tej_cache 現存個股 → 已下市個股若不在快取即有存活者偏誤。
      (d) fwd 的 close→close 不可執行 (見 #6)。

--------------------------------------------------------------------------------
用法
--------------------------------------------------------------------------------
  python scripts/build_research_base.py --audit    # 只印欄位字典/稽核表,不算
  python scripts/build_research_base.py --stage1   # 重建 obs_dump_full.parquet (慢)
  python scripts/build_research_base.py --stage2   # 重建 obs_alpha.parquet (數分鐘)
  python scripts/build_research_base.py --all      # 全鏈重建
  python scripts/build_research_base.py --verify           # 重建到暫存並逐欄對帳
  python scripts/build_research_base.py --verify --stage2  # 只對帳 stage2 的 20 欄
  python scripts/build_research_base.py --pit-test 2012-06-29,2021-06-30
                                                   # 未來函數決定性稽核 (見下)

  --verify 與 --pit-test 的差別很重要:
    --verify   證明「本檔的重建 = 現有 parquet」→ 面板可重現、建置鏈確為此二腳本。
    --pit-test 證明「把輸入砍到 as_of 就沒有任何欄位會變」→ 面板無未來函數。
    前者防的是「不知道怎麼生出來的」,後者防的是「生錯了」。兩個都要過。
================================================================================
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lab_paths import OBS_DUMP_FULL, OBS_ALPHA, RESEARCH_BASE   # noqa: E402

# ---- 凍結參數 (見檔頭「凍結參數」段) ------------------------------------------
DUMP_START = "2005-01-01"
DUMP_END = "2026-12-31"
HOLDING_DAYS = 20
MOMENTUM_WINDOW = 20
CHIP_WINDOW = 20
CHIP_MODE = "turnover"

# 逐欄對帳的容差:同碼同輸入應 bitwise 相同,容差只用來吸收 parquet 往返的浮點噪音。
ATOL = 1e-9
RTOL = 1e-9

STAGE1_COLS = ["value", "momentum", "chip", "fwd", "eps", "roe", "revenue_yoy",
               "op_income", "net_income", "mom60", "mom120", "high52_prox",
               "eps_pos_q4", "rev_yoy_3m", "period"]
STAGE2_COLS = ["adv20", "listed_ok", "tej_ind_name", "rev_accel", "value_ind",
               "rsi14", "bbp20", "ma_gap60", "vol60", "chip5", "chip10", "chip60",
               "chip_accel", "ratio_1000up", "big_d4w", "big_d12w", "holders_chg12w",
               "pledge_pct", "pledge_d3m", "director_holding_pct"]
KEY = ["as_of", "stock_id"]

# 預註冊要求的最低對帳欄位 (docs/預註冊_High52Lab.md 稽核缺口)
REQUIRED_RECON = ["high52_prox", "momentum", "value_ind", "revenue_yoy", "adv20", "fwd"]


# ------------------------------------------------------------------------------
# stage1 — 直接呼叫 tej_universe_screen_validation 的函式 (不重寫因子)
# ------------------------------------------------------------------------------
def build_stage1(out_path: Path, cache_dir: Path = None,
                 start: str = DUMP_START, end: str = DUMP_END,
                 holding: int = HOLDING_DAYS) -> Path:
    import tej_universe_screen_validation as v

    cache_dir = Path(cache_dir) if cache_dir else v.TEJ_CACHE_DIR
    print(f"[stage1] 讀 tej_cache 全市場快取 (DuckDB)… cache={cache_dir}")
    price, chip, fund, rev = v.load_market(cache_dir)
    print(f"[stage1]   price_valuation      {len(price):>9,} 列 / {price['stock_id'].nunique()} 檔")
    print(f"[stage1]   institutional_flow   {len(chip):>9,} 列 / {chip['stock_id'].nunique()} 檔")
    print(f"[stage1]   fundamentals_quarterly {len(fund):>7,} 列 / {fund['stock_id'].nunique()} 檔")
    print(f"[stage1]   revenue_growth       {len(rev):>9,} 列 / {rev['stock_id'].nunique()} 檔")

    all_dates = price["date"].unique().tolist()
    dates = v.rebalance_dates(all_dates, start, end, "M")
    if not dates:
        raise SystemExit(f"[stage1] 區間 {start}~{end} 內無 rebalance 日")
    print(f"[stage1] rebalance 日 {len(dates)} 期 ({dates[0]} ~ {dates[-1]});"
          f"holding={holding};逐股迴圈開始…")

    obs = v.build_observations(price, chip, dates, holding, MOMENTUM_WINDOW,
                               CHIP_WINDOW, CHIP_MODE,
                               fund=fund, rev=rev, quality_filter="none")
    df = pd.DataFrame(obs)
    df["period"] = "custom"          # 對齊原始 --dump-start/--dump-end 的單一區間標籤
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"[stage1] 已輸出 {len(df):,} 列 × {df.shape[1]} 欄 → {out_path}")
    return out_path


# ------------------------------------------------------------------------------
# stage2 — 直接呼叫 alpha_gate_lab.build() (改導 module 級輸入/輸出路徑)
# ------------------------------------------------------------------------------
def build_stage2(src_path: Path, out_path: Path, cache_dir: Path = None) -> Path:
    import alpha_gate_lab as agl

    prev_src, prev_out, prev_tej = agl.OBS_SRC, agl.OBS_OUT, agl.TEJ
    agl.OBS_SRC, agl.OBS_OUT = Path(src_path), Path(out_path)
    if cache_dir:
        agl.TEJ = Path(cache_dir)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[stage2] src={src_path}\n[stage2] out={out_path}\n[stage2] tej={agl.TEJ}")
        agl.build()
    finally:
        agl.OBS_SRC, agl.OBS_OUT, agl.TEJ = prev_src, prev_out, prev_tej
    return out_path


# ------------------------------------------------------------------------------
# PIT 截斷測試 —— 未來函數的決定性稽核
# ------------------------------------------------------------------------------
#  對帳 (--verify) 只證明「可重現」,不證明「無未來函數」:同一份程式跑兩次,
#  就算它偷看未來,兩次也會偷看得一模一樣。
#
#  本測試改問一個不同的問題:把所有輸入資料硬砍到 as_of 當日為止 (之後一列都不留),
#  重跑全鏈,如果某欄真的只用 trailing 資料,它必須逐位元重現全量面板的值;
#  只要有任何一欄用到 as_of 之後的資料,砍掉之後就一定會變 (或變 NaN)。
#
#  技術點:build_observations 在 fwd 取不到 (i0+holding 超出資料尾端) 時會整列丟棄,
#  硬截斷會導致零列。故本測試用 holding=0 (fwd 恆等於 0,不需要任何未來價格),
#  讓非 fwd 欄位仍能產生 —— 這正好也順帶證明 fwd 是唯一需要未來資料的欄位。
# ------------------------------------------------------------------------------
PIT_DATASETS = ["price_valuation", "institutional_flow", "fundamentals_quarterly",
                "revenue_growth", "tdcc_weekly", "director_pledge"]


def make_pit_cache(cutoff: str, dest: Path, src_cache: Path) -> Path:
    """把 tej_cache 各資料集硬砍到 date <= cutoff,複製成一份獨立快取。"""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cutoff):
        raise SystemExit(f"[pit] cutoff 需為 YYYY-MM-DD,收到 {cutoff!r}")
    dest.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for ds in PIT_DATASETS:
        (dest / ds).mkdir(parents=True, exist_ok=True)
        out = dest / ds / "all.parquet"
        # 路徑由本機 Path 組出 (非外部輸入);cutoff 一律走參數綁定。
        glob = (src_cache / ds / "*.parquet").as_posix()
        res = con.execute(
            "SELECT * FROM read_parquet(?, union_by_name=true) "
            "WHERE CAST(date AS VARCHAR) <= ?", [glob, cutoff])
        # duckdb >=1.4 用 to_arrow_table();舊版只有 fetch_arrow_table()
        tbl = (res.to_arrow_table() if hasattr(res, "to_arrow_table")
               else res.fetch_arrow_table())
        # 必須經 Arrow 落地、不能走 pandas.to_parquet:
        # 截斷點早於某資料集的起始日時 (如 2008 之於 2019 才有的 TDCC/質押/財報),
        # 結果是空表,而 pandas 會把空的 object 欄寫成 parquet 的 null 型別,
        # DuckDB 再讀回來會變成 int32 → alpha_gate_lab 的 merge_asof(by="stock_id")
        # 會因左右型別不符而炸掉。Arrow 落地可原樣保留來源 schema。
        pq.write_table(tbl, out)
        print(f"[pit] {ds:<24} 截斷至 <= {cutoff}:{tbl.num_rows:>10,} 列"
              f"{'  (空表:該資料集起始日晚於截斷點)' if tbl.num_rows == 0 else ''}")
    con.close()
    # industry_map 無 date 欄 (靜態快照,見檔頭欄位字典 #20 的已知限制),原樣複製
    shutil.copy(src_cache / "industry_map.parquet", dest / "industry_map.parquet")
    return dest


def pit_test(as_of: str, work: Path) -> bool:
    import tej_universe_screen_validation as v

    src_cache = v.TEJ_CACHE_DIR
    pit_cache = work / f"pit_cache_{as_of}"
    s1 = work / f"pit_s1_{as_of}.parquet"
    s2 = work / f"pit_s2_{as_of}.parquet"

    print("\n" + "=" * 92)
    print(f"PIT 截斷測試 — as_of = {as_of}")
    print(f"  輸入資料硬砍到 <= {as_of},重跑全鏈,與全量面板同日逐欄比對")
    print("=" * 92)

    make_pit_cache(as_of, pit_cache, src_cache)
    build_stage1(s1, cache_dir=pit_cache, start=as_of, end=as_of, holding=0)

    old = pd.read_parquet(OBS_ALPHA)
    old = old[old["as_of"].astype(str) == as_of].copy()
    old["stock_id"] = old["stock_id"].astype(str)

    # 母體對齊:全量面板會丟掉「as_of 之後湊不滿 20 交易日」的個股 (下市/停牌),
    # PIT 版 holding=0 不受此限,母體會是超集。這個差異純粹來自 fwd 的前瞻需求,
    # 與因子是否偷看未來無關;但 value_ind 是同日橫斷面排名,母體變大會連帶改變它。
    # 故先把 stage1 產物砍到與全量面板同一組 stock_id,再跑 stage2,
    # 才不會把「母體組成差異」誤判成「未來函數」。
    d1 = pd.read_parquet(s1)
    d1["stock_id"] = d1["stock_id"].astype(str)
    keep = set(old["stock_id"])
    extra = sorted(set(d1["stock_id"]) - keep)
    d1 = d1[d1["stock_id"].isin(keep)].reset_index(drop=True)
    d1.to_parquet(s1, index=False)
    print(f"[pit] 母體對齊:PIT stage1 額外多出 {len(extra)} 檔 (全量面板因 fwd 湊不滿而丟棄),"
          f"已剔除後再跑 stage2;對齊後 {len(d1):,} 列")

    build_stage2(s1, s2, cache_dir=pit_cache)

    new = pd.read_parquet(s2)
    print(f"\n全量面板該日 {len(old):,} 列;PIT 重建 {len(new):,} 列")

    for df in (old, new):
        df["as_of"] = df["as_of"].astype(str)
        df["stock_id"] = df["stock_id"].astype(str)
    o = old.set_index(KEY).sort_index()
    n = new.set_index(KEY).sort_index()
    idx = o.index.intersection(n.index)
    only_old, only_new = len(o.index.difference(n.index)), len(n.index.difference(o.index))
    print(f"共同 key {len(idx):,};僅全量 {only_old:,};僅 PIT {only_new:,}")
    o, n = o.loc[idx], n.loc[idx]

    # fwd 預期不同 (PIT 版 holding=0 → 恆 0);period 是標籤欄。兩者排除在判定外。
    cols = [c for c in STAGE1_COLS + STAGE2_COLS if c not in ("fwd", "period")]
    print(f"\n{'欄位':<22}{'比對數':>10}{'NaN不符':>9}{'最大絕對差':>13}{'超容差':>8}  判定")
    print("-" * 92)
    all_ok = True
    for c in cols:
        r = _cmp_column(o[c], n[c])
        ok = (r["nan_mismatch"] == 0 and r["n_exceed"] == 0)
        all_ok &= ok
        mad = "n/a" if (isinstance(r["max_abs_diff"], float) and np.isnan(r["max_abs_diff"])) \
            else f"{r['max_abs_diff']:.3e}"
        star = " ★" if c in REQUIRED_RECON else ""
        print(f"{c:<22}{r['n_cmp']:>10,}{r['nan_mismatch']:>9,}{mad:>13}"
              f"{r['n_exceed']:>8,}  {'一致' if ok else '不一致'}{star}")

    print("-" * 92)
    print(f"fwd (排除在判定外):全量面板該日 |fwd| 總和 = {float(o['fwd'].abs().sum()):,.1f};"
          f"PIT 版 holding=0 → 恆 0 (需 as_of 之後的價格才算得出來)")
    print(f"\n結論:{'截斷後全部非 fwd 欄位完全重現 → 無未來函數 ✔' if all_ok else '有欄位在截斷後改變 → 疑似未來函數 ✘'}")
    return all_ok


# ------------------------------------------------------------------------------
# 逐欄對帳
# ------------------------------------------------------------------------------
def _cmp_column(a: pd.Series, b: pd.Series) -> dict:
    """回傳單欄對帳統計。a=現有 (old), b=重建 (new),已對齊同一組 key。"""
    na, nb = a.isna(), b.isna()
    nan_mismatch = int((na ^ nb).sum())
    both_ok = ~na & ~nb
    n_cmp = int(both_ok.sum())
    res = {"n_cmp": n_cmp, "nan_mismatch": nan_mismatch,
           "max_abs_diff": np.nan, "n_exceed": 0, "corr": np.nan}
    if n_cmp == 0:
        return res
    x, y = a[both_ok], b[both_ok]
    if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
        xf, yf = x.astype("float64"), y.astype("float64")
        d = (xf - yf).abs()
        res["max_abs_diff"] = float(d.max())
        res["n_exceed"] = int((d > (ATOL + RTOL * yf.abs())).sum())
        if xf.std() > 0 and yf.std() > 0:
            res["corr"] = float(np.corrcoef(xf, yf)[0, 1])
    else:                                    # 字串/布林欄:直接比相等
        neq = (x.astype(str) != y.astype(str))
        res["max_abs_diff"] = float(neq.sum())
        res["n_exceed"] = int(neq.sum())
        res["corr"] = 1.0 if neq.sum() == 0 else np.nan
    return res


def reconcile(old_path: Path, new_path: Path, cols: list, label: str) -> bool:
    print("\n" + "=" * 92)
    print(f"逐欄對帳 — {label}")
    print(f"  現有 (old): {old_path}")
    print(f"  重建 (new): {new_path}")
    print("=" * 92)
    old = pd.read_parquet(old_path)
    new = pd.read_parquet(new_path)

    for df in (old, new):
        df["as_of"] = df["as_of"].astype(str)
        df["stock_id"] = df["stock_id"].astype(str)

    ko = set(map(tuple, old[KEY].values))
    kn = set(map(tuple, new[KEY].values))
    only_old, only_new, common = ko - kn, kn - ko, ko & kn
    print(f"\n列數:old {len(old):,} / new {len(new):,};"
          f"共同 key {len(common):,};僅 old {len(only_old):,};僅 new {len(only_new):,}")
    if only_old or only_new:
        print("  ⚠ key 集合不一致 —— 下方逐欄統計只跑共同 key。")
        for tag, s in (("僅old", only_old), ("僅new", only_new)):
            if s:
                ds = sorted({d for d, _ in s})
                print(f"    {tag} 涉及 {len(ds)} 個 as_of,例:{ds[:5]}")

    o = old.set_index(KEY).sort_index()
    n = new.set_index(KEY).sort_index()
    idx = o.index.intersection(n.index)
    o, n = o.loc[idx], n.loc[idx]

    print(f"\n{'欄位':<22}{'比對數':>10}{'NaN不符':>9}{'最大絕對差':>13}{'超容差':>8}{'相關':>9}  判定")
    print("-" * 92)
    all_ok = True
    missing = []
    for c in cols:
        if c not in o.columns or c not in n.columns:
            missing.append(c)
            print(f"{c:<22}{'—— 欄位不存在於 old/new ——':>50}")
            all_ok = False
            continue
        r = _cmp_column(o[c], n[c])
        ok = (r["nan_mismatch"] == 0 and r["n_exceed"] == 0)
        all_ok &= ok
        mad = "n/a" if (isinstance(r["max_abs_diff"], float) and np.isnan(r["max_abs_diff"])) \
            else f"{r['max_abs_diff']:.3e}"
        corr = "n/a" if (isinstance(r["corr"], float) and np.isnan(r["corr"])) else f"{r['corr']:.6f}"
        star = " ★" if c in REQUIRED_RECON else ""
        print(f"{c:<22}{r['n_cmp']:>10,}{r['nan_mismatch']:>9,}{mad:>13}"
              f"{r['n_exceed']:>8,}{corr:>9}  {'一致' if ok else '不一致'}{star}")

    covered = [c for c in REQUIRED_RECON if c in cols]
    print("-" * 92)
    print(f"★ = 預註冊要求的最低對帳欄位;本次涵蓋 {covered}")
    print(f"\n結論:{'全部欄位一致 ✔' if all_ok else '有欄位不一致 ✘ —— 見上表'}"
          f"{'' if not missing else f';缺欄 {missing}'}")
    return all_ok


# ------------------------------------------------------------------------------
def print_audit():
    print(__doc__)


def main():
    ap = argparse.ArgumentParser(
        description="obs_alpha.parquet 權威建置入口 (兩階段鏈 + 逐欄對帳)")
    ap.add_argument("--stage1", action="store_true", help="重建 obs_dump_full.parquet")
    ap.add_argument("--stage2", action="store_true", help="重建 obs_alpha.parquet")
    ap.add_argument("--all", action="store_true", help="stage1 + stage2 全鏈")
    ap.add_argument("--verify", action="store_true",
                    help="重建到暫存路徑並與現有 parquet 逐欄對帳 (不覆蓋正式檔)")
    ap.add_argument("--audit", action="store_true", help="只印欄位字典與未來函數稽核表")
    ap.add_argument("--pit-test", default=None, metavar="YYYY-MM-DD[,YYYY-MM-DD...]",
                    help="PIT 截斷測試:輸入資料硬砍到該 as_of,重跑全鏈驗證無未來函數")
    ap.add_argument("--work-dir", default=None,
                    help="--verify/--pit-test 的暫存輸出目錄 (預設 data/research_base/_verify)")
    args = ap.parse_args()

    work = Path(args.work_dir) if args.work_dir else RESEARCH_BASE / "_verify"

    if args.audit:
        print_audit()
        return

    if args.pit_test:
        work.mkdir(parents=True, exist_ok=True)
        days = [d.strip() for d in args.pit_test.split(",") if d.strip()]
        results = {d: pit_test(d, work) for d in days}
        print("\n" + "=" * 92)
        print("PIT 截斷測試總結")
        for d, r in results.items():
            print(f"  {d}: {'無未來函數 ✔' if r else '疑似未來函數 ✘'}")
        print("=" * 92)
        sys.exit(0 if all(results.values()) else 1)

    do1 = args.stage1 or args.all
    do2 = args.stage2 or args.all
    if not (do1 or do2):
        if args.verify:
            do1 = do2 = True
        else:
            ap.print_help()
            return

    if args.verify:
        work.mkdir(parents=True, exist_ok=True)
        s1_new = work / "obs_dump_full.parquet"
        s2_new = work / "obs_alpha.parquet"
        ok = True
        if do1:
            build_stage1(s1_new)
            ok &= reconcile(OBS_DUMP_FULL, s1_new, STAGE1_COLS, "stage1 / obs_dump_full (17 欄)")
        if do2:
            # stage2 的來源:有重建過就用重建的,否則用現有 dump (單獨驗 stage2 的 20 欄)
            src = s1_new if (do1 and s1_new.exists()) else OBS_DUMP_FULL
            build_stage2(src, s2_new)
            ok &= reconcile(OBS_ALPHA, s2_new, STAGE2_COLS, "stage2 / obs_alpha 增補欄 (20 欄)")
        print("\n" + "=" * 92)
        print(f"對帳總結:{'重建可完整重現現有面板 ✔' if ok else '重建與現有面板有差異 ✘'}")
        print("=" * 92)
        sys.exit(0 if ok else 1)

    if do1:
        build_stage1(OBS_DUMP_FULL)
    if do2:
        build_stage2(OBS_DUMP_FULL, OBS_ALPHA)


if __name__ == "__main__":
    main()
