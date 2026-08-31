# -*- coding: utf-8 -*-
"""A2 · the seal must cover the whole replayable route, not the decision core.

`route_closure.production_route_code_closure()` walks `core.*` from the two
adapter entry points. Everything between a declared source file and
`run_decision` sits outside it, and a gate that stopped there would let the
first prospective observation bind the code that DECIDES while leaving unbound
every line that decides what it SEES.

These tests are about the three holes that made that possible:

  * the closure was core-only;
  * `route_closure` declares items still owed before a seal may be taken, and
    nothing read that declaration;
  * `source_ownership_manifest` requires `route_seal_id` to be non-empty and
    checks nothing else, so the literal string `PENDING` was a valid identity.
"""
from __future__ import annotations

import ast
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

import l3_route_seal as rs                                          # noqa: E402
import run_l3_prospective as R                                      # noqa: E402
from route_closure import production_route_code_closure             # noqa: E402


# --- the closure is wider than the decision core ------------------------------------

def test_the_route_closure_reaches_the_whole_prospective_route():
    files = set(rs.route_closure_files())

    for expected in (
            "research/b0_l3_runner/run_l3_prospective.py",
            "research/b0_checkpoint/portfolio_side.py",
            "research/b0_checkpoint/portfolio_checkpoint.py",
            "research/b0_l3/l3_assemble.py",
            "research/b0_l3/l3_readers.py",
            "research/b0_l3/l3_snapshot.py",
            "research/b0_l3/route_closure.py",
            "research/b0_materializer/source_ownership_manifest.py",
            "core/b0_l3_run_layout.py",
            "core/b0_route.py",
            "core/b0_adapter_production.py"):
        assert expected in files, expected


def test_the_route_closure_is_strictly_wider_than_the_core_closure():
    """The gap is the point: it is every line the core closure never bound."""
    core = {"core/%s.py" % m for m in production_route_code_closure()}
    files = set(rs.route_closure_files())

    assert core < files
    added = sorted(files - core)
    assert added, "the route closure adds nothing to the core closure"
    # It adds two kinds of file, and both are the point. Research-layer code is
    # the obvious one; the less obvious one is that the route reaches CORE
    # modules the decision closure never does -- run storage and the opening
    # state contract are part of a replayable route and of no decision.
    assert any(p.startswith("research/") for p in added)
    assert "core/b0_l3_run_layout.py" in added
    for path in added:
        assert os.path.isfile(os.path.join(REPO, path)), path


def test_the_producers_are_bound_even_though_no_import_reaches_them():
    """A run CONSUMES leaves; the code that built them is reached by nothing."""
    derived = set(rs.route_closure_files())
    producers = set(rs.source_producer_files())
    sealed = set(rs.sealed_file_set())

    assert producers, "no leaf producers found on disk"
    assert producers - derived, (
        "a producer is now imported by the route; this test's premise moved")
    assert producers <= sealed
    assert derived <= sealed


def test_a_producer_outside_the_sealed_set_is_refused():
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_no_producer_is_unbound(rs.route_closure_files())
    assert "source producer" in str(exc.value)


def test_the_producer_set_is_read_from_disk_not_hand_listed(tmp_path,
                                                            monkeypatch):
    """A list nobody derived is a list nobody checked.

    Read off a SYNTHETIC tree, never by writing into this one. The original
    created research/b0_materializer/build_zzz_probe_leaf.py inside the repo and
    removed it in a `finally`, and that path is inside `sealed_file_set()`: a run
    that died between the two -- SIGKILL, power loss, or a sandbox that denies
    the removal -- left behind a producer file the closure reaches and no seal
    ever bound, which is exactly the state `assert_seal_binds_current_route`
    refuses. It also made this file unrunnable wherever the tree is read-only,
    which is where an independent reviewer runs it: measured, 7 PermissionError
    failures and no assertion failures.

    Both halves of the property are still checked, and the real-tree half is
    checked FIRST so a broken glob cannot hide behind the synthetic one.
    """
    assert "research/b0_materializer/build_prices_leaf.py" \
        in rs.source_producer_files(), "the globs no longer reach the real tree"

    materializer = tmp_path / "research" / "b0_materializer"
    materializer.mkdir(parents=True)
    (materializer / "build_zzz_probe_leaf.py").write_text(
        "# probe\n", encoding="utf-8")
    monkeypatch.setattr(rs, "REPO", str(tmp_path))

    assert "research/b0_materializer/build_zzz_probe_leaf.py" \
        in rs.source_producer_files()


