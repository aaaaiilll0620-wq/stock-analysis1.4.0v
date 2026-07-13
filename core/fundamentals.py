import logging
from typing import Dict, Any, Union, Optional, List
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)

class FundamentalEngine:
    """
    基本面評估引擎 (Fundamental Analysis Engine)
    量化系統的第一層篩選,根據財務報表數據計算公司的綜合健康分數。

    本版強化三大能力:
      1. 獲利品質 (Profit Quality):加入營收年增率 vs 淨利年增率的一致性檢查,
         淨利成長遠高於營收成長時標註「獲利動態風險」(可能來自業外/一次性收益);
         並以毛利率高低評估「護城河 (Moat)」。
      2. 財務健康 (Financial Health):加入營業現金流 (OCF) 與自由現金流 (FCF),
         OCF 為負或與淨利嚴重背離時列為「高風險」。
      3. 資料治理:任何欄位缺失都不讓流程崩潰,改以缺漏清單降低信心分數。
    """
    # v4.4 候選訊號開關 (未來優化藍圖 10):總資產週轉率 (年化季營收÷總資產) 進獲利能力組。
    # A/B (scripts/factor_experiments.py):基本面單因子多空 全期 +1.51→+2.05%、2022 +0.14→+0.26%,
    # 綜合多空全期 +2.63→+2.93% ✅ 通過 → 預設開啟。金融股豁免 (資產結構特殊)。
    USE_ASSET_TURNOVER = True

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        # Default weights sum to 1.0
        self.weights = weights or {
            "profitability": 0.30,
            "growth": 0.25,
            "safety": 0.25,
            "valuation": 0.20
        }
        # Normalize weights to sum to 1.0
        total = sum(self.weights.values())
        self.weights = {k: v / total for k, v in self.weights.items()}
        self.group_mapping = {
            "profitability": ["roe", "net_margin", "gross_margin"],
            "growth": ["rev_cagr", "eps_cagr"],
            "safety": ["debt_to_asset", "current_ratio"],
            "valuation": ["pe_vs_industry"]
        }
        # ------------------------------------------------------------------
        # 評分邊界設定 (lower -> 0 分, upper -> 100 分)
        # 「越低越好」的指標把大數字放 lower、小數字放 upper 即可自動反向。
        # ------------------------------------------------------------------
        self.bounds = {
            "roe": {"lower": 5.0, "upper": 20.0},
            "net_margin": {"lower": 0.0, "upper": 15.0},
            "gross_margin": {"lower": 10.0, "upper": 30.0},
            "asset_turnover": {"lower": 0.5, "upper": 3.0},
            "rev_cagr": {"lower": -5.0, "upper": 15.0},
            "eps_cagr": {"lower": 0.0, "upper": 20.0},
            "cash_quality": {"lower": 0.7, "upper": 1.5},
            "debt_to_asset": {"lower": 60.0, "upper": 30.0},   # 60%->0分, 30%->100分
            "current_ratio": {"lower": 100.0, "upper": 250.0}, # 百分比制
            "pe_vs_industry": {"lower": 30.0, "upper": 10.0}   # 原始 PE:30->0分, 10->100分
        }
        self.hard_filters = {
            "max_debt_to_asset": 85.0,       # 負債比 > 85% 在台股屬高風險
            "min_current_ratio": 50.0,       # 流動比率 < 50% 視為缺錢
            "min_net_margin": -10.0,         # 嚴重虧損的淨利率剔除
            "min_cash_quality": 0.5
        }
        # ------------------------------------------------------------------
        # 獲利品質 / 護城河 / 現金流健康門檻 (可依產業自行調整)
        # ------------------------------------------------------------------
        self.quality_thresholds = {
            # 淨利年增率 - 營收年增率 的差距 (百分點) 超過此值,且淨利成長為正,
            # 代表獲利成長「不是靠本業擴張」撐起來的,標註獲利動態風險。
            "profit_growth_gap": 25.0,
            "moat_strong_gross": 40.0,       # 毛利率 >= 40% 視為強護城河
            "moat_mid_gross": 20.0,          # 20% <= 毛利率 < 40% 視為中等護城河
            # 現金含金量:OCF / 淨利。< 0.5 視為背離、< 0 (OCF 負) 直接高風險
            "ocf_ni_divergence": 0.5,
        }

    # ==================================================================
    # 基礎線性內插評分
    # ==================================================================
    def _calculate_score(self, value: float, bounds: dict) -> float:
        """
        線性內插 (0-100):score = (value - lower) / (upper - lower) * 100
        upper < lower 時 (越低越好) 分母為負,公式自然反向。
        """
        lower = bounds.get("lower")
        upper = bounds.get("upper")
        if value is None or pd.isna(value) or value == -999:
            return 0.0
        if lower is None or upper is None or lower == upper:
            return 0.0
        score = (value - lower) / (upper - lower) * 100.0
        return float(max(0.0, min(100.0, score)))

    # ==================================================================
    # 新增:獲利品質一致性 + 護城河
    # ==================================================================
    def _evaluate_profit_quality(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        獲利品質檢查:
          - 一致性:淨利年增率若「遠高於」營收年增率,標註獲利動態風險
            (常見於認列業外收益、處分資產、匯兌利益等非經常性項目)。
          - 護城河:以毛利率高低分級 strong / mid / weak。
        缺資料時回傳 note 但不讓流程崩潰。
        """
        rev_g = data.get("revenue_growth")
        if rev_g is None or pd.isna(rev_g):
            rev_g = data.get("rev_cagr")
        ni_g = data.get("net_income_growth")
        gross = data.get("gross_margin")

        result = {"risk": False, "note": "", "moat": "未知"}

        # --- 一致性檢查 ---
        if ni_g is not None and not pd.isna(ni_g) and rev_g is not None and not pd.isna(rev_g):
            gap = float(ni_g) - float(rev_g)
            if float(ni_g) > 0 and gap >= self.quality_thresholds["profit_growth_gap"]:
                # 優先判斷本業獲利占比(營業利益/稅後淨利):
                #   >=80% → 視為本業真成長(營運槓桿),不論毛利率高低。
                #   <80%  → 才視為可能業外/一次性拉動的風險。
                op_ratio_raw = data.get("operating_profit_ratio")
                has_op = op_ratio_raw is not None and not pd.isna(op_ratio_raw)
                op_ratio = None
                if has_op:
                    op_ratio = float(op_ratio_raw)
                    if op_ratio > 1.5:
                        op_ratio = op_ratio / 100.0
                if has_op and op_ratio is not None and op_ratio >= 0.80:
                    result["risk"] = False
                    result["operating_leverage"] = True
                    result["note"] = (
                        f"本業獲利爆發:淨利年增 {ni_g:.1f}%,本業獲利占比達 {float(op_ratio)*100:.0f}%,"
                        f"係營運槓桿/毛利改善帶動,屬強勢而非風險"
                    )
                elif has_op and op_ratio is not None:
                    result["risk"] = True
                    result["note"] = (
                        f"獲利動態風險:淨利年增 {ni_g:.1f}% 遠高於營收年增 {rev_g:.1f}%,"
                        f"且本業獲利占比僅 {float(op_ratio)*100:.0f}% (<80%),獲利主要來自業外/一次性項目"
                    )
                else:
                    # 缺本業占比資料 → 無法斷定業外,不武斷打風險,僅資訊提示
                    result["risk"] = False
                    result["note"] = (
                        f"淨利年增 {ni_g:.1f}% 高於營收年增 {rev_g:.1f}%;"
                        f"缺本業獲利占比資料,無法區分本業/業外,建議自行確認財報業外項目"
                    )
            elif float(ni_g) < 0 and float(rev_g) > 0:
                result["risk"] = True
                result["note"] = (
                    f"獲利品質背離:營收年增 {rev_g:.1f}% 為正但淨利年增 {ni_g:.1f}% 轉負,"
                    f"成本或費用侵蝕獲利"
                )
        else:
            result["note"] = "缺營收/淨利年增率,無法檢查獲利一致性"

        # --- 護城河 (毛利率) ---
        if gross is not None and not pd.isna(gross):
            g = float(gross)
            if g >= self.quality_thresholds["moat_strong_gross"]:
                result["moat"] = "強護城河"
            elif g >= self.quality_thresholds["moat_mid_gross"]:
                result["moat"] = "中等護城河"
            else:
                result["moat"] = "弱護城河"
        return result

    # ==================================================================
    # 新增:現金流健康
    # ==================================================================
    def _evaluate_cash_flow_health(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        現金流健康度:
          - OCF 為負 → 高風險 (公司本業無法自己產生現金)。
          - OCF > 0 但 OCF/淨利 < 門檻 → 現金含金量不足 (獲利未轉成現金,觀察)。
          - FCF 為負 → 資本支出吃掉現金,標註 (成長期公司未必是壞事,故僅提示)。
        回傳 risk_level: healthy / watch / high_risk
        """
        ocf = data.get("operating_cash_flow")
        fcf = data.get("free_cash_flow")
        ni = data.get("net_income")
        ratio = data.get("ocf_to_net_income")

        notes: List[str] = []
        risk_level = "healthy"

        if ocf is None or pd.isna(ocf):
            return {"risk_level": "unknown", "notes": ["缺營業現金流資料,無法評估現金流健康"]}

        ocf = float(ocf)
        # 高速成長判定:新創/擴張期本業可能階段性燒錢,不等於營運失敗
        strong_growth = (float(data.get("revenue_cum_yoy") or 0) >= 30.0) or \
                        (float(data.get("rev_cagr") or 0) >= 30.0)

        if ocf < 0:
            if strong_growth:
                # 營收高速成長但 OCF 為負 → 研判為成長/擴張期投入,列「觀察」而非直接高風險
                risk_level = "watch"
                notes.append(
                    f"營業現金流為負 ({ocf:,.0f} 千元),惟營收高速成長,研判為成長/擴張期投入,列為觀察"
                )
            else:
                risk_level = "high_risk"
                notes.append(f"營業現金流為負 ({ocf:,.0f} 千元),本業無法自產現金")
        else:
            # 現金含金量比對 (OCF > 0 時才有意義)
            if ratio is None or pd.isna(ratio):
                if ni is not None and not pd.isna(ni) and float(ni) != 0:
                    ratio = ocf / float(ni)
            if ratio is not None and not pd.isna(ratio):
                if float(ratio) < self.quality_thresholds["ocf_ni_divergence"]:
                    risk_level = "watch" if risk_level == "healthy" else risk_level
                    notes.append(
                        f"現金含金量偏低 (OCF/淨利={float(ratio):.2f}),獲利未充分轉為現金"
                    )

        # 自由現金流為負:區分「本業有賺、資本支出擴張」vs「本業就缺錢」
        if fcf is not None and not pd.isna(fcf) and float(fcf) < 0:
            if ocf > 0:
                # 【成長型投資】本業現金流為正,FCF 因資本支出(擴廠/設備)轉負 → 不扣分,僅資訊提示
                notes.append(
                    f"自由現金流為負 ({float(fcf):,.0f} 千元),係資本支出(擴廠/投資)所致,"
                    f"本業營運現金流為正,屬成長型投入而非營運惡化"
                )
            else:
                # 本業已無法自產現金、又在持續支出 → 才是真正的資金壓力
                if risk_level == "healthy":
                    risk_level = "watch"
                notes.append(f"自由現金流為負 ({float(fcf):,.0f} 千元) 且本業現金流不足,需留意資金壓力")

        if not notes:
            notes.append("營業與自由現金流健康")
        return {"risk_level": risk_level, "notes": notes}

    # ==================================================================
    # 主評估
    # ==================================================================
    def evaluate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行硬門檻檢查 + 加權評分 + 獲利品質 + 現金流健康。
        缺失非核心欄位 (如 cash_quality) 的績優股能順利通關;缺漏會降低 confidence。
        """
        raw_data = {
            "roe": data.get("roe"),
            "net_margin": data.get("net_margin"),
            "gross_margin": data.get("gross_margin"),
            # 金融股資產結構特殊 (存款/保單即資產),週轉率天生極低 → 豁免不計,避免結構性懲罰
            "asset_turnover": (None if data.get("is_financial") else data.get("asset_turnover")),
            "rev_cagr": data.get("rev_cagr"),
            "eps_cagr": data.get("eps_cagr"),
            "debt_to_asset": data.get("debt_to_asset"),
            "current_ratio": data.get("current_ratio"),
            "pe_vs_industry": data.get("pe_vs_industry"),
            "cash_quality": data.get("cash_quality")
        }
        is_passed = True
        reasons = []
        missing_fields: List[str] = []

        # 核心硬門檻檢查
        critical_checks = [
            ("debt_to_asset", "Debt too high"),
            ("current_ratio", "Current ratio too low"),
            ("net_margin", "Net margin too low")
        ]
        for field_name, error_msg in critical_checks:
            val = raw_data.get(field_name)
            if val is None or pd.isna(val):
                is_passed = False
                reasons.append(f"Missing core {field_name} data")
                missing_fields.append(field_name)
                continue
            if field_name == "debt_to_asset" and val > self.hard_filters["max_debt_to_asset"]:
                # 高總負債比未必是壞事,要分「好負債 vs 壞負債」:
                #   金融保險:存款/準備金即負債,負債比天生 90%+ → 豁免此門檻。
                #   代工/通路/航運等高週轉業:多為應付帳款等「營運負債」(供應鏈的免費資金),
                #     屬善用槓桿的好負債。只有「流動性不足 或 虧損」時才視為真正償債風險。
                is_financial = bool(data.get("is_financial", False))
                cr = raw_data.get("current_ratio")
                nm = raw_data.get("net_margin")
                liquidity_weak = (cr is not None and not pd.isna(cr) and float(cr) < 100.0)
                unprofitable = (nm is not None and not pd.isna(nm) and float(nm) < 0.0)
                extreme_debt = val > 92.0    # 極端高 (非金融) 仍視為風險,守住底線
                if is_financial:
                    pass                                     # 金融業豁免
                elif (liquidity_weak or unprofitable) or extreme_debt:
                    is_passed = False
                    why = "流動性不足" if liquidity_weak else ("虧損" if unprofitable else "負債極高")
                    reasons.append(f"{error_msg}: {val}% + {why} (壞負債)")
                # else: 高負債但流動性健康且獲利 → 營運槓桿(好負債),放行
            elif field_name == "current_ratio" and val < self.hard_filters["min_current_ratio"]:
                if not bool(data.get("is_financial", False)):   # 金融業流動比率定義不同,豁免
                    is_passed = False
                    reasons.append(f"{error_msg}: {val}%")
            elif field_name == "net_margin" and val < self.hard_filters["min_net_margin"]:
                is_passed = False
                reasons.append(f"{error_msg}: {val}%")

        # 非核心 cash_quality 容錯
        cq_val = raw_data.get("cash_quality")
        if cq_val is not None and not pd.isna(cq_val):
            if cq_val < self.hard_filters["min_cash_quality"]:
                is_passed = False
                reasons.append(f"Poor cash flow quality: {cq_val}")

        # --- 細項評分 ---
        scores = {}
        metrics = [
            ("roe", "profitability"), ("net_margin", "profitability"),
            ("gross_margin", "profitability"),
            ("rev_cagr", "growth"), ("eps_cagr", "growth"),
            ("debt_to_asset", "safety"), ("current_ratio", "safety"),
            ("pe_vs_industry", "valuation")
        ]
        if self.USE_ASSET_TURNOVER:
            metrics.append(("asset_turnover", "profitability"))
        for key, group in metrics:
            v = raw_data.get(key)
            if v is None or pd.isna(v):
                # asset_turnover 屬候選訊號且金融股豁免 → 缺漏不扣信心分
                if key not in missing_fields and key != "asset_turnover":
                    missing_fields.append(key)
            scores[key] = self._calculate_score(v, self.bounds.get(key, {}))

        # --- 加權總分 ---
        # 僅就「有資料」的指標取平均;整組皆缺時給中性 50 分,
        # 避免「缺資料」被當成「表現最差 (0 分)」而重複懲罰 (信心分數已另外反映缺漏)。
        def _avg_present(keys):
            vals = [scores[k] for k in keys
                    if raw_data.get(k) is not None and not pd.isna(raw_data.get(k))]
            return sum(vals) / len(vals) if vals else 50.0

        profit_keys = ["roe", "net_margin", "gross_margin"]
        if self.USE_ASSET_TURNOVER:
            profit_keys.append("asset_turnover")
        score_profit = _avg_present(profit_keys)
        score_growth = _avg_present(["rev_cagr", "eps_cagr"])
        score_safety = _avg_present(["debt_to_asset", "current_ratio"])
        pe_v = raw_data.get("pe_vs_industry")
        score_valuation = scores["pe_vs_industry"] if (pe_v is not None and not pd.isna(pe_v)) else 50.0
        total_score = (
            score_profit * self.weights["profitability"] +
            score_growth * self.weights["growth"] +
            score_safety * self.weights["safety"] +
            score_valuation * self.weights["valuation"]
        )

        # --- 新增:獲利品質 + 現金流健康 ---
        profit_quality = self._evaluate_profit_quality(data)
        cash_health = self._evaluate_cash_flow_health(data)

        # 現金流為負 → 依過濾邏輯列為高風險 (不直接踢除,交由 advisor 降評,但記錄)
        if cash_health["risk_level"] == "high_risk":
            reasons.append("High risk: negative operating cash flow / severe divergence")

        # --- 信心分數:每缺一個關鍵欄位扣分 ---
        confidence = max(0.0, 100.0 - len(set(missing_fields)) * 12.0)

        # --- 產出人類可讀 quality_flag (供報表 Quality_Flag 欄位) ---
        quality_flag = self._compose_quality_flag(profit_quality, cash_health, is_passed)

        return {
            "is_passed": is_passed,
            "reasons": reasons,
            "scores": scores,
            "group_scores": {
                "profitability": round(score_profit, 2),
                "growth": round(score_growth, 2),
                "safety": round(score_safety, 2),
                "valuation": round(score_valuation, 2),
            },
            "total_score": float(round(total_score, 2)),
            "profit_quality": profit_quality,       # 新增
            "cash_flow_health": cash_health,        # 新增
            "quality_flag": quality_flag,           # 新增 (報表用)
            "missing_fields": sorted(set(missing_fields)),
            "confidence": float(round(confidence, 1)),
        }

    @staticmethod
    def _compose_quality_flag(profit_quality: dict, cash_health: dict, is_passed: bool) -> str:
        """把獲利品質與現金流健康濃縮成一句報表旗標。"""
        parts = []
        if not is_passed:
            parts.append("⚠️未過基本面門檻")
        if cash_health.get("risk_level") == "high_risk":
            parts.append("⚠️現金流高風險")
        elif cash_health.get("risk_level") == "watch":
            parts.append("現金流需觀察")
        elif cash_health.get("risk_level") == "healthy":
            parts.append("現金流健康")
        if profit_quality.get("risk"):
            parts.append("⚠️獲利動態風險")
        elif profit_quality.get("operating_leverage"):
            parts.append("🚀本業獲利爆發")
        moat = profit_quality.get("moat")
        if moat and moat != "未知":
            parts.append(moat)
        return "·".join(parts) if parts else "數據不足"

    # ==================================================================
    # 工具
    # ==================================================================
    @staticmethod
    def _ensure_dataframe(data: Union[Dict[str, Any], pd.DataFrame]) -> pd.DataFrame:
        if isinstance(data, dict):
            return pd.DataFrame(data)
        return data.copy()

    def _safe_divide(self, numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator != 0 else 0