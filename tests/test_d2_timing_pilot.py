import collections
import math
import sys

import numpy as np
import pytest

from scripts.d2_timing_pilot import (
    AGG_DTYPE,
    B_TEST,
    L_BLOCK,
    N_M,
    DuplicateWriteError,
    FailureRecord,
    IndexOutOfBoundsError,
    InvalidTimingDataError,
    OuterIndexMismatchError,
    _circular_block_indices,
    append_failure_records,
    compute_e_j,
    core_busy_delta,
    final_scan,
    go_no_go,
    method_d,
    new_agg_container,
    p_value_plus_one,
    proc_cpu_delta,
    proc_cpu_fields_supported,
    rate_from_checkpoints,
    record_result,
    runner_tree_cpu_delta,
    spawn_outer_triple,
    u_total,
)

FakeCpuTimes = collections.namedtuple(
    "FakeCpuTimes", ["user", "system", "children_user", "children_system"]
)
FakeScputimes = collections.namedtuple(
    "FakeScputimes", ["user", "system", "idle", "interrupt", "dpc"]
)


def _reference_circular_block_bootstrap_means(x0, L, B_test, seed_sequence):
    """Deliberately slow, non-vectorized reference implementation, used
    only to cross-check the vectorized production path (§3 research
    discipline: an important result needs a second independent path).
    Not part of the frozen runner design."""
    M = len(x0)
    n_blocks = math.ceil(M / L)
    rng = np.random.default_rng(seed_sequence)
    means = []
    for _ in range(B_test):
        starts = rng.integers(0, M, size=n_blocks)
        resampled = []
        for s in starts:
            for k in range(L):
                resampled.append(x0[(int(s) + k) % M])
        resampled = resampled[:M]
        means.append(sum(resampled) / len(resampled))
    return np.array(means)


# ---------------------------------------------------------------------------
# method D kernel
# ---------------------------------------------------------------------------


def test_method_d_t_obs_uses_uncentered_mean():
    x = np.array([10.0, 12.0, 8.0, 11.0, 9.0, 10.0])
    T_obs, _, _ = method_d(x, np.random.SeedSequence(12345), L=3, B_test=50)
    assert T_obs == pytest.approx(np.mean(x))
    assert T_obs == pytest.approx(10.0)
    assert T_obs != pytest.approx(0.0)


def test_circular_block_wraps_around_array_boundary():
    M, L = 24, 12
    starts = np.array([[20, 0]])
    idx = _circular_block_indices(starts, L, M)
    expected_block0 = [20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7]
    expected_block1 = list(range(12))
    assert idx[0].tolist() == expected_block0 + expected_block1


def test_reference_circular_bootstrap_matches_vectorized_implementation():
    x = np.array([10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 13.0, 7.0])  # M=8
    T_obs = float(np.mean(x))
    x0 = x - T_obs
    L, B_test = 3, 200

    from scripts.d2_timing_pilot import _circular_block_bootstrap_means

    vectorized = _circular_block_bootstrap_means(
        x0, L=L, B_test=B_test, seed_sequence=np.random.SeedSequence(2026)
    )
    reference = _reference_circular_block_bootstrap_means(
        x0, L=L, B_test=B_test, seed_sequence=np.random.SeedSequence(2026)
    )
    assert np.allclose(vectorized, reference)

    p_vectorized = p_value_plus_one(T_obs, vectorized, B_test)
    p_reference = p_value_plus_one(T_obs, reference, B_test)
    assert p_vectorized == pytest.approx(p_reference)


def test_p_value_uses_plus_one_formula():
    p = p_value_plus_one(0.0, np.array([1.0, 1.0, -1.0, -1.0]), B_test=4)
    assert p == pytest.approx((1 + 2) / (4 + 1))


def test_method_d_is_reproducible_given_same_seed():
    x = np.array([1.0, 2.0, 3.0, 4.0, 1.5, 2.5, 3.5, 4.5, 1.0, 2.0, 3.0, 4.0])
    r1 = method_d(x, np.random.SeedSequence(7), L=4, B_test=50)
    r2 = method_d(x, np.random.SeedSequence(7), L=4, B_test=50)
    assert r1 == r2


