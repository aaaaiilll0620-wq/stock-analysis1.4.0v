# -*- coding: utf-8 -*-
"""Build the CRLF→LF provenance migration ledger (M-3 ruling, 2026-08-18).

During Repo & Provenance Finalization Closure the repository gained a
`.gitattributes` that fixes LF as the canonical byte representation. 150 tracked
files had drifted to CRLF in the working tree; restoring them changed their RAW
BYTES, and raw bytes are what `sha256` sees.

Nine hashes recorded inside three Frozen-A-era research provenance records were
computed over the CRLF byte-form and therefore no longer describe the file on
disk. The ruling is explicit: **do not silently overwrite historical hashes.**
Both values are preserved, and the transformation between them is stated and
mechanically verified rather than asserted.

For every case this script CHECKS, and refuses to emit the ledger otherwise:

    sha256(current file bytes)                 == current_canonical_lf_sha256
    sha256(current bytes with LF -> CRLF)      == historical_crlf_sha256

If both hold, the difference between the two recorded values is line endings and
nothing else — which is what `substantive_change: false` claims. If either fails
the file changed for some other reason and the claim would be false, so the
script aborts instead of writing a ledger that says otherwise.

    python research/b0_registry/build_lf_migration_ledger.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "lf_migration_ledger.json")

TRANSFORMATION = "CRLF_TO_LF_ONLY"

# (provenance record that carries the stale hash, path it describes,
#  the historical CRLF-byte value that record still states)
CASES: tuple[tuple[str, str, str], ...] = (
    ("research/p0_r1_research_production_identity/preflight.json",
     "core/score_store.py",
     "58de00f76481ea1ce13fd6fa2f946ac0b2f3dae641e1d80f9b56319345bc7874"),
    ("research/p0_r1_research_production_identity/preflight.json",
     "app.py",
     "2eb834c3f92c2bf951835aeadc86b985db76a6072216f09636d9e499874a2f6b"),
    ("research/p0_r1_research_production_identity/preflight.json",
     "beat_0050/strategies/high52_lab.py",
     "09fbe6efa34e5c6e8481adafddad58d073970227c7804c8a269e6ed29b0f72f8"),
    ("research/p0_r1_research_production_identity/preflight.json",
     "scripts/lab_paths.py",
     "8cb132fc436d26f41c579932f636ecfa947a27f964a728f01a8d5e453528d0b0"),
    ("beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json",
     "scripts/gate1_delta_ic_maxt.py",
     "9bcb71ff18ac09f49029023195d4e3ae53cfcd9c061b7c51a7273fce05791930"),
    ("beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json",
     "scripts/build_gate1_provenance_overlay.py",
     "49dd87117270cc97b283b26eab17a947fe03adb370e5a38563e4f624fd1aabd9"),
    ("beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json",
     "beat_0050/results/gate1/gate1_preflight.json",
     "8429aeb673254b7fda64bb088b5aac5e10feaf4d21c8d70c6cb55dc79320c4af"),
    # This record was relocated to the gitignored artefact root by the same
    # ruling; the path below is where it lived when the drift was measured.
    ("beat_0050/results/gate2/gate2_preflight.json",
     "beat_0050/results/gate1/GATE1_EXECUTION_MANIFEST.json",
     "4ed3b2c95e5856bf3c0a86bc7445570f439f3f5c8a1d7a94953ed71e61ef32be"),
    ("beat_0050/results/gate2/gate2_preflight.json",
     "beat_0050/results/gate1/GATE1_PROVENANCE_OVERLAY.json",
     "7344424dd8b5f034d1cde1f236840c2c824aaadfed6944c42eb2e617b98d09bb"),
)

# Records that still print a historical value as if it were current. Named here
# so "which documents need an amendment" is a query, not a memory.
RECORDS_REQUIRING_AUDIT_AMENDMENT: tuple[str, ...] = tuple(sorted({c[0] for c in CASES}))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build() -> dict:
    entries, failures = [], []
    for record, path, historical in CASES:
        abs_path = os.path.join(REPO_ROOT, path)
        if not os.path.isfile(abs_path):
            failures.append(f"{path}: file is missing; cannot verify the migration claim")
            continue
        lf = open(abs_path, "rb").read()
        if b"\r\n" in lf:
            failures.append(f"{path}: still contains CRLF; the repository is not canonical")
            continue
        crlf = lf.replace(b"\n", b"\r\n")
        current = _sha(lf)
        if _sha(crlf) != historical:
            failures.append(
                f"{path}: recorded historical hash {historical[:16]}… is NOT the CRLF "
                f"form of the current file ({_sha(crlf)[:16]}…). The difference is "
                f"therefore not line endings alone, and substantive_change=false "
                f"would be a false claim.")
            continue
        entries.append({
            "record": record,
            "path": path,
            "historical_crlf_sha256": historical,
            "current_canonical_lf_sha256": current,
            "transformation": TRANSFORMATION,
            "substantive_change": False,
            "verified": "sha256(current bytes with LF->CRLF) == historical_crlf_sha256",
        })
    if failures:
        for f in failures:
            print("FAIL:", f, file=sys.stderr)
        raise SystemExit(
            f"aborting: {len(failures)} case(s) could not be verified as "
            f"line-ending-only. A ledger asserting substantive_change=false for "
            f"them would be untrue.")
    return {
        "ledger": "crlf_to_lf_provenance_migration",
        "ruling": "M-3 ruling 2026-08-18; master preregistration v1.14",
        "why": ("`.gitattributes` fixed LF as the canonical repository byte "
                "representation. These records hash files by raw bytes and were "
                "written against the CRLF form. Historical values are preserved as "
                "historical CRLF-byte fingerprints, not overwritten."),
        "blocks_b0_baseline_seal": False,
        "blocks_rationale": ("None of these paths is a consumed B0 input or a "
                             "normative implementation module. B0 identity was "
                             "re-verified after normalization: spec document, all 23 "
                             "normative modules, all 10 derived artefacts and all 14 "
                             "upstream zips still match the freeze registry."),
        "records_requiring_audit_amendment": list(RECORDS_REQUIRING_AUDIT_AMENDMENT),
        "entry_count": len(entries),
        "entries": entries,
    }


def main() -> None:
    ledger = build()
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {OUT}")
    print(f"entries verified: {ledger['entry_count']}")
    for e in ledger["entries"]:
        print(f"  {e['historical_crlf_sha256'][:12]}… -> "
              f"{e['current_canonical_lf_sha256'][:12]}…  {e['path']}")


if __name__ == "__main__":
    main()
