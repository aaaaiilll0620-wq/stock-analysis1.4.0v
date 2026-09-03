"""Record the master preregistration freeze: document hash + frozen artefacts.

The document cannot contain its own hash, so the binding lives here. B-21 seals
reference this record; `spec_sha256` in the L2 opening registry is this value.

READ-ONLY with respect to Frozen A. No performance quantity is computed.
"""

import glob
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_provenance import file_sha256          # noqa: E402
from core.b0_master_prereg import (                   # noqa: E402
    FROZEN_B0_LINEAGE, MASTER_PREREG_DOC, MASTER_PREREG_DOCS, active_lineage,
    assert_declared_lineage, lineage_freeze_path, lineage_suffix,
    normative_module_hashes, spec_document_sha256, specified_keys,
)

# --- lineage scoping ----------------------------------------------------------
# Resolved by `core.b0_master_prereg.active_lineage()` - ONE reader for the whole
# build chain (materialize -> freeze -> seal -> open -> run). This script and
# `build_market_side_state.py` must agree about which lineage is being built or
# the registry ends up binding one lineage's hashes under another's name, and
# separate readers that must agree are readers that eventually will not. Set the
# environment variable once; every stage asks the same function.
LINEAGE = active_lineage()
DATA_ROOT = "data/b0" if LINEAGE == FROZEN_B0_LINEAGE else "data/%s" % LINEAGE.lower()

OUT = lineage_freeze_path(LINEAGE)

FROZEN_B0_FREEZE = lineage_freeze_path(FROZEN_B0_LINEAGE)

# `--lineage X` confirms the resolved lineage; it never sets it. See
# `assert_declared_lineage` for why (a WSL shell does not pass the variable to a
# Windows interpreter unless WSLENV names it, and the build then runs as B0).
_DECLARED = None
if "--lineage" in sys.argv:
    _i = sys.argv.index("--lineage")
    _DECLARED = sys.argv[_i + 1] if _i + 1 < len(sys.argv) else ""
    del sys.argv[_i:_i + 2]
assert_declared_lineage(_DECLARED, LINEAGE)



def assert_not_overwriting_frozen_b0(path: str) -> None:
    """A non-B0 lineage may not write Frozen B0's freeze registry.

    Same guard, same reason, as the materializer's: the run that destroys B0's
    identity is not a malicious one, it is an ordinary invocation with the wrong
    environment variable set. Resolved absolute paths, so a relative path, a
    symlink or a `..` cannot walk into it.
    """
    if LINEAGE == FROZEN_B0_LINEAGE:
        return
    if os.path.realpath(path) == os.path.realpath(FROZEN_B0_FREEZE):
        raise SystemExit(
            "REFUSING TO WRITE: lineage %s resolved its freeze registry onto "
            "Frozen B0's (%s). That record is B0's sealed identity."
            % (LINEAGE, FROZEN_B0_FREEZE))

# F0-R3: the list is normative and therefore lives in the specification,
# not in this reporting tool.
from core.b0_master_prereg import NORMATIVE_MODULES   # noqa: E402

_DERIVED_ARTEFACTS_B0 = (
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
    # B0.2 §13.4. Evaluation-only benchmark lineage: never an input to the
    # strategy route, but bound here because gate 1 must be reproducible from
    # the seal alone.
    "data/b0/benchmark_0050_panel.parquet",
    "data/b0/benchmark_0050_distributions.csv",
    "data/b0/benchmark_0050_share_unit_events.parquet",
)

# Re-rooted onto the lineage being frozen. The B0 list stays the single place
# the SET of artefacts is stated; only the root moves, so a lineage cannot
# quietly seal a shorter list than B0 did.
DERIVED_ARTEFACTS = tuple(
    DATA_ROOT + p[len("data/b0"):] for p in _DERIVED_ARTEFACTS_B0)

CA_EXPORT_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "配股相關2004-20260817")
STATUS_EXPORT_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "暫停交易2004-20260818")


def _document_version(doc: str) -> str:
    """B0.7: read the version FROM the document instead of restating it.

    This was a literal, and it had already gone stale: the document said 1.32
    while the freeze record still said 1.31, so a seal would have bound a
    version number that no longer described the specification it hashed. It is
    exactly the F0-R4 failure mode - a sentence that stays true-looking while
    the thing under it moves - and a literal is the one form of it no test can
    catch, because both sides read the same literal.
    """
    import re

    with io.open(doc, encoding="utf-8") as fh:
        head = fh.read(4096)
    # Both colons. B0's document uses the ASCII one and B1's uses the
    # full-width one; a regex that silently knows only about B0's would abort on
    # a perfectly well-formed B1 document and invite someone to "fix" the
    # document to match the tool.
    m = re.search(r"\*\*版本[:：]\*\*\s*([0-9]+\.[0-9]+)", head)
    if not m:
        raise SystemExit(
            "abort: no '**版本:** <n.n>' line in the first 4096 bytes of %s; the "
            "freeze record may not invent a version the document does not state"
            % doc)
    return m.group(1)


def main():
    assert_not_overwriting_frozen_b0(OUT)
    doc_rel = MASTER_PREREG_DOCS[LINEAGE]
    doc = os.path.join(REPO, doc_rel)
    print("lineage     :", LINEAGE)
    print("data root   :", DATA_ROOT)
    record = {
        "lineage": LINEAGE,
        "document": doc_rel,
        "version": _document_version(doc),
        "status": "NORMATIVE_FROZEN",
        "spec_sha256": spec_document_sha256(LINEAGE),
        "spec_bytes": os.path.getsize(doc),
        "normative_modules": normative_module_hashes(),
        "derived_artefacts": {
            p: {"sha256": file_sha256(os.path.join(REPO, p)),
                "bytes": os.path.getsize(os.path.join(REPO, p))}
            for p in DERIVED_ARTEFACTS if os.path.exists(os.path.join(REPO, p))},
        "derived_artefacts_absent": [
            p for p in DERIVED_ARTEFACTS
            if not os.path.exists(os.path.join(REPO, p))],
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
    # An artefact that is simply absent used to vanish from the record without
    # a word, which for a second lineage means sealing a SHORTER list than B0
    # did and calling it the same baseline. Say so, loudly.
    if record["derived_artefacts_absent"]:
        print("ABSENT DERIVED ARTEFACTS (%d):"
              % len(record["derived_artefacts_absent"]))
        for p in record["derived_artefacts_absent"]:
            print("   ", p)
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