def test_method_d_runs_at_frozen_scale_without_error():
    rng = np.random.default_rng(0)
    x = rng.normal(loc=0.01, scale=0.02, size=24)
    T_obs, p, reject = method_d(x, np.random.SeedSequence(99), L=L_BLOCK, B_test=B_TEST)
    assert math.isfinite(T_obs)
    assert 0.0 <= p <= 1.0
    assert isinstance(reject, (bool, np.bool_))


def test_outer_seed_spawn_is_deterministic():
    triple_a = spawn_outer_triple(np.random.SeedSequence(2026080300))
    triple_b = spawn_outer_triple(np.random.SeedSequence(2026080300))
    for a, b in zip(triple_a, triple_b):
        assert np.array_equal(a.generate_state(4), b.generate_state(4))


def test_method_d_rejects_empty_x():
    with pytest.raises(InvalidTimingDataError):
        method_d(np.array([]), np.random.SeedSequence(1), L=3, B_test=10)


def test_method_d_rejects_2d_x():
    with pytest.raises(InvalidTimingDataError):
        method_d(np.zeros((4, 3)), np.random.SeedSequence(1), L=3, B_test=10)


def test_method_d_rejects_nonfinite_x():
    x = np.array([1.0, 2.0, float("nan"), 4.0])
    with pytest.raises(InvalidTimingDataError):
        method_d(x, np.random.SeedSequence(1), L=2, B_test=10)


def test_method_d_rejects_nonpositive_l():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(InvalidTimingDataError):
        method_d(x, np.random.SeedSequence(1), L=0, B_test=10)


def test_method_d_rejects_nonpositive_b_test():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(InvalidTimingDataError):
        method_d(x, np.random.SeedSequence(1), L=2, B_test=-5)


def test_method_d_rejects_string_array():
    with pytest.raises(InvalidTimingDataError):
        method_d(["1", "2", "3", "4"], np.random.SeedSequence(1), L=2, B_test=10)


def test_method_d_rejects_bool_array():
    with pytest.raises(InvalidTimingDataError):
        method_d([True, False, True, False], np.random.SeedSequence(1), L=2, B_test=10)


def test_method_d_rejects_complex_array():
    x = np.array([1 + 2j, 3 + 4j, 5 + 6j, 7 + 8j])
    with pytest.raises(InvalidTimingDataError):
        method_d(x, np.random.SeedSequence(1), L=2, B_test=10)


def test_method_d_rejects_object_array():
    x = np.array([1.0, 2.0, None, 4.0], dtype=object)
    with pytest.raises(InvalidTimingDataError):
        method_d(x, np.random.SeedSequence(1), L=2, B_test=10)


def test_method_d_rejects_ragged_input_without_raw_valueerror():
    # inhomogeneous nested list -- numpy raises ValueError at np.asarray()
    # itself; must surface as InvalidTimingDataError, not raw ValueError.
    ragged = [[1.0, 2.0], [3.0]]
    with pytest.raises(InvalidTimingDataError):
        method_d(ragged, np.random.SeedSequence(1), L=2, B_test=10)


def test_method_d_rejects_none_seed():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(InvalidTimingDataError):
        method_d(x, None, L=2, B_test=10)


def test_method_d_rejects_int_as_seed():
    # a bare int is *not* a SeedSequence -- must not silently be accepted
    # in place of one (that would break the frozen seed hierarchy).
    x = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(InvalidTimingDataError):
        method_d(x, 12345, L=2, B_test=10)


def test_method_d_rejects_huge_int_in_x_without_raw_overflowerror():
    x = np.array([1.0, 2.0, 3.0, 10**400], dtype=object)
    with pytest.raises(InvalidTimingDataError):
        method_d(x, np.random.SeedSequence(1), L=2, B_test=10)


def test_spawn_outer_triple_rejects_none():
    with pytest.raises(InvalidTimingDataError):
        spawn_outer_triple(None)


def test_p_value_rejects_t_b_length_mismatch():
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(0.0, np.array([1.0, 2.0, 3.0]), B_test=4)


def test_p_value_rejects_2d_t_b():
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(0.0, np.zeros((2, 2)), B_test=4)


def test_p_value_rejects_nonfinite_t_b():
    T_b = np.array([1.0, float("inf"), -1.0, 0.5])
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(0.0, T_b, B_test=4)


def test_p_value_rejects_nonfinite_t_obs():
    T_b = np.array([1.0, -1.0, 0.5, 0.2])
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(float("nan"), T_b, B_test=4)


