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
    """A list nobody derived is a list nobody checked."""
    extra = os.path.join(REPO, "research", "b0_materializer",
                         "build_zzz_probe_leaf.py")
    try:
        with open(extra, "w", encoding="utf-8") as fh:
            fh.write("# probe\n")
        assert "research/b0_materializer/build_zzz_probe_leaf.py" \
            in rs.source_producer_files()
    finally:
        if os.path.exists(extra):
            os.remove(extra)


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
    with pytest.raises(rs.RouteSealError) as exc:
        rs.load_route_seal("L3SEAL-" + "f" * 64)
    assert "no 'latest'" in str(exc.value)


def test_a_tampered_seal_file_is_refused(tmp_path, monkeypatch, sealable):
    monkeypatch.setattr(rs, "SEAL_ROOT", str(tmp_path))
    ident = rs.route_seal_id(sealable)
    payload = {**sealable, "route_seal_id": ident,
               "route_seal_payload_sha256": ident[7:]}
    path = os.path.join(str(tmp_path), ident + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    assert rs.load_route_seal(ident)["route_seal_id"] == ident

    payload["file_count"] = payload["file_count"] + 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    with pytest.raises(rs.RouteSealError) as exc:
        rs.load_route_seal(ident)
    assert "altered since it was taken" in str(exc.value)


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
