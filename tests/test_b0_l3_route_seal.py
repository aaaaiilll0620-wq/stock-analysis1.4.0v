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

    The probe leaf is created under `tmp_path` with `rs.REPO` pointed at it,
    NEVER inside the real repository: `SOURCE_PRODUCER_GLOBS` matches
    `build_*_leaf.py`, so a probe written into `research/b0_materializer/`
    joins `sealed_file_set()` and changes every `route_seal_id` computed while
    it exists. A `finally` does not make that safe -- a hard interrupt during
    the write leaves the file behind, and it also dirties `git status`, which
    `core.b0_diagnostic_iteration.changed_files` reads.
    """
    landing = tmp_path / "research" / "b0_materializer"
    landing.mkdir(parents=True)
    (landing / "build_zzz_probe_leaf.py").write_text("# probe\n",
                                                     encoding="utf-8")
    monkeypatch.setattr(rs, "REPO", str(tmp_path))
    assert "research/b0_materializer/build_zzz_probe_leaf.py" \
        in rs.source_producer_files()


# --- A-1c · the sealed retrospective line is not a root, and escapes are refused -------

def test_b0_l2_is_not_a_module_root():
    """A-1c, ruled 2026-09-02. It contributed 0 of the 45 files, so this is not
    about a file: a root means a FUTURE import into the sealed retrospective
    line joins the prospective route's identity without anyone deciding it."""
    assert not any("b0_l2" in r for r in rs.MODULE_ROOTS)
    assert not any(f.startswith("research/b0_l2") for f in rs.sealed_file_set())


def test_a_repo_module_outside_the_roots_is_refused_not_skipped():
    """Dropping the root alone only reverses which way the silence runs."""
    entry = os.path.join(REPO, "research", "b0_l3_runner", "run_l3_prospective.py")
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_no_import_escapes_the_roots(entry, "run_sealed_l2")
    assert "outside MODULE_ROOTS" in str(exc.value)
    assert "research/b0_l2/run_sealed_l2.py" in str(exc.value)


@pytest.mark.parametrize("module", ["os", "sys", "json", "pandas", "pytest",
                                    "l3_snapshot", "core.b0_state"])
def test_the_guard_is_silent_for_everything_it_should_be(module):
    """Stdlib, third-party and in-roots names all resolve to nothing outside the
    roots. Refusing every unresolved name would abort on `import os`."""
    assert rs._resolve_outside_roots(module) is None
    rs.assert_no_import_escapes_the_roots(__file__, module)


def test_the_closure_walk_itself_refuses_an_escaping_import(tmp_path, monkeypatch):
    """Wired into `route_closure_files`, not merely available beside it.

    Built in a fake repo under `tmp_path`: writing a probe into the real tree is
    what `test_the_producer_set_is_read_from_disk_not_hand_listed` was fixed for,
    and here it would change `route_seal_id` while it existed.
    """
    root = tmp_path / "repo"
    (root / "research" / "b0_l3_runner").mkdir(parents=True)
    (root / "research" / "b0_stray").mkdir(parents=True)
    (root / "research" / "b0_l3_runner" / "entry.py").write_text(
        "import stray\n", encoding="utf-8")
    (root / "research" / "b0_stray" / "stray.py").write_text(
        "x = 1\n", encoding="utf-8")
    monkeypatch.setattr(rs, "REPO", str(root))

    entry = os.path.join("research", "b0_l3_runner", "entry.py")
    with pytest.raises(rs.RouteSealError, match="outside MODULE_ROOTS"):
        rs.route_closure_files(entry_points=(entry,))


def test_the_search_roots_are_derived_from_the_filesystem(tmp_path, monkeypatch):
    """A hand-listed set of places to look drifts, and drifts permissive: the
    directory it stops naming is the one that then escapes unnoticed."""
    root = tmp_path / "repo"
    (root / "research" / "b0_has_code").mkdir(parents=True)
    (root / "research" / "b0_has_code" / "m.py").write_text("", encoding="utf-8")
    (root / "research" / "just_data").mkdir(parents=True)
    (root / "research" / "just_data" / "x.csv").write_text("", encoding="utf-8")
    monkeypatch.setattr(rs, "REPO", str(root))

    roots = {r.replace("\\", "/") for r in rs._module_search_roots()}
    assert "research/b0_has_code" in roots
    assert "research/just_data" not in roots


# --- N1-1 · no seal while a required family has no authoritative leg -------------------

def test_the_calendar_blocks_sealing_because_it_has_no_authoritative_leg():
    """N1-1, ruled 2026-09-02. The family that decides WHEN reads LIVE /
    SUPPLEMENTARY since A-4, R-W1-2 gives authority to TEJ, and the calendar's
    bytes are not TEJ -- so nothing exists to reconcile it against."""
    assert rs.unauthoritative_floor_families() == ("calendar",)
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_route_is_sealable()
    assert "N1-1" in str(exc.value)
    assert "calendar" in str(exc.value)


