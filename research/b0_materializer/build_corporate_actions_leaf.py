# -*- coding: utf-8 -*-
"""W4 · the corporate-actions leaf: an archive set PLUS a leaf dependency.

`corporate_actions_ledger.csv` has two upstreams, and only one of them is a file
in a directory.

    primary    7 x 配股相關*.zip
               (`p0_v1b_stock_dividend/build_corporate_action_ledger.py:37`)

    derived    data/b0/security_status.csv, which is where the holder-side
               reorganization rows come from. B0.4's comment says it outright:
               "the ONLY source in the corpus that establishes the disappearing
               side of a reorganization at all". Those are the rows carrying
               `holder_side_reorganization_exit`, which is what B0.7 terminates
               on at period 67.

So this leaf declares the seven archives directly and BINDS the security_status
leaf by payload hash rather than restating its six archives. Two leaves listing
the same six files would be two places to update and one place to forget; a
hash binding is checked, and the aggregate validator confirms it points at the
security_status leaf OF THE SAME RUN.

⚠ `corporate_action_provenance.json` may NOT be promoted into this: it binds the
seven archives but records ledger hash `f426…`, while the current ledger is
`c838…` (it moved through B0.3 and B0.4). A provenance record that describes a
different ledger cannot vouch for this one.

    python research/b0_materializer/build_corporate_actions_leaf.py <run_dir> <run_id> <as_of>
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    LEAF_FILENAME, ManifestError, SELF_HASH_FIELD, build_leaf, load_leaf,
    write_leaf,
)

DATASET = "corporate_actions"

LANDING_DIRECTORY = os.path.join(
    "tej_exports", "DataExport0806", "配股相關2004-20260817")
EXTENSIONS = (".zip",)

CONSUMED = (
    "配股相關2004-2007.zip", "配股相關2008-2011.zip", "配股相關2012-2013.zip",
    "配股相關2014-2017.zip", "配股相關2018-2021.zip", "配股相關2022-2025.zip",
    "配股相關20260817.zip",
)

LEDGER = os.path.join("data", "b0", "corporate_actions_ledger.csv")
BUILDER = "research/p0_v1b_stock_dividend/build_corporate_action_ledger.py"

DEPENDENCY_POLICY = {
    "rule": "HOLDER_SIDE_ROWS_DEPEND_ON_SECURITY_STATUS",
    "detail": (
        "the reorganization-exit rows are derived from security_status, not "
        "from any 配股相關 archive. The dependency is bound by the "
        "security_status LEAF's payload hash and must resolve within the same "
        "run — a source set assembled from two runs is not a source set."),
}


def _members(path: str) -> list:
    with zipfile.ZipFile(path) as z:
        return [{"name": i.filename, "size": int(i.file_size),
                 "crc32": "%08x" % i.CRC}
                for i in sorted(z.infolist(), key=lambda i: i.filename)]


def build(run_id: str, as_of: str, run_dir: str = "",
          landing_dir: str = "") -> dict:
    landing = landing_dir or os.path.join(REPO, LANDING_DIRECTORY)
    if not os.path.isdir(landing):
        raise ManifestError("abort: 配股相關 export not found: %s" % landing)
    observed_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    present, unknown = [], []
    for name in sorted(os.listdir(landing)):
        p = os.path.join(landing, name)
        if (os.path.isfile(p) and not os.path.islink(p)
                and os.path.splitext(name)[1].lower() in EXTENSIONS):
            present.append(name)
        else:
            unknown.append(name)
    if unknown:
        raise ManifestError(
            "abort: %d undeclared entr(y/ies) in %s:\n%s"
            % (len(unknown), landing, "\n".join("    %s" % n for n in unknown)))

    missing = [z for z in CONSUMED if z not in present]
    if missing:
        raise ManifestError(
            "abort: declared archive(s) %s not present under %s"
            % (missing, landing))

    entries = []
    for name in present:
        p = os.path.join(landing, name)
        consumed = name in CONSUMED
        e = {
            "locator": name,
            "format": "zip",
            "raw_sha256": file_sha256(p),
            "export_vintage": _dt.date.fromtimestamp(
                os.path.getmtime(p)).isoformat(),
            "observed_at": observed_at,
            "source_family": "TEJ",
            "authority": "AUTHORITATIVE",
            "disposition": "consumed" if consumed else "not_consumed",
        }
        if consumed:
            e["members"] = _members(p)
        else:
            e["not_consumed_reason"] = "outside the declared 配股相關 corpus"
        entries.append(e)

    # The derived half. Bound by the security_status LEAF's payload hash, which
    # is why this producer needs the run directory: the dependency is on that
    # run's declared status source, not on whatever status file happens to exist.
    dependency = {}
    if run_dir:
        status_path = os.path.join(run_dir, LEAF_FILENAME % "security_status")
        if not os.path.isfile(status_path):
            raise ManifestError(
                "abort: %s depends on the security_status leaf, which has not "
                "been written for this run yet. Build security_status first — "
                "the dependency is on THIS run's declared status source."
                % DATASET)
        status_leaf = load_leaf(status_path)
        if status_leaf["run_id"] != run_id or status_leaf["as_of"] != as_of:
            raise ManifestError(
                "abort: the security_status leaf in this run directory is for "
                "run %r / as_of %r, not %r / %r."
                % (status_leaf["run_id"], status_leaf["as_of"], run_id, as_of))
        dependency = {
            "security_status": {
                "leaf": os.path.basename(status_path),
                "payload_sha256": status_leaf[SELF_HASH_FIELD],
            }
        }

    ledger_path = os.path.join(REPO, LEDGER)
    return build_leaf(
        dataset=DATASET, run_id=run_id, as_of=as_of, entries=entries,
        landing_directory=LANDING_DIRECTORY.replace("\\", "/"),
        accepted_extensions=EXTENSIONS,
        derived_dependencies=dependency,
        policies={
            "dependency": DEPENDENCY_POLICY,
            "derived_artefact": {
                "rule": "LEDGER_IDENTITY_IS_BOUND_HERE",
                "path": LEDGER.replace("\\", "/"),
                "builder": BUILDER,
                "sha256": (file_sha256(ledger_path)
                           if os.path.isfile(ledger_path) else ""),
                "detail": (
                    "corporate_action_provenance.json is NOT admissible as a "
                    "substitute: it records ledger f426…, which predates B0.3 "
                    "and B0.4; the current ledger is c838…."),
            },
        })


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: build_corporate_actions_leaf.py <run_dir> <run_id> <as_of>")
        return 2
    run_dir, run_id, as_of = argv[1], argv[2], argv[3]
    rec = write_leaf(run_dir, build(run_id, as_of, run_dir=run_dir))
    for k, v in rec.items():
        print("%-15s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
