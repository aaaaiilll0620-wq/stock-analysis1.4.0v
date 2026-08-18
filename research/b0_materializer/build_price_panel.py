# -*- coding: utf-8 -*-
"""Canonical intermediate: the daily price / valuation panel B0 replays against.

Collapses the per-security corpus under `~/tej_cache/price_valuation` into one
columnar panel carrying exactly the fields the frozen route consumes:

    close            marks (§6.2), sigma20d input (C-26), momentum input
    open             execution price (§6.5: the OPEN of the following session)
    Trading_Volume   with close, the adv20 traded-VALUE input (C-25)
    PER_TSE, PBR_TSE the FROZEN valuation lineage (§3.2 / B-09)

`PER_TEJ` / `PBR_TEJ` are present in the source and are deliberately NOT carried.
B-09 freezes B/M on the TSE lineage, and a panel that shipped both fields would
make substituting the TEJ one a one-word edit. Dropping them makes the frozen
lineage the only thing downstream can read.

No formula is applied here. adv20 and sigma20d are NOT computed in this file:
they are computed by `core.b0_state.compute_adv20` / `compute_sigma20d` at
materialization time, from the series this panel supplies. Putting them here
would be a second implementation of a frozen formula.

READ-ONLY with respect to strategy.

    python research/b0_materializer/build_price_panel.py
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

CORPUS = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
OUT_PARQUET = os.path.join(REPO, "data", "b0", "price_panel.parquet")
OUT_RECEIPT = os.path.join(HERE, "price_panel_receipt.json")

CARRY = ["stock_id", "date", "open", "close", "Trading_Volume", "PER_TSE", "PBR_TSE"]
# Present in the source, intentionally excluded — see module docstring.
EXCLUDED_BY_LINEAGE = ["PER_TEJ", "PBR_TEJ"]


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus_fingerprint(files: list[str]) -> dict:
    """Same shape as research/d1_price_universe/fingerprint_corpus.py (D-1)."""
    lines, rows_total, dmin, dmax = [], 0, None, None
    for f in files:
        df = pd.read_parquet(f, columns=["stock_id", "date"])
        if df.empty:
            continue
        sid = str(df["stock_id"].iloc[0])
        d = df["date"].astype(str)
        lo, hi = d.min(), d.max()
        lines.append(f"{sid}:{lo}:{hi}:{len(df)}")
        rows_total += len(df)
        dmin = lo if dmin is None or lo < dmin else dmin
        dmax = hi if dmax is None or hi > dmax else dmax
    blob = "\n".join(sorted(lines))
    return {"content_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
            "securities": len(lines), "rows": rows_total,
            "date_min": dmin, "date_max": dmax}


def build() -> tuple[pd.DataFrame, dict]:
    files = sorted(glob.glob(os.path.join(CORPUS, "*.parquet")))
    if not files:
        raise SystemExit(f"abort: price corpus not found at {CORPUS}")

    fp = corpus_fingerprint(files)

    frames = []
    for f in files:
        df = pd.read_parquet(f)
        missing = [c for c in CARRY if c not in df.columns]
        if missing:
            raise SystemExit(
                f"abort: {os.path.basename(f)} lacks {missing}. A corpus that cannot "
                f"supply the frozen fields cannot be replayed against.")
        frames.append(df[CARRY])
    panel = pd.concat(frames, ignore_index=True)

    panel["stock_id"] = panel["stock_id"].astype(str).str.strip()
    panel["date"] = pd.to_datetime(panel["date"]).dt.strftime("%Y-%m-%d")
    for c in ("open", "close", "Trading_Volume", "PER_TSE", "PBR_TSE"):
        panel[c] = pd.to_numeric(panel[c], errors="coerce")

    dupes = int(panel.duplicated(subset=["stock_id", "date"]).sum())
    if dupes:
        raise SystemExit(
            f"abort: {dupes} duplicate (stock_id, date) price rows. Which observation "
            f"is the session's price is not something this builder may choose (M-3).")

    panel = panel.sort_values(["stock_id", "date"]).reset_index(drop=True)

    receipt = {
        "artefact": "data/b0/price_panel.parquet",
        "builder": "research/b0_materializer/build_price_panel.py",
        "upstream_corpus": {"dir": CORPUS, **fp},
        "carried_columns": CARRY,
        "excluded_by_frozen_lineage": EXCLUDED_BY_LINEAGE,
        "lineage_note": ("B/M uses PBR_TSE (B-09). TEJ valuation fields exist upstream "
                         "and are excluded so they cannot be substituted downstream."),
        "rows": int(len(panel)),
        "securities": int(panel["stock_id"].nunique()),
        "date_min": str(panel["date"].min()),
        "date_max": str(panel["date"].max()),
        "na_rates": {c: round(float(panel[c].isna().mean()), 6)
                     for c in ("open", "close", "Trading_Volume", "PER_TSE", "PBR_TSE")},
        "schema_sha256": hashlib.sha256("|".join(CARRY).encode("utf-8")).hexdigest(),
        "performance_computed": False,
    }
    return panel, receipt


def main() -> None:
    panel, receipt = build()
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    panel.to_parquet(OUT_PARQUET, index=False)
    receipt["content_sha256"] = _file_sha(OUT_PARQUET)
    receipt["bytes"] = os.path.getsize(OUT_PARQUET)
    with open(OUT_RECEIPT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    for k in ("rows", "securities", "date_min", "date_max", "na_rates",
              "content_sha256"):
        print(f"  {k:24} {receipt[k]}")
    print(f"  upstream corpus sha256   {receipt['upstream_corpus']['content_sha256']}")
    print(f"wrote {os.path.relpath(OUT_PARQUET, REPO)}")


if __name__ == "__main__":
    main()
