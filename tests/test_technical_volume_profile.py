"""
籌碼成本區 (Volume Profile) 單元測試。

重點鎖住『雙峰量能真空 / 追高』情境的回歸:
當股票由低基期主成本區 (POC) 大幅噴出、頂部又有高檔換手平台、中間為量能真空時,
現價雖遠離 POC,卻曾被誤判為『成本區內』並被下游 advisor 標成
『現價位於成本帶下緣(偏防守區)』——一個把追高頂部說成防守買點的危險誤導。

同時涵蓋:
  - lookback 預設 = 90
  - 已移除現價 ±25% 價格帶硬限縮
  - 支撐改以『全部高量能節點 (HVN)』掃描,避免支撐與 POC 硬重合(4958)、
    並能標出主成本區上緣的中繼換手節點(8046)。
"""
import inspect
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from core.technical_analysis import TechnicalEngine
from core.advisor import InvestmentAdvisor

_REAL_4958_CSV = os.path.join(os.path.dirname(__file__), "data", "4958_actual_data.csv")


# --------------------------------------------------------------------------- #
# 測試資料產生器 (以固定 seed 保持可重現)
# --------------------------------------------------------------------------- #
def _df(closes, vols, start="2026-03-01"):
    return pd.DataFrame({
        "date": pd.date_range(start, periods=len(closes)),
        "close": list(closes),
        "volume": list(vols),
    })


def _bimodal_air_gap(seed=4958, base=202, top=586, last=None):
    """重底部主成本區 + 中間量能真空 + 頂部高檔換手平台(現價貼著頂部)。"""
    rng = np.random.default_rng(seed)
    closes, vols = [], []
    for _ in range(48):                                  # 底部累積(主成本區)
        closes.append(base + rng.normal(0, 4)); vols.append(int(rng.integers(7000, 11000)))
    for p in np.linspace(base + 13, top - 26, 25):       # 稀薄拉抬(量能真空)
        closes.append(p + rng.normal(0, 3)); vols.append(int(rng.integers(1000, 2200)))
    for _ in range(15):                                  # 頂部高檔換手平台
        closes.append(top + rng.normal(0, 5)); vols.append(int(rng.integers(6000, 9000)))
    closes.append(top if last is None else last); vols.append(8000)
    return _df(closes, vols)


def _stock_from_vp(vp, cur):
    """把 volume_profile 輸出對映成 advisor._buy_zone_note 需要的 stock 屬性
    (對應 data_provider.py 的實際 passthrough)。"""
    return SimpleNamespace(
        cost_zone_poc=vp["poc"], cost_zone_status=vp["status"], current_price=cur,
        cost_zone_support=vp["support"], cost_zone_resistance=vp["resistance"],
        value_area_low=vp["val"], value_area_high=vp["vah"],
        cost_zone_confidence=None, cost_zone_hvn_levels=[],
    )


# --------------------------------------------------------------------------- #
# 預設值 / 舊邏輯移除
# --------------------------------------------------------------------------- #
class TestVolumeProfileDefaults:
    def test_lookback_default_is_90(self):
        sig = inspect.signature(TechnicalEngine.calculate_volume_profile)
        assert sig.parameters["lookback"].default == 90

    def test_no_plus_minus_25pct_price_band_clamp(self):
        # 主成本區落在現價 -60% 處。舊版 ±25% 價格帶會把它排除,POC 被迫貼近現價;
        # 移除價格帶後,POC 必須落在真正的量能重心(遠低於現價 ±25% 帶的下緣)。
        rng = np.random.default_rng(1)
        closes, vols = [], []
        for _ in range(60):
            closes.append(100 + rng.normal(0, 2)); vols.append(int(rng.integers(8000, 12000)))
        for p in np.linspace(105, 250, 30):
            closes.append(p + rng.normal(0, 2)); vols.append(int(rng.integers(1000, 2000)))
        vp = TechnicalEngine.calculate_volume_profile(_df(closes, vols))
        cur = closes[-1]
        assert vp["poc"] < cur * 0.75            # 若仍有 ±25% 硬限縮,POC 不可能落在此處


