# -*- coding: utf-8 -*-
"""Month-end closes on the 87 decision sessions, from the ADMISSIBLE 2019+ corpus.

Reads only `股價 2019-2022.zip` and `股價2023-20260817.zip` — the vintage §2.8.3
made canonical for `>= 2019`. The yearly xlsx files in the same directory are the
quarantined 2019+ vintage and are never opened here (this script globs `*.zip`).

Only the close column is taken. No valuation column is read from this corpus:
the 2019+ zips carry 本益比-TEJ / 股價淨值比-TEJ, and B-09 freezes B/M on the TSE
lineage, so reading them would be the substitution the open item exists to
prevent. The close is used solely to invert the OFFICIAL published ratio into an
implied book value per share.

    python research/b0_valuation_lineage_audit/build_2019plus_closes.py
"""
from __future__ import annotations

import glob
import io
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from harvest_official_pbr import decision_sessions  # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
OUT = os.path.join(ART, "closes_2019plus_month_ends.csv")
SRC_DIR = os.path.join(
    REPO, "tej_exports", "DataExport0806", "個股股價、本益比2004-20260817")


def main() -> None:
    import pandas as pd

    sessions = {s for _, _, s in decision_sessions("2019-01", "2026-03")}
    zips = sorted(glob.glob(os.path.join(SRC_DIR, "*.zip")))
    if not zips:
        raise SystemExit("abort: no admissible zip vintage found in %s" % SRC_DIR)
    print("admissible zips: %s" % [os.path.basename(z) for z in zips], flush=True)

    frames = []
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as fh:
                txt = fh.read().decode("utf-16")
        df = pd.read_csv(io.StringIO(txt), sep="\t",
                         usecols=["證券代碼", "年月日", "收盤價(元)"], dtype=str)
        df["session"] = pd.to_datetime(
            df["年月日"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df[df["session"].isin(sessions)]
        df["stock_id"] = df["證券代碼"].astype(str).str.split().str[0].str.strip()
        df["close"] = pd.to_numeric(df["收盤價(元)"], errors="coerce")
        frames.append(df[["stock_id", "session", "close"]])
        print("  %s: %d rows on decision sessions" % (os.path.basename(z), len(df)),
              flush=True)

    out = pd.concat(frames, ignore_index=True)
    out = out[out["close"].notna() & (out["close"] > 0)]
    os.makedirs(ART, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8")
    print("sessions=%d rows=%d -> %s" % (
        out["session"].nunique(), len(out), os.path.relpath(OUT, REPO)))


if __name__ == "__main__":
    main()
