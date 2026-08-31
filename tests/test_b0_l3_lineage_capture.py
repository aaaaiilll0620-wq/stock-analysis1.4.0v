"""§20 · C-70 — the lineage floor capture contract.

CONTRACT ONLY. Nothing here reads a price, builds a leaf, captures a floor or
runs a route; every test works on tmp_path and on constructed basis dicts.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.b0_l3_lineage_capture import (                          # noqa: E402
    CAPTURE_AUTHORITY, CAPTURE_FILENAME, DIAGNOSTIC_EVIDENCE_CLASS,
    DIAGNOSTIC_EXPECTED_FLOOR, LINEAGE_BASIS_FIELDS, LineageCaptureError,
    PLACEHOLDER_ROUTE_SEAL_IDS, PURPOSE_CAPTURE, PURPOSE_DIAGNOSTIC,
    FLOOR_CAPTURE_REQUIRED_DATASETS, PURPOSE_PRODUCTION,
    RATIFIED_INVENTORY_AUTHORITY, ROUTE_SEAL_CONTRACT_STATUS,
    assert_capture_run_id, assert_floor_matches_expected,
    assert_inventory_is_ratified, assert_leg_summaries, assert_lineage_id,
    assert_manifest_binding, assert_no_decision_fields, assert_record_is_admissible,
    assert_receipt_names_its_lineage, assert_repo_identity, build_capture_record,
    capture_lineage_floor, capture_path, create_lineage_dir_exclusively,
    display_alias, lineage_basis, lineage_id_from_basis,
    derive_leg_summaries, load_and_verify_capture_record, next_attempt_run_id,
    write_capture_record_exclusively,
)

RUN = "L3-FLOOR-CAPTURE-20260826-A01"
AS_OF = "2026-08-26"
SHA = "a" * 64


def _basis(**over):
    b = {f: "x" for f in LINEAGE_BASIS_FIELDS}
    b.update({"capture_run_id": RUN, "as_of": AS_OF,
              "lineage_price_floor": DIAGNOSTIC_EXPECTED_FLOOR,
              "price_leaf_payload_sha256": SHA,
              "aggregate_manifest_payload_sha256": SHA,
              "repo_commit_sha": "0" * 40})
    b.update(over)
    return b


# --- §20.2 · the chain is one-way ------------------------------------------------

def test_a_capture_manifest_may_not_name_a_route_seal():
    """The seal binds the capture record; binding both ways is a deadlock."""
    assert assert_manifest_binding(
        PURPOSE_CAPTURE, capture_authority=CAPTURE_AUTHORITY) == PURPOSE_CAPTURE
    for seal in ("PENDING", "", "L3SEAL-0123456789abcdef"):
        with pytest.raises(LineageCaptureError, match="route_seal_id"):
            assert_manifest_binding(PURPOSE_CAPTURE, route_seal_id=seal,
                                    capture_authority=CAPTURE_AUTHORITY)


def test_a_capture_manifest_must_bind_the_c70_authority():
    with pytest.raises(LineageCaptureError, match="capture authority"):
        assert_manifest_binding(PURPOSE_CAPTURE, capture_authority=None)
    with pytest.raises(LineageCaptureError, match="capture authority"):
        assert_manifest_binding(PURPOSE_CAPTURE, capture_authority="C-70")


@pytest.mark.parametrize("placeholder", PLACEHOLDER_ROUTE_SEAL_IDS)
def test_a_production_manifest_refuses_every_placeholder_seal(placeholder):
    """A placeholder is not a weaker binding, it is a false one."""
    with pytest.raises(LineageCaptureError, match="placeholder"):
        assert_manifest_binding(PURPOSE_PRODUCTION, route_seal_id=placeholder)


def test_a_plausible_string_is_not_a_seal():
    """The hole this closes: 'not in the denylist' admitted "x"."""
    for not_a_seal in ("x", "seal-abc123", "L3SEAL-nothex", "L3SEAL-" + "0" * 63):
        with pytest.raises(LineageCaptureError, match="content-addressed|placeholder"):
            assert_manifest_binding(PURPOSE_PRODUCTION, route_seal_id=not_a_seal)


def test_a_well_formed_seal_still_fails_closed_until_the_contract_is_ratified(tmp_path):
    """Right form, right artefact, right digest — and still refused, because no
    seal contract exists to admit it yet."""
    from core.b0_canonical_hash import file_sha256

    art = tmp_path / "seal.json"
    art.write_text("{}", encoding="utf-8")
    sid = "L3SEAL-" + file_sha256(str(art))
    with pytest.raises(LineageCaptureError, match=ROUTE_SEAL_CONTRACT_STATUS):
        assert_manifest_binding(PURPOSE_PRODUCTION, route_seal_id=sid,
                                route_seal_artifact=str(art))
    with pytest.raises(LineageCaptureError, match="does not match its artefact"):
        assert_manifest_binding(PURPOSE_PRODUCTION,
                                route_seal_id="L3SEAL-" + "a" * 64,
                                route_seal_artifact=str(art))
    with pytest.raises(LineageCaptureError, match="names no artefact"):
        assert_manifest_binding(PURPOSE_PRODUCTION, route_seal_id=sid)


def test_a_production_manifest_may_not_stand_on_the_capture_authority():
    with pytest.raises(LineageCaptureError, match="capture authority"):
        assert_manifest_binding(PURPOSE_PRODUCTION, route_seal_id="L3SEAL-" + "a" * 64,
                                capture_authority=CAPTURE_AUTHORITY)


def test_a_diagnostic_run_borrows_nothing():
    """A reader fixture is not a lineage event."""
    assert assert_manifest_binding(PURPOSE_DIAGNOSTIC) == PURPOSE_DIAGNOSTIC
    assert DIAGNOSTIC_EVIDENCE_CLASS == "NOT_L3_EVIDENCE"
    for kw in ({"route_seal_id": "L3SEAL-" + "a" * 64},
               {"capture_authority": CAPTURE_AUTHORITY},
               {"lineage_id": "L3-" + "a" * 64},
               {"capture_record_sha256": "a" * 64}):
        with pytest.raises(LineageCaptureError, match="may not bind"):
            assert_manifest_binding(PURPOSE_DIAGNOSTIC, **kw)


def test_an_unknown_purpose_is_not_a_default():
    with pytest.raises(LineageCaptureError, match="purpose"):
        assert_manifest_binding("SOMETHING_ELSE", route_seal_id="L3SEAL-x")


def test_a_period_receipt_must_name_the_capture_that_froze_its_floor():
    ok = {"lineage_id": lineage_id_from_basis(_basis()),
          "capture_record_sha256": SHA,
          "lineage_price_floor": "2004-01-02",
          "observed_price_coverage_floor": "2004-01-02"}
    assert_receipt_names_its_lineage(ok)
    for drop in ("lineage_id", "capture_record_sha256"):
        with pytest.raises(LineageCaptureError, match="does not bind"):
            assert_receipt_names_its_lineage({k: v for k, v in ok.items()
                                              if k != drop})


# --- §20.4 · identity -------------------------------------------------------------

def test_the_lineage_id_is_derived_and_deterministic():
    a, b = lineage_id_from_basis(_basis()), lineage_id_from_basis(_basis())
    assert a == b == assert_lineage_id(a)
    assert len(a) == len("L3-") + 64


def test_a_different_floor_names_a_different_lineage():
    assert lineage_id_from_basis(_basis()) != \
        lineage_id_from_basis(_basis(lineage_price_floor="2013-01-01"))


def test_the_basis_may_not_contain_what_is_derived_from_it():
    """Otherwise the identity depends on itself."""
    lid = lineage_id_from_basis(_basis())
    for field, value in (("lineage_id", lid), ("lineage_basis_sha256", SHA),
                         ("route_seal_id", "L3SEAL-x")):
        with pytest.raises(LineageCaptureError, match="lineage basis"):
            lineage_basis(**_basis(**{field: value}))


def test_the_basis_is_exactly_the_declared_fields():
    with pytest.raises(LineageCaptureError, match="missing"):
        lineage_basis(**{k: v for k, v in _basis().items() if k != "as_of"})
    with pytest.raises(LineageCaptureError, match="unexpected"):
        lineage_basis(**dict(_basis(), extra_thought="maybe"))


def test_the_short_alias_is_display_only():
    lid = lineage_id_from_basis(_basis())
    alias = display_alias(lid)
    assert alias == lid[:19] and len(alias) < len(lid)
    with pytest.raises(LineageCaptureError, match="display alias"):
        assert_lineage_id(alias)


# --- §20.5 · a capture is ONE transaction, and the writer does not trust it ------

def _full_basis(**over):
    b = {f: SHA for f in LINEAGE_BASIS_FIELDS}
    b.update({"contract_version": "L3_LINEAGE_FLOOR_CAPTURE_CONTRACT_V1",
              "capture_authority": CAPTURE_AUTHORITY,
              "capture_run_id": RUN, "as_of": AS_OF,
              "lineage_price_floor": DIAGNOSTIC_EXPECTED_FLOOR,
              "master_version": "1.35",
              "repo_commit_sha": "0" * 40,
              "leg_summaries": _legs()})
    b.update(over)
    return b


def _legs():
    return [{"leg": "pre-2019", "entry_count": 2300, "inventory_digest": SHA,
             "leg_floor": "2004-01-02", "quarantine_boundary": "2019-01-01",
             "rows_dropped_by_quarantine": 3349771, "admissible_rows": 5660136},
            {"leg": "2019+", "entry_count": 2, "inventory_digest": SHA,
             "leg_floor": "2019-01-02", "quarantine_boundary": "2019-01-01",
             "rows_dropped_by_quarantine": 0, "admissible_rows": 3470627}]


def _capture(root, **over):
    kw = dict(basis=_full_basis(), capture_date="2026-08-27",
              required_datasets_provenance=RATIFIED_INVENTORY_AUTHORITY,
              tracked_clean=True, untracked_clean=True)
    kw.update(over)
    return capture_lineage_floor(root, **kw)


def test_the_capture_transaction_is_the_way_in(tmp_path):
    root = str(tmp_path / "artifacts")
    out = _capture(root)
    assert os.path.basename(out["path"]) == CAPTURE_FILENAME
    assert out["record"]["lineage_id"].startswith("L3-")
    assert len(out["payload_sha256"]) == 64 and len(out["raw_sha256"]) == 64
    with pytest.raises(LineageCaptureError, match="already exists"):
        _capture(root)


@pytest.mark.parametrize("over,match", [
    ({"basis": {"lineage_price_floor": "2013-01-01"}}, "STOP"),
    ({"basis": {"repo_commit_sha": "309800fa"}}, "40-hex"),
    ({"basis": {"capture_run_id": "L3-FLOOR-CAPTURE-20260826-A1"}}, "capture run id"),
    ({"basis": {"price_leaf_payload_sha256": "nope"}}, "sha256 hex digest"),
    ({"basis": {"leg_summaries": "only-2019"}}, "missing"),
    ({"kw": {"tracked_clean": False}}, "not clean"),
    ({"kw": {"untracked_clean": False}}, "not clean"),
    ({"kw": {"required_datasets_provenance": "PROVISIONAL - owed by W4/A2"}},
     "PROVISIONAL"),
])
def test_the_transaction_creates_nothing_when_a_guard_fails(tmp_path, over, match):
    """§20.9: every refusal happens before the filesystem is touched."""
    root = str(tmp_path / "artifacts")
    kw = dict(over.get("kw", {}))
    basis_over = dict(over.get("basis", {}))
    if basis_over.get("leg_summaries") == "only-2019":
        basis_over["leg_summaries"] = [_legs()[1]]
    if basis_over:
        kw["basis"] = _full_basis(**basis_over)
    with pytest.raises(LineageCaptureError, match=match):
        _capture(root, **kw)
    assert not os.path.exists(os.path.join(root, "l3_run")), (
        "a failed capture must leave no lineage directory behind")


def test_the_low_level_writer_refuses_a_hand_made_record(tmp_path):
    """The writer is reachable directly, so it may not trust its caller.

    This is the hole the review found: floor 2013-01-01, a bogus run id, invalid
    digests and an abbreviated commit sha all reached disk.
    """
    root = str(tmp_path / "artifacts")
    good = build_capture_record(
        _full_basis(), capture_date="2026-08-27",
        required_datasets_provenance=RATIFIED_INVENTORY_AUTHORITY,
        tracked_clean=True, untracked_clean=True)
    create_lineage_dir_exclusively(root, good["lineage_id"])

    for mutate, match in (
            ({"lineage_price_floor": "2013-01-01"}, "not the digest of its own"),
            ({"capture_run_id": "whatever"}, "not the digest of its own"),
            ({"lineage_id": "L3-" + "b" * 64}, "not the digest of its own"),
            ({"manifest_purpose": PURPOSE_PRODUCTION}, "only a"),
            ({"route_seal_id": "L3SEAL-" + "a" * 64}, "may not name a route seal"),
            ({"decision_date": "2026-08-26"}, "carries no"),
            ({"tracked_clean": False}, "not clean"),
            ({"leg_summaries": []}, "not the digest of its own")):
        with pytest.raises(LineageCaptureError, match=match):
            write_capture_record_exclusively(root, {**good, **mutate})
    assert not os.path.exists(capture_path(root, good["lineage_id"])), (
        "no rejected record may reach disk")


def test_a_record_whose_identity_does_not_re_derive_is_refused():
    good = build_capture_record(
        _full_basis(), capture_date="2026-08-27",
        required_datasets_provenance=RATIFIED_INVENTORY_AUTHORITY,
        tracked_clean=True, untracked_clean=True)
    assert_record_is_admissible(good)
    with pytest.raises(LineageCaptureError, match="lineage_basis_sha256"):
        assert_record_is_admissible({**good, "lineage_basis_sha256": "c" * 64})


def test_the_record_carries_no_fabricated_decision(tmp_path):
    record = build_capture_record(_full_basis(), capture_date="2026-08-27")
    assert record["decision_date"] is None and record["execution_date"] is None
    assert record["route_seal_id"] is None
    assert record["performance_computed"] is False
    assert_no_decision_fields(record)
    with pytest.raises(LineageCaptureError, match="capture run carries no"):
        assert_no_decision_fields({**record, "decision_date": "2026-08-26"})


def test_the_lineage_directory_is_created_exclusively(tmp_path):
    lid = lineage_id_from_basis(_basis())
    root = str(tmp_path / "artifacts")
    made = create_lineage_dir_exclusively(root, lid)
    assert os.path.isdir(made)
    assert made.endswith(os.path.join("l3_run", "lineages", lid))
    with pytest.raises(LineageCaptureError, match="already exists"):
        create_lineage_dir_exclusively(root, lid)


# --- §20.3 / §20.8 · the record is verifiable, and the receipt is checked ----------

def test_a_written_record_verifies_and_a_tampered_one_does_not(tmp_path):
    root = str(tmp_path / "artifacts")
    out = _capture(root)
    loaded = load_and_verify_capture_record(out["path"])
    assert loaded["payload_sha256"] == out["payload_sha256"]
    assert loaded["record"]["lineage_id"] == out["record"]["lineage_id"]

    doc = json.load(open(out["path"], encoding="utf-8"))
    doc["lineage_price_floor"] = "2013-01-01"      # self-hash left stale
    open(out["path"], "w", encoding="utf-8").write(json.dumps(doc))
    with pytest.raises(LineageCaptureError, match="does not hash to its own"):
        load_and_verify_capture_record(out["path"])


def test_the_receipt_is_verified_against_the_record_not_its_shape(tmp_path):
    root = str(tmp_path / "artifacts")
    out = _capture(root)
    rec = out["record"]
    receipt = {"lineage_id": rec["lineage_id"],
               "capture_record_sha256": out["payload_sha256"],
               "lineage_price_floor": rec["lineage_price_floor"],
               "observed_price_coverage_floor": rec["lineage_price_floor"]}
    got = assert_receipt_names_its_lineage(receipt, capture_record_path=out["path"])
    assert got["verified"] == "AGAINST_THE_RECORD"

    with pytest.raises(LineageCaptureError, match="points at nothing"):
        assert_receipt_names_its_lineage({**receipt, "capture_record_sha256": SHA},
                                         capture_record_path=out["path"])
    with pytest.raises(LineageCaptureError, match="froze"):
        assert_receipt_names_its_lineage(
            {**receipt, "lineage_price_floor": "2013-01-01"},
            capture_record_path=out["path"])
    with pytest.raises(LineageCaptureError, match="names lineage"):
        assert_receipt_names_its_lineage(
            {**receipt, "lineage_id": "L3-" + "b" * 64},
            capture_record_path=out["path"])


def test_a_capture_refuses_a_provisional_inventory():
    assert assert_inventory_is_ratified(RATIFIED_INVENTORY_AUTHORITY)
    for bad in ("PROVISIONAL — owed by W4/A2 production-route inventory",
                "draft list", "TBD", ""):
        with pytest.raises(LineageCaptureError):
            assert_inventory_is_ratified(bad)


def test_the_manifest_floor_is_the_route_closure_inventory():
    """§20.8: the W4/A2 authority is not prose — it is a set that must match."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "research", "b0_l3"))
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "research", "b0_materializer"))
    from route_closure import REQUIRED_DATASET_FLOOR
    from source_ownership_manifest import REQUIRED_DATASETS

    assert set(REQUIRED_DATASETS) == set(REQUIRED_DATASET_FLOOR)
    assert "PROVISIONAL" not in RATIFIED_INVENTORY_AUTHORITY.upper() or False


