"""
交易計畫 (trade plan)
================================================================================
把個股『已經算好』的價量結構欄位,換算成可以直接照著看的:
  進場區間 (entry_low ~ entry_high) / 停損 (stop) / 目標 (target1, target2)
  / 距買區% (dist_to_buy_pct) / 風報比 (rr) / 是否已在買區 (in_buy_zone)。

用到的現成欄位 (皆由既有管線算好,本模組不抓 API、不改狀態):
  current_price, atr,
  value_area_low  (VAL,支撐帶下緣),  value_area_high (VAH,壓力帶上緣),
  cost_zone_poc   (POC,大戶成本區中心),
  cost_zone_support / cost_zone_resistance (最近的量能支撐/壓力), ma20

設計原則:
  · 進場鎖在『成本區 / 支撐』,不鼓勵追在現價 → 現價很高時會叫你等回檔。
  · 停損錨定在『進場下緣之下』(用 ATR 當緩衝),與現價多高無關,邏輯一致。
  · 目標優先用結構壓力 (VAH/量能壓力),延伸目標用 2R。
⚠️ 所有價位都是規則換算的『參考』,不是保證,也不是投資建議;下單前請自行覆核。
================================================================================
"""

from dataclasses import dataclass, asdict
from typing import Optional

# 量價位階『脫離現價』判準:下方 POC/VAL/支撐 若低於現價的此比例,視為已失效
# (強趨勢股的舊成本區),不採用 → 改由 MA20/ATR 錨定。0.75 = 容忍現價 25% 以內的回檔支撐。
_STALE_FLOOR = 0.75


def _f(v):
    """安全轉 float;None/非數字 → None。"""
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class TradePlan:
    entry_low: Optional[float]        # 建議進場區間下緣 (理想承接價)
    entry_high: Optional[float]       # 建議進場區間上緣 (可接受成本價)
    stop: Optional[float]             # 停損參考 (跌破即出)
    target1: Optional[float]          # 第一目標 (結構壓力)
    target2: Optional[float]          # 延伸目標 (2R)
    dist_to_buy_pct: Optional[float]  # 現價距進場上緣% (正=還在上方要等回檔;負/0=已到買區或更低)
    rr: Optional[float]               # 風報比 = (目標-進場) / (進場-停損)
    in_buy_zone: bool                 # 現價是否已落在建議進場區間內 (含以下)
    note: str                         # 一句白話操作提示

    def as_dict(self):
        return asdict(self)


