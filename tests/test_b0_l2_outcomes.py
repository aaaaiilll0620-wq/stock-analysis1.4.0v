"""T-7/T-8 · the L2 outcome vocabulary must be able to say what happened.

Run `L2-2520c80aa980d681` terminated in §6.1.14 F-CA-C and could not record its
own result: the machine vocabulary carried three outcomes and none of them was
true. Forcing it into `NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK` would have
disguised an implementation defect as a data problem — the one substitution
§6.1.14 exists to forbid.
"""

import pytest

from core.b0_master_prereg import (
    L2_FORBIDDEN_WORDS,
    L2_NON_EVIDENTIAL_OUTCOMES,
    L2_NOT_EVALUABLE,
    L2_NOT_EVALUABLE_CA_BLOCK,
    L2_NOT_SUPPORTED,
    L2_OUTCOMES,
    L2_RUN_INVALID_CONFORMANCE,
    L2_SUPPORTED,
    L2Opening,
    assert_l2_wording,
)

# §6.1.14's two names, verbatim, as the Master writes them in prose.
SECTION_6_1_14_RESULTS = {
    "NOT EVALUABLE — CORPORATE ACTION RECONSTRUCTION BLOCK":
        L2_NOT_EVALUABLE_CA_BLOCK,
    "RUN INVALID — IMPLEMENTATION CONFORMANCE FAILURE":
        L2_RUN_INVALID_CONFORMANCE,
}


def test_every_section_6_1_14_result_has_a_machine_token():
    for prose, token in SECTION_6_1_14_RESULTS.items():
        assert token in L2_OUTCOMES, "%s has no machine token" % prose


def test_the_tokens_preserve_the_exact_terminology():
    """R5: add the exact names; do not rename, do not generalise."""
    assert L2_NOT_EVALUABLE_CA_BLOCK == \
        "NOT_EVALUABLE_CORPORATE_ACTION_RECONSTRUCTION_BLOCK"
    assert L2_RUN_INVALID_CONFORMANCE == \
        "RUN_INVALID_IMPLEMENTATION_CONFORMANCE_FAILURE"


def test_no_run_invalid_family_was_created():
    """A generic family would reopen four questions nobody asked."""
    invalid = [o for o in L2_OUTCOMES if o.startswith("RUN_INVALID")]
    assert invalid == [L2_RUN_INVALID_CONFORMANCE], (
        "exactly one RUN_INVALID outcome is defined; a family would require "
        "ruling which defects are INVALID vs NOT_EVALUABLE, which consume the "
        "once-only observation, and how they take precedence")


def test_the_existing_three_outcomes_are_unchanged():
    for o in (L2_SUPPORTED, L2_NOT_SUPPORTED, L2_NOT_EVALUABLE):
        assert o in L2_OUTCOMES
    assert L2_SUPPORTED == "SUPPORTED"
    assert L2_NOT_SUPPORTED == "NOT_SUPPORTED"
    assert L2_NOT_EVALUABLE == "NOT_EVALUABLE_DATA_RECONSTRUCTION_BLOCK"


@pytest.mark.parametrize("outcome", sorted(L2_OUTCOMES))
def test_every_terminal_outcome_can_be_recorded(outcome):
    """T-8. The run that could not record its own result must not recur."""
    entry = L2Opening(opened_at="2026-08-19T06:25:31+00:00",
                      spec_sha256="a" * 64, code_commit="d49222b1",
                      data_manifest_sha256="b" * 64, outcome=outcome)
    assert entry.outcome == outcome


def test_an_unknown_outcome_is_still_refused():
    with pytest.raises(Exception, match="not an L2 outcome"):
        L2Opening(opened_at="t", spec_sha256="a" * 64, code_commit="c",
                  data_manifest_sha256="b" * 64, outcome="MOSTLY_FINE")


def test_the_non_evidential_outcomes_are_named():
    """§6.1.14: a run ending in any of these proves nothing about the strategy."""
    assert set(L2_NON_EVIDENTIAL_OUTCOMES) == {
        L2_NOT_EVALUABLE, L2_NOT_EVALUABLE_CA_BLOCK, L2_RUN_INVALID_CONFORMANCE}
    assert L2_SUPPORTED not in L2_NON_EVIDENTIAL_OUTCOMES
    assert L2_NOT_SUPPORTED not in L2_NON_EVIDENTIAL_OUTCOMES


def test_l3_wording_is_still_forbidden_at_l2():
    assert "VALIDATED" in L2_FORBIDDEN_WORDS
    for token in L2_OUTCOMES:
        assert_l2_wording(token)
