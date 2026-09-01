# -*- coding: utf-8 -*-
"""C-73 · the diagnostic replay iteration contract.

The B0.n retrospective diagnostic lineage is an ITERATIVE REPAIR LOOP. It ran
2 -> 4 -> 4 -> 45 -> 66 -> 66 periods across B0.1 .. B0.7, one conformance
repair per round, and it had no rule for when it stops or for what a single
repair may touch. Meanwhile every round wrote `port_value` into
`period_progress.jsonl`, which the operator reads on every iteration.

A loop that repairs until the run completes, run by someone who can see the
partial NAV as they go, is formally indistinguishable from an in-sample search.
Not because anyone tuned anything -- because nothing in the artefacts can tell
the two apart afterwards.

So this module mechanises four things, in the order that makes each one mean
something:

  R1  blinding      outcome quantities leave the iteration-visible stream
  R2  repair claim  the hypothesis and the scope are frozen BEFORE the edit
  R3  blind proof   the evidence a repair cites carries no outcome
  R4  stop          141/141 with zero failures, then and only then the seal opens
  R5  divergence    how far a repair moved the path, measured without reading it

Two rules that look obvious are deliberately NOT here, both refuted by measuring
the lineage instead of reasoning about it:

  * "the diff must stay inside the failing traceback's files." B0.6 raised
    `PriceObservabilityError` from `core/b0_pit_observability.py`; C-66 fixed it
    by changing `core/b0_corporate_actions.py` and `core/b0_state.py` and did
    not touch the raising module at all. Symptom site and root-cause site are
    systematically different here. The rule would have rejected the single most
    substantive repair in the lineage.

  * "extend STRATEGY_OUTCOME_ROW_KEYS with port_value." That tuple is consumed
    by `verify_opening_state_restatement`, which raises on it BEFORE reaching
    the branch that permits `port_value` when it equals the sealed opening cash.
    Adding the key would flip the legacy L2 run's condition 2 from PASS to FAIL
    and silently rewrite C-57's recorded evidence. The set below is a NEW
    constant that reads the old one without touching it.

Scope: B0.n retrospective diagnostic replay only. Nothing here authorises,
reopens, or otherwise reaches the official Frozen B0 L2 path, which C-72 closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

from core.b0_canonical_hash import canonical_sha256
from core.b0_master_prereg import STRATEGY_OUTCOME_ROW_KEYS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PERIODS_REQUIRED = 141

CONFORMANCE_STREAM = "period_progress.jsonl"
OUTCOME_STREAM = "outcome_series.jsonl"
FAILURE_STREAM = "failure_record.jsonl"
CA_LEDGER_STREAM = "ca_transition_ledger.jsonl"
REPAIR_CLAIM = "repair_claim.json"
TERMINAL_RESULT = "final_result.json"

# R1. Every stream a human reads while the loop is still running.
BLINDED_ARTEFACTS: tuple[str, ...] = (
    CONFORMANCE_STREAM, FAILURE_STREAM, CA_LEDGER_STREAM, REPAIR_CLAIM,
)

# R1/R7. `positions` is NOT here, by a named decision: it is the primary
# conformance signal (positions == 0 says the decision layer died) and it is the
# only divergence witness in R5 that survives a state-hash scope change. It does
# carry weak outcome information -- B0.6 -> B0.7 moved it 23 -> 22 at seq 49 --
# and a run's terminal record must say so rather than let it pass unremarked.
DIAGNOSTIC_OUTCOME_ROW_KEYS: tuple[str, ...] = tuple(sorted(set(
    STRATEGY_OUTCOME_ROW_KEYS + (
        "port_value", "cash_after", "nav", "nav_series", "nav_rows",
        "terminal_wealth", "wealth_multiple", "sharpe_0rf", "gates",
        "performance", "metrics", "opening_cash_after",
    ))))

POSITIONS_KEY = "positions"

# R5. The scope-stable divergence witness, added after applying R5 to the real
# lineage exposed that `positions` is a LAGGING one: C-66 moved the economics at
# seq 12 and the position COUNT only at seq 49, so a count-based R5 reported 49
# and was blind to the 37 periods in between. `post_state_hash` would have seen
# seq 2, but it is uninterpretable once the state domain widens (§1.5).
#
# A hash over holdings alone is strictly MORE blind than the count it
# supplements -- it is a change detector, not an information channel: it yields
# one bit (same / different) and no one can read a selection back out of it,
# whereas `positions` publishes an integer every period. It is also finer: a
# 20 -> 20 swap moves the hash and leaves the count flat.
HOLDINGS_KEY = "holdings_hash"


class DiagnosticIterationViolation(RuntimeError):
    """Base: the iteration contract was not honoured."""


class OutcomeLeak(DiagnosticIterationViolation):
    """R1: a strategy-outcome quantity reached an iteration-visible stream."""


class RepairClaimExists(DiagnosticIterationViolation):
    """R2: this run already froze a repair claim. Nothing was written."""


class RepairNotAdmissible(DiagnosticIterationViolation):
    """R2/R3: the repair is not the one the claim froze."""


class StopConditionNotMet(DiagnosticIterationViolation):
    """R4: the loop has not terminated, so nothing may be unsealed."""


# =============================================================================
# R1 · blinding
# =============================================================================

def _rows(path: str) -> list[dict]:
    out = []
    if not os.path.exists(path):
        return out
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
    else:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        out = payload if isinstance(payload, list) else [payload]
    return out


def _offending_keys(value, prefix: str = "") -> list[str]:
    """Every outcome-bearing key reachable in `value`, path-qualified.

    Recursive because `ca_transition_ledger.jsonl` rows are built from a
    dataclass `__dict__` and nothing guarantees they stay flat.
    """
    found = []
    if isinstance(value, dict):
        for key, sub in value.items():
            here = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in DIAGNOSTIC_OUTCOME_ROW_KEYS:
                found.append(here)
            found.extend(_offending_keys(sub, here))
    elif isinstance(value, (list, tuple)):
        for i, sub in enumerate(value):
            found.extend(_offending_keys(sub, f"{prefix}[{i}]"))
    return found


def assert_stream_blinded(path: str) -> dict:
    """R1: this artefact carries no outcome quantity. Returns what it measured.

    Keys, not values. A free-text `error` or `traceback` field can quote a
    number and this will not catch it; that limit is declared rather than
    papered over, because a value scan on prose would either miss the real cases
    or reject legitimate error text, and an enforcement nobody trusts is worse
    than a declared boundary.
    """
    rows = _rows(path)
    for i, row in enumerate(rows):
        offending = _offending_keys(row)
        if offending:
            raise OutcomeLeak(
                f"R1: {os.path.relpath(path, REPO_ROOT)} row {i} carries "
                f"{offending}. An iteration-visible stream may not hold a "
                f"quantity that is only knowable after a strategy decision: "
                f"that is what makes 'repair until it completes' and 'tune "
                f"until it looks good' indistinguishable afterwards.")
    return {"path": os.path.relpath(path, REPO_ROOT).replace("\\", "/"),
            "rows_checked": len(rows), "blinded": True,
            "key_set_only": True}


def assert_run_blinded(run_dir: str) -> dict:
    """R1 across every iteration-visible artefact of one run.

    An absent artefact is NAMED absent rather than dropped from the result.
    Filtering by `os.path.exists` and returning only what was found meant a run
    with no streams at all reported `{}` and read as blinded -- so deleting the
    conformance stream made a run MORE compliant, not less. `REPAIR_CLAIM` is
    legitimately absent on a first iteration, so absence is reported here rather
    than refused; R4 is where the conformance stream's presence is required.
    """
    out = {}
    for name in BLINDED_ARTEFACTS:
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            out[name] = assert_stream_blinded(path)
        else:
            out[name] = {"path": os.path.relpath(path, REPO_ROOT).replace(
                "\\", "/"), "present": False, "checked": False}
    return out


# =============================================================================
# R2/R3 · the repair claim
# =============================================================================

REPAIR_CLAIM_FIELDS: tuple[str, ...] = (
    "cites", "hypothesized_root_cause", "falsifier", "declared_scope",
    "parent_commit", "declared_at",
)


def _exclusive_write(path: str, blob: bytes) -> str:
    """Create-or-fail, one syscall. Same primitive as C-58/C-59, same reason:
    a claim that can be rewritten after the fact is not a claim."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        os.write(fd, blob)
    finally:
        os.close(fd)
    return path