def test_both_price_legs_must_be_summarised():
    assert_leg_summaries(_legs())
    with pytest.raises(LineageCaptureError, match="missing"):
        assert_leg_summaries([_legs()[1]])
    with pytest.raises(LineageCaptureError, match="entry_count"):
        assert_leg_summaries([{**_legs()[0], "entry_count": 0}, _legs()[1]])


def test_leg_summaries_are_derived_from_the_verified_leaf_and_rows():
    import pandas as pd

    leaf = {"entries": [
        {"locator": "1101.parquet", "raw_sha256": SHA,
         "disposition": "consumed", "leg": "pre-2019"},
        {"locator": "prices.zip", "raw_sha256": "b" * 64,
         "members": [{"name": "p.csv", "size": 1, "crc32": "00000000"}],
         "disposition": "consumed", "leg": "2019+"},
    ]}
    rows = pd.DataFrame({"date": ["2004-01-02", "2018-12-28",
                                       "2019-01-02", "2026-08-28"]})
    got = derive_leg_summaries(
        leaf, rows, rows_dropped_by_quarantine=7)
    assert [row["leg"] for row in got] == ["pre-2019", "2019+"]
    assert got[0]["admissible_rows"] == 2
    assert got[0]["rows_dropped_by_quarantine"] == 7
    assert got[1]["admissible_rows"] == 2
    assert got[1]["rows_dropped_by_quarantine"] == 0


