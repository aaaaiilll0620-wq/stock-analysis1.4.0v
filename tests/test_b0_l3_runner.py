# -*- coding: utf-8 -*-
"""The L3 prospective runner: what it refuses, and what it may not touch.

The runner is the only place in the L3 track where the strategy route could be
entered, so almost every test here is about a REFUSAL. Three of them are about
things that must stay true of files this harness deliberately does not own:

  * `run_b0_7_diagnostic.py` still hashes to the value its own completed run
    recorded -- which is the entire reason this is a second harness rather than
    a mode added to that one;
  * the runner reaches no strategy layer by import;
  * the first execution of the prospective route is gated on the SPECIFICATION,
    not on a flag, and the gate is currently closed.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from datetime import date
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_l3_runner"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.b0_l3_run_layout as layout                             # noqa: E402
import run_l3_prospective as R                                     # noqa: E402

B0_7_HARNESS = os.path.join(REPO, "research", "b0_7_diagnostic",
                            "run_b0_7_diagnostic.py")
B0_7_RUNS = os.path.join(REPO, "artifacts", "b0_7_diagnostic", "runs")


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# --- why this is a second harness --------------------------------------------------

def test_the_b0_7_harness_still_hashes_to_what_its_own_run_recorded():
    """A completed run pinned its harness by sha256. Those bytes are evidence."""
    pinned = {}
    for name in sorted(os.listdir(B0_7_RUNS)):
        final = os.path.join(B0_7_RUNS, name, "final_result.json")
        if os.path.exists(final):
            with open(final, encoding="utf-8") as fh:
                rec = json.load(fh)
            if rec.get("harness_sha256"):
                pinned[name] = rec["harness_sha256"]

    assert pinned, "no completed B0.7 run to pin the harness against"
    measured = _sha(B0_7_HARNESS)
    for run_id, sha in pinned.items():
        assert measured == sha, (
            "run %s recorded harness_sha256=%s but the file now hashes to %s. "
            "The L3 runner exists as a separate file precisely so that this "
            "never has to move." % (run_id, sha[:16], measured[:16]))


def test_the_runner_does_not_import_the_pinned_harness():
    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names |= {a.name for a in node.names}

    assert not any("b0_7" in n for n in names), sorted(names)


def test_the_runner_contains_no_strategy_layer_import():
    """Every decision happens behind `run_decision`, as in L2."""
    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            reached.add(node.module)
        elif isinstance(node, ast.Import):
            reached |= {a.name for a in node.names}

    forbidden = {"core.b0_decision", "core.b0_eligibility", "core.b0_features",
                 "core.b0_execution"}
    assert not (reached & forbidden), sorted(reached & forbidden)
    assert "core.b0_route" in reached      # and the shared route IS reached


# --- the two-phase hand-off ---------------------------------------------------------
#
# A prospective period is observed twice: `--mode intent` ON the decision date,
# and `--mode execute` after the next session is observed. The two phases can
# NEVER assemble the same market state -- the executable one contains that
# session's date and its opening prices and the decision-date one cannot -- so
# `market_state_sha256` differs BY CONSTRUCTION and only
# `decision_cutoff_state_sha256` (the same payload with those two execution
# facts blanked) can be an equality field.
#
# The fixtures below therefore use DIFFERENT market-state hashes on the two
# sides deliberately, because that is what reality produces. The previous
# version of this file used one value on both sides, which meant the hand-off
# test would have passed no matter which of the two fields was bound -- and the
# bound field was the one that made `--mode execute` unreachable.
INTENT_MARKET_STATE = "1" * 64
EXEC_MARKET_STATE = "2" * 64
CUTOFF_STATE = "3" * 64
PROVENANCE = {"genesis_cohort_id": "L3_PRIMARY_20M",
              "opening_c_ref": 20_000_000.0,
              "route_seal_id": "L3-ROUTE-SEAL-FIXTURE",
              "sealed_evidence": False,
              "commit_sha": "d" * 40, "harness_sha256": "e" * 64}


def _intent_stub(*, ranking=("1102", "1101"), selected=("1102",),
                 weights=None, config_hash="c" * 64):
    return SimpleNamespace(
        route_kind="production",
        decision_date="2026-08-31", as_of="2026-08-28",
        config_hash=config_hash, stages=("pit_raw_state",),
        eligibility=SimpleNamespace(eligible=("1101", "1102")),
        ranking=tuple(ranking),
        targets=SimpleNamespace(selected=tuple(selected),
                                weights=dict(weights or {"1102": 0.05})),
        target_shares={"1102": 1000}, port_value=20_000_000.0)


def _built(market_state):
    """One phase's `build_period` result, reduced to what the contract reads."""
    return {
        "assembled": {"market_state_sha256": market_state,
                      "decision_cutoff_state_sha256": CUTOFF_STATE},
        "portfolio_side_payload": {"cash": 20_000_000.0},
    }


def _publish_intent(directory, built, intent, provenance=None, mutate=None):
    """A REAL publication bundle, written by the runner's own committer.

    `assert_prior_intent_matches` refuses a bare `decision_intent.json`: a
    half-published directory is not an executable intent, and a test that wrote
    only that one file aborted on the missing marker before it ever reached the
    comparison it existed to make.
    """
    provenance = PROVENANCE if provenance is None else provenance
    payload = R.decision_intent_payload("L3-INTENT", built, intent, provenance)
    if mutate is not None:
        payload = mutate(payload)
    R.write_provenance_json(os.path.join(directory, R.DECISION_INTENT), payload)
    for name in (R.SNAPSHOT_RECEIPT, R.PORTFOLIO_RECEIPT, R.OPENING_RECORD,
                 R.FINAL_RESULT):
        R.write_provenance_json(os.path.join(directory, name),
                                {"record": name, "run_id": "L3-INTENT"})
    R.commit_publication(directory, "L3-INTENT", "intent",
                         intent.decision_date, provenance,
                         (R.SNAPSHOT_RECEIPT, R.PORTFOLIO_RECEIPT,
                          R.OPENING_RECORD, R.DECISION_INTENT, R.FINAL_RESULT))
    return os.path.join(directory, R.DECISION_INTENT), payload


def test_decision_intent_payload_cannot_claim_an_execution():
    intent = _intent_stub()
    built = _built(INTENT_MARKET_STATE)
    payload = R.decision_intent_payload("L3-TEST", built, intent,
                                        {"commit_sha": "h" * 40})

    assert payload["execution_date"] is None
    assert payload["execution_observed"] is False
    assert payload["execution_layer_invoked"] is False
    assert payload["costs"] is None
    assert payload["post_trade_state"] is None
    assert payload["sizing_price_basis"] == "AS_OF_MARK_NOT_EXECUTION_PRICE"
    assert payload["selected"] == ["1102"]
    assert len(payload["intent_payload_sha256"]) == 64
    assert payload["decision_contract_sha256"] == \
        R.canonical_sha256(payload["decision_contract"])


