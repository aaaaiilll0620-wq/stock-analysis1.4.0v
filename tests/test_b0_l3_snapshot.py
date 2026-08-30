# -*- coding: utf-8 -*-
"""W6b · the L3 snapshot materializer.

What it has to refuse is the point:

    a source set that is not READY
    an as_of the caller supplied rather than one §6.6 derived
    a manifest whose declared as_of disagrees with the frozen rule
    a decision date whose period is not over
    a declared calendar that stops before the decision date, so as_of cannot be
        shown to be the latest completed session before it
    a second receipt for the same period
    being mistaken for a materialized snapshot when it is only a bound one
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(REPO, "research", "b0_materializer"),
           os.path.join(REPO, "research", "b0_l3")):
    sys.path.insert(0, _p)

from core.b0_l3_lineage_capture import (                          # noqa: E402
    PURPOSE_DIAGNOSTIC,
)
import build_bonus_shares_leaf as B                              # noqa: E402
import build_corporate_actions_leaf as CA                        # noqa: E402
import build_financials_leaf as FIN                              # noqa: E402
import build_flat_leaves as F                                    # noqa: E402
import build_prices_leaf as P                                    # noqa: E402
import build_valuation_leaf as V                                 # noqa: E402
import l3_snapshot as S                                          # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    AGGREGATE_FILENAME, LEAF_FILENAME, ManifestError, assemble_aggregate,
    write_aggregate, write_leaf,
)

RUN = "L3-0000000000000001"
AS_OF, DECISION = "2026-03-30", "2026-03-31"

sources = pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO, P.LANDING_DIRECTORY)),
    reason="TEJ exports not present")


def _run(tmp_path, as_of=AS_OF, seal="PENDING", full=True):
    d = str(tmp_path)
    for ds in sorted(F.FLAT_FAMILIES):
        write_leaf(d, F.build(ds, RUN, as_of))
    for mod in (FIN, P, B):
        write_leaf(d, mod.build(RUN, as_of))
    write_leaf(d, V.build(RUN, as_of))
    write_leaf(d, CA.build(RUN, as_of, run_dir=d))
    if full:
        write_aggregate(d, assemble_aggregate(
            run_dir=d, run_id=RUN, as_of=as_of, purpose=PURPOSE_DIAGNOSTIC))
    return d


def _calendar_source_through(dest: str, last_session: str) -> str:
    """The REAL declared TAIEX series, truncated after `last_session`.

    Not a stubbed session tuple: this writes a parquet the leaf builder then
    reads, hashes and declares, and that `l3_snapshot` re-hashes before parsing.
    Truncation is the condition under test — a calendar whose last observed
    session IS the decision date — and it is the one thing that has to be
    manufactured, because the harvested cache always runs past the month-ends
    the valuation payloads exist for.
    """
    import pandas as pd

    landing = os.path.join(REPO, F.FLAT_FAMILIES["calendar"]["landing"])
    df = pd.read_parquet(os.path.join(landing, "taiex_daily.parquet"))
    kept = df[[str(d) <= last_session for d in df["date"]]]
    os.makedirs(dest, exist_ok=True)
    kept.to_parquet(os.path.join(dest, "taiex_daily.parquet"), index=False)
    return dest


def _run_observed_through(tmp_path, last_session: str, as_of=AS_OF, drop=()):
    """A real nine-family run whose declared calendar stops at `last_session`.

    Every leaf is built by its own producer from the real exports, and the
    aggregate is assembled and verified for real, so `verify_aggregate`,
    `assert_ready` and `_sessions_from_declared_calendar` all run. `drop` removes
    a leaf AFTER the others are built — the same order `assemble_aggregate` is
    asked to notice — so readiness is decided by what is on disk.
    """
    base = str(tmp_path)
    d = os.path.join(base, "run")
    os.makedirs(d, exist_ok=True)
    calendar_dir = _calendar_source_through(
        os.path.join(base, "declared_calendar"), last_session)

    for ds in sorted(F.FLAT_FAMILIES):
        extra = {"landing_dir": calendar_dir} if ds == "calendar" else {}
        write_leaf(d, F.build(ds, RUN, as_of, **extra))
    for mod in (FIN, P, B):
        write_leaf(d, mod.build(RUN, as_of))
    write_leaf(d, V.build(RUN, as_of))
    write_leaf(d, CA.build(RUN, as_of, run_dir=d))
    for ds in drop:
        os.remove(os.path.join(d, LEAF_FILENAME % ds))
    write_aggregate(d, assemble_aggregate(
        run_dir=d, run_id=RUN, as_of=as_of, purpose=PURPOSE_DIAGNOSTIC))
    return d


# --- the period is derived, not supplied ---------------------------------------

@sources
def test_the_as_of_comes_from_the_rule_not_from_the_caller(tmp_path):
    p = S.plan(_run(tmp_path), RUN, DECISION)
    assert p["as_of"] == AS_OF                    # §6.6: strictly before
    assert p["as_of"] < p["decision_date"] < p["execution_date"]
    assert p["execution_date"] == "2026-04-01"


def test_a_missing_decision_date_has_no_default(tmp_path):
    with pytest.raises(S.L3SnapshotError, match="no default"):
        S.plan(str(tmp_path), RUN, "")


@sources
def test_a_manifest_claiming_a_different_as_of_is_refused(tmp_path):
    """The manifest says which day the sources were harvested for; §6.6 says
    which day the decision stands on. They must be the same day."""
    # A session that IS harvested, but not the one §6.6 resolves 2026-03-31 to.
    d = _run(tmp_path, as_of="2026-02-26")
    with pytest.raises(S.L3SnapshotError, match="resolves"):
        S.plan(d, RUN, DECISION)


def _declared(monkeypatch, sessions, manifest_as_of):
    """Stub the declared source set: a calendar and the as_of it was harvested
    for. Nothing here touches the filesystem, so a `plan*` call that got as far
    as claiming a receipt would be visible as a write, not a pass."""
    monkeypatch.setattr(
        S, "verify_aggregate",
        lambda d: {"run_id": RUN, "as_of": manifest_as_of})
    monkeypatch.setattr(S, "assert_ready", lambda aggregate: None)
    monkeypatch.setattr(
        S, "_sessions_from_declared_calendar", lambda d: tuple(sessions))


# The decision date IS a session here, and it is the last one the calendar has:
# coverage reaches through the decision date, and the execution session after it
# does not exist yet. That is precisely the state an intent run is built for.
COVERED = ("2026-08-27", "2026-08-28", "2026-08-31")


@sources
def test_a_period_that_is_not_over_is_refused(tmp_path):
    """§6.5 executes at the open of the session AFTER the decision date. If the
    declared calendar has no such session, the month has not finished.

    Run on REAL inputs, and deliberately not on `_declared`. That helper
    monkeypatches `verify_aggregate`, `assert_ready` AND
    `_sessions_from_declared_calendar` — every dependency `plan()` has between
    its arguments and its answer — so the version of this test that used it
    would have passed with `assert_ready` deleted from the module and with no
    declared calendar in existence. A gate test that stubs the gate's own
    collaborators certifies the stub.

    So all three run for real here: nine leaves built by their own producers, an
    aggregate assembled and re-verified from the bytes on disk, and a declared
    calendar the snapshot re-hashes before parsing. Both refusals `plan()` owes
    on that path are asserted, in the order it owes them.
    """
    # 1. readiness comes first, and it is REACHED rather than assumed: a run
    #    missing one of the nine is refused by the manifest engine before any
    #    question about the period is asked.
    partial = _run_observed_through(tmp_path / "partial", DECISION,
                                    drop=("prices",))
    with pytest.raises(ManifestError, match="NOT_READY"):
        S.plan(partial, RUN, DECISION)

    # 2. with a ready source set, the declared calendar is real enough to
    #    resolve as_of through: coverage reaches the decision date exactly.
    d = _run_observed_through(tmp_path / "ready", DECISION)
    assert S._sessions_from_declared_calendar(d)[-1] == DECISION
    intent = S.plan_decision_intent(d, RUN, DECISION)
    assert intent["as_of"] == AS_OF                 # §6.6, latest completed
    assert intent["execution_date"] is None
    assert intent["calendar_last_session"] == DECISION

    # 3. ...and the executable path still refuses, because §6.5's session does
    #    not exist. The refusal names the calendar end rather than guessing one.
    with pytest.raises(S.L3SnapshotError, match="period is not over") as excinfo:
        S.plan(d, RUN, DECISION)
    assert DECISION in str(excinfo.value)


def test_a_decision_intent_does_not_invent_the_future_execution_session(
        tmp_path, monkeypatch):
    """The LEGITIMATE half of the decision/execution split: the session after
    the decision date may be absent, and the intent says so with an explicit
    null rather than a weekday guess. The calendar still reaches through the
    decision date, so §6.6 can name as_of exactly."""
    _declared(monkeypatch, COVERED, "2026-08-28")
    planned = S.plan_decision_intent(str(tmp_path), RUN, "2026-08-31")
    assert planned["as_of"] == "2026-08-28"     # latest completed session
    assert planned["execution_date"] is None    # and no invented one
    assert planned["calendar_last_session"] == "2026-08-31"


def test_a_calendar_covering_exactly_through_the_decision_date_is_accepted(
        tmp_path, monkeypatch):
    """The positive boundary: coverage ending ON the decision date, with no
    later session at all, is enough for an intent. Nothing beyond it is asked
    for, so a calendar harvested on the decision date is admissible."""
    _declared(monkeypatch, COVERED, "2026-08-28")
    planned = S.plan_decision_intent(str(tmp_path), RUN, "2026-08-31")
    assert planned["as_of"] < planned["decision_date"] == COVERED[-1]
    assert planned["execution_date"] is None

    # The requirement is coverage THROUGH the decision date, not coverage that
    # stops exactly there: a calendar reaching further is admissible too, and
    # resolves to the same as_of.
    _declared(monkeypatch, COVERED + ("2026-09-01",), "2026-08-28")
    assert S.plan_decision_intent(
        str(tmp_path), RUN, "2026-08-31")["as_of"] == "2026-08-28"


def test_a_calendar_that_stops_before_the_decision_date_is_refused(
        tmp_path, monkeypatch):
    """The DEFECT half. Leaves harvested 2026-08-14, an operator running an
    intent for 2026-08-31: the observed prefix used to be clipped, as_of
    silently became 2026-08-14, eleven sessions vanished from the eligible
    population and the ADV20 window, and the intent still declared
    decision_date 2026-08-31. §6 stop rule: as_of must EQUAL the latest
    completed session before the decision date, and this calendar cannot
    establish that. It aborts."""
    harvested = ("2026-08-12", "2026-08-13", "2026-08-14")
    _declared(monkeypatch, harvested, "2026-08-14")

    with pytest.raises(S.L3SnapshotError) as excinfo:
        S.plan_decision_intent(str(tmp_path), RUN, "2026-08-31")

    message = str(excinfo.value)
    # An operator must be able to act on this without reading the source: the
    # coverage end, the requested decision date, and the as_of that would have
    # been used are all named.
    assert "2026-08-14" in message                      # coverage end / as_of
    assert "2026-08-31" in message                      # requested decision
    assert "as_of that would have been used" in message

    # The executable path refuses it too, and for this reason rather than the
    # §6.5 one — the calendar never even reaches the decision date.
    with pytest.raises(S.L3SnapshotError, match="observed only through"):
        S.plan(str(tmp_path), RUN, "2026-08-31")


def test_the_route_helper_refuses_the_clipped_prefix_itself(monkeypatch):
    """The guard belongs to the route, not only to the L3 caller: the
    production adapter resolves as_of through the same helper."""
    from core.b0_market_state import SourceContract, TradingCalendar
    from core import b0_route

    observed = ("2026-08-12", "2026-08-13", "2026-08-14")
    calendar = TradingCalendar(observed, SourceContract(
        name="short_calendar", kind="trading_calendar",
        importer_version="test", content_sha256="0" * 64,
        schema_sha256="0" * 64, date_min=observed[0], date_max=observed[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False))

    with pytest.raises(b0_route.RouteError, match="observed only through"):
        b0_route.resolve_as_of_observed_prefix("2026-08-31", calendar)

    # ...and resolves normally once coverage reaches the decision date.
    full = observed + ("2026-08-17", "2026-08-31")
    calendar = TradingCalendar(full, SourceContract(
        name="full_calendar", kind="trading_calendar",
        importer_version="test", content_sha256="0" * 64,
        schema_sha256="0" * 64, date_min=full[0], date_max=full[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False))
    assert b0_route.resolve_as_of_observed_prefix(
        "2026-08-31", calendar) == "2026-08-17"


@sources
def test_the_future_guard_raises_in_this_exception_class(tmp_path):
    """`resolve_as_of` also refuses it, but as MarketStateError — which a caller
    guarding L3SnapshotError would not catch."""
    d = _run(tmp_path)
    with pytest.raises(S.L3SnapshotError):
        S.plan(d, RUN, "2027-01-29")


# --- the source set must be ready ----------------------------------------------

@sources
def test_a_partial_source_set_is_refused(tmp_path):
    d = _run(tmp_path, full=False)
    os.remove(os.path.join(d, "source_manifest_prices.json"))
    write_aggregate(d, assemble_aggregate(
        run_dir=d, run_id=RUN, as_of=AS_OF, purpose=PURPOSE_DIAGNOSTIC))

    # Readiness belongs to the manifest engine, not to the snapshot: the layer
    # that knows the source set is incomplete is the layer that says so.
    with pytest.raises(ManifestError, match="NOT_READY"):
        S.plan(d, RUN, DECISION)


@sources
def test_an_aggregate_from_another_run_is_refused(tmp_path):
    d = _run(tmp_path)
    with pytest.raises(S.L3SnapshotError, match="is for run"):
        S.plan(d, "L3-SOMEONE-ELSE", DECISION)


@sources
def test_a_changed_calendar_source_is_detected(tmp_path, monkeypatch):
    """as_of is resolved against the calendar the MANIFEST declares, so that
    file's bytes are checked before it is trusted."""
    d = _run(tmp_path)
    import l3_snapshot as mod

    monkeypatch.setattr(mod, "file_sha256", lambda p: "9" * 64)
    with pytest.raises(S.L3SnapshotError, match="has changed since the manifest"):
        mod._sessions_from_declared_calendar(d)


