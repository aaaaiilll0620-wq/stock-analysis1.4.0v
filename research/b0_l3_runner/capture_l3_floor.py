"""Prepare an L3 floor capture from immutable run-scoped source snapshots.

The default operation is a no-publication diagnostic.  It copies mutable
landing surfaces into a private staging directory, builds and verifies the two
capture leaves, derives the floor and its two leg summaries, then removes the
staging tree.  It never creates a formal run, lineage, route seal or receipt.

Publication is deliberately not implemented here yet.  The prepared result is
the user of the contract: after it has exposed the real constraints, a narrow
ratified transaction may publish the already-defined evidence.

⚠ SUCCESS CLEANS UP.  FAILURE DOES NOT.
    The staging tree is removed only when the preparation completed.  A failed
    attempt is exactly the case whose evidence is irreplaceable — the
    floor/session mismatch this path exists to detect leaves nothing behind but
    a stack trace unless the leaves and the aggregate survive — so a failure
    MOVES the staged tree to `<staging_root>/failed_capture/<run_id>` and writes
    a `failure_evidence.json` beside it.  What must survive is not this module's
    opinion: `core.b0_l3_lineage_capture.FAILED_CAPTURE_PRESERVATION` names it,
    and `_preserve_failed_capture` checks each clause and records the answer.

⚠ A DECLARED LANDING DIRECTORY IS NOT A READ ONE.
    The planned leaves are enumerated from the private staging copies and then
    DECLARE the run directory the bytes will land in.  That address is empty at
    the moment the manifest is written, and its payload hash is what a published
    capture record would bind.  A string test that the staging path no longer
    appears in the JSON is satisfied precisely by the substitution being
    complete, so it proves nothing.  `assert_declaration_reconciles` replaces it
    with a real reconciliation: the planned leaf must be the read leaf with only
    its ADDRESS changed, every declared member is re-hashed against the staged
    bytes it was actually read from, the staged directory must hold exactly the
    declared members and nothing else, and the whole chain is bound back to the
    snapshot inventory digest as an explicit staging-provenance record.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_materializer"))

from core.b0_canonical_hash import canonical_sha256, file_sha256  # noqa: E402
from core.b0_l3_lineage_capture import (  # noqa: E402
    CAPTURE_AUTHORITY, CAPTURE_FILENAME, CONTRACT_VERSION,
    DIAGNOSTIC_EXPECTED_FLOOR, FAILED_CAPTURE_PRESERVATION,
    FLOOR_CAPTURE_REQUIRED_DATASETS, LINEAGE_ROOT_PARTS, PURPOSE_CAPTURE,
    RATIFIED_INVENTORY_AUTHORITY, assert_floor_is_a_trading_session,
    assert_prices_are_on_calendar, derive_leg_summaries,
    floor_capture_code_closure_sha256, next_attempt_run_id,
    publish_exclusively,
)
from research.b0_l3.l3_readers import read_calendar, read_prices  # noqa: E402
from research.b0_materializer import build_flat_leaves, build_prices_leaf  # noqa: E402
from research.b0_materializer.l3_temporal_snapshot import (  # noqa: E402
    TEMPORAL_SNAPSHOT_CONTRACT_VERSION, sessions_through,
    snapshot_directory,
)
from research.b0_materializer.source_ownership_manifest import (  # noqa: E402
    AGGREGATE_FILENAME, LEAF_FILENAME, assemble_aggregate, load_leaf,
    verify_aggregate, write_aggregate, write_leaf,
)

EVIDENCE_CLASS = "UNSEALED_DIAGNOSTIC"

# D4 · ONE definition of "today". `run_l3_prospective._taipei_today()` records a
# decision intent against `datetime.now(ZoneInfo("Asia/Taipei")).date()`. This
# module used `date.today()`, which on a UTC-configured host is the PREVIOUS day
# for the first eight hours of every Taipei day — so a capture and an intent
# taken in the same session could carry different calendar dates, and the run id
# stamps that date into the lineage identity. The clock is named here rather
# than imported so that the two modules stay independent but agree.
CAPTURE_TIMEZONE = ZoneInfo("Asia/Taipei")

# D1 · where a failed attempt's evidence lands. Stable and derived from the run
# id, because FAILED_CAPTURE_PRESERVATION's last clause is "the attempt id is
# never reused or cleared": a second attempt gets A(NN+1) and therefore its own
# directory, and a collision here means the id WAS reused, which aborts.
PRESERVED_FAILURE_DIRNAME = "failed_capture"
FAILURE_EVIDENCE_FILENAME = "failure_evidence.json"
FAILURE_EVIDENCE_SCHEMA = "b0_l3_floor_capture_failure_evidence@1"

# D2 · which of the two admissible reconciliations this module performs.
#
#   DECLARED_DIRECTORY_CONTAINS_THE_MEMBERS
#       only available AFTER the bytes have landed — i.e. after publication,
#       which this module deliberately does not perform.
#   STAGING_PROVENANCE_ASSERTED
#       available now: the declaration is checkable against the staged bytes
#       that were actually read, and the record says so in band.
#
# The first is still done opportunistically when the declared directory happens
# to exist, so a landing that disagrees with the manifest cannot slip past.
DECLARATION_RECONCILIATION = "STAGING_PROVENANCE_ASSERTED"
DECLARATION_RECONCILIATION_MATERIALIZED = \
    "STAGING_PROVENANCE_ASSERTED_AND_DECLARED_DIRECTORY_VERIFIED"

# D3 · the label that stops a machine-local digest being quoted as evidence.
NON_REPRODUCIBLE_VALIDATION_NOTICE = {
    "reproducibility": "NON_REPRODUCIBLE_MACHINE_LOCAL_PATHS",
    "admissible_as_capture_evidence": False,
    "why": (
        "the validation-pass leaves must point at the private staging snapshot "
        "the readers are about to open, so their `landing_directory` is a "
        "machine-absolute temporary path. That path is inside the leaf payload "
        "hash and therefore inside the aggregate's, so these two digests differ "
        "in every run, on every host and in every clone even when the source "
        "bytes are identical. They establish that THIS run's leaves and "
        "aggregate were internally consistent, and nothing else."),
    "compare_instead": ("planned_leaf_payload_sha256",
                        "planned_aggregate_payload_sha256"),
    "compare_instead_caveat": (
        "the planned digests are CLONE-STABLE, which is a smaller claim than "
        "reproducible: they declare repo-relative addresses, so the same source "
        "bytes observed at the same instant hash the same in any clone. They "
        "still carry `observed_at`, which is a fact about WHEN the sources were "
        "read and is meant to move between runs."),
}


class FloorCapturePreparationError(RuntimeError):
    """The no-publication preparation could not establish its evidence."""


def _taipei_now() -> dt.datetime:
    return dt.datetime.now(CAPTURE_TIMEZONE)


def _taipei_today() -> dt.date:
    return _taipei_now().date()


def _repo_state(repo_root: str) -> dict:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True,
        text=True, check=True).stdout.strip()
    tracked = subprocess.run(
        ["git", "diff", "--quiet"], cwd=repo_root).returncode == 0 and \
        subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_root).returncode == 0
    untracked = not bool(subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_root,
        capture_output=True, text=True, check=True).stdout.strip())
    return {"commit_sha": head, "tracked_clean": tracked,
            "untracked_clean": untracked}


def _quarantined_rows(pre_2019_dir: str,
                      boundary: str = "2019-01-01") -> int:
    import pandas as pd

    count = 0
    for name in sorted(os.listdir(pre_2019_dir)):
        if not name.lower().endswith(".parquet"):
            continue
        frame = pd.read_parquet(os.path.join(pre_2019_dir, name),
                                columns=["date"])
        dates = pd.to_datetime(frame["date"], errors="coerce").dt.strftime(
            "%Y-%m-%d")
        count += int((dates >= boundary).sum())
    return count


# --- D2 · declaration <-> read reconciliation ---------------------------------------

def _entry_landing(leaf: dict, entry: dict) -> str:
    """An entry's effective landing: its own if it has one, else the leaf's.

    `prices` needs the distinction — §2.8.3 splits its lineage at 2019-01-01 and
    the two halves live in different trees, so the pre-2019 entries carry their
    own address while the archives use the leaf's.
    """
    return str(entry.get("landing_directory")
               or leaf.get("landing_directory") or "")


def _addressless(leaf: dict) -> dict:
    """The leaf with every landing address removed.

    What is left is the part a re-declaration may NOT change: which files, which
    bytes, which members, which policies, which run.
    """
    body = {k: v for k, v in leaf.items()
            if k not in ("landing_directory", "entries")}
    body["entries"] = [{k: v for k, v in e.items() if k != "landing_directory"}
                       for e in leaf["entries"]]
    return body


def _files_in(directory: str) -> list:
    return sorted(n for n in os.listdir(directory)
                  if os.path.isfile(os.path.join(directory, n))
                  and not os.path.islink(os.path.join(directory, n)))


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def assert_declaration_reconciles(*, dataset: str, read_leaf: dict,
                                  planned_leaf: dict, requested_declarations,
                                  snapshots, repo_root: str = REPO) -> dict:
    """A DECLARED landing directory must be reconcilable with what was READ.

    The planned leaf declares `<final_run_dir>/inputs/...`, which is empty when
    the manifest is written; its payload hash is nonetheless what a published
    capture record would bind. The guard this replaces asked only whether the
    private staging path still APPEARED in the JSON — a test that the
    substitution passes exactly by being complete, and that therefore cannot
    fail for the reason it exists.

    Four things are established here instead, and any one of them failing is an
    abort:

    1 · the planned leaf is the read leaf with only its ADDRESS changed. Every
        locator, hash, member inventory, policy and disposition must be
        identical; a re-declaration that also re-enumerated is not a
        re-declaration.
    2 · each declared address corresponds to exactly one staged directory that
        was actually read, and vice versa. An address nobody read is refused by
        name rather than trusted.
    3 · every declared member is RE-HASHED against the staged bytes, and the
        staged directory must hold exactly the declared members — no extra file
        that the manifest does not name, no named file that is not there.
    4 · the staged directory is bound back to its `snapshot_directory` record,
        so the chain source -> snapshot inventory digest -> staged bytes ->
        declared address is stated explicitly and asserted, not implied.

    When the declared directory already exists on disk it is verified directly
    as well, which is the stronger of the two reconciliations; the record says
    which one was performed.

    Returns the staging-provenance record for the caller to publish alongside
    the manifest.
    """
    read_body, planned_body = _addressless(read_leaf), _addressless(planned_leaf)
    if canonical_sha256(read_body) != canonical_sha256(planned_body):
        differing = sorted(
            {e["locator"] for e in read_body["entries"]}
            ^ {e["locator"] for e in planned_body["entries"]}) or sorted(
            r["locator"] for r, p in zip(read_body["entries"],
                                         planned_body["entries"]) if r != p)
        raise FloorCapturePreparationError(
            "abort: the planned %s leaf is not the read leaf re-addressed. A "
            "declaration may change WHERE the bytes will live and nothing "
            "else; this one also changed %s. Differing/unpaired locators: %s"
            % (dataset,
               "its entries" if differing else "its non-entry body",
               differing or "<none — the leaf body itself differs>"))

    by_snapshot = {_key(s["snapshot"]): s for s in snapshots}
    pairs, mapping, reverse = [], {}, {}
    for read_entry, planned_entry in zip(read_leaf["entries"],
                                         planned_leaf["entries"]):
        staged = _entry_landing(read_leaf, read_entry)
        declared = _entry_landing(planned_leaf, planned_entry)
        if not staged or not declared:
            raise FloorCapturePreparationError(
                "abort: %s entry %s carries no landing directory on one side "
                "of the declaration" % (dataset, read_entry["locator"]))
        if mapping.setdefault(declared, staged) != staged:
            raise FloorCapturePreparationError(
                "abort: %s declares landing directory %s over two different "
                "staged directories (%s and %s). One address cannot stand in "
                "for two reads." % (dataset, declared, mapping[declared],
                                    staged))
        if reverse.setdefault(staged, declared) != declared:
            raise FloorCapturePreparationError(
                "abort: %s reads staged directory %s but declares it as both "
                "%s and %s" % (dataset, staged, reverse[staged], declared))
        pairs.append((declared, staged, planned_entry))

    # The addresses the CALLER asked to declare, checked independently of the
    # builders' own stamping. A declaration that is machine-absolute would hash
    # differently in every clone; one that resolves somewhere the caller never
    # named is a substitution nobody requested.
    resolved, wanted = {}, {_key(p) for p in requested_declarations}
    for declared in sorted(mapping):
        if os.path.isabs(declared):
            raise FloorCapturePreparationError(
                "abort: %s declares the machine-absolute landing directory %r. "
                "The declared address is inside the leaf payload hash, so the "
                "same source bytes would hash differently in every clone."
                % (dataset, declared))
        resolved[declared] = _key(os.path.join(repo_root, declared))
    unexpected = sorted(d for d in resolved if resolved[d] not in wanted)
    if unexpected:
        raise FloorCapturePreparationError(
            "abort: %s declares landing director(y/ies) %s, which resolve to "
            "paths the caller never asked to declare. Requested: %s"
            % (dataset, unexpected, sorted(requested_declarations)))

    declarations, materialized_all = [], bool(mapping)
    for declared in sorted(mapping):
        staged = mapping[declared]
        if not os.path.isdir(staged):
            raise FloorCapturePreparationError(
                "abort: %s was declared over staged directory %s, which is not "
                "a directory. There is nothing for the declaration to stand in "
                "for." % (dataset, staged))
        snapshot = by_snapshot.get(_key(staged))
        if snapshot is None:
            raise FloorCapturePreparationError(
                "abort: %s declares %s over staged directory %s, which is not "
                "one of this run's immutable source snapshots. A declaration "
                "whose read cannot be traced to a snapshot has no provenance."
                % (dataset, declared, staged))

        members = [e for d, s, e in pairs if d == declared]
        declared_names = sorted(e["locator"] for e in members)
        on_disk = _files_in(staged)
        if declared_names != on_disk:
            raise FloorCapturePreparationError(
                "abort: %s declares %s over staged directory %s, but the two "
                "do not enumerate the same members.\n  declared only: %s\n"
                "  staged only:   %s\nA declaration that does not cover exactly "
                "what was read is a manifest for a directory nobody enumerated."
                % (dataset, declared, staged,
                   sorted(set(declared_names) - set(on_disk)) or "none",
                   sorted(set(on_disk) - set(declared_names)) or "none"))

        snapshot_hashes = {e["path"]: e["raw_sha256"]
                           for e in snapshot.get("entries", ())}
        inventory = []
        for entry in sorted(members, key=lambda e: e["locator"]):
            locator, declared_hash = entry["locator"], entry["raw_sha256"]
            staged_hash = file_sha256(os.path.join(staged, locator))
            if staged_hash != declared_hash:
                raise FloorCapturePreparationError(
                    "abort: %s declares %s under %s with raw_sha256 %s, but the "
                    "staged bytes it was read from hash to %s."
                    % (dataset, locator, declared, declared_hash, staged_hash))
            if snapshot_hashes.get(locator) != declared_hash:
                raise FloorCapturePreparationError(
                    "abort: %s declares %s under %s with raw_sha256 %s, which "
                    "the snapshot inventory for %s does not carry (it has %r). "
                    "The declaration is not traceable to the snapshot that was "
                    "taken." % (dataset, locator, declared, declared_hash,
                                staged, snapshot_hashes.get(locator)))
            inventory.append({"locator": locator, "raw_sha256": declared_hash})

        # The stronger reconciliation, when it is available at all: the bytes
        # have landed, so check them rather than their provenance.
        materialized = os.path.isdir(os.path.join(repo_root, declared))
        if materialized:
            landing = os.path.join(repo_root, declared)
            landed = _files_in(landing)
            if landed != declared_names:
                raise FloorCapturePreparationError(
                    "abort: the declared landing directory %s EXISTS and does "
                    "not hold what %s declares.\n  declared only: %s\n"
                    "  landed only:   %s"
                    % (declared, dataset,
                       sorted(set(declared_names) - set(landed)) or "none",
                       sorted(set(landed) - set(declared_names)) or "none"))
            for entry in inventory:
                got = file_sha256(os.path.join(landing, entry["locator"]))
                if got != entry["raw_sha256"]:
                    raise FloorCapturePreparationError(
                        "abort: %s landed in %s with raw_sha256 %s but %s "
                        "declares %s" % (entry["locator"], declared, got,
                                         dataset, entry["raw_sha256"]))
        materialized_all = materialized_all and materialized

        declarations.append({
            "declared_landing_directory": declared,
            "declared_landing_directory_materialized": materialized,
            "read_from_staging_directory": staged.replace("\\", "/"),
            "staged_from_source": snapshot["source"],
            "snapshot_contract_version": snapshot["contract_version"],
            "snapshot_raw_inventory_digest": snapshot["raw_inventory_digest"],
            "members": inventory,
            "member_count": len(inventory),
        })

    return {
        "dataset": dataset,
        "reconciliation": (DECLARATION_RECONCILIATION_MATERIALIZED
                           if materialized_all else
                           DECLARATION_RECONCILIATION),
        "declared_directories_verified_directly": materialized_all,
        "note": (
            "the declared landing directories did not exist when this manifest "
            "was written; the declaration is bound to the staged bytes that "
            "WERE read, member by member, and to their snapshot inventory "
            "digest" if not materialized_all else
            "the declared landing directories exist and were verified directly "
            "as well as through their staging provenance"),
        "declarations": declarations,
        "addressless_leaf_sha256": canonical_sha256(planned_body),
    }


# --- D1 · failure preserves the evidence --------------------------------------------

def _tree(root: str) -> list:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            out.append(os.path.relpath(os.path.join(dirpath, name),
                                       root).replace("\\", "/"))
    return sorted(out)


def _preserve_failed_capture(root: str, *, staging_root: str, run_id: str,
                             capture_date: str, exc: BaseException) -> dict:
    """Move a failed attempt's staged evidence somewhere stable and say why.

    `FAILED_CAPTURE_PRESERVATION` is the contract, and it is not this module's
    opinion:

        the run-scoped price leaf is preserved
        the run-scoped aggregate manifest is preserved
        the failure evidence is preserved
        no lineage directory is created
        no capture record is written
        the attempt id is never reused or cleared

    Each clause is checked against the preserved tree and the answer recorded —
    including when it is False, which is the honest report for a failure that
    happened before the leaves existed. Nothing here deletes anything, and a
    preservation that itself fails leaves the staging tree exactly where it is.
    """
    staging_root = os.path.abspath(staging_root)
    destination = os.path.join(staging_root, PRESERVED_FAILURE_DIRNAME, run_id)
    notes = []
    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.lexists(destination):
            raise FloorCapturePreparationError(
                "preserved evidence for %s already exists at %s; an attempt id "
                "is never reused, so this is a reused id rather than a retry"
                % (run_id, destination))
        shutil.move(root, destination)
        relocated = True
    except Exception as move_error:            # noqa: BLE001 — never mask `exc`
        destination, relocated = os.path.abspath(root), False
        notes.append("could not relocate the staged tree (%s: %s); it is left "
                     "in place at %s" % (type(move_error).__name__, move_error,
                                         destination))

    present = _tree(destination) if os.path.isdir(destination) else []
    price_leaf = [p for p in present
                  if os.path.basename(p) == LEAF_FILENAME % "prices"]
    aggregate = [p for p in present
                 if os.path.basename(p) == AGGREGATE_FILENAME]
    capture_records = [p for p in present
                       if os.path.basename(p) == CAPTURE_FILENAME]
    lineage_marker = "/".join(LINEAGE_ROOT_PARTS)
    lineage_dirs = [p for p in present if lineage_marker in p]

    checks = {
        FAILED_CAPTURE_PRESERVATION[0]: bool(price_leaf),
        FAILED_CAPTURE_PRESERVATION[1]: bool(aggregate),
        FAILED_CAPTURE_PRESERVATION[2]: True,      # this file, written below
        FAILED_CAPTURE_PRESERVATION[3]: not lineage_dirs,
        FAILED_CAPTURE_PRESERVATION[4]: not capture_records,
        FAILED_CAPTURE_PRESERVATION[5]: relocated,
    }
    evidence = {
        "schema": FAILURE_EVIDENCE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "capture_authority": CAPTURE_AUTHORITY,
        "evidence_class": EVIDENCE_CLASS,
        "formal_publication_performed": False,
        "run_id": run_id,
        "capture_date": capture_date,
        "failed_at": _taipei_now().isoformat(timespec="seconds"),
        "error_type": type(exc).__name__,
        "error_module": type(exc).__module__,
        "error_message": str(exc),
        "traceback": "".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__)),
        "preserved_directory": destination.replace("\\", "/"),
        "staged_tree_relocated": relocated,
        "preserved_files": present,
        "preservation_contract": list(FAILED_CAPTURE_PRESERVATION),
        "preservation_contract_satisfied": checks,
        "price_leaf_paths": price_leaf,
        "aggregate_manifest_paths": aggregate,
        "notes": notes,
    }
    evidence_path = os.path.join(destination, FAILURE_EVIDENCE_FILENAME)
    def _write_evidence(temporary: str) -> None:
        # P2-11. Byte-for-byte the write this has always performed. The mode
        # was "x" -- exclusive create on the FINAL path, bytes afterwards -- so
        # an interruption froze a zero-byte evidence file that could never be
        # rewritten, and FAILED_CAPTURE_PRESERVATION would then be recorded as
        # satisfied by an empty file.
        with open(temporary, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())

    try:
        os.makedirs(destination, exist_ok=True)
        publish_exclusively(evidence_path, _write_evidence)
    except Exception as write_error:           # noqa: BLE001 — never mask `exc`
        evidence["preservation_contract_satisfied"][
            FAILED_CAPTURE_PRESERVATION[2]] = False
        evidence["notes"].append(
            "could not write the failure evidence file (%s: %s)"
            % (type(write_error).__name__, write_error))
        evidence_path = ""
    else:
        evidence["preserved_files"] = _tree(destination)

    record = dict(evidence)
    record["failure_evidence_path"] = evidence_path.replace("\\", "/")
    record["preservation_complete"] = all(
        record["preservation_contract_satisfied"].values())
    return record


def _report_preserved(exc: BaseException, preserved: dict) -> None:
    """Attach the preserved location to the exception AND to stderr.

    The original exception is re-raised unchanged — a floor/session mismatch
    must keep being a `LineageCaptureError` — so the location travels as a note
    (visible in the traceback) and as an attribute (readable by a caller).
    """
    unmet = sorted(k for k, ok in
                   preserved["preservation_contract_satisfied"].items()
                   if not ok)
    message = (
        "floor-capture attempt %s FAILED. Staged evidence PRESERVED at:\n"
        "    %s\n  failure evidence: %s\n  preserved files:  %s\n"
        "  FAILED_CAPTURE_PRESERVATION unmet: %s"
        % (preserved["run_id"], preserved["preserved_directory"],
           preserved["failure_evidence_path"] or "<not written>",
           len(preserved["preserved_files"]), unmet or "none"))
    try:
        setattr(exc, "preserved_evidence", preserved)
    except Exception:                          # noqa: BLE001
        pass
    if hasattr(exc, "add_note"):
        exc.add_note(message)
    print(message, file=sys.stderr)


def prepare_floor_capture(*, prior_attempt_id: str, capture_date: str,
                          calendar_source: str, prices_2019_source: str,
                          prices_pre_2019_source: str, final_run_dir: str,
                          staging_root: str, repo_root: str = REPO) -> dict:
    """Run the full source/read/floor path without publishing formal evidence."""
    try:
        capture_date = dt.date.fromisoformat(capture_date).isoformat()
    except ValueError as exc:
        raise FloorCapturePreparationError(
            "capture_date must be a real ISO date") from exc
    today = _taipei_today().isoformat()
    if capture_date != today:
        raise FloorCapturePreparationError(
            "capture_date %s is not today's actual Asia/Taipei "
            "source-observation date %s" % (capture_date, today))
    run_id = next_attempt_run_id(prior_attempt_id,
                                 capture_date=capture_date)
    before_repo = _repo_state(repo_root)
    observed_at = _taipei_now().isoformat(timespec="seconds")
    os.makedirs(staging_root, exist_ok=True)
    root = tempfile.mkdtemp(prefix=run_id + "-", dir=staging_root)
    inputs = os.path.join(root, "inputs")
    validation = os.path.join(root, "validation")
    os.makedirs(validation)
    try:
        cal_stage = os.path.join(inputs, "calendar")
        p19_stage = os.path.join(inputs, "prices_2019")
        pre_stage = os.path.join(inputs, "prices_pre2019")
        snapshots = {
            "calendar": snapshot_directory(
                calendar_source, cal_stage, extensions=(".parquet",),
                declared_subdirectories=build_flat_leaves.FLAT_FAMILIES[
                    "calendar"].get("declared_subdirectories", ())),
            "prices_2019": snapshot_directory(
                prices_2019_source, p19_stage,
                extensions=build_prices_leaf.ENUMERATED_EXTENSIONS),
            "prices_pre2019": snapshot_directory(
                prices_pre_2019_source, pre_stage, extensions=(".parquet",)),
        }
        validation_leaves = {
            "calendar": build_flat_leaves.build(
                "calendar", run_id, capture_date, landing_dir=cal_stage,
                observed_at=observed_at),
            "prices": build_prices_leaf.build(
                run_id, capture_date, landing_dir=p19_stage,
                pre_2019_dir=pre_stage, observed_at=observed_at),
        }
        for leaf in validation_leaves.values():
            write_leaf(validation, leaf)
        aggregate = assemble_aggregate(
            run_dir=validation, run_id=run_id, as_of=capture_date,
            purpose=PURPOSE_CAPTURE, capture_authority=CAPTURE_AUTHORITY,
            required=FLOOR_CAPTURE_REQUIRED_DATASETS)
        aggregate_payload, aggregate_raw = write_aggregate(validation, aggregate)
        verify_aggregate(validation)

        sessions = sessions_through(read_calendar(validation), capture_date)
        if not sessions:
            raise FloorCapturePreparationError(
                "calendar has no session through capture date")
        prices = read_prices(validation, "1900-01-01", capture_date)
        assert_prices_are_on_calendar(prices["date"], sessions)
        floor = str(prices["date"].min())
        assert_floor_is_a_trading_session(floor, sessions)
        price_leaf = load_leaf(os.path.join(
            validation, LEAF_FILENAME % "prices"))
        legs = derive_leg_summaries(
            price_leaf, prices,
            rows_dropped_by_quarantine=_quarantined_rows(pre_stage))

        final_inputs = os.path.join(os.path.abspath(final_run_dir), "inputs")
        declared_calendar = os.path.join(final_inputs, "calendar")
        declared_prices_2019 = os.path.join(final_inputs, "prices_2019")
        declared_prices_pre = os.path.join(final_inputs, "prices_pre2019")
        planned_leaves = {
            "calendar": build_flat_leaves.build(
                "calendar", run_id, capture_date, landing_dir=cal_stage,
                declared_landing_dir=declared_calendar,
                observed_at=observed_at),
            "prices": build_prices_leaf.build(
                run_id, capture_date, landing_dir=p19_stage,
                pre_2019_dir=pre_stage,
                declared_landing_dir=declared_prices_2019,
                declared_pre_2019_dir=declared_prices_pre,
                observed_at=observed_at),
        }
        # D2. The guard that used to stand here asked whether the private
        # staging path still APPEARED in the planned JSON — a string test that
        # the substitution passes exactly by being complete, so it could not
        # fail for the reason it existed. It is replaced, not supplemented: the
        # declaration is now reconciled against the bytes that were read.
        declaration_provenance = {
            "calendar": assert_declaration_reconciles(
                dataset="calendar", read_leaf=validation_leaves["calendar"],
                planned_leaf=planned_leaves["calendar"],
                requested_declarations=(declared_calendar,),
                snapshots=(snapshots["calendar"],), repo_root=repo_root),
            "prices": assert_declaration_reconciles(
                dataset="prices", read_leaf=validation_leaves["prices"],
                planned_leaf=planned_leaves["prices"],
                requested_declarations=(declared_prices_2019,
                                        declared_prices_pre),
                snapshots=(snapshots["prices_2019"],
                           snapshots["prices_pre2019"]),
                repo_root=repo_root),
        }
        planned_dir = os.path.join(root, "planned")
        os.makedirs(planned_dir)
        planned_leaf_receipts = {
            name: write_leaf(planned_dir, leaf)
            for name, leaf in planned_leaves.items()
        }
        planned_aggregate = assemble_aggregate(
            run_dir=planned_dir, run_id=run_id, as_of=capture_date,
            purpose=PURPOSE_CAPTURE, capture_authority=CAPTURE_AUTHORITY,
            required=FLOOR_CAPTURE_REQUIRED_DATASETS)
        planned_aggregate_payload, _ = write_aggregate(
            planned_dir, planned_aggregate)
        after_repo = _repo_state(repo_root)
        if after_repo != before_repo:
            raise FloorCapturePreparationError(
                "repository identity changed during capture preparation")
        freeze_path = os.path.join(
            repo_root, "research", "b0_registry", "master_prereg_freeze.json")
        with open(freeze_path, encoding="utf-8") as fh:
            freeze = json.load(fh)
        basis_preview = {
            "contract_version": CONTRACT_VERSION,
            "capture_authority": CAPTURE_AUTHORITY,
            "capture_run_id": run_id,
            "as_of": capture_date,
            "lineage_price_floor": floor,
            "price_leaf_payload_sha256": planned_leaf_receipts["prices"][
                "payload_sha256"],
            "aggregate_manifest_payload_sha256": planned_aggregate_payload,
            "leg_summaries": list(legs),
            "master_version": str(freeze["version"]),
            "spec_sha256": str(freeze["spec_sha256"]),
            "master_prereg_freeze_sha256": file_sha256(freeze_path),
            "floor_capture_code_closure_sha256":
                floor_capture_code_closure_sha256(repo_root),
            "repo_commit_sha": before_repo["commit_sha"],
        }
        result = {
            "evidence_class": EVIDENCE_CLASS,
            "formal_publication_performed": False,
            "run_id": run_id,
            "capture_date": capture_date,
            "capture_date_timezone": str(CAPTURE_TIMEZONE),
            "decision_date": None,
            "execution_date": None,
            "lineage_price_floor": floor,
            "diagnostic_expected_floor": DIAGNOSTIC_EXPECTED_FLOOR,
            "expected_floor_matched": floor == DIAGNOSTIC_EXPECTED_FLOOR,
            "source_max_session": max(sessions),
            "temporal_contract_version": TEMPORAL_SNAPSHOT_CONTRACT_VERSION,
            "snapshots": snapshots,
            "planned_leaf_payload_sha256": {
                name: receipt["payload_sha256"]
                for name, receipt in planned_leaf_receipts.items()},
            "planned_aggregate_payload_sha256": planned_aggregate_payload,
            "declaration_provenance": declaration_provenance,
            # D3. These two used to sit here as `validation_aggregate_*_sha256`,
            # beside the reproducible planned digests and indistinguishable from
            # them — and were quoted in a dry-run report as if they were
            # evidence. They are kept (the run did produce them) but they are
            # now unreachable without reading the notice that says what they
            # are: a name a consumer cannot mistake, inside a record that states
            # in band that they are not reproducible and not admissible.
            "non_reproducible_validation_digests": dict(
                NON_REPRODUCIBLE_VALIDATION_NOTICE,
                compare_instead=list(
                    NON_REPRODUCIBLE_VALIDATION_NOTICE["compare_instead"]),
                aggregate_payload_sha256_non_reproducible=aggregate_payload,
                aggregate_raw_sha256_non_reproducible=aggregate_raw),
            "basis_preview": basis_preview,
            "repo_state": before_repo,
            "required_datasets_provenance": RATIFIED_INVENTORY_AUTHORITY,
        }
    except BaseException as exc:
        # D1. The `finally: shutil.rmtree(...)` that used to close this block
        # deleted the staged leaves, the aggregate manifest and the snapshot
        # inventory on FAILURE as well as on success — including the one failure
        # this whole path exists to detect, `assert_floor_is_a_trading_session`,
        # whose evidence is then a stack trace and nothing else.
        try:
            _report_preserved(
                exc, _preserve_failed_capture(
                    root, staging_root=staging_root, run_id=run_id,
                    capture_date=capture_date, exc=exc))
        except Exception as preservation_error:   # noqa: BLE001
            # Preserving the evidence may never replace the failure it exists to
            # preserve. Worst case the staged tree is left exactly where it is —
            # which is still more than the old `finally` left behind.
            if hasattr(exc, "add_note"):
                exc.add_note(
                    "preservation itself failed (%s: %s); the staged tree is "
                    "left in place at %s" % (type(preservation_error).__name__,
                                             preservation_error, root))
        raise
    # Success, and only success, cleans up.
    shutil.rmtree(root, ignore_errors=True)
    return result


__all__ = ["CAPTURE_TIMEZONE", "DECLARATION_RECONCILIATION",
           "EVIDENCE_CLASS", "FAILURE_EVIDENCE_FILENAME",
           "FloorCapturePreparationError", "NON_REPRODUCIBLE_VALIDATION_NOTICE",
           "PRESERVED_FAILURE_DIRNAME", "assert_declaration_reconciles",
           "prepare_floor_capture"]