def test_the_n1_gate_is_derived_from_the_declaration_not_from_a_list(monkeypatch):
    """It must open when a family genuinely gains an authoritative leg, and
    close again the moment one loses it -- without anyone editing a sentence.

    A prose item in `route_closure.still_owed_before_a_seal_may_be_taken` would
    need a human to delete it; that list carried "MASTER FREEZE records v1.32"
    long after the freeze said 1.37.
    """
    import build_flat_leaves as flat

    honest = dict(flat.FLAT_FAMILIES["calendar"])
    honest.update(source_family="TEJ", authority="AUTHORITATIVE")
    monkeypatch.setitem(flat.FLAT_FAMILIES, "calendar", honest)
    assert rs.unauthoritative_floor_families() == ()

    # ... and the owed list is what refuses next, not this gate.
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_route_is_sealable()
    assert "N1-1" not in str(exc.value)
    assert "still declares" in str(exc.value)


def test_n1_is_checked_before_the_owed_list():
    """`route_closure` lists its specification gap first "because no amount of
    implementation closes it". N1-1 is that shape and is checked the same way:
    it is not an owed item, and nothing anyone builds clears it."""
    with pytest.raises(rs.RouteSealError) as exc:
        rs.assert_route_is_sealable()
    assert "N1-1" in str(exc.value)
    assert "still declares" not in str(exc.value)


# --- N-2 · the seal binds code, and says so where a reader of the seal sees it --------

def _sealable(monkeypatch):
    """Satisfy both bars so the payload can be built at all: the N1-1 gate and
    `route_closure`'s owed list. Neither is removed -- each is given the state
    it is waiting for, so nothing here weakens what the other tests check."""
    import build_flat_leaves as flat
    import route_closure

    honest = dict(flat.FLAT_FAMILIES["calendar"])
    honest.update(source_family="TEJ", authority="AUTHORITATIVE")
    monkeypatch.setitem(flat.FLAT_FAMILIES, "calendar", honest)

    real = route_closure.seal_payload

    def cleared():
        p = dict(real())
        p["still_owed_before_a_seal_may_be_taken"] = []
        return p

    monkeypatch.setattr(route_closure, "seal_payload", cleared)


def test_the_seal_declares_that_it_binds_code_and_not_data(monkeypatch):
    """N-2, ruled 2026-09-02. Binding the calendar was REJECTED -- it gains a
    row every trading day, so it would expire the seal daily. Disclosure was
    taken instead, and it has to be readable FROM the seal: the failure it
    guards against is somebody comparing leaf hashes across clones with no way
    to learn that a leaf is not purely a function of the archives."""
    _sealable(monkeypatch)
    payload = rs.route_seal_payload()
    assert payload["binding_scope"] == "PRODUCTION_ROUTE_CODE_ONLY"
    assert "does NOT bind data" in payload["binding_disclosure"]


def test_the_disclosure_is_inside_the_seals_own_digest(monkeypatch):
    """A disclosure outside the digest is a comment: it could be edited after
    the fact without the id moving, which is the one thing content-addressing
    exists to prevent."""
    _sealable(monkeypatch)
    payload = rs.route_seal_payload()
    ident = rs.route_seal_id(payload)

    for field in ("binding_scope", "binding_disclosure"):
        tampered = {**payload, field: "something else"}
        assert rs.route_seal_id(tampered) != ident, (
            "%s is outside the digest" % field)


def test_the_seal_does_not_bind_the_two_data_files_n2_named(monkeypatch):
    """The ruling names them. Neither may appear among the sealed files."""
    _sealable(monkeypatch)
    payload = rs.route_seal_payload()
    for data_file in ("data/b0/trading_calendar.csv",
                      "research/d1_price_universe/price_source_contract.json"):
        assert data_file not in payload["files"], data_file


# --- the route's own "still owed" declaration ------------------------------------------

def test_sealability_is_read_from_route_closure_not_restated(monkeypatch):
    """A copy of that list would go stale in the direction that matters.

    The N1-1 gate is checked ahead of the owed list and would otherwise refuse
    first, so it is satisfied here rather than removed: this test is about where
    the OWED list comes from, and neutering the gate to reach it would leave the
    gate untested by everything that runs after.
    """
    import build_flat_leaves as flat

    honest = dict(flat.FLAT_FAMILIES["calendar"])
    honest.update(source_family="TEJ", authority="AUTHORITATIVE")
    monkeypatch.setitem(flat.FLAT_FAMILIES, "calendar", honest)
    assert rs.unauthoritative_floor_families() == ()

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


