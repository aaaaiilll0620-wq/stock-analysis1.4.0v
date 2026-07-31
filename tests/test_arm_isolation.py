"""candidate arm 的**順序隔離**回歸測試。

為什麼要有這個測試:`build_arm_panel.apply_arm()` 原本是「只碰這個 arm 需要的那一個
模組級旋鈕」,結果**兩個方向**都會殘留前一個 arm 的狀態:

  · `v0` / `A1` / `A2` 不會清 `RESEARCH_ARM`(A3/A4 的旗標)
    → 先跑 A3 再跑 A1,A1 的面板會**同時**帶著 A3 的缺值語意;
  · `A3` / `A4` 不會清 `_rs_bench_bundle` / `_bench_state`(A1/A2 的注入)
    → 先跑 A1 再跑 A3,A3 的面板會**同時**帶著補過的 0050。

兩個方向都是**靜默**污染:分數看起來完全正常、不噴任何錯、驗收閘門也抓不到
(因為閘門只比 V0,而污染後的 arm 確實與 V0 不同)。而 Gate 1 的 `ΔIC` 會把
那個混合體當成「單一變更」來檢定 —— 預註冊 §4-5 宣告的搜尋空間就失效了。

**修法**:`apply_arm()` 改成**宣告完整狀態** —— 先 `reset_arm_state()` 把每一個旋鈕
復位成 V0,再打開這個 arm 要的那一個。結果因此與「先前套用過哪個 arm」無關。

目前的執行路徑(每個 arm 各開一個 `python -m` 行程)本來就不會踩到,
但這個測試把「不可能踩到」從**巧合**變成**結構保證**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

BAP = pytest.importorskip("beat_0050.realbody.build_arm_panel")

V0_STATE = {"bt.RESEARCH_ARM": None, "val.RESEARCH_ARM": None,
            "rs_injected": False, "regime_injected": False}


@pytest.fixture(autouse=True)
def _clean_state():
    """每個測試前後都復位 —— 免得這支測試自己污染同一 pytest 行程裡的其他測試。"""
    BAP.reset_arm_state()
    yield
    BAP.reset_arm_state()


def test_v0_state_is_all_knobs_off():
    BAP.apply_arm("v0")
    assert BAP.arm_state() == V0_STATE


@pytest.mark.parametrize("arm,expected", [
    ("A3", {**V0_STATE, "bt.RESEARCH_ARM": "A3"}),
    ("A4", {**V0_STATE, "val.RESEARCH_ARM": "A4"}),
])
def test_flag_arms_set_exactly_one_knob(arm, expected):
    BAP.apply_arm(arm)
    assert BAP.arm_state() == expected


def test_unknown_arm_raises():
    with pytest.raises(SystemExit):
        BAP.apply_arm("A9")


# ---------------------------------------------------------------------------
# 順序隔離 —— 這是本檔的核心
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("first", ["A3", "A4"])
@pytest.mark.parametrize("second", ["v0", "A3", "A4"])
def test_flag_arm_then_other_arm_leaves_no_residue(first, second):
    """先套一個旗標 arm,再套另一個 arm → 第二個的狀態必須與「單獨套用」完全相同。

    修好之前:`apply_arm('A3')` → `apply_arm('v0')` 會留下 `bt.RESEARCH_ARM == 'A3'`,
    於是那一輪 v0 的面板其實是 A3。
    """
    BAP.apply_arm(first)
    BAP.apply_arm(second)
    after_sequence = BAP.arm_state()

    BAP.reset_arm_state()
    BAP.apply_arm(second)
    standalone = BAP.arm_state()

    assert after_sequence == standalone, (
        f"套用順序 {first} → {second} 的狀態與單獨套用 {second} 不同:"
        f"{after_sequence} vs {standalone} —— 前一個 arm 有殘留")


def test_a3_and_a4_are_mutually_exclusive():
    """A3 與 A4 不得同時生效(預註冊:每個 arm 只有一類主要變更)。"""
    BAP.apply_arm("A3")
    BAP.apply_arm("A4")
    st = BAP.arm_state()
    assert st["bt.RESEARCH_ARM"] is None, "切到 A4 之後 A3 的旗標必須已清除"
    assert st["val.RESEARCH_ARM"] == "A4"

    BAP.apply_arm("A3")
    st = BAP.arm_state()
    assert st["val.RESEARCH_ARM"] is None, "切到 A3 之後 A4 的旗標必須已清除"
    assert st["bt.RESEARCH_ARM"] == "A3"


def test_reset_restores_v0_from_every_arm():
    for arm in ("A3", "A4"):
        BAP.apply_arm(arm)
        BAP.reset_arm_state()
        assert BAP.arm_state() == V0_STATE, f"從 {arm} 復位後不是 V0 狀態"


# ---------------------------------------------------------------------------
# A1 / A2 的注入方向 —— 需要讀 0050,拿不到就 skip(不讓環境缺資料變成假失敗)
# ---------------------------------------------------------------------------
def _splice_available() -> bool:
    try:
        BAP.spliced_benchmark()
        return True
    except BaseException:
        return False


needs_0050 = pytest.mark.skipif(not _splice_available(),
                                reason="0050 拼接序列不可得(缺快取或 repo parquet)")


@needs_0050
def test_a1_injects_only_rs_consumer():
    BAP.apply_arm("A1")
    st = BAP.arm_state()
    assert st["rs_injected"] is True
    assert st["regime_injected"] is False, "A1 不得碰 regime 消費端"
    assert st["bt.RESEARCH_ARM"] is None and st["val.RESEARCH_ARM"] is None


@needs_0050
def test_a2_injects_only_regime_consumer():
    BAP.apply_arm("A2")
    st = BAP.arm_state()
    assert st["regime_injected"] is True
    assert st["rs_injected"] is False, "A2 不得碰 RS 消費端"
    assert st["bt.RESEARCH_ARM"] is None and st["val.RESEARCH_ARM"] is None


@needs_0050
@pytest.mark.parametrize("first,second", [
    ("A1", "A2"), ("A2", "A1"),          # 兩個注入 arm 互相殘留
    ("A1", "v0"), ("A2", "v0"),          # 注入 arm → v0 必須乾淨
    ("A1", "A3"), ("A2", "A4"),          # 注入 arm → 旗標 arm(原本會殘留 0050)
    ("A3", "A1"), ("A4", "A2"),          # 旗標 arm → 注入 arm(原本會殘留旗標)
])
def test_sequential_arms_never_leak(first, second):
    """任兩個 arm 依序套用,第二個的狀態必須等於單獨套用它。"""
    BAP.apply_arm(first)
    BAP.apply_arm(second)
    seq = BAP.arm_state()

    BAP.reset_arm_state()
    BAP.apply_arm(second)
    alone = BAP.arm_state()

    assert seq == alone, (
        f"{first} → {second} 有殘留:{seq} vs 單獨 {second} 的 {alone}")
