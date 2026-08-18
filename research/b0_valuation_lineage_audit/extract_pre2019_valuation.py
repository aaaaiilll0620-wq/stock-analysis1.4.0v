# -*- coding: utf-8 -*-
"""Pre-2019 valuation legs from the ADMISSIBLE yearly export — READ-ONLY.

Both frozen ratios come out of the same sheet in one pass:

    股價淨值比-TSE  ->  pbr_tse      (B-09 Value, ruled C-48)
    本益比-TSE      ->  per_tse      (C-17 PEG numerator, ruling pending)
    收盤價(元)      ->  close        (priced-universe denominator only)

`股價淨值比-TEJ` and `本益比-TEJ` sit in the same rows and are never read.
Years >= 2019 are refused outright: that era of this vintage is the D-1
quarantined corpus, and §2.8.3 puts the admissible boundary at 2018.

Two session sets, because they answer different questions and must not be
confused:

    overlap   the 36 month-end sessions 2016-2018 the PBR reconciliation used.
              Audit only.
    route     the 54 as-of sessions §6.6 resolves for decision months
              2014-07 .. 2018-12 — last completed session STRICTLY BEFORE the
              decision date. This is the set a sealed panel must be keyed to.

    python research/b0_valuation_lineage_audit/extract_pre2019_valuation.py
    B0_SESSION_MODE=route ...
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from harvest_official_pbr import decision_sessions, route_as_of_sessions  # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
YEARLY_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "個股股價、本益比2004-20260817")

MODE = os.environ.get("B0_SESSION_MODE", "overlap").lower()
OUT = os.path.join(ART, "pre2019_valuation_%s.csv" % MODE)

COL_ID, COL_DATE, COL_CLOSE = "代號", "年月日", "收盤價(元)"
COL_PBR_TSE, COL_PER_TSE = "股價淨值比-TSE", "本益比-TSE"
EXCLUDED_BY_LINEAGE = ("股價淨值比-TEJ", "本益比-TEJ")


def sessions_for(mode: str) -> list[str]:
    if mode == "overlap":
        return [s for _, _, s in decision_sessions("2016-01", "2018-12")]
    if mode == "route":
        return [s for _, _, s in route_as_of_sessions("2014-07", "2018-12")]
    raise SystemExit("abort: unknown session mode %r" % mode)


def main() -> None:
    import pandas as pd

    sessions = sessions_for(MODE)
    years = sorted({s[:4] for s in sessions})
    print("mode=%s sessions=%d years=%s" % (MODE, len(sessions), years), flush=True)

    frames = []
    for y in years:
        if int(y) >= 2019:
            raise SystemExit(
                "abort: %s is the quarantined 2019+ vintage of this corpus; the "
                "admissible pre-2019 leg stops at 2018 (§2.8.3)" % y)
        f = os.path.join(YEARLY_DIR, "%sDataExport.xlsx" % y)
        if not os.path.exists(f):
            raise SystemExit("abort: missing admissible yearly export %s" % f)
        d = pd.read_excel(f, engine="openpyxl",
                          usecols=[COL_ID, COL_DATE, COL_CLOSE,
                                   COL_PBR_TSE, COL_PER_TSE])
        d["session"] = pd.to_datetime(
            d[COL_DATE], errors="coerce").dt.strftime("%Y-%m-%d")
        d = d[d["session"].isin(sessions)]
        d["stock_id"] = d[COL_ID].astype(str).str.split().str[0].str.strip()
        d = d.rename(columns={COL_PBR_TSE: "pbr_tse", COL_PER_TSE: "per_tse",
                              COL_CLOSE: "close"})
        frames.append(d[["stock_id", "session", "close", "pbr_tse", "per_tse"]])
        print("  %s: %d rows" % (y, len(d)), flush=True)

    out = pd.concat(frames, ignore_index=True)
    os.makedirs(ART, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8", lineterminator="\n")
    print("sessions=%d rows=%d pbr_na=%d per_na=%d -> %s" % (
        out["session"].nunique(), len(out),
        int(out["pbr_tse"].isna().sum()), int(out["per_tse"].isna().sum()),
        os.path.relpath(OUT, REPO)))


if __name__ == "__main__":
    main()
