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

    python scripts/b0_open_l2.py --seal <sha256> --authorization "<reference>"
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
    attempted_opening_count, composed_market_state_sha256, create_opening_claim,
    create_run_dir, read_opening_claim, sha256_of,
)
from core.b0_master_prereg import (                                # noqa: E402
    FROZEN_B0_LINEAGE, L2ReopeningUnreachable, assert_l2_reopening_reachable,
    effective_observation_count, write_provenance_json,
)

# C-72 / §9.6e-R5. This script IS the opening boundary: it claims the run
# directory and writes the opening claim. Every path in it is Frozen B0 — the
# seal archive, the market-state manifest and the period-1 receipt below are all
# that lineage's — so the lineage is a constant here, not an argument.
#
# The guard being in `assert_reopening_admissible` was not enough. That function
# is consulted by whoever chooses to consult it, and this script did not: it
# read `effective_observation_count()` only to COPY the number into the record.
# A gate the entry point never asks is not a closed gate.
LINEAGE = FROZEN_B0_LINEAGE

SEAL_ARCHIVE = os.path.join(REPO, "artifacts", "baseline_seal", "seals")
FREEZE = os.path.join(REPO, "research", "b0_registry", "master_prereg_freeze.json")
MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")
PERIOD1_RECEIPT = os.path.join(
    REPO, "research", "b0_materializer", "period1_full_input_receipt.json")


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
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

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
    existing = read_opening_claim(a.seal)
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
        "attempted_openings_before_this": attempted_opening_count(),
        "effective_observations_before_this": effective_observation_count(),
        "window": [manifest[0]["decision_date"], manifest[-1]["decision_date"]],
        "periods": len(manifest),
    }

    if a.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=1))
        print("\n--dry-run: nothing created")
        return 0

    # 5 · claim the directory. R3: exclusive, and before any byte.
    try:
        run_dir = create_run_dir(run_id)
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
        })
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
    print("attempted openings: %d" % attempted_opening_count())
    return 0


if __name__ == "__main__":
    sys.exit(main())
