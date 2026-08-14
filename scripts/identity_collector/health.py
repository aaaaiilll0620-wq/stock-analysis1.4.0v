"""HealthSummary — FR-48, effective_persistence_status join (check #8).
Counters derive from EFFECTIVE status, joining receipt + ledger, never from
the receipt's own frozen field alone (round-6 bug this design corrected: a
recovered PENDING_MIRROR receipt must be countable as COMMITTED).
"""
from identity_collector import SCHEMA_VERSION
from identity_collector.ledger import mirror_events_for_run


def effective_persistence_status(receipt: dict, ledger_entries: list) -> str:
    """Item 3 fix: previously trusted a mirror event's `new_status=="VERIFIED"`
    literally, with no re-check. If a bogus mirror event ever reached the
    ledger (e.g. via the generic `ledger.append_event` instead of
    `append_mirror_recovery_event`, bypassing check #11 at write time), health
    counting would have silently promoted an under-evidenced run to COMMITTED.
    Re-running check #11 here, at READ time, is the second, independent gate
    the user asked for: verification must happen before ledger append AND
    before health counts a recovery, not merely one or the other."""
    if receipt["persistence_status"] in ("COMMITTED", "FAILED"):
        return receipt["persistence_status"]
    from identity_collector import schema_validation as sv

    verified = []
    for e in mirror_events_for_run(ledger_entries, receipt["run_id"]):
        if e["payload"]["new_status"] != "VERIFIED":
            continue
        ok, _problems = sv.check_11_mirror_recovery_per_file(e["payload"], receipt)
        if ok:
            verified.append(e)
    return "COMMITTED" if verified else "PENDING_MIRROR"


def build_health_summary(receipts: list, ledger_entries: list, current_lock_state: str, current_lock_holder_pid, generated_at: dict) -> dict:
    successes = [r for r in receipts if r.get("persistence_status") != "FAILED"]
    failures = [r for r in receipts if r.get("persistence_status") == "FAILED"]
    eff = {r["run_id"]: effective_persistence_status(r, ledger_entries) for r in successes}
    committed = [r for r in successes if eff[r["run_id"]] == "COMMITTED"]
    pending = [r for r in successes if eff[r["run_id"]] == "PENDING_MIRROR"]

    last_success = max(committed, key=lambda r: r["completed_at"]["utc"], default=None)
    last_failure = max(failures, key=lambda r: r["completed_at"]["utc"], default=None)
    monthly_eligible = [r for r in committed if r["monthly_status"] == "MONTHLY_ELIGIBLE"]
    comparable = [r for r in committed if r["identity_status"] == "COMPARABLE_IDENTITY"]
    source_mutation_count = sum(1 for r in receipts if r.get("source_mutation"))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "last_success_run_id": last_success["run_id"] if last_success else None,
        "last_success_at": last_success["completed_at"] if last_success else None,
        "last_failure_run_id": last_failure["run_id"] if last_failure else None,
        "last_failure_at": last_failure["completed_at"] if last_failure else None,
        "last_failure_code": last_failure["failure_code"] if last_failure else None,
        "pending_mirror_count": len(pending),
        "monthly_eligible_count": len(monthly_eligible),
        "comparable_identity_count": len(comparable),
        "source_mutation_count": source_mutation_count,
        "current_lock_state": current_lock_state,
        "current_lock_holder_pid": current_lock_holder_pid,
    }
