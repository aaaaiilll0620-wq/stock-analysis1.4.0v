# -*- coding: utf-8 -*-
"""W6a · the financials leaf producer for an L3 run.

Emits `source_manifest_financials.json` into a run directory: the concrete files
that will feed the financials side of one L3 decision, with their bytes, their
export vintage, and what each one owns and yields.

⚠ THIS DOES NOT IMPORT L2's `SOURCE_OWNERSHIP`, and must not be changed to.
The first L3 declaration below was TRANSCRIBED from it once, by hand, on
2026-08-26. After transcription the two are independent: L2 keeps its constant
because its source set is finished, and this manifest takes its identity from
concrete file hashes, its own payload hash, and the run receipt that binds it.
Importing the constant would recreate the coupling the ruling forbids and would
make an L3 run's inputs move whenever an L2 file was edited.

Ordinary monthly re-export is a NEW RUN MANIFEST, not an edit here:

    a new file taking over a NEW period      -> new run manifest, no code change
    a new file taking over a DECLARED period -> a source-semantic change, needs a
                                                contract version bump and its own
                                                adjudication

    python research/b0_materializer/build_financials_leaf.py <run_dir> <run_id> <as_of>
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    ManifestError, build_leaf, write_leaf,
)

DATASET = "financials"

# The financials landing surface is a flat directory of workbooks and exports.
LANDING_DIRECTORY = os.path.join(
    "tej_exports", "DataExport0806", "財報2004~202606")
ACCEPTED_EXTENSIONS = (".xlsx", ".csv")

# --- the transcribed first declaration ----------------------------------------
#
# Transcribed 2026-08-26 from L2's constant. `export_vintage` is the date the
# export was produced (from the exporter, not guessed from the filename pattern
# — the filename merely happens to agree); `observed_at` is filled in at write
# time, because when WE saw a file is our fact, not the exporter's.
#
# Measured basis for the ownership split, so a later reader does not have to
# re-derive it: on period 202606 the workbook carries 318 securities and the csv
# 1,879 (a strict superset, only-xlsx = 0), and on the 318 they share, 16 of 57
# columns differ — 加權平均股數 on 201 rows by up to 106,846 shares, 每股盈餘 on
# 15 rows by up to 0.16. The later export carries the more finalised numbers, so
# it owns the period and the workbook yields it.

DECLARATION: tuple = (
    {
        "locator": "20260806090633.xlsx",
        "format": "xlsx",
        "export_vintage": "2026-08-06",
        "source_family": "TEJ",
        "authority": "AUTHORITATIVE",
        "disposition": "consumed",
        "owns": "<= 202603",
        "yields": ["202606"],
    },
    {
        "locator": "2026 0826 2385家.csv",
        # A csv by extension only: BOM ff fe, zero commas, tab-separated.
        "format": "csv:utf-16:tab",
        "export_vintage": "2026-08-26",
        "source_family": "TEJ",
        "authority": "AUTHORITATIVE",
        "disposition": "consumed",
        "owns": ["202606"],
        "yields": [],
    },
)


def build(run_id: str, as_of: str, landing_dir: str = "") -> dict:
    landing = landing_dir or os.path.join(REPO, LANDING_DIRECTORY)
    observed_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    entries = []
    for decl in DECLARATION:
        path = os.path.join(landing, decl["locator"])
        if not os.path.isfile(path):
            raise ManifestError(
                "abort: declared source %s is not present under %s. A manifest "
                "may only declare files that exist at the moment it is written."
                % (decl["locator"], landing))
        entries.append({**decl,
                        "raw_sha256": file_sha256(path),
                        "observed_at": observed_at})

    return build_leaf(
        dataset=DATASET, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=LANDING_DIRECTORY.replace("\\", "/"),
        accepted_extensions=ACCEPTED_EXTENSIONS)


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    run_dir, run_id, as_of = argv[1], argv[2], argv[3]
    record = write_leaf(run_dir, build(run_id, as_of))
    print("dataset        %s" % record["dataset"])
    print("path           %s" % record["path"])
    print("raw_sha256     %s" % record["raw_sha256"])
    print("payload_sha256 %s" % record["payload_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
