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
    RunDirectoryExists, assert_legacy_run_unmutated, create_run_dir,
)
from core.b0_master_prereg import (                                # noqa: E402
    effective_observation_count, read_registry, write_provenance_json,
)

SEAL_ARCHIVE = os.path.join(REPO, "artifacts", "baseline_seal", "seals")
FREEZE = os.path.join(REPO, "research", "b0_registry", "master_prereg_freeze.json")
MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")


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

    freeze = json.load(open(FREEZE, encoding="utf-8"))
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    composed = hashlib.sha256("".join(
        "%s:%s\n" % (m["decision_month"], m["market_state_sha256"])
        for m in manifest).encode()).hexdigest()

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
        "openings_permitted": body["l2_opening_protocol"]["openings_permitted"],
        "attempted_openings_before_this": len(read_registry()),
        "effective_observations_before_this": effective_observation_count(),
        "window": [manifest[0]["decision_date"], manifest[-1]["decision_date"]],
        "periods": len(manifest),
    }

    if a.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=1))
        print("\n--dry-run: nothing created")
        return 0

    # 4 · claim the directory FIRST. R3: exclusive, and before any byte.
    try:
        run_dir = create_run_dir(run_id)
    except RunDirectoryExists as exc:
        raise SystemExit("abort: %s" % exc)

    write_provenance_json(os.path.join(run_dir, "opening_record.json"), record)
    # The opening registry entry is written by the RUNNER at termination, with
    # the run's real outcome. It is deliberately not written here: M-2 outcomes
    # are terminal results, and seeding one with a placeholder would put a
    # reconstruction-block verdict on record for a run that has not started.

    print("run_id        : %s" % run_id)
    print("run directory : %s" % os.path.relpath(run_dir, REPO))
    print("baseline seal : %s" % a.seal)
    print("opened_at     : %s" % opened_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