# --------------------------------------------------------------------------- #
# 核心:雙峰量能真空 / 追高
# --------------------------------------------------------------------------- #
class TestBimodalAirGap:
    def test_status_flags_chase_never_defense(self):
        vp = TechnicalEngine.calculate_volume_profile(_bimodal_air_gap())
        assert vp["price_vs_poc_pct"] is not None and vp["price_vs_poc_pct"] > 50   # 追高:遠高於 POC
        assert "上方" in vp["status"]                 # 必須標為追高/上方
        assert "下方" not in vp["status"]             # 關鍵:含 "下方" 會被 advisor 誤分流成『相對便宜』
        assert "成本區內" not in vp["status"]         # 也不可被當成成本帶內

    def test_support_not_glued_to_price(self):
        df = _bimodal_air_gap()
        vp = TechnicalEngine.calculate_volume_profile(df)
        cur = float(df["close"].iloc[-1])
        assert vp["support"] is not None
        # 支撐不得貼著現價(頂部平台),須明顯在下方(真空另一側的主成本區)
        assert (cur - vp["support"]) / cur > 0.10

    def test_advisor_emits_chase_warning_not_defense(self):
        df = _bimodal_air_gap()
        vp = TechnicalEngine.calculate_volume_profile(df)
        cur = round(float(df["close"].iloc[-1]))
        note = InvestmentAdvisor(min_score=60.0)._buy_zone_note(_stock_from_vp(vp, cur))
        assert "追高" in note            # 正確:警示追高風險
        assert "防守" not in note        # 原本的危險誤導字樣不得出現
        assert "相對便宜" not in note


# --------------------------------------------------------------------------- #
# 支撐應能標出中繼換手節點,且不與 POC 硬重合 (8046 型)
# --------------------------------------------------------------------------- #
class TestIntermediateShelfSupport:
    def test_support_is_distinct_shelf_not_poc(self):
        rng = np.random.default_rng(21)
        closes, vols = [], []
        for _ in range(30):                                  # 主成本區 POC ~908
            closes.append(905 + rng.normal(0, 4)); vols.append(int(rng.integers(7000, 10000)))
        for _ in range(18):                                  # 主成本區上緣換手節點 ~940
            closes.append(940 + rng.normal(0, 4)); vols.append(int(rng.integers(4000, 6500)))
        for p in np.linspace(965, 1190, 22):
            closes.append(p + rng.normal(0, 6)); vols.append(int(rng.integers(1500, 2800)))
        for _ in range(8):
            closes.append(1215 + rng.normal(0, 6)); vols.append(int(rng.integers(2500, 4200)))
        closes.append(1218); vols.append(3000)
        vp = TechnicalEngine.calculate_volume_profile(_df(closes, vols))
        cur = float(closes[-1])
        assert vp["support"] is not None
        assert vp["support"] != vp["poc"]                    # 支撐不再與 POC 硬重合
        assert vp["poc"] < vp["support"] < cur               # 支撐為 POC 上方、現價下方的中繼節點


# --------------------------------------------------------------------------- #
# 回歸:正常情境不得被誤判為追高
# --------------------------------------------------------------------------- #
class TestRegressionLegitCases:
    def test_in_zone_consolidation_no_false_air_gap(self):
        # 緊密盤整:現價貼近 POC,絕不可觸發『量能真空/追高』誤判
        # (注意:隨機游走末點偶爾略高於 VAH 而顯示普通 "上方" 屬既有正常行為,非本次修正對象;
        #  這裡只鎖住不得誤報 air-gap 追高。)
        rng = np.random.default_rng(0)
        closes = [120 + rng.normal(0, 2) for _ in range(90)]
        vols = [int(rng.integers(4000, 6000)) for _ in range(90)]
        vp = TechnicalEngine.calculate_volume_profile(_df(closes, vols))
        assert abs(vp["price_vs_poc_pct"]) < 25       # 現價貼近 POC
        assert "量能真空" not in vp["status"]          # 不得觸發雙峰真空追高判定

    def test_downtrend_below_cost_zone(self):
        rng = np.random.default_rng(2)
        closes = list(np.linspace(150, 100, 90) + rng.normal(0, 1.5, 90))
        vols = [int(rng.integers(4000, 6000)) for _ in range(90)]
        vp = TechnicalEngine.calculate_volume_profile(_df(closes, vols))
        assert "下方" in vp["status"]

    def test_insufficient_data_returns_empty(self):
        vp = TechnicalEngine.calculate_volume_profile(_df([100, 101, 102], [1000, 1100, 1200]))
        assert vp["poc"] is None and vp["status"] == ""


