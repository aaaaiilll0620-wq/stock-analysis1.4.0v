from pathlib import Path

import pandas as pd

from core import data_provider as dpmod
from scripts import build_dataexport_runtime_overlay as overlay_builder


def test_read_tej_merges_runtime_overlay_without_mutating_frozen_cache(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    overlay = tmp_path / "overlay"
    (frozen / "financial_statements").mkdir(parents=True)
    overlay.mkdir()
    pd.DataFrame({"stock_id": ["2330", "2330"],
                  "date": pd.to_datetime(["2026-03-01", "2026-06-01"]),
                  "eps": [10.0, 11.0]}).to_parquet(
        frozen / "financial_statements" / "2330.parquet", index=False)
    pd.DataFrame({"stock_id": ["2330", "2317"],
                  "date": pd.to_datetime(["2026-06-01", "2026-06-01"]),
                  "eps": [12.5, 3.0]}).to_parquet(
        overlay / "financial_statements.parquet", index=False)

    monkeypatch.setattr(dpmod, "TEJ_CACHE_DIR", str(frozen))
    monkeypatch.setattr(dpmod, "TEJ_RUNTIME_OVERLAY_DIR", str(overlay))
    dpmod.DataProvider._runtime_overlay_cache.clear()

    got = dpmod.DataProvider._read_tej("financial_statements", "2330")
    assert got["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-01", "2026-06-01"]
    assert got["eps"].tolist() == [10.0, 12.5]
    # frozen parquet 仍是原值，讀取 overlay 不回寫。
    assert pd.read_parquet(frozen / "financial_statements" / "2330.parquet")["eps"].tolist() == [10.0, 11.0]


def test_runtime_overlay_module_uses_auditable_financial_conflict_policy():
    source = Path(overlay_builder.__file__).read_text(encoding="utf-8")
    assert "later_source_mtime_wins_with_manifest_hash_receipt" in source
    assert "sources_in_precedence_order" in source


def _recent_weekdays(count):
    """The most recent `count` weekdays ending before today, oldest first.

    Derived from the runtime clock rather than written down, because
    `_read_local_price_valuation` drops a series whose newest date is more than
    7 calendar days old — a fixture with literal dates passes only until the
    calendar walks past them. Snapped to weekdays so the expected ordering is
    deterministic; the newest is at most 3 days back (today Monday -> Friday),
    which stays well inside that gate.
    """
    day = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    out = []
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day -= pd.Timedelta(days=1)
    return list(reversed(out))


def test_runtime_overlay_date_normalization_keeps_daily_union_sortable(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    overlay = tmp_path / "overlay"
    market = tmp_path / "market"
    (frozen / "price_valuation").mkdir(parents=True)
    (market / "price_valuation_daily").mkdir(parents=True)
    overlay.mkdir()

    early, mid, late = _recent_weekdays(3)
    # frozen TEJ parquet carries real datetimes ...
    pd.DataFrame({"stock_id": ["1213", "1213"], "date": [early, mid],
                  "close": [10.0, 11.0]}).to_parquet(
                      frozen / "price_valuation" / "1213.parquet", index=False)
    # ... while the collector's daily snapshot carries strings, and overlaps on `mid`.
    pd.DataFrame({"stock_id": ["1213", "1213"],
                  "date": [mid.strftime("%Y-%m-%d"), late.strftime("%Y-%m-%d")],
                  "close": [99.0, 10.5]}).to_parquet(
                      market / "price_valuation_daily" / "latest.parquet", index=False)

    monkeypatch.setattr(dpmod, "TEJ_CACHE_DIR", str(frozen))
    monkeypatch.setattr(dpmod, "TEJ_RUNTIME_OVERLAY_DIR", str(overlay))
    monkeypatch.setattr(dpmod, "MARKET_CACHE_DIR", str(market))
    dpmod.DataProvider._runtime_overlay_cache.clear()
    dpmod.DataProvider._market_daily_price = None

    got = dpmod.DataProvider._read_local_price_valuation("1213")
    assert got is not None
    # the two dtypes normalise into one sortable datetime column, in order
    assert pd.api.types.is_datetime64_any_dtype(got["date"])
    assert got["date"].tolist() == [early, mid, late]
    # TEJ wins on the overlapping date; the string-sourced 99.0 is discarded
    assert got["close"].tolist() == [10.0, 11.0, 10.5]