# --- the route's own "still owed" declaration ------------------------------------------

def test_sealability_is_read_from_route_closure_not_restated():
    """A copy of that list would go stale in the direction that matters."""
    from route_closure import seal_payload

    owed = list(seal_payload().get("still_owed_before_a_seal_may_be_taken") or ())
    if owed:
        with pytest.raises(rs.RouteSealError) as exc:
            rs.assert_route_is_sealable()
        message = str(exc.value)
        assert "route_closure.py" in message
        # the refusal quotes the route's own words rather than paraphrasing
        assert str(owed[0])[:40] in message
    else:
        payload = rs.assert_route_is_sealable()
        assert payload["code_closure_size"] > 0


def test_the_runner_gate_refuses_while_anything_is_owed():
    from route_closure import seal_payload

    owed = list(seal_payload().get("still_owed_before_a_seal_may_be_taken") or ())
    if not owed:
        pytest.skip("route_closure now declares nothing owed")
    with pytest.raises(rs.RouteSealError):
        rs.route_seal_payload("not-reached.json")


# --- placeholder route_seal_ids ---------------------------------------------------------

@pytest.mark.parametrize("declared", ["", "   ", "PENDING", "pending", "TBD",
                                      "none", "PLACEHOLDER", "-"])
def test_a_placeholder_route_seal_id_names_no_route(declared):
    """`assemble_aggregate` only requires it to be non-empty, so it gets here."""
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_aggregate_names_this_seal({"route_seal_id": declared},
                                            "a" * 64)
    assert "names no route" in str(exc.value)


def test_a_source_set_harvested_against_another_seal_is_refused():
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_aggregate_names_this_seal({"route_seal_id": "b" * 64},
                                            "a" * 64)
    assert "never tied to" in str(exc.value)


def test_the_matching_seal_id_is_accepted():
    assert rs.assert_aggregate_names_this_seal(
        {"route_seal_id": "a" * 64}, "a" * 64) == "a" * 64


def test_the_fixture_route_seal_id_used_everywhere_is_a_placeholder():
    """`PENDING` is what every harvest and every fixture writes today."""
    assert "PENDING" in rs.PLACEHOLDER_SEAL_IDS


# --- verifying a seal against the working tree --------------------------------------------

@pytest.fixture()
def sealable(monkeypatch):
    """Pretend `route_closure` has cleared its owed list, and nothing else."""
    monkeypatch.setattr(rs, "assert_route_is_sealable",
                        lambda: {"code_closure_size": len(
                            production_route_code_closure())})
    monkeypatch.setattr(rs, "verified_capture_binding", lambda path: {
        "lineage_id": "L3-" + "1" * 64,
        "capture_run_id": "L3-FLOOR-CAPTURE-20260829-A02",
        "capture_as_of": "2026-08-29",
        "lineage_price_floor": "2004-02-11",
        "capture_record_payload_sha256": "2" * 64,
        "capture_record_raw_sha256": "3" * 64,
    })
    monkeypatch.setattr(rs, "current_repo_identity", lambda: {
        "repo_commit_sha": "4" * 40,
        "tracked_tree_sha256": "5" * 64,
        "tracked_clean": True,
        "untracked_clean": True,
        "untracked_inventory_sha256": "6" * 64,
    })
    return rs.route_seal_payload("capture.json")


def test_a_seal_over_the_current_tree_verifies(sealable):
    verified = rs.assert_seal_binds_current_route(sealable)
    assert verified["verified_files"] == len(sealable["files"])
    assert verified["sealed_but_no_longer_reached"] == []


def test_a_changed_file_is_refused(sealable):
    tampered = {**sealable,
                "files": {**sealable["files"], "core/b0_route.py": "0" * 64}}
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_seal_binds_current_route(tampered)
    assert "changed since the seal" in str(exc.value)