def test_a_prospective_intent_cannot_be_claimed_early_or_backdated(monkeypatch):
    monkeypatch.setattr(R, "_taipei_today", lambda: date(2026, 8, 31))

    R._assert_intent_claim_is_today("2026-08-31")
    with pytest.raises(R.L3RunAbort, match="actual Asia/Taipei"):
        R._assert_intent_claim_is_today("2026-09-01")
    with pytest.raises(R.L3RunAbort, match="backdating"):
        R._assert_intent_claim_is_today("2026-08-28")


def _cohort_args(**kw):
    base = dict(opening_kind="GENESIS", genesis_cohort="", lineage_cohort="",
                c_ref=0.0, synthetic_sources=False, sealed_evidence=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_genesis_cash_is_bound_to_a_named_prospective_cohort():
    good = _cohort_args(genesis_cohort="L3_PRIMARY_20M", c_ref=20_000_000.0)
    assert R._assert_cohort_identity(good)["opening_cash"] == 20_000_000.0

    with pytest.raises(R.L3RunAbort, match="requires opening cash"):
        R._assert_cohort_identity(_cohort_args(
            genesis_cohort="L3_PRIMARY_20M", c_ref=2_000_000.0))
    with pytest.raises(R.L3RunAbort, match="fixture-only"):
        R._assert_cohort_identity(_cohort_args(
            genesis_cohort=R.SYNTHETIC_PARITY_COHORT, c_ref=2_000_000.0))


# --- S-1 · the cohort is carried forward, not asserted once at genesis ----------
#
# Two registered cells run side by side (L3_PRIMARY_20M / L3_SECONDARY_50M) and
# NAV is the input to `core.b0_eligibility.adv_floor(port_value)`. Cohort
# identity used to be checked at GENESIS only: from period 2 the two tracks were
# separated by the magnitude of `state.cash` and by nothing else, so a
# checkpoint crossed between them produced a normal-looking decision over a
# silently different eligible population.

def test_a_continuation_must_name_the_cohort_its_lineage_was_opened_under():
    # "named nothing" and "named something unregistered" are different facts
    # and get different refusals. Matching only the flag name would let the
    # first guard be deleted and the message quietly become the second one's.
    with pytest.raises(
            R.L3RunAbort,
            match="must name the cohort its lineage was opened under"):
        R._assert_cohort_identity(_cohort_args(opening_kind="CONTINUATION"))
    with pytest.raises(R.L3RunAbort, match="not a registered cohort"):
        R._assert_cohort_identity(_cohort_args(
            opening_kind="CONTINUATION", lineage_cohort="L3_SOMETHING_ELSE"))
    with pytest.raises(R.L3RunAbort, match="fixture-only"):
        R._assert_cohort_identity(_cohort_args(
            opening_kind="CONTINUATION",
            lineage_cohort=R.SYNTHETIC_PARITY_COHORT))

    got = R._assert_cohort_identity(_cohort_args(
        opening_kind="CONTINUATION", lineage_cohort="L3_SECONDARY_50M"))
    assert got["cohort_id"] == "L3_SECONDARY_50M"
    # and it reaches the field the decision contract already compares, which is
    # what makes the two tracks distinguishable from period 2 onward
    assert got["genesis_cohort_id"] == "L3_SECONDARY_50M"


def test_the_continuation_cohort_is_not_blank_in_the_decision_contract():
    """The defect, expressed at the contract: `genesis_cohort_id` was ""."""
    cohort = R._assert_cohort_identity(_cohort_args(
        opening_kind="CONTINUATION", lineage_cohort="L3_PRIMARY_20M"))
    provenance = dict(PROVENANCE, genesis_cohort_id=cohort["genesis_cohort_id"])
    contract = R.decision_contract_payload(_built(INTENT_MARKET_STATE),
                                           _intent_stub(), provenance)

    assert contract["genesis_cohort_id"] == "L3_PRIMARY_20M"
    assert "genesis_cohort_id" in R.DECISION_CONTRACT_COMPARED_FIELDS


def test_one_cohort_argument_per_opening_contract_and_no_third_form():
    """An argument that would be IGNORED is a decision input silently lost."""
    with pytest.raises(R.L3RunAbort, match="belongs to the CONTINUATION"):
        R._assert_cohort_identity(_cohort_args(
            genesis_cohort="L3_PRIMARY_20M", c_ref=20_000_000.0,
            lineage_cohort="L3_PRIMARY_20M"))
    with pytest.raises(R.L3RunAbort,
                       match="may not name a genesis cohort or c_ref"):
        R._assert_cohort_identity(_cohort_args(
            opening_kind="CONTINUATION", lineage_cohort="L3_PRIMARY_20M",
            c_ref=20_000_000.0))


def _cohort_checkpoint(tmp_path, name, cohort_id, cash=20_000_000.0, rows=1):
    """A checkpoint file whose rows name (or refuse to name) a cohort."""
    from core.b0_master_prereg import append_provenance_record
    from core.b0_state import PortfolioState
    from research.b0_checkpoint import portfolio_checkpoint as pc

    d = tmp_path / name
    d.mkdir()
    path = str(d / pc.CHECKPOINT_FILENAME)
    for seq in range(1, rows + 1):
        append_provenance_record(path, pc.checkpoint_record(
            run_id="L3-PREV", seq=seq, period="2026-%02d" % (8 + seq),
            state=PortfolioState(as_of="2026-09-30", cash=cash, shares={}),
            cohort_id=cohort_id))
    return path


def test_a_continuation_whose_checkpoint_names_another_cohort_aborts(tmp_path):
    """The crossed checkpoint. Both cells look identical apart from cash."""
    crossed = _cohort_checkpoint(tmp_path, "crossed", "L3_SECONDARY_50M",
                                 cash=50_000_000.0)

    with pytest.raises(R.L3RunAbort, match="crossed between two capacity cells"):
        R.build_period("unused", "L3-NOW", "2026-10-30", {}, crossed,
                       opening_kind="CONTINUATION",
                       cohort_id="L3_PRIMARY_20M")


def test_a_continuation_whose_checkpoint_names_no_cohort_aborts(tmp_path):
    """"Names none" is refused exactly as "names another" is."""
    unnamed = _cohort_checkpoint(tmp_path, "unnamed", "")

    with pytest.raises(R.L3RunAbort, match="name no cohort"):
        R.build_period("unused", "L3-NOW", "2026-10-30", {}, unnamed,
                       opening_kind="CONTINUATION",
                       cohort_id="L3_PRIMARY_20M")


def test_a_continuation_may_not_reach_a_checkpoint_without_naming_a_cohort(
        tmp_path):
    named = _cohort_checkpoint(tmp_path, "named", "L3_PRIMARY_20M")

    with pytest.raises(R.L3RunAbort, match="must name the cohort"):
        R.build_period("unused", "L3-NOW", "2026-10-30", {}, named,
                       opening_kind="CONTINUATION", cohort_id="")


def test_a_genesis_opening_checkpoint_may_predate_the_cohort_field(tmp_path):
    """It was written before the field existed -- but a disagreement still stops."""
    from research.b0_checkpoint import portfolio_checkpoint as pc

    older = _cohort_checkpoint(tmp_path, "older", "")
    assert pc.assert_checkpoint_cohort(
        older, expected_cohort_id="L3_PRIMARY_20M",
        rule=pc.COHORT_MAY_PREDATE_THE_LINEAGE)["rows_naming_no_cohort"] == 1

    disagreeing = _cohort_checkpoint(tmp_path, "disagreeing", "L3_SECONDARY_50M")
    with pytest.raises(pc.CheckpointError, match="crossed between"):
        pc.assert_checkpoint_cohort(
            disagreeing, expected_cohort_id="L3_PRIMARY_20M",
            rule=pc.COHORT_MAY_PREDATE_THE_LINEAGE)


def test_the_checkpoint_cohort_rule_is_declared_never_inferred():
    from research.b0_checkpoint import portfolio_checkpoint as pc

    with pytest.raises(pc.CheckpointError, match="never an inference"):
        pc.assert_checkpoint_cohort("nowhere.jsonl",
                                    expected_cohort_id="L3_PRIMARY_20M",
                                    rule="whatever-seems-reasonable")
    with pytest.raises(pc.CheckpointError, match="verifies nothing"):
        pc.assert_checkpoint_cohort("nowhere.jsonl", expected_cohort_id="",
                                    rule=pc.COHORT_MUST_BE_NAMED)


def test_the_runner_writes_a_checkpoint_that_names_its_cohort():
    """The carry-forward half: what run N writes is what run N+1 verifies.

    `portfolio_side.append_checkpoint` cannot name a cohort, so a runner that
    still used it would write the very row the next period must refuse.
    """
    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    writes = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call)
              and getattr(n.func, "attr", "") in ("append_checkpoint",
                                                  "checkpoint_record")]
    named = [n for n in writes
             if any(k.arg == "cohort_id" for k in n.keywords)]
    assert writes, "the runner writes no checkpoint at all"
    assert len(named) == len(writes), (
        "%d of %d checkpoint write(s) in the runner do not name a cohort"
        % (len(writes) - len(named), len(writes)))


