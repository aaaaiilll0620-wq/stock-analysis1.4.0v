"""D2 method-D timing-pilot: pure, unit-testable core.

Implements the frozen policy in
`docs/預註冊_C3Forward_D2方法驗證.md` §2.A.2 (method D) and §2.E.1-2.E.10
(P8 / P8.1 / P8.2 timing-pilot design).

Phase 1 scope only (per the authorising `GPT answer.md` instruction): every
function here is pure — no pool/process creation, no sleeping, no memory
precheck, no CLI entry point, no real timing/synthetic/OOS execution. This
module exists so the statistical kernel, the CPU-telemetry arithmetic, the
aggregation bookkeeping, and the E_j/U_total/go-no-go judgement can each be
unit-tested in isolation before any of them are wired into an actual runner.

Every public function here is fail-closed on malformed input:
  * a violation always raises `InvalidTimingDataError` (or one of the
    narrower aggregation exceptions below) — never a bare TypeError,
    ValueError, ComplexWarning, or OverflowError, and never a
    normal-looking result computed from bad input;
  * numeric-looking values are never silently coerced — bool, complex,
    string/bytes, and object-dtype inputs are rejected outright rather
    than cast (`bool("false")` being truthy, or a string array silently
    parsing as floats, are exactly the failure modes this guards
    against);
  * conversions that could raise Python's built-in OverflowError
    (float(huge_int), huge-int true-division, etc.) are caught and
    re-raised as InvalidTimingDataError; a result overflowing to +-inf
    is likewise rejected rather than returned.
"""
from __future__ import annotations

import collections.abc
import math
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

import numpy as np


class InvalidTimingDataError(Exception):
    pass