def test_a_file_the_route_now_reaches_and_the_seal_never_bound_is_refused(
        sealable):
    """The direction that looks like nothing happened."""
    files = dict(sealable["files"])
    files.pop("research/b0_checkpoint/portfolio_side.py")
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_seal_binds_current_route(
            {**sealable, "files": files, "file_count": len(files)})
    assert "never sealed" in str(exc.value)


def test_a_file_sealed_but_no_longer_reached_is_refused(
        sealable, monkeypatch):
    current = tuple(p for p in rs.sealed_file_set()
                    if p != "research/b0_checkpoint/portfolio_side.py")
    monkeypatch.setattr(rs, "sealed_file_set", lambda: current)
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_seal_binds_current_route(sealable)
    assert "sealed but no longer reached" in str(exc.value)


def test_a_seal_from_another_contract_version_is_refused(sealable):
    with pytest.raises(rs.RouteSealError):
        rs.assert_seal_binds_current_route(
            {**sealable, "contract_version": "b0_l3_route_seal@0"})


def test_the_seal_id_is_content_addressed(sealable):
    ident = rs.route_seal_id(sealable)
    assert ident.startswith("L3SEAL-") and len(ident) == 71
    # adding the id to the payload must not move the id
    assert rs.route_seal_id({**sealable, "route_seal_id": ident,
                             "route_seal_payload_sha256": ident[7:],
                             "route_seal_raw_sha256": "9" * 64}) == ident
    # changing any bound file does move it
    moved = {**sealable,
             "files": {**sealable["files"], "core/b0_route.py": "0" * 64}}
    assert rs.route_seal_id(moved) != ident


def test_loading_a_seal_that_does_not_exist_names_no_fallback():
    """MECHANISM (Master 9.6e(b)): `read_seal_artifact`, not `load_route_seal`.

    `load_route_seal` is now the ratification-gated boundary and refuses before
    it looks at any path (P1-8), so a test of well-formedness has to call the
    mechanism directly. The alternative -- widening the gate so the mechanism
    stays reachable through it -- is what C-72 refused: a guard that a test may
    walk around has stopped being a guard. The assertions are unchanged.
    """
    with pytest.raises(rs.RouteSealError) as exc:
        rs.read_seal_artifact("L3SEAL-" + "f" * 64)
    assert "no 'latest'" in str(exc.value)


