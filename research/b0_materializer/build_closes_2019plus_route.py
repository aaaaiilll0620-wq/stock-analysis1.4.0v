# -*- coding: utf-8 -*-
"""Rebuild `closes_2019plus_route.csv` — the 2019+ priced-universe denominator.

`build_valuation_panel` needs, for each 2019+ route `as_of` session, the set of
securities that HAVE a price there: an exchange PBR/PER page lists a ratio for
names that are not in B0's canonical price universe, and §2.8 does not let a
valuation row exist for a security B0 cannot price.

That file existed as a hand-made artefact of the C-48 / C-49 lineage audit with
no builder in the repository, cut at the 87 sessions of the then-current window.
It is not a source: every row is a projection of the sealed price panel, which
this reproduces mechanically — verified below by rebuilding the 87 sessions the
hand-made file already carried and refusing to write unless every one of them
comes back identical.

    python research/b0_materializer/build_closes_2019plus_route.py
"""
from __future__ import annotations

import collections
import csv
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "research", "b0_valuation_lineage_audit"))

from harvest_official_pbr import route_as_of_sessions            # noqa: E402

ART = os.path.join(os.environ.get("B0_ARTIFACT_DIR") or
                   os.path.join(REPO, "artifacts"), "valuation_lineage_audit")
OUT = os.path.join(ART, "closes_2019plus_route.csv")
PANEL = os.path.join(REPO, "data", "b0", "price_panel.parquet")
FIRST_OFFICIAL_YM = "2019-01"


def _read_existing(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    by_session = collections.defaultdict(dict)
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            by_session[r["session"]][r["stock_id"]] = float(r["close"])
    return dict(by_session)


def main() -> None:
    from core.b0_master_prereg import spec as frozen_spec

    window_to = str(frozen_spec("window_end"))[:7]
    sessions = [s for _, _, s in route_as_of_sessions(FIRST_OFFICIAL_YM, window_to)]
    print("route as_of sessions %s..%s : %d"
          % (FIRST_OFFICIAL_YM, window_to, len(sessions)), flush=True)

    px = pd.read_parquet(PANEL, columns=["stock_id", "date", "close"])
    px["date"] = px["date"].astype(str).str[:10]
    px["stock_id"] = px["stock_id"].astype(str)
    px = px[px["date"].isin(set(sessions))]
    px = px[px["close"].notna() & (px["close"] > 0)]

    built = collections.defaultdict(dict)
    for r in px.itertuples(index=False):
        built[r.date][r.stock_id] = float(r.close)

    missing = [s for s in sessions if not built.get(s)]
    if missing:
        raise SystemExit(
            "abort: the sealed price panel has no priced security on %s. The "
            "denominator cannot be projected from a panel that does not reach "
            "the window." % ", ".join(missing))

    # The regression gate: whatever the hand-made file already asserted must
    # come back unchanged, or this builder is not reproducing it and the 87
    # sealed sessions would silently acquire a new lineage.
    existing = _read_existing(OUT)
    drift = []
    for sess, rows in sorted(existing.items()):
        if built.get(sess) != rows:
            got, want = built.get(sess, {}), rows
            drift.append("%s (%d -> %d securities)" % (sess, len(want), len(got)))
    if drift:
        raise SystemExit(
            "abort: rebuilding changed %d session(s) the previous file already "
            "carried: %s. A denominator that moves under a window extension is "
            "not a projection of the panel." % (len(drift), "; ".join(drift[:6])))
    print("reproduced %d pre-existing sessions unchanged" % len(existing), flush=True)

    os.makedirs(ART, exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["stock_id", "session", "close"])
        for sess in sessions:
            for sid in sorted(built[sess]):
                w.writerow([sid, sess, built[sess][sid]])
    os.replace(tmp, OUT)

    added = [s for s in sessions if s not in existing]
    print("sessions written %d (new: %s)"
          % (len(sessions), ", ".join(added) or "none"), flush=True)
    print("rows %d" % sum(len(built[s]) for s in sessions), flush=True)
    print("wrote", os.path.relpath(OUT, REPO), flush=True)


if __name__ == "__main__":
    main()
