# -*- coding: utf-8 -*-
"""W6b · the L3 snapshot materializer.

What it has to refuse is the point:

    a source set that is not READY
    an as_of the caller supplied rather than one §6.6 derived
    a manifest whose declared as_of disagrees with the frozen rule
    a decision date whose period is not over
    a second receipt for the same period
    being mistaken for a materialized snapshot when it is only a bound one
"""
from __future__ import annotations

import datetime as _dt
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
    AGGREGATE_FILENAME, ManifestError, assemble_aggregate, write_aggregate,
    write_leaf,
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


# The declared calendar is the LIVE `~/market_cache/taiex_daily.parquet`, which
# gains a session every trading day. A literal date on either side of its end is
# therefore an assertion about the wall clock, not about the guard: `2026-08-31`
# was beyond the calendar when it was written and was inside it by 2026-09-01,
# at which point this file stopped testing what it says it tests. Both dates
# below are DERIVED from the declared calendar so that each names its own input
# to `l3_snapshot.py`'s coverage guard for good.
def _last_session(run_dir):
    return S._sessions_from_declared_calendar(run_dir)[-1]


@sources
def test_a_period_that_is_not_over_is_refused(tmp_path):
    """§6.5 executes at the open of the session AFTER the decision date. If the
    declared calendar has no such session, the month has not finished.

    The last declared session is INSIDE coverage and still has nothing after it
    — which is the case this refusal is worded for.
    """
    d = _run(tmp_path)
    with pytest.raises(S.L3SnapshotError, match="period is not over"):
        S.plan(d, RUN, _last_session(d))


@sources
def test_the_future_guard_raises_in_this_exception_class(tmp_path):
    """`resolve_as_of` also refuses it, but as MarketStateError — which a caller
    guarding L3SnapshotError would not catch.

    A day past the last declared session is BEYOND coverage. It reaches the same
    guard, and what this asserts is the exception CLASS it arrives in.
    """
    d = _run(tmp_path)
    beyond = _dt.date.fromisoformat(_last_session(d)) + _dt.timedelta(days=1)
    with pytest.raises(S.L3SnapshotError):
        S.plan(d, RUN, beyond.isoformat())


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
