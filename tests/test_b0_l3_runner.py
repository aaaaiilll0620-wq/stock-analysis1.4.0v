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


def test_genesis_cash_is_bound_to_a_named_prospective_cohort():
    good = SimpleNamespace(
        opening_kind="GENESIS", genesis_cohort="L3_PRIMARY_20M",
        c_ref=20_000_000.0, synthetic_sources=False)
    assert R._assert_genesis_cohort(good)["opening_cash"] == 20_000_000.0

    with pytest.raises(R.L3RunAbort, match="requires opening cash"):
        R._assert_genesis_cohort(SimpleNamespace(
            opening_kind="GENESIS", genesis_cohort="L3_PRIMARY_20M",
            c_ref=2_000_000.0, synthetic_sources=False))
    with pytest.raises(R.L3RunAbort, match="fixture-only"):
        R._assert_genesis_cohort(SimpleNamespace(
            opening_kind="GENESIS",
            genesis_cohort=R.SYNTHETIC_PARITY_COHORT,
            c_ref=2_000_000.0, synthetic_sources=False))


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