# --- §20.6 · the capture run id ----------------------------------------------------

def test_the_capture_run_id_names_its_own_as_of():
    assert assert_capture_run_id(RUN, AS_OF) == 1
    with pytest.raises(LineageCaptureError, match="disagrees"):
        assert_capture_run_id(RUN, "2026-03-30")
    for bad in ("L3-FLOOR-CAPTURE-20260826", "CAPTURE-20260826-A01",
                "L3-FLOOR-CAPTURE-20260826-A1", ""):
        with pytest.raises(LineageCaptureError, match="capture run id"):
            assert_capture_run_id(bad, AS_OF)


def test_an_as_of_that_is_not_a_real_date_is_refused():
    """`2026-08-32` and `not-a-date` both look enough like one to pass a regex."""
    for bad in ("2026-08-32", "2026-13-01", "20260826", "not-a-date", ""):
        with pytest.raises(LineageCaptureError, match="ISO calendar date"):
            assert_capture_run_id("L3-FLOOR-CAPTURE-20260826-A01", bad)


def test_a_failed_attempt_is_never_reused():
    assert next_attempt_run_id(RUN) == "L3-FLOOR-CAPTURE-20260826-A02"
    assert next_attempt_run_id(next_attempt_run_id(RUN)) == \
        "L3-FLOOR-CAPTURE-20260826-A03"


