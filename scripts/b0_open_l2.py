# -*- coding: utf-8 -*-
"""Create exactly one L2 opening. C-58/R2/R3.

The first opening record was written inline in a session, which is how it came
to live at `artifacts/l2_run/opening_record.json` — the path a second run would
have overwritten. Opening is now a script, so the run directory is claimed
exclusively before any byte is written and the run_id is bound into every
artefact path.

This script does NOT authorise anything. It refuses to run without an explicit
authorization reference, and it binds the Baseline Seal hash the caller names
against the seal actually archived. The decision to open L2 is the user's; this
only makes the recording of it reproducible.

    B0_MATERIALIZE_LINEAGE=<lineage> python scripts/b0_open_l2.py \
        --seal <sha256> --authorization "<reference>" --lineage <lineage>

`--lineage` confirms; the environment variable governs. On WSL driving a Windows
interpreter the variable does not cross unless `WSLENV` names it too.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core.b0_l2_run_layout import (                                # noqa: E402
    OpeningClaimExists, RunDirectoryExists, assert_legacy_run_unmutated,
    composed_market_state_sha256, create_opening_claim, create_run_dir,
    lineage_attempted_opening_count, read_opening_claim, sha256_of,
)
from core.b0_master_prereg import (                                # noqa: E402
    L2ReopeningUnreachable, active_lineage, assert_declared_lineage,
    assert_l2_reopening_reachable,
    effective_observation_count, lineage_freeze_path,
    lineage_market_state_manifest, lineage_period1_receipt_path,
    lineage_registry_path, lineage_seal_archive_root, write_provenance_json,
)

# C-72 / §9.6e-R5. This script IS the opening boundary: it claims the run
# directory and writes the opening claim.
#
# The lineage used to be the constant FROZEN_B0, because every path here was
# B0's. It is now resolved by `active_lineage()` — ONE reader, in the
# specification module, shared with the materializer, the freeze builder and the
# sealer, failing closed on any name that is not registered. Every path below is
# derived from it rather than spelled out, so there is no combination of
# environment and argument that opens B1 against B0's seal archive.
#
# What has NOT changed is the gate. `assert_l2_reopening_reachable(LINEAGE)` is
# still asked here, first, by this entry point. The guard being in
# `assert_reopening_admissible` was not enough: that function is consulted by
# whoever chooses to consult it, and this script did not — it read
# `effective_observation_count()` only to COPY the number into the record. A
# gate the entry point never asks is not a closed gate, and resolving the
# lineage dynamically makes asking it here more load-bearing, not less.
LINEAGE = active_lineage()

SEAL_ARCHIVE = lineage_seal_archive_root(LINEAGE)
FREEZE = lineage_freeze_path(LINEAGE)
MANIFEST = lineage_market_state_manifest(LINEAGE)
PERIOD1_RECEIPT = lineage_period1_receipt_path(LINEAGE)
REGISTRY = lineage_registry_path(LINEAGE)


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=REPO).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal", required=True,
                    help="the Baseline Seal sha256 the opening binds")
    ap.add_argument("--authorization", required=True,
                    help="the explicit user authorization this opening rests on")
    ap.add_argument("--lineage", default="",
                    help="confirm the lineage being opened; this CHECKS the "
                         "resolved lineage, it does not set it")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # Before anything else, including the reachability gate: if the caller
    # stated which lineage they meant, that statement is checked against the
    # environment. A gate asked about the wrong lineage answers correctly and
    # uselessly.
    assert_declared_lineage(a.lineage, LINEAGE)

    if not a.authorization.strip():
        raise SystemExit("abort: an opening requires a named authorization")

    # 0 · C-72 / §9.6e-R5 · may this lineage be opened at all?
    #     BEFORE everything: before the seal is looked up, before HEAD is read,
    #     before --dry-run prints a record that would suggest an opening is
    #     available. --dry-run creates nothing, but it is not exempt: the answer
    #     it would print is wrong.
    try:
        assert_l2_reopening_reachable(LINEAGE)
    except L2ReopeningUnreachable as exc:
        raise SystemExit("abort: %s" % exc)

    # 1 · the seal the caller names must be the one actually archived
    archive = os.path.join(SEAL_ARCHIVE, a.seal + ".json")
    if not os.path.exists(archive):
        raise SystemExit("abort: no archived seal %s" % a.seal)
    body = json.load(open(archive, encoding="utf-8"))
    if body["baseline_seal_sha256"] != a.seal:
        raise SystemExit("abort: %s does not reopen to the identity it claims"
                         % archive)
    if body["l2_opened"] is not False:
        raise SystemExit("abort: seal %s already records l2_opened=%r"
                         % (a.seal, body["l2_opened"]))

    # 2 · the repo must still be the one the seal bound
    head = _git("rev-parse", "HEAD")
    if head != body["commit_sha"]:
        raise SystemExit("abort: HEAD %s is not the sealed commit %s"
                         % (head[:8], body["commit_sha"][:8]))
    if _git("status", "--porcelain"):
        raise SystemExit("abort: working tree is dirty")

    # 3 · the first attempt's provenance must still be intact
    assert_legacy_run_unmutated()

    # 4 · one Baseline Seal, one opening. Checked here for a clear message and
    # again by O_EXCL below, which is the check that actually holds.
    existing = read_opening_claim(a.seal, LINEAGE)
    if existing is not None:
        raise SystemExit(
            "abort: baseline %s was already opened by run %s at %s"
            % (a.seal[:8], existing["run_id"], existing["opened_at"]))

    freeze = json.load(open(FREEZE, encoding="utf-8"))
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    composed = composed_market_state_sha256(MANIFEST)
    period1 = json.load(open(PERIOD1_RECEIPT, encoding="utf-8"))[
        "full_decision_input_sha256"]

    opened_at = datetime.now(timezone.utc).isoformat()
    run_id = "L2-" + hashlib.sha256(
        "|".join([a.seal, freeze["spec_sha256"], head, composed,
                  opened_at]).encode()).hexdigest()[:16]

    record = {
        "run_id": run_id,
        "opened_at_utc": opened_at,
        "baseline_seal_sha256": a.seal,
        "commit_sha": head,
        "spec_sha256": freeze["spec_sha256"],
        "master_version": freeze["version"],
        "market_state_composed_sha256": composed,
        "authorization": a.authorization,
        "period1_full_input_sha256": period1,
        "openings_permitted": body["l2_opening_protocol"]["openings_permitted"],
        "lineage": LINEAGE,
        "attempted_openings_before_this":
            lineage_attempted_opening_count(LINEAGE),
        "effective_observations_before_this":
            effective_observation_count(REGISTRY),
        "window": [manifest[0]["decision_date"], manifest[-1]["decision_date"]],
        "periods": len(manifest),
    }

    if a.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=1))
        print("\n--dry-run: nothing created")
        return 0

    # 5 · claim the directory. R3: exclusive, and before any byte.
    try:
        run_dir = create_run_dir(run_id, LINEAGE)
    except RunDirectoryExists as exc:
        raise SystemExit("abort: %s" % exc)

    # 6 · write the opening record, then pin its hash into the opening claim.
    #     Until step 7 succeeds this is a PRE-OPENING ORPHAN: it counts as
    #     nothing and the runner refuses it.
    record_path = os.path.join(run_dir, "opening_record.json")
    write_provenance_json(record_path, record)
    record_sha, _ = sha256_of(record_path)

    # 7 · THE opening boundary. O_EXCL, so two openers racing on different
    #     run_ids still yield exactly one formal opening.
    try:
        claim_path = create_opening_claim({
            "run_id": run_id,
            "baseline_seal_sha256": a.seal,
            "opening_record_sha256": record_sha,
            "spec_sha256": freeze["spec_sha256"],
            "commit_sha": head,
            "market_state_composed_sha256": composed,
            "period1_full_input_sha256": period1,
            "authorization": a.authorization,
            "opened_at": opened_at,
        }, LINEAGE)
    except OpeningClaimExists as exc:
        raise SystemExit(
            "abort: %s\n"
            "the run directory just created is a PRE-OPENING ORPHAN: it is not "
            "an attempted opening and the runner will refuse it." % exc)

    print("run_id            : %s" % run_id)
    print("run directory     : %s" % os.path.relpath(run_dir, REPO))
    print("opening claim     : %s" % os.path.relpath(claim_path, REPO))
    print("opening record sha: %s" % record_sha)
    print("baseline seal     : %s" % a.seal)
    print("opened_at         : %s" % opened_at)
    print("lineage           : %s" % LINEAGE)
    print("attempted openings: %d" % lineage_attempted_opening_count(LINEAGE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