# --- S-4 · the synthetic cohort may not borrow a registered cell's identity -----

@pytest.mark.parametrize("cash", sorted(R.L3_GENESIS_COHORTS.values()))
def test_the_parity_cohort_may_not_open_at_a_registered_cells_cash(cash):
    """`expected = c_ref` admitted ANY NAV, including a registered cell's.

    `core.b0_state` refuses a synthetic input for a sealed run, so this never
    reached sealed evidence -- but a fixture opened at 20,000,000 selects
    L3_PRIMARY_20M's eligible population and writes records nothing can tell
    apart from the real cell's.
    """
    with pytest.raises(R.L3RunAbort, match="may not borrow a registered"):
        R._assert_cohort_identity(_cohort_args(
            genesis_cohort=R.SYNTHETIC_PARITY_COHORT, c_ref=cash,
            synthetic_sources=True))


def test_the_parity_cohort_may_not_open_a_sealed_run():
    with pytest.raises(R.L3RunAbort, match="sealed evidence"):
        R._assert_cohort_identity(_cohort_args(
            genesis_cohort=R.SYNTHETIC_PARITY_COHORT, c_ref=2_000_000.0,
            synthetic_sources=True, sealed_evidence=True))


def test_the_parity_cohort_still_opens_the_frozen_c_ref_fixture():
    """The tightening may not close the path the fixture legitimately uses."""
    from core.b0_benchmark_construction import C_REF

    assert C_REF not in set(R.L3_GENESIS_COHORTS.values())
    got = R._assert_cohort_identity(_cohort_args(
        genesis_cohort=R.SYNTHETIC_PARITY_COHORT, c_ref=C_REF,
        synthetic_sources=True))
    assert got["opening_cash"] == C_REF

    with pytest.raises(R.L3RunAbort, match="positive opening cash"):
        R._assert_cohort_identity(_cohort_args(
            genesis_cohort=R.SYNTHETIC_PARITY_COHORT, c_ref=0.0,
            synthetic_sources=True))


def test_the_contract_binds_the_phase_invariant_hash_and_records_the_other():
    """Which set a field is in is a declaration, not an accident of the dict."""
    contract = R.decision_contract_payload(_built(INTENT_MARKET_STATE),
                                           _intent_stub(), PROVENANCE)

    assert sorted(contract) == sorted(R.DECISION_CONTRACT_COMPARED_FIELDS)
    assert not (set(R.DECISION_CONTRACT_COMPARED_FIELDS)
                & set(R.DECISION_CONTRACT_RECORDED_FIELDS))
    # the field that differs by construction is not an equality field ...
    assert "market_state_sha256" not in contract
    assert contract["decision_cutoff_state_sha256"] == CUTOFF_STATE

    payload = R.decision_intent_payload("L3-INTENT", _built(INTENT_MARKET_STATE),
                                        _intent_stub(), PROVENANCE)
    # ... but it is still published, at the same key it always occupied, and is
    # still immutable evidence: it is covered by the outer payload hash and by
    # the publication marker. Dropping it would sever a published intent from
    # the snapshot receipt of the run that produced it.
    assert payload["market_state_sha256"] == INTENT_MARKET_STATE
    assert payload["decision_state_provenance"] == {
        "market_state_sha256": INTENT_MARKET_STATE}
    assert payload["decision_state_provenance_compared"] is False
    assert "market_state_sha256" not in payload["decision_contract"]


def test_execution_completes_an_intent_whose_market_state_moved(tmp_path):
    """Phase B must be REACHABLE: the whole point of publishing an intent.

    The two sides differ exactly as an intent run and its later execution run
    differ -- a different `market_state_sha256`, the same decision cut-off --
    and the hand-off must accept that. It is not a tolerance: nothing that was
    decided has changed, and the field that moved is the one that names the
    execution session the decision could not have seen.
    """
    intent = _intent_stub()
    path, published = _publish_intent(str(tmp_path), _built(INTENT_MARKET_STATE),
                                      intent)

    prior = R.assert_prior_intent_matches(
        path, _built(EXEC_MARKET_STATE), intent, PROVENANCE)

    assert prior["decision_contract_sha256"] == \
        published["decision_contract_sha256"]
    assert prior["decision_state_provenance"]["market_state_sha256"] == \
        INTENT_MARKET_STATE
    assert prior["execution_observed"] is False


@pytest.mark.parametrize("field,execute_side", [
    ("ranking", dict(ranking=("1101", "1102"))),
    ("selected", dict(selected=("1101",), weights={"1101": 0.05})),
    ("target_weights", dict(weights={"1102": 0.06})),
    ("config_hash", dict(config_hash="f" * 64)),
])
def test_execution_is_refused_when_a_decision_bearing_field_differs(
        tmp_path, field, execute_side):
    """The negative half. Without it the contract could compare nothing.

    Each case re-decides ONE thing at execution time -- a different order of
    the ranking, a different name selected, a different weight, a different
    frozen configuration -- and the abort must name that field. The market
    state moves in every case too, exactly as it does in reality, so no case
    can pass merely because the two sides were identical.
    """
    path, _ = _publish_intent(str(tmp_path), _built(INTENT_MARKET_STATE),
                              _intent_stub())

    with pytest.raises(R.L3RunAbort, match="differs") as exc:
        R.assert_prior_intent_matches(path, _built(EXEC_MARKET_STATE),
                                      _intent_stub(**execute_side), PROVENANCE)
    assert field in str(exc.value)
    assert "market_state_sha256" not in str(exc.value)


