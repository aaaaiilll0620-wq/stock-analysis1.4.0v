"""C-53 · the opening-state seam, and C-52 · immutable seal retention.

Two closure rules with the same shape: something that used to be implicit is now
checkable, and the check is what stops it being abused. R2's danger is a generic
re-dating facility; R1's is an overwritten seal body.
"""

import json
import os
import sys

import pytest

from core.b0_master_prereg import spec
from core.b0_opening_state import (
    CANONICAL_OPENING_STATE_DATE,
    NORMALIZATION_PERIOD_INDEX,
    NORMALIZATION_SCOPE,
    PERMITTED_DATE_METADATA_FIELDS,
    PORTFOLIO_ECONOMIC_FIELDS,
    REGISTERED_OPENING_STATE_DATE,
    OpeningStateError,
    assert_not_a_generic_redater,
    assert_opening_state_normalization,
    canonical_opening_state,
    registered_opening_state,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

P1_RECEIPT = os.path.join(REPO, "research", "b0_materializer",
                          "period1_full_input_receipt.json")
LINEAGE = os.path.join(REPO, "research", "b0_registry",
                       "baseline_seal_lineage.jsonl")


def _pair(**over):
    reg = registered_opening_state("2014-07-31", 2_000_000.0)
    reg.update(over)
    return reg, canonical_opening_state(reg, "2014-07-30")


# --- C-53/R2 · the two datings ------------------------------------------------

def test_the_two_datings_are_named_in_the_specification():
    assert REGISTERED_OPENING_STATE_DATE == "window_start"
    assert CANONICAL_OPENING_STATE_DATE == "resolve_as_of(window_start)"
    assert NORMALIZATION_SCOPE == "period_1_opening_state_only"
    assert PERMITTED_DATE_METADATA_FIELDS == ("as_of",)
    assert set(PORTFOLIO_ECONOMIC_FIELDS) == {
        "cash", "shares", "pending_exit", "cash_dividend_receivable",
        "stock_dividend_receivable"}


def test_the_normalization_moves_the_date_and_nothing_else():
    reg, can = _pair()
    assert_opening_state_normalization(reg, can,
                                       period_index=NORMALIZATION_PERIOD_INDEX)
    assert can["as_of"] == "2014-07-30" and reg["as_of"] == "2014-07-31"
    for f in PORTFOLIO_ECONOMIC_FIELDS:
        assert reg[f] == can[f]


@pytest.mark.parametrize("field,value", [
    ("cash", 1.0),
    ("shares", {"1101": 1000}),
    ("pending_exit", {"1101": 500}),
    ("cash_dividend_receivable", 12.5),
    ("stock_dividend_receivable", {"1101": 100}),
])
def test_any_economic_difference_stops_the_normalization(field, value):
    reg, can = _pair()
    can = {**can, field: value}
    with pytest.raises(OpeningStateError, match="R2"):
        assert_opening_state_normalization(
            reg, can, period_index=NORMALIZATION_PERIOD_INDEX)


def test_an_opening_state_carrying_holdings_would_stop_the_normalization():
    """The rule is safe BECAUSE it is conditional, not because it is narrow."""
    reg, can = _pair(shares={"2330": 1000})
    # identical on both sides -> still admissible ...
    assert_opening_state_normalization(reg, can,
                                       period_index=NORMALIZATION_PERIOD_INDEX)
    # ... but any drift in those holdings is not
    with pytest.raises(OpeningStateError, match="shares"):
        assert_opening_state_normalization(
            reg, {**can, "shares": {"2330": 999}},
            period_index=NORMALIZATION_PERIOD_INDEX)


def test_only_period_1_may_be_normalized():
    reg, can = _pair()
    for t in (2, 7, 141):
        with pytest.raises(OpeningStateError, match="period_1_opening_state_only"):
            assert_opening_state_normalization(reg, can, period_index=t)


def test_the_canonical_date_must_be_strictly_earlier():
    reg, can = _pair()
    with pytest.raises(OpeningStateError, match="strictly before"):
        assert_opening_state_normalization(
            reg, {**can, "as_of": "2014-08-01"},
            period_index=NORMALIZATION_PERIOD_INDEX)


def test_a_normalization_may_not_add_or_drop_a_field():
    reg, can = _pair()
    with pytest.raises(OpeningStateError, match="same object"):
        assert_opening_state_normalization(
            reg, {**can, "margin": 0.0},
            period_index=NORMALIZATION_PERIOD_INDEX)


def test_no_generic_portfolio_redater_exists():
    """R2's last clause. This is the abuse the boundary rule must not enable."""
    assert_not_a_generic_redater("2014-07-31", "2014-07-31", is_opening_state=False)
    assert_not_a_generic_redater("2014-07-31", "2014-07-30", is_opening_state=True)
    with pytest.raises(OpeningStateError, match="only portfolio with two"):
        assert_not_a_generic_redater("2019-03-29", "2019-03-28",
                                     is_opening_state=False)


def test_both_opening_hashes_are_bound_in_the_receipt():
    if not os.path.exists(P1_RECEIPT):
        pytest.skip("period-1 full input not materialized")
    from core.b0_canonical_hash import canonical_sha256

    with open(P1_RECEIPT, encoding="utf-8") as fh:
        seam = json.load(fh)["opening_state_seam"]
    reg = registered_opening_state(spec("window_start"), spec("C_ref"))
    can = canonical_opening_state(reg, seam["canonical_opening_state_as_of"])
    assert seam["registered_opening_state_sha256"] == canonical_sha256(reg)
    assert seam["canonical_opening_state_sha256"] == canonical_sha256(can)
    assert seam["registered_opening_state_sha256"] != \
        seam["canonical_opening_state_sha256"], (
        "if the two hashes agreed there would be no seam to bind")
    assert seam["normalization_scope"] == NORMALIZATION_SCOPE


# --- C-52/R1 · immutable seal retention ---------------------------------------

def test_a_seal_body_may_not_be_overwritten(tmp_path, monkeypatch):
    import b0_baseline_seal as bs

    monkeypatch.setattr(bs, "SEAL_ARCHIVE", str(tmp_path / "seals"))
    monkeypatch.setattr(bs, "OUT_DIR", str(tmp_path))
    h = "a" * 64
    rec = {"baseline_seal_sha256": h, "seal": "B0_BASELINE_SEAL"}
    archive, pointer = bs.write_immutable(rec, h)
    assert os.path.basename(archive) == h + ".json"
    assert os.path.exists(pointer)
    with pytest.raises(bs.SealOverwrite, match="immutable"):
        bs.write_immutable(rec, h)


def test_the_archived_body_reopens_to_the_hash_its_name_claims(tmp_path, monkeypatch):
    import b0_baseline_seal as bs

    monkeypatch.setattr(bs, "SEAL_ARCHIVE", str(tmp_path / "seals"))
    monkeypatch.setattr(bs, "OUT_DIR", str(tmp_path))
    h = "b" * 64
    with pytest.raises(bs.SealOverwrite, match="does not reopen"):
        bs.write_immutable({"baseline_seal_sha256": "c" * 64}, h)


def test_the_lineage_ledger_records_supersession_truthfully():
    if not os.path.exists(LINEAGE):
        pytest.skip("no seal lineage recorded yet")
    with open(LINEAGE, encoding="utf-8") as fh:
        entries = [json.loads(l) for l in fh if l.strip()]
    assert entries, "the ledger must not be empty once a seal has been taken"
    assert [e["seq"] for e in entries] == list(range(1, len(entries) + 1))
    assert sum(1 for e in entries if e["state"] == "CURRENT") == 1
    for e in entries:
        assert e["l2_opened"] is False
        assert "historical_hash_recorded" in e
        assert "canonical_body_available" in e
        if not e["canonical_body_available"]:
            assert e["reason"], (
                "a lost body must say WHY it is lost, not merely that it is")
        else:
            assert os.path.exists(os.path.join(REPO, e["archive_path"]))
    lost = [e for e in entries if not e["canonical_body_available"]]
    for e in lost:
        assert "overwritten before immutable archival" in e["reason"]
        assert "baseline_seal_sha256" in e or "historical_hash_prefix" in e


def test_the_lost_predecessor_body_is_not_reconstructed():
    """C-52/R1: missing provenance is recorded, never fabricated."""
    if not os.path.exists(LINEAGE):
        pytest.skip("no seal lineage recorded yet")
    with open(LINEAGE, encoding="utf-8") as fh:
        entries = [json.loads(l) for l in fh if l.strip()]
    first = entries[0]
    assert first["historical_hash_recorded"] is True
    assert first["canonical_body_available"] is False
    assert "archive_path" not in first, (
        "a lost body must not claim an archive path")
    assert first.get("historical_hash_prefix") == "bdc69c32"