def test_a_later_attempt_names_the_day_it_actually_reads_sources():
    assert next_attempt_run_id(RUN, capture_date="2026-08-29") == \
        "L3-FLOOR-CAPTURE-20260829-A02"
    with pytest.raises(LineageCaptureError, match="move backwards"):
        next_attempt_run_id(RUN, capture_date="2026-08-25")


def test_there_is_no_attempt_after_a99():
    """A100 does not match the run-id form; handing it back would produce a run
    id every later guard rejects."""
    with pytest.raises(LineageCaptureError, match="last attempt"):
        next_attempt_run_id("L3-FLOOR-CAPTURE-20260826-A99")


# --- §20.7 · repo identity ---------------------------------------------------------

def test_capture_requires_a_committed_clean_tree():
    full = "0" * 40
    assert assert_repo_identity(commit_sha=full, tracked_clean=True,
                                untracked_clean=True) == full
    with pytest.raises(LineageCaptureError, match="40-hex"):
        assert_repo_identity(commit_sha="bde9167e", tracked_clean=True,
                             untracked_clean=True)
    for tracked, untracked in ((False, True), (True, False)):
        with pytest.raises(LineageCaptureError, match="not clean"):
            assert_repo_identity(commit_sha=full, tracked_clean=tracked,
                                 untracked_clean=untracked)


