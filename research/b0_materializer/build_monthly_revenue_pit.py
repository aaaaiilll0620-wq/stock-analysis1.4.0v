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

THE SOURCE SET IS ENUMERATED, NOT GLOBBED. Until 2026-08-30 this builder opened
its corpus with `glob(CORPUS/*.xlsx)`. `月營收7月完整.zip` — the completed 202607
export — then matched nothing and raised nothing, so the finalised July would
have been absent from the panel while the rebuild printed a clean receipt.
Every entry in the corpus is now forced into consumed / not_consumed / unknown
against `build_flat_leaves.FLAT_FAMILIES["revenue"]`, and `unknown` aborts.

The same declaration also decides the OVERLAP: both exports carry 202607 (the
workbook partially — 406 of 2,002 securities, all announced by its 08-06 export
date), so the archive OWNS that month and the workbook YIELDS it. Exactly one
source is canonical for a period, and which one is a declaration rather than a
row-order accident.

READ-ONLY with respect to strategy.

    python research/b0_materializer/build_monthly_revenue_pit.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import tej_importer as ti                                      # noqa: E402
import build_flat_leaves as flat                               # noqa: E402
from core.b0_master_prereg import spec as frozen_spec         # noqa: E402
from source_ownership_manifest import (                        # noqa: E402
    assert_periods_conform, norm_period, owns_predicate,
)

SPEC = ti.DATASETS["monthly_revenue"]
# ONE declaration, two consumers. `build_flat_leaves.FLAT_FAMILIES["revenue"]`
# already names every file this corpus may hold and what each one owns; the leaf
# manifest is built from it and so is this panel. A second copy here would be
# two places to update and one place to forget — which is the same defect as a
# glob, only slower to notice.
FAMILY = flat.FLAT_FAMILIES["revenue"]
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


def _assert_corpus_is_the_declared_landing() -> None:
    """The bytes this panel reads and the bytes the leaf declares are one set.

    `CORPUS` comes from `tej_importer.DATASETS`, the leaf's landing comes from
    `FLAT_FAMILIES["revenue"]["landing"]`. They are the same directory today
    (`tej_exports/DataExport0806` is a link into the data tree, and both resolve
    through it). If they ever stop being, the manifest would be attesting one
    directory while the panel was built from another — a lineage claim about
    files nobody read.
    """
    declared = os.path.join(REPO, FAMILY["landing"])
    if os.path.realpath(declared) != os.path.realpath(CORPUS):
        raise SystemExit(
            "abort: the monthly-revenue panel would be built from a directory "
            "the revenue leaf does not declare.\n"
            "  panel reads:   %s\n  leaf declares: %s\n"
            "One of the two is wrong; a panel and its provenance record may not "
            "point at different bytes." % (CORPUS, declared))


def enumerate_corpus() -> tuple[list, list]:
    """Every entry in the corpus is CONSUMED or REJECTED — or this aborts.

    ⚠ THE DEFECT THIS REPLACES. This function used to be
    `glob.glob(CORPUS + "/*.xlsx")`. A glob answers with what it matched and
    says nothing about what it did not: when 月營收7月完整.zip landed here it
    matched nothing, raised nothing, and the completed July month would have
    been absent from the panel while the rebuild printed a clean receipt.
    Omission-by-glob is silent by construction, which is why the enumeration is
    now total.

    Same idiom as `build_flat_leaves.build()`: force every directory entry into
    accepted or `unknown`, and let `unknown` abort. Returns
    (consumed, not_consumed) as filenames in declared order / sorted order.
    """
    _assert_corpus_is_the_declared_landing()
    if not os.path.isdir(CORPUS):
        raise SystemExit(f"abort: monthly revenue export not found at {CORPUS}")

    declared_consumed = tuple(FAMILY["consumed"])
    extensions = tuple(FAMILY["extensions"])
    present, not_consumed, unknown = [], [], []
    for name in sorted(os.listdir(CORPUS)):
        p = os.path.join(CORPUS, name)
        if os.path.islink(p) or not os.path.isfile(p):
            unknown.append(name)
        elif name in declared_consumed:
            present.append(name)
        elif os.path.splitext(name)[1].lower() in extensions:
            not_consumed.append(name)
        else:
            unknown.append(name)
    if unknown:
        raise SystemExit(
            "abort: %d entr(y/ies) in the monthly-revenue corpus are neither "
            "declared-consumed nor declared-rejected:\n%s\n"
            "  directory: %s\n  declared:  %s\n"
            "A file this builder cannot name is a file it would have skipped in "
            "silence. Declare it in FLAT_FAMILIES['revenue'] or remove it."
            % (len(unknown), "\n".join("    %s" % n for n in unknown), CORPUS,
               list(declared_consumed)))

    missing = [n for n in declared_consumed if n not in present]
    if missing:
        raise SystemExit(
            "abort: the revenue family declares %s as consumed but they are not "
            "present under %s. A declared source that disappears must be "
            "noticed, not absorbed." % (missing, CORPUS))
    return [n for n in declared_consumed], not_consumed


