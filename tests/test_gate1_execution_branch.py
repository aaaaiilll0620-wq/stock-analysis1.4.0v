# -*- coding: utf-8 -*-
"""Gate 1 正式執行分支(`run_gate1`)的合成測試。

`run_gate1()` 是實際開火時會跑的那一段。本檔用**合成 blocks** 驗它:
G1-a 與 G1-c 共用同一份 `baseline_idx`、AND 判定、退化行為、可重現性、
以及 `M*` 不一致時必須 raise。

⚠ 全部合成資料。**不讀任何 candidate 面板、不執行正式 permutation、
不產生任何 candidate 的 ΔIC / t / T* / p-value。**
測試用的 `n_perm` 刻意設得很小(數十),與凍結的 2000 無關。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

G = pytest.importorskip("gate1_delta_ic_maxt")
R = pytest.importorskip("gate1_assemble_12arm")

N_MONTHS, N_STOCKS, K = 14, 60, 12
ARMS = [f"arm{j}" for j in range(K)]


def _panel(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(N_MONTHS):
        v0 = rng.standard_normal(N_STOCKS)
        ret = 0.15 * v0 + rng.standard_normal(N_STOCKS)
        rows.append(pd.DataFrame({
            "as_of": f"2020-{m + 1:02d}-28",
            "stock_id": [f"{1000 + i}" for i in range(N_STOCKS)],
            G.REAL_COMP_COL: v0,
            G.RET_COL: ret,
            "_ind": [f"ind{i % 5}" for i in range(N_STOCKS)],
        }))
    return pd.concat(rows, ignore_index=True)


def _with_arms(d, devs):
    out = d.copy()
    for j, dev in enumerate(devs):
        out[ARMS[j]] = out[G.REAL_COMP_COL] if dev is None else out[G.REAL_COMP_COL] + dev
    return out


def _blocks(d):
    ba, ia = G.build_month_blocks(d, ARMS)
    bc, ic = G.build_month_blocks(d, ARMS, neutral_by="_ind")
    return ba, ia, bc, ic


def _distinct(seed=11):
    rng = np.random.default_rng(seed)
    d = _panel(seed)
    return _with_arms(d, [rng.standard_normal(len(d)) * 0.5 for _ in range(K)])


# ---------------------------------------------------------------------------
def test_declared_shape_matches_the_hardcoded_table():
    """runner 硬編碼的宣告表必須就是勘誤 E1 的那一張,且索引 5 是 C3。"""
    assert R.BASELINE_IDX == [-1] * 6 + [5] * 6
    assert R.ALL_ARMS[R.IDX_C3] == "C3"
    assert R.ALL_ARMS[:6] == R.FIRST_BATCH
    assert R.ALL_ARMS[6:] == R.SECOND_BATCH
    assert len(R.ALL_ARMS) == G.N_ARMS


def test_no_source_code_arming_constant_remains():
    """武裝不得靠原始碼常數 —— 改碼會變更 runner hash 並使已驗過的 overlay 失效。"""
    assert not hasattr(R, "EXECUTION_APPROVED"), \
        "EXECUTION_APPROVED 應已廢除,改用外部授權檔"
    assert R.ARM_FLAG == "--i-am-executing-the-frozen-gate"
    assert R.AUTH_TOKEN == "gate1-first-official-permutation"


def test_run_gate1_shape_and_same_baseline_for_both_versions():
    """G1-a 與 G1-c 必須用**同一份** baseline_idx,結果形狀為 K。"""
    ba, ia, bc, ic = _blocks(_distinct())
    res = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=40, seed=G.SEED)

    assert res["settings"]["baseline_idx"] == R.BASELINE_IDX
    for tag in ("G1a", "G1c"):
        assert len(res[tag]["t"]) == K
        assert len(res[tag]["p_adj"]) == K
    assert len(res["passed"]) == K
    assert res["n_months_M_star"] == N_MONTHS


def test_run_gate1_uses_frozen_functions_verbatim():
    """`run_gate1` 不得自算統計量 —— 結果必須與直接呼叫凍結函式逐位元相同。"""
    ba, ia, bc, ic = _blocks(_distinct())
    res = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=40, seed=G.SEED)

    t_a = G.delta_ic_t(ba, baseline_idx=R.BASELINE_IDX)
    t_c = G.delta_ic_t(bc, baseline_idx=R.BASELINE_IDX)
    n_a = G.joint_maxt_null(ba, n_perm=40, seed=G.SEED, baseline_idx=R.BASELINE_IDX)
    n_c = G.joint_maxt_null(bc, n_perm=40, seed=G.SEED, baseline_idx=R.BASELINE_IDX)

    assert res["G1a"]["t"] == t_a.tolist()
    assert res["G1c"]["t"] == t_c.tolist()
    assert res["G1a"]["T_star"] == n_a["T_star"]
    assert res["G1c"]["T_star"] == n_c["T_star"]


def test_decision_is_AND_of_g1a_and_g1c():
    """通過條件是 AND —— 只過一邊不算通過(第一批 §7 / Codex 第九輪 §2)。"""
    ba, ia, bc, ic = _blocks(_distinct())
    res = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=40, seed=G.SEED)
    for k in range(K):
        assert res["passed"][k] == (res["pass_G1a"][k] and res["pass_G1c"][k])
    assert "AND" in res["decision_rule"]


def test_degenerate_family_yields_zero_t_and_no_pass():
    """12 個 arm 全等於 V0 → t 全 0、T* 全 0 → 不得有任何 arm 通過。

    注意:此處 baseline_idx 用全 V0,因為 B 腿若對 C3 而兩者又都等於 V0,
    語意仍是退化;這裡驗的是最基本的「什麼都沒改就不能通過」。
    """
    d = _with_arms(_panel(), [None] * K)
    ba, ia, bc, ic = _blocks(d)
    res = R.run_gate1(ba, ia, bc, ic, [G.V0_BASELINE] * K, n_perm=30, seed=G.SEED)
    assert all(t == 0.0 for t in res["G1a"]["t"])
    assert res["G1a"]["T_star"] == 0.0
    assert res["G1a"]["degenerate"] is True
    assert not any(res["passed"]), "什麼都沒改的族系不得有 arm 通過"


def test_same_seed_reproduces_the_whole_result():
    ba, ia, bc, ic = _blocks(_distinct())
    a = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=50, seed=G.SEED)
    b = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=50, seed=G.SEED)
    assert a["G1a"] == b["G1a"] and a["G1c"] == b["G1c"]
    assert a["passed"] == b["passed"]


def test_mismatched_months_raise_before_any_statistic():
    """G1-a 與 G1-c 的 M* 不一致 → 必須 raise,不得先算出一半的統計量。"""
    ba, ia, bc, ic = _blocks(_distinct())
    ic = dict(ic)
    ic["months"] = ic["months"][:-1]
    with pytest.raises(SystemExit, match="M\\* 不一致"):
        R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=10, seed=G.SEED)


def test_bad_baseline_declaration_is_rejected_by_run_gate1():
    """宣告表錯誤必須在執行分支就被凍結函式擋下。"""
    ba, ia, bc, ic = _blocks(_distinct())
    bad = list(R.BASELINE_IDX)
    bad[0] = 0
    with pytest.raises(ValueError, match="以自己為 baseline"):
        R.run_gate1(ba, ia, bc, ic, bad, n_perm=10, seed=G.SEED)


def test_p_adj_is_conservative_and_never_zero():
    """單步 max-t 的 adjusted p 用 (1+#)/(1+B) 慣例 → 恆 > 0 且 ≤ 1。"""
    ba, ia, bc, ic = _blocks(_distinct())
    res = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=40, seed=G.SEED)
    for tag in ("G1a", "G1c"):
        for p in res[tag]["p_adj"]:
            assert 0.0 < p <= 1.0
        assert min(res[tag]["p_adj"]) >= 1 / 41