def test_p_value_rejects_bool_t_obs():
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(True, np.array([1.0, -1.0, 0.5, 0.2]), B_test=4)


def test_p_value_rejects_complex_t_obs():
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(1 + 2j, np.array([1.0, -1.0, 0.5, 0.2]), B_test=4)


def test_p_value_rejects_string_t_b():
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(0.0, ["1", "2", "3", "4"], B_test=4)


def test_p_value_rejects_huge_t_obs_without_raw_overflowerror():
    with pytest.raises(InvalidTimingDataError):
        p_value_plus_one(10**400, np.array([1.0, -1.0, 0.5, 0.2]), B_test=4)


# ---------------------------------------------------------------------------
# CPU telemetry
# ---------------------------------------------------------------------------


def test_proc_cpu_delta_ignores_children_fields():
    before = FakeCpuTimes(user=1.0, system=2.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user=1.5, system=2.2, children_user=999.0, children_system=999.0)
    assert proc_cpu_delta(before, after) == pytest.approx(0.5 + 0.2)


def test_proc_cpu_fields_supported_accepts_extra_fields():
    ct = FakeCpuTimes(user=1.0, system=2.0, children_user=100.0, children_system=200.0)
    assert proc_cpu_fields_supported(ct) is True


def test_proc_cpu_fields_supported_rejects_missing_required_field():
    Incomplete = collections.namedtuple("Incomplete", ["user"])
    assert proc_cpu_fields_supported(Incomplete(user=1.0)) is False


def test_core_busy_delta_clamps_each_field_before_summing():
    before = FakeScputimes(user=10.0, system=5.0, idle=100.0, interrupt=1.0, dpc=1.0)
    after = FakeScputimes(user=12.0, system=6.0, idle=90.0, interrupt=0.5, dpc=1.5)
    got = core_busy_delta(before, after)
    assert got == pytest.approx((12.0 - 10.0) + (6.0 - 5.0) + 0.0 + (1.5 - 1.0))


def test_proc_cpu_delta_rejects_nan_field_instead_of_silently_zeroing():
    before = FakeCpuTimes(user=1.0, system=2.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user=float("nan"), system=2.5, children_user=0.0, children_system=0.0)
    with pytest.raises(InvalidTimingDataError):
        proc_cpu_delta(before, after)


def test_proc_cpu_delta_rejects_inf_field():
    before = FakeCpuTimes(user=1.0, system=2.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user=float("inf"), system=2.5, children_user=0.0, children_system=0.0)
    with pytest.raises(InvalidTimingDataError):
        proc_cpu_delta(before, after)


def test_proc_cpu_delta_rejects_bool_field():
    before = FakeCpuTimes(user=1.0, system=2.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user=True, system=2.5, children_user=0.0, children_system=0.0)
    with pytest.raises(InvalidTimingDataError):
        proc_cpu_delta(before, after)


def test_proc_cpu_delta_rejects_string_field():
    before = FakeCpuTimes(user=1.0, system=2.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user="1.5", system=2.5, children_user=0.0, children_system=0.0)
    with pytest.raises(InvalidTimingDataError):
        proc_cpu_delta(before, after)


def test_field_delta_rejects_subtraction_overflow_to_inf():
    big = 1.0e308
    before = FakeCpuTimes(user=-big, system=0.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user=big, system=0.0, children_user=0.0, children_system=0.0)
    with pytest.raises(InvalidTimingDataError):
        proc_cpu_delta(before, after)


def test_core_busy_delta_rejects_nonfinite_field():
    before = FakeScputimes(user=1.0, system=2.0, idle=3.0, interrupt=0.1, dpc=0.1)
    after = FakeScputimes(user=1.5, system=2.5, idle=2.5, interrupt=float("nan"), dpc=0.2)
    with pytest.raises(InvalidTimingDataError):
        core_busy_delta(before, after)


def test_proc_cpu_delta_rejects_sum_overflow():
    # user delta and system delta are each individually finite (1e308),
    # but their *sum* overflows to inf.
    before = FakeCpuTimes(user=0.0, system=0.0, children_user=0.0, children_system=0.0)
    after = FakeCpuTimes(user=1e308, system=1e308, children_user=0.0, children_system=0.0)
    with pytest.raises(InvalidTimingDataError):
        proc_cpu_delta(before, after)


