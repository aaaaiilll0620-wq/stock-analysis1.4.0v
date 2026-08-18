"""D-1 · inventory and fingerprint the 20260817 price export (candidate source).

Deliberately makes NO assumption that the new export fixes anything. It reports
what is there — coverage, schema, securities, rows, hashes — and the verifier
decides separately.

The folder mixes vintages: the yearly .xlsx files are the OLD (contaminated)
2004-2026 vintage carried over, and the two .zip files dated 2026-08-18 are the
new material, covering 2019 onward. The candidate canonical source is therefore
the zips for 2019+, with the pre-2019 era served by the existing yearly files —
which were never the defect (2012-2017 showed ordinary churn against the
independent reference).

That is a VINTAGE BOUNDARY, not a patch. The distinction matters: a patch adds
back the specific securities observed to be missing, which is forbidden; this
replaces an entire era wholesale and is then re-verified from scratch.

READ-ONLY. No return, IC, Sharpe, ranking or selection quantity is computed.
"""

import glob
import hashlib
import io
import json
import os
import sys
import zipfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NEW_DIR = os.path.join(REPO, "tej_exports", "DataExport0806",
                       "個股股價、本益比2004-20260817")
OUT = os.path.join(HERE, "new_export_inventory.json")
PARQUET_OUT = os.path.join(REPO, "data", "b0", "price_2019plus_new.parquet")

EXPECTED_COLUMNS = (
    "證券代碼", "年月日", "開盤價(元)", "最高價(元)", "最低價(元)", "收盤價(元)",
    "成交量(千股)", "成交值(千元)", "流通在外股數(千股)", "本益比-TEJ", "股價淨值比-TEJ",
)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def d8(s):
    s = s.strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else None


def read_zip(path):
    """Stream the member CSV; returns (header, row_iter_factory, member_info)."""
    zf = zipfile.ZipFile(path)
    name = zf.namelist()[0]
    info = zf.getinfo(name)
    return zf, name, info


def main():
    zips = sorted(glob.glob(os.path.join(NEW_DIR, "*.zip")))
    if not zips:
        print("no zips found in", NEW_DIR)
        return 1

    per_sec_years = defaultdict(set)
    per_sec_first = {}
    per_sec_last = {}
    per_sec_rows = defaultdict(int)
    rows_total = 0
    schemas = {}
    members = []
    member_hash = hashlib.sha256()

    for z in zips:
        zf, name, info = read_zip(z)
        members.append({
            "zip": os.path.basename(z),
            "zip_sha256": file_sha256(z),
            "zip_bytes": os.path.getsize(z),
            "member": name,
            "member_bytes": info.file_size,
            "member_date": "%04d-%02d-%02d" % info.date_time[:3],
        })
        with zf.open(name) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-16", newline="")
            header = stream.readline().rstrip("\r\n").split("\t")
            schemas[os.path.basename(z)] = header
            i_id = header.index("證券代碼")
            i_d = header.index("年月日")
            for line in stream:
                if not line.strip():
                    continue
                f = line.rstrip("\r\n").split("\t")
                if len(f) <= max(i_id, i_d):
                    continue
                sid = f[i_id].split()[0]
                d = d8(f[i_d])
                if d is None:
                    continue
                member_hash.update(f"{sid}|{d}\n".encode("utf-8"))
                rows_total += 1
                per_sec_rows[sid] += 1
                per_sec_years[sid].add(d[:4])
                if sid not in per_sec_first or d < per_sec_first[sid]:
                    per_sec_first[sid] = d
                if sid not in per_sec_last or d > per_sec_last[sid]:
                    per_sec_last[sid] = d
        zf.close()
        print(f"  scanned {os.path.basename(z)}  rows so far {rows_total:,}")

    same_schema = len({tuple(v) for v in schemas.values()}) == 1
    schema_ok = all(tuple(v) == EXPECTED_COLUMNS for v in schemas.values())
    all_years = sorted({y for ys in per_sec_years.values() for y in ys})
    dmin = min(per_sec_first.values())
    dmax = max(per_sec_last.values())

    # Content fingerprint in the SAME form used for the old corpus, so the two
    # are directly comparable and the new one can be shown to differ.
    manifest = "\n".join(sorted(
        f"{s}:{per_sec_first[s]}:{per_sec_last[s]}:{per_sec_rows[s]}"
        for s in per_sec_first))
    content_sha = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
    schema_sha = hashlib.sha256(
        "|".join(EXPECTED_COLUMNS).encode("utf-8")).hexdigest()

    per_year_counts = {}
    for y in all_years:
        per_year_counts[y] = sum(1 for ys in per_sec_years.values() if y in ys)

    payload = {
        "study": "D-1 new price export inventory",
        "read_only": True, "performance_computed": False,
        "source_dir": os.path.relpath(NEW_DIR, REPO).replace("\\", "/"),
        "members": members,
        "schema_identical_across_members": same_schema,
        "schema_matches_expected": schema_ok,
        "schema": schemas[os.path.basename(zips[0])],
        "securities": len(per_sec_first),
        "rows": rows_total,
        "date_min": dmin, "date_max": dmax,
        "years": all_years,
        "securities_per_year": per_year_counts,
        "content_sha256": content_sha,
        "schema_sha256": schema_sha,
        "row_key_sha256": member_hash.hexdigest(),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print("\nsecurities      :", f"{len(per_sec_first):,}")
    print("rows            :", f"{rows_total:,}")
    print("coverage        :", dmin, "..", dmax)
    print("schema identical:", same_schema, "| matches expected:", schema_ok)
    print("content_sha256  :", content_sha)
    print("\nsecurities per year:")
    for y in all_years:
        print("   %s  %5d" % (y, per_year_counts[y]))

    # Persist the per-security coverage the audit needs, so the expensive scan
    # happens once.
    import pandas as pd
    pd.DataFrame([{"stock_id": s, "first": per_sec_first[s],
                   "last": per_sec_last[s], "rows": per_sec_rows[s],
                   "years": ",".join(sorted(per_sec_years[s]))}
                  for s in sorted(per_sec_first)]).to_parquet(
                      PARQUET_OUT, index=False)
    print("\nwrote", os.path.relpath(OUT, REPO))
    print("wrote", os.path.relpath(PARQUET_OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
