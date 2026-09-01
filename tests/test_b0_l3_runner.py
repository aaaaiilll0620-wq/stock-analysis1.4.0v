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


def test_a_route_seal_id_supplied_to_a_mode_that_ignores_it_is_refused(tmp_path):
    """Only `--mode execute` reaches the seal gate.

    Outside it the id was recorded in `_provenance` while `S.build_receipt`
    fell back to the aggregate's own `route_seal_id`, so one run could name two
    different seals with nothing raising. Same rule `resolve_spans` states for
    span endpoints: an ignored argument is a decision input the caller believes
    it supplied.
    """
    args = R.build_parser().parse_args([
        "--run-id", "L3-0000000000000009",
        "--decision-date", "2026-04-30",
        "--authorization", "ref",
        "--mode", "assemble",
        "--route-seal-id", "a" * 64,
        "--opening-checkpoint", str(tmp_path / "cp.jsonl"),
        "--opening-kind", "GENESIS",
        "--run-dir", str(tmp_path)])

    with pytest.raises(R.L3RunAbort) as exc:
        R.preflight(args)
    assert "--route-seal-id is an execute-mode input" in str(exc.value)


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