# --- §20.9 · the stop check --------------------------------------------------------

def test_a_floor_mismatch_stops_before_anything_is_created(tmp_path):
    root = str(tmp_path / "artifacts")
    with pytest.raises(LineageCaptureError, match="STOP"):
        assert_floor_matches_expected("2013-01-01")
    assert not os.path.exists(root), (
        "a mismatch must leave no lineage directory behind")
    assert assert_floor_matches_expected(DIAGNOSTIC_EXPECTED_FLOOR) == \
        DIAGNOSTIC_EXPECTED_FLOOR


def test_the_expected_floor_is_a_check_not_a_frozen_constant():
    from core.b0_master_prereg import spec

    assert spec("l3_capture_diagnostic_expected_floor_is_normative") is False


def test_the_floor_capture_closure_is_its_own():
    """Not the production route's closure: a capture's correctness depends on
    the readers and the leaf builder, not on the decision layer."""
    from core.b0_l3_lineage_capture import (
        FLOOR_CAPTURE_CODE_CLOSURE, floor_capture_code_closure_sha256,
    )

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert "core/b0_l3_lineage_capture.py" in FLOOR_CAPTURE_CODE_CLOSURE
    assert "core/b0_l3_price_span.py" in FLOOR_CAPTURE_CODE_CLOSURE
    assert not any("decision" in p for p in FLOOR_CAPTURE_CODE_CLOSURE)
    for p in FLOOR_CAPTURE_CODE_CLOSURE:
        assert os.path.isfile(os.path.join(repo, p)), p
    assert len(floor_capture_code_closure_sha256(repo)) == 64