def _canonical_bytes(payload) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
    return (body + "\n").replace("\r\n", "\n").encode("utf-8")


def repair_claim_path(run_dir: str) -> str:
    return os.path.join(run_dir, REPAIR_CLAIM)


def create_repair_claim(run_dir: str, payload: dict) -> str:
    """R2: freeze the hypothesis and the scope BEFORE editing anything.

    The single-shot discipline of `docs/研究紀律_ResearchDiscipline.md` §2,
    applied to conformance repair. What stops an already-seen NAV prefix from
    biasing the work is not that the operator forgot it -- they did not -- it is
    that an admissible repair has exactly one declared shape, fixed before the
    repaired trajectory exists.
    """
    missing = [f for f in REPAIR_CLAIM_FIELDS if not payload.get(f)]
    if missing:
        raise RepairNotAdmissible(
            f"R2: a repair claim must bind {missing}. A claim that cannot say "
            f"what it repairs, on what evidence, or how it could be wrong, is "
            f"not a claim.")
    falsifier = payload["falsifier"]
    if not isinstance(falsifier, dict) or not falsifier.get("file") \
            or not falsifier.get("test"):
        raise RepairNotAdmissible(
            "R2: `falsifier` must name {file, test}. A repair with no test that "
            "FAILS before it is not a conformance repair, it is a change.")
    for offending in (_offending_keys(payload),):
        if offending:
            raise OutcomeLeak(
                f"R3: the repair claim itself carries {offending}.")
    os.makedirs(run_dir, exist_ok=True)
    try:
        return _exclusive_write(repair_claim_path(run_dir),
                                _canonical_bytes(dict(payload)))
    except FileExistsError as exc:
        raise RepairClaimExists(
            f"R2: {repair_claim_path(run_dir)} already exists. A claim is "
            f"frozen once; widening `declared_scope` means voiding this "
            f"iteration and opening a new one, with the voided claim kept. "
            f"Nothing has been written."
        ) from exc