def test_a_tampered_seal_file_is_refused(tmp_path, monkeypatch, sealable):
    """MECHANISM: see `test_loading_a_seal_that_does_not_exist_names_no_fallback`."""
    monkeypatch.setattr(rs, "SEAL_ROOT", str(tmp_path))
    ident = rs.route_seal_id(sealable)
    payload = {**sealable, "route_seal_id": ident,
               "route_seal_payload_sha256": ident[7:]}
    path = os.path.join(str(tmp_path), ident + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    assert rs.read_seal_artifact(ident)["route_seal_id"] == ident

    payload["file_count"] = payload["file_count"] + 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    with pytest.raises(rs.RouteSealError) as exc:
        rs.read_seal_artifact(ident)
    assert "altered since it was taken" in str(exc.value)


# --- P1-8 - ratification protects the writer, and nobody has to be the writer ---

def _hand_crafted_seal(tmp_path, monkeypatch, sealable) -> tuple:
    """A seal file nobody was authorised to take, internally self-consistent.

    Exactly the artefact the review described: written by hand rather than by
    the (deliberately unreachable) writer, hashing to its own filename, with a
    source aggregate that names it.
    """
    monkeypatch.setattr(rs, "SEAL_ROOT", str(tmp_path))
    ident = rs.route_seal_id(sealable)
    seal = {**sealable, "route_seal_id": ident,
            "route_seal_payload_sha256": ident[7:]}
    with open(os.path.join(str(tmp_path), ident + ".json"), "w",
              encoding="utf-8") as fh:
        json.dump(seal, fh)
    return ident, seal


def test_the_hand_crafted_seal_really_is_internally_self_consistent(
        tmp_path, monkeypatch, sealable):
    """The premise of the defect, pinned: nothing is WRONG with this file.

    If this stopped holding, the refusal below would start passing for the
    wrong reason -- a malformed seal -- and would no longer be evidence that
    ratification is what refuses it.
    """
    ident, seal = _hand_crafted_seal(tmp_path, monkeypatch, sealable)

    assert rs.read_seal_artifact(ident)["route_seal_id"] == ident
    assert rs.assert_seal_binds_current_route(seal)["verified_files"] > 0
    assert rs.assert_aggregate_names_this_seal(
        {"route_seal_id": ident}, ident) == ident
    assert rs.route_seal_receipt_fields(
        seal, raw_sha256="d" * 64)["route_seal_id"] == ident


def test_a_self_consistent_seal_is_refused_while_the_contract_is_unratified(
        tmp_path, monkeypatch, sealable):
    """P1-8. The consumer door was never asked, and now it is."""
    from core.b0_l3_lineage_capture import ROUTE_SEAL_CONTRACT_STATUS

    assert ROUTE_SEAL_CONTRACT_STATUS != rs.RATIFIED_ROUTE_SEAL_CONTRACT_STATUS
    ident, _ = _hand_crafted_seal(tmp_path, monkeypatch, sealable)

    with pytest.raises(rs.RouteSealError) as exc:
        rs.load_route_seal(ident)
    assert ROUTE_SEAL_CONTRACT_STATUS in str(exc.value)


def _first_statement_calls(module_path: str, function: str, callee: str) -> bool:
    """Does `function`'s FIRST executable statement call `callee`?

    Ordering, not presence. C-72 ruled the refusal must happen BEFORE the
    boundary does anything -- "the refusal must occur before the seal is
    obtained, because once obtained it is already a fact in the ledger" -- so a
    guard called somewhere in the body would not satisfy it.
    """
    tree = ast.parse(open(module_path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and \
                isinstance(body[0].value, ast.Constant) and \
                isinstance(body[0].value.value, str):
            body = body[1:]                      # the docstring
        if not body:
            return False
        first = body[0]
        for sub in ast.walk(first):
            if isinstance(sub, ast.Call):
                func = sub.func
                name = (func.attr if isinstance(func, ast.Attribute)
                        else getattr(func, "id", ""))
                if name == callee:
                    return True
        return False
    raise AssertionError("%s defines no %s" % (module_path, function))


@pytest.mark.parametrize("boundary", rs.RATIFICATION_GATED_BOUNDARIES)
def test_every_gated_boundary_asks_the_gate_first(boundary):
    """AST, not a comment: both seal doors ask ratification before anything."""
    assert _first_statement_calls(rs.__file__, boundary,
                                  "assert_route_seal_contract_ratified"), \
        "%s does not ask the ratification gate first" % boundary


def test_the_declared_boundaries_are_the_boundaries_that_exist():
    """A boundary list that drifted from the module would gate nothing."""
    assert set(rs.RATIFICATION_GATED_BOUNDARIES) == {"write_route_seal",
                                                     "load_route_seal"}
    for name in rs.RATIFICATION_GATED_BOUNDARIES:
        assert callable(getattr(rs, name)), name


def test_the_execution_boundary_asks_the_gate_before_anything_else():
    """C-72(c): the gate belongs at the REAL boundary, not only in the API."""
    assert _first_statement_calls(R.__file__,
                                  "assert_route_execution_admissible",
                                  "assert_route_seal_contract_ratified")


def test_the_runner_execution_gate_refuses_a_self_consistent_seal(
        tmp_path, monkeypatch, sealable):
    """End of the chain: the run cannot be admitted on a hand-written seal."""
    from core.b0_l3_lineage_capture import ROUTE_SEAL_CONTRACT_STATUS

    ident, _ = _hand_crafted_seal(tmp_path, monkeypatch, sealable)
    with pytest.raises(R.L3RunAbort) as exc:
        R.assert_route_execution_admissible({"route_seal_id": ident}, ident,
                                            "2004-02-11")
    assert R.ROUTE_EXECUTION_GATE in str(exc.value)
    assert ROUTE_SEAL_CONTRACT_STATUS in str(exc.value)


# --- P1-7 - the seal binds the floor the runner assembles on -------------------

def test_a_floor_that_disagrees_with_the_capture_is_refused(sealable):
    """The captured floor is 2004-02-11; one session away is another universe."""
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_declared_floor_is_the_captured_floor(sealable, "2004-02-12")
    message = str(exc.value)
    assert "2004-02-12" in message and "2004-02-11" in message
    assert "spell_start" in message


def test_the_captured_floor_is_the_only_floor_accepted(sealable):
    assert rs.assert_declared_floor_is_the_captured_floor(
        sealable, "2004-02-11") == "2004-02-11"


def test_an_undeclared_floor_is_refused_rather_than_defaulted(sealable):
    """C-68 has no default, and the seal may not supply one silently."""
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_declared_floor_is_the_captured_floor(sealable, "")
    assert "no default" in str(exc.value)


def test_a_seal_carrying_no_floor_admits_nothing(sealable):
    stripped = {k: v for k, v in sealable.items()
                if k != "lineage_price_floor"}
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_declared_floor_is_the_captured_floor(stripped, "2004-02-11")
    assert "no lineage_price_floor" in str(exc.value)


def test_the_execution_gate_cross_checks_the_declared_floor():
    """The gate must CALL the cross-check; a mechanism nobody calls is P1-7."""
    source = open(R.__file__, encoding="utf-8").read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and \
                node.name == "assert_route_execution_admissible":
            called = {n.func.attr for n in ast.walk(node)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute)}
            assert "assert_declared_floor_is_the_captured_floor" in called
            return
    raise AssertionError("the execution gate is gone")


def test_the_gate_passes_the_CALLERS_floor_to_the_cross_check():
    """Presence is not wiring, and only presence was pinned.

    Mutation that motivated this: keep the call exactly as the test above
    requires and pass `seal.get("lineage_price_floor")` in place of the callers
    argument. The cross-check then compares the seal with itself, every
    `--lineage-price-floor` is accepted whatever the capture said, and the whole
    scope stayed green. The gate is reachable only once A-1 ratifies the
    contract, so the wiring is pinned here rather than exercised.
    """
    tree = ast.parse(open(R.__file__, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "assert_route_execution_admissible"):
            continue
        for call in ast.walk(node):
            if not (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr
                    == "assert_declared_floor_is_the_captured_floor"):
                continue
            assert len(call.args) == 2, "the cross-check takes (seal, declared)"
            declared = call.args[1]
            assert isinstance(declared, ast.Name), (
                "the declared floor must be the gate own parameter; a value "
                "read back out of the seal compares the seal with itself")
            assert declared.id == "lineage_price_floor"
            return
        raise AssertionError("the gate does not call the cross-check")
    raise AssertionError("the execution gate is gone")


def test_a_receipt_binding_refuses_a_floor_the_seal_did_not_capture(
        tmp_path, monkeypatch, sealable):
    """The one floor path that is REACHABLE while the contract is unratified.

    `assert_route_execution_admissible` refuses on ratification before it can
    reach its floor cross-check, so no behavioural test could stand there. This
    one can: `route_seal_binding` is what puts the binding into every receipt,
    and with ratification simulated it exercises the same cross-check on the
    same two values.
    """
    import core.b0_l3_lineage_capture as lcap
    from types import SimpleNamespace

    ident, _ = _hand_crafted_seal(tmp_path, monkeypatch, sealable)
    monkeypatch.setattr(lcap, "ROUTE_SEAL_CONTRACT_STATUS",
                        rs.RATIFIED_ROUTE_SEAL_CONTRACT_STATUS)

    agreed = R.route_seal_binding(SimpleNamespace(
        mode="intent", route_seal_id=ident, lineage_price_floor="2004-02-11"))
    assert agreed["lineage_price_floor"] == "2004-02-11"
    assert agreed["lineage_price_floor_bound_by_a_capture"] is True

    with pytest.raises(R.L3RunAbort) as exc:
        R.route_seal_binding(SimpleNamespace(
            mode="intent", route_seal_id=ident,
            lineage_price_floor="2004-02-12"))
    assert "2004-02-12" in str(exc.value)


def test_the_receipt_fields_now_have_a_production_caller():
    """They existed to be published and were in no receipt at all."""
    source = open(R.__file__, encoding="utf-8").read()
    called = {n.func.attr for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "route_seal_receipt_fields" in called


def test_an_unsealed_mode_records_that_the_floor_was_never_bound():
    """An absent field and an unbound floor look identical in an audit."""
    from types import SimpleNamespace

    binding = R.route_seal_binding(SimpleNamespace(
        mode="assemble", route_seal_id="", lineage_price_floor="2004-02-11"))

    assert binding["route_seal_in_force"] is False
    assert binding["lineage_price_floor_bound_by_a_capture"] is False
    assert binding["declared_lineage_price_floor"] == "2004-02-11"
    assert binding["reason"] == R.NO_ROUTE_SEAL_IN_FORCE


def test_a_decision_mode_cannot_produce_a_binding_while_unratified(
        tmp_path, monkeypatch, sealable):
    """The receipt path goes through the same gated door as the run gate."""
    from types import SimpleNamespace

    from core.b0_l3_lineage_capture import ROUTE_SEAL_CONTRACT_STATUS

    ident, _ = _hand_crafted_seal(tmp_path, monkeypatch, sealable)
    with pytest.raises(R.L3RunAbort) as exc:
        R.route_seal_binding(SimpleNamespace(
            mode="intent", route_seal_id=ident,
            lineage_price_floor="2004-02-11"))
    assert ROUTE_SEAL_CONTRACT_STATUS in str(exc.value)


def test_capture_binding_is_verified_not_copied(monkeypatch):
    from core import b0_l3_lineage_capture as capture

    monkeypatch.setattr(capture, "load_and_verify_capture_record", lambda path: {
        "record": {
            "lineage_id": "L3-" + "a" * 64,
            "capture_run_id": "L3-FLOOR-CAPTURE-20260829-A02",
            "as_of": "2026-08-29",
            "lineage_price_floor": "2004-02-11",
        },
        "payload_sha256": "b" * 64,
        "raw_sha256": "c" * 64,
    })
    bound = rs.verified_capture_binding("verified.json")
    assert bound == {
        "lineage_id": "L3-" + "a" * 64,
        "capture_run_id": "L3-FLOOR-CAPTURE-20260829-A02",
        "capture_as_of": "2026-08-29",
        "lineage_price_floor": "2004-02-11",
        "capture_record_payload_sha256": "b" * 64,
        "capture_record_raw_sha256": "c" * 64,
    }


def test_actual_seal_creation_is_fail_closed_before_any_write(
        tmp_path, monkeypatch):
    target = tmp_path / "must-not-exist"
    monkeypatch.setattr(rs, "SEAL_ROOT", str(target))
    with pytest.raises(rs.RouteSealError) as exc:
        rs.write_route_seal("not-even-inspected.json")
    assert "NOT_YET_RATIFIED" in str(exc.value)
    assert not target.exists()


def test_empty_route_closure_cannot_be_sealed(monkeypatch):
    monkeypatch.setattr(rs, "assert_route_is_sealable",
                        lambda: {"code_closure_size": 1})
    monkeypatch.setattr(rs, "sealed_file_set", lambda: ())
    with pytest.raises(rs.RouteSealError) as exc:
        rs.route_seal_payload("not-reached.json")
    assert "empty" in str(exc.value)


def test_period_receipt_fields_bind_capture_route_and_repo(sealable):
    ident = rs.route_seal_id(sealable)
    seal = {**sealable, "route_seal_id": ident,
            "route_seal_payload_sha256": ident[7:]}
    fields = rs.route_seal_receipt_fields(seal, raw_sha256="d" * 64)
    assert fields["lineage_id"] == sealable["lineage_id"]
    assert fields["capture_record_payload_sha256"] == "2" * 64
    assert fields["capture_record_raw_sha256"] == "3" * 64
    assert fields["route_seal_id"] == ident
    assert fields["route_seal_payload_sha256"] == ident[7:]
    assert fields["route_seal_raw_sha256"] == "d" * 64
    assert fields["route_repo_commit_sha"] == "4" * 40
    assert fields["route_tracked_tree_sha256"] == "5" * 64


# --- taking a seal is never a side effect ----------------------------------------------------

def test_the_runner_never_takes_a_route_seal():
    """`write_route_seal` must be unreachable from any runner mode."""
    source = open(R.__file__, encoding="utf-8").read()
    tree = ast.parse(source)
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                called.add(func.attr)
            elif isinstance(func, ast.Name):
                called.add(func.id)

    assert "write_route_seal" not in called
    assert "write_route_seal" not in source
