"""FR-45 scheduling mutex. Lock lease fixed at 120 minutes (a) — never
config/param-overridable, so it is a module constant, not a function
parameter. Staleness requires BOTH age>120min AND the recorded PID being dead
(b); collector never auto-reclaims a stale lock, only flags it (c); manual
unlock is CLI-only, requires expected run-id + operator reason (d), and
appends an unlock_receipt rather than editing the original lock record (e).
"""
import json
import os
from datetime import datetime
from pathlib import Path

from identity_collector.timestamps import now_pair

LOCK_LEASE_MINUTES = 120


class LockHeld(Exception):
    pass


class LockStaleDetected(Exception):
    pass


def _lock_path(lock_dir) -> Path:
    return Path(lock_dir) / "collector.lock"


def read_lock(lock_dir):
    p = _lock_path(lock_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def lock_state(lock_dir, now_utc: datetime, pid_is_alive) -> tuple[str, dict | None]:
    """pid_is_alive: injectable callable(pid:int)->bool -- tests inject a fake
    liveness table rather than querying the real OS."""
    rec = read_lock(lock_dir)
    if rec is None:
        return "FREE", None
    acquired_at = datetime.fromisoformat(rec["acquired_at_utc"])
    age_minutes = (now_utc - acquired_at).total_seconds() / 60
    if age_minutes > LOCK_LEASE_MINUTES and not pid_is_alive(rec["pid"]):
        return "STALE_DETECTED", rec
    return "HELD", rec


def acquire(lock_dir, run_id: str, pid: int, now_utc: datetime, pid_is_alive) -> dict:
    """OS-level atomic exclusive acquisition (item 2 fix): the previous
    implementation read the lock, branched on its state, THEN wrote a new file
    -- a read-then-write race two genuinely concurrent processes could both
    pass through before either wrote (`os.replace`/plain `write_text` both
    silently overwrite an existing file, so a loser could still "win"). The
    actual mutual-exclusion primitive is `os.open(..., O_CREAT | O_EXCL)`:
    the OS's filesystem layer atomically arbitrates which of two concurrent
    callers gets to CREATE the file; the other gets FileExistsError with no
    window for both to succeed. `lock_state` is still consulted first, but
    ONLY to produce the STALE_DETECTED diagnostic (c) -- the actual winner
    determination for two live, concurrent, non-stale callers is the atomic
    create below, not the preceding read."""
    state, rec = lock_state(lock_dir, now_utc, pid_is_alive)
    if state == "STALE_DETECTED":
        # (c): MUST NOT auto-reclaim -- refuse and let the caller write a
        # LOCK_STALE_DETECTED diagnostic; the stale record is left untouched.
        raise LockStaleDetected(f"stale lock detected (age>120min, pid {rec['pid']} dead) -- refusing to start; manual unlock required")

    new_rec = {"run_id": run_id, "pid": pid, "acquired_at_utc": now_utc.isoformat()}
    Path(lock_dir).mkdir(parents=True, exist_ok=True)

    # Write full content to a PID-unique temp name first, THEN atomically
    # hard-link it into place. os.link() fails atomically with FileExistsError
    # if the destination name already exists -- unlike O_CREAT|O_EXCL on the
    # final name directly, this leaves no window where a concurrent reader
    # could observe the lock file existing with empty/partial content (a real
    # race this test suite's multi-process test caught: the loser's
    # read_lock() sometimes read the winner's file before its write flushed).
    tmp_path = Path(lock_dir) / f".lock.{os.getpid()}.tmp"
    tmp_path.write_text(json.dumps(new_rec), encoding="utf-8")
    try:
        os.link(str(tmp_path), str(_lock_path(lock_dir)))
    except FileExistsError:
        losing_rec = read_lock(lock_dir)
        holder = losing_rec["pid"] if losing_rec else "?"
        holder_run = losing_rec["run_id"] if losing_rec else "?"
        raise LockHeld(f"lock held by pid={holder} run_id={holder_run}") from None
    finally:
        tmp_path.unlink(missing_ok=True)
    return new_rec


def release(lock_dir, run_id: str) -> None:
    rec = read_lock(lock_dir)
    if rec is not None and rec["run_id"] == run_id:
        _lock_path(lock_dir).unlink()


def manual_unlock(lock_dir, expected_run_id: str, operator: str, reason: str, clock) -> dict:
    """(d): CLI-only, requires BOTH expected run-id and operator reason -- missing
    either raises. (e): returns an unlock_receipt to append to
    collector_ledger.jsonl; the original lock file is deleted here (this IS the
    human override), but the ledger entry documents who/why/when, never edits
    a prior record."""
    if not expected_run_id or not reason:
        raise ValueError("manual_unlock requires both expected_run_id and reason")
    rec = read_lock(lock_dir)
    if rec is None:
        raise ValueError("no lock currently held -- nothing to unlock")
    if rec["run_id"] != expected_run_id:
        raise ValueError(f"expected_run_id {expected_run_id!r} does not match held lock's run_id {rec['run_id']!r}")
    _lock_path(lock_dir).unlink()
    return {
        "run_id_of_lock": rec["run_id"],
        "expected_run_id_provided": expected_run_id,
        "operator": operator,
        "reason": reason,
        "unlocked_at": now_pair(clock),
    }
