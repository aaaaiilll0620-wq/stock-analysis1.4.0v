# -*- coding: utf-8 -*-
"""core/canonical_universe.py — P0-U1 Canonical Ranking Universe Alignment

預註冊：docs/prereg_P0_U1_CanonicalUniverse_2026-08-11.md

背景（見該預註冊 §5-9）：H1-H5 已驗證的 `dual100` 基準
(`beat_0050/strategies/high52_lab.py::dual_confirm_mask`) 在計算 real_composite
（管線 A）與 c2（管線 B，四腳等權平均）百分位時，雖然共用同一個 ADV 分層母體
`P.tier_valid[tier]` 起點，但 A 與 B 各自的排名分母其實不同：
- A（real_composite）因 `min_cov=1.0` 硬性覆蓋率門檻，本來就 100% 覆蓋 `tier_valid[tier]`；
- B（c2）是四條腿（value_ind / revenue_yoy / high52_prox / momentum）各自百分位後
  等權平均，任一腿缺值該檔 c2 即為 NaN —— 因此 B 的有效分母可能是 `tier_valid[tier]`
  的**真子集**，而 A 的分母仍是完整的 `tier_valid[tier]`。

這正是預註冊 §6-9 要修的「A/B percentile denominator 不對齊」，只是落在這個引擎裡的
具體位置與預註冊背景文字描述的 production（watchlist.txt vs 每日 ADV 全池）不同一個
site —— 使用者已在對話中確認：本次 U1 對象是 H1-H5 已驗證研究引擎（非 production
score_store/l4a_decision.py 路徑），故 canonical universe 在此定義為：

    C_t = tier_valid[tier] ∩ {real_composite 有效} ∩ {c2 四腳皆有效}

本模組只做兩件事：
  1. 提供從 `high52_lab.dual_confirm_mask` 內嵌 closure **逐位元原樣抽取**的百分位排名
     原語（`rank_pct_desc` / `topk_mask_desc`）——不得在抽取時順便改演算法（§9）。
  2. 提供建構 canonical universe 與其自動化 assertion 的函式（§6、§14）。

禁止事項（§11 全部適用）：本模組不得新增/放寬/收緊任何 eligibility 條件本身
（不改 ADV 門檻、不改 listed_ok、不改 c2 四腳定義、不改 tie-handling），只把 A 與 B
的排名分母對齊到同一個交集母體。
"""
from __future__ import annotations

import numpy as np

# c2_score（研究引擎版，見 high52_lab.dual_confirm_mask 內的 `c2 = (v+f+ph+(100-m))/4`）
# 用到的四條原始腿，逐字對齊該函式，不得增減（§11「管線 B」禁止修改清單）。
C2_LEGS = ("value_ind", "revenue_yoy", "high52_prox", "momentum")