def build_trade_plan(stock, score_result=None) -> TradePlan:
    """由 StockData(+可選 ScoreResult) 換算交易計畫。資料不足時盡量降級,不丟例外。"""
    price = _f(getattr(stock, "current_price", None))
    atr = _f(getattr(stock, "atr", None)) or 0.0
    val = _f(getattr(stock, "value_area_low", None))        # 支撐帶下緣
    vah = _f(getattr(stock, "value_area_high", None))       # 壓力帶上緣
    poc = _f(getattr(stock, "cost_zone_poc", None))         # 成本區中心
    sup = _f(getattr(stock, "cost_zone_support", None))     # 最近下方量能支撐
    res = _f(getattr(stock, "cost_zone_resistance", None))  # 最近上方量能壓力
    ma20 = _f(getattr(stock, "ma20", None))

    if not price or price <= 0:
        return TradePlan(None, None, None, None, None, None, None, False,
                         "資料不足,無法計算價位參考。")

    # 過濾『已脫離現價』的量價位階:強趨勢股 (如 90 天內翻倍) 的 POC/VAL 會停在數月前的
    # 低價帶,直接拿來當進場/停損會算出橫跨一倍的無意義區間 → 低於現價 _STALE_FLOOR 的
    # 下方量價位階視為失效,改由 MA20/ATR 錨定現價附近。壓力 (VAH/res) 在上方,不受此過濾。
    def _fresh(x):
        return x if (x and x > 0 and x >= price * _STALE_FLOOR) else None
    val_f, poc_f, sup_f = _fresh(val), _fresh(poc), _fresh(sup)

    # ---- 進場區間 ----
    # 上緣 = 可接受成本:POC / MA20 取『有值(未脫離現價)且較低者』;都沒有 → 現價回檔一點。
    upper_candidates = [x for x in (poc_f, ma20) if x and 0 < x <= price * 1.02]
    entry_high = (min(upper_candidates) if upper_candidates
                  else round(price - (0.5 * atr if atr > 0 else price * 0.01), 2))
    # 下緣 = 理想承接:VAL / 支撐 取『有值(未脫離)且低於上緣』的最高者;沒有 → 上緣往下 1.5 ATR。
    lower_candidates = [x for x in (val_f, sup_f) if x and 0 < x < entry_high]
    entry_low = (max(lower_candidates) if lower_candidates
                 else round(entry_high - (1.5 * atr if atr > 0 else entry_high * 0.03), 2))
    if entry_low > entry_high:                              # 保護:確保 low <= high
        entry_low, entry_high = entry_high, entry_low

    # ---- 停損:錨定在進場下緣之下,用 ATR 當緩衝 (與現價多高無關,邏輯一致) ----
    buffer = 1.5 * atr if atr > 0 else entry_low * 0.03
    stop = round(entry_low - buffer, 2)
    if stop <= 0:
        stop = round(entry_low * 0.95, 2)

    # ---- 目標:優先結構壓力 (VAH/量能壓力,且須在現價之上),否則 +2ATR ----
    res_up = next((x for x in (vah, res) if x and x > price), None)   # 只採現價上方的壓力
    target1 = res_up or (round(price + 2.0 * atr, 2) if atr > 0 else round(price * 1.08, 2))
    # 目標至少要離現價一個 ATR (避免壓力就貼在現價,給出幾乎沒空間的假目標)
    min_target = price + (1.0 * atr if atr > 0 else price * 0.04)
    if target1 < min_target:
        target1 = round(min_target, 2)
    # 若壓力就在進場上緣下方 (現價已突破整個結構),目標改用 +2ATR 往上推
    if target1 <= entry_high:
        target1 = round(entry_high + (2.0 * atr if atr > 0 else entry_high * 0.06), 2)

    # 延伸目標 = 2R (以進場上緣為假想進場、到停損為 1R)
    risk = entry_high - stop
    target2 = round(entry_high + 2.0 * risk, 2) if risk > 0 else None

    # ---- 距買區%、是否在買區 ----
    dist = round((price - entry_high) / entry_high * 100.0, 1)
    in_zone = price <= entry_high * 1.005                   # 容忍 0.5%

    # ---- 風報比 (以進場上緣為假想進場) ----
    rr = round((target1 - entry_high) / risk, 2) if risk > 0 else None

    # ---- 白話提示 (參考評級語氣) ----
    rating = getattr(score_result, "rating", "") if score_result else ""
    if in_zone and dist <= -3:
        note = "現價已低於成本區,留意是否破線;確認支撐守穩再承接,別接落刀。"
    elif in_zone:
        note = "現價已在建議進場區間,可依評級分批進場;跌破停損即出場。"
    elif dist <= 4:
        note = f"現價略高於買區上緣約 {dist}%,可小量試單,回到 {entry_low}~{entry_high} 再加碼。"
    else:
        hot = "(強勢股回檔常不深,可掛單等)" if rating == "強勢買進" else ""
        note = f"現價高於成本區約 {dist}%,追高風險大,等回檔到 {entry_low}~{entry_high} 再分批較穩。{hot}"

    return TradePlan(entry_low, entry_high, stop, target1, target2, dist, rr, in_zone, note)


def format_plan_lines(plan: TradePlan) -> list:
    """回傳 console 報告用的幾行字。"""
    def s(v):
        return f"{v:,.2f}" if isinstance(v, (int, float)) else "—"
    if plan.entry_high is None:
        return [plan.note]
    dist_txt = f"　(現價距上緣 {plan.dist_to_buy_pct:+.1f}%)" if plan.dist_to_buy_pct is not None else ""
    l2 = f"停損參考:{s(plan.stop)}　｜　目標:{s(plan.target1)}"
    if plan.target2:
        l2 += f" → {s(plan.target2)}"
    if plan.rr is not None:
        l2 += f"　｜　風報比 {plan.rr}"
    return [
        f"進場區間:{s(plan.entry_low)} ~ {s(plan.entry_high)}{dist_txt}",
        l2,
        plan.note,
    ]