def test_execution_is_refused_when_the_declared_opening_differs(tmp_path):
    path, _ = _publish_intent(str(tmp_path), _built(INTENT_MARKET_STATE),
                              _intent_stub())

    changed = dict(PROVENANCE, opening_c_ref=50_000_000.0)
    with pytest.raises(R.L3RunAbort, match="differs") as exc:
        R.assert_prior_intent_matches(path, _built(EXEC_MARKET_STATE),
                                      _intent_stub(), changed)
    assert "opening_c_ref" in str(exc.value)


def test_a_prior_intent_that_bound_a_phase_dependent_field_is_refused(tmp_path):
    """An intent published under the OLD contract shape is not comparable.

    Its equality set contains a field that can never be equal across the two
    phases. Executing it would abort on that field with a message about a
    re-decision that never happened, so the shape is refused by name instead.
    """
    def _legacy(payload):
        legacy = dict(payload)
        legacy.pop("intent_payload_sha256")
        contract = dict(legacy["decision_contract"],
                        market_state_sha256=INTENT_MARKET_STATE)
        legacy["decision_contract"] = contract
        legacy["decision_contract_sha256"] = R.canonical_sha256(contract)
        return {**legacy,
                "intent_payload_sha256": R.canonical_sha256(legacy)}

    path, _ = _publish_intent(str(tmp_path), _built(INTENT_MARKET_STATE),
                              _intent_stub(), mutate=_legacy)

    with pytest.raises(R.L3RunAbort, match="different field set") as exc:
        R.assert_prior_intent_matches(path, _built(EXEC_MARKET_STATE),
                                      _intent_stub(), PROVENANCE)
    assert "phase-dependent" in str(exc.value)
    assert "market_state_sha256" in str(exc.value)


def test_the_hand_off_refuses_a_bundle_that_was_never_committed(tmp_path):
    """The marker, not the file, is what makes a published intent executable."""
    payload = R.decision_intent_payload("L3-INTENT", _built(INTENT_MARKET_STATE),
                                        _intent_stub(), PROVENANCE)
    path = tmp_path / R.DECISION_INTENT
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(R.L3RunAbort, match="publication commit marker"):
        R.assert_prior_intent_matches(str(path), _built(EXEC_MARKET_STATE),
                                      _intent_stub(), PROVENANCE)


# --- the execution gate --------------------------------------------------------------

def test_the_closure_transaction_state_is_measured_not_asserted():
    state = R.closure_transaction_state()

    for key in ("freeze_version", "document_version", "freeze_spec_sha256",
                "document_spec_sha256", "version_agrees", "spec_sha_agrees",
                "normative_module_set_agrees", "normative_modules_agree",
                "normative_module_mismatch", "in_transaction"):
        assert key in state
    assert state["in_transaction"] == (not (
        state["version_agrees"] and state["spec_sha_agrees"]
        and state["normative_module_set_agrees"]
        and state["normative_modules_agree"]))


def test_route_execution_is_refused_while_the_specification_is_mid_transaction():
    """The gate is on the spec, not on a flag the caller can flip.

    This test asserts the LOGIC, not today's verdict: if the closure transaction
    is open, or the assembly still reports unregistered span derivations, the
    first execution must be refused and the refusal must name the gate.
    """
    import l3_route_seal as rs

    tx = R.closure_transaction_state()
    spans = R.span_derivation_state()
    try:
        rs.assert_route_is_sealable()
        sealable = True
    except rs.RouteSealError:
        sealable = False
    should_refuse = (tx["in_transaction"]
                     or not spans["spans_have_a_registered_derivation"]
                     or not sealable)

    if should_refuse:
        with pytest.raises(R.L3RunAbort) as exc:
            R.assert_route_execution_admissible({"route_seal_id": "PENDING"}, "")
        assert R.ROUTE_EXECUTION_GATE in str(exc.value)
    else:
        checks = R.assert_route_execution_admissible({"route_seal_id": "PENDING"}, "")
        assert all(c["status"] == "PASS" for c in checks)


def test_the_span_derivation_state_reads_the_assembly_not_a_local_copy():
    """The declaration is the assembly's own, on whichever contract it is on."""
    import l3_assemble as A

    state = R.span_derivation_state()
    assert (tuple(state["assembly_unregistered_span_derivations"])
            == tuple(getattr(A, "UNREGISTERED_SPAN_DERIVATIONS", ()) or ()))
    assert state["spans_have_a_registered_derivation"] == bool(
        state["span_rule_module_present"]
        and state["assembly_span_contract"] == R.CONTRACT_LINEAGE_FLOOR
        and not getattr(A, "UNREGISTERED_SPAN_DERIVATIONS", ()))


def test_the_span_contract_is_detected_from_the_assembly_signature():
    """Guessing wrong is a TypeError, not a wrong number -- so it is detected.

    `l3_assemble.assemble` is being re-wired by §19 / C-68 from four
    caller-supplied endpoints to one frozen lineage floor. This runner is
    directly downstream of it and must take whichever it is on TODAY.
    """
    import inspect

    import l3_assemble as A

    params = set(inspect.signature(A.assemble).parameters)
    contract = R.assembly_span_contract()

    assert contract in (R.CONTRACT_LINEAGE_FLOOR, R.CONTRACT_EXPLICIT_SPANS)
    if contract == R.CONTRACT_LINEAGE_FLOOR:
        assert "lineage_price_floor" in params
    else:
        assert {"price_span", "bonus_window"} <= params


def test_the_section_19_contract_refuses_a_caller_supplied_endpoint():
    """Under §19 an override is not an alternative, it is an error."""
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(
            _Args(lineage_price_floor="2004-01-02", **LEGACY_FOUR),
            as_of="2026-03-30", execution_date="2026-04-01",
            contract=R.CONTRACT_LINEAGE_FLOOR)
    assert "override is refused" in str(exc.value)


def test_the_section_19_contract_still_refuses_to_default_the_floor():
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(_Args(), as_of="2026-03-30",
                        execution_date="2026-04-01",
                        contract=R.CONTRACT_LINEAGE_FLOOR)
    assert "--lineage-price-floor" in str(exc.value)


def test_the_section_19_contract_resolves_to_the_floor_alone():
    spans = R.resolve_spans(_Args(lineage_price_floor="2004-01-02"),
                            as_of="2026-03-30", execution_date="2026-04-01",
                            contract=R.CONTRACT_LINEAGE_FLOOR)
    assert spans["lineage_price_floor"] == "2004-01-02"
    assert "price_span" not in spans     # the assembly derives it, not this
    assert "bonus_window" not in spans


