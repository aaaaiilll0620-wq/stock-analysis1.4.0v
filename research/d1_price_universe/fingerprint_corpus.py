"""Compute a stable content fingerprint for a price corpus (D1-6 / D1-7).

Quarantine is by content hash rather than by path, so that copying or renaming a
contaminated export does not launder it. The fingerprint is the sha256 of the
sorted `symbol:first_date:last_date:rows` manifest — it changes if any security's
coverage changes, which is exactly the property D-1 turns on, and it does not
depend on file layout.

READ-ONLY. No performance quantity is computed.
"""

import glob
import hashlib
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_CORPUS = os.path.join(os.path.expanduser("~"), "tej_cache", "price_valuation")
OUT = os.path.join(HERE, "corpus_fingerprint.json")


def fingerprint(corpus_dir: str):
    lines, securities, dmin, dmax, rows_total = [], 0, None, None, 0
    for f in sorted(glob.glob(os.path.join(corpus_dir, "*.parquet"))):
        df = pd.read_parquet(f, columns=["stock_id", "date"])
        if df.empty:
            continue
        sid = str(df["stock_id"].iloc[0])
        d = df["date"].astype(str)
        lo, hi = d.min(), d.max()
        lines.append(f"{sid}:{lo}:{hi}:{len(df)}")
        securities += 1
        rows_total += len(df)
        dmin = lo if dmin is None or lo < dmin else dmin
        dmax = hi if dmax is None or hi > dmax else dmax
    blob = "\n".join(sorted(lines))
    return {
        "corpus_dir": corpus_dir,
        "content_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(b"stock_id|date|close").hexdigest(),
        "securities": securities,
        "rows": rows_total,
        "date_min": dmin,
        "date_max": dmax,
    }


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CORPUS
    fp = fingerprint(target)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(fp, fh, ensure_ascii=False, indent=1)
    for k, v in fp.items():
        print(f"  {k}: {v}")
    print("wrote", os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
