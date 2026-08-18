"""Emit the D-1 churn report the blocking verifier reads.

Converts probe_universe_churn.py's JSON into the flat schema
core.b0_frozen_spec.verify_price_universe_churn expects. Kept separate so the
expensive per-year xlsx scan does not have to be repeated.

READ-ONLY. No performance quantity is computed.
"""

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(HERE, "universe_churn.json")
OUT = os.path.join(REPO, "data", "b0", "price_universe_churn.csv")


def main():
    with open(SRC, encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = []
    for key, v in sorted(payload["churn"].items()):
        year = key.split("->")[0]
        rows.append({
            "year": year,
            "securities": v["present"],
            "dropped_next_year": v["dropped"],
            "added_next_year": v["added"],
            "dropped_but_traded_to_year_end": v["dropped_but_traded_to_year_end"],
            "year_end_session": v["year_end_session"],
        })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {os.path.relpath(OUT, REPO)}  ({len(rows)} years)")
    for r in rows:
        print("   %s  securities=%5d  dropped=%4d  traded_to_year_end=%3d"
              % (r["year"], r["securities"], r["dropped_next_year"],
                 r["dropped_but_traded_to_year_end"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