@sources
def test_the_calendar_is_the_declared_one_not_the_sealed_l2_artefact(tmp_path):
    """`data/b0/trading_calendar.csv` is L2's, frozen in place under R-W1-1, and
    it stops at 2026-08-17. The declared TAIEX series runs further."""
    sessions = S._sessions_from_declared_calendar(_run(tmp_path))
    assert sessions[-1] > "2026-08-17"


# --- the receipt ----------------------------------------------------------------

@sources
def test_the_receipt_binds_one_hash_that_covers_every_source(tmp_path):
    d = _run(tmp_path)
    r = S.build_receipt(d, RUN, DECISION)

    from core.b0_canonical_hash import file_sha256
    assert r["source_ownership_manifest_sha256"] == file_sha256(
        os.path.join(d, AGGREGATE_FILENAME))
    assert len(r["required_datasets"]) == 9
    assert r["route_code_closure_size"] == 29      # +b0_l3_price_span (v1.34/C-68)
                                                   # +b0_l3_lineage_capture (v1.35/C-70)


@sources
def test_the_receipt_says_it_is_not_evidence(tmp_path):
    r = S.build_receipt(_run(tmp_path), RUN, DECISION)
    assert r["evidence_class"] == "NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED"
    assert r["performance_computed"] is False
    assert r["decision_layer_invoked"] is False


