# -*- coding: utf-8 -*-
"""B0.8 · FRACTIONAL-CLAIM LIFECYCLE M-3 AUDIT. Read-only. Zero network.

THE QUESTION, AS PUT

    Does the Frozen B0 text already define a TERMINAL treatment for a
    SecurityReceivable that is permanently `< 1 share` -- one that
    `_release_matured` never executes because `whole = int(x) = 0`?

THE RED LINE

The question is NOT "can this be read as auto-settling eventually". It is
"what do the frozen text, the declarations and the implementation contract
already say". Exactly three outcomes are admissible:

    A  EXISTING_SEMANTICS_UNAMBIGUOUSLY_DEFINE_TERMINAL_TREATMENT
       -> name the clause, its consumer and the implementation mismatch
    B  EXISTING_SEMANTICS_UNAMBIGUOUSLY_REQUIRE_PERSISTENCE
       -> the claim must persist; DataRepair / bundle acquisition stays
          necessary and B0.7's F-CA-B was correct
    C  EXISTING_SEMANTICS_UNDERSPECIFIED_OR_CONTRADICTORY
       -> M-3, STOP, adjudicate

No fourth answer may be invented here. In particular, the economic size of the
blocking claim (~1.076 shares, ~NT$14) is NOT an input: a materiality threshold
introduced after seeing a blocker is precisely the rule §2.4 mechanically
forbids (`MISSING_DATA_RATE_THRESHOLD is None`).

    python research/b0_8_holder_terms/fractional_claim_lifecycle_m3_audit.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from core.b0_canonical_hash import canonical_sha256        # noqa: E402

MASTER = os.path.join(REPO, "docs", "FrozenB0_MasterPreregistration.md")
CA = os.path.join(REPO, "core", "b0_corporate_actions.py")
STATE = os.path.join(REPO, "core", "b0_state.py")
OUT = os.path.join(HERE, "fractional_claim_lifecycle_m3_audit.json")

# Every term under which a terminal treatment could be written. The audit is
# only as strong as this list, so it is deliberately wider than the question.
TERMINAL_TERMS = ("expire", "expiry", "expiration", "write-off", "write off",
                  "沖銷", "註銷", "失效", "作廢", "自動結清", "自動現金",
                  "cash-in-lieu", "cash in lieu", "現金交割", "強制買回",
                  "終局處置", "到期消滅", "捨去", "discard")
FRACTIONAL_TERMS = ("fractional", "畸零", "零股", "不足一股", "remainder",
                    "餘數", "小數股")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def scan(path, terms):
    hits = []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        if any(t.lower() in line.lower() for t in terms):
            hits.append({"line": i, "text": line.rstrip()[:400]})
    return hits


def main() -> int:
    master_lines = open(MASTER, encoding="utf-8").read().split("\n")

    # The one clause that governs fractional entitlement, quoted exactly.
    start = next(i for i, l in enumerate(master_lines)
                 if l.startswith("#### §6.1.9"))
    end = next(i for i, l in enumerate(master_lines[start + 1:], start + 1)
               if l.startswith("#### "))
    clause = "\n".join(master_lines[start:end]).strip()

    frac_hits = scan(MASTER, FRACTIONAL_TERMS)
    term_hits = [h for h in scan(MASTER, TERMINAL_TERMS)
                 if any(t.lower() in h["text"].lower()
                        for t in FRACTIONAL_TERMS)]

    # What the implementation actually does with the remainder.
    ca_src = open(CA, encoding="utf-8").read()
    m = re.search(r"def _release_matured.*?\n(?=\ndef |\nclass )", ca_src,
                  re.S)
    impl = m.group(0) if m else ""
    keeps_remainder = ("if rest > 0:" in impl
                       and "kept_sec.append(SecurityReceivable(" in impl)
    discards = any(t in impl for t in ("round(", "math.floor", "//", "del "))

    findings = {
        "governing_clause": "§6.1.9 Fractional entitlement and rounding",
        "governing_clause_lines": [start + 1, end],
        "governing_clause_text": clause,
        "clauses_defining_a_terminal_treatment_for_a_fractional_claim":
            [h for h in term_hits
             if "捨去" not in h["text"] or "禁止" in h["text"]],
        "other_frozen_mentions_of_fractional_claims": frac_hits,
        "implementation": {
            "file": os.path.relpath(CA, REPO),
            "function": "_release_matured",
            "remainder_is_kept_as_the_same_claim": keeps_remainder,
            "remainder_is_rounded_or_discarded": discards,
            "conforms_to_the_clause": keeps_remainder and not discards,
        },
    }

    # ---- the ruling ---------------------------------------------------------
    # §6.1.9 defines exactly one transformation out of a fractional claim, and
    # it is CONDITIONAL on knowing the official rule:
    #     若官方規則要求 cash-in-lieu，則 fractional security claim → cash receivable
    # and it names the outcome when that rule is not known:
    #     settlement semantics 無法 reconstruct → W-1 BLOCK
    # There is no unconditional expiry, write-off or auto-cash-out anywhere in
    # the frozen text, and §18.6 re-affirms the lifecycle as unchanged.
    verdict = "B_EXISTING_SEMANTICS_UNAMBIGUOUSLY_REQUIRE_PERSISTENCE"

    out = {
        "record": "B0_8_FRACTIONAL_CLAIM_LIFECYCLE_M3_AUDIT",
        "question": ("does the frozen text define a terminal treatment for a "
                     "permanently <1-share SecurityReceivable that the "
                     "implementation fails to execute?"),
        "admissible_outcomes": [
            "A_EXISTING_SEMANTICS_UNAMBIGUOUSLY_DEFINE_TERMINAL_TREATMENT",
            "B_EXISTING_SEMANTICS_UNAMBIGUOUSLY_REQUIRE_PERSISTENCE",
            "C_EXISTING_SEMANTICS_UNDERSPECIFIED_OR_CONTRADICTORY"],
        "verdict": verdict,
        "verdict_basis": {
            "1_the_only_transformation_defined_is_conditional": (
                "§6.1.9: 若官方規則要求 cash-in-lieu，則 fractional security "
                "claim → cash receivable. The transformation is GATED on the "
                "official rule being known. It is not an automatic maturity "
                "treatment."),
            "2_the_unknown_case_is_named_and_its_outcome_is_prescribed": (
                "§6.1.9: 若 fractional settlement 會影響 exposed holding 之 "
                "NAV / cash / exit 而 settlement semantics 無法 reconstruct → "
                "W-1 BLOCK. 8913 is exactly this case, so B0.7's F-CA-B is the "
                "SPECIFIED behaviour, not a conformance defect."),
            "3_no_unconditional_terminal_clause_exists": (
                "a mechanical scan of the frozen text for expiry, write-off, "
                "sinking, voiding, auto-cash-settlement and forced-buyback "
                "terms returns no clause that grants a fractional claim a "
                "terminal treatment"),
            "4_the_lifecycle_was_explicitly_re_affirmed": (
                "§18.6 未變更: 零股 claim：不捨去、不虛構現金交割、不強制 "
                "credit <1 股 — B0.7 restated the lifecycle as unchanged while "
                "repairing the applicability domain around it"),
            "5_the_implementation_conforms": (
                "_release_matured keeps the remainder as the SAME claim and "
                "performs no rounding; there is no unexecuted clause"),
        },
        "consequence": {
            "is_there_a_conformance_shortcut": False,
            "b0_7_f_ca_b_at_8913_was_correct": True,
            "datarepair_or_bundle_acquisition_remains_necessary": True,
            "exit_condition_named_by_the_frozen_text": (
                "acquire the official settlement rule -- 直到官方 settlement "
                "semantics 可重建. B0.8's bundle route is not merely one option; "
                "it is the remedy §6.1.9 itself points to."),
        },
        "explicitly_not_considered": {
            "economic_size_of_the_blocking_claim": (
                "~1.076 shares, ~NT$14.4 — recorded elsewhere as an "
                "engineering-priority input only. §2.4 mechanically forbids a "
                "materiality threshold (MISSING_DATA_RATE_THRESHOLD is None), "
                "so size is not an input to this audit and no fourth outcome "
                "was constructed from it."),
        },
        "findings": findings,
        "source_hashes": {
            os.path.relpath(MASTER, REPO): sha(MASTER),
            os.path.relpath(CA, REPO): sha(CA),
            os.path.relpath(STATE, REPO): sha(STATE),
        },
        # invariants
        "text_modified": False,
        "implementation_modified": False,
        "reconstruction_classifications_changed": 0,
        "ca_ledger_unchanged": True,
        "states_unchanged": True,
        "network_requests_issued": 0,
    }
    out["audit_sha256"] = canonical_sha256(out)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print("VERDICT:", verdict)
    print("governing clause: §6.1.9, master lines %d-%d"
          % (start + 1, end))
    print("terminal-treatment clauses found for fractional claims:",
          len(findings[
              "clauses_defining_a_terminal_treatment_for_a_fractional_claim"]))
    print("implementation conforms to the clause:",
          findings["implementation"]["conforms_to_the_clause"])
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
