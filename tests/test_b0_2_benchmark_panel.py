# -*- coding: utf-8 -*-
"""B0.2 · the acquired TWSE 0050 benchmark lineage (ruling R1-R11).

Evaluation-only data, acquired from the first-party exchange because the
previously sealed sources were insufficient. These tests pin the properties the
ruling actually requires, and the one gap it does not yet close.
"""
from __future__ import annotations

import json
import os

import pytest

pd = pytest.importorskip("pandas")

from core import b0_benchmark_construction as bc

REPO = bc.__file__.rsplit(os.sep + "core", 1)[0]
PANEL = os.path.join(REPO, "data", "b0", "benchmark_0050_panel.parquet")
DIST = os.path.join(REPO, "data", "b0", "benchmark_0050_distributions.csv")
UNIT = os.path.join(REPO, "data", "b0", "benchmark_0050_share_unit_events.parquet")
RECEIPT = os.path.join(REPO, "research", "b0_benchmark",
                       "benchmark_0050_panel_receipt.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(PANEL),
    reason="benchmark panel not materialized in this working tree")


def _panel():
    return pd.read_parquet(PANEL)


# --- R3 · market fields --------------------------------------------------------

def test_panel_carries_every_required_market_field():
    cols = set(_panel().columns)
    for c in ("session", "open", "high", "low", "close",
              "volume_shares", "traded_value"):
        assert c in cols, c


def test_traded_value_is_the_source_field_not_close_times_volume():
    """R3 forbids reconstructing dollar turnover. A reconstruction would agree
    exactly; real volume-weighted turnover does not."""
    df = _panel()
    rel = ((df.traded_value - df.close * df.volume_shares).abs()
           / df.traded_value)
    assert int((rel < 1e-9).sum()) == 0
    assert rel.median() > 1e-4


def test_panel_has_no_gaps_interpolation_or_nonpositive_values():
    df = _panel()
    assert df.session.is_unique
    assert df.session.is_monotonic_increasing
    for c in ("open", "high", "low", "close", "volume_shares", "traded_value"):
        assert df[c].notna().all()
        assert (df[c] > 0).all()
    assert (df.close.between(df.low, df.high)).all()
    assert (df.open.between(df.low, df.high)).all()


def test_r6_coverage_spans_the_horizon_with_lookback():
    """Enough history before the first execution for ADV20 and sigma20d."""
    df = _panel()
    assert df.session.min() <= "2014-05-01"      # lookback before 2014-08-01
    assert df.session.max() >= "2026-03-31"      # through the window end
    before = int((df.session < "2014-08-01").sum())
    assert before >= 21, before                  # sigma20d needs 21 closes


# --- R4 · distributions --------------------------------------------------------

def test_distributions_are_cash_only_and_dated():
    d = pd.read_csv(DIST)
    assert len(d) == 23
    assert (d.kind == "息").all()
    assert (d.cash_per_unit > 0).all()
    assert d.ex_date.is_monotonic_increasing


def test_payment_date_is_recorded_as_unacquired_not_invented():
    """R4 requires it and it was NOT obtained. It must not be back-filled."""
    d = pd.read_csv(DIST, keep_default_na=False)
    assert (d.payment_date == "").all()
    assert (d.payment_date_status
            == "NOT_ACQUIRED_NO_AUTHORITATIVE_MACHINE_READABLE_SOURCE").all()


def test_payment_date_cannot_change_benchmark_wealth():
    """Why the gap is recorded rather than guessed.

    Under B2 (cash earns no interest), B7 (never reinvested) and 2.5 (NAV
    includes the receivable), a distribution contributes its face amount to
    wealth from the ex-date onward whether it is sitting in `receivable` or in
    `cash`. Moving the payment date therefore moves value between two buckets
    that are both carried at face and neither of which compounds.

    Proved as a property over arbitrary payment-date assignments, so it does not
    depend on -- and does not compute -- any real benchmark wealth path.
    """
    ex_dates = ["2014-10-24", "2015-10-26", "2016-07-28"]
    amounts = [1.55, 2.00, 0.85]
    shares = 30_000

    def wealth(valuation, payment_dates):
        cash = receivable = 0.0
        for ex, amt, pay in zip(ex_dates, amounts, payment_dates):
            if ex <= valuation:
                if pay <= valuation:
                    cash += shares * amt          # credited
                else:
                    receivable += shares * amt    # still a claim
        return cash + receivable                  # both at face, B2/B7

    for valuation in ("2014-11-01", "2015-11-01", "2016-08-01", "2026-03-31"):
        immediate = wealth(valuation, ex_dates)                     # pay on ex
        late = wealth(valuation, ["2026-12-31"] * 3)                # pay after
        staggered = wealth(valuation, ["2014-12-01", "2015-12-01", "2016-09-01"])
        assert immediate == late == staggered


# --- R5 · share-unit transformation -------------------------------------------

def test_exactly_one_share_unit_event_in_the_horizon():
    u = pd.read_parquet(UNIT)
    assert len(u) == 1
    r = u.iloc[0]
    assert r.effective_date == "2025-06-18"
    assert r.twse_note.strip() == "**"


def test_the_split_ratio_is_four_by_twse_own_reference_arithmetic():
    """TWSE flags the resumption session and quotes the change against its OWN
    adjusted reference, so the ratio is first-party arithmetic, not an inference
    from the raw price jump. 188.65 / 4 = 47.1625 -> 47.16 at tick; no other
    integer ratio lands there."""
    u = pd.read_parquet(UNIT).iloc[0]
    df = _panel()
    row = df[df.session == "2025-06-18"].iloc[0]
    assert row.close == pytest.approx(47.57)
    twse_reference = round(u.prev_close / 4.0, 4)
    assert twse_reference == pytest.approx(47.1625)
    for wrong in (2, 3, 5, 10):
        assert abs(u.prev_close / wrong - 47.16) > 1.0


def test_split_is_vacuous_only_for_the_buy_date_statistics():
    """R4 is emphatic that the split is NOT economically vacuous.

    It is vacuous for the 2014-08-01 sigma20d/ADV20 lookback, eleven years
    earlier -- and for nothing else. The holder ledger carries it, which is what
    the R7 regressions cover.
    """
    u = pd.read_parquet(UNIT)
    assert (u.effective_date > "2014-08-01").all()
    assert bc.SHARE_UNIT_EVENTS_ARE_OUTCOME_REQUIRED is True


# --- R8 · seal-bindable receipt ------------------------------------------------

def test_receipt_binds_every_required_lineage_element():
    r = json.load(open(RECEIPT, encoding="utf-8"))
    for k in ("source_authority", "source_endpoint", "schema_sha256",
              "content_sha256", "coverage", "upstream_raw_sha256",
              "distributions_sha256", "share_unit_events_sha256"):
        assert r.get(k), k
    assert r["upstream_raw_count"] == 145
    assert len(r["upstream_raw_sha256"]) == 145
    assert r["evaluation_only"] is True
    assert r["not_added_to_selection_universe"] is True
    assert r["traded_value_reconstructed_from_close_times_volume"] is False


def test_receipt_content_hash_matches_the_panel_on_disk():
    import hashlib
    r = json.load(open(RECEIPT, encoding="utf-8"))
    actual = hashlib.sha256(open(PANEL, "rb").read()).hexdigest()
    assert actual == r["content_sha256"]


def test_0050_was_not_added_to_the_selection_universe():
    """R8 / R9: evaluation-only. The strategy universe must be untouched."""
    pp = pd.read_parquet(os.path.join(REPO, "data", "b0", "price_panel.parquet"))
    assert int((pp.stock_id.astype(str) == "0050").sum()) == 0