@sources
def test_a_receipt_only_snapshot_is_not_a_materialized_one(tmp_path):
    """The families are declared and bound; they are not yet parsed. A run may
    not proceed on that."""
    r = S.build_receipt(_run(tmp_path), RUN, DECISION)
    assert r["state"] == S.STATE_RECEIPT_ONLY
    with pytest.raises(S.L3SnapshotError, match="have not been parsed"):
        S.assert_snapshot_complete(r)

    r["state"] = S.STATE_MATERIALIZED
    S.assert_snapshot_complete(r)


@sources
def test_a_period_is_observed_once(tmp_path):
    d = _run(tmp_path)
    r = S.build_receipt(d, RUN, DECISION)
    S.write_receipt(d, r)
    with pytest.raises(S.L3SnapshotError, match="already exists"):
        S.write_receipt(d, r)


@sources
def test_the_written_receipt_round_trips(tmp_path):
    d = _run(tmp_path)
    raw = S.write_receipt(d, S.build_receipt(d, RUN, DECISION))
    on_disk = json.load(open(os.path.join(d, S.SNAPSHOT_RECEIPT_FILENAME),
                             encoding="utf-8"))
    assert on_disk["as_of"] == AS_OF
    assert len(raw) == 64


# --- S-7: the contract version moves when the receipt payload moves -------------
#
# The defect: `SNAPSHOT_CONTRACT_VERSION` stayed `..._V1` while the v1.38
# decision-intent/execution split added `decision_intent_only` and
# `price_span_endpoint_kind` to the MATERIALIZED payload. Pre- and post-change
# receipts for the same period therefore differ in bytes and in raw sha256 while
# declaring the same contract — and because `write_receipt` is O_EXCL, the two
# can never be produced by one run and diffed in place. Nothing in either
# artefact said why they disagreed.
#
# Bumping the string alone would move the problem one version along, so the
# version is pinned to an EXPLICIT key set here. Not `len(receipt) == 30`: a
# count survives an add-one/remove-one edit and says nothing about what the
# contract IS. The keys are written out so that changing the payload forces this
# table to be edited, which forces the version decision to be made rather than
# inherited.