# --- §20.8 · C-71 · the floor's causal closure is fixed ---------------------------

def test_the_capture_inventory_is_exactly_the_floor_causal_closure():
    """Short OR long is a refusal. A01 was blocked by a `valuation` payload that
    cannot move the earliest admissible session; C-71 removes that gate without
    letting a caller choose its own list."""
    from core.b0_l3_lineage_capture import (
        FLOOR_CAPTURE_REQUIRED_DATASETS, assert_capture_inventory,
    )

    assert FLOOR_CAPTURE_REQUIRED_DATASETS == ("calendar", "prices")
    assert assert_capture_inventory(FLOOR_CAPTURE_REQUIRED_DATASETS) == \
        ("calendar", "prices")
    for wrong in (("prices",), ("calendar",), (), ("calendar", "prices", "valuation"),
                  ("calendar", "prices", "corporate_actions")):
        with pytest.raises(LineageCaptureError, match="reads exactly"):
            assert_capture_inventory(wrong)


def test_a_production_run_still_binds_all_nine_families():
    """C-71 narrows the CAPTURE inventory only."""
    from core.b0_l3_lineage_capture import PRODUCTION_INVENTORY_IS_UNCHANGED_BY_C71
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "research", "b0_l3"))
    from route_closure import REQUIRED_DATASET_FLOOR

    assert PRODUCTION_INVENTORY_IS_UNCHANGED_BY_C71 is True
    assert len(REQUIRED_DATASET_FLOOR) == 9
    assert set(FLOOR_CAPTURE_REQUIRED_DATASETS) < set(REQUIRED_DATASET_FLOOR)