def test_the_declared_master_version_is_read_from_the_document():
    version = R.declared_master_version()
    assert version.count(".") == 1 and version.replace(".", "").isdigit()
    # and it is the document's own claim, not the freeze record's
    with open(R.FREEZE, encoding="utf-8") as fh:
        freeze = json.load(fh)
    assert R.closure_transaction_state()["freeze_version"] == freeze["version"]


# --- spans are never defaulted ---------------------------------------------------------

class _Args:
    def __init__(self, **kw):
        self.price_span_from = ""
        self.price_span_to = ""
        self.bonus_window_from = ""
        self.bonus_window_to = ""
        self.lineage_price_floor = ""
        for k, v in kw.items():
            setattr(self, k, v)


LEGACY_FOUR = dict(price_span_from="2013-01-01", price_span_to="2026-04-01",
                   bonus_window_from="2013-06-29", bonus_window_to="2026-03-31")


def test_resolve_spans_refuses_to_pick_an_endpoint():
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(_Args(), as_of="2026-03-30",
                        execution_date="2026-04-01",
                        contract=R.CONTRACT_EXPLICIT_SPANS)
    assert "no default" in str(exc.value)


def test_resolve_spans_accepts_four_explicit_endpoints():
    spans = R.resolve_spans(
        _Args(price_span_from="2004-01-02", price_span_to="2026-04-01",
              bonus_window_from="2025-02-28", bonus_window_to="2026-03-30"),
        as_of="2026-03-30", execution_date="2026-04-01",
        contract=R.CONTRACT_EXPLICIT_SPANS)

    assert spans["price_span"] == ("2004-01-02", "2026-04-01")
    assert spans["bonus_window"] == ("2025-02-28", "2026-03-30")
    assert spans["source"] == "explicit_caller_declaration"
    assert spans["assembly_span_contract"] == R.CONTRACT_EXPLICIT_SPANS
    # No floor disposition, because on this contract there is no floor rule to
    # adjudicate against -- inventing one here would be the specification-by-
    # code §19 exists to replace.
    assert "floor_disposition" not in spans
    assert "lineage_price_floor" not in spans


def test_the_lineage_floor_belongs_to_the_other_contract_and_is_refused():
    """An argument that would be IGNORED is a decision input silently lost."""
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(_Args(lineage_price_floor="2004-01-02", **LEGACY_FOUR),
                        as_of="2026-03-30", execution_date="2026-04-01",
                        contract=R.CONTRACT_EXPLICIT_SPANS)
    assert "--lineage-price-floor belongs to" in str(exc.value)


@pytest.mark.parametrize("absent", list(R.LEGACY_SPAN_ARGS))
def test_a_partial_explicit_span_set_is_refused_by_name(absent):
    """Three of four is not 'no default' -- it is a half-supplied decision input."""
    supplied = {k: v for k, v in LEGACY_FOUR.items() if k != absent}
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(_Args(**supplied), as_of="2026-03-30",
                        execution_date="2026-04-01",
                        contract=R.CONTRACT_EXPLICIT_SPANS)
    assert "--" + absent.replace("_", "-") in str(exc.value)


def test_an_explicit_price_span_that_stops_before_execution_is_refused():
    """§6.5: a span that cannot price the trade the decision authorises."""
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(_Args(**{**LEGACY_FOUR, "price_span_to": "2026-03-30"}),
                        as_of="2026-03-30", execution_date="2026-04-01",
                        contract=R.CONTRACT_EXPLICIT_SPANS)
    assert "--price-span-to" in str(exc.value)


@pytest.mark.parametrize("name", list(R.LEGACY_SPAN_ARGS))
def test_every_legacy_span_argument_is_refused_under_section_19_individually(
        name):
    """Previously only three of the four were caught; one at a time proves it."""
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(
            _Args(lineage_price_floor="2004-01-02",
                  **{name: LEGACY_FOUR[name]}),
            as_of="2026-03-30", execution_date="2026-04-01",
            contract=R.CONTRACT_LINEAGE_FLOOR)
    assert "--" + name.replace("_", "-") in str(exc.value)


def test_the_two_section_19_hint_arguments_are_gone():
    """`--earliest-month-end-session` / `--observed-price-floor` are removed.

    Under §19 the assembly reads the month-end session off the declared
    calendar and the observed floor off the declared prices. A caller-supplied
    answer to either IS the override §19 refuses, so the arguments do not exist
    rather than being accepted and ignored.
    """
    flags = {a for action in R.build_parser()._actions
             for a in action.option_strings}

    assert "--earliest-month-end-session" not in flags
    assert "--observed-price-floor" not in flags
    source = open(R.__file__, encoding="utf-8").read()
    assert "earliest_month_end_session" not in source
    assert "observed_price_floor" not in source


def test_an_unknown_assembly_contract_is_an_abort_not_a_guess():
    with pytest.raises(R.L3RunAbort) as exc:
        R.resolve_spans(_Args(), as_of="2026-03-30",
                        execution_date="2026-04-01", contract="something-else")
    assert "guessing at a decision input" in str(exc.value)


# --- S-2 · the source-revision stop rule is wired to the decision route -----------
#
# `l3_temporal_snapshot.assert_append_only_continuity` implements the ruling
# draft's stop rule ("a revision inside the overlap is a stop, not a quiet
# refresh") and had no caller anywhere outside its own unit test, so on this
# route the rule did not exist. The baseline is the PRECEDING run's own
# source-ownership manifest; the first run of a lineage declares that it has
# none, and that declaration is recorded rather than skipped.

def _source_entry(locator, sha, vintage, **over):
    e = {"locator": locator, "format": "parquet", "raw_sha256": sha,
         "export_vintage": vintage,
         "observed_at": "2026-08-31T00:00:00+08:00",
         "source_family": "TEJ", "authority": "AUTHORITATIVE",
         "disposition": "consumed"}
    e.update(over)
    return e


def _source_run(root, run_id, entries, dataset="calendar", policies=None):
    """A real run directory with a real leaf and a real aggregate.

    Built through the manifest engine rather than by writing JSON, so the
    baseline this test compares against is the same object the runner reads.
    """
    from core.b0_l3_lineage_capture import PURPOSE_DIAGNOSTIC
    from source_ownership_manifest import (
        assemble_aggregate, build_leaf, write_aggregate, write_leaf,
    )

    d = os.path.join(str(root), run_id)
    os.makedirs(d)
    write_leaf(d, build_leaf(dataset=dataset, run_id=run_id,
                             as_of="2026-08-31", entries=entries,
                             policies=policies))
    write_aggregate(d, assemble_aggregate(
        run_dir=d, run_id=run_id, as_of="2026-08-31",
        purpose=PURPOSE_DIAGNOSTIC, required={dataset}))
    return d


def _baseline_manifest(run_dir):
    from source_ownership_manifest import AGGREGATE_FILENAME

    return os.path.join(run_dir, AGGREGATE_FILENAME)


