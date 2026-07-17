"""全市場掃描每日摘要 (0 API):讀 outputs/universe_pool/ 的歷史 shortlist,
產出 digest_{date}.md —— 新進排序前 N、掉出前 N、連續在榜天數、來源臂、regime 旗。
排序欄自動偵測:新檔用 c2_score (v4.6),舊檔回退 composite。
掛在 market_snapshot_collect.bat 的粗篩之後;手動跑也行。
用法: python scripts/universe_digest.py [--top 50] [--streak-min 5] [--lookback 40]
"""
import os
import glob
import argparse
from pathlib import Path

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL_DIR = Path(project_root) / "outputs" / "universe_pool"

ARMS = {"value_ind_pct_pool_pct": "便宜", "momentum20_pool_pct": "動能",
        "chip20_turnover_pool_pct": "籌碼", "high52_prox_pool_pct": "突破",
        "rev_accel_pool_pct": "營收加速"}
ARM_THR = 85.0


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"stock_id": str})
    return df.set_index("stock_id")


def arms_of(row) -> str:
    return "+".join(label for col, label in ARMS.items()
                     if col in row.index and pd.notna(row[col]) and row[col] > ARM_THR)


def md_table(df: pd.DataFrame, streaks: dict, cap: int = 10**9, extra_cols=(),
             score_col: str = "composite") -> str:
    lines = [f"| 代號 | 名稱 | 產業 | 收盤 | {score_col} | 來源臂 | 連續在榜 |" +
             ("".join(f" {c} |" for c in extra_cols)),
             "|---|---|---|---|---|---|---|" + "---|" * len(extra_cols)]
    for sid, r in df.iterrows():
        n = streaks.get(sid, 1)
        streak_txt = f"≥{n}天" if n >= cap else f"{n}天"   # 撞到回看窗上限=至少這麼多天
        lines.append(f"| {sid} | {r.get('name', '')} | {r.get('industry', '')} "
                     f"| {r.get('close', float('nan')):.1f} | {r[score_col]:.1f} "
                     f"| {arms_of(r)} | {streak_txt} |" +
                     "".join(f" {r.get(c, '')} |" for c in extra_cols))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="全市場掃描每日摘要")
    ap.add_argument("--top", type=int, default=50, help="『前 N』的 N (預設 50)")
    ap.add_argument("--streak-min", type=int, default=5, help="連續在榜亮點門檻 (天)")
    ap.add_argument("--lookback", type=int, default=40, help="回看幾個交易日算連續在榜")
    args = ap.parse_args()

    files = sorted(glob.glob(str(POOL_DIR / "shortlist_*.csv")))
    if not files:
        print("找不到任何 shortlist 檔案")
        return
    today_f = files[-1]
    date = Path(today_f).stem.replace("shortlist_", "")
    today = load(today_f)
    rc = "c2_score" if "c2_score" in today.columns else "composite"
    today = today.sort_values(rc, ascending=False)

    # 連續在榜天數 (含今天;往回掃)
    hist_sets = [set(load(f).index) for f in files[-(args.lookback + 1):]]
    streaks = {}
    for sid in today.index:
        n = 0
        for s in reversed(hist_sets):
            if sid in s:
                n += 1
            else:
                break
        streaks[sid] = n

    top_today = set(today.head(args.top).index)
    prev_top = set()
    if len(files) >= 2:
        prev = load(files[-2])
        prev_rc = "c2_score" if "c2_score" in prev.columns else "composite"
        prev = prev.sort_values(prev_rc, ascending=False)
        prev_top = set(prev.head(args.top).index)
    new_in = today.loc[[s for s in today.head(args.top).index if s not in prev_top]]
    dropped = sorted(prev_top - top_today)

    # regime 旗 (live pool 檔才有;缺欄容忍)
    pool_f = POOL_DIR / f"pool_{date}.csv"
    regime = "未知"
    if pool_f.exists():
        p = pd.read_csv(pool_f, nrows=1)
        if "bear_regime" in p.columns:
            regime = "⚠️ 空頭 (shortlist 參考性降低)" if bool(p["bear_regime"].iloc[0]) else "多頭 ✅"

    stayers = (today[[sid in streaks and streaks[sid] >= args.streak_min for sid in today.index]]
               .assign(_s=lambda d: [streaks[s] for s in d.index])
               .sort_values(["_s", rc], ascending=False).head(30))

    out = POOL_DIR / f"digest_{date}.md"
    parts = [
        f"# 全市場掃描摘要 {date}",
        f"",
        f"市場 regime:{regime}",
        f"shortlist {len(today)} 檔｜{rc} 前 {args.top}:新進 {len(new_in)} 檔、掉出 {len(dropped)} 檔",
        f"",
        f"## 🆕 新進 {rc} 前 {args.top}",
        md_table(new_in, streaks, cap=len(hist_sets), score_col=rc) if len(new_in) else "(無)",
        f"",
        f"## 🔥 連續在榜 ≥{args.streak_min} 天 (依天數排,前 30)",
        md_table(stayers.drop(columns=['_s']), streaks, cap=len(hist_sets), score_col=rc) if len(stayers) else
        f"(無;歷史檔 {len(hist_sets)} 天,榜齡會隨累積增長)",
        f"",
        f"## 📉 掉出前 {args.top}",
        ("、".join(dropped) if dropped else "(無)"),
        f"",
        f"---",
        f"*來源臂門檻=池內百分位>{ARM_THR:.0f};完整名單見 shortlist_{date}.csv;"
        f"shortlist 是分流參考不是投組,空頭段超額歷史上偏負。*",
    ]
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"摘要已輸出 {out} (新進 {len(new_in)}/掉出 {len(dropped)}/連榜亮點 {len(stayers)})")


if __name__ == "__main__":
    main()