def read_repair_claim(run_dir: str) -> dict | None:
    path = repair_claim_path(run_dir)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_cited_failure(parent_run_dir: str, cites: dict) -> dict:
    """R2.1: the cited failure row must exist and resolve to exactly one row."""
    rows = _rows(os.path.join(parent_run_dir, FAILURE_STREAM))
    if not rows:
        raise RepairNotAdmissible(
            f"R2: {parent_run_dir} holds no failure record. A run that did not "
            f"fail affords no admissible repair -- and a completed 141/141 run "
            f"affords no next iteration at all.")
    matched = []
    for row in rows:
        if cites.get("event_id") and row.get("event_id") != cites["event_id"]:
            continue
        if cites.get("error_type") and row.get("error_type") != cites["error_type"]:
            continue
        if cites.get("seq") is not None and row.get("seq") != cites["seq"]:
            continue
        matched.append(row)
    if len(matched) != 1:
        raise RepairNotAdmissible(
            f"R2: `cites` resolved to {len(matched)} rows in "
            f"{os.path.join(parent_run_dir, FAILURE_STREAM)}; it must resolve "
            f"to exactly one. Cite `event_id`, or `error_type` with `seq`.")
    return matched[0]


def _git(*args: str) -> str:
    return subprocess.run(("git",) + args, cwd=REPO_ROOT, check=True,
                          capture_output=True, text=True).stdout


def changed_files(parent_commit: str, head: str = "HEAD") -> list[str]:
    """Committed diff UNION working-tree dirt.

    The union, not the diff alone: an uncommitted edit is still an edit that
    shaped the run, and a scope rule that only sees commits is one `git stash`
    away from meaning nothing.
    """
    out = set(p for p in _git("diff", "--name-only", parent_commit, head)
              .splitlines() if p.strip())
    # `-uall`: without it git collapses an untracked DIRECTORY into a single
    # `?? path/` entry, and `_in_scope` compares paths exactly -- so a repair
    # that correctly declared `research/b0_l3_runner/run_l3_prospective.py`
    # would be refused as out-of-scope for a path naming its directory. The
    # refusal is fail-closed but false, and the remedy its message proposes
    # (void the iteration) is the wrong one.
    for line in _git("status", "--porcelain", "-uall").splitlines():
        entry = line[3:].strip().split(" -> ")[-1]
        if not entry:
            continue
        if entry.endswith("/"):
            # Belt to `-uall`'s braces: a directory here means the expansion did
            # not happen, and every scope decision below it would be silently
            # wrong. Refuse rather than judge scope on a path that names no file.
            raise RepairNotAdmissible(
                f"R2: `git status` reported the directory {entry!r} rather than "
                f"the files inside it, so no scope decision about it can be "
                f"trusted. Expected `--porcelain -uall` to expand it.")
        out.add(entry)
    return sorted(out)


def _in_scope(path: str, declared: list[str]) -> bool:
    path = path.replace("\\", "/")
    if path.startswith("tests/") or path.startswith("docs/"):
        return True
    return any(path == d.replace("\\", "/") for d in declared)