def test_core_busy_delta_rejects_sum_overflow():
    before = FakeScputimes(user=0.0, system=0.0, idle=0.0, interrupt=0.0, dpc=0.0)
    after = FakeScputimes(user=1e308, system=1e308, idle=0.0, interrupt=1e308, dpc=1e308)
    with pytest.raises(InvalidTimingDataError):
        core_busy_delta(before, after)


def _pid_pairs(pids, cpu_times):
    return [(pid, cpu_times) for pid in pids]


def test_runner_tree_cpu_delta_sums_across_parent_and_workers():
    parent_pid = 100
    workers = list(range(1, 9))
    before = _pid_pairs([parent_pid, *workers], FakeCpuTimes(0.0, 0.0, 0.0, 0.0))
    after = _pid_pairs([parent_pid, *workers], FakeCpuTimes(0.1, 0.1, 0.0, 0.0))
    got = runner_tree_cpu_delta(parent_pid, workers, before, after)
    assert got == pytest.approx(9 * 0.2)


def test_runner_tree_cpu_delta_rejects_worker_count_not_eight():
    parent_pid = 100
    workers = list(range(1, 8))  # only 7
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    snapshot = _pid_pairs([parent_pid, *workers], ct)
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, snapshot, snapshot)


def test_runner_tree_cpu_delta_rejects_duplicate_in_raw_worker_input():
    # 8 list entries but only 7 distinct PIDs -- must be caught before
    # any frozenset() conversion could silently collapse the duplicate.
    parent_pid = 100
    workers = [1, 1, 2, 3, 4, 5, 6, 7]
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    snapshot = _pid_pairs([parent_pid, 1, 2, 3, 4, 5, 6, 7], ct)
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, snapshot, snapshot)


def test_runner_tree_cpu_delta_rejects_parent_also_in_worker_set():
    parent_pid = 100
    workers = [100, 2, 3, 4, 5, 6, 7, 8]  # parent role-collides with a worker
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    snapshot = _pid_pairs([parent_pid, 2, 3, 4, 5, 6, 7, 8], ct)
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, snapshot, snapshot)


def test_runner_tree_cpu_delta_rejects_missing_pid_in_snapshot():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    before = _pid_pairs([parent_pid, *workers], ct)
    after = _pid_pairs([parent_pid, *workers[:-1]], ct)  # one worker missing
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, before, after)


def test_runner_tree_cpu_delta_rejects_extra_pid_in_snapshot():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    before = _pid_pairs([parent_pid, *workers], ct)
    after = _pid_pairs([parent_pid, *workers], ct) + [(999, ct)]
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, before, after)


def test_runner_tree_cpu_delta_rejects_duplicate_pid_in_snapshot():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    before = _pid_pairs([parent_pid, *workers], ct)
    after = _pid_pairs([parent_pid, *workers], ct)
    after[-1] = (after[0][0], ct)  # duplicate parent's pid; worker 8 now absent
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, before, after)


def test_runner_tree_cpu_delta_rejects_sum_overflow_across_workers():
    # each worker's own proc_cpu_delta is individually finite
    # (float_max/4), but summing 9 of them (parent + 8 workers) overflows.
    parent_pid = 0
    workers = list(range(1, 9))
    per_pid_delta = sys.float_info.max / 4
    before = _pid_pairs([parent_pid, *workers], FakeCpuTimes(0.0, 0.0, 0.0, 0.0))
    after = _pid_pairs([parent_pid, *workers], FakeCpuTimes(per_pid_delta, 0.0, 0.0, 0.0))
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, before, after)


def test_runner_tree_cpu_delta_rejects_malformed_pair_wrong_length():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    good = _pid_pairs([parent_pid, *workers], ct)
    malformed = good[:-1] + [(good[-1][0], ct, "unexpected_extra_element")]
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, malformed, good)


def test_runner_tree_cpu_delta_rejects_single_value_pair():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    good = _pid_pairs([parent_pid, *workers], ct)
    malformed = good[:-1] + [(good[-1][0],)]  # one-tuple, not a pair
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, malformed, good)


def test_runner_tree_cpu_delta_rejects_float_pid_in_snapshot():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    good = _pid_pairs([parent_pid, *workers], ct)
    bad = good[:-1] + [(1.0, ct)]
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, bad, good)


