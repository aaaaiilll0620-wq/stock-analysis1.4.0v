# -*- coding: utf-8 -*-
"""Gate 1 CLI 執行順序的合成測試 —— 真正走 `main()`。

**要防的具體漏洞**(Codex 2026-08-02 複核指出):
`verify_overlay_or_die()` 的 47 項檢查**本身就會逐檔讀取並雜湊 12 個 candidate panel
與 V0**。舊版把它排在武裝旗標/授權/認領**之前**,等於任何人打一條指令就能讓程式
讀過一輪 candidate —— 授權與單發射擊的認領形同虛設。

凍結的正確順序:
    1 CLI armed flag → 2 authorization(只讀授權檔 + overlay 檔本身)
    → 3 exclusive-create STARTED → 4 verify_overlay_or_die(此後才可讀 candidate)
    → 5 assemble + preflight → 6 run_gate1

本檔用 monkeypatch 把 `verify_overlay_or_die` / `assemble` / `preflight` 換成**間諜**,
記錄呼叫順序,並斷言未授權時它們**一次都沒被呼叫**。

⚠ 不執行 `--part gate` 的真實流程、不讀任何真實面板、不產生任何 candidate 統計量。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

R = pytest.importorskip("gate1_assemble_12arm")
OVL = pytest.importorskip("build_gate1_provenance_overlay")

PROG = "gate1_assemble_12arm.py"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    """把 runner 的輸出目錄與 overlay 路徑導到暫存區,並裝上間諜。"""
    overlay = tmp_path / "GATE1_PROVENANCE_OVERLAY.json"
    overlay.write_text('{"fake": "overlay"}', encoding="utf-8")

    monkeypatch.setattr(OVL, "OUT", overlay)
    monkeypatch.setattr(R, "OUT_DIR", tmp_path)

    calls: list[str] = []

    def spy_verify():
        calls.append("verify_overlay")
        return {"items_verified": 47, "passed": True,
                "overlay_sha256": R.sha256_file(overlay), "overlay_path": str(overlay)}

    def spy_assemble():
        calls.append("assemble")
        return None, {}

    def spy_preflight(d, rep):
        calls.append("preflight")
        raise RuntimeError("合成測試:preflight 到此為止,不進 run_gate1")

    real_claim = R.claim_execution

    def spy_claim(**kw):
        calls.append("claim")
        return real_claim(**kw)

    monkeypatch.setattr(R, "verify_overlay_or_die", spy_verify)
    monkeypatch.setattr(R, "assemble", spy_assemble)
    monkeypatch.setattr(R, "preflight", spy_preflight)
    monkeypatch.setattr(R, "claim_execution", spy_claim)

    def write_auth(overlay_sha=None, token=None) -> Path:
        p = tmp_path / "auth.json"
        p.write_text(json.dumps({
            "authorizes": token or R.AUTH_TOKEN,
            "overlay_sha256": overlay_sha or R.sha256_file(overlay),
            "authorized_by": "synthetic-test",
        }, ensure_ascii=False), encoding="utf-8")
        return p

    def run(argv):
        monkeypatch.setattr(sys, "argv", [PROG] + argv)
        return R.main()

    return {"tmp": tmp_path, "overlay": overlay, "calls": calls,
            "write_auth": write_auth, "run": run,
            "started": tmp_path / R.STARTED_NAME,
            "manifest": tmp_path / R.MANIFEST_NAME,
            "failure": tmp_path / R.FAILURE_NAME}


def _assert_no_candidate_touched(cli):
    assert "verify_overlay" not in cli["calls"], \
        "未授權就呼叫了 verify_overlay_or_die —— 它會讀取並雜湊 12 個 candidate panel"
    assert "assemble" not in cli["calls"], "未授權就讀取了 candidate 面板"
    assert not cli["started"].exists(), "未授權不該留下 STARTED"


# ---------------------------------------------------------------------------
# 1. 未 armed / 授權無效 → verify_overlay_or_die 與 assemble 都不得被呼叫
# ---------------------------------------------------------------------------
def test_not_armed_touches_no_candidate(cli):
    with pytest.raises(SystemExit) as e:
        cli["run"](["--part", "gate"])
    assert e.value.code == 2
    assert cli["calls"] == [], f"未 armed 卻有呼叫:{cli['calls']}"
    _assert_no_candidate_touched(cli)


def test_armed_but_no_authorization_touches_no_candidate(cli):
    with pytest.raises(SystemExit, match="未提供授權檔"):
        cli["run"](["--part", "gate", R.ARM_FLAG])
    _assert_no_candidate_touched(cli)


def test_authorization_bound_to_wrong_overlay_touches_no_candidate(cli):
    auth = cli["write_auth"](overlay_sha="0" * 64)
    with pytest.raises(SystemExit, match="綁定的 overlay 與現行的不符"):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])
    _assert_no_candidate_touched(cli)


def test_authorization_with_wrong_token_touches_no_candidate(cli):
    auth = cli["write_auth"](token="some-other-token")
    with pytest.raises(SystemExit, match="authorizes"):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])
    _assert_no_candidate_touched(cli)


def test_overlay_changed_after_authorization_touches_no_candidate(cli):
    """先簽授權,再改 overlay → 必須在讀 candidate 之前擋下。"""
    auth = cli["write_auth"]()
    cli["overlay"].write_text('{"fake": "overlay TAMPERED"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="綁定的 overlay 與現行的不符"):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])
    _assert_no_candidate_touched(cli)


# ---------------------------------------------------------------------------
# 2. 授權通過 → claim 必須早於 verify_overlay_or_die
# ---------------------------------------------------------------------------
def test_claim_happens_before_overlay_verification_and_assemble(cli):
    auth = cli["write_auth"]()
    with pytest.raises(RuntimeError, match="preflight 到此為止"):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])

    assert cli["calls"] == ["claim", "verify_overlay", "assemble", "preflight"], \
        f"順序錯誤:{cli['calls']}"
    assert cli["calls"].index("claim") < cli["calls"].index("verify_overlay"), \
        "verify_overlay_or_die 會讀 candidate,必須在 claim_execution 之後"


def test_started_lands_before_any_candidate_access(cli):
    """STARTED 必須在 verify_overlay / assemble 之前就落地。"""
    auth = cli["write_auth"]()
    landed: list[bool] = []

    real_verify = R.verify_overlay_or_die

    def check_then_verify():
        landed.append(cli["started"].exists())
        return real_verify()

    import unittest.mock as _m
    with _m.patch.object(R, "verify_overlay_or_die", check_then_verify):
        with pytest.raises(RuntimeError):
            cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])

    assert landed == [True], "進入 verify_overlay_or_die 時 STARTED 尚未落地"


# ---------------------------------------------------------------------------
# 3. 失敗處理:STARTED 保留 + FAILURE 落地 + 禁止重跑
# ---------------------------------------------------------------------------
def test_preflight_failure_keeps_started_and_writes_failure(cli):
    auth = cli["write_auth"]()
    with pytest.raises(RuntimeError):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])

    assert cli["started"].exists(), "失敗後 STARTED 必須保留"
    assert cli["failure"].exists(), "失敗必須寫 FAILURE"
    assert not cli["manifest"].exists(), "失敗不得產生 EXECUTION_MANIFEST"

    rec = json.loads(cli["failure"].read_text(encoding="utf-8"))
    assert rec["error_type"] == "RuntimeError"
    assert rec["started_record"]["baseline_idx"] == list(R.BASELINE_IDX)

    # 封存前再跑一次 → 必須在 claim 就被拒
    cli["calls"].clear()
    with pytest.raises(SystemExit, match="已存在"):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])
    assert "verify_overlay" not in cli["calls"] and "assemble" not in cli["calls"]


def test_started_payload_records_everything_required(cli):
    """STARTED 必須記錄 Codex 指定的全部欄位。"""
    auth = cli["write_auth"]()
    with pytest.raises(RuntimeError):
        cli["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])

    rec = json.loads(cli["started"].read_text(encoding="utf-8"))
    for key in ("started_at", "command", "overlay_sha256", "runner_sha256",
                "frozen_impl_sha256", "authorization_path", "authorization_sha256",
                "baseline_idx", "baseline_map", "n_perm", "seed"):
        assert key in rec, f"STARTED 缺 {key}"
    assert rec["baseline_idx"] == list(R.BASELINE_IDX)
    assert rec["n_perm"] == R.N_PERM and rec["seed"] == R.SEED
    assert rec["baseline_map"]["B1"] == "arm_C3" and rec["baseline_map"]["A1"] == "V0"


def test_preflight_part_never_claims_or_requires_authorization(cli):
    """`--part preflight` 不走武裝流程,也不得留下任何鎖檔。"""
    with pytest.raises(RuntimeError, match="preflight 到此為止"):
        cli["run"](["--part", "preflight"])
    assert cli["calls"] == ["assemble", "preflight"]
    assert not cli["started"].exists()
    assert not cli["manifest"].exists()


# ---------------------------------------------------------------------------
# 4. 步驟 6 的封存失敗(Codex 2026-08-02 最終複核)
#    開火成功但結果封存失敗 —— 最危險的一種:那一槍已經打出去了。
# ---------------------------------------------------------------------------
FAKE_RES = {
    "decision_rule": "G1-a AND G1-c", "n_months_M_star": 80,
    "settings": {"n_perm": 10, "seed": 1, "alpha": 0.05, "baseline_idx": list(R.BASELINE_IDX)},
    "G1a": {"T_star": 1.0, "t": [0.0] * 12, "p_adj": [0.5] * 12,
            "rho_hat": None, "rho_status": "ok", "degenerate": False},
    "G1c": {"T_star": 1.0, "t": [0.0] * 12, "p_adj": [0.5] * 12,
            "rho_hat": None, "rho_status": "ok", "degenerate": False},
    "pass_G1a": [False] * 12, "pass_G1c": [False] * 12, "passed": [False] * 12,
}


@pytest.fixture(scope="module")
def real_rep():
    """**真實** `assemble()` + `preflight()` 的回傳 —— 契約的唯一來源。

    attempt 1 的根因就是「合成 fake rep 比真實回傳更完整」:fake 自帶
    `preflight_passed`,真實回傳當時沒有,於是 gate 分支的 KeyError 被測試遮掉,
    一路過關到正式執行才炸,而那時單發已經認領。
    所以契約測試**不接受任何替身**,直接跑真實路徑。
    (只讀面板、不算任何統計量,不涉及 permutation。)
    """
    try:
        d, rep = R.assemble()
        rep, _blk = R.preflight(d, rep)
    except SystemExit as exc:
        pytest.skip(f"缺面板,跳過真實契約測試:{exc}")
    return rep


def test_preflight_contract_includes_gate_branch_keys(real_rep):
    """gate 分支會讀的兩把鑰匙,必須是 `preflight()` **自己**的產物。"""
    assert "preflight_checks" in real_rep, \
        "preflight() 未產出 preflight_checks —— gate 分支會 KeyError"
    assert "preflight_passed" in real_rep, \
        "preflight() 未產出 preflight_passed —— attempt 1 就是死在這裡"
    assert isinstance(real_rep["preflight_passed"], bool)
    assert isinstance(real_rep["preflight_checks"], dict)
    assert real_rep["preflight_checks"], "檢查項不得為空"
    assert real_rep["preflight_passed"] == all(real_rep["preflight_checks"].values())


def test_fake_rep_never_richer_than_the_real_one(real_rep):
    """**這是防止 attempt 1 重演的那道測試。**

    合成 rep 不得含有真實 `preflight()` 不會產生的鍵 —— 一旦可以,
    測試就會替不存在的欄位背書,缺陷要等到正式執行才會現形。
    """
    extra = set(_fake_rep()) - set(real_rep)
    assert not extra, (
        f"合成 rep 有真實 preflight() 不會產生的鍵:{sorted(extra)}\n"
        "這正是 attempt 1 的失敗模式 —— 假物件比真實回傳更完整,把缺鍵遮起來了。")


def test_main_reads_but_never_writes_the_verdict(real_rep):
    """判定只能由 preflight() 寫;main() 的列印區塊不得再設定它。"""
    src = (REPO_ROOT / "scripts" / "gate1_assemble_12arm.py").read_text(encoding="utf-8")
    body = src.split("def main(", 1)[1]
    for key in ('rep["preflight_checks"] =', 'rep["preflight_passed"] ='):
        assert key not in body, f"main() 仍在設定 {key} —— 判定必須是 preflight() 的產物"


def _fake_rep():
    """能走完 main() 列印區塊的最小 rep(合成值,不對應任何真實面板)。

    ⚠ 它的鍵集合必須是真實 `preflight()` 回傳的**子集**,
    由 `test_fake_rep_never_richer_than_the_real_one` 強制。
    """
    arms = list(R.ALL_ARMS)
    return {
        "v0_panel_path": "synthetic/v0.parquet", "v0_panel_sha256": "0" * 64,
        "rows_before_clock": 10, "rows_after_clock": 10, "as_of_in_clock": 1,
        "return_line": {"column": "fwd_x", "notna_rows": 10},
        "candidate_score": {"column": "real_composite"},
        "n_industries": 1, "clock": ["2019-08-01", "2026-03-31"],
        "frozen": {"SEED": 1},
        "inputs": {a: {"baseline": "V0", "rows_full_panel": 1, "duplicate_keys": 0,
                       "score_error": 0, "sha256": "0" * 64} for a in arms},
        "arm_coverage_in_clock": {a: {"missing_in_clock": 0, "coverage": 1.0} for a in arms},
        "all_arms_full_coverage": True, "frozen_matches_instruction": True,
        "baseline_idx": list(R.BASELINE_IDX),
        "baseline_idx_map": {a: ("V0" if R.BASELINE_IDX[k] == -1 else "arm_C3")
                             for k, a in enumerate(arms)},
        "baseline_shared_by_g1a_and_g1c": True,
        "common_sample": {"n_months_M_star": 80, "months_first": ["m"], "months_last": ["m"],
                          "n_stocks_per_month_min": 1, "n_stocks_per_month_max": 1,
                          "n_stocks_per_month_median": 1.0, "dropped_months": [],
                          "G1a_G1c_same_months": True},
        "rows_excluded_by_each_arm": {a: 0 for a in arms},
        # 判定由 preflight() 產出,合成版照樣要帶(否則就不是真實回傳的子集)
        "preflight_checks": {"合成檢查": True}, "preflight_passed": True,
        # `runner_sha256` / `frozen_impl_sha256` 刻意**不放** —— 那是 main() 自己設的,
        # 不是 preflight() 的產物。放了就會比真實回傳更完整。
    }


@pytest.fixture()
def cli_fires(cli, monkeypatch):
    """讓流程走到步驟 6:preflight 通過、run_gate1 回傳合成結果。"""
    monkeypatch.setattr(R, "preflight", lambda d, rep: (_fake_rep(), {
        "blocks_a": None, "info_a": None, "blocks_c": None, "info_c": None}))
    monkeypatch.setattr(R, "run_gate1", lambda *a, **k: (
        cli["calls"].append("run_gate1"), FAKE_RES)[1])
    return cli


def _fire(cli_fires):
    auth = cli_fires["write_auth"]()
    return cli_fires["run"](["--part", "gate", R.ARM_FLAG, "--authorization", str(auth)])


def test_happy_path_lands_manifest_atomically(cli_fires):
    """對照組:一切正常時 manifest 完整落地,且沒有殘留 .tmp。"""
    _fire(cli_fires)
    assert cli_fires["manifest"].exists()
    assert not cli_fires["failure"].exists()
    assert not (cli_fires["tmp"] / (R.MANIFEST_NAME + ".tmp")).exists()
    man = json.loads(cli_fires["manifest"].read_text(encoding="utf-8"))
    assert man["results"]["n_months_M_star"] == 80
    assert man["authorization"]["sha256"]


@pytest.mark.parametrize("target", ["assemble_execution_manifest", "atomic_write_json"])
def test_archival_failure_keeps_started_writes_failure_and_no_manifest(
        cli_fires, monkeypatch, target):
    """模擬 manifest 建立 / 原子落地失敗 —— 單發已擊發,結果不得遺失。"""
    def boom(*a, **k):
        raise OSError(f"合成測試:{target} 失敗")
    monkeypatch.setattr(R, target, boom)

    with pytest.raises(OSError, match=f"{target} 失敗"):
        _fire(cli_fires)

    assert "run_gate1" in cli_fires["calls"], "應已開火"
    assert cli_fires["started"].exists(), "STARTED 必須保留"
    assert cli_fires["failure"].exists(), "必須寫 FAILURE"
    assert not cli_fires["manifest"].exists(), "正式 manifest 不得存在"

    rec = json.loads(cli_fires["failure"].read_text(encoding="utf-8"))
    assert rec["candidate_statistics_computed"] is True, \
        "已擊發卻沒標記 —— 重跑會被誤當首發"
    assert "單發已擊發" in rec["⚠"]
    assert rec["recovery_payload"]["results"]["n_months_M_star"] == 80, \
        "已擊發的結果必須留在 recovery_payload,否則那一槍永久遺失"


def test_archival_failure_forbids_rerun(cli_fires, monkeypatch):
    monkeypatch.setattr(R, "atomic_write_json",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        _fire(cli_fires)

    cli_fires["calls"].clear()
    with pytest.raises(SystemExit, match="已存在"):
        _fire(cli_fires)
    assert "run_gate1" not in cli_fires["calls"], "封存失敗後不得再開一槍"


def test_run_gate1_failure_marks_not_fired(cli_fires, monkeypatch):
    """permutation 本身失敗 → candidate_statistics_computed 必須是 False。"""
    monkeypatch.setattr(R, "run_gate1",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("perm 掛了")))
    with pytest.raises(RuntimeError, match="perm 掛了"):
        _fire(cli_fires)
    rec = json.loads(cli_fires["failure"].read_text(encoding="utf-8"))
    assert rec["candidate_statistics_computed"] is False
    assert "recovery_payload" not in rec
    assert "note_not_fired" in rec


def test_partial_tmp_file_is_never_the_official_name(cli_fires, tmp_path):
    """原子落地:半份檔案只會叫 `.tmp`,永遠不會頂著正式檔名。"""
    payload = {"a": 1}
    out = tmp_path / R.MANIFEST_NAME
    R.atomic_write_json(out, payload)
    assert out.exists() and json.loads(out.read_text(encoding="utf-8")) == payload
    assert not out.with_name(out.name + ".tmp").exists()
