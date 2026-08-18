# -*- coding: utf-8 -*-
"""Canonical intermediate: quarterly financials WITH the real announcement date.

Why this exists. §2.2 freezes the availability rule for quarterly fundamentals:

    財報：`financial_statements` 2005-12 起 100% 真實公告日
    任何以固定 lag 代替真實公告日的做法，在 B0 一律禁止。

The raw export carries that date (`財報發布日`), and the frozen importer spec in
`tej_importer.DATASETS["financial_statements"]` already maps it to `release_date`.
The per-security cache under `~/tej_cache/financial_statements` does NOT carry it —
it was written by an older path. Materializing PIT quarterly inputs from that cache
would therefore have required inventing an availability rule, which §2.2 forbids.

So this reads the RAW export and applies the FROZEN importer spec. It introduces no
mapping, no unit convention and no filtering of its own: every rename, every
thousand-scaling and both accepted period formats come from `DATASETS`.

Measured on the sealed export (not assumed):
  * 138,731 rows, and 138,731 distinct (stock_id, 年月) keys — every security-period
    appears exactly ONCE, so no consolidated-vs-individual choice is ever made here.
    124,682 rows are 合併=Y and 14,049 are 合併=N, but never both for one key.
  * `drop_duplicates` is consequently a guard, not a selector. It is kept, and it
    raises rather than silently dropping if that measured fact ever stops holding.

READ-ONLY with respect to strategy. No feature, score, ranking or portfolio quantity
is computed here.

    python research/b0_materializer/build_financials_pit.py
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

import tej_importer as ti                                    # noqa: E402
from core.b0_master_prereg import spec as frozen_spec         # noqa: E402

SPEC = ti.DATASETS["financial_statements"]
# The last decision date L2 can ever stand on. Read from the frozen registry.
WINDOW_END = str(frozen_spec("window_end"))
SOURCE_DIR = str(SPEC["source_dir"])
OUT_PARQUET = os.path.join(REPO, "data", "b0", "financials_pit.parquet")
OUT_RECEIPT = os.path.join(HERE, "financials_pit_receipt.json")

# The identity columns the frozen spec does not rename but this panel needs.
PERIOD_COL = SPEC["date_col"]                                 # 年月
ID_COL = "證券代碼"
CONSOLIDATION_COL = "合併(Y/N)"


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_period(series: pd.Series) -> pd.Series:
    """Both formats the frozen spec accepts, and nothing else."""
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    raw = series.astype(str).str.strip()
    for fmt in SPEC["date_format"]:
        need = out.isna()
        if not need.any():
            break
        out.loc[need] = pd.to_datetime(raw[need], format=fmt, errors="coerce")
    if out.isna().any():
        bad = sorted(raw[out.isna()].unique())[:5]
        raise SystemExit(
            f"abort: {int(out.isna().sum())} period values match neither frozen "
            f"format {SPEC['date_format']}: {bad}. A third format is a source "
            f"change, not something this builder may absorb.")
    return out


def load_raw() -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(SOURCE_DIR, "*.xlsx")))
    if not files:
        raise SystemExit(f"abort: no source workbook under {SOURCE_DIR}")
    frames, sources = [], []
    for f in files:
        df = pd.read_excel(f, engine="openpyxl")
        # The two workbooks differ in header layout (merged vs split id column,
        # 年月 vs 年/月). Both normalisations are the frozen importer's own, so
        # this builder inherits them rather than inventing a second convention.
        df = ti._normalize_source_column_aliases(df, os.path.basename(f))
        df = ti._split_id_name(df)
        missing = [c for c in SPEC["required_cols"]
                   if c != ID_COL and c not in df.columns]
        if missing:
            raise SystemExit(
                f"abort: {os.path.basename(f)} is missing frozen required column(s) "
                f"{missing}. A source that cannot supply them cannot be imported "
                f"under the frozen spec.")
        frames.append(df)
        sources.append({"file": os.path.relpath(f, REPO), "rows": int(len(df)),
                        "sha256": _file_sha(f)})
    return pd.concat(frames, ignore_index=True), sources


def build() -> tuple[pd.DataFrame, dict]:
    raw, sources = load_raw()
    n_raw = len(raw)

    df = raw.rename(columns=SPEC["rename"]).copy()
    df["stock_id"] = raw["stock_id"].astype(str).str.strip()
    df["date"] = _parse_period(raw[PERIOD_COL])
    df["release_date"] = pd.to_datetime(
        raw["財報發布日"], format=SPEC["extra_date_cols"]["release_date"],
        errors="coerce")

    # §2.2: a row whose announcement date cannot be read has no availability, and
    # a fixed-lag substitute is forbidden. Such rows are dropped from the PIT panel
    # and counted, never back-filled.
    no_release = int(df["release_date"].isna().sum())
    df = df[df["release_date"].notna()].copy()

    # A statement announced after the last decision date is unusable by the frozen
    # availability rule (release_date <= decision_date) at EVERY decision date in
    # the window, so it is dropped rather than carried. This is the frozen window
    # plus the frozen rule, not a new one — and it is what removes the only source
    # overlap in the export: the 2026-08 re-export of period 2026-06, which no L2
    # decision could ever have seen.
    unusable = int((df["release_date"] > pd.Timestamp(WINDOW_END)).sum())
    df = df[df["release_date"] <= pd.Timestamp(WINDOW_END)].copy()

    for src, dst in SPEC["thousand_cols"].items():
        df[dst] = pd.to_numeric(df[src], errors="coerce") * 1000.0
    for c in SPEC["numeric_cols"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["consolidated"] = raw.loc[df.index, CONSOLIDATION_COL].astype(str).str.strip()

    keep = (["stock_id", "date", "release_date", "quarter", "consolidated", "eps"]
            + sorted(SPEC["thousand_cols"].values()))
    df = df[keep].sort_values(["stock_id", "date"]).reset_index(drop=True)

    # The measured invariant, enforced rather than trusted.
    dupes = int(df.duplicated(subset=["stock_id", "date"]).sum())
    if dupes:
        raise SystemExit(
            f"abort: {dupes} duplicate (stock_id, period) rows INSIDE the usable "
            f"window. Which of two competing statements for one security-period wins "
            f"is NOT specified by the master preregistration, and must not be decided "
            f"here (M-3). Register it and stop.")

    receipt = {
        "artefact": "data/b0/financials_pit.parquet",
        "builder": "research/b0_materializer/build_financials_pit.py",
        "importer_spec": "tej_importer.DATASETS['financial_statements'] (frozen)",
        "availability_rule": "real 財報發布日 -> release_date; fixed-lag proxies forbidden (§2.2)",
        "sources": sources,
        "rows_raw": int(n_raw),
        "rows_kept": int(len(df)),
        "rows_dropped_no_release_date": no_release,
        "rows_dropped_released_after_window_end": unusable,
        "window_end": WINDOW_END,
        "securities": int(df["stock_id"].nunique()),
        "period_min": str(df["date"].min().date()),
        "period_max": str(df["date"].max().date()),
        "release_min": str(df["release_date"].min().date()),
        "release_max": str(df["release_date"].max().date()),
        "consolidation_basis_counts": {
            str(k): int(v) for k, v in df["consolidated"].value_counts().items()},
        "columns": list(df.columns),
        "schema_sha256": _sha_bytes("|".join(df.columns).encode("utf-8")),
        "performance_computed": False,
    }
    return df, receipt


def main() -> None:
    df, receipt = build()
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    receipt["content_sha256"] = _file_sha(OUT_PARQUET)
    receipt["bytes"] = os.path.getsize(OUT_PARQUET)
    with open(OUT_RECEIPT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    for k in ("rows_raw", "rows_kept", "rows_dropped_no_release_date", "securities",
              "period_min", "period_max", "release_min", "release_max",
              "consolidation_basis_counts", "content_sha256"):
        print(f"  {k:32} {receipt[k]}")
    print(f"wrote {os.path.relpath(OUT_PARQUET, REPO)}")


if __name__ == "__main__":
    main()