def test_a_later_source_export_is_admitted_as_a_strict_append(tmp_path):
    base = _source_run(tmp_path, "L3-BASE",
                       [_source_entry("taiex.parquet", "a" * 64, "2026-08-17")])
    later = _source_run(tmp_path, "L3-LATER",
                        [_source_entry("taiex.parquet", "a" * 64, "2026-08-17"),
                         _source_entry("taiex_0828.parquet", "b" * 64,
                                       "2026-08-28")])

    got = R.assert_source_continuity(later,
                                     prior_manifest=_baseline_manifest(base),
                                     no_prior_declared=False)

    assert got["baseline"] == "PRIOR_RUN_SOURCE_OWNERSHIP_MANIFEST"
    assert got["baseline_run_id"] == "L3-BASE"
    assert got["datasets_compared"] == ["calendar"]
    calendar = got["per_dataset"]["calendar"]
    assert calendar["status"] == "APPEND_ONLY"
    assert calendar["appended_rows"] == 1
    # the overlap is digest-identical, which is what "append" MEANS here
    assert calendar["prior_full_semantic_digest"] == \
        calendar["current_overlap_semantic_digest"]


def test_a_revision_inside_the_observed_overlap_is_a_stop(tmp_path):
    """The negative half. Same locator, same vintage, DIFFERENT bytes."""
    base = _source_run(tmp_path, "L3-BASE",
                       [_source_entry("taiex.parquet", "a" * 64, "2026-08-17")])
    revised = _source_run(tmp_path, "L3-REVISED",
                          [_source_entry("taiex.parquet", "c" * 64,
                                         "2026-08-17")])

    with pytest.raises(R.L3RunAbort) as exc:
        R.assert_source_continuity(revised,
                                   prior_manifest=_baseline_manifest(base),
                                   no_prior_declared=False)
    assert "HISTORICAL_SOURCE_REVISION" in str(exc.value)
    assert "calendar" in str(exc.value)
    assert "quiet refresh" in str(exc.value)


def test_a_source_family_that_stops_being_declared_is_a_stop(tmp_path):
    base = _source_run(tmp_path, "L3-BASE",
                       [_source_entry("taiex.parquet", "a" * 64, "2026-08-17")])
    other = _source_run(tmp_path, "L3-OTHER",
                        [_source_entry("px.parquet", "d" * 64, "2026-08-17")],
                        dataset="prices")

    with pytest.raises(R.L3RunAbort, match="stops being declared"):
        R.assert_source_continuity(other,
                                   prior_manifest=_baseline_manifest(base),
                                   no_prior_declared=False)


def test_the_first_run_of_a_lineage_records_no_baseline_rather_than_skipping(
        tmp_path):
    """A silent skip and a genuinely first run look identical afterwards."""
    first = _source_run(tmp_path, "L3-FIRST",
                        [_source_entry("taiex.parquet", "a" * 64,
                                       "2026-08-17")])

    got = R.assert_source_continuity(first, prior_manifest="",
                                     no_prior_declared=True)

    assert got["baseline"] == R.NO_SOURCE_BASELINE
    assert got["datasets_compared"] == []
    assert got["datasets_without_baseline"] == ["calendar"]


def test_the_source_baseline_is_a_declaration_with_no_third_state(tmp_path):
    base = _source_run(tmp_path, "L3-BASE",
                       [_source_entry("taiex.parquet", "a" * 64, "2026-08-17")])

    for prior, none_declared in ((_baseline_manifest(base), True), ("", False)):
        with pytest.raises(R.L3RunAbort, match="exactly one of"):
            R.assert_source_continuity(base, prior_manifest=prior,
                                       no_prior_declared=none_declared)


def test_a_run_may_not_be_its_own_source_baseline(tmp_path):
    base = _source_run(tmp_path, "L3-BASE",
                       [_source_entry("taiex.parquet", "a" * 64, "2026-08-17")])

    with pytest.raises(R.L3RunAbort, match="own source baseline"):
        R.assert_source_continuity(base,
                                   prior_manifest=_baseline_manifest(base),
                                   no_prior_declared=False)


def test_the_stop_rule_is_reached_through_the_shared_primitive():
    """It must be THE rule, not a second copy of it living in the runner."""
    import research.b0_materializer.l3_temporal_snapshot as TS

    assert R.assert_append_only_continuity is TS.assert_append_only_continuity

    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "assert_append_only_continuity"]
    assert calls, "the runner does not call the stop rule"


# --- S-2 · continuity compares DECISION SEMANTICS, not only source identity -------
#
# `raw_sha256` names the bytes. It says nothing about the declaration constants
# written beside them, and two of those decide what the bytes MEAN: `leg` picks
# the unit convention (成交量(千股) x1000 vs shares already), `roster_basis` says
# whether the archive can evidence delisted coverage. Neither is derivable from
# the rows -- `assert_declared_span.does_not_catch` says so in as many words --
# so an entry whose bytes and locator never moved could flip either one and pass
# an append-only check built on identity alone.

def _price_entry(locator="px.zip", sha="a" * 64, vintage="2026-08-17", **over):
    e = _source_entry(locator, sha, vintage, format="zip",
                      members=[{"name": "px.csv", "size": 10,
                                "crc32": "deadbeef"}],
                      leg="2019+", covers=["2019-01-02", "2026-08-17"],
                      roster_basis="BULK_HISTORICAL_QUERY")
    e.update(over)
    return e


def _continuity(tmp_path, before, after):
    base = _source_run(tmp_path, "L3-BASE", [before], dataset="prices")
    now = _source_run(tmp_path, "L3-NOW", [after], dataset="prices")
    return R.assert_source_continuity(
        now, prior_manifest=_baseline_manifest(base), no_prior_declared=False)


def test_the_projection_carries_the_fields_that_decide_what_the_bytes_MEAN():
    for field in ("leg", "roster_basis", "covers"):
        assert field in R.SOURCE_CONTINUITY_PROJECTED_FIELDS
    # and the deliberate exclusions stay excluded, each for a stated reason
    for field in ("observed_at", "members", "covers_verified",
                  "declared_properties", "landing_directory"):
        assert field not in R.SOURCE_CONTINUITY_PROJECTED_FIELDS


def test_a_leg_flip_on_unchanged_bytes_is_a_stop(tmp_path):
    """The 1000x one. Same locator, same `raw_sha256`, same vintage -- and
    `l3_readers` would send the archive down the other leg's unit convention,
    moving every security across §4.2's absolute NTD liquidity floor."""
    with pytest.raises(R.L3RunAbort) as exc:
        _continuity(tmp_path, _price_entry(), _price_entry(leg="pre-2019"))
    assert "HISTORICAL_SOURCE_REVISION" in str(exc.value)
    assert "prices" in str(exc.value)


def test_a_roster_basis_flip_on_unchanged_bytes_is_a_stop(tmp_path):
    """D1-6 survivorship, re-entering through a constant: an archive that
    cannot evidence delisted coverage, re-declared as one that can."""
    with pytest.raises(R.L3RunAbort, match="HISTORICAL_SOURCE_REVISION"):
        _continuity(tmp_path, _price_entry(),
                    _price_entry(roster_basis="CURRENT_ROSTER_SNAPSHOT"))


