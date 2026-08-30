# -*- coding: utf-8 -*-
"""`research/b0_l3_runner/capture_l3_floor.py` — the four things it used to get wrong.

The module had no test and no caller anywhere in the tree, which is how all four
survived. Each test below names the defect it pins:

D1  the module destroyed its own failure evidence. `finally: shutil.rmtree(root,
    ignore_errors=True)` ran on failure as well as on success, so the one
    outcome this path exists to detect — `assert_floor_is_a_trading_session`
    disagreeing with the calendar — left a stack trace and nothing else, while
    `FAILED_CAPTURE_PRESERVATION` requires the run-scoped price leaf, the
    aggregate manifest and the failure evidence to survive.

D2  a manifest could declare a landing directory nobody had read. The planned
    leaves are enumerated from private staging copies and declare
    `<final_run_dir>/inputs/...`, which is empty at that moment; that leaf's
    payload hash is what a published capture record would bind. The only guard
    was a string test that the staging path no longer APPEARED in the JSON —
    which the substitution passes exactly by being complete.

D3  `validation_aggregate_payload_sha256` was returned as a headline value
    beside the reproducible planned digests. The validation leaves must point at
    the machine-absolute staging snapshot, so it differs in every run and every
    clone; it was quoted in a dry-run report as if it were evidence.

D4  two definitions of "today". This module used `date.today()` (system-local)
    while `run_l3_prospective._taipei_today()` uses Asia/Taipei, so on a UTC
    host a capture and an intent taken in the same session could carry different
    calendar dates — and the capture date is stamped into the run id.

FIXTURES. The real sources are hundreds of MB of TEJ archives pinned by hash, so
these run on synthetic surfaces built under the scratch root. The prices family
declares its archives BY BYTES, so the declaration is re-pointed at the
synthetic archives for the duration of a test; that is the one place these tests
reach into another module's constants, and it is done from that module's own
declaration so a renamed or re-listed archive is picked up rather than guessed.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import zipfile
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, os.path.join(REPO, "research", "b0_l3"),
           os.path.join(REPO, "research", "b0_l3_runner"),
           os.path.join(REPO, "research", "b0_materializer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.b0_canonical_hash import file_sha256                      # noqa: E402
from core.b0_l3_lineage_capture import (                            # noqa: E402
    CAPTURE_FILENAME, FAILED_CAPTURE_PRESERVATION, LINEAGE_ROOT_PARTS,
    LineageCaptureError,
)
from research.b0_l3.l3_readers import PRICE_COLUMNS                 # noqa: E402
from research.b0_l3_runner import capture_l3_floor as C             # noqa: E402
from research.b0_materializer import build_flat_leaves as F         # noqa: E402
from research.b0_materializer import build_prices_leaf as P         # noqa: E402
from research.b0_materializer.source_ownership_manifest import (    # noqa: E402
    AGGREGATE_FILENAME, LEAF_FILENAME,
)

# Explicitly the harness scratch root, not `tmp_path`: these fixtures are the
# only readable record of what a failed capture preserved, and a per-test temp
# directory that pytest reaps is the same mistake the module was making.
SCRATCH_ROOT = os.environ.get("B0_CAPTURE_SCRATCH") or os.path.join(
    tempfile.gettempdir(), "claude", "scratch_cap")

PRE_2019_SESSIONS = ("2018-01-02", "2018-01-03")
QUARANTINED_CACHE_ROW = "2019-06-03"     # dropped by the reader, counted by D-1

# Declared, never created. A declaration is not a read, which is D2's whole
# point; if this ever exists the reconciliation verifies it directly instead.
FINAL_RUN_DIR = os.path.join(REPO, "artifacts", "l3_run",
                             "TEST-DECLARED-NEVER-CREATED")


# --- synthetic source surfaces --------------------------------------------------

def _write_price_archive(path: str, rows) -> None:
    header = "\t".join(PRICE_COLUMNS)
    body = "\n".join("\t".join(r) for r in rows)
    payload = (header + "\n" + body + "\n").encode("utf-16")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("member.csv", payload)


def _archive_days(names) -> dict:
    """One 2019+ session per declared archive, taken from its own `covers`.

    Falls back to generated days when the declaration carries no span or when
    two archives would land on the same session — the reader refuses a
    (stock_id, date) key that appears in two legs, and it is right to.
    """
    declarations = getattr(P, "CONSUMED_ARCHIVE_DECLARATIONS", {}) or {}
    days = {}
    for name in names:
        covers = (declarations.get(name) or {}).get("covers")
        days[name] = str(covers[0]) if covers else ""
    if len(set(days.values())) != len(names) or not all(days.values()):
        days = {name: "2019-01-%02d" % (2 + i)
                for i, name in enumerate(names)}
    return days


def _calendar_dir(root: str, sessions) -> str:
    import pandas as pd

    os.makedirs(root, exist_ok=True)
    pd.DataFrame({"date": sorted(sessions)}).to_parquet(
        os.path.join(root, "taiex_daily.parquet"), index=False)
    return root


@pytest.fixture(scope="module")
def sources():
    root = os.path.join(SCRATCH_ROOT, "sources")
    if os.path.isdir(root):
        shutil.rmtree(root)
    calendar = os.path.join(root, "calendar")
    prices_2019 = os.path.join(root, "prices_2019")
    prices_pre = os.path.join(root, "prices_pre2019")
    for d in (calendar, prices_2019, prices_pre):
        os.makedirs(d)

    names = tuple(P.CONSUMED_ARCHIVES)
    days = _archive_days(names)
    for name in names:
        _write_price_archive(
            os.path.join(prices_2019, name),
            [["1101 台泥", days[name], "37.0", "37.5", "1234"]])

    import pandas as pd
    rows = [{"stock_id": "1101", "date": d, "open": 30.0, "close": 31.0,
             "Trading_Volume": 1000.0}
            for d in PRE_2019_SESSIONS + (QUARANTINED_CACHE_ROW,)]
    pd.DataFrame(rows).to_parquet(
        os.path.join(prices_pre, "1101.parquet"), index=False)

    sessions = sorted(set(PRE_2019_SESSIONS) | set(days.values()))
    _calendar_dir(calendar, sessions)
    return SimpleNamespace(root=root, calendar=calendar,
                           prices_2019=prices_2019, prices_pre=prices_pre,
                           archive_days=days, sessions=tuple(sessions))


@pytest.fixture
def surfaces(sources, monkeypatch):
    """`sources`, with the prices family's byte-pinned declaration re-pointed.

    `build_prices_leaf` declares each archive by its `raw_sha256` — correctly:
    same name, different bytes is a different source. Synthetic archives can
    never carry the real hashes, so the declaration is rebuilt from itself with
    the synthetic bytes and the measured span substituted.
    """
    declarations = getattr(P, "CONSUMED_ARCHIVE_DECLARATIONS", None)
    if declarations is not None:
        aligned = {}
        for name, declared in declarations.items():
            entry = dict(declared)
            entry["raw_sha256"] = file_sha256(
                os.path.join(sources.prices_2019, name))
            if "covers" in entry:
                day = sources.archive_days[name]
                entry["covers"] = (day, day)
            aligned[name] = entry
        monkeypatch.setattr(P, "CONSUMED_ARCHIVE_DECLARATIONS", aligned)
        monkeypatch.setattr(P, "CONSUMED_ARCHIVES", tuple(aligned))

        # The SEALED CONTRACT's own record of those same bytes is re-pointed for
        # exactly the same reason. `build` now reconciles the declared set
        # against `price_source_contract.json`, which names the two composed
        # archives by hash — and a synthetic archive can no more carry the
        # contract's hashes than it can carry the declaration's.
        #
        # Only `upstream_zips` is substituted. `content_sha256` stays real,
        # because it is what a beyond-contract allowance is keyed to, and
        # `date_max` stays real, because the 2026-08 archive must still be seen
        # to reach past it — substituting either would make this fixture pass
        # for a reason the production path does not have.
        loader = getattr(P, "sealed_contract_payload", None)
        if loader is not None:
            payload = loader()
            payload["upstream_zips"] = {
                name: aligned[name]["raw_sha256"]
                for name in payload["upstream_zips"] if name in aligned}
            monkeypatch.setattr(P, "sealed_contract_payload",
                                lambda path="", _p=payload: _p)
    return sources


def _capture_date() -> str:
    return C._taipei_today().isoformat()


def _kwargs(surfaces, staging_root, *, calendar_source=None,
            final_run_dir=FINAL_RUN_DIR) -> dict:
    day = _capture_date()
    return dict(
        prior_attempt_id="L3-FLOOR-CAPTURE-%s-A01" % day.replace("-", ""),
        capture_date=day,
        calendar_source=calendar_source or surfaces.calendar,
        prices_2019_source=surfaces.prices_2019,
        prices_pre_2019_source=surfaces.prices_pre,
        final_run_dir=final_run_dir,
        staging_root=staging_root,
        repo_root=REPO)


def _staging(name: str) -> str:
    path = os.path.join(SCRATCH_ROOT, "staging", name)
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)
    return path


def _files_under(root: str) -> list:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            out.append(os.path.relpath(os.path.join(dirpath, name),
                                       root).replace("\\", "/"))
    return sorted(out)


# --- the path itself -------------------------------------------------------------

def test_the_no_publication_path_completes_and_cleans_up_after_ITSELF(surfaces):
    """The success case, and the only case in which deleting the tree is right."""
    staging = _staging("success")
    result = C.prepare_floor_capture(**_kwargs(surfaces, staging))

    assert result["evidence_class"] == "UNSEALED_DIAGNOSTIC"
    assert result["formal_publication_performed"] is False
    assert result["lineage_price_floor"] == min(PRE_2019_SESSIONS)
    assert result["lineage_price_floor"] in surfaces.sessions
    # Success — and ONLY success — removes the staging tree.
    assert _files_under(staging) == []


# --- D1 · a failure preserves the evidence the contract names ----------------------

def test_D1_the_floor_session_mismatch_preserves_its_evidence(surfaces,
                                                              monkeypatch):
    """The mismatch this whole path exists to detect must leave more than a trace.

    `assert_floor_is_a_trading_session` is forced to disagree — the shape
    `FAILED_CAPTURE_PRESERVATION` was written for. The old `finally` deleted the
    staged leaves, the aggregate and the snapshot inventory at exactly that
    moment.
    """
    def _mismatch(floor, sessions):
        raise LineageCaptureError(
            "abort: the observed floor %s is not a session in the declared "
            "calendar." % floor)

    monkeypatch.setattr(C, "assert_floor_is_a_trading_session", _mismatch)
    staging = _staging("floor_mismatch")

    with pytest.raises(LineageCaptureError) as excinfo:
        C.prepare_floor_capture(**_kwargs(surfaces, staging))

    # The exception TYPE is unchanged — a mismatch is still a LineageCaptureError
    # — and it carries the reported location rather than replacing the message.
    preserved = getattr(excinfo.value, "preserved_evidence", None)
    assert preserved is not None, "the failure reported no preserved evidence"
    directory = preserved["preserved_directory"]
    assert os.path.isdir(directory)
    # Stable and derived from the attempt id, not a random tempdir name.
    assert directory.replace("/", os.sep).endswith(
        os.path.join(C.PRESERVED_FAILURE_DIRNAME, preserved["run_id"]))

    present = _files_under(directory)
    assert any(p.endswith(LEAF_FILENAME % "prices") for p in present), present
    assert any(p.endswith(LEAF_FILENAME % "calendar") for p in present), present
    assert any(p.endswith(AGGREGATE_FILENAME) for p in present), present
    assert C.FAILURE_EVIDENCE_FILENAME in present

    with open(os.path.join(directory, C.FAILURE_EVIDENCE_FILENAME),
              encoding="utf-8") as fh:
        evidence = json.load(fh)
    assert evidence["error_type"] == "LineageCaptureError"
    assert "not a session in the declared calendar" in evidence["error_message"]
    assert evidence["traceback"]
    # Every clause of the contract, checked and answered — not asserted in prose.
    assert evidence["preservation_contract"] == list(FAILED_CAPTURE_PRESERVATION)
    assert evidence["preservation_contract_satisfied"] == {
        clause: True for clause in FAILED_CAPTURE_PRESERVATION}
    assert preserved["preservation_complete"] is True

    # "no lineage directory is created" and "no capture record is written",
    # verified against the tree rather than trusted.
    assert not any(CAPTURE_FILENAME in p for p in present)
    assert not any("/".join(LINEAGE_ROOT_PARTS) in p for p in present)


def test_D1_a_real_off_calendar_failure_preserves_the_same_evidence(surfaces):
    """Not only the forced case: the natural refusal one guard earlier.

    `assert_prices_are_on_calendar` fires when a price row lands on a day the
    declared calendar does not have. Same `try` block, same destroyed evidence.
    """
    day = sorted(surfaces.archive_days.values())[0]
    short_calendar = _calendar_dir(
        os.path.join(SCRATCH_ROOT, "sources", "calendar_missing_session"),
        [s for s in surfaces.sessions if s != day])
    staging = _staging("off_calendar")

    with pytest.raises(LineageCaptureError) as excinfo:
        C.prepare_floor_capture(**_kwargs(surfaces, staging,
                                          calendar_source=short_calendar))

    assert "not sessions in the declared calendar" in str(excinfo.value)
    directory = excinfo.value.preserved_evidence["preserved_directory"]
    present = _files_under(directory)
    assert any(p.endswith(LEAF_FILENAME % "prices") for p in present)
    assert any(p.endswith(AGGREGATE_FILENAME) for p in present)
    assert C.FAILURE_EVIDENCE_FILENAME in present


def test_D1_preserved_evidence_is_never_overwritten_by_a_reused_attempt_id(
        surfaces, monkeypatch):
    """`the attempt id is never reused or cleared` — so neither is its evidence."""
    def _mismatch(floor, sessions):
        raise LineageCaptureError("abort: forced floor/session mismatch")

    monkeypatch.setattr(C, "assert_floor_is_a_trading_session", _mismatch)
    staging = _staging("reused_attempt_id")

    with pytest.raises(LineageCaptureError) as first:
        C.prepare_floor_capture(**_kwargs(surfaces, staging))
    directory = first.value.preserved_evidence["preserved_directory"]
    original = {p: file_sha256(os.path.join(directory, p))
                for p in _files_under(directory)}

    with pytest.raises(LineageCaptureError) as second:
        C.prepare_floor_capture(**_kwargs(surfaces, staging))

    # The second attempt carries the same run id (same prior attempt), so its
    # evidence may not land on top of the first's.
    assert second.value.preserved_evidence["staged_tree_relocated"] is False
    assert second.value.preserved_evidence["preserved_directory"] != directory
    surviving = {p: file_sha256(os.path.join(directory, p))
                 for p in _files_under(directory)}
    assert surviving == original
    assert any("already exists" in n or "could not relocate" in n
               for n in second.value.preserved_evidence["notes"])


# --- D2 · a declaration must be reconcilable with what was READ --------------------

def _leaf_pair(surfaces, staging_name):
    """A read leaf and its re-addressed planned twin, built the way the module does."""
    stage = os.path.join(SCRATCH_ROOT, "d2", staging_name)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    snapshot = C.snapshot_directory(surfaces.calendar,
                                    os.path.join(stage, "calendar"),
                                    extensions=(".parquet",))
    staged = os.path.join(stage, "calendar")
    declared = os.path.join(FINAL_RUN_DIR, "inputs", "calendar")
    day = _capture_date()
    read_leaf = F.build("calendar", "L3-FLOOR-CAPTURE-20260101-A02", day,
                        landing_dir=staged, observed_at="2026-01-01T00:00:00+08:00")
    planned_leaf = F.build("calendar", "L3-FLOOR-CAPTURE-20260101-A02", day,
                           landing_dir=staged, declared_landing_dir=declared,
                           observed_at="2026-01-01T00:00:00+08:00")
    return SimpleNamespace(read=read_leaf, planned=planned_leaf,
                           snapshot=snapshot, staged=staged, declared=declared)


def test_D2_a_faithful_re_declaration_reconciles(surfaces):
    """The honest case: only the ADDRESS changed, and the record says so in band."""
    pair = _leaf_pair(surfaces, "faithful")
    record = C.assert_declaration_reconciles(
        dataset="calendar", read_leaf=pair.read, planned_leaf=pair.planned,
        requested_declarations=(pair.declared,), snapshots=(pair.snapshot,),
        repo_root=REPO)

    assert record["reconciliation"] == C.DECLARATION_RECONCILIATION
    assert record["declared_directories_verified_directly"] is False
    only = record["declarations"][0]
    assert only["read_from_staging_directory"] == pair.staged.replace("\\", "/")
    assert only["snapshot_raw_inventory_digest"] == \
        pair.snapshot["raw_inventory_digest"]
    assert not os.path.isabs(only["declared_landing_directory"])
    assert [m["locator"] for m in only["members"]] == ["taiex_daily.parquet"]


def test_D2_a_declaration_whose_hashes_disagree_with_the_read_is_refused(
        surfaces):
    """The case the string-only guard passed.

    The staging path is fully substituted out — which is exactly what the old
    `root in json.dumps(leaf)` test checked — and the manifest still declares
    bytes that were never read.
    """
    pair = _leaf_pair(surfaces, "tampered_hash")
    tampered = json.loads(json.dumps(pair.planned))
    tampered["entries"][0]["raw_sha256"] = "0" * 64

    # The old guard would have been satisfied: the staging root is gone.
    assert pair.staged.replace("\\", "/") not in json.dumps(tampered)

    with pytest.raises(C.FloorCapturePreparationError) as excinfo:
        C.assert_declaration_reconciles(
            dataset="calendar", read_leaf=pair.read, planned_leaf=tampered,
            requested_declarations=(pair.declared,), snapshots=(pair.snapshot,),
            repo_root=REPO)
    assert "not the read leaf re-addressed" in str(excinfo.value)


def test_D2_a_declaration_covering_a_member_nobody_read_is_refused(surfaces):
    """A declared member that is not in the staged directory is not a declaration."""
    pair = _leaf_pair(surfaces, "extra_member")
    extra = json.loads(json.dumps(pair.planned))
    ghost = dict(extra["entries"][0])
    ghost["locator"] = "never_read.parquet"
    extra["entries"].append(ghost)
    read = json.loads(json.dumps(pair.read))
    read["entries"].append(dict(ghost))

    with pytest.raises(C.FloorCapturePreparationError) as excinfo:
        C.assert_declaration_reconciles(
            dataset="calendar", read_leaf=read, planned_leaf=extra,
            requested_declarations=(pair.declared,), snapshots=(pair.snapshot,),
            repo_root=REPO)
    assert "do not enumerate the same members" in str(excinfo.value)


def test_D2_a_declared_address_the_caller_never_asked_for_is_refused(surfaces):
    """The substitution must land where the caller said, not merely somewhere."""
    pair = _leaf_pair(surfaces, "wrong_address")
    with pytest.raises(C.FloorCapturePreparationError) as excinfo:
        C.assert_declaration_reconciles(
            dataset="calendar", read_leaf=pair.read, planned_leaf=pair.planned,
            requested_declarations=(os.path.join(FINAL_RUN_DIR, "inputs",
                                                 "somewhere_else"),),
            snapshots=(pair.snapshot,), repo_root=REPO)
    assert "the caller never asked to declare" in str(excinfo.value)


def test_D2_a_declaration_with_no_snapshot_provenance_is_refused(surfaces):
    """Without the snapshot record the chain source -> bytes -> address is broken."""
    pair = _leaf_pair(surfaces, "no_snapshot")
    with pytest.raises(C.FloorCapturePreparationError) as excinfo:
        C.assert_declaration_reconciles(
            dataset="calendar", read_leaf=pair.read, planned_leaf=pair.planned,
            requested_declarations=(pair.declared,), snapshots=(),
            repo_root=REPO)
    assert "immutable source snapshots" in str(excinfo.value)


def test_D2_the_runner_refuses_a_planned_leaf_that_re_enumerated(surfaces,
                                                                 monkeypatch):
    """End to end: the reconciliation is wired into `prepare_floor_capture`.

    `build_flat_leaves.build` is made to alter one hash on the PLANNED pass only
    (the pass that supplies `declared_landing_dir`), which is the shape of a
    manifest describing a directory nobody read.
    """
    real = F.build

    def _shim(dataset, run_id, as_of, landing_dir="", declared_landing_dir="",
              observed_at=""):
        leaf = real(dataset, run_id, as_of, landing_dir=landing_dir,
                    declared_landing_dir=declared_landing_dir,
                    observed_at=observed_at)
        if declared_landing_dir:
            leaf = json.loads(json.dumps(leaf))
            leaf["entries"][0]["raw_sha256"] = "1" * 64
        return leaf

    monkeypatch.setattr(F, "build", _shim)
    staging = _staging("d2_end_to_end")

    with pytest.raises(C.FloorCapturePreparationError) as excinfo:
        C.prepare_floor_capture(**_kwargs(surfaces, staging))
    assert "not the read leaf re-addressed" in str(excinfo.value)
    # And D1 still holds for this failure too.
    assert os.path.isdir(excinfo.value.preserved_evidence["preserved_directory"])


def test_D2_the_vacuous_string_guard_is_gone(surfaces):
    """The guard it replaced could not fail for the reason it existed."""
    source = open(os.path.join(REPO, "research", "b0_l3_runner",
                               "capture_l3_floor.py"), encoding="utf-8").read()
    assert "planned manifest retains a private staging path" not in source
    assert "assert_declaration_reconciles" in C.__all__


def test_D2_the_runner_records_the_provenance_it_asserted(surfaces):
    """The reconciliation is not only performed, it is reported."""
    staging = _staging("d2_provenance")
    result = C.prepare_floor_capture(**_kwargs(surfaces, staging))

    provenance = result["declaration_provenance"]
    assert sorted(provenance) == ["calendar", "prices"]
    for dataset, record in provenance.items():
        assert record["reconciliation"] == C.DECLARATION_RECONCILIATION
        assert record["declared_directories_verified_directly"] is False
        for declaration in record["declarations"]:
            assert declaration["members"]
            assert declaration["snapshot_raw_inventory_digest"]
            assert not os.path.isabs(
                declaration["declared_landing_directory"])
    # prices declares BOTH legs' addresses; §2.8.3 splits them across two trees.
    assert len(provenance["prices"]["declarations"]) == 2


# --- D3 · a machine-local digest may not read as evidence --------------------------

def test_D3_the_validation_digest_is_labelled_and_no_longer_a_headline(surfaces):
    staging = _staging("d3")
    result = C.prepare_floor_capture(**_kwargs(surfaces, staging))

    # The name a consumer used to reach for is gone, so an old indexer fails
    # loudly instead of quoting a value that means nothing.
    assert "validation_aggregate_payload_sha256" not in result
    assert "validation_aggregate_raw_sha256" not in result

    notice = result["non_reproducible_validation_digests"]
    assert notice["reproducibility"] == "NON_REPRODUCIBLE_MACHINE_LOCAL_PATHS"
    assert notice["admissible_as_capture_evidence"] is False
    assert notice["why"]
    assert notice["compare_instead"] == ["planned_leaf_payload_sha256",
                                         "planned_aggregate_payload_sha256"]
    assert len(notice["aggregate_payload_sha256_non_reproducible"]) == 64
    assert len(notice["aggregate_raw_sha256_non_reproducible"]) == 64


def test_D3_the_label_is_true_the_planned_digests_are_the_stable_ones(
        surfaces, monkeypatch):
    """Two runs of the same bytes at the same instant, in two staging roots.

    Holding `observed_at` fixed isolates the ONE variable the label is about:
    the path. The planned digests declare repo-relative addresses and agree; the
    validation digests declare the tempdir they were read from and cannot.
    """
    fixed = dt.datetime.combine(C._taipei_today(), dt.time(9, 0),
                                tzinfo=C.CAPTURE_TIMEZONE)
    monkeypatch.setattr(C, "_taipei_now", lambda: fixed)

    first = C.prepare_floor_capture(**_kwargs(surfaces, _staging("d3_a")))
    second = C.prepare_floor_capture(**_kwargs(surfaces, _staging("d3_b")))

    assert first["planned_leaf_payload_sha256"] == \
        second["planned_leaf_payload_sha256"]
    assert first["planned_aggregate_payload_sha256"] == \
        second["planned_aggregate_payload_sha256"]

    a = first["non_reproducible_validation_digests"]
    b = second["non_reproducible_validation_digests"]
    assert a["aggregate_payload_sha256_non_reproducible"] != \
        b["aggregate_payload_sha256_non_reproducible"]
    assert a["aggregate_raw_sha256_non_reproducible"] != \
        b["aggregate_raw_sha256_non_reproducible"]


# --- D4 · one definition of "today" ------------------------------------------------

def test_D4_today_is_asia_taipei_and_matches_the_prospective_runner():
    assert C.CAPTURE_TIMEZONE == ZoneInfo("Asia/Taipei")
    assert C._taipei_today() == dt.datetime.now(
        ZoneInfo("Asia/Taipei")).date()

    # The definition this module has to agree with, read from its source rather
    # than imported — `run_l3_prospective` pulls in the whole route.
    other = open(os.path.join(REPO, "research", "b0_l3_runner",
                              "run_l3_prospective.py"), encoding="utf-8").read()
    assert 'ZoneInfo("Asia/Taipei")' in other

    # Checked on the parsed module, not on its text: the prose that explains
    # the fix names the call it removed, and a substring test would read that
    # explanation as the defect.
    source = open(os.path.join(REPO, "research", "b0_l3_runner",
                               "capture_l3_floor.py"), encoding="utf-8").read()
    called = {node.func.attr for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)}
    assert "today" not in called, "the system-local clock is back"
    assert "now" in called                       # _taipei_now, which IS tz-aware


def test_D4_a_capture_date_that_is_not_the_taipei_day_is_refused(surfaces,
                                                                 monkeypatch):
    """The eight-hour window on a UTC host, made deterministic.

    `capture_date` is stamped into the run id and therefore into the lineage
    identity, so 'today' has to be the same day the decision intent will claim.
    """
    taipei_day = C._taipei_today()
    monkeypatch.setattr(C, "_taipei_today", lambda: taipei_day)
    yesterday = (taipei_day - dt.timedelta(days=1)).isoformat()

    kwargs = _kwargs(surfaces, _staging("d4"))
    kwargs["capture_date"] = yesterday
    with pytest.raises(C.FloorCapturePreparationError) as excinfo:
        C.prepare_floor_capture(**kwargs)
    assert "Asia/Taipei" in str(excinfo.value)
    assert yesterday in str(excinfo.value)


def test_D4_the_returned_record_names_the_clock_it_used(surfaces):
    result = C.prepare_floor_capture(**_kwargs(surfaces, _staging("d4_record")))
    assert result["capture_date_timezone"] == "Asia/Taipei"
    assert result["capture_date"] == C._taipei_today().isoformat()
