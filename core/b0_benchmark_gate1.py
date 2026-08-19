# -*- coding: utf-8 -*-
"""B0.2 · R8 — the pre-replay invariant for V-4 gate 1's inputs.

Gate 1 is `net cumulative wealth > 0050 buy-and-hold` (§9.4). The B0.1
diagnostic report established that NOTHING which could produce the right-hand
side is inside the sealed input closure: no benchmark artefact appears in the
baseline seal's `datasets` or `derived` lists, and `0050` has no row in
`data/b0/price_panel.parquet` (ETFs are not in the stock-selection universe, and
§R7 forbids adding one there merely to make a gate work).

That is a REPLAY-TIME failure that would be discovered at EVALUATION time — the
worst possible ordering, because by then 141 periods have run and the temptation
to reach for an unsealed file is at its strongest. This module moves the failure
to before the first period.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It contains no benchmark semantics. Not a date, not a notional, not a sizing
rule, not a capacity rule, not a terminal-treatment rule, not a missing-session
rule. Those are exactly the six things the frozen master does not determine, and
they are registered as the M-3 item `benchmark_construction_semantics`; writing
any of them here would be the implementer picking a free parameter that sits
directly on the primary gate. This module only asks whether the inputs a gate-1
computation would need are PRESENT and SEAL-BOUND, which is a provenance
question and answerable without deciding a single economic convention.

So while the M-3 item is open this check fails for TWO independent reasons, and
both should be reported: the semantics are unruled, and the artefact does not
exist. Closing one does not close the other.
"""
from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The canonical benchmark artefact R7 requires: a source/panel independent of the
# stock-selection price universe. Named here so that "is it bound?" is a lookup
# rather than a search, NOT because this module decides how to build it.
BENCHMARK_PANEL = "data/b0/benchmark_0050_panel.parquet"

# What a seal must carry for gate 1 to be reproducible from sealed inputs alone.
GATE1_REQUIRED_BINDINGS: tuple[str, ...] = (
    "benchmark_panel_content_sha256",
    "benchmark_panel_schema_sha256",
    "benchmark_source_contract",
    "benchmark_derivation_receipt",
    "benchmark_upstream_sha256",
    "benchmark_date_coverage",
)

GATE1_SEMANTICS_ITEM = "benchmark_construction_semantics"


class Gate1InputsNotSealed(RuntimeError):
    """R8: a B0.2 replay whose gate 1 could not be reproduced from its seal."""


def _seal_binds_benchmark(seal: dict) -> dict:
    """Which required bindings a seal manifest actually carries."""
    present, missing = [], []
    names = set()
    for group in ("datasets", "derived"):
        for row in seal.get(group, ()) or ():
            if isinstance(row, dict) and row.get("name"):
                names.add(str(row["name"]))
    benchmark_rows = sorted(n for n in names
                            if "benchmark" in n.lower() or "0050" in n)
    declared = seal.get("benchmark") if isinstance(seal.get("benchmark"), dict) else {}
    for key in GATE1_REQUIRED_BINDINGS:
        (present if declared.get(key) else missing).append(key)
    return {"benchmark_rows_in_manifest": benchmark_rows,
            "bindings_present": present, "bindings_missing": missing}


def gate1_input_status(seal: dict | None = None) -> dict:
    """Measured, not asserted. Safe to call for reporting at any time."""
    from core.b0_finalization_items import open_keys

    panel = os.path.join(REPO_ROOT, BENCHMARK_PANEL)
    status = {
        "panel_path": BENCHMARK_PANEL,
        "panel_present": os.path.exists(panel),
        "semantics_item": GATE1_SEMANTICS_ITEM,
        "semantics_ruled": GATE1_SEMANTICS_ITEM not in open_keys(),
        "seal_provided": seal is not None,
    }
    status.update(_seal_binds_benchmark(seal or {}))
    status["gate1_reproducible_from_sealed_inputs"] = bool(
        status["panel_present"] and status["semantics_ruled"]
        and not status["bindings_missing"] and status["benchmark_rows_in_manifest"])
    return status


def assert_gate1_inputs_sealed(seal: dict | None = None) -> dict:
    """R8 · benchmark gate 1 inputs complete and seal-bound. Pre-replay.

    Called before a B0.2 141-period replay may start. It refuses in the only
    place where refusing is cheap.
    """
    status = gate1_input_status(seal)
    if status["gate1_reproducible_from_sealed_inputs"]:
        return status
    reasons = []
    if not status["semantics_ruled"]:
        reasons.append(
            "M-3 %s is still open: the frozen master does not determine the "
            "benchmark's initial date, notional, share sizing, capacity "
            "treatment, terminal valuation or missing-session handling, and an "
            "implementer must not pick them" % GATE1_SEMANTICS_ITEM)
    if not status["panel_present"]:
        reasons.append(
            "the canonical benchmark panel %s does not exist" % BENCHMARK_PANEL)
    if not status["benchmark_rows_in_manifest"]:
        reasons.append(
            "no benchmark dataset or derived artefact appears in the seal manifest")
    if status["bindings_missing"]:
        reasons.append("the seal carries none of: %s"
                       % ", ".join(status["bindings_missing"]))
    raise Gate1InputsNotSealed(
        "R8: V-4 gate 1 (net cumulative wealth > 0050 buy-and-hold) could not "
        "be reproduced from sealed inputs, so a B0.2 replay must not start. "
        + "; ".join(reasons)
        + ". A replay that discovers this at evaluation time discovers it after "
          "141 periods have run, which is when reaching for an unsealed file is "
          "most tempting.")