def test_a_re_declared_span_on_unchanged_bytes_is_a_stop(tmp_path):
    """S-9 re-measures `covers` in the CURRENT build. The baseline is a prior
    run's manifest, which a builder from before S-9 may have written -- so this
    rule does not assume another gate ran in a run it cannot inspect."""
    with pytest.raises(R.L3RunAbort, match="HISTORICAL_SOURCE_REVISION"):
        _continuity(tmp_path, _price_entry(),
                    _price_entry(covers=["2019-01-02", "2026-08-28"]))


def test_declaring_a_field_and_declaring_nothing_are_different_rows(tmp_path):
    """`leg` is None on a not_consumed workbook and absent on most families.
    Absence is a named marker, so 'no leg declared' and 'leg declared' cannot
    compare equal."""
    with pytest.raises(R.L3RunAbort, match="HISTORICAL_SOURCE_REVISION"):
        _continuity(tmp_path, _price_entry(leg=None), _price_entry())


def test_a_declared_value_may_not_spell_the_absence_marker(tmp_path):
    run = _source_run(tmp_path, "L3-MARKER",
                      [_price_entry(leg=R.SOURCE_CONTINUITY_ABSENT)],
                      dataset="prices")
    with pytest.raises(R.L3RunAbort, match="absence marker"):
        R.declared_source_rows(run)


def test_a_byte_derived_rendering_is_not_reported_as_a_source_revision(
        tmp_path):
    """`members` is DERIVED from the archive by the builder, so equal bytes
    entail an equal inventory. What a change there would signal is a change in
    the BUILDER -- a code fact the route seal owns -- and calling that a
    historical source revision would name the wrong failure."""
    got = _continuity(
        tmp_path, _price_entry(),
        _price_entry(members=[{"name": "px.csv", "size": 11,
                               "crc32": "deadbeef"}]))
    assert got["per_dataset"]["prices"]["status"] == "APPEND_ONLY"


def test_an_unchanged_declaration_still_appends_cleanly(tmp_path):
    """The projection must not turn every second run into a stop."""
    base = _source_run(tmp_path, "L3-BASE", [_price_entry()], dataset="prices")
    later = _source_run(
        tmp_path, "L3-LATER",
        [_price_entry(), _price_entry(locator="px2.zip", sha="b" * 64,
                                      vintage="2026-08-28")],
        dataset="prices")
    got = R.assert_source_continuity(later,
                                     prior_manifest=_baseline_manifest(base),
                                     no_prior_declared=False)
    assert got["per_dataset"]["prices"]["appended_rows"] == 1


# --- S-8 · an allowance earned by another reader is not this route's --------------
#
# The clip-based allowance was verified against `panel_end_session()` -- the L2
# composed panel's end. This route reads through the period's EXECUTION session
# and inherits no window, so the archive the panel clips away is read in full
# here. The leaf publishes who each allowance was checked for; this route reads
# its own name out of that list and refuses.

def _reconciliation(denied=(), *, scope=True, consumer=None):
    import build_prices_leaf as P

    key = P.CONSUMER_L3_PROSPECTIVE if consumer is None else consumer
    record = {"rule": "THE_DECLARED_ARCHIVE_SET_MUST_RECONCILE_WITH_THE_SEALED_CONTRACT",
              "sealed_contract_name": "b0_price_universe_20260817"}
    if scope:
        record["archives_denied_to_consumer"] = {
            P.CONSUMER_L2_PANEL: [], key: list(denied)}
    return {R.SOURCE_RECONCILIATION_POLICY: record}


def test_the_route_looks_itself_up_under_the_leafs_own_consumer_name():
    """Not a second copy of the string: a name that could drift would look
    itself up under a key nobody grants or denies."""
    import build_prices_leaf as P

    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name == "assert_declared_sources_admit_this_route")
    imported = {a.name for n in ast.walk(fn)
                if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "CONSUMER_L3_PROSPECTIVE" in imported
    assert P.CONSUMER_L3_PROSPECTIVE in P.LEAF_CONSUMERS


def test_a_route_may_not_read_an_archive_it_was_not_granted(tmp_path):
    """The defect, at the consumer that is actually at risk."""
    run = _source_run(tmp_path, "L3-DENIED", [_price_entry()], dataset="prices",
                      policies=_reconciliation(denied=["股價0817-0828.zip"]))
    with pytest.raises(R.L3RunAbort) as exc:
        R.assert_declared_sources_admit_this_route(run)
    assert "股價0817-0828.zip" in str(exc.value)
    assert "another consumer of the same leaf" in str(exc.value)
    assert "R-W1-1" in str(exc.value)


def test_a_leaf_that_never_considered_this_consumer_is_not_permission(tmp_path):
    run = _source_run(tmp_path, "L3-SILENT", [_price_entry()], dataset="prices",
                      policies=_reconciliation(consumer="SOMEBODY_ELSE"))
    with pytest.raises(R.L3RunAbort, match="Silence is not a grant"):
        R.assert_declared_sources_admit_this_route(run)


def test_a_reconciliation_without_a_consumer_scope_is_refused(tmp_path):
    """A record from before the scope existed says the allowance was checked
    for SOME reader, and this route is not necessarily that reader."""
    run = _source_run(tmp_path, "L3-OLD", [_price_entry()], dataset="prices",
                      policies=_reconciliation(scope=False))
    with pytest.raises(R.L3RunAbort, match="no `archives_denied_to_consumer`"):
        R.assert_declared_sources_admit_this_route(run)


def test_a_prices_leaf_must_reconcile_against_its_sealed_contract(tmp_path):
    """Deleting the record must remove the gate's SUBJECT, not the gate."""
    run = _source_run(tmp_path, "L3-NOPOLICY", [_price_entry()],
                      dataset="prices")
    with pytest.raises(R.L3RunAbort, match="carries no `sealed_source"):
        R.assert_declared_sources_admit_this_route(run)


def test_a_family_with_no_sealed_contract_needs_no_reconciliation(tmp_path):
    """Only prices has one today. The positive half, so the gate is not simply
    'always abort'."""
    run = _source_run(tmp_path, "L3-CAL",
                      [_source_entry("taiex.parquet", "a" * 64, "2026-08-17")])
    got = R.assert_declared_sources_admit_this_route(run)
    assert got["datasets_with_a_reconciliation_record"] == []
    assert got["archives_refused_to_this_route"] == {}


def test_a_route_that_is_granted_everything_it_declares_proceeds(tmp_path):
    run = _source_run(tmp_path, "L3-OK", [_price_entry()], dataset="prices",
                      policies=_reconciliation())
    got = R.assert_declared_sources_admit_this_route(run)
    assert got["datasets_with_a_reconciliation_record"] == ["prices"]
    assert got["consumer"] == "L3_PROSPECTIVE_ROUTE"


def test_the_admission_gate_is_reached_from_preflight_and_from_provenance():
    """A gate whose passage is not recorded is a gate nobody can audit later."""
    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    reached = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        if any(isinstance(n, ast.Call)
               and getattr(n.func, "id", "")
               == "assert_declared_sources_admit_this_route"
               for n in ast.walk(fn)):
            reached.add(fn.name)
    assert {"preflight", "_provenance"} <= reached


def test_a_continuation_may_not_declare_that_it_has_no_source_baseline(tmp_path):
    """A CONTINUATION has a preceding run by definition."""
    args = R.build_parser().parse_args([
        "--mode", "assemble", "--run-id", "L3-0000000000000009",
        "--decision-date", "2026-10-30", "--authorization", "ref",
        "--opening-checkpoint", str(tmp_path / "cp.jsonl"),
        "--opening-kind", "CONTINUATION", "--lineage-cohort", "L3_PRIMARY_20M",
        "--run-dir", str(tmp_path), "--no-prior-source-manifest"])

    with pytest.raises(R.L3RunAbort, match="GENESIS-only declaration"):
        R.preflight(args)


# --- S-5 · decision and lineage records are claimed exclusively --------------------

def test_a_decision_record_may_not_be_overwritten(tmp_path):
    """`write_provenance_json` opens "wb", which truncates without saying so."""
    path = str(tmp_path / R.DECISION_INTENT)

    R.write_decision_record(path, {"record": "FIRST"})
    with pytest.raises(R.L3RunAbort, match="claimed exclusively"):
        R.write_decision_record(path, {"record": "SECOND"})

    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["record"] == "FIRST"


def test_the_exclusive_claim_does_not_change_the_recorded_bytes(tmp_path):
    """Exclusivity is a claim AROUND the provenance primitive, not a rewrite."""
    payload = {"record": "B0_L3_DECISION_INTENT", "run_id": "L3-1",
               "nested": {"b": 2, "a": [1, 2, 3]}}
    a = str(tmp_path / "overwrite.json")
    b = str(tmp_path / "exclusive.json")

    R.write_provenance_json(a, payload)
    R.write_decision_record(b, payload)

    assert open(a, "rb").read() == open(b, "rb").read()


def test_every_decision_record_in_the_runner_is_claimed_exclusively():
    """The wiring half: one missed call site is one overwritable record."""
    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    overwrites = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "write_provenance_json"):
            continue
        # the single legitimate one is inside write_decision_record itself,
        # which has already claimed the path with O_EXCL
        parents = [f for f in ast.walk(tree)
                   if isinstance(f, ast.FunctionDef)
                   and any(n is node for n in ast.walk(f))]
        if any(f.name == "write_decision_record" for f in parents):
            continue
        overwrites.append(node.lineno)
    assert not overwrites, (
        "record(s) at line(s) %s are written with overwrite semantics" % overwrites)