def test_runner_tree_cpu_delta_rejects_bool_pid_in_snapshot():
    parent_pid = 0
    workers = list(range(1, 9))
    ct = FakeCpuTimes(0.0, 0.0, 0.0, 0.0)
    good = _pid_pairs([parent_pid, *workers], ct)
    bad = good[:-1] + [(True, ct)]
    with pytest.raises(InvalidTimingDataError):
        runner_tree_cpu_delta(parent_pid, workers, bad, good)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_new_agg_container_has_frozen_dtype():
    arr = new_agg_container(5)
    assert arr.dtype == AGG_DTYPE
    assert arr.shape == (5,)


def test_new_agg_container_rejects_nonpositive_size():
    with pytest.raises(InvalidTimingDataError):
        new_agg_container(0)
    with pytest.raises(InvalidTimingDataError):
        new_agg_container(-3)


def test_new_agg_container_rejects_bool_size():
    with pytest.raises(InvalidTimingDataError):
        new_agg_container(True)


def test_record_result_rejects_out_of_bounds_index():
    arr = new_agg_container(3)
    with pytest.raises(IndexOutOfBoundsError):
        record_result(arr, 5, 5, True, False, 0.01, 0.9)


def test_record_result_rejects_duplicate_write():
    arr = new_agg_container(3)
    record_result(arr, 0, 0, True, False, 0.01, 0.9, fail_flag=False)
    with pytest.raises(DuplicateWriteError):
        record_result(arr, 0, 0, False, False, 0.5, 0.5, fail_flag=False)


def test_record_result_rejects_outer_index_mismatch():
    arr = new_agg_container(3)
    with pytest.raises(OuterIndexMismatchError):
        record_result(arr, 1, 2, True, False, 0.01, 0.9)
    assert not bool(arr[1]["written"])


def test_record_result_rejects_bool_index():
    arr = new_agg_container(3)
    with pytest.raises(InvalidTimingDataError):
        record_result(arr, True, True, False, False, 0.5, 0.5)


def test_record_result_rejects_string_reject_flag_truthiness_footgun():
    # bool("false") is True in plain Python -- must be rejected outright,
    # not silently coerced.
    arr = new_agg_container(1)
    with pytest.raises(InvalidTimingDataError):
        record_result(arr, 0, 0, "false", False, 0.5, 0.5)
    assert not bool(arr[0]["written"])


def test_record_result_rejects_string_p_value_coercion():
    arr = new_agg_container(1)
    with pytest.raises(InvalidTimingDataError):
        record_result(arr, 0, 0, False, False, "0.5", 0.5)
    assert not bool(arr[0]["written"])


def test_record_result_rejects_out_of_range_p_value():
    arr = new_agg_container(1)
    with pytest.raises(InvalidTimingDataError):
        record_result(arr, 0, 0, False, False, 1.5, 0.5)
    assert not bool(arr[0]["written"])


def test_record_result_rejects_nonfinite_p_value():
    arr = new_agg_container(1)
    with pytest.raises(InvalidTimingDataError):
        record_result(arr, 0, 0, False, False, float("nan"), 0.5)
    assert not bool(arr[0]["written"])


def test_record_result_rejects_complex_p_value():
    arr = new_agg_container(1)
    with pytest.raises(InvalidTimingDataError):
        record_result(arr, 0, 0, False, False, 0.5 + 1j, 0.5)
    assert not bool(arr[0]["written"])


def test_final_scan_passes_on_complete_consistent_batch():
    arr = new_agg_container(2)
    record_result(arr, 0, 0, reject_raw=True, reject_ind=False, p_raw=0.01, p_ind=0.5)
    record_result(arr, 1, 1, reject_raw=False, reject_ind=False, p_raw=0.5, p_ind=0.9)
    assert final_scan(arr, phase="Stage1", M=24, cell=1, batch=0) == []


def test_final_scan_rejects_non_ndarray():
    with pytest.raises(InvalidTimingDataError):
        final_scan([1, 2, 3], phase="P7", M=24, cell=0, batch=0)


def test_final_scan_rejects_2d_structured_array():
    arr = new_agg_container(4).reshape(2, 2)
    with pytest.raises(InvalidTimingDataError):
        final_scan(arr, phase="P7", M=24, cell=0, batch=0)