def _require_int(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise InvalidTimingDataError(
            f"{name} must be an int (not bool/float), got {type(value).__name__}: {value!r}"
        )


def _require_positive_int(value: Any, name: str) -> None:
    _require_int(value, name)
    if value <= 0:
        raise InvalidTimingDataError(f"{name} must be a positive integer, got {value!r}")


def _require_real_scalar(value: Any, name: str) -> float:
    """Reject bool, complex, string/bytes, and anything else that is not
    a genuine real int/float, then require finiteness. Any OverflowError
    raised while coercing to float (e.g. an oversized Python int) is
    converted to InvalidTimingDataError rather than leaking out raw."""
    if isinstance(value, bool) or isinstance(value, (complex, np.complexfloating)):
        raise InvalidTimingDataError(f"{name} must be a real number, got {type(value).__name__}: {value!r}")
    if isinstance(value, (str, bytes)):
        raise InvalidTimingDataError(f"{name} must be a real number, got {type(value).__name__}: {value!r}")
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise InvalidTimingDataError(f"{name} must be a real number, got {type(value).__name__}: {value!r}")
    try:
        value = float(value)
    except OverflowError as exc:
        raise InvalidTimingDataError(f"{name} is too large to convert to float: {exc}") from exc
    if not math.isfinite(value):
        raise InvalidTimingDataError(f"{name} must be finite, got {value!r}")
    return value


def _require_finite_nonnegative(value: Any, name: str) -> float:
    value = _require_real_scalar(value, name)
    if not value >= 0:
        raise InvalidTimingDataError(f"{name} must be non-negative, got {value!r}")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise InvalidTimingDataError(f"{name} must be bool, got {type(value).__name__}: {value!r}")
    return bool(value)


def _require_unit_probability(value: Any, name: str) -> float:
    value = _require_real_scalar(value, name)
    if not (0.0 <= value <= 1.0):
        raise InvalidTimingDataError(f"{name} must be in [0,1], got {value!r}")
    return value


def _require_real_numeric_array(x: Any, name: str) -> np.ndarray:
    """Reject bool/complex/string/object dtype arrays *before* any cast
    to float64 — numpy will otherwise silently coerce a bool array
    (True/False -> 1.0/0.0) or a numeric-looking string array
    (['1','2'] -> [1.0, 2.0]) without complaint. Any ValueError/TypeError
    raised while interpreting `x` as an array (e.g. a ragged/inhomogeneous
    nested list) and any OverflowError raised while casting (an int too
    large for float64) are converted to InvalidTimingDataError rather
    than leaking out raw."""
    try:
        arr = np.asarray(x)
    except (ValueError, TypeError) as exc:
        raise InvalidTimingDataError(f"{name} could not be interpreted as an array: {exc}") from exc
    if arr.dtype.kind not in ("i", "u", "f"):
        raise InvalidTimingDataError(
            f"{name} must be real numeric (int/uint/float), got dtype {arr.dtype} (kind={arr.dtype.kind!r})"
        )
    try:
        return arr.astype(np.float64)
    except (ValueError, TypeError, OverflowError) as exc:
        raise InvalidTimingDataError(f"{name} could not be converted to float64: {exc}") from exc


def _require_seed_sequence(value: Any, name: str = "seed_sequence") -> None:
    """A bare `None` (or anything else) must not silently fall through
    to `np.random.default_rng(None)`, which would seed from OS entropy
    and destroy the reproducibility the whole pilot design depends on."""
    if not isinstance(value, np.random.SeedSequence):
        raise InvalidTimingDataError(
            f"{name} must be a np.random.SeedSequence instance, got {type(value).__name__}"
        )


# ---------------------------------------------------------------------------
# §2.A.2 method D: centered circular-block bootstrap (non-studentized)
# ---------------------------------------------------------------------------

L_BLOCK = 12
B_TEST = 1999


def _circular_block_indices(starts: np.ndarray, L: int, M: int) -> np.ndarray:
    """starts: shape (n_reps, n_blocks) of block-start positions, each in
    {0, ..., M-1}. Returns shape (n_reps, n_blocks*L) indices into an array
    of length M, wrapping past the end back to index 0 (circular block)."""
    offsets = np.arange(L)
    idx = (starts[:, :, None] + offsets[None, None, :]) % M
    return idx.reshape(starts.shape[0], starts.shape[1] * L)


def _circular_block_bootstrap_means(
    x0: np.ndarray, L: int, B_test: int, seed_sequence: np.random.SeedSequence
) -> np.ndarray:
    """Each of the B_test replicates independently draws ceil(M/L) starts,
    uniform over {0, ..., M-1}, takes circular blocks of length L,
    concatenates, and truncates to length M. Assumes the caller
    (`method_d`) has already validated x0/L/B_test/seed_sequence."""
    M = x0.shape[0]
    n_blocks = math.ceil(M / L)
    rng = np.random.default_rng(seed_sequence)
    starts = rng.integers(0, M, size=(B_test, n_blocks))
    idx = _circular_block_indices(starts, L, M)[:, :M]
    return x0[idx].mean(axis=1)


def p_value_plus_one(T_obs: float, T_b: Sequence[float], B_test: int) -> float:
    """p = (1 + #{T_b >= T_obs}) / (B_test + 1).

    T_b must be a real-numeric (not bool/complex/string/object), 1-D,
    all-finite array of length exactly B_test; T_obs must be a real,
    finite scalar. Any violation is fail-closed.
    """
    _require_positive_int(B_test, "B_test")
    T_obs = _require_real_scalar(T_obs, "T_obs")
    T_b = _require_real_numeric_array(T_b, "T_b")
    if T_b.ndim != 1 or T_b.shape[0] != B_test:
        raise InvalidTimingDataError(f"T_b must be 1-D with length {B_test}, got shape {T_b.shape}")
    if not np.all(np.isfinite(T_b)):
        raise InvalidTimingDataError("T_b must be all finite")
    count_ge = int(np.count_nonzero(T_b >= T_obs))
    return (1 + count_ge) / (B_test + 1)


def method_d(
    x: np.ndarray,
    seed_sequence: np.random.SeedSequence,
    L: int = L_BLOCK,
    B_test: int = B_TEST,
) -> tuple[float, float, bool]:
    """Return (T_obs, p_value, reject) per §2.A.2.

    T_obs is the mean of the *original*, uncentered x — it must not be
    computed from a pre-centered series. Only the bootstrap resampling
    source x0 = x - mean(x) is centered.

    x must be a real-numeric (not bool/complex/string/object), nonempty,
    1-D, all-finite array; L and B_test must be positive integers;
    seed_sequence must be a genuine np.random.SeedSequence (not None —
    that would silently seed from OS entropy and break reproducibility).
    Any violation is fail-closed.
    """
    x = _require_real_numeric_array(x, "x")
    if x.ndim != 1 or x.shape[0] == 0:
        raise InvalidTimingDataError(f"x must be a nonempty 1-D array, got shape {x.shape}")
    if not np.all(np.isfinite(x)):
        raise InvalidTimingDataError("x must be all finite")
    _require_positive_int(L, "L")
    _require_positive_int(B_test, "B_test")
    _require_seed_sequence(seed_sequence)

    T_obs = float(np.mean(x))
    x0 = x - T_obs
    T_b = _circular_block_bootstrap_means(x0, L=L, B_test=B_test, seed_sequence=seed_sequence)
    p = p_value_plus_one(T_obs, T_b, B_test)
    reject = p <= 0.05
    return T_obs, p, reject


def spawn_outer_triple(
    outer_seed: np.random.SeedSequence,
) -> tuple[np.random.SeedSequence, np.random.SeedSequence, np.random.SeedSequence]:
    """outer_seed.spawn(3) -> (x_dgp_placeholder, d_raw_seed, d_ind_seed).

    x_dgp_placeholder exists only for positional parity with production's
    seed hierarchy (§2.E.4); pilot code must not consume it to regenerate x.
    """
    _require_seed_sequence(outer_seed, "outer_seed")
    return tuple(outer_seed.spawn(3))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# §2.E.9.7 / §2.E.10 CPU telemetry: clamp-then-sum, user+system only
# ---------------------------------------------------------------------------

REQUIRED_PROC_CPU_FIELDS = {"user", "system"}
CORE_BUSY_FIELDS = ("user", "system", "interrupt", "dpc")


def proc_cpu_fields_supported(cpu_times: Any) -> bool:
    """§2.E.10.3: accept anything whose fields at least contain
    {user, system}; never reject on extra fields (children_*, or any
    future addition) via exact tuple equality."""
    fields = set(getattr(cpu_times, "_fields", ()))
    return REQUIRED_PROC_CPU_FIELDS.issubset(fields)


def _field_delta(before: Any, after: Any, field: str) -> float:
    """max(0, after.field - before.field). Both readings go through
    `_require_real_scalar` (rejects bool/complex/string, catches
    OverflowError), so a nonsensical field value raises rather than
    silently becoming 0.0 via max(); the subtraction result is then
    re-checked for finiteness in case two finite values overflowed on
    subtraction."""
    if not (hasattr(before, field) and hasattr(after, field)):
        raise InvalidTimingDataError(f"missing required field: {field}")
    b = _require_real_scalar(getattr(before, field), f"{field} (before)")
    a = _require_real_scalar(getattr(after, field), f"{field} (after)")
    delta = a - b
    if not math.isfinite(delta):
        raise InvalidTimingDataError(f"field {field!r} delta overflowed to non-finite: {delta!r}")
    return max(0.0, delta)


def proc_cpu_delta(before: Any, after: Any) -> float:
    """§2.E.10.2: per distinct PID, max(0,delta user)+max(0,delta system)
    only. children_user/children_system (and any other extra fields) are
    ignored entirely, to avoid double-counting worker CPU time that is
    already captured by each worker's own PID. Each field delta is
    individually finite (see `_field_delta`), but their *sum* could
    still overflow to inf — checked explicitly rather than returned."""
    total = _field_delta(before, after, "user") + _field_delta(before, after, "system")
    return _require_finite_nonnegative(total, "proc_cpu_delta")


def core_busy_delta(before: Any, after: Any) -> float:
    """§2.E.9.7 Windows scputimes: clamp each field individually (after
    checking it exists, is a real number, and is finite), then sum
    user+system+interrupt+dpc (busy = total - idle). The sum itself is
    checked for overflow rather than returned as-is."""
    total = sum(_field_delta(before, after, f) for f in CORE_BUSY_FIELDS)
    return _require_finite_nonnegative(total, "core_busy_delta")


def runner_tree_cpu_delta(
    parent_pid: int,
    frozen_worker_pids: Iterable[int],
    before: Sequence[tuple[int, Any]],
    after: Sequence[tuple[int, Any]],
) -> float:
    """§2.E.9.7 / §2.E.4.3 worker health, with explicit PID *roles*.

    parent_pid: the single frozen parent PID.
    frozen_worker_pids: must contain exactly 8 distinct int PIDs (the
        raw input is checked for duplicates *before* any set-conversion
        would silently collapse them away).
    parent_pid must not also appear in frozen_worker_pids (role
    violation). before/after are sequences of (pid, cpu_times) pairs
    (not a dict, so an accidental duplicate entry is actually
    detectable); each snapshot's PID set must equal exactly
    {parent_pid} union frozen_worker_pids — missing, extra, duplicate,
    or role-misassigned PIDs are all fail-closed.
    """
    _require_int(parent_pid, "parent_pid")

    worker_pid_list = list(frozen_worker_pids)
    for pid in worker_pid_list:
        _require_int(pid, "frozen_worker_pids element")
    worker_pid_set = frozenset(worker_pid_list)
    if len(worker_pid_list) != len(worker_pid_set):
        raise InvalidTimingDataError("frozen_worker_pids contains duplicate PIDs")
    if len(worker_pid_set) != 8:
        raise InvalidTimingDataError(
            f"frozen_worker_pids must contain exactly 8 distinct PIDs, got {len(worker_pid_set)}"
        )
    if parent_pid in worker_pid_set:
        raise InvalidTimingDataError(f"parent_pid {parent_pid} must not also appear in frozen_worker_pids")

    frozen_pids = frozenset({parent_pid}) | worker_pid_set

    def _validate_snapshot(label: str, snapshot: Sequence[tuple[int, Any]]) -> dict:
        pids = []
        try:
            for item in snapshot:
                pid, _cpu_times = item
                pids.append(pid)
        except (ValueError, TypeError) as exc:
            raise InvalidTimingDataError(
                f"{label} snapshot contains a malformed (pid, cpu_times) pair: {exc}"
            ) from exc
        for pid in pids:
            _require_int(pid, f"{label} snapshot PID")
        pid_set = frozenset(pids)
        if len(pids) != len(pid_set):
            raise InvalidTimingDataError(f"{label} snapshot contains duplicate PIDs")
        if pid_set != frozen_pids:
            missing = sorted(frozen_pids - pid_set)
            extra = sorted(pid_set - frozen_pids)
            raise InvalidTimingDataError(
                f"{label} snapshot PID set does not match {{parent}}∪workers "
                f"(missing={missing}, extra={extra})"
            )
        return dict(snapshot)

    before_map = _validate_snapshot("before", before)
    after_map = _validate_snapshot("after", after)
    total = sum(proc_cpu_delta(before_map[pid], after_map[pid]) for pid in frozen_pids)
    return _require_finite_nonnegative(total, "runner_tree_cpu_delta")


# ---------------------------------------------------------------------------
# §2.E.6 aggregation: dtype, per-record write guard, batch final scan
# ---------------------------------------------------------------------------

AGG_DTYPE = np.dtype(
    [
        ("outer_index", "i8"),
        ("reject_raw", "?"),
        ("reject_ind", "?"),
        ("p_raw", "f8"),
        ("p_ind", "f8"),
        ("fail_flag", "?"),
        ("written", "?"),
    ]
)


class IndexOutOfBoundsError(Exception):
    pass


class DuplicateWriteError(Exception):
    pass


class OuterIndexMismatchError(Exception):
    """Raised when the outer_index a worker echoes back does not match
    the slot the parent intended to write it to (§2.E key-schema check).
    The parent must never silently overwrite this into the expected
    index — that would mask a real dispatch/return-path bug."""

    def __init__(self, expected: int, returned: int):
        super().__init__(f"expected outer_index {expected}, worker returned {returned}")
        self.expected = expected
        self.returned = returned


def new_agg_container(size: int) -> np.ndarray:
    """§2.E.6 aggregation container. size must be a positive integer —
    an empty (size=0) container is rejected outright, rather than being
    allowed to vacuously PASS `final_scan` later."""
    _require_positive_int(size, "size")
    arr = np.zeros(size, dtype=AGG_DTYPE)
    arr["p_raw"] = np.nan
    arr["p_ind"] = np.nan
    return arr


def record_result(
    arr: np.ndarray,
    index: int,
    returned_outer_index: int,
    reject_raw: bool,
    reject_ind: bool,
    p_raw: float,
    p_ind: float,
    fail_flag: bool = False,
) -> None:
    """§2.E.6① per-result checks, in order: index/returned_outer_index
    must be real ints; index bounds; the returned_outer_index must match
    the target index (fail-closed on mismatch — never silently corrected
    to `index`); written[index] duplicate check; then strict type/range
    validation of the payload itself (reject_raw/reject_ind/fail_flag
    must be real bool, not a truthy string like "false"; p_raw/p_ind
    must be real finite numbers in [0,1], not a string coerced via
    float()). No write happens unless every check passes.
    """
    _require_int(index, "index")
    _require_int(returned_outer_index, "returned_outer_index")
    if not (0 <= index < arr.shape[0]):
        raise IndexOutOfBoundsError(index)
    if returned_outer_index != index:
        raise OuterIndexMismatchError(expected=index, returned=returned_outer_index)
    if bool(arr[index]["written"]):
        raise DuplicateWriteError(index)

    reject_raw = _require_bool(reject_raw, "reject_raw")
    reject_ind = _require_bool(reject_ind, "reject_ind")
    fail_flag = _require_bool(fail_flag, "fail_flag")
    p_raw = _require_unit_probability(p_raw, "p_raw")
    p_ind = _require_unit_probability(p_ind, "p_ind")

    arr[index] = (index, reject_raw, reject_ind, p_raw, p_ind, fail_flag, True)


class FailureRecord(NamedTuple):
    """§2.E.6 fixed failure side-record schema."""

    phase: str
    M: int
    cell: int
    batch: int
    outer: int
    endpoint: str
    reason: str
    intermediates: Any


def final_scan(
    arr: np.ndarray, *, phase: str, M: int, cell: int, batch: int
) -> list[FailureRecord]:
    """§2.E.6② batch-level final scan. Returns [] iff every binding check
    passes; otherwise one fully-identified FailureRecord per detected
    problem (never a bare generic string).

    Checked independently of how `arr` was populated — i.e. this also
    catches a benchmark/dry-run that wrote directly into the structured
    array, bypassing `record_result` entirely (an out-of-range p=-1 or
    p=2 must still fail here, not just at the record_result boundary):
      * every slot's written flag (missing);
      * every written slot's stored outer_index equals its own array
        position;
      * every written slot's fail_flag;
      * every written slot's p_raw/p_ind are finite and in [0,1];
      * every written, in-range slot's reject flag is consistent with
        its p-value.

    An empty array (size 0) can no longer be constructed via
    `new_agg_container`, but is still rejected defensively here too,
    rather than vacuously reporting [] (numpy's `.all()`/`.any()` are
    vacuously True/False on empty arrays).

    The container contract itself is checked before any field is
    touched: `arr` must be an actual np.ndarray, 1-D, with dtype exactly
    AGG_DTYPE — a 2-D structured array, a plain float array, or an
    array with the wrong structured dtype all raise
    InvalidTimingDataError rather than a raw ValueError/IndexError from
    field access failing partway through.
    """
    if not isinstance(arr, np.ndarray):
        raise InvalidTimingDataError(f"arr must be a np.ndarray, got {type(arr).__name__}")
    if arr.ndim != 1:
        raise InvalidTimingDataError(f"arr must be 1-D, got ndim={arr.ndim}")
    if arr.dtype != AGG_DTYPE:
        raise InvalidTimingDataError(f"arr must have dtype AGG_DTYPE, got {arr.dtype}")

    if arr.shape[0] == 0:
        return [
            FailureRecord(
                phase, M, cell, batch, outer=-1, endpoint="raw+ind",
                reason="empty_container", intermediates=None,
            )
        ]

    failures: list[FailureRecord] = []
    written = arr["written"]

    missing = np.nonzero(~written)[0]
    for i in missing:
        failures.append(FailureRecord(phase, M, cell, batch, int(i), "raw+ind", "missing", None))

    # The remaining checks only make sense for slots that were actually
    # written — an unwritten slot is already fully explained by "missing"
    # above and would otherwise generate redundant duplicate reports.
    expected_index = np.arange(arr.shape[0])
    index_mismatch = np.nonzero(written & (arr["outer_index"] != expected_index))[0]
    for i in index_mismatch:
        failures.append(
            FailureRecord(
                phase, M, cell, batch, int(i), "raw+ind", "outer_index_mismatch",
                {"stored_outer_index": int(arr[i]["outer_index"])},
            )
        )

    failed = np.nonzero(written & arr["fail_flag"])[0]
    for i in failed:
        failures.append(FailureRecord(phase, M, cell, batch, int(i), "raw+ind", "fail_flag", None))

    for endpoint, p_field, reject_field in (("raw", "p_raw", "reject_raw"), ("ind", "p_ind", "reject_ind")):
        p_values = arr[p_field]
        finite_mask = np.isfinite(p_values)

        nonfinite = np.nonzero(written & ~finite_mask)[0]
        for i in nonfinite:
            failures.append(
                FailureRecord(
                    phase, M, cell, batch, int(i), endpoint, "nonfinite_p",
                    {p_field: float(p_values[i])},
                )
            )

        in_range_mask = finite_mask & (p_values >= 0.0) & (p_values <= 1.0)
        out_of_range = np.nonzero(written & finite_mask & ~in_range_mask)[0]
        for i in out_of_range:
            failures.append(
                FailureRecord(
                    phase, M, cell, batch, int(i), endpoint, "p_out_of_range",
                    {p_field: float(p_values[i])},
                )
            )

        inconsistent = np.nonzero(written & in_range_mask & (arr[reject_field] != (p_values <= 0.05)))[0]
        for i in inconsistent:
            failures.append(
                FailureRecord(
                    phase, M, cell, batch, int(i), endpoint, "reject_p_inconsistent",
                    {reject_field: bool(arr[i][reject_field]), p_field: float(p_values[i])},
                )
            )

    return failures


def append_failure_records(sink: list, records: Iterable[FailureRecord]) -> None:
    """The failure side-record 'write path': appends fully-populated
    FailureRecord entries to the provided sink. A real runner would
    persist `sink` somewhere durable; that persistence layer is outside
    Phase-1 (pure-core) scope — this function is the seam a future
    runner hooks into."""
    sink.extend(records)


# ---------------------------------------------------------------------------
# §2.E.5 / §2.E.9.9 / §2.E.7: E_j, U_total, 72h go/no-go
# ---------------------------------------------------------------------------

TCRIT_DF4_ONE_SIDED_95 = 2.131846786326649
N_REPEATS = 5
N_M = 2_304_000
M_KEYS = frozenset({24, 36, 48})
WARMUP_PHASE_KEYS = frozenset({"P7", "Stage1", "Stage2"})


def u_total(e_j: Sequence[float]) -> float:
    """§2.E.5: U_total = mean(E_j) + tcrit * sd(E_j, ddof=1) / sqrt(5),
    using only the frozen tcrit constant — there is no parameter to
    override it with.

    Fail-closed (§2.E.1): raises InvalidTimingDataError unless e_j is
    real-numeric (not bool/complex/string/object) with shape exactly
    (5,) — a (5,1) array must be rejected, not silently squeezed —
    every E_j is finite and strictly positive, and the resulting
    U_total itself is finite and strictly positive.
    """
    arr = _require_real_numeric_array(e_j, "e_j")
    if arr.shape != (N_REPEATS,):
        raise InvalidTimingDataError(f"e_j must have shape ({N_REPEATS},), got {arr.shape}")
    if not np.all(np.isfinite(arr)) or not np.all(arr > 0):
        raise InvalidTimingDataError("E_j must be finite and strictly positive")
    mean_e = float(arr.mean())
    sd_e = float(arr.std(ddof=1))
    result = mean_e + TCRIT_DF4_ONE_SIDED_95 * sd_e / math.sqrt(N_REPEATS)
    if not (math.isfinite(result) and result > 0):
        raise InvalidTimingDataError("U_total must be finite and strictly positive")
    return result


def go_no_go(total_seconds: float) -> bool:
    """§2.E.7: PASS iff U_total/3600 <= 72 (equality counts as PASS).
    Fail-closed unless total_seconds is a real, finite, strictly
    positive number — bool/complex/string are rejected, and a negative
    value must never be allowed to trivially PASS."""
    total_seconds = _require_real_scalar(total_seconds, "U_total")
    if not total_seconds > 0:
        raise InvalidTimingDataError("U_total must be finite and strictly positive")
    return total_seconds / 3600.0 <= 72.0


def compute_e_j(
    global_seed_setup: float,
    startup: float,
    outer_seed_setup: float,
    aggregation_bookkeeping: float,
    close: float,
    warmups: Mapping[str, float],
    rate_by_m: Mapping[int, float],
) -> float:
    """§2.E.5/§2.E.9: one repeat's E_j —

        E_j = global_seed_setup + startup + outer_seed_setup
              + aggregation_bookkeeping + close
              + sum(warmups) + sum((N_M - 200) * rate_M)

    `warmups` keys must be exactly {P7, Stage1, Stage2}; `rate_by_m` keys
    must be exactly {24, 36, 48}. N_M is the frozen 2,304,000 constant,
    identical across all three M (per §2.E — the per-M workload count is
    the same, only the per-outer rate differs by M). Every one-time
    component and every warmup must be finite and >=0; every rate must
    be finite and strictly >0; the resulting E_j must be finite and
    strictly >0. All fail-closed.
    """
    one_time = {
        "global_seed_setup": global_seed_setup,
        "startup": startup,
        "outer_seed_setup": outer_seed_setup,
        "aggregation_bookkeeping": aggregation_bookkeeping,
        "close": close,
    }
    for name, value in one_time.items():
        one_time[name] = _require_finite_nonnegative(value, name)

    if not isinstance(warmups, collections.abc.Mapping):
        raise InvalidTimingDataError(f"warmups must be a mapping, got {type(warmups).__name__}")
    if not isinstance(rate_by_m, collections.abc.Mapping):
        raise InvalidTimingDataError(f"rate_by_m must be a mapping, got {type(rate_by_m).__name__}")

    if set(warmups.keys()) != WARMUP_PHASE_KEYS:
        raise InvalidTimingDataError(
            f"warmups keys must be exactly {sorted(WARMUP_PHASE_KEYS)}, got {sorted(warmups.keys())}"
        )
    warmup_values = {
        phase: _require_finite_nonnegative(value, f"warmups[{phase}]")
        for phase, value in warmups.items()
    }

    # Validate key *type* before the set-equality check: Python's
    # 24 == 24.0 (and hash(24) == hash(24.0)) means a float key like
    # 24.0 would otherwise slip through `set(rate_by_m.keys()) == M_KEYS`
    # undetected.
    for m in rate_by_m.keys():
        _require_int(m, "rate_by_m key")
    if set(rate_by_m.keys()) != M_KEYS:
        raise InvalidTimingDataError(
            f"rate_by_m keys must be exactly {sorted(M_KEYS)}, got {sorted(rate_by_m.keys())}"
        )
    rate_values = {}
    for m, rate in rate_by_m.items():
        rate = _require_real_scalar(rate, f"rate_by_m[{m}]")
        if not rate > 0:
            raise InvalidTimingDataError(f"rate_by_m[{m}] must be strictly positive, got {rate!r}")
        rate_values[m] = rate

    total = sum(one_time.values()) + sum(warmup_values.values())
    total += sum((N_M - 200) * rate for rate in rate_values.values())

    if not (math.isfinite(total) and total > 0):
        raise InvalidTimingDataError("E_j must be finite and strictly positive")
    return total


# ---------------------------------------------------------------------------
# §2.E.9.1/§2.E.9.2 chunk checkpoint / rate
# ---------------------------------------------------------------------------


def rate_from_checkpoints(
    stream_start_ns: int,
    t200_ns: int,
    t800_ns: int,
    t1000_ns: int,
    stream_stop_ns: int,
) -> float:
    """rate_jM = (T800-T200)/600, converted from ns to seconds.

    All five timestamps must be genuine ints (np.integer accepted, bool
    and float rejected — perf_counter_ns() always returns int). Requires
    the full ordering
        stream_start_ns < T200 < T800 < T1000 <= stream_stop_ns
    (T1000 may equal stream_stop_ns; every earlier inequality is strict),
    and a finite, strictly positive duration and rate. An OverflowError
    from dividing an absurdly large integer is converted to
    InvalidTimingDataError rather than leaking out raw. All fail-closed.
    """
    for value, name in (
        (stream_start_ns, "stream_start_ns"),
        (t200_ns, "t200_ns"),
        (t800_ns, "t800_ns"),
        (t1000_ns, "t1000_ns"),
        (stream_stop_ns, "stream_stop_ns"),
    ):
        _require_int(value, name)

    if not (stream_start_ns < t200_ns < t800_ns < t1000_ns <= stream_stop_ns):
        raise InvalidTimingDataError(
            "checkpoints must satisfy stream_start < T200 < T800 < T1000 <= stream_stop"
        )

    try:
        duration_ns = t800_ns - t200_ns
        duration_finite = math.isfinite(duration_ns)
        rate = duration_ns / 600 / 1e9
        rate_finite = math.isfinite(rate)
    except OverflowError as exc:
        raise InvalidTimingDataError(f"checkpoint arithmetic overflowed: {exc}") from exc

    if not (duration_finite and duration_ns > 0):
        raise InvalidTimingDataError("T800-T200 duration must be finite and strictly positive")
    if not (rate_finite and rate > 0):
        raise InvalidTimingDataError("rate must be finite and strictly positive")
    return rate