def rank_pct_desc(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """橫斷面百分位（分數越高、百分位越高），逐列（每個決策日）獨立計算。

    與 `high52_lab.dual_confirm_mask` 內嵌的 `pct()` closure 逐位元相同：
    - 由高到低排序，`kind="stable"` tie-break（同分先出現在陣列裡的先贏，
      **不是** pandas `.rank()` 預設的 average-rank）；
    - 分母 = 該列 `valid` 母體內的有效（非 NaN）檔數；
    - 公式 `100 * (1 - (rank-1)/N)`，rank=1（最高分）→ 100；**不是**
      `pandas.rank(pct=True)*100`（= rank/N）——兩者對同一筆資料數值不同，
      混用會靜默改變演算法，違反預註冊 §9。

    `values` / `valid` shape 皆為 (T, S)（決策日 × 股票），`valid=False` 或
    `values` 為 NaN 的格子回傳 NaN。
    """
    ok = valid & np.isfinite(values)
    x = np.where(ok, values, -np.inf).astype(np.float64)
    order = np.argsort(-x, axis=1, kind="stable")
    n_cols = values.shape[1]
    rk = np.empty(order.shape, dtype=np.float64)
    np.put_along_axis(rk, order, np.arange(1, n_cols + 1, dtype=np.float64)[None, :], axis=1)
    nv = ok.sum(1).astype(float)[:, None]
    return np.where(ok, 100.0 * (1.0 - (rk - 1) / np.maximum(nv, 1)), np.nan)


def topk_mask_desc(values: np.ndarray, valid: np.ndarray, top_pct: int) -> np.ndarray:
    """Top-K 遮罩，逐位元同 `dual_confirm_mask` 內嵌的 `topk()` closure。

    以**名次門檻**（`rank <= floor(N * top_pct / 100)`，至少取 1 檔）選股，
    不是對 `rank_pct_desc()` 的輸出值做 `>= 100-top_pct` 門檻比較——兩者對於
    有並列名次（tie）的邊界檔可能選出不同集合，必須用原本的名次門檻寫法
    才是「與現行 production 完全相同的 percentile ranking function」（§9）。
    """
    ok = valid & np.isfinite(values)
    x = np.where(ok, values, -np.inf)
    order = np.argsort(-x, axis=1, kind="stable")
    n_cols = values.shape[1]
    rk = np.empty(order.shape, dtype=np.int32)
    np.put_along_axis(rk, order, np.arange(1, n_cols + 1, dtype=np.int32)[None, :], axis=1)
    kk = np.maximum(1, (ok.sum(1) * top_pct // 100).astype(int))
    return (rk <= kk[:, None]) & ok


def build_canonical_valid_mask(tier_valid: np.ndarray, real_composite: np.ndarray,
                               factor_legs: dict, legs: tuple = C2_LEGS) -> np.ndarray:
    """C_t = tier_valid ∩ {real_composite 有效} ∩ {c2 四腳皆有效}（預註冊 §6）。

    只對既有的 eligibility 條件取交集，不新增、不放寬、不收緊任何門檻本身
    （§11：不得改 ADV 門檻、不得新增流動性/市值/成交值篩選）。

    `tier_valid`：(T, S) bool，現行 ADV 分層母體（未改動，直接沿用）。
    `real_composite`：(T, S) float，A 腿原始分數（未改動）。
    `factor_legs`：`{factor_name: (T, S) float}`，B 腿（c2）用到的原始腿字典
    （即 `Panel.F`），未改動。
    """
    valid = tier_valid & np.isfinite(real_composite)
    for leg in legs:
        valid = valid & np.isfinite(factor_legs[leg])
    return valid


def assert_canonical_invariants(canonical: np.ndarray, real_composite: np.ndarray,
                                c2: np.ndarray, stocks: np.ndarray, months: np.ndarray) -> None:
    """預註冊 §14：每個 rebalance date 的自動化 assertion。任一失敗 raise，不得靜默降級。

    逐一對應 §14 的四組要求：
      1/2. set/len(A_rank_tickers) == set/len(B_rank_tickers) == set/len(C_t)
           —— 用「isfinite(real_composite) 與 isfinite(c2) 在 canonical 母體內
           必須逐格相等」來證明：A 的有效格、B 的有效格、canonical 母體三者
           在每個決策日都是同一個股票集合。
      3.   real_composite.notna().all() / c2_score_full.notna().all()
           —— 在 canonical 母體內兩者皆不得有缺值（上一條已隱含，這裡明寫）。
      4.   ticker / date 唯一性 —— Panel 的矩陣表示本身即以 (date, ticker) 為
           格點座標，不可能重複；這裡改為檢查 `stocks`/`months` 陣列本身無重複
           （矩陣座標軸的唯一性前提，一旦違反代表 Panel 建構壞了，非 U1 本身邏輯）。
    """
    if not np.array_equal(np.isfinite(real_composite) & canonical, canonical):
        bad = int((canonical & ~np.isfinite(real_composite)).sum())
        raise AssertionError(
            f"U1-S 失敗：real_composite 在 canonical universe C_t 內有 {bad} 個缺值格 "
            "—— A_rank_tickers != C_t。")
    if not np.array_equal(np.isfinite(c2) & canonical, canonical):
        bad = int((canonical & ~np.isfinite(c2)).sum())
        raise AssertionError(
            f"U1-S 失敗：c2 在 canonical universe C_t 內有 {bad} 個缺值格 "
            "—— B_rank_tickers != C_t。")
    if len(stocks) != len(set(stocks.tolist())):
        raise AssertionError("U1-S 失敗：Panel.stocks 有重複 ticker —— 矩陣座標軸不唯一。")
    if len(months) != len(set(months.tolist())):
        raise AssertionError("U1-S 失敗：Panel.months 有重複 date —— 矩陣座標軸不唯一。")