def test_the_floor_must_be_a_declared_trading_session():
    from core.b0_l3_lineage_capture import assert_floor_is_a_trading_session

    sessions = ("2004-01-02", "2004-01-05", "2004-01-06")
    assert assert_floor_is_a_trading_session("2004-01-02", sessions) == "2004-01-02"
    with pytest.raises(LineageCaptureError, match="not a session"):
        assert_floor_is_a_trading_session("2004-01-03", sessions)   # a Saturday
    with pytest.raises(LineageCaptureError, match="YYYY-MM-DD"):
        assert_floor_is_a_trading_session("20040102", sessions)


def test_an_off_calendar_price_row_may_not_deepen_the_floor():
    from core.b0_l3_lineage_capture import assert_prices_are_on_calendar

    sessions = ("2004-01-02", "2004-01-05")
    assert assert_prices_are_on_calendar(["2004-01-05", "2004-01-02"], sessions) == 0
    with pytest.raises(LineageCaptureError, match="not sessions"):
        assert_prices_are_on_calendar(["2003-12-31", "2004-01-02"], sessions)


def test_the_d1_quarantine_is_a_rule_not_a_dataset_family():
    from core.b0_l3_lineage_capture import (
        D1_QUARANTINE_AUTHORITY, FLOOR_CAPTURE_CODE_CLOSURE,
        FLOOR_CAPTURE_REQUIRED_DATASETS,
    )

    assert D1_QUARANTINE_AUTHORITY["boundary"] == "2019-01-01"
    assert "not a dataset family" in D1_QUARANTINE_AUTHORITY["bound_by"]
    assert not any("quarantine" in d for d in FLOOR_CAPTURE_REQUIRED_DATASETS)
    assert "research/b0_materializer/build_prices_leaf.py" in FLOOR_CAPTURE_CODE_CLOSURE
    assert "research/b0_l3/l3_readers.py" in FLOOR_CAPTURE_CODE_CLOSURE


# --- P2-11 · publication is a rename, not a claim followed by a write -----------
#
# `write_capture_record_exclusively` claimed the FINAL path with O_EXCL and then
# wrote the bytes. An interruption between the two froze a ZERO-BYTE capture
# record at a lineage-scoped path that, by §20's own rule, may never be written
# again -- so a power loss could permanently destroy a lineage identity, and the
# only trace would be an empty file.

from core.b0_l3_lineage_capture import (                          # noqa: E402
    PARTIAL_PUBLICATION_SUFFIX, PUBLICATION_IS_ATOMIC_NO_REPLACE,
    publish_bytes_exclusively, publish_exclusively, rename_no_replace,
)


class _PowerLoss(RuntimeError):
    """Whatever kills a process between the claim and the last byte."""