def test_final_scan_rejects_plain_float_array():
    arr = np.zeros(5, dtype=np.float64)
    with pytest.raises(InvalidTimingDataError):
        final_scan(arr, phase="P7", M=24, cell=0, batch=0)


def test_final_scan_rejects_wrong_structured_dtype():
    wrong_dtype = np.dtype([("outer_index", "i8"), ("p_raw", "f8")])
    arr = np.zeros(3, dtype=wrong_dtype)
    with pytest.raises(InvalidTimingDataError):
        final_scan(arr, phase="P7", M=24, cell=0, batch=0)


def test_final_scan_flags_empty_container():
    empty = np.zeros(0, dtype=AGG_DTYPE)
    records = final_scan(empty, phase="P7", M=24, cell=0, batch=0)
    assert len(records) == 1
    assert records[0].reason == "empty_container"


def test_final_scan_flags_missing_entries_with_full_context():
    arr = new_agg_container(2)
    record_result(arr, 0, 0, True, False, 0.01, 0.9)
    records = final_scan(arr, phase="Stage1", M=24, cell=7, batch=1)
    missing = [r for r in records if r.reason == "missing"]
    assert len(missing) == 1
    r = missing[0]
    assert (r.phase, r.M, r.cell, r.batch, r.outer) == ("Stage1", 24, 7, 1, 1)


def test_final_scan_flags_fail_flag_with_full_context():
    arr = new_agg_container(2)
    record_result(arr, 0, 0, False, False, 0.5, 0.5)
    record_result(arr, 1, 1, False, False, 0.5, 0.5, fail_flag=True)
    records = final_scan(arr, phase="P7", M=48, cell=3, batch=0)
    matches = [r for r in records if r.reason == "fail_flag" and r.outer == 1]
    assert len(matches) == 1
    assert matches[0].phase == "P7" and matches[0].M == 48 and matches[0].cell == 3


def test_final_scan_flags_reject_p_inconsistency_with_endpoint():
    arr = new_agg_container(1)
    record_result(arr, 0, 0, reject_raw=True, reject_ind=False, p_raw=0.9, p_ind=0.9)
    records = final_scan(arr, phase="Stage2", M=36, cell=2, batch=0)
    matches = [r for r in records if r.reason == "reject_p_inconsistent"]
    assert len(matches) == 1
    assert matches[0].endpoint == "raw"


def test_final_scan_does_not_double_report_missing_slots():
    arr = new_agg_container(2)
    record_result(arr, 0, 0, False, False, 0.5, 0.5)
    records = final_scan(arr, phase="Stage1", M=24, cell=0, batch=0)
    reasons_for_slot_1 = {r.reason for r in records if r.outer == 1}
    assert reasons_for_slot_1 == {"missing"}


def test_final_scan_flags_out_of_range_p_written_directly_bypassing_record_result():
    # a benchmark/dry-run that pokes the structured array directly,
    # skipping record_result's own validation, must still be caught here.
    arr = new_agg_container(2)
    arr[0] = (0, False, False, -1.0, 0.5, False, True)
    arr[1] = (1, False, False, 0.5, 2.0, False, True)
    records = final_scan(arr, phase="Stage1", M=24, cell=0, batch=0)
    out_of_range = {(r.outer, r.endpoint) for r in records if r.reason == "p_out_of_range"}
    assert (0, "raw") in out_of_range
    assert (1, "ind") in out_of_range


def test_failure_injection_side_record_write_path():
    arr = new_agg_container(3)
    record_result(arr, 0, 0, False, False, 0.5, 0.5)
    record_result(arr, 1, 1, False, False, 0.5, 0.5, fail_flag=True)  # injected failure
    records = final_scan(arr, phase="Stage1", M=24, cell=5, batch=2)
    sink = []
    append_failure_records(sink, records)
    reasons = {(r.reason, r.outer) for r in sink}
    assert ("fail_flag", 1) in reasons
    assert ("missing", 2) in reasons
    fail_record = next(r for r in sink if r.reason == "fail_flag")
    assert (fail_record.phase, fail_record.M, fail_record.cell, fail_record.batch) == (
        "Stage1", 24, 5, 2,
    )


def test_failure_record_schema_fields():
    assert FailureRecord._fields == (
        "phase", "M", "cell", "batch", "outer", "endpoint", "reason", "intermediates",
    )


