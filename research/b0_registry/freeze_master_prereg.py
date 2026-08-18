"""Record the master preregistration freeze: document hash + frozen artefacts.

The document cannot contain its own hash, so the binding lives here. B-21 seals
reference this record; `spec_sha256` in the L2 opening registry is this value.

READ-ONLY with respect to Frozen A. No performance quantity is computed.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_provenance import file_sha256          # noqa: E402
from core.b0_master_prereg import (                   # noqa: E402
    MASTER_PREREG_DOC, normative_module_hashes, spec_document_sha256,
    specified_keys,
)

OUT = os.path.join(HERE, "master_prereg_freeze.json")

# F0-R3: the list is normative and therefore lives in the specification,
# not in this reporting tool.
from core.b0_master_prereg import NORMATIVE_MODULES   # noqa: E402

DERIVED_ARTEFACTS = (
    "data/b0/corporate_actions_ledger.csv",
    "data/b0/stock_dividend_pit.csv",
    "data/b0/trading_calendar.csv",
    "data/b0/security_status.csv",
    "data/b0/price_universe_churn.csv",
    "data/b0/price_universe_audit.csv",
    "data/b0/price_universe_clusters.csv",
    "data/b0/price_2019plus_new.parquet",
    "data/b0/price_presence.parquet",
    "data/b0/s3b_guard_fixture.csv",
    # Sealed inputs the L2 materializer consumes. Each also carries its own
    # receipt under research/b0_materializer/; the hash is bound here as well so
    # that the freeze record alone is enough to say which bytes were frozen.
    "data/b0/financials_pit.parquet",
    "data/b0/monthly_revenue_pit.parquet",
    "data/b0/valuation_panel.parquet",
    "data/b0/industry_pit.parquet",
    "data/b0/price_panel.parquet",
    "data/b0/bonus_share_panel.parquet",
    # Definition A: the artefact that states all 141 market-side states
    # exist, and carries each one's hash.
    "data/b0/market_state_manifest.json",
)

CA_EXPORT_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "配股相關2004-20260817")
STATUS_EXPORT_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "暫停交易2004-20260818")


def main():
    doc = os.path.join(REPO, MASTER_PREREG_DOC)
    record = {
        "document": MASTER_PREREG_DOC,
        "version": "1.18",
        "status": "NORMATIVE_FROZEN",
        "spec_sha256": spec_document_sha256(),
        "spec_bytes": os.path.getsize(doc),
        "normative_modules": normative_module_hashes(),
        "derived_artefacts": {
            p: {"sha256": file_sha256(os.path.join(REPO, p)),
                "bytes": os.path.getsize(os.path.join(REPO, p))}
            for p in DERIVED_ARTEFACTS if os.path.exists(os.path.join(REPO, p))},
        "upstream_corporate_action_zips": {
            os.path.basename(z): file_sha256(z)
            for z in sorted(glob.glob(os.path.join(CA_EXPORT_DIR, "*.zip")))},
        # O-F (v1.10). The 20260806 vintage this replaces was deleted upstream;
        # its raw hashes were never recorded and are NOT required to reappear.
        "upstream_security_status_zips": {
            os.path.basename(z): file_sha256(z)
            for z in sorted(glob.glob(os.path.join(STATUS_EXPORT_DIR, "*.zip")))},
        "superseded_status_vintage": {
            "folder": "tej_exports/DataExport0806/暫停交易2004-20260806",
            "state": "DELETED_BY_USER_2026-08-18", "raw_sha256": None},
        # C-47: the CRLF->LF migration ledger is part of the frozen record, so
        # "which historical hashes were superseded, and why that was only line
        # endings" is bound rather than remembered.
        "lf_migration_ledger": (
            {"path": "research/b0_registry/lf_migration_ledger.json",
             "sha256": file_sha256(os.path.join(HERE, "lf_migration_ledger.json"))}
            if os.path.exists(os.path.join(HERE, "lf_migration_ledger.json")) else None),
        "specified_keys": list(specified_keys()),
        "open_specification_items": _open_items(),
        "open_finalization_items": _finalization_items(),
        "declaration_conformance": _declaration_conformance(),
        "unmet_blocking_requirements": _unmet(),
        "performance_computed": False,
    }
    # newline="\n" is a provenance control, not a style choice: this record is
    # hashed by raw bytes elsewhere, and letting the platform choose the line
    # ending is exactly how the CRLF drift of 2026-08-18 happened.
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    print("spec_sha256 :", record["spec_sha256"])
    print("spec_bytes  :", record["spec_bytes"])
    print("specified keys:", len(record["specified_keys"]))
    print("derived artefacts:", len(record["derived_artefacts"]))
    print("upstream CA zips:", len(record["upstream_corporate_action_zips"]))
    print("upstream status zips:", len(record["upstream_security_status_zips"]))
    print("UNMET BLOCKING:", record["unmet_blocking_requirements"])
    print("OPEN SPEC ITEMS:", record["open_specification_items"]["total"])
    print("OPEN FINALIZATION ITEMS:", record["open_finalization_items"]["keys"])
    print("DECLARATION CONFORMANCE:", record["declaration_conformance"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


def _open_items():
    """P-1b-U. A frozen specification with open items is not a complete one, so
    the count travels with the freeze record rather than only in a document."""
    from core.b0_open_items import summary
    return summary()


def _finalization_items():
    """F-0. A frozen spec with an undefined hash scope is not a sealable one, so
    the count travels with the freeze record rather than only in a document."""
    from core.b0_finalization_items import summary
    return summary()


def _declaration_conformance():
    """F0-R4. Recorded in the freeze itself so that 'the declarations were
    checked' is a fact about this record and not about somebody's test run."""
    from core.b0_declaration_conformance import summary
    return summary()


def _unmet():
    """Recorded in the freeze itself, so a reader cannot mistake a frozen spec
    for a sealable one."""
    from core.b0_frozen_spec import unmet_blocking_requirements
    return [r.key for r in unmet_blocking_requirements()]


if __name__ == "__main__":
    sys.exit(main())

