# -*- coding: utf-8 -*-
"""The 141-period preflight receipt, DERIVED rather than hand-written.

This receipt existed before this script did: it was assembled inline in a
session, which meant the numbers inside it were correct only for as long as
nobody changed anything. When the Master moved to v1.22 the period-1 full-input
hash moved with it (the input binds the spec identity), and the receipt silently
became stale — the same shape of defect as the sealed-input gap that invalidated
an L2 run, one layer up.

So the receipt is now recomputed from the artefacts it describes. It asserts
rather than restates: every hash here is read back from the manifest and the
upstream receipts at the moment of writing.

Read-only with respect to sealed inputs. It materializes nothing, invokes no
decision layer, and computes no performance quantity.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(REPO, "data", "b0", "market_state_manifest.json")
RECEIPT = os.path.join(HERE, "preflight_141_receipt.json")
P1_RECEIPT = os.path.join(HERE, "period1_full_input_receipt.json")

# The upstream receipts whose sealed-artefact hashes this preflight carries.
SEALED_INPUTS = {
    "price_panel": "price_panel_receipt.json",
    "financials_pit": "financials_pit_receipt.json",
    "monthly_revenue_pit": "monthly_revenue_pit_receipt.json",
    "valuation_panel": "valuation_panel_receipt.json",
    "industry_pit": "industry_pit_receipt.json",
    "bonus_share_panel": "bonus_share_panel_receipt.json",
}

PROVENANCE_NOTE = (
    "v1.22 M-3 l2_reopening_after_run_invalid closure (R1-R5). This ruling "
    "changed NO sealed input content: the composed 141-state hash is unchanged "
    "at 66640a78, verified by a clean single-writer rebuild whose 141 parquet "
    "hashes reproduced the previous ones exactly. The period-1 full-input hash "
    "DID move, because that input binds the Master spec identity and the Master "
    "moved 1.21 -> 1.22; no market-side or portfolio content changed. Any new "
    "authorization must bind the values in this receipt."
)


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _sealed_input_sha(name: str, filename: str) -> str:
    """Read the artefact hash out of the receipt that produced it."""
    receipt = _load(os.path.join(HERE, filename))
    sha = receipt.get("content_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise SystemExit(
            "abort: %s carries no content_sha256; refusing to guess which of its "
            "hashes identifies %s" % (filename, name))
    return sha


def main() -> int:
    manifest = _load(MANIFEST)
    if len(manifest) != 141:
        raise SystemExit("abort: manifest holds %d periods, expected 141"
                         % len(manifest))

    composed = "".join("%s:%s\n" % (m["decision_month"], m["market_state_sha256"])
                       for m in manifest)
    composed_sha = hashlib.sha256(composed.encode()).hexdigest()

    p1 = _load(P1_RECEIPT)
    securities = sorted({m["securities"] for m in manifest})

    receipt = {
        "clause": "141-period preflight, pre-L2",
        "allowed_this_pass": ["materialize market-side state", "hash it",
                              "build period-1 full input", "invariant tests"],
        "denied_this_pass": ["run_decision", "SelectionScore", "Top20",
                             "portfolio", "NAV", "CAGR", "Sharpe", "MDD", "IC",
                             "win rate", "benchmark comparison", "open L2"],
        "market_side": {
            "manifest": "data/b0/market_state_manifest.json",
            "periods_built": len(manifest),
            "periods_required": 141,
            "composed_market_state_sha256": composed_sha,
            "securities_per_period": [securities[0], securities[-1]],
            "window": [manifest[0]["decision_date"], manifest[-1]["decision_date"]],
        },
        "full_decision_input": {
            "period_1_decision_date": p1["decision_date"],
            "period_1_as_of": p1["as_of"],
            "full_decision_input_sha256": p1["full_decision_input_sha256"],
            "registered_opening_state_sha256":
                p1["opening_state_seam"]["registered_opening_state_sha256"],
            "canonical_opening_state_sha256":
                p1["opening_state_seam"]["canonical_opening_state_sha256"],
            "portfolio_source": (
                "frozen opening state (C_ref cash, no holdings), read from the "
                "registry and normalized onto the canonical as-of session under "
                "C-53/R2"),
            "periods_with_full_input": p1["periods_with_full_input"],
            "periods_deferred": p1["periods_deferred"],
        },
        "sealed_inputs": {name: _sealed_input_sha(name, fn)
                          for name, fn in sorted(SEALED_INPUTS.items())},
        "statement": (
            "141/141 market-side canonical states materialized. 1/141 full "
            "CanonicalDecisionInput materialized pre-L2. Remaining 140 full "
            "inputs are intentionally deferred because their portfolio state is "
            "causally generated by prior B0 execution."),
        "why_not_a_blocker": (
            "definition B: full_input[t] cannot exist before executing t-1. The "
            "140 deferred inputs are a causal property of the specification, not "
            "a missing artefact, and nothing was fabricated to close the gap: no "
            "synthetic portfolio, no empty-portfolio substitute, no prior-period "
            "TARGET standing in for an actual portfolio, and no early run of the "
            "decision layer."),
        "provenance_note": PROVENANCE_NOTE,
        "is_blocker": False,
        "is_not_evaluable": False,
        "decision_layer_invoked": False,
        "performance_computed": False,
    }

    from core.b0_master_prereg import write_provenance_json
    write_provenance_json(RECEIPT, receipt)

    print("composed_market_state_sha256  %s" % composed_sha)
    print("full_decision_input_sha256    %s" % p1["full_decision_input_sha256"])
    print("periods_built                 %d" % len(manifest))
    print("wrote %s" % os.path.relpath(RECEIPT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
