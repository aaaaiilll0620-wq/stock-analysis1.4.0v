# -*- coding: utf-8 -*-
"""W6b · the L3 snapshot materializer: one decision date, one immutable receipt.

Deliberately NOT the L2 materializer with a parameter. `build_market_side_state`
stays pinned at 2026-03-31 and is not touched here, because a builder that
accepts an arbitrary cutoff is a path by which the sealed 141-period history can
be rebuilt and re-dated. Two producers, two contracts, no shared cutoff.

WHAT THIS ENFORCES
------------------
    as_of is DERIVED, never accepted
        The caller supplies a decision date. §6.6 / `b0_route.resolve_as_of`
        then fixes as_of from the calendar THE MANIFEST DECLARES — not from
        `data/b0/trading_calendar.csv`, which is L2's sealed artefact and is
        frozen in place (R-W1-1). The manifest's own `as_of` must equal what the
        frozen rule produces; a manifest that claims a different one is refused.

    the source set must be READY
        Nine leaves, every one of them, verified against the bytes on disk. A
        snapshot built on a partial inventory is not a prospective observation.

    the receipt binds ONE hash
        The aggregate's raw sha256, which transitively covers every leaf and
        every declared file. Re-checking the receipt re-checks the sources.

    nothing may be materialized for a date that has not happened
        §6.5 executes at the OPEN of the session after the decision date. If
        that session does not exist in the declared calendar yet, the period is
        not over and there is nothing to observe. This is the guard that stops
        an L3 month being "run" early and then quietly counted.

    the receipt is immutable
        O_EXCL, like the manifests. A second attempt at the same period is a new
        run, never an overwrite.

WHAT THIS DOES NOT DO YET
-------------------------
It does not parse the nine families into a `CanonicalDecisionInput`. That is
W6b-2 and it needs L3-side readers for each locator form. Until then this
produces the receipt and the guards, and `assert_snapshot_complete` refuses to
call a receipt-only snapshot a materialized one.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (REPO, os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.b0_canonical_hash import file_sha256                  # noqa: E402
from core.b0_market_state import SourceContract, TradingCalendar  # noqa: E402
from core.b0_route import resolve_as_of                          # noqa: E402
from source_ownership_manifest import (                          # noqa: E402
    AGGREGATE_FILENAME, LEAF_FILENAME, SELF_HASH_FIELD, assert_ready,
    load_leaf, verify_aggregate,
)

SNAPSHOT_RECEIPT_FILENAME = "l3_snapshot_receipt.json"
SNAPSHOT_CONTRACT_VERSION = "L3_SNAPSHOT_CONTRACT_V1"

STATE_RECEIPT_ONLY = "RECEIPT_ONLY_SOURCES_NOT_YET_PARSED"
STATE_MATERIALIZED = "MATERIALIZED"


class L3SnapshotError(SystemExit):
    """Fail-loud: the snapshot cannot be built as declared."""


def _sessions_from_declared_calendar(run_dir: str) -> tuple:
    """Sessions read from the calendar the MANIFEST declares.

    Not from `data/b0/trading_calendar.csv`: that is L2's sealed artefact, it is
    frozen in place under R-W1-1, and it stops at 2026-08-17. An L3 run that
    resolved its as_of against a frozen calendar would silently be asking a
    question about the wrong day.
    """
    import pandas as pd

    leaf_path = os.path.join(run_dir, LEAF_FILENAME % "calendar")
    leaf = load_leaf(leaf_path)
    consumed = [e for e in leaf["entries"] if e["disposition"] == "consumed"]
    if len(consumed) != 1:
        raise L3SnapshotError(
            "abort: the calendar leaf declares %d consumed sources; exactly one "
            "series defines the sessions." % len(consumed))
    entry = consumed[0]

    landing = leaf["landing_directory"]
    if not os.path.isabs(landing):
        landing = os.path.join(REPO, landing)
    path = os.path.join(landing, entry["locator"])
    got = file_sha256(path)
    if got != entry["raw_sha256"]:
        raise L3SnapshotError(
            "abort: the declared calendar source has changed since the manifest "
            "was written.\n  declared: %s\n  on disk:  %s"
            % (entry["raw_sha256"], got))

    # The same derivation `build_market_state.build_calendar()` uses: the
    # distinct dates of the TAIEX daily series, sorted.
    df = pd.read_parquet(path)
    return tuple(sorted({str(d) for d in df["date"]}))


def _calendar(sessions: tuple) -> TradingCalendar:
    return TradingCalendar(sessions, SourceContract(
        name="l3_declared_calendar", kind="trading_calendar",
        importer_version=SNAPSHOT_CONTRACT_VERSION,
        content_sha256="0" * 64, schema_sha256="0" * 64,
        date_min=sessions[0], date_max=sessions[-1],
        has_effective_dates=True, has_availability_semantics=True,
        is_current_snapshot=False))


def plan(run_dir: str, run_id: str, decision_date: str) -> dict:
    """Resolve the period and check every precondition. Writes nothing."""
    if not decision_date:
        raise L3SnapshotError(
            "abort: decision_date is required and has no default. An L3 period "
            "that cannot say which decision it is has nothing to observe.")

    aggregate = verify_aggregate(run_dir)
    assert_ready(aggregate)

    if aggregate["run_id"] != run_id:
        raise L3SnapshotError(
            "abort: the aggregate in %s is for run %r, not %r"
            % (run_dir, aggregate["run_id"], run_id))

    sessions = _sessions_from_declared_calendar(run_dir)
    calendar = _calendar(sessions)

    # Coverage first, and in THIS exception class. `resolve_as_of` also refuses
    # a date beyond the calendar, but it raises `MarketStateError`, which a
    # caller guarding against `L3SnapshotError` would not catch — and the reason
    # that matters here is not "beyond coverage", it is "the period is not over".
    after = [s for s in sessions if s > decision_date]
    if not after:
        raise L3SnapshotError(
            "abort: the declared calendar has no session after %s, so the §6.5 "
            "execution session does not exist yet.\n"
            "  calendar ends: %s\n"
            "The period is not over. There is nothing here to observe, and a "
            "snapshot taken now would be a forecast wearing a receipt."
            % (decision_date, sessions[-1]))

    as_of = resolve_as_of(decision_date, calendar)
    if as_of != aggregate["as_of"]:
        raise L3SnapshotError(
            "abort: §6.6 resolves %s to as_of %s, but the manifest declares "
            "%s.\nThe sources were harvested for a different day than the one "
            "this decision stands on."
            % (decision_date, as_of, aggregate["as_of"]))

    return {
        "decision_date": decision_date,
        "as_of": as_of,
        "execution_date": after[0],
        "calendar_last_session": sessions[-1],
        "aggregate": aggregate,
    }


def build_receipt(run_dir: str, run_id: str, decision_date: str,
                  route_seal_id: str = "", assembled: dict = None) -> dict:
    """The per-period receipt. Binds the aggregate, not the individual leaves.

    `assembled` is `l3_assemble.assemble(...)`'s result, and passing it is what
    moves the receipt from RECEIPT_ONLY to MATERIALIZED. It is an ARGUMENT
    rather than a later mutation because the receipt is written under `O_EXCL`:
    a period is observed once, so the state it certifies has to be known before
    it is written, not stamped onto it afterwards.
    """
    p = plan(run_dir, run_id, decision_date)
    aggregate_path = os.path.join(run_dir, AGGREGATE_FILENAME)

    from route_closure import seal_payload

    closure = seal_payload()
    built = {}
    if assembled is not None:
        if assembled["period"]["decision_date"] != p["decision_date"]:
            raise L3SnapshotError(
                "abort: the assembled state is for decision date %s, this "
                "receipt is for %s."
                % (assembled["period"]["decision_date"], p["decision_date"]))
        built = {
            "state": STATE_MATERIALIZED,
            "state_detail": (
                "the nine declared families were parsed and assembled into the "
                "market side of one canonical decision state"),
            # The market side ONLY. Definition B: portfolio[t] is causally
            # generated by executing t-1, so a receipt that bound a portfolio
            # here would be certifying a fabrication.
            "market_state_sha256": assembled["market_state_sha256"],
            "securities": assembled["securities"],
            "price_span": assembled["price_span"],
            "bonus_window": assembled["bonus_window"],
            "price_legs": assembled["price_legs"],
            "price_coverage_floor": assembled["price_coverage_floor"],
            "spell_starts_at_price_coverage_floor":
                assembled["spell_starts_at_price_coverage_floor"],
            # §19.4: the frozen lineage floor and the period's observed source
            # depth are bound TOGETHER. The first says what this lineage
            # promised, the second says what the declared sources actually
            # reach, and only the pair makes the disposition auditable.
            "lineage_price_floor": assembled["lineage_price_floor"],
            "observed_price_coverage_floor":
                assembled["observed_price_coverage_floor"],
            "floor_disposition": assembled["floor_disposition"],
            "span_derivation_authority": assembled["span_derivation_authority"],
            "portfolio_side_materialized": False,
        }
    return {
        "contract_version": SNAPSHOT_CONTRACT_VERSION,
        "run_id": run_id,
        "decision_date": p["decision_date"],
        "as_of": p["as_of"],
        "execution_date": p["execution_date"],
        # ONE hash. It covers every leaf, and every leaf covers every file.
        "source_ownership_manifest_sha256": file_sha256(aggregate_path),
        "source_ownership_manifest_payload_sha256":
            p["aggregate"][SELF_HASH_FIELD],
        "required_datasets": list(p["aggregate"]["required_datasets"]),
        "route_seal_id": route_seal_id or p["aggregate"]["route_seal_id"],
        "route_code_closure_size": closure["code_closure_size"],
        "state": STATE_RECEIPT_ONLY,
        "state_detail": (
            "the source set is declared, verified and bound; the nine families "
            "have not yet been parsed into a CanonicalDecisionInput (W6b-2)"),
        "performance_computed": False,
        "decision_layer_invoked": False,
        "evidence_class": "NOT_L3_EVIDENCE_UNTIL_THE_ROUTE_IS_SEALED",
        "written_at": _dt.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        **built,
    }


def write_receipt(run_dir: str, receipt: dict) -> str:
    """Immutable, like the manifests. Returns the receipt's raw sha256."""
    path = os.path.join(run_dir, SNAPSHOT_RECEIPT_FILENAME)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise L3SnapshotError(
            "abort: a snapshot receipt already exists at %s. A period is "
            "observed once; a second attempt is a NEW run, never an overwrite."
            % path)
    with os.fdopen(fd, "wb") as fh:
        fh.write((json.dumps(receipt, ensure_ascii=False, sort_keys=True,
                             indent=1) + "\n").replace("\r\n", "\n")
                 .encode("utf-8"))
    return file_sha256(path)


def assert_snapshot_complete(receipt: dict) -> None:
    """A receipt-only snapshot is not a materialized one."""
    if receipt.get("state") != STATE_MATERIALIZED:
        raise L3SnapshotError(
            "abort: snapshot state is %r — the source set is bound but the "
            "families have not been parsed into a CanonicalDecisionInput. A "
            "run may not proceed on a snapshot that has not been built."
            % receipt.get("state"))


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: l3_snapshot.py <run_dir> <run_id> <decision_date>")
        return 2
    run_dir, run_id, decision_date = argv[1], argv[2], argv[3]
    receipt = build_receipt(run_dir, run_id, decision_date)
    raw = write_receipt(run_dir, receipt)
    for k in ("decision_date", "as_of", "execution_date",
              "source_ownership_manifest_sha256", "state"):
        print("%-38s %s" % (k, receipt[k]))
    print("%-38s %s" % ("receipt_sha256", raw))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
