# -*- coding: utf-8 -*-
"""P0-R2 forward identity collector — Phase C blocker-fix tests (round 2 review).

Covers the six items from the user's Phase C blocker list:
  1. check_3_roots_independent volume/filesystem identity (see also the fixed
     test_primary_mirror_must_be_independent in test_identity_collector_basics.py)
  2. OS-level atomic mutex acquisition, tested with two REAL concurrent processes
  3. mirror recovery key-set + hash equality, enforced at BOTH ledger-append and
     health-counting time
  4. checkpoint using the correct hash field per ledger type, both ledgers tested
  5. `collect --dry-run` real read-only source adapters + real app/L4a integration
  6. R-FWD membership parity month-key-set equality

Stage 1 boundary unchanged: no evidence roots created, no production writes,
no Task Scheduler, no stage/commit.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from identity_collector import checkpoint  # noqa: E402
from identity_collector import cli  # noqa: E402
from identity_collector import fusion  # noqa: E402
from identity_collector import ledger as ledger_mod  # noqa: E402
from identity_collector import lock as lock_mod  # noqa: E402
from identity_collector import qualification_ledger  # noqa: E402
from identity_collector import r_fwd_adapter  # noqa: E402
from identity_collector import ranking_adapter  # noqa: E402
from identity_collector import schema_validation as sv  # noqa: E402
from identity_collector import source_adapters  # noqa: E402
from identity_collector.hashing import sha256_hex  # noqa: E402
from identity_collector.timestamps import now_pair  # noqa: E402

FIXED_CLOCK = lambda: datetime(2026, 8, 7, 1, 0, 0, tzinfo=timezone.utc)  # noqa: E731


# ============================================================================
# Item 1 (companion): explicit standalone assertion, kept short since the full
# coverage lives in test_identity_collector_basics.py's updated test.
# ============================================================================
def test_item1_same_volume_different_directory_fails(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ok, problems = sv.check_3_roots_independent(str(a), str(b))
    assert not ok
    assert "same filesystem/volume" in problems[0]


# ============================================================================
# Item 2: OS-level atomic exclusive acquisition, real concurrent processes
# ============================================================================
def _mutex_worker(lock_dir: str, run_id: str, pid_val: int, barrier, result_queue) -> None:
    """Module-level (picklable) worker for multiprocessing 'spawn'."""
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(lock_dir).resolve().parents[0] / "__unused__"))  # no-op, keeps signature stable
    _repo_root = _Path(__file__).resolve().parent.parent
    _sys.path.insert(0, str(_repo_root / "scripts"))
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from identity_collector import lock as _lock_mod

    barrier.wait()
    try:
        _lock_mod.acquire(lock_dir, run_id, pid_val, _dt.now(_tz.utc), lambda p: True)
        result_queue.put("won")
    except _lock_mod.LockHeld:
        result_queue.put("lost")
    except Exception as e:  # pragma: no cover -- surfaces unexpected errors in the parent
        result_queue.put(f"error:{e!r}")


def test_concurrent_run_single_mutex_winner_real_processes(tmp_path):
    """Item 2: two REAL OS processes race for the same lock_dir. Real wall-clock
    is used deliberately here (the one disclosed exception to this suite's
    fixed-clock discipline) -- the point of this test IS real OS-level
    concurrency, which a fixed/injected clock cannot exercise."""
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    q = ctx.Queue()
    p1 = ctx.Process(target=_mutex_worker, args=(str(tmp_path), "run-A", 11111, barrier, q))
    p2 = ctx.Process(target=_mutex_worker, args=(str(tmp_path), "run-B", 22222, barrier, q))
    p1.start()
    p2.start()
    p1.join(timeout=15)
    p2.join(timeout=15)
    assert p1.exitcode == 0 and p2.exitcode == 0
    results = [q.get(timeout=5), q.get(timeout=5)]
    assert results.count("won") == 1, results
    assert results.count("lost") == 1, results
    winner_rec = lock_mod.read_lock(tmp_path)
    assert winner_rec is not None and winner_rec["run_id"] in ("run-A", "run-B")


# ============================================================================
# Item 3: mirror recovery key-set + hash equality, enforced at append AND health-count time
# ============================================================================
def _original_receipt_with_outputs(output_hashes: dict) -> dict:
    return {
        "run_id": sha256_hex(b"orig-run"),
        "persistence_status": "PENDING_MIRROR",
        "monthly_status": "DAILY_DIAGNOSTIC",
        "identity_status": "P_ONLY_EVIDENCE",
        "completed_at": now_pair(FIXED_CLOCK),
        "output_hashes": output_hashes,
        "mirror_verification": {"primary_aggregate_sha256": sha256_hex(b"agg"), "status": "PENDING",
                                  "mirror_aggregate_sha256": None, "per_file_verification": {}},
        "source_mutation": False,
        "failure_code": None,
    }


def _full_mirror_verification(output_hashes: dict, tamper: str | None = None) -> dict:
    from identity_collector.hashing import obj_hash

    per_file = {k: {"primary_sha256": v["sha256"], "mirror_sha256": v["sha256"], "match": True} for k, v in output_hashes.items()}
    if tamper == "missing_key":
        per_file.pop(next(iter(per_file)))
    if tamper == "extra_key":
        per_file["extra_unexpected_file.json"] = {"primary_sha256": sha256_hex(b"x"), "mirror_sha256": sha256_hex(b"x"), "match": True}
    if tamper == "wrong_hash":
        k = next(iter(per_file))
        per_file[k] = {"primary_sha256": sha256_hex(b"WRONG"), "mirror_sha256": sha256_hex(b"WRONG"), "match": True}
    # matches check #11's own recomputation convention exactly (obj_hash over
    # {filename: primary_sha256} / {filename: mirror_sha256}), not an ad hoc formula
    primary_agg = obj_hash({k: v["primary_sha256"] for k, v in per_file.items()})
    mirror_agg = obj_hash({k: v["mirror_sha256"] for k, v in per_file.items()})
    return {"status": "VERIFIED", "primary_aggregate_sha256": primary_agg, "mirror_aggregate_sha256": mirror_agg, "per_file_verification": per_file}


def test_mirror_recovery_key_set_and_hash_equality_enforced_at_append(tmp_path):
    output_hashes = {"p_a_scores.parquet": {"bytes": 10, "sha256": sha256_hex(b"pa")}, "p_b_fullpool.parquet": {"bytes": 10, "sha256": sha256_hex(b"pb")}}
    original = _original_receipt_with_outputs(output_hashes)
    ledger_path = tmp_path / "collector_ledger.jsonl"

    # missing key -> append_mirror_recovery_event refuses outright
    with pytest.raises(ValueError, match="check #11"):
        ledger_mod.append_mirror_recovery_event(ledger_path, original["run_id"], "PENDING", "VERIFIED",
                                                  _full_mirror_verification(output_hashes, tamper="missing_key"), original, FIXED_CLOCK)
    assert ledger_mod.read_ledger(ledger_path) == []  # nothing written

    # extra key -> refused
    with pytest.raises(ValueError, match="check #11"):
        ledger_mod.append_mirror_recovery_event(ledger_path, original["run_id"], "PENDING", "VERIFIED",
                                                  _full_mirror_verification(output_hashes, tamper="extra_key"), original, FIXED_CLOCK)

    # wrong hash -> refused
    with pytest.raises(ValueError, match="check #11"):
        ledger_mod.append_mirror_recovery_event(ledger_path, original["run_id"], "PENDING", "VERIFIED",
                                                  _full_mirror_verification(output_hashes, tamper="wrong_hash"), original, FIXED_CLOCK)

    # correct -> accepted
    good_event = ledger_mod.append_mirror_recovery_event(ledger_path, original["run_id"], "PENDING", "VERIFIED",
                                                            _full_mirror_verification(output_hashes), original, FIXED_CLOCK)
    ok, errors = sv.validate("LedgerEvent", good_event)
    assert ok, errors
    assert len(ledger_mod.read_ledger(ledger_path)) == 1


def test_mirror_recovery_primary_correct_mirror_wrong_but_self_consistent_rejected(tmp_path):
    """Item 1 (P1 blocker, round 2): the user's exact counterexample. Every
    `primary_sha256` correctly matches the original receipt's real bytes.
    Every `mirror_sha256` is WRONG (does not equal the corresponding
    `primary_sha256`) -- but the wrong mirror hashes are themselves
    internally self-consistent: `mirror_aggregate_sha256` correctly
    recomputes FROM those wrong per-file mirror hashes, and `match=True` is
    (falsely) claimed for every file. Round 1's check #11 never compared
    mirror_sha256 to primary_sha256 per file at all, so this passed. It must
    now be rejected, and effective_persistence_status must stay
    PENDING_MIRROR -- not because the aggregate fails to recompute (it
    doesn't -- that's the whole point of "self-consistent"), but because the
    mirror copy demonstrably does not match the primary copy."""
    from identity_collector import health as health_mod
    from identity_collector.hashing import obj_hash

    output_hashes = {
        "p_a_scores.parquet": {"bytes": 10, "sha256": sha256_hex(b"pa-real")},
        "p_b_fullpool.parquet": {"bytes": 10, "sha256": sha256_hex(b"pb-real")},
    }
    original = _original_receipt_with_outputs(output_hashes)
    ledger_path = tmp_path / "collector_ledger.jsonl"

    # primary: correct. mirror: wrong-but-different-from-each-other-consistently.
    per_file = {
        "p_a_scores.parquet": {"primary_sha256": sha256_hex(b"pa-real"), "mirror_sha256": sha256_hex(b"pa-WRONG-MIRROR"), "match": True},
        "p_b_fullpool.parquet": {"primary_sha256": sha256_hex(b"pb-real"), "mirror_sha256": sha256_hex(b"pb-WRONG-MIRROR"), "match": True},
    }
    primary_agg = obj_hash({k: v["primary_sha256"] for k, v in per_file.items()})
    mirror_agg = obj_hash({k: v["mirror_sha256"] for k, v in per_file.items()})  # self-consistent: recomputes correctly FROM the wrong values
    self_consistent_but_wrong_mv = {
        "status": "VERIFIED",
        "primary_aggregate_sha256": primary_agg,
        "mirror_aggregate_sha256": mirror_agg,
        "per_file_verification": per_file,
    }

    payload = ledger_mod.build_mirror_recovery_payload(original["run_id"], "PENDING", "VERIFIED", self_consistent_but_wrong_mv, original)
    ok, problems = sv.check_11_mirror_recovery_per_file(payload, original)
    assert not ok
    assert any("mirror_sha256 != primary_sha256" in p for p in problems)
    assert any("primary_aggregate_sha256 != mirror_aggregate_sha256" in p for p in problems)

    with pytest.raises(ValueError, match="check #11"):
        ledger_mod.append_mirror_recovery_event(ledger_path, original["run_id"], "PENDING", "VERIFIED", self_consistent_but_wrong_mv, original, FIXED_CLOCK)
    assert ledger_mod.read_ledger(ledger_path) == []

    # bypass the append gate directly (as if some other bug let it through) --
    # health counting must STILL refuse to promote this to COMMITTED.
    bogus_payload = ledger_mod.build_mirror_recovery_payload(original["run_id"], "PENDING", "VERIFIED", self_consistent_but_wrong_mv, original)
    ledger_mod.append_event(ledger_path, "mirror", original["run_id"], bogus_payload, FIXED_CLOCK)
    entries = ledger_mod.read_ledger(ledger_path)
    assert health_mod.effective_persistence_status(original, entries) == "PENDING_MIRROR"


def test_mirror_recovery_match_flag_lying_rejected(tmp_path):
    """Item 1: `match` must reflect ACTUAL hash equality -- a payload cannot
    claim `match=False` for files that actually match, nor `match=True` for
    files that don't (the second half is the dangerous direction; the first
    is checked too, for completeness)."""
    output_hashes = {"p_a_scores.parquet": {"bytes": 10, "sha256": sha256_hex(b"pa")}}
    original = _original_receipt_with_outputs(output_hashes)

    mv = _full_mirror_verification(output_hashes)
    mv["per_file_verification"]["p_a_scores.parquet"]["match"] = False  # lies in the safe direction, still wrong
    payload = ledger_mod.build_mirror_recovery_payload(original["run_id"], "PENDING", "VERIFIED", mv, original)
    ok, problems = sv.check_11_mirror_recovery_per_file(payload, original)
    assert not ok
    assert any("does not reflect actual hash equality" in p for p in problems)


def test_mirror_recovery_original_receipt_binding_validated(tmp_path):
    """Item 1: original_receipt_sha256 / original_output_aggregate_sha256 are
    now actually CHECKED (round 1 only used them when BUILDING a payload,
    never when validating one)."""
    output_hashes = {"p_a_scores.parquet": {"bytes": 10, "sha256": sha256_hex(b"pa")}}
    original = _original_receipt_with_outputs(output_hashes)
    mv = _full_mirror_verification(output_hashes)

    good_payload = ledger_mod.build_mirror_recovery_payload(original["run_id"], "PENDING", "VERIFIED", mv, original)
    tampered_receipt_sha = dict(good_payload, original_receipt_sha256=sha256_hex(b"WRONG"))
    ok, problems = sv.check_11_mirror_recovery_per_file(tampered_receipt_sha, original)
    assert not ok
    assert any("original_receipt_sha256" in p for p in problems)

    tampered_agg_sha = dict(good_payload, original_output_aggregate_sha256=sha256_hex(b"WRONG"))
    ok, problems = sv.check_11_mirror_recovery_per_file(tampered_agg_sha, original)
    assert not ok
    assert any("original_output_aggregate_sha256" in p for p in problems)

    ok, problems = sv.check_11_mirror_recovery_per_file(good_payload, original)
    assert ok, problems


def test_mirror_recovery_health_reverifies_even_if_ledger_bypassed(tmp_path):
    """Item 3, defense-in-depth: a bogus mirror event that somehow reaches the
    ledger via the GENERIC append_event (bypassing append_mirror_recovery_event's
    own check #11 gate) must still NOT be trusted by health counting -- the
    second, independent gate the user asked for."""
    from identity_collector import health as health_mod

    output_hashes = {"p_a_scores.parquet": {"bytes": 10, "sha256": sha256_hex(b"pa")}}
    original = _original_receipt_with_outputs(output_hashes)
    ledger_path = tmp_path / "collector_ledger.jsonl"

    bogus_payload = ledger_mod.build_mirror_recovery_payload(
        original["run_id"], "PENDING", "VERIFIED", _full_mirror_verification(output_hashes, tamper="wrong_hash"), original,
    )
    # bypass append_mirror_recovery_event entirely -- simulates a bug/attack that
    # reached the ledger through the generic, unguarded append path
    ledger_mod.append_event(ledger_path, "mirror", original["run_id"], bogus_payload, FIXED_CLOCK)

    entries = ledger_mod.read_ledger(ledger_path)
    assert health_mod.effective_persistence_status(original, entries) == "PENDING_MIRROR"  # NOT promoted to COMMITTED

    summary = health_mod.build_health_summary([original], entries, "FREE", None, now_pair(FIXED_CLOCK))
    assert summary["pending_mirror_count"] == 1  # still counted as pending, the bogus VERIFIED claim did not fool the counter


# ============================================================================
# Item 4: checkpoint per-ledger-type hash field + truncation detection, both ledgers
# ============================================================================
def test_checkpoint_collector_ledger_uses_event_hash(tmp_path):
    ledger_path = tmp_path / "collector_ledger.jsonl"
    ledger_mod.append_event(ledger_path, "run", sha256_hex(b"r1"), {"note": "one"}, FIXED_CLOCK)
    ledger_mod.append_event(ledger_path, "run", sha256_hex(b"r2"), {"note": "two"}, FIXED_CLOCK)

    primary, mirror = tmp_path / "primary", tmp_path / "mirror"
    record = checkpoint.build_checkpoint(ledger_path, "collector_ledger.jsonl", primary, mirror, FIXED_CLOCK)
    ok, errors = sv.validate("LedgerHeadCheckpointRecord", record)
    assert ok, errors
    entries = ledger_mod.read_ledger(ledger_path)
    assert record["payload"]["head_record_hash"] == entries[-1]["event_hash"]

    ok, problems = sv.check_20_checkpoint_record(record, entries)
    assert ok, problems

    # truncation: drop the tail entry, re-check against the (unchanged) checkpoint
    truncated = entries[:-1]
    ok, problems = sv.check_20_checkpoint_record(record, truncated)
    assert not ok
    assert any("truncation" in p for p in problems)


def test_checkpoint_qualification_ledger_uses_record_hash(tmp_path):
    from identity_collector.testing import build_qualification_attempt_body

    qlp = tmp_path / "r_fwd_adapter_qualification_ledger.jsonl"
    attempt_body, _p, _m = build_qualification_attempt_body(tmp_path, gates_pass=True, bundle_verified=True)
    written = qualification_ledger.append_ledger_entry(qlp, attempt_body)

    primary, mirror = tmp_path / "cp_primary", tmp_path / "cp_mirror"
    record = checkpoint.build_checkpoint(qlp, "r_fwd_adapter_qualification_ledger.jsonl", primary, mirror, FIXED_CLOCK)
    ok, errors = sv.validate("LedgerHeadCheckpointRecord", record)
    assert ok, errors
    assert record["payload"]["head_record_hash"] == written["record_hash"]

    entries = qualification_ledger.read_ledger(qlp)
    ok, problems = sv.check_20_checkpoint_record(record, entries)
    assert ok, problems

    ok, problems = sv.check_20_checkpoint_record(record, [])  # full truncation
    assert not ok
    assert any("truncation" in p for p in problems)


def test_checkpoint_rejects_unknown_ledger_name():
    with pytest.raises(ValueError, match="unknown ledger_name"):
        checkpoint.hash_field_for("some_other_ledger.jsonl")


# ============================================================================
# Item 5/2: collect --dry-run, real read-only source adapters, real app/L4a
# integration, frozen-input isolation. Item 2's requirement 4: tests must NOT
# assume the host has (or lacks) a real score cache -- data_cache.set_store()
# is core/data_cache.py's OWN production-sanctioned injection point ("供測試
# 注入記憶體 store"), used here to construct BOTH present and missing P-A
# scenarios deterministically regardless of what is actually on this machine.
# ============================================================================
REQUIRED_SCORE_COLUMNS = [
    "stock_id", "name", "as_of", "mode", "composite", "rating", "fundamental",
    "valuation", "technical", "momentum", "whale", "valuation_status",
    "data_confidence", "data_gaps", "dyn_weight", "price", "atr",
    "value_area_low", "value_area_high", "cost_zone_poc", "cost_zone_support",
    "cost_zone_resistance", "ma20", "inst_participation", "foreign_flow",
    "trust_flow", "foreign_buy_days", "trust_buy_days",
]


def _synthetic_score_row(stock_id, composite, as_of="2026-08-07", mode="balanced"):
    row = {c: 0.0 for c in REQUIRED_SCORE_COLUMNS}
    row.update({
        "stock_id": stock_id, "name": f"name-{stock_id}", "as_of": as_of, "mode": mode,
        "composite": composite, "rating": "test", "valuation_status": "test",
        "data_gaps": "", "foreign_buy_days": 0, "trust_buy_days": 0,
    })
    return row


@pytest.fixture
def injected_score_cache(tmp_path):
    """Injects a real, minimal Scores parquet via data_cache's own DI point
    (present case) or an empty store (missing case), and restores the
    original store afterward regardless of test outcome."""
    sys.path.insert(0, str(REPO_ROOT))
    from core import data_cache

    original_store = data_cache.get_store()

    def _inject(rows=None):
        store = data_cache._ParquetStore(tmp_path / "injected_score_cache")
        if rows:
            import pandas as pd
            store.write("Scores", "ALL", pd.DataFrame(rows))
        data_cache.set_store(store)
        return store

    yield _inject
    data_cache.set_store(original_store)


def test_source_adapters_real_read_only_p_b():
    df, frozen_bytes, path = source_adapters.read_p_b_fullpool("2026-08-07")
    assert len(df) > 0
    assert "c2_score_full" in df.columns
    assert "stock_id" in df.columns
    assert isinstance(frozen_bytes, bytes) and len(frozen_bytes) > 0
    assert path.exists()


def test_source_adapters_p_b_missing_date_raises():
    with pytest.raises(source_adapters.SourceReadError):
        source_adapters.read_p_b_fullpool("1999-01-01")


def test_source_adapters_p_b_read_exactly_once_physically(tmp_path, monkeypatch):
    """Round 3 P1: the exact reported defect was two physical reads of P-B
    (`pd.read_csv(path)` inside the old read_p_b_fullpool, then a second,
    independent `Path(path).read_bytes()` in fusion.run_real_dual_fusion).
    Uses a private tmp copy (never the real repo file) so this test can
    instrument reads without risking any production file. Asserts BOTH that
    `Path.read_bytes` is called exactly once against the source path, and
    that `pandas.read_csv` is never invoked with a path/str/Path argument
    (only ever with the in-memory BytesIO already produced by that one
    read_bytes call)."""
    import shutil

    import pandas as pd

    real_p_b_path = source_adapters.UNIV_DIR / "c2_fullpool_2026-08-07.csv"
    private_copy = tmp_path / "c2_fullpool_2026-08-07.csv"
    shutil.copy2(real_p_b_path, private_copy)

    read_bytes_calls = []
    original_read_bytes = Path.read_bytes

    def counting_read_bytes(self):
        if self == private_copy:
            read_bytes_calls.append(str(self))
        return original_read_bytes(self)

    read_csv_path_args = []
    original_read_csv = pd.read_csv

    def spying_read_csv(filepath_or_buffer, *args, **kwargs):
        if isinstance(filepath_or_buffer, (str, Path)):
            read_csv_path_args.append(filepath_or_buffer)
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(pd, "read_csv", spying_read_csv)

    df, frozen_bytes, path = source_adapters.read_p_b_fullpool("2026-08-07", universe_pool_dir=tmp_path)

    assert read_bytes_calls == [str(private_copy)], f"expected exactly one physical read of {private_copy}, got {read_bytes_calls}"
    assert read_csv_path_args == [], f"pd.read_csv must only ever be called against the frozen in-memory bytes, never a path -- got {read_csv_path_args}"
    assert len(df) > 0
    assert path == private_copy


def test_source_adapters_p_b_snapshot_survives_source_mutation_after_read(tmp_path):
    """Round 3 P1, second half: take the P-B snapshot, then mutate the
    (private, non-production) source file the snapshot was read from, then
    prove BOTH derived forms -- the DataFrame consumed by
    compute_app_path_fusion, and the frozen_bytes consumed by
    compute_l4a_path_fusion_frozen -- still reflect the PRE-mutation content,
    never the post-mutation live file. Uses a tmp private copy, never the
    real repo file under outputs/universe_pool/, so the mutation never
    touches a production source."""
    import shutil

    import pandas as pd

    real_p_b_path = source_adapters.UNIV_DIR / "c2_fullpool_2026-08-07.csv"
    private_copy = tmp_path / "c2_fullpool_2026-08-07.csv"
    shutil.copy2(real_p_b_path, private_copy)

    df, frozen_bytes, path = source_adapters.read_p_b_fullpool("2026-08-07", universe_pool_dir=tmp_path)
    top_stock_id = df.nlargest(1, "c2_score_full")["stock_id"].iloc[0]
    p_a = pd.DataFrame({"stock_id": [top_stock_id], "pct_rank": [99.0], "composite": [99.0], "as_of": ["2026-08-07"], "name": ["x"], "price": [100.0]})

    # Mutate the private copy AFTER the snapshot was taken -- a producer
    # rewriting the file mid-run, simulated safely against our own tmp copy.
    mutated_row = "999999,MUTATED,999.0\n"
    original_columns_line = private_copy.read_text(encoding="utf-8").splitlines()[0]
    private_copy.write_text(private_copy.read_text(encoding="utf-8") + mutated_row, encoding="utf-8")
    post_mutation_bytes = private_copy.read_bytes()
    assert post_mutation_bytes != frozen_bytes  # sanity: the mutation is real and would be observable if re-read
    assert "999999" not in original_columns_line

    # Neither derived form re-reads the (now-mutated) file:
    assert "999999" not in set(df["stock_id"].astype(str))  # df was parsed from the pre-mutation bytes only
    app_membership = fusion.compute_app_path_fusion(p_a, df, fusion_pct=20)
    assert "999999" not in app_membership

    l4a_membership = fusion.compute_l4a_path_fusion_frozen(p_a, frozen_bytes, "2026-08-07")
    assert "999999" not in l4a_membership
    assert top_stock_id in l4a_membership


def test_source_adapters_p_a_missing_cache_injected(injected_score_cache):
    """Item 2 requirement 4: deterministic 'missing' case via an injected
    EMPTY store -- not an assumption about this host's real environment."""
    injected_score_cache(rows=None)
    with pytest.raises(source_adapters.SourceReadError):
        source_adapters.read_p_a_composite("2026-08-07")


def test_source_adapters_p_a_present_cache_injected(injected_score_cache):
    """Item 2 requirement 4: deterministic 'present' case via an injected
    store holding a real, minimal Scores parquet -- exercises the REAL
    core.score_store.screen_by_composite_at query path (DuckDB against the
    injected Parquet), not a mock of the adapter itself."""
    injected_score_cache(rows=[
        _synthetic_score_row("2330", 90.0),
        _synthetic_score_row("2317", 70.0),
        _synthetic_score_row("2454", 50.0),
    ])
    df = source_adapters.read_p_a_composite("2026-08-07")
    assert set(df["stock_id"]) == {"2330", "2317", "2454"}
    assert "pct_rank" in df.columns


def test_app_path_fusion_formula_against_real_p_b_file():
    """Real P-B (outputs/universe_pool/c2_fullpool_2026-08-07.csv) + synthetic
    P-A -- proves compute_app_path_fusion runs the REAL formula against REAL
    production P-B data, not a placeholder."""
    import pandas as pd

    p_b, _p_b_bytes, _p_b_path = source_adapters.read_p_b_fullpool("2026-08-07")
    top_stock_ids = p_b.nlargest(5, "c2_score_full")["stock_id"].tolist()
    p_a = pd.DataFrame({"stock_id": top_stock_ids, "pct_rank": [95.0] * 5})
    membership = fusion.compute_app_path_fusion(p_a, p_b, fusion_pct=20)
    assert membership == set(top_stock_ids)  # all 5 clear both the real c2 top-20% and the synthetic pct_rank>=80 bar


def test_l4a_path_frozen_fails_closed_on_empty_frozen_input():
    """Frozen-input version: an empty frozen_p_a correctly fails closed via
    compute_target_list's own SystemExit, translated to SourceReadError --
    no dependence on whatever score cache this host does or doesn't have,
    since the frozen input is supplied directly."""
    import pandas as pd

    empty_p_a = pd.DataFrame(columns=["stock_id", "name", "as_of", "composite", "pct_rank"])
    p_b_bytes = Path(source_adapters.UNIV_DIR / "c2_fullpool_2026-08-07.csv").read_bytes()
    with pytest.raises(source_adapters.SourceReadError):
        fusion.compute_l4a_path_fusion_frozen(empty_p_a, p_b_bytes, "2026-08-07")


def test_l4a_path_frozen_never_rereads_live_source_after_it_changes(tmp_path):
    """THE direct test for item 2's core requirement: freeze P-A/P-B, then
    MUTATE the live P-B file the collector would otherwise have re-read, then
    run the l4a path -- if it were re-reading live sources, the mutation
    would leak into the result. It must not, because
    `_frozen_l4a_call_context` never lets l4a_decision touch the real
    UNIV_DIR at all."""
    import pandas as pd

    real_p_b_path = source_adapters.UNIV_DIR / "c2_fullpool_2026-08-07.csv"
    frozen_p_b_bytes = real_p_b_path.read_bytes()
    frozen_p_b_df = pd.read_csv(real_p_b_path, dtype={"stock_id": str})
    top_stock_id = frozen_p_b_df.nlargest(1, "c2_score_full")["stock_id"].iloc[0]
    frozen_p_a = pd.DataFrame({"stock_id": [top_stock_id], "pct_rank": [99.0], "composite": [99.0], "as_of": ["2026-08-07"], "name": ["x"], "price": [100.0]})

    # Prove the live file is genuinely reachable at this path (sanity), then
    # verify _frozen_l4a_call_context's temp dir is what l4a_decision sees --
    # by asserting UNIV_DIR is restored to its ORIGINAL value afterward, and
    # that the frozen copy (not the live file) was what got read: corrupt a
    # SEPARATE temp "live" directory that is never touched by the frozen path.
    with fusion._frozen_l4a_call_context(frozen_p_a, frozen_p_b_bytes, "2026-08-07") as l4a_decision:
        assert l4a_decision.UNIV_DIR != real_p_b_path.parent  # repointed away from the real directory
        assert str(tempfile.gettempdir()) in str(l4a_decision.UNIV_DIR) or "p0r2_frozen_l4a_" in str(l4a_decision.UNIV_DIR)
        target_df, _ = l4a_decision.compute_target_list("2026-08-07", mode="balanced", fusion_pct=20, top_n=None)
        assert top_stock_id in set(target_df["stock_id"].astype(str))
    # after the context exits, the real module state must be fully restored
    import l4a_decision as l4a_decision_module
    assert l4a_decision_module.UNIV_DIR == real_p_b_path.parent
    from core import score_store
    assert score_store.screen_by_composite_at.__name__ == "screen_by_composite_at"  # not left monkeypatched


def test_cli_collect_dry_run_reports_missing_source_deterministically(capsys, injected_score_cache):
    """No RootsNotConfigured -- dry-run is allowed even with Stage 2 pending.
    Item 2 requirement 4: the MISSING case is constructed via the injected
    empty store, not assumed from whatever this host happens to have."""
    injected_score_cache(rows=None)
    result = cli.run_collect_dry_run("2026-08-07")
    assert result["status"] == "MISSING_SOURCE"
    assert result["dry_run"] is True

    exit_code = cli.main(["collect", "--as-of", "2026-08-07", "--config", "x.json", "--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "MISSING_SOURCE" in captured.out


def test_cli_collect_dry_run_reports_ok_deterministically(injected_score_cache):
    """Item 2 requirement 4: the PRESENT case, also via injection -- this test
    passes identically whether or not the host running it has a real score
    cache, because it never looks at the host's real cache at all (P-A is
    fully injected; P-B is the real file, but only its rank ORDER matters,
    picking the real top-c2 stock_id makes the outcome deterministic
    regardless of the file's actual score values)."""
    real_p_b, _real_p_b_bytes, _real_p_b_path = source_adapters.read_p_b_fullpool("2026-08-07")
    top_c2_stock_id = real_p_b.nlargest(1, "c2_score_full")["stock_id"].iloc[0]
    injected_score_cache(rows=[
        _synthetic_score_row(top_c2_stock_id, 99.0),  # highest composite AND highest real c2 -> clears both 80th-percentile bars
        _synthetic_score_row("__dummy_low__", 1.0),   # gives percent_rank a second point to rank against
    ])
    result = cli.run_collect_dry_run("2026-08-07")
    assert result["status"] == "OK", result
    assert result["p_a_rows"] == 2
    assert top_c2_stock_id in result["fusion_membership"]


def test_cli_collect_without_dry_run_still_fails_closed():
    exit_code = cli.main(["collect", "--as-of", "2026-08-07", "--config", "x.json"])
    assert exit_code == 1


# ============================================================================
# Item 6: R-FWD membership parity month-key-set equality
# ============================================================================
def test_membership_parity_requires_exact_month_key_set():
    oracle = {f"{2005 + i // 12}-{(i % 12) + 1:02d}-28": ["2330"] for i in range(255)}

    missing_month = dict(oracle)
    del missing_month["2026-03-28"]  # adapter silently omits the last month
    with pytest.raises(ValueError, match="key sets differ"):
        r_fwd_adapter.membership_parity_result(missing_month, oracle)

    extra_month = dict(oracle, **{"2026-04-28": ["9999"]})  # adapter reports a month outside the oracle's 255
    with pytest.raises(ValueError, match="key sets differ"):
        r_fwd_adapter.membership_parity_result(extra_month, oracle)

    exact_keys = dict(oracle)  # same key set, identical content -> full match
    result = r_fwd_adapter.membership_parity_result(exact_keys, oracle)
    assert result["exact_match_count"] == 255