# --------------------------------------------------------------------------- #
# 回歸:壓力不得等於現價自身 bin(2330 型「壓力約 XXXX(+0%)」假壓力)
# 情境:主成本區 110(POC)、現價 118 坐在次級換手平台(HVN bin)內、上方 130 另有換手節點。
# 舊版分支②③ above 用 c >= cur → 壓力 = 自身 bin 中心 ≈ 現價(+0%),
# 連鎖誤觸 advisor 的 near_resistance →『現價位於成本帶上緣(接近壓力區)』。
# --------------------------------------------------------------------------- #
class TestResistanceNotOwnBin:
    def _vp_and_cur(self):
        rng = np.random.default_rng(2330)
        closes, vols = [], []
        for _ in range(45):                                  # 主成本區 POC ~110
            closes.append(110 + rng.normal(0, 1.5)); vols.append(int(rng.integers(8000, 11000)))
        for _ in range(25):                                  # 現價所在的次級換手平台 ~118
            closes.append(118 + rng.normal(0, 1.2)); vols.append(int(rng.integers(5000, 7000)))
        for _ in range(19):                                  # 上方換手節點 ~130
            closes.append(130 + rng.normal(0, 1.5)); vols.append(int(rng.integers(4000, 6000)))
        closes.append(118.0); vols.append(6000)              # 收在平台內(+7% vs POC,成本區內)
        vp = TechnicalEngine.calculate_volume_profile(_df(closes, vols))
        return vp, float(closes[-1])

    def test_resistance_strictly_above_current_price(self):
        vp, cur = self._vp_and_cur()
        assert vp["resistance"] is not None
        assert vp["resistance"] > cur * 1.005                # 壓力須明確高於現價,不得同價位帶

    def test_advisor_note_never_shows_zero_pct_resistance(self):
        vp, cur = self._vp_and_cur()
        note = InvestmentAdvisor(min_score=60.0)._buy_zone_note(_stock_from_vp(vp, cur))
        assert "壓力約" in note
        assert "(+0%)" not in note                           # 原始 bug:壓力=現價 → (+0%)

    def test_new_keys_present(self):
        vp, _ = self._vp_and_cur()
        assert vp["confidence"] is not None and 0 <= vp["confidence"] <= 100
        assert vp["hvn_levels"], "HVN 節點列表不得為空"
        # hvn_levels 依量能排序:第一個必為 POC 所在價位帶
        assert abs(vp["hvn_levels"][0] - vp["poc"]) < 2.0
        assert isinstance(vp["lvn_levels"], list)

    def test_empty_result_contains_new_keys(self):
        vp = TechnicalEngine.calculate_volume_profile(_df([100, 101], [1000, 1200]))
        assert vp["confidence"] is None
        assert vp["hvn_levels"] == [] and vp["lvn_levels"] == []


# --------------------------------------------------------------------------- #
# 真實資料回歸:4958(2026-03 ~ 2026-07,現價 588、主成本 ~211)
# 這是一檔『由低基期連續強漲、量能沿路墊高』的股票(非中空雙峰)。
# 曾出現的問題:(1) 誤報防守區;(2) 支撐被推到過低的 522(-11%)。
# 期望:標為追高、支撐落在近期換手密集帶下緣(約 -3%,不得低到 522)。
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not os.path.exists(_REAL_4958_CSV), reason="缺 4958 真實資料檔")
class TestReal4958:
    def _vp(self):
        df = pd.read_csv(_REAL_4958_CSV)
        return TechnicalEngine.calculate_volume_profile(df), round(float(df["close"].iloc[-1]))

    def test_flagged_as_chase_not_defense(self):
        vp, cur = self._vp()
        assert "上方" in vp["status"] and "下方" not in vp["status"]
        assert "成本區內" not in vp["status"]
        assert vp["price_vs_poc_pct"] > 100          # 現價遠高於主成本(+179%)

    def test_support_near_recent_floor_not_too_low(self):
        vp, cur = self._vp()
        assert vp["support"] is not None
        assert vp["support"] != vp["poc"]            # 不得與主成本硬重合
        # 支撐須落在近期換手密集帶(現價下方一個量能節點),而非過低的 522(-11%)
        assert vp["support"] > 540
        assert 0.0 < (cur - vp["support"]) / cur <= 0.08

    def test_advisor_message_is_safe(self):
        vp, cur = self._vp()
        stock = _stock_from_vp(vp, cur)
        note = InvestmentAdvisor(min_score=60.0)._buy_zone_note(stock)
        assert "追高" in note
        assert "防守" not in note and "相對便宜" not in note
