import numpy as np
import pandas as pd
import pytest

from scripts.build_face_postprocess_arms import (
    _c3_buckets,
    _percentile_desc,
    build_arm,
)


def _diag(rows):
    d = pd.DataFrame(rows)
    d["score_error"] = ""
    d["composite_indep"] = d["real_composite"]
    return d


def test_percentile_desc_matches_frozen_formula_and_preserves_nan():
    got = _percentile_desc(pd.Series([10.0, 20.0, np.nan, 20.0]))
    assert got.iloc[0] == pytest.approx(100.0 - 2.0 * 100.0 / 3.0)
    assert got.iloc[1] == pytest.approx(100.0)
    assert np.isnan(got.iloc[2])
    assert got.iloc[3] == pytest.approx(100.0 - 100.0 / 3.0)


def test_c3_percentiles_are_calculated_within_each_as_of():
    rows = []
    for as_of, values in [("2005-01-31", [1.0, 2.0]), ("2005-02-28", [100.0, 200.0])]:
        for i, v in enumerate(values):
            rows.append({"as_of": as_of, "stock_id": str(i), "b_fund": v,
                         "b_val": 50.0, "b_tech": 50.0, "b_mom": 50.0,
                         "b_whale": 50.0, "regime": "neutral", "dyn_weight": False,
                         "real_composite": 50.0})
    got = _c3_buckets(_diag(rows))
    assert got.loc[0, "b_fund"] == got.loc[2, "b_fund"] == 50.0
    assert got.loc[1, "b_fund"] == got.loc[3, "b_fund"] == 100.0


def test_c1_removes_regime_but_keeps_dynamic_weight():
    row = {"as_of": "2020-01-31", "stock_id": "1", "b_fund": 50.0,
           "b_val": 10.0, "b_tech": 50.0, "b_mom": 50.0, "b_whale": 50.0,
           "regime": "bear", "dyn_weight": False, "real_composite": 0.0}
    got = build_arm("C1", _diag([row]))
    # C1 must be nominal balanced weighting: .31*50 + .08*10 + .19*50 + .27*50 + .15*50.
    assert got.loc[0, "real_composite"] == pytest.approx(46.8)


def test_c3_keeps_regime_weighting_after_bucket_percentiles():
    rows = []
    for i, v in enumerate([10.0, 20.0]):
        rows.append({"as_of": "2020-01-31", "stock_id": str(i), "b_fund": v,
                     "b_val": 50.0, "b_tech": 50.0, "b_mom": 50.0,
                     "b_whale": 50.0, "regime": "bear", "dyn_weight": False,
                     "real_composite": 0.0})
    got = build_arm("C3", _diag(rows))
    assert got.loc[0, "b_fund_pct"] == 50.0
    assert got.loc[1, "b_fund_pct"] == 100.0
    assert got["real_composite"].notna().all()