_RECEIPT_ONLY_KEYS_V2 = frozenset({
    "contract_version", "run_id", "decision_date", "as_of", "execution_date",
    "source_ownership_manifest_sha256",
    "source_ownership_manifest_payload_sha256",
    "required_datasets", "route_seal_id", "route_code_closure_size",
    "state", "state_detail", "performance_computed", "decision_layer_invoked",
    "evidence_class", "written_at",
})

# Everything the RECEIPT_ONLY shape has, plus the market-side facts an assembled
# observation certifies. `state` / `state_detail` are re-stated, not added.
_MATERIALIZED_KEYS_V2 = _RECEIPT_ONLY_KEYS_V2 | {
    "market_state_sha256", "securities", "price_span", "bonus_window",
    "price_legs", "price_coverage_floor",
    "spell_starts_at_price_coverage_floor",
    "lineage_price_floor", "observed_price_coverage_floor",
    "floor_disposition", "span_derivation_authority",
    "portfolio_side_materialized",
    # v1.38. The two that moved while the version did not.
    "decision_intent_only", "price_span_endpoint_kind",
}

PINNED_RECEIPT_KEYS = {
    "L3_SNAPSHOT_CONTRACT_V2": {
        "receipt_only": _RECEIPT_ONLY_KEYS_V2,
        "materialized": _MATERIALIZED_KEYS_V2,
    },
}