def assert_repair_admissible(run_dir: str, parent_run_dir: str,
                             changed: list[str] | None = None) -> dict:
    """R2/R3: this repair is the one the claim froze, on blind evidence."""
    claim = read_repair_claim(run_dir)
    if claim is None:
        raise RepairNotAdmissible(
            f"R2: {repair_claim_path(run_dir)} does not exist. The claim is "
            f"written before the edit, not reconstructed after it.")
    cited = resolve_cited_failure(parent_run_dir, claim["cites"])
    offending = _offending_keys(cited)
    if offending:
        raise OutcomeLeak(
            f"R3: the cited failure row carries {offending}. A repair that "
            f"cannot be justified from outcome-free evidence is not a "
            f"conformance repair.")
    changed = changed_files(claim["parent_commit"]) if changed is None else changed
    out_of_scope = [p for p in changed if not _in_scope(p, claim["declared_scope"])]
    if out_of_scope:
        raise RepairNotAdmissible(
            f"R2: {out_of_scope} lie outside the frozen `declared_scope` "
            f"{claim['declared_scope']}. Widening the scope after seeing the "
            f"repaired trajectory is the degree of freedom this contract "
            f"exists to remove: void this iteration and open a new claim.")
    return {"claim": claim, "cited_failure_seq": cited.get("seq"),
            "cited_failure_classification": cited.get("classification"),
            "changed_files": changed, "admissible": True}


# =============================================================================
# R4 · the stopping condition
# =============================================================================

def assert_stop_condition(run_dir: str,
                          periods_required: int = PERIODS_REQUIRED) -> dict:
    """R4: mechanical, outcome-independent, no judgement call anywhere in it."""
    final_path = os.path.join(run_dir, TERMINAL_RESULT)
    if not os.path.exists(final_path):
        raise StopConditionNotMet(
            f"R4: {final_path} does not exist; the run has not terminated.")
    with open(final_path, encoding="utf-8") as fh:
        final = json.load(fh)
    done = final.get("periods_executed")
    if done != periods_required:
        raise StopConditionNotMet(
            f"R4: periods_executed={done!r}, required {periods_required}. "
            f"The loop stops when the replay completes, not when it has gone "
            f"far enough to look convincing.")
    # The conformance stream is the thing `periods_executed` is ABOUT, and
    # until this check existed nothing counted it: a run directory holding a
    # hand-written `{"periods_executed": 141}` passed R4 outright, and the
    # fixture in this module's own test suite wrote three progress rows beside
    # exactly that number. For a rule whose contract is "mechanical,
    # outcome-independent, no judgement call anywhere in it", the one quantity
    # it gates on may not be the one quantity nobody verifies.
    progress_path = os.path.join(run_dir, CONFORMANCE_STREAM)
    if not os.path.exists(progress_path):
        raise StopConditionNotMet(
            f"R4: {progress_path} does not exist. A run that claims "
            f"{done} completed periods and carries no conformance stream has "
            f"not been shown to have executed any.")
    progress = _rows(progress_path)
    if len(progress) != done:
        raise StopConditionNotMet(
            f"R4: {TERMINAL_RESULT} claims periods_executed={done} but "
            f"{CONFORMANCE_STREAM} holds {len(progress)} row(s). The claim and "
            f"the stream it is about must be the same number.")
    failures = _rows(os.path.join(run_dir, FAILURE_STREAM))
    if failures:
        raise StopConditionNotMet(
            f"R4: {len(failures)} failure record row(s) present. A completed "
            f"run with a recorded failure has not met the stop condition.")
    blinded = assert_run_blinded(run_dir)
    return {"run_dir": os.path.relpath(run_dir, REPO_ROOT).replace("\\", "/"),
            "periods_executed": done, "failure_rows": 0,
            "blinded_streams": sorted(n for n, v in blinded.items()
                                      if v.get("blinded")),
            "absent_artefacts": sorted(n for n, v in blinded.items()
                                       if not v.get("present", True)), "stop_condition_met": True}


def assert_outcome_release_permitted(run_dir: str,
                                     periods_required: int = PERIODS_REQUIRED
                                     ) -> str:
    """The only supported door to `outcome_series.jsonl`. Opens after R4."""
    assert_stop_condition(run_dir, periods_required)
    return os.path.join(run_dir, OUTCOME_STREAM)


def read_outcome_series(run_dir: str,
                        periods_required: int = PERIODS_REQUIRED) -> list[dict]:
    """R1/R4: sealed during the loop, readable the moment the loop is over."""
    return _rows(assert_outcome_release_permitted(run_dir, periods_required))


# =============================================================================
# R5 · trajectory divergence
# =============================================================================