def _read_declared(path: str, name: str) -> pd.DataFrame:
    """Read one declared source with the reader its DECLARED format names.

    The format string is the decision, not the extension: 月營收7月完整.zip is a
    zip container whose single member is a UTF-16LE tab-separated csv, and the
    wrong (encoding, separator) pair yields ONE column silently rather than an
    error. An unrecognised declaration aborts — an unparsed declaration is an
    undeclared one.
    """
    fmt = str(FAMILY.get("declarations", {}).get(name, {}).get(
        "format", os.path.splitext(name)[1].lower().lstrip(".")))
    if fmt == "xlsx":
        return pd.read_excel(path, engine="openpyxl")
    if fmt == "zip:csv:utf-16:tab":
        with zipfile.ZipFile(path) as z:
            members = [i for i in sorted(z.infolist(), key=lambda i: i.filename)
                       if not i.is_dir()]
            # The archive's own contents get the same treatment as the
            # directory's: a member that is not the declared kind is not
            # skipped, it stops the build. A member added to a declared zip is
            # as invisible as a file added to a declared directory.
            stray = [i.filename for i in members
                     if not i.filename.lower().endswith(".csv")]
            if stray or not members:
                raise SystemExit(
                    "abort: %s declares csv members only, and holds %s. A "
                    "re-packed archive is a new source, not the same source."
                    % (name, stray or "none"))
            frames = [pd.read_csv(io.BytesIO(z.read(i.filename)),
                                  encoding="utf-16-le", sep="\t")
                      for i in members]
        return pd.concat(frames, ignore_index=True) if len(frames) > 1 \
            else frames[0]
    raise SystemExit(
        "abort: %s declares format %r, which this builder has no reader for. "
        "Guessing a reader is how a UTF-16 tab file becomes one column of "
        "garbage without anyone being told." % (name, fmt))


def _apply_declared_ownership(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the periods this source OWNS; abort on any it never named.

    The two revenue exports OVERLAP on 202607: the workbook carries a partial
    406-security July, the archive the finalised 2,002. Exactly one may be
    canonical for a period (§ the manifest's own rule), so the workbook's July
    rows are dropped HERE — because the declaration says it yields them, not
    because a de-duplicator happened to prefer the other file's row order.

    `assert_periods_conform` is the manifest engine's own predicate, reused
    rather than reimplemented: a period a source neither owns nor yields aborts.
    """
    decl = FAMILY.get("declarations", {}).get(name, {})
    if "owns" not in decl:
        return df
    periods = df["_period"].dropna().unique()
    assert_periods_conform({**decl, "locator": name}, periods)
    owns, _ = owns_predicate(decl["owns"])
    return df[df["_period"].map(lambda p: bool(p) and owns(p))].copy()


def build() -> tuple[pd.DataFrame, dict]:
    files, not_consumed = enumerate_corpus()

    frames, sources = [], []
    for name in files:
        f = os.path.join(CORPUS, name)
        raw = _read_declared(f, name)
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
        # `norm_period` is the manifest engine's own parser and raises on any
        # 年月 it cannot read; a month that cannot be named cannot be owned.
        df["_period"] = raw[SPEC["date_col"]].map(norm_period)
        kept = _apply_declared_ownership(name, df)
        frames.append(kept[CARRY])
        decl = FAMILY.get("declarations", {}).get(name, {})
        sources.append({
            "file": os.path.relpath(f, REPO), "rows": int(len(raw)),
            "sha256": _file_sha(f),
            "format": str(decl.get("format",
                                   os.path.splitext(name)[1].lower().lstrip("."))),
            "owns": decl.get("owns", "ALL_PERIODS_IN_FILE"),
            "yields": list(decl.get("yields", ())),
            # Rows the declaration YIELDED to another source. Reported, not
            # inferred: `rows` minus `rows_owned` is what this file carried and
            # did not get to decide.
            "rows_owned": int(len(kept)),
            "months_owned": int(kept["_period"].nunique()),
            "month_min_owned": (min(kept["_period"]) if len(kept) else None),
            "month_max_owned": (max(kept["_period"]) if len(kept) else None),
        })
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
        # Present in the corpus, deliberately unused, and NAMED — the invariant
        # the glob could not hold. An empty list here means the enumeration
        # found nothing to reject, not that it did not look.
        "not_consumed_in_corpus": [
            {"file": n, "reason": FAMILY["not_consumed_reason"]}
            for n in not_consumed],
        "carried_columns": CARRY,
        "excluded_by_frozen_lineage": EXCLUDED_BY_LINEAGE,
        "lineage_note": ("revenue_yoy / revenue_accel are derived by "
                         "core.b0_features.compute_revenue_yoy (§3.5); the vendor "
                         "YoY column is excluded so it cannot become a second "
                         "growth definition."),
        "rows_read_from_sources": int(sum(s["rows"] for s in sources)),
        # `rows_raw` counts rows that survived the OWNERSHIP split, so it is the
        # population the availability rule then applies to. The difference from
        # `rows_read_from_sources` is rows a source carried and yielded to
        # another source — reported so the split is visible rather than implied.
        "rows_dropped_yielded_to_another_source":
            int(sum(s["rows"] for s in sources)) - int(total),
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
    for k in ("rows_read_from_sources", "rows_dropped_yielded_to_another_source",
              "rows_raw", "rows_kept", "rows_dropped_no_release_date",
              "rows_dropped_released_after_window_end", "securities", "month_min",
              "month_max", "first_real_release_date", "revenue_na_rate",
              "content_sha256"):
        print(f"  {k:38} {receipt[k]}")
    print(f"wrote {os.path.relpath(OUT_PARQUET, REPO)}")


if __name__ == "__main__":
    main()