def test_the_runner_gate_refuses_while_anything_is_owed(monkeypatch):
    import build_flat_leaves as flat

    honest = dict(flat.FLAT_FAMILIES["calendar"])
    honest.update(source_family="TEJ", authority="AUTHORITATIVE")
    monkeypatch.setitem(flat.FLAT_FAMILIES, "calendar", honest)

    from route_closure import seal_payload

    owed = list(seal_payload().get("still_owed_before_a_seal_may_be_taken") or ())
    if not owed:
        pytest.skip("route_closure now declares nothing owed")
    with pytest.raises(rs.RouteSealError):
        rs.route_seal_payload()


# --- placeholder route_seal_ids ---------------------------------------------------------

@pytest.mark.parametrize("declared", ["", "   ", "PENDING", "pending", "TBD",
                                      "none", "PLACEHOLDER", "-",
                                      # A-1b: admitted here until 2026-09-02,
                                      # refused by core the whole time.
                                      "TODO", "todo", "PENDING_SEAL", "0"])
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


def test_the_placeholder_list_is_cores_and_not_a_copy():
    """A-1b, ruled 2026-09-02 (§9.2). Two lists existed and had drifted.

    Identity, not equality: a copy that happens to agree today is the state this
    ruling removed. `l3_route_seal` consults the vocabulary; it does not own it.
    """
    from core.b0_l3_lineage_capture import PLACEHOLDER_ROUTE_SEAL_IDS

    assert rs.placeholder_seal_ids() == frozenset(PLACEHOLDER_ROUTE_SEAL_IDS)


def test_a_hand_copied_list_would_not_follow_core(monkeypatch):
    """The test the equality check could not make.

    A literal that agrees with core today passes every assertion about its
    CONTENTS. Only a live read follows core when core moves, so that is what is
    asserted: extend core's vocabulary in-process and this module must refuse
    the new value without being touched.
    """
    import core.b0_l3_lineage_capture as lcap

    monkeypatch.setattr(
        lcap, "PLACEHOLDER_ROUTE_SEAL_IDS",
        tuple(lcap.PLACEHOLDER_ROUTE_SEAL_IDS) + ("NOT_A_SEAL_YET",))
    assert "NOT_A_SEAL_YET" in rs.placeholder_seal_ids()
    with pytest.raises(rs.RouteSealError, match="names no route"):
        rs.assert_aggregate_names_this_seal(
            {"route_seal_id": "NOT_A_SEAL_YET"}, "a" * 64)


def test_the_drift_ran_in_the_permissive_direction():
    """Every string core refuses is refused here too.

    This is the asymmetry that made the drift dangerous rather than merely
    untidy: `assert_aggregate_names_this_seal` runs inside the runner's gate,
    ahead of the manifest engine, so the WIDER list was the effective one.
    """
    from core.b0_l3_lineage_capture import PLACEHOLDER_ROUTE_SEAL_IDS

    for declared in PLACEHOLDER_ROUTE_SEAL_IDS:
        with pytest.raises(rs.RouteSealError):
            rs.assert_aggregate_names_this_seal(
                {"route_seal_id": declared}, "a" * 64)


def test_the_fixture_route_seal_id_used_everywhere_is_a_placeholder():
    """`PENDING` is what every harvest and every fixture writes today."""
    assert "PENDING" in rs.placeholder_seal_ids()


# --- verifying a seal against the working tree --------------------------------------------

@pytest.fixture()
def sealable(monkeypatch):
    """Pretend `route_closure` has cleared its owed list, and nothing else."""
    monkeypatch.setattr(rs, "assert_route_is_sealable",
                        lambda: {"code_closure_size": len(
                            production_route_code_closure())})
    return rs.route_seal_payload()


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
        rs.assert_seal_binds_current_route({**sealable, "files": files})
    assert "never sealed" in str(exc.value)


def test_a_seal_from_another_contract_version_is_refused(sealable):
    with pytest.raises(rs.RouteSealError):
        rs.assert_seal_binds_current_route(
            {**sealable, "contract_version": "b0_l3_route_seal@0"})


def test_the_seal_id_is_content_addressed(sealable):
    ident = rs.route_seal_id(sealable)
    assert len(ident) == 64
    # adding the id to the payload must not move the id
    assert rs.route_seal_id({**sealable, "route_seal_id": ident}) == ident
    # changing any bound file does move it
    moved = {**sealable,
             "files": {**sealable["files"], "core/b0_route.py": "0" * 64}}
    assert rs.route_seal_id(moved) != ident


def test_loading_a_seal_that_does_not_exist_names_no_fallback():
    with pytest.raises(rs.RouteSealError) as exc:
        rs.load_route_seal("f" * 64)
    assert "no 'latest'" in str(exc.value)


def test_a_tampered_seal_file_is_refused(tmp_path, monkeypatch, sealable):
    monkeypatch.setattr(rs, "SEAL_ROOT", str(tmp_path))
    ident = rs.route_seal_id(sealable)
    payload = {**sealable, "route_seal_id": ident}
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