def test_an_interrupted_publication_leaves_the_final_path_untouched(tmp_path):
    target = str(tmp_path / "record.json")

    def _die(_temporary):
        raise _PowerLoss("between the claim and the bytes")

    with pytest.raises(_PowerLoss):
        publish_exclusively(target, _die)

    assert not os.path.exists(target)
    assert os.listdir(str(tmp_path)) == [], "a temporary was left behind"

    publish_bytes_exclusively(target, b"whole\n")
    assert open(target, "rb").read() == b"whole\n"


def test_publication_never_replaces_an_existing_final_path(tmp_path):
    """The exclusivity guarantee had to survive the change, and does."""
    target = str(tmp_path / "record.json")
    publish_bytes_exclusively(target, b"first\n")

    with pytest.raises(FileExistsError):
        publish_bytes_exclusively(target, b"second\n")
    assert open(target, "rb").read() == b"first\n"
    assert os.listdir(str(tmp_path)) == ["record.json"]


def test_the_rename_itself_refuses_to_replace(tmp_path):
    """The guarantee is the rename, not the existence check above it.

    `os.rename` is no-replace on Windows and SILENTLY REPLACING on POSIX, so
    this is the one line whose behaviour is not portable by default.
    """
    source = tmp_path / "src"
    destination = tmp_path / "dst"
    source.write_bytes(b"new")
    destination.write_bytes(b"old")

    with pytest.raises(FileExistsError):
        rename_no_replace(str(source), str(destination))
    assert destination.read_bytes() == b"old"


def test_an_interrupted_capture_record_can_still_be_captured(tmp_path,
                                                             monkeypatch):
    """The defect at its worst: a lineage id nothing could ever write again."""
    import core.b0_l3_lineage_capture as lcap

    root = str(tmp_path / "artifacts")
    record = build_capture_record(
        _full_basis(), capture_date="2026-08-27",
        required_datasets_provenance=RATIFIED_INVENTORY_AUTHORITY,
        tracked_clean=True, untracked_clean=True)
    create_lineage_dir_exclusively(root, record["lineage_id"])
    path = capture_path(root, record["lineage_id"])

    def _die(_path, _writer):
        raise _PowerLoss("between the claim and the bytes")

    monkeypatch.setattr(lcap, "publish_exclusively", _die)
    with pytest.raises(_PowerLoss):
        write_capture_record_exclusively(root, record)
    monkeypatch.undo()

    assert not os.path.exists(path), "a zero-byte capture record survived"

    payload_sha, raw_sha = write_capture_record_exclusively(root, record)
    assert len(payload_sha) == 64 and len(raw_sha) == 64
    loaded = load_and_verify_capture_record(path)
    assert loaded["record"]["lineage_id"] == record["lineage_id"]

    with pytest.raises(LineageCaptureError, match="already exists"):
        write_capture_record_exclusively(root, record)
    assert not [f for f in os.listdir(os.path.dirname(path))
                if f.endswith(PARTIAL_PUBLICATION_SUFFIX)]


def test_the_capture_record_bytes_did_not_move(tmp_path):
    """The record's content is a lineage fact; publication may not touch it."""
    import json

    root = str(tmp_path / "artifacts")
    record = build_capture_record(
        _full_basis(), capture_date="2026-08-27",
        required_datasets_provenance=RATIFIED_INVENTORY_AUTHORITY,
        tracked_clean=True, untracked_clean=True)
    create_lineage_dir_exclusively(root, record["lineage_id"])
    write_capture_record_exclusively(root, record)

    from core.b0_canonical_hash import canonical_sha256

    body = {k: v for k, v in record.items()
            if k != "capture_record_payload_sha256"}
    body["capture_record_payload_sha256"] = canonical_sha256(body)
    expected = (json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True)
                + "\n").encode("utf-8")

    with open(capture_path(root, record["lineage_id"]), "rb") as fh:
        assert fh.read() == expected
    assert PUBLICATION_IS_ATOMIC_NO_REPLACE is True