def holdings_fingerprint(shares) -> str:
    """R5: the canonical hash of a portfolio's composition, and nothing else.

    Zero-share entries are dropped rather than hashed: a security that fell out
    of the book and one that was never in it are the same portfolio, and a
    fingerprint that disagreed would report a divergence no decision made.

    Deliberately NOT the state hash. This covers `{sid: shares}` only, so it
    does not move when a repair widens what the state carries -- which is the
    entire reason `post_state_hash` could not answer the question for C-66.
    """
    book = {str(sid): int(n) for sid, n in dict(shares).items() if int(n)}
    return canonical_sha256(book)


def _scope_fingerprint(rows: list[dict]) -> tuple[str, ...]:
    """What the progress schema exposes, which is a proxy for what the state
    hash covers. B0.7 added `claim_only_securities` when it widened the state
    domain, and its seq-1 `state_hash` therefore differs from B0.6's while the
    economics of that period are identical."""
    return tuple(sorted(rows[0])) if rows else ()


def compute_trajectory_divergence(parent_progress: str,
                                  child_progress: str) -> dict:
    """R5: how far the repair moved the path, computed WITHOUT any outcome.

    Not a pass/fail gate. A genuine conformance repair moves the trajectory --
    C-66 moved it from seq 12 -- and a rule forbidding that would forbid
    repairing anything. What was missing was not a prohibition, it was a
    measurement: nothing in B0.7's artefacts says how far it moved B0.6.
    """
    a, b = _rows(parent_progress), _rows(child_progress)
    for rows, path in ((a, parent_progress), (b, child_progress)):
        for i, row in enumerate(rows):
            offending = _offending_keys(row)
            if offending:
                raise OutcomeLeak(
                    f"R5: refusing to compare {path} row {i}, which carries "
                    f"{offending}. Divergence is measured on outcome-free "
                    f"fields or it is not measured.")
    scope_a, scope_b = _scope_fingerprint(a), _scope_fingerprint(b)
    scope_changed = scope_a != scope_b
    n = min(len(a), len(b))

    def first_divergence(key: str) -> int | None:
        for i in range(n):
            if a[i].get(key) != b[i].get(key):
                return a[i].get("seq", i + 1)
        return None

    positions_seq = first_divergence(POSITIONS_KEY)
    hash_seq = first_divergence("post_state_hash")
    # EVERY row, not `a[0], b[0]`. If `holdings_hash` was added mid-stream the
    # first row lacks it and R5 silently fell back to the `positions` witness
    # that HOLDINGS_KEY was introduced to replace; if it is dropped mid-stream
    # in one run and not the other, `first_divergence` compares None against a
    # hash and reports a divergence that is an artefact of schema, not of the
    # repair. The witness is available only when both streams carry it whole.
    holdings_present = bool(a and b) and all(
        HOLDINGS_KEY in row for row in (*a, *b))
    holdings_seq = first_divergence(HOLDINGS_KEY) if holdings_present else None
    return {
        "state_hash_scope_changed": scope_changed,
        "parent_schema": list(scope_a), "child_schema": list(scope_b),
        # The primary witness when both runs carry it: scope-stable and finer
        # than the count. Runs predating C-73 have no `holdings_hash`, and the
        # field then says so rather than reporting a null that reads as "no
        # divergence" -- the two are not the same answer.
        "holdings_hash_available": holdings_present,
        # Companion to the three `first_*_divergence_seq` nulls, for the same
        # reason `holdings_hash_available` accompanies the first of them: when
        # the runs are of different lengths only the common prefix is compared,
        # so `None` means "the prefix agreed", NOT "the repair moved nothing".
        # A parent that stopped at 66 and a child that ran 141 agree on every
        # row that was compared, and `parent_rows`/`child_rows` below are what
        # say the other 75 were never looked at.
        "compared_full_length": bool(a) and bool(b) and len(a) == len(b),
        "first_holdings_divergence_seq": holdings_seq,
        "first_positions_divergence_seq": positions_seq,
        "first_post_state_hash_divergence_seq": hash_seq,
        # A hash divergence under a changed scope says nothing: the same
        # economic state hashes differently once the state domain widens.
        "post_state_hash_divergence_interpretable": not scope_changed,
        "divergence_witness": ("holdings_hash" if holdings_present else
                               "positions (lagging; holdings_hash absent)"),
        "compared_prefix_length": n,
        "parent_rows": len(a), "child_rows": len(b),
    }


def sha256_of(path: str) -> tuple[str, int]:
    raw = open(path, "rb").read()
    return hashlib.sha256(raw).hexdigest(), len(raw)
