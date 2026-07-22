# -*- coding: utf-8 -*-
"""_template.py — 策略起手式:把一句話假設變成可驗證策略的最小骨架。
================================================================================
一支策略 = 一個「每月給每檔股票打分,取前 K 檔」的函式。你只需要改 score() 一行。

六步迴圈 (每支策略都走一遍,別跳):
  1. 假設:一句話寫下「為什麼這樣選能贏 0050?利用了什麼沒被市場消化的東西?」
  2. 預註冊:先寫死規則 + 及格門檻 (下面 THESIS / PASS_RULE),跑之前就決定,事後不准改。
  3. 打分:改 score() —— 用 obs_alpha 欄位組出你的排序分數 (這是唯一要動腦的地方)。
  4. 回測:python beat_0050/strategies/_template.py → Engine 給你六時代淨夏普 vs 0050。
  5. 判定:只看樣本外時代 (2022 空頭 + 2023-26 是最誠實的試金石),不是全期擬合。
  6. 殺或留:多數點子會死,這是正常的。死得快 = 省時間。

⚠️ 鐵律:fwd 是「答案」(未來 20 日報酬),**絕對不能拿來當 score 的輸入**,否則是作弊(未來函數)。
================================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from beat_0050.honest_backtest import Engine, OBS_ALPHA

# ── 步驟 1-2:預註冊 (跑之前填好,別事後改) ──────────────────────────────────
THESIS = "低波動股長期夏普較高(低波動異常),用它贏 0050 的分母"   # 你的一句話假設
TOP_K = 20                                                        # 每月持有檔數 (小資金別太多)
ADV_FLOOR = 2e7                                                   # 流動性下限,濾掉買不進的
PASS_RULE = "樣本外(2022+2023-26)淨夏普 > 0050 同窗,且 2022 不為負"   # 及格門檻

# ── 可用訊號選單 (obs_alpha 37 欄,依論點分組;挑幾個組出你的分數) ──────────
#  價值   : value(綜合價值分,高=便宜), value_ind(產業內相對), eps, roe
#  動能   : momentum, mom60, mom120, high52_prox(距52週高%), ma_gap60, rsi14, bbp20
#  成長   : revenue_yoy, rev_yoy_3m, rev_accel(營收加速), eps_pos_q4(連4季正)
#  籌碼   : chip, chip5/10/60(法人買超), chip_accel, ratio_1000up(千張大戶%), big_d4w/12w
#  風險   : vol60(60日波動,低=穩), adv20(流動性)
#  內部人 : holders_chg12w, pledge_pct(質押%), pledge_d3m, director_holding_pct(董監持股%)
#  產業   : tej_ind_name (可做產業中性化/分散)
#  ⚠️ fwd : 這是未來報酬=答案,禁止當輸入!


def score(m: pd.DataFrame) -> pd.Series:
    """給當月 DataFrame,回每檔的分數 (高分=優先持有)。★這是唯一要改的地方★

    範例:低波動 = vol60 越低越好 → 用負號讓「低波動=高分」。
    換方向就換這一行,例如:
      動能   : return m["mom120"]
      價值   : return m["value"]
      籌碼   : return m["chip60"]
      複合   : return zscore(m["value"]) + zscore(m["chip60"]) - zscore(m["vol60"])
    """
    return -m["vol60"]


# ── 步驟 3-4:把 score 轉成 holdings 並回測 (以下不用改) ──────────────────────
def build_holdings() -> dict:
    df = pd.read_parquet(OBS_ALPHA)
    df = df[(df["listed_ok"] == True) & (df["adv20"] >= ADV_FLOOR)].copy()  # noqa: E712
    holdings = {}
    for as_of, g in df.groupby("as_of"):
        g = g.dropna(subset=["vol60"])            # 依你 score 用到的欄位改 dropna
        if len(g) < TOP_K:
            continue
        s = score(g)
        top = g.assign(_s=s).nlargest(TOP_K, "_s")
        holdings[as_of] = top["stock_id"].tolist()
    return holdings


if __name__ == "__main__":
    print(f"假設: {THESIS}")
    print(f"門檻: {PASS_RULE}\n")
    eng = Engine()
    holdings = build_holdings()
    result = eng.run(holdings)
    eng.report(result, f"Top{TOP_K}·{THESIS[:12]}")