def test_execution_manifest_records_inputs_and_no_performance():
    """execution manifest 必須帶輸入指紋、baseline、設定,並聲明未跑績效。"""
    ba, ia, bc, ic = _blocks(_distinct())
    res = R.run_gate1(ba, ia, bc, ic, R.BASELINE_IDX, n_perm=20, seed=G.SEED)
    rep = {
        "inputs": {"A1": {"sha256": "x"}}, "v0_panel_path": "p", "v0_panel_sha256": "s",
        "return_line": {"column": "fwd_x"}, "candidate_score": {"column": "real_composite"},
        "clock": ["2019-08-01", "2026-03-31"], "frozen": {"SEED": G.SEED},
        "baseline_idx": R.BASELINE_IDX, "baseline_idx_map": {}, "common_sample": {},
        "preflight_checks": {}, "runner_sha256": "r", "frozen_impl_sha256": "f",
    }
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc)
    man = R.build_execution_manifest(rep, res, {"passed": True}, t, t, ["cmd"])

    assert man["baseline_idx"] == R.BASELINE_IDX
    assert man["performance_analysis_executed"] is False
    assert "外部授權 JSON" in man["authorization_mechanism"]
    assert man["results"]["settings"]["seed"] == G.SEED
    assert man["provenance_overlay"]["passed"] is True
    assert man["inputs"]["A1"]["sha256"] == "x"


# ---------------------------------------------------------------------------
# 授權 + 單發射擊認領(Codex 2026-08-02 §1-§3)
# ---------------------------------------------------------------------------
@pytest.fixture()
def gate_fs(tmp_path):
    """合成的 overlay + 授權檔 + 三個鎖檔路徑,全在暫存目錄。"""
    ov = tmp_path / "GATE1_PROVENANCE_OVERLAY.json"
    ov.write_text('{"fake": "overlay"}', encoding="utf-8")
    ov_sha = R.sha256_file(ov)

    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({
        "authorizes": R.AUTH_TOKEN, "overlay_sha256": ov_sha,
        "authorized_by": "tester", "authorized_at": "2026-08-02T00:00:00+08:00",
    }, ensure_ascii=False), encoding="utf-8")

    return {"overlay": ov, "overlay_sha": ov_sha, "auth": auth,
            "started": tmp_path / R.STARTED_NAME,
            "manifest": tmp_path / R.MANIFEST_NAME,
            "failure": tmp_path / R.FAILURE_NAME}