# --- S-6 · an unobtainable repo identity is a stop, not an empty string ------------

def test_the_repo_identity_is_a_stop_when_git_cannot_be_reached(monkeypatch):
    def _boom(*a, **k):
        raise OSError("git not found")

    monkeypatch.setattr(R.subprocess, "run", _boom)
    with pytest.raises(R.L3RunAbort, match="not an empty string"):
        R.repo_commit_sha()


def test_the_repo_identity_is_a_stop_when_git_fails(monkeypatch):
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="", stderr="fatal: not a git repository", returncode=128))
    with pytest.raises(R.L3RunAbort, match="exited 128"):
        R.repo_commit_sha()


def test_the_repo_identity_must_look_like_a_commit(monkeypatch):
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="HEAD\n", stderr="", returncode=0))
    with pytest.raises(R.L3RunAbort, match="not a 40-hex commit sha"):
        R.repo_commit_sha()


def test_the_repo_identity_resolves_in_this_working_tree():
    """The positive half: the stop must not be unconditional."""
    sha = R.repo_commit_sha()
    assert len(sha) == 40 and set(sha) <= set("0123456789abcdef")


# --- run-directory discipline -----------------------------------------------------------

def test_the_runner_never_claims_a_run_directory(tmp_path, monkeypatch):
    """W7B5: only `create_run_dir` may claim one."""
    monkeypatch.setattr(layout, "RUNS_ROOT", str(tmp_path / "runs"))

    with pytest.raises(layout.RunDirectoryMissing):
        R.resolve_run_directory("L3-0000000000000009")
    assert not os.path.exists(str(tmp_path / "runs"))


def test_an_explicit_run_dir_must_already_exist(tmp_path):
    with pytest.raises(R.L3RunAbort):
        R.resolve_run_directory("L3-0000000000000009",
                                str(tmp_path / "nope"))

    real = tmp_path / "here"
    real.mkdir()
    assert R.resolve_run_directory("L3-0000000000000009", str(real)) \
        == os.path.abspath(str(real))


def test_an_explicit_run_dir_inside_the_l3_tree_is_still_guarded(tmp_path,
                                                                monkeypatch):
    """A path handed in by a caller may not become a back door into the tree."""
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(layout, "RUNS_ROOT", str(runs))

    with pytest.raises(layout.RunDirectoryMissing):
        R.resolve_run_directory("L3-0000000000000009",
                                str(runs / "L3-0000000000000009"))


# --- the harness's own declarations ---------------------------------------------------------

def test_preflight_requires_a_named_authorization(tmp_path):
    args = R.build_parser().parse_args([
        "--run-id", "L3-0000000000000009",
        "--decision-date", "2026-04-30",
        "--authorization", "   ",
        "--opening-checkpoint", str(tmp_path / "cp.jsonl"),
        "--opening-kind", "GENESIS",
        "--run-dir", str(tmp_path)])

    with pytest.raises(R.L3RunAbort) as exc:
        R.preflight(args)
    assert "authorization" in str(exc.value)


def test_the_default_mode_is_the_one_that_writes_nothing():
    args = R.build_parser().parse_args([
        "--run-id", "L3-1", "--decision-date", "2026-04-30",
        "--authorization", "ref", "--opening-checkpoint", "cp.jsonl",
        "--opening-kind", "CONTINUATION"])
    assert args.mode == "preflight"
    assert args.sealed_evidence is None       # no default, by design


def test_sealed_evidence_has_no_default_and_must_be_declared():
    parser = R.build_parser()
    assert parser.parse_args([
        "--run-id", "L3-1", "--decision-date", "2026-04-30",
        "--authorization", "r", "--opening-checkpoint", "c",
        "--opening-kind", "GENESIS", "--sealed-evidence"]).sealed_evidence is True
    assert parser.parse_args([
        "--run-id", "L3-1", "--decision-date", "2026-04-30",
        "--authorization", "r", "--opening-checkpoint", "c",
        "--opening-kind", "GENESIS", "--no-sealed-evidence"]).sealed_evidence is False


def test_the_runner_binds_its_own_bytes_and_its_own_path():
    assert R.HARNESS_PATH == "research/b0_l3_runner/run_l3_prospective.py"
    assert os.path.exists(os.path.join(REPO, R.HARNESS_PATH))
    from core.b0_canonical_hash import file_sha256

    assert file_sha256(os.path.join(REPO, R.HARNESS_PATH)) == _sha(R.__file__)