def _receipt_key_sets_from_source() -> dict:
    """The key sets `build_receipt` actually emits, read off its own AST.

    Static so that it runs everywhere, including a tree with no TEJ exports: a
    version signal guarded by a fixture is a version signal that can be missing
    exactly when someone is working without the exports.
    `test_the_built_receipt_has_exactly_the_pinned_keys` ties this back to a
    receipt that was really built, so the AST is never trusted on its own.
    """
    import ast

    path = os.path.join(REPO, "research", "b0_l3", "l3_snapshot.py")
    fn = next(n for n in ast.walk(ast.parse(open(path, encoding="utf-8").read()))
              if isinstance(n, ast.FunctionDef) and n.name == "build_receipt")

    def literal_keys(node):
        names, splats = [], []
        for key, value in zip(node.keys, node.values):
            if key is None:                     # **something
                assert isinstance(value, ast.Name), ast.dump(value)
                splats.append(value.id)
                continue
            assert isinstance(key, ast.Constant) and isinstance(key.value, str), \
                "a computed receipt key cannot be pinned: %s" % ast.dump(key)
            names.append(key.value)
        return set(names), splats

    built = next(
        n.value for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
        and n.value.keys
        and any(getattr(t, "id", "") == "built" for t in n.targets))
    returned = next(n.value for n in ast.walk(fn)
                    if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict))

    base, base_splats = literal_keys(returned)
    extra, extra_splats = literal_keys(built)
    # A second `**` in either dict would let part of the payload escape the pin.
    assert base_splats == ["built"], base_splats
    assert extra_splats == [], extra_splats
    return {"receipt_only": base, "materialized": base | extra}


