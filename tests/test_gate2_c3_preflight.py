# -*- coding: utf-8 -*-
"""Gate 2(C3)runner 的 preflight 測試。

⚠ 本檔不執行 Gate 2、不產生任何 CAGR / Sharpe / MDD / 月報酬 / bootstrap 數字。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

R = pytest.importorskip("gate2_c3_runner")
BS = pytest.importorskip("gate2b_bootstrap")


def test_frozen_settings_match_prereg():
    """§5-1 凍結值:L=12 / B=10,000 / seed=20260731,且 bootstrap 是 import 來的。"""
    assert R.BLOCK_LEN == 12
    assert R.N_BOOT == 10_000
    assert R.SEED == 20260731
    assert R.paired_block_bootstrap is BS.paired_block_bootstrap, \
        "必須 import 凍結實作,不得另寫一份"


def test_frozen_clock_and_columns():
    assert (R.CLOCK_LO, R.CLOCK_HI) == ("2019-08-01", "2026-03-31")
    assert R.N_MONTHS_EXPECTED == 80
    assert R.RET_COL == "fwd_x"
    assert R.REAL_COMP_COL == "real_composite"
    assert R.TOP_PCT == 20


def test_gate2b_guardrail_is_the_only_pass_condition():
    """Gate 2 唯一保留的通過條件是 2-B 的 MDD 風險護欄(§5 Gate 2)。"""
    assert R.MDD_GUARDRAIL_PCT == -22.01
    # V0 −17.01% 減 5pp
    assert round(R.V0_BASELINE["gate2b_composite_int_c2"]["MDD_pct"] - 5.0, 2) == -22.01


def test_v0_baselines_match_frozen_prereg_numbers():
    a = R.V0_BASELINE["gate2a_composite_alone"]
    b = R.V0_BASELINE["gate2b_composite_int_c2"]
    assert (a["CAGR_pct"], a["Sharpe"], a["MDD_pct"]) == (24.61, 1.09, -22.51)
    assert (b["CAGR_pct"], b["Sharpe"], b["MDD_pct"]) == (28.00, 1.34, -17.01)


def test_execution_path_is_fail_closed():
    """`run_gate2` 本輪不可執行。"""
    with pytest.raises(SystemExit, match="本輪不可執行"):
        R.run_gate2()


def test_cli_without_preflight_only_is_blocked(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gate2_c3_runner.py"])
    with pytest.raises(SystemExit) as e:
        R.main()
    assert e.value.code == 2
    assert "fail-closed" in capsys.readouterr().out


def test_c3_qualification_is_read_not_hardcoded():
    """C3 的資格必須從 Gate 1 execution manifest 讀,改掉通過者就該拒絕。"""
    g1 = {"arms": list("ABCDEFGHIJKL"),
          "results": {"passed": [False] * 12,
                      "G1a": {"T_star": 1.0}, "G1c": {"T_star": 1.0}}}
    v = R.verify_c3_is_sole_gate1_passer(g1)
    assert v["c3_is_sole_passer"] is False
    assert v["failure"]

    g1["arms"] = ["A1", "A2", "A3", "A4", "C1", "C3",
                  "B1", "B2", "B3", "B4", "B5", "C2"]
    g1["results"]["passed"] = [a == "C3" for a in g1["arms"]]
    assert R.verify_c3_is_sole_gate1_passer(g1)["c3_is_sole_passer"] is True


# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def rep():
    try:
        return R.preflight()
    except SystemExit as exc:
        pytest.skip(f"缺輸入,跳過:{exc}")


def test_preflight_binds_all_four_input_hashes(rep):
    for k in ("c3_panel", "v0_panel", "gate1_execution_manifest",
              "gate1_provenance_overlay"):
        assert k in rep["inputs"], f"preflight 未綁定 {k}"
        assert len(rep["inputs"][k]["sha256"]) == 64


def test_preflight_produces_no_performance_numbers(rep):
    """最重要的一條:preflight 不得帶出任何績效數字。"""
    assert rep["performance_computed"] is False
    blob = json.dumps(rep, ensure_ascii=False, default=str)
    for banned in ("bootstrap_ci", "delta_cagr", "delta_sharpe",
                   "monthly_returns", "observed_cagr", "observed_sharpe",
                   "observed_mdd"):
        assert banned not in blob, f"preflight 輸出含績效欄位 {banned}"
    # V0 基準是**凍結對照值**,不是本次計算 —— 只准出現在 frozen.v0_baseline
    assert "v0_baseline" in rep["frozen"]


def test_preflight_reports_missing_s8_steps_without_backfilling(rep):
    """§8 稽核只報告缺什麼,不得自行補跑。"""
    au = rep["prereg_s8_audit"]
    assert set(au["missing_steps"]) == {"s8_4_train_val_diagnostics",
                                        "s8_5_validation_select_walkforward"}
    assert au["ordering_violation"] is True
    assert au["steps"]["s8_6_oos_once"]["present"] is True
    # 診斷面板 log 不得被當成 Train/Validation 診斷
    assert "不是 Train/Validation" in au["steps"]["s8_4_train_val_diagnostics"]["note"]


# ---------------------------------------------------------------------------
# 可用報酬母體(Codex 2026-08-02 §2):不得拿 C3 原始 parquet 列數當樣本
# ---------------------------------------------------------------------------
def test_return_universe_comes_from_load_real_panel_not_raw_parquet(rep):
    ru = rep["return_universe"]
    assert "load_real_panel" in ru["source"]
    assert "drop_na_ret=True" in ru["source"] and "min_coverage=1.0" in ru["source"]
    assert ru["return_line"] == "fwd_x"
    # canonical 必須嚴格小於 C3 原始面板時鐘內列數 —— 兩者混用就是把無報酬資格的列算進樣本
    assert ru["canonical_keys_in_clock"] < ru["c3_rows_in_clock_raw_panel"], \
        "canonical 母體不可等於 C3 原始列數 —— 那代表沒有真的過 exec_ret 篩選"


def test_return_universe_numbers_are_reported(rep):
    ru = rep["return_universe"]
    assert ru["canonical_keys_in_clock"] == 96_956
    assert ru["n_months_in_clock"] == 80
    assert ru["c3_coverage"] == 1.0
    assert ru["canonical_keys_missing_c3_score"] == 0
    assert ru["c3_only_rows_without_return_eligibility"] == 999
    assert ru["merged_rows"] == ru["canonical_keys_in_clock"]
    assert "不具報酬資格" in ru["note_excluded"] or "沒有可執行" in ru["note_excluded"]


def test_c3_missing_a_canonical_key_must_fail(monkeypatch):
    """C3 若缺 canonical 鍵 → preflight 必須失敗。"""
    import pandas as pd
    real = pd.read_parquet

    def short_c3(path, *a, **k):
        df = real(path, *a, **k)
        if "arm_C3_" in str(path):
            df = df.iloc[:-5000]          # 砍掉一段,製造缺鍵
        return df

    monkeypatch.setattr(R.pd, "read_parquet", short_c3)
    rep = R.preflight()
    assert rep["preflight_passed"] is False
    assert any("缺 C3 分數" in m for m in rep["failures"]), rep["failures"]


# ---------------------------------------------------------------------------
# 程序違序必須 fail-closed(Codex 2026-08-02 §1)
# ---------------------------------------------------------------------------
def test_ordering_violation_makes_preflight_fail(rep):
    """現況就是違序 —— preflight 必須是 False,不得因為其他檢查都過就放行。"""
    assert rep["prereg_s8_audit"]["ordering_violation"] is True
    assert rep["preflight_passed"] is False, \
        "有程序違序卻 preflight_passed=true —— 會被誤讀成可執行 Gate 2"
    assert any("執行順序違序" in m for m in rep["failures"])


def test_no_violation_would_allow_pass(monkeypatch):
    """反向:違序旗標解除時,其他檢查全過就該放行 —— 證明失敗確實來自違序。"""
    real_audit = R.audit_prereg_s8

    def clean_audit():
        a = real_audit()
        a["ordering_violation"] = False
        a["verdict"] = "(測試)假設違序已處置"
        return a

    monkeypatch.setattr(R, "audit_prereg_s8", clean_audit)
    rep = R.preflight()
    assert rep["preflight_passed"] is True, rep["failures"]


def test_cli_exits_nonzero_when_preflight_fails(monkeypatch):
    """fail-closed 必須反映在退出碼,否則自動化流程會當成通過。"""
    monkeypatch.setattr(sys, "argv", ["gate2_c3_runner.py", "--preflight-only"])
    with pytest.raises(SystemExit) as e:
        R.main()
    assert e.value.code == 3


def test_protocol_deviation_record_exists_and_states_irreversibility():
    """協定偏差記錄必須存在,且明講補跑不能恢復盲測性。"""
    p = REPO_ROOT / "docs" / "協定偏差_FaceRedesignV2_S8.md"
    assert p.exists(), "缺協定偏差記錄草案"
    t = p.read_text(encoding="utf-8")
    assert "事後" in t and "探索" in t
    assert "不能恢復盲測性" in t or "無法恢復盲測性" in t
    assert "不改寫已落地的 Gate 1 結果" in t
