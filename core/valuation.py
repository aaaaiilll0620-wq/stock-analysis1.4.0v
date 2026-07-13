import logging
from typing import Dict, Any, Optional, List
import pandas as pd

logger = logging.getLogger(__name__)


class ValuationEngine:
    """
    估值引擎 (Valuation Engine) —— 安全邊際與估值整合。

    對四項估值指標做加權評分,確保選出的不只是「好公司」,而是「價格合理的好公司」:
        P/E Ratio       本益比      (越低越好)
        P/B Ratio       股價淨值比  (越低越好)
        P/S Ratio       股價營收比  (越低越好;由 PE × 淨利率推導,不額外耗 API)
        Dividend Yield  殖利率      (越高越好)

    設計原則與 FundamentalEngine 一致:
      - 線性內插 0-100,upper < lower 時自動反向 (越低越好)。
      - 任一指標缺失都不崩潰,改記入 missing 並降低 confidence,權重動態重分配。
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or {
            "pe": 0.35,
            "pb": 0.25,
            "ps": 0.20,
            "dividend_yield": 0.20,
        }
        total = sum(self.weights.values())
        self.weights = {k: v / total for k, v in self.weights.items()}

        # lower -> 0 分, upper -> 100 分
        self.bounds = {
            "pe": {"lower": 30.0, "upper": 8.0},    # PE 30->0, 8->100
            "pb": {"lower": 4.0, "upper": 0.8},     # PB 4->0, 0.8->100
            "ps": {"lower": 8.0, "upper": 0.5},     # PS 8->0, 0.5->100
            "dividend_yield": {"lower": 0.0, "upper": 6.0},  # 殖利率 0%->0, 6%->100
        }
        # valuation_status 判定門檻 (分數越高代表越便宜)
        self.status_thresholds = {"cheap": 65.0, "fair": 40.0}

    # 本益比歷史高檔的交叉驗證門檻
    PE_PERCENTILE_HIGH = 80.0    # 本益比歷史位階 >= 此值才做「成長溢價 vs 昂貴泡泡」分類
    GROWTH_STRONG = 15.0         # 累計營收年增 >= 此值視為成長強勁
    PEG_CHEAP = 1.0             # PEG < 此值視為成長撐得起本益比
    BUBBLE_SCORE_CAP = 30.0      # 判定為「昂貴泡泡」時,估值分數上限

    def _score_metric(self, value: Optional[float], bounds: dict) -> Optional[float]:
        """線性內插;缺值回傳 None 讓上層重分配權重。"""
        if value is None or pd.isna(value):
            return None
        lower, upper = bounds.get("lower"), bounds.get("upper")
        if lower is None or upper is None or lower == upper:
            return None
        score = (float(value) - lower) / (upper - lower) * 100.0
        return float(max(0.0, min(100.0, score)))

    def evaluate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # ============================================================
        # 跨牛熊估值:三重視角
        #   A. PEG 成長調整 (本益比 ÷ 成長率) —— 與市場多空無關的核心標準
        #   B. 相對歷史位階 (河流圖百分位) —— 相對自身歷史便宜/貴
        #   C. 絕對門檻 —— 前兩者都缺時的後備
        # 有 A/B 任一即混合計分;皆缺才退回 C。
        # ============================================================
        pe = data.get("pe_ratio")

        # ---- A. PEG 成長調整分 ----
        #   成長率優先序:EPS年增 > 淨利年增 > 累計營收年增 > 近3月營收年增。
        peg_score = None
        peg_ratio = None
        growth = None
        for key in ("eps_cagr", "net_income_growth", "revenue_cum_yoy", "rev_cagr"):
            g = data.get(key)
            if g is not None and not pd.isna(g) and float(g) > 0:
                growth = float(g)
                break
        if pe is not None and not pd.isna(pe) and float(pe) > 0 and growth and growth > 0:
            peg_ratio = float(pe) / growth
            # PEG 0.75→100, 1.0→80, 1.5→55, 2.0→35, 3.0→0 (分段線性)
            peg_score = self._peg_to_score(peg_ratio)

        # ---- B. 相對歷史位階分 ----
        pe_pct = data.get("pe_percentile")
        pb_pct = data.get("pb_percentile")
        yld_pct = data.get("dividend_yield_percentile")
        rel_score = None
        rel_detail = {}
        if pe_pct is not None or pb_pct is not None:
            per_metric: Dict[str, float] = {}
            if pe_pct is not None:
                per_metric["pe"] = 100.0 - float(pe_pct)
            if pb_pct is not None:
                per_metric["pb"] = 100.0 - float(pb_pct)
            if yld_pct is not None:
                per_metric["dividend_yield"] = float(yld_pct)
            rel_w = {"pe": 0.45, "pb": 0.30, "dividend_yield": 0.25}
            wsum = sum(rel_w[k] for k in per_metric)
            rel_score = sum(per_metric[k] * (rel_w[k] / wsum) for k in per_metric)
            rel_detail = {k: round(v, 1) for k, v in per_metric.items()}

        # ---- 混合 A + B ----
        # v4.4 (藍圖項9) 重修:混合比例 55/45 → 85/15。
        #   因子實驗診斷 (45檔池,全期/2022):現行混合 IC +0.022/−0.008、單因子多空 −0.81%/−0.95%;
        #   拖累源是「歷史位階」成分 (單獨 IC 全期 −0.021),PEG 成分單獨 IC +0.055、多空 +1.07% 為正
        #   → 判定為『訊號品質』問題而非因子本質 → 加重 PEG 至 0.85。
        #   保留 0.15 位階:2022 空頭段位階 IC +0.039 (熊市價值有效),且昂貴泡泡交叉驗證仍需它;
        #   純 PEG (100/0) 全期最好但 2022 綜合 −1.34% 明顯變差,故不取。
        if peg_score is not None or rel_score is not None:
            parts, wsum = 0.0, 0.0
            if peg_score is not None:
                parts += peg_score * 0.85
                wsum += 0.85
            if rel_score is not None:
                parts += rel_score * 0.15
                wsum += 0.15
            score = float(round(parts / wsum, 2))
            basis_bits = []
            if peg_score is not None:
                basis_bits.append("成長(PEG)")
            if rel_score is not None:
                basis_bits.append("歷史位階")

            # 本益比歷史高檔 → 用 PEG／營收成長交叉驗證是「成長溢價」還是「昂貴泡泡」
            label = ""
            rev = data.get("revenue_cum_yoy")
            if pe_pct is not None and float(pe_pct) >= self.PE_PERCENTILE_HIGH:
                has_growth = (peg_ratio is not None) or (rev is not None) or (growth is not None)
                if has_growth:
                    is_premium = (peg_ratio is not None and peg_ratio < self.PEG_CHEAP) or \
                                 (rev is not None and float(rev) >= self.GROWTH_STRONG)
                    if is_premium:
                        label = "成長溢價"       # 獲利/營收跟得上股價,不砍分
                    else:
                        label = "昂貴泡泡"       # 高檔但成長跟不上 → 壓低分數
                        score = min(score, self.BUBBLE_SCORE_CAP)
                # 成長資料全缺 → 無法交叉驗證,不硬判 (label 維持 "")

            missing = [k for k in ("pe", "pb", "dividend_yield") if k not in rel_detail]
            return {
                "valuation_score": score,
                "valuation_status": self._status_relative(score),
                "valuation_label": label,
                "valuation_basis": "+".join(basis_bits),
                "peg_ratio": round(peg_ratio, 2) if peg_ratio is not None else None,
                "growth_used": round(growth, 1) if growth is not None else None,
                "per_metric": rel_detail,
                "inputs": {"pe": pe, "pe_percentile": pe_pct, "pb_percentile": pb_pct,
                           "dividend_yield_percentile": yld_pct, "peg": peg_ratio},
                "missing_fields": missing,
                "confidence": float(round(max(40.0, 100.0 - len(missing) * 12.0), 1)),
            }

        # ---- C. 絕對門檻 (前兩者皆缺) ----
        return self._evaluate_absolute(data)

    @staticmethod
    def _peg_to_score(peg: float) -> float:
        """PEG → 0-100 分 (越低越好)。分段線性:0.75→100, 1→80, 1.5→55, 2→35, 3→0。"""
        pts = [(0.75, 100.0), (1.0, 80.0), (1.5, 55.0), (2.0, 35.0), (3.0, 0.0)]
        if peg <= pts[0][0]:
            return 100.0
        if peg >= pts[-1][0]:
            return 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= peg <= x1:
                return float(y0 + (y1 - y0) * (peg - x0) / (x1 - x0))
        return 0.0

    def _evaluate_absolute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raw = {
            "pe": data.get("pe_ratio"),
            "pb": data.get("pb_ratio"),
            "ps": data.get("price_to_sales"),
            "dividend_yield": data.get("dividend_yield"),
        }
        # 殖利率 0.0 在台股多半代表「當年未發或資料缺」,視為缺值以免誤判為超差
        if raw["dividend_yield"] is not None and float(raw["dividend_yield"]) == 0.0:
            raw["dividend_yield"] = None

        per_metric = {}
        missing = []
        for key, bounds in self.bounds.items():
            s = self._score_metric(raw.get(key), bounds)
            per_metric[key] = s
            if s is None:
                missing.append(key)

        available = {k: self.weights[k] for k, s in per_metric.items() if s is not None}
        if available:
            w_sum = sum(available.values())
            valuation_score = sum(per_metric[k] * (available[k] / w_sum) for k in available)
        else:
            valuation_score = 0.0

        valuation_score = float(round(valuation_score, 2))
        status = self._status(valuation_score, has_data=bool(available))
        confidence = max(0.0, 100.0 - len(missing) * 20.0)

        return {
            "valuation_score": valuation_score,
            "valuation_status": status,
            "valuation_label": "",
            "valuation_basis": "絕對",
            "per_metric": {k: (round(v, 1) if v is not None else None)
                           for k, v in per_metric.items()},
            "inputs": {k: raw.get(k) for k in self.bounds},
            "missing_fields": missing,
            "confidence": float(round(confidence, 1)),
        }

    def _status_relative(self, score: float) -> str:
        if score >= 65.0:
            return "相對偏低 (便宜)"
        if score >= 40.0:
            return "相對合理"
        return "相對偏高 (昂貴)"

    def _status(self, score: float, has_data: bool) -> str:
        if not has_data:
            return "估值資料不足"
        if score >= self.status_thresholds["cheap"]:
            return "估值偏低 (便宜)"
        if score >= self.status_thresholds["fair"]:
            return "估值合理"
        return "估值偏高 (昂貴)"
