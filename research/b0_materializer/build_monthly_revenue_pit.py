# -*- coding: utf-8 -*-
"""Canonical intermediate: monthly revenue with its real announcement date.

§2.2, quoted:

    月營收：讀**真實 `release_date`**，不得使用固定 lag 代理
    （舊 `REVENUE_LAG_DAYS = 10` 已 Remove）

§2.1 makes that date the binding constraint on the whole window:

    資料邊界 = monthly_revenue 真實公告日 2013-01
    First eligible decision month = 2013-01 + 18 = 2014-07

So the window start is a CONSEQUENCE of where real announcement dates begin. This
panel therefore reports where they actually begin rather than assuming it, and a
month without one is dropped and counted — never given a lag proxy.

Only the revenue series is carried. `revenue_yoy_pct` exists upstream and is NOT
carried: §3.5 derives revenue_yoy — and revenue_accel as a difference of exactly
that quantity — through `core.b0_features.compute_revenue_yoy`. Shipping a
vendor-computed YoY alongside it would put a second growth definition within
reach of the materializer.

READ-ONLY with respect to strategy.

    python research/b0_materializer/build_monthly_revenue_pit.py
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

import tej_importer as ti                                      # noqa: E402
from core.b0_master_prereg import spec as frozen_spec         # noqa: E402

SPEC = ti.DATASETS["monthly_revenue"]
# Read the RAW export, not ~/tej_cache/monthly_revenue: that cache begins at
# 2019-01, which would silently give Growth no history for the 54 window months
# before 2019. Measured on the raw export, 營收發布日 is present for 100% of rows
# from 2013 and 0% before — which is exactly the boundary §2.1 states, and the
# reason the window opens at 2014-07 (2013-01 + 18).
CORPUS = str(SPEC["source_dir"])
OUT_PARQUET = os.path.join(REPO, "data", "b0", "monthly_revenue_pit.parquet")
OUT_RECEIPT = os.path.join(HERE, "monthly_revenue_pit_receipt.json")

WINDOW_END = str(frozen_spec("window_end"))
CARRY = ["stock_id", "date", "release_date", "revenue"]
EXCLUDED_BY_LINEAGE = ["revenue_yoy_pct", "cum_revenue", "cum_revenue_last_year",
                       "revenue_last_year"]


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build() -> tuple[pd.DataFrame, dict]:
    files = sorted(glob.glob(os.path.join(CORPUS, "*.xlsx")))
    if not files:
        raise SystemExit(f"abort: monthly revenue export not found at {CORPUS}")

    frames, sources = [], []
    for f in files:
        raw = pd.read_excel(f, engine="openpyxl")
        raw = ti._normalize_source_column_aliases(raw, os.path.basename(f))
        raw = ti._split_id_name(raw)
        missing = [c for c in SPEC["required_cols"]
                   if c != "證券代碼" and c not in raw.columns]
        if missing:
            raise SystemExit(
                f"abort: {os.path.basename(f)} lacks frozen required column(s) "
                f"{missing}; without a real release_date §2.2 leaves no admissible "
                f"way to date these rows.")
        df = raw.rename(columns=SPEC["rename"]).copy()
        df["stock_id"] = raw["stock_id"].astype(str).str.strip()
        df["date"] = pd.to_datetime(raw[SPEC["date_col"]].astype(str).str.strip(),
                                    format=SPEC["date_format"], errors="coerce")
        # TEJ writes "." for an absent announcement date (all pre-2013 rows).
        # Coerced to NaT and dropped below — never given a lag proxy (§2.2).
        rel = pd.to_numeric(raw["營收發布日"], errors="coerce")
        df["release_date"] = pd.to_datetime(
            rel.astype("Int64").astype(str).replace("<NA>", ""),
            format=SPEC["extra_date_cols"]["release_date"], errors="coerce")
        df["revenue"] = pd.to_numeric(df["_revenue_thousand"], errors="coerce") * 1000.0
        frames.append(df[CARRY])
        sources.append({"file": os.path.relpath(f, REPO), "rows": int(len(raw)),
                        "sha256": _file_sha(f)})
    panel = pd.concat(frames, ignore_index=True)

    total = len(panel)
    no_release = int(panel["release_date"].isna().sum())
    panel = panel[panel["release_date"].notna()].copy()

    # Announced after the last decision date -> unusable at every decision date.
    unusable = int((panel["release_date"] > pd.Timestamp(WINDOW_END)).sum())
    panel = panel[panel["release_date"] <= pd.Timestamp(WINDOW_END)].copy()

    dupes = int(panel.duplicated(subset=["stock_id", "date"]).sum())
    if dupes:
        raise SystemExit(
            f"abort: {dupes} duplicate (stock_id, month) revenue rows inside the "
            f"usable window; which one is the month's revenue is not specified (M-3).")

    panel = panel.sort_values(["stock_id", "date"]).reset_index(drop=True)
    panel["date"] = panel["date"].dt.strftime("%Y-%m-%d")
    panel["release_date"] = panel["release_date"].dt.strftime("%Y-%m-%d")

    first_real = panel["release_date"].min()
    receipt = {
        "artefact": "data/b0/monthly_revenue_pit.parquet",
        "builder": "research/b0_materializer/build_monthly_revenue_pit.py",
        "availability_rule": "real release_date; fixed-lag proxies forbidden (§2.2)",
        "upstream_sources": sources,
        "carried_columns": CARRY,
        "excluded_by_frozen_lineage": EXCLUDED_BY_LINEAGE,
        "lineage_note": ("revenue_yoy / revenue_accel are derived by "
                         "core.b0_features.compute_revenue_yoy (§3.5); the vendor "
                         "YoY column is excluded so it cannot become a second "
                         "growth definition."),
        "rows_raw": int(total),
        "rows_kept": int(len(panel)),
        "rows_dropped_no_release_date": no_release,
        "rows_dropped_released_after_window_end": unusable,
        "window_end": WINDOW_END,
        "securities": int(panel["stock_id"].nunique()),
        "month_min": str(panel["date"].min()),
        "month_max": str(panel["date"].max()),
        "first_real_release_date": str(first_real),
        "declared_data_boundary": "2013-01 (§2.1)",
        "revenue_na_rate": round(float(panel["revenue"].isna().mean()), 6),
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
    for k in ("rows_raw", "rows_kept", "rows_dropped_no_release_date",
              "rows_dropped_released_after_window_end", "securities", "month_min",
              "month_max", "first_real_release_date", "revenue_na_rate",
              "content_sha256"):
        print(f"  {k:38} {receipt[k]}")
    print(f"wrote {os.path.relpath(OUT_PARQUET, REPO)}")


if __name__ == "__main__":
    main()