def test_authorization_accepts_matching_overlay(gate_fs):
    got = R.load_authorization(gate_fs["auth"], gate_fs["overlay"])
    assert got["overlay_sha256"] == gate_fs["overlay_sha"]
    assert got["sha256"] == R.sha256_file(gate_fs["auth"])


@pytest.mark.parametrize("mutate, match", [
    (lambda c: c.update(overlay_sha256="0" * 64), "綁定的 overlay 與現行的不符"),
    (lambda c: c.pop("overlay_sha256"), "缺 `overlay_sha256`"),
    (lambda c: c.update(authorizes="something-else"), "authorizes"),
])
def test_authorization_rejects_bad_content(gate_fs, mutate, match):
    c = json.loads(gate_fs["auth"].read_text(encoding="utf-8"))
    mutate(c)
    gate_fs["auth"].write_text(json.dumps(c), encoding="utf-8")
    with pytest.raises(SystemExit, match=match):
        R.load_authorization(gate_fs["auth"], gate_fs["overlay"])


def test_authorization_rejects_missing_absent_and_malformed(gate_fs, tmp_path):
    with pytest.raises(SystemExit, match="未提供授權檔"):
        R.load_authorization(None, gate_fs["overlay"])
    with pytest.raises(SystemExit, match="授權檔不存在"):
        R.load_authorization(tmp_path / "nope.json", gate_fs["overlay"])
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="不是合法 JSON"):
        R.load_authorization(bad, gate_fs["overlay"])


def test_overlay_change_after_authorization_stops_before_any_candidate_read(gate_fs):
    """授權後 overlay 被改 → 必須停,且是在讀取／計算 candidate 之前。

    `load_authorization` 是純函式,不碰任何面板 —— 它 raise 就代表尚未讀過 candidate。
    """
    gate_fs["overlay"].write_text('{"fake": "overlay TAMPERED"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="綁定的 overlay 與現行的不符"):
        R.load_authorization(gate_fs["auth"], gate_fs["overlay"])


def _claim(fs, payload=None):
    return R.claim_execution(started_path=fs["started"], manifest_path=fs["manifest"],
                             failure_path=fs["failure"],
                             payload=payload or {"started_at": "t", "seed": G.SEED})


def test_claim_creates_started_exclusively(gate_fs):
    assert not gate_fs["started"].exists()
    _claim(gate_fs)
    assert gate_fs["started"].exists(), "STARTED 必須在 run_gate1 前落地"
    body = json.loads(gate_fs["started"].read_text(encoding="utf-8"))
    assert body["seed"] == G.SEED


def test_claim_refuses_when_started_already_exists(gate_fs):
    _claim(gate_fs)
    with pytest.raises(SystemExit, match="EXECUTION_STARTED 已存在"):
        _claim(gate_fs)


def test_claim_refuses_when_manifest_already_exists(gate_fs):
    gate_fs["manifest"].write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="EXECUTION_MANIFEST 已存在"):
        _claim(gate_fs)
    assert not gate_fs["started"].exists(), "被拒絕時不該留下 STARTED"


def test_claim_refuses_when_previous_failure_not_archived(gate_fs):
    gate_fs["failure"].write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="EXECUTION_FAILURE 已存在"):
        _claim(gate_fs)


def test_started_is_retained_when_run_gate1_fails(gate_fs):
    """模擬 run_gate1 失敗:STARTED 必須保留,另寫 FAILURE。

    刪掉 STARTED 等於抹掉「已經開過一槍」的痕跡,下一次會被當成首發。
    """
    started = _claim(gate_fs)
    try:
        raise RuntimeError("模擬 permutation 中途失敗")
    except RuntimeError as exc:
        R.write_failure_record(failure_path=gate_fs["failure"],
                               started=started, error=exc)

    assert gate_fs["started"].exists(), "失敗後 STARTED 必須保留"
    rec = json.loads(gate_fs["failure"].read_text(encoding="utf-8"))
    assert rec["error_type"] == "RuntimeError"
    assert "模擬 permutation 中途失敗" in rec["error"]
    assert rec["started_record"]["seed"] == G.SEED

    # 封存前不得重跑
    with pytest.raises(SystemExit):
        _claim(gate_fs)


def test_authorization_template_binds_current_overlay(gate_fs):
    tpl = R.authorization_template(gate_fs["overlay"])
    assert tpl["authorizes"] == R.AUTH_TOKEN
    assert tpl["overlay_sha256"] == gate_fs["overlay_sha"]