# ---------------------------------------------------------------------------
# E_j / U_total / go-no-go
# ---------------------------------------------------------------------------


def test_u_total_matches_frozen_formula():
    e = [10.0, 11.0, 9.0, 10.5, 9.5]
    got = u_total(e)
    arr = np.array(e)
    expected = arr.mean() + 2.131846786326649 * arr.std(ddof=1) / math.sqrt(5)
    assert got == pytest.approx(expected)


def test_u_total_has_no_overridable_tcrit_parameter():
    import inspect

    params = inspect.signature(u_total).parameters
    assert "tcrit" not in params


def test_u_total_rejects_nonfinite_e_j():
    with pytest.raises(InvalidTimingDataError):
        u_total([1.0, 2.0, float("nan"), 3.0, 4.0])


def test_u_total_rejects_nonpositive_e_j():
    with pytest.raises(InvalidTimingDataError):
        u_total([1.0, 2.0, 0.0, 3.0, 4.0])


def test_u_total_rejects_wrong_repeat_count():
    with pytest.raises(InvalidTimingDataError):
        u_total([1.0, 2.0, 3.0, 4.0])


def test_u_total_rejects_column_shaped_input():
    with pytest.raises(InvalidTimingDataError):
        u_total(np.array([[1.0], [2.0], [3.0], [4.0], [5.0]]))


def test_u_total_rejects_string_input():
    with pytest.raises(InvalidTimingDataError):
        u_total(["1.0", "2.0", "3.0", "4.0", "5.0"])


def test_u_total_rejects_bool_input():
    with pytest.raises(InvalidTimingDataError):
        u_total([True, False, True, False, True])


def test_u_total_rejects_huge_int_input_without_raw_overflowerror():
    with pytest.raises(InvalidTimingDataError):
        u_total(np.array([1.0, 2.0, 3.0, 4.0, 10**400], dtype=object))


def test_go_no_go_accepts_exact_72_hour_boundary():
    assert go_no_go(72 * 3600.0) is True


def test_go_no_go_rejects_just_over_72_hours():
    assert go_no_go(72 * 3600.0 + 1.0) is False


def test_go_no_go_rejects_nonfinite():
    with pytest.raises(InvalidTimingDataError):
        go_no_go(float("inf"))


def test_go_no_go_rejects_negative_value_instead_of_passing():
    with pytest.raises(InvalidTimingDataError):
        go_no_go(-5.0)


def test_go_no_go_rejects_zero():
    with pytest.raises(InvalidTimingDataError):
        go_no_go(0.0)


def test_go_no_go_rejects_bool():
    with pytest.raises(InvalidTimingDataError):
        go_no_go(True)


def test_go_no_go_rejects_string():
    with pytest.raises(InvalidTimingDataError):
        go_no_go("259200.0")


def test_go_no_go_rejects_huge_int_without_raw_overflowerror():
    with pytest.raises(InvalidTimingDataError):
        go_no_go(10**400)


# ---------------------------------------------------------------------------
# compute_e_j
# ---------------------------------------------------------------------------


def _valid_warmups():
    return {"P7": 1.0, "Stage1": 2.0, "Stage2": 1.5}


def _valid_rates():
    return {24: 0.001, 36: 0.0015, 48: 0.002}


def test_compute_e_j_matches_hand_calculation():
    warmups = _valid_warmups()
    rates = _valid_rates()
    got = compute_e_j(
        global_seed_setup=0.5,
        startup=0.2,
        outer_seed_setup=0.3,
        aggregation_bookkeeping=0.4,
        close=0.1,
        warmups=warmups,
        rate_by_m=rates,
    )
    expected = (
        (0.5 + 0.2 + 0.3 + 0.4 + 0.1)
        + sum(warmups.values())
        + sum((N_M - 200) * r for r in rates.values())
    )
    assert N_M == 2_304_000
    assert got == pytest.approx(expected)


def test_compute_e_j_rejects_missing_warmup_key():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(
            0.5, 0.2, 0.3, 0.4, 0.1,
            warmups={"P7": 1.0, "Stage1": 2.0}, rate_by_m=_valid_rates(),
        )