def _pinned_for_the_current_version() -> dict:
    assert S.SNAPSHOT_CONTRACT_VERSION in PINNED_RECEIPT_KEYS, (
        "the receipt contract version is %r and no key set is pinned for it. A "
        "version is only a signal if it says what it stands for: declare that "
        "version's payload in PINNED_RECEIPT_KEYS."
        % S.SNAPSHOT_CONTRACT_VERSION)
    return PINNED_RECEIPT_KEYS[S.SNAPSHOT_CONTRACT_VERSION]


def test_the_receipt_key_set_is_pinned_to_the_contract_version():
    """S-7. Change the payload without changing the version and this fails."""
    pinned = _pinned_for_the_current_version()
    emitted = _receipt_key_sets_from_source()

    for shape in ("receipt_only", "materialized"):
        assert emitted[shape] == pinned[shape], (
            "%s receipt payload keys changed under %s.\n  added:   %s\n"
            "  removed: %s\nEither this is a new contract version or the key "
            "does not belong in the receipt; it cannot be neither."
            % (shape, S.SNAPSHOT_CONTRACT_VERSION,
               sorted(emitted[shape] - pinned[shape]),
               sorted(pinned[shape] - emitted[shape])))

    # The two the split added, named, so a REVERT is as visible as an add — and
    # so that they stay on the materialized side only.
    assert {"decision_intent_only", "price_span_endpoint_kind"} <= \
        pinned["materialized"]
    assert not ({"decision_intent_only", "price_span_endpoint_kind"}
                & pinned["receipt_only"])


class _AssembledStub(dict):
    """An assembled state that answers every key `build_receipt` asks it for.

    A plain dict would raise KeyError on a newly added field, which reads as a
    broken test rather than as an unpinned payload key. This makes the key set
    the thing that fails.
    """

    def __missing__(self, key):
        return "STUB_%s" % key


@sources
def test_the_built_receipt_has_exactly_the_pinned_keys(tmp_path):
    """The AST pin, tied to a receipt that was really built by `build_receipt`.

    The RECEIPT_ONLY shape is built on the real nine-family run. The MATERIALIZED
    shape needs an assembled state, which is `l3_assemble`'s contract and not
    this module's, so the assembly is a stub — but the `built` block that maps it
    into the payload is this module's own code running for real, and that block
    is what the key set is about.
    """
    d = _run(tmp_path)
    pinned = _pinned_for_the_current_version()

    receipt = S.build_receipt(d, RUN, DECISION)
    assert set(receipt) == pinned["receipt_only"]
    assert receipt["contract_version"] == S.SNAPSHOT_CONTRACT_VERSION

    materialized = S.build_receipt(
        d, RUN, DECISION,
        assembled=_AssembledStub(period={"decision_date": DECISION}))
    assert set(materialized) == pinned["materialized"]
    assert materialized["state"] == S.STATE_MATERIALIZED
    assert materialized["decision_intent_only"] is False

    intent = S.build_intent_receipt(
        d, RUN, DECISION,
        assembled=_AssembledStub(period={"decision_date": DECISION},
                                 decision_intent_only=True))
    assert set(intent) == pinned["materialized"]
    assert intent["decision_intent_only"] is True


# --- L2 stays untouched ---------------------------------------------------------

def test_the_l3_materializer_does_not_import_the_l2_one():
    """A builder that accepts an arbitrary cutoff is a path by which the sealed
    141-period history could be rebuilt and re-dated."""
    import ast

    path = os.path.join(REPO, "research", "b0_l3", "l3_snapshot.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "build_market_side_state" not in node.module
        if isinstance(node, ast.Import):
            for a in node.names:
                assert "build_market_side_state" not in a.name