def test_compute_e_j_rejects_extra_warmup_key():
    warmups = _valid_warmups()
    warmups["Extra"] = 9.0
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=warmups, rate_by_m=_valid_rates())


def test_compute_e_j_rejects_missing_m_key():
    rates = _valid_rates()
    del rates[48]
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


def test_compute_e_j_rejects_extra_m_key():
    rates = _valid_rates()
    rates[60] = 0.001
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


def test_compute_e_j_rejects_nan_component():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(
            float("nan"), 0.2, 0.3, 0.4, 0.1,
            warmups=_valid_warmups(), rate_by_m=_valid_rates(),
        )


def test_compute_e_j_rejects_negative_component():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(-0.1, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=_valid_rates())


def test_compute_e_j_rejects_bool_component():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(True, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=_valid_rates())


def test_compute_e_j_rejects_nonpositive_rate():
    rates = _valid_rates()
    rates[24] = 0.0
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


def test_compute_e_j_rejects_nan_rate():
    rates = _valid_rates()
    rates[36] = float("nan")
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


def test_compute_e_j_rejects_string_rate():
    rates = _valid_rates()
    rates[36] = "0.0015"
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


def test_compute_e_j_rejects_non_mapping_warmups():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(
            0.5, 0.2, 0.3, 0.4, 0.1,
            warmups=[("P7", 1.0), ("Stage1", 2.0), ("Stage2", 1.5)],  # list of pairs, not a mapping
            rate_by_m=_valid_rates(),
        )


def test_compute_e_j_rejects_non_mapping_rate_by_m():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=[24, 36, 48])


def test_compute_e_j_rejects_none_rate_by_m_without_raw_attributeerror():
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=None)


def test_compute_e_j_rejects_float_m_key_despite_equal_value():
    # 24.0 == 24 and hash(24.0) == hash(24) in Python, so a naive
    # `set(rate_by_m.keys()) == M_KEYS` check would let a float key
    # through undetected -- the key's *type* must also be checked.
    rates = {24.0: 0.001, 36: 0.0015, 48: 0.002}
    assert set(rates.keys()) == {24, 36, 48}  # sanity: the footgun is real
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


def test_compute_e_j_rejects_bool_m_key():
    rates = {True: 0.001, 36: 0.0015, 48: 0.002}
    with pytest.raises(InvalidTimingDataError):
        compute_e_j(0.5, 0.2, 0.3, 0.4, 0.1, warmups=_valid_warmups(), rate_by_m=rates)


# ---------------------------------------------------------------------------
# Chunk checkpoint / rate
# ---------------------------------------------------------------------------

_START, _T200, _T800, _T1000, _STOP = 0, 200_000_000, 800_000_000, 1_000_000_000, 1_000_000_000


def test_rate_from_checkpoints_matches_frozen_formula():
    got = rate_from_checkpoints(_START, _T200, _T800, _T1000, _STOP)
    expected = (_T800 - _T200) / 600 / 1e9
    assert got == pytest.approx(expected)


def test_rate_from_checkpoints_allows_t1000_equal_stream_stop():
    got = rate_from_checkpoints(_START, _T200, _T800, _T1000, stream_stop_ns=_T1000)
    assert math.isfinite(got) and got > 0


def test_rate_from_checkpoints_rejects_t1000_after_stream_stop():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, _T200, _T800, _T1000, stream_stop_ns=_T1000 - 1)


def test_rate_from_checkpoints_rejects_start_not_before_t200():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_T200, _T200, _T800, _T1000, _STOP)


def test_rate_from_checkpoints_rejects_bad_t200_t800_ordering():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, _T800, _T200, _T1000, _STOP)


def test_rate_from_checkpoints_rejects_bad_t800_t1000_ordering():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, _T200, _T1000, _T800, _STOP)


def test_rate_from_checkpoints_rejects_float_timestamp():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, float(_T200), _T800, _T1000, _STOP)


def test_rate_from_checkpoints_rejects_nan_timestamp():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, float("nan"), _T800, _T1000, _STOP)


def test_rate_from_checkpoints_rejects_bool_timestamp():
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, True, _T800, _T1000, _STOP)


def test_rate_from_checkpoints_rejects_huge_int_without_raw_overflowerror():
    huge = 10**400
    with pytest.raises(InvalidTimingDataError):
        rate_from_checkpoints(_START, _T200, huge, huge + 1, huge + 2)
